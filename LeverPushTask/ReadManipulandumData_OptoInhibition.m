clearvars data out outnew currentday

folderpath = 'G:\Other computers\My Computer\Thalamus_optogenetics\ThalOpto_Manipulandum_CSV_optosessions\';

files = dir(fullfile(folderpath, '*.csv'));
load('D:\Dropbox\SU_Ding Lab\Code\Thal_Manipulandum_Opto\BaseStimFrames.mat')

corrstart = 800;
corrend = 900;

for i = 1:numel(files)

filename = files(i).name;
filepath = [folderpath filename];

if exist(filepath)==0
    continue
else
currentmouse = filename(1:12);
data = readtable(filepath);
robotstate = table2array(data(:,11));


% Use this to find the first frame by when manipulandum recording started
% (currently this is done when caframe trigger data is missing
robot_1 = find(robotstate==1); %find frames with robot state = 1 which corresponds to Waiting for movement (before the mouse is pushing joystick), and happens after session/block is started
frame_first = robot_1(1); % find first frame by identifying first time robot is in robot state 1 (waiting for movement).
Ca_frame_column =NaN(size(data,1),1);

if strcmp(currentmouse, 'RR20230628_U')
    frame_first = 144000; %refer to notes for why
end

frame_last = frame_first+(15*60*200); % last frame is 15 min after start
if size(data,1) < frame_last
    frame_last = size(data,1);
end

recorded_length = (frame_last - frame_first)./200; %length of analyzed recording in sec

data = data(frame_first:frame_last,:);
Ca_frame_column = Ca_frame_column(frame_first:frame_last,:);
robotstate2 = table2array(data(:,11));


% Find all trials

    % Find robot transition from 1 to 0 (this is each time the manipulandum detected a movement and went from movement to hold) 
    trial_all_idxs = find(diff(robotstate2 == 0 & circshift(robotstate2 == 1, 1)) == 1);
    
    num_trials = length(trial_all_idxs);


% Find rewarded trials
   
    % Find rewarded trials based on reward delivery state
    reward_delivery = table2array(data(:,10)); %Column 10 is reward delivery
    reward_idxs = find(diff([0; reward_delivery]) == 1); %find row indeces of rewards by finding unique transitions in reward delivery states
    
    num_rewards = length(reward_idxs);
    num_rewards2 = sum(reward_delivery)./14; %find number of rewards by dividing reward time by 14 (assuming 70ms reward duration at 200hz)
    
    % Find which trials of all trials are rewarded
    trial_all_idxs_rewarded = NaN (num_trials,1);
    for j = 1:num_trials
    if min(abs(reward_idxs - trial_all_idxs(j))) < 500
        trial_all_idxs_rewarded(j) = 1;
    else
        trial_all_idxs_rewarded(j) = 0;
    end
    end
    num_rewards3 = sum(trial_all_idxs_rewarded);
    trial_all_idxs_rewarded=logical(trial_all_idxs_rewarded);
    trial_all_rewarded_idxs = trial_all_idxs(trial_all_idxs_rewarded);



%

out(i).date = currentmouse;
out(i).trials = num_trials;
out(i).rewards = num_rewards;
out(i).length = recorded_length;
out(i).S_rate = num_rewards./num_trials;
out(i).trial_all_idxs = trial_all_idxs;
out(i).trial_all_rewarded_idxs = trial_all_rewarded_idxs;
out(i).trial_all_idxs_rewarded = trial_all_idxs_rewarded;


% hold on
% scatter(trial_all_idxs,i*ones(num_trials,1))


%% Pull out y-positions for all trials
clearvars trials_y
y_coordinate = table2array(data(:,2));
% trialidxsused = trial_all_rewarded_idxs;
trialidxsused = trial_all_idxs;

for k = 1:numel(trialidxsused)
    if size(data,1) > trialidxsused(k)+800 && trialidxsused(k) > 800
        y_currenttrial = y_coordinate(trialidxsused(k)-800:trialidxsused(k)+800,1);
        robotstate2_currenttrial = robotstate2 (trialidxsused(k)-800:trialidxsused(k)+800,1);
        y_currenttrial(robotstate2_currenttrial==3)=NaN; %Remove y values for the returning portion of the previous trial
    else
        y_currenttrial = NaN(1601,1);
    end
trials_y(:,k) = y_currenttrial;

% figure
% plot(y_currenttrial)
% figure
% plot(robotstate2_currenttrial)
end
out(i).trials_y=trials_y;


% %%
% figure
% plot(trials_y(:,82))
% figure
% plot(diff(trials_y(:,82)))


%% Find movement onsets and align trials to this
clearvars shiftAmounts maxIndices maxPeaks locs

trials_diff = diff(trials_y(1:801,:));
trials_y_aligned = zeros(size(trials_y));

for col = 1:size(trials_y, 2)
    [peaks, locs] = findpeaks(trials_diff(:, col), 'MinPeakHeight', 0.25, 'NPeaks', 1);
    if ~isempty(locs)
    maxIndices(col) = locs(1);
    maxPeaks(col) = peaks(1);
    else
        [peaks, locs] = findpeaks(trials_diff(:, col), 'MinPeakHeight', 0.15, 'NPeaks', 1); 
        if ~isempty(locs)
        maxIndices(col) = locs(1);
        maxPeaks(col) = peaks(1);
        else
        maxIndices(col) = 801;  
        maxPeaks(col) = NaN;
        end
    end
    currentshiftAmount = (801 - maxIndices(col));
    shiftAmounts(col) = currentshiftAmount;
    trials_y_aligned(:, col) = [NaN(currentshiftAmount, 1); trials_y(1:end-currentshiftAmount, col)];
end

trial_all_idxs_onsets = trial_all_idxs-shiftAmounts';
trial_all_rewarded_idxs_onsets = trial_all_idxs_onsets(trial_all_idxs_rewarded);
trial_all_failed_idxs_onsets = trial_all_idxs_onsets(~trial_all_idxs_rewarded);

trial_all_Ca_frame = Ca_frame_column(trial_all_idxs_onsets,1);
trial_reward_Ca_frame = Ca_frame_column(trial_all_rewarded_idxs_onsets,1);
trial_failed_Ca_frame = Ca_frame_column(trial_all_failed_idxs_onsets,1);

out(i).shiftAmounts_all = shiftAmounts; %this represents movement duration
out(i).shiftAmounts_rewarded = shiftAmounts(trial_all_idxs_rewarded');
out(i).shiftAmounts_failed = shiftAmounts(~trial_all_idxs_rewarded');

out(i).trials_y_aligned = trials_y_aligned;
out(i).trials_y_aligned_reward = trials_y_aligned(:,trial_all_idxs_rewarded');
out(i).trials_y_aligned_failed = trials_y_aligned(:,~trial_all_idxs_rewarded');

out(i).trial_all_idxs_onsets=trial_all_idxs_onsets;
out(i).trial_all_rewarded_idxs_onsets=trial_all_rewarded_idxs_onsets;
out(i).trial_all_failed_idxs_onsets=trial_all_failed_idxs_onsets;

out(i).trial_all_Ca_frame=trial_all_Ca_frame;
out(i).trial_reward_Ca_frame=trial_reward_Ca_frame;
out(i).trial_failed_Ca_frame=trial_failed_Ca_frame;


%% Find max y

trials_y_aligned_max = max(trials_y_aligned(700:1000,:));

out(i).trials_y_aligned_max_all = trials_y_aligned_max;
out(i).trials_y_aligned_max_rewarded = trials_y_aligned_max(trial_all_idxs_rewarded');
out(i).trials_y_aligned_max_failed = trials_y_aligned_max(~trial_all_idxs_rewarded');

%% Find reward presentation using post-shift onset idxs
clearvars trials_rewarddelivery

trialidxsused = trial_all_idxs_onsets;
% trialidxsused = trial_all_rewarded_idxs_onsets;

for k = 1:numel(trialidxsused)
    if size(data,1) > trialidxsused(k)+800 && trialidxsused(k) > 800
        reward_currenttrial = reward_delivery(trialidxsused(k)-800:trialidxsused(k)+800,1);
        reward_currenttrial(1:800,1)=NaN; %Remove y values for the returning portion of the previous trial
    else
        reward_currenttrial = NaN(1601,1);
    end
trials_rewarddelivery(:,k) = reward_currenttrial;

end

% figure
% plot(trials_rewarddelivery)
out(i).trials_rewarddelivery_all=trials_rewarddelivery;
out(i).trials_rewarddelivery_rewarded=trials_rewarddelivery(:,trial_all_idxs_rewarded');

%% Find licking using post-shift onset idxs
clearvars trials_licking

licking = table2array(data(:,9));
trialidxsused = trial_all_idxs_onsets;
% trialidxsused = trial_all_rewarded_idxs_onsets;

for k = 1:numel(trialidxsused)
    if size(data,1) > trialidxsused(k)+800 && trialidxsused(k) > 800
        licking_currenttrial = licking(trialidxsused(k)-800:trialidxsused(k)+800,1);
%         licking_currenttrial(1:800,1)=NaN; %Remove y values for the returning portion of the previous trial
    else
        licking_currenttrial = NaN(1601,1);
    end
trials_licking(:,k) = licking_currenttrial;

end

% figure
% plot(trials_licking)

out(i).trials_licking_all=trials_licking;
out(i).trials_licking_rewarded=trials_licking(:,trial_all_idxs_rewarded');
out(i).trials_licking_failed=trials_licking(:,~trial_all_idxs_rewarded');

%% Plot aligned trials
% trials_to_plot = trials_y_aligned(:,trial_all_idxs_rewarded');
% % trials_to_plot = trials_y_aligned(:,~trial_all_idxs_rewarded');
% 
% figure
% plot(diff(trials_to_plot))
% xlim([1 1600])
% figure
% plot(trials_to_plot)
% xlim([1 1600])



%% split things by baseline, stim, post-stim

% % trials split by baseline, stim, post-stim
% base_logi = trial_all_idxs>BaseStimFrames(i,1)*200 & trial_all_idxs<=BaseStimFrames(i,2)*200; %baseline
% stim_logi = trial_all_idxs>BaseStimFrames(i,2)*200 & trial_all_idxs<=BaseStimFrames(i,3)*200; %stim
% post_logi = trial_all_idxs>BaseStimFrames(i,3)*200 & trial_all_idxs<=BaseStimFrames(i,4)*200; %post stim

% trials split by baseline, stim, post-stim with better timing
base_logi = trial_all_idxs>(BaseStimFrames(i,2)-120)*200 & trial_all_idxs<=BaseStimFrames(i,2)*200; %baseline
stim_logi = trial_all_idxs>(BaseStimFrames(i,3)-120)*200 & trial_all_idxs<=BaseStimFrames(i,3)*200; %stim
post_logi = trial_all_idxs>(BaseStimFrames(i,3)+60)*200 & trial_all_idxs<=(BaseStimFrames(i,3)+60+120)*200; %post stim


out(i).base_logi = base_logi;
out(i).stim_logi = stim_logi;
out(i).post_logi = post_logi;

% Use this to find trials
out(i).trials_base = sum(base_logi);
out(i).trials_stim = sum(stim_logi);
out(i).trials_post = sum(post_logi);

out(i).rewardtrials_base = sum(base_logi.*trial_all_idxs_rewarded);
out(i).rewardtrials_stim = sum(stim_logi.*trial_all_idxs_rewarded);
out(i).rewardtrials_post = sum(post_logi.*trial_all_idxs_rewarded);


% trial y-values
out(i).trials_y_aligned_all_base = trials_y_aligned(:,base_logi);
out(i).trials_y_aligned_all_stim = trials_y_aligned(:,stim_logi);
out(i).trials_y_aligned_all_post = trials_y_aligned(:,post_logi);

out(i).trials_y_aligned_rewarded_base = trials_y_aligned(:,logical(base_logi.*trial_all_idxs_rewarded));
out(i).trials_y_aligned_rewarded_stim = trials_y_aligned(:,logical(stim_logi.*trial_all_idxs_rewarded));
out(i).trials_y_aligned_rewarded_post = trials_y_aligned(:,logical(post_logi.*trial_all_idxs_rewarded));

out(i).trials_y_aligned_failed_base = trials_y_aligned(:,logical(base_logi.*~trial_all_idxs_rewarded));
out(i).trials_y_aligned_failed_stim = trials_y_aligned(:,logical(stim_logi.*~trial_all_idxs_rewarded));
out(i).trials_y_aligned_failed_post = trials_y_aligned(:,logical(post_logi.*~trial_all_idxs_rewarded));

% trial y-max values
out(i).trials_y_aligned_max_all_base = trials_y_aligned_max(:,base_logi);
out(i).trials_y_aligned_max_all_stim = trials_y_aligned_max(:,stim_logi);
out(i).trials_y_aligned_max_all_post = trials_y_aligned_max(:,post_logi);

out(i).trials_y_aligned_max_rewarded_base = trials_y_aligned_max(:,logical(base_logi.*trial_all_idxs_rewarded));
out(i).trials_y_aligned_max_rewarded_stim = trials_y_aligned_max(:,logical(stim_logi.*trial_all_idxs_rewarded));
out(i).trials_y_aligned_max_rewarded_post = trials_y_aligned_max(:,logical(post_logi.*trial_all_idxs_rewarded));

out(i).trials_y_aligned_max_failed_base = trials_y_aligned_max(:,logical(base_logi.*~trial_all_idxs_rewarded));
out(i).trials_y_aligned_max_failed_stim = trials_y_aligned_max(:,logical(stim_logi.*~trial_all_idxs_rewarded));
out(i).trials_y_aligned_max_failed_post = trials_y_aligned_max(:,logical(post_logi.*~trial_all_idxs_rewarded));

% Movement duration
out(i).shiftAmounts_all_base = shiftAmounts(:,base_logi); %this represents movement duration
out(i).shiftAmounts_all_stim = shiftAmounts(:,stim_logi); %this represents movement duration
out(i).shiftAmounts_all_post = shiftAmounts(:,post_logi); %this represents movement duration

out(i).shiftAmounts_rewarded_base = shiftAmounts(:,logical(base_logi.*trial_all_idxs_rewarded));
out(i).shiftAmounts_rewarded_stim = shiftAmounts(:,logical(stim_logi.*trial_all_idxs_rewarded));
out(i).shiftAmounts_rewarded_post = shiftAmounts(:,logical(post_logi.*trial_all_idxs_rewarded));

out(i).shiftAmounts_failed_base = shiftAmounts(:,logical(base_logi.*~trial_all_idxs_rewarded));
out(i).shiftAmounts_failed_stim = shiftAmounts(:,logical(stim_logi.*~trial_all_idxs_rewarded));
out(i).shiftAmounts_failed_post = shiftAmounts(:,logical(post_logi.*~trial_all_idxs_rewarded));

