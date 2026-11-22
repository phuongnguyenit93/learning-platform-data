# WebSession, WebSessionManager và thời điểm lưu phiên trong Spring WebFlux

## 1. WebSession giải quyết bài toán gì?

Trong Spring WebFlux, `WebSession` là abstraction của **phiên làm việc phía server**, cho phép giữ các thuộc tính của một người dùng qua nhiều HTTP request. Ví dụ: trạng thái giỏ hàng tạm, bước hiện tại của một quy trình nhiều màn hình, lựa chọn giao diện hoặc một mã tham chiếu ngắn hạn.

Khác với cookie tự chứa toàn bộ dữ liệu, session thường hoạt động theo mô hình:

- Server lưu dữ liệu session trong một nơi lưu trữ.
- Client giữ một **session ID** để server tìm lại session trong request tiếp theo.
- Server dùng session ID để truy xuất `WebSession`, đọc/ghi attributes và cập nhật trạng thái phiên.

Cookie mặc định của `CookieWebSessionIdResolver` có tên `SESSION`; cookie chứa định danh phiên, không phải toàn bộ map attributes. Session data vẫn nằm ở server-side store.

Trong WebFlux, API session được thiết kế reactive. `ServerWebExchange.getSession()` trả về `Mono<WebSession>`, nên controller hoặc filter có thể kết hợp việc đọc/ghi session với các publisher khác mà không gọi `block()`.

**Điểm quan trọng nhất của bài:** lấy được một đối tượng `WebSession` **không đồng nghĩa session đã được tạo và gửi ID cho client**. Session chỉ được đánh dấu started khi gọi `start()` hoặc khi thêm attribute. Việc lưu session thường do framework tự thực hiện ngay trước khi response được commit.

## 2. WebSession, WebSessionManager, WebSessionIdResolver và WebSessionStore

Bốn thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `WebSession` | API thao tác với ID, attributes, thời gian truy cập, idle timeout, start, save, invalidate và đổi ID |
| `WebSessionManager` | Lấy session phù hợp với HTTP request hiện tại; tìm session theo ID client gửi hoặc tạo instance mới |
| `WebSessionIdResolver` | Đọc session ID từ request và gửi/expire ID ở response, thường qua cookie hoặc header |
| `WebSessionStore` | Chiến lược tạo, truy xuất, cập nhật last-access time và xóa session trong nơi lưu trữ |

Luồng tổng quát:

~~~text
HTTP request
   |
   | Cookie SESSION=<opaque-id> hoặc header session ID
   v
WebSessionIdResolver
   | resolveSessionIds(exchange)
   v
WebSessionManager
   | getSession(exchange)
   v
WebSessionStore
   | retrieveSession(id) hoặc createWebSession()
   v
WebSession
   | getAttribute / getAttributes / put / invalidate
   v
WebFlux xử lý handler và tạo response
   |
   | ngay trước khi response commit
   v
WebSession.save()
   | persist hoặc remove theo trạng thái
   v
WebSessionIdResolver cập nhật/expire session ID ở response
~~~

Trong WebFlux infrastructure, bean có tên `webSessionManager` là nơi cung cấp session cho `ServerWebExchange`. Theo cấu hình mặc định, đó là `DefaultWebSessionManager`. Manager này kết hợp một resolver để xử lý session ID và một store để quản lý dữ liệu phiên.

## 3. Lấy session không tự động bắt đầu session

Cách thông thường trong controller hoặc WebFilter là:

~~~java
Mono<WebSession> session = exchange.getSession();
~~~

`ServerWebExchange.getSession()` luôn trả về một `WebSession` tương ứng với session ID client gửi, hoặc một instance mới nếu client chưa gửi ID hay session cũ đã hết hạn. Tuy nhiên, việc gọi `getSession()` **không tự động start session**.

Khi instance mới chưa started:

- `session.isStarted()` trả về `false`.
- Chưa cần gửi session ID cho client.
- `save()` sẽ không tạo session mới nếu chưa gọi `start()` hoặc chưa thêm attribute.

Có hai cách chủ động bắt đầu:

### Cách 1: thêm session attribute

