# Đối chiếu header thực tế sau mỗi lần triển khai

## Mục tiêu, phạm vi và kết quả học tập

Trong chương **Vận hành và giám sát** của module **SPRING_SECURITY_HTTP_PROTECTION**, các lớp bảo vệ HTTP của Spring Security — **CSRF, CORS, security headers, Content Security Policy (CSP), HTTP Strict Transport Security (HSTS), HTTP firewall và session** — chỉ có giá trị khi cấu hình mong muốn thực sự đến được **trình duyệt hoặc client đích**.

Một bean **SecurityFilterChain** đúng không đồng nghĩa response mà người dùng nhận cũng đúng. Load balancer, API gateway, ingress, CDN, web server tĩnh, cache, các phiên bản pod khác nhau, rewrite rules và cơ chế TLS termination đều có thể **thêm, xóa, ghi đè, nhân đôi hoặc thay đổi** HTTP headers. Vì vậy sau mỗi lần triển khai, đội vận hành phải **đối chiếu expected policy với actual response headers** trên những tuyến quan trọng, không chỉ xác nhận ứng dụng khởi động và trả 200.

Bài học này là một quy trình có thể đưa vào **CI/CD, synthetic monitoring và runbook**. Các ví dụ có cả **Servlet** và **Reactive/WebFlux**, cùng kiểm tra HTTP từ origin, reverse proxy, public HTTPS edge và DevTools trong browser.

Sau bài học, người học có thể:

1. Xây dựng một **header contract** theo host, route, phương thức, origin, trạng thái xác thực và mã HTTP.
2. Phân biệt header được cấu hình trong Spring với header **thực sự xuất hiện trên response public**, và biết xác định tầng gây sai lệch.
3. Kiểm tra HSTS, CSP, chống MIME sniffing, framing, Referrer-Policy, caching và thuộc tính Set-Cookie.
4. Kiểm chứng CORS bằng cả **OPTIONS preflight** và **request thực**, không dựa vào một lần curl GET thành công.
5. Kết hợp kiểm tra header với **CSRF filter** và authorization: có header đúng chưa chứng minh request giả mạo bị chặn.
6. Viết kiểm thử **MockMvc/WebTestClient**, shell smoke tests và synthetic probes có cảnh báo không làm lộ token/session.
7. Thiết lập deployment gate, phát hiện drift giữa pod và edge, xử lý rollback và điều tra sự cố.
8. Phân biệt các trường hợp header **bắt buộc, tùy điều kiện, không áp dụng hoặc bị cấm** để giảm false positive.

## 1. Bài toán: cấu hình trong code khác response ở production

Xét một hệ thống thực tế:

~~~mermaid
flowchart LR
    A["Browser tại app.example.com"] -->|HTTPS| B["CDN / public edge"]
    B --> C["Ingress / API gateway"]
    C --> D["Spring Security app"]
    D --> E["SecurityFilterChain hoặc SecurityWebFilterChain"]
    E --> D
    D --> C
    C --> B
    B -->|Final response headers| A
~~~

Một request đến **https://api.example.com/api/csrf** có thể trải qua nhiều chặng:

- Spring Security gắn **Cache-Control: no-store**, X-Content-Type-Options và các security headers theo cấu hình.
- API gateway có thể đặt lại CORS headers dựa trên Origin hoặc chặn OPTIONS.
- Ingress có thể xử lý X-Forwarded-Proto sai, khiến backend nhầm HTTPS thành HTTP.
- CDN có thể cache một JSON response chứa CSRF token nếu một rule cache-by-URL ghi đè chính sách.
- Browser có thể không nhận cookie vì SameSite/Domain/Secure, dù response chứa Set-Cookie.
- Trang SPA HTML nằm trên **app.example.com**, nên CSP từ API ở **api.example.com** không tự bảo vệ document được serve ở frontend origin.
- Một deployment canary có thể dùng phiên bản Spring Security khác hoặc một config revision khác những pod còn lại.

**Không có một câu lệnh kiểm tra header duy nhất cho mọi trường hợp.** Cần có ma trận yêu cầu, điểm đo, điều kiện gửi request và cách diễn giải kết quả.

### 1.1. Ba câu hỏi cho mỗi header

1. **Header này có được kỳ vọng trên loại response này không?** Ví dụ HSTS cần kiểm tra trên public HTTPS; CSP có ý nghĩa trọng tâm trên response phục vụ HTML document, không phải cứ JSON đều phải có một CSP giống HTML.
2. **Giá trị cần khớp chính xác hay chỉ thỏa predicate?** CSP thường phải so policy đã duyệt, trong khi Cache-Control có thể chứa nhiều directives và chỉ cần xác minh no-store; Set-Cookie cần kiểm tra từng cookie và thuộc tính.
3. **Header quan sát từ đâu?** MockMvc từ ứng dụng, curl từ public edge, hoặc DevTools browser trong một ngữ cảnh cookie/CORS cụ thể có thể cho kết quả khác.

### 1.2. Đối chiếu không phải chỉ nhìn header tồn tại

Ví dụ cùng có header **Content-Security-Policy**:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'
~~~

và:

~~~http
Content-Security-Policy: default-src * 'unsafe-inline'; object-src *
~~~

đều “có CSP”, nhưng mức độ bảo vệ và nguy cơ khác rất nhiều. Tương tự:

- **Strict-Transport-Security: max-age=0** không tương đương một HSTS policy yêu cầu max-age dài.
- **Access-Control-Allow-Origin: *** không hợp lệ cho credentialed Fetch khi frontend gửi credentials include.
- **Set-Cookie** có HttpOnly nhưng thiếu Secure khác policy production đòi cả hai.
- **Cache-Control: no-cache** không thay cho **no-store** nếu endpoint trả token theo phiên.
- Hai header Access-Control-Allow-Origin khác nhau không được coi là “an toàn hơn”; browser có thể từ chối response vì cú pháp sai.

## 2. Thiết lập source of truth: header contract có version

Đội vận hành cần một **bảng expected policy được duyệt**, không kiểm thử dựa trên trí nhớ hoặc chụp một response bất kỳ làm chuẩn.

### 2.1. Phân loại theo context và trạng thái

