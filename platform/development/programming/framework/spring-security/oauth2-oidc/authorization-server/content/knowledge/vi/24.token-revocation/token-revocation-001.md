# Mục đích của OAuth2 Token Revocation

> **Chương:** Revocation  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi ví dụ:** OAuth 2.0 theo RFC 7009 và Spring Authorization Server 1.x trên Servlet stack; các ví dụ API tập trung vào nhánh 1.5.x. Cần đối chiếu Javadoc của phiên bản thư viện đang triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao OAuth 2.0 cần Token Revocation Endpoint và những rủi ro mà nó giải quyết.
2. Phân biệt thu hồi access token, refresh token, authorization grant, phiên đăng nhập và OIDC logout.
3. Mô tả request/response của RFC 7009, ý nghĩa của `token_type_hint` và cách xác thực client.
4. Hiểu vì sao server trả HTTP 200 ngay cả khi token không tồn tại, đã hết hạn hoặc không thuộc client đang gọi.
5. Cấu hình và kiểm thử Token Revocation Endpoint trong Spring Authorization Server.
6. Hiểu vai trò của `OAuth2AuthorizationService` trong việc lưu trạng thái token và đánh dấu token đã bị invalidated.
7. Phân biệt hiệu lực thu hồi với JWT self-contained và opaque/reference token được kiểm tra qua introspection.
8. Thiết kế cascade revocation giữa refresh token và access token theo khuyến nghị RFC 7009.
9. Xây dựng quy trình logout, xử lý token bị lộ, thu hồi hàng loạt và bảo đảm trạng thái nhất quán giữa nhiều instance.
10. Kiểm thử các trường hợp token hợp lệ, token không tồn tại, sai client, token đã thu hồi, refresh rotation và Resource Server cache.

**Ý chính:** OAuth2 Token Revocation cho phép client yêu cầu Authorization Server ngừng công nhận một token trước khi token tự hết hạn. Việc đánh dấu token đã thu hồi trong AS chỉ giải quyết một phần; Resource Server phải có cách nhận biết trạng thái đó. Với JWT được xác minh hoàn toàn cục bộ, thay đổi trong authorization database không tự làm JWT đang còn hạn mất hiệu lực ngay lập tức.

## 2. Vì sao cần Token Revocation?

Access token và refresh token có thời hạn. Nếu một token bị lộ, client bị xâm nhập, người dùng đăng xuất hoặc quyền truy cập thay đổi, chờ đến khi token hết hạn có thể quá lâu.

Ví dụ:

1. Ứng dụng `booking-bff` nhận access token có TTL 30 phút và refresh token có TTL 7 ngày.
2. Người dùng đăng xuất hoặc quản trị viên phát hiện refresh token đã bị sao chép.
3. Nếu AS không có cơ chế revocation, kẻ có refresh token có thể tiếp tục xin access token mới cho tới khi refresh token hết hạn.
4. Client gửi yêu cầu thu hồi refresh token tới AS.
5. AS xác minh client, tìm authorization tương ứng và đánh dấu token bị thu hồi.
6. Những lần refresh tiếp theo phải bị từ chối. Các access token đã phát hành cần được xử lý theo chính sách revocation và cách Resource Server xác minh token.

Token Revocation Endpoint là một phần của OAuth 2.0 để thực hiện bước 4 và 5 theo giao thức chuẩn.

### 2.1. Những tình huống thực tế

| Tình huống | Vì sao cần thu hồi? | Token thường cần xử lý |
| --- | --- | --- |
| Người dùng logout khỏi ứng dụng | Không muốn refresh token tiếp tục tạo access token mới | Refresh token và, tùy policy, access token liên quan |
| Thiết bị bị mất | Ngăn thiết bị tiếp tục dùng credential đã lưu | Refresh token/authorization của thiết bị |
| Client secret hoặc private credential bị lộ | Ngăn client tiếp tục sử dụng token cũ | Token/authorization thuộc client, đồng thời xoay credential |
| Nhân viên rời tổ chức | Thu hồi quyền đã cấp cho tài khoản | Grant/token liên quan đến user |
| User gỡ quyền ứng dụng | Ngừng ứng dụng truy cập dữ liệu | Authorization grant và token liên quan |
| Phát hiện refresh token replay | Ngăn token family bị chiếm dụng tiếp tục hoạt động | Token bị replay và các token cùng family theo policy |
| Thay đổi tenant/role quan trọng | Không để token cũ tiếp tục mang quyền cũ quá lâu | Token liên quan đến authorization bị thay đổi |
| Incident bảo mật | Cắt quyền truy cập trước khi token hết hạn | Các token bị ảnh hưởng, có thể cả client/grant |

### 2.2. Revocation không phải là xóa token khỏi máy client

Client có thể vẫn giữ chuỗi token sau khi AS thu hồi. Revocation không thể tự xóa bản sao trong browser storage, mobile secure storage, log hoặc memory.

Client cần tự xóa token khỏi nơi lưu trữ khi logout/thu hồi thành công. AS cần ngừng chấp nhận token theo trạng thái đã lưu và policy của hệ thống.

### 2.3. Revocation không phải authorization check

Thu hồi token ngăn token đó tiếp tục được sử dụng. Nó không thay thế việc Resource Server kiểm tra:

- Token được phát hành bởi issuer nào.
- Token dành cho audience/resource nào.
- Token còn hạn hay không.
- Scope/authority có đủ không.
- Người dùng/client có quyền với đối tượng dữ liệu cụ thể không.

