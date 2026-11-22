# invalid_request, invalid_token và insufficient_scope

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một HTTP request dùng Bearer Access Token có thể thất bại vì nhiều nguyên nhân rất khác nhau: client gửi credential sai cú pháp, token không còn đáng tin cậy, hoặc token hợp lệ nhưng không có quyền gọi endpoint. Ba mã lỗi chuẩn của **OAuth 2.0 Bearer Token Usage — RFC 6750** giúp diễn đạt các tình huống đó:

- **`invalid_request`**: cách client **gửi Bearer token trong request** không đúng quy tắc.
- **`invalid_token`**: Bearer credential được gửi lên nhưng **không thể được chấp nhận làm token hợp lệ**.
- **`insufficient_scope`**: token đã được xác thực nhưng **không có phạm vi quyền cần thiết** cho tài nguyên hoặc thao tác.

Phân biệt đúng ba tình huống rất quan trọng: client biết nên sửa request, lấy token mới hay yêu cầu thêm quyền; API trả đúng mã HTTP; đội vận hành không nhầm lỗi cấu hình JWT với thiếu scope; và hệ thống không vô tình biến một token sai thành người dùng đã đăng nhập.

Bài học này giải thích chi tiết **HTTP status, `WWW-Authenticate` challenge, các tham số `error`, `error_description`, `error_uri`, `realm`, `scope`**, luồng xử lý trong **Spring Security 6.x**, ví dụ với **JWT và opaque Access Token**, cách bảo vệ error response, và những bài kiểm thử quan trọng. Ví dụ sử dụng **Spring Boot 3.x, Java 17+ và Servlet Resource Server**. Những hostname và token đều chỉ mang tính minh họa.

## 1. Bối cảnh: ai trả lỗi và ở bước nào?

Giả sử một client gọi API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Resource Server phải đi qua nhiều quyết định:

~~~text
HTTP request
     |
     v
1. Trích xuất Bearer token từ request
     |-- header/scheme sai quy tắc?
     |     -> invalid_request
     v
2. Xác thực Bearer token
     |-- JWT: chữ ký, iss, aud, exp, nbf...
     |-- Opaque: introspection, active, metadata...
     |-- token không hợp lệ?
     |     -> invalid_token
     v
3. Tạo Authentication đã xác thực
     |-- principal, authorities (SCOPE_...)
     v
4. HTTP/method authorization
     |-- thiếu authority/scope?
     |     -> insufficient_scope hoặc access denied
     v
5. Domain authorization
     |-- sai tenant, owner, trạng thái tài khoản?
     |     -> 403/404 theo chính sách nghiệp vụ
     v
Controller / Service
~~~

**Một JWT có chữ ký đúng vẫn có thể bị từ chối do thiếu quyền.** Ngược lại, một JWT có claim `scope: "admin.manage"` nhưng chữ ký sai không được đi đến bước phân quyền. OAuth 2.0 lỗi Bearer phải được đặt đúng ở ranh giới **request parsing → authentication → authorization**.

| Tầng | Dữ liệu kiểm tra | Lỗi liên quan |
| --- | --- | --- |
| **Bearer token resolution** | Authorization header, cách chuyển token, số nguồn token. | `invalid_request` khi định dạng Bearer request không hợp lệ. |
| **Token authentication** | Chữ ký JWT, issuer, audience, thời hạn; hoặc introspection status. | `invalid_token`. |
| **Scope/authority authorization** | `SCOPE_orders.read`, `SCOPE_orders.write`, vai trò được cho phép. | `insufficient_scope` trong trường hợp thiếu phạm vi quyền. |
| **Business authorization** | Owner, tenant, record-level permission, local account status. | 403 hoặc 404 theo policy; không nhất thiết là `insufficient_scope`. |

## 2. Bảng phân biệt nhanh ba lỗi chuẩn

| OAuth Bearer error | Tình huống điển hình | HTTP status RFC 6750 gợi ý | Client nên làm gì? |
| --- | --- | --- | --- |
| **`invalid_request`** | Bearer request sai định dạng, gửi token theo nhiều cách, tham số không được chấp nhận. | **400 Bad Request** | Sửa cách tạo HTTP request. |
| **`invalid_token`** | Token hết hạn, revoked, không xác minh được, sai audience/issuer theo policy. | **401 Unauthorized** | Lấy credential hợp lệ mới hoặc thực hiện lại authorization flow phù hợp. |
| **`insufficient_scope`** | Token hợp lệ nhưng thiếu quyền của endpoint. | **403 Forbidden** | Xin phạm vi quyền được phép, dùng đúng client/account hoặc từ chối thao tác. |

RFC 6750 yêu cầu dùng **`WWW-Authenticate`** để trả challenge khi cần, đồng thời mô tả những status code phù hợp. Tuy nhiên **không phải mọi 400, 401 hoặc 403 trong một ứng dụng đều tương ứng một trong ba mã này**:

- JSON request body sai schema có thể là **400** của domain validation, không phải `invalid_request` thuộc Bearer protocol.
- Một API trả **401** khi không có Bearer token có thể chỉ trả challenge `Bearer`, **không có `error="invalid_token"`**.
- Một tài khoản bị khóa hoặc request truy cập bản ghi của người khác có thể nhận **403**, nhưng không nhất thiết do thiếu OAuth scope.
- Lỗi Authorization Server/JWKS/introspection endpoint không khả dụng là **vấn đề phụ thuộc xác thực**, không tự động đồng nghĩa token thật đã bị revoke.

## 3. WWW-Authenticate là nơi mô tả lỗi Bearer

Trong HTTP, `WWW-Authenticate` là response header để Resource Server thông báo **authentication scheme** và các tham số challenge. Với OAuth 2.0 Bearer Token, response có thể chứa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Các thành phần:

| Thành phần | Ví dụ | Chức năng |
| --- | --- | --- |
| **Scheme** | `Bearer` | Báo đây là Bearer challenge. |
| **`realm`** | `"orders-api"` | Mô tả vùng bảo vệ, hữu ích khi client tương tác với nhiều API. |
| **`error`** | `"invalid_token"` | Mã lỗi đã chuẩn hóa. |
| **`error_description`** | `"The access token expired"` | Mô tả ngắn, tùy chọn; cần tránh lộ dữ liệu nhạy cảm. |
| **`error_uri`** | `"https://docs.example.test/errors/invalid-token"` | Link tới tài liệu giải thích lỗi, tùy chọn. |
| **`scope`** | `"orders.write"` | Các scope cần thiết, có thể cung cấp khi thiếu quyền. |

