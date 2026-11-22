# Spring AOP proxy và nguy cơ bỏ qua kiểm tra khi tự gọi phương thức

## 1. Vấn đề: annotation có nhưng kiểm tra quyền vẫn không chạy

Spring Security cho phép bảo vệ lời gọi phương thức bằng các annotation như **@PreAuthorize**, **@PostAuthorize**, **@Secured** hoặc **@RolesAllowed**. Khi dùng **@EnableMethodSecurity** trong cấu hình mặc định, những kiểm tra này được thực hiện thông qua cơ chế **Spring AOP proxy**. Điều đó có một giới hạn kiến trúc quan trọng:

**Lời gọi đến phương thức được bảo vệ đi qua Spring proxy có thể kích hoạt kiểm tra quyền. Lời gọi từ một phương thức sang phương thức khác ngay trong cùng đối tượng bằng this hoặc gọi ngầm không qua proxy, vì thế không kích hoạt advice của phương thức được gọi.**

Xét tình huống sau:

~~~java
@Service
class ReportService {

    public String readFromController() {
        return this.readSensitiveReport();
    }

    @PreAuthorize("hasAuthority('report:read')")
    public String readSensitiveReport() {
        return "confidential-report";
    }
}
~~~

Đây là fragment minh họa, giả định đã bật @EnableMethodSecurity và lớp được Spring quản lý. Nếu một controller gọi **reportService.readSensitiveReport()** trên bean đã được proxy hóa, Spring Security có thể từ chối người thiếu quyền. Nhưng nếu controller gọi **reportService.readFromController()**, rồi method này gọi **this.readSensitiveReport()**, việc kiểm tra ở **@PreAuthorize của readSensitiveReport** bị bỏ qua trong cấu hình proxy thông thường.

Điều này dễ tạo ra **lỗ hổng phân quyền** nếu một phương thức chỉ dựa vào annotation ở method bên trong để bảo vệ dữ liệu. Đây là đặc tính chung của Spring AOP proxy, có thể ảnh hưởng tới @Transactional và @Cacheable, nhưng bài tập trung vào tác động bảo mật của method security.

Sau bài này, bạn sẽ:
- Phân biệt **proxy object**, **target object**, **advice** và **method interceptor**.
- Hiểu vì sao **self-invocation** bỏ qua bảo vệ ở phương thức được gọi.
- Nhận biết tình huống qua kết quả HTTP **200/401/403**.
- Tổ chức lại các Spring bean để kiểm tra quyền chạy đúng trên mọi đường gọi.
- Viết test kiểm tra cả đường gọi trực tiếp qua proxy và đường gọi gián tiếp.
- Phân biệt giới hạn self-invocation với vấn đề **private/final method**, bean tạo thủ công và việc chưa bật method security.

## 2. Cách method security hoạt động với Spring AOP

### 2.1. Bật method security không phải mặc định của Spring Boot Starter Security

Thêm dependency **spring-boot-starter-security** sẽ bật cơ chế bảo mật HTTP mặc định của Spring Boot, nhưng **không tự kích hoạt annotation-level method security**. Với Spring Security 6.x, cách phổ biến để bật là:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Hoặc đặt **@EnableMethodSecurity** trên một class cấu hình khác, kể cả lớp ứng dụng chính. Trong cấu hình mặc định, annotation này kích hoạt các interceptor liên quan đến **@PreAuthorize**, **@PostAuthorize**, **@PreFilter** và **@PostFilter**. Các nhóm như @Secured hoặc JSR-250 cần tùy chọn bật tương ứng khi sử dụng.

**@EnableMethodSecurity** hoạt động trên những đối tượng được Spring quản lý trong ApplicationContext. Nếu một đối tượng được tạo bằng **new ReportService()** bên ngoài container, Spring không có cơ hội thay đối tượng đó bằng proxy method-security.

### 2.2. Proxy là đối tượng được các bean khác gọi tới

Một bean có method cần bảo vệ có thể được Spring bọc bằng proxy. Phần gọi qua proxy được Spring AOP chặn và đưa qua các interceptor. Đối với @PreAuthorize, Spring Security dùng interceptor trước lời gọi method để đánh giá biểu thức quyền dựa trên Authentication hiện tại.

~~~text
Controller / Service khác
         |
         | gọi reportService.readSensitiveReport()
         v
