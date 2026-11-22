# HttpSession của Servlet và WebSession của WebFlux trong Spring Boot

## 1. Session dùng để làm gì?

HTTP là giao thức request–response. Theo mặc định, server không tự nhớ một request trước khi nhận request kế tiếp. Khi cần giữ giỏ hàng tạm, bước đang làm của biểu mẫu, tùy chọn giao diện hoặc trạng thái đăng nhập giữa các request, ứng dụng có thể sử dụng **server-side session**.

Spring Boot có hai API session tương ứng hai web stack:

- **`jakarta.servlet.http.HttpSession`** dành cho **Jakarta Servlet / Spring MVC**, thường chạy trên Tomcat hoặc Jetty.
- **`org.springframework.web.server.WebSession`** dành cho **Spring WebFlux / Reactive**, thường chạy trên Reactor Netty nhưng cũng hỗ trợ các runtime HTTP phù hợp khác.

Cả hai lưu attributes phía server và liên kết request với session qua **session ID**, thường trao đổi bằng **cookie**. Điểm khác biệt cốt lõi là cách tạo/bắt đầu phiên, cách xử lý các thao tác vòng đời, API và cơ chế lưu trữ.

Học xong bài này, bạn sẽ có thể:
1. Phân biệt session, session ID, cookie, request attribute và trạng thái đăng nhập.
2. Dùng đúng `HttpSession` trong MVC và `WebSession` trong WebFlux.
3. Hiểu `request.getSession(false)`, `WebSession.start()` và `isStarted()`.
4. Thực hành hai ví dụ Spring Boot Java 17+ hoàn chỉnh và xác thực cookie bằng `curl`.
5. Cấu hình timeout, Secure, HttpOnly, SameSite theo từng stack.
6. Phân tích session fixation, logout, concurrency, local store và Spring Session Redis.

> **Phiên bản thực hành:** hai ứng dụng mẫu là **hai dự án riêng** dùng Java 17+, Spring Boot **3.5.x** với Gradle và đúng starter MVC/WebFlux. Với Spring Boot 4.x, starter MVC được đổi sang `spring-boot-starter-webmvc`; kiểm tra lại dependency theo phiên bản. Các ví dụ chưa tích hợp Spring Security, để dễ quan sát vòng đời session đơn thuần.

## 2. Cookie và session ID đi qua HTTP như thế nào?

~~~text
Browser                               Spring Boot
  |                                       |
  | POST /visit (chưa có session cookie)  |
  |-------------------------------------->|
  |                           tạo/bắt đầu session
  |                           lưu visits=1 phía server
  | HTTP 200                              |
  | Set-Cookie: SESSION_ID=<id>; ...      |
  |<--------------------------------------|
  |                                       |
  | GET /visit                            |
  | Cookie: SESSION_ID=<id>               |
  |-------------------------------------->|
  |                           tra ID -> session -> visits
  | HTTP 200                              |
  |<--------------------------------------|
~~~

`SESSION_ID` và `<id>` trong sơ đồ chỉ là ký hiệu. Cookie thực tế thường có tên `JSESSIONID` với Servlet container hoặc `SESSION` với WebFlux default resolver; tên, Domain, Path và các flags có thể được tùy biến.

**Cookie không phải session object.** Cookie thường chỉ mang ID để server tìm lại attributes từ memory, Redis, JDBC hoặc session store khác. Client giữ cookie; dữ liệu như `visits` được lưu ở server. Vì ID cho phép liên kết tới một phiên, phải coi session ID như **bí mật có giá trị xác thực**: không log nguyên văn, không đưa vào URL, query parameter, response JSON hoặc trang lỗi công khai.

| Đối tượng | Sống ở đâu? | Phạm vi |
|---|---|---|
| Request attribute | Trong xử lý một HTTP request | Không tự tồn tại qua request kế tiếp |
| Session attribute | Server-side session store | Qua nhiều request cùng session đến khi hết hạn/xóa |
| Session ID | Server biết ID; client thường giữ qua cookie | Định danh để tìm session |
| Cookie | Browser/client | Gửi theo điều kiện Domain, Path, Secure, SameSite |
| JWT hoặc access token | Client và hệ thống xác thực tùy kiến trúc | Không tự tương đương với server-side session |

