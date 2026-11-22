# Kiểm thử bằng trình duyệt thay vì chỉ dựa vào kết quả gọi curl

> **Module:** Spring Security – fundamentals  
> **Nhóm:** CORS  
> **Đề bài:** Kiểm thử bằng trình duyệt thay vì chỉ dựa vào kết quả gọi curl  
> **Phạm vi thực hành:** Spring MVC/Servlet, Spring Security 6.5.x, Spring Boot 3.5.7, Java 17+, browser hiện đại và HTTP client dòng lệnh.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ biết cách:

1. Giải thích vì sao API chạy tốt bằng `curl` hoặc Postman nhưng JavaScript `fetch` trên browser lại báo lỗi CORS.
2. Phân biệt **origin**, **site**, **same-origin**, **cross-origin** và **cross-site**.
3. Quan sát request `Origin`, `OPTIONS` preflight và response `Access-Control-Allow-*` bằng DevTools.
4. Nhận ra trường hợp browser chỉ chặn quyền **đọc response** và trường hợp browser chặn **request thật trước preflight**.
5. Thử bốn nhóm lỗi: origin không nằm trong allowlist, header không được phép, method không được phép và credential mode không tương thích.
6. Chạy một lab Java 17+ với frontend tại `127.0.0.1:5500`, API tại `127.0.0.1:8080`, cùng trang frontend ở `127.0.0.1:5501` để tái hiện sự khác biệt.
7. Viết kiểm thử Spring `MockMvc` cho chính sách CORS, nhưng hiểu vì sao MockMvc không thay thế browser thật.
8. Phân biệt CORS với HTTP authentication, authorization, CSRF, CSP, cookie SameSite và lỗi network.
9. Xây dựng checklist QA/CI bao quát preflight, actual request, credentials, redirect, proxy và side effects.

**Thông điệp trọng tâm:** CORS là cơ chế bảo vệ do **browser** thực thi. `curl` có thể kiểm tra response headers của server, nhưng không tự áp Same-Origin Policy/CORS checks như trình duyệt. Vì vậy **“curl nhận 200 OK” không chứng minh “JavaScript của frontend được quyền đọc response”**.

## 2. Khái niệm origin và tại sao khác port cũng đủ gây CORS

Một origin được xác định bằng bộ ba:

~~~text
scheme + hostname + port
~~~

Ví dụ:

| Trang nguồn | URL đích | Cùng origin? | Lý do |
| --- | --- | --- | --- |
| `http://127.0.0.1:5500` | `http://127.0.0.1:8080` | Không | Khác port |
| `http://localhost:5500` | `http://127.0.0.1:5500` | Không | Hostname khác |
| `http://example.test` | `https://example.test` | Không | Scheme khác |
| `https://app.example.test` | `https://api.example.test` | Không | Subdomain khác |
| `https://example.test/a` | `https://example.test/b` | Có | Path không thuộc origin |
| `https://example.test` | `https://example.test:443` | Có | 443 là HTTPS default port |

**Same-Origin Policy** giới hạn JavaScript của website A đọc dữ liệu từ website B khác origin nếu B không cấp quyền CORS phù hợp. Nếu không có ranh giới này, một trang không đáng tin có thể tìm cách đọc dữ liệu từ những hệ thống mà người dùng đang đăng nhập.

**CORS (Cross-Origin Resource Sharing)** là cơ chế theo HTTP headers giúp resource server tuyên bố origin nào được browser cho phép truy cập response.

**Cross-origin không đồng nghĩa cross-site.** Cookie `SameSite` dùng khái niệm site, có thể bao trùm nhiều subdomains; trong khi CORS kiểm tra origin đầy đủ (scheme, hostname, port). Một frontend `app.example.test` gọi `api.example.test` có thể là cross-origin nhưng vẫn same-site tùy scheme/domain. Vì vậy không được đồng nhất CORS với cookie policy hoặc CSRF.

## 3. Browser khác curl ở điểm cốt lõi nào?

Giả sử backend có endpoint:

~~~http
GET /api/public HTTP/1.1
Host: 127.0.0.1:8080
~~~

Dùng CLI:

~~~bash
curl -i http://127.0.0.1:8080/api/public
~~~

Curl không gắn request vào một trang web có origin `http://127.0.0.1:5501`, nên nó không tự gửi preflight và không tự thực hiện CORS response check. Nếu API trả 200 với JSON, curl đọc được.

Nhưng từ trang `http://127.0.0.1:5501`:

~~~javascript
fetch("http://127.0.0.1:8080/api/public")
  .then(response => response.json())
  .then(console.log)
  .catch(console.error);
~~~

Browser biết script đến từ origin 5501. Nếu backend chỉ cho phép 5500, browser không cho script ở 5501 đọc response; promise có thể reject bằng `TypeError`, trong DevTools có thông báo CORS cụ thể.

### Bảng đối chiếu

| Phép kiểm | Browser `fetch` | curl thông thường |
| --- | --- | --- |
| Nhận biết origin của trang JavaScript | Có | Không |
| Tự gửi `Origin` khi cần | Có | Người dùng có thể tự thêm |
| Tự gửi preflight `OPTIONS` | Có nếu request cần | Không |
| Thực thi `Access-Control-Allow-Origin` | Có | Không |
| Thực thi `Allow-Methods`/`Allow-Headers` cho preflight | Có | Không |
| Xét `credentials`, cookies, SameSite/Secure | Có | Không theo chính sách browser |
| Chặn JavaScript đọc response trái CORS | Có | Không |
| Áp CSP, mixed content, browser privacy settings | Có | Không cùng cơ chế |
| Kiểm tra HTTP status/body ở backend | Có khi được đọc response | Có |
| Mô phỏng preflight bằng tay | Không cần, browser tự làm | Có thể gửi `OPTIONS` thủ công |