~~~java
return exchange.getSession().map(session -> {
    session.getAttributes().put("theme", "dark");
    return "Session attribute added";
});
~~~

Thêm attribute sẽ **ngầm start** session. Đây là cách thường gặp nhất vì ứng dụng chỉ tạo session khi thật sự có dữ liệu cần lưu.

### Cách 2: gọi start() rõ ràng

~~~java
return exchange.getSession().map(session -> {
    session.start();
    return "Session explicitly started";
});
~~~

Dùng khi cần một session ngay cả khi chưa có attribute. Ví dụ, một flow cần phát hành session ID trước khi người dùng đi qua các bước tiếp theo.

Không nên gọi `start()` ở mọi request nếu endpoint không thực sự cần session. Tạo session không cần thiết làm tăng số lượng session phía server và phát cookie cho client dù không có trạng thái cần giữ.

## 4. Các thao tác chính trên WebSession

`WebSession` cung cấp những API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `getId()` | Lấy session ID hiện tại |
| `getAttributes()` | Lấy map attributes có thể đọc/ghi |
| `getAttribute(name)` | Lấy attribute; trả về null nếu không có |
| `getAttributeOrDefault(name, defaultValue)` | Lấy attribute hoặc giá trị mặc định |
| `getRequiredAttribute(name)` | Lấy attribute bắt buộc; báo lỗi nếu thiếu |
| `start()` | Đánh dấu session đã bắt đầu |
| `isStarted()` | Kiểm tra session đã started hay chưa |
| `save()` | Lưu qua WebSessionStore; framework tự gọi trước khi response commit |
| `invalidate()` | Hủy session hiện tại và xóa session khỏi storage |
| `changeSessionId()` | Tạo ID mới và cập nhật storage |
| `getCreationTime()` | Thời điểm session được tạo |
| `getLastAccessTime()` | Thời điểm truy cập gần nhất |
| `getMaxIdleTime()` | Thời gian không hoạt động tối đa |
| `setMaxIdleTime(duration)` | Đặt thời gian idle tối đa |
| `isExpired()` | Kiểm tra session đã hết hạn hay chưa |

Ví dụ đọc và cập nhật attribute:

~~~java
return exchange.getSession().map(session -> {
    String theme = session.getAttributeOrDefault("theme", "light");
    session.getAttributes().put("theme", "dark");
    return theme;
});
~~~

`getAttributes()` trả về map của session. Việc sửa map làm session được đánh dấu started khi thêm attribute mới. Nếu chỉ đọc session hoặc chỉ lấy ID, không nhất thiết tạo session mới.

Không lưu dữ liệu lớn, file, stream, entity graph phức tạp hoặc object không thể serialize/khôi phục ổn định vào session. Chỉ giữ trạng thái nhỏ cần thiết để nhận diện và tiếp tục flow.

## 5. Thời điểm session được lưu: trước khi response commit

Đây là phần dễ gây hiểu nhầm nhất.

`WebSession.save()` trả về `Mono<Void>`, nhưng API Spring ghi rõ phương thức này **không dành cho ứng dụng gọi trực tiếp**. Framework tự gọi save **ngay trước khi response được commit**.

Quy trình:

1. Handler lấy `WebSession`.
2. Handler đọc hoặc thay đổi attributes.
3. Handler trả về `Mono`/`Flux` response.
4. Khi response chuẩn bị commit, WebFlux lưu session nếu cần.
5. Resolver gửi session ID hoặc xử lý việc expire ID trong response.

Vì vậy, đoạn sau là đủ:

~~~java
@GetMapping("/theme")
public Mono<String> changeTheme(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.getAttributes().put("theme", "dark");
        return "Theme saved";
    });
}
~~~

Không cần:

~~~java
// Không nên gọi save() trực tiếp trong controller.
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put("theme", "dark");
        return session.save().thenReturn("saved");
    });
~~~

Việc tự gọi `save()` có thể làm rối lifecycle và không cần thiết trong flow WebFlux thông thường. Hãy để framework quản lý việc persist và gửi session ID.

