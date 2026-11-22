# Spring AOP và điều kiện để Method Security được thực thi

## 1. Vì sao có `@PreAuthorize` nhưng phương thức vẫn chạy?

Xem hai lời gọi đến cùng một phương thức:

```java
// (1) reportService được Spring inject từ ApplicationContext
reportService.deleteReport("R-7");

// (2) nằm bên trong ReportService
this.deleteReport("R-7");
```

Giả sử `deleteReport` gắn `@PreAuthorize("hasRole('ADMIN')")`. Trong cấu hình Spring Method Security sử dụng **Spring AOP proxy** mặc định, lời gọi (1) đi qua proxy để kiểm tra quyền, còn lời gọi (2) là **self-invocation** có thể đi thẳng đến đối tượng đích và bỏ qua kiểm tra. Đây là nguyên nhân của nhiều lỗi phân quyền ở tầng service dù annotation trông hoàn toàn đúng.

Bài này giải thích các điều kiện cần thiết để Spring Security **thực sự chặn lời gọi phương thức**: kích hoạt Method Security, xác định bean được Spring quản lý, đường gọi đi qua proxy, loại proxy, khả năng intercept method, annotation được bật, dữ liệu xác thực và các yếu tố liên quan đến giao dịch.

Sau bài học, bạn sẽ biết:

1. Phân biệt **Spring AOP proxy** với Spring Security HTTP filter chain.
2. Hiểu cơ chế Spring Security áp dụng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.
3. Xác định lúc nào một lời gọi **đi qua proxy** và lúc nào bị bypass.
4. Phân biệt proxy JDK interface và CGLIB subclass, nhất là giới hạn `private`, `final`, `static` và self-invocation.
5. Viết một ví dụ Spring Boot Java 17+ kiểm chứng **cùng một method** có thể bị từ chối qua proxy nhưng được chạy qua `this`.
6. Thiết kế service và test để phát hiện lỗi sớm, kể cả khi phối hợp `@Transactional` và `@Async`.

**Ngữ cảnh kỹ thuật:** Spring Security 6.x / Spring Boot 3.x với proxy-based Method Security, là trường hợp phổ biến ở ứng dụng Spring MVC, REST và service. Spring Security có các chế độ nâng cao như AspectJ weaving, nhưng chúng không phải hành vi mặc định ở đây.

## 2. Từ lời gọi Java đến interceptor bảo mật

Spring AOP không tự thay đổi bytecode của mọi lời gọi Java trong ứng dụng. Trong cơ chế proxy thông thường, Spring đặt **một đối tượng proxy** trước bean đích. Caller lấy bean từ container thường nhận proxy, và proxy chạy một chuỗi advisor/interceptor trước hoặc sau khi chuyển lời gọi đến target.

```text
Controller / service khác / test
                  |
                  | gọi reportService.deleteReport(...)
                  v
          Bean Spring inject
           (AOP proxy)
                  |
                  v
          Method Security advisors
           |  @PreFilter: lọc tham số
           |  @PreAuthorize: kiểm tra quyền trước
           |  Authentication + SpEL + AuthorizationManager
           |
        granted? ------- no ------> AccessDeniedException
           |
          yes
           v
          Target bean
          deleteReport(...)
           |
           v
           |  @PostAuthorize: kiểm tra kết quả
           |  @PostFilter: lọc kết quả
           v
        Caller nhận kết quả
```

Đây là sơ đồ khái niệm: thứ tự advisor cụ thể phụ thuộc loại annotation và cấu hình. `@PreFilter`, `@PreAuthorize`, `@PostAuthorize` và `@PostFilter` có interceptor riêng. Ví dụ ở Spring Security hiện đại, `@PreAuthorize` được xử lý bởi `AuthorizationManagerBeforeMethodInterceptor`, sử dụng `PreAuthorizeAuthorizationManager` để đánh giá biểu thức.

**Điều quan trọng:** annotation không phải đoạn code tự động chạy mỗi khi JVM thực thi method. Annotation là metadata; cần có hạ tầng AOP phù hợp và **lời gọi đi qua ranh giới proxy** để interceptor được kích hoạt.

### Spring Method Security khác HTTP Security thế nào?

| Cơ chế | Điểm chặn chính | Thích hợp bảo vệ | Có cần HTTP không? |
| --- | --- | --- | --- |
| `SecurityFilterChain` | Request HTTP đi vào web application | URL, route, endpoint, request | Có |
| Method Security | Lời gọi Spring bean thông qua advisor | Service operation, tham số, kết quả | Không |
| Kiểm soát quyền tại database | Truy vấn/ghi dữ liệu | Quyền sở hữu, tenant, điều kiện cạnh tranh | Không |

