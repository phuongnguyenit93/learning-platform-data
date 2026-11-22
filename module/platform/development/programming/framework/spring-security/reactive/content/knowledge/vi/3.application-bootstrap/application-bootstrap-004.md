# Cấu hình bảo mật mặc định của Spring Boot và tài khoản phát triển được sinh tự động

> **Phạm vi:** Spring Boot 3.3.x, Spring WebFlux, Spring Security 6.x, Java 17+. Bài học giải thích điều gì xảy ra **khi mới thêm Spring Security vào một ứng dụng WebFlux**, cách dùng tài khoản tạm để phát triển, cách nhận biết auto-configuration đang hoạt động, và thời điểm phải thay cấu hình mặc định.

## 1. Vì sao vừa thêm dependency thì API đã yêu cầu đăng nhập?

Một ứng dụng Spring Boot WebFlux thuần có thể trả lời request mà không cần xác thực. Khi bổ sung `spring-boot-starter-security`, Spring Boot phát hiện Spring Security trên classpath và tự cấu hình các thành phần bảo mật nếu ứng dụng chưa cung cấp cấu hình thay thế.

Với một ứng dụng WebFlux tối thiểu, kết quả điển hình:

- Các đường dẫn HTTP cần **người dùng đã xác thực**; điều này áp dụng cả đường dẫn API do mình viết, không chỉ trang đăng nhập.
- Có sẵn **HTTP Basic** cho client/API và **form login** cho trình duyệt; cách phản hồi khi chưa đăng nhập có thể phụ thuộc `Accept`/content negotiation.
- Có trang đăng nhập/đăng xuất mặc định, các HTTP security headers và bảo vệ CSRF theo cấu hình Spring Security.
- Spring Boot tạo **một tài khoản trong bộ nhớ** để có thể kiểm tra ngay khi phát triển: tên mặc định `user`, mật khẩu được sinh ngẫu nhiên lúc khởi động.
- Ứng dụng WebFlux sử dụng cơ chế reactive, bao gồm `SecurityWebFilterChain` và `ReactiveUserDetailsService`. Đừng nhầm với `SecurityFilterChain` và `UserDetailsService` kiểu Servlet.

Mục đích của mặc định là không vô tình phơi bày endpoint khi lập trình viên vừa thêm thư viện bảo mật. Đó mới là điểm khởi đầu, **không phải chính sách phân quyền hoàn chỉnh** cho sản phẩm.

### Trường hợp nào kích hoạt?

Điều kiện thực tế phải có **ứng dụng WebFlux và dependency bảo mật**. Một ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Chỉ thêm starter WebFlux không tự tạo tài khoản Spring Security. Chỉ tự thêm thư viện client OAuth2/Resource Server có thể làm các điều kiện auto-configuration nguồn người dùng thay đổi; cần kiểm tra lại loại xác thực thực sự được cấu hình.

## 2. Hai phần auto-configuration độc lập cần hiểu

Trong Spring Boot 3.3, hai nhánh thường được nhắc đến là:

1. **`ReactiveSecurityAutoConfiguration`:** tích hợp bảo mật ở tầng WebFlux, tạo cơ sở để Spring Security đưa các `WebFilter` vào chuỗi xử lý request. Nếu không có cấu hình bảo mật riêng, quy tắc mặc định yêu cầu xác thực.
2. **`ReactiveUserDetailsServiceAutoConfiguration`:** cung cấp kho người dùng reactive trong bộ nhớ (`ReactiveUserDetailsService`) khi chưa có hạ tầng xác thực phù hợp do ứng dụng cung cấp. Đây là nơi xuất hiện tài khoản phát triển và mật khẩu sinh ngẫu nhiên.

Có thể hình dung:

```text
GET /api/message
       |
       v
WebFlux / ServerWebExchange
       |
       v
SecurityWebFilterChain
       |-- Kiểm tra request có được truy cập chưa?
       |-- Chọn form login / HTTP Basic khi phù hợp
       |-- Xác thực username/password
       |           |
       |           +--> ReactiveUserDetailsService
       |                    +--> user (mật khẩu sinh lúc startup)
       v
Controller -> Mono/Flux -> HTTP response
```

