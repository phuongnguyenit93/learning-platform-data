# Bearer token và rủi ro khi token bị đánh cắp

Bearer token là một loại thông tin xác thực mà người sở hữu token có thể dùng để chứng minh quyền truy cập với API. Trong request, client thường gửi token trong header `Authorization` theo dạng `Bearer <token>`. Cách dùng này thuận tiện cho web app, mobile app, service-to-service và API gateway, nhưng có một rủi ro cốt lõi: **bất kỳ ai lấy được bearer token hợp lệ đều có thể sử dụng token đó trong phạm vi quyền và thời hạn của nó**.

Bearer token không tự chứng minh người gửi là chủ tài khoản ban đầu. Server thường chỉ xác minh token hợp lệ và còn hiệu lực. Nếu token bị sao chép từ trình duyệt, thiết bị, log, proxy hoặc hệ thống giám sát, kẻ lấy được token có thể phát lại request như người dùng hợp lệ. Vì vậy, bảo mật API cần bảo vệ token trong toàn bộ vòng đời: phát hành, lưu trữ, truyền tải, xác minh, gia hạn, thu hồi và giám sát.

## 1. Bearer token là gì?

Bearer token là credential theo mô hình bearer: quyền sử dụng token thuộc về bên đang nắm giữ nó. Client không cần ký từng request bằng một khóa riêng để chứng minh mình là chủ token. Điều này làm cho tích hợp đơn giản, nhưng cũng khiến việc bảo vệ bí mật token trở thành yêu cầu quan trọng.

Một request thường có dạng:

```http
GET /api/v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...<access-token>
Accept: application/json
```

Header `Authorization` mang access token. Server xác minh token, tạo ngữ cảnh xác thực và tiếp tục kiểm tra quyền đối với endpoint, method, object cùng các điều kiện nghiệp vụ.

Không nên gửi bearer token trong query string như:

```http
GET /api/v1/orders?access_token=<token>
```

URL thường xuất hiện trong browser history, access log, proxy log, analytics, hệ thống giám sát và đôi khi trong header `Referer`. HTTPS bảo vệ token trên đường truyền giữa các điểm kết nối, nhưng không ngăn URL bị ghi lại ở các hệ thống đầu cuối. Hãy dùng `Authorization` header theo hợp đồng API và cấu hình mọi lớp trung gian để không ghi giá trị token.

## 2. Access token và refresh token

Trong nhiều hệ thống OAuth 2.0 hoặc OpenID Connect, client có thể nhận hai loại token với mục đích khác nhau:

| Loại | Mục đích | Đặc điểm cần bảo vệ |
|---|---|---|
| Access token | Gọi resource server/API | Thường có thời hạn ngắn, quyền và audience giới hạn |
| Refresh token | Xin access token mới khi access token hết hạn | Có vòng đời dài hơn, phải lưu trữ kỹ và có cơ chế rotation/revocation phù hợp |

Access token được gửi tới API để truy cập tài nguyên. Refresh token thường chỉ được gửi tới authorization server/token endpoint; không gửi refresh token đến resource API. Nếu refresh token bị đánh cắp, kẻ tấn công có thể liên tục xin access token mới cho đến khi token bị thu hồi, hết hạn hoặc cơ chế phát hiện reuse chặn lại.

Không phải mọi hệ thống đều dùng refresh token. Một số ứng dụng yêu cầu người dùng đăng nhập lại sau khi access token hết hạn; một số dùng session server-side hoặc backend-for-frontend (BFF) để giữ token phía server. Lựa chọn phụ thuộc loại client, mức độ nhạy cảm và yêu cầu trải nghiệm.

## 3. Token có thể là opaque token hoặc JWT

Bearer mô tả cách sử dụng credential, không phải định dạng token. Hai dạng thường gặp là opaque token và JWT.

### Opaque token

Opaque token là chuỗi không mang cấu trúc claim có thể đọc trực tiếp theo một định dạng công khai. Resource server thường kiểm tra token qua introspection endpoint hoặc một cơ chế tra cứu đáng tin cậy. Authorization server có thể thu hồi token tập trung và resource server nhận trạng thái mới theo chính sách cache.

Ưu điểm là thông tin và trạng thái token được quản lý phía server; client không cần biết nội dung token. Đổi lại, introspection có thể thêm độ trễ và phụ thuộc vào khả năng sẵn sàng của authorization server hoặc cache.

### JWT access token

