# Header name, header value và ràng buộc ký tự

## 1. Vì sao firewall cần kiểm tra tên và giá trị HTTP header?

Trong chương **Firewall trên Servlet** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, chúng ta tìm hiểu các ranh giới bảo vệ HTTP của Spring Security: `HttpFirewall`, lựa chọn `SecurityFilterChain`, authentication, authorization, CSRF, CORS, security headers, CSP, HSTS và bảo vệ session. Các biện pháp ấy bảo vệ những vấn đề khác nhau nhưng cùng dựa trên một yêu cầu: **request mà ứng dụng xử lý phải được diễn giải đủ nhất quán và đáng tin cậy**.

HTTP headers mang nhiều loại dữ liệu:

```http
GET /api/orders/42 HTTP/1.1
Host: app.example.test
Accept: application/json
Origin: https://ui.example.test
Authorization: Bearer example-access-token
X-Request-Id: 7f3a91
```

Tên header như `Host`, `Origin`, `Authorization` hoặc `X-Request-Id` có cú pháp riêng; giá trị header có thể chứa dấu cách, dấu phân cách, parameter, token hoặc chuỗi theo định dạng đặc thù. Nếu header name hoặc value chứa **ký tự điều khiển**, **ký tự Unicode chưa được định nghĩa**, hay một dạng nội dung không phù hợp với parser/logging, các tầng HTTP có thể diễn giải khác nhau.

`StrictHttpFirewall` của Spring Security Servlet cung cấp hai điểm cấu hình quan trọng:

- `setAllowedHeaderNames(Predicate<String>)`: xác định những **tên header** được chấp nhận.
- `setAllowedHeaderValues(Predicate<String>)`: xác định những **giá trị header** được chấp nhận.

Trong nhiều phiên bản Spring Security hiện đại, mặc định các predicate loại bỏ những ký tự điều khiển và những ký tự Unicode không được định nghĩa; một số phiên bản có ngoại lệ cho **horizontal tab trong header value**. Việc này bổ sung một lớp kiểm tra request sau Servlet HTTP parser, nhưng **không thay thế HTTP parser, validation nghiệp vụ, quản lý trusted proxy hay authorization**.

Một chi tiết đặc biệt quan trọng: **kiểm tra header name/value trong `StrictHttpFirewall` có thể được thực hiện khi `FirewalledRequest` đọc hoặc duyệt header**, không nhất thiết quét toàn bộ headers ngay trong lời gọi `getFirewalledRequest(...)`. Vì thế, không được kết luận một request đã có tất cả header hợp lệ chỉ vì firewall tạo wrapper thành công.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **HTTP header field name** với **field value** theo HTTP semantics.
2. Giải thích default predicates của `StrictHttpFirewall` và giới hạn của việc kiểm tra dựa trên Java `String`.
3. Hiểu khi nào `getHeader`, `getHeaders` và `getHeaderNames` có thể kích hoạt `RequestRejectedException`.
4. Phân biệt ký tự HTTP name token, khoảng trắng, HTAB, CR, LF, Unicode code points và các ký tự điều khiển.
5. Cấu hình `setAllowedHeaderNames`/`setAllowedHeaderValues` có chủ đích, giữ những quy tắc an toàn đang có.
6. Không đánh đồng *ký tự hợp lệ* với *header có giá trị đáng tin*; nhận diện rủi ro từ `Host`, `Origin`, `Forwarded`, `Authorization` và `Cookie`.
7. Viết unit tests, MockMvc tests và kiểm chứng qua HTTP server/proxy.
8. Chẩn đoán request bị từ chối ở Servlet container, firewall, CORS, authentication hoặc application validation.
9. Phân biệt API Servlet với firewall trên Reactive/WebFlux.

## 2. Header field name và field value không có chung ngữ pháp

Một dòng HTTP/1.1 header thông thường có dạng khái niệm:

```text
field-name ":" OWS field-value OWS
```

`OWS` là *optional whitespace* theo HTTP grammar. **Tên** là định danh của header field, còn **giá trị** chứa dữ liệu thuộc cú pháp riêng của field đó.

Ví dụ:

```http
Content-Type: application/json; charset=utf-8
Cache-Control: private, max-age=60
If-None-Match: "abc123"
X-Request-Id: rq-2026-0042
```

### 2.1. Tên header là một token, không phải tùy ý Unicode

Theo HTTP Semantics (RFC 9110), **field name** tuân theo cú pháp `token`, dùng tập ký tự ASCII được quy định. Những dấu thường có thể xuất hiện gồm:

```text
! # $ % & ' * + - . ^ _ ` | ~
```

cùng chữ cái `A-Z`, `a-z` và chữ số `0-9`. Trong đoạn minh họa trên, dấu huyền ngược (backtick, U+0060) thuộc tập `tchar`; đây là ký tự của tên HTTP field, không phải dấu phân cách Markdown.

Một số tên thông thường:

```text
Host
Content-Type
X-Request-Id
If-None-Match
Sec-Fetch-Site
X_Custom_Header
```

Tên chứa dấu cách, dấu hai chấm thông thường, CR hoặc LF **không thuộc cú pháp field name chuẩn**. Chẳng hạn `X Request Id` không phải một tên HTTP field hợp lệ theo RFC.

Tuy nhiên, **các proxy có thể có chính sách bổ sung**: ví dụ một proxy không forward headers có underscore theo cấu hình nhất định dù underscore là ký tự được phép trong `token`. Vì vậy “đúng ngữ pháp HTTP” và “được mọi hạ tầng chấp nhận” vẫn là hai câu hỏi khác nhau.

### 2.2. Giá trị header có thể có khoảng trắng và dấu phân cách

`Content-Type: application/json; charset=utf-8` chứa dấu `;`, dấu `=`, dấu `/` và khoảng trắng trong **value**; đây là cấu trúc bình thường. Một rule toàn cục cấm dấu `;` trong mọi header value sẽ phá nhiều headers hợp lệ, kể cả khi mục tiêu ban đầu chỉ là kiểm tra một custom header.

Ví dụ:

| Header | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `Accept` | `application/json, text/plain;q=0.9` | Danh sách media ranges, dấu phẩy, semicolon. |
| `Content-Type` | `application/json; charset=utf-8` | Media type và parameter. |
| `Authorization` | `Bearer eyJ...` | Scheme và credentials token. |
| `Cookie` | `sid=abc; theme=dark` | Nhiều cookie pairs. |
| `Origin` | `https://ui.example.test` | Origin của caller trong CORS. |
| `If-None-Match` | `"etag-42"` | Entity tag dùng trong conditional requests. |
| `User-Agent` | `ExampleClient/2.0 (demo)` | Client product information. |
| `X-Request-Id` | `req-4ca9` | Correlation identifier do hệ thống định nghĩa. |

Vì ngữ pháp **value** thay đổi theo từng field, `StrictHttpFirewall` chỉ đóng vai trò **kiểm tra các ký tự được chấp nhận ở mức chung**; application vẫn phải parse và validate từng trường theo mục đích.

### 2.3. Tên header không phân biệt chữ hoa/thường

Theo HTTP semantics, `Content-Type` và `content-type` chỉ cùng một field name. Không nên viết allowlist tên header bằng một phép so sánh phân biệt hoa/thường rồi bất ngờ chặn những client hợp lệ.

Ví dụ, nếu một kiểm tra custom header yêu cầu `X-Client-Mode`:

```java
// Minh họa kiểm tra một header theo tên, không phải firewall policy.
boolean isClientModeHeader =
    "X-Client-Mode".equalsIgnoreCase(headerName);
```

Đừng đưa ra quy tắc chỉ chấp nhận đúng cách viết `X-Client-Mode` trong một policy firewall toàn cục khi HTTP/2 còn yêu cầu header field names được mã hóa chữ thường trên đường truyền.

## 3. Ranh giới parser: ứng dụng Servlet không thấy mọi byte thô

`StrictHttpFirewall` xử lý `HttpServletRequest` **sau khi** một HTTP server và Servlet container đã phân tích request.

```mermaid
flowchart TD
    A["Client gửi HTTP/1.1 hoặc HTTP/2"] --> B["CDN / gateway / reverse proxy"]
    B --> C["HTTP parser của Tomcat, Jetty hoặc Undertow"]
    C --> D{"Request hợp lệ ở tầng parser?"}
    D -->|Không| R["HTTP error từ proxy/container"]
    D -->|Có| E["HttpServletRequest"]
    E --> F["DelegatingFilterProxy"]
    F --> G["FilterChainProxy"]
    G --> H["StrictHttpFirewall: method/path/host; bọc request"]
    H --> I["Chọn SecurityFilterChain"]
    I --> J["Filters/handlers đọc header qua FirewalledRequest"]
    J --> K["Header name/value predicate có thể được kiểm tra khi đọc"]
    K --> L["Controller / service"]
    R --> M["Client thấy response"]
    L --> M
```

Có ba ranh giới khác nhau:

1. **On-wire HTTP bytes/frames:** syntax, header compression, request framing, kích thước header block và những giới hạn protocol.
2. **Servlet API:** `getHeader`/`getHeaders`/`getHeaderNames` trả `String` hoặc `Enumeration<String>` sau parser/connector.
3. **Spring Security firewall wrapper:** thêm policy dựa trên request representation mà Servlet cung cấp.

