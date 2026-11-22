# HttpSession: tạo, hủy phiên và giới hạn khi triển khai nhiều máy chủ

## 1. Tại sao một ứng dụng web cần session?

HTTP về bản chất xử lý những request riêng biệt: một request không tự chứa bộ nhớ của request trước. Tuy vậy, ứng dụng đôi khi cần duy trì **trạng thái ngắn hạn của một trình duyệt** qua nhiều lần gọi, ví dụ giỏ hàng, các bước điền biểu mẫu, tùy chọn giao diện hoặc thông tin liên quan phiên đăng nhập. Trong Java Servlet stack, `jakarta.servlet.http.HttpSession` là API để liên kết dữ liệu phía server với một session identifier được client mang theo.

Ví dụ trình tự:

~~~text
Client                         Load balancer               Server
  | GET /catalog                    |                          |
  |-------------------------------->|------------------------->|
  |<------------------------------- HTTP 200, chưa cần session-|
  |
  | POST /api/demo-session/start     |                          |
  |-------------------------------->|------------------------->| getSession(true)
  |                                  |                          | setAttribute(...)
  |<------------------------------- Set-Cookie: JSESSIONID=... |
  |
  | GET /api/demo-session + Cookie   |                          |
  |-------------------------------->|------------------------->| getSession(false)
  |<------------------------------- dữ liệu đã lưu ------------|
  |
  | DELETE /api/demo-session         |                          |
  |-------------------------------->|------------------------->| invalidate()
  |<------------------------------- HTTP 204 ------------------|
~~~

Tên `JSESSIONID` trong sơ đồ là cookie session phổ biến của Servlet container. Nếu sử dụng Spring Session, tên mặc định có thể là `SESSION`; tên cuối cùng có thể được tùy biến. **Cookie thông thường mang ID để tra cứu; session attributes được giữ ở server/store, không tự được nhúng vào cookie.** Đừng nhầm HttpSession với JWT tự chứa claims hoặc cookie lưu toàn bộ dữ liệu.

Bài học giúp bạn:
- Hiểu lifecycle session: chưa tồn tại, tạo, đọc/ghi attributes, timeout, invalidate và tạo phiên mới.
- Phân biệt `getSession()` / `getSession(true)` với `getSession(false)`, và cách tránh tạo phiên ngoài ý muốn.
- Hiểu session ID/cookie, inactivity timeout, logout, session fixation và các chính sách bảo mật.
- Thực hành Java 17+ Spring Boot MVC có controller/test và hai request dùng chung một session.
- Đánh giá việc dùng session cục bộ khi load balancing nhiều node, sticky sessions và shared session store qua Spring Session + Redis.
- Phân biệt session store dùng chung với cơ sở dữ liệu nghiệp vụ, độ bền/nhất quán và các giới hạn khi scale.

**Phạm vi phiên bản:** ví dụ Servlet stack `jakarta.servlet`, Java 17+ và Spring Boot 3.3.x / Spring Framework 6.1.x. Ý nghĩa Servlet API vẫn áp dụng trong các phiên bản hiện đại. Khi dùng Spring Security hoặc Spring Session cần đối chiếu dependency/configuration của phiên bản đang chạy.

## 2. HttpSession là gì và không phải là gì?

`HttpSession` đại diện một phiên logic giữa ứng dụng web với một client trong khoảng thời gian hữu hạn. Server/container tạo session ID, lưu các attribute theo khóa String và có thể sử dụng cookie hoặc URL rewriting để kết nối request tiếp theo với cùng session.

| Thành phần | Lưu ở đâu? | Chức năng |
| --- | --- | --- |
| `HttpSession` và attributes | Servlet container hoặc kho session thay thế | Trạng thái gắn với phiên |
| Session ID | Được server phát sinh, trình duyệt thường gửi qua cookie | Khóa tra cứu phiên |
| `JSESSIONID` | Cookie thường gặp ở container Servlet | Chuyển ID của container session |
| `SESSION` | Cookie thường gặp khi Spring Session sử dụng default cookie resolver | Chuyển ID của Spring Session |
| `HttpServletRequest` | Một request cụ thể | Cho phép tra cứu/tạo phiên và thông tin cookie |
| `SecurityContext` | Ngữ cảnh xác thực do Spring Security quản lý | Không tương đương toàn bộ session, cách lưu tùy authentication/security configuration |

**Session không phải cơ chế xác thực tự động.** Chỉ gọi `getSession()` không làm user được đăng nhập hoặc phân quyền. Một session có thể là anonymous, và các attribute bất kỳ bạn đặt vào session không thay thế quy trình authentication, CSRF protection hay authorization.

Một browser cũng có thể chứa nhiều cookie. Server chọn đúng cookie theo domain, path, secure flags và cấu hình. Không gửi session ID vào URL hay query string trong API bình thường; URL thường đi vào log, lịch sử browser và referrer, nên tăng nguy cơ lộ định danh phiên.

### 2.1. Lifecycle tổng quát

~~~text
                   HTTP request không có session hợp lệ
                                  |
                         getSession(false)?
                          /             \
                       null         getSession(true)
                                       |
                                       v
                            NEW session + generated ID
                                       |
                               setAttribute(...)
                                       |
                                       v
                            ACTIVE, client gửi cookie
                                 /              \
                       Không hoạt động         invalidate()
                       quá timeout                 |
                            |                      v
                            v                    INVALID
                          EXPIRED                không dùng lại
                              \                    /
                               \                  /
                            Request tiếp theo:
                       không tìm được phiên cũ
                    tạo phiên mới chỉ khi có yêu cầu
~~~

Timeout thường dựa trên **khoảng không hoạt động (inactivity)** giữa các truy cập từ client, không phải một thời hạn tuyệt đối tính từ thời điểm login. Server có thể có cleanup bất đồng bộ, vì thế “hết hạn đúng một giây cố định” không phải cam kết để dựa vào giao diện. Với các session store phân tán, thời điểm key bị xóa và thời điểm lần đọc tiếp theo phát hiện expired có thể khác nhau.

## 3. Các phương thức Servlet quan trọng