JWT (JSON Web Token) là một định dạng biểu diễn claim. JWT thường có ba phần Base64URL ngăn bởi dấu chấm: header, payload và signature. Payload có thể đọc được sau khi giải mã Base64URL; chữ ký giúp xác minh tính toàn vẹn và nguồn phát hành theo thuật toán, khóa đã cấu hình. JWT được ký không đồng nghĩa với được mã hóa.

Ví dụ payload minh họa:

```json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.update",
  "iat": 1795000000,
  "exp": 1795000900
}
```

Các claim thường có ý nghĩa như sau:

| Claim | Ý nghĩa | Kiểm tra cần thiết |
|---|---|---|
| `iss` | Issuer phát hành token | Phải khớp issuer được tin cậy |
| `sub` | Subject, chủ thể mà token đại diện | Ánh xạ tới danh tính theo quy ước của hệ thống |
| `aud` | Audience, đối tượng nhận token | Phải chứa API/resource server hiện tại |
| `exp` | Thời điểm hết hạn | Từ chối token đã hết hạn |
| `nbf` | Thời điểm token bắt đầu có hiệu lực | Từ chối token chưa đến thời điểm hiệu lực |
| `iat` | Thời điểm token được phát hành | Có thể dùng để kiểm tra chính sách tuổi token |
| `scope` hoặc `scp` | Phạm vi quyền được cấp | Chuyển thành quyền chức năng theo chính sách API |
| `jti` | Định danh token | Chỉ hữu ích cho chống phát lại/thu hồi khi hệ thống có cơ chế lưu và kiểm tra tương ứng |

Không được tin payload chỉ vì có thể giải mã JWT. Resource server phải xác minh chữ ký bằng khóa và thuật toán được cấu hình, kiểm tra issuer, audience, thời hạn và các điều kiện cần thiết khác. Không chấp nhận thuật toán hoặc khóa do token tự chọn một cách tùy tiện. Với JWT ký, không đặt mật khẩu, secret hoặc dữ liệu cá nhân nhạy cảm trong payload vì chữ ký không che giấu nội dung.

JWT giúp resource server xác minh token cục bộ mà không cần tra cứu mỗi request, nhưng thông tin trong token có thể tiếp tục được chấp nhận đến khi hết hạn nếu không có cơ chế thu hồi hoặc kiểm tra trạng thái bổ sung. Opaque token và JWT đều có thể được dùng làm bearer token; định dạng không làm thay đổi nguyên tắc rằng người lấy được token có thể sử dụng nó.

## 4. Vì sao token bị đánh cắp có thể dẫn đến chiếm quyền?

Khi server nhận bearer token hợp lệ, server thường không thể biết người gửi là client gốc hay người vừa sao chép token. Nếu token còn hiệu lực, đúng audience và có scope phù hợp, request có thể được chấp nhận.

Ví dụ, người dùng đăng nhập vào ứng dụng và nhận access token có quyền `orders.read`. Kẻ tấn công lấy được token đó rồi gửi:

```http
GET /api/v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <stolen-access-token>
Accept: application/json
```

Nếu token còn hiệu lực và API không có biện pháp bổ sung để ràng buộc token với client hoặc phiên cụ thể, server có thể xử lý request như request của người dùng. Nếu token có quyền rộng như `admin`, tác động có thể nghiêm trọng hơn nhiều.

Rủi ro phụ thuộc vào phạm vi quyền, thời hạn token, khả năng truy cập dữ liệu và hành động được token cho phép. Một access token chỉ có `orders.read` với audience `orders-api` gây tác động khác với token quản trị có quyền truy cập nhiều service. Vì vậy, giảm thiểu tác động khi token bị lộ cần kết hợp bảo vệ bí mật với giới hạn quyền và thời gian sử dụng.

## 5. Những đường token có thể bị lộ

Token có thể bị lộ ở nhiều lớp của hệ thống, không chỉ trong lúc truyền qua mạng.

### Lưu trữ phía client

- Ứng dụng web lưu token trong `localStorage` hoặc `sessionStorage` có thể bị lộ token nếu có lỗ hổng XSS và mã độc chạy được trong origin đó.
- Cookie không có `HttpOnly` có thể bị JavaScript đọc. Cookie thiếu `Secure` có nguy cơ bị gửi qua kết nối không an toàn trong một số cấu hình.
- Mobile app lưu token trong file, database hoặc vùng lưu trữ không được bảo vệ có thể làm token bị lấy khi thiết bị bị root/jailbreak, malware kiểm soát hoặc bản sao lưu bị lộ.
- Desktop app, extension hoặc môi trường phát triển có thể ghi token vào file cấu hình, clipboard, crash dump hoặc lịch sử lệnh.

