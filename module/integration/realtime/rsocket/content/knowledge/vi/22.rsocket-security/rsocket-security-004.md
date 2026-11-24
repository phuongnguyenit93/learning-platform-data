# Metadata xác thực dạng simple authentication và bearer token

RSocket mang thông tin xác thực trong metadata của SETUP hoặc trong metadata của một request. Spring Security tích hợp các metadata extension này với cơ chế xác thực reactive để chuyển credential thành Authentication, sau đó áp dụng quy tắc phân quyền cho route và interaction.

Hai cách phổ biến là Simple Authentication và Bearer Token Authentication. Simple Authentication gửi username/password theo định dạng metadata chuẩn của RSocket. Bearer Token gửi access token, thường là JWT, để server xác minh chữ ký và các claim trước khi tạo principal. Cả hai đều dùng MIME type xác thực của RSocket và có thể được gửi khi thiết lập connection hoặc theo từng request.

## 1. Authentication metadata trong RSocket

RSocket tách data và metadata trong mỗi payload. Data thường chứa nội dung nghiệp vụ; metadata chứa thông tin điều khiển hoặc ngữ cảnh như route, tracing và authentication.

Authentication metadata được nhận diện bằng MIME type chuẩn:

<code>message/x.rsocket.authentication.v0</code>

Trong Java có thể lấy MIME type này bằng <code>WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION</code>. Không nên tự tạo MIME type gần giống hoặc dùng các hằng số cũ đã deprecated.

Metadata xác thực có thể được gửi ở hai thời điểm:

| Thời điểm | Cách gửi | Trường hợp phù hợp |
| --- | --- | --- |
| Khi mở connection | <code>setupMetadata(...)</code> | Một connection gắn với một người dùng hoặc một danh tính dịch vụ. |
| Trong từng request | <code>metadata(...)</code> trên request spec | Một connection được nhiều người dùng hoặc nhiều principal chia sẻ. |
| Cả hai thời điểm | Credential dịch vụ trong SETUP và credential người dùng trong từng request | Server cần xác thực ứng dụng kết nối và người dùng cuối riêng biệt. |

Nếu xác thực tại SETUP, danh tính được gắn với connection và có thể được dùng cho các request tiếp theo trên connection đó. Nếu connection được chia sẻ giữa nhiều người dùng, gửi credential theo từng request giúp server xác định đúng principal của từng thao tác.

~~~text
Authentication tại SETUP
Client -- SETUP + authentication metadata --> Server
Client -- request A -----------------------> Server (principal của connection)
Client -- request B -----------------------> Server (principal của connection)

Authentication tại request
Client -- SETUP ---------------------------> Server
Client -- request A + token của user A ----> Server (principal A)
Client -- request B + token của user B ----> Server (principal B)
~~~

Authentication và authorization là hai bước riêng:

- Authentication xác minh credential và xác định principal là ai.
- Authorization kiểm tra principal có quyền thực hiện route hoặc thao tác đang yêu cầu hay không.

Một token hợp lệ không có nghĩa người dùng được phép gọi mọi route.

## 2. Phân biệt Simple Authentication và Bearer Token

| Tiêu chí | Simple Authentication | Bearer Token |
| --- | --- | --- |
| Credential | Username và password | Access token, thường là JWT |
| Metadata Java | <code>UsernamePasswordMetadata</code> | <code>BearerTokenMetadata</code> |
| Encoder client | <code>SimpleAuthenticationEncoder</code> | <code>BearerTokenAuthenticationEncoder</code> |
| Xác thực server | <code>simpleAuthentication(...)</code> | <code>jwt(...)</code> |
| Nguồn xác minh | <code>ReactiveUserDetailsService</code> hoặc <code>ReactiveAuthenticationManager</code> | <code>ReactiveJwtDecoder</code> và các validator |
| Trường hợp phù hợp | Hệ thống nội bộ, demo hoặc client đăng nhập bằng tài khoản | Tích hợp OAuth 2.0/OIDC, service-to-service hoặc client có access token |

Simple Authentication là extension xác thực riêng của RSocket, không phải HTTP Basic Authentication. RSocket Basic Authentication là bản draft cũ, đã được thay thế bởi Simple Authentication và chỉ còn hỗ trợ tương thích ngược. Các API <code>basicAuthentication(...)</code>, <code>BasicAuthenticationEncoder</code> cùng MIME type Basic cũ đã deprecated. Với dự án mới, hãy dùng Simple Authentication.

