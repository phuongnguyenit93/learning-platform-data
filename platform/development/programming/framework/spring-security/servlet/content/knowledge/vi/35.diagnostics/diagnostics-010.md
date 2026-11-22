# @PreAuthorize không chạy do cấu hình proxy hoặc lời gọi nội bộ — Chẩn đoán Spring Security Servlet

> **Phạm vi:** Spring Security 6.x, Spring Framework 6.x, Spring Boot 3.x, Java 17+; trọng tâm là **method security trên các Spring-managed beans** trong ứng dụng Spring MVC/Servlet. Nội dung phân biệt lỗi chưa bật method security, đối tượng không phải proxy, lời gọi `this.method()` trong cùng bean, giới hạn của JDK dynamic proxy/CGLIB proxy và lỗi kiểm thử khiến `@PreAuthorize` tưởng như không có tác dụng. Ví dụ hoàn chỉnh có Maven, ứng dụng và bài kiểm thử MockMvc để **quan sát được cả lỗi self-invocation và bản sửa bằng bean khác**.

## 1. Triệu chứng và câu hỏi đầu tiên

Bạn viết:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteEverything() {
    // Thao tác nhạy cảm.
}
~~~

Nhưng một người chỉ có `ROLE_USER` vẫn kích hoạt được method, hoặc unit test gọi method mà không nhận `AccessDeniedException`. Không thể vội kết luận Spring Security đã bỏ qua authorization do một lỗi duy nhất. Có ít nhất bốn nhóm nguyên nhân:

1. **Method security chưa được kích hoạt**: thiếu `@EnableMethodSecurity` hoặc annotation nằm trong configuration không được tạo thành bean.
2. **Lời gọi không đi qua Spring AOP proxy**: `this.deleteEverything()`, method nội bộ gọi trực tiếp, tạo object bằng `new`, hoặc dùng reference tới target thay vì proxy.
3. **Proxy không thể intercept method cụ thể**: method `private`, `final`, target class `final` trong class-based proxy, visibility/method resolution/annotation placement không phù hợp với proxy và phiên bản framework.
4. **Biểu thức hoặc test không như bạn tưởng**: `hasRole` khác `hasAuthority`, `Authentication` giả có quyền quá rộng, request matcher khác, test không nạp security configuration, đang gọi sai bean/overload hoặc có custom method-security advisor.

**Nguyên tắc quan trọng:** `@PreAuthorize` không phải lệnh `if` tự chạy ở đầu thân hàm. Với cấu hình method security mặc định sử dụng **Spring AOP proxy**, framework kiểm tra expression **trên đường đi qua proxy trước khi method target thực thi**. Nếu bạn gọi thẳng vào target mà không qua proxy, advice có thể không được thực thi.

### 1.1. Kết quả bình thường là gì?

Giả sử một service có:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String sensitiveAction() {
    return "allowed";
}
~~~

Khi **lời gọi đi qua proxy**:
- Authentication hợp lệ có `ROLE_ADMIN` → method chạy và trả `allowed`.
- Authentication hợp lệ chỉ có `ROLE_USER` → interceptor từ chối trước khi method chạy, thường ném `AccessDeniedException`.
- Không có Authentication/không đủ tin cậy → security infrastructure xử lý theo context và exception loại tương ứng.

Trong một HTTP request đi qua `SecurityFilterChain`, exception có thể được chuyển thành:
- **403 Forbidden** nếu đã xác thực nhưng thiếu quyền;
- **401 Unauthorized** hoặc **302 redirect tới trang login** nếu chưa xác thực, tùy authentication entry point.

Khi gọi trực tiếp service từ test Java không có Servlet filters, bạn thường thấy **exception Java** chứ không phải HTTP status. Không nên đồng nhất `@PreAuthorize` với “luôn tạo ra 403 trong mọi môi trường”.

## 2. Spring Security method security hoạt động qua proxy như thế nào?

Với Spring Security 6.x và `@EnableMethodSecurity`, các interceptor/authorization managers tích hợp Spring AOP để áp dụng annotations như `@PreAuthorize` trên các method được hỗ trợ.

~~~text
HTTP request đã đi qua Spring Security FilterChain
         |
         v
Controller (Spring-managed)
         |
         | injected reference tới service BEAN
         v
+-------------------------------+
| Spring AOP proxy của service  |  <--- đây là biên được bảo vệ
| - @PreAuthorize interceptor   |
| - đọc Authentication hiện tại |
| - đánh giá SpEL               |
| - DENY -> exception           |
| - ALLOW -> gọi target         |
+-------------------------------+
         |
         v
     Target service method
         |
         v
     Business operation
~~~

**Từ khóa là proxy reference.** Spring quản lý bean và thường tiêm reference đã được bọc bằng proxy tại điểm phụ thuộc. Framework không chèn một dòng authorization thật vào body của class bạn viết.

### 2.1. Cấu hình tối thiểu trong Spring Security 6

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Đoạn trên là **một class cấu hình đầy đủ nếu đặt trong application Spring**. Từ Spring Security 6, dùng `@EnableMethodSecurity` thay cho cấu hình `@EnableGlobalMethodSecurity` kiểu cũ. `@EnableMethodSecurity` hỗ trợ `@PreAuthorize`/`@PostAuthorize` mặc định, không bắt buộc thêm `prePostEnabled=true` cho cách dùng phổ biến.

**Phân biệt hai trục độc lập:**
- `http.authorizeHttpRequests(...)` kiểm soát **HTTP request** đi qua Servlet filter chain.
- `@PreAuthorize(...)` kiểm soát **lời gọi Java method** thông qua method-security infrastructure.

Một ứng dụng có thể có URL yêu cầu login nhưng **method security chưa bật**. Khi đó `authenticated()` chỉ bảo vệ request khỏi anonymous user; nó **không thay thế** rule `hasRole('ADMIN')` trên service.

### 2.2. Những thành phần quan trọng

| Thành phần | Vai trò |
| --- | --- |
| `@EnableMethodSecurity` | Kích hoạt infrastructure method-security trong application context. |
| `@PreAuthorize` | Khai báo expression cần kiểm trước method execution. |
| `AuthorizationManagerBeforeMethodInterceptor` | Một interceptor trong mô hình method security mới, áp dụng authorization decision. |
| `SecurityContextHolder` | Nguồn Authentication thường được đọc khi method security đánh giá quyết định. |
| `Authentication` và `GrantedAuthority` | Danh tính đã xác thực và authorities thực tế. |
| Spring AOP proxy | Điểm chặn lời gọi method trước khi đến target. |
| `AopUtils.isAopProxy(bean)` | Kiểm tra bean reference có phải AOP proxy hay không trong một test/diagnostic. |

Các lớp nội bộ và tập advisor có thể khác nhau theo phiên bản hoặc customization. **Không hardcode thứ tự filter, advisor hay tên class internal** làm API contract nếu không được framework bảo đảm.

## 3. Lỗi điển hình: self-invocation bỏ qua @PreAuthorize

Ví dụ:

~~~java
@Service
public class OrderService {

    public void submitOrder() {
        // Đây là lệnh gọi TRONG CÙNG target object:
        this.approveHighValueOrder();
    }

