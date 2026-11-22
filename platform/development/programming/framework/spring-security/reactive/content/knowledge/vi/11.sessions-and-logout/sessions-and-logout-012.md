# Lựa chọn hủy phiên cũ hoặc từ chối đăng nhập khi vượt giới hạn phiên trong Spring Security reactive

## 1. Mục tiêu bài học

Một người dùng đăng nhập cùng tài khoản từ laptop, điện thoại và trình duyệt khác. Nếu hệ thống chỉ cho phép **một phiên đăng nhập cùng lúc**, điều gì xảy ra khi thiết bị thứ hai đăng nhập thành công bằng đúng mật khẩu?

Với **Spring Security cho Spring WebFlux**, bạn có hai chiến lược tiêu biểu:

1. **Cho phép đăng nhập mới và hủy phiên cũ** — mặc định là vô hiệu hóa phiên ít được sử dụng gần đây nhất (least recently used, LRU).
2. **Giữ phiên cũ và từ chối đăng nhập mới** — dùng handler ngăn tạo session mới khi giới hạn đã đạt.

Bài này giải thích các thành phần reactive, cách chọn chính sách theo nghiệp vụ, cấu hình chạy được với Java 17+, thử thực tế bằng hai browser profile, quản lý registry/store và các bẫy quan trọng về đăng xuất, session timeout, nhiều instance, OAuth2 và JWT.

**Điều cần nhớ:** giới hạn phiên đồng thời là chính sách đối với những **phiên được hệ thống quản lý/đăng ký**; nó không đồng nghĩa giới hạn số TCP connection, request đồng thời hay số JWT đang còn hạn.

## 2. “Phiên đồng thời” thực sự là gì?

Trong ứng dụng form login dùng cookie, một phiên thường tương ứng với `WebSession` ở phía server và một session ID được browser gửi bằng cookie. `SecurityContext` có thể được lưu giữa các request qua `ServerSecurityContextRepository`, thường là `WebSessionServerSecurityContextRepository`.

Khi concurrent sessions control được bật, Spring Security reactive dùng `ReactiveSessionRegistry` để giữ thông tin phiên được đăng ký theo principal. Mỗi session record có thể chứa session ID, last-access time và trạng thái bị vô hiệu hóa.

Một user có hai tab dùng **cùng cookie session** trên cùng browser profile thường chỉ sử dụng **một phiên**, không phải hai. Hai browser profile, một cửa sổ ẩn danh tách biệt và browser thường sẽ có cookie jars riêng, vì vậy có thể tạo hai phiên khác nhau.

| Khái niệm | Ví dụ | Có bị giới hạn bởi maximumSessions không? |
| --- | --- | --- |
| Browser tab thứ hai nhưng dùng cùng session cookie | Hai tab trong một profile | Thường vẫn **một phiên** |
| Hai profile độc lập, mỗi profile có WebSession riêng | Profile A và B | **Hai phiên** nếu cả hai được đăng ký |
| Hai HTTP requests đồng thời dùng cùng cookie | Tải trang và API song song | **Một phiên**, không phải hai |
| HTTP Basic request xác thực theo credentials | Client gửi Authorization mỗi request | Có thể được success handler của concurrent sessions control theo dõi, nhưng semantics khác phiên form login |
| JWT self-contained do client giữ | Nhiều access tokens hợp lệ | **Không tự** nằm trong WebSession registry |
| Phiên SSO ở Identity Provider (IdP) | OAuth2 login tới nhà cung cấp ngoài | Registry ứng dụng **không tự** thu hồi phiên IdP |

Spring Security cho phép **không giới hạn số phiên** theo mặc định cho đến khi bạn cấu hình giới hạn. Concurrent session control trong reactive stack được hỗ trợ từ Spring Security 6.3; đoạn API trong bài theo nhánh Spring Security 6.5/7.1, không sao chép các tên API dành cho Servlet.

## 3. So sánh hai chính sách

Giả sử `SessionLimit.of(1)`, user `learner` đã đăng nhập trong **Browser A** và B chuẩn bị đăng nhập bằng đúng credentials.

### 3.1. Chính sách 1 — Hủy phiên ít được dùng gần đây nhất

~~~text
T0: Browser A đăng nhập thành công -> session A được đăng ký
T1: Browser B gửi form login với credentials hợp lệ
T2: Spring Security kiểm tra số phiên đã đăng ký: 1 / limit 1
T3: Vượt giới hạn nếu cấp thêm session cho B
T4: Handler mặc định vô hiệu hóa phiên LRU (thường là A)
T5: B đăng nhập thành công; session B là phiên hiện hành
T6: A gửi request /private mới -> không còn quyền từ session cũ
~~~

Lớp handler mặc định là `InvalidateLeastUsedServerMaximumSessionsExceededHandler`. Nó vô hiệu hóa **số lượng phiên cũ cần thiết** để đáp ứng giới hạn; không có nghĩa luôn hủy mọi phiên. Ví dụ limit 2, nếu tạo thêm một phiên và vượt đúng một, handler thường thu hồi một phiên LRU.

