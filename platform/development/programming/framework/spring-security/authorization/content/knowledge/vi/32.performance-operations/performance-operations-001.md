# Đo độ trễ kiểm tra quyền theo HTTP, phương thức và dữ liệu

## 1. Vì sao cần đo riêng độ trễ phân quyền?

Trong Spring Security, một yêu cầu có thể đi qua nhiều bước: xác thực danh tính, **kiểm tra quyền ở tầng HTTP**, **kiểm tra quyền tại phương thức Java**, rồi **tra cứu quyền dựa trên dữ liệu** như chủ sở hữu, tenant, ACL hoặc trạng thái nghiệp vụ. Mỗi bước có chi phí khác nhau; khi người dùng nói “API chậm vì Spring Security”, thời gian đáp ứng HTTP tổng thể chưa đủ chứng minh phần phân quyền nào là nguyên nhân.

Mục tiêu của bài là biết **đặt đồng hồ ở ranh giới đúng**, thu thập số liệu không làm thay đổi quyết định allow/deny, so sánh các nhóm tình huống công bằng và tìm điểm cần tối ưu mà vẫn giữ nguyên chính sách bảo mật.

Sau bài này, bạn có thể:

1. Phân biệt **thời gian toàn yêu cầu** với **thời gian đưa ra quyết định phân quyền**.
2. Đo riêng ba lớp: **HTTP authorization** (request matcher/AuthorizationManager), **method authorization** (ví dụ @PreAuthorize) và **data-aware authorization** (ACL, owner, tenant, truy vấn dữ liệu).
3. Dùng Micrometer Timer, số lần thực thi, tỷ lệ từ chối, phân vị p50/p95/p99 và trace để điều tra độ trễ.
4. Viết kiểm thử Spring Security + MockMvc xác nhận các đồng hồ ghi nhận đúng lớp, đồng thời kiểm tra người thiếu quyền thật sự bị chặn.
5. Thiết kế phép đo dưới tải có kiểm soát, không nhầm sai số, cache hay chi phí của toàn ứng dụng thành chi phí đánh giá quyền.
6. Giữ số lượng tag của metrics ở mức kiểm soát được và không tiết lộ danh tính/tài nguyên nhạy cảm.

**Phạm vi:** Spring MVC/Servlet, Java 17+, Spring Boot 3.x với Spring Security 6.x. Một số API minh họa được cố định cho dòng Spring Security 6.4+ để dễ đọc; khi dùng Spring Security 7 hoặc reactive security, đối chiếu API/đường chạy thực tế của phiên bản đó.

## 2. Mô hình ba tầng và ranh giới cần đo

~~~text
Client
  │
  │  Tổng thời gian HTTP: kết nối + filters + controller + service
  ▼
SecurityFilterChain
  ├── Xác thực (authentication)                 [đo riêng nếu cần]
  ├── Quyết định quyền HTTP                     [T_http_auth]
  │      URL + HTTP method + GrantedAuthority
  ▼
Controller
  ▼
Spring AOP proxy của service
  ├── Quyết định quyền tại phương thức          [T_method_auth]
  │      @PreAuthorize / AuthorizationManager
  ▼
Service / nghiệp vụ
  ├── Chính sách dựa trên dữ liệu               [T_data_auth]
  │      ACL, ownership, tenant, query repository
  ▼
Database / cache / ứng dụng trả response
~~~

| Chỉ số | Đặt đồng hồ ở đâu? | Bao gồm | Không bao gồm |
| --- | --- | --- | --- |
| Toàn bộ HTTP request | Quan sát HTTP server của Spring Boot/Actuator | Filter chain, controller, nghiệp vụ, truy vấn, tạo response trong phạm vi instrument | Không tách được riêng quyết định quyền |
| HTTP authorization | Bọc AuthorizationManager dùng trong authorizeHttpRequests | Thời gian delegate đánh giá rule HTTP; có thể gồm lấy Authentication từ Supplier | Thân controller, service, DB nghiệp vụ phía sau |
| Method authorization | Bọc AuthorizationManager của interceptor @PreAuthorize | Thời gian đánh giá điều kiện method, SpEL, lấy thông tin người gọi | Thân phương thức nếu dùng pre-authorization đơn giản |
| Data authorization | Đo trực tiếp policy hoặc repository tra quyền | So sánh tenant, owner, ACL; có thể gồm round-trip DB/cache nếu đặt trong vùng đo | Không tự động là thời gian toàn service |
| Truy vấn ACL/database | Instrument repository/DB span thực tế | Truy vấn/đọc dữ liệu quyền, chờ kết nối nếu nằm trong span | Java kiểm tra quyền sau khi có dữ liệu, trừ khi span bao quanh cả hai |

**Ranh giới quyết định ý nghĩa số liệu.** Nếu @PreAuthorize gọi một bean chính sách qua SpEL, ví dụ @PreAuthorize("@policy.canRead(authentication,#p0)"), thì **T_method_auth có thể chứa T_data_auth**; hai số đo bị lồng nhau. Nếu service thực hiện kiểm tra dữ liệu **sau** @PreAuthorize, như ví dụ ở mục 5, hai khoảng thời gian không lồng nhau. Trong cả hai trường hợp, **không cộng** các timer thành “tổng HTTP” hoặc coi phép trừ đơn giản là chi phí tuyệt đối của một lớp: còn các bước khác, độ trễ đo, GC, scheduling và độ lệch ranh giới.

### 2.1. Phân biệt quyết định allow và deny