Một request chứa ký tự không hợp lệ có thể bị NGINX hoặc Tomcat trả `400` **trước khi Java nhận request**. Ngược lại, một `MockHttpServletRequest` có thể chứa header name/value bất thường mà HTTP server thật sẽ không bao giờ cho qua.

### 3.1. HTTP/2 và HTTP/3 có khác biệt gì?

HTTP/2 và HTTP/3 dùng framing và header field representations khác HTTP/1.1. Trong HTTP/2, field names trên đường truyền phải dùng chữ thường; pseudo-headers như `:method`, `:path` và `:authority` mang thông tin điều khiển đặc biệt.

**Không đưa pseudo-header như `:method` vào `setAllowedHeaderNames` của Servlet rồi coi nó là một header field ứng dụng bình thường.** HTTP server xử lý pseudo-headers ở protocol layer và sau đó trình bày `HttpServletRequest` tương ứng.

Những ràng buộc như HTTP/2 header-list size, compression handling, pseudo-header ordering hoặc framing attacks cũng không thể được giải quyết chỉ bằng hai Java `Predicate<String>`.

### 3.2. Các tầng có thể normalize hoặc từ chối headers khác nhau

Gateway có thể loại một header, chuẩn hóa tên, hợp nhất nhiều giá trị hoặc bổ sung forwarded headers trước khi gửi upstream. Vì vậy việc kiểm thử cần xác định **headers thực sự đến backend**, không chỉ headers client nghĩ rằng đã gửi.

Một số HTTP libraries cũng từ chối CR/LF trong values ngay lúc xây request. Không cố qua mặt thư viện bằng các request malformed khi không có môi trường kiểm thử được cấp phép.

## 4. `StrictHttpFirewall` kiểm tra header thế nào?

`StrictHttpFirewall` là một implementation `HttpFirewall` của Spring Security Servlet. Nó thường được `FilterChainProxy` áp **trước khi chọn `SecurityFilterChain`** để kiểm tra method, URL và host rồi tạo `FirewalledRequest`.

Nhưng các kiểm tra **header name/value** có tính chất riêng: `FirewalledRequest` override các thao tác đọc header và dùng predicates lúc dữ liệu được truy cập.

### 4.1. Các API cốt lõi

```java
StrictHttpFirewall firewall = new StrictHttpFirewall();

firewall.setAllowedHeaderNames(namePredicate);
firewall.setAllowedHeaderValues(valuePredicate);
```

Các tham số là `Predicate<String>`. Mỗi predicate quyết định một `String` có được phép hay không:

- `test(value) == true`: giá trị được predicate chấp nhận.
- `test(value) == false`: firewall có thể ném `RequestRejectedException` khi header được truy cập qua wrapper.
- Predicate trả `true` không chứng minh syntax/semantics của một header đã hợp lệ; nó chỉ đạt **điều kiện predicate đó**.

**Đừng nhầm với `setAllowedParameterNames` và `setAllowedParameterValues`**: hai API này xử lý request parameters, không phải HTTP headers.

### 4.2. Kiểm tra lazy khi đọc: chi tiết nhiều tài liệu bỏ qua

Trong những phiên bản Spring Security hiện đại, source `StrictHttpFirewall` có hành vi tương ứng:

| Thao tác trên `FirewalledRequest` | Loại kiểm tra |
| --- | --- |
| `getHeader("X-Id")` | Kiểm tra **tên được yêu cầu**, sau đó kiểm tra **giá trị trả về** nếu có. |
| `getHeaders("X-Id")` | Kiểm tra tên; mỗi giá trị được kiểm tra **khi Enumeration trả phần tử**. |
| `getHeaderNames()` | Tên được kiểm tra **khi Enumeration trả từng phần tử**. |
| `getIntHeader(name)` / `getDateHeader(name)` | Kiểm tra tên; Servlet API chuyển đổi giá trị theo ngữ nghĩa riêng. |
| `getFirewalledRequest(request)` | Kiểm tra method/path/host rồi trả wrapper; **không nên giả định đã duyệt mọi header**. |

Ví dụ khái niệm:

```java
FirewalledRequest safe =
    firewall.getFirewalledRequest(originalRequest);

// Các thao tác đọc sau đây có thể kích hoạt kiểm tra header:
String requestId = safe.getHeader("X-Request-Id");

Enumeration<String> allNames = safe.getHeaderNames();
while (allNames.hasMoreElements()) {
    String name = allNames.nextElement();
    // Tên đã được kiểm tra khi trả về trong wrapper tương ứng.
}
```

Hành vi chi tiết có thể thay đổi theo phiên bản. Điều cần nhớ là **một request có header xấu nhưng không hề được ứng dụng đọc không nhất thiết bị `StrictHttpFirewall` từ chối chỉ vì wrapper được tạo**. Ngoài ra, nhiều header không hợp lệ bị chặn từ parser trước đó.

### 4.3. Nhiều giá trị cùng tên

`getHeader("X-Test")` thường lấy giá trị đầu tiên, trong khi `getHeaders("X-Test")` duyệt toàn bộ các values. Nếu cùng tên header xuất hiện nhiều lần, chỉ kiểm tra giá trị đầu tiên không chứng minh mọi giá trị còn lại đã được validate bởi cùng một code path.

Ví dụ:

```text
X-Demo: first
X-Demo: second
```

Một số HTTP headers cho phép gộp nhiều giá trị thành danh sách; một số khác có quy tắc đặc biệt như `Set-Cookie` ở **response**. Không tự hợp nhất `Authorization`, `Content-Length` hoặc `Host` theo cách tùy tiện. Những field liên quan framing/authority cần để HTTP server xử lý đúng protocol.

### 4.4. Security chain matcher có thể đọc header trước controller

Nếu `RequestMatcher` kiểm tra `Origin`, `User-Agent` hoặc một custom header, việc đọc header qua wrapper có thể làm xuất hiện `RequestRejectedException` **ngay trong lúc chọn chain**, trước `AuthorizationFilter`.

Trong tình huống khác, header chỉ được `@RequestHeader` ở controller đọc sau authorization, nên rejection có thể xảy ra muộn hơn. Hai request cùng có header không hợp lệ có thể có đường đi khác nhau tùy code có đọc header hay không.

Đây là lý do cần **kiểm thử đúng code path**, không chỉ xác minh `getFirewalledRequest(...)` trả object.

## 5. Mặc định: ký tự Unicode được định nghĩa và không phải control

Theo Spring Security Reference/Javadoc của `StrictHttpFirewall`, các ràng buộc mặc định cho **header names** và **header values** nhằm từ chối những ký tự không được định nghĩa và ký tự điều khiển ISO.

Ở các nguồn mã hiện đại, mặc định được biểu diễn bằng predicates dùng nhóm Unicode như `\p{IsAssigned}` và `\p{IsControl}`. Có phiên bản cho phép **HTAB** (U+0009) trong header **value** nhưng không trong header **name**, phù hợp với việc HTTP field value có thể chứa horizontal whitespace theo ngữ cảnh.

Do đó cần phân biệt ba lớp quy tắc:

1. **HTTP field-name grammar** (RFC 9110): tên là một ASCII token với tập ký tự `tchar`.
2. **Servlet container parser**: kiểm tra HTTP syntax ở tầng server.
3. **`StrictHttpFirewall` predicates**: bộ lọc ở Java `String` sau parser.

**Không tuyên bố default predicate của firewall là một parser RFC 9110 đầy đủ.** Nó có thể cho phép một code point “được định nghĩa, không phải control” về mặt Unicode dù tên header đó không hợp ngữ pháp ASCII token, nếu trước đó parser không chặn. Ngược lại, HTTP parser có thể từ chối những bytes mà firewall chưa từng nhìn thấy.

### 5.1. Những nhóm ký tự cần hiểu

| Ký tự/nhóm | Trong tên header | Trong giá trị header | Ghi chú |
| --- | --- | --- | --- |
| Chữ cái ASCII và chữ số | Hợp lệ khi thuộc `token` | Hợp lệ theo field syntax | Nhóm phổ biến nhất. |
| Dấu `-` và `_` | Thuộc `tchar` | Có thể xuất hiện | Proxy có thể có policy riêng với underscore. |
| Dấu `:` | Không hợp lệ trong tên field thông thường | Có thể xuất hiện trong URL/time/scheme | HTTP/2 pseudo-header là trường hợp protocol riêng, không phải application field name. |
| Dấu cách `SP` | Không thuộc header name token | Thường hợp lệ trong field value theo cú pháp field | Tránh whitespace bao quanh giá trị khi không cần. |
| Tab `HTAB` | Không thuộc header name token | Có thể được chấp nhận trong value ở một số implementation/policy | Không tự đưa tab vào dữ liệu tùy tiện. |
| `CR` (U+000D), `LF` (U+000A) | Không hợp lệ | Không cho phép trong field value thông thường | Liên quan header splitting/obs-fold và parser ambiguity. |
| NUL U+0000, ESC U+001B | Không hợp lệ | Nên bị từ chối | Ký tự điều khiển. |
| Unicode chưa được gán | Không thuộc RFC field name token | Default firewall thường từ chối | Ngữ nghĩa Java `String` và code point. |
| Unicode được gán ngoài ASCII | Không thuộc RFC field name token | Việc có được chấp nhận tùy parser/encoding và field-specific syntax | Không suy cứ thuộc `IsAssigned` là hợp lệ on-wire. |

