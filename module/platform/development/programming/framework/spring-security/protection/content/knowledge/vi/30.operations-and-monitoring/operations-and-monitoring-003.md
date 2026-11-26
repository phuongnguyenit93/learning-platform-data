# Chuyển CSP từ Report-Only sang thực thi có kiểm soát

## Mục tiêu và phạm vi

Trong chương **Vận hành và giám sát** của module **SPRING_SECURITY_HTTP_PROTECTION**, **Content Security Policy (CSP)** là lớp phòng vệ phía trình duyệt giúp giới hạn nguồn tài nguyên và hành vi script mà document được phép sử dụng. Spring Security có thể phát header CSP, nhưng **chọn policy, điều tra vi phạm và chuyển sang chế độ chặn thật** là công việc của cả frontend, backend, bảo mật và vận hành.

Một trang web có thể hoạt động bình thường khi dùng **Content-Security-Policy-Report-Only**, nhưng trắng trang hoặc mất chức năng khi đổi sang **Content-Security-Policy** thực thi (*Enforce*). Ngược lại, giữ Report-Only vô thời hạn khiến policy chỉ tạo báo cáo mà không ngăn nguồn tài nguyên trái phép theo những directive hỗ trợ báo cáo. Vì vậy cần một lộ trình **quan sát → sửa lỗi → thử nghiệm → canary → Enforce → giám sát** với tiêu chí cụ thể.

Bài học kết hợp phạm vi của dịch vụ **SPRING_SECURITY_HTTP_PROTECTION**: security headers, CSP, CSRF, CORS, HSTS, HTTP firewall và bảo vệ session. Trọng tâm là **chuyển CSP có kiểm soát** ở ứng dụng **Servlet và Reactive/WebFlux**, với frontend HTML có thể do Spring, CDN hoặc một gateway riêng phục vụ.

Sau bài học, người học có thể:

1. Phân biệt chính xác **CSP Report-Only** và **CSP Enforce**, kể cả khi hai headers cùng xuất hiện.
2. Xây dựng danh sách script, style, image, font, connect, iframe và endpoint theo từng user flow trước khi viết policy.
3. Thiết kế **chính sách thử nghiệm chặt hơn**, báo cáo vi phạm có kiểm soát dữ liệu và tránh log lộ token/session.
4. Chuyển từ inline scripts/styles và nguồn tùy ý sang **nonce, hash, code migration** và host allowlist có review.
5. Cấu hình CSP trên **HttpSecurity (Servlet)** và **ServerHttpSecurity (WebFlux)** đúng vị trí phát HTML document.
6. Triển khai song song **Enforce policy hiện có** và **Report-Only policy ứng viên** khi cần.
7. Đặt **CI gates, browser E2E tests, CSP violation metrics, canary thresholds và rollback runbook**.
8. Giải thích giới hạn CSP: không thay input validation, output encoding, CSRF, authentication, authorization hoặc TLS.

## 1. Report-Only và Enforce khác nhau thế nào?

Hai header sau **không tương đương**:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
~~~

- **Report-Only:** Browser đánh giá chính sách ứng viên và có thể ghi cảnh báo hoặc gửi báo cáo vi phạm, nhưng **không chặn tải/chạy chỉ vì policy thử nghiệm đó**. Việc phát báo cáo phụ thuộc hỗ trợ trình duyệt, sampling và đường thu thập.
- **Enforce:** Browser **áp dụng hạn chế** theo directive hỗ trợ; tài nguyên hay hành vi không thỏa policy có thể bị chặn. Policy thực thi vẫn có thể phát báo cáo nếu có reporting directives.
- **Cùng lúc:** Có thể phát **một Enforce policy đang được duyệt** và **một Report-Only policy ứng viên chặt hơn**. Browser tiếp tục chặn theo Enforce, còn policy ứng viên cung cấp thêm tín hiệu dự kiến nếu được bật. Report-Only **không làm yếu** Enforce hiện có.
- **Nhiều Enforce policies:** Browser áp dụng từng policy được gửi; về thực tế hành vi phải vượt qua **tất cả chính sách áp dụng**, chứ không chọn policy rộng nhất. Header bị nhân đôi ngoài chủ đích có thể chặn tài nguyên bất ngờ.
- **CSP trong meta tag:** Có giới hạn so với HTTP header, ví dụ không cung cấp tương đương đầy đủ cho Report-Only và một số directive; ưu tiên **HTTP response header trên HTML document**.

### 1.1. Sơ đồ chuyển đổi

~~~mermaid
flowchart LR
    A["Inventory tài nguyên và user flows"] --> B["Định nghĩa CSP candidate"]
    B --> C["Report-Only và thu reports"]
    C --> D["Phân loại violations, sửa app"]
    D --> E["E2E/CI regression + baseline"]
    E --> F["Canary: bật Enforce cho cohort"]
    F --> G{"Lỗi/violation và SLO đạt?"}
    G -->|Có| H["Mở rộng Enforce"]
    G -->|Không| I["Dừng canary, rollback đúng policy"]
    I --> D
    H --> J["Giám sát CSP/drift sau release"]
~~~

**Không đổi tên header từ Report-Only sang Enforce rồi mới đi tìm lỗi.** Khi đó lỗi chức năng sẽ xuất hiện trước khả năng xử lý và thường dẫn đến phản ứng nguy hiểm: mở script-src * hoặc unsafe-inline để trang hoạt động lại.

### 1.2. CSP giảm rủi ro gì, không giải quyết gì?

CSP giúp **hạn chế việc tải và thực thi script, style và các tài nguyên từ nguồn không được phép**, tùy directive và browser. Một CSP tốt có thể giảm tác động của một số lỗ hổng XSS; frame-ancestors hỗ trợ phòng clickjacking, object-src giới hạn plugin/object.

Tuy nhiên, CSP **không bảo đảm ngăn mọi XSS**; script đã được phép có thể vẫn thao tác DOM và gửi request trong quyền của trang. CSP không thay:

- **Output encoding, template escaping, DOM sanitization và Trusted Types** khi thích hợp.
- **CsrfFilter/CsrfWebFilter** cho request cookie-authenticated thay đổi trạng thái.
- **CORS allowlist** để giới hạn origin JavaScript nào được đọc credentialed API response.
- **Authentication, authorization, rate limiting và kiểm tra dữ liệu nghiệp vụ**.
- **TLS/HSTS** chống rủi ro trên đường truyền hoặc downgrade.
- **HTTP firewall và URL normalization** trên Servlet/gateway.
- **Secure/HttpOnly/SameSite** của session cookie và quản lý phiên.

CSP là **defense in depth**, không phải lý do xóa các lớp HTTP protection khác.

## 2. Chọn đúng response: CSP bảo vệ HTML document ở origin nào?

Một kiến trúc SPA thường có:

~~~text
Browser
  https://app.example.com/            <- HTML document, JS bundles
  https://static.example.com/app.js    <- static asset/CDN
  https://api.example.com/api/orders   <- JSON API + cookie/auth
~~~

**CSP bảo vệ document cần được gửi trên response HTML của app.example.com.** Header CSP trên response JSON từ api.example.com **không tự lan sang** document được tải từ app.example.com.

Nếu HTML do Spring MVC hoặc WebFlux trả về, cấu hình CSP trên Spring Security chain phục vụ HTML. Nếu HTML do CDN/static hosting trả về, policy phải ở **frontend origin/CDN**. Nếu gateway thay response, phải kiểm tra ở **HTTPS public edge** sau mọi tầng.

### 2.1. Kiểm kê entrypoints thay vì chỉ kiểm tra trang chủ

| Trang/bề mặt | Tài nguyên và hành vi thường cần kiểm tra |
| --- | --- |
| Login và MFA | Form, CSS, JS, captcha provider, redirect/SSO |
| SPA shell | Main bundle, chunk loading, CSS, icon, manifest |
| Profile/settings | Upload preview, avatar image, API calls, validation |
| Checkout/payment | Third-party script, iframe, redirect, postMessage |
| Documentation/docs | Syntax highlight, inline snippets, iframe demos |
| Admin console | Widgets, charts, export, embedded dashboard |
| Error pages | HTML do Spring, gateway, CDN hoặc WAF tạo |
| Legacy SSR/templates | Inline script, inline event handler, style attributes |
| Service worker/PWA | Worker, manifest, offline assets, caching |
| Reports/analytics | Beacon, image pixel, script nguồn bên thứ ba |

**Không lấy một lần mở trang chủ rồi kết luận CSP đã sẵn sàng.** Những luồng ít truy cập như logout, reset password, callback OAuth, lỗi 403/500, in hóa đơn hoặc mở popup thường có scripts/iframes riêng.

### 2.2. Định nghĩa chủ sở hữu của HTML và các response trung gian

- **Spring app:** SecurityFilterChain hoặc SecurityWebFilterChain có match HTML route không?
- **Static CDN:** Header được cấu hình tại hosting/CDN, có khác giữa path/regions không?
- **Ingress/WAF:** Có xóa/nhân đôi/ghi đè CSP trên 200/3xx/4xx/5xx không?
- **Browser:** Enforce hay Report-Only, hỗ trợ directive nào, có blocked resource không?
- **CSP reporter:** Reports từ browser nào, policy revision nào, source nào, được scrub trước lưu chưa?

Một release cần gắn **artifact digest, config revision, CDN policy revision và CSP policy revision** để phát hiện drift và rollback nhất quán.

## 3. Kiểm kê nguồn tài nguyên và xây dựng CSP baseline

Trước khi áp Report-Only, bắt đầu từ **asset/source inventory**. Danh sách cần phân biệt nguồn cần thiết, nguồn di sản, nguồn không tin cậy và nguồn chưa xác minh.

