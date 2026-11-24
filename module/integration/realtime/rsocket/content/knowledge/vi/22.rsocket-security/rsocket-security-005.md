# Tích hợp `@EnableRSocketSecurity` và `PayloadSocketAcceptorInterceptor`

Spring Security cung cấp một lớp bảo vệ cho các tương tác RSocket. `@EnableRSocketSecurity` bật hạ tầng bảo mật RSocket; `RSocketSecurity` là DSL để cấu hình xác thực và phân quyền; `PayloadSocketAcceptorInterceptor` áp dụng các quy tắc đó vào luồng nhận kết nối và payload của server.

Điểm tích hợp quan trọng là interceptor phải được gắn vào `SocketAcceptor` của RSocket server. Chỉ khai báo một bean `PayloadSocketAcceptorInterceptor` chưa đủ nếu server không sử dụng interceptor đó. Khi được đăng ký đúng, server có thể xác thực thông tin trong authentication metadata và kiểm tra quyền truy cập theo route trước khi chuyển request đến handler Spring.

## 1. Các thành phần bảo mật RSocket

| Thành phần | Vai trò |
|---|---|
| `@EnableRSocketSecurity` | Bật cấu hình Spring Security dành cho RSocket và cung cấp các thành phần cần thiết để xây dựng security interceptor. |
| `RSocketSecurity` | DSL khai báo cách xác thực và quy tắc authorization cho SETUP, route và payload. |
| `PayloadSocketAcceptorInterceptor` | Intercept quá trình accept socket/payload để thực thi authentication và authorization. |
| `ReactiveAuthenticationManager` | Xác thực thông tin đăng nhập theo mô hình reactive và trả về `Authentication`. |
| `RSocketRequester` | Phía client tạo request và gắn authentication metadata vào SETUP hoặc payload theo cấu hình. |
| `@MessageMapping` | Handler nghiệp vụ được gọi sau khi request vượt qua các bước bảo mật. |

Luồng xử lý ở phía server:

```text
RSocket client
     |
     | SETUP / REQUEST + authentication metadata
     v
RSocket server SocketAcceptor
     |
     v
PayloadSocketAcceptorInterceptor
     |
     +--> Authentication: xác minh credentials/token
     |
     +--> Authorization: kiểm tra setup, route và quyền
     |
     v
Spring RSocketMessageHandler
     |
     v
@MessageMapping handler
```

Authentication xác định caller là ai. Authorization quyết định caller đó được phép thực hiện tương tác nào. Hai bước này liên quan nhưng không thay thế cho nhau.

## 2. Thêm dependency

Ứng dụng cần module Spring Security RSocket tương thích với phiên bản Spring Security đang dùng. Với Gradle và Spring Boot dependency management:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-rsocket")
}
```

Với Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-rsocket</artifactId>
    </dependency>
</dependencies>
```

Nên để Spring Boot BOM quản lý phiên bản để các module Spring Framework và Spring Security tương thích. Không trộn một phiên bản `spring-security-rsocket` khác dòng với các module security còn lại.

## 3. Bật RSocket Security

Đặt `@EnableRSocketSecurity` trên một lớp cấu hình Spring:

```java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {
}
```

Annotation này bật hạ tầng bảo mật cho RSocket. Bản thân annotation chưa xác định route nào được phép truy cập và cũng chưa gắn interceptor vào server. Ứng dụng cần khai báo `PayloadSocketAcceptorInterceptor` từ `RSocketSecurity` và đăng ký interceptor với RSocket server.

## 4. Tạo PayloadSocketAcceptorInterceptor bằng RSocketSecurity

Một cấu hình thường dùng là cho phép SETUP để client thiết lập kết nối, sau đó yêu cầu xác thực cho các route nghiệp vụ:

```java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().permitAll()
                .route("orders.read").hasRole("USER")
                .route("orders.write").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .simpleAuthentication(Customizer.withDefaults());

        return rsocket.build();
    }
}
```

Trong cấu hình này:

- `setup().permitAll()` cho phép frame SETUP hoàn tất quá trình mở kết nối. Quy tắc này chỉ áp dụng cho SETUP, không làm cho mọi request nghiệp vụ trở thành public.
- `route("orders.read").hasRole("USER")` yêu cầu caller có role `ROLE_USER` khi gọi route đọc đơn hàng.
- `route("orders.write").hasRole("ADMIN")` yêu cầu role `ROLE_ADMIN` cho route ghi.
- `anyRequest().authenticated()` yêu cầu xác thực đối với các payload/request còn lại.
- `simpleAuthentication(...)` bật cơ chế giải mã username/password authentication metadata.
- `rsocket.build()` tạo `PayloadSocketAcceptorInterceptor` mang các quy tắc vừa cấu hình.

