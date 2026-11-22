# RequestRejectedException và RequestRejectedHandler trong Spring Security Servlet

> **Phạm vi:** Spring Security 6.x trên Servlet stack (Spring MVC, thường đi cùng Spring Boot 3.x và Java 17+). Bài học tập trung vào lỗi do `HttpFirewall` từ chối HTTP request và cơ chế `RequestRejectedHandler` chuyển lỗi đó thành HTTP response. Đây là luồng của Servlet; WebFlux có filter và lớp request riêng. Một vài quyết định chặn request còn phụ thuộc phiên bản Spring Security, Servlet container và reverse proxy.

## 1. Vấn đề: request bị chặn trước cả bước xác thực

Thông thường ta hình dung HTTP request đi qua Spring Security theo trình tự: lấy thông tin đăng nhập → kiểm tra quyền → controller. Nhưng có một lớp kiểm tra sớm hơn: **`HttpFirewall`** được `FilterChainProxy` sử dụng để kiểm tra và chuẩn hóa cách Spring Security quan sát request trước khi lựa chọn và chạy `SecurityFilterChain`.

Một request có đường dẫn không chuẩn hóa, mã hóa URL đáng ngờ, dấu phân cách bị cấm hoặc HTTP method ngoài danh sách được phép có thể bị firewall từ chối **ngay từ đầu**. Trong tình huống đó:

- Controller chưa được gọi; annotation `@GetMapping`, `@PostMapping` hoặc `@ExceptionHandler` trong Spring MVC có thể không nhận được cơ hội xử lý.
- Request chưa được quyết định bằng các quy tắc `authorizeHttpRequests` thông thường.
- Spring Security phát sinh `RequestRejectedException`; cơ chế `RequestRejectedHandler` quyết định phản hồi HTTP cho lỗi đó.
- Mã phản hồi thường gặp khi dùng `HttpStatusRequestRejectedHandler` là **400 Bad Request**, không phải 401 vì chưa đăng nhập hay 403 vì thiếu quyền.

Phân biệt trường hợp này đặc biệt hữu ích khi client báo “URL hợp lệ trên máy tôi nhưng production trả 400”, khi có reverse proxy thay đổi path, hoặc khi một request cố tình chứa dấu `;`, `%2F` hay dấu gạch chéo lặp gây cách diễn giải không thống nhất giữa tầng proxy, Spring Security và controller.

## 2. Quan hệ giữa HttpFirewall, exception và handler

| Đối tượng | Trách nhiệm | Điều không nên nhầm |
| --- | --- | --- |
| `HttpFirewall` | Giao diện kiểm tra/bao bọc request và response trước security filters. | Không phải một authorization rule. |
| `StrictHttpFirewall` | Implementation chặt chẽ phổ biến, chặn nhiều request không chuẩn hay có ký tự/method không được phép. | Không có nghĩa mọi URL chứa encoding đều bị chặn; quy tắc chính xác tùy input/phiên bản. |
| `RequestRejectedException` | Tín hiệu **request bị firewall từ chối**; mang nguyên nhân ở dạng exception. | Khác `AuthenticationException` và `AccessDeniedException`. |
| `RequestRejectedHandler` | Xử lý request/response sau khi exception bị bắt, ví dụ trả 400 và log ở mức phù hợp. | Không nên tự “cho qua” request hoặc biến nó thành truy cập hợp lệ. |
| `FilterChainProxy` | Điều phối firewall, chọn security chain và chuyển rejection cho handler tương ứng. | Một `SecurityFilterChain` không tự đảm nhiệm toàn bộ vai trò của proxy. |

Luồng khái niệm:

~~~text
HTTP client / browser
        |
        v
Servlet container / reverse proxy (có thể từ chối sớm)
        |
        v
DelegatingFilterProxy -> FilterChainProxy
        |
        +--> HttpFirewall.getFirewalledRequest(request)
        |        |
        |        +-- Hợp lệ --> FirewalledRequest
        |        |                 |
        |        |                 +--> chọn SecurityFilterChain
        |        |                 +--> security filters
        |        |                 +--> DispatcherServlet / controller
        |        |
        |        +-- Không hợp lệ --> RequestRejectedException
        |                                  |
        |                                  v
        |                          RequestRejectedHandler
        |                                  |
        |                                  +--> response 400 (ví dụ)
        |
        +--> HttpFirewall.getFirewalledResponse(response)
