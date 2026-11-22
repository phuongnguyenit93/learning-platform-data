# Kiểm thử hết hạn code, token, client secret và chứng thư

Authorization Server phải từ chối mọi credential đã hết hạn, đồng thời tiếp tục chấp nhận credential còn hiệu lực trong đúng khoảng thời gian được cấu hình. Với Spring Authorization Server, việc kiểm thử cần bao phủ cả nơi phát hành credential, nơi lưu trạng thái OAuth2 và nơi xác minh credential. Một bài kiểm thử chỉ kiểm tra claim `exp` trong JWT chưa chứng minh token đã bị từ chối ở resource server; tương tự, kiểm tra ngày hết hạn của chứng thư bằng cách đọc file PEM chưa chứng minh TLS handshake sẽ từ chối chứng thư đó.

Bài học này thuộc module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, tập trung vào thiết kế và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Authorization Server. Các ví dụ hướng đến kiểm thử các luồng authorization code, access token, refresh token, client authentication và TLS trong môi trường tích hợp.

## 1. Phân biệt các loại thời hạn

Mỗi loại credential có vòng đời và điểm thực thi khác nhau. Xác định đúng điểm kiểm tra trước khi viết test giúp tránh kết luận sai từ một thành phần không chịu trách nhiệm xác minh credential đó.

| Đối tượng | Thời hạn được biểu diễn ở đâu | Thành phần phải từ chối khi hết hạn |
|---|---|---|
| Authorization code | `expiresAt` của authorization code được lưu trong `OAuth2Authorization` | Token endpoint của Authorization Server |
| Access token dạng JWT | Claim `exp` trong JWT và metadata authorization được lưu | Resource server khi xác minh JWT; Authorization Server khi xử lý trạng thái liên quan |
| Access token dạng opaque | Metadata token và trạng thái authorization trong kho lưu trữ | Resource server thông qua introspection hoặc cơ chế xác minh tương ứng |
| Refresh token | `expiresAt` của refresh token trong authorization state | Token endpoint khi nhận `grant_type=refresh_token` |
| Client secret | `clientSecretExpiresAt` của `RegisteredClient` | Cơ chế client authentication tại token endpoint hoặc endpoint yêu cầu xác thực client |
| TLS server certificate | `notBefore` và `notAfter` trong chứng thư máy chủ | TLS client khi xác minh chứng thư của Authorization Server |
| TLS client certificate | `notBefore` và `notAfter` trong chứng thư client | TLS terminator hoặc thành phần xác minh mTLS trước khi xử lý request |

Hết hạn khác với thu hồi hoặc vô hiệu hóa. Một authorization code có thể còn trong thời hạn nhưng đã được sử dụng; refresh token có thể còn hạn nhưng đã bị xoay vòng hoặc thu hồi; client secret có thể chưa hết hạn nhưng đã bị thay thế. Test cần xác nhận từng nguyên nhân riêng biệt để lỗi được phân loại chính xác.

## 2. Chuẩn bị cấu hình thời hạn có thể kiểm tra

Spring Authorization Server cho phép cấu hình thời hạn access token và refresh token thông qua `TokenSettings`. Mỗi `RegisteredClient` có thể dùng bộ thiết lập token riêng.

```java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
```

Trong ví dụ này, refresh token được xoay vòng khi refresh thành công. Cấu hình `reuseRefreshTokens(false)` giúp token endpoint phát hành refresh token mới và vô hiệu hóa refresh token cũ theo hành vi của phiên bản Spring Authorization Server đang dùng.

Một client dùng các thiết lập trên có thể được đăng ký như sau:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientSecretExpiresAt(Instant.now().plus(Duration.ofDays(30)))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://client.example.com/login/oauth2/code/orders")
        .scope("orders.read")
        .tokenSettings(tokenSettings)
        .build();
