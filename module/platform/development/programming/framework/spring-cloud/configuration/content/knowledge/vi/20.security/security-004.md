# Không dùng application, profile hoặc label thay cho kiểm soát quyền

Spring Cloud Config Server nhận `application`, `profile` và `label` trong URL để tìm đúng bộ cấu hình. Ba giá trị này là bộ chọn tài nguyên, không phải bằng chứng về danh tính của client và cũng không phải quy tắc phân quyền. Một ứng dụng đã xác thực vẫn có thể thử đổi tên application trong request để đọc cấu hình của dịch vụ khác nếu Config Server chỉ kiểm tra đăng nhập mà không kiểm tra quyền trên từng tài nguyên.

Ví dụ, `order-service` được cấp credential để lấy cấu hình của chính nó. Nếu Config Server chỉ yêu cầu HTTP Basic hoặc một JWT hợp lệ, client đó có thể thử gọi `/payroll-service/prod/main`. Khi server không có chính sách phân quyền theo application, request vẫn có thể được chấp nhận. Nếu response chứa password database, token hoặc endpoint nội bộ của payroll, đây là rò rỉ bí mật giữa các dịch vụ.

Thiết kế an toàn phải tách ba việc: xác thực ai đang gọi, xác định application/profile/label mà request muốn đọc, rồi kiểm tra danh tính đó có quyền đọc đúng tổ hợp tài nguyên hay không.

## 1. Application, profile và label chỉ là selector

Config Client gửi yêu cầu cấu hình qua các thành phần URL:

```text
GET /{application}/{profile}/{label}
```

Ví dụ:

```text
GET /order-service/prod/release-2026.11
```

Ba phần có ý nghĩa:

| Thành phần | Mục đích | Vì sao không phải quyền truy cập |
|---|---|---|
| `application` | Chọn tên ứng dụng hoặc nhóm cấu hình cần đọc | Client có thể thay tên trong URL; tên không chứng minh client là ứng dụng đó |
| `profile` | Chọn biến thể cấu hình như `dev`, `test`, `prod` | Client có thể gửi profile bất kỳ, không cần chạy trong môi trường tương ứng |
| `label` | Chọn phiên bản nguồn cấu hình, thường là Git branch, tag hoặc commit | Tên branch/tag không chứng minh người gọi được phép đọc phiên bản đó |

Config Client mặc định lấy application từ `spring.application.name`, profile từ các active profiles và label từ cấu hình client. Những giá trị này có thể được ghi đè bằng `spring.cloud.config.name`, `spring.cloud.config.profile` và `spring.cloud.config.label`. `spring.cloud.config.name` còn có thể chứa danh sách tên phân tách bằng dấu phẩy để ghép nhiều nhóm property source. Người vận hành cũng có thể gọi trực tiếp HTTP API với một bộ giá trị khác.

Do đó:

- Đặt `spring.application.name=order-service` không chứng minh request đến từ tiến trình order-service.
- Gửi profile `prod` không chứng minh request đến từ workload production.
- Chọn label `release` hoặc một commit SHA không cấp quyền đọc lịch sử cấu hình đó.
- Đổi tên application thành tên khó đoán hoặc đặt secret trong một label riêng không phải biện pháp bảo mật.

Danh tính phải đến từ cơ chế xác thực độc lập như credential riêng của service, OAuth2 client identity, mTLS hoặc workload identity. Config Server dùng danh tính đã xác thực để kiểm tra selector trong request.

## 2. Một client có thể gọi nhiều dạng endpoint

Config Server không chỉ có endpoint Environment JSON. Các dạng HTTP resource phổ biến gồm:

```text
/{application}/{profile}[/{label}]
/{application}-{profile}.yml
/{label}/{application}-{profile}.yml
/{application}-{profile}.properties
/{label}/{application}-{profile}.properties
```

Ví dụ các request sau đều có thể trả cấu hình của `order-service`:

```bash
curl -i https://config.example.com/order-service/prod/main
curl -i https://config.example.com/order-service-prod.yml
curl -i https://config.example.com/main/order-service-prod.yml
curl -i https://config.example.com/order-service-prod.properties
```

Nếu chính sách chỉ bảo vệ `/order-service/**` mà để các endpoint dạng file truy cập tự do, client có thể chuyển sang URL `.yml` hoặc `.properties` để bỏ qua quy tắc. Mọi dạng endpoint được bật phải đi qua cùng chính sách phân quyền. Nếu ứng dụng chỉ cần endpoint Environment JSON, có thể từ chối các dạng khác bằng quy tắc `denyAll` mặc định.

## 3. Phân biệt authentication và authorization

**Authentication (xác thực)** trả lời câu hỏi: “Ai đang gọi?” Ví dụ:

- Username/password riêng cho từng service.
- OAuth2 access token có chữ ký hợp lệ và claim định danh client.
- Chứng thư client TLS được xác minh bởi Config Server hoặc gateway.
- Danh tính workload do nền tảng cấp.

**Authorization (phân quyền)** trả lời câu hỏi: “Danh tính này được phép đọc gì?” Ví dụ:

- `order-service` chỉ đọc application `order-service`.
- Service thanh toán được đọc profile `prod` nhưng không được đọc cấu hình `finance-admin`.
- Chỉ nhóm vận hành được truy cập label phát hành hoặc endpoint `/encrypt` và `/decrypt`.
- Endpoint health chỉ cho phép load balancer truy cập, không đồng nghĩa với quyền đọc cấu hình.

Spring Cloud Config 5.1.0 nêu rõ: mặc định bất kỳ người dùng đã xác thực nào cũng có thể yêu cầu cấu hình của bất kỳ `{application}` nào. Muốn cô lập bí mật giữa các dịch vụ, cần tự bổ sung chính sách trong `SecurityFilterChain` hoặc `RequestMatcher`.

Một tài khoản HTTP Basic dùng chung cho toàn bộ Config Client chỉ xác nhận rằng người gọi biết cùng một mật khẩu. Nó không cho Config Server biết client nào đang gọi. Khi cần phân quyền theo dịch vụ, cấp danh tính riêng và ánh xạ danh tính đó tới phạm vi application được phép.

## 4. Bật xác thực cho Config Server

### HTTP Basic Authentication

Thêm Spring Security, ví dụ qua `spring-boot-starter-security`. Cấu hình mặc định của Spring Boot tạo user `user` và mật khẩu ngẫu nhiên khi khởi động. Không nên dựa vào mật khẩu ngẫu nhiên này cho vận hành production; hãy dùng credential được quản lý rõ ràng và thay đổi theo chính sách.

Ví dụ cấu hình đơn giản:

```yaml
spring:
  security:
    user:
      name: configserver
      password: ${CONFIG_SERVER_PASSWORD}
```

Config Client cung cấp credential qua nguồn bảo mật của môi trường triển khai:

```yaml
spring:
  cloud:
    config:
      uri: https://config.example.com
      username: ${CONFIG_SERVER_USER}
      password: ${CONFIG_SERVER_PASSWORD}
```

HTTP Basic phù hợp cho môi trường nhỏ hoặc khi có tài khoản riêng cho từng client. Nếu tất cả service dùng chung một tài khoản, Config Server không thể phân biệt quyền của từng service chỉ từ username đó.

### OAuth2 Resource Server và JWT

Với nhiều client cần danh tính độc lập, có thể bảo vệ Config Server bằng OAuth2 Bearer Token. Thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Cấu hình issuer của authorization server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
```

Spring Security Resource Server kiểm tra chữ ký và các thuộc tính token theo cấu hình issuer/JWK. Trong production, cần xác nhận thêm audience, scope/role và claim định danh client theo hợp đồng của identity provider. Token hợp lệ của một API khác không nên tự động được chấp nhận để đọc cấu hình.

Config Client có thể lấy token bằng OAuth2 client registration và grant `client_credentials`. Với Spring Cloud Config hiện hành, bật OAuth2 trên Config Client và cung cấp registration ID:

```yaml
spring:
  cloud:
    config:
      uri: https://config.example.com
      oauth2:
        enabled: true
        client-registration-id: config-client

  security:
    oauth2:
      client:
        registration:
          config-client:
            client-id: ${CONFIG_CLIENT_ID}
            client-secret: ${CONFIG_CLIENT_SECRET}
            authorization-grant-type: client_credentials
        provider:
          config-client:
            token-uri: https://idp.example.com/oauth/token
