# TLS, danh tính kết nối và quyền trên từng yêu cầu

> Phạm vi: bảo vệ kết nối RSocket bằng TLS, xác thực danh tính ở thời điểm thiết lập kết nối hoặc trên từng request, và phân quyền theo route, principal cùng dữ liệu nghiệp vụ trong Spring Security.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt TLS, xác thực (authentication) và phân quyền (authorization).
- Chọn thời điểm xác thực phù hợp: lúc gửi `SETUP`, trên từng request, hoặc kết hợp cả hai.
- Cấu hình TLS cho RSocket TCP và RSocket qua WebSocket trong Spring Boot.
- Hiểu vai trò của chứng thư máy chủ, trust store và mutual TLS (mTLS).
- Cấu hình Spring Security RSocket bằng `@EnableRSocketSecurity`, `RSocketSecurity` và `PayloadSocketAcceptorInterceptor`.
- Viết quy tắc quyền theo setup, route, role và ngữ cảnh của request.
- Xử lý đúng tình huống một kết nối được dùng chung bởi nhiều người dùng.

## 2. Ba lớp bảo vệ cần phân biệt

Một hệ thống RSocket an toàn thường cần ba lớp phối hợp:

| Lớp | Câu hỏi được trả lời | Cơ chế điển hình |
| --- | --- | --- |
| Bảo vệ đường truyền | Dữ liệu có bị nghe lén hoặc sửa trên mạng không? Máy chủ có đúng là máy chủ cần kết nối không? | TLS, chứng thư X.509, kiểm tra hostname |
| Xác thực | Ai đang kết nối hoặc đang gửi request? | JWT, bearer token, username/password metadata, client certificate đã được ánh xạ thành principal |
| Phân quyền | Danh tính đó được phép làm hành động nào trên tài nguyên nào? | Role, authority, route rule, kiểm tra tenant hoặc quyền sở hữu dữ liệu |

TLS bảo vệ kênh truyền. Nó không tự quyết định người dùng có được đọc một tài khoản hay xóa một đơn hàng hay không. Tương tự, một JWT hợp lệ chứng minh danh tính và các claim của token theo chính sách xác minh; ứng dụng vẫn phải quyết định quyền truy cập tài nguyên.

RSocket là giao thức ứng dụng chạy trên một transport như TCP hoặc WebSocket. Vì vậy, TLS được cấu hình ở transport. Metadata xác thực của RSocket được xử lý ở lớp giao thức/ứng dụng. Khi không có TLS, token hoặc dữ liệu nhạy cảm nằm trong payload metadata có thể bị quan sát trên đường truyền.

## 3. TLS cho RSocket

### 3.1. TLS bảo vệ điều gì?

TLS tạo một kênh mã hóa giữa hai đầu transport. Trong cấu hình TLS thông thường:

1. Máy khách xác minh chứng thư máy chủ được ký bởi CA mà nó tin cậy.
2. Máy khách kiểm tra hostname của máy chủ khớp với danh tính trong chứng thư.
3. Hai phía thương lượng phiên mã hóa và khóa phiên.
4. Dữ liệu truyền qua kênh được bảo vệ tính bí mật và tính toàn vẹn.

TLS một chiều thường xác thực máy chủ. Với mutual TLS (mTLS), máy chủ cũng yêu cầu máy khách trình chứng thư; máy chủ kiểm tra chứng thư đó bằng trust store. mTLS phù hợp cho giao tiếp service-to-service hoặc môi trường cần danh tính workload ở tầng transport.

Chứng thư TLS đại diện cho một endpoint hoặc workload. Nó không mặc nhiên đại diện cho người dùng cuối đang sử dụng endpoint đó. Nếu một gateway dùng một chứng thư để mở kết nối RSocket rồi chuyển tiếp request của nhiều người dùng, chứng thư chỉ nhận diện gateway. Muốn phân quyền theo từng người dùng, cần thêm danh tính ở từng request hoặc một cơ chế truyền danh tính đã được xác thực và tin cậy.