## 3. Simple Authentication Metadata Extension

Simple Authentication mang username và password trong một metadata entry. Định dạng trên dây gồm độ dài username bằng một byte, các byte UTF-8 của username, sau đó là các byte UTF-8 của password.

Spring Security cung cấp hai kiểu chính:

- <code>UsernamePasswordMetadata</code> giữ username và password ở phía client.
- <code>SimpleAuthenticationEncoder</code> mã hóa đối tượng này thành metadata theo extension chuẩn.

MIME type dùng cho entry xác thực là <code>message/x.rsocket.authentication.v0</code>.

Ví dụ tạo credential:

~~~java
UsernamePasswordMetadata credentials =
    new UsernamePasswordMetadata(username, password);

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);
~~~

Không tự ghép chuỗi username:password, không Base64 credential theo cách của HTTP Basic và không dùng <code>UsernamePasswordMetadata.BASIC_AUTHENTICATION_MIME_TYPE</code>. Hãy để encoder của Spring Security tạo định dạng metadata đúng.

### 3.1. Cấu hình Simple Authentication ở server

Thêm các dependency Spring Security RSocket và messaging cùng với starter RSocket và Security. Khi dùng Spring Boot dependency management, không cần tự gắn version riêng cho từng artifact.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-rsocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-messaging</artifactId>
    </dependency>
</dependencies>
~~~

Khai báo <code>@EnableRSocketSecurity</code> và tạo <code>PayloadSocketAcceptorInterceptor</code>:

~~~java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .simpleAuthentication(Customizer.withDefaults())
            .authorizePayload(authorize -> authorize
                .setup().authenticated()
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            );

        return rsocket.build();
    }
}
~~~

<code>simpleAuthentication(...)</code> cài đặt bộ chuyển đổi authentication metadata để Spring Security đọc <code>UsernamePasswordMetadata</code> và xác thực credential. Quy tắc <code>setup().authenticated()</code> yêu cầu danh tính hợp lệ ngay khi mở connection; <code>anyRequest().authenticated()</code> yêu cầu request có metadata phải có principal đã xác thực.

<code>anyExchange().permitAll()</code> trong ví dụ cho phép những exchange không khớp các quy tắc phía trên. Nếu ứng dụng cần chính sách mặc định chặt hơn, hãy thay bằng quy tắc phù hợp và kiểm tra cả SETUP, request lẫn các payload tiếp theo của request-channel. Các quy tắc được xét theo thứ tự; quy tắc khớp đầu tiên được áp dụng.

Spring Boot có thể tự gắn <code>SecuritySocketAcceptorInterceptor</code> vào RSocket server khi các dependency tích hợp phù hợp được đưa vào classpath. Nếu không dùng Boot auto-configuration, cần đăng ký interceptor với <code>RSocketServerCustomizer</code> để nó thực sự tham gia xử lý connection.

### 3.2. Nguồn người dùng và PasswordEncoder

Trong ví dụ nhỏ, có thể dùng <code>MapReactiveUserDetailsService</code>. Mật khẩu lưu trữ phải được hash bằng <code>PasswordEncoder</code>; không lưu mật khẩu thô trong database hoặc file cấu hình.

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
MapReactiveUserDetailsService userDetailsService(
        PasswordEncoder passwordEncoder) {

    UserDetails user = User.withUsername("rsocket-client")
        .password(passwordEncoder.encode(passwordFromSecretStore))
        .roles("USER")
        .build();

    return new MapReactiveUserDetailsService(user);
}
~~~

<code>passwordFromSecretStore</code> đại diện cho mật khẩu được lấy từ secret store hoặc cấu hình bảo mật. Đây là cấu hình minh họa cho một tài khoản. Trong production, nên dùng nguồn người dùng reactive thực tế, quản lý vòng đời tài khoản, khóa tài khoản, đổi mật khẩu và chính sách credential theo yêu cầu của hệ thống. Không dùng <code>User.withDefaultPasswordEncoder()</code> cho ứng dụng production.

<code>PasswordEncoder</code> bảo vệ mật khẩu được lưu trữ. Nó không mã hóa mật khẩu khi truyền trên mạng; transport vẫn cần TLS.

