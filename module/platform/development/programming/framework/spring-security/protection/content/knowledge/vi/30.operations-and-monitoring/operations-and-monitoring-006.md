# Giới hạn dữ liệu lưu trong báo cáo CSP và log bảo mật

## Mục tiêu, phạm vi và tình huống thực tế

Trong chương **Vận hành và giám sát** của dịch vụ **SPRING_SECURITY_HTTP_PROTECTION**, Spring Security hỗ trợ phòng vệ HTTP và trình duyệt qua **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session**. Các lớp bảo vệ này tạo ra tín hiệu quan sát quan trọng: CSP violation, CSRF deny, authentication/authorization deny, RequestRejectedException, lỗi CORS và vấn đề cookie. Nhưng nếu bật ghi log toàn bộ request/response và lưu nguyên báo cáo CSP, chính hệ thống giám sát có thể trở thành nơi làm lộ **token, cookie phiên, thông tin cá nhân, URL nội bộ và dữ liệu nghiệp vụ**.

Tình huống giả định: SPA tại **https://app.example.com** dùng cookie để gọi API tại **https://api.example.com**. Đội vận hành thử policy CSP mới qua **Content-Security-Policy-Report-Only** và nhận POST báo cáo. Cùng lúc, ứng dụng Spring Security ghi audit khi CSRF bị từ chối và gateway ghi access log. Một đường dẫn có thể chứa email hoặc mã đặt lại mật khẩu; một đoạn inline script có thể nhúng dữ liệu theo phiên; một log debug có thể chứa **JSESSIONID, Authorization và X-CSRF-TOKEN**. Nếu toàn bộ dữ liệu này được đẩy vào APM/SIEM, rủi ro đã lan rộng trước khi đội bảo mật bắt đầu điều tra.

Bài học giải quyết câu hỏi: **Cần giữ thông tin tối thiểu nào để phát hiện, phân loại, sửa lỗi bảo mật mà không lưu dữ liệu thô không cần thiết?** Phạm vi bao gồm cả **Servlet và Reactive/WebFlux**, frontend browser, gateway/CDN, collector CSP, metrics, logs, traces, tests, retention và incident response.

Sau bài học, người học có thể:

1. Mô tả trường dữ liệu mà **CSP Reporting API** và cơ chế **report-uri** có thể gửi, bao gồm URL, policy, referrer và script sample.
2. Phân biệt **dữ liệu cần để tổng hợp bảo mật** với **dữ liệu nhạy cảm không nên thu hoặc lưu**.
3. Xây dựng hợp đồng **allowlist schema**, chuẩn hóa URL thành nhóm route, phân loại directive/source, không lưu raw report.
4. Bảo vệ endpoint nhận báo cáo khỏi **report forgery, spam, JSON bombs, log injection và dữ liệu độ nhạy cao**.
5. Áp dụng **CSRF exception hẹp** cho collector không có session mà vẫn duy trì bảo vệ browser API, Servlet và WebFlux.
6. Thiết kế logs/metrics/traces hữu hạn với **privacy by design**, giới hạn cardinality, retention, quyền truy cập và pipeline scrub.
7. Viết **MockMvc, WebTestClient và browser E2E tests** chứng minh cả CSP/reporting lẫn bảo mật dữ liệu quan sát.
8. Chẩn đoán collector outage, report volume spike, false positives và sự cố lộ secrets qua hệ thống giám sát.

## 1. Nguyên tắc nền tảng: thu ít hơn trước khi phải xóa nhiều hơn

### 1.1. Data minimization áp dụng ở từng điểm thu

Một pipeline thường có nhiều lớp, và mỗi lớp đều có thể lưu dữ liệu:

~~~mermaid
flowchart LR
    A["Browser: CSP violation"] --> B["CDN / WAF / Gateway"]
    B --> C["CSP collector Spring hoặc dịch vụ riêng"]
    C --> D["Validate + classify + sanitize trong memory"]
    D --> E["Aggregate counters / bounded events"]
    E --> F["Metrics / logs / SIEM có phân quyền"]
    F --> G["Dashboards / alerts / incident response"]
~~~

**Điểm dừng quan trọng là trước bước lưu bền vững hoặc truyền sang bên thứ ba.** Nếu raw JSON đã đi vào reverse-proxy access log, APM request-body capture hoặc message broker, việc scrub ở dashboard là quá muộn.

Quy trình nên:

1. **Không thu** trường không cần: tắt request/response body capture, Cookie/Authorization header logging và CSP script samples mặc định.
2. **Giới hạn sớm** kích thước body, số reports/batch, nesting depth, rate và thời gian xử lý.
3. **Chỉ lấy giá trị để phân loại trong memory**; không ghi raw payload ra log, disk, queue hoặc trace.
4. **Chuẩn hóa thành dữ liệu hữu hạn**: policy revision tin cậy, directive category, route group, source class, disposition và outcome.
5. **Lưu tối thiểu** theo thời gian và quyền hạn đã được phê duyệt; kiểm tra sao lưu, replicas và nhà cung cấp APM.
6. **Xóa theo lifecycle** và có quy trình incident nếu dữ liệu nhạy cảm bị thu ngoài ý muốn.

Data minimization không đồng nghĩa phải bỏ mọi tín hiệu. Mục tiêu là giữ được khả năng chứng minh CSP đang hoạt động, phát hiện regression CSRF/CORS và xác định lớp bảo vệ từ chối mà **không cần giữ danh tính hay secrets của người dùng**.

### 1.2. Bốn loại dữ liệu cần phân biệt

| Loại | Ví dụ | Cách xử lý mặc định |
| --- | --- | --- |
| **Hữu hạn, ít nhạy cảm** | Policy revision do server xác định, directive allowlist, environment, release | Có thể tổng hợp theo policy |
| **Có thể nhận dạng gián tiếp** | Route rất hiếm, URL cụ thể, thời điểm chính xác, browser/region kết hợp | Hạ độ chi tiết; review retention và quyền |
| **Có nguy cơ chứa PII/secrets** | document URL, referrer, blocked URL, script sample, exception message | Không lưu raw; chỉ phân loại tạm trong memory |
| **Credential hoặc dữ liệu tối mật** | JSESSIONID, JWT, refresh token, CSRF/XSRF token, Authorization, password | Không log, không dùng làm metric label hoặc event field |

Một **hash không mặc định làm dữ liệu an toàn**: băm token, email hoặc URL vẫn có thể tạo mã theo dõi ổn định, có thể bị dò từ không gian giá trị nhỏ và không giải quyết câu hỏi có cần thu dữ liệu hay không. Ưu tiên **không thu** thay vì thay nguyên văn bằng hash.

### 1.3. Mục tiêu của một sự kiện giám sát CSP

Từ báo cáo thô:

~~~text
document URL = trang theo session
blocked URL  = nguồn asset hoặc inline
sample       = đoạn script/style, có thể chứa dữ liệu user
original CSP = policy dài có thể khác revision hiện tại
~~~

Chỉ cần lưu dạng đã phân loại:

~~~text
event=csp.violation
policy_revision=csp-v7
route_group=checkout
effective_directive=script-src-elem
source_class=approved-payment-provider
disposition=report
browser_family=chromium
count=1
~~~

**policy_revision ở đây đến từ nguồn cấu hình/rollout tin cậy**, không phải tự tin vào chuỗi original-policy do một client bất kỳ gửi.

## 2. CSP Report-Only, Enforce và hai định dạng báo cáo

### 2.1. Report-Only không ngăn tài nguyên, Enforce có hiệu lực chặn

~~~http
Reporting-Endpoints: csp="https://app.example.com/__security/csp-report"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-to csp; report-uri /__security/csp-report
~~~

Ví dụ policy thử nghiệm: browser phân tích vi phạm mà **không chặn chỉ vì Report-Only**. Khi dùng **Content-Security-Policy** thay vì Report-Only, các directives thực thi có thể ngăn nguồn vi phạm. Một HTML document có thể có **Enforce policy hiện hành** và **Report-Only candidate**; hai cơ chế không tự triệt tiêu nhau.

**CSP phải nằm trên response HTML document cần bảo vệ.** API JSON ở một origin khác phát CSP không tự bảo vệ HTML frontend. Nếu HTML được serve bởi CDN, chính frontend/CDN phải phát header.

### 2.2. report-to và report-uri không gửi chung một định dạng

| Thành phần | Cơ chế cũ report-uri | Reporting API report-to |
| --- | --- | --- |
| Chỉ định đích | CSP directive report-uri | CSP directive report-to tham chiếu tên endpoint |
| Mapping endpoint | URI trong directive | Header Reporting-Endpoints, endpoint URL HTTPS |
| Body thường gặp | Object có khóa csp-report | JSON array các reports, type csp-violation và body |
| Content-Type thường gặp | application/csp-report | application/reports+json |
| Trường vi phạm | document-uri, blocked-uri, effective-directive... | documentURL, blockedURL, effectiveDirective... |
| Disposition | enforce hoặc report | enforce hoặc report |
| Dữ liệu không tin cậy | Có | Có |

**report-uri đã bị deprecated** nhưng vẫn hữu ích như fallback cho một số browser cũ. Browser hỗ trợ report-to có thể bỏ qua report-uri trong cùng CSP policy; **không kỳ vọng cả hai collector luôn nhận cùng một violation**. Hỗ trợ thực tế còn tùy browser/version và privacy settings. Test bằng các browser mục tiêu.

Không dùng CSP meta tag như thay thế tương đương header reporting; **Report-Only và một số directives cần HTTP response header**.

### 2.3. Ví dụ legacy report-uri

