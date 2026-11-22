# Phân quyền theo route và kiểm soát metadata của RSocket

> **Ngữ cảnh:** RSocket và luồng dài, trong hệ sinh thái **Spring Security reactive / Spring WebFlux**. Bài này tập trung vào phân quyền **RSocket route**, an ninh của **SETUP/request metadata**, khác biệt giữa **request khởi đầu** và **PAYLOAD tiếp nối** của luồng dài, cách Spring Security 6.5 sử dụng `RSocketSecurity`, `PayloadSocketAcceptorInterceptor` và `ReactiveAuthenticationManager`. Ví dụ dùng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x**, RSocket TCP ở loopback, Simple Authentication; mở rộng JWT/metadata riêng được trình bày riêng. Các tài khoản và mật khẩu ví dụ **chỉ để thực hành**, không dùng thật trên Internet.

## 1. Mục tiêu bài học

Hoàn thành bài này, người học cần có khả năng:

1. Giải thích RSocket **không phải HTTP API**: route nằm trong metadata, không phải đường dẫn URL.
2. Phân biệt `SETUP`, `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_FNF`, `PAYLOAD` và `METADATA_PUSH` khi bàn về quyền.
3. Biết metadata nào chứa **routing**, metadata nào chứa **authentication**, metadata nào là **business context** như tenant/tracing; không trộn chúng.
4. Dùng `@EnableRSocketSecurity` và bean `PayloadSocketAcceptorInterceptor` với `RSocketSecurity.authorizePayload(...)`.
5. Hiểu matcher `.setup()`, `.route("...")`, `.matcher(...)`, `.anyRequest()`, `.anyExchange()`; quy tắc xét theo thứ tự và first-match-wins.
6. Chọn chiến lược **authentication tại connection setup** hoặc **mỗi request**, nhất là khi nhiều users dùng chung một RSocket connection.
7. Cấu hình route chỉ dành cho `ROLE_READER`/`ROLE_ADMIN`, không dùng một `authenticated()` chung để mở mọi chức năng.
8. Giữ `anyExchange().permitAll()` có chủ đích cho payload không mang route của một channel đã được cấp quyền, **không** coi đó là quyền bỏ qua kiểm dữ liệu.
9. Đăng ký custom metadata MIME bằng `RSocketStrategiesCustomizer` và `MetadataExtractorRegistry`, đọc bằng `@Header`; coi mọi custom metadata do client gửi là **untrusted**.
10. Thiết kế bảo vệ **long-lived streams** khi quyền thay đổi, token hết hạn, revoke, reconnect, backpressure, rate/byte quotas và cancellation.
11. Viết integration tests với `RSocketRequester`/`StepVerifier` kiểm setup credentials đúng/sai, route reader/admin, stream và channel.
12. Hiểu các lỗi phổ biến: gửi HTTP Basic header thay vì RSocket authentication metadata, thiếu auth encoder, route rule quá rộng, lấy role từ tenant header và mặc định tin JWT đã decode mà chưa verify.

**Thông điệp chính:** Trong RSocket, **route là metadata do client có thể chọn**, còn authentication metadata chỉ là credential **chưa được tin cho tới khi xác thực**. Phải quyết định quyền theo **principal đã xác thực + route + tài nguyên thực**, đồng thời kiểm lifecycle của các stream tồn tại lâu.

## 2. RSocket khác HTTP như thế nào?

RSocket là giao thức binary hỗ trợ nhiều loại tương tác trên một kết nối TCP/WebSocket:

| RSocket interaction | Dạng API reactive thường gặp | Ý nghĩa bảo mật |
| --- | --- | --- |
| Request-Response | Một request, một response (`Mono<T>`) | Cần authz tại request đầu |
| Fire-and-Forget | Một request, không chờ response nghiệp vụ | Vẫn cần authz, `Mono<Void>` của client không chứng minh server đã xử lý |
| Request-Stream | Một request, nhiều response (`Flux<T>`) | Kiểm quyền trước khi mở stream, cân nhắc revoke giữa stream |
| Request-Channel | Hai chiều truyền nhiều messages (`Flux<T>` vào/ra) | Kiểm request khởi đầu **và** validate từng item, quota/backpressure |
| Metadata-Push | Gửi metadata connection-level không thuộc request riêng | Không coi metadata push như request đã được route-authorized |
| SETUP | Thương lượng MIME type, keepalive, credentials/metadata đầu kết nối | Có thể xác thực client ngay khi kết nối |
| PAYLOAD nối tiếp | Frames tiếp theo sau request đầu (đặc biệt channel) | Không nhất thiết mang lại route metadata mới |

Trong REST, một URL ví dụ `GET /reports/me` thường xác định endpoint. Với RSocket, client có thể gọi:

```java
requester.route("reports.me")
    .retrieveMono(Report.class);
```

Chuỗi `reports.me` được serialize thành **routing metadata**, không phải URL path. Spring Messaging `@MessageMapping("reports.me")` dispatch đến handler. Điều đó **không có nghĩa** route string là bằng chứng user đã có quyền.

### 2.1 Một frame gồm gì?

Ở mức khái niệm:

```text
RSocket SETUP:
  data MIME type:      application/json hoặc application/cbor
  metadata MIME type:  message/x.rsocket.composite-metadata.v0
  setup auth metadata: UsernamePasswordMetadata / BearerTokenMetadata
  keepalive/lifetime settings
          |
          v
REQUEST_STREAM (route="events.stream"):
  metadata:
    entry 1: message/x.rsocket.routing.v0       -> "events.stream"
    entry 2: message/x.rsocket.authentication.v0 -> token/credentials nếu auth mỗi request
    entry 3: message/x.example.tenant.v1         -> "north" nếu ứng dụng có đăng ký
  data: payload mở stream
          |
          v
PAYLOAD/REQUEST_N/CANCEL:
  frames phục vụ luồng đang tồn tại
  nhiều frame **không mang lại route metadata**
```

Đây là sơ đồ logic, **không phải dump byte-level của một gói thực**. Tùy interaction, một frame có thể có hoặc không có data/metadata; routing metadata thường ở **frame khởi đầu của một request**.

### 2.2 Composite metadata là gì?

RSocket có thể gửi nhiều metadata entries với MIME type khác nhau trong một payload. MIME composite phổ biến:

```text
message/x.rsocket.composite-metadata.v0
```

Các entry thường gặp:

```text
message/x.rsocket.routing.v0
message/x.rsocket.authentication.v0
message/x.example.tenant.v1       (custom MIME của ứng dụng, chỉ ví dụ)
```

MIME type chỉ nói **cách giải mã** một metadata entry; nó **không xác minh sự thật** của giá trị. Ví dụ `tenant=north` vẫn là chuỗi do client kiểm soát, không phải tenant đã được ủy quyền.

## 3. RSocket Security chạy ở lớp nào?

Spring Security RSocket không dựa vào `SecurityWebFilterChain` của HTTP. Nó dùng cơ sở:

- `@EnableRSocketSecurity` bật tích hợp security RSocket.
- `RSocketSecurity` khai báo authentication và authorization DSL.
- `PayloadSocketAcceptorInterceptor` chứa các payload interceptors.
- `SecuritySocketAcceptorInterceptor` gắn payload security vào socket acceptor.
- `AuthenticationPayloadInterceptor` xác thực metadata bằng reactive authentication machinery.
- `AuthorizationPayloadInterceptor` xét `PayloadExchange` theo các matchers.
- `MapReactiveUserDetailsService` + password encoder cho Simple Authentication trong bài demo.
- `@MessageMapping` của Spring Messaging nhận request sau lớp routing/security.

Với Spring Boot 3.x khi có đúng dependencies và auto-configuration, **Boot đăng ký RSocket server và security socket acceptor interceptor**. Nếu bạn khởi tạo RSocket server **thủ công** (không qua Boot), phải tự gắn `SecuritySocketAcceptorInterceptor`; chỉ khai bean interceptor nhưng không gắn vào server có thể khiến request đi vòng ngoài security.