**Hãy cập nhật session trước khi response được commit.** Với response streaming, response có thể được commit khi bắt đầu ghi body; đừng dựa vào việc sửa session sau khi stream đã bắt đầu để cập nhật cookie hoặc trạng thái phiên cho response hiện tại.

Nếu session chưa started, `save()` không có tác dụng tạo session mới. Nếu session đã được lấy từ store nhưng sau đó invalidated, thao tác save có thể báo lỗi theo hợp đồng của implementation.

## 6. WebSessionManager.getSession() hoạt động thế nào?

`WebSessionManager` là abstraction mức thấp để truy xuất session cho một `ServerWebExchange`:

~~~java
Mono<WebSession> getSession(ServerWebExchange exchange);
~~~

Hợp đồng đảm bảo trả về một trong hai trường hợp:

- Session tương ứng với ID mà client gửi trong request, nếu session còn hợp lệ.
- Một session instance mới nếu client không gửi ID hoặc session cũ đã hết hạn.

Ứng dụng thông thường nên dùng:

~~~java
exchange.getSession()
~~~

Đây là API tiện lợi đã được `ServerWebExchange` cung cấp. Chỉ cần tương tác trực tiếp với `WebSessionManager` khi viết hạ tầng tùy biến, tích hợp một session manager khác hoặc xây dựng thành phần cấp thấp.

Ví dụ dùng manager trực tiếp trong một thành phần hạ tầng:

~~~java
// Mã minh họa; manager được inject từ ApplicationContext.
Mono<WebSession> current =
    webSessionManager.getSession(exchange);
~~~

Không cần inject manager vào mọi controller chỉ để đọc một attribute. Dùng `exchange.getSession()` giúp code bám sát API WebFlux thông thường.

## 7. WebSessionIdResolver: cookie hay header?

`WebSessionIdResolver` xác định cách client gửi session ID và cách server trả ID về client. Hai implementation phổ biến:

| Resolver | Cách truyền ID | Trường hợp sử dụng |
| --- | --- | --- |
| `CookieWebSessionIdResolver` | Cookie trong request/response | Trình duyệt và web application |
| `HeaderWebSessionIdResolver` | HTTP header | Client API có chủ đích quản lý session ID qua header |

`DefaultWebSessionManager` mặc định dùng `CookieWebSessionIdResolver`. Cookie name mặc định là `SESSION`.

### CookieWebSessionIdResolver

Cookie thuận tiện cho browser vì trình duyệt tự gửi cookie phù hợp theo domain/path. Có thể đổi tên cookie và cấu hình thuộc tính cookie bằng resolver.

Ví dụ tùy biến tên cookie và một số thuộc tính:

~~~java
@Bean
WebSessionManager webSessionManager() {
    DefaultWebSessionManager manager = new DefaultWebSessionManager();

    CookieWebSessionIdResolver resolver =
        new CookieWebSessionIdResolver();

    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(cookie -> cookie
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax"));

    manager.setSessionIdResolver(resolver);
    return manager;
}
~~~

Đây là cấu hình hạ tầng tùy chọn, không cần thêm vào demo mặc định. Khi dùng `secure(true)`, client chỉ gửi cookie qua HTTPS; môi trường production cần cấu hình HTTPS đúng cách.

### HeaderWebSessionIdResolver

Resolver dạng header có thể phù hợp cho API client không dựa vào browser cookie:

~~~java
HeaderWebSessionIdResolver resolver =
    new HeaderWebSessionIdResolver();

resolver.setHeaderName("X-SESSION-ID");
~~~

Client phải gửi lại header này trong request tiếp theo. Header session ID vẫn là credential nhạy cảm; không log giá trị, không đưa vào URL và phải bảo vệ bằng TLS.

Dù dùng cookie hay header, resolver chỉ vận chuyển ID. Việc xác thực danh tính và kiểm tra quyền vẫn thuộc Spring Security hoặc tầng authorization của ứng dụng.

## 8. WebSessionStore và lưu trữ mặc định

`WebSessionStore` định nghĩa chiến lược persistence của session:

| Method | Trách nhiệm |
| --- | --- |
| `createWebSession()` | Tạo một WebSession instance mới |
| `retrieveSession(id)` | Tìm session theo ID; kiểm tra expiry và cập nhật last access time |
| `updateLastAccessTime(session)` | Cập nhật thời điểm truy cập gần nhất |
| `removeSession(id)` | Xóa session khỏi storage |

`DefaultWebSessionManager` mặc định sử dụng `InMemoryWebSessionStore`. Store này là implementation map-based, lưu session trong bộ nhớ của tiến trình.

Ưu điểm của in-memory store:

- Không cần database hoặc Redis để chạy demo.
- Đơn giản cho ứng dụng đơn instance và môi trường phát triển.
- Dễ kiểm thử vòng đời session.

Giới hạn:

- Session nằm trong bộ nhớ của một instance ứng dụng.
- Restart process có thể làm mất toàn bộ session.
- Nhiều node không tự chia sẻ cùng một session store.
- Nếu load balancer chuyển request sang node khác, node đó có thể không tìm thấy session.

Vì vậy, ứng dụng chạy nhiều instance hoặc cần session tồn tại qua restart nên dùng một store chia sẻ như Spring Session với Redis, thay vì phụ thuộc vào map trong bộ nhớ.

## 9. Tích hợp Spring Session với Redis

Spring Session có thể thay implementation `WebSession` phía dưới mà không buộc controller thay đổi cách gọi `exchange.getSession()`. Tích hợp WebFlux sử dụng `WebSessionManager` được hỗ trợ bởi `ReactiveSessionRepository`.

Ví dụ cấu hình khái niệm:

~~~java
@Configuration
@EnableRedisWebSession
public class SessionConfiguration {
}
~~~

Cần thêm dependency Spring Session Data Redis tương thích với Spring Boot/Spring Framework của dự án và cấu hình reactive Redis connection factory. Trong Spring Boot, có thể cấu hình host, port và credentials của Redis qua application properties.

`@EnableRedisWebSession` đăng ký bean `webSessionManager` dùng implementation dựa trên Redis. Từ góc nhìn controller, cách dùng vẫn giữ nguyên:

~~~java
return exchange.getSession()
    .map(session -> {
        session.getAttributes().put("cartCount", 3);
        return "updated";
    });
~~~

Điểm khác biệt nằm ở nơi session được persist. Spring Session xử lý việc tích hợp với `ReactiveSessionRepository`; ứng dụng không cần tự viết một `WebSessionStore` Redis nếu dùng module hỗ trợ có sẵn.

Với cluster, cần cấu hình Redis availability, timeout, serialization, expiry, network security và quan sát lỗi lưu session. Session store tập trung giúp nhiều node dùng chung session nhưng cũng trở thành một dependency quan trọng của request.

## 10. Idle timeout và thời điểm hết hạn

`WebSession` có các thuộc tính thời gian:

- `getCreationTime()`: thời điểm tạo session.
- `getLastAccessTime()`: thời điểm truy cập gần nhất.
- `getMaxIdleTime()`: thời gian tối đa được phép không có hoạt động.
- `setMaxIdleTime(Duration)`: thay đổi idle timeout.
- `isExpired()`: kiểm tra trạng thái hết hạn.

Ví dụ đặt idle timeout 20 phút:

~~~java
return exchange.getSession().map(session -> {
    session.setMaxIdleTime(Duration.ofMinutes(20));
    session.getAttributes().put("userPreference", "compact");
    return "updated";
});
~~~

Session có thể hết hạn khi thời gian kể từ last access vượt quá max idle time. Store cần kiểm tra expiration khi truy xuất; session hết hạn được loại bỏ và request tiếp theo nhận một session mới.

Một giá trị `Duration` âm biểu thị session không hết hạn theo idle timeout. Không nên dùng session không hết hạn nếu không có chính sách dọn dẹp và bảo mật rõ ràng.

**Cookie Max-Age và session maxIdleTime là hai khái niệm khác nhau:**

- Cookie Max-Age kiểm soát thời gian browser giữ cookie session ID.
- `WebSession.maxIdleTime` kiểm soát thời gian server cho phép session không hoạt động.

Browser vẫn có thể gửi cookie cũ sau khi session phía server đã hết hạn; server sẽ không khôi phục dữ liệu cũ chỉ vì cookie còn tồn tại.

## 11. Xóa session, logout và đổi session ID

### invalidate()

`invalidate()` hủy session hiện tại và xóa session storage:

~~~java
@PostMapping("/logout")
public Mono<ResponseEntity<Void>> logout(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate)
        .thenReturn(ResponseEntity.<Void>noContent().build());
}
~~~