### Log và hệ thống quan sát

Reverse proxy, API gateway, web server, APM agent, distributed tracing, log ứng dụng và hệ thống phân tích có thể ghi toàn bộ header request nếu cấu hình không lọc. Khi `Authorization` bị ghi vào log, nhiều người hoặc hệ thống có quyền đọc log có thể vô tình có khả năng sử dụng token.

Không ghi token thô vào log, trace, metric label, exception message hoặc audit event. Nếu cần tương quan sự kiện, dùng request ID hoặc dấu vân tay token đã được băm bằng cơ chế phù hợp; không dùng giá trị token thật làm định danh log.

### Thiết bị và phiên người dùng bị xâm nhập

Malware, thiết bị dùng chung, trình duyệt có extension độc hại, máy tính đã bị chiếm quyền hoặc tài khoản hệ điều hành bị lộ có thể làm lộ token trong bộ nhớ hay kho lưu trữ. Đăng xuất trên giao diện không bảo đảm token đã bị thu hồi nếu server vẫn chấp nhận token cũ.

### Lỗi truyền tải và cấu hình

- Gửi token qua HTTP thay vì HTTPS có thể cho phép bên thứ ba trên đường truyền quan sát hoặc sửa request.
- Cấu hình TLS sai, proxy không đáng tin hoặc terminate TLS không đúng ranh giới có thể làm lộ token tại điểm trung gian.
- Đặt token trong URL, redirect hoặc liên kết chia sẻ làm tăng nơi token có thể xuất hiện.
- Cấu hình CORS quá rộng không trực tiếp làm lộ mọi bearer token, nhưng có thể làm tăng tác động của XSS hoặc một ứng dụng web độc hại khi kết hợp với cookie/credential và chính sách trình duyệt sai.

### Sao chép qua con người và quy trình vận hành

Token có thể bị dán vào ticket, chat, email, ảnh chụp màn hình, tài liệu hướng dẫn hoặc ví dụ code. Credential test được chia sẻ lâu dài cũng có thể trở thành điểm xâm nhập. Hãy coi token là bí mật tương đương thông tin xác thực, không đưa token thật vào tài liệu hoặc kênh hỗ trợ.

## 6. Giảm khả năng token bị đánh cắp

Không có một biện pháp đơn lẻ bảo vệ mọi loại client. Hãy kết hợp bảo mật truyền tải, lưu trữ, trình duyệt, thiết bị và vận hành.

### Bắt buộc bảo vệ đường truyền

Chỉ gửi access token qua HTTPS với TLS được cấu hình đúng. Không cho phép client hạ cấp sang HTTP đối với endpoint có xác thực. Với web, dùng HSTS ở domain phù hợp để trình duyệt ưu tiên HTTPS. Nếu TLS kết thúc ở load balancer hoặc gateway, bảo vệ cả chặng từ gateway tới service theo mô hình tin cậy của hạ tầng.

### Lưu token theo loại client

**Ứng dụng server-side hoặc BFF:** giữ access token và refresh token ở phía server, client chỉ giữ session cookie. Cookie nên có `Secure`, `HttpOnly`, `SameSite` phù hợp và phạm vi `Domain`/`Path` hẹp. Vì trình duyệt tự gửi cookie, cần thiết kế phòng chống CSRF cho các request thay đổi trạng thái.

**Ứng dụng trình duyệt gọi API trực tiếp:** token trong bộ nhớ giảm thời gian tồn tại trong kho lưu trữ lâu dài nhưng vẫn có thể bị lấy qua XSS đang chạy. `localStorage` tồn tại qua lần tải lại và dễ truy cập từ JavaScript, nên một lỗ hổng XSS có thể đọc token. Không có lựa chọn lưu trữ phía client nào thay thế được việc ngăn XSS bằng output encoding, Content Security Policy phù hợp, dependency hygiene và kiểm soát script.

**Ứng dụng di động:** dùng cơ chế lưu trữ bảo mật của nền tảng như Android Keystore hoặc iOS Keychain, giới hạn quyền truy cập và tránh lưu token trong log, file cấu hình hay backup không được bảo vệ. Bảo vệ thiết bị và phát hiện rủi ro runtime có thể bổ sung nhưng không nên được xem là bằng chứng tuyệt đối rằng thiết bị sạch.