| Method | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `request.getSession()` | Trả session hiện tại, hoặc **tạo mới** nếu chưa có | Có thể phát sinh state/cookie ngoài ý muốn |
| `request.getSession(true)` | Tương đương hành vi tạo khi thiếu | Dùng khi thật sự muốn bắt đầu session |
| `request.getSession(false)` | Trả session hiện tại nếu tồn tại/hợp lệ, **không tự tạo** | Dùng ở endpoint chỉ đọc hoặc logout |
| `session.setAttribute(key,value)` | Lưu hoặc thay một attribute | Dữ liệu cần nhỏ, ổn định, phù hợp serializer |
| `session.getAttribute(key)` | Đọc attribute hoặc null | Cast/kiểm kiểu và khả năng thiếu |
| `session.removeAttribute(key)` | Xóa riêng một attribute | Không hủy toàn bộ session |
| `session.invalidate()` | Hủy session và unbind attributes | Không sử dụng object session đó sau invalidate |
| `session.getId()` | Đọc session ID | Tránh log/trả client như data thông thường |
| `session.getCreationTime()` | Thời điểm tạo | Không phải authentication timestamp |
| `session.getLastAccessedTime()` | Thời điểm truy cập liên quan request | Không phải thời điểm gọi setAttribute gần nhất |
| `session.setMaxInactiveInterval(seconds)` | Thay timeout không hoạt động cho phiên này | Giá trị `<= 0` thường có nghĩa không timeout; tránh trong production |
| `session.getMaxInactiveInterval()` | Đọc timeout hiện có | Đơn vị là **giây**, khác duration trong application config |
| `request.changeSessionId()` | Đổi ID của session hiện tại, giữ các attributes | Dùng đúng điểm xác thực thành công khi cần chống fixation |
| `request.isRequestedSessionIdValid()` | Kiểm ID từ request có nhận diện session hợp lệ không | Không đồng nghĩa user đã authenticated |

`request.getSession(false)` rất quan trọng. Một endpoint trạng thái “chưa có giỏ hàng/phiên” không nên tự tạo session chỉ vì controller khai báo `HttpSession` rồi gọi một API khác. Khi tiêm trực tiếp `HttpSession` vào tham số handler, Spring MVC/Servlet thường có thể tạo phiên nếu chưa có; muốn tuyệt đối tránh, nhận `HttpServletRequest` và gọi `getSession(false)` rõ ràng.

Sau `invalidate()`, nhiều thao tác trên object `HttpSession` cũ sẽ ném `IllegalStateException`. Không giữ tham chiếu session trong singleton service hoặc thread background; lấy phiên theo context của request khi cần.

### 3.1. Khác nhau giữa attribute và hủy phiên

~~~java
HttpSession session = request.getSession(true);
session.setAttribute("theme", "dark");
session.setAttribute("cartId", 42L);

// Xóa một khóa, session vẫn có thể tồn tại:
session.removeAttribute("theme");

// Hủy mọi attribute/phiên:
session.invalidate();
~~~

Đây là **fragment** cần đặt trong method có biến `HttpServletRequest request`. Không dùng `removeAttribute("user")` làm logout mặc định khi Spring Security còn lưu trạng thái xác thực ở nơi khác; đăng xuất cần dùng security/logout flow đã cấu hình.

### 3.2. Không dùng HttpSession làm bộ nhớ toàn cục

Một `@Service` singleton có thể phục vụ nhiều user; biến instance mutable của service là dữ liệu chia sẻ không đúng với session scope. `HttpSession` là trạng thái của một client, nhưng **cũng không tự đảm bảo thread safety**: hai request đồng thời từ cùng browser có thể đọc/ghi cùng session attributes.

Ví dụ sai:

~~~java
// MINH HỌA SAI: service singleton không lưu cart riêng từng client.
@Service
class WrongCartService {
    private final List<String> items = new ArrayList<>();
    public void add(String item) { items.add(item); }
}
~~~

Fragment trên thiếu imports và không dành để copy chạy riêng. Nó minh họa vấn đề dữ liệu toàn cục, **không phải ví dụ chính của bài**.

Ngay cả khi thay `items` bằng `session.getAttribute("cart")` rồi thêm phần tử vào một `ArrayList` mutable, vẫn có race condition và rủi ro trong distributed session store. Với giỏ hàng thật, cân nhắc lưu trong database theo user/cart ID hoặc cập nhật transactional/atomic ở backend.

## 4. Session ID, cookie và các thuộc tính bảo mật

HTTP response lần đầu tạo session thường có `Set-Cookie`, các request kế tiếp có `Cookie` tương ứng. Browser tự lưu và gửi cookie khi domain/path/security conditions phù hợp.

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Đây là **ví dụ về một cookie đã cấu hình bảo mật trên HTTPS**, không phải header mặc định trong mọi môi trường. `<opaque-id>` phải được server tạo ngẫu nhiên, không lấy từ username hoặc timestamp dễ đoán.

- **`HttpOnly`:** JavaScript trong browser không trực tiếp đọc cookie, giảm một số đường đánh cắp qua script; không thay thế phòng chống XSS.
- **`Secure`:** cookie chỉ được gửi qua HTTPS; nếu bật `Secure` khi thử `http://localhost` bằng trình duyệt/curl, tùy client có thể không gửi lại cookie.
- **`SameSite=Lax/Strict/None`:** giúp hạn chế một số ngữ cảnh cross-site; `SameSite=None` yêu cầu `Secure` ở browser hiện đại. Không coi SameSite là thay thế CSRF protection hoàn chỉnh.
- **`Path`, `Domain`:** xác định nơi cookie được gửi; cấu hình sai có thể làm cookie không quay lại endpoint khác.
- **`Max-Age` / `Expires` của cookie:** mô tả thời gian lưu cookie phía client; **khác** `HttpSession` server-side inactivity timeout. Cookie còn tồn tại không đảm bảo session ở server còn hợp lệ.

Không trả session ID trong body debug hoặc access logs. Reverse proxy phải truyền HTTPS/forwarded headers đúng và được tin cậy có kiểm soát, nhất là khi quyết định cookie Secure, URL/redirect và origin validation.

### 4.1. Session fixation: đổi ID sau xác thực

Nếu attacker kiểm soát hoặc biết một ID phiên trước login, rồi nạn nhân login mà hệ thống tiếp tục dùng ID đó, attacker có thể lợi dụng (*session fixation*). Với Servlet 3.1+ có `request.changeSessionId()` để tạo ID mới cho **session hiện tại** mà vẫn giữ attributes cần thiết.

