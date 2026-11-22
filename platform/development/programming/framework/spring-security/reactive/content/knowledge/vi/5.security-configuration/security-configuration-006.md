# Tách chuỗi bảo mật cho REST API, giao diện đăng nhập và điểm quản trị trong Spring Security WebFlux

## Mục tiêu bài học

Khi một ứng dụng WebFlux vừa có **REST API**, vừa phục vụ **giao diện đăng nhập bằng form**, vừa có **endpoint quản trị**, mỗi nhóm thường cần cách xác thực và chính sách truy cập khác nhau. Bài này hướng dẫn tách cấu hình thành nhiều `SecurityWebFilterChain` trong **Spring Security reactive**, thay vì nhồi mọi quy tắc và cơ chế đăng nhập vào một chuỗi duy nhất.

Sau bài học, bạn có thể:

1. Xác định đúng vai trò của `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity`, `securityMatcher` và `@Order`.
2. Thiết kế ba chain có trách nhiệm rõ ràng: REST API, trang web/form login, vùng quản trị.
3. Dự đoán chain nào nhận `/api/**`, `/app/**`, `/login`, `/admin/**` và những đường dẫn không được mô tả.
4. Tách xác thực bằng HTTP Basic/Bearer khỏi đăng nhập form và xác định phạm vi sử dụng session, CSRF.
5. Dựng ví dụ Java 17+, Spring Boot WebFlux và kiểm thử được cả **200/401/403/redirect** cũng như lỗi thứ tự/matcher.

**Phạm vi:** Bài tập trung vào **tách và chọn security chain**. Xác thực JWT/OAuth2 và cấu hình Actuator management context được nêu dưới dạng lựa chọn mở rộng; ứng dụng chạy mẫu dùng HTTP Basic cho API/quản trị để thử trực tiếp bằng `curl`, form login cho UI.

## 1. Ba lớp cần hiểu trước khi tách chain

Trong Spring Security WebFlux, luồng tổng quát là:

```text
HTTP request
   |
   v
WebFlux WebFilter chain toàn cục
   |
   v
Spring Security WebFilterChainProxy (một WebFilter)
   |
   +-- xét các SecurityWebFilterChain theo thứ tự @Order
   |      |
   |      +-- securityMatcher(request) của từng chain
   |      |
   |      +-- lấy CHAIN ĐẦU TIÊN khớp
   |             |
   |             +-- chạy các security WebFilter của chain đó
   |                    (authentication, authorization,
   |                     CSRF, exception translation... tùy cấu hình)
   |
   v
WebFilterChain còn lại -> route handler -> HTTP response
```

- **`WebFilterChainProxy`** là điểm đi vào Spring Security reactive từ hệ thống `WebFilter` của WebFlux; nó duyệt các security chain, chèn các filter của chain được chọn vào đường đi.
- **`SecurityWebFilterChain`** là cặp **điều kiện áp dụng** + **tập security WebFilter**. Nó được tạo từ `ServerHttpSecurity.build()`, không phải một endpoint hoặc một controller.
- **`securityMatcher(...)`** là điều kiện cho biết **request thuộc chain nào**.
- **`authorizeExchange(...)`** quy định **quyền truy cập sau khi chain đã được chọn**.
- **`@Order` trên bean `SecurityWebFilterChain`** quy định **thứ tự chọn chain**: giá trị số nhỏ hơn có độ ưu tiên cao hơn; chain khớp đầu tiên thắng.
- **`SecurityWebFiltersOrder`** dành cho thứ tự các filter bên trong một chain; `@Order` của global `WebFilter` lại là một thứ tự khác.

**Quy tắc đặc biệt quan trọng:** Nếu chain được chọn yêu cầu `authenticated()` nhưng authentication thất bại, Spring Security **không tự nhảy sang chain kế tiếp**. Match trước, rồi chạy policy của chain đó. Chỉ request chưa khớp chain nào mới tiếp tục được thử với chain kế tiếp.

## 2. Xác định ranh giới trách nhiệm của ba nhóm endpoint

Một thiết kế thực tế có thể chia:

| Nhóm | Đường dẫn minh họa | Chain ưu tiên | Cơ chế xác thực | Quy tắc ủy quyền |
| --- | --- | --- | --- | --- |
| Quản trị | `/admin/**` | 1 — `adminChain` | HTTP Basic riêng trong demo; thực tế có thể cần MFA, mạng hạn chế hoặc token đặc thù | `hasRole("ADMIN")` |
| REST API | `/api/**` | 2 — `apiChain` | HTTP Basic trong demo; thực tế thường Bearer/OAuth2 Resource Server | `authenticated()` hoặc quyền/scope cụ thể |
| UI và form login | `/login`, `/app/**`, `/public/**` | 3 — `webChain` (fallback) | Form login + session web | Public đối với login/static; trang ứng dụng cần đăng nhập; path còn lại từ chối |

Đặt **admin trước, API sau, UI cuối** là cách thể hiện “matcher cụ thể trước, catch-all sau”. Nếu `/admin/**` không giao nhau với `/api/**` thì đổi thứ tự giữa hai chain đầu không làm thay đổi kết quả hiện tại. Tuy vậy, sắp xếp có chủ đích giúp bảo vệ khi đường dẫn sau này mở rộng, chẳng hạn chuyển admin vào `/api/admin/**` hoặc thêm matcher gộp.

Nếu hệ thống dùng `/api/admin/**`, điều kiện `/api/**` rộng hơn sẽ khớp cả endpoint admin. Khi đó chain **`/api/admin/**` phải đứng trước** `/api/**` hoặc chính API chain phải chứa rule `hasRole("ADMIN")` ở mức đường dẫn chi tiết. Không được tin rằng chain admin phía sau sẽ “nâng cấp” quyền cho request đã vào API chain.

**Không đồng nhất phân tách chain với phân tách tài khoản.** Ví dụ đơn giản có chung `ReactiveUserDetailsService` cho ba chain; trong hệ thống thật, các chain có thể dùng các `ReactiveAuthenticationManager` hoặc identity provider khác nhau. Nhưng dù dùng chung user store, policy của vùng quản trị vẫn phải được kiểm tra riêng.

## 3. Hai câu hỏi về matcher và authorization

Giả sử có:

```java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/admin/**"))
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().hasRole("ADMIN"));
```

Đoạn trên có **hai lớp quyết định**:

1. `securityMatcher("/admin/**")`: request có thuộc vùng mà chain này xử lý không? Nếu không, proxy thử chain kế tiếp.
2. `anyExchange().hasRole("ADMIN")`: sau khi chain đã được chọn, principal có authority `ROLE_ADMIN` không? Nếu không, request bị từ chối/challenge theo cơ chế của chain hiện tại.

