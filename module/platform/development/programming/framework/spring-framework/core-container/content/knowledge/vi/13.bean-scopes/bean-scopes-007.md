# Điều kiện cần có của context hỗ trợ phạm vi web trong Spring Framework

## Mục tiêu

Hiểu khi nào các bean thuộc phạm vi `request`, `session`, `application` và `websocket` có thể hoạt động; phân biệt **web-aware Spring ApplicationContext** với **HTTP request hiện hành**; cấu hình đúng cho Spring MVC và cho request đi ngoài `DispatcherServlet`; sử dụng web-scoped bean an toàn trong singleton và chẩn đoán lỗi thường gặp.

## 1. “Context hỗ trợ phạm vi web” có nghĩa gì?

Spring IoC quản lý bean trong `ApplicationContext`. Các scope cơ bản như `singleton` và `prototype` dùng được trong ứng dụng Java thuần. Bốn web scope yêu cầu container có khả năng tương tác với hạ tầng web:

| Scope | Đơn vị chia sẻ bean | Điều kiện sử dụng |
| --- | --- | --- |
| `request` | Một HTTP request | Web-aware `ApplicationContext` và request đang được Spring nhận diện tại thời điểm truy cập |
| `session` | Một HTTP session | Web-aware context và HTTP session/request thích hợp |
| `application` | Một `ServletContext` | Servlet-aware application context đã liên kết với `ServletContext` |
| `websocket` | Một WebSocket session theo cơ chế hỗ trợ của Spring, điển hình STOMP over WebSocket | Hạ tầng WebSocket/STOMP và session scope tương ứng đang hoạt động |

`application` **khác** `singleton`: một bean `singleton` thuộc **một** Spring IoC container, còn bean `application` thuộc **một** `ServletContext` (có thể được nhiều Spring web context trong cùng ứng dụng nhìn thấy như ServletContext attribute).

Một web-aware context không chỉ là “project có dependency `spring-web`”, “đã đặt `@RequestScope`” hay “đang chạy trong JVM có cổng HTTP”. Spring phải khởi tạo loại context phù hợp và đăng ký các `Scope` tương ứng. Với web request/session, luồng thực thi còn cần truy cập được `RequestAttributes` của request hiện tại.

### Hai điều kiện độc lập cần phân biệt

1. **Lúc khởi tạo container:** web-aware context được thiết lập, đăng ký web scopes và liên kết với web runtime tương ứng. Ví dụ trong ứng dụng Servlet MVC là `WebApplicationContext` (có thể có context gốc và context con của `DispatcherServlet`).
2. **Lúc truy cập bean:** đối với `request`/`session`, phải có HTTP request hợp lệ mà Spring đã gắn vào ngữ cảnh xử lý hiện tại. Nếu một job nền gọi scoped bean khi không có request, container web vẫn có thể tồn tại nhưng **scope của request hiện không active**.

Sơ đồ:

```text
Servlet container
  └─ ServletContext
      ├─ WebApplicationContext (đăng ký web scopes)
      │   └─ bean definitions: singleton, request, session, application, ...
      └─ HTTP request → DispatcherServlet / RequestContextFilter / RequestContextListener
                           └─ RequestAttributes gắn với thread xử lý
                               ├─ request-scoped target hiện hành
                               └─ session-scoped target của HTTP session
```

Đặc biệt: có **bean definition** của một web-scoped bean trong container chưa có nghĩa là target bean đã được tạo. Target có thể chỉ được tạo khi có request/session đang hoạt động và có lời gọi thực sự đến nó.

## 2. Container và hạ tầng tối thiểu

### 2.1. Chọn đúng ApplicationContext

Trong mô hình Spring MVC dựa trên Jakarta Servlet:

- `WebApplicationContext` là giao diện `ApplicationContext` có thể truy cập môi trường Servlet; các triển khai cấu hình web như `AnnotationConfigWebApplicationContext`, `XmlWebApplicationContext` được tạo với lifecycle phù hợp.
- `DispatcherServlet` sử dụng `WebApplicationContext`; có thể có root context do `ContextLoaderListener` quản lý và servlet-specific child context. Không phải ứng dụng nào cũng cần tự cấu hình cả hai.
- Với Spring Boot chạy **Servlet web application** (ví dụ có `spring-boot-starter-web` và dùng `SpringApplication.run`), Boot tự thiết lập servlet web context và đăng ký MVC dispatcher cần thiết. Bạn thường chỉ cần khai báo bean với `@RequestScope`, `@SessionScope` hoặc `@ApplicationScope`.

Ví dụ một context độc lập:

```java
// Minh họa context KHÔNG có môi trường web, không phải ứng dụng chạy HTTP.
try (var context = new org.springframework.context.annotation.AnnotationConfigApplicationContext()) {
    context.registerBean("greeting", String.class, () -> "hello");
    context.refresh();
    System.out.println(context.getBean("greeting"));
}
```

Container trên phù hợp với bean thông thường; nó không tự cung cấp request/session web scopes. Nếu đăng ký bean với `@Scope("request")` rồi yêu cầu Spring tạo target qua context loại này, sẽ gặp lỗi liên quan **scope name không được đăng ký** (có thể được bọc trong `BeanCreationException`).

**Không** khắc phục bằng cách tạo tùy tiện một `SimpleThreadScope` dưới tên `request`: “mỗi thread” không đồng nghĩa “mỗi HTTP request”; servlet container tái sử dụng thread, còn xử lý bất đồng bộ có thể đổi thread.

### 2.2. Đảm bảo HTTP request được Spring expose

Trong Spring MVC, `DispatcherServlet` đã expose request và các trạng thái cần thiết. Request đi qua nó **không cần** đăng ký thêm `RequestContextListener` hoặc `RequestContextFilter` chỉ để kích hoạt scope.

Nếu một HTTP request xử lý **ngoài** `DispatcherServlet` (ví dụ servlet hoặc một framework MVC khác cần dùng Spring web-scoped bean), cấu hình **một** trong hai:

- `RequestContextListener`: listener thuộc Servlet API, gắn và dọn ngữ cảnh request cho listener callbacks.
- `RequestContextFilter`: servlet filter gắn request context khi chuỗi filter được gọi; có thể phù hợp khi cần ánh xạ URL/dispatcher types hoặc không thể dùng listener.

Ví dụ web.xml **chọn listener** (ứng dụng Servlet truyền thống):

```xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <listener>
        <listener-class>org.springframework.web.context.request.RequestContextListener</listener-class>
    </listener>
</web-app>
```

Ví dụ **phương án thay thế dùng filter**, không phải phần bắt buộc phải thêm cùng listener:

```xml
<filter>
    <filter-name>requestContextFilter</filter-name>
    <filter-class>org.springframework.web.filter.RequestContextFilter</filter-class>
</filter>
<filter-mapping>
    <filter-name>requestContextFilter</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
```

Đoạn filter ở trên chỉ là **phần cấu hình đặt bên trong web.xml hợp lệ**, không phải một tài liệu XML độc lập. Hãy kiểm tra ánh xạ URL/dispatcher types khi cần hỗ trợ error/async dispatch. Trên Spring Framework 6+/Spring Boot 3+, API Servlet là `jakarta.servlet.*`; không trộn với `javax.servlet.*` của các phiên bản cũ.

## 3. Cách Spring xác định request/session hiện hành

Trong xử lý Servlet, Spring biểu diễn dữ liệu HTTP request bằng `ServletRequestAttributes` và truy cập qua `RequestContextHolder`. `DispatcherServlet`, `RequestContextFilter` hoặc `RequestContextListener` liên kết dữ liệu đó với thread đang phục vụ request, sau đó dọn liên kết đúng lifecycle.

Khi một bean dùng `request` được yêu cầu, implementation của scope tìm request attributes tương ứng, tạo hoặc tìm target của bean trong request và đăng ký callback dọn dẹp khi request kết thúc. Với `session`, target gắn với session tương ứng, tiếp tục tồn tại qua nhiều request của cùng session cho tới khi session không còn hợp lệ (phụ thuộc lifecycle/session management).

Lưu ý về thời điểm:

- **Container đã khởi động** không có nghĩa mọi thread đều có HTTP request.
- **Lấy proxy** lúc khởi động có thể hợp lệ; **gọi proxy để lấy target** ngoài request mới gây lỗi.
- Hai request từ hai client khác nhau có target `request` riêng. Hai request trong cùng một HTTP session thường chia sẻ target `session`, nếu cookie/session id được duy trì.
- HTTP request mới do cùng thread pool worker phục vụ vẫn phải có target `request` mới; scope không được ràng buộc với danh tính thread.

Có thể kiểm tra ngữ cảnh hiện hành khi chẩn đoán:

```java
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;

RequestAttributes attributes = RequestContextHolder.getRequestAttributes();
if (attributes == null) {
    // Thread này hiện không có request attributes được Spring gắn.
}
```