Một cookie `JSESSIONID` xuất hiện **không chứng minh** người dùng đã đăng nhập. Session ẩn danh cũng có thể dùng cookie; kiểm tra quyền vẫn phải do authentication/authorization xác định.

## 3. So sánh API HttpSession và WebSession

| Khía cạnh | Servlet `HttpSession` | Reactive `WebSession` |
|---|---|---|
| Package | `jakarta.servlet.http.HttpSession` | `org.springframework.web.server.WebSession` |
| Web stack | Spring MVC / Servlet | Spring WebFlux |
| Nhận phiên | `request.getSession()` hoặc `request.getSession(false)` | Inject `WebSession` hoặc `exchange.getSession()` |
| Thời điểm bắt đầu | `getSession()` tạo session nếu chưa có | Chỉ lấy `WebSession` không tự bắt đầu; thêm attribute hoặc `start()` để bắt đầu |
| Đọc attribute | `getAttribute(String)` trả `Object` | `getAttribute(String)` / `getAttributeOrDefault(String,T)` |
| Ghi attribute | `setAttribute(String,Object)` | `getAttributes().put(String,Object)` |
| Xóa attribute | `removeAttribute(String)` | `getAttributes().remove(String)` |
| Đọc ID | `getId()` | `getId()` |
| Trạng thái | `isNew()`: client đã tham gia phiên chưa | `isStarted()`: session đã được bắt đầu chưa |
| Time-to-idle | `getMaxInactiveInterval()` trả số giây | `getMaxIdleTime()` trả `Duration` |
| Thay timeout | `setMaxInactiveInterval(int)` | `setMaxIdleTime(Duration)` |
| Creation/access time | Giá trị `long` (milliseconds kể từ epoch) | `Instant` |
| Rotate ID | `HttpServletRequest.changeSessionId()` | `WebSession.changeSessionId()` trả `Mono<Void>` |
| Logout/invalidate | `invalidate()` trả `void` | `invalidate()` trả `Mono<Void>` |
| Lưu cuối request | Container/SessionRepository xử lý | WebFlux thông thường gọi `save()` trước khi commit response |
| Local store mặc định | Session manager của Servlet container | `InMemoryWebSessionStore` qua `DefaultWebSessionManager` |
| Shared store | Spring Session với Redis hoặc JDBC | Spring Session với `ReactiveSessionRepository`, ví dụ Redis |

**Đặc biệt:** `isNew()` của Servlet không tương đương với `isStarted()` của WebFlux. `isNew()` phản ánh client đã tham gia session hay chưa theo hợp đồng Servlet; `isStarted()` cho biết một WebSession đã được bắt đầu tường minh hay nhờ có attribute.

Spring Boot chọn web stack theo classpath và cấu hình. Nếu cả MVC và WebFlux cùng có mặt, Boot thông thường ưu tiên Servlet/MVC. Vì vậy dùng Tomcat hay Netty **không đủ** để quyết định API session; phải xem web application type và framework đang xử lý request.

## 4. HttpSession: cách tạo, đọc, cập nhật và kết thúc

### 4.1. Lấy session có kiểm soát

Trong một controller Spring MVC:

~~~java
HttpSession createdOrExisting = request.getSession(); // Có thể tạo session mới
HttpSession onlyExisting = request.getSession(false);  // Không tạo, có thể null
~~~

Hai lời gọi khác nhau về tác động:
- `getSession()` hay `getSession(true)` tìm session hợp lệ, nếu không có thì tạo mới.
- `getSession(false)` trả `null` nếu không có session hợp lệ.
- Một controller nhận `HttpSession` làm tham số thường được cung cấp session theo cơ chế argument resolution; nếu muốn bảo đảm **không sinh session khi chỉ đọc**, hãy lấy `HttpServletRequest` rồi gọi `getSession(false)`.

Thường sau khi tạo session mới, Servlet container phát `Set-Cookie: JSESSIONID=...`. Việc phát cookie cụ thể phụ thuộc tracking mode, response state và container.

### 4.2. Attributes và thời gian sống

~~~java
HttpSession session = request.getSession();
session.setAttribute("theme", "dark");
String theme = (String) session.getAttribute("theme");
session.removeAttribute("theme");
~~~

