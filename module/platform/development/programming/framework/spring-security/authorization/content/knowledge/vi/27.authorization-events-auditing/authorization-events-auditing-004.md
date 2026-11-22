# Đăng ký listener và xác minh vị trí sự kiện được phát trong Spring Security Authorization

Một bản ghi audit hữu ích phải trả lời được **quyết định phân quyền nào xảy ra, tại lớp nào và tại thời điểm nào**. Trong Spring Security dùng Servlet, sự kiện từ chối có thể xuất phát từ kiểm tra quyền theo URL trong filter chain, từ kiểm tra trước khi gọi service (`@PreAuthorize`), hoặc từ kiểm tra sau khi service trả kết quả (`@PostAuthorize`). Đăng ký một `@EventListener` mới chỉ giải quyết việc **nhận** sự kiện; muốn xác định **nơi phát**, cần bật đúng `AuthorizationEventPublisher`, kiểm tra đối tượng đích của sự kiện, quan sát call stack và viết kiểm thử cho từng nhánh.

Bài học dùng **Java 17+, Spring Boot 3.5.x / Spring Security 6.5.x** theo mô hình Spring MVC/Servlet. Tên package, class và endpoint của ví dụ được khai báo đầy đủ để có thể đặt vào một dự án Spring Boot Maven đã có các dependency tương ứng. Nếu dùng Spring Security 7.x hoặc một nhánh khác, đối chiếu API/Javadoc đúng phiên bản đang chạy.

## 1. Phân biệt sự kiện authorization với authentication và audit nghiệp vụ

| Tín hiệu | Dùng để biết điều gì? | Nguồn thường gặp | Có tự phát đầy đủ mọi trường hợp? |
| --- | --- | --- | --- |
| `AuthorizationDeniedEvent` | Một `AuthorizationManager` đã ra quyết định **deny** | `AuthorizationFilter`, interceptor method security | Chỉ khi có publisher được cấu hình ở đường đi đó |
| `AuthorizationGrantedEvent` | Quyết định **grant** | Cùng điểm kiểm tra quyền | **Không phát mặc định** bởi `SpringAuthorizationEventPublisher` trên 6.5 |
| `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent` | Đăng nhập/xác thực thành công hoặc thất bại | `AuthenticationManager`/authentication provider | Cần cơ chế `AuthenticationEventPublisher` tương ứng |
| `AccessDeniedException` / HTTP 403 | Request bị từ chối khi xử lý | Filter, method, CSRF hoặc tầng ứng dụng | **Không đồng nghĩa** chắc chắn có `AuthorizationDeniedEvent` |
| Audit nghiệp vụ | Ai sửa dữ liệu nào, trước/sau, tác động gì? | Code nghiệp vụ hoặc hệ thống audit riêng | Không thể suy ra đầy đủ từ sự kiện kiểm tra quyền |

**Không nhầm tên:** sự kiện `AuthorizationDeniedEvent` thuộc `org.springframework.security.authorization.event`, khác với các event authentication trong `org.springframework.security.authentication.event` và các event cũ thuộc `org.springframework.security.access.event` (nhiều API đã deprecated).

`AuthorizationEventPublisher` là giao diện Spring Security dùng để phát authorization event. `SpringAuthorizationEventPublisher` là adapter chuyển sang `ApplicationEventPublisher` của Spring, để `@EventListener` hoặc `ApplicationListener` nhận được. Có bean listener mà **không có publisher** ở tuyến phân quyền có thể dẫn đến không nhận gì.

## 2. Sự kiện được phát chính xác ở giai đoạn nào?

~~~text
HTTP request
  |
  v
SecurityFilterChain: authentication filters, CSRF, ...
  |
  v
AuthorizationFilter / AuthorizationManager (URL policy)
  |-- deny -----> AuthorizationEventPublisher
  |                '-- AuthorizationDeniedEvent
  |                         '-- Spring ApplicationEventPublisher -> @EventListener
  |-- grant ----> tiếp tục (grant event mặc định không được publish)
  v
DispatcherServlet -> Controller -> Spring-proxied Service
                                  |
                                  +-- AuthorizationManagerBeforeMethodInterceptor
                                  |      @PreAuthorize: check trước method
                                  |      deny -> AuthorizationDeniedEvent -> listener
                                  |      grant -> method được chạy
                                  |
                                  '-- method trả kết quả
                                        |
                                        v
                                     AuthorizationManagerAfterMethodInterceptor
                                       @PostAuthorize: check sau method
                                       deny -> AuthorizationDeniedEvent -> listener
                                       grant -> trả kết quả
