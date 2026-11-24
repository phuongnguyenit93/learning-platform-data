# Xác thực ở bước SETUP, từng yêu cầu hoặc kết hợp cả hai

RSocket cho phép xác thực ở nhiều thời điểm trong vòng đời kết nối. Ứng dụng có thể xác thực một lần khi gửi frame `SETUP`, xác thực lại danh tính trên từng request, hoặc kết hợp cả hai để kiểm soát cả kết nối lẫn người dùng đang sử dụng kết nối đó.

Lựa chọn phụ thuộc vào cách chia sẻ kết nối. Nếu một kết nối chỉ phục vụ một người dùng hoặc một thiết bị, xác thực ở `SETUP` thường phù hợp. Nếu một kết nối được nhiều người dùng chia sẻ, thông tin xác thực nên đi theo từng request. Với kiến trúc gateway hoặc service-to-service, có thể dùng credential ở `SETUP` để xác thực ứng dụng mở kết nối và credential riêng trên từng request để xác thực người dùng cuối.

## 1. Phân biệt xác thực và phân quyền

Hai bước này giải quyết hai câu hỏi khác nhau:

- **Authentication (xác thực):** peer là ai? Ví dụ user, thiết bị hoặc service nào đang kết nối/gửi request?
- **Authorization (phân quyền):** danh tính đó được phép làm gì? Ví dụ có được gọi route `orders.create`, xem dữ liệu tenant hay điều khiển thiết bị hay không?

Một JWT hợp lệ chỉ chứng minh token được phát hành bởi issuer đáng tin cậy và còn hiệu lực theo các điều kiện kiểm tra. Server vẫn phải áp dụng authorization rules và kiểm tra quyền truy cập tài nguyên cụ thể.

RSocket là giao thức hai chiều và multiplex nhiều stream trên một kết nối. Một kết nối TCP hoặc WebSocket có thể mang request của nhiều người dùng nếu ứng dụng chủ động chia sẻ requester. Vì vậy không nên mặc định một kết nối luôn tương ứng với một user.

## 2. Ba mô hình xác thực

### 2.1. Xác thực ở SETUP

Client gửi credential trong metadata của frame `SETUP` khi mở kết nối. Server xác thực credential trước khi chấp nhận phiên; danh tính được xác thực gắn với ngữ cảnh kết nối và có thể được dùng cho các request tiếp theo.

Mô hình này phù hợp khi:

- Một người dùng hoặc một thiết bị sở hữu riêng kết nối RSocket.
- Kết nối có vòng đời gắn với phiên đăng nhập hoặc phiên thiết bị.
- Các request trên kết nối đều thuộc cùng một danh tính.
- Muốn từ chối ngay kết nối không có credential hợp lệ.

Ví dụ, ứng dụng mobile đăng nhập rồi mở một RSocket connection riêng. Các stream realtime trên kết nối đó đều hoạt động dưới danh tính của người dùng đã đăng nhập.

Hạn chế: nếu một kết nối được nhiều user dùng chung, danh tính ở `SETUP` chỉ đại diện cho chủ thể mở kết nối. Không thể dùng nó để phân biệt từng user cuối nếu không có credential riêng theo request.

### 2.2. Xác thực trên từng request

Client gửi credential trong metadata của từng request. Server xác thực từng request độc lập, vì vậy nhiều người dùng có thể dùng chung một kết nối nhưng vẫn có danh tính và quyền khác nhau.

Mô hình này phù hợp khi:

- Một web application hoặc gateway duy trì một kết nối tới RSocket server cho nhiều người dùng.
- Mỗi request có thể thuộc một user, tenant hoặc workload khác nhau.
- Token có thể thay đổi trong khi kết nối vẫn được giữ nguyên.
- Cần kiểm tra trạng thái credential ở mỗi lần gọi.

Chi phí xác thực có thể cao hơn vì server xử lý credential nhiều lần. Có thể tối ưu bằng cache hoặc cơ chế xác minh phù hợp, nhưng cache phải tôn trọng thời hạn token, thu hồi quyền và ranh giới giữa các user.

