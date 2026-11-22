# Interceptor trước handler, sau handler và sau khi hoàn tất yêu cầu

Trong Spring MVC, một HTTP request có thể đi qua **Servlet Filter** và nhiều **HandlerInterceptor** trước khi controller method được gọi. Interceptor còn có cơ hội chạy sau khi controller thực thi hoặc khi request đã hoàn tất. Những callback này hữu ích cho việc ghi dấu thời gian, thêm thông tin vào model của view, đo đạc request, chuẩn bị và dọn dữ liệu theo vòng đời request, hoặc chẩn đoán luồng xử lý.

Ba callback quan trọng của giao diện `org.springframework.web.servlet.HandlerInterceptor`:

- **`preHandle(...)`:** trước handler; trả `true` để tiếp tục hoặc `false` để dừng.
- **`postHandle(...)`:** sau khi handler thực thi thành công, trước bước render view của `DispatcherServlet`.
- **`afterCompletion(...)`:** khi việc xử lý request kết thúc, dùng để cleanup và ghi nhận kết quả; chỉ áp dụng cho interceptor đã có `preHandle` trả `true` trong lượt dispatch tương ứng.

Điểm dễ sai nhất không phải cú pháp mà là **thứ tự gọi khi có nhiều interceptor**, **hành vi khi preHandle trả false**, **exception đã được xử lý**, và **request async**. Đặc biệt, với `@ResponseBody`/`ResponseEntity`, response có thể đã được ghi/commit trong `HandlerAdapter` trước `postHandle`, vì vậy callback này không phải nơi đáng tin để thêm header hoặc chỉnh JSON.

Bài học thuộc nhóm **Bộ lọc và interceptor**, dùng **Spring Boot 3.3.x / Spring Framework 6.1 / Spring MVC Servlet / Java 21**. Spring WebFlux có `WebFilter` và xử lý reactive riêng; không lấy `HandlerInterceptor` của Servlet MVC áp trực tiếp lên WebFlux.

## 1. HandlerInterceptor nằm ở đâu trong request pipeline?

Sơ đồ với một HTTP request đồng bộ đã tìm thấy controller:

~~~text
HTTP client
    |
    v
Embedded Tomcat / Servlet container
    |
    v
Servlet Filter chain (Servlet API)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping chọn handler + HandlerExecutionChain
    |        |
    |        +-- Interceptor A.preHandle()
    |        +-- Interceptor B.preHandle()
    |        +-- Interceptor C.preHandle()
    |        |
    |        v
    |     HandlerAdapter -> @Controller/@RestController
    |        |
    |        +-- Handler trả kết quả
    |        |
    |        +-- C.postHandle()
    |        +-- B.postHandle()
    |        +-- A.postHandle()
    |        |
    |        v
    |     View rendering / xử lý response phù hợp
    |        |
    |        +-- C.afterCompletion()
    |        +-- B.afterCompletion()
    |        +-- A.afterCompletion()
    |
    v
Servlet Filter chain hoàn tất
    |
    v
HTTP response
~~~

Sơ đồ thể hiện thứ tự callback khái niệm khi **cả ba `preHandle` trả `true`**, handler thành công và đang dùng request processing đồng bộ. Ngoài đời có thể có exception, async dispatch, CORS preflight, static resources hoặc custom `HandlerMapping`; không suy rằng request nào cũng đi qua toàn bộ chuỗi.

### 1.1. Phân biệt ba thành phần hạ tầng

- **`HandlerMapping`** quyết định handler nào khớp URL/HTTP method/conditions và chuẩn bị chuỗi interceptors.
- **`HandlerAdapter`** thực thi handler phù hợp, resolve tham số và xử lý return value.
- **`HandlerExecutionChain`** chứa handler cùng danh sách interceptor có hiệu lực, điều phối các callbacks của chúng.

Interceptor chạy sau khi framework **đã chọn được handler**. Vì vậy, nó không phải lớp bao phủ tuyệt đối mọi HTTP request như một Servlet Filter được map phù hợp.

## 2. Hợp đồng HandlerInterceptor trong Spring Framework 6.1

Hình dạng API rút gọn:

~~~java
package org.springframework.web.servlet;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.ModelAndView;

public interface HandlerInterceptor {

    default boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
        return true;
    }

    default void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) throws Exception {
    }

    default void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) throws Exception {
    }
}
~~~

Đây là **minh họa chữ ký phương thức**; interface thực đã nằm trong Spring Framework và có nullability annotations/Javadoc. Không tự tạo một interface trùng package trong project.

| Callback | Thời điểm | Return | Việc thường làm |
| --- | --- | --- | --- |
| `preHandle` | Sau khi handler được chọn, trước khi gọi | `boolean` | Bắt đầu timer, gắn request attribute, quyết định tiếp tục |
| `postHandle` | Sau handler thành công, trước view render | `void` | Bổ sung dữ liệu cho `ModelAndView` ở MVC view |
| `afterCompletion` | Sau khi MVC xử lý hoàn tất ở lượt đồng bộ/dispatch hoàn thành | `void` | Dọn tài nguyên, kết thúc timer, log/metrics |
| `afterConcurrentHandlingStarted` (thuộc `AsyncHandlerInterceptor`) | Khi bắt đầu async và thread ban đầu sắp rời MVC dispatch | `void` | Dọn thread-bound state trong lượt async ban đầu |

Không có callback tên `aroundHandle` trong `HandlerInterceptor`. Nếu muốn bao quanh toàn bộ Servlet chain, xem `Filter`; nếu muốn bao quanh một phương thức Java tùy ý, xem Spring AOP với phạm vi và ngữ nghĩa khác.

### 2.1. Tham số handler là gì?

`handler` có thể là `HandlerMethod` khi request ánh xạ tới annotated controller method, nhưng không phải mọi kiểu mapping đều cung cấp `HandlerMethod`. Có thể kiểm tra:

~~~java
if (handler instanceof HandlerMethod method) {
    String methodName = method.getMethod().getName();
    Class<?> controllerType = method.getBeanType();
}
~~~

Đây là fragment sử dụng trong `preHandle` hoặc callback tương ứng; cần import `org.springframework.web.method.HandlerMethod`. Đừng ép kiểu thẳng sang `HandlerMethod` mà không kiểm tra, vì functional/static-resource/custom handlers có thể khác.

## 3. preHandle: tiếp tục hay dừng chuỗi?

Chữ ký:

~~~java
boolean preHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler
) throws Exception;
~~~