**Tách riêng hai câu hỏi:**

- *Endpoint nào được vào?* — do `SecurityWebFilterChain`/`ServerHttpSecurity`, matcher và các quy tắc authorization quyết định.
- *Người dùng được tìm và xác thực như thế nào?* — do `ReactiveUserDetailsService`, `ReactiveAuthenticationManager` và cơ chế xác thực tương ứng quyết định.

Thay rule đường dẫn không đồng nghĩa đã thay kho người dùng; thay kho người dùng cũng không tự mở công khai endpoint.

### Các tình huống thay đổi cấu hình

| Bạn cấu hình thêm | Hành vi thường mong đợi |
|---|---|
| Không cấu hình bean bảo mật riêng, có `starter-security` | WebFlux được bảo vệ mặc định, có tài khoản phát triển tự sinh |
| Tạo `SecurityWebFilterChain` riêng | Quy tắc HTTP của ứng dụng thay cấu hình web mặc định; tài khoản tự sinh **có thể vẫn tồn tại** nếu chưa thay thành phần xác thực |
| Tạo `ReactiveUserDetailsService` riêng | Ứng dụng dùng nguồn người dùng bạn cung cấp; mặc định không tạo thêm tài khoản phát triển ở nhánh đó |
| Tạo `ReactiveAuthenticationManager` riêng | Nhánh tạo `ReactiveUserDetailsService` tự động có thể nhường quyền theo điều kiện auto-configuration |
| Bổ sung OAuth2 Client/Resource Server | Nhánh tạo người dùng mặc định có thể không kích hoạt; cần xác định cơ chế xác thực dự kiến |
| Cấu hình cả chain lẫn authentication | Toàn bộ chính sách và nguồn danh tính do ứng dụng chủ động định nghĩa |

Các điều kiện “back off” là hành vi **có điều kiện** của auto-configuration, không phải quy luật rằng cứ viết bất kỳ bean nào thì Spring Security tắt hết.

## 3. Tài khoản phát triển tự sinh: username, password, role, vòng đời

Khi Spring Boot thực sự phải tạo người dùng mặc định, thông thường:

| Thuộc tính | Giá trị/ý nghĩa |
|---|---|
| Username | `user` |
| Password | Chuỗi ngẫu nhiên được sinh khi application context khởi động |
| Nơi nhìn thấy password | Thông điệp WARN trong startup log, nếu mức logging cho phép |
| Vai trò mặc định | `USER` (authority tương ứng `ROLE_USER`) |
| Nơi lưu người dùng | In-memory reactive user store, không phải bảng người dùng trong database |
| Mục đích | Hỗ trợ thử ứng dụng đang phát triển; không dùng làm tài khoản production |

Ví dụ **minh họa định dạng log**, không phải một mật khẩu thật cần sao chép:

```text
Using generated security password: <random-secret>
This generated password is for development use only.
Your security configuration must be updated before running your application in production.
```

Log thường phát từ nhóm `org.springframework.boot.autoconfigure.security` ở mức WARN trong Spring Boot 3.3. Nếu không nhìn thấy dòng này, **đừng kết luận ứng dụng không có bảo mật**: có thể bạn đã định nghĩa nguồn xác thực riêng, đã đặt mật khẩu thông qua cấu hình, log level không hiển thị WARN hoặc cơ chế auto-configuration đã đổi do dependency.

Mật khẩu tự sinh **không ổn định giữa các lần khởi động độc lập**. Không mã hóa cứng nó vào source, test script chia sẻ hoặc CI. Không coi bản in trong log là kênh cấp phát credential an toàn.

### Vì sao tên role không đồng nghĩa quyền đối với tài nguyên?

`ROLE_USER` chỉ là một authority cho phép policy so khớp, ví dụ `hasRole("USER")`. Một tài khoản có role USER **không mặc nhiên được xem dữ liệu của mọi user khác**. Bài học này tập trung cấu hình mặc định; khi xây API thực tế vẫn phải kiểm quyền ở service/repository theo tài nguyên.