Đây là **đoạn minh họa đặt trong một method**, không phải file Java độc lập. `getRequestAttributes()` trả `null` nếu không có binding; còn `currentRequestAttributes()` có thể ném `IllegalStateException`. Đừng sử dụng `RequestContextHolder` như kho lưu trạng thái nghiệp vụ tùy ý hoặc cache sống lâu.

## 4. Ví dụ hoàn chỉnh: @RequestScope hoạt động với Spring Boot MVC

Ví dụ sau dùng **Java 17+**, Spring Boot 3.3.13 (Servlet MVC) và Maven. Tạo thư mục:

```text
web-scope-demo/
├── pom.xml
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── RequestToken.java
    └── ScopeController.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>web-scope-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

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

**src/main/java/demo/DemoApplication.java**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**src/main/java/demo/RequestToken.java**

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestToken {
    private static final AtomicLong SEQUENCE = new AtomicLong();
    private final long id = SEQUENCE.incrementAndGet();

    public long id() {
        return id;
    }
}
```

**src/main/java/demo/ScopeController.java**

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScopeController {
    private final RequestToken requestToken;

    public ScopeController(RequestToken requestToken) {
        this.requestToken = requestToken;
    }

    @GetMapping(value = "/scope", produces = MediaType.TEXT_PLAIN_VALUE)
    public String scope() {
        long first = requestToken.id();
        long second = requestToken.id();
        return "first=" + first + ",second=" + second;
    }
}
```

Chạy trong thư mục `web-scope-demo`:

```bash
mvn spring-boot:run
```

Mở **terminal thứ hai** và gọi lần lượt (ứng dụng mới chạy, chưa có request nào đến endpoint):

```bash
curl -s http://localhost:8080/scope
curl -s http://localhost:8080/scope
```

Mỗi lệnh nhận một body văn bản, **không kèm newline**:

```text
first=1,second=1
first=2,second=2
```

Các dòng output trên biểu diễn **hai response liên tiếp**, mỗi response là một dòng logic; khi in bằng `curl -s` trực tiếp trong cùng terminal, hai body có thể nối sát nhau nếu terminal không tự chèn newline. Giá trị bộ đếm giả định ứng dụng mới khởi động và hai request này là hai request đầu tiên tạo `RequestToken`.

Vì sao code chạy được dù `ScopeController` mặc định là singleton?

- `@RequestScope` khai báo scope `request` và mặc định dùng **class-based scoped proxy** (`ScopedProxyMode.TARGET_CLASS`).
- Spring inject một **proxy** vào controller singleton; proxy không lưu một `RequestToken` cố định.
- Mỗi lần `requestToken.id()` chạy trong HTTP request, proxy phân giải target của **request hiện tại**. Hai lần gọi trong cùng request dùng cùng một target; request kế tiếp nhận target mới.
- Khi request hoàn tất, request-scoped target hết vòng đời của request; controller singleton còn sống.

**Thử nghiệm đối chứng:** nếu thay `@RequestScope` bằng `@Scope("request")` mà không cấu hình proxy và vẫn constructor-inject vào singleton eager, Spring thường cố resolve target quá sớm khi khởi tạo controller, dẫn tới lỗi request scope chưa active. Có thể sửa bằng `@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)`, giữ `@RequestScope`, hoặc inject `ObjectProvider<RequestToken>` rồi lấy target tại thời điểm có request.

## 5. Inject web-scoped bean vào singleton một cách đúng đắn

Hai cách phổ biến:

### A. Scoped proxy

```java
@Component
@RequestScope
class RequestState {
    public String value() {
        return "per-request";
    }
}

@Service
class BusinessService {
    private final RequestState state;

    BusinessService(RequestState state) {
        this.state = state; // Nhận proxy an toàn lúc khởi tạo singleton.
    }

    String handle() {
        return state.value(); // Target được tìm trong request đang active.
    }
}
```

Đây là **đoạn minh họa hai lớp**, đặt trong một package của ứng dụng Spring MVC. Đừng giả định `handle()` chạy hợp lệ từ scheduler hay `@PostConstruct` của singleton: proxy vẫn đòi request active ở lúc gọi.

### B. ObjectProvider (lazy lookup)

```java
@Service
class BusinessService {
    private final org.springframework.beans.factory.ObjectProvider<RequestState> states;

    BusinessService(org.springframework.beans.factory.ObjectProvider<RequestState> states) {
        this.states = states;
    }