Các matcher được đánh giá theo thứ tự khai báo. Đặt quy tắc cụ thể trước quy tắc tổng quát để tránh một matcher rộng che mất quy tắc riêng. Với hệ thống cần deny-by-default, có thể dùng `.anyRequest().denyAll()` rồi chỉ mở các route được phép.

## 5. Phân biệt SETUP authorization và request authorization

RSocket có một frame `SETUP` để khởi tạo connection, sau đó mới có các request như request-response, request-stream, fire-and-forget hoặc request-channel. Spring Security cho phép đặt quy tắc riêng cho hai giai đoạn:

| Matcher | Phạm vi | Ví dụ |
|---|---|---|
| `setup()` | Frame thiết lập kết nối | Cho phép client mở connection, hoặc yêu cầu SETUP đã được xác thực. |
| `route("...")` | Request có routing metadata khớp route | Chỉ role USER được gọi `orders.read`. |
| `anyRequest()` | Request không khớp các matcher trước | Yêu cầu authenticated hoặc từ chối mặc định. |

`setup().permitAll()` thường được dùng khi ứng dụng muốn cho phép transport connection được tạo trước, trong khi mọi route nghiệp vụ vẫn yêu cầu xác thực. Nếu policy yêu cầu danh tính phải có ngay khi thiết lập connection, hãy cân nhắc `.setup().authenticated()` và bảo đảm client gửi authentication metadata trong SETUP.

Không nhầm `setup().permitAll()` với việc tắt toàn bộ RSocket Security. Các request tiếp theo vẫn đi qua authorization matcher.

## 6. Cung cấp ReactiveAuthenticationManager

Authentication metadata chỉ là dữ liệu credential được gửi qua giao thức. Server vẫn cần một cơ chế xác minh credential. Với username/password, có thể dùng `ReactiveUserDetailsService` và `UserDetailsRepositoryReactiveAuthenticationManager`:

```java
@Configuration
public class AuthenticationConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("alice")
            .password(encoder.encode("change-this-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("ops")
            .password(encoder.encode("change-this-admin-password"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(user, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }
}
```

Đây là kho người dùng trong bộ nhớ để minh họa. Trong production, thay bằng user store phù hợp, lưu password dưới dạng hash bằng password encoder, quản lý rotation và không hard-code mật khẩu trong source code. `ReactiveAuthenticationManager` có thể được thay bằng cơ chế xác thực token hoặc identity provider của hệ thống.

## 7. Gửi username/password authentication metadata từ client

Với simple authentication, client gửi `UsernamePasswordMetadata` trong SETUP metadata. MIME type chuẩn của RSocket authentication là `message/x.rsocket.authentication.v0`.

```java
MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

RSocketRequester requester = RSocketRequester.builder()
    .setupMetadata(
        new UsernamePasswordMetadata("alice", "change-this-password"),
        authenticationMimeType)
    .tcp("localhost", 7000);
```

`setupMetadata(...)` gắn credential vào frame SETUP. Server giải mã metadata qua cơ chế simple authentication, sau đó security context có thể được dùng khi kiểm tra request theo policy đã cấu hình.

MIME type và cấu trúc metadata phải tương thích với authentication decoder trên server. Không tự đóng gói username/password thành JSON tùy ý rồi kỳ vọng simple authentication tự hiểu; hãy dùng đúng metadata type và codec mà Spring Security hỗ trợ.

Thông tin đăng nhập trong ví dụ chỉ dành cho môi trường local/test. Trên mạng không tin cậy, phải bảo vệ transport bằng TLS và quản lý credential như secret. Không log username/password metadata hoặc token.

## 8. Đăng ký interceptor với RSocket server

`PayloadSocketAcceptorInterceptor` cần được cài vào socket acceptor pipeline. Với Spring Boot RSocket server, có thể dùng `RSocketServerCustomizer`:

```java
@Configuration
public class RSocketServerSecurityIntegration {

    @Bean
    RSocketServerCustomizer securitySocketAcceptor(
            PayloadSocketAcceptorInterceptor interceptor) {

        return server -> server.interceptors(registry ->
            registry.forSocketAcceptor(interceptor));
    }
}
```

