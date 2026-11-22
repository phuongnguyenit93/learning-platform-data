# @EnableMethodSecurity và điều kiện để annotation có hiệu lực

> **Module:** Spring Security - fundamentals  
> **Nhóm:** Bảo vệ phương thức  
> **Câu hỏi trọng tâm:** Vì sao đặt `@PreAuthorize` lên một method vẫn có thể không chặn người thiếu quyền? Những điều kiện nào phải đúng để Spring Security thực sự kiểm tra lời gọi method?

## 1. Học xong bài này cần nắm được gì?

Bạn sẽ hiểu:

- Vai trò của `@EnableMethodSecurity` trong việc **kích hoạt cơ chế phân quyền ở mức phương thức** của Spring Security.
- Sự khác nhau giữa khai báo một annotation `@PreAuthorize` và việc annotation đó thực sự được **Spring Method Security interceptor thực thi**.
- Những điều kiện quan trọng: cấu hình được nạp vào ApplicationContext, đối tượng là Spring-managed bean, lời gọi đi qua proxy/advice, phương thức có thể được intercept và `Authentication`/`GrantedAuthority` đáp ứng điều kiện.
- Vì sao tự gọi method trong cùng class (`self-invocation`), dùng `new`, đặt annotation lên private/final method hoặc cấu hình sai tầng Servlet/WebFlux có thể dẫn tới mất hiệu lực mong đợi.
- Cách viết và chạy ví dụ Spring Boot với `@EnableMethodSecurity`, `@PreAuthorize`, `@WithMockUser` để kiểm chứng cả lời gọi được phép lẫn bị từ chối.
- Khi nào dùng `@PreAuthorize`, `@PostAuthorize`, `@Secured`, JSR-250 và `@EnableReactiveMethodSecurity`.

## 2. Method security bảo vệ điều gì?

**Method security** là kiểm soát truy cập khi gọi **phương thức của ứng dụng**. Ví dụ:

~~~java
@PreAuthorize("hasAuthority('report:publish')")
public String publishReport() {
    return "published";
}
~~~

Luật trên có nghĩa: *trước khi chạy thân method*, Spring Security cần quyết định principal hiện hành có authority `report:publish` hay không. Nếu không đạt, một interceptor phân quyền từ chối lời gọi, thường bằng một exception thuộc họ `AccessDeniedException`.

Phạm vi của method security khác với cấu hình quyền ở HTTP endpoint:

| Tầng | Ví dụ | Thời điểm kiểm tra |
| --- | --- | --- |
| HTTP request security | `requestMatchers("/reports/**").authenticated()` | Khi request đi qua security filter chain |
| Method security | `@PreAuthorize("hasAuthority('report:publish')")` | Khi method được gọi qua hạ tầng interceptor |
| Object-level authorization | `@PreAuthorize("@reportPolicy.canRead(authentication, #id)")` | Khi policy của method đánh giá chủ thể và tài nguyên |

Một endpoint có thể cho phép mọi người gọi tại tầng HTTP bằng `permitAll()` nhưng service được gọi bên dưới vẫn có `@PreAuthorize` và có thể từ chối. Ngược lại, method không được bảo vệ chỉ vì URL của một controller khác đã có `authenticated()`.

**Điểm mấu chốt:** Annotation phân quyền không phải lệnh Java được JVM tự kiểm tra. Nó là **metadata** để Spring Security cấu hình cơ chế chặn lời gọi. Nếu cơ chế đó không hoạt động hoặc lời gọi không đi qua nó, thân method có thể chạy bình thường.

## 3. `@EnableMethodSecurity` kích hoạt những thành phần nào?

Trong Spring Security 6, cách thông thường là đặt `@EnableMethodSecurity` trên một class cấu hình được Spring nạp:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Bạn cũng có thể đặt `@EnableMethodSecurity` trên class `@SpringBootApplication`, vì class đó là cấu hình Spring.

Đây là điểm dễ bỏ sót:

> **Chỉ thêm `spring-boot-starter-security` không tự động bật method security.** Bạn cần kích hoạt riêng bằng `@EnableMethodSecurity` (hoặc cấu hình tương đương).

Khi kích hoạt, Spring Security đăng ký hạ tầng advisors/interceptors cho annotation liên quan. Đối với `@PreAuthorize`, một interceptor dựa trên `AuthorizationManager` thực hiện quyết định trước lời gọi. Đối với `@PostAuthorize`, kiểm tra diễn ra sau khi method trả về. Trong chế độ proxy thông dụng, Spring AOP tạo/áp dụng proxy cho Spring bean phù hợp để lời gọi đi qua các interceptor này.

Khái quát:

~~~text
ApplicationContext nạp @EnableMethodSecurity
    |
    v
Đăng ký Method Security advisors/interceptors
    |
    v