**Ưu điểm:** người dùng bị mất thiết bị hoặc quên logout vẫn đăng nhập được ở thiết bị mới. Đây là trải nghiệm thường phù hợp cho hệ thống phổ thông, nhưng cần nhận biết rủi ro nếu kẻ xấu đã có credentials: đăng nhập mới có thể đẩy user hợp pháp khỏi phiên cũ.

**Nhược điểm:** browser A có thể đột ngột bị yêu cầu đăng nhập lại; quy trình giao dịch chưa lưu có thể gián đoạn. Cần có thông báo “Phiên của bạn đã được thay thế bởi lần đăng nhập khác” và cơ chế lưu bản nháp khi phù hợp.

### 3.2. Chính sách 2 — Ngăn đăng nhập mới

~~~text
T0: Browser A đăng nhập thành công -> session A được đăng ký
T1: Browser B gửi form login với credentials hợp lệ
T2: Spring Security kiểm tra số phiên đã đăng ký: 1 / limit 1
T3: Handler từ chối tạo authenticated session mới
T4: Browser B đi theo authentication failure path
T5: A vẫn truy cập /private bằng session A
T6: B chỉ đăng nhập được sau khi A logout, hết hạn hoặc phiên được giải phóng
~~~

Lớp reactive tương ứng là `PreventLoginServerMaximumSessionsExceededHandler`. Nó phát sinh `SessionAuthenticationException` khi đã đạt giới hạn và ngăn xác thực thành công của phiên mới. Khi dùng **form login mặc định**, yêu cầu thất bại thường được redirect đến trang login kèm trạng thái lỗi (ví dụ `/login?error`); **không** giả định một status 401 cố định cho mọi cơ chế.

**Ưu điểm:** bảo vệ sự liên tục của thiết bị đang dùng; phù hợp với môi trường quản trị nhạy cảm, terminal đã cấp phát hoặc chính sách license/phiên mà phiên đã đăng nhập được ưu tiên.

**Nhược điểm:** nếu cookie thất lạc, browser bị đóng mà session chưa hết hạn, hoặc registry không nhận được sự kiện cleanup, user có thể **không đăng nhập lại được** dù biết đúng mật khẩu. Hệ thống cần timeout hợp lý và một cách đáng tin để người dùng/đội hỗ trợ thu hồi phiên cũ.

### 3.3. Bảng quyết định

| Tiêu chí | Hủy phiên LRU (mặc định) | Từ chối login mới |
| --- | --- | --- |
| Thiết bị mới đăng nhập đủ credentials | Được phép sau khi dọn phiên cũ | Bị từ chối khi đã đạt limit |
| Thiết bị cũ | Bị vô hiệu hóa nếu là phiên bị chọn | Tiếp tục hoạt động |
| Người dùng quên logout | Dễ tự phục hồi | Có thể bị khóa ngoài tạm thời |
| Trải nghiệm khi đổi thiết bị | Thuận tiện | Cần logout/thu hồi phiên cũ |
| Rủi ro user bị đẩy khỏi phiên bởi login khác | Có | Không theo chính sách này |
| Rủi ro tài khoản bị chiếm quyền | Vẫn cần MFA, alert và kiểm soát credentials | Vẫn cần MFA; attacker có thể đăng nhập trước và chiếm “slot” |
| Yêu cầu hỗ trợ người dùng | Thông báo phiên bị thay thế | Màn hình quản lý phiên/timeout/thu hồi an toàn |
| Chính sách phù hợp | Consumer web, nhân viên di chuyển thiết bị | Terminal đặc thù, hệ thống ưu tiên phiên hiện hữu |

**Không chính sách nào tự thay thế MFA, phát hiện login bất thường, device risk scoring hoặc quản lý token.** “Từ chối phiên mới” không có nghĩa attacker không thể login nếu chưa có phiên nào tồn tại.

## 4. Các lớp reactive tham gia

Một cấu hình bằng `ServerHttpSecurity.sessionManagement(...)` kết nối các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `SecurityWebFilterChain` | Security filter chain cho request WebFlux |
| `ServerHttpSecurity.SessionManagementSpec.ConcurrentSessionsSpec` | DSL cấu hình số phiên và handler khi vượt giới hạn |
| `SessionLimit` | Cách xác định số phiên tối đa từ `Authentication` |
| `ReactiveSessionRegistry` | Tra cứu và lưu các phiên đã biết của principal |
| `InMemoryReactiveSessionRegistry` | Implementation registry trong RAM, hợp cho demo/một node |
| `ConcurrentSessionControlServerAuthenticationSuccessHandler` | Kiểm tra giới hạn khi authentication thành công |
| `RegisterSessionServerAuthenticationSuccessHandler` | Đăng ký session sau authentication thành công |
| `InvalidateLeastUsedServerMaximumSessionsExceededHandler` | Mặc định vô hiệu hóa phiên LRU khi vượt limit |
| `PreventLoginServerMaximumSessionsExceededHandler` | Từ chối tạo phiên mới nếu giới hạn đã chạm |
| `ServerMaximumSessionsExceededHandler` | Interface để thay chiến lược xử lý |
| `WebSessionStore` | Kho dữ liệu backing cho WebSession thực tế |

Luồng rút gọn:

~~~text
POST /login (browser B)
      |
      v
ServerFormLoginAuthenticationConverter
      |
      v