Vì vậy, curl và browser **không thay thế nhau**: curl hữu ích để kiểm tra HTTP connectivity, status, headers, payload; browser cần thiết để kiểm tra browser enforcement.

Một chi tiết quan trọng: nếu curl **cố tình** gửi header `Origin` bị từ chối, Spring CORS processor có thể trả 403. Điều này kiểm tra server policy khi nhìn thấy Origin, nhưng **curl vẫn không tự áp quy tắc CORS lên kết quả** như browser. Tùy implementation, server khác có thể trả 200 không có CORS header, curl vẫn đọc body trong khi browser chặn.

## 4. Browser gửi preflight khi nào?

### 4.1. Request đơn giản — không nhất thiết có OPTIONS

Ví dụ:

~~~javascript
fetch("http://127.0.0.1:8080/api/public");
~~~

Với một GET đơn giản không có các header đặc biệt, browser thường gửi GET trực tiếp rồi kiểm tra CORS headers trên response:

~~~text
Browser tại 5500
  |
  +-- GET /api/public
  |   Origin: http://127.0.0.1:5500
  v
API ở 8080
  |
  +-- 200 OK
  |   Access-Control-Allow-Origin: http://127.0.0.1:5500
  v
Browser cho JS đọc response
~~~

Nếu server không cho phép origin, request GET **có thể đã được xử lý** nhưng JavaScript vẫn không được đọc response. Không được hiểu thông báo CORS failure là bằng chứng request chưa tới backend.

### 4.2. Request không đơn giản — browser gửi OPTIONS trước

Ví dụ:

~~~javascript
fetch("http://127.0.0.1:8080/api/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Demo-Tag": "browser"
  },
  body: JSON.stringify({ message: "hello" })
});
~~~

`Content-Type: application/json` không thuộc các CORS-safelisted content types cho simple requests; `X-Demo-Tag` là custom header. Browser sẽ thực hiện **preflight OPTIONS**:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-demo-tag
~~~

Nếu server đồng ý, response có các thông tin kiểu:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://127.0.0.1:5500
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-Demo-Tag
~~~

Sau đó browser gửi **POST thực**. Nếu preflight bị từ chối, browser **không gửi POST thật sau preflight đó**. Đây là phép thử cần quan sát bằng Network tab, không thể suy luận từ curl POST.

### 4.3. Preflight không phải request đăng nhập

Theo mô hình CORS/Fetch, preflight không mang cookies/credentials thông thường như `JSESSIONID`. Vì thế Spring Security khuyến nghị **xử lý CORS trước authentication/authorization** để OPTIONS không bị trả 401 chỉ vì chưa có session cookie.

Preflight **không cấp quyền nghiệp vụ** và không chứng minh người dùng đang đăng nhập. Sau khi preflight thành công, request thật vẫn cần authentication, authorization, CSRF protection nếu có cookie-based state-changing operations.

### 4.4. Tại sao đôi khi không thấy OPTIONS?

Có thể là:

- Request GET/POST thuộc nhóm simple request nên không cần preflight.
- Browser đã cache kết quả preflight theo `Access-Control-Max-Age`.
- DevTools đang lọc request, ví dụ chỉ hiện Fetch/XHR hoặc ẩn loại OPTIONS.
- Request không xảy ra do JavaScript error, CSP, mixed content, DNS, TLS hoặc kết nối thất bại trước đó.
- Có Service Worker hoặc tầng cache làm thay đổi luồng thực tế.

Đừng “sửa lỗi” vì chỉ không thấy OPTIONS. Hãy xác định request có thuộc loại cần preflight không và kiểm tra toàn bộ Network.

## 5. Các header phải kiểm tra

| Header | Nguồn | Vai trò |
| --- | --- | --- |
| `Origin` | Browser request | Origin của script thực hiện request |
| `Access-Control-Request-Method` | OPTIONS request | HTTP method thật dự kiến |
| `Access-Control-Request-Headers` | OPTIONS request | Các request headers cần được cấp phép |
| `Access-Control-Allow-Origin` | Response | Origin được phép chia sẻ response |
| `Access-Control-Allow-Methods` | OPTIONS response | Danh sách methods được cho phép |
| `Access-Control-Allow-Headers` | OPTIONS response | Danh sách request headers được cho phép |
| `Access-Control-Allow-Credentials` | Response | Có cho credentialed requests hay không |
| `Access-Control-Expose-Headers` | Response | Response headers JS được đọc ngoài nhóm safelisted |
| `Access-Control-Max-Age` | OPTIONS response | Thời gian cache preflight |
| `Vary: Origin` | Response | Giúp cache phân biệt response theo Origin |

**Lưu ý:** Các giá trị method/header là case-insensitive theo quy tắc HTTP phù hợp. Browser có thể liệt kê tên header bằng chữ thường, Spring trả tên bằng cách viết khác. Đừng viết assertion cứng với thứ tự tùy ý nếu điều đó không phải yêu cầu của hệ thống.

Một response có `HTTP 200` nhưng thiếu `Access-Control-Allow-Origin` hợp lệ vẫn có thể bị browser chặn. Để chẩn đoán, phải nhìn **cả request headers, response headers, browser console và URL origin**.

## 6. Demo hoàn chỉnh bằng Java 17 + Spring Boot

Dự án có ba thành phần chạy độc lập:

~~~text
Frontend được phép:        http://127.0.0.1:5500
Backend Spring Boot:       http://127.0.0.1:8080
Frontend không được phép:  http://127.0.0.1:5501
~~~

Backend chỉ chấp nhận CORS từ port **5500**. Frontend port **5501** sử dụng cùng HTML nhưng bị hạn chế bởi origin allowlist.

Các endpoint:

- `GET /api/public`: JSON public, request đơn giản.
- `GET /api/stats`: số lần POST thực sự xử lý.
- `POST /api/echo`: nhận JSON, tăng counter và trả header có thể expose.
- `OPTIONS /api/echo`: preflight do browser tự gửi khi POST có JSON/custom header.

**Phạm vi an toàn:** Demo này không có login/cookie; endpoint POST chỉ tăng bộ đếm trong RAM. Security tắt CSRF **trong API demo stateless không dùng ambient credentials** để cô lập CORS. Không sao chép nguyên thiết kế sang API có cookie login và dữ liệu thực.

### 6.1. Thư mục dự án

~~~text
cors-browser-lab/
  pom.xml
  PreviewServer.java
  frontend/
    index.html
  src/main/java/com/example/corslab/
    CorsBrowserLabApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/corslab/
    CorsBrowserLabTests.java
~~~

### 6.2. pom.xml

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
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>cors-browser-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
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
~~~

### 6.3. CorsBrowserLabApplication.java

~~~java
package com.example.corslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsBrowserLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsBrowserLabApplication.class, args);
    }
}
~~~

### 6.4. SecurityConfig.java

~~~java
package com.example.corslab;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://127.0.0.1:5500"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-Demo-Tag"));
        cors.setExposedHeaders(List.of("X-Demo-Result"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(0L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").permitAll()
                .anyRequest().denyAll());

        return http.build();
    }
}
~~~

Giải thích:

- `UrlBasedCorsConfigurationSource` cấu hình CORS cho `/api/**` và được Spring Security sử dụng thông qua `.cors(...)`.
- Chỉ origin `http://127.0.0.1:5500` được phép, không có wildcard.
- Methods gồm GET, POST, OPTIONS; custom headers được phép gồm `Content-Type` và `X-Demo-Tag`.
- Khi gửi header `X-Not-Allowed`, preflight sẽ bị từ chối.
- `Access-Control-Expose-Headers` cho phép JS đọc response header `X-Demo-Result`.
- `setAllowCredentials(false)` nghĩa demo không cấp credentialed CORS access.
- `setMaxAge(0L)` để giảm caching trong bài tập, giúp quan sát preflight rõ hơn.
- `STATELESS` tránh dùng session để khôi phục authentication của Spring Security.
- `csrf(AbstractHttpConfigurer::disable)` là **chủ ý trong lab không có cookie authentication và không xử lý dữ liệu thật**, không phải khuyến nghị chung.
- `requestMatchers("/api/**").permitAll()` khiến lab tách biệt biến CORS; production cần authentication/authorization riêng.

### 6.5. DemoController.java

~~~java
package com.example.corslab;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final AtomicInteger posts = new AtomicInteger();

    public record EchoInput(String message) {}

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "public");
    }

    @GetMapping("/stats")
    public Map<String, Integer> stats() {
        return Map.of("acceptedPosts", posts.get());
    }

    @PostMapping("/echo")
    public ResponseEntity<Map<String, Object>> echo(
            @RequestBody EchoInput request,
            @RequestHeader(value = "X-Demo-Tag",
                           defaultValue = "none") String tag
    ) {
        int current = posts.incrementAndGet();
        return ResponseEntity.ok()
            .header("X-Demo-Result", "accepted")
            .body(Map.of(
                "message", request.message(),
                "tag", tag,
                "acceptedPosts", current
            ));
    }

    int currentAcceptedPosts() {
        return posts.get();
    }
}
~~~

Controller chỉ làm mutation trong `@PostMapping`, không khi browser hỏi OPTIONS. Bộ đếm cho phép kiểm chứng: request preflight thất bại **không làm POST được thực thi**. Tuy nhiên lưu ý request **simple POST** có thể tới server rồi browser mới block response; CORS không phải cơ chế ngăn mọi loại side effect.

### 6.6. application.properties

~~~properties
server.address=127.0.0.1
server.port=8080
~~~

API chỉ bind loopback trong lab, hạn chế vô tình mở lên mạng bên ngoài. Dùng đúng hostname `127.0.0.1` ở frontend/browser để origin khớp cấu hình.

### 6.7. PreviewServer.java — frontend server thuần Java 17

File đặt ở gốc `cors-browser-lab/PreviewServer.java`:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class PreviewServer {
    public static void main(String[] args) throws IOException {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 5500;
        byte[] html = Files.readAllBytes(Path.of("frontend/index.html"));

        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", port), 0
        );

        server.createContext("/", exchange -> {
            exchange.getResponseHeaders().set(
                "Content-Type", "text/html; charset=UTF-8"
            );
            exchange.getResponseHeaders().set(
                "Cache-Control", "no-store"
            );

            exchange.sendResponseHeaders(200, html.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(html);
            }
        });

        server.start();
        System.out.println("Frontend origin: http://127.0.0.1:" + port);
    }
}
~~~

Chạy từ thư mục gốc của dự án:

~~~bash
java --add-modules jdk.httpserver PreviewServer.java 5500
~~~

Stdout kỳ vọng:

~~~text
Frontend origin: http://127.0.0.1:5500
~~~

`PreviewServer` dùng module `jdk.httpserver` có sẵn trong JDK 17. Không yêu cầu Node/Python. Nó chỉ phục vụ một file HTML cố định ở loopback, **không phải web server production**.

