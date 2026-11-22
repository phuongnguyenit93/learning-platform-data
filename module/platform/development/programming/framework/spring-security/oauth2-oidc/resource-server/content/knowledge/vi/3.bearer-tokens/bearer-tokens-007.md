# Không có token khác với có token nhưng không hợp lệ

## 1. Hai yêu cầu đều có thể trả 401 nhưng khác bản chất

Một **OAuth 2.0 Resource Server** bảo vệ API bằng Bearer access token có thể trả `401 Unauthorized` cho cả hai trường hợp:

1. **Không có Bearer token:** Client chưa cung cấp credential mà API yêu cầu. Không có chuỗi token nào để xác thực.
2. **Có Bearer token nhưng không hợp lệ:** Client đã cung cấp một credential nhưng Resource Server không chấp nhận nó, chẳng hạn token hết hạn, sai chữ ký hoặc sai issuer.

Ví dụ với endpoint `GET /api/reports` yêu cầu access token:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
```

Đây là request **không có token**. Ngược lại:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...invalid-or-expired...
```

Đây là request **có Bearer credential**; Resource Server có thể thử xác thực và xác định credential không hợp lệ. Phân biệt này giúp đọc đúng `WWW-Authenticate`, hiểu luồng Spring Security và chọn biện pháp xử lý phù hợp.

Trong phần lớn API Bearer-only, hai trạng thái đều dẫn tới **401** khi endpoint bắt buộc xác thực. Tuy nhiên, chúng khác ở nguyên nhân, giai đoạn xử lý và thông tin lỗi. Đặc biệt, **token hợp lệ nhưng thiếu quyền** lại là một trường hợp thứ ba, thường dẫn tới **403 Forbidden**.

## 2. Bảng phân biệt ba trạng thái

| Trạng thái | Authentication | Authorization | Phản hồi điển hình |
| --- | --- | --- | --- |
| Không có Bearer token | Chưa có credential để xác thực người gọi. | Endpoint cần authentication nên không cho truy cập. | `401`, header `WWW-Authenticate: Bearer`, thường **không có mã `error`**. |
| Có token nhưng không hợp lệ | Đã nhận credential nhưng xác thực thất bại. | Chưa đến bước đánh giá quyền dựa trên principal hợp lệ. | `401`, `error="invalid_token"` khi lỗi thuộc loại invalid token. |
| Có access token hợp lệ nhưng thiếu quyền | Xác thực thành công. | Không đáp ứng scope/authority hoặc chính sách quyền. | `403`, có thể có `error="insufficient_scope"`. |

Luồng tư duy:

```mermaid
flowchart TD
    A["Request vào Resource Server"] --> B{"Có Bearer credential?"}
    B -- "Không" --> C{"Endpoint yêu cầu xác thực?"}
    C -- "Không" --> D["Có thể cho phép xử lý"]
    C -- "Có" --> E["401 - Bearer challenge, không có invalid_token"]
    B -- "Có" --> F{"Token qua xác thực?"}
    F -- "Không" --> G["401 - invalid_token hoặc lỗi cú pháp tương ứng"]
    F -- "Có" --> H{"Đủ quyền endpoint?"}
    H -- "Không" --> I["403 - access denied / insufficient_scope"]
    H -- "Có" --> J["Tiếp tục kiểm tra quyền dữ liệu, nghiệp vụ"]
```

Sơ đồ giả định một API chỉ dùng Bearer authentication. Nếu ứng dụng cũng dùng session, Basic hoặc cơ chế khác, một request **không có Bearer token** vẫn có thể được xác thực bằng phương thức đó; kết quả cuối cùng tùy filter chain.

## 3. Không có token nghĩa là gì?

Resource Server không nhận được Bearer credential theo cách mà nó được cấu hình để đọc. Ví dụ:

- Không có header `Authorization`.
- Client nhầm dùng `X-Access-Token` trong khi API chỉ đọc `Authorization`.
- Client gửi `Authorization: Basic ...` vào API chỉ xử lý Bearer; Bearer resolver không coi đây là Bearer token.
- Client đặt `access_token` trong query string, nhưng resource server dùng `DefaultBearerTokenResolver` mặc định không bật nhận token qua URI.

Request tới endpoint được bảo vệ:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Accept: application/json
```

Phản hồi điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Nếu server cấu hình realm, header có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api"
```

RFC 6750 hướng dẫn server **không gửi mã `error`** khi client chưa gửi thông tin xác thực. Vì vậy, **không có token** thường là một Bearer challenge trống hoặc chỉ có `realm`, chứ không phải `invalid_token`.

### Endpoint công khai có thể không cần token