ReactiveAuthenticationManager: credentials hợp lệ?
      |
      +-- NO --> authentication failure handler
      |
      +-- YES --> ConcurrentSessionControlServerAuthenticationSuccessHandler
                         |
                         v
                  ReactiveSessionRegistry
                  getAllSessions(principal)
                         |
             +-----------+------------+
             |                        |
       chưa đạt limit             đã đạt limit
             |                        |
             v                        v
       Đăng ký phiên       ServerMaximumSessionsExceededHandler
             |                        |
             |                +-------+-------+
             |                |               |
             |              EVICT           PREVENT
             |                |               |
             v                v               v
       login thành công  xóa phiên cũ     từ chối login mới
       + lưu context     rồi nhận B       qua failure path
~~~

Đây là mô hình học tập. Thứ tự xử lý nội bộ, lưu session context và handler cụ thể phụ thuộc cơ chế login cùng phiên bản. Không tự dùng sơ đồ làm bằng chứng rằng mọi custom authentication filter đều đã đăng ký session.

### Một chi tiết cực kỳ quan trọng: success handler

Spring Security tự chèn những success handler phục vụ concurrent-session control cho các cơ chế được hỗ trợ như **form login**, **OAuth2 login** và **HTTP Basic**, **nếu** bạn không thay thế success handler theo cách loại bỏ cơ chế đó.

Ví dụ cấu hình:

~~~java
.formLogin(login -> login
        .authenticationSuccessHandler(
                new RedirectServerAuthenticationSuccessHandler("/")))
~~~

có thể **vô tình tắt concurrent-session registration/control đối với form login** vì đã thay toàn bộ success handler mặc định. Khi cần thêm logic sau đăng nhập (audit/redirect), dùng API thêm handler vào danh sách thay vì ghi đè danh sách; tài liệu reactive có `authenticationSuccessHandler(Consumer<List<ServerAuthenticationSuccessHandler>>)` cho mục đích này. Kiểm thử lại concurrent-session behavior sau khi thay success handler.

## 5. Demo hoàn chỉnh: đổi chính sách bằng một property

Ví dụ sau chạy một ứng dụng Spring Boot WebFlux Java 17+; `demo.session-policy` chọn `evict` hoặc `prevent`. Có một user `learner`, một route HTML công khai và một route chỉ dành cho user đã đăng nhập.

**Không cần tự viết form đăng nhập.** `formLogin(Customizer.withDefaults())` tạo trang `GET /login` và nhận `POST /login`; Spring Security giữ CSRF protection mặc định.

### 5.1. Tạo project

Chọn Spring Initializr với Maven, Java 17+, Spring Boot **4.1.2** (hoặc bản patch Boot tương thích được hỗ trợ), dependencies **Spring Reactive Web** và **Spring Security**.

File `pom.xml` tối giản đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-session-policy</artifactId>
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
~~~

Không thêm `spring-boot-starter-web` vì đó là Spring MVC/Servlet. Không tự ghép version của Spring Security, Reactor và Netty; để Spring Boot BOM quản lý.

### 5.2. Code Java đầy đủ

Tạo `src/main/java/com/example/sessionpolicy/ReactiveSessionPolicyApplication.java`:

~~~java
package com.example.sessionpolicy;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.session.InMemoryReactiveSessionRegistry;
import org.springframework.security.core.session.ReactiveSessionRegistry;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.PreventLoginServerMaximumSessionsExceededHandler;
import org.springframework.security.web.server.authentication.SessionLimit;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSessionPolicyApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionPolicyApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learn123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    ReactiveSessionRegistry reactiveSessionRegistry() {
        return new InMemoryReactiveSessionRegistry();
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http, Environment env) {
        String mode = env.getProperty("demo.session-policy", "evict")
                .trim().toLowerCase(java.util.Locale.ROOT);

        if (!mode.equals("evict") && !mode.equals("prevent")) {
            throw new IllegalArgumentException(
                    "demo.session-policy must be evict or prevent");
        }

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.disable())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(sessions -> sessions
                        .concurrentSessions(concurrency -> {
                            concurrency.maximumSessions(SessionLimit.of(1));
                            if (mode.equals("prevent")) {
                                concurrency.maximumSessionsExceededHandler(
                                        new PreventLoginServerMaximumSessionsExceededHandler());
                            }
                            // "evict" dùng handler mặc định của Spring Security
                        }))
                .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> index() {
            return Mono.just("""
                    <!doctype html>
                    <html lang="vi">
                      <head><meta charset="UTF-8">
                        <title>Concurrent Session Demo</title></head>
                      <body>
                        <h1>Trang công khai</h1>
                        <a href="/private">Trang yêu cầu đăng nhập</a>
                      </body>
                    </html>
                    """);
        }

        @GetMapping("/public")
        Mono<String> publicPage() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/private")
        Mono<String> privatePage(Principal principal) {
            return Mono.just("PRIVATE_OK:" + principal.getName());
        }
    }
}
~~~

**Giải thích:**