**Service-to-service:** lưu credential trong secret manager hoặc hệ thống quản lý khóa, cấp quyền tối thiểu cho service account và tránh nhúng token dài hạn vào source code, image container hoặc biến môi trường bị ghi lại trong diagnostic dump.

### Giảm quyền của token

Access token nên có:

- Audience cụ thể cho resource server cần truy cập.
- Scope hoặc quyền tối thiểu theo chức năng cần dùng.
- Thời hạn ngắn phù hợp với rủi ro và trải nghiệm.
- Subject đại diện rõ ràng cho người dùng hoặc service account.
- Các claim cần thiết cho quyết định truy cập, tránh nhồi dữ liệu cá nhân hoặc thông tin không cần thiết.

Không cấp một token có quyền quản trị toàn hệ thống cho ứng dụng chỉ cần đọc một loại tài nguyên. Nếu một ứng dụng cần gọi nhiều API, cân nhắc token riêng theo audience hoặc token exchange để mỗi service chỉ nhận quyền cần thiết.

### Làm giảm thời gian token có thể bị lạm dụng

Access token có thời hạn ngắn giúp giới hạn khoảng thời gian sử dụng token bị lộ. Tuy nhiên, thời hạn ngắn không tự thu hồi token ngay lập tức và không giải quyết được refresh token bị đánh cắp. Cần cân bằng giữa thời hạn, độ nhạy cảm của API, khả năng refresh và nhu cầu vận hành.

## 7. Xác minh bearer token tại resource server

Resource server phải kiểm tra token trước khi xử lý nghiệp vụ. Với JWT, quy trình thường bao gồm:

1. Parse token theo định dạng và kích thước được hỗ trợ; từ chối token sai cấu trúc.
2. Xác minh chữ ký bằng khóa tin cậy và thuật toán được cấu hình cố định.
3. Kiểm tra `iss` đúng authorization server đã tin cậy.
4. Kiểm tra `aud` có chứa API hiện tại.
5. Kiểm tra `exp`, `nbf` và độ lệch đồng hồ theo chính sách.
6. Kiểm tra loại token và các claim bắt buộc theo profile của hệ thống.
7. Ánh xạ scope/role thành quyền chức năng, sau đó kiểm tra quyền trên object và thuộc tính trong service.

Với opaque token, resource server thường gọi introspection endpoint qua kết nối được xác thực để kiểm tra token còn active và lấy metadata/quyền cần thiết. Nếu cache kết quả introspection, cần đặt thời gian cache phù hợp với yêu cầu thu hồi; cache quá lâu có thể khiến token đã bị thu hồi vẫn được chấp nhận trong khoảng thời gian đó.

Không chấp nhận token chỉ vì chữ ký hợp lệ. Một JWT phát hành cho `billing-api` không nên được chấp nhận ở `orders-api` nếu audience không khớp. Không tự coi mọi claim `role` hoặc `admin` trong payload là quyền nếu issuer, audience, schema và cách ánh xạ claim chưa được xác định rõ.

## 8. Ví dụ xác minh JWT với Spring Security

Spring Security Resource Server hỗ trợ xác minh Bearer JWT thông qua `oauth2ResourceServer().jwt()`. Cấu hình issuer cho phép framework lấy metadata và khóa công khai từ authorization server theo cơ chế được hỗ trợ.

Ví dụ cấu hình cơ bản:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
```

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Trong môi trường thật, ngoài chữ ký, issuer và thời hạn, resource server cần xác minh audience. Ví dụ validator bổ sung audience `orders-api`:

```java
@Bean
JwtDecoder jwtDecoder(
        @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}") String issuer) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Required audience is missing", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));

    return decoder;
}
```

Đây là ví dụ minh họa; cần các import Spring Security OAuth2 phù hợp với phiên bản dự án. `NimbusJwtDecoder.withIssuerLocation` dùng metadata/JWK endpoint của issuer để cấu hình decoder; issuer phải là địa chỉ được tin cậy. Ứng dụng cũng cần kiểm tra token type, thuật toán, claim và chính sách scope theo authorization server thực tế.

Sau xác thực, quyền chức năng vẫn phải được kiểm tra. Ví dụ:

```java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {}
```

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
@GetMapping("/api/v1/orders/{orderId}")
public OrderResponse getOrder(@PathVariable UUID orderId) {
    return orderService.getVisibleOrder(orderId);
}
```