Các tham số của challenge phải tuân thủ cú pháp HTTP và ràng buộc của RFC 6750. **Đừng tự nối các chuỗi do client kiểm soát** vào `WWW-Authenticate`: sẽ có rủi ro tạo header sai định dạng, header injection hoặc phản chiếu nội dung nhạy cảm.

### 3.1. Ví dụ đầy đủ cho từng mã

**Request gửi Bearer sai định dạng:**

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request", error_description="Malformed bearer token request"
~~~

**Token không còn được chấp nhận:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

**Token hợp lệ nhưng thiếu quyền:**

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Đây là **các response minh họa theo ngữ nghĩa RFC**, không phải cam kết rằng mọi trường hợp Spring Security đều tự đặt đủ `realm`, `scope` hay `error_description`. Nội dung header thực tế phụ thuộc exception, handler và cấu hình.

### 3.2. Vì sao response khi chưa gửi token thường không có error?

Giả sử client gọi endpoint yêu cầu Bearer token nhưng **không gửi credential**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

Phản hồi thích hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Theo RFC 6750, khi request **không có thông tin xác thực**, hoặc sử dụng cách xác thực mà Resource Server không hỗ trợ, server **không nên thêm thông tin lỗi OAuth Bearer**. Vì chưa có token để đánh giá, trả `invalid_token` sẽ gây hiểu nhầm.

Điều tương tự có thể xảy ra nếu request mang:

~~~http
Authorization: Basic SOME_OTHER_CREDENTIAL
~~~

trong khi endpoint chỉ hỗ trợ Bearer. Resource Server có thể trả 401 Bearer challenge mà không gắn `invalid_token` vào một credential thuộc scheme khác.

### 3.3. Có nhất thiết phải trả error_description?

Không. Các tham số `error_description`, `error_uri` và `scope` đều cần cân nhắc. Ví dụ, trả `"JWT signature verification failed using key kid-..." ` với chi tiết khóa và cấu hình có thể giúp attacker suy đoán hạ tầng; còn thông điệp `"Token is invalid"` thường đủ cho client.

`error_description` là thông tin phục vụ client, không phải log debug nội bộ. Đừng trả nguyên Authorization header, token, secret, stack trace, user ID, lý do quản trị khóa tài khoản hoặc đường dẫn hệ thống vào response.

## 4. invalid_request: lỗi cách gửi Bearer token

Mã **`invalid_request`** liên quan đến **request sử dụng Bearer credential**, ví dụ:

- Request thiếu một tham số Bearer bắt buộc trong một cách truyền token được sử dụng.
- Request lặp một tham số theo cách không được phép.
- Request gửi token theo **nhiều phương thức truyền đồng thời** (chẳng hạn header và form body khi server có hỗ trợ cả hai).
- Request chứa định dạng token không thể chấp nhận.
- Request sử dụng cơ chế truyền token mà endpoint không hỗ trợ, tùy triển khai và quy tắc áp dụng.

RFC 6750 mô tả các lỗi cú pháp và cách sử dụng Bearer token; đây **không** phải mã lỗi chung cho mọi dữ liệu API không hợp lệ.

### 4.1. Bearer header hợp lệ trông như thế nào?

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Giữa scheme và token phải có cú pháp hợp lệ. Một request như:

~~~http
Authorization: Bearer abc def
~~~

không biểu diễn một Bearer credential hợp lệ theo cú pháp thông dụng vì token bị tách thành nhiều phần bởi khoảng trắng. Với cấu hình `DefaultBearerTokenResolver` mặc định phù hợp, kiểu request đó có thể bị từ chối bằng `invalid_request` và **HTTP 400**.

Không coi `abc def` là hai token để chọn token thứ nhất. Không dùng `split(" ")` rồi lặng lẽ bỏ phần dư nếu đang viết token resolver tùy chỉnh.

### 4.2. Gửi token đồng thời ở header và query

Ví dụ không nên dùng:

~~~http
GET /api/orders?access_token=TOKEN_FROM_QUERY HTTP/1.1
Authorization: Bearer TOKEN_FROM_HEADER
~~~

RFC 6750 không cho phép dùng **nhiều cách truyền Access Token trong cùng request**. Nếu Resource Server được cấu hình hỗ trợ nhiều phương thức truyền và thấy token ở nhiều nơi, đây là một tình huống `invalid_request`.

Trong Spring Security Resource Server, **`DefaultBearerTokenResolver` mặc định ưu tiên Authorization header**; form-encoded body hoặc URI query token **không được bật theo mặc định**. Vì vậy, đừng giả định mọi request có `access_token` trong query đều bị phân loại giống nhau khi server **không bật** việc tìm token trong query.

**Khuyến nghị:** dùng duy nhất:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Không bật token trong URI query nếu không có yêu cầu bắt buộc và đánh giá rủi ro riêng: query string có thể bị ghi vào access logs, browser history, analytics, referrer hoặc giám sát hạ tầng.

### 4.3. Body token không phải phương thức mặc định cho JSON API

RFC 6750 mô tả khả năng truyền token trong **form-encoded body** với các điều kiện nhất định, nhưng đó không phải phương án mặc định tốt cho REST JSON API.

Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN_VALUE&item=sample
~~~

Nếu ứng dụng Spring Security **không cho phép form-body token**, request đó không tự trở thành authenticated chỉ vì có tham số `access_token`. Nếu hỗ trợ, phải tránh đồng thời dùng Authorization header và body token, và phải đánh giá nguy cơ token lộ trong body log.

### 4.4. Header Authorization lặp

Khi client/proxy gửi nhiều `Authorization` headers, behavior có thể phụ thuộc **HTTP server, reverse proxy và token resolver**. Hệ thống cần xác định chính sách **không chấp nhận cách đưa nhiều Bearer credentials không rõ ràng** và kiểm thử qua stack thực. Đừng tự viết logic lấy “header đầu tiên hoặc cuối cùng” khi các thành phần khác trong hạ tầng có thể hiểu khác.

### 4.5. invalid_request không phải lỗi JSON request body

Nếu endpoint `POST /api/orders` nhận:

~~~json
{"quantity": -100}
~~~

thì body sai nghiệp vụ có thể dẫn tới:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
~~~

Đây là lỗi **validation của API**, không phải OAuth Bearer `invalid_request` nếu Bearer credential được gửi đúng. Không nên gắn `WWW-Authenticate: Bearer error="invalid_request"` vào mọi lỗi 400 của REST API.

## 5. invalid_token: token không thể được xác thực/chấp nhận

Mã **`invalid_token`** mô tả Access Token hết hạn, bị revoke, malformed hoặc không hợp lệ vì lý do khác. Resource Server thường trả **401** nếu client có Bearer credential nhưng không thể xác thực nó.

### 5.1. Với JWT Resource Server

Các tình huống điển hình:

| Vấn đề JWT | Vì sao token bị từ chối? |
| --- | --- |
| JWT sai chữ ký | Không xác minh được bằng public key được tin cậy. |
| Token được ký bởi key/issuer khác | Không đáp ứng cấu hình trust của API. |
| `iss` sai | Không do issuer được cho phép phát hành theo hợp đồng. |
| `aud` sai hoặc không chứa API | Token dành cho resource khác. |
| `exp` đã qua | Token đã hết hiệu lực thời gian. |
| `nbf` chưa đến | Token chưa được phép sử dụng. |
| Algorithm không được cho phép | JWT không đáp ứng chính sách xác minh chữ ký. |
| Claims bắt buộc sai/missing | Không đáp ứng token profile của API. |
| JWT bị sửa hoặc không thể parse | Credential không phải JWT hợp lệ theo decoder. |
| Token sai loại/mục đích | Ví dụ dùng OIDC ID Token thay Access Token dành cho Resource Server. |

Lỗi `invalid_token` không có nghĩa Spring Security phải tiết lộ **nguyên nhân cụ thể** cho caller. Một response ngắn gọn thường phù hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Issuer/audience phải được kiểm tra tường minh. **Chữ ký hợp lệ không đủ** nếu token được phát hành cho API khác hoặc principal không thuộc nguồn được phép.

### 5.2. Với opaque token

Resource Server gửi token tới introspection endpoint. Nếu nhận:

~~~json
{"active": false}
~~~

thì token không được chấp nhận, thường dẫn đến **401** với ý nghĩa invalid token.

Nhưng **HTTP 200 từ introspection endpoint** có thể chứa `active:false` nên không được diễn giải HTTP status upstream là token hợp lệ. Ngược lại, HTTP 401/503 hoặc timeout **từ introspection endpoint** là vấn đề khác (client authentication hoặc sự cố upstream), không tự động chứng minh Access Token của caller đã hết hạn.

### 5.3. Token hết hạn không giống scope thiếu

Ví dụ token có:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "aud": ["orders-api"],
  "exp": 1700000000,
  "scope": "orders.read orders.write"
}
~~~

Khi thời điểm hiện tại đã qua `exp`, token phải bị từ chối ở **authentication** dù scope có mọi quyền. Nó không được “đi tiếp rồi nhận 403 vì scope” và không nên được chấp nhận vì request đã ghi đúng `Authorization: Bearer`.

### 5.4. Client nên làm gì khi nhận invalid_token?

Tùy OAuth flow, client có thể:

- Xin Access Token hợp lệ từ Authorization Server bằng một quy trình được phép.
- Nếu là OAuth 2.0 Client có Refresh Token, thực hiện refresh theo chính sách.
- Yêu cầu người dùng xác thực lại khi cần.
- Nếu token đã bị thu hồi, không cố phát lại cùng token liên tục.
- Kiểm tra client đang gọi **đúng API audience**, không gửi ID Token hoặc Access Token của một API khác.

Không phải mọi `invalid_token` đều sửa được bằng “refresh”: một client bị từ chối do issuer/audience sai hoặc cấu hình Authorization Server không phù hợp cần sửa token request/registration và scope/resource, không chỉ đổi token cùng loại.

## 6. insufficient_scope: credential hợp lệ nhưng không đủ quyền

Ví dụ endpoint:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
Content-Type: application/json

{"item":"book"}
~~~

Token đã được xác thực và có:

~~~json
{
  "scope": "orders.read"
}
~~~

Nhưng endpoint POST cần:

~~~text
orders.write
~~~

Khi đó Resource Server thường từ chối:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

**401 không phù hợp để mô tả trường hợp token được xác thực nhưng chỉ thiếu scope**, trừ khi một chính sách riêng coi sự thiếu hụt đó là điều kiện token profile không hợp lệ ngay ở authentication. Cần nhất quán giữa contract của token và lớp policy.

### 6.1. Scope không mặc định có quan hệ thứ bậc

Nếu token có `orders.write`, API **không nên tự suy** rằng nó cũng có `orders.read` trừ khi contract quy định. Spring Security:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

kiểm tra **đúng** GrantedAuthority đã được ánh xạ. Nó không biết `orders.write` có bao hàm `orders.read` hay không.

### 6.2. Scope khác vai trò và quyền trên tài nguyên

Giả sử caller có `SCOPE_orders.read` nhưng cố xem đơn hàng của người khác:

~~~text
JWT hợp lệ
Authority: SCOPE_orders.read
Order ID: 42 thuộc tenant khác
~~~

Điều kiện OAuth scope có thể đã đạt, nhưng **domain authorization** vẫn phải chặn. Response có thể là **403** hoặc **404** theo chính sách che giấu tài nguyên. Không nhất thiết dùng `insufficient_scope`, vì caller không thiếu scope chung; caller thiếu **quyền trên bản ghi cụ thể**.

Tương tự, `hasRole("ADMIN")` theo mặc định kiểm tra `ROLE_ADMIN`, không giống `hasAuthority("SCOPE_admin.manage")`. Nếu domain sử dụng role nội bộ thay OAuth scopes, error handling không nên tự diễn giải mọi AccessDeniedException là thiếu OAuth scope thật.

### 6.3. Có nên thông báo scope cần thiết?

RFC 6750 cho phép kèm tham số `scope`:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

Điều đó giúp client hiểu quyền yêu cầu. Nhưng chỉ cung cấp những scope được phép tiết lộ. Nếu endpoint/role hoặc tài nguyên mang tính nhạy cảm, việc liệt kê scope có thể bị lợi dụng để thăm dò chức năng. Cũng không có gì bảo đảm client sẽ được Authorization Server cấp scope đó chỉ vì Resource Server yêu cầu.