`getAttribute` trả `Object` nên cần cast hoặc kiểm tra kiểu dữ liệu. Thời gian:
- `getCreationTime()` và `getLastAccessedTime()` trả giá trị milliseconds.
- `getMaxInactiveInterval()` và `setMaxInactiveInterval(int seconds)` cho phép đọc/thay khoảng thời gian không hoạt động.
- Session được xem là quá hạn khi không hoạt động vượt giới hạn theo cơ chế container/store.
- `invalidate()` làm session không còn hợp lệ. Gọi tiếp method trên session đã invalid có thể ném `IllegalStateException`.

### 4.3. Đổi ID sau đăng nhập

~~~java
// Fragment trong MVC khi request đang có session hợp lệ:
request.changeSessionId();
~~~

`changeSessionId()` nằm trên `HttpServletRequest`, **không phải** method của `HttpSession`. Nó là biện pháp hữu ích chống session fixation khi người dùng được xác thực. Nếu dùng Spring Security, hãy để session fixation protection của Security điều phối; không thêm logic rotate trùng lặp.

## 5. WebSession: lấy được session chưa chắc đã tạo cookie

### 5.1. Inject WebSession

Spring WebFlux cho phép truyền `WebSession` trực tiếp vào handler method:

~~~java
// Fragment trong @RestController WebFlux:
@GetMapping("/theme")
public String theme(WebSession session) {
    return session.getAttributeOrDefault("theme", "light");
}
~~~

Lời gọi này **chỉ đọc**. Khi chưa có session cũ, việc tạo đối tượng `WebSession` không tự bắt đầu một session được lưu hoặc phát cookie ID. WebSession bắt đầu:
- **Implicit**: khi thêm attribute vào `session.getAttributes()`.
- **Explicit**: gọi `session.start()`.
- Có thể xem `session.isStarted()` để biết đã bắt đầu hay chưa.

~~~java
session.getAttributes().put("theme", "dark");
session.start();
boolean started = session.isStarted();
~~~

Đoạn trên chỉ minh họa API trong handler, không phải class Java độc lập. Ghi một attribute đã đủ bắt đầu session; không nhất thiết gọi thêm `start()`.

### 5.2. WebSession có Mono cho thao tác vòng đời

~~~java
Mono<Void> rotated = session.changeSessionId();
Mono<Void> removed = session.invalidate();
~~~

WebFlux làm việc theo publisher: kết quả `Mono<Void>` **phải trở thành một phần của luồng được subscribe**. Ví dụ:

~~~java
@PostMapping("/logout")
public Mono<String> logout(WebSession session) {
    return session.invalidate().thenReturn("logged out");
}
~~~

Nếu chỉ gọi `session.invalidate()` rồi bỏ qua Mono và trả kết quả khác, thao tác bất đồng bộ có thể **không được thực thi**. Không dùng `block()` trên Reactor event loop để ép kết quả; hãy compose bằng `then`, `flatMap`, `thenReturn` theo luồng xử lý.

`WebSession.save()` cũng trả Mono nhưng framework thông thường gọi trước lúc commit response. Không cần tự gọi `save()` ở mỗi controller. Khi dùng Spring Session với Redis reactive, cần kết nối/storage không chặn phù hợp; bản thân tên WebSession không khiến các I/O tùy ý trong handler trở thành non-blocking.

## 6. Ví dụ runnable A — Spring Boot MVC và HttpSession

Tạo một dự án bằng Spring Initializr: **Spring Boot 3.5.x, Java 17+, Gradle**, dependency **Spring Web**. Không thêm Spring Security trong bài thử này. Nếu dự án đã có Boot plugin và dependency management, dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Đặt file `src/main/java/demo/servlet/ServletSessionDemo.java`:

~~~java
package demo.servlet;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ServletSessionDemo {

    public static void main(String[] args) {
        SpringApplication.run(ServletSessionDemo.class, args);
    }

    @PostMapping("/visit")
    public Map<String, Integer> visit(HttpServletRequest request) {
        HttpSession session = request.getSession();
        Integer current = (Integer) session.getAttribute("visits");
        int next = (current == null ? 0 : current) + 1;
        session.setAttribute("visits", next);
        return Map.of("visits", next);
    }

    @GetMapping("/visit")
    public Map<String, Integer> read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        Integer visits = session == null ? null
                : (Integer) session.getAttribute("visits");
        return Map.of("visits", visits == null ? 0 : visits);
    }

    @PostMapping("/logout")
    public Map<String, Boolean> logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return Map.of("loggedOut", true);
    }
}
~~~

