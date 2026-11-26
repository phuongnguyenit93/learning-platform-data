# Theo dõi request bị firewall từ chối

## Mục tiêu và bối cảnh vận hành

Trong chương **Vận hành và giám sát** của dịch vụ **SPRING_SECURITY_HTTP_PROTECTION**, nhiều lớp phòng vệ HTTP cùng hoạt động: **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session protection**. Khi request bất thường bị từ chối, nhiệm vụ của vận hành không chỉ là nhìn mã HTTP, mà còn xác định **lớp nào đã từ chối, vì sao, có ảnh hưởng người dùng hợp lệ không và liệu chính sách bảo vệ có bị suy yếu sau triển khai hay không**.

Trên stack Servlet, Spring Security sử dụng cơ chế **HttpFirewall** trong **FilterChainProxy**, thường với **StrictHttpFirewall**, nhằm kiểm tra và chuẩn hóa cách request được nhìn nhận trước khi lựa chọn security filter chain và các request matchers. Một request chứa đường dẫn hoặc phương thức không được chấp nhận có thể gây **RequestRejectedException** trước khi tới controller. Trong thực tế, **API gateway, WAF, reverse proxy, Servlet container hoặc CDN** còn có thể từ chối request *trước cả Spring Security*. Trên **Reactive/WebFlux**, không sử dụng chính StrictHttpFirewall của Servlet: lớp kiểm tra request thuộc HTTP server, gateway, framework routing và các WebFilters phù hợp.

Mục tiêu bài học là xây dựng khả năng quan sát **an toàn, phân loại được nguyên nhân và đủ để đưa ra quyết định**. Người học sẽ thực hành với Spring Security Servlet lẫn WebFlux, metrics, structured audit, kiểm thử URL normalization, deployment gates và runbook điều tra.

Sau khi học, bạn có thể:

1. Giải thích vai trò, ranh giới và thứ tự xử lý của **StrictHttpFirewall**, **FilterChainProxy**, **RequestRejectedException** và **RequestRejectedHandler** trên Servlet.
2. Phân biệt **Spring firewall rejection** với WAF/proxy rejection, authentication 401, authorization/CSRF 403, CORS failure và validation 400.
3. Nhận diện các nhóm request bất thường như encoded separators, semicolon, path normalization, HTTP methods hoặc headers/host không hợp lệ mà không tự động nới firewall.
4. Thiết kế **log, metrics và trace correlation an toàn**, tránh ghi raw URL/query, Cookie, Authorization, JWT, CSRF token hay HTTP request bodies.
5. Viết kiểm thử **StrictHttpFirewall**, **MockMvc**, browser/public-edge và **WebTestClient** phù hợp trách nhiệm của từng stack.
6. Phân tích khác biệt giữa **lỗi tương thích client/gateway** và **lưu lượng scanning/probing** mà không kết luận động cơ từ một request.
7. Thiết lập **canary gates, alert, runbook và rollback** để giải quyết lỗi hợp lệ mà vẫn ngăn bypass security matchers.

## 1. HTTP firewall là gì, và không phải là gì?

### 1.1. Ranh giới an toàn trước khi chọn security chain

Một URL có thể có nhiều biểu diễn tương đương hoặc gần tương đương tùy cách **HTTP server, proxy, servlet container, framework và request matcher** giải mã/chuẩn hóa. Ví dụ, các tầng có thể khác nhau khi gặp:

- Dấu phân tách path được URL-encode.
- Dấu chấm và dấu chấm kép, path traversal, dấu chấm phẩy (matrix parameters).
- Backslash, repeated slashes hoặc chuỗi có nhiều lớp encoding.
- Các ký tự điều khiển, xuống dòng hoặc header values bất thường.
- HTTP methods không có trong danh sách cho phép.
- Host/header/parameter có giá trị không hợp lệ theo policy.

Nếu authorization matcher đọc **đường dẫn A** nhưng application handler thực thi **đường dẫn B**, có nguy cơ bypass quyền. HttpFirewall giúp Spring Security kiểm tra và thống nhất cách xử lý request tại ranh giới Servlet security.

~~~mermaid
flowchart TD
    A["Internet client / Browser"] --> B["CDN / WAF / Reverse Proxy"]
    B --> C["Servlet container"]
    C --> D["Spring Security FilterChainProxy"]
    D --> E["HttpFirewall validation"]
    E --> F{"Request hợp lệ?"}
    F -->|Không| G["RequestRejectedException"]
    F -->|Có| H["Chọn SecurityFilterChain"]
    H --> I["CSRF / Authentication / Authorization"]
    I --> J["Spring MVC / Application"]
    G --> K["RequestRejectedHandler / error handling"]
~~~

Đây là **luồng logic**, không cam kết mọi gateway, container hoặc phiên bản framework đều trả cùng HTTP status. Một request bất thường có thể bị chặn tại WAF/container trước FilterChainProxy, nên Spring hoàn toàn không nhận được nó.

### 1.2. StrictHttpFirewall khác WAF ở đâu?

| Công cụ | Mục tiêu chính | Bằng chứng vận hành |
| --- | --- | --- |
| **Spring Security StrictHttpFirewall (Servlet)** | Ràng buộc tính hợp lệ của request nhìn từ Servlet và an toàn request matching | RequestRejectedException qua FilterChainProxy |
| **Spring Security CSRF filter** | Bảo vệ browser cookie-authenticated unsafe requests khỏi forged requests | Missing/Invalid CSRF theo request handler/filter |
| **Spring Security Authorization** | Kiểm tra identity, roles, scopes, ownership | Authorization denied / 403 |
| **CORS processing** | Điều khiển browser origin nào được đọc cross-origin response | OPTIONS preflight và Allow-Origin/Headers/Credentials |
| **WAF ở edge** | Chặn theo rule/traffic signatures, bot behavior và edge policy | WAF decision/rule category |
| **Reverse proxy / ingress** | HTTP parsing, routing, normalization, TLS termination | Status/route rewrite/forwarded request logs |
| **Servlet container** | HTTP grammar/parser, limits và connector behavior | Connector 400/414/431 hoặc connection close |
| **Reactive server/gateway** | HTTP parsing và route matching ở stack WebFlux/Netty/gateway | Reactive HTTP status/exception, gateway reason |

**StrictHttpFirewall không phải WAF tổng quát**. Nó không tự phát hiện mọi exploit HTTP, không thay input validation, SQL injection defense, rate limiting, authorization hay browser-side CSP/CSRF. Một request được firewall chấp nhận vẫn có thể vi phạm quy tắc nghiệp vụ và phải được các lớp sau kiểm tra.

### 1.3. Từ chối firewall không mặc nhiên là “tấn công thành công”

Khi firewall chặn request, cơ chế bảo vệ **đang từ chối một biểu diễn request không chấp nhận được**. Nó không chứng minh người gửi có ý đồ tấn công; một mobile client, bookmark, proxy rewrite hay legacy application cũng có thể sinh URL sai.

Ngược lại, một request **không** bị firewall từ chối không đảm bảo request an toàn; nó vẫn có thể thiếu CSRF token, không được phép truy cập tài nguyên hoặc chứa dữ liệu nguy hiểm trong business payload.

Vì vậy dashboard phải thể hiện **decision** và **control**, không tự biến mọi RequestRejectedException thành “đã ngăn một cuộc tấn công” có độ tin cậy tuyệt đối.

## 2. Hiểu RequestRejectedException, RequestRejectedHandler và HTTP status

### 2.1. Vị trí phát sinh của Servlet firewall rejection

Trong Servlet stack, Spring Security **FilterChainProxy** sử dụng **HttpFirewall** để kiểm tra request trước khi đưa qua SecurityFilterChain đã chọn. Khi request không hợp lệ theo cấu hình, firewall có thể ném **RequestRejectedException**.

Điểm đáng lưu ý:

- Request có thể bị từ chối **trước controller và trước MVC handler mapping**, nên **route template** chưa chắc đã tồn tại.
- Request có thể bị chặn **trước CsrfFilter hoặc AuthorizationFilter**, nên không nên gắn nhãn CSRF/authorization cho rejection này.
- **RequestRejectedHandler** là extension point để quyết định cách trả lời hoặc ghi nhận rejection trong các đường xử lý được nối phù hợp.
- Kết quả HTTP **thường là 400 Bad Request** với handler/status policy phổ biến, nhưng không được giả định mọi Spring Security version, custom handler, server hoặc proxy đều trả chính xác 400.
- Một HTTP 400 có thể phát sinh từ JSON parser, bean validation, reverse proxy, Servlet container hoặc business contract, **không phải luôn là RequestRejectedException**.
- Một WAF cũng có thể trả **403** cho URL tương tự mà Spring không nhìn thấy request.

### 2.2. Đừng dùng mã 400/403 để suy ra handler đã chạy

| Response nhìn thấy | Các nguyên nhân có thể | Điểm xác nhận |
| --- | --- | --- |
| **400** | StrictHttpFirewall, container parser, invalid request, JSON/body validation | Exception category và tầng trả response |
| **401** | Authentication không hợp lệ hoặc chưa có | AuthenticationEntryPoint, cookie/JWT |
| **403** | WAF deny, CSRF, authorization, một custom firewall handler | WAF decision hoặc security exception |
| **404** | Không có route, proxy rewrite, mismatch security path | Gateway route và MVC/WebFlux matching |
| **405** | Method không có handler | HTTP method mapping/allowed methods |
| **414** | Request target quá dài ở proxy/container | Upstream limits, không mặc định từ StrictHttpFirewall |
| **431** | HTTP request headers quá lớn ở proxy/container | Header size limit |
| **Connection reset/close** | HTTP grammar/parser hoặc network rejection trước ứng dụng | Proxy/server telemetry và raw network test trong staging |

