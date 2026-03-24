import { isEmpty, repoPathFromUrl } from "utils";
import * as yup from "yup";

import { type GenerateWorkflowsParams } from "../context/workflowsEditor";

export const importJsonWorkflow = (
  e: React.ChangeEvent<HTMLInputElement>,
): Promise<GenerateWorkflowsParams> | null => {
  const file = e.target.files?.[0];

  if (file) {
    return new Promise<GenerateWorkflowsParams>((resolve, reject) => {
      const reader = new FileReader();

      reader.onload = (e) => {
        try {
          const jsonData = JSON.parse(
            e.target?.result as string,
          ) as GenerateWorkflowsParams;

          resolve(jsonData); // Resolve the promise with the JSON data
        } catch (error) {
          reject(error as Error); // Reject the promise with an error if JSON parsing fails
        }
      };

      reader.readAsText(file);
    });
  }

  return null; // Return null if no file is selected
};

export const validateJsonImported = (json: any): void => {
  const schema = yup
    .object()
    .shape({
      workflowEdges: yup
        .array()
        .of(
          yup.object().shape({
            id: yup.string().required(),
            source: yup.string().required(),
            target: yup.string().required(),
          }),
        )
        .required(),
      workflowNodes: yup
        .array()
        .of(
          yup
            .object()
            .shape({
              data: yup
                .object()
                .shape({
                  name: yup.string().required(),
                  orientation: yup.string().required(),
                })
                .required(),
              position: yup
                .object()
                .shape({
                  x: yup.number().required(),
                  y: yup.number().required(),
                })
                .required(),
            })
            .required(),
        )
        .required(),
      workflowPieces: yup.lazy((value) => {
        if (!isEmpty(value)) {
          const validationObject = {
            id: yup.number().required(),
            source_image: yup.string().required(),
            source_url: yup.string().required(),
            repository_url: yup.string().required(),
            input_schema: yup.object().shape({}).required(),
            output_schema: yup.object().shape({}).required(),
          };
          const newEntries = Object.keys(value).reduce(
            (acc, val) => ({
              ...acc,
              [val]: yup.object(validationObject),
            }),
            {},
          );

          return yup.object().shape(newEntries).required();
        }
        return yup.mixed().notRequired();
      }),
      workflowPiecesData: yup.mixed(),
    })
    .strict()
    .noUnknown();

  schema.validateSync(json);
};

export interface Differences {
  source: string;
  repository_url: string;
  installedVersion: string | null;
  requiredVersion: string;
}
export const findDifferencesInJsonImported = (
  json: any,
  pieces: Piece[],
): Differences[] => {
  const currentRepositories = new Set<string>(
    Object.values(pieces)?.map(
      (p) =>
        repoPathFromUrl(p?.repository_url) +
          ":" +
          p?.source_image.split(":")[1]?.replace(/-group\d+$/g, "") || "",
    ) || [],
  );

  // Map "path:version" -> full repository_url so DifferencesModal can use it directly
  const incomeRepositoriesMap = new Map<string, string>();
  Object.values(json.workflowPieces).forEach((next: any) => {
    const path = repoPathFromUrl(next.repository_url);
    const version = next.source_image
      .split(":")[1]
      ?.replace(/-group\d+$/g, "");
    if (path && version) {
      incomeRepositoriesMap.set(`${path}:${version}`, next.repository_url);
    }
  });

  const differences = [...incomeRepositoriesMap.keys()].filter(
    (x) => !currentRepositories.has(x),
  );

  return differences.map((d) => {
    const source = d.split(":")[0];
    const requiredVersion = d.split(":")[1];
    const installedVersion = [...currentRepositories].find((cr) =>
      cr.startsWith(source + ":"),
    );

    return {
      source,
      repository_url: incomeRepositoriesMap.get(d) ?? "",
      installedVersion: installedVersion
        ? installedVersion.split(":")[1]
        : null,
      requiredVersion,
    };
  });
};