Đây là một class Java đầy đủ trong project đúng dependency. Ví dụ chỉ quản lý bộ đếm `visits` để quan sát session; endpoint `/logout` không đại diện cho quy trình logout của hệ thống bảo mật thật.

Chạy từ thư mục root của dự án:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi Boot chạy ở `localhost:8080`, gửi lần lượt:

~~~bash
curl -sS -c servlet-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b servlet-cookies.txt -c servlet-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b servlet-cookies.txt http://localhost:8080/visit
curl -sS -b servlet-cookies.txt -X POST http://localhost:8080/logout
curl -sS -b servlet-cookies.txt http://localhost:8080/visit
~~~

**Năm response body JSON kỳ vọng, mỗi dòng là kết quả một request độc lập:**

~~~text
{"visits":1}
{"visits":2}
{"visits":2}
{"loggedOut":true}
{"visits":0}
~~~

Vì sao?
1. Request đầu không gửi cookie cũ, `getSession()` tạo session và lưu 1; `curl -c` giữ cookie.
2. Request thứ hai dùng `curl -b` gửi cookie, nên server tìm lại session và tăng lên 2.
3. GET dùng `getSession(false)` đọc 2.
4. POST logout invalidate session.
5. GET với ID đã invalid không tìm ra session hợp lệ, trả 0.

Header `Set-Cookie` và ID ngẫu nhiên sẽ thay đổi giữa các lần chạy. Đừng cố so sánh chính xác chuỗi ID với output minh họa. Nếu ứng dụng có Spring Security, các POST mặc định có thể cần CSRF token; ví dụ này cố ý không thêm Security.

## 7. Ví dụ runnable B — Spring WebFlux và WebSession

Tạo **một dự án riêng khác**, Spring Boot 3.5.x, Java 17+, Gradle, dependency **Spring Reactive Web (WebFlux)**. Không thêm starter MVC vào dự án này. Dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Tạo file `src/main/java/demo/reactive/ReactiveSessionDemo.java`:

~~~java
package demo.reactive;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveSessionDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionDemo.class, args);
    }

    @PostMapping("/visit")
    public Mono<Map<String, Integer>> visit(WebSession session) {
        int next = session.getAttributeOrDefault("visits", 0) + 1;
        session.getAttributes().put("visits", next);
        return Mono.just(Map.of("visits", next));
    }

    @GetMapping("/visit")
    public Mono<Map<String, Integer>> read(WebSession session) {
        int value = session.getAttributeOrDefault("visits", 0);
        return Mono.just(Map.of("visits", value));
    }

    @PostMapping("/logout")
    public Mono<Map<String, Boolean>> logout(WebSession session) {
        return session.invalidate()
                .thenReturn(Map.of("loggedOut", true));
    }
}
~~~

Chạy cùng lệnh `./gradlew bootRun` hoặc `.\gradlew.bat bootRun` từ dự án reactive. Dừng dự án Servlet trước khi chạy reactive nếu cả hai cùng dùng cổng 8080.

~~~bash
curl -sS -c reactive-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b reactive-cookies.txt -c reactive-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b reactive-cookies.txt http://localhost:8080/visit
curl -sS -b reactive-cookies.txt -X POST http://localhost:8080/logout
curl -sS -b reactive-cookies.txt http://localhost:8080/visit
~~~

**Response body JSON kỳ vọng:**

~~~text
{"visits":1}
{"visits":2}
{"visits":2}
{"loggedOut":true}
{"visits":0}
~~~

Lý giải sự giống và khác:
- Luồng request và kết quả có thể giống Servlet vì cả hai duy trì state theo cookie.
- WebFlux `getAttributeOrDefault` chỉ đọc không tự start session.
- `session.getAttributes().put` bắt đầu session khi lần đầu cần state; framework tự lưu khi response được commit.
- `session.invalidate().thenReturn(...)` thực hiện hủy session trong reactive chain.
- Cookie default WebFlux thường tên `SESSION`, không nên hardcode vào client; `curl` lưu đúng cookie server phát.