~~~java
// MINH HỌA trong authentication flow riêng do ứng dụng tự sở hữu:
HttpSession existing = request.getSession(false);
if (existing != null && authenticationSucceeded) {
    request.changeSessionId();
}
~~~

Fragment không độc lập: `authenticationSucceeded` là kết quả đã được auth service xác minh, không do client cung cấp. Nếu ứng dụng dùng **Spring Security**, tránh tự xoay ID hoặc tự xóa security context một cách tùy ý: Spring Security thường áp dụng session fixation protection khi login. Với Servlet hiện đại, chiến lược mặc định thường là `changeSessionId`; có `newSession`/`migrateSession` khi có yêu cầu cụ thể. Kiểm tra policy thực tế bằng integration test.

Đổi ID không tự tước quyền trên tất cả những credential khác; logout và thu hồi token, remember-me, refresh token, SSO có logic riêng. Nên dựa vào Spring Security `SecurityFilterChain` và configured logout handlers để làm việc đó.

## 5. Timeout và hủy phiên: điều cần phân biệt

### 5.1. Timeout bất hoạt

`session.setMaxInactiveInterval(1800)` có nghĩa giới hạn không hoạt động khoảng **1800 giây (30 phút)**. Mỗi request liên kết với session được container/store quan sát có thể cập nhật mốc truy cập theo định nghĩa tương ứng. `getLastAccessedTime()` không đơn giản bằng thời điểm gần nhất một lập trình viên gọi `setAttribute()`.

Trong Spring Boot Servlet app có thể dùng:

~~~properties
server.servlet.session.timeout=30m
~~~

Nếu có Spring Session, tham số `spring.session.timeout=30m` có thể kiểm soát timeout của repository; khi không được thiết lập, auto-configuration Servlet của Spring Boot lấy từ `server.servlet.session.timeout`. Đừng đặt cả hai rồi giả định precedence dựa trên tên; xem dependency-managed version và xác minh giá trị runtime qua `getMaxInactiveInterval()`.

**Không dùng negative timeout như một cách “giữ user đăng nhập vĩnh viễn”.** Nó làm tăng rủi ro session bị đánh cắp hoặc dữ liệu bị giữ không giới hạn. Nếu sản phẩm cần “remember me”, hãy dùng cơ chế xác thực thích hợp (token/cookie lifecycle, rotation, revocation), không phải session vô hạn.

### 5.2. Logout và session invalidation

~~~java
HttpSession existing = request.getSession(false);
if (existing != null) {
    existing.invalidate();
}
~~~

Dùng `getSession(false)` tránh tạo phiên mới chỉ để hủy. Request tiếp theo mang cookie cũ sẽ không tìm được phiên cũ nếu việc invalidate được lưu hiệu quả trong kho phiên. Tuy nhiên, với **các request đã bắt đầu chạy song song**, invalidation không bảo đảm thu hồi ngay mọi hành động đang thực hiện; cần kiểm tra authorization ở ranh giới nghiệp vụ và chọn semantics phù hợp.

Trong ứng dụng có Spring Security, hãy dùng logout endpoint/handler do Spring Security quản lý: nó có thể xóa security context, invalidate HttpSession và dọn cookie tùy cấu hình. Demo bên dưới không có Spring Security nên chỉ thể hiện thao tác Servlet, **không được xem là triển khai login/logout an toàn**.

### 5.3. Session events và dọn dẹp

Servlet có `HttpSessionListener`, `HttpSessionAttributeListener` và `HttpSessionIdListener`, dùng khi cần quan sát tạo/hủy session hoặc đổi ID. Nếu dùng Spring Session Redis, event `SessionCreatedEvent`/`SessionDeletedEvent`/`SessionExpiredEvent` phụ thuộc repository/configuration và Redis keyspace notifications; **không hứa callback expiry đúng thời điểm từng giây hoặc chạy chắc chắn trong mọi failover**.

Không gắn logic nghiệp vụ quan trọng như hoàn tiền, hủy đơn hàng hay khóa vé **chỉ** vào session-expired event. Những công việc đó cần transaction, job/reconciliation và nguồn dữ liệu bền vững độc lập với vòng đời phiên.

## 6. Ví dụ chạy được: tạo, đọc và hủy phiên qua Spring MVC

Ví dụ sử dụng **Java 17, Spring Boot 3.3.5** và `spring-boot-starter-web`. Không có Spring Security và không dùng database để tập trung vào `HttpSession`. Giá trị `nickname` chỉ là chuỗi demo, **không được tin như danh tính đã xác thực**.

Cấu trúc:

~~~text
session-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/sessiondemo/
    │   ├── SessionDemoApplication.java
    │   └── web/DemoSessionController.java
    └── test/java/com/example/sessiondemo/web/
        └── DemoSessionControllerTest.java
~~~

### 6.1. Gradle project

`settings.gradle`:

~~~groovy
rootProject.name = 'session-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Có thể thêm `src/main/resources/application.properties`:

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Trong **production HTTPS**, đặt thêm `server.servlet.session.cookie.secure=true`. Không bật cứng Secure trong demo HTTP thuần nếu client thử nghiệm cần gửi lại cookie. Spring Boot có cơ chế liên quan forwarded headers, session cookie customizer và session store; kiểm thử cookie thực tế thay vì dựa vào config ở code review.

`src/main/java/com/example/sessiondemo/SessionDemoApplication.java`:

~~~java
package com.example.sessiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
~~~

### 6.2. Controller: chủ động tạo session, chỉ đọc khi có, hủy phiên

`src/main/java/com/example/sessiondemo/web/DemoSessionController.java`:

~~~java
package com.example.sessiondemo.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo-session")
public class DemoSessionController {

    public record StartRequest(String nickname) {}
    public record DemoState(String nickname, int timeoutSeconds) {}

