# Đưa cấu hình theo môi trường ra properties và cấu hình kiểu an toàn trong Spring Security WebFlux

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Tách **quy tắc bảo mật**, **cấu hình thay đổi theo môi trường** và **bí mật** thành các lớp có trách nhiệm rõ ràng.
- Dùng `application.yml`, `application-dev.yml`, `application-prod.yml` và biến môi trường để cấu hình Spring Boot mà không sửa mã Java mỗi lần triển khai.
- Bind nhóm security settings thành Java `record` bằng `@ConfigurationProperties`, kiểm tra giá trị với `@Validated` và Jakarta Bean Validation để **fail fast** khi giá trị bị thiếu hoặc sai.
- Sử dụng dữ liệu đã kiểm tra để cấu hình `SecurityWebFilterChain`, HTTP Basic, HTTPS, CORS và các route được phép công khai trong Spring WebFlux.
- Giữ mặc định bảo vệ, quản lý password hash qua secret nguồn ngoài, kiểm chứng 200/401/403 bằng test, và nhận ra những lỗi cấu hình nguy hiểm.

> Phạm vi: Spring Boot 3.x, Java 17+, **Spring Security reactive với WebFlux**. API bảo mật của bài là `ServerHttpSecurity` và `SecurityWebFilterChain`; `HttpSecurity` và `SecurityFilterChain` thuộc luồng Servlet/MVC khác.

## 1. Vì sao phải externalize cấu hình bảo mật?

Ứng dụng có thể chạy ở local dev, test, staging và production. Từng môi trường khác nhau về domain, origin frontend, cổng HTTPS, secret storage và khả năng truy cập các endpoint thử nghiệm. Hardcode các giá trị này vào code khiến cùng một phiên bản ứng dụng phải biên dịch lại hoặc dễ bị cấu hình dev vô tình chạy trên production.

Hãy phân biệt:

| Loại | Ví dụ | Nguồn phù hợp |
| --- | --- | --- |
| **Chính sách nền tảng** | `/admin/**` luôn yêu cầu vai trò ADMIN; route còn lại cần đăng nhập | Code/cấu hình được review và test như security policy |
| **Tham số môi trường** | Domain CORS được phép, bật HTTPS redirect, công khai endpoint tài liệu thử nghiệm hay không | `application-{profile}.yml`, cấu hình deployment |
| **Bí mật** | Mật khẩu, password hash, private key, OAuth client secret, signing key | Secret manager, config tree, hoặc environment được bảo vệ |
| **Quyền theo người dùng** | Ai có quyền xem một báo cáo cụ thể | Identity provider/DB/service authorization, không đặt hàng loạt trong YAML |

Password hash không phải plaintext nhưng vẫn cần bảo vệ: hash bị lộ tạo điều kiện cho tấn công đoán password ngoại tuyến. Không commit giá trị bí mật thật vào Git, không in đối tượng cấu hình chứa hash ra log.

### Cấu hình typed và "an toàn" là hai mục tiêu liên quan

**Type safety** giúp nhận dạng lỗi như gán chữ `maybe` cho boolean hay thiếu tên người dùng. **Security safety** giúp tránh mặc định thành `permitAll()` khi một giá trị không có. Cả hai cần thiết: một boolean kiểu đúng như `allow-all=true` vẫn có thể là một quyết định bảo mật cực kỳ nguy hiểm.

Cách nên tránh:

```java
// Minh họa anti-pattern, không dùng trong ứng dụng thật:
String env = System.getenv("APP_ENV");
if ("dev".equals(env)) {
    http.authorizeExchange(a -> a.anyExchange().permitAll());
}
```

Nếu môi trường production bị đặt nhầm `APP_ENV=dev`, toàn bộ endpoint sẽ bị mở. Cách tốt hơn là cấu hình chính xác **route nào** được công khai, với rule cuối bảo vệ mọi request còn lại.

## 2. Profile và thứ tự nguồn cấu hình Spring Boot

