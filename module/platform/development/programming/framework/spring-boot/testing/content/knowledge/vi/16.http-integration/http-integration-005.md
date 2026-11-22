# Cookie, session, redirect và nhiều request liên tiếp trong kiểm thử HTTP Spring Boot

## 1. Vì sao test một request riêng lẻ là chưa đủ?

Một API có thể trả đúng HTTP 200 cho một request đơn mà vẫn hoạt động sai trong một **chuỗi HTTP requests phụ thuộc trạng thái**. Ví dụ:

1. Client gửi **POST /demo/login** với tên người dùng.
2. Server tạo **HttpSession**, gắn dữ liệu cho session và trả **Set-Cookie: JSESSIONID=...** cùng **303 See Other** và **Location: /demo/profile**.
3. Client lưu cookie rồi gửi **GET /demo/profile**. Server nhận **Cookie: JSESSIONID=...**, tra cứu session cũ và trả dữ liệu tương ứng.
4. Client gửi GET thêm lần nữa: bộ đếm visits trong **cùng session** tăng từ 1 lên 2.
5. Client gửi **POST /demo/logout**. Server invalidates session.
6. Client dù còn giữ cookie cũ cũng không thể truy cập dữ liệu session: GET profile trả **401**.

Một test chỉ gọi controller.login(...) trực tiếp không chứng minh được **Set-Cookie**, **Cookie** ở request sau, **Location**, chính sách **redirect** của HTTP client hay vòng đời servlet session. Một test dùng HTTP thực với cổng ngẫu nhiên và **cùng cookie jar qua nhiều request** có thể xác minh những ranh giới đó.

**Mục tiêu của bài học:**

- Phân biệt HTTP **cookie** (metadata client gửi lại), **server-side session** (state tại server) và **redirect** (response 3xx, Location).
- Dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)**, **@LocalServerPort** và Java 17 **HttpClient** để gửi nhiều request HTTP thực.
- Cấu hình **CookieManager** riêng cho từng scenario; so sánh client tự lưu cookie với client không lưu.
- Test rõ **303** khi không tự follow, và response **200** sau khi client tự follow POST → GET.
- Kiểm thử session được giữ qua nhiều request, cô lập giữa hai clients, không nhận session nếu thiếu cookie, logout làm mất hiệu lực session và input sai trả 400.
- Tránh lỗi do redirect bị follow ngầm, session dùng chung giữa tests, cookie attributes, concurrency, thời gian hết hạn hoặc rollback transaction được hiểu sai.
- Hiểu giới hạn bảo mật của ví dụ: đây là **mô phỏng session**, không phải một hệ thống đăng nhập an toàn cho production.

**Phiên bản thực hành:** Java 17, Spring Boot 3.3.5, Spring MVC/embedded Tomcat, JUnit Jupiter, Gradle. Code dùng **Jakarta Servlet API** của Spring Boot 3.x, không dùng javax.servlet của Spring Boot 2.x.

## 2. Cookie, HttpSession và redirect không phải một thứ

| Khái niệm | Nơi lưu/đi qua | Công dụng | Điều phải kiểm tra |
|---|---|---|---|
| **Set-Cookie** | HTTP response header từ server | Yêu cầu client ghi nhớ cookie | Server có phát cookie name/value/attributes đúng không? |
| **Cookie** | HTTP request header từ client | Gửi lại các cookie phù hợp domain/path/scheme | Request sau có mang session ID không? |
| **HttpSession** | State do servlet container hoặc session repository quản lý | Liên kết request với dữ liệu server-side | Cùng cookie có đọc đúng state cũ không? |
| **JSESSIONID** | Tên session tracking cookie phổ biến của servlet container | Định danh session, **không phải toàn bộ nội dung session** | Cookie được client lưu và gửi lại đúng không? |
| **303 See Other** | HTTP response status + Location | Hướng client truy cập URI khác, thông thường bằng GET | Test có nhận 303 hay đã theo redirect để nhận 200? |
| **Location** | Header của response redirect | Chỉ nơi cần đi tiếp | URI tương đối/tuyệt đối có đúng và an toàn không? |
| **CookieManager** | State của HTTP client Java 17 | Giữ cookie qua nhiều requests dựa theo chính sách | Test không rò cookie sang scenario khác? |
| **HttpClient.Redirect** | Cấu hình client Java 17 | Quyết định theo redirect tự động hay không | NEVER và NORMAL có đúng expected status? |

**Phân biệt cực quan trọng:** Set-Cookie chứa **session identifier**, không phải username hay biến visits. Tại server, HttpSession liên kết ID với những attributes đã lưu. Khi client gửi đúng cookie, servlet container có thể tìm session; nếu ID không hợp lệ, session đã timeout hoặc bị invalidate, cookie đó không còn chứng minh session tồn tại.

**HTTP vốn stateless** theo mỗi request; cookie + server-side session tạo khả năng theo dõi nhiều requests liên tiếp. Cookie cũng có thể dùng cho mục đích khác như preference, CSRF token hoặc tracking; không phải cookie nào cũng là JSESSIONID, và không phải mọi ứng dụng đều dùng HttpSession. Hệ thống dùng Bearer token/stateless JWT có thể không có servlet session.

### 2.1. Luồng request và response thực

~~~text
Client: CookieManager ban đầu trống
       |
       | POST /demo/login {"username":"Lan"}
       v
Embedded Tomcat -> Spring MVC Controller
       |           request.getSession(true)
       |           session["username"] = "Lan"
       |           session["visits"] = 0
       v
HTTP/1.1 303 See Other
Location: /demo/profile
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly; ...
       |
       | Client lưu JSESSIONID vào cookie jar
       | Redirect.NEVER: nhận 303, tự gửi GET sau
       | Redirect.NORMAL: client có thể tự đi tiếp
       v
GET /demo/profile
Cookie: JSESSIONID=<opaque-id>
       |
       v
request.getSession(false) -> session cũ
session["visits"] = 1
HTTP/1.1 200 OK
{"username":"Lan","visits":1}
       |
       | GET /demo/profile, cùng cookie
       v
HTTP/1.1 200 OK
{"username":"Lan","visits":2}
       |
       | POST /demo/logout, cùng cookie
       v
session.invalidate()
HTTP/1.1 204 No Content
       |
       | GET /demo/profile, cookie cũ có thể vẫn còn
       v
HTTP/1.1 401 Unauthorized
~~~

Phần Set-Cookie ở sơ đồ là **dạng minh họa**: giá trị session ID không cố định, thuộc tính cookie phụ thuộc servlet container và Spring Boot configuration. Không đưa session identifier cụ thể vào expected output và không log cookie nhạy cảm trong CI.

## 3. Redirect: 301, 302, 303, 307 và 308 khác nhau