- Trả **`true`**: Spring tiếp tục interceptor kế tiếp; nếu hết chain, gọi handler.
- Trả **`false`**: Spring **không gọi các interceptor còn lại và không gọi handler**. Framework giả định interceptor đã xử lý response hoặc quyết định cách kết thúc phù hợp.
- Ném exception: error-handling path của MVC được kích hoạt; không tương đương với trả `false`.

Ví dụ fragment dùng trong một interceptor:

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    if (request.getRequestURI().endsWith("/demo-stop")) {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        return false;
    }
    return true;
}
~~~

Đây chỉ là **minh họa việc short-circuit**, không phải cách bảo vệ authorization: một kiểm tra suffix URI không phản ánh đầy đủ routing, context path, proxy rewrite hay security policy.

### 3.1. Trả false không tự phát status lỗi

Nếu `preHandle` trả `false` nhưng không set status hoặc ghi response, client có thể nhận phản hồi không như mong đợi, thậm chí 200 rỗng. Muốn từ chối theo policy, phải thiết lập response/status/body rõ ràng **trước khi trả false**, đồng thời đảm bảo không có component khác lại ghi cùng response.

Nếu request cần báo lỗi JSON nhất quán, hãy cân nhắc xử lý bằng `ResponseStatusException`/exception mapping ở controller, `@ControllerAdvice` cho exception phù hợp, hoặc một security/filter layer chuyên trách. Đừng tự viết JSON error body tràn lan trong mỗi interceptor.

### 3.2. Điều kiện dừng không thay quyền truy cập

Spring Framework cảnh báo interceptor không phải lớp security lý tưởng vì path matching của nó có thể lệch với annotated controller matching. Xác thực/phân quyền phải được cấu hình ở **Spring Security filter chain** hoặc cơ chế tương đương phù hợp, không phụ thuộc một interceptor tự kiểm tra URL string.

## 4. postHandle: chạy sau handler thành công

Chữ ký:

~~~java
void postHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    ModelAndView modelAndView
) throws Exception;
~~~

Nó được gọi sau khi `HandlerAdapter` thực thi handler thành công và trước khi `DispatcherServlet` render view, trong **luồng đồng bộ bình thường**. Nếu controller ném exception mà MVC xử lý bằng `HandlerExceptionResolver`, `postHandle` của chuỗi handler ban đầu thường **không được gọi**.

### 4.1. Bổ sung dữ liệu chung cho MVC view

Ví dụ đoạn callback:

~~~java
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) {

    if (modelAndView != null) {
        modelAndView.addObject("supportEmail", "support@example.test");
    }
}
~~~

Nếu controller trả logical view name cùng model và view rendering xảy ra sau callback, biến `supportEmail` có thể được view sử dụng. Đây là trường hợp phù hợp cho `postHandle`. Trái lại, `modelAndView` có thể `null` đối với REST handler trả body trực tiếp, vì vậy luôn kiểm tra trước khi sử dụng.

### 4.2. Với @RestController, quá muộn để sửa body hoặc header

Spring MVC có thể serialize `@ResponseBody`/`ResponseEntity` thành response **ngay trong `HandlerAdapter`**, tức trước `postHandle`. Vì thế:

~~~java
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView mav) {
    response.setHeader("X-Demo", "late"); // Không đáng tin
}
~~~

đây là **ví dụ phản diện**: header có thể không được gửi nếu response đã commit. Muốn thêm header trước khi trả REST body, cân nhắc:

- `preHandle` cho metadata đã biết trước controller.
- `ResponseEntity` trong controller khi header phụ thuộc kết quả nghiệp vụ.
- `ResponseBodyAdvice` khi cần can thiệp vào body/response được xử lý bởi message converter.
- `Filter`/response wrapper nếu cần logic thực sự bao quanh Servlet response và hiểu rõ commit lifecycle.

Không tự tin rằng `postHandle` luôn ghi được header chỉ vì code không ném exception.

## 5. afterCompletion: dọn dẹp khi request đã hoàn tất

Chữ ký:

~~~java
void afterCompletion(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    Exception ex
) throws Exception;
~~~

Ý nghĩa:

- Chạy sau xử lý MVC đã hoàn tất, kể cả sau bước render view trong luồng đồng bộ bình thường.
- Dùng để dọn request-related resources, kết thúc measurement và quan sát status cuối cùng.
- Với nhiều interceptor, callback chạy **ngược thứ tự `preHandle`**.
- **Chỉ gọi cho interceptor mà `preHandle` của nó đã hoàn tất và trả `true`.**
- `ex` có thể là `null`; nó **không bao gồm exception đã được một `HandlerExceptionResolver` xử lý**. Không dùng `ex == null` làm bằng chứng “không có lỗi” trong mọi request.

Ví dụ logic đo thời gian:

~~~java
private static final String START_NS = "com.example.startNano";

@Override
public boolean preHandle(
        HttpServletRequest req,
        HttpServletResponse res,
        Object handler) {
    req.setAttribute(START_NS, System.nanoTime());
    return true;
}

@Override
public void afterCompletion(
        HttpServletRequest req,
        HttpServletResponse res,
        Object handler,
        Exception ex) {
    Object value = req.getAttribute(START_NS);
    if (value instanceof Long start) {
        long elapsedNs = System.nanoTime() - start;
        // Ghi metrics có nhãn giới hạn cardinality.
    }
    req.removeAttribute(START_NS);
}
~~~

Đây là fragment của một interceptor, không phải class độc lập. `System.nanoTime()` dùng đo **elapsed duration**, không dùng để tạo timestamp lưu database. Để đo elapsed time, phép trừ hai giá trị monotonic là phù hợp. Với ứng dụng production, Micrometer Observation/Tracing có thể thích hợp hơn custom metrics.

### 5.1. afterCompletion không phải Servlet Filter finally

`afterCompletion` không nhất thiết chạy trong mọi đường đi trước `DispatcherServlet`: request có thể bị chặn bởi một Filter trước MVC, không tìm được handler, interceptor chưa được gọi hoặc bất đồng bộ chưa hoàn tất. Khi cần dọn tài nguyên đã tạo ở cấp Servlet Filter, nên dùng `try/finally` trong Filter phù hợp với async dispatch thay vì mong `afterCompletion` luôn bọc toàn bộ HTTP lifecycle.

## 6. Nhiều interceptor: thứ tự đi và thứ tự về

Giả sử ba interceptor được đăng ký với thứ tự:

~~~text
A (order 0)
B (order 1)
C (order 2)
~~~

Tất cả `preHandle` đều trả true và controller trả thành công. Chuỗi callback:

~~~text
A.preHandle
B.preHandle
C.preHandle
Controller
C.postHandle
B.postHandle
A.postHandle
View/response completion
C.afterCompletion
B.afterCompletion
A.afterCompletion
~~~

Đây là nguyên tắc **vào theo thứ tự, ra theo thứ tự ngược lại**, tương tự việc lồng các lớp middleware. Không đọc `order=0` là “chạy đầu tiên ở tất cả callbacks”; nó chỉ đến trước trong pre, còn post/after ở phía ngoài cùng chạy sau.

### 6.1. InterceptorRegistry và thứ tự

Cấu hình thường gặp:

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new FirstInterceptor())
            .addPathPatterns("/api/**")
            .order(0);

        registry.addInterceptor(new SecondInterceptor())
            .addPathPatterns("/api/**")
            .order(1);
    }
}
~~~

Đây là **skeleton minh họa**; `FirstInterceptor` và `SecondInterceptor` cần được định nghĩa. Dùng `.order(...)` để thể hiện thứ tự rõ thay vì dựa vào thứ tự incidental của code. Chú ý thứ tự còn bị ảnh hưởng khi có interceptors tự động do framework/custom `HandlerMapping` đăng ký.

### 6.2. Đường dừng sớm ở B

Giả sử `A.preHandle` trả true, `B.preHandle` trả false:

~~~text
A.preHandle -> true
B.preHandle -> false
           -> controller KHÔNG chạy
           -> C.preHandle KHÔNG chạy
           -> không có postHandle cho A/B/C
A.afterCompletion
~~~

**B.afterCompletion không chạy** vì B đã trả false; **C.afterCompletion không chạy** vì C chưa đi vào chain. Đây là chi tiết quan trọng để tránh đặt logic cleanup của B vào callback mà B có thể không bao giờ nhận.

Nếu B đã tạo tài nguyên **trước khi quyết định false**, B cần tự cleanup ngay trước khi return false hoặc chuyển thiết kế sang một abstraction có bảo đảm cleanup phù hợp. Tương tự, nếu `preHandle` của B ném exception, B chưa hoàn thành true nên không nên trông chờ chính B.afterCompletion.

### 6.3. Khi exception xuất hiện

Nếu controller ném exception:

~~~text
A.preHandle -> true
B.preHandle -> true
Controller -> throws Exception
HandlerExceptionResolver / @ControllerAdvice xử lý
B.afterCompletion
A.afterCompletion
~~~

`postHandle` thường bị bỏ qua vì handler không thực thi thành công. `afterCompletion` vẫn chạy đối với các interceptor đã pre=true nếu MVC hoàn tất xử lý tương ứng. Trong `afterCompletion`, `ex` có thể `null` khi exception đã được resolver xử lý. Nếu exception không xử lý được, kết quả có thể khác và exception được chuyển tiếp.

## 7. Ví dụ Java độc lập để nhớ thứ tự callback

Đây là chương trình **Java 17+ độc lập**, mô phỏng nguyên tắc thứ tự. Nó **không phải implementation của Spring HandlerExecutionChain**; dùng để quan sát logic vào/ra và việc dừng giữa chừng.

**ChainOrderDemo.java**

~~~java
import java.util.ArrayList;
import java.util.List;

public class ChainOrderDemo {

    public static void main(String[] args) {
        run(false);
        System.out.println("---");
        run(true);
    }

    private static void run(boolean stopAtB) {
        List<String> entered = new ArrayList<>();

        for (String name : List.of("A", "B", "C")) {
            System.out.println(name + ".pre");

            if (stopAtB && name.equals("B")) {
                // B không trả true, nên không được thêm vào entered.
                after(entered);
                return;
            }
            entered.add(name);
        }

        System.out.println("handler");

        for (int i = entered.size() - 1; i >= 0; i--) {
            System.out.println(entered.get(i) + ".post");
        }

        after(entered);
    }

    private static void after(List<String> entered) {
        for (int i = entered.size() - 1; i >= 0; i--) {
            System.out.println(entered.get(i) + ".after");
        }
    }
}
~~~

Chạy:

~~~bash
javac ChainOrderDemo.java
java ChainOrderDemo
~~~

Stdout chính xác:

~~~text
A.pre
B.pre
C.pre
handler
C.post
B.post
A.post
C.after
B.after
A.after
---
A.pre
B.pre
A.after
~~~

Điểm cần nhớ: `B.pre` ở trường hợp dừng sớm **không kéo theo `B.after`**. Không có controller hoặc post callbacks trong nhánh dừng. Các đặc tính này sẽ được kiểm thử bằng một Spring Boot app thật bên dưới.

## 8. Cấu hình interceptor trong Spring Boot bằng WebMvcConfigurer

Đối với annotated Spring MVC controllers, cách cấu hình phổ biến là triển khai `WebMvcConfigurer#addInterceptors(InterceptorRegistry)`.

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TraceInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**")
            .order(0);
    }
}
~~~

Đây là skeleton: `TraceInterceptor` chưa được định nghĩa. Các pattern dùng chung logic path matching của MVC infrastructure (đặc biệt với Spring Framework 6), nhưng không nên suy rằng cùng một pattern sẽ bao phủ cả Servlet Filter paths hoặc Security matchers theo cách hoàn toàn giống nhau.

### 8.1. addPathPatterns và excludePathPatterns

- `addPathPatterns("/api/**")`: chỉ áp interceptor lên mapping paths tương ứng.
- `excludePathPatterns("/api/public/**")`: không áp lên những routes tương ứng, kể cả khi khớp include pattern.
- Khi không cấu hình include patterns, interceptor có thể áp dụng rộng cho các handlers thuộc HandlerMapping tương ứng.

Không cho rằng một interceptor chỉ áp lên `@RestController`: nó có thể áp dụng với static resources, view controllers hoặc một số handler types khác tùy registration. Cần test đúng URLs và loại handler được chọn.

### 8.2. Interceptor là object sống qua nhiều request

Một interceptor thường được tái sử dụng giữa nhiều request. **Không lưu mutable currentUser, currentRequestId, startTime của request vào instance field** của interceptor:

~~~java
public class BadTimingInterceptor implements HandlerInterceptor {
    private long startedNanos; // Sai khi nhiều request đồng thời
}
~~~

Hai requests chạy cùng lúc sẽ ghi đè `startedNanos`. Dùng local variables, `HttpServletRequest.setAttribute(...)`, Micrometer Observation hoặc một context được thiết kế đúng vòng đời.

### 8.3. @Component và đăng ký thủ công

