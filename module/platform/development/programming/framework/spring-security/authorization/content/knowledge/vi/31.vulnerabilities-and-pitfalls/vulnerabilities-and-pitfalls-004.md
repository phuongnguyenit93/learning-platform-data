# Thiếu @EnableMethodSecurity hoặc gọi phương thức không qua proxy

## 1. Vấn đề bảo mật cần nhận diện

Trong Spring Security, đặt **@PreAuthorize**, **@PostAuthorize** hay một annotation bảo vệ trên phương thức **chưa đủ để bảo đảm mọi lệnh gọi đều được kiểm quyền**. Hai sai sót quan trọng trong cơ chế *method security* là:

1. **Chưa kích hoạt method security:** project có Spring Security và các annotation trên service nhưng thiếu **@EnableMethodSecurity** trong application context. Khi đó annotation **@PreAuthorize** có thể chỉ là metadata, không có interceptor áp dụng.
2. **Lệnh gọi không đi qua Spring AOP proxy:** method security đã bật nhưng code tự gọi một phương thức có annotation trên cùng đối tượng (**self-invocation**) hoặc gọi một object không được Spring quản lý; interceptor không xuất hiện trong đường gọi.

Hậu quả có thể là một người dùng đã xác thực nhưng không đủ quyền vẫn đọc báo cáo, duyệt lệnh, cập nhật số dư hoặc thực hiện một thao tác đáng lẽ chỉ quản trị viên được làm. Lỗi này thuộc nhóm **broken authorization**, không nhất thiết biểu hiện bằng lỗi biên dịch, exception hay log.

Mục tiêu của bài: hiểu khi nào **@PreAuthorize** thật sự chạy, tái hiện cả hai nguyên nhân, chuyển lời gọi qua bean được proxy, và viết regression test khiến ứng dụng **báo đỏ** nếu method security lại bị vô hiệu.

> Ví dụ tập trung vào Spring Boot 3.3.x, Spring Security 6.x, Java 17+ và mô hình Spring MVC thông dụng. Chỉ tái hiện lỗ hổng bằng tài khoản và dữ liệu do bạn kiểm soát trong môi trường học/test.

## 2. Vì sao security ở request chưa thay thế được security ở service?

Một ứng dụng có thể có cấu hình:

~~~java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

Rule này yêu cầu người gọi phải đăng nhập, nhưng **không tự áp đặt** quy tắc rằng chỉ role ADMIN mới được gọi **ReportReader.readSecret(...)**. Nếu controller dành cho mọi user đã đăng nhập gọi phương thức service, cần thêm quy tắc ở request, ở service, hoặc cả hai tùy thiết kế. Khi đã chọn policy tại service, nó phải được kích hoạt và đi qua interceptor.

Phân biệt các lớp:

| Thành phần | Tác dụng | Điều không tự bảo đảm |
| --- | --- | --- |
| SecurityFilterChain và authorizeHttpRequests | Kiểm soát request HTTP theo matcher/rule | Mọi lệnh gọi nội bộ của service đều bị kiểm @PreAuthorize |
| @EnableMethodSecurity | Đăng ký hạ tầng kiểm quyền ở cấp method | Mỗi lời gọi đều đi qua proxy nếu code tự gọi bằng this |
| @PreAuthorize trên phương thức | Mô tả điều kiện trước khi thực thi | Tự chạy nếu không có interceptor tương ứng |
| Spring AOP proxy | Chặn lời gọi đi vào bean để chạy authorization advice | Chặn được self-invocation trên target object |
| Business policy / data-access check | Xác định quyền theo chủ sở hữu, tenant, action | Được gọi đúng nếu đường đi thực tế bỏ qua tầng policy |

**Role và quyền theo đối tượng là hai cấp khác nhau.** Ngay cả khi method security hoạt động, **hasRole('ADMIN')** chỉ kiểm role; với dữ liệu đa tenant hay tài liệu thuộc người dùng khác, ứng dụng còn cần policy theo tài nguyên.