## 4. Ví dụ Spring Boot WebFlux tối thiểu chạy được

Ví dụ này **cố ý không khai báo** `SecurityWebFilterChain` hoặc `ReactiveUserDetailsService` để quan sát auto-configuration thật. Giả định máy đã có JDK 17+ và Gradle phiên bản tương thích với Spring Boot 3.3.

Cấu trúc:

```text
default-security-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/reactive/DefaultSecurityApplication.java
```

**settings.gradle**:

```groovy
rootProject.name = 'default-security-demo'
```

**build.gradle**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.reactive'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

**src/main/java/demo/reactive/DefaultSecurityApplication.java**:

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class DefaultSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(DefaultSecurityApplication.class, args);
    }

    @GetMapping("/api/public")
    public Mono<String> publicMessage() {
        return Mono.just("public endpoint");
    }

    @GetMapping("/api/hello")
    public Mono<String> hello() {
        return Mono.just("hello from WebFlux");
    }
}
```

Ở trạng thái ban đầu, tên `/api/public` **không làm nó công khai**. Không có `permitAll()` nào được khai báo nên cả hai URL đều cần xác thực.

### Chạy và quan sát

Trong thư mục dự án:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle wrapper tương thích, có thể dùng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Đọc startup log, lấy mật khẩu sinh ngẫu nhiên **trên lần khởi động đó**.

Từ terminal khác:

```bash
# Không có credential: yêu cầu API JSON
curl -i -H "Accept: application/json" http://localhost:8080/api/hello

# Có HTTP Basic: thay GENERATED_PASSWORD bằng chuỗi vừa thấy trong log
curl -i -H "Accept: application/json" \
  -u "user:GENERATED_PASSWORD" \
  http://localhost:8080/api/hello

# Endpoint có tên public vẫn bị chặn nếu chưa cấu hình permitAll
curl -i -H "Accept: application/json" http://localhost:8080/api/public
```

Kết quả chính cần kiểm tra:

| Request | HTTP kỳ vọng | Giải thích |
|---|---|---|
| `GET /api/hello` không credential, `Accept: application/json` | `401 Unauthorized` | Chưa xác thực |
| `GET /api/hello` với tài khoản `user` và mật khẩu mới sinh | `200 OK`, body `hello from WebFlux` | Authenticated |
| `GET /api/public` không credential | `401 Unauthorized` | Tên endpoint không tạo ngoại lệ |
| Truy cập `/api/hello` bằng browser có `Accept: text/html` | Thường chuyển hướng `302` sang `/login` | Form login/content negotiation |

Mã HTTP quan trọng hơn nội dung HTML/thông báo lỗi, vì body và header có thể thay đổi theo client, version và cấu hình. Trên browser, trang login mặc định xuất hiện nếu browser chưa đăng nhập. Tránh diễn giải một redirect `302` thành “API không được bảo vệ”.

> **Mẹo:** Thử sai mật khẩu để xác nhận `401`. Thử đăng nhập thành công rồi mở URL thứ hai để thấy cách session/form login khác với việc gửi HTTP Basic ở từng request. Trong ứng dụng dùng cookie/form login, các request thay đổi trạng thái phải tuân thủ bảo vệ CSRF.

## 5. Thay username/password mặc định khi phát triển

Spring Boot cung cấp nhóm property `spring.security.user.*`. Ví dụ cho một môi trường local **vẫn dùng nguồn người dùng mặc định**:

**application.yml**:

```yaml
spring:
  security:
    user:
      name: local-user
      password: ${LOCAL_DEV_PASSWORD}
      roles: USER