Một **HTTP status monitor** nên đếm trạng thái với nhãn chung. Chỉ tạo nhãn **control=spring_http_firewall** khi đã xác nhận request được xử lý bởi HttpFirewall/RequestRejectedHandler, thay vì suy đoán từ status.

### 2.3. Mẫu sự kiện rejection không chứa dữ liệu nhạy cảm

~~~json
{
  "event": "http.security.request_rejected",
  "control": "spring_http_firewall",
  "decision": "rejected",
  "reason": "unclassified_request_rejected",
  "httpMethodClass": "OTHER",
  "pathGroup": "unmatched",
  "status": 400,
  "environment": "prod",
  "release": "r63",
  "requestId": "req-c27d"
}
~~~

Đây là **schema do dự án tự định nghĩa**, không phải log/metric mặc định. Đặc biệt **reason** nên bắt đầu bằng loại hữu hạn như **unclassified_request_rejected**. Không tự parse raw exception message thành nhãn dữ liệu dài vô hạn.

### 2.4. Tại sao không log nguyên exception message?

Một **RequestRejectedException** có thể chứa chi tiết request/path/characters dẫn tới lỗi. Nội dung đó **đến từ input chưa tin cậy** và có thể mang dữ liệu nhạy cảm hoặc kí tự điều khiển/log injection.

Tránh những cách ghi:

~~~java
// Không dùng cách này trong production telemetry không kiểm soát.
logger.warn("Rejected: {}", exception.getMessage());

// Không thu full URL, query hoặc mọi request headers.
logger.warn("Rejected {} {}", request.getMethod(),
    request.getRequestURI());
~~~

Nếu cần điều tra một lỗi khó, có thể dùng **test environment, dữ liệu tổng hợp, debug scope ngắn hạn và quy trình quyền truy cập**; đừng biến full request dump thành chính sách logging mặc định.

## 3. Những nhóm request thường bị StrictHttpFirewall từ chối

### 3.1. Bảng phân loại kỹ thuật

| Nhóm | Ví dụ biểu diễn | Rủi ro cần xem | Cách khắc phục an toàn |
| --- | --- | --- | --- |
| **Encoded path separator** | Ký hiệu slash/backslash được URL-encode | Các tầng giải mã khác nhau dẫn đến matcher confusion | Thiết kế lại API path; đặt dữ liệu ở query/body đúng contract |
| **Semicolon / matrix params** | Path chứa dấu chấm phẩy và parameters | Một tầng bỏ parameter, tầng khác giữ | Review route/matcher, ưu tiên path không ambiguous |
| **Dot segments / traversal** | Đường dẫn có dấu chấm/chấm kép bất thường | Path normalization và resource traversal | Chặn canonicalization bất nhất; không nới firewall hàng loạt |
| **Repeated slashes** | Path có nhiều dấu phân tách liên tiếp | Proxy và app xử lý không giống nhau | Chuẩn hóa URL contract tại client/proxy |
| **Backslash** | Dấu phân tách theo hệ khác | Container/framework có thể diễn giải khác | Reject và sửa client |
| **Encoded percent / double encoding** | Nhiều tầng percent-encoding | Decode một lần hay nhiều lần cho kết quả khác | Thống nhất decode boundary và test qua edge |
| **Control characters** | NUL, CR/LF, ký tự không hợp lệ | Header/log injection, parser confusion | Reject trước app khi có thể, không log payload |
| **Unsupported HTTP method** | TRACE hoặc phương thức không được phép | Lạm dụng/cross-tier method inconsistencies | Giữ allowlist method phù hợp business |
| **Header names/values lạ** | Ký tự không hợp lệ, tên/giá trị không đạt predicate | Header parser/matcher confusion | Validate/từ chối; review legitimate client |
| **Host không được duyệt** | Hostname lạ khi policy allowlist | Host spoofing, routing confusion | Bảo vệ Host tại proxy và firewall khi phù hợp |

Các ví dụ là **nhóm phân loại**, không phải cam kết mỗi bản Spring Security đều có một exception class riêng cho từng nhóm. Chi tiết mặc định của StrictHttpFirewall và Servlet container **phụ thuộc phiên bản/connector**; hãy pin BOM và viết negative tests cho những nhóm quan trọng.

### 3.2. Đường dẫn URI nhìn thấy ở các tầng có thể khác nhau

Ví dụ một client tạo URL chứa ký tự phân tách encoded:

~~~text
Client original request-target
    /api/items/<encoded-separator>/detail

CDN / gateway path rewrite
    /api/items/.../detail

Servlet request URI và servletPath
    có thể khác tùy connector và decoding

Spring Security matcher
    phải áp authorization trên path có semantics nhất quán
~~~

Nếu proxy giải mã rồi rewrite request trước khi Spring nhận, **StrictHttpFirewall có thể không còn thấy biểu diễn encoded ban đầu**. Vì vậy chỉ test MockMvc direct không đủ; cần chạy **public-edge → proxy → container → Spring MVC** trong staging với cùng routing rules.

Không thử nới firewall để “đón nhận mọi URL” nếu chưa biết chính xác mỗi tầng xử lý nó. Mục tiêu của sửa lỗi là **thống nhất contract**, không cho các tầng hiểu hai đường dẫn khác nhau.

### 3.3. HTTP methods và application contract

Spring Security StrictHttpFirewall có cơ chế danh sách **HTTP methods được cho phép**. Các phương thức bất thường hoặc không phù hợp với policy có thể bị từ chối trước controller. Tuy vậy:

- Một endpoint không hỗ trợ DELETE có thể trả **405** từ MVC, không nhất thiết bị firewall chặn nếu DELETE thuộc method allowlist.
- Phương thức TRACE có thể bị firewall reject hoặc HTTP server từ chối trước đó, tùy cấu hình.
- CORS preflight dùng **OPTIONS** và thường không mang cookie session; không chặn OPTIONS một cách máy móc rồi kết luận request đáng ngờ.
- Bật một HTTP method ở firewall **không cấp quyền nghiệp vụ**. Authentication, authorization, CSRF và route mapping vẫn phải kiểm tra.
- Request method có thể được proxy/HTTP method override layer thay đổi; cần kiểm tra các override headers và method tunneling nếu hệ thống sử dụng.

Không thay một method allowlist vì một alert từ scanner mà chưa biết ứng dụng có cần method đó không.

### 3.4. RequestRejectedException không phải câu trả lời cho mọi path traversal

StrictHttpFirewall giúp bảo vệ ranh giới request matching trên Servlet. File serving, file path resolution, archive extraction, static resource mapping và downstream services vẫn phải kiểm tra riêng path traversal. Một URL đã vượt firewall không có nghĩa mọi thao tác filesystem an toàn.

## 4. Thiết kế structured audit cho firewall rejection

### 4.1. Phân loại sự kiện theo nguồn phát

Một pipeline giám sát nên tách rõ **trạng thái cuối** với **quyết định bảo mật đã xác nhận**:

~~~text
HTTP status observed
    -> 4xx/5xx tổng ở public edge/app

Spring HTTP firewall rejected
    -> chỉ khi đã thấy RequestRejectedException qua đúng handler

WAF rejected
    -> chỉ khi có quyết định từ WAF/gateway

CSRF rejected
    -> chỉ khi CsrfFilter/CsrfWebFilter xác nhận

Authorization denied
    -> chỉ khi authorization flow xác nhận
~~~

Không được đếm **một HTTP 400** thành **một Spring firewall rejection** chỉ vì request trông “lạ”. Cũng không coi mọi WAF 403 là CSRF 403. Khi log có sampling hoặc pipeline bị mất sự kiện, **absence of log không phải chứng cứ chắc chắn request không đến tầng đó**.

### 4.2. Schema sự kiện với field tối thiểu

~~~json
{
  "event": "http.security.request_rejected",
  "layer": "spring-servlet-firewall",
  "decision": "rejected",
  "reasonCategory": "unclassified",
  "methodClass": "UNSAFE",
  "pathGroup": "unmatched",
  "responseStatus": 400,
  "releaseRevision": "r63",
  "policyRevision": "firewall-v4",
  "environment": "prod",
  "requestId": "req-c27d",
  "source": "security-filter-chain"
}
~~~

Đây là **hợp đồng telemetry do đội vận hành tự định nghĩa**, không phải event mặc định phát từ Spring Security. Các trường chỉ dùng giá trị được chuẩn hóa và **có số lượng hữu hạn**.

- **layer**: edge-waf, ingress, servlet-container, spring-servlet-firewall, reactive-server, app-validation...
- **reasonCategory**: bắt đầu bằng **unclassified**; chỉ gắn loại chi tiết khi có nguồn reason code được xác minh mà không cần raw payload.
- **methodClass**: SAFE/UNSAFE/OTHER; hoặc method đã chuẩn hóa thuộc danh sách hữu hạn. Method string từ request cũng là untrusted input.
- **pathGroup**: unmapped, login, api-orders, static, health, other. Khi firewall reject trước MVC mapping, **không cố lấy MVC route template chưa được xác lập**.
- **responseStatus**: trạng thái handler thực sự trả; handler có thể tùy chỉnh theo contract.
- **requestId**: ID độc lập do edge/gateway tin cậy sinh, không dựa trên token/cookie.
- **policyRevision**: version của rules được duyệt; tránh log nguyên cấu hình môi trường chứa secrets.

### 4.3. Dữ liệu tuyệt đối không đưa vào audit mặc định