Đây là ví dụ trong controller. Vì `invalidate()` trả về `Mono<Void>`, phải compose publisher để response chỉ được tạo sau khi thao tác invalidate hoàn tất. Không gọi `subscribe()` bên trong controller.

Sau khi logout, session cũ không còn được sử dụng. Session ID cookie được resolver/framework xử lý theo lifecycle invalidation; client không nên tiếp tục dùng ID cũ.

### changeSessionId()

`changeSessionId()` tạo ID mới và cập nhật storage:

~~~java
return exchange.getSession()
    .flatMap(WebSession::changeSessionId);
~~~

Đây là thao tác reactive trả `Mono<Void>`. Dùng khi cần đổi session ID mà giữ nguyên session state, chẳng hạn sau một thay đổi mức tin cậy hoặc quyền truy cập.

Một trường hợp quan trọng là **session fixation**: sau khi người dùng đăng nhập hoặc quyền thay đổi, cần bảo đảm ID phiên không tiếp tục là ID mà kẻ tấn công có thể đã biết trước. Spring Security cung cấp cơ chế session fixation protection; nên dùng cấu hình bảo mật của framework thay vì tự triển khai toàn bộ quy trình.

### Xóa một attribute

Nếu chỉ cần xóa một phần trạng thái:

~~~java
return exchange.getSession().map(session -> {
    session.getAttributes().remove("temporaryCheckout");
    return "temporary data removed";
});
~~~

Không cần invalidate toàn bộ session nếu chỉ muốn bỏ một thuộc tính tạm.

## 12. Phân biệt WebSession với @SessionAttribute và @SessionAttributes

Spring WebFlux có thêm annotation hỗ trợ controller:

| Cơ chế | Mục đích |
| --- | --- |
| `WebSession` | API trực tiếp để đọc, ghi, invalidate hoặc đổi session ID |
| `@SessionAttribute` | Đọc một attribute đã tồn tại và được quản lý bên ngoài controller |
| `@SessionAttributes` | Lưu model attribute của một controller vào WebSession giữa nhiều request |
| `SessionStatus.setComplete()` | Đánh dấu hoàn tất workflow và xóa các model attributes được quản lý bởi `@SessionAttributes` |

Ví dụ đọc attribute đã có:

~~~java
@GetMapping("/profile")
public Mono<String> profile(
        @SessionAttribute(name = "displayName", required = false)
        String displayName) {
    return Mono.just(
        displayName == null ? "Guest" : displayName
    );
}
~~~

`@SessionAttribute` phù hợp khi attribute đã được tạo bởi filter, security hoặc thành phần khác. Nếu controller cần tự thêm/xóa attributes, dùng `WebSession` trực tiếp.

`@SessionAttributes` phù hợp với workflow controller, chẳng hạn giữ một form nhiều bước. Đây là cơ chế model attribute theo phạm vi controller, khác với việc truy cập trực tiếp toàn bộ session map.

## 13. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ tạo một session counter đơn giản:

- `GET /api/session`: đọc session, tăng số lần truy cập và trả JSON.
- `POST /api/session/logout`: invalidate session và trả 204.
- Dùng cookie jar của cURL để gửi lại session ID qua nhiều request.

Cấu trúc:

~~~text
websession-demo/
├── pom.xml
└── src/main/java/com/example/websession/
    ├── WebSessionApplication.java
    └── SessionController.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>websession-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/websession/WebSessionApplication.java`:

~~~java
package com.example.websession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSessionApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/websession/SessionController.java`:

~~~java
package com.example.websession;

import java.time.Duration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import org.springframework.web.server.WebSession;

@RestController
@RequestMapping("/api/session")
public class SessionController {

