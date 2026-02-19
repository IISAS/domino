import { lazyImport } from "@utils/lazyImports";
import SignInPage from "@features/auth/pages/signIn/signInPage";
import SignUpPage from "@features/auth/pages/signUp/signUpPage";
import { Navigate } from "react-router-dom";

const { AuthRoutes } = lazyImport(
  async () => await import("@features/auth/routes"),
  "AuthRoutes",
);

export const publicRoutes = [
  { path: "sign-in", element: <SignInPage /> },
  { path: "sign-up", element: <SignUpPage /> },
  // { path: "recover-password", element: <RecoverPasswordPage /> },

  // Catch-all for invalid public routes
  { path: "*", element: <Navigate to="/sign-in" replace /> },
];