Spring Boot hỗ trợ các nguồn cấu hình từ file YAML/properties, file profile, biến môi trường, system properties, command-line arguments và vị trí ngoài JAR. Những nguồn có độ ưu tiên cao hơn có thể ghi đè nguồn trước đó; file profile trong cùng nhóm thường ghi đè file base.

Thư mục ví dụ:

```text
src/main/resources/
    application.yml
    application-dev.yml
    application-prod.yml
```

- `application.yml` chứa giá trị chung và mặc định phòng thủ.
- `application-dev.yml` chỉ khác ở những gì cần cho local, chẳng hạn origin `http://localhost:5173` và không redirect HTTP localhost sang HTTPS.
- `application-prod.yml` ghi rõ HTTPS và origin frontend production; không chứa password/key thật.
- `SPRING_PROFILES_ACTIVE=dev` hoặc `--spring.profiles.active=dev` kích hoạt profile dev. Không tự dùng profile dev để triển khai production.
- Biến môi trường hoặc tham số chạy có thể override file. Phải kiểm tra **giá trị hiệu lực** trong môi trường triển khai, không nghĩ rằng chỉ cần có `application-prod.yml` là bảo đảm an toàn.

Spring Boot sử dụng *relaxed binding*: key YAML `app.security.require-https` bind vào Java `requireHttps`. Khi override trực tiếp property bằng biến môi trường theo quy tắc của Boot, tên là `APP_SECURITY_REQUIREHTTPS`: đổi dấu chấm thành gạch dưới, bỏ dấu gạch ngang, viết hoa. Tên biến dùng trong placeholder như `APP_ADMIN_PASSWORD_HASH` dưới đây là tên **do mình tự chọn**, không cần khớp quy tắc relaxed binding vì được đọc qua placeholder.

### Cẩn thận với danh sách

Trong cấu hình multi-profile, `List` thông thường được **thay thế** bởi danh sách từ nguồn có ưu tiên cao hơn, không tự hợp nhất từng origin. Ví dụ, danh sách localhost của dev sẽ không tự cộng thêm origin production; đây là behavior hữu ích để tránh vô tình mở rộng phạm vi CORS. Kiểm thử origin thật khi deploy.

## 3. Thiết kế typed security settings với record

Ví dụ đầy đủ sử dụng Java 17+, Spring Boot 3.x, Spring WebFlux và Spring Security. Có thêm starter validation để các annotation constraint thực sự được áp dụng.

**`build.gradle`** — dependencies trong dự án Gradle đã có Spring Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Không thêm `spring-boot-starter-web` cho demo WebFlux vì khi cả MVC và WebFlux cùng hiện diện, Spring Boot thường chọn ứng dụng Servlet nếu không ép loại ứng dụng.

**`src/main/java/example/secureconfig/SecuritySettings.java`**:

```java
package example.secureconfig;

import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.security")
public record SecuritySettings(
        @NotNull Boolean requireHttps,
        @NotNull Boolean publicDocs,
        @NotBlank String adminUsername,
        @NotBlank
        @Pattern(
            regexp = "\\{bcrypt\\}.+",
            message = "must use an encoded {bcrypt} password"
        )
        String adminPasswordHash,
        @NotNull List<@NotBlank String> corsAllowedOrigins
) {}
```

Ý nghĩa cụ thể:

1. `@ConfigurationProperties` bind các key trong nhóm `app.security.*` vào một object, tránh rải hàng loạt `@Value` với tên key/string magic trong security config.
2. `record` phù hợp với cấu hình được bind qua constructor và không có setter. Với record chỉ có một constructor, Spring Boot 3.x không đòi `@ConstructorBinding`. Kết quả phản ánh **cấu hình lúc bean được tạo**, không tự reload khi bạn sửa một biến môi trường.
3. `Boolean` wrapper kết hợp `@NotNull` phát hiện key bắt buộc bị thiếu; dùng primitive `boolean` có thể biến thiếu value thành `false` không có chủ đích.
4. `@NotBlank` và `@Pattern` chặn hash rỗng hoặc plaintext thiếu tiền tố `{bcrypt}`. Regex chỉ kiểm tra **dạng**; không chứng minh toàn bộ hash có thể xác minh được hoặc password đủ mạnh.
5. `@NotNull List<@NotBlank String>` yêu cầu phải có một danh sách; danh sách rỗng `[]` hợp lệ để **không cho phép origin cross-site nào**. Các phần tử trong danh sách không được blank.
6. `@Validated` sử dụng Bean Validation (nhờ starter validation). Khi dữ liệu không hợp lệ, ứng dụng thất bại lúc khởi động thay vì âm thầm chọn cấu hình rủi ro.