    public record SessionView(
        int visits,
        boolean started,
        long maxIdleSeconds
    ) {}

    @GetMapping
    public Mono<SessionView> visit(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer previous = session.getAttribute("visits");
            int visits = previous == null ? 1 : previous + 1;

            session.getAttributes().put("visits", visits);
            session.setMaxIdleTime(Duration.ofMinutes(20));

            return new SessionView(
                visits,
                session.isStarted(),
                session.getMaxIdleTime().toSeconds()
            );
        });
    }

    @PostMapping("/logout")
    public Mono<ResponseEntity<Void>> logout(
            ServerWebExchange exchange) {
        return exchange.getSession()
            .flatMap(WebSession::invalidate)
            .thenReturn(ResponseEntity.<Void>noContent().build());
    }
}
~~~

Chạy từ thư mục `websession-demo` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Request đầu tiên

~~~bash
curl -i -c session.cookies -b session.cookies http://localhost:8080/api/session
~~~

Body JSON dự kiến:

~~~json
{"visits":1,"started":true,"maxIdleSeconds":1200}
~~~

Response đầu tiên sẽ có cookie session ID nếu session được start và lưu thành công. Với resolver mặc định, tên cookie là `SESSION`; giá trị ID là opaque và thay đổi theo lần chạy.

### Request tiếp theo với cùng cookie

~~~bash
curl -i -c session.cookies -b session.cookies http://localhost:8080/api/session
~~~

Body JSON dự kiến:

~~~json
{"visits":2,"started":true,"maxIdleSeconds":1200}
~~~

Client gửi lại cookie, server tìm session cũ và tăng counter từ 1 lên 2. Không có cookie jar, mỗi request có thể nhận session mới và counter bắt đầu lại.

### Logout

~~~bash
curl -i -X POST -b session.cookies -c session.cookies http://localhost:8080/api/session/logout
~~~

Kết quả chính:

~~~http
HTTP/1.1 204 No Content
~~~

Sau logout, request GET tiếp theo sẽ dùng một session mới và counter bắt đầu lại từ 1.

Demo dùng default in-memory store, nên phù hợp để học và chạy local. Nó không cung cấp session persistence qua restart hoặc chia sẻ giữa nhiều node.

## 14. Race condition khi nhiều request cùng dùng một session

Một session có thể được dùng bởi nhiều request đồng thời, ví dụ browser mở nhiều tab hoặc client gửi song song nhiều request với cùng cookie.

Đoạn đọc-sửa-ghi:

~~~java
Integer old = session.getAttribute("visits");
int next = old == null ? 1 : old + 1;
session.getAttributes().put("visits", next);
~~~

không phải một phép tăng nguyên tử xuyên suốt nhiều request. Hai request có thể cùng đọc giá trị 5, cùng tính 6 rồi cùng ghi 6; một lần tăng bị mất.

Không nên mặc định toàn bộ `WebSession` hoặc object nằm trong attributes là thread-safe. Với dữ liệu cần tính nhất quán:

- Dùng thao tác atomic tại Redis/database hoặc một store hỗ trợ cập nhật có kiểm soát.
- Thiết kế operation idempotent nếu client có thể retry.
- Tránh giữ mutable object lớn được nhiều request sửa đồng thời.
- Không xem session là nơi lưu dữ liệu nghiệp vụ cần transaction mạnh.

Session phù hợp với trạng thái ngắn hạn phục vụ trải nghiệm request, không thay thế database làm nguồn dữ liệu chính.

## 15. Bảo mật và vận hành session

Session ID là một credential dạng bearer: ai có ID hợp lệ có thể được nhận diện như chủ phiên theo chính sách ứng dụng. Cần bảo vệ cả ID và dữ liệu session.

### Cookie và transport

- Dùng HTTPS trong production.
- Bật `Secure` để browser chỉ gửi cookie qua HTTPS.
- Bật `HttpOnly` để JavaScript phía browser không đọc cookie.
- Chọn `SameSite` phù hợp với luồng điều hướng và tích hợp cross-site.
- Cấu hình Domain/Path hẹp nhất có thể.
- Không đặt session ID trong URL hoặc query string.

