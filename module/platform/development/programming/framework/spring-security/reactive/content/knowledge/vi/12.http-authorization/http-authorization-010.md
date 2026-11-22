# Thiết kế quy tắc mặc định từ chối và xử lý đường dẫn không khớp

## 1. Vấn đề: một URL mới không được tự động mở quyền

Trong ứng dụng Spring Security Reactive chạy trên Spring WebFlux, hệ thống có thể có hàng chục hoặc hàng trăm endpoint: công khai, dành cho người dùng đã đăng nhập, chỉ dành cho quản trị viên và các đường dẫn không bao giờ được truy cập trực tiếp. Những endpoint mới có thể xuất hiện sau khi lập trình viên thêm controller, RouterFunction, Actuator hoặc một module khác.

Nếu cấu hình chỉ nói:

~~~java
// Cấu hình CHƯA đủ chặt nếu mục tiêu là allowlist từng endpoint.
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated())
~~~

thì **mọi đường dẫn còn lại đều được chấp nhận sau khi xác thực**, kể cả một endpoint tương lai chưa qua kiểm duyệt quyền. Đây là chính sách “mặc định cần đăng nhập”, khác với **“mặc định từ chối”**.

Khi muốn chủ động cho phép đúng những chức năng đã phê duyệt, dùng chính sách **deny-by-default**:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .pathMatchers(HttpMethod.GET, "/api/admin/summary").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Đoạn thứ hai là snippet cấu hình cần được đặt trong `ServerHttpSecurity` và import `org.springframework.http.HttpMethod`. Mọi request không khớp các quy tắc đứng trước sẽ bị từ chối, **kể cả khi người gọi có tài khoản quản trị viên**.

Bài học này thuộc nhóm **Phân quyền HTTP**. Trọng tâm không phải cách mã hóa mật khẩu hay tạo JWT, mà là cách xây dựng các quy tắc cho HTTP request để một đường dẫn/HTTP method chưa được khai báo **không vô tình được sử dụng**.

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt `denyAll()`, `permitAll()`, `authenticated()`, `hasRole()` và `hasAuthority()`.
2. Hiểu **thứ tự matcher** và tại sao quy tắc đặc hiệu phải đứng trước `anyExchange()`.
3. Phân biệt **security-chain matcher**, **authorization matcher** và **WebFlux handler mapping**.
4. Giải thích khi nào một URL không có handler nhận 403 thay vì 404; tại sao 401/403/404/405 phụ thuộc lớp xử lý.
5. Tạo cấu hình “allowlist + default deny” cho cả path và HTTP method.
6. Xử lý đúng trường hợp nhiều `SecurityWebFilterChain`, route không khớp security chain, actuator/static resources, CORS preflight và reverse proxy.
7. Chạy ứng dụng Java 17+ với Spring Boot/WebFlux/Spring Security, thử bằng curl và `WebTestClient`.
8. Xây checklist đánh giá quy tắc trong code review và test regression.

## 2. Nguyên tắc “default deny” và “least privilege”

**Default deny** nghĩa là một HTTP request chỉ được đi tiếp nếu chính sách có một quy tắc **cho phép** phù hợp. Bất kỳ request chưa được đưa vào danh sách có quyền truy cập sẽ bị từ chối.

**Least privilege** nghĩa là quy tắc cho phép phải cấp ít quyền nhất cần cho chức năng. Ví dụ:
- `GET /public/ping`: công khai, không yêu cầu authentication.
- `GET /api/reports`: cần `ROLE_READER`.
- `GET /api/admin/summary`: cần `ROLE_ADMIN`.
- `GET /api/debug`: có thể tồn tại trong code nhưng **không được cho phép** qua cấu hình hiện tại.
- `GET /api/something-new`: endpoint mới chưa được phê duyệt, mặc định bị từ chối.

Hai mức mặc định thường bị nhầm:

| Quy tắc kết thúc | Ý nghĩa khi request không khớp rule nào trước đó | Rủi ro |
| --- | --- | --- |
| `anyExchange().permitAll()` | Không cần bất kỳ quyền nào | Dễ mở toàn bộ endpoint ngoài ý muốn |
| `anyExchange().authenticated()` | Cần một Authentication phù hợp | Mọi endpoint mới có thể được mọi user đã đăng nhập truy cập |
| `anyExchange().hasRole("USER")` | Cần một role chung | Vẫn tự động mở những endpoint mới cho role chung |
| `anyExchange().denyAll()` | Không một identity nào được phép | Mỗi endpoint mới cần một quyết định explicit |

`authenticated()` có thể là lựa chọn hợp lệ nếu **đó là chính sách được chủ đích áp dụng cho mọi endpoint**. Nhưng khi yêu cầu kiểm soát chặt đường dẫn và phương thức mới, `denyAll()` tạo ra một hàng rào rõ ràng: phát triển tính năng phải đi kèm thay đổi rule và test.

**Không có “superuser” tự động bỏ qua `denyAll()`.** Dù user có `ROLE_ADMIN`, một rule `denyAll()` cuối cùng vẫn từ chối nếu URL không match các rule trước nó.

## 3. Ba tầng khớp đường dẫn: phải phân biệt rõ

Đây là phần quan trọng nhất của chủ đề “xử lý đường dẫn không khớp”. Trong WebFlux Security có **ba quyết định match khác nhau**:

### Tầng A — Chọn SecurityWebFilterChain

Ứng dụng có thể khai báo một hoặc nhiều bean `SecurityWebFilterChain`. Mỗi chain có `securityMatcher` xác định nó áp dụng cho request nào. Spring Security xét các chain theo thứ tự và chọn chain phù hợp đầu tiên.

Ví dụ:

~~~java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

Đây là snippet thuộc **cấu hình chain**: request ngoài `/api/**` sẽ không dùng chain này. Nếu không có một chain khác bảo vệ request đó, chính sách trong chain này **không áp dụng** cho đường dẫn ngoài phạm vi.

### Tầng B — Chọn rule trong authorizeExchange

Bên trong chain đã được chọn, `authorizeExchange` có các `pathMatchers`/`matchers` cho từng quyền:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .anyExchange().denyAll())
~~~

Quy tắc được xét theo thứ tự. **Rule khớp đầu tiên quyết định quyền**, còn `anyExchange()` bắt phần còn lại của **chain đang chọn**.

### Tầng C — Tìm WebFlux handler

Sau khi request vượt qua security, WebFlux còn phải tìm controller method hoặc `RouterFunction` phù hợp với URL và HTTP method. Nếu không có handler:
- HTTP 404 thường có ý nghĩa “không tìm thấy route”.
- HTTP 405 có thể xuất hiện khi URL được hỗ trợ nhưng **method** không được handler chấp nhận.
- Các bộ xử lý exception, router, static resources và proxy có thể ảnh hưởng response.

**Bảo mật có thể từ chối trước khi WebFlux đi tới quyết định 404/405.** Đây là lý do một URL không hề tồn tại vẫn có thể trả 403 (hoặc 401 tùy entry point và trạng thái authentication).

### 3.1. Sơ đồ ba tầng

~~~text
HTTP request
    |
    v
Chọn SecurityWebFilterChain theo securityMatcher + @Order
    |
    +-- Không có chain phù hợp:
    |      Không có bảo vệ của Spring Security chain tương ứng
    |      (các lớp khác vẫn có thể xử lý hoặc từ chối)
    |
    +-- Có chain phù hợp:
           |
           v
     Xét authorizeExchange từ trên xuống
           |
           +-- path/method match --> permitAll / role / authority / deny
           |
           +-- không match rule cụ thể --> anyExchange().denyAll()
                                             |
                                       403/401 tùy xử lý
           |
           +-- được phép
                    |
                    v
             WebFlux HandlerMapping
                    |
                    +-- Handler tồn tại --> handler thực thi
                    |
                    +-- Không có handler --> thường 404
                    |
                    +-- Path có handler nhưng method không hỗ trợ
                                                --> có thể 405
~~~

Sơ đồ là mô hình khái niệm: filter xử lý authentication, CSRF, CORS, exception translation có vị trí và hành vi riêng, nên không suy luận status tuyệt đối chỉ từ một dòng DSL.

## 4. Thứ tự rule trong authorizeExchange

Ví dụ đúng:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .pathMatchers(HttpMethod.GET, "/api/admin/summary").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Dòng `anyExchange().denyAll()` là **fallback ở cuối**, không phải một rule được sử dụng để thay thế những rule đã có. Khi request match một rule cụ thể trước đó, policy của rule đó được áp dụng.

### 4.1. Sai thứ tự làm rule cụ thể không còn tác dụng

Đoạn sau thể hiện **tư duy sai**:

~~~java
// SAI: rule tổng quát nuốt request cần kiểm soát riêng.
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Với `GET /api/admin/summary`, `/api/**` đã match trước và chỉ đòi một user đăng nhập. Rule ADMIN phía sau không được áp dụng như mong muốn.

Sửa bằng cách đặt rule đặc hiệu trước:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/reports").hasRole("READER")
        .anyExchange().denyAll())
~~~

Nếu có nhu cầu cho phép mọi user đọc một tập route cố định, nên khai báo **tập route hẹp, có method rõ ràng** hơn là cho phép toàn bộ `/api/**`.

### 4.2. Vì sao không viết anyExchange đầu tiên?

`anyExchange()` là matcher tổng quát cho phần còn lại. Nó nên đứng sau các rule cụ thể. Một cấu hình có catch-all ở đầu có thể bị framework từ chối khi cố thêm rule phía sau, hoặc khiến rule phía sau không còn tác dụng; không xây dựng policy dựa trên thứ tự đó.

### 4.3. Vai trò và authorities

`hasRole("ADMIN")` theo mặc định kiểm tra authority `ROLE_ADMIN`. Vì vậy:

~~~java
.pathMatchers("/api/admin/**").hasRole("ADMIN")
~~~

không đồng nghĩa với:

~~~java
.pathMatchers("/api/admin/**").hasAuthority("ADMIN")
~~~

Trường hợp sau yêu cầu đúng authority chuỗi `ADMIN`; chuỗi `ROLE_ADMIN` không khớp trực tiếp. Với OAuth2 Resource Server, scopes thường được map thành authorities dạng `SCOPE_read` hoặc tương đương theo cấu hình. Phải thống nhất các quy ước giữa authentication mapping và authorization.

## 5. Xử lý đường dẫn không khớp: 403 hay 404?

