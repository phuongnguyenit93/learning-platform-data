# Ranh giới giữa request firewall, WAF và kiểm tra dữ liệu nghiệp vụ

## 1. Ba lớp bảo vệ nhìn cùng một request nhưng đặt câu hỏi khác nhau

Trong chương **Firewall trên Servlet** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, chúng ta xây dựng hệ thống phòng vệ HTTP và trình duyệt với Spring Security: từ kiểm tra request, CSRF, CORS, response security headers, CSP, HSTS đến bảo vệ session. Các thành phần ấy chỉ có hiệu quả khi xác định đúng **ranh giới trách nhiệm**.

Giả sử khách hàng gọi API chuyển tiền:

```http
POST /api/transfers HTTP/1.1
Host: bank.example.test
Content-Type: application/json
Cookie: JSESSIONID=example

{
  "sourceAccountId": 17,
  "targetAccountId": 53,
  "amount": 250000,
  "currency": "VND"
}
```

Ba câu hỏi quan trọng, hoàn toàn không thay thế cho nhau:

1. **Web Application Firewall (WAF):** lưu lượng có trông giống một pattern tấn công, vi phạm một chính sách edge hay vượt giới hạn tổng quát không?
2. **Request firewall của Spring Security:** hình thức HTTP request mà Servlet trình bày có phù hợp với các ràng buộc về đường dẫn, HTTP method, tên host và các ký tự/representation mà security matcher có thể diễn giải an toàn không?
3. **Kiểm tra dữ liệu và quyền nghiệp vụ:** số tiền có hợp lệ, tài khoản nguồn có thuộc người dùng, có đủ hạn mức, trạng thái giao dịch cho phép và giao dịch có được thực hiện đúng một lần không?

Một request chứa JSON hợp lệ, đi qua WAF và `StrictHttpFirewall` vẫn **có thể là một giao dịch gian lận**, vì ứng dụng chưa hề xác minh người gọi có quyền sử dụng `sourceAccountId=17`.

**Nguyên tắc xuyên suốt:** *WAF không thay request firewall; request firewall không thay validation, authentication hay authorization; validation không thay kiểm tra quyền trên dữ liệu thực.*

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ đường đi request từ client, CDN/WAF, proxy, HTTP parser, `FilterChainProxy` tới service/storage.
2. Mô tả rõ `StrictHttpFirewall` kiểm tra những gì và **không** kiểm tra những gì.
3. Nêu khả năng, giới hạn, false positives và bypass paths của WAF.
4. Phân biệt **syntax validation**, **semantic/business validation**, **authentication**, **function-level authorization** và **object-level authorization**.
5. Chọn đúng lớp xử lý các trường hợp URL không chuẩn, header đáng ngờ, JSON sai schema, SQL injection, XSS, BOLA/IDOR, CSRF, CORS và workflow abuse.
6. Chẩn đoán nguyên nhân thực của HTTP 400/401/403/404/413/429/431/5xx, kể cả các lỗi bị từ chối trước Java.
7. Viết ví dụ Java Spring Security Servlet và Bean Validation, kết hợp service-level authorization.
8. Thiết kế bộ test unit, MockMvc, HTTP server và staging qua WAF với cả positive/negative cases.
9. Quản lý WAF exception/virtual patch mà không hạ mức phòng vệ nội bộ.
10. Đối chiếu Servlet với Reactive/WebFlux khi áp các cùng nguyên tắc.

## 2. Bức tranh end-to-end và các trust boundaries

Trong một deployment thường gặp:

```mermaid
flowchart TD
    A["Client / browser / API consumer"] --> B["DNS + TLS termination"]
    B --> C["CDN / reverse proxy / WAF"]
    C --> D["Upstream HTTP proxy hoặc load balancer"]
    D --> E["Servlet container HTTP parser"]
    E --> F["HttpServletRequest"]
    F --> G["DelegatingFilterProxy"]
    G --> H["FilterChainProxy → StrictHttpFirewall"]
    H --> I{"Request được firewall chấp nhận?"}
    I -->|Không| RJ["RequestRejectedException → Handler"]
    I -->|Có| S["SecurityFilterChain"]
    S --> SEC["CORS / CSRF / Authentication / Authorization"]
    SEC --> MVC["Spring MVC / parsing / DTO binding"]
    MVC --> VAL["Bean Validation / field contracts"]
    VAL --> BIZ["Service: business rules + resource authorization"]
    BIZ --> DB["Data access / storage / external services"]
    DB --> OUT["Response"]
    C --> EDGE["WAF block / rate limit / challenge"]
    E --> PARSER["Parser reject / size error"]
    EDGE --> RESP["Response do edge tạo"]
    PARSER --> RESP
    RJ --> RESP
```

Đây là sơ đồ **một topology tham khảo**: có hệ thống triển khai WAF như embedded module, service mesh proxy hoặc managed cloud service; một số requests còn đi qua internal queues, WebSockets và gRPC. Không được mặc định mọi deployment có WAF, hoặc WAF luôn thấy request cùng representation mà Servlet nhận.

### 2.1. Ai quyết định trước ai?

| Tầng | Dữ liệu thường nhìn thấy | Cơ chế | Khi bị từ chối |
| --- | --- | --- | --- |
| Client/browser | URL, headers, body tự tạo | Kiểm tra giao diện, same-origin browser policies | Có thể không gửi request. |
| TLS/HTTP edge | SNI, IP, Host, raw hoặc parsed HTTP | Virtual host, certificate, TLS/protocol policy | Connection error/4xx trước backend. |
| WAF/reverse proxy | Method, URL, headers, body theo năng lực parser WAF | Rules/signatures/anomaly scoring, rate limit, bot policy | Block/challenge/log theo policy. |
| Servlet HTTP parser | HTTP request line/frames, headers, body framing | Kiểm tra syntax, size, encoding, protocol | 4xx từ container, chưa vào Spring. |
| `StrictHttpFirewall` | `HttpServletRequest` sau parser | Method/path/hostname và một số header/parameter predicates | `RequestRejectedException`. |
| Security filters | Identity, session, CSRF, CORS, route | Authentication và authorization | 401/403/redirect/preflight error. |
| MVC/DTO validation | Giá trị đã parse theo controller contract | Kiểu, format, required fields, range, list length | Thường 400/422 theo API contract. |
| Service/domain | Principal, record thật, trạng thái hệ thống | Ownership, hạn mức, invariant, transaction rules | Deny/409/422/403 tùy semantics. |
| Storage/output | Query, object/blob, response representation | Parameterized queries, storage isolation, output encoding | Không có quyền vẫn phải chặn trước sink. |

**Định hướng chẩn đoán:** nếu không hề có backend request log, đừng tìm `RequestRejectedException` bằng mọi giá. Nếu service trả dữ liệu của tenant khác, thêm WAF rule chỉ là giảm nhẹ ngoài rìa, không thay sửa authorization logic.

### 2.2. Mỗi lớp chỉ có thể kiểm tra thông tin nó thật sự có

Một WAF trước authentication thường không biết principal đã được backend xác thực thành ai. `StrictHttpFirewall` không biết giá trị `amount=250000` có vượt hạn mức của user không. Bean Validation biết `amount` dương, nhưng không biết account đang bị khóa nếu chưa tra domain state. `@PreAuthorize` theo role biết có quyền gọi function, nhưng không tự chứng minh một record ID thuộc người gọi.

Vì vậy thiết kế phải dựa trên **thông tin và quyết định thực có ở đúng điểm kiểm tra**, không dựa vào tên gọi “firewall” hoặc “validation” chung chung.

## 3. HTTP parser và reverse proxy: lớp nền thường bị bỏ sót

Trước khi Java nhận `HttpServletRequest`, HTTP server phải phân tích request line, Host/authority, headers, body framing và các giới hạn tài nguyên.

Ví dụ request:

```http
GET /api/files/a%2Fb HTTP/1.1
Host: app.example.test
```

Có thể xảy ra các kết quả khác nhau:

- HTTP client giữ nguyên `%2F` hoặc tự chuẩn hóa URL trước khi gửi.
- CDN/proxy từ chối encoded separator.
- Proxy chuyển path nguyên văn hoặc đã decode/normalize.
- Servlet container từ chối request trước Spring Security.
- `StrictHttpFirewall` thấy URL và từ chối.
- Nếu đã nới firewall, Spring MVC matcher có thể diễn giải path khác business code.

**Không một test MockMvc đơn lẻ chứng minh được chuỗi xử lý qua từng hop.**

### 3.1. Parser là nơi đặt byte limits và framing safeguards

Những cấu hình thường cần ở HTTP server/edge:

- Kích thước request line, URI, header block và số lượng headers.
- HTTP/2 header-list size, stream/concurrency limits.
- Body size, upload size, form parameter count.
- Timeouts, connection limits và backpressure.
- Chặn Host/authority malformed, invalid HTTP method syntax.
- Quy tắc xử lý `Content-Length`, `Transfer-Encoding` và HTTP framing bất thường.
- Trusted proxy/forwarded-header handling.

`setAllowedHeaderValues(Predicate<String>)` hoặc `setAllowedParameterValues(Predicate<String>)` của `StrictHttpFirewall` không phải cách chính để giới hạn **raw HTTP byte size**. Chúng nhận Java `String` sau parser và có thể được áp khi code truy cập request fields.

### 3.2. Request smuggling không được giải quyết bằng regex ở controller

Nếu proxy và backend HTTP parsers không thống nhất ranh giới request body, vấn đề có thể xảy ra **trước khi** Java tạo `HttpServletRequest`. Một custom Servlet validator không thể sửa framing của kết nối đã bị parser diễn giải sai.

Cần cập nhật proxy/container, kiểm soát HTTP protocol normalization, áp network isolation, và kiểm thử được cấp phép tại gateway. `StrictHttpFirewall` bổ sung một lớp phòng vệ sau parser, không thay parser.

### 3.3. Không tin client-supplied forwarded headers

`Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` và `X-Forwarded-For` có thể giúp backend biết request public ban đầu nhưng **client Internet cũng có thể tự gửi chúng**.