```

Trước khi chạy, đặt biến môi trường `LOCAL_DEV_PASSWORD` trong shell của bạn. Ví dụ PowerShell:

```powershell
$env:LOCAL_DEV_PASSWORD = "local-only-change-me"
gradle bootRun
```

Dòng trên chỉ là mật khẩu trình diễn ở máy cá nhân; không gửi vào Git và không sử dụng trong hệ thống chung. Khi có property password do bạn cung cấp, bạn không còn mong đợi dòng **mật khẩu ngẫu nhiên** giống ví dụ trước. Chính sách chặn tất cả URL **vẫn còn**, chỉ credential thay đổi.

Nếu thực hiện qua `application.properties`, cú pháp tương đương:

```properties
spring.security.user.name=local-user
spring.security.user.password=${LOCAL_DEV_PASSWORD}
spring.security.user.roles=USER
```

Không cần khai báo cả YAML và properties cùng lúc; hãy dùng một cách. Cấu hình này chỉ thuận tiện cho thử nghiệm ngắn. Với production, ưu tiên hệ thống nhận dạng/xác thực phù hợp và quản lý secret chuyên dụng; **một tài khoản dùng chung vẫn không phải mô hình quản lý người dùng đầy đủ**.

### Khi nào property trên không có tác dụng như mong đợi?

`spring.security.user.*` phục vụ user do Boot auto-configure. Nếu bạn đã viết `@Bean ReactiveUserDetailsService`, `ReactiveAuthenticationManager` hoặc chuyển sang cơ chế OAuth2/JWT, nguồn xác thực và điều kiện tạo user có thể đã khác. Khi đó thay `spring.security.user.name` có thể không sửa người dùng đang thực sự được dùng. Điều tra bean xác thực đang hoạt động, không cố sửa property vô hạn.

## 6. Chủ động đổi quy tắc URL: custom SecurityWebFilterChain

Khi mới thêm security, mọi URL đều đòi hỏi đăng nhập. Giả sử muốn `/api/public` đọc được không cần đăng nhập nhưng `/api/hello` vẫn có bảo vệ.

Thêm **một file Java nữa** trong cùng dự án, giữ nguyên `DefaultSecurityApplication.java`:

**src/main/java/demo/reactive/WebFluxSecurityConfig.java**:

```java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **cấu hình tùy chỉnh**, vì vậy kết quả sau khi restart sẽ khác ví dụ mặc định:

| Đường dẫn | Không credential | Với credential hợp lệ |
|---|---|---|
| `GET /api/public` | `200`, body `public endpoint` | `200` |
| `GET /api/hello` với `Accept: application/json` | `401` | `200` |
| Các đường dẫn khác chưa khai báo | Vẫn cần xác thực theo `anyExchange().authenticated()` | Không tự bảo đảm route tồn tại |

Lưu ý:

1. `pathMatchers(HttpMethod.GET, "/api/public")` chỉ miễn xác thực cho **GET**, không tự miễn cho POST/PUT/DELETE.
2. `anyExchange().authenticated()` bao phủ mọi exchange còn lại; nếu thiếu điều kiện này, cần chủ động đánh giá các đường dẫn không khớp, tránh vô tình mở route.
3. **Custom filter chain không tự thay tài khoản phát triển.** Nếu không thêm nguồn xác thực khác, Boot vẫn có thể tạo `user` và password.
4. `@EnableWebFluxSecurity` không bắt buộc trong ví dụ Spring Boot này, vì auto-configuration Boot đã tích hợp WebFlux Security. Khi viết cấu hình Spring Security thuần không qua Boot, annotation có thể cần thiết tùy cấu trúc dự án.
5. Không gọi `csrf().disable()` chỉ để đơn giản hóa demo GET. Nếu UI dùng cookie/session và request ghi, CSRF phải được xét đúng theo mô hình xác thực.
6. Đối với endpoint vận hành/Actuator, khi thêm custom chain bạn phải kiểm lại policy riêng, nhất là khi có matcher đặc thù hoặc cổng quản trị.

## 7. Thay tài khoản phát triển bằng nguồn xác thực của ứng dụng

Khi cần tài khoản thật, Spring Security reactive có thể dùng:

- `ReactiveUserDetailsService` tự triển khai hoặc `MapReactiveUserDetailsService` cho demo/test có danh sách hữu hạn.
- `ReactiveAuthenticationManager` nếu quy trình xác thực cần tùy chỉnh.
- OAuth2 Login hoặc OAuth2 Resource Server/JWT nếu kiến trúc ứng dụng dùng nhà cung cấp định danh/token.

Điểm bản chất: **khai báo source authentication** và **khai báo access rules** là hai việc khác nhau.

Ví dụ mã *minh họa cho môi trường phát triển*, thay thế kho người dùng ngẫu nhiên bằng một user của ứng dụng; phần này là **cấu hình tùy chọn thay cho cơ chế user tự sinh**, không cần thêm vào bài demo mặc định trừ khi bạn muốn thử nhánh này.

**src/main/java/demo/reactive/LocalUsersConfig.java**:

```java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration(proxyBeanMethods = false)
public class LocalUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails developer = User.withUsername("developer")
            .password(encoder.encode("demo-only-password"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(developer);
    }
}
```

Ở trạng thái này, dùng `developer`/`demo-only-password` (trên localhost) thay cho `user`/mật khẩu sinh ngẫu nhiên. Đây là ví dụ cố định để học bean và PasswordEncoder: **không đưa password literal vào ứng dụng production**; nhận dữ liệu từ nguồn quản lý bí mật hoặc nhà cung cấp danh tính. `BCryptPasswordEncoder` giúp lưu/so sánh hash thay vì lưu mật khẩu thô trong đối tượng người dùng, nhưng mã demo vẫn chứa một chuỗi rõ trong nguồn. Với user thật, không nên dùng in-memory store để thay một hệ thống quản lý định danh đầy đủ.

Nếu chỉ có `LocalUsersConfig` mà chưa thêm custom `SecurityWebFilterChain`, URL vẫn cần xác thực theo mặc định. Nếu chỉ có `WebFluxSecurityConfig` mà chưa có `LocalUsersConfig`, tài khoản `user` tự sinh có thể vẫn hoạt động. Đây là cách tốt để kiểm tra hai lớp không bị lẫn.

## 8. Lỗi hay gặp khi khởi tạo ứng dụng

### 8.1 “Endpoint không truy cập được nên WebFlux bị lỗi”

Thêm starter Security là thay đổi hành vi hợp lệ: request bị từ chối do thiếu credential. Đọc status/`WWW-Authenticate` hoặc `Location: /login` trước khi sửa controller. Truy cập `/error` cũng có thể chịu bảo vệ mặc định.

### 8.2 “Không thấy generated password, chắc security đã tắt”

Sai. Những lý do phổ biến: log WARN của `org.springframework.boot.autoconfigure.security` bị lọc; đã đặt password trong cấu hình; đã cung cấp `ReactiveUserDetailsService`/`ReactiveAuthenticationManager`; hoặc các dependency OAuth2 đã khiến nhánh tạo user tự động nhường quyền. Kiểm tra dependency và bean, không suy luận từ một dòng log.

### 8.3 “Đã thêm chain nên user tự sinh sẽ biến mất”

Custom `SecurityWebFilterChain` là thay đổi chính sách request. Nó không tự bảo đảm `ReactiveUserDetailsService` mặc định bị thay. Cần cấu hình authentication riêng nếu muốn bỏ user phát triển.

### 8.4 “WebFlux dùng SecurityFilterChain như MVC”

Trong reactive stack:
- Bộ lọc bảo mật HTTP: `SecurityWebFilterChain` + `ServerHttpSecurity`.
- Kho người dùng: `ReactiveUserDetailsService`.
- Authentication manager: `ReactiveAuthenticationManager`.
- Request web: `ServerWebExchange`.

Tên kiểu của Servlet stack không thay thế trực tiếp cho các kiểu reactive tương ứng.

### 8.5 “Thay name/password là đủ để chạy production”

Một tài khoản đơn lẻ trong memory thiếu vòng đời người dùng, phân quyền tài nguyên, quản lý khóa, auditing, thu hồi credential, MFA, rate limit và khả năng quản lý phiên. Dùng source xác thực phù hợp, TLS, chính sách secret, phân quyền và kiểm thử trước khi triển khai.