    @PostMapping(path = "/start", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<DemoState> start(
            @RequestBody StartRequest input,
            HttpServletRequest request) {

        if (input.nickname() == null || input.nickname().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        HttpSession session = request.getSession(true);
        String nickname = input.nickname().trim();
        session.setAttribute("nickname", nickname);

        return ResponseEntity.ok(
                new DemoState(nickname, session.getMaxInactiveInterval()));
    }

    @GetMapping
    public ResponseEntity<DemoState> read(HttpServletRequest request) {
        // Không tự tạo session cho người chỉ xem trạng thái.
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.noContent().build();
        }

        Object value = session.getAttribute("nickname");
        if (!(value instanceof String nickname)) {
            return ResponseEntity.noContent().build();
        }

        return ResponseEntity.ok(
                new DemoState(nickname, session.getMaxInactiveInterval()));
    }

    @DeleteMapping
    public ResponseEntity<Void> end(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

**Phân tích:**
1. `POST /start` kiểm tra nickname, sau đó `getSession(true)` tạo phiên nếu chưa có; nếu đã có, nó **sử dụng lại phiên hiện tại**. Dữ liệu lưu là chuỗi nhỏ, tránh serialization phức tạp khi sau này chuyển sang kho dùng chung.
2. `GET /api/demo-session` gọi `getSession(false)`, trả `204 No Content` khi chưa có session hoặc chưa có nickname, không vô tình tạo session mới. Đây là **chính sách của demo**, không phải status bắt buộc Servlet.
3. `DELETE /api/demo-session` invalidates session nếu có và luôn trả 204. Với cookie cũ, GET sau logout sẽ không thể đọc attribute của phiên đã hủy.
4. Không trả `session.getId()` trong JSON; ID phải được giữ kín như credential phiên.
5. `timeoutSeconds` đọc từ `getMaxInactiveInterval()` (đơn vị giây), không nhất thiết bằng “số giây còn lại”.
6. Demo không có auth; ai kiểm soát cookie có thể truy cập nickname của session demo. Không dùng endpoint này để cấp quyền truy cập tài nguyên thật.

Nếu controller nhận `HttpSession` trực tiếp thay vì `HttpServletRequest` ở `read`, framework có thể tạo session trên GET. Thiết kế ở đây chủ ý không làm thế.

### 6.3. Chạy và quan sát cookie với curl

Tại project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `.\gradlew.bat bootRun`. Dùng `curl.exe` trong PowerShell khi muốn giữ nguyên cách truyền option của curl.

Đầu tiên, GET chưa có session:

~~~bash
curl -i 'http://localhost:8080/api/demo-session'
~~~

Kết quả mong đợi **204 No Content**, thường không có cookie session mới do controller này tạo. Các filter bên ngoài (nếu thêm sau này) có thể tạo session riêng, nên đừng tuyên bố cả ứng dụng không bao giờ sinh cookie.

Bắt đầu session, lưu cookie vào jar:

~~~bash
curl -i -c cookies.txt -X POST \
  'http://localhost:8080/api/demo-session/start' \
  -H 'Content-Type: application/json' \
  -d '{"nickname":"Lan"}'
~~~

Dự kiến **200 OK**, JSON có nickname `Lan` và timeoutSeconds gần giá trị config (ví dụ 1800). Header `Set-Cookie` thường có tên `JSESSIONID` khi dùng container session. Cookie jar chỉ phục vụ kiểm thử; **không commit/công khai file cookie**.

Đọc lại bằng chính cookie:

~~~bash
curl -i -b cookies.txt 'http://localhost:8080/api/demo-session'
~~~

Dự kiến **200 OK** và `nickname="Lan"`. Không gửi cookie:

~~~bash
curl -i 'http://localhost:8080/api/demo-session'
~~~

Dự kiến **204 No Content** vì request không liên kết session cũ. Đây là bằng chứng trạng thái được nối bởi session ID, không bởi địa chỉ IP.

Hủy:

~~~bash
curl -i -b cookies.txt -X DELETE \
  'http://localhost:8080/api/demo-session'
curl -i -b cookies.txt 'http://localhost:8080/api/demo-session'
~~~

Request DELETE dự kiến **204**; GET với cookie cũ dự kiến **204**. Container có thể gửi cookie expired hoặc không tùy cấu hình, nhưng server đã invalidated session. Sau khi hủy, gửi POST /start với cookie cũ có thể tạo **một phiên mới** và ID mới; không hồi sinh phiên cũ.

### 6.4. Kiểm thử MockMvc vòng đời session

`src/test/java/com/example/sessiondemo/web/DemoSessionControllerTest.java`:

~~~java
package com.example.sessiondemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoSessionControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithoutSessionDoesNotCreateOne() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo-session"))
                .andExpect(status().isNoContent())
                .andReturn();
        assertEquals(null, result.getRequest().getSession(false));
    }

    @Test
    void sameSessionKeepsAttributeUntilInvalidation() throws Exception {
        MvcResult created = mvc.perform(post("/api/demo-session/start")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"nickname\":\"Lan\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("Lan"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) created.getRequest().getSession(false);
        assertNotNull(session);
        assertEquals("Lan", session.getAttribute("nickname"));

        mvc.perform(get("/api/demo-session").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("Lan"));

        mvc.perform(delete("/api/demo-session").session(session))
                .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());

        // Request mới không cung cấp session vừa hủy:
        mvc.perform(get("/api/demo-session"))
                .andExpect(status().isNoContent());
    }

    @Test
    void blankNicknameIsRejectedWithoutSessionCreation() throws Exception {
        MvcResult result = mvc.perform(post("/api/demo-session/start")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"nickname\":\"  \"}"))
                .andExpect(status().isBadRequest())
                .andReturn();
        assertEquals(null, result.getRequest().getSession(false));
    }
}
~~~

Chạy `./gradlew test`. Kiểm thử trên xác nhận `getSession(false)`, attribute và `invalidate()` ở MockMvc **trong một ứng dụng**. Nó không chứng minh Redis TTL, cookie qua browser thực, cân bằng tải hai node, concurrent session writes hoặc xử lý khi Redis down; các bài kiểm thử đó cần server/container, Redis và load balancer thực tế.

Gợi ý bổ sung kiểm thử cho sản phẩm: thời gian timeout nhỏ và client cookie thật; session bị invalidate khi logout; cookie `HttpOnly/Secure/SameSite`; kiểm thử xác thực/CSRF của Spring Security; gửi hai request đồng thời; kiểm thử qua hai node với session store chung.

## 7. Multi-server: tại sao session mặc định của một node gây sự cố?

Giả sử load balancer chuyển request tới hai ứng dụng độc lập cùng chạy một phiên bản:

~~~text
                  ┌───────────────┐
Browser ──LB─────┤ App node A    │  Local session memory A
                  └───────────────┘
                  ┌───────────────┐
             └────┤ App node B    │  Local session memory B
                  └───────────────┘