```

Client cần có `spring-boot-starter-security-oauth2-client` trên classpath để Config Client dùng OAuth2 bearer-token interceptor tích hợp. Với phiên bản cũ hoặc cơ chế token riêng, có thể cần custom `RestTemplate`/HTTP interceptor. Không lưu client secret trong Git; cấp nó từ secret manager hoặc workload identity.

## 5. Phân quyền theo application bằng Spring Security

Một chính sách cơ bản là so sánh application trong URL với danh tính đã xác thực. Ví dụ sau minh họa endpoint Environment dạng `/{application}/...` và OAuth2 JWT:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ConfigServerSecurityConfig {

    @Bean
    SecurityFilterChain configServerSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/{application}/**").access((authentication, context) -> {
                    String requestedApplication =
                            context.getVariables().get("application");
                    String clientIdentity = authentication.get().getName();

                    return new AuthorizationDecision(
                            clientIdentity.equals(requestedApplication));
                })
                // Chỉ cho phép các route đã được khai báo rõ ràng.
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ví dụ này dựa trên nguyên tắc trong tài liệu Spring Cloud Config: application path phải khớp danh tính đã xác thực. Nó chỉ cho phép route dạng `/{application}/...`; các endpoint file như `/{application}-{profile}.yml` bị từ chối bởi `denyAll`. Nếu hệ thống cần các endpoint file, phải thêm matcher và kiểm tra application tương ứng cho từng dạng URL.

Trong ví dụ JWT, `Authentication.getName()` phải trả về một định danh client ổn định, ví dụ `order-service`. Mặc định tên principal của JWT thường lấy từ claim `sub`; nếu identity provider dùng claim `client_id` hoặc claim riêng, hãy cấu hình `JwtAuthenticationConverter` để ánh xạ claim đó thành principal/authority trước khi dùng trong chính sách. Không lấy tên client từ header tự do hoặc từ `spring.application.name` trong request vì người gọi có thể tự thay đổi.

### Nếu cần hỗ trợ endpoint YAML/Properties

Với số lượng application nhỏ, có thể dùng authority riêng theo service và khai báo các route cần thiết:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers(
        "/orders/**",
        "/orders-*.yml",
        "/orders-*.properties",
        "/{label}/orders-*.yml",
        "/{label}/orders-*.properties"
    ).hasAuthority("SCOPE_config.orders.read")
    .requestMatchers(
        "/payments/**",
        "/payments-*.yml",
        "/payments-*.properties",
        "/{label}/payments-*.yml",
        "/{label}/payments-*.properties"
    ).hasAuthority("SCOPE_config.payments.read")
    .anyRequest().denyAll()
)
```

Đây là đoạn minh họa các matcher theo tên application cụ thể. Với hệ thống lớn, nên viết một `RequestMatcher`/`AuthorizationManager` tập trung để phân tích các dạng endpoint được hỗ trợ, chuẩn hóa application/profile/label và tra cứu chính sách từ một bảng quyền. Cần kiểm thử cả URL chuẩn, URL có label, URL YAML, URL properties, URL mã hóa và các trường hợp path không hợp lệ.

Không chỉ thêm matcher cho route phổ biến rồi để `anyRequest().authenticated()`. Cách đó vô tình cho phép mọi người dùng đã xác thực truy cập những endpoint chưa được xét đến.

## 6. Phân quyền theo cả profile và label

