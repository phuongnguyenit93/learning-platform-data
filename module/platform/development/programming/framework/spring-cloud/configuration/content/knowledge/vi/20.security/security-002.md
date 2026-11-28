# Xác thực truy cập Config Server bằng Spring Security

Spring Cloud Config Server có thể trả về cấu hình cho nhiều ứng dụng Spring Boot. Các response này đôi khi chứa URL nội bộ, thông tin kết nối, feature flag và dữ liệu nhạy cảm. Vì vậy, không nên để mọi client trên mạng đều có thể gọi endpoint cấu hình. Cần xác thực danh tính của bên gọi và phân quyền theo loại thao tác, chẳng hạn đọc cấu hình, mã hóa/giải mã giá trị hoặc truy cập Actuator.

**Authentication (xác thực)** trả lời câu hỏi “bên gọi là ai?”. **Authorization (phân quyền)** trả lời “danh tính đó được phép làm gì?”. Spring Security cung cấp cơ chế để bảo vệ HTTP endpoint của Config Server bằng hai lớp này. Việc bảo vệ endpoint phải đi cùng TLS, quản lý credential và giới hạn mạng; chỉ bật Basic Auth mà không kiểm soát các lớp còn lại là chưa đủ.

## 1. Các đường truy cập cần bảo vệ

Config Server thường có nhiều nhóm endpoint:

| Nhóm endpoint | Ví dụ | Quyền nên xem xét |
| --- | --- | --- |
| Đọc cấu hình | `GET /billing-api/prod/main` | Client của ứng dụng được phép đọc cấu hình tương ứng |
| Đọc cấu hình dạng YAML/properties | `GET /billing-api-prod.yml` | Quyền đọc cấu hình tương đương endpoint JSON |
| Mã hóa/giải mã | `POST /encrypt`, `POST /decrypt` | Quyền quản trị mật mã riêng; đặc biệt hạn chế `/decrypt` |
| Health | `GET /actuator/health` | Có thể cho phép probe nội bộ đọc trạng thái tối thiểu |
| Chẩn đoán | `/actuator/env`, `/actuator/configprops`, `/actuator/conditions` | Quyền vận hành hạn chế; có thể tiết lộ thông tin cấu hình |
| Refresh | `POST /actuator/refresh`, `/actuator/busrefresh` | Chỉ pipeline/operator được phép kích hoạt |

Một client chỉ cần đọc cấu hình không nên mặc nhiên có quyền gọi `/decrypt`, xem toàn bộ Actuator hoặc phát refresh event. Phân quyền theo mục đích giúp giảm tác động nếu một credential của client bị lộ.

## 2. Thêm Spring Security vào Config Server