### 3.1 Cấu hình đầu vào

```java
@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfig {
    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {
        return rsocket
            .authorizePayload(authz -> authz
                .setup().authenticated()
                .route("events.stream").hasRole("READER")
                .route("admin.audit").hasRole("ADMIN")
                .anyRequest().denyAll()
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **đoạn minh họa**, các imports/file đầy đủ ở mục 8. Ý nghĩa là một connection phải xác thực ngay tại SETUP; sau đó routes `events.stream` và `admin.audit` có rule khác nhau; request khác bị deny; PAYLOAD không phải request mới được phép đi qua nếu không khớp rule trước đó.

### 3.2 Vì sao không dùng @EnableWebFluxSecurity để bảo vệ riêng RSocket TCP?

HTTP và RSocket có các security pipelines riêng. `@EnableWebFluxSecurity` và `ServerHttpSecurity` áp vào HTTP WebFlux; RSocket dùng `@EnableRSocketSecurity`, `RSocketSecurity` và payload interceptors. Khi RSocket dùng **WebSocket transport** trên HTTP server, lớp HTTP handshake vẫn cần kiểm origin/TLS/gateway, nhưng **không thay thế** route authorization bên trong RSocket frames.

Không giả định “WebSocket đã qua HTTP authentication nên mọi RSocket route đều tự được cấp quyền”. Sau upgrade, các request RSocket riêng vẫn cần policy và identity propagation được thiết kế tường minh.

## 4. Các loại matcher trong authorizePayload

| Rule | Khớp cái gì? | Dùng cho |
| --- | --- | --- |
| `.setup()` | Payload exchange ở SETUP | Điều kiện mở kết nối RSocket |
| `.route("events.stream")` | Routing metadata khớp pattern | Role/scope theo tên route |
| `.route("admin.*")` | Pattern theo route matcher | Nhóm routes admin, tránh wildcard quá rộng |
| `.matcher(customMatcher)` | Một `PayloadExchangeMatcher` tùy biến | Điều kiện nâng cao theo exchange type/metadata |
| `.anyRequest()` | Request interaction khởi đầu (không phải từng PAYLOAD continuation) | Fallback deny hoặc authenticated cho requests chưa match |
| `.anyExchange()` | Exchange còn lại, bao gồm loại không phải request | Quyết định cuối cho payloads/no-route/metadata push |

**Rules được xét theo thứ tự**. Spring Security dùng **rule đầu tiên khớp**, không chạy tất cả rules để lấy rule “mạnh nhất”.

### 4.1 Thứ tự đúng

```java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("CONNECT")
    .route("status.ping").authenticated()
    .route("events.stream").hasRole("READER")
    .route("admin.audit").hasRole("ADMIN")
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

Sắp xếp cụ thể trước fallback:
- `.setup()` là rule cho SETUP;
- `.route("...")` cho các request routes đã định;
- `.anyRequest().denyAll()` cho request lạ/không hợp lệ không được liệt kê;
- `.anyExchange().permitAll()` cho những exchanges còn lại **không phải initial request** (phải đánh giá kỹ khi có metadata push/channel).

### 4.2 Sai: anyRequest trước route cụ thể

```java
// SAI: mọi request vào rule này trước.
.authorizePayload(authz -> authz
    .anyRequest().authenticated()
    .route("admin.audit").hasRole("ADMIN")
    .anyExchange().permitAll()
)
```

Vì `anyRequest()` khớp request tới admin trước, rule admin sẽ không còn hiệu quả: một user bất kỳ đã authenticated có thể vượt qua layer route authorization. Đây là lỗi **privilege escalation**, không chỉ lỗi style.

### 4.3 Sai: anyExchange().permitAll() ở đầu

```java
// SAI nghiêm trọng: anyExchange khớp tất cả.
.authorizePayload(authz -> authz
    .anyExchange().permitAll()
    .route("admin.audit").hasRole("ADMIN")
)
```

Rule phía sau không được xét. Không đặt fallback rộng trước routes có security restrictions.

### 4.4 Vì sao không mặc định anyExchange().denyAll()?

Trong `REQUEST_CHANNEL` hoặc một số interactions, những `PAYLOAD` nối tiếp có thể **không có routing metadata mới**. Nếu bạn `denyAll()` mọi exchange không phải request, có thể chặn các payload vốn thuộc stream đã được cho phép.

Theo Spring Security RSocket docs, `anyRequest()` match request mở đầu, còn `anyExchange()` match cả những payload không có metadata/routing. Cấu hình mẫu dùng `anyRequest().denyAll()` và `anyExchange().permitAll()` để:
1. Chặn mọi **request khởi đầu** chưa có route rule;
2. Cho phép **frames tiếp nối** để stream/channel đã được chấp nhận có thể hoạt động.

**Không hiểu nhầm:** `anyExchange().permitAll()` **không phải giấy phép** để metadata-push hoặc payload tiếp theo thực hiện thao tác nhạy cảm không được kiểm. Với `METADATA_PUSH`, `@ConnectMapping`, custom interceptors hoặc channel mutation, phải có checks riêng và hoặc `matcher(...)` cho exchange type cần bảo vệ. Bài demo không xử lý privileged metadata-push.

## 5. Authentication ở SETUP hay trên từng request?

### 5.1 SETUP authentication

Client gửi authentication metadata khi mở connection. Tình huống:

- RSocket connection dành riêng cho **một identity**;
- Mobile/desktop user duy trì connection trong phiên;
- Service-to-service connection có service principal ổn định.

```text
CONNECT TCP/TLS -> SETUP(credentials user=reader)
                     |
                     +-- auth fail -> connection bị từ chối
                     |
                     +-- auth success -> SecurityContext cho connection
                                              |
                                              +-- events.stream -> ROLE_READER?
                                              +-- admin.audit   -> ROLE_ADMIN?
```

Ưu điểm: giảm chi phí verify mỗi message/route, kết nối dùng identity ổn định. Nhược điểm: nếu token/quyền bị revoke giữa **stream dài**, hệ thống không mặc nhiên kiểm lại sau mỗi event.

### 5.2 Request-time authentication

Một backend gateway có thể chia sẻ một RSocket connection cho nhiều users. Khi đó **SETUP** chỉ xác nhận danh tính app/gateway (`ROLE_CONNECT`), còn **mỗi request** mang credential của user cụ thể:

```text
SETUP: token của trusted gateway, role CONNECT
  |
  +-- REQUEST_STREAM route=users.alice.events
  |        authentication metadata: access token of alice
  |
  +-- REQUEST_RESPONSE route=users.bob.profile
           authentication metadata: access token of bob
```

Nếu dùng request-time auth, không được vì connection đã được `ROLE_CONNECT` mà mặc định cấp các quyền dữ liệu của user. Service identity để mở socket **khác** user identity dùng cho route/tenant-specific data.

### 5.3 Có thể kết hợp cả hai

Spring Security docs mô tả dùng auth cả setup lẫn mỗi request. Ví dụ:
- Setup credential có authority `ROLE_CONNECT`, không có `ROLE_READ_PERSONAL_DATA`.
- Request credential của user có scopes/roles dùng ở route.
- Route sensitive yêu cầu user-specific authority, không thể chỉ dựa vào setup role.
- Scope và tenant được server kiểm qua trusted principal.

**Quan trọng:** Không dùng token của user A làm “default identity” cho toàn bộ connection được nhiều users B/C dùng chung. Nếu backend tái sử dụng RSocketRequester với `setupMetadata(userAToken)`, có thể vô tình gọi route thay mặt A trong requests của B.

## 6. Metadata của RSocket cần kiểm soát những gì?

### 6.1 Routing metadata

MIME:

```text
message/x.rsocket.routing.v0
```