~~~

Sơ đồ diễn tả trách nhiệm, không phải thứ tự từng lệnh nguồn code của một phiên bản cụ thể. Quan trọng nhất là **rejection xảy ra trong vùng thực thi của `FilterChainProxy`, trước các xử lý bảo mật/nghiệp vụ thông thường**.

Nếu proxy hay Servlet container đã từ chối request trước khi nó đến Spring Security, ứng dụng có thể vẫn trả 400 nhưng **không có `RequestRejectedException` của Spring Security**. Phải xác định nơi tạo response bằng log và quan sát hạ tầng.

## 3. `RequestRejectedException` là gì?

`org.springframework.security.web.firewall.RequestRejectedException` là exception biểu thị request vi phạm yêu cầu của firewall. Ví dụ thường gặp với cấu hình `StrictHttpFirewall` mặc định hoặc chặt tương đương:

1. **Path không chuẩn hóa:** các cách biểu diễn đường dẫn có thể khiến các tầng diễn giải khác nhau, ví dụ các biến thể `..`, slash kép hoặc ký tự phân cách bất thường.
2. **URL encoding gây mơ hồ:** một số biểu diễn mã hóa như encoded slash (`%2F`), backslash (`%5C`) hoặc percent encoding được firewall kiểm soát chặt.
3. **Dấu chấm phẩy/matrix parameters:** `/items;version=1` có thể bị chặn khi không cho phép semicolon, nhằm tránh cách parse path khác nhau giữa các tầng.
4. **HTTP method không được phép:** một số method như `TRACE` không nằm trong danh sách mặc định của `StrictHttpFirewall`.
5. **Tên/giá trị header hoặc parameter đáng ngờ:** các ký tự điều khiển hay dữ liệu không thỏa policy an toàn có thể bị từ chối trong những phiên bản hỗ trợ kiểm tra này.

Không phải mọi chuỗi ví dụ đều đi đến Spring Security dưới đúng dạng ban đầu. Container, load balancer và proxy có thể giải mã, chuẩn hóa hoặc chặn request trước đó. Cũng không phải cứ “URL có dấu %” là chắc chắn bị chặn. Luôn thử **đúng path, đúng method, đúng cấu hình, đúng tầng tiếp nhận**.

### Ví dụ: vì sao URL normalization liên quan đến security?

Hãy hình dung proxy dùng chuỗi path ban đầu để quyết định một route có thuộc `/admin/**` hay không, trong khi component khác đã giải mã `%2F` hoặc loại `..` trước khi chọn controller. Nếu hai tầng nhìn nhận đường dẫn khác nhau, yêu cầu có thể đi qua một rule không dành cho endpoint thực sự. Firewall giảm nhóm rủi ro này bằng cách từ chối các biểu diễn mơ hồ.

Một đường dẫn hợp lệ, đã chuẩn hóa rõ ràng nên được ưu tiên hơn việc nới lỏng firewall chỉ để cho phép nhiều kiểu mã hóa tương đương.

### Bản chất của exception

- Exception **không chứng minh client đang tấn công**. Nó nói rằng request vi phạm policy firewall hiện hành; có thể do URL hợp lệ trong hệ thống cũ, proxy encoding hai lần, crawler, lỗi HTTP client hoặc tác nhân xấu.
- Không dùng nguyên `exception.getMessage()` làm nội dung response công khai. Message có thể chứa chi tiết request và dữ liệu do client kiểm soát; phản chiếu ra response tạo rủi ro tiết lộ cấu hình, log injection hoặc thông tin không cần thiết.
- Không “catch rồi bỏ qua” để chạy tiếp `FilterChainProxy`. Request đã bị đánh dấu không hợp lệ cần được xử lý tại ranh giới firewall, hoặc sửa cách client/proxy tạo request.

## 4. `RequestRejectedHandler` xử lý exception ở đâu và ra sao?

`org.springframework.security.web.firewall.RequestRejectedHandler` là functional interface ở tầng web security. Hợp đồng cốt lõi:

~~~java
void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        RequestRejectedException requestRejectedException)
        throws IOException, ServletException;
~~~