Không mở frontend qua đường dẫn `file://` vì có thể tạo opaque origin/`Origin: null` khác hẳn bài tập.

### 6.8. frontend/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CORS browser lab</title>
  <style>
    body { font: 16px/1.5 system-ui, sans-serif;
           max-width: 850px; margin: 3rem auto; padding: 0 1rem; }
    button { margin: .3rem; padding: .65rem 1rem; cursor: pointer; }
    pre { white-space: pre-wrap; word-break: break-word;
          background: #eee; padding: 1rem; min-height: 150px; }
  </style>
</head>
<body>
  <h1>CORS browser test</h1>
  <p>Frontend origin: <strong id="origin"></strong></p>
  <p>Backend URL: http://127.0.0.1:8080</p>

  <button id="simple">1. Simple GET</button>
  <button id="allowed">2. Allowed JSON POST</button>
  <button id="blocked">3. Blocked header POST</button>
  <button id="credentials">4. Credentialed GET</button>
  <button id="stats">5. Read POST counter</button>

  <pre id="log"></pre>

  <script>
    const api = "http://127.0.0.1:8080";
    const log = document.getElementById("log");
    document.getElementById("origin").textContent = location.origin;

    function line(message) {
      log.textContent += message + "\n";
    }

    async function run(label, action) {
      line("\n" + label);
      try {
        const response = await action();
        line("HTTP available to JS: " + response.status);
        line("X-Demo-Result: " +
            response.headers.get("X-Demo-Result"));
        line("Body: " + await response.text());
      } catch (error) {
        line("Fetch error: " + error.name + ": " + error.message);
        line("Inspect DevTools Console and Network for CORS details.");
      }
    }

    document.getElementById("simple").onclick = () =>
      run("Simple GET", () => fetch(api + "/api/public"));

    document.getElementById("allowed").onclick = () =>
      run("Allowed JSON POST", () => fetch(api + "/api/echo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Demo-Tag": "browser"
        },
        body: JSON.stringify({ message: "hello from browser" })
      }));

    document.getElementById("blocked").onclick = () =>
      run("Denied header preflight", () => fetch(api + "/api/echo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Not-Allowed": "test"
        },
        body: JSON.stringify({ message: "should not be posted" })
      }));

    document.getElementById("credentials").onclick = () =>
      run("Credentialed GET", () => fetch(api + "/api/public", {
        credentials: "include"
      }));

    document.getElementById("stats").onclick = () =>
      run("Read counter", () => fetch(api + "/api/stats"));
  </script>
</body>
</html>
~~~

JavaScript này thực sự chạy trong browser, phát request theo `fetch` và tuân theo CORS. Phần log hiển thị response **chỉ khi JavaScript được browser phép truy cập**; khi bị chặn, thông báo có thể là `TypeError: Failed to fetch`, trong khi DevTools Network vẫn cho thấy các HTTP requests đã xảy ra.

### 6.9. Chạy toàn bộ lab

Mở các terminal trong thư mục dự án.

**Terminal 1 — backend:**

~~~bash
mvn clean test
mvn spring-boot:run
~~~

**Terminal 2 — frontend được phép:**

~~~bash
java --add-modules jdk.httpserver PreviewServer.java 5500
~~~

Mở trang:

~~~text
http://127.0.0.1:5500
~~~

**Terminal 3 — frontend origin không được phép (tùy chọn):**

~~~bash
java --add-modules jdk.httpserver PreviewServer.java 5501
~~~

Mở trang:

~~~text
http://127.0.0.1:5501
~~~

Hai frontend dùng **cùng file HTML**. Khác duy nhất là port/origin, nên dễ cô lập nguyên nhân CORS. Dừng process cũ nếu port đã được dùng. Không tự sửa backend allowlist trong khi đang đo đạc nếu mục tiêu là so sánh đúng/sai.

## 7. Kết quả kỳ vọng và cách quan sát trên browser

| Nút / phép thử | Origin frontend | Preflight? | Hành vi dự kiến | POST thực có xảy ra? |
| --- | --- | --- | --- | --- |
| Simple GET | 5500 | Thường không | JS đọc 200/JSON | Không |
| Allowed JSON POST | 5500 | Có | OPTIONS pass, POST 200 | Có, counter tăng |
| Blocked header POST | 5500 | Có | OPTIONS bị từ chối, JS báo CORS | Không |
| Credentialed GET | 5500 | Thường không | JS bị chặn do thiếu ACA-Credentials | Không, chỉ GET có thể đã tới |
| Simple GET | 5501 | Thường không | JS bị chặn do origin không cho phép | Không, GET có thể đã tới |
| JSON POST | 5501 | Có | Preflight không cho origin | Không |

**Chú ý:** Giá trị HTTP status do Spring trả ở request bị reject có thể là 403. Với nhiều hệ thống khác, server có thể trả 200 nhưng không có CORS headers; browser vẫn chặn JS. Không lấy riêng status 200/403 làm điều kiện duy nhất.

### 7.1. Mở DevTools

1. Truy cập `http://127.0.0.1:5500`.
2. Nhấn `F12`, mở **Network** và **Console**.
3. Bật Preserve log nếu có redirect; kiểm tra request filter không ẩn OPTIONS.
4. Bấm nút **Simple GET**; tìm GET /api/public.
5. Bấm nút **Allowed JSON POST**; tìm OPTIONS trước, POST sau.
6. Bấm **Blocked header POST**; so sánh OPTIONS với trường hợp trước.
7. Bấm **Read POST counter** để kiểm tra side effect.
8. Mở cùng trang ở cổng 5501 và lặp lại.
9. Quan sát cả request headers và response headers, không chỉ dòng lỗi màu đỏ.