Sender dùng `requester.route("...")`; responder dùng `@MessageMapping("...")`. Client có quyền **tự chọn route string**, vì thế:
- Không tự động cấp quyền vì route bắt đầu bằng `admin.` hoặc có tên “trusted”;
- Đăng ký route-specific policies ở `authorizePayload`;
- Chặn mọi request route lạ với `anyRequest().denyAll()`;
- Với route pattern có path variable, dữ liệu biến là **input chưa tin cậy**;
- Nếu route như `tenant.events.{tenantId}`, phải kiểm tenantId với principal của token/connection, không chỉ kiểm `ROLE_READER`.

### 6.2 Authentication metadata

MIME phổ biến:

```text
message/x.rsocket.authentication.v0
```

Spring Security RSocket có các kiểu:
- `UsernamePasswordMetadata` cho **Simple Authentication Metadata Extension**;
- `BearerTokenMetadata` cho JWT access token;
- `SimpleAuthenticationEncoder` và `BearerTokenAuthenticationEncoder` ở bên gửi, tương ứng converters ở bên nhận.

**Không phải HTTP headers.** `Authorization: Basic`/`Authorization: Bearer` thuộc HTTP, còn RSocket Simple/Bearer credentials là **metadata entry** riêng. Nếu client RSocket dùng `requester.metadata(...)` với MIME sai hoặc không đăng ký encoder, server có thể không đọc được authentication dù credential đúng.

### 6.3 Composite metadata

Composite metadata cho phép route + auth + tenant/tracing entries cùng xuất hiện. Thứ tự các entries không được dùng để quyết định authority; loại MIME/codec và server policy quyết định ý nghĩa.

Ví dụ:

```text
Request:
  route MIME: "tenant.events.north"
  authentication MIME: signed token for alice
  tenant MIME: "south"
```

Server **không được** cho rằng route tenant north hoặc tenant header south là đáng tin. Một request có metadata mâu thuẫn cần bị từ chối/ghi audit, nhưng không lộ token. Định danh tenant tin cậy đến từ verified authentication + server-side tenant membership/ACL.

### 6.4 Custom metadata cần đăng ký codec

Spring Messaging cung cấp `RSocketStrategies`, `MetadataExtractorRegistry` và `@Header`. Khi cần thêm field như tenant/trace, khai MIME riêng, chọn codec rõ, cấu hình extractor bên server, encoder ở client.

`@Header("tenant-id")` **không tự xác thực** tenant. Nó chỉ đọc metadata **đã decode**. Authorization theo role/scope phải ở RSocket Security; authorization theo resource/tenant phải ở business layer hoặc custom `ReactiveAuthorizationManager` tin cậy.

### 6.5 Kích thước và số lượng metadata

RSocket binary framing có metadata length/fragmentation; phần cứng, Netty codecs và server policies quyết định giới hạn thực tế. Không cho client gửi metadata tùy ý dài vô hạn:
- Giới hạn frame size, payload size, độ sâu/kiểu dữ liệu khi decode;
- Allowlist MIME types, routes và metadata keys;
- Không accept unknown MIME thành vai trò mặc định;
- Giới hạn tenant IDs/trace IDs (độ dài, ký tự) để tránh log injection;
- Không log raw authentication metadata;
- Đặt connection/request/channel quotas, timeout và backpressure limits.

## 7. Thiết kế demo trước khi viết code

Bài demo dùng **một RSocket TCP server**, bind loopback `127.0.0.1:7000` để không vô tình lộ password demo qua mạng.

**Identity và quyền:**

| Username | Password demo | Granted authorities |
| --- | --- | --- |
| `reader` | `reader-secret` | `ROLE_CONNECT`, `ROLE_READER` |
| `admin` | `admin-secret` | `ROLE_CONNECT`, `ROLE_READER`, `ROLE_ADMIN` |
| `guest` | `guest-secret` | `ROLE_CONNECT` |

**Route policies:**

| Route | Interaction | Rule | Ý nghĩa |
| --- | --- | --- | --- |
| `status.ping` | Request-Response | authenticated | Connection đã setup đúng, được xem trạng thái |
| `events.stream` | Request-Stream | hasRole("READER") | Xem 3 events mẫu |
| `events.channel` | Request-Channel | hasRole("READER") | Gửi 2 messages và nhận acknowledgments |
| `tenant.read.{tenant}` | Request-Response | hasRole("READER") + server ACL | Reader chỉ được tenant north; admin được cả |
| `admin.audit` | Request-Response | hasRole("ADMIN") | Admin-only route |
| Route không liệt kê | Bất kỳ request khởi đầu | denyAll | Không mặc định mở chức năng mới |
| SETUP | Connection setup | hasRole("CONNECT") | Kết nối cần credentials |
| Payload tiếp nối | Channel/stream payload | anyExchange permitAll | Không thay thế item validation |

Đây là **demo giới hạn**. Production phải dùng dữ liệu quyền từ trusted IAM/policy DB, mã hóa đường truyền và identities phù hợp — không dùng 3 tài khoản demo.

## 8. Project Spring Boot 3.5 / Java 17+ đầy đủ

### 8.1 Dependencies

Tạo project Spring Initializr với Java 17+, Spring Boot 3.5.x, Gradle Groovy. Với project đã có Spring Boot plugin và dependency management, phần `dependencies` cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**RSocket TCP độc lập không bắt buộc có `spring-boot-starter-webflux`**. RSocket bản thân đã reactive, dựa trên Reactor và Spring Messaging. Nếu cùng app có WebFlux HTTP, có thể thêm `spring-boot-starter-webflux`, nhưng HTTP security chain là chuyện riêng. Đừng thay `spring-security-rsocket` bằng chỉ `spring-security-web` rồi giả định RSocket route policy được bật.

### 8.2 Cấu trúc files

```text
src/main/java/com/example/securestream/
  SecureStreamApplication.java
  RSocketRouteSecurityConfig.java
  EventRSocketController.java
src/main/resources/
  application.yml
src/test/java/com/example/securestream/
  RSocketRouteSecurityTest.java
```

Mỗi class public nằm trong file Java đúng tên. `SecureStreamApplication` là main class; `RSocketRouteSecurityTest` là test tích hợp khởi động server trên **port ngẫu nhiên**. Không cần WebFlux HTTP server cho mẫu này.

### 8.3 application.yml

`src/main/resources/application.yml`:

```yaml
spring:
  rsocket:
    server:
      address: 127.0.0.1
      transport: tcp
      port: 7000
```

RSocket TCP server bind chỉ trên localhost; `tcp` không tự mang TLS. **Chỉ để học**. Với production expose network, phải cấu hình RSocket TLS/SSL hoặc TLS-terminating infrastructure đáng tin cậy, không cho Simple Authentication credential đi qua plaintext TCP công khai.

### 8.4 SecureStreamApplication.java

`src/main/java/com/example/securestream/SecureStreamApplication.java`:

```java
package com.example.securestream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureStreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureStreamApplication.class, args);
    }
}
```

### 8.5 RSocketRouteSecurityConfig.java

`src/main/java/com/example/securestream/RSocketRouteSecurityConfig.java`:

```java
package com.example.securestream;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration(proxyBeanMethods = false)
@EnableRSocketSecurity
public class RSocketRouteSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-secret"))
            .roles("CONNECT", "READER")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-secret"))
            .roles("CONNECT", "READER", "ADMIN")
            .build();

        var guest = User.withUsername("guest")
            .password(encoder.encode("guest-secret"))
            .roles("CONNECT")
            .build();

        return new MapReactiveUserDetailsService(
            reader, admin, guest
        );
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        return rsocket
            .authorizePayload(authz -> authz
                // First rule: require authenticated CONNECT authority.
                .setup().hasRole("CONNECT")

                // Specific routes before the deny-all fallback.
                .route("status.ping").authenticated()
                .route("events.stream").hasRole("READER")
                .route("events.channel").hasRole("READER")
                .route("tenant.read.{tenant}").hasRole("READER")
                .route("admin.audit").hasRole("ADMIN")

                // An unknown new request must NEVER be public by default.
                .anyRequest().denyAll()

                // Continued PAYLOADs may lack routing metadata.
                // This is NOT a substitute for per-item domain checks.
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults())
            .build();
    }
}
```

**Phân tích cấu hình:**