~~~

Bảng xác minh nguồn phát:

| Vị trí quyết định | Class cần quan sát bằng debugger | Đối tượng được bảo vệ thường nằm trong `event.getObject()` | Khi bị deny |
| --- | --- | --- | --- |
| Kiểm tra URL | `AuthorizationFilter#doFilter` | `HttpServletRequest` | Controller **chưa** được gọi |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor#invoke` | `MethodInvocation` | Method mục tiêu **chưa** chạy |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor#invoke` | Ngữ cảnh kết quả method, thường `MethodInvocationResult` | Method mục tiêu **đã** chạy |
| Đưa event vào Spring | `SpringAuthorizationEventPublisher#publishAuthorizationEvent` | Đối tượng mà điểm kiểm tra quyền truyền vào | Publisher lựa chọn có publish hay không |
| Listener nhận event | `@EventListener` trên Spring bean | `AuthorizationDeniedEvent<?>` | Thực thi sau lời gọi publish (thường cùng thread nếu multicaster đồng bộ) |

`AuthorizationFilter` thường nằm gần cuối Security filter chain và chạy **trước** Spring MVC. Với method security, Spring AOP proxy tạo interceptor cho `@PreAuthorize`/`@PostAuthorize`; `@EnableMethodSecurity` cần được bật. Gọi service bằng `new` hoặc self-invocation trong cùng class có thể bỏ qua proxy và do đó không có method authorization event.

**Cẩn trọng về số lượng:** một HTTP request có thể đi qua cả kiểm tra URL và method. Nếu URL bị deny, service sẽ không được gọi. Nếu URL grant nhưng service bị deny, event quan sát được phát từ tầng method. Với `FORWARD`, `ERROR` hoặc `ASYNC` dispatch và nhiều interceptor, số lần quyết định có thể khác số request ngoài mạng; **không mặc định “một request = một event”**.

## 3. Đăng ký publisher đúng chỗ

Trong dự án Spring Boot có `spring-boot-starter-web`, `spring-boot-starter-security` và Java 17+, dùng các file sau, tất cả trong package `com.example.securityaudit`. `@EnableMethodSecurity` bật method security; publisher bean phục vụ các điểm kiểm tra authorization có tích hợp Spring Security.

**`src/main/java/com/example/securityaudit/SecurityAuditApplication.java`**