Không biến property record thành bean `@Component` rồi mong constructor binding chạy như `@ConfigurationProperties`. Bài này đăng ký đúng qua `@EnableConfigurationProperties` trong lớp SecurityConfiguration.

### Vì sao không cần khai báo default cho mọi trường?

Hai cờ có default an toàn ở `application.yml`. Trái lại, username và hash không có default vì *thiếu secret là lỗi triển khai*. Không dùng cú pháp `${APP_ADMIN_PASSWORD_HASH:password}` hay `{noop}123456` để "cho ứng dụng chạy được". Nếu environment không cung cấp credential hợp lệ, khởi động phải dừng.

## 4. Khai báo file cấu hình theo môi trường

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: reactive-secure-config

app:
  security:
    require-https: true
    public-docs: false
    admin-username: ${APP_ADMIN_USERNAME}
    admin-password-hash: ${APP_ADMIN_PASSWORD_HASH}
    cors-allowed-origins: []
```

Giải thích:

- `require-https: true`: mặc định bật chuyển hướng sang HTTPS.
- `public-docs: false`: mặc định không công khai tài liệu demo.
- `admin-username` và `admin-password-hash` phải lấy từ môi trường runtime hoặc một secret source cung cấp đúng key.
- `cors-allowed-origins: []`: không mở CORS tùy tiện.

**`src/main/resources/application-dev.yml`**:

```yaml
app:
  security:
    require-https: false
    public-docs: true
    cors-allowed-origins:
      - "http://localhost:5173"
```

**`src/main/resources/application-prod.yml`**:

```yaml
app:
  security:
    require-https: true
    public-docs: false
    cors-allowed-origins:
      - "https://console.example.com"
```

`https://console.example.com` là hostname **minh họa**: thay bằng origin chính xác đã được phê duyệt của frontend thật. Sự khác biệt có chủ đích giữa dev và prod là khả năng truy cập docs, CORS allowlist và TLS redirect, không phải toàn bộ chính sách authentication/authorization.

Lưu ý file dev đi kèm artifact JAR vẫn có thể được kích hoạt nếu người vận hành đặt sai profile. Phải có kiểm soát deploy và test ngăn profile dev chạy trên môi trường sản xuất; profile chỉ là cơ chế cấu hình, không phải security boundary bất khả xâm phạm.

## 5. Áp dụng settings vào Spring Security WebFlux

Đoạn code dưới đây kết hợp đăng ký record, nguồn xác thực, password encoder, CORS và `SecurityWebFilterChain`. HTTP Basic chỉ được dùng để demo cách nối cấu hình; hệ thống thật có thể chọn OIDC/OAuth2 resource server tùy mô hình xác thực.

**`src/main/java/example/secureconfig/SecureConfigApplication.java`**:

```java
package example.secureconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureConfigApplication.class, args);
    }
}
```

**`src/main/java/example/secureconfig/ReactiveSecurityConfiguration.java`**:

```java
package example.secureconfig;

import java.util.List;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableConfigurationProperties(SecuritySettings.class)
class ReactiveSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(SecuritySettings settings) {
        UserDetails admin = User.withUsername(settings.adminUsername())
                .password(settings.adminPasswordHash())
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(SecuritySettings settings) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(settings.corsAllowedOrigins());
        cors.setAllowedMethods(List.of("GET", "HEAD", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);

        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            SecuritySettings settings,
            ReactiveAuthenticationManager authManager,
            CorsConfigurationSource corsSource) {

        http
            .authorizeExchange(exchanges -> {
                exchanges.pathMatchers(HttpMethod.GET, "/public/ping")
                        .permitAll();

                if (settings.publicDocs()) {
                    exchanges.pathMatchers(HttpMethod.GET, "/docs/info")
                            .permitAll();
                } else {
                    exchanges.pathMatchers("/docs/**")
                            .denyAll();
                }

                exchanges.pathMatchers("/admin/**")
                        .hasRole("ADMIN");
                exchanges.anyExchange().authenticated();
            })
            .httpBasic(basic -> basic.authenticationManager(authManager))
            .formLogin(form -> form.disable())
            .cors(cors -> cors.configurationSource(corsSource));

        if (settings.requireHttps()) {
            http.redirectToHttps(Customizer.withDefaults());
        }

        return http.build();
    }
}
```

**`src/main/java/example/secureconfig/DemoController.java`**:

```java
package example.secureconfig;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {
    @GetMapping("/public/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/docs/info")
    Mono<String> docs() {
        return Mono.just("demo docs");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/admin/report")
    Mono<String> report() {
        return Mono.just("admin report");
    }
}
```

### Tại sao code này áp dụng cấu hình kiểu an toàn?

- `@EnableConfigurationProperties(SecuritySettings.class)` cho Spring Boot tạo bean thông qua Binder, rồi validate; mọi bean khác nhận **một object cấu hình có kiểu**.
- Credential trong `MapReactiveUserDetailsService` là một user minh họa, với **password hash** từ nguồn bí mật. `UserDetailsRepositoryReactiveAuthenticationManager` nhận `PasswordEncoder` và được gắn rõ vào HTTP Basic để kiểm chứng password.
- `pathMatchers(GET, "/public/ping").permitAll()` công khai chính xác một route. `/docs/info` chỉ mở anonymous khi `publicDocs=true`; khi cờ false, `/docs/**` bị `denyAll()`. `/admin/**` luôn yêu cầu role ADMIN và mọi request còn lại cần authentication.
- `roles("ADMIN")` tạo authority `ROLE_ADMIN`. `hasRole("ADMIN")` tự thêm tiền tố `ROLE_`, nên không viết `hasRole("ROLE_ADMIN")`.
- CORS được cấu hình qua `CorsConfigurationSource` loại **reactive**. Nó xử lý browser origin/preflight; nó không thay thế authentication, authorization hoặc CSRF.
- `formLogin` tắt vì demo này không có UI form login/cookie session; `httpBasic` bật rõ ràng. Ví dụ không tắt CSRF mặc định (controller chỉ có các `GET`). Với POST/PUT/DELETE hoặc browser dùng cookie, phải đánh giá CSRF theo threat model thực tế.
- `redirectToHttps` chỉ bật theo cờ đã bind. Truyền HTTP Basic qua kết nối public không TLS sẽ lộ mật khẩu; cấu hình production cần TLS thực từ client đến điểm chấm dứt tin cậy.
- Controller dùng `ReactiveSecurityContextHolder` để đọc danh tính trong Reactor Context, tránh API thread-local kiểu Servlet.

**Cẩn thận về quyền:** `permitAll()` cho route công khai không có nghĩa security filter, CORS hay các biện pháp phòng vệ khác bị bỏ qua. `anyExchange().authenticated()` cũng chưa đủ để bảo vệ tài nguyên theo từng chủ sở hữu; service/repository vẫn cần phân quyền đối tượng khi dữ liệu nhạy cảm.

## 6. Bí mật và password hash phải được cấp phát ngoài mã nguồn

Hai placeholder trong file base nhận:

- `APP_ADMIN_USERNAME`: tài khoản demo.
- `APP_ADMIN_PASSWORD_HASH`: một hash BCrypt với prefix `{bcrypt}` mà `DelegatingPasswordEncoder` hiểu được, ví dụ cấu trúc `{bcrypt}$2a$...` (dấu ba chấm không phải hash hợp lệ).

