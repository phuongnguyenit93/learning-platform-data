# CorsConfiguration: origins, methods, headers và exposedHeaders trong Spring Security Servlet

## 1. Bối cảnh: vì sao cần CORS?

Giả sử giao diện chạy tại **http://localhost:5173** và gọi API tại **http://localhost:8080**. Đây là hai **origin** khác nhau vì origin được xác định bởi **scheme (http/https) + host + port**. Trình duyệt áp dụng Same-Origin Policy, nên JavaScript ở origin A không mặc nhiên được đọc phản hồi của origin B.

**Cross-Origin Resource Sharing (CORS)** cho phép máy chủ B công bố chính sách để trình duyệt biết website nào có thể đọc kết quả, method và request header nào được phép khi có preflight, và response header nào JavaScript được đọc thêm. Trong Spring Framework/Spring Security Servlet, **org.springframework.web.cors.CorsConfiguration** chứa chính sách đó.

Bốn thuộc tính là trọng tâm:

| Java API | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| **setAllowedOrigins(...)** | Trang web từ **origin nào** được phép truy cập response cross-origin? | http://localhost:5173 |
| **setAllowedMethods(...)** | **HTTP method của request thực tế** nào được chấp nhận cho CORS? | GET, POST |
| **setAllowedHeaders(...)** | **Request header** nào trình duyệt được phép gửi? | Content-Type, X-CSRF-TOKEN |
| **setExposedHeaders(...)** | **Response header** nào JavaScript được phép đọc thêm? | X-Request-ID, Content-Disposition |

Các thuộc tính này khác nhau về **chiều dữ liệu** và **mục đích**. Chúng không thay thế authentication, authorization, CSRF hay kiểm tra nghiệp vụ. CORS được **trình duyệt thực thi**; curl, Postman hay server-to-server clients không bị browser Same-Origin Policy ràng buộc.

## 2. allowedOrigins và origin matching

Origin gồm **scheme + host + port**, không bao gồm path, query hoặc fragment:

| Trang frontend | Backend | Có cross-origin? |
| --- | --- | --- |
| http://localhost:5173 | http://localhost:8080 | Có: khác port |
| https://app.example.com | https://api.example.com | Có: khác host |
| https://app.example.com | http://app.example.com | Có: khác scheme |
| https://app.example.com/dashboard | https://app.example.com/api | Không: path không tính |
| https://app.example.com | https://app.example.com:443 | Không: 443 là port mặc định của HTTPS |

Trình duyệt thường gửi **Origin: http://localhost:5173** khi gọi cross-origin. Để cho phép origin này:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("http://localhost:5173"));
~~~