- Bean `MapReactiveUserDetailsService` cung cấp user thử nghiệm `learner`. Hash dạng `{noop}` chỉ dùng cho môi trường học trên local; production phải dùng `PasswordEncoder` mạnh, HTTPS và identity store thật.
- `ReactiveSessionRegistry` được Spring Security dùng để lưu thông tin phiên theo user. `InMemoryReactiveSessionRegistry` phù hợp với một instance demo, không phải giải pháp hoàn chỉnh cho cluster.
- `SessionLimit.of(1)` giới hạn **một session đã đăng ký** cho mỗi user.
- Ở mode `evict` không cần tạo handler riêng: DSL mặc định dùng `InvalidateLeastUsedServerMaximumSessionsExceededHandler`.
- Ở mode `prevent`, `maximumSessionsExceededHandler(new PreventLoginServerMaximumSessionsExceededHandler())` đổi kết quả khi chạm giới hạn.
- Tắt HTTP Basic ở ví dụ để **chỉ có form login và cookie session**, giúp thử hai browser profile dễ hiểu. Nếu bật Basic, mỗi request có thể kích hoạt cơ chế authentication success theo thiết kế khác, không nên dùng nó để mô phỏng hai phiên form login.
- Dùng login mặc định và không tùy biến success handler để tránh vô tình loại các success handler quản lý phiên.
- Không tắt CSRF; form login mặc định chứa CSRF token hợp lệ. Không dùng GET để thực hiện login/logout.
- `Principal` trong `privatePage` lấy user đã qua security, không phải tên do browser tự khai báo.

**Lưu ý phiên bản class name:** Java API reactive có class chính xác là `PreventLoginServerMaximumSessionsExceededHandler` thuộc `org.springframework.security.web.server.authentication`. Một số ví dụ trong trang tài liệu dùng tên ngắn `PreventLoginMaximumSessionsExceededHandler`, nhưng tên đó **không khớp với Javadoc class trong package này**. Với IDE, kiểm tra import từ Javadoc của version đang sử dụng.

### 5.3. Chạy mode EVICT (mặc định)

Tại thư mục `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Windows dùng `.\mvnw.cmd spring-boot:run`. Nếu không có Maven wrapper, dùng `mvn spring-boot:run` khi đã cài Maven phù hợp.

Kịch bản thủ công:

1. Mở **Browser A**, ví dụ một Chrome profile bình thường. Truy cập `http://localhost:8080/private`; được redirect tới `/login`.
2. Nhập `learner` / `learn123`. Browser A được đưa tới tài nguyên đã yêu cầu, thấy text `PRIVATE_OK:learner`.
3. Mở **Browser B** trong một Chrome profile độc lập hoặc cửa sổ ẩn danh **không chia sẻ cookie** với A. Truy cập `/private` và login **cùng tài khoản**.
4. Với mode mặc định `evict`, B được đăng nhập. Quay về A và **refresh `/private`**. Session A đã bị chọn để vô hiệu hóa và thường được redirect về login.
5. Refresh B: phiên B vẫn truy cập `/private` bình thường.

Để xem response redirect ban đầu mà không tự theo chuyển hướng:

~~~bash
curl -i http://localhost:8080/private
~~~

Khi chưa có cookie đã xác thực, thông thường trả HTTP **302** với `Location` trỏ tới `/login`. Đừng bật `curl -L` nếu muốn quan sát response 302 thay vì HTML 200 của trang login.

**Không dùng hai tab trong cùng một browser profile** để kiểm chứng vì chúng thường dùng chung session cookie, do đó vẫn chỉ là một phiên. Không dự đoán cố định session ID hoặc thời điểm cleanup; kiểm tra hành vi trên **request kế tiếp** của phiên cũ.

### 5.4. Chạy mode PREVENT (từ chối login mới)

Dừng ứng dụng rồi chạy với property:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--demo.session-policy=prevent
~~~

Nếu dùng file JAR đã build, cú pháp dễ kiểm tra hơn và không phụ thuộc quy tắc quote của Maven shell:

~~~bash
java -jar target/reactive-session-policy-0.0.1-SNAPSHOT.jar --demo.session-policy=prevent
~~~

Khi dùng command `java -jar`, hãy build trước bằng `./mvnw clean package`. Để mode thay đổi có hiệu lực, cần **khởi động lại ứng dụng**; property không tự chuyển chính sách của các phiên đang tồn tại lúc runtime.

Lặp lại bài thử với A và B là hai browser profile riêng:

1. A login thành công và truy cập `/private`.
2. B mở `/login`, nhập đúng `learner` / `learn123`.
3. Vì A đã chiếm 1/1 slot, **B bị từ chối authentication session mới**. Với form login mặc định, B thường về `/login?error`; không nên khẳng định response là HTTP 401 cho form login.
4. A refresh `/private` vẫn thấy `PRIVATE_OK:learner`.
5. A logout bằng nút/form logout của Spring Security hoặc đợi session timeout/thu hồi session theo quy trình hợp lệ. B có thể thử đăng nhập lại sau khi slot đã được giải phóng.

**Quy trình logout đúng:** mặc định Spring Security form login có xử lý `POST /logout` với CSRF; dùng giao diện logout hoặc form có token hợp lệ. Đừng giả định `GET /logout` luôn thực hiện logout trong cấu hình có CSRF. Nếu browser A chỉ đóng tab, server chưa nhất thiết biết session phải chấm dứt.