Ứng dụng Config Server cần dependency `spring-boot-starter-security`. Quản lý phiên bản thông qua Spring Boot dependency management/BOM của dự án; không tự chọn một phiên bản Spring Security riêng không tương thích.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
}
```

Khi thêm starter, Spring Boot auto-configure bảo vệ các HTTP endpoint theo cấu hình mặc định. Nếu không khai báo cơ chế người dùng riêng, ứng dụng thường tạo user mặc định và in password được sinh ra trong log khởi động. Đây chỉ là hành vi tiện lợi khi phát triển; không dùng password sinh tự động đó làm danh tính production lâu dài.

Trong production, cần khai báo rõ user store hoặc tích hợp identity provider, chọn phương thức xác thực, thiết lập quyền cho từng endpoint và kiểm tra cấu hình sau khi khởi động.

## 3. Cấu hình HTTP Basic cho môi trường nội bộ

HTTP Basic là lựa chọn đơn giản cho các service-to-service client trong mạng nội bộ. Client gửi username/password trong HTTP Authorization header. Vì credential chỉ được mã hóa theo Base64 ở tầng HTTP, **chỉ sử dụng Basic Auth qua HTTPS/TLS**.

Ví dụ dưới đây tạo hai danh tính minh họa: một client chỉ đọc cấu hình và một operator có thêm quyền dùng endpoint mã hóa/giải mã. Password được lấy từ biến môi trường, không hard-code trong mã nguồn:

```java
@Configuration
public class ConfigServerSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${CONFIG_READER_PASSWORD}") String readerPassword,
            @Value("${CONFIG_CRYPTO_ADMIN_PASSWORD}") String adminPassword) {

        UserDetails reader = User.withUsername("billing-client")
                .password(encoder.encode(readerPassword))
                .roles("CONFIG_READER")
                .build();

        UserDetails cryptoAdmin = User.withUsername("config-operator")
                .password(encoder.encode(adminPassword))
                .roles("CONFIG_READER", "CONFIG_CRYPTO_ADMIN")
                .build();

        return new InMemoryUserDetailsManager(reader, cryptoAdmin);
    }

    @Bean
    SecurityFilterChain configServerFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/encrypt", "/encrypt/**", "/decrypt", "/decrypt/**")
                            .hasRole("CONFIG_CRYPTO_ADMIN")
                        .requestMatchers(HttpMethod.GET, "/**")
                            .hasRole("CONFIG_READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Các import Java cần thiết gồm `Configuration`, `Bean`, `Value`, `HttpMethod`, `PasswordEncoder`, `BCryptPasswordEncoder`, `User`, `UserDetails`, `UserDetailsService`, `InMemoryUserDetailsManager`, `SecurityFilterChain`, `HttpSecurity` và `Customizer`.

Ví dụ dùng `InMemoryUserDetailsManager` để minh họa luồng phân quyền, không phải kho danh tính production cho hệ thống nhiều instance. Trong môi trường thật, lấy user/service account từ LDAP, identity provider hoặc cơ chế quản lý danh tính tập trung; lưu password trong secret manager và xoay vòng định kỳ.

Trong ví dụ, các GET endpoint yêu cầu role `CONFIG_READER`; `/encrypt` và `/decrypt` yêu cầu role `CONFIG_CRYPTO_ADMIN`; endpoint khác bị từ chối mặc định. `anyRequest().denyAll()` giúp endpoint mới được thêm vào không tự động trở thành public. Khi bật thêm Actuator hoặc endpoint quản trị, hãy khai báo quyền tường minh.

Spring Security mặc định bật CSRF protection. Ví dụ trên giữ nguyên CSRF; các GET request đọc cấu hình không cần CSRF token. Các POST như `/encrypt` hoặc `/decrypt` sẽ cần token theo chính sách CSRF hiện tại. Nếu xây dựng API chỉ dành cho machine-to-machine dùng bearer token trong Authorization header, có thể thiết kế CSRF policy riêng cho đúng endpoint không dùng cookie/session; không tắt CSRF toàn cục chỉ để làm cho một lệnh curl hoạt động.

## 4. Cấu hình Config Client gửi credential

Config Client có thể khai báo username/password trong cấu hình bên ngoài:

```yaml
spring:
  application:
    name: billing-api
  config:
    import: "configserver:https://config-server.internal:8443"
  cloud:
    config:
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
```

Khi khởi động, Config Client dùng credential để xác thực với Config Server. Các biến `CONFIG_SERVER_USERNAME` và `CONFIG_SERVER_PASSWORD` phải được cấp qua secret manager, Kubernetes Secret hoặc cơ chế an toàn tương đương.

Không nhúng credential vào URL dạng `https://user:password@host`, vì URL có thể xuất hiện trong log, process metadata, trace hoặc công cụ chẩn đoán. Cũng không commit password thật trong `application.yml` hoặc Git repository cấu hình.

Nếu dùng nhiều ứng dụng, cấp service account riêng cho từng client hoặc nhóm client. Không dùng chung một username/password cho toàn bộ microservice; nếu một service bị xâm nhập, credential dùng chung có thể cho phép đọc cấu hình của tất cả service khác.

## 5. Authentication khác authorization như thế nào?

Một client có thể xác thực thành công nhưng vẫn không được phép đọc một endpoint. Ví dụ:

| Danh tính | Đã xác thực? | Quyền | Kết quả mong đợi |
| --- | --- | --- | --- |
| `billing-client` | Có | `CONFIG_READER` | Đọc endpoint cấu hình được bảo vệ |
| `billing-client` | Có | Không có `CONFIG_CRYPTO_ADMIN` | Bị từ chối `/decrypt` |
| `config-operator` | Có | `CONFIG_READER`, `CONFIG_CRYPTO_ADMIN` | Đọc cấu hình và thao tác crypto theo chính sách |
| Client không có credential | Không | Không có | HTTP 401 hoặc bị chặn tại lớp gateway |
| User hợp lệ nhưng thiếu role | Có | Không đủ quyền | HTTP 403 |

Thông thường:

- **401 Unauthorized**: request chưa cung cấp danh tính hợp lệ hoặc credential không hợp lệ.
- **403 Forbidden**: danh tính đã được xác thực nhưng không có quyền thực hiện thao tác.

Phân biệt 401 và 403 giúp vận hành biết lỗi nằm ở credential hay policy phân quyền.

## 6. Giới hạn quyền đọc theo application

Trong hệ thống nhiều ứng dụng, yêu cầu bảo mật tốt hơn là client `billing-api` chỉ đọc được cấu hình của `billing-api`, còn `inventory-api` chỉ đọc được cấu hình của chính nó.

Có thể thiết kế authorization dựa trên application path, chẳng hạn các route dạng:

```text
/billing-api/{profile}/{label}
/inventory-api/{profile}/{label}
```

Với Spring Security, có thể dùng request matcher riêng cho từng nhóm route:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/billing-api/**")
        .hasRole("BILLING_CONFIG_READER")
    .requestMatchers(HttpMethod.GET, "/inventory-api/**")
        .hasRole("INVENTORY_CONFIG_READER")
    .requestMatchers(HttpMethod.GET, "/**")
        .hasRole("CONFIG_READER")
    .anyRequest().denyAll())
```

Đây là ví dụ minh họa cho endpoint JSON dạng application/profile/label. Config Server còn có các route biểu diễn khác như YAML/properties, route có profile trong tên hoặc endpoint bổ sung. Nếu triển khai phân quyền theo application, phải bao phủ **tất cả cách biểu diễn cùng một dữ liệu**, tránh trường hợp một client bị chặn ở JSON endpoint nhưng có thể đọc qua endpoint `.yml` tương đương.

Với policy phức tạp, nên dùng custom `RequestMatcher` hoặc `AuthorizationManager` để phân tích application name theo đúng route của phiên bản Config Server. Kiểm thử cả đường dẫn hợp lệ, đường dẫn biến thể, profile nhiều giá trị và label có dấu `/`. Không xem URL path matcher đơn giản là ranh giới bảo mật hoàn chỉnh nếu chưa kiểm chứng.

## 7. Dùng OAuth2/JWT cho hệ thống nhiều service

Với hệ thống có identity provider, OAuth2 Resource Server giúp Config Server xác thực access token JWT. Token có thể mang scope hoặc authority để phân biệt quyền đọc cấu hình và quyền quản trị.

Dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Cấu hình issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/platform
```

Security chain có thể kiểm tra scope:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/actuator/health").permitAll()
                    .requestMatchers(HttpMethod.GET, "/**")
                        .hasAuthority("SCOPE_config.read")
                    .requestMatchers(HttpMethod.POST, "/encrypt", "/decrypt")
                        .hasAuthority("SCOPE_config.crypto")
                    .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

Đoạn code này là một lựa chọn thay thế cho Basic Auth chain ở trên, không đăng ký đồng thời hai chain cùng match toàn bộ request. JWT scope thường được ánh xạ thành authority có tiền tố `SCOPE_`. Identity provider cần cấp đúng scope cho từng service account; Config Server phải kiểm tra issuer, audience và các claim cần thiết theo policy của tổ chức.

Nếu dùng bearer token và không dùng cookie/session authentication cho các endpoint API này, có thể cấu hình CSRF theo phạm vi hẹp phù hợp với mô hình machine-to-machine. Hãy đánh giá nguy cơ CSRF và các cơ chế browser trước khi bỏ qua bảo vệ; không tắt CSRF toàn cục một cách máy móc.

Config Client cần lấy access token từ identity provider theo client credentials flow hoặc cơ chế service identity phù hợp. Việc lấy token, cache, refresh và xử lý token hết hạn nên do thư viện OAuth2 client hoặc nền tảng triển khai đảm nhiệm, không tự viết logic lưu token plaintext.

## 8. mTLS và xác thực ở lớp mạng

Mutual TLS yêu cầu cả client và server xác thực certificate của nhau. mTLS hữu ích trong service mesh hoặc môi trường có PKI nội bộ, giúp xác định workload ở lớp kết nối.

Tuy nhiên, mTLS không tự động thay thế authorization ở tầng ứng dụng. Nếu mọi certificate hợp lệ đều được phép gọi mọi endpoint, một service có certificate vẫn có thể đọc dữ liệu không thuộc phạm vi của nó. Có thể kết hợp mTLS với Spring Security để ánh xạ identity/certificate sang quyền đọc cụ thể.

Tương tự, API gateway có thể xác thực token và áp dụng policy trước khi request tới Config Server, nhưng Config Server vẫn nên có lớp bảo vệ phù hợp để tránh truy cập vòng qua gateway. Không để endpoint cấu hình lộ trực tiếp ra mạng công cộng nếu kiến trúc yêu cầu chỉ truy cập nội bộ.

## 9. Bảo vệ Actuator và endpoint quản trị

Actuator thường được bật để health check, refresh hoặc chẩn đoán. Không nên phơi bày tất cả endpoint chỉ vì cần một endpoint health.

Ví dụ chỉ expose các endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Nếu cần `refresh`, `busrefresh`, `env` hoặc `configprops`, hãy thêm có chủ đích và tạo policy riêng. `env` và `configprops` có thể tiết lộ cấu trúc hoặc giá trị cấu hình; `refresh` và `busrefresh` có thể làm thay đổi hành vi nhiều ứng dụng. Chỉ cho operator hoặc pipeline có quyền tương ứng sử dụng.

Có thể tách management port/interface khỏi cổng API chính, giới hạn bind address vào mạng quản trị và áp dụng firewall/network policy. `management.server.port` và `management.server.address` là các thuộc tính có thể dùng tùy phiên bản Spring Boot; xác nhận cấu hình triển khai thực tế.

## 10. Phân biệt credential Config Client với credential Config Server tới Git

Có hai kết nối độc lập:

1. **Client → Config Server:** client xác thực để đọc cấu hình qua HTTP(S), dùng Basic Auth, OAuth2/JWT, mTLS hoặc cơ chế được tổ chức hỗ trợ.
2. **Config Server → Git/Vault:** server dùng credential riêng để đọc repository hoặc secret store.

Credential của client không phải credential truy cập Git. Không chia sẻ Git deploy key cho tất cả microservice chỉ để chúng có thể gọi Config Server. Server giữ quyền đọc backend; client chỉ nhận các property source mà authorization của server cho phép.

Ví dụ Git credential phía Config Server:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
```

Git token cần quyền đọc tối thiểu. Không dùng token này làm password HTTP Basic cho Config Client.

## 11. Kiểm thử xác thực và phân quyền

Trước khi triển khai, kiểm tra các trường hợp:

| Ca kiểm thử | Request | Kết quả mong đợi |
| --- | --- | --- |
| Không có credential | GET Config API | 401 hoặc bị gateway từ chối |
| Password sai | GET Config API | 401 |
| Credential hợp lệ, role đọc | GET Config API | 200 và `Environment` đúng phạm vi |
| Credential chỉ đọc | POST `/decrypt` | 403 |
| Credential operator | POST `/decrypt` | Được phép nếu CSRF và policy crypto hợp lệ |
| User không có role refresh | POST `/actuator/refresh` | 403 |
| Client billing truy cập inventory | GET inventory route | 403 nếu policy cách ly theo application được bật |
| Certificate không tin cậy | HTTPS/mTLS request | TLS handshake bị từ chối |

Có thể thử endpoint đọc cấu hình bằng curl:

```bash
curl -i \
  -u "${CONFIG_SERVER_USERNAME}:${CONFIG_SERVER_PASSWORD}" \
  "https://config-server.internal:8443/billing-api/prod/main"
```

Không bật `--insecure` trong production để bỏ kiểm tra certificate. Không đặt password trực tiếp trong command line nếu terminal history hoặc process listing có thể ghi nhận nó; ví dụ trên chỉ minh họa cú pháp, thực tế nên dùng secret injection an toàn hoặc token flow.

Kiểm tra cả endpoint JSON và các endpoint YAML/properties, Actuator, encrypt/decrypt, các profile nhiều giá trị và label. Đảm bảo policy không vô tình mở endpoint do matcher quá rộng hoặc do một chain khác có thứ tự ưu tiên cao hơn.

## 12. Theo dõi, audit và rotation credential

Một hệ thống xác thực cần được vận hành liên tục:

- Audit danh tính gọi endpoint, thời điểm, application/profile/label và kết quả HTTP.
- Không ghi Authorization header, password, access token hoặc response chứa secret vào log.
- Theo dõi 401/403 tăng bất thường, token hết hạn, lỗi TLS và request tới endpoint nhạy cảm.
- Dùng service account riêng, quyền tối thiểu và thời hạn credential phù hợp.
- Rotation password, client secret, certificate và token signing key theo chính sách identity provider.
- Thu hồi ngay credential của service bị xâm nhập; không chỉ tạo password mới mà vẫn giữ credential cũ hoạt động.
- Kiểm tra quyền định kỳ và xóa service account không còn sử dụng.

Nếu dùng OAuth2/JWT, cần kiểm tra quy trình JWKS/key rotation, issuer/audience và thời gian hiệu lực token. Nếu dùng Basic Auth, dùng password hash an toàn ở nơi lưu trữ user và truyền secret qua kênh bảo mật. Với mTLS, quản lý cấp phát, gia hạn, thu hồi certificate và truststore.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Client nhận 401 | Thiếu username/password, token sai/hết hạn, sai issuer hoặc credential chưa được cấp |
| Client nhận 403 | Đã xác thực nhưng thiếu role/scope hoặc route matcher không cho phép |
| GET hoạt động nhưng POST encrypt/decrypt lỗi | CSRF token hoặc policy POST chưa được cấu hình phù hợp |
| Basic Auth gửi đúng nhưng vẫn bị từ chối | User store, password encoder, role prefix `ROLE_` hoặc SecurityFilterChain matcher |
| Actuator health hoạt động nhưng refresh bị chặn | Policy đã permit health nhưng chưa cấp quyền refresh |
| Client đọc được cấu hình ứng dụng khác | Policy path quá rộng, endpoint format khác chưa được bảo vệ hoặc credential dùng chung |
| TLS handshake thất bại | Truststore, certificate chain, hostname/SAN hoặc thời hạn certificate |

Khi debug, xác định request thất bại ở lớp TLS, authentication hay authorization. Không bật log chi tiết có thể in credential hoặc token ở môi trường production. Sử dụng correlation ID, principal name và status code để truy vết mà không ghi bí mật.

## 14. Checklist triển khai production

- [ ] Thêm `spring-boot-starter-security` và cấu hình SecurityFilterChain tường minh.
- [ ] Không dùng generated default password hoặc user dùng chung cho production.
- [ ] Chọn Basic Auth qua TLS, OAuth2/JWT hoặc mTLS phù hợp với hệ thống identity.
- [ ] Tách quyền đọc cấu hình, quyền crypto và quyền Actuator/refresh.
- [ ] Cấp service account riêng và quyền tối thiểu cho từng client.
- [ ] Nếu phân quyền theo application, bảo vệ mọi dạng endpoint trả về cùng dữ liệu.
- [ ] Không đặt credential trong URL, Git, image hoặc log.
- [ ] Bảo vệ `/encrypt`, `/decrypt`, `env`, `configprops`, `refresh` và `busrefresh`.
- [ ] Giữ CSRF protection hoặc chỉ điều chỉnh theo đúng mô hình API machine-to-machine đã đánh giá.
- [ ] Dùng TLS/mTLS và xác minh certificate; không bỏ qua hostname verification.
- [ ] Tách credential Client→Server khỏi credential Server→Git/Vault.
- [ ] Kiểm thử 401, 403, truy cập chéo application, Actuator và endpoint crypto.
- [ ] Có audit, alert, credential rotation và quy trình thu hồi quyền.

Spring Security giúp Config Server xác thực client và giới hạn quyền theo endpoint. Khi kết hợp danh tính riêng cho từng service, TLS, authorization theo ứng dụng, bảo vệ Actuator và quản lý credential có vòng đời, hệ thống có thể phân phối cấu hình tập trung mà không mở rộng quyền đọc vượt quá nhu cầu của từng thành phần.