~~~java
package com.example.securityaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityAuditApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/securityaudit/SecurityConfiguration.java`**

~~~java
package com.example.securityaudit;

import jakarta.servlet.DispatcherType;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new SpringAuthorizationEventPublisher(springEvents);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers("/api/admin").hasAuthority("ADMIN")
            .requestMatchers("/api/report", "/api/post")
                .hasAuthority("WEB_USER")
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("web-only")
                .password("{noop}demo123")
                .authorities("WEB_USER")
                .build(),
            User.withUsername("reader")
                .password("{noop}reader123")
                .authorities("WEB_USER", "REPORT_READ", "RESULT_VIEW")
                .build()
        );
    }
}
~~~

Ở ví dụ này, `/api/admin` yêu cầu `ADMIN` nên người dùng demo sẽ bị deny ngay tại filter. `/api/report` và `/api/post` chỉ yêu cầu `WEB_USER` ở filter để request có thể tới service, nơi có rule chi tiết hơn. `DispatcherType.ERROR` được cho qua để xử lý lỗi không bị chuyển thành một lần deny mới trong error dispatch; đây là quyết định riêng cho demo, dự án thật phải xem xét chính sách cho từng dispatcher. `{noop}` dùng duy nhất để minh họa, tuyệt đối không dùng làm cấu hình mật khẩu production.

**Tại sao phải đăng ký `AuthorizationEventPublisher`?** `SpringAuthorizationEventPublisher` là cơ chế phát mà Spring Security hỗ trợ. Với Spring Security 6.5, nó mặc định **chỉ publish denied**, tránh phát dày đặc mỗi lần grant. Khi debug, vì vậy **không thấy event cho 200** là bình thường; đó không chứng minh listener lỗi.

## 4. Đăng ký listener và ghi nhận ngữ cảnh an toàn

Tạo một `@Component` với `@EventListener`. Dùng `event.getObject()` để phân loại nguồn, không dùng `event.getSource()` như một thay thế: `getObject()` là API thể hiện đối tượng đang được kiểm tra quyền.

Ví dụ lưu bộ nhớ để test và log **metadata giới hạn**. Trong production, phần bộ nhớ phải thay bằng cơ chế audit có retention, phân quyền đọc và kiểm soát dữ liệu phù hợp.

**`src/main/java/com/example/securityaudit/AuthorizationAuditListener.java`**

~~~java
package com.example.securityaudit;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import jakarta.servlet.http.HttpServletRequest;
import org.aopalliance.intercept.MethodInvocation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.authorization.method.MethodInvocationResult;
import org.springframework.stereotype.Component;

@Component
public class AuthorizationAuditListener {

    private static final Logger log =
        LoggerFactory.getLogger(AuthorizationAuditListener.class);

    public record Mark(String stage, String operation) {}

    private final Queue<Mark> marks = new ConcurrentLinkedQueue<>();

    @EventListener
    public void denied(AuthorizationDeniedEvent<?> event) {
        Object target = event.getObject();
        Mark mark;

        if (target instanceof HttpServletRequest request) {
            // Demo chỉ dùng các URL cố định, không có query/PII.
            mark = new Mark(
                "HTTP",
                request.getMethod() + " " + request.getRequestURI()
            );
        } else if (target instanceof MethodInvocationResult after) {
            mark = new Mark(
                "METHOD_AFTER",
                after.getMethodInvocation().getMethod().getName()
            );
        } else if (target instanceof MethodInvocation before) {
            mark = new Mark(
                "METHOD_BEFORE",
                before.getMethod().getName()
            );
        } else {
            // Custom AuthorizationManager có thể dùng object type khác.
            mark = new Mark("OTHER",
                target == null ? "unknown" : target.getClass().getSimpleName());
        }

        marks.add(mark);
        log.info("authorization.denied stage={} operation={}",
                 mark.stage(), mark.operation());
    }

    public List<Mark> snapshot() {
        return List.copyOf(marks);
    }

    public void clear() {
        marks.clear();
    }
}
~~~

Listener này **không** log giá trị `Authentication#getCredentials()`, cookie, header `Authorization`, payload, kết quả method, hoặc toàn bộ `HttpServletRequest`/`MethodInvocation`. Trong ứng dụng thật, đường dẫn có ID người dùng/tenant hoặc thông tin bí mật cũng phải được chuẩn hóa trước khi lưu; ở đây endpoint không có biến ID nên mới ghi trực tiếp URI. Việc suy luận `METHOD_BEFORE`/`METHOD_AFTER` từ kiểu object là công cụ quan sát hiệu quả cho demo 6.5; với custom publisher/manager, hãy **kiểm tra object type và call stack thực tế** rồi mở rộng bộ phân loại.

Có thể dùng `ApplicationListener<AuthorizationDeniedEvent<?>>` thay cho `@EventListener`; hai cách đều phải được Spring quản lý. `@EventListener` phù hợp khi cần một hoặc vài handler chuyên biệt. Cần biết default `ApplicationEventMulticaster` của Spring thường giao event đồng bộ trên cùng thread; nếu dự án cấu hình executor/`@Async`, listener có thể chạy bất đồng bộ nên thời gian, thứ tự và `SecurityContextHolder` ở thread mới sẽ khác.

## 5. Tạo ba tình huống để xác minh tầng phát

**`src/main/java/com/example/securityaudit/ReportService.java`**

~~~java
package com.example.securityaudit;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final AtomicInteger beforeCalls = new AtomicInteger();
    private final AtomicInteger afterCalls = new AtomicInteger();

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        beforeCalls.incrementAndGet();
        return "REPORT-42";
    }

    @PostAuthorize("hasAuthority('RESULT_VIEW')")
    public String readSensitiveResult() {
        afterCalls.incrementAndGet();
        return "SENSITIVE";
    }

    public int beforeCalls() {
        return beforeCalls.get();
    }

    public int afterCalls() {
        return afterCalls.get();
    }
}
~~~

**`src/main/java/com/example/securityaudit/AuditController.java`**