Ở đây, “từng request” là từng interaction được khởi tạo bằng `REQUEST_RESPONSE`, `REQUEST_FNF`, `REQUEST_STREAM` hoặc `REQUEST_CHANNEL`. Với stream hoặc channel, authentication metadata nằm ở request mở đầu interaction; các `PAYLOAD` tiếp theo trong cùng stream không phải request mới và không tự kích hoạt xác thực lại. Nếu mỗi message trong một channel cần danh tính riêng, hãy mang token hoặc chữ ký ở cấp message và tự xác minh trong logic ứng dụng.

### 2.3. Kết hợp SETUP và từng request

Một gateway có thể mở kết nối bằng credential của chính ứng dụng, sau đó gửi credential của user cuối trong từng request:

- Credential ở `SETUP` chứng minh gateway hoặc service được phép mở kết nối.
- Credential trên request xác định người dùng cuối đang thực hiện thao tác.
- Authorization có thể yêu cầu cả quyền kết nối `ROLE_SETUP` lẫn quyền riêng của user như `ROLE_ORDER_READ`.

Ví dụ, gateway có quyền kết nối tới RSocket server nhưng không có quyền tự ý đọc đơn hàng của mọi user. Mỗi request cần mang JWT của user và server kiểm tra quyền trên route tương ứng.

```text
Gateway / RSocket client                 RSocket server
          |                                      |
          |---- SETUP + service credential ---->|
          |                                      | xác thực service
          |<----------- connection ready -------|
          |                                      |
          |---- REQUEST + user A JWT ----------->|
          |                                      | xác thực user A
          |                                      | kiểm tra quyền route
          |<----------- response A --------------|
          |                                      |
          |---- REQUEST + user B JWT ----------->|
          |                                      | xác thực user B
          |                                      | kiểm tra quyền route
          |<----------- response B --------------|
```

Mô hình này tách rõ quyền mở kết nối khỏi quyền thực hiện nghiệp vụ. Credential ở `SETUP` không thay thế credential của từng user khi kết nối được chia sẻ.

## 3. Credential được gửi qua metadata

Spring Security RSocket hỗ trợ các authentication metadata extension. Cách hiện đại nên ưu tiên là Simple Authentication Metadata Extension hoặc Bearer Token Authentication Metadata Extension.

Với JWT bearer token, Spring Security sử dụng `BearerPayloadExchangeConverter` để lấy token từ metadata và `ReactiveJwtDecoder` để xác minh chữ ký, issuer, thời hạn và các điều kiện JWT được cấu hình.

Ví dụ tạo MIME type authentication:

```java
MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
```

Với Simple Authentication, credential thường là username/password được mã hóa theo extension. Không tự đặt một MIME type tùy ý rồi giả định Spring Security sẽ hiểu nó. Client và server phải dùng cùng extension và encoder/decoder tương ứng.

Không gửi credential trong route, query string hoặc log. Khi truyền username/password hoặc bearer token, kết nối phải được bảo vệ bằng TLS; RSocket qua TCP hay WebSocket không tự động mã hóa dữ liệu ứng dụng nếu transport không bật TLS.

## 4. Cấu hình Spring Security RSocket

Thêm dependency Spring Security RSocket và cấu hình `@EnableRSocketSecurity`. Với JWT, ứng dụng cần có `ReactiveJwtDecoder` để xác minh token.

Ví dụ cấu hình authorization:

```java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(RSocketSecurity rsocket) {
        rsocket
                .authorizePayload(authorize -> authorize
                        .setup().hasRole("SETUP")
                        .route("admin.*").hasRole("ADMIN")
                        .anyRequest().authenticated()
                        .anyExchange().permitAll()
                )
                .jwt(Customizer.withDefaults());

        return rsocket.build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
                "https://identity.example.com/realms/platform");
    }
}
```

Các rule được xét theo thứ tự; rule đầu tiên khớp sẽ được áp dụng. Trong ví dụ:

- `setup().hasRole("SETUP")`: chỉ principal có authority `ROLE_SETUP` mới được thiết lập kết nối.
- `route("admin.*").hasRole("ADMIN")`: các route admin yêu cầu `ROLE_ADMIN`.
- `anyRequest().authenticated()`: các request còn lại có metadata yêu cầu danh tính đã xác thực.
- `anyExchange().permitAll()`: các exchange không khớp các rule trước được cho phép; nếu ứng dụng không có exchange công khai, hãy thay bằng chính sách chặt hơn.

`jwt()` bật xử lý bearer token cho payload exchange. Token có thể được gửi ở `SETUP`, trên request hoặc cả hai, tùy mô hình mà ứng dụng lựa chọn. Nếu dùng Simple Authentication thay cho JWT, cấu hình `.simpleAuthentication(Customizer.withDefaults())` và cung cấp `ReactiveUserDetailsService` hoặc cơ chế xác thực phù hợp.

Có thể thu hẹp policy theo từng mô hình. Với một user riêng trên mỗi kết nối, xác thực tại `SETUP` rồi dùng danh tính kết nối cho các request:

```java
.authorizePayload(authorize -> authorize
        .setup().authenticated()
        .anyRequest().authenticated()
        .anyExchange().denyAll())
.jwt(Customizer.withDefaults());
```

Với kết nối chia sẻ, cho phép mở transport session nhưng yêu cầu credential trên từng request:

```java
.authorizePayload(authorize -> authorize
        .setup().permitAll()
        .anyRequest().authenticated()
        .anyExchange().denyAll())
.jwt(Customizer.withDefaults());
```

Với mô hình kết hợp, dùng `setup().hasRole("SETUP")` và `anyRequest().authenticated()` như cấu hình đầy đủ ở trên. Các đoạn trích này là phần cấu hình DSL bên trong bean `PayloadSocketAcceptorInterceptor`; chúng cần được ghép vào `RSocketSecurity` và có authentication mechanism tương ứng. Nếu có route công khai hoặc exchange không mang metadata, hãy thêm rule cụ thể cho chúng thay vì nới lỏng fallback toàn cục.

Spring Boot tự đăng ký `SecuritySocketAcceptorInterceptor` khi có các dependency cần thiết. Nếu tự cấu hình RSocket server ngoài auto-configuration, cần gắn interceptor vào socket acceptor:

```java
@Bean
RSocketServerCustomizer springSecurityRSocketSecurity(
        SecuritySocketAcceptorInterceptor interceptor) {
    return server -> server.interceptors(
            registry -> registry.forSocketAcceptor(interceptor));
}
```

Nếu interceptor không được gắn vào server, việc khai báo `@EnableRSocketSecurity` và bean policy chưa đủ để bảo vệ traffic thực tế.

## 5. Gửi credential ở SETUP

Với mô hình một user hoặc một thiết bị trên mỗi kết nối, client gửi token khi tạo requester:

```java
MimeType authMimeType = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata setupToken = new BearerTokenMetadata(accessToken);

Mono<RSocketRequester> requester = RSocketRequester.builder()
        .setupMetadata(setupToken, authMimeType)
        .connectTcp("rsocket.example.com", 7000);
```

`setupMetadata(...)` thêm authentication metadata vào frame `SETUP`. Server xác thực credential trong quá trình thiết lập phiên. Nếu credential không hợp lệ hoặc không có quyền thiết lập, kết nối bị từ chối.

Khi kết nối chỉ thuộc một user, các request sau đó có thể sử dụng danh tính đã được xác thực trong ngữ cảnh kết nối. Tuy nhiên, vẫn phải áp dụng authorization cho từng route; xác thực thành công không có nghĩa user được phép gọi mọi chức năng.

Với WebSocket, cách thêm setup metadata tương tự; chỉ khác phương thức mở transport. Không đưa token vào URL WebSocket vì URL có thể xuất hiện trong access log, proxy log hoặc lịch sử trình duyệt.

## 6. Gửi credential trên từng request

Với kết nối được chia sẻ, client gắn token của user vào từng request:

```java
public Mono<OrderView> findOrder(
        RSocketRequester requester,
        String orderId,
        String userAccessToken) {

    MimeType authMimeType = MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    return requester
            .route("orders.find")
            .metadata(new BearerTokenMetadata(userAccessToken), authMimeType)
            .data(new FindOrder(orderId))
            .retrieveMono(OrderView.class);
}
```

