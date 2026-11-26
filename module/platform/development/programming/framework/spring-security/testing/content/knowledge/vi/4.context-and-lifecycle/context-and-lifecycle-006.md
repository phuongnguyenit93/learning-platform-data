# @SecurityTestExecutionListeners trong phạm vi phù hợp

Khi kiểm thử một service có bảo vệ bằng Spring Security, đôi khi bạn chỉ cần mô phỏng người dùng bằng `@WithMockUser` rồi gọi phương thức nghiệp vụ. Bạn không cần khởi tạo `ApplicationContext`, inject bean, quản lý transaction hay chạy các listener phục vụ Spring Test khác. Trong trường hợp gọn như vậy, `@SecurityTestExecutionListeners` giúp đăng ký riêng các listener kiểm thử bảo mật.

Nhưng annotation này có một đặc điểm rất quan trọng: nó được thiết kế để **chỉ bật listener của Spring Security**. Vì vậy, đặt nó lên một lớp test đang cần `@SpringBootTest`, `@SpringJUnitConfig`, dependency injection hoặc transaction test có thể làm mất những listener mặc định cần thiết. Bài học thuộc chương **Ngữ cảnh và vòng đời** của module **SPRING_SECURITY_TESTING**, tập trung vào việc chọn đúng phạm vi sử dụng, phối hợp với `@TestExecutionListeners` và kiểm thử Servlet/Reactive bằng `spring-security-test`.

## 1. @SecurityTestExecutionListeners là gì?

`@SecurityTestExecutionListeners` nằm trong package:

~~~java
org.springframework.security.test.context.annotation.SecurityTestExecutionListeners
~~~

Đây là annotation cấp lớp (type-level), có retention runtime và được đánh dấu `@Inherited`. Nó là một meta-annotation trên `@TestExecutionListeners`. Trong các phiên bản Spring Security hiện hành, khai báo tương đương về ý nghĩa là:

~~~java
@TestExecutionListeners(
    inheritListeners = false,
    listeners = {
        WithSecurityContextTestExecutionListener.class,
        ReactorContextTestExecutionListener.class
    }
)
~~~

Hai listener này phục vụ hai kiểu ngữ cảnh:

| Listener | Vai trò |
| --- | --- |
| `WithSecurityContextTestExecutionListener` | Xử lý annotation như `@WithMockUser`, `@WithUserDetails` và annotation tùy biến dựa trên `@WithSecurityContext`; đặt/dọn `SecurityContext` cho test |
| `ReactorContextTestExecutionListener` | Cung cấp ngữ cảnh bảo mật cho các test reactive method security thông qua `ReactiveSecurityContextHolder` |

Annotation không có thuộc tính để thêm listener tùy ý. Mục tiêu của nó là đăng ký **các listener bảo mật cần thiết** cho một test class không cần toàn bộ listener mặc định của Spring TestContext.

Trong các bản Spring Security hiện hành, annotation đăng ký cả hai listener trên. Một số phiên bản cũ có danh sách listener khác, vì vậy hãy đối chiếu Javadoc của đúng phiên bản `spring-security-test` đang dùng. Dependency `spring-security-test` cũng cần tương thích với phiên bản Spring Security của ứng dụng.

## 2. Khi nào nên dùng?

Trường hợp phù hợp nhất là một test class:

- Cần Spring TestContext để nhận các callback của `TestExecutionListener`.
- Dùng `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` hoặc annotation tùy biến bảo mật.
- Không cần khởi tạo `ApplicationContext`.
- Không cần `@Autowired`, `@Transactional`, `@Sql` hoặc các tiện ích khác phụ thuộc listener mặc định của Spring Test.

Ví dụ, một lớp test đơn giản chỉ xác minh rằng authentication giả lập được đặt trên `SecurityContextHolder`:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.annotation.SecurityTestExecutionListeners;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
@SecurityTestExecutionListeners
class SecurityOnlyTest {

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void securityListenerCreatesAuthentication() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication).isNotNull();
        assertThat(authentication.getName()).isEqualTo("lan");
        assertThat(authentication.getAuthorities())
                .extracting("authority")
                .contains("ROLE_READER");
    }
}
~~~

