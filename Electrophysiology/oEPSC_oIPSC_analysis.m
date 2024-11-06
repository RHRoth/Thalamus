%%
clear
DropboxPath = 'D:\Dropbox\';

Overview = readtable([DropboxPath 'SU_Ding Lab\Thalamus\EPhys\Overview_read_Aug2024.xlsx']);

Output = struct('Mouse',[],'Date',[],'Cell',[],'baseline_450nm_70mV',[],'peak_450nm_70mV',[],'oEPSC_450nm_70mV',[],'oEPSC_450nm_70mV_trace',[],'baseline_450nm_10mV',[],'peak_450nm_10mV',[],'oIPSC_450nm_10mV',[],'oIPSC_450nm_10mV_trace',[],'baseline_593nm_10mV',[],'peak_593nm_10mV',[],'oIPSC_593nm_10mV',[],'oIPSC_593nm_10mV_trace',[],'baseline_593nm_70mV',[],'peak_593nm_70mV',[],'oEPSC_593nm_70mV',[],'oEPSC_593nm_70mV_trace',[]);
%%
% for i=1
for i=1:size(Overview,1)
    path = Overview.Var8{i};
    Output.Mouse{i,1} = Overview.Var1{i};
    Output.Date(i,1) = Overview.Var2(i);
    Output.Cell{i,1} = Overview.Var3(i);
    recording_450nm_70mV = ['AD0_' num2str(Overview.Var4(i))];
    recording_593nm_10mV = ['AD0_' num2str(Overview.Var5(i))];
    recording_450nm_10mV = ['AD0_' num2str(Overview.Var6(i))];
    recording_593nm_70mV = ['AD0_' num2str(Overview.Var7(i))];

    % 450nm -70mV
    load([path '\' recording_450nm_70mV]);
    file = eval(recording_450nm_70mV);

    Output.baseline_450nm_70mV(i,1) = mean(file.data(1,20000:20500));
    Output.peak_450nm_70mV(i,1) = min(file.data(1,20500:21000));
    Output.oEPSC_450nm_70mV(i,1) = Output.peak_450nm_70mV(i,1) - Output.baseline_450nm_70mV(i,1);
    Output.oEPSC_450nm_70mV_trace{i,1} = file.data(1,20000:23000);

    figure
    subplot(4,1,1)
    plot(file.data)
    title([num2str(i) '  450nm -70mV'])

    % 450nm 10mV
    load([path '\' recording_450nm_10mV]);
    file = eval(recording_450nm_10mV);

    Output.baseline_450nm_10mV(i,1) = mean(file.data(1,20000:20500));
    Output.peak_450nm_10mV(i,1) = max(file.data(1,20500:21000));
    Output.oIPSC_450nm_10mV(i,1) = Output.peak_450nm_10mV(i,1) - Output.baseline_450nm_10mV(i,1);
    Output.oIPSC_450nm_10mV_trace{i,1} = file.data(1,20000:23000);
   
    subplot(4,1,2)
    plot(file.data)
    title([num2str(i) '  450nm 10mV'])

    % 593nm 10mV
    load([path '\' recording_593nm_10mV]);
    file = eval(recording_593nm_10mV);
    
    if length(file.data) < 81000
    
        Output.baseline_593nm_10mV(i,1) = mean(file.data(1,20000:20500));
        Output.peak_593nm_10mV(i,1) = max(file.data(1,20500:21000));
        Output.oIPSC_593nm_10mV(i,1) = Output.peak_593nm_10mV(i,1) - Output.baseline_593nm_10mV(i,1);
        Output.oIPSC_593nm_10mV_trace{i,1} = file.data(1,20000:23000);

    elseif length(file.data) > 81000
    
        Output.baseline_593nm_10mV(i,1) = mean(file.data(1,81500:82000));
        Output.peak_593nm_10mV(i,1) = max(file.data(1,82000:82500));
        Output.oIPSC_593nm_10mV(i,1) = Output.peak_593nm_10mV(i,1) - Output.baseline_593nm_10mV(i,1);
        Output.oIPSC_593nm_10mV_trace{i,1} = file.data(1,81500:84500);
    end
  
    subplot(4,1,3)
    plot(file.data)
    title([num2str(i) '  593nm 10mV'])
    
    % 593nm -70mV
    load([path '\' recording_593nm_70mV]);
    file = eval(recording_593nm_70mV);
    
    if length(file.data) < 81000
    
        Output.baseline_593nm_70mV(i,1) = mean(file.data(1,20000:20500));
        Output.peak_593nm_70mV(i,1) = min(file.data(1,20500:21000));
        Output.oEPSC_593nm_70mV(i,1) = Output.peak_593nm_70mV(i,1) - Output.baseline_593nm_70mV(i,1);
        Output.oEPSC_593nm_70mV_trace{i,1} = file.data(1,20000:23000);

    elseif length(file.data) > 81000
    
        Output.baseline_593nm_70mV(i,1) = mean(file.data(1,81500:82000));
        Output.peak_593nm_70mV(i,1) = min(file.data(1,82000:82500));
        Output.oEPSC_593nm_70mV(i,1) = Output.peak_593nm_70mV(i,1) - Output.baseline_593nm_70mV(i,1);
        Output.oEPSC_593nm_70mV_trace{i,1} = file.data(1,81500:84500);
    end
  
    subplot(4,1,4)
    plot(file.data)
    title([num2str(i) '  593nm -70mV'])
    
end