| Status | Ngữ nghĩa | POST khi client follow | Gợi ý kiểm thử |
|---|---|---|---|
| **301 Moved Permanently** | Resource chuyển vĩnh viễn | Một số client có thể đổi POST → GET | Test method của request tiếp theo theo client cụ thể |
| **302 Found** | Chuyển tạm thời | Lịch sử browser/client cho phép đổi POST → GET | Tránh phụ thuộc hành vi mơ hồ |
| **303 See Other** | Xem kết quả tại URI khác | **GET** (hoặc HEAD khi phù hợp), rất hợp với POST/Redirect/GET | Assert 303 + Location hoặc assert final GET |
| **307 Temporary Redirect** | Chuyển tạm, **giữ nguyên method/body** | Giữ POST | Dùng khi chính request cần gửi lại |
| **308 Permanent Redirect** | Chuyển vĩnh viễn, **giữ nguyên method/body** | Giữ POST | Chú ý ảnh hưởng lâu dài/cache client |

Ví dụ của bài cố ý trả **303 See Other** sau POST /demo/login. Nếu HTTP client follow, nó GET /demo/profile. Điều này diễn đạt rõ quy trình **POST/Redirect/GET** và tránh việc browser gửi lại POST khi người dùng refresh trang kết quả.

**Java 17 HttpClient.Redirect:**
- **NEVER**: không tự theo redirect; response nhận được là **303** và bạn tự đọc Location, quyết định request kế tiếp.
- **NORMAL**: tự follow redirect hợp lệ, trừ trường hợp chuyển **HTTPS → HTTP**; POST nhận 303 được đổi thành GET theo semantics HTTP.
- **ALWAYS**: cho phép follow cả HTTPS → HTTP; không nên bật bừa bãi vì có nguy cơ hạ mức bảo mật kết nối.

HttpClient mới tạo với cấu hình mặc định **không tự follow redirect**. Các client khác, như browser, TestRestTemplate, RestTemplate dùng các request factories khác nhau hoặc RestAssured, có thể có hành vi follow khác. Vì vậy **đừng chỉ assert final 200 rồi tưởng server chưa từng trả 303**.

**Location có thể là relative URI**, ví dụ /demo/profile, hoặc absolute URI. Khi tự follow:

~~~java
String location = response.headers()
        .firstValue("Location")
        .orElseThrow();

URI destination = response.uri().resolve(location);
~~~

URI.resolve tạo absolute URI dựa vào URI của request gốc. Trong ứng dụng thật, **không tự follow redirect bất kỳ domain nào từ input chưa đáng tin**; cần kiểm soát host/scheme/allowlist để tránh open redirect, gửi cookie hoặc credentials sang đích lạ.

## 4. Vì sao chọn real HTTP integration test thay vì chỉ MockMvc?

| Phương pháp | Embedded server + socket thật? | Cookie/session nhiều request? | Thế mạnh |
|---|---|---|---|
| **Unit test controller/service** | Không | Phải mô phỏng thủ công | Logic Java thuần |
| **MockMvc** với MockHttpSession | Không | Có thể mô phỏng session/cookies qua request builders | Test MVC/filter ở tầng Servlet mà không mở cổng |
| **@SpringBootTest + @AutoConfigureMockMvc** | Không cho các lời gọi mvc.perform | Có thể dùng mock session | Full Spring context, mock servlet calls |
| **@SpringBootTest(RANDOM_PORT) + HttpClient** | **Có** | **Có, với CookieManager hoặc Cookie header** | Cookie jar, HTTP redirects, actual server/container boundary |
| **WebTestClient bindToApplicationContext** | Không nhất thiết | Có cơ chế test phù hợp | Reactive/mock web testing |
| **Real HTTP client + Testcontainers/staging** | Có | Có, tùy test setup | Gắn thêm DB/proxy hoặc môi trường production-like |

MockMvc không kém chất lượng: nó rất hữu ích cho nhiều bài controller test và có thể kiểm tra session thông qua **MockHttpSession**. Nhưng nếu đề bài trực tiếp là **Cookie, session, redirect và nhiều request liên tiếp ở HTTP level**, cần ít nhất một test với HTTP client quản lý cookie/redirect như client thật.

Một HTTP integration test không tự chứng minh SSL, reverse proxy, browser SameSite enforcement hay distributed session repository. Đây là bài test trên embedded Tomcat trong JVM test, dùng loopback HTTP.

## 5. Dự án Spring Boot chạy được: ứng dụng session demo

Ta tạo một API chỉ dành cho học tập:

- **POST /demo/login** nhận JSON có username không blank, đặt username/visits vào HttpSession; trả **303** và **Location: /demo/profile**.
- **GET /demo/profile** đọc session hiện có. Nếu không có session hợp lệ → **401**. Nếu có, tăng visits từ 0 lên 1, rồi lần kế tiếp lên 2 và trả JSON.
- **POST /demo/logout** invalidate session nếu tồn tại, trả **204**; gọi lại không có session vẫn được trả 204.
- POST login username blank → **400**, không tạo session thành công.

Ở hệ thống thật, login không thể chỉ nhận username rồi coi là authenticated! Đây là **demo về HTTP session lifecycle**, không có xác thực, phân quyền, CSRF hoặc password. Khi xây dựng sản phẩm, sử dụng Spring Security và bảo vệ state-changing endpoints.

### 5.1. Cấu trúc project

~~~text
settings.gradle
build.gradle
src/main/java/demo/httpstate/HttpStateApplication.java
src/main/java/demo/httpstate/LoginRequest.java
src/main/java/demo/httpstate/ProfileResponse.java
src/main/java/demo/httpstate/SessionController.java
src/test/java/demo/httpstate/SessionHttpIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'http-cookie-session-integration'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích:**
- spring-boot-starter-web đưa Spring MVC, Jackson, Jakarta Servlet API và embedded Tomcat vào classpath ở Spring Boot 3.3.
- spring-boot-starter-test đưa JUnit Jupiter, Spring Test, Spring Boot Test và assertions.
- java.net.http.HttpClient, java.net.CookieManager đã có sẵn trong **JDK 17**, không cần thêm Apache HttpClient chỉ để lưu cookie trong bài này.
- Không có database, Redis, Spring Security hay external services, nên kết quả test phụ thuộc đúng vào session + cookie/redirect. Nếu bổ sung security, các expected response cần được điều chỉnh theo cơ chế xác thực/CSRF.
- useJUnitPlatform() cần cho JUnit Jupiter tests.

### 5.2. Application

**src/main/java/demo/httpstate/HttpStateApplication.java**

~~~java
package demo.httpstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpStateApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpStateApplication.class, args);
    }
}
~~~

**src/main/java/demo/httpstate/LoginRequest.java**

~~~java
package demo.httpstate;

public record LoginRequest(String username) {
}
~~~

**src/main/java/demo/httpstate/ProfileResponse.java**