### 5.2. Case-insensitive tên, case-sensitive giá trị khi protocol yêu cầu

Field names không phân biệt hoa/thường; **field values không có một quy tắc so sánh chung**. Ví dụ token bearer credentials, ETag và resource identifiers có thể nhạy cảm với chữ hoa/thường, trong khi một số token protocol khác có quy tắc riêng.

Vì vậy không lower-case **mọi giá trị header** để so sánh hoặc lưu vào log, đặc biệt `Authorization` và chữ ký HMAC.

### 5.3. Không dùng Unicode normalization làm biện pháp sửa header tùy tiện

Một header name chứa ký tự trông giống `A` hoặc dấu phân cách tương tự không nên được “sửa” bằng việc normalize Unicode rồi mới so security rule. Header field names là token theo ngữ pháp ASCII; application nên dùng **tên chuẩn được định nghĩa rõ ràng**, và để parser/firewall từ chối representation không hợp đồng.

Với values chứa Unicode theo format nghiệp vụ, áp validation tại field-specific parser, không “chuyển mọi ký tự lạ thành dấu hỏi” rồi tiếp tục tin dữ liệu đã được sửa.

## 6. CR, LF và header injection: ranh giới quan trọng

`CR` là carriage return (U+000D), `LF` là line feed (U+000A). Trong HTTP/1.x truyền thống, `CRLF` là dấu phân cách dòng. Nếu một thành phần cho phép chuỗi control này đi vào nơi dựng hoặc xử lý headers không an toàn, có thể phát sinh **header injection**, **response splitting** hoặc log ambiguity.

Ví dụ minh họa chuỗi *trong Java String*, không phải một request hợp lệ để gửi qua Internet:

```java
String unsafeValue = "request-42\r\nX-Injected: yes";
```

Trong một mock Servlet request, giá trị trên có thể được đặt trực tiếp vào header để kiểm thử `StrictHttpFirewall`. Trên đường truyền, nhiều HTTP clients, reverse proxies và Servlet containers sẽ từ chối nó trước khi Spring Security chạy.

### 6.1. Tên header chứa CR/LF

```java
String invalidName = "X-Request-Id\nFake-Header";
```

Một tên như vậy vi phạm ngữ pháp HTTP token và predicate mặc định của firewall. Nếu tạo `MockHttpServletRequest` chứa tên này rồi duyệt `getHeaderNames()` trên `FirewalledRequest`, test có thể chứng minh rejection trong Java. Nhưng HTTP server thật rất có thể không tạo `HttpServletRequest` cho một header field name như thế.

### 6.2. Giá trị header chứa CR/LF

```java
String invalidValue = "trace-42\r\nInjected: yes";
```

`StrictHttpFirewall` thường từ chối các control chars này khi header value được đọc qua wrapper. Không được chỉ kiểm tra `getFirewalledRequest(...)` rồi kết luận giá trị đã bị từ chối; test phải **thực sự gọi `getHeader(...)` hoặc duyệt `getHeaders(...)`**.

### 6.3. OBS-FOLD và HTTP parser

Các quy tắc HTTP hiện đại không khuyến khích/không cho phép xử lý gộp dòng kiểu cũ `obs-fold` trong những ngữ cảnh không thích hợp. Tầng server có thể từ chối hoặc xử lý khác nhau tùy protocol/version. Spring Security không phải HTTP parser chịu trách nhiệm chính cho việc phân tích CRLF trên đường truyền.

Bảo vệ đúng là **parser standards-compliance + firewall predicates + không phản chiếu dữ liệu vào response headers bừa bãi**. Không xem một Java predicate là biện pháp ngăn chặn mọi kiểu HTTP request smuggling hoặc response splitting.

### 6.4. Tại sao không tắt kiểm tra bằng `value -> true`?

Một số ứng dụng legacy muốn “chấp nhận mọi thứ cho tương thích”:

```java
StrictHttpFirewall firewall = new StrictHttpFirewall();

// ANTI-PATTERN nếu chỉ nhằm bỏ qua mọi lỗi header:
// firewall.setAllowedHeaderNames(name -> true);
// firewall.setAllowedHeaderValues(value -> true);
```

Khi tắt predicate như trên, lớp firewall không còn chặn những tên/giá trị chứa control characters mà nó có thể thấy. Đây là thay đổi rộng và phải có threat model rất đặc biệt; **không dùng làm mặc định production**.

Ngay cả khi tầng parser thường chặn CRLF, vẫn có thể có mock tests, filter wrappers hoặc ứng dụng legacy tạo/chuyển header theo các cách không dự kiến. Giữ defense in depth là lựa chọn tốt hơn.

## 7. Mặc định không phải allowlist nghiệp vụ cho `Host` hay `Origin`

Một giá trị header có **ký tự được phép** không đồng nghĩa nó được **tin cậy**. Cần hiểu một số headers có ý nghĩa bảo mật riêng.

### 7.1. `Host` và trusted hostname

Client có thể gửi:

```http
Host: attacker.example
```

Chuỗi `attacker.example` chỉ gồm ký tự bình thường; nó có thể vượt predicate mặc định về **header value**. Nhưng ứng dụng có thể chỉ phục vụ `app.example.test` và không được dùng `Host` tùy ý để xây redirect, URL tuyệt đối, callback hoặc link reset password.

Spring Security `StrictHttpFirewall` có **`setAllowedHostnames(Predicate<String>)`** để bổ sung quy tắc hostname, nhưng vẫn cần cấu hình trusted host/proxy ở ingress và server.

Ví dụ:

```java
import java.util.Locale;
import java.util.Set;
import org.springframework.security.web.firewall.StrictHttpFirewall;

StrictHttpFirewall firewall = new StrictHttpFirewall();

Set<String> approvedHosts = Set.of(
    "app.example.test", "localhost");

firewall.setAllowedHostnames(host ->
    host != null
        && approvedHosts.contains(
            host.toLowerCase(Locale.ROOT)));
```

Đây là **mẫu minh họa**. Trong production, phải xét cách `getServerName()` phản ánh Host, trusted forwarding, internal upstream hostnames, IDN, ports và environment-specific aliases. Không giả định một predicate này thay thế toàn bộ host-header trust boundary.

### 7.2. `Origin` và CORS

`Origin: https://evil.example` có cú pháp ký tự hợp lệ, nhưng ứng dụng CORS có thể **không cho phép** origin đó.

- `StrictHttpFirewall` predicate kiểm tra **ký tự** trong header value theo policy.
- CORS configuration kiểm tra **nguồn truy cập cross-origin** và requested headers/method.
- Authentication/authorization kiểm tra **danh tính và quyền**.

Không sửa một lỗi CORS bằng `setAllowedHeaderValues(value -> true)`; hai quyết định hoàn toàn khác nhau.

### 7.3. `Forwarded`, `X-Forwarded-Host` và `X-Forwarded-Proto`

Các headers forwarded có thể mô tả client scheme/host/remote IP từ proxy. Nhưng nếu bất kỳ client Internet nào cũng được tự gửi và ứng dụng tin chúng, có thể ảnh hưởng redirect, cookie `Secure`, HSTS, callback URL hoặc audit.

Ví dụ:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
```

Cả hai values có ký tự hợp lệ. **Điều đó không chứng minh chúng đến từ proxy đáng tin.** Cần cấu hình ingress để loại hoặc ghi đè các headers do client tự gửi, và chỉ bật forwarded-header processing theo trust boundary rõ ràng.

### 7.4. `Authorization` và `Cookie`

`Authorization` và `Cookie` thường chứa dữ liệu nhạy cảm. Predicate mặc định của firewall không xác thực JWT, chữ ký, session ID, thời hạn cookie hay tính hợp lệ của credentials.

Với bearer token, Spring Security authentication provider/filter xử lý token semantics sau những bước thích hợp. Với session cookie, session management, CSRF và cookie attributes (`Secure`, `HttpOnly`, `SameSite`) đóng vai trò khác.

**Không log nguyên `Authorization` hoặc `Cookie`** khi debug một request bị firewall từ chối; đặc biệt không in cả header map chỉ để xem ký tự.

## 8. Request headers và response security headers là hai hướng khác nhau

Chủ đề bài này nói về **header names/values trong HTTP request** nhận từ client. Trong khi đó:

- `Content-Security-Policy` (CSP)
- `Strict-Transport-Security` (HSTS)
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`
- `Access-Control-Allow-Origin`

là những **response headers** thường do Spring Security, MVC hoặc reverse proxy phát cho browser.

`StrictHttpFirewall#setAllowedHeaderValues` **không phải API để thiết lập CSP/HSTS**. Nếu một ứng dụng muốn thêm CSP, nó dùng response header writer/`headers(...)` hoặc tầng response phù hợp; không thay predicate input.