```

Đây là cấu hình minh họa cho test fixture. Ứng dụng thực tế phải dùng `PasswordEncoder` phù hợp, lưu client bằng repository bền vững và quản lý secret qua kho cấu hình an toàn. Không dùng secret dạng rõ trong cấu hình production.

### 2.1. Đừng giả định mọi credential có cùng TTL

`TokenSettings` điều khiển các thời hạn token mà API đó hỗ trợ, chẳng hạn access token và refresh token. Authorization code có thể được tạo và hết hạn bởi provider xử lý authorization request; khả năng cấu hình TTL phụ thuộc phiên bản và cách tùy biến Spring Authorization Server. Hãy kiểm tra API của phiên bản dự án đang sử dụng, rồi kiểm thử giá trị `expiresAt` được lưu thực tế. Không suy luận thời hạn authorization code từ `accessTokenTimeToLive`.

Client secret dùng `clientSecretExpiresAt` trên `RegisteredClient`, không dùng `TokenSettings`. TLS certificate lại có thời hạn riêng do CA phát hành và TLS stack kiểm tra. Tách cấu hình theo từng loại credential giúp bài test chỉ ra chính xác chính sách nào bị sai.

## 3. Kiểm thử authorization code hết hạn và chỉ được sử dụng một lần

Authorization code là credential ngắn hạn được cấp sau khi người dùng hoàn tất authorization flow. Client gửi code đến token endpoint để đổi lấy token. Token endpoint cần từ chối code đã hết hạn, sai client, sai redirect URI hoặc đã được sử dụng.

Hai trường hợp cần kiểm thử riêng:

- **Hết hạn:** thời điểm hiện tại đã bằng hoặc vượt `expiresAt` của code.
- **Replay:** code đã được đổi thành công trước đó và được gửi lại.

### 3.1. Tạo fixture code đã hết hạn

Để kiểm thử hết hạn mà không phải chờ TTL thực, tạo một `OAuth2Authorization` fixture có authorization code với `expiresAt` nằm trong quá khứ, rồi lưu qua `OAuth2AuthorizationService` mà token endpoint đang sử dụng. Fixture phải có registered client, principal, grant type `AUTHORIZATION_CODE` và authorization request phù hợp để provider có đủ dữ liệu thực hiện các kiểm tra còn lại.

Ví dụ phần tạo code trong test:

```java
import java.time.Instant;

import org.springframework.security.oauth2.core.OAuth2AuthorizationCode;

Instant issuedAt = Instant.now().minusSeconds(120);
OAuth2AuthorizationCode expiredCode = new OAuth2AuthorizationCode(
        "expired-code-for-test",
        issuedAt,
        Instant.now().minusSeconds(60));