~~~http
POST /__security/csp-report HTTP/1.1
Host: app.example.com
Content-Type: application/csp-report

{
  "csp-report": {
    "document-uri": "https://app.example.com/checkout?flow=example",
    "blocked-uri": "https://thirdparty.example.net/asset.js",
    "effective-directive": "script-src-elem",
    "violated-directive": "script-src-elem",
    "disposition": "report",
    "original-policy": "default-src 'self'; script-src 'self'; report-uri /__security/csp-report",
    "source-file": "https://app.example.com/app.js",
    "line-number": 22,
    "status-code": 200
  }
}
~~~

Dữ liệu là **minh họa synthetic**, không phải payload production. URL/path/query, original policy và source-file không phải dữ liệu bạn nên lưu nguyên. Một báo cáo có thể thiếu trường hoặc có trường khác giữa browser versions.

### 2.4. Ví dụ Reporting API

~~~http
POST /__security/csp-report HTTP/1.1
Host: app.example.com
Content-Type: application/reports+json

[
  {
    "type": "csp-violation",
    "age": 45,
    "url": "https://app.example.com/checkout",
    "body": {
      "documentURL": "https://app.example.com/checkout",
      "effectiveDirective": "script-src-elem",
      "blockedURL": "inline",
      "disposition": "enforce",
      "sourceFile": "https://app.example.com/app.js",
      "lineNumber": 14,
      "sample": "/* synthetic example */",
      "originalPolicy": "default-src 'self'; script-src 'self'"
    }
  }
]
~~~

Reporting API có thể truyền **nhiều report trong một POST** và metadata khác (ví dụ age, user agent) nên parser phải **giới hạn số entries**, không giả định request luôn chứa đúng một event.

### 2.5. Những trường có nguy cơ chứa dữ liệu nhạy cảm

| Legacy / Reporting API | Rủi ro |
| --- | --- |
| document-uri / documentURL | Query chứa email, reset code, order ID, personal path |
| blocked-uri / blockedURL | URL tài nguyên, query, internal endpoint hoặc literal inline/eval |
| referrer | Trang trước, URL có định danh và dữ liệu khách hàng |
| source-file / sourceFile | Đường dẫn code, query, thông tin build/private CDN |
| script-sample / sample | Đoạn đầu của inline script/style/handler có thể chứa dữ liệu được render |
| original-policy / originalPolicy | Cấu hình nguồn tin cậy cần quản trị, nhưng ở report lại là **input không tin cậy** |
| user_agent | Fingerprint/tracking, high cardinality |
| line/column | Có thể cần khi debug, nhưng route/version/source context vẫn có thể nhận dạng |
| age, status-code, disposition | Dùng được sau validation/range limits; không mặc định tin dữ liệu |

Browsers có một số **quy tắc giảm chi tiết cross-origin blocked URLs**, nhưng không được dùng browser truncation làm biện pháp bảo vệ dữ liệu phía collector. Payload có thể bị client khác gửi giả và cùng-origin URLs vẫn có thể chứa thông tin riêng tư.

## 3. Vì sao report-sample là một quyết định dữ liệu nhạy cảm?

### 3.1. report-sample có thể đưa nội dung code vào báo cáo

Ví dụ CSP:

~~~http
Content-Security-Policy-Report-Only: script-src 'self' 'report-sample'; report-uri /__security/csp-report
~~~

Trong các browser hỗ trợ, nếu inline script hoặc style vi phạm, report có thể chứa **một đoạn mẫu ngắn** của nội dung bị vi phạm. Ngay cả một đoạn ngắn cũng có thể chứa:

- Giá trị JWT/token hoặc mật khẩu được nhúng sai vào HTML.
- Email, tên, mã đơn hàng, tên khách hoặc một phần thông tin tài khoản.
- Dữ liệu cấu hình frontend nội bộ hoặc phần mã nhạy cảm.
- Một payload do attacker kiểm soát, dùng để gây log injection nếu được hiển thị không escape.

**Khuyến nghị mặc định:** Không bật **report-sample** nếu chưa có phân tích dữ liệu và nhu cầu chẩn đoán rõ ràng. Nếu đã bật, collector vẫn **không nên lưu sample nguyên văn**. Khi debug, dùng staging với dữ liệu synthetic và source map được bảo vệ thay cho đoạn script production.

### 3.2. Giới hạn bộ dữ liệu không chỉ ở collector

Một pipeline có thể không lưu sample vào database nhưng vẫn để lộ ở:

- Nginx/Ingress HTTP body logging.
- WAF request inspection logs hoặc packet capture.
- Spring MVC/WebFlux request logging filter.
- APM automatic request-body capture.
- Unhandled exception log khi JSON parse fail.
- Kafka dead-letter queue chứa raw body.
- Distributed trace attributes/baggage.
- Object storage snapshots/backups và exports cho vendor.
- Frontend console/bug-report hoặc screenshot chia sẻ công khai.

Cần có **inventory các sink** trước rollout. Một chính sách “DB không lưu PII” chưa đủ nếu raw body đang nằm trong APM hoặc SIEM.

### 3.3. Khi cần điều tra vi phạm trên một dòng cụ thể

Thay vì lưu script sample, giữ **directive, route group, frontend build revision và source class**. Dùng source map private hoặc reproducible build để khớp vị trí trong **môi trường test**. Nếu cần tạm thu thông tin chi tiết hơn cho incident, phải có owner, quyền hạn, thời hạn, phạm vi tối thiểu, audit truy cập và quy trình xóa.

## 4. Phân loại security logs của Spring Security trước khi quyết định lưu

### 4.1. Các sự kiện thường cần giữ

| Control/tầng | Ví dụ sự kiện | Thông tin tối thiểu hữu ích |
| --- | --- | --- |
| **CSRF Servlet/Reactive** | Unsafe request thiếu/sai token | reason category, method class, route group, release, denied |
| **Authorization** | AccessDeniedException | control=authorization, policy/role category hữu hạn, route group |
| **Authentication** | Login failed, session expired | auth flow stage, outcome, client class, release |
| **HTTP firewall Servlet** | RequestRejectedException | layer=spring-servlet-firewall, reason category, method class |
| **WAF/gateway** | Edge rule rejected | WAF rule class, host group, route group, decision |
| **CORS** | Trusted preflight failed | OPTIONS, origin class/trusted flag, requested header class |
| **CSP** | Violation report | disposition, effective directive, source class, frontend revision |
| **Session/cookie** | Cookie blocked/renewed | cookie name category, policy outcome; không có giá trị cookie |
| **HSTS/headers** | Public HTTPS policy drift | header contract ID, expected revision, PASS/FAIL |

**Không đánh đồng HTTP 400/403 với lỗi CSRF hoặc firewall được xác nhận.** Một HTTP 403 từ WAF không chứng minh CsrfFilter đã chạy; cần source-aware events.

### 4.2. Những nội dung không ghi trong log

~~~text
Cookie: JSESSIONID=...
Authorization: Bearer ...
X-CSRF-TOKEN: ...
X-XSRF-TOKEN: ...
POST /login body password=...
GET /reset?token=...
CSP report sample="window.userSecret=..."
RequestRejectedException message with raw URI...
~~~

Nhiều trường hợp **exception.getMessage()** chứa raw request data do client kiểm soát, nhất là từ HTTP firewall. Không ghi nguyên stack hoặc headers chỉ vì log level DEBUG được bật. Hạn chế **request/response body capture** ở APM và logging middleware.

### 4.3. Audit event đề xuất

~~~json
{
  "event": "http.security.decision",
  "control": "csrf",
  "decision": "denied",
  "reason": "invalid_or_missing_actual",
  "httpMethod": "POST",
  "routeGroup": "orders",
  "statusClass": "4xx",
  "service": "protection-api",
  "release": "r42",
  "requestId": "req-8ae2"
}
~~~

Đây là **schema dự án tự định nghĩa**, không phải định dạng mặc định Spring Security. requestId chỉ nên là ID độc lập đã được sanitize ở logs có quyền truy cập; **không** sử dụng làm metric label. Không lưu username, userId hoặc sessionId theo mặc định chỉ để biết một request bị 403.

## 5. Hợp đồng lưu trữ: raw input chỉ tồn tại tạm thời

### 5.1. Data model sau chuẩn hóa

Một sự kiện CSP đã giảm dữ liệu có thể lưu hoặc tổng hợp:

~~~json
{
  "eventType": "csp-violation",
  "policyRevision": "csp-v7",
  "frontendRevision": "web-r42",
  "routeGroup": "checkout",
  "directive": "script-src-elem",
  "sourceClass": "approved-payment-provider",
  "disposition": "report",
  "environment": "prod"
}
~~~

**policyRevision/frontendRevision phải lấy từ nguồn phát hành tin cậy**, không dựa trên original-policy, documentURL hoặc client-controlled fields. Nếu rollout nhiều policy và không xác minh được revision, dùng **unknown**; không gắn session ID hay secret vào reporting URL để correlate.

Với nhiều nhu cầu vận hành, **aggregate counters theo directive/source/route/revision** đã đủ. Không nhất thiết lưu từng report riêng biệt.

### 5.2. Quyết định giữ hay bỏ từng field

