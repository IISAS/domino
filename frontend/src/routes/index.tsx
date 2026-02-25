import { useAuthentication } from "@context/authentication";
import { useRoutes } from "react-router-dom";

import { protectedRoutes } from "./protected";
import { publicRoutes } from "./public";

export const AppRoutes = () => {
  const element = useRoutes([
    ...publicRoutes,
    ...protectedRoutes,
  ]);

  return <>{element}</>;
};