### 5.5. Kết quả cần quan sát

| Bước | Mode EVICT | Mode PREVENT |
| --- | --- | --- |
| A login lần đầu | Thành công | Thành công |
| B login cùng tài khoản sau A | Thành công; phiên LRU bị hủy | Thất bại vì hết slot |
| B truy cập `/private` sau login | `PRIVATE_OK:learner` | Chưa có phiên auth thành công, được chuyển về login |
| A refresh `/private` | Bị yêu cầu login lại | `PRIVATE_OK:learner` |
| A chủ động logout, B login lại | B đã có session, không cần login lại | B có thể login khi registry giải phóng phiên A |
| Có user **khác** login | Có slot riêng nếu policy áp dụng theo user | Có slot riêng nếu policy áp dụng theo user |

Status, cookie, địa chỉ redirect và body cụ thể có thể khác theo custom handler và version. Bài thực hành tập trung vào **ai tiếp tục sở hữu phiên hợp lệ sau lần đăng nhập thứ hai**.

## 6. Chọn giới hạn theo tài khoản bằng SessionLimit

`maximumSessions` nhận `SessionLimit`, là một functional interface: lấy `Authentication` và trả `Mono<Integer>`. Có thể dùng số khác nhau theo role hoặc loại tài khoản. Ví dụ **đoạn thay thế cho SessionLimit.of(1)** trong method security phía trên:

~~~java
SessionLimit limit = authentication -> {
    boolean unlimited = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_UNLIMITED_SESSIONS".equals(a.getAuthority()));
    if (unlimited) {
        return Mono.empty(); // không giới hạn
    }

    boolean admin = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    return Mono.just(admin ? 2 : 1);
};

// Trong concurrentSessions(...):
concurrency.maximumSessions(limit);
~~~

Đây là **snippet cấu hình**, chưa phải Java class độc lập. Cần import `org.springframework.security.web.server.authentication.SessionLimit` và `reactor.core.publisher.Mono`. Ý nghĩa:

- `Mono.just(1)`: một phiên.
- `Mono.just(2)`: hai phiên.
- `Mono.empty()`: không giới hạn cho user được chọn.
- `SessionLimit.UNLIMITED` là hằng có sẵn nếu tất cả user đều không có giới hạn.

**Đừng nhầm với `Mono.empty()` của AuthenticationManager.** Ở đây empty là contract của **SessionLimit**, mang nghĩa không giới hạn, **không phải** là authentication failure hoặc một lỗi lưu session.

Khi role thay đổi sau login, policy số phiên sẽ được tính trên `Authentication` mà quá trình xác thực cung cấp. Nếu cần siết số phiên ngay khi role bị thu hồi, phải chủ động thu hồi/kiểm tra lại phiên; đừng chỉ đổi role trong database rồi coi registry đã tự dọn hết.

## 7. Registry, session store và tính nhất quán

### 7.1. Registry và backing session store là hai việc khác nhau

`ReactiveSessionRegistry` trả lời “user này có những phiên nào đã được đăng ký?”; `WebSessionStore` trả lời “dữ liệu WebSession cụ thể đang được lưu ở đâu?”. Để thu hồi một phiên chắc chắn, cần phối hợp cả hai mặt.

Nếu chỉ xóa record trong registry, session cookie có thể vẫn trỏ đến WebSession chứa SecurityContext. Nếu chỉ xóa WebSession mà registry còn giữ record, chế độ **PREVENT** có thể tiếp tục nghĩ user đã đủ số phiên và từ chối login mới.

Một implementation in-memory registry có ý nghĩa với **một JVM/process**. Khi chạy nhiều pod/node, user có thể login trên node A và B, mỗi node thấy số phiên riêng. Muốn giới hạn toàn hệ thống phải có giải pháp session/registry dùng chung, đồng bộ lifecycle và kiểm soát cạnh tranh giữa các lần login.

### 7.2. Thu hồi phiên thủ công cho trường hợp mất thiết bị

Tài liệu reactive cung cấp mẫu thao tác bằng `ReactiveSessionRegistry` và `WebSessionStore`. Ví dụ **class service ghép vào ứng dụng đã cấu hình session registry/store**, không phải file chạy độc lập:

~~~java
import org.springframework.security.core.session.ReactiveSessionRegistry;
import org.springframework.web.server.session.WebSessionStore;
import reactor.core.publisher.Mono;

final class SessionRevocationService {
    private final ReactiveSessionRegistry registry;
    private final WebSessionStore store;

    SessionRevocationService(
            ReactiveSessionRegistry registry, WebSessionStore store) {
        this.registry = registry;
        this.store = store;
    }

    Mono<Void> revokeKnownSessions(String principal) {
        return registry.getAllSessions(principal)
                .concatMap(session -> session.invalidate()
                        .then(store.removeSession(session.getSessionId())))
                .then();
    }
}
~~~

**Giải thích:**