Đây là chữ ký để giải thích API; khi viết file Java thật cần import các class Servlet/Spring Security. Handler được gọi khi luồng `FilterChainProxy` bắt được `RequestRejectedException` trong phạm vi xử lý của nó.

Handler được quyền **quyết định response**:

- Đặt status HTTP, thường là 400.
- Gửi body ổn định nếu API cần JSON, ví dụ `application/problem+json`.
- Ghi log hoặc metric đã lọc thông tin, phục vụ vận hành.
- Không trả nội dung từ exception message/URI thô nếu chưa có bộ lọc log và lý do bảo mật rõ ràng.

Handler không có nhiệm vụ cấp quyền, tạo authentication, làm CSRF check hay phân tích JSON body cho controller. Đó là những phần khác của pipeline.

### 4.1. Dùng sẵn `HttpStatusRequestRejectedHandler`

Nếu chỉ cần HTTP status, `HttpStatusRequestRejectedHandler` là lựa chọn gọn:

~~~java
RequestRejectedHandler handler =
    new HttpStatusRequestRejectedHandler(400);
~~~

Đây là fragment API, cần import `org.springframework.security.web.firewall.RequestRejectedHandler` và `HttpStatusRequestRejectedHandler` trong dự án có Spring Security. Handler dạng này gửi lỗi HTTP với status được cấu hình. Cụ thể server trả body HTML/JSON gì sau `sendError` còn tùy Servlet container, error dispatch và ứng dụng.

Các phiên bản/cấu hình Spring Security hiện đại thường dùng cách phản hồi 400 cho firewall rejection. Để tránh suy đoán thông điệp hoặc body mặc định, hãy kiểm tra phản hồi thực tế trong phiên bản đang chạy; muốn body JSON cố định thì dùng handler riêng.

### 4.2. Tùy biến: JSON ổn định, không lộ nội dung request

Một API có thể muốn lỗi cố định:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json;charset=UTF-8

{"type":"about:blank","title":"Bad Request","status":400,"detail":"Invalid HTTP request"}
~~~

Đây là **mẫu response từ custom handler** ở mục 6, không phải cam kết body do Spring Security tự phát sinh. Giữ thông điệp chung, không đưa URI lỗi, token, cookie hoặc exception message vào response.

## 5. Khác gì với 401/403 và lỗi MVC?

| Tình huống | Thành phần thường xử lý | Status thường gặp |
| --- | --- | --- |
| Path/header/method bị firewall từ chối | `HttpFirewall` → `RequestRejectedException` → `RequestRejectedHandler` | 400 với handler status thông dụng |
| User chưa đăng nhập vào tài nguyên cần xác thực | `AuthenticationEntryPoint` | 401 hoặc redirect login |
| User đăng nhập nhưng thiếu quyền | `AccessDeniedHandler` | 403 |
| POST dùng session cookie thiếu CSRF token | `CsrfFilter` và xử lý access denied | 403 |
| Controller validate body thất bại | Spring MVC exception handling | Thường 400 |
| Servlet container tự từ chối HTTP request lỗi | Container/proxy | Thường 400, không nhất thiết có exception Spring Security |

**Cùng status 400 không có nghĩa cùng nguyên nhân.** Với firewall rejection, controller và `@ControllerAdvice` có thể chưa chạy. Với `@Valid` hoặc lỗi parse JSON trong controller argument resolution, xử lý thường xảy ra ở MVC và dùng cơ chế exception handler của MVC.

Không nên giải quyết một lỗi 400 bằng cách thêm `permitAll()` cho URL bị chặn. `permitAll` là quy tắc authorization cho request đã tới giai đoạn đó; firewall quyết định có chấp nhận hình thức request trước tiên hay không.

## 6. Cấu hình Spring Boot/Spring Security 6: handler tùy chỉnh

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/Spring MVC, các dependency `spring-boot-starter-web` và `spring-boot-starter-security`. Các file cùng package `com.example.firewalldemo`. Đây là **các file Java của ứng dụng Spring Boot**, không phải chương trình một file chạy với `javac` thiếu dependency.

### 6.1. Điểm khởi động ứng dụng

**`src/main/java/com/example/firewalldemo/FirewallDemoApplication.java`:**

~~~java
package com.example.firewalldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FirewallDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FirewallDemoApplication.class, args);
    }
}
~~~