**Không** ghi một hash mật khẩu thật vào repository/tài liệu công khai. Dùng secret manager, config tree, hoặc môi trường process được kiểm soát quyền truy cập. Tuyệt đối không dùng `{noop}` để lưu password production.

Để tạo hash trong tiện ích nội bộ Java đã có Spring Security trên classpath, thao tác cốt lõi là:

```java
String encoded = "{bcrypt}" +
        new BCryptPasswordEncoder().encode(passwordFromProtectedInput);
```

Đây là **mã minh họa**, giả định biến `passwordFromProtectedInput` được nhận từ một cơ chế nhập bảo vệ và đã import `BCryptPasswordEncoder`. Mã này không độc lập, không có `main()`, và không nên in raw password. Cách provisioning phải tuân theo quy định quản lý secret của tổ chức.

Trong môi trường container, Spring Boot còn hỗ trợ import cấu hình từ secret mount:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Cần mount đúng tên file/key cấu hình, bảo vệ quyền đọc và quản lý rotation. `optional:configtree:...` cho phép đường dẫn vắng mặt nhưng không phải lựa chọn hợp lý nếu thiếu secret bắt buộc phải dừng deploy. Biến môi trường cũng có thể lộ qua công cụ xem process, debug log hoặc crash dump; chúng không tự động được xem là secret manager.

**Không log object `SecuritySettings`.** `record.toString()` mặc định hiển thị mọi component, bao gồm `adminPasswordHash`. Actuator `/env` và `/configprops` cũng cần được bảo vệ, kiểm soát sanitization và không công khai.

## 7. Chạy thử với profile và kiểm tra endpoint

Trong dự án có Gradle Wrapper, sau khi provision username/password hash đúng vào process sẽ chạy app, chọn profile dev:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Trong production, chọn `prod` từ manifest/môi trường triển khai, không dùng `dev` để giải quyết lỗi chứng chỉ hoặc redirect. Khi chạy JAR đã build:

```bash
java -jar build/libs/your-app.jar --spring.profiles.active=prod
```

`your-app.jar` là tên minh họa; thay bằng tên output thật của Gradle. Đảm bảo biến môi trường có trong **process Java**, không chỉ ở terminal khác.

Thử từ terminal riêng:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/docs/info
curl -i http://localhost:8080/admin/report
curl -i -u ADMIN_USER http://localhost:8080/me
curl -i -u ADMIN_USER http://localhost:8080/admin/report
```

Thay `ADMIN_USER` bằng tài khoản demo đã provision. Với `curl -u username` không kèm password, curl có thể hỏi password trong terminal. Tránh đặt mật khẩu trực tiếp trên dòng lệnh vì có thể bị ghi vào lịch sử hoặc process list.

| Request khi chạy dev | Kết quả dự kiến | Giải thích |
| --- | --- | --- |
| `GET /public/ping` anonymous | 200, body `pong` | Explicit `permitAll` |
| `GET /docs/info` anonymous | 200, body `demo docs` | Dev đặt `public-docs=true` |
| `GET /admin/report` anonymous | 401, Basic challenge | Thiếu authentication |
| `GET /me` với credential hợp lệ | 200, `hello <username>` | Principal đọc từ reactive security context |
| `GET /admin/report` với admin hợp lệ | 200, body `admin report` | Có `ROLE_ADMIN` |

Trong profile prod, nếu request đã đi qua HTTPS hợp lệ, `/docs/info` bị deny. Với người đã authenticated, deny thường dẫn đến **403**; người anonymous có thể nhận **401** khi security entry point yêu cầu đăng nhập. Vì vậy không khẳng định mọi deny đều cho 403 với mọi client.

### HTTPS và reverse proxy

Nếu TLS kết thúc ở reverse proxy/load balancer rồi proxy gửi HTTP đến WebFlux, framework có thể cần cấu hình trusted forwarded headers để biết client ban đầu dùng HTTPS. Nếu sai có thể phát sinh redirect loop hoặc tạo URL sai. Kiểm tra `server.forward-headers-strategy` tùy hạ tầng, thiết lập trust boundary rõ ràng và bảo đảm proxy loại bỏ `Forwarded`/`X-Forwarded-*` do client ngoài giả mạo. Không giải quyết bằng cách tắt HTTPS để che sự cố hạ tầng.

### CORS khác authentication

Danh sách origin CORS là chính sách cho **trình duyệt**. Không có nghĩa một client backend hoặc `curl` từ origin khác sẽ tự bị ngăn kết nối. Một request cross-origin có header `Authorization` thường phát sinh preflight; hãy thử preflight đúng method/header/origin trên frontend. Khi dùng cookie/session cross-origin, phải cấu hình credentials, SameSite và CSRF nhất quán, không mở wildcard bừa bãi.

## 8. Tự động kiểm thử với WebTestClient

Đoạn test dưới đây cấp một hash BCrypt cho tài khoản **chỉ trong test**, không cần secret production. Nó ép HTTPS redirect tắt trong test HTTP local và bật trạng thái docs false để kiểm chứng fail-closed.

**`src/test/java/example/secureconfig/SecurityHttpTest.java`**:

```java
package example.secureconfig;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "app.security.require-https=false",
        "app.security.public-docs=false"
    }
)
@AutoConfigureWebTestClient
class SecurityHttpTest {