### 8.6 “Vì chỉ làm API nên có thể tắt mọi cơ chế mặc định”

HTTP Basic, form login, CSRF và session có mục đích khác nhau. Với API token bearer thuần, bạn có thể thiết kế một policy khác, nhưng cần cấu hình rõ authentication và kiểm tra CSRF/CORS theo credential thực tế. **Không vô hiệu hóa toàn bộ bảo mật để làm request 200.**

### 8.7 “Dùng logger có thể khôi phục được mật khẩu cũ”

Generated password là giá trị được tạo cho lần khởi động đó; nếu bạn restart, giá trị cũ thường không dùng được. Không xây hệ thống dựa trên lịch sử log để phân phát credential. Log có mật khẩu dev cũng cần được hạn chế truy cập.

## 9. Checklist trước khi chuyển từ demo sang ứng dụng thật

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Dự án chạy WebFlux hay MVC? | Đúng reactive starter và loại security chain |
| Tại sao URL đang yêu cầu đăng nhập? | Có security starter và chain nào đang áp dụng |
| Dữ liệu user đến từ đâu? | Generated user, custom reactive user service, auth manager hay IdP |
| Có còn credential tạm? | Không dùng user/password tự sinh hay mật khẩu hardcode ở production |
| Endpoint public và protected là gì? | Matcher + fallback rule + method-level/object-level authorization |
| Browser gửi cookie hay API dùng bearer? | Chính sách CSRF, session, CORS được thiết kế tương ứng |
| Secrets/tokens có bị đưa vào log? | Đã che, kiểm quyền xem log và vòng đời credential |
| Có thể kiểm thử âm tính không? | Không credential, sai password, sai role, route thiếu quyền |
| Có Actuator và endpoint vận hành? | Được cấu hình bảo vệ hoặc giới hạn mạng đúng mức |

Nên có ít nhất bốn bài kiểm thử khởi đầu: (1) request không credential bị từ chối với API protected; (2) credential hợp lệ vào được; (3) endpoint public cố ý cho phép được truy cập mà không cần credential; (4) tài khoản không đủ quyền bị từ chối ở route có role restriction.

## 10. Bài tập tự kiểm tra

1. Khởi động demo **chưa có** `WebFluxSecurityConfig`, ghi lại trạng thái `401` ở hai endpoint. Tìm dòng “Using generated security password”, đăng nhập bằng `user`.
2. Thêm `WebFluxSecurityConfig`, restart và chứng minh `GET /api/public` chuyển từ `401` sang `200` trong khi `GET /api/hello` chưa login vẫn `401`.
3. Chỉ thêm `LocalUsersConfig`, quan sát tài khoản `developer` dùng được, và user ngẫu nhiên không còn là nguồn mặc định của nhánh demo.
4. Đặt `spring.security.user.name` theo cấu hình local khi **không có** `LocalUsersConfig`; sau đó so sánh khi có `LocalUsersConfig` để hiểu cơ chế auto-configuration nhường quyền.
5. Thử browser với `Accept: text/html` và curl với `Accept: application/json`; mô tả vì sao trường hợp chưa đăng nhập có thể khác redirect và challenge.
6. Giải thích: tại sao “đã khai báo custom `SecurityWebFilterChain`” không chứng minh đã thay `ReactiveUserDetailsService`?

Khi trả lời được sáu câu này, bạn đã phân biệt được **bảo mật web mặc định**, **nguồn tài khoản được tạo tự động** và **quy tắc do ứng dụng tự cấu hình**—ba việc thường bị nhầm khi mới tích hợp Spring Security vào WebFlux.

## Tài liệu đối chiếu

- Spring Boot 3.3, Spring Security (đặc biệt phần **WebFlux Security**): https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security, **Getting Started with WebFlux Applications**: https://docs.spring.io/spring-security/reference/6.3/reactive/getting-started.html
- Spring Security, **WebFlux Security Configuration**: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
