# Đăng ký interceptor, phạm vi đường dẫn và AsyncHandlerInterceptor trong Spring MVC

## 1. Mục tiêu và tình huống sử dụng

Trong Spring MVC, một ứng dụng có thể muốn ghi thời gian xử lý theo controller, gắn trace/correlation metadata, bổ sung thông tin trước khi handler chạy hoặc quan sát đường hoàn tất request. `HandlerInterceptor` là extension point được gắn vào một `HandlerExecutionChain` của Spring MVC. Nó khác `Servlet Filter` vì interceptor được chọn sau khi Spring tìm handler, còn filter nằm trong Servlet filter chain bên ngoài `DispatcherServlet`.

Giả sử ứng dụng có bốn đường dẫn:

~~~text
GET /api/orders/7         => áp dụng interceptor
GET /api/reports/async    => áp dụng interceptor và xử lý async
GET /api/public/ping      => cố tình loại trừ
GET /health               => nằm ngoài phạm vi /api/**
~~~

Bài học giải thích cách đăng ký với `WebMvcConfigurer`, `InterceptorRegistry`, `addPathPatterns`/`excludePathPatterns`, thứ tự và lifecycle các callback, khác biệt khi controller dùng `Callable`/`DeferredResult`, cleanup `ThreadLocal` khi chuyển thread, các giới hạn timeout/network error và kiểm thử chính xác bằng MockMvc.

**Phạm vi:** Spring MVC Servlet stack, Java 17+, Spring Boot 3.x và Spring Framework 6.x với namespace `jakarta.servlet`. Spring WebFlux có lập trình request khác. `@Async` trên service method không tự đồng nghĩa với Servlet async request processing.

## 2. Vị trí interceptor trong HTTP pipeline

`HandlerInterceptor` thuộc `HandlerExecutionChain` của Spring MVC: Servlet Filters đã chạy ở tầng container; `DispatcherServlet` và `HandlerMapping` xác định handler trước khi interceptor được gọi. Vì vậy, interceptor có thể biết `HandlerMethod` đã chọn, nhưng không tự bao phủ những request bị Security/Servlet Filter chặn sớm.

~~~text
Servlet Filter chain
    → DispatcherServlet / HandlerMapping
    → A.preHandle → B.preHandle
    → MVC handler + xử lý return value
    → B.postHandle → A.postHandle   (đường đồng bộ thành công)
    → view rendering nếu có
    → B.afterCompletion → A.afterCompletion
~~~

Ba callback có vai trò khác nhau: `preHandle` trả `true` để đi tiếp hoặc `false` để dừng (phải tự hoàn tất response và cleanup phần việc của chính nó); `postHandle` nhận `ModelAndView` có thể null và ở REST có thể quá muộn để sửa body/header; `afterCompletion` chỉ dành cho interceptor đã hoàn tất `preHandle=true`, và tham số `ex` có thể null dù lỗi đã được MVC resolver xử lý. `handler` không nhất thiết là `HandlerMethod`, ví dụ static resource handler.

Với A rồi B, chiều trước handler là A→B và chiều sau là B→A. Nếu B trả `false`, A có thể nhận `afterCompletion` nhưng B không; handler và `postHandle` không chạy. Nếu handler ném exception, `postHandle` thường không chạy còn cleanup áp dụng cho những interceptor đã active. Đó là kiến thức nền cho **registration/path matching** ở mục 3–4 và **ASYNC redispatch** ở mục 5; ví dụ chính về từng nhánh callback, thứ tự và lỗi nằm ở bài chuyên đề `preHandle`/`postHandle`/`afterCompletion`.

## 3. Đăng ký qua WebMvcConfigurer trong Spring Boot

Cách điển hình:

~~~java
@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {

    private final AuditInterceptor audit;

    public MvcConfiguration(AuditInterceptor audit) {
        this.audit = audit;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(audit)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(0);
    }
}
~~~

Đoạn này là **fragment**, cần `AuditInterceptor` đã định nghĩa và imports tương ứng. Chi tiết:
- `addInterceptor(audit)` đăng ký instance interceptor thuộc chain MVC.
- `addPathPatterns("/api/**")` chọn các route thuộc phạm vi API.
- `excludePathPatterns("/api/public/**")` bỏ interceptor ở phần URL đã công bố.
- `order(0)` xếp thứ tự tương đối với registration khác.
- Không khai báo include patterns thường có nghĩa áp dụng cho các path do MVC handler mapping tương ứng xử lý, chứ không có nghĩa mọi request tới toàn bộ server.

Đặt class config trong package mà `@SpringBootApplication` component scan được. Nên để interceptor là Spring bean khi nó cần inject dependencies, thay vì `new` nhiều instance ở nhiều cấu hình khác nhau.

**Không thêm `@EnableWebMvc` chỉ để đăng ký interceptor.** Trong Spring Boot, annotation này thường làm bạn chủ động sở hữu toàn bộ MVC configuration và có thể khiến nhiều Boot MVC auto-config không còn hiệu lực. `WebMvcConfigurer` cho phép bổ sung cấu hình mà vẫn giữ hành vi Boot mặc định.

### 3.1. Thứ tự registration

~~~java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(first)
            .addPathPatterns("/api/**")
            .order(0);

    registry.addInterceptor(second)
            .addPathPatterns("/api/admin/**")
            .order(10);
}
~~~

Fragment cần bean `first` và `second`. Với `/api/admin/report`, cả hai có thể khớp; preHandle từ first tới second, callback hoàn tất ngược chiều. Số thứ tự nhỏ hơn có mức ưu tiên sớm hơn trong registry. Thứ tự các bộ lọc Servlet không bị thay đổi bởi `order` ở đây.

### 3.2. MappedInterceptor bean

Ngoài Java config, Spring MVC hỗ trợ `MappedInterceptor`: một bean chứa include/exclude patterns và interceptor delegate. Ví dụ:

~~~java
@Bean
MappedInterceptor monitoringMapping(AuditInterceptor delegate) {
    return new MappedInterceptor(
            new String[]{"/api/**"},
            new String[]{"/api/public/**"},
            delegate);
}
~~~

Đây là fragment, cần import `@Bean` và `MappedInterceptor`, không đồng thời copy vào demo mục 8. Tài liệu Spring phân biệt: Java `addInterceptors` thường đăng ký vào các `HandlerMapping` do MVC Java configuration quản lý, trong khi `MappedInterceptor` bean có thể được phát hiện bởi các `HandlerMapping` khác, kể cả integration của framework khác.

**Không đăng ký cùng một interceptor hai lần** qua cả bean `MappedInterceptor` và `registry.addInterceptor` cho cùng scope: callback có thể lặp và metrics có thể đếm sai. Chọn một chiến lược, rồi integration-test trên mapping thực tế của ứng dụng.

## 4. Phạm vi đường dẫn và pattern matching

Với cấu hình:

~~~java
registry.addInterceptor(audit)
        .addPathPatterns("/api/**")
        .excludePathPatterns("/api/public/**");
~~~

Các kỳ vọng trong một ứng dụng MVC thông thường:

| Path | Áp dụng? | Giải thích |
| --- | --- | --- |
| `/api/orders/7` | Có | Khớp `/api/**` |
| `/api/reports/async` | Có | Khớp include |
| `/api/public/ping` | Không | Bị exclude |
| `/health` | Không | Ngoài include |
| `/api/deep/nested/path` | Có | Wildcard nhiều path segments |
| `/app/api/orders/7` với context path `/app` | Thường vẫn xét application-relative path `/api/orders/7` | Đừng nhầm context path với route |

`/api/*` thường là một cấp path segment, còn `/api/**` biểu đạt nhiều cấp theo path matcher được cấu hình. Pattern matching được thực hiện trong ngữ cảnh `HandlerMapping`, không nên thay bằng `request.getRequestURI().startsWith(...)` vì context path, URL encoding và servlet mapping.

### 4.1. PathPatternParser và AntPathMatcher

Spring MVC 6 phổ biến sử dụng `PathPatternParser`, khác một số cấu hình cũ dùng `AntPathMatcher`. Khi nâng cấp:
- Không mặc định `/api/items` và `/api/items/` luôn khớp giống nhau; hành vi trailing slash đã thay đổi ở các phiên bản mới.
- Một số wildcard pattern, encoding, matrix parameters và servlet mapping có ngữ nghĩa khác nhau giữa hai hệ matching.
- `**` trong parsed patterns có những giới hạn vị trí nhất định; đừng chuyển các Ant patterns phức tạp sang PathPattern mà không test.
- Nếu chạy dưới context path hoặc reverse proxy, xác minh route mà `HandlerMapping` thực sự xét.

Test path include, exclude và slash variants bằng MockMvc/integration test phù hợp version. Không tự xây logic bảo mật dựa trên so sánh string path thô.

### 4.2. Loại trừ đường dẫn không phải authorization

`excludePathPatterns("/api/public/**")` chỉ bỏ **interceptor đang xét**, không tự tạo chính sách “permit all” hoặc “deny all”. Đặc biệt, Spring chính thức cảnh báo interceptor không phải vị trí lý tưởng để triển khai lớp security chính vì có thể lệch giữa controller path matching và các luật bảo vệ.

Đối với xác thực/phân quyền, dùng Spring Security filter chain/authorization rules. Đối với request metrics hay intercepting controller metadata, interceptor phù hợp hơn. Một request bị security filter từ chối có thể không bao giờ đến interceptor.

### 4.3. Các request không đi qua handler mapping dự kiến

Interceptor có thể không thấy:
- Request bị filter/Security chặn sớm.
- Static resource do Servlet/container hoặc HandlerMapping khác xử lý.
- CORS preflight được MVC xử lý ở nhánh đặc biệt.
- `ERROR`/`FORWARD` dispatch theo cấu hình riêng.
- Actuator endpoints trên management port/context khác.

Nếu cần quan sát mọi request HTTP bất kể có controller hay không, hãy cân nhắc Filter hoặc observability tích hợp ở tầng phù hợp. Đừng suy từ việc interceptor không chạy rằng request chưa hề đến server.

## 5. AsyncHandlerInterceptor khác gì HandlerInterceptor?

`AsyncHandlerInterceptor` kế thừa `HandlerInterceptor` và thêm:

~~~java
void afterConcurrentHandlingStarted(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception;
~~~

Khi controller return `Callable<T>`, `WebAsyncTask<T>` hoặc `DeferredResult<T>` và MVC bắt đầu Servlet async processing, thread Servlet ban đầu được giải phóng trong khi HTTP response vẫn có thể chưa hoàn tất. Vì vậy lifecycle bình thường bị tách thành nhiều lượt dispatch.

### 5.1. Request đồng bộ

~~~text
REQUEST dispatch
  interceptor.preHandle()
  controller runs and returns result
  MVC processes return value / view
  interceptor.postHandle()
  interceptor.afterCompletion()
  request handling completes
~~~

Đây là đường thành công thông thường khi `preHandle` trả true và không có error.

### 5.2. Request bất đồng bộ thành công

~~~text
INITIAL REQUEST DISPATCH — servlet thread:
  preHandle()                             DispatcherType.REQUEST
  controller returns Callable / DeferredResult
  Spring MVC starts async handling
  afterConcurrentHandlingStarted()
  servlet request thread is released

ASYNC COMPUTATION:
  Callable computes result on executor thread,
  or DeferredResult completed by another producer

ASYNC DISPATCH — servlet thread (may be a different thread):
  preHandle()                             DispatcherType.ASYNC
  Spring MVC resumes using concurrent result
  postHandle()                            normal successful completion
  afterCompletion()                       final MVC processing
~~~

**Điểm quan trọng:**
1. Ở lượt ban đầu bắt đầu async, `postHandle` và `afterCompletion` **không gọi ngay**; `afterConcurrentHandlingStarted` được gọi thay thế.
2. Khi kết quả sẵn sàng, container dispatch lại tới `DispatcherServlet`; `preHandle` thường chạy **một lần nữa** trong `ASYNC` dispatch.
3. Controller method **không nhất thiết được gọi lại** trong lượt redispatch; Spring xử lý kết quả đã được worker/event tạo ra.
4. Không mặc định “một HTTP request chỉ gọi preHandle một lần”. Nếu đếm request, tạo trace hoặc kiểm TTL theo số lần preHandle, async redispatch có thể khiến thống kê sai.
5. Sơ đồ không yêu cầu chính xác ba thread vật lý khác nhau; thread pool có thể tái sử dụng threads.

Dùng `request.getDispatcherType()` để phân biệt `REQUEST` và `ASYNC` trong những trường hợp cần. Servlet còn có dispatcher types khác (FORWARD, INCLUDE, ERROR); chúng phụ thuộc container/filter mappings.

### 5.3. Vì sao cần cleanup ở afterConcurrentHandlingStarted?

Một interceptor có thể tạo dữ liệu thread-bound như MDC/logging context/`ThreadLocal`. Khi bắt đầu async, servlet thread đầu chuẩn bị quay về pool, nên **phải dọn dữ liệu mà interceptor đã gắn vào thread đó**. Nếu chỉ dọn tại `afterCompletion`, callback này không chạy trên lượt request ban đầu; thread sẽ có nguy cơ giữ context của client A và rò qua request B.

Ví dụ ý tưởng:

~~~java
@Override
public void afterConcurrentHandlingStarted(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {
    MDC.remove("traceId");
}
~~~

Đoạn trên là fragment, chỉ phù hợp nếu chính interceptor **sở hữu và đã set** key `traceId`; cần import `org.slf4j.MDC`. Không xóa ngẫu nhiên context do tracing library khác quản lý. Sau khi đã dọn thread ban đầu, **không có nghĩa context tự xuất hiện trong Callable worker**: cần truyền metadata rõ ràng hoặc dùng Micrometer Context Propagation/`TaskDecorator` và capture/restore thích hợp.

Nếu còn cần state xuyên dispatch, có thể lưu dữ liệu nhỏ trong request attribute. Đừng xóa attribute ngay ở `afterConcurrentHandlingStarted` rồi mong redispatch vẫn đọc được.

### 5.4. Timeout và network errors

Với async requests, Servlet container có thể timeout hoặc bị ngắt kết nối. Một số đường lỗi **không có successful redispatch**, do đó `postHandle`/`afterCompletion` không được đảm bảo chạy như nhánh thành công.

Để bắt các sự kiện này, dùng extension phù hợp:
- `DeferredResult.onTimeout(Runnable)`, `DeferredResult.onCompletion(Runnable)`.
- `WebAsyncTask` callbacks và timeout cho `Callable`.
- `WebAsyncManager.registerCallableInterceptor(...)` hoặc `registerDeferredResultInterceptor(...)` để quan sát sâu hơn.
- Filter/container async lifecycle nếu trách nhiệm phải nằm ở tầng Servlet, với dispatch mapping chính xác.

Không đặt cleanup của tài nguyên quan trọng **duy nhất** trong `afterCompletion` rồi kết luận mọi kết nối/khóa luôn được giải phóng. Với request hoàn tất muộn, callback completion thường chỉ để dọn/quan sát, không phải lúc nào còn được phép tạo HTTP result mới.

### 5.5. Async MVC không đồng nghĩa reactive non-blocking

`Callable` chạy trên executor; JDBC/blocking HTTP calls vẫn block worker thread. `DeferredResult` cho phép event bên ngoài quyết định lúc hoàn tất mà không cần giữ Servlet request thread trong lúc chờ. Spring WebFlux là framework khác, không dùng nguyên cách hook `AsyncHandlerInterceptor` của Servlet MVC.

Production nên cấu hình bounded `AsyncTaskExecutor`, default timeout, queue policy và error handling. Không dùng executor không giới hạn trong ứng dụng có nhiều request blocking chậm chỉ vì muốn tăng concurrency.

## 6. Những lỗi dễ gặp trước khi thiết kế

| Hiện tượng | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| Header/body không đổi khi viết ở `postHandle` | Response body đã được converter ghi | Dùng `ResponseBodyAdvice` nếu thật sự cần đổi body |
| Metrics request tăng gấp đôi ở API async | `preHandle` chạy ở REQUEST rồi ASYNC dispatch | Đếm một logical request, kiểm dispatcher type |
| MDC bị rò sang user khác | Không dọn thread đầu khi async start | `afterConcurrentHandlingStarted` và context ownership rõ |
| Thread async không có trace context | Không có propagation | Capture/restore explicit hoặc Micrometer/TaskDecorator |
| Timeout không chạy cleanup | Chỉ dựa `afterCompletion` | Async timeout/completion hooks |
| Interceptor không có tác dụng ở static resource | Resource đi qua mapping khác | Đặt logic trong Filter nếu cần toàn Servlet |
| Security bị bypass do exclude path | Dùng interceptor như ACL | Spring Security filter chain |
| Callback lặp bất thường sync | Đăng ký cùng bean hai lần | Chọn registry hoặc MappedInterceptor |
| Boot MVC mất converters | Thêm `@EnableWebMvc` tùy tiện | Dùng `WebMvcConfigurer` |
| Cast `handler` ném `ClassCastException` | Handler không phải `HandlerMethod` | Dùng `instanceof` |
| Handler bị skip nhưng response rỗng | preHandle false mà không set response | Gửi status/body rõ ràng |

## 7. Ứng dụng Java 17 + Spring Boot minh họa

Ứng dụng có bốn route để kiểm scope và async lifecycle:
- `GET /api/items/{id}`: sync JSON, có interceptor.
- `GET /api/async/report`: `Callable<Report>`, có interceptor qua hai lượt dispatch bình thường.
- `GET /api/public/ping`: bị exclude, không có interceptor demo.
- `GET /health`: ngoài include, không có interceptor demo.

Code dùng Spring Boot 3.3.5, Spring MVC và MockMvc, **không cần database**. Header `X-Mvc-Interceptor` và `X-Mvc-Pre-Visits` chỉ để quan sát kỹ thuật; không dùng chúng làm token/authorization state.

### 7.1. Cấu trúc thư mục

~~~text
interceptor-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/interceptordemo/
    │   ├── InterceptorDemoApplication.java
    │   └── web/
    │       ├── RequestTraceInterceptor.java
    │       ├── MvcConfiguration.java
    │       └── DemoController.java
    └── test/java/com/example/interceptordemo/web/
        └── DemoControllerTest.java
~~~

### 7.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'interceptor-demo'
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

Sử dụng Gradle wrapper tương thích Java 17/Spring Boot 3.3. Trên Linux/macOS chạy `./gradlew bootRun`, `./gradlew test`; trên Windows chạy `.\gradlew.bat bootRun`, `.\gradlew.bat test`. Code phụ thuộc Spring nên không chạy `javac` trực tiếp khi thiếu classpath.

### 7.3. Application entry point

`src/main/java/com/example/interceptordemo/InterceptorDemoApplication.java`:

~~~java
package com.example.interceptordemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InterceptorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InterceptorDemoApplication.class, args);
    }
}
~~~

### 7.4. RequestTraceInterceptor

`src/main/java/com/example/interceptordemo/web/RequestTraceInterceptor.java`:

~~~java
package com.example.interceptordemo.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

@Component
public class RequestTraceInterceptor implements AsyncHandlerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestTraceInterceptor.class);
    private static final String STATE_KEY =
            RequestTraceInterceptor.class.getName() + ".state";

    private static final class State {
        private final long startNanos = System.nanoTime();
        private int preVisits;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        State state = (State) request.getAttribute(STATE_KEY);
        if (state == null) {
            state = new State();
            request.setAttribute(STATE_KEY, state);
        }
        state.preVisits++;

        response.setHeader("X-Mvc-Interceptor", "active");
        response.setHeader(
                "X-Mvc-Pre-Visits", Integer.toString(state.preVisits));
        log.debug("pre path={} dispatch={} visits={}",
                request.getRequestURI(), request.getDispatcherType(),
                state.preVisits);
        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) {
        log.debug("post path={} dispatch={}",
                request.getRequestURI(), request.getDispatcherType());
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        log.debug("async-start path={} dispatch={}",
                request.getRequestURI(), request.getDispatcherType());
        // Nếu tự đặt MDC/ThreadLocal trong preHandle,
        // dọn context thuộc Servlet thread ban đầu ở đây.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        State state = (State) request.getAttribute(STATE_KEY);
        if (state != null) {
            long elapsedMs =
                    (System.nanoTime() - state.startNanos) / 1_000_000L;
            log.debug("complete status={} dispatch={} elapsedMs={}",
                    response.getStatus(), request.getDispatcherType(),
                    elapsedMs);
        }
    }
}
~~~

Phân tích:
- `State` gắn vào **request attribute**, không lưu trong bean singleton field chia sẻ mọi user.
- `preVisits` tăng ở mỗi lượt preHandle; sync thường là 1, async thành công sau redispatch thường là 2. Không dùng counter đó làm metric tổng số HTTP requests.
- `postHandle` và `afterCompletion` chỉ log, không cố sửa JSON sau khi converter có thể đã ghi.
- `afterConcurrentHandlingStarted` ghi nhận bước bắt đầu async, và là điểm hợp lý để dọn thread-bound state **do interceptor này tạo**.
- Không log cookie, Authorization header, raw request body hoặc session ID. Với production metrics, ưu tiên route template từ MVC thay vì raw URI chứa ID.

### 7.5. MvcConfiguration

`src/main/java/com/example/interceptordemo/web/MvcConfiguration.java`:

~~~java
package com.example.interceptordemo.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {

    private final RequestTraceInterceptor trace;

    public MvcConfiguration(RequestTraceInterceptor trace) {
        this.trace = trace;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(trace)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(0);
    }
}
~~~

Config này chọn cả route đồng bộ và async trong `/api/**`, trừ nhánh public. Không đăng ký interceptor qua MappedInterceptor lần nữa.

### 7.6. Controller

`src/main/java/com/example/interceptordemo/web/DemoController.java`:

~~~java
package com.example.interceptordemo.web;

import java.util.Map;
import java.util.concurrent.Callable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    public record Item(long id, String status) {}
    public record Report(String status) {}

    @GetMapping("/api/items/{id}")
    public Item item(@PathVariable("id") long id) {
        return new Item(id, "ok");
    }

    @GetMapping("/api/async/report")
    public Callable<Report> asyncReport() {
        return () -> new Report("ready");
    }

    @GetMapping("/api/public/ping")
    public String publicPing() {
        return "pong";
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "up");
    }
}
~~~

`asyncReport` trả đúng `Callable<Report>` cho Spring MVC nên kích hoạt Servlet async processing, sau đó kết quả `Report` được serialize ở lượt completion. Không nhầm với việc gọi một `@Async` service method rồi chặn đợi kết quả.

### 7.7. Test với MockMvc

`src/test/java/com/example/interceptordemo/web/DemoControllerTest.java`:

~~~java
package com.example.interceptordemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void includedApiRouteRunsInterceptor() throws Exception {
        mvc.perform(get("/api/items/7"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Mvc-Interceptor", "active"))
                .andExpect(header().string("X-Mvc-Pre-Visits", "1"))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void excludedPublicRouteHasNoInterceptorHeader() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("X-Mvc-Interceptor"))
                .andExpect(content().string("pong"));
    }

    @Test
    void routeOutsideIncludeHasNoInterceptorHeader() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("X-Mvc-Interceptor"))
                .andExpect(jsonPath("$.status").value("up"));
    }

    @Test
    void asyncDispatchRunsASecondPreHandle() throws Exception {
        MvcResult first = mvc.perform(get("/api/async/report"))
                .andExpect(request().asyncStarted())
                .andExpect(header().string("X-Mvc-Interceptor", "active"))
                .andReturn();

        mvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ready"))
                .andExpect(header().string("X-Mvc-Interceptor", "active"))
                .andExpect(header().string("X-Mvc-Pre-Visits", "2"));
    }
}
~~~

Các test phân biệt:
- Header có ở include route, không có ở exclude và outside route.
- `request().asyncStarted()` xác minh MVC đã bắt đầu async.
- `asyncDispatch(first)` là lượt tiếp tục **cùng logical HTTP request**, không phải gửi một GET mới.
- Hai lượt `preHandle` thể hiện initial REQUEST và ASYNC completion trong đường mẫu. Với error/timeout hoặc một dispatch tùy biến, không coi con số hai là quy luật bất biến.

Chạy `./gradlew test`. MockMvc không thay thế integration tests với Servlet container/load balancer khi cần nghiên cứu thread pools, timeouts và network disconnect.

### 7.8. Quan sát bằng curl

~~~bash
curl -i 'http://localhost:8080/api/items/7'
curl -i 'http://localhost:8080/api/async/report'
curl -i 'http://localhost:8080/api/public/ping'
curl -i 'http://localhost:8080/health'
~~~

Kết quả dự kiến:
- `/api/items/7`: HTTP 200, `{"id":7,"status":"ok"}`, có `X-Mvc-Interceptor: active` và `X-Mvc-Pre-Visits: 1`.
- `/api/async/report`: HTTP 200, `{"status":"ready"}`, thông thường header visits cuối là 2 sau successful async dispatch.
- `/api/public/ping`: HTTP 200, body text `pong`, không có header của interceptor.
- `/health`: HTTP 200, JSON `{"status":"up"}`, không có header của interceptor.

Thread names và elapsedMs trong debug logs không cố định. Endpoint demo không triển khai security và header chỉ phục vụ kiểm tra cơ chế MVC.

## 8. Cấu hình executor và timeout cho production

Spring MVC cho phép mở rộng `WebMvcConfigurer#configureAsyncSupport`. Ví dụ **fragment** (không nằm sẵn trong source app ở mục 7):

~~~java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setTaskExecutor(mvcAsyncExecutor);
    configurer.setDefaultTimeout(5_000L);
}
~~~

`mvcAsyncExecutor` là `AsyncTaskExecutor` đã được inject từ một bean khác; cần import `AsyncSupportConfigurer`. Bean thread pool minh họa:

~~~java
@Bean
public ThreadPoolTaskExecutor mvcAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mvc-async-");
    executor.initialize();
    return executor;
}
~~~

Đây cũng là fragment, cần imports `@Bean` và `ThreadPoolTaskExecutor`. Khi tích hợp vào app thực tế, đảm bảo bean được quản lý một lần, có shutdown/rejection policy phù hợp, executor được inject đúng và các con số được điều chỉnh theo tải/thời gian I/O. Spring MVC default executor cho một số tác vụ async không thích hợp production khi nhiều công việc blocking.

Nếu dùng `DeferredResult`, cũng phải xác định producer/event source hoàn tất response và dọn state khi timeout/cancel.

### 8.1. DeferredResult và callback

~~~java
@GetMapping("/api/deferred")
public DeferredResult<String> deferred() {
    DeferredResult<String> result = new DeferredResult<>(5_000L);
    result.onTimeout(() -> result.setErrorResult(
            new IllegalStateException("Deferred response timed out")));
    result.onCompletion(() -> {
        // Cleanup resource gắn với deferred operation.
    });
    return result;
}
~~~

Fragment không độc lập: cần import `DeferredResult` và một event/worker chủ động gọi `setResult` trước timeout khi có kết quả. Nếu không ai hoàn tất, nó đi vào timeout. `onCompletion` có thể được gọi khi response đã hoàn tất, không nên kỳ vọng có thể ghi thêm body.

## 9. ThreadLocal, MDC và context propagation

Một `ThreadLocal` có vẻ hoạt động với handler sync vì toàn request chạy trên một thread. Với async, cần quan tâm ít nhất ba giai đoạn: Servlet thread ban đầu, worker thread và Servlet thread của redispatch. Chúng **không đảm bảo cùng một thread**.

Nếu interceptor đặt `MDC.put("traceId", ...)` trong `preHandle`:
1. Dọn trên Servlet thread đầu khi bắt đầu async (thường là `afterConcurrentHandlingStarted`).
2. Dùng context propagation có chủ đích nếu Callable cần trace ID.
3. Khi redispatch, có thể dựng lại MDC từ request attribute/tracing context.
4. Dọn đúng key ở cuối lifecycle tương ứng; không xóa context thuộc component khác.

Micrometer Context Propagation, `TaskDecorator` hoặc các cơ chế Spring Security context propagation có thể hỗ trợ; việc chọn API phụ thuộc phiên bản và hệ thống tracing. Đừng tự cho rằng ThreadLocal được Java tự sao chép qua thread pool.

Một request attribute nhỏ có thể giữ request ID/timestamp xuyên async dispatch, nhưng không thay thế cleanup của thread-bound state và không nên chứa credentials hoặc object mutable lớn. Nếu code có nhiều async callbacks cùng đụng một object, cần đồng bộ hoặc immutable state phù hợp.

## 10. Không dùng interceptor như tầng security chính

Spring Framework lưu ý rõ interceptor không lý tưởng để triển khai security bởi đường mapping MVC có thể khác đường request matching của các lớp bảo vệ. Một request có thể bị filter chặn trước interceptor; tương tự, static resources hoặc alternate HandlerMappings có thể bypass interceptor đăng ký chỉ cho MVC.

Dùng:
- **Spring Security** cho authentication, authorization và CSRF policy.
- **Servlet Filter** cho xử lý nằm ngoài MVC handler và request/response wrapping ở tầng Servlet.
- **HandlerInterceptor** cho metadata/quan sát hoặc hook gắn với MVC handler cụ thể.
- **ResponseBodyAdvice** khi cần biến đổi response body theo message conversion, thay vì chỉnh JSON muộn ở postHandle.
- **ControllerAdvice/HandlerExceptionResolver** cho hợp đồng lỗi HTTP.

Nếu kiểm tra annotation trên handler, dùng `handler instanceof HandlerMethod`, không cast mù:

~~~java
if (handler instanceof HandlerMethod method) {
    String name = method.getMethod().getName();
    // Chỉ dùng tên method như metadata nội bộ có chủ đích.
}
~~~

Đoạn trên là fragment, cần import `org.springframework.web.method.HandlerMethod`.

## 11. Các tình huống kiểm thử bổ sung

Với ứng dụng lớn, cần thêm regression tests:
- Hai interceptors có thứ tự; xác minh chiều thuận của preHandle và chiều ngược của postHandle/afterCompletion.
- Interceptor B trả false; handler không chạy, A được dọn, B tự dọn resource của mình.
- Handler ném exception và exception được resolver xử lý; không mặc định `ex` của afterCompletion chứa original exception.
- Path khác context path, servlet mapping và trailing slash; có/không encoded characters.
- Request `OPTIONS`/CORS preflight, static resource và Actuator mapping được cấu hình riêng.
- Async return lỗi và timeout: completion/interceptor callbacks được thực thi theo policy thực tế.
- Worker `Callable` sử dụng logging/security context đúng; thread Servlet được dọn trước khi reuse.
- Production bounded executor, circuit breaker/downstream timeout và response khi queue quá tải.

Không chỉ kiểm tra HTTP 200. Một interceptor có thể “được gọi” nhưng chỉ ở một nhánh và không thực thi cleanup mong muốn. Dùng test double hoặc recorder theo request nếu cần khẳng định thứ tự callback đầy đủ.

## 12. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Giải pháp |
| --- | --- | --- |
| Không thấy interceptor chạy | Config không được component scan hoặc path không match | Xem bean, mapping và test include |
| Exclude không có tác dụng | Pattern sai, đăng ký trùng hoặc matcher khác | Kiểm paths và registrations |
| Mỗi async request bị đếm hai lần | Initial REQUEST + ASYNC redispatch | Phân biệt dispatcher type, dùng request-scoped marker |
| `postHandle` không chạy ngay khi trả `Callable` | Đã bắt đầu async | Dùng `afterConcurrentHandlingStarted` |
| `afterCompletion` không chạy ở timeout | Không có successful final dispatch | Dùng async-specific callbacks |
| Response header đặt ở postHandle bị mất | Response đã commit | Đặt sớm khi phù hợp hoặc đúng response hook |
| MDC của user A xuất hiện ở user B | ThreadLocal không được dọn | Dọn thread context khi async start/complete |
| Async worker thiếu locale/security context | Không truyền context | Explicit propagation/TaskDecorator |
| Kết quả `Callable` không hoàn tất | Executor/timeouts/mapping async support | Kiểm queue, thread pool, timeout, Servlet async config |
| @EnableWebMvc làm biến mất MVC converter | Boot auto-configuration thay đổi | Dùng WebMvcConfigurer khi chỉ thêm interceptor |
| Filter thấy request nhưng interceptor không | Request bị reject sớm hoặc thuộc mapping khác | Chọn đúng tầng hook |
| Có thể bypass authorization | Đặt rule trong interceptor không đủ bao phủ | Spring Security |
| Runtime lỗi khi cast handler | Handler không phải HandlerMethod | Dùng instanceof |

### Trình tự debug

1. Xác nhận URL và HTTP method match handler trong Spring MVC.
2. Kiểm config class/bean interceptor trong application context.
3. Đối chiếu include/exclude patterns với route mà HandlerMapping nhận diện.
4. Log có kiểm soát `DispatcherType` ở preHandle để phân biệt REQUEST và ASYNC.
5. Với async, kiểm `request().asyncStarted()`, executor và việc gọi `asyncDispatch` trong test.
6. Với timeout, dùng callbacks ngoài afterCompletion.
7. Xác minh thread-bound cleanup/propagation không leak.
8. Nếu mục tiêu là security hoặc toàn HTTP, chuyển hook sang đúng filter/Security layer.

## 13. Câu hỏi tự kiểm tra

**1.** `WebMvcConfigurer#addInterceptors` có cần `@EnableWebMvc` trong Spring Boot không?

**Trả lời:** Thường không. Chỉ triển khai WebMvcConfigurer để bổ sung interceptors và giữ Boot MVC auto-configuration.

**2.** `excludePathPatterns("/api/public/**")` có thay Spring Security authorization rules không?

**Trả lời:** Không. Nó chỉ điều chỉnh phạm vi của interceptor đó.

**3.** Với A rồi B, thứ tự callback sync thông thường là gì?

**Trả lời:** A.pre → B.pre → handler → B.post → A.post → B.complete → A.complete.

**4.** Vì sao request trả Callable có thể gọi preHandle hai lần?

**Trả lời:** MVC xử lý lượt REQUEST đầu, bắt đầu async, rồi có lượt ASYNC redispatch sau khi kết quả sẵn sàng.

**5.** Ở lượt đầu bắt đầu async, callback nào được gọi thay postHandle/afterCompletion?

**Trả lời:** `AsyncHandlerInterceptor.afterConcurrentHandlingStarted()`.

**6.** Timeout và client disconnect có bảo đảm postHandle/afterCompletion không?

**Trả lời:** Không. Phải thiết kế callbacks chuyên biệt và kiểm container/error path.

**7.** Dọn ThreadLocal trên Servlet thread có tự chuyển state sang Callable worker không?

**Trả lời:** Không. Cần propagation được xác định rõ.

**8.** Muốn can thiệp body JSON REST sau serialization, có nên mặc định dùng postHandle?

**Trả lời:** Không. Có thể quá muộn; `ResponseBodyAdvice` hoặc message-converter layer phù hợp hơn.

## 14. Tài liệu chính thức

- [Spring Framework — MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer`, registration, patterns và cảnh báo security.
- [Spring Framework 6.1 — AsyncHandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html): callback lúc async start, ASYNC dispatch và timeout caveats.
- [Spring Framework 6.1 — HandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html): `preHandle`, `postHandle` và `afterCompletion`.
- [Spring Framework — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, executor, timeout, context propagation.
- [Spring Framework — MVC Java Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html): `WebMvcConfigurer` và `@EnableWebMvc`.
- [Spring Framework 6.1 — MappedInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/handler/MappedInterceptor.html): dùng bean với include/exclude.
- [Jakarta Servlet 6 — DispatcherType](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype): REQUEST, ASYNC và các dispatch types.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): Filter chain và security boundary.

**Ghi nhớ:** interceptor làm việc quanh Spring MVC handler, có thể giới hạn bằng include/exclude, nhưng không thay Filter/Security. Khi handler bắt đầu async, `afterConcurrentHandlingStarted` được gọi thay cho cặp callback hoàn tất của lượt đầu; `preHandle` có thể chạy lại ở ASYNC redispatch, và timeout/thread context cleanup cần cơ chế riêng. Viết test cho cả path scope lẫn async lifecycle trước khi đưa interceptor vào production.
