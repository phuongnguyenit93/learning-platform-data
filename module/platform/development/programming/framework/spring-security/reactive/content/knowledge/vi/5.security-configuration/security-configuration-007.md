# Phân biệt permitAll với bỏ qua toàn bộ chuỗi bảo mật trong Spring Security WebFlux

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích chính xác `permitAll()` trong `authorizeExchange(...)` có nghĩa là **cho phép truy cập theo quy tắc phân quyền HTTP**.
- Phân biệt việc **một request đã được chọn vào `SecurityWebFilterChain`** với việc **một quy tắc authorization cho phép request đó**.
- Hiểu vì sao endpoint `permitAll()` vẫn có thể chạy các WebFilter xác thực, CSRF, security headers, CORS và các cơ chế khác đã cấu hình; thậm chí vẫn có thể trả `401`/`403`.
- Nhận ra trường hợp một URL **không khớp bất kỳ `SecurityWebFilterChain` nào** và hệ quả khi toàn bộ các bộ lọc nội bộ của Spring Security không áp dụng cho URL đó.
- Viết cấu hình Java 17+ cho endpoint công khai an toàn, phân chia nhiều chuỗi bằng `securityMatcher(...)`, và kiểm thử được sự khác biệt qua HTTP.

> **Phạm vi:** Spring Security **reactive** dùng Spring WebFlux và `ServerHttpSecurity`. Các API Servlet như `HttpSecurity`, `SecurityFilterChain` và `WebSecurityCustomizer.ignoring()` là một mô hình khác; không sao chép trực tiếp cú pháp hoặc kỳ vọng của Servlet sang WebFlux.

## 1. Hai quyết định tách biệt: chọn chuỗi và phân quyền

Có hai tầng logic cần phân biệt khi một HTTP request đi qua Spring Security WebFlux.

**Tầng A — Chọn chuỗi bảo mật.** `WebFilterChainProxy` của Spring Security tìm `SecurityWebFilterChain` phù hợp với request bằng matcher của chuỗi, thường được cấu hình qua `http.securityMatcher(...)`. Khi có nhiều bean `SecurityWebFilterChain`, Spring Security xem xét chúng theo thứ tự và chọn **chuỗi khớp đầu tiên**. Nếu có một chuỗi bắt tất cả `anyExchange`/matcher mặc định, các request chưa khớp chuỗi cụ thể vẫn đi qua chuỗi dự phòng đó.

**Tầng B — Quyết định truy cập HTTP bên trong chuỗi đã chọn.** Bộ lọc authorization áp dụng các quy tắc của `http.authorizeExchange(...)`. Một quy tắc `pathMatchers("/public/**").permitAll()` nói rằng request khớp đường dẫn đó **không cần được chấp thuận dựa trên việc đã đăng nhập hoặc role** để qua bước authorization tương ứng.

Hai tầng khác nhau về mục đích và vị trí:

~~~text
HTTP request
  |
  v
WebFlux và các WebFilter của ứng dụng
  |
  v
Spring Security WebFilterChainProxy
  |
  +-- Có SecurityWebFilterChain khớp? -- KHÔNG --> Không chạy filter nội bộ của
  |                                            SecurityWebFilterChain nào
  |                                            (nhưng WebFilter khác vẫn chạy)
  |
  CÓ
  |
  v
Các filter trong SecurityWebFilterChain được chọn
  |-- SecurityContext / xác thực (nếu cấu hình)
  |-- CSRF / các header bảo mật / xử lý lỗi (nếu cấu hình)
  |-- AuthorizationWebFilter
         |
         +-- Quy tắc permitAll() --> authorization cho phép
         +-- authenticated() ----> yêu cầu đã xác thực
         +-- hasRole(...) -------> kiểm tra quyền
         +-- denyAll() ----------> authorization từ chối
  |
  v
Handler / controller (nếu không có filter chặn trước đó)
~~~

