# WebAsyncManagerIntegrationFilter và tích hợp Callable của Spring MVC trong Spring Security Servlet

## 1. Vấn đề: SecurityContext gắn với luồng, nhưng Callable chạy ở luồng khác

Trong ứng dụng Spring Security **Servlet** (Spring MVC), thông tin đăng nhập của request thường được truy cập bằng `SecurityContextHolder`:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Dòng trên chỉ là **đoạn Java phụ thuộc Spring Security**, không phải chương trình độc lập. `Authentication` có thể chứa principal, authorities và trạng thái xác thực của request hiện tại. Cách lưu mặc định của `SecurityContextHolder` là **`ThreadLocal`**, tức cùng một giá trị holder không tự xuất hiện ở mọi luồng khác.

Với request đồng bộ, chuỗi xử lý thường nằm trên một luồng Servlet. Với một controller trả về `java.util.concurrent.Callable<T>`, Spring MVC có thể thực thi công việc trên một luồng của executor khác. Nếu không có cầu nối context, lệnh đọc `SecurityContextHolder` **bên trong `Callable`** có thể không thấy authentication từ request ban đầu.

Spring Security cung cấp **`WebAsyncManagerIntegrationFilter`**, kết nối Spring MVC asynchronous request processing với Spring Security. Trong cấu hình filter chain thông thường, filter này đăng ký **`SecurityContextCallableProcessingInterceptor`** với **`WebAsyncManager`** của request. Interceptor chuyển SecurityContext phù hợp tới luồng thực thi `Callable` và dọn holder khi hoàn thành, để controller/service có thể thực thi bảo vệ theo người gọi.

### Ví dụ sử dụng

Người dùng Alice có quyền `REPORT_READ` gọi:

~~~http
GET /api/async/report HTTP/1.1
Host: api.example.test
Authorization: Basic <credentials-minh-hoa>
~~~

Controller trả một `Callable` để chạy tính toán tương đối chậm, còn service được bảo vệ bằng `@PreAuthorize("hasAuthority('REPORT_READ')")`. Khi `Callable` chạy trên worker thread, service cần nhìn thấy identity/quyền của Alice. Nếu context mất, việc kiểm tra quyền có thể từ chối sai; nếu context của người dùng khác còn sót trên thread pool thì có thể xảy ra lỗi bảo mật nghiêm trọng.

**Điều quan trọng:** Spring Security đưa **ngữ cảnh bảo mật** vào `Callable` do Spring MVC quản lý; điều này **không** có nghĩa mọi Thread, `CompletableFuture`, `@Async` hoặc background job đều được tự động truyền context.

## 2. Các thành phần cần nắm rõ

| Thành phần | Vai trò |
| --- | --- |
| `SecurityContextHolder` | Cung cấp SecurityContext gắn với luồng theo strategy, mặc định thường là ThreadLocal |
| `SecurityContext` | Chứa `Authentication` của request, không phải một request hay session object |
| `SecurityContextHolderFilter` / cơ chế context tương ứng | Tải và thiết lập context cho luồng request theo cấu hình Spring Security, rồi dọn theo lifecycle |
| `FilterChainProxy` | Chạy các security filters phù hợp với request |
| `WebAsyncManagerIntegrationFilter` | Đăng ký tích hợp SecurityContext với `WebAsyncManager` của Spring MVC |
| `WebAsyncManager` | Điều phối async request của Spring MVC, hỗ trợ `Callable` và các callbacks |
| `SecurityContextCallableProcessingInterceptor` | Chụp SecurityContext phía request, thiết lập vào worker thread khi Callable chạy và dọn sau đó |
| `AsyncTaskExecutor` | Thực thi Callable của MVC trên luồng worker; cần cấu hình phù hợp tải hệ thống |
| Servlet async dispatch | Cho phép Servlet request được mở trong lúc controller trả sớm, sau đó dispatch kết quả trở lại pipeline |

Tên các lớp và chi tiết filter chain có thể thay đổi theo phiên bản/cấu hình. Bài học dùng **Spring Boot 3.x, Spring Security 6.x, Spring Framework 6.x, Java 17+**. Không nên gán thứ tự filter “luôn là vị trí số N”, vì security chain còn phụ thuộc các cấu hình khác.

Một vài nhầm lẫn phổ biến:

- **`WebAsyncManagerIntegrationFilter` không phải “executor bảo mật”**. Nó đăng ký interceptor cho MVC; executor vẫn do MVC quản lý.
- **`SecurityContextCallableProcessingInterceptor` không tạo ra quyền mới**. Nó dùng authentication đã có từ request; authorization phải tiếp tục được áp dụng.
- **`WebAsyncManager` không đồng nghĩa `WebClient` hoặc Reactor Context**. Đây là cơ chế **Spring MVC Servlet**, không phải Spring WebFlux reactive security.
- **Session, SecurityContext và ThreadLocal là ba khái niệm khác nhau**. Dữ liệu có thể được lưu theo session, nhưng khi Callable chạy trên worker, phải thiết lập context đúng trên luồng đó.
- **Đọc được principal không có nghĩa đã được phép thực hiện tác vụ**. Nếu operation nhạy cảm cần authority riêng, phải áp policy trên URL và/hoặc method/service.

## 3. Luồng thực thi một controller trả Callable

Giả sử cấu hình MVC sử dụng thread pool để chạy `Callable<Map<String, String>>`. Luồng khái niệm như sau:

~~~text
Client HTTP GET /api/async/whoami
               │
               ▼
Servlet container: request thread T1
               │
               ▼
Spring Security FilterChainProxy
  - tải SecurityContext / xác thực user
  - WebAsyncManagerIntegrationFilter
      đăng ký SecurityContextCallableProcessingInterceptor
               │
               ▼
Spring MVC DispatcherServlet + Controller (T1)
               │
               └─ return Callable<T> (chưa chạy body của Callable)
                        │
                        ▼
        WebAsyncManager bắt đầu async processing
        interceptor ghi nhận SecurityContext phù hợp
                        │
                        ▼
        AsyncTaskExecutor: worker thread T2
        interceptor thiết lập SecurityContext vào T2
                        │
                        ▼
        Callable.call() truy cập SecurityContextHolder
        và có thể gọi service được bảo vệ quyền
                        │
                        ▼
        interceptor dọn SecurityContextHolder ở T2
                        │
                        ▼
        Spring MVC nhận concurrent result
        Servlet async dispatch và render HTTP response
                        │
                        ▼
                    Client nhận kết quả
~~~

**Thứ tự quan trọng:**

1. Request ban đầu được xác thực/ủy quyền theo security chain trên T1.
2. Controller **trả về** đối tượng Callable, thay vì chạy nội dung nặng trực tiếp trên T1.
3. Khi MVC bắt đầu concurrent handling, interceptor ghi nhận SecurityContext tương ứng với request trước khi T1 thoát khỏi lần dispatch ban đầu.
4. Trên T2, interceptor thiết lập context cho đoạn gọi Callable; mã trong Callable có thể truy xuất `SecurityContextHolder` như một request có authentication phù hợp.
5. Sau Callable, Spring Security dọn context trên T2, hạn chế việc reuse thread pool làm lộ authentication sang task tiếp theo.
6. Spring MVC thực hiện async dispatch để xử lý kết quả, exception, message conversion và tạo HTTP response.

**Không phải T1 “chuyển nguyên ThreadLocal sang T2”.** Đây là quá trình **chụp, đặt rồi dọn** qua interceptor. Ngữ cảnh được chụp có thể chứa các object references; không nên đồng thời sửa một `Authentication`/`SecurityContext` được nhiều luồng sử dụng và giả định đó là một deep copy độc lập.

Trong vòng đời khác (timeout, error, client disconnect), hành vi cụ thể phụ thuộc MVC, Servlet container và executor. Các thao tác nhạy cảm phải có chính sách timeout/cancellation riêng; không được mặc định coi HTTP timeout là chắc chắn worker đã ngừng mọi side effect.

## 4. Ví dụ chạy trong Spring Boot 3 / Spring Security 6

### 4.1. Dependencies và cấu trúc

Dự án Spring Boot dùng Java 17+ và Spring MVC có thể cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Một cấu trúc file ví dụ:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  SecurityConfig.java
  AsyncWhoAmIController.java
  AsyncMvcConfig.java
src/test/java/com/example/demo/
  AsyncSecurityTest.java
~~~

Nếu khởi tạo dự án Spring Boot từ generator, `DemoApplication.java` là application entry point có `@SpringBootApplication` và `main()`. Các class tiếp theo là **thành phần của dự án Spring**, không phải chương trình độc lập chạy bằng `javac` thuần.

### 4.2. SecurityFilterChain