**Thử thêm:** chạy `curl -i http://localhost:8080/visit` trước mọi POST và xem header `Set-Cookie`. Trong WebFlux mặc định, chỉ đọc WebSession mới chưa start không cần tạo cookie. So sánh với một handler Servlet gọi `request.getSession()` dù chỉ đọc: Servlet có thể tạo session sớm hơn.

## 8. Cấu hình timeout và cookie trong Spring Boot

### 8.1. Servlet

Ví dụ cấu hình `application.yml` dành cho môi trường **HTTPS production**:

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        name: JSESSIONID
        http-only: true
        secure: true
        same-site: lax
~~~

Các property quan trọng:
- `server.servlet.session.timeout`: thời gian không hoạt động (idle timeout) trước khi session có thể hết hạn.
- `server.servlet.session.cookie.name`: tên session cookie.
- `http-only`: browser hạn chế JavaScript đọc cookie.
- `secure`: chỉ gửi cookie trong kênh HTTPS theo chính sách trình duyệt.
- `same-site`: giảm một số trường hợp cookie tự gửi trong cross-site request.

### 8.2. Reactive

Ví dụ HTTPS production tương ứng:

~~~yaml
server:
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        secure: true
        same-site: lax
~~~

`server.reactive.session.timeout` và `server.reactive.session.cookie.*` là các property của **WebFlux session** theo Spring Boot 3.5. Đừng đặt `server.servlet.session.*` rồi kỳ vọng Reactor Netty/WebFlux áp dụng.

**Lưu ý khi thử local bằng HTTP:** nếu bật `secure: true` trên môi trường `http://localhost:8080`, nhiều client sẽ không gửi lại cookie như trong production HTTPS. Vì vậy ví dụ runnable ở trên dùng cấu hình mặc định để tránh nhiễu do browser/cookie policy.

### 8.3. Timeout session và tuổi thọ cookie không giống nhau

| Cơ chế | Ai quyết định? | Ý nghĩa |
|---|---|---|
| Session timeout | Server/store | Sau thời gian không hoạt động, session không còn hợp lệ |
| Cookie Max-Age/Expires | Client/browser | Khi nào browser loại cookie |
| Cookie Secure | Client/browser | Khi nào gửi cookie qua kênh an toàn |
| Cookie HttpOnly | Client/browser | JavaScript có thể đọc cookie hay không |
| Cookie SameSite | Client/browser | Điều kiện gửi cookie trong ngữ cảnh cross-site |

Cookie còn nhưng session đã hết hạn ⇒ server nhận ID cũ nhưng không lấy được state. Ngược lại, cookie bị xóa sớm không nhất thiết khiến server xóa ngay session; state có thể chờ hết hạn/cleanup.

**Idle timeout không phải absolute max lifetime**: mỗi hoạt động hợp lệ có thể cập nhật thời gian truy cập tùy store; hệ thống cần thời gian đăng nhập tối đa tuyệt đối phải bổ sung chính sách riêng phù hợp.

## 9. Xoay ID, hủy phiên và logout an toàn

### Session fixation

Kịch bản: kẻ tấn công biết một session ID trước khi nạn nhân đăng nhập. Nếu ID không đổi sau login, kẻ tấn công có thể chiếm phiên. Khi user được xác thực, một biện pháp là **đổi session ID**:

~~~java
// Servlet MVC fragment: request đã có session hợp lệ.
request.changeSessionId();
~~~

~~~java
// WebFlux fragment: phải đưa Mono vào pipeline.
return session.changeSessionId().thenReturn("ready");
~~~

Khác với `invalidate()`, thay ID thường giữ mục đích sử dụng session tiếp tục nhưng gắn một ID mới. Trong ứng dụng Spring Security, sử dụng session fixation strategy của Security trước khi tự viết cơ chế riêng.

### Logout