~~~

Nếu lần đầu POST /start vào node A, container A tạo session ID và lưu nickname ở bộ nhớ A. Request tiếp theo tới B mang cùng cookie, nhưng B **không có entry session cục bộ** đó. `getSession(false)` trên B có thể trả null; client thấy trạng thái “mất” hoặc phải đăng nhập lại. Khi rolling deployment hay node restart, memory-local sessions cũng có thể biến mất.

Vấn đề này không được giải quyết chỉ bằng cách:
- Deploy cùng một file JAR lên hai node.
- Dùng cùng database nghiệp vụ nhưng vẫn giữ session in-memory.
- Bật HTTPS hoặc cookie chung domain.
- Đưa session ID trong header.
- Giữ một object user static hoặc singleton ở mỗi JVM.

Cần một cơ chế định tuyến hoặc **shared session persistence** phù hợp.

### 7.1. Sticky sessions ở load balancer

LB có thể giữ một browser tiếp tục vào node A (*session affinity/sticky routing*). Đây là cách giảm việc “nhảy node” khi sessions vẫn ở memory từng JVM.

Ưu điểm: đơn giản, ít round trip đến kho session; phù hợp một số hệ thống nhỏ, ngắn hạn.

Hạn chế:
- Nếu A chết/được thay trong deployment, dữ liệu in-memory có thể mất.
- Phân phối tải không đều khi có nhiều session nặng.
- Có thể cần cấu hình cookie affinity riêng của LB; cookie đó khác cookie ứng dụng.
- Mở rộng/giảm node và drain connections cần chiến lược.
- Sticky routing **không tự tạo failover session**; cần container replication hoặc shared store nếu muốn phiên sống sót khi node mất.

Không kết luận sticky luôn sai: nó là lựa chọn có trade-off, nhưng phải kiểm failure và công bố tác động user khi node hỏng.

### 7.2. Chia sẻ HttpSession qua Spring Session

Spring Session thay thế cơ chế lưu session phía container bằng một `SessionRepository`, thường thông qua `springSessionRepositoryFilter` bọc `HttpServletRequest/HttpSession`. Redis, JDBC hoặc store được hỗ trợ sẽ giữ attributes và metadata session dùng chung giữa node.

~~~text
 Browser (cookie SESSION hoặc cấu hình tương đương)
                   |
            Load balancer
             /          \
            v            v
      App node A      App node B
      Spring Session  Spring Session
            \          /
             \        /
           Shared Redis
       session attributes + TTL
~~~

Nhờ dùng chung Redis, request mang ID hợp lệ có thể đọc cùng session ở A hoặc B, miễn hai node dùng cấu hình namespace, serializer, timeout và session cookie tương thích. Spring Session **không làm toàn ứng dụng stateless**; nó chuyển trạng thái session từ mỗi JVM sang kho dùng chung.

Giới hạn:
- Redis/network có thể chậm hoặc down: read/write session thất bại và ảnh hưởng availability.
- Serialization của session attributes phải tương thích giữa các version deploy.
- Cùng session được cập nhật đồng thời từ nhiều node có thể có lost updates; không mặc nhiên có transaction/locking cho mọi attribute.
- Session cache/flush mode, TTL và thư viện khác nhau ảnh hưởng thời điểm thay đổi được lưu.
- Redis replication/failover có trade-off về durability; một lần ACK không đồng nghĩa mọi bản sao ở mọi vùng đã nhận được dữ liệu.
- Shared session store không tự chia sẻ dữ liệu của singleton/local caches, WebSocket state, file tạm hoặc transaction đang chạy.

### 7.3. Cấu hình Spring Boot 3.3 và Spring Session Redis

Giữ source Java Controller ở mục 6. Trong **ứng dụng Boot 3.3.x**, thêm các dependency do Spring Boot quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là đoạn **thay thế block dependencies** trong `build.gradle` ở mục 6, không phải thêm một block `dependencies` thứ hai vô điều kiện. Với Boot 3.3, `spring-session-data-redis` cộng Redis connector là lựa chọn đúng theo Spring Session 3.x/Boot 3.3 docs. Tài liệu latest Spring Session 4.x có thể chỉ tới starter `spring-boot-starter-session-data-redis` của thế hệ Boot mới hơn; không copy tên starter latest vào Boot 3.3 khi chưa kiểm phiên bản.

Ví dụ cấu hình Redis ở môi trường **phát triển**:

~~~properties
server.servlet.session.timeout=30m
spring.session.timeout=30m
spring.session.redis.namespace=demo:session
spring.session.redis.flush-mode=on_save
spring.data.redis.host=localhost
spring.data.redis.port=6379
~~~

Với production:
- Thay Redis host/port qua environment/secrets/managed Redis, bảo vệ kết nối TLS, network policy, credentials, failover.
- Các node ứng dụng chia sẻ **một session repository phù hợp** và serializer/schema tương thích.
- Tách Redis namespace theo môi trường/ứng dụng; không chia sẻ namespace giữa staging và production.
- Định cấu hình request timeout, connection pool, monitoring, max memory và eviction phù hợp. Nếu Redis xóa key do eviction/TTL, phiên biến mất.
- Cookie name/path/domain và secure flags phải nhất quán qua node và reverse proxy.
- Đo độ trễ đọc/ghi phiên; tránh ghi object đồ sộ hoặc thay đổi liên tục.

Spring Boot auto-configuration có thể tự tạo repository filter khi có đúng dependency. Không cần vừa kích hoạt auto-configuration vừa gắn thêm `@EnableRedisHttpSession` trừ khi có chủ đích override; nếu tự cấu hình, hiểu rõ điều gì được auto-config back off. Sau khi bật, cookie mặc định có thể là `SESSION` thay cho `JSESSIONID`.

**Về serialization:** Redis session repositories cần serialize thuộc tính, nhiều cấu hình mặc định dùng JDK serialization; nếu lưu custom object, có thể cần `Serializable` và version/class compatibility. Dùng immutable primitives/String/ID đơn giản giúp giảm rủi ro; nếu đổi sang JSON serializer, cần quy tắc type metadata và chống deserialization gadget. Không bao giờ coi bất kỳ serialized Java object từ store là dữ liệu hoàn toàn vô hại chỉ vì đến từ Redis.