~~~java
package demo.httpstate;

public record ProfileResponse(String username, int visits) {
}
~~~

Java 17 hỗ trợ record. Jackson trong Spring Boot 3.3 hỗ trợ chuyển các DTO record đơn giản sang/từ JSON. Giữ mỗi public type trong một file cùng tên.

### 5.3. Controller tạo, dùng lại và hủy HttpSession

**src/main/java/demo/httpstate/SessionController.java**

~~~java
package demo.httpstate;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class SessionController {

    private static final String USERNAME = "username";
    private static final String VISITS = "visits";

    @PostMapping("/login")
    public ResponseEntity<Void> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request) {

        if (body.username() == null
                || body.username().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "username must not be blank");
        }

        HttpSession session = request.getSession(true);
        session.setAttribute(USERNAME, body.username());
        session.setAttribute(VISITS, 0);

        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create("/demo/profile"))
                .build();
    }

    @GetMapping("/profile")
    public ResponseEntity<ProfileResponse> profile(
            HttpServletRequest request) {

        // false: không tự tạo session chỉ để đọc profile.
        HttpSession session = request.getSession(false);

        if (session == null) {
            return ResponseEntity.status(
                    HttpStatus.UNAUTHORIZED).build();
        }

        Object value = session.getAttribute(USERNAME);

        if (!(value instanceof String username)) {
            return ResponseEntity.status(
                    HttpStatus.UNAUTHORIZED).build();
        }

        Integer oldVisits =
                (Integer) session.getAttribute(VISITS);
        int nextVisits = (oldVisits == null ? 0 : oldVisits) + 1;
        session.setAttribute(VISITS, nextVisits);

        return ResponseEntity.ok(
                new ProfileResponse(username, nextVisits));
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }

        return ResponseEntity.noContent().build();
    }
}
~~~

**Điểm cần phân tích từ source:**

1. **getSession(true)** trong login tạo session nếu chưa có, hoặc dùng session hiện tại nếu có. Để đơn giản, demo ghi username/visits; production cần chống session fixation bằng Spring Security, không tự đánh dấu một username là authenticated.
2. Session attributes được giữ **ở server side**; client không nhận username/visits trong cookie. Với embedded Tomcat mặc định, session tracking cookie thường mang tên **JSESSIONID**.
3. **ResponseEntity.status(HttpStatus.SEE_OTHER)** đặt HTTP **303**, còn **location(...)** đặt Location thành /demo/profile. Đây là cặp cần assert cùng nhau.
4. GET profile dùng **getSession(false)**: nếu request không có session hợp lệ, controller không tạo session mới chỉ để đọc và trả **401**.
5. Bộ đếm visits ban đầu 0; lần GET thành công thứ nhất 1, thứ hai 2. Đây là **read-modify-write** trên HttpSession attribute nên **không an toàn cho những request đồng thời trên cùng session** nếu không có cơ chế đồng bộ. Mọi test trạng thái trong bài chạy **tuần tự**; xem phần concurrency.
6. **invalidate()** xóa hiệu lực session phía server. Client **có thể vẫn còn giữ cookie cũ**; cookie không làm session bị invalidate sống lại.
7. POST logout trả **204 No Content** cả khi session vắng mặt. Điều này giúp phép logout có tính idempotent về hiệu quả, nhưng POST không phải HTTP method idempotent theo định nghĩa chung; hành vi idempotent ở đây là do API quy định.
8. App không có login security thật. Nếu đem source này lên Internet sẽ cho phép bất kỳ người nào khai báo username tùy ý. Tuyệt đối không áp dụng như authentication implementation.

**Vì sao không đặt @SessionAttributes ở đây?** @SessionAttributes của Spring MVC là cơ chế lưu một số model attributes vào session cho workflow controller; nó **không đồng nhất với HttpSession API** và không phải yêu cầu khi muốn truy cập session trực tiếp. Bài tập tập trung vào cookie/servlet session HTTP boundary nên sử dụng HttpServletRequest.getSession.

## 6. Integration test: Java 17 HttpClient và CookieManager

**Chiến lược của test:**
- Mỗi phương thức @Test tạo **CookieManager và HttpClient của riêng mình**. Không dùng CookieHandler.setDefault(...), vì nó thay đổi global state của JVM.
- Client có cookie jar được cấu hình với **CookiePolicy.ACCEPT_ALL** cho **loopback-only integration fixture**. Đây không phải khuyến nghị chấp nhận cookie từ mọi nguồn trong production; với client thật cần policy thích hợp.
- Dùng **HttpClient.Redirect.NEVER** để nhìn tận mắt HTTP 303 và Location.
- Dùng **HttpClient.Redirect.NORMAL** ở test khác để kiểm tra client tự follow 303 từ POST sang GET.
- Luôn dùng URI dựa trên **@LocalServerPort**. Cổng do OS chọn, không hard-code 8080.
- Mỗi request có timeout, test send đồng bộ nên request sau chỉ chạy khi request trước đã trả response.

**src/test/java/demo/httpstate/SessionHttpIntegrationTest.java**