| Directive | Nhóm hành vi | Kiểm kê thực tế |
| --- | --- | --- |
| **default-src** | Fallback cho một số directive khi không định nghĩa riêng | Baseline hạn chế, không để wildcard theo thói quen |
| **script-src** | Script execution và một số hành vi script liên quan | Bundle, dynamic import, third-party JS, inline code |
| **script-src-elem / script-src-attr** | Script elements và inline attributes ở browser hỗ trợ | Script tags, inline event handlers |
| **style-src** | Stylesheets và inline styles theo semantics hỗ trợ | CSS bundles, critical CSS, style attr |
| **img-src** | Images và nguồn URL ảnh | CDN ảnh, avatar, blob/data nếu thật cần |
| **font-src** | Font downloads | Self-hosted fonts/CDN font |
| **connect-src** | fetch, XHR, WebSocket, EventSource và các kết nối JS khác | API, realtime, analytics, reporting SDK |
| **frame-src** | Embedded frames do document tải | Payment/SSO iframe, video |
| **frame-ancestors** | Những origin được phép nhúng document | Clickjacking policy theo từng trang |
| **object-src** | object/embed và plugin content | Thường đặt none |
| **base-uri** | Giá trị base của document | Thường self hoặc none |
| **form-action** | Đích gửi biểu mẫu | Login, checkout, SSO submit endpoints |
| **worker-src** | Worker/service worker | PWA workers hoặc fallback hợp lệ |
| **manifest-src** | Web app manifest | Manifest URL |
| **report-uri / report-to** | Đích thu CSP violations | Collector an toàn, giới hạn thông tin |

**Chú ý các directive có fallback khác nhau**: không mặc định mọi directive đều fallback về default-src (ví dụ frame-ancestors, form-action, base-uri cần được khai báo riêng nếu là yêu cầu bảo vệ). Đồng thời, connect-src có thể ảnh hưởng WebSocket; kiểm thử qua browser thật.

### 3.1. Policy ứng viên không phải allowlist mọi thứ thấy trong báo cáo

Ví dụ một policy **Report-Only ban đầu** cho SPA với API riêng origin:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.com; font-src 'self'; connect-src 'self' https://api.example.com; form-action 'self'; report-uri /__csp/report
~~~

Đây là **ví dụ có chủ đích hạn chế**. App có inline scripts, analytics, payment iframe hoặc style runtime có thể phát violations — đó là tín hiệu để phân tích, không phải bằng chứng cần thêm mọi domain quan sát được.

**Không tự động thêm origin lạ vào CSP chỉ vì có violation**: một violation có thể là quảng cáo/trình duyệt extension, script injection, XSS attempt hoặc lỗi extension, không phải chức năng hợp lệ của app.

### 3.2. Giữ baseline chống clickjacking và plugin abuse

Ngay cả khi script-src còn đang được tinh chỉnh, có thể xem xét sớm các directives sau trong policy phù hợp:

~~~text
object-src 'none';
base-uri 'self';
frame-ancestors 'none';
form-action 'self';
~~~

Tuy nhiên, **frame-ancestors 'none' chặn việc trang của bạn bị iframe nhúng**, nên các sản phẩm cần iframe hợp lệ phải có danh sách ancestor cụ thể. form-action 'self' có thể chặn submit tới payment/SSO ngoài origin. Không copy toàn bộ mà không kiểm kê luồng nghiệp vụ.

### 3.3. Tại sao cần version policy?

Ghi mã revision, ví dụ csp-policy-v4, trong **release manifest hoặc nhãn của monitoring**, không nhất thiết nhét một directive vô nghĩa vào CSP. Khi thấy violations, phải biết policy version ứng viên, frontend version, hostname, route nhóm và browser family; nếu không, reports của hai release có thể bị trộn, khiến đội vận hành sửa nhầm.

## 4. Report-Only cần telemetry đáng tin nhưng không lộ bí mật

Đưa browser CSP reports về backend không có nghĩa nên log nguyên JSON. Báo cáo có thể chứa **document URL, blocked URL, source file, line/column, sample của script** và các trường chưa tin cậy. Một URL có thể chứa **query chứa token, email hoặc dữ liệu cá nhân** nếu hệ thống đã thiết kế URL không an toàn.

### 4.1. Hai cơ chế báo cáo cần biết

Với các browser hỗ trợ, một cấu hình có thể gồm:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.com/csp"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-to csp-endpoint; report-uri /__csp/report
~~~

- **report-to csp-endpoint** sử dụng Reporting API/Reporting-Endpoints ở những trình duyệt triển khai tương ứng.
- **report-uri /__csp/report** là cơ chế cũ có giá trị fallback cho một số browser; cơ chế và format body không giống hoàn toàn report-to.
- Một số browser ưu tiên report-to khi hỗ trợ và bỏ qua report-uri trong policy tương ứng. **Không kỳ vọng hai endpoint luôn nhận cùng một violation**.
- Chính sách report-only có thể sinh cảnh báo ở DevTools nhưng **không gửi network report** nếu endpoint bị chặn, browser không hỗ trợ, privacy settings hoặc sampling.
- **report-sample** có thể đưa một đoạn nội dung inline script/style vào báo cáo; cần đánh giá rủi ro dữ liệu trước khi bật.

**Không dựa vào số báo cáo bằng 0 như bằng chứng chắc chắn không có vi phạm**. Cần kết hợp kiểm thử browser thực, synthetic scripts cố ý vi phạm ở staging và kiểm tra availability của report collector.

### 4.2. Format báo cáo không đồng nhất

Một số browser gửi payload dạng cũ:

~~~http
POST /__csp/report HTTP/1.1
Content-Type: application/csp-report

{"csp-report":{"document-uri":"https://app.example.com/profile","violated-directive":"script-src-elem","blocked-uri":"https://cdn.example.net/a.js","disposition":"report"}}
~~~

Reporting API có thể gửi danh sách JSON objects với Content-Type: application/reports+json và các field khác. Payload là **untrusted input**, không coi blocked-uri, source-file hoặc bất kỳ URL nào là bí mật đáng tin để lưu nguyên.

### 4.3. Quy tắc an toàn cho report collector