### 7.4. Thực nghiệm hai node, một Redis

Khởi động Redis phù hợp ở localhost:6379 (hoặc trỏ cả hai node tới kho đã được cấp quyền). Chạy **hai tiến trình ứng dụng** cùng source và config Redis, khác port:

~~~bash
./gradlew bootRun --args='--server.port=8081'
./gradlew bootRun --args='--server.port=8082'
~~~

Chạy mỗi lệnh trong terminal/process riêng. Hai tiến trình cần sử dụng cùng Redis session namespace và cấu hình cookie/serialization. Với nhiều ứng dụng cùng hostname `localhost` nhưng khác port, cookie HTTP **không tách theo port**; điều này cho phép thử chuyển node nhưng có thể gây nhiễu nếu trên cùng hostname còn app khác. Nên dùng cookie jar riêng cho test.

Gửi POST tạo session ở A, sau đó GET ở B bằng cùng cookie jar:

~~~bash
curl -i -c shared-cookies.txt -X POST \
  'http://localhost:8081/api/demo-session/start' \
  -H 'Content-Type: application/json' \
  -d '{"nickname":"Lan"}'

curl -i -b shared-cookies.txt \
  'http://localhost:8082/api/demo-session'
~~~

Nếu Spring Session Redis hoạt động và cả hai node dùng chung store, GET tại B dự kiến **200** với nickname `Lan`. Thử DELETE ở B rồi GET ở A:

~~~bash
curl -i -b shared-cookies.txt -X DELETE \
  'http://localhost:8082/api/demo-session'

curl -i -b shared-cookies.txt \
  'http://localhost:8081/api/demo-session'
~~~

Dự kiến GET cuối là **204**, chứng minh invalidation đã được quan sát qua repository dùng chung (với điều kiện các request thực hiện tuần tự và backend khỏe). Nếu vẫn thấy 204 ngay trước khi chia sẻ Redis, chưa đủ chứng minh gì: hãy chắc chắn request đầu tạo session, response có cookie, tên/path cookie đúng và request sau gửi đúng cookie.

### 7.5. Khi kho session gặp lỗi

Nếu Redis không khả dụng, kết quả phụ thuộc cấu hình và thời điểm:
- Tạo/read/write session có thể thất bại; không được tự động coi user anonymous rồi tiếp tục quyền nhạy cảm.
- LB có thể nhận nhiều request thất bại đồng thời.
- Chuyển node không có tác dụng nếu cả hai đều phụ thuộc cùng store hỏng.
- Thêm Redis HA/replication giúp cải thiện availability nhưng **không cung cấp consistency/durability tuyệt đối**.
- Khi một phiên mất vì eviction/TTL, người dùng có thể cần tạo phiên lại/đăng nhập lại; hệ thống phải làm rõ hành vi trải nghiệm.

Cần monitoring session lookup failures, Redis latency, error rates, key eviction, stale serialization, rolling deploy compatibility. Không log session ID thô để debug; dùng request tracing và các metric tổng hợp.

## 8. Concurrency: shared session store không tự xử lý race condition

Hai request đồng thời có thể cùng đọc một attribute rồi sửa:

~~~text
Ban đầu counter=0
Request A đọc counter=0
Request B đọc counter=0
Request A ghi counter=1
Request B ghi counter=1
Kết quả counter=1 thay vì 2
~~~

Điều này có thể xảy ra với `HttpSession` cục bộ lẫn shared Redis. `setAttribute` không phải atomic “increment counter”, và container/store có thể có copy-on-read/write hoặc flush mode khác nhau. Một `synchronized(session)` trong node A **không đồng bộ với node B**.

Đối với operation quan trọng (thanh toán, kiểm kê, quota, giỏ hàng có tiền), cần nghiệp vụ có transaction, optimistic locking/version, Redis atomic command/Lua hoặc cơ chế hàng đợi/phân tán được thiết kế đúng. HttpSession phù hợp với trạng thái giao diện nhỏ và tạm thời; không dùng nó làm nguồn sự thật cho tài sản/đơn hàng.

Đặc biệt tránh đặt object mutable như `ArrayList` vào session rồi chỉnh nội dung mà không `setAttribute` lại: tùy session repository và flush mode, thay đổi bên trong object có thể không được đánh dấu “dirty” hoặc không được lưu đúng lúc. Với distributed session, ưu tiên immutable values, gán lại attribute sau thay đổi và thiết kế update an toàn trước cạnh tranh.

## 9. HttpSession, Spring MVC model session và Spring Security khác nhau

### 9.1. `@SessionAttribute` và `@SessionAttributes`

| API | Vị trí dùng | Mục đích |
| --- | --- | --- |
| `HttpSession` | Servlet request/controller | Chủ động tạo, đọc, ghi và hủy session |
| `@SessionAttribute("key")` | **Tham số** handler | Đọc một attribute đã tồn tại; có `required` |
| `@SessionAttributes("form")` | **Cấp controller** | Lưu model attribute tạm trong quy trình nhiều bước của controller |
| `SessionStatus#setComplete()` | Trong luồng `@SessionAttributes` | Kết thúc việc quản lý model session attributes của controller |
| `@RequestAttribute` | Tham số handler | Đọc attribute của **một request**, không phải session |

`@SessionAttributes` không phải câu lệnh tạo session tùy ý cho mọi dữ liệu. Nó thích hợp cho flow model qua nhiều request ở cùng controller; `SessionStatus.setComplete()` hoàn thành conversational model và dọn attribute liên quan, **không có nghĩa invalidate toàn bộ HttpSession** hay logout tài khoản.

`@SessionAttribute` phù hợp nếu filter/middleware đã đặt dữ liệu cần đọc; để không vô tình tạo session hoặc tự kiểm soát toàn bộ lifecycle, sử dụng `HttpServletRequest.getSession(false)` có thể dễ hiểu hơn.

### 9.2. Spring Security session management

Spring Security có thể dùng HttpSession để lưu `SecurityContext`/authenticated principal qua các request tùy authentication setup. Nhưng không phải mọi ứng dụng Spring Security đều stateful: bearer token resource server hoặc thiết lập `SessionCreationPolicy.STATELESS` có thể không duy trì session cho auth. Cụm từ “REST API” cũng **không bắt buộc** luôn stateless, dù stateless là lựa chọn phổ biến cho một số kiến trúc.

