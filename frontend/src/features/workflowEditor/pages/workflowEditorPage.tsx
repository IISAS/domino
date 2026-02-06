import { Grid } from "@mui/material";

import { WorkflowsEditorComponent } from "../components/WorkflowEditor";
import WorkflowsEditorProviderWrapper from "../context";

export const WorkflowsEditorPage: React.FC = () => {
  return (
    <Grid container>
      <Grid size={{ xs:12 }}>
        <WorkflowsEditorProviderWrapper>
          <WorkflowsEditorComponent />
        </WorkflowsEditorProviderWrapper>
      </Grid>
    </Grid>
  );
};