### 3.2. Cấu hình TLS cho RSocket TCP độc lập bằng Spring Boot

Với RSocket server độc lập, Spring Boot hỗ trợ các thuộc tính `spring.rsocket.server.ssl.*`. Ví dụ dùng PKCS12 keystore cho chứng thư máy chủ và trust store chứa CA ký chứng thư máy khách:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
      ssl:
        enabled: true
        key-store: classpath:rsocket-server.p12
        key-store-type: PKCS12
        key-store-password: ${RSOCKET_KEYSTORE_PASSWORD}
        trust-store: classpath:rsocket-client-ca.p12
        trust-store-type: PKCS12
        trust-store-password: ${RSOCKET_TRUSTSTORE_PASSWORD}
        client-auth: need
```

`client-auth: need` yêu cầu client gửi chứng thư và server xác minh nó theo trust store. Cấu hình này bật mTLS. Nếu chỉ cần TLS một chiều, có thể bỏ trust store và đặt `client-auth: none` hoặc dùng mặc định phù hợp của phiên bản Boot đang chạy.

Không đặt mật khẩu keystore trực tiếp trong file cấu hình được commit. Dùng biến môi trường, secret manager hoặc cơ chế quản lý secret của nền tảng triển khai. Bảo vệ private key và giới hạn quyền đọc file chứng thư.

Các thuộc tính trên thuộc Spring Boot và server RSocket độc lập. Nếu RSocket được gắn vào WebFlux Web Server bằng WebSocket mapping path, endpoint chia sẻ TLS connector của web server; cấu hình chứng thư bằng `server.ssl.*` của web server. Client kết nối bằng URL `wss://...`. Không cấu hình nhầm SSL của một RSocket server độc lập cho endpoint WebSocket đang dùng chung cổng HTTPS.

### 3.3. Cấu hình TLS ở client TCP

Khi cần trust store tùy chỉnh hoặc mTLS ở client, có thể tạo một `ClientTransport` từ Reactor Netty `TcpClient` đã bật TLS, rồi truyền transport đó cho `RSocketRequester.Builder`:

```java
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import io.rsocket.transport.ClientTransport;
import io.rsocket.transport.netty.client.TcpClientTransport;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.netty.tcp.TcpClient;

import java.io.File;

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("certs/server-ca.pem"))
        .build();

TcpClient tcpClient = TcpClient.create()
        .host("rsocket.example.com")
        .port(9898)
        .secure(ssl -> ssl.sslContext(sslContext));

ClientTransport transport = TcpClientTransport.create(tcpClient);

RSocketRequester requester = RSocketRequester.builder()
        .transport(transport);
```

Đây là ví dụ transport phía client; ứng dụng vẫn cần thiết lập metadata, codec và xử lý vòng đời kết nối theo contract của mình. `trustManager` cung cấp CA mà client tin cậy. Với mTLS, thêm client certificate và private key vào SSL context:

```java
SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("certs/server-ca.pem"))
        .keyManager(
                new File("certs/client.crt"),
                new File("certs/client.key"))
        .build();
```

Phía server phải bật client authentication và tin cậy CA đã ký `client.crt`. Không tắt xác minh chứng thư hoặc hostname để khắc phục lỗi kết nối trong production. Hãy sửa chuỗi certificate, trust store, hostname hoặc cấu hình TLS cho đúng.

### 3.4. TLS qua WebSocket

Nếu RSocket chạy trên WebSocket, dùng `wss://` để bảo vệ WebSocket bằng TLS. Khi Spring Boot tích hợp RSocket vào WebFlux Web Server, cấu hình TLS trên web server, ví dụ:

```yaml
server:
  ssl:
    enabled: true
    key-store: classpath:web-server.p12
    key-store-type: PKCS12
    key-store-password: ${WEB_KEYSTORE_PASSWORD}

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

Client dùng endpoint tương ứng, ví dụ `wss://api.example.com/rsocket`. Nếu TLS được kết thúc ở load balancer hoặc ingress, cần xác định rõ đoạn nào được mã hóa. Nếu proxy chuyển tiếp tới service qua mạng nội bộ, hãy bảo vệ hop nội bộ bằng TLS hoặc một ranh giới mạng được kiểm soát và xác minh phù hợp.

