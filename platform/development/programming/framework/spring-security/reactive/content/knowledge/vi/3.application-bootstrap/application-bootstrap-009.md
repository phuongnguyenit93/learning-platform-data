# Kiểm chứng ứng dụng bằng trình duyệt, curl và WebTestClient

**Chủ đề:** Spring Security Reactive (Spring WebFlux) · **Ngữ cảnh:** Khởi tạo ứng dụng.

Sau khi tạo ứng dụng Spring WebFlux và cấu hình Spring Security, cần kiểm chứng hai việc độc lập: **ứng dụng có khởi động và phục vụ HTTP đúng không**, và **quy tắc xác thực/phân quyền có được áp dụng đúng không**. Trình duyệt giúp quan sát hành vi người dùng; `curl` cho phép nhìn chính xác request/response; `WebTestClient` biến kỳ vọng thành bài kiểm tra có thể chạy lặp lại trong quá trình phát triển và CI.

Bài này đưa ra một ứng dụng mẫu Java 17+, chỉ rõ kết quả mong đợi, cách chạy cả ba kênh, cách phân biệt lỗi startup, routing, authentication, authorization và các điểm riêng của reactive. Mọi tài khoản/mật khẩu trong mẫu đều **chỉ dùng trên localhost để học**, không dùng lại trên hệ thống thực.

## 1. Mục tiêu và ma trận kiểm chứng

Sau bài này, bạn có thể:

1. Chạy ứng dụng WebFlux có `SecurityWebFilterChain` và nhận biết khi nào server thật sự sẵn sàng nghe cổng.
2. Mở endpoint trên trình duyệt, xem mã HTTP và response headers trong DevTools thay vì chỉ nhìn trang hiển thị.
3. Dùng `curl` gửi request không credential, credential đúng/sai và credential thiếu role; đối chiếu status, header, body.
4. Viết test `WebTestClient` khởi tạo Spring context và kiểm chứng nguyên đường đi HTTP, bao gồm Spring Security WebFilter.
5. Phân biệt `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, redirect `302` và lỗi CSRF; biết trường hợp nào một status riêng lẻ chưa đủ chứng minh.
6. Giữ phép thử độc lập, ổn định, không tự `subscribe()` trong controller và không phụ thuộc dữ liệu/người dùng bên ngoài.

Ma trận kỳ vọng của **ứng dụng mẫu bên dưới** (toàn bộ đều là `GET`):

| Endpoint | Credential | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| `/api/public` | Không gửi | `200`, body `public-ok` | Đường công khai thực sự truy cập được |
| `/api/me` | Không gửi | `401` và header thách thức Basic | Đường cần xác thực |
| `/api/me` | `reader` / `reader123` | `200`, body `reader` | Xác thực thành công; lấy principal trong Reactor Context |
| `/api/me` | `reader` / mật khẩu sai | `401` | Không chấp nhận credential sai |
| `/api/admin` | `reader` / `reader123` | `403` | Đã xác thực nhưng thiếu quyền admin |
| `/api/admin` | `admin` / `admin123` | `200`, body `admin-ok` | Người có role được phép truy cập |
| `/api/admin` | Không gửi | `401` | Yêu cầu xác thực trước khi xét quyền |

**Lưu ý về mã HTTP:** `401` ở đây chỉ trường hợp không có/xác thực không hợp lệ; `403` là thiếu quyền sau khi xác thực. Đây là kỳ vọng theo cấu hình HTTP Basic của mẫu, không phải quy tắc bất biến của mọi ứng dụng: login form có thể trả `302`, resource server có thể dùng Bearer challenge, tùy biến `authenticationEntryPoint` hoặc `accessDeniedHandler` có thể đổi response.

## 2. Dựng ứng dụng WebFlux tối thiểu để thử

### 2.1. Công cụ và cấu trúc

Cần JDK 17+, Maven 3.9+ và `curl`. Không cần cơ sở dữ liệu, Docker hoặc trình duyệt có plugin riêng. Mẫu dùng **Spring Boot 3.5.16** để API test có thể tái hiện; đây là phiên bản ví dụ, không phải yêu cầu mọi dự án phải dùng đúng phiên bản này.

```text
reactive-security-check/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/check/
    │   │   ├── ReactiveSecurityCheckApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/java/demo/check/
        └── ReactiveSecurityCheckApplicationTests.java
```

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-security-check</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/resources/application.properties`:

```properties
spring.application.name=reactive-security-check
server.port=8080
```