`requestMatchers("/admin/**").hasRole("ADMIN")` không thay thế được ràng buộc của service được gọi từ scheduler, message listener hay service khác. Ngược lại, `@PreAuthorize` cũng không tự cấu hình authentication HTTP hoặc luồng trả lỗi 401/403.

## 3. Những điều kiện để Method Security chạy

Có thể kiểm tra theo thứ tự sau:

| Điều kiện | Nếu thiếu điều kiện | Kiểm tra thực tế |
| --- | --- | --- |
| Thư viện Spring Security và AOP tương thích nằm trên classpath | Không có hạ tầng authorization method phù hợp | Kiểm tra dependency và ApplicationContext |
| Có `@EnableMethodSecurity` hoặc cấu hình tương đương | `@PreAuthorize` không được kích hoạt chỉ nhờ thêm starter | Đọc cấu hình và kiểm thử lời gọi |
| Method/class có annotation **được bật** và xác định rõ | Không có advisor áp dụng cho method cần bảo vệ | Kiểm tra annotation và tùy chọn enable |
| Target thuộc Spring bean, proxy được tạo và caller dùng bean proxy | Đối tượng `new` thủ công không được chặn | `AopUtils.isAopProxy(bean)` |
| Lời gọi có thể được intercept và **đi qua proxy** | `this.method()`, `private`/`final` (với CGLIB) có thể bypass | Test gọi từ bean khác |
| Có `Authentication` và chính sách/biểu thức hợp lệ | Bị từ chối hoặc đánh giá sai theo ngữ cảnh | `@WithMockUser`, test quyền cho phép/từ chối |
| Không bị ảnh hưởng bởi thay đổi thread hoặc thứ tự advisor ngoài dự tính | Đánh giá bằng security context khác, hoặc thứ tự kiểm tra không như dự kiến | Test đường đi thật với async/transaction |

Các điều kiện về AOP và annotation quyết định **cơ chế có chặn method không**. Việc có `Authentication` và chính sách đúng quyết định **chặn rồi sẽ cho phép hay từ chối**. Phân biệt hai lớp này giúp tránh chẩn đoán sai: một lệnh trả kết quả thành công không nhất thiết là được cấp quyền; có thể vì lời gọi đã bỏ qua interceptor.

## 4. Kích hoạt Method Security đúng cách

### 4.1. Đăng ký cấu hình

Với Java config:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Có thể đặt `@EnableMethodSecurity` trực tiếp trên lớp `@SpringBootApplication`, như ví dụ đầy đủ ở mục 7. Trong Spring Boot, thêm dependency `spring-boot-starter-security` **chưa mặc nhiên bật** Method Security. `@EnableMethodSecurity` thay thế cách cấu hình cũ `@EnableGlobalMethodSecurity` trong Spring Security hiện đại.

`@EnableMethodSecurity` mặc định bật nhóm pre/post annotation:

- `@PreAuthorize`: điều kiện phải đúng **trước khi** thân phương thức chạy.
- `@PostAuthorize`: đánh giá **sau khi** thân phương thức trả về; có thể tham chiếu `returnObject`.
- `@PreFilter`: loại những phần tử tham số đầu vào không đạt điều kiện.
- `@PostFilter`: lọc những phần tử của giá trị trả về.

Để dùng `@Secured` hoặc JSR-250 (`@RolesAllowed`, `@PermitAll`, `@DenyAll`) theo cơ chế tương ứng, cần bật tùy chọn:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

Cấu hình đó là **ví dụ thay thế**, không cần thêm song song với `@EnableMethodSecurity` mặc định cho bài demo. Cần dependency annotation tương ứng khi dùng JSR-250. Nếu cấu hình `prePostEnabled = false`, những annotation nhóm pre/post không còn tự được bật bởi `@EnableMethodSecurity`.

### 4.2. Bean, proxy và phạm vi scan

Thông thường, một service cần là bean được Spring quản lý:

```java
@Service
public class PaymentService {
    @PreAuthorize("hasAuthority('payment:approve')")
    public void approve(long paymentId) {
        // ...
    }
}
```

Caller cần được tiêm `PaymentService` bởi Spring, và phải gọi **qua tham chiếu đã được container cung cấp**. Điều này khác với:

```java
PaymentService service = new PaymentService();
service.approve(42L); // Java object thủ công; không có Spring AOP advice
```

Đoạn trên chỉ minh họa lỗi, không phải đoạn code dùng trong ứng dụng thật. `@Service` là cách phổ biến để tạo bean qua component scan; bean cũng có thể được cung cấp bằng `@Bean`. Annotation bảo mật có thể đặt ở method, class hoặc interface theo quy tắc Spring Security, nhưng các annotation mâu thuẫn qua nhiều interface/supertype cần được giải quyết rõ thay vì dựa vào kết quả không xác định.

**Chỉ có bean chưa đủ:** nếu method gọi một protected method khác bên trong cùng target qua `this`, lời gọi nội bộ không đi trở lại proxy.

### 4.3. Giới hạn của annotation và biểu thức

Ví dụ:

```java
@PreAuthorize("hasAuthority('report:read')")
public Report readReport(String id) {
    // ...
}
```

`hasAuthority('report:read')` tìm authority có chuỗi chính xác `report:read` trong `Authentication`. `hasRole('ADMIN')` theo cấu hình mặc định kiểm tra authority `ROLE_ADMIN`, không phải chỉ chuỗi `ADMIN`. Cần đặc tả nhất quán cách ứng dụng cấp role/authority.

Spring Security không tự suy ra quyền đối tượng từ tên method. Nếu muốn kiểm tra owner/ACL, phải cung cấp biểu thức và nguồn dữ liệu tin cậy thích hợp. Kể cả khi interceptor hoạt động hoàn hảo, chính sách quyền viết sai vẫn gây lỗi bảo mật.

## 5. Proxy JDK và proxy CGLIB

Spring AOP có hai cơ chế proxy chủ yếu:

| Đặc điểm | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| Đối tượng proxy | Triển khai interface của target | Lớp con sinh ra từ target |
| Phù hợp | Service khai báo interface; caller dùng interface | Bean không có interface hoặc cấu hình dùng class proxy |
| Phương thức có thể gọi qua proxy | Những method phơi bày qua interface được proxy | Những method instance có thể override/intercept |
| Hạn chế chính | Method không có trong interface không được phơi bày trên JDK proxy | `final` class không thể subclass; `final`/`private` method không thể override |
| Self-invocation `this.method()` | Bypass AOP advice | Bypass AOP advice |

Tài liệu Spring Framework mô tả mặc định của Spring AOP thuần: có interface thì có thể dùng JDK proxy, không có interface thì dùng CGLIB. **Spring Boot có thể cấu hình proxy kiểu class theo mặc định**; đừng suy luận kiểu proxy chỉ từ việc có interface. Cách chắc chắn là kiểm tra đối tượng thực:

```java
import org.springframework.aop.support.AopUtils;

System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.isJdkDynamicProxy(service));
System.out.println(AopUtils.isCglibProxy(service));
```

Ba dòng là **mảnh code minh họa**, giả định biến `service` đã được Spring tiêm; kết quả phụ thuộc cấu hình đang chạy.

### `private`, `final`, `static`, constructor

- `private` method không thể là điểm intercept của subclass proxy; đặt `@PreAuthorize` lên private helper không bảo vệ lời gọi helper.
- `final` method của một CGLIB-proxied class không thể override nên không được advice; `final` class không thể tạo subclass proxy. Với JDK interface proxy, cần xem đúng lời gọi qua interface, nhưng không nên biến điều đó thành cách vượt thiết kế lớp.
- `static` method không được gọi qua instance proxy theo cách Spring AOP method advice thông thường.
- Constructor và code đang chạy trước lúc bean/proxy được cung cấp cho caller không phải nơi an toàn để dựa vào `@PreAuthorize` trên phương thức khác. Tránh gọi logic yêu cầu method security từ constructor hoặc khởi tạo sớm rồi cho rằng proxy đã bảo vệ.
- Spring AOP có thể hỗ trợ một số non-public method trong tình huống proxy nhất định, nhưng **public service method được gọi từ bean khác** là lựa chọn minh bạch và dễ kiểm thử nhất.
- Nếu dùng Kotlin, class và method `final` theo mặc định cần đặc biệt chú ý cơ chế plugin `all-open` hoặc thiết kế interface/proxy.

**Đổi JDK proxy sang CGLIB không sửa lỗi self-invocation.** Cả hai đều chỉ áp dụng advice khi lời gọi đến proxy.

## 6. Self-invocation: nguyên nhân, hậu quả và hướng sửa