`SCOPE_orders.read` chỉ là quyền chức năng. `getVisibleOrder` vẫn phải xác minh người dùng hoặc service account được phép xem đúng `orderId`, tenant và các trường được trả về. Xác thực token không thay thế authorization ở cấp object/property.

## 9. Refresh token rotation và thu hồi token

Khi dùng refresh token, authorization server có thể cấp refresh token mới mỗi lần sử dụng và vô hiệu hóa token cũ. Cơ chế này gọi là refresh token rotation. Nếu token cũ được sử dụng lại sau khi đã rotate, server có thể coi đó là dấu hiệu token bị sao chép và thu hồi cả token family hoặc yêu cầu xác thực lại theo chính sách.

Một thiết kế refresh token cần xác định:

- Token có gắn với client, user, device hoặc session cụ thể không?
- Mỗi lần refresh có cấp token mới và vô hiệu hóa token cũ không?
- Server lưu trạng thái token family và phát hiện reuse như thế nào?
- Logout, đổi mật khẩu, khóa tài khoản hoặc phát hiện xâm nhập có thu hồi refresh token không?
- Token hết hạn do không hoạt động và thời hạn tối đa của session được quy định ra sao?

Thu hồi JWT access token cần cân nhắc vì resource server có thể xác minh JWT cục bộ mà không hỏi authorization server. Các lựa chọn gồm access token ngắn hạn, denylist theo `jti` hoặc token identifier, kiểm tra token version/session state, introspection hoặc cơ chế thu hồi tập trung. Mỗi lựa chọn có chi phí về độ trễ, khả năng mở rộng và mức độ tức thời của việc thu hồi.

Logout ở client chỉ xóa token khỏi nơi lưu trữ của client. Nếu token đã bị sao chép, bản sao đó vẫn có thể dùng được cho đến khi hết hạn hoặc bị server từ chối. Vì vậy, logout nhạy cảm nên kết hợp thu hồi refresh token/session và chính sách giới hạn tuổi access token.

## 10. Sender-constrained token: giảm giá trị của token bị sao chép

Bearer token có thể được sử dụng bởi bất kỳ ai nắm giữ nó. Sender-constrained token bổ sung bằng chứng rằng request được gửi bởi client đang sở hữu một khóa hoặc chứng thư đã được ràng buộc với token.

Hai cơ chế thường gặp:

- **Mutual TLS (mTLS):** client xác thực với server bằng certificate; token có thể được ràng buộc với certificate của client. Kẻ chỉ sao chép token nhưng không có private key phù hợp sẽ khó sử dụng token ở một kết nối khác.
- **DPoP (Demonstrating Proof of Possession):** client tạo proof có chữ ký bằng khóa riêng cho request, thường gắn với method, URI, thời điểm và token. Resource server kiểm tra proof, khóa và các điều kiện chống phát lại theo profile DPoP.

Các cơ chế này làm tăng độ phức tạp triển khai và vận hành khóa, nhưng có thể giảm tác động của token bị sao chép đơn thuần. Chúng không bảo vệ hoàn toàn khi thiết bị hoặc tiến trình đang giữ private key bị chiếm quyền. Nếu kẻ tấn công kiểm soát được client đang hoạt động, họ có thể yêu cầu client ký hoặc gửi request thay mặt mình.

## 11. Xử lý khi nghi ngờ token bị lộ

Khi phát hiện token xuất hiện trong log, ticket, chat, thiết bị thất lạc hoặc request bất thường, hãy xử lý như một credential đã bị xâm phạm:

1. Xác định loại token, issuer, subject, audience, scope, thời điểm phát hành và thời hạn còn lại bằng nguồn dữ liệu an toàn. Không sao chép token vào công cụ phân tích hoặc kênh trao đổi thông thường.
2. Thu hồi refresh token/session liên quan và vô hiệu hóa access token theo cơ chế của hệ thống. Nếu token là JWT tự xác minh, đánh giá denylist, introspection hoặc biện pháp khẩn cấp khác.
3. Nếu token bị ghi vào log hoặc ticket, hạn chế quyền truy cập, xóa/che dữ liệu theo quy trình lưu trữ và xử lý bản sao ở các hệ thống liên quan.
4. Kiểm tra audit log theo subject, client, audience, IP, user agent, route và thời điểm; tìm request bất thường, truy cập object ngoài phạm vi hoặc hành động nhạy cảm.
5. Đánh giá dữ liệu đã bị đọc, thay đổi hoặc xuất ra; thực hiện quy trình ứng phó sự cố và thông báo theo chính sách tổ chức.
6. Cấp credential mới sau khi xử lý nguyên nhân lộ token; yêu cầu người dùng hoặc service xác thực lại khi cần.
7. Sửa điểm rò rỉ như logging header, XSS, lưu trữ không an toàn, proxy cấu hình sai hoặc quy trình chia sẻ secret.