File `SecurityConfig.java` minh họa endpoint bất đồng bộ chỉ dành cho user đã đăng nhập. Dùng HTTP Basic để test ngắn; ứng dụng thật có thể thay bằng form login, OIDC, JWT hoặc phương thức khác.

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/async/whoami").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Điểm cần hiểu: Spring Security **thường tự đăng ký** `WebAsyncManagerIntegrationFilter` khi xây dựng filter chain cho ứng dụng Servlet. **Không cần tự `addFilterBefore(new WebAsyncManagerIntegrationFilter(), ...)`** như cách chữa lỗi context mất; thêm thủ công sai hoặc lặp filter có thể tạo hành vi khó chẩn đoán.

`authenticated()` ở đây bảo vệ request đầu vào. Với ứng dụng thực tế, các endpoint khác cần được bảo vệ theo yêu cầu; `permitAll()` ở ví dụ **không phải cấu hình production chung**.

Nếu một URL bị loại hẳn khỏi Spring Security bằng `web.ignoring()` hoặc custom filter chain không chạy qua integration filter, không thể mặc định kỳ vọng context propagation như đường MVC bảo vệ thông thường.

### 4.3. Controller trả Callable và đọc authentication trên worker

File `AsyncWhoAmIController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import java.util.concurrent.Callable;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AsyncWhoAmIController {

    @GetMapping("/api/async/whoami")
    public Callable<Map<String, String>> whoAmI() {
        // Spring MVC gọi phần thân lambda ở một worker thread.
        // Không lấy Authentication từ request body/header tùy ý.
        return () -> {
            Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

            if (auth == null || !auth.isAuthenticated()) {
                throw new AuthenticationCredentialsNotFoundException(
                    "No authenticated SecurityContext in worker");
            }

            return Map.of("principal", auth.getName());
        };
    }
}
~~~

Khi Alice đã xác thực hợp lệ, response **minh họa**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"principal":"alice"}
~~~

Đây là body minh họa, không phải output một phiên server đã chạy. HTTP status/header khác có thể được container/Spring bổ sung. Ví dụ chỉ hiển thị tên principal cho chính user đã authenticated, không nên tự trả token, toàn bộ authorities hoặc thông tin tài khoản nhạy cảm vào response.

**Điểm cốt lõi là lệnh đọc ở bên trong lambda.** Nếu controller đọc authentication ở T1 rồi đóng gói sẵn chuỗi `auth.getName()` cho lambda, ví dụ đó **không chứng minh** SecurityContext đã được truyền sang T2.

Đừng dựa vào giả định “Callable luôn tạo một Java thread mới cho mỗi request”: Spring MVC sử dụng executor và có thể tái sử dụng các worker threads. Vì vậy **dọn ThreadLocal** sau task là quan trọng.

### 4.4. Cấu hình executor và timeout cho Spring MVC Callable

Spring MVC cho phép cấu hình executor qua `WebMvcConfigurer#configureAsyncSupport`. Dưới tải cao, không nên dựa vào executor mặc định mà không đo capacity; dùng thread pool có giới hạn và timeout phù hợp.

File `AsyncMvcConfig.java`:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AsyncMvcConfig {

    @Bean("mvcCallableExecutor")
    ThreadPoolTaskExecutor mvcCallableExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(40);
        executor.setThreadNamePrefix("mvc-callable-");
        // Spring quản lý lifecycle của @Bean, gồm khởi tạo/dừng.
        return executor;
    }

    @Bean
    WebMvcConfigurer mvcAsyncConfigurer(
            @Qualifier("mvcCallableExecutor")
            AsyncTaskExecutor executor) {
        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(
                    AsyncSupportConfigurer configurer) {
                configurer.setTaskExecutor(executor);
                configurer.setDefaultTimeout(15_000L);
            }
        };
    }
}
~~~

Các số `4/12/40/15_000` chỉ là **giá trị demo**, không phải thông số tuning khuyến nghị cho mọi server. Lựa chọn theo CPU/IO, queueing, SLA, lưu lượng và giới hạn kết nối downstream.

**Cấu hình executor ở đây không làm thay vai trò của filter**: MVC chọn worker thread; `WebAsyncManagerIntegrationFilter` đăng ký interceptor để SecurityContext có mặt khi Callable chạy. Không nên cấu hình một thread pool vô hạn để né lỗi bị từ chối tác vụ; khi quá tải phải có chính sách backpressure, timeout, 503/429 phù hợp và metrics.