- `getAllSessions(principal)` truy xuất session mà registry biết đến; phải dùng cùng khóa principal với cách registry lưu. Trong hệ thống thật ưu tiên user ID ổn định, xử lý nếu username thay đổi.
- `session.invalidate()` đánh dấu registry record không còn hợp lệ.
- `store.removeSession(id)` xóa session khỏi backing store thực tế.
- `concatMap` tuần tự hóa thao tác dọn, phù hợp khi cần tránh quá nhiều tác vụ đồng thời.
- `then()` hoàn tất khi publisher kết thúc; đừng tạo Mono rồi không return/subscribe.
- Đây là cơ chế cho **các phiên đã được đăng ký**; không thể hủy những phiên mà registry không biết hoặc token JWT ngoài WebSession.

Đảm bảo caller có thẩm quyền (user tự quản phiên của mình hoặc admin đã được kiểm tra quyền), ghi audit event an toàn, chống request CSRF ở endpoint thay đổi trạng thái và có lỗi/retry policy. Đừng phơi session ID trong log/frontend.

### 7.3. Cleanup session khi hết hạn

Mode PREVENT yêu cầu vòng đời session được giải phóng **đúng lúc**:

- Logout phải xóa context/session/registry theo cơ chế được cấu hình.
- Session timeout phải được backing store và registry phản ánh.
- Eviction phải dọn được session ở mọi node.
- Session bị hủy thủ công không được giữ lại như một “slot” còn chiếm.

Kiểm thử các tình huống browser đóng đột ngột, mất mạng, phiên hết hạn và server restart. Với production, cung cấp giao diện “Thiết bị đang đăng nhập” hoặc quy trình “Đăng xuất các thiết bị khác” đã được xác thực lại/MFA theo rủi ro.

## 8. Không đồng nhất WebSession với OAuth2 IdP, Basic hay JWT

### 8.1. Form login

Demo phần 5 dùng form login, session cookie và mặc định của Spring Security, do đó kết quả dễ quan sát. Success handlers cho form login được tích hợp với concurrent session control nếu không bị custom override.

### 8.2. OAuth2/OIDC login

Reactive concurrent session control có thể ghi nhận **session của ứng dụng sau khi OAuth2 login thành công**, nhưng không tự biết số phiên bên trong IdP/SSO. Nếu thiết bị A mất session ứng dụng, nó có thể vẫn giữ session đăng nhập với IdP và đăng nhập lại rất nhanh. Khi yêu cầu giới hạn cả tại identity provider hoặc cần global logout, phải dùng API/session/logout của IdP tương ứng, có xử lý sự cố và kiểm tra quyền.

### 8.3. HTTP Basic

Tài liệu reactive liệt kê HTTP Basic trong các cơ chế được success handler quản lý. Tuy vậy, request Basic thường gửi credentials **mỗi lần**, nên semantics “đăng nhập tại hai thiết bị” khác browser form login. Nếu sử dụng HTTP Basic trong một API thuần stateless, không nên giả định `maximumSessions(1)` tự bảo vệ số lượng client hoặc số lần gửi request; chọn mô hình authentication và session tracking phù hợp.

### 8.4. JWT/Bearer token stateless

JWT tự chứa claims và có thể được resource server xác minh offline; `ReactiveSessionRegistry` không tự biết những JWT đã được phát. Vì vậy `maximumSessions` cho WebSession **không tự giới hạn** số JWT còn hạn hoặc refresh token.

Nếu nghiệp vụ yêu cầu “một thiết bị/token đang hoạt động”, cân nhắc token family/device ID, refresh-token rotation, revoked-token store, `jti` denylist, security version hoặc introspection. Mỗi resource server phải kiểm tra trạng thái đó theo policy; nếu chỉ xác minh signature và `exp`, token cũ có thể tiếp tục hoạt động đến hết hạn.

### 8.5. Đa instance / cluster

Khi ứng dụng scale từ một node lên nhiều node, `InMemoryReactiveSessionRegistry` chỉ thấy memory của node đó. Một distributed WebSession store **không tự chứng minh** registry đã chia sẻ và lựa chọn LRU đã nhất quán. Thiết kế phải đồng bộ session index và lifecycle, xử lý login đồng thời (race) và tránh hai node cùng thấy “còn slot” rồi đều cấp phiên.

## 9. Chọn chính sách cho tình huống nghiệp vụ

### 9.1. Ứng dụng nhân viên hay di chuyển thiết bị

**Ưu tiên EVICT** nếu yêu cầu UX là người dùng có thể nhanh chóng đăng nhập máy mới khi quên logout. Nên bổ sung thông báo “đã có lần đăng nhập khác”, kiểm tra rủi ro thiết bị, email/push notification, MFA và audit.

### 9.2. Máy POS/terminal hoặc thiết bị được cấp quyền hoạt động liên tục

**Ưu tiên PREVENT** nếu việc mất phiên hiện tại có thể gây gián đoạn nghiệp vụ hoặc khi một ca vận hành phải gắn với một terminal đã phê duyệt. Nhưng bắt buộc có cơ chế thu hồi phiên từ người quản trị được ủy quyền; nếu mất thiết bị, hệ thống không được khóa user vĩnh viễn chỉ vì registry giữ slot cũ.

### 9.3. Hệ thống tài chính hoặc quản trị rủi ro cao

Không chỉ chọn một enum. Cân nhắc login trên thiết bị mới chỉ được phép sau MFA/step-up, thu hồi phiên cũ có xác nhận và thông báo, khóa tài khoản khi phát hiện bất thường, giới hạn thời lượng WebSession, kiểm tra account state và monitoring. Nếu user cần hai thiết bị hợp lệ, limit 1 có thể là chính sách sai ngay từ đầu.

