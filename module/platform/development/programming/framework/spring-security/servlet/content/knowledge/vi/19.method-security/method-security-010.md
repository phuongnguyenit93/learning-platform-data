# Spring AOP proxy, lời gọi nội bộ và giới hạn bảo vệ phương thức trong Spring Security Servlet

**Phạm vi:** Java 17+, Spring Boot 3.x, Spring Security 6.x và ứng dụng Servlet. Bài thuộc nhóm **Bảo vệ phương thức**. Trọng tâm là cách Spring AOP proxy kích hoạt <code>@PreAuthorize</code>, vì sao lời gọi nội bộ <code>this.method()</code> có thể bỏ qua interceptor, những hạn chế của JDK proxy/CGLIB và cách sửa, kiểm thử, review kiến trúc để quyền được thực thi nhất quán.

**Thông điệp cốt lõi:** một method có annotation bảo mật **không có nghĩa** mọi lần gọi Java tới method đều được bảo vệ. Với proxy-based method security, interceptor chỉ quan sát những lời gọi đi qua Spring proxy. Nếu code gọi trực tiếp target, nhất là lời gọi nội bộ qua <code>this</code>, phần kiểm tra quyền có thể không chạy.

## 1. Method security và HTTP security không thay thế nhau

Trong Spring Security có nhiều tầng quyết định quyền:

| Tầng | Cơ chế | Vai trò |
| --- | --- | --- |
| HTTP | <code>SecurityFilterChain</code>, <code>authorizeHttpRequests</code> | Chặn request theo URL, HTTP method, trạng thái authentication hoặc role tổng quát |
| Method | <code>@PreAuthorize</code>, <code>@PostAuthorize</code>, method interceptors | Bảo vệ việc gọi operation/service theo authority hoặc policy |
| Policy | Bean quyết định quyền trên action/resource | Xét owner, tenant, dữ liệu, trạng thái |
| Persistence | Query scope, transaction, version, constraint | Không để tác vụ chạm dữ liệu ngoài phạm vi, tránh TOCTOU |

Ví dụ một lớp service:

~~~java
@PreAuthorize("hasAuthority('report:export')")
public String exportRestrictedData() {
    return "confidential-report";
}
~~~

Khi lời gọi **đi qua Spring proxy đã được cấu hình method security**, user không có <code>report:export</code> bị từ chối trước khi method chạy. Nhưng chỉ nhìn vào annotation trong source là chưa đủ để biết tất cả đường gọi có đi qua proxy hay không.

Một URL được bảo vệ bằng <code>authenticated()</code> chỉ yêu cầu danh tính đã xác thực. Người có <code>report:read</code> không mặc nhiên có <code>report:export</code>. Ngược lại, method security không tự thay thế CSRF, login/logout, session, entry point, CORS và các kiểm tra tại Servlet layer.

## 2. Spring AOP proxy được đặt trước target bean

Spring có thể tạo một proxy bao quanh object nghiệp vụ để chạy thêm advice/interceptor. Một bean khác inject dependency thường nhận proxy do container quản lý thay vì tự tạo target object.

~~~text
Controller hoặc OtherService
           |
           v
      Spring proxy
           |
       Method interceptor
       @PreAuthorize
          / \
       deny  allow
        |      |
        v      v
       403   Target service method
                 |
                 v
             Business logic
~~~

<code>Proxy</code> nhận lời gọi đến public service method, cho method-security interceptor đánh giá <code>Authentication</code> và authority, rồi chuyển tiếp đến target khi được phép. Nếu bị từ chối, thường xuất hiện <code>AccessDeniedException</code> (hoặc subclass), được web security layer chuyển thành response thích hợp.

Đây là **interception**, không phải JVM tự hiểu <code>@PreAuthorize</code> như một lệnh <code>if</code> chạy ở mọi lần gọi method. Proxy không phải sandbox ngăn tất cả code nội bộ tự truy cập repository hay object thật.

### Kích hoạt method security

Trong Spring Security 6, cấu hình thường dùng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Khi áp dụng, <code>@EnableMethodSecurity</code> đăng ký hạ tầng method authorization cho các annotation được bật; <code>@PreAuthorize</code>/<code>@PostAuthorize</code> được hỗ trợ theo cấu hình chuẩn. Không có cấu hình method security phù hợp, annotation có thể hiện diện mà không có interceptor.

Không dùng việc import thành công một annotation làm bằng chứng phương thức đã được bảo vệ; cần test chạy trên bean được Spring quản lý với application context thực.

## 3. Self-invocation: lời gọi nội bộ không đi qua proxy

Ví dụ service có lỗi cố ý:

~~~java
@Service
public class UnsafeReportService {

    public String runInsecureWorkflow() {
        return this.exportRestrictedData();
    }

    @PreAuthorize("hasAuthority('report:export')")
    public String exportRestrictedData() {
        return "confidential:2026";
    }
}
~~~