Một token chưa bị thu hồi vẫn có thể không đủ quyền truy cập một API. Một token đã bị thu hồi phải bị từ chối ngay cả khi chữ ký và expiry vẫn hợp lệ.

## 3. OAuth 2.0 Token Revocation theo RFC 7009

RFC 7009 định nghĩa endpoint cho client yêu cầu AS thu hồi token. Endpoint thường có URL:

~~~text
/oauth2/revoke
~~~

URL thực tế được công bố qua metadata/cấu hình của Authorization Server. Không hardcode endpoint giả định nếu issuer metadata đã cung cấp endpoint chính thức.

### 3.1. Request cơ bản

Client gửi HTTP POST với content type `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

Các tham số:

| Tham số | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `token` | Có | Giá trị access token hoặc refresh token cần thu hồi |
| `token_type_hint` | Không | Gợi ý loại token để AS tìm kiếm nhanh hơn |
| `client_id` | Theo phương thức client authentication | Nhận diện public client hoặc client không dùng HTTP Basic |
| Client authentication | Theo loại client | Chứng minh client được phép gửi yêu cầu revocation |

`token_type_hint` là gợi ý, không phải bằng chứng về loại token. AS có thể bỏ qua hint nếu không nhận diện hoặc không tìm thấy token theo hint đó, rồi thử các loại token được hỗ trợ khác.

### 3.2. Các token_type_hint phổ biến

RFC 7009 định nghĩa các giá trị:

- `access_token`
- `refresh_token`

Không gửi `token_type_hint` không có nghĩa server không thể tìm token. AS có thể tìm trong các loại token được hỗ trợ.

Không dùng hint để bỏ qua việc kiểm tra token thuộc client nào. Token type và quyền client revoke là hai kiểm tra độc lập.

### 3.3. Client authentication

Confidential client thường xác thực bằng phương thức đã đăng ký, ví dụ:

~~~http
Authorization: Basic <base64(client_id:client_secret)>
~~~

Public client không có client secret phải gửi `client_id` theo quy tắc áp dụng. AS phải xác định client context và chỉ xử lý yêu cầu phù hợp với chính sách.

Nếu client A gửi token thuộc client B, AS không được tiết lộ token đó có tồn tại hay không. RFC 7009 yêu cầu phản hồi không giúp attacker dò tìm token của client khác.

### 3.4. Token phải nằm trong body, không nằm trên URL

Không gửi token trong query string:

~~~http
# Không nên
POST /oauth2/revoke?token=REFRESH_TOKEN_VALUE
~~~

Query string thường bị ghi vào access log, reverse proxy log, browser history, monitoring và tracing. Gửi token trong form body qua HTTPS và cấu hình redaction cho request body tại các thành phần trung gian.

## 4. Response và semantics bảo mật của RFC 7009

### 4.1. Thành công trả HTTP 200

Khi request revocation hợp lệ, AS trả:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

Response body thường rỗng. Không có trường `revoked: true` hay `active: false` trong response revocation.

Điểm quan trọng: server trả HTTP 200 khi token đã bị thu hồi **hoặc token không tồn tại/không hợp lệ/không thuộc client được xác thực**. Điều này ngăn endpoint trở thành oracle để dò xem token của người khác có tồn tại hay không.

### 4.2. Vì sao token không tồn tại vẫn trả 200?

Giả sử attacker có một chuỗi token đoán được và gửi tới revocation endpoint. Nếu AS trả:

- `200` khi token tồn tại.
- `404` khi token không tồn tại.

Attacker có thể dùng response để kiểm tra token nào đang hoạt động hoặc thuộc tài khoản nào.

RFC 7009 chọn phản hồi thành công cho trường hợp token không tồn tại để giảm khả năng dò tìm. Client vì thế không nên suy luận token trước đó có hiệu lực chỉ từ HTTP 200.

### 4.3. Những lỗi giao thức vẫn có thể trả lỗi

Các trường hợp lỗi request/authentication có thể trả OAuth2 error:

| Error | HTTP status thường gặp | Nguyên nhân |
| --- | --- | --- |
| `invalid_request` | 400 | Thiếu `token` hoặc request malformed |
| `invalid_client` | 401 | Client authentication không hợp lệ |
| `unsupported_token_type` | 400 | AS không hỗ trợ loại token được yêu cầu theo semantics endpoint |
| `server_error` | 500 | Lỗi nội bộ |
| `temporarily_unavailable` | 503 | AS tạm thời không xử lý được |

Không trả `invalid_token` hoặc `token_not_found` chỉ để tiết lộ token không tồn tại. Trường hợp token không được nhận diện hoặc không thuộc client đã xác thực phải được xử lý theo semantics bảo vệ quyền riêng tư của RFC.

### 4.4. Client nên xử lý response thế nào?

- HTTP 200: coi yêu cầu revocation đã được xử lý theo contract; xóa token local theo flow logout.
- HTTP 400: sửa request, tham số hoặc token type hint nếu lỗi chỉ ra request không hợp lệ.
- HTTP 401: xác minh client credentials/mTLS/client authentication.
- HTTP 5xx: retry có backoff phù hợp; không gửi token vào log khi chẩn đoán.
- Timeout: kết quả có thể chưa rõ vì server có thể đã thu hồi trước khi kết nối bị ngắt. Retry request là an toàn hơn nếu endpoint xử lý idempotent theo semantics.

Revocation nên có tính lặp an toàn: thu hồi token đã thu hồi không tạo quyền mới và không làm token hoạt động trở lại.

## 5. Access token, refresh token và cascade revocation

Revocation của một token có thể ảnh hưởng đến những token khác được sinh ra từ cùng authorization grant.

### 5.1. Thu hồi refresh token

Khi refresh token bị thu hồi:

- Những lần refresh tiếp theo bằng token đó phải thất bại.
- Theo RFC 7009, nếu AS hỗ trợ access token, AS **SHOULD** thu hồi cả các access token được tạo từ cùng authorization grant.
- Nếu authorization grant có nhiều access token hoặc refresh token do rotation, cần xác định token family và trạng thái liên quan.

`SHOULD` trong RFC là khuyến nghị mạnh, có thể có ngoại lệ khi có lý do được ghi nhận; trong hệ thống production, nên thiết kế cascade rõ ràng.

### 5.2. Thu hồi access token

Khi access token bị thu hồi:

- AS ngừng công nhận token đó.
- RFC 7009 cho phép (MAY) AS thu hồi refresh token tương ứng được dùng để tạo access token.
- Nếu không thu hồi refresh token, client có thể xin access token mới bằng refresh token vẫn còn hiệu lực.

Vì vậy, khi mục tiêu là logout hoặc xử lý incident, chỉ thu hồi access token có thể chưa đủ. Phải quyết định có thu hồi refresh token và authorization grant liên quan hay không.

### 5.3. Quan hệ giữa các token

~~~mermaid
flowchart TD
    G["Authorization Grant<br/>User consent / client authorization"]
    C["Authorization Code"]
    A1["Access Token A"]
    R1["Refresh Token R1"]
    A2["Access Token B"]
    R2["Refresh Token R2<br/>sau rotation"]
    G --> C
    C --> A1
    A1 --> R1
    R1 --> A2
    R1 --> R2

    R1 -.->|"Revocation theo grant/family policy"| A1
    R1 -.->|"Cascade theo RFC SHOULD"| A2
    R1 -.->|"Rotation/replay policy"| R2
~~~

Sơ đồ chỉ mô tả quan hệ khái niệm. Thực tế access token và refresh token có thể được tạo/lưu trong cùng `OAuth2Authorization`, nhưng không phải mọi grant đều có refresh token và không phải mọi rotation implementation đều lưu token family riêng.

### 5.4. Revocation của token không đồng nghĩa xóa toàn bộ authorization

Có thể có những chính sách khác nhau:

- Thu hồi một access token duy nhất.
- Thu hồi refresh token và access token liên quan.
- Thu hồi toàn bộ token thuộc authorization grant.
- Thu hồi tất cả authorization của một user với một client.
- Thu hồi tất cả authorization của một client khi credential bị lộ.

RFC 7009 định nghĩa endpoint theo token được gửi. Cách mở rộng thành logout-all-devices, revoke-all-client-grants hoặc user disable là chính sách ứng dụng/AS cần thiết kế riêng.

## 6. Spring Authorization Server triển khai Token Revocation Endpoint

### 6.1. Endpoint mặc định

Spring Authorization Server cung cấp Token Revocation Endpoint, thường tại:

~~~text
POST /oauth2/revoke
~~~

Các thành phần chính trong nhánh SAS 1.x gồm:

- `OAuth2TokenRevocationEndpointConfigurer`: DSL cấu hình endpoint.
- `OAuth2TokenRevocationEndpointFilter`: nhận HTTP request tại endpoint.
- `OAuth2TokenRevocationAuthenticationConverter`: chuyển form request thành authentication request.
- `OAuth2TokenRevocationAuthenticationProvider`: xác minh token/client và xử lý revocation.
- `OAuth2AuthorizationService`: tìm và lưu authorization/token state.

Tên package và một số extension point có thể thay đổi theo version; kiểm tra Javadoc tương ứng trước khi tùy biến.

### 6.2. Cấu hình SecurityFilterChain

Ví dụ Spring Authorization Server 1.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.tokenRevocationEndpoint(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

Ví dụ giả định ứng dụng đã có các bean cần thiết như `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer/JWK configuration và các chain khác cho login/authorization endpoint. Token Revocation Endpoint dùng client authentication context từ các filter/provider client authentication đã được cấu hình trong AS.