### 7.2. Case A: GET đơn giản từ origin hợp lệ

Network dự kiến:

~~~http
GET /api/public HTTP/1.1
Origin: http://127.0.0.1:5500
~~~

Response có:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://127.0.0.1:5500
~~~

JS đọc được JSON:

~~~json
{"status":"public"}
~~~

Đây là kết quả **kỳ vọng từ code**, không phải kết quả đã chạy trong tài liệu. Không có OPTIONS là bình thường vì GET này không cần preflight.

### 7.3. Case B: POST JSON với header được phép

Browser trước hết gửi:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-demo-tag
~~~

Backend xác nhận origin, method, header. Browser sau đó mới gửi:

~~~http
POST /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Content-Type: application/json
X-Demo-Tag: browser

{"message":"hello from browser"}
~~~

Response dự kiến 200 với `X-Demo-Result: accepted` và JSON có `acceptedPosts`. Nếu browser đọc được `X-Demo-Result` qua `response.headers.get(...)`, đó là do backend đã thêm `Access-Control-Expose-Headers: X-Demo-Result`.

### 7.4. Case C: header không được phép

Nút `Blocked header POST` làm browser yêu cầu:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-not-allowed
~~~

`X-Not-Allowed` không có trong allowlist. Spring CORS processor từ chối preflight. Trong Network, bạn có thể thấy HTTP 403 ở OPTIONS, nhưng **không có POST thật sau đó**. Counter không tăng.

Kết quả này khác với một GET đơn giản bị chặn **chỉ ở bước đọc response**, nơi backend có thể đã xử lý GET rồi.

### 7.5. Case D: origin bị cấm

Truy cập HTML từ `http://127.0.0.1:5501`, bấm Simple GET. Origin lúc này là 5501. Spring CORS config chỉ cho phép 5500; browser không cho phép đọc response. Đừng thay URL backend, bởi mục tiêu bài tập chỉ đổi origin trang nguồn.

### 7.6. Case E: credentials include

Nút `Credentialed GET` chạy:

~~~javascript
fetch("http://127.0.0.1:8080/api/public", {
  credentials: "include"
});
~~~

Browser yêu cầu response phải tương thích credential mode. Nhưng backend demo đặt `allowCredentials(false)` và không trả `Access-Control-Allow-Credentials: true`, nên JavaScript bị chặn. Điều này xảy ra **dù server không có user cookie trong demo**: fetch credentials mode vẫn ảnh hưởng CORS validation.

Một GET đơn giản có thể thực sự tới backend và response hiển thị trong Network, nhưng JavaScript không đọc được. Đây không phải lỗi server đã cố tình giữ bí mật nào, mà là policy do lab đặt ra.

## 8. Tại sao curl vẫn hữu ích nhưng không đủ?

### 8.1. Curl không mang Origin mặc định

~~~bash
curl -i http://127.0.0.1:8080/api/public
~~~

Kỳ vọng 200 và JSON. Điều này **không kiểm tra** browser từ origin 5501 có được đọc response hay không.

### 8.2. Curl gửi Origin hợp lệ

~~~bash
curl -i \
  -H "Origin: http://127.0.0.1:5500" \
  http://127.0.0.1:8080/api/public
~~~

Kỳ vọng có `Access-Control-Allow-Origin` cho 5500. Có thể dùng curl để xem server-side CORS headers, nhưng không kiểm được browser preflight cache, credential mode, CSP, cookies hoặc khả năng JS đọc response.

### 8.3. Curl mô phỏng preflight

~~~bash
curl -i -X OPTIONS \
  -H "Origin: http://127.0.0.1:5500" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-demo-tag" \
  http://127.0.0.1:8080/api/echo
~~~

Kỳ vọng preflight được chấp nhận. Thử thay `x-demo-tag` bằng `x-not-allowed` sẽ thấy server từ chối theo cấu hình.

### 8.4. Curl gửi POST không cần preflight

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "X-Demo-Tag: cli" \
  -d '{"message":"sent by curl"}' \
  http://127.0.0.1:8080/api/echo
~~~

Kỳ vọng POST 200 và counter tăng. Curl không tự hỏi quyền bằng OPTIONS trước; nó gửi POST ngay. Vì vậy đừng kết luận “curl POST được tức là browser phải POST được”.

### 8.5. Curl với Origin không được phép

~~~bash
curl -i \
  -H "Origin: http://127.0.0.1:5501" \
  http://127.0.0.1:8080/api/public
~~~

Spring CORS processor trong lab có thể chủ động trả 403. Nhưng một server khác có thể trả 200 thiếu ACAO và curl vẫn hiển thị body. Browser sẽ enforce CORS checks bất kể cách server chọn status.

**Kết luận:** Curl trả lời “HTTP server phản hồi gì khi tôi gửi những header này?”. Browser trả lời thêm “JavaScript từ origin hiện tại có được gửi request thật và đọc response hay không?”.

## 9. MockMvc: xác minh Spring Security CORS policy

MockMvc rất phù hợp để xác minh backend trả đúng ACA headers và chặn preflight sai, nhưng nó **không chạy browser engine**, không áp policy JS response exposure.

Tạo file `src/test/java/com/example/corslab/CorsBrowserLabTests.java`:

~~~java
package com.example.corslab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsBrowserLabTests {

    private static final String ALLOWED =
        "http://127.0.0.1:5500";

    private static final String DENIED =
        "http://127.0.0.1:5501";

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoController controller;

    @Test
    void allowedGetIncludesCorsHeader() throws Exception {
        mvc.perform(get("/api/public").header("Origin", ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", ALLOWED))
            .andExpect(jsonPath("$.status").value("public"));
    }

    @Test
    void allowedPreflightSucceeds() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-demo-tag"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", ALLOWED))
            .andExpect(header().exists("Access-Control-Allow-Methods"))
            .andExpect(header().exists("Access-Control-Allow-Headers"));
    }

    @Test
    void unlistedHeaderPreflightIsRejected() throws Exception {
        int before = controller.currentAcceptedPosts();

        mvc.perform(options("/api/echo")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-not-allowed"))
            .andExpect(status().isForbidden());

        assertEquals(before, controller.currentAcceptedPosts());
    }

    @Test
    void deniedOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", DENIED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedActualPostReturnsCorsAndExposedHeader()
            throws Exception {
        mvc.perform(post("/api/echo")
                .header("Origin", ALLOWED)
                .header("X-Demo-Tag", "test")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", ALLOWED))
            .andExpect(header().exists(
                "Access-Control-Expose-Headers"))
            .andExpect(header().string("X-Demo-Result", "accepted"))
            .andExpect(jsonPath("$.message").value("hello"));
    }

    @Test
    void requestWithoutOriginReachesApi() throws Exception {
        mvc.perform(post("/api/echo")
                .header("X-Demo-Tag", "cli")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"from curl\"}"))
            .andExpect(status().isOk());
    }
}
~~~

Chạy `mvn clean test`. Test này kiểm tra chính sách phía server:

- Origin 5500 được cấp ACAO.
- Preflight POST với các header cho phép thành công.
- Header lạ bị chặn, counter không tăng.
- Origin 5501 bị chặn.
- Actual POST origin hợp lệ có CORS headers và body.
- Request không có Origin vẫn có thể vào API công khai.

**Hạn chế:** MockMvc không chứng minh browser có tạo preflight, tự gửi cookies theo SameSite, tôn trọng CSP hay expose đúng response headers cho JavaScript. Vì vậy một chiến lược QA đầy đủ cần **MockMvc + browser E2E/DevTools**, không được chỉ test một trong hai.

Mã là ví dụ kiến thức có đầy đủ file/import/dependency; **chưa có kết quả chạy Maven thực tế trong bài**, nên không tuyên bố `BUILD SUCCESS` nếu chưa tự thực thi.

## 10. Credentialed CORS và cookie: đừng dùng wildcard

Với ứng dụng có session-cookie login, frontend cross-origin có thể dùng:

~~~javascript
fetch("https://api.example.test/me", {
  credentials: "include"
});
~~~

Backend cần cấu hình origin rõ ràng và cho phép credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Sai khi browser yêu cầu credentialed access:**

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser sẽ không cho JavaScript dùng response vì wildcard origin không tương thích với credentialed CORS. Spring Framework cũng không cho dùng trực tiếp `allowedOrigins("*")` cùng `allowCredentials(true)`. Có thể sử dụng `allowedOriginPatterns` cho các pattern đáng tin, nhưng không được biến nó thành “echo mọi Origin” không kiểm soát.

Fragment minh họa (không dùng nguyên cùng lab public):

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.test"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
cors.setAllowCredentials(true);
~~~

CORS pass **chưa đủ** để cookie login hoạt động:

- Browser phải gửi cookies khi phù hợp `credentials`.
- Cookie cần `Domain`/`Path`/`Secure`/`SameSite` đúng, và có thể bị third-party cookie restrictions chặn.
- Session server phải còn hợp lệ; `SecurityContext`/`Authentication` cần được khôi phục.
- POST/PUT/DELETE với cookie authentication **vẫn cần chống CSRF** theo threat model.
- Người dùng phải có permission trên dữ liệu thật, không chỉ từ origin được phép.
- Preflight thường không có session cookie; đừng chặn nó bằng HTTP authentication.
- Login redirects/preflight redirects có thể gây lỗi; hãy xem Network chi tiết.

**CORS không phải CSRF defense:** Một số simple requests có thể đã tới server trước khi browser chặn quyền đọc response. Backend phải bảo vệ side effects bằng authentication, authorization, CSRF và business rules tương ứng.

## 11. CORS failure không phải lúc nào cũng là vấn đề CORS config

Khi browser Console báo lỗi network hoặc CORS, kiểm tra theo trình tự:

1. **Origin thật là gì?** So sánh đầy đủ scheme/hostname/port; `localhost` và `127.0.0.1` không phải cùng host.
2. **Backend có chạy không?** DNS, port, TLS certificate, firewall, proxy, HTTP 5xx có thể làm `fetch` reject.
3. **Trang HTTPS có gọi API HTTP không?** Browser có thể chặn mixed content trước khi CORS hoàn tất.
4. **Có CSP `connect-src` không?** CSP có thể chặn fetch tới URL dù server có ACAO đúng.
5. **Request có preflight không?** OPTIONS bị 401/403 hoặc redirect có thể là nguồn gốc.
6. **Method và request headers nào được preflight xin phép?** So với allowlist thực.
7. **Response có ACAO không và có khớp origin?** Không dùng URL backend làm giá trị mong đợi của ACAO.
8. **Có credential mode không?** Kiểm tra ACA-Credentials và wildcard origin.
9. **Cookie có thực sự được gửi không?** `SameSite`, `Secure` và browser privacy policy có thể ảnh hưởng.
10. **Có redirect/login/gateway không?** Redirect từ OPTIONS hoặc API response không có ACA headers có thể gây lỗi.
11. **Có reverse proxy/CDN không?** Header bị bỏ, response cache nhầm origin, thiếu `Vary: Origin`.
12. **Actual request có được gửi chưa?** OPTIONS failure khác với GET/POST simple response rejection.
13. **Có Service Worker hoặc extension?** Những tầng này có thể chặn/biến đổi request.
14. **HTTP 401/403 có đến từ authz/CSRF không?** Đừng quy mọi 403 thành CORS.
15. **Frontend có dùng `mode: "no-cors"` không?** Opaque response không cho JS đọc JSON, không phải bản sửa CORS đúng.