Nếu interceptor là Spring bean cần inject service/config, có thể tạo `@Component` rồi inject bean vào `WebMvcConfigurer` để đăng ký đúng một lần. Đừng vừa cho framework auto-register cùng một interceptor lẫn đăng ký lại bằng `registry.addInterceptor(...)` tùy ý mà không biết các `HandlerMapping` đang giữ những instances nào.

Trong ví dụ runnable ở phần sau, `new LifecycleInterceptor(...)` được tạo trong config để thứ tự và trạng thái của demo dễ thấy; nó không có dependency cần inject.

## 9. Project runnable: ghi dấu pre, post, after của Spring MVC

Ví dụ hoàn chỉnh dùng **Spring Boot 3.3.13 + Java 21 + Gradle 8.5**, với ba interceptor tên `outer`, `inner`, `gate`. Dữ liệu trace đặt trên **HttpServletRequest attribute** để các requests không chia sẻ mutable trace.

Routes demo:

| URL | Kết quả | Mục tiêu |
| --- | --- | --- |
| `GET /api/ok` | 200 JSON | Thứ tự pre → handler → post → after |
| `GET /api/blocked` | 403 body rỗng | `gate.preHandle` trả false, chuỗi dừng sớm |
| `GET /api/boom` | 500 JSON từ advice | Exception được xử lý, bỏ qua post |
| `GET /api/async` | 200 JSON qua `Callable` | Quan sát `afterConcurrentHandlingStarted` và async redispatch |

**Lưu ý bảo mật:** `gate` chỉ mô phỏng khả năng dừng chain dựa trên đường dẫn thử nghiệm. Không dùng interceptor của demo làm authentication hoặc authorization thật.

Cấu trúc dự án:

~~~text
interceptor-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/interceptors/
    │   ├── InterceptorDemoApplication.java
    │   ├── RequestTrace.java
    │   ├── LifecycleInterceptor.java
    │   ├── WebConfig.java
    │   ├── DemoController.java
    │   └── DemoExceptionAdvice.java
    └── test/java/com/example/interceptors/
        └── InterceptorLifecycleTest.java
~~~

### 9.1. Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'interceptor-lifecycle-demo'
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

### 9.2. Main application

**src/main/java/com/example/interceptors/InterceptorDemoApplication.java**

~~~java
package com.example.interceptors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InterceptorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InterceptorDemoApplication.class, args);
    }
}
~~~

### 9.3. RequestTrace: lưu events trên đúng HTTP request

**src/main/java/com/example/interceptors/RequestTrace.java**

~~~java
package com.example.interceptors;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class RequestTrace {

    private static final String KEY =
        RequestTrace.class.getName() + ".events";

    private RequestTrace() {
    }

    @SuppressWarnings("unchecked")
    private static List<String> events(HttpServletRequest request) {
        Object existing = request.getAttribute(KEY);

        if (existing instanceof List<?>) {
            return (List<String>) existing;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(KEY, created);
        return created;
    }

    public static void record(
            HttpServletRequest request, String event) {
        events(request).add(event);
    }

    public static List<String> snapshot(
            HttpServletRequest request) {
        return List.copyOf(events(request));
    }
}
~~~

Đây là tiện ích demo, không đưa events vào static `List` chia sẻ toàn ứng dụng. Một HTTP request có danh sách riêng; các unit tests có thể đọc danh sách sau MVC dispatch để kiểm tra thứ tự.

Ví dụ **không ghi events từ nhiều async threads cùng lúc**. Nếu production có nhiều nhánh đồng thời cùng sửa request attribute, `ArrayList` không mặc nhiên thread-safe; cần thiết kế thread safety hoặc dùng công cụ tracing phù hợp.

### 9.4. LifecycleInterceptor: ba callbacks và async callback

**src/main/java/com/example/interceptors/LifecycleInterceptor.java**

~~~java
package com.example.interceptors;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public final class LifecycleInterceptor
        implements AsyncHandlerInterceptor {

    private final String name;
    private final boolean blocksDemoRoute;

    public LifecycleInterceptor(
            String name, boolean blocksDemoRoute) {
        this.name = name;
        this.blocksDemoRoute = blocksDemoRoute;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        RequestTrace.record(request, name + ".pre");

        if (blocksDemoRoute
                && request.getRequestURI().endsWith("/api/blocked")) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            // Gate chưa trả true: afterCompletion của gate sẽ không chạy.
            return false;
        }

        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) {

        RequestTrace.record(request, name + ".post");
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        RequestTrace.record(request, name + ".after");
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        RequestTrace.record(request, name + ".async-started");
    }
}
~~~

`blocksDemoRoute` chỉ dùng cho bài test false branch. Trong sản phẩm thật, không dựa vào `endsWith(...)` để bảo vệ route hoặc phân quyền.

### 9.5. Đăng ký ba interceptor đúng thứ tự

**src/main/java/com/example/interceptors/WebConfig.java**

~~~java
package com.example.interceptors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {

        registry.addInterceptor(
                new LifecycleInterceptor("outer", false))
            .addPathPatterns("/api/**")
            .order(0);

        registry.addInterceptor(
                new LifecycleInterceptor("inner", false))
            .addPathPatterns("/api/**")
            .order(1);

        registry.addInterceptor(
                new LifecycleInterceptor("gate", true))
            .addPathPatterns("/api/**")
            .order(2);
    }
}
~~~

Với request `/api/ok`:

~~~text
pre:   outer -> inner -> gate
post:  gate  -> inner -> outer
after: gate  -> inner -> outer
~~~

Với request `/api/blocked`, gate trả false và không ghi trace `gate.after`, còn outer/inner được cleanup ngược lại vì đã trả true.

### 9.6. Controller mô phỏng thành công, dừng, lỗi và async

**src/main/java/com/example/interceptors/DemoController.java**

~~~java
package com.example.interceptors;

import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    public record Message(String message) {
    }

    @GetMapping("/ok")
    public Message ok(HttpServletRequest request) {
        RequestTrace.record(request, "handler");
        return new Message("ok");
    }

    @GetMapping("/blocked")
    public Message blocked(HttpServletRequest request) {
        RequestTrace.record(request, "handler.blocked");
        return new Message("must-not-run");
    }

    @GetMapping("/boom")
    public Message boom(HttpServletRequest request) {
        RequestTrace.record(request, "handler.boom");
        throw new IllegalStateException("demonstration failure");
    }

    @GetMapping("/async")
    public Callable<Message> async(HttpServletRequest request) {
        RequestTrace.record(request, "handler.async");

        // Không đọc HttpServletRequest trong Callable;
        // chỉ trả giá trị immutable có thể serialize khi redispatch.
        return () -> new Message("async-ok");
    }
}
~~~