~~~java
package com.example.securityaudit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuditController {

    private final ReportService reports;

    public AuditController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/admin")
    public String admin() {
        return "ADMIN";
    }

    @GetMapping("/report")
    public String report() {
        return reports.readReport();
    }

    @GetMapping("/post")
    public String post() {
        return reports.readSensitiveResult();
    }
}
~~~

Các trường hợp khi dùng `web-only/demo123`:

1. `GET /api/admin`: user có `WEB_USER` nhưng không có `ADMIN`. `AuthorizationFilter` deny; controller chưa chạy. Listener dự kiến thấy `Mark("HTTP", "GET /api/admin")`.
2. `GET /api/report`: URL cho phép vì có `WEB_USER`, nhưng `@PreAuthorize` cần `REPORT_READ` nên từ chối **trước** `readReport()`. Listener dự kiến thấy `Mark("METHOD_BEFORE", "readReport")`.
3. `GET /api/post`: URL cho phép; `readSensitiveResult()` đã chạy; `@PostAuthorize` cần `RESULT_VIEW` nên từ chối **sau** method. Listener dự kiến thấy `Mark("METHOD_AFTER", "readSensitiveResult")`.

Khi dùng `reader/reader123`, `/api/report` và `/api/post` đều trả nội dung bình thường. Do default publisher chỉ phát denied, listener không ghi event grant của hai đường đi này.

Tại các điểm deny, việc phát event và việc trả HTTP status là hai trách nhiệm khác nhau. `AuthorizationDeniedEvent` được phát khi authorization manager/interceptor quyết định deny; `AccessDeniedException` (hoặc exception tương ứng) được chuyển thành 403/challenge bởi cơ chế xử lý security. Một listener thành công **không** tự quyết định HTTP status; một controller tự trả `ResponseEntity.status(403)` cũng không mặc nhiên phát authorization event.

## 6. Kiểm thử tự động vị trí phát bằng MockMvc và listener

Thêm `spring-boot-starter-test` và `spring-security-test` ở scope `test`; các dependency ứng dụng như phần trước. Dùng `@WithMockUser` để mô phỏng đúng authority và `@Autowired` bean qua Spring proxy. Bộ đếm trong service chứng minh method **đã/chưa** chạy; `AuthorizationAuditListener.snapshot()` chứng minh listener nhận event.

**`src/test/java/com/example/securityaudit/AuthorizationAuditTests.java`**

~~~java
package com.example.securityaudit;

import jakarta.servlet.http.HttpServletRequest;
import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.event.ApplicationEvents;
import org.springframework.boot.test.context.event.RecordApplicationEvents;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationAuditTests {

    @Autowired MockMvc mvc;
    @Autowired ReportService service;
    @Autowired AuthorizationAuditListener listener;
    @Autowired ApplicationEvents publishedEvents;

    @BeforeEach
    void clearAudit() {
        listener.clear();
    }

    @Test
    @WithMockUser(authorities = "WEB_USER")
    void requestDenialComesFromHttpLayer() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());

        assertTrue(listener.snapshot().stream().anyMatch(m ->
            m.stage().equals("HTTP")
                && m.operation().equals("GET /api/admin")));

        assertTrue(publishedEvents.stream(AuthorizationDeniedEvent.class)
            .anyMatch(e -> e.getObject() instanceof HttpServletRequest));
    }

    @Test
    @WithMockUser(authorities = "WEB_USER")
    void preAuthorizeDenialOccursBeforeServiceCall() throws Exception {
        int calls = service.beforeCalls();
        mvc.perform(get("/api/report"))
            .andExpect(status().isForbidden());

        assertEquals(calls, service.beforeCalls());
        assertTrue(listener.snapshot().stream().anyMatch(m ->
            m.stage().equals("METHOD_BEFORE")
                && m.operation().equals("readReport")));

        assertTrue(publishedEvents.stream(AuthorizationDeniedEvent.class)
            .anyMatch(e -> e.getObject() instanceof MethodInvocation));
    }

    @Test
    @WithMockUser(authorities = "WEB_USER")
    void postAuthorizeDenialOccursAfterServiceCall() throws Exception {
        int calls = service.afterCalls();
        mvc.perform(get("/api/post"))
            .andExpect(status().isForbidden());

        assertEquals(calls + 1, service.afterCalls());
        assertTrue(listener.snapshot().stream().anyMatch(m ->
            m.stage().equals("METHOD_AFTER")
                && m.operation().equals("readSensitiveResult")));
    }

    @Test
    @WithMockUser(authorities = {
        "WEB_USER", "REPORT_READ", "RESULT_VIEW"
    })
    void approvedCallsDoNotCreateDeniedEvents() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT-42"));

        mvc.perform(get("/api/post"))
            .andExpect(status().isOk())
            .andExpect(content().string("SENSITIVE"));

        assertTrue(listener.snapshot().isEmpty());
        assertFalse(publishedEvents.stream(AuthorizationDeniedEvent.class)
            .findAny().isPresent());
    }
}
~~~