Giả sử user chỉ có <code>report:read</code>. Nếu caller gọi <code>unsafeReportService.exportRestrictedData()</code> qua Spring proxy, method-security interceptor thấy <code>@PreAuthorize</code> và từ chối.

Nhưng khi caller gọi <code>unsafeReportService.runInsecureWorkflow()</code>:
1. Proxy nhận lời gọi <code>runInsecureWorkflow()</code>.
2. Outer method không có authorization rule của chính nó, nên proxy cho target xử lý.
3. Target gọi <code>this.exportRestrictedData()</code> **trên chính target object**.
4. Inner call không quay lại proxy, nên interceptor gắn với inner method không được kích hoạt.
5. Logic <code>exportRestrictedData()</code> chạy dù user không có export authority.

~~~text
Caller               Spring proxy                 Target UnsafeReportService
  |                        |                                 |
  | runInsecureWorkflow()  |                                 |
  |----------------------->|                                 |
  |                        | runInsecureWorkflow()           |
  |                        |-------------------------------->|
  |                        |                                 |
  |                        |       this.exportRestrictedData()
  |                        |       (bỏ qua proxy)             |
  |                        |                                 |
  |<-----------------------|<--------------------------------|
  |       confidential:2026                                 |
~~~

**Đây là một lỗi bảo mật thực sự nếu outer method là một entry point có thể truy cập.** Người học cần hiểu cơ chế này thay vì chỉ đặt thêm annotation lên inner method rồi nghĩ rằng mọi call đều được bảo vệ.

Trong dự án thực hành bên dưới, <code>UnsafeReportService</code> chỉ phục vụ test chứng minh bypass, **không được nối vào HTTP Controller**.

## 4. Khác biệt giữa lời gọi qua proxy và lời gọi qua this

Hai đường:

~~~text
ĐƯỜNG AN TOÀN (cross-bean)
Controller
   |
   v
ReportWorkflowService.runExport()
   |
   v
ReportExportService proxy.exportRestrictedData()
   |
   +--> @PreAuthorize("hasAuthority('report:export')")
           |
           +-- Deny -> dừng
           +-- Allow -> target exportRestrictedData()


ĐƯỜNG KHÔNG AN TOÀN (self-invocation)
UnsafeReportService proxy.runInsecureWorkflow()
   |
   v
Target.runInsecureWorkflow()
   |
   v
this.exportRestrictedData() trên target
   |
   v
Bỏ qua interceptor của exportRestrictedData()
~~~

Một hướng sửa dễ audit là **tách operation yêu cầu quyền cao sang một Spring bean riêng** và cho workflow inject bean đó. Mỗi lần workflow gọi bean được inject, lời gọi đi qua proxy và interceptor có cơ hội từ chối.

Cũng có thể gắn <code>@PreAuthorize</code> trên **public entrypoint** <code>runInsecureWorkflow()</code> nếu toàn bộ workflow phải yêu cầu cùng quyền. Tuy nhiên phải bảo đảm mọi entrypoint khác tới operation vẫn được bảo vệ; chỉ vá một URL/outer method có thể bỏ sót caller mới.

Khi policy cần điều kiện trên tài liệu, owner hoặc tenant, có thể đánh giá tường minh ở domain service/use case. Điều quan trọng không phải “bắt buộc dùng AOP”, mà là **mọi đường thực thi hành động nhạy cảm đều có điểm kiểm tra bắt buộc**.

## 5. JDK dynamic proxy và CGLIB proxy

Spring AOP có hai loại proxy thông dụng:

| Đặc điểm | JDK dynamic proxy | CGLIB/class-based proxy |
| --- | --- | --- |
| Cơ chế | Proxy implement interface | Proxy là subclass của target class |
| API caller thường dùng | Interface | Class hoặc interface |
| Giới hạn | Method concrete-only không có trong interface proxy | Final class không thể subclass, final method không thể override |
| Lời gọi <code>this.inner()</code> | Vẫn bypass proxy | Vẫn bypass proxy |
| Chọn thế nào | Phụ thuộc interface và proxy strategy | Có thể cấu hình <code>proxyTargetClass=true</code> |

Không khẳng định mọi ứng dụng Spring Boot luôn dùng một kiểu proxy. Cách tạo proxy còn phụ thuộc setting Spring AOP, hạ tầng method security và cấu trúc bean.

Khi cần class-based proxy:

~~~java
@Configuration
@EnableMethodSecurity(proxyTargetClass = true)
public class MethodSecurityConfiguration {
}
~~~

Điều này **không sửa self-invocation**, không khiến private method hay static method được intercept, và không thể làm CGLIB override final method. Nếu dự án dùng JDK proxy, caller thường nên inject bằng interface phù hợp; nếu chỉ inject concrete implementation có thể xuất hiện lỗi type/proxy.

Có thể kiểm tra bean ở test:

~~~java
assertThat(AopUtils.isAopProxy(reportExportService)).isTrue();
// Khi cần: AopUtils.isJdkDynamicProxy(bean)
// hoặc AopUtils.isCglibProxy(bean).
~~~

<code>AopUtils</code> thuộc Spring AOP; kiểm tra proxy type giúp chẩn đoán cấu hình, **nhưng bean là proxy chưa đủ bảo đảm mọi call path đều được bảo vệ**.

## 6. Các trường hợp method-security interception có giới hạn

**Private method:** không phải public service API có thể gọi qua JDK proxy; lời gọi nội bộ tới private method không được coi là chỗ gắn policy bắt buộc.

**Final method:** CGLIB không override được final method. Với interface proxy, điều kiện liên quan là lời gọi đi qua interface/proxy; không được kết luận chung một chiều cho mọi chiến lược proxy. Nếu yêu cầu security interception, ưu tiên public, non-final service operations được kiểm thử.

**Final class:** class-proxy bằng subclass không thể thực hiện trên final class; cấu hình cần subclass có thể thất bại khi khởi động.

**Static method:** không phải lời gọi instance đi qua Spring bean proxy.

**Constructor / @PostConstruct:** khi object còn đang khởi tạo, không giả định proxy đã sẵn sàng để intercept lời gọi nội bộ. Startup thường cũng không có SecurityContext người dùng.

**Object tạo bằng new:** constructor thủ công không qua Spring container và bean post-processors; <code>@PreAuthorize</code> không tự trở thành interceptor cho object đó.

**Annotation ở interface/implementation:** Spring Security có quy tắc tìm metadata annotation, nhưng inheritance/đa interface có thể gây mâu thuẫn. Test cấu hình proxy thật; không chỉ nhìn vào chữ annotation trong source.

**Multiple proxies/advice:** <code>@Transactional</code>, <code>@Async</code>, custom AOP advice có thể áp dụng ở các lớp khác nhau và thứ tự advice ảnh hưởng behavior. Không phỏng đoán chỉ dựa trên thứ tự annotation trong file Java.

## 7. Thiết kế dự án thực hành

Dùng **Java 17+, Maven, Spring Boot 3.3.5, Spring Security 6.x**. Ví dụ có hai user demo: <code>reader</code> được <code>report:read</code>; <code>exporter</code> được cả <code>report:read</code> và <code>report:export</code>.

HTTP Basic được chọn để dễ quan sát 401/403/200; các password hardcode chỉ dùng cho localhost. Endpoint public và endpoint export được mở bằng Controller. Class unsafe được tạo như Spring bean nhưng **không expose qua HTTP**; chỉ test dùng nó để minh họa bypass.

~~~text
method-proxy-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/methodproxy/
    │   ├── MethodProxyApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── UnsafeReportService.java
    │   ├── ReportExportService.java
    │   ├── ReportWorkflowService.java
    │   └── ReportController.java
    └── test/java/com/example/methodproxy/
        └── MethodProxySecurityTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-proxy-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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

### 7.2. Application class

Tạo <code>src/main/java/com/example/methodproxy/MethodProxyApplication.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodProxyApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration.java

Tạo <code>src/main/java/com/example/methodproxy/SecurityConfiguration.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-local-123"))
                .authorities("report:read")
                .build(),
            User.withUsername("exporter")
                .password(encoder.encode("exporter-local-123"))
                .authorities("report:read", "report:export")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/reports/public").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

<code>@EnableMethodSecurity</code> kích hoạt method-security advice. HTTP chỉ yêu cầu authenticated cho các URL báo cáo; quyền export chi tiết được enforced ở method service. <code>authorities("report:export")</code> dùng chuỗi chính xác, nên expression là <code>hasAuthority</code>, không phải <code>hasRole</code> tự thêm prefix <code>ROLE_</code>.

Mật khẩu demo được encoder băm; không dùng credential hardcode trong production. CSRF không bị tắt. Nếu có endpoint POST thay đổi trạng thái, phải đánh giá CSRF theo browser/token model và không dùng GET để tạo side effects chỉ cho tiện kiểm thử.

### 7.4. UnsafeReportService.java — cố ý minh họa lỗi

Tạo <code>src/main/java/com/example/methodproxy/UnsafeReportService.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class UnsafeReportService {

    public String runInsecureWorkflow() {
        // CỐ Ý SAI: gọi this trên target, không quay lại proxy.
        return this.exportRestrictedData();
    }

    @PreAuthorize("hasAuthority('report:export')")
    public String exportRestrictedData() {
        return "confidential:2026";
    }
}
~~~

Nếu bean caller gọi proxy <code>unsafe.exportRestrictedData()</code>, rule export được kiểm tra. Nhưng <code>unsafe.runInsecureWorkflow()</code> chuyển vào target và <code>this.exportRestrictedData()</code> đi thẳng đến inner method, làm rule trên inner method bị bỏ qua. **Không đưa service này ra HTTP endpoint** trong ứng dụng thật.

### 7.5. ReportExportService.java — operation protected riêng