    @PreAuthorize("hasRole('MANAGER')")
    public void approveHighValueOrder() {
        // Logic phê duyệt.
    }
}
~~~

Đoạn trên là **fragment mô tả lỗi**, chưa có imports và các thành phần ứng dụng khác.

Nếu Controller gọi `orderService.approveHighValueOrder()` qua **Spring bean proxy**, security advice có cơ hội chặn. Nhưng Controller gọi `orderService.submitOrder()` qua proxy, sau đó `submitOrder()` của **target** thực hiện `this.approveHighValueOrder()`, thì bước gọi nội bộ **không đi qua proxy lần hai**. Annotation trên `approveHighValueOrder()` có thể **không được kiểm tra**.

~~~text
CASE A — external invocation qua proxy:

Controller -> OrderService proxy
              | @PreAuthorize(hasRole('MANAGER'))
              | -> deny USER / allow MANAGER
              v
            target.approveHighValueOrder()


CASE B — self invocation BỎ QUA advice ở inner method:

Controller -> OrderService proxy
              | submitOrder() không có policy tương đương
              v
            target.submitOrder()
              |
              | this.approveHighValueOrder()
              |  ^ call trực tiếp trong target
              |    không qua proxy/interceptor
              v
            target.approveHighValueOrder()
~~~

**Đây là bản chất của self-invocation trong proxy-based Spring AOP**, không phải một hành vi chỉ có `@PreAuthorize`. Cơ chế tương tự có thể ảnh hưởng `@Transactional`, `@Cacheable`, `@Async` nếu gọi nội bộ trong cùng class và advice dựa trên proxy.

### 3.1. Vì sao “outer method đã đi qua proxy” vẫn chưa đủ?

Proxy chỉ có thể áp dụng interceptor cho **method entry đang đi qua proxy**. Việc một method đã được proxy gọi không làm mọi lệnh `this.*` bên trong method tự đi qua proxy.

Ví dụ nếu `submitOrder()` chỉ có `@PreAuthorize("isAuthenticated()")`, còn `approveHighValueOrder()` yêu cầu `MANAGER`, một user đã authenticated vẫn có thể chạy phần inner method nếu không có kiểm tra khác. **Rule ở outer method yếu hơn không thể thay thế rule ở inner method**.

### 3.2. Lưu ý về lệnh gọi không viết rõ “this”

Trong Java, chỉ cần gọi:

~~~java
approveHighValueOrder();
~~~

bên trong cùng class cũng tương đương self-call qua `this`. Bỏ chữ `this.` **không sửa vấn đề**. Lời gọi từ constructor, `private` helper hay reference tới target được giữ lại trong field cũng không tự biến thành lời gọi đi qua Spring proxy.

## 4. Cách sửa tốt nhất: tách boundary được bảo vệ sang một Spring bean khác

Hướng sửa dễ hiểu và dễ kiểm thử nhất là đưa thao tác có policy cần bảo vệ vào **một service bean riêng**, rồi cho các luồng gọi khác tiêm bean đó bằng dependency injection.

~~~text
Controller
   |
   v
WorkflowService bean
   |
   | injected reference
   v
SensitiveOperationService PROXY
   |
   | @PreAuthorize("hasRole('ADMIN')")
   |
   +-- user thiếu quyền -> AccessDeniedException
   |
   v
SensitiveOperationService target
~~~

Lúc đó mọi entry point cần thao tác nhạy cảm đều gọi qua proxy service chứa policy. Cấu trúc này:
- giảm nguy cơ quên kiểm tra khi thêm entry point;
- tách **orchestration** khỏi **security-sensitive operation**;
- cho phép test hành vi deny ở đúng boundary;
- không cần hack lấy proxy hiện tại từ `AopContext`;
- dễ áp dụng trên Controller, message listener hay các service có caller khác nhau.

**Quan trọng:** Tách bean không thay thế kiểm quyền tài nguyên cụ thể; `@PreAuthorize("hasRole('ADMIN')")` chỉ là ví dụ role-based. Khi kiểm ownership/tenant cần expression hoặc authorization service phù hợp.

## 5. Ví dụ Maven/Java 17 chạy được: quan sát lỗi và bản sửa

Project gồm:
- `GET /api/direct`: Controller gọi method bảo vệ qua injected Spring service proxy.
- `GET /api/unsafe`: Controller gọi một method khác của service; method này **self-invoke** method bảo vệ. Endpoint này **cố tình không an toàn để chứng minh lỗi**.
- `GET /api/fixed`: Controller gọi orchestration service khác, orchestration service gọi method bảo vệ **qua proxy reference**.
- Hai tài khoản: `alice` có `ROLE_USER` và `admin` có `ROLE_ADMIN`.

**Chỉ dùng project trong môi trường học tập; endpoint `/api/unsafe` là anti-pattern có chủ đích và không được giữ lại trong production.** Dùng Spring Boot 3.3.5 làm một ví dụ phiên bản cụ thể với Java 17+, không khẳng định đây là bản mới nhất.

### 5.1. Cấu trúc project

~~~text
method-security-proxy-demo/
  pom.xml
  src/
    main/
      java/com/example/methodsecurity/
        MethodSecurityDemoApplication.java
        SecurityConfig.java
        SensitiveService.java
        WorkflowService.java
        ProbeController.java
    test/
      java/com/example/methodsecurity/
        MethodSecurityIntegrationTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>method-security-proxy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

### 5.3. Main application và EnableMethodSecurity

**`src/main/java/com/example/methodsecurity/MethodSecurityDemoApplication.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityDemoApplication.class, args);
    }
}
~~~

Lưu ý `@EnableMethodSecurity` phải thuộc **configuration được Spring ApplicationContext thực sự nạp**. Đặt annotation trên class tự tạo bằng `new` hoặc trên configuration nằm ngoài component scan mà không import sẽ không kích hoạt method-security infrastructure.

### 5.4. SecurityConfig: người dùng thật cho HTTP Basic demo

**`src/main/java/com/example/methodsecurity/SecurityConfig.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("user-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Tất cả endpoint ví dụ chỉ đọc bằng GET;
            // không tắt CSRF và không có state-changing POST.
            .build();
    }
}
~~~

Điểm cần nhớ:

1. `httpBasic` xác minh credential thật qua authentication provider; test không sử dụng một principal do client tự khai.
2. `.authenticated()` ở URL bảo đảm user đã đăng nhập nhưng **chưa kiểm role ADMIN**. Đây là chủ ý để test chứng minh khác biệt giữa HTTP security và method security.
3. `.roles("ADMIN")` tạo `ROLE_ADMIN` authority, tương thích `hasRole('ADMIN')`.
4. `SessionCreationPolicy.STATELESS` giúp demo Basic không dựa vào phiên; **không** phải điều kiện bật method security.
5. Demo có password cố định ở source để học. Production cần identity store/IdP, password hashing, secret management, TLS/HTTPS và audit phù hợp.
6. Các API GET không thay đổi trạng thái nghiệp vụ, kể cả endpoint “unsafe” chỉ trả string; mục tiêu là quan sát proxy, không tạo lỗ hổng thực tế trong hệ thống đang chạy.

### 5.5. SensitiveService: method protected và self-invocation