```

Gắn code này vào authorization fixture bằng builder `OAuth2Authorization.withRegisteredClient(...)`, đặt `AuthorizationGrantType.AUTHORIZATION_CODE`, principal và các thuộc tính authorization request cần thiết, sau đó gọi `authorizationService.save(authorization)`. Cấu trúc đầy đủ của fixture phụ thuộc principal và cách ứng dụng lưu authorization request; nên dùng cùng factory tạo fixture cho các test token endpoint để tránh bỏ sót thuộc tính bắt buộc.

Gửi request đổi code đến token endpoint với đúng client và redirect URI. Kết quả mong đợi là lỗi OAuth2 `invalid_grant`; không phát hành access token hoặc refresh token. Không kiểm tra riêng HTTP status rồi bỏ qua body lỗi, vì body giúp phân biệt `invalid_grant` với `invalid_client` hoặc `invalid_request`.

### 3.2. Kiểm thử code replay

Với code còn hạn, thực hiện authorization flow hợp lệ và đổi code lần đầu. Request đầu tiên phải thành công. Gửi lại cùng code với cùng client và redirect URI; request thứ hai phải bị từ chối với `invalid_grant`.

Khi chạy test trên nhiều instance, lưu authorization bằng repository dùng chung rồi gửi lần đổi code đầu tiên đến node A và request replay đến node B. Kết quả từ node B phải phản ánh code đã được sử dụng. Nếu node B vẫn chấp nhận code, hãy kiểm tra tính nhất quán của `OAuth2AuthorizationService`, transaction và cơ chế cập nhật trạng thái dùng một lần.

Không dùng một code hết hạn để kiểm thử replay: cả hai trường hợp đều bị từ chối nhưng không chứng minh được server đã phân biệt được hai quy tắc.

## 4. Kiểm thử access token hết hạn

Access token có thể là JWT hoặc opaque token. Cách kiểm thử khác nhau ở nơi resource server xác minh token.

### 4.1. Kiểm tra thời hạn khi phát hành JWT

Với JWT, kiểm tra claim `iat` và `exp` trong token được phát hành. Nếu chính sách quy định access token có TTL năm phút, `exp` phải tương ứng với thời điểm phát hành cộng thời hạn đó, trong giới hạn độ chính xác của đồng hồ và cách làm tròn timestamp.

Có thể kiểm tra metadata trong authorization store bằng `OAuth2AuthorizationService.findByToken(...)` và đối chiếu `OAuth2Authorization.Token.getToken().getExpiresAt()` với claim `exp`. Việc giải mã payload chỉ phục vụ kiểm tra dữ liệu trong test; nó không xác minh chữ ký và không thể thay thế kiểm thử resource server.

### 4.2. Xác minh JWT đã hết hạn ở resource server

Resource server phải xác minh chữ ký, issuer, audience nếu được yêu cầu và thời hạn `exp`. Tạo một JWT test đã ký bằng khóa test tin cậy với `exp` trong quá khứ, sau đó gửi JWT đến endpoint được bảo vệ. Kết quả phải là `401 Unauthorized` và request không được đi vào logic nghiệp vụ.

Ví dụ kiểm thử ở mức HTTP:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.HttpHeaders;

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + expiredJwt))
    .andExpect(status().isUnauthorized());
```

`expiredJwt` phải là JWT có chữ ký hợp lệ và issuer/key được resource server tin cậy, nhưng có `exp` đã qua. Nếu dùng token sai chữ ký hoặc issuer không khớp, test có thể nhận `401` vì một nguyên nhân khác và không chứng minh bộ kiểm tra hết hạn hoạt động.

Spring Security có thể áp dụng clock skew khi xác minh timestamp để dung hòa sai lệch đồng hồ giữa các hệ thống. Hãy đọc cấu hình `JwtTimestampValidator` của resource server và kiểm thử cả thời điểm nằm ngoài khoảng clock skew. Nếu test chỉ gửi token vừa hết hạn vài mili giây, kết quả có thể vẫn được chấp nhận theo chính sách clock skew. Ghi rõ khoảng đệm thời gian trong kỳ vọng của test.

### 4.3. Kiểm thử opaque access token

Với opaque token, resource server thường gọi introspection endpoint. Khi token hết hạn, Authorization Server phải trả `active: false`; resource server phải từ chối request tương ứng. Test nên bao gồm:

1. Token còn hạn được introspect là active và truy cập endpoint được bảo vệ thành công.
2. Token đã hết hạn được introspect là inactive.
3. Resource server từ chối token inactive, kể cả khi client gửi token đúng định dạng.
4. Cache introspection không giữ trạng thái active quá thời điểm hết hạn theo chính sách cache.

Nếu introspection response được cache, TTL cache phải ngắn hơn hoặc bằng thời gian còn lại của token. Khi token bị thu hồi, cache cũng cần được xử lý theo mức độ chấp nhận độ trễ thu hồi của hệ thống.

## 5. Kiểm thử refresh token hết hạn và xoay vòng

Refresh token cho phép client yêu cầu access token mới mà không bắt người dùng đăng nhập lại. Vì refresh token có thời hạn dài và quyền lực cao, token endpoint phải từ chối refresh token hết hạn, đã bị thu hồi hoặc đã bị thay thế trong quá trình xoay vòng.