Server xác thực token gắn với request đó. Request của user A và user B có thể đi qua cùng một TCP/WebSocket connection nhưng được xử lý với hai `Authentication` khác nhau.

Không lưu user token của request trước vào biến mutable gắn với requester dùng chung. Nếu làm vậy, hai request đồng thời có thể ghi đè danh tính của nhau và gây lỗi phân tách quyền. Hãy gắn credential vào từng request immutable và để Spring Security tạo security context theo payload exchange.

## 7. Kết hợp credential ở SETUP và từng request

Ví dụ gateway dùng service token khi mở kết nối và user token cho từng request:

```java
MimeType authMimeType = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

Mono<RSocketRequester> sharedRequester = RSocketRequester.builder()
        .setupMetadata(new BearerTokenMetadata(serviceAccessToken), authMimeType)
        .connectTcp("rsocket.example.com", 7000);
```

Khi xử lý từng user request:

```java
Mono<OrderView> response = sharedRequester.flatMap(requester ->
        requester.route("orders.find")
                .metadata(new BearerTokenMetadata(userAccessToken), authMimeType)
                .data(new FindOrder(orderId))
                .retrieveMono(OrderView.class));
```

Phía server có thể yêu cầu `ROLE_SETUP` ở bước kết nối và yêu cầu user đã xác thực cho mỗi request. Service token cần có authority dành riêng cho setup; user token mang các authority nghiệp vụ. Không cấp `ROLE_SETUP` cho user cuối chỉ để họ có thể sử dụng một kết nối do gateway quản lý.

Trong ví dụ này, cả hai credential dùng JWT bearer để cùng một cấu hình `.jwt(...)` xác minh. Nếu dùng hai cơ chế xác thực khác nhau, cần cấu hình các converter/interceptor tương ứng và kiểm tra thứ tự interceptor; không giả định mọi authentication metadata có thể được xử lý đồng thời mà không cấu hình.

## 8. Simple Authentication với username/password

Spring Security hỗ trợ Simple Authentication Metadata Extension. Phía gửi có thể thêm `SimpleAuthenticationEncoder` vào `RSocketStrategies`:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoder(new SimpleAuthenticationEncoder())
        .build();
```

Sau đó gửi username/password trong `SETUP`:

```java
MimeType authMimeType = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

UsernamePasswordMetadata credentials =
        new UsernamePasswordMetadata("device-agent", devicePassword);

Mono<RSocketRequester> requester = RSocketRequester.builder()
        .setupMetadata(credentials, authMimeType)
        .rsocketStrategies(strategies)
        .connectTcp("rsocket.example.com", 7000);
```

Phía server cấu hình:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(RSocketSecurity rsocket) {
    rsocket
            .authorizePayload(authorize -> authorize
                    .anyRequest().authenticated()
                    .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults());

    return rsocket.build();
}
```

Simple Authentication phù hợp với một số hệ thống username/password hoặc thiết bị. Với hệ thống phân tán có identity provider và token ngắn hạn, JWT bearer thường thuận tiện hơn. Basic Authentication Metadata Extension cũ đã được thay bằng Simple Authentication và chỉ nên giữ để tương thích hệ thống cũ; không bắt đầu thiết kế mới dựa trên API Basic đã deprecated.

## 9. Authorization theo SETUP và route

Authentication tạo ra principal và authorities. `authorizePayload` quyết định principal đó được làm gì.

Ví dụ chính sách route:

```java
rsocket.authorizePayload(authorize -> authorize
        .setup().hasRole("SETUP")
        .route("orders.create").hasAuthority("ORDER_WRITE")
        .route("orders.*").hasAuthority("ORDER_READ")
        .route("admin.*").hasRole("ADMIN")
        .anyRequest().authenticated()
        .anyExchange().denyAll());
```

Các rule được đánh giá theo thứ tự. Đặt rule cụ thể trước rule tổng quát để tránh `orders.*` bắt request trước khi tới rule `orders.create`. Cần thống nhất cách chuyển claim trong JWT thành authority; ví dụ claim `scope` có thể được ánh xạ thành authority có tiền tố `SCOPE_`, trong khi `hasRole("ADMIN")` mặc định kiểm tra `ROLE_ADMIN`.