### 6.2. Tạo `RequestRejectedHandler` trả JSON

**`src/main/java/com/example/firewalldemo/JsonRequestRejectedHandler.java`:**

~~~java
package com.example.firewalldemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.RequestRejectedHandler;

public final class JsonRequestRejectedHandler implements RequestRejectedHandler {

    private static final Logger log =
            LoggerFactory.getLogger(JsonRequestRejectedHandler.class);

    private static final String BODY =
            "{\"type\":\"about:blank\","
          + "\"title\":\"Bad Request\","
          + "\"status\":400,"
          + "\"detail\":\"Invalid HTTP request\"}";

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            RequestRejectedException exception) throws IOException {

        // Không ghi raw URL, headers, query string hoặc message của exception.
        log.warn("HttpFirewall rejected a request; exceptionType={}",
                exception.getClass().getSimpleName());

        if (response.isCommitted()) {
            // Không thể ghi status/body mới khi response đã committed.
            return;
        }

        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.getWriter().write(BODY);
    }
}
~~~

`RequestRejectedHandler.handle` cho phép khai báo `IOException, ServletException`; implementation này chỉ cần `IOException`. Mã dùng UTF-8, status 400 và body cố định để không lộ URL bị từ chối. `response.isCommitted()` tránh ghi vào response đã gửi; thực tế một firewall rejection thường xuất hiện trước khi response được commit.

Ứng dụng có thể ghi thêm metric theo tên rule đã được chuẩn hóa, nhưng cần chú ý **cardinality**: không lấy nguyên URL/query hoặc exception message làm label metric vì attacker có thể tạo vô số giá trị khác nhau.

### 6.3. Lắp firewall và handler vào `WebSecurity`

**`src/main/java/com/example/firewalldemo/SecurityConfig.java`:**

~~~java
package com.example.firewalldemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.RequestRejectedHandler;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class SecurityConfig {

    @Bean
    StrictHttpFirewall strictHttpFirewall() {
        // Giữ các kiểm tra chặt mặc định.
        return new StrictHttpFirewall();
    }

    @Bean
    RequestRejectedHandler requestRejectedHandler() {
        return new JsonRequestRejectedHandler();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(
            StrictHttpFirewall firewall,
            RequestRejectedHandler rejectedHandler) {

        return web -> {
            web.httpFirewall(firewall);
            web.requestRejectedHandler(rejectedHandler);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/hello").permitAll()
                .anyRequest().authenticated())
            .build();
    }
}
~~~

**Vì sao dùng `WebSecurityCustomizer`?** `HttpSecurity` chủ yếu xây dựng một `SecurityFilterChain`. Trong khi đó, `HttpFirewall` và `RequestRejectedHandler` gắn với **`FilterChainProxy`**, bộ điều phối bao ngoài các security chains. Cấu hình `WebSecurityCustomizer` cho phép thiết lập hai thành phần đúng nơi; cấu hình `authorizeHttpRequests` không thay thế chúng.

Ứng dụng không cần tạo thủ công một `FilterChainProxy` hoặc tự đăng ký thêm `CorsFilter`/`DelegatingFilterProxy` chỉ để triển khai handler trên. Spring Security/Spring Boot đã xây dựng và nối bộ lọc khi các starter và security configuration phù hợp được nạp.

### 6.4. Controller hợp lệ để đối chiếu

**`src/main/java/com/example/firewalldemo/HelloController.java`:**

~~~java
package com.example.firewalldemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "ok");
    }
}
~~~

Với request hợp lệ `GET /api/hello`, handler trong controller trả:

~~~json
{"message":"ok"}
~~~

Với request bị `StrictHttpFirewall` từ chối và được `FilterChainProxy` chuyển tới custom handler, response có status 400 và body JSON cố định mô tả ở mục 4. Không vì có controller `permitAll` mà một URL bất thường được chấp nhận.

### 6.5. Cách chạy dự án

Thêm đúng các starter Spring Web và Security; Spring Boot 3.x sử dụng Jakarta Servlet API (`jakarta.servlet.*`). Đặt các file theo package trên trong project Spring Boot, rồi dùng build tool của dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows với Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Lệnh chỉ có ý nghĩa khi dự án đã có Gradle wrapper và plugin Spring Boot. Ví dụ Maven tương đương là `./mvnw spring-boot:run`. Bài này không cung cấp một build.gradle tổng quát cho mọi phiên bản; dùng dependency versions do Spring Boot BOM quản lý để Spring Security và Spring MVC tương thích.

