# Request, session, application và WebSocket scope trong Spring Framework

## 1. Vì sao cần web bean scope?

Spring IoC Container quản lý vòng đời của bean theo **scope**. Nếu không chỉ định scope, một bean thường là `singleton`: mỗi định nghĩa bean có một instance trong một Spring IoC container. Trong ứng dụng web, không phải trạng thái nào cũng nên chia sẻ cho toàn bộ request hay người dùng. Spring cung cấp bốn web scope để ràng buộc instance vào vòng đời của HTTP request, HTTP session, ServletContext hoặc phiên WebSocket.

Phân biệt ba khái niệm:
- **Bean definition**: cấu hình Spring biết cách tạo đối tượng.
- **Bean instance**: đối tượng thật được tạo theo bean definition.
- **Scope**: quy tắc Spring tìm/tạo và giữ instance cho một ngữ cảnh cụ thể. Hai lần truy cập cùng bean definition trong *cùng ngữ cảnh scope* thường nhận cùng target instance; khi đổi ngữ cảnh, target có thể khác.

| Scope | Khóa ngữ cảnh | Thời điểm tạo target | Kết thúc / thu hồi | Dùng điển hình |
| --- | --- | --- | --- | --- |
| `request` | Một HTTP request | Lần đầu bean được sử dụng trong request | Kết thúc request và cleanup tương ứng | Request ID, dữ liệu xử lý tạm cho một request |
| `session` | Một HTTP `HttpSession` | Lần đầu dùng trong session đó | Session hết hạn hoặc bị invalidate | Tùy chọn UI, quy trình thao tác có trạng thái cho một phiên |
| `application` | Một `ServletContext` | Lần đầu bean được sử dụng trong web application | ServletContext kết thúc | Trạng thái/cấu hình chia sẻ trong **một instance** ứng dụng |
| `websocket` | Một phiên WebSocket trong hạ tầng Spring STOMP messaging | Lần đầu dùng trong WebSocket session | WebSocket session kết thúc | Bộ đếm/trạng thái riêng của kết nối STOMP |

Các scope này **không** đồng nghĩa với `singleton` hay `prototype`. `singleton` thuộc về từng Spring IoC container; `application` thuộc về `ServletContext`, có thể được nhìn thấy như một servlet context attribute, kể cả khi một ứng dụng có nhiều Spring ApplicationContext. Không scope nào tự làm đối tượng thread-safe, tự đồng bộ các replica của ứng dụng hoặc tự lưu vào database.

### Hình dung nhanh

```text
HTTP request #1 ── request bean R1 ─┐
HTTP request #2 ── request bean R2 ─┴── cùng HTTP session S1 ── session bean S1
HTTP request #3 ── request bean R3 ──── HTTP session S2 ── session bean S2

                         ServletContext A ── application bean A
WebSocket connection W1 ── websocket bean W1
WebSocket connection W2 ── websocket bean W2
```

Mỗi lần HTTP request mới có request bean mới nếu nó truy cập bean đó. Hai request gửi cùng session ID hợp lệ dùng cùng session-scoped target; không gửi hoặc đổi session ID có thể dẫn đến session khác. Một WebSocket session không phải một HTTP request kéo dài và cũng không mặc nhiên là một HTTP session.

## 2. Điều kiện sử dụng và cơ chế quản lý

Bốn web scope chỉ hoạt động khi Spring có web-aware application context và hạ tầng scope tương ứng. Trong Spring MVC xử lý qua `DispatcherServlet`, Spring đã expose request vào ngữ cảnh hiện tại; ứng dụng Spring Boot dùng `spring-boot-starter-web` thường có sẵn điều kiện này. Nếu xử lý servlet ngoài `DispatcherServlet` (ví dụ một số integration), cấu hình `RequestContextListener` hoặc `RequestContextFilter` để bind request context khi thích hợp.