    String handle() {
        return states.getObject().value();
    }
}
```

`ObjectProvider` trì hoãn việc lấy bean cho tới lúc cần; gọi `getObject()` vẫn yêu cầu scope đang active. Nếu dùng `@Scope("request")` không proxy, cách này hữu ích khi không muốn tạo scoped proxy. Những ví dụ ở mục này yêu cầu đủ import Spring tương ứng và nằm trong một ứng dụng web đã cấu hình; ví dụ chạy đầy đủ là ở mục 4.

Không giữ tham chiếu đến **target** web-scoped bean hoặc `HttpServletRequest` bên trong static field, cache dùng chung hay singleton ngoài vòng đời của request/session. Với class-based proxy, chú ý các hạn chế thông thường khi dùng lớp/method `final`, `private`; cân nhắc interface proxy hoặc `ObjectProvider` khi phù hợp.

## 6. Phạm vi session, application và websocket cần gì thêm?

### HTTP session

```java
@Component
@org.springframework.web.context.annotation.SessionScope
class Cart {
    private final java.util.List<String> items = new java.util.ArrayList<>();

    public void add(String item) {
        items.add(item);
    }

    public java.util.List<String> items() {
        return java.util.List.copyOf(items);
    }
}
```

Bean tồn tại theo **HTTP session**, không theo user account toàn hệ thống. Client phải giữ session identifier (thường là cookie); khi session bị invalidate/expire sẽ không còn cùng instance. Với nhiều request đồng thời của cùng session, bean có thể được truy cập đồng thời: cần thiết kế đồng bộ an toàn nếu có mutable state. Trong hệ thống phân tán, chiến lược chia sẻ/persist session và serialization của đối tượng session phụ thuộc hạ tầng triển khai; web scope tự nó không giải quyết vấn đề cluster.

### Servlet application

```java
@Component
@org.springframework.web.context.annotation.ApplicationScope
class AppPreferences {
    public String localeDefault() {
        return "vi-VN";
    }
}
```

Bean thuộc `ServletContext` của web application. Phù hợp với trạng thái cấp ứng dụng Servlet thực sự, nhưng cần thận trọng nếu có nhiều Spring contexts trong cùng `ServletContext` hoặc dữ liệu mutable được cập nhật đồng thời. Scope `application` **không tự biến bean thành biến toàn cục của tất cả JVM/replica**.

### WebSocket

Scope `websocket` trong Spring gắn với WebSocket session (đặc biệt trong hạ tầng messaging/STOMP over WebSocket). Phải có kết nối/session và hạ tầng message processing phù hợp. Tạo bean `@Scope("websocket")` trong ứng dụng chỉ xử lý HTTP REST **không đủ** để kích hoạt scope WebSocket. Request HTTP ban đầu của handshake và vòng đời WebSocket session là hai phạm vi khác nhau.

## 7. Các tình huống dễ gây nhầm lẫn

| Tình huống | Kết quả/biện pháp |
| --- | --- |
| `new AnnotationConfigApplicationContext(...)` rồi dùng `@RequestScope` | Context Java thuần chưa có web scopes; dùng web-aware context khi thực sự chạy Servlet web app |
| Ứng dụng Spring Boot đặt ở chế độ non-web (chẳng hạn `WebApplicationType.NONE`) | Không có servlet request hiện hành; không dùng request/session scoped target như trong MVC |
| Có `WebApplicationContext` nhưng gọi bean `request` từ `@Scheduled` hoặc thread nền | Scope không active trong thread đó; truyền dữ liệu cần thiết thành tham số/job payload |
| Request MVC đi qua `DispatcherServlet` | DispatcherServlet đã expose request; không bắt buộc thêm listener/filter |
| Servlet/JSF request không qua `DispatcherServlet` | Cần `RequestContextListener` hoặc `RequestContextFilter` được map đúng |
| Inject trực tiếp `@Scope("request")` không proxy vào singleton eager | Target có thể bị resolve trước khi có request; dùng `@RequestScope` có proxy hoặc `ObjectProvider` |
| Lưu mutable session bean và có hai HTTP requests song song cùng session | Cùng instance có thể bị truy cập đồng thời; tránh race conditions |
| Khởi tạo background task từ request rồi dùng scoped proxy sau khi response đã kết thúc | Không thể dựa vào request context cũ; chuyển dữ liệu bất biến cần thiết sang task |
| Test tạo Spring context thuần rồi gọi request bean | Dùng `MockHttpServletRequest` + `ServletRequestAttributes` cho unit test có kiểm soát hoặc integration test có Spring MVC đúng hạ tầng |
| Dùng reactive Spring WebFlux | Không bê nguyên giả định Servlet thread binding; dùng cơ chế context và bean lifecycle phù hợp WebFlux/Reactor |

### Cẩn thận với thread pool, async và ThreadLocal

`RequestContextHolder` thường ràng buộc request attributes với thread xử lý. Spring MVC hỗ trợ nhiều luồng async dispatch có cơ chế thiết lập lại context phù hợp, nhưng **không suy ra rằng mọi CompletableFuture, ExecutorService, scheduler hoặc thread mới tự động có request context**.

`RequestContextFilter` có tùy chọn `threadContextInheritable`; mặc định là `false`. Bật `true` bừa bãi đặc biệt nguy hiểm với thread pool có thể tái sử dụng thread: dữ liệu request từ một công việc có thể bị giữ hoặc lộ trong công việc khác. Thay vì truyền request-bound bean qua thread, hãy truyền một DTO/giá trị cần dùng; nếu cần context propagation thì chọn cơ chế được Spring hỗ trợ theo đúng mô hình async.

### Một lỗi có hai nguyên nhân khác nhau

**Lỗi scope chưa đăng ký** (chẳng hạn `No Scope registered for scope name 'request'`) nghĩa là đang dùng context/bean factory chưa thiết lập web scope.

**Lỗi scope đã đăng ký nhưng không active** (chẳng hạn `Scope 'request' is not active for the current thread`) nghĩa là đã biết scope nhưng thiếu request attributes trong thời điểm/thread truy cập. Cả hai đều có thể nổi lên dưới dạng `BeanCreationException` khi Spring tạo bean; phải đọc **root cause** để chọn cách sửa phù hợp.

## 8. Checklist triển khai và kiểm thử

1. Xác định ứng dụng **Servlet MVC** hay **reactive WebFlux**; bài này tập trung vào Servlet MVC.
2. Xác nhận container sử dụng web-aware `ApplicationContext` và Servlet environment có cấu hình hợp lệ.
3. Chọn `@RequestScope`, `@SessionScope`, `@ApplicationScope` đúng theo lifetime mong muốn; chỉ dùng `websocket` khi có hỗ trợ tương ứng.
4. Với request qua `DispatcherServlet`: dùng cấu hình có sẵn. Với đường xử lý ngoài dispatcher: đăng ký và map `RequestContextListener` hoặc `RequestContextFilter` đúng phạm vi.
5. Khi inject web-scoped bean vào singleton: dùng scoped proxy hoặc provider/lazy lookup; không resolve target trong constructor init/scheduler không có request.
6. Kiểm thử hai HTTP requests độc lập, hai requests cùng session và request từ client không mang cookie; quan sát instance được tái sử dụng theo đúng scope.
7. Kiểm thử đường đi ngoài dispatcher, async jobs, thread pool; xử lý mất context hoặc truyền dữ liệu cần thiết đúng cách.
8. Nếu thất bại, kiểm tra **đúng context có đăng ký scope hay chưa**, rồi **đúng thread/request có request attributes hay chưa**.

## 9. Câu hỏi tự kiểm tra

**Hỏi:** Có thể tạo `@RequestScope` bean bằng `AnnotationConfigApplicationContext` không?  
**Đáp:** Annotation không tự kích hoạt web scope. Context Java thuần không có cơ sở tạo target của request-scoped bean; phải dùng môi trường web-aware hoặc thiết lập Scope phù hợp trong kiểm thử riêng biệt.

**Hỏi:** Khi đã chạy Spring MVC, có phải luôn thêm `RequestContextListener` không?  
**Đáp:** Không. `DispatcherServlet` tự gắn request context cho các request mà nó xử lý. Listener/filter cần xem xét khi xử lý Servlet request ngoài dispatcher.

**Hỏi:** Tại sao singleton controller vẫn inject được request bean?  
**Đáp:** Vì `@RequestScope` mặc định sử dụng scoped proxy. Singleton giữ proxy, còn target được phân giải khi gọi trong request hiện hành.

**Hỏi:** Khởi động thành công có bảo đảm mọi chỗ đều gọi được request bean?  
**Đáp:** Không. Request scope chỉ active trong môi trường xử lý request thích hợp, không mặc nhiên active ở scheduler, background worker hay lúc startup.

**Hỏi:** `application` có nghĩa là chia sẻ qua các pod/JVM không?  
**Đáp:** Không. Scope này gắn với `ServletContext` của một web application, không phải distributed store.

## Tài liệu chuẩn

- Spring Framework Reference – [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html), đặc biệt phần “Request, Session, Application, and WebSocket Scopes” và “Initial Web Configuration”.
- Spring Framework Reference – [DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html).
- Spring Framework Javadoc – [RequestContextFilter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/RequestContextFilter.html).