Tạo fixture authorization có refresh token với `expiresAt` nằm trong quá khứ và lưu vào `OAuth2AuthorizationService`. Gửi request `grant_type=refresh_token` với đúng client. Kết quả mong đợi là `invalid_grant`, không có token mới được phát hành.

Ngoài trường hợp hết hạn, kiểm thử xoay vòng như sau:

1. Phát hành access token và refresh token hợp lệ.
2. Dùng refresh token để yêu cầu token mới.
3. Xác nhận request thành công và nhận refresh token mới nếu `reuseRefreshTokens(false)` được cấu hình.
4. Gửi lại refresh token cũ; server phải từ chối theo chính sách xoay vòng.
5. Xác nhận refresh token mới còn hiệu lực và có thời hạn theo cấu hình.

Khi kiểm thử concurrency, gửi hai request refresh gần như đồng thời bằng cùng refresh token. Chỉ một request được phép tiêu thụ token cũ thành công. Request còn lại phải bị từ chối hoặc được xử lý theo chính sách chống replay mà hệ thống công bố. Nếu cả hai request đều tạo ra token hợp lệ, kiểm tra transaction và thao tác cập nhật authorization state có được thực hiện nguyên tử hay không.

## 6. Kiểm thử client secret hết hạn

`RegisteredClient` có trường `clientSecretExpiresAt` để biểu diễn thời điểm client secret hết hạn. Client authentication phải từ chối secret sau thời điểm này, kể cả khi giá trị secret gửi lên vẫn khớp với hash đang lưu.

Trong test fixture, tạo client có secret hết hạn:

```java
RegisteredClient expiredSecretClient = RegisteredClient.withId("test-client-id")
        .clientId("expired-secret-client")
        .clientSecret(passwordEncoder.encode("expired-secret"))
        .clientSecretExpiresAt(Instant.now().minusSeconds(60))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();

registeredClientRepository.save(expiredSecretClient);
```

Gọi token endpoint bằng client ID và secret đúng qua HTTP Basic. Vì secret đã hết hạn, server phải trả lỗi `invalid_client` và không cấp token. Dùng secret sai cho một test riêng để chứng minh trường hợp credential mismatch cũng bị từ chối.