| Field trong báo cáo | Dùng tạm trong memory | Dữ liệu cuối |
| --- | --- | --- |
| type | Chỉ chấp nhận csp-violation | Event type hữu hạn |
| effectiveDirective | Xác định directive | Enum hoặc other |
| disposition | Phân biệt report/enforce | report/enforce/unknown |
| documentURL | Parse route | checkout/login/admin/other |
| blockedURL | Phân loại nguồn | inline/eval/self/approved/external-other |
| originalPolicy | Thường không cần | Trusted policy revision từ release |
| sourceFile và line/column | Không cần cho analytics thường | Bỏ; debug riêng có kiểm soát |
| sample/script-sample | Không cần | **Không lưu** |
| referrer | Không cần | **Không lưu** |
| user_agent | Có thể phân loại nhanh | Browser family hữu hạn hoặc bỏ |
| age, statusCode | Có thể validate | Bỏ hoặc bounded status class |
| IP/Cookie/Authorization | Không cần | **Không lưu** |
| Report count | Có sau giới hạn batch | Aggregate counter |

**Hash không tự động ẩn danh**. Hash URL, email, token hoặc session ID có thể tạo khóa theo dõi dài hạn hoặc bị đoán qua từ điển. Ưu tiên không thu thay vì hash raw secrets.

### 5.3. URL được chuyển thành route group

Không đưa raw URL vào metric label:

~~~text
KHÔNG NÊN:
route=https://app.example.com/users/84392/checkout?email=...

NÊN:
route_group=checkout
~~~

Quy trình:

1. Giới hạn chiều dài URL trước parse.
2. Parse URI trong memory, invalid input trở thành invalid/other.
3. Chỉ chấp nhận HTTPS origin canonical đã duyệt, port phù hợp và không userinfo.
4. Map path bằng exact match hoặc prefix **có slash boundary** sang nhóm cố định.
5. Không lưu path cụ thể, query, fragment hoặc unknown host.
6. Dùng other cho nguồn ngoài phạm vi; không dùng raw fallback.
7. Không sử dụng báo cáo làm input cho CSP allowlist/authorization.

Path chứa ID cũng có thể là dữ liệu cá nhân, dù đã bỏ query. **Đường dẫn thô không phải trường audit mặc định**.

### 5.4. Nhóm directive/source hữu hạn

~~~text
directive:
  script-src | script-src-elem | script-src-attr
  style-src | style-src-elem | style-src-attr
  connect-src | img-src | font-src | frame-src
  frame-ancestors | worker-src | form-action | other

source_class:
  inline | eval | self | approved-static-cdn
  approved-payment-provider | browser-extension-unverified
  external-other | invalid
~~~

Nhóm approved-payment-provider **chỉ nghĩa là chuỗi URL khớp host đã biết**, không chứng minh report đến từ browser thật. Không tự thêm nguồn lạ vào CSP khi report volume tăng.

## 6. Collector phải giới hạn dữ liệu trước khi persist

### 6.1. Luồng ingestion

Một collector CSP có thể bị browser, bot hoặc client tùy ý gọi. Nó là **Internet-facing telemetry endpoint**, không phải business API có user identity.

~~~mermaid
flowchart TD
    A["Browser hoặc client tùy ý"] --> B["TLS edge: rate/body limits"]
    B --> C["Parser: content type, JSON size/depth"]
    C --> D{"Legacy object hay Reporting API batch?"}
    D -->|Hợp lệ| E["Validate type + max batch entries"]
    D -->|Không| F["Reject/drop, không echo input"]
    E --> G["Reduce URL/directive/source vào enum"]
    G --> H["Chỉ reduced DTO đến metrics/queue"]
    H --> I["Retention + access controls"]
~~~

### 6.2. Các giới hạn nhiều lớp

| Tầng | Kiểm soát |
| --- | --- |
| Gateway/ingress | Max body size, request rate và concurrent connections |
| Servlet/Reactive HTTP server | Header/line limits, timeouts, early rejection |
| JSON parser | Max bytes, nested depth và string length |
| Reporting batch | Max reports mỗi POST |
| Schema | Chỉ CSP format và loại được phê duyệt |
| Normalizer | Enum/known host/route template |
| Metrics | Cardinality budget và sampling/drop policy |
| Queue | Bounded capacity; không raw payload trong dead-letter |
| Persistent storage | TTL, encryption, least privilege |
| Logging/APM | Không request-body/secret capture |

**Không chỉ kiểm tra string length trong Controller sau khi framework đã deserialize body**: lúc đó RAM có thể đã bị sử dụng. Giới hạn ở edge/server **và** trong lúc đọc payload.

### 6.3. Endpoint CSP không phải business mutation

Ví dụ đích nhận:

~~~text
POST https://app.example.com/__security/csp-report
~~~

Không đưa session ID, user ID, email, CSRF token hoặc policy secret vào reporting URL. Browser có thể gửi cookie theo policy; backend collector **không được phụ thuộc cookie hoặc ghi Cookie vào log**.