Trong ứng dụng Java SE chỉ dùng `AnnotationConfigApplicationContext` thông thường, không thể kỳ vọng `request`/`session`/`application` được đăng ký và có ngữ cảnh web để resolve; có thể gặp lỗi unknown scope. Với `websocket`, phải bật hạ tầng Spring messaging cho **STOMP over WebSocket** (ví dụ `@EnableWebSocketMessageBroker`); chỉ mở một endpoint WebSocket thô không bảo đảm có Spring websocket bean scope.

Spring lưu một target theo key trong kho của scope tương ứng: request attributes, session attributes, servlet context attributes hoặc WebSocket/SIMP session attributes. Bean được tạo khi có lần truy cập phù hợp, trừ khi cơ chế khởi tạo đặc biệt buộc truy cập trước đó. Với web-scoped target, các lifecycle callback như `@PostConstruct` và destruction callback có thể được áp dụng lúc tạo/hủy scope; không nên giả định kết thúc scope luôn đồng nghĩa server dừng bình thường (crash có thể bỏ qua callback).

## 3. HTTP request scope

`@RequestScope` là composed annotation cho `@Scope("request")`. Mỗi HTTP request có một target bean riêng; nhiều component cùng sử dụng bean trong một request sẽ dùng chung target đó. Sang HTTP request kế tiếp, target mới được tạo khi có nhu cầu.

```java
package edu.example.scopes;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMarker {
    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

Dùng cho trace/context tạm, memoization chỉ trong request hoặc đối tượng tích lũy kết quả của một lần xử lý. Không dùng để lưu giỏ hàng hay tùy chọn cần tồn tại qua nhiều request. Scope này gắn với **HTTP request**, không phải "một thread": servlet container có thể tái sử dụng thread cho request khác; tác vụ chạy qua `@Async`/`Executor` không tự mang theo request context.

## 4. HTTP session scope

`@SessionScope` là composed annotation cho `@Scope("session")`. Lần đầu bean được dùng trong `HttpSession` S1, Spring tạo target S1; request tiếp theo của cùng S1 tiếp tục sử dụng target S1. Session khác nhận target riêng. Khi session hết hạn hoặc bị `invalidate()`, state gắn với session không còn hợp lệ.

```java
package edu.example.scopes;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class SessionVisits {
    private int visits;

    // Một session có thể nhận nhiều request đồng thời.
    public synchronized int next() {
        return ++visits;
    }
}
```

HTTP session thường được nhận diện qua cookie `JSESSIONID`, nhưng cookie chủ yếu giữ *session identifier*; bean thật ở server/session store. Một tab trình duyệt mới thường dùng chung cookie và vì vậy dùng chung HTTP session với tab cũ trong cùng browser profile. "Mỗi user một bean" là cách diễn đạt dễ nhầm: một người có thể có nhiều session; các người dùng/thiết bị cũng không được định danh bằng bean scope.

Thận trọng với dung lượng session và clustered deployment: nếu session cần replicate/serialize, các object lưu trong session cần phù hợp với cơ chế persistence/serialization của hệ thống; Java `Serializable` chỉ là một phần của vấn đề, không phải bảo đảm session tự được chia sẻ qua mọi server. Đừng coi session scope là lớp bảo mật hay nguồn chân lý cho quyền truy cập.

## 5. Application scope

`@ApplicationScope` là composed annotation cho `@Scope("application")`, với target gắn với một `ServletContext`. Nó phù hợp với trạng thái thực sự chia sẻ giữa mọi request/session **trên một web application instance**. Bean cũng xuất hiện như một attribute trong servlet context.

```java
package edu.example.scopes;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
public class ApplicationVisits {
    private final AtomicLong count = new AtomicLong();

