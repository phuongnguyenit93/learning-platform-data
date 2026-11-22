# Kiểm thử lời gọi qua proxy so với lời gọi nội bộ trong cùng đối tượng

## 1. Bài toán: cùng một phương thức, hai đường gọi khác nhau

Trong ứng dụng **Spring Security Servlet** sử dụng **method security**, bạn có thể viết một phương thức:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readReport() {
    return "REPORT-42";
}
~~~

Một lời gọi **từ bean khác đi qua Spring proxy** thường kích hoạt lời khuyên bảo mật (security advice) do **@PreAuthorize** tạo ra. Caller không có authority **report:read** sẽ bị từ chối trước khi thân phương thức chạy.

Nhưng nếu một phương thức **khác trong cùng đối tượng** gọi **this.readReport()**, lời gọi nội bộ đó đi thẳng đến target object thay vì quay lại Spring proxy. Trong cơ chế **proxy-based method security**, advice trên **readReport()** có thể không chạy. Đây là bẫy **self-invocation**.

~~~text
Đường A — đi qua Spring proxy:

Controller / Facade
       │
       ▼
Spring AOP proxy của ReportService
       │
       ├── @PreAuthorize("hasAuthority('report:read')")
       │     ├── được phép → readReport()
       │     └── thiếu quyền → AccessDeniedException
       ▼
Target ReportService.readReport()


Đường B — lời gọi nội bộ:

Controller
       │
       ▼
Spring AOP proxy của ReportService
       │  (outerMethod không có advice)
       ▼
Target ReportService.outerMethod()
       │
       └── this.readReport()
               │
               └── gọi trực tiếp trên target, không quay qua proxy
                   ⇒ @PreAuthorize trên readReport() không được đánh giá
~~~

Chủ đề không phải “Spring Security bỏ qua @PreAuthorize ngẫu nhiên”. **Đường đi của lời gọi** quyết định method interception có xảy ra hay không.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **proxy invocation** và **self-invocation** trong Spring AOP/method security.
2. Cấu hình **@EnableMethodSecurity**, **@PreAuthorize** và một security boundary đúng.
3. Viết **unit/integration test có Spring context** để kiểm tra method security với principal đủ quyền, thiếu quyền và lời gọi nội bộ.
4. Dùng **MockMvc** xác minh hệ quả HTTP của từng đường gọi; hiểu rõ **401** và **403**.
5. Phát hiện **false positive** khi test bằng cách tự **new** service, mock mất proxy, hoặc chỉ kiểm thử một controller path.
6. Refactor sang **bean khác** hoặc bảo vệ **entry method công khai**, không phụ thuộc vào một lời gọi this() bị bỏ qua advice.

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC (Servlet)**. Không áp dụng nguyên cấu hình SecurityFilterChain cho WebFlux SecurityWebFilterChain.

## 2. Cơ chế proxy-based method security

### 2.1. Spring method security không chỉ là annotation

Khi bật **@EnableMethodSecurity** trong ứng dụng Spring, framework tạo các interceptor/advisor cho những annotation hỗ trợ như **@PreAuthorize** và **@PostAuthorize**. Ở chế độ proxy thông dụng:

- Bean đích được truy cập qua một **Spring AOP proxy**.
- Lời gọi có thể được interceptor bao quanh để kiểm tra **Authentication** và quyết định authorization.
- **@PreAuthorize** được đánh giá **trước** thân phương thức.
- Nếu denied, advice ném **AccessDeniedException** (hoặc lỗi bảo mật tương ứng), và thân phương thức không thực thi.
- **@PostAuthorize** kiểm tra sau khi thân phương thức chạy; có thể ngăn trả kết quả cho caller nhưng **không hoàn tác side effect** đã xảy ra. Nó cũng chịu cùng vấn đề về ranh giới proxy.

Không có **@EnableMethodSecurity**, việc chỉ đặt **@PreAuthorize** trên phương thức chưa đảm bảo interceptor chạy. Trong Spring Security 6, **@EnableMethodSecurity** là hướng cấu hình hiện đại; đừng nhầm với cấu hình cũ **@EnableGlobalMethodSecurity**.