Spring MVC async cũng yêu cầu Servlet container/filter liên quan hỗ trợ asynchronous request processing. Khi custom Servlet Filter, xem `asyncSupported` và dispatcher types theo cấu hình deployment; đừng nhầm lỗi async dispatch với lỗi authentication.

### 4.5. Ví dụ method security chạy trong Callable

Ví dụ đơn giản đọc principal là bước đầu. Ở ứng dụng thật, service thực hiện công việc nhạy cảm nên có kiểm soát quyền độc lập với việc controller chỉ kiểm `authenticated()`.

Với `@EnableMethodSecurity`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Và service bean được gọi từ lambda:

~~~java
package com.example.demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String loadReport() {
        return "ready";
    }
}
~~~

Trong controller có thể inject `ReportService` rồi gọi **bên trong Callable**:

~~~java
@GetMapping("/api/async/report")
public Callable<String> report() {
    return () -> reportService.loadReport();
}
~~~

Đoạn cuối là **minh họa method bên trong controller có field `reportService` đã được inject**; không phải class Java độc lập. Nếu thực hiện đúng qua Spring bean proxy, `@PreAuthorize` đánh giá authentication trên worker thread khi method thực thi. Nếu thiếu context, có thể bị deny; nếu context từ user khác còn sót, đó là lỗi nghiêm trọng.

Bảo đảm URL `/api/async/report` trong thực tế cũng có authorization policy phù hợp; ví dụ `SecurityConfig` ở trên chỉ bảo vệ `/api/async/whoami` để giữ ví dụ ngắn. Không coi kiểm tra bên controller là lý do bỏ method-level checks với nghiệp vụ dùng được từ nhiều điểm gọi.

**Không gọi self-invocation trong cùng bean rồi mong `@PreAuthorize` được áp**: proxy-based method security cần lời gọi đi qua proxy được Spring quản lý.

## 5. Kiểm thử context propagation bằng MockMvc

Để kiểm tra đúng tính năng, cần **kiểm tra dữ liệu đọc trong Callable**, không chỉ mã 200 trên request đồng bộ. File `AsyncSecurityTest.java` dùng Spring Boot Test + Spring Security Test:

~~~java
package com.example.demo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableCanReadOriginalPrincipal() throws Exception {
        MvcResult pending = mvc.perform(
                get("/api/async/whoami").with(user("alice")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"));
    }

    @Test
    void anonymousRequestDoesNotReachProtectedCallable()
            throws Exception {
        mvc.perform(get("/api/async/whoami"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Giải thích kiểm thử:**

- `user("alice")` là post-processor của Spring Security Test, tạo authentication giả trong môi trường test; nó **không chứng minh** password validation thật. Nó giúp kiểm tra integration giữa security filter chain, MVC async và SecurityContext.
- `request().asyncStarted()` xác minh handler thực sự bắt đầu Servlet asynchronous processing.
- `asyncDispatch(pending)` cho MockMvc mô phỏng vòng dispatch sau khi concurrent result hoàn thành; test mới kiểm tra body mà Callable tạo.
- Kiểm tra 401 khi anonymous vì ví dụ cấu hình `httpBasic()`. Nếu đổi sang form login, kết quả có thể là redirect tới login thay vì 401.
- Code test phải chạy trong project Boot có application class, security config, controller và các dependencies đã nêu. Không chạy trực tiếp bằng `java AsyncSecurityTest` mà không có build/test runner.
- Với integration test môi trường thật, bổ sung bảo vệ proxy, session, cookie, token JWT hoặc IdP đúng cách; MockMvc không thay browser/container thật và không tự chứng minh trạng thái thread pool ngoài JVM.

Khi test chạy thành công bằng Maven hoặc Gradle, output cụ thể tùy phiên bản công cụ. Ví dụ chạy:

~~~bash
./mvnw test
# hoặc
./gradlew test
~~~

Với dự án dùng Maven cần `spring-boot-starter-test`/`spring-security-test` tương ứng trong `pom.xml`; snippet dependency mục 4.1 dùng Gradle. Trên Windows có thể chạy `mvnw.cmd test` hoặc `gradlew.bat test`.

### Các ca kiểm thử thêm

1. Trả `Callable` đọc `SecurityContextHolder` trong worker, khẳng định principal và authorities đúng.
2. Gọi từ user A rồi user B trên **cùng pool**; bảo đảm không có cross-request leakage dù thread được reuse.
3. Kiểm tra `@PreAuthorize` trong service gọi từ Callable: có authority thì qua, thiếu authority thì bị từ chối.
4. Test request không authenticated, session hết hạn, JWT sai hoặc resource server auth fail ngay ở request đầu.
5. Test timeout và exception bên trong Callable; response/code lỗi phải phù hợp, không lộ stack trace/token.
6. Test nhiều request song song, worker pool quá tải, queue full và hủy request; không rò SecurityContext sang task kế tiếp.
7. Khi custom nhiều `SecurityFilterChain`, xác nhận URL đi qua đúng chain và filter integration; không chỉ test một endpoint.

## 6. Điều gì KHÔNG được tự động truyền theo?

### 6.1. DeferredResult và CompletableFuture

Spring MVC cũng có kiểu trả về `DeferredResult<T>`. Khác `Callable`, với `DeferredResult` lập trình viên hoặc hệ thống bên ngoài thường điều khiển lúc nào có kết quả và thread nào gọi `setResult(...)`. `WebAsyncManagerIntegrationFilter` **không có hợp đồng bảo đảm tự đưa SecurityContext sang mọi thread được tạo thủ công để hoàn tất DeferredResult**.

Ví dụ (mã minh họa ngữ cảnh, không phải class độc lập):

~~~java
@GetMapping("/api/async/slow")
public DeferredResult<String> slow() {
    DeferredResult<String> result =
        new DeferredResult<>(15_000L);

    executor.execute(() -> {
        // Thread ở đây là do ứng dụng tự sắp xếp;
        // đừng giả định SecurityContextHolder chứa caller.
        result.setResult("done");
    });

    return result;
}
~~~

Nếu code bên trong task cần identity để quyết định quyền, hãy truyền dữ liệu tối thiểu có kiểm chứng hoặc dùng wrapper/delegating executor thích hợp (mục 7), và **kiểm tra quyền nghiệp vụ ở ranh giới cần thiết**. Khi dữ liệu đã được phê duyệt ở request đầu, đôi khi tốt hơn chỉ truyền một command có quyền đã được kiểm tra thay vì giữ nguyên toàn bộ SecurityContext trong tác vụ kéo dài.

Tương tự, việc trả `CompletableFuture`, `CompletionStage`, dùng `@Async` hoặc gọi `ExecutorService.submit(...)` có thể đi qua code không thuộc interceptor Callable tiêu chuẩn. Đừng áp dụng quy tắc “Spring Security tự lo mọi async”.

### 6.2. ThreadLocal khác session và RequestContextHolder

Ngay cả khi SecurityContext đã được chuyển, **mọi ThreadLocal tùy chỉnh khác không tự có mặt**: transaction context, MDC/log correlation ID, tenant resolver, locale, request-scoped dependencies hoặc data source routing có lifecycle riêng.

Spring MVC có một số cơ chế riêng cho request context trên luồng xử lý do framework quản lý, nhưng **không suy ra** custom thread tự tạo cũng có `RequestContextHolder` hoặc đối tượng request/response hợp lệ. Không gửi `HttpServletRequest`/`HttpServletResponse` vào job chạy lâu rồi tiếp tục dùng sau khi response đã kết thúc.

### 6.3. ThreadLocal strategy không phải giải pháp “bật global”

Thấy mất context trên executor, một cách chữa sai là chuyển toàn ứng dụng sang:

~~~java
SecurityContextHolder.setStrategyName(
    SecurityContextHolder.MODE_INHERITABLETHREADLOCAL);
~~~

Dòng này chỉ mang tính minh họa và **không khuyến nghị** như fix tổng quát. `InheritableThreadLocal` truyền giá trị tới *thread mới tạo lúc kế thừa*, nhưng với **thread pool tái sử dụng** có thể mang context cũ, không phản ánh từng request và gây rò user. `MODE_GLOBAL` còn nguy hiểm hơn cho ứng dụng phục vụ nhiều người dùng. Dùng cơ chế propagation có phạm vi và cleanup rõ ràng.

## 7. Nếu thực sự phải chạy task bên ngoài Spring MVC Callable

Khi ứng dụng cần chạy một `Callable` trực tiếp trên `ExecutorService` riêng, Spring Security cung cấp cơ chế **`DelegatingSecurityContextCallable`**, `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextAsyncTaskExecutor` để thiết lập và dọn context quanh tác vụ.

Ví dụ mã trích trong service/controller có `ExecutorService executor`, đang ở luồng đã xác thực:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

// Đoạn minh họa trong method đang có SecurityContext:
// ExecutorService executor được khởi tạo và quản lý lifecycle nơi khác.
SecurityContext captured = SecurityContextHolder.getContext();

Callable<String> task = () -> {
    var auth = SecurityContextHolder.getContext()
        .getAuthentication();
    if (auth == null) {
        throw new IllegalStateException("Authentication missing");
    }
    return auth.getName();
};

Callable<String> secured =
    new DelegatingSecurityContextCallable<>(task, captured);

Future<String> future = executor.submit(secured);
~~~

Đây là **đoạn Java để ghép vào class/logic có executor**, không phải một compilation unit độc lập (các `import` thuộc đầu file). Wrapper quản lý việc thiết lập/dọn SecurityContext khi task chạy. Nó không tự làm auth mạnh hơn, không biến executor thành safe sandbox và không cung cấp cơ chế thu hồi token. Đánh giá xem có thực sự cần **giữ identity đầy đủ** trong background hay chỉ cần truyền ID/tác vụ đã kiểm quyền.

Khi dùng `@Async` hoặc async executor do ứng dụng tự quản, có thể dùng `DelegatingSecurityContextAsyncTaskExecutor` để bọc `AsyncTaskExecutor` phù hợp. **Không cần bọc toàn bộ MVC Callable executor lần nữa chỉ để tạo context** khi `WebAsyncManagerIntegrationFilter` đã đảm nhiệm; tránh làm phức tạp thứ tự capture/cleanup mà không giải quyết nguyên nhân.

Chú ý đặc biệt:

- **Capture đúng thời điểm**: bọc task khi đang ở request có authentication phù hợp, không bọc lúc startup khi SecurityContext rỗng rồi dùng mãi.
- **Không dùng một “superuser context” cho mọi task** trừ khi đó là service identity được thiết kế có kiểm soát; nếu không sẽ trở thành escalation.
- **Thu hồi quyền/sự kiện logout**: task đã được giao và mang context cũ có thể tiếp tục dù phiên bị vô hiệu hóa. Với tác vụ nhạy cảm/đường dài, cần revalidate quyền hoặc hủy theo policy.
- **Cleanup**: wrapper và interceptor giúp tránh leakage giữa các task; không ghi SecurityContext thủ công vào thread pool mà quên finally/clearContext.
- **Error handling**: task thất bại và future bị hủy phải có logging an toàn, retry/backoff giới hạn và tài nguyên được giải phóng.

## 8. Minh họa Java 17 thuần: vì sao ThreadLocal không tự qua worker

Chạy ví dụ không phụ thuộc Spring trước khi học interceptor. File `ThreadLocalDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadLocalDemo {
    public static void main(String[] args) throws Exception {
        ThreadLocal<String> identity = new ThreadLocal<>();
        ExecutorService executor =
            Executors.newSingleThreadExecutor();

        try {
            identity.set("alice");

            String requestThread = identity.get();
            String workerThread = executor.submit(
                () -> {
                    String value = identity.get();
                    return value == null ? "(empty)" : value;
                }
            ).get();

            System.out.println("request=" + requestThread);
            System.out.println("worker=" + workerThread);
        } finally {
            identity.remove();
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
~~~

Stdout **chính xác** với JDK 17+:

~~~text
request=alice
worker=(empty)
~~~

Lý do: `ThreadLocal` của luồng main không tạo bản sao ở thread của executor. Trong Spring Security, `SecurityContextHolder` mặc định cũng dựa vào ThreadLocal; bộ lọc và interceptor liên kết MVC Callable tạo **phạm vi context rõ ràng** cho worker.

Ví dụ này không phải cách tự triển khai Spring Security; nó chỉ minh họa hành vi Java. Không copy nguyên giá trị principal từ ThreadLocal của user sang biến static hoặc global để “sửa” hiện tượng worker rỗng.

## 9. Giới hạn tin cậy và rủi ro bảo mật khi async

### 9.1. Authentication được truyền không tự xác minh lại

Khi MVC Callable chạy, interceptor thường mang context đã được xác thực ở request ban đầu. Điều này **không** nhất thiết kiểm tra lại password, token validity hay nguồn quyền sau mỗi mili giây. Nếu user bị thu hồi quyền hoặc logout giữa lúc đã submit và lúc job thực hiện, có thể xuất hiện cửa sổ dùng context cũ.

Với công việc kéo dài hoặc side effect quan trọng, xác định policy revalidation, kiểm soát quyền ngay trước commit, hủy job hoặc kiểm tra phiên/tài nguyên ở dịch vụ đích. Không coi việc có `Authentication` trên worker là sự bảo đảm quyền không thể thay đổi.

### 9.2. Không nhầm với security context của outbound API

Nếu request nhận Bearer JWT, SecurityContext trong MVC Callable có thể cho code biết user/authorities. Nhưng một HTTP client khác (`RestClient`/`WebClient`) **không tự nhiên** gắn inbound access token vào outbound request. Việc chọn token để gọi downstream cần OAuth2 Client, token exchange hoặc delegated authorization theo trust model, tuyệt đối không chuyển tiếp raw `Authorization` cho URL không đáng tin.

### 9.3. Xử lý timeout và exception

Khi Callable ném lỗi, Spring MVC có thể thực hiện error dispatch/exception resolution theo cấu hình. Với asynchronous request, lỗi từ worker cần được quan sát qua metrics/tracing, trả status/body an toàn và không làm lộ `Authentication`, JWT/Basic credentials hoặc stack trace.

Timeout HTTP không luôn dừng được I/O đang chạy trong Callable. Nếu task tạo side effect, cần idempotency, deadline ở client downstream, cancellation nếu có hỗ trợ và giới hạn số tác vụ. Không nắm giữ database connection/transaction của request thread sang worker một cách tùy tiện; transaction context được quản lý riêng theo thread và transaction boundary.

### 9.4. Tài nguyên và bảo vệ hệ thống

- Thread pool phải giới hạn concurrency, queue size và timeout; đo tỷ lệ từ chối task, latency, p95/p99 và lỗi downstream.
- Với nhiều request của user khác nhau, bảo đảm authentication không bị rò khi executor tái sử dụng thread.
- Đừng lưu `SecurityContext` trong singleton field cho user hiện tại, cache toàn cục hoặc static variable.
- Xem xét session expiry, logout và multi-node infrastructure nếu task async còn chạy khi client đã rời đi.
- Không ghi log raw token, cookie, password, headers nhạy cảm hoặc full SecurityContext/Authentication object.
- Custom filters và reverse proxy có thể xử lý async/error dispatch khác nhau; test đường đi thật, không chỉ local development.
- Khi code cần tenant ID, xác nhận tenant từ principal đáng tin và resource authorization, không chỉ từ header người dùng cung cấp.

## 10. Bảng đối chiếu: tình huống nào có context?

| Hình thức xử lý | SecurityContext có tự được truyền từ request Servlet không? | Cách tiếp cận |
| --- | --- | --- |
| Controller xử lý đồng bộ trong security chain | Có trên request thread theo cấu hình bình thường | Dùng `SecurityContextHolder` trong phạm vi request |
| Spring MVC controller trả `Callable<T>` | **Được tích hợp** qua `WebAsyncManagerIntegrationFilter` khi filter chain phù hợp | Dùng interceptor sẵn có; test bên trong Callable |
| Controller trả `DeferredResult<T>`, task do executor riêng chạy | Không mặc định cho mọi thread bên ngoài MVC Callable | Wrapper/delegating hoặc truyền dữ liệu đã kiểm chứng tối thiểu |
| Task tạo bằng `new Thread(...)` | Không tự truyền theo ThreadLocal mặc định | Không tùy tiện tạo thread; dùng executor và propagation rõ ràng |
| `CompletableFuture.supplyAsync(...)` ở common pool | Không tự truyền theo lời hứa của MVC Callable interceptor | Executor/wrapper phù hợp, kiểm soát lifecycle |
| Service method có `@Async` | Không nên giả định sẽ tự dùng SecurityContext của request | Dùng DelegatingSecurityContextAsyncTaskExecutor nếu thật sự cần |
| Scheduled job không có request | Không có principal người dùng request để truyền | Dùng service identity rõ ràng hoặc cơ chế phân quyền job |
| WebFlux reactive handler | Cơ chế khác Servlet Callable, dựa vào reactive context | Tìm hiểu riêng reactive SecurityContext |

Tùy vào custom filter, async dispatch settings và phiên bản Spring, cần kiểm chứng trong ứng dụng thật. Bảng mô tả **điểm xuất phát của cấu hình chuẩn**, không phải lời đảm bảo cho mọi cách dựng security chain.

## 11. Sai lầm phổ biến và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách điều tra/xử lý |
| --- | --- | --- |
| Trong controller có principal, trong Callable lại null | URL không đi qua filter integration, custom chain/async handling khác thường | Xác nhận FilterChainProxy, WebAsyncManagerIntegrationFilter, MVC Callable thật và test asyncDispatch |
| Service có `@PreAuthorize` trả 403 trong Callable | Context không có trên worker hoặc caller thật thiếu authority | So sánh authentication ở T1/T2 bằng log đã sanitize; kiểm tra method proxy và authorities |
| Async task của user B thấy user A | ThreadLocal bị tự set mà không clear; dùng inheritable strategy trên pool | Loại bỏ global/inheritable workaround, dùng interceptor/wrapper scoped và finally cleanup |
| `Callable` thành công nhưng `CompletableFuture` con mất context | Subtask tạo trên executor khác, nằm ngoài phạm vi Callable interceptor | Propagate ở boundary của subtask hoặc thiết kế lại công việc |
| Test luôn 200 mà không chứng minh propagation | Đọc principal trước khi trả Callable hoặc mock bỏ qua filter chain | Đọc holder **bên trong lambda**, xác nhận asyncStarted/asyncDispatch |
| Request bị 401/302 trước khi Callable chạy | Endpoint cần authentication hoặc session hết hạn | Xác minh security chain, login/Basic/Bearer config và request auth |
| Timeout trả lỗi nhưng job vẫn tác động database | HTTP timeout không chắc đã cancel công việc | Idempotency, deadline, cancellation, kiểm tra quyền trước commit |
| Nhiều request async làm máy chủ kiệt tài nguyên | Executor/queue không giới hạn, I/O blocking, timeout quá dài | Bounded pool, backpressure và observability |
| Lỗi “Async support must be enabled” | Servlet/filter custom không hỗ trợ async hoặc cấu hình dispatcher | Kiểm tra asyncSupported và Servlet registration |
| Sau logout job vẫn chạy với quyền cũ | Context được capture trước khi bị thu hồi | Thiết kế revalidation/hủy job tại thời điểm side effect |
| MDC/tenant/transaction mất trên worker | Không thuộc cơ chế SecurityContextCallableProcessingInterceptor | Propagate từng context theo hợp đồng riêng, quản lý cleanup |
| Cố thêm filter thủ công nhiều lần | Nhầm integration filter với generic async wrapper | Dùng filter chain chuẩn và kiểm tra không đăng ký trùng |

## 12. Checklist nghiệm thu một endpoint async có bảo mật

- [ ] Endpoint nằm trong **Spring Security Servlet filter chain** dự kiến; không bị vô tình bỏ qua.
- [ ] Controller thật sự trả `Callable<T>` và phần logic cần identity chạy bên trong Callable.
- [ ] `WebAsyncManagerIntegrationFilter`/MVC integration hoạt động; không dùng ThreadLocal strategy toàn cục để chữa lỗi.
- [ ] SecurityContext trong worker có đúng principal/authority, không có dữ liệu user khác trên thread được reuse.
- [ ] Quyền endpoint và quyền business operation được kiểm tra đúng thời điểm; không chỉ dựa vào authentication đã capture.
- [ ] Custom MVC executor bị giới hạn tài nguyên, có timeout/queue/cancellation/observability phù hợp.
- [ ] Không coi integration Callable là propagation mặc định cho `DeferredResult`, `CompletableFuture`, `@Async`, scheduled job.
- [ ] Khi có subtask ngoài MVC Callable, propagation rõ ràng bằng wrapper/delegating hoặc truyền dữ liệu an toàn tối thiểu.
- [ ] Test MockMvc thực hiện **asyncStarted → asyncDispatch → kiểm tra principal trong worker**.
- [ ] Test user A/B, không authenticated, thiếu quyền, timeout, concurrent requests, error dispatch và logout/revocation.
- [ ] Log/trace không chứa tokens, cookies, passwords, full SecurityContext hoặc claims nhạy cảm.
- [ ] Những hành động có side effect kiểm soát idempotency, revalidation và trạng thái khi request HTTP đã kết thúc.

**Kết luận:** `WebAsyncManagerIntegrationFilter` là cầu nối **Spring Security Servlet ↔ Spring MVC Callable**. Nó đăng ký `SecurityContextCallableProcessingInterceptor` để chuyển SecurityContext của request sang worker trong phạm vi Callable và dọn sau khi xử lý. Nhờ vậy, code và method security trong Callable có thể nhận đúng authentication, nhưng cơ chế này không thay thế authorization, quản lý thread pool, kiểm soát timeout hoặc propagation riêng cho các tác vụ async khác.