Spring tạo bean cần bảo vệ và proxy phù hợp
    |
    v
Caller -> Spring bean proxy -> kiểm tra @PreAuthorize
                                   |
                         +---------+---------+
                         |                   |
                     GRANTED               DENIED
                         |                   |
                         v                   v
                  Thực thi method     AccessDeniedException
~~~

Không phải mọi lời gọi Java tới method có annotation đều đi qua đoạn kiểm tra. **Proxy/advice chính là ranh giới quyết định.**

### Mặc định các họ annotation

Các cờ quan trọng của `@EnableMethodSecurity`:

| Thuộc tính | Mặc định | Annotation ảnh hưởng |
| --- | --- | --- |
| `prePostEnabled` | `true` | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` |
| `securedEnabled` | `false` | `@Secured` |
| `jsr250Enabled` | `false` | `@RolesAllowed`, `@PermitAll`, `@DenyAll` của Jakarta annotations |

Do đó:

~~~java
@EnableMethodSecurity
~~~

đã đủ để dùng `@PreAuthorize`/`@PostAuthorize` trong cấu hình thông thường, nhưng nếu bạn muốn dùng `@Secured` hoặc `@RolesAllowed`, hãy bật rõ:

~~~java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Không cần bật tất cả họ annotation nếu dự án thống nhất sử dụng một họ duy nhất. Việc bật thêm họ annotation chỉ hợp lý khi thực sự dùng chúng, vì nhiều chính sách chồng lên nhau có thể khó kiểm soát.

## 4. Điều kiện cần để annotation **thực sự** có hiệu lực

Hãy xem đây là chuỗi các điều kiện cùng phải thỏa.

### Điều kiện 1: Cấu hình được Spring nạp vào đúng ApplicationContext

`@EnableMethodSecurity` phải nằm trên class cấu hình được quét hoặc import vào context đang chứa service cần bảo vệ. Nếu tạo file cấu hình bên ngoài phạm vi `@ComponentScan` mà không `@Import`/đăng ký, annotation không có tác dụng chỉ vì class tồn tại trong source.

Với Spring Boot, đặt cấu hình trong package gốc hoặc package con được scan, hoặc import tường minh. Đừng suy luận rằng một cấu hình ở module khác đã tự động có hiệu lực trong test slice hay ApplicationContext mới.

### Điều kiện 2: Đối tượng được Spring quản lý

Ví dụ đúng:

~~~java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "ok";
    }
}
~~~

Khi ứng dụng lấy `ReportService` từ Spring container (dependency injection, `ApplicationContext.getBean(...)`), container có cơ hội tạo proxy/interceptor để bảo vệ.

Ví dụ bỏ qua container:

~~~java
// Ví dụ sai nếu kỳ vọng Spring AOP bảo vệ lời gọi này:
ReportService service = new ReportService();
service.readReport();
~~~

Object tạo trực tiếp bằng `new` không phải proxy do Spring quản lý. Annotation vẫn tồn tại trong bytecode nhưng **không có method-security interceptor** đứng trước lời gọi đó.

### Điều kiện 3: Lời gọi đi qua proxy/advice

Trong chế độ proxy mặc định, lời gọi phải đi từ caller qua reference là **bean đã được Spring cung cấp**, không bypass proxy.

~~~text
Controller / Service khác
       |
       v
ReportService bean proxy
       |
       v
@PreAuthorize interceptor
       |
       v
ReportService target method
~~~

Nếu bean dùng JDK dynamic proxy, các method cần bảo vệ phải phù hợp với interface được proxy. Nếu dùng class-based proxy, các ràng buộc kế thừa/override của Java áp dụng: `final` class không thể được subclass; `final` method không thể được override. `private` method không thể được override để tạo advice theo cách class proxy thông thường. Đừng dựa vào annotation trên những method như vậy rồi kết luận “đã được bảo vệ”.

Spring Framework 6 có hỗ trợ intercept một số method non-public khi dùng class-based proxy trong các trường hợp phù hợp, nhưng **thiết kế dễ kiểm chứng nhất** cho bài học là bảo vệ public method của Spring-managed service được gọi qua proxy. Không khái quát rằng mọi method không public luôn được chặn hoặc luôn bị bỏ qua ở tất cả proxy mode.

### Điều kiện 4: Có ngữ cảnh xác thực tương ứng khi kiểm tra

`@PreAuthorize("hasAuthority('report:read')")` cần truy cập `Authentication` và các `GrantedAuthority` đang áp dụng. Hệ thống có thể có identity hợp lệ nhưng thiếu authority; lúc đó annotation **đã hoạt động đúng** khi từ chối.

Trường hợp chưa đăng nhập, ngữ cảnh có thể rỗng hoặc chứa anonymous authentication tùy cấu hình. Tùy đường gọi và exception translation, kết quả là lỗi/từ chối ở mức method hoặc HTTP response thích hợp. Không xem mọi lần nhận `403` là bằng chứng “annotation không hoạt động”.

**Đừng tự tạo authenticated token từ dữ liệu client để thử bypass bảo mật trong code production.** Trong test, `@WithMockUser` tạo security context giả lập là hợp lệ vì đó là fixture được kiểm soát.

### Điều kiện 5: Biểu thức và nguồn dữ liệu chính sách có nghĩa

Ví dụ:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void closePeriod() {
    // ...
}
~~~

Mặc định `hasRole("ADMIN")` tìm authority `ROLE_ADMIN`. Nếu hệ thống chỉ cấp `ADMIN` mà không có tiền tố phù hợp, annotation có thể từ chối dù user đã đăng nhập. Tương tự, `hasAuthority("report:read")` yêu cầu khớp đúng chuỗi authority.

Biểu thức có thể truy cập tham số method:

~~~java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report find(long reportId) {
    // ...
}
~~~

Đây là đoạn minh họa, cần bean `reportPolicy`, type `Report` và implementation tương ứng. Tên `#reportId` phải có thể phân giải qua parameter name metadata hoặc cơ chế đặt tên tham số phù hợp. Với Java, build có `-parameters` giúp lưu tên tham số để Spring sử dụng; hoặc chỉ định tên một cách tường minh bằng `@P("reportId")` khi cần. Nếu expression tham chiếu sai tên, lỗi SpEL hoặc quyết định không như dự kiến có thể xuất hiện.

