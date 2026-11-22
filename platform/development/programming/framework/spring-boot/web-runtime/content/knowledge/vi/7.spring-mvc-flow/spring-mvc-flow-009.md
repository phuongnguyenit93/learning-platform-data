# RequestContext, ServletRequestAttributes và phạm vi dữ liệu theo yêu cầu

Trong một request HTTP của **Spring MVC trên Servlet stack**, controller, service, filter, view và phần xử lý lỗi đôi khi cần truy cập thông tin chỉ thuộc về request hiện tại: ngôn ngữ, đường dẫn, correlation ID, các giá trị trung gian hay một đối tượng tạm chỉ sống trong request đó. Spring cung cấp các abstraction để quản lý thông tin này mà không phải đưa toàn bộ `HttpServletRequest` qua từng tầng nghiệp vụ.

Ba tên dễ gây nhầm lẫn:

1. **`org.springframework.web.servlet.support.RequestContext`** là đối tượng tiện ích cho ngữ cảnh MVC/view, chẳng hạn locale, message, URL có context path và binding errors. Nó không phải biến toàn cục chứa request.
2. **`org.springframework.web.context.request.RequestContextHolder`** là lớp giữ `RequestAttributes` gắn với thread đang xử lý request. Trong MVC, `DispatcherServlet` thường thiết lập ngữ cảnh này.
3. **`org.springframework.web.context.request.ServletRequestAttributes`** là implementation của `RequestAttributes` dựa trên Jakarta Servlet, bao bọc `HttpServletRequest` và có thể bao bọc `HttpServletResponse`. Nó cho phép đọc/ghi các thuộc tính thuộc request hoặc session.

Bài học này giải thích cách những đối tượng trên phối hợp, vòng đời của **request scope**, cách sử dụng trong controller/service, lý do cần scoped proxy và các giới hạn khi chuyển việc sang thread khác. Ví dụ dùng **Spring Boot 3.3.x, Spring MVC, Java 21** và namespace `jakarta.servlet.*` của Spring Framework 6.

## 1. Một request đi qua những đâu?

Luồng đồng bộ thường gặp:

~~~text
HTTP client
    |
    v
Tomcat / Servlet container
    |
    v
Servlet Filter chain
    |
    v
DispatcherServlet
    |-- thiết lập ngữ cảnh LocaleContextHolder / RequestContextHolder
    |-- chọn HandlerMapping và HandlerAdapter
    |
    v
Controller -> Service -> Repository
    |             |
    |             +--> có thể đọc RequestAttributes hiện hành
    |                  nếu đang ở thread được Spring bind context
    |
    v
HttpMessageConverter hoặc ViewResolver / View
    |
    v
HTTP response
    |
    v
Dọn / khôi phục thread-bound context sau dispatch
~~~

Trong `DispatcherServlet`, Spring chuẩn bị những thông tin gắn với request trước khi chạy handler, rồi khôi phục trạng thái context cũ sau khi xử lý. Các request khác nhau có thể được xử lý bởi cùng một **worker thread** ở những thời điểm khác nhau. Việc dọn context đúng vòng đời là yêu cầu quan trọng để không rò rỉ dữ liệu giữa request.

Sơ đồ là luồng khái niệm. Servlet async, async dispatch, exception handling, custom filter và executor có thể tạo ra nhiều lần dispatch và thay đổi thread thực thi.

**Phạm vi request khác phạm vi thread:** đối tượng request-scoped có vòng đời theo HTTP request; `ThreadLocal` trong `RequestContextHolder` chỉ là cơ chế tìm ra ngữ cảnh hiện hành của thread đang xử lý. Không nên coi “request scope” và “thread scope” là một.

## 2. Bảng phân biệt các API quan trọng

| Loại | Package / class | Trách nhiệm | Có đại diện cho request hiện hành không? |
| --- | --- | --- | --- |
| MVC view helper | `org.springframework.web.servlet.support.RequestContext` | Locale, message, URL có context path, binding errors/model | Nhận request qua constructor; không phải thread-local holder |
| Thread-bound holder | `org.springframework.web.context.request.RequestContextHolder` | Tra cứu/bind/reset `RequestAttributes` trên thread | Có, nếu đã được Spring bind |
| Generic request attributes | `org.springframework.web.context.request.RequestAttributes` | Đọc/ghi attribute theo request/session scope | Interface, không phụ thuộc Servlet |
| Servlet implementation | `org.springframework.web.context.request.ServletRequestAttributes` | Truy cập `HttpServletRequest`, `HttpServletResponse` tùy trường hợp, session và attributes | Có, khi đang dùng Servlet stack |
| Jakarta request object | `jakarta.servlet.http.HttpServletRequest` | HTTP method, URI, headers, parameters, request attributes | Có, truyền/inject trong xử lý request |
| Request-scoped bean | `@RequestScope` | Một bean target riêng cho mỗi HTTP request | Spring IoC quản lý vòng đời |
| Spring MVC model | `Model`/`ModelMap` | Dữ liệu mà handler chuyển cho view | Không phải nơi lưu trạng thái toàn cục của request |

Trong REST API, thường chỉ cần method parameter `HttpServletRequest`, header/path/query parameters hoặc bean `@RequestScope`. `RequestContext` là tiện ích liên quan tới MVC view và i18n; không nên dùng nó như một request storage tùy ý.

## 3. RequestAttributes: abstraction cho dữ liệu thuộc request và session

`RequestAttributes` cung cấp những phương thức kiểu:

~~~java
Object getAttribute(String name, int scope);
void setAttribute(String name, Object value, int scope);
void removeAttribute(String name, int scope);
String[] getAttributeNames(int scope);
~~~

Hai hằng scope phổ biến:

- `RequestAttributes.SCOPE_REQUEST`: dữ liệu chỉ thuộc HTTP request.
- `RequestAttributes.SCOPE_SESSION`: dữ liệu thuộc HTTP session, có thể tồn tại qua nhiều request của cùng session.

Ví dụ trong code đang có request context hợp lệ:

~~~java
RequestAttributes attrs = RequestContextHolder.currentRequestAttributes();

attrs.setAttribute(
    "demo.requestId",
    "req-123",
    RequestAttributes.SCOPE_REQUEST
);

String id = (String) attrs.getAttribute(
    "demo.requestId",
    RequestAttributes.SCOPE_REQUEST
);
~~~

Đây là đoạn minh họa **được chạy trong một method xử lý HTTP request**, không phải chương trình Java độc lập. Giá trị `req-123` chỉ là ví dụ: hệ thống thật nên dùng ID duy nhất được tạo tin cậy hoặc chuẩn hóa từ gateway.

Điểm mấu chốt: ghi attribute theo `SCOPE_REQUEST` không biến dữ liệu thành singleton và không đưa nó vào session; khi request kết thúc, nó không còn là nơi lưu trạng thái cho request tiếp theo.

### 3.1. Attribute name là khóa dùng chung trong request

Những thư viện khác cũng có thể đặt attribute trên cùng request. Hãy chọn tên có namespace rõ ràng, ví dụ `com.example.trace.requestId` thay vì `id` hoặc `data`, để tránh vô tình đè lên dữ liệu của filter/framework.

Không dùng request attributes để chứa mật khẩu, access token hoặc dữ liệu cá nhân nhạy cảm nếu không thực sự cần thiết; nhiều filter, interceptor, controller và view có thể đọc cùng request. Hạn chế logging và chỉ lưu dữ liệu tối thiểu.

### 3.2. Scope session không thay thế scope request

Một người dùng có thể gửi nhiều request trong cùng HTTP session, thậm chí song song. Nếu ghi một trường request-specific vào session, request khác có thể nhìn thấy hoặc ghi đè. Dữ liệu session có yêu cầu đồng bộ hóa, thời gian hết hạn và chi phí lưu trữ riêng.

Nếu chỉ cần correlation ID hoặc kết quả tạm cho một request, hãy dùng `SCOPE_REQUEST` thay vì `SCOPE_SESSION`.

## 4. ServletRequestAttributes bao bọc đối tượng Servlet như thế nào?

`ServletRequestAttributes` triển khai `RequestAttributes` trên nền `HttpServletRequest` và `HttpSession` của Servlet container. Một số API:

~~~java
HttpServletRequest getRequest();
HttpServletResponse getResponse(); // Có thể null
Object getAttribute(String name, int scope);
void setAttribute(String name, Object value, int scope);
void removeAttribute(String name, int scope);
~~~

Về mặt hành vi, `SCOPE_REQUEST` tương ứng các attributes gắn với `HttpServletRequest`. Do đó:

~~~java
ServletRequestAttributes servletAttrs =
    (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();

servletAttrs.setAttribute(
    "com.example.demo.flag",
    "ready",
    RequestAttributes.SCOPE_REQUEST
);

Object sameValue = servletAttrs.getRequest()
    .getAttribute("com.example.demo.flag");
~~~

`sameValue` có giá trị `"ready"` trong cùng request. Đây là đoạn minh họa chạy trong một Servlet request; trong mã tổng quát nên kiểm tra `instanceof` trước khi ép kiểu vì `RequestAttributes` còn có những implementation khác.

### 4.1. Native request và response không phải lúc nào cũng sẵn

- `getRequest()` cung cấp `HttpServletRequest` được bao bọc.
- `getResponse()` có thể trả `null` nếu đối tượng `ServletRequestAttributes` được tạo không có response.
- Các API riêng của Servlet không áp dụng trực tiếp với ứng dụng WebFlux chạy trên Reactor Netty.

Đừng giữ `HttpServletRequest` hoặc `ServletRequestAttributes` trong static field, singleton mutable field hay background task chạy lâu sau khi request đã hoàn tất. Vòng đời của Servlet request không kéo dài vô hạn.

### 4.2. Cơ chế kết thúc request

Spring có thể quản lý callback hủy của request-scoped bean/attributes khi request hoàn tất. Ứng dụng không nên tự gọi `requestCompleted()` của `ServletRequestAttributes` đang được `DispatcherServlet` quản lý; đó là công việc của hạ tầng. Nếu manually bind `RequestContextHolder` trong test hoặc integration đặc thù, phải hiểu trách nhiệm cleanup và khôi phục context cũ.

## 5. RequestContextHolder: đọc ngữ cảnh request gắn với thread

Hai cách tra cứu phổ biến:

~~~java
RequestAttributes optional =
    RequestContextHolder.getRequestAttributes();

RequestAttributes required =
    RequestContextHolder.currentRequestAttributes();
~~~

Sự khác biệt:

| API | Khi có request context | Khi không có context |
| --- | --- | --- |
| `getRequestAttributes()` | Trả về `RequestAttributes` | Trả về `null` |
| `currentRequestAttributes()` | Trả về `RequestAttributes` | Thường ném `IllegalStateException`, trừ trường hợp fallback như JSF |
| `setRequestAttributes(attributes)` | Bind vào thread hiện hành | Cần được cân nhắc kỹ khi tự quản lý |
| `resetRequestAttributes()` | Xóa context khỏi thread hiện hành | Không tạo request mới |

Trong Spring MVC thông thường, `DispatcherServlet` đã expose request context. Nếu chạy code từ `@Scheduled`, một executor tự tạo hoặc `main()`, thường **không có HTTP request** để đọc.

Ví dụ helper an toàn trong code vốn có thể chạy cả ở request thread lẫn background thread:

~~~java
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

public final class CurrentRequestInfo {
    private CurrentRequestInfo() {
    }

    public static String currentPathOrUnknown() {
        RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
        if (attrs instanceof ServletRequestAttributes servletAttrs) {
            return servletAttrs.getRequest().getRequestURI();
        }
        return "(no servlet request)";
    }
}
~~~

Đây là lớp tiện ích để dùng trong ứng dụng có Spring Web dependency, không phải chương trình độc lập chỉ dùng JDK. Nó không tự “tạo” request cho background thread và không cần catch exception chỉ để che việc context đang vắng mặt.

### 5.1. Không nên tự setRequestAttributes trong nghiệp vụ

`RequestContextHolder.setRequestAttributes(...)` là API cấp hạ tầng. Tự bind một request vào thread pool hoặc quên cleanup có thể làm thread tái sử dụng giữ context cũ. Khi viết adapter đặc thù cần tự bind, hãy lưu context trước, đảm bảo restore trong `finally` và hiểu rõ request còn sống hay không.

Thông thường **không cần** gọi setter trong controller/service Spring MVC. Hãy nhận `HttpServletRequest` qua method argument, inject request-scoped collaborator hoặc truyền dữ liệu riêng cần thiết.

### 5.2. Vì sao ThreadLocal cần cleanup?

Tomcat sử dụng pool worker threads. Sau request A, thread T1 có thể xử lý request B. Nếu code tùy ý để lại context của A, request B có nguy cơ đọc nhầm thông tin của A. Hạ tầng Spring quản lý bind/restore đúng trong dispatch; khi ứng dụng tự tạo ThreadLocal thì ứng dụng chịu trách nhiệm cleanup.

Ví dụ Java 17+ **độc lập**, minh họa `ThreadLocal` ở cấp khái niệm (đây không phải implementation đầy đủ của Spring request scope):

**ThreadLocalConceptDemo.java**

~~~java
public class ThreadLocalConceptDemo {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    public static void main(String[] args) {
        try {
            CURRENT.set("request-A");
            System.out.println("Inside: " + CURRENT.get());
        } finally {
            CURRENT.remove();
        }

        System.out.println("After cleanup: " + CURRENT.get());
    }
}
~~~

Chạy:

~~~bash
javac ThreadLocalConceptDemo.java
java ThreadLocalConceptDemo
~~~

Stdout chính xác:

~~~text
Inside: request-A
After cleanup: null
~~~

Đối với mã Spring, chỉ dùng ví dụ để hiểu nguyên lý thread-bound context, không dùng static ThreadLocal tự viết để thay thế cơ chế request scope của framework.

## 6. RequestContext (MVC view helper) là lớp khác RequestContextHolder

Tên đầy đủ của `RequestContext` cần nói rõ:

~~~java
org.springframework.web.servlet.support.RequestContext
~~~

Đây là lớp hỗ trợ view/MVC:

- Truy xuất `WebApplicationContext` và `MessageSource`.
- Xác định `Locale` và tùy trường hợp `TimeZone` từ ngữ cảnh web.
- Lấy thông điệp i18n bằng message code.
- Tạo URL có tính tới context path qua `getContextUrl(...)`.
- Hỗ trợ dữ liệu binding/errors, thường hữu ích trong JSP, FreeMarker hoặc view technology tương tự.

Ví dụ trong controller Spring MVC khi có `HttpServletRequest`:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.servlet.support.RequestContext;

public String linkForCurrentApplication(HttpServletRequest request) {
    RequestContext context = new RequestContext(request);
    return context.getContextUrl("/orders");
}
~~~

Nếu ứng dụng đặt `server.servlet.context-path=/training`, kết quả với path trên thường là `/training/orders`; với context path mặc định rỗng là `/orders`. `RequestContext` trong ví dụ lấy request được truyền qua argument, không đọc context từ `RequestContextHolder` chỉ vì tên giống nhau.

Trong phần lớn REST API, việc tạo `RequestContext` thủ công không cần thiết. Nếu chỉ cần locale thì có thể dùng tham số `Locale`, nếu cần URL thì cân nhắc `ServletUriComponentsBuilder`/URI builder phù hợp và chính sách reverse proxy, còn dữ liệu request thì dùng method parameter hoặc request scope.

**Chú ý về cùng tên:** Trong WebFlux cũng có các lớp mang tên `RequestContext` ở package khác nhau. Bài này nói về `org.springframework.web.servlet.support.RequestContext` thuộc Spring MVC/Servlet stack, không phải một “global RequestContext” chung cho mọi stack.

## 7. Phạm vi dữ liệu: request, session, application, singleton

| Phạm vi | Vòng đời | Nơi phù hợp | Tránh dùng cho |
| --- | --- | --- | --- |
| Biến cục bộ method | Một lần gọi method | DTO trung gian, phép tính ngắn | Chia sẻ qua tầng không có argument |
| `HttpServletRequest.setAttribute` | Một HTTP request | Metadata giữa filter/interceptor/controller/view | Trạng thái người dùng qua nhiều request |
| `@RequestScope` | Một HTTP request | Một object chứa trạng thái có nghĩa trong request | Cache toàn hệ thống, background task lâu dài |
| `@SessionScope` | Một HTTP session | Một số preference/session conversation | Correlation ID chỉ dùng cho một request |
| `@ApplicationScope` | ServletContext của web application | Dữ liệu ứng dụng gắn với ServletContext | Thông tin cá nhân hoặc request-specific |
| Singleton Spring bean | Một instance cho mỗi bean definition/container | Service stateless, dependency dùng chung | Mutable field chứa userId/currentRequest của request vừa tới |

Phân biệt hai cách lưu request-specific state:

- **Request attribute:** key/value gắn với request, ví dụ `request.setAttribute("traceId", id)`.
- **Request-scoped bean:** Spring quản lý đối tượng theo request; có thể có behavior, dependency và callback lifecycle.

Hai cách cùng phục vụ phạm vi request nhưng không phải một API. Request scope của Spring sử dụng hạ tầng `RequestAttributes` bên dưới để truy cập object tương ứng.

## 8. Vì sao request scope quan trọng với singleton service?

`@Service` mặc định là singleton. Giả sử code sai:

~~~java
@Service
public class BadAuditService {
    private String currentUserId;

    public void record(String userId) {
        this.currentUserId = userId;
        // Request khác có thể ghi đè field trong lúc đang xử lý.
    }
}
~~~

Đây là **ví dụ phản diện**, không phải code khuyến nghị. Khi hai request chạy đồng thời, cả hai chia sẻ một field `currentUserId` trong singleton, dẫn tới race condition và nguy cơ trộn dữ liệu.

Cách tốt nhất khi dữ liệu ngắn gọn là **truyền tường minh** qua method argument:

~~~java
public void record(String userId, String correlationId) {
    // Dữ liệu chỉ nằm trong call này, không ghi vào shared field.
}
~~~

Nếu nhiều thành phần của cùng request cần một đối tượng mang trạng thái, có thể dùng `@RequestScope` để Spring tạo target riêng theo request. Đừng mặc định sử dụng request scope để né việc thiết kế API rõ ràng; passing explicit context vẫn thường dễ kiểm thử và an toàn hơn cho xử lý async.

## 9. @RequestScope và scoped proxy

Annotation `@RequestScope` là shortcut cho `@Scope("request")`, với `proxyMode=ScopedProxyMode.TARGET_CLASS` theo mặc định. Điều này giúp inject vào singleton bean bằng proxy mà chưa cần tạo target request-scoped lúc startup.

Luồng:

~~~text
Singleton RequestStateService được tạo lúc startup
           |
           +--> giữ reference đến scoped proxy của RequestState
                           |
Request A -> proxy -> RequestState target A
Request B -> proxy -> RequestState target B
Request A -> proxy -> vẫn target A trong request A
~~~

Cần hiểu rõ:

1. **Proxy là reference lâu sống**, còn target data chỉ sống trong request.
2. Trong một HTTP request, các lần truy cập bean target thông thường dùng **cùng một instance**.
3. Request mới có target khác; không mang trạng thái của request trước.
4. Truy cập proxy khi **không có request scope active** có thể gây `ScopeNotActiveException` hoặc lỗi liên quan.
5. `@RequestScope` mặc định dùng class-based proxy; hãy tránh final class/final method cần proxy hoặc dùng interface-based proxy khi thiết kế phù hợp.
6. Chỉ đánh dấu `@Scope("request")` thuần túy rồi inject trực tiếp vào singleton có thể không được proxy như mong đợi; cần proxy đúng hoặc `ObjectProvider` để resolve bean theo request.

**Request-scoped bean không tự động thread-safe.** Nếu cùng một HTTP request có nhiều nhánh async cùng truy cập mutable state, vẫn cần thiết kế đồng bộ hóa. “Mỗi request một bean” không có nghĩa “mỗi thread một bean”.

## 10. Ví dụ đầy đủ: Spring Boot + RequestContext + ServletRequestAttributes + @RequestScope

Ứng dụng ví dụ chứng minh bốn điều:

1. Controller đọc ngữ cảnh đang được bind qua `RequestContextHolder`.
2. `ServletRequestAttributes` và `HttpServletRequest` nhìn thấy cùng một request attribute.
3. Singleton service inject một `@RequestScope` bean qua scoped proxy; target giữ state ổn định trong cùng request và khác giữa các request.
4. `RequestContext` tạo đường dẫn tương đối với context path của ứng dụng.

Sử dụng Spring Boot **3.3.13**, Java **21** và Gradle **8.5+** phù hợp với Java 21.

Cấu trúc dự án:

~~~text
request-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/requestcontext/
    │       ├── RequestContextDemoApplication.java
    │       ├── RequestState.java
    │       ├── RequestStateService.java
    │       └── RequestDemoController.java
    └── test/
        └── java/com/example/requestcontext/
            └── RequestDemoControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'request-context-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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

Starter web cung cấp Spring MVC và embedded Tomcat mặc định; starter test cung cấp JUnit 5, MockMvc và các hỗ trợ kiểm thử. Không cần thêm JSP/FreeMarker để dùng các API `RequestContext` trên controller; việc render view bằng template là chủ đề riêng.

### 10.1. Lớp main

**src/main/java/com/example/requestcontext/RequestContextDemoApplication.java**

~~~java
package com.example.requestcontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestContextDemoApplication.class, args);
    }
}
~~~