## 7. Dùng handler có sẵn thay vì JSON tùy chỉnh

Không phải ứng dụng nào cũng cần body JSON do chính nó viết. Nếu chỉ cần status 400, có thể dùng handler có sẵn. Đây là **phương án thay thế** cho bean `requestRejectedHandler` ở mục 6; không đăng ký thêm hai bean cùng kiểu rồi kỳ vọng Spring tự chọn:

~~~java
@Bean
RequestRejectedHandler requestRejectedHandler() {
    return new HttpStatusRequestRejectedHandler(400);
}
~~~

Các import liên quan:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.firewall.HttpStatusRequestRejectedHandler;
import org.springframework.security.web.firewall.RequestRejectedHandler;
~~~

Đây là fragment ở trong một `@Configuration` class có `WebSecurityCustomizer` gắn handler. `HttpStatusRequestRejectedHandler` phù hợp nếu client chỉ cần mã lỗi và không yêu cầu body nhất quán. Thông điệp lỗi/HTML do container tạo sau `sendError` không nên coi là hợp đồng API cố định nếu chưa kiểm chứng.

### Khi nào nên chọn custom handler?

- API công khai có error contract rõ ràng `application/problem+json`.
- Cần log an toàn hoặc metric cố định cho request bị chặn mà không tiết lộ input.
- Muốn cùng một cấu trúc response cho các rejection xảy ra tại firewall.

Ngay cả khi trả JSON, không biến handler thành “normalizer” âm thầm sửa URL, xóa ký tự rồi chạy lại request. Việc này có thể làm thay đổi endpoint mà client thực sự yêu cầu.

## 8. Hiểu chính sách của `StrictHttpFirewall` trước khi nới lỏng

`StrictHttpFirewall` được thiết kế để từ chối các HTTP request không đáng tin với các biểu diễn có thể dẫn đến khác biệt trong path matching. Một số dự án cũ dùng matrix variables, encoded slash hoặc custom HTTP method; khi bật cấu hình mặc định, request trước đây chấp nhận có thể thành 400.

Cách xử lý ưu tiên:

1. Xác nhận client thực sự cần dạng path/header/method đó hay không.
2. Xác nhận reverse proxy có decode/encode/normalize làm thay đổi request không.
3. Nếu có thể, đổi client sang đường dẫn chuẩn, tránh percent-encode không cần thiết.
4. Chỉ khi có yêu cầu tương thích bắt buộc, đánh giá một tùy chọn firewall cụ thể và các tầng cùng diễn giải path.
5. Có test cho URL hợp lệ, URL độc hại và path matching/authorization trước và sau thay đổi.

Ví dụ chỉ để hiểu API `setAllowedHttpMethods`, **không cần dùng nếu mặc định đáp ứng nghiệp vụ**:

~~~java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowedHttpMethods(java.util.List.of(
    "GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"
));
~~~

Đoạn trên là fragment trong cấu hình Java, không phải class runnable độc lập. Tránh cho phép tất cả method bằng `setUnsafeAllowAnyHttpMethod(true)` để xử lý một trường hợp TRACE/OPTIONS lỗi; nới whitelist làm tăng phạm vi giao thức mà ứng dụng phải xử lý an toàn.

Tương tự, chỉ bật các tùy chọn như cho phép semicolon/encoded slash sau khi kiểm tra kỹ hiệu ứng ở container, reverse proxy, Spring MVC và security matcher. Ký tự được phép ở firewall **không đồng nghĩa** authorization và controller xử lý tương đương, cũng không tự loại rủi ro path traversal.

### `permitAll` và `web.ignoring` không phải giải pháp

- `permitAll` cho một path chỉ ảnh hưởng authorization **sau khi request qua firewall**.
- Đường đi được cấu hình bỏ qua một số security filters không có nghĩa mọi request sẽ tránh được firewall ở `FilterChainProxy`; cần xác định chính xác cấu hình và entrypoint thực tế.
- Không tạo servlet/filter riêng bắt mọi exception rồi trả 200 cho request đã bị từ chối, vì đó là thay đổi chính sách bảo vệ.
- Nếu frontend tạo ra `/api/items;session=…` không tương thích, ưu tiên sửa cách tạo URL hoặc định tuyến phiên, thay vì mở mọi semicolon.