| Dữ liệu | Vì sao nguy hiểm |
| --- | --- |
| Full request URI/query/fragment | Có thể chứa token, user ID, PII hoặc ký tự chèn dòng |
| Raw Host/Origin/Referer | Có thể do client kiểm soát, chứa dữ liệu nhạy cảm, cardinality lớn |
| Cookie/JSESSIONID | Session credential |
| Authorization header/JWT/refresh token | Credential dùng truy cập trực tiếp |
| X-CSRF-TOKEN/X-XSRF-TOKEN | Token bảo vệ phiên |
| Raw header names/values bất kỳ | Injection/high cardinality; tên header cũng là untrusted input |
| Raw RequestRejectedException message | Có thể chứa path/raw value và control chars |
| Request body | Mật khẩu, CSRF token, business data |
| IP đầy đủ trong metrics labels | Tracking, cardinality cao; không đủ để quy kết attacker |
| Full user agent | Dễ bị giả mạo, cardinality cao |

**Không dùng exception.getMessage() làm Prometheus label** và không gửi nguyên request path vào bên thứ ba chỉ để phân loại. Nếu cần tra cứu chi tiết phục vụ incident, thực hiện theo quy trình truy cập hạn chế, retention tối thiểu và dữ liệu synthetic ở staging.

### 4.4. Phân loại reason không dựa trên cách cắt chuỗi mong manh

Khi cần taxonomy:

| Reason category được duyệt | Nguồn bằng chứng cần có |
| --- | --- |
| **method_not_allowed** | Policy explicit method allowlist, test xác nhận case |
| **invalid_path_representation** | Đã có reason code đáng tin hoặc test-bound classifier |
| **invalid_header** | Security exception hoặc edge parser reason đã xác nhận |
| **invalid_host** | Host allowlist explicit và reason code được kiểm chứng |
| **unclassified** | Mọi rejection chưa phân loại an toàn |
| **upstream_rejected** | Gateway/container xác nhận từ chối trước Spring |

**Không tự động map regex trên exception message tùy ý** thành class rồi dùng làm triage rule lâu dài. Message/format có thể thay giữa versions, và việc regex nội dung untrusted làm sai dữ liệu. Nếu muốn phân nhóm sâu, chỉ dùng logic **đã test** trên phiên bản đã pin hoặc source-specific telemetry an toàn.

## 5. Servlet: cấu hình StrictHttpFirewall theo nguyên tắc fail-closed

### 5.1. Giữ StrictHttpFirewall mặc định trừ khi có yêu cầu rõ

Spring Security Servlet cung cấp **StrictHttpFirewall**, với các ràng buộc cho URL/path, HTTP method và một số thành phần request. Không nên tùy ý thay bằng firewall dễ dãi chỉ để xử lý báo động.

Đoạn mã minh họa cách khai báo firewall và gắn nó vào **WebSecurity**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
class FirewallConfiguration {

    @Bean
    HttpFirewall httpFirewall() {
        // Giữ các kiểm tra StrictHttpFirewall mặc định.
        return new StrictHttpFirewall();
    }

    @Bean
    WebSecurityCustomizer firewallCustomizer(HttpFirewall firewall) {
        return web -> web.httpFirewall(firewall);
    }
}
~~~

**Ý nghĩa**: ứng dụng vẫn dùng HTTP firewall và có một nơi để review policy. Đoạn mã không tự thêm telemetry. Muốn log đúng RequestRejectedException, phải có **RequestRejectedHandler** được gắn vào **FilterChainProxy** thực sự nhận requests.

Các hệ thống có nhiều Servlet contexts, nhiều Spring Security chains hoặc custom FilterChainProxy cần test routing/bean wiring ở deployment thực tế. Đừng đăng ký nhiều filter proxies chồng lên nhau để “đo lại request”.

### 5.2. Host allowlist là một quyết định deployment

Khi cần hạn chế hostname, một **StrictHttpFirewall** có thể dùng predicate:

~~~java
import org.springframework.security.web.firewall.StrictHttpFirewall;

// Đoạn thay thế trong bean HttpFirewall, chỉ khi host policy đã được duyệt.
StrictHttpFirewall firewall = new StrictHttpFirewall();

firewall.setAllowedHostnames(host ->
    "api.example.com".equalsIgnoreCase(host)
    || "app.example.com".equalsIgnoreCase(host));

return firewall;
~~~

**Chỉ sử dụng danh sách host thực** sau khi kiểm tra proxy, port, virtual hosts và request routing. Nếu ingress chuyển Host thành tên service nội bộ, ví dụ có thể chặn toàn bộ traffic hợp lệ; phải điều chỉnh topology hoặc gateway forwarding policy an toàn.

**Host và X-Forwarded-Host từ Internet không phải bằng chứng đáng tin**. Ingress phải xóa/ghi đè forwarded headers không tin cậy. Firewall host allowlist không thay việc chặn host spoofing ở public edge.

### 5.3. Không mở các escape hatches một cách đại trà

Các method trên StrictHttpFirewall như **setAllowSemicolon**, **setAllowUrlEncodedSlash**, **setAllowBackSlash**, **setAllowUrlEncodedPercent** hoặc thay **allowed HTTP methods** có thể làm thay đổi mức chấp nhận URL.

Ví dụ anti-pattern cần tránh:

~~~java
// ANTI-PATTERN: không dùng làm "sửa nhanh" production.
StrictHttpFirewall firewall = new StrictHttpFirewall();

firewall.setAllowSemicolon(true);
firewall.setAllowUrlEncodedSlash(true);
firewall.setAllowBackSlash(true);
firewall.setAllowUrlEncodedPercent(true);
~~~

Cú pháp tương ứng phải được kiểm tra với version đã pin, vì tập method và default protections có thể thay đổi. **Dù các setters tồn tại, điều đó không có nghĩa nên bật chúng**.

Nếu một client legacy bắt buộc có semicolon hoặc encoded slash, phải hoàn thành các bước trước khi xét exception:

1. Định nghĩa **ngữ nghĩa URL chính xác** ở client, gateway, Servlet container, Spring Security matcher và MVC.
2. Xác định tầng nào đang reject; đừng nới firewall khi lỗi ở proxy/parser.
3. Chứng minh không có path-based authorization bypass khi biểu diễn URL được chấp nhận.
4. Cân nhắc đổi API design: chuyển dữ liệu path ambiguous sang query/body theo contract hoặc encode thành định danh không chứa separators.
5. Viết **negative tests** cho những biểu diễn có khả năng bypass, kể cả nhiều tầng encode.
6. Tạo security review với **scope, owner, expiry, rollback trigger**.
7. Canary theo một nhóm client/route sau khi đảm bảo chính sách phù hợp; không nới toàn bộ app không giới hạn.

### 5.4. Firewall và nhiều SecurityFilterChain

Ứng dụng có thể có:

~~~text
/api/web/**     -> session cookie + CSRF + browser authorization
/api/mobile/**  -> OAuth2 resource server Bearer-only
/internal/**    -> mTLS/private network + authorization
/actuator/**    -> management controls
~~~

**HttpFirewall ở FilterChainProxy ảnh hưởng cách đường dẫn được kiểm tra và matching cho các chains**. Một thay đổi normalization có thể khiến URL lạ match **mobile chain** thay vì **web chain**, hoặc bypass một rule dựa trên path.

Phải kiểm tra:

- Mỗi chain chọn đúng routes sau rewrite.
- Browser cookie không được dùng để xác thực Bearer-only endpoint.
- Unsafe browser POST thiếu CSRF vẫn bị chặn.
- Authorization theo role/scope vẫn áp trên canonical path.
- HTTP method matcher nhận method đúng sau gateway.
- Host/scheme sau trusted proxy không thể bị client spoof.
- URL bị từ chối **không thực hiện side effect**.

**Đừng dùng web.ignoring() cho toàn bộ API** để né firewall: bỏ qua Spring Security chain có thể bỏ qua những lớp protection thiết yếu. Nếu cần bỏ qua static assets, phải nắm rõ cả filter chain semantics và các headers được áp.

## 6. Quan sát rejection đúng đường qua RequestRejectedHandler

### 6.1. Handler chỉ ghi metadata được cho phép

Spring Security Servlet có interface **RequestRejectedHandler** để xử lý request bị firewall từ chối theo đường đã được wiring. Dưới đây là ví dụ handler **không ghi request URI hoặc exception message**, trả status 400 theo policy:

~~~java
import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.web.firewall.HttpStatusRequestRejectedHandler;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.RequestRejectedHandler;

public final class SafeRequestRejectedHandler
        implements RequestRejectedHandler {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeRequestRejectedHandler.class);

    private final RequestRejectedHandler delegate =
        new HttpStatusRequestRejectedHandler(400);

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            RequestRejectedException exception)
            throws IOException, ServletException {

        // Không log exception.getMessage() hoặc raw URI.
        // Method phải được chuẩn hóa theo allowlist.
        String method = normalizeMethod(request.getMethod());

        LOG.warn(
            "control=spring_http_firewall decision=rejected " +
            "reason=unclassified method={} status=400",
            method);

        delegate.handle(request, response, exception);
    }

    private static String normalizeMethod(String method) {
        if (method == null) return "OTHER";
        return switch (method) {
            case "GET", "HEAD", "OPTIONS", "POST", "PUT",
                 "PATCH", "DELETE" -> method;
            default -> "OTHER";
        };
    }
}
~~~

**Điểm quan trọng:** Tạo class/bean RequestRejectedHandler **không đảm bảo nó đã được FilterChainProxy sử dụng**. Cần nối vào đúng instance FilterChainProxy bằng extension/configuration mechanism được phiên bản Spring Security/Spring Boot đang dùng hỗ trợ, và **test handler thực sự nhận RequestRejectedException**. Không dựng FilterChainProxy thứ hai hoặc vô tình thay SecurityFilterChain hiện hữu chỉ để chèn telemetry.

Nếu dùng default handler của phiên bản đang triển khai, hãy xác minh **default response status và logging** trước khi thay. Một số cấu hình tự động có thể ghi request URI trong thông điệp lỗi; tránh bật TRACE/debug rộng rãi ở production.

### 6.2. Response phải đủ chẩn đoán nhưng không phản chiếu input

Một response an toàn thường chỉ cần:

~~~http
HTTP/1.1 400 Bad Request
Cache-Control: no-store
Content-Type: application/json

{"error":"INVALID_HTTP_REQUEST"}
~~~

Đây là **contract JSON minh họa**, không khẳng định HttpStatusRequestRejectedHandler tự tạo JSON body. Handler đơn giản có thể chỉ đặt status và không có body. Nếu chủ động trả JSON cho client API, dùng **mã lỗi ổn định** và request ID độc lập, không in URL/bad header/exception message.

Thêm một JSON body vào handler không tự làm browser CORS preflight hợp lệ hoặc chứng minh request vô hại. Nếu request không vượt qua firewall, **chưa đến tầng CSRF/authz**, nên không được dùng phản hồi này để tiết lộ security chain details.

### 6.3. Vòng đời response và trách nhiệm logging

RequestRejectedHandler có thể được gọi trước khi MVC controller, HandlerInterceptor hoặc @ControllerAdvice xử lý. Do đó:

- Không kỳ vọng **@ExceptionHandler(RequestRejectedException.class)** trong ControllerAdvice luôn nhận được exception từ FilterChainProxy.
- Một filter chỉ bao các MVC handlers có thể **không nhìn thấy** response do FilterChainProxy tạo.
- Một filter ở vị trí sớm có thể chỉ thấy **HTTP 400 tổng**, không thấy exception class.
- WAF/container reject xảy ra **ngoài JVM** sẽ không tạo Spring RequestRejectedException.
- Nếu handler mặc định ném exception thay vì chuyển thành status trong configuration cụ thể, cần xác minh behavior và vị trí catches.
- Với nhiều dispatches, một request có thể tạo nhiều events; tránh double count.
- Hãy tách **rejection event** từ **final HTTP status observation** để không nhân đôi số request.

### 6.4. Không tạo error endpoint làm bypass security

Đừng cấu hình một đường “debug rejected URL” public phản chiếu raw path/headers để thu thập dữ liệu. Những gì cần thường là **counter theo category, release, route group** và một synthetic test độc lập.

Nếu request bị reject vì CR/LF hoặc percent encoding nguy hiểm, việc log nguyên URL còn có thể gây **log injection**, khiến đội điều tra đọc nhầm event hoặc token trong dashboard.

## 7. Reactive/WebFlux: cùng mục tiêu giám sát nhưng không dùng StrictHttpFirewall Servlet

Spring Security Reactive dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **ServerWebExchange** và **WebFilters**. Tầng HTTP runtime thường là Reactor Netty hoặc một adapter Reactive khác. **StrictHttpFirewall, HttpServletRequest và RequestRejectedHandler trong phần trước thuộc Servlet**, không có nghĩa cứ đưa bean StrictHttpFirewall vào context WebFlux sẽ bảo vệ request tương đương.

### 7.1. Các tầng rejection ở WebFlux

~~~mermaid
flowchart TD
    A["Client"] --> B["CDN / WAF / Gateway"]
    B --> C["Reactive HTTP server parser"]
    C --> D["WebFlux WebFilter chain"]
    D --> E["Spring Security SecurityWebFilterChain"]
    E --> F["CSRF / Authn / Authz"]
    F --> G["Handler routing / validation"]
    B --> H["Edge deny event"]
    C --> I["Server parser error / close"]
    D --> J["Reactive status / exception"]
    E --> J
~~~

Lỗi URI malformed có thể bị **Reactor Netty HTTP parser** từ chối trước khi tạo ServerWebExchange. Một URL có path được chấp nhận ở Netty có thể vẫn không match router hoặc bị Gateway security policy chặn. Do đó khi giám sát Reactive cần tách:

- **Gateway/WAF rejection**.
- **HTTP server/parser 4xx hoặc connection failure**.
- **WebFilter/security rejection**.
- **WebFlux routing/argument-validation errors**.
- **CSRF/authentication/authorization denials** thuộc các filter riêng.

Không đặt tên mọi HTTP 400 Reactive là **RequestRejectedException**; exception đó gắn với Servlet HttpFirewall khi đường xử lý liên quan.

### 7.2. Ví dụ WebFilter quan sát HTTP 400 tổng

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
final class ReactiveBadRequestObserver implements WebFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(ReactiveBadRequestObserver.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange).doFinally(signal -> {
            HttpStatusCode status =
                exchange.getResponse().getStatusCode();

            if (status != null && status.value() == 400) {
                LOG.info(
                    "layer=reactive_webfilter status=400 " +
                    "reason=unclassified method={}",
                    safeMethod(exchange.getRequest().getMethod().name()));
            }
        });
    }

    private static String safeMethod(String method) {
        if (method == null) return "OTHER";
        return switch (method) {
            case "GET", "HEAD", "OPTIONS", "POST",
                 "PUT", "PATCH", "DELETE" -> method;
            default -> "OTHER";
        };
    }
}
~~~

Đây là **ví dụ status observer**, không phải WebFlux equivalent của StrictHttpFirewall. Lưu ý:

1. Request bị server parser hoặc WAF reject **trước khi vào WebFilter** sẽ không được quan sát ở đây.
2. Một HTTP 400 từ application validation cũng có thể tăng counter; **không gắn nhãn firewall confirmed**.
3. doFinally có thể được gọi khi chain bị cancel/error; trạng thái có thể chưa có hoặc được đổi bởi handler khác. Integration tests phải xác minh thời điểm đo.
4. Đừng block event loop hoặc ghi raw URL/request body trong callback.
5. Nếu đã có HTTP server/Micrometer observations, tránh double count khi thêm custom WebFilter.

Với các ứng dụng Reactive phát sinh lỗi do URL normalization, ưu tiên kiểm tra **Netty/gateway settings, WebFlux path parsing và authorization matchers**; không cố cài một servlet filter vào Netty.

### 7.3. Cấu hình SecurityWebFilterChain cho browser khác gì firewall?

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
    return http
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .build();
}
~~~

Ví dụ này **không tự xử lý invalid HTTP grammar** và không cấu hình CORS source hoặc authentication provider. Nó minh họa việc CSRF/authorization có **trách nhiệm độc lập** ở Reactive chain.

Khi có gateway WebFlux đứng trước Servlet backend, hai lớp có thể có **hai policy boundaries**. Hãy test canonical path ở gateway, đường Servlet container nhận và SecurityFilterChain backend; không coi request được Gateway cho qua nghĩa là backend firewall phải chấp nhận.

## 8. Đối chiếu proxy, container và HTTP firewall ở public edge

### 8.1. Chọn đúng điểm kiểm tra

| Điểm đo | Điều có thể biết | Không thể tự kết luận |
| --- | --- | --- |
| Client/browser DevTools | Final status, redirect, CORS/CSP behavior | Request có đến Spring FilterChainProxy không |
| CDN/WAF | WAF decision, cache/routing và edge parsing | RequestRejectedException trong JVM |
| Ingress/gateway | Rewrites, forwarded Host/Proto, upstream status | MVC matcher nhận path nào sau container |
| Servlet connector | HTTP syntax/limits, chuyển request thành HttpServletRequest | SecurityFilterChain chính xác nếu chưa qua proxy |
| Spring FilterChainProxy | Firewall rejection và chain match | Tất cả request bị WAF reject trước đó |
| MVC/controller | Handler mapping, business validation | Các request bị firewall chặn trước controller |
| Reactive HTTP server/WebFilter | Parser vs WebFilter outcome | StrictHttpFirewall của Servlet |

Khi điều tra một request bị chặn, chỉ nên kết luận **tầng nào** khi có đủ status/trace evidence từ tầng đó. Một HTTP 403 trả về có thể xuất phát ở CDN, không phải Spring Security.

### 8.2. So sánh path trước và sau rewrite mà không log raw dữ liệu

Trong staging có request synthetic cố định, ví dụ:

~~~text
synthetic_test_id = url-encoding-case-02
expected gateway route = api-service
expected servlet path group = items
expected result = rejected
reason category = invalid_path_representation
~~~

Ở production, để giám sát dài hạn, chỉ lưu **synthetic test ID, route group, release/policy revision và result**. Không thu raw request-target của mọi user. Với incident cần xem một URL thật, thực hiện quy trình truy cập giới hạn, scrub query và giữ retention tối thiểu.

### 8.3. Phân biệt normalization mismatch và lỗi ứng dụng

Một triệu chứng phổ biến:

1. Client legacy gửi request URI có encoded slash.
2. Ingress bảo toàn ký tự encoded, nhưng Servlet connector giải mã hoặc reject.
3. Nếu request tới Spring, StrictHttpFirewall có thể reject trước MVC matcher.
4. Team ứng dụng chỉ thấy “HTTP 400” và yêu cầu bật setAllowUrlEncodedSlash(true).
5. Sau khi bật, một đường path có thể được proxy matcher và backend authorization hiểu khác nhau.

**Bước đúng:** Xem raw request handling qua **test synthetic** ở từng tầng, xác định contract URL mong muốn, sửa client/path encoding hoặc proxy rewrite trước. Chỉ nới firewall sau **security review và negative matchers tests**.

### 8.4. X-Forwarded-* và Host spoofing

Một reverse proxy có thể truyền:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
Forwarded: proto=https;host=api.example.com
~~~

Những header này chỉ có thể được tin khi **trusted edge đã xóa/ghi đè giá trị không đáng tin từ client**. Không mặc định một request có X-Forwarded-Proto: https đã đi qua TLS. Nếu Host spoofing chưa được kiểm soát, application redirect và URL generation có thể bị thao túng.

StrictHttpFirewall host allowlist là một lớp hỗ trợ; **public edge cần host routing validation** và ứng dụng phải có policy cho canonical host/forwarded behavior.

### 8.5. CORS và browser error có thể che khuất status firewall

Một SPA cross-origin có thể nhận “CORS error” trong console khi **preflight OPTIONS** bị WAF/firewall reject trước khi actual POST được gửi. Chẩn đoán như sau:

1. Browser Network cho thấy có OPTIONS hay không.
2. Xác minh OPTIONS thuộc danh sách method hợp lệ và CORS filter order.
3. Xem status/Allow-Origin/Allow-Headers/Allow-Methods tại public edge.
4. So gateway, container và app events để xác định lớp reject.
5. Kiểm tra POST chỉ sau khi preflight thành công; không suy đoán CSRF POST từ OPTIONS.
6. Không mở CORS wildcard credentials hoặc tắt CSRF để làm biến mất thông báo lỗi.

Một GET thành công bằng curl không chứng minh browser CORS/cookie/CSP hoạt động đúng.

## 9. Kiểm thử StrictHttpFirewall trực tiếp ở Servlet

### 9.1. Unit test cho HTTP method không được phép

Với Spring Security Test/Spring Test trong classpath, có thể test **chính firewall**, không cần server chạy thật:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

class StrictHttpFirewallUnitTests {

    private final StrictHttpFirewall firewall =
        new StrictHttpFirewall();

    @Test
    void traceMethodIsRejectedByDefaultPolicy() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("TRACE", "/api/orders");

        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(request));
    }
}
~~~

Test trên **chứng minh quy tắc firewall ở phạm vi unit**, không chứng minh Servlet connector hoặc gateway cùng có behavior. Nếu thay allowed methods trong production, test cần dựa trên **policy explicit đã duyệt** chứ không chỉ default mơ hồ.

### 9.2. Unit test cho semicolon/matrix parameter

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Test
void semicolonInServletPathIsRejectedByStrictDefault() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();

    MockHttpServletRequest request =
        new MockHttpServletRequest(
            "GET", "/api/items;revision=2");

    request.setServletPath("/api/items;revision=2");

    assertThrows(RequestRejectedException.class,
        () -> firewall.getFirewalledRequest(request));
}
~~~

Đoạn này là **thân test** thuộc class có JUnit; cần dùng default StrictHttpFirewall và Spring Test. Một số container có thể xử lý semicolon trong request target trước Spring, vì vậy MockHttpServletRequest chỉ là kiểm tra **firewall unit**, không đại diện public edge.

### 9.3. Unit test cho request hợp lệ

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Test
void ordinaryGetPassesFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();

    MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/api/items");

    assertDoesNotThrow(
        () -> firewall.getFirewalledRequest(request));
}
~~~

**Không coi unit test pass là authorize request**. Sau firewall còn SecurityFilterChain, authentication, authorization, CSRF và handler validation.

### 9.4. Testing RequestRejectedHandler ghi sự kiện an toàn

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.firewall.RequestRejectedException;

@Test
void rejectionHandlerReturns400WithoutEchoingInput()
        throws Exception {

    SafeRequestRejectedHandler handler =
        new SafeRequestRejectedHandler();

    MockHttpServletRequest req =
        new MockHttpServletRequest("GET", "/api/items");

    MockHttpServletResponse res =
        new MockHttpServletResponse();

    handler.handle(req, res,
        new RequestRejectedException("synthetic malformed URI"));

    assertEquals(400, res.getStatus());
    // Thực tế còn phải kiểm tra audit sink không có raw URI,
    // exception message, Cookie, Authorization hoặc token.
}
~~~

Đây chỉ xác nhận **handler độc lập** hoạt động. Bài test tích hợp tiếp theo phải chứng minh **FilterChainProxy thật** đã gắn handler đó, và chỉ request bị firewall reject mới tăng counter confirmed firewall.

### 9.5. Integration test MockMvc cần cấu hình HTTP security thật

Khi MockMvc được tích hợp Spring Security filters:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;

// Test trong @SpringBootTest + @AutoConfigureMockMvc,
// với HttpStatusRequestRejectedHandler trả 400 đã được gắn thật.
@Test
void badMethodRejectedBeforeController() throws Exception {
    mvc.perform(request(HttpMethod.TRACE, "/api/orders"))
        .andExpect(status().isBadRequest());
}
~~~

**Kết quả phụ thuộc cấu hình/phiên bản cụ thể.** Nếu handler để exception đi ra thay vì chuyển 400, assertion cần dựa trên hợp đồng đã duyệt và đường xử lý được test. Test thêm **metrics/audit** để xác nhận event spring_firewall_rejected, không chỉ HTTP status.

Đối với encoded path, **MockMvc có thể không tái hiện đúng Servlet container/proxy decoding**. Dùng real server integration tests qua staging gateway cho các case cần chứng minh cross-tier path normalization.

### 9.6. Kiểm thử positive + negative sau một thay đổi firewall

Một change firewall cần kiểm thử ít nhất:

| Test | Điều bắt buộc |
| --- | --- |
| URL thông thường, GET hợp lệ | Không bị chặn nhầm |
| POST cookie-auth không CSRF | Bị từ chối, không side effect |
| POST token đúng nhưng role không đủ | Bị authorization chặn |
| Encoded separator/semicolon case đã duyệt | Kết quả đúng theo contract qua cả proxy/container |
| Path traversal hoặc double decoding case | Không bypass securityMatcher/authorization |
| TRACE/unsupported methods | Bị từ chối đúng policy |
| OPTIONS CORS preflight hợp lệ | Không bị firewall chặn sai |
| Unknown Host nếu policy enforce | Không có host spoofing bypass |
| URLs dài/headers quá giới hạn | Tầng thực sự từ chối được xác định |
| Rejected request telemetry | Không log raw URI/headers/token |
| Nhiều SecurityFilterChain | Không route sai sang chain có quyền yếu hơn |

Không bỏ negative tests để “tránh 400” khi một API mới ra mắt.

## 10. WebTestClient, Reactive HTTP parser và gateway boundaries

### 10.1. WebFlux không tự có Servlet StrictHttpFirewall

WebFlux sử dụng **ServerHttpSecurity, SecurityWebFilterChain, ServerWebExchange** và một Reactive HTTP server như Reactor Netty. Một request có HTTP grammar hoặc URI bất thường có thể bị từ chối **trước khi một ServerWebExchange được tạo**; một request khác có thể tới WebFilter nhưng bị router hoặc Spring Security từ chối.

Vì thế **WebTestClient in-memory không phải kiểm thử cho StrictHttpFirewall của Servlet**. Nó phù hợp cho reactive routing, CORS, CSRF và authorization. Muốn xác minh HTTP parser, chạy thử trên **real embedded Reactive server** và qua gateway/ingress giống production.

### 10.2. Test CSRF WebFlux độc lập với firewall

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import java.util.Map;

// Đoạn test khi ứng dụng có POST /api/orders.
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

**403 do CsrfWebFilter không phải RequestRejectedException của Servlet**. Cần assert không có side effect ở request bị từ chối và test authorization riêng khi CSRF đúng. Helpers mockUser/csrf không đại diện cho browser cookie/WebSession lifecycle đầy đủ.

### 10.3. Real Reactive server test qua nhiều tầng

Để xác định một request bất thường bị reject ở đâu:

1. Dùng synthetic request-target đã được duyệt trên staging.
2. Test qua public HTTPS edge rồi test direct embedded Reactive server trong mạng được kiểm soát.
3. Kiểm tra WAF/proxy decision, Reactor Netty/server parser outcome và WebFilter status nếu có.
4. Test URL hợp lệ ở route tương ứng còn hoạt động.
5. Kiểm tra path normalization có tạo securityMatcher/authorization bypass hay không.
6. Không dùng Servlet RequestRejectedHandler để giải thích Reactive server 400.

Khi **WebFilter không có event**, request có thể bị parser từ chối trước nó, hoặc telemetry có sampling. **Thiếu log không phải bằng chứng tuyệt đối** cho tầng reject.

### 10.4. WebFlux Gateway trước Servlet backend

~~~mermaid
flowchart LR
    A["Client"] --> B["WebFlux API Gateway"]
    B --> C["Servlet Spring backend"]
    B --> D["Gateway HTTP/parser metrics"]
    C --> E["StrictHttpFirewall + Servlet chains"]
    E --> F["RequestRejectedHandler metrics"]
~~~

Một URL có thể được gateway chấp nhận nhưng backend Servlet từ chối. Đối chiếu **request-target semantics trước/sau rewrite**, không chỉ HTTP status. Nếu gateway reject trước backend, không có Spring Servlet RequestRejectedException.

## 11. Synthetic probes tại public edge

### 11.1. Đo đúng điểm, không log dữ liệu

| Probe | Nguồn kết quả | Giới hạn |
| --- | --- | --- |
| StrictHttpFirewall unit test | Java object firewall | Không thấy HTTP parser/proxy |
| MockMvc | Servlet FilterChainProxy nếu tích hợp đúng | Không tái hiện đầy đủ connector encoding |
| Real Servlet server | Connector + Spring | Không bao gồm CDN/WAF |
| WebTestClient | Reactive WebFilter/security | Không kiểm tra Servlet HttpFirewall |
| Public HTTPS probe | Final HTTP status/headers | Không tự biết exception class |
| WAF/ingress metrics | Edge decision và URL rewrite class | Không thay application authz test |
| Browser DevTools | CORS/cookie/CSP/HSTS behavior | Không cho biết backend stack trace |

### 11.2. Probe cố định cho semicolon trên staging

~~~bash
#!/usr/bin/env bash
set -euo pipefail

test_case="semicolon-path"
target="https://staging.example.com/api/items;revision=2"

status="$(curl --silent --show-error \
  --path-as-is --globoff --max-time 10 \
  --output /dev/null --write-out '%{http_code}' "$target")"

printf 'case=%s status=%s\n' "$test_case" "$status"
~~~

Chỉ dùng **route thử nghiệm và môi trường được phép**. Không fuzz URLs bừa bãi trên production. Option --path-as-is tránh một số client normalization nhưng không buộc mọi proxy/connector giữ nguyên byte. **Kỳ vọng không phải luôn HTTP 400**: server/gateway có thể reject khác nhau; cần contract về **security outcome và layer**.

Lệnh trên không in body, Cookie hay Authorization. Không thêm --insecure để bỏ xác minh TLS, không dùng token thật hoặc ghi raw header dump vào CI logs.

### 11.3. Positive probe phải chạy cùng negative probe

~~~bash
#!/usr/bin/env bash
set -euo pipefail

target="https://staging.example.com/public/ping"
status="$(curl --silent --show-error --max-time 10 \
  --output /dev/null --write-out '%{http_code}' "$target")"

if [ "$status" != "200" ]; then
  printf 'FAIL legitimate endpoint status=%s\n' "$status"
  exit 1
fi
printf 'PASS legitimate endpoint\n'
~~~

Đây là **endpoint ví dụ**, không nên tạo public diagnostic endpoint lộ secret chỉ để chạy smoke test. Kết hợp test URL bình thường và URL bất thường để phát hiện cả **mở lỗ hổng** lẫn **chặn nhầm người dùng hợp lệ**.

### 11.4. Một HTTP 400 không đủ chứng minh StrictHttpFirewall làm đúng

400 có thể do StrictHttpFirewall, Servlet connector, WAF hoặc business validation. Muốn xác nhận firewall, cần **đúng RequestRejectedHandler event** hoặc unit/integration test. Muốn chứng minh không có bypass, cần **authorization matcher và database side-effect tests**.

## 12. Dashboard và metrics phân loại theo tầng

### 12.1. Tên metrics chỉ là đề xuất, không phải mặc định Spring Security

~~~text
http_security_rejections_total{
  environment="prod",
  layer="spring-servlet-firewall",
  reason="unclassified",
  path_group="unmapped",
  method_class="OTHER",
  release="r63"
}

http_security_rejections_total{
  environment="prod",
  layer="edge-waf",
  reason="invalid-request",
  path_group="public-api",
  method_class="UNSAFE",
  release="edge-v4"
}

http_security_contract_probes_total{
  environment="prod",
  probe_group="url-normalization",
  outcome="pass",
  policy_revision="firewall-v4"
}

security_policy_revision_match{
  environment="prod",
  workload="http-protection-api",
  outcome="pass"
}
~~~

**Chỉ gắn layer=spring-servlet-firewall khi RequestRejectedException thực sự đã được xác nhận**, không gán dựa trên status 400. Các metrics này cần được dự án instrument hoặc lấy từ hệ thống observability cụ thể.

### 12.2. Labels thấp cardinality và an toàn

| Nên dùng | Không dùng làm label |
| --- | --- |
| environment, workload, release/policy revision | raw URL/query hoặc path chứa userId |
| layer: edge/connector/spring/reactive | exception message |
| reason category hữu hạn | raw Host/Origin/Referer |
| method class hoặc allowlisted HTTP methods | method string không kiểm soát |
| path group được định nghĩa trước | request URI chưa chuẩn hóa |
| outcome/status class | Cookie, CSRF token, JWT, Authorization |
| static synthetic probe ID | request ID, trace ID, IP thô |

Correlation ID có thể ở **log/trace được kiểm soát**, không phải Prometheus label. Nếu cần điều tra theo IP/địa chỉ mạng, áp chính sách quyền truy cập/retention riêng, tránh nhãn có cardinality cao.

### 12.3. Định nghĩa tỷ lệ đúng mẫu số

\[
\text{Spring firewall reject rate} =
\frac{\text{RequestRejectedException được xác nhận}}
{\text{Requests thực sự đến FilterChainProxy}}
\]

Không dùng toàn bộ request CDN làm mẫu số nếu phần lớn đã bị WAF chặn trước Spring. Nếu metrics đến từ sampled logs, cần biết sampling rate và không cộng thẳng với full request counts.

Dashboard nên theo dõi **rejection confirmed**, **4xx tổng**, **edge parser/WAF denials**, **normal user-flow success**, **canary vs control**, **config drift** và **negative security probe pass/fail** trên cùng release timeline.

### 12.4. Phân biệt tăng rejection vì phòng vệ hoạt động với lỗi chức năng

Một bot scan có thể làm rejection tăng mà legitimate flows vẫn ổn định. Một lỗi gateway normalization có thể làm rejection tăng ít nhưng khiến **checkout/login của một browser** thất bại. Vì vậy alert phải xem **route criticality, baseline, sample size, release timing, business SLO và security negative tests**, không chỉ đếm HTTP 400.

## 13. Regression hay traffic bất thường: ma trận phân loại

### 13.1. Dấu hiệu nghiêng về lỗi tích hợp

- Rejections tăng ngay sau **frontend, gateway, Servlet container hoặc Spring Security version** deploy.
- Lỗi tập trung ở một route và một phiên bản client hợp lệ.
- OAuth/login callback hoặc static asset URL bị chặn do proxy rewrite.
- Pod A chấp nhận nhưng pod B từ chối vì policy revision khác.
- Host allowlist mới không phù hợp canonical host mà ingress truyền.
- Hệ thống legacy phát semicolon/matrix-style URL trái contract.
- Valid business flow success giảm cùng lúc với firewall denies.

### 13.2. Dấu hiệu nghiêng về scanning/probing cần điều tra

- Nhiều URI lạ, encoded separators, traversal, invalid methods và headers qua nhiều route.
- WAF và Spring rejects cùng tăng nhưng legitimate user flows ổn định.
- Nhiều lần thử tiếp sau khi server đã từ chối.
- Request path/method không giống bất kỳ client được duyệt nào.
- Tốc độ, phân bố route hoặc các dấu hiệu automation khác thường.

**Không kết luận từ IP, quốc gia, User-Agent hoặc một request đơn lẻ**. NAT/proxy, internal security scans và client bugs đều có thể giống scanning.

### 13.3. Bảng hành động

| Quan sát | Giả thuyết ưu tiên | Xác minh |
| --- | --- | --- |
| Rejects tăng sau ingress change | URL rewrite regression | Synthetic path cases qua hai revisions |
| 400 chỉ ở một SPA route | Client URL contract | Client release và test browser |
| 403 WAF, không có Spring event | Edge deny | WAF decision, sampling |
| Connector 400 trước app | HTTP grammar/limit | Connector metrics và controlled reproducer |
| Chỉ một pod từ chối | Runtime policy drift | Artifact/config revision |
| OPTIONS bị chặn | CORS/method/proxy policy | OPTIONS không Cookie, Allow-Headers |
| POST CSRF 403 | CSRF chứ không firewall | CsrfFilter/handler |
| Path bất thường pass vào chain yếu | Matcher bypass tiềm tàng | Authz/CSRF negative tests |
| Rejects ở nhiều random routes | Có thể scanning | WAF trends và business health |

### 13.4. Không “chữa” lỗi bằng cách nới mọi URL

Quy trình khắc phục ưu tiên: xác nhận tầng → tái hiện synthetic → xác định URL semantics → sửa client/proxy → kiểm authorization matchers → security review nếu cần exception → canary + negative tests → rollback khi vi phạm gate.

**Không tự động bật setAllowSemicolon(true), setAllowUrlEncodedSlash(true) hoặc thay StrictHttpFirewall bằng cấu hình dễ dãi** để làm số 400 giảm. Hệ quả có thể nghiêm trọng hơn lỗi request bị chặn.

## 14. Deployment gates và alerting: đo cả an toàn lẫn chức năng

### 14.1. Gate trước rollout thay đổi firewall hoặc gateway

~~~mermaid
flowchart LR
    A["Code/config change"] --> B["Security review + URL contract"]
    B --> C["Unit + integration tests"]
    C --> D["Staging real server/gateway"]
    D --> E["Canary với positive/negative probes"]
    E --> F{"Policy và user-flow gates PASS?"}
    F -->|Có| G["Rollout rộng"]
    F -->|Không| H["Stop và triage"]
    H --> I["Rollback artifact + config + edge policy"]
    I --> D
    G --> J["Periodic drift monitoring"]
~~~

Một deployment gate nên kiểm tra:

1. **Policy revision** được review; các ngoại lệ URL/HTTP methods có owner, thời hạn và phạm vi.
2. **StrictHttpFirewall unit tests** reject các trường hợp không được phép và nhận request bình thường.
3. **MockMvc + real Servlet server** test FilterChainProxy và RequestRejectedHandler được wiring thật.
4. **Reactive WebFilter/Netty/gateway tests** cho ứng dụng WebFlux, không dùng Servlet firewall giả.
5. **Path normalization cross-tier tests** giữa client/gateway/container/security matcher.
6. **Security negative tests** bảo đảm encoded/traversal variants không bypass authorization hoặc CSRF.
7. **Positive user flows** như login, checkout, upload và callback không bị chặn nhầm.
8. **CORS preflight** OPTIONS vẫn chạy khi cần và không bypass authentication/CSRF ở request thực.
9. **Audit redaction**: không log raw URL/headers, Cookie, JWT, CSRF token hoặc request body.
10. **Canary/control metrics** đủ để phát hiện regression và có owner dừng/rollback.

### 14.2. Các tình huống cần dừng rollout ngay

- Một request URI bất thường **bypass SecurityFilterChain/Authorization** hoặc khiến route browser không cần CSRF mà vẫn thay đổi dữ liệu.
- Tắt hẳn HttpFirewall hoặc nới URL/method allowlist ngoài phạm vi được duyệt.
- Một pod/region dùng policy yếu hơn các instance khác vì config drift.
- Triển khai logging/trace mới bắt đầu lưu token/session/Authorization/raw URL chứa secret.
- Một flow trọng yếu của user hợp lệ bị chặn sau canary, ví dụ login callback hoặc checkout.
- WAF/gateway path rewrite khiến proxy và application đánh giá authorization trên **hai canonical paths khác nhau**.
- Các negative probes trước đây bị từ chối nay đi tới business handler không phù hợp.

Không nhất thiết phải rollback chỉ vì confirmed rejection count tăng. Nếu đó là request không hợp lệ bị chặn và các security/business gates vẫn đạt, có thể phòng vệ đang hoạt động đúng. Alert cần **baseline, release correlation, traffic class và business SLO**.

### 14.3. Alert severity dựa trên nguy cơ

| Tình huống | Ưu tiên xử lý gợi ý |
| --- | --- |
| Authz/CSRF bypass do URL normalization | Critical; stop rollout và điều tra ngay |
| Invalid Host được chấp nhận ngoài policy, redirect nguy hiểm | High/Critical theo blast radius |
| Lộ JSESSIONID/JWT/CSRF token qua firewall logs | High; đánh giá incident scope |
| Legitimate login/checkout bị reject hàng loạt | High; dừng canary/khôi phục flow |
| Một region mất firewall policy | High; cô lập drift |
| WAF/parser rejections tăng do scanning, user flows bình thường | Điều tra/tối ưu bot controls, không vội nới firewall |
| Legacy client duy nhất gặp semicolon reject | Triage tương thích, sửa URL contract có kế hoạch |
| Metrics handler không nhận event nhưng HTTP status vẫn đúng | Investigate observability wiring, không mặc định bypass |

Severity cụ thể phụ thuộc threat model và SLO thực, không có một threshold áp cho mọi công ty.

### 14.4. Rollback không chỉ là chạy lại JAR cũ

Một release có thể đồng thời thay:

- Spring Security/BOM và Servlet container.
- StrictHttpFirewall configuration/RequestRejectedHandler.
- Gateway rewrite rules, WAF allowlist, CDN behavior và TLS termination.
- Frontend URL generation/API path contract.
- SecurityFilterChain matchers, CSRF/CORS policy.
- Session cookie domain và session store routing.

Vì vậy rollback phải phục hồi **artifact + app config + proxy/WAF policy + frontend contract** tương thích. CDN cache hoặc browser session vẫn có thể giữ trạng thái cũ. Sau rollback cần chạy **normal route positive probes, encoded-path negative probes, CSRF/authz side-effect tests và header/cookie checks**; pod healthy không đủ.

## 15. Runbook điều tra request bị firewall từ chối

### 15.1. Runbook A — HTTP 400 tăng sau nâng Spring Security hoặc Servlet container

**Dấu hiệu:** Sau upgrade, nhiều 400 xuất hiện ở các routes trước đó hoạt động.

1. Ghi **release time**, dependency versions, container/runtime revision và config revision.
2. Đếm **confirmed RequestRejectedException** riêng khỏi container/parser/gateway 400.
3. Phân nhóm theo **path group, method class và client release**, không lưu raw request-target.
4. Tái hiện bằng **synthetic request URL** trong staging với cùng connector/proxy topology.
5. So behavior giữa phiên bản cũ/mới và xem thay đổi default validation có thể liên quan.
6. Với request hợp lệ, sửa URL contract hoặc proxy normalization; đánh giá trường hợp cần ngoại lệ hẹp.
7. Chạy security negative tests sau bất kỳ thay đổi allowlist nào.
8. Nếu flow quan trọng bị phá, stop rollout hoặc rollback đã phê duyệt.
9. Không khẳng định framework version mới “kém an toàn” chỉ vì reject nhiều hơn; xem nguyên nhân và semantics.

### 15.2. Runbook B — URL chứa semicolon/encoded slash bị reject

**Dấu hiệu:** Một client cũ gửi URI đặc thù và thấy 400.

1. Xác định URL contract có **thực sự cần** semicolon hoặc encoded slash không.
2. Test qua CDN/WAF, ingress, real Servlet container và FilterChainProxy trong staging.
3. Tách trường hợp **parser reject trước Spring** khỏi **StrictHttpFirewall reject**.
4. Đối chiếu Spring securityMatcher và MVC handler mapping có nhìn cùng canonical path không.
5. Ưu tiên sửa client dùng path/identifier không ambiguous hoặc chuyển dữ liệu cần thiết sang query/body theo hợp đồng API.
6. Nếu phải chấp nhận tạm, cần security review, negative authorization tests và expiry.
7. Không bật nhiều setAllow* flags toàn cục một lúc; mỗi exception làm tăng phạm vi cần test.
8. Kiểm tra các routes nhạy cảm vẫn bị CSRF/authz chặn khi dùng path variants.

### 15.3. Runbook C — WAF 403 tăng nhưng Spring không có RequestRejectedException

**Dấu hiệu:** Public edge báo 403, backend không thấy confirmed firewall events.

1. Kiểm tra **WAF rule category, edge request count và correlation ID**.
2. Kiểm tra có request được forward lên upstream không; phân biệt sampling/drop logs.
3. Nếu reject ở WAF, không sửa StrictHttpFirewall để “chữa” 403.
4. So WAF policy revision với frontend release và traffic baseline.
5. Với false positive ở client hợp lệ, đánh giá điều chỉnh **narrow WAF rule** qua review và canary.
6. Test untrusted requests vẫn bị chặn và legitimate flows còn hoạt động.
7. Chỉ kích hoạt incident chống lạm dụng khi có đủ bằng chứng, không gán attacker theo IP đơn lẻ.

### 15.4. Runbook D — CORS preflight OPTIONS bị từ chối

**Dấu hiệu:** Browser báo CORS/preflight failure, API route vẫn hoạt động bằng Postman/curl GET.

1. Dùng synthetic **OPTIONS không Cookie**, với Origin, Access-Control-Request-Method và Allow-Headers mong muốn.
2. Kiểm tra OPTIONS bị **StrictHttpFirewall/method policy**, WAF, authentication hay CorsFilter chặn.
3. Xem CORS source có exact trusted origin, method và custom headers đúng không.
4. Kiểm tra Spring CORS xử lý trước auth, gateway không redirect preflight đến login.
5. Khi OPTIONS pass, test actual POST với CSRF/authorization; hai bước không thay thế nhau.
6. Không sửa bằng Allow-Origin wildcard có credentials hoặc disable CSRF.
7. Test origin ngoài allowlist vẫn bị browser chặn quyền đọc credentialed response.

### 15.5. Runbook E — Một pod/region reject khác các pod khác

**Dấu hiệu:** Cùng flow, cùng client có lúc pass lúc 400, phụ thuộc instance/region.

1. So artifact digest, Spring BOM, Java/container version và config revision.
2. Kiểm tra HttpFirewall host/method/path settings, gateway route và WAF rules theo region.
3. Xem có rollout partial, environment override, manual hotfix hoặc cache chưa hết hạn không.
4. Dùng synthetic probes cố định với **mỗi nhóm instance**, không thu raw customer URL.
5. Nếu instance có bảo vệ yếu hơn, ngừng traffic vào instance theo runbook.
6. Redeploy immutable config qua pipeline; không sửa tay ở production rồi quên đồng bộ.
7. Kiểm lại request success, negative authorization cases, session/CSRF và public edge.
8. Thêm policy-revision drift alert.

### 15.6. Runbook F — Rejections tăng do quét URL bất thường

**Dấu hiệu:** Nhiều URI malformed và unsupported methods trong một khoảng thời gian, nhưng business SLO không giảm.

1. Xác minh nguồn event: WAF, container hay Spring firewall.
2. Phân loại theo method class, path group, reason category và release, không lưu raw payload.
3. So cùng thời điểm có authn/authz denials, rate limit hits và những route nhạy cảm bị thử không.
4. Kiểm tra negative probes của firewall/authz vẫn PASS; không có side effects.
5. Đánh giá hạn chế tốc độ, edge bot defenses, limits và khả năng quá tải.
6. Không mở firewall chỉ để giảm số rejects; đó có thể làm mất lớp bảo vệ cần thiết.
7. Theo dõi false positives cho người dùng NAT/proxy và traffic của security scanners nội bộ.
8. Escalate incident khi có dấu hiệu bypass, credential leak, availability impact hoặc thành công không được phép.

### 15.7. Runbook G — HTTP 400 trước controller, ControllerAdvice không bắt được

1. Xác nhận request có đi qua FilterChainProxy không.
2. Nếu RequestRejectedException, kiểm tra **RequestRejectedHandler thực sự được wiring**.
3. Nếu Servlet container parser trả 400 trước filter, xem connector telemetry và HTTP grammar.
4. Nếu gateway trả error, sửa đúng gateway owner; thay ControllerAdvice không giải quyết.
5. Không tạo custom filter thứ hai chỉ để bắt một exception ngoài vùng nó quan sát.
6. Test một request malformed cùng một request valid để chứng minh không chặn nhầm.
7. Bổ sung alert **source-aware** thay vì đếm status tổng.

### 15.8. Runbook H — Raw URL hoặc token lộ trong firewall log

1. Tạm dừng logger/trace/body capture đang chứa **raw request-target hoặc secrets**.
2. Giới hạn quyền truy cập logs/APM, không copy nội dung nhạy cảm vào chat/ticket.
3. Xác định loại thông tin, người/hệ thống có quyền đọc, thời điểm và retention.
4. Nếu có session/JWT/refresh credentials bị lộ, thực hiện session invalidation/credential rotation theo incident policy.
5. Nếu URL chứa user data/CSRF token, scrub và đánh giá nguy cơ/obligations theo phạm vi.
6. Sửa logging bằng allowlist low-cardinality fields, không dump exception.getMessage().
7. Chạy **synthetic canary trong staging** xác minh log redaction ở edge, Spring và APM.
8. Theo dõi kết quả remediation, bảo đảm vẫn có request ID và rejection reason category hữu ích.

### 15.9. Cây quyết định điều tra nhanh

~~~mermaid
flowchart TD
    A["Request bất thường bị từ chối"] --> B{"Có confirmed Spring RequestRejectedException?"}
    B -->|Có| C["StrictHttpFirewall/Servlet integration"]
    B -->|Không| D{"Edge hoặc container báo reject?"}
    D -->|Có| E["WAF/Ingress/Parser telemetry"]
    D -->|Chưa rõ| F["Kiểm tra correlation và sampling"]
    C --> G{"Valid user flow bị ảnh hưởng?"}
    G -->|Có| H["Reproduce URL contract, rollback nếu cần"]
    G -->|Không| I["Đối chiếu scanning, baseline, SLO"]
    E --> J["Sửa đúng layer, không nới firewall sai chỗ"]
    F --> J
    H --> K["Negative matcher/CSRF/authz tests"]
    I --> K
    J --> K
~~~

Một sự cố có thể có **hai nguyên nhân đồng thời**: proxy rewrite làm hỏng client hợp lệ và bot scanning khiến rejection tăng. Dùng evidence phân tầng để tránh giải thích mọi request bằng một giả thuyết.

## 16. Bài tập thực hành

**Bài A — Unit StrictHttpFirewall:** Viết tests cho TRACE, semicolon và URL bình thường. Chứng minh request không hợp lệ bị RequestRejectedException nhưng request bình thường đi tiếp.

**Bài B — RequestRejectedHandler:** Viết handler trả 400, log method class/reason không nhạy cảm. Test không bao giờ xuất raw URL, exception message, Cookie hoặc CSRF token.

**Bài C — Wiring audit:** Gắn handler vào đúng FilterChainProxy trong app thử nghiệm. Chứng minh unit handler test pass **chưa đủ** nếu production proxy không thực dùng handler.

**Bài D — Nhiều SecurityFilterChain:** Một app có /api/web/** cookie session và /api/mobile/** Bearer-only. Test encoded path không khiến route cookie đi vào chain mobile thiếu CSRF.

**Bài E — Proxy normalization:** Gửi một synthetic encoded path case qua ingress rồi direct Servlet server. So status và nơi reject, không ghi raw dữ liệu thật.

**Bài F — Semicolon legacy:** Một client dùng matrix parameter. Lập migration API contract và kế hoạch exception có security review, negative tests và sunset date.

**Bài G — CORS/OPTIONS:** Một frontend khác origin bị preflight reject. Chẩn đoán WAF/method/CORS filter trước khi xét CSRF của actual POST.

**Bài H — Reactive:** Dùng WebTestClient kiểm tra WebFlux routing và CSRF; dùng real Reactor Netty server/gateway để thử malformed request-target. Giải thích vì sao không thể gọi đó là StrictHttpFirewall.

**Bài I — HTTP logs privacy:** Gửi synthetic URL có query chứa một canary string trong staging. Xác minh event Spring/WAF/APM không ghi nguyên query/string đó.

**Bài J — Alerting:** Tạo metrics theo layer/reason/release/route group. Thiết kế ngưỡng phát hiện scanning và lỗi integration, không dùng raw IP/token làm Prometheus labels.

**Bài K — Canary:** Một release mới làm normal login callback bị 400, còn encoded traversal requests vẫn bị reject. Định nghĩa stop gate và rollback không mở firewall toàn cục.

**Bài L — Drift:** Pod A và B có firewall policy revisions khác nhau. Dùng synthetic probes để chứng minh drift rồi redeploy đúng artifact/config qua pipeline.

**Bài M — Incident tabletop:** WAF tăng 403 do scanning cùng lúc một Spring Security upgrade tăng 400 ở route checkout hợp lệ. Lập thứ tự triage theo bằng chứng và user-flow impact.

**Bài N — Defense in depth:** Chứng minh request vượt firewall vẫn phải qua CSRF/authentication/authorization, còn URL rejected không được phép tạo business side effect.

## 17. Checklist triển khai và nguyên tắc vận hành

### 17.1. Checklist trước khi đánh dấu PASS

| Nhóm | Điều kiện PASS |
| --- | --- |
| **Đúng stack** | StrictHttpFirewall chỉ coi là cơ chế Servlet; Reactive có server/gateway policy riêng |
| **FilterChainProxy** | Firewall policy thực sự được dùng và RequestRejectedHandler được wiring/test |
| **HTTP methods** | Methods được chấp nhận đúng business contract; TRACE/khác policy có negative tests |
| **Path validation** | Encoded separators, semicolon, traversal và double encoding không bypass matcher |
| **Security chains** | Cookie-auth/CSRF, Bearer-only và management routes không bị match lẫn |
| **Host/proxy** | Host routing và X-Forwarded-* qua trusted edge không bị spoof |
| **CORS** | OPTIONS preflight hợp lệ; không mở credentialed wildcard |
| **CSRF/authorization** | Unsafe POST thiếu CSRF hoặc thiếu quyền không có side effect |
| **Telemetry** | HTTP 400 tổng khác confirmed firewall rejection, WAF/connector có nguồn riêng |
| **Privacy** | Không log raw URI/headers/query/body, Cookie, CSRF token hoặc JWT |
| **Metrics** | Low-cardinality labels: layer/reason/path group/release/method class |
| **Servlet tests** | Unit StrictHttpFirewall, handler, MockMvc và real container checks |
| **Reactive tests** | WebTestClient + real HTTP server/gateway parser tests |
| **Browser/edge tests** | Public HTTPS, CORS, HSTS, session cookie và CSP không bị ảnh hưởng |
| **Canary** | Positive + negative probes, business SLO và stop/rollback gates |
| **Drift** | Artifact/BOM/config/edge policy revisions đồng nhất |
| **Rollback** | Known-good app/config/gateway/frontend tuple có thể khôi phục |
| **Runbooks** | Có owner điều tra WAF, Servlet, gateway, Reactive và incident privacy |

### 17.2. Mười hai nguyên tắc cốt lõi

1. **StrictHttpFirewall trên Servlet nhằm bảo vệ ranh giới request matching**, không phải WAF tổng quát.
2. **RequestRejectedException khác HTTP 400/403 tổng**; chỉ gắn nhãn confirmed khi có handler evidence.
3. **Firewall rejection thường xảy ra trước controller**, nên MVC route mapping hoặc ControllerAdvice có thể không thấy request.
4. **Browser, gateway, container và Spring có thể hiểu URL khác nhau**, vì vậy negative tests phải đi qua các tầng thật.
5. **Không tùy tiện bật setAllow* hoặc thay firewall dễ dãi** để làm giảm báo động; cần threat model và security review.
6. **Một request pass firewall vẫn cần CSRF, authentication, authorization và input validation**.
7. **CORS preflight là câu chuyện riêng**, OPTIONS lỗi không chứng minh POST bị CSRF từ chối.
8. **WebFlux không có Servlet StrictHttpFirewall**, phải quan sát Reactor Netty/gateway/WebFilters đúng layer.
9. **Log an toàn chỉ ghi categories đã chuẩn hóa**, không exception message, raw URI, Cookie, JWT hoặc CSRF token.
10. **Metrics dùng route group, method class, reason và release hữu hạn**, không có request ID/IP thô làm labels.
11. **Canary đánh giá cả security negative probes và user-flow success**, không chỉ rejection counts.
12. **Rollback phải đồng bộ app, firewall policy, proxy/WAF và client URL contract**, rồi verify lại security matchers/CSRF/authz.

**Kết luận:** Theo dõi request bị firewall từ chối là quá trình **xác định đúng tầng reject → phân loại bằng chứng đáng tin → giám sát không lộ dữ liệu → so sánh với baseline và user flows → xử lý không làm yếu phòng vệ**. Với StrictHttpFirewall trên Servlet, lớp parser/gateway trên Reactive và các kiểm thử đa tầng, đội vận hành có thể phát hiện path-normalization bypass, giảm false positives và khắc phục lỗi tích hợp mà vẫn giữ vững CSRF, CORS, security headers, HSTS và bảo vệ session.

## Tài liệu tham khảo chính thức và bổ trợ

- [Spring Security 6.5 — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Security API — StrictHttpFirewall](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/firewall/StrictHttpFirewall.html)
- [Spring Security API — RequestRejectedHandler](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/firewall/RequestRejectedHandler.html)
- [Spring Security 6.5 — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
- [MDN — HTTP Overview](https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview)