Giả sử `/api/public` được cấu hình `permitAll()`. Request không có token vẫn có thể trả **200 OK**. Filter Bearer không tìm thấy token thì để request đi tiếp; tại bước authorization, `permitAll()` cho phép truy cập.

Ngược lại, `/api/reports` yêu cầu `authenticated()` hoặc `SCOPE_reports:read` thì không thể truy cập bằng một request anonymous trong ứng dụng Bearer-only. Do đó **không có token không tự tạo lỗi ngay tại bước trích xuất Bearer credential**; việc 401 xuất hiện phụ thuộc endpoint có yêu cầu xác thực hay không.

## 4. Có token nhưng không hợp lệ nghĩa là gì?

Client đã gửi một chuỗi Bearer token:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...expired...
```

Resource Server nhận được credential, nhưng việc xác thực thất bại. Phản hồi điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Có thể có tham số bổ sung:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token", error_description="The access token expired"
```

`error_description` chỉ là trường tùy chọn. Client nên dựa vào HTTP status và `error` chuẩn, không phụ thuộc chính xác vào từng chữ của mô tả.

### Các nguyên nhân cần nhận biết

| Nguyên nhân | JWT access token | Opaque access token |
| --- | --- | --- |
| Hết hạn | Claim `exp` đã hết hiệu lực. | Introspection cho biết token không còn active. |
| Sai chữ ký/thuật toán | JWT decoder không xác thực được chữ ký hoặc algorithm không được chấp nhận. | Opaque token không được Resource Server kiểm tra chữ ký kiểu JWT. |
| Issuer không tin cậy | Claim `iss` không phù hợp issuer đã cấu hình. | Kiểm tra theo hợp đồng issuer/introspection và chính sách API. |
| Sai audience | `aud` không hướng tới API, **nếu API cấu hình kiểm tra audience**. | Đánh giá thông tin token và resource phù hợp theo dữ liệu introspection/provider. |
| Chưa có hiệu lực | `nbf` hoặc điều kiện thời gian liên quan không hợp lệ. | Phụ thuộc trạng thái introspection và quy tắc provider. |
| Thu hồi token | JWT offline validation không tự phát hiện mọi trường hợp thu hồi nếu không có cơ chế bổ sung. | Introspection thường phản ánh trạng thái không active khi provider hỗ trợ. |
| Dùng sai loại token | Ví dụ gửi **OIDC ID token** cho API kiểm tra đúng audience/token type. | Cần áp dụng chính sách token type của provider. |

**JWT có chữ ký hợp lệ chưa chắc được phép gọi API.** ID token của OIDC có thể được cùng issuer ký nhưng dành cho OIDC Client; API phải xác minh audience, access-token profile và những chính sách mà tài nguyên này yêu cầu. Chỉ bật JWT decoder mà không thẩm định token dành cho API có thể gây chấp nhận nhầm token.

### Cú pháp request bị lỗi là một nhánh riêng

Ví dụ header:

```http
Authorization: Bearer
```

không cung cấp chuỗi Bearer hợp lệ. Cũng có thể client truyền token đồng thời qua nhiều phương thức trong cấu hình cho phép nhận nhiều nguồn. Những trường hợp này xảy ra ở bước **BearerTokenResolver** và có thể phát sinh `OAuth2AuthenticationException` trước khi JWT decoder/introspection chạy.

RFC 6750 phân biệt các mã:

| Mã Bearer error | Ý nghĩa | HTTP status thường dùng |
| --- | --- | --- |
| `invalid_token` | Token hết hạn, bị thu hồi, sai/không được chấp nhận. | **401** |
| `invalid_request` | Request Bearer sai cấu trúc, lặp tham số, dùng nhiều cách truyền token... | **400** |
| `insufficient_scope` | Token hợp lệ nhưng quyền không đáp ứng tài nguyên. | **403** |

**Không nên khẳng định mọi header Bearer sai định dạng đều trả cùng một mã.** Kết quả phụ thuộc lỗi cụ thể và cách `DefaultBearerTokenResolver`/custom resolver biểu diễn lỗi. Hãy quan sát cả status và `WWW-Authenticate`.

## 5. Spring Security xử lý từng nhánh như thế nào?

Trong cấu hình `oauth2ResourceServer()`, một thành phần quan trọng là `BearerTokenAuthenticationFilter`. Filter dùng `BearerTokenResolver` (mặc định thường là `DefaultBearerTokenResolver`) để tìm token.

### Nhánh A: Không có Bearer token