Ngược lại, viết:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated());
```

trong một chain **không có `securityMatcher`** có nghĩa chain có matcher mặc định khớp tất cả request; `pathMatchers` chỉ điều khiển quyền **bên trong chain**. Khi chain này đứng trước, nó có thể “nuốt” toàn bộ `/api/**` và `/login` khiến các chain sau không bao giờ được chọn.

### Quy tắc ba bước khi thiết kế

- Bước 1: liệt kê **nhóm URL, HTTP method** và cơ chế xác thực cho từng nhóm.
- Bước 2: định nghĩa `securityMatcher` cho từng chain cụ thể; đặt `@Order` rõ ràng và bổ sung **một chain fallback cuối cùng**.
- Bước 3: trong từng chain, định nghĩa `authorizeExchange` với **quy tắc cụ thể trước** và `anyExchange()` cuối; kiểm thử URL hợp lệ, URL lân cận và URL không khớp.

Nếu không có security chain nào khớp, `WebFilterChainProxy` có thể cho request đi tiếp **không qua tập security filter của chain nào**. Vì vậy đừng suy ra “không match tức là 403”. Đường dự phòng từ chối là hàng rào cần thiết, đặc biệt khi bảo vệ điểm quản trị.

## 4. Ví dụ hoàn chỉnh: Java 17+, Spring Boot 3.3.x và WebFlux

Ví dụ tạo ứng dụng nhỏ có các route:

- `GET /api/data` trả `API_OK`, yêu cầu HTTP Basic hợp lệ.
- `GET /admin/report` trả `ADMIN_OK`, chỉ tài khoản mang `ROLE_ADMIN` qua HTTP Basic.
- `GET /app/home` trả HTML tối giản sau đăng nhập bằng form; nếu chưa có session hợp lệ, trình duyệt được đưa tới trang đăng nhập.
- `GET /public/ping` và `GET /` là công khai.
- `GET /login` và `POST /login` thuộc **webChain**, do Spring Security form login xử lý; không tự tạo handler `/login` trong demo.

### 4.1. Cấu trúc tệp

```text
security-chain-split/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          SecurityChainSplitApplication.java
    test/
      java/
        example/
          SecurityChainSplitApplicationTests.java
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'security-chain-split'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

BOM của Spring Boot quản lý phiên bản Spring Framework, Spring Security và Reactor đồng bộ. Không trộn tùy tiện Spring Security Servlet dependency/cấu hình như `HttpSecurity`/`SecurityFilterChain` vào ví dụ reactive này.

### 4.2. Ứng dụng và ba security chain

Tạo `src/main/java/example/SecurityChainSplitApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SecurityChainSplitApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainSplitApplication.class, args);
    }

    @GetMapping("/api/data")
    public String data() {
        return "API_OK";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "ADMIN_OK";
    }

    @GetMapping(value = "/app/home", produces = MediaType.TEXT_HTML_VALUE)
    public String home() {
        return "<html><body><h1>APP_HOME</h1></body></html>";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/")
    public String index() {
        return "Public home; visit /app/home or /login";
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/admin/**"))
            .authorizeExchange(ex -> ex
                .anyExchange().hasRole("ADMIN"))
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            // Không chỉ định securityMatcher:
            // matcher mặc định bao phủ phần còn lại.
            .authorizeExchange(ex -> ex
                .pathMatchers("/", "/login", "/public/**").permitAll()
                .pathMatchers("/app/**").authenticated()
                .anyExchange().denyAll())
            .formLogin(withDefaults())
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}view")
            .roles("USER")
            .build();

        UserDetails operator = User.withUsername("operator")
            .password("{noop}admin")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(viewer, operator);
    }
}
```

**Vì sao thiết kế này hợp lý cho bài học?**

**`adminChain`:** matcher `/admin/**`, ưu tiên 1, yêu cầu `ROLE_ADMIN` và HTTP Basic. Tài khoản `viewer` xác thực thành công nhưng chỉ có `ROLE_USER` nên vẫn bị 403. Tài khoản `operator` mang `ROLE_ADMIN` được vào.

**`apiChain`:** matcher `/api/**`, ưu tiên 2, yêu cầu bất kỳ người dùng đã xác thực; không bật form login để API thiếu credentials nhận luồng HTTP Basic challenge thay vì bị chuyển tới màn hình đăng nhập.

**`webChain`:** không gọi `securityMatcher`, nên áp dụng cho những request chưa khớp hai chain trên. Nó bật form login; `GET /login` được Spring Security tạo trang mặc định khi chưa cung cấp trang đăng nhập tùy biến, và `POST /login` là endpoint xử lý thông tin đăng nhập. `/app/**` yêu cầu session đăng nhập; `/public/**` cho phép khách; URL còn lại bị `denyAll()`.

**`NoOpServerSecurityContextRepository` ở API/admin:** không lưu/khôi phục `SecurityContext` qua repository giữa những request của hai chain này, vì mục tiêu demo là để API/admin yêu cầu credentials riêng. `webChain` không dùng `NoOp` để form login vẫn có thể duy trì đăng nhập bằng web session. Lưu ý **NoOp không tự tắt mọi cơ chế tạo `WebSession`**: ví dụ CSRF token repository mặc định vẫn có thể dùng session. Đây là khác biệt giữa **không lưu SecurityContext** và **stateless tuyệt đối**.

**Mật khẩu `{noop}` chỉ phục vụ demo** để dễ thử `curl`; ứng dụng thật dùng password encoder phù hợp, kho danh tính thích hợp và HTTPS. HTTP Basic ở đây giúp bài học chạy được mà không cần dựng OAuth Authorization Server/JWK. Với REST API thật, nếu client là browser hoặc cần phân quyền bằng scope, nên cân nhắc Bearer token/OAuth2 Resource Server và quy tắc CSRF tương ứng.

### 4.3. Chạy và quan sát kết quả

Từ thư mục `security-chain-split`, dùng JDK 17+ và Gradle tương thích với plugin Boot:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper của dự án, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Mở terminal khác rồi chạy các lệnh độc lập:

```bash
curl -i http://localhost:8080/public/ping

curl -i http://localhost:8080/api/data

curl -i -u viewer:view http://localhost:8080/api/data

curl -i -u viewer:view http://localhost:8080/admin/report

curl -i -u operator:admin http://localhost:8080/admin/report

curl -i http://localhost:8080/app/home

curl -i http://localhost:8080/login
```

Kết quả kỳ vọng khi ứng dụng chạy thành công (bỏ qua header và chi tiết trang HTML thay đổi theo phiên bản):

| Request | Chain | HTTP dự kiến | Giải thích |
| --- | --- | --- | --- |
| `GET /public/ping`, không credentials | `webChain` | 200, body `PONG` | Public |
| `GET /api/data`, không credentials | `apiChain` | 401 + `WWW-Authenticate` | API yêu cầu Basic |
| `GET /api/data`, Basic `viewer:view` | `apiChain` | 200, body `API_OK` | Đã xác thực |
| `GET /admin/report`, Basic `viewer:view` | `adminChain` | 403 | Có danh tính, thiếu `ROLE_ADMIN` |
| `GET /admin/report`, Basic `operator:admin` | `adminChain` | 200, body `ADMIN_OK` | Đủ role |
| `GET /app/home`, chưa có session | `webChain` | 302 hướng `/login` | UI dùng form login |
| `GET /login` | `webChain` | 200, HTML login mặc định | Đường login ở đúng chain |

Cần hiểu giới hạn: bảng trên dựa vào **đúng cấu hình demo**. Response 401/403/302 trong ứng dụng khác có thể khác nếu entry point, access-denied handler, matcher hoặc cơ chế xác thực được thay đổi. Đừng suy ra mã HTTP chỉ từ `@Order`.

Thử đăng nhập thực tế: mở `http://localhost:8080/app/home` trong trình duyệt, đi theo redirect tới trang `/login`, dùng `viewer/view` hoặc `operator/admin` rồi truy cập lại. Việc đăng nhập bằng form duy trì browser session cho `/app/**`. Nó **không có nghĩa** có thể truy cập `/api/data` hay `/admin/report` bằng session ấy: hai chain đó đã chọn `NoOpServerSecurityContextRepository` và không bật form login, nên cần cơ chế xác thực mà từng chain chấp nhận.

## 5. Vì sao /login phải nằm trong chain giao diện?

Form login không chỉ có **một trang HTML**. Nó bao gồm cả các đường đi:

```text
GET /app/home (chưa đăng nhập)
      |
      v
webChain: authentication cần thiết
      |
      v
redirect đến GET /login
      |
      v
webChain: hiển thị form + token CSRF
      |
      v
người dùng POST /login (username, password, CSRF)
      |
      v
webChain: xác thực, lưu SecurityContext vào web session
      |
      v
redirect sau đăng nhập -> yêu cầu /app/home có session
```

Vì `WebFilterChainProxy` chỉ chọn **một chain cho mỗi request**, cả `GET /login` lẫn `POST /login` phải được bao phủ bởi chain có `formLogin(...)`. Nếu bạn gắn `securityMatcher("/app/**")` cho web chain nhưng lại để `/login` ngoài matcher, browser có thể nhìn thấy trang đăng nhập của một chain khác hoặc request `POST /login` không được filter đúng xử lý.

Ví dụ cấu hình **sai**:

```java
@Bean
@Order(3)
SecurityWebFilterChain brokenWebChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/app/**"))
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated())
        .formLogin(withDefaults())
        .build();
}
```

Nếu không có chain khác cung cấp `/login`, request login không gặp filter xử lý form đúng cách. Ngay cả khi có chain fallback, việc tách matcher cho login và web yêu cầu thiết kế nhất quán giữa URL, CSRF, success/failure handler, login processing và repository lưu security context.

**Cách tránh:** Với UI thông thường, một `webChain` mặc định phủ phần còn lại vừa chứa `/app/**`, `/login`, `/logout` và static assets cần thiết. Nếu cần login URL tùy biến như `/signin`, bảo đảm GET trang, POST xử lý, URL lỗi và các tài nguyên của trang đều đi qua chain phù hợp; tránh redirect vòng lặp (`/signin` lại yêu cầu đăng nhập).

### Trang login công khai có nghĩa là gì?

`permitAll()` trên `/login` chỉ cho phép người chưa xác thực xem trang hoặc gửi request tới endpoint; nó **không bỏ qua** kiểm tra username/password hoặc CSRF khi `POST /login`. Login filter và CSRF filter có trách nhiệm riêng. Không dùng `web.ignoring` theo kiểu Servlet cho WebFlux; muốn tài nguyên công khai, nên dùng rule `permitAll()` có chủ đích trong chain thích hợp.

## 6. CSRF và session: tách chain không tự tạo an toàn

Một sai lầm phổ biến là thấy REST API dùng JSON hoặc HTTP Basic rồi tắt `csrf` vô điều kiện. Trong Spring Security WebFlux, **CSRF được bật mặc định**; WebFlux form login/POST logout dựa trên bảo vệ này.

### Bảng quyết định

| Tình huống | Phân tích CSRF |
| --- | --- |
| Browser form login + cookie session | **Giữ CSRF** cho login, logout và request thay đổi trạng thái; form phải gửi token |
| REST API chỉ nhận Bearer token trong header do client tự đặt, không nhận cookie/credentials tự gửi | Thường không phụ thuộc CSRF theo mô hình xác thực này; chỉ tắt sau khi đã xác minh giao diện xác thực thực tế |
| REST API dùng HTTP Basic từ browser | Trình duyệt có thể tự gửi Basic credentials đã ghi nhớ; **không suy ra là an toàn trước CSRF** |
| Endpoint admin thực hiện POST/PUT/DELETE | Bảo vệ CSRF nếu có cơ chế credentials trình duyệt tự đính kèm; ngoài ra cần kiểm soát role, audit và thao tác nhạy cảm |
| API nhận cookie session dù kết quả là JSON | Có nguy cơ CSRF tương tự website; đường dẫn `/api/**` không tự bảo vệ |

Trong ví dụ chạy được, **không tắt CSRF** tại chain nào: chỉ có các GET endpoint an toàn để tập trung kiểm chứng cơ chế tách chain. Nếu thêm `POST /api/orders` hoặc `POST /admin/restart`, request Basic đơn thuần chưa có CSRF token có thể nhận 403. Đó là kết quả của **chính sách CSRF**, không phải do chọn nhầm security chain. Với API production Bearer thuần, có thể cấu hình tắt CSRF **chỉ ở chain được đánh giá là không có rủi ro credentials tự đính kèm**, ví dụ:

```java
// Chỉ là mảnh cấu hình, KHÔNG dùng nếu API chấp nhận Basic
// được trình duyệt tự đính kèm, cookie session, hoặc cơ chế tương tự.
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"))
    .csrf(csrf -> csrf.disable())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(withDefaults()));
```

Mảnh trên **không độc lập/chạy được ngay** vì cần dependency OAuth2 Resource Server và `ReactiveJwtDecoder`/issuer/JWK hợp lệ. Nó minh họa vị trí áp dụng policy sau khi kiến trúc xác thực bằng Bearer được triển khai. Đừng lấy mỗi dòng `csrf.disable()` mà bỏ điều kiện về loại credentials.

### Phân biệt web session, security context và token

- **Web session** có thể chứa security context hoặc CSRF token và những dữ liệu khác.
- **SecurityContext** biểu diễn thông tin xác thực của request; có thể được tải/lưu bởi `ServerSecurityContextRepository`.
- **NoOpServerSecurityContextRepository** ngăn việc lưu/đọc security context qua repository này; nó không đồng nghĩa không có session ở mọi tầng.
- **CSRF token** là bằng chứng chống request giả mạo, khác hẳn access token hoặc session cookie.
- **Authentication** (đăng nhập thành công) vẫn cần **Authorization** (đủ quyền vào endpoint).

Duy trì session cho UI nhưng dùng credentials mỗi request cho API và admin là lựa chọn thiết kế của demo. Trong hệ thống thật cần kiểm tra thêm domain, cookie, proxy, CORS, MFA, hạn chế nguồn truy cập admin, ghi audit và thời hạn token/session.

## 7. Tách vùng quản trị đúng cách

Trong ví dụ, “điểm quản trị” là controller của ứng dụng dưới `/admin/**`. Mức kiểm soát gồm:

1. Một matcher riêng để mọi request `/admin/**` được chọn bởi `adminChain`.
2. Authentication bằng HTTP Basic ở chain admin.
3. Authorization `hasRole("ADMIN")`, kiểm tra authority thực tế `ROLE_ADMIN`.
4. Fallback `denyAll()` giúp những URL quên cấu hình không được tự động mở ra.
5. Kiểm thử đồng thời tài khoản thường, tài khoản admin, và trường hợp thiếu credentials.

**`hasRole("ADMIN")` không đồng nghĩa so sánh `username.equals("admin")`.** Spring Security theo quy ước role prefix: user tạo bởi `.roles("ADMIN")` có authority `ROLE_ADMIN`. Nếu ứng dụng lưu authority dạng `ADMIN` thuần, cần chọn `hasAuthority("ADMIN")` hoặc ánh xạ authority đúng cách; không dự đoán từ tên tài khoản.

**REST endpoints quản trị không tự trở thành actuator endpoints.** Nếu dùng Spring Boot Actuator tại `/actuator/**`, chúng có route và cơ chế đăng ký riêng; matcher `/admin/**` **không** tự bảo vệ `/actuator/**`. Nếu Actuator cùng context/port, cần lập chính sách cho vị trí thực tế (ví dụ matcher dựa trên endpoint thông qua API Spring Boot phù hợp); nếu dùng **management port/context riêng**, cần xác minh security của management context thay vì suy đoán chain ứng dụng chính sẽ chạy tại cổng đó.

Không nên dùng “đổi URL thành `/secret/admin`” làm biện pháp bảo mật: path ẩn không thay cho role, xác thực mạnh, network segmentation hoặc kiểm toán. Đối với thao tác rất nhạy cảm (xóa dữ liệu, cấp quyền, restart), cần thêm cơ chế xác nhận/ủy quyền theo nghiệp vụ; chỉ vai trò ADMIN có thể chưa đủ.

## 8. Các tình huống sai thứ tự và hở phạm vi

### 8.1. Chain tổng quát đứng trước

```java
// CẢNH BÁO: ví dụ sai, minh họa nguyên nhân.
@Bean
@Order(1)
SecurityWebFilterChain tooBroad(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated())
        .formLogin(withDefaults())
        .build();
}
```

Chain không có `securityMatcher` này khớp tất cả URL, kể cả `/admin/report` và `/api/data`. Khi đứng trước, các chain admin/API không có cơ hội được chọn, làm sai cả challenge lẫn chính sách quản trị. **Sửa:** chuyển chain bao phủ phần còn lại xuống cuối và bảo đảm quyền trong chain fallback theo nguyên tắc từ chối.

### 8.2. API matcher bao cả admin nhưng thiếu role

```text
Chain 1: /api/** -> authenticated()
Chain 2: /api/admin/** -> hasRole("ADMIN")
Request: /api/admin/delete
Kết quả: Chain 1 khớp trước; Chain 2 KHÔNG được xét tiếp.
```

**Sửa:** đặt `/api/admin/**` trước `/api/**`, hoặc gộp role rule vào API chain bằng `pathMatchers("/api/admin/**").hasRole("ADMIN")` trước `anyExchange()`.

### 8.3. Đường dẫn gốc không khớp pattern

Với `PathPatternParserServerWebExchangeMatcher("/admin/**")`, không nên đoán cách mọi phiên bản/router chuẩn hóa `/admin`, `/admin/`, path có dấu chấm phẩy hoặc encoded path. Kiểm thử **cả URL gốc và URL có đoạn con**, cùng HTTP method thực tế. Trong mẫu này, `/admin` không có handler và fallback `denyAll()`, nên không có ý định cấp quyền theo lỗi khớp pattern.

Nếu nghiệp vụ cần bảo vệ chính xác `/admin` **và** `/admin/**` bằng cùng một chain, dùng matcher kết hợp (như `OrServerWebExchangeMatcher`) hoặc matcher phù hợp API phiên bản thay vì chỉ trông cậy vào một pattern chưa được kiểm chứng.

### 8.4. Tắt form login ở chain sai

Nếu chỉ bật `formLogin` trong `webChain` nhưng lại đặt `/login` dưới matcher `/api/**`, request GET/POST login có thể rơi vào chain Basic, dẫn tới 401/404 hoặc không có xử lý form đúng. Sửa lại ranh giới URL và bảo đảm cả login page, processing, error redirect đều đi qua chain tương thích.

### 8.5. Không có chain nào khớp

Một ứng dụng chỉ tạo hai chain `/admin/**` và `/api/**` sẽ bỏ lại `/app/**`, `/login`, `/public/**` ngoài các chain ấy. **Không có match không tự động tạo DENY.** Nếu không có security chain khác phù hợp, request có thể tiếp tục tới handler. Đây là lý do cần chain cuối có matcher tổng quát và `anyExchange().denyAll()` cho phần không được định nghĩa.

### 8.6. Phân tách authentication nhưng dùng chung session ngoài ý muốn

Nếu chain API có thể đọc `SecurityContext` từ web session, user đã login qua giao diện có thể vô tình được API coi là authenticated dù bạn định yêu cầu API credential riêng. Không coi việc chỉ bật `httpBasic()` là bảo đảm cách ly hoàn toàn khỏi session; phải xem xét `ServerSecurityContextRepository`, điều kiện nhận credentials và các filter thực tế. Demo chọn NoOp cho API/admin, còn browser chain dùng cơ chế session cho form.

## 9. Kiểm thử phân tách chain bằng WebTestClient

Tạo `src/test/java/example/SecurityChainSplitApplicationTests.java` để kiểm chứng behavior thực, thay vì chỉ nhìn số lượng bean:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityChainSplitApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsPublic() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void apiRequiresCredentials() {
        client.get().uri("/api/data")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void apiAcceptsValidBasicCredentials() {
        client.get().uri("/api/data")
            .headers(h -> h.setBasicAuth("viewer", "view"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("API_OK");
    }

    @Test
    void adminDeniesUserWithoutAdminRole() {
        client.get().uri("/admin/report")
            .headers(h -> h.setBasicAuth("viewer", "view"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminAcceptsAdminRole() {
        client.get().uri("/admin/report")
            .headers(h -> h.setBasicAuth("operator", "admin"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ADMIN_OK");
    }

    @Test
    void browserAppRedirectsToLogin() {
        client.get().uri("/app/home")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void generatedLoginPageIsReachable() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Chạy:

```bash
gradle test
```

Hoặc dùng Wrapper như phần chạy ứng dụng. Các test này kiểm tra route behavior **với SecurityWebFilterChain thực**. Chúng không kiểm tra đầy đủ form POST/CSRF (cần gửi CSRF token hợp lệ và kiểm tra cookie/session), không thay cho test xác thực JWT hay kiểm thử load. Nên bổ sung test riêng khi bạn thay HTTP Basic bằng Bearer.

Với chain có role nhạy cảm, luôn có ít nhất một kiểm thử **negative** chứng minh tài khoản thường bị từ chối. Test mỗi endpoint chỉ với admin sẽ không phát hiện lỗi `authenticated()` vô tình cho phép mọi người đăng nhập.

## 10. Checklist thiết kế và triển khai

| Vấn đề cần kiểm | Câu hỏi xác nhận |
| --- | --- |
| Bao phủ URL | Mọi endpoint có nằm trong đúng chain? Đường không nhận diện được có bị deny? |
| Ưu tiên | Chain cụ thể đứng trước chain tổng quát? Có matcher chồng lấp nào cần test? |
| Login | `GET /login` và `POST /login` đi qua chain có form login? Có redirect loop? |
| Authorization | Khu admin bắt buộc role/authority hay chỉ cần authenticated? |
| Authentication | API chấp nhận Basic/Bearer nào? UI có form session? Có vô tình reuse session? |
| CSRF | Có tác vụ POST/PUT/DELETE với browser credentials tự đính kèm? |
| Error | Thiếu xác thực có trả challenge/redirect phù hợp? Thiếu quyền có bị chặn? |
| Vận hành | Admin endpoint có audit, HTTPS, rate limiting, quản lý bí mật và kiểm soát truy cập mạng? |
| Test | Đã thử URL công khai, URL cần đăng nhập, URL admin, URL ngoài matcher và case quyền sai chưa? |

### Lỗi thường gặp

- **Dùng lớp Servlet thay WebFlux:** `SecurityFilterChain`/`HttpSecurity` không phải `SecurityWebFilterChain`/`ServerHttpSecurity`. Tránh lẫn package và mô hình thread.
- **Đặt catch-all ở `@Order(1)`:** các chain cụ thể không bao giờ được chọn.
- **Hiểu `pathMatchers` như chọn chain:** nó chỉ chọn rule bên trong chain được chọn.
- **Chỉ match `/app/**` rồi quên `/login`:** trình duyệt bị kẹt tại trang/POST đăng nhập.
- **Cấp quyền admin bằng `authenticated()`:** người dùng thường cũng có thể được phép vào admin. Dùng role/authority nghiệp vụ.
- **Tắt CSRF vì URL bắt đầu bằng `/api/`:** URI và JSON không loại bỏ nguy cơ CSRF nếu browser tự gửi credentials.
- **Cho rằng NoOp repository xóa mọi session:** CSRF và thành phần khác vẫn có thể sử dụng web session.
- **Tin là nhiều chain được gộp tự động:** Spring Security dùng **chain đầu tiên khớp**, không lấy tất cả chain rồi hợp quyền.
- **Chỉ kiểm tra HTTP 200:** thiếu test 401, 403, redirect và URL ngoài matcher khiến bypass khó phát hiện.
- **Bỏ qua Actuator ở cổng khác:** chain cho `/admin/**` không đồng nghĩa đã bảo vệ management endpoints của Boot.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao có `@Order(1)` cho `/admin/**` và `@Order(3)` cho chain mặc định?  
**Đáp:** Để proxy xét matcher quản trị trước. Một khi chain quản trị khớp, chỉ các filter/policy của chain đó được áp dụng; chain mặc định không chạy thêm.

**Câu 2.** `GET /api/data` không credentials trong ví dụ có bị chuyển đến `/login` không?  
**Đáp:** Không. Request vào `apiChain`, nơi bật HTTP Basic và tắt form login; kết quả dự kiến là 401 challenge.

**Câu 3.** Người đã login vào `/app/home` có tự truy cập `/admin/report` qua cookie session không?  
**Đáp:** Không theo thiết kế demo. `adminChain` không dùng repository session để lấy `SecurityContext` và kiểm tra role ADMIN bằng cơ chế xác thực của chính chain đó. Browser login cũng không thay thế role.

**Câu 4.** Vì sao `/login` phải thuộc phạm vi webChain?  
**Đáp:** Đây là URL hiển thị và xử lý form. Chain có `formLogin` phải áp dụng cho các request liên quan, gồm POST login và kiểm tra CSRF.

**Câu 5.** Nếu chỉ có hai chain `/admin/**` và `/api/**`, `/app/home` tự bị chặn 403 không?  
**Đáp:** Không thể suy ra. Nếu không chain nào khớp, request có thể đi tiếp tới handler mà không qua security filters của chain đã định nghĩa. Cần chain fallback/phòng vệ rõ ràng.

**Câu 6.** Nếu đổi sang OAuth2 Resource Server, chỉ cần bật `jwt()` ở API chain là xong không?  
**Đáp:** Chưa. Cần dependency, cấu hình `ReactiveJwtDecoder`/issuer, xác thực chữ ký, audience và ánh xạ authority/scope thích hợp; kiểm thử 401/403, CSRF, refresh/revocation theo kiến trúc cụ thể.

**Kết luận:** Tách chuỗi trong Spring Security reactive là tách **phạm vi matcher**, **cơ chế xác thực** và **chính sách ủy quyền**. Với REST API, UI form login và quản trị, hãy tạo các `SecurityWebFilterChain` có thứ tự minh bạch, đặt **chain fallback từ chối** cuối cùng, bảo đảm `/login` nằm trong chain phù hợp và kiểm thử case sai quyền. Mỗi request chỉ đi qua **một security chain được chọn**.

## Tài liệu tham khảo

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `@Order`, `securityMatcher` và lựa chọn chain đầu tiên.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html) — cơ chế token, WebSession, login/logout, tác vụ thay đổi dữ liệu.
- [Spring Security — OAuth2 Resource Server for WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html) — Bearer token, JWT và bảo vệ API theo token.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — cấu hình authentication, authorization, CSRF, form login và context repository.
- [Spring Security — NoOpServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html) — repository không lưu `SecurityContext`.
- [Spring Boot — WebFlux Security Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html) — cách Boot phối hợp cấu hình security ứng dụng.