Tương tự, một request chứa CRLF trong header có thể bị từ chối rất sớm, khiến response lỗi **không đi qua `HeaderWriterFilter`**. Lỗi response thiếu CSP/HSTS không tự chứng minh firewall hoạt động sai. Nếu tổ chức yêu cầu baseline security headers cho mọi public error response, cần xác định tầng nào tạo response và thiết kế policy tại đó.

## 9. Cấu hình `setAllowedHeaderNames`: mở hay thắt phải có chủ đích

Với nhiều ứng dụng, **giữ mặc định** là đủ. Khi cần chính sách chặt hơn cho tên header, hãy **kết hợp** ràng buộc hiện hành thay vì thay bằng predicate “luôn đúng”.

### 9.1. Ví dụ siết tên header theo RFC `token`

Đoạn sau minh họa một predicate chặt hơn: chỉ chấp nhận những tên header là ASCII `token`, đồng thời giữ predicate mặc định của `StrictHttpFirewall` nếu phiên bản cung cấp hằng số công khai tương ứng.

```java
import java.util.regex.Pattern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
class HeaderNameFirewallConfig {

    // RFC 9110 tchar: ! # $ % & ' * + - . ^ _ ` | ~, chữ và số.
    private static final Pattern FIELD_NAME_TOKEN = Pattern.compile(
        "[!#$%&'*+.^_`|~0-9A-Za-z-]+");

    @Bean
    WebSecurityCustomizer firewallCustomizer() {
        return web -> {
            StrictHttpFirewall firewall = new StrictHttpFirewall();

            firewall.setAllowedHeaderNames(
                StrictHttpFirewall.ALLOWED_HEADER_NAMES.and(
                    name -> FIELD_NAME_TOKEN.matcher(name).matches()));

            web.httpFirewall(firewall);
        };
    }
}
```

Sau khi thay placeholder Markdown, ký tự backtick trong regex là một ký tự literal thuộc `tchar`. Đây là **mẫu tăng ràng buộc**, không phải điều mọi ứng dụng cần thêm. HTTP parser của container thường đã áp các điều kiện tên field; việc siết tại firewall chỉ bổ sung kiểm soát trong Java.

**Lưu ý version:** `StrictHttpFirewall.ALLOWED_HEADER_NAMES` là public predicate ở các bản hiện đại; kiểm tra Javadoc đúng Spring Security version đang dùng trước khi sao chép. Nếu version không có hằng số này, hãy chọn cách giữ mặc định thay vì giả định một API không tồn tại.

### 9.2. Không viết allowlist chỉ cho headers bạn biết

Ví dụ sai:

```java
// RỦI RO: có thể từ chối Host, Accept, Cookie, Authorization,
// CORS preflight headers, tracing headers hoặc headers do HTTP client thêm.
firewall.setAllowedHeaderNames(
    name -> "X-My-Header".equalsIgnoreCase(name));
```

Predicate áp ở **mức firewall cho mọi headers được đọc**, không chỉ header do ứng dụng tự thiết kế. Một allowlist chỉ có `X-My-Header` có thể làm vỡ các request hợp lệ từ browser, load balancer và monitoring.

Nếu bạn chỉ muốn giới hạn **các giá trị cho một custom header**, thường phù hợp hơn khi parse/validate riêng field đó ở controller, filter nghiệp vụ hoặc service.

### 9.3. HTTP field names theo phương thức khác nhau

Trong HTTP/2, field names trên đường truyền cần là lowercase, nhưng `Servlet` trừu tượng hóa request sau parse. Nếu quy định “chỉ chấp nhận uppercase X-...” tại `setAllowedHeaderNames`, một browser HTTP/2 hợp lệ có thể bị loại. Một predicate tên field an toàn nên **không tự áp giới hạn casing** trái với HTTP semantics.

## 10. `setAllowedHeaderValues`: global value predicate có giới hạn

`setAllowedHeaderValues(Predicate<String>)` chỉ nhận **giá trị**, không nhận tên header tương ứng. Vì vậy nó phù hợp với những quy tắc **chung cho mọi header values** (ví dụ không có ký tự control), không phù hợp để diễn tả quy tắc “`X-Client-Mode` chỉ có giá trị `summary` hoặc `full`”.

### 10.1. Vì sao không so value bằng một danh sách hẹp?

Anti-pattern:

```java
// KHÔNG dùng: áp cho mọi header, từ Authorization đến Accept.
firewall.setAllowedHeaderValues(
    value -> "summary".equals(value) || "full".equals(value));
```

Nó sẽ từ chối `Accept: application/json`, `Content-Type: application/json`, `Authorization: Bearer ...` và vô số values bình thường khác khi chúng được đọc.

### 10.2. Nếu siết chung, hãy giữ default predicate

Một ví dụ chỉ dùng khi tổ chức có **một chính sách toàn cục thực sự** và đã kiểm tra tương thích:

```java
StrictHttpFirewall firewall = new StrictHttpFirewall();

firewall.setAllowedHeaderValues(
    StrictHttpFirewall.ALLOWED_HEADER_VALUES.and(
        value -> value.length() <= 16_384));
```

Đây là một **giới hạn độ dài value theo số ký tự Java**, không phải giới hạn byte của HTTP wire. Nó có thể ảnh hưởng authorization tokens, cookies và headers nghiệp vụ lớn. Trong phần lớn hệ thống, giới hạn byte **header size/count** nên được xử lý tại gateway/HTTP server, với budget và error handling phù hợp.

Đừng dùng đoạn này mặc định nếu không có requirement và regression tests. Quan trọng hơn, kiểm tra `ALLOWED_HEADER_VALUES` tồn tại ở version tương ứng trước khi dùng.

### 10.3. Quy tắc riêng cho `X-Client-Mode` nên đặt ở tầng ứng dụng

```java
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class ModeController {

    private static final Set<String> ALLOWED =
        Set.of("summary", "full");

    @GetMapping("/api/view")
    String view(
            @RequestHeader(name = "X-Client-Mode", required = false)
            String mode) {

        String selected = (mode == null) ? "summary" : mode;

        if (!ALLOWED.contains(selected)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid X-Client-Mode");
        }

        return selected;
    }
}
```

Ví dụ này hợp lý hơn việc đặt `summary/full` làm allowed values **cho mọi header**. Nó vẫn cần authentication/authorization và validation đầu vào phù hợp với route. Nếu controller chấp nhận duplicate `X-Client-Mode` values, phải xác định cách xử lý chúng; không mặc định chỉ lấy giá trị đầu tiên là an toàn.

### 10.4. Header value có thể có nhiều ngữ pháp

`Accept` dùng media ranges, `If-Match` dùng entity tags, `Authorization` dùng authentication schemes, `Cookie` dùng cookie grammar. Không một predicate chung nào có thể thay tất cả parser này. Firewall chỉ kiểm tra **tính chấp nhận được về ký tự ở cấp chung**.

## 11. Một bộ cấu hình hoàn chỉnh giữ default firewall

Trong một ứng dụng Spring Security Servlet, nhiều khi không cần custom firewall. Nếu muốn siết header names bằng ASCII token theo yêu cầu của hạ tầng, có thể dùng `WebSecurityCustomizer` như mục 9 và để các kiểm tra URL/method/host còn lại giữ mặc định.

Ví dụ security chain riêng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HeaderDemoSecurityConfig {

    @Bean
    SecurityFilterChain headerDemoChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF, CORS hoặc default security headers
        // chỉ để một header bất thường được chấp nhận.
        return http.build();
    }
}
```

Trong ứng dụng production, cần xem cấu hình CORS, session, authentication mechanisms, CSRF protection và response headers theo service threat model. Các ví dụ có mục đích học thuật, không tự thay thế chuỗi bảo mật hiện có.

### 11.1. Tại sao không thêm một filter bên trong chain rồi gọi là HttpFirewall?

`HttpSecurity.addFilterBefore(...)` thêm một security filter vào **chain đã được chọn**. `HttpFirewall` được `FilterChainProxy` dùng **trước khi chọn chain**. Vì vậy custom filter đặt trong chain không thay thế điểm kiểm tra request ở firewall.

Nếu ứng dụng muốn validate một **header nghiệp vụ cụ thể** trước khi handler xử lý, một filter/controller validator có thể phù hợp; nhưng phải hiểu rằng vị trí và phạm vi của nó **khác** `StrictHttpFirewall`.

### 11.2. Đừng nới Unicode/control characters chỉ để một client cũ không lỗi

Nếu client gửi header value chứa NUL hoặc CR/LF, giải pháp thường là **sửa client encoding/protocol** thay vì viết predicate chấp nhận mọi ký tự. Nếu một field cần truyền dữ liệu nhiều dòng, dùng request body có content type và schema phù hợp, không nhét raw newlines vào header.

## 12. JUnit unit test: bắt đầu với request và header hợp lệ