Đường `/api/blocked` có controller handler để chứng minh nó **không** chạy nếu `gate.preHandle` trả false. Không cần database, không sử dụng mutable state chung giữa requests.

### 9.7. Advice để xử lý lỗi có body xác định

**src/main/java/com/example/interceptors/DemoExceptionAdvice.java**

~~~java
package com.example.interceptors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DemoExceptionAdvice {

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> handle(
            IllegalStateException exception) {

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Map.of("error", "demo-failure"));
    }
}
~~~

Một `@ExceptionHandler` có thể xử lý `IllegalStateException` thành HTTP 500. Trong test, `postHandle` của interceptor chain handler ban đầu không được gọi sau exception, còn `afterCompletion` vẫn dùng để kết thúc phần đã pre=true. `ex` ở afterCompletion không nhất thiết chứa exception đã được resolver xử lý.

### 9.8. Chạy ứng dụng

Với JDK 21 và Gradle wrapper phù hợp:

~~~bash
./gradlew bootRun
~~~

Nếu mới tạo project và chưa có Gradle wrapper nhưng đã cài Gradle hỗ trợ Java 21:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Kiểm tra:

~~~bash
curl -i http://localhost:8080/api/ok
curl -i http://localhost:8080/api/blocked
curl -i http://localhost:8080/api/boom
curl -i http://localhost:8080/api/async
~~~

Kết quả dự kiến:

| Request | HTTP status | Body có ý nghĩa |
| --- | --- | --- |
| `/api/ok` | 200 | `{"message":"ok"}` |
| `/api/blocked` | 403 | Không có body từ controller |
| `/api/boom` | 500 | `{"error":"demo-failure"}` |
| `/api/async` | 200 | `{"message":"async-ok"}` |

**Lưu ý:** danh sách callback events nằm trong request attribute để phục vụ MockMvc test, không xuất ra body trả cho client. Việc `curl` chỉ thấy JSON/status là có chủ đích, tránh nhầm event trace với nội dung response.

## 10. Kiểm thử chính xác thứ tự callback bằng MockMvc

**src/test/java/com/example/interceptors/InterceptorLifecycleTest.java**