    public long next() {
        return count.incrementAndGet();
    }
}
```

Nhiều request đồng thời có thể cùng gọi `next()`. `AtomicLong` giúp phép tăng đếm thread-safe; nếu dùng `long` thường và `++` không đồng bộ có thể mất cập nhật. Trong cụm hai JVM/pod, mỗi instance có `ServletContext` và bộ đếm riêng. Nếu cần tổng truy cập cho cả cluster, dùng datastore hoặc metrics backend được thiết kế cho việc đó.

So với `singleton`: nếu hệ thống chỉ có một ApplicationContext trong ServletContext thì hành vi quan sát có thể giống nhau, nhưng *ranh giới lưu trữ* khác nhau. `@ApplicationScope` có mục đích rõ ràng khi cần chia sẻ ở ServletContext, trong khi phần lớn service stateless nên để `singleton` mặc định.

## 6. Ví dụ Spring Boot MVC hoàn chỉnh: quan sát ba HTTP scope

Ví dụ sau chạy với **Java 17+, Maven 3.6.3+ và Spring Boot 3.5.6** (Spring Framework 6.2.x). Đây là một dự án tối thiểu, không cần database. Tạo cấu trúc:

```text
spring-scopes-demo/
├── pom.xml
└── src/main/java/edu/example/scopes/
    ├── ScopeDemoApplication.java
    ├── RequestMarker.java
    ├── SessionVisits.java
    ├── ApplicationVisits.java
    └── ScopeController.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-scopes-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`ScopeDemoApplication.java`:

```java
package edu.example.scopes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopeDemoApplication.class, args);
    }
}
```

Ba tệp `RequestMarker.java`, `SessionVisits.java`, `ApplicationVisits.java` dùng **nguyên văn** các class Java đã trình bày ở mục 3, 4, 5; mỗi class có package `edu.example.scopes` và là public class riêng. Tệp `ScopeController.java`:

```java
package edu.example.scopes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScopeController {
    private final RequestMarker requestMarker;
    private final SessionVisits sessionVisits;
    private final ApplicationVisits applicationVisits;

    public ScopeController(RequestMarker requestMarker,
                           SessionVisits sessionVisits,
                           ApplicationVisits applicationVisits) {
        this.requestMarker = requestMarker;
        this.sessionVisits = sessionVisits;
        this.applicationVisits = applicationVisits;
    }

    @GetMapping("/scopes")
    public ScopeInfo getScopes() {
        return new ScopeInfo(
                requestMarker.id(),
                sessionVisits.next(),
                applicationVisits.next()
        );
    }

    public record ScopeInfo(String requestId, int sessionVisits,
                            long applicationVisits) {}
}
```

Controller mặc định là singleton; ba dependency được inject qua proxy do các annotation scope HTTP đã cấu hình. Chỉ khi phương thức gọi đến target, proxy mới resolve bean hiện hành từ scope tương ứng.

Chạy ở thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Mở terminal khác, thử hai request dùng chung cookie/session rồi một request có cookie jar khác:

```bash
curl -s -c jar-a.txt -b jar-a.txt http://localhost:8080/scopes
curl -s -c jar-a.txt -b jar-a.txt http://localhost:8080/scopes
curl -s -c jar-b.txt -b jar-b.txt http://localhost:8080/scopes
```

Nếu ứng dụng vừa khởi động và **chỉ** ba lệnh này gọi endpoint, kết quả có dạng (UUID là **ví dụ minh họa**, không cố định):

```json
{"requestId":"2d50fe8b-0d58-4a8e-b514-d363303a65c0","sessionVisits":1,"applicationVisits":1}
{"requestId":"8876aa20-2963-408e-b01d-dfa670aa94a4","sessionVisits":2,"applicationVisits":2}
{"requestId":"4b079e10-eaa4-431d-9b39-cc11c3fc3139","sessionVisits":1,"applicationVisits":3}
```

Giải thích: `requestId` khác nhau sau mỗi HTTP request; `sessionVisits` tăng lên 2 khi cùng jar A và bắt đầu từ 1 ở jar B; `applicationVisits` tăng trên toàn bộ instance. Nếu jar B đã tồn tại, có nhiều client gọi đồng thời hoặc ứng dụng đã nhận request trước đó, số đếm cụ thể có thể khác. Xóa hai file jar để bắt đầu thử hai HTTP session mới; restart app để reset bộ đếm application trong RAM.