Kết quả bị từ chối có thể **nhanh hơn** vì dừng từ đầu, hoặc **chậm hơn** nếu phải tra DB/ACL trước khi biết nên từ chối. Báo cáo một p95 chung của tất cả quyết định có thể che các khác biệt lớn. Nên phân nhóm:

- **layer:** http, method, data.
- **result:** allow, deny, abstain (nếu manager có trạng thái không ra quyết định), error.
- **operation:** một nhãn hữu hạn được chuẩn hóa, ví dụ document-read; chỉ thêm khi thực sự có nhu cầu.
- **authentication_type/route:** nếu cần, dùng nhóm hữu hạn như jwt/session/basic và mẫu URI, không lấy token hay URL gốc.

**Denied** không đồng nghĩa một Java exception được ném ở chính hàm đánh giá: một AuthorizationManager thường trả kết quả không cho phép; interceptor hoặc filter xử lý phản hồi phù hợp. **Error** là lỗi thực thi của bộ đánh giá (ví dụ exception khi tra nguồn chính sách), cần tách khỏi deny vì hai trạng thái có nguyên nhân, tác động và hướng khắc phục khác nhau.

### 2.2. Những đại lượng cần hiểu

Micrometer Timer ghi nhận **count** và **totalTime**, và có thể phát thêm phân bố/histogram theo cấu hình backend. Độ trễ trung bình xấp xỉ tổng thời gian chia cho số lần đo, nhưng không thể thay p95/p99. Percentile cao giúp phát hiện đuôi chậm, thường quan trọng ở tra cứu ACL/DB.

| Đại lượng | Trả lời câu hỏi |
| --- | --- |
| count / throughput | Có bao nhiêu quyết định trong khoảng thời gian? |
| p50 | Đa số lời gọi thông thường nhanh thế nào? |
| p95 / p99 | Nhóm 5% / 1% chậm nhất ra sao? |
| max (theo cửa sổ) | Có đỉnh chậm bất thường không? |
| allow/deny/error rate | Chính sách đang cho phép/từ chối/lỗi bao nhiêu, có thay đổi sau phát hành không? |
| cache hit/miss, query count | Vì sao quyết định dựa trên dữ liệu nhanh hoặc chậm? |

Không đọc p99 của chỉ vài lời gọi như một đặc tính ổn định. Phân vị cần **đủ số mẫu trong cửa sổ**; luôn hiển thị count cùng đồ thị. Nếu chỉ cần biết phương thức được gọi bao nhiêu lần trong test, Timer.count() có giá trị; nếu cần chứng minh tối ưu nhanh hơn, phải đo nhiều lần trong môi trường kiểm soát.

## 3. Chiến lược công cụ quan sát

### 3.1. Cấp tổng thể: HTTP server observation

Với Spring Boot Actuator và Micrometer được cấu hình phù hợp, có thể dùng observation HTTP server, thường mang metric **http.server.requests**. Nó cho thấy thời gian đáp ứng theo status, HTTP method và mẫu route; đây là điểm bắt đầu để tìm endpoint bị ảnh hưởng. Tuy nhiên, **http.server.requests không đo riêng quá trình kiểm tra quyền**. Một request 403 cũng có thể mất thời gian vì xác thực, xử lý exception hoặc những thành phần khác.

Đừng lấy số đo từ @Timed đặt quanh phương thức controller rồi gọi đó là chi phí authorization ở filter: thời điểm controller được thực thi đã **sau** HTTP authorization. Với method security, đo thân service cũng có thể bỏ sót interceptor vì interceptor chạy trước khi vào phương thức.

### 3.2. Quyết định quyền: AuthorizationManager/Observation

Spring Security có **ObservationAuthorizationManager**, nhận ObservationRegistry và delegate AuthorizationManager để theo dõi quá trình đánh giá quyền. Nó có thể giúp quan sát các manager được bọc đúng chỗ; việc nó có đang được đăng ký cho một filter hay method interceptor cụ thể phụ thuộc cấu hình thực tế. Không giả định rằng cứ thêm Actuator là tự có đủ ba timer riêng.

Trong bài này, chúng ta dùng **TimedAuthorizationManager** tường minh để xác định ranh giới và kiểm thử số lần ghi. Cách này cũng minh họa cách instrument một hệ thống chưa dùng tracing. **Chọn một đường instrument chính** trên cùng một quyết định để tránh thu thập trùng/đánh giá sai khi dùng đồng thời built-in observation và wrapper tùy biến.

### 3.3. Dữ liệu: quan sát chính sách và truy vấn

Ví dụ một chính sách kiểm tra quyền đọc tài liệu phải lấy owner từ repository. Độ trễ ở đây có thể gồm chờ connection pool, truy vấn, cache, xử lý Java và so sánh quyền. Nếu cần phân biệt từng phần, tạo span hoặc timer riêng cho **data-policy** và **ACL lookup**.

Không chỉ đo thời gian của Map.get()/so sánh String rồi kết luận hệ thống DB thực tế cũng nhanh như vậy. Dùng Map trong fixture chỉ để **minh chứng wiring và ranh giới đo**; kết quả hiệu năng thật phải được đánh giá với dữ liệu, đường kết nối, cache và tải phù hợp.

## 4. Nguyên tắc instrument chính xác và an toàn