1. `@EnableRSocketSecurity` cấu hình support RSocket, không phải HTTP WebFlux filter chain.
2. Bean `PayloadSocketAcceptorInterceptor` được Spring Boot tự gắn vào RSocket server khi dependencies/auto-config đúng.
3. `simpleAuthentication()` dùng RSocket Simple Authentication Metadata Extension, **không phải HTTP Basic**.
4. `MapReactiveUserDetailsService` trả user data demo, `PasswordEncoder` lưu encoded passwords trong bộ nhớ.
5. `.setup().hasRole("CONNECT")` yêu cầu SETUP credentials có `ROLE_CONNECT`.
6. Các `route` rules là allowlist có quyền riêng. `.route("tenant.read.{tenant}")` match pattern route và tên biến là **input chưa tin cậy**.
7. `.anyRequest().denyAll()` từ chối request mở đầu tới route khác.
8. `.anyExchange().permitAll()` không mở route lạ vì request trước đó đã khớp `anyRequest().denyAll()`; nó phục vụ exchanges không phải request mới. Cần review metadata-push, channel data và custom handlers riêng.

**Không nên** thay `.anyRequest().denyAll()` bằng `.anyRequest().authenticated()` chỉ vì dễ test hơn: như vậy mọi route mới được thêm sau này mặc nhiên chỉ yêu cầu đăng nhập, ngay cả route administrative.

### 8.6 EventRSocketController.java

`src/main/java/com/example/securestream/EventRSocketController.java`:

```java
package com.example.securestream;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class EventRSocketController {

    @MessageMapping("status.ping")
    public Mono<String> ping() {
        return Mono.just("OK");
    }

    @MessageMapping("events.stream")
    public Flux<String> events() {
        return Flux.interval(Duration.ofMillis(100))
            .take(3)
            .map(n -> "event-" + (n + 1));
    }

    @MessageMapping("events.channel")
    public Flux<String> channel(Flux<String> messages) {
        // Limit accepted items in this teaching example.
        // Production also needs byte-size, request-rate and time limits.
        return messages
            .take(2)
            .map(msg -> {
                if (msg.length() > 256) {
                    throw new IllegalArgumentException(
                        "Message too long");
                }
                return "ack:" + msg;
            });
    }

    @MessageMapping("admin.audit")
    public Mono<String> adminAudit() {
        return Mono.just("AUDIT-OK");
    }

    @MessageMapping("tenant.read.{tenant}")
    public Mono<String> tenantRead(
            @DestinationVariable String tenant) {

        // This is a small, deliberate server-side ACL illustration.
        // Route variable is NOT trusted just because it is metadata.
        return ReactiveSecurityContextHolder.getContext()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Missing security context")))
            .flatMap(context -> {
                Authentication auth = context.getAuthentication();
                if (auth == null || !auth.isAuthenticated()) {
                    return Mono.error(new AccessDeniedException(
                        "Unauthenticated"));
                }

                boolean permitted =
                    "admin".equals(auth.getName())
                    && ("north".equals(tenant)
                        || "south".equals(tenant));

                permitted = permitted
                    || ("reader".equals(auth.getName())
                        && "north".equals(tenant));

                if (!permitted) {
                    return Mono.error(new AccessDeniedException(
                        "Tenant not permitted"));
                }

                return Mono.just("tenant:" + tenant);
            });
    }
}
```

Đây là **ACL demo đơn giản**:
- `reader` có ROLE_READER nhưng chỉ được `tenant.read.north`.
- `admin` có ROLE_READER và ROLE_ADMIN, được north/south.
- `guest` chỉ CONNECT, không qua được route tenant vì thiếu ROLE_READER.

Mục đích là chứng minh **role route-level không thay kiểm ownership/tenant-level**. Trong ứng dụng thật, `permitted` đến từ trusted tenant membership / database / authorization service và phải query theo principal đã xác thực + tenant/resource, không hardcode username.

### 8.7 Lỗi nếu bỏ kiểm tenant trong Controller

Nếu code chỉ dùng `.route("tenant.read.{tenant}").hasRole("READER")` rồi trả dữ liệu cho bất kỳ tenant nào trong route variable, user reader có thể tự gọi `tenant.read.south` để đọc dữ liệu tenant south. Rule READER chỉ cho biết user có loại quyền “đọc”, **không nói đọc tenant nào**.

Bất kỳ biến route, data body hay custom metadata cũng phải được coi là **untrusted request input**. Không bao giờ ghép trực tiếp route var vào câu SQL không tham số hoặc đường dẫn file không kiểm.

## 9. RSocketRequester gửi Simple Authentication metadata

Với **RSocket Simple Authentication**, sender cần:

1. Đúng MIME authentication `message/x.rsocket.authentication.v0`.
2. `UsernamePasswordMetadata` mang username/password.
3. `SimpleAuthenticationEncoder` được thêm vào `RSocketStrategies` client.
4. `setupMetadata(...)` trước khi kết nối nếu auth ở SETUP; hoặc `metadata(...)` trên mỗi request nếu auth request-time.
5. TLS ở mạng thực tế để không lộ credentials.

Ví dụ builder:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(builder ->
        builder.encoder(new SimpleAuthenticationEncoder()))
    .setupMetadata(
        new UsernamePasswordMetadata("reader", "reader-secret"),
        authMime)
    .tcp("127.0.0.1", 7000);
```

Đây là **snippet**; cần imports `RSocketRequester` từ Spring Messaging, `MimeType`/`MimeTypeUtils`, `WellKnownMimeType`, `UsernamePasswordMetadata` và `SimpleAuthenticationEncoder`. `tcp(...)` trong Spring Framework 6.x trả requester và connection được dùng khi có request; thuộc client builder API hiện đại. Khi hoàn tất, gọi `requester.dispose()` để giải phóng resources.

Đừng copy một `Authorization: Basic ...` HTTP header vào RSocket `.metadata(...)` với MIME tùy ý rồi mong `.simpleAuthentication()` tự hiểu: RSocket authentication metadata là định dạng khác.

### 9.1 Gửi per-request metadata (biến thể)

Nếu RSocket connection **đã được phép mở** và bạn muốn thay principal theo từng request, Spring hỗ trợ `.metadata(credentials, authMime)`:

```java
UsernamePasswordMetadata perRequestUser =
    new UsernamePasswordMetadata("reader", "reader-secret");

Flux<String> stream = requester
    .route("events.stream")
    .metadata(perRequestUser, authMime)
    .retrieveFlux(String.class);
```

Snippet trên **giả định** requester đã được tạo và encoder Simple Authentication đã đăng ký. Nếu server dùng `.setup().hasRole("CONNECT")` thì **SETUP vẫn phải cung cấp một identity có ROLE_CONNECT**, và per-request credentials có thể là identity khác. Không dùng một setup principal mạnh có quyền đọc dữ liệu cá nhân làm fallback cho requests của nhiều users.

### 9.2 Dùng Bearer JWT metadata thay Simple Authentication

Khi dùng OAuth2 JWT:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    return rsocket
        .authorizePayload(authz -> authz
            .setup().authenticated()
            .route("events.stream").hasAuthority("SCOPE_events.read")
            .route("admin.audit").hasAuthority("SCOPE_events.admin")
            .anyRequest().denyAll()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults())
        .build();
}
```

Đây là **một bean thay thế**, **không** bật cùng bean Simple Authentication phía trên. Muốn hoạt động cần `ReactiveJwtDecoder` thật do app/Boot tạo, ví dụ từ trusted issuer/JWKs. Bên gửi dùng `BearerTokenMetadata`, `BearerTokenAuthenticationEncoder` và RSocket auth MIME; không dùng JWT payload đã Base64-decoded mà không verify signature.

Lưu ý `hasRole("READER")` kiểm authority `ROLE_READER`, còn `hasAuthority("SCOPE_events.read")` kiểm exact scope authority. JWT Resource Server phải kiểm signature, `iss`, `exp`, `nbf` và `aud` theo trust policy; RSocket stream auth không tự thay thế audience validation.