| Context | Header/policy cần xác minh | Điều kiện quan trọng |
| --- | --- | --- |
| **HTML document qua HTTPS** | CSP, chống framing, nosniff, Referrer-Policy, HSTS | Kiểm tra tại origin **phục vụ HTML** |
| **GET /api/csrf** | Cache-Control no-store, Content-Type JSON, CORS nếu khác origin | Session/token theo phiên, **không cache công khai** |
| **POST /api/orders thành công** | CORS cho trusted SPA; cache policy phù hợp; không phản chiếu token | Phải có CSRF header và authentication hợp lệ |
| **POST thiếu CSRF token** | HTTP 403 và CORS hợp lệ cho trusted origin khi cần | **Không có side effect**; không trả token trong lỗi |
| **401/403 do authn/authz** | Security headers theo policy, CORS khi request từ trusted SPA | Không biến 401/403 thành lỗi CORS mơ hồ |
| **Preflight OPTIONS** | Allow-Origin, Allow-Methods, Allow-Headers, Allow-Credentials khi dùng cookie | OPTIONS thường **không mang session cookie** |
| **POST /login hoặc /logout** | Cookie attributes, CORS, redirects và CSRF lifecycle | Kiểm tra đường URL thực, không chỉ /api/** |
| **Static JS/CSS có hash/version** | Cache-Control công khai dài hạn nếu chủ đích; nosniff | Không áp no-store máy móc cho assets immutable |
| **Actuator/internal endpoint** | Không public nếu không được phép; no-store với thông tin nhạy cảm | Network/AuthN/AuthZ quan trọng hơn header |
| **Response redirect** | Location HTTPS đúng host, HSTS theo HTTPS context, cookie nếu có | Không tạo redirect sang HTTP/host ngoài ý muốn |

Không phải header nào cũng bắt buộc ở mọi context. Đối với một SPA được phục vụ từ CDN khác origin với API, **header CSP cần kiểm tra trên response HTML của CDN**, còn CORS có credentials cần kiểm tra ở response API.

### 2.2. Bốn loại tiêu chí expected

- **REQUIRED**: phải có và đạt giá trị được duyệt, ví dụ no-store trên JSON CSRF bootstrap.
- **FORBIDDEN**: không được xuất hiện hoặc không được dùng giá trị này, ví dụ wildcard Allow-Origin với credentials hoặc cookie session thiếu HttpOnly.
- **CONDITIONAL**: chỉ kiểm tra khi đủ điều kiện, ví dụ HSTS trên HTTPS public, Set-Cookie khi thực sự cấp hoặc thay cookie.
- **NOT_APPLICABLE**: không đánh fail khi cơ chế không liên quan, ví dụ không đòi Access-Control-Allow-Credentials cho native Bearer-only API vốn không phục vụ browser credentialed requests.

Mỗi rule cần có **owner, môi trường, host/route, method, expected value/predicate, mức độ nghiêm trọng, version, thời điểm áp dụng**. Khi thay đổi CSP/CORS/HSTS, thay cả contract và test cùng pull request, không âm thầm sửa expected thành trạng thái đang lỗi.

### 2.3. Ví dụ biểu diễn contract trong tài liệu vận hành

~~~yaml
policyRevision: "web-protection-v4"
environment: "prod"
checks:
  - id: public-html-csp
    target: "https://app.example.com/"
    method: GET
    expects:
      contentSecurityPolicy: "approved-policy-for-html"
      referrerPolicy: "strict-origin-when-cross-origin"
      frameAncestors: "'none'"
  - id: api-csrf-no-store
    target: "https://api.example.com/api/csrf"
    method: GET
    expects:
      cacheControlContains: "no-store"
      contentType: "application/json"
  - id: trusted-cors-preflight
    target: "https://api.example.com/api/orders"
    method: OPTIONS
    requestOrigin: "https://app.example.com"
    requestMethod: POST
    requestHeaders: ["content-type", "x-csrf-token"]
    expects:
      allowOrigin: "https://app.example.com"
      allowCredentials: "true"
~~~

Đây là **contract minh họa để thiết kế test**, không phải file config Spring Boot hay một tool có sẵn. **Không thêm token thật, cookie thật hoặc access credentials vào contract**. Khi chuyển thành automated tests, cần mã hóa rõ trường expected nào là exact, chứa directive, hoặc có điều kiện.

### 2.4. Đối chiếu policy cùng release manifest

Header contract nên đi kèm:

~~~text
artifact digest       = sha256:<build-digest>
spring security set   = BOM/version đã kiểm chứng
application config    = Git revision
ingress/CDN policy    = infrastructure revision
header contract       = approved policy revision
deployment target     = environment + hostname
~~~

Các placeholder này không phải secret, nhưng manifest phải được đặt trong hệ thống vận hành có quyền truy cập phù hợp. Một canary rollback mà vẫn giữ CDN policy mới có thể trả header khác release cũ; phải xác minh **cả code và hạ tầng**.

## 3. Checklist header: ngữ nghĩa và giới hạn thực tế

| Header | Nên kiểm tra điều gì? | Sai lầm thường gặp |
| --- | --- | --- |
| **Strict-Transport-Security** | Trên HTTPS public, max-age đủ, includeSubDomains/preload chỉ theo quyết định đã duyệt | Có header max-age=0 nhưng vẫn báo PASS |
| **Content-Security-Policy** | Directive thực sự giới hạn nguồn; không mở wildcard/unsafe-inline vô tội vạ | Chỉ check tồn tại, không kiểm tra giá trị |
| **Content-Security-Policy-Report-Only** | Có mục tiêu quan sát trước enforce, endpoint report phù hợp | Coi report-only là policy đang được browser enforce |
| **X-Content-Type-Options** | Giá trị nosniff | Chấp nhận mọi chuỗi không rỗng |
| **X-Frame-Options** | DENY/SAMEORIGIN khi còn dùng theo browser support | Dùng ALLOW-FROM lỗi thời hoặc lẫn với CSP frame-ancestors |
| **Referrer-Policy** | Giá trị phù hợp dữ liệu URL và nhu cầu ứng dụng | no-referrer cho mọi trang mà không xét analytics, hoặc mở unsafe-url |
| **Cache-Control** | no-store ở response chứa CSRF token/session data | Chỉ có no-cache, max-age=0 hoặc Vary và tưởng không lưu |
| **Set-Cookie** | Secure, HttpOnly, SameSite, Domain, Path, expiry theo loại cookie | Chỉ thấy Set-Cookie mà không kiểm tra attributes |
| **Access-Control-Allow-Origin** | Exact trusted Origin ở credentialed response | Wildcard, phản chiếu tùy tiện, header trùng |
| **Access-Control-Allow-Credentials** | true khi cho trusted browser gửi credentials | Dùng true mà Allow-Origin vẫn wildcard |
| **Access-Control-Allow-Headers** | Cho custom CSRF/Authorization/Content-Type cần thiết | Quên x-csrf-token gây preflight fail |
| **Access-Control-Allow-Methods** | Chỉ method được hỗ trợ/cho phép trong preflight | Hiểu nhầm nó thay authorization cho POST |
| **Vary** | Origin hoặc headers preflight cần thiết khi responses khác nhau | Dùng Vary như cách thay CSRF hoặc no-store |
| **Location** | Redirect về HTTPS host tin cậy, không rò secret | Redirect sau login tạo HTTP URL |
| **Cross-Origin-Opener-Policy** | Chỉ áp khi ứng dụng cần isolation được kiểm thử | Bật same-origin máy móc rồi phá OAuth/popup |
| **Cross-Origin-Embedder-Policy/CORP** | Chỉ theo yêu cầu isolation và tài nguyên được cấp quyền | Bật mà không kiểm tra CDN/fonts/iframe |

**Không có một bộ “tất cả headers phải tồn tại” đúng cho mọi API và mọi frontend.** Nên kiểm tra chính xác từng **header contract** theo chức năng và browser security model.

### 3.1. Một số nuance không được bỏ qua

- Tên HTTP header **không phân biệt chữ hoa/chữ thường**. HTTP/2 và HTTP/3 thường hiển thị tên lowercase; test phải so tên theo semantics thay vì string exact-case.
- Header trùng có semantics khác nhau. **Set-Cookie** có thể xuất hiện nhiều lần và không được nối bừa bằng dấu phẩy; **Access-Control-Allow-Origin** nhân đôi có thể làm browser từ chối; **CSP nhiều policies** thường được cùng áp dụng theo giao nghĩa của browser, không phải lấy policy “mở nhất”.
- **HSTS chỉ được browser xử lý từ HTTPS response hợp lệ**. Kiểm tra HTTP nội bộ phía sau TLS termination không thay việc kiểm tra HTTPS public.
- **X-Frame-Options** và **CSP frame-ancestors** không đồng nhất; frame-ancestors cần được gửi trên response cần bảo vệ khỏi bị nhúng, không nằm trong meta tag.
- **CORS** không phải hệ thống authentication. Curl có thể nhận response dù browser sẽ từ chối JavaScript đọc nó.
- **Cookie SameSite và Secure** điều chỉnh browser gửi cookie, không phải giá trị CORS; credentialed Fetch cần cả browser credentials mode và chính sách server/cookie.
- **Content-Type** và nosniff quan trọng khi API trả JSON/script/static assets; một response trả sai MIME có thể gây lỗi hoặc tăng rủi ro.
- **Cache-Control no-store** không tự cấu hình CDN custom cache rules hoặc tắt APM/body logging.

## 4. Thiết lập ma trận request: cùng URL nhưng khác status/Origin/session

Một test GET trả 200 với header đúng chỉ là một điểm dữ liệu. Cần thay **method, status, cookie, Origin, phiên bản và đường đi**.

### 4.1. Ma trận chuẩn nên có

| Probe | Method và đường | Ngữ cảnh | Phải chứng minh |
| --- | --- | --- | --- |
| P1 | GET / HTML | Anonymous, public HTTPS | CSP/HSTS/nosniff/frame/referrer policy |
| P2 | GET /api/csrf | Anonymous, chưa có session | no-store, có thể cấp token/session đúng |
| P3 | GET /api/csrf | Authenticated | no-store, cookie/session không rò vào cache |
| P4 | OPTIONS /api/orders | Trusted Origin, không Cookie | preflight CORS thành công trước authentication |
| P5 | OPTIONS /api/orders | Untrusted Origin | Không cấp quyền đọc credentialed response |
| P6 | POST /api/orders | Cookie session, thiếu CSRF | 403, **không side effect** |
| P7 | POST /api/orders | Cookie session, CSRF đúng | Authorization và business validation hoạt động |
| P8 | GET /api/me | Session hết hạn | 401/redirect đúng contract; headers không bị mất |
| P9 | POST /logout | Session + CSRF hợp lệ | Cookie invalidation/session lifecycle và headers |
| P10 | GET /assets/app-hash.js | Không auth | Content-Type/nosniff/cache static theo policy |
| P11 | GET /api/does-not-exist | 404 | Error route không lộ secret, headers theo policy |
| P12 | GET /health | Endpoint public/internal theo thiết kế | Không vô tình public actuator/diagnostics |
| P13 | GET qua redirect HTTP→HTTPS | Không credential nhạy cảm | Location đúng host, không loop |
| P14 | GET /api/csrf qua CDN | Hai session A/B | Không phục vụ chung token response |
| P15 | P1–P14 qua các pod/canary | Từng artifact/config revision | Không drift giữa instance |

**Không dùng token production thật trong probes hoặc log.** Tạo accounts/test sessions có quyền hạn tối thiểu, request thử mang dữ liệu giả, và bảo đảm những POST có side effect được xử lý trong môi trường test hoặc endpoint idempotent được thiết kế riêng.

### 4.2. Khi nào header có thể không xuất hiện mà vẫn đúng?

- **Set-Cookie** không nhất thiết được phát lại trong mọi GET nếu cookie đã có và session không đổi.
- **Access-Control-Allow-Origin** có thể không hiện trên request không gửi Origin. Muốn test CORS phải chủ động gửi Origin đúng/ngược.
- **Access-Control-Allow-Headers/Methods** chủ yếu được xem ở **preflight OPTIONS**, không bắt mọi GET thông thường có chúng.
- **HSTS** không có trên HTTP response thuần trong nhiều cấu hình là bình thường, nhưng phải có ở HTTPS public theo contract.
- **CSP** trên JSON API có thể không cần cùng policy với frontend HTML; cần đánh giá origin tạo document.
- **401/403** có thể phát sinh từ gateway trước khi request vào Spring; cần quy định nơi nào chịu trách nhiệm security headers trên các response đó.
- **304 Not Modified** và HEAD có semantics khác GET response body; phải đối chiếu các header áp dụng theo chuẩn và cache policy thực thay vì bắt y hệt body GET.
- **Browser managed redirects** có thể trả nhiều responses; phải kiểm tra từng chặng thay vì chỉ response cuối.

## 5. Quy trình đối chiếu từng tầng: origin, gateway, edge, browser

~~~mermaid
flowchart TD
    A["Có header contract và release revision"] --> B["Probe Spring application trực tiếp"]
    B --> C["Probe gateway/ingress nội bộ"]
    C --> D["Probe public HTTPS edge"]
    D --> E["Probe browser thực"]
    E --> F{"Actual thỏa expected theo context?"}
    F -->|Có| G["Lưu PASS + revision + evidence đã scrub"]
    F -->|Không| H["Xác định tầng thay đổi header"]
    H --> I["Đánh giá impact và stop/rollback rollout"]
    I --> J["Sửa đúng owner: app, proxy, CDN hoặc frontend"]
    J --> A
~~~

### 5.1. Spring application direct

Mục đích: kiểm chứng SecurityFilterChain, HeaderWriter, endpoint CSRF, CORS source và cache headers mà **ứng dụng** phát ra.

Dùng **MockMvc** (Servlet) hoặc **WebTestClient** (WebFlux), hoặc HTTP client trong mạng test kết nối trực tiếp app nếu được phép. Không suy luận rằng ứng dụng tự phát HSTS trên backend HTTP nội bộ khi SSL terminate tại proxy.

### 5.2. Ingress/gateway nội bộ

So sánh header có bị **override, strip, append hoặc duplicate** không. Kiểm tra đặc biệt:

- Access-Control-Allow-Origin có bị gateway thêm bản thứ hai không.
- CSP có bị CDN replace bằng policy yếu hơn/khác với Spring không.
- Redirect Location sinh sai scheme vì X-Forwarded-Proto hoặc Host.
- Cookie flags có bị proxy rewrite không.
- Cache-Control no-store có bị cache rules override không.
- 401/403/404/502 từ gateway có thiếu policy headers không.
- OPTIONS preflight có bị login/security middleware chặn không.

### 5.3. Public HTTPS edge

Đây là **kết quả thực mà browser có thể nhìn thấy**. Với HSTS, CSP, cookie và CORS browser, điểm này là bắt buộc. Đừng chỉ kiểm tra service nội bộ rồi đánh dấu release pass.

Nếu CDN serve HTML cho SPA ở frontend origin, kiểm tra **frontend CDN**, không chỉ API gateway. Cookie auth là API response; CSP của document là HTML origin; hai nhiệm vụ có thể có owner khác nhau.

### 5.4. Browser DevTools

DevTools là cần thiết để thấy **behavior**, không chỉ header text:

- Browser có lưu/gửi cookie Secure/SameSite/Domain/Path không?
- CORS preflight có thực hiện trước custom-header POST không?
- CSP có chặn script, iframe hoặc connect-src hợp lệ?
- HSTS có được browser áp dụng từ HTTPS host đúng không?
- Có redirect chain làm mất headers hoặc chuyển host không?
- Các Set-Cookie có bị chặn với lý do trình duyệt không hỗ trợ hoặc third-party cookie policies không?

**Một header đúng trên dây chưa chắc tác động đúng** nếu browser từ chối cookie, source CSP sai hoặc Origin/credentials không tương thích.

## 6. Thu thập header bằng HTTP client mà không làm lộ credential

### 6.1. Kiểm tra HTTPS public bằng curl

Trong terminal được phép truy cập môi trường, dùng curl để **chỉ hiển thị response headers** và bỏ body. Khi endpoint có token, **không in response body**, không copy Set-Cookie/Authorization từ production vào ticket.

~~~bash
# GET thật, không chuyển thành HEAD; -D - in response headers,
# -o /dev/null bỏ body, không follow redirect ngầm.
curl --silent --show-error --max-time 10 \
  --dump-header - --output /dev/null \
  https://app.example.com/

curl --silent --show-error --max-time 10 \
  --dump-header - --output /dev/null \
  https://api.example.com/api/csrf
~~~

**Thận trọng:** Lệnh dump-header vẫn có thể hiện **Set-Cookie** nếu server phát cookie. Chỉ chạy trên môi trường test hoặc lọc dữ liệu nhạy cảm **trước khi ghi vào logs/artifacts**. Không lưu nguyên header dump từ production công khai. Với probes tự động, chỉ trích các header được allowlist và **biến chúng thành PASS/FAIL**.

Curl thường được cấu hình để xác minh TLS certificate. Không thêm **-k/--insecure** như một cách chữa lỗi thường trực; probe không xác minh TLS có thể bỏ sót cả một lớp bảo vệ.

### 6.2. HEAD không hoàn toàn tương đương GET

~~~bash
curl --head https://app.example.com/
~~~

HEAD có thể được server/proxy xử lý khác GET: route chỉ có GET handler, cookie chỉ được tạo khi GET controller truy cập token, caching/redirect logic khác nhau. Vì thế:

- Dùng **GET thật và bỏ body** cho các probes quan trọng.
- HEAD chỉ là bài kiểm tra bổ sung khi route hỗ trợ rõ ràng.
- Với GET /api/csrf, HEAD không thể chứng minh token deferred được materialize giống GET thật.
- Test cần chỉ rõ có follow redirect không; **--location** có thể che giấu response trung gian gây mất cookie/header.
- Không gửi credential thật qua URL hoặc lưu cookie jar production trong artifact CI.

### 6.3. Kiểm tra redirect theo từng chặng

~~~bash
# Mục tiêu: nhìn response 301/302/307/308 và Location
# mà không theo redirect sang host khác.
curl --silent --show-error --max-time 10 \
  --max-redirs 0 \
  --dump-header - --output /dev/null \
  http://app.example.com/
~~~

Ở đây response HTTP có thể chỉ chứa Location để chuyển sang HTTPS, còn **HSTS cần được đánh giá trên HTTPS response**. Không coi việc HTTP redirect thiếu HSTS là lỗi giống thiếu HSTS trên HTTPS document.

**Không tự động truyền Cookie hoặc Authorization sang host khác khi follow redirect.** Nếu điều tra login flow, dùng test account riêng và điều khiển rõ mỗi chặng.

### 6.4. Một probe chỉ xuất metadata đã được lọc

Ví dụ shell dùng curl và awk để kiểm tra security headers của **một trang HTML HTTPS không yêu cầu authentication**. Script này **không lưu body** và **không xuất Set-Cookie**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

target="https://app.example.com/"
headers="$(curl --silent --show-error --max-time 10 \
  --dump-header - --output /dev/null "$target")"

printf '%s\n' "$headers" |
  awk 'BEGIN { IGNORECASE=1 }
       {
         line=$0
         sub(/\r$/, "", line)
         lower=tolower(line)
         if (lower ~ /^strict-transport-security:/ ||
             lower ~ /^content-security-policy:/ ||
             lower ~ /^x-content-type-options:/ ||
             lower ~ /^referrer-policy:/ ||
             lower ~ /^x-frame-options:/ ||
             lower ~ /^cache-control:/) {
           print line
         }
       }'
~~~

**Chú ý:** Script để quan sát thủ công, **chưa phải automated assertion đầy đủ**. Cần status code, kết nối TLS hợp lệ, multiple headers, redirect chains và expected predicates trong CI. Trường hợp CSP chứa URL hoặc dữ liệu cấu hình nhạy cảm, chỉ đưa bản đã scrub vào artifact.

Với Windows PowerShell, có thể dùng curl.exe (không phải alias curl của PowerShell 5.1) và kiểm tra qua các field response object. Không xuất nguyên response headers nếu có Set-Cookie thật.

## 7. Spring Security Servlet: cấu hình một contract có thể kiểm thử

Ví dụ Spring Boot 3, Spring Security 6.x, Java 17+ dùng Servlet. Nếu frontend HTML được serve từ **app.example.com** và API từ **api.example.com**, áp CSP cho HTML ở đúng frontend origin, không chỉ ở JSON API.

### 7.1. SecurityFilterChain có security headers và CSRF

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
        .csrf(Customizer.withDefaults())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp.policyDirectives(
                "default-src 'self'; object-src 'none'; " +
                "base-uri 'self'; frame-ancestors 'none'"))
            .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(31536000)
                .includeSubDomains(true)))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **mẫu tham khảo**, không tự định nghĩa CORS source, authentication users hoặc frontend resources. Cần có **CorsConfigurationSource với exact allowedOrigins** nếu SPA khác origin; HSTS includeSubDomains chỉ sau khi xác nhận toàn bộ subdomain dùng HTTPS. CSP phải được thiết kế từ asset/source inventory thực, không áp policy ví dụ máy móc cho frontend cần scripts/fonts từ origin khác.

Các header do Spring Security cung cấp theo mặc định hoặc tùy biến **có thể bị proxy/CDN thay đổi**. Mã trên chỉ minh họa điểm phát header tại Servlet filter chain; **probe HTTPS public** vẫn là bước bắt buộc.

### 7.2. GET JSON CSRF token cần no-store

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfBootstrapServletController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (csrf == null) {
            throw new IllegalStateException("CSRF filter is missing");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                csrf.getHeaderName(),
                csrf.getToken()));
    }
}
~~~

Token JSON **có thể là XOR-masked representation** trên Spring Security 6.x. Frontend gửi nguyên token đúng header với **cùng cookie/session**; request handler server phải giải được token đó. Không dùng một GET 200 để suy luận CSRF POST được bảo vệ; cần negative POST test.

Mẫu này không log token, không đưa token vào path/query. Với CDN/proxy, cần bypass cache cho /api/csrf và trang chứa token trong HTML. **Cache-Control no-store không cấu hình redaction cho APM/access log**, nên observability vẫn phải có guardrails riêng.

### 7.3. CSP và X-Frame-Options cần đối chiếu trên đúng document

Nếu Spring Security ở API origin không phục vụ SPA HTML, response JSON có CSP không chứng minh HTML frontend được chống XSS/clickjacking.

Kiểm tra:

1. GET **https://app.example.com/** trả CSP trên HTML document.
2. Directive **frame-ancestors** bảo vệ chính HTML document có nguy cơ bị nhúng.
3. X-Frame-Options nếu sử dụng phải phù hợp với frame-ancestors và yêu cầu browser compatibility.
4. CSP Enforce và CSP Report-Only được phân biệt; **Report-Only không chặn hành vi**, chỉ báo cáo theo browser support.
5. Các static assets/CDN origins cần thiết có được phép trong CSP đã duyệt, tránh sửa bằng cách mở wildcard.
6. Nếu document bị trả qua một HTML shell ở gateway, kiểm tra CSP của **shell cuối cùng** thay vì chỉ của backend API.

### 7.4. Servlet filters, exception và error dispatch

Một số response lỗi có thể được tạo ở tầng **AuthenticationEntryPoint, AccessDeniedHandler, gateway, WAF hoặc container**. Nếu request không đến endpoint controller, controller-specific header code có thể không chạy.

Với 401/403/404/500, kiểm tra header thực sự và quyết định owner chịu trách nhiệm. Đừng chỉ test GET /api/me 200. Nếu Spring Security filters không áp cho một error dispatch hoặc gateway sinh error page trước ứng dụng, header phải được bổ sung ở tầng tương ứng khi cần.

**HTTP firewall** có thể reject URL bất thường trước controller. Negative test cần xác minh **không có bypass security matcher**; riêng header trên một 400/RequestRejected response có thể do container/gateway quyết định, phải được đưa vào contract hợp lý.

## 8. WebFlux: cùng yêu cầu header, API kiểm thử riêng

Reactive app dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **CsrfWebFilter**, **ServerWebExchange** và **WebSession**. Không copy HttpServletRequest, SecurityFilterChain của Servlet sang WebFlux.

### 8.1. SecurityWebFilterChain với CSP và CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain browserReactiveSecurity(
        ServerHttpSecurity http) {

    return http
        .csrf(Customizer.withDefaults())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp.policyDirectives(
                "default-src 'self'; object-src 'none'; " +
                "base-uri 'self'; frame-ancestors 'none'")))
        .authorizeExchange(auth -> auth
            .pathMatchers("/", "/assets/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .build();
}
~~~

CORS cho WebFlux cần **Reactive CorsConfigurationSource** và CORS integration theo **ServerHttpSecurity**; không import source Servlet. HSTS và cookie WebSession có cấu hình/behavior riêng, cần kiểm tra bằng HTTPS edge probes.

Mẫu chỉ mô tả lớp bảo vệ ứng dụng, **không** khẳng định mọi header đều xuất hiện trên mọi response nếu thiếu controller, router hoặc public TLS edge.

### 8.2. Endpoint GET CSRF Reactive

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class CsrfBootstrapReactiveController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "Reactive CSRF filter is missing"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken())));
    }
}
~~~

**Không block() trong Reactive controller.** Mono được subscribe trong pipeline response. WebSession, CookieServerCsrfTokenRepository hay XOR request handler phải được cấu hình/kiểm thử theo phiên bản thực tế.

### 8.3. Header trên response được tạo bởi WebFilter/gateway

Trong WebFlux, các lỗi từ **authentication, authorization, route not found hoặc proxy gateway** có thể khác response controller. WebTestClient nên kiểm tra từng status/route. Với Netty/web gateway, header normalization, CORS và forwarded scheme phải được kiểm tra ở edge tương tự Servlet.

## 9. CORS: đối chiếu cả preflight và actual response

Một SPA ở **https://app.example.com** gửi POST JSON đến **https://api.example.com** bằng cookie. Request thường có **OPTIONS preflight** do custom CSRF header.

### 9.1. Preflight không có cookie

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response mong muốn khi đã duyệt đúng origin:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin
~~~

**Preflight thường không gửi JSESSIONID**, nên CORS phải được xử lý trước authentication. Đừng sửa lỗi OPTIONS 401 bằng cách disable toàn bộ CSRF hay mở CORS wildcard.

### 9.2. Probe preflight qua edge

~~~bash
curl --silent --show-error --max-time 10 \
  --request OPTIONS \
  --header "Origin: https://app.example.com" \
  --header "Access-Control-Request-Method: POST" \
  --header "Access-Control-Request-Headers: content-type,x-csrf-token" \
  --dump-header - --output /dev/null \
  https://api.example.com/api/orders
~~~

Cần test thêm Origin **ngoài allowlist**. Nếu origin lạ được cấp credentialed response, đó có thể là lỗ hổng policy. Nếu origin thật của frontend bị từ chối, đó có thể là regression nghiêm trọng sau release.

### 9.3. Actual POST vẫn cần CSRF và authorization

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...
Content-Type: application/json

{"sku":"P100","quantity":1}
~~~

Ở đây Cookie và X-CSRF-TOKEN chỉ là **ký hiệu**, không phải credential thật. **CORS response hợp lệ không tự chứng minh CsrfFilter đang kiểm tra token**. Kiểm thử riêng: cookie phiên hợp lệ + thiếu header CSRF phải bị chặn và không thay đổi dữ liệu; token đúng nhưng user không đủ quyền vẫn bị authorization từ chối.

### 9.4. Những sai lệch hay gặp

| Header actual | Ý nghĩa |
| --- | --- |
| Allow-Origin wildcard, Allow-Credentials true | Sai policy credentialed CORS; browser từ chối, review security |
| Allow-Origin có hai giá trị do API + gateway cùng đặt | Có thể khiến browser không dùng được; thống nhất một owner |
| Preflight 302 chuyển đến login | CORS xử lý sau authentication hoặc gateway redirect OPTIONS |
| Allow-Headers thiếu x-csrf-token | Browser chặn POST JSON có custom CSRF header |
| Trusted origin chỉ có Allow-Origin trên 200, mất trên 401/403 | Frontend thấy CORS error thay vì hiểu auth/CSRF error |
| Origin lạ được phản chiếu với credentials | Rủi ro lộ response phiên cho website không đáng tin |
| Cache response CORS theo URL mà không phân biệt Origin | CDN có thể trả allow-origin sai giữa clients |
| OPTIONS được phép nhưng POST vẫn 403 | Có thể CSRF/authorization hoặc cookie; không coi tất cả là lỗi CORS |

**Không đọc Set-Cookie trực tiếp bằng Fetch response.headers trong JavaScript**: header đó do browser xử lý đặc biệt và không được lộ cho script. Dùng DevTools Network/Storage và các kiểm thử cookie-aware để đối chiếu.

## 10. Set-Cookie, session và CSRF: kiểm tra thuộc tính, không chụp bí mật

Trong ứng dụng cookie-authenticated, một header Set-Cookie là **cấu trúc gồm tên cookie, giá trị và attributes**, không chỉ là một chuỗi chứa session ID.

### 10.1. Những thuộc tính cần đối chiếu

~~~http
Set-Cookie: JSESSIONID=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Dấu ngoặc chỉ là ký hiệu minh họa. Không bao giờ đưa session ID thật vào log, metrics hoặc ảnh chụp màn hình công khai.

| Thuộc tính | Contract thường gặp trên HTTPS production | Cần kiểm tra thêm |
| --- | --- | --- |
| **Secure** | Có trên session cookie | Request thực từ HTTPS edge, không chỉ app HTTP nội bộ |
| **HttpOnly** | Có trên session cookie | JavaScript không được đọc session ID |
| **SameSite** | Lax/Strict/None theo kiến trúc | Khác origin cùng site không đồng nghĩa khác site |
| **Domain** | Host-only nếu không có nhu cầu chia sẻ | Không mở rộng toàn domain chỉ để frontend đọc XSRF |
| **Path** | Giới hạn đúng đường API/auth | Login/logout/refresh có thuộc scope không |
| **Max-Age/Expires** | Theo chính sách phiên/remember-me | Hành vi hết hạn, refresh và logout |
| **Cookie prefix** | __Host- hoặc __Secure- khi kiến trúc đáp ứng | Prefix có ràng buộc Secure/Path/Domain và browser support |
| **Các Set-Cookie khác nhau** | Kiểm tra từng cookie riêng | Không nối nhiều Set-Cookie thành một chuỗi CSV |

**Cookie session** thường phải HttpOnly. **Cookie XSRF-TOKEN** có thể cần JavaScript-readable nếu SPA cùng origin theo mô hình cookie-to-header; không có nghĩa cho phép JavaScript đọc JSESSIONID.

### 10.2. Token XSRF và phiên có vòng đời khác nhau

Một GET /api/csrf đôi khi trả Set-Cookie khi token hoặc session được tạo mới; nhưng **không phải mỗi GET đều bắt buộc Set-Cookie** nếu cookie đã có. Các kịch bản cần test:

1. Anonymous GET chưa có session → backend tạo token/cookie nếu repository cần.
2. Browser đã có session → GET token không nhất thiết set lại cookie.
3. Login thành công → session ID có thể rotate; expected CSRF token có thể bị xóa.
4. Logout thành công → cookie/session invalidation; GET token kế tiếp có thể tạo anonymous session mới.
5. Session timeout → token cũ phải được xử lý theo repository hiện hành.
6. Nhiều tab → cookie dùng chung nhưng token cache trong memory mỗi tab có thể cũ.
7. Nhiều pod → session repository phải đồng bộ hoặc có routing/session affinity theo kiến trúc.

**Chỉ đọc giá trị token để so khác nhau không đủ để đánh giá an toàn**, nhất là XOR masking có thể tạo biểu diễn thay đổi giữa các response dù expected token vẫn vậy.

### 10.3. Không coi cookie hiển thị trong Response Headers là đã được browser lưu

Trên một SPA/API khác origin hoặc khác site, browser còn xét:

- Request Fetch **credentials: include**.
- Origin CORS và Access-Control-Allow-Credentials phù hợp.
- Cookie Secure, SameSite, Domain, Path, expiry.
- Third-party cookie restrictions và browser policy.
- HTTPS scheme và trạng thái TLS.
- Cookie bị ghi đè/hết hạn do response login/logout.
- Scope của cookie host-only khi SPA ở subdomain khác API.

**DevTools Application/Storage và Network blocked cookie reason** mới giúp biết browser thực sự làm gì. Curl thấy Set-Cookie không mô phỏng đủ chính sách cookie browser.

### 10.4. Probe không làm lộ Set-Cookie

Với probe tự động, không lưu raw Set-Cookie value. Có thể xử lý header trong memory rồi chỉ xuất:

~~~text
cookie_name=JSESSIONID
secure=true
httpOnly=true
sameSite=lax
domainScope=host-only
pathScope=/
status=PASS
~~~

Không dùng **Set-Cookie** như một label trong metrics, không đẩy giá trị nguyên vào log/CI artifacts. Nếu test phát hiện thiếu HttpOnly hoặc Secure, chỉ báo **tên cookie và thuộc tính thiếu**.

## 11. Cache-Control, Content-Type, redirect và error headers

### 11.1. Không cache response có CSRF token

Một GET bootstrap token theo session có thể trả:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json
Vary: Origin

{"headerName":"X-CSRF-TOKEN","token":"<not-a-real-token>"}
~~~

**Không đưa response body chứa token thật vào CI logs.** no-store không thay redaction APM, nhưng là chỉ thị quan trọng để cache HTTP không lưu response nhạy cảm. Các response phục vụ cookie session/SSR form theo phiên cần cache policy tương ứng.

| Giá trị | Có đủ cho token response? | Giải thích |
| --- | --- | --- |
| **no-store** | Ưu tiên | Hạn chế caches lưu response |
| **no-cache** | Không thay no-store | Có thể lưu nhưng phải revalidate |
| **private** | Chưa đủ nếu yêu cầu không lưu | Cache private vẫn có thể lưu |
| **max-age=0** | Không | Chỉ hết freshness ngay |
| **Vary: Cookie** | Không thay no-store | Không bảo đảm đúng mọi CDN custom rule |
| **Set-Cookie tồn tại** | Không phải bảo đảm cache an toàn | Proxy/CDN có thể override behavior |

Nếu CDN cache theo URL mà không tách session, user A có thể bị trả token của B. Token không đúng phiên có thể khiến POST bị chặn, nhưng việc phục vụ sai dữ liệu vẫn là sự cố cần giải quyết.

### 11.2. Static assets phải có policy khác

Với JS/CSS có content hash và không chứa dữ liệu theo phiên, có thể dùng:

~~~http
Cache-Control: public, max-age=31536000, immutable
X-Content-Type-Options: nosniff
Content-Type: text/javascript
~~~

Cần kiểm tra filename/content-addressing và purge strategy. Không bắt mọi response static phải có no-store; điều đó gây suy giảm hiệu năng mà không giải quyết CSRF.

### 11.3. Error responses và redirects không được bỏ qua

Kiểm tra cụ thể:

- **401/403 từ Spring Security**: header theo policy, trusted origin có CORS hợp lệ để frontend biết lỗi; không lộ token/session trong body.
- **404/405**: không trả lộ stack traces; có nosniff, cache policy và CORS hợp lý theo owner.
- **429 từ rate limiter**: không đưa dữ liệu nhạy cảm vào Retry-After hoặc lỗi.
- **502/503 từ gateway**: response do gateway tạo; security headers trên HTML error page có thể do gateway quản lý.
- **302/303 sau login**: Location phải đúng host/scheme, không rò CSRF/JWT trong query.
- **304 Not Modified**: áp dụng semantics cache revalidation, không cố so y hệt body GET.
- **HEAD**: kiểm tra route có hỗ trợ và không coi HEAD là minh chứng token bootstrap giống GET.
- **Content-Type**: JSON nên có MIME phù hợp; nosniff giúp tránh type confusion, nhưng không thay validation/encoding.

Nếu response thực không đến Spring app, **thay SecurityFilterChain không sửa được header của gateway error page**. Phải phân định đúng tầng sở hữu lỗi.

## 12. Kiểm thử Servlet bằng MockMvc: expected header và hành vi bảo mật

Bộ test minh họa dưới đây dùng **Spring Boot 3 / Spring Security 6.x**, giả định ứng dụng có routes /, /api/csrf, /api/orders; Spring Security filters được tích hợp trong MockMvc. Các mã status thành công chỉ hợp lệ khi controller nghiệp vụ và quyền thực tế phù hợp.

### 12.1. Kiểm tra security headers trên HTML HTTPS context

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ServletHeaderContractTests {

    @Autowired MockMvc mvc;

    @Test
    void htmlOverHttpsCarriesApprovedHeaders() throws Exception {
        mvc.perform(get("/").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=31536000")))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("frame-ancestors 'none'")))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"));
    }
}
~~~

Với **httpStrictTransportSecurity** đặt theo DSL Servlet, secure(true) mô phỏng HTTPS ở request. Đó **không phải xác minh TLS edge thật**. Thêm một public HTTPS probe cho HSTS và CSP trên origin serve HTML thực.

### 12.2. GET token không được cache

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

// Đoạn thân test, đặt trong class có field MockMvc mvc.
@Test
void csrfBootstrapMustNotBeStored() throws Exception {
    mvc.perform(get("/api/csrf"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL,
            containsString("no-store")))
        .andExpect(jsonPath("$.headerName").isNotEmpty())
        .andExpect(jsonPath("$.token").isNotEmpty());
}
~~~

**Không dùng .andDo(print()) trên response có token trong CI công khai**; nó có thể xuất body, Cookie hoặc headers nhạy cảm.

### 12.3. Preflight tin cậy không đòi đăng nhập

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;

// Đoạn thân test, cần bean CorsConfigurationSource chứa exact origin.
@Test
void preflightIsHandledBeforeAuthentication() throws Exception {
    mvc.perform(options("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers",
                "content-type,x-csrf-token"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Access-Control-Allow-Origin",
            "https://app.example.com"))
        .andExpect(header().string(
            "Access-Control-Allow-Credentials",
            "true"));
}
~~~

Đây là test cho **CORS processor và filter order**, không phải test POST CSRF. Bổ sung negative test Origin không được allowlist: không được cho browser đọc credentialed response.

### 12.4. CSRF đúng hay sai cần đo side effect

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

@Test
void unsafeBrowserRequestWithoutCsrfIsForbidden() throws Exception {
    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"sku\":\"P100\",\"quantity\":1}"))
        .andExpect(status().isForbidden());
}

@Test
void validCsrfCanPassButBusinessRulesStillApply() throws Exception {
    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"sku\":\"P100\",\"quantity\":1}"))
        .andExpect(status().is2xxSuccessful());
}
~~~

**user()** và **csrf()** là test helpers, không mô phỏng đầy đủ login/session cookie thật. Cần bổ sung test GET token JSON với cùng session, auth transition sau login/logout và **assert không có đơn hàng được tạo** khi POST thiếu CSRF.

Một test kiểm tra header HSTS/CSP xanh **không chứng minh CsrfFilter hoạt động**. Hai nhóm assertions phải tồn tại độc lập trong regression suite.

## 13. Kiểm thử Reactive/WebFlux bằng WebTestClient

### 13.1. Kiểm tra header trả về từ WebFilter chain

~~~java
import org.springframework.http.HttpHeaders;

// Đoạn thân test trong test context WebFlux có WebTestClient.
webTestClient.get().uri("/")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        "Content-Security-Policy",
        ".*frame-ancestors 'none'.*")
    .expectHeader().valueEquals(
        "X-Content-Type-Options", "nosniff");

webTestClient.get().uri("/api/csrf")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        HttpHeaders.CACHE_CONTROL, ".*no-store.*");
~~~

In-memory WebTestClient thường **không đại diện đầy đủ cho public HTTPS TLS handshake**, nên không lấy đó làm bằng chứng duy nhất rằng HSTS được browser nhận. Hãy kiểm tra HSTS ở HTTPS edge.

### 13.2. Reactive preflight và CSRF filter

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import org.springframework.http.HttpHeaders;

// Với Reactive CORS source đã cấu hình cho Origin tin cậy.
webTestClient.options().uri("/api/orders")
    .header(HttpHeaders.ORIGIN, "https://app.example.com")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
        "content-type,x-csrf-token")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.com");

// Cần java.util.Map và POST /api/orders thật.
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

Bộ test Reactive này chứng minh filter/webfilter logic trong test context. Để kiểm tra **WebSession cookie và token XOR/raw**, cần test GET bootstrap với cookie jar, POST với token JSON thực, login/logout và session timeout. Đừng dùng **block()** trong controller Reactive chỉ để test token.

## 14. Đưa kiểm tra header vào CI/CD và synthetic monitoring

Một lần kiểm tra thủ công không đủ, bởi drift có thể xuất hiện sau deployment, sửa ingress/CDN rule, thay chứng chỉ/TLS proxy hoặc rollout dở dang. Cần probes tại các mốc **pull request, staging, canary, post-deploy và định kỳ**.

### 14.1. Phân tầng test theo thời điểm

| Giai đoạn | Nơi chạy | Kết quả cần có |
| --- | --- | --- |
| Pull request | MockMvc/WebTestClient | CORS, CSRF, HeaderWriter và route policy có regression tests |
| Build | Dependency/security check | Artifact/Spring version nằm trong compatibility matrix |
| Staging | HTTPS gateway giống production | Header/cookie/redirect cuối tương thích browser |
| Canary | Public HTTPS edge | Các contract bắt buộc PASS trước mở rộng |
| Post-deploy | Browser + public API | Positive/negative tests và cookie behavior PASS |
| Định kỳ | Multi-region synthetic probes | Không drift giữa origin, edge, regions |
| Sau rollback | Same probes | Artifact, config và gateway policy quay về trạng thái đã biết tốt |

### 14.2. Script gate chỉ xuất PASS/FAIL, không dump cookies

Ví dụ shell tối giản kiểm tra HTML public trên HTTPS. Nó chỉ in trạng thái policy, **không in toàn bộ response header** và không lưu body.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

target="https://app.example.com/"

# Giữ header trong memory; tuyệt đối không bật set -x.
raw="$(curl --silent --show-error --max-time 15 \
  --max-redirs 0 \
  --dump-header - --output /dev/null \
  --write-out '\n__STATUS__:%{http_code}\n' \
  "$target")"
clean="$(printf '%s\n' "$raw" | tr -d '\r')"

assert_header() {
  local header_name="$1"
  local expected_regex="$2"

  if ! printf '%s\n' "$clean" |
      grep -Eiq "^$header_name:[[:space:]]*$expected_regex"; then
    printf 'FAIL: %s contract\n' "$header_name"
    exit 1
  fi

  printf 'PASS: %s contract\n' "$header_name"
}

if ! printf '%s\n' "$clean" | grep -Fq "__STATUS__:200"; then
  printf 'FAIL: HTML endpoint status is not 200\n'
  exit 1
fi

assert_header "strict-transport-security" \
  "max-age=31536000([;[:space:]]|$)"
assert_header "x-content-type-options" "nosniff"
assert_header "content-security-policy" \
  ".*frame-ancestors[[:space:]]+'none'"
assert_header "referrer-policy" \
  "(no-referrer|strict-origin-when-cross-origin)"

printf 'PASS: public HTML header smoke gate\n'
~~~

**Đây là demo kiểm tra một phần contract, không phải parser HTTP toàn diện.** Production tool nên kiểm tra status, header duplicates, CSP directives hiệu lực, HSTS policy, redirect chain, cookie attributes và không nhầm nhiều HTTP header blocks. Regex tìm substring có thể báo false positive; chính sách quan trọng cần parser và assertions có ngữ nghĩa.

Không dùng **--insecure** để bỏ TLS validation, không follow redirect tùy ý với credential, không chạy probe tạo giao dịch production ngoài thiết kế. Khi đánh giá response có Set-Cookie thật, không xuất biến raw/clean ra logs hoặc artifacts.

### 14.3. Các gate riêng cho CORS và CSRF

Một pipeline cần hai nhóm test:

- **CORS:** OPTIONS từ exact trusted Origin không cookie phải được xử lý trước auth; Allow-Origin, Methods/Headers và Credentials khớp contract. Origin ngoài allowlist **không** được cấp quyền đọc credentialed response.
- **CSRF:** Browser POST có cookie session nhưng thiếu/sai token phải bị chặn **trước side effect**; POST token đúng vẫn cần đủ quyền; token cũ sau login/logout phải được xử lý theo repository.

**OPTIONS thành công không có nghĩa CSRF đang bật**, và **403 không luôn là CSRF**. Kiểm tra exception category/route hoặc một integration test độc lập, không mở allowlist hay disable CsrfFilter để đạt test nhanh.

### 14.4. Canary gate và rollback trigger

~~~mermaid
flowchart LR
    A["Build + policy contract tests"] --> B["Staging qua HTTPS gateway"]
    B --> C["Deploy canary"]
    C --> D["Public-edge header probes + browser flows"]
    D --> E{"Security gates PASS?"}
    E -->|Có| F["Rollout rộng"]
    E -->|Không| G["Stop và triage"]
    G --> H["Rollback artifact + config + edge policy"]
    H --> D
    F --> I["Periodic drift monitor"]
~~~

Những trường hợp có thể phải **chặn rollout ngay**:

1. Browser cookie route không còn CsrfFilter hoặc unsafe request không token vẫn thay đổi dữ liệu.
2. Credentialed CORS cấp quyền cho wildcard/untrusted origin.
3. Session cookie mất Secure/HttpOnly trên public HTTPS.
4. HTML document mất CSP Enforce hay CSP bị nới trái với policy đã duyệt.
5. HTTPS public host mất HSTS theo contract đã phê duyệt.
6. GET token/session-sensitive data bị shared cache hoặc mất no-store.
7. Một region/pod phục vụ policy yếu hơn các instance còn lại.

**Rollback phải xem cả artifact, config revision và gateway/CDN policy**. HSTS đã cache ở browser không biến mất ngay khi server rollback; CORS preflight cache cũng có thể giữ kết quả cũ.

### 14.5. Không để synthetic probes trở thành sự cố vận hành

Probes cần có timeout, rate limit, dữ liệu giả, test users có quyền tối thiểu và request chỉ đọc khi có thể. Với test POST thực sự, dùng staging hoặc endpoint được thiết kế idempotent/transaction rollback.

Không đưa cookie/JWT/CSRF token vào URL, logs, tracing baggage hoặc metric labels; không tự retry thao tác gây side effect khi request trước có thể đã thành công.

## 15. Phát hiện drift giữa policy, pod, gateway và browser

### 15.1. Ba trạng thái cần so sánh

| Tầng | Ví dụ nguồn bằng chứng | Giới hạn |
| --- | --- | --- |
| **Desired** | Git policy và approved header contract revision | Đã duyệt không đồng nghĩa đã deploy |
| **Resolved runtime** | Artifact digest, active profile, sanitized config fingerprint, filter chain | Không public Environment/Actuator secrets |
| **Observed** | Public HTTPS response headers, browser behavior, security negative tests | Có thể khác giữa regions và CDN cache states |

Ví dụ:

~~~text
Policy v7 đã duyệt:
  HTML CSP: frame-ancestors 'none'
  HSTS: max-age=31536000
  /api/csrf: no-store
  CORS credentials: https://app.example.com only

Spring pod A: đủ policy
Spring pod B: env override thêm debug origin
CDN region R1: HTML CSP và cache bypass đúng
CDN region R2: CSP cũ và cache token theo URL
~~~

Nếu chỉ đọc Git hoặc test một pod, nhiều sai lệch vẫn không bị phát hiện. Cần **sampling theo instance, deployment revision và multi-region public-edge probes**.

### 15.2. Observability: metrics low cardinality

Ví dụ metrics do nhóm vận hành **tự định nghĩa** (không phải tên metric mặc định Spring Security):

~~~text
http_security_header_contract_checks_total{
  environment="prod",
  host_group="frontend",
  route_group="html",
  policy="hsts",
  outcome="pass",
  release="r42"
}

http_security_header_contract_checks_total{
  environment="prod",
  host_group="api",
  route_group="csrf-bootstrap",
  policy="cache-control",
  outcome="fail",
  release="r43"
}

security_config_revision_match{
  environment="prod",
  workload="api",
  expected_revision="policy-v7"
}
~~~

Chỉ dùng labels hữu hạn: environment, release, route template/group, host group, header category và outcome. **Không dùng raw Origin từ internet, token, cookie, userId, query string, CSRF token hoặc JWT làm metrics labels**.

### 15.3. Cảnh báo theo tác động, không theo sự tồn tại lỗi 403

| Tín hiệu | Khả năng cần điều tra |
| --- | --- |
| CSP probe thất bại sau frontend deploy | CDN/HTML policy hoặc asset origin thay đổi |
| HSTS biến mất chỉ ở một region | Edge config drift |
| Trusted OPTIONS trả 401 | CORS filter order hoặc gateway auth |
| CSRF 403 tăng sau nâng Spring Security | Raw/XOR mismatch hoặc token lifecycle |
| 403 tăng từ scanner/untrusted Origin | Có thể policy đang chặn đúng |
| X-Cache HIT hoặc Age tăng tại GET /api/csrf | Rủi ro cache theo URL |
| Curl thấy Set-Cookie nhưng browser không lưu | SameSite/Secure/Domain/third-party policy |
| Login loop sau change cookie Domain | Session scope/redirect cookie mismatch |
| Chỉ một pod khác headers | Runtime config/artifact mismatch |

Một số trường hợp phải cảnh báo **Critical** dù không có 5xx, ví dụ wildcard credentialed CORS, cookie session mất HttpOnly hoặc CSRF protection bị bypass. Không lập cảnh báo chỉ vì 403 tăng, vì một đợt tấn công bị chặn cũng có thể làm 403 tăng.

### 15.4. Quy trình đối chiếu khi mismatch

1. Ghi **host, route group, method, status, Origin class, region, timestamp, release/policy revision**; không ghi secrets.
2. Tái lập với probe không chứa production token.
3. So header trực tiếp Spring app, qua gateway, tại public HTTPS edge rồi browser.
4. Xác định response do **app, auth filter, WAF, ingress error page hay CDN cache** sinh.
5. Đối chiếu artifact, config revision, dependency và edge policy tương ứng.
6. Nếu có bypass bảo vệ hoặc lộ dữ liệu, stop rollout/giảm lưu lượng và kích hoạt incident response.
7. Sửa đúng owner qua source of truth có review; tránh manual hotfix không ghi nhận.
8. Test lại positive/negative behavior, không chỉ đưa header trở lại.
9. Bổ sung regression test và alert để cùng lỗi không tái diễn.

## 16. Runbook điều tra header sai sau triển khai

Runbook cần xác định **điểm đo, status/request context, tầng tạo response, owner và biện pháp khôi phục**. Không chỉ sửa code Spring Security khi lỗi thực sự nằm ở CDN hoặc gateway.

### 16.1. HSTS được cấu hình nhưng không thấy ở HTTPS public

1. Đối chiếu HTTPS hostname thật với backend/HTML origin. Trang frontend có thể được CDN phục vụ độc lập với API Spring.
2. Kiểm tra trực tiếp app, ingress và public edge để xác định nơi header mất.
3. Xem request thật có HTTPS hợp lệ; **HSTS không được browser xử lý từ HTTP response không an toàn**.
4. Kiểm tra TLS termination, X-Forwarded-Proto/Host và trusted proxy; proxy phải sanitize forwarded headers từ client không đáng tin.
5. Xác minh max-age không phải 0; includeSubDomains có đúng policy hay không.
6. Lặp lại probes qua các regions/canary pods.

**HSTS đã cache trên browser không tự mất ngay sau rollback server**; vì vậy thay max-age hoặc includeSubDomains cần quy trình thay đổi được duyệt.

### 16.2. CSP có header nhưng vẫn mở script không đáng tin

1. Đo **HTML document origin** chứ không chỉ response JSON API.
2. Phân biệt **Content-Security-Policy Enforce** với **Content-Security-Policy-Report-Only**.
3. Kiểm tra giá trị thực của script-src, default-src, object-src, base-uri, frame-ancestors, connect-src, form-action theo yêu cầu.
4. Kiểm tra CDN có ghi đè/nhân đôi CSP; nhiều policies có semantics kết hợp, không đơn giản chọn policy “mở nhất”.
5. So policy với asset inventory, nonces/hashes và browser CSP violations.
6. Không mở wildcard hoặc unsafe-inline hàng loạt chỉ để frontend hết lỗi.
7. Test lại HTML của những routes và versions frontend đang được phục vụ.

**Một test chỉ kiểm tra CSP tồn tại chưa đủ để chứng minh XSS/clickjacking protection.**

### 16.3. CORS OPTIONS bị 401/403 sau release

1. Gửi OPTIONS với Origin, Access-Control-Request-Method và Access-Control-Request-Headers, **không Cookie**.
2. Kiểm tra CorsFilter/CorsWebFilter có xử lý trước authentication không.
3. Kiểm tra exact origin allowlist, đúng path và các custom headers X-CSRF-TOKEN/X-XSRF-TOKEN.
4. Xem gateway và Spring có cùng thêm Access-Control-Allow-Origin dẫn đến header trùng không.
5. Kiểm tra response errors 401/403 có CORS phù hợp với trusted origin không.
6. Chạy negative test origin ngoài allowlist, rồi POST thiếu CSRF để bảo đảm không mở bypass.

**Không sửa bằng wildcard CORS có credentials hoặc tắt CSRF toàn cục.**

### 16.4. Set-Cookie xuất hiện nhưng người dùng bị đăng xuất liên tục

1. Dùng DevTools xem cookie bị browser từ chối vì lý do nào.
2. Kiểm tra Secure, HttpOnly, SameSite, Domain, Path, expiry trên HTTPS public.
3. Phân biệt **khác origin** với **khác site**; Fetch có credentials include hay không?
4. Kiểm tra third-party cookie restrictions và trình duyệt thực tế.
5. So các response login/logout với session rotation; xem Set-Cookie có bị gateway rewrite không.
6. Nếu có nhiều pods, kiểm tra session store, keys và cookie configuration revisions.
7. Với cookie host-only, không mở Domain chỉ để SPA đọc XSRF như một bản vá tùy tiện.

**Không đặt HttpOnly=false cho session cookie** để “sửa” JavaScript không đọc được session.

### 16.5. Token endpoint bị shared cache

1. GET /api/csrf từ app direct phải có no-store theo contract.
2. Đo qua gateway/CDN, kiểm tra Age/X-Cache và bypass rules.
3. Dùng hai session **test** A/B tách biệt; kiểm tra không nhận chung cached body.
4. XOR masked token có thể thay đổi mỗi response, nên **không so token string đơn thuần** để kết luận caching an toàn.
5. Sửa ứng dụng/edge config, purge objects đã cache và kiểm tra lại.
6. Nếu có nguy cơ lộ session/CSRF token hoặc dữ liệu cá nhân, xử lý theo incident response và retention policy.

### 16.6. Chỉ thiếu headers trên 401/403/404/502

1. Xác định response do Spring Controller, CsrfFilter/AuthenticationEntryPoint, HTTP firewall, WAF, CDN, ingress hay container tạo.
2. Nếu lỗi phát sinh trước controller, controller advice hoặc ResponseEntity ở controller **có thể không áp dụng**.
3. Với response do gateway phát, owner phải sửa gateway headers, không chỉ thêm Java filter.
4. Kiểm tra CORS trên error response cho trusted SPA, nhưng không cấp quyền cho untrusted origins.
5. Với HTML error page, đặt CSP/framing policy ở đúng origin và route.
6. So cả status/error type và actual headers ở public HTTPS edge.

### 16.7. Header khác nhau giữa các pods/regions

1. Gắn kết quả probe với release/policy revision và region bằng metadata không nhạy cảm.
2. Kiểm tra rollout partial, active profiles, environment override, config reload và runtime BOM.
3. Xác minh CDN cache propagation; header cũ có thể đến từ edge dù app đã thay.
4. Nếu một instance có bảo vệ yếu hơn, stop canary hoặc rút traffic theo runbook.
5. Redeploy artifact/config đã review, không sửa tay không lưu dấu.
6. Test từng instance và public edge sau remediation; bổ sung drift alert.

### 16.8. Sau nâng Spring Security bị mất header mặc định

Thứ tự phân tích:

~~~text
Dependency BOM và runtime classpath mới
→ SecurityFilterChain/ServerHttpSecurity matcher có nhận route không?
→ Header writer hoặc filter có được đăng ký không?
→ Response từ Spring application có header không?
→ Gateway/CDN có thay đổi header không?
→ Public HTTPS browser nhận policy gì?
→ Negative security tests có còn chặn request nguy hiểm không?
~~~

Không tự kết luận lỗi do framework chỉ vì xảy ra sau upgrade; hạ tầng và config cũng có thể được thay cùng release. Khi mã nguồn build được nhưng headers khác, **version compatibility tests** phải là HTTP behavior tests, không chỉ compilation.

## 17. Bài tập thực hành

**Bài A — Xây header contract:** Chọn frontend HTML và API session cookie. Định nghĩa 12 probes bao gồm HTML, /api/csrf, OPTIONS, POST thiếu CSRF, 401/403, login/logout, static assets, redirect, 404 và CDN. Phân loại REQUIRED/FORBIDDEN/CONDITIONAL/NOT_APPLICABLE.

**Bài B — Đo ba tầng:** Trong staging được phép, đo cùng route tại Spring direct, ingress và public HTTPS edge. Chỉ xuất allowlisted headers và xác định owner của một giá trị bị ghi đè.

**Bài C — HSTS:** Bật HSTS ở Servlet/WebFlux, xem max-age tại HTTPS public. Thử thay max-age trong staging và giải thích vì sao cache browser ảnh hưởng rollback.

**Bài D — CSP đúng HTML origin:** Đặt CSP trên JSON API nhưng không đặt trên HTML CDN. Chứng minh HTML không được CSP API bảo vệ, rồi triển khai policy trên frontend origin và test browser.

**Bài E — CORS hai origins:** Preflight từ origin tin cậy và origin không tin cậy. Kiểm tra exact Allow-Origin/Headers/Methods, rồi chạy POST thiếu CSRF và chứng minh không side effect.

**Bài F — Cache token:** Cấu hình sai CDN cache theo URL cho GET /api/csrf trong staging, dùng session test A/B phát hiện và sửa bằng no-store + edge bypass/purge.

**Bài G — Cookie attributes:** Tạo cấu hình cookie session sai SameSite/Path/Secure trong HTTPS staging, chẩn đoán bằng DevTools và sửa nhưng giữ HttpOnly.

**Bài H — Error responses:** So sánh 200, 401, 403, 404, 502 qua gateway và Spring, xác định nơi phát response cùng header owner.

**Bài I — Servlet regression:** Viết MockMvc cho HSTS/CSP/nosniff, JSON CSRF no-store, OPTIONS và POST thiếu CSRF. Kiểm tra database không bị thay đổi khi bị từ chối.

**Bài J — WebFlux parity:** Viết WebTestClient cho CSP/nosniff, CORS và CsrfWebFilter, bổ sung public HTTPS probe cho HSTS.

**Bài K — Canary CI:** Chuyển contract thành release gate, cố ý bỏ CSP hoặc HSTS trong staging và chứng minh pipeline dừng trước rollout rộng.

**Bài L — Drift drill:** Hai pods có config revisions khác nhau; dùng probes và release manifest tìm instance sai, sau đó restore qua pipeline.

**Bài M — Incident tabletop:** CDN vô tình cache token response và một edge mất CSP. Xây thứ tự cô lập, phân loại rủi ro, purge, rollback và regression tests sau sự cố.

## 18. Checklist triển khai và nguyên tắc cần nhớ

### 18.1. Checklist trước khi đánh dấu deployment PASS

| Nhóm | Điều kiện |
| --- | --- |
| **Header contract** | Có expected policy theo host/route/status, owner và revision |
| **Public HTTPS** | HSTS đúng max-age/scope trên đúng hostname, TLS hợp lệ |
| **HTML document** | CSP Enforce/Report-Only đúng mục tiêu; framing và Referrer-Policy phù hợp |
| **MIME protection** | X-Content-Type-Options nosniff và Content-Type đúng |
| **Cookie/session** | Session cookie Secure/HttpOnly, SameSite/Domain/Path đúng, browser chấp nhận |
| **CORS** | Trusted Origin exact; untrusted Origin không được cấp quyền |
| **Preflight** | OPTIONS không cần session cookie, Allow-Headers/Methods đúng |
| **CSRF** | Request unsafe thiếu/sai token bị từ chối, không side effect |
| **Cache** | Token/session-sensitive response no-store và CDN bypass |
| **Errors** | 401/403/404/502 có headers theo contract và đúng response owner |
| **Redirects** | Location đúng HTTPS host, không có secrets trong URL |
| **Static assets** | MIME/nosniff và cache policy theo versioned assets |
| **Servlet/Reactive** | Có kiểm thử riêng theo stack và Spring Security version |
| **Gateway/CDN** | Không strip/duplicate/override header trái policy |
| **Canary/regions** | Không có drift artifact/config/edge policy |
| **Observability** | Metrics/logs không lưu session ID/JWT/CSRF token |
| **Rollback** | Artifact/config/edge policy known-good được xác định |
| **Post-deploy** | Synthetic probes, browser flows và negative tests PASS |

### 18.2. Mười hai nguyên tắc cốt lõi

1. **Header viết trong code không bảo đảm browser nhận được**; phải đo HTTPS public edge.
2. **Expected phụ thuộc route, method, Origin, status và auth state**; không áp một bộ header máy móc cho mọi response.
3. **So giá trị hiệu lực, không chỉ sự tồn tại**: CSP Report-Only, HSTS max-age=0 và wildcard CORS có ý nghĩa khác.
4. **CSP của SPA phải được trả trên HTML origin**, không chỉ JSON API.
5. **HSTS phải xác minh qua HTTPS**, kể cả khi backend nhận HTTP từ trusted proxy.
6. **OPTIONS và POST cần kiểm thử riêng**; CORS đúng không chứng minh CsrfFilter đang chặn request.
7. **Set-Cookie cần kiểm tra attributes và browser behavior**, không chỉ chuỗi header.
8. **Token bootstrap cần no-store và CDN bypass**, cùng kiểm thử hai sessions độc lập.
9. **Servlet và WebFlux có filters và API riêng**, cần MockMvc/WebTestClient theo stack cùng browser/edge tests.
10. **Error responses, redirects và regions có thể khác header 200**, cần ma trận nhiều tình huống.
11. **CI gates/drift metrics phải tránh secrets**, chỉ dùng route template, policy outcome và revision.
12. **Rollback liên quan artifact, runtime config, CDN và browser caches**, không chỉ thay code.

**Kết luận:** Đối chiếu header thực tế sau mỗi deployment là một chu trình **policy đã duyệt → Spring Security runtime → proxy/CDN → browser → kiểm thử kết quả và cảnh báo**. Với header contract theo ngữ cảnh, probes nhiều tầng, regression tests và rollback runbook, đội vận hành có thể phát hiện kịp thời việc suy yếu CSP/HSTS, CORS, CSRF, cache hay cookie/session trước khi trở thành sự cố.

## Tài liệu tham khảo chính thức và thực hành bổ trợ

- [Spring Security 6.5 — HTTP Security Headers Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — CSRF Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CORS Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — HTTP Firewall Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Security 6.5 — HTTP Security Headers Reactive](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — CSRF Reactive](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — CORS Reactive](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)