## 3. Cơ chế: Spring gọi vào proxy rồi mới tới method thật

Khi method security được kích hoạt với chế độ mặc định **PROXY**, Spring tạo proxy quanh các bean thích hợp. Khi bean khác gọi một method được bảo vệ, lời gọi đi qua proxy, qua **AuthorizationManagerBeforeMethodInterceptor** (đối với @PreAuthorize), sau đó mới đi vào target nếu chính sách cho phép.

~~~text
Controller / một bean khác
          |
          v
   Spring AOP proxy của ReportReader
          |
          +--> kiểm @PreAuthorize("hasRole('ADMIN')")
                   |                    |
                   | được phép          | bị từ chối
                   v                    v
            ReportReader.readSecret   AccessDeniedException
                   |
                   v
              Kết quả / side effect
~~~

Ngược lại, sau khi đã vào target object, lời gọi **this.readSecret(...)** là lệnh gọi Java nội bộ tới cùng object. Nó **không quay trở lại proxy**, nên advice trên **readSecret** không được chạy cho lời gọi ấy.

~~~text
Một bean khác --> proxy của ReportService --> target.run()
                                               |
                                               v
                                       this.readSecret()
                                       (không qua proxy)
                                               |
                                               v
                                       lệnh bảo vệ bị bỏ qua
~~~

Đó là khác biệt giữa **annotation có mặt trong source** và **authorization được thực thi ở runtime**.

### 3.1. Sai sót 1: thiếu @EnableMethodSecurity

Ví dụ service:

~~~java
@Service
class PaymentApprovalService {
    @PreAuthorize("hasRole('ADMIN')")
    public void approve(long paymentId) {
        // Thực hiện việc duyệt thanh toán
    }
}
~~~

Nếu application context **không có @EnableMethodSecurity** (hoặc cấu hình tương đương), Spring Boot Starter Security **không tự bật kiểm quyền cấp phương thức**. Trong một ứng dụng chỉ kiểm **authenticated()** ở HTTP, user thường có thể đi tới **approve** dù không có ADMIN. Đây là đoạn minh họa, chưa gồm repository/service bên dưới.

Kích hoạt trên một configuration thuộc application context đang chạy:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Hoặc đặt **@EnableMethodSecurity** trên class **@SpringBootApplication**. Với Spring Security 6, annotation này thay cho API cũ **@EnableGlobalMethodSecurity** trong cấu hình mới.

Các trường hợp dễ nhầm:
- Annotation nằm trên một **@Configuration** không được component-scan/import vào context cần bảo vệ. Code vẫn biên dịch, nhưng interceptor chưa được bật tại nơi bean chạy.
- Cấu hình **@EnableMethodSecurity(prePostEnabled = false)** nhưng code lại dựa vào **@PreAuthorize/@PostAuthorize**. Bạn đã tắt nhóm interceptor pre/post mặc định, trừ khi tự đăng ký lại.
- Ứng dụng dùng **@Secured** hoặc **@RolesAllowed** nhưng chưa kích hoạt nhóm tương ứng. Với cấu hình thường dùng, chỉ **@PreAuthorize/@PostAuthorize** được bật mặc định; **@Secured** cần **securedEnabled = true**, JSR-250 **@RolesAllowed** cần **jsr250Enabled = true**.
- Kiểm thử chỉ gọi controller với một người dùng có quyền cao; không có ca **USER phải bị từ chối** nên thiếu cấu hình vẫn cho test xanh.

### 3.2. Sai sót 2: self-invocation bỏ qua proxy

Đoạn sau **có @EnableMethodSecurity** nhưng vẫn nguy hiểm nếu **run()** được gọi bởi một user thường và không có policy khác bảo vệ đường đó:

~~~java
@Service
public class ReportService {
    public String run(long id) {
        return readSecret(id); // tương đương this.readSecret(id)
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret(long id) {
        return "report:" + id;
    }
}
~~~

Giải thích theo từng lệnh gọi:

1. Code bên ngoài lấy bean **ReportService** từ Spring và gọi **run(7)**. Lời gọi vào **run** có thể đi qua proxy, nhưng **run** không có điều kiện @PreAuthorize.
2. Trong target, **run** gọi **this.readSecret(7)**. Đây là lệnh gọi nội bộ; method interceptor của **readSecret** không được chạy.
3. Kết quả **report:7** có thể trả ra cho USER. Nhưng cùng USER gọi trực tiếp **reportService.readSecret(7)** qua proxy lại bị chặn.

Sự khác biệt này làm lỗ hổng khó phát hiện khi chỉ thử phương thức được gắn annotation mà không thử **mọi entry point** có thể dẫn tới nó. Cả lời gọi tường minh **this.readSecret(...)** và lời gọi không ghi **this** đều có cùng vấn đề.

Các trường hợp không đi qua proxy khác gồm: tự tạo service bằng **new ReportService()**; gọi phương thức **private** hoặc **final** kỳ vọng Spring AOP chặn; gọi trên target object thuần thay cho bean Spring; gọi qua một đường nội bộ không chạm vào interceptor. Với class proxy (CGLIB), phương thức **private/final** không thể được override để advice; JDK dynamic proxy chỉ expose các phương thức tương ứng trên interface được proxy. Quy tắc an toàn cho demo là dùng phương thức **public**, bean do Spring quản lý, và một bean khác gọi qua dependency injection.

**Đổi thành @EnableMethodSecurity(proxyTargetClass = true) không chữa self-invocation.** Chọn CGLIB thay JDK proxy chỉ đổi hình thức proxy, không làm lệnh gọi bằng this đi xuyên qua proxy. Spring có lựa chọn AspectJ weaving, nhưng cần cấu hình/phụ thuộc riêng và không phải bản sửa mặc định cho lỗi thiết kế service.

## 4. Ma trận tái hiện và xác định đúng nguyên nhân

Giả sử route **GET /api/reports/7** yêu cầu người dùng đăng nhập. Chính sách nghiệp vụ: chỉ người có quyền **ROLE_ADMIN** được xem report; người có **ROLE_USER** phải bị từ chối.

| Method security | Đường gọi vào logic bảo vệ | Caller | Kỳ vọng | Dấu hiệu lỗi |
| --- | --- | --- | --- | --- |
| Bật và proxy hoạt động | Controller → ReportReader proxy → readSecret | ADMIN | 200, đúng nội dung report | Không |
| Bật và proxy hoạt động | Controller → ReportReader proxy → readSecret | USER | 403, không có dữ liệu report | Nếu thành 200, cần điều tra |
| **Thiếu @EnableMethodSecurity** | Controller → bean với @PreAuthorize không được kích hoạt | USER | 403 | 200 cho thấy annotation không chặn |
| Bật nhưng **self-invocation** | Controller → run → this.readSecret | USER | 403 | 200 do bỏ qua interceptor |
| Bật và proxy hoạt động | Gọi trực tiếp qua Spring-managed proxy | USER | AccessDeniedException | Nếu trả nội dung, lời gọi không bị guard |
| Bật và proxy hoạt động | HTTP request không xác thực | anonymous | 401 với HTTP Basic | Nếu 200, cả request rule cần kiểm |

**403** trong Spring MVC thường là hệ quả khi **AccessDeniedException** phát sinh trong request flow rồi được filter xử lý; test trực tiếp service sẽ nhận exception, không có HTTP status. Phân biệt hai bối cảnh khi đọc test. Nếu đăng nhập qua form, client có thể gặp 302 redirect tới login thay cho 401.

Khi nghi ngờ thiếu cấu hình, kiểm tra:
- Context nào thực sự chứa **@EnableMethodSecurity**?
- Annotation **@PreAuthorize** có bị tắt bằng **prePostEnabled = false** không?
- Bean được kiểm thử là bean **@Autowired** từ Spring hay instance tạo bằng **new**?
- Entry point đang gọi trực tiếp method có annotation, hay đi qua một method khác trên **cùng instance**?
- Có proxy hay không, và loại proxy có bao phủ method cần bảo vệ không?
- Security rule của HTTP/endpoint có đang che giấu lỗ hổng? Ví dụ route chặn USER trước service, nhưng service vẫn không an toàn khi được gọi từ queue/job khác.

## 5. Ví dụ Java 17+ hoàn chỉnh: bật method security và gọi qua bean proxy

Ví dụ tạo Spring Boot 3.3.5 application nhỏ. Endpoint **GET /api/reports/{id}** chỉ cần authenticated ở request, còn quyền ADMIN được kiểm tại method trên **ReportReader**. **ReportFacade** và **ReportReader** là hai Spring bean khác nhau; nhờ đó khi facade gọi **reader.readSecret(...)**, lệnh gọi đi qua proxy của reader. Demo này trả chuỗi giả lập, không chứa báo cáo thật.

### 5.1. Cấu trúc thư mục

~~~text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/security/
    │   ├── MethodSecurityDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── ReportReader.java
    │   ├── ReportFacade.java
    │   └── ReportController.java
    └── test/java/example/security/
        └── MethodSecurityRegressionTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'method-security-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/example/security/MethodSecurityDemoApplication.java**

~~~java
package example.security;

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

Việc đặt **@EnableMethodSecurity** tại class khởi động bảo đảm nó thuộc application context chính của demo. Mặc định **prePostEnabled = true**, vì vậy interceptor cho **@PreAuthorize** được bật.

**src/main/java/example/security/SecurityConfig.java**

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Cấu hình HTTP cố ý chỉ yêu cầu authenticated để test có thể chứng minh **service method security** là nơi ngăn USER truy cập. Trong hệ thống thực, vẫn nên thêm các HTTP rule tương ứng để phòng vệ nhiều lớp; không trông chờ route tự kiểm ADMIN trong ví dụ này.

**src/main/java/example/security/ReportReader.java**

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportReader {
    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret(long reportId) {
        return "report:" + reportId;
    }
}
~~~

**hasRole('ADMIN')** yêu cầu authority **ROLE_ADMIN** theo quy ước mặc định của Spring Security; **@WithMockUser(roles = "ADMIN")** sẽ tạo authority phù hợp trong test. **@PreAuthorize** chặn trước khi thân method bắt đầu nên thích hợp cho operation cần ngăn side effect.

**src/main/java/example/security/ReportFacade.java**

~~~java
package example.security;

import org.springframework.stereotype.Service;

@Service
public class ReportFacade {
    private final ReportReader reader;