Xét ví dụ lỗi:

```java
@Service
public class InvoiceService {

    public void submitInvoice(long id) {
        this.publishInvoice(id); // gọi trực tiếp trên target
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void publishInvoice(long id) {
        // Giả sử có side effect ghi dữ liệu thật
    }
}
```

Một service khác gọi `invoiceService.submitInvoice(10)` qua proxy. Sau khi proxy chuyển lời gọi vào thân `submitInvoice`, biểu thức `this.publishInvoice(10)` chỉ là lời gọi Java nội bộ. Vì nó **không tạo lượt gọi mới đến proxy**, advisor của `publishInvoice` không được chạy.

Tính chất này cũng thường gặp với `@Transactional`, `@Cacheable` và các cơ chế Spring AOP khác. Nó không phải lỗi của SpEL hoặc của `hasRole`.

### Thiết kế đúng: tách ranh giới bean

```java
@Service
public class InvoicePublishingService {

    @PreAuthorize("hasRole('ADMIN')")
    public void publishInvoice(long id) {
        // thao tác chỉ admin được phép làm
    }
}
```

```java
@Service
public class InvoiceWorkflowService {

    private final InvoicePublishingService publishingService;

    public InvoiceWorkflowService(InvoicePublishingService publishingService) {
        this.publishingService = publishingService;
    }

    public void submitInvoice(long id) {
        publishingService.publishInvoice(id); // qua bean/proxy
    }
}
```

Hai mảnh code này minh họa cách tách bean; nếu đặt trong hai file Java riêng với các import cần thiết, phương thức được bảo vệ sẽ đi qua tham chiếu do Spring inject. Người gọi workflow không cần biết chi tiết AOP. Ngay cả vậy, hãy kiểm thử đúng bean trong context và logic cập nhật dữ liệu.

Các lựa chọn ít ưu tiên hơn gồm inject tham chiếu proxy của chính bean hoặc dùng `AopContext.currentProxy()`. Chúng tăng độ phụ thuộc vào Spring AOP, có thể tạo vòng phụ thuộc hoặc yêu cầu cấu hình bổ sung. Khi được phép thay đổi thiết kế, **tách một service chịu trách nhiệm bảo vệ method** thường dễ hiểu, dễ bảo trì và dễ test hơn.

Nếu yêu cầu thật sự phải intercept **cả lời gọi nội bộ**, Spring Security có chế độ AspectJ weaving (`@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)`), nhưng phải cấu hình AspectJ, thư viện aspects và compile-time/load-time weaving đầy đủ. **Chỉ đổi một tham số annotation mà không thiết lập weaving không biến self-invocation thành lời gọi được bảo vệ.**

## 7. Ví dụ chạy được: quan sát proxy và self-invocation

Đây là một ứng dụng Java 17 / Spring Boot `3.5.8` (phiên bản cố định phục vụ demo). Nó không cần HTTP server hay database. Dòng `SELF_CALL` minh họa **một lỗ hổng cố ý** trên phương thức chỉ trả chuỗi để học AOP; không sao chép kiểu gọi này vào nghiệp vụ có side effect.

Cấu trúc:

```text
method-security-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── MethodSecurityProxyDemoApplication.java
    │   ├── ReportService.java
    │   └── ReportWorkflow.java
    └── test/java/demo/
        └── ReportServiceSecurityTest.java
```

### 7.1. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'method-security-proxy-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` cung cấp Spring Security và những dependency liên quan; `@EnableMethodSecurity` trong ứng dụng sẽ đăng ký hạ tầng method authorization. `spring-boot-starter-test` và `spring-security-test` phục vụ kiểm thử `@WithMockUser`.

### 7.2. Service với ba đường gọi

**`src/main/java/demo/ReportService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport(String id) {
        return "report:" + id;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminOnly() {
        return "admin-result";
    }

    // CHỈ ĐỂ MINH HỌA VẤN ĐỀ; không dùng cho nghiệp vụ thật.
    public String selfCallDemo() {
        return this.adminOnly(); // bypass proxy method-security advice
    }
}
```

`readReport` và `adminOnly` sẽ được Spring Security kiểm tra khi caller gọi qua proxy. Ngược lại, `selfCallDemo` gọi `this.adminOnly()` sau khi đã ở bên trong target; vì vậy interceptor của `adminOnly` không thực thi lần nữa.

### 7.3. Workflow đi qua bean được inject