Servlet: `HttpSession.invalidate()` đồng bộ. WebFlux: `WebSession.invalidate()` trả `Mono<Void>`, phải compose vào publisher. Nhưng hủy session **không đồng nghĩa** đã revoke mọi access token, refresh token hoặc phiên trên các thiết bị khác. Quy trình logout của ứng dụng có Security cần xóa security context, quản lý cookie và token theo hợp đồng bảo mật thực tế.

### CSRF / XSS

Session cookie tự được browser đính kèm khi điều kiện cookie cho phép, nên các endpoint thay đổi state cần chống **CSRF**. `SameSite` giảm rủi ro trong một số tình huống nhưng không thay hoàn toàn CSRF tokens/Origin checks. `HttpOnly` giảm nguy cơ đánh cắp ID qua JavaScript nhưng không vô hiệu hóa mọi tấn công XSS; script độc hại cùng origin vẫn có thể phát request mang cookie hợp lệ.

Không trả session ID từ API, không ghi ID vào URL hay ghi nguyên token vào log/tracing labels.

## 10. Session local và Spring Session khi triển khai nhiều instance

### 10.1. Nếu chỉ lưu trong memory local

Thông thường session state nằm trong một instance:

~~~text
Client --cookie--> instance A   session ID -> attributes nằm ở A
Client --cookie--> instance B   B không tìm được attributes ở A
~~~

Với Servlet, container quản lý session; với WebFlux mặc định, `DefaultWebSessionManager` sử dụng `InMemoryWebSessionStore`. Load balancing giữa hai replica mà không có shared session store có thể khiến user thấy state “mất ngẫu nhiên”. Sticky session chỉ giảm việc đổi replica; nó không xử lý được lỗi hoặc shutdown của instance đang giữ session.

### 10.2. Spring Session và store chia sẻ

Spring Session cung cấp lớp repository thay session store mặc định:
- Với MVC/Servlet: `SessionRepository`, thường dùng Redis hoặc JDBC.
- Với WebFlux: `ReactiveSessionRepository` tích hợp qua `WebSessionManager`; Redis reactive là lựa chọn phổ biến được Spring Boot hỗ trợ.
- Spring Boot starter Spring Session có thể auto-configure filter/manager cần thiết, không cần tự thêm `@EnableRedisHttpSession` hoặc `@EnableRedisWebSession` khi giữ auto-configuration.

Ví dụ fragment Gradle Spring Boot 3.5 (thêm vào dự án MVC **hoặc** WebFlux phù hợp):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-session-data-redis'
}
~~~

Ví dụ cấu hình kết nối ở môi trường phát triển:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 20m
~~~

`spring.session.timeout` dùng khi Spring Session được auto-configure; trên Servlet, nếu không đặt property này, Boot có thể fallback sang `server.servlet.session.timeout`. Với WebFlux và Spring Session Redis cần kiểm tra property timeout, repository và configuration thực tế của phiên bản đang dùng.

**Thêm dependency không đủ** để tuyên bố đã có shared session: Redis phải chạy, cấu hình kết nối phù hợp và ứng dụng thật sự đang sử dụng Spring Session manager/filter. Nên test hai replica với cùng session cookie, restart một replica, kiểm tra state và expiry.

### 10.3. Đừng lưu mọi thứ vào session

Lưu ID nhỏ hoặc state ngắn hạn; tránh:
- Danh sách dữ liệu lớn, file upload hoặc kết quả truy vấn có thể lấy lại từ DB.
- Database connection, stream, request/response, bean có state vòng đời.
- Object khó serialize khi chuyển sang Redis/JDBC hoặc thay version lớp Java.
- Dữ liệu cần lưu bền cho nghiệp vụ thanh toán/đơn hàng.

Session có thể bị invalidate, hết hạn, mất khi store lỗi hoặc bị eviction. Dùng database giao dịch cho nguồn dữ liệu nghiệp vụ cốt lõi.

## 11. Hai request đồng thời có thể cập nhật session sai

Ví dụ `visits=5` và hai request cùng chạy:
1. Request A đọc 5; request B cũng đọc 5.
2. Cả hai tính giá trị tiếp theo là 6.
3. A ghi 6; B ghi 6.
4. Session cuối có thể là **6** dù đã có hai lượt thăm.