Đối với ứng dụng web đăng nhập cookie/session:
- Xác thực credentials ở auth provider/filter đáng tin.
- Có bảo vệ session fixation khi đăng nhập; Servlet hiện đại thường đổi session ID.
- Cấu hình CSRF protection cho request state-changing khi trình duyệt tự đính kèm cookie.
- Logout qua Spring Security để dọn security context và invalidated session theo config.
- Có thể áp giới hạn concurrent sessions và chiến lược khi session hết hạn.
- Xem xét remember-me token và SSO khác session; invalidating HttpSession không thu hồi mọi loại token.

Ví dụ `SessionCreationPolicy.STATELESS` nhằm tránh sử dụng HttpSession cho SecurityContext, nhưng **không phải lệnh cấm mọi code ứng dụng gọi `getSession(true)`**. Nếu muốn không có server session, phải thiết kế mọi thành phần đồng bộ với mục tiêu đó.

## 10. Chọn kiến trúc session khi tăng số lượng node

| Tiêu chí | Local container HttpSession | Sticky LB + local session | Spring Session + shared Redis/JDBC |
| --- | --- | --- | --- |
| Đơn giản khi một node | Tốt | Cần LB | Cần kho ngoài |
| Giữ state giữa hai node bất kỳ | Không | Không, trừ khi affinity luôn về node cũ | Có, nếu store và config khỏe |
| Node A mất khi có session | Thường mất session | Thường mất/ảnh hưởng phiên gắn A | Node B có thể tiếp tục với store chung |
| Latency cho attribute access | Thường trong process | Thường trong process | Có chi phí I/O/serialization |
| Vấn đề concurrency | Có | Có | Có, thậm chí cross-node |
| Vấn đề serialization/deploy | Container-specific | Container-specific | Rõ hơn, cần tương thích schema/serializer |
| Kho session là phụ thuộc mới | Không | Không | Có, cần HA/observability |
| Phù hợp | Dev, một node, session mất được | Affinity được chấp nhận, fallback có kế hoạch | Nhiều node cần duy trì session qua chuyển node |

Nếu nghiệp vụ **không cần server-side session**, một API stateless với xác thực token phù hợp có thể dễ scale hơn vì các node không cần dùng chung HttpSession. Nhưng token cũng có expiration, rotation, revocation, replay và security trade-off; không tuyên bố chuyển sang JWT tự động giải quyết mọi vấn đề phân tán.

Có ứng dụng vẫn dùng Redis cho caching/rate limiting nhưng không dùng Spring Session; chỉ thêm Redis dependency không có nghĩa `HttpSession` tự động chuyển sang Redis. Phải có Spring Session integration/repository filter và cấu hình đúng.

## 11. Bảo mật và vận hành thực tế

### 11.1. Rủi ro và biện pháp

| Rủi ro | Hành động |
| --- | --- |
| Session ID bị đọc từ JavaScript | Dùng cookie HttpOnly và phòng chống XSS |
| Cookie gửi qua HTTP | Bật HTTPS và Secure cookie ở production |
| Session fixation sau login | Xoay ID với Spring Security/container strategy |
| CSRF trên cookie-authenticated POST/DELETE | Dùng Spring Security CSRF token và chính sách SameSite phù hợp |
| Session tồn tại quá lâu | Timeout hợp lý, absolute lifetime nếu nghiệp vụ đòi hỏi |
| Lộ session trong logs | Không log ID/cookie; dùng correlation ID riêng |
| Redis outage/eviction | Giám sát availability, memory policy, TTL và recovery |
| Serialization của object lớn | Chỉ lưu dữ liệu nhỏ, ID bất biến, serializer/schema có version |
| Concurrent writes mất cập nhật | Atomic/transactional update ở domain store |
| Cross-environment session namespace | Prefix tách môi trường, credentials và network isolation |
| Logout chỉ xóa cookie client | Phải invalidate/revoke state phía server hoặc auth layer |
| Dùng session giữ tiền/quota | Chuyển nguồn sự thật sang transactional datastore |

### 11.2. Độ bền dữ liệu và session store

Một session **không phải** database giao dịch dài hạn. Nếu Redis được cấu hình làm cache có eviction, key session có thể mất trước expected inactivity timeout khi thiếu bộ nhớ. Redis replication/HA không đồng nghĩa không mất dữ liệu trong mọi partition/failover. JDBC-backed Spring Session có trade-off khác về độ bền, latency, cleanup và locking, nhưng cũng cần migration/schema, index, transaction và security.

Với rolling deployment, hai phiên bản app có thể chạy cùng lúc. Nếu session chứa serialized class của bản mới mà bản cũ không hiểu, người dùng gặp lỗi khi request tới node cũ. Cách giảm rủi ro: dùng record dữ liệu đơn giản, schema rõ, chiến lược serialization tương thích hoặc versioned attributes, và test canary/blue-green thực tế.

### 11.3. Điều cần đo trong production

Theo dõi: số session hoạt động, tỉ lệ tạo mới bất thường, mất session giữa requests, tỉ lệ login thất bại do timeout, Redis/session-store latency và error, dung lượng/key eviction, serialization failures, số cookie sai domain/path, session fixation/auth anomalies, thời gian xử lý logout và số request đồng thời trên cùng session.

Để chẩn đoán, dùng trace ID được tạo tin cậy và route template. Không đưa raw `Cookie`, `Set-Cookie`, session ID, password hoặc private attributes vào dashboard/log của mọi developer.