    @Autowired WebTestClient client;

    @DynamicPropertySource
    static void credentials(DynamicPropertyRegistry registry) {
        registry.add("app.security.admin-username", () -> "admin");
        registry.add(
            "app.security.admin-password-hash",
            () -> "{bcrypt}" + new BCryptPasswordEncoder(4)
                    .encode("test-only-password")
        );
    }

    @Test
    void publicRouteWorksWithoutLogin() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotAccessAdmin() {
        client.get().uri("/admin/report").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void adminCanAccessAdminReport() {
        client.get().uri("/admin/report")
                .headers(h -> h.setBasicAuth("admin", "test-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin report");
    }

    @Test
    void authenticatedAdminStillCannotReadDisabledDocs() {
        client.get().uri("/docs/info")
                .headers(h -> h.setBasicAuth("admin", "test-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Lệnh:

```bash
./gradlew test --tests example.secureconfig.SecurityHttpTest
```

Trên PowerShell: `.\gradlew.bat test --tests example.secureconfig.SecurityHttpTest`. Với code và môi trường đúng, bốn case dự kiến PASS. Đây là **test bảo mật HTTP**, chưa chứng minh đã deploy đúng TLS/proxy, không có lỗi CORS, hoặc secret production được rotation chính xác. Cần bổ sung bài test/kiểm tra riêng cho các điều kiện đó.

### Negative tests cho typed configuration

Các trường hợp dưới đây nên chạy dưới test context cô lập hoặc quy trình startup validation; không cố tình gây lỗi trong production:

| Thay đổi thử | Mong đợi | Phát hiện bởi |
| --- | --- | --- |
| Không cấp `APP_ADMIN_PASSWORD_HASH` và không override tương đương | App không khởi động được | Placeholder/binding/validation |
| `app.security.require-https=maybe` | App không khởi động | Không thể convert thành Boolean |
| `app.security.admin-username=""` | App không khởi động | `@NotBlank` |
| `app.security.admin-password-hash=plaintext` | App không khởi động | `@Pattern` |
| `app.security.cors-allowed-origins[0]=""` | Validation không đạt | `List<@NotBlank String>` |
| `app.security.public-docs=false` | Authenticated admin bị từ chối ở `/docs/info` | Rule `denyAll` |
| `app.security.require-https=true`, request HTTP hợp lệ | Chuyển sang HTTPS | HTTPS redirect trong chain |

Giá trị type-safe chỉ xác nhận cấu hình có hình dạng hợp lệ. Nó không đảm bảo origin đáng tin hay role được gán đúng; phải có review và test policy riêng. Không bật debug log làm lộ hash/token chỉ để quan sát binding.

## 9. Sai lầm phổ biến và cách sửa

| Sai lầm | Tác hại | Cách xử lý |
| --- | --- | --- |
| Dùng nhiều `@Value` rời rạc, string-compare cờ security | Khó kiểm kê và kiểm tra tính nhất quán | Gom nhóm với `@ConfigurationProperties` |
| Dùng primitive `boolean` không có default được review | Thiếu value âm thầm thành false | `Boolean @NotNull` hoặc safe default được test |
| Dùng `security.enabled=false` / `allow-all=true` | Rủi ro mở mọi route khi bật nhầm | Rule chính xác, `anyExchange().authenticated()` |
| Commit mật khẩu, hash thực hoặc secret trong YAML | Lộ qua Git history/artifact | Chỉ giữ placeholder và provision từ secret store |
| Có fallback `${PASSWORD:password}` | Mất secret thì app vẫn chạy yếu | Bỏ fallback yếu, fail fast |
| Gắn profile dev ở production | Có thể tắt TLS và mở docs | Kiểm soát profile ở CI/CD và deployment |
| Dùng `@Component` cho constructor-bound record | Binder có thể không tạo đúng kiểu bean | `@EnableConfigurationProperties` |
| Thiếu validation provider | Không đảm bảo constraint được thực thi | Thêm starter validation, test startup fail |
| Tưởng danh sách cấu hình các profile tự merge | Origin có thể khác dự kiến | Kiểm tra list replacement và allowlist hiệu lực |
| Dùng CORS thay authorization | Client ngoài browser vẫn gọi được API | Kiểm tra authentication/authorization độc lập |
| Tắt CSRF khi ứng dụng có cookie/session | Tăng nguy cơ cross-site request forgery | Quyết định CSRF dựa trên loại client/credential |
| Tin `X-Forwarded-Proto` không kiểm soát | Bị giả mạo scheme, redirect sai | Chỉ trust proxy được quản lý |
| Log `SecuritySettings.toString()` | Có thể để lộ password hash | Mask/redact; không log secrets |
| Cho rằng chỉnh env sẽ tự đổi bean đang chạy | Chính sách không cập nhật như kỳ vọng | Thiết kế reload/restart/rotation có kiểm chứng |

## 10. Bài tập vận dụng

1. Tạo profile `staging` với origin frontend riêng, vẫn bật HTTPS và tắt docs. Kiểm tra effective config và CORS preflight.
2. Thử xóa password hash khỏi môi trường rồi chạy app, so sánh lỗi placeholder với lỗi validation khi hash thiếu prefix.
3. Thêm property `security.audit-enabled` (thuộc nhóm `app.security`) để bật ghi audit không nhạy cảm, dùng typed binding; giải thích vì sao không nên log header Authorization.
4. Viết hai integration tests cho `public-docs=true/false`; chứng minh chỉ `/docs/info` đổi trạng thái và `/admin/report` luôn cần role ADMIN.
5. Đặt app phía sau reverse proxy dùng TLS, test scheme của request, redirect và forwarded header trust. Đảm bảo client không thể giả mạo header để bỏ qua chính sách.
6. Thay user local bằng resource server JWT hoặc OIDC: giữ ý tưởng externalize issuer/JWKS/audience và secret có validation, nhưng chỉ dùng cơ chế authentication được Spring Security hỗ trợ tương ứng.

**Kết luận:** Externalize giá trị thay đổi theo môi trường, bind chúng vào cấu hình **có kiểu và được validate**, giữ bí mật ngoài code, đồng thời duy trì chính sách WebFlux bảo vệ mọi endpoint không được công khai rõ ràng. Kết hợp fail-fast configuration, kiểm tra quyền bằng HTTP tests và xác minh deployment mới tạo ra cấu hình bảo mật đáng tin cậy.

## Tham khảo chính thức

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Configuration Properties Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — WebFlux CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html)
- [Spring Security — Reactive HTTP/HTTPS](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