**Lưu ý code:** Các snippet mục 3–5 là source đầy đủ của ba tệp được liệt kê, không cần thêm `@Bean` hoặc cấu hình request/session scope cho mẫu Boot MVC này. Không dùng `javac` thuần cho dự án vì cần dependency Spring; Maven sẽ biên dịch và chạy bằng plugin.

## 7. WebSocket scope với STOMP messaging

`websocket` scope trong Spring gắn với **phiên WebSocket của hạ tầng STOMP messaging**, không gắn với từng message. Khi cùng kết nối gửi nhiều message, target bean WebSocket vẫn giữ state; kết nối khác có target khác. Spring lưu bean trong session attributes của thông điệp STOMP/SIMP và thu hồi khi phiên kết thúc.

Bổ sung vào phần `<dependencies>` của `pom.xml` ở ví dụ trên:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>
```

Tạo `StompConfig.java`:

```java
package edu.example.scopes;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
```

Tạo `SocketCounter.java`:

```java
package edu.example.scopes;

import java.util.UUID;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SocketCounter {
    private final String connectionMarker = UUID.randomUUID().toString();
    private int count;

    public synchronized int next() {
        return ++count;
    }

    public String marker() {
        return connectionMarker;
    }
}
```

Tạo `StompCounterController.java`:

```java
package edu.example.scopes;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class StompCounterController {
    private final SocketCounter counter;

    public StompCounterController(SocketCounter counter) {
        this.counter = counter;
    }

    @MessageMapping("/count")
    @SendTo("/topic/counts")
    public CountReply count() {
        return new CountReply(counter.marker(), counter.next());
    }

    public record CountReply(String connectionMarker, int count) {}
}
```

Dùng một STOMP client: kết nối WebSocket tới `ws://localhost:8080/ws`; subscribe `/topic/counts`; gửi hai STOMP `SEND` message đến `/app/count`. Với một kết nối mới, phản hồi thường có cùng `connectionMarker` và `count` lần lượt bằng 1, 2; ngắt kết nối, mở WebSocket session mới và gửi tiếp thì `count` của target mới bắt đầu từ 1. `/topic/counts` là **broadcast**: các subscriber khác cũng sẽ thấy message; ví dụ chỉ gửi dữ liệu thử nghiệm, không broadcast thông tin phiên hoặc người dùng nhạy cảm trong hệ thống thực tế.

Mẫu trên dùng cú pháp chạy trên Spring Framework 6.2 và 7.x. Từ **Spring Framework 7.0**, có thể thay `@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)` bằng `@WebSocketScope` (import `org.springframework.web.socket.config.annotation.WebSocketScope`); annotation mới mặc định tạo class-based scoped proxy. **Không dùng `@WebSocketScope` với Spring Framework 6.2**, vì phiên bản đó chưa có annotation này.

Một socket thô với `WebSocketHandler` đơn lẻ không đủ để áp dụng trực tiếp ví dụ `@MessageMapping`/STOMP và scope này. `HttpSession` tồn tại lúc handshake cũng không đồng nghĩa WebSocket session; xác thực và ánh xạ user giữa hai giao thức là trách nhiệm khác với bean scope.

## 8. Scoped proxy và inject bean ngắn hạn vào singleton

Ví dụ MVC inject `RequestMarker`, `SessionVisits`, `ApplicationVisits` vào controller singleton. Nếu inject trực tiếp *target* ngắn hạn lúc singleton khởi tạo, Spring có thể không tìm thấy request/session đang hoạt động, hoặc vô tình giữ một target của request đầu tiên. Cách thông dụng là **scoped proxy**.

Luồng thực tế:

```text
Singleton ScopeController (tồn tại lâu)
        |
        +--> proxy RequestMarker (reference ổn định)
                    |
                    +-- HTTP request X --> target RequestMarker X
                    +-- HTTP request Y --> target RequestMarker Y

        +--> proxy SessionVisits
                    |
                    +-- HTTP session A --> target SessionVisits A
                    +-- HTTP session B --> target SessionVisits B
```