Một service có thể được phép đọc cấu hình `dev` nhưng không được đọc `prod`, hoặc chỉ được đọc label đang triển khai. Khi yêu cầu bảo mật cần giới hạn như vậy, chính sách phải kiểm tra cả application, profile và label:

```text
authorization decision = policy(
    authenticated client identity,
    requested application,
    requested profile(s),
    requested label(s)
)
```

Ví dụ bảng quyền:

| Client identity | Application | Profile được phép | Label được phép |
|---|---|---|---|
| `order-service` | `order-service` | `dev`, `test`, `prod` | `main`, `release-*` |
| `order-test-runner` | `order-service` | `test` | `test-*` |
| `payment-service` | `payment-service` | `prod` | `release-*` |
| `ops-config-reader` | Danh sách application được quản lý | Theo nhiệm vụ | Theo nhiệm vụ |

Đây là chính sách ví dụ; phạm vi thực tế cần được cấp theo nguyên tắc tối thiểu. Nếu `spring.cloud.config.name` chứa nhiều application, policy phải kiểm tra tất cả tên và từ chối toàn bộ request nếu có một tên nằm ngoài phạm vi. Nếu profile chứa danh sách phân tách bằng dấu phẩy hoặc label hỗ trợ nhiều giá trị, policy phải kiểm tra từng phần tử và từ chối khi có phần tử nằm ngoài phạm vi. Nếu label bị bỏ qua, áp dụng default label của server và kiểm tra default đó có được phép.

Một request có profile `prod` vẫn chỉ là một yêu cầu đọc dữ liệu production. Nó không chứng minh workload đang chạy production. Tương tự, client không được tự nâng quyền bằng cách thay `spring.cloud.config.profile` hoặc `spring.cloud.config.label`.

## 7. Cấu hình dùng chung và composite repository ảnh hưởng ranh giới bảo mật

Spring Cloud Config luôn phục vụ property source `application` làm cấu hình nền mà mọi application kế thừa. Khi client `order-service` yêu cầu cấu hình, response có thể bao gồm cả `application.yml` và các file riêng của order-service.

Vì vậy:

- Chỉ đặt giá trị thật sự dùng chung và không nhạy cảm trong `application.yml`.
- Không đặt password, token, private key hoặc dữ liệu chỉ dành cho một dịch vụ vào file cấu hình nền.
- Không giả định application-level authorization sẽ che giấu một khóa nằm trong file dùng chung; file nền được trả cùng Environment của ứng dụng.

Với composite repository, Config Server tổng hợp property source từ các backend. Quyền đọc một application thường cho phép client nhận Environment đã tổng hợp cho application đó, bao gồm các nguồn phù hợp từ composite. Không nên dùng thứ tự repository hoặc label làm ranh giới bảo mật giữa các nhóm.

Nếu hai nhóm không được phép đọc cấu hình của nhau ở cấp repository hoặc dữ liệu, hãy cân nhắc tách Config Server theo trust zone, dùng backend/credential riêng và chính sách mạng riêng. Một endpoint chung có thể phục vụ nhiều application; nhưng khi backend chứa dữ liệu có mức độ bí mật khác nhau, việc cô lập ở hạ tầng thường dễ kiểm soát và kiểm toán hơn một policy động phức tạp.

## 8. Bảo vệ Git backend và bí mật

Config Server thường có quyền đọc Git repository bằng một credential server-side. Credential đó không phải credential của Config Client. Client chỉ nên nhận property source mà server đã cho phép, không được truy cập trực tiếp Git bằng quyền của Config Server.

Các nguyên tắc:

- Cấp quyền read-only cho credential Config Server trên đúng repository cần thiết.
- Dùng SSH deploy key hoặc `spring.cloud.config.server.git.username` và `spring.cloud.config.server.git.password` để cấp credential; tránh nhúng user/password vào phần userinfo của Git URI.
- Nếu Git URI dùng placeholder `{application}`, `{profile}` hoặc `{label}` để chọn repository, giới hạn các giá trị request bằng allow-list và không cho selector tùy ý tạo URL đến host hoặc repository khác.
- Đặt credential trong secret manager hoặc biến môi trường được quản lý, không commit vào Git.
- Không lưu bí mật dạng rõ trong repository chỉ vì repository là private.
- Dùng Vault, cloud secret manager hoặc KMS cho secret có vòng đời riêng; kiểm tra quyền truy cập ở backend và ở Config Server.
- Rotate credential khi nhân sự, workload hoặc quyền truy cập thay đổi.

Nếu dùng mã hóa `{cipher}` của Spring Cloud Config, cần bảo vệ endpoint `/encrypt` và `/decrypt`, khóa mã hóa và quyền đọc response. Mã hóa dữ liệu trong Git không thay thế authorization: Config Server có thể giải mã trước khi trả cấu hình cho client. Người gọi API vẫn phải được phép đọc application tương ứng.

## 9. Bảo vệ Actuator và các endpoint quản trị

Config Server API và Actuator có thể cùng chạy trên một web server. Spring Cloud Config cảnh báo rằng nếu Actuator không nằm trong classpath, một request `/actuator/...` có thể bị hiểu như request Config API `/{application}/{label}` và vô tình trả thông tin cấu hình.

Khi cần health check:

1. Thêm `spring-boot-starter-actuator` vào Config Server.
2. Expose đúng endpoint cần dùng, thường là `health` và có thể `info`.
3. Cấu hình rule riêng cho `/actuator/health`.
4. Không cấp quyền đọc Config API cho danh tính chỉ cần health check.
5. Bảo vệ các endpoint quản trị khác như `env`, `configprops`, `refresh`, `encrypt` và `decrypt` theo quyền riêng.