`RSocketServerCustomizer` cho phép tùy chỉnh server do Spring Boot tạo. `forSocketAcceptor(interceptor)` đăng ký interceptor ở ranh giới acceptor, nơi các kết nối và request được tiếp nhận. Khi server bind transport, các connection đi qua interceptor này.

Nếu ứng dụng tự tạo RSocket server thay vì dùng Boot auto-configuration, hãy gắn interceptor vào builder trước khi bind:

```java
RSocketServer server = RSocketServer.create(socketAcceptor)
    .interceptors(registry -> registry.forSocketAcceptor(interceptor));

server.bind(TcpServerTransport.create("0.0.0.0", 7000));
```

Tên package và overload builder có thể khác theo phiên bản RSocket Java/Spring Boot. Dùng `RSocketServerCustomizer` khi tích hợp với Boot-managed server; với server tự quản lý, kiểm tra API của dependency đang dùng và bảo đảm interceptor nằm trong SocketAcceptor chain.

Điểm cần xác minh khi cấu hình: bean `PayloadSocketAcceptorInterceptor` đã được tạo và chính server đang chạy đã nhận interceptor. Một bean tồn tại trong ApplicationContext nhưng không được đăng ký vào server sẽ không bảo vệ các request.

## 9. Handler được bảo vệ bằng route authorization

Sau khi interceptor được cài, các handler Spring vẫn khai báo bình thường:

```java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.read")
    public Mono<OrderSummary> read(@Payload OrderQuery query) {
        return orderService.read(query.orderId());
    }

    @MessageMapping("orders.write")
    public Mono<OrderReceipt> write(@Payload CreateOrder command) {
        return orderService.create(command);
    }
}
```

Security interceptor kiểm tra route và authentication trước khi request được xử lý bởi handler. Client không thể tự cấp role bằng cách thêm một header hoặc route segment; authorities phải đến từ `Authentication` do server xác minh.

Nếu handler cần biết caller để áp dụng quy tắc ở cấp tài nguyên, có thể nhận `Principal` hoặc `Authentication` qua các argument resolver Spring phù hợp:

```java
@MessageMapping("orders.read")
public Mono<OrderSummary> read(
        @Payload OrderQuery query,
        Principal principal) {

    return orderService.readForUser(query.orderId(), principal.getName());
}
```

Authorization theo route trả lời câu hỏi caller có được gọi loại thao tác đó không. Kiểm tra quyền trên từng đơn hàng/tenant vẫn cần thực hiện trong service hoặc một authorization manager ở cấp tài nguyên.

## 10. Cấp quyền theo route và mặc định từ chối

Một policy rõ ràng nên khai báo các route cụ thể trước và xác định rõ hành vi với route chưa biết:

```java
rsocket.authorizePayload(authorize -> authorize
    .setup().permitAll()
    .route("orders.read").hasAnyRole("USER", "ADMIN")
    .route("orders.write").hasRole("ADMIN")
    .route("telemetry.subscribe").hasAuthority("SCOPE_telemetry.read")
    .anyRequest().denyAll()
);
```

Trong ví dụ:

- USER và ADMIN có thể đọc đơn hàng.
- Chỉ ADMIN được tạo hoặc cập nhật đơn hàng.
- Caller có authority `SCOPE_telemetry.read` mới được subscribe telemetry.
- Route không được khai báo bị từ chối.

`hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`; `hasAuthority(...)` so khớp chính xác tên authority. Cần cấp authorities đúng định dạng từ authentication provider. Không nhầm role với tên route hoặc metadata tự khai báo bởi client.

## 11. Authentication metadata ở SETUP và ở từng request

RSocket có thể mang metadata trong frame SETUP và trong payload của từng request. Hai vị trí này có vòng đời khác nhau:

| Vị trí | Phạm vi | Ví dụ sử dụng |
|---|---|---|
| SETUP metadata | Khi thiết lập một connection | Xác thực danh tính kết nối bằng username/password hoặc token. |
| Request metadata | Theo từng tương tác | Gửi credential/token hoặc ngữ cảnh cần kiểm tra theo request, nếu security configuration hỗ trợ. |

Khi dùng `setupMetadata(...)`, credential gắn với quá trình mở connection. Nếu ứng dụng cần xác thực lại theo từng request hoặc hỗ trợ token thay đổi trong khi connection còn mở, cần thiết kế rõ vị trí credential và cấu hình decoder/authorization tương ứng. Không giả định token gửi trong SETUP tự động được refresh khi token hết hạn.