## 7. Phân biệt ba mã lỗi với những trường hợp không thuộc Bearer

| Request hoặc trạng thái | Mã HTTP thường gặp | Bearer error phù hợp? |
| --- | --- | --- |
| GET endpoint bảo vệ, không có Authorization header | **401** | Bearer challenge **không có error**. |
| Authorization theo scheme khác và API chỉ hỗ trợ Bearer | **401** | Có thể chỉ Bearer challenge, không gắn error. |
| Bearer header sai cú pháp | **400** | `invalid_request`. |
| Gửi token theo nhiều cách không được phép | **400** | `invalid_request`. |
| JWT bị sửa/chữ ký sai | **401** | `invalid_token`. |
| JWT hết hạn, issuer/audience không hợp lệ | **401** | `invalid_token`. |
| Opaque introspection trả `active:false` | **401** | `invalid_token`. |
| Bearer token hợp lệ nhưng thiếu OAuth scope | **403** | `insufficient_scope`. |
| Bearer token hợp lệ, scope đủ, tài khoản nội bộ bị khóa | **403** | Domain denied; không tự xem là `invalid_token`. |
| Scope đủ nhưng truy cập order của tenant khác | **403/404** | Domain denied; không nhất thiết `insufficient_scope`. |
| JSON body sai schema | **400** | Lỗi REST API, **không phải** `invalid_request` Bearer. |
| Route không tồn tại | **404** hoặc security policy có thể từ chối trước | Không tự suy Bearer error. |
| Introspection endpoint 503 / JWKS không tải được | **Có thể 5xx** theo exception mapping | Lỗi upstream; phải fail closed, không tự gọi token revoked. |

**Điểm cốt lõi:** HTTP status, OAuth error code và business error code **có liên quan nhưng không đồng nhất**. Thiết kế tốt phân loại lỗi ở đúng tầng phát sinh thay vì bắt mọi exception rồi trả cùng một response.

## 8. Spring Security xử lý lỗi Bearer ở đâu?

Với Servlet Resource Server, các thành phần thường gặp:

~~~text
HttpServletRequest
      |
      v
BearerTokenAuthenticationFilter
      |
      +-- BearerTokenResolver
      |     +-- request không hợp lệ -> OAuth2AuthenticationException
      |           |
      |           v
      |       BearerTokenAuthenticationEntryPoint
      |       -> invalid_request / 400 (khi error tương ứng)
      |
      +-- Có token
             |
             v
       AuthenticationManager
             |
             +-- JWT: JwtAuthenticationProvider -> JwtDecoder
             |
             +-- Opaque: OpaqueTokenAuthenticationProvider
             |           -> OpaqueTokenIntrospector
             |
             +-- Không xác thực được
             |     -> BearerTokenAuthenticationEntryPoint
             |     -> 401 / invalid_token khi error tương ứng
             |
             +-- Xác thực thành công
                     |
                     v
               AuthorizationFilter
                     |
                     +-- Thiếu authority/scope
                     |      -> AccessDeniedException
                     |      -> BearerTokenAccessDeniedHandler
                     |      -> 403 / insufficient_scope khi phù hợp
                     v
               Controller / Method Security
~~~

### 8.1. DefaultBearerTokenResolver

`DefaultBearerTokenResolver` của Spring Security đọc Bearer Access Token từ request. Mặc định nó ưu tiên **Authorization header** và không bật truyền token trong query/form body. Nó cũng kiểm tra định dạng Bearer header trước khi đưa token vào AuthenticationManager.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);

    return resolver;
}
~~~

Trong ví dụ, hai tùy chọn được đặt **false một cách tường minh**; đây cũng là lựa chọn mặc định phổ biến. Nếu cấu hình bean resolver riêng, phải chắc chắn nó đang được Resource Server sử dụng. Không tự bật `setAllowUriQueryParameter(true)` chỉ để hỗ trợ một client cũ mà chưa đánh giá rủi ro token lộ qua URL.

### 8.2. BearerTokenAuthenticationEntryPoint

`BearerTokenAuthenticationEntryPoint` có nhiệm vụ trả **challenge** khi authentication thất bại hoặc credential không có/không hợp lệ.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;

@Bean
BearerTokenAuthenticationEntryPoint bearerEntryPoint() {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();
    entryPoint.setRealmName("orders-api");
    return entryPoint;
}
~~~

Đặt `realm` giúp response thể hiện vùng bảo vệ. Lỗi chính xác trong header phụ thuộc `AuthenticationException` và `OAuth2Error`/Bearer error mà Spring Security nhận được.

**Không thay toàn bộ exception handling bằng một handler luôn trả 401** vì như vậy có thể biến thiếu scope thành “token invalid” và làm mất thông tin cần thiết cho client.

### 8.3. BearerTokenAccessDeniedHandler

`BearerTokenAccessDeniedHandler` xử lý `AccessDeniedException` khi caller đã qua authentication nhưng không được phép truy cập.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

@Bean
BearerTokenAccessDeniedHandler bearerAccessDeniedHandler() {
    BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();
    handler.setRealmName("orders-api");
    return handler;
}
~~~

Với Authentication hợp lệ thiếu authority, handler thường trả **403** và Bearer `insufficient_scope`. Nhưng một `AccessDeniedException` cũng có thể đến từ tenant/owner policy. Nếu ứng dụng cần error code domain riêng, phải làm rõ ranh giới và thiết kế handler có chủ đích; không mặc định mọi 403 đều do OAuth scope.

### 8.4. Gắn entry point và access-denied handler

Ví dụ DSL:

~~~java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerAccessDeniedHandler)
);
~~~

Đoạn trên dùng các bean đã tạo ở hai mục trước và đặt trong cùng `SecurityFilterChain` của API Bearer. Đây là cấu hình minh họa thay vì một Spring Boot application hoàn chỉnh độc lập; mục tiếp theo trình bày chain đầy đủ.

## 9. Cấu hình JWT Resource Server và nhóm endpoint

### 9.1. Dependencies

Ví dụ Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 9.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