Tạo <code>src/main/java/com/example/methodproxy/ReportExportService.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {

    @PreAuthorize("hasAuthority('report:export')")
    public String exportRestrictedData() {
        return "confidential:2026";
    }
}
~~~

Operation này chỉ chạy qua proxy khi caller dùng Spring-managed bean. Nếu không có authority phù hợp, interceptor từ chối trước khi return dữ liệu. Một service thật vẫn cần policy theo tenant, report ownership và query scope, không chỉ kiểm tra một authority.

### 7.6. ReportWorkflowService.java — lời gọi sang bean khác

Tạo <code>src/main/java/com/example/methodproxy/ReportWorkflowService.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.stereotype.Service;

@Service
public class ReportWorkflowService {

    private final ReportExportService exportService;

    public ReportWorkflowService(ReportExportService exportService) {
        this.exportService = exportService;
    }

    public String runExport() {
        // Gọi Spring bean được inject, không phải this.exportRestrictedData().
        return exportService.exportRestrictedData();
    }
}
~~~

Khi workflow được gọi, nó ủy quyền cho một **Spring proxy khác**. Điều này khắc phục đúng nguyên nhân bypass trong demo. Nếu có caller mới tới export service, chính operation vẫn mang policy. Còn nếu một developer inject repository trực tiếp rồi bypass export service, kiến trúc vẫn cần review và test.

### 7.7. ReportController.java — không expose unsafe bean

Tạo <code>src/main/java/com/example/methodproxy/ReportController.java</code>:

~~~java
package com.example.methodproxy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportWorkflowService workflow;

    public ReportController(ReportWorkflowService workflow) {
        this.workflow = workflow;
    }

    @GetMapping("/reports/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/reports/export")
    public String export() {
        return workflow.runExport();
    }
}
~~~

Controller không chứa policy và không inject <code>UnsafeReportService</code>. Endpoint GET trả một nội dung giả lập; trong sản phẩm thật, export có thể tạo job hoặc thay đổi tài nguyên, khi ấy phải chọn HTTP method/CSRF/rate limit/audit phù hợp và không biến một mutation thành GET.

## 8. Kiểm thử bằng Spring Security Test và MockMvc

Tạo <code>src/test/java/com/example/methodproxy/MethodProxySecurityTest.java</code>:

~~~java
package com.example.methodproxy;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodProxySecurityTest {

    @Autowired
    UnsafeReportService unsafe;

    @Autowired
    ReportExportService exportService;

    @Autowired
    ReportWorkflowService workflow;

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "reader", authorities = {"report:read"})
    void selfInvocationBypassesInnerMethodInterceptor() {
        // Bean có proxy nhưng inner call qua this vẫn bypass.
        assertThat(AopUtils.isAopProxy(unsafe)).isTrue();

        assertThatThrownBy(() -> unsafe.exportRestrictedData())
            .isInstanceOf(AccessDeniedException.class);

        // Đây là bằng chứng lỗi, không phải hành vi được khuyến nghị.
        assertThat(unsafe.runInsecureWorkflow())
            .isEqualTo("confidential:2026");
    }

    @Test
    @WithMockUser(username = "reader", authorities = {"report:read"})
    void crossBeanInvocationEnforcesPolicy() {
        assertThat(AopUtils.isAopProxy(exportService)).isTrue();

        assertThatThrownBy(() -> workflow.runExport())
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "exporter",
        authorities = {"report:read", "report:export"})
    void exporterMayCallProtectedOperation() {
        assertThat(workflow.runExport()).isEqualTo("confidential:2026");
    }

    @Test
    void httpBoundaryAndMethodSecurityWorkTogether() throws Exception {
        mvc.perform(get("/reports/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/reports/export"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/reports/export")
                .with(httpBasic("reader", "reader-local-123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/reports/export")
                .with(httpBasic("exporter", "exporter-local-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("confidential:2026"));
    }
}
~~~

Bộ test chứng minh hai hành vi rất khác:
- Bean unsafe có proxy. Gọi trực tiếp method có annotation từ bên ngoài thì reader bị deny; nhưng cùng reader gọi outer method rồi <code>this.exportRestrictedData()</code> thì bypass.
- Bean export an toàn có proxy; cross-bean call từ workflow thực thi policy và reader bị deny.
- Exporter có quyền thì được phép.
- MockMvc đưa request qua cả HTTP security và method security, tạo status 200/401/403 dự kiến.

Test cố ý cho unsafe method trả secret là một **bài kiểm thử phát hiện vulnerability**. Trong code production, phải loại bỏ luồng bypass, không mở HTTP route và không coi test này là điều kiện “thành công nghiệp vụ”.

Dùng <code>@SpringBootTest</code> để nạp thực sự Spring-managed beans và method-security interceptor. Một <code>@WebMvcTest</code> hoặc một mock service có thể không đại diện đúng hạ tầng proxy của production; ít nhất một bài integration test phải kiểm tra call path thật.

## 9. Chạy bằng Maven và kiểm tra 401/403/200

Trong thư mục có pom.xml:

~~~bash
mvn test
mvn spring-boot:run
~~~

Tại terminal khác:

~~~bash
# Anonymous được xem nội dung public.
curl -i http://localhost:8080/reports/public

# Anonymous không có quyền truy cập export.
curl -i http://localhost:8080/reports/export

# Reader đã đăng nhập nhưng thiếu report:export.
curl -i -u reader:reader-local-123 http://localhost:8080/reports/export

# Exporter có authority report:export.
curl -i -u exporter:exporter-local-123 http://localhost:8080/reports/export
~~~

| Caller | HTTP authenticated() | Method @PreAuthorize | Kết quả dự kiến |
| --- | --- | --- | --- |
| Anonymous GET /reports/public | permitAll | Không áp export | 200, public |
| Anonymous GET /reports/export | Không đạt | Không đến service | 401 (Basic) |
| Reader GET /reports/export | Đạt | Thiếu report:export | 403 |
| Exporter GET /reports/export | Đạt | Có report:export | 200, confidential:2026 |

Nếu reader nhận 200 thay vì 403, kiểm tra <code>@EnableMethodSecurity</code>, bean có được proxied, đường Controller -> Workflow -> ExportService có đúng hay không và method được gọi thực sự qua proxy. Đừng “sửa” tạm bằng cách chỉ thêm if ở Controller vì service vẫn có thể bị caller khác gọi từ batch/message handler.

Status trên là kết quả dự kiến cho cấu hình minh họa, **không phải kết quả Maven đã chạy sẵn**. Mã được thiết kế và kiểm tra logic tĩnh; chạy thực tế với JDK 17+/Maven để xác nhận đầy đủ.

## 10. @PreAuthorize so với @PostAuthorize và các annotation khác

| Cơ chế | Khi kiểm tra | Lưu ý |
| --- | --- | --- |
| <code>@PreAuthorize</code> | Trước lời gọi method | Thích hợp chặn hành động nhạy cảm trước side effects |
| <code>@PostAuthorize</code> | Sau khi method chạy | Có thể xem returnObject nhưng side effects có thể đã xảy ra |
| <code>@PreFilter</code> | Trước lời gọi, lọc collection đầu vào | Phù hợp tình huống nhất định, cần hiểu mutability |
| <code>@PostFilter</code> | Sau lời gọi, lọc collection trả về | Không thay thế query scope cho tập dữ liệu lớn |
| <code>@Secured</code> | Dựa trên danh sách role/authority | Cần bật hỗ trợ tương ứng, ví dụ <code>securedEnabled=true</code> |
| <code>@RolesAllowed</code> | JSR-250 role-based | Cần cấu hình <code>jsr250Enabled=true</code> và dependency cần thiết |

<code>@EnableMethodSecurity</code> hỗ trợ pre/post annotations theo cấu hình thông dụng; <code>@Secured</code> và JSR-250 phải được bật đúng khi sử dụng. Không suy ra rằng chuyển annotation sang loại khác sẽ tự khắc phục self-invocation: khi enforcement vẫn dựa trên proxy thì inner call vẫn có thể bypass.

**Không dùng @PostAuthorize làm lớp chắn duy nhất cho hành động có tác dụng thay đổi hệ thống.** Một method có thể đã UPDATE database, gửi email hoặc gọi dịch vụ ngoài trước khi post-authorization từ chối. HTTP 403 lúc đó không tự rollback các side effects.

Ví dụ tham chiếu một bean policy:

~~~java
@PreAuthorize("@documentPolicy.canEdit(authentication, #documentId)")
public void editDocument(@P("documentId") Long documentId, String content) {
    // Chỉ vào đây sau khi policy cho phép.
}
~~~

Đây là trích đoạn minh họa, không phải một class chạy độc lập. <code>documentPolicy</code> phải là bean có method canEdit phù hợp, <code>@P</code> thuộc <code>org.springframework.security.access.method.P</code>. Dùng source identity/tenant đáng tin cậy, không tin owner từ request body.

## 11. Self-invocation cũng có thể ảnh hưởng @Transactional và @Async

<code>@Transactional</code> của Spring thường dựa trên proxy-based advice. Nếu một method A gọi <code>this.methodB()</code> với annotation transaction chỉ trên B, lời gọi nội bộ có thể bỏ qua transaction advice dành cho B.

Tương tự <code>@Async</code> thường được áp dụng bằng proxy; <code>this.asyncMethod()</code> có thể không chuyển công việc sang executor như kỳ vọng.

Đáng lưu ý, phương thức vừa có <code>@PreAuthorize</code> vừa có <code>@Transactional</code> hoặc <code>@Async</code> có thể liên quan nhiều interceptor/advice. Đừng phỏng đoán transaction bắt đầu lúc nào chỉ từ thứ tự annotations. Hãy test rằng permission bị từ chối **trước** side effect, và transaction/query giữ đúng dữ liệu khi race xảy ra.

### Async và SecurityContext

<code>SecurityContextHolder</code> mặc định thường gắn với thread. Khi code chạy trên executor thread khác, không mặc định nhận được Authentication của HTTP request. Có thể dùng <code>DelegatingSecurityContextRunnable</code>, <code>DelegatingSecurityContextCallable</code>, executor wrapper thích hợp hoặc chuyển trusted identity rồi xác minh lại quyền tại thời điểm xử lý.

Không dùng <code>MODE_INHERITABLETHREADLOCAL</code> như cách tổng quát cho thread pool vì rủi ro giữ nhầm identity. Không truyền raw token/cookie trong task payload/log. Khi user bị thu hồi quyền trong lúc job vẫn chạy, cần chính sách re-check và cancellation/compensation phù hợp.

### Transaction và TOCTOU

Nếu quyền owner/tenant được kiểm tra lúc t1 nhưng dữ liệu bị thay đổi trước UPDATE tại t2, một câu UPDATE không có điều kiện owner/tenant có thể ghi nhầm đối tượng (time-of-check to time-of-use). Cần transaction isolation/lock, optimistic version hoặc conditional SQL:

~~~sql
UPDATE reports
SET content = :content
WHERE id = :reportId
  AND tenant_id = :trustedTenant
  AND owner_username = :authenticatedUsername
  AND status = 'EDITABLE';
~~~

Các bind values nhạy cảm phải được server xác minh; kiểm tra số dòng đã cập nhật. Code này là SQL minh họa, không phải tệp của dự án demo. Method security bổ sung, nhưng **không thay thế** tính nhất quán ở data layer.

## 12. Một số lối bypass khác và cách phòng tránh

### Dùng new thay vì bean Spring

~~~java
ReportExportService direct = new ReportExportService();
direct.exportRestrictedData(); // Không có Spring proxy, không có advice.
~~~

Đây là đoạn minh họa nguy cơ. Không có ranh giới Spring AOP khi object được tạo thủ công bên ngoài container.

### Gọi private/final/static method

Một private method có annotation không phải một protected service entrypoint. Với CGLIB, final method không thể bị subclass override. Với static method, không có lời gọi qua instance proxy. Đặt policy ở public API method mà caller thực sự gọi qua Spring-managed proxy.

### Tự inject bean của chính mình hoặc AopContext.currentProxy()

Có thể gặp giải pháp tự inject proxy hoặc gọi <code>AopContext.currentProxy()</code> khi exposeProxy được bật. Chúng tạo coupling với Spring AOP, circular dependencies và khó bảo trì; trong hệ thống mới nên **ưu tiên tách protected operation sang bean riêng** hoặc enforce policy tường minh ở public use case.

### Interface và annotation inheritance

Khi dùng JDK dynamic proxy, caller có thể chỉ nhìn thấy interface methods. Với nhiều interface, generic inheritance và annotation đặt trên interface lẫn implementation, cần kiểm tra metadata được Spring Security áp dụng như mong muốn. Tránh annotations mâu thuẫn và test trực tiếp bean proxy.

### Khi có nhiều SecurityFilterChain hoặc nhiều entry point

Method security có thể bảo vệ service dù một message consumer, GraphQL resolver hoặc scheduled job gọi vào — **nếu lời gọi đi qua proxy** và có authentication/policy context phù hợp. Nhưng một HTTP route mới gọi repository trực tiếp hoặc một background job thiếu context vẫn là đường không an toàn. Architecture review phải tìm tất cả lối gọi tới hành động nhạy cảm.

## 13. Method security theo owner/tenant nên thiết kế ra sao?

Authority như <code>report:export</code> chỉ cho biết một quyền tổng quát. Để quyết định có thể xuất một report thuộc tenant nào, policy cần xét tenant membership và resource metadata từ server.

Một ví dụ cấu trúc policy (không phải file Java độc lập trong dự án demo):

~~~java
@Component("reportPolicy")
public class ReportPolicy {
    private final ReportRepository reports;
    private final TenantDirectory tenants;

    public ReportPolicy(
            ReportRepository reports, TenantDirectory tenants) {
        this.reports = reports;
        this.tenants = tenants;
    }

    public boolean canExport(Authentication auth, Long reportId) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }

        boolean allowedAuthority = auth.getAuthorities().stream()
            .anyMatch(a -> "report:export".equals(a.getAuthority()));
        if (!allowedAuthority) {
            return false;
        }

        String trustedTenant = tenants.findTrustedTenant(auth.getName());
        return trustedTenant != null && reports.findById(reportId)
            .map(r -> trustedTenant.equals(r.tenantId()))
            .orElse(false);
    }
}
~~~

<code>ReportRepository</code>, <code>TenantDirectory</code> và domain entity phải được tạo đúng theo hệ thống thực; đây chỉ là trích đoạn diễn giải policy. Không lấy tenantId từ HTTP header tự khai làm quyền. Nếu một user thuộc nhiều tenant, cần kiểm tra membership đối với tenant đã chọn và action cụ thể.

Một service operation:

~~~java
@PreAuthorize("@reportPolicy.canExport(authentication, #reportId)")
public byte[] exportOne(@P("reportId") Long reportId) {
    // Sau khi policy cho phép, truy vấn đúng data scope.
    return new byte[0];
}
~~~

Vẫn phải gọi qua proxy. Nếu service có public workflow gọi <code>this.exportOne()</code>, biểu thức method policy có thể không chạy. Tách operation sang bean khác hoặc bảo vệ outer use case. Query cũng phải scope theo tenant/owner trước pagination/export; không lấy tất cả tài liệu rồi lọc quyền sau trong Java.

## 14. Cần phân biệt proxy với mô hình quyền nghiệp vụ

Một proxy chỉ đảm bảo code interception theo cơ chế Spring AOP. Nó **không tự biết** tài liệu nào thuộc account, tenant nào được phép hay dữ liệu đã bị thu hồi quyền.

Phân chia rõ:
- Authentication xác định người dùng đã được xác minh, authorities có nguồn gốc đáng tin cậy.
- Policy tập trung quy tắc owner/tenant/resource/action, mặc định deny khi thiếu dữ liệu.
- Method-security interceptor bắt buộc gọi policy trước operation qua proxy.
- Service thực thi nghiệp vụ.
- Repository/transaction thực thi data scope và concurrency invariants.
- Controller chỉ nhận HTTP và trả DTO, không copy rule thành hàng chục if/else.

Nếu một lớp data access có public method trả mọi record, method security ở service không ngăn developer khác inject thẳng repository. Kết hợp architecture tests, dependency boundaries và code review để loại bỏ đường bypass.

## 15. Kiểm thử nào là bằng chứng đủ mạnh?

| Loại test | Khẳng định được điều gì? | Giới hạn |
| --- | --- | --- |
| <code>AopUtils.isAopProxy(bean)</code> | Bean hiện là AOP proxy | Không chứng minh inner call được intercept |
| Direct secured method test | Proxy method từ chối user thiếu quyền | Chưa kiểm tra outer workflow |
| Self-invocation demonstration | Outer call có thể bỏ qua inner annotation | Phải sửa code production sau khi nhận diện |
| Cross-bean workflow test | Call đi qua protected proxy | Không thay thế tenant policy |
| MockMvc HTTP test | SecurityFilterChain + method security có tác dụng ở request | Không mô phỏng mọi background caller |
| Policy unit test | Ma trận owner/tenant/role đúng | Không chứng minh proxy wiring |
| Database/transaction test | Policy và update/query nhất quán | Cần dữ liệu/transaction gần production |
| Async/security-context test | Identity đúng qua executor | Không tự chứng minh quyền chưa bị revoke |
| Architecture tests | Không có controller/adapter inject repository bừa | Không thay thế runtime integration tests |

**Test negative rất quan trọng.** Chỉ kiểm thử admin/exporter thành công không phát hiện việc user quyền thấp gọi workflow và vượt qua bảo vệ. Nên có test với user chỉ <code>report:read</code> trên *tất cả public use cases* và trên mọi đường gọi.

<code>@WebMvcTest</code> có thể không khởi tạo mọi security interceptors/bean thực; cần ít nhất một <code>@SpringBootTest</code> hoặc test context tương đương cho method security thực. Đừng mock protected service trong test rồi kết luận annotation hoạt động.

## 16. Các lỗi phổ biến

| Lỗi / triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Có @PreAuthorize nhưng người dùng vẫn gọi được | Self-invocation, chưa bật method security hoặc không dùng proxy | Kiểm tra EnableMethodSecurity, bean, call path |
| AopUtils cho biết bean là proxy nhưng inner vẫn không chặn | Proxy chỉ thấy outer method | Tách protected operation ra bean riêng |
| @Transactional trên inner method không có hiệu lực | this.inner() bỏ qua transaction advice | Gọi qua bean proxy, kiểm tra transaction |
| @Async chạy đồng bộ | Self-invocation bypass async advice | Cross-bean call hoặc async infrastructure đúng |
| Final class không class-proxy được | CGLIB không subclass final class | Thiết kế service proxy-compatible |
| Private @PreAuthorize method | Không phải intercepted public bean API | Bảo vệ public operation |
| new Service() có annotation nhưng không chặn | Không là Spring-managed bean | Inject bean được container quản lý |
| JDK proxy không inject concrete type được | JDK proxy expose interface | Inject interface hoặc điều chỉnh proxy strategy |
| @PostAuthorize dùng cho mutation | Side effect xảy ra trước deny | Pre-authorize và transaction invariants |
| @WithMockUser admin test luôn xanh | Không có negative test | Test reader/cross-tenant/anonymous |
| Web test mock service, mất method interceptor | Slice/mock không giống production | Integration test real bean |
| HTTP authenticated() nhưng export bị lộ | Method policy thiếu/bypass | Enforce tại operation service |
| Async thread không có Authentication | Context chưa propagate | Context wrappers hoặc kiểm tra lại quyền |
| Một manager được xem tenant khác | Chỉ kiểm tra role | Tenant membership và query scope |
| Policy check rồi UPDATE ghi sai record | TOCTOU | Conditional update, transaction/lock |
| Catch AccessDeniedException rồi trả dữ liệu mặc định | Swallow denial | Fail closed và status phù hợp |

## 17. Checklist trước khi triển khai production

1. Đã bật <code>@EnableMethodSecurity</code> và test chứng minh <code>@PreAuthorize</code> thực sự được interceptor áp dụng.
2. Các protected operations là public methods trên Spring-managed services có đường gọi qua proxy.
3. Không dựa vào <code>this.securedMethod()</code> như enforcement. Mọi self-invocation nhạy cảm phải được sửa hoặc có policy check tường minh.
4. Chọn proxy strategy phù hợp interface/classes; tránh final/private/static làm điểm bắt buộc policy.
5. Controller/batch/message/GraphQL không truy cập repository nhạy cảm trực tiếp để bỏ qua enforced service.
6. Chạy cả positive lẫn negative tests, đặc biệt user ít quyền gọi outer workflow.
7. HTTP authentication, CSRF, CORS, session policy, authorization URL và method policy đều được xem xét.
8. Policy theo resource dùng identity/tenant từ nguồn đã được xác minh; deny nếu resource/membership không hợp lệ.
9. Kiểm tra transaction, race, optimistic version và query scope khi mutation hoặc export có dữ liệu thật.
10. Khi có @Async, kiểm soát context propagation, lifecycle, cancellation và thời điểm kiểm tra lại quyền.
11. Không dùng @PostAuthorize như lớp bảo vệ trước side effect.
12. Khi thêm public service method, HTTP route hoặc scheduler, rà soát lại enforcement/call paths.
13. Audit deny/allow an toàn, không log credentials, session IDs hay dữ liệu chưa có quyền đọc.
14. Sau nâng cấp Spring Boot/Security hoặc thay proxy settings, chạy lại method-security integration tests.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao <code>this.exportRestrictedData()</code> có thể bỏ qua <code>@PreAuthorize</code>?  
**Đáp án:** Nó gọi method trên target object, không gọi lại qua Spring AOP proxy. Interceptor của inner method không được kích hoạt.

**Câu 2.** Bật <code>@EnableMethodSecurity(proxyTargetClass=true)</code> có tự sửa self-invocation không?  
**Đáp án:** Không. CGLIB thay chiến lược proxy, nhưng inner method call vẫn trên target và có thể bypass interceptor.

**Câu 3.** Tại sao bean là AOP proxy chưa đủ chứng minh mọi method đều an toàn?  
**Đáp án:** Proxy chỉ kiểm tra những lời gọi đi qua nó. Một đường inner call, new object hoặc direct data access có thể đi vòng.

**Câu 4.** Cross-bean invocation giúp gì?  
**Đáp án:** Workflow gọi protected operation qua một Spring bean được inject, vì vậy proxy/interceptor kiểm tra authority trước khi target chạy.

**Câu 5.** Vì sao @PostAuthorize không phù hợp làm quyền duy nhất trước khi DELETE/UPDATE?  
**Đáp án:** Vì nó đánh giá sau khi method chạy, có thể đã tạo side effects mà 403 không tự hoàn tác.

**Câu 6.** HTTP cho phép <code>authenticated()</code> nhưng method yêu cầu <code>report:export</code>. Reader có <code>report:read</code> nhận gì?  
**Đáp án:** Reader qua lớp authentication thô nhưng bị method security từ chối, thông thường HTTP 403.

**Câu 7.** Có nên tin <code>@WithMockUser</code> trong một slice test để kết luận production đã bật proxy interception chưa?  
**Đáp án:** Không. Cần test với real Spring bean và application context có method-security infrastructure.

**Câu 8.** Một job @Async có được mặc nhiên dùng Authentication từ request thread không?  
**Đáp án:** Không. Cần cơ chế truyền context hoặc kiểm tra lại identity/quyền.

**Câu 9.** Có authority export thì có chắc được export mọi tenant không?  
**Đáp án:** Không. Phải xác minh membership/ownership và dữ liệu thuộc phạm vi được phép.

**Ghi nhớ:** Spring Security method security ở chế độ proxy là **interceptor trên lời gọi qua Spring proxy**. Thiết kế các protected operations ở những Spring bean được gọi thực sự qua proxy; không mặc định self-invocation được bảo vệ; dùng policy/service/data layer và integration tests để bảo đảm không có đường gọi nào đến hành động nhạy cảm mà thiếu kiểm tra quyền.