1. Dùng **System.nanoTime()** hoặc Micrometer Timer/Sample cho khoảng thời gian; không dùng System.currentTimeMillis() để đo đoạn rất ngắn vì đây là đồng hồ thời gian thực, có thể điều chỉnh và độ phân giải không phù hợp.
2. Bọc đúng **delegate đánh giá quyền**, không vô tình gọi delegate hai lần hoặc thay đổi kết quả.
3. Ghi cả **allow, deny, error**; nếu API cho phép null/abstain thì giữ nguyên trạng thái đó thay vì tự chuyển thành allow.
4. Đặt ghi metrics ở **finally** để đường lỗi cũng được đếm. Dùng Timer đã khởi tạo cho các tag hữu hạn để giảm chi phí đăng ký meter trên đường nóng.
5. Kể cả khi đo chi tiết, phải giữ **test từ chối quyền**. Một bản tối ưu authorization mà vô tình bỏ qua policy là lỗi bảo mật, dù độ trễ rất thấp.
6. Không dùng username, email, token, documentId, raw URI chứa id hay SQL parameters làm **metric tags**: làm tăng cardinality, chi phí lưu trữ và nguy cơ lộ dữ liệu.
7. Với quyết định truy cập vào DB/cache, đo cả **thời gian** và **số truy vấn**; hạn chế việc policy tạo N truy vấn cho N đối tượng.
8. Cẩn thận với **asynchronous/reactive code**: thời điểm gọi trả về Mono/CompletionStage chưa phải thời điểm kết thúc công việc; cần đặt phép đo trong pipeline hoặc span bao quanh thời điểm hoàn thành. Ví dụ dưới đây dùng đồng bộ.

## 5. Ví dụ hoàn chỉnh: Spring Security 6.4 + Micrometer + JUnit 5

Một fixture thực hành với các bước:

- **HTTP:** GET /api/docs/{id} yêu cầu authority document:read. Bao quanh AuthorizationManager riêng cho HTTP.
- **Method:** DocumentService.read(id) có @PreAuthorize("hasAuthority('document:read')"), instrument interceptor bằng AuthorizationManager cho @PreAuthorize.
- **Data:** DocumentAcl tra chủ sở hữu từ Map dữ liệu giả, dùng SecurityContext; instrument quyết định owner/ACL.
- **Test:** người đúng quyền/đúng tài liệu được phép, thiếu quyền bị chặn ở HTTP hoặc method, còn đọc tài liệu không thuộc mình bị từ chối ở tầng dữ liệu.
- **Quan sát:** cùng một request thành công tạo ba bản ghi **http=allow, method=allow, data=allow**; đường HTTP bị từ chối không chạy method/data.

### 5.1. Dependency

Dùng dự án **Spring Boot 3.x** đã quản lý phiên bản dependency, Java 17+; ví dụ kiểm thử sử dụng API có trong Spring Security 6.4.x. Các dependency liên quan:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'io.micrometer:micrometer-core'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Trong sản phẩm thật, **spring-boot-starter-actuator** và registry như **micrometer-registry-prometheus** giúp phát metrics ra hệ thống quan sát. Fixture dùng **SimpleMeterRegistry** để đếm ngay trong bộ nhớ test, không cần Prometheus hay database và không mở management endpoint.

### 5.2. Một tệp JUnit chạy được trong dự án Boot 3.x

Tạo **src/test/java/demo/authorization/AuthorizationLatencyTest.java**:

~~~java
package demo.authorization;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.Test;
import org.springframework.aop.Advisor;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.authorization.method.PreAuthorizeAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(classes = AuthorizationLatencyTest.App.class)
@AutoConfigureMockMvc
class AuthorizationLatencyTest {

    static final String METRIC = "security.authorization.latency";

    /*
     * Wrapper dành cho dòng Spring Security 6.4.x.
     * check() còn dùng được trong dòng 6.x; đối chiếu API khi lên 7.x.
     */
    static final class TimedManager<T> implements AuthorizationManager<T> {
        private final AuthorizationManager<T> delegate;
        private final Timer allow;
        private final Timer deny;
        private final Timer abstain;
        private final Timer error;

        TimedManager(AuthorizationManager<T> delegate,
                     MeterRegistry registry, String layer) {
            this.delegate = delegate;
            this.allow = timer(registry, layer, "allow");
            this.deny = timer(registry, layer, "deny");
            this.abstain = timer(registry, layer, "abstain");
            this.error = timer(registry, layer, "error");
        }

        @Override
        @SuppressWarnings("deprecation")
        public AuthorizationDecision check(
                Supplier<Authentication> authentication, T object) {
            long started = System.nanoTime();
            Timer selected = error;
            try {
                AuthorizationDecision result =
                        delegate.check(authentication, object);

                selected = result == null ? abstain :
                        result.isGranted() ? allow : deny;
                return result; // Giữ nguyên quyết định, kể cả null.
            } finally {
                selected.record(System.nanoTime() - started,
                        TimeUnit.NANOSECONDS);
            }
        }
    }

    static Timer timer(MeterRegistry registry,
                       String layer, String result) {
        return Timer.builder(METRIC)
                .description("Elapsed authorization decision time")
                .tags("layer", layer, "result", result)
                .register(registry);
    }

    /*
     * Chính sách dữ liệu giả: Document 42 thuộc alice, 43 thuộc bob.
     * Thay Map bằng repository khi kiểm thử tích hợp dữ liệu thật.
     */
    static final class DocumentAcl {
        private final Map<Long, String> owners =
                Map.of(42L, "alice", 43L, "bob");
        private final Timer allow;
        private final Timer deny;
        private final Timer error;

        DocumentAcl(MeterRegistry registry) {
            this.allow = timer(registry, "data", "allow");
            this.deny = timer(registry, "data", "deny");
            this.error = timer(registry, "data", "error");
        }