Trên các phiên bản Spring Boot hỗ trợ `audiences`, API yêu cầu claim `aud` chứa `orders-api`. Nếu phiên bản khác, cần thêm audience validator phù hợp. Resource Server cũng cần xác minh JWT signature, issuer, time claims và profile theo chính sách.

### 9.3. SecurityFilterChain hoàn chỉnh

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApiChain(HttpSecurity http)
            throws Exception {

        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
            new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin.manage")
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong ví dụ:

- Không có token cho `GET /api/orders` → **401** Bearer challenge, thông thường không có error code.
- Bearer token malformed → token resolver từ chối, có thể **400 invalid_request** theo error được phát sinh.
- Bearer JWT sai chữ ký hoặc hết hạn → **401 invalid_token**.
- JWT hợp lệ chỉ có `orders.read` nhưng gọi `POST /api/orders` → **403 insufficient_scope** theo handler.
- JWT hợp lệ có `orders.read`, gọi GET → có thể đi tới controller/domain policy.
- Endpoint không được khai báo trong chain → `denyAll`, kể cả khi có token quản trị.

`securityMatcher("/api/**")` chỉ chọn **chain** cho đường dẫn này; nếu ứng dụng có URL ngoài `/api/**`, phải tạo **fallback SecurityFilterChain** hoặc chính sách khác. Không giả định `anyRequest().denyAll()` bảo vệ request nằm ngoài mọi chain.

`csrf.disable()` và `STATELESS` ở đây dành cho API chỉ dùng Bearer Authorization header, không dùng session-cookie authentication. Nếu cùng backend có web OIDC Login, cần chính sách CSRF/session/CORS tương ứng theo từng chain.

## 10. Một request public vẫn có thể bị từ chối vì Bearer header sai

Giả sử API định nghĩa:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
~~~

Với request:

~~~http
GET /api/public/ping HTTP/1.1
Host: api.example.test
~~~

thì HTTP authorization cho phép anonymous truy cập.

Nhưng với:

~~~http
GET /api/public/ping HTTP/1.1
Authorization: Bearer abc def
~~~

`BearerTokenAuthenticationFilter` có thể xử lý header trước `AuthorizationFilter`, phát hiện Bearer request malformed và trả **invalid_request**. Vì vậy **`permitAll()` không đồng nghĩa “bỏ qua mọi authentication filter”**.

Tương tự, một Bearer token sai chữ ký gửi vào public endpoint có thể gây **401**, tùy security chain có Bearer processing và cách handler được cấu hình.

Nếu cần một health endpoint hoàn toàn không phụ thuộc authentication, hãy thiết kế **chain/route riêng** theo nhu cầu hạ tầng và giới hạn dữ liệu được công bố, chứ không dựa vào giả định permitAll sẽ chặn xử lý credential lỗi.

## 11. JWT và opaque token cùng sử dụng các lỗi Bearer

Ba mã của RFC 6750 thuộc **giao thức sử dụng Bearer token**, không chỉ dành cho JWT.

### 11.1. JWT Resource Server

~~~text
Bearer token
  -> NimbusJwtDecoder
  -> JWS signature + issuer/audience/time validation
  -> JwtAuthenticationToken
  -> SCOPE_... authorities
~~~

JWT hết hạn/sai issuer/sai chữ ký thường dẫn tới `invalid_token`. Token hợp lệ mà thiếu scope dẫn tới `insufficient_scope` trong trường hợp phù hợp.

### 11.2. Opaque Resource Server

~~~text
Bearer token
  -> OpaqueTokenIntrospector
  -> Authorization Server introspection
  -> active false => token invalid
  -> active true + metadata đáp ứng contract
  -> BearerTokenAuthentication
  -> SCOPE_... authorities
~~~

Với opaque token, cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: SECRET_FROM_A_SECURE_STORE
~~~

Và trong chain chọn:

~~~java
.oauth2ResourceServer(oauth ->
    oauth.opaqueToken(Customizer.withDefaults()))
~~~

để thay cho nhánh `jwt()` khi API chỉ nhận opaque token.

Lỗi **`active:false`** thường được trả cho client như `invalid_token`; token active nhưng thiếu scope vẫn có thể trả `insufficient_scope`. **Introspection endpoint timeout hoặc HTTP 503** là lỗi xác thực phụ thuộc dịch vụ, không tự kết luận Access Token revoked; không dùng cơ chế fail-open.

## 12. Những chi tiết trong Spring Security dễ gây hiểu nhầm

### 12.1. BearerTokenErrors và OAuth2AuthenticationException

Spring Security có các kiểu lỗi liên quan Bearer như `BearerTokenError`, `BearerTokenErrors` và những hằng mã ở `BearerTokenErrorCodes`. Token resolver hoặc authentication provider có thể phát sinh `OAuth2AuthenticationException` chứa một `OAuth2Error` tương ứng. Entry point dùng loại lỗi đó để tạo HTTP response.

Vì vậy, nếu tự viết token resolver/introspector, hãy **giữ ngữ nghĩa error type** thay vì quăng mọi exception thành `RuntimeException` rồi bắt lại bằng một controller advice luôn trả 500 hoặc 200.

### 12.2. BearerTokenAccessDeniedHandler không biết toàn bộ domain policy

Handler này có thể dùng `insufficient_scope` cho những AccessDeniedException khi Authentication đã được xác thực. Tuy nhiên:

~~~text
Role/Scope authorization: thiếu SCOPE_orders.write
Domain authorization: đơn hàng không thuộc caller
~~~

đều có thể kết thúc bằng **403** nhưng **không cùng ý nghĩa**. Khi ứng dụng yêu cầu phân biệt ở response, cần thiết kế exception/domain error mapping riêng, giữ status bảo mật, tránh tiết lộ owner/tenant nhạy cảm và không làm mất các challenge Bearer thật.

### 12.3. Không phải mọi Authentication là JWT

Với JWT Resource Server principal thường là `JwtAuthenticationToken`; với opaque token thường là `BearerTokenAuthentication`; với OAuth2 Login session có thể là dạng Authentication khác. Một custom error handler không nên cast mọi principal thành `Jwt` để lấy `scope` hoặc `iss`.

### 12.4. 401 là unauthorized nhưng nói về authentication

Tên HTTP **401 Unauthorized** dễ gây hiểu nhầm: trong security architecture, nó thường yêu cầu **authentication** hợp lệ. Còn **403 Forbidden** áp cho principal đã xác thực nhưng **không được phép** thực hiện hành động.

Nếu JWT sai chữ ký, không thể cho request trở thành Authentication thành công rồi trả 403 chỉ vì thiếu một role. Nếu không có token, đừng tạo principal anonymous với authority quản trị để “cho endpoint chạy”.

## 13. Thiết kế lỗi JSON body đi cùng Bearer challenge

Spring Security có thể trả chỉ `WWW-Authenticate` mà không có JSON body. Nếu API muốn JSON lỗi nhất quán, có thể bổ sung body nhưng **không được làm sai HTTP status và header Bearer**.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json

{
  "type": "https://docs.example.test/problems/invalid-token",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Không thể xác thực yêu cầu."
}
~~~

Lưu ý:

- Body không thay thế `WWW-Authenticate` challenge.
- Không tự động đưa mọi thông tin từ exception vào `detail`.
- Tránh body `{"error":"Signature key rsa-2026-a missing from internal-jwks-host"}` vì tiết lộ cấu hình.
- Không trả thông tin người sở hữu token, email, `sub` hoặc quyền internal nếu token invalid.
- Giữ API error contract nhất quán giữa filter exceptions và controller/domain exceptions.

**Chỉ dựa vào `@RestControllerAdvice` không đủ để xử lý mọi lỗi Resource Server**, vì Bearer filter và authorization filters chạy **trước controller**. Nếu viết JSON error handler, tích hợp qua `AuthenticationEntryPoint` và `AccessDeniedHandler` hoặc cơ chế phù hợp; phải giữ hành vi đã chuẩn của Bearer challenge.

### 13.1. Không trả quá nhiều thông tin về insufficient_scope

Một response có thể ghi:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

nhưng API quản trị nội bộ không nhất thiết muốn công bố toàn bộ danh sách scope/role được sử dụng. Có thể dùng thông điệp trung tính ở body và tài liệu dành cho client được cấp quyền. Scope xuất hiện trong challenge cũng phải đúng tên scope OAuth được sử dụng trong contract, không tự suy ra từ các internal roles có tiền tố `ROLE_`.

### 13.2. CORS expose headers nếu frontend cần đọc WWW-Authenticate

Browser JavaScript có thể cần đọc `WWW-Authenticate` để xử lý lỗi. CORS policy có thể phải **expose** header đó cho origin được phép:

~~~java
cors.setExposedHeaders(
    List.of("WWW-Authenticate"));
~~~

Đây là phần bổ sung vào một `CorsConfiguration` đã có origin/method/header allowlist. CORS không thay authentication/authorization, và việc expose header không cho client quyền mới. Đừng dùng wildcard origin/credentials không đúng quy định để “sửa” lỗi 401 hoặc 403.

## 14. HTTP client nên xử lý ba lỗi thế nào?

Một OAuth 2.0 client tốt không xử lý mọi 401/403 bằng vòng lặp “refresh và gọi lại”.

### 14.1. Khi nhận invalid_request

Kiểm tra:

1. Có đúng `Authorization: Bearer TOKEN` không?
2. Có khoảng trắng hoặc ký tự không hợp lệ trong header không?
3. Có gửi token trong query/body cùng lúc không?
4. Proxy có gộp/sửa/lặp Authorization header không?
5. Client có dùng cơ chế truyền token mà server hỗ trợ không?

**Sửa request**, không nhất thiết làm user đăng nhập lại. Refresh token không giải quyết lỗi header malformed.

### 14.2. Khi nhận invalid_token

Kiểm tra credential lifecycle:

1. Token có hết hạn/revoked không?
2. Client có gửi đúng Access Token thay vì ID Token không?
3. Có đúng issuer và audience/resource không?
4. Client có đang giữ token từ một môi trường khác (dev/staging/prod) không?
5. Có thể lấy Access Token mới bằng flow hợp lệ không?

Nếu là client có refresh token, có thể refresh theo chính sách với **giới hạn retry** và tránh nhiều concurrent refresh bất tận. Không log token cũ/mới. Nếu server liên tục từ chối token mới do issuer/audience sai, cần điều tra cấu hình, không gọi refresh mãi.

### 14.3. Khi nhận insufficient_scope

Đừng giả định refresh cùng grant sẽ cấp quyền mới: scope không tự tăng qua refresh. Có thể:

- Kiểm tra đã gọi đúng endpoint không.
- Nếu quyền phù hợp chính sách, bắt đầu authorization flow để **yêu cầu scopes bổ sung**.
- Hiển thị thông báo không đủ quyền hoặc liên hệ quản trị viên.
- Không cho client tự gửi một header `X-Scope: admin.manage` để thay thế claims đã được xác thực.

Không hướng dẫn client gửi lại Access Token trong query string nhằm “vượt 403”; vấn đề là quyền, không phải cách đưa token.

## 15. Kiểm thử từng mã lỗi bằng MockMvc và decoder test

Để kiểm thử đúng, cần tách:

- **Token resolution tests**: Bearer header và cách truyền token có hợp lệ không?
- **Token authentication tests**: JWT/opaque token có thực sự được xác minh không?
- **HTTP authorization tests**: principal hợp lệ có đủ authority cho endpoint không?

### 15.1. Ma trận yêu cầu

| Kịch bản | Dự kiến | Tầng |
| --- | --- | --- |
| Không gửi Authorization header tới endpoint bảo vệ | **401**, Bearer challenge không error. | Authentication entry point. |
| Gửi `Authorization: Basic ...` tới Bearer-only API | **401**, có thể chỉ Bearer challenge. | Unsupported/missing Bearer credential. |
| Gửi `Authorization: Bearer abc def` | **400 invalid_request** theo resolver mặc định phù hợp. | Token resolution. |
| Gửi JWT chuỗi sai định dạng | **401 invalid_token** khi decoder từ chối. | Token authentication. |
| JWT hết hạn | **401 invalid_token**. | JWT validation. |
| JWT sai issuer/audience | **401 invalid_token**. | JWT validation. |
| Opaque `active:false` | **401 invalid_token**. | Introspection authentication. |
| JWT hợp lệ, `SCOPE_orders.read`, gọi GET | Cho phép đi tới handler/domain service. | HTTP authorization. |
| JWT hợp lệ, chỉ `SCOPE_orders.read`, gọi POST | **403 insufficient_scope**. | HTTP authorization. |
| JWT hợp lệ, đủ scope nhưng sai owner/tenant | **403 hoặc 404**, không nhất thiết insufficient_scope. | Domain authorization. |
| Malformed JSON body với Bearer hợp lệ | **400 domain validation**, không phải Bearer invalid_request. | Controller/request validation. |
| JWKS hoặc introspection endpoint timeout | Không cho truy cập; mapping 5xx/503 tùy handler. | Dependency/operation failure. |

### 15.2. Unit test token resolver: invalid_request

Để kiểm tra cú pháp Bearer header trực tiếp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BearerTokenResolverTest {

    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void malformedBearerHeaderIsInvalidRequest() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();
        request.addHeader(
            HttpHeaders.AUTHORIZATION, "Bearer abc def");

        OAuth2AuthenticationException exception =
            assertThrows(
                OAuth2AuthenticationException.class,
                () -> resolver.resolve(request));

        assertEquals(
            "invalid_request", exception.getError().getErrorCode());
    }

    @Test
    void noBearerTokenReturnsNull() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        assertEquals(null, resolver.resolve(request));
    }
}
~~~