~~~java
package com.example.interceptors;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InterceptorLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Test
    void normalRequestRunsAllCallbacksInExpectedOrder()
            throws Exception {

        MvcResult result = mvc.perform(get("/api/ok"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("ok"))
            .andReturn();

        assertEquals(List.of(
            "outer.pre",
            "inner.pre",
            "gate.pre",
            "handler",
            "gate.post",
            "inner.post",
            "outer.post",
            "gate.after",
            "inner.after",
            "outer.after"
        ), RequestTrace.snapshot(result.getRequest()));
    }

    @Test
    void preHandleFalseStopsHandlerAndSkipsItsOwnCleanup()
            throws Exception {

        MvcResult result = mvc.perform(get("/api/blocked"))
            .andExpect(status().isForbidden())
            .andReturn();

        assertEquals(List.of(
            "outer.pre",
            "inner.pre",
            "gate.pre",
            "inner.after",
            "outer.after"
        ), RequestTrace.snapshot(result.getRequest()));
    }

    @Test
    void handledExceptionSkipsPostButRunsAfterCompletion()
            throws Exception {

        MvcResult result = mvc.perform(get("/api/boom"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.error").value("demo-failure"))
            .andReturn();

        assertEquals(List.of(
            "outer.pre",
            "inner.pre",
            "gate.pre",
            "handler.boom",
            "gate.after",
            "inner.after",
            "outer.after"
        ), RequestTrace.snapshot(result.getRequest()));
    }

    @Test
    void asyncHasSpecialInitialPhaseAndLaterRedispatch()
            throws Exception {

        MvcResult started = mvc.perform(get("/api/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        List<String> initial =
            RequestTrace.snapshot(started.getRequest());

        assertTrue(initial.contains("handler.async"));
        assertTrue(initial.contains("outer.async-started"));
        assertFalse(initial.contains("outer.post"));

        MvcResult completed = mvc.perform(asyncDispatch(started))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("async-ok"))
            .andReturn();

        List<String> finalEvents =
            RequestTrace.snapshot(completed.getRequest());

        assertTrue(finalEvents.contains("outer.after"));
        assertTrue(finalEvents.contains("inner.after"));
        assertTrue(finalEvents.contains("gate.after"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Ý nghĩa test:

- **`normalRequest...`** xác minh callback order của ba interceptor.
- **`preHandleFalse...`** xác minh controller không chạy, `gate.after` không chạy, chỉ những interceptor đã pre=true được cleanup.
- **`handledException...`** xác minh advice xử lý lỗi và không có post callbacks của handler thất bại.
- **`asyncHasSpecial...`** xác minh initial async phase nhận callback riêng, không có `postHandle` ngay lúc thread rời dispatch; khi async redispatch hoàn tất thì có after callbacks.

Các code snippets được rà soát theo API Spring MVC; kết quả test bên trên là **kỳ vọng từ source**. Chỉ tuyên bố “đã chạy Gradle test thành công” nếu thực sự chạy tool build và nhận exit code thành công.

`@SpringBootTest` + `@AutoConfigureMockMvc` chạy MVC request chain mà thường không cần lắng nghe socket HTTP thật. Để kiểm thử behavior của Servlet container async timeout, proxy hoặc dispatch types, bổ sung integration test với server thật.

## 11. Request async: AsyncHandlerInterceptor khác luồng đồng bộ

Spring MVC hỗ trợ `Callable`, `WebAsyncTask`, `DeferredResult` và Servlet async dispatch. Trong trường hợp handler khởi động async, DispatcherServlet có thể rời thread ban đầu **không gọi `postHandle` và `afterCompletion` ngay lúc đó** vì kết quả chưa sẵn sàng.

Với `AsyncHandlerInterceptor`, framework gọi:

~~~java
void afterConcurrentHandlingStarted(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler
) throws Exception;
~~~

Nó thay cho `postHandle`/`afterCompletion` của **initial dispatch**. Sau khi có async result và request được dispatch lại, callback chain có thể chạy lại trên một thread khác, gồm pre/post/after theo luồng phù hợp.

~~~text
Initial dispatch thread:
  preHandle
  handler returns Callable / DeferredResult
  async processing begins
  afterConcurrentHandlingStarted
  thread leaves DispatcherServlet

Concurrent computation:
  produces async result on worker/event callback

Async redispatch:
  preHandle invoked again
  adapter processes completed async result
  postHandle
  afterCompletion
~~~

**Không coi toàn bộ quá trình async là một chuỗi đơn giản chỉ có một `preHandle` rồi một `afterCompletion`.** Tùy số dispatch và behavior của framework/container, interceptor có thể nhận callback nhiều lần trong cùng HTTP request.

### 11.1. Timeout hoặc network error

Nếu async request timeout, bị network disconnect hoặc gặp lỗi khi client đã rời đi, có thể không có redispatch/completion flow như dự kiến từ một request thành công. Đừng thiết kế cleanup của thread-local/resource quan trọng dựa hoàn toàn vào `afterCompletion` của đường async.

Với async thực tế cần xem `WebAsyncManager`, `CallableProcessingInterceptor`, `DeferredResultProcessingInterceptor` hoặc callback liên quan tới async lifecycle; timeout/error/cancellation phải được xử lý có chủ đích. `afterConcurrentHandlingStarted` là nơi hợp lý để dọn những thread-bound state mà thread ban đầu không nên giữ.

### 11.2. Đừng giữ ThreadLocal qua thread pool

Với code như:

~~~java
private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();
~~~

dữ liệu `CURRENT` trên Servlet worker thread không tự xuất hiện trên một executor thread. Ngược lại, nếu quên `remove()` trên worker thread được tái sử dụng, request sau có thể thấy dữ liệu cũ.

Ưu tiên truyền snapshot immutable như correlation ID, authenticated principal đã được xác minh, locale hoặc request metadata cần thiết qua API/cơ chế propagation của framework. Không truyền nguyên `HttpServletRequest` vào long-running task khi request đã kết thúc.

## 12. HandlerInterceptor và Servlet Filter khác nhau thế nào?

| Tiêu chí | `HandlerInterceptor` | Servlet `Filter` |
| --- | --- | --- |
| Mức tích hợp | Spring MVC handler mapping | Servlet filter chain |
| Chạy trước chọn handler? | Không; handler đã được mapping | Thường có thể chạy trước `DispatcherServlet` |
| Có biết handler được chọn? | Có tham số `Object handler` | Thường không trực tiếp |
| Callback trước xử lý | `preHandle` | Code trước `chain.doFilter(...)` |
| Callback sau xử lý | `postHandle`/`afterCompletion` với ngữ nghĩa MVC | Code sau `chain.doFilter` và `finally` với dispatch semantics |
| Bao phủ static resources/404 ngoài MVC? | Phụ thuộc `HandlerMapping` và registration | Phụ thuộc filter URL patterns và dispatcher types |
| Can thiệp request/response wrappers | Không phải mục đích chính | Phù hợp hơn với `HttpServletRequestWrapper`/`HttpServletResponseWrapper` |
| Authentication/authorization | Không khuyến nghị làm lớp security chính | Spring Security tích hợp theo Servlet filter chain |
| Xử lý async | `AsyncHandlerInterceptor`, MVC redispatch | Dispatcher types `ASYNC`/`ERROR`, async-aware filter design |

### 12.1. Filter có thể bao quanh DispatcherServlet

Ví dụ fragment:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    long start = System.nanoTime();
    try {
        chain.doFilter(request, response);
    } finally {
        long elapsed = System.nanoTime() - start;
        // Ghi metrics/cleanup phù hợp với Servlet dispatch.
    }
}
~~~

Trong Filter, `chain.doFilter` là điểm tiếp tục chuỗi. Code trong `finally` chạy khi call đó trả về/ném exception, nhưng **đừng tự suy rằng nó luôn đồng nghĩa toàn bộ Servlet async request đã hoàn thành**: thread có thể rời dispatch trước khi async computation kết thúc. Khi cần đo thời gian đến lúc async hoàn tất, phải xử lý async lifecycle riêng.

### 12.2. Nên chọn ở tầng nào?

- **Spring Security**: authentication/authorization/CSRF và các policy bảo mật.
- **Servlet Filter**: inbound/outbound HTTP concerns cần bao phủ sớm, wrapping request/response, request ID ở Servlet boundary.
- **HandlerInterceptor**: metadata biết handler, MVC-specific timing, view model adjustments, tracking theo controller route.
- **ControllerAdvice/ResponseBodyAdvice**: error response schema, tùy biến body/headers khi serialize REST response.
- **AOP**: cross-cutting trong Java services/methods, không thay HTTP lifecycle.

Không viết nhiều lớp cùng xử lý một việc mà không có owner rõ ràng. Một correlation ID có thể được thiết lập ở Filter, đọc ở controller/interceptor và liên kết với Micrometer Tracing nhưng phải có quy tắc propagation và cleanup duy nhất.

## 13. Dùng interceptor để đo thời gian và gắn thông tin request

Một interceptor có thể lấy start time trong `preHandle` rồi đo elapsed trong `afterCompletion`:

~~~java
public final class TimingInterceptor implements HandlerInterceptor {

    private static final String START =
        TimingInterceptor.class.getName() + ".started";

    @Override
    public boolean preHandle(
            HttpServletRequest req,
            HttpServletResponse resp,
            Object handler) {
        req.setAttribute(START, System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest req,
            HttpServletResponse resp,
            Object handler,
            Exception ex) {
        Object started = req.getAttribute(START);
        try {
            if (started instanceof Long ns) {
                long duration = System.nanoTime() - ns;
                // Ghi metric/trace an toàn, không chứa input nhạy cảm.
            }
        } finally {
            req.removeAttribute(START);
        }
    }
}
~~~

Ví dụ này là class minh họa compile được trong Spring MVC project có imports tương ứng (đã lược imports vì trọng tâm là logic). Với **async redispatch**, `preHandle` có thể chạy lần nữa và ghi đè start time, khiến duration chỉ tính dispatch cuối. Nếu muốn đo từ lúc HTTP request bắt đầu tới khi hoàn tất **cả async**, nên dùng đo đạc ở Filter/observation infrastructure hoặc request attribute chỉ set khi chưa có, và xử lý timeout/error cho đúng.

### 13.1. Metrics labels và cardinality

Tránh dùng full URL path chứa ID như `/users/123456` hay header value/userId làm metric label; số lượng label có thể tăng không giới hạn. Nếu cần tags cho controller route, hãy chọn **route template** như `/users/{id}` và giới hạn label values. Spring Boot Actuator/Micrometer có các tính năng observation/metrics; không phải lúc nào cũng cần custom timing interceptor.

### 13.2. Logging và MDC

MDC trong nhiều logging frameworks dựa trên thread-local. Nếu Filter/Interceptor đưa correlation ID vào MDC, phải cleanup đúng thread và tránh nhầm async lifecycle. Một field `MDC.put(...)` ở `preHandle` không tự xuất hiện trong worker thread của `Callable` hoặc executor tùy ý.

Thông thường để instrumentation/tracing chuẩn, nên dùng Micrometer Observation và logging context propagation đã cấu hình; tránh tự nhân bản tracing trong nhiều interceptors.

## 14. Exception handling và afterCompletion.ex

Một điểm tinh tế trong Spring MVC:

~~~java
@GetMapping("/error")
public String error() {
    throw new IllegalArgumentException("invalid");
}
~~~

Nếu một `@ExceptionHandler` bắt exception và tạo response, `afterCompletion(..., ex)` **có thể nhận `null`** vì exception đã được resolver xử lý. Javadoc của `HandlerInterceptor` nói tham số `ex` **không bao gồm exceptions đã được HandlerExceptionResolver xử lý**.

Do đó, không dùng code:

~~~java
if (ex == null) {
    log.info("All good"); // Sai: request có thể đã trả 4xx/5xx.
}
~~~

Hãy dùng kết hợp HTTP status, exception recording/observation và error-handling policy. HTTP status 500 do advice tạo vẫn là error outcome dù `ex` trong afterCompletion không có.

### 14.1. Exception trong preHandle

Nếu một interceptor ném exception trước khi return true, nó chưa được đánh dấu là interceptor đã “entered” thành công. Cleanup của chính nó trong `afterCompletion` không được bảo đảm. Sử dụng `try/finally` cục bộ nếu phải tạo resource rồi code có thể throw trước lúc preHandle hoàn tất.

### 14.2. Exception trong postHandle

`postHandle` tự ném exception cũng khiến request đi vào exception resolution, trong khi `afterCompletion` của các interceptors đã pre=true vẫn có thể chạy khi MVC kết thúc xử lý. Cần tránh code postHandle quá phức tạp; thao tác lỗi ở đây có thể ảnh hưởng error response mà view/controller đã chuẩn bị.

## 15. Interceptor và xử lý response body/view

### 15.1. MVC view response

Với `@Controller` trả view name, `postHandle` có thể thay đổi `ModelAndView` trước khi view engine render HTML. Đây là use case điển hình của interceptor post-processing.

### 15.2. REST response JSON

Với `@RestController`:

~~~java
@GetMapping("/hello")
public Map<String, String> hello() {
    return Map.of("message", "hello");
}
~~~

Jackson/message converter có thể ghi JSON trong `HandlerAdapter`. Nếu muốn chỉnh JSON object toàn cục, xem `ResponseBodyAdvice`, API DTO hoặc serialization policy của Jackson, **không thêm/chỉnh JSON trong `postHandle`**.

### 15.3. Response đã commit

Khi header/body đã commit, không thể thay HTTP status hoặc thêm header một cách chắc chắn. Interceptor `afterCompletion` nên được coi là nơi quan sát/cleanup, không phải nơi trả một HTTP response mới. Khi exception xảy ra sau commit, error handler cũng không thể đổi status 200 đã phát thành 500 hồi tố.

### 15.4. CORS preflight

Một HTTP OPTIONS preflight có thể được framework/proxy xử lý theo CORS configuration trước controller; không giả định custom interceptor sẽ luôn được gọi như các GET/POST requests. CORS nên được cấu hình qua Spring MVC CORS support, Spring Security hoặc gateway theo topology, không cố giải quyết bằng `preHandle` kiểm tra một vài headers.

## 16. Interceptor và Spring Security: không trộn vai trò

Một số lỗi bảo mật xuất hiện khi controller path matcher và interceptor path matcher không đồng nhất, đặc biệt với encoded URLs, reverse proxy prefix, request dispatch và multi-mapping conditions. Nếu kiểm tra authorization trong interceptor bằng cách so sánh chuỗi `request.getRequestURI()`, một request có thể đi qua đường khác mà vẫn tới protected controller.

Khi cần quyền truy cập:

- Dùng **Spring Security SecurityFilterChain**, authorization matchers và method security phù hợp.
- Thiết kế policy theo roles/scopes/ownership thực sự được xác thực, không dựa vào header tự do từ client.
- Test cả endpoints dự kiến được phép và bị từ chối, với HTTP method và path variants.
- Kiểm tra `ERROR`/`ASYNC` dispatch, CORS, CSRF và gateway path rewriting theo kiến trúc ứng dụng.
- Không xem việc `preHandle` trả false/403 trong demo là một mẫu thay thế cho authentication/authorization.

Interceptor rất phù hợp để **đo thời gian và biết tên handler**, nhưng security enforcement có yêu cầu bao phủ request sớm hơn và chính xác hơn.

## 17. WebFlux khác gì?

Trong Spring WebFlux native reactive:

- `DispatcherHandler` phối hợp handlers/reactive results, không phải `DispatcherServlet`.
- `WebFilter` là lựa chọn cross-cutting ở mức reactive web chain.
- `WebFilter.filter(ServerWebExchange, WebFilterChain)` trả `Mono<Void>`.
- `HandlerInterceptor` của Spring MVC yêu cầu `jakarta.servlet.http.HttpServletRequest` và không trực tiếp chạy trên Reactor Netty native request handling.
- Dữ liệu reactive context thường được propagate qua Reactor Context/instrumentation phù hợp, không tự dựa vào Servlet ThreadLocal.

Ví dụ fragment WebFlux:

~~~java
@Component
public class LogWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println("Reactive request finished: " + signal));
    }
}
~~~

Đây là **fragment**; cần imports `WebFilter`, `WebFilterChain`, `ServerWebExchange` và `Mono`. Với real app, đừng log mọi request trực tiếp bằng `System.out` hoặc đưa dữ liệu cá nhân vào log. `doFinally` có thể nhận các tín hiệu completion/error/cancel; không đồng nghĩa tất cả response body đã được client đọc hoàn toàn trên mạng.

Nếu dự án có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn Servlet MVC theo mặc định; xác nhận runtime trước khi dùng Servlet interceptor hay WebFilter.

## 18. Lỗi thường gặp khi dùng HandlerInterceptor

### 18.1. Cho rằng postHandle luôn chạy

Không đúng khi `preHandle` trả false, handler ném exception, hoặc initial async dispatch chưa hoàn tất. Không đặt cleanup bắt buộc chỉ ở postHandle.

### 18.2. Cho rằng afterCompletion luôn chạy nếu object interceptor đã tạo

Không đúng: callback chỉ dành cho interceptor đã `preHandle` trả true trong flow tương ứng, và còn có các ranh giới MVC/async khác.

### 18.3. Dùng instance field chứa request-specific state

Interceptor dùng chung cho nhiều request; mutable shared field gây race/leak. Dùng request attributes, immutable context hoặc observation framework.

### 18.4. Dùng postHandle để sửa header JSON

`@ResponseBody`/`ResponseEntity` có thể đã commit trước postHandle. Đặt logic đúng tầng hoặc dùng `ResponseBodyAdvice`.

### 18.5. Trả false mà không set response

Client có thể nhận status/body không được dự tính. Nếu chủ động short-circuit, phải sở hữu response đó trước khi return false.

### 18.6. Tự dùng interceptor làm security firewall

Không khuyến nghị; dùng Spring Security FilterChain và test URL matching thật.

### 18.7. Không xét async dispatch

Một HTTP request async có thể có nhiều lượt interceptor callbacks, initial `afterConcurrentHandlingStarted` và redispatch. Không dùng assumption mỗi request có đúng một pre/post/after.

### 18.8. Dựa vào ex != null để quyết định mọi lỗi

Exceptions đã được resolver xử lý có thể không còn trong `afterCompletion.ex`. Dùng HTTP status và observation policy.

### 18.9. Đặt excludePathPatterns sai

Ví dụ chỉ include `/api/**` nhưng public endpoint nằm dưới `/v1/**` thì interceptor sẽ không chạy. Cần contract tests cho path includes/excludes và context path/proxy behavior.

### 18.10. Nhầm HandlerInterceptor với ClientHttpRequestInterceptor

`ClientHttpRequestInterceptor` dùng cho **outbound HTTP client** như `RestTemplate`; `HandlerInterceptor` dùng ở **inbound Spring MVC handler dispatch**. Tên giống nhau nhưng lifecycle khác.

### 18.11. Xử lý lỗi 404 bằng interceptor nhưng handler không được map

Nếu không tìm thấy handler phù hợp, có thể không có HandlerExecutionChain mong muốn để chạy interceptor. Dùng Spring MVC error handling, `@ControllerAdvice`/Boot error handling hoặc Filter nếu cần quan sát mọi request ở cấp thấp hơn.

### 18.12. Đăng ký cùng interceptor nhiều lần

Có thể khiến callback/log/metrics nhân đôi. Kiểm tra `WebMvcConfigurer`, custom HandlerMapping và Spring bean registration, không tự đoán framework chỉ chạy mỗi object một lần.

### 18.13. Hiểu nhầm order là thứ tự của mọi callback

Pre chạy theo order, post/after chạy reverse. Các interceptors trước đó có thể được cleanup khi một interceptor sau trả false.

### 18.14. Dùng afterCompletion để ghi response mới

Đây là callback sau hoàn tất, không phải giai đoạn xây response. Header/status đã commit có thể không còn sửa được.

## 19. Checklist code review và vận hành

1. Interceptor có đúng package `org.springframework.web.servlet.HandlerInterceptor` không?
2. Đã phân biệt interceptor với Servlet Filter và Spring Security chưa?
3. `preHandle` trả true/false theo semantics rõ ràng chưa?
4. Nếu preHandle false, response đã được xử lý với status/body phù hợp chưa?
5. Resource do một interceptor tạo trước khi false/throw có được dọn ngay không?
6. Có bao nhiêu interceptors, thứ tự `.order(...)` có được chỉ định rõ không?
7. Đã test pre thuận và post/after ngược chưa?
8. `postHandle` có đang được dùng để sửa header/body của REST response đã commit không?
9. `modelAndView` có thể null, code đã kiểm tra chưa?
10. `afterCompletion` chỉ chạy cho pre=true, code có dựa vào giả định sai không?
11. `ex == null` có bị coi là “request thành công” dù exception đã được resolver xử lý không?
12. Có request async `Callable`/`DeferredResult`, đã xét `AsyncHandlerInterceptor` chưa?
13. Có thể có async redispatch khiến preHandle chạy lần nữa không?
14. Timeout, cancellation và cleanup có được xử lý đúng, không chỉ dựa vào happy path không?
15. Các request attributes/ThreadLocal/MDC có được quản lý theo đúng vòng đời không?
16. Có instance mutable field chia sẻ dữ liệu giữa nhiều HTTP requests không?
17. Include/exclude paths có khớp controller mappings và các gateway prefixes không?
18. Có nhu cầu xử lý request trước DispatcherServlet? Nếu có, Filter phù hợp hơn không?
19. Có dependency vào REST body shape? Nếu có, `ResponseBodyAdvice`/DTO có phù hợp hơn không?
20. Authentication/authorization có đang nằm ở Spring Security thay vì custom interceptor không?
21. Metrics labels có dựa trên route template, tránh cardinality cao và dữ liệu nhạy cảm không?
22. Test đã bao phủ success, early false, handled exception và async dispatch chưa?
23. Đã phân biệt Spring MVC Servlet với WebFlux runtime trước khi cấu hình chưa?
24. HTTP response và logs có correlation ID/trace metadata mà không leak secrets không?

**Kết luận:** `preHandle` là cổng vào trước controller; `postHandle` chạy sau khi handler thành công và phù hợp với việc bổ sung model của MVC view; `afterCompletion` là callback cleanup/observability khi xử lý hoàn tất, **chỉ với interceptor đã pre=true**. Với nhiều interceptor, **đi vào theo order và trở ra theo order ngược**. Khi `preHandle` trả false, controller và các interceptors phía sau không chạy; khi có exception, `postHandle` thường bị bỏ qua; khi async, `afterConcurrentHandlingStarted` thay thế callback của initial dispatch rồi có thể có redispatch. Hãy chọn đúng abstraction: Filter/Security ở vòng ngoài, HandlerInterceptor ở MVC mapping layer, ResponseBodyAdvice cho REST body và các công cụ observation cho metrics/tracing.

## Tài liệu tham khảo

- [Spring Framework 6.1 — HandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html): điều kiện pre=true, reverse order, exception đã được resolver xử lý.
- [Spring Framework 6.1 — AsyncHandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html): `afterConcurrentHandlingStarted`, async dispatch.
- [Spring Framework — MVC Interception](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html): pre/post/after, REST commit và security caution.
- [Spring Framework — MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer.addInterceptors`, mapping patterns.
- [Spring Framework — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult` và Servlet async lifecycle.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): filter chain và các wrapper.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Servlet stack và web configuration.