Unit test gọi `StrictHttpFirewall` trực tiếp cho phép cô lập behavior của firewall khỏi Servlet container. Các ví dụ sau dùng Spring Security Servlet 6.x+, Spring Test và JUnit 5.

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.FirewalledRequest;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HeaderFirewallUnitTest {

    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    private MockHttpServletRequest request() {
        var request = new MockHttpServletRequest("GET", "/api/view");
        request.setServletPath("/api/view");
        return request;
    }

    @Test
    void acceptsSimpleHeaderNameAndValue() {
        var request = request();
        request.addHeader("X-Request-Id", "req-42");

        FirewalledRequest safe =
            firewall.getFirewalledRequest(request);

        assertEquals("req-42", safe.getHeader("X-Request-Id"));
        safe.reset();
    }
}
```

Dùng constructor với method `GET` rõ ràng vì mock method rỗng có thể bị firewall từ chối trước khi bạn kiểm tra header. Test này chứng minh một header bình thường được đọc an toàn **trong request object do test tạo**, không chứng minh HTTP server đã parse một wire request như vậy.

### 12.1. Test giá trị chứa CR/LF phải đọc header

```java
import org.springframework.security.web.firewall.RequestRejectedException;

import static org.junit.jupiter.api.Assertions.assertThrows;

// Thêm vào class HeaderFirewallUnitTest:
@Test
void rejectsHeaderValueWithCrLfWhenRead() {
    var request = request();
    request.addHeader("X-Request-Id",
        "req-42\r\nX-Injected: yes");

    FirewalledRequest safe =
        firewall.getFirewalledRequest(request);

    assertThrows(RequestRejectedException.class,
        () -> safe.getHeader("X-Request-Id"));

    safe.reset();
}
```

**Điểm chính:** lời gọi `getFirewalledRequest(...)` có thể **không ném lỗi ngay**. `RequestRejectedException` được kiểm tra trong test ở **thao tác `safe.getHeader(...)`**. Đây là test có chủ đích về tính *lazy* của header predicates.

### 12.2. Test một tên header không hợp lệ bằng Enumeration

```java
@Test
void rejectsHeaderNameWithControlCharacterWhenEnumerated() {
    var request = request();
    request.addHeader("X-Bad\nName", "value");

    FirewalledRequest safe =
        firewall.getFirewalledRequest(request);

    var names = safe.getHeaderNames();

    assertThrows(RequestRejectedException.class, () -> {
        while (names.hasMoreElements()) {
            names.nextElement(); // Kiểm tra tên được thực hiện khi đọc phần tử.
        }
    });

    safe.reset();
}
```

Spring `MockHttpServletRequest` có thể cho phép tạo header name không hợp lệ để kiểm thử; một HTTP container thật nhiều khả năng đã từ chối từ parser. Bài test này không nên được dùng để khẳng định raw wire header `X-Bad\nName` có thể đến controller.

### 12.3. Test nhiều giá trị, trong đó một giá trị không hợp lệ

```java
@Test
void validatesEachHeaderValueWhenIterating() {
    var request = request();
    request.addHeader("X-Request-Id", "first");
    request.addHeader("X-Request-Id", "second\r\nBad: value");

    FirewalledRequest safe =
        firewall.getFirewalledRequest(request);

    var values = safe.getHeaders("X-Request-Id");

    assertEquals("first", values.nextElement());

    assertThrows(RequestRejectedException.class,
        values::nextElement);

    safe.reset();
}
```

Phép thử minh họa rằng **kiểm tra một giá trị không đồng nghĩa kiểm tra tất cả giá trị cùng tên**, vì enumeration kiểm tra khi trả từng phần tử. Nếu client/backend có chính sách hạn chế duplicate headers, đặt quy tắc ấy ở lớp parser hoặc validation field-specific phù hợp.

### 12.4. Test khi đọc tên có CR/LF trực tiếp

```java
@Test
void rejectsInvalidHeaderNameWhenRequested() {
    var request = request();
    request.addHeader("X-Request-Id", "req-42");

    FirewalledRequest safe =
        firewall.getFirewalledRequest(request);

    assertThrows(RequestRejectedException.class,
        () -> safe.getHeader("X-Invalid\r\nName"));

    safe.reset();
}
```

Test này kiểm tra **tên truyền vào API đọc** chứ không phải header name nhận trên wire. Hai việc khác nhau nhưng cùng cho thấy wrapper có thể kiểm tra header-name predicate theo thao tác truy cập.

### 12.5. Test null/unassigned code point cần thận trọng

Có thể thử một Java `String` chứa ký tự chưa được gán Unicode hoặc control char như `\u0000`. Nhưng ký tự đó có tới được Java từ HTTP parser hay không còn phụ thuộc encoding/server. Unit test nên tập trung kiểm tra predicate thực của version và đừng khẳng định một URI malformed trên production sẽ có cùng result.

Trong nhiều trường hợp, CR/LF là case minh họa dễ hiểu và thể hiện đúng nhu cầu an toàn hơn việc cố tạo một bộ payload kỳ lạ không có liên quan tới ứng dụng.

## 13. Test predicate tùy chỉnh mà không vô hiệu hóa default

Khi tổ chức thực sự cần ràng buộc tên field chỉ gồm ASCII token, hãy test cả header hợp lệ và những tên không phù hợp.

```java
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.security.web.firewall.RequestRejectedException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HeaderNamePolicyTest {

    private static final Pattern TOKEN =
        Pattern.compile("[!#$%&'*+.^_`|~0-9A-Za-z-]+");

    private StrictHttpFirewall firewall() {
        var firewall = new StrictHttpFirewall();
        firewall.setAllowedHeaderNames(
            StrictHttpFirewall.ALLOWED_HEADER_NAMES.and(
                name -> TOKEN.matcher(name).matches()));
        return firewall;
    }

    @Test
    void commonAsciiHeaderNameIsAccepted() {
        var request = new MockHttpServletRequest("GET", "/health");
        request.setServletPath("/health");
        request.addHeader("X-Request-Id", "42");

        var safe = firewall().getFirewalledRequest(request);
        assertEquals("42", safe.getHeader("X-Request-Id"));
        safe.reset();
    }

    @Test
    void spaceInFieldNameIsRejectedWhenAccessed() {
        var request = new MockHttpServletRequest("GET", "/health");
        request.setServletPath("/health");
        request.addHeader("X Request Id", "42");

        var safe = firewall().getFirewalledRequest(request);
        assertThrows(RequestRejectedException.class,
            () -> safe.getHeader("X Request Id"));
        safe.reset();
    }
}
```

Lưu ý: `X Request Id` vốn đã sai HTTP field-name grammar; kết quả trong test dựa trên mock cho phép tạo field để thử firewall. Trên HTTP server thật, request có thể bị từ chối sớm hơn.

### 13.1. Test với tên header có underscore

`X_Request_Id` sử dụng underscore, vẫn thuộc `tchar` theo RFC. Nếu tổ chức cố cấm underscore do quy tắc ingress cụ thể, cần định nghĩa chính sách thống nhất ở cả edge và backend; không vô tình nới hoặc siết khác nhau giữa hai tầng.

### 13.2. Test giữ nguyên default header-value predicate

Nếu viết predicate giá trị riêng cho mọi header, regression tests cần chứng minh:

- `Accept: application/json, text/plain;q=0.9` hoạt động.
- `Content-Type: application/json; charset=utf-8` hoạt động.
- `Authorization: Bearer ...` được truyền đến authentication filter đúng.
- `Cookie` với nhiều cặp giá trị hợp lệ vẫn được parser/session xử lý.
- CR/LF và control chars không bị cho qua.
- CORS preflight `Origin`/`Access-Control-Request-Headers` hoạt động theo policy.

Đừng viết test chỉ cho custom `X-Client-Mode` rồi đánh dấu chính sách global `setAllowedHeaderValues` là an toàn.

## 14. MockMvc: kiểm tra header mà controller thực sự đọc

Một ứng dụng MVC mẫu đọc custom header `X-Request-Id` và trả một giá trị đơn giản:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class HeaderProbeController {

    @GetMapping("/demo/header")
    String readHeader(HttpServletRequest request) {
        String value = request.getHeader("X-Request-Id");
        return (value == null) ? "missing" : "received";
    }
}
```

Controller **cố ý đọc** header qua `HttpServletRequest` để kích hoạt code path liên quan. Nó không phản chiếu raw value về client, tránh tạo một ví dụ phản xạ dữ liệu không cần thiết.

Ví dụ security chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HeaderProbeSecurityConfig {

    @Bean
    SecurityFilterChain probeChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/demo/header").permitAll()
            .anyRequest().authenticated());
        return http.build();
    }
}
```

Ví dụ này minh họa cách test header, không phải production configuration hoàn chỉnh.

### 14.1. Integration test cho header hợp lệ

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HeaderProbeIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void readsOrdinaryHeaderWithSecurityFilters() throws Exception {
        mvc.perform(get("/demo/header")
                .header("X-Request-Id", "req-42"))
            .andExpect(status().isOk())
            .andExpect(content().string("received"))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void missingOptionalHeaderDoesNotBreakRoute() throws Exception {
        mvc.perform(get("/demo/header"))
            .andExpect(status().isOk())
            .andExpect(content().string("missing"));
    }
}
```

Test giả định ứng dụng nạp `HeaderProbeController` và Spring Security filters vào MockMvc. Nếu có thêm security configurations/filters ở dự án thật, cần điều chỉnh test context tương ứng. Với Spring Boot version mới hơn, package `@AutoConfigureMockMvc` có thể được tổ chức khác; đối chiếu dependency.