Với JWT, Spring Security có hỗ trợ cấu hình JWT authentication cho RSocket thông qua decoder phù hợp. Cần cấu hình `ReactiveJwtDecoder`, kiểm tra issuer/audience/expiry và dùng đúng bearer authentication metadata format. Không thay JWT decoder bằng simple username/password decoder hoặc tự parse token trong handler.

## 12. Security context và reactive execution

Spring Security reactive lưu `SecurityContext` trong Reactor Context thay vì dựa vào `ThreadLocal` như cách xử lý đồng bộ truyền thống. Vì vậy, không nên giả định một request RSocket luôn chạy trên cùng một thread.

Trong pipeline reactive, hãy giữ nguyên context bằng các operator Reactor thông thường và tránh tự chuyển sang callback/thread tùy ý mà không truyền context cần thiết. Spring Security tích hợp với reactive chain để các bước authorization và truy cập principal hoạt động theo subscription.

Nếu tự tạo task ngoài pipeline, chẳng hạn gọi `subscribe()` thủ công hoặc gửi công việc sang executor riêng, cần xem xét cách truyền security context và không sao chép toàn bộ `Authentication` một cách thiếu kiểm soát. Ưu tiên compose `Mono`/`Flux` và trả publisher về framework.

## 13. Kiểm thử authentication và authorization

Kiểm thử cần xác minh cả trường hợp được phép lẫn bị từ chối:

1. Client không có credential gọi route yêu cầu authenticated và bị từ chối.
2. Credential sai không tạo được authenticated principal.
3. User có role USER gọi `orders.read` thành công.
4. User có role USER gọi `orders.write` bị từ chối.
5. Admin gọi `orders.write` thành công.
6. Route không khai báo bị từ chối khi policy dùng `anyRequest().denyAll()`.
7. SETUP được phép nhưng request nghiệp vụ vẫn phải qua authorization matcher.
8. Metadata thiếu, sai MIME type hoặc malformed được xử lý như lỗi authentication, không rơi về anonymous access ngoài ý muốn.
9. Kiểm tra interceptor thực sự được gắn vào server đang chạy.

Ví dụ kiểm thử request-response từ client đã xác thực:

```java
StepVerifier.create(
        requester.route("orders.read")
            .data(new OrderQuery(orderId))
            .retrieveMono(OrderSummary.class))
    .expectNextMatches(summary -> summary.orderId().equals(orderId))
    .verifyComplete();
```

Để kiểm thử user không có quyền, tạo requester với credentials của USER rồi gọi route `orders.write`; xác minh publisher kết thúc bằng lỗi authorization phù hợp. Không chỉ kiểm tra status ở handler vì request bị từ chối có thể chưa bao giờ đến handler.

## 14. Quan sát và xử lý lỗi bảo mật

Lỗi xác thực và phân quyền nên được quan sát ở server bằng log/metric có kiểm soát. Nên ghi nhận route, correlation ID, loại lỗi và danh tính đã được xác minh nếu policy cho phép; không ghi password, bearer token hoặc raw authentication metadata.

Các nhóm lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Tất cả request đều bị từ chối | Interceptor không được gắn đúng, authentication manager không hoạt động hoặc matcher quá rộng. | Kiểm tra server customizer, route thực tế, auth manager và security logs. |
| SETUP thành công nhưng route bị từ chối | Setup được permit nhưng request chưa có principal/credential hợp lệ hoặc thiếu authority. | Kiểm tra vị trí authentication metadata và authorities. |
| Client gửi credential nhưng server không xác thực | MIME type hoặc metadata encoding không khớp. | Kiểm tra `MESSAGE_RSOCKET_AUTHENTICATION` và metadata decoder. |
| User xác thực được nhưng không gọi được route | Role/authority không khớp policy hoặc route matcher. | Kiểm tra `ROLE_` prefix, authority và route string. |
| Handler vẫn chạy dù nghĩ đã bật security | Interceptor bean chưa được gắn vào SocketAcceptor thực tế. | Xác minh `RSocketServerCustomizer` hoặc builder interceptor chain. |
| Request bị lỗi sau khi đổi token | Connection còn giữ authentication context cũ hoặc token hết hạn. | Thiết kế refresh/reconnect hoặc xác thực theo request rõ ràng. |