## 10. RSocket integration tests thực tế với StepVerifier

Test dưới đây khởi động **embedded RSocket TCP server thật** ở port ngẫu nhiên rồi dùng `RSocketRequester` thực, không mock authentication. Test chịu trách nhiệm đóng requester sau mỗi request.

### 10.1 File RSocketRouteSecurityTest.java

`src/test/java/com/example/securestream/RSocketRouteSecurityTest.java`:

```java
package com.example.securestream;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import io.rsocket.metadata.WellKnownMimeType;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.rsocket.server.address=127.0.0.1",
    "spring.rsocket.server.transport=tcp",
    "spring.rsocket.server.port=0"
})
class RSocketRouteSecurityTest {

    @Value("${local.rsocket.server.port}")
    int port;

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
        );

    private RSocketRequester requester(String user, String password) {
        return RSocketRequester.builder()
            .rsocketStrategies(b ->
                b.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(
                new UsernamePasswordMetadata(user, password),
                AUTH_MIME)
            .tcp("127.0.0.1", port);
    }

    private Mono<String> request(
            String user, String password, String route) {

        // Use and dispose a dedicated requester for the test.
        return Mono.using(
            () -> requester(user, password),
            r -> r.route(route).retrieveMono(String.class),
            RSocketRequester::dispose
        );
    }

    private Flux<String> stream(String user, String password) {
        return Flux.using(
            () -> requester(user, password),
            r -> r.route("events.stream").retrieveFlux(String.class),
            RSocketRequester::dispose
        );
    }

    private Flux<String> channel(String user, String password) {
        return Flux.using(
            () -> requester(user, password),
            r -> r.route("events.channel")
                .data(Flux.just("one", "two"), String.class)
                .retrieveFlux(String.class),
            RSocketRequester::dispose
        );
    }

    @Test
    void readerCanPing() {
        StepVerifier.create(
            request("reader", "reader-secret", "status.ping"))
            .expectNext("OK")
            .verifyComplete();
    }

    @Test
    void readerCanOpenRequestStream() {
        StepVerifier.create(stream("reader", "reader-secret"))
            .expectNext("event-1", "event-2", "event-3")
            .verifyComplete();
    }

    @Test
    void readerCanOpenChannel() {
        StepVerifier.create(channel("reader", "reader-secret"))
            .expectNext("ack:one", "ack:two")
            .verifyComplete();
    }

    @Test
    void guestCanPingButCannotReadEvents() {
        StepVerifier.create(
            request("guest", "guest-secret", "status.ping"))
            .expectNext("OK")
            .verifyComplete();

        StepVerifier.create(stream("guest", "guest-secret"))
            .expectError()
            .verify();
    }

    @Test
    void readerCannotCallAdminAudit() {
        StepVerifier.create(
            request("reader", "reader-secret", "admin.audit"))
            .expectError()
            .verify();
    }

    @Test
    void adminCanCallAdminAudit() {
        StepVerifier.create(
            request("admin", "admin-secret", "admin.audit"))
            .expectNext("AUDIT-OK")
            .verifyComplete();
    }

    @Test
    void unknownRouteIsNotAllowed() {
        StepVerifier.create(
            request("admin", "admin-secret", "secret.new.route"))
            .expectError()
            .verify();
    }

    @Test
    void wrongSetupPasswordCannotUseConnection() {
        StepVerifier.create(
            request("reader", "wrong-password", "status.ping"))
            .expectError()
            .verify();
    }

    @Test
    void tenantMembershipCheckedAfterRouteRole() {
        StepVerifier.create(
            request("reader", "reader-secret", "tenant.read.north"))
            .expectNext("tenant:north")
            .verifyComplete();

        StepVerifier.create(
            request("reader", "reader-secret", "tenant.read.south"))
            .expectError()
            .verify();

        StepVerifier.create(
            request("admin", "admin-secret", "tenant.read.south"))
            .expectNext("tenant:south")
            .verifyComplete();
    }
}
```

**Lưu ý quan trọng:**
- `@Value("${local.rsocket.server.port}")` dùng local RSocket port mà Spring Boot 3.x test infrastructure đưa vào Environment sau khi embedded server bắt đầu. Khác với `server.port` của HTTP.
- Test `unknownRouteIsNotAllowed` kỳ vọng lỗi, nhưng nếu framework báo “no route handler found” thay vì security denial, test chỉ chứng minh request không trả dữ liệu. Muốn khẳng định cụ thể rule bị kích hoạt, thêm metric/test authorization manager hoặc custom logging/test spy.
- `.expectError()` ở negative tests xác minh request không thành công, **không phân biệt tất cả mã lỗi RSocket**. Ở RSocket, lỗi thường được truyền qua stream error signal/ERROR frame chứ không có HTTP status 401/403 trực tiếp.
- Auth setup dùng credentials demo, hiện tại TCP loopback. Không dùng password thật trong committed tests.
- `Mono.using` và `Flux.using` gọi `dispose()` khi publisher kết thúc để tránh giữ nhiều RSocket connections.
- Test không có IdP/JWT, không chứng minh TLS, token expiry/rotation và revoke giữa stream. Mỗi nhóm này cần integration tests riêng.

### 10.2 Lệnh chạy

Linux/macOS:

```bash
./gradlew test --tests '*RSocketRouteSecurityTest'
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*RSocketRouteSecurityTest'
.\gradlew.bat bootRun
```

App demo TCP server được cấu hình ở port `7000` cho `bootRun`; **test đặt port 0** để tránh va chạm với app đang chạy. Không cần chạy `bootRun` trước khi test.

**Kết quả mong đợi** (không phải log test đã chạy trong quá trình soạn):
- reader đọc ping, mở stream và channel thành công;
- guest chỉ được ping, không đọc stream;
- reader không gọi admin;
- admin gọi admin được;
- wrong password SETUP bị từ chối;
- tenant south bị từ chối với reader;
- route lạ không được trả dữ liệu.

### 10.3 Test mà chỉ đổi @MessageMapping không đủ

Nếu bạn thay `@MessageMapping("admin.audit")` thành `@MessageMapping("admin.download")` nhưng quên cập nhật `authorizePayload`, `anyRequest().denyAll()` sẽ chặn route mới — đó là default an toàn. Nếu trước đó viết `anyRequest().authenticated()`, route mới có thể **được mở cho mọi user đã đăng nhập**.

Vì vậy khi thêm route:
1. Định nghĩa rõ role/scope/tenant policy;
2. Viết negative test “user đã xác thực nhưng thiếu quyền”;
3. Chỉ sau đó mới cho phép route trong DSL;
4. Chạy integration test trên **real RSocket transport**, không chỉ gọi trực tiếp controller method.

## 11. Đăng ký custom metadata MIME và đọc bằng @Header

Một nhu cầu phổ biến: client gửi `tenant-id` để chọn dataset hoặc `trace-id` để theo dõi request. **Metadata không được tin làm permission**; nó chỉ là input.

### 11.1 Server-side metadata extractor

Nếu thêm metadata type:

```text
message/x.example.tenant.v1
```

Ta cần đăng ký extractor cho `String`:

```java
package com.example.securestream;

import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.codec.StringDecoder;
import org.springframework.util.MimeType;

@Configuration(proxyBeanMethods = false)
public class TenantMetadataConfig {

    public static final MimeType TENANT_MIME =
        MimeType.valueOf("message/x.example.tenant.v1");

    @Bean
    RSocketStrategiesCustomizer tenantMetadata() {
        return strategies -> strategies
            .decoder(StringDecoder.allMimeTypes())
            .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    TENANT_MIME, String.class, "tenant-id"));
    }
}
```

**Đây là một file Java bổ sung tùy chọn**, không cần cho demo/test chính ở mục 8–10. `RSocketStrategiesCustomizer` được Spring Boot dùng để tùy biến codecs/metadata extractor; extractor decode entry theo MIME rồi lưu dưới key `tenant-id`.