Giữ chỉ WebFlux starter cho mẫu này. Nếu vô tình thêm cả `spring-boot-starter-web`, Spring Boot có thể chọn ứng dụng Servlet/MVC, khiến hành vi/filter và loại test khác dự kiến. Trong dự án có cả hai stack, phải xác định rõ loại ứng dụng trước khi đối chiếu.

### 2.2. Entry point khởi động

`src/main/java/demo/check/ReactiveSecurityCheckApplication.java`:

```java
package demo.check;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityCheckApplication.class, args);
    }
}
```

`@SpringBootApplication` bật component scan trong package `demo.check` và các package con. Các class Security và Controller cùng package nên được Spring tìm thấy.

### 2.3. Cấu hình bảo mật rõ ràng

`src/main/java/demo/check/SecurityConfig.java`:

```java
package demo.check;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Giải thích những lựa chọn ảnh hưởng đến phép kiểm:

- `httpBasic(...)` chấp nhận HTTP Basic và trả challenge cho request cần xác thực. `formLogin(...disable())` làm phép thử API dự đoán được (tránh tự chuyển thành trang đăng nhập `302`).
- `permitAll()` áp dụng cho endpoint công khai, `authenticated()` yêu cầu danh tính hợp lệ và `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo prefix mặc định.
- `anyExchange().denyAll()` chủ ý từ chối mọi đường chưa khai báo. Do đó, **trong đúng cấu hình này**, ngay cả một URL không tồn tại cũng có thể nhận `401`/`403` ở lớp bảo mật trước khi routing có cơ hội trả `404`. Đừng dùng URL lạ để suy luận controller đã tồn tại hay chưa.
- `{noop}` lưu mật khẩu rõ trong ví dụ để việc chạy cục bộ đơn giản. Ứng dụng thực phải dùng password encoder thích hợp, secret management, HTTPS và tài khoản test tách biệt; không hard-code mật khẩu production.

### 2.4. Ba endpoint có kết quả ổn định

`src/main/java/demo/check/ProbeController.java`:

```java
package demo.check;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ProbeController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public-ok");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("admin-ok");
    }
}
```

`/api/me` đọc `Authentication` trong **Reactor Context** khi Publisher được subscribe bởi WebFlux; không dựa vào `ThreadLocal` và không gọi `subscribe()` thủ công trong controller. Cả ba endpoint trả về body kiểu chuỗi, giúp kiểm chứng dễ dàng mà không phụ thuộc JSON serializer hay database.

## 3. Chạy ứng dụng và xác nhận server đã sẵn sàng

Tại thư mục dự án:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Với Maven Wrapper có sẵn, thay `mvn` bằng `./mvnw` trên macOS/Linux hoặc `mvnw.cmd` trên Windows. Bước khởi động thành công khi tiến trình **vẫn đang chạy** và log cho biết WebFlux/Netty đã khởi chạy trên cổng 8080. Nội dung và thời điểm các dòng log thay đổi theo phiên bản, vì vậy không dùng một dòng log cố định làm tiêu chí duy nhất.

Ở terminal **khác**, kiểm tra request đơn giản:

```bash
curl -i http://localhost:8080/api/public
```

Kết quả cần thấy: status `HTTP/1.1 200 OK` (hoặc dạng HTTP tương đương) và phần body là `public-ok`; các header như `Date`, `Content-Length`, `Content-Type` có thể khác theo môi trường. Nếu connection refused/timeout, trước tiên kiểm tra process, địa chỉ, port, proxy và log khởi động, chứ chưa kết luận security sai.

Nếu cổng 8080 đã bị chiếm, thay `server.port` bằng cổng còn trống rồi sửa tất cả URL `curl`/trình duyệt tương ứng. Test tự động ở phần 6 sử dụng cổng ngẫu nhiên nên không phụ thuộc cổng này.

## 4. Kiểm chứng thủ công bằng trình duyệt

Mở Chrome, Edge hoặc Firefox. Trước tiên truy cập:

```text
http://localhost:8080/api/public
```

Trang có thể hiển thị đơn giản `public-ok` (không có giao diện HTML). Đây là tín hiệu tốt: controller được gọi và body được trả. Mở **DevTools → Network**, tải lại trang và chọn request để kiểm tra `Request URL`, `Request Method`, `Status Code`, `Response Headers` và `Response`.