## 4. Danh tính ở thời điểm thiết lập kết nối

### 4.1. SETUP và connection-level identity

Khi mở một kết nối RSocket, client gửi frame `SETUP`. Frame này có thể chứa data và metadata ban đầu. `RSocketRequester.Builder` cung cấp các phương thức:

- `setupData(Object)`: data cho frame `SETUP`.
- `setupMetadata(Object, MimeType)`: metadata cho frame `SETUP`.
- `setupRoute(String, Object...)`: route gắn với `SETUP` nếu ứng dụng sử dụng.

Phía responder có thể xử lý sự kiện bắt đầu kết nối bằng `@ConnectMapping`. Spring Security cũng có thể xác thực metadata ở `SETUP` và áp dụng quy tắc riêng bằng `authorizePayload(...).setup()`.

Xác thực tại `SETUP` phù hợp khi một kết nối đại diện cho đúng một principal trong suốt vòng đời kết nối, ví dụ ứng dụng di động mở một kết nối riêng cho người dùng đang đăng nhập. Sau khi kết nối được xác thực, các request trên kết nối có thể sử dụng identity đã gắn với connection theo cấu hình security.

Điểm cần quản lý là vòng đời của kết nối. Khi người dùng đăng xuất, token hết hạn, quyền bị thu hồi hoặc người dùng đổi tài khoản, ứng dụng cần đóng hoặc tái xác thực kết nối theo chính sách. Một kết nối lâu dài không nên giữ identity cũ vô thời hạn.

### 4.2. Khi nào connection-level identity không đủ?

Giả sử một backend gateway mở một kết nối RSocket dùng chung đến service đích. Hàng trăm người dùng cuối gửi request qua gateway đó. Ở tầng transport và `SETUP`, service đích chỉ thấy một kết nối của gateway.

Nếu chỉ xác thực ở `SETUP`, mọi request qua cùng kết nối có thể bị nhìn nhận dưới danh tính của gateway. Service đích không thể phân biệt người dùng A với người dùng B để kiểm tra quyền sở hữu dữ liệu của từng người.

Trong tình huống này, cần xác thực trên từng request bằng token hoặc metadata danh tính riêng. Không lấy user id từ data payload hay route rồi tin trực tiếp giá trị đó; requester có thể tự sửa giá trị. Danh tính phải đến từ credential được xác minh bởi server.

## 5. Xác thực trên từng request

### 5.1. Request metadata

Metadata của request đầu tiên chứa thông tin định tuyến và có thể chứa credential. Với composite metadata, một request có thể mang nhiều entry có MIME type riêng, ví dụ route và bearer authentication metadata.

Spring Security hỗ trợ Simple Authentication Metadata Extension và Bearer Token Authentication Metadata Extension. Với ứng dụng mới, bearer token/JWT thường phù hợp hơn khi hệ thống đã có OAuth 2.0 hoặc OpenID Connect issuer.

### 5.2. Gửi bearer token trên mỗi request

Ví dụ client gắn JWT vào metadata cho từng request:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
        "message/x.rsocket.authentication.v0");

BearerTokenMetadata userToken = new BearerTokenMetadata(jwtForCurrentUser);

Mono<AccountView> result = requester
        .route("account.read.{accountId}", accountId)
        .metadata(userToken, authenticationMimeType)
        .retrieveMono(AccountView.class);