Route authorization chưa đủ để bảo vệ tài nguyên theo tenant hoặc owner. Ví dụ hai user đều có `ORDER_READ`, nhưng user A không được đọc đơn hàng của user B. Service cần lấy principal đã xác thực và kiểm tra quyền trên `orderId` thực tế.

## 10. Chọn mô hình nào?

| Tiêu chí | SETUP | Từng request | Kết hợp |
| --- | --- | --- | --- |
| Phạm vi danh tính | Toàn kết nối | Từng request | Service/connection và user/request |
| Một kết nối phục vụ nhiều user | Không phù hợp nếu chỉ có setup identity | Phù hợp | Phù hợp |
| Chi phí xác thực | Thấp hơn sau khi kết nối mở | Xác thực mỗi request | Cả kết nối và request |
| Thay đổi user giữa các request | Không tự nhiên | Có | Có |
| Kiểm soát service mở kết nối | Có | Không trực tiếp | Có |
| Ví dụ | Mobile app, thiết bị riêng | Gateway đa người dùng | Gateway gọi service nội bộ |

Một số câu hỏi giúp quyết định:

1. Một kết nối có thể được dùng bởi nhiều người dùng cuối không?
2. Danh tính có thể thay đổi trong khi kết nối vẫn mở không?
3. Server có cần xác minh danh tính của service/gateway trước khi chấp nhận kết nối không?
4. Khi token hết hạn hoặc bị thu hồi, hệ thống cần ngắt kết nối hay chỉ từ chối request tiếp theo?
5. Có yêu cầu audit để biết chính xác user nào thực hiện từng thao tác không?

Nếu câu trả lời cho câu đầu là có, không dựa riêng vào danh tính ở `SETUP`. Nếu cần giới hạn cả service mở kết nối lẫn user thao tác, chọn mô hình kết hợp.

## 11. Token hết hạn, thu hồi và vòng đời kết nối

Xác thực ở `SETUP` diễn ra một lần khi mở kết nối. Việc token hết hạn sau đó không tự động có nghĩa Spring Security sẽ xác thực lại credential setup trên từng request. Nếu chính sách yêu cầu token setup hết hạn phải chấm dứt phiên, ứng dụng cần quản lý thời hạn session, đóng kết nối hoặc buộc client reconnect bằng credential mới.

Với xác thực từng request, JWT được kiểm tra khi request mang token được xử lý. Token hết hạn sẽ khiến request đó thất bại, trong khi các stream khác trên cùng connection có thể tiếp tục nếu chính sách và trạng thái kết nối cho phép.

Khi dùng mô hình kết hợp:

- Theo dõi thời hạn service credential ở `SETUP` và vòng đời kết nối.
- Kiểm tra user token ở từng request.
- Khi service credential bị thu hồi, đóng hoặc thay thế kết nối theo chính sách.
- Khi user token hết hạn, chỉ làm mới credential của user đó; không cần thay danh tính service nếu kết nối vẫn hợp lệ.
- Khi logout, thu hồi session hoặc thay đổi quyền, áp dụng chính sách revoke rõ ràng thay vì giả định mọi connection context tự cập nhật.

Đối với JWT offline validation, việc thu hồi token trước `exp` có thể không được nhận biết ngay nếu không có denylist, introspection hoặc cơ chế kiểm tra bổ sung. Cần cân nhắc thời hạn token ngắn, cache có giới hạn và chiến lược đóng session.

## 12. Bảo vệ credential trên transport và trong log

Metadata authentication là dữ liệu truyền qua kết nối. Hãy bật TLS cho TCP hoặc WSS cho WebSocket khi credential đi qua mạng không hoàn toàn tin cậy.