Nếu collector nằm cùng Spring app có cookie-authenticated API, có thể cần miễn CSRF cho **đúng method POST và path collector**. Không miễn CSRF trên toàn prefix /api/** hoặc /__security/**. Nếu có thể, tách collector riêng, không chứa session/business state.

### 6.4. Payload không phải chứng cứ được xác thực

Các field type, documentURL, originalPolicy, disposition, user_agent và cả Origin/Referer đều có thể bị giả mạo. Do đó:

- Coi reports là **low-trust telemetry**.
- Chống rate abuse và metric poisoning; không lấy report count làm attack count.
- Không tự khóa user hoặc tự allowlist external script do một report.
- Đối chiếu browser E2E, CSP headers trên HTML origin, frontend errors và business SLO.
- Có synthetic canary reports trong staging để kiểm tra ingestion; **0 reports không có nghĩa hệ thống an toàn**.
- Không phản chiếu nguyên báo cáo trong 400/413/429 response.

## 7. Java normalizer: chỉ tạo enum, không giữ raw input

### 7.1. Reduced event type

~~~java
record ReducedCspReport(
    String routeGroup,
    String directive,
    String sourceClass,
    String disposition
) {}
~~~

**Không có field documentURL, blockedURL, originalPolicy, sample hoặc referrer** trong DTO đi tới metrics/storage.

### 7.2. Normalizer minh họa cho Jackson JsonNode

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;

final class CspReportNormalizer {
    static final int MAX_BATCH = 10;
    static final int MAX_URL_CHARS = 2048;

    List<ReducedCspReport> reduce(JsonNode root) {
        List<ReducedCspReport> events = new ArrayList<>();

        if (root.isObject() && root.path("csp-report").isObject()) {
            JsonNode b = root.path("csp-report");
            events.add(reduced(
                b.path("document-uri").asText(""),
                b.path("blocked-uri").asText(""),
                b.path("effective-directive").asText(
                    b.path("violated-directive").asText("")),
                b.path("disposition").asText("unknown")));
            return events;
        }

        if (!root.isArray() || root.size() > MAX_BATCH) {
            return List.of();
        }

        for (JsonNode r : root) {
            if (!"csp-violation".equals(
                    r.path("type").asText(""))) continue;
            JsonNode b = r.path("body");
            if (!b.isObject()) continue;

            events.add(reduced(
                b.path("documentURL").asText(""),
                b.path("blockedURL").asText(""),
                b.path("effectiveDirective").asText(""),
                b.path("disposition").asText("unknown")));
        }
        return events;
    }

    private ReducedCspReport reduced(
            String document, String blocked,
            String directive, String disposition) {

        return new ReducedCspReport(
            routeGroup(document), directiveClass(directive),
            sourceClass(blocked), dispositionClass(disposition));
    }

    private String directiveClass(String s) {
        return switch (s) {
            case "script-src", "script-src-elem", "script-src-attr",
                 "style-src", "style-src-elem", "style-src-attr",
                 "connect-src", "img-src", "font-src",
                 "frame-src", "frame-ancestors", "worker-src",
                 "form-action", "object-src", "base-uri" -> s;
            default -> "other";
        };
    }

    private String dispositionClass(String s) {
        return switch (s) {
            case "report", "enforce" -> s;
            default -> "unknown";
        };
    }

    private String routeGroup(String raw) {
        URI u = safeHttps(raw);
        if (u == null || !"app.example.com".equalsIgnoreCase(
                u.getHost())) return "external-or-invalid";

        String path = u.getRawPath();
        if (path == null) return "other";
        if (path.equals("/checkout") ||
                path.startsWith("/checkout/")) return "checkout";
        if (path.equals("/login") ||
                path.startsWith("/login/")) return "login";
        if (path.equals("/admin") ||
                path.startsWith("/admin/")) return "admin";
        return "other";
    }

    private String sourceClass(String raw) {
        if ("inline".equals(raw)) return "inline";
        if ("eval".equals(raw)) return "eval";
        if (raw != null && raw.startsWith("chrome-extension:")) {
            return "browser-extension-unverified";
        }
        URI u = safeHttps(raw);
        if (u == null) return "invalid";
        String host = u.getHost();
        if ("app.example.com".equalsIgnoreCase(host)) {
            return "self";
        }
        if ("static.example.com".equalsIgnoreCase(host)) {
            return "approved-static-cdn";
        }
        if ("pay.example.net".equalsIgnoreCase(host)) {
            return "approved-payment-provider";
        }
        return "external-other";
    }

    private URI safeHttps(String raw) {
        if (raw == null || raw.length() > MAX_URL_CHARS) {
            return null;
        }
        try {
            URI u = URI.create(raw);
            if (!"https".equalsIgnoreCase(u.getScheme())
                    || u.getRawUserInfo() != null
                    || u.getHost() == null
                    || (u.getPort() != -1 && u.getPort() != 443)) {
                return null;
            }
            return u;
        } catch (IllegalArgumentException ignored) {
            return null;
        }
    }
}
~~~

**Đây là normalizer mang tính hướng dẫn**, không phải CSP parser đầy đủ. Hostnames, categories, URL rules và size constraints cần được review theo hệ thống thật. JSON parser còn phải giới hạn độ sâu, độ dài chuỗi và số entries. Các nguồn enum được suy từ **untrusted strings**, không phải cơ chế xác thực reports.

### 7.3. Những field cố ý không đưa vào output

- sample/script-sample, originalPolicy, referrer.
- sourceFile, line/column, user_agent.
- documentURL, blockedURL, query/fragment.
- IP, Cookie, Authorization, CSRF token, session ID.

Khi cần thêm dữ liệu cho một incident riêng, tạo quy trình thu thập **có phạm vi/retention/approval**, không nới DTO chung cho toàn bộ production.

## 8. Servlet: collector có giới hạn bytes và không log raw body

Ví dụ dưới đây dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+**. Phần parser sử dụng Jackson; phần metrics dùng Micrometer. Đây là **mẫu kiến trúc có giới hạn**, không thay reverse-proxy limits, JSON stream constraints, anti-abuse monitoring và retention policy.

### 8.1. Receiver Servlet đọc tối đa một lượng bytes cố định

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
final class ServletCspReportController {

    private static final int MAX_BYTES = 16 * 1024;
    private final ObjectMapper mapper;
    private final MeterRegistry meters;
    private final CspReportNormalizer normalizer =
        new CspReportNormalizer();

    ServletCspReportController(
            ObjectMapper mapper, MeterRegistry meters) {
        this.mapper = mapper;
        this.meters = meters;
    }

    @PostMapping(
        path = "/__security/csp-report",
        consumes = {
            "application/csp-report",
            "application/reports+json"
        }
    )
    ResponseEntity<Void> accept(
            HttpServletRequest request) throws IOException {

        // Không dùng @RequestBody String: bộ nhớ có thể đã được
        // cấp phát trước khi controller kiểm tra độ dài.
        byte[] bytes = request.getInputStream()
            .readNBytes(MAX_BYTES + 1);

        if (bytes.length > MAX_BYTES) {
            return ResponseEntity.status(
                HttpStatus.PAYLOAD_TOO_LARGE).build();
        }

        JsonNode root;
        try {
            root = mapper.readTree(bytes);
        } catch (JsonProcessingException invalidJson) {
            // Không log exception message hoặc JSON.
            return ResponseEntity.badRequest().build();
        }

        if (root == null) {
            return ResponseEntity.badRequest().build();
        }

        List<ReducedCspReport> events =
            normalizer.reduce(root);

        for (ReducedCspReport event : events) {
            meters.counter(
                "csp_reports_ingested_total",
                "route_group", event.routeGroup(),
                "directive", event.directive(),
                "source_class", event.sourceClass(),
                "disposition", event.disposition()
            ).increment();
        }

        // Không echo payload, token, URL hoặc report count.
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

**Cần hiểu giới hạn của mã ví dụ:**

- readNBytes(MAX_BYTES+1) giới hạn bytes **được controller đọc**, nhưng server/proxy vẫn phải có request body limit và read timeout để chống slow clients.
- Jackson cần cấu hình **stream read constraints** cho độ sâu JSON, độ dài chuỗi và khả năng sử dụng tài nguyên; max bytes không giải quyết mọi parsing attack.
- Normalizer bỏ báo cáo không đúng format và giới hạn số elements/batch. Có thể dùng **counter drop tổng quát**, không log raw.
- Nếu lượng metrics lớn, cần quota/batching. Ngay cả bounded label combinations cũng có thể làm quá tải monitoring nếu không có rate limit.
- Không dùng ObjectMapper hoặc exception resolver đã cấu hình tự động log nguyên body khi JSON invalid.
- Nếu muốn trả 413 với payload lớn, đảm bảo **gateway/body limits và response semantics nhất quán**; không cần trả chi tiết lý do có chứa payload.
- Nếu báo cáo dùng **content type không có trong consumes**, Spring có thể trả 415. Cần test browser versions/collector contract thực.
- Không lưu JSON thô trong database/queue để phân loại lại sau; chỉ các ReducedCspReport mới rời khỏi xử lý request.

### 8.2. CSRF exemption cực hẹp cho Servlet

Nếu collector chung Spring MVC app có session-cookie authentication, cấu hình mẫu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain browserSecurity(HttpSecurity http)
        throws Exception {

    return http
        .cors(Customizer.withDefaults())
        .csrf(csrf -> csrf.ignoringRequestMatchers(request ->
            "POST".equals(request.getMethod())
                && "/__security/csp-report".equals(
                    request.getServletPath())))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.POST, "/__security/csp-report").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .build();
}
~~~

**Không dùng csrf.disable()**, không miễn CSRF trên /api/**. Exemption ở đây chỉ áp dụng **đúng POST collector**, vì browser report không đính kèm CSRF header của business app theo hợp đồng. CSRF cho login/logout/unsafe API vẫn phải được kiểm tra và giữ nguyên.

Nếu ứng dụng có Servlet context path hoặc proxy rewrite, **getServletPath() có thể không trùng public URL**. Integration test phải chứng minh exemption chỉ có trên đúng endpoint và không bị mở rộng do matcher sai. Đoạn cấu hình là một phần của SecurityFilterChain, còn authentication provider, login/logout, CORS source và headers phải được tích hợp phù hợp ứng dụng thật.

### 8.3. Không vô tình tạo session cho mọi CSP report

Collector không được gọi getSession() để log user hoặc thiết lập authentication. Nếu middleware khác tự tạo session cho anonymous report:

- Xem session creation policy và security chain phù hợp.
- Không dùng CSRF report làm lý do phát JSESSIONID.
- Đừng tự suy ra browser nào là authenticated từ Cookie header.
- Cân nhắc chuyển collector sang subdomain/origin riêng, không có business session cookie.
- Vẫn test CORS/report delivery với browser thực; Reporting API không phải Fetch request thông thường.

### 8.4. Tương tác với HTTP firewall và exception logging

Một báo cáo với path hoặc header malformed có thể bị **StrictHttpFirewall**/Servlet container chặn trước controller. Không mong ControllerAdvice của collector sẽ thấy tất cả HTTP 400. Không bật log exception.getMessage() trên RequestRejectedException để tìm báo cáo “bị mất”; điều đó có thể làm lộ URL/headers chưa tin cậy.

**HTTP 400 từ controller parse JSON** và **RequestRejectedException của firewall** là hai nguồn riêng. Chỉ dùng nhãn control=firewall khi có sự kiện xác nhận từ đường HttpFirewall tương ứng.

## 9. Reactive/WebFlux: giới hạn body mà không block event loop

Reactive app dùng **ServerHttpSecurity, SecurityWebFilterChain, ServerWebExchange**, HTTP server (thường Reactor Netty) và **WebSession**. Không copy HttpServletRequest hoặc Servlet HttpFirewall sang WebFlux.

### 9.1. WebFlux collector với DataBufferUtils.join có giới hạn

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
final class ReactiveCspReportController {

    private static final int MAX_BYTES = 16 * 1024;
    private final ObjectMapper mapper;
    private final MeterRegistry meters;
    private final CspReportNormalizer normalizer =
        new CspReportNormalizer();

    ReactiveCspReportController(
            ObjectMapper mapper, MeterRegistry meters) {
        this.mapper = mapper;
        this.meters = meters;
    }

    @PostMapping(
        path = "/__security/csp-report",
        consumes = {
            "application/csp-report",
            "application/reports+json"
        }
    )
    Mono<ResponseEntity<Void>> accept(
            ServerWebExchange exchange) {

        return DataBufferUtils.join(
                exchange.getRequest().getBody(), MAX_BYTES)
            .map(buffer -> {
                try {
                    byte[] bytes =
                        new byte[buffer.readableByteCount()];
                    buffer.read(bytes);

                    JsonNode root = mapper.readTree(bytes);
                    if (root == null) {
                        return ResponseEntity.badRequest()
                            .<Void>build();
                    }

                    for (ReducedCspReport event :
                            normalizer.reduce(root)) {
                        meters.counter(
                            "csp_reports_ingested_total",
                            "route_group", event.routeGroup(),
                            "directive", event.directive(),
                            "source_class", event.sourceClass(),
                            "disposition", event.disposition()
                        ).increment();
                    }

                    return ResponseEntity.noContent()
                        .<Void>build();
                } catch (IOException invalidJson) {
                    // Không log buffer hoặc raw exception message.
                    return ResponseEntity.badRequest()
                        .<Void>build();
                } finally {
                    DataBufferUtils.release(buffer);
                }
            })
            .switchIfEmpty(Mono.just(
                ResponseEntity.badRequest().<Void>build()))
            .onErrorResume(
                DataBufferLimitException.class,
                err -> Mono.just(ResponseEntity
                    .status(HttpStatus.PAYLOAD_TOO_LARGE)
                    .<Void>build()));
    }
}
~~~

**Tại sao giới hạn ở trước parse?** DataBufferUtils.join với **maxByteCount** không cho phép gom một body tùy ý vô hạn vào một buffer hợp nhất; khi vượt giới hạn, pipeline báo lỗi. Trong nhánh thành công cần **release DataBuffer**. Vẫn phải đặt body limits, timeouts và rate limits ở ingress/Netty/gateway; JSON parsing có depth/string constraints.

Đoạn ví dụ parse một payload nhỏ **trong event loop**; chỉ giữ các thao tác CPU nhỏ, không gọi blocking database, network hoặc filesystem IO ở đó. Khi cần queue/aggregation phức tạp, thiết kế async boundary được giới hạn dung lượng và chỉ truyền **reduced events**, không raw body.

### 9.2. Reactive CSRF exemption vẫn phải hẹp