Thực thi trong dự án Maven có Spring Boot plugin và dependency đã nêu:

~~~bash
./mvnw test
~~~

Trên Windows chạy `mvnw.cmd test`. **Kỳ vọng** bốn test pass. Dữ liệu `publishedEvents` lấy từ `@RecordApplicationEvents` của Spring Boot, xác minh event thật đã đi qua Spring application event bus; `listener.snapshot()` kiểm tra listener xử lý được. Dự án thật có event đồng bộ và test chạy tuần tự mặc định như ví dụ. Nếu bạn bật async event multicaster hoặc JUnit chạy test song song, cần bổ sung cơ chế await/test isolation thay cho kiểm tra tức thì và queue chia sẻ.

**Tại sao không chỉ kiểm tra 403?** Cả ba test denied có thể trả cùng 403. Chỉ status **không phân biệt** filter URL, `@PreAuthorize` và `@PostAuthorize`. Cặp bằng chứng `event.getObject()` + counter service giúp định vị nguồn phát mà không dựa vào suy đoán từ status.

## 7. Tự xác minh khi chạy ứng dụng

Khởi động trong dự án Maven:

~~~bash
./mvnw spring-boot:run
~~~

Sau đó gọi từng endpoint, có thể dùng `curl`:

~~~bash
# Đường đi URL: từ chối tại AuthorizationFilter
curl -s -o /dev/null -w '%{http_code}\n' \
  -u web-only:demo123 http://localhost:8080/api/admin

# Đường đi @PreAuthorize: từ chối trước readReport()
curl -s -o /dev/null -w '%{http_code}\n' \
  -u web-only:demo123 http://localhost:8080/api/report

# Đường đi @PostAuthorize: từ chối sau readSensitiveResult()
curl -s -o /dev/null -w '%{http_code}\n' \
  -u web-only:demo123 http://localhost:8080/api/post

# Người có đủ quyền: không có denied event
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader123 http://localhost:8080/api/report
~~~

Stdout **kỳ vọng** (mỗi lệnh một dòng):

~~~text
403
403
403
200
~~~

Trong log ứng dụng, tìm thông điệp `authorization.denied stage=... operation=...` do chính listener tạo. Phần log khác (timestamp, thread, Spring Security DEBUG...) phụ thuộc cấu hình nên không trình bày như stdout cố định. Các dấu vết cần có về mặt logic:

~~~text
authorization.denied stage=HTTP operation=GET /api/admin
authorization.denied stage=METHOD_BEFORE operation=readReport
authorization.denied stage=METHOD_AFTER operation=readSensitiveResult
~~~

Ba dòng trên là **mẫu thông điệp sau khi lược bỏ tiền tố logger**, không phải nhật ký đã chạy thực tế. Nếu quan sát khác, dùng `getObject().getClass()` và debugger để xác định loại context chính xác trong phiên bản và cấu hình của bạn.

## 8. Kiểm tra bằng debugger: điểm dừng nào trả lời câu hỏi nào?

Đặt breakpoint trong mã ứng dụng hoặc mã nguồn Spring Security khớp bản dependency:

1. `AuthorizationFilter#doFilter`: xem request/dispatcher và việc gọi `AuthorizationManager`. Nếu deny ở đây, controller chưa chạy.
2. `AuthorizationManagerBeforeMethodInterceptor#invoke`: xem `MethodInvocation` và quyết định trước method. Khi deny, target method chưa chạy.
3. `AuthorizationManagerAfterMethodInterceptor#invoke`: xem kết quả thật và quyết định sau method. Nếu deny, code method đã thực hiện rồi.
4. `SpringAuthorizationEventPublisher#publishAuthorizationEvent`: xem authentication supplier, object đích và kết quả; kiểm tra publisher có cố tình bỏ event grant hay không.
5. `ApplicationEventPublisher#publishEvent` / `SimpleApplicationEventMulticaster#multicastEvent`: xác minh event đã rời publisher và được chuyển đến application listeners.
6. `AuthorizationAuditListener#denied`: xem loại `event.getObject()`, stage do listener suy ra và thread thực thi.