Cả `HttpSession` và `WebSession` đều không biến tổ hợp đọc–tính–ghi thành transaction. Demo curl ở trên gửi **tuần tự**, nên body deterministic; không suy luận counter đó an toàn dưới tải đồng thời.

Nếu nghiệp vụ đòi tính chính xác, dùng storage hỗ trợ atomic increment, optimistic locking hoặc transaction phù hợp. Trong WebFlux, tránh “sửa” bằng cách gọi `block()` trên event-loop. Với Redis Session, việc lưu map attributes cũng không tự đồng nghĩa thao tác cộng biến là atomic.

## 12. @SessionAttribute, @SessionAttributes và SessionStatus

Ba API này có mục tiêu khác nhau:

| API | Mục đích |
|---|---|
| `HttpSession` / `WebSession` | Quản lý attributes và vòng đời session |
| `@SessionAttribute` | Lấy một session attribute đã có, thường do filter hoặc code khác đặt |
| `@SessionAttributes` | Giữ model attributes của **một workflow controller** qua nhiều request |
| `SessionStatus.setComplete()` | Kết thúc state do `@SessionAttributes` quản lý, **không phải logout toàn hệ thống** |

Ví dụ fragment dùng cho MVC hoặc WebFlux controller phù hợp:

~~~java
// Đoạn minh họa riêng; UserDraft và imports phải có trong dự án.
@Controller
@SessionAttributes("draft")
class DraftController {

    @ModelAttribute("draft")
    UserDraft draft() {
        return new UserDraft();
    }

    @PostMapping("/draft/finish")
    String finish(SessionStatus status) {
        status.setComplete();
        return "redirect:/done";
    }
}
~~~

`@SessionAttributes` là annotation cấp controller class để lưu model attribute qua workflow. Đừng nhầm với `@SessionAttribute` số ít chỉ lấy attribute có sẵn. Nếu cần thay đổi trực tiếp session-wide state, chọn `HttpSession` hoặc `WebSession` đúng stack.

## 13. Checklist bảo mật và vận hành

- [ ] Xác định MVC/Servlet hay WebFlux trước khi chọn session API và property.
- [ ] Tránh tạo session khi không cần; MVC read-only dùng `getSession(false)`.
- [ ] WebFlux chỉ bắt đầu session khi cần lưu state; dùng đúng `start()`/attribute mutation.
- [ ] WebFlux `changeSessionId()`, `invalidate()` phải nằm trong publisher chain.
- [ ] Không log, hiển thị hoặc gắn session ID vào metric labels.
- [ ] Cấu hình Secure/HttpOnly/SameSite/Domain/Path phù hợp với HTTPS, proxy và browser.
- [ ] Session fixation được xử lý khi login; logout hủy cả session/security context cần thiết.
- [ ] Có CSRF protection khi dùng auth dựa trên cookie.
- [ ] Timeout và cookie Max-Age được hiểu là hai cơ chế khác nhau.
- [ ] Nếu nhiều replica, session store dùng chung hoặc kiến trúc stateless được thiết kế có chủ đích.
- [ ] Session attributes nhỏ, có khả năng serialize khi dùng shared store, không phải source of truth nghiệp vụ.
- [ ] Đã đo idle expiry, cookie bị từ chối, store latency, race condition dưới concurrent requests.

## 14. Bảng xử lý lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách giải quyết |
|---|---|---|
| curl POST hai lần vẫn `visits=1` | Không gửi lại cookie | Dùng `curl -c` và `curl -b` |
| GET read-only MVC lại tạo cookie mới | Code dùng `getSession()` hoặc filter/Security tạo session | Đổi sang `getSession(false)` khi thích hợp; kiểm tra toàn request pipeline |
| Inject WebSession nhưng không có cookie | Session mới chưa có attribute/chưa `start()` | Bình thường; chỉ tạo khi cần lưu state |
| Cookie có nhưng không lấy được attributes | Session hết hạn, ID invalid, sai store hoặc sai cookie policy | Kiểm tra Cookie header, timeout, Domain/Path, store |
| Chạy 2 replica lúc giữ lúc mất session | Lưu state local | Dùng Spring Session shared store hoặc đổi kiến trúc |
| Logout nhưng vẫn đăng nhập | Chỉ xóa một attribute, còn Security context/token | Dùng logout flow của Security, revoke token phù hợp |
| Cookie không gửi trên HTTP local | `Secure=true` hoặc policy client | Dùng HTTPS hoặc cấu hình dev riêng |
| Cross-origin frontend mất session | CORS/credentials/SameSite/Secure/Domain | Xem Request/Response cookies và cấu hình CORS đúng origin |
| WebFlux logout không hủy | Mono từ `invalidate()` bị bỏ qua | Return/compose publisher |
| ClassNotFound `javax.servlet` | Sai Java package so với Spring Boot 3+/4+ | Sử dụng `jakarta.servlet.http.HttpSession` |
| Lỗi session Redis sau deploy | Serialization/schema/connection | Kiểm tra Redis, serializer, namespace, migration |
| Session counter dưới concurrent requests bị mất update | Read-modify-write không atomic | Cập nhật qua storage có cơ chế atomic/transaction |