### 3.3. Gửi username/password trong SETUP

Client phải đăng ký <code>SimpleAuthenticationEncoder</code> trong <code>RSocketStrategies</code>. Nếu ứng dụng đã có JSON hoặc CBOR codec, hãy bổ sung encoder xác thực vào cùng bộ strategies để không làm mất codec nghiệp vụ.

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> {
        encoders.add(new Jackson2JsonEncoder());
        encoders.add(new SimpleAuthenticationEncoder());
    })
    .decoders(decoders -> {
        decoders.add(new Jackson2JsonDecoder());
    })
    .build();

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);

UsernamePasswordMetadata credentials =
    new UsernamePasswordMetadata(username, password);

Mono<RSocketRequester> requester = RSocketRequester.builder()
    .setupMetadata(credentials, authenticationMimeType)
    .rsocketStrategies(strategies)
    .connectTcp("localhost", 7000);
~~~

Khi client kết nối, credential được gửi trong SETUP. Server xác thực trước khi chấp nhận connection theo quy tắc đã cấu hình. Nếu credential sai hoặc tài khoản không hợp lệ, quá trình thiết lập có thể bị từ chối.

Với WebSocket, thay transport TCP bằng endpoint WebSocket tương ứng. Cách mã hóa Simple Authentication metadata không thay đổi theo transport; đường truyền production vẫn cần TLS, thường là <code>wss://</code> cho WebSocket.

### 3.4. Gửi username/password trong từng request

Nếu một RSocket connection được chia sẻ giữa nhiều người dùng, không nên xác thực một người dùng duy nhất ở SETUP rồi dùng chung principal đó cho mọi người. Thay vào đó, gửi credential trong metadata của request:

~~~java
Mono<OrderView> result = requester
    .route("orders.find")
    .metadata(credentials, authenticationMimeType)
    .data(new OrderQuery("ORD-2026-018"))
    .retrieveMono(OrderView.class);
~~~

Server dùng cùng <code>simpleAuthentication(...)</code> để giải mã metadata xác thực ở request. Mỗi request có thể được xác thực theo người dùng tương ứng.

Với cách này, chính sách server phải cho phép SETUP chưa xác thực bằng <code>setup().permitAll()</code> trong khi vẫn yêu cầu <code>anyRequest().authenticated()</code>. Mẫu cấu hình request-level ở phần 7 áp dụng cho cả Simple Authentication và Bearer Token.

Gửi username/password ở mọi request làm tăng số lần truyền credential và yêu cầu bảo vệ transport nghiêm ngặt. Với hệ thống có authorization server, access token thường phù hợp hơn cho mô hình connection chia sẻ.

## 4. Bearer Token Authentication Metadata Extension

Bearer token cho phép client chứng minh quyền truy cập bằng access token do authorization server cấp. Trong Spring Security RSocket, cấu hình <code>.jwt(...)</code> hỗ trợ xác minh JWT và sử dụng các claim/authority của token cho authorization.

Các kiểu Java thường dùng:

- <code>BearerTokenMetadata</code> giữ token dạng chuỗi.
- <code>BearerTokenAuthenticationEncoder</code> mã hóa token thành bearer authentication metadata.
- <code>ReactiveJwtDecoder</code> xác minh và giải mã JWT ở server.

MIME type chuẩn vẫn là <code>message/x.rsocket.authentication.v0</code>, lấy từ <code>WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION</code>. Không dùng <code>BearerTokenMetadata.BEARER_AUTHENTICATION_MIME_TYPE</code> vì hằng số này đã deprecated.

Token truyền vào <code>BearerTokenMetadata</code> là giá trị access token thô, không thêm tiền tố chuỗi <code>Bearer </code>. Encoder chịu trách nhiệm tạo định dạng metadata theo extension.

## 5. Cấu hình JWT ở server

Để xác minh JWT bằng Spring Security, thêm OAuth 2.0 Resource Server starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Khai báo <code>ReactiveJwtDecoder</code> trỏ tới issuer của authorization server:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    return ReactiveJwtDecoders.fromIssuerLocation(
        "https://identity.example.com/issuer"
    );
}
~~~