## 9. Kiểm thử đơn vị: chứng minh exception và handler

Để có test ổn định, trước hết kiểm trực tiếp `StrictHttpFirewall` bằng `MockHttpServletRequest` và kiểm handler bằng `MockHttpServletResponse`. Thêm `spring-boot-starter-test` và `spring-security-test` ở test scope nếu dự án cần những thư viện đó; các lớp Mock Servlet nằm trong `spring-test`, còn JUnit 5 do test starter cung cấp.

**`src/test/java/com/example/firewalldemo/FirewallRejectionTest.java`:**

~~~java
package com.example.firewalldemo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FirewallRejectionTest {

    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    @Test
    void rejectsSemicolonInRequestUriByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/items;debug=true");

        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(request));
    }

    @Test
    void rejectsTraceMethodByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("TRACE", "/api/hello");

        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(request));
    }

    @Test
    void normalRequestIsNotRejectedByFirewall() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/hello");

        assertFalse(request.getRequestURI().contains(";"));
        // Không ném exception khi request có dạng hợp lệ.
        assertTrue(firewall.getFirewalledRequest(request) != null);
    }

    @Test
    void customHandlerWritesSanitized400Response() throws Exception {
        JsonRequestRejectedHandler handler =
            new JsonRequestRejectedHandler();

        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/hello");

        MockHttpServletResponse response = new MockHttpServletResponse();

        handler.handle(request, response,
            new RequestRejectedException("sensitive request details"));

        assertEquals(400, response.getStatus());
        assertTrue(response.getContentType()
                .startsWith("application/problem+json"));
        assertTrue(response.getContentAsString()
                .contains("\"detail\":\"Invalid HTTP request\""));
        assertFalse(response.getContentAsString().contains("sensitive"));
    }
}
~~~

Các bài test trên phân biệt hai trách nhiệm:

- Test firewall xác nhận một input cụ thể tạo `RequestRejectedException` **trước khi có controller**.
- Test handler xác nhận error contract trả 400 cố định, không phản chiếu exception message.

Test với `MockHttpServletRequest` kiểm trực tiếp firewall; đây không phải test end-to-end của Servlet container. Với mỗi ứng dụng thực, bổ sung integration test trên `MockMvc` hoặc HTTP test server để xác nhận `WebSecurityCustomizer`, `FilterChainProxy`, proxy và error response được nối đúng như thiết kế.

Chạy trong project Gradle phù hợp:

~~~bash
./gradlew test
~~~

Hoặc Windows:

~~~powershell
.\gradlew.bat test
~~~

**Kỳ vọng:** 4 test hoàn tất thành công với cấu hình và dependencies đúng. Không đưa ra log stdout giả định vì Gradle test logging khác nhau theo dự án.

### Kiểm thử bằng HTTP thật khi debug

Request URL có dấu `;` có thể được thử trên một môi trường nội bộ cho phép kiểm tra:

~~~bash
curl --path-as-is -i "http://localhost:8080/api/items;debug=true"
~~~

`--path-as-is` yêu cầu curl không tự chuẩn hóa một số dạng path trước khi gửi. Tuy nhiên, proxy hoặc Servlet container vẫn có thể chặn/biến đổi request trước Spring. Nếu response 400 không đi qua Spring, test handler trực tiếp vẫn cho kết quả đúng nhưng không chứng minh rằng đường đi production đã đến `FilterChainProxy`.

Để phân biệt 400 firewall với 404 do controller không có route, gửi request hợp lệ `/api/hello` làm đối chứng; ghi lại status, response body và dấu vết logger của handler, tránh log URI chứa dữ liệu nhạy cảm.

## 10. Tương tác với CORS, SecurityFilterChain và reverse proxy

### CORS/preflight

Một request `OPTIONS` hợp lệ phục vụ CORS thường nằm trong danh sách HTTP methods được `StrictHttpFirewall` cho phép. Nhưng một preflight có path/method/header bất thường vẫn có thể bị firewall từ chối **trước khi `CorsFilter` xử lý CORS**. Nếu frontend báo CORS khi server trả 400, cần kiểm tra request có vi phạm firewall không; không thể chữa bằng cách chỉ thêm `Access-Control-Allow-Origin`.