Ingress phải strip/overwrite dữ liệu untrusted và chỉ backend mới được xử lý forwarded fields từ trusted hops. Nếu WAF sử dụng một client IP khác backend rate limiter do sai cấu hình proxy trust, kẻ tấn công có thể bị kiểm soát không nhất quán.

## 4. WAF là gì và nên chịu trách nhiệm đến đâu?

**Web Application Firewall (WAF)** là lớp kiểm tra traffic HTTP theo các chính sách và tín hiệu tấn công, thường đặt trước ứng dụng. Tùy sản phẩm, WAF có thể hoạt động theo:

- Signature/rule matching cho mẫu phổ biến như SQLi, XSS, scanner traffic.
- **Anomaly scoring**: nhiều tín hiệu nhỏ cộng thành mức chặn.
- Virtual patching: rule tạm thời giảm lưu lượng khai thác một lỗ hổng chưa kịp sửa ở app.
- Rate limiting, bot mitigation, IP/reputation/geographic controls.
- API schema/positive security policies ở một số giải pháp.
- Request size, header/body inspection và phương án challenge/block/log.
- Thống kê, sự kiện và correlation ID ở edge.

**Không WAF nào mặc nhiên hiểu trọn vẹn trạng thái nghiệp vụ của mọi service.** Một WAF có thể có tích hợp API schema hoặc identity context, nhưng không được suy tính năng đó tồn tại/chính xác nếu chưa được triển khai và kiểm thử.

### 4.1. Ví dụ các tín hiệu WAF thường xem

```text
GET /products?q=...              Query chứa pattern nghi SQLi
POST /api/login                  Lưu lượng credential stuffing tăng cao
GET /.git/config                 Scanner tìm file cấu hình
POST /api/files                  Body hoặc file metadata có pattern nguy hiểm
GET /api/orders?limit=1000000    Có thể bị API schema/rate policy chặn
```

WAF có thể nhận diện những dấu hiệu này, nhưng **một string giống SQL syntax trong field ghi chú chưa chắc là SQL injection**. Một backend dùng prepared statements có thể xử lý ký tự dấu nháy hoàn toàn an toàn, còn WAF rule quá rộng lại chặn người dùng hợp lệ.

### 4.2. WAF nhìn thấy bao nhiêu phần của request?

Phụ thuộc topology và policy:

- TLS có được giải mã tại WAF không?
- WAF có hỗ trợ HTTP/1.1, HTTP/2, HTTP/3 ở đường traffic thực không?
- Request body có được inspect đầy đủ không, hay chỉ một số bytes đầu?
- JSON, XML, multipart, form data có được parser nhận diện không?
- WAF có bỏ qua streaming, WebSocket upgrade hoặc endpoint ngoại lệ không?
- Có đường private/backend direct nào bypass WAF không?
- WAF inspection/response ở report-only hay blocking mode?
- Quy tắc có chạy trên cả inbound và outbound traffic không?

**Cần xác minh coverage bằng cấu hình và kiểm thử**, không tự suy rằng WAF đã quét 100% JSON/file bytes trên mọi endpoint.

### 4.3. WAF không phải API authentication/authorization provider

Một request:

```http
GET /api/orders/987 HTTP/1.1
Host: api.example.test
Authorization: Bearer valid-token-of-user-B
```

có thể không có ký tự bất thường hay pattern tấn công nào. Nếu order 987 thuộc user A, WAF không thể thay service kiểm tra ownership với principal B. Đây là ví dụ **Broken Object Level Authorization (BOLA/IDOR)**, không phải lỗi định dạng HTTP.

### 4.4. WAF chặn được không đồng nghĩa ứng dụng đã an toàn

Một WAF rule có thể chặn một payload SQLi phổ biến, nhưng nếu ứng dụng tiếp tục nối input vào SQL, một biến thể không khớp rule có thể khai thác cùng lỗi. Phải sửa **query construction** bằng prepared statements và giới hạn quyền DB.

Tương tự, WAF có thể nhận diện nhiều mẫu XSS nhưng không thay **contextual output encoding** và CSP; có thể chặn một vài path traversal patterns nhưng không thay safe storage path mapping; có thể chống rate spike nhưng không thay transaction idempotency và business rate limits.

## 5. `StrictHttpFirewall` nhìn request dưới góc khác WAF

`StrictHttpFirewall` thuộc `org.springframework.security.web.firewall` và được `FilterChainProxy` áp trước chọn `SecurityFilterChain` ở Servlet stack. Mục tiêu chính là giảm ambiguity trong **cách security matching diễn giải request**, từ chối những representations đáng ngờ.

Ví dụ:

```java
import org.springframework.security.web.firewall.StrictHttpFirewall;

StrictHttpFirewall firewall = new StrictHttpFirewall();
```

Không cần tự tạo bean riêng nếu mặc định đã phù hợp. `StrictHttpFirewall` được Spring Security dùng theo cấu hình Servlet hiện đại trừ khi đã thay thế.

### 5.1. Những lớp kiểm tra tiêu biểu

| Rule family | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| HTTP method allowlist | TRACE không nằm trong default methods | Giảm HTTP verb tampering/XST surface. |
| Path normalization | `/public/../admin` | Tránh security matcher hiểu khác handler. |
| Semicolon | `/secure;mode=1/reports` | Mặc định từ chối path parameters mơ hồ. |
| Encoded slash | `/files/a%2Fb` | Tránh encoded separator ambiguity. |
| Encoded backslash/percent/period | `%5C`, `%25`, `%2E` | Giảm parser/decoder mismatch. |
| Duplicate slash | `/admin//reports` | Tránh nhiều path representations. |
| Hostname predicate | `request.getServerName()` | Có thể giới hạn hosts theo deployment. |
| Header name/value predicates | Control chars/Unicode properties | Kiểm soát ký tự của headers khi getter đọc. |
| Parameter name/value predicates | Name control chars; custom value policy | Mặc định value predicate khá rộng; không thay field validation. |
| Response header safeguard | Newline trong response header | Giảm response splitting qua firewall response wrapper. |

**Caveat theo version:** Spring Security Javadoc/source cần được đối chiếu với dependency triển khai. Một số setter/default blocklists và chi tiết decoded/encoded URL phụ thuộc phiên bản. Không viết unit test dựa trên một behavior tưởng tượng.

### 5.2. HTTP firewall không phải WAF signatures engine

`StrictHttpFirewall` mặc định không có module “SQLi detection” cho mọi JSON body hoặc “XSS score” cho từng parameter value. Nó cũng không có thông tin domain như số dư, customer tier hay trạng thái tài khoản.

Đừng tự đặt hàng trăm regex nhận diện payload SQLi/XSS vào global `setAllowedParameterValues` rồi nghĩ đã xây WAF. Cách đó dễ false positive, bỏ sót JSON/file bodies và không sửa lỗi tại sink.

### 5.3. Mặc định parameter values không được validation theo nghiệp vụ

Trong những phiên bản Spring Security hiện đại:

- `ALLOWED_PARAMETER_NAMES` thường loại ký tự điều khiển và Unicode chưa được định nghĩa.
- `ALLOWED_PARAMETER_VALUES` mặc định tương ứng **predicate cho phép mọi value** ở cấp firewall.
- Header name/value predicates có defaults khác và **không được đồng nhất với parameter value**.

Một `message` nhiều dòng trong form có thể hoàn toàn hợp lệ. Một `amount=-100` có thể được firewall chấp nhận như chuỗi nhưng phải bị validation nghiệp vụ từ chối.

### 5.4. Nhiều checks trên header/parameter xảy ra khi đọc

`FirewalledRequest` có thể áp header/parameter predicates trong `getHeader`, `getHeaders`, `getParameter`, `getParameterMap` và các enumeration getters. Chỉ gọi `getFirewalledRequest(...)` thành công không chứng minh mọi header/parameter đã được kiểm tra.

Khác với WAF body inspection, Servlet request firewall **không nhất thiết chủ động duyệt toàn bộ dữ liệu**. Khi kiểm thử predicate custom, cần gọi đúng getters.

### 5.5. Request firewall không thay route authorization

Giả sử:

```text
/api/admin/** → hasRole("ADMIN")
/api/**       → authenticated
```

`StrictHttpFirewall` giúp giảm ambiguity của URL trước matching, nhưng cấu hình `SecurityFilterChain` và method/resource authorization vẫn phải bảo đảm USER không vào admin. Request `/api/admin/reports` hoàn toàn chuẩn có thể vượt firewall rồi bị từ chối `403`; đây là hành vi đúng.

## 6. Kiểm tra dữ liệu nghiệp vụ có nhiều cấp độ

Khi API nhận:

```json
{
  "sourceAccountId": 17,
  "targetAccountId": 53,
  "amount": 250000,
  "currency": "VND"
}
```

không thể dùng một boolean `isValid(request)` duy nhất cho mọi tầng. Ít nhất cần:

1. **Parsing:** body là JSON đúng syntax, size/nesting/charset hợp lệ.
2. **Structural/schema validation:** fields bắt buộc có mặt, types đúng, không có fields không cho phép theo contract.
3. **Field validation:** amount dương, currency là enum, ID đúng dạng, lengths/counts trong giới hạn.
4. **Cross-field validation:** nguồn và đích khác nhau, tổ hợp currency/amount hợp lệ.
5. **Authentication:** ai đang yêu cầu hành động?
6. **Function authorization:** người này có quyền gọi tính năng chuyển tiền không?
7. **Object authorization:** có quyền giao dịch từ account 17 không? Có quyền dùng tài khoản đích theo chính sách không?
8. **Domain invariants:** source active, balance đủ, limit/ngày còn đủ, không bị khóa/risk hold.
9. **Concurrency/idempotency:** không double-spend, retry không tạo giao dịch trùng.
10. **Output/sink safety:** query DB an toàn, log không lộ dữ liệu nhạy cảm, response không tiết lộ record của tenant khác.

WAF có thể giảm bớt một số lưu lượng xấu ở ngoài nhưng **các quyết định trên phải có chủ sở hữu rõ trong ứng dụng và domain**.

### 6.1. Syntax hợp lệ không có nghĩa semantics hợp lệ

`amount=250000` có thể là số nguyên hợp lệ nhưng vượt hạn mức. `startDate=2026-12-01` và `endDate=2026-11-30` đều là ngày hợp lệ nhưng khoảng thời gian sai. `currency=VND` có thể là enum hợp lệ nhưng account đích không hỗ trợ VND.