Sơ đồ khái niệm; trình tự chính xác và các filter xuất hiện phụ thuộc cấu hình Spring Security. Điều cốt lõi là **`permitAll()` thuộc tầng B, không hủy tầng A**.

## 2. permitAll() thực sự cho phép điều gì?

Ví dụ:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**", "/login").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là một method cấu hình minh họa, đặt trong class cấu hình Spring; cần import `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer` và `@Bean`. Giả sử chuỗi này khớp mọi request (không giới hạn bằng `securityMatcher`):

- `GET /public/info` không cần người dùng đã đăng nhập để vượt quy tắc authorization.
- `GET /admin/audit` cần `ROLE_ADMIN` (`hasRole("ADMIN")` áp dụng tiền tố `ROLE_` mặc định).
- Các đường dẫn còn lại cần `Authentication` đáp ứng `authenticated()`.
- **Không có đường dẫn nào bị loại khỏi chuỗi bảo mật chỉ vì `permitAll()`.**

Những điều `permitAll()` **không khẳng định**:

1. Không hứa request luôn trả `200 OK`. Controller vẫn có thể trả `404`, `400`, lỗi khác, hoặc security filter khác có thể từ chối trước authorization.
2. Không tự tắt `CsrfWebFilter`. Một `POST` ở route công khai vẫn có thể bị `403` nếu CSRF được bật và thiếu token hợp lệ.
3. Không vô hiệu hóa bộ lọc xác thực đã bật (HTTP Basic, bearer token, v.v.). Nếu client **chủ động gửi credential sai**, một authentication filter phù hợp có thể xử lý thất bại và trả `401` ngay cả khi URL được `permitAll()`.
4. Không tự tắt response headers bảo mật như `X-Content-Type-Options: nosniff` hoặc `X-Frame-Options: DENY`.
5. Không đảm bảo trả về một principal cụ thể. Endpoint công khai có thể chạy không có người dùng đăng nhập; nếu có credential hợp lệ và cơ chế authentication xử lý nó, principal có thể được thiết lập.
6. Không bỏ qua security ở **tầng method**. Nếu bật reactive method security, một method có `@PreAuthorize(...)` vẫn có thể bị từ chối theo quy tắc đó, kể cả URL được `permitAll()`.

**Câu ngắn cần nhớ:** `permitAll()` bỏ yêu cầu authorization cho URL ở quy tắc tương ứng; request vẫn được xử lý trong chuỗi security đã chọn.

## 3. Thế nào là “bỏ qua toàn bộ chuỗi bảo mật”?

Trong WebFlux, một tình huống đáng chú ý là **request không khớp với bất kỳ bean `SecurityWebFilterChain` nào**. Khi đó `WebFilterChainProxy` không có chuỗi Spring Security nội bộ để áp dụng cho request ấy.

Ví dụ chỉ minh họa matcher ở cấp chuỗi:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/open").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Cần import `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher`. Nếu đây là **SecurityWebFilterChain duy nhất** trong ứng dụng:

- `/api/open`: khớp chuỗi `/api/**` rồi qua authorization với `permitAll()`; các filter khác của chuỗi vẫn có thể chạy.
- `/api/private`: khớp chuỗi `/api/**`; cần authenticated.
- `/public-outside`: không khớp `/api/**`; **không có SecurityWebFilterChain nội bộ được chọn**.

Nếu ứng dụng còn một bean khác khớp mọi request, ví dụ chuỗi mặc định không có `securityMatcher` giới hạn, `/public-outside` **sẽ đi qua chuỗi đó**. Vì vậy không thể kết luận một path “bỏ qua security” chỉ bằng cách thấy nó không khớp matcher của một chuỗi cụ thể.

Lưu ý khác biệt phạm vi: những `WebFilter` của WebFlux nằm **ngoài** `SecurityWebFilterChain` (custom filter, gateway filter, xử lý CORS ở tầng khác, v.v.) vẫn có thể chạy. Method security và những bộ kiểm soát ở tầng khác cũng không tự biến mất. “Bỏ qua toàn bộ chuỗi bảo mật” ở đây chỉ đúng với **các filter bên trong chuỗi Spring Security không được chọn**, không phải bỏ qua mọi phần mềm trung gian hay mọi quy tắc bảo mật của hệ thống.