### 9.4. Giới hạn theo role, tenant, subscription

Có thể viết `SessionLimit` để trả 1, 2 hoặc unlimited tùy authority, nhưng nếu giới hạn thuộc subscription/tenant ở database, policy cần nguồn dữ liệu reactive phù hợp và xử lý concurrency an toàn. Không gọi JDBC blocking trực tiếp trong một lambda được dùng ở reactive authentication success path.

## 10. Lỗi và bẫy thường gặp

### “Cấu hình maximumSessions(1) rồi vẫn đăng nhập được ở nhiều tab”

Hai tab có thể **cùng cookie WebSession**. Hãy thử hai browser profiles độc lập, kiểm tra `SESSION` cookie và registry thay vì đếm số tab.

### “Tôi cấu hình prevent, user đóng browser rồi không login được nữa”

Đóng browser **không chắc** gửi logout request. Session phía server có thể tồn tại đến timeout. Cần timeout hợp lý, logout đúng CSRF và luồng revoke session cũ.

### “Tôi custom form success handler, giới hạn phiên không còn tác dụng”

Một handler tự thay thế có thể loại `ConcurrentSessionControlServerAuthenticationSuccessHandler` và `RegisterSessionServerAuthenticationSuccessHandler` khỏi flow. Dùng API thêm handler vào list, hoặc tự tích hợp đầy đủ cơ chế này; luôn test 2 browser sau khi custom.

### “Tôi dùng class PreventLoginMaximumSessionsExceededHandler và IDE báo không tìm thấy”

Trong reactive Javadoc, tên class là `PreventLoginServerMaximumSessionsExceededHandler`. Không dùng tên gần giống trong phần code minh họa tài liệu hoặc API Servlet. Import đúng package `org.springframework.security.web.server.authentication`.

### “Dùng maxSessionsPreventsLogin(true) trên WebFlux”

Đây là cú pháp quen thuộc ở một số **Servlet** API/tài liệu cũ. Với reactive DSL đã xác minh, cấu hình bằng `maximumSessions(SessionLimit.of(...))` và `maximumSessionsExceededHandler(...)`. Không trộn `HttpSecurity` với `ServerHttpSecurity`.

### “Hủy session cũ nghĩa là JWT, refresh token và IdP SSO đều bị thu hồi”

Không. Những hệ thống giữ trạng thái xác thực khác nhau. WebSession/registry của ứng dụng không tự thu hồi bearer token hay session của identity provider.

### “InMemoryReactiveSessionRegistry hoạt động ổn khi chạy ba pod”

Không có bảo đảm toàn cluster nếu mỗi pod có registry riêng. Cần thiết kế shared registry, shared session store và bảo vệ race giữa các node.

### “Form login thứ hai bị từ chối nhưng phải trả 401 mới đúng”

Với form login, failure handler có thể redirect tới `/login?error`; HTTP 401 thường gặp hơn với API Basic/Bearer. Kiểm tra **không có phiên mới**, thay vì cố định status cho mọi authentication mechanism.

### “Chọn LRU nghĩa là phiên mở lâu nhất sẽ bị hủy”

Không nhất thiết. **Least recently used** là phiên **ít được truy cập gần đây nhất**, không phải chắc chắn phiên được tạo sớm nhất. Khi A vẫn hoạt động thường xuyên còn B đã mở trước nhưng ít dùng, lựa chọn LRU cần dựa vào last-access info và cơ chế cập nhật tương ứng.

### “Mỗi login lại trên cùng WebSession luôn tăng số phiên”

Không nên tự giả định. Registry dựa vào session ID và success handler. Khi login lại/cookie bị xoay, việc đăng ký/invalidating sẽ tùy session lifecycle; test theo implementation thực tế, không dùng số lần submit form như số phiên.

## 11. Test matrix cần có

| Kịch bản | Cách thử | Kết quả mong đợi |
| --- | --- | --- |
| A login đầu tiên | Browser A login | Có session A hợp lệ |
| EVICT khi B login | B độc lập login, A refresh | B thành công, A bị yêu cầu login lại |
| PREVENT khi B login | B độc lập login, A refresh | B không có auth session; A còn hợp lệ |
| User khác login | Dùng tài khoản khác | Giới hạn độc lập theo principal |
| Hai tab dùng cùng cookie | Hai tab cùng profile | Không tính thành hai phiên riêng |
| A logout rồi B login ở PREVENT | Form POST logout với CSRF | Slot được giải phóng; B có thể đăng nhập |
| A mất kết nối/đóng browser | Không gửi logout, chờ timeout | Session được giải phóng theo lifecycle cấu hình |
| A bị admin revoke | Service invalidate session + remove store | A không tiếp tục truy cập bằng cookie cũ |
| Đăng nhập đồng thời | B và C cùng login trong thời điểm sát nhau | Không vượt chính sách theo guarantee hệ thống công bố |
| Nhiều node | A login node 1, B login node 2 | Registry/store toàn cụm áp dụng cùng policy |
| Custom success handler | Thêm audit hoặc redirect | Concurrent control vẫn có hiệu lực |
| OAuth2 SSO | App session hết hạn nhưng IdP còn session | Xử lý đúng giới hạn app và phiên IdP |
| JWT access token | Có token còn hạn sau WebSession revoke | Token chỉ bị chặn khi có cơ chế revoke/version riêng |