~~~java
package demo.httpstate;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private static BrowserState browser(
            HttpClient.Redirect redirectPolicy) {

        CookieManager jar =
                new CookieManager(null, CookiePolicy.ACCEPT_ALL);

        HttpClient client = HttpClient.newBuilder()
                .cookieHandler(jar)
                .followRedirects(redirectPolicy)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        return new BrowserState(client, jar);
    }

    private record BrowserState(
            HttpClient http, CookieManager jar) {
    }

    private HttpRequest loginRequest(String username)
            throws Exception {

        String json = mapper.writeValueAsString(
                new LoginRequest(username));

        return HttpRequest.newBuilder(uri("/demo/login"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();
    }

    private HttpRequest getRequest(String path) {
        return HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
    }

    private HttpRequest logoutRequest() {
        return HttpRequest.newBuilder(uri("/demo/logout"))
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
    }

    private static HttpResponse<String> send(
            HttpClient client, HttpRequest request)
            throws Exception {

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    private ProfileResponse profileBody(HttpResponse<String> response)
            throws Exception {

        return mapper.readValue(response.body(), ProfileResponse.class);
    }

    @Test
    void loginReturns303LocationAndSessionCookie() throws Exception {
        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        HttpResponse<String> response = send(
                browser.http(), loginRequest("Lan"));

        assertEquals(303, response.statusCode());
        assertEquals(
                "/demo/profile",
                response.headers()
                        .firstValue("Location").orElseThrow());

        assertTrue(response.headers()
                .allValues("Set-Cookie").stream()
                .anyMatch(value -> value.startsWith("JSESSIONID=")));

        assertTrue(browser.jar().getCookieStore().getCookies()
                .stream()
                .anyMatch(cookie ->
                        cookie.getName().equals("JSESSIONID")));
    }

    @Test
    void manualRedirectUsesStoredCookie() throws Exception {
        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        HttpResponse<String> first = send(
                browser.http(), loginRequest("Linh"));

        assertEquals(303, first.statusCode());

        URI destination = first.uri().resolve(
                first.headers().firstValue("Location").orElseThrow());

        assertEquals("127.0.0.1", destination.getHost());
        assertEquals(port, destination.getPort());
        assertEquals("/demo/profile", destination.getPath());

        HttpRequest follow = HttpRequest.newBuilder(destination)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> profile = send(browser.http(), follow);

        assertEquals(200, profile.statusCode());
        assertEquals(
                new ProfileResponse("Linh", 1), profileBody(profile));
    }

    @Test
    void repeatedRequestsKeepOneSessionAndAdvanceState()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        assertEquals(303, send(
                browser.http(), loginRequest("Mai")).statusCode());

        HttpResponse<String> first = send(
                browser.http(), getRequest("/demo/profile"));
        HttpResponse<String> second = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(200, first.statusCode());
        assertEquals(200, second.statusCode());
        assertEquals(
                new ProfileResponse("Mai", 1), profileBody(first));
        assertEquals(
                new ProfileResponse("Mai", 2), profileBody(second));
    }

    @Test
    void withoutCookieHandlerSessionCannotBeReused()
            throws Exception {

        HttpClient noJar = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        assertEquals(303, send(
                noJar, loginRequest("An")).statusCode());

        HttpResponse<String> profile = send(
                noJar, getRequest("/demo/profile"));

        assertEquals(401, profile.statusCode());
    }

    @Test
    void separateCookieJarsHaveSeparateSessions()
            throws Exception {

        BrowserState alice = browser(HttpClient.Redirect.NEVER);
        BrowserState bob = browser(HttpClient.Redirect.NEVER);

        assertEquals(303, send(
                alice.http(), loginRequest("Alice")).statusCode());
        assertEquals(303, send(
                bob.http(), loginRequest("Bob")).statusCode());

        HttpResponse<String> aliceProfile = send(
                alice.http(), getRequest("/demo/profile"));
        HttpResponse<String> bobProfile = send(
                bob.http(), getRequest("/demo/profile"));

        assertEquals(
                new ProfileResponse("Alice", 1),
                profileBody(aliceProfile));
        assertEquals(
                new ProfileResponse("Bob", 1),
                profileBody(bobProfile));
    }

    @Test
    void automatic303RedirectChangesPostIntoGet()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NORMAL);

        HttpResponse<String> finalResponse = send(
                browser.http(), loginRequest("Vy"));

        // HttpClient theo 303 -> GET /demo/profile với cookie.
        assertEquals(200, finalResponse.statusCode());
        assertEquals(
                "/demo/profile", finalResponse.uri().getPath());
        assertEquals(
                new ProfileResponse("Vy", 1),
                profileBody(finalResponse));

        HttpResponse<String> next = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(
                new ProfileResponse("Vy", 2), profileBody(next));
    }

    @Test
    void followingRedirectWithoutCookiesEndsAt401()
            throws Exception {

        HttpClient noJar = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpResponse<String> response = send(
                noJar, loginRequest("Minh"));

        // Theo Location nhưng không gửi JSESSIONID tới GET tiếp.
        assertEquals(401, response.statusCode());
        assertEquals("/demo/profile", response.uri().getPath());
    }

    @Test
    void logoutInvalidatesSessionOnServer()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        send(browser.http(), loginRequest("Hà"));

        HttpResponse<String> beforeLogout = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(200, beforeLogout.statusCode());

        HttpResponse<String> logout = send(
                browser.http(), logoutRequest());

        assertEquals(204, logout.statusCode());

        HttpResponse<String> afterLogout = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(401, afterLogout.statusCode());
    }

    @Test
    void blankLoginIsRejectedAndCannotOpenProfile()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        HttpResponse<String> rejected = send(
                browser.http(), loginRequest("  "));

        assertEquals(400, rejected.statusCode());

        HttpResponse<String> profile = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(401, profile.statusCode());
    }
}
~~~

**Tổng cộng 9 phương thức @Test**, không dùng @TestMethodOrder hay @TestInstance(PER_CLASS). Mỗi phương thức được thiết kế **độc lập** với các phương thức khác vì nó tự tạo HTTP client/cookie jar. Thứ tự chạy JUnit Jupiter không cần cố định.

### 6.1. Giải thích chi tiết từng kiểm thử

**Test 1 — loginReturns303LocationAndSessionCookie**

Test gắn **Redirect.NEVER** để thấy server trả status 303. Sau đó kiểm tra Location chính xác và response có Set-Cookie bắt đầu bằng JSESSIONID=. Nó cũng kiểm tra CookieManager đã lưu cookie trong store. Không assert giá trị session ID — đó là dữ liệu động, phải được tạo khác nhau và không nên phơi ra log. Không assert toàn bộ chuỗi Set-Cookie vì Tomcat có thể bổ sung Path/HttpOnly/SameSite khác nhau theo config.

**Test 2 — manualRedirectUsesStoredCookie**

Khi không tự follow, một request POST kết thúc ở 303. Test đọc **Location** và dùng URI.resolve để xây URI tiếp theo. Điều quan trọng là **dùng lại browser.http()**: cookie jar cùng instance nên GET /demo/profile mang JSESSIONID. Server trả ProfileResponse("Linh",1). Test cũng kiểm tra redirect không chuyển sang host khác trong phạm vi fixture.

**Test 3 — repeatedRequestsKeepOneSessionAndAdvanceState**

Cùng HTTP client được dùng cho POST login và hai GET profile liên tiếp. Expected visits lần lượt **1 và 2**; username vẫn là "Mai". Nếu mỗi request tạo HttpClient không có chung cookie jar, hoặc server không giữ session, test này thất bại. Đây là minh chứng trực tiếp cho **nhiều request liên tiếp**.

**Test 4 — withoutCookieHandlerSessionCannotBeReused**

JDK HttpClient không được gắn CookieManager sẽ không tự giữ cookie trong ví dụ. POST login vẫn thành công và trả 303, nhưng GET sau **không gửi JSESSIONID** nên nhận 401. Sự khác biệt không nằm ở controller logic — nó nằm ở HTTP client state.

**Test 5 — separateCookieJarsHaveSeparateSessions**

Hai browser giả lập có hai CookieManager khác nhau, cùng gọi một embedded server. Alice nhìn thấy session của Alice, Bob thấy session của Bob. Test dùng **tên khác nhau** thay vì assert session IDs ngẫu nhiên; nếu cookie jar bị chia sẻ ngoài dự kiến, assertion sẽ lộ lỗi.

**Test 6 — automatic303RedirectChangesPostIntoGet**