### Nhiều `SecurityFilterChain`

Firewall được áp dụng ở tầng `FilterChainProxy` bao ngoài các chains; một `RequestRejectedHandler` cấu hình cho proxy có thể xử lý rejection xảy ra trước việc chọn chain. Vì thế thêm một rule `requestMatchers("/api/**").permitAll()` ở chain cụ thể không làm đường dẫn bị firewall cấm trở nên hợp lệ.

Nếu ứng dụng chủ động đăng ký nhiều proxy/filter chain qua các điểm vào khác nhau, cần xác định request thực tế đi vào proxy nào; tránh tự suy đoán chỉ dựa vào tên một bean.

### Reverse proxy và container

Một yêu cầu bên ngoài thường trải qua:

~~~text
Client URL
  -> CDN/WAF (có thể lọc)
  -> Reverse proxy / ingress (có thể decode/normalize path)
  -> Servlet container (có thể chặn URI/method/header)
  -> FilterChainProxy / HttpFirewall
  -> SecurityFilterChain
  -> Spring MVC
~~~

Lỗi được báo ở tầng nào tùy request và cách triển khai. Một status 400 do nginx hoặc Tomcat trả về không tự động kích hoạt `RequestRejectedHandler`. So sánh request-target ở proxy và log ứng dụng, nhưng phải bảo vệ dữ liệu khỏi bị log injection và lộ secrets.

### Security và quan sát vận hành

- Dùng status 400 cho request không hợp lệ là phản hồi thực tế thường hợp lý; chỉ chọn mã khác nếu có hợp đồng API/hạ tầng cụ thể.
- Không tiết lộ filter name, rule nội bộ, Java stack trace hay exception message chi tiết cho client.
- Log thống kê số rejection theo nhóm nguồn đã xác thực/sanitize, route nhóm hoặc loại lỗi cố định; không lấy full URL làm tag metric.
- Nếu lượng rejection tăng đột biến, điều tra origin, client rollout, proxy path rewriting và khả năng probe; không tự động nới policy chỉ để giảm số log.

## 11. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng cần xem xét | Cách xác minh và xử lý |
| --- | --- | --- |
| API trả 400 ngay cả khi `permitAll` | Firewall reject trước authorization. | Kiểm tra `RequestRejectedException`/handler logs và path/method. |
| URI chứa `;` chạy cũ nhưng bị 400 sau nâng cấp | Strict firewall chặn semicolon hoặc cách parse path thay đổi. | Sửa URL hoặc đánh giá tương thích có test chặt. |
| URL encoded slash `%2F` bị 400 | Firewall/container/proxy không cho phép cách mã hóa này. | Đọc đúng điểm từ chối, tránh yêu cầu encoded slash khi có thể. |
| Custom `@ControllerAdvice` không bắt được | Exception xảy ra ở `FilterChainProxy`, trước MVC. | Dùng `RequestRejectedHandler` ở web security. |
| Đã đăng nhập nhưng request bị 400 | Authentication không quyết định request có hợp lệ về cú pháp không. | Xử lý encoding/headers/method; không thêm role. |
| Muốn JSON nhưng nhận HTML status 400 | Container tạo error page từ `sendError` hoặc handler mặc định. | Dùng custom handler với body cố định; kiểm tra gateway. |
| Không thấy log custom handler nhưng vẫn 400 | Request bị container/proxy chặn trước Spring. | Xem access/error logs của các tầng trước ứng dụng. |
| Preflight OPTIONS 400 | Method/path/header có thể bị firewall/container từ chối. | Đọc request OPTIONS thật; phân biệt với 403 do CORS policy. |
| Một URL trở thành endpoint khác sau decode | Path normalization khác nhau giữa proxy và MVC. | Ưu tiên URL chuẩn và giữ firewall chặt; test authorization. |
| Log bị xuống dòng/ký tự lạ | Đã log raw URL hoặc exception message do client điều khiển. | Sanitize, log message cố định, tránh dữ liệu nhạy cảm. |

### Trình tự điều tra ngắn