### 14.2. Test header CR/LF trong MockMvc không nên hardcode 400

Khi MockMvc nhận một header value chứa CR/LF do test dựng, `StrictHttpFirewall` có thể ném `RequestRejectedException` lúc controller đọc value. Nhưng:

- Có setup chuyển exception thành HTTP status như `400`.
- Có setup ném exception ra test harness.
- Có setup khác không vào đúng code path vì header bị filter hoặc test builder xử lý khác.

Vì vậy, nếu mục tiêu là **contract của firewall**, hãy dùng JUnit unit test ở mục 12 với `assertThrows`. Nếu mục tiêu là **response cuối cùng**, integration test phải xác định `RequestRejectedHandler` và Servlet container thực tế trước khi assert status.

### 14.3. Header không được controller đọc thì sao?

Nếu controller không bao giờ đọc `X-Request-Id` và không filter/matcher nào duyệt header ấy, `StrictHttpFirewall` có thể không kiểm tra giá trị đó qua getter. Đây không phải bằng chứng mọi header xấu đều được cho phép trên wire; HTTP parser có thể đã áp rule. Nhưng nó cho thấy **không nên dùng tính lazy của firewall làm chiến lược business validation cho mọi header**.

Nếu tổ chức cần một policy quét toàn bộ headers của request trước business logic, phải thiết kế và kiểm thử cơ chế riêng phù hợp, bảo đảm không đánh đổi hiệu năng hoặc vô tình log/khởi tạo dữ liệu nhạy cảm.

## 15. Có nên chủ động duyệt toàn bộ headers trong một filter?

Đôi khi nhóm phát triển muốn dùng một Servlet filter để duyệt toàn bộ header names/values nhằm kích hoạt kiểm tra ngay lúc đầu. Về mặt ý tưởng:

```java
// PSEUDOCODE, không phải filter production hoàn chỉnh.
Enumeration<String> names = request.getHeaderNames();

while (names.hasMoreElements()) {
    String name = names.nextElement();
    Enumeration<String> values = request.getHeaders(name);

    while (values.hasMoreElements()) {
        values.nextElement();
    }
}
```

Nếu chạy trên `FirewalledRequest`, các getter/Enumeration có thể kích hoạt predicate. Tuy nhiên cần cân nhắc:

1. **Vị trí filter:** nếu đặt trong một security chain, nó chỉ chạy trên chain được chọn và sau matching.
2. **Parser đã làm gì:** một header malformed có thể không bao giờ vào Servlet request.
3. **Không làm việc thừa:** duyệt tất cả headers mỗi request có chi phí nhất định, đặc biệt với headers lớn.
4. **Không log giá trị:** việc kiểm tra không có nghĩa nên ghi toàn bộ cookies/tokens vào logs.
5. **Không tạo policy mâu thuẫn:** các predicates mặc định, parser limits và field-specific validators có trách nhiệm khác nhau.
6. **Không thay routing/authorization:** dù tất cả headers có ký tự hợp lệ, Host/Origin/Authorization vẫn cần chính sách riêng.
7. **Kiểm soát lỗi:** nếu `RequestRejectedException` xuất hiện sau khi response đã commit, khả năng trả lỗi sạch có thể khác.

Trong đa số ứng dụng, **giữ HTTP parser/Servlet container an toàn, firewall mặc định và field-specific validation** dễ bảo trì hơn việc bắt buộc quét mọi header chỉ để có một điểm kiểm tra chung.

## 16. Giới hạn độ dài, số lượng và tổng bytes của HTTP headers

Ký tự hợp lệ không có nghĩa request có thể chứa bao nhiêu header cũng được. Header block quá lớn có thể tiêu tốn CPU/bộ nhớ, gây lỗi proxy/upstream hoặc bị server từ chối.

Những giới hạn thường cần xét:

- Tổng số bytes của request headers.
- Độ dài mỗi header field name/value.
- Tổng số header fields.
- Request-line size, URI size và HTTP/2 header-list size.
- Số lượng/độ dài cookies và bearer tokens.
- Timeout/stream limits ở gateway và backend.

`setAllowedHeaderValues` là `Predicate<String>` **không phải API chính để cấu hình byte limits trên đường truyền**. Nó nhận Java String sau parsing; `value.length()` đếm UTF-16 code units chứ không phải số bytes được HTTP server nhận.

### 16.1. Đặt giới hạn ở đúng tầng

| Mục tiêu | Tầng thường phù hợp |
| --- | --- |
| Giới hạn total header bytes và parser buffers | HTTP server / Servlet connector / reverse proxy. |
| Kiểm soát header count | HTTP parser / ingress policy. |
| Giới hạn giá trị của một custom application header | Field-specific validator, controller/filter nghiệp vụ. |
| Kiểm tra header name/value characters khi ứng dụng đọc | `StrictHttpFirewall` predicates. |
| Giới hạn bearer token/JWT theo authentication format | Authentication stack và gateway/server budgets. |
| Kiểm soát Host/forwarded host | Trusted ingress, server config, host allowlist. |
| Chặn log injection từ header values | Structured logging + escaping + minimization. |

Đừng đặt ngưỡng `value.length() <= 100` cho toàn bộ HTTP headers chỉ vì correlation ID của bạn tối đa 100 ký tự: điều đó có thể vô tình chặn `Authorization` hoặc `Cookie` hợp lệ.

## 17. Header ambiguities: duplicate, whitespace và framing

### 17.1. Duplicate headers

Một HTTP request có thể chứa nhiều field lines cùng tên. HTTP semantics quy định việc hợp nhất/lặp khác nhau tùy header. Đừng tự ghép mọi field bằng dấu phẩy, đặc biệt với những trường đặc biệt liên quan request framing và authentication.

Nếu security logic dùng `getHeader("X-Role")` (giá trị đầu tiên) nhưng gateway hoặc application logic khác dùng giá trị cuối, một inconsistency có thể phát sinh.

**Nguyên tắc:** không lấy role, tenant hay quyền truy cập trực tiếp từ custom header do client tự gửi. Với headers do ingress thêm, cần trusted proxy policy và chặn client tự giả mạo.

### 17.2. Leading/trailing whitespace và tab

HTTP field parsing có quy tắc `OWS`. Một số parser trim leading/trailing whitespace trước khi Servlet trả String; một số wrapper có thể giữ representation khác. Khi validate dữ liệu bảo mật, **đừng tự sử dụng `trim()` để “sửa” mọi header rồi tin rằng hai tầng thống nhất**.

Ví dụ `Authorization` có syntax riêng; token/certificate/signature cần parser chuẩn. Một predicate “không có ký tự điều khiển” vẫn không xác thực dấu cách, prefix, token format hoặc chữ ký.

### 17.3. HTTP request smuggling không thể được giải quyết chỉ bằng header predicates

Những header như `Content-Length` và `Transfer-Encoding` liên quan cách HTTP/1.x xác định **ranh giới request body**. Nếu proxy và backend HTTP parser không thống nhất về framing, request smuggling có thể xảy ra **trước khi Spring Security có một `HttpServletRequest`**.

Vì vậy:

- Luôn cập nhật HTTP server/proxy khi có security fixes.
- Tránh cấu hình proxy forwarding không tương thích.
- Kiểm soát parser/header-size limits.
- Không tự parse raw `Content-Length` hoặc `Transfer-Encoding` trong controller để thay parser.
- Không cho rằng `setAllowedHeaderValues` là giải pháp chống mọi request smuggling.

`StrictHttpFirewall` là một lớp phòng vệ **sau parser**, không phải một parser/HTTP gateway thay thế.

## 18. CORS, CSRF, CSP, HSTS và session khi header gặp lỗi

### 18.1. CORS preflight sử dụng nhiều request headers

Một browser có thể gửi:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://ui.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Ký tự của headers trên có thể hợp lệ với firewall, nhưng CORS policy vẫn phải quyết định origin/method/headers/credentials. Một predicate custom quá hẹp có thể làm preflight bị `RequestRejectedException`; một CORS configuration sai có thể trả lỗi dù firewall chấp nhận request.

Đừng thêm `Access-Control-Allow-Origin: *` như cách chữa một header-value rejection. `Access-Control-Allow-Origin` là **response header**, khác với `Origin` bên request.

### 18.2. CSRF với cookie-session POST

Một POST dùng cookie session có thể bị `CsrfFilter` từ chối nếu không có token, dù `Content-Type` và `Cookie` chứa ký tự hợp lệ. Đây là hành vi thuộc **CSRF**, không phải lỗi `StrictHttpFirewall` header characters.

Trong test, dùng `csrf()` từ `spring-security-test` để kiểm tra request có token hợp lệ và không có token theo đúng policy. Đừng tắt CSRF để cho header lạ đi qua.

### 18.3. Authentication/Authorization

Một bearer token có thể chứa ký tự hợp lệ nhưng chữ ký sai, hết hạn hoặc không có scope phù hợp. Firewall cho qua predicate chỉ chứng minh **chuỗi không vi phạm rule ký tự**; `BearerTokenAuthenticationFilter`, authentication provider và authorization sẽ quyết định tiếp.

Một header `X-User-Role: ADMIN` do client gửi vẫn chỉ là input không đáng tin. Đừng dùng nó để nâng quyền nếu không có cơ chế trust/proxy được bảo vệ.