Với custom MIME và String data, ta bổ sung `StringDecoder.allMimeTypes()` để metadata decode không bị giới hạn chỉ `text/plain`. Không cấu hình “ignore tất cả metadata chưa hiểu”; unknown security metadata cần bị từ chối hoặc không được tạo identity.

### 11.2 Client gửi metadata cùng route

```java
import org.springframework.core.codec.CharSequenceEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester r = RSocketRequester.builder()
    .rsocketStrategies(b -> {
        b.encoder(new SimpleAuthenticationEncoder());
        b.encoder(CharSequenceEncoder.allMimeTypes());
    })
    .setupMetadata(
        new UsernamePasswordMetadata("reader", "reader-secret"),
        AUTH_MIME)
    .tcp("127.0.0.1", 7000);

Mono<String> result = r.route("tenant.read.north")
    .metadata("north", TenantMetadataConfig.TENANT_MIME)
    .retrieveMono(String.class);
```

Đây là **client snippet**, cần imports của `UsernamePasswordMetadata`, `SimpleAuthenticationEncoder`, `Mono` và giá trị `AUTH_MIME` như mục 10. Đoạn này **không phải file hoàn chỉnh**. `CharSequenceEncoder.allMimeTypes()` cho phép String metadata được encode dưới custom MIME.

### 11.3 Controller @Header và kiểm metadata

Một biến thể cho handler:

```java
@MessageMapping("tenant.read.{tenant}")
public Mono<String> tenantRead(
        @DestinationVariable String tenant,
        @Header(value = "tenant-id", required = false)
        String tenantMetadata) {

    if (tenantMetadata == null
            || !tenantMetadata.equals(tenant)) {
        return Mono.error(new AccessDeniedException(
            "Tenant route and metadata differ"));
    }

    return trustedTenantPolicy.checkCurrentPrincipal(tenant)
        .flatMap(allowed -> allowed
            ? Mono.just("tenant:" + tenant)
            : Mono.error(new AccessDeniedException(
                "Tenant not permitted")));
}
```

**Đây là method snippet về policy**, không phải method thay thế độc lập có thể compile ngay: `trustedTenantPolicy` là service mà app thật phải implement bằng verified authentication + trusted ACL. Nó yêu cầu imports `@MessageMapping`, `@DestinationVariable`, `@Header`, `AccessDeniedException` và `Mono`. Cố ý không tự hiện thực `trustedTenantPolicy` bằng việc so hai chuỗi do client kiểm soát: **route và metadata nhất quán chưa có nghĩa user được quyền tenant đó**.

Trong ứng dụng thật, metadata tenant có thể bị bỏ qua hoàn toàn nếu tenant lấy từ trusted JWT claims/session/membership. Mục đích của `@Header` chỉ là trích metadata **sau khi decode**, không nâng nó thành source of authority.

### 11.4 Các test metadata nên có

- Không có tenant-id khi route buộc phải có → từ chối;
- Tenant-id rỗng/quá dài/ký tự ngoài allowlist → từ chối;
- Route tenant north, metadata tenant south → từ chối;
- Reader có role READ nhưng **không thuộc north** → từ chối;
- Admin được phép north/south theo trusted ACL → thành công;
- Caller cố gởi custom metadata `role=ADMIN` → **không tự được cấp ROLE_ADMIN**;
- Một payload có nhiều entries cùng key tenant → quy tắc duy nhất, tránh chọn first/last bất định;
- Unsupported MIME và malformed composite metadata → không bypass auth;
- Giá trị trace-id độc hại chứa newline/escape/control chars → sanitize trước khi log;
- Raw authentication metadata không bao giờ xuất hiện trong tracing/metrics.

## 12. JWT và Bearer authentication metadata: khi dùng IdP

RSocket có **Bearer Token Authentication Metadata Extension**. Ở Spring Security, sender có thể dùng `BearerTokenMetadata` và `BearerTokenAuthenticationEncoder`, receiver dùng `RSocketSecurity.jwt(...)`.

Ví dụ client (snippet):

```java
MimeType authenticationMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
    );

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(b ->
        b.encoder(new BearerTokenAuthenticationEncoder()))
    .setupMetadata(
        new BearerTokenMetadata("<REDACTED_SIGNED_JWT>"),
        authenticationMimeType)
    .tcp("127.0.0.1", 7000);
```

Cần imports `BearerTokenMetadata` và `BearerTokenAuthenticationEncoder` từ Spring Security RSocket metadata package. Placeholder `<REDACTED_SIGNED_JWT>` **không phải token dùng được**.

**Khác HTTP:**
- Không gửi `Authorization: Bearer` HTTP header rồi mong RSocket JWT auth tự đọc được.
- JWT nằm trong RSocket auth metadata MIME.
- Server phải có `ReactiveJwtDecoder` phù hợp để verify chữ ký và issuer/expiry/audience.
- Scope được map thành authorities như `SCOPE_events.read` theo decoder/authorities converter.
- Token của route A không được tự gửi tới service/issuer B nếu client có kết nối tới nhiều backend.

### 12.1 Token hết hạn trong một stream dài

Khi JWT được xác minh **tại SETUP** hoặc **tại thời điểm mở request**, stream có thể tiếp tục phát dữ liệu lâu hơn thời hạn `exp` ban đầu nếu ứng dụng không tự áp dụng recheck/cancel. **Không giả định Spring Security tự hủy mọi stream đang chạy ngay đúng giây token hết hạn**, hoặc có re-introspection cho từng event.

Với dữ liệu nhạy cảm:
- Đặt max stream/session duration;
- Dùng periodic reauthorization hoặc ràng buộc stream lifetime với token expiration đã verify;
- Khi revoke/quyền thay đổi, phát tín hiệu đóng kết nối/cancel stream theo session registry hoặc event-driven policy;
- Với request-time auth, buộc client cung cấp token mới khi mở request mới;
- Có short-lived tokens, refresh ở OAuth2 Client **ngoài RSocket resource stream**, không gửi refresh token vào metadata của Resource Server;
- Kiểm downstream ACL tại thời điểm đọc từng tài nguyên nếu threat model yêu cầu;
- Dừng gửi ngay khi principal bị disable/tenant access bị thu hồi theo policy.

## 13. Luồng dài, request-channel và quyền theo từng payload

### 13.1 Request-stream

`events.stream` chỉ cần một `REQUEST_STREAM` ban đầu; server gửi nhiều `PAYLOAD` cho tới completion hoặc cancellation. Rule `route("events.stream").hasRole("READER")` bảo vệ **việc mở stream**, không chứng minh mỗi event phát ra trong tương lai vẫn được phép.

Nếu stream kéo dài hàng giờ, cần:
- `timeout`/session lifetime;
- recheck/reauthorize định kỳ hoặc khi nhận quyền thay đổi;
- consumer-side cancellation;
- server-side resource policy theo tenant/subject;
- quotas active streams per principal;
- hạn số event/byte, memory và retention khi client chậm.

### 13.2 Request-channel

`REQUEST_CHANNEL` mang initial request với routing metadata; những payload tiếp theo thường không có route mới. Vì vậy:
- Kiểm route và identity ở **initial request**;
- Kiểm từng item dữ liệu về length/schema/tenant/authorization context;
- Không cho một message sau tự gán `role=ADMIN` rồi dùng quyền khác;
- Khi reconnect/channel restart, đòi authorization mới;
- Tôn trọng `request(n)` backpressure/`CANCEL`; không mở luồng không giới hạn chỉ vì user đã authenticated;
- Đặt per-message và per-channel quotas, không chỉ per-connection rate limiting.

Trong code demo, `events.channel` dùng `take(2)` và giới hạn String length 256 để minh họa; production phải còn giới hạn bytes trước decode, quotas, timeout và kiểm business rules.

### 13.3 Metadata-push và SETUP

`METADATA_PUSH` là interaction connection-level, có thể được handler `@ConnectMapping` tiếp nhận. **Không coi nó như một route đã qua `.route("...").hasRole(...)`** nếu payload không mang route request metadata.

