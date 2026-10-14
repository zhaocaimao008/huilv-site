# 今日汇率换算站(全自动)

一个中文汇率查询/换算静态网站：
- 14 种货币、182 个货币对页面 + 260 个"X 元等于多少 Y"金额页面,共约 440 页
- 每个页面包含今日汇率、在线换算器、30 日走势图、对照表、历史汇率、常见问题
- 数据来自欧洲央行(ECB)公开参考汇率(通过免费的 Frankfurter API),无需 API Key
- GitHub Actions 每个工作日自动抓数据、重新生成、发布到 GitHub Pages,**全程零服务器、零费用**
- 自动生成 sitemap.xml、robots.txt、ads.txt,填入广告 ID 后自动在页面插入 Google AdSense 广告位

## 一次性设置(手机上也能完成)

1. **仓库设为公开**(GitHub Pages 免费版要求公开仓库)。
2. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**。
3. 修改 `config.json`:
   - `base_url`:改成你的域名,例如 `https://huilv.example.cn`
   - `site_name`:网站名称
4. 在域名注册商处给这个域名加一条 DNS 记录:
   - 子域名(如 `huilv.xxx.com`):`CNAME` 指向 `你的GitHub用户名.github.io`
   - 根域名(如 `xxx.com`):`A` 记录指向 `185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`
5. Settings → Pages 里填写 Custom domain,勾选 **Enforce HTTPS**。
6. 到 **Google Search Console** 和 **Bing Webmaster** 添加网站并提交 `https://你的域名/sitemap.xml`。
7. 网站有一定内容和流量后申请 **Google AdSense**,拿到 `ca-pub-xxxxxxxx` 填到 `config.json` 的 `adsense_client`,提交即可自动上广告。

之后无需任何操作：每个工作日自动更新。

## 本地/离线测试

```bash
python3 build.py --sample   # 用模拟数据生成到 dist/
python3 -m http.server -d dist
```

## 扩展

- 增减货币或金额:改 `config.json` 的 `currencies` / `amounts`(仅限欧洲央行发布的币种)。
- 多个域名:复制本仓库,改 `config.json` 的域名和网站名即可再开一个站。