Một lời gọi từ Java thông thường **không tự biến thành** lời gọi có method-security advice chỉ vì class nằm trong ứng dụng Spring. Muốn interception, caller phải lấy **bean được Spring quản lý** và đi qua **proxy** thích hợp.

### 2.2. JDK dynamic proxy và class-based proxy

Spring AOP có thể dùng:

- **JDK dynamic proxy**: thường áp dụng khi proxy qua interface. Caller nên làm việc qua interface phù hợp.
- **Class-based proxy (CGLIB)**: tạo subclass proxy của class đích; thường cần cho bean không có interface.

Dù là loại nào, **self-invocation** vẫn không tự đi qua interceptor: khi execution đã vào target object, **this.someMethod()** không gửi một request mới tới proxy.

Một số method/class không thể được proxy theo cách thông thường. Ví dụ **final method** không được subclass-based proxy override/intercept; **private method** không phải public proxy entry point. Đừng dùng annotation trên private/final method rồi giả định method security bảo vệ nó. Hành vi với method không public phụ thuộc proxy type và phiên bản Spring; hãy kiểm thử trên đúng cấu hình thực tế.

**Proxy configuration không biến self-invocation thành intercepted invocation.** Chọn class-based proxy thay vì JDK proxy không sửa bản chất của lời gọi **this.readReport()**.

### 2.3. Quyền và đường gọi: bảng đối chiếu

Giả sử **readReport()** yêu cầu authority **report:read**, còn **readFromInside()** không có annotation:

| Caller / đường gọi | Principal có report:read? | Kết quả |
| --- | --- | --- |
| Bean khác gọi **reportService.readReport()** qua proxy | Có | Được vào method, nhận **REPORT-42** |
| Bean khác gọi **reportService.readReport()** qua proxy | Không | **AccessDeniedException**; body method không chạy |
| Gọi **reportService.readFromInside()** qua proxy rồi nó tự gọi **this.readReport()** | Có | Nhận **REPORT-42** |
| Gọi **reportService.readFromInside()** qua proxy rồi nó tự gọi **this.readReport()** | Không | **Vẫn có thể nhận REPORT-42**: annotation ở inner method không được intercept |
| Caller dùng **new ReportService()** thay vì lấy bean Spring | Không | Không có Spring proxy; annotation trên class đơn thuần không chặn |
| Caller dùng bean đã bị thay bằng mock thuần | Bất kỳ | Mock có thể không chứa interceptor thực; kết quả không chứng minh method security |

Dòng thứ tư là lỗi an ninh cần có **negative test**. Một test chỉ chứng minh người dùng đủ quyền đọc được báo cáo là không đủ.

## 3. Ví dụ Spring Boot có đường proxy và đường self-invocation

Ví dụ triển khai **hai HTTP endpoint GET chỉ dành cho môi trường demo**. Cả hai đều yêu cầu người dùng đã được xác thực ở HTTP layer; chỉ **/demo/proxy** đi qua annotation cần authority **report:read**. **/demo/self** cố tình mô phỏng anti-pattern để test thấy chỗ bảo vệ bị bỏ qua. Không đưa endpoint thiếu kiểm soát này lên production.

### 3.1. Dependency và cấu trúc

Dự án Spring Boot 3.x dùng Java 17+ và Gradle wrapper. Trong **build.gradle**, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các tệp Java minh họa:

~~~text
src/
├── main/java/com/example/methodproxy/
│   ├── MethodProxyApplication.java
│   ├── ReportService.java
│   ├── ReportFacade.java
│   └── DemoController.java
└── test/java/com/example/methodproxy/
    └── ProxyBoundaryTest.java
~~~

Cần tạo package **com.example.methodproxy** đúng như tên trong source. **Spring Boot starter-security** cung cấp các thư viện Spring Security cần thiết và cơ chế Spring AOP phục vụ method-security proxy.