Trong cấu hình chuẩn, endpoint revocation đã là một phần của Authorization Server configurer. Gọi `tokenRevocationEndpoint(Customizer.withDefaults())` giúp thể hiện rõ nơi cấu hình endpoint; không cần tạo controller tự xử lý token revocation thay framework.

### 6.3. Đổi endpoint path nếu cần

`AuthorizationServerSettings` có thể cấu hình endpoint path theo deployment:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .tokenRevocationEndpoint("/oauth2/revoke")
        .build();
}
~~~

Đây là fragment cấu hình. Nếu đổi path, cập nhật discovery metadata, API gateway, client configuration, firewall rule, monitoring và integration tests. Không để metadata công bố một URL khác với endpoint thực tế.

## 7. Cách Spring Authorization Server xử lý revocation

### 7.1. Tìm token trong authorization store

Sau khi client authentication thành công và converter parse request, provider cần:

1. Lấy token value và token type hint.
2. Tìm authorization có token tương ứng qua `OAuth2AuthorizationService`.
3. Kiểm tra authorization thuộc client đã xác thực.
4. Xác định token record và trạng thái hiện tại.
5. Đánh dấu token bị invalidated theo metadata/token state.
6. Lưu authorization đã cập nhật.
7. Hoàn tất response theo semantics RFC 7009.

API tìm kiếm thường dùng:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(token, tokenTypeHint);
~~~