Đặt main class ở package cha cùng các bean cần scan để `@Component`, `@Service` và `@RestController` được phát hiện.

### 10.2. Bean có scope theo từng HTTP request

**src/main/java/com/example/requestcontext/RequestState.java**

~~~java
package com.example.requestcontext;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestState {

    private final String requestId = UUID.randomUUID().toString();
    private int touches;

    public String id() {
        return requestId;
    }

    public int nextTouch() {
        return ++touches;
    }
}
~~~

`RequestState` được tạo riêng cho từng HTTP request. `requestId` là ID minh họa được sinh khi target bean được khởi tạo, không phải ID lấy từ gateway. Field `touches` cố ý có state để thử tính cô lập; trong hệ thống thật nên ưu tiên immutable state nếu không có lý do để thay đổi dữ liệu.

### 10.3. Singleton service dùng scoped proxy

**src/main/java/com/example/requestcontext/RequestStateService.java**

~~~java
package com.example.requestcontext;

import org.springframework.stereotype.Service;

@Service
public class RequestStateService {

    private final RequestState state;

    public RequestStateService(RequestState state) {
        this.state = state;
    }

    public Sample sample() {
        int first = state.nextTouch();
        int second = state.nextTouch();
        return new Sample(state.id(), first, second);
    }

    public record Sample(String id, int first, int second) {
    }
}
~~~