Đây là **unit test token resolution**, không phải HTTP response test; nó chỉ chứng minh resolver phát lỗi với mã `invalid_request`. Khi kiểm thử HTTP 400 và `WWW-Authenticate`, cần chạy request qua Spring Security filter chain cùng entry point.

### 15.3. MockMvc test cho authentication và authorization

Ví dụ tối thiểu dùng một `JwtDecoder` test từ chối raw Bearer token, còn `jwt()` tạo principal giả để kiểm tra scope:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(BearerErrorHttpTest.TestDecoderConfig.class)
class BearerErrorHttpTest {

    @Autowired
    MockMvc mockMvc;

    @TestConfiguration
    static class TestDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException("Bad test token");
            };
        }
    }

    @Test
    void missingTokenHasBearerChallengeWithoutInvalidTokenCode()
            throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void malformedBearerHeaderReturnsInvalidRequest()
            throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer abc def"))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_request")));
    }

    @Test
    void tokenRejectedByDecoderReturnsInvalidToken()
            throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer opaque-looking-value"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_token")));
    }

    @Test
    void authenticatedReaderCannotWrite()
            throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedReaderCanPassReadRule()
            throws Exception {
        // Nếu không có controller tương ứng, kết quả
        // cuối có thể là 404 dù authorization đã cho phép.
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }
}
~~~