## 12. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân | Kiểm tra |
| --- | --- | --- |
| GET endpoint tạo `JSESSIONID` bất ngờ | `getSession()`/injected `HttpSession` hoặc filter/security tạo session | Log có kiểm soát nơi gọi `getSession(true)`, kiểm chain |
| Mỗi request có session ID mới | Client không gửi cookie, cookie path/domain/secure sai | Dùng curl cookie jar và inspect Set-Cookie/Cookie |
| Đang dùng HTTPS nhưng cookie không quay lại | Reverse proxy/forwarded headers, SameSite/Path/Domain | Test browser/devtools và ingress config |
| Session mất khi chuyển node | Container-local state trên từng JVM | Test request A→B, xem Spring Session/shared store |
| Sticky routing vẫn mất session khi deploy | Pod/node cũ bị thay, local memory không replica | Lập kế hoạch drain và shared repository hoặc chấp nhận reset |
| Redis có dữ liệu nhưng app không đọc session | Khác namespace/cookie name/serializer, session expired | Đối chiếu config mỗi node, TTL, phiên bản |
| Thay attribute nhưng node khác vẫn thấy cũ | Flush/save behavior hoặc concurrent updates | Chọn immutable value, set lại, xem transaction/last-writer |
| `IllegalStateException` sau logout | Code tiếp tục dùng object session đã invalidate | Dừng mọi truy cập phiên cũ sau `invalidate()` |
| Logout không thực sự logout | Chỉ xóa custom attr/cookie; security context/token còn | Dùng Spring Security logout/revocation flow |
| Tạo session cho tất cả request API | Cấu hình/framework hoặc dùng getSession mặc định | Kiểm sessions policy và các filters |
| Session expiry event không chạy đúng lúc | Repository/event config, Redis keyspace notifications | Không phụ thuộc event cho nghiệp vụ quan trọng |
| Memory leak/session quá lớn | Lưu entity graph/giỏ hàng lớn, timeout vô hạn | Chỉ lưu ID/small data, timeout và instrumentation |
| Counter/cart bị ghi đè | Hai request cùng sửa session | DB transaction, optimistic locking hoặc atomic Redis operation |
| Test MockMvc xanh, multi-node fail | Mock session không chứng minh cookie/network/store | Viết integration test hai server + Redis/LB |

## 13. Quy trình chẩn đoán từng bước

1. **Xem Set-Cookie** của request tạo phiên và **Cookie** của request sau. Xác định tên và Path/Domain/Secure/SameSite; không copy giá trị thật ra ticket/log công khai.
2. Dùng `request.getSession(false)` ở endpoint đọc để thấy session có thực sự tồn tại không; tránh làm kết quả thay đổi chỉ vì debug.
3. Kiểm `getMaxInactiveInterval()` và cấu hình `server.servlet.session.timeout` / `spring.session.timeout` theo version.
4. So sánh request vào node A rồi node B với cùng cookie. Nếu chỉ A đọc được, xác định local memory hay không tương thích Spring Session.
5. Kiểm Redis connectivity, namespace, TTL, serialization, flush mode, memory eviction và độ trễ.
6. Với concurrent updates, kiểm lại ai sửa attribute, có dùng read-modify-write không, có transaction/locking không.
7. Kiểm Spring Security: session creation policy, fixation, login/logout, CSRF, SecurityContextRepository và remember-me nếu có.
8. Thử shutdown một node và kiểm client còn phiên khi dùng store chung; với shared store down, kiểm phương án fail closed, metrics và thông báo người dùng.
9. Kiểm cookie flags và TLS/forwarded-header config trong môi trường thật.
10. Phân biệt dữ liệu user/business không được phép mất với trạng thái session có thể tái tạo; chuyển dữ liệu lâu dài sang persistence phù hợp.

## 14. Câu hỏi tự kiểm tra

**1.** `request.getSession(false)` khác `request.getSession()` như thế nào?

**Trả lời:** `false` không tạo session mới và trả null nếu không có phiên hợp lệ; `getSession()` có thể tạo phiên khi thiếu.

**2.** `session.invalidate()` xóa một attribute hay toàn bộ session?

**Trả lời:** Nó làm session không còn hợp lệ và unbind các attributes; không nên dùng tiếp object đó.

**3.** Browser có cookie `JSESSIONID` còn tồn tại, vậy session server chắc chắn còn không?

**Trả lời:** Không. Server có thể đã invalidate, timeout hoặc mất in-memory state.

**4.** Vì sao sticky LB không bảo đảm session tồn tại sau khi node A chết?

**Trả lời:** Affinity chỉ định tuyến request đến A khi A còn khả dụng; state local A thường mất nếu A bị thay và không replication.

**5.** Spring Session Redis có tự tạo transaction toàn cục cho mọi session attribute không?

**Trả lời:** Không. Nó chia sẻ persistence; vẫn cần thiết kế concurrency, serialization, failure handling và tính nhất quán.

**6.** Khi Spring Security dùng session để lưu auth, chỉ gọi `session.removeAttribute("user")` có phải logout an toàn không?

**Trả lời:** Không. Auth state có thể ở security context hoặc thành phần khác. Dùng logout flow được Security cấu hình.

**7.** Có thể dùng `@SessionAttributes` như alias của `HttpSession.invalidate()` không?

**Trả lời:** Không. `@SessionAttributes` dành cho model attributes trong controller workflow; `SessionStatus.setComplete()` dọn dữ liệu flow, không hủy toàn bộ session hay đảm bảo logout.

## 15. Tài liệu chính thức

- [Jakarta Servlet 6.0 — `HttpSession`](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession): attributes, invalidate, inactivity timeout, access time, isNew.
- [Jakarta Servlet 6.0 — `HttpServletRequest`](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest): `getSession(false)`, `changeSessionId()`, request/session ID methods.
- [Spring Framework — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html): đọc session attribute có sẵn.
- [Spring Framework — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): lưu model attributes qua các bước form.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): authentication persistence, session fixation, concurrency/session policies.
- [Spring Boot 3.3 — Spring Session Integration](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html): session stores, auto-configuration, timeout properties.
- [Spring Session 3.3 — Redis Reference](https://docs.spring.io/spring-session/reference/3.3/http-session.html): thay HttpSession container bằng Spring Session, clustered session integration.
- [Spring Session — Redis Boot Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): repository filter, Redis config và cookie behavior (đối chiếu version Boot khi chọn dependency).
- [Spring Session — API và Redis expiration/events](https://docs.spring.io/spring-session/reference/api.html): repository, flush modes, serialization, session events.

**Ghi nhớ:** HttpSession giúp nhiều HTTP requests chia sẻ trạng thái bằng session ID; `getSession(false)` đọc mà không tạo, `invalidate()` hủy phiên, timeout dựa trên inactivity. Khi chuyển từ một server sang nhiều server, cần quyết định rõ liệu giữ affinity và chấp nhận mất state hay dùng Spring Session với shared repository. Kho phiên phân tán giúp chia sẻ state nhưng vẫn cần bảo vệ ID, quản lý lifecycle, serialization, concurrency, availability và dữ liệu nghiệp vụ lâu dài.