`@RequestScope`, `@SessionScope` và `@ApplicationScope` mặc định có `proxyMode = ScopedProxyMode.TARGET_CLASS`, nên mẫu code ở trên inject được class cụ thể. Cấu hình tường minh tương đương:

```java
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
```

`TARGET_CLASS` dùng class-based proxy; class `final` hoặc method `final` không phù hợp để proxy bằng cách subclass/intercept. Nếu dùng `ScopedProxyMode.INTERFACES`, injection point cần thích hợp với interface mà proxy implement. Bean proxy cũng không giúp gọi target trong thread không có scope tương ứng.

Lựa chọn khác là inject `ObjectProvider<T>` và tra target **tại thời điểm sử dụng**; ví dụ minh họa sau là đoạn class độc lập về mặt ý tưởng, thay cho `RequestMarker` có proxy ở trên:

```java
// Đăng ký component ở request scope KHÔNG tạo scoped proxy:
@Component
@RequestScope(proxyMode = ScopedProxyMode.NO)
class RequestValue {
    public String value() { return "data in current request"; }
}

@Service
class CurrentRequestService {
    private final ObjectProvider<RequestValue> provider;

    CurrentRequestService(ObjectProvider<RequestValue> provider) {
        this.provider = provider;
    }

    public String read() {
        return provider.getObject().value();
    }
}
```

Snippet này cần các import Spring tương ứng (`Component`, `Service`, `RequestScope`, `ScopedProxyMode`, `ObjectProvider`) và phải chạy trong web-aware context; nó minh họa cách lookup, không phải tệp Java chạy độc lập. Quan trọng: `provider.getObject()` phải được gọi **trong HTTP request đang hoạt động**, không gọi một lần trong constructor rồi cache vào field singleton. Một số tình huống cần đọc trực tiếp request/session có thể inject `HttpServletRequest` hoặc truy cập request attributes qua API phù hợp, nhưng đó là lựa chọn về phụ thuộc web API, không thay đổi quy tắc scope.

## 9. Vòng đời và cleanup

| Sự kiện | Request scope | Session scope | Application scope | WebSocket scope |
| --- | --- | --- | --- | --- |
| Lần đầu truy cập bean | Tạo trong request | Tạo trong HTTP session | Tạo trong ServletContext | Tạo trong WebSocket session |
| Nhiều lần gọi cùng scope | Dùng lại target | Dùng lại target | Dùng lại target | Dùng lại target |
| Request HTTP kế tiếp | Target khác | Có thể cùng target nếu cùng session | Cùng target trên instance đó | Không liên quan trực tiếp |
| Kết thúc scope | Kết thúc request | Invalidate/timeout session | ServletContext dừng | Đóng/kết thúc socket session |

Khi Spring quản lý destruction callback cho scope, `@PreDestroy`/`DisposableBean` được gọi theo lifecycle thông thường. Chẳng hạn, target websocket thường được hủy khi kết nối kết thúc. Không dùng `@PreDestroy` để đảm bảo lưu dữ liệu kinh doanh quan trọng: session timeout, restart bất thường hoặc crash không thay thế transaction/persistence.

Nếu cần chủ động kết thúc HTTP session, dùng `request.getSession(false)` để lấy session đang tồn tại (nếu có), sau đó `session.invalidate()` nếu phù hợp với luồng logout. `getSession(false)` có thể trả `null`; `getSession()` có thể tạo session mới. Không truy cập bean `@SessionScope` sau invalidate trong cùng đường xử lý và giả định nó vẫn là target cũ.