**Điều kiện dùng ví dụ:** ứng dụng test phải có một `SecurityFilterChain` như mục 9 và **controller `GET /api/orders` trả 200** để assertion cuối đúng. Nếu chưa có handler, request được authorization cho phép có thể trả **404**, không phải lỗi security. Bean decoder test chỉ dành cho kiểm thử và không được tồn tại cùng một bean decoder production gây trùng cấu hình. `with(jwt())` cố ý bỏ qua decoder, nên hai test cuối **không xác minh chữ ký thật**.

### 15.4. Kiểm tra riêng insufficient_scope header

Với `BearerTokenAccessDeniedHandler` mặc định phù hợp và principal đã được xác thực:

~~~java
mockMvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("insufficient_scope")));
~~~

Đây là test **HTTP authorization + access-denied handler**. Header có thể không chứa tham số `scope="orders.write"` nếu handler không biết danh sách scope thiếu từ `AccessDeniedException`; không ép mọi test phải thấy tham số đó. Nếu ứng dụng có custom handler, cần kiểm tra semantics riêng của handler.

### 15.5. Kiểm thử JWT ký thật

Một bộ test khác phải xác minh đường JWT thực:

~~~text
1. Sinh RSA key pair test.
2. Cấu hình NimbusJwtDecoder bằng public key test hoặc JWKS test server.
3. Ký JWT bằng private key test.
4. Tạo token hợp lệ, token sai chữ ký,
   token sai issuer, token sai audience, token hết hạn.
5. Gửi Bearer token qua filter chain, không dùng jwt().
6. Kiểm tra token hợp lệ có thể authenticated,
   token sai bị từ chối trước khi chạy controller.
~~~

`JwtDecoder` cần validator issuer, audience và thời gian phù hợp. Một `jwt()` MockMvc fixture **không** kiểm tra decoder/JWKS; test đó chỉ phù hợp kiểm tra authorities và endpoint policy.

### 15.6. Kiểm thử opaque introspection thật

Dùng introspection test server trả:

~~~text
token=active-reader
  -> HTTP 200 {"active":true,"scope":"orders.read"}

token=inactive
  -> HTTP 200 {"active":false}

token=upstream-error
  -> HTTP 503
~~~

Gửi raw Bearer token qua Resource Server với introspector thật trỏ test server. Kiểm tra:

- `active:false` → authentication thất bại, thường **401 invalid_token**.
- `active:true`, thiếu write scope → **403 insufficient_scope** khi gọi POST.
- HTTP 503 → không cho request chạy như authenticated; lỗi được phân loại upstream, không nhầm thành token revoked.

Helper MockMvc `opaqueToken()` tạo Authentication giả nên **không test RFC 7662 `active` thực tế**. Muốn kiểm tra introspection phải dùng client/server fixture.

## 16. Lưu ý về multiple SecurityFilterChain

Ứng dụng có thể có:

~~~text
/api/**       -> Resource Server Bearer chain
/web/**       -> OIDC Login + session chain
/management/**-> Management policy riêng
fallback      -> denyAll
~~~

Nếu cùng ứng dụng sử dụng OIDC Login và API Bearer, không nên để **Bearer entry point** điều khiển mọi request web session, hoặc để **redirect tới login page** thay cho HTTP 401 khi API client gửi Bearer token.

`securityMatcher` chọn chain; bên trong chain, `requestMatchers` quyết định quyền. Phải đặt chain cụ thể trước, fallback sau, và bảo đảm không có endpoint nằm ngoài mọi chain được bảo vệ.

Đối với CORS preflight từ browser, OPTIONS request thường không chứa Bearer Access Token; cần cấu hình **CORS processing đúng trước authentication**. Đừng gọi CORS preflight failure là `invalid_token` khi browser chưa gửi token. Với API dùng cookie/session, xử lý CSRF theo mô hình tương ứng; với Bearer header stateless có thể chọn chính sách khác.

## 17. Bảo vệ error handling và quan sát hệ thống

### 17.1. Những dữ liệu có thể log

- Request ID, endpoint logical name, HTTP method và status.
- Error category như `bearer_invalid_request`, `jwt_invalid_token`, `insufficient_scope`.
- Issuer/resource **đã cấu hình** khi cần cho diagnostics, tránh lấy URL chưa kiểm chứng làm nguồn tin cậy.
- JWT decoder/introspection latency và các lỗi mạng ở mức loại lỗi.
- Tỷ lệ 401/403, tỷ lệ auth failure và authorization denied.

### 17.2. Những dữ liệu không nên log

- Nguyên `Authorization` header hoặc Access Token.
- Refresh Token, client secret, private keys hoặc introspection request body.
- Toàn bộ JWT payload/claims chứa PII.
- Session cookies hoặc dữ liệu xác thực do client gửi.
- Stack trace trong HTTP response, URL JWKS nội bộ nhạy cảm, key material.

### 17.3. Chống thăm dò lỗi

Nếu client nhận thông điệp quá chi tiết cho từng token:

~~~text
Token không tồn tại
Token thuộc user A và đã bị khóa
Token có kid X nhưng ký sai
Token của tenant Y không có scope ...
~~~

kẻ tấn công có thể suy ra thông tin token hoặc kiến trúc. Nên dùng challenge chuẩn, mô tả ngắn gọn và log nội bộ được phân quyền thay vì phản chiếu mọi chi tiết.

Không xử lý `invalid_request` bằng cách in raw Authorization header để debug; đó là một trong những nơi dễ làm lộ Bearer credential khi client mắc lỗi.

## 18. Những lỗi thường gặp khi áp dụng ba mã OAuth

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Trả `invalid_token` cho request không có token. | Client hiểu nhầm token có tồn tại nhưng bị lỗi. | 401 Bearer challenge, thường **không có error**. |
| Trả `invalid_request` cho mọi HTTP 400. | Trộn lỗi Bearer protocol với validation của body. | Phân loại theo tầng. |
| Trả `invalid_token` cho JWT hợp lệ thiếu write scope. | Sai ngữ nghĩa authentication/authorization. | Thường 403 `insufficient_scope`. |
| Trả 403 cho token sai chữ ký. | Giả định principal đã xác thực trong khi credential sai. | 401 `invalid_token`. |
| Cho phép khi JWT decoder/introspection timeout. | Fail-open ở ranh giới xác thực. | Fail closed, phân loại upstream error. |
| Thấy HTTP 200 introspection thì cho token đi qua. | Response 200 có thể `active:false`. | Kiểm tra boolean active. |
| Dùng `hasRole("ADMIN")` với token chỉ có `SCOPE_admin.manage`. | Rule không khớp hoặc bị workaround kém an toàn. | Thống nhất authority converter và policy. |
| Tạo custom handler luôn trả JSON 200/401. | Che mất 400 invalid_request và 403 insufficient_scope. | Giữ đúng HTTP status và WWW-Authenticate. |
| Trả `scope` từ body do client gửi. | Client ảnh hưởng mô tả chính sách bảo mật. | Scope phải do server policy định nghĩa. |
| Cho phép Bearer token trong URL vì client tiện. | Token dễ lộ qua logs/history/referrer. | Dùng Authorization header. |
| Bỏ security filter trên public endpoints để né lỗi Bearer. | Mất các security controls khác. | Dùng permitAll/chain rõ ràng theo yêu cầu. |
| Chỉ test MockMvc `jwt()` rồi nghĩ invalid_token được test. | Test bỏ qua JWT verification. | Thêm signed-JWT integration tests. |
| Log toàn bộ Bearer header khi authentication failure. | Rò rỉ credential. | Log mã lỗi và request ID. |
| Đồng nhất domain 403 với `insufficient_scope`. | Thông báo sai nguyên nhân; lộ cấu trúc quyền. | Domain error mapping riêng khi cần. |

## 19. Quy trình triển khai lỗi Bearer nhất quán

1. **Xác định loại Access Token**: JWT hoặc opaque, issuer/audience, token type và cách xác thực phù hợp.
2. **Đặt Bearer resolution rõ ràng**: chấp nhận Authorization header, không mặc nhiên nhận token từ query/body hoặc nhiều nguồn.
3. **Dùng framework exception handling chuẩn**: `BearerTokenAuthenticationEntryPoint` cho authentication, `BearerTokenAccessDeniedHandler` cho authorization.
4. **Phân loại ba lỗi**: request malformed → `invalid_request`; token không hợp lệ → `invalid_token`; token hợp lệ thiếu OAuth scope → `insufficient_scope`.
5. **Giữ 401/403 đúng ranh giới**: không có credential hoặc token sai thuộc authentication; scope và quyền nghiệp vụ thuộc authorization.
6. **Thiết kế response không lộ bí mật**: `WWW-Authenticate` đúng cú pháp, body ngắn gọn, không chứa token, secrets, owner/tenant hoặc stack trace.
7. **Tách upstream outage**: JWKS/introspection lỗi không tự cho phép; không gọi nhầm mọi lỗi network là revoked token.
8. **Kiểm thử ở ba tầng**: resolver, JwtDecoder/introspector thật, endpoint authorization bằng MockMvc.
9. **Đảm bảo chain coverage/CORS/CSRF**: API Bearer khác web OIDC session; public endpoint có thể vẫn xử lý malformed Bearer header.
10. **Ghi nhận metrics và audit an toàn**: theo dõi error categories, 401/403 và reliability mà không làm lộ credential.

**Ghi nhớ:** **`invalid_request` = request Bearer sai quy tắc; `invalid_token` = credential không được chấp nhận; `insufficient_scope` = token hợp lệ nhưng thiếu phạm vi quyền.** Với Spring Security Resource Server, việc hiểu **`WWW-Authenticate`**, phân biệt **400/401/403** và kiểm thử các đường **authentication/authorization** giúp API rõ ràng với client mà vẫn giữ đúng ranh giới bảo mật.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Section 3: WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc6750#section-3).
- [RFC 6750 — Section 3.1: Error Codes](https://www.rfc-editor.org/rfc/rfc6750#section-3.1).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [Spring Security — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html).
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