Thay URL minh họa bằng issuer URI thật. Spring Security dùng metadata của issuer để tìm khóa xác minh và tạo decoder phù hợp. Nếu không dùng OIDC discovery, có thể cấu hình decoder theo khóa công khai hoặc cơ chế xác minh riêng.

Kích hoạt JWT authentication trong RSocket Security:

~~~java
@Configuration
@EnableRSocketSecurity
public class RSocketJwtSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .jwt(Customizer.withDefaults())
            .authorizePayload(authorize -> authorize
                .setup().permitAll()
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            );

        return rsocket.build();
    }
}
~~~

Ví dụ này cho phép SETUP chưa xác thực và yêu cầu các request có metadata phải được xác thực bằng bearer token. Nếu muốn xác thực ngay khi tạo connection, thay <code>setup().permitAll()</code> bằng <code>setup().authenticated()</code> và gửi token trong SETUP.

<code>jwt(Customizer.withDefaults())</code> tự cấu hình converter để đọc bearer authentication metadata và sử dụng <code>ReactiveJwtDecoder</code> có trong application context. Nếu không có decoder phù hợp, cấu hình JWT không thể xác minh token.

DSL <code>.jwt(...)</code> tập trung vào JWT. Nếu authorization server cấp opaque access token, hãy dùng cơ chế introspection hoặc một <code>ReactiveAuthenticationManager</code> tùy chỉnh thay vì cố giải mã token đó bằng <code>ReactiveJwtDecoder</code>.

## 6. Gửi bearer token từ client

Client cần đăng ký <code>BearerTokenAuthenticationEncoder</code> trong <code>RSocketStrategies</code>:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> {
        encoders.add(new Jackson2JsonEncoder());
        encoders.add(new BearerTokenAuthenticationEncoder());
    })
    .decoders(decoders -> {
        decoders.add(new Jackson2JsonDecoder());
    })
    .build();

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);

BearerTokenMetadata token = new BearerTokenMetadata(accessToken);

Mono<RSocketRequester> requester = RSocketRequester.builder()
    .setupMetadata(token, authenticationMimeType)
    .rsocketStrategies(strategies)
    .connectTcp("localhost", 7000);
~~~

Ví dụ gửi token ngay trong SETUP. Token được lấy từ luồng đăng nhập hoặc OAuth 2.0 client của ứng dụng; không hard-code token vào source code.

Nếu cần gửi token theo từng request:

~~~java
Mono<OrderView> order = requester
    .route("orders.find")
    .metadata(
        new BearerTokenMetadata(accessToken),
        authenticationMimeType
    )
    .data(new OrderQuery("ORD-2026-018"))
    .retrieveMono(OrderView.class);
~~~

Encoder <code>BearerTokenAuthenticationEncoder</code> cần có trong strategies của requester để Spring ghi token theo định dạng bearer extension. Nếu chỉ gửi một <code>String</code> thông thường mà không dùng đúng encoder/metadata format, server có thể không nhận diện được token.

## 7. Chọn xác thực tại SETUP hay từng request

Lựa chọn thời điểm xác thực phụ thuộc vào cách ứng dụng sử dụng connection:

| Mô hình | Cách xác thực | Lợi ích | Điều cần cân nhắc |
| --- | --- | --- | --- |
| Mobile client riêng biệt | Token hoặc credential ở SETUP | Xác thực một lần cho connection của người dùng | Khi đổi người dùng hoặc credential, cần quản lý lại connection. |
| Backend dùng chung một connection | Token trên từng request | Mỗi request mang principal của người dùng cuối | Client phải gắn đúng token cho từng request. |
| Service identity + user identity | Credential dịch vụ ở SETUP, token người dùng ở request | Tách quyền kết nối dịch vụ và quyền thao tác người dùng | Cần quy tắc authorization cho cả hai lớp. |

Spring Security hỗ trợ xác thực ở SETUP, request time hoặc cả hai. Ví dụ, connection chỉ được mở bởi một service có authority <code>SETUP</code>, trong khi từng người dùng cuối được xác thực riêng trên các request. Như vậy, người dùng cuối không cần có quyền tạo connection mới.

### Quy tắc cho SETUP và request

Nếu xác thực tại SETUP:

~~~java
.authorizePayload(authorize -> authorize
    .setup().authenticated()
    .anyRequest().authenticated()
    .anyExchange().permitAll()
)
~~~