Nếu breakpoint ở `AuthorizationFilter` chạy nhưng `SpringAuthorizationEventPublisher` không chạy, kiểm tra bean và wiring; cũng có thể điểm kiểm tra đang dùng publisher khác hoặc rule không tạo quyết định cụ thể. Nếu breakpoint publisher chạy mà listener không chạy, kiểm tra `@Component`, component scan, type event được đăng ký và cấu hình Spring application events. Nếu listener chạy nhiều lần, kiểm tra loại dispatch, số interceptor, các security filter chains và đường đi nội bộ của request.

Có thể tạm bật logging chẩn đoán:

~~~yaml
logging:
  level:
    org.springframework.security.web.access.intercept.AuthorizationFilter: TRACE
    org.springframework.security.authorization.method: TRACE
~~~

Đây là logging hỗ trợ quan sát; **không** thay thế kiểm thử sự kiện, và thông điệp cụ thể khác nhau theo phiên bản. Nên giữ mức TRACE/DEBUG ở môi trường kiểm thử trong khoảng cần thiết, tránh ghi thông tin nhạy cảm và lượng log quá lớn ở production.

## 9. Phiên bản API và điều kiện để event xuất hiện

- `AuthorizationEventPublisher` và `SpringAuthorizationEventPublisher` có từ Spring Security **5.7**, nhưng các overload và kiểu kết quả thay đổi theo phiên bản. Ở **6.4+**, API dùng thêm `AuthorizationResult`; các overload cũ nhận `AuthorizationDecision` đã được đánh dấu deprecated ở nhánh mới hơn. Đừng tự sao chép implementation publisher từ nhánh 7.x vào 6.2 hoặc 6.5 rồi kỳ vọng chữ ký tương thích.
- `AuthorizationDeniedEvent#getObject()` và `getAuthentication()` cho phép xem đối tượng được bảo vệ và supplier danh tính; `getAuthorizationResult()` có từ **6.4**. Nếu phải hỗ trợ phiên bản thấp hơn, đối chiếu lại Javadoc. Không log nguyên `Authentication`, credentials, arguments hoặc return value.
- Ở Spring Security **6.5**, `SpringAuthorizationEventPublisher` phát event deny; grant không mặc định phát. Sang nhánh **7.0+**, publisher có tùy chọn predicate phát kết quả (`setShouldPublishResult` theo Javadoc nhánh tương ứng); nếu muốn audit grant ở 6.5, cần thiết kế **publisher tùy biến** và giới hạn lượng sự kiện, không chỉ thêm `@EventListener(AuthorizationGrantedEvent.class)`.
- Cấu hình method security phải được bật bằng `@EnableMethodSecurity`, còn HTTP request authorization cần `authorizeHttpRequests` đi qua `AuthorizationFilter`. Với bảo mật cũ dùng `FilterSecurityInterceptor`/`AccessDecisionManager`, tên event và điểm phát có thể khác.
- Sự kiện authentication thất bại cần publisher riêng (chẳng hạn `DefaultAuthenticationEventPublisher`). Request sai mật khẩu bị authentication filter từ chối **chưa chắc từng tới** `AuthorizationFilter`; vì vậy không có `AuthorizationDeniedEvent` là hợp lý.
- CSRF token sai/mất có thể bị từ chối trước authorization; controller/service chủ động trả 403, ném exception hoặc route trả 404 cũng không mặc định trở thành authorization event.

## 10. Thiết kế audit đáng tin cậy: những điểm không được bỏ sót

**Không dùng listener để thay đổi quyết định quyền.** Listener nhận event từ quyết định đã có, không phải nơi sửa `AuthorizationManager`. Listener ném exception hoặc xử lý chậm có thể gây lỗi/độ trễ trong request khi chạy đồng bộ. Nếu cần gửi event tới message broker hoặc SIEM, dùng cơ chế delivery không làm nghẽn request và có chiến lược retry, chống trùng, giám sát mất event.