### 3.2. Application và security configuration

Tệp **src/main/java/com/example/methodproxy/MethodProxyApplication.java**:

~~~java
package com.example.methodproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableMethodSecurity
public class MethodProxyApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodProxyApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-password"))
                        .authorities("report:read")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-password"))
                        .authorities("report:edit")
                        .build());
    }
}
~~~

Giải thích:

- **@EnableMethodSecurity** bật phương thức kiểm tra authorization bằng annotation; ví dụ này sử dụng **@PreAuthorize**.
- **SecurityFilterChain** đặt điều kiện tối thiểu **authenticated()** cho mọi HTTP route. Đây là **web authorization**, tách biệt method authorization bên trong service.
- **alice** có **report:read** nên được phép đọc báo cáo khi lời gọi qua proxy.
- **bob** chỉ có **report:edit**, vì vậy đã đăng nhập nhưng **không được phép đọc báo cáo** theo chính sách tại method.
- **HTTP Basic** và hai tài khoản demo chỉ nhằm tái hiện phép thử. Không hard-code mật khẩu demo trong production và không truyền Basic credentials qua HTTP không có TLS ngoài môi trường local.

Điểm quan trọng: **web chain .authenticated()** sẽ cho phép cả alice và bob đi tới controller; việc phân quyền chi tiết cho báo cáo được kỳ vọng diễn ra ở method-security proxy.

### 3.3. Service có một method được bảo vệ và một self-invocation

Tệp **src/main/java/com/example/methodproxy/ReportService.java**:

~~~java
package com.example.methodproxy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "REPORT-42";
    }

    public String readFromInside() {
        // Cố ý là anti-pattern: this là target object, KHÔNG phải proxy.
        return this.readReport();
    }
}
~~~

**readReport()** là method public được Spring advice bảo vệ khi gọi **thông qua proxy**. **readFromInside()** cũng là public nên controller có thể gọi nó qua bean proxy, nhưng bản thân nó **không** có annotation bắt buộc report:read. Khi execution tới **this.readReport()**, interceptor trên readReport() không được gọi.

Đây là thiết kế **cố tình sai** để viết regression test chứng minh rủi ro. Một ứng dụng thật không nên để entry point không được bảo vệ có đường đi đến dữ liệu nhạy cảm theo cách này.

### 3.4. Facade gọi sang bean khác để đi qua proxy

Tệp **src/main/java/com/example/methodproxy/ReportFacade.java**:

~~~java
package com.example.methodproxy;

import org.springframework.stereotype.Service;

@Service
public class ReportFacade {

    private final ReportService reportService;

    public ReportFacade(ReportService reportService) {
        this.reportService = reportService;
    }

    public String readThroughProxy() {
        // Bean khác gọi public method trên bean được Spring inject.
        return reportService.readReport();
    }
}
~~~

**ReportFacade** nhận một bean **ReportService** qua constructor injection. Trong cấu hình method security chuẩn, tham chiếu injected là **proxy** hoặc đối tượng đại diện được framework trang bị advice. Khi facade gọi **reportService.readReport()**, policy được đánh giá.

Refactor thành **hai bean riêng** là cách giải quyết thông dụng nhất cho self-invocation, vì ranh giới interception rõ ràng, không cần tìm proxy hiện tại từ ThreadLocal hay tự inject chính bean vào nó.

### 3.5. Controller để so sánh bằng HTTP

Tệp **src/main/java/com/example/methodproxy/DemoController.java**:

~~~java
package com.example.methodproxy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ReportService reportService;
    private final ReportFacade reportFacade;

    public DemoController(
            ReportService reportService,
            ReportFacade reportFacade) {
        this.reportService = reportService;
        this.reportFacade = reportFacade;
    }

    @GetMapping("/demo/proxy")
    public String throughProxy() {
        return reportFacade.readThroughProxy();
    }

    @GetMapping("/demo/self")
    public String throughSelfInvocation() {
        // Dùng để chứng minh lỗi, KHÔNG giữ endpoint này ở production.
        return reportService.readFromInside();
    }
}
~~~