Ví dụ quy tắc:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/actuator/health").hasAuthority("SCOPE_config.health")
    .requestMatchers("/encrypt", "/decrypt").hasAuthority("SCOPE_config.crypto.admin")
    .requestMatchers("/actuator/**").hasAuthority("SCOPE_config.ops")
    .requestMatchers("/{application}/**").access(applicationAuthorizationManager)
    .anyRequest().denyAll()
)
```

Chỉ cho phép health công khai nếu đó là quyết định có chủ đích và endpoint không tiết lộ dữ liệu nhạy cảm. Quy tắc cụ thể phải được sắp xếp sao cho matcher quản trị không bị matcher rộng hơn bắt trước.

## 10. TLS, gateway và mạng nội bộ

Spring Cloud Config khuyến nghị dùng TLS cho Config Server để credential và giá trị cấu hình không truyền dưới dạng plaintext. Có thể cấu hình TLS trực tiếp bằng `server.ssl.*` hoặc kết thúc TLS tại reverse proxy/gateway có kiểm soát.

Một lớp bảo vệ nhiều tầng có thể gồm:

- **Network:** Config Server chỉ nhận kết nối từ subnet, workload hoặc gateway cần thiết.
- **Transport:** HTTPS/TLS; cân nhắc mTLS khi cần xác thực workload bằng chứng thư client.
- **Identity:** HTTP Basic riêng từng service hoặc OAuth2 JWT client credentials.
- **Authorization:** kiểm tra application/profile/label theo danh tính đã xác thực.
- **Backend:** Git/secret manager có credential read-only và phạm vi truy cập tối thiểu.
- **Audit:** log danh tính, application/profile/label, kết quả cho phép/từ chối và request ID; không log secret hoặc Authorization header.

API Gateway có thể thực hiện một phần xác thực và phân quyền, nhưng Config Server vẫn nên có chính sách bảo vệ riêng. Nếu gateway chuyển tiếp header danh tính, chỉ tin header được gateway ghi đè sau khi xác thực; không tin giá trị do client tự gửi trực tiếp.

## 11. Lỗ hổng theo phiên bản cho thấy vì sao selector phải được kiểm soát

Các advisory Spring năm 2026 ghi nhận một số lỗi liên quan đến việc client có thể điều khiển selector hoặc khai thác response Config Server. Đây là lý do cần nâng cấp đúng nhánh và kiểm tra cả request authorization lẫn phiên bản thư viện.

### CVE-2026-22739 — profile substitution, file access và SSRF

Khi Config Server dùng native filesystem backend, profile được thay thế từ request có thể cho phép truy cập file ngoài `search-locations`. Với source control backend, profile có thể bị chèn vào URL repository và dẫn đến SSRF.

| Nhánh | Phiên bản bị ảnh hưởng | Bản sửa được advisory nêu |
|---|---|---|
| 5.0.x | 5.0.0–5.0.1 | 5.0.2 (OSS) |
| 4.3.x | 4.3.0–4.3.1 | 4.3.2 (OSS) |
| 4.2.x | 4.2.0–4.2.5 | 4.2.6 (Enterprise Support Only) |
| 4.1.x | Các bản đến 4.1.8 | 4.1.9 (Enterprise Support Only) |
| 3.1.x | 3.1.12 và trước đó | 3.1.13 (Enterprise Support Only) |

### CVE-2026-40981 — Google Secret Manager cross-project access

Khi dùng Google Secret Manager làm backend, một client có thể tạo request để Config Server truy cập secret từ project GCP ngoài dự kiến. Dải bị ảnh hưởng gồm 5.0.0–5.0.2, 4.3.0–4.3.2, 4.2.0–4.2.6, 4.1.0–4.1.9 và 3.1.13 trở về trước. Bản sửa là 5.0.3 OSS, 4.3.3 OSS, 4.2.7, 4.1.10 và 3.1.14 (các bản enterprise support only ở nhánh cũ). Nếu chưa nâng cấp, advisory nêu tùy chọn `spring.cloud.config.server.gcp-secret-manager.token-mandatory=true` để bắt buộc client gửi token hợp lệ có quyền truy cập project được yêu cầu.

### CVE-2026-40982 — directory traversal

Request được tạo đặc biệt có thể khiến Config Server phục vụ file text hoặc binary ngoài phạm vi dự kiến. Dải bị ảnh hưởng gồm 5.0.0–5.0.2, 4.3.0–4.3.2, 4.2.0–4.2.6, 4.1.0–4.1.9 và 3.1.13 trở về trước. Bản sửa là 5.0.3 OSS, 4.3.3 OSS, 4.2.7, 4.1.10 và 3.1.14 (các bản enterprise support only ở nhánh cũ).

### CVE-2026-59435 — lộ credential trong PropertySource name

Advisory ngày 19-11-2026 cho biết Config Server đưa toàn bộ backend Git/SVN URI vào tên property source. Nếu URI chứa username/password trong phần userinfo, credential có thể xuất hiện dạng rõ trong response cấu hình.

| Nhánh | Phiên bản bị ảnh hưởng | Bản sửa được advisory nêu |
|---|---|---|
| 5.0.x | 5.0.0–5.0.6 | 5.0.7 (OSS) |
| 4.3.x | 4.3.0–4.3.5 | 4.3.6 (Enterprise Support Only) |
| 4.0.x–4.2.x | 4.0.0–4.2.9 | 4.2.10 (Enterprise Support Only) |
| 3.1.x | 3.1.0–3.1.15 | 3.1.16 (Enterprise Support Only) |

Trong khi nâng cấp, tránh nhúng credential vào Git URI. Dùng SSH key hoặc thuộc tính username/password riêng của Git backend. Nếu credential đã từng xuất hiện trong response, hãy rotate ngay cả khi đã nâng cấp.

Các bảng trên là thông tin theo advisory được dẫn, không thay thế việc kiểm tra release train và ma trận hỗ trợ hiện tại của dự án. Dùng Spring Cloud BOM tương thích với Spring Boot, kiểm tra dependency tree thực tế và ưu tiên bản vá mới nhất còn được hỗ trợ.

## 12. Kiểm thử authorization thay vì chỉ kiểm tra đăng nhập

Một bộ kiểm thử bảo mật cần xác minh cả trường hợp được phép và bị từ chối. Ví dụ với hai client `order-service` và `payment-service`:

| Danh tính token | Request | Kết quả mong đợi |
|---|---|---|
| `order-service` | `/order-service/prod/main` | Cho phép |
| `order-service` | `/payment-service/prod/main` | Từ chối `403` |
| `payment-service` | `/payment-service/prod/main` | Cho phép |
| `payment-service` | `/order-service/prod/main` | Từ chối `403` |
| Không có token | `/order-service/prod/main` | Từ chối `401` |
| Token hết hạn/sai issuer | `/order-service/prod/main` | Từ chối xác thực |
| `order-service` | `/order-service/prod/other-branch` | Theo allow-list label; từ chối nếu label không được cấp |
| `order-service` | `/order-service-prod.yml` | Từ chối nếu chỉ cho phép Environment endpoint; nếu hỗ trợ thì phải áp dụng cùng policy |
| Health checker | `/actuator/health` | Chỉ cho phép theo rule health đã định nghĩa |
| Health checker | `/payment-service/prod/main` | Từ chối |

Kiểm thử thêm các trường hợp:

- Application/profile/label rỗng, không tồn tại hoặc chứa ký tự không hợp lệ.
- Profile dạng danh sách và label dạng danh sách.
- URL có dấu gạch chéo mã hóa, dấu chấm hoặc biến thể encoding.
- Các endpoint YAML, properties, label-first và API file text/binary nếu được bật.
- Request đến `/encrypt`, `/decrypt`, `/actuator/env` và các endpoint quản trị.
- Cấu hình chung `application.yml` có chứa khóa nhạy cảm; bảo đảm không có secret dùng riêng cho dịch vụ khác.
- Client bị thu hồi credential hoặc scope và token cũ hết hạn.

Kiểm thử âm phải chứng minh client đã xác thực nhưng không có quyền nhận response cấu hình của application khác. Một test chỉ kiểm tra `401` khi thiếu password chưa kiểm tra được lỗi IDOR do thay `{application}`.

## 13. Các lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Cách sửa |
|---|---|---|
| Chỉ bật HTTP Basic rồi cho mọi user truy cập mọi route | Bất kỳ user biết tên application đều có thể đọc cấu hình của app khác | Phân quyền theo application và danh tính client |
| Dùng chung một username/password cho tất cả service | Không phân biệt được client và không thể thu hồi quyền riêng | Cấp credential hoặc token riêng từng workload |
| Tin `spring.application.name` do client gửi | Client tự đổi tên để yêu cầu tài nguyên khác | So sánh selector với principal/claim đã xác thực |
| Dùng profile `prod` hoặc label `secret` để ẩn cấu hình | Client có thể tự yêu cầu profile/label khác | Authorization policy kiểm tra cả application/profile/label |
| Chỉ bảo vệ `/{application}/**` nhưng mở endpoint `.yml` | Có thể đi vòng qua route matcher | Bảo vệ mọi endpoint hoặc deny route không dùng |
| Đặt secret riêng dịch vụ trong `application.yml` | Mọi application kế thừa có thể nhận secret đó | Chuyển secret về backend riêng hoặc tách trust zone |
| Dùng một composite server cho nhiều vùng bí mật | Application response có thể tổng hợp nguồn ngoài dự kiến | Tách Config Server/backend theo ranh giới bảo mật |
| Chỉ dựa vào gateway hoặc mạng private | Một client nội bộ bị xâm nhập có thể đọc cấu hình khác | Defense-in-depth: TLS, identity, authorization và network policy |
| Nhúng password vào Git URI | Có thể lộ trong property source name, log hoặc response | SSH key hoặc credential field riêng; nâng cấp bản vá |

## 14. Checklist thiết kế phân quyền

| Hạng mục | Điều kiện đạt |
|---|---|
| Client identity | Mỗi workload có danh tính riêng, có thể thu hồi và rotate |
| Authentication | Config Server kiểm tra chữ ký/token, password hoặc client certificate |
| Audience/issuer | JWT đúng issuer, audience và thời hạn cho Config Server |
| Application policy | Danh tính được ánh xạ tới danh sách application được phép |
| Profile policy | Profile được kiểm tra theo môi trường và nhiệm vụ |
| Label policy | Branch/tag/commit nằm trong allow-list phù hợp |
| Endpoint coverage | JSON, YAML, properties, label-first, encrypt/decrypt và file endpoints đều có rule |
| Shared config | `application.yml` chỉ chứa giá trị dùng chung, không có secret riêng service |
| Composite backend | Không dùng composite như ranh giới phân quyền giữa repository |
| Backend credential | Config Server có quyền read-only tối thiểu; không nhúng credential vào URI |
| Actuator | Health và endpoint quản trị có rule riêng, không cấp Config API cho health checker |
| Transport/network | HTTPS hoặc mTLS, private routing, gateway/network policy |
| Audit | Ghi principal, resource selectors, decision và request ID; không log secret |
| Version | Config Server/monitor/backend connector dùng bản đã vá và BOM tương thích |
| Negative tests | Client A không thể đọc application/profile/label của client B |

## 15. Nguyên tắc cần ghi nhớ

- `application`, `profile` và `label` chỉ chọn tài nguyên; chúng không xác thực danh tính hoặc cấp quyền.
- Theo mặc định, bất kỳ người dùng đã xác thực nào cũng có thể yêu cầu cấu hình của bất kỳ application nào nếu chưa có policy riêng.
- Xác thực bằng HTTP Basic, OAuth2/JWT hoặc mTLS phải đi cùng authorization theo application và khi cần theo profile/label.
- Không tin `spring.application.name` hoặc header do client tự gửi làm danh tính.
- Bảo vệ mọi dạng endpoint Config Server; không để URL `.yml`/`.properties` bỏ qua matcher của Environment API.
- `application.yml` là cấu hình nền được nhiều application kế thừa; không đặt secret riêng dịch vụ trong đó.
- Composite repository không tạo ra ranh giới bảo mật giữa các backend.
- Credential Git là credential của Config Server; giữ quyền read-only và không nhúng userinfo vào URI.
- Bảo vệ riêng `/actuator/**`, `/encrypt` và `/decrypt`; health checker không cần quyền đọc cấu hình.
- Dùng TLS, network policy, audit và kiểm thử âm để xác minh client này không đọc được cấu hình của client khác.
- Theo dõi advisory và nâng cấp Config Server/backend connector lên phiên bản đã vá.

Application, profile và label giúp Config Server chọn đúng dữ liệu, nhưng quyền đọc dữ liệu phải xuất phát từ danh tính đã được xác thực và chính sách được kiểm tra ở mỗi request. Khi kết hợp identity riêng cho từng workload, authorization bao phủ mọi endpoint, backend credential tối thiểu, bảo vệ Actuator và kiểm thử âm, Config Server mới có thể phân phối cấu hình tập trung mà vẫn giữ được ranh giới bí mật giữa các ứng dụng.

## Tài liệu tham khảo

- [Spring Cloud Config 5.1 — Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html)
- [Spring Cloud Config — Actuator and Security](https://docs.spring.io/spring-cloud-config/reference/server/actuator-and-security.html)
- [Spring Cloud Config Client — URL selectors and OAuth2 client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Security Advisory CVE-2026-22739 — Profile substitution, file access and SSRF](https://spring.io/security/cve-2026-22739/)
- [Spring Security Advisory CVE-2026-40981 — Google Secret Manager cross-project access](https://spring.io/security/cve-2026-40981/)
- [Spring Security Advisory CVE-2026-40982 — Directory traversal](https://spring.io/security/cve-2026-40982/)
- [Spring Security Advisory CVE-2026-59435 — Backend Git/SVN credentials in property source names](https://spring.io/security/cve-2026-59435/)