```

Ví dụ tập trung vào phần metadata của request. `jwtForCurrentUser` phải là token do hệ thống xác thực cấp và còn hiệu lực. Phía server cần cấu hình JWT decoder và quy tắc phân quyền tương ứng. Không ghi token vào log, exception message hoặc metric label.

Nếu dùng username/password metadata, Spring Security cung cấp `simpleAuthentication()` và client có thể đăng ký `SimpleAuthenticationEncoder` trong `RSocketStrategies`. Simple Authentication phù hợp với một số hệ thống nội bộ; Basic Authentication metadata cũ chỉ còn hỗ trợ tương thích ngược. Không tự xây một định dạng mật khẩu riêng trong metadata.

## 6. Spring Security RSocket

### 6.1. Các thành phần chính

| Thành phần | Vai trò |
| --- | --- |
| `@EnableRSocketSecurity` | Bật hạ tầng bảo mật RSocket trong Spring Security |
| `RSocketSecurity` | DSL cấu hình xác thực và phân quyền payload |
| `AuthenticationPayloadInterceptor` | Chuyển credential trong payload thành `Authentication` thông qua `ReactiveAuthenticationManager` |
| `AuthorizationPayloadInterceptor` | Áp dụng quyền trên `PayloadExchange` thông qua `ReactiveAuthorizationManager` |
| `PayloadSocketAcceptorInterceptor` | Kết hợp các payload interceptor cho RSocket |
| `SecuritySocketAcceptorInterceptor` | Nối payload security interceptor với RSocket server acceptor |
| `ReactiveJwtDecoder` | Xác minh và giải mã JWT |

Với Spring Boot và các dependency RSocket/Spring Security phù hợp, Boot tự đăng ký `SecuritySocketAcceptorInterceptor` thông qua auto-configuration. Nếu không dùng auto-configuration của Boot, cần gắn interceptor vào server.

### 6.2. Cấu hình JWT và authorization theo payload

Ví dụ sau minh họa một service yêu cầu scope `rsocket.connect` để mở kết nối, xác thực JWT cho request, kiểm tra authority theo route và từ chối exchange không có quy tắc phù hợp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
                "https://identity.example.com");
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketSecurity(
            RSocketSecurity rsocket) {
        rsocket
            .authorizePayload(authz -> authz
                .setup().hasAuthority("SCOPE_rsocket.connect")
                .route("account.read.{accountId}")
                    .access((authentication, context) ->
                        checkAccountAccess(authentication, context))
                .route("admin.user.delete")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().authenticated()
                .anyExchange().denyAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
```

Đây là cấu hình minh họa; `checkAccountAccess(authentication, context)` là hàm kiểm tra nghiệp vụ của ứng dụng, cần được triển khai với quyền truy cập dữ liệu thực tế. JWT decoder lấy issuer từ URL đã cấu hình, xác minh chữ ký và các điều kiện token theo cấu hình của Spring Security.

Ví dụ dùng `hasAuthority("SCOPE_...")` vì JWT authentication mặc định của Spring Security ánh xạ scope thành authority có tiền tố `SCOPE_`. Nếu token dùng claim `roles` hoặc tên authority riêng, cần cấu hình converter tương ứng; khi đó mới dùng `hasRole(...)` nếu authority được ánh xạ theo quy ước `ROLE_...`.

Quy tắc `setup().hasAuthority("SCOPE_rsocket.connect")` bảo vệ thao tác mở kết nối. Trong mô hình kết hợp, client gửi một token service có scope `rsocket.connect` ở `SETUP`, sau đó gửi JWT của người dùng trên từng request. Token service không thay thế token người dùng.

Nếu ứng dụng không cần xác thực danh tính ở `SETUP`, có thể cho phép setup theo chính sách của hệ thống rồi yêu cầu xác thực ở request. Không giữ rule setup yêu cầu scope nếu client không gửi credential có scope đó, vì kết nối sẽ bị từ chối ngay khi thiết lập.

### 6.3. Gửi token ở SETUP và trên từng request

Trong mô hình gateway dùng chung kết nối, client có thể gửi token của workload lúc setup và token người dùng ở request:

```java
MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
        "message/x.rsocket.authentication.v0");

BearerTokenMetadata serviceToken =
        new BearerTokenMetadata(jwtForGateway);

RSocketRequester requester = RSocketRequester.builder()
        .setupMetadata(serviceToken, authenticationMimeType)
        .transport(secureTransport);

BearerTokenMetadata userToken =
        new BearerTokenMetadata(jwtForCurrentUser);

Mono<AccountView> account = requester
        .route("account.read.{accountId}", accountId)
        .metadata(userToken, authenticationMimeType)
        .retrieveMono(AccountView.class);
```