**Phải có correlation ID và định danh hành động an toàn.** Với request HTTP, có thể truyền request ID/tracing context từ filter. Với method event, dùng method name và operation/business key đã được chuẩn hóa; không serialize toàn bộ `MethodInvocation` hay object trả về. Khi multicaster chạy async, MDC và `SecurityContextHolder` có thể không tự đi theo thread: trích xuất metadata cần thiết tại thời điểm phát hoặc cấu hình context propagation rõ ràng.

**Không đảm bảo exactly-once.** Forward/error dispatch, retries, nhiều check trong một request, nhiều instance ứng dụng và listener fail đều có thể làm trùng hoặc thiếu. Với audit cần kiểm toán pháp lý/transactional, phải thiết kế idempotency, persistence và transactional outbox (khi phù hợp) ở lớp nghiệp vụ; `ApplicationEventPublisher` mặc định là event bus nội bộ process chứ không phải kho audit bền vững.

**Không đánh đồng status với nơi phát.** `403` có thể do URL, method, CSRF hoặc business rule; `401` thường thuộc authentication challenge; `200` có thể là grant hoặc là fallback từ handler che dữ liệu; `404` có thể là route không tồn tại hoặc chính sách ẩn tài nguyên. Chỉ có event object, call stack và tình huống kiểm thử mới giúp khoanh đúng nguồn.

**Lưu cả negative test.** Hãy kiểm tra trường hợp không có publisher, method security chưa bật, service gọi qua `new`/`this`, sai filter chain, sai bean scope, login failure, CSRF denial và request `ERROR` dispatch. Không cần ép mọi thất bại phát cùng một event; mục đích là hiểu chính xác trách nhiệm của từng tầng.

## 11. Checklist triển khai và nghiệm thu

- [ ] Xác minh phiên bản `spring-security-*` đang có trong dependency tree và dùng tài liệu đúng nhánh.
- [ ] Đăng ký bean `AuthorizationEventPublisher` (ví dụ `new SpringAuthorizationEventPublisher(applicationEventPublisher)`).
- [ ] Đăng ký listener Spring bean bằng `@Component + @EventListener` hoặc `ApplicationListener`.
- [ ] Bật `@EnableMethodSecurity` nếu muốn nhận sự kiện từ `@PreAuthorize`/`@PostAuthorize`.
- [ ] Thiết kế ít nhất ba scenario tách biệt: URL deny, method-before deny, method-after deny.
- [ ] Kiểm tra `event.getObject()` và call stack, không suy ra nguồn phát chỉ từ HTTP status.
- [ ] Kiểm thử bằng Spring-managed proxy + `@WithMockUser` và quan sát cả method invocation counter.
- [ ] Kiểm tra `AuthorizationGrantedEvent` không xuất hiện mặc định trên Spring Security 6.5.
- [ ] Phân biệt authentication failure, CSRF denial và domain 403/404 khỏi authorization events.
- [ ] Redact dữ liệu nhạy cảm, giới hạn event volume, chuẩn hóa correlation ID, xem xét concurrency/dispatch.
- [ ] Với audit bắt buộc bền vững: thiết kế cơ chế lưu trữ riêng, retry, dedupe và quyền truy cập phù hợp.

## Tài liệu chính thức

1. [Spring Security 6.5 — Authorization Events](https://www.springframework.org/spring-security/reference/6.5/servlet/authorization/events.html): cách đăng ký publisher, listener, lý do grant không phát mặc định.
2. [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, các điểm kiểm tra request và dispatcher.
3. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, interceptor trước/sau method và denial.
4. [Spring Security 6.5 Javadoc — AuthorizationEventPublisher](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationEventPublisher.html): hợp đồng phát event và thay đổi từ `AuthorizationDecision` sang `AuthorizationResult`.
5. [Spring Security 6.5 Javadoc — AuthorizationDeniedEvent](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html): `getObject()`, `getAuthentication()` và thông tin quyết định.
6. [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): publisher/listener cho sự kiện xác thực.
7. [Spring Boot — Testing Application Events](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@RecordApplicationEvents` và `ApplicationEvents`.

Khi cần trả lời “sự kiện được phát ở đâu?”, bằng chứng đáng tin cậy là **rule bị từ chối**, **điểm chặn tương ứng trong call stack**, **loại `event.getObject()`**, và **test chứng minh method đã/chưa chạy**. Mã 403 hoặc chỉ có dòng log listener không đủ để phân biệt các lớp này.
