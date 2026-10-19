/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // O navegador fala apenas com o mesmo domínio; o Next encaminha /api para o backend.
  // Assim o cookie de sessão é httpOnly/same-site e nenhuma chave de API chega ao frontend.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