Không nên trả chi tiết nội bộ của authentication provider cho client. Client chỉ cần biết request không được xác thực hoặc không được phép; log server có thể giữ chi tiết đã được lọc để điều tra.

## 15. Những lỗi tích hợp thường gặp

| Lỗi | Vì sao sai? | Cách xử lý |
|---|---|---|
| Chỉ thêm `@EnableRSocketSecurity` | Annotation bật hạ tầng nhưng không tự mô tả policy và chưa chắc đã cài interceptor. | Tạo `PayloadSocketAcceptorInterceptor` từ `RSocketSecurity` và gắn vào server. |
| Tạo interceptor bean nhưng không đăng ký vào server | Request có thể không đi qua security chain. | Dùng `RSocketServerCustomizer` hoặc cấu hình interceptor trên server builder. |
| Cho phép SETUP rồi nghĩ mọi request đều public | SETUP và request có matcher riêng. | Khai báo route authorization và fallback rõ ràng. |
| Dùng `anyRequest().authenticated()` khi muốn deny-by-default | Mọi route chưa khai báo vẫn mở cho user đã xác thực. | Dùng `anyRequest().denyAll()` rồi mở từng route cần thiết. |
| Gửi username/password với MIME type tùy ý | Decoder simple authentication không nhận diện được metadata. | Dùng authentication MIME type và metadata class tương ứng. |
| Dùng metadata client gửi làm role/authority | Client có thể giả mạo giá trị. | Authorities phải được tạo bởi authentication provider đáng tin cậy. |
| Chỉ kiểm tra quyền theo route | User có quyền route nhưng có thể truy cập tài nguyên của tenant khác. | Kiểm tra quyền tài nguyên ở service/domain layer. |
| Log raw credentials hoặc token | Rò rỉ bí mật qua log/trace. | Redact metadata nhạy cảm và dùng TLS. |
| Gọi `subscribe()` thủ công trong handler | Security context và cancellation có thể tách khỏi request reactive. | Compose và trả `Mono`/`Flux` cho framework. |

## 16. Checklist triển khai

Trước khi đưa RSocket Security vào môi trường thật, kiểm tra:

- Dependency `spring-security-rsocket` cùng dòng phiên bản Spring Security.
- `@EnableRSocketSecurity` được đặt trong cấu hình Spring.
- `ReactiveAuthenticationManager` và credential/token verifier đã được cấu hình.
- `PayloadSocketAcceptorInterceptor` được tạo từ `RSocketSecurity`.
- Interceptor được đăng ký vào SocketAcceptor pipeline của server đang chạy.
- SETUP matcher và route matcher phản ánh đúng policy.
- Có fallback rõ ràng, ưu tiên deny-by-default với route không khai báo.
- Client gửi authentication metadata đúng MIME type và đúng vị trí.
- TLS được bật khi credential/token đi qua mạng không tin cậy.
- Có kiểm thử authenticated, unauthenticated, forbidden và unknown route.
- Log/metric không chứa raw password, bearer token hoặc authentication payload.
- Authorization ở tầng nghiệp vụ kiểm tra quyền truy cập tài nguyên cụ thể.

## Tài liệu tham khảo

- [Spring Security Reference — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html) — `@EnableRSocketSecurity`, authorization và authentication cho RSocket.
- [Spring Security Javadoc — RSocketSecurity](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html) — DSL cấu hình bảo mật RSocket.
- [Spring Security Javadoc — PayloadSocketAcceptorInterceptor](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html) — interceptor bảo vệ SocketAcceptor.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html) — cấu hình server RSocket trong Spring Boot.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — SETUP, authentication metadata và các kiểu tương tác.

## Kết luận

`@EnableRSocketSecurity` bật hạ tầng bảo mật RSocket; `RSocketSecurity` mô tả authentication và authorization; `PayloadSocketAcceptorInterceptor` thực thi các quy tắc trên đường tiếp nhận request. Ứng dụng cần tạo interceptor bằng `rsocket.build()` rồi gắn nó vào SocketAcceptor pipeline của server, ví dụ qua `RSocketServerCustomizer` trong Spring Boot. Hãy cấu hình authentication metadata và `ReactiveAuthenticationManager`, tách quyền SETUP khỏi quyền route, đặt fallback an toàn và kiểm thử cả authenticated lẫn forbidden request. Khi tích hợp đúng, các handler Spring chỉ nhận những tương tác đã vượt qua lớp xác thực và phân quyền.