### 18.4. Response security headers và HSTS

CSP điều khiển một số hành vi browser liên quan nguồn tài nguyên, HSTS nói browser ưu tiên HTTPS trên hostname phù hợp, `nosniff` hạn chế MIME sniffing. Không header nào trong số đó kiểm soát tính hợp lệ của request-header name/value trước Java.

Nếu một request bị gateway/HTTP parser từ chối, backend header writers có thể không chạy. Muốn baseline headers trên mọi response public phải thiết kế ở tầng có thể phát response lỗi, tránh duplication/conflict giữa proxy và backend.

## 19. Quan sát HTTP thực ở staging

### 19.1. Gửi request hợp lệ bằng curl

```bash
# Chỉ dùng trên môi trường do bạn sở hữu hoặc có quyền kiểm thử.
curl -sS -D - -o /dev/null \
  'https://staging.example.test/demo/header' \
  -H 'X-Request-Id: req-42'

# Kiểm tra Origin/CORS theo một case được phép.
curl -sS -D - -o /dev/null -X OPTIONS \
  'https://staging.example.test/api/orders' \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Trên Windows PowerShell, dùng `curl.exe` và `-o NUL` thay `/dev/null`. `curl -I` gửi HEAD chứ không phải GET; không thay kết quả GET bằng HEAD nếu ứng dụng có policy theo method.

### 19.2. Không cố gửi CRLF malformed qua client thường để chứng minh firewall

Nhiều HTTP clients từ chối CRLF trong header values ngay khi xây request; gateway hoặc container cũng có thể từ chối. **Không cần tìm cách vượt client validation** để làm một unit test header value ở Spring Security.

Đối với kiểm thử firewall, dùng `MockHttpServletRequest` trong môi trường test; đối với HTTP parser/proxy, dùng các bài kiểm thử được phê duyệt từ bộ test của hạ tầng, không gửi payload malformed ngẫu nhiên vào production.

### 19.3. Dùng response và logs để xác định tầng từ chối

| Triệu chứng | Giả thuyết | Cần xác minh |
| --- | --- | --- |
| Public `400`, backend không có log | Gateway/HTTP parser từ chối sớm | Logs và request ID ở ingress/container. |
| `RequestRejectedException` khi đọc header | Firewall predicate từ chối value/name | Getter nào chạy, config nào được dùng. |
| Controller không được gọi, không có rejection log | CORS/auth/route hoặc parser từ chối | Filter chain, gateway và status. |
| Mock unit test rejection nhưng HTTP thực `400` khác body | Test bypass parser; lỗi public từ tầng khác | Tách test contract và on-wire result. |
| Browser CORS error | Origin/method/headers/credentials hoặc preflight path | Kiểm tra OPTIONS và response CORS. |
| `401` với `Authorization` hợp lệ về ký tự | Token sai/hết hạn hoặc scheme không được hỗ trợ | Authentication mechanism. |
| `403` với POST | CSRF hoặc thiếu quyền | Token, role và resource policy. |
| `431 Request Header Fields Too Large` | Header size/count budget tại server/edge | Cấu hình parser/limits; không tự nới predicate. |
| `502`/`503` | Proxy/upstream lỗi | Backend có nhận request không? |
| HSTS/CSP thiếu chỉ trên lỗi edge | Response không đi qua Spring Security header writer | Thiết kế response policy ở tầng phát lỗi. |

`431` là status phù hợp khi server đánh giá request header fields quá lớn, nhưng server/proxy có thể chọn status hoặc behavior khác tùy implementation. Đừng suy mọi lỗi kích thước header đều trả đúng `431`.

### 19.4. Logging an toàn cho rejected headers

Khi xử lý security rejection, chỉ ghi đủ thông tin để chẩn đoán: request ID, route đã chuẩn hóa ở mức phù hợp, loại lỗi, method và tầng xử lý. Nếu cần ghi tên field, escape control characters và giới hạn độ dài; không ghi raw:

- `Authorization` credentials/tokens.
- `Cookie` và session identifiers.
- CSRF tokens.
- Giá trị `X-Api-Key` hoặc secrets.
- Header values chứa thông tin cá nhân.
- Raw CRLF/control characters có thể làm log injection.

Đừng dùng dòng code kiểu `request.getHeaderNames()` rồi ghi mọi value vào log chỉ để biết firewall từ chối field nào.

## 20. Ma trận regression khi tùy chỉnh header predicates

| Trường hợp | Firewall/default predicate | Kiểm tra tiếp |
| --- | --- | --- |
| `X-Request-Id: req-42` | Chấp nhận ký tự | Route/correlation ID đúng format. |
| `content-type: application/json` | Tên hợp lệ, value hợp lệ | Content-Type parser và handler. |
| `Accept: application/json, text/plain;q=0.9` | Có dấu phẩy/semicolon hợp lệ trong value | Không đặt global ASCII alphanumeric-only value rule. |
| `Authorization: Bearer ...` | Có thể qua kiểm tra ký tự | Authentication token signature/expiry. |
| `Cookie: sid=abc; theme=dark` | Có semicolon trong **value**, khác semicolon trong URL path | Session/cookie parser và CSRF. |
| `Origin: https://ui.example.test` | Chấp nhận ký tự | CORS origin allowlist. |
| `Origin: https://evil.example` | Vẫn có ký tự hợp lệ | CORS policy phải quyết định từ chối. |
| `X-Request-Id` với CR/LF trong value mock | Từ chối khi đọc qua wrapper | Xác nhận `RequestRejectedException` trong unit test. |
| Tên header có LF trong mock | Từ chối khi truy cập tên | HTTP parser có thể từ chối sớm trên wire. |
| Header name chứa dấu cách | Sai RFC token; custom strict token regex từ chối | HTTP server có thể từ chối sớm. |
| Header name dùng underscore | Hợp lệ theo `tchar` | Proxy/config có thể xử lý khác. |
| Duplicate `X-Request-Id` values | Từng phần tử được kiểm tra khi duyệt `getHeaders` | Quy định duplicate policy của ứng dụng. |
| Header value có Unicode được gán | Có thể phù hợp default predicate | On-wire encoding/parser + field grammar. |
| Header value chứa Unicode chưa gán | Thường bị default predicate từ chối khi đọc | Test theo version/Java Unicode tables. |
| Header rất dài | Có thể qua predicate ký tự | Server/proxy header-size budgets. |
| `Host: attacker.example` | Ký tự có thể hợp lệ | Trusted hostname/proxy policy. |
| `Forwarded: host=...` từ client chưa tin | Ký tự có thể hợp lệ | Không tin forwarded headers từ Internet. |
| CORS preflight `OPTIONS` | Header names/values có thể hợp lệ | Allowed origin/method/headers/credentials. |
| Response `400` thiếu security headers | Có thể lỗi trước header writers | Kiểm tra layer tạo response. |

### 20.1. Sau khi đổi proxy, servlet container hoặc Spring Security

Chạy lại test với thông tin chính xác:

- Spring Security `spring-security-web` version.
- Servlet container và HTTP connector version/config.
- Gateway/WAF/CDN header forwarding và size limits.
- HTTP/1.1/2/3 path mà client thực sử dụng.
- Allowed header name/value predicates và bean/customizer thực sự được nạp.
- Các endpoints có đọc hay duyệt headers không.
- CORS/auth/CSRF/authorization behavior.
- Error handling, response headers và logging.

Một thay đổi HTTP server có thể chặn header **trước** khi unit test trong Spring Security từng thấy; đó là lý do cần kiểm thử nhiều lớp.

## 21. Reactive/WebFlux: API tương ứng, request model khác

Dịch vụ **SPRING_SECURITY_HTTP_PROTECTION** bao gồm Servlet lẫn Reactive. Bài này tập trung vào `StrictHttpFirewall` của Servlet; với WebFlux, **không áp nguyên bean Servlet này vào Reactive HTTP server**.

| Chủ đề | Servlet | Reactive/WebFlux |
| --- | --- | --- |
| Request | `HttpServletRequest` | `ServerWebExchange` / `ServerHttpRequest` |
| Security chain manager | `FilterChainProxy` | `WebFilterChainProxy` |
| Firewall API | `HttpFirewall` | `ServerWebExchangeFirewall` |
| Strict implementation | `StrictHttpFirewall` | `StrictServerWebExchangeFirewall` |
| Allowed header-name predicate | `setAllowedHeaderNames(Predicate<String>)` | API tương ứng theo Reactive firewall/version |
| Allowed header-value predicate | `setAllowedHeaderValues(Predicate<String>)` | API tương ứng theo Reactive firewall/version |
| Security matcher | `RequestMatcher` | `ServerWebExchangeMatcher` |
| Header writer | `HeaderWriter` / `HeaderWriterFilter` | `ServerHttpHeadersWriter` / `HttpHeaderWriterWebFilter` |
| Test | `MockHttpServletRequest`, MockMvc, Servlet server | `MockServerWebExchange`, WebTestClient, Reactive HTTP server |