Tiếp theo mở cửa sổ ẩn danh để hạn chế credential Basic đã được trình duyệt cache, rồi vào `http://localhost:8080/api/me`. Với Basic challenge, trình duyệt **có thể** hiện hộp nhập tài khoản/mật khẩu; tùy browser nó cũng có thể hiển thị response 401 thay vì prompt. Nhập `reader` / `reader123` nếu được hỏi; request hợp lệ sẽ thấy `reader`. Xem lại Network để xác nhận status `200` cho request có credential, không chỉ dựa vào nội dung giao diện.

Cuối cùng truy cập `http://localhost:8080/api/admin` với tài khoản `reader`: request đã xác thực vẫn bị từ chối `403`. Thử `admin` / `admin123` trong **phiên đăng nhập/cửa sổ mới** thì endpoint trả `admin-ok`. Khi đổi user nhưng trình duyệt vẫn dùng tài khoản cũ, hãy đóng cửa sổ ẩn danh, mở phiên mới hoặc kiểm tra `Authorization` trong request; cơ chế HTTP Basic có thể cache thông tin và không có nút logout mặc định của ứng dụng mẫu.

**Đọc tín hiệu đúng cách:** trình duyệt có thể render thông báo lỗi, trang trắng hoặc JSON tùy header `Accept` và error handler. Màn hình “trông như lỗi” không cung cấp đủ bằng chứng là 401 hay 403. Căn cứ vào Network và response thực tế.

### 4.1. Browser khác curl ở điểm nào?

- Trình duyệt có thể gửi cookie, cache credential HTTP Basic, tự xử lý challenge, redirect, tài nguyên phụ và JavaScript. Một lần tải trang có thể tạo **nhiều request**.
- Trang đang chạy trên origin khác có thể gặp **CORS**: trình duyệt chặn JavaScript đọc response mặc dù `curl` gọi endpoint thành công. CORS và xác thực là hai chính sách khác nhau.
- DevTools giúp thấy redirect chain và response cuối; luôn kiểm tra request thực sự bị lỗi, không chỉ URL trên thanh địa chỉ.
- Với login form mặc định, `GET` chưa đăng nhập thường có thể dẫn đến `302`/trang login. Mẫu tắt form login để tập trung vào Basic auth. Không gán `302` mặc định cho “được cấp quyền”.

## 5. Kiểm chứng chính xác bằng curl

`curl` phù hợp để viết lại request và nhận kết quả có thể so sánh. Dùng `-i` để xem cả status line, headers lẫn body; `-u` để gửi Basic credentials. Trên PowerShell Windows cũ, `curl` có thể là alias của `Invoke-WebRequest`; khi đó hãy gọi rõ `curl.exe`.

### 5.1. Không credential: public 200, protected 401

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/admin
```

Kiểm tra:

- Public trả `200` và body `public-ok`.
- Hai protected request trả `401` khi chưa xác thực.
- Response `401` của HTTP Basic có header `WWW-Authenticate` với scheme `Basic`. Đây là lời mời client gửi credential, không phải kết quả cấp quyền.

### 5.2. Credential hợp lệ và sai

```bash
curl -i --user reader:reader123 http://localhost:8080/api/me
curl -i --user reader:wrong http://localhost:8080/api/me
curl -i --user reader:reader123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
```

Đối chiếu lần lượt: `200` + `reader`; `401`; `403`; `200` + `admin-ok`.

`--user` giúp `curl` tạo header Basic; không cần tự mã hóa Base64. Basic chỉ mã hóa theo dạng biểu diễn Base64, **không mã hóa bảo mật dữ liệu trên đường truyền**, nên ngoài localhost phải dùng HTTPS. Khi chạy lệnh chứa mật khẩu, shell history và danh sách process có thể lộ credential; trong môi trường thật, dùng `curl --user reader` để `curl` hỏi mật khẩu tương tác, test token/secret store an toàn hoặc biến môi trường thích hợp.

### 5.3. Tách status code khỏi body để script kiểm tra

Trên hệ thống có shell phù hợp:

```bash
curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}\n' \
  --user reader:reader123 \
  http://localhost:8080/api/admin