Khi dùng **Redirect.NORMAL**, HTTP client thấy 303 sau POST và tự gửi GET tới Location. Vì cũng có CookieManager, GET mang session cookie; response cuối cùng là **200** và URI cuối cùng là /demo/profile. Một GET tiếp theo trả visits=2, cho thấy redirect đã tạo lượt truy cập profile đầu tiên.

**Test 7 — followingRedirectWithoutCookiesEndsAt401**

Client follow redirect nhưng không lưu cookie. Nó có thể đi tiếp tới /demo/profile, song không có session ID, nên final response là **401**. Đây là kiểm thử tách hai trục độc lập: **follow redirect ≠ preserve session**. Chỉ bật followRedirects không đủ cho một workflow cần cookies.

**Test 8 — logoutInvalidatesSessionOnServer**

Client có thể vẫn giữ JSESSIONID trong cookie store sau logout; việc invalidate session do **server** thực hiện. GET sau logout trả 401. Test không phụ thuộc server có gửi thêm Set-Cookie để xóa cookie hay không; nó kiểm tra hiệu quả quan trọng nhất: **session cũ không còn quyền truy cập**.

**Test 9 — blankLoginIsRejectedAndCannotOpenProfile**

Username blank phải được từ chối bằng 400, và không nên tạo một session hợp lệ. GET profile sau đó trả 401. Đây là test âm kết hợp nhiều request, chứng minh request lỗi không vô tình tạo authenticated state trong demo.

**Về 401 trong bài này:** Nó được controller trả cho thiếu session theo hợp đồng minh họa. Trong production, 401/403 phải do security policy đúng nghĩa quyết định, thường qua Spring Security; đừng lấy việc session có một username string làm điều kiện an toàn để xác thực.

## 7. Chạy ví dụ và kiểm tra kết quả

Với một dự án đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Khi tự tạo project từ các file trong bài mà **chưa có wrapper scripts/JAR**, cần tạo bằng Gradle tương thích đã cài hoặc dùng **gradle test**. Các file build.gradle/settings.gradle không tự tạo ./gradlew.

Bộ source ở mục 5 và 6 có **9 phương thức JUnit Jupiter @Test**, toàn bộ thuộc **SessionHttpIntegrationTest**. Với phiên bản/dependencies và cấu hình server mặc định đã nêu, tất cả được thiết kế để PASS. Đây là **kỳ vọng của source mẫu**, không phải tuyên bố đã chạy test trong môi trường của người đọc. Báo cáo thực tế thường tại:

~~~text
build/reports/tests/test/index.html
~~~

Chạy đúng lớp cần debug:

~~~bash
./gradlew test --tests demo.httpstate.SessionHttpIntegrationTest
~~~

**Một số kết quả mang tính tất định:**

| Test/scenario | Response mong đợi | State quan trọng |
|---|---|---|
| Login Redirect.NEVER | **303** + Location + Set-Cookie | Client lưu JSESSIONID |
| Follow Location thủ công | **200**, username=Linh, visits=1 | Cùng cookie jar |
| POST login + hai GET | **303 → 200 → 200** | visits=1 rồi 2 |
| Client không có cookie handler | **303 → 401** | Cookie không được gửi lại |
| Hai cookie jars riêng | Hai response **200** | Alice/Bob không lẫn nhau |
| Redirect.NORMAL có CookieManager | Final **200** sau 303 | GET tự follow, visits=1 |
| Redirect.NORMAL không cookie jar | Final **401** sau 303 | Có redirect nhưng không có session |
| Login, profile, logout, profile | **303 → 200 → 204 → 401** | Session server invalidated |
| Login blank, GET profile | **400 → 401** | Không tạo session usable |

**Không được kỳ vọng một giá trị JSESSIONID hoặc một số port cố định.** Random port từ @LocalServerPort và session identifier do container tạo nên khác nhau giữa các lần chạy. Test chính xác là test **quan hệ giữa các requests**, không phải test các giá trị ngẫu nhiên.

## 8. Thử thủ công bằng curl để thấy rõ HTTP headers

Bản demo có thể được chạy riêng qua Gradle nếu ứng dụng đã cấu hình và build được:

~~~bash
./gradlew bootRun
~~~

Ở chế độ chạy ứng dụng thông thường, Spring Boot thường dùng cổng **8080** nếu bạn không đổi server.port. Trong **@SpringBootTest(RANDOM_PORT)** không nên giả định 8080; các lệnh curl dưới đây dành cho **bootRun cục bộ** dùng 8080, không phải test đang chạy cổng ngẫu nhiên.

Trên Bash/Linux/macOS, có thể thao tác:

~~~bash
# Login: -i hiển thị status/headers, -c lưu cookie từ response.
curl -i -c cookies.txt \
  -H 'Content-Type: application/json' \
  --data '{"username":"Lan"}' \
  http://127.0.0.1:8080/demo/login

# GET gửi cookie đã lưu: --cookie đọc jar.
curl -i --cookie cookies.txt \
  http://127.0.0.1:8080/demo/profile

# Lặp GET: visits tăng trong session cũ.
curl -i --cookie cookies.txt \
  http://127.0.0.1:8080/demo/profile

# Logout: cookie cũ có thể còn trên máy client.
curl -i --cookie cookies.txt -X POST \
  http://127.0.0.1:8080/demo/logout

# Sau logout, session đã invalidate -> 401.
curl -i --cookie cookies.txt \
  http://127.0.0.1:8080/demo/profile
~~~

Tệp cookies.txt chỉ là **cookie jar thử nghiệm** do curl ghi; không commit nó vào Git hay đẩy vào log vì có thể chứa session identifiers. Xóa file sau khi thử. Trên Windows PowerShell, dùng **curl.exe** và điều chỉnh quoting phù hợp với shell, vì alias/lệnh curl có thể khác Bash.

**Để quan sát redirect mà không bị follow:** không thêm -L; curl hiển thị status 303 và Location. Nếu thêm -L, client theo chuyển hướng; cần hiểu cookie jar đã được gắn để request tiếp theo có session. Không kết luận “server trả 200 thay vì 303” nếu bạn đang đọc response cuối sau chuỗi redirects.

## 9. CookieManager, CookieStore và sự cô lập test

### 9.1. Không phải cứ dùng cùng HttpClient là tự lưu cookies

Với Java 17 HttpClient, cookie handling là cấu hình **tùy chọn** qua builder.cookieHandler(...). Nếu không cấu hình, client không tự có một cookie jar dùng cho ví dụ. Để lưu cookies:

~~~java
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ALL);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(jar)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Tham số null đầu tiên tạo default in-memory CookieStore. **ACCEPT_ALL chỉ được dùng ở test loopback có kiểm soát**; trong client production cần chính sách cookie phù hợp với origin/domain và yêu cầu bảo mật. Có thể dùng **CookiePolicy.ACCEPT_ORIGINAL_SERVER** hoặc policy tự viết, nhưng phải kiểm tra tương thích với Set-Cookie thật của server.