### Điều kiện 6: Không có đường gọi bỏ qua hạ tầng kiểm tra

Method security chỉ kiểm tra các lời gọi thực sự được intercept. Một đường truy cập khác có thể gọi target trực tiếp, hoặc thao tác tương tự được đặt ở một method không có policy. Do đó cần kiểm thử **điểm vào công khai của service** và các cách thức gọi thật, thay vì chỉ nhìn thấy annotation trong file source.

## 5. Ví dụ chạy được: Spring Boot + Spring Security + JUnit

Mục đích là kiểm chứng bằng **hành vi thực**, chứ không chỉ xem code có chứa `@PreAuthorize`.

Bản ví dụ dùng Java 17, Spring Boot 3.3.5 (Spring Security 6.x), Gradle 8.x và Spring Security Test. Nó không cần web server vì gọi thẳng Spring bean từ test. Nhờ đó ta cô lập đúng câu hỏi: method security có chặn service method hay không?

### 5.1. Cấu trúc project

~~~text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/methodsecurity/
    │   ├── MethodSecurityApplication.java
    │   └── ReportService.java
    └── test/java/demo/methodsecurity/
        └── ReportServiceSecurityTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'method-security-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-security` cung cấp hạ tầng Spring Security; `spring-security-test` mang các annotation test như `@WithMockUser`; `spring-boot-starter-test` mang JUnit 5 và tích hợp Spring Boot Test.

### 5.2. Kích hoạt Method Security

File `src/main/java/demo/methodsecurity/MethodSecurityApplication.java`:

~~~java
package demo.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
~~~

Ở đây class `@SpringBootApplication` được nạp khi ứng dụng/test Spring khởi tạo context, vì vậy `@EnableMethodSecurity` nằm đúng nơi có hiệu lực. Không cần thêm `@Configuration` riêng trong ví dụ này.

### 5.3. Method được bảo vệ trong Spring bean

File `src/main/java/demo/methodsecurity/ReportService.java`:

~~~java
package demo.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "report:ok";
    }

    @PreAuthorize("hasAuthority('report:write')")
    public String publishReport() {
        return "report:published";
    }
}
~~~

Hai method đều public và class không final, phù hợp với proxying cơ bản. Chính sách phân biệt authority `report:read` và `report:write`; một user có quyền đọc **không tự động** có quyền xuất bản.

### 5.4. Test từ bên ngoài bean

File `src/test/java/demo/methodsecurity/ReportServiceSecurityTest.java`:

~~~java
package demo.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    void securityAdviceIsAppliedToSpringBean() {
        assertTrue(AopUtils.isAopProxy(reportService));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void aReaderCanRead() {
        assertEquals("report:ok", reportService.readReport());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void aReaderCannotPublish() {
        assertThrows(AccessDeniedException.class,
            () -> reportService.publishReport());
    }

    @Test
    @WithMockUser(username = "bob",
        authorities = {"report:read", "report:write"})
    void aPublisherCanPublish() {
        assertEquals("report:published", reportService.publishReport());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotRead() {
        assertThrows(AccessDeniedException.class,
            () -> reportService.readReport());
    }
}
~~~

Chạy từ root project với JDK 17+ và Gradle 8.x:

~~~bash
gradle test
~~~

Hoặc chỉ chạy test của bài:

~~~bash
gradle test --tests demo.methodsecurity.ReportServiceSecurityTest
~~~

**Kết quả mong đợi:** năm test trên thành công. Test đầu xác minh instance được inject là AOP proxy; các test tiếp theo xác minh lời gọi method được phép/từ chối đúng theo authorities. Nội dung `"report:ok"` và `"report:published"` là giá trị trả về xác định từ code, được assert trực tiếp, không cần dự đoán toàn bộ log Gradle hay startup log.

**Các test này là mã để bạn chạy trong project mẫu; kết quả “thành công” là kỳ vọng thiết kế, không phải kết quả đã thực thi trong bài viết.** Với môi trường thiếu JDK, Gradle hoặc mạng để tải dependency, cần chuẩn bị môi trường trước khi chạy.

### 5.5. Tại sao test này có giá trị?

- `@WithMockUser` đặt security context trong môi trường test; nó không thực hiện login/password validation thực tế. Do đó test tập trung đúng vào **authorization**, không đánh đồng với authentication.
- `@Autowired` nhận bean từ Spring, nên test đi qua proxy; gọi `new ReportService()` sẽ bỏ qua điều kiện này.
- Một trường hợp **thiếu quyền** được kiểm tra bằng exception, thay vì chỉ chạy trường hợp thành công. Nếu vô tình tắt method security, test `aReaderCannotPublish` nhiều khả năng thất bại vì method không còn bị chặn.
- `AopUtils.isAopProxy` là một tín hiệu hữu ích về cơ chế proxy, nhưng một proxy có thể được tạo vì lý do khác (transaction, cache...). Cần **kiểm tra hành vi từ chối** để chứng minh method security đang thực thi, không chỉ kiểm tra có proxy.

## 6. Lỗi kinh điển: self-invocation bỏ qua proxy

Ví dụ sau minh họa cấu trúc có rủi ro:

~~~java
@Service
public class UnsafeReportWorkflow {

    public String runWorkflow() {
        // Lời gọi nội bộ trên "this", KHÔNG đi qua Spring AOP proxy.
        return publish();
    }

    @PreAuthorize("hasAuthority('report:write')")
    public String publish() {
        return "published";
    }
}
~~~

Nếu một caller bên ngoài lấy `UnsafeReportWorkflow` qua Spring rồi gọi `runWorkflow()`, lời gọi đầu tiên đi qua proxy. Nhưng `runWorkflow()` **không có** `@PreAuthorize`; khi nó gọi `this.publish()`, đó là lời gọi nội bộ trên target object và không đi qua proxy. Trong proxy mode thông thường, annotation trên `publish()` **không bảo vệ đường gọi nội bộ này**.

Sơ đồ:

~~~text
Caller
  |
  v
Spring proxy -> runWorkflow()  (không có rule)
                      |
                      v
                   this.publish()
                      |
                      +-- bypass proxy / không chạy @PreAuthorize
~~~

### Cách sửa rõ ràng: tách method được bảo vệ sang bean riêng

~~~java
@Service
public class PublishCommandService {

    @PreAuthorize("hasAuthority('report:write')")
    public String publish() {
        return "published";
    }
}
~~~

~~~java
@Service
public class ReportWorkflowService {

    private final PublishCommandService commands;

    public ReportWorkflowService(PublishCommandService commands) {
        this.commands = commands;
    }

    public String runWorkflow() {
        return commands.publish();
    }
}
~~~

Hai đoạn trên là **mã tích hợp minh họa**, cần import `@Service` và đặt các public class vào file riêng tương ứng. Spring inject `PublishCommandService` qua bean reference nên lời gọi `commands.publish()` đi qua proxy của service được bảo vệ.

Nếu toàn bộ workflow phải yêu cầu quyền xuất bản, cũng có thể đặt `@PreAuthorize` trực tiếp lên **entry method công khai** `runWorkflow()` để bảo vệ ranh giới người dùng thực sự gọi. Thiết kế nên rõ ràng hơn việc dựa vào một lời gọi nội bộ tình cờ được intercept.

**Không coi self-invocation là lỗi cú pháp của annotation.** Annotation vẫn được biên dịch, application vẫn có thể khởi động bình thường, nhưng đường thực thi thực tế bypass interception.

## 7. Proxy mode, visibility, final và điểm gọi

Các trường hợp này phải được phân tích theo kiểu proxy và điểm gọi:

| Trường hợp | Nguy cơ | Cách kiểm chứng hoặc xử lý |
| --- | --- | --- |
| Tạo service bằng `new` | Không dùng Spring bean/proxy | Dùng dependency injection / `ApplicationContext` |
| Method gọi method khác trong cùng object | Self-invocation bypass advice theo proxy mode | Tách bean hoặc bảo vệ entry method |
| `private` method có annotation | Proxy AOP không chặn private self-call theo cách thông thường | Đặt rule lên method public có thể intercept |
| `final` method/class với class-based proxy | Không thể override/subclass để apply advice | Thiết kế bean/method không final hoặc chọn proxy strategy phù hợp |
| Interface-based proxy | Chỉ các lời gọi qua interface method được expose đúng cách mới đi qua JDK proxy | Dùng contract interface phù hợp, test injection/dispatch |
| Bean nằm ngoài component scan | Không có bean/proxy trong context mong đợi | Sửa `@ComponentScan`/`@Import`/config |
| Một method có annotation nhưng caller giữ target object trực tiếp | Bỏ qua advice | Dùng reference do Spring quản lý |
| Service được chạy ở context riêng của test | Có thể thiếu `@EnableMethodSecurity` trong context đó | Dùng `@SpringBootTest` hoặc import cấu hình method security phù hợp |

**AspectJ weaving là một cơ chế khác** với proxy Spring AOP và có thể xử lý một số vấn đề self-invocation nếu được cấu hình riêng. Đây không phải mặc định của `@EnableMethodSecurity`, và việc chuyển sang weaving cần chủ đích, dependency và kiểm thử tương ứng; không áp dụng chỉ vì annotation đang bị bỏ qua mà chưa phân tích đường gọi.

### Có nên gọi proxy của chính mình?

Một số mã cố lấy proxy qua `ApplicationContext` hoặc self-inject để né self-invocation. Cách đó có thể hoạt động trong điều kiện cụ thể nhưng tạo phụ thuộc vòng, khó đọc và khó test. Với code mới, ưu tiên tách trách nhiệm sang bean khác hoặc đặt policy tại public entry point. Nếu dự án có legacy design khó tách, cần test thực tế ở đúng đường gọi thay vì tin vào cách né proxy.

## 8. Cấu hình bật và tắt một họ annotation

Ví dụ dùng `@PreAuthorize` mà không dùng `@Secured`:

~~~java
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@PreAuthorize` sẽ được bật theo mặc định. Trong một số hệ thống legacy, bạn có thể gặp:

~~~java
@Secured("ROLE_ADMIN")
public void rotateKeys() {
    // ...
}
~~~

Để `@Secured` có hiệu lực, cần:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Tương tự với Jakarta JSR-250:

~~~java
@RolesAllowed("ADMIN")
public void rotateKeys() {
    // ...
}
~~~

cần:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

`@Secured` thuộc `org.springframework.security.access.annotation.Secured`; `@RolesAllowed` thuộc `jakarta.annotation.security.RolesAllowed`. Đoạn ví dụ này dùng để phân biệt cấu hình, không tạo một ứng dụng độc lập. Tên role và authority trong hệ thống phải nhất quán với cách Spring Security so khớp.

Bạn cũng có thể dùng:

~~~java
@EnableMethodSecurity(prePostEnabled = false)
~~~

khi cần chủ động vô hiệu hóa cấu hình mặc định của nhóm pre/post, nhưng lúc đó **đừng kỳ vọng** `@PreAuthorize`/`@PostAuthorize` hoạt động trừ khi đã đăng ký một hạ tầng thay thế phù hợp. Đây là một nguyên nhân thực tế khiến annotation “có trong code nhưng không được chạy”.

Nếu cùng một method bị nhiều rule/advice phân quyền bao phủ, tất cả các kiểm tra áp dụng cần được đáp ứng; đừng suy diễn rằng viết một `@PermitAll` ở một họ annotation sẽ tự động bỏ qua mọi rule từ họ khác hoặc từ HTTP security.

## 9. Đọc chính xác biểu thức `@PreAuthorize`

### 9.1. Kiểm tra authentication

~~~java
@PreAuthorize("isAuthenticated()")
public String viewMyDashboard() {
    return "dashboard";
}
~~~

Đòi hỏi principal được Spring Security công nhận là authenticated. Anonymous authentication có những semantics riêng nên không tự kiểm tra bằng `authentication.isAuthenticated()` trong code rồi cho rằng tương đương với security expression.

### 9.2. Kiểm tra role

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void cleanAuditLogs() {
    // ...
}
~~~

Theo quy ước mặc định, `hasRole('ADMIN')` kiểm tra `ROLE_ADMIN` trong `GrantedAuthority`. `hasAuthority('ADMIN')` kiểm tra chính xác chuỗi `ADMIN`. Nếu user có quyền `ROLE_EDITOR`, method yêu cầu `ROLE_ADMIN` vẫn phải bị từ chối dù đã login.

### 9.3. Kiểm tra authority cụ thể

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readReport() {
    return "report:ok";
}
~~~

Authority `report:read` đến từ cơ chế xác thực/ánh xạ quyền được tin cậy, không phải một field do client tùy ý gửi trong body request. Một người có `report:write` cũng **không nhất thiết** có `report:read`, trừ khi hệ thống cấp cả hai hoặc chính sách quy định một mapping khác.

### 9.4. Kiểm tra tham số và object-level policy

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document loadDocument(long documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
~~~

Đoạn này chỉ minh họa: `Document`, `documentRepository` và bean `documentPolicy` phải được ứng dụng định nghĩa. Chính sách cần dùng dữ liệu server để kiểm tra owner/tenant; không tin `ownerId` hoặc `tenantId` do client tự khai báo. Nếu không có policy bean hoặc tên tham số không giải được, expression có thể lỗi thay vì “âm thầm cấp quyền”.

Method security chỉ giúp bạn **đưa ra quyết định đúng nơi**; nó không tự đảm bảo quy tắc nghiệp vụ hay quyền truy cập đối tượng đã được viết đầy đủ.

## 10. `@PreAuthorize` và `@PostAuthorize` khác nhau

- `@PreAuthorize` chạy trước thân method, phù hợp để chặn hành động nếu chưa được cấp quyền.
- `@PostAuthorize` đánh giá sau khi method trả về và có thể truy cập kết quả thông qua `returnObject`.
- `@PreFilter`/`@PostFilter` có khả năng lọc collection/argument/return value khi sử dụng đúng kiểu dữ liệu và semantics hỗ trợ.

Ví dụ minh họa:

~~~java
@PreAuthorize("hasAuthority('invoice:read')")
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public Invoice getInvoice(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

`Invoice`, field `ownerUsername` và `repository` là dữ liệu của ứng dụng; đây không phải ví dụ chạy độc lập. Điều kiện đầu kiểm tra authority. Điều kiện sau chỉ cho phép trả invoice nếu user là owner.

**Không dùng `@PostAuthorize` để “bảo vệ” thao tác đã gây tác dụng phụ trước đó.** Nếu method đã gửi tiền, xóa dữ liệu hoặc gọi API ngoài rồi mới bị từ chối sau khi trả về, hành động có thể đã xảy ra. Với operation làm thay đổi trạng thái, cần kiểm tra quyền **trước khi** thực thi, bao gồm quyền trên object/tenant.

Tương tự, đọc được dữ liệu rồi mới từ chối ở `@PostAuthorize` có thể tốn tài nguyên hoặc phát sinh side effects (logging, cache). Chọn vị trí policy theo đặc tính nghiệp vụ, không theo sự tiện lợi của một annotation.

## 11. Annotation trên class và method

Spring Security có thể nhận metadata bảo mật ở mức class hoặc method, tùy vị trí và loại annotation:

~~~java
@Service
@PreAuthorize("hasAuthority('finance:read')")
public class FinanceService {

    public String summary() {
        return "summary";
    }

    @PreAuthorize("hasAuthority('finance:write')")
    public String updateBudget() {
        return "updated";
    }
}
~~~

Mức class tạo chính sách chung cho các method liên quan; mức method có thể cụ thể hóa/thay thế rule của cùng họ theo cơ chế phân giải metadata của Spring Security. Không mặc nhiên cộng hai biểu thức cùng loại thành phép AND hoặc OR nếu chưa hiểu quy tắc override và thứ tự interceptor.

Cần tránh các annotation security mâu thuẫn được kế thừa từ nhiều interface hoặc superclass. Trong một số trường hợp Spring có thể báo lỗi vì metadata mơ hồ và yêu cầu annotation rõ ràng ở implementation. Với API quan trọng, viết test tại điểm gọi thực tế để xác minh rule cuối cùng được áp dụng.

## 12. Servlet và WebFlux: chọn đúng cơ chế

Nội dung chính của bài dùng method security kiểu imperative trong ứng dụng Servlet/Spring MVC hoặc service thường:

~~~java
@Configuration
@EnableMethodSecurity
class ServletMethodSecurityConfig {
}
~~~

Đối với **reactive method security** trong WebFlux, sử dụng cấu hình riêng:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

Các import ở ví dụ reactive là `org.springframework.context.annotation.Configuration` và `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`.

Spring Security reactive sử dụng Reactor Context cho `Authentication` thông qua `ReactiveSecurityContextHolder`. Khi viết service reactive, hãy trả về publisher (`Mono`/`Flux`) và để security advice tương tác với publisher theo mô hình reactive, ví dụ:

~~~java
// Minh họa một method thuộc Spring-managed reactive service.
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> readReport() {
    return Mono.just("report:ok");
}
~~~

Đoạn trên không phải class chạy độc lập. Cần dependency Reactor/WebFlux và cấu hình reactive tương ứng. Tránh dùng `SecurityContextHolder` kiểu ThreadLocal hoặc `block()` như cách mặc định để làm security check trong WebFlux. Không tự cho rằng `@EnableMethodSecurity` của Servlet tự thay thế được `@EnableReactiveMethodSecurity` khi quyền nằm trong Reactor Context.

Nếu ứng dụng trộn các tầng blocking và non-blocking, ranh giới chuyển ngữ cảnh phải được thiết kế/test rõ ràng; không dùng việc đổi scheduler như một bảo đảm tự động truyền `ThreadLocal` qua mọi API bên ngoài Reactor.

## 13. Khi test HTTP trả 401/403 thì method security có hoạt động chưa?

**Không thể kết luận chỉ từ status HTTP.** Một request có thể bị chặn trước khi gọi method (tại filter chain, CSRF, CORS, request authorization) hoặc bị chặn ở method interceptor.

Ví dụ với Servlet:

~~~text
HTTP request
   |
   v
SecurityFilterChain / request authorization
   |
   +-- bị từ chối ở đây -> controller/service có thể chưa chạy
   |
   v
Controller
   |
   v
Spring proxy của service
   |
   +-- @PreAuthorize từ chối -> AccessDeniedException
   |
   v
Service target method
~~~

Khi request chưa xác thực, ứng dụng HTTP Basic thường trả `401` theo entry point; user đã xác thực nhưng thiếu quyền thường nhận `403` qua exception translation. Nhưng CSRF cũng có thể trả `403`, custom handlers hoặc form login có thể redirect, và lời gọi method ngoài HTTP sẽ ném exception thay vì sinh một HTTP status.

**Phép thử đáng tin nhất cho method security** là gọi bean từ Spring context trong test với `@WithMockUser` đủ/thiếu quyền và assert thân method chỉ được thực thi khi hợp lệ. Test HTTP vẫn cần thiết để kiểm chứng toàn bộ request flow, nhưng một test chỉ nhìn response `403` không cho biết filter nào đã từ chối.

### Phân biệt test có annotations nhưng chưa bật method security

Nếu bạn xóa `@EnableMethodSecurity` khỏi project mẫu:

- Source của `ReportService` vẫn biên dịch và chứa `@PreAuthorize`.
- Một lời gọi `reportService.publishReport()` có thể thực thi trực tiếp vì không có method-security interceptor tương ứng.
- Test `aReaderCannotPublish` phải thất bại (không ném `AccessDeniedException`), qua đó phát hiện thiếu hạ tầng.

Đây là phép thử **tư duy để hiểu nguyên nhân**, không phải yêu cầu xóa cấu hình trong bản ứng dụng bạn sẽ giữ.

## 14. Gỡ lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Kiểm tra cụ thể |
| --- | --- | --- |
| `@PreAuthorize` không chặn bất kỳ ai | Thiếu `@EnableMethodSecurity` hoặc config không được nạp | Kiểm tra class cấu hình/context của ứng dụng và test |
| Gọi trực tiếp bằng `new` vẫn chạy | Không qua bean/proxy | Inject `@Service` bằng constructor hoặc `@Autowired` |
| Controller gọi service bị chặn, nhưng gọi từ method khác cùng class thì không | Self-invocation | Theo dõi `this.method()`, tách bean hoặc đặt rule tại entry |
| `@Secured` không chặn | `securedEnabled` mặc định `false` | Bật `@EnableMethodSecurity(securedEnabled = true)` |
| `@RolesAllowed` không chặn | `jsr250Enabled` chưa bật | Bật `jsr250Enabled = true` |
| Admin bị từ chối dù đã login | Sai authority, ví dụ `ADMIN` so với `ROLE_ADMIN` | Kiểm tra `Authentication.getAuthorities()` và rule |
| Expression `#id` không đúng | Thiếu parameter name metadata hoặc SpEL sai | Dùng build có `-parameters` hoặc `@P("id")` |
| Method final/private không được bảo vệ | Hạn chế proxy/visibility | Đưa policy lên public interceptable entry method |
| `@SpringBootTest` chạy khác web runtime | Context test thiếu config hoặc dữ liệu security khác | Kiểm tra test annotation/import, dùng integration test |
| Có proxy nhưng vẫn không thấy từ chối | Proxy phục vụ mục đích khác hoặc security advice không áp dụng | Test thiếu quyền bằng `assertThrows`, xem advisors/interceptors |
| WebFlux đọc sai principal hoặc mất identity | Dùng ThreadLocal/Servlet assumptions trong reactive pipeline | Dùng reactive method security + Reactor Context |
| HTTP 403 dù method đúng quyền | Request filter/CSRF/authorization chặn trước | Trace filter chain và đối chiếu security rules |

Khi debug, **không log credentials, token thô hoặc toàn bộ `SecurityContext`**. Có thể ghi audit tối thiểu gồm principal ID, action, resource và quyết định ở ranh giới thích hợp, tránh lộ thông tin nhạy cảm.

## 15. Checklist trước khi coi annotation là “đang bảo vệ”

1. **Đúng annotation:** Cần `@PreAuthorize`, `@PostAuthorize`, `@Secured` hay `@RolesAllowed`? Nhóm đó đã được bật?
2. **Đúng context:** `@EnableMethodSecurity` nằm trong cấu hình Spring thực sự được nạp?
3. **Đúng bean:** Service do Spring container tạo? Caller nhận được bean/proxy thay vì tạo object bằng `new`?
4. **Đúng đường gọi:** Lời gọi đi qua proxy, không bị self-invocation hoặc final/private method chặn advice?
5. **Đúng principal:** Authentication của caller là gì? Có anonymous/remember-me không? Quyền đang cấp có khớp chuỗi rule không?
6. **Đúng policy:** Biểu thức SpEL có tham số, bean và dữ liệu resource hợp lệ không?
7. **Đúng stack:** Đang dùng imperative/Servlet `@EnableMethodSecurity` hay reactive/WebFlux `@EnableReactiveMethodSecurity`?
8. **Có test phủ định:** Thiếu quyền có thực sự bị từ chối **trước khi** nghiệp vụ chạy không?

Các câu hỏi trên nên được trả lời bằng test/instrumentation tại **đường gọi thật**. Đó là cách kiểm tra hiệu lực đáng tin cậy hơn việc chỉ thấy annotation xuất hiện trong IDE.

## 16. Bài tập tự kiểm tra

**Bài 1 — thiếu cấu hình.** Một Spring Boot application có `spring-boot-starter-security` và service với `@PreAuthorize("hasRole('ADMIN')")`, nhưng không có `@EnableMethodSecurity`. Có thể kết luận method đã được bảo vệ không?

**Đáp án:** Không. Spring Boot Starter Security không tự bật method-level authorization. Cần thêm cấu hình tương ứng vào ApplicationContext, sau đó test các lời gọi qua bean.

**Bài 2 — self-invocation.** Class `OrderService` có `placeOrder()` gọi `this.approveOrder()`, trong đó `approveOrder()` mang `@PreAuthorize("hasAuthority('order:approve')")`. Vì sao người thiếu quyền vẫn có thể đi vào thân method?

**Đáp án:** Trong Spring AOP proxy mode, lời gọi nội bộ qua `this` không đi qua proxy/advice. Hãy tách `approveOrder` sang Spring bean khác hoặc đặt rule trên entry method phù hợp; kiểm chứng bằng test.

**Bài 3 — role và authority.** User có authority `ROLE_ADMIN`. Điều gì khác nhau giữa `hasRole('ADMIN')` và `hasAuthority('ADMIN')`?

**Đáp án:** Với prefix role mặc định, `hasRole('ADMIN')` kiểm tra `ROLE_ADMIN`, còn `hasAuthority('ADMIN')` kiểm tra đúng chuỗi `ADMIN`. Chúng có thể cho kết quả khác nhau.

**Bài 4 — proxy.** Vì sao `AopUtils.isAopProxy(service) == true` chưa đủ chứng minh `@PreAuthorize` đang có hiệu lực?

**Đáp án:** Proxy có thể được tạo bởi transaction/caching hoặc advice khác; phải test một request/caller thiếu authority và xác minh method bị từ chối đúng lúc.

**Bài 5 — method sau khi thực thi.** Vì sao không nên dùng riêng `@PostAuthorize` để bảo vệ thao tác chuyển tiền?

**Đáp án:** Vì phép kiểm tra sau khi method kết thúc có thể đến quá muộn; side effect đã xảy ra. Phải kiểm tra policy và quyền đối với tài nguyên trước khi thực hiện.

**Bài 6 — WebFlux.** Ứng dụng trả về `Mono<String>` và dùng Reactor Context cho principal. Annotation kích hoạt method security nào phù hợp?

**Đáp án:** Sử dụng `@EnableReactiveMethodSecurity` và reactive method security infrastructure; tránh đọc identity bằng ThreadLocal như mặc định của Servlet.

## 17. Ghi nhớ và tài liệu tham khảo

**`@EnableMethodSecurity` bật hạ tầng phân quyền phương thức; annotation chỉ thực sự bảo vệ khi Spring đã nạp cấu hình, phương thức thuộc Spring bean, lời gọi được interceptor chặn và biểu thức phân quyền được đánh giá với ngữ cảnh xác thực đúng.** Với proxy mode, kiểm tra kỹ self-invocation và những method không thể intercept. Luôn test cả trường hợp đủ quyền và thiếu quyền.

Tài liệu Spring Security chính thức:

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — EnableMethodSecurity API](https://docs.spring.io/spring-security/site/docs/6.2.6/api/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