Token trong `SETUP` chỉ nên cấp quyền cần thiết để tạo kết nối. Token trong request xác định người dùng đang thực hiện thao tác cụ thể. Service kiểm tra cả quyền kết nối và quyền của người dùng đối với route/tài nguyên.

Đối với một kết nối riêng cho một người dùng, có thể xác thực tại `SETUP` và áp dụng `.anyRequest().authenticated()` cho request. Đối với kết nối chia sẻ, cần xác thực mỗi request hoặc truyền identity người dùng bằng một cơ chế được xác minh tương đương.

### 6.4. Simple Authentication

Nếu dùng username/password metadata, cấu hình server có thể dùng:

```java
rsocket
    .authorizePayload(authz -> authz
        .anyRequest().authenticated()
        .anyExchange().denyAll()
    )
    .simpleAuthentication(Customizer.withDefaults());
```

Client cần đăng ký encoder tương ứng:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoder(new SimpleAuthenticationEncoder())
        .build();
```

Khi gửi credential trong `SETUP`, dùng `setupMetadata(credentials, authenticationMimeType)`. Khi gửi trên request, dùng `.metadata(credentials, authenticationMimeType)`. Credential phải được bảo vệ bằng TLS và xác minh qua `ReactiveAuthenticationManager`/user store. Không dùng mật khẩu mặc định hoặc mật khẩu hard-code trong production.

## 7. Quyền theo từng request

### 7.1. Phân quyền theo route

`authorizePayload` cho phép viết các quy tắc dựa trên `PayloadExchange`. Những trường hợp thường gặp:

- `.setup()`: áp dụng cho frame thiết lập kết nối.
- `.route("...")`: áp dụng cho route cụ thể hoặc route pattern.
- `.anyRequest()`: áp dụng cho request có metadata khởi tạo request.
- `.anyExchange()`: áp dụng cho exchange còn lại, kể cả payload không có metadata tương ứng.

Các quy tắc được đánh giá theo thứ tự khai báo. Quy tắc đầu tiên khớp sẽ được áp dụng. Vì vậy, đặt route cụ thể trước quy tắc tổng quát và kết thúc bằng chính sách mặc định rõ ràng, thường là yêu cầu authenticated hoặc deny.

Ví dụ:

```java
.authorizePayload(authz -> authz
    .setup().hasAuthority("SCOPE_rsocket.connect")
    .route("profile.me").authenticated()
    .route("admin.user.delete").hasAuthority("SCOPE_admin")
    .anyRequest().authenticated()
    .anyExchange().denyAll()
)
```

Ở ví dụ này, route `profile.me` yêu cầu danh tính đã xác thực; route xóa user yêu cầu authority `SCOPE_admin`; request khác phải authenticated; exchange không khớp và không có metadata bị từ chối. Hãy thiết kế rule theo API thực tế và tránh để một rule tổng quát cho phép truy cập trước rule nhạy cảm.

### 7.2. Quyền theo tài nguyên, tenant và chủ sở hữu

Role thường chỉ mô tả quyền ở mức rộng. Ví dụ, role `USER` có thể cho phép đọc một số tài nguyên, nhưng không có nghĩa người dùng được đọc mọi tài khoản.

Với route `account.read.{accountId}`, ứng dụng cần xác minh:

1. JWT có chữ ký hợp lệ, chưa hết hạn và đúng issuer/audience theo chính sách.
2. Principal có authority cho hành động đọc tài khoản.
3. `accountId` tồn tại và thuộc tenant hoặc người dùng mà principal được phép truy cập.
4. Quyền vẫn còn hiệu lực theo trạng thái nghiệp vụ hiện tại.

Spring Security cho phép dùng `.access((authentication, context) -> ...)` để thực hiện kiểm tra tùy chỉnh. Biến route, ví dụ `accountId`, có thể được đọc từ authorization context. Không tin giá trị account id do client gửi chỉ vì route đã khớp.

Kiểm tra quyền sở hữu cần được thực hiện ở tầng service/domain hoặc trong custom authorization manager, nơi có thể truy vấn quyền thật. Nếu chỉ kiểm tra `hasRole("USER")`, mọi người dùng cùng role có thể vô tình đọc tài nguyên của nhau.

### 7.3. AuthenticationPrincipal trong handler

Handler có thể cần biết principal để ghi audit hoặc truyền ngữ cảnh vào service. Spring Security cung cấp `AuthenticationPrincipalArgumentResolver`; nếu cấu hình messaging handler không tự đăng ký resolver này, cần thêm vào `RSocketMessageHandler` thông qua `ArgumentResolverConfigurer`.

Một lựa chọn khác trong reactive code là lấy security context bằng `ReactiveSecurityContextHolder` trong reactive chain. Không lưu principal của một request vào biến mutable dùng chung trên singleton controller, vì nhiều request có thể chạy đồng thời trên cùng kết nối.

## 8. Connection identity và per-request identity: chọn mô hình

| Tình huống | Xác thực tại SETUP | Xác thực trên request | Lý do |
| --- | --- | --- | --- |
| Một người dùng, một kết nối riêng | Phù hợp | Có thể không cần nếu identity được gắn an toàn với connection | Principal ổn định trong vòng đời kết nối |
| Gateway dùng chung một kết nối cho nhiều người dùng | Dùng cho danh tính gateway/workload nếu cần | Cần thiết để phân biệt người dùng | Một connection không đại diện cho một end-user duy nhất |
| Service-to-service với mTLS | TLS/mTLS xác minh workload | Có thể thêm JWT khi cần quyền theo thao tác | Chứng thư nhận diện workload; token có thể mang quyền ứng dụng |
| Kết nối WebSocket từ trình duyệt | Có thể xác thực lúc setup | Thường dùng token theo request khi có nhiều user qua gateway | Cookie/HTTP handshake và identity request cần được thiết kế đồng bộ |

Mô hình kết hợp thường hữu ích: mTLS hoặc token service giới hạn workload nào được mở kết nối; JWT theo request xác định người dùng và quyền cho từng thao tác. Mỗi lớp cần có chính sách riêng và không được mặc định kế thừa quyền từ lớp khác.

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| TLS handshake thất bại | Server certificate không được tin cậy, thiếu intermediate certificate hoặc protocol/cipher không tương thích | Kiểm tra certificate chain, trust store và TLS protocol ở cả hai phía |
| Hostname verification thất bại | Host dùng để kết nối không khớp SAN trong chứng thư | Dùng DNS name khớp chứng thư hoặc cấp lại certificate đúng SAN |
| mTLS bị từ chối | Client không gửi certificate hoặc server không tin CA ký certificate | Kiểm tra `client-auth`, trust store và client key pair |
| Kết nối thành công nhưng request bị từ chối | Credential thiếu, token sai issuer/audience, hết hạn hoặc thiếu authority | Kiểm tra JWT decoder, claim mapping và rule đang khớp |
| Mọi user qua gateway có cùng quyền | Chỉ xác thực danh tính gateway tại SETUP | Gửi credential người dùng đã xác minh trên từng request |
| User A đọc được dữ liệu của user B | Chỉ kiểm tra role, không kiểm tra owner/tenant | Thêm kiểm tra object-level authorization |
| Route nhạy cảm bị rule tổng quát cho phép | Rule rộng đứng trước rule cụ thể hoặc fallback quá rộng | Sắp xếp lại rule; dùng default deny khi phù hợp |
| Token lộ trong log | Log toàn bộ metadata hoặc exception payload | Redact credential và giới hạn dữ liệu log |
| Quyền cũ còn hiệu lực trên kết nối dài hạn | Chỉ xác thực tại setup nhưng không xử lý token expiry/revocation | Đặt tuổi thọ kết nối, reconnect hoặc xác thực lại theo request |

Một số lệnh kiểm tra TLS ở mức transport:

```bash
openssl s_client -connect rsocket.example.com:9898 \
  -servername rsocket.example.com -showcerts
