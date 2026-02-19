import { ForbiddenPage } from "@components/Routes/ForbiddenPage";
import { NotFoundRoute } from "@components/Routes/NotFoundRoute";
import { PublicRoute } from "@components/Routes/PublicRoute";
import React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import SignInPage from "../pages/signIn/signInPage";
import SignUpPage from "../pages/signUp/signUpPage";

export const AuthRoutes: React.FC = () => {
  const location = useLocation();
  return (
    <Routes>
      {/* Root redirect */}
      <Route index element={<Navigate to="sign-in" replace />} />

      {/* Public-only routes */}
      <Route element={<PublicRoute publicOnly />}>
        <Route path="sign-in" element={<SignInPage />} />
        <Route path="sign-up" element={<SignUpPage />} />
        {/*<Route path="recover-password" element={<h1>Recover password</h1>} />*/}
      </Route>

      {/* Standalone routes */}
      <Route path="forbidden" element={<ForbiddenPage />} />
      <Route path="404" element={<NotFoundRoute />} />

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/404" state={{ from: location.pathname }} replace />}/>
    </Routes>
  );
};