Ví dụ này dùng JUnit Jupiter. `@ExtendWith(SpringExtension.class)` kích hoạt Spring TestContext; `@SecurityTestExecutionListeners` cấu hình listener bảo mật. Không có `@ContextConfiguration` hoặc `@SpringBootTest` vì test không yêu cầu tạo Spring application context.

Nếu dùng JUnit 4, ý tưởng tương tự với runner Spring:

~~~java
@RunWith(SpringRunner.class)
@SecurityTestExecutionListeners
public class SecurityOnlyJUnit4Test {
    @Test
    @WithMockUser(username = "lan")
    public void authenticationIsAvailable() {
        // Assert SecurityContextHolder.getContext().getAuthentication()
    }
}
~~~

Không được bỏ runner/extension Spring rồi kỳ vọng annotation tự chạy. `@SecurityTestExecutionListeners` khai báo cấu hình listener; nó không tự biến một test JUnit thuần thành Spring TestContext test.

## 3. Vì sao annotation này có thể làm hỏng test cần ApplicationContext?

`@SecurityTestExecutionListeners` được thiết kế với `inheritListeners = false` và chỉ khai báo listener bảo mật. Nó không mang ý nghĩa “thêm listener bảo mật vào toàn bộ listener mặc định”. Khi Spring TestContext xử lý cấu hình này, danh sách listener được chỉ định thay thế danh sách mặc định cho lớp test đó.

Các listener mặc định có thể đảm nhiệm những việc như:

- Chuẩn bị và inject dependency cho test instance.
- Thiết lập request context trong test web.
- Quản lý transaction test.
- Xử lý `@Sql`.
- Quản lý vòng đời `ApplicationContext` và các chức năng Spring Test khác.

Vì vậy, ví dụ sau là một cách dùng sai trong trường hợp cần inject bean:

~~~java
@SpringBootTest
@SecurityTestExecutionListeners
class ReportServiceIntegrationTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "lan")
    void readsReport() {
        reportService.readReport();
    }
}
~~~

`@SecurityTestExecutionListeners` có thể loại bỏ `DependencyInjectionTestExecutionListener` khỏi tập listener của lớp, khiến `@Autowired` không được xử lý như mong đợi. Tùy cấu hình, những chức năng Spring Test khác cũng có thể ngừng hoạt động.

Nếu test cần `ApplicationContext`, hãy dùng cấu hình Spring Test thông thường và để các listener mặc định được đăng ký:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ReportTestConfig.class)
class ReportServiceIntegrationTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "lan")
    void readsReport() {
        // Spring TestContext inject bean và listener bảo mật xử lý annotation.
    }
}
~~~

Trong ứng dụng Spring Boot, `@SpringBootTest`, `@WebMvcTest` hoặc `@WebFluxTest` thường đã kích hoạt hạ tầng test tương ứng. Thông thường không cần thêm `@SecurityTestExecutionListeners` vào các lớp test này.

**Quy tắc thực tế:** dùng `@SecurityTestExecutionListeners` cho test class chỉ cần hỗ trợ listener bảo mật; giữ cấu hình listener mặc định cho test có context, DI, transaction, SQL hoặc web test infrastructure.

## 4. Phân biệt với @TestExecutionListeners

Hai annotation có tên gần giống nhưng mục đích khác nhau:

| Annotation | Mục đích | Cách hoạt động |
| --- | --- | --- |
| `@SecurityTestExecutionListeners` | Bật riêng listener bảo mật của Spring Security Test | Meta-annotated với `@TestExecutionListeners` và cấu hình danh sách listener chuyên biệt |
| `@TestExecutionListeners` | Tùy chỉnh danh sách listener của Spring TestContext | Có thể thay thế listener mặc định hoặc gộp listener tự khai báo với listener mặc định |

Nếu một test class có listener riêng (ví dụ listener ghi audit hoặc chuẩn bị fixture) và vẫn muốn giữ các listener mặc định, hãy sử dụng `mergeMode = MERGE_WITH_DEFAULTS`:

~~~java
import org.springframework.test.context.TestExecutionListeners;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ReportTestConfig.class)
@TestExecutionListeners(
    listeners = AuditTestExecutionListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ReportWithAuditListenerTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void customAndDefaultListenersAreAvailable() {
        reportService.readReport();
    }
}
~~~

Trong ví dụ, `AuditTestExecutionListener` là listener do ứng dụng tự định nghĩa. `MERGE_WITH_DEFAULTS` yêu cầu Spring TestContext kết hợp listener được khai báo với danh sách mặc định đã được phát hiện, trong đó có listener của Spring Security Test khi dependency và cấu hình tương ứng có mặt.

Nếu đặt `mergeMode = REPLACE_DEFAULTS`, bạn chủ động thay danh sách mặc định. Khi làm vậy, phải tự chịu trách nhiệm liệt kê tất cả listener cần thiết, bao gồm listener phục vụ injection, transaction, context và security. Đây là cấu hình nâng cao; chỉ dùng khi có lý do rõ ràng và đã kiểm tra toàn bộ vòng đời test.

Không nên vừa thêm `@SecurityTestExecutionListeners` vừa kỳ vọng `MERGE_WITH_DEFAULTS` tự được áp dụng: annotation chuyên biệt đã mang cấu hình `@TestExecutionListeners` riêng. Nếu cần thêm listener ứng dụng, hãy dùng `@TestExecutionListeners` với merge mode phù hợp.

## 5. Khi đã có @SpringBootTest hoặc @SpringJUnitConfig

Với test cần Spring bean, thông thường không cần thêm annotation chuyên biệt. Spring Security Test tích hợp listener vào hạ tầng Spring TestContext. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "lan", authorities = "report:read")
    void authenticatedReaderCanRead() {
        assertThat(reportService.readReport()).isNotBlank();
    }
}
~~~

Ví dụ giả định ứng dụng có bean `ReportService` và phương thức `readReport()` được cấu hình đúng. Listener tạo authentication trước khi phương thức test chạy. Spring Boot test infrastructure vẫn cần các listener mặc định để inject `ReportService` và quản lý context.

Nếu test có `@ContextConfiguration` hoặc `@SpringJUnitConfig`, cách dùng tương tự. Hãy giữ listener mặc định trừ khi bạn đang chủ động thay đổi toàn bộ TestContext infrastructure.

## 6. Ảnh hưởng với Servlet và MockMvc

`@SecurityTestExecutionListeners` không tự cấu hình `MockMvc`, không tạo `SecurityFilterChain` và không cài filter vào request. Nó chỉ đăng ký các listener test bảo mật. Để kiểm thử HTTP Servlet, ứng dụng vẫn phải có Spring MVC context và tích hợp Spring Security vào `MockMvc`.

Ví dụ với Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void readerCanReadReports() throws Exception {
        mockMvc.perform(get("/api/reports"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "mai", roles = "GUEST")
    void guestCannotReadReports() throws Exception {
        mockMvc.perform(get("/api/reports"))
                .andExpect(status().isForbidden());
    }
}
~~~

Đoạn test cần các import cho `MockMvc`, `get`, `status`, `@AutoConfigureMockMvc` và ứng dụng có endpoint `/api/reports` yêu cầu `ROLE_READER`. `@SpringBootTest` và `@AutoConfigureMockMvc` cung cấp hạ tầng web test; không thêm `@SecurityTestExecutionListeners` vào lớp này.

Khi dựng `MockMvc` thủ công từ `WebApplicationContext`, dùng `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build()` để tích hợp filter chain. Nếu bỏ filter bảo mật, request thành công không chứng minh rule xác thực/phân quyền HTTP đã chạy.

Danh tính được cấp bởi `@WithMockUser` là dữ liệu test. Nó giúp kiểm tra chính sách phân quyền nhưng không chứng minh mật khẩu, JWT signature, OAuth2 authorization code hay OIDC ID token được xác minh thật. Với JWT/OAuth2/OIDC giả lập, dùng request postprocessor phù hợp như `jwt()`, `oauth2Login()` hoặc `oidcLogin()` khi kiểm tra authorization. Để kiểm chứng quá trình xác thực thật, phải đưa request qua thành phần xác thực tương ứng.

## 7. Reactive: listener thứ hai có vai trò gì?

Trong các phiên bản Spring Security hiện hành, `@SecurityTestExecutionListeners` đăng ký cả `ReactorContextTestExecutionListener` bên cạnh `WithSecurityContextTestExecutionListener`. Listener Reactive giúp đưa ngữ cảnh bảo mật test vào `ReactiveSecurityContextHolder` cho các bài kiểm thử reactive method security.

Ví dụ một test không cần `ApplicationContext`, chỉ cần kiểm tra Reactor Context:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.test.context.annotation.SecurityTestExecutionListeners;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@ExtendWith(SpringExtension.class)
@SecurityTestExecutionListeners
class ReactiveSecurityOnlyTest {

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void reactiveContextContainsAuthentication() {
        Mono<String> username = ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());

        StepVerifier.create(username)
                .expectNext("lan")
                .verifyComplete();
    }
}
~~~