```

Output mong đợi:

```text
403
```

Dạng lệnh này chỉ in status để dễ kiểm tra tự động; muốn điều tra lỗi cần quay lại `curl -i` để thấy challenge/headers/body. `curl` **không tự coi HTTP 4xx là lỗi process** nếu không bật `--fail`, vì vậy đừng dùng riêng exit code 0 của `curl` làm bằng chứng authorization đã pass. `--fail` làm thay đổi cách xử lý body và mã thoát cho HTTP 4xx/5xx; quyết định dùng nó theo mục đích script.

Một phép thử tốt luôn nêu **method + path + credential + expected status + body/header quan trọng**. Chỉ gọi API và thấy trả về JSON hay HTML chưa đủ khẳng định quyền đúng.

## 6. Biến kỳ vọng thành kiểm thử WebTestClient

`WebTestClient` là client kiểm thử của Spring WebFlux. Nó gửi HTTP request, đăng ký nhận response và có API assertion; controller/service của ứng dụng vẫn phải **trả Publisher** để framework quản lý subscription. Ở đây ta chọn `@SpringBootTest(webEnvironment = RANDOM_PORT)`: Spring khởi động server thật trên **cổng ngẫu nhiên** rồi cấu hình `WebTestClient` gửi request vào server đó. Test không cần tiến trình `mvn spring-boot:run` đang chạy bên ngoài.

Tạo `src/test/java/demo/check/ReactiveSecurityCheckApplicationTests.java`:

```java
package demo.check;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveSecurityCheckApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void protectedEndpointChallengesAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void validReaderCanSeeOwnName() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderCannotAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void adminRouteChallengesAnonymous() {
        client.get().uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Chạy từ thư mục dự án:

```bash
mvn test
```

Mong đợi Maven báo build thành công và có **7 test pass** (nếu chỉ có đúng class test trên). Không nên chép một output Maven cố định vì thời gian, phiên bản plugin, thứ tự và định dạng báo cáo thay đổi. Nếu test fail, quan sát assertion: *expected status*, *actual status*, response headers/body và stack trace để biết sai ở startup, filter, route hay dữ liệu.

**Giải nghĩa chuỗi assertion:**

1. `client.get().uri(...)` tạo đặc tả request.
2. `headers(h -> h.setBasicAuth(...))` gửi credential như một client HTTP thực; không nhét `Authentication` trực tiếp vào mã controller.
3. `exchange()` thực sự thực hiện request và nhận response.
4. `expectStatus()` kiểm tra quyết định HTTP; `expectHeader()` kiểm tra Basic challenge; `expectBody()` chứng minh controller trả đúng nội dung sau khi vượt qua security.

Ở bài tập này, assertion `200` **và** đúng body quan trọng hơn chỉ `200`: một endpoint khác trả 200 hoặc handler trả nội dung sai vẫn phải làm test thất bại. Ngược lại, assertion `401` và `403` là hai bài kiểm tra âm quan trọng để đảm bảo bảo mật không bị vô tình mở rộng.

### 6.1. Khi nào dùng RANDOM_PORT, mock WebFlux hoặc test tách lớp?

| Cách | Phạm vi | Cần lưu ý |
| --- | --- | --- |
| `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` (mẫu đang dùng) | HTTP thật qua server, filter, routing, serialization và app context | Tương đối chậm hơn slice test; thích hợp phép kiểm startup + security end-to-end |
| `@SpringBootTest` + `@AutoConfigureWebTestClient`, môi trường mock phù hợp | Test luồng WebFlux trong application context mà không mở cổng server thật | Phải giữ security filter được áp dụng và hiểu các bean được load |
| `@WebFluxTest` | Slice web/controller nhanh, có thể mock service | Không tự động có tất cả service/security config tùy ứng dụng; import cấu hình và các mock cần thiết |
| `WebTestClient.bindToServer()` | Tự cấu hình client đến server đã chạy | Phải kiểm soát base URL/port và lifecycle server |

Với test mock đã bind vào Spring context, `spring-security-test` hỗ trợ `SecurityMockServerConfigurers.mockUser(...)` hoặc mock OAuth2/JWT theo cơ chế tương ứng. **Không dùng `mockUser` như thể nó truyền danh tính qua một kết nối HTTP tới server thật**: trong test `RANDOM_PORT`, hãy gửi credential/token giống client thực, như `setBasicAuth` của ví dụ. Nếu đang kiểm thử OAuth2 resource server, thay Basic credentials bằng Bearer token đã được issuer/signature/claims xử lý phù hợp.

## 7. Kiểm chứng đúng luồng reactive, không tự subscribe

WebFlux nhận `Mono`/`Flux` từ controller và subscribe để tạo HTTP response. Cách làm đúng:

```java
@GetMapping("/items/{id}")
public Mono<Item> one(@PathVariable String id) {
    return repository.findById(id);
}
```

Không làm như sau:

```java
@GetMapping("/items/{id}")
public Mono<Item> wrong(@PathVariable String id) {
    repository.findById(id).subscribe(item -> audit(item)); // Tách ra một tác vụ khó kiểm soát
    return Mono.empty();
}
```

Hai fragment chỉ minh họa (cần `Item`, `repository`, `audit` và các import tương ứng), không phải các file Java độc lập. Khi tự `subscribe()` ở handler, công việc có thể tiếp tục ngoài vòng đời HTTP, lỗi/cancellation và security context không còn được kiểm soát theo đường request như mong đợi. `WebTestClient` kiểm chứng HTTP response, nhưng **không tự chứng minh** rằng không còn side effect bất đồng bộ bị tách khỏi response. Đối với nghiệp vụ ghi/xử lý dữ liệu nhạy cảm, cần test thêm các dependency và hiệu ứng thực tế.

Nếu endpoint không trả dữ liệu như kỳ vọng, hãy phân biệt **assembly** (tạo Publisher) với **subscription** (chạy nguồn cold). Đừng kết luận “không chạy” chỉ vì chưa thấy log trước khi `exchange()`/trước HTTP request. Khi sử dụng `Mono.defer`, `fromSupplier` hoặc repository reactive, công việc thường diễn ra lúc subscribe. Security context trong WebFlux thường được đọc qua `ReactiveSecurityContextHolder` trên cùng luồng reactive; đừng dựa vào biến `ThreadLocal` gắn với một request cũ.

## 8. Cách đọc lỗi: startup, endpoint hay bảo mật?

| Hiện tượng | Khả năng cần điều tra | Kiểm chứng tiếp |
| --- | --- | --- |
| `curl: (7) Failed to connect` hoặc browser `ERR_CONNECTION_REFUSED` | Server chưa chạy, khởi động lỗi, sai host/cổng | Xem log startup, `server.port`, tiến trình lắng nghe; thử `/api/public` |
| `200` nhưng body sai | Route khác, logic controller, mock, serialisation hoặc stale deployment | Kiểm tra response body chính xác, request URL, port, app instance |
| `401` ở `/api/me` với credential tưởng đúng | Sai username/password, header Basic không được gửi hoặc cấu hình auth khác | Dùng `curl -i -u ...`, kiểm tra `WWW-Authenticate`, user store và log an toàn |
| `403` ở `/api/admin` khi dùng `reader` | **Đúng kỳ vọng**: user đã xác thực nhưng thiếu `ROLE_ADMIN` | Thử user `admin` và kiểm tra `hasRole`/authority |
| `403` cho request POST/PUT/DELETE dù role hợp lệ | Có thể thiếu CSRF token, ngoài lỗi authorization | Xem method, CSRF config, token/cookie và security log; đừng tắt CSRF chỉ để test xanh |
| `302` thay vì `401` | Có thể do form login, redirect HTTPS hoặc app/proxy | Dùng `curl -i` không bật follow redirect; xem `Location` và config filter |
| `404` với endpoint mong đợi | Mapping không tồn tại, sai prefix/method, controller không được scan | Xem `@RequestMapping`/`@GetMapping` và package scan; cũng đối chiếu security rules |
| `403` trên một URL lạ trong mẫu này | `anyExchange().denyAll()` chặn trước routing | Thử các URL đã biết; không suy luận endpoint tồn tại chỉ từ 403 |
| Test `@Autowired WebTestClient` không có bean hoặc chạy MVC | Sai dependency/configuration test, dùng nhầm web stack | Xác minh WebFlux starter, loại môi trường test, Boot version, context startup |
| Test fail ngẫu nhiên khi chạy song song | Shared state, dữ liệu test, cache, port cố định hoặc dependency bên ngoài | Dùng `RANDOM_PORT`, fixture riêng, assertion không phụ thuộc thứ tự |

**CSRF là kiểm tra riêng.** Trong Spring Security WebFlux, CSRF thường bật theo mặc định và tác động lên request thay đổi trạng thái. Bài này chỉ dùng `GET` để làm rõ authentication/authorization. Nếu mở rộng sang `POST`, phải có test *đúng token*, *thiếu token* và *token sai* theo cơ chế của ứng dụng, không đánh đồng 403 do CSRF với 403 do thiếu role. CSRF và CORS giải quyết các nguy cơ khác nhau.

**Không rò rỉ bí mật khi debug:** hạn chế chụp/sao chép `Authorization`, cookie/session, JWT và mật khẩu vào log, video hướng dẫn hay ticket. Với HTTP Basic, thông tin trong header có thể giải mã Base64, nên luôn dùng HTTPS ngoài môi trường cục bộ.

## 9. Quy trình kiểm chứng sau mỗi lần khởi tạo/chỉnh cấu hình

1. **Build được:** `mvn test` chạy được trên JDK đúng phiên bản; không bỏ qua lỗi compile/import.
2. **App khởi động được:** `mvn spring-boot:run` không thoát vì exception và có endpoint `/api/public` trả `200` tại cổng dự kiến.
3. **Từ trình duyệt:** ít nhất một đường public và một đường protected được kiểm tra qua DevTools Network; quan sát user và cached credential.
4. **Từ curl:** ghi lại các request đối chiếu `200`, `401` và `403` với credential đúng/sai và role khác nhau, cùng body/headers quan trọng.
5. **Từ WebTestClient:** có test công khai, bảo vệ request chưa đăng nhập, từ chối sai mật khẩu, từ chối thiếu quyền và cho phép đúng quyền; chạy tự động sau thay đổi cấu hình.
6. **Đọc lỗi ở đúng tầng:** không “sửa” sai filter chỉ vì port đóng, không bỏ bảo mật để tránh 403 và không mặc định một test 200 đã chứng minh toàn bộ chính sách đúng.

Khi chuyển từ mẫu sang ứng dụng thật, thay các endpoint bằng đường nghiệp vụ quan trọng, lập ma trận theo **method/path/role**, thêm trường hợp *không có quyền*, *quyền vừa bị thu hồi*, *dữ liệu thuộc người khác*, token hết hạn và các đường tương đương (ví dụ cùng service được gọi bằng endpoint khác). Kiểm tra body và side effect bên cạnh HTTP status; riêng chính sách authorization cần được kiểm chứng cả ở boundary web lẫn tầng phương thức/dữ liệu khi có.

## 10. Bài luyện tập tự đánh giá

**Câu 1.** Bạn mở `/api/me` bằng browser, thấy hộp thoại đăng nhập và sau đó thấy chữ `reader`. Đã đủ chứng minh 401 ban đầu chưa? **Chưa.** Xem request chưa gửi credential trong Network hoặc dùng `curl -i`; trình duyệt có thể tự xử lý challenge và chỉ hiển thị response cuối.

**Câu 2.** `curl` trả exit code 0 nhưng response status 403. Test thành công chưa? **Chưa.** Mặc định `curl` có thể exit 0 với HTTP 4xx; cần kiểm tra status/body hoặc dùng chính sách `--fail` phù hợp.

**Câu 3.** `reader` gọi `/api/admin` và nhận 403, còn `admin` nhận 200. Phép thử chứng minh điều gì? **Chứng minh quy tắc phân quyền cho endpoint và hai loại credential đang hoạt động theo kỳ vọng.** Nó chưa chứng minh mọi endpoint khác hoặc mọi dữ liệu phía sau đều bảo mật.

**Câu 4.** Test `RANDOM_PORT` có cần mở một terminal chạy `spring-boot:run` trước không? **Không.** Test khởi động server riêng trên cổng ngẫu nhiên. Nếu test cố trỏ vào localhost:8080 bằng URL cứng thì đó là cấu hình client khác, cần xem lại.

**Câu 5.** Sau khi thêm `POST /api/items`, request dùng admin vẫn nhận 403. Có nên disable CSRF ngay? **Không.** Xác định có phải thiếu CSRF token không rồi thêm cơ chế nhận/gửi token đúng với khách hàng thực và test tương ứng.

**Câu 6.** Tại sao không chỉ dùng trình duyệt hoặc chỉ dùng WebTestClient? Trình duyệt thể hiện hành vi thật với cookie, cache, prompt, redirect/CORS; `curl` cho request có thể tái tạo và response minh bạch; `WebTestClient` cho kiểm tra tự động, nhất quán. Cả ba hỗ trợ nhau trong quá trình đưa ứng dụng vào chạy.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework, *Testing with WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security, *CSRF for WebFlux*: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- curl, *Command line tool documentation*: https://curl.se/docs/manpage.html

**Kết quả cần đạt:** Bất kể kiểm chứng qua browser, `curl` hay `WebTestClient`, cùng một request và cùng credential phải phản ánh nhất quán **đúng method, đúng endpoint, đúng trạng thái xác thực, đúng quyền và đúng response mong đợi**. Khi có khác biệt, thu hẹp nguyên nhân theo môi trường chạy, header/cookie, security filter, routing rồi mới đến logic reactive.