**Không đặt CookieHandler.setDefault(jar)** trong mỗi @Test: đó là global state cấp JVM, có thể làm test khác nhận cookie ngoài dự kiến, đặc biệt khi chạy song song. Gắn CookieManager **vào từng HttpClient instance** là phương pháp dễ kiểm soát hơn.

### 9.2. Khi nào CookieManager tự gửi cookie?

CookieStore giữ cookie cùng các thuộc tính **Domain, Path, Secure, Max-Age/Expires**. Khi client gửi request mới, CookieManager chọn cookie phù hợp đích request. Ví dụ:
- Cookie gắn với Path=/demo có thể được gửi tới /demo/profile, không nhất thiết tới /admin.
- Cookie có Secure thường chỉ được gửi qua HTTPS theo quy tắc user agent.
- Cookie đã hết hạn có thể không được gửi.
- Thay hostname từ **127.0.0.1** sang **localhost** có thể khiến quy tắc domain/host thay đổi dù chúng trỏ đến cùng máy.
- Cookie manager của JDK **không phải trình duyệt**; không dùng nó để kết luận đầy đủ hành vi SameSite/CSRF trong browser.

Do đó test dùng **cùng hostname** 127.0.0.1 và cổng từ @LocalServerPort cho mọi request. Chúng ta không tự set Cookie header; để CookieManager làm việc nhằm kiểm thử đúng cơ chế client state.

### 9.3. Mỗi test dùng một jar, không chỉ một test instance

JUnit Jupiter thông thường tạo test class instance mới cho từng method, nhưng Spring TestContext có thể tái sử dụng ApplicationContext/server. Một **static CookieManager**, singleton client fixture hoặc một CookieHandler global vẫn có thể làm nhiều method share cookie không mong muốn.

Bộ ví dụ tạo BrowserState mới **ngay trong mỗi @Test**, nên việc giữ session chỉ tồn tại theo luồng của chính test ấy. Server vẫn có thể còn session không được invalidate cho đến khi timeout, nhưng các test khác không có session ID để truy cập nó.

Ở hệ thống lớn, cân nhắc dọn server sessions/DB/cache hoặc dùng môi trường tạm để tránh tài nguyên tồn tại lâu. Tuyệt đối không dùng cookie của một tài khoản production trong test.

## 10. Session lifecycle: tạo, truy cập, timeout và invalidate

**getSession(true)**: lấy session hiện có nếu request mang session ID hợp lệ; nếu không, tạo session mới.

**getSession(false)**: chỉ trả session hiện có, **không tạo mới**. Trường hợp client không có cookie hoặc cookie cũ không còn hợp lệ, kết quả thường null. Đây là cách phù hợp cho endpoint cần kiểm tra session có tồn tại không mà không tự tạo session rỗng.

**invalidate()**: làm session hiện tại không hợp lệ. Cookie client có thể vẫn tồn tại, nhưng server không còn state cũ. Nếu cần chủ động xóa cookie ở client (đặc biệt với custom cookie), server có thể gửi Set-Cookie hết hạn với name/path/domain tương ứng; không nên giả định session.invalidate tự gửi một Set-Cookie xóa cookie trong mọi servlet container.

**Timeout:** Session thường hết hạn sau một khoảng không hoạt động; Spring Boot servlet có cấu hình **server.servlet.session.timeout**. Không nên dùng **Thread.sleep(30 phút)** để test timeout mặc định. Nếu thật sự cần kiểm tra hết hạn, cấu hình một session timeout ngắn trong test profile/isolated context, kiểm tra bằng thời gian có giới hạn và tránh chồng với test khác; hoặc unit test abstraction quản lý expiry riêng.

**Session ID rotation:** Khi xác thực thật, Spring Security thường hỗ trợ cơ chế chống session fixation, bao gồm thay session ID theo cấu hình. Demo ở đây **không làm security login**, vì vậy không test một chính sách session fixation. Trong ứng dụng thật, hãy kiểm tra login thành công không dùng lại ID session do attacker cố định, đồng thời kiểm tra chính sách sau logout.

**State có thể biến mất khi app restart:** Embedded Tomcat in-memory session không nhất thiết tồn tại sau restart hoặc khi request tới instance khác. Nếu cần session phân tán, xem Spring Session với Redis/JDBC và sticky-session/load-balancer policy. Cookie hiện diện không có nghĩa session server-side còn tồn tại trên mọi node.

## 11. Cookie security: HttpOnly, Secure, SameSite, Path và Domain

Những attributes của **Set-Cookie** tác động tới cách browser xử lý:

| Attribute | Tác dụng | Điểm cần lưu ý khi test |
|---|---|---|
| **HttpOnly** | Hạn chế JavaScript đọc cookie | Không thay thế XSS protection; browser vẫn gửi cookie qua request phù hợp |
| **Secure** | Giới hạn cookie trên kết nối an toàn | Ở test HTTP loopback, đừng bật Secure rồi kỳ vọng JDK client luôn gửi như HTTPS |
| **SameSite=Strict/Lax/None** | Quy định khi browser gửi cookie trong cross-site contexts | Không dùng HttpClient đơn thuần làm bằng chứng browser chống CSRF |
| **Path** | Giới hạn request path có cookie | Mỗi endpoint của demo cùng /demo |
| **Domain** | Giới hạn/cho phép hostname/subdomains | Không đổi giữa localhost và 127.0.0.1 trong cùng scenario |
| **Max-Age / Expires** | Thời hạn cookie phía client | Hết hạn cookie không giống hẳn session timeout phía server |
| **Name** | Tên cookie, ví dụ JSESSIONID | Nếu custom server.servlet.session.cookie.name, sửa assertion |

Trong Spring Boot 3.3, các property thường gặp:

~~~properties
# Ví dụ cho môi trường HTTPS thật, KHÔNG áp dụng nguyên
# vào bài integration test HTTP loopback:
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
~~~

**Tại sao không đặt các properties trên vào ví dụ chạy được?** Bài test dùng **http://127.0.0.1** chứ không dùng HTTPS, trong khi cookie Secure có semantics riêng theo client/browser. Nếu ép Secure trong một test HTTP loopback, có thể tạo lỗi client không gửi cookie, làm lệch mục tiêu kiểm tra. Trong production, cookie session nhạy cảm nên được bảo vệ bằng HTTPS + Secure/HttpOnly/SameSite phù hợp và các biện pháp CSRF.

Lưu ý **SameSite=None** thường yêu cầu **Secure** trong browser hiện đại. Cấu hình cookie trong Spring Boot không thay cho CSRF defense nếu API dùng cookie-based authentication cho state-changing methods.

### 11.1. Authentication và session demo là hai việc khác nhau