Những quyết định này phụ thuộc context của business service; không đưa vào WAF signature hoặc URL firewall.

### 6.2. Object-level authorization khác validation

Một account ID `17` có thể là ID đã tồn tại, nhưng user hiện tại không có quyền thao tác. Đây là vấn đề **BOLA/IDOR** nếu service cho phép đọc/sửa resource đó chỉ dựa trên input ID.

Đừng nhầm:

```text
@Positive accountId         → valid format
accountRepository.exists(id) → record tồn tại
accessPolicy.canDebit(user,id) → user có quyền ghi nợ
```

Cả ba là câu hỏi riêng. Trong mọi API nhận object reference từ path, query, header hoặc body, phải kiểm tra quyền trên **object thật** và action được yêu cầu.

### 6.3. Input validation không thay output encoding/SQL parameterization

Dù `name` có định dạng được chấp nhận, ứng dụng vẫn phải dùng:

- Prepared statements hoặc ORM parameter binding cho SQL values.
- Context-specific escaping cho HTML/attribute/JavaScript/URL output.
- An toàn khi xử lý command execution hoặc external services.
- XML/JSON parser security và schema theo ngữ cảnh.
- Safe storage mapping khi truy cập file.

Cấm tất cả dấu nháy trong tên người dùng để "ngăn SQL injection" vừa phá dữ liệu hợp lệ vừa không chứng minh queries an toàn.

## 7. Ma trận phân công trách nhiệm theo tình huống

| Tình huống | Lớp chính chịu trách nhiệm | Lớp hỗ trợ |
| --- | --- | --- |
| HTTP/2 frame/framing malformed | HTTP parser / proxy | WAF nếu có protocol policy phù hợp. |
| URI traversal `/../` chưa chuẩn hóa | `StrictHttpFirewall` hoặc parser/edge | WAF path anomaly rule. |
| Encoded slash giữa path segments | Parser + `StrictHttpFirewall` | WAF, hợp đồng URI của API. |
| TRACE ngoài methods cho phép | HTTP server/`StrictHttpFirewall` | WAF method policy. |
| Host/forwarded-header spoofing | Ingress + trusted proxy config | Strict host predicate, canonical URL policy. |
| SQLi pattern trong query | Prepared statements **bắt buộc** tại sink | WAF anomaly/signature, schema validation. |
| XSS trong user comment | Output encoding/safe rendering | CSP, WAF pattern rules, input limits. |
| JSON thiếu `sourceAccountId` | DTO/schema + Bean Validation | WAF schema policy nếu có. |
| Amount âm hoặc quá lớn | Field/domain validation | WAF API schema/rate policies. |
| Account thuộc người khác | Object-level authorization | Authentication và method security. |
| Giao dịch vượt hạn mức | Domain service/invariants | Rate limiting/fraud controls. |
| Cookie-session POST thiếu CSRF | `CsrfFilter` | SameSite, Origin defenses theo threat model. |
| Browser origin không được phép | CORS config | WAF origin anomaly monitoring. |
| Excessive login requests | Rate limiter/identity controls | WAF/bot mitigation. |
| Oversized request body | Edge/container size limits | MVC validation sau parsing. |
| JSON cực sâu | JSON parser nesting limits | WAF body inspection limits. |
| File có malware | File handling/scanning service | WAF/upload restrictions. |
| Malicious redirect target | Redirect URI allowlist + domain logic | WAF URL pattern checks. |
| CSP/HSTS thiếu trên response | Response header writer/edge owner | Kiểm thử qua public HTTPS. |
| Secret/token lộ trong logs | Logging/data governance | WAF redaction/config. |
| User vượt tenant boundary | Service-level authorization + tenant isolation | Security filter role checks. |

### 7.1. “Lớp hỗ trợ” không được nâng thành nguồn sự thật

Một WAF báo request "allow" không phải security attestation. Một firewall báo request "accepted" không phải authorization. Một DTO có `@Valid` không chứng minh ownership. Một `hasRole("USER")` không chứng minh user này sở hữu record cụ thể.

**Rule thực dụng:** điều kiện liên quan **trạng thái và quyền nghiệp vụ** phải được kiểm tra tại nơi ứng dụng biết dữ liệu và principal đáng tin.

## 8. Ví dụ A — URL mơ hồ: WAF, parser và StrictHttpFirewall

Yêu cầu:

```http
GET /public/../admin/reports HTTP/1.1
Host: app.example.test
```

Các tầng có thể phản ứng:

- WAF chặn path traversal pattern.
- Gateway normalize path thành `/admin/reports`.
- HTTP server từ chối URI chưa chuẩn.
- `StrictHttpFirewall` từ chối vì path không được normalize.
- Nếu request đã được normalized ở edge, Spring Security phải enforce authorization cho **path mà backend thực thấy**.

Điểm nguy hiểm nhất không chỉ là request có `..`; mà là **security matcher xét representation khác với handler/resource**.

### 8.1. Không nên tự sửa path sau khi security đã quyết định

```java
// ANTI-PATTERN: tự decode/normalize URI sau security matching.
String path = request.getRequestURI();
String decodedAgain = java.net.URLDecoder.decode(
    path, java.nio.charset.StandardCharsets.UTF_8);
```

`URLDecoder` dùng form semantics (`+` có thể thành space), không phải cách parse mọi URI path. Nếu service dùng `decodedAgain` để chọn tài nguyên khác identity đã được authorize, có thể tạo lỗi permission.

Giữ `StrictHttpFirewall` mặc định, chọn parser/matcher nhất quán và thực hiện resource authorization tại service. Nếu client cần URL chứa `/` trong ID, cân nhắc dùng opaque ID hoặc query/body field thay vì nới encoded slash toàn app.

### 8.2. WAF không đồng nhất với `StrictHttpFirewall`

WAF có thể normalize/inspect URL theo policy riêng rồi gửi upstream một URI khác. `StrictHttpFirewall` chỉ nhìn representation mà Servlet container cung cấp **sau các tầng trước**. Nếu WAF/edge đã biến đổi URL, Spring không thể suy raw bytes client ban đầu.

Muốn biết tầng nào chặn, cần logs có correlation IDs và test qua public ingress, không chỉ JUnit tạo request mock.

## 9. Ví dụ B — SQL injection: nơi sửa bắt buộc là data access

Một API tìm kiếm nhận:

```http
GET /api/products?q=phone HTTP/1.1
Host: api.example.test
```

Một client có thể gửi dấu nháy, keyword hoặc chuỗi mã hóa bất thường trong `q`. WAF có thể phát hiện một số signatures SQLi nhưng nhiều input chứa dấu nháy là hợp lệ.

### 9.1. Code sai

```java
// ANTI-PATTERN: input bị nối vào câu SQL.
String sql = "SELECT * FROM product WHERE name = '"
    + q + "'";

// Không nên giao raw SQL như vậy cho JDBC.
```

Bỏ hết dấu nháy khỏi `q` không giải quyết tận gốc. Một biến thể không khớp sanitizer vẫn có thể làm lệch truy vấn.

### 9.2. Code với parameter binding

```java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

class ProductSearchRepository {

    private final JdbcTemplate jdbc;

    ProductSearchRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<Long> findProductIdsByName(String name) {
        return jdbc.query(
            "SELECT id FROM product WHERE name = ?",
            (rs, rowNum) -> rs.getLong("id"),
            name
        );
    }
}
```

`JdbcTemplate` truyền `name` như **bind parameter**, không làm nó thành SQL syntax. Vẫn cần application-level length limits, resource access và query plans phù hợp; ví dụ chỉ minh họa sink.

**Vai trò WAF:** virtual patch/signature có thể giảm nguy cơ trong thời gian chờ release; sau fix vẫn giữ monitoring phù hợp. Không coi WAF block log là proof code đã hết SQLi.

### 9.3. Dynamic column names không dùng bind parameter như values

Nếu user chọn `sort=price`, SQL identifier/`ORDER BY` thường cần **allowlist từ server**:

```java
String orderBy = switch (sort) {
    case "price" -> "price";
    case "name" -> "name";
    default -> throw new IllegalArgumentException("Unknown sort");
};
```

Sau đó chỉ nối **tên cột hằng do server chọn**, không nối raw `sort` từ client. Đây là validation theo domain/query design, không phải chức năng của `StrictHttpFirewall`.

## 10. Ví dụ C — XSS: WAF hỗ trợ, output encoding là trách nhiệm gốc

User nhập:

```text
Comment: I use <code> and quotes when teaching HTTP.
```

Một WAF rule chặn mọi dấu `<` hoặc dấu nháy sẽ làm hỏng nhu cầu nhập nội dung kỹ thuật, nhưng vẫn không bảo đảm mọi XSS vector bị loại.

### 10.1. Tránh nối raw input vào HTML

```java
// ANTI-PATTERN: không phản chiếu raw user input như HTML tin cậy.
String html = "<div>" + comment + "</div>";
```

Thay bằng template engine tự escape hoặc encoding **đúng output context**. Dữ liệu đi vào HTML text, HTML attribute, JavaScript, CSS hoặc URL có escape rules khác nhau.

### 10.2. CSP là lớp phòng vệ bổ sung

`Content-Security-Policy` có thể hạn chế nguồn script và các hành vi trình duyệt. Một CSP tốt làm giảm hậu quả của một số injection, nhưng không thay contextual encoding hoặc tránh DOM-based XSS trong client code.

WAF, `StrictHttpFirewall`, server-side validation, output encoding và CSP cần được hiểu là **các lớp khác chức năng**, không phải các module thay nhau khi một layer bị tắt.

## 11. Ví dụ D — BOLA/IDOR: request “sạch” vẫn có thể trái quyền

Hai account trong hệ thống:

```text
User A: account 17
User B: account 53
```

User B gửi một request có JWT hợp lệ:

```http
GET /api/accounts/17/balance HTTP/1.1
Host: api.example.test
Authorization: Bearer user-B-token
```

Không có URI malformed, không có WAF signature, không có JSON sai schema. WAF và `StrictHttpFirewall` có thể hoàn toàn chấp nhận request.