Để chạy ví dụ cần Reactor Core, Reactor Test, JUnit Jupiter, Spring Test và Spring Security Test tương thích. Listener Reactive cung cấp context cho pipeline test; nó không tự cấu hình WebFlux server hoặc `WebTestClient`.

Với kiểm thử HTTP Reactive, dùng `WebTestClient` và cấu hình Spring Security WebFlux phù hợp. Request postprocessor `mockUser()` cấp user cho một request cụ thể:

~~~java
webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Trong test WebFlux có `@WebFluxTest` hoặc `@SpringBootTest`, hãy giữ các listener mặc định để Spring khởi tạo context, inject bean và cấu hình web test. Không dùng `@SecurityTestExecutionListeners` như cách thay thế cho hạ tầng đó.

Nếu chỉ kiểm thử reactive method security mà không cần Spring application context, annotation chuyên biệt có thể là lựa chọn phù hợp vì nó bao gồm listener Reactor trong phiên bản hiện hành. Với phiên bản cũ, hãy kiểm tra API/Javadoc và listener thực tế được đăng ký.

## 8. Phạm vi lớp, lớp cha và kế thừa

`@SecurityTestExecutionListeners` là annotation cấp lớp và được đánh dấu `@Inherited`. Vì vậy, hãy cân nhắc nơi đặt annotation:

- Đặt trên một lớp test nhỏ, độc lập, chỉ cần listener bảo mật.
- Tránh đặt trên base test class dùng chung cho cả unit test không context và integration test cần DI/transaction.
- Khi một lớp con bổ sung nhu cầu Spring Test mặc định, kiểm tra cấu hình listener mà lớp con nhận được; không giả định annotation chuyên biệt chỉ thêm listener bảo mật.
- Nếu dự án có nhiều nhóm test với hạ tầng khác nhau, tách test class theo phạm vi thường rõ ràng hơn việc dùng một base class cấu hình listener cho tất cả.

Thuộc tính `inheritListeners = false` trong cấu hình meta của annotation thể hiện rằng danh sách listener được chọn theo mục tiêu chuyên biệt, không nhằm kế thừa thêm các listener tùy biến của lớp cha. Đây là lý do cần thận trọng khi gắn annotation vào hệ thống lớp test có kế thừa.

## 9. Bảng quyết định sử dụng