Nếu xác thực theo từng request và cho phép tạo connection trước:

~~~java
.authorizePayload(authorize -> authorize
    .setup().permitAll()
    .anyRequest().authenticated()
    .anyExchange().permitAll()
)
~~~

<code>anyRequest()</code> khớp các request exchange; <code>anyExchange()</code> là quy tắc dự phòng cho các exchange còn lại. Vì vậy, cần hiểu rõ những payload nào mang metadata và thứ tự áp dụng rule. Với request-channel, request đầu tiên mở interaction và các payload tiếp theo có thể không mang metadata xác thực riêng; nếu mỗi phần tử cần quyết định quyền độc lập, hãy bổ sung kiểm tra quyền ở tầng nghiệp vụ cho từng phần tử.

## 8. Phân quyền theo route và authority

Sau khi xác thực thành công, Spring Security đưa principal và authority vào security context của exchange. <code>authorizePayload</code> cho phép giới hạn quyền theo route, role hoặc authority.

Ví dụ:

~~~java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    rsocket
        .jwt(Customizer.withDefaults())
        .authorizePayload(authorize -> authorize
            .setup().authenticated()
            .route("admin.users.delete").hasRole("ADMIN")
            .route("orders.read").hasAuthority("SCOPE_orders.read")
            .route("orders.write").hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated()
            .anyExchange().permitAll()
        );

    return rsocket.build();
}
~~~

Các route cụ thể phải được đặt trước <code>anyRequest()</code> vì rule được xét theo thứ tự và chỉ rule đầu tiên khớp được thực thi. <code>hasRole("ADMIN")</code> kiểm tra authority <code>ROLE_ADMIN</code>; <code>hasAuthority("SCOPE_orders.read")</code> kiểm tra đúng chuỗi authority.

Với JWT resource server, Spring Security mặc định ánh xạ scope trong claim thành authority có tiền tố <code>SCOPE_</code>. Nếu authorization server dùng claim hoặc quy ước role riêng, hãy cấu hình JWT authentication converter để ánh xạ claim thành authority theo hợp đồng của ứng dụng.

Không chỉ dựa vào route để quyết định quyền truy cập dữ liệu. Ví dụ route <code>orders.read</code> có thể được gọi hợp lệ nhưng service vẫn phải kiểm tra người dùng có quyền xem đúng <code>orderId</code> trong payload và đơn hàng có thuộc tenant tương ứng hay không.

## 9. Kiểm tra và xác thực JWT

JWT thường có ba phần được mã hóa Base64URL: header, payload và signature. Chữ ký giúp server xác minh token được phát hành bởi issuer đáng tin cậy và nội dung chưa bị sửa đổi. JWT dạng JWS không mã hóa payload; người có token có thể đọc các claim.

Các thuộc tính quan trọng cần xác minh:

| Thuộc tính | Mục đích |
| --- | --- |
| Signature | Xác minh token được ký bởi khóa đáng tin cậy. |
| <code>iss</code> | Xác minh issuer đúng authorization server. |
| <code>exp</code> | Từ chối token đã hết hạn. |
| <code>nbf</code> | Không chấp nhận token trước thời điểm bắt đầu hiệu lực. |
| <code>aud</code> | Xác minh token được cấp cho resource server hiện tại. |
| <code>scope</code> hoặc role claims | Ánh xạ quyền để authorization. |

<code>ReactiveJwtDecoders.fromIssuerLocation(...)</code> là cách khởi tạo thuận tiện cho issuer có discovery metadata. Nếu hệ thống yêu cầu audience cụ thể, hãy thêm validator cho <code>aud</code> thay vì cho rằng chỉ kiểm tra chữ ký và issuer đã đủ.

Không đưa mật khẩu, secret hoặc dữ liệu nhạy cảm vào JWT payload. Hạn chế ghi token vào log, trace, exception message hoặc metric label.

## 10. Vòng đời access token và connection

Bearer token có thời hạn và có thể bị thu hồi. Ứng dụng cần phối hợp vòng đời token với vòng đời RSocket connection:

1. Client lấy access token từ authorization server theo OAuth 2.0/OIDC flow phù hợp.
2. Client gửi token trong SETUP hoặc metadata của từng request.
3. Server xác minh token và áp dụng authorization.
4. Khi token sắp hết hạn, client lấy token mới theo cơ chế OAuth đã cấu hình.
5. Nếu xác thực theo từng request, client dùng token mới cho các request tiếp theo.
6. Nếu xác thực ở SETUP, ứng dụng cần có chính sách đổi hoặc tái thiết lập connection khi danh tính/credential cần được xác minh lại.

Không gửi refresh token trong metadata RSocket như một access token. Refresh token chỉ nên được dùng với authorization server theo flow được thiết kế. Access token là credential dạng bearer: ai lấy được token có thể thử sử dụng nó trong thời hạn hiệu lực.

Đối với hệ thống cần thu hồi quyền tức thời, không chỉ dựa vào thời hạn JWT. Có thể cần token lifetime ngắn, introspection hoặc cơ chế thu hồi/denylist phù hợp, tùy mô hình bảo mật.

## 11. Bảo vệ credential trên transport

Simple Authentication gửi username và password trong metadata theo định dạng giao thức; bản thân extension không mã hóa credential. Bearer token cũng là credential dạng bearer và có thể bị sử dụng lại nếu bị lộ.

Vì vậy:

- Dùng TLS cho TCP và WSS cho WebSocket trong môi trường production.
- Không coi Base64, encoding metadata hoặc chữ ký JWT là mã hóa đường truyền.
- Không ghi username/password, access token hoặc refresh token vào log.
- Không đặt credential trong route, data nghiệp vụ hoặc query parameter.
- Lưu password bằng password hash chuyên dụng như BCrypt hoặc Argon2 thông qua <code>PasswordEncoder</code>.
- Cấp JWT với scope và thời hạn tối thiểu cần thiết.
- Xác minh issuer, audience, expiry và quyền trước khi xử lý nghiệp vụ.
- Xử lý token refresh và connection close theo chính sách thống nhất.

Nếu client/server kết nối qua proxy hoặc gateway, cần bảo đảm TLS được kết thúc ở một điểm tin cậy và đoạn truyền tiếp theo cũng được bảo vệ. Không để metadata xác thực đi qua một hop nội bộ không mã hóa.

## 12. Kiểm thử authentication và authorization

Kiểm thử cần xác nhận credential được mã hóa đúng, server xác thực đúng và route bị từ chối khi principal không đủ quyền.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Simple Authentication hợp lệ | Gửi <code>UsernamePasswordMetadata</code> đúng username/password | SETUP hoặc request được xác thực. |
| Simple Authentication sai password | Gửi password không khớp | Connection hoặc request bị từ chối theo thời điểm xác thực. |
| Thiếu authentication metadata | Gọi route yêu cầu authenticated | Authorization từ chối. |
| JWT hợp lệ | Gửi bearer token có chữ ký và claim hợp lệ | Principal được tạo và route cho phép truy cập. |
| JWT hết hạn | Gửi token có <code>exp</code> trong quá khứ | Authentication thất bại. |
| JWT sai issuer hoặc audience | Gửi token không thuộc resource server | Decoder/validator từ chối. |
| JWT thiếu scope | Gọi route yêu cầu scope cụ thể | Authentication có thể hợp lệ nhưng authorization bị từ chối. |
| Token đổi theo request | Dùng một connection chung và hai principal | Mỗi request được xác thực bằng token tương ứng. |
| Route quản trị | Principal không có <code>ROLE_ADMIN</code> gọi <code>admin.*</code> | Access bị từ chối. |
| Channel nhiều phần tử | Gửi request-channel sau khi xác thực request mở đầu | Xác nhận rõ chính sách cho các payload tiếp theo. |