Nếu collector nằm ngay trong Reactive browser app, có thể dùng ServerWebExchangeMatcher để loại **đúng POST report endpoint** ra khỏi default CSRF matcher:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CsrfWebFilter;
import org.springframework.security.web.server.util.matcher.AndServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.NegatedServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
SecurityWebFilterChain browserReactiveChain(
        ServerHttpSecurity http) {

    return http
        .csrf(csrf -> csrf.requireCsrfProtectionMatcher(
            new AndServerWebExchangeMatcher(
                CsrfWebFilter.DEFAULT_CSRF_MATCHER,
                new NegatedServerWebExchangeMatcher(
                    ServerWebExchangeMatchers.pathMatchers(
                        HttpMethod.POST,
                        "/__security/csp-report"
                    ))
            )))
        .authorizeExchange(auth -> auth
            .pathMatchers(
                HttpMethod.POST, "/__security/csp-report").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .build();
}
~~~

Đây là **mẫu cho Spring Security 6.x Reactive** và cần kiểm tra bằng WebTestClient trên version/BOM của dự án. Không dùng Servlet RequestMatcher ở đây. Giữ CSRF protection cho mọi unsafe browser API không được miễn cụ thể.

**Hãy kiểm thử POST /__security/csp-report thiếu token được chấp nhận nhưng POST /api/orders thiếu token bị chặn**. Nếu route hoặc proxy rewrite làm matcher rộng hơn dự định, phải sửa trước khi deploy.

### 9.3. Khi collector là dịch vụ riêng

Mô hình dễ kiểm soát hơn có thể là:

~~~text
app.example.com HTML  -> Reporting-Endpoints: collector.example.com
collector.example.com  -> no login session, no business API
api.example.com         -> Cookie/CSRF/CORS/authentication
~~~

Đặt collector ở origin khác **không tự động bảo đảm reports được gửi**: phải thử với Reporting API support, HTTPS, browser reporting restrictions, network permissions và nội dung header. Collector vẫn nhận untrusted data và cần đủ body/rate/retention limits.

### 9.4. Servlet và Reactive khác nhau ở đâu?

| Nhiệm vụ | Servlet | Reactive |
| --- | --- | --- |
| HTTP request | HttpServletRequest | ServerWebExchange |
| Bounded body read | InputStream với max bytes | DataBufferUtils.join(..., maxByteCount) |
| Security DSL | HttpSecurity | ServerHttpSecurity |
| CSRF filter | CsrfFilter | CsrfWebFilter |
| Exception matcher | Servlet RequestMatcher | ServerWebExchangeMatcher |
| Session | HttpSession | WebSession |
| Integration test | MockMvc | WebTestClient |
| HTTP parser | Servlet container | Reactor Netty/Reactive adapter |
| Dữ liệu được lưu | Reduced event/metric | Cùng reduced schema, nhưng pipeline khác |

**Cùng một privacy contract, khác cách triển khai.** Không đánh giá hệ thống an toàn chỉ vì một stack có controller đã hạn chế raw data.

## 10. Log bảo mật ngoài CSP: giữ tín hiệu nhưng không giữ credential

### 10.1. Nhãn control và reason hữu hạn

Một schema audit Spring Security có thể có:

~~~json
{
  "event": "http.security.denial",
  "control": "csrf",
  "reason": "invalid_or_missing_actual",
  "decision": "denied",
  "methodClass": "UNSAFE",
  "routeGroup": "orders",
  "statusClass": "4xx",
  "release": "r42",
  "requestId": "req-3f1a"
}
~~~

Các giá trị control nên là tập **csrf, authentication, authorization, firewall, cors, edge-waf, other**. Đừng gắn nhãn csrf chỉ vì status=403: gateway WAF, authorization và HTTP firewall cũng có thể trả 403. Tương tự, RequestRejectedException của Servlet firewall có thể nằm **trước MVC**, nên route template chưa có; dùng path group tĩnh hoặc unknown.

### 10.2. Log những gì ở CSRF denial?

Giữ:

- Request method đã chuẩn hóa và route group.
- Lý do xác nhận từ CsrfFilter/CsrfWebFilter khi handler thực sự thấy exception.
- Có header CSRF hay không dưới dạng Boolean **nếu cần**, không giá trị token.
- release/version, app/edge layer, outcome.
- Correlation ID riêng được kiểm soát nếu cần incident trace.

Không giữ expected token, actual token, raw/XOR representation, JSESSIONID, request body, query hoặc raw exception message. **MissingCsrfTokenException không tự chứng minh frontend thiếu header**; nó liên quan expected token path. Test category theo phiên bản thực.

### 10.3. Log những gì ở HTTP firewall?

Giữ **layer=spring-servlet-firewall**, method class, rejection category và policy revision **chỉ khi RequestRejectedHandler thực sự thấy RequestRejectedException**. Đừng ghi exception.getMessage(), request.getRequestURI() hoặc toàn bộ headers theo mặc định; URL có thể chứa dữ liệu nhạy cảm và ký tự control gây log injection.

WebFlux không dùng Servlet StrictHttpFirewall. Một HTTP 400 từ Netty/Reactive parser không tự động trở thành event spring-servlet-firewall; gateway/server phải có source-aware telemetry riêng.

### 10.4. CORS, HSTS, CSP và session

- **CORS:** Lưu trusted/untrusted origin **class**, requested header class và preflight outcome; không lưu arbitrary Origin string.
- **HSTS:** Ghi policy version và public HTTPS header check PASS/FAIL; không cần user identity.
- **CSP:** Directive, source class, route group và policy version; không script sample.
- **Cookie/session:** Ghi cookie attribute outcome và session-present Boolean; không Cookie/Set-Cookie value.
- **Authentication:** Ghi login success/failure category và flow stage, không password/JWT/refresh token.
- **Authorization:** Ghi denied policy group, không raw principal/email/subject.
- **Rate limit/WAF:** Ghi rule group/status class, không dump raw request-target.

Các sự kiện này thường đủ để phát hiện regressions sau deploy và phân biệt bảo vệ đang chặn đúng với lỗi tích hợp.

## 11. Kiểm thử: chứng minh raw data không thoát khỏi ranh giới

Một test trả HTTP 204 chỉ chứng minh endpoint nhận request; **không chứng minh URL/token đã bị loại trước khi vào log, metrics, queue và APM**. Bộ test phải có cả **privacy assertions** lẫn **security negative tests**.

### 11.1. Unit test normalizer với dữ liệu synthetic nhạy cảm

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;

class CspReportNormalizerTests {
    private final ObjectMapper mapper = new ObjectMapper();
    private final CspReportNormalizer normalizer =
        new CspReportNormalizer();

    @Test
    void rawUrlAndSampleAreNotRetained() throws Exception {
        String payload = """
            {
              "csp-report": {
                "document-uri":
                  "https://app.example.com/checkout/123?token=CANARY_SECRET",
                "blocked-uri":
                  "https://pay.example.net/js?v=CANARY_SECRET",
                "effective-directive": "script-src-elem",
                "disposition": "report",
                "script-sample": "CANARY_SECRET",
                "original-policy": "not-trusted"
              }
            }
            """;

        JsonNode parsed = mapper.readTree(payload);
        List<ReducedCspReport> reduced =
            normalizer.reduce(parsed);

        assertEquals(1, reduced.size());
        assertEquals("checkout", reduced.get(0).routeGroup());
        assertEquals("script-src-elem",
            reduced.get(0).directive());
        assertEquals("approved-payment-provider",
            reduced.get(0).sourceClass());

        assertFalse(reduced.toString().contains(
            "CANARY_SECRET"));
    }
}
~~~

**CANARY_SECRET là chuỗi giả do test tạo**, không phải JWT/CSRF token thật. Test kiểm tra **output DTO**, nhưng vẫn phải kiểm tra log capture, trace exporters, metrics, ingress access logs và DLQ. Một exception handler ngoài reducer vẫn có thể ghi raw input.

### 11.2. Test các nguồn dữ liệu sai shape, batch và origin

| Input | Điều kiện mong đợi |
| --- | --- |
| Reporting API type khác csp-violation | Bỏ qua, không lưu raw |
| Legacy không có csp-report object hợp lệ | Bỏ/drop theo contract |
| JSON array vượt MAX_BATCH | Reject/drop trước duyệt từng entry |
| documentURL chứa email/query/ID | Chỉ còn route group hữu hạn |
| documentURL sai host, HTTP hoặc userinfo | external-or-invalid |
| blockedURL là inline | source_class=inline |
| blockedURL đến host bất kỳ ngoài danh sách | external-other |
| effectiveDirective là chuỗi bất kỳ | directive=other |
| disposition lạ hoặc missing | unknown |
| sample chứa canary secret | Không rơi vào metrics/logs |
| Trường URL quá dài, URI parse lỗi | Trả invalid/other, không log exception message |
| JSON nested quá sâu hoặc body quá lớn | Giới hạn parser/body hoạt động |
| Cookie/Authorization trong request | Không trở thành sự kiện lưu trữ |

Các test phải **khẳng định sink cuối cùng không có raw data**, không chỉ assert đối tượng Java trong memory đã scrub.

### 11.3. MockMvc test endpoint nhận report nhưng business CSRF vẫn bật

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CspReportServletIntegrationTests {

    @Autowired MockMvc mvc;

    @Test
    void reportWithoutCsrfHeaderIsAccepted() throws Exception {
        mvc.perform(post("/__security/csp-report")
                .contentType("application/csp-report")
                .content("""
                    {"csp-report":{
                      "document-uri":"https://app.example.com/login",
                      "effective-directive":"script-src-elem",
                      "blocked-uri":"inline",
                      "disposition":"report"
                    }}
                    """))
            .andExpect(status().isNoContent());
    }

    @Test
    void unsafeBusinessPostStillRequiresCsrf()
            throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void oversizedReportDoesNotGetParsed()
            throws Exception {
        mvc.perform(post("/__security/csp-report")
                .contentType("application/csp-report")
                .content("x".repeat(17 * 1024)))
            .andExpect(status().isPayloadTooLarge());
    }
}
~~~

**Lưu ý:** Các test này giả định route/security chain đúng như phần 8.2. Với response policy hoặc middleware custom, status có thể khác theo contract; cần test chính xác kết quả đã duyệt. Để khẳng định CSRF không bị bypass, **assert database không đổi** khi unsafe business POST thiếu token.

Không dùng MockMvc **print()** hoặc HTTP trace dumping trong CI đối với response/request chứa token thật. Các payload ở đây là synthetic.

### 11.4. WebTestClient cho Reactive collector

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import org.springframework.http.MediaType;

// Trong WebFlux integration test context:
webTestClient.post()
    .uri("/__security/csp-report")
    .contentType(MediaType.parseMediaType(
        "application/csp-report"))
    .bodyValue("""
        {"csp-report":{
          "document-uri":"https://app.example.com/login",
          "effective-directive":"script-src-elem",
          "blocked-uri":"inline",
          "disposition":"report"
        }}
        """)
    .exchange()
    .expectStatus().isNoContent();

webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/orders")
    .bodyValue(java.util.Map.of("sku", "P100"))
    .exchange()
    .expectStatus().isForbidden();
~~~

WebTestClient không tự chứng minh giới hạn body ở **Reactor Netty/gateway** hoặc HTTP reporting được browser gửi thực tế. Thêm test **quá MAX_BYTES**, invalid JSON, timeout, callback **DataBuffer release** và các loại CSP reports từ browser mục tiêu.

### 11.5. Browser E2E cho Reporting API và fallback

Trong staging:

1. Tạo HTML document có **Content-Security-Policy-Report-Only** cùng report-to/report-uri theo contract.
2. Tạo một inline script **không có nonce/hash** để cố ý sinh violation; không dùng dữ liệu thật.
3. Xác minh browser vẫn chạy script trong giai đoạn Report-Only nếu không có Enforce baseline khác chặn nó.
4. Đối chiếu collector nhận **csp-violation** qua đúng cơ chế browser hỗ trợ.
5. Thử một policy **Enforce** riêng: script trái phép bị chặn và disposition được ghi nhận khi report gửi tới collector.
6. Kiểm tra collector chỉ có **reduced metrics**, không raw document URL/query hoặc script sample.
7. Nếu browser không gửi report do privacy setting/version/network, ghi **report delivery unsupported/unknown**, không kết luận rằng không có violation.
8. Kiểm tra CDN/gateway ở HTML origin thật, không chỉ header từ JSON API.

**Cùng lúc có hai headers Enforce và Report-Only** cần phân biệt policy nào thực thi. Một report-only policy không thay thế Enforce baseline đã có.

### 11.6. Synthetic canary để kiểm tra cả dữ liệu lẫn pipeline

Tạo request báo cáo giả ở **môi trường test** mang chuỗi như:

~~~text
test_canary=DO_NOT_PERSIST_006
documentURL=https://app.example.com/checkout/123?secret=DO_NOT_PERSIST_006
sample=DO_NOT_PERSIST_006
~~~

Sau đó quét **metrics, app logs, traces, queue, DLQ, ingress/WAF logs, APM và object backups** trong phạm vi test được cho phép:

- Collector nhận/giới hạn request theo contract.
- Reduced event chỉ chứa route_group/directive/source_class/disposition.
- Không tồn tại chuỗi canary trong persistent data.
- Không tạo request-ID hoặc metrics label từ chuỗi canary.
- Nếu có exception, error response không echo body.
- Khi cần retention/deletion, test time-to-delete thực.

Không dùng canary để quét dữ liệu production thật hoặc cố tình gửi credentials vào logs.

## 12. Logs, metrics và distributed tracing: áp allowlist ở mọi sink

### 12.1. Metrics low-cardinality

Những tên metrics sau là **đề xuất**, không phải tên được Spring Security tự phát:

~~~text
csp_reports_ingested_total{
  environment="prod",
  policy_revision="csp-v7",
  route_group="checkout",
  directive="script-src-elem",
  source_class="approved-payment-provider",
  disposition="report"
}

csp_reports_dropped_total{
  environment="prod",
  reason="invalid_json",
  collector_revision="r42"
}

security_denials_total{
  environment="prod",
  control="csrf",
  reason="invalid_or_missing_actual",
  route_group="orders"
}
~~~

**policy_revision phải được gắn từ trusted config/telemetry**, không từ originalPolicy do client POST. Các nhãn mới phải có **giới hạn số lượng giá trị**. Không phát một meter mới cho mỗi full URL, Host, referrer, IP hoặc user-agent.

### 12.2. Audit logs và traces

Một log sự kiện được duyệt:

~~~text
timestamp=...
event=http.security.denied
control=csrf
reason=invalid_or_missing_actual
route_group=orders
status=403
release=r42
request_id=req-8ae2
~~~

request_id dùng để correlate các tầng trong **logs có phân quyền**, không phải metric label. Nó phải là ID độc lập, không lấy từ Cookie, token hay raw query. Nếu cho client gửi request ID, phải giới hạn độ dài/ký tự và chống log injection; trusted gateway có thể sinh ID riêng.

Không đưa raw báo cáo vào:

- Span attributes hoặc span events trong distributed tracing.
- OpenTelemetry baggage truyền qua các services.
- Error breadcrumbs có URL/query.
- HTTP client instrumentation tự ghi Cookie/Authorization.
- Application event serialized rồi truyền tới bên thứ ba.
- Metrics exemplars chứa thông tin nhận dạng không theo chính sách.

Một trace có status 403 **không chứng minh đây là CSRF deny**; phải có nguồn phân loại từ đúng security handler. CORS, HTTP firewall, WAF và authorization là các control khác.

### 12.3. Giới hạn logging khi bật DEBUG hoặc TRACE

Chế độ DEBUG/TRACE trên Spring Security, HTTP client/server hoặc gateway có thể đưa request properties vào logs nhiều hơn dự định. Trong production:

1. Chỉ bật trong phạm vi **hẹp và có thời hạn** được duyệt.
2. Kiểm tra logger/appender không ghi credential, raw path/query hoặc report body.
3. Đặt redaction ở **nguồn phát log**, không chỉ ở dashboard.
4. Không bật wire dump/network payload logging cho route nhận CSP report.
5. Không cho exception handler render nguyên lỗi parser/URL chứa raw input.
6. Sau điều tra, tắt verbose logging và kiểm tra dữ liệu đã được lưu ở nơi nào.

### 12.4. Mẫu dashboard tốt hơn một bảng raw reports

| Dashboard | Các trường cần | Không cần |
| --- | --- | --- |
| CSP rollout | Policy version, disposition, directive, source class, route group | documentURL, script sample |
| Frontend regressions | Release, browser family, JS error rate, route group | Full user-agent, userId |
| Security denial | Control, reason, status class, release | CSRF token, Cookie, JWT |
| Collector health | Received/drop rate, 400/413/415/429, latency | Raw POST body |
| Privacy guardrail | Canary leak test PASS/FAIL, redaction version | Sensitive value bị rò |
| Drift | HTML CSP header revision theo region/host group | User navigation history |

Khi số reports tăng, đối chiếu **browser E2E và user flows**; một attacker có thể spam collector tạo báo cáo giả. Không mặc định volumes chính là số XSS attempts bị chặn.

## 13. Retention, kiểm soát truy cập và quy trình xóa

### 13.1. Data lifecycle theo loại, không một TTL cho tất cả

Ví dụ **ma trận tham khảo để tổ chức tự phê duyệt**, không phải quy định pháp lý chung:

| Dữ liệu | Retention gợi ý để thảo luận | Chủ sở hữu |
| --- | --- | --- |
| Raw CSP request body | **Không persist** | Collector/security engineering |
| Raw Cookie/JWT/CSRF token | **Không persist** | Tất cả services/observability |
| Reduced CSP events chi tiết | Ngắn, ví dụ tối đa 7 ngày nếu thật cần | Security/observability |
| CSP aggregate counters | Theo nhu cầu trend, ví dụ 30–90 ngày | SRE/security |
| Security denial logs đã scrub | Theo incident/SOC policy riêng | Security operations |
| Synthetic canary results | Theo release/QA policy, không chứa secret | QA/SRE |
| Incident evidence đã phê duyệt | Retention đặc thù vụ việc và nghĩa vụ pháp lý | Incident owner/legal/privacy |

**Các thời hạn chỉ mang tính minh họa.** Việc lưu giữ, xóa, sao lưu, xử lý dữ liệu cá nhân và bảo vệ quyền riêng tư phải phù hợp chính sách tổ chức và luật áp dụng. Không dùng bảng này như một kết luận pháp lý.

### 13.2. Quyền truy cập theo nhiệm vụ

- **Ứng dụng/collector:** Chỉ ghi counters hoặc reduced data, không quyền đọc toàn bộ kho security logs.
- **SRE:** Xem tình trạng ingestion, rate, drop, latency và policy drift.
- **Security:** Xem denial categories, canary/incident data theo quyền được duyệt.
- **Developer:** Xem dữ liệu tổng hợp để sửa CSP/front-end flow; không cần truy cập raw user traces.
- **External APM/SIEM vendor:** Chỉ nhận dữ liệu đã scrub, có scope và retention được review.
- **Auditor/incident responder:** Truy cập có lý do, giới hạn thời gian và audit trail.

Áp dụng mã hóa khi lưu và khi truyền, quản lý keys, rotation, sao lưu và kiểm tra quyền của dashboard/export. **Mã hóa không thay data minimization**: dữ liệu không cần thiết vẫn có thể bị lộ nếu quá nhiều người có quyền giải mã.

### 13.3. Xóa một bản ghi chưa chắc đã xóa mọi bản sao

Nếu trước đây collector đã ghi raw payload vào queue hoặc APM, cần kiểm kê:

1. Application/database logs.
2. CDN/WAF/gateway access logs và request sampling.
3. Traces, metrics exemplars và error event attachments.
4. Message queues, retry/dead-letter topics.
5. Object storage exports và dashboards.
6. Snapshots, backups và replicated regions.
7. Third-party monitoring vendors.
8. Local developer captures, HAR và support tickets.

Không tuyên bố dữ liệu đã được xóa hoàn toàn chỉ vì đã xóa một record ở primary database. Quy trình xóa/retention cần có bằng chứng và thời gian thực hiện theo policy.

### 13.4. Khi cần thông tin sâu hơn để điều tra

Không mở raw logs toàn hệ thống. Thiết kế **exception workflow**:

- Mục đích và loại sự cố đã xác minh.
- Owner, người phê duyệt, phạm vi routes/systems.
- Mức dữ liệu tối thiểu, không chứa credentials nếu tránh được.
- Truy cập tạm thời, logging về ai đã truy cập.
- Giới hạn lưu, thủ tục xóa và thời hạn kết thúc.
- Test bằng dữ liệu synthetic trước khi thu bất kỳ nội dung production nào.

Chỉ sử dụng cách thu phù hợp với chính sách bảo mật và pháp lý của tổ chức.

## 14. Runbook vận hành, cảnh báo và phản ứng khi dữ liệu bị lưu sai

### 14.1. Runbook A — CSP reports tăng đột biến sau frontend deploy

**Dấu hiệu:** Metrics CSP reports tăng theo route group hoặc source class khi vừa bật Report-Only/Enforce.

1. Gắn thời gian thay đổi với **frontend build, CSP policy revision, CDN/gateway config** và browser family.
2. Tách **report disposition** khỏi enforce; một policy Report-Only có thể chỉ tạo cảnh báo mà không chặn script.
3. Xem directive category, route group và source class đã giảm dữ liệu; **không dump originalPolicy/documentURL/script sample**.
4. So với browser E2E, client JavaScript error rate và các flow login/checkout/profile.
5. Xác minh nguồn bị chặn có phải dependency đã được review; browser extensions và bot reports có thể tạo noise.
6. Nếu flow hợp lệ bị CSP Enforce chặn, stop canary hoặc rollback policy/artifact theo quy trình.
7. Nếu chỉ có báo cáo từ nguồn lạ, không tự thêm wildcard/unsafe-inline vào CSP.
8. Kiểm tra report collection availability/rate limiter có làm méo dữ liệu hay không.
9. Sau remediation, xác minh collector vẫn không lưu raw input và báo cáo canary còn đến được.

**Một spike CSP không tự chứng minh XSS thật hoặc attack rate.** Báo cáo là dữ liệu low-trust, có thể bị giả.

### 14.2. Runbook B — Reports bằng 0 nhưng browser có CSP violations

**Dấu hiệu:** DevTools báo CSP block/report nhưng metrics collector không tăng.

1. Kiểm tra HTML document thực sự có Reporting-Endpoints, report-to và/hoặc report-uri đúng format.
2. Phân biệt CSP Enforce với Report-Only; test trên HTML origin, không chỉ JSON API.
3. Kiểm tra browser version, privacy settings và khả năng hỗ trợ Reporting API.
4. Test synthetic violation ở staging với HTTPS endpoint, không dùng credential thật.
5. Xem status 400/413/415/429 từ gateway/collector và drop counters.
6. Kiểm tra CSP reporting endpoint đã được công bố đúng hostname/path và TLS hợp lệ.
7. Xem WAF/ingress hoặc client network có chặn reporting requests không.
8. Xem collector có bỏ báo cáo vì parser sai format hoặc max-batch limit không.
9. Kết luận **telemetry unavailable/insufficient evidence** nếu chưa xác minh, không kết luận vi phạm bằng 0.

### 14.3. Runbook C — Token, Cookie hoặc dữ liệu cá nhân xuất hiện trong SIEM/APM

**Dấu hiệu:** Một truy vấn log hoặc alert phát hiện chuỗi giống JWT/JSESSIONID, reset link, CSRF token hoặc email nằm trong CSP report/HTTP debug log.

1. **Ngừng hoặc hạn chế nguồn capture gây lộ** và giới hạn quyền tới sink liên quan.
2. Tránh dán raw payload vào issue/chat/email; dùng request ID đã scrub và mô tả loại dữ liệu.
3. Xác định dữ liệu thuộc loại credential, CSRF token đơn lẻ, PII hay business secret; đánh giá ngữ cảnh.
4. Xác định phạm vi: ingress/WAF, app logs, traces, queues, metrics, DLQ, backups, vendor exports.
5. Nếu session/refresh/JWT credentials bị lộ, cân nhắc **revocation/rotation** theo incident policy; không đồng nhất mọi CSP token lộ với chiếm quyền phiên.
6. Sửa nơi phát sinh bằng **allowlist schema và tắt body/header capture**, không chỉ ẩn dữ liệu trên dashboard.
7. Làm việc với data owner/privacy/legal về retention, cleanup và nghĩa vụ báo cáo nếu có.
8. Chạy lại synthetic canary cho Servlet/Reactive/edge để chứng minh dữ liệu không bị thu tiếp.
9. Ghi postmortem với owner, policy revision, coverage của các sinks và cách phòng tái diễn.

**Không tuyên bố xóa xong** nếu vẫn còn bản sao ở object storage, backups hoặc APM vendor ngoài tầm kiểm soát.

### 14.4. Runbook D — CSP collector bị spam hoặc JSON payload bất thường

**Dấu hiệu:** CPU tăng, latency/queue backlog tăng, nhiều POST báo cáo lớn hoặc malformed JSON.

1. Xem rate/size/time metrics, response class 2xx/4xx/413/415/429, nhưng không ghi raw requests.
2. Áp gateway/body size limit và rate limits đã review; bảo vệ normal traffic khỏi false positives.
3. Xác minh parser có giới hạn max bytes, nesting depth, string length và batch entries.
4. Kiểm tra memory/GC và Reactive event loop không bị blocking hoặc buffering vô hạn.
5. Kiểm tra queue bounded capacity, không có raw body ở DLQ/retry.
6. Dùng quota/drop counters thay vì ghi mỗi malformed report vào warning log.
7. Không tắt CSP Enforce chỉ vì collector đang quá tải; CSP protection và reporting availability là các vấn đề khác nhau.
8. Nếu cần giảm tải, ưu tiên **sampling/drop reporting data** có kiểm soát, không làm yếu browser policy.
9. Sau khi khôi phục, thử synthetic normal/oversized cases và so business SLO.

### 14.5. Runbook E — Prometheus/cardinality tăng bất thường

**Dấu hiệu:** Số time series tăng quá nhanh sau khi thêm blocked-uri, path hoặc User-Agent vào labels.

1. Dừng phát nhãn dynamic trong instrumentation; giữ nhãn finite đã duyệt.
2. Chuyển full URL thành source class và route group.
3. Kiểm tra Metrics/Observation filters có ghi raw exception messages không.
4. Ước tính ảnh hưởng tới metrics storage, dashboards và retention.
5. Sửa schema và quay lại policy revision trước; không cố “hash URL” rồi tiếp tục phát một series cho mỗi URL.
6. Xác minh security incident evidence vẫn có mặt ở aggregate counters, không vô tình bỏ toàn bộ tín hiệu.
7. Chạy load test với nhiều URLs synthetic khác nhau: số series mới phải **không tăng tuyến tính theo URLs**.

### 14.6. Runbook F — Ngoại lệ CSP reporting vô tình bỏ CSRF trên API khác

**Dấu hiệu:** Sau khi triển khai collector, browser POST nghiệp vụ thiếu token bất ngờ trả 2xx hoặc tạo side effect.

1. **Stop rollout/traffic** theo mức độ, coi đây là vấn đề bảo vệ CSRF nghiêm trọng.
2. Kiểm tra CSRF exception matcher trên Servlet/Reactive: có đang ignore path prefix rộng không?
3. Kiểm tra gateway rewrite/context path khiến matcher nhận diện sai không.
4. Kiểm tra nhiều SecurityFilterChain/ServerHttpSecurity chains và chain ordering.
5. Chạy negative test POST /api/orders thiếu token, test dữ liệu không đổi.
6. Khôi phục matchers hẹp chỉ POST collector, giữ authorization cho API khác.
7. Rerun browser/login/logout, CORS preflight và collector ingestion tests.
8. Viết regression test cố định và kiểm lại rollout canary trước mở rộng.

**Bỏ CSRF toàn cục không phải giải pháp cho CSP reporting.** Một collector thực hiện telemetry ẩn danh không làm thay đổi security boundary của browser business endpoints.

### 14.7. Runbook G — Sai lệch giữa Servlet, Reactive và gateway sau migration

**Dấu hiệu:** Cùng CSP report format, một service nhận 204 còn service khác trả 415/413 hoặc ghi raw body.

1. Xác định ứng dụng dùng **Servlet hay WebFlux** và version/binder/body readers.
2. So Content-Type support application/csp-report và application/reports+json.
3. So max bytes, max batch, rate limits, error handling, JSON depth constraints.
4. Xác minh Servlet InputStream và Reactive DataBuffer đều release/bounded.
5. So logger/APM instrumentation của từng service; không copy Servlet filter sang WebFlux.
6. Test cùng synthetic input qua edge → service A/B và kiểm kết quả cuối của metrics.
7. Thống nhất **reduced data schema**, không nhất thiết cùng code parser implementation.
8. Canary migration theo region/release; có fallback/rollback không mất CSP protection.

### 14.8. Runbook H — Dữ liệu bảo mật thiếu khiến điều tra khó

Không phản ứng bằng cách bật raw logs vô thời hạn. Thay vào đó:

- Xác nhận **câu hỏi điều tra**: route nào bị CSP block, token bootstrap có lỗi, hay WAF từ chối?
- Tìm các trường **đã có**: directive, source class, release, route group, disposition, request ID độc lập.
- Tái hiện bằng test account và synthetic inputs trong staging.
- Cần thêm một field? Thực hiện **privacy review, data-classification, new schema test, TTL và access approval**.
- Nếu thật sự cần chi tiết production, sử dụng controlled incident evidence workflow đã được duyệt, không thay mặc định toàn hệ thống.

### 14.9. Cây quyết định khi phát hiện CSP/HTTP security anomaly

~~~mermaid
flowchart TD
    A["CSP report/log security anomaly"] --> B{"Có dữ liệu nhạy cảm đã persist?"}
    B -->|Có| C["Contain source, access và retention incident"]
    B -->|Không| D{"Reporting pipeline hoạt động?"}
    D -->|Không| E["Kiểm tra browser support, endpoint, size/rate limits"]
    D -->|Có| F{"Business flow bị ảnh hưởng?"}
    F -->|Có| G["Triage CSP/CORS/CSRF/JS, rollback nếu cần"]
    F -->|Không| H["Classify reports + security review"]
    C --> I["Fix allowlist, scrub, canary retest"]
    E --> I
    G --> I
    H --> I
~~~

Một sự cố có thể gồm nhiều nguyên nhân: collector bị bot spam, trong khi frontend thật bị CSP Enforce chặn payment script. Dùng **bằng chứng đa tầng** trước khi quyết định.

## 15. Bài tập thực hành

**Bài A — Map dữ liệu nhạy cảm:** Vẽ đường đi CSP report từ browser qua CDN/WAF, Spring collector, metrics, logs, tracing, queue và dashboard. Ghi rõ raw fields có thể bị lưu ở đâu.

**Bài B — Hai format CSP:** Tạo synthetic report-uri application/csp-report và Reporting API application/reports+json. Viết parser đưa về một DTO hữu hạn, không dựa vào sample/referrer.

**Bài C — URL classification:** Test URL có email/query/ID, URL ngoài origin, malformed URL và URL quá dài. Chứng minh chỉ các route groups tĩnh được lưu.

**Bài D — Ngăn cardinality explosion:** Gửi 1.000 synthetic blocked URLs khác nhau vào normalizer. Xác minh số metric label combinations vẫn hữu hạn.

**Bài E — Report-sample:** Bật report-sample trong staging có dữ liệu synthetic và quan sát payload. Giải thích vì sao sample không nên lưu ở production và cách dùng source maps thay thế.

**Bài F — Servlet collector:** Viết InputStream receiver giới hạn bytes, parse JSON có constraints, chỉ emit reduced events và không log request body.

**Bài G — Reactive collector:** Dùng DataBufferUtils.join có maxByteCount, release buffer, tránh blocking IO, test overflow và malformed JSON bằng WebTestClient.

**Bài H — CSRF ngoại lệ hẹp:** Test POST collector không cần token nhưng POST nghiệp vụ cookie-auth thiếu token bị 403 và không có side effect. Thực hiện trên Servlet và Reactive.

**Bài I — APM redaction:** Đưa canary secret giả vào documentURL, sample, Cookie test và error payload trong staging. Kiểm tra APM/traces/logs/DLQ không có giá trị đó.

**Bài J — Collector abuse:** Gửi batch vượt giới hạn, JSON nested quá sâu, nhiều malformed requests. Chứng minh rate/body limits giảm tải mà không ảnh hưởng CSP policy Enforce.

**Bài K — Reporting support:** Test một browser mới và một browser có mức hỗ trợ cũ, phân biệt report-to và report-uri; không coi báo cáo bằng 0 là bằng chứng không có lỗi.

**Bài L — Retention:** Thiết kế data inventory và xóa thử một dữ liệu synthetic qua database, queue, metrics, object exports, backups và vendor APM theo policy.

**Bài M — Incident tabletop:** Giả định sau release CSP reporter bắt đầu log JSESSIONID và script-sample có PII. Lập thứ tự containment, quyền truy cập, rotation khi cần, deletion và chứng cứ kiểm thử.

**Bài N — Rollout gate:** Thiết kế CI/CD gate kết hợp browser CSP fixture, collector availability, canary redaction test và CSRF negative test, chặn rollout khi một gate trọng yếu FAIL.

## 16. Checklist triển khai và nguyên tắc cần nhớ

### 16.1. Checklist trước khi đánh dấu PASS

| Hạng mục | Điều kiện PASS |
| --- | --- |
| **Scope** | Biết HTML origin phát CSP và nơi nhận report |
| **Policy** | Report-Only/Enforce được gắn đúng, không vô tình nhân đôi Enforce |
| **Report mechanisms** | report-to/Reporting-Endpoints và report-uri fallback được test theo browsers |
| **Data inventory** | Liệt kê browser, edge, WAF, Spring, APM, queue, metrics, backups |
| **Allowlist schema** | Chỉ giữ route group/directive/source class/disposition/revision hữu hạn |
| **URL/privacy** | documentURL/blockedURL/referrer/query/raw path không persist |
| **Sample** | Không lưu script-sample, hạn chế report-sample khi chưa review |
| **Credentials** | Không Cookie, JWT, refresh, CSRF/XSRF, password trong logs/traces |
| **Input limits** | Max bytes, JSON depth/string, batch count, rate và timeouts |
| **Collector output** | Không echo payload hoặc error stack/raw exception message |
| **Servlet** | Bounded read, HttpSecurity exception matcher rất hẹp |
| **Reactive** | Bounded DataBuffers, release, ServerHttpSecurity matcher đúng |
| **Business CSRF** | POST nghiệp vụ thiếu token bị chặn, không side effect |
| **CORS/cookie** | Trusted browser flows vẫn hoạt động, session không bị lộ |
| **Metrics** | Low-cardinality labels, không URL/IP/request ID làm metric labels |
| **Tracing** | Không request/response body, token hoặc raw report trong spans/baggage |
| **Logging** | Allowlist trước sink; DEBUG/TRACE có kiểm soát |
| **Retention** | TTL và quyền đã phê duyệt; backup/vendor exports được kiểm kê |
| **QA** | MockMvc/WebTestClient, browser fixture, synthetic redaction canary PASS |
| **Monitoring** | Collector drop/ingest rate, data-leak tests và frontend SLO |
| **Incident** | Runbook contamination/DoS/CSRF-bypass và rollback owner rõ |

### 16.2. Mười hai nguyên tắc cốt lõi

1. **CSP report là input không tin cậy**, không phải bằng chứng đã được xác thực từ browser.
2. **Report-Only và Enforce khác nhau**; reporting không thay thế CSP enforcement.
3. **URL, referrer và script sample có thể chứa secrets/PII**, kể cả khi browser đã cắt bớt chi tiết cross-origin.
4. **Thu ít từ đầu** tốt hơn lưu raw rồi chỉ che dữ liệu trong dashboard.
5. **Allowlist output fields và enum hữu hạn**; unknown URL/host chuyển thành other, không dùng raw fallback.
6. **Không dùng hash như mặc định thay cho data minimization** với token, user IDs hoặc URLs.
7. **Giới hạn body, JSON parser, batch và rate trước persistence**, ở cả gateway/server và ứng dụng.
8. **Collector có thể cần miễn CSRF hẹp**, nhưng business POST vẫn phải được CsrfFilter/CsrfWebFilter bảo vệ.
9. **Servlet và Reactive có pipeline đọc body khác nhau**, cùng áp dụng privacy contract.
10. **Security logs cần source-aware classification**, không coi mọi 400/403 là firewall/CSRF.
11. **Metrics, traces, APM, queues và backups cũng là nơi lưu dữ liệu**, không chỉ database.
12. **Retention, access và incident response phải được thiết kế trước rollout**, có synthetic canary xác minh.

**Kết luận:** Giới hạn dữ liệu trong CSP reports và security logs không phải xóa vài trường ở cuối pipeline. Đó là thiết kế **browser policy → bounded ingestion → reduce trong memory → emit schema hữu hạn → control access/retention → kiểm thử redaction liên tục**. Khi thực hiện đúng, đội vận hành vẫn thấy được CSP violations, CSRF/CORS failures, HTTP firewall rejects và session regressions mà không biến logs/metrics thành kho chứa credential và thông tin riêng tư của người dùng.

## Tài liệu tham khảo chính thức và bổ trợ

- [MDN — Content Security Policy và Reporting](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only)
- [MDN — report-uri directive và payload/field security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-uri)
- [MDN — report-to directive và Reporting API payload](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-to)
- [MDN — Reporting-Endpoints header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Reporting-Endpoints)
- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [Spring Security 6.5 — Servlet Security Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Reactive Security Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — HTTP Firewall](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)