        boolean mayRead(long id) {
            long started = System.nanoTime();
            Timer selected = error;
            try {
                Authentication auth =
                        SecurityContextHolder.getContext()
                                .getAuthentication();
                String owner = owners.get(id);

                boolean permitted = auth != null
                        && auth.isAuthenticated()
                        && owner != null
                        && owner.equals(auth.getName());

                selected = permitted ? allow : deny;
                return permitted;
            } finally {
                selected.record(System.nanoTime() - started,
                        TimeUnit.NANOSECONDS);
            }
        }
    }

    static class DocumentService {
        private final DocumentAcl acl;

        DocumentService(DocumentAcl acl) {
            this.acl = acl;
        }

        @PreAuthorize("hasAuthority('document:read')")
        public String read(long id) {
            if (!acl.mayRead(id)) {
                throw new AccessDeniedException(
                        "Insufficient document permission");
            }
            return "document:" + id;
        }
    }

    @RestController
    @RequestMapping("/api/docs")
    static class DocumentController {
        private final DocumentService service;

        DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/{id}")
        String read(@PathVariable("id") long id) {
            return service.read(id);
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity(prePostEnabled = false)
    static class App {

        @Bean
        MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        DocumentAcl documentAcl(MeterRegistry registry) {
            return new DocumentAcl(registry);
        }

        @Bean
        DocumentService documentService(DocumentAcl acl) {
            return new DocumentService(acl);
        }

        @Bean
        DocumentController documentController(DocumentService service) {
            return new DocumentController(service);
        }

        @Bean
        SecurityFilterChain securityFilterChain(
                HttpSecurity http, MeterRegistry registry)
                throws Exception {

            AuthorizationManager<RequestAuthorizationContext> read =
                    AuthorityAuthorizationManager
                            .hasAuthority("document:read");

            http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/docs/*")
                        .access(new TimedManager<>(read, registry, "http"))
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults());

            return http.build();
        }

        /*
         * prePostEnabled=false tắt interceptor mặc định để ta
         * đăng ký đúng một interceptor @PreAuthorize có đo thời gian.
         * Cấu hình này minh họa một điểm móc, không bật @PostAuthorize.
         */
        @Bean
        @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
        static Advisor preAuthorizeAdvisor(MeterRegistry registry) {
            AuthorizationManager<MethodInvocation> manager =
                    new PreAuthorizeAuthorizationManager();

            return AuthorizationManagerBeforeMethodInterceptor.preAuthorize(
                    new TimedManager<>(manager, registry, "method"));
        }
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Autowired
    MeterRegistry registry;

    long count(String layer, String result) {
        Timer t = registry.find(METRIC)
                .tags("layer", layer, "result", result)
                .timer();
        return t == null ? 0L : t.count();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void validReaderMeasuresThreeLayers() throws Exception {
        long http = count("http", "allow");
        long method = count("method", "allow");
        long data = count("data", "allow");

        mvc.perform(get("/api/docs/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("document:42"));

        assertEquals(http + 1, count("http", "allow"));
        assertEquals(method + 1, count("method", "allow"));
        assertEquals(data + 1, count("data", "allow"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "other")
    void missingHttpPermissionSkipsService() throws Exception {
        long deny = count("http", "deny");
        long method = count("method", "allow")
                + count("method", "deny");
        long data = count("data", "allow")
                + count("data", "deny");

        mvc.perform(get("/api/docs/42"))
                .andExpect(status().isForbidden());

        assertEquals(deny + 1, count("http", "deny"));
        assertEquals(method, count("method", "allow")
                + count("method", "deny"));
        assertEquals(data, count("data", "allow")
                + count("data", "deny"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void dataPolicyDeniesAnotherOwnersDocument() throws Exception {
        long http = count("http", "allow");
        long method = count("method", "allow");
        long dataDeny = count("data", "deny");

        mvc.perform(get("/api/docs/43"))
                .andExpect(status().isForbidden());

        assertEquals(http + 1, count("http", "allow"));
        assertEquals(method + 1, count("method", "allow"));
        assertEquals(dataDeny + 1, count("data", "deny"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "other")
    void directServiceCallIsDeniedByMethodInterceptor() {
        long methodDeny = count("method", "deny");

        assertThrows(AccessDeniedException.class,
                () -> service.read(42L));

        assertEquals(methodDeny + 1, count("method", "deny"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void correctAuthorityDoesNotBypassDataOwnership() throws Exception {
        long dataDeny = count("data", "deny");

        mvc.perform(get("/api/docs/42"))
                .andExpect(status().isForbidden());

        assertEquals(dataDeny + 1, count("data", "deny"));
    }
}
~~~

**Chạy:** Trong dự án Gradle Spring Boot 3.x sử dụng Java 17+ và JUnit Jupiter:

~~~bash
./gradlew test --tests "demo.authorization.AuthorizationLatencyTest"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "demo.authorization.AuthorizationLatencyTest"
~~~

**Kỳ vọng từ logic fixture:** 5 test thành công nếu đúng các phiên bản và dependency nêu trên. Đây là kết quả kỳ vọng, không phải log benchmark đã chạy. MockMvc xác minh 200/403, còn Timer.count() xác minh **đúng số lần decision được đo**. Fixture không đặt ngưỡng thời gian cứng vì đo microseconds/milliseconds trong CI dễ dao động.

### 5.3. Vì sao fixture ghi nhận đúng ba lớp?

**Đường cho phép — Alice đọc tài liệu 42:**

1. AuthorizationManager HTTP đánh giá document:read, ghi **http/allow**.
2. Interceptor @PreAuthorize đánh giá authority ở service, ghi **method/allow**.
3. Service gọi DocumentAcl với id=42. Map chứa owner=alice, ghi **data/allow**.
4. Controller trả chuỗi **document:42** và HTTP 200.

**Thiếu quyền chức năng — Alice chỉ có authority khác:**

1. HTTP manager trả deny, ghi **http/deny**.
2. Filter không gọi controller, nên không có bản ghi method/data mới.
3. MockMvc trả 403.

**Đúng authority nhưng sai owner — Alice đọc tài liệu 43:**

1. HTTP manager cho phép, ghi http/allow.
2. Method interceptor cho phép, ghi method/allow.
3. DocumentAcl tìm owner=bob, trả false, ghi data/deny.
4. Service ném AccessDeniedException, yêu cầu bị chặn với 403.

**Gọi service trực tiếp qua bean:**

- Method interceptor vẫn kiểm tra quyền và ghi method/deny nếu thiếu document:read.
- Không chạy qua HTTP filter nên không ghi http.
- Nếu interceptor từ chối trước khi vào thân hàm, không có tra cứu ACL và không ghi data.

**Giới hạn của ví dụ:** Map được dùng làm dữ liệu ACL giả; đo data layer ở đây là **lookup trong bộ nhớ + so sánh owner**, không chứng minh hiệu năng DB hoặc cache. Việc ghi cả ba Timer trong một HTTP request không có nghĩa các phép đo độc lập thống kê, vì chúng cùng chịu tác động của tải máy và cùng một request. Test đếm số bản ghi, không biến các quyết định phân quyền thành các lời gọi “đo thêm” riêng biệt.

### 5.4. Điều cần giữ khi thay đổi kiến trúc

- **@EnableMethodSecurity(prePostEnabled=false)** trong fixture chủ động tắt cấu hình pre/post mặc định để đăng ký một advisor đo @PreAuthorize. Trong ứng dụng có @PostAuthorize, @PreFilter, @PostFilter hoặc các interceptor khác, cần giữ đầy đủ các quy tắc đó; đừng sao chép cấu hình tắt mặc định mà quên đăng ký lại policy đang dùng.
- Đừng gắn cùng một interceptor hai lần. Nhân đôi advisor làm tăng chi phí, tăng số bản ghi và có thể làm thay đổi hành vi đánh giá.
- Nếu chuyển điều kiện dữ liệu vào SpEL @PreAuthorize, data timer sẽ **nằm trong** method timer; phải điều chỉnh cách đọc dashboard.
- Một lời gọi **new DocumentService(...)** không được Spring proxy bảo vệ. Bộ test trực tiếp dùng bean được inject.
- Với kiểm thử production, cần xác minh mapping người dùng/role/claim thành authorities; @WithMockUser tự cấp authority, chỉ kiểm chứng enforcement trong fixture.
- Khi dùng chính sách theo tenant, trạng thái, thời hạn quyền hoặc cache, thêm kiểm thử cả chiều cho phép và từ chối cho từng ranh giới.

## 6. Đo và so sánh trong hệ thống thực tế

### 6.1. Kịch bản benchmark tối thiểu

Lập bảng phép thử trước khi chạy để các lớp có thể so sánh:

| Nhóm | HTTP | Method | Data/ACL | Kết quả dự kiến | Mục đích |
| --- | --- | --- | --- | --- | --- |
| A | authority hợp lệ | @PreAuthorize hợp lệ | owner hợp lệ | allow | Đường thành công đủ 3 lớp |
| B | authority thiếu | không được gọi | không được gọi | deny ở HTTP | Chi phí từ chối sớm |
| C | authority hợp lệ | thiếu authority riêng | không được gọi | deny ở method | Chi phí interceptor/SpEL |
| D | authority hợp lệ | hợp lệ | sai tenant/owner | deny ở data | Chi phí đọc ACL trước từ chối |
| E | hợp lệ | hợp lệ | cache hit | allow | Data policy với cache nóng |
| F | hợp lệ | hợp lệ | cache miss / DB lookup | allow hoặc deny | Chi phí truy cập dữ liệu thật |
| G | hợp lệ | hợp lệ | ACL lớn / nhiều đối tượng | theo quyền | Khả năng mở rộng theo quy mô |

Fixture ở mục 5 chứng minh A, B, D và đường gọi method riêng; để so sánh C, E, F, G cần bổ sung dữ liệu và chính sách thật. Không thể đo lớp method bằng cách lấy thời gian toàn service rồi trừ thời gian JDBC nếu mọi bước khác còn dao động.

### 6.2. Kiểm soát điều kiện đo

1. **Cố định phiên bản:** JDK, Spring Security, Spring Boot, JVM flags, CPU/memory, kích thước pool, trạng thái TLS, database và cache.
2. **Tách môi trường:** Một bài test MockMvc thích hợp chứng minh policy và instrumentation; phép đo độ trễ end-to-end nên chạy trên ứng dụng triển khai thật (có network, DB, thread pool).
3. **Warm-up:** JVM cần biên dịch JIT, class loading, khởi tạo AOP và cache. Đo sau một giai đoạn warm-up có kiểm soát, đồng thời giữ kịch bản cache cold riêng nếu muốn khảo sát nó.
4. **Tỷ lệ allow/deny:** Cố định workload mix. Nếu tăng số request bị deny sớm, p95 tổng thể có thể giảm mà không hề tối ưu phần chính sách.
5. **Dữ liệu và quyền:** Đảm bảo cùng một tài khoản, cùng authority, cùng kiểu resource và quy mô ACL giữa baseline và candidate; dùng tài khoản test/cấu hình an toàn.
6. **Tải:** Chạy nhiều mức concurrency và request rate. Độ trễ có thể tăng phi tuyến khi connection pool/CPU cạn; p95 ở tải thấp không đại diện tải cao.
7. **Lặp lại:** Chạy nhiều đợt, ghi count, throughput, p50/p95/p99, tỷ lệ lỗi, GC, CPU, thời gian chờ DB và cache hit rate; không chọn một phép đo “đẹp nhất”.
8. **Kiểm thử đúng quyền:** Cùng workload phải xác minh HTTP status, quyết định ở từng lớp và trạng thái dữ liệu. Tối ưu bỏ qua rule có thể làm kết quả nhanh nhưng sai.
9. **Không dùng sleep để tạo benchmark giả:** Độ trễ sleep chỉ kiểm tra rằng Timer bao quanh đoạn mã; không mô phỏng phân bố DB/ACL thực.

### 6.3. Khi nào nên dùng JMH?

Nếu chỉ so sánh chi phí thuần Java cực nhỏ của hai thuật toán policy (ví dụ tra cứu dữ liệu trong Map so với tập hợp Set), JMH giúp xử lý warm-up, vòng lặp đo, tối ưu hóa JIT và nhiễu của microbenchmark. Nhưng JMH **không đại diện** cho chi phí HTTP filter chain, proxy, network, database hay connection pool. Đừng báo “giảm 50% độ trễ API” chỉ vì JMH cho thấy một phép kiểm tra Set nhanh hơn.

Nên phối hợp: **unit test** cho đúng quyết định, **JMH** cho toán tử Java khi thật sự cần, **integration/trace** cho đường thực thi, và **load test** cho p95/p99 sản phẩm.

## 7. Micrometer, histogram và dashboard vận hành

### 7.1. Thiết kế metric

Trong fixture, metric tùy biến có tên **security.authorization.latency**, với hai tag **layer** và **result**. Điều kiện sản phẩm có thể bổ sung **operation** gồm các giá trị hữu hạn như document-read, invoice-approve. Không thêm id tài liệu, tên người dùng, địa chỉ email, URL nguyên bản, query string hay chuỗi SpEL động vào tags.

Ví dụ các chuỗi đo hợp lệ:

~~~text
security.authorization.latency{layer="http",result="allow"}
security.authorization.latency{layer="method",result="deny"}
security.authorization.latency{layer="data",result="allow"}
~~~

Đó là **tên Micrometer + tag mang tính minh họa**, không phải định dạng xuất của một backend cụ thể. Nếu xuất sang Prometheus bằng micrometer-registry-prometheus, tên và đơn vị được registry chuyển đổi, thường thành họ metric có hậu tố **_seconds_count**, **_seconds_sum** và **_seconds_bucket** (nếu histogram được cấu hình). Không coi tên nội bộ Micrometer là tên truy vấn PromQL nguyên văn.

### 7.2. Tại sao chỉ Timer chưa chắc có p95 server-side?

Timer cơ bản luôn có count và total time; **histogram bucket cần bật** theo backend/cấu hình. Với Prometheus, bật percentile histogram hoặc một số SLO buckets hữu hạn cho timer cần xem phân vị. Ví dụ cấu hình ở vị trí đăng ký Timer trong hệ thống thực:

~~~java
// Minh họa thay cho hàm timer(...) trong fixture, khi dùng
// registry hỗ trợ histogram; không cần cho các test đếm.
return Timer.builder("security.authorization.latency")
        .tags("layer", layer, "result", result)
        .serviceLevelObjectives(
                java.time.Duration.ofMillis(1),
                java.time.Duration.ofMillis(5),
                java.time.Duration.ofMillis(20),
                java.time.Duration.ofMillis(100))
        .publishPercentileHistogram()
        .register(registry);
~~~

Đối với quyết định rất nhanh trong bộ nhớ, có thể đặt bucket dưới 1 ms theo số liệu thực tế; đối với truy vấn ACL qua DB, các bucket lớn hơn có thể hữu ích. Số bucket và tag combinations ảnh hưởng chi phí bộ nhớ và time series. Percentile tính ở client không tổng hợp chính xác được giữa nhiều instance như histogram server-side; hãy chọn cách phù hợp backend.

### 7.3. Truy vấn Prometheus minh họa

Giả sử metric được xuất thành **security_authorization_latency_seconds** và có các bucket, ví dụ p95 quyết định data/allow trên toàn nhóm instance:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(security_authorization_latency_seconds_bucket{
      layer="data",result="allow"
    }[5m])
  )
)
~~~

Đếm tốc độ quyết định HTTP bị từ chối:

~~~promql
sum(
  rate(security_authorization_latency_seconds_count{
    layer="http",result="deny"
  }[5m])
)
~~~

Tỷ lệ từ chối HTTP giữa những quyết định đã cho phép/từ chối có thể minh họa bằng:

~~~promql
sum(rate(security_authorization_latency_seconds_count{
  layer="http",result="deny"
}[5m]))
/
clamp_min(
  sum(rate(security_authorization_latency_seconds_count{
    layer="http",result=~"allow|deny"
  }[5m])),
  1e-9
)
~~~

**Diễn giải:** Đây là tỷ lệ **trong các quyết định được đo tại HTTP manager đó**, không phải tỷ lệ 403 trên mọi request ứng dụng. Những đường bị chặn trước khi vào manager, matcher khác hoặc authentication thất bại có thể không nằm trong mẫu số. Để nhìn toàn cảnh, kết hợp với http.server.requests và các chỉ số authentication/exception tương ứng.

### 7.4. Dashboard nên hiển thị gì?

- Hàng đầu: tổng HTTP request p95/p99 theo route template và status; tỷ lệ lỗi; throughput.
- Hàng thứ hai: authorization latency p50/p95/p99 theo layer, result, operation; count/rate cùng cửa sổ để biết mẫu đủ lớn.
- Hàng thứ ba: DB/ACL query latency, số query mỗi quyết định, cache hit/miss, connection pool saturation.
- Kèm trace exemplar hoặc correlation id ở công cụ tracing/log riêng khi cần điều tra một trường hợp hiếm. Correlation id **không phải** metric tag.
- Chú thích thời điểm deploy và thay đổi policy để đọc regression; chỉ cảnh báo khi đủ dữ liệu và đúng workload.

## 8. Phân tích nút thắt và hướng tối ưu

### 8.1. HTTP authorization chậm

**Dấu hiệu:** T_http_auth tăng trong khi method/data không tăng tương ứng.

**Kiểm tra:** số matcher, thứ tự matcher, custom AuthorizationManager, truy cập remote policy engine/identity provider, việc tái xác thực/thẩm định token trong đường đánh giá. Một số rule chỉ so sánh authority rất rẻ; nếu HTTP check chậm hàng chục ms cần tìm lời gọi I/O hoặc xử lý bổ sung thay vì đổ lỗi cho khái niệm role/permission.

**Hướng xử lý:** giảm I/O trong chính sách HTTP, cấu hình matcher có chủ đích, cache dữ liệu quyền có TTL/invalidation phù hợp; đừng lưu cache theo user mà bỏ qua tenant, phạm vi resource hoặc phiên bản quyền.

### 8.2. Method authorization chậm

**Dấu hiệu:** T_method_auth cao, đặc biệt với biểu thức SpEL phức tạp hoặc nhiều phép tra cứu.

**Kiểm tra:** có nhiều interceptor cùng áp dụng không; @PreAuthorize gọi bean chính sách có I/O không; rule sau khi đổi annotation có thực hiện nhiều lần không; self-invocation/proxy đường gọi có như kỳ vọng không.

**Hướng xử lý:** làm rõ vị trí chính sách, hạn chế gọi dữ liệu lặp, tái sử dụng logic kiểm tra đã định nghĩa và tách query khỏi diễn giải biểu thức khi hợp lý. **Không** gỡ bỏ @PreAuthorize hay thay bằng authenticated() để giảm thời gian.

### 8.3. Data authorization chậm

**Dấu hiệu:** T_data_auth tăng theo số tài nguyên, tỷ lệ cache miss hoặc độ lớn ACL; DB span cho thấy query đắt.

**Kiểm tra:** N+1 query, thiếu index trên (tenant_id, resource_id, principal_id/action), join ACL đắt, connection pool, network latency, cache key/quy tắc invalidation, truy vấn lặp khi một request kiểm tra nhiều tài nguyên.

**Hướng xử lý:** index đúng theo truy vấn thực tế; chuyển kiểm tra quyền và lọc kết quả vào query có ràng buộc phù hợp; batch lookup thay vì một truy vấn mỗi bản ghi; cache theo đủ context quyền với chiến lược làm mới; tránh đưa dữ liệu ngoài quyền vào bộ nhớ rồi mới lọc khi cơ sở dữ liệu có thể hạn chế từ đầu.

**Giới hạn bảo mật của cache:** cache quyết định allow của user A cho tài nguyên 42 không được dùng lại cho user B hoặc tenant khác. Khi quyền bị thu hồi, quyền cũ không được kéo dài ngoài cửa sổ hệ thống chấp nhận. Hiệu năng và tính đúng đắn của cache phải được kiểm chứng cùng nhau.

### 8.4. Đã giảm p95 nhưng người dùng vẫn thấy API chậm

Nếu thời gian kiểm tra quyền từ 3 ms giảm còn 1 ms nhưng độ trễ request là vài trăm ms, lợi ích ở HTTP tổng thể có thể rất nhỏ. Cần xác định **tỷ trọng thời gian** của mỗi phần và kiểm tra lại bằng trace/load test; không tối ưu nhiều ngày cho một đoạn chiếm rất ít ngân sách độ trễ.

Ngược lại, nếu một request danh sách 100 phần tử gọi ACL 100 lần, mỗi lần 2 ms, tổng chi phí có thể đáng kể dù p95 của **mỗi quyết định** nhìn riêng không cao. Vì vậy phải đo **số lần gọi quyết định trên một request**, không chỉ độ trễ mỗi lần gọi.

## 9. Các trường hợp dễ gây hiểu sai

| Hiện tượng | Kết luận sai | Cách đọc đúng |
| --- | --- | --- |
| HTTP p95 cao, HTTP auth timer thấp | “Không liên quan security” | Xác thực hoặc method/data auth vẫn có thể chậm; cần trace đủ |
| HTTP 403 có độ trễ rất thấp | “Chính sách tối ưu hoàn hảo” | Có thể bị deny trước khi vào service/DB |
| Data timer giảm khi cache bật | “Cache luôn an toàn” | Cần test TTL, thu hồi quyền, tenant và cache key |
| Method timer chứa DB call trong SpEL | “Cộng method + data để có tổng” | Timer bị lồng; cộng sẽ đếm trùng |
| Timer.count thấp sau một đợt tải | “Authorization ít được gọi” | Có thể match sai đường, bị chặn trước hoặc instrument thiếu |
| p99 dao động lớn với rất ít mẫu | “Bản cập nhật gây regression” | Tăng cỡ mẫu, nhiều cửa sổ, kiểm soát độ tin cậy |
| MockMvc thực thi nhanh | “Thời gian production cũng vậy” | MockMvc không mô phỏng network, DB hay concurrency production |
| Test chỉ kiểm tra duration | “Tối ưu thành công” | Có thể đã bỏ qua rule; bắt buộc kiểm tra allow/deny |
| CPU tăng sau bật histogram cho mọi tag | “Dịch vụ nghiệp vụ có vấn đề” | Metrics có thể tạo quá nhiều time series/bucket |
| Đặt userId/resourceId trong tags | “Dễ điều tra hơn” | Cardinality không giới hạn và nguy cơ lộ dữ liệu; dùng trace/log bảo vệ |

**Định nghĩa rõ thời gian đo:** Quyết định ở request matcher có thể chỉ đánh giá quyền chức năng; chính sách object/tenant xuất hiện sau khi controller tải resource. Khi sửa luồng để đẩy kiểm tra dữ liệu vào method interceptor, số liệu ở nhóm method tăng và nhóm data thay đổi dù tổng thời gian thực chưa đổi. Trong dashboard cần gắn phiên bản instrument và chính sách để so sánh đúng.

## 10. Quy trình vận hành khi có cảnh báo độ trễ quyền

1. Xác định route template, HTTP method, trạng thái, thời điểm, tần suất và môi trường; kiểm tra đủ số mẫu.
2. So sánh p95/p99 HTTP với **http/method/data authorization**, tách allow và deny.
3. Đọc trace một hoặc nhiều request thực tế; tìm span I/O, chờ pool, truy vấn ACL hoặc lời gọi policy engine.
4. Kiểm tra thay đổi gần nhất: code, rule, indexes, cache hit rate, phiên bản token/role hierarchy, quy mô ACL.
5. Tái hiện bằng dữ liệu và tỷ lệ quyền tương ứng, điều chỉnh một yếu tố mỗi lần.
6. Sau tối ưu, chạy lại cả test **có quyền**, **không có quyền**, **sai owner/tenant**, **quyền vừa bị thu hồi**.
7. Đối chiếu baseline và candidate theo p95/p99, số mẫu, throughput, tài nguyên sử dụng và tỷ lệ allow/deny; ghi chú bất kỳ thay đổi cấu hình metrics.
8. Theo dõi hậu phát hành: cải thiện độ trễ đi đôi với tính đúng đắn của quyền và không làm tăng error/denied bất thường.

**Ví dụ chọn mục tiêu:** Có thể đặt ngân sách độ trễ cho mỗi đường: HTTP quyền tĩnh nên thấp hơn kiểm tra ACL qua DB. Nhưng ngưỡng cụ thể phải rút ra từ baseline và yêu cầu SLO của ứng dụng; không áp một con số tùy ý cho mọi hệ thống. Với quyền quan trọng, ưu tiên độ đúng và tính nhất quán dữ liệu hơn một mức tiết kiệm thời gian rất nhỏ.

## 11. Bài tập thực hành và tiêu chí đạt

**Bài 1 — Phát hiện điểm đo sai.** Đặt System.nanoTime() trong phương thức controller rồi so sánh với http.server.requests. Giải thích vì sao thời gian ở controller không bao gồm HTTP filter authorization chạy trước controller. Sửa bằng wrapper đặt trên HTTP AuthorizationManager.

**Bài 2 — Từ chối ở tầng method.** Thêm phương thức có @PreAuthorize yêu cầu document:delete; gọi trực tiếp bean với người chỉ có document:read. Test phải chứng minh method/deny tăng một lần, còn data policy không được chạy.

**Bài 3 — Dữ liệu thật.** Thay Map owners bằng một repository chỉ đọc trong môi trường test; thêm span cho truy vấn quyền. Đo cold/warm cache; thử dữ liệu 100, 10.000, 1.000.000 bản ghi với index phù hợp. Báo count, p50/p95/p99, query count, tỷ lệ cache hit; không điền số liệu giả.

**Bài 4 — Permission trong SpEL.** Đưa quyền owner vào một bean được gọi từ @PreAuthorize. Dùng trace để chỉ ra data span nằm trong method authorization. Sửa dashboard để không cộng hai timer lồng nhau.

**Bài 5 — Nhiều đối tượng.** Viết chức năng đọc danh sách 100 tài liệu; so sánh kiểm tra ACL theo từng phần tử và truy vấn được batch. Bắt buộc so sánh cả **số query**, thời gian toàn request, độ trễ mỗi quyết định và danh sách trả về. Cả hai phương án phải chỉ trả dữ liệu được phép.

**Tiêu chí hoàn thành:**

- Có sơ đồ ranh giới đo **HTTP / method / data**; chỉ rõ các span có thể lồng nhau.
- Ghi được **số lần** và **thời gian** cho allow/deny/error ở từng lớp đang sử dụng, không tạo tag có cardinality vô hạn.
- Test chứng minh HTTP deny chặn phương thức/data; method deny chặn data; data deny vẫn ngăn trả tài nguyên.
- Kết quả đo có baseline, warm-up, workload mix, số mẫu, p95/p99 và điều kiện cache/DB được mô tả.
- Sau bất kỳ tối ưu nào, ma trận quyền không thay đổi ngoài các thay đổi chính sách được chủ động phê duyệt.
- Không khẳng định kết quả performance production dựa trên fixture Map/MockMvc hoặc một phép microbenchmark đơn lẻ.

## 12. Tài liệu tham khảo

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.4/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/6.4/servlet/authorization/method-security.html
- Spring Security — AuthorizationManagerBeforeMethodInterceptor API 6.4: https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html
- Spring Security — ObservationAuthorizationManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ObservationAuthorizationManager.html
- Spring Boot — Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