`SameSite` không thay thế hoàn toàn CSRF protection. Với cookie tự động được browser gửi, cần bật cơ chế chống CSRF phù hợp cho các request thay đổi trạng thái.

### Session fixation và logout

- Dùng Spring Security session fixation protection khi xác thực.
- Đổi session ID sau khi quyền/trạng thái xác thực thay đổi theo policy.
- Invalidate session khi logout hoặc khi cần kết thúc phiên.
- Không log session ID, cookie value hoặc toàn bộ attributes nhạy cảm.
- Không tin dữ liệu session như bằng chứng authorization nếu nó chưa được thiết lập từ nguồn đáng tin cậy.

### Dữ liệu lưu trong session

- Chỉ lưu dữ liệu nhỏ và cần thiết.
- Tránh lưu password, access token dài hạn, thông tin thẻ thanh toán hoặc dữ liệu bí mật không cần thiết.
- Xác định cách serialize nếu dùng store ngoài tiến trình.
- Thiết kế versioning cho session data nếu nhiều phiên bản ứng dụng cùng đọc/ghi.
- Có chính sách expiry và cleanup để tránh session tồn tại lâu hơn nhu cầu.

### Vận hành

Theo dõi số lượng session active, tỷ lệ session hết hạn, lỗi đọc/ghi store, latency khi lấy session và kích thước payload. Nếu Redis/store lỗi, request cần xử lý lỗi theo chính sách; đừng âm thầm biến mọi lỗi persistence thành session mới nếu điều đó có thể làm mất trạng thái hoặc bỏ qua yêu cầu bảo mật.

## 16. Những lỗi thường gặp

1. **Gọi `exchange.getSession()` rồi nghĩ cookie đã được gửi:** sai. Chỉ lấy instance chưa start session; cần `start()` hoặc thêm attribute.
2. **Gọi `session.save()` thủ công trong controller:** không cần thiết trong flow thông thường; framework tự save trước response commit.
3. **Sửa session sau khi response đã commit:** có thể quá muộn để persist thay đổi hoặc cập nhật cookie cho response hiện tại.
4. **Gọi `block()` trên `Mono<WebSession>`:** chặn event-loop. Compose bằng `map`/`flatMap` và trả publisher.
5. **Gọi `subscribe()` thủ công để lưu session:** tạo subscription tách khỏi lifecycle HTTP. Trả publisher cho WebFlux.
6. **Tạo session ở mọi request dù không có state:** làm tăng số session và phát cookie không cần thiết.
7. **Nhầm cookie Max-Age với server idle timeout:** một bên là browser giữ cookie, bên kia là server hết hạn session.
8. **Dùng in-memory store cho cluster mà không có chiến lược chia sẻ:** node khác không thấy session được tạo trong process này.
9. **Lưu object lớn hoặc không serialize được:** làm tăng bộ nhớ, latency hoặc lỗi khi dùng distributed store.
10. **Coi session attributes là thread-safe:** request song song có thể ghi đè dữ liệu; read-modify-write không tự atomic.
11. **Không invalidate khi logout:** session cũ có thể tiếp tục được sử dụng nếu ID còn hợp lệ.
12. **Không đổi session ID sau xác thực:** có thể tạo rủi ro session fixation; dùng Spring Security protection.
13. **Log session ID:** biến log thành nơi lưu credential có thể bị tái sử dụng.
14. **Dùng cookie session nhưng bỏ qua CSRF:** browser tự gửi cookie, nên cần bảo vệ request thay đổi trạng thái.
15. **Đưa session ID vào URL:** ID có thể rò qua browser history, referrer, analytics và access log.
16. **Dùng session làm nguồn dữ liệu nghiệp vụ:** session ngắn hạn, có thể hết hạn hoặc mất khi store thay đổi; dữ liệu quan trọng cần database.
17. **Cho rằng WebSessionManager là nơi chứa toàn bộ attributes:** manager điều phối việc lấy session; store mới là chiến lược persistence.
18. **Tự triển khai resolver/store mà bỏ kiểm tra expiry:** session hết hạn có thể được sử dụng lại hoặc không cập nhật last access time đúng cách.