Khi ứng dụng xử lý metadata-push để đổi subscription/tenant/feature flag:
- Explicitly authorize theo current trusted connection principal;
- Đối với thay đổi identity, không chấp nhận metadata push tự tuyên bố một user mới;
- Không dùng metadata-push để “refresh” authentication mà không đi qua trusted auth flow;
- Nếu không dùng metadata-push, có thể reject/ignore nó qua policy riêng;
- Kiểm RSocket `PayloadExchangeType` trong custom matcher/interceptor nếu cần chặn một số exchange types;
- Giữ `anyExchange().permitAll()` chỉ khi toàn bộ handlers/interactions còn lại an toàn theo kiến trúc.

### 13.4 Backpressure không phải authorization

RSocket sử dụng Reactive Streams demand để giảm áp lực luồng dữ liệu. Nhưng backpressure:
- Không biết user có scope/role/tenant permission;
- Không chặn token revoked;
- Không chống DoS từ client mở hàng nghìn streams nếu không có quotas;
- Không thay payload validation và network policy.

Backpressure là **flow-control**, authorization là **security decision**. Cả hai cần được thiết kế đồng thời.

## 14. Kiểm soát route variables và metadata trong policy động

### 14.1 Route variable là untrusted input

```text
tenant.read.north
tenant.read.south
tenant.read.anything
```

Nếu security DSL dùng `route("tenant.read.{tenant}")`, cả ba routes có thể match về **hình thức**. Điều đó không khẳng định tenant hợp lệ, cũng không khẳng định user được đọc tenant đã chỉ định. Controller/service phải so tenant ID với membership đã xác minh; khi cần, dùng custom `.access((authentication, context) -> ...)` và policy service reactive.

Không tạo scope bằng cách ghép không kiểm:
```java
// Dễ lỗi nếu metadata/route do client kiểm soát:
String wanted = "SCOPE_" + tenantIdFromRoute + ".admin";
```

Thay vào đó, server có trusted tenant identifiers, grants và per-resource ACL; client request chỉ định **đối tượng muốn truy cập**, không chỉ định authority được cấp.

### 14.2 Custom PayloadExchangeMatcher

Spring Security DSL hỗ trợ `.matcher(PayloadExchangeMatcher)` và `.access(...)` để thực hiện điều kiện phức tạp. API matcher dùng `PayloadExchange`/exchange type và route metadata, chứ không nhận HTTP `ServerWebExchange`.

Một ví dụ **cấu trúc DSL**, không phải file Java hoàn chỉnh:

```java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("CONNECT")
    .route("tenant.read.{tenant}")
        .access((authentication, context) ->
            policyService.canReadTenant(
                authentication, context))
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

Ở đây `policyService.canReadTenant(...)` là **contract giả định** bạn phải triển khai, trả `Mono<AuthorizationDecision>` theo trusted user/tenant membership. Đừng tự đoán cách lấy route variables từ context: theo docs, matcher có thể cung cấp route variables, nhưng key/API extraction cần kiểm phiên bản Spring Security thật. Mẫu đầy đủ ở mục 8 dùng route-level role **và** ACL trong controller để tránh import/custom API chưa được định nghĩa.

### 14.3 Không đưa route/metadata vào log tùy ý

Route strings và metadata có thể chứa:
- Giá trị PII/tenant/customer IDs;
- Escape/newlines làm log injection;
- Opaque bearer credentials;
- Trace IDs không kiểm format;
- Kích thước cực lớn làm đầy logs.

Chỉ log route name được allowlist, principal ID đã minimize, request/stream correlation ID đã sanitize, security decision và latency. **Không log raw auth metadata, JWT, username/password, token endpoint response hoặc byte buffers**.

## 15. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Route admin ai cũng dùng được | `anyRequest().authenticated()` đặt trước `route("admin.*")` | Đặt routes cụ thể trước; fallback denyAll |
| Admin route được permitAll | `anyExchange().permitAll()` đặt đầu | Dời xuống cuối; test negative |
| Không kết nối được dù username/password đúng | Client thiếu `SimpleAuthenticationEncoder` hoặc auth MIME sai | Dùng `UsernamePasswordMetadata` + đúng MIME/encoder |
| Gửi HTTP Basic header vào RSocket | Nhầm protocol | Dùng RSocket Simple Authentication metadata |
| Bearer token hợp lệ vẫn bị reject | Chưa đăng ký JWT receiver/encoder, issuer/expiry sai | Kiểm `jwt()` + decoder + metadata MIME |
| Route được mở nhưng channel payload lỗi | `anyExchange().denyAll()` chặn PAYLOAD nối tiếp | Tách initial request policy và non-request policy |
| Channel item được dùng như metadata permission | Không validate từng message | Schema/tenant policy per item |
| Có quyền READER nhưng đọc tenant khác | Tin route variable `{tenant}` | Trusted ACL check trong handler/service |
| Thêm handler mới và mọi user đã login gọi được | Fallback `anyRequest().authenticated()` quá rộng | `anyRequest().denyAll()` |
| Token đã revoke nhưng stream vẫn phát | Chỉ kiểm tại setup/request đầu | Stream lifetime/recheck/cancellation/revocation events |
| Shared connection lộ dữ liệu user A cho B | Setup identity dùng thay request-time identity | User-specific auth trên từng request |
| Metadata push đổi role được | Tin custom metadata là source of authority | Chặn self-asserted role, trusted auth only |
| CUSTOM MIME không đọc qua `@Header` | Thiếu `metadataExtractorRegistry` hoặc codec | Đăng ký MIME, decoder, metadata key |
| CUSTOM MIME string encode không được | Encoder chỉ hỗ trợ text/plain | Thêm phù hợp `CharSequenceEncoder.allMimeTypes()` |
| RSocket qua WebSocket đã được auth HTTP | Tưởng HTTP handshake đủ cho mọi route | Cấu hình RSocket Security riêng |
| Server tạo thủ công không có security | Quên gắn `SecuritySocketAcceptorInterceptor` | Gắn interceptor vào RSocketServer |
| Tests gọi trực tiếp controller pass | Bypass security socket acceptor | Test qua RSocketRequester thực |
| Test unknown route lỗi nhưng không rõ vì sao | Handler không tồn tại cũng gây lỗi | Inspect error type/security metric, thêm allowed handler không được phép |
| CORS lỗi với browser WebSocket | Origin/handshake policy | Kiểm HTTP upgrade/origin và RSocket auth riêng |
| Nhiều requests làm memory cao | Unlimited channels/connections | Per-principal quotas, frame limits, timeouts |
| Password bị lộ trên mạng | Dùng plaintext TCP cho Simple Authentication | TLS hoặc loopback-only demo |
| `@ConnectMapping` tác động tới business mà không check | Metadata push/setup không qua route auth tương ứng | Separate authorization/validation |
| Route matcher pattern quá rộng | `admin.*` vô tình match route khác | Match exact, test patterns |
| Hỏng khi upgrade Spring Security | Thay đổi DSL/mime/decoder | Lock/test Boot/Security/RSocket versions |

## 16. Quy trình debug có trách nhiệm

Khi kết nối hoặc route bị từ chối, xác định **bước bị lỗi** trước khi sửa:

1. **TCP/WebSocket**: host, port, DNS, TLS, origin, proxy, handshake; nếu lỗi connection refused thì chưa tới route authorization.
2. **RSocket SETUP**: data/metadata MIME, simple/bearer encoder, credentials, `setup()` rule; nếu fail ngay khi connect/use, kiểm đây.
3. **Routing metadata**: client gọi `route("...")` chính xác chưa, server có `@MessageMapping` tương ứng chưa.
4. **Authentication**: identity được xác minh qua credential tại SETUP hoặc mỗi request chưa; không nhìn token string rồi đoán.
5. **Authorization**: role/scope thuộc principal; policy order/fallback; route variables/tenant ACL.
6. **Codec**: data MIME, custom metadata MIME, encoder/decoder có cùng contract không.
7. **Stream lifecycle**: expiry/revocation, backpressure, cancel, timeouts, channel item limits, connector reconnect.
8. **Observability**: log/error metrics đã loại secret; không bật global wiretap chứa raw metadata trong production.

RSocket lỗi được gửi qua reactive error signals hoặc protocol ERROR frames; **không có HTTP 401/403 cho mỗi RSocket route**. Với RSocket over WebSocket, HTTP status chỉ có thể liên quan handshake/upgrade ở tầng khác. Bài test `expectError()` không phân biệt được mọi security error nếu bạn không inspect loại exception.

## 17. Checklist production

- [ ] RSocket TCP/WebSocket endpoint được expose có chủ đích và có TLS/trusted network boundaries.
- [ ] Spring Boot đã gắn `SecuritySocketAcceptorInterceptor`, không bypass bằng server riêng chưa có auth.
- [ ] Có `@EnableRSocketSecurity` và bean `PayloadSocketAcceptorInterceptor`.
- [ ] Đã chọn setup vs per-request authentication phù hợp mô hình identity/connection reuse.
- [ ] `SimpleAuthenticationEncoder` / `BearerTokenAuthenticationEncoder` và MIME types đúng trên client.
- [ ] JWT access tokens được verify signature/issuer/audience/expiry/allowed algorithms; refresh token không gửi tới Resource Server.
- [ ] `.setup()` rule rõ ràng, connection principal không mặc nhiên được quyền data.
- [ ] Route-specific roles/scopes được khai **trước** fallbacks.
- [ ] `anyRequest().denyAll()` chặn request routes không liệt kê.
- [ ] `anyExchange()` policy được audit cho channel follow-up và metadata push.
- [ ] Mọi route variable và custom metadata được coi là untrusted input.
- [ ] Domain ACL kiểm principal/tenant/resource ownership ở thời điểm cần.
- [ ] Metadata custom có MIME và extractor rõ; unknown/malformed metadata không được tự cấp quyền.
- [ ] Không có metadata/header `role=ADMIN` self-asserted được tin trực tiếp.
- [ ] Long-lived streams có max duration, cancellation, reauthorization/revocation strategy.
- [ ] Request-channel validate từng item về schema/size/tenant/side effects.
- [ ] Per-principal connection/stream/channel quotas, backpressure, frame-size limits và rate limits được cấu hình.
- [ ] Logs/traces/metrics không lưu raw token, password hoặc authentication metadata.
- [ ] Integration tests chạy qua RSocket transport, có positive/negative, unknown routes, setup errors, streams/channels và tenant ACL.
- [ ] Test với TLS, reverse proxy, WebSocket origin, reconnect/retry, IdP/JWKS rotation nếu dùng JWT.
- [ ] Khi thêm handler mới, cập nhật route policy/test tương ứng trước khi deploy.
- [ ] Có runbook cho account disable, session revocation, stream termination và credential leak.

## 18. Tự luyện tập

**Bài 1 — Kiểm thứ tự rule.** Thử đưa `anyRequest().authenticated()` lên trước `route("admin.audit").hasRole("ADMIN")`. Vì sao user reader có thể bị coi là đủ điều kiện cho route admin ở authorization layer? Hãy hoàn nguyên để route rule được áp trước.

**Bài 2 — Fail-closed fallback.** Đổi tên route handler thành `events.export` nhưng không sửa security DSL. Yêu cầu: gọi route mới phải bị từ chối bởi `anyRequest().denyAll()`, kể cả user admin.

**Bài 3 — Tenant authorization.** Viết ACL kiểm reader chỉ thuộc tenant north. Dù client dùng `tenant.read.south` và gửi metadata `tenant-id=south`, vẫn từ chối nếu trusted membership không cho.

**Bài 4 — Channel payload.** Tạo client gửi 10.000 messages trong `events.channel`. Kiểm server chỉ nhận tối đa số item policy cho phép, thực sự cancel upstream khi hoàn tất, và có byte/connection quotas.

**Bài 5 — Shared connection.** Giữ setup identity role CONNECT và yêu cầu auth per-request. Kiểm user A không thể dùng metadata/credential của user B và không mặc định hưởng quyền từ setup principal.

**Bài 6 — JWT expiry.** Dùng token exp rất ngắn trên stream dài. Chứng minh bằng test rằng **chính sách do bạn viết** mới đóng stream khi expiry/revocation, không giả định RSocket Security tự luôn kiểm từng PAYLOAD.

**Bài 7 — Metadata push.** Viết `@ConnectMapping` chỉ cho phép trusted client cập nhật một thông số non-sensitive. Chứng minh metadata-push không thể tự đổi role/tenant/access.

### Câu hỏi tự kiểm tra

**1. Route RSocket có phải URL HTTP không?** Không; nó được encode trong routing metadata và dùng cho `@MessageMapping`.

**2. `setup().hasRole("CONNECT")` bảo vệ cái gì?** SETUP/connection establishment, không tự thay domain ACL ở mọi route.

**3. Vì sao `anyRequest().denyAll()` đứng trước `anyExchange().permitAll()`?** Chặn requests mở đầu không match route, đồng thời không vô tình deny mọi PAYLOAD tiếp nối của channel.

**4. Nếu đặt `anyExchange().permitAll()` trước `route("admin.audit")`?** Rule admin không được xét; mất route authorization.

**5. Simple Authentication RSocket có dùng HTTP Basic header không?** Không. Dùng `UsernamePasswordMetadata` với RSocket auth MIME và encoder.

**6. Custom metadata `tenant=north` có xác minh membership không?** Không. Nó là input của client, cần trusted principal/ACL server-side.

**7. Khi nào nên gửi auth mỗi request?** Khi một connection được nhiều principals dùng chung hoặc cần user-level authorization trên mỗi request.

**8. Token JWT hết hạn sau khi stream mở có bị hủy tự động ngay không?** Không được mặc nhiên giả định; phải thiết kế refresh/recheck/cancellation/stream lifetime.

**9. Thế nào là request-channel payload không mang route?** Frame tiếp nối trong channel đã mở, có thể không có routing metadata mới; initial request đã được authorize nhưng data vẫn cần validation.

**10. Vì sao thử bằng controller unit test chưa đủ?** Vì nó bypass RSocket socket acceptor/authentication/authorization pipeline. Cần transport integration test.

## 19. Tóm tắt

Spring Security RSocket cho phép phân quyền theo connection setup và **route metadata** bằng `RSocketSecurity.authorizePayload()`. Một cấu hình an toàn cần:

```java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("CONNECT")
    .route("events.stream").hasRole("READER")
    .route("admin.audit").hasRole("ADMIN")
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

Nhưng **route pattern không thay thế domain ACL**, **custom metadata không phải quyền được xác minh**, và **stream dài không mặc nhiên bị reauthorize mỗi PAYLOAD**. Vì vậy phải kết hợp route policy, trusted authentication, metadata validation, tenant/resource authorization, quotas/backpressure, stream revocation và tests thực qua RSocket transport.

**Điểm nhớ cuối:** Chỉ tin vào principal sau Spring Security authentication; luôn kiểm client-controlled route/metadata; sắp thứ tự route rules trước fallback; giữ long-lived streams có giới hạn và có cơ chế hủy khi quyền thay đổi.

### Nguồn tham khảo chính thức

- [Spring Security 6.5 — RSocket Security](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html)
- [Spring Security 6.5 — RSocketSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security 6.5 — RSocketSecurity.AuthorizePayloadsSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.AuthorizePayloadsSpec.html)
- [Spring Security 6.5 — PayloadExchangeType API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/api/PayloadExchangeType.html)
- [Spring Framework 6.2 — RSocket protocol, RSocketRequester, MetadataExtractor](https://docs.spring.io/spring-framework/reference/6.2/rsocket.html)
- [Spring Boot 3.5 — RSocket auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [Spring Security RSocket Simple Authentication encoder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Security RSocket UsernamePasswordMetadata](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/UsernamePasswordMetadata.html)
- [RSocket protocol specifications](https://rsocket.io/about/protocol/)