`RequestStateService` là singleton nhưng reference `state` mà nó giữ là **proxy**. Khi request A gọi `sample()` hai lần truy cập target bean sẽ thuộc request A; request B lại có target bean riêng. Service không lưu request-specific state trực tiếp trong field của chính singleton.

### 10.4. Controller dùng cả ba API

**src/main/java/com/example/requestcontext/RequestDemoController.java**

~~~java
package com.example.requestcontext;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.support.RequestContext;

@RestController
@RequestMapping("/context")
public class RequestDemoController {

    private final RequestStateService service;

    public RequestDemoController(RequestStateService service) {
        this.service = service;
    }

    @GetMapping("/state")
    public Inspection state(HttpServletRequest request) {
        RequestAttributes attributes =
            RequestContextHolder.currentRequestAttributes();

        if (!(attributes instanceof ServletRequestAttributes servlet)) {
            throw new IllegalStateException("Servlet request expected");
        }

        servlet.setAttribute(
            "com.example.demo.note",
            "request-only",
            RequestAttributes.SCOPE_REQUEST
        );

        String note = (String) request.getAttribute("com.example.demo.note");

        RequestStateService.Sample sample = service.sample();

        RequestContext viewContext = new RequestContext(request);

        return new Inspection(
            servlet.getRequest().getMethod(),
            request.getRequestURI(),
            note,
            sample.id(),
            sample.first(),
            sample.second(),
            viewContext.getLocale().toLanguageTag(),
            viewContext.getContextUrl("/context/state")
        );
    }

    public record Inspection(
        String method,
        String path,
        String note,
        String requestId,
        int first,
        int second,
        String locale,
        String contextUrl
    ) {
    }
}
~~~

Cơ chế cụ thể:

- `HttpServletRequest` được Spring MVC cung cấp cho handler method, không phải một singleton.
- `RequestContextHolder.currentRequestAttributes()` đọc context được bind trong dispatch.
- `ServletRequestAttributes.setAttribute(..., SCOPE_REQUEST)` ghi vào request; `request.getAttribute(...)` đọc lại cùng một giá trị.
- `service.sample()` gọi bean `@RequestScope` hai lần, nên `first=1` và `second=2` đối với mỗi request mới.
- `RequestContext` là đối tượng khác với holder; ví dụ dùng nó để đọc locale và tạo URL có context path.
- HTTP response được Jackson tạo từ Java record `Inspection`.

### 10.5. Chạy và thử thủ công

Nếu máy đã có Gradle và JDK 21, từ thư mục dự án:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Nếu project đã có wrapper, bỏ qua lệnh `gradle wrapper`. Trên Windows PowerShell chạy `.\gradlew.bat bootRun`.

Gọi HTTP request:

~~~bash
curl -i http://localhost:8080/context/state
~~~

Kết quả kỳ vọng: HTTP **200 OK** và JSON có những trường như:

~~~json
{
  "method": "GET",
  "path": "/context/state",
  "note": "request-only",
  "requestId": "d1a4fb7e-6fd5-4e24-9ad4-9da397b0d216",
  "first": 1,
  "second": 2,
  "locale": "vi-VN",
  "contextUrl": "/context/state"
}
~~~

**Đây là response minh họa, không phải output cố định:** `requestId` là UUID ngẫu nhiên; `locale` phụ thuộc ngôn ngữ client và resolver; JSON field order có thể khác. Giá trị `method`, `path`, `note`, `first` và `second` tương ứng code và URL đã cho trong cấu hình mặc định.

Gửi lại request sẽ có `requestId` mới, nhưng `first=1`, `second=2` vẫn đúng cho request tiếp theo. Giải thích: target `RequestState` mới được tạo trên mỗi request; biến `touches` không tồn tại qua request khác.

Nếu thêm tùy chọn:

~~~yaml
server:
  servlet:
    context-path: /training
~~~

thì URL request trở thành `http://localhost:8080/training/context/state` và `contextUrl` được tạo bởi `RequestContext` là `/training/context/state`. Giá trị `path` do `getRequestURI()` cũng chứa context path. Không nên tự chắp chuỗi URL trong mọi chỗ; khi có reverse proxy cần kiểm tra forwarded headers và cấu hình tin cậy từ hạ tầng.

## 11. Kiểm thử hai request thực sự tách biệt

Khi muốn kiểm tra scope, chỉ gọi một controller method một lần không đủ để chứng minh state không rò rỉ giữa request. MockMvc có thể thực hiện nhiều lần dispatch MVC trong test context và kiểm tra ID khác nhau.

**src/test/java/com/example/requestcontext/RequestDemoControllerTest.java**