Spring AOP proxy của ReportService
         |
         +--> Advisor / Method Security interceptor
         |         |
         |         +--> Đọc @PreAuthorize
         |         +--> Lấy Authentication từ SecurityContext
         |         +--> So khớp authority
         |         |
         |         +--> Thiếu quyền: từ chối (method không chạy)
         |         +--> Đủ quyền: cho gọi target method
         |
         v
ReportService target.readSensitiveReport()
         |
         v
Giá trị trả về
~~~

**Advice** là hành vi bổ sung tại một điểm gọi phương thức. Với @PreAuthorize, advice thực hiện kiểm tra **trước** khi method target chạy; với @PostAuthorize có thể kiểm tra **sau** khi method trả về. Spring Security 6.x triển khai thông qua các AuthorizationManager và method interceptors.

Lời gọi qua proxy là điểm khởi đầu của kiểm tra. Vì vậy, việc chỉ nhìn thấy annotation trong source code **chưa đủ** để kết luận mọi đường gọi đều được bảo vệ.

### 2.3. Vì sao self-invocation lại khác?

~~~text
BÊN NGOÀI: Controller -> proxy -> readSensitiveReport()
                                   |
                                   +--> @PreAuthorize được chạy

NỘI BỘ: Controller -> proxy -> readFromController()
                                     |
                                     v
                                  target.readFromController()
                                     |
                                     v
                                  this.readSensitiveReport()
                                     |
                                     +--> KHÔNG đi lại qua proxy
                                     +--> KHÔNG chạy @PreAuthorize ở method đích
~~~

Sau khi lời gọi đi vào **target object**, tham chiếu **this** trỏ tới chính đối tượng đang thực thi method. Lời gọi **this.readSensitiveReport()** hoặc **readSensitiveReport()** trong cùng class không quay lại proxy bên ngoài. Do đó Spring AOP không có điểm để áp dụng interceptor của method đích.

Điều cần phân biệt:
- **Không phải @PreAuthorize ngừng hoạt động trên toàn bộ ứng dụng.** Lời gọi external vào đúng protected method vẫn được chặn.
- **Không phải người dùng đã được cấp quyền ngầm.** Đường gọi nội bộ chỉ đi vòng qua nơi kiểm tra quyền được đặt.
- **Không phải @EnableMethodSecurity(proxyTargetClass=true) khắc phục vấn đề.** Proxy dựa trên subclass cũng có giới hạn self-invocation trong mô hình Spring AOP proxy.
- **Không phải mọi self-invocation đều là lỗ hổng.** Rủi ro xuất hiện khi luồng gọi đến dữ liệu/thao tác nhạy cảm mà không có kiểm tra quyền tương đương ở các cổng truy cập có thể đến được.

## 3. JDK dynamic proxy và class-based proxy (CGLIB)

Spring AOP có hai mô hình proxy phổ biến:

| Đặc điểm | JDK dynamic proxy | Class-based proxy (CGLIB) |
| --- | --- | --- |
| Cơ chế | Proxy triển khai interface | Proxy sinh subclass của class |
| Thường dùng khi | Bean có interface thích hợp và không buộc class proxy | Bean không có interface phù hợp, hoặc cấu hình ép class proxy |
| Góc nhìn caller | Thường tiêm qua interface | Có thể tiêm theo class type |
| Tác động self-invocation | **Vẫn bỏ qua advice** khi target tự gọi method | **Vẫn bỏ qua advice** khi target tự gọi method |
| Giới hạn đáng chú ý | Chỉ phương thức thuộc các interface proxy được expose qua kiểu interface | Class final và method final/private không thể được subclass override để advice |

Bạn có thể thấy:
- **@EnableMethodSecurity(proxyTargetClass = true)** để yêu cầu class-based proxy cho method-security ở chế độ PROXY.
- Các cấu hình proxy toàn cục khác của Spring Boot/Spring Framework có thể ảnh hưởng loại proxy đang được tạo.
- **@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)** là một chế độ khác, nhưng đòi hỏi cách thiết lập AspectJ weaving tương ứng; không thể chỉ đổi cờ rồi giả định mọi lời gọi nội bộ sẽ được bảo vệ.

**Kết luận quan trọng:** chọn JDK proxy hay CGLIB không phải giải pháp cho self-invocation. Cách sửa thông thường là **sắp xếp lời gọi để phương thức nhạy cảm được gọi từ bean khác qua proxy**, hoặc đặt kiểm tra quyền tại điểm vào có thể truy cập.

## 4. Ví dụ đối chứng hoàn chỉnh bằng Spring Boot 3.x

Ta tạo ba đường dẫn chỉ để quan sát cơ chế:

1. **/lab/direct**: gọi trực tiếp phương thức có @PreAuthorize qua proxy.
2. **/lab/self**: gọi một phương thức công khai *không có annotation*, rồi phương thức đó gọi nội bộ method có annotation.
3. **/lab/fixed**: gọi một façade service, service này gọi phương thức có @PreAuthorize của **bean khác**.

Các endpoint /lab/** được **permitAll ở tầng HTTP** để làm nổi bật riêng tác động của **method security**. Trong ứng dụng thực tế, không nên để những route nhạy cảm chỉ dựa vào một tầng bảo vệ bị cấu hình sai.

### 4.1. Tạo project

Dùng Spring Initializr tạo project Gradle với:
- Java 17 hoặc mới hơn, Spring Boot **3.x**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependency **Spring Web** (spring-boot-starter-web).
- Dependency **Spring Security** (spring-boot-starter-security).

Tên class chính bên dưới là **MethodSecurityProxyDemoApplication**. Đặt cả mã trong đúng một file:

**src/main/java/com/example/demo/MethodSecurityProxyDemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityProxyDemoApplication.class, args);
    }
}

@Configuration
class HttpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        // Demo: permitAll để nhìn rõ method security.
                        .requestMatchers("/lab/**").permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .authorities("report:read")
                .build();

        return new InMemoryUserDetailsManager(viewer, reader);
    }
}

@Service
class VulnerableReportService {

    // Khi gọi từ bean khác qua Spring proxy, method này được bảo vệ.
    @PreAuthorize("hasAuthority('report:read')")
    public String readProtectedReport() {
        return "sensitive-report";
    }

    // Method này không có quy tắc kiểm tra quyền.
    public String readBySelfInvocation() {
        // Cùng một target object: bỏ qua advice của readProtectedReport.
        return this.readProtectedReport();
    }
}

@Service
class ProtectedReportReader {

    // Điểm bảo vệ nằm trên bean riêng.
    @PreAuthorize("hasAuthority('report:read')")
    public String readProtectedReport() {
        return "sensitive-report";
    }
}

@Service
class SafeReportFacade {

    private final ProtectedReportReader protectedReader;

    SafeReportFacade(ProtectedReportReader protectedReader) {
        this.protectedReader = protectedReader;
    }

    public String readViaOtherBean() {
        // Đây là lời gọi đến proxy của bean khác.
        return protectedReader.readProtectedReport();
    }
}

@RestController
class LabController {

    private final VulnerableReportService vulnerableService;
    private final SafeReportFacade safeFacade;

    LabController(VulnerableReportService vulnerableService,
            SafeReportFacade safeFacade) {
        this.vulnerableService = vulnerableService;
        this.safeFacade = safeFacade;
    }

    @GetMapping("/lab/direct")
    String direct() {
        return vulnerableService.readProtectedReport();
    }

    @GetMapping("/lab/self")
    String self() {
        return vulnerableService.readBySelfInvocation();
    }

    @GetMapping("/lab/fixed")
    String fixed() {
        return safeFacade.readViaOtherBean();
    }
}
~~~

**Vì sao code có thể chạy trong một tệp?** Chỉ MethodSecurityProxyDemoApplication là public top-level class, tên class trùng tên file; các class còn lại là package-private nhưng được Spring component scan khi khởi động ứng dụng trong cùng package. Các method được bảo vệ đều **public**, class không final và là Spring bean nên có thể được proxy hóa.

**Không có lớp Service tự tạo bằng new** trong ví dụ. Spring tiêm các dependency qua constructor, vì thế controller nắm tham chiếu tới bean/proxy do container cung cấp.

**Mật khẩu {noop}** chỉ để minh họa chạy cục bộ; không dùng cho production. Demo chỉ sử dụng GET, nên CSRF mặc định không cản các ca kiểm tra. Trong ví dụ này, HTTP Basic được bật để curl gửi danh tính viewer/reader rõ ràng.

### 4.2. Chạy và gửi request

Trong thư mục gốc của dự án vừa tạo:

~~~bash
./gradlew bootRun
~~~

Với Windows dùng **gradlew.bat bootRun**. Khi ứng dụng đang chạy ở cổng mặc định **8080**, mở terminal khác:

~~~bash
# Người thiếu quyền gọi thẳng method được bảo vệ
curl -i -u viewer:demo123 http://localhost:8080/lab/direct

# Người thiếu quyền đi qua phương thức tự gọi nội bộ
curl -i -u viewer:demo123 http://localhost:8080/lab/self

# Người thiếu quyền đi qua bản sửa gọi bean khác
curl -i -u viewer:demo123 http://localhost:8080/lab/fixed

# Người có authority report:read
curl -i -u reader:demo123 http://localhost:8080/lab/direct
curl -i -u reader:demo123 http://localhost:8080/lab/fixed

# Không gửi credentials: so sánh direct và self
curl -i http://localhost:8080/lab/direct
curl -i http://localhost:8080/lab/self
~~~

Trong PowerShell có thể phải dùng **curl.exe** thay **curl**.

### 4.3. Kết quả dự kiến và điều cần rút ra

| Request | HTTP status dự kiến | Body thành công | Lý do |
| --- | --- | --- | --- |
| viewer -> GET /lab/direct | **403** | — | Gọi qua proxy; viewer chỉ có ROLE_USER, thiếu report:read. |
| viewer -> GET /lab/self | **200** | sensitive-report | Method ngoài không bảo vệ; lời gọi nội bộ bỏ qua @PreAuthorize. |
| viewer -> GET /lab/fixed | **403** | — | Facade gọi proxy của ProtectedReportReader; thiếu quyền nên bị từ chối. |
| reader -> GET /lab/direct | **200** | sensitive-report | Có report:read; interceptor cho phép. |
| reader -> GET /lab/fixed | **200** | sensitive-report | Có report:read và lời gọi đi qua proxy. |
| anonymous -> GET /lab/direct | **401** với Basic | — | Method security từ chối; Basic entry point yêu cầu xác thực. |
| anonymous -> GET /lab/self | **200** | sensitive-report | Self-invocation bỏ qua kiểm tra, dù không có danh tính. |

Đây là **kết quả mong đợi từ cấu hình trong ví dụ**, không phải stdout hoặc HTTP log của một lần chạy thực tế. Header và response error body tùy phiên bản/cấu hình, nhưng sự khác biệt giữa hai đường gọi khi thiếu quyền chính là bằng chứng cần quan sát.

**Tại sao permitAll không ngăn được @PreAuthorize?** permitAll ở URL layer cho phép request đi đến controller. Nếu controller đi qua proxy của method được bảo vệ, method security thực hiện thêm một kiểm tra độc lập. **permitAll không làm @PreAuthorize mất hiệu lực**; việc tự gọi method bên trong target mới làm interceptor bị bỏ qua.

**Tại sao đây là vấn đề an ninh?** Người không đủ quyền có thể truy cập dữ liệu mà developer tưởng đã đặt sau @PreAuthorize. Trong ví dụ, response "sensitive-report" là chuỗi minh họa, không chứa dữ liệu thật. Trong hệ thống thực, cùng kiểu code có thể dẫn đến trả về dữ liệu nội bộ, xuất báo cáo nhạy cảm hoặc thay đổi trạng thái trái phép.

### 4.4. Đổi sang CGLIB có giúp không?

Không. Nếu đổi cấu hình thành:

~~~java
@EnableMethodSecurity(proxyTargetClass = true)
~~~

thì cơ chế proxy tạo theo class được yêu cầu trong chế độ PROXY, nhưng phương thức **readBySelfInvocation()** vẫn gọi **this.readProtectedReport()** trên target. Spring AOP không quay lại proxy cho lần gọi nội bộ, nên vẫn không thực thi advice ở readProtectedReport.

Cách sửa không nằm ở việc chọn loại proxy; nó nằm ở đường đi của lời gọi và vị trí kiểm tra quyền.

## 5. Sửa đúng: tách phương thức được bảo vệ sang bean riêng

Cách khuyến nghị trong code thông thường là phân tách trách nhiệm để phương thức cần bảo vệ có **đường gọi từ bean khác qua Spring proxy**:

~~~text
Controller
    |
    v
SafeReportFacade (Spring bean)
    |
    | protectedReader.readProtectedReport()
    v
ProtectedReportReader proxy
    |
    +--> @PreAuthorize("hasAuthority('report:read')")
              |
              +--> viewer / anonymous: từ chối
              +--> reader: cho phép
    |
    v
ProtectedReportReader target
    |
    v
Kết quả báo cáo
~~~

Điểm quan trọng của refactor:
1. **ProtectedReportReader** sở hữu phương thức nhạy cảm và annotation kiểm tra quyền.
2. **SafeReportFacade** chỉ điều phối luồng xử lý, nhận **ProtectedReportReader qua constructor injection**.
3. Caller không tự tạo object protectedReader bằng new; Spring cung cấp bean phù hợp (có proxy khi advisor áp dụng).
4. Mọi điểm sử dụng chức năng nhạy cảm đều gọi phương thức public đã bảo vệ qua bean được tiêm, hoặc thực thi kiểm tra quyền tương đương tại cổng vào.

Đây là lý do ví dụ có **SafeReportFacade** và **ProtectedReportReader** thay vì một class gọi chéo các method qua this.

### 5.1. Có thể chỉ thêm @PreAuthorize lên phương thức ngoài?

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readBySelfInvocation() {
    return this.readProtectedReport();
}
~~~

Nếu một caller bên ngoài gọi **readBySelfInvocation()** qua proxy, interceptor ở phương thức ngoài sẽ yêu cầu report:read trước khi cho vào. Với **đúng đường vào đó**, kiểm tra có tác dụng.

Tuy nhiên, **lời gọi vào readProtectedReport() từ bên trong vẫn không chạy interceptor riêng của readProtectedReport()**. Nếu một ngày có phương thức wrapper khác không được bảo vệ hoặc yêu cầu quyền yếu hơn, rủi ro sẽ quay lại. Do đó, cần rà soát **tất cả entry point**, không chỉ gắn annotation để làm một test đơn lẻ thành công.

### 5.2. Đừng phá thiết kế bằng cách tiêm chính mình một cách tùy tiện

Có những cách kỹ thuật để đi vòng qua giới hạn:

- **Self injection:** một bean giữ tham chiếu đến proxy của chính nó rồi gọi qua tham chiếu proxy, nhưng dễ gây vòng phụ thuộc, phụ thuộc lifecycle và khiến source khó theo dõi.
- **AopContext.currentProxy():** có thể truy cập proxy hiện tại trong điều kiện đã cấu hình exposeProxy, nhưng làm mã nghiệp vụ phụ thuộc trực tiếp Spring AOP; tài liệu Spring Framework không khuyến khích làm mặc định.
- **AspectJ compile-time/load-time weaving:** khác proxy-based AOP, có thể intercept lời gọi nội bộ vì advice được dệt vào bytecode; đổi lại thêm cấu hình, tooling và yêu cầu kiểm thử.

Trong phần lớn service nghiệp vụ, **tách thành bean bảo vệ riêng** hoặc **đặt kiểm tra quyền tại entry point rõ ràng** dễ hiểu, dễ test và ít phụ thuộc cơ chế proxy hơn.

## 6. Kiểm thử hồi quy: phát hiện đường bypass chứ không chỉ kiểm tra annotation

Nếu chỉ test rằng **viewer gọi /lab/direct nhận 403**, chưa đủ: endpoint /lab/self có thể đang trả dữ liệu nhạy cảm. Test cần bao phủ **mọi đường thực tế đến thao tác**, đặc biệt các method orchestration cùng class.

### 6.1. Test tích hợp với MockMvc

Thêm dependency test nếu dự án chưa có (Gradle Groovy DSL):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là fragment đặt trong **build.gradle**, không phải build.gradle đầy đủ; tránh khai báo trùng dependency đã được Spring Initializr tạo. Tạo file:

**src/test/java/com/example/demo/MethodSecurityProxyDemoTest.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityProxyDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void directCallRejectsUserWithoutAuthority() throws Exception {
        mvc.perform(get("/lab/direct")
                    .with(httpBasic("viewer", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void internalSelfCallShowsTheBypass() throws Exception {
        mvc.perform(get("/lab/self")
                    .with(httpBasic("viewer", "demo123")))
                .andExpect(status().isOk())
                .andExpect(content().string("sensitive-report"));
    }

    @Test
    void refactoredCrossBeanCallRejectsUserWithoutAuthority()
            throws Exception {
        mvc.perform(get("/lab/fixed")
                    .with(httpBasic("viewer", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void refactoredCrossBeanCallAllowsReader() throws Exception {
        mvc.perform(get("/lab/fixed")
                    .with(httpBasic("reader", "demo123")))
                .andExpect(status().isOk())
                .andExpect(content().string("sensitive-report"));
    }
}
~~~

**Chạy test** từ thư mục dự án:

~~~bash
./gradlew test
~~~

Với Windows dùng **gradlew.bat test**. Khi dùng Java 17+, dependency Spring Boot và Security đúng phiên bản tương thích, bốn test minh họa các trạng thái dự kiến của bài.

**Test thứ hai cố tình xác nhận một hành vi không an toàn** để chứng minh lỗi. Khi sửa code thực tế, không được giữ kiểu test này làm tiêu chí “đúng sản phẩm”. Hãy đổi kỳ vọng thành 403/401 theo chính sách khi đường vào được bảo vệ, hoặc xóa endpoint không an toàn và viết test cho toàn bộ entry point hợp lệ. Kiểm thử chức năng chỉ có giá trị khi kỳ vọng phản ánh chính sách an toàn.

### 6.2. Test trực tiếp bean được tiêm, đừng new service trong test

Một lỗi kiểm thử phổ biến là:

~~~java
VulnerableReportService service = new VulnerableReportService();
service.readProtectedReport();
~~~

Object này chưa qua Spring container và proxy; test đó **không chứng minh method security hoạt động**. Muốn kiểm tra interceptor, dùng test có Spring ApplicationContext và tiêm bean:

~~~java
@Autowired
VulnerableReportService vulnerableService;
~~~

Sau đó thiết lập Authentication phù hợp, gọi qua bean đã tiêm và kiểm tra exception khi thiếu quyền. Với MockMvc và Basic từ ví dụ, ta còn xác minh được các response 200/403 của HTTP entry point.

Trong test service trực tiếp, có thể dùng **@WithMockUser(authorities = "report:read")** (khi có spring-security-test) để tạo SecurityContext. Khi test tình huống thiếu quyền, dùng authorities khác hoặc user không có authority cần thiết. Với JUnit test chạy nhiều luồng hoặc Reactor pipeline, cần thiết lập security context đúng cơ chế thay vì dựa vào ThreadLocal tùy tiện.

## 7. Các tình huống khác cũng khiến annotation không được thực thi

### 7.1. Đối tượng không do Spring quản lý

~~~java
ReportService service = new ReportService();
service.sensitive();
~~~

Mã này chỉ là ví dụ tổng quát. Nếu ReportService được tạo bằng new ở ngoài Spring, method security proxy không xuất hiện. **@Service** ghi trên class cũng không tự biến một instance tạo thủ công thành bean.

### 7.2. private, final và lớp không thể proxy

Với **class-based proxy**, các method **private** hoặc **final** không thể được override để Spring AOP gắn advice; class **final** không thể được subclass proxy. Đây là những điều kiện phải xét khi kiểm tra method security.

Thực hành an toàn trong các bean cần bảo vệ:
- Dùng **public** method rõ ràng làm cổng truy cập bảo mật.
- Không giả định @PreAuthorize trên **private helper** sẽ chặn lời gọi từ method khác cùng class.
- Với Kotlin, chú ý class/method final theo mặc định; cần cấu hình mở cho proxy tương ứng (ví dụ plugin all-open trong dự án phù hợp).
- Khi bean triển khai interface và proxy theo JDK, cân nhắc khả năng method được expose qua interface và nơi đặt annotation; xác minh bằng test, không chỉ nhìn tên class.

### 7.3. Constructor, @PostConstruct và giai đoạn khởi tạo

Khi object đang được tạo, quá trình xây dựng proxy có thể chưa hoàn tất. Không nên trông đợi method được gọi từ constructor, initializer hoặc lifecycle callback bên trong chính bean sẽ chịu method security như lời gọi external qua proxy. Tách logic khởi tạo khỏi các thao tác bảo vệ; test đường gọi sau khi bean đã được container cấp.

### 7.4. Bất kỳ annotation proxy nào cũng có thể bị ảnh hưởng

Một self-call có thể bỏ qua **@Transactional**, **@Cacheable**, **@Async** hoặc advice tùy chỉnh, tùy cách các khả năng đó được cấu hình. Chẳng hạn method A trong cùng bean gọi this.methodB() với @Transactional trên B thì transaction advice trên B có thể không chạy.

Tuy nhiên, không đánh đồng hậu quả: method-security bypass có thể dẫn tới **đọc/sửa tài nguyên trái phép**; transaction proxy bị bỏ qua có thể gây sai transaction boundary. Cùng nguyên nhân AOP nhưng mức độ rủi ro và cách kiểm thử khác nhau.

### 7.5. Method security không thay thế hoàn toàn URL security

Cấu hình cho HTTP và method có phạm vi khác nhau:

| Tầng | Ví dụ | Tác dụng |
| --- | --- | --- |
| HTTP request | requestMatchers("/reports/**").hasAuthority("report:read") | Bảo vệ nhóm request trước controller |
| Method | @PreAuthorize("hasAuthority('report:read')") | Bảo vệ lời gọi method được Spring proxy intercept |
| Nghiệp vụ dữ liệu | Kiểm tra user có thuộc tenant/owner của báo cáo hay không | Ngăn truy cập bản ghi ngoài phạm vi quyền |

Nếu URL layer đã chặn chắc chắn người không có quyền, có thể demo self-call không lộ qua route đó. Tuy nhiên, service còn có thể được gọi từ controller khác, scheduled jobs, message consumers hoặc luồng nội bộ. Vì vậy, khi có yêu cầu bảo vệ logic nghiệp vụ ở method, đừng coi cấu hình HTTP che được mọi lỗi self-invocation trong tầng service.

Method security cũng không mặc nhiên kiểm tra **ownership/tenant/resource state**. Điều kiện dựa trên thông tin tài nguyên có thể cần biểu thức authorization có tham số, AuthorizationManager riêng hoặc kiểm tra ở service tương ứng.

## 8. Cách chẩn đoán khi @PreAuthorize không hoạt động

Khi gặp một method có @PreAuthorize nhưng người thiếu quyền vẫn truy cập được, xem lần lượt:

1. **@EnableMethodSecurity đã bật chưa?** Spring Boot Starter Security không tự bật annotation method security.
2. **Đối tượng có phải bean được Spring quản lý không?** Instance được tạo bằng new không có proxy.
3. **Caller có thật sự cầm proxy không?** Với bean injection, kiểm tra loại bean tại runtime.
4. **Có self-invocation không?** Tìm các lời gọi dạng **this.sensitive()**, **sensitive()** trong cùng class hoặc method wrapper công khai.
5. **Method có thể được intercept không?** Cân nhắc private/final, kiểu proxy, interface, visibility, cấu trúc bean.
6. **Annotation nằm đúng nơi không?** Kiểm tra method thực tế đang được gọi, meta-annotation và các cấu hình quyền hiện hành.
7. **Authentication có authority gì?** So sánh chuỗi role/authority chính xác; hasRole mặc định liên quan ROLE_.
8. **Có nhiều đường truy cập cùng chức năng?** Rà soát controller, events, service khác, scheduler và background jobs.
9. **Có kiểm tra ở tầng khác làm sai lệch kết quả test không?** URL authorization, CSRF hoặc authentication entry point có thể từ chối trước khi đến method.

### 8.1. Kiểm tra bean có phải Spring proxy không

Trong đoạn kiểm tra chạy **bên trong Spring ApplicationContext**, bạn có thể dùng:

~~~java
import org.springframework.aop.support.AopUtils;

// Ví dụ fragment: service được @Autowired từ Spring.
boolean isProxy = AopUtils.isAopProxy(service);
System.out.println("Spring AOP proxy: " + isProxy);
~~~

**AopUtils.isAopProxy** chỉ hỗ trợ xác minh đối tượng có được AOP proxy hóa; việc là proxy **không chứng minh mọi lời gọi** đến mọi method đều được advice. Thao tác quan trọng vẫn là test các đường truy cập và các trường hợp không đủ quyền.

Nếu muốn xem class name thật, dùng **service.getClass().getName()** trong test môi trường phát triển; với class-based proxy có thể thấy tên chứa dấu hiệu proxy. Không viết test phụ thuộc vào chuỗi tên proxy cụ thể vì đó là chi tiết triển khai.

### 8.2. Logging và phép thử có kiểm soát

Trong môi trường phát triển, có thể bật tạm:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.aop=DEBUG
~~~

Nhưng log chỉ giúp quan sát, không thay thế test. Tránh log password, session cookie, access token hoặc dữ liệu nhạy cảm. Test quan trọng nhất là **người thiếu quyền gọi qua từng entry point đều bị chặn**, không chỉ một method mẫu được gọi đúng cách.

## 9. Với Spring WebFlux và reactive method security

Spring WebFlux có cơ chế HTTP security riêng (ServerHttpSecurity, SecurityWebFilterChain). Với **reactive method security**, ứng dụng thường bật **@EnableReactiveMethodSecurity** và dùng kiểu trả về reactive như Mono/Flux, để authorization được đưa vào pipeline reactive với Reactor Context.

**Giới hạn proxy self-invocation vẫn là vấn đề cần rà soát khi cấu hình theo AdviceMode.PROXY.** Không copy @EnableMethodSecurity của servlet rồi mặc định mọi phép kiểm tra reactive đã hoạt động đúng. Đồng thời không đọc Authentication từ ThreadLocal của servlet như cách duy nhất trong reactor pipeline.

Với ứng dụng reactive, các bước kiểm tra vẫn tương tự về mặt kiến trúc: Spring bean, caller giữ proxy, lời gọi qua proxy, authority đúng, test đường self-call và test publisher sau khi subscribe/StepVerifier. Mỗi stack cần kiểm thử dựa trên API và security context của chính nó.

## 10. Quy trình review thực tế cho service nhạy cảm

Khi review một chức năng như **exportReport**, **approvePayment**, **deleteUser** hoặc **readPrivateDocument**, hãy trả lời:

- **Ai có thể kích hoạt thao tác?** Liệt kê HTTP route, scheduled job, queue consumer và service caller.
- **Điểm kiểm tra quyền nằm ở đâu?** URL policy, method annotation hoặc check nghiệp vụ.
- **Lời gọi có đi qua Spring proxy không?** Quan sát bean wiring và call graph, tìm self-invocation.
- **Có đường gọi gián tiếp nào không được chú ý?** Method helper public không annotation gọi method có annotation trong cùng class.
- **Quyền được kiểm tra đã đủ chặt chưa?** Authority, role, tenant, ownership và trạng thái tài nguyên.
- **Mỗi đường truy cập có negative test chưa?** Đặc biệt dùng user đã xác thực nhưng thiếu authority tương ứng.
- **Có giải pháp rõ ràng nếu bypass không?** Ưu tiên tách bean theo trách nhiệm bảo mật, test lại tất cả entry point.

### Tình huống trước và sau khi sửa

**Trước:** Controller -> ReportService.readForDashboard() -> this.readConfidentialData() (@PreAuthorize). Caller thiếu quyền có thể chạm tới dữ liệu do method đích không qua proxy.

**Sau:** Controller -> DashboardService.read() -> SecuredReportReader.readConfidentialData() (@PreAuthorize). Lời gọi xuyên bean đi qua proxy, quyền được kiểm tra trước khi đọc dữ liệu.

Dù cấu hình đã sửa, nên kiểm thử cả route công khai, route bị chặn, role hợp lệ và thiếu role. Trong production, không để một đoạn dữ liệu bí mật chỉ được bảo vệ bằng giả định rằng “annotation chắc chắn luôn chạy” khi source chứa lời gọi nội bộ.

## 11. Câu hỏi tự đánh giá

1. **@EnableMethodSecurity** dùng để làm gì? Vì sao chỉ thêm spring-boot-starter-security chưa đủ?
2. **Proxy** và **target** có vai trò khác nhau gì khi thực thi @PreAuthorize?
3. Vì sao Controller gọi bean.sensitive() có thể được chặn, nhưng bean.doWork() gọi this.sensitive() lại không?
4. Nếu đổi sang **proxyTargetClass=true**, self-invocation có tự được sửa không? Giải thích đường đi của lời gọi.
5. Trong demo, tại sao **viewer -> /lab/direct** nhận 403 còn **viewer -> /lab/self** nhận 200?
6. Vì sao tách method có @PreAuthorize sang **ProtectedReportReader** làm lời gọi từ **SafeReportFacade** được kiểm tra?
7. Khi nào thêm @PreAuthorize cho wrapper bên ngoài có tác dụng, và vì sao vẫn phải rà soát những entry point khác?
8. Test trực tiếp new ReportService() có chứng minh Spring method security hoạt động không?
9. Các phương thức **private/final** có hạn chế gì với class-based proxy?
10. Khi xử lý report của nhiều tenant, chỉ cần @PreAuthorize("hasAuthority('report:read')") có đủ không? Cần kiểm tra thêm dữ liệu nào?
11. Nếu cùng một business method được gọi từ controller và message consumer, vì sao cần test cả hai đường?
12. Đối với Spring WebFlux, tại sao cần dùng cơ chế reactive security context và kiểm tra publisher thực tế?

**Ghi nhớ:** Spring Security method security ở chế độ Spring AOP proxy bảo vệ **lời gọi qua proxy**, không bảo vệ một method bằng cách tự động chặn tất cả lời gọi trực tiếp trong target. **Self-invocation có thể bỏ qua @PreAuthorize/@PostAuthorize** của phương thức đích. Khi có logic nhạy cảm, hãy bảo đảm có đường kiểm tra quyền rõ ràng, ưu tiên tách bean và gọi qua proxy, đồng thời viết **negative tests** cho mọi entry point.

## Tài liệu chính thức

- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 API — @EnableMethodSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html
- Spring Framework — Proxying Mechanisms, Self Invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