```

Lệnh này giúp kiểm tra TLS handshake, certificate chain và hostname ở mức OpenSSL. Nó không chứng minh RSocket `SETUP`, MIME type, authentication metadata hoặc authorization rule hoạt động đúng. Sau khi TLS pass, cần chạy kiểm thử RSocket thực tế.

## 10. Kiểm thử bảo mật

Một bộ integration test nên bao gồm các trường hợp:

1. Kết nối TLS với certificate hợp lệ thành công.
2. Certificate không được tin cậy hoặc hostname sai bị từ chối.
3. Với mTLS, client không có certificate bị từ chối khi server yêu cầu `client-auth: need`.
4. Credential tại `SETUP` thiếu authority kết nối bị từ chối.
5. JWT hết hạn, sai issuer hoặc sai chữ ký không được xác thực.
6. Request thiếu token bị từ chối với route yêu cầu authenticated.
7. Người dùng thường không gọi được route admin.
8. Hai người dùng cùng role không truy cập được tài nguyên thuộc tenant/người dùng còn lại.
9. Request không khớp rule bị xử lý theo fallback policy đã chọn.
10. Kết nối dùng chung gửi token riêng cho từng request và server phân biệt đúng principal.
11. Token không xuất hiện trong application log, trace attribute hoặc metric label.

Nên kiểm thử cả trường hợp reconnect và token hết hạn trên kết nối dài hạn. Một bài test đơn lẻ cho thấy request đầu tiên thành công chưa đủ để xác nhận chính sách identity vẫn đúng sau khi kết nối tồn tại lâu.

## 11. Checklist triển khai

- [ ] TLS được bật trên transport RSocket hoặc WebSocket endpoint tương ứng.
- [ ] Client xác minh certificate chain và hostname của server.
- [ ] Private key và keystore password được lưu trong secret manager hoặc môi trường bảo mật.
- [ ] Nếu dùng mTLS, server yêu cầu client certificate và trust đúng CA.
- [ ] Ứng dụng phân biệt rõ danh tính workload với danh tính người dùng cuối.
- [ ] Đã quyết định xác thực ở SETUP, request hay cả hai.
- [ ] Spring Security RSocket interceptor được gắn vào server.
- [ ] JWT decoder kiểm tra issuer, chữ ký, thời hạn và audience theo yêu cầu hệ thống.
- [ ] Rule route cụ thể đứng trước rule tổng quát.
- [ ] Có fallback policy rõ ràng cho request không khớp.
- [ ] Kiểm tra quyền theo tenant/owner đối với tài nguyên cụ thể.
- [ ] Có chính sách hết hạn, thu hồi credential và reconnect cho kết nối dài hạn.
- [ ] Log và trace đã loại bỏ token, password và metadata nhạy cảm.
- [ ] Có integration test cho TLS, authentication, authorization và connection sharing.

## 12. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): transport, SETUP, requester, metadata và annotated responders.
- [Spring Security Reference — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): setup-vs-request authentication, Simple Authentication, JWT và authorizePayload.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): RSocket server auto-configuration và transport.
- [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.rsocket.server.ssl.*` và `server.ssl.*`.
- [Reactor Netty Reference — TCP Server](https://projectreactor.io/docs/netty/release/reference/tcp-server.html): TLS context cho TCP server.
- [Reactor Netty Reference — TCP Client](https://projectreactor.io/docs/netty/release/reference/tcp-client.html): TLS context cho TCP client.
- [RSocket Protocol](https://github.com/rsocket/rsocket/blob/master/Protocol.md): SETUP, request frames, transport và payload.

Các ví dụ cấu hình Boot sử dụng thuộc tính của Spring Boot hiện hành; API cụ thể có thể khác giữa các nhánh Spring Framework, Spring Security, Spring Boot và RSocket Java. Luôn đối chiếu dependency version thực tế của dự án trước khi sao chép cấu hình.