Ví dụ tình huống thường gặp:

~~~text
Backend allow: http://127.0.0.1:5500
Browser mở:   http://localhost:5500

=> Origin KHÔNG KHỚP, dù cùng máy.
~~~

Hoặc:

~~~text
Browser:
  Origin: https://app.example.test
  Request headers: Authorization, Content-Type

Backend:
  AllowedHeaders: Content-Type

=> Preflight xin Authorization bị từ chối.
~~~

Hãy sửa **đúng cấu hình theo nhu cầu thật**, không mở `*` bừa bãi hoặc tắt toàn bộ Spring Security.

## 12. Dấu hiệu chẩn đoán theo tầng

| Triệu chứng | Tầng cần xem trước | Gợi ý |
| --- | --- | --- |
| Curl GET 200, browser báo CORS | CORS/Origin | ACAO và origin thực |
| OPTIONS 401 | Security filter ordering | `.cors(...)` và authentication trong preflight |
| OPTIONS 403 | CORS allowlist | Origin, Method, Headers |
| Browser POST không xuất hiện | Preflight | OPTIONS failed hoặc browser khác chặn |
| GET Network 200 nhưng JS TypeError | Browser response exposure | ACAO, ACA-Credentials, CSP |
| JS đọc JSON nhưng thiếu custom response header | Exposed headers | `Access-Control-Expose-Headers` |
| CORS pass nhưng API 401 | Authentication | Cookie/bearer/session |
| CORS pass nhưng API 403 | Authorization/CSRF | Role, policy, CSRF token |
| Browser gửi cookie nhưng server vẫn anonymous | Cookie/session | SameSite, session expiration, store |
| Test localhost được nhưng production lỗi | Proxy/TLS/allowlist | Scheme, host, forwarded headers, CDN |
| Có lúc thấy OPTIONS, lúc không | Preflight caching | `Access-Control-Max-Age` và browser cache |
| JS chỉ nhận opaque response | Fetch mode | Không dùng `no-cors` để lấy JSON |

### 12.1. Khi request thực đã chạy nhưng browser chặn response

Một lỗi tư duy nguy hiểm là:

> “Nếu browser báo CORS thì backend không thể đã ghi dữ liệu.”

Sai. CORS chủ yếu bảo vệ khả năng JS đọc response. Với **simple requests**, browser có thể gửi request thật, backend xử lý mutation, rồi browser chặn đọc response. Vì vậy backend vẫn cần chống CSRF và authorization cho các hành động thay đổi trạng thái.

Trong lab, JSON POST là **preflighted**: khi preflight không đạt, browser không gửi POST. Đây là đặc tính của **ca thử nghiệm cụ thể**, không phải lời bảo đảm của CORS với mọi requests.

### 12.2. Error responses cũng cần CORS đúng

Nếu frontend được phép gọi API mà backend trả 400/401/403/404/500, response lỗi cũng nên có CORS headers phù hợp để JS đọc status/message. Nếu middleware xử lý lỗi bỏ mất ACAO, frontend có thể chỉ thấy lỗi CORS thay vì JSON lỗi gốc, gây khó debug.

Không nên lạm dụng CORS headers để “che” lỗi 401/403. Hãy bảo đảm CORS policy được áp nhất quán, đồng thời server vẫn từ chối request không được xác thực/ủy quyền.

## 13. Ma trận QA cho dự án thực

| Nhóm | Test case | Điều phải quan sát |
| --- | --- | --- |
| Origin | Allowed origin | JS đọc response |
| Origin | Unknown origin/khác port | JS không đọc response |
| Origin | HTTP vs HTTPS | Origin khác scheme không nhầm |
| Preflight | POST JSON + custom header | Có OPTIONS trước POST |
| Preflight | Header bị cấm | POST không chạy khi OPTIONS fail |
| Preflight | Method bị cấm | Không gửi actual request sau preflight reject |
| Simple request | GET không custom headers | Có thể không cần OPTIONS |
| Credentials | include + ACA-Credentials true + origin cụ thể | Browser đọc response khi cookie policy hợp lệ |
| Credentials | include + ACAO wildcard | Browser chặn |
| Cookies | SameSite/Secure/third-party policy | Cookie được gửi hoặc bị chặn đúng |
| CSRF | Session-cookie POST thiếu CSRF | Backend từ chối mutation |
| Authn/Authz | User thiếu quyền | CORS pass vẫn bị 401/403 |
| Expose | Custom response header | JS đọc được khi expose |
| Error | 400/401/403/500 | Frontend đọc được status/error theo policy |
| Proxy | CDN cache các origin | Không trộn responses khác Origin |
| Browser | Chrome/Firefox/Edge | Hành vi cross-origin phù hợp |
| Cache | Preflight maxAge | Không nhầm cached preflight với thiếu cấu hình |
| Side effects | Blocked preflight vs blocked response | Biết server đã xử lý thao tác chưa |

**Acceptance criteria tối thiểu:** Browser từ origin được phép gọi được API và đọc đúng body/headers; browser từ origin không cho phép bị giới hạn; preflight thực hiện đúng khi cần; credentials/CSRF/authz không bị mở ngoài ý muốn; backend side effects được kiểm chứng.