1. Endpoint chỉ nhận **report data**, không thay đổi trạng thái session hoặc nghiệp vụ.
2. **Không yêu cầu user login** để ghi một report. Browser có thể gửi report không kèm credential bạn mong đợi.
3. Đặt **body size limit, rate limit, content type validation** và giới hạn retention.
4. **Normalize** document-uri, source-file theo route template/host group; bỏ query/fragment và bí mật.
5. Không lưu raw Cookie/Authorization, request headers hay script sample có thể chứa dữ liệu người dùng.
6. Giới hạn origin báo cáo và chống spam theo threat model; không tin payload từ internet là báo cáo browser thật.
7. Phân loại disposition = report/enforce khi có, loại directive, route group và policy revision.
8. Không mở CORS wildcard có credentials chỉ để report đến được collector; reporting mechanism không tương đương JavaScript fetch.
9. Nếu collector nằm ở origin khác, xác minh browser compatibility và network path thực bằng test, không chỉ kết luận từ server 200.
10. Một endpoint nhận report ở app Spring Security cần **quy tắc CSRF riêng, rất hẹp** nếu POST không có CSRF token; không tắt CSRF cho /api/** hoặc browser session.

### 4.4. Đừng coi mọi vi phạm là tấn công

| Nhóm báo cáo | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Ứng dụng hợp lệ bị chặn** | Checkout script từ domain payment đã duyệt | Review dependency rồi allowlist đúng origin/path hoặc refactor |
| **Inline script legacy** | HTML template nhúng script không nonce/hash | Chuyển sang external file, nonce hoặc hash có kiểm soát |
| **Browser extension** | URL kiểu extension injection | Phân loại, tránh nới policy server chỉ vì extension |
| **Thư viện dùng eval** | Bundle phát vi phạm unsafe-eval | Xác định dependency/build mode, thay cách build hoặc thư viện |
| **CSP reporting noise** | Browser cũ, duplicate reports, parser quirks | Normalize và phân nhóm |
| **Nghi vấn XSS/probing** | Inline handler/script bất ngờ, nguồn lạ | Điều tra cùng app logs đã scrub, không tự allowlist |
| **False positive do policy sai origin** | API hostname thay nhưng connect-src chưa cập nhật | Sửa contract theo deploy revision, test E2E |

Quan sát **số lượng, tần suất, đường nghiệp vụ, loại browser và thời điểm rollout**. Một domain lạ có traffic lớn vẫn không mặc định là dependency hợp lệ.

## 5. Các giai đoạn chuyển từ Report-Only sang Enforce

### 5.1. Giai đoạn 0 — Khai báo policy, owner và ranh giới

Đầu tiên, định nghĩa:

- **HTML origins và routes được áp dụng**, ví dụ app.example.com/ và /checkout, không gộp nhầm với JSON API host khác.
- **CSP revision** và artifact/frontend build tương ứng, ví dụ policy-v4 cùng frontend r42.
- **Các directives bắt buộc** theo threat model: script-src, object-src, base-uri, frame-ancestors, form-action, connect-src, v.v.
- **Những nguồn thật sự được phê duyệt**; mỗi external script có owner, lý do, phạm vi và kế hoạch loại bỏ nếu không cần.
- **Các workflow quan trọng** và bộ browser cần test: login/MFA, đăng ký, reset password, checkout, admin, offline/PWA.
- **SLO/SLA và mức độ nghiêm trọng**: lỗi checkout khác một font trang marketing bị thiếu.
- **Tiêu chí rollback** cùng người có quyền dừng canary/đổi CDN policy.
- **Privacy policy cho CSP reports**; report endpoint không được thu raw URL, Cookie, session hay đoạn script chứa dữ liệu cá nhân.

Gắn chính sách vào Git/Infrastructure as Code, không giữ bản cuối chỉ trong screenshot của DevTools.

### 5.2. Giai đoạn 1 — Report-Only trên các document đã xác định

Phát **Content-Security-Policy-Report-Only** với candidate CSP. Browser vẫn cho chức năng vận hành theo policy hiện tại; đội phát triển kiểm tra console và dữ liệu collector đã chuẩn hóa.

Mục tiêu giai đoạn này không phải **0 báo cáo** bằng mọi giá. Mục tiêu là hiểu **báo cáo nào đến từ hành vi hợp lệ, có thể sửa, hoặc đáng điều tra**.

Ví dụ báo cáo tổng hợp sau khi scrub:

~~~text
policy_revision = csp-v4
route_group     = /checkout
directive       = script-src-elem
source_category = approved-payment-provider
browser_family  = chromium
disposition     = report
count           = 231
~~~

Không cần lưu nguyên document URI, blocked URL kèm token hoặc raw request body để phân loại được vấn đề. Các metric labels phải có cardinality thấp.

**Giới hạn Report-Only:** Không phải mọi CSP directive được browser báo cáo giống hệt khi Enforce; một số cơ chế như chống nhúng frame có giới hạn quan sát trong report-only. Kiểm chứng **Enforce trên staging/canary** là bắt buộc, nhất là đối với frame-ancestors, sandbox và các điều kiện navigation đặc biệt.

### 5.3. Giai đoạn 2 — Phân loại và sửa nguyên nhân, không tự nới CSP

Dùng checklist cho mỗi cụm violation:

1. Route và browser nào phát ra?
2. Có tái lập ở môi trường staging với phiên bản frontend tương ứng không?
3. Source có phải dependency đã duyệt, nội dung ứng dụng, extension hay script lạ?
4. Có thể **self-host, bỏ dependency hoặc thay inline script bằng external module** không?
5. Nếu phải cấp quyền: origin nào, directive nào, route nào và ai phê duyệt?
6. Có tác động tới CORS/cookie/CSRF/auth khi thay đổi nguồn script hoặc connect-src không?
7. Sửa xong có regression test không; report rate có giảm mà không nới policy ngoài ý muốn không?

Với các dependency dùng eval, giải pháp thường là đổi production build configuration hoặc nâng/thay thư viện. **Không thêm unsafe-eval chỉ để im báo cáo** khi chưa đánh giá tác động.

### 5.4. Giai đoạn 3 — Test đầy đủ trong môi trường giống production

Khi số vi phạm chức năng hợp lệ đã được xử lý:

- Bật **Enforce trên staging** có TLS, hostname, CDN, cookies và CSP giống production.
- Chạy browser E2E trên desktop/mobile browsers hỗ trợ chính; test login, OAuth popup, payment iframe, error pages.
- Thử một **tình huống script không được phép** bằng fixture vô hại: Enforce phải chặn theo directive mong muốn.
- Test script được phép vẫn chạy, nguồn bên thứ ba cần thiết không bị chặn.
- Kiểm tra UI, chức năng, accessibility, client-side routing, dynamic chunks, service workers và monitoring.
- So CSP trên HTTPS public edge, không chỉ unit test của Spring app.

**Không khẳng định policy hoạt động chỉ vì GET HTML trả 200.** Browser có thể tải HTML 200 nhưng các script cần cho UI đều bị chặn.

### 5.5. Giai đoạn 4 — Canary Enforce ở production

Áp Enforce cho **một tập document/host/route hoặc cohort có thể định tuyến ổn định**, tránh randomly thay policy giữa các lần load của cùng một session nếu điều đó khiến đo lường nhiễu.

Ví dụ:

~~~text
0% Enforce  -> Report-Only toàn bộ document đang trong scope
5% Enforce  -> canary cohort ổn định, so với control
25% Enforce -> nếu error/violation gates đạt
50% Enforce -> tiếp tục kiểm thử workflow trọng yếu
100% Enforce -> sau approval và stability window
~~~

Các tỷ lệ chỉ là **minh họa**, không phải công thức bắt buộc. Có thể dùng canary theo hostname, region hoặc route dễ kiểm soát hơn theo user cohort, tùy hạ tầng.

Trong giai đoạn chuyển tiếp có thể phát:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /__csp/report
~~~

Header **Enforce hiện có** vẫn đang chặn theo baseline; **Report-Only ứng viên** đo ảnh hưởng của script-src chặt hơn. Khi canary bật Enforce candidate, hãy thay phần policy chủ động và giữ reporting phù hợp để biết những gì đã bị chặn.

### 5.6. Giai đoạn 5 — 100% Enforce và duy trì

Khi rollout hoàn tất:

- **Enforce policy là trạng thái chuẩn** được ghi trong Git/manifest.
- Có thể giữ **Report-Only với policy kế tiếp chặt hơn**, nhưng tránh để bản cũ không ai xem kéo dài vô thời hạn.
- Giám sát reports, browser UX/SLO, policy drift và thay đổi mới của third-party assets.
- Mỗi frontend release thay nguồn script/style phải có CSP compatibility test.
- Gỡ exceptions tạm thời theo deadline/owner, không biến chúng thành wildcard vĩnh viễn.
- Với một incident, rollback **policy + frontend artifact + CDN config** phù hợp; rollback header không lập tức xóa browser caches hoặc state của user.

## 6. Xử lý inline script, style và eval trước khi bật chặn thật

Các ứng dụng legacy thường có inline scripts, inline event handlers, style attributes và runtime bundler cần eval. Đây là lý do chính khiến chuyển Enforce thất bại dù trang chạy ổn dưới Report-Only.

### 6.1. Anti-pattern: mở quyền cho mọi inline script

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; object-src *
~~~

Chính sách này có thể duy trì chức năng nhưng **làm suy yếu đáng kể mục tiêu giảm XSS** và cần được xem là ngoại lệ rủi ro cao, không phải kết quả cuối của migration.

Ưu tiên:

1. **Di chuyển inline JavaScript sang file tĩnh** cùng origin, được quản lý qua build pipeline.
2. Với SSR cần inline script, dùng **nonce sinh ngẫu nhiên cho từng response HTML**, truyền đúng nonce vào CSP header và script element.
3. Với đoạn inline bất biến có nội dung xác định, có thể dùng **hash nguồn script** được tính trong build/release.
4. Thay **onclick/onload inline handlers** bằng addEventListener trong script được cho phép; nonce trên script tag không tự cấp quyền cho tất cả inline event attributes.
5. Với styles, ưu tiên external stylesheet/class, hoặc chọn hash/nonce đúng mục đích và browser support.
6. Loại bỏ **eval/new Function**, xem xét devtool production bundle; không copy dev build settings vào production.

### 6.2. Nonce trên document HTML

Một response HTML có thể dùng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'nonce-BASE64_RANDOM_PER_RESPONSE' 'strict-dynamic'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
Cache-Control: no-store
~~~

~~~html
<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8">
    <script nonce="BASE64_RANDOM_PER_RESPONSE">
      window.initialFlags = { featureA: true };
    </script>
  </head>
  <body>
    <div id="app"></div>
  </body>
</html>
~~~

**BASE64_RANDOM_PER_RESPONSE chỉ là placeholder.** Trong triển khai thật, nonce phải được tạo bằng CSPRNG, không đoán được, **mới cho mỗi response HTML** và khớp chính xác giữa CSP header với thuộc tính nonce của phần tử được phép.

**Không dùng** nonce cố định trong application.yaml, build artifact, CDN template được shared-cache, cookie hoặc URL. Nếu HTML chứa nonce theo response, phải có cache policy phù hợp, tránh dùng một response HTML đã sinh nonce cho nhiều người dùng hoặc tái sử dụng nonce dài hạn.

Bản thân một nonce không làm an toàn những biến dữ liệu chưa được escape được nhúng vào script. **Output encoding/JSON serialization thích hợp vẫn phải làm** để tránh biến dữ liệu người dùng thành JavaScript.

### 6.3. Sinh nonce an toàn bằng Java

Đây là **helper** dùng cho tầng render document, không phải một SecurityFilterChain hoàn chỉnh:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonceFactory {

    private final SecureRandom random = new SecureRandom();

    public String newNonce() {
        byte[] bytes = new byte[16]; // 128 bit ngẫu nhiên
        random.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
~~~

Quy trình tích hợp Servlet/Reactive SSR:

1. Tạo nonce **một lần cho mỗi HTML response**.
2. Đặt nonce vào request/exchange render context trước khi template được thực thi.
3. Render nonce lên từng script element thật sự được cho phép.
4. Gắn chính nonce đó vào **Content-Security-Policy HTTP response header**.
5. Không để một static CSP writer thứ hai ghi đè header động hoặc chèn thêm policy gây xung đột.
6. Không log nonce như credential, không đưa vào URL, query hoặc metrics labels; không cache chung HTML động.
7. Thêm regression test bảo đảm header nonce khớp HTML nonce nhưng khác ở các response độc lập.

Với **SPA tĩnh được CDN serve**, cách đơn giản hơn thường là external JS bundles với host allowlist hoặc build-time hash, thay vì tự tạo nonce cố định trong file HTML tĩnh.

### 6.4. Hash cho đoạn inline bất biến

Nếu đoạn inline JS không đổi theo user/session, dùng digest của **chính xác bytes nội dung** (bao gồm whitespace/newlines theo quy tắc CSP). Ví dụ dạng policy:

~~~http
Content-Security-Policy: script-src 'self' 'sha256-<base64-digest>'; object-src 'none'; base-uri 'self'
~~~

Chuỗi **base64-digest là placeholder**, cần tính bằng tooling của build pipeline từ nội dung script thật và đưa vào policy cùng release artifact. Đổi một khoảng trắng hoặc nội dung script có thể làm hash không còn khớp.

Hash **không phù hợp với script inline chứa dữ liệu người dùng thay đổi mỗi response** nếu bạn chỉ hardcode một digest cũ. Với nội dung động, ưu tiên externalization hoặc nonce theo response.

### 6.5. strict-dynamic và trust propagation

Trong các browser hỗ trợ CSP Level 3, script-src với nonce/hash và **strict-dynamic** có thể cho phép script được tin cậy tải thêm các script theo cơ chế truyền tin cậy phù hợp.

Điểm quan trọng:

- Host/scheme allowlist có thể có hành vi khác khi kết hợp strict-dynamic trong browser hỗ trợ; không giả định mọi origin list đều còn hiệu lực như cũ.
- Một script được cấp nonce nhưng có hành vi tải mã từ URL không tin cậy vẫn là rủi ro. **Chỉ cấp nonce cho mã mà bạn review và tin cậy**.
- Browser cũ có mức hỗ trợ khác, nên phải test và thiết kế fallback có chủ đích.
- strict-dynamic không thay **SRI (Subresource Integrity)** khi dùng tài nguyên bên ngoài thích hợp; và SRI cũng không thay CSP.
- Không dùng strict-dynamic như đường tắt để tránh kiểm kê third-party scripts.

### 6.6. Styles, event handlers, WebAssembly và Trusted Types

Các tình huống cần xem riêng:

| Tình huống | Rủi ro khi bật Enforce | Hướng xử lý |
| --- | --- | --- |
| Inline style attributes | style-src chặn việc chèn style một số cách | Chuyển sang class/stylesheet; nghiên cứu style-src-attr nếu thật cần |
| Inline event handlers | onclick/onload có thể bị chặn | Refactor addEventListener thay vì mở unsafe-inline |
| CSS-in-JS runtime | Framework tự tạo style tags động | Dùng nonce/style policy theo khả năng framework hoặc build CSS tĩnh |
| Eval/new Function | script-src không cho unsafe-eval | Sửa dependency/build mode, đánh giá ngoại lệ ngắn hạn |
| WebAssembly compilation | Một số browser áp restriction liên quan wasm-unsafe-eval | Kiểm thử worker/Wasm, dùng policy có chủ đích |
| Trusted Types | Browser hỗ trợ khác nhau, app có DOM sink legacy | Thử report-only/compat, refactor DOM sinks trước enforce |
| blob/data URLs | Dùng cho workers/images/previews | Chỉ cho phép đúng directive/nơi thật cần, không mở script-src data: |
| WebSocket | connect-src có thể cần wss:// endpoint | Test realtime, không chỉ fetch/XHR |

Đối với Trusted Types, các directive như **require-trusted-types-for 'script'** là lớp bổ sung có mức browser support riêng, không coi nó là chức năng phổ quát của mọi phiên bản CSP. Chọn adoption path riêng và test đầy đủ.

## 7. Nguồn bên thứ ba, login/SSO, thanh toán và CSP liên quan

### 7.1. Phân loại dependency theo chức năng

- **Payment provider:** Có thể cần script-src, frame-src, connect-src, form-action tương ứng. Một số provider đổi host theo vùng/quốc gia; cần tài liệu chính thức và kiểm thử thật bằng sandbox.
- **OIDC/OAuth login:** Browser có thể mở popup, redirect, form submit hoặc silent login iframe. CSP và COOP/COEP có thể làm luồng cũ bị ảnh hưởng; không chỉ test API token endpoint.
- **Analytics/telemetry:** Có thể cần connect-src hoặc img-src. Cân nhắc privacy/security, tránh allowlist tùy tiện mọi host.
- **Captcha/anti-bot:** Có thể cần script/frame/connect nhiều origin; phải review vendor và kiểm thử fallback.
- **CDN fonts/images:** Nguồn nào có thể self-host nên cân nhắc để giảm policy complexity.
- **Dynamic import/module chunks:** Deployment mới đổi chunk origin hoặc asset path; test lazy routes, không chỉ trang đầu.
- **PWA/service workers:** worker-src, update lifecycle và offline HTML cache có thể khiến CSP khác phiên bản.

### 7.2. CSP không thay kiểm soát tin cậy script bên thứ ba

Cho phép một script ngoài origin hoạt động nghĩa là script đó có thể tương tác với DOM theo quyền của trang. Một allowlist rộng cho một nhà cung cấp không bảo đảm toàn bộ mã nhà cung cấp không bị thay đổi.

Cần đánh giá dependency integrity, origin ownership, version pinning, SRI nếu phù hợp, và kế hoạch rút quyền khi không cần. Không lấy report từ domain lạ làm lý do cấp quyền mà không có owner.

### 7.3. Một CSP cho mọi HTML route có thể quá cứng hoặc quá rộng

Nếu trang checkout cần payment iframe còn các trang khác không cần, có thể cân nhắc **policy theo nhóm route/document**:

~~~text
/               -> script-src cho SPA; frame-ancestors 'none'
/checkout       -> thêm frame-src payment provider đã duyệt
/admin          -> script-src chặt hơn; form-action 'self'
/legacy/reports -> giai đoạn Report-Only với sunset deadline
~~~

Tuy nhiên, policy routing phức tạp tăng khả năng **nhầm matcher/CDN cache hoặc bypass**. Mỗi nhóm phải có automated test, owner và đúng URL sau reverse proxy rewrite.

**Không dùng User-Agent, tên client hoặc một query parameter người dùng tự chọn để hạ CSP xuống mức yếu hơn**. Rollout cohorts phải dựa trên cơ chế định tuyến đáng tin và được quan sát.

## 8. Servlet: chọn CSP Report-Only hoặc Enforce bằng policy có version

Các ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x và Java 17+** trên Servlet. Với Boot 3, các Servlet APIs thuộc namespace **jakarta.servlet**.

### 8.1. Cấu hình có validation fail-fast

Không nên có flag chung **security.enabled=false** hoặc fallback CSP rỗng. Định nghĩa chế độ tường minh trong Spring Boot external configuration:

~~~yaml
app:
  security:
    csp:
      mode: report-only
      directives: >-
        default-src 'self';
        script-src 'self';
        object-src 'none';
        base-uri 'self';
        frame-ancestors 'none';
        connect-src 'self' https://api.example.com;
        report-uri /__csp/report
~~~

Khi được duyệt để canary Enforce, thay mode **enforce** trong config revision qua pipeline. Không cho production tự lùi về report-only khi thiếu config.

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security.csp")
public record CspPolicyProperties(String mode, String directives) {

    public CspPolicyProperties {
        if (!"report-only".equals(mode) && !"enforce".equals(mode)) {
            throw new IllegalArgumentException(
                "CSP mode must be report-only or enforce");
        }
        if (directives == null || directives.isBlank()) {
            throw new IllegalArgumentException(
                "CSP directives must not be empty");
        }
    }

    boolean isReportOnly() {
        return "report-only".equals(mode);
    }
}
~~~

Validation trên chỉ là guardrail cơ bản: production cần thêm policy linter để phát hiện wildcard, unsafe-inline/eval không được phê duyệt, directives trùng, cú pháp sai, các nguồn/host bị cấm và policy thiếu baseline.

### 8.2. SecurityFilterChain Servlet phát đúng loại header

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableConfigurationProperties(CspPolicyProperties.class)
class ServletCspConfiguration {

    @Bean
    SecurityFilterChain browserChain(
            HttpSecurity http,
            CspPolicyProperties policy) throws Exception {

        return http
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                (HttpServletRequest request) ->
                    "POST".equalsIgnoreCase(request.getMethod())
                        && "/__csp/report".equals(
                            request.getServletPath())))
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> {
                    csp.policyDirectives(policy.directives());
                    if (policy.isReportOnly()) {
                        csp.reportOnly();
                    }
                }))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .requestMatchers(
                    HttpMethod.POST, "/__csp/report").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích vận hành:**

- Với mode **report-only**, Spring Security phát **Content-Security-Policy-Report-Only**. Với mode **enforce**, nó phát **Content-Security-Policy** để browser thực thi.
- **CsrfFilter vẫn bảo vệ browser API dùng cookie**. Chỉ POST collector tại **đúng servletPath** được bỏ kiểm tra CSRF vì CSP report POST không chứa CSRF header của ứng dụng.
- **Không biến endpoint report thành API nghiệp vụ**: nó chỉ nhận telemetry đã sanitize, không đọc/sửa session, không đổi dữ liệu người dùng.
- **permitAll không nghĩa là cho spam vô hạn**: collector cần body limit, rate limit, schema validation và log redaction.
- Nếu có servlet context path, gateway rewrite hoặc custom servlet mapping, **servletPath có thể không như URL public**. Kiểm thử matcher thực thay vì copy y nguyên.
- Ví dụ chỉ nêu một số route. Ứng dụng thật phải khai báo login, logout, callback, health và assets theo policy; không đổi anyRequest().denyAll() thành permitAll cho tiện.
- Cấu hình CSP chỉ có ích cho **document được Servlet chain này thực sự phục vụ**. Nếu HTML SPA do CDN riêng trả, đặt CSP trên CDN HTML origin.
- Nhiều SecurityFilterChain cần test thứ tự matchers. Header Spring không tự xuất hiện trên error page do gateway tạo.

Đây là mẫu cho Spring Security 6.x, không phải cam kết mọi minor version có cùng DSL; build và kiểm thử trên BOM của dự án.

### 8.3. Song song Enforce baseline với Report-Only candidate

Nếu hệ thống đã có CSP Enforce hiện tại, không cần tắt nó để thử một candidate chặt hơn:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /__csp/report
~~~

Trên Servlet, có thể giữ một CSP writer Enforce và thêm một header writer cho candidate:

~~~java
import org.springframework.security.web.header.writers.StaticHeadersWriter;

// Đoạn cấu hình thay thế trong builder HttpSecurity.
.headers(headers -> {
    headers.contentSecurityPolicy(csp -> csp.policyDirectives(
        "default-src 'self'; object-src 'none'; base-uri 'self'"));
    headers.addHeaderWriter(new StaticHeadersWriter(
        "Content-Security-Policy-Report-Only",
        "default-src 'self'; script-src 'self'; " +
        "object-src 'none'; base-uri 'self'; " +
        "report-uri /__csp/report"));
})
~~~

**Đây là biến thể riêng**, không chèn đồng thời vào cấu hình một-mode của phần 8.2 mà không kiểm soát kết quả. Khi candidate được phê duyệt, promote nó thành Enforce; nếu cần, bổ sung Report-Only cho candidate tiếp theo.

**Không nhầm hai Enforce headers với một Enforce + một Report-Only**: nhiều Enforce policies cùng có hiệu lực. Nếu gateway/CDN phát CSP riêng, policy của Spring và policy edge có thể cùng được browser áp dụng; cần thống nhất owner và kiểm thử actual response.

### 8.4. CSP không thay CSRF, CORS và session

Một script-src chặt không thay CsrfFilter cho browser cookie-authenticated POST. Một form cross-site vẫn có thể kích hoạt request browser gửi cookie trong những bối cảnh cho phép. CSP cũng không thay secure output escaping và DOM sanitization.

Nếu SPA gọi JSON API khác origin, **connect-src** của trang phải cho kết nối đó, còn API vẫn cần **CORS exact origin allowlist**, authentication, authorization và CSRF tương ứng. Cho phép một origin trong connect-src không làm browser vượt CORS; CORS không cho phép script trái script-src thực thi.

Session cookie vẫn cần Secure, HttpOnly và SameSite đúng deployment. CSP không làm JavaScript đọc được HttpOnly cookie.

## 9. WebFlux/Reactive: CSP policy giống nhau, DSL khác nhau

Reactive app dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **ServerWebExchange**, **WebSession** và **CsrfWebFilter**. Không copy HttpSecurity/HttpServletRequest hoặc StrictHttpFirewall từ Servlet.

### 9.1. SecurityWebFilterChain theo mode

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableConfigurationProperties(CspPolicyProperties.class)
class ReactiveCspConfiguration {

    @Bean
    SecurityWebFilterChain browserReactiveChain(
            ServerHttpSecurity http,
            CspPolicyProperties policy) {

        return http
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> {
                    csp.policyDirectives(policy.directives());
                    if (policy.isReportOnly()) {
                        csp.reportOnly();
                    }
                }))
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/assets/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Trong ví dụ này, **collector report nằm ở dịch vụ ngoài app browser** và không cần ngoại lệ CSRF ở chain Reactive. Nếu collector nằm ngay trong WebFlux app, phải:

1. Chỉ miễn CSRF cho **đúng POST report endpoint** bằng ServerWebExchangeMatcher hẹp và negative tests.
2. Không tắt CSRF trên toàn /api/** để reports được gửi.
3. Giới hạn body/rate và không đọc user session như một business action.
4. Kiểm thử chính xác request path sau proxy rewrite và WebFilter chain.
5. Xác minh GET/POST khác vẫn giữ CSRF theo policy.

ServerHttpSecurity có APIs/behavior phiên bản riêng. Dùng build và WebTestClient trên BOM đã duyệt; không suy ra từ việc Servlet build pass.

### 9.2. Dual headers trên Reactive hoặc CDN

Nếu cần Enforce baseline và Report-Only candidate cùng lúc, dùng **hai header writers có owner rõ ràng** trong Reactive chain hoặc trên HTML CDN/gateway. Không để custom WebFilter và ServerHttpSecurity cùng phát headers không được quản lý. Header cuối có thể chứa nhiều policies Enforce cùng có hiệu lực, làm hỏng tài nguyên.

Trong staging/canary cần xác minh:

- Có **Content-Security-Policy** baseline Enforce nếu chính sách cũ yêu cầu.
- Có **Content-Security-Policy-Report-Only** candidate, không đổi nhầm tên header.
- WebTestClient thấy headers app phát; browser HTTPS public thấy headers cuối qua proxy/CDN.
- Khi candidate được promote, không mất object-src/base-uri/frame-ancestors vốn có.
- Error pages/redirects do gateway tạo được kiểm tra riêng.
- Không để policy version cho canary tự thay đổi giữa các requests của cùng user ngoài kế hoạch.

### 9.3. So sánh Servlet và Reactive

| Nhiệm vụ | Servlet | WebFlux |
| --- | --- | --- |
| Security DSL | HttpSecurity | ServerHttpSecurity |
| Filter chain | SecurityFilterChain | SecurityWebFilterChain |
| CSRF | CsrfFilter | CsrfWebFilter |
| CSP | HttpSecurity headers contentSecurityPolicy | ServerHttpSecurity headers contentSecurityPolicy |
| Request | HttpServletRequest | ServerWebExchange |
| Session | HttpSession | WebSession |
| URL/path protection | StrictHttpFirewall và MVC matchers | Reactive parser/WebFilter/gateway |
| HTTP test | MockMvc | WebTestClient |
| CSP report collector | Servlet controller/external service | Reactive handler/external service |

Cùng một CSP directive có thể được phát qua hai stack khác nhau, nhưng **phải test actual header và browser enforcement riêng**.

## 10. CSP reporting collector: giữ nguyên ranh giới bảo mật

### 10.1. Báo cáo browser POST không phải business POST

Một CSP report có thể được browser gửi ở định dạng khác API JSON thường dùng và **không được giả định có cookie phiên hoặc CSRF token của ứng dụng**. Collector nên chỉ nhận telemetry, không làm business mutation.

Ví dụ endpoint Servlet minh họa:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CspReportController {

    @PostMapping(
        path = "/__csp/report",
        consumes = {
            "application/csp-report",
            "application/reports+json"
        }
    )
    ResponseEntity<Void> receiveReport(
            @RequestBody(required = false) String rawBody) {

        // DEMO: Cố tình không ghi rawBody vào log/storage.
        // Collector thật phải parse, scrub, aggregate trước lưu.
        // Giới hạn request size ở ingress/server TRƯỚC
        // khi body được bind vào String.
        return ResponseEntity.status(HttpStatus.NO_CONTENT).build();
    }
}
~~~

**Ví dụ trả 204 và bỏ dữ liệu**, không phải collector hoàn chỉnh. Nếu chỉ kiểm tra body length trong controller thì body đã được bind vào memory: có thể quá muộn để chống request lớn. Đặt body size limit ở ingress/web server và áp rate limiting trước parser.

### 10.2. Pipeline xử lý một CSP report

~~~mermaid
flowchart LR
    A["Browser gửi CSP violation"] --> B["Collector không dùng session auth"]
    B --> C["Size/rate/content-type validation"]
    C --> D["Parse + scrub URL/query/body"]
    D --> E["Classify directive/source/route"]
    E --> F["Aggregate low-cardinality metrics"]
    F --> G["Dashboard/SLO và security review"]
~~~

Metadata được phép sau scrub:

~~~text
policy_revision=csp-v5
route_group=/checkout
effective_directive=script-src-elem
source_category=reviewed-payment-provider
browser_family=chromium
disposition=report
count=42
~~~

Không lưu nguyên:

~~~text
document-uri=https://app.example.com/profile?access_token=...
blocked-uri=https://cdn.example.com/js?email=...
script-sample=window.userSecret = ...
Cookie: JSESSIONID=...
Authorization: Bearer ...
~~~

**CSP reports là input từ internet**, không tin là dữ liệu do browser hợp lệ tạo. Có thể bị spam, log injection, high-cardinality denial of service hoặc chứa thông tin cá nhân. Không dùng raw report fields làm metric labels, và không đẩy JSON thô sang APM/sentry.

### 10.3. Các yêu cầu vận hành cho collector

- **Rate limit, max request bytes, schema/type validation, retention** và quyền truy cập hạn chế.
- Parser chấp nhận những content type/shape thật sự hỗ trợ, không phản hồi 500/stack trace vì một report xấu.
- Scrub query/fragment của URLs trước lưu; sử dụng hostname/route group đã cho phép.
- Không log header Cookie/Authorization, không echo raw payload vào error body.
- Không tạo session mới để ghi telemetry; không dùng login cookie làm quyền cho report.
- Exemption CSRF (nếu cần) **chỉ cho POST report**, không cho route prefix rộng.
- Khi nhận reports tại service bên thứ ba, đánh giá dữ liệu chuyển tới provider và chính sách bảo mật.
- Có synthetic canary report ở staging để xác minh pipeline hoạt động; số reports bằng 0 không tự chứng minh policy đúng.

## 11. HTML CDN, reverse proxy và chính sách phát header

### 11.1. SPA HTML thuộc origin nào?

~~~mermaid
flowchart TD
    A["Browser nhận index.html"] --> B["CSP của HTML origin"]
    B --> C["Browser tải script/style/iframe theo CSP"]
    C --> D["SPA fetch API theo connect-src"]
    D --> E["CORS/CSRF/auth ở API backend"]
    F["Spring Security API"] --> E
~~~

Nếu SPA HTML là static index.html cache lâu ở CDN, nonce được hardcode trong file **không đủ yêu cầu nonce mới theo response**. Ưu tiên external JS bundles, build-time hash cho inline bất biến hoặc thiết kế HTML dynamic generation thật với nonce CSPRNG và cache policy phù hợp.

### 11.2. Tránh CSP headers nhân đôi ngoài ý muốn

Kiểm tra từng tầng:

- Spring có phát Enforce/Report-Only không; route HTML có thuộc chain đó không?
- Gateway/CDN có ghi đè, append hoặc strip header không?
- CDN cache HTML/CSP theo policy revision cũ sau khi frontend deploy asset mới không?
- Các regions/pods có cùng CSP revision không?
- HTML error page do ingress tạo có chính sách khác document chính không?
- Có hai Enforce policies được browser áp đồng thời không?
- Report-Only candidate có đến được browser thật, hay bị mất sau TLS termination không?

**Không lấy một test ở app direct thay cho HTTPS public edge**. Nếu frontend HTML ở CDN khác host API, đo CDN frontend riêng.

### 11.3. HSTS, cookies và proxy vẫn cần bảo vệ độc lập

CSP không thay HSTS/TLS; khi proxy terminate HTTPS cần xác minh:

1. HSTS public HTTPS có max-age đúng và includeSubDomains theo policy domain.
2. CSP trên HTML document cuối không bị gateway sửa sai.
3. Proxy sanitize X-Forwarded-Host/Proto từ client không đáng tin trước khi backend dùng.
4. Redirect Location đúng HTTPS host, không phát URL có session/JWT/CSRF token.
5. Session cookie có Secure, HttpOnly, SameSite/Domain/Path phù hợp.
6. API vẫn dùng CSRF/CORS/authorization theo authentication mechanism.
7. CSP reporter không tự lưu token/cookie trong logs/telemetry.

## 12. MockMvc: xác minh header, mode và CSRF không bị suy yếu

Các test sau giả định Spring Boot 3 / Spring Security 6 Servlet app có CspPolicyProperties, HTML GET /, POST /__csp/report và POST /api/orders. Với HTML được CDN phục vụ riêng, cần thêm HTTP/browser tests trên HTML origin thực.

### 12.1. Kiểm tra chế độ Report-Only

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "app.security.csp.mode=report-only",
    "app.security.csp.directives=" +
        "default-src 'self'; script-src 'self'; " +
        "object-src 'none'; report-uri /__csp/report"
})
class CspReportOnlyServletTests {

    @Autowired MockMvc mvc;

    @Test
    void candidateIsReportOnly() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy-Report-Only",
                containsString("script-src 'self'")))
            .andExpect(header().doesNotExist(
                "Content-Security-Policy"));
    }
}
~~~

Kỳ vọng Enforce header vắng mặt chỉ đúng với **single-mode design** ở phần 8.2. Nếu hệ thống đã có **Enforce baseline và Report-Only candidate**, test phải khẳng định cả hai headers đúng contract.

MockMvc chỉ kiểm tra header ứng dụng tạo ra; **không chạy browser CSP** và không kiểm chứng CDN/gateway có giữ header.

### 12.2. Kiểm tra chế độ Enforce

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "app.security.csp.mode=enforce",
    "app.security.csp.directives=" +
        "default-src 'self'; script-src 'self'; " +
        "object-src 'none'; frame-ancestors 'none'"
})
class CspEnforceServletTests {

    @Autowired MockMvc mvc;

    @Test
    void enforcedPolicyHasRequiredDirectives() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("script-src 'self'")))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("object-src 'none'")))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("frame-ancestors 'none'")))
            .andExpect(header().doesNotExist(
                "Content-Security-Policy-Report-Only"));
    }
}
~~~

Kỳ vọng không có Report-Only cũng chỉ áp dụng cho **single-mode**. Với dual-policy, test riêng baseline và candidate; tránh một CD pipeline vô tình đổi tên cả hai thành Enforce.

**Bài test tồn tại header không đủ**: cần policy linter phát hiện script-src wildcard, unsafe-inline/unsafe-eval không được phê duyệt hoặc mất directives quan trọng.

### 12.3. CSP reporting POST là ngoại lệ hẹp, không bỏ CSRF nghiệp vụ

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

// Đoạn thân test trong class có field MockMvc mvc.
@Test
void cspReportIsAcceptedWithoutCsrfHeader() throws Exception {
    mvc.perform(post("/__csp/report")
            .contentType("application/csp-report")
            .content("{\"csp-report\":{\"violated-directive\":\"script-src\"}}"))
        .andExpect(status().isNoContent());
}

@Test
void businessPostStillRequiresCsrf() throws Exception {
    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"sku\":\"P100\",\"quantity\":1}"))
        .andExpect(status().isForbidden());
}
~~~

Test 204 không chứng minh collector đã parse/redact/rate-limit payload. Bổ sung test với body quá lớn, malformed JSON, flood requests và không có session side effect trong collector.

Đối với POST nghiệp vụ bị 403, phải kiểm tra **dữ liệu không đổi**. CSRf được giữ độc lập với CSP Enforce.

### 12.4. Fail-fast khi mode không hợp lệ

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

@Test
void unsupportedCspModeMustFailValidation() {
    assertThrows(IllegalArgumentException.class, () ->
        new CspPolicyProperties("disabled", "default-src *"));
}
~~~

Khi deploy production, cần test **resolved config** để không có fallback sang Report-Only do thiếu biến môi trường hoặc bị cấu hình override không qua review.

## 13. WebTestClient: kiểm thử CSP và CsrfWebFilter trong WebFlux

### 13.1. Report-Only mode

~~~java
// Đoạn thân WebTestClient test với config mode=report-only.
webTestClient.get().uri("/")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        "Content-Security-Policy-Report-Only",
        ".*script-src 'self'.*");
~~~

Nếu baseline Enforce vẫn hoạt động, test cả header Enforce và Report-Only. Không suy ra từ GET 200 rằng browser không bị chặn bởi một policy Enforce khác.

### 13.2. Enforce mode

~~~java
// Chạy trong test context riêng với mode=enforce.
webTestClient.get().uri("/")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        "Content-Security-Policy",
        ".*script-src 'self'.*")
    .expectHeader().valueMatches(
        "Content-Security-Policy",
        ".*object-src 'none'.*");
~~~

Một ApplicationContext đã bind mode trước đó không tự cập nhật khi chỉ đổi một biến trong code test. Dùng test profiles/context riêng hoặc DynamicPropertySource theo lifecycle đúng của Spring Test.

### 13.3. CSP không thay CSRF cho request WebSession

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn test, cần java.util.Map và POST /api/orders thật.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

mockUser/csrf là helpers; chúng **không kiểm tra login thật, cookie/WebSession và raw/XOR token hợp đồng JSON**. Cần integration test qua GET CSRF token cùng session rồi POST thiếu/sai/đúng token.

Nếu WebTestClient pass nhưng browser fail, kiểm tra **HTML origin CDN, proxy CSP override, route securityMatcher và error pages** trước khi nới policy.

## 14. Browser E2E: chứng minh CSP thực sự chặn script không được phép

### 14.1. Fixture vô hại trong staging

Một trang staging chỉ dùng để kiểm tra enforcement, không chứa dữ liệu user:

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>CSP fixture</title></head>
<body>
  <div id="csp-fixture">blocked</div>
  <script>
    document.getElementById("csp-fixture").textContent = "executed";
  </script>
</body>
</html>
~~~

Nếu candidate script-src 'self' không cho inline script và script này không có nonce/hash:

- **Report-Only đơn độc:** Inline script chạy, text trở thành executed; có thể có CSP report.
- **Enforce:** Inline script bị chặn, text vẫn blocked.
- **Dual-policy:** Nếu Enforce baseline hiện tại cũng chặn inline, fixture bị chặn ngay trong giai đoạn Report-Only của candidate. Điều chỉnh fixture theo **baseline thực tế**, không kết luận candidate đã Enforce vì một policy khác đang chặn.

Test này chỉ dùng ở staging/canary được phép, không khuyến khích nhúng inline script không nonce vào trang production thật.

### 14.2. Playwright test cho fixture

~~~javascript
import { test, expect } from "@playwright/test";

test("CSP fixture obeys active policy", async ({ page }) => {
  await page.goto("https://staging.example.com/csp-fixture");

  const expectEnforce = process.env.CSP_EXPECT_ENFORCE === "true";
  const expected = expectEnforce ? "blocked" : "executed";

  await expect(page.locator("#csp-fixture")).toHaveText(expected);
});
~~~

CI đặt CSP_EXPECT_ENFORCE theo **stage có phê duyệt**, không từ query parameter hoặc header do client tự chọn trên production.

### 14.3. Bộ user-flow thực cần kiểm tra

| User flow | CSP có thể làm hỏng | Tín hiệu PASS |
| --- | --- | --- |
| SPA shell | Inline runtime, chunk JS, critical CSS | App mount và routing thành công |
| Login/MFA | Captcha, popup, form-action, iframe | Login hoàn tất, CSRF/session đúng |
| API fetch | connect-src thiếu API origin | API trả đúng, CORS/CSRF không lỗi |
| Checkout | Payment script, frame, redirect | Sandbox checkout thành công |
| Profile/avatar | blob image preview, worker | Preview/upload hoạt động |
| Admin console | Chart libs, CSS-in-JS, realtime | Dashboard và permissions đúng |
| Lazy routes | Dynamic import khác CDN path | Mở mọi route trọng yếu được |
| Error pages | HTML 403/404/500 dùng JS/CSS riêng | Không trắng trang và không lộ stack |
| WebView/mobile browsers | Browser support khác desktop | Luồng quan trọng hoạt động |
| Offline/PWA | Cached HTML, service workers | Không trộn policy/nonce giữa versions |

**GET HTML 200 không chứng minh CSP rollout thành công.** Browser có thể nhận HTML nhưng chặn toàn bộ mã tạo giao diện.

### 14.4. Report count bằng 0 không phải bằng chứng an toàn

Browser có thể không hỗ trợ report-to/report-uri, privacy settings có thể chặn reports, collector có thể outage, sampling/quotas làm mất sự kiện, script chặn telemetry hoặc Report-Only không phản ánh đủ hành vi Enforce. Phải kết hợp:

1. **Synthetic violation canary ở staging** để kiểm chứng pipeline.
2. **Fixture browser execution** cho Enforce.
3. **User-flow E2E** trên browsers thực.
4. **Policy header contract** trên HTTPS edge.
5. **Product outcomes** như login/checkout completion và JS error rate.

## 15. Deployment gates, CSP metrics và quyết định go/no-go

### 15.1. Những tín hiệu cần giám sát

| Tín hiệu | Cách đo | Cảnh báo |
| --- | --- | --- |
| CSP reports | Count/rate theo directive, source class, route group và disposition | Vi phạm hợp lệ mới xuất hiện sau release |
| Frontend errors | Unhandled errors, blank screen, chunk load failures | Có thể do CSP chặn JS hoặc CDN mismatch |
| Product flows | Login, MFA, checkout, submit và navigation completion | Tỷ lệ thành công giảm so với baseline/control |
| Header contract | Enforce/Report-Only policy revision trên HTML HTTPS edge | Mất CSP, sai mode hoặc bị ghi đè |
| Browser block test | Synthetic inline script fixture trên staging | Không được phép chạy dưới Enforce kỳ vọng |
| Session/CSRF | 403 CSRF, login loop, cookie blocked events | CSP chặn CSRF bootstrap hoặc JS login |
| CORS | OPTIONS trusted Origin và response CORS hợp lệ | Không nhầm connect-src với CORS |
| CSP collector | Report ingest success, dropped data, sampling, availability | Không kết luận an toàn chỉ vì ít report |
| Revision/drift | Artifact, HTML/CDN CSP revision theo pod/region | Một instance đang Enforce yếu hơn |
| Privacy | Synthetic canary và redaction tests | Report collector/log thu URL/token nhạy cảm |

**CSP reports là dữ liệu từ browser/Internet không đáng tin**. Một attacker có thể gửi reports giả làm số lỗi tăng. Không trực tiếp dùng raw reports để quyết định rollback mà thiếu xác minh sản phẩm và source identity.

### 15.2. Ví dụ low-cardinality metrics

Tên dưới đây chỉ là **metrics do dự án tự thiết kế**, không phải tên mặc định của Spring Security:

~~~text
csp_violation_total{
  environment="prod",
  csp_revision="csp-v5",
  route_group="checkout",
  directive="script-src-elem",
  source_class="approved-payment-provider",
  disposition="report"
}

csp_header_contract_check_total{
  environment="prod",
  csp_revision="csp-v5",
  host_group="frontend-html",
  mode="enforce",
  outcome="pass"
}

csp_collector_ingest_total{
  environment="prod",
  report_format="reporting-api",
  outcome="accepted"
}
~~~

**Không dùng** token CSRF, JWT, session ID, email, raw document URL/query, script sample, IP thô, blocked-uri bất kỳ hoặc correlation ID làm metric labels. Chọn route templates và known host categories, kiểm soát cardinality và data retention.

### 15.3. Gates trước khi bật Enforce canary

Một checklist go/no-go hợp lý:

1. **CSP linter PASS**: required directives đầy đủ, các ngoại lệ rủi ro được review, không có wildcard/unsafe-inline không được phê duyệt.
2. **Asset/source inventory được duyệt** cho từng document group và frontend release.
3. **Report-Only candidate tới đúng HTML HTTPS origin** qua CDN/ingress; policy revision khớp manifest.
4. **CSP collector hoạt động và scrub đúng**, synthetic canary violation được thu trong staging.
5. **Vi phạm từ chức năng hợp lệ đã được sửa** hoặc có exception giới hạn với owner/expiry.
6. **Browser E2E PASS** cho login/MFA/checkout/profile/admin và các routes quan trọng.
7. **Fixture Enforce PASS**: script không được phép bị chặn, script được phép vẫn chạy.
8. **CSRF/CORS/authorization không suy yếu**: POST thiếu token vẫn bị chặn, trusted preflight và cookie hoạt động.
9. **Canary routing ổn định**, metrics có thể so sánh với control cohort và đủ coverage trình duyệt.
10. **Rollback được chuẩn bị** cho frontend artifact, Spring config, HTML CDN/edge policy và user session impacts.

Không lấy một con số reports tuyệt đối làm threshold duy nhất. Định nghĩa **ngưỡng dựa trên baseline, lưu lượng, độ phủ browser và SLO**, chẳng hạn sự khác biệt login/checkout completion giữa cohort canary và control, tỷ lệ JS errors mới và blockages ở critical routes.

### 15.4. Ma trận quyết định khi canary hoạt động

| Quan sát | Quyết định gợi ý |
| --- | --- |
| Script fixture bị chặn, user flows tốt, known violations được xử lý | Tiếp tục tăng canary theo kế hoạch |
| Checkout mất payment frame/script | Dừng tăng; sửa candidate rồi retest |
| SSO/login/MFA bị chặn | Dừng hoặc rollback theo blast radius |
| Một CDN region thiếu CSP Enforce | Dừng rollout, điều tra drift |
| Reports từ browser extensions tăng nhưng clean browser E2E tốt | Phân loại noise, không nới script-src vội |
| Report count bằng 0 nhưng collector canary cũng mất | Không đủ tín hiệu để promote |
| CSRF 403 tăng vì script bootstrap không chạy | Sửa script/CSP rồi retest; không tắt CSRF |
| CSP header có mặt nhưng script trái phép vẫn chạy | Kiểm tra HTML origin, policy, multiple headers, fixture/browser |
| Có hai Enforce headers mâu thuẫn | Dừng canary và xác định header owner |
| Reports chứa URL/query/token nhạy cảm | Ngừng capture/giới hạn quyền và xử lý privacy incident |

### 15.5. Giám sát sau rollout 100%

Khi policy đã Enforce 100%, duy trì **synthetic header probes và browser UX metrics** để phát hiện regression từ những thay đổi không qua source code: CDN rules, proxy, third-party scripts, SDK analytics, CSP reporting provider hay browser updates.

Mọi exception tạm thời cần có owner, phạm vi route, thời hạn, lý do và test. Nếu vẫn dùng Report-Only cho policy chặt hơn tiếp theo, ghi rõ **mục tiêu nâng cấp** và deadline, không để nó tồn tại mà không ai đọc dashboard.

## 16. Runbook: điều tra CSP sau deploy và rollback có kiểm soát

### 16.1. Trang trắng sau khi chuyển Enforce

**Dấu hiệu:** HTML GET vẫn 200, nhưng SPA không mount/hydrate hoặc JavaScript console báo CSP blocked scripts.

**Xử lý:**

1. Xác định **policy revision và frontend artifact** đang chạy trên browser bị ảnh hưởng.
2. Xem Content-Security-Policy thực tế trên **HTML document HTTPS public**, không chỉ API JSON.
3. Tìm blocked directive/source qua browser DevTools và reports đã scrub.
4. Kiểm tra script inline có nonce/hash đúng, static JS origin, lazy chunks và dynamic import.
5. So canary với control, browser/version và source assets.
6. Nếu ảnh hưởng flow trọng yếu, stop canary và rollback policy hoặc frontend artifact **theo cặp đã biết tốt**.
7. Không mở script-src wildcard/unsafe-inline trên production như bản vá không review.
8. Viết regression fixture và rerun E2E trước khi promote lại.

### 16.2. CSP có Report-Only nhưng không nhận báo cáo

1. Kiểm tra browser đã nhận **Content-Security-Policy-Report-Only** trên đúng HTML origin chưa.
2. Kiểm tra report-to group, Reporting-Endpoints header và report-uri fallback có đúng host/path không.
3. Xem đường collector 204/4xx/429, WAF, ingress, request size, content types và rate limit.
4. Tạo synthetic violation trên staging, xác minh browser có hỗ trợ cơ chế đang dùng.
5. Kiểm tra ad-blocker/privacy setting, sampling và bộ browser.
6. Không mặc định số reports 0 là không có vi phạm; dùng browser E2E và fixture.

### 16.3. Báo cáo tăng khi nâng frontend hoặc framework

1. Gắn thời điểm tăng với frontend build/CSP revision/third-party script update.
2. Phân loại **vi phạm thực của app**, extensions, bot spam và collector noise.
3. Dùng route group, directive, host category; tránh lưu raw URLs chứa dữ liệu cá nhân.
4. So source inventory và E2E flow liên quan. Với dynamic bundles, xem static asset origins đã thay.
5. Đánh giá liệu thay script-src, connect-src, frame-src hay style-src thật sự cần thiết.
6. Sửa code/build hoặc allowlist origin **có review**; không tự cho mọi domain xuất hiện trong report.
7. Nếu ảnh hưởng canary Enforce, stop rollout cho đến khi test đạt.

### 16.4. Login, OAuth popup hoặc payment iframe bị chặn

1. Xác định bị **CSP**, **COOP/COEP**, **CORS**, **SameSite/third-party cookies** hay authentication failure; chúng không đồng nghĩa.
2. Kiểm tra CSP frame-src/frame-ancestors, form-action, script-src, connect-src và redirect chain theo flow.
3. Xem document nào đang bị iframe: CSP frame-ancestors thuộc **document được nhúng**, frame-src thuộc **document cha tải frame**.
4. Kiểm tra vendor sandbox endpoint và expected host origin thật.
5. Không tắt CSRF hoặc mở credentialed CORS wildcard để sửa CSP.
6. Xác minh lại login/logout, cookie session và CSRF bootstrap sau khi sửa.

### 16.5. CSP bị mất hoặc nhân đôi tại một CDN region

1. So headers Spring direct, ingress và public HTTPS edge ở nhiều vantage points.
2. Kiểm tra owner của header: Spring, CDN/static hosting, WAF hay gateway.
3. Phát hiện **hai Enforce policies** hoặc Enforce bị thay bằng Report-Only ngoài chủ đích.
4. So deployment manifest của artifact, CSP revision và edge policy.
5. Giảm lưu lượng region/canary có policy yếu; sửa qua IaC/GitOps thay vì manual hotfix không lưu dấu.
6. Purge cache HTML nếu đang giữ header cũ theo rule, rồi đo lại.
7. Thêm synthetic probe phát hiện mode/value sai.

### 16.6. Token hoặc dữ liệu người dùng xuất hiện trong CSP reports

1. Dừng thu payload raw và khóa truy cập telemetry chứa dữ liệu nhạy cảm.
2. Xác định trường nào có query/token, scope quyền truy cập và retention.
3. Không copy raw báo cáo sang chat/ticket để điều tra.
4. Sửa scrub trước data export, thay URL mang token bằng endpoint/body/header phù hợp.
5. Nếu kèm session cookie/JWT/credential leak, cân nhắc invalidation/rotation theo incident response policy.
6. Xóa/purge dữ liệu sai phạm trong các kho có hỗ trợ, theo quy trình và nghĩa vụ bảo mật của tổ chức.
7. Chạy staging synthetic canary và kiểm tra toàn bộ pipeline.

### 16.7. Rollback không phải là xóa mọi tác động ngay lập tức

Một CSP rollout có thể liên quan:

- **Frontend HTML artifact** và generated nonce/hash/CSP header.
- **Spring Security mode/config revision** khi Spring phục vụ HTML.
- **CDN/ingress header rules** và cache đã phân phối.
- **Service worker/offline HTML cache** còn giữ phiên bản cũ.
- **Browser-loaded document** đã nhận policy trước rollback, chỉ được thay khi tải lại document.
- **Session/authentication state** có thể bị gián đoạn trong lúc login/callback.
- **CORS/HSTS/preflight cache** thuộc các chính sách khác vẫn có vòng đời riêng.

Do đó rollback phải **khôi phục cặp artifact + CSP config + edge policy đã được kiểm chứng**, sau đó chạy lại HTTPS public probes và browser E2E. Không tuyên bố thành công chỉ vì app pod đã khởi động.

## 17. Bài tập thực hành

**Bài A — Phân biệt hai header:** Dùng một fixture chứa inline script không nonce trên staging. Xác minh Report-Only chỉ ghi nhận còn Enforce chặn; giải thích khi nào baseline Enforce khiến test khác kỳ vọng.

**Bài B — Inventory:** Lập danh sách nguồn script, style, connect, frame, font, img, worker và form-action của một SPA qua các flow login/checkout/profile/admin/error.

**Bài C — Classify reports:** Nhận bộ CSP reports giả gồm extension, payment provider, eval và URL lạ. Chọn hành động xử lý mà không tự động allowlist mọi nguồn.

**Bài D — Telemetry privacy:** Xây một CSP collector staging có body limit/rate limit, scrub query/fragment, gom directive/route group. Chứng minh không có raw token/session trong logs.

**Bài E — Nonce động:** Render HTML có script nonce 128-bit CSPRNG; kiểm tra nonce CSP header trùng template trên cùng response nhưng khác giữa các response. Không shared-cache HTML chứa nonce.

**Bài F — Hash cố định:** Chọn một inline script bất biến, tính SHA-256 CSP hash từ nội dung chính xác và chạy regression khi nội dung thay đổi một ký tự.

**Bài G — Không dùng unsafe-inline:** Chuyển onclick inline thành addEventListener, bỏ eval trong production bundle, sau đó thử Enforce với script-src chặt.

**Bài H — Servlet:** Cấu hình CspPolicyProperties mode report-only/enforce và MockMvc tests cho header đúng; chứng minh POST report được tiếp nhận nhưng POST nghiệp vụ thiếu CSRF bị từ chối.

**Bài I — Reactive:** Dùng ServerHttpSecurity CSP mode và WebTestClient kiểm tra headers. Phân biệt collector ngoài app với collector trong WebFlux cần CSRF exemption hẹp.

**Bài J — Frontend CDN:** Đặt CSP trên JSON API nhưng bỏ trên SPA HTML ở CDN, chứng minh document không được bảo vệ. Di chuyển policy đến đúng HTML origin và test browser.

**Bài K — Third-party sandbox:** Tích hợp một payment iframe test, nhận diện frame-src/form-action/redirect bị block rồi sửa chỉ đúng directive/source đã review.

**Bài L — Canary:** Thiết kế go/no-go gates, stop threshold và rollback cho CSP candidate trên một cohort nhỏ, so với login/checkout success của control.

**Bài M — Drift drill:** Giả lập một CDN region còn CSP Report-Only khi regions khác đã Enforce. Dùng multi-region probes và release manifest xác định sai lệch.

**Bài N — Incident tabletop:** Giả sử sau Enforce có login loop và CSP collector lưu URL chứa token. Xác định thứ tự ưu tiên khôi phục flow người dùng, bảo vệ dữ liệu và kiểm chứng sau sửa.

## 18. Checklist trước phát hành và tổng kết

### 18.1. Release readiness checklist

| Hạng mục | Điều kiện PASS |
| --- | --- |
| **Scope** | Biết HTML origin/routes chịu CSP; không nhầm với JSON API |
| **Policy revision** | Có Git review, owner, các nguồn đã phê duyệt và mức hỗ trợ browser |
| **Directives** | script/style/connect/frame/form/object/base/ancestors được chọn theo threat model |
| **Reporting** | Report-Only candidate có collector khỏe, dữ liệu đã scrub và sampling được hiểu |
| **Inline scripts** | Đã externalize hoặc dùng nonce/hash đúng; tránh unsafe-inline/unsafe-eval không phê duyệt |
| **Nonce/hash** | Nonce CSPRNG theo response; hash đúng bytes theo artifact; không shared-cache HTML động |
| **Third-party** | Payment/SSO/captcha/analytics được review và test qua sandbox |
| **Servlet** | SecurityFilterChain phát đúng mode/header, không tắt CSRF nghiệp vụ |
| **Reactive** | SecurityWebFilterChain phát đúng mode/header, collector xử lý riêng |
| **CSP header contract** | Enforce và Report-Only có đúng tên/giá trị, không nhân đôi Enforce ngoài ý muốn |
| **HTTPS edge** | Browser nhận CSP ở HTML origin sau proxy/CDN, không chỉ Spring direct |
| **Browser E2E** | Fixture negative test và các luồng login/checkout/profile/admin/error PASS |
| **CSRF/CORS/session** | Cookie và token vẫn hoạt động; CORS exact origin; POST không CSRF vẫn bị chặn |
| **Canary** | Routing ổn định, rollout gates/owner/rollback sẵn sàng |
| **Observability** | Metrics labels hữu hạn; CSP reports không lộ URL query/token/cookie |
| **Drift** | Version của artifact/CSP/CDN tương ứng trên pods và regions |
| **Rollback** | Cặp artifact/config/edge policy known-good có thể khôi phục và retest |
| **Post-deploy** | Synthetic probes, collector health và UX/SLO theo dõi liên tục |

### 18.2. Mười hai nguyên tắc cần ghi nhớ

1. **Report-Only là giai đoạn quan sát, không phải thực thi.**
2. **Enforce chặn tài nguyên trái phép**, nên phải kiểm thử browser behavior, không chỉ header text.
3. **Có thể giữ Enforce baseline khi thử Report-Only candidate**; report-only không làm yếu baseline.
4. **CSP phải nằm trên HTML document origin**, không chỉ ở JSON API backend khác hostname.
5. **Inventory đi trước allowlist**; vi phạm không phải lệnh tự cấp quyền cho một nguồn.
6. **Nonce cần ngẫu nhiên mới cho từng HTML response**, hash phù hợp inline code bất biến; không hardcode nonce trong static CDN artifact.
7. **Inline handlers/eval và third-party scripts cần được refactor/review** thay vì mở unsafe-inline/unsafe-eval đại trà.
8. **CSP report collector nhận dữ liệu không đáng tin**, phải hạn chế size/rate, scrub thông tin và quản lý quyền truy cập.
9. **Servlet và WebFlux có DSL/filter/CSRF khác nhau**, cần test cả hai khi hệ thống sử dụng.
10. **CSP không thay CSRF, CORS, HSTS, HTTP firewall, cookie protection hay authorization.**
11. **Canary/rollout cần dựa trên cả security negative tests lẫn user-flow SLO**, không chỉ số báo cáo.
12. **Rollback phải xem HTML artifact, CSP policy, proxy/CDN và browser cache**, sau đó verify lại tại HTTPS public edge.

**Kết luận:** Chuyển CSP từ Report-Only sang Enforce không phải hành động đổi một tên HTTP header. Đó là một **thay đổi chính sách có version, có quan sát, có sửa mã, có kiểm thử browser và có khả năng rollback**. Khi thực hiện đúng, Spring Security và hạ tầng HTTP phát chính sách trên đúng HTML document, còn đội vận hành dùng reports đã scrub, canary, security tests và UX metrics để chặn nguồn không tin cậy mà không làm đứt luồng người dùng hợp lệ.

## Tài liệu tham khảo chính thức và bổ trợ

- [Spring Security 6.5 — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — CORS Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — CORS Reactive](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — Content-Security-Policy Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy)
- [MDN — Content-Security-Policy-Report-Only Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only)
- [MDN — CSP Nonces](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP#nonces)
- [MDN — Reporting-Endpoints Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Reporting-Endpoints)
- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)