1. Resolver trả `null` vì không phát hiện Bearer credential.
2. `BearerTokenAuthenticationFilter` **không gọi JWT decoder hay introspection**; nó cho request tiếp tục đi qua filter chain.
3. Nếu endpoint yêu cầu authenticated user, bước authorization sẽ từ chối request anonymous.
4. `ExceptionTranslationFilter` dẫn đến authentication entry point thích hợp; trong Bearer Resource Server, `BearerTokenAuthenticationEntryPoint` thường trả **401** với Bearer challenge không có `invalid_token`.

Vì không có credential nào được gửi, **không thể kết luận JWT đã hết hạn hay chữ ký sai**. Token chưa từng được đem ra kiểm tra.

### Nhánh B: Có token nhưng xác thực thất bại

1. Resolver lấy được Bearer token.
2. Filter đưa token tới `AuthenticationManager` và authentication provider.
3. Với JWT, `JwtDecoder` kiểm tra chữ ký, thời gian, issuer và validators đã cấu hình. Với opaque token, Resource Server dùng `OpaqueTokenIntrospector` hoặc introspection tương ứng.
4. Nếu credential bị từ chối, authentication thất bại; failure handler/entry point tạo Bearer challenge, thường **401** với `invalid_token`.

Nếu resolver tự ném exception do request sai, bước xác thực JWT có thể chưa xảy ra; lúc đó response theo `BearerTokenError` mà resolver phát sinh.

### Nhánh C: Xác thực thành công nhưng thiếu quyền

1. Access token hợp lệ tạo `Authentication` thích hợp trong `SecurityContext`.
2. Endpoint đòi authority hoặc điều kiện phân quyền mà Authentication không đáp ứng.
3. Access denied handler xử lý. `BearerTokenAccessDeniedHandler` có thể tạo **403** với `insufficient_scope` đối với Bearer authentication phù hợp.

Thứ tự quan trọng: **trích xuất credential → xác thực token → phân quyền endpoint → phân quyền dữ liệu/nghiệp vụ**.

## 6. Ví dụ Spring Boot Resource Server

Ứng dụng dùng JWT access token có thể cấu hình issuer như sau:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
```

Quy tắc endpoint:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                            .hasAuthority("SCOPE_reports:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Ví dụ dùng các class Spring Security như `HttpSecurity`, `SecurityFilterChain`, `HttpMethod` và `Customizer`. Trong trường hợp phổ biến, claim `scope`/`scp` của JWT được ánh xạ thành authority có tiền tố `SCOPE_`. API yêu cầu `SCOPE_reports:read` nghĩa là token cần scope `reports:read` theo cơ chế mapping được cấu hình.

**Cấu hình `issuer-uri` một mình không phải bằng chứng token có audience phù hợp với API.** Tùy phiên bản Spring Security/Boot và provider, cần bổ sung audience validator và các kiểm tra profile/loại access token cần thiết. Việc kiểm tra quyền còn bao gồm ownership, tenant và chính sách nghiệp vụ.

Với opaque token, cấu hình Resource Server theo `opaquetoken` và cung cấp introspection URI/client credentials theo Authorization Server. Các nhánh “thiếu Bearer token” và “token bị từ chối” vẫn có ý nghĩa tương tự.

### Trường hợp 1: Không gửi token

```bash
curl -i https://api.example.test/api/reports/2026
```

Phản hồi điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

### Trường hợp 2: Gửi token giả/không hợp lệ

```bash
curl -i \
  -H 'Authorization: Bearer definitely-not-a-valid-token' \
  https://api.example.test/api/reports/2026
```

Với JWT decoder, token giả không qua xác thực:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

### Trường hợp 3: Token hợp lệ nhưng thiếu `reports:read`

```bash
curl -i \
  -H 'Authorization: Bearer <VALID_ACCESS_TOKEN_WITHOUT_REPORTS_READ>' \
  https://api.example.test/api/reports/2026
```

Phản hồi điển hình:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Header có thể được bổ sung các tham số như `scope` tùy handler; không nên phụ thuộc việc mọi triển khai luôn liệt kê đủ scope còn thiếu.

### Trường hợp 4: Token hợp lệ và đủ scope

```bash
curl -i \
  -H 'Authorization: Bearer <VALID_ACCESS_TOKEN_WITH_REPORTS_READ>' \
  https://api.example.test/api/reports/2026