Ví dụ request trong MockMvc:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("expired-secret-client", "expired-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("scope", "orders.read"))
    .andExpect(status().isUnauthorized())
    .andExpect(jsonPath("$.error").value("invalid_client"));
```

Test phải chạy với đúng `RegisteredClientRepository` và cơ chế client authentication mà production sử dụng. Nếu mock toàn bộ provider xác thực client, test chỉ xác nhận mock được gọi mà không kiểm tra hành vi hết hạn thực tế.

Với secret rotation, kiểm thử thêm quy trình thay secret: secret cũ bị từ chối sau thời điểm hết hạn hoặc sau khi bị thay thế, secret mới được chấp nhận, và không có khoảng thời gian mà một secret đã bị thu hồi vẫn xác thực được do cache client cũ. Nếu cache `RegisteredClient`, xác định rõ thời gian đồng bộ và cơ chế invalidation giữa các instance.

## 7. Kiểm thử chứng thư TLS hết hạn

Chứng thư TLS có hai vai trò phổ biến trong hệ thống authorization:

- Chứng thư server xác thực hostname của Authorization Server với client kết nối.
- Chứng thư client xác thực workload khi dùng mutual TLS (mTLS), có thể được dùng cho client authentication hoặc ràng buộc access token với chứng thư.

Thời hạn chứng thư được ghi trong `notBefore` và `notAfter`. TLS stack kiểm tra khoảng hiệu lực cùng chuỗi tin cậy, chữ ký CA, hostname/SAN và các ràng buộc sử dụng khóa. Chứng thư hết hạn thường bị từ chối ngay trong TLS handshake, trước khi request đến endpoint OAuth2. Do đó, không mong đợi mọi trường hợp chứng thư hết hạn đều trả về JSON lỗi OAuth2.

### 7.1. Kiểm tra chứng thư server

Từ máy client hoặc một môi trường kiểm thử bên ngoài cụm, kiểm tra chứng thư được proxy hoặc server công bố:

```bash
openssl s_client \
  -connect auth.example.com:443 \
  -servername auth.example.com \
  -CAfile trusted-ca.pem \
  -verify 5 \
  -verify_return_error \
  -showcerts
```

Đọc thời hạn của một chứng thư đã lưu:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates
```

Test tích hợp nên khởi động TLS server cục bộ với chứng thư test hết hạn và xác nhận client TLS từ chối kết nối. Dùng CA và khóa chỉ dành cho test; không sử dụng private key production trong test fixture. Kiểm tra riêng chứng thư hợp lệ để chứng minh test thất bại đúng vì hết hạn chứ không phải vì trust store hoặc hostname sai.

Nếu TLS kết thúc tại ingress, API gateway hoặc reverse proxy, chứng thư mà client nhìn thấy là chứng thư ở tầng đó. Kiểm thử endpoint public và kiểm tra cấu hình gia hạn/deploy tại đúng TLS terminator. Chứng thư nội bộ giữa proxy và ứng dụng là một kết nối TLS riêng và cần bộ test riêng nếu hệ thống bật TLS ở upstream.

### 7.2. Kiểm tra chứng thư client trong mTLS

Với mTLS, client trình chứng thư trong handshake. TLS terminator phải từ chối chứng thư hết hạn, chưa đến thời điểm có hiệu lực hoặc không nằm trong chuỗi CA tin cậy. Hãy kiểm thử ít nhất các trường hợp:

- Chứng thư client hợp lệ, đúng CA và đúng định danh được đăng ký: handshake thành công.
- Chứng thư client hết hạn: handshake thất bại trước khi token endpoint xử lý request.
- Chứng thư chưa có hiệu lực: handshake thất bại.
- Chứng thư được ký bởi CA không tin cậy: handshake thất bại.
- Chứng thư hợp lệ nhưng SAN/Subject không khớp client đã đăng ký: client authentication bị từ chối theo cơ chế mapping đang cấu hình.

Nếu reverse proxy kết thúc mTLS rồi chuyển danh tính client qua header, backend chỉ được tin header đó khi request chắc chắn đến từ proxy tin cậy. Proxy phải xóa header cùng tên do client Internet gửi lên, tự ghi giá trị sau khi xác minh chứng thư và bảo vệ đường truyền proxy-backend. Không để client có thể gọi trực tiếp backend và tự khai báo danh tính chứng thư bằng header.

Ví dụ gọi endpoint mTLS với chứng thư test:

```bash
curl --cacert test-ca.pem \
  --cert client-cert.pem \
  --key client-key.pem \
  https://auth.example.test/oauth2/token \
  -u mtls-client:unused \
  -d grant_type=client_credentials
```

Ví dụ này giả định endpoint yêu cầu cả mTLS và client authentication phù hợp với cấu hình thử nghiệm. Với `tls_client_auth`, cách định danh client dựa trên chứng thư cần khớp registration và cấu hình TLS của server. Không thêm HTTP Basic nếu client chỉ được cấu hình xác thực bằng chứng thư.

### 7.3. Kiểm thử certificate-bound access token

Nếu client đăng ký dùng chứng thư để ràng buộc access token, kiểm tra token có confirmation claim `cnf` với thumbprint chứng thư theo profile đang triển khai, thường là `x5t#S256`. Resource server phải đối chiếu chứng thư client trình trong request với thumbprint trong token.

Các ca kiểm thử nên gồm token được dùng với đúng chứng thư, token được dùng với một chứng thư khác nhưng đều hợp lệ, và chứng thư hết hạn. Chứng thư khác phải bị từ chối vì thumbprint không khớp; chứng thư hết hạn phải bị từ chối ở TLS handshake. Hai ca này chứng minh hai lớp kiểm soát khác nhau.

## 8. Kiểm soát thời gian trong test

Kiểm thử thời hạn thường dễ trở nên chậm và không ổn định nếu phụ thuộc `Thread.sleep`. Ưu tiên tạo fixture có timestamp quá khứ/tương lai đã biết, sau đó gọi đúng thành phần chịu trách nhiệm xác minh.

Với logic nghiệp vụ do ứng dụng tự viết, inject `Clock` để có thể dùng thời gian cố định trong test:

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;

@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

Trong test, thay bean bằng clock cố định hoặc clock có thể điều chỉnh, rồi xác minh hành vi ngay trước, đúng tại và ngay sau thời điểm hết hạn. Điều này đặc biệt hữu ích cho chính sách secret rotation, cảnh báo chứng thư sắp hết hạn và logic gia hạn do ứng dụng quản lý.

Không mặc định rằng mọi provider nội bộ của Spring Authorization Server đều sử dụng bean `Clock` của ứng dụng. Nếu provider dùng thời gian hệ thống nội bộ, clock test của ứng dụng không tự thay đổi hành vi đó. Với code/token do framework tạo, hãy dùng fixture authorization đã hết hạn, JWT đã ký có `exp` trong quá khứ hoặc test tích hợp với TTL ngắn và một khoảng chờ được kiểm soát. Tránh thay đồng hồ toàn hệ điều hành của môi trường CI.

Kiểm tra ba điểm biên cho mọi quy tắc thời hạn:

| Thời điểm | Kỳ vọng |
|---|---|
| Trước `expiresAt` | Credential còn hiệu lực |
| Tại hoặc sau `expiresAt` | Credential hết hạn theo quy tắc của thành phần xác minh |
| Sau `expiresAt` cộng clock skew (nếu có) | Credential bị từ chối sau khi vượt khoảng dung sai được cấu hình |

Với chứng thư X.509, điểm biên là `notBefore` và `notAfter`; với JWT, là `nbf` và `exp`; với client secret và authorization state, là timestamp được lưu trong repository. Ghi rõ timezone và dùng UTC để tránh lỗi chuyển đổi múi giờ hoặc daylight saving.

## 9. Ma trận test đề xuất

| Thành phần | Ca hợp lệ | Ca hết hạn | Kết quả mong đợi khi hết hạn |
|---|---|---|---|
| Authorization code | Đổi code còn hạn một lần | Đổi code có `expiresAt` trong quá khứ | Token endpoint trả `invalid_grant` |
| Authorization code replay | Đổi code lần đầu thành công | Gửi lại code đã dùng | Token endpoint trả `invalid_grant` |
| JWT access token | JWT có chữ ký hợp lệ và `exp` trong tương lai | JWT có chữ ký hợp lệ và `exp` quá hạn ngoài clock skew | Resource server trả 401 |
| Opaque access token | Introspection trả `active: true` | Introspection trả `active: false` | Resource server từ chối |
| Refresh token | Refresh token còn hạn | Refresh token có `expiresAt` trong quá khứ | Token endpoint trả `invalid_grant` |
| Client secret | Secret còn hạn và khớp | Secret khớp nhưng `clientSecretExpiresAt` đã qua | Client authentication trả `invalid_client` |
| TLS server certificate | Chain hợp lệ, hostname khớp, còn hạn | Chứng thư server hết hạn | TLS client từ chối handshake |
| TLS client certificate | Chứng thư mTLS hợp lệ và đúng client | Chứng thư client hết hạn | TLS terminator từ chối handshake |

Ngoài các test đơn lẻ, chạy test qua load balancer để xác minh mọi instance dùng chung chính sách và trạng thái. Một node không được chấp nhận credential đã hết hạn chỉ vì cache hoặc dữ liệu cục bộ cũ hơn node còn lại.

## 10. Những lỗi kiểm thử thường gặp

| Biểu hiện | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Test code hết hạn nhưng nhận `invalid_client` | Client secret hoặc client authentication fixture sai | Sửa fixture để xác thực client thành công trước khi kiểm tra code |
| Test JWT hết hạn nhưng token vẫn được chấp nhận ngay sau `exp` | Clock skew của resource server cho phép khoảng dung sai | Đặt `exp` quá xa trong quá khứ hoặc kiểm tra sau khi vượt clock skew |
| JWT hết hạn bị từ chối nhưng không rõ do `exp` | Chữ ký, issuer, audience hoặc thuật toán cũng sai | Dùng JWT test hợp lệ ở mọi thuộc tính khác và chỉ làm sai `exp` |
| Refresh token cũ vẫn dùng được trên node khác | Authorization store không dùng chung, cache stale hoặc cập nhật không nguyên tử | Kiểm tra persistence, transaction và invalidation giữa các node |
| Secret hết hạn vẫn được chấp nhận | `clientSecretExpiresAt` chưa được lưu hoặc repository/cache trả bản RegisteredClient cũ | Đọc lại client từ repository và kiểm tra cache của từng instance |
| Chứng thư hết hạn trả lỗi TLS thay vì JSON OAuth2 | TLS handshake đã từ chối trước khi HTTP request đến ứng dụng | Xác nhận đây là lớp xử lý đúng và kiểm tra log TLS terminator |
| Test mTLS hết hạn vẫn đi tới token endpoint | TLS bị kết thúc ở proxy khác hoặc proxy không yêu cầu client certificate | Kiểm tra nơi thực sự terminate TLS và cấu hình verify client certificate |
| Test chứng thư thất bại vì hostname thay vì ngày hết hạn | SAN không khớp hostname test | Dùng hostname khớp SAN để cô lập điều kiện hết hạn |
| Test thời hạn chập chờn trên CI | Dùng `sleep` quá ngắn hoặc đồng hồ giữa các node lệch nhau | Dùng fixture thời gian cố định, UTC và khoảng cách timestamp đủ lớn |

## 11. Checklist trước khi phát hành

- [ ] Xác nhận TTL access token và refresh token theo từng loại client.
- [ ] Kiểm tra `expiresAt` thực tế được lưu cùng authorization state.
- [ ] Authorization code hết hạn bị từ chối với `invalid_grant`.
- [ ] Authorization code đã sử dụng không thể replay ở cùng node hoặc node khác.
- [ ] JWT access token hết hạn bị resource server từ chối sau khoảng clock skew.
- [ ] Opaque access token hết hạn trả `active: false` khi introspection.
- [ ] Refresh token hết hạn, bị thu hồi hoặc đã xoay vòng bị từ chối.
- [ ] Client secret hết hạn trả `invalid_client`, kể cả khi secret gửi lên vẫn khớp.
- [ ] TLS server certificate hết hạn bị client từ chối khi kết nối endpoint public.
- [ ] TLS client certificate hết hạn bị TLS terminator từ chối trong luồng mTLS.
- [ ] Certificate-bound token được kiểm tra với đúng chứng thư và bị từ chối khi thumbprint không khớp.
- [ ] Test được chạy với cấu hình persistence/cache gần production và qua nhiều instance.
- [ ] Private key, client secret và token không xuất hiện trong log hoặc test report.

Một bộ test thời hạn đáng tin cậy phải chứng minh credential hợp lệ được chấp nhận, credential hết hạn bị từ chối tại đúng lớp chịu trách nhiệm, và trạng thái đó nhất quán giữa các instance. Khi tách riêng expiration, replay, revocation, credential mismatch và lỗi trust chain, kết quả kiểm thử sẽ chỉ ra chính xác chính sách bảo mật cần sửa.