Mặc dù endpoint tên login, controller trong bài nhận **username tùy ý** mà không kiểm tra password/token. Không được coi đó là cơ chế đăng nhập production. Ứng dụng thật cần:
- Authentication bằng Spring Security, lưu authentication state theo security session strategy hoặc token design phù hợp.
- Chống **session fixation** khi chuyển trạng thái anonymous → authenticated.
- CSRF protection cho cookie-authenticated state-changing operations nếu thiết kế yêu cầu.
- Logout làm vô hiệu session/token theo threat model, không chỉ trả 204.
- Cookie attributes an toàn, HTTPS và policy storage/expiration.
- Không expose JSESSIONID trong debug logs, query strings hay client-visible JSON.

Bộ ví dụ chỉ chứng minh rằng **một cookie liên kết nhiều HTTP requests với một HttpSession**. Tách bạch mục tiêu giúp không biến một bài học testing thành hướng dẫn bảo mật sai.

## 12. Redirect và cookies là hai trục kiểm thử độc lập

Xem bốn trường hợp:

| Client follow redirect? | Client lưu cookie? | POST login rồi xem kết quả | Vì sao |
|---|---|---|---|
| **Không** | Có | Nhận **303**; tự GET sau được **200** | Cookie jar giữ JSESSIONID |
| **Không** | Không | Nhận **303**; tự GET sau nhận **401** | Không có session ID |
| **Có (NORMAL)** | Có | HTTP client tự follow, final **200** | 303 đổi POST thành GET, cookie được gửi |
| **Có (NORMAL)** | Không | HTTP client tự follow, final **401** | Theo URL không đồng nghĩa theo session |

Đây là lý do **một assertion status cuối cùng chưa đủ** để phát hiện nguyên nhân thất bại. Nếu mong final 200 nhưng nhận 401, câu hỏi đầu tiên không nhất thiết là controller có lỗi; có thể bạn đang follow đúng redirect nhưng **quên CookieManager**.

Ngược lại, nếu mong 303 mà nhận 200, kiểm tra client có bật auto-follow không, hoặc một test helper đã thay HTTP request factory. Muốn test 3xx contract, **tắt auto-follow** và assert Location/Set-Cookie trực tiếp.

Khi redirect trỏ sang domain khác, cookie gắn với origin cũ **không nên tự được gửi** sang domain mới nếu không khớp Domain/Path/Secure policy. Đừng cố “sửa test” bằng cách copy raw Cookie header bất kể origin: đó có thể làm lộ session ID sang bên thứ ba.

## 13. Session state khi chạy đồng thời và khi context được cache

Trong demo, session giữ một Integer visits với logic:

~~~java
Integer visits = (Integer) session.getAttribute("visits");
int next = (visits == null ? 0 : visits) + 1;
session.setAttribute("visits", next);
~~~

Đây là **read-modify-write không nguyên tử**. Nếu hai requests đến **đồng thời với cùng JSESSIONID**, cả hai có thể đọc visits=1, cùng ghi 2 và làm mất một lần tăng. Bộ tests mẫu dùng các request **tuần tự**, vì chúng kiểm tra sequence/session chứ không kiểm tra concurrent increments.

Nếu nghiệp vụ yêu cầu đếm chính xác dưới concurrency, cân nhắc:
- Dùng một thành phần state có phép tăng **atomic** phù hợp với phạm vi session/storage.
- Dùng database transaction/optimistic locking hoặc key-value store atomic increment khi cần distributed state.
- Tránh lưu mutable object không thread-safe trong session.
- Viết concurrency tests riêng, không kỳ vọng HttpSession tự serialize mọi requests vào cùng session.

**Spring TestContext cache:** Các test method dùng cùng @SpringBootTest config có thể dùng lại embedded server và session manager. Vì thế:
- Đừng dùng static CookieManager giữa các test.
- Đừng dựa vào thứ tự test để tận dụng session do test trước tạo.
- Mỗi test nên tạo cookie jar/account/fixture riêng, hoặc dọn state rõ ràng.
- Một **@DirtiesContext** có thể buộc khởi động lại server nhưng không phải cách khuyến nghị để dọn cookie jar; dọn state đúng chủ sở hữu.
- Nếu dữ liệu được lưu trong Redis/JDBC qua Spring Session, context restart **không tự xóa** dữ liệu bên ngoài.

## 14. Giao dịch DB khi HTTP client và server ở hai threads

Bộ demo không có persistence, nhưng trong integration test thật, login, checkout, cart hoặc session-backed order có thể ghi database. Khi @SpringBootTest dùng **RANDOM_PORT** hay **DEFINED_PORT**, HTTP client và server xử lý request ở các threads/transactions khác nhau.

**Bẫy thường gặp:** Annotation @Transactional trên test method rollback **test-managed transaction** sau test; nó **không tự rollback transaction đã commit bởi server-side request**. Vì vậy một POST qua HTTP có thể để lại dữ liệu trong DB, ảnh hưởng test sau.

Cách xử lý:
1. Dùng test DB/schema/Redis namespace riêng.
2. Dùng ID duy nhất cho test dữ liệu ghi vào server.
3. Cleanup repository/script/fixture ở transaction phù hợp **sau khi request server hoàn tất**.
4. Dùng Testcontainers hoặc database tạm để giảm nhiễm dữ liệu giữa runs.
5. Đừng coi @DirtiesContext là cách xóa DB/Redis; nó chỉ tác động cache ApplicationContext.
6. Với nhiều request liên tiếp, phải phân biệt **state trong HttpSession** với state ở persistence; logout không nhất thiết xóa cart/order đã ghi DB.

**Tách phạm vi:** Session test cần chứng minh client gửi JSESSIONID và server giữ attributes; database transaction test cần chứng minh persistence semantics. Không gộp hai mục tiêu mà thiếu cleanup, vì lỗi sẽ khó xác định hơn.