## 14. Sai lầm cần tránh

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “curl trả 200 tức CORS đã OK” | Curl không enforce browser policy | Dùng browser DevTools/E2E |
| “Mọi POST đều có OPTIONS” | Simple POST có thể không preflight | Xác định method/content-type/headers |
| “Không thấy OPTIONS là hỏng” | Simple request hoặc preflight cached | Kiểm Network/cache |
| “CORS lỗi thì request chưa vào server” | Simple request có thể đã xử lý | Kiểm server state/logs |
| Đặt ACAO `*` với credentials | Browser từ chối | Explicit allowlist origin |
| Echo mọi `Origin` không kiểm tra | Có thể mở data nhạy cảm | Allowlist đáng tin |
| Tắt Spring Security vì OPTIONS 401 | Mở lỗ hổng | Tích hợp CORS đúng thứ tự |
| Tắt CSRF vì browser báo CORS | CSRF và CORS khác nhau | Giữ CSRF khi dùng cookie |
| `fetch` `mode: "no-cors"` | Opaque response, không đọc JSON | Cấu hình CORS server |
| Chỉ test Postman/MockMvc | Thiếu browser enforcement | Thêm browser E2E |
| Đặt frontend bằng `file://` | Opaque Origin khác lab | Chạy HTTP server |
| Cho rằng localhost = 127.0.0.1 | Hostnames khác | Đồng bộ URL/allowlist |
| Cho rằng CORS là user permission | CORS không xác thực user | Authn/authz riêng |
| Quên `Vary: Origin` khi origin động | Shared cache nhầm responses | Cấu hình/cache policy chuẩn |

## 15. Bài tập tự kiểm tra

**Bài 1.** Frontend mở tại `http://127.0.0.1:5501`, backend allow `http://127.0.0.1:5500`. Vì sao browser chặn GET dù curl nhận 200?

**Bài 2.** Browser gửi POST JSON có `X-Demo-Tag`. Hãy ghi ba request/response headers quan trọng trong preflight và giải thích khi nào POST thật được gửi.

**Bài 3.** Khi thêm `X-Not-Allowed`, backend counter không tăng. Quan sát nào chứng minh preflight đã chặn POST?

**Bài 4.** Browser gửi simple GET và không thấy OPTIONS. Điều này có chứng minh CORS disabled không?

**Bài 5.** Một trang login dùng cookie session, frontend đặt `credentials: "include"`, server trả `Access-Control-Allow-Origin: *`. Browser sẽ làm gì? Sửa cấu hình nào?

**Bài 6.** API có `Access-Control-Allow-Origin` đúng nhưng JavaScript không đọc được `X-Demo-Result` dù Network nhìn thấy. Phải thêm header nào?

**Bài 7.** Một POST đơn giản đã thực hiện mutation nhưng browser báo CORS. Vì sao CORS không thay thế CSRF protection?

**Bài 8.** Preflight nhận 401 từ Spring Security dù URL API đòi login. Vì sao không được yêu cầu cookie login ngay trong preflight?

**Bài 9.** Phân biệt curl với header Origin, MockMvc CORS test và browser E2E. Mỗi loại xác minh được điều gì?

**Bài 10.** Thiết kế 5 test cases cho một SPA dùng cookie session, API khác origin, có CSRF token và nhiều response lỗi.

**Gợi ý đáp án:**

1. Port là thành phần origin, JavaScript từ 5501 không nằm trong allowlist.
2. OPTIONS chứa Origin, Access-Control-Request-Method, Access-Control-Request-Headers; browser chỉ gửi POST sau khi được cho phép.
3. Network có OPTIONS bị reject nhưng không có POST thật; counter giữ nguyên.
4. Không, GET simple thường không cần preflight; preflight cũng có cache.
5. Browser không chấp nhận wildcard cho credentialed CORS; dùng origin cụ thể và `Access-Control-Allow-Credentials: true`, kiểm cookie policy.
6. `Access-Control-Expose-Headers: X-Demo-Result`.
7. Browser có thể gửi simple request trước khi chặn response; backend phải bảo vệ side effects bằng CSRF/authz.
8. OPTIONS hỏi quyền CORS trước actual request, thường không gửi session cookie; tích hợp CORS trước auth đúng cách.
9. Curl/MockMvc kiểm behavior server; browser E2E kiểm SOP/preflight/cookies/response exposure.
10. Gồm allowed/disallowed origin, credentials include, CSRF missing/valid, permission 403 và error response CORS.

## 16. Kết luận

**Kiểm thử CORS đủ tốt phải có một trình duyệt thật.** Curl kiểm tra API và headers rất hiệu quả, nhưng không tái tạo Same-Origin Policy, tự động preflight, credential mode, cookie restrictions và quyết định JavaScript có được đọc response hay không.

Quy trình hiệu quả:

1. Dùng MockMvc/curl kiểm backend CORS policy.
2. Chạy frontend bằng HTTP server tại **origin cụ thể**.
3. Mở DevTools để xem **OPTIONS và actual request**.
4. So sánh origin cho phép và origin bị từ chối.
5. Kiểm tra credential mode/cookies/redirect/CSRF nếu có login.
6. Xác minh side effect phía server, không suy luận chỉ từ JS exception.
7. Giữ authentication và authorization độc lập với CORS.

### Tài liệu chính thức

- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [MDN — CORS wildcard and credentials error](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials)
- [MDN — Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials)
- [Spring Security 6.5 — CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Framework — Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