~~~java
package com.example.requestcontext;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void requestScopeIsFreshForEachRequest() throws Exception {
        MvcResult first = mvc.perform(get("/context/state"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.note").value("request-only"))
            .andExpect(jsonPath("$.first").value(1))
            .andExpect(jsonPath("$.second").value(2))
            .andReturn();

        MvcResult second = mvc.perform(get("/context/state"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.first").value(1))
            .andExpect(jsonPath("$.second").value(2))
            .andReturn();

        JsonNode body1 = mapper.readTree(
            first.getResponse().getContentAsString());
        JsonNode body2 = mapper.readTree(
            second.getResponse().getContentAsString());

        String id1 = body1.path("requestId").asText();
        String id2 = body2.path("requestId").asText();

        assertFalse(id1.isBlank());
        assertFalse(id2.isBlank());
        assertNotEquals(id1, id2);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test kiểm tra cả **ổn định trong một request** (`first=1`, `second=2`) và **tách biệt giữa hai request** (UUID khác nhau). Xác suất trùng UUID về mặt lý thuyết không bằng không nhưng cực nhỏ đối với ví dụ.

`@SpringBootTest` khởi tạo ứng dụng và `@AutoConfigureMockMvc` thiết lập MockMvc mà không cần mở network socket. Muốn kiểm thử kết nối Tomcat/HTTP thật, dùng integration test với `webEnvironment=RANDOM_PORT` và HTTP client phù hợp — đó là phạm vi khác.

## 12. Cách truy cập request data trong từng tầng

| Vị trí | Ưu tiên | Lưu ý |
| --- | --- | --- |
| Controller method | `@RequestHeader`, `@PathVariable`, `@RequestParam`, `HttpServletRequest` | Dễ thấy dependency, dễ kiểm thử |
| Servlet Filter | `HttpServletRequest`/`ServletRequest` được truyền vào filter | Có thể chạy trước DispatcherServlet bind context |
| Spring MVC HandlerInterceptor | `HttpServletRequest` tham số `preHandle`/`postHandle` | Chú ý callback khi có async dispatch |
| Singleton service | Dữ liệu immutable qua method argument, hoặc request-scoped collaborator phù hợp | Tránh mutable field chứa current user/request |
| View technology | Model attributes và `RequestContext` khi cần | View helper không phải global storage |
| Error handler/advice | Parameter injection và thông tin từ exception/request | Cần xử lý cả lỗi xảy ra trước handler |
| `@Async` hoặc executor tự tạo | Truyền snapshot immutable cần thiết | Thread-bound request context thường không tự propagate |
| `@Scheduled`/startup task | Không dựa vào request context | Không có HTTP request hiện hành |
| WebFlux/Reactive | `ServerWebExchange`/Reactor Context | Không giả định ServletRequestAttributes tồn tại |

**Nguyên tắc lựa chọn:** nếu chỉ cần một hoặc hai giá trị, truyền chúng như tham số thường rõ ràng và ít ràng buộc hạ tầng nhất. Chỉ dùng `RequestContextHolder` sâu trong code khi có lý do hợp lý và chấp nhận được dependency ngầm vào web request.

## 13. RequestContextListener và RequestContextFilter dùng khi nào?

Trong ứng dụng Spring MVC thông thường, `DispatcherServlet` đã bind request context cho xử lý phía trong dispatch. Tuy nhiên, nếu một đoạn code chạy **ngoài DispatcherServlet** cần truy cập `RequestContextHolder` hoặc web scope, Spring Framework cung cấp:

- `RequestContextListener`: Servlet listener expose request theo lifecycle.
- `RequestContextFilter`: Servlet filter bind request context trong filter chain; hỗ trợ xử lý async/error dispatch theo hành vi của filter.
- `DispatcherServlet`: tự expose request khi đang điều phối MVC request.

Đừng đăng ký listener/filter bổ sung chỉ vì thấy một ví dụ trực tuyến. Kiểm tra xem đoạn code đang chạy trong servlet dispatch thông thường hay bên ngoài, cấu hình Boot đã có filter gì, và thứ tự filter chain cần thiết. Đăng ký thừa có thể làm khó reasoning về context hoặc filter order.

Một tình huống thực tế: một servlet/filter của bên thứ ba xử lý request mà không đi vào DispatcherServlet nhưng muốn dùng request scope của Spring. Khi ấy có thể cần một cơ chế expose request context ngoài DispatcherServlet; đồng thời phải kiểm tra rõ các giới hạn lifecycle và dispatch.

## 14. Thread-bound context không tự chuyển sang @Async, CompletableFuture

`RequestContextHolder` dựa vào `ThreadLocal` (hoặc `InheritableThreadLocal` khi cấu hình đặc biệt). Khi controller chuyển việc sang `@Async`, `CompletableFuture.supplyAsync` hoặc một executor pool, task thường chạy trên thread khác. Trên thread đó:

~~~java
RequestContextHolder.getRequestAttributes()
~~~

có thể trả `null`; còn:

~~~java
RequestContextHolder.currentRequestAttributes()
~~~

có thể ném `IllegalStateException` với thông báo không có thread-bound request. Đây không nhất thiết là bug của Spring Boot; thường là hệ quả của **mất ranh giới context qua thread**.

### 14.1. Đừng giữ nguyên HttpServletRequest qua background job

Không nên làm như sau:

~~~java
// Ví dụ phản diện: tránh giữ đối tượng request sống lâu qua thread khác.
executor.execute(() -> {
    String userAgent = request.getHeader("User-Agent");
    // Request có thể đã hoàn tất khi code này chạy.
});
~~~

Đoạn này chỉ minh họa lỗi thiết kế, không phải chương trình runnable. Dùng reference tới `HttpServletRequest` sau khi request hoàn tất có thể vi phạm vòng đời; việc dùng request data trong background task còn có nguy cơ lộ dữ liệu hoặc lệ thuộc Servlet container.

### 14.2. Cách an toàn: chụp snapshot chỉ gồm dữ liệu cần thiết

Ở request thread, lấy các giá trị cần cho nghiệp vụ, rồi truyền một DTO immutable:

~~~java
public record RequestSnapshot(String correlationId, String localeTag) {
}
~~~

Trong controller hoặc service nhận tham số đã xác thực/chuẩn hóa:

~~~java
RequestSnapshot snapshot =
    new RequestSnapshot(correlationId, locale.toLanguageTag());

backgroundService.submit(snapshot);
~~~

Đây là đoạn mã mô tả cách thiết kế, không phải class Java hoàn chỉnh; giả định `correlationId`, `locale` và `backgroundService` được cung cấp hợp lệ. Task chỉ nhận snapshot, không giữ toàn bộ Servlet request và không truy cập `RequestContextHolder` khi request đã kết thúc.

Đừng coi correlation ID lấy trực tiếp từ header là bằng chứng danh tính. Authentication/authorization phải được xử lý theo chính sách security riêng.

### 14.3. InheritableThreadLocal không phải cách chữa mọi thread pool

`RequestContextHolder.setRequestAttributes(attributes, true)` có thể sử dụng `InheritableThreadLocal`. Cách này **không an toàn làm giải pháp tổng quát cho thread pool**, vì thread được tạo/tái sử dụng có thể giữ context không liên quan hoặc context đã hết hạn. Spring cũng cảnh báo không bật inheritance khi dùng thread pool có thể tự tạo thêm worker.

Nếu cần context propagation, dùng cơ chế có quản lý vòng đời rõ ràng, truyền immutable snapshot hoặc công cụ propagation được framework hỗ trợ đúng phiên bản và loại tác vụ. Không tự set/reset context bên trong mỗi business method như một quy tắc chung.

### 14.4. Spring MVC async là trường hợp được framework điều phối

Spring MVC hỗ trợ `Callable`, `WebAsyncTask`, `DeferredResult` và async Servlet dispatch. Với một số đường async do Spring MVC quản lý, framework có khả năng quản lý ngữ cảnh khi thực thi và dispatch lại, nhưng **không được suy diễn** mọi worker thread tùy ý sẽ nhìn thấy cùng `RequestContextHolder`.

Với `DeferredResult`, servlet request có thể đang ở trạng thái async khi thread ban đầu đã thoát khỏi DispatcherServlet; framework sẽ dispatch lại khi có kết quả. Nếu code yêu cầu truy cập context ở một callback bất kỳ, phải kiểm tra rõ ranh giới thread/dispatch và khả năng context được propagate trong trường hợp cụ thể.

## 15. Correlation ID, logging và trách nhiệm security

Một ứng dụng thường muốn mọi log của một HTTP request mang cùng correlation ID. Có thể đưa correlation ID vào request attribute và/hoặc MDC trong filter, nhưng hai thứ không giống nhau:

- **Request attribute:** dữ liệu tồn tại trong HTTP request và có thể được đọc bởi các thành phần có request reference.
- **MDC:** dữ liệu chẩn đoán thường lưu theo thread trong logging framework, cần dọn trong `finally` và có thể cần propagation khi chuyển thread.
- **HTTP header:** dữ liệu đến từ client/gateway, có thể giả mạo trừ khi có chính sách tin cậy.
- **Trace context:** mô hình tracing có propagation và chuẩn riêng, ví dụ W3C trace context; không đồng nhất với một request attribute tùy ý.

Nếu triển khai MDC thủ công, đặt và xóa trong `try/finally` quanh request; chú ý filter được gọi ở async/error dispatch như thế nào. Khi sử dụng Micrometer Tracing/Spring Boot Actuator, ưu tiên công cụ instrumentation đã được cấu hình để không tự làm lệch trace ID.

**Không dùng `RequestContextHolder` để lấy “current user” bằng cách đọc một request attribute không được xác thực rồi coi nó là quyền truy cập.** Principal/Spring Security context và policy kiểm soát truy cập là chủ đề khác, cần được xác minh độc lập.

## 16. Những lỗi thường gặp và cách chẩn đoán

### 16.1. “No thread-bound request found”

Triệu chứng: gọi `RequestContextHolder.currentRequestAttributes()` trong `@Async`, `@Scheduled`, unit test không mở MVC context hoặc callback ngoài request thread.

Cách xử lý: xác nhận call stack và thread; đừng bind một request giả chỉ để làm lỗi biến mất. Chuyển dữ liệu cần thiết thành method parameter/immutable snapshot hoặc chạy logic trong MVC dispatch được framework hỗ trợ.

### 16.2. “Scope 'request' is not active for the current thread”

Triệu chứng: request-scoped bean được truy cập từ startup method, background worker hoặc scope chưa hoạt động.

Cách xử lý: không gọi proxy ngoài request; kiểm tra code khởi tạo singleton và lifecycle. Với unit test riêng, cung cấp request context hợp lệ hoặc mock dependency thay vì tái sử dụng Servlet request thật.

### 16.3. Singleton service lưu currentUserId trong mutable field

Triệu chứng: request A nhận dữ liệu của B khi tải cao.

Cách xử lý: biến local, immutable DTO truyền tham số, bean request-scoped được inject qua proxy; không sử dụng shared mutable field chứa trạng thái theo request.

### 16.4. Cast RequestAttributes sang ServletRequestAttributes không an toàn

Triệu chứng: `ClassCastException` trong môi trường không phải Servlet hoặc test đặc thù.

Cách xử lý: dùng `instanceof ServletRequestAttributes`, hoặc phụ thuộc vào abstraction `RequestAttributes` nếu chỉ cần get/set request attributes.

### 16.5. Dùng javax.servlet khi chạy Spring Boot 3

Spring Boot 3 sử dụng Jakarta Servlet API (`jakarta.servlet.http.HttpServletRequest`). Mã cũ dùng `javax.servlet.*` của Spring Boot 2 không được chép trực tiếp mà không migration.

### 16.6. RequestContext bị nhầm với RequestContextHolder

`RequestContext` ở package `web.servlet.support` là view helper, không có phương thức static `currentRequestAttributes()`. Phương thức đó thuộc `RequestContextHolder` ở `web.context.request`. Đọc package/import khi tên class na ná nhau.

### 16.7. Trạng thái request-scoped bean bị thay đổi ngoài dự kiến

Nếu nhiều nhánh async trong **cùng một request** cùng sửa một object request-scoped, object này không mặc nhiên thread-safe. Dùng immutable state, đồng bộ hóa phù hợp hoặc thiết kế không chia sẻ mutable state.

### 16.8. Dùng SCOPE_SESSION để truyền data giữa filter và controller

Request-specific data chuyển sang session có thể tồn tại qua nhiều HTTP requests, làm trộn trạng thái và tăng storage. Dùng `SCOPE_REQUEST` để gắn dữ liệu vào đúng request.

### 16.9. Request-scoped dependency trong @WebMvcTest không hiện diện

`@WebMvcTest` là MVC slice, không tự import mọi service tùy ý. Nếu controller cần service/request-scoped bean, cần cung cấp `@MockBean`/`@MockitoBean` thích hợp theo phiên bản hoặc cấu hình `@Import`. Ví dụ đầy đủ ở bài dùng `@SpringBootTest` để tránh thiếu application beans.

### 16.10. Lấy Locale từ nơi không đúng

`request.getLocale()` thường phản ánh preference từ HTTP request; `RequestContext.getLocale()` có thể dùng locale do Spring MVC `LocaleResolver` xác định. Trong hệ thống hỗ trợ đổi ngôn ngữ qua cookie/session/resolver, hai giá trị có thể khác. Chọn nguồn phù hợp với chính sách i18n của ứng dụng.

### 16.11. MockMvc bị hiểu nhầm là Tomcat thật

MockMvc thực thi MVC dispatch trong môi trường test, không mở cổng mạng theo mặc định. Test scope thành công không chứng minh cấu hình reverse proxy, session cookie hoặc network timeout của production đã đúng.

## 17. Khi nào nên chọn cách nào?

Bảng quyết định nhanh:

| Nhu cầu | Cách ưu tiên |
| --- | --- |
| Đọc một header trong controller | `@RequestHeader` hoặc `HttpServletRequest` |
| Lấy request path cho một handler | Method argument `HttpServletRequest` hoặc thành phần MVC được cung cấp |
| Chia sẻ metadata giữa filter và controller | `request.setAttribute(...)`/`getAttribute(...)` với khóa có namespace |
| Cùng một object có state trong toàn bộ một request | Bean `@RequestScope` |
| Dùng request-scoped bean trong singleton service | Scoped proxy mặc định của `@RequestScope` hoặc `ObjectProvider` khi phù hợp |
| Lấy `RequestAttributes` ở chỗ không nhận trực tiếp request | `RequestContextHolder.getRequestAttributes()` nếu chấp nhận dependency vào thread-bound context |
| Tạo URL có context path và i18n trong MVC view | `RequestContext` hoặc helper view phù hợp |
| Chạy tác vụ background | Truyền snapshot immutable / job payload |
| Dùng reactive WebFlux | `ServerWebExchange` và Reactor Context, không dùng Servlet request làm chuẩn |
| Lưu trạng thái lâu dài | Database/cache/session có kiểm soát, không dùng request scope |

Một nguyên tắc đáng nhớ: **ưu tiên dữ liệu tường minh, giảm dependency ngầm vào thread**. `RequestContextHolder` tiện lợi nhưng làm service khó chạy độc lập trong CLI/batch/async/test. Chỉ dùng khi lợi ích và phạm vi sử dụng được xác định rõ.

## 18. Checklist tự kiểm tra

1. Đã phân biệt `RequestContext` (MVC view) với `RequestContextHolder` (thread-bound holder) chưa?
2. Khi gọi `RequestContextHolder`, code chắc chắn nằm trong một request dispatch hợp lệ hay không?
3. Dữ liệu cần lưu thuộc request, HTTP session hay toàn ứng dụng?
4. Nếu dùng `ServletRequestAttributes`, đã kiểm tra môi trường Servlet và response nullable chưa?
5. Key request attribute có namespace, tránh xung đột với framework/filter khác không?
6. Singleton service có chứa mutable field lưu current user/request ID không?
7. `@RequestScope` target có được truy cập qua scoped proxy/`ObjectProvider` đúng cách không?
8. Có truy cập request-scoped object trong startup, scheduler, @Async hoặc worker pool không?
9. Nếu dùng async, dữ liệu đã được truyền bằng immutable snapshot hoặc propagation phù hợp chưa?
10. Có nguy cơ giữ `HttpServletRequest`/`ServletRequestAttributes` sau khi HTTP request hoàn tất không?
11. Có log dữ liệu nhạy cảm từ header, token, request attributes hay session không?
12. Test đã xác nhận state ổn định **trong một request** và khác nhau **giữa các request** chưa?
13. Đã kiểm thử cả đường MVC bình thường lẫn error/async dispatch nếu ứng dụng dùng không?
14. Với Spring Boot 3, import đã là `jakarta.servlet.*` chưa?
15. Nếu chuyển sang WebFlux, code đã loại giả định Servlet và ThreadLocal context chưa?

**Kết luận:** Trong luồng Spring MVC, `RequestContextHolder` giúp truy cập `RequestAttributes` gắn với thread đang được framework quản lý; `ServletRequestAttributes` hiện thực abstraction đó trên Servlet request/session; còn `RequestContext` là helper MVC cho locale, message và URL/view. Khi cần dữ liệu chỉ sống trong một HTTP request, dùng request attributes hoặc `@RequestScope` đúng mục đích. Đừng đặt state của request trong singleton mutable field, và đừng giả định thread-bound context tự động đi theo `@Async` hay các thread pool: hãy truyền dữ liệu tối thiểu, rõ vòng đời và kiểm thử ở ranh giới request.

## Tài liệu tham khảo

- Spring Framework — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html), giải thích request scope và scoped proxy.
- Spring Framework 6.1 — [RequestContextHolder](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html), API thread-bound attributes.
- Spring Framework 6.1 — [ServletRequestAttributes](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/context/request/ServletRequestAttributes.html), request/session adapter.
- Spring Framework 6.1 — [RequestContext](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/servlet/support/RequestContext.html), MVC view helper.
- Spring Framework — [Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html), async Servlet dispatch.