    public ReportFacade(ReportReader reader) {
        this.reader = reader;
    }

    public String open(long reportId) {
        return reader.readSecret(reportId);
    }
}
~~~

**ReportFacade** được tiêm **ReportReader bean** do Spring quản lý, không tự khởi tạo bằng **new**. Nếu method **readSecret** được áp policy, lời gọi từ một bean khác này đi qua proxy. Đây là điểm sửa chính cho lỗi self-invocation.

**src/main/java/example/security/ReportController.java**

~~~java
package example.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportFacade facade;

    public ReportController(ReportFacade facade) {
        this.facade = facade;
    }

    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return facade.open(id);
    }
}
~~~

Lưu ý: response là text demo, không phải bài toán truy cập dữ liệu theo ID. Với API thật, check role không thay thế kiểm owner/tenant của report; cần kiểm thêm quyền trên object cụ thể tại service/data-access.

## 6. Regression test: kiểm cả proxy, cả đường đi từ HTTP

**src/test/java/example/security/MethodSecurityRegressionTest.java**

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityRegressionTest {
    @Autowired MockMvc mvc;
    @Autowired ReportReader reader;
    @Autowired ReportFacade facade;

    @Test
    void securedReaderIsAopProxy() {
        assertTrue(AopUtils.isAopProxy(reader));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotCallReaderDirectly() {
        assertThrows(AccessDeniedException.class,
                () -> reader.readSecret(7));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotBypassMethodSecurityThroughFacade() throws Exception {
        assertThrows(AccessDeniedException.class,
                () -> facade.open(7));

        mvc.perform(get("/api/reports/7"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadThroughHttpAndFacade() throws Exception {
        assertEquals("report:7", facade.open(7));

        mvc.perform(get("/api/reports/7"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:7"));
    }

    @Test
    void anonymousUserMustAuthenticate() throws Exception {
        mvc.perform(get("/api/reports/7"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy trong thư mục project bằng JDK 17+ và Gradle tương thích (ví dụ wrapper Gradle 8.5):

~~~bash
./gradlew test
~~~

Nếu project mới chưa có Gradle wrapper, dùng Gradle đã cài:

~~~bash
gradle test
~~~

**Kỳ vọng 5 test PASS** trên cấu hình đúng. Test không cần DB hoặc HTTP server bên ngoài: **MockMvc** khởi chạy request trong application context kiểm thử; **@WithMockUser** tạo security context giả lập. Lệnh và kết quả dưới đây là **kỳ vọng của mẫu**, không phải stdout của một lần chạy đã được thực hiện.

| Test | Điều khẳng định |
| --- | --- |
| securedReaderIsAopProxy | Reader được bọc trong AOP proxy |
| userCannotCallReaderDirectly | USER bị chặn ở method trực tiếp |
| userCannotBypassMethodSecurityThroughFacade | USER bị chặn cả ở facade và endpoint |
| adminCanReadThroughHttpAndFacade | ADMIN vẫn thực hiện được thao tác hợp lệ |
| anonymousUserMustAuthenticate | Request không đăng nhập bị 401 |

**Thử phép kiểm chứng phản chứng trong môi trường test:**

1. Tạm bỏ **@EnableMethodSecurity**, chạy test. **userCannotCallReaderDirectly** và **userCannotBypassMethodSecurityThroughFacade** phải FAIL vì method không còn bị chặn; test proxy cũng có thể FAIL. Khôi phục annotation.
2. Tạm thay facade bằng phiên bản tự gọi method được bảo vệ **trên chính nó** (đoạn ở mục 7), chạy test. USER có thể lấy dữ liệu; bài test **userCannotBypassMethodSecurityThroughFacade** phải FAIL. Khôi phục hai-bean design.
3. Chạy lại test sau khi khôi phục. Chỉ coi cấu hình an toàn khi cả test phủ denied và allowed case PASS.

Không suy ra bảo mật chỉ vì test ADMIN trả 200: cả implementation có lỗi và implementation đúng đều có thể trả 200 cho ADMIN. **Negative test với USER** mới chứng minh rào kiểm quyền đang hoạt động.

## 7. Biến thể cố ý có lỗi để hiểu self-invocation

Đây là **phiên bản thay thế minh họa nguy hiểm**, không ghép chung với **ReportFacade.java** ở mục 5. Nếu thay facade bằng code này và giữ nguyên controller/config/test, phương thức **open** tự gọi **readSecret** trên chính target:

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportFacade {
    public String open(long reportId) {
        return readSecret(reportId); // self-invocation: bypass advice
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret(long reportId) {
        return "report:" + reportId;
    }
}
~~~

Nhận xét:

- **GET /api/reports/7** với USER có thể trả **200, report:7**, vì endpoint gọi **open**, trong khi **@PreAuthorize** chỉ nằm trên **readSecret** và không được chạy qua proxy.
- Với USER, gọi **reportFacade.readSecret(7)** trực tiếp từ bean khác lại bị từ chối do lời gọi này đi vào proxy.
- Nếu bạn chỉ kiểm method readSecret trực tiếp mà quên kiểm đường **open**, bạn có thể kết luận sai rằng method security đã bảo vệ toàn bộ service.
- Sửa bằng cách đưa logic bảo vệ sang **ReportReader bean** riêng và tiêm vào facade như mục 5. Không giải quyết bằng cách lặp lại **@EnableMethodSecurity** hay bật **proxyTargetClass**.

Nếu design bắt buộc nhiều lệnh gọi nội bộ trên cùng class, có thể đưa policy vào một **bean kiểm quyền riêng** và gọi qua bean đó ở entry point; hoặc dùng kiểm tra quyền tường minh trong service một cách nhất quán. Giải pháp tự inject chính mình hay gọi **AopContext.currentProxy()** tạo sự phụ thuộc vào cơ chế AOP và có thể phát sinh phụ thuộc vòng/cấu hình khó bảo trì; nên ưu tiên tách bean.

## 8. Chẩn đoán bằng proxy và đường gọi thực tế

Một kiểm tra hữu ích khi có nghi vấn là xem object được inject có phải proxy hay không:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(reportReader);
System.out.println("Proxied: " + proxy);
~~~

Đây là snippet phụ thuộc biến **reportReader** được inject từ Spring; không phải Java standalone. Nếu method **readSecret** được áp interceptor trong ví dụ, kỳ vọng **Proxied: true**. Nhưng chỉ thấy proxy **không đủ** để kết luận mọi path an toàn: lời gọi từ proxy sang target rồi target tự gọi một method khác vẫn có thể bỏ qua advice.

Đọc stack trace hoặc đặt breakpoint tại:
- Bean được inject ở controller/facade.
- Phương thức public gắn **@PreAuthorize**.
- Code gọi method ấy từ bean khác hay từ **this**.
- Kết quả denied và mọi side effect đã phát sinh.

Không chỉ tìm chuỗi **@PreAuthorize** trong source. Mục tiêu là chứng minh **caller thực tế** được kiểm trước khi logic nhạy cảm chạy. Nếu method có nhiều entry point như HTTP, message consumer, scheduler, CLI hoặc test, lập ma trận trên từng entry point.

Phân biệt những tình huống dễ bị đánh đồng:

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Có @PreAuthorize nhưng USER vẫn gọi được ngay cả khi gọi thẳng bean được inject | Method security chưa bật, nhóm annotation bị tắt, bean không được proxy/annotation không được nhận diện | Kiểm cấu hình và negative test direct-call |
| Direct-call bị chặn, nhưng một endpoint khác vẫn trả dữ liệu | Self-invocation hoặc đường gọi khác né method bảo vệ | Truy vết từ endpoint đến target; test qua facade |
| Test có proxy nhưng vẫn bị bypass | Proxy chỉ chặn lần đi vào bean; lời gọi nội bộ không qua nó | Xem method chứa this.method() |
| USER luôn bị 403 khi gọi HTTP nên tưởng service an toàn | Rule HTTP chặn trước, service method security có thể vẫn vô hiệu | Test service qua bean được inject, không chỉ test endpoint |
| Chỉ phương thức annotation trên interface/class nào đó không được chặn | Cấu trúc proxy, annotation placement hoặc khả năng override của method | Kiểm bean thực tế, interface và public/final/private; test quyền thực tế |
| Test dùng new ReportReader() rồi kiểm security | Object không do Spring quản lý | Dùng @SpringBootTest và @Autowired bean |

**Đừng dùng @PostAuthorize để “chặn trước” thao tác ghi.** @PostAuthorize có thể đánh giá sau khi thân method đã chạy, vì vậy có thể tồn tại side effect trước khi từ chối. Với lệnh ghi/xóa/duyệt nhạy cảm, nên dùng @PreAuthorize hoặc service-level policy được gọi trước thao tác và kiểm tra tính nhất quán của giao dịch.

## 9. Phòng ngừa trong code review và kiểm thử dự án thật

Checklist tập trung vào đúng hai lỗi của bài:

- Tìm cấu hình method security có hiệu lực trong **application context được deploy**, không chỉ trong source/test config.
- Xác nhận annotation đúng loại được bật: **@PreAuthorize**, **@PostAuthorize**, **@Secured**, **@RolesAllowed** có cờ kích hoạt khác nhau.
- Kiểm bean đã được Spring tạo/tiêm; không bypass bằng **new** hoặc tham chiếu trực tiếp đến target object.
- Tìm lời gọi **this.sensitiveMethod(...)**, lời gọi nội bộ ngầm định, helper **private/final** mang annotation quyền; đánh giá mọi entry point có thể gọi tới logic ấy.
- Đặt method bảo vệ ở **service boundary** phù hợp và gọi từ một bean khác; giảm logic nghiệp vụ nhạy cảm trong controller.
- Có ít nhất một test **allowed** và một test **denied** cho từng vai trò/action quan trọng. Test cả service qua **@Autowired** và endpoint/consumer thực tế.
- Với object/tenant authorization, bổ sung case khác chủ/khác tenant; **hasRole** không thay thế xác thực quyền trên tài nguyên.
- Khi thay đổi cấu hình AOP, package scan, bean lifecycle hoặc tách/gộp service, chạy lại test phủ authorization; self-invocation rất dễ tái xuất hiện sau refactor.
- Với API ghi, kiểm trạng thái lưu trữ/side effect sau request bị từ chối; chỉ nhìn 403 có thể bỏ sót thay đổi xảy ra trước khi check.
- Không dùng thao tác kiểm thử trên production data nếu không có quyền; ghi log testcase với dữ liệu giả lập và ẩn credential.

### Những nhầm tưởng phổ biến

**“Có spring-boot-starter-security nghĩa là method security tự bật.”** Sai. Starter hỗ trợ security ở web, nhưng cấu hình kiểm quyền phương thức cần **@EnableMethodSecurity** hoặc thiết lập tương đương.

**“@PreAuthorize đặt trên một method là đủ.”** Chưa đủ. Method phải được interceptor phù hợp nhìn thấy và lời gọi phải đi qua điểm chặn của proxy.

**“Đã dùng CGLIB nên this.securedMethod() được chặn.”** Sai. CGLIB vẫn là proxy; self-invocation trên target không đi qua nó.

**“Test principal ADMIN thành công chứng minh policy đang chạy.”** Sai. Điều đó chỉ chứng minh đường thành công; cần test USER bị chặn.

**“Đặt policy ở controller là bảo vệ mọi nơi.”** Chưa chắc. Message listener, scheduled job hay một bean khác có thể gọi trực tiếp service. Phân quyền theo nghiệp vụ nên được kiểm tại tầng sở hữu logic nhạy cảm.

**“Tắt HTTP filter trong MockMvc để test method security cho dễ.”** Không nên dùng phép test HTTP bị vô hiệu filter làm bằng chứng cho policy HTTP. Khi test service, dùng direct bean test; khi test endpoint, giữ đúng security filter chain.

## 10. Kết luận vận dụng

Để một phương thức Spring thực sự được bảo vệ bằng **@PreAuthorize**, cần đồng thời thỏa hai điều kiện: **(1) method security được bật trong đúng context; (2) lời gọi đến method được chặn đi qua Spring-managed proxy** (hoặc cơ chế advice thay thế đã được cấu hình chủ đích). Thiếu một trong hai, annotation có thể không kiểm quyền dù source trông hợp lệ.

Khi kiểm thử, luôn thực hiện **hai chiều**: một user hợp lệ phải gọi thành công, và một user không đủ quyền phải bị chặn cả khi gọi trực tiếp bean lẫn qua mọi entry point liên quan. Với Spring Security, kiểm chứng đường gọi thực tế đáng tin cậy hơn việc chỉ đếm annotation trong code.

### Tài liệu chính thức để tra cứu sâu hơn

- Spring Security — Method Security (Spring Security 6.x): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework — Spring AOP Proxying Mechanisms (self-invocation, JDK/CGLIB): https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