Để điều tra, theo trình tự: **Cookie/Set-Cookie → API session → timeout và store → Security → concurrency**. HTTP 200 một lần không chứng minh request tiếp theo tìm lại được session.

## 15. Câu hỏi ôn tập

**1.** MVC cần kiểm tra session có tồn tại nhưng không tạo mới. Dùng lệnh gì?

**Đáp án:** `request.getSession(false)`. Nó trả `null` nếu chưa có session hợp lệ.

**2.** WebFlux controller nhận `WebSession` rồi chỉ đọc thuộc tính. Có mặc nhiên gửi cookie mới không?

**Đáp án:** Không. Khi không có session cũ, WebSession chưa start nếu chỉ đọc. Thêm attribute hoặc `start()` mới bắt đầu session.

**3.** `HttpSession.invalidate()` khác `WebSession.invalidate()` ở đâu?

**Đáp án:** Servlet method trả `void`, WebFlux method trả `Mono<Void>`. Mono phải được subscribe qua reactive flow.

**4.** Cookie `JSESSIONID` có nghĩa người dùng đã đăng nhập không?

**Đáp án:** Không. Nó mang ID phiên; quyền và auth state cần được xác minh độc lập.

**5.** Hai request cùng tăng session counter có chắc tăng hai đơn vị không?

**Đáp án:** Không, read–modify–write không tự atomic; có thể lost update.

**6.** WebFlux mặc định nên dùng `server.servlet.session.timeout` hay `server.reactive.session.timeout`?

**Đáp án:** Với WebFlux default session, dùng `server.reactive.session.timeout`. Khi Spring Session được dùng, kiểm tra `spring.session.timeout` và repository config.

**7.** Xóa state bằng `SessionStatus.setComplete()` có làm mọi session người dùng hết hạn?

**Đáp án:** Không. Nó dọn state của workflow `@SessionAttributes`; không thay thế invalidate/logout.

**8.** Có 3 replica dùng local sessions, người dùng thỉnh thoảng bị mất giỏ hàng. Vì sao?

**Đáp án:** Request được phân phối sang replica không chứa dữ liệu session tương ứng. Cần shared session store hoặc thiết kế lại state.

### Thực hành tự kiểm tra

Thử `curl -i` với endpoint `GET /visit` chưa gửi cookie, sau đó POST rồi GET gửi cookie jar. Kiểm tra những gì có trong `Set-Cookie` (và không ghi ID ra log). Tắt app, đổi session timeout ở từng stack xuống `1m` trong test profile, thử lại sau thời gian không hoạt động; giải thích khác nhau giữa cookie tồn tại và session đã hết hạn.

## 16. Tài liệu tham khảo chính thức

- [Jakarta Servlet — HttpSession](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html)
- [Jakarta Servlet — HttpServletRequest](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html)
- [Spring Framework 6.2 — WebSession](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — MVC @SessionAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html)
- [Spring Framework — WebFlux @SessionAttribute](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattribute.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

**Ghi nhớ:** cả `HttpSession` và `WebSession` giữ session attributes **phía server** và thường dùng cookie mang ID. Sự khác nhau thuộc Servlet versus WebFlux, thời điểm bắt đầu session và cách thực thi thao tác vòng đời. Khi triển khai, hãy luôn kiểm tra timeout, cookie flags, session fixation, logout, store đa instance và concurrency.
