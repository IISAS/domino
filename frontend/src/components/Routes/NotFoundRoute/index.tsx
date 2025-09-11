import { useAuthentication } from "@context/authentication";
import { getBasename } from "@utils/basenameUtils";
import { type ReactNode, type FC } from "react";
import { Navigate, useLocation } from "react-router-dom";

export interface Props {
  children?: ReactNode;
}

export const NotFoundRoute: FC<Props> = () => {
  const { isLogged } = useAuthentication();
  const { state } = useLocation();
  const basename = getBasename();

  if (isLogged) {
    return state &&
      state.from === basename + (state.from.endsWith("/") ? "/" : "") ? (
      <>
        <Navigate to="/workspaces" replace />
      </>
    ) : (
      <>
        <h1>404 - Not Found</h1>
      </>
    );
  } else {
    return state &&
      state.from === basename + (state.from.endsWith("/") ? "/" : "") ? (
      <>
        <Navigate to="/sign-in" replace />
      </>
    ) : (
      <>
        <h1>404 - Not Found</h1>
      </>
    );
  }
};