**Lưu ý về giá trị:** viết đúng origin, không thêm **/dashboard** hoặc dấu **/** ở cuối. Giao diện dùng scheme/port khác thì là origin khác. Nên phân biệt origin đáng tin cậy của frontend với domain của backend API.

Có hai API:

~~~java
// Danh sách origin xác định:
cors.setAllowedOrigins(List.of(
        "http://localhost:5173",
        "https://app.example.com"));

// Cách thay thế khi có nhu cầu thật cho nhiều subdomain:
cors.setAllowedOriginPatterns(List.of("https://*.example.com"));
~~~

**allowedOrigins** dùng giá trị origin cụ thể hoặc wildcard **"*"** trong các trường hợp cho phép. **allowedOriginPatterns** nhận cú pháp pattern của Spring, ví dụ **https://*.example.com**, không phải regex tổng quát. Khi origin khớp pattern, Spring trả về origin cụ thể trong **Access-Control-Allow-Origin**.

Với request mang cookie/credentials, **không kết hợp allowedOrigins("*") với allowCredentials(true)**. Browser không chấp nhận wildcard **Access-Control-Allow-Origin: *** cùng credentialed request; Spring cũng kiểm tra và có thể báo cấu hình không hợp lệ. Hãy liệt kê chính xác các origin đáng tin cậy. Không bật pattern quá rộng nếu các subdomain có thể do bên không tin cậy quản lý.

## 3. allowedMethods: cho phép method nào?

~~~java
cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
~~~

Danh sách này dành cho **method của request API thực tế**. Với request cần preflight, browser gửi **OPTIONS** để hỏi xem method dự định có được phép:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Trong ví dụ, **Access-Control-Request-Method: POST** phải được đối chiếu với **allowedMethods**. **OPTIONS** là method của preflight, **không nhất thiết phải thêm OPTIONS vào allowedMethods để preflight POST được phép**.

Khi hợp lệ, response preflight có thể mang:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
~~~

Các dòng trên minh họa ý nghĩa, không cam kết thứ tự và tập header chính xác của mọi phiên bản/proxy. Browser quyết định có gửi POST thực tế hay không dựa vào phản hồi preflight.

**Phân biệt hai lớp kiểm tra:** CORS cho phép POST không có nghĩa người dùng được quyền tạo đơn hàng. Request thật vẫn có thể trả 401, 403, 422 vì xác thực, phân quyền, CSRF hoặc validation. Ngược lại, method không được CORS cho phép thì browser không cho JavaScript gọi/đọc theo cơ chế CORS, dù endpoint vẫn có thể nhận request từ client không phải browser.

## 4. allowedHeaders: tên header của request

~~~java
cors.setAllowedHeaders(List.of(
        "Content-Type",
        "X-CSRF-TOKEN",
        "X-Request-ID"));
~~~

**allowedHeaders** mô tả **request header do browser muốn gửi**; preflight khai báo tên trong **Access-Control-Request-Headers**. Thí dụ:

- **Content-Type: application/json** thường gây preflight vì không thuộc giá trị Content-Type được CORS safelist.
- **Authorization: Bearer ...** là request header không thuộc safelist; nếu frontend thật sự gửi thì cần cho phép **Authorization**.
- **X-CSRF-TOKEN** là header thường dùng khi gửi CSRF token cho ứng dụng xác thực bằng session cookie.
- **X-Request-ID** ở **request** chỉ cần allowedHeaders nếu frontend chủ động gửi nó. Nếu chỉ server trả lại X-Request-ID thì tên này cần **exposedHeaders**, không cần allowedHeaders.

Tên HTTP header không phân biệt chữ hoa/thường về ý nghĩa. Không phải GET/POST nào cũng preflight: một GET không gửi header đặc biệt thường không cần OPTIONS, còn GET thêm Authorization hoặc header tùy chỉnh thường cần.

Có thể khai báo **setAllowedHeaders(List.of("*"))** để chấp nhận một tập rộng, nhưng với production nên kê rõ các header cần thiết để giảm cấu hình dư thừa. **allowedHeaders không quyết định response header được JavaScript đọc**, đó là thuộc tính khác.

## 5. exposedHeaders: tên header của response

Ngay cả khi request vượt qua CORS, JavaScript cross-origin chỉ tự đọc được nhóm **CORS-safelisted response headers**: **Cache-Control, Content-Language, Content-Length, Content-Type, Expires, Last-Modified, Pragma**. Các header response khác phải được khai báo qua **Access-Control-Expose-Headers**:

~~~java
cors.setExposedHeaders(List.of(
        "X-Request-ID",
        "Content-Disposition"));
~~~

Ví dụ server trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: X-Request-ID,Content-Disposition
X-Request-ID: request-42
Content-Disposition: attachment; filename="orders.csv"
Content-Type: application/json
~~~

Frontend:

~~~javascript
const response = await fetch("http://localhost:8080/api/orders", {
  credentials: "include"
});
console.log(response.headers.get("X-Request-ID"));     // request-42
console.log(response.headers.get("Content-Type"));     // application/json
~~~

Nếu response thật có **X-Request-ID** nhưng không expose, DevTools Network vẫn có thể hiển thị header đó, còn **response.headers.get("X-Request-ID")** trong JavaScript cross-origin trả **null**. **exposedHeaders chỉ cho phép đọc header có sẵn, không tự tạo header**. Controller hoặc gateway phải thật sự trả header cần thiết.

Đừng expose **Set-Cookie** rồi kỳ vọng JavaScript đọc được: theo Fetch, đây là **forbidden response-header name** và bị lọc khỏi response.headers; cookie **HttpOnly** cũng không được đọc từ document.cookie. Với request credentials, nên dùng danh sách exposedHeaders tường minh, tránh dựa vào wildcard "*" vì tương tác wildcard với Fetch và Spring có những chi tiết dễ nhầm.

## 6. CORS request, preflight và hướng đi của từng header

Một request GET không có header đặc biệt có thể đi thẳng:

~~~http
GET /api/orders HTTP/1.1
Origin: http://localhost:5173
~~~

Nếu server trả header CORS hợp lệ, browser cho code đọc response. Nhưng khi POST JSON cùng header CSRF:

~~~javascript
await fetch("http://localhost:8080/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "gia-tri-token-thuc-tu-server"
  },
  body: JSON.stringify({ name: "order-01" })
});
~~~

Browser thường gửi **OPTIONS preflight** trước, kèm **Origin**, **Access-Control-Request-Method: POST** và **Access-Control-Request-Headers: content-type,x-csrf-token**. Nếu phản hồi cho phép origin, POST và các request header, browser mới gửi POST thực tế. Cookie phiên chỉ đi kèm khi **fetch credentials** và chính sách cookie cho phép. Sau đó browser tiếp tục xét header CORS trên response thực tế trước khi cho JS đọc.

Preflight có thể được cache theo **Access-Control-Max-Age** và giới hạn browser. **Không viết code frontend để tự gọi preflight**; đó là nhiệm vụ của browser. Một request có Origin không đồng nghĩa chắc chắn có preflight.

| Header | Chiều | Cấu hình/mục đích |
| --- | --- | --- |
| Origin | Browser → API | So với allowedOrigins/allowedOriginPatterns |
| Access-Control-Request-Method | Browser → API, preflight | So với allowedMethods |
| Access-Control-Request-Headers | Browser → API, preflight | So với allowedHeaders |
| Access-Control-Allow-Origin | API → Browser | Origin được cho phép |
| Access-Control-Allow-Methods | API → Browser, preflight | Method có thể dùng |
| Access-Control-Allow-Headers | API → Browser, preflight | Request header có thể gửi |
| Access-Control-Expose-Headers | API → Browser, response | Response header JS được đọc thêm |
| Access-Control-Allow-Credentials | API → Browser | allowCredentials |
| Access-Control-Max-Age | API → Browser, preflight | maxAge |

**Access-Control-Allow-Headers** và **Access-Control-Expose-Headers** đều là response header nhưng phục vụ hai mục đích khác nhau: cái đầu cấp quyền **gửi request headers**, cái sau cấp quyền **đọc response headers**.

## 7. Ví dụ chạy được: Spring Boot 3.4.5, Java 17 và Spring Security Servlet

Ví dụ này dùng backend **http://localhost:8080**, frontend **http://localhost:5173**, cho phép GET/POST, JSON + CSRF request headers và expose **X-Request-ID**. Để minh họa tính độc lập, **CSRF vẫn bật** theo mặc định; endpoint chỉ **permitAll()** để không phải thiết lập đăng nhập trong demo.

Tạo dự án:

~~~text
cors-servlet-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cors/CorsDemoApplication.java
    └── test/java/demo/cors/CorsDemoApplicationTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>cors-servlet-demo</artifactId>
    <version>1.0.0</version>
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

**src/main/java/demo/cors/CorsDemoApplication.java**:

~~~java
package demo.cors;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN", "X-Request-ID"));
        cors.setExposedHeaders(List.of(
                "X-Request-ID", "Content-Disposition"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().permitAll());
        // CSRF vẫn bật theo mặc định.
        return http.build();
    }
}

@RestController
@RequestMapping("/api")
class OrderController {
    @GetMapping("/orders")
    ResponseEntity<Map<String, String>> list() {
        return ResponseEntity.ok()
                .header("X-Request-ID", "request-42")
                .body(Map.of("status", "ready"));
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
                request.getAttribute(CsrfToken.class.getName());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "token", token.getToken(),
                        "headerName", token.getHeaderName()));
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, String>> create(
            @RequestBody Map<String, String> order) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Request-ID", "request-43")
                .body(Map.of("name", order.getOrDefault("name", "unnamed")));
    }
}
~~~

**Giải thích code:** **CorsConfiguration** chứa chính sách; **UrlBasedCorsConfigurationSource** ràng buộc chính sách với đường dẫn API **/api/*** phía server. **http.cors(Customizer.withDefaults())** đưa xử lý CORS vào Spring Security filter chain; preflight không mang cookie cũng có thể được xử lý trước bước authentication. **anyRequest().permitAll()** chỉ dùng trong demo, không phải cấu hình production. CORS không tự tắt CSRF.

Endpoint **GET /api/csrf** cho phép giao diện lấy token thực do Spring Security cấp, đồng thời đặt **Cache-Control: no-store**. Với Spring Security 6, token ở request attribute có thể được XOR-mask trước khi trình bày để giảm rủi ro BREACH; frontend gửi lại token đó qua header được chỉ định. **GET /api/orders** trả response header **X-Request-ID** để kiểm tra exposedHeaders.

### 7.1. Thử preflight bằng curl

Chạy backend:

~~~bash
mvn spring-boot:run
~~~

Trong một terminal khác:

~~~bash
curl -i -H "Origin: http://localhost:5173" \
  "http://localhost:8080/api/orders"

curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: https://attacker.example" \
  -H "Access-Control-Request-Method: POST"
~~~

Quan sát kỳ vọng: GET hợp lệ trả **200** với **Access-Control-Allow-Origin** đúng và **X-Request-ID**; preflight hợp lệ được chấp nhận và trả các **Access-Control-Allow-*** cần thiết; origin lạ bị từ chối, thường **403**. Tập header chính xác có thể khác về thứ tự và chữ hoa/thường.

**curl không thực thi chính sách CORS của browser**; nó chỉ giúp kiểm tra server có gửi header gì. Trên Windows PowerShell 5.1, **curl** có thể là alias Invoke-WebRequest; dùng **curl.exe** nếu muốn cú pháp curl.

### 7.2. Gọi fetch từ giao diện thật

Mở frontend được phục vụ tại **http://localhost:5173**. Đoạn JavaScript sau dùng cùng cookie/session khi nhận CSRF token và POST:

~~~javascript
const api = "http://localhost:8080/api";

// GET: không cần preflight khi không có header đặc biệt.
const getResponse = await fetch(api + "/orders", {
  credentials: "include"
});
console.log(getResponse.status);                     // 200
console.log(getResponse.headers.get("X-Request-ID")); // request-42
console.log((await getResponse.json()).status);       // ready

// Lấy CSRF token từ server và để browser nhận/giữ cookie phiên.
const tokenResponse = await fetch(api + "/csrf", {
  credentials: "include"
});
const csrf = await tokenResponse.json();

// POST JSON: browser thường tự gửi OPTIONS preflight trước.
const postResponse = await fetch(api + "/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ name: "order-01" })
});
console.log(postResponse.status);                     // 201
console.log(postResponse.headers.get("X-Request-ID")); // request-43
console.log((await postResponse.json()).name);         // order-01
~~~

Đây là kịch bản học tập chạy trên **trang được phục vụ từ đúng origin đã cho phép**; chạy trong trang ở origin khác sẽ bị CORS kiểm soát khác. Nếu login/logout làm xóa CSRF token, giao diện phải nhận token mới. Cấu hình cookie (SameSite, Secure, Domain...), session store và chính sách browser cũng phải cho phép cookie được dùng trong fetch.

## 8. Kiểm thử server với Spring Security Test và MockMvc

Tạo **src/test/java/demo/cors/CorsDemoApplicationTests.java**:

~~~java
package demo.cors;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CorsDemoApplicationTests {
    private static final String ALLOWED = "http://localhost:5173";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightAllowsConfiguredOriginMethodAndHeaders()
            throws Exception {
        mvc.perform(options("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED)
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                "content-type,x-csrf-token"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void preflightRejectsUnlistedOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                        .header(HttpHeaders.ORIGIN, "https://attacker.example")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void responseExposesRequestId() throws Exception {
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                        containsString("X-Request-ID")))
                .andExpect(header().string("X-Request-ID", "request-42"));
    }

    @Test
    void corsAllowedDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"order-01\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidCsrfSucceeds() throws Exception {
        mvc.perform(post("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"order-01\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("order-01"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Kiểm thử xác nhận preflight origin/method/headers, origin bị từ chối, exposed response header, và sự khác biệt giữa CORS với CSRF. **MockMvc mô phỏng phía server**; cần kiểm thử trong browser thật để quan sát cookie policy, preflight cache và giới hạn response.headers của JavaScript.

## 9. allowCredentials, session cookie và CSRF

Với giao diện sử dụng session cookie, code thường cần:

~~~java
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowCredentials(true);
~~~

và fetch cần **credentials: "include"** cho cross-origin. Response credentialed request phải có **Access-Control-Allow-Origin** bằng origin cụ thể và **Access-Control-Allow-Credentials: true**; wildcard origin không hợp lệ ở đây.

Điều đó **không bảo đảm cookie sẽ được gửi**. Cookie còn bị chi phối bởi **Domain, Path, SameSite, Secure, HttpOnly**, quy tắc chống third-party cookies và khả năng sử dụng HTTPS. Với quan hệ thực sự cross-site, cookie **SameSite=None; Secure** thường là yêu cầu để gửi trong ngữ cảnh đó. **allowCredentials** cho phép browser xử lý credentials theo chính sách CORS, không thay đổi giới hạn cookie.

**CORS không phải CSRF:** một số POST từ form HTML đơn giản có thể được browser gửi dù không có preflight; CORS chủ yếu ngăn code của origin không được phép đọc response hoặc thực hiện request cần preflight. Với API dùng cookie tự đính kèm, vẫn cần bảo vệ CSRF cho thao tác thay đổi trạng thái. **permitAll()** cũng không tự miễn kiểm tra CSRF.

**CORS không phải phân quyền:** client không phải browser có thể tự đặt Origin; backend vẫn phải xác thực, kiểm tra quyền trên tài nguyên, validate input và audit theo yêu cầu. Với server-to-server calls không chạy trong browser, CORS thường không phải giới hạn áp dụng.

## 10. Tích hợp Spring MVC, Spring Security và phạm vi áp dụng

Spring MVC hỗ trợ **@CrossOrigin** hoặc **WebMvcConfigurer#addCorsMappings**. Spring Security có thể tích hợp chính sách CORS của MVC trong điều kiện cấu hình phù hợp. Trong ví dụ này, chính sách được khai báo **rõ ràng bằng một CorsConfigurationSource bean** và kích hoạt qua **http.cors(Customizer.withDefaults())**, giúp nhận biết nguồn cấu hình mà filter chain sử dụng.

Nếu ứng dụng có nhiều SecurityFilterChain, cần kiểm tra chain nào thực sự xử lý **/api/** và đảm bảo CORS được bật ở chain đó. Nếu preflight OPTIONS gặp authentication filter trước CORS, nó có thể bị 401 do không mang cookie; đây là lý do thứ tự CORS và Security rất quan trọng. Tránh tạo nhiều CorsFilter hoặc nguồn CORS trùng lặp không rõ độ ưu tiên.

**registerCorsConfiguration("/api/**", cors)** là pattern **đường dẫn server**, không phải allowed origin. **setMaxAge(3600L)** đặt số giây preflight được cache (browser vẫn có giới hạn riêng), không phải thời gian sống session, token hoặc cookie. **applyPermitDefaultValues()** điền một số mặc định tương đối rộng; đừng gọi mà không kiểm soát những thuộc tính chưa cấu hình.

## 11. Sự cố thực tế và cách debug

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Browser báo thiếu Access-Control-Allow-Origin | Origin không khớp scheme/port/host; path không áp dụng CORS | Xem Origin của request và mapping policy |
| OPTIONS trả 403 | allowedOrigins, allowedMethods hoặc allowedHeaders không khớp | So Access-Control-Request-Method/Headers với cấu hình |
| OPTIONS trả 401 | Security authentication chạy trước CORS | Xem http.cors(...) và filter chain đang áp dụng |
| GET chạy, POST JSON bị lỗi CORS | POST JSON cần preflight, Content-Type chưa được cho phép | Cho phép Content-Type và POST nếu đúng nghiệp vụ |
| Authorization header gây lỗi preflight | allowedHeaders không chứa Authorization | Thêm Authorization khi client thật dùng |
| X-Request-ID có trong Network nhưng JS đọc null | exposedHeaders chưa liệt kê header | setExposedHeaders(List.of("X-Request-ID")) |
| Browser từ chối wildcard origin + credentials | Cấu hình allowCredentials và allowedOrigins không tương thích | Dùng origin tường minh |
| curl trả 200 nhưng fetch lỗi | curl không áp dụng browser CORS | Kiểm tra DevTools Network và CORS response |
| Preflight qua rồi POST 403 | CSRF token sai/thiếu, authorization hoặc lỗi backend | Xem request thật, server log, token/session |
| Cookie không đi kèm | credentials, SameSite, Secure, Domain hoặc browser policy | Kiểm tra Application/Cookies, network request |
| Qua CDN/proxy có lúc đúng lúc sai | CORS response bị cache sai theo Origin/preflight headers | Xem Vary: Origin, Access-Control-Request-Method/Headers |

Khi debug, hãy đi lần lượt: **Origin thực** → có hay không **OPTIONS preflight** → **Access-Control-Request-Method/Headers** → **Access-Control-Allow-*** ở response → status và logic của **request thực tế** → **exposedHeaders** nếu JS không đọc được response header. Đừng tắt CSRF hoặc mở toàn bộ origin để “sửa” lỗi trình duyệt mà chưa hiểu request cụ thể.

## 12. Tự kiểm tra

1. UI **localhost:5173** gọi API **localhost:8080** có cross-origin không? **Có, khác port.**
2. Preflight OPTIONS hỏi quyền POST: so **POST** với property nào? **allowedMethods.**
3. UI gửi header X-CSRF-TOKEN nhưng chỉ muốn đọc X-Request-ID từ response: tên thứ nhất thuộc **allowedHeaders**, tên thứ hai thuộc **exposedHeaders**.
4. API trả X-Request-ID nhưng JS đọc null dù response 200: kiểm tra **Access-Control-Expose-Headers**.
5. Có thể dùng **allowedOrigins("*")** với **allowCredentials(true)** không? **Không.**
6. Preflight thành công mà POST 403 có chắc lỗi CORS không? **Không: có thể là CSRF/authz.**
7. CORS có chặn curl, Postman tự gửi Origin không? **Không, CORS chủ yếu do browser thực thi.**

**Ghi nhớ:** **allowedOrigins** giới hạn **origin**, **allowedMethods** giới hạn **method của request**, **allowedHeaders** giới hạn **request header được gửi**, còn **exposedHeaders** mở quyền **đọc response header** cho JavaScript cross-origin. Trên Spring Security Servlet, tích hợp CorsConfiguration qua **CorsConfigurationSource + http.cors(...)**, kiểm thử cả preflight và request thật, đồng thời duy trì xác thực, phân quyền và CSRF riêng biệt.
