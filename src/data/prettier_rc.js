// https://github.com/prettier/prettier/issues/15388#issuecomment-1717746872
const config = {
  plugins: [
    require.resolve("prettier-plugin-sh"),
    require.resolve("prettier-plugin-toml"),
  ],
};

module.exports = config;
