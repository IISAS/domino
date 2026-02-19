import { useAuthentication } from "@context/authentication";
import { type ReactNode, type FC } from "react";
import { Navigate, useLocation } from "react-router-dom";

export interface Props {
  children?: ReactNode;
}

export const NotFoundRoute: FC = () => {
  return <h1>404 - Not Found</h1>;
};