Trong đó `tokenTypeHint` có thể là `OAuth2TokenType.ACCESS_TOKEN` hoặc `OAuth2TokenType.REFRESH_TOKEN`; việc hint có null hay không phụ thuộc converter/request. Provider cần xử lý token không tìm thấy theo semantics không tiết lộ thông tin.

### 7.2. Authorization record là nguồn trạng thái

`OAuth2AuthorizationService` quản lý trạng thái authorization. Khi token bị thu hồi, AS có thể lưu metadata invalidation tương ứng với token trong authorization.

Ở mức mô hình, token record có thể có các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Token value | Giá trị token đã phát hành |
| Issued at | Thời điểm phát hành |
| Expires at | Thời điểm hết hạn |
| Invalidated | Token đã bị thu hồi/vô hiệu hóa hay chưa |
| Claims/metadata | Claims hoặc dữ liệu liên quan nếu có |
| Authorization ID | Authorization/grant chứa token |
| Registered client ID | Client đã nhận token |

Không tự viết SQL cập nhật một cột tùy ý nếu không hiểu schema và serialization của implementation. Dùng `OAuth2AuthorizationService` để thay đổi trạng thái theo model.

### 7.3. Lưu trữ phải bền vững trong production

`InMemoryOAuth2AuthorizationService` phù hợp demo/test đơn giản. Khi ứng dụng restart, dữ liệu trong bộ nhớ mất; các instance cũng không chia sẻ trạng thái.

Production nên dùng persistence phù hợp như `JdbcOAuth2AuthorizationService` hoặc implementation bền vững khác. Cần bảo đảm:

- Mọi AS instance đọc/ghi cùng trạng thái authorization nhất quán.
- Transaction không để response thành công nhưng trạng thái revocation chưa được lưu.
- Backup/restore không làm token đã thu hồi sống lại ngoài dự kiến.
- Truy vấn theo token/index có hiệu năng phù hợp.
- Schema migration giữ được trạng thái token.
- Cache authorization không phục vụ trạng thái cũ quá lâu.

### 7.4. Revocation provider mặc định và cascade

Không nên giả định mọi phiên bản/framework tự động thu hồi toàn bộ token liên quan theo đúng chính sách nghiệp vụ của hệ thống. Kiểm tra hành vi của `OAuth2TokenRevocationAuthenticationProvider` trong version SAS đang chạy, đặc biệt:

- Khi gửi refresh token, access token cùng authorization có bị invalidated không?
- Khi gửi access token, refresh token có bị invalidated không?
- Khi refresh token đã rotation, token cũ và token mới có được xem là cùng family không?
- Token không thuộc client đã xác thực được xử lý ra sao?
- Token đã invalidated có thể bị revocation lặp lại an toàn không?

Nếu yêu cầu sản phẩm cần cascade theo RFC 7009 hoặc thu hồi cả token family, hãy triển khai policy rõ ràng quanh authorization service/provider và có integration test. Không sửa trực tiếp database để bỏ qua model của SAS.

## 8. Ví dụ request revocation

### 8.1. Confidential client thu hồi refresh token

~~~bash
curl --request POST \
  --user "booking-bff:CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=REFRESH_TOKEN_VALUE" \
  --data-urlencode "token_type_hint=refresh_token" \
  https://auth.example.test/oauth2/revoke
~~~

Trong production, không đưa secret thật vào shell history hoặc CI log. Dùng secret injection/credential store, TLS và redaction.

### 8.2. Thu hồi access token

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_VALUE&token_type_hint=access_token
~~~

AS xác minh client, xác định token và áp dụng revocation. Client không được kỳ vọng nhận về trạng thái active/inactive của token trong response.

### 8.3. Public client

Một public client không có secret có thể gửi `client_id` cùng token theo phương thức đã đăng ký:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=mobile-app&token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

AS phải ràng buộc token với client ID đã xác định và áp dụng policy phù hợp. Không coi việc client gửi một client ID tùy ý là bằng chứng nó sở hữu token.

## 9. Thu hồi token ảnh hưởng thế nào tới Resource Server?

Đây là phần thường bị hiểu nhầm nhất.

### 9.1. JWT self-contained và kiểm tra cục bộ

Một Resource Server xác minh JWT cục bộ thường thực hiện:

1. Lấy public key từ JWKS.
2. Xác minh chữ ký.
3. Kiểm tra issuer, audience và thời hạn.
4. Ánh xạ scope/claim thành authority.

Nó không truy vấn `OAuth2AuthorizationService` của AS ở mỗi request. Vì vậy:

- AS đánh dấu JWT bị thu hồi trong database.
- RS vẫn có thể xác minh chữ ký của JWT.
- `exp` chưa qua và claims vẫn hợp lệ.
- RS tiếp tục chấp nhận JWT nếu không có kiểm tra revocation bổ sung.

**Thu hồi trong AS không tự vô hiệu JWT self-contained tại mọi RS ngay lập tức.**

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant DB as Authorization Store
    participant RS as Resource Server

    C->>AS: POST /oauth2/revoke + access token
    AS->>DB: Mark token invalidated
    AS-->>C: 200 OK
    C->>RS: API request + JWT cũ
    RS->>RS: Verify signature / iss / aud / exp locally
    Note over RS: Không đọc trạng thái revocation từ AS
    RS-->>C: Có thể vẫn chấp nhận tới exp
~~~

### 9.2. Opaque/reference token và introspection

Với reference token, RS thường gọi Introspection Endpoint. AS đọc trạng thái token trong authorization store và trả `active`:

~~~json
{
  "active": false
}
~~~