Nếu controller dùng `accountId=17` để tra balance mà không kiểm tra owner, đây là **Broken Object Level Authorization**. OWASP API Security khuyến nghị xác minh quyền trên mỗi object/function nhận ID từ client.

### 11.1. Anti-pattern

```java
// ANTI-PATTERN: chỉ xác thực user, không xác thực quyền xem account.
@GetMapping("/api/accounts/{accountId}/balance")
BigDecimal balance(@PathVariable long accountId) {
    return accountRepository.findBalance(accountId);
}
```

### 11.2. Thiết kế đúng theo resource thực

```java
// PSEUDOCODE: Account, repository và policy do ứng dụng định nghĩa.
Account account = accountRepository.requireById(accountId);

accountAccessPolicy.requireCanRead(
    authentication, account);

return balanceService.balanceOf(account);
```

Đặt quyền trên record thực, không chỉ trên path prefix hoặc sự tồn tại của ID. Với multi-tenant data, cần ràng buộc principal/tenant/resource và tránh cross-tenant cache leaks.

### 11.3. Vì sao WAF rule “không cho ID 17” là sai lớp?

Account ownership thay đổi theo user, session, quyền delegation và domain state. WAF thường không có nguồn sự thật cập nhật cho từng record. Một block list ID ở edge vừa dễ sai vừa không thay kiểm tra quyền trong service.

## 12. Ví dụ E — Business logic: đúng syntax nhưng sai quy trình

Đặt hàng, hoàn tiền, chuyển tiền, cấp voucher, thay đổi địa chỉ giao hàng thường có **state machine** và giới hạn nghiệp vụ:

```text
Order.CREATED → Order.PAID → Order.SHIPPED → Order.DELIVERED
                                  |
                                  └→ Refund theo điều kiện
```

Một request `POST /refunds` có JSON hợp lệ và user đã login vẫn phải kiểm tra:

- Order có tồn tại và thuộc user/tenant không?
- Đã thanh toán và còn trong thời hạn refund không?
- Giá trị refund có vượt khoản còn lại không?
- Có request refund trùng hoặc replay không?
- Có workflow approval/anti-fraud nào phải qua không?
- Transaction atomicity và concurrency locking ra sao?

WAF rate limits có thể giảm abuse, nhưng không biết refund amount còn lại và không thực thi business state transitions. `StrictHttpFirewall` cũng không.

### 12.1. Retry và idempotency

Nếu client retry `POST` sau timeout, service cần idempotency key/transaction handling khi domain yêu cầu. WAF không thể tự quyết định hai POST với body giống nhau có nên tạo hai giao dịch hay một giao dịch; request có thể đại diện các nghiệp vụ khác nhau.

### 12.2. Không tin UI/client-side validation

Browser form có thể disable một nút hoặc kiểm tra số tiền, nhưng client có thể gửi HTTP trực tiếp. Mọi invariant bảo mật/pháp lý/tiền tệ phải được xác minh tại server trong transaction phù hợp.

## 13. Dữ liệu JSON, form, headers, cookies và files không đi qua cùng validator

| Dữ liệu | Nơi parse | Nơi validate | Firewall/WAF nhìn gì? |
| --- | --- | --- | --- |
| Query string | Servlet parameter parser / Spring MVC | `@RequestParam`, field schema/service | WAF có thể inspect query; Strict parameter name/value predicates khi đọc. |
| Form-urlencoded | Servlet form parser / MVC binder | DTO, `@ModelAttribute`, Bean Validation | WAF có thể parse body; Strict predicates không thay form validation. |
| JSON body | Jackson/HTTP message converter | `@RequestBody @Valid`, JSON schema, service | WAF tùy body inspector; Strict parameter predicates **không kiểm tra JSON fields**. |
| Multipart text field | Multipart resolver / Servlet | Field validation | WAF/body parser khả năng giới hạn; không đồng nhất JSON. |
| Multipart file bytes | Multipart parser/stream | File validation, content scanning, size/type/stored name | WAF có thể inspect một phần; Strict predicate không quét file bytes. |
| HTTP headers | Servlet HTTP parser / framework | Trusted proxy checks, auth/CORS/custom header validation | WAF inspect tùy policy; Strict header name/value predicates. |
| Cookies | HTTP server/Spring Security session | Session integrity/cookie attributes | WAF có thể inspect; Strict không xác thực session token. |
| Path variables | Container+Spring MVC router | Type/ID validation và resource authorization | WAF và Strict có URL/path checks; không biết ownership. |
| WebSocket frames | Upgrade+protocol handler | Message schema/auth per operation | WAF có thể chỉ inspect handshake, tùy sản phẩm. |

### 13.1. “WAF đã quét JSON” cần bằng chứng cấu hình

Một WAF trước backend có thể inspect request body trong giới hạn bytes/size cụ thể; khi body lớn, behavior có thể là block/ignore/truncate theo cấu hình. Không tự suy JSON nested fields hoặc file streams đã được parse và validate đầy đủ.

### 13.2. Schema validation và unknown fields

Một DTO có các properties `amount` và `currency` không mặc định có nghĩa serializer **luôn từ chối unknown JSON properties**. Hành vi phụ thuộc Jackson/JSON converter config. Với API cần contract chặt, định nghĩa rõ policy cho required, null, unknown và nested properties; test theo runtime thực.

### 13.3. Mass assignment

Đừng bind request trực tiếp vào entity có fields như `isAdmin`, `ownerId`, `balance` hoặc `status`. Đặt DTO chỉ chứa fields client được sửa, rồi mapping explicit sang domain object với server-owned fields lấy từ principal/state.

## 14. Một thiết kế Spring MVC + Bean Validation thực tế

Ví dụ API tạo chuyển tiền với field validation. Các types domain/repositories bên dưới là **mẫu minh họa**, không phải project hoàn chỉnh.

### 14.1. DTO chỉ chứa dữ liệu client được phép cung cấp

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