Các phiên bản hiện đại của `StrictServerWebExchangeFirewall` có những setter tên tương tự về header names/values. Nhưng **thứ tự xử lý và API Reactive không được suy từ Servlet wrapper behavior một cách máy móc**. Cần đối chiếu implementation/version và kiểm thử Reactor Netty/Reactive server thật khi vấn đề nằm ở HTTP protocol parsing.

### 21.1. Ví dụ Reactive chỉ mang tính khái niệm

```java
import org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall;

StrictServerWebExchangeFirewall firewall =
    new StrictServerWebExchangeFirewall();

// Thường không cần chỉnh: giữ default constraints.
// Nếu phải custom, đối chiếu Javadoc Reactive đúng version.
```

Không chèn đoạn này vào một Servlet SecurityFilterChain hoặc cho rằng nó tự được dùng chỉ vì có biến Java. Việc đăng ký firewall Reactive cần tuân theo cơ chế cấu hình WebFlux/Spring Security Reactive của dự án.

### 21.2. Test WebTestClient không thay HTTP parser

WebTestClient với mock exchange không mô phỏng mọi ràng buộc HTTP/2 frame, gateway normalization hay kích thước header block. Nếu test hạ tầng HTTP parser/ingress, cần có môi trường Reactive HTTP server thật cùng proxy mục tiêu.

## 22. Bài tập tình huống có đáp án định hướng

### Bài A — CRLF trong header value

Một unit test dùng `MockHttpServletRequest` với `X-Request-Id: "abc\r\nInjected: yes"`. `getFirewalledRequest` trả về wrapper bình thường nhưng `safe.getHeader("X-Request-Id")` ném exception.

**Định hướng:** header-value validation có thể chạy *lazy* khi đọc. Test phải gọi getter phù hợp. Không kết luận firewall hỏng vì bước tạo wrapper chưa ném exception.

### Bài B — Header không bao giờ được đọc

Một request mock có field value bất thường nhưng controller không đọc field ấy, và test chỉ assert status `200`.

**Định hướng:** không thể kết luận predicate đã kiểm tra field đó. HTTP parser có thể lọc ở wire; nếu cần chứng minh firewall predicate, viết unit test trực tiếp với getter/enumeration.

### Bài C — Cấm dấu semicolon trên mọi header value

Nhóm security viết predicate value chỉ cho chữ, số và dấu gạch ngang. Browser gửi `Cookie: sid=123; theme=dark` và frontend liên tục lỗi.

**Định hướng:** semicolon là bình thường trong Cookie/Content-Type/Accept values; khác semicolon trong URI path. Dùng default predicate và parser/validation theo từng header.

### Bài D — Case-sensitive tên header

Một rule custom chỉ cho `X-Client-Mode` chính xác cách viết này; HTTP/2 browser gửi `x-client-mode`.

**Định hướng:** field names là case-insensitive; không xây policy trái HTTP semantics. Dùng regex token chung hoặc `equalsIgnoreCase` khi cần nhận diện header cụ thể.

### Bài E — Host có ký tự hợp lệ nhưng không được tin

Request gửi `Host: attacker.example`; predicate value cho qua và ứng dụng xây password-reset URL theo Host.

**Định hướng:** character validity không đồng nghĩa trusted host. Cấu hình host/forwarded trust tại ingress, có thể thêm `setAllowedHostnames`, không dựng security links từ Host chưa validate.

### Bài F — CORS Origin bị từ chối

`Origin: https://evil.example` vượt firewall nhưng browser không đọc được response do CORS.

**Định hướng:** đây là CORS policy, không phải firewall-value predicate. Không nới CORS chỉ vì header có cú pháp hợp lệ.

### Bài G — Hai X-Request-Id values

Một request mock có hai giá trị cùng tên; giá trị đầu hợp lệ, giá trị thứ hai chứa CRLF. `getHeader` chỉ trả một giá trị.

**Định hướng:** dùng `getHeaders` và duyệt enumeration để kiểm tra từng value trong test; định nghĩa duplicate handling ở tầng ứng dụng nếu cần.

### Bài H — Header quá lớn

Client nhận `431` do header block vượt giới hạn gateway; test `StrictHttpFirewall` với cùng một Java String lại pass predicate.

**Định hướng:** ký tự hợp lệ khác byte/size budget. Giới hạn headers ở HTTP server/edge; đừng cố ép mọi size policy bằng `Predicate<String>`.

### Bài I — Authorization token hợp lệ về ký tự nhưng sai chữ ký

`Authorization: Bearer ...` qua firewall, API trả `401`.

**Định hướng:** authentication provider/filter chịu trách nhiệm token signature, expiry và scheme; firewall không thay xác thực.

### Bài J — Cookie session POST bị 403

HTTP headers có ký tự hợp lệ, request POST vẫn `403`.

**Định hướng:** kiểm tra CSRF token, session và authorization. Đừng thay `setAllowedHeaderValues` để sửa CSRF.

### Bài K — Tắt firewall-value check cho legacy client

Một client gửi ký tự NUL trong custom header; nhóm định dùng `value -> true`.

**Định hướng:** sửa client/protocol hoặc chuyển dữ liệu sang body có định dạng; không vô hiệu hóa phòng vệ chung chỉ vì một client lỗi.

### Bài L — HTTP/2 pseudoheaders

Một developer muốn cho `:authority` vào `setAllowedHeaderNames`.

**Định hướng:** pseudoheaders được HTTP/2 parser xử lý ở protocol layer, không phải request header field name thông thường cho application. Kiểm tra server request abstraction và Host/authority trust boundary.

### Bài M — Proxy thêm X-Forwarded-Proto

Gateway gửi `X-Forwarded-Proto: https`; giá trị qua predicate và backend lập tức tin request là HTTPS dù client có thể tự gửi header tương tự.

**Định hướng:** gateway phải strip/overwrite forwarded headers do client cung cấp; chỉ bật forwarded handling cho trusted proxies. Character predicate không xác định nguồn gốc header.

### Bài N — Tên header chứa space trong MockMvc

Test mock tạo `X Request Id`; firewall có thể từ chối khi gọi `getHeader`, còn production trả `400` trước Java.

**Định hướng:** cả hai hành vi có thể đúng ở những tầng khác nhau. Unit test kiểm chứng predicate; HTTP parser test xác minh wire behavior.

## 23. Checklist production

1. **Phân biệt tên và giá trị header**: name có HTTP `token` grammar, value có syntax theo field.
2. **Giữ `StrictHttpFirewall` mặc định** trừ khi có yêu cầu được phê duyệt.
3. **Hiểu các header checks có thể lazy trên `FirewalledRequest`**; test getter/enumeration thực sự.
4. **Không xem `getFirewalledRequest(...)` trả wrapper là bằng chứng mọi header đã được duyệt**.
5. **Không thay header predicates bằng `name -> true` hoặc `value -> true` để né lỗi client**.
6. **Nếu siết, ưu tiên compose với default predicates** và xác minh API/version tương ứng.
7. **Không dùng global `setAllowedHeaderValues` để validate một custom header cụ thể**.
8. **Không phân biệt hoa/thường với field names**, nhất là khi có HTTP/2.
9. **Không cấm dấu cách, semicolon, comma bừa bãi trong mọi field values**.
10. **Giữ CR/LF, NUL và control-character handling chặt chẽ** tại parser/firewall, không phản chiếu raw data.
11. **Đặt byte size/header count limits ở gateway/HTTP server**, không coi Java `String.length` là tổng bytes on-wire.
12. **Không tin `Host`/`Forwarded` chỉ vì values có ký tự hợp lệ**; xác định trusted ingress.
13. **Không xem `Origin` hợp lệ là CORS allowed**, và không xem `Authorization` hợp lệ về ký tự là authenticated.
14. **Giữ CSRF/session rules** cho POST/PUT/PATCH/DELETE theo kiểu xác thực.
15. **Phân biệt request header validation với CSP/HSTS/response header writers**.
16. **Test unit + MockMvc + HTTP server/proxy** ở đúng những ranh giới cần chứng minh.
17. **Test duplicate headers**, các values khác nhau và cách ứng dụng đọc chúng.
18. **Ghi log bằng escaping và loại bỏ secrets**, không lưu raw Authorization/Cookie.
19. **Đừng kỳ vọng `StrictHttpFirewall` ngăn mọi request smuggling**, vì framing/parsing có thể xảy ra trước Java.
20. **Kiểm tra API đúng stack Servlet/Reactive** và version Spring Security.
21. **Khi đổi firewall hoặc HTTP parser, chạy regression** với CORS, authentication, CSRF, header size và protected routes.
22. **Ghi rõ policy owner, threat model, test evidence và rollback plan** cho mọi ngoại lệ.

### Tài liệu tham khảo

- [Spring Security Reference — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html)
- [Spring Security Javadoc — StrictHttpFirewall](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html)
- [Spring Security Javadoc — HttpFirewall](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/HttpFirewall.html)
- [Spring Security Javadoc — RequestRejectedException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/RequestRejectedException.html)
- [Spring Security Reference — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security Reference — Servlet CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security Javadoc — StrictServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/firewall/StrictServerWebExchangeFirewall.html)
- [Spring Security Reference — Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112)
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/)
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [OWASP — HTTP Response Splitting](https://owasp.org/www-community/attacks/HTTP_Response_Splitting)