Sau khi token bị thu hồi, introspection có thể trả `active: false` và RS từ chối token. Đây là cách phổ biến để có revocation gần thời gian thực, tùy cache và độ nhất quán của store.

Nếu RS cache introspection response `active: true` trong 5 phút, token bị thu hồi có thể tiếp tục được chấp nhận trong khoảng cache đó. TTL cache là một phần của revocation latency.

### 9.3. Ba chiến lược cho JWT cần revocation nhanh

| Chiến lược | Cách hoạt động | Trade-off |
| --- | --- | --- |
| Access token TTL ngắn | JWT tự hết hạn nhanh | Không phải thu hồi tức thì; client refresh thường xuyên hơn |
| Denylist/Revocation store | RS kiểm tra `jti` hoặc token identifier trong store/cache | Có lookup online và quản lý dữ liệu denylist |
| Introspection/online authorization | RS hỏi AS hoặc service trạng thái ở mỗi request/qua cache ngắn | Latency và phụ thuộc availability AS |

Có thể kết hợp TTL ngắn với event invalidation hoặc denylist. Không có cách nào khiến một JWT đã phát hành tự thay đổi payload sau khi nằm ở client.

### 9.4. Cache có thể trì hoãn hiệu lực revocation

Ngay cả khi dùng introspection:

- RS có thể cache `active: true`.
- Gateway có thể cache authorization result.
- Service có thể giữ SecurityContext hoặc session riêng.
- Event revocation có thể đến trễ hoặc bị mất.
- Một request đang chạy trước thời điểm thu hồi có thể hoàn tất sau đó.

Hãy xác định rõ mục tiêu: revocation có hiệu lực ngay, trong vài giây hay tối đa trong một khoảng TTL. Với thao tác nhạy cảm, có thể cần kiểm tra online trạng thái authorization tại thời điểm thực thi.

## 10. Revocation, logout và session management

### 10.1. Logout không tự động thu hồi mọi token

Logout ở ứng dụng có thể có các hành động:

- Xóa session cookie phía browser.
- Hủy server-side HTTP session.
- Xóa access/refresh token ở client.
- Gọi Token Revocation Endpoint cho refresh token.
- Thu hồi authorization grant.
- Gửi OIDC RP-Initiated Logout tới OP.
- Thu hồi session tại identity provider.

Các hành động này không tương đương. Xóa cookie local không thu hồi refresh token ở AS. Thu hồi refresh token không nhất thiết hủy browser session của OP. OIDC logout không tự đảm bảo mọi access token JWT đã phát hành bị RS từ chối ngay.

### 10.2. User logout khỏi một thiết bị

Một flow điển hình:

1. Client xác định refresh token của session/thiết bị cần kết thúc.
2. Gọi `/oauth2/revoke` với refresh token và client authentication.
3. AS đánh dấu token bị thu hồi và áp dụng cascade policy.
4. Client xóa access/refresh token local và session liên quan.
5. RS nhận biết token bị thu hồi theo introspection/denylist/TTL.
6. Nếu dùng OIDC, client thực hiện RP-Initiated Logout khi cần kết thúc OP session.

### 10.3. Logout all devices

Đây thường là chức năng nghiệp vụ mở rộng, không chỉ là một lần gọi RFC 7009. Hệ thống cần xác định tất cả authorization/grant thuộc user, tenant hoặc client và thu hồi theo policy.

Một API nội bộ có thể yêu cầu `OAuth2AuthorizationService` tìm authorization theo principal/client rồi invalidated các token liên quan. Phải kiểm tra quyền quản trị, audit, transaction và multi-instance consistency.

Không cho mobile client tự gửi lệnh “revoke tất cả token của user X” nếu không có authorization phù hợp.

## 11. Refresh token rotation và token family revocation

### 11.1. Rotation tạo ra trạng thái nhiều token

Khi `reuseRefreshTokens(false)` được cấu hình, refresh flow có thể phát refresh token mới thay token cũ. Hệ thống phải xử lý:

- Refresh token cũ đã dùng có bị invalidated không.
- Token mới có thuộc cùng authorization grant không.
- Hai request đồng thời dùng cùng token cũ xử lý thế nào.
- Nếu token cũ bị replay, có thu hồi token mới và access token cùng family không.
- Revocation endpoint nhận token cũ thì policy nào áp dụng.

### 11.2. Phát hiện replay và thu hồi family

Ví dụ chuỗi:

~~~text
R1 --refresh--> A2 + R2
R1 bị dùng lại (replay)
=> phát hiện credential cũ đã tiêu thụ
=> revoke R2 và access tokens liên quan theo family policy
=> yêu cầu user/client thực hiện authorization mới
~~~

Đây là một policy an ninh phổ biến với refresh token rotation. Tuy nhiên, khả năng phát hiện replay và quản lý family phụ thuộc authorization store/provider implementation. Không giả định chỉ bật `reuseRefreshTokens(false)` đã cung cấp đầy đủ token-family revocation.

### 11.3. Race condition

Hai request đồng thời dùng R1 có thể cùng đến hai AS instances. Nếu storage không có transaction/locking hoặc compare-and-set phù hợp, cả hai có thể được xử lý không nhất quán.

Cần test:

- Một request refresh thành công, request còn lại bị từ chối.
- Token cũ không được sử dụng lại sau khi rotation.
- Revocation xảy ra đồng thời với refresh không làm token bị phát hành lại ngoài ý muốn.
- Các AS instances nhìn thấy trạng thái cập nhật giống nhau.
- Retry do timeout không tạo thêm refresh chain bất thường.