| Bối cảnh test | Có nên dùng `@SecurityTestExecutionListeners`? | Cấu hình nên chọn |
| --- | --- | --- |
| JUnit Jupiter + SpringExtension, chỉ đọc `SecurityContextHolder` từ `@WithMockUser`, không cần bean | **Có** | `@ExtendWith(SpringExtension.class)` + `@SecurityTestExecutionListeners` |
| Test reactive method security không cần ApplicationContext | **Có thể** | Đảm bảo phiên bản annotation đăng ký `ReactorContextTestExecutionListener` |
| `@SpringBootTest` có `@Autowired` service/repository | **Không** | Dùng listener mặc định của Spring TestContext |
| `@WebMvcTest`/`@WebFluxTest` cần controller, filter, WebTestClient | **Không** | Giữ test slice và listener mặc định |
| `@Transactional` hoặc `@Sql` | **Không** | Giữ transaction/SQL listeners mặc định |
| Có listener tùy chỉnh và vẫn cần default listeners | **Không dùng annotation chuyên biệt** | `@TestExecutionListeners(mergeMode = MERGE_WITH_DEFAULTS)` |
| Chủ động thay toàn bộ listener mặc định | Chỉ khi hiểu rõ hệ quả | Liệt kê đầy đủ listener cần thiết; kiểm tra DI, context, transaction và security |
| HTTP request đi tới server thật qua cổng mạng | **Không giải quyết bằng annotation này** | Gửi credentials/token/cookie trong request và kiểm thử server |

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `@Autowired` thành `null` sau khi thêm `@SecurityTestExecutionListeners` | Listener dependency injection mặc định bị thay thế | Bỏ annotation chuyên biệt trên integration test; dùng listener mặc định |
| `@Transactional` không rollback như trước | Transaction listener không còn trong danh sách | Dùng `MERGE_WITH_DEFAULTS` hoặc cấu hình đúng transaction listener |
| `@WithMockUser` không có tác dụng | SpringExtension/runner không chạy hoặc listener bảo mật không được đăng ký | Kiểm tra Spring TestContext và dependency `spring-security-test` |
| Test Reactive method security không có principal | Thiếu `ReactorContextTestExecutionListener` hoặc phiên bản annotation cũ không đăng ký listener này | Kiểm tra Javadoc đúng phiên bản; cấu hình listener Reactive phù hợp |
| `MockMvc` request vẫn không được bảo vệ | Chỉ đăng ký test listener, chưa tích hợp security filter | Dùng `springSecurity()` hoặc Boot auto-configure phù hợp |
| `@TestExecutionListeners` làm mất security listener | Danh sách tùy chỉnh thay thế mặc định | Dùng `MERGE_WITH_DEFAULTS` hoặc khai báo rõ listener cần thiết |
| Test lớp con hoạt động khác lớp cha | Annotation cấp lớp và cấu hình kế thừa listener ảnh hưởng phạm vi test | Kiểm tra lớp nào khai báo annotation và listener thực tế |

Một nguyên tắc quan trọng: **listener test và filter bảo mật là hai lớp hạ tầng khác nhau**. `@SecurityTestExecutionListeners` không thay thế `SecurityFilterChain`, không cài filter cho `MockMvc` và không biến một bài test đơn giản thành kiểm thử HTTP thực tế.

## 11. Bài thực hành

Tạo ba lớp test riêng để so sánh phạm vi:

1. **Security-only:** dùng `@ExtendWith(SpringExtension.class)` và `@SecurityTestExecutionListeners`. Dùng `@WithMockUser` và xác minh `SecurityContextHolder` có username/authority mong đợi.
2. **Integration:** dùng `@SpringBootTest` với `@Autowired` service có `@PreAuthorize`. Không thêm `@SecurityTestExecutionListeners`; kiểm tra user được phép và user bị từ chối.
3. **Custom listener:** khai báo một `TestExecutionListener` phục vụ audit, dùng `MERGE_WITH_DEFAULTS` và xác minh cả listener audit lẫn listener bảo mật đều hoạt động.
4. **Reactive security-only:** dùng `@SecurityTestExecutionListeners` để kiểm tra `ReactiveSecurityContextHolder` trong pipeline với `StepVerifier`.
5. **Web test:** dùng `MockMvc` và `WebTestClient` với cấu hình security thực tế; phân biệt kết quả do listener test cung cấp context với kết quả do filter chain xử lý request.

Sau bài thực hành, hãy giải thích được ba điều: annotation đăng ký listener nào, vì sao nó có thể làm mất các listener mặc định, và tại sao nó không thay thế cấu hình HTTP security. Đó là tiêu chí để quyết định phạm vi sử dụng phù hợp.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security and Security Test Setup](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security API — SecurityTestExecutionListeners](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/annotation/SecurityTestExecutionListeners.html)
- [Spring Framework — @TestExecutionListeners](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html)
- [Spring Security API — WithSecurityContextTestExecutionListener](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithSecurityContextTestExecutionListener.html)
- [Spring Security API — ReactorContextTestExecutionListener](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/ReactorContextTestExecutionListener.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