**`src/main/java/com/example/methodsecurity/SensitiveService.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SensitiveService {

    @PreAuthorize("hasRole('ADMIN')")
    public String privilegedAction() {
        return "privileged-action";
    }

    // CỐ TÌNH SAI: target gọi chính target.
    // @PreAuthorize ở privilegedAction() không được áp dụng
    // cho lệnh gọi nội bộ this.privilegedAction().
    public String unsafeSelfInvocation() {
        return this.privilegedAction();
    }
}
~~~

**Điểm chẩn đoán:** `SensitiveService` do Spring quản lý nên reference được inject vào controller có thể là proxy. Nhưng **bên trong target**, lời gọi `this.privilegedAction()` không qua proxy — và method không kiểm quyền lần nữa.

Đừng giải quyết bằng cách chỉ thêm `@PreAuthorize("isAuthenticated()")` vào `unsafeSelfInvocation()`. Một user thông thường đã authenticated, nên vẫn có thể vào method; expression cần bao phủ quyền thật hoặc phải đổi cấu trúc để method nhạy cảm được gọi qua proxy.

### 5.6. WorkflowService: sửa bằng gọi qua bean được inject

**`src/main/java/com/example/methodsecurity/WorkflowService.java`:**

~~~java
package com.example.methodsecurity;

import org.springframework.stereotype.Service;

@Service
public class WorkflowService {

    private final SensitiveService sensitiveService;

    public WorkflowService(SensitiveService sensitiveService) {
        this.sensitiveService = sensitiveService;
    }

    public String invokeSafely() {
        // Một bean KHÁC gọi SensitiveService qua injected proxy.
        return sensitiveService.privilegedAction();
    }
}
~~~

Bean separation tạo một điểm chặn rõ ràng. Khi `WorkflowService.invokeSafely()` được gọi từ controller, nó gọi `SensitiveService.privilegedAction()` qua reference do Spring tiêm, cho phép `@PreAuthorize` intercept.

### 5.7. Controller: ba lối gọi để so sánh

**`src/main/java/com/example/methodsecurity/ProbeController.java`:**

~~~java
package com.example.methodsecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ProbeController {

    private final SensitiveService sensitiveService;
    private final WorkflowService workflowService;

    public ProbeController(
            SensitiveService sensitiveService,
            WorkflowService workflowService) {
        this.sensitiveService = sensitiveService;
        this.workflowService = workflowService;
    }

    @GetMapping("/direct")
    public Map<String, String> direct() {
        return Map.of(
            "result", sensitiveService.privilegedAction());
    }

    @GetMapping("/unsafe")
    public Map<String, String> unsafe() {
        return Map.of(
            "result", sensitiveService.unsafeSelfInvocation());
    }

    @GetMapping("/fixed")
    public Map<String, String> fixed() {
        return Map.of(
            "result", workflowService.invokeSafely());
    }
}
~~~

Endpoint `/api/unsafe` cố tình mô phỏng đường **bypass method-security advice** để người học quan sát. **Không triển khai endpoint này trên hệ thống thật** và không dùng một endpoint GET để thực hiện các thao tác thay đổi dữ liệu.

### 5.8. Chạy thử bằng Maven và curl

Yêu cầu JDK 17+, Maven và repository truy cập được dependencies.

~~~bash
mvn test
mvn spring-boot:run
~~~

Không có một stdout Maven cố định: dependency caching, logger/test reporter và cấu hình máy có thể làm output khác nhau. Dưới đây là những **HTTP kết quả mong đợi theo cấu hình demo**, không phải transcript đã thu từ server.

Không gửi credential:

~~~bash
curl -i http://localhost:8080/api/direct
~~~

Kỳ vọng HTTP `401 Unauthorized` vì `/api/**` yêu cầu authentication và ứng dụng bật Basic entry point.

Gửi user không có ROLE_ADMIN:

~~~bash
curl -i -u alice:user-pass http://localhost:8080/api/direct
~~~

Kỳ vọng HTTP `403 Forbidden`. `@PreAuthorize` được chặn qua proxy.

Cùng user gọi đường self-invocation sai:

~~~bash
curl -i -u alice:user-pass http://localhost:8080/api/unsafe
~~~

Kỳ vọng HTTP 200, response đại diện:

~~~json
{"result":"privileged-action"}
~~~

**200 ở đây là dấu hiệu lỗi thiết kế có chủ đích, không phải điều nên mong đợi trong production.** HTTP authentication vẫn đã chạy và thành công; method security **không áp dụng ở lời gọi nội bộ**.

Cùng user gọi đường đã sửa:

~~~bash
curl -i -u alice:user-pass http://localhost:8080/api/fixed
~~~

Kỳ vọng HTTP `403 Forbidden` vì lời gọi đi qua proxy của `SensitiveService`.

Gửi admin hợp lệ:

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/api/direct
curl -i -u admin:admin-pass http://localhost:8080/api/fixed
~~~

Kỳ vọng HTTP 200 cùng `{"result":"privileged-action"}` trên cả hai endpoint.

**Lưu ý:** `curl -u` và HTTP localhost trong ví dụ chỉ dành cho học tập. Trên mạng thật dùng HTTPS, không đưa mật khẩu sản xuất vào terminal history/log.

## 6. Integration tests chứng minh nguyên nhân thực tế

Test phải nạp Spring application context và security filters thật. Dùng MockMvc với Basic credentials để có Authentication thực và AOP method-security proxies.

**`src/test/java/com/example/methodsecurity/MethodSecurityIntegrationTest.java`:**

~~~java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private SensitiveService sensitiveService;

    @Test
    void sensitiveServiceIsAnAopProxy() {
        assertTrue(AopUtils.isAopProxy(sensitiveService));
    }

    @Test
    void anonymousRequestIsRejectedBeforeController() throws Exception {
        mvc.perform(get("/api/direct"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/direct")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void directCallDeniesNonAdmin() throws Exception {
        mvc.perform(get("/api/direct")
                .with(httpBasic("alice", "user-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void directCallAllowsAdmin() throws Exception {
        mvc.perform(get("/api/direct")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                "privileged-action"));
    }

    @Test
    void internalThisCallDemonstratesBypass() throws Exception {
        // Negative demonstration: 200 is proof of the BUG.
        mvc.perform(get("/api/unsafe")
                .with(httpBasic("alice", "user-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                "privileged-action"));
    }

    @Test
    void refactoredCrossBeanCallDeniesNonAdmin() throws Exception {
        mvc.perform(get("/api/fixed")
                .with(httpBasic("alice", "user-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void refactoredCrossBeanCallAllowsAdmin() throws Exception {
        mvc.perform(get("/api/fixed")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                "privileged-action"));
    }
}
~~~

**Vì sao bộ test này có giá trị?**

1. `@SpringBootTest` nạp chính `@EnableMethodSecurity`, `SecurityFilterChain`, service beans và Spring AOP infrastructure.
2. `@AutoConfigureMockMvc` giữ filter chain để Basic credentials thật đi qua authentication provider.
3. `AopUtils.isAopProxy(sensitiveService)` xác minh bean reference được inject có proxy, tránh chẩn đoán sai rằng Spring hoàn toàn chưa tạo proxy.
4. Test `/api/direct` và `/api/fixed` mong 403 với USER: hai đường đi vào protected method **qua proxy**.
5. Test `/api/unsafe` mong 200 với USER **chỉ nhằm tái hiện lỗ hổng**, không phải expected behavior của sản phẩm.
6. Test ADMIN mong 200 giúp chứng minh rule thật sự cho phép role tương ứng thay vì luôn block.
7. Password sai mong 401; điều này tách lỗi authentication ở HTTP filters với lỗi authorization của method security.

Sau khi sửa code production bằng cách **xóa đường unsafe**, test cần đổi thành “mọi public entry point tới thao tác này đều deny non-admin”. Không nên giữ bài test mong lỗ hổng tồn tại trong bộ test production.

### 6.1. Vì sao không dùng unit test tạo object bằng new?

Một test như:

~~~java
SensitiveService service = new SensitiveService();
String result = service.privilegedAction();
~~~

sẽ trả `privileged-action` vì đây là **đối tượng Java thông thường**, không có Spring proxy. Điều đó không chứng minh `@EnableMethodSecurity` đã hỏng; nó chứng minh **bạn không gọi Spring bean**.

Unit test có thể kiểm logic thuần, nhưng **test method security** phải đi qua một `ApplicationContext` có infrastructure method-security/proxy và Authentication phù hợp, hoặc dùng test integration từ HTTP như trên.

### 6.2. Vì sao @WithMockUser có thể đánh lừa?

`@WithMockUser(roles = "ADMIN")` rất hữu ích để kiểm **authorization policy**; nhưng nó không chứng minh HTTP Basic password, JWT decoder hay form login hoạt động. Nếu bạn chỉ tạo mock ADMIN, method bảo vệ đương nhiên cho qua và bạn có thể bỏ sót test ROLE_USER/anonymous. Khi chẩn đoán proxy, hãy có **deny case** với user không đủ authority và **allow case** với user đủ quyền.

### 6.3. Nếu test 403 không như kỳ vọng

Kiểm theo thứ tự:
- `@EnableMethodSecurity` được nạp chưa?
- service bean reference có phải AOP proxy chưa?
- gọi qua proxy hay qua `this.`?
- user có `ROLE_ADMIN` thật không?
- method annotation nằm ở implementation/interface/override nào, có bị sai method overload không?
- response có bị xử lý lại bởi `@ControllerAdvice` hoặc custom exception handler không?
- test có bật filters, đúng security chain và user context không?

Không sửa test bằng cách thêm `permitAll()` hoặc tắt method security/CSRF; như vậy sẽ che giấu lỗi thay vì chữa nó.

## 7. Chẩn đoán proxy thực tế trước khi sửa cấu hình

### 7.1. Lấy đúng bean từ ApplicationContext

Một fragment chạy trong test/application Spring:

~~~java
@Autowired ApplicationContext context;

@Test
void inspectProxy() {
    Object bean = context.getBean(SensitiveService.class);

    System.out.println("proxy=" + AopUtils.isAopProxy(bean));
    System.out.println("jdk=" + AopUtils.isJdkDynamicProxy(bean));
    System.out.println("cglib=" + AopUtils.isCglibProxy(bean));
    System.out.println("targetType=" + AopUtils.getTargetClass(bean));
}
~~~

Đây là **fragment** cần imports `ApplicationContext`, `Test`, `AopUtils` và class demo; không phải một Java program standalone. Các kết quả cụ thể của JDK/CGLIB phụ thuộc cấu trúc class/interface và cấu hình proxy target class.

Đừng chỉ kiểm `bean.getClass().getName()`: proxy có thể mang tên class sinh tự động, khác nhau theo framework; **AopUtils** là cách hỏi trực tiếp framework. `isAopProxy=true` chỉ nói bean là proxy; để xác nhận **method cụ thể có method-security advice**, vẫn cần deny/allow integration tests.

### 7.2. Trường hợp bean không được proxy

Nếu `AopUtils.isAopProxy` trả false dù bạn mong `@PreAuthorize`, kiểm:
1. `@EnableMethodSecurity` có xuất hiện trong **application context đang chạy/test** không?
2. Class có được đăng ký làm bean qua `@Service`, `@Component`, `@Bean` hoặc configuration tương đương không?
3. Bạn có vô tình gọi một instance được tạo bằng `new` hay không?
4. Method annotation có ở vị trí mà Spring Security method-security pointcut phát hiện được không?
5. Bean có được tạo quá sớm trong lifecycle hay bị bỏ qua xử lý post-processor không?
6. Có custom AOP/proxy factories, profiles hoặc conditional configuration làm thay đổi bean không?

Nếu bean có những advice khác (`@Transactional`, caching), việc `isAopProxy=true` cũng **không bảo đảm** `@PreAuthorize` advisor tồn tại. Test access-denied tại boundary mới là bằng chứng cuối.

### 7.3. Trường hợp proxy có nhưng method vẫn không chặn

Kiểm:
- **Self-invocation:** trong target có `this.protectedMethod()` không?
- **Method visibility:** method có `public` và là phương thức có thể được advice intercept phù hợp không?
- **Final methods/classes:** class-based proxy không thể override final method; final class không thể subclass.
- **Annotation placement:** annotation ở class, interface hay implementation? Có overload/override khác đang được gọi không?
- **Proxy type:** bean được inject qua interface, nhưng code giữ reference tới concrete class/target?
- **Expression:** role/authority thực tế và principal có đúng không?
- **Multiple application contexts:** test hoặc servlet child context có tạo hai beans/cấu hình khác nhau không?

Đặc biệt, **“proxy có” và “lời gọi đi qua proxy” là hai mệnh đề khác nhau**. Ví dụ self-invocation: bean được inject là proxy nhưng method bên trong target gọi method khác bằng `this`, vẫn bypass advice ở method sau.

## 8. JDK dynamic proxy và CGLIB class-based proxy

Spring AOP chủ yếu dùng hai hình thức:

| Đặc điểm | JDK dynamic proxy | Class-based proxy (thường CGLIB) |
| --- | --- | --- |
| Cơ sở | Implement interfaces. | Subclass target class. |
| Điều kiện điển hình | Bean có interface, proxy-target-class không bị ép true. | Không có interface hoặc cấu hình ép class proxy. |
| Phương thức có thể advice | Phụ thuộc method được lộ qua interface và mapping tới target. | Phụ thuộc method có thể override/intercept; không intercept final/private. |
| Khi inject theo concrete class | Không phải lúc nào gán được vì JDK proxy không extends class. | Thường gán được nếu type phù hợp. |
| Self-invocation `this.method()` | **Bị bypass.** | **Bị bypass.** |
| Sửa self-invocation bằng cách đổi proxy type? | **Không.** | **Không.** |

### 8.1. Không sửa self-invocation bằng cách đổi JDK → CGLIB

Có thể cấu hình:

~~~java
@EnableMethodSecurity(proxyTargetClass = true)
~~~

để yêu cầu class-based proxies trong môi trường Spring Security method-security hỗ trợ option này. Nhưng **đây không phải bản sửa tự động cho self-invocation**: cả proxy dạng interface và subclass đều không intercept lời gọi nội bộ target theo mô hình Spring AOP proxy.

Nếu mục tiêu là “method trong cùng bean phải được advice”, lựa chọn ưu tiên là **refactor qua bean khác**. AspectJ weaving là một mô hình khác cần cài đặt và vận hành riêng; không được bật chỉ bởi `proxyTargetClass=true`.

### 8.2. final class/final method/private method

Đừng gắn `@PreAuthorize` vào `private void performSensitiveOperation()` rồi kỳ vọng Spring AOP proxy có thể gọi advice trên private method. Class-based proxy không thể override một method `final`. Một class `final` không thể bị subclass bởi class-based proxy. Đối với interface-based proxy, method được advice phải có đường đi phù hợp qua interface và implementation; các method chỉ có trên concrete target có thể không được gọi thông qua JDK proxy.

Thiết kế an toàn dễ kiểm chứng nhất là **public, non-final method trên Spring-managed service bean**, được **gọi từ bean khác qua injected proxy**. Nếu ngôn ngữ như Kotlin mặc định class/method là final, cần xem plugin/framework hỗ trợ “open” classes hoặc bố trí interface/advice tương thích.

### 8.3. @PreAuthorize trên interface hay implementation?

Cách phát hiện annotation có thể liên quan method declaration, interface, superclass và quy tắc resolution trong phiên bản Spring Security đang dùng. Tránh dựa vào suy đoán “framework tự tìm mọi annotation ở mọi nơi”.

Trong codebase lớn:
- đặt policy tại **boundary công khai của service** mà caller thật sự sử dụng;
- giữ một quy ước nhất quán (ví dụ trên service implementation public methods);
- không khai báo annotation mâu thuẫn trên interface/implementation/override;
- viết test gọi đúng bean qua type mà production sử dụng.

Nếu annotations trong class hierarchy gây ambiguity hoặc application startup lỗi, đọc thông báo rõ ràng và điều chỉnh policy placement, không che bằng cách bắt và nuốt exception.

## 9. Những lỗi cấu hình @EnableMethodSecurity thường gặp

### 9.1. Thiếu annotation hoặc đặt ở class không được nạp

Có class:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityMethodConfig {
}
~~~

nhưng class nằm ngoài phạm vi component scan và không được import vào context. Khi đó annotation **không có tác dụng**, dù nhìn thấy trong source. Kiểm `@SpringBootApplication` base package, `@Import`, test slices/profiles và các cấu hình condition.

### 9.2. Nhầm @EnableWebSecurity với @EnableMethodSecurity

`@EnableWebSecurity`/`SecurityFilterChain` liên quan web security. `@EnableMethodSecurity` kích hoạt method security. Đừng suy từ việc HTTP Basic login chạy đúng rằng `@PreAuthorize` chắc chắn đã được kích hoạt.

### 9.3. Config Spring Security 5 đã được migrate một phần

Một số dự án cũ dùng:

~~~java
@EnableGlobalMethodSecurity(prePostEnabled = true)
~~~

Khi chuyển sang Spring Security 6, ưu tiên dùng `@EnableMethodSecurity`. **Không trộn ví dụ cũ và API mới** mà không kiểm dependency/version; cách đăng ký interceptors và cấu hình annotations đã thay đổi theo các đời framework.

### 9.4. Multi-module và context khác nhau

Nếu controller ở ứng dụng A nhưng service là một thư viện được khởi tạo trong context B, method-security configuration có thể không tồn tại ở context chứa bean. Hoặc test `@WebMvcTest` chỉ load MVC components, không load service/configuration bạn nghĩ có mặt. Khi đó hãy kiểm **bean instances và active context**, không chỉ grep source.

### 9.5. @Configuration(proxyBeanMethods=false) không phải nút bật/tắt method security

`proxyBeanMethods` trên `@Configuration` quyết định một kiểu proxying của configuration bean methods, **không phải** công tắc cho `@PreAuthorize` trên service methods. Đừng thử đổi property đó như một giải pháp chung cho method security.

## 10. SpEL sai có thể trông giống lỗi proxy

Với method security đã được intercept, expression vẫn có thể không đúng với nghiệp vụ.

### 10.1. hasRole và hasAuthority

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void adminAction() {
    // ...
}
~~~

`hasRole('ADMIN')` thường đối chiếu authority `ROLE_ADMIN` theo role prefix mặc định. `hasAuthority('ADMIN')` đối chiếu **chuỗi chính xác** `ADMIN`. Nếu hệ JWT chỉ phát authority `SCOPE_reports.read` mà bạn viết `hasRole('ADMIN')`, request sẽ không được cho phép trừ khi authority converter/policy cung cấp role đó.

Một expression sai thường gây **từ chối quá mức** (403), không phải giải thích hợp lý cho việc bypass qua self-invocation. Tuy vậy vẫn cần kiểm authorities thật khi phân tích test.

### 10.2. Parameter names trong SpEL

~~~java
@PreAuthorize("#accountId == authentication.name")
public String readMyData(String accountId) {
    return accountId;
}
~~~

Đây là fragment. Để `#accountId` được resolve theo tên parameter, compiler/runtime cần metadata hoặc annotation phù hợp. Với Java, có thể cấu hình `-parameters` trong build. Khi thiếu metadata, expression có thể đánh giá khác hoặc gây exception; kiểm parameter name discovery của version đang chạy.

Một số phương án:
- thêm `-parameters` trong Maven/Gradle compiler configuration;
- dùng `@P` cho parameter name khi API hỗ trợ;
- dùng chỉ số parameter như `#p0` theo contract của method-security SpEL;
- viết authorization service có unit/integration tests rõ ràng.

**Không lấy actor identity từ client-supplied `accountId` mà không kiểm với Authentication**. Khi kiểm ownership, phải đối chiếu user/tenant/permission thật, không coi có annotation là đủ.

### 10.3. User/service gọi helper protected method nội bộ

Ngay cả khi `@PreAuthorize("@permissionService.canEdit(authentication,#id)")` được viết đúng, nó cũng **không chạy** nếu protected method bị gọi qua `this`. Vì vậy nên kiểm **call graph/proxy path** trước khi dành thời gian sửa expression.

### 10.4. @PreAuthorize không bảo vệ mọi code path

Nếu cùng thao tác nghiệp vụ có đường gọi từ:
- REST Controller;
- scheduled job;
- message listener;
- batch task;
- một service khác;
- hoặc service tự gọi chính mình;

thì phải xác định entry points nào đi qua proxy, và background job có Authentication phù hợp hay không. Trong job không có end-user security context, policy `hasRole` có thể từ chối hoặc ném lỗi. Không tự giả lập SYSTEM admin trong mọi job; thiết kế quyền của service principal/system task tường minh.

## 11. SecurityFilterChain và method security là hai lớp khác nhau

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Chỉ yêu cầu người dùng đăng nhập ở URL; không hề bảo đảm “chỉ ADMIN mới gọi mọi service”. Nếu method protection đúng, một USER có thể được HTTP layer cho đi tiếp nhưng bị từ chối ở service và trả 403.

~~~text
GET /api/direct với ROLE_USER
    |
    +-- HTTP authentication Basic -> SUCCESS
    |
    +-- URL authorization authenticated() -> ALLOW
    |
    +-- Method security hasRole('ADMIN') -> DENY
    |
    v
HTTP 403
~~~

Với self-invocation:

~~~text
GET /api/unsafe với ROLE_USER
    |
    +-- HTTP authentication Basic -> SUCCESS
    |
    +-- URL authorization authenticated() -> ALLOW
    |
    +-- Public outer service method -> ALLOW (không có rule)
    |
    +-- target.this.privilegedAction() -> KHÔNG qua proxy
    |
    v
HTTP 200 trong demo (BUG)
~~~

**Đừng thêm `.permitAll()` để chữa 403 do method security.** Và đừng xem `.authenticated()` là đủ cho object-level authorization. Quy tắc bảo mật cần được đặt ở boundary tương ứng với dữ liệu và nghiệp vụ.

## 12. Các cách sửa: nên dùng gì, nên tránh gì?

### 12.1. Ưu tiên: tách bean và rõ authorization boundary

Tách `SensitiveOperationService` có protected method, các workflow gọi nó qua Spring-managed dependency. Tạo test cả caller được phép và bị từ chối, kể cả người dùng thiếu quyền.

### 12.2. Nếu chỉ có một entry point: bảo vệ outer method

Có thể gắn chính sách phù hợp lên public outer method:

~~~java
@PreAuthorize("hasRole('MANAGER')")
public void approveAndPublish() {
    approveInternal();
    publishInternal();
}
~~~

Đây là **fragment**, chỉ an toàn nếu **mọi đường gọi** đều qua public outer method được proxy và policy bảo vệ toàn bộ việc thực hiện. Nếu inner method còn bị gọi trực tiếp từ nơi khác hoặc policy inner mạnh hơn, phải xem lại. Không coi đây là giải pháp chung cho service lớn.

### 12.3. Dùng authorization service tường minh khi phù hợp

Đối với một số business operations nhạy cảm, bạn có thể viết kiểm quyền tường minh tại application/service layer, ví dụ dependency `AuthorizationService.requirePermission(actor, resource)` được gọi ngay trước side effect. Điều này có thể giảm phụ thuộc vào AOP ở những luồng khó proxy, nhưng code phải bao phủ **mọi call sites** và có tests. **Không** sao chép actor do client gửi mà coi là authenticated.

### 12.4. Self-injection / AopContext là workaround, không phải mặc định

Một số mẫu lấy chính proxy của bean thông qua `ObjectProvider`, self-injection hoặc `AopContext.currentProxy()`. Chúng có thể cần `exposeProxy=true`, dẫn tới coupling với AOP, nguy cơ circular dependency và khó hiểu lifecycle.

Không khuyến nghị các kỹ thuật này là bản sửa đầu tiên cho `@PreAuthorize` trong ứng dụng nghiệp vụ. **Refactor thành hai beans và boundary rõ** đơn giản hơn, dễ test hơn và tránh giữ target reference sai.

### 12.5. AspectJ weaving là lựa chọn kiến trúc khác

Spring hỗ trợ các mô hình weaving khác Spring AOP proxy, nhưng cần **module, plugin, JVM/instrumentation và cấu hình cụ thể**. AspectJ có thể xử lý những trường hợp self-invocation khác proxy-based AOP, tùy cách weaving, nhưng không tự bật chỉ nhờ `@EnableMethodSecurity` mặc định.

Không đổi sang AspectJ chỉ để “sửa nhanh” một class; cân nhắc build/deploy complexity, hiệu năng, compatibility và kiểm thử toàn bộ. Nếu chưa có lý do kỹ thuật rõ ràng, tách service beans thường là phương án ít rủi ro hơn.

## 13. @Transactional, @Async và chuyện nhiều advice

Vấn đề self-invocation là một tính chất chung của nhiều Spring AOP features.

### 13.1. @Transactional

Nếu method A trong service gọi `this.methodB()` mà methodB có `@Transactional`, transaction advice trên B có thể không áp dụng. Điều này dễ bị nhầm với lỗi database hoặc JPA flush. Với `@PreAuthorize` và `@Transactional` trên cùng method, **cả hai đều cần lời gọi đi qua proxy** và có thể có thứ tự advice/transaction khác nhau theo cấu hình. Không giả định authorization nhất định luôn xảy ra trước khi transaction được mở trừ khi đã kiểm order cụ thể.

### 13.2. @Async

Một method `@Async` gọi qua `this.asyncMethod()` có thể chạy đồng bộ do advice bị bypass. Nếu thực sự chạy trên executor khác, `SecurityContextHolder` dùng ThreadLocal có thể không được truyền như mong đợi; method security có thể thấy Authentication khác hoặc null.

Hãy tách hai vấn đề:
1. **Proxy entry:** advice có được gọi không?
2. **Authentication propagation:** nếu advice chạy trên thread khác, có security context đúng không?

Trong Spring Security, có các wrapper như `DelegatingSecurityContextExecutor` và tích hợp cho một số Spring MVC async modes. Không tự chuyển mọi security context sang background jobs bằng InheritableThreadLocal.

### 13.3. @Cacheable

Nếu cache advice trên protected method bị self-invocation bypass, kết quả không được cache như dự kiến. Nguy hiểm hơn, nếu policy và cache phối hợp không đúng, cache key có thể lẫn dữ liệu giữa users/tenants. Luôn thiết kế cache key/authorization rõ ràng, không dựa vào proxy như biện pháp cách ly duy nhất.

## 14. HTTP 401, 403, 500 và exception handling

`@PreAuthorize` chạy trước target method (khi intercept đúng), có thể đưa ra access denial exception. Trong Servlet request thông qua Spring Security filters, `ExceptionTranslationFilter` và các thành phần liên quan chuyển exception theo context thành response 401/403/redirect.

| Kết quả | Giải thích phổ biến | Cách xác minh |
| --- | --- | --- |
| **401** | HTTP authentication chưa có hoặc credential sai (với Basic entry point). | Kiểm HTTP auth filter, header và provider. |
| **302** | App dùng form login và redirect tới login page. | Kiểm entry point, Accept header/saved request. |
| **403** | Có Authentication nhưng thiếu authority/permission, hoặc CSRF denial. | Phân biệt method denial và CSRF/filter denial. |
| **200 bất thường** | Rule không áp dụng, self-invocation, method chưa proxy, hoặc user có quyền thật. | Test role yếu và xem call graph. |
| **500** | Expression lỗi, bean/proxy conflict, exception bị handler map sai, hoặc application bug. | Đọc exception type/stack trace đã sanitize. |

**Lưu ý:** 403 không nhất thiết do `@PreAuthorize`: CSRF và URL authorization cũng có thể trả 403. Và một HTTP status 200 không tự chứng minh service method thật sự đã chạy; hãy kiểm response và side effect trong test phù hợp.

### Vì sao @ControllerAdvice có thể che dấu lỗi?

Một global handler bắt quá rộng `Exception.class` hoặc `RuntimeException.class` có thể chuyển `AccessDeniedException` thành HTTP 200, 400 hoặc 500 không đúng contract. Không “chữa” bằng cách nuốt denial; hãy để Spring Security xử lý hoặc map exception đúng và tránh tiết lộ internals.

Trong service unit test không chạy Servlet filters, `AccessDeniedException` có thể được ném trực tiếp. Không kỳ vọng nó tự tạo HTTP response nếu không có web request.

## 15. Debug logging và quan sát method security

Trong môi trường phát triển, có thể tạm bật log:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.aop: DEBUG
~~~

Hoặc tăng `TRACE` có giới hạn để xem chi tiết filter/advisor trong môi trường cách ly. Nhưng log level cao có chi phí và có thể lộ thông tin về authentication/cấu hình; **không bật lâu dài ở production**, không dump password, JWT, Authorization header, session cookie hoặc raw principal.

### Thứ cần quan sát

1. `ApplicationContext` đã nạp config chứa `@EnableMethodSecurity` chưa?
2. Bean đang gọi có phải Spring AOP proxy không? Proxy JDK hay CGLIB?
3. Call site bên ngoài gọi bean reference hay `this.method()`?
4. Method bị bảo vệ là public/non-final? Có method override/overload không?
5. Authentication có authority thật gì? Chuỗi role có prefix đúng không?
6. Khi deny, exception bị ném ở đâu và ai chuyển sang status?
7. Test có dùng đúng context/security filters không?
8. Sự cố chỉ xảy ra ở một entry point, thread hoặc background job?

Nếu muốn ghi audit khi method bị từ chối, dùng cơ chế event/authorization observability có hỗ trợ theo version và application policy. **Đừng log token hoặc cả Authentication object** để xác minh role; chỉ ghi tên class/principal ID đã chuẩn hóa khi được phép và reason code hữu hạn.

## 16. Mô hình checklist để khoanh vùng lỗi nhanh

| Câu hỏi | Nếu “không” hoặc sai | Hành động |
| --- | --- | --- |
| Project có `@EnableMethodSecurity` được nạp không? | Không có method-security advisors. | Đưa annotation vào Spring configuration thực sự được load. |
| Object có phải Spring bean không? | `new Target()` không có proxy. | Inject bean từ ApplicationContext. |
| Bean reference có phải AOP proxy không? | Không có proxy hoặc advisor không match. | `AopUtils.isAopProxy` và kiểm config/annotation. |
| Caller đi qua proxy? | `this.method()` bypass inner advice. | Tách bean và gọi qua injected dependency. |
| Method có thể intercept? | `private`/`final`/final class/visibility sai. | Dùng public non-final entry point, kiểm proxy strategy. |
| Role thật đúng? | `ROLE_ADMIN` vs `ADMIN`/`SCOPE_*`. | Kiểm authorities, expression và converter. |
| Tham số SpEL resolve đúng? | Thiếu `-parameters`/sai property. | Kiểm build metadata, `#p0`/`@P` khi phù hợp. |
| Test có chạy security infrastructure? | `@WebMvcTest` thiếu beans hoặc unit test gọi new. | `@SpringBootTest`/configured Spring test context. |
| Có đúng target method/overload? | Annotation ở method khác. | Tìm call site thực tế và test behavior. |
| Exception có bị thay đổi? | 200/500 dù method deny. | Kiểm `@ControllerAdvice`/exception translation. |
| Có nhiều chains/contexts? | HTTP code path khác dự kiến. | Test chain matcher, bean instance, config profiles. |
| Có async thread? | SecurityContext không được truyền. | Context propagation rõ ràng và test thread. |

### Thứ tự kiểm tra tối ưu

**Bước 1:** Tái hiện bằng hai identities — USER và ADMIN — qua cùng một HTTP endpoint, không chỉ một mock test.

**Bước 2:** Xác nhận `@EnableMethodSecurity` có hiệu lực và bean được inject là proxy.

**Bước 3:** Kiểm entry point/call graph có lệnh gọi nội bộ `this.` không. Nếu có, đây thường là bước mang lại lời giải nhanh nhất.

**Bước 4:** Kiểm method visibility, final modifiers và proxy type. Đừng tự động chuyển proxy type mà chưa xác định vấn đề.

**Bước 5:** Kiểm SpEL, authorities, parameter names và policy configuration.

**Bước 6:** Kiểm exceptions/status conversion, đặc biệt khi controller/global exception handlers tùy biến.

**Bước 7:** Sau khi sửa, thêm negative tests cho **mọi public/business entry point** có thể dẫn đến thao tác nhạy cảm; không chỉ test annotated method trực tiếp.

## 17. Những anti-pattern nguy hiểm cần nhận diện

### 17.1. Chỉ gắn annotation cho method nội bộ “nhạy cảm”

~~~java
public void checkout() {
    this.commitPayment();
}

@PreAuthorize("hasRole('PAYMENT_ADMIN')")
public void commitPayment() {
    // Side effect.
}
~~~

Nếu `checkout()` là entry point được gọi qua proxy nhưng không có policy tương đương, `commitPayment()` có thể được gọi mà không chạy authorization advice. Ngay cả khi role policy có ở method inner, nó chưa bảo vệ luồng thực.

**Sửa:** tách `PaymentCommitService` có method protected, hoặc thiết kế kiểm quyền ở boundary public trước side effect; cần idempotency, ownership và transaction policy riêng.

### 17.2. Dựa vào @PreAuthorize để chống IDOR nhưng parameter lấy từ client

~~~java
@PreAuthorize("isAuthenticated()")
public Order loadOrder(UUID orderId) {
    return repository.getReferenceById(orderId);
}
~~~

Fragment này không bảo vệ ownership; một user đã đăng nhập có thể cố lấy orderId của người khác. Khi cần bảo vệ object-level access, expression/service phải kiểm **actor, tenant và đối tượng** phù hợp. Proxy chỉ giúp thực thi policy đã viết, không sửa policy quá yếu.

### 17.3. Test với user có toàn quyền

Một bộ test chỉ dùng ADMIN sẽ không thể phát hiện service đã mất `@PreAuthorize`: cả trước/sau đều trả thành công. Luôn có test negative với USER và anonymous, và test một pathway từng dễ bị self-invocation bypass.

### 17.4. Bắt AccessDeniedException rồi cho qua

~~~java
try {
    service.privilegedAction();
} catch (AccessDeniedException ex) {
    return successFallback();
}
~~~

Đây là fragment anti-pattern; nuốt denial và coi như thành công có thể biến authorization failure thành bypass logic. Nếu muốn báo lỗi hợp lệ, phải trả failure response hoặc propagate phù hợp; không thực thi side effect thay thế mà policy cũng phải chặn.

### 17.5. Tự gọi method security annotation bằng reflection

Gắn `@PreAuthorize` rồi invoke method trên target object bằng reflection cũng có thể bypass proxy. Reflection không tự “kích hoạt” Spring advisors. Nếu cần dynamic invocation, đi qua bean proxy và những APIs được hỗ trợ, test rõ từng path.

## 18. Câu hỏi tự kiểm tra và đáp án

**Câu 1. Vì sao `@PreAuthorize` ở `deleteInvoice()` không chạy khi `createInvoice()` gọi `this.deleteInvoice()`?**

Vì Spring AOP proxy intercept ở ranh giới lời gọi qua proxy. Lệnh `this.deleteInvoice()` chạy trực tiếp trên target, không đi qua proxy nên method-security advice ở method inner không được gọi.

**Câu 2. Đổi `@EnableMethodSecurity(proxyTargetClass=true)` có sửa self-invocation không?**

Không. Class-based proxy và JDK dynamic proxy đều có giới hạn self-invocation trong mô hình Spring AOP proxy. Cần đổi call graph hoặc mô hình weaving, không chỉ đổi proxy type.

**Câu 3. Spring Security Basic hoạt động nhưng `@PreAuthorize` không chạy. Nguyên nhân có thể là gì?**

Web security và method security là hai tầng khác nhau. Có thể thiếu `@EnableMethodSecurity`, bean/proxy không đúng hoặc gọi nội bộ. Việc Basic xác thực thành công không chứng minh method security được bật.

**Câu 4. `AopUtils.isAopProxy(service)==true` có bảo đảm mọi method annotation đều chạy không?**

Không. Proxy có thể tồn tại vì advisor khác hoặc protected method không được gọi qua proxy. Cần test deny/allow ở đúng entry point và xác minh advisor/annotation placement.

**Câu 5. Với `hasRole('ADMIN')`, authority nào được mong đợi mặc định?**

Thông thường `ROLE_ADMIN`. Nếu dùng `hasAuthority('ADMIN')`, chuỗi mong đợi là chính xác `ADMIN`. Với JWT scopes thường là `SCOPE_*` theo converter mặc định, không phải tự động `ROLE_ADMIN`.

**Câu 6. Cách sửa đơn giản nhất nếu WorkflowService tự gọi sensitive method trong cùng class là gì?**

Tách sensitive operation thành một Spring-managed service khác và inject nó vào WorkflowService, khiến lời gọi protected method đi qua Spring proxy.

**Câu 7. Unit test `new SensitiveService().privilegedAction()` trả 200 hay exception?**

Nó chỉ là lời gọi Java trực tiếp, không có HTTP và không có proxy; nó sẽ thực thi body và trả kết quả. Không thể suy từ đó về method-security integration thực của application.

**Câu 8. HTTP 403 có đủ chứng minh `@PreAuthorize` hoạt động không?**

Chưa. 403 có thể do URL authorization, CSRF, reverse proxy hoặc business rule khác. Phải test method boundary và xác định exception/code path.

**Câu 9. Nếu `@PreAuthorize` chạy trong `@Async` worker nhưng không có Authentication, có phải proxy mất tác dụng không?**

Không nhất thiết. Proxy advice có thể chạy nhưng `SecurityContext` không được truyền sang thread mới. Cần phân biệt proxy interception với security context propagation.

**Câu 10. Có nên để một endpoint “unsafe” như demo trên production để quan sát proxy không?**

Không. Endpoint `/api/unsafe` chỉ là bài học tái hiện lỗ hổng. Khi sửa, xóa unsafe path, triển khai authorization boundary nhất quán và viết negative tests cho mọi đường đi tới thao tác nhạy cảm.

## 19. Bài tập thực hành

1. **Tắt @EnableMethodSecurity trong demo, chạy test.** Quan sát `directCallDeniesNonAdmin` và `refactoredCrossBeanCallDeniesNonAdmin` không còn từ chối đúng. Giải thích vì sao HTTP `authenticated()` vẫn cho ROLE_USER đi qua URL.
2. **Giữ annotation và thử self-invocation.** Xem test `internalThisCallDemonstratesBypass` trả 200 với alice. Vẽ call graph chỉ ra proxy bị bỏ qua ở đâu.
3. **Tách bean.** Di chuyển privileged method sang service riêng. Viết test USER bị 403, ADMIN được 200 qua cả direct và orchestration path; xóa hoàn toàn endpoint cố tình bypass.
4. **Tạo method final.** Thử đánh dấu protected method `final` khi dùng class-based proxy. Ghi lại proxy limitation và lý do framework không thể override method đó; không đưa kiểu thử nghiệm này lên production.
5. **Thêm hasAuthority.** Dùng `@PreAuthorize("hasAuthority('SCOPE_orders.read')")` cho method mới. Tạo principal có đúng scope và principal không có scope, kiểm allow/deny. Không nhầm `SCOPE_orders.read` với `ROLE_ADMIN`.
6. **Thử thiếu parameter metadata.** Dùng expression `#accountId`; thay build option `-parameters` trong môi trường thử. Quan sát cách Spring Security tìm tên parameter và so sánh với cách dùng `#p0`.
7. **Tạo một HTTP access test.** Xác nhận 401 khi thiếu Basic, 403 khi alice gọi protected method qua proxy, 200 khi admin gọi; đừng gộp authentication và method authorization thành cùng một nguyên nhân.
8. **Mở rộng sang object permission.** Tạo `OrderAuthorizationService.canView(Authentication, UUID)` và annotation kiểm quyền. Test actor thuộc tenant A không thể đọc đối tượng tenant B, bất kể actor biết object ID.
9. **Kiểm multiple entry points.** Nếu service được gọi từ REST, scheduler và message consumer, hãy lập bảng context/proxy path của từng entry point; chỉ cho phép operation khi policy được thực thi tương ứng.
10. **Viết regression test.** Sau khi sửa self-invocation, giữ ít nhất một negative integration test chứng minh USER **không thể** hoàn thành thao tác từ mọi public method có thể dẫn tới nó.

## 20. Checklist cuối cùng trước khi coi lỗi đã sửa

- [ ] Đã xác nhận `@EnableMethodSecurity` thuộc configuration đang thực sự được load.
- [ ] Service chứa `@PreAuthorize` là Spring-managed bean, không phải instance tạo bằng `new`.
- [ ] Method có thể intercept theo proxy strategy, không rơi vào private/final/self-invocation bất khả thi.
- [ ] Mọi caller quan trọng gọi qua Spring proxy, không thông qua `this.method()` trên target.
- [ ] Nếu tách bean, dependency là bean do Spring inject, không phải target reference tự giữ.
- [ ] Expression đúng role prefix, authority, SpEL parameter names và business permission.
- [ ] HTTP SecurityFilterChain và method security có policy phân tầng rõ ràng.
- [ ] Test context có method-security infrastructure và đúng authentication mechanism.
- [ ] Có test USER bị từ chối và ADMIN được cho phép ở đúng service entry.
- [ ] Có negative test cho từng đường đi nghiệp vụ quan trọng, không chỉ method trực tiếp.
- [ ] Không lạm dụng AopContext/self-injection chỉ để che cấu trúc service.
- [ ] Không thay đổi proxy mode một cách mù quáng hoặc vô hiệu hóa authorization để test pass.
- [ ] Không log credential, full principal hay token khi debug method-security issues.
- [ ] Không để lại endpoint cố ý bypass trên môi trường thật.
- [ ] Với task async/background, security context và system principal có policy rõ ràng.
- [ ] Với object authorization, đã kiểm tenant/ownership/target, không chỉ role tổng quát.

**Kết luận:** Khi `@PreAuthorize` “không chạy”, hãy kiểm **ba câu hỏi theo thứ tự**: (1) `@EnableMethodSecurity` đã hoạt động chưa? (2) method mục tiêu có **Spring AOP proxy phù hợp** không? (3) **lời gọi cụ thể có đi qua proxy** hay chỉ là `this.method()` trong target? Phần lớn sai lầm chẩn đoán đến từ việc chỉ nhìn annotation mà bỏ qua call graph. Cách sửa bền vững thường là **đặt chính sách trên một public service boundary và gọi qua bean được inject**, sau đó kiểm chứng với USER, ADMIN và anonymous bằng integration tests.