## 15. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Cách khắc phục |
|---|---|---|
| Login trả 303 nhưng profile trả 401 | Client không lưu hoặc không gửi JSESSIONID | Gắn CookieManager, dùng cùng client/jar qua requests |
| Test mong 303 nhưng nhận 200 | HTTP client tự follow redirect | Dùng Redirect.NEVER và assert Location |
| Test mong final 200 nhưng nhận 303 | Client không follow redirect | Dùng Redirect.NORMAL hoặc tự gửi GET tới Location |
| Follow 303 thành 401 | Redirect có nhưng cookie jar vắng | Kiểm tra hai trục redirect và cookie riêng |
| CookieStore có JSESSIONID nhưng server không tìm session | Cookie không gửi do path/domain/secure/expired, hoặc session đã invalid/timeout | Kiểm tra request Cookie, session store và hostname |
| Gọi localhost:8080 fail | @SpringBootTest dùng RANDOM_PORT | Dùng @LocalServerPort |
| Cookie có khi chạy một test nhưng mất khi chạy khác | CookieManager tạo mới hoặc test chia sẻ global state không kiểm soát | Tạo client riêng theo scenario; kiểm tra chính sách |
| Visits không tăng đúng dưới concurrency | Read-modify-write không atomic | Cô lập sequential tests; thiết kế atomic cho concurrency |
| Logout xong GET vẫn thành công | Server chưa invalidate session hoặc đã tạo session mới ngoài ý muốn | Kiểm tra getSession(false), invalidate và auth policy |
| GET unauthorized vẫn phát Set-Cookie ngoài dự kiến | Code dùng getSession(true) hoặc filter tạo session | Dùng getSession(false) khi chỉ cần kiểm tra; xem security |
| Server session tồn tại nhưng browser không gửi cookie | SameSite/Secure/Domain/Path hoặc CSRF flow | Test bằng browser thật khi cần, kiểm tra cookie attributes |
| Test pass riêng nhưng fail cùng suite | Cookie jar static, shared session, DB/Redis state hoặc context cache | Tách fixtures/cleanup đúng boundary |
| POST dùng redirect 307 làm GET handler không chạy | 307 giữ POST method/body | Dùng 303 nếu muốn POST → GET |
| Nhận 401/403 ngay login khi thêm Security | Authentication/CSRF của Spring Security | Gửi credentials/CSRF token đúng contract, đừng tắt bừa bảo mật |
| @Transactional test không rollback DB write của server | Server request ở thread/transaction khác | Dùng test DB và cleanup tường minh |

**Quy trình debug tối thiểu:**

1. Xem **response status của POST login** trước khi tự follow. Nếu 303, đọc **Location** và **Set-Cookie**.
2. Xác nhận HTTP client có cookie handler và CookieStore giữ JSESSIONID.
3. Xem URL request kế tiếp: **cùng host và path nằm trong phạm vi cookie**? Đừng đổi localhost ↔ 127.0.0.1.
4. Nếu client follow tự động, xem **response.uri()** và final status để biết đã đi đâu.
5. Nếu GET 401, kiểm tra server nhận Cookie header và **getSession(false)** có trả session hợp lệ không.
6. Nếu hai client lẫn state, kiểm tra static CookieManager/HttpClient hoặc session fixtures.
7. Nếu logout không hiệu quả, kiểm tra invalidate, session ID rotation, caches/authentication store.
8. Nếu lỗi chỉ xảy ra trên CI, xem network sandbox/port, startup logs, parallelism, DB state và browser vs Java client semantics.
9. Đối chiếu status, Location, Set-Cookie/Cookie, body và session state **theo thứ tự requests**, không chỉ dựa vào một assertion cuối.
10. Tránh in toàn bộ session identifiers vào CI logs; log tên cookie hoặc trạng thái có/không thay vì giá trị bí mật.

## 16. Bài tập áp dụng và tự kiểm tra

**Bài 1 — Chứng minh cookie cần thiết.** Tạo một HttpClient không gắn CookieManager, gửi POST login và GET profile. Vì sao POST trả 303 nhưng GET trả 401? Thêm CookieManager có thay đổi redirect policy không?

**Bài 2 — Xem redirect rõ ràng.** Dùng Redirect.NEVER và assert 303, Location, Set-Cookie. Sau đó bật Redirect.NORMAL và assert final URI/path cùng 200. Vì sao trong trường hợp thứ hai bạn không còn trực tiếp nhìn thấy response 303 như response cuối?

**Bài 3 — Hai clients độc lập.** Tạo hai CookieManager, login Alice/Bob, GET hai profile. Viết assertion chứng minh không lấy nhầm username. Nếu dùng CookieHandler.setDefault ở @BeforeEach cho cả suite có rủi ro gì?

**Bài 4 — Logout.** Sau logout, một client vẫn còn cookie JSESSIONID trong jar. Vì sao server phải từ chối phiên cũ? Một session cookie có tự chứa username và visits không?

**Bài 5 — Cookie scope.** Cấu hình cookie path=/demo. Request GET /demo/profile và GET /admin có cùng nhận cookie không? Khi đổi host từ localhost sang 127.0.0.1, vì sao có thể mất session dù vẫn cùng máy?

**Bài 6 — Redirect method.** So sánh POST nhận 303 và POST nhận 307. Với 307, client có được tự ý chuyển thành GET không? Status nào phù hợp với POST/Redirect/GET trong bài?

**Bài 7 — Concurrency.** Hai GET profile gửi đồng thời trên cùng session có thể làm mất một increment visits. Vì sao? Đề xuất cách test và lưu state bảo đảm atomic khi nghiệp vụ cần.

**Bài 8 — Production security.** Nếu nhận X-Username header rồi gán vào session mà không xác thực, client có thể giả mạo quyền như thế nào? Hãy thay demo bằng Spring Security login/CSRF/session fixation policy, kiểm tra status 401/403 và session rotation theo thiết kế.

**Bài 9 — Cookie flags.** Khi bật Secure cho session cookie nhưng vẫn test qua HTTP 127.0.0.1 bằng JDK HttpClient, vì sao cookie có thể không được gửi? Bạn nên thay đổi test transport hay làm yếu cookie policy production?

**Bài 10 — Transaction.** Một POST qua RANDOM_PORT ghi DB trong server transaction. Vì sao @Transactional đặt trên JUnit method không rollback DB write ấy? Hãy đề xuất cơ chế cleanup.

**Đáp án ngắn cần ghi nhớ:** CookieManager lưu/gửi ID đúng scope; HttpSession lưu state ở server; redirect policy quyết định có theo Location; 303 chuyển POST sang GET; invalidate làm ID cũ vô hiệu; context cache có thể giữ server/session manager nhưng mỗi test cần cookie jar riêng; real HTTP transaction không phải transaction của test method.

## 17. Tài liệu chuẩn để đối chiếu

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — @SpringBootTest(RANDOM_PORT), @LocalServerPort, lưu ý transaction khác thread.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html) — Servlet container settings và session cookie configuration.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/) — server.servlet.session.timeout, cookie.http-only/secure/same-site/path.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — HTTP client, cookie handler và redirect defaults.
- [Java SE 17 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html) — NEVER, NORMAL, ALWAYS.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html) — CookieStore, policy và lưu cookie.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — Location/redirect, 303, 307 và 308.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) — HttpOnly, Secure, SameSite, Domain/Path và expiration.

**Kết luận:** Kiểm thử HTTP nhiều bước cần **bảo toàn state đúng ở client và server**. CookieManager làm client gửi lại JSESSIONID; HttpSession giữ dữ liệu ở server; Location + redirect policy quyết định request tiếp theo. Hãy kiểm tra **từng status/header/body trong chuỗi**, tạo cookie jar riêng cho mỗi test, không dựa thứ tự test, và tách rõ demo session với authentication/security production.