**Controller không tự đặt quyền report:read lên cả hai endpoint**, bởi mục đích demo là phơi bày sự khác nhau giữa proxy invocation và self-invocation. Trong thiết kế production, policy nhạy cảm nên nằm ở entry boundary không thể đi vòng và được kiểm tra thêm tại service.

## 4. Kết quả chạy dự kiến và giải thích từng request

Chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Với HTTP Basic trên máy local, thử **alice**:

~~~bash
curl -i -u alice:alice-demo-password \
  'http://localhost:8080/demo/proxy'
~~~

Kết quả dự kiến:

~~~http
HTTP/1.1 200

REPORT-42
~~~

Header HTTP thực tế (Content-Type, Content-Length, cache, security headers) có thể khác, nhưng **200** và nội dung **REPORT-42** là kết quả nghiệp vụ kỳ vọng.

Thử **bob** qua proxy:

~~~bash
curl -i -u bob:bob-demo-password \
  'http://localhost:8080/demo/proxy'
~~~

Kết quả dự kiến **HTTP 403 Forbidden** vì bob đã xác thực nhưng thiếu **report:read**. Body response có thể là thông báo lỗi do Spring Boot render tùy cấu hình; không gán body cố định cho lỗi này.

Sau đó thử **bob** bằng đường self-invocation:

~~~bash
curl -i -u bob:bob-demo-password \
  'http://localhost:8080/demo/self'
~~~

Trong demo, dự kiến nhận **HTTP 200** và **REPORT-42**. Đây chính là chứng cứ rằng **chỉ có @PreAuthorize trên inner method là không đủ** khi lời gọi có thể đi từ cùng target object.

Cuối cùng thử không truyền credential:

~~~bash
curl -i 'http://localhost:8080/demo/proxy'
~~~

Kỳ vọng **HTTP 401** do HTTP Basic yêu cầu authentication trước khi controller được xử lý.

### Vì sao một đường 403 còn đường kia 200?

Không phải bob có quyền đọc tài liệu khi đi qua đường thứ hai. Bob **vẫn thiếu report:read**. Vấn đề là đường thứ hai **không chạy kiểm tra report:read**. Vì vậy một test mong mọi đường truy cập đều 403 phải được xem là tiêu chuẩn bảo mật. Test minh họa chứng minh bug hiện hữu, không phải công nhận 200 là hành vi sản phẩm mong muốn.

## 5. Integration test chứng minh proxy boundary

Viết test sử dụng **@SpringBootTest** để Spring khởi tạo bean và method-security proxy thật. Dùng **@WithMockUser** của spring-security-test để đặt Authentication với authority xác định cho lời gọi service. Đây là **kiểm thử authorization/method interception**, không phải kiểm thử xác thực mật khẩu thật.

Tệp **src/test/java/com/example/methodproxy/ProxyBoundaryTest.java**:

~~~java
package com.example.methodproxy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProxyBoundaryTest {

    @Autowired
    ReportService reportService;

    @Autowired
    ReportFacade facade;

    @Autowired
    MockMvc mvc;

    @Test
    void serviceBeanIsProxied() {
        assertThat(AopUtils.isAopProxy(reportService)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void externalCallWithAuthorityPasses() {
        assertThat(reportService.readReport()).isEqualTo("REPORT-42");
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:edit")
    void externalCallWithoutAuthorityIsDenied() {
        assertThatThrownBy(() -> reportService.readReport())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:edit")
    void callFromAnotherBeanStillUsesProxy() {
        assertThatThrownBy(() -> facade.readThroughProxy())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:edit")
    void selfInvocationDemonstratesBypass() {
        // Phơi bày BUG: entry method không có advice, inner call là this.
        assertThat(reportService.readFromInside()).isEqualTo("REPORT-42");
    }

    @Test
    void httpProxyRouteRejectsMissingAuthority() throws Exception {
        mvc.perform(get("/demo/proxy")
                        .with(user("bob").authorities(
                                new SimpleGrantedAuthority("report:edit"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void httpProxyRouteAcceptsRequiredAuthority() throws Exception {
        mvc.perform(get("/demo/proxy")
                        .with(user("alice").authorities(
                                new SimpleGrantedAuthority("report:read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT-42"));
    }

    @Test
    void httpSelfRouteExposesTheBypass() throws Exception {
        // Đây là test phát hiện vấn đề, KHÔNG phải mong muốn production.
        mvc.perform(get("/demo/self")
                        .with(user("bob").authorities(
                                new SimpleGrantedAuthority("report:edit"))))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT-42"));
    }

    @Test
    void httpRouteWithoutAuthenticationIsUnauthorized() throws Exception {
        mvc.perform(get("/demo/proxy"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy trong thư mục gốc có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.methodproxy.ProxyBoundaryTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.methodproxy.ProxyBoundaryTest
~~~

**Kết quả kỳ vọng:** 9 test hoàn thành nếu ví dụ được lắp vào dự án Boot/Security đúng phiên bản và không có cấu hình khác can thiệp. Đây là **kết quả dự đoán từ mã mẫu**, không phải kết quả runtime đã xác nhận.

### Bốn loại kết luận khác nhau từ bộ test

| Nhóm test | Chứng minh được | Không chứng minh được |
| --- | --- | --- |
| **AopUtils.isAopProxy(...)** | Service injected là AOP proxy | Mỗi method cụ thể đều có security advice |
| **@WithMockUser** gọi service | Method-security interceptor có thể cho phép/từ chối theo Authentication | Password, OAuth2 token, session hay HTTP filter thật đã hoạt động |
| **MockMvc + user(...)** | Web security và method security phối hợp trong HTTP request giả lập | Real Basic credentials đã được encoder xác minh, proxy/gateway ngoài app đúng |
| **HTTP bằng curl và Basic thực** | Tái hiện endpoint và Basic authentication trong ứng dụng chạy thật | An toàn production, IAM/IdP và mọi đường vào khác đều đã được kiểm thử |

**Không lạm dụng test chỉ có @WithMockUser**. Nó đặc biệt hữu ích cho authorization, nhưng SecurityContext là do test tạo ra. Với xác thực mật khẩu hoặc OAuth2/JWT, cần thêm test xác thực thật tương ứng.

### Mục đích của test “bypass vẫn trả 200”

Trong bài học, test **selfInvocationDemonstratesBypass** và **httpSelfRouteExposesTheBypass** có expected result đúng với lỗi đang được mô phỏng. **Không nên giữ các assertion cho phép bypass như tiêu chí chấp nhận production**.

Khi refactor, hãy đổi thành regression test yêu cầu người thiếu quyền **bị từ chối** ở **mọi đường**; đó mới là tiêu chí nghiệm thu an toàn.

## 6. Refactor để không còn self-invocation bypass

### Giải pháp A — Chuyển method có kiểm tra quyền sang bean khác (ưu tiên)

Thay vì trong cùng một bean:

~~~java
@Service
class InsecureReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "REPORT-42";
    }

    public String exportReport() {
        return this.readReport(); // advice bị bỏ qua
    }
}
~~~

tách **method bảo vệ** và **method điều phối** thành hai bean. Với tệp **ReportService.java** giữ nguyên annotation trên readReport(), tệp **ReportFacade.java** đã thực hiện cấu trúc đúng:

~~~java
public String readThroughProxy() {
    return reportService.readReport();
}
~~~

Bởi **ReportFacade** gọi sang **ReportService bean được inject**, lời gọi đi qua method-security proxy. Khi caller thiếu report:read, interceptor từ chối trước khi thân readReport() chạy.

**Đừng tự new ReportService**, và đừng tháo bean khỏi Spring context để giảm thời gian test: làm vậy mất proxy.

### Giải pháp B — Bảo vệ ngay entry method công khai

Nếu nhiều đường gọi thực sự cần cùng policy, có thể đưa guard tới entry method:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readFromInside() {
    return this.readReport();
}
~~~

Khi một bean bên ngoài gọi **reportService.readFromInside()** qua proxy, **@PreAuthorize trên readFromInside()** sẽ được đánh giá. Điều này có thể đủ nếu toàn bộ luồng gọi chỉ có entry method đó. Tuy nhiên:

- Lời gọi **this.readFromInside()** từ một method khác trong cùng target lại có nguy cơ bỏ qua advice trên entry.
- Nếu một entry point khác gọi trực tiếp business logic không được bảo vệ, policy vẫn có thể bị bỏ qua.
- Nếu policy khác nhau giữa methods, annotation trên entry chưa chắc tương đương chính sách chi tiết bên trong.
- Chỉ đặt guard trên controller path không ngăn lời gọi từ scheduler, message consumer hoặc service khác tới method nhạy cảm; cần policy ở một service boundary đáng tin.

Vì thế, thiết kế thành **bean bảo vệ được các caller khác nhau gọi qua proxy** thường dễ audit/test hơn.

### Giải pháp C — AspectJ weaving: kiến trúc khác, không phải một cờ đơn giản

AOP **AspectJ weaving** có thể áp advice theo các join point mà proxy-based AOP không chặn được, tùy cấu hình weaving/annotation/mode. Nhưng nó cần dependencies, compiler hoặc load-time weaving và chiến lược triển khai/test phù hợp. **Không khẳng định chỉ đổi một cờ cấu hình @EnableMethodSecurity là self-invocation tự được bảo vệ**.

Trong phần lớn dịch vụ Spring Boot thông thường, tách bean hoặc đưa chính sách ở entry public method là giải pháp dễ hiểu và ít rủi ro hơn.

### Không ưu tiên AopContext.currentProxy() hay tự inject chính bean

Có thể thấy các workaround như **AopContext.currentProxy()**, self-injection hoặc ApplicationContext.getBean(...) để gọi ngược qua proxy. Những cách này có thể phụ thuộc **exposeProxy**, proxy type, vòng phụ thuộc hoặc cấu trúc test, khiến code khó bảo trì. Với nghiệp vụ bảo mật, **refactor ranh giới service rõ ràng** thường tốt hơn.

## 7. Viết regression test sau khi sửa thiết kế

Khi đã loại bỏ đường self-invocation không bảo vệ, một ma trận tối thiểu nên là:

| Tình huống | Tiêu chí production |
| --- | --- |
| Alice có **report:read** gọi trực tiếp service proxy | Được phép |
| Bob không có **report:read** gọi trực tiếp service proxy | Bị từ chối |
| Bob đi qua facade/service điều phối | Bị từ chối |
| Bob đi qua controller HTTP | **403** |
| Anonymous gọi HTTP endpoint | **401** đối với cấu hình Basic trong demo |
| Bob đi qua mọi method nội bộ/đường thay thế | Không thể đọc report |
| Task scheduler hoặc message handler gọi service bảo vệ | Không vô tình được quyền theo Authentication cũ hoặc mặc định |
| Dữ liệu thuộc user khác dù cùng role | Vẫn bị policy ownership/tenant từ chối |
| Body method có side effect | Không chạy side effect khi bị denied ở @PreAuthorize |
| Method có @PostAuthorize | Không rò kết quả; kiểm tra side effect đã xảy ra trước khi advice hậu kiểm |

### Chứng minh method thực sự KHÔNG chạy khi bị deny

Chỉ nhìn exception đôi khi chưa đủ nếu phương thức có tác dụng phụ. Một cách test là tạo một **mock repository** ở phía dưới service và xác minh không gọi **save/update** khi điều kiện @PreAuthorize thất bại. Tuy nhiên cần đảm bảo service **vẫn là bean được Spring AOP proxy**; không mock hoặc thay toàn bộ service rồi kết luận interceptor đã được kiểm thử.

Ví dụ về ý tưởng kiểm thử:

~~~text
Given: Authentication có role USER nhưng không có report:write
When:  gọi qua proxy tới method @PreAuthorize("hasAuthority('report:write')")
Then:  AccessDeniedException
And:   repository.save(...) chưa từng được gọi

Đối chứng:
Given: caller có report:write
When:  gọi qua proxy
Then:  method chạy; repository được gọi đúng như nghiệp vụ
~~~

Bài này dùng một chuỗi literal **REPORT-42** để minh họa nên không cần repository hoặc cơ sở dữ liệu. Với dữ liệu thật, hãy kiểm tra cả authorization theo **resource ownership**, không chỉ một authority chung.

## 8. Những sai lầm trong kiểm thử method security

### 8.1. Tạo service bằng new

~~~java
ReportService service = new ReportService();
service.readReport();  // Không đi qua Spring AOP proxy.
~~~

Đoạn trên **không phải test method security**, chỉ là test logic Java của target object. Nếu mục tiêu là kiểm thử interceptor, phải sử dụng bean từ Spring Test context hoặc thiết lập proxy có thật.

### 8.2. Gọi chính method trong cùng class test thông qua this

Ví dụ một method của service trực tiếp gọi method được annotate trong cùng object, khiến **@PreAuthorize** trên inner method không bị chặn. Tránh nghĩ rằng chỉ cần @WithMockUser là khôi phục được advice: test user cung cấp Authentication, **không thay đổi đường đi qua proxy**.

### 8.3. Mock service đã có annotation

Nếu dùng Mockito mock hoặc một bean replacement thay thế toàn bộ service dưới test, lời gọi có thể chỉ chạy trên mock. Test trả chuỗi/exception được stub không chứng minh **@PreAuthorize** thật đã được áp dụng. Hãy giữ bean thực ở ranh giới proxy cần kiểm thử và chỉ mock những dependency thấp hơn như repository hoặc gateway.

### 8.4. Chỉ test người đủ quyền

Nếu chỉ có:

~~~java
@WithMockUser(authorities = "report:read")
@Test
void happyPath() {
    assertThat(service.readReport()).isEqualTo("REPORT-42");
}
~~~

thì test có thể **pass kể cả khi proxy chưa được kích hoạt**, vì method vẫn trả REPORT-42. Muốn bắt lỗi “chưa bật @EnableMethodSecurity”, “self-invocation bypass” hoặc “test đang gọi target trực tiếp”, phải có **negative test** với principal không đủ quyền. Chính negative test mới chỉ ra sự khác biệt giữa proxy có advice và Java method thông thường.

### 8.5. Nhầm 401/403 trong lời gọi service và HTTP

**AccessDeniedException** là một exception Java khi gọi method trong test service. **401/403 là HTTP status** do web security exception handling quyết định, không phải giá trị trả về của một lời gọi Java trực tiếp.

- Lời gọi method bảo vệ với user đã xác thực nhưng thiếu quyền → trong demo ném **AccessDeniedException**.
- HTTP request đã xác thực nhưng method bị deny → web layer dịch thành **403**.
- HTTP request không có Basic credentials → filter chặn trước controller, **401**.
- Nếu có custom AuthenticationEntryPoint/AccessDeniedHandler, status/response có thể khác; khẳng định status trong test ở đúng cấu hình đang triển khai.

### 8.6. Chỉ dựa vào isAopProxy()

**AopUtils.isAopProxy(reportService)** cho biết bean injected là AOP proxy, nhưng **không đảm bảo** advice cụ thể trên method đã được đăng ký đúng và thực sự được gọi. Một bean có thể được proxy vì transaction, cache hoặc advice khác. Phải có test **denied khi gọi từ bên ngoài** và **allowed khi đủ quyền**, không dừng ở phép kiểm tra metadata.

### 8.7. Đặt @PreAuthorize trên private/final method

Proxy interception cần điều kiện method phù hợp. Với class-based proxy, **final** chặn override; **private** không trở thành proxy entry point. Đừng giả định annotation chạy nếu không có khả năng intercept. Xây test từ caller thực tế và rà lại class design.

### 8.8. Không test tất cả đường vào cùng nghiệp vụ

Một service có thể được gọi từ controller REST, MVC action, scheduled job, event listener hoặc message consumer. Tất cả đường có khả năng chạm dữ liệu nhạy cảm đều cần boundary kiểm soát đáng tin. Chỉ test một controller path và thấy 403 không đủ nếu method nội bộ khác có thể bypass.

## 9. Phân biệt method security với các proxy annotation khác

Tuy cùng dùng cơ chế AOP proxy, những annotation sau có mục đích khác nhau:

| Annotation | Ý nghĩa | Rủi ro self-invocation |
| --- | --- | --- |
| **@PreAuthorize** | Chặn trước khi method chạy nếu không đủ quyền | Bỏ qua guard ở inner method |
| **@PostAuthorize** | Kiểm tra điều kiện sau khi method chạy | Bỏ qua kiểm tra output; side effect có thể đã xảy ra |
| **@Transactional** | Tạo transaction boundary | Inner method có thể không mở transaction mới như kỳ vọng |
| **@Async** | Chuyển thực thi sang executor | Inner method có thể chạy đồng bộ trong caller thread |
| **@Cacheable** | Chạy logic cache trước/sau method | Inner method có thể bỏ qua cache interceptor |

Những annotation này có các tính năng và ngoại lệ riêng theo cấu hình, nhưng **lời gọi nội bộ bypass proxy** là mẫu lỗi chung với Spring AOP proxy. Đừng vì test transaction hay async vẫn chạy mà suy ra method security chắc chắn đúng; hãy test từng loại advice.

## 10. Checklist cho code review và triển khai

- **Method security được bật chưa?** Có @EnableMethodSecurity trong Spring context thực tế?
- **Bean đúng proxy chưa?** Caller nhận bean qua dependency injection, không tự new?
- **Method được gọi qua đâu?** Trace đường controller → facade → service, đặc biệt các lời gọi **this.** trong cùng class.
- **Annotation ở đâu?** Policy đặt trên một boundary mà mọi caller phải đi qua, không chỉ trên helper nội bộ.
- **Method có thể được intercept không?** Kiểm tra private/final/class proxy type/visibility.
- **Policy đầy đủ chưa?** Authentication, authority, quyền đối tượng/tenant, trạng thái tài khoản và điều kiện nghiệp vụ.
- **Negative tests có chưa?** Người thiếu quyền bị deny khi gọi method bean, facade và HTTP; self-invocation không được bỏ qua.
- **Có test sai cách không?** Tránh new, bean mock thay service, method gọi nội bộ ngoài proxy, test chỉ có authorized happy path.
- **HTTP status rõ chưa?** Phân biệt lỗi Java AccessDeniedException với HTTP 401/403 và custom handlers.
- **Side effect được bảo vệ chưa?** @PreAuthorize deny trước khi ghi dữ liệu; @PostAuthorize không ngăn side effect đã xảy ra.
- **Các entry khác đã được phủ chưa?** Scheduler, consumer, integration hooks, admin APIs và shared service.
- **Refactor bền vững chưa?** Ưu tiên tách bean hoặc bảo vệ entry method; không lạm dụng self-injection/AopContext.
- **Kiểm thử trên deployment thật đã có chưa?** Proxy mode, Spring Security version, cấu hình method-security và servlet security chain phù hợp.

**Kết luận:** Trong Spring Security Servlet với method security dựa trên proxy, **annotation chỉ được thực thi khi đường gọi đi qua interceptor thích hợp**. Lời gọi **this.method()** trong cùng target object không tự đi qua proxy, nên có thể vượt qua **@PreAuthorize** đặt ở inner method. Hãy chứng minh điều đó bằng **test thiếu quyền**, kiểm tra cả lời gọi service và HTTP, rồi refactor để mọi đường truy cập nghiệp vụ nhạy cảm đều đi qua ranh giới authorization bắt buộc.