## 4. Bảng so sánh ba trường hợp

| Câu hỏi | Route trong chuỗi với `permitAll()` | Route được chuỗi Spring Security khác xử lý | Route không khớp **bất kỳ** SecurityWebFilterChain |
|---|---|---|---|
| Có `SecurityWebFilterChain` được chọn? | Có | Có, theo `securityMatcher` và `@Order` | Không |
| Quy tắc authorization HTTP | Cho phép theo `permitAll()` | Theo quy tắc của chuỗi khác | Không có authorization filter của SecurityWebFilterChain |
| Authentication filter của Spring Security | Có thể chạy nếu được cấu hình | Tùy chuỗi được chọn | Không có filter authentication từ các chuỗi không khớp |
| CSRF do Spring Security | Vẫn có thể áp dụng cho request không an toàn | Tùy cấu hình chuỗi | Không áp dụng từ các chuỗi không khớp |
| Security response headers do Spring Security | Vẫn có thể được thêm | Tùy cấu hình chuỗi | Không do filter của chuỗi không khớp thêm; thành phần khác vẫn có thể thêm |
| Xử lý 401/403 của Spring Security | Có thể xảy ra từ các filter còn hoạt động | Tùy cấu hình | Không từ chuỗi nội bộ không được chọn; tầng khác vẫn có thể từ chối |
| WebFilter khác của ứng dụng | Vẫn chạy theo thứ tự | Vẫn chạy theo thứ tự | Vẫn có thể chạy |
| Kết luận | **Endpoint công khai nhưng còn lớp bảo vệ chung** | **Một chính sách bảo mật khác** | **Có nguy cơ tạo vùng không được Spring Security bảo vệ** |

Không xem việc endpoint có hoặc không có `Authentication` là phép đo duy nhất: với `permitAll()`, authentication không bắt buộc cho quyết định authorization, nhưng cơ chế xác thực được cấu hình vẫn có thể hoạt động.

## 5. securityMatcher(...) khác pathMatchers(...).permitAll() như thế nào?

### 5.1. `securityMatcher(...)` quyết định chuỗi được chọn

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

Đây là điều kiện **ở cấp SecurityWebFilterChain**. Request `/api/products` thuộc phạm vi chuỗi. Request `/docs/index.html` không thuộc phạm vi chuỗi đó, song có thể khớp chuỗi khác.

### 5.2. `pathMatchers(...).permitAll()` quyết định truy cập bên trong chuỗi

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated());
~~~

Các rule này được đánh giá **sau khi chuỗi tương ứng đã được chọn**. Chúng không tạo thêm `SecurityWebFilterChain` và cũng không đẩy request ra khỏi chuỗi hiện tại.

### 5.3. Thứ tự quan trọng ở cả hai tầng

- **Giữa nhiều SecurityWebFilterChain**: sắp xếp bean bằng `@Order`; Spring Security chọn chuỗi khớp đầu tiên. Chuỗi matcher rộng đặt trước có thể che mất chuỗi hẹp.
- **Giữa các authorization matcher trong cùng một chuỗi**: luật cụ thể cần đặt trước luật bao quát. `anyExchange()` đặt cuối.
- Nếu chỉ có chuỗi `/api/**` mà quên chuỗi dự phòng, các route không khớp có thể không được bảo vệ bởi Spring Security. Đây là lỗi cấu hình nghiêm trọng khi về sau thêm endpoint mới.

**Cạm bẫy:** Hai bean `SecurityWebFilterChain` không tự động “cộng dồn” filter cho một request. Spring Security chọn chuỗi phù hợp đầu tiên, không thực thi tuần tự tất cả các chuỗi phù hợp.