1. Xác nhận status/body 400 được tạo ở container/proxy hay trong ứng dụng.
2. Xem có `RequestRejectedException` và custom handler được gọi không.
3. So sánh URL raw, path sau proxy, HTTP method, headers/parameters có ký tự bất thường; tránh phát tán secrets.
4. Kiểm tra cấu hình `StrictHttpFirewall`, bean `WebSecurityCustomizer` và việc nối `RequestRejectedHandler` vào `FilterChainProxy`.
5. Tạo một request hợp lệ cùng endpoint để loại trừ vấn đề controller/authorization.
6. Chỉ thay đổi policy firewall sau khi có test chứng minh route và authorization không bị lách.

## 12. Những sai lầm cần tránh

**“Mọi 400 đều là RequestRejectedException.”** Không đúng. Spring MVC, container, proxy và gateway đều có thể phát sinh 400 vì lý do khác nhau.

**“RequestRejectedException là AccessDeniedException.”** Không đúng. Rejection thuộc tính hợp lệ của HTTP request; access denied thuộc quyết định cấp quyền sau các bước bảo mật khác.

**“Chỉ cần thêm `permitAll`.”** Không đúng. Firewall chạy trước authorization; một request không đạt tiêu chuẩn hình thức không thể được “cấp quyền” bởi rule bên dưới.

**“Tắt StrictHttpFirewall để xử lý nhanh.”** Cách đó có thể đưa request mơ hồ trở lại path matching. Hãy điều chỉnh URL/client và môi trường trước, nới từng rule chỉ khi có căn cứ.

**“Custom handler nên trả nguyên exception message để dễ debug.”** Không nên. Request URI, encoded data và nội dung do client điều khiển có thể xuất hiện trong message. Response lỗi nên ổn định và không tiết lộ thông tin nhạy cảm.

**“@ControllerAdvice sẽ bắt tất cả.”** Không đúng với exception nằm bên ngoài `DispatcherServlet`/MVC. Muốn tùy chỉnh phản hồi firewall, xử lý ở vị trí `FilterChainProxy` thông qua `RequestRejectedHandler`.

**“Unit test handler pass nghĩa là production có đúng response.”** Test handler chỉ chứng minh logic của handler. Cần xác nhận wiring, servlet container, error page, reverse proxy và security chain thực tế.

## 13. Câu hỏi tự kiểm tra

1. **`RequestRejectedException` thường được tạo trong bước nào?** Khi `HttpFirewall` thấy request không thỏa policy trong quá trình `FilterChainProxy` chuẩn bị xử lý request.
2. **Ai chuyển exception thành HTTP 400?** `RequestRejectedHandler` được cấu hình; `HttpStatusRequestRejectedHandler` là lựa chọn status đơn giản.
3. **`@ControllerAdvice` có luôn thấy exception này không?** Không; rejection thường xảy ra trước khi request vào Spring MVC.
4. **Vì sao một request 400 không nên được “chữa” bằng `permitAll`?** Authorization không thay đổi tiêu chuẩn chấp nhận request của firewall.
5. **Có nên trả `exception.getMessage()` ra client?** Không theo mặc định; message có thể chứa dữ liệu client hoặc chi tiết nội bộ.
6. **Khi production 400 nhưng local không 400, cần so sánh điều gì?** URL/method/header thực, Spring Security version, firewall config, Servlet container, proxy/CDN normalization.
7. **Vì sao không nên cho phép mọi HTTP method?** Tăng các đầu vào mà proxy, firewall, route matching và ứng dụng phải xử lý nhất quán; có thể nới bề mặt tấn công.
8. **Test nào kiểm tra trách nhiệm của handler độc lập với filter chain?** Gọi trực tiếp `handler.handle(mockRequest, mockResponse, new RequestRejectedException(…))` rồi kiểm tra status/body và không tiết lộ message.

**Ghi nhớ:** `RequestRejectedException` là tín hiệu *request không đáp ứng chính sách `HttpFirewall`*; `RequestRejectedHandler` là điểm trả lời HTTP khi `FilterChainProxy` bắt tín hiệu đó. Hãy giữ firewall chặt, chẩn đoán đúng tầng từ chối, trả lỗi 400 an toàn và chỉ nới policy sau khi đã chứng minh cần thiết bằng test.