record TransferRequest(
    @NotNull @Positive Long sourceAccountId,
    @NotNull @Positive Long targetAccountId,
    @NotNull @DecimalMin("0.01")
        @Digits(integer = 12, fraction = 2)
        BigDecimal amount,
    @NotBlank @Size(max = 3) String currency
) {}
```

Các constraints giúp kiểm tra:

- IDs bắt buộc và dương.
- Amount bắt buộc, dương theo decimal rule và giới hạn chữ số.
- Currency không rỗng, giới hạn độ dài.

Chúng **chưa kiểm tra** currency có thuộc `VND`/`USD` theo product contract, source khác target, người gọi có quyền hay balance đủ.

### 14.2. Controller nhận DTO đã validation

```java
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TransferController {

    private final TransferService service;

    TransferController(TransferService service) {
        this.service = service;
    }

    @PostMapping("/api/transfers")
    @ResponseStatus(HttpStatus.ACCEPTED)
    TransferReceipt transfer(
            @Valid @RequestBody TransferRequest body,
            Authentication authentication) {

        return service.transfer(authentication, body);
    }
}
```

`TransferService` và `TransferReceipt` do ứng dụng định nghĩa. `202 Accepted` là **status minh họa** nếu hệ thống xử lý bất đồng bộ; với giao dịch xử lý đồng bộ, API contract có thể chọn status khác. Đừng gắn cứng status trong sản phẩm nếu response semantics chưa được đặc tả.

### 14.3. Service phải kiểm tra state và ownership

```java
// PSEUDOCODE: không phải implementation banking production.
@Transactional
public TransferReceipt transfer(
        Authentication auth, TransferRequest dto) {

    Account source =
        accountRepository.lockById(dto.sourceAccountId());

    Account target =
        accountRepository.requireById(dto.targetAccountId());

    transferPolicy.requireCanDebit(auth, source);
    transferPolicy.requireAllowedDestination(auth, source, target);

    if (source.id().equals(target.id())) {
        throw new InvalidTransferException(
            "Same source and target");
    }

    currencyPolicy.requireSupported(dto.currency(), source, target);
    limitPolicy.requireWithinLimits(auth, source, dto.amount());
    balancePolicy.requireSufficientFunds(source, dto.amount());

    // Idempotency, anti-fraud và transaction boundaries
    // phải được thiết kế theo nghiệp vụ thực.
    return transferLedger.post(source, target, dto.amount());
}
```

Đoạn pseudocode thể hiện **đặt quyết định tại nơi có quyền, state và dữ liệu thực**. Một hệ thống tài chính cần còn nhiều điều kiện như regulatory limits, transaction integrity, outbox/idempotency, fraud detection và concurrency controls; không xem đây là implementation hoàn chỉnh.

### 14.4. Method security hỗ trợ nhưng không thay object checks

```java
@PreAuthorize("hasAuthority('transfer:create')")
public TransferReceipt transfer(
        Authentication authentication, TransferRequest request) {
    // Vẫn phải xác minh quyền debit sourceAccountId thực.
}
```

`@EnableMethodSecurity` cần được bật khi dùng `@PreAuthorize`. Có authority `transfer:create` chỉ xác minh **function-level permission**, không chứng minh user có quyền trên account cụ thể.

### 14.5. Exception mapping cần phân biệt lỗi

- JSON parse error hoặc thiếu field: thường `400 Bad Request`.
- Không đăng nhập/credentials sai: `401` hoặc login redirect theo auth mechanism.
- Không có quyền với source account: `403` hoặc `404` che sự tồn tại tùy policy.
- Domain conflict/idempotency: `409 Conflict` nếu hợp đồng API xác định.
- Input semantic invalid: `400` hoặc `422` tùy API contract.
- HTTP firewall rejection: thường `400` từ `RequestRejectedHandler`, có thể trước MVC.
- WAF block: response do edge quyết định, có thể không tới Java.

Không tạo `@ControllerAdvice` bắt mọi exception rồi trả `200`/cùng một body. Clients và monitoring cần phân biệt class lỗi đúng.

## 15. Cấu hình Spring Security Servlet và vị trí `HttpFirewall`

Một security chain mẫu bảo vệ API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpProtectionSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/transfers")
                    .hasAuthority("transfer:create")
                .requestMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là ví dụ auth với HTTP Basic để đơn giản. Production phải lựa chọn session/token/OAuth mechanisms đúng threat model, TLS, CORS/CSRF và session configuration theo hệ thống.

**Không tắt CSRF vô điều kiện**: nếu API dùng cookie-session và browser có thể gửi state-changing requests, Spring Security CSRF protection thường cần thiết. Nếu API stateless chỉ dùng Authorization header, hãy đánh giá CSRF theo credential delivery model thực, không chỉ theo endpoint tên `/api/**`.

### 15.1. `WebSecurityCustomizer` chỉ khi cần custom firewall

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
class FirewallPolicyConfiguration {

    @Bean
    WebSecurityCustomizer firewallCustomizer() {
        return web -> web.httpFirewall(new StrictHttpFirewall());
    }
}
```

`StrictHttpFirewall` mặc định thường đã có; ví dụ cho thấy **nơi đăng ký** nếu phải tùy chỉnh. Không tạo đồng thời nhiều firewall instances/configurations khiến runtime không rõ dùng policy nào. Một setter như `setAllowSemicolon(true)` thay chính sách **instance dùng chung ở `FilterChainProxy`**, không tự scope chỉ một controller hoặc security chain.

### 15.2. CORS và CSRF chạy ở security chain, không thay firewall

- CORS quyết định browser context nào có thể đọc response và preflight ra sao.
- CSRF bảo vệ state-changing requests khi browser credentials có thể được tự gửi.
- Authentication xác định principal.
- Authorization quyết định function/resource access.
- `StrictHttpFirewall` kiểm tra request representation và path matching consistency.

Các lớp nên được test **độc lập và cùng nhau**.

## 16. WAF anomaly scoring và false positives

WAF rule có thể nhìn thấy một pattern nghi vấn, nhưng dữ liệu thật có thể hợp lệ:

```http
POST /api/comments HTTP/1.1
Content-Type: application/json

{
  "text": "Cú pháp SELECT * FROM table được dùng trong ví dụ SQL."
}
```

Nếu WAF chặn vì thấy `SELECT`, đây có thể là false positive — nhất là website học lập trình hoặc một công cụ ghi chú kỹ thuật.

### 16.1. Phân biệt ba kết quả

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| True positive | Request vi phạm rule và có nguy cơ thực. | Giữ block, xác minh application có phòng vệ gốc. |
| False positive | Request hợp lệ bị chặn vì rule quá rộng. | Điều chỉnh WAF theo trường/route/điều kiện nhỏ nhất. |
| False negative | Request nguy hiểm lọt WAF. | Sửa app flaw, cải tiến detection; đừng chỉ tăng rule mù quáng. |

Không đánh giá chất lượng WAF chỉ bằng số request bị chặn; rule chặn quá rộng có thể gây outage và làm người dùng không thể gửi dữ liệu hợp lệ.

### 16.2. Tuning đúng nghĩa có phạm vi

Ví dụ một endpoint `/api/comments` cho phép nhiều chữ và dấu câu. Nếu rule SQLi tạo false positive:

1. Kiểm tra event logs đã redacted và request contract.
2. Xác định đúng rule ID và field bị inspect.
3. Xác định field `text` là free-form content, không phải dynamic SQL.
4. Sửa application nếu vẫn có lỗi SQL construction.
5. Tạo exception theo **rule + field + route** nếu WAF hỗ trợ; không tắt toàn bộ SQLi protection cho mọi API.
6. Test negative SQLi input trên các endpoints thật sự nhận SQL-sensitive fields.
7. Theo dõi false-positive rate và review exception định kỳ.

Đừng dùng `SecRuleEngine Off` hoặc tương đương cho toàn site chỉ vì một form nhập dấu nháy. Tùy sản phẩm WAF, cú pháp exemption khác nhau; phải dùng tài liệu sản phẩm và review thực tế.

### 16.3. WAF managed rules và virtual patch có vòng đời

Một rule tạm chặn exploit đang có thể cần sau khi phát hiện CVE mới, nhưng **code/config fix là đích đến**. Virtual patch cần owner, expiration/retest, coverage analysis và rollback, không để mãi như giải pháp duy nhất.

Nếu một WAF rule bắt buộc phải tắt, hãy chứng minh application vẫn có parameter binding, output encoding, resource authorization và tests chứng minh invariant tương ứng.

## 17. Khi WAF và backend không thấy cùng một request

### 17.1. URL decoding ở mỗi hop

`%252F` có thể thành `%2F` sau decode một lần, và `/` sau lần thứ hai. Nếu WAF inspect một representation còn backend hoặc service decode thêm, có thể tạo chênh lệch.

Đừng tự gọi `URLDecoder.decode` nhiều lần trên path sau security matching. Kiểm tra raw query/body, parsed Servlet path và handler resource identity tại từng tầng.

### 17.2. HTTP request headers và duplicates

Một số headers có thể xuất hiện nhiều lần. HTTP parser/WAF có thể gộp hoặc reject theo semantics riêng; một application gọi `getHeader` thường chỉ thấy một giá trị.

Đặc biệt `Host`, `Content-Length`, `Transfer-Encoding`, `Authorization`, `Forwarded` không được xử lý bằng một rule “lấy giá trị đầu là được”. Dùng parser chuẩn và trusted proxy config, tránh framing/identity ambiguity.

### 17.3. JSON body normalization và duplicate keys

`{"role":"USER","role":"ADMIN"}` là JSON có duplicate member names. Hành vi của parsers khác nhau có thể chọn first/last hoặc từ chối tùy configuration; WAF parser và Jackson backend có thể diễn giải không giống nhau.

Với các field nhạy cảm, phải có schema/parser configuration và tests **từ edge tới service**. Không lấy WAF JSON inspector làm nguồn sự thật cho authorization.

### 17.4. Multipart boundaries

WAF có thể không parse mọi file bytes, hoặc chỉ inspect phần đầu body. Servlet MultipartResolver có giới hạn size và file handling khác. Ứng dụng vẫn phải xác minh media type dựa trên content nếu cần, giữ upload ngoài web root, validate extension/name, limits, malware scanning theo risk profile, và phân quyền đọc/ghi file.

### 17.5. Giao thức/traffic ngoài WAF

Internal service-to-service traffic, scheduled jobs, message queues, Kafka consumers, DB triggers, gRPC endpoints hoặc WebSocket messages có thể không đi qua HTTP WAF. **Domain service và data validation vẫn phải bảo vệ mọi entry point**, không chỉ REST controller public.

## 18. WAF bypass: direct-to-origin và luồng nội bộ

Giả sử public topology:

```text
Internet → CDN/WAF → Gateway → Spring Boot backend
```

Nếu backend có public IP/port mà client gọi trực tiếp được, WAF rules bị bypass mà `StrictHttpFirewall` và business security vẫn phải tự bảo vệ request.

### 18.1. Những biện pháp cần có

- Chặn direct-to-origin ở network/firewall/security groups.
- Chỉ cho ingress/trusted proxies truy cập backend listener.
- Xác thực service-to-service qua mTLS/identity khi phù hợp.
- Hạn chế management/actuator endpoints.
- Ràng buộc trusted forwarded headers, Host/SNI, routing.
- Không có “secret header” thuần client-supplied làm biện pháp duy nhất.
- Tự bảo vệ authorization tại backend kể cả khi WAF offline/bị bypass.

### 18.2. WAF outage: fail-open hay fail-closed?

Không có câu trả lời chung cho mọi service. Cần định nghĩa:

- Nếu WAF không sẵn sàng, traffic bị block hay có fallback không?
- Quy trình incident/manual override có được phê duyệt không?
- Đường fallback có bị giới hạn theo service/host/time không?
- Có alert và audit trail khi policy chuyển chế độ không?
- Backend vẫn có parser limits, `StrictHttpFirewall` và auth không?

Đối với dữ liệu đặc biệt nhạy cảm, việc fail-open không có safeguards có thể không được chấp nhận. Nhưng fail-closed trên dịch vụ thiết yếu có thể gây outage lớn; lựa chọn là một **risk/availability decision của tổ chức**, không phải do `StrictHttpFirewall` tự quyết định.

## 19. Không trộn WAF rate limiting với hạn mức nghiệp vụ

Ví dụ user được phép tạo tối đa 5 yêu cầu chuyển tiền/ngày; WAF cho 100 requests/phút/IP. Hai giới hạn độc lập:

- **Edge rate limit:** giảm volumetric abuse, bot traffic, tài nguyên gateway.
- **Identity-aware rate limit:** hạn chế theo account/token/user sau xác thực.
- **Business quota:** giới hạn số giao dịch, số tiền, voucher use, refund frequency.
- **Transaction idempotency:** chống duplicate operations do retries/races.

Không dùng địa chỉ IP từ `X-Forwarded-For` do client tự khai báo làm khóa bảo mật nếu trust proxy chưa đúng. Với NAT/mobile networks, rate limits chỉ theo IP cũng có thể làm nhiều người dùng hợp lệ bị ảnh hưởng.

## 20. Những mã HTTP thường làm đội ngũ nhầm nguyên nhân

| Quan sát | Có thể từ tầng nào | Không nên kết luận |
| --- | --- | --- |
| HTTP `400` không có backend log | Edge WAF/HTTP parser | Không mặc định do Spring firewall. |
| HTTP `400` với `RequestRejectedException` | `StrictHttpFirewall`/`FilterChainProxy` | Không tự suy business DTO sai. |
| HTTP `400` từ MVC binding | JSON parser/Bean Validation | Không tự chỉnh WAF rule nếu API contract sai. |
| HTTP `401` | Authentication entry point | Không phải dấu hiệu method/path malformed. |
| HTTP `403` | CSRF/authorization/WAF tùy policy | Phải xác định layer bằng event/correlation. |
| HTTP `404` | Routing hoặc deliberate resource hiding | Không chứng minh resource không tồn tại với mọi principal. |
| HTTP `405` | MVC method mapping | Khác firewall method allowlist từ chối `TRACE`/custom method. |
| HTTP `409` | Domain conflict/idempotency | WAF không thể giải quyết business state. |
| HTTP `413` | Request body too large | Thường parser/gateway limits, không phải Bean Validation length rule. |
| HTTP `429` | Rate limit edge/app | Cần biết key là IP, principal hay API key. |
| HTTP `431` | Request header fields too large | Không liên quan mọi JSON/form values. |
| HTTP `5xx` | Backend/proxy failure | Không tự quy là WAF attack. |
| CORS error trong browser | CORS response/preflight, có thể bị block trước app | JavaScript không đọc được response không có nghĩa backend không trả lỗi. |
| Thiếu CSP/HSTS trên WAF block page | Error được tạo trước header writer của app | Cần owner response security headers ở edge. |

**Không dùng status code làm bằng chứng duy nhất về lớp từ chối.** Dùng source của response, WAF event ID, gateway request ID và backend traces với logs bảo vệ dữ liệu.

## 21. Kiểm thử unit: `StrictHttpFirewall` với request mock

Dùng JUnit 5 và Spring Test để chứng minh request firewall, không cần kết nối WAF.

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FirewallBoundaryUnitTest {

    private final StrictHttpFirewall firewall =
        new StrictHttpFirewall();

    private MockHttpServletRequest request(
            String method, String path) {

        var req = new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        return req;
    }

    @Test
    void rejectsUnnormalizedUrl() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "/public/../admin")));
    }

    @Test
    void rejectsMethodOutsideDefaultAllowlist() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("TRACE", "/health")));
    }

    @Test
    void acceptsOrdinaryRequestWithoutCheckingBusinessRights() {
        var safe = assertDoesNotThrow(() ->
            firewall.getFirewalledRequest(
                request("GET", "/api/accounts/17")));

        safe.reset();
        // Không có authentication, ownership hay DB access ở test này!
    }
}
```

### 21.1. Test nói được điều gì?

- Firewall từ chối path/method không phù hợp trên mock Servlet request.
- Firewall cho `/api/accounts/17` qua **không chứng minh** user có quyền xem account 17.
- Test chưa đi qua HTTP parser hoặc WAF. Để chứng minh HTTP status cuối, phải có `FilterChainProxy`/handler hoặc real HTTP server.

### 21.2. Chú ý constructor mock

Dùng `new MockHttpServletRequest("GET", path)` và `setServletPath` phù hợp. Một mock không có HTTP method hợp lệ có thể bị từ chối do method, làm test URL sai mục tiêu.

### 21.3. Test parameter value mặc định

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void defaultParameterValuePredicateDoesNotEnforceBusinessRange() {
    var req = request("GET", "/api/search");
    req.setParameter("amount", "-100000000");

    var safe = firewall.getFirewalledRequest(req);

    assertEquals("-100000000", safe.getParameter("amount"));
    safe.reset();
}
```

Method bổ sung cho class `FirewallBoundaryUnitTest`. Test chứng minh giá trị `-100000000` không bị default parameter value predicate coi là business error; Bean Validation/service chịu trách nhiệm với amount.

## 22. Unit test DTO: validation độc lập WAF/firewall

Để thử constraints của `TransferRequest` mà không cần HTTP:

```java
import java.math.BigDecimal;

import jakarta.validation.Validation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TransferDtoValidationTest {

    private final Validator validator =
        Validation.buildDefaultValidatorFactory()
            .getValidator();

    @Test
    void rejectsNegativeAmount() {
        var invalid = new TransferRequest(
            17L, 53L, new BigDecimal("-1"), "VND");

        assertFalse(validator.validate(invalid).isEmpty());
    }

    @Test
    void acceptsStructurallyValidAmount() {
        var valid = new TransferRequest(
            17L, 53L, new BigDecimal("250000.00"), "VND");

        assertTrue(validator.validate(valid).isEmpty());
        // Không chứng minh source 17 thuộc người dùng hiện tại!
    }
}
```

Test dùng Jakarta Bean Validation provider từ dependencies của ứng dụng (ví dụ Hibernate Validator). Đây là **validation cấp DTO**, chưa test JSON parsing hay owner authorization.

### 22.1. Kiểm tra semantic constraints riêng

Hai account IDs đều hợp lệ về kiểu nhưng bằng nhau; `currency="XYZ"` có ba ký tự và không blank nhưng có thể không nằm trong domain enum. Phải bổ sung domain validation tests cho source!=target, supported currency, state và limit.

### 22.2. Không biến Bean Validation thành quyền sở hữu

`@NotNull`, `@Positive` và `@Size` không thể xác thực principal có quyền rút tiền. Có thể viết custom Bean Validation constraint có truy cập dữ liệu, nhưng không nên che logic domain authorization trong validator mơ hồ; đặt kiểm tra quyền ở service/policy dễ audit và transactional consistency hơn.

## 23. Unit test object-level authorization: negative tests quan trọng hơn

Một test cốt lõi:

```java
// PSEUDOCODE dùng fixtures của dự án:
// account17 thuộc Alice; account53 thuộc Bob.

@Test
void bobCannotDebitAlicesAccount() {
    Authentication bob = loginAs("bob");

    TransferRequest request = new TransferRequest(
        17L, 53L, new BigDecimal("10.00"), "VND");

    assertThrows(AccessDeniedException.class,
        () -> transferService.transfer(bob, request));

    assertEquals(new BigDecimal("1000.00"),
        balanceOf(17L));

    assertEquals(0, newLedgerEntriesFor(17L));
}
```

Các hàm `loginAs`, `balanceOf`, `newLedgerEntriesFor` là **fixtures mô tả**, phải được dự án triển khai. Điều quan trọng: assertion không chỉ xem response `403`, mà còn chứng minh **không có side effects**.

### 23.1. BOLA swap test

Tạo hai users và hai records cùng loại, rồi đổi IDs giữa sessions:

| Principal | Record | Kỳ vọng |
| --- | --- | --- |
| Alice | Alice account | Được phép theo scope/action phù hợp. |
| Alice | Bob account | Từ chối, không side effect. |
| Bob | Bob account | Được phép theo scope/action phù hợp. |
| Bob | Alice account | Từ chối. |
| Anonymous | Bất kỳ private account | Authentication required. |

Lặp cho GET/POST/PATCH/DELETE tùy domain. Một GET có ownership check không chứng minh PATCH cũng có check.

### 23.2. Concurrency test

Với tiền, điểm thưởng hoặc inventory, cần test đồng thời hai requests không vượt số dư/hạn mức. WAF rate limit hoặc validation `amount > 0` không thay locking, transaction isolation hoặc idempotency constraints.

## 24. MockMvc: test Spring Security chain, binding, CSRF

Một Servlet integration test phù hợp cần context thực có `SecurityFilterChain`, controller, DTO validator và mocked/domain service được kiểm soát. Những ví dụ sau minh họa **test design**; phải điều chỉnh security mechanism/fixtures của dự án.

### 24.1. Đường đi JSON không hợp lệ

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TransferMvcBoundaryTest {

    @Autowired MockMvc mvc;

    @Test
    void negativeAmountFailsValidation() throws Exception {
        mvc.perform(post("/api/transfers")
                .contentType("application/json")
                .content("""
                    {
                      "sourceAccountId": 17,
                      "targetAccountId": 53,
                      "amount": -1,
                      "currency": "VND"
                    }
                    """)
                .with(user("alice").authorities("transfer:create"))
                .with(csrf()))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingCsrfTokenIsRejectedForSessionStyleRequest()
            throws Exception {

        mvc.perform(post("/api/transfers")
                .contentType("application/json")
                .content("""
                    {
                      "sourceAccountId": 17,
                      "targetAccountId": 53,
                      "amount": 10,
                      "currency": "VND"
                    }
                    """)
                .with(user("alice").authorities("transfer:create")))
            .andExpect(status().isForbidden());
    }
}
```

Đây là example với cookie/session-style CSRF enabled và `spring-security-test`; nếu application dùng stateless bearer-token API/CSRF policy khác, expectation phải dựa trên threat model thực. Nếu service được gọi khi DTO hợp lệ, test cần mock/fixture chặt để tránh kết nối DB/thực hiện giao dịch thật.

### 24.2. Vì sao tách hai tests?

- Test negative amount có `csrf()` để request không bị CSRF chặn **trước khi** tới Bean Validation.
- Test missing CSRF dùng amount hợp lệ để cô lập behavior của `CsrfFilter`.

Nếu gửi negative amount mà thiếu CSRF, nhận `403` **không chứng minh** DTO validator đã chạy. Đây là lỗi test design phổ biến.

### 24.3. Kiểm tra quyền method/function

```java
@Test
void userWithoutTransferAuthorityIsDenied() throws Exception {
    mvc.perform(post("/api/transfers")
            .contentType("application/json")
            .content("""
                {
                  "sourceAccountId": 17,
                  "targetAccountId": 53,
                  "amount": 10,
                  "currency": "VND"
                }
                """)
            .with(user("reader").authorities("report:read"))
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

Chỉ kiểm tra **function-level authority**, không thay BOLA tests ở service. Phải giữ fallback deny-all và không dùng `permitAll` cho protected operations chỉ để test nhanh.

## 25. HTTP integration: WAF/edge và Servlet khác mock như thế nào?

Để kiểm chứng ranh giới WAF, HTTP parser và request firewall, phải có một staging environment **do bạn sở hữu hoặc có quyền kiểm thử**, cùng loại proxy/HTTP server như production.

### 25.1. Baseline endpoint hợp lệ

```bash
curl -sS -D - -o /dev/null \
  'https://staging.example.test/health'

curl -sS -D - -o /dev/null \
  'https://staging.example.test/api/products?q=phone'
```

Đầu tiên xác minh ingress routing, TLS/Host, backend request ID và response headers cơ bản.

### 25.2. Semicolon hoặc encoded slash

```bash
# Chỉ dùng staging/có quyền; request là ca kiểm thử policy.
curl -sS -D - -o /dev/null \
  'https://staging.example.test/secure;mode=test'

curl -sS -D - -o /dev/null \
  'https://staging.example.test/files/a%2Fb'
```

Một `400` có thể do WAF, gateway, Servlet container hoặc `StrictHttpFirewall`. Dùng event IDs và backend logs để xác định, không tự động nới firewall khi nhận `400`.

### 25.3. Tránh chạy load/fuzzing tùy tiện

Không gửi hàng nghìn malformed requests vào production hoặc endpoints không thuộc quyền kiểm thử. Dùng một số ít cases có mục tiêu, test accounts và giới hạn tốc độ theo phạm vi được phê duyệt. Thử nghiệm load/rate-limit cần phối hợp vận hành vì có thể kích hoạt WAF ban/reputation, tốn phí hoặc ảnh hưởng người dùng.

### 25.4. Đối chiếu representation qua ba hop

Ghi nhận trong môi trường test:

```text
Client request-target / host / method
   -> WAF event và action (ALLOW, BLOCK, CHALLENGE, LOG)
   -> gateway upstream URL/headers đã sanitize
   -> Servlet requestURI/contextPath/servletPath/pathInfo
   -> Spring Security rejected/selected chain
   -> MVC handler và domain validation result
```

Không log full Authorization/Cookie, CSRF token, body chứa PII hoặc raw malformed input không escape. Dùng correlation ID đáng tin, redaction và sampling.

## 26. Ma trận kiểm thử hồi quy đầy đủ

| Case | Edge/WAF | Request firewall | Validation/Auth/Business | Kỳ vọng |
| --- | --- | --- | --- | --- |
| GET `/health` hợp lệ | Chấp nhận | Chấp nhận | Cho phép công khai | 2xx. |
| TRACE `/health` | Có thể chặn | Strict mặc định từ chối | Không vào controller | 4xx, xác định layer. |
| `/public/../admin` | Có thể chặn/normalize | Từ chối nếu tới strict chưa chuẩn hóa | Admin vẫn bảo vệ | Không bypass. |
| Encoded slash `%2F` | Theo WAF parser | Default strict từ chối | Không xử lý file sai | Không bypass. |
| JSON amount âm | Có thể allow | Chấp nhận URL/method | Bean Validation từ chối | 400/contract error. |
| JSON thiếu source ID | Có thể allow | Chấp nhận | Required validation từ chối | 400. |
| JSON amount dương, account khác owner | Có thể allow | Chấp nhận | Resource authorization từ chối | 403/404 theo policy, không side effect. |
| Currency ba ký tự nhưng unsupported | Có thể allow | Chấp nhận | Domain policy từ chối | API validation error. |
| POST session thiếu CSRF | Có thể allow | Chấp nhận | CSRF từ chối | 403. |
| POST user không scope | Có thể allow | Chấp nhận | Function authorization từ chối | 403. |
| User B đọc record A | Có thể allow | Chấp nhận | BOLA check từ chối | Không lộ dữ liệu. |
| Input chứa apostrophe hợp lệ | Có thể false-positive | Thường không cấm | Query bind và output escape | Không SQLi, WAF tuning có scope. |
| Free-form code snippet | Có thể false-positive | Value được parse | Field length/schema + output encoding | Chấp nhận nếu contract cho phép. |
| Oversized body | Edge/container chặn | Có thể không chạy | Không được parse quá giới hạn | 413/khác theo server. |
| Duplicate sensitive JSON key | WAF parser tùy rule | Không parse JSON | JSON parser/schema reject theo config | Không diễn giải mơ hồ. |
| Origin không được phép | WAF có thể allow | Chấp nhận path | CORS policy từ chối | Browser không đọc được. |
| Unknown Host | Ingress virtual host chặn | Host predicate nếu cấu hình | Không đến business | Không route nhầm. |
| Legacy path hợp lệ | WAF allow theo scope | Cấu hình có chủ đích | Auth/validator áp dụng | Pass có kiểm soát. |
| Direct backend bypass WAF | Network policy chặn | Vẫn bảo vệ nếu nhận | Auth/validation không thay | Không có WAF single point of trust. |
| Retry chuyển tiền trùng | Có thể allow | Chấp nhận | Idempotency/business rule xử lý | Không double charge. |
| WAF 403 block page | WAF chặn | Không chạy | Không chạy | Response do edge; không suy CSRF. |
| App 403 không có WAF event | WAF allow | Chấp nhận | Auth/CSRF deny | Không sửa WAF vô cớ. |
| Security headers trên 4xx | Edge tùy config | Chain có thể chưa chạy | Error owner rõ ràng | CSP/HSTS theo chính sách public response. |

### 26.1. Không chỉ xác nhận HTTP status

Trong test các giao dịch và quyền, hãy kiểm:

- Controller/service có bị gọi không.
- DB ledger/balance có thay đổi không.
- Principal và tenant/resource được chọn đúng không.
- Có chứa dữ liệu nhạy cảm trong response/log không.
- CORS và cookie attributes có thay đổi không.
- WAF event là block hay chỉ log/challenge.
- HTTP error được sinh tại edge hay backend.

Một `403` ở edge không chứng minh service có object authorization đúng; một `200` ở service có thể vẫn là sai quyền nếu trả nhầm record.

## 27. Quan sát, logging, WAF telemetry và incident triage

### 27.1. Correlation IDs xuyên suốt các lớp

Một hệ thống vận hành nên có correlation IDs do trusted edge/server tạo hoặc validate, được chuyển qua WAF/gateway/backend theo policy. Chú ý không mặc định tin mọi `X-Request-Id` do client gửi.

Bộ sự kiện tối thiểu có thể ghi:

```text
timestamp
environment / service
safe correlation_id
edge_action: allow / block / challenge / log
edge_rule_id: fixed registry entry
http_status
backend_received: true / false
firewall_rejected: true / false
security_outcome: authn_failed / access_denied / allowed
application_validation_class: schema / range / domain
```

Không cần log full raw request body/URL để phân loại tất cả các events.

### 27.2. Low-cardinality metrics

Các labels như `waf_rule_id=...` hoặc `event=firewall_rejected` có thể dùng nếu tập giá trị được kiểm soát. **Không** gắn raw URI/query/user-agent/token/exception text làm metric tags vô giới hạn.

### 27.3. Những dữ liệu không nên ghi nguyên văn

- `Authorization`, API keys, session Cookie, CSRF tokens.
- Password reset/OAuth codes và signed URLs.
- Thông tin tài chính, PII, raw account numbers.
- Raw CRLF/control chars gây log injection.
- Full file upload bytes hoặc multipart bodies.
- WAF request samples khi chưa có retention/redaction policy.

WAF event logging cũng có rủi ro privacy; cấu hình retention, access controls và redaction theo tổ chức.

### 27.4. Khi WAF báo tấn công nhưng app không có event

Có thể WAF đã chặn **trước backend**. Đây là behavior hợp lệ. Đừng cố bắt mọi WAF block bằng `@ControllerAdvice` hoặc `RequestRejectedHandler` của Spring Security; chúng không được gọi khi request chưa vào Java.

## 28. Sơ đồ quyết định: request lỗi nên sửa ở đâu?

```mermaid
flowchart TD
    A["User thấy request bị lỗi"] --> B{"Có tới backend không?"}
    B -->|Không| C["Kiểm tra TLS/WAF/gateway/HTTP parser"]
    B -->|Có| D{"Có RequestRejectedException?"}
    D -->|Có| E["Kiểm tra StrictHttpFirewall path/method/host/predicates"]
    D -->|Không| F{"Có auth/CSRF/CORS denial?"}
    F -->|Có| G["Authentication / authorization / CSRF / CORS policy"]
    F -->|Không| H{"Có MVC parse/validation error?"}
    H -->|Có| I["DTO/Bean Validation/schema/limits"]
    H -->|Không| J["Service/domain resource permission và invariant"]
    C --> K["Sửa tại owner đúng tầng; test qua public gateway"]
    E --> K
    G --> K
    I --> K
    J --> K
```

### 28.1. Nguyên tắc sửa ở lớp thấp nhất có thông tin đủ

- HTTP parser/ingress: request framing, malformed headers, size limits.
- WAF: signature/anomaly rule, bot/rate policy, managed exception.
- `StrictHttpFirewall`: accept/reject URI/method/host representation.
- MVC: parsing, types, required fields, field schema.
- Domain/service: principal, ownership, state, quotas, transactions.
- Response/browser: CSP/HSTS/SameSite/output encoding.

Không tạo một “fix” ở tầng khác chỉ vì tầng đó dễ sửa cấu hình nhất.

## 29. Reactive/WebFlux: phạm vi khác nhưng nguyên tắc không đổi

Dịch vụ **SPRING_SECURITY_HTTP_PROTECTION** dạy cả Servlet và Reactive. Nhưng `StrictHttpFirewall` trong bài là API **Servlet**, không thể đưa nguyên vào `ServerWebExchange`.

| Mục đích | Servlet | Reactive/WebFlux |
| --- | --- | --- |
| Request | `HttpServletRequest` | `ServerWebExchange`/`ServerHttpRequest` |
| Security chain dispatcher | `FilterChainProxy` | `WebFilterChainProxy` |
| Request firewall | `HttpFirewall` | `ServerWebExchangeFirewall` |
| Strict implementation | `StrictHttpFirewall` | `StrictServerWebExchangeFirewall` |
| Filters | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Handler/controller | Spring MVC | Spring WebFlux |
| DTO validation | MVC Bean Validation | WebFlux validation |
| Real HTTP parser | Tomcat/Jetty/Undertow | Reactor Netty hoặc Reactive server khác |
| Test | MockMvc/Servlet HTTP integration | WebTestClient/Reactive HTTP integration |

### 29.1. Reactive parser cũng nằm trước security

Reactor Netty/other HTTP parsers có thể từ chối malformed requests trước `WebFilterChainProxy`. Một WebTestClient mock exchange không thể chứng minh WAF/gateway handling hoặc HTTP framing trên wire.

### 29.2. Đừng chuyển `HttpFirewall` decorator sang Reactive

Nếu service WebFlux cần policy semicolon/host, đọc Javadoc của `StrictServerWebExchangeFirewall` và các API đăng ký firewall Reactive theo version. Không sao chép code `HttpServletRequest.getServletPath()` hoặc `FirewalledRequest.reset()` sang Reactive; hai stack có vòng đời request khác nhau.

### 29.3. Service authorization vẫn phải thống nhất

Dù endpoint được triển khai bằng MVC hay WebFlux, object ownership và transaction invariants nên ở service/domain layer hoặc policy layer được cả hai entry points áp dụng. Điều này cũng bảo vệ luồng nội bộ không qua WAF.

## 30. Bài tập tình huống và đáp án định hướng

### Tình huống 1 — WAF cho qua, API lộ order của người khác

User B gọi `GET /api/orders/17` với token hợp lệ và nhận order của A.

**Định hướng:** BOLA. Sửa service/object-level authorization; WAF và `StrictHttpFirewall` không chứng minh ownership.

### Tình huống 2 — Encoded slash nhận HTTP 400

Request `/files/a%2Fb` bị 400. Team đề xuất tắt WAF vì cho rằng WAF phá API.

**Định hướng:** xác định tầng: client/edge/parser/Strict. Ưu tiên sửa URL contract/opaque ID; không bật hàng loạt firewall relaxations.

### Tình huống 3 — Sản phẩm cho user nhập code SQL

WAF chặn comment có `SELECT * FROM`, dù app dùng prepared statement.

**Định hướng:** đánh giá false positive, tuning đúng field/route/rule, giữ validation/output encoding; không disable WAF toàn site.

### Tình huống 4 — JSON amount âm

WAF và Strict cho request qua nhưng Bean Validation trả `400`.

**Định hướng:** behavior đúng. Amount là field-level business validation, không phải URL firewall.

### Tình huống 5 — Amount dương nhưng vượt hạn mức

Bean Validation pass, service từ chối.

**Định hướng:** business/domain invariant. Một số validation cần trạng thái account và lịch sử giao dịch, không thể đặt trong static DTO annotations.

### Tình huống 6 — POST bằng session thiếu CSRF

WAF allow, Strict accept, Spring Security trả `403`.

**Định hướng:** kiểm tra `CsrfFilter`, không tắt CSRF hoặc thêm WAF bypass.

### Tình huống 7 — WAF block page thiếu HSTS

Browser thấy `403` do WAF nhưng không có HSTS do Spring header writer thường thêm.

**Định hướng:** response sinh ở edge trước Java. Thiết kế owner HSTS/TLS response policy tại WAF/ingress.

### Tình huống 8 — Direct-to-origin vẫn truy cập được

Public WAF block một request, nhưng client gọi thẳng backend port lại được.

**Định hướng:** vá network isolation, trusted proxy policy; backend vẫn phải có Strict/auth/validation. Không coi WAF là boundary duy nhất.

### Tình huống 9 — Admin route không có fallback deny-all

Security chain `/api/**` dùng authenticated, `/admin/**` cần admin nhưng một URL bất thường chọn nhầm chain.

**Định hướng:** giữ strict URL handling, matcher nhất quán, deny-by-default fallback, method/resource authorization và regression negative tests.

### Tình huống 10 — Một JSON key xuất hiện hai lần

WAF đọc giá trị đầu còn Jackson backend nhận giá trị sau.

**Định hướng:** parser discrepancy. Thiết kế reject duplicate sensitive keys và test real gateway+backend; không chỉ thêm WAF regex.

### Tình huống 11 — Header Forwarded do client tự gửi

Client giả mạo `X-Forwarded-Host` và backend tạo reset link sai host.

**Định hướng:** sanitize forwarded headers ở trusted ingress, canonical URL server-controlled, host validation; WAF không tự chứng minh header trusted.

### Tình huống 12 — Dữ liệu hợp lệ nhưng SQL bị nối chuỗi

Team định cấm dấu nháy trong query và tăng WAF SQLi sensitivity.

**Định hướng:** chuyển sang prepared statements, schema validation phù hợp; WAF chỉ hỗ trợ/virtual patch.

### Tình huống 13 — File upload qua WAF không bị chặn

Ứng dụng nhận file malware nhưng WAF không có deep file scanning.

**Định hướng:** WAF inspection có giới hạn; dùng file validation, sandbox/scanning theo risk, safe storage, ownership và download authorization.

### Tình huống 14 — Giao dịch được gửi lại hai lần

Hai POST hợp lệ làm người dùng bị trừ tiền hai lần.

**Định hướng:** idempotency và transaction concurrency ở service/domain, không thể chỉ dùng rate limit IP.

### Tình huống 15 — WAF có false positives sau release

Một rule mới chặn 20% comments chứa dấu câu.

**Định hướng:** rollback/tune rule đúng scope, xác minh app-level defenses, có feature owner và regression corpus.

### Tình huống 16 — HTTP 429 tăng nhưng không có WAF events

Ứng dụng có rate limiter identity-aware sau authentication.

**Định hướng:** 429 có thể do app. Dùng logs phân lớp, không chỉ xem WAF dashboard.

### Tình huống 17 — WebFlux service không dùng `StrictHttpFirewall`

Team nghĩ phải đăng ký Servlet firewall bean để WebFlux có phòng vệ.

**Định hướng:** dùng `ServerWebExchangeFirewall`/`StrictServerWebExchangeFirewall` và API Reactive đúng version; test WebTestClient và server thật.

### Tình huống 18 — Container trả 413 trước controller

JSON body rất lớn và Bean Validation không chạy.

**Định hướng:** parser/body limit cố ý chặn trước binding; không cần validator chạy để bảo vệ tài nguyên.

### Tình huống 19 — Unauthorized PATCH cùng record

GET kiểm tra ownership, PATCH chỉ kiểm tra role USER rồi sửa record của người khác.

**Định hướng:** BOLA/BFLA phân biệt; mọi operation trên object phải có quyền đúng action. Test GET/PATCH/DELETE riêng.

### Tình huống 20 — Một WAF rule được coi là fix vĩnh viễn

Lỗ hổng SQLi ở app chưa sửa vì WAF đang chặn nhiều payload.

**Định hướng:** virtual patch chỉ giảm nguy cơ. Ưu tiên sửa code ở query sink, test công khai và review vòng đời WAF rule.

## 31. Checklist production

1. **Ghi rõ topology thực tế**, không mặc định WAF luôn có mặt/trên mọi đường.
2. **Xác định ai sở hữu HTTP parser, WAF, `HttpFirewall`, DTO validation và service authorization**.
3. **Giữ `StrictHttpFirewall` strict** trừ khi có use case và security review rõ ràng.
4. **Không dùng WAF như chứng nhận request được an toàn**.
5. **Không dùng firewall acceptance thay quyền người dùng trên object**.
6. **Không đặt business rules ở WAF signatures hoặc global parameter predicates**.
7. **Sửa SQLi bằng prepared statements**, không chỉ regex block keywords.
8. **Sửa XSS bằng contextual output encoding**, phối hợp CSP phù hợp.
9. **Thiết kế DTO chỉ chứa client-editable fields**, tránh mass assignment.
10. **Phân biệt syntax, field, cross-field, domain và stateful validations**.
11. **Enforce function-level authorization và object-level authorization riêng**.
12. **Test swap IDs giữa users/tenants** cho mọi operation nhạy cảm.
13. **Bảo vệ CSRF khi browser cookie credentials có thể bị lợi dụng**, không nhầm với CORS.
14. **Giới hạn request sizes/counts/nesting ở edge/parser**, trước khi parse vào bộ nhớ.
15. **Cấu hình trusted forwarded headers đúng**, không tin client X-Forwarded-*.
16. **Không cho direct-to-origin bypass WAF** ngoài đường được phê duyệt.
17. **Kiểm chứng WAF có inspect đúng protocols, JSON, multipart, traffic paths thực**.
18. **Đặt WAF exceptions theo route/field/rule nhỏ nhất và có expiration**.
19. **Kiểm tra false positives và false negatives** với corpus đầu vào hợp lệ/không hợp lệ.
20. **Không tự decode URI nhiều lần sau authorization**, tránh parser mismatch.
21. **Giữ deny-by-default fallback security chain và service-level permissions**.
22. **Thiết kế idempotency, rate limits và transaction invariants theo nghiệp vụ**.
23. **Tách unit firewall, DTO validation, resource authorization, MockMvc và real HTTP tests**.
24. **Bảo đảm test negative cases không làm thay đổi storage/ledger**.
25. **Không suy HTTP 400/403/429 cho riêng một tầng nếu thiếu correlation evidence**.
26. **Thiết lập response CSP/HSTS/cookie policies tại tầng tạo response phù hợp**.
27. **Ghi log có redaction, escaping, low-cardinality labels và retention controls**.
28. **Giữ WAF virtual patches có owner, runbook, ngày review và kế hoạch sửa app**.
29. **Kiểm thử sau upgrade gateway, Spring Security, Servlet server và JSON parser**.
30. **Áp cùng domain authorization cho REST, WebFlux, jobs và internal event handlers**.
31. **Chuẩn bị rollback khi WAF rule hoặc custom firewall mở rộng surface ngoài dự kiến**.
32. **Đánh giá an toàn theo tài nguyên/thao tác thật, không theo số request đã bị chặn**.

## 32. Kết luận

**WAF** là lớp giảm thiểu tấn công tổng quát ở hạ tầng HTTP, có thể dựa trên signatures, anomaly scores, body inspection và rate/bot policies. **`StrictHttpFirewall`** là guard ở Servlet security boundary, tập trung bảo đảm request representation đủ nhất quán và từ chối các hình thức HTTP đáng ngờ trước hoặc trong security processing. **Validation và authorization của ứng dụng** xác định dữ liệu có đúng schema, nghiệp vụ có hợp lệ và principal có quyền thao tác trên resource thật hay không.

Không chọn giữa ba lớp như thể chỉ được bật một. Hãy để từng lớp làm tốt việc của nó, đồng thời dùng negative tests để chứng minh **một lớp chấp nhận request không vô hiệu quyết định bảo mật của lớp khác**. Đặc biệt, WAF block rules không thể thay sửa lỗ hổng code, còn một request đã vượt firewall vẫn cần kiểm tra quyền trên mọi object và transaction.

### Tài liệu tham khảo

- [Spring Security Reference — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html)
- [Spring Security Javadoc — StrictHttpFirewall](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html)
- [Spring Security Javadoc — FilterChainProxy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security Reference — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security Reference — HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Framework Reference — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Security Javadoc — StrictServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/firewall/StrictServerWebExchangeFirewall.html)
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/)
- [OWASP Web Security Testing Guide — Application Architecture / WAF](https://wstg.owasp.org/latest/05-Information_Gathering/09-Map_Application_Architecture/)
- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP Web Cache Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Web_Cache_Security_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP ModSecurity Core Rule Set](https://coreruleset.org/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112)
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)