Với test tự động, có thể dùng `WebTestClient` kết hợp Spring Security test support để login qua form/CSRF và quản lý hai cookie jars khác nhau; hoặc dùng test browser (Playwright/Selenium) cho hành vi redirect. Không chỉ assert 302/200: kiểm tra browser nào thực sự có principal sau request kế tiếp.

## 12. Checklist triển khai

1. Đã xác định rõ “session” là **WebSession đăng ký theo principal**, không phải tab, connection hay JWT.
2. Đã chọn rõ **EVICT** hoặc **PREVENT** từ yêu cầu sản phẩm và trải nghiệm người dùng.
3. Có `SessionLimit` đúng: số dương, hoặc `UNLIMITED` cho trường hợp được cho phép.
4. Đã cấu hình `ReactiveSessionRegistry` và xác minh login success handler đang đăng ký phiên.
5. Nếu PREVENT: có timeout, logout, cleanup và công cụ thu hồi session cũ.
6. Nếu EVICT: có thông báo khi phiên bị thay thế, audit đăng nhập mới và kiểm soát MFA/risk.
7. Cả registry và `WebSessionStore` được đồng bộ trong cluster; xử lý login đồng thời giữa nhiều node.
8. Có CSRF protection cho form login/logout; cookie dùng HTTPS, Secure/HttpOnly/SameSite theo threat model.
9. Không dựa vào WebSession limit để kiểm soát JWT/refresh token/IdP session.
10. Có test cho A/B độc lập, logout, session timeout, password change, role change, cluster và các lỗi hạ tầng.
11. Không log session ID, password, cookie, access/refresh token hoặc dữ liệu người dùng nhạy cảm.
12. Kiểm tra API đúng phiên bản: reactive `ServerHttpSecurity`, không nhầm Servlet `HttpSecurity`.

## 13. Câu hỏi tự đánh giá

**Câu 1.** Limit 1, A đang đăng nhập. B đăng nhập bằng đúng password. Default reactive policy xử lý thế nào?

**Đáp án:** B có thể đăng nhập, phiên ít được sử dụng gần đây nhất bị vô hiệu hóa để duy trì giới hạn; thường A là phiên bị thu hồi khi chỉ có A trước đó.

**Câu 2.** Làm sao để phiên A được giữ và B bị từ chối?

**Đáp án:** Cấu hình `maximumSessions(SessionLimit.of(1))` cùng `maximumSessionsExceededHandler(new PreventLoginServerMaximumSessionsExceededHandler())` trong `ServerHttpSecurity.sessionManagement(...).concurrentSessions(...)`.

**Câu 3.** Tại sao B bị redirect về trang login khi PREVENT, thay vì HTTP 401?

**Đáp án:** Đây là flow form login. Handler ngăn tạo phiên mới phát lỗi authentication/session, failure handler của form có thể redirect đến login error. HTTP response phụ thuộc authentication mechanism.

**Câu 4.** Hai tab cùng browser được đếm thành mấy phiên?

**Đáp án:** Thường một nếu chúng dùng chung session cookie/WebSession, dù có hai cửa sổ hiển thị.

**Câu 5.** Vì sao chỉ dùng InMemoryReactiveSessionRegistry có thể sai khi deploy 4 pod?

**Đáp án:** Các node có registry riêng, không biết tất cả phiên trong hệ thống; cần registry/store và concurrency control phân tán đúng cách.

**Câu 6.** User logout đúng cách nhưng registry vẫn nghĩ còn slot. Điều gì cần kiểm tra?

**Đáp án:** Session invalidation, `WebSessionStore`, registry record cleanup, timeout events và cách ánh xạ principal. Chỉ xóa cookie phía client là không đủ.

**Câu 7.** Vì sao tối đa một WebSession không đồng nghĩa tối đa một JWT?

**Đáp án:** JWT có thể được phát và xác minh độc lập với WebSession/ReactiveSessionRegistry. Cần token issuance/revocation policy riêng nếu muốn giới hạn token hoặc thiết bị.

## 14. Tài liệu chính thức

- [Spring Security — Reactive Concurrent Sessions Control](https://docs.spring.io/spring-security/reference/reactive/authentication/concurrent-sessions-control.html)
- [Spring Security — ServerHttpSecurity.SessionManagementSpec.ConcurrentSessionsSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.SessionManagementSpec.ConcurrentSessionsSpec.html)
- [Spring Security — SessionLimit API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/SessionLimit.html)
- [Spring Security — ReactiveSessionRegistry API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/ReactiveSessionRegistry.html)
- [Spring Security — PreventLoginServerMaximumSessionsExceededHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/PreventLoginServerMaximumSessionsExceededHandler.html)
- [Spring Security — InvalidateLeastUsedServerMaximumSessionsExceededHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/InvalidateLeastUsedServerMaximumSessionsExceededHandler.html)
- [Spring Security — Authentication and Logout in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