Giả sử chain bảo vệ mọi URL và có:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/public/catalog/**").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .anyExchange().denyAll())
~~~

Xem hai request:

**A. `GET /public/catalog/not-existing`:** khớp rule `permitAll` dù không có controller thực tế. Security cho phép request đi tiếp. Nếu không có handler/static resource, WebFlux thường trả **404 Not Found**.

**B. `GET /api/not-existing`:** không khớp rule cho phép, rơi vào `denyAll`. Security từ chối **trước khi** HandlerMapping xác định 404. Với client đã xác thực và cấu hình Basic thông thường, bạn có thể quan sát **403 Forbidden**.

Điều quan trọng là **403 không chứng minh endpoint tồn tại**, và **404 không phải lúc nào cũng chứng minh request đã đi qua authorization**. Phải xem toàn bộ chain.

### 5.1. 401, 403, 404, 405: ý nghĩa thực hành

| Status | Điều thường xảy ra | Có thể bị ảnh hưởng bởi |
| --- | --- | --- |
| **401 Unauthorized** | Endpoint yêu cầu authentication nhưng request không có hoặc có credentials không hợp lệ | HTTP Basic/Bearer entry point và filter xác thực |
| **403 Forbidden** | Request đã xác thực nhưng thiếu quyền, hoặc bị deny-by-default; POST thiếu CSRF token cũng có thể 403 | Authorization, CSRF, exception handling |
| **404 Not Found** | Request đã được các filter cho đi tiếp nhưng không có handler/resource phù hợp | WebFlux router/handler/static resources |
| **405 Method Not Allowed** | URL có handler nhưng không hỗ trợ HTTP method yêu cầu | Method mapping; có thể không tới được nếu security chặn trước |

Status thực tế phụ thuộc bộ lọc nào từ chối sớm nhất. Với anonymous request rơi vào một rule deny, entry point có thể tạo 401 trong một số cấu hình; với authenticated request, 403 là kết quả thông thường. Đừng viết test yêu cầu 404 cho đường dẫn đang bị deny-by-default.

### 5.2. Có nên “cho phép route không tồn tại” để nhìn thấy 404?

**Không làm vậy một cách tùy tiện.** Việc cố thêm một wildcard `permitAll()` chỉ để một URL sai trả 404 có thể khiến những endpoint mới thực sự được đăng ký dưới wildcard đó trở thành công khai.

Nếu sản phẩm yêu cầu 404 cho một namespace public, có thể cho phép **một phạm vi public đã được đánh giá** rồi để WebFlux trả 404 cho route không tồn tại. Nhưng namespace đó phải thực sự được phép công khai ngay cả khi developer thêm endpoint mới. Nếu không chắc, giữ deny-by-default.

Một số hệ thống cố ý trả 404 thay 403 cho tài nguyên mà người gọi không được quyền biết có tồn tại. Đây là **quyết định ở tầng authorization/exception policy**, không phải lý do mở wildcard. Việc che giấu tồn tại không thể thay quyền truy cập thật và phải được kiểm thử tránh lộ qua timing/cache/log.

## 6. Kết hợp HTTP method và path: “chỉ GET” là một rule khác “mọi method”

So sánh:

~~~java
// Rule 1: cho phép GET tại /api/reports.
.pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
~~~

với:

~~~java
// Rule 2: cho phép mọi HTTP method tại /api/reports.
.pathMatchers("/api/reports").hasRole("READER")
~~~

Rule 2 rộng hơn: user có role READER có thể qua authorization cho POST/PUT/DELETE ở cùng path, nếu được những filter khác cho phép. Nếu sau này một developer thêm `@DeleteMapping("/api/reports")`, rule 2 đã cấp quyền cho chức năng mới. Rule 1 thì không.

Ví dụ policy viết/chỉ đọc:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/items/**")
            .hasAuthority("SCOPE_items.read")
        .pathMatchers(HttpMethod.POST, "/api/items")
            .hasAuthority("SCOPE_items.write")
        .anyExchange().denyAll())
~~~

Đây là snippet dành cho API có mapping scopes chính xác, **không phải chương trình độc lập**. Với POST/PUT/PATCH/DELETE từ browser có ambient credentials, vẫn cần CSRF protection khi phù hợp. Đừng disable CSRF chỉ để đạt 200.

### 6.1. HEAD và OPTIONS

- HTTP `HEAD` có semantics gần GET nhưng là **HTTP method riêng**. Một rule chỉ match `HttpMethod.GET` không mặc nhiên cho phép HEAD. Nếu cần HEAD, khai báo chính sách riêng và test kết quả.
- `OPTIONS` có thể được dùng cho CORS preflight. Nếu application cần browser cross-origin, CORS phải xử lý preflight đúng, theo allowlist origin/method/headers phù hợp. Không mở `OPTIONS /** permitAll` một cách tự động mà không xem CORS và security chain.
- Những HTTP methods bất thường cũng nên bị từ chối mặc định, không trông cậy chỉ vào controller method mapping.

### 6.2. Query string và path variables

Authorization matcher dựa trên path/method không tự động kiểm tra quyền theo query parameter hoặc ID tài nguyên. Ví dụ:

~~~text
GET /api/orders/123?expand=items
GET /api/orders/999?expand=items
~~~

Cả hai có thể match `GET /api/orders/**`, nhưng user chỉ nên xem đơn hàng thuộc về họ. **HTTP rule là hàng rào đầu; quyền sở hữu dữ liệu phải được kiểm tra ở service/method authorization** dựa trên user, tài nguyên và tenant. Không lấy role chung làm bằng chứng user được xem mọi object.

Khi custom matcher có kiểm tra query/headers, phải xử lý normalization/encoding và security invariants rõ ràng; không tự đoán rằng mọi giá trị URL đã được chuẩn hóa giống nhau ở proxy, framework và ứng dụng.

## 7. Thiết kế bảng quy tắc trước khi viết Java

Một mẫu giúp code review dễ hiểu:

| Method | Path hoặc nhóm route | Đối tượng được phép | Lý do |
| --- | --- | --- | --- |
| GET | `/public/ping` | Ai cũng được | Health-like endpoint demo không có bí mật |
| GET | `/public/catalog/**` | Ai cũng được | Catalog công khai theo chính sách sản phẩm |
| GET | `/api/reports` | `ROLE_READER` | Xem báo cáo |
| GET | `/api/admin/summary` | `ROLE_ADMIN` | Chỉ dành cho quản trị |
| GET | `/api/debug` | **Không ai qua policy HTTP này** | Route tồn tại trong code để minh họa deny mặc định |
| Mọi method khác | Mọi path khác | **Deny** | Không tự động mở endpoint chưa phê duyệt |

Chú ý vùng `/public/catalog/**` là một **quyết định cho phép cả các endpoint hiện tại và tương lai** nằm trong namespace; nó chỉ phù hợp khi tất cả nội dung bên dưới thực sự được phép công khai. Với hệ thống nhạy cảm, cho phép từng path chính xác sẽ an toàn hơn.

Thực hành tốt là liên kết bảng này với ticket/thiết kế API và các test. Khi bổ sung route, developer cần chỉ rõ method, path, role/authority, CSRF/CORS và quyền sở hữu dữ liệu. Không để một wildcard bao trùm biến việc review thành hình thức.

## 8. Ví dụ Java 17+ hoàn chỉnh: WebFlux default deny

Ví dụ sử dụng Java 17, Gradle, Spring Boot 3.5.7, Spring WebFlux và Spring Security Reactive. Nó cố tình chỉ khai báo GET endpoints để tập trung vào authorization và 403/404; CSRF protection vẫn giữ cấu hình mặc định của Spring Security cho những method unsafe.

**Tài khoản demo (chỉ sử dụng local):**
- `reader / localpass` có `ROLE_READER`.
- `admin / adminpass` có `ROLE_ADMIN`.
- Hai role **không bao gồm lẫn nhau**. Một admin trong demo không được tự động truy cập route dành riêng cho READER.

Cấu trúc:

~~~text
webflux-default-deny/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── DefaultDenySecurityTest.java
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-default-deny'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

### 8.3. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/public/catalog/**")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasRole("READER")
                        .pathMatchers(HttpMethod.GET, "/api/admin/summary")
                            .hasRole("ADMIN")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}localpass")
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

Ý nghĩa:
1. Không gọi `securityMatcher(...)` nên chain này có thể match mọi request theo cơ chế mặc định. Trong ví dụ chỉ có **một** security chain.
2. Các rule công khai được liệt kê đầu tiên, có method GET.
3. Route report chỉ yêu cầu `ROLE_READER`; route admin chỉ yêu cầu `ROLE_ADMIN`.
4. `anyExchange().denyAll()` chặn mọi path/method không được khai báo trong rule trước.
5. HTTP Basic được dùng để dễ chạy lệnh curl. Form login bị tắt để phản hồi 401 được quan sát rõ hơn.
6. CSRF vẫn bật mặc định. Không dùng POST thiếu token để chứng minh duy nhất `denyAll`, vì CSRF cũng có thể trả 403.
7. `{noop}` không băm password, **chỉ dành cho local demo**. Production phải dùng PasswordEncoder mạnh, HTTPS, secrets management và cơ chế đăng nhập phù hợp.

**Đừng triển khai tài khoản/password hard-code này lên Internet.** Trong sản phẩm thật, HTTP Basic chỉ an toàn về đường truyền khi dùng HTTPS; Base64 không phải encryption. Nếu dùng JWT, cần Resource Server validation và mapping authorities tương ứng, nhưng authorization rules vẫn áp dụng cùng nguyên tắc.

### 8.5. DemoController.java

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/public/catalog/items")
    public Mono<String> catalog() {
        return Mono.just("catalog");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("report");
    }

    @GetMapping("/api/admin/summary")
    public Mono<String> adminSummary() {
        return Mono.just("admin-summary");
    }

    @GetMapping("/api/debug")
    public Mono<String> debug() {
        return Mono.just("debug-should-not-be-public");
    }
}
~~~

Chú ý `/api/debug` **có handler thật**, nhưng không có rule cho phép. Nó sẽ bị `denyAll()` từ chối trước khi controller chạy. Trái lại, `/public/catalog/missing` không có handler, nhưng nằm dưới phạm vi công khai đã được cho phép; WebFlux sẽ được quyền xử lý và trả 404.

### 8.6. Chạy ứng dụng

Đứng tại thư mục dự án:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, có thể dùng `./gradlew bootRun` trên macOS/Linux hoặc `gradlew.bat bootRun` trên Windows. Mặc định server nghe `localhost:8080`; không mở cổng demo này ra mạng công khai.

Ở terminal khác:

~~~bash
# Công khai đúng route
curl -i http://localhost:8080/public/ping

# Catalog công khai có handler
curl -i http://localhost:8080/public/catalog/items

# Được phép về security nhưng không có handler
curl -i http://localhost:8080/public/catalog/missing

# Route bảo vệ, thiếu credentials
curl -i http://localhost:8080/api/reports

# Đúng role READER
curl -i -u reader:localpass http://localhost:8080/api/reports

# Role READER không phải ADMIN
curl -i -u reader:localpass http://localhost:8080/api/admin/summary

# Đúng role ADMIN
curl -i -u admin:adminpass http://localhost:8080/api/admin/summary

# Route thực sự tồn tại nhưng không được liệt kê trong policy
curl -i -u admin:adminpass http://localhost:8080/api/debug

# Route không tồn tại, cũng không được cho phép bởi policy
curl -i -u admin:adminpass http://localhost:8080/api/ghost

# Admin không tự động là READER
curl -i -u admin:adminpass http://localhost:8080/api/reports
~~~

Kỳ vọng khi sử dụng đúng code và dữ liệu:

| Request | HTTP | Giải thích |
| --- | --- | --- |
| GET `/public/ping` | **200** | Rule public exact; body `pong` |
| GET `/public/catalog/items` | **200** | Namespace public; body `catalog` |
| GET `/public/catalog/missing` | **404** | Security cho đi tiếp, nhưng không có handler |
| GET `/api/reports` không auth | **401** | Có rule yêu cầu READER nhưng chưa xác thực; Basic challenge |
| GET `/api/reports` với reader | **200** | Đủ role; body `report` |
| GET `/api/admin/summary` với reader | **403** | User đã xác thực nhưng không có ADMIN |
| GET `/api/admin/summary` với admin | **200** | Đủ role; body `admin-summary` |
| GET `/api/debug` với admin | **403** | Route có handler nhưng rơi vào default deny |
| GET `/api/ghost` với admin | **403** | Security deny trước khi WebFlux trả 404 |
| GET `/api/reports` với admin | **403** | Admin demo chỉ có ADMIN, không có READER |

**Phần thân JSON lỗi và header cụ thể có thể khác nhau theo phiên bản/cấu hình; các status trên là kỳ vọng của demo.** Trường hợp 404 của URL catalog giả định không có resource/route khác bắt tên đó, đúng với dự án vừa liệt kê.

Không suy luận rằng một route có 403 chứng minh sự tồn tại của controller. Ví dụ `/api/ghost` hoàn toàn không có handler mà vẫn nhận 403 do default deny.

## 9. Kiểm thử WebFlux với WebTestClient

Thử qua curl là bước thực nghiệm, nhưng một thay đổi matcher trong code cần **regression tests** để chặn tình trạng endpoint mới được mở ngoài ý muốn.

Spring Security Test cho Reactive tích hợp với `WebTestClient`. Tạo file:

`src/test/java/demo/DefaultDenySecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class DefaultDenySecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicPingIsAccessibleWithoutAuthentication() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingRouteInsideExplicitlyPublicNamespaceIs404() {
        client.get().uri("/public/catalog/missing")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void readerRouteWithoutAuthenticationIs401() {
        client.get().uri("/api/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerRoleCanReadReports() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "localpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report");
    }

    @Test
    void readerRoleCannotAccessAdminEndpoint() {
        client.get().uri("/api/admin/summary")
                .headers(h -> h.setBasicAuth("reader", "localpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() {
        client.get().uri("/api/admin/summary")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-summary");
    }

    @Test
    void registeredButUnlistedDebugRouteIsDenied() {
        client.get().uri("/api/debug")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownPathIsDeniedBeforeRouterCanReturn404() {
        client.get().uri("/api/ghost")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminRoleDoesNotAutomaticallyIncludeReaderRole() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postIsDeniedEvenWhenCsrfIsPresent() {
        client.mutateWith(csrf())
                .post().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("attempt")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Dự kiến cả nhóm test PASS khi đã tạo đúng các file và dependency. Đây là **kết quả mong đợi từ mã nguồn**, không phải tuyên bố đã chạy Gradle thực tế.

Các test phân biệt ba hiện tượng:
1. **403 dù handler tồn tại** (debug bị default deny).
2. **403 dù handler không tồn tại** (ghost bị default deny).
3. **404 vì handler không tồn tại nhưng security cho phép** (public catalog namespace).

Test POST có `csrf()` là chủ đích: tránh quy 403 cho việc thiếu CSRF token. Khi token hợp lệ mà method POST vẫn bị deny, điều đó cho thấy rule không cho phép method đó. `csrf()` là helper **chỉ dành cho môi trường test**, không phải cách “tắt CSRF” trong sản phẩm thật.

**Không lạm dụng public namespace trong sản phẩm thật chỉ để có test 404.** Namespace public trong demo là một điều kiện được chủ ý cho phép; với hệ thống nhạy cảm, nên liệt kê hẹp những route public thật sự.

## 10. Nếu muốn tách nhiều SecurityWebFilterChain

Khi ứng dụng có hai nhóm authentication, ví dụ:
- `/api/**` dùng Bearer JWT với resource server.
- Web UI dùng form login/session.
- Các route public cần cơ chế khác.

Có thể tạo **nhiều `SecurityWebFilterChain`** để tách authentication mechanism và policy. Điều quan trọng là **Spring Security chọn một chain phù hợp theo thứ tự**, không cộng dồn tất cả các rule của mọi chain.

Ví dụ **một cấu hình thay thế**, không đặt chung với bean `SecurityWebFilterChain` của demo trước:

~~~java
// Trích đoạn minh họa: cần đặt trong @Configuration, có imports và
// authentication/cấu hình JWT thực tế cho từng chain.

@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                    .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET, "/public/ping")
                        .permitAll()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là snippet kiến trúc, **không phải dự án runnable độc lập**. Nó cần imports Spring, OAuth2 Resource Server starter, issuer/JWK/JWT validation, cấu hình CSRF/CORS phù hợp và thiết kế namespace cụ thể. Trong production, không bật HTTP Basic không cần thiết chỉ để có fallback; fallback có thể đơn thuần deny.

Giải thích:
- Chain API có `securityMatcher("/api/**")`, được xét trước.
- Trong chain API, mọi path/method không khớp rule report đều bị `denyAll()`.
- Chain fallback không có `securityMatcher` giới hạn nên nhận những request còn lại; chỉ public ping được phép.
- Nếu một route **không khớp chain API** nhưng khớp fallback, nó chịu **fallback policy**, không chịu anyExchange của API.
- Nếu chỉ tạo chain API mà **không có fallback chain**, request ngoài scope API có thể **không được Spring Security chain đó bảo vệ**. Không coi việc đặt `anyExchange().denyAll()` trong một chain hạn chế phạm vi là chính sách toàn ứng dụng.

### 10.1. Vấn đề ở `/api` và `/api/**`

Các pattern có semantics cụ thể do `PathPatternParser` và matcher áp dụng. Đường dẫn `/api`, `/api/` và `/api/users` không nên được mặc định là luôn có cùng kết quả match với mọi pattern. Hãy test cả các đường dẫn biên và trailing slash phù hợp theo phiên bản.

Đặc biệt, một reverse proxy có thể thêm/bỏ prefix trước khi forward tới WebFlux. Điều developer nhìn thấy bên ngoài (`/gateway/api/users`) có thể khác đường dẫn `ServerWebExchange` thấy bên trong. Cấu hình matcher phải theo **path mà Spring Security thực sự đánh giá**, và proxy không được cho client giả mạo forwarded headers.

### 10.2. @Order là thứ tự chain, không phải thứ tự rule

- `@Order` trên bean chain điều khiển **chain nào được xét trước**.
- Thứ tự các `pathMatchers` trong `authorizeExchange` điều khiển **rule nào áp dụng** bên trong chain đã được chọn.

Đây là hai quy tắc ưu tiên độc lập; sửa sai một cái không tự sửa cái kia. Đừng đặt chain match-all với `@Order(1)` trước chain chỉ cho API, nếu bạn muốn API chain được chọn.

## 11. Các đường dẫn đặc biệt: Actuator, static resources, Swagger, CORS

### 11.1. Actuator và health check

Khi thêm Spring Boot Actuator, endpoint health/metrics có thể có matcher và exposure riêng. Chính sách default deny không tự biết health endpoint có cần public hay chỉ cho monitoring agent.

Không tự thêm:

~~~java
// CÓ RỦI RO: mở rộng cho toàn bộ management endpoints.
.pathMatchers("/actuator/**").permitAll()
~~~

trừ khi đã đánh giá mọi endpoint sẽ được expose, cổng và chính sách quản trị. Thường chỉ có một health/probe endpoint được phép công khai hạn chế, còn metrics/config/env phải được bảo vệ. Nếu dùng management port/context riêng, còn cần xem security chain và network policy của management context.

### 11.2. Static resources và documentation

Một rule `/static/** permitAll` có thể hợp lý nếu toàn bộ files dưới namespace đó là tài nguyên công khai. Nhưng đừng cho phép `/docs/**` hay `/swagger-ui/**` chỉ theo suy nghĩ “tài liệu không có bí mật”; OpenAPI schema có thể tiết lộ endpoint nội bộ hoặc dữ liệu vận hành.

Nếu cho public namespace, phải có **quy tắc quản trị nội dung namespace**: khi thêm route trong phạm vi public, người phát triển hiểu rằng nó đang được cấp quyền công khai.

### 11.3. CORS preflight

Browser cross-origin thường gửi `OPTIONS` với `Origin` và `Access-Control-Request-Method` trước một số request. Nếu CORS được dùng, phải cấu hình CORS để xử lý preflight phù hợp, không chỉ thêm một `pathMatchers("/api/**").permitAll()`.

Một request OPTIONS bị 403 có thể do security fallback, do CORS policy, hoặc do route/matcher. Kiểm thử cả `OPTIONS` đúng origin và origin không được phép. **Cho phép CORS preflight không đồng nghĩa cấp quyền cho request thật**: request GET/POST vẫn phải qua authentication và authorization của chính nó.

### 11.4. Error routes và health proxies

Khi request bị từ chối, error handling có thể đi qua infrastructure/framework handler. Không mở toàn bộ `/error/**` công khai nếu không xác minh framework behavior và nội dung lỗi. Cấu hình API error response có thể trả JSON nhưng không được để stack trace, exception details, SecurityContext hoặc credentials rò ra ngoài.

### 11.5. WebSocket/functional routes

WebFlux có `RouterFunction` và hỗ trợ WebSocket. Cấu hình HTTP authorization cần tính đến HTTP handshake, các route chức năng và quyền ở message/application layer nếu cần. Một `anyExchange().denyAll()` giúp chặn handshake chưa được phê duyệt ở HTTP layer, nhưng không thay message-level authorization hay quyền truy cập business data.

## 12. Tại sao không dùng 404 như hàng rào bảo mật?

Một endpoint trả 404 không tự chứng minh dữ liệu đã được bảo vệ. Ví dụ:
- API không tìm được route vì path sai.
- Security cho phép request nhưng controller không tồn tại.
- Một policy có chủ đích che giấu tài nguyên bằng 404.
- Proxy hoặc upstream service trả 404 trước khi request tới ứng dụng.
- Route tồn tại nhưng app ánh xạ thông báo “không thấy dữ liệu” thành 404.

**Không thể suy luận về authorization chỉ từ một status 404.** Khi kiểm tra security:
1. Thử một endpoint **thực sự tồn tại** nhưng chưa được allowlist.
2. Thử một URL không có handler.
3. Thử URL trong vùng public được allowlist nhưng không có handler.
4. Thử với anonymous và nhiều role khác nhau.
5. Thử các HTTP methods không được khai báo.
6. Kiểm tra chain nào đang match request trước khi suy luận.

Nếu sản phẩm cần giấu sự tồn tại của một tài nguyên khỏi user không có quyền, có thể dùng policy ở service trả 404 thay 403 tùy yêu cầu. Nhưng nội bộ vẫn phải **kiểm tra quyền**; chuyển đổi status đơn thuần không tạo bảo mật.

### 12.1. Đừng tiết lộ đường dẫn qua body lỗi

Dù status là 403/404, không nên trả stack trace, danh sách endpoint nội bộ hay gợi ý “route admin tồn tại, vui lòng nâng cấp quyền” cho người gọi không tin cậy. Dùng cấu trúc response lỗi nhất quán và correlation ID phù hợp. Hệ thống logging nội bộ có thể ghi route template, mã lỗi và loại quyết định để điều tra nhưng phải tránh secrets và thông tin cá nhân không cần thiết.

## 13. Tầng authorization HTTP không thay tầng quyền dữ liệu

Kể cả khi `GET /api/reports` đã require `ROLE_READER`, user A không nhất thiết được xem báo cáo của user B. Khi route có path variable:

~~~text
GET /api/reports/42
GET /api/reports/99
~~~

một matcher `/api/reports/**` chỉ kiểm soát **loại route**, không tự kiểm soát chủ sở hữu từng report. Cần kiểm tra thêm ở service:

~~~java
// Snippet minh họa trong service/controller reactive.
// Chưa phải class chạy độc lập; cần ReportRepository và quyền nghiệp vụ.
return reportRepository.findById(reportId)
        .filter(report -> report.getOwnerId().equals(currentUserId))
        .switchIfEmpty(Mono.error(
                new AccessDeniedException("Not allowed")))
        .map(this::toDto);
~~~

Nếu tenant/user ID lấy từ request parameter, phải đối chiếu với authentication đã được xác minh, không tin giá trị client tự khai. Khi nào trả 403 hoặc 404 cho tài nguyên không sở hữu là quyết định security/API design riêng.

Với Spring Security Reactive, có thể dùng method security reactive hoặc `ReactiveAuthorizationManager` tùy nhu cầu, nhưng authorization ở request layer vẫn nên deny những route chưa được khai báo trước khi controller thực thi.

## 14. Lỗi cấu hình thường gặp

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| `anyExchange().authenticated()` trong hệ thống cần allowlist | Endpoint mới tự mở cho mọi người đã login | Dùng `anyExchange().denyAll()` và rule hẹp |
| `pathMatchers("/api/**").authenticated()` trước ADMIN | Rule tổng quát nuốt rule đặc hiệu | Đặt ADMIN/role cụ thể trước |
| `permitAll()` wildcard quá rộng | Endpoint nội bộ có thể công khai | Cho phép những path/method đã được phê duyệt |
| Chỉ một chain `securityMatcher("/api/**")` và không có fallback | Route ngoài API scope có thể không chịu Spring Security | Tạo catch-all chain có policy mặc định |
| Chain match-all đặt trước chain API | Chain API không được dùng | Dùng `@Order` đúng và test matcher |
| Nghĩ `anyExchange` match mọi URL trên toàn app | Chỉ match phần còn lại **trong chain đã chọn** | Phân biệt chain matcher với rule matcher |
| Muốn URL không tồn tại luôn trả 404 | Security có thể deny trước HandlerMapping | Hiểu ranh giới 403/404, không mở route để sửa status |
| Dùng `hasRole("ADMIN")` nhưng cấp authority `ADMIN` | Quyền không match vì prefix | Thống nhất `ROLE_ADMIN` hoặc dùng `hasAuthority` |
| Chỉ kiểm soát path, quên HTTP method | Một POST/DELETE mới có thể mở theo wildcard | Dùng `pathMatchers(HttpMethod.X, ...)` |
| Dùng `GET` để xóa dữ liệu | CSRF mặc định thường không kiểm tra GET | Đổi semantics và bảo vệ method unsafe |
| Gặp 403 POST thì disable CSRF | Mất một lớp bảo vệ độc lập | Giữ CSRF nếu client/browser cần |
| Cho phép mọi `OPTIONS` vô điều kiện | Có thể mở sai policy hoặc che CORS issue | Xử lý preflight bằng CORS + security |
| Nhầm Servlet `HttpSecurity` với Reactive `ServerHttpSecurity` | Cấu hình không áp đúng WebFlux | Dùng `SecurityWebFilterChain`/`authorizeExchange` |
| Kiểm thử chỉ happy path 200 | Bỏ sót wildcard và endpoint quên đăng ký | Test 401/403/404 + route/method mới |
| Xem ADMIN như role siêu quyền mặc định | Có thể cấp sai quyền nhóm khác | Xác định role hierarchy explicitly nếu cần |
| Tự catch `AccessDeniedException` thành 200 | Bỏ qua chặn access control | Trả HTTP lỗi đúng và quan sát nội bộ |

**Không sửa 403 bằng cách mở rộng `permitAll` cho tới khi test xanh.** Trước hết kiểm tra chain, matchers, authentication và rule cụ thể.

## 15. Quy trình code review / security QA

Một checklist thực dụng:

- [ ] Viết bảng các HTTP methods, paths và roles/authorities dự kiến.
- [ ] Có `anyExchange().denyAll()` ở cuối các chain cần allowlist.
- [ ] Không có wildcard `permitAll()` rộng hơn chính sách.
- [ ] Rule đặc hiệu có ưu tiên trước rule tổng quát.
- [ ] Đã kiểm tra `hasRole` vs `hasAuthority` và prefix/claims mapping.
- [ ] Nếu có nhiều chains, `@Order` và `securityMatcher` không để lộ route ngoài phạm vi.
- [ ] Có catch-all security chain hoặc cơ chế bảo vệ phù hợp cho phần còn lại.
- [ ] Đã test `/api`, `/api/`, trailing slash, prefix, path variables và URL encoding cần thiết.
- [ ] Các method GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS được kiểm soát theo policy.
- [ ] GET/HEAD không gây side effects; CSRF/CORS được đánh giá độc lập.
- [ ] Actuator, docs, static assets, health check có allowlist riêng khi cần.
- [ ] Đã test ít nhất một route **có controller nhưng bị deny**.
- [ ] Đã test một URL **không có controller và bị deny**.
- [ ] Đã test một URL **được security cho phép nhưng không có handler**.
- [ ] Đã test anonymous, đúng role, sai role, và credential không hợp lệ.
- [ ] Đã xem network/route do reverse proxy và load balancer nhìn thấy.
- [ ] Rule HTTP không thay kiểm tra quyền sở hữu object/multi-tenant trong service.
- [ ] Error response không rò secrets, stack trace hay inventory endpoint nhạy cảm.

### 15.1. Kịch bản regression khi thêm endpoint

Giả sử một developer thêm:

~~~java
@GetMapping("/api/export/all")
public Mono<String> exportAll() {
    return Mono.just("sensitive-export");
}
~~~

Đoạn này là snippet minh họa. Với cấu hình default deny ở bài, endpoint mới sẽ bị từ chối ngay, không vì người dùng đã login mà tự có quyền. Để mở nó một cách có chủ đích, developer phải:
1. Xác định ai được xem export.
2. Quy định HTTP method và path cụ thể.
3. Thêm rule có quyền phù hợp **trước `anyExchange().denyAll()`**.
4. Viết test cho người được phép và người không được phép.
5. Kiểm tra dữ liệu export có phân quyền theo tenant/user hay không.

Đó là giá trị vận hành của default deny: một thay đổi API không âm thầm mở rộng quyền cho các nhóm user cũ.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `anyExchange().authenticated()` và `anyExchange().denyAll()` khác nhau thế nào?

> Cái đầu cho phép mọi request còn lại nếu đã xác thực, cái sau từ chối mọi request còn lại bất kể role.

**Câu 2.** Nếu `pathMatchers("/api/**").authenticated()` đứng trước `/api/admin/** hasRole("ADMIN")` thì chuyện gì có thể xảy ra?

> Request admin match rule tổng quát trước và bỏ qua rule ADMIN, dẫn tới kiểm soát quá rộng.

**Câu 3.** Một URL không có controller có thể trả 403 không?

> Có. Authorization default deny có thể từ chối trước khi WebFlux xác định route không tồn tại.

**Câu 4.** Một URL dưới `/public/catalog/** permitAll` không có controller thường trả gì?

> 404, vì security cho đi tiếp nhưng WebFlux không tìm được handler.

**Câu 5.** Nếu có chain chỉ match `/api/**` và trong đó `anyExchange().denyAll()`, route `/admin/secret` có được bảo vệ bởi rule đó không?

> Không. Rule đó chỉ hoạt động trong chain đã chọn. Cần fallback chain hoặc cơ chế bảo vệ độc lập cho route khác.

**Câu 6.** `@Order` và thứ tự `pathMatchers` có giống nhau không?

> Không. `@Order` quyết định chain được xét trước; thứ tự pathMatchers quyết định rule áp dụng bên trong chain.

**Câu 7.** Role ADMIN có tự động match `hasRole("READER")` không?

> Không, trừ khi authentication cấp cả hai authorities hoặc tổ chức cấu hình role hierarchy tương ứng.

**Câu 8.** Vì sao `GET /api/orders/123` cần thêm object-level check dù HTTP rule match?

> Rule HTTP cho phép loại chức năng; nó không xác nhận user sở hữu order ID 123.

**Câu 9.** Nếu POST chưa có CSRF token trả 403, có chứng minh default deny đang hoạt động không?

> Chưa. CSRF filter cũng có thể tạo 403; test có token hợp lệ hoặc dùng GET để tách nguyên nhân.

**Câu 10.** Vì sao không cho phép `/actuator/**` công khai chỉ để health check hoạt động?

> Vì wildcard có thể bao gồm endpoint quản trị/metrics nhạy cảm và các endpoint mới sau này.

**Câu 11.** Tại sao status 404 không phải bằng chứng endpoint được bảo vệ?

> 404 có thể do WebFlux không tìm thấy handler hoặc proxy trả về; phải kiểm thử một endpoint có handler thật và kiểm tra chain/rule.

**Câu 12.** Một API có GET được phép nhưng HEAD không được khai báo trong matcher. Có nên giả định HEAD cũng được phép?

> Không. HEAD là một HTTP method khác; cần chính sách explicit và test nếu muốn hỗ trợ.

## 17. Kết luận

Một chính sách phân quyền HTTP an toàn trong Spring Security Reactive nên vận hành theo nguyên tắc:

~~~text
Chọn security chain đúng phạm vi
      |
Xét rule đặc hiệu theo HTTP method + path
      |
Cho phép tối thiểu đúng vai trò/authority
      |
Không khớp rule đã phê duyệt --> DENY
      |
Chỉ những request được cho phép mới tới WebFlux router
~~~

Cấu hình điển hình:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("READER")
        .pathMatchers(HttpMethod.GET, "/api/admin/summary").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Nên nhớ:
- `denyAll()` không phải “yêu cầu đăng nhập” mà là “không cho phép”.
- Một URL không tồn tại có thể trả **403 trước 404**.
- `anyExchange()` chỉ áp dụng bên trong **SecurityWebFilterChain đã match**.
- HTTP method và thứ tự rule quan trọng không kém path.
- CORS, CSRF, method security và object-level authorization là những lớp bổ sung, không được bỏ chỉ vì đã có default deny.
- Quy tắc deny-by-default chỉ phát huy tác dụng khi được kiểm thử cho cả đường dẫn **đã đăng ký**, **chưa đăng ký** và **không nằm trong security matcher**.

### Tài liệu chính thức

- Spring Security Reference — Authorize ServerHttpRequest (WebFlux): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security Reference — WebFlux Security / Multiple Chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security Javadoc — ServerHttpSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Reference — Testing Authentication in WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security Reference — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Framework Reference — WebFlux Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html