## 12. Bảo mật Token Revocation Endpoint

### 12.1. Xác thực client trước khi xử lý token

Revocation endpoint phải dùng client authentication đã đăng ký:

- `client_secret_basic`.
- `client_secret_post` nếu policy cho phép.
- `private_key_jwt`.
- mTLS client authentication.
- `none` cho public client theo cơ chế được hỗ trợ.

Không để endpoint trở thành API ẩn danh nhận token bất kỳ rồi thay đổi trạng thái authorization của hệ thống.

### 12.2. Kiểm tra quyền sở hữu token

Sau khi xác thực client, AS phải xác định token có liên quan tới client đó hay không. Không cho client A thu hồi token của client B chỉ vì A biết chuỗi token.

Với token không tồn tại hoặc không thuộc client, phản hồi theo RFC để tránh token enumeration. Không trả thêm thông tin như user ID, client ID sở hữu token hoặc thời gian token hết hạn.

### 12.3. TLS và bảo vệ credential

- Bắt buộc HTTPS.
- Không gửi token qua URL/query string.
- Không log form body có token.
- Redact `Authorization` header, refresh token và access token tại proxy/APM.
- Hạn chế quyền đọc authorization database.
- Bảo vệ endpoint khỏi brute-force/DoS bằng rate limit phù hợp.
- Dùng client authentication mạnh cho confidential client.
- Có audit event nhưng không ghi raw token.

### 12.4. Idempotency và race

Revocation nên an toàn khi gửi lại cùng token:

- Token đang active: đánh dấu invalidated.
- Token đã invalidated: không làm sống lại token.
- Token không tìm thấy: trả response theo semantics RFC.
- Hai request revocation đồng thời: kết quả cuối vẫn là token invalidated.
- Revocation đồng thời với refresh: transaction/locking phải bảo đảm token không được cấp lại trái policy.

Không dựa vào response 200 để khẳng định đã tìm thấy một token cụ thể.

## 13. Kiểm thử Token Revocation Endpoint

### 13.1. Ma trận kiểm thử HTTP

| Ca kiểm thử | Request | Kỳ vọng |
| --- | --- | --- |
| Thu hồi refresh token hợp lệ | Client đúng, token active, hint refresh | 200, token invalidated |
| Thu hồi access token hợp lệ | Client đúng, token active, hint access | 200, token invalidated |
| Token không tồn tại | Token random | 200 theo RFC, không tiết lộ |
| Token đã thu hồi | Gửi lại cùng token | 200, idempotent |
| Token thuộc client khác | Client A gửi token của B | Không tiết lộ, không thu hồi trái quyền |
| Thiếu token | Body không có `token` | 400 `invalid_request` |
| Client secret sai | Basic credential sai | 401 `invalid_client` |
| Hint không đúng loại | Hint sai/không nhận diện | Server tìm theo loại khác hoặc xử lý theo RFC |
| Loại token không hỗ trợ | Token type thực sự không được hỗ trợ | Error phù hợp, thường `unsupported_token_type` |
| Refresh bị revoke | Thử refresh tiếp bằng token cũ | Từ chối grant |
| Access token opaque bị revoke | Introspection sau revocation | `active: false` |
| JWT local validation sau revoke | RS chỉ verify JWT | Có thể vẫn hợp lệ đến expiry nếu không có online check |
| Cascade policy | Thu hồi RT | Các AT cùng grant bị xử lý theo policy |
| Concurrent revocation | Hai request cùng token | Trạng thái cuối vẫn invalidated |
| Refresh/revoke race | Hai request đồng thời | Không phát lại token trái policy |
| Audit/log | Revocation request | Không có raw token trong log |

### 13.2. MockMvc test ví dụ

Ví dụ test confidential client thu hồi refresh token:

~~~java
@Test
void revokeRefreshTokenReturnsOk() throws Exception {
    mockMvc.perform(post("/oauth2/revoke")
            .with(httpBasic("booking-bff", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("token", "known-refresh-token")
            .param("token_type_hint", "refresh_token"))
        .andExpect(status().isOk());
}
~~~

Test fixture cần có:

- RegisteredClient `booking-bff` đã được đăng ký client authentication method phù hợp.
- Authorization record chứa refresh token `known-refresh-token`.
- Authorization service có thể tìm token và lưu trạng thái invalidated.
- Filter chain AS và revocation endpoint hoạt động.

**HTTP 200 một mình chưa chứng minh token đã bị thu hồi**, vì token không tồn tại cũng được trả 200. Phải đọc trạng thái authorization hoặc gọi token endpoint/introspection để xác minh token không còn được công nhận.

### 13.3. Kiểm thử trạng thái token qua authorization service

Ví dụ kiểm tra theo hướng integration test:

~~~java
OAuth2Authorization authorizationBefore =
    authorizationService.findByToken(
        "known-refresh-token",
        OAuth2TokenType.REFRESH_TOKEN);

assertThat(authorizationBefore).isNotNull();

mockMvc.perform(post("/oauth2/revoke")
        .with(httpBasic("booking-bff", "test-only-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("token", "known-refresh-token")
        .param("token_type_hint", "refresh_token"))
    .andExpect(status().isOk());

OAuth2Authorization authorizationAfter =
    authorizationService.findByToken(
        "known-refresh-token",
        OAuth2TokenType.REFRESH_TOKEN);

assertThat(authorizationAfter).isNotNull();
assertThat(authorizationAfter.getRefreshToken().isInvalidated())
    .isTrue();
~~~

Đây là ví dụ minh họa theo model SAS 1.x; tùy version, accessor và fixture có thể cần điều chỉnh. Nếu provider xóa record thay vì giữ token metadata, test phải xác minh semantics qua API/service phù hợp.

### 13.4. Test client không sở hữu token

Chuẩn bị hai client A và B, mỗi client có token riêng. Client A gửi token B tới revocation endpoint:

- Endpoint vẫn phản hồi theo semantics không tiết lộ token.
- Token B không bị thu hồi bởi request của A.
- Không có response body tiết lộ token B thuộc client nào.
- Audit có thể ghi outcome generic và client A đã xác thực.

### 13.5. Test propagation tới Resource Server

Với opaque token:

1. Gọi API bằng token active.
2. Thu hồi token.
3. Gọi introspection và xác nhận `active: false`.
4. Gọi API lại và xác nhận RS từ chối sau khi cache hết hạn/được invalidated.

Với JWT:

1. Gọi API bằng JWT hợp lệ.
2. Thu hồi tại AS.
3. Nếu RS chỉ verify local, chứng minh token có thể vẫn hợp lệ đến `exp`.
4. Bật denylist/introspection/event strategy.
5. Xác nhận RS từ chối theo mục tiêu revocation latency đã đặt ra.

Test cần phản ánh kiến trúc thật, không mock decoder luôn trả invalid sau revocation rồi kết luận JWT local có revocation tự động.

## 14. Vận hành và quan sát

### 14.1. Audit event

Có thể ghi các trường:

- Timestamp.
- Correlation/request ID.
- Client ID đã xác thực.
- Token type hint.
- Outcome tổng quát (processed/error).
- Error code nếu request malformed/client auth failure.
- Authorization/grant identifier nội bộ đã được bảo vệ, nếu cần điều tra.
- Nguồn yêu cầu (logout, admin, incident workflow).

Không ghi raw access token, refresh token, authorization header hoặc full request body.

### 14.2. Metrics

| Metric | Mục đích |
| --- | --- |
| Revocation request count | Theo dõi khối lượng |
| Revocation success/processing rate | Quan sát hoạt động endpoint |
| Invalid client rate | Phát hiện credential/configuration issue |
| Revocation persistence latency | Đo thời gian cập nhật trạng thái |
| Introspection active/inactive count | Theo dõi hiệu lực ở RS |
| JWT denylist lookup/failure | Đo online revocation strategy |
| Revocation propagation delay | Đo thời gian từ AS revoke tới RS deny |
| Refresh-after-revocation failures | Kiểm tra token đã bị vô hiệu |
| Concurrent refresh/revoke conflicts | Phát hiện race |

Không dùng token value làm metric label. Cardinality sẽ bùng nổ và có nguy cơ lộ credential.

### 14.3. Mục tiêu revocation latency

Hãy định nghĩa rõ thời gian từ lúc AS xác nhận revocation đến lúc tất cả RS từ chối token:

| Chiến lược | Độ trễ điển hình | Yếu tố ảnh hưởng |
| --- | --- | --- |
| JWT local + TTL | Tới khi token hết hạn | Access token lifetime, clock skew |
| JWT + denylist | Gần thời gian thực theo store/cache | Event propagation, cache invalidation |
| Opaque + introspection không cache | Gần thời gian thực | Store consistency và network latency |
| Opaque + introspection cache | Tối đa gần TTL cache | Cache invalidation và refresh |
| Gateway-only revocation check | Phụ thuộc gateway | Đường gọi bypass gateway phải bị chặn |

Đây là mục tiêu kiến trúc, không phải cam kết cố định của RFC hoặc framework. API nhạy cảm có thể cần kiểm tra trạng thái authorization online cho từng request.

## 15. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ HTTP 200 chứng minh token đã tồn tại | Sai semantics RFC 7009 | 200 không tiết lộ trạng thái token |
| Thu hồi refresh token nhưng không nghĩ đến access token đã phát | Access token cũ có thể còn hoạt động | Thiết kế cascade/RS propagation |
| Nghĩ JWT tự hết hiệu lực ngay khi AS đánh dấu revoked | RS local vẫn verify chữ ký và expiry | Introspection, denylist hoặc TTL ngắn |
| Chỉ xóa token ở client | Token bị sao chép vẫn dùng được | Gọi AS revocation và xóa local |
| Chỉ xóa session cookie | Refresh token vẫn có thể còn hiệu lực | Revocation token riêng |
| Client A có thể revoke token B | Cross-client denial of service | Kiểm tra ownership/client binding |
| Dùng token trong URL | Token lộ qua log/history | Form body qua HTTPS |
| Log toàn bộ revocation request | Lộ refresh/access token | Redaction và audit metadata |
| Coi token_type_hint là sự thật | Có thể bỏ sót token hoặc xử lý sai loại | Hint chỉ để tối ưu tìm kiếm |
| Cho rằng SAS tự cascade mọi token family | Có thể thiếu policy theo yêu cầu | Kiểm tra provider version và test cascade |
| Dùng InMemoryAuthorizationService production | Restart/multi-instance mất trạng thái | Persistence bền vững |
| Cache introspection quá lâu | Revocation chậm | TTL theo risk và invalidation |
| Không test race refresh/revoke | Token có thể được cấp lại ngoài ý muốn | Transaction/locking và concurrency tests |
| Coi logout OIDC là revocation access token | API vẫn nhận JWT cũ | Tách logout, session và token revocation |
| Chỉ test status 200 | Không chứng minh state đã đổi | Kiểm tra authorization store/introspection/RS |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Mục đích chính của OAuth2 Token Revocation là gì?

**Đáp án:** Cho phép client yêu cầu AS ngừng công nhận access token hoặc refresh token trước khi token tự hết hạn, ví dụ khi logout, mất thiết bị hoặc phát hiện credential bị lộ.

**Câu 2.** Vì sao RFC 7009 trả HTTP 200 khi token không tồn tại?

**Đáp án:** Để không biến endpoint thành oracle cho attacker dò token của client/người dùng khác.

**Câu 3.** `token_type_hint` có bắt buộc không?

**Đáp án:** Không. Đây là gợi ý giúp AS tìm token; không phải bằng chứng loại token và AS có thể tìm theo loại khác.

**Câu 4.** Thu hồi refresh token có ảnh hưởng tới access token đã phát không?

**Đáp án:** RFC 7009 khuyến nghị mạnh AS nên thu hồi các access token dựa trên cùng authorization grant khi refresh token bị thu hồi. Cần kiểm tra/triển khai cascade theo policy và version thực tế.

**Câu 5.** Thu hồi access token có bắt buộc thu hồi refresh token không?

**Đáp án:** Không bắt buộc; RFC cho phép AS thu hồi refresh token tương ứng. Quyết định phụ thuộc mục tiêu logout/incident.

**Câu 6.** Vì sao JWT self-contained có thể vẫn dùng được sau revocation?

**Đáp án:** RS xác minh chữ ký và expiry cục bộ, không truy vấn trạng thái invalidated trong AS. Cần denylist, introspection/online check hoặc TTL ngắn.

**Câu 7.** Vì sao opaque token dễ hỗ trợ revocation gần thời gian thực hơn?

**Đáp án:** RS thường introspect token với AS; trạng thái active/inactive được đọc từ authorization store, miễn là cache không giữ kết quả cũ quá lâu.

**Câu 8.** HTTP 200 từ revocation endpoint có đủ để test token đã bị thu hồi không?

**Đáp án:** Không. Token không tồn tại cũng được trả 200. Phải kiểm tra authorization state, introspection hoặc hành vi RS.

**Câu 9.** Logout và token revocation có giống nhau không?

**Đáp án:** Không. Logout có thể hủy session/cookie/OIDC OP session; revocation thay đổi trạng thái token tại AS. Một flow logout hoàn chỉnh có thể cần thực hiện cả hai.

**Câu 10.** Client A gửi token của client B tới endpoint revocation, AS nên làm gì?

**Đáp án:** Không thu hồi token B và không tiết lộ token có tồn tại hay không; phản hồi theo semantics RFC 7009.

## 17. Checklist triển khai production

- [ ] Token Revocation Endpoint được bật và URL công bố đúng.
- [ ] Request dùng HTTPS, POST và form body; token không nằm trên URL.
- [ ] Client authentication được cấu hình theo RegisteredClient.
- [ ] AS kiểm tra token thuộc client đã xác thực.
- [ ] `token_type_hint` được xem là hint, không phải nguồn sự thật.
- [ ] Token không tồn tại/không thuộc client được xử lý theo semantics không tiết lộ RFC 7009.
- [ ] Authorization store lưu trạng thái revocation bền vững và chia sẻ giữa AS instances.
- [ ] Đã xác minh hành vi cascade refresh-token/access-token theo RFC và SAS version.
- [ ] Refresh token rotation/replay có policy family rõ.
- [ ] Resource Server có chiến lược nhận biết revoked token.
- [ ] JWT local validation không bị nhầm là có revocation tức thì.
- [ ] Introspection/denylist cache TTL đáp ứng mục tiêu revocation latency.
- [ ] Logout phân biệt session, refresh token, access token và OIDC logout.
- [ ] Có kiểm soát race giữa refresh và revocation.
- [ ] Có audit/metrics nhưng không log raw tokens hoặc secrets.
- [ ] Có test token active, revoked, nonexistent, wrong client, malformed request, cascade và multi-instance.
- [ ] Có runbook cho mất thiết bị, token theft, client compromise và logout all devices.

## 18. Tài liệu tham khảo và kết luận

Tài liệu chuẩn và tài liệu framework:

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7009, Section 2 — Revocation Endpoint](https://www.rfc-editor.org/rfc/rfc7009#section-2)
- [RFC 7009, Section 2.1 — Revocation Request](https://www.rfc-editor.org/rfc/rfc7009#section-2.1)
- [RFC 7009, Section 2.2 — Revocation Response](https://www.rfc-editor.org/rfc/rfc7009#section-2.2)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — OAuth2TokenRevocationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenRevocationEndpointConfigurer.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)

**Kết luận:** OAuth2 Token Revocation cung cấp cơ chế chuẩn để client yêu cầu AS ngừng công nhận token trước khi hết hạn. RFC 7009 cố ý trả HTTP 200 cho token không tồn tại hoặc không thuộc client để tránh rò rỉ thông tin. Trong Spring Authorization Server, endpoint revocation làm việc cùng client authentication, revocation provider và authorization service. Để đạt hiệu lực thực tế, hệ thống còn phải xử lý cascade giữa refresh/access token, lưu trạng thái bền vững và bảo đảm Resource Server nhận biết token đã bị thu hồi. Đặc biệt, JWT tự xác minh cục bộ không tự mất hiệu lực khi AS cập nhật database; cần lựa chọn introspection, denylist, event invalidation hoặc TTL ngắn theo yêu cầu bảo mật và độ trễ của hệ thống.