- Không ghi bearer token, username/password hoặc raw authentication metadata vào log.
- Không đưa token vào route, URL hoặc query parameter.
- Không chia sẻ một mutable token holder giữa nhiều user request đồng thời.
- Giới hạn kích thước metadata và từ chối credential có định dạng bất thường.
- Dùng issuer, audience, signature algorithm và thời hạn JWT được cấu hình rõ ràng.
- Xác minh quyền trên tài nguyên ở server; không tin role hoặc tenant ID do client tự khai trong data.
- Không dùng TLS thay cho authentication/authorization; TLS bảo vệ kênh truyền, còn Spring Security xác định danh tính và quyền.

## 13. Kiểm thử xác thực ở SETUP và từng request

Kiểm thử cần bao gồm cả credential hợp lệ, không hợp lệ và ranh giới giữa các user trên một kết nối chia sẻ.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| SETUP token hợp lệ có `ROLE_SETUP` | Kết nối được chấp nhận |
| SETUP token không hợp lệ | Kết nối bị từ chối |
| Thiếu SETUP credential khi policy yêu cầu | Không thiết lập được phiên |
| Request JWT hợp lệ | Request được xác thực và tiếp tục authorization |
| Request token hết hạn hoặc sai chữ ký | Stream/request tương ứng bị từ chối |
| User A và B dùng chung requester | Mỗi request được xác thực theo token riêng, không lẫn principal |
| User thiếu authority route | Request bị từ chối dù token hợp lệ |
| User có role nhưng không sở hữu tài nguyên | Service từ chối ở bước kiểm tra quyền tài nguyên |
| SETUP service credential hợp lệ, user credential sai | Kết nối vẫn mở theo policy; request sai bị từ chối |
| Token bị thu hồi hoặc logout | Hành vi đóng kết nối/từ chối request đúng chính sách đã chọn |

Ví dụ kiểm thử tích hợp nên tạo một requester dùng chung, gửi hai request với hai JWT khác nhau và xác nhận response/authorization đúng user. Sau đó gửi token không hợp lệ và kiểm tra chỉ request tương ứng bị từ chối, không làm lẫn security context của request khác.

Với test SETUP, thử kết nối bằng token có và không có authority `ROLE_SETUP`. Với test kết hợp, service token chỉ có quyền setup, còn user token có quyền nghiệp vụ. Xác minh user không thể mở connection mới chỉ bằng token người dùng nếu policy yêu cầu `ROLE_SETUP`.

## 14. Checklist triển khai

- [ ] Xác định một connection dành riêng cho một user hay được nhiều user chia sẻ.
- [ ] Chọn authentication ở SETUP, từng request hoặc kết hợp theo mô hình chia sẻ kết nối.
- [ ] Dùng authentication metadata extension được Spring Security hỗ trợ.
- [ ] Cấu hình `@EnableRSocketSecurity`, `PayloadSocketAcceptorInterceptor` và JWT decoder hoặc Simple Authentication phù hợp.
- [ ] Đảm bảo interceptor được gắn vào RSocket server; kiểm tra auto-configuration của Spring Boot.
- [ ] Viết authorization rules cho SETUP, route và request còn lại theo thứ tự cụ thể trước, tổng quát sau.
- [ ] Nếu kết hợp, tách authority của service mở kết nối và user thực hiện request.
- [ ] Không chia sẻ mutable authentication state giữa các request đồng thời.
- [ ] Định nghĩa cách xử lý token hết hạn, logout, revoke và reconnect.
- [ ] Bật TLS/WSS và không log credential.
- [ ] Kiểm thử SETUP rejection, request rejection, nhiều user trên một connection và quyền tài nguyên.

Xác thực ở `SETUP` phù hợp với kết nối có một danh tính ổn định. Xác thực từng request phù hợp với kết nối multiplex dùng chung cho nhiều người. Kết hợp cả hai giúp kiểm soát cả service mở kết nối và user cuối thực hiện thao tác. Hãy lựa chọn theo ranh giới danh tính thực tế, sau đó áp dụng authorization cho từng route và tài nguyên để bảo vệ đầy đủ ứng dụng RSocket.

## Tài liệu tham khảo

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security — `RSocketSecurity`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security — `BearerTokenMetadata`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/rsocket/metadata/BearerTokenMetadata.html)
- [RSocket Protocol — Authentication Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Authentication.md)