Không chỉ xóa token khỏi giao diện rồi xem sự cố đã kết thúc. Cần xác minh token cũ thực sự không còn được chấp nhận ở các resource server liên quan và kiểm tra cả refresh token có thể dùng để cấp token mới.

## 12. Giám sát việc sử dụng token

Log và telemetry nên giúp phát hiện bất thường mà không lưu bí mật. Có thể ghi nhận:

- Subject hoặc service identity ở dạng định danh phù hợp.
- Client ID, issuer, audience và scope đã được ánh xạ.
- Route template, method, kết quả xác thực/phân quyền và status code.
- Request ID, thời điểm, nguồn mạng theo chính sách tin cậy và dấu hiệu thiết bị phù hợp.
- Số lần token bị từ chối, refresh thất bại, reuse refresh token hoặc hoạt động khác thường.

Không ghi raw bearer token, refresh token, secret, mật khẩu hoặc toàn bộ header `Authorization`. Nếu cần phát hiện cùng token xuất hiện ở nhiều nơi, dùng fingerprint được tạo bằng HMAC với khóa giám sát riêng và kiểm soát quyền truy cập. Không đưa fingerprint nhạy cảm vào metric label có cardinality cao.

Các dấu hiệu cần điều tra có thể gồm cùng một session xuất hiện từ hai vùng địa lý không thể di chuyển hợp lý trong khoảng thời gian ngắn, số lượng request tăng đột biến, nhiều lần thử token không hợp lệ, scope bất thường hoặc truy cập hàng loạt object. IP và user agent có thể thay đổi hợp lệ do mạng di động, VPN hoặc proxy; không nên tự động kết luận token bị đánh cắp chỉ từ một tín hiệu.

## 13. Checklist bảo vệ Bearer token

- [ ] Chỉ truyền token qua HTTPS; không đặt token trong path, query, URL hoặc nội dung có thể chia sẻ.
- [ ] Reverse proxy, gateway, application log, APM và tracing đã loại bỏ hoặc che header `Authorization` và refresh token.
- [ ] Token được lưu theo mô hình client phù hợp; browser, mobile và service không để credential trong nơi lưu trữ hoặc file không an toàn.
- [ ] Access token có audience, scope và thời hạn tối thiểu cần thiết.
- [ ] Resource server xác minh chữ ký/active state, issuer, audience, thời hạn và loại token theo chính sách.
- [ ] JWT được ký không bị hiểu nhầm là đã mã hóa; không đưa bí mật vào payload.
- [ ] Quyền chức năng, object và property được kiểm tra sau khi xác thực token.
- [ ] Refresh token có rotation, phát hiện reuse, giới hạn thời hạn và cơ chế thu hồi phù hợp nếu hệ thống sử dụng.
- [ ] Logout, khóa tài khoản và xử lý sự cố có quy trình thu hồi hoặc giới hạn tuổi token rõ ràng.
- [ ] Cân nhắc DPoP hoặc mTLS khi rủi ro đánh cắp/replay token đủ cao và client có thể quản lý khóa an toàn.
- [ ] Có cảnh báo và quy trình ứng phó khi token xuất hiện trong log hoặc được sử dụng bất thường.

## Kết luận

Bearer token giúp API xác thực request thuận tiện, nhưng quyền sử dụng token gắn với việc nắm giữ nó. Nếu token bị sao chép, kẻ tấn công có thể phát lại request cho đến khi token hết hạn hoặc bị server từ chối. Hãy giảm rủi ro bằng HTTPS, lưu trữ an toàn, không ghi token vào log, giới hạn audience/scope/thời hạn, xác minh token đầy đủ, quản lý refresh và thu hồi, đồng thời cân nhắc sender-constrained token cho hệ thống có yêu cầu bảo vệ cao. Sau xác thực, API vẫn phải phân quyền theo endpoint, object, thuộc tính và trạng thái nghiệp vụ.