## 17. Checklist thiết kế session

Trước khi dùng session, hãy xác định:

- Có thực sự cần giữ trạng thái qua nhiều HTTP request không?
- Dữ liệu nào được lưu? Có nhạy cảm hoặc quá lớn không?
- Khi nào session bắt đầu: thêm attribute hay gọi `start()`?
- Thay đổi session có xảy ra trước response commit không?
- Idle timeout và cookie lifetime có phù hợp không?
- Store là in-memory, Redis hay persistence khác?
- Ứng dụng chạy một node hay nhiều node?
- Cookie có Secure, HttpOnly, SameSite và HTTPS phù hợp không?
- CSRF được xử lý ra sao nếu browser tự gửi cookie?
- Login/logout và session fixation được bảo vệ thế nào?
- Request song song có thể cập nhật cùng attribute không?
- Đã kiểm thử expiry, invalidation, session ID rotation và store failure chưa?

## 18. Câu hỏi tự kiểm tra

**1.** `WebSession` là gì? API server-side để giữ session attributes qua nhiều HTTP request.

**2.** `ServerWebExchange.getSession()` trả về kiểu gì? `Mono<WebSession>`.

**3.** Gọi `getSession()` có tự start session không? Không. Nó trả về session phù hợp hoặc instance mới; cần `start()` hoặc thêm attribute để bắt đầu.

**4.** `WebSessionManager` có nhiệm vụ gì? Tìm session theo ID client gửi hoặc cung cấp session mới cho exchange.

**5.** `WebSessionIdResolver` làm gì? Đọc session ID từ request và gửi/expire ID ở response.

**6.** `WebSessionStore` làm gì? Tạo, truy xuất, cập nhật last access time và xóa session.

**7.** Mặc định `DefaultWebSessionManager` dùng resolver/store nào? `CookieWebSessionIdResolver` và `InMemoryWebSessionStore`.

**8.** Tên cookie mặc định của `CookieWebSessionIdResolver` là gì? `SESSION`.

**9.** Khi nào WebFlux tự gọi `WebSession.save()`? Ngay trước khi response được commit.

**10.** Có nên gọi `save()` thủ công trong controller không? Không trong flow thông thường; framework tự quản lý.

**11.** `Mono<Void>` từ `invalidate()` và `changeSessionId()` nên được xử lý thế nào? Compose bằng `flatMap`/`then`, không bỏ publisher và không subscribe thủ công.

**12.** Làm sao đặt idle timeout? Gọi `session.setMaxIdleTime(Duration)`.

**13.** In-memory store có phù hợp cluster nhiều node không? Không nếu không có session store chia sẻ; mỗi process giữ map riêng.

**14.** Dùng gì để chia sẻ WebSession qua nhiều node? Spring Session với `ReactiveSessionRepository`, ví dụ Redis.

**15.** Vì sao không nên cập nhật counter bằng read-modify-write trong session khi request song song? Vì thao tác không tự atomic; có thể mất cập nhật.

**16.** Vì sao cần đổi session ID sau đăng nhập? Giảm nguy cơ session fixation; Spring Security có cơ chế bảo vệ tương ứng.

**Ghi nhớ:** `WebSession` giữ attributes phía server; `WebSessionManager` lấy session cho request; `WebSessionIdResolver` vận chuyển ID; `WebSessionStore` quản lý persistence. Lấy session không tự start nó. Thêm attribute hoặc gọi `start()` mới bắt đầu; WebFlux tự gọi `save()` ngay trước response commit. Dùng `exchange.getSession()` và compose reactive, chọn store phù hợp deployment, quản lý idle timeout, invalidate/logout và bảo vệ session ID như một credential.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebSession Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework 6.2 — WebSessionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/session/WebSessionManager.html)
- [Spring Framework 6.2 — DefaultWebSessionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html)
- [Spring Framework 6.2 — Reactive Core and WebSession infrastructure](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — @SessionAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/sessionattribute.html)
- [Spring Framework 6.2 — @SessionAttributes](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/sessionattributes.html)
- [Spring Session — WebSession Integration and Redis](https://docs.spring.io/spring-session/reference/web-session.html).