## 10. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `No Scope registered for scope name 'request'` hoặc tương tự | Dùng container không nhận biết web / thiếu đăng ký scope | Chạy trong Spring MVC web context, kiểm tra cấu hình context |
| `No thread-bound request found` | Gọi request/session-scoped target bên ngoài HTTP request có bind context | Chỉ resolve trong request; chuyển dữ liệu cần thiết qua tham số vào background task |
| Scope ngắn hạn không inject được vào singleton khi startup | Không có proxy/provider hoặc bean đòi target quá sớm | Dùng scoped proxy hoặc `ObjectProvider`; tránh gọi method của target trong constructor singleton |
| State session mất sau mỗi HTTP call | HTTP client không gửi lại session cookie / session expired / ứng dụng chuyển instance không chia sẻ session | Dùng cookie jar, kiểm tra timeout và chiến lược session store |
| Hai tab trình duyệt thấy cùng state | Hai tab cùng HTTP session/cookie | Nếu thực sự cần state theo tab, định nghĩa định danh tab riêng thay vì chỉ dựa `@SessionScope` |
| Mutable application bean cập nhật sai | Shared object được truy cập đồng thời | Dùng immutable data, `AtomicLong`, lock hoặc datastore phù hợp |
| WebSocket bean không resolve | Chưa bật STOMP broker hoặc gọi ngoài SIMP message context | Kiểm tra `@EnableWebSocketMessageBroker`, endpoint, `@MessageMapping`, message headers và phạm vi resolve |
| `@WebSocketScope` không compile | Spring Framework 6.2 chưa cung cấp annotation đó | Dùng `@Scope("websocket", proxyMode = TARGET_CLASS)` trên 6.2 |
| Proxy class gây lỗi với `final` method/class | Class-based proxy cần subclass/override | Dùng class/method có thể proxy hoặc interface-based proxy đúng kiểu |
| State scope biến mất sau deploy/restart | State nằm trong RAM/session store chưa cấu hình | Persist dữ liệu bắt buộc hoặc dùng shared backing store |

**Các nhầm lẫn cần tránh:**
1. `session` là phiên HTTP, không mặc nhiên là user đăng nhập; `websocket` là phiên kết nối STOMP, không phải HTTP session.
2. `application` không đồng nghĩa distributed global singleton; đa instance có state riêng.
3. Scope quản lý *địa chỉ lưu trữ/vòng đời bean*, không thay cho đồng bộ thread, transaction, security hay data persistence.
4. Scoped proxy giữ reference ổn định trong singleton nhưng target được chọn khi gọi method; đừng đọc/giữ target thật ngoài vòng đời của nó.
5. Web scope trong Spring Servlet stack không đồng nhất với request context của ứng dụng WebFlux/Reactor; không áp dụng máy móc cơ chế `ThreadLocal` sang reactive pipeline.

## 11. Tự kiểm tra kiến thức

1. Gửi ba request A1, A2 (cùng `JSESSIONID`) và B1 (cookie khác) vào endpoint. Bean nào đổi ở cả ba lần, bean nào lặp lại ở A1/A2, bean nào chung cả ba trên một JVM?
2. Một singleton service cần request ID hiện tại để log. Vì sao giữ request bean thật trong field singleton là sai? Viết giải pháp qua scoped proxy hoặc provider.
3. Hai pod xử lý cùng một ứng dụng. Nếu bean `@ApplicationScope` giữ bộ đếm trong RAM, vì sao kết quả của hai pod khác nhau?
4. Một kết nối STOMP gửi 10 frame vào `/app/count`. WebSocket-scoped counter có mấy target được dùng? Khi client reconnect, điều gì thay đổi?
5. Tại sao `@SessionScope` không nên được hiểu là "một instance cho một user"?

**Đáp án kiểm chứng:** (1) Request bean khác ở cả ba request; session bean chung cho A1/A2, khác B1; application bean chung trong cùng ServletContext. (2) Singleton sống lâu hơn request, phải resolve target tại runtime. (3) Mỗi pod có ServletContext và memory riêng. (4) Một target cho kết nối nếu chỉ một scope context và bean được truy cập, reconnect tạo target mới. (5) User có thể có nhiều session, một session có thể không có user đăng nhập.

## Tài liệu chính thức

- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — STOMP WebSocket Scope: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/scope.html
- Spring Framework 6.2 — WebSocket Scope (cú pháp `@Scope`): https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/scope.html
- Spring Framework — Scoped bean configuration: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html