```

Sau khi kiểm tra thêm quyền dữ liệu và điều kiện nghiệp vụ, endpoint có thể trả **200 OK**. Các giá trị trong dấu ngoặc nhọn là placeholder, không phải token dùng được. Trong môi trường thử nghiệm phải sử dụng token do Authorization Server hợp lệ cấp.

### Tình huống đặc biệt: `permitAll()` nhưng Bearer token sai vẫn bị 401

Với cùng filter chain ở trên, gọi `GET /api/public` **không kèm token** có thể trả 200 do `permitAll()`. Nhưng nếu HTTP client tự gắn header `Authorization: Bearer <expired-token>` vào chính endpoint công khai đó, `BearerTokenAuthenticationFilter` vẫn cố xác thực credential và có thể trả **401** trước khi request đến bước authorization.

**`permitAll()` không tự vô hiệu hóa Bearer authentication filter.** Nếu một khu vực API thực sự cần bỏ qua xử lý Bearer hoàn toàn, phải thiết kế các `SecurityFilterChain`/matcher phù hợp. Đây là lý do nhiều HTTP client tự động gắn token hết hạn vào mọi request có thể gây lỗi bất ngờ trên route công khai.

## 7. Đọc header `WWW-Authenticate`

Đối với Bearer scheme, `WWW-Authenticate` là tín hiệu quan trọng để biết loại tình huống:

| Header minh họa | Ý nghĩa |
| --- | --- |
| `WWW-Authenticate: Bearer` | Yêu cầu client cung cấp Bearer credential; thường thấy khi chưa có token. |
| `WWW-Authenticate: Bearer realm="reports-api"` | Bearer challenge có định danh protection space. |
| `WWW-Authenticate: Bearer error="invalid_token"` | Có token/credential nhưng token không được chấp nhận. |
| `WWW-Authenticate: Bearer error="invalid_request"` | Yêu cầu truyền Bearer credential sai cấu trúc. |
| `WWW-Authenticate: Bearer error="insufficient_scope"` | Token được xác thực nhưng quyền chưa đủ. |

Server có thể thêm `error_description`, `error_uri` hoặc `scope` theo trường hợp. Body JSON **không phải yêu cầu bắt buộc** của Bearer challenge; một API có thể trả body trống, body lỗi tùy chỉnh hoặc để gateway thay đổi phản hồi. Vì vậy, client không nên phân loại lỗi chỉ dựa vào trường JSON `message`.

## 8. Cách xử lý ở phía client

### 8.1. Không có token

Nếu endpoint yêu cầu xác thực, client phải lấy access token bằng luồng OAuth 2.0 phù hợp (chẳng hạn Authorization Code + PKCE cho ứng dụng có người dùng, hoặc Client Credentials cho service-to-service khi được phép). Sau đó gửi token qua:

```http
Authorization: Bearer <access_token>
```

Nếu client khẳng định đã gửi token mà API phản hồi giống trường hợp thiếu token, kiểm tra tên header, đúng URL, đường đi qua reverse proxy/gateway và liệu header `Authorization` có bị loại bỏ hay ghi đè.

### 8.2. Có token nhưng `invalid_token`

- Nếu token **hết hạn**, sử dụng refresh token flow nếu client được cấp refresh token và được phép refresh; thử lại một cách có giới hạn.
- Nếu không thể refresh, thực hiện lại luồng lấy token/đăng nhập phù hợp.
- Nếu **sai audience, issuer, hoặc loại token**, cần sửa cấu hình và luồng cấp/chọn token. Refresh nhiều lần với cùng cấu hình sai sẽ không có tác dụng.
- Nếu token đã bị thu hồi, phải lấy credential mới theo chính sách của nhà phát hành.

Tránh vòng lặp `401 → refresh → gọi lại → 401`. Khi nhiều request đồng thời gặp lỗi hết hạn, nên phối hợp refresh để hạn chế nhiều lần refresh cùng lúc, nhất là khi sử dụng refresh token rotation.

### 8.3. Token hợp lệ nhưng `insufficient_scope`

Lỗi này là **phân quyền**, không phải token đã hết hạn. Xác định endpoint yêu cầu scope/authority nào, token đã được cấp gì và có các điều kiện vai trò/tenant/ownership nào khác. Việc refresh token hiện tại không tự cấp thêm quyền; có thể cần yêu cầu thêm scope hoặc thay đổi quyền qua quy trình hợp lệ.

Không nên xử lý `401` bằng cách tắt kiểm tra chữ ký, issuer, expiry, audience hay nới lỏng bảo vệ API.

## 9. Chẩn đoán trong Spring Security

| Hiện tượng | Cần kiểm tra |
| --- | --- |
| Không có `Authorization`, endpoint yêu cầu đăng nhập trả 401 | Quy tắc `authenticated()`/scope có áp dụng không? Có Bearer challenge không? |
| Client đã gửi token nhưng phản hồi giống thiếu token | Header đã tới Resource Server chưa? Có nhầm header, sai scheme, gateway xóa header không? |
| JWT liên tục nhận `invalid_token` | Issuer, JWKS, chữ ký, `exp`, `nbf`, audience validator và token type/profile. |
| Opaque token liên tục bị từ chối | Introspection endpoint/credentials, kết quả `active` và các thuộc tính token. |
| ID token gọi API vẫn được chấp nhận | Kiểm tra thiếu audience validation hoặc thiếu ràng buộc access-token profile. |
| Token đúng nhưng trả 403 | Mapping `scope`/`scp` sang `SCOPE_`, `hasAuthority()`, method security và quyền nghiệp vụ. |
| `permitAll()` vẫn trả 401 khi có token cũ | Bearer filter đang kiểm tra token được gắn vào request trước bước authorization. |
| 401 nhưng không thấy `WWW-Authenticate` | Cấu hình entry point, response handler, API gateway/reverse proxy. |

Có thể bật log phục vụ chẩn đoán trong môi trường phát triển:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Không in nguyên access token, ID token hay refresh token vào log. Để quan sát lỗi, ưu tiên request ID, tên endpoint, loại lỗi, thời điểm và các thông tin kỹ thuật phi nhạy cảm. Quy định mức log và thời gian lưu giữ phù hợp với chính sách vận hành.

## 10. Những nhầm lẫn thường gặp

**“Không có token tức là token invalid.”** Sai: chưa có credential thì chưa có gì được xác thực. Với protected endpoint, thường nhận 401 challenge **không có** `invalid_token`.

**“Hễ 401 là phải đăng nhập lại.”** Chưa đủ: cần phân biệt thiếu header, token hết hạn, sai audience/issuer hoặc gateway không chuyển tiếp header.

**“Có header Authorization tức là Bearer resolver đã nhận token.”** Sai: `Authorization: Basic ...`, header sai định dạng hoặc cơ chế không được cấu hình có thể không tạo ra một Bearer credential hợp lệ.

**“Thiếu scope là invalid_token.”** Sai: access token đã xác thực thành công nhưng thiếu quyền thường dẫn tới **403 insufficient_scope**.

**“`permitAll()` sẽ luôn bỏ qua token hỏng được gắn kèm.”** Sai: trong filter chain xử lý Bearer, token hỏng có thể bị từ chối trước bước authorization.

**“Cùng là JWT và cùng issuer thì ID token dùng được để gọi API.”** Sai: ID token dành cho OIDC Client, còn access token hướng tới Resource Server. API cần kiểm tra token phù hợp đối tượng nhận và mục đích.

## 11. Bài tập phân loại request

| Request / điều kiện | Kết quả điển hình |
| --- | --- |
| `GET /api/reports` không có `Authorization` | **401**, Bearer challenge không có mã lỗi. |
| `GET /api/reports` với JWT hết hạn | **401 invalid_token**. |
| `GET /api/reports` với JWT còn hạn nhưng `iss` không được tin cậy | **401 invalid_token**. |
| `GET /api/reports` với token hợp lệ nhưng thiếu `reports:read` | **403 insufficient_scope**. |
| `GET /api/public` không có token, endpoint `permitAll()` | Có thể thành công. |
| `GET /api/public` với Bearer token lỗi, cùng filter chain | Có thể **401** trước bước authorization. |
| Gửi token vào `X-Access-Token` nhưng API chỉ đọc `Authorization` | Thường được xem là **không có Bearer token**. |
| Gửi Bearer credential bị sai cấu trúc | Có thể bị từ chối bởi resolver với `invalid_token` hoặc `invalid_request` tùy lỗi. |

## 12. Nguyên tắc ghi nhớ

Với API dùng Spring Security OAuth 2.0 Resource Server, nên đọc request theo bốn câu hỏi:

1. **Có Bearer token được resolver nhận diện không?** Nếu không, request chưa mang Bearer credential; protected endpoint thường trả 401 challenge.
2. **Token có qua authentication không?** Nếu không, thường trả 401 với `invalid_token`, hoặc lỗi cấu trúc request tương ứng.
3. **Principal/token hợp lệ có đủ quyền không?** Nếu thiếu scope/authority thì thường là 403.
4. **Người gọi có được phép truy cập chính dữ liệu đó không?** Scope chỉ là một lớp; quyền tenant/ownership và chính sách nghiệp vụ vẫn phải được kiểm tra.

**Điểm mấu chốt:** *không có token* nghĩa là Resource Server chưa nhận được credential để xác thực; *có token nhưng không hợp lệ* nghĩa là credential đã được gửi nhưng bị từ chối. Chúng có thể cùng trả HTTP 401, song khác nhau về giai đoạn xử lý, Bearer challenge và cách phía client khắc phục.