## 6. Bài thực hành Java 17+: nhìn sự khác biệt qua HTTP

Ví dụ nhỏ này cố ý có **một chuỗi chỉ khớp `/api/**`** để lộ ra ba hành vi: (a) `permitAll` trong chuỗi, (b) URL yêu cầu đăng nhập, (c) URL nằm ngoài mọi chuỗi. Đường dẫn ngoài chuỗi tồn tại **chỉ để quan sát**, không phải cấu hình khuyến nghị cho production.

Dùng Spring Boot `3.3.5` và Java 17. Các phiên bản dependency Spring Security và Reactor được quản lý qua Spring Boot BOM.

### 6.1. Cấu trúc dự án

~~~text
permitall-webflux-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/PermitAllWebFluxDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'permitall-webflux-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

`src/main/java/example/PermitAllWebFluxDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class PermitAllWebFluxDemo {

    public static void main(String[] args) {
        SpringApplication.run(PermitAllWebFluxDemo.class, args);
    }

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            // Chọn duy nhất các request dưới /api/.
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/public-post").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // Cố ý giữ CSRF mặc định để quan sát với POST.
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Chỉ để chạy demo ở localhost.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicGet() {
            return Mono.just(Map.of("access", "public"));
        }

        @PostMapping("/api/public-post")
        Mono<Map<String, String>> publicPost() {
            return Mono.just(Map.of("access", "public-post"));
        }

        @GetMapping("/api/private")
        Mono<Map<String, String>> privateGet(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "access", "private",
                    "username", principal.getName()));
        }

        @GetMapping("/outside")
        Mono<Map<String, String>> outsideGet() {
            return Mono.just(Map.of("access", "outside"));
        }
    }
}
~~~

**Giải thích cấu hình:**

- `securityMatcher("/api/**")` giới hạn **toàn bộ chuỗi** vào nhóm URL `/api/`.
- `permitAll()` cho GET `/api/public` và POST `/api/public-post` chỉ ảnh hưởng đến authorization. Các filter trong chuỗi `apiChain` vẫn còn, bao gồm CSRF mặc định của Spring Security.
- `anyExchange().authenticated()` bảo vệ các API khác, ví dụ `/api/private`.
- `/outside` không khớp chuỗi `/api/**`. Do demo không có SecurityWebFilterChain dự phòng, endpoint này được WebFlux xử lý nhưng **không có filter bảo mật của chuỗi `apiChain`**.
- Method nhận `ServerWebExchange` để lấy principal trên route private; không lấy người dùng từ header tùy ý.

### 6.2. Lệnh chạy

Trong thư mục `permitall-webflux-demo`, cần JDK 17+ và Gradle phù hợp (hoặc Gradle Wrapper do bạn tạo):

~~~bash
gradle bootRun
~~~

Nếu có wrapper: Linux/macOS dùng `./gradlew bootRun`, Windows dùng `gradlew.bat bootRun`. Sau khi ứng dụng đã khởi động, ở terminal khác:

~~~bash
# 1. URL public nhưng vẫn nằm trong security chain
curl -i http://localhost:8080/api/public

# 2. URL yêu cầu Authentication
curl -i http://localhost:8080/api/private

# 3. URL yêu cầu Authentication với credential hợp lệ
curl -i -u learner:demo-pass http://localhost:8080/api/private

# 4. URL permitAll nhưng là POST, thiếu CSRF token
curl -i -X POST http://localhost:8080/api/public-post

# 5. URL nằm ngoài matcher của chain duy nhất
curl -i http://localhost:8080/outside

# 6. Thử gửi credential Basic sai tới URL public
curl -i -u learner:sai-mat-khau http://localhost:8080/api/public
~~~

Lưu ý: trên Windows PowerShell, nếu `curl` là alias của công cụ khác, hãy dùng `curl.exe`. Với Boot đang chạy port 8080 mặc định và không có cấu hình ngoài làm thay đổi security, các kết quả kỳ vọng:

| Request | Status kỳ vọng | Ý nghĩa |
|---|---|---|
| `GET /api/public`, không credential | `200` | Authorization `permitAll`; security headers do chuỗi thêm vẫn quan sát được, ví dụ `X-Content-Type-Options: nosniff`. |
| `GET /api/private`, không credential | `401` | Bước authorization cần Authentication; HTTP Basic entry point tạo challenge. |
| `GET /api/private`, Basic đúng | `200` | Authentication hợp lệ, body JSON chứa `"username":"learner"`. |
| `POST /api/public-post`, không CSRF token | `403` | `permitAll` không tắt `CsrfWebFilter`; thiếu token trên HTTP method có khả năng thay đổi trạng thái. |
| `GET /outside` | `200` | Endpoint tồn tại, nhưng không khớp SecurityWebFilterChain duy nhất. Không có security headers **do chuỗi ấy tạo**; thành phần ngoài chuỗi có thể thêm header của riêng mình. |
| `GET /api/public`, Basic sai | Có thể `401` với cấu hình Basic này | Authentication filter nhận credential Basic và xử lý thất bại dù authorization URL là `permitAll`. |

Ví dụ body thành công của `GET /api/public` là:

~~~json
{"access":"public"}
~~~

`GET /api/private` với credential hợp lệ trả đối tượng JSON có `access=private` và `username=learner`; thứ tự field trong JSON không được bảo đảm. Kết quả của `curl -i` là HTTP header/body, **không phải stdout cố định của chương trình Java**; port, server log, các header động và thời gian phản hồi có thể thay đổi. Dùng HTTP status và header có chủ đích làm phép kiểm chứng.

**Giới hạn bảo mật của demo:** Tài khoản dùng `{noop}` và mật khẩu tĩnh chỉ phục vụ học trên localhost. Không dùng ngoài môi trường thử nghiệm. Triển khai thật cần password encoder phù hợp, quản lý secret và HTTPS. Không coi đường dẫn `/outside` là cấu hình an toàn; mục 7 giải thích cách sửa.

## 7. Cấu hình nên dùng trong ứng dụng thực

### 7.1. Phương án phổ biến: một chuỗi bao phủ mọi URL, permitAll cho public

Trong bài thực hành trên, thay bean `apiChain` bằng một bean không giới hạn `securityMatcher`:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public", "/outside")
                .permitAll()
            .pathMatchers(HttpMethod.POST, "/api/public-post")
                .permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
~~~

Đây là **method thay thế** cho bean trong demo, không đặt đồng thời cả hai method. Các import và controller giữ nguyên. Vì matcher cấp chuỗi mặc định bao trùm mọi URL, `/outside` lúc này là **public trong security chain**, nên vẫn được filter bảo mật tương ứng xử lý. Luật `permitAll` ở POST **vẫn không mặc nhiên gỡ yêu cầu CSRF**.

Ưu điểm: các endpoint công khai vẫn nhận các cơ chế bảo vệ chung; endpoint mới chưa khai báo public mặc định phải authenticated. Khi yêu cầu bảo vệ khác nhau sâu hơn giữa API và website, có thể sử dụng nhiều chuỗi.

### 7.2. Phương án nhiều chuỗi: cấu hình khác nhau, vẫn có chuỗi dự phòng

Các đoạn sau là **ví dụ cấu hình tích hợp** trong một class có bean Spring, không dùng đồng thời với `apiChain` của bài demo:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/health").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
~~~

Cần import `org.springframework.core.annotation.Order` và các import từ ví dụ trước. Nếu muốn dùng controller `/outside` làm public trong fallback, hãy khai báo rõ ràng ở fallback bằng `pathMatchers(...).permitAll()`; đoạn trên cố ý để `/outside` yêu cầu authentication để minh họa bảo vệ mặc định.

Quy tắc chọn chuỗi:

- `/api/public` và `/api/private` khớp chuỗi `@Order(1)`.
- `/health` hoặc `/outside` không khớp `/api/**` nhưng khớp chuỗi thứ hai (matcher mặc định của nó phù hợp mọi request).
- `/health` trong fallback được `permitAll` nhưng vẫn đi qua **chuỗi fallback**, khác với bị bỏ mặc không có chuỗi nào.

Tránh đặt chuỗi bao quát lên trước chuỗi hẹp; nó sẽ bắt cả `/api/**`, làm cấu hình chain API bị che. Không giả định framework tự chọn matcher cụ thể nhất bất kể thứ tự.

### 7.3. Khi nào mới thực sự muốn không có SecurityWebFilterChain?

Trường hợp này cần quyết định kiến trúc chủ động và đánh giá rủi ro, chẳng hạn một vùng tài nguyên tĩnh hoàn toàn công khai đã có một lớp security gateway thực sự bảo vệ và toàn bộ header security cần thiết được cấu hình ở tầng khác. Dẫu vậy, chỉ vì endpoint cần public **không phải lý do đủ tốt** để loại nó khỏi chuỗi.

Đặc biệt tránh bỏ chuỗi cho `/api/admin/**`, endpoint chứa dữ liệu người dùng, actuator/management endpoint, route ghi dữ liệu, hoặc đường dẫn mới thêm chưa được review. Một URL không khớp mọi SecurityWebFilterChain có thể thiếu cả authorization filter, authentication filter và các security headers mặc định của Spring Security.

## 8. Các lớp bảo vệ vẫn có ý nghĩa khi permitAll

### 8.1. CSRF độc lập với authorization

CSRF bảo vệ request có khả năng thay đổi trạng thái trong các kịch bản trình duyệt tự gửi credential (như cookie/session). Mặc định Spring Security WebFlux bật bảo vệ CSRF; rule `permitAll` không tự vô hiệu hóa nó. Một route `POST /signup` dù công khai vẫn có thể cần token CSRF nếu mô hình ứng dụng dùng cookie/session.

Nếu API được xác thực hoàn toàn bằng bearer token không tự động gửi bởi trình duyệt và **không dựa vào cookie/session** cho các request thay đổi trạng thái, có thể đánh giá việc điều chỉnh CSRF. Đừng tự tắt CSRF trên toàn ứng dụng chỉ để một `POST` public chạy được; cân nhắc threat model, matcher CSRF chính xác và cách client cung cấp token.

### 8.2. Authentication có thể thất bại trước bước permitAll

`permitAll` nghĩa là authorization không đòi authentication. Nó không ngăn một `AuthenticationWebFilter` đã cấu hình kiểm tra credential do client chủ động gửi. Ví dụ header `Authorization: Basic ...` sai có thể tạo phản hồi `401`. Vì vậy test `GET /public` không credential **khác** với test cùng URL nhưng gửi credential sai.

Điều này cũng có nghĩa endpoint công khai không nên tự rút dữ liệu người dùng bằng `SecurityContextHolder` kiểu Servlet. Trong reactive, dùng `ReactiveSecurityContextHolder`/principal theo đúng subscription và xử lý trường hợp không có Authentication.

### 8.3. Security headers và CORS

Nếu chuỗi đang được áp dụng và headers không bị tắt, Spring Security thường thêm các header bảo vệ như `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` và cache-control. `Strict-Transport-Security` chỉ áp dụng trên HTTPS theo cấu hình hỗ trợ. `permitAll` không phải lệnh tắt các header đó.

CORS là chính sách trình duyệt có phần cấu hình riêng; `permitAll` không tự cấu hình `Access-Control-Allow-Origin` và không có nghĩa mọi preflight đều thành công. Nếu dùng Spring Security CORS integration hoặc WebFlux CORS, hãy cấu hình origin/method/header thật sự được phép. Đừng dùng `permitAll` làm cách sửa mọi lỗi CORS.

### 8.4. Security context và session

Cơ chế nạp/lưu `SecurityContext` phụ thuộc cấu hình repository và authentication. Với public endpoint, không nên buộc phải có principal, nhưng một người dùng gửi credential hợp lệ có thể được xác thực. `permitAll` không tương đương “luôn anonymous”, và cũng không nhất thiết kích hoạt tải toàn bộ session ở mọi request. Điều nào xảy ra cần kiểm tra theo version/cấu hình đã dùng, thay vì suy đoán từ tên quy tắc authorization.

### 8.5. Method security có thể giữ hàng rào bổ sung

Với reactive method security đã bật, method được đánh dấu `@PreAuthorize("hasRole('ADMIN')")` có thể từ chối lời gọi ngay cả khi URL được `permitAll`. Điều này **không thay thế** cho HTTP-level security chain: các bảo vệ CSRF/headers/authentication ở HTTP và method authorization phục vụ trách nhiệm khác nhau. Khi thiếu chuỗi security, cũng có thể thiếu principal/Authentication cần thiết để method policy hoạt động như mong muốn.

## 9. Các sai lầm hay gặp và cách sửa

**Sai lầm 1 — Viết `permitAll()` để “tắt Spring Security” cho static resources.** Kết quả là route vẫn qua chuỗi, còn một số người lại cố loại chuỗi vì tưởng đó là cách đúng. Thông thường hãy để tài nguyên công khai trong chuỗi và permit các URL cần thiết; security headers vẫn hữu ích cho static content.

**Sai lầm 2 — Tưởng `securityMatcher` và `pathMatchers` giống nhau.** Một cái **chọn chuỗi**; một cái **chọn rule authorization trong chuỗi**. Đặt `securityMatcher("/api/**")` mà không có fallback sẽ làm đường dẫn khác nằm ngoài phạm vi mọi chain.

**Sai lầm 3 — Dùng ví dụ Servlet `web.ignoring()` trong WebFlux.** Đó là API của kiến trúc Servlet, không phải cách cấu hình `ServerHttpSecurity` reactive. Với WebFlux, phải lý giải bằng `SecurityWebFilterChain` và `ServerWebExchangeMatcher`.

**Sai lầm 4 — Cho rằng `permitAll` bảo đảm mọi request trả 200.** CSRF, authentication failure, handler error, HTTP method mismatch hay các filter khác đều có thể tạo kết quả khác. Đọc log đúng component và test từng cơ chế.

**Sai lầm 5 — Đặt fallback `anyExchange().authenticated()` trước rule public.** Matcher rộng hơn có thể bắt request trước khi tới rule public, dẫn đến `401`. Đặt rule cụ thể trước `anyExchange`.

**Sai lầm 6 — Đặt chain catch-all ở `@Order(1)` và chain API ở `@Order(2)`.** Chain tổng quát bắt mọi request trước; chain API không được chọn. Đặt chain có `securityMatcher` hẹp lên trước và catch-all cuối.

**Sai lầm 7 — Chỉ test URL trống credential.** Cần test cả credential hợp lệ, credential sai, CSRF và các trường hợp `GET`/`POST`. `permitAll` của authorization không khiến lỗi authentication/CSRF biến mất.

**Sai lầm 8 — Coi không thấy header security là “tắt được authentication”.** Bảo vệ HTTP có nhiều phần. Đánh giá trạng thái matching chain, rule authorization, security headers, CSRF, authentication và method security riêng rẽ.

**Sai lầm 9 — Bỏ mặc endpoint mới ngoài matcher.** Endpoint mới nằm ngoài `/api/**` và không có fallback có thể được truy cập công khai mà không có security filters. Nên test toàn bộ nhóm URL và có catch-all policy rõ ràng.

## 10. Bài tập kiểm thử và checklist review

### 10.1. Checklist theo hai tầng

Khi review một endpoint `/x`, trả lời theo thứ tự:

1. Có bao nhiêu bean `SecurityWebFilterChain`? Thứ tự `@Order` của chúng là gì?
2. Chuỗi **đầu tiên khớp `/x`** theo `securityMatcher` là chuỗi nào? Nếu không có, đã có một security gap.
3. Trong chuỗi được chọn, `pathMatchers`/`anyExchange` khớp rule nào? Đó là `permitAll`, `authenticated`, role hay `denyAll`?
4. Những filter authentication/CSRF/headers/exception handling nào thực sự bật trong chuỗi ấy?
5. Nếu URL là public POST, CSRF token có được cung cấp theo mô hình xác thực và rủi ro CSRF của ứng dụng không?
6. Có policy method-level hoặc upstream gateway nào liên quan? Chúng không mặc nhiên thay thế cấu hình Spring Security HTTP.
7. Test `GET` công khai, `GET` cần đăng nhập, credential sai, `POST` không token, và URL nằm ngoài matcher như thế nào?

### 10.2. Câu hỏi tự đánh giá có đáp án

**Câu 1.** Cấu hình có một chuỗi `securityMatcher("/api/**")`, bên trong `pathMatchers("/api/health").permitAll()`. `GET /api/health` có bỏ qua security filter chain không?

**Đáp án:** Không. Nó khớp chuỗi `/api/**` và được cho qua bước authorization theo `permitAll`; các filter còn lại của chuỗi vẫn có thể chạy.

**Câu 2.** Với đúng một chuỗi matcher `/api/**`, `GET /docs` không khớp. `GET /docs` có mặc nhiên bị Spring Security từ chối không?

**Đáp án:** Không. Nếu không có `SecurityWebFilterChain` nào khác khớp, các filter nội bộ của Spring Security không áp dụng cho URL đó. Controller/resource handler có thể trả nội dung; cơ chế ngoài chuỗi vẫn có thể tác động.

**Câu 3.** Tại sao `POST /signup` được `permitAll()` nhưng trả 403?

**Đáp án:** Một nguyên nhân thường gặp là filter CSRF đang bật và request thiếu token phù hợp. Phải xác định filter gây từ chối từ log/test; không tự kết luận chỉ từ status 403. `permitAll` không tắt CSRF.

**Câu 4.** Nếu ứng dụng có hai chuỗi: `@Order(1)` matcher `/api/**` và `@Order(2)` matcher mặc định tất cả, `GET /docs` có bỏ qua chuỗi không?

**Đáp án:** Không. Nó không khớp chuỗi đầu nhưng khớp chuỗi thứ hai; chịu policy của chuỗi đó.

**Câu 5.** Một URL có `permitAll()` nhưng client gửi HTTP Basic sai. Liệu bắt buộc trả 200?

**Đáp án:** Không. Một filter authentication có thể cố xác thực credential do client gửi và từ chối với 401 trước khi authorization cho phép.

## 11. Ghi nhớ khi thiết kế Spring Security reactive

- **`securityMatcher` = chọn chuỗi**, còn **`authorizeExchange().pathMatchers().permitAll()` = chọn quy tắc phân quyền trong chuỗi**.
- Route public thường nên **ở trong một SecurityWebFilterChain có phạm vi phù hợp**, nơi response headers, CSRF và các cơ chế phòng vệ chung vẫn hoạt động theo cấu hình.
- Một request **không khớp bất kỳ SecurityWebFilterChain nào** là một tình huống khác hoàn toàn; không đánh đồng với public `permitAll`.
- Khi nhiều chuỗi, cần **chain cụ thể trước, catch-all sau**, kiểm thử tất cả vùng URL để tránh lỗ hổng do matcher bỏ sót.
- Để xác định hành vi thực, kiểm tra đồng thời **chain matching, authorization rule, authentication/CSRF/headers và HTTP response**, thay vì chỉ nhìn một dòng `permitAll()`.

## Tài liệu chính thức

- Spring Security — WebFlux Security (cấu hình cơ bản, nhiều chuỗi và thứ tự): https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Authorize ServerHttpRequest (`pathMatchers`, `permitAll`, `authenticated`): https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Security HTTP Response Headers for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