**`src/main/java/demo/ReportWorkflow.java`:**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ReportWorkflow {

    private final ReportService reports;

    public ReportWorkflow(ReportService reports) {
        this.reports = reports;
    }

    public String callAdmin() {
        return reports.adminOnly();
    }
}
```

`ReportWorkflow` nhận `ReportService` từ Spring, nên dù `callAdmin` không gắn annotation, lời gọi **đến `ReportService.adminOnly`** vẫn đi qua proxy của `ReportService`.

### 7.4. Cấu hình và chương trình quan sát

**`src/main/java/demo/MethodSecurityProxyDemoApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityProxyDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            ReportService reports,
            ReportWorkflow workflow) {
        return args -> {
            var authentication = new UsernamePasswordAuthenticationToken(
                "alice",
                "demo-only",
                List.of(new SimpleGrantedAuthority("report:read"))
            );
            SecurityContextHolder.getContext()
                .setAuthentication(authentication);

            try {
                System.out.println("PROXY: " + AopUtils.isAopProxy(reports));
                System.out.println("READ: " + reports.readReport("R-7"));

                try {
                    reports.adminOnly();
                    System.out.println("DIRECT_ADMIN: UNEXPECTED");
                } catch (AccessDeniedException denied) {
                    System.out.println("DIRECT_ADMIN: DENIED");
                }

                // Chỉ minh họa: this.adminOnly() bypass security advice.
                System.out.println("SELF_CALL: " + reports.selfCallDemo());

                try {
                    workflow.callAdmin();
                    System.out.println("OTHER_BEAN: UNEXPECTED");
                } catch (AccessDeniedException denied) {
                    System.out.println("OTHER_BEAN: DENIED");
                }
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }
}
```

Trong chương trình demo, `alice` có authority `report:read` nhưng **không có `ROLE_ADMIN`**. Vì `ReportService` là Spring bean được proxy, gọi `reports.adminOnly()` bị từ chối. `reports.selfCallDemo()` được gọi qua proxy, nhưng bên trong nó gọi `this.adminOnly()` nên vòng interceptor của `adminOnly` không chạy.

Tạo Gradle Wrapper tương ứng nếu dự án chưa có, rồi chạy:

```bash
./gradlew bootRun
```

Trên Windows PowerShell: `.\gradlew.bat bootRun`. Nếu máy có Gradle cài sẵn và dự án chưa có Wrapper, có thể chạy `gradle bootRun`.

**Các dòng stdout do mã demo in ra** (Spring Boot còn có log khởi động) là:

```text
PROXY: true
READ: report:R-7
DIRECT_ADMIN: DENIED
SELF_CALL: admin-result
OTHER_BEAN: DENIED
```

Giải thích theo đúng thứ tự:

1. `PROXY: true` chứng minh bean đang được Spring AOP bọc proxy.
2. `READ` thành công vì authority khớp `report:read`.
3. `DIRECT_ADMIN: DENIED` chứng minh gọi `@PreAuthorize("hasRole('ADMIN')")` qua proxy hoạt động.
4. `SELF_CALL: admin-result` là **bằng chứng của self-invocation bypass**, chứ **không phải cấp quyền thành công**.
5. `OTHER_BEAN: DENIED` chứng minh gọi cùng phương thức từ bean khác thông qua injection vẫn áp dụng kiểm tra.

`UsernamePasswordAuthenticationToken` tự tạo là **kỹ thuật mô phỏng security context cho demo**. Không dùng cách nhận username từ client rồi tự tạo token đã xác thực trong hệ thống thật; phải dùng flow xác thực đã được Spring Security cấu hình.

## 8. Kiểm thử bảo mật bằng `@SpringBootTest`

**`src/test/java/demo/ReportServiceSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired ReportService reports;
    @Autowired ReportWorkflow workflow;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "report:read"
    )
    void proxyEnforcesProtectionOnExternalCalls() {
        assertTrue(AopUtils.isAopProxy(reports));
        assertEquals("report:R-7", reports.readReport("R-7"));

        assertThrows(
            AccessDeniedException.class,
            reports::adminOnly
        );
        assertThrows(
            AccessDeniedException.class,
            workflow::callAdmin
        );
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void selfInvocationDemonstratesBypass() {
        // CHỈ kiểm chứng vấn đề; không chấp nhận mẫu này trong sản phẩm.
        assertEquals("admin-result", reports.selfCallDemo());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanInvokeProtectedMethod() {
        assertEquals("admin-result", reports.adminOnly());
        assertThrows(
            AccessDeniedException.class,
            () -> reports.readReport("R-7")
        );
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerCannotRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.readReport("R-7")
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

`@SpringBootTest` tải context thật, còn `@WithMockUser`/`@WithAnonymousUser` đến từ `spring-security-test`. `@Autowired` lấy proxy của service, không tạo `new ReportService()` thủ công. Bốn test xác nhận đồng thời: **có proxy**, **cho phép đúng authority**, **từ chối thiếu authority**, **self-invocation bypass** và **từ chối anonymous**.

Đây là kiểm thử có ích vì một unit test chỉ gọi trực tiếp Java object có thể vượt qua mọi assertion nghiệp vụ mà **không bao giờ chạy interceptor**. Nếu thay `@SpringBootTest` bằng một test slice như `@WebMvcTest`, phải kiểm tra slice đó có import đầy đủ method security config và service bean cần thiết hay không.

## 9. Tại sao `@PreAuthorize` và `@PostAuthorize` khác nhau khi có tác dụng phụ?

Hai annotation chạy ở vị trí khác nhau:

```java
@PreAuthorize("hasAuthority('document:write')")
public void updateDocument(long id) {
    // update diễn ra sau khi kiểm tra pre-authorize thành công
}
```

```java
@PostAuthorize("returnObject.owner() == authentication.name")
public Document findDocument(long id) {
    // phương thức này đã chạy trước khi check kết quả
    return repository.findById(id).orElseThrow();
}
```

Đây là **mảnh cú pháp minh họa**, giả định có `Document` record và `repository` được Spring inject; không phải chương trình Java độc lập. `@PostAuthorize` cho phép dùng `returnObject`, hữu ích khi phải đọc tài nguyên trước rồi mới biết quyền xem. Nhưng nếu thân phương thức **đã ghi dữ liệu**, hậu kiểm có thể diễn ra quá muộn để ngăn side effect. Với thao tác ghi, cần kiểm tra trước hoặc gắn điều kiện quyền vào chính thao tác dữ liệu và transaction.

`@PreFilter`/`@PostFilter` cũng yêu cầu đi qua proxy và có thể thay đổi collection; đừng cho rằng annotation tự được áp dụng nếu lời gọi thuộc self-invocation.

## 10. Method Security và `@Transactional`

Một service thường có cả hai:

```java
@PreAuthorize("hasAuthority('transfer:approve')")
@Transactional
public void approveTransfer(long transferId) {
    // kiểm tra ràng buộc nghiệp vụ và cập nhật trong transaction
}
```

**Method Security và Transaction Management đều dùng advisor** trong Spring AOP ở chế độ proxy. Một lượt gọi có thể đi qua nhiều interceptor; **thứ tự advisor** quyết định lúc nào kiểm tra quyền và lúc nào transaction bắt đầu. Không nên đoán rằng mọi ứng dụng đều có cùng thứ tự, vì có cấu hình `order`, `offset`, advisor tùy chỉnh và các cách bố trí bean khác nhau.

Những điều cần ghi nhớ:

- `@PreAuthorize` chặn trước khi **thân phương thức** chạy; nó không mặc định giải quyết tính nguyên tử với database.
- `@PostAuthorize` thực hiện hậu kiểm; nếu method đã commit dữ liệu, không thể kỳ vọng hậu kiểm tự động “quay ngược” side effect.
- `@Transactional` cũng có rủi ro self-invocation trong chế độ proxy. Một lời gọi `this.update()` có thể bỏ qua cả transaction advice của `update`.
- Khi ownership/ACL có thể thay đổi đồng thời, kiểm tra quyền trước và thao tác ghi sau tạo khoảng trống **TOCTOU (time of check, time of use)**. Trong thao tác ghi nhạy cảm, ràng buộc điều kiện quyền ngay tại câu truy vấn/cập nhật trong transaction, chẳng hạn `UPDATE ... WHERE id = :id AND owner_id = :currentUser`, rồi kiểm tra số hàng bị ảnh hưởng.
- Nếu cần rõ ràng về điểm cắt bảo mật và transaction, có thể tổ chức facade bảo mật gọi sang bean transaction riêng, kiểm thử cả trường hợp được phép và bị từ chối, và cấu hình advisor order khi thực sự cần.

Sơ đồ thiết kế dễ kiểm soát:

```text
HTTP Controller / Message Consumer
              |
              v
    Secured Facade Bean
    @PreAuthorize(...)
              |
              v
    Transactional Service Bean
    @Transactional
              |
              v
       Repository / DB
```

Cả hai phương thức nên được gọi qua **đúng bean proxy**. Thiết kế tách lớp không thay thế ràng buộc quyền cấp bản ghi ở DB; nó chỉ giúp đặt ranh giới dễ đọc và test.

## 11. Vấn đề luồng, async và vòng đời bean

### 11.1. `SecurityContext` theo thread

Spring Security trong ứng dụng Servlet thông thường dùng `SecurityContextHolder` để gắn authentication với ngữ cảnh thực thi, mặc định dựa trên `ThreadLocal`. Khi chuyển sang thread khác bằng `@Async`, `CompletableFuture`, executor hoặc tự tạo `Thread`, context có thể **không tự truyền** sang thread mới.

Hệ quả: một phương thức protected trong tác vụ async có thể bị từ chối dù caller gốc đã đăng nhập, hoặc nhận một ngữ cảnh không phù hợp nếu ứng dụng xử lý context sai. Cân nhắc `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế propagation được framework cung cấp và **xóa context đúng thời điểm**. Không hard-code một tài khoản quản trị chung vào toàn bộ thread pool để “sửa” lỗi.

### 11.2. Khởi tạo bean và constructor

Spring phải tạo và chuẩn bị bean trước khi các caller có thể nhận đầy đủ proxy. Đừng sử dụng logic cần `@PreAuthorize` trong constructor để bảo vệ một thao tác khởi tạo. Tương tự, việc gọi protected method từ `@PostConstruct` có thể không đi qua đường proxy mà bạn kỳ vọng.

Nếu công việc cần chạy sau startup, hãy tổ chức thành bean khác được inject và gọi qua proxy, xác định chính xác security context của tác vụ. `CommandLineRunner` trong demo chạy sau khi context khởi tạo, nhưng nó tự dựng authentication **chỉ để minh họa**.

### 11.3. Non-HTTP entry points

Method Security có thể bảo vệ lời gọi từ job, message listener hoặc component nội bộ **nếu** chúng gọi Spring-managed bean qua proxy và có authentication/policy phù hợp. Không có request HTTP không đồng nghĩa tự có người dùng hiện tại; job chạy nền cần chính sách service-account hoặc identity rõ ràng.

## 12. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `@PreAuthorize` bị bỏ qua mọi nơi | Chưa bật `@EnableMethodSecurity`; bean không được scan | Kiểm tra config và test qua context |
| Chỉ lời gọi từ một số nơi bị bỏ qua | `this.method()`, tạo object bằng `new` | Kiểm tra call graph; tách bean hoặc gọi qua bean proxy |
| Gắn annotation vào `private` method nhưng không có hiệu lực | Không thể intercept qua subclass AOP proxy | Chuyển ranh giới bảo mật lên public service method |
| Annotation ở `final` method/class không hoạt động khi dùng CGLIB | Không thể override/subclass | Bỏ `final` ở ranh giới proxy hoặc thiết kế interface phù hợp |
| Tiêm implementation class thất bại khi JDK proxy | Đối tượng proxy chỉ triển khai interface | Tiêm qua interface hoặc cấu hình proxy class khi phù hợp |
| Dùng `@Secured`/`@RolesAllowed` mà không chạy | Chưa bật `securedEnabled`/`jsr250Enabled` | Bật tùy chọn đúng và test annotation đó |
| Bị từ chối dù có role được mong đợi | Nhầm `ROLE_ADMIN` với `ADMIN`, sai authority hoặc context | Kiểm tra `GrantedAuthority` thực tế và SpEL |
| Hoạt động khi gọi trực tiếp, thất bại trong async | Security context không được truyền sang thread mới | Dùng cơ chế delegation và test async end-to-end |
| Transaction không mở ở lời gọi nội bộ | Bypass transaction proxy qua self-invocation | Tách bean và kiểm tra transaction thực tế |
| Unit test xanh nhưng production lộ quyền | Test gọi `new Service()` hoặc mock bỏ advisor | Thêm integration test `@SpringBootTest` + `@WithMockUser` |
| HTTP 403 và 401 không như kỳ vọng | Cấu hình entry point/exception translation khác nhau | Kiểm tra authentication và web error handling |
| `hasPermission` hoặc biểu thức bean lỗi | Thiếu evaluator/bean, sai tên tham số hoặc SpEL | Kiểm tra expression handler, `@P`, source dữ liệu và test deny |

### Checklist điều tra tối thiểu

1. **Bean:** `AopUtils.isAopProxy(service)` có `true`? Nếu `false`, xem bean có trong context và method có annotation được bật hay không.
2. **Đường gọi:** caller giữ bean do Spring inject hay `new` thủ công? Có `this.protectedMethod()` trong cùng class không?
3. **Kiểu proxy:** `AopUtils.isJdkDynamicProxy`/`isCglibProxy`; method có `private`/`final`/`static` hoặc chỉ có trên implementation không?
4. **Annotation:** `@EnableMethodSecurity` ở config thực sự được load? Có tắt `prePostEnabled` hay quên bật `securedEnabled`/`jsr250Enabled` không?
5. **Authentication:** `Authentication` có đúng principal và authorities? Có chuyển thread/context?
6. **Test:** một user có quyền phải qua; một user không quyền phải bị `AccessDeniedException`; phương thức không được tạo side effect khi bị chặn.
7. **Giao dịch và dữ liệu:** ownership/ACL ở DB có được kiểm tra ở thời điểm ghi hay không?

`AopUtils.isAopProxy(service) == true` chỉ chứng minh **bean có AOP proxy**, không chứng minh từng protected method hoặc từng đường gọi đã được bảo vệ. Một bean có thể được proxy do `@Transactional`/logging thay vì Method Security. Phải xác nhận bằng test **cho phép và từ chối đúng method**; log advisor/debug có thể hỗ trợ nhưng không thay thế test kết quả.

## 13. Kiến thức kiểm tra nhanh

1. **Thêm `spring-boot-starter-security` có tự bật `@PreAuthorize` không?**  
   Không. Thông thường phải có `@EnableMethodSecurity` hoặc cấu hình tương đương.

2. **Một service là `@Service` nhưng tạo bằng `new` có được method security bảo vệ không?**  
   Không. Object do `new` thủ công không phải bean proxy mà Spring đã cấu hình.

3. **Vì sao `this.adminOnly()` nguy hiểm?**  
   Vì lời gọi nội bộ không đi qua proxy để chạy interceptor của `adminOnly`.

4. **Chuyển từ JDK proxy sang CGLIB có khắc phục self-invocation không?**  
   Không. Cả hai vẫn là cơ chế proxy, không tự chặn `this.method()`.

5. **Vì sao method `final` có thể làm hỏng bảo vệ bằng CGLIB?**  
   Proxy subclass không override được method `final`.

6. **`@PreAuthorize` và `@PostAuthorize` khác nhau ở đâu?**  
   Một bên kiểm tra trước thân method, bên kia kiểm tra sau method và có thể đọc `returnObject`.

7. **Có thể dùng Method Security trong job không có HTTP request không?**  
   Có, nếu job gọi qua proxy và có authentication/policy tương ứng.

8. **`@Transactional` có làm `@PreAuthorize` trở nên không cần thiết không?**  
   Không. Transaction quản lý tính nhất quán/rollback; authorization quyết định ai được phép thao tác. Cả hai có ranh giới proxy và cần kiểm thử phối hợp.

9. **Nếu `isAopProxy(service)` trả `true` thì có chắc method đó an toàn không?**  
   Không. Còn phải xác minh annotation đúng, method intercept được, đường gọi qua proxy và quyết định quyền đúng.

10. **Cách sửa dễ bảo trì cho self-invocation?**  
    Chuyển protected method sang service bean riêng và inject bean đó vào caller, sau đó thêm integration test cho trường hợp thiếu quyền.

## 14. Tài liệu tham khảo chính thức

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): bật `@EnableMethodSecurity`, interceptors, annotation, cấu hình advisor và AspectJ mode.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK proxy, CGLIB, `final`/`private`, self-invocation và các cách xử lý.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): khái niệm proxy trong Spring AOP.
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` và kiểm thử method authorization.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): truyền `SecurityContext` qua thread/executor.
- [Spring Boot 3.5.8 release](https://spring.io/blog/2025/11/20/spring-boot-3-5-8-available-now/): thông tin phiên bản được dùng trong ví dụ.

**Kết luận cần nhớ:** một annotation Method Security chỉ bảo vệ lời gọi khi hạ tầng được bật, bean và method phù hợp, đường gọi đi qua proxy có advisor tương ứng và điều kiện quyền được đánh giá với authentication đúng. **Self-invocation là giới hạn quan trọng của Spring AOP proxy**; hãy thiết kế ranh giới service và test ở đường gọi thực tế, đồng thời bảo vệ thao tác ghi ở tầng dữ liệu khi cần.