Với unit test, có thể kiểm thử <code>ReactiveAuthenticationManager</code>, <code>ReactiveJwtDecoder</code> và converter. Với integration test, mở RSocket client/server thật để xác nhận metadata đi qua encoder, decoder, authentication interceptor và authorization rule.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Server không đọc được username/password | Chưa đăng ký <code>SimpleAuthenticationEncoder</code> hoặc MIME type sai. | Thêm encoder vào <code>RSocketStrategies</code> và dùng <code>MESSAGE_RSOCKET_AUTHENTICATION</code>. |
| Simple Authentication bị từ chối dù password đúng | UserDetailsService không tìm thấy user hoặc password hash không khớp. | Kiểm tra user lookup và <code>PasswordEncoder</code>. |
| Bearer token không được nhận diện | Thiếu <code>BearerTokenAuthenticationEncoder</code> hoặc metadata không đúng định dạng. | Đăng ký encoder và dùng <code>BearerTokenMetadata</code>. |
| JWT luôn bị từ chối | Thiếu <code>ReactiveJwtDecoder</code>, sai issuer hoặc khóa xác minh. | Kiểm tra discovery URI, JWK Set và validator. |
| JWT hợp lệ nhưng route bị từ chối | Authority không khớp với rule. | Kiểm tra scope/role mapping và thứ tự authorization rule. |
| Kết nối được tạo nhưng request không được phép | Chỉ cho phép SETUP, chưa cấu hình rule cho request. | Thêm <code>anyRequest()</code> hoặc route rule phù hợp. |
| Người dùng A nhìn thấy dữ liệu người dùng B | Nhiều người dùng dùng chung connection đã xác thực ở SETUP. | Xác thực theo từng request và kiểm tra quyền ở service. |
| Token bị lộ trong log | Log toàn bộ metadata hoặc object credential. | Che credential và loại token khỏi log/trace. |
| Credential truyền qua mạng dạng đọc được | Dùng TCP/WS không TLS. | Cấu hình TLS/WSS và xác minh chứng thư. |

## 14. Checklist triển khai

- [ ] Chọn Simple Authentication hoặc Bearer Token theo mô hình danh tính của client.
- [ ] Dùng MIME type <code>message/x.rsocket.authentication.v0</code>.
- [ ] Với Simple Authentication, đăng ký <code>SimpleAuthenticationEncoder</code>.
- [ ] Với bearer token, đăng ký <code>BearerTokenAuthenticationEncoder</code>.
- [ ] Cấu hình server bằng <code>simpleAuthentication(...)</code> hoặc <code>jwt(...)</code>.
- [ ] Cung cấp <code>ReactiveUserDetailsService</code> hoặc <code>ReactiveJwtDecoder</code> tương ứng.
- [ ] Định nghĩa rõ xác thực tại SETUP hay tại từng request.
- [ ] Viết authorization rule cho route, setup và các exchange không có metadata.
- [ ] Xác minh issuer, audience, expiry và scope của JWT.
- [ ] Dùng TLS/WSS và không log credential.
- [ ] Kiểm thử credential sai, token hết hạn, thiếu scope và request-channel.
- [ ] Xác định chính sách token refresh, thu hồi và connection lifecycle.

## 15. Ghi nhớ

- Simple Authentication dùng <code>UsernamePasswordMetadata</code> và <code>SimpleAuthenticationEncoder</code>; không dùng API Basic Authentication cũ đã deprecated.
- Bearer token dùng <code>BearerTokenMetadata</code> và <code>BearerTokenAuthenticationEncoder</code>; token truyền vào là giá trị thô, không thêm tiền tố <code>Bearer </code>.
- MIME type chuẩn cho authentication metadata là <code>message/x.rsocket.authentication.v0</code>, lấy qua <code>WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION</code>.
- Server bật <code>.simpleAuthentication(...)</code> cho username/password hoặc <code>.jwt(...)</code> cho JWT; JWT cần <code>ReactiveJwtDecoder</code>.
- Xác thực ở SETUP phù hợp với một principal trên một connection; xác thực ở từng request phù hợp với connection được nhiều người dùng chia sẻ.
- <code>authorizePayload</code> phân quyền theo setup, route, request và exchange; rule được xét theo thứ tự.
- JWT chữ ký không đồng nghĩa payload được mã hóa; cần TLS/WSS để bảo vệ credential trên đường truyền.
- Authentication không thay thế authorization ở route và kiểm tra quyền trên tài nguyên nghiệp vụ.

## Tài liệu tham khảo

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security — RSocketSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security — SimpleAuthenticationEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Security — BearerTokenAuthenticationEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/rsocket/metadata/BearerTokenAuthenticationEncoder.html)
- [Spring Security — UsernamePasswordMetadata API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/rsocket/metadata/UsernamePasswordMetadata.html)
- [Spring Security — BearerTokenMetadata API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/rsocket/metadata/BearerTokenMetadata.html)
- [RSocket — Authentication Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Security/README.md)
