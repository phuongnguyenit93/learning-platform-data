# Giữ vòng đời SecurityContext độc lập với dữ liệu nghiệp vụ của test

Một bài test dùng `@WithMockUser(username = "lan")` có thể chạy qua authorization, nhưng điều đó không tự tạo tài khoản `lan` trong database. Ngược lại, một fixture có thể lưu tài khoản và báo cáo thành công, nhưng transaction rollback không tự xóa `Authentication` khỏi `SecurityContextHolder`. Hai loại trạng thái này phục vụ mục đích khác nhau và có cơ chế quản lý vòng đời riêng.

Trong module **SPRING_SECURITY_TESTING**, bài học thuộc chương **Ngữ cảnh và vòng đời**, tập trung vào việc giữ vòng đời `SecurityContext` độc lập với dữ liệu nghiệp vụ của test. Người học sẽ phân biệt context do Spring Security Test dựng, principal với entity trong database, transaction rollback với security cleanup, fixture với tài nguyên ngoài transaction; sau đó phối hợp `@WithMockUser`, `@WithUserDetails`, `@BeforeEach`, `@AfterEach`, `@Transactional`, `@Sql` và `MockMvc` để viết test ổn định.

## 1. Hai vòng đời khác nhau trong cùng một bài test

Một bài kiểm thử tích hợp thường quản lý ít nhất hai nhóm trạng thái:

- **Trạng thái bảo mật:** `Authentication`, principal, authorities và `SecurityContext` gắn với test thread hoặc request.
- **Dữ liệu nghiệp vụ:** user record, report, order, tenant, file, cache entry hoặc tài nguyên do test tạo ra.

Mỗi nhóm có chủ sở hữu riêng:

| Trạng thái | Thành phần quản lý | Cách kết thúc vòng đời thường gặp |
| --- | --- | --- |
| Context do `@WithMockUser`/`@WithUserDetails` tạo | `WithSecurityContextTestExecutionListener` | Listener dọn context sau phương thức test |
| Context test do code tự đặt | Mã test | `try/finally` hoặc `@AfterEach` |
| Dữ liệu trong database thuộc transaction test | Transaction manager / Spring Test | Rollback sau test, trừ khi cấu hình commit |
| Dữ liệu tạo bởi `@Sql` | `SqlScriptsTestExecutionListener` cùng transaction mode | Script cleanup hoặc rollback theo cấu hình |
| File, message, cache hoặc dịch vụ ngoài transaction | Fixture/test code hoặc công cụ tích hợp | Xóa/hoàn nguyên rõ ràng trong cleanup |
| Session/HTTP request context | Security filter chain và repository | Kết thúc request, logout hoặc session expiration |

Một lỗi phổ biến là dùng một cơ chế để thay cho cơ chế kia: mong transaction rollback dọn security context, hoặc mong listener dọn context xóa luôn user record trong database. Cả hai giả định đều sai.

## 2. SecurityContext được tạo và dọn như thế nào?

Khi test chạy trong Spring TestContext với `spring-security-test`, `WithSecurityContextTestExecutionListener` xử lý các annotation như `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` và annotation tùy biến dựa trên `@WithSecurityContext`.

Với JUnit Jupiter, thứ tự tổng quát:

~~~text
Spring TestContext: beforeTestMethod
  ├─ TransactionalTestExecutionListener có thể bắt đầu transaction test
  └─ WithSecurityContextTestExecutionListener
       └─ dựng SecurityContext theo annotation (mặc định TEST_METHOD)
JUnit Jupiter: @BeforeEach
JUnit Jupiter: @Test
JUnit Jupiter: @AfterEach
Spring TestContext: afterTestMethod
  ├─ WithSecurityContextTestExecutionListener dọn context
  └─ TransactionalTestExecutionListener hoàn tất transaction
       └─ rollback nếu test được cấu hình rollback
~~~

Thứ tự chính xác giữa các listener phụ thuộc cấu hình listener và thứ tự của chúng; sơ đồ chỉ nêu các mốc quan trọng, không nên dùng nó để suy ra thứ tự tuyệt đối của mọi callback tùy biến. Hai việc vẫn độc lập: listener bảo mật quản lý context; transaction listener quản lý transaction.

Ví dụ một test dùng annotation:

~~~java
@Test
@WithMockUser(username = "lan", authorities = "report:read")
void readsReportAsLan() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.getName()).isEqualTo("lan");
}
~~~

Listener đặt context cho test và dọn theo vòng đời của nó. Không cần thêm `@AfterEach` chỉ để gọi `SecurityContextHolder.clearContext()` cho một test chỉ dùng `@WithMockUser` bình thường. Nếu code test tự ghi đè context, hãy xác định rõ ai đang sở hữu trạng thái mới và dọn phù hợp.

## 3. @WithMockUser không tạo entity trong database

`@WithMockUser` tạo một principal giả lập dựa trên thông tin annotation. Principal thường là đối tượng `User` của Spring Security, không phải entity `AppUser` hoặc `Account` do ứng dụng định nghĩa.

Ví dụ:

~~~java
@Test
@WithMockUser(username = "lan", roles = "READER")
void authenticationHasLanButDatabaseMayNot() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.getName()).isEqualTo("lan");
    assertThat(authentication.getPrincipal())
            .isInstanceOf(org.springframework.security.core.userdetails.User.class);
}
~~~

Test trên không gọi repository và không tạo hàng dữ liệu. Nếu service chỉ đọc `authentication.getName()` rồi dùng tên đó làm tham số tìm kiếm, test có thể hoạt động mà không cần record user. Nhưng nếu service cần tải entity, kiểm tra trạng thái tài khoản, tenant hoặc quan hệ sở hữu, fixture nghiệp vụ phải được tạo riêng.

~~~java
@Service
class ReportService {

    private final AccountRepository accounts;
    private final ReportRepository reports;

    ReportService(AccountRepository accounts, ReportRepository reports) {
        this.accounts = accounts;
        this.reports = reports;
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Report readOwnReport(String reportId) {
        String username = SecurityContextHolder.getContext()
                .getAuthentication().getName();

        Account account = accounts.findByUsername(username)
                .orElseThrow();

        return reports.findByOwnerAndId(account, reportId)
                .orElseThrow();
    }
}
~~~

Trong trường hợp này, `@WithMockUser(username = "lan")` chỉ cung cấp tên principal và authority. Test còn phải tạo account `lan` và report thuộc account đó. Nếu không, test có thể nhận `NoSuchElementException` hoặc lỗi nghiệp vụ dù authorization đã cho phép.

## 4. Tạo fixture nghiệp vụ riêng với @Transactional

Khi dữ liệu test nằm trong database hỗ trợ transaction, `@Transactional` trên test class hoặc method thường là cách thuận tiện để rollback dữ liệu sau mỗi test.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class ReportAuthorizationIntegrationTest {

    @Autowired
    AccountRepository accounts;

    @Autowired
    ReportRepository reports;

    @Autowired
    ReportService reportService;

    @BeforeEach
    void createBusinessFixture() {
        Account lan = accounts.save(new Account("lan", true));
        reports.save(new Report("report-1", lan, "Quarterly summary"));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "report:read")
    void readerCanReadOwnReport() {
        Report report = reportService.readOwnReport("report-1");

        assertThat(report.getOwner().getUsername()).isEqualTo("lan");
    }
}
~~~

Ví dụ giả định entity và repository của ứng dụng có các constructor/phương thức tương ứng. `@Transactional` tạo transaction test; dữ liệu được tạo trong `@BeforeEach` và các thao tác repository của service tham gia cùng transaction nếu dùng cùng transaction manager. Theo mặc định, transaction test được rollback khi kết thúc.

Điều quan trọng:

- Rollback xóa các thay đổi database thuộc transaction đó.
- Rollback không gọi `SecurityContextHolder.clearContext()`.
- Security listener không xóa account/report trong database.
- Nếu code mở transaction riêng, dùng `REQUIRES_NEW`, gọi dịch vụ ngoài hoặc ghi dữ liệu qua kết nối khác, rollback của transaction test có thể không hoàn nguyên những thay đổi đó.

Không cần vừa rollback transaction vừa xóa thủ công cùng một record trong `@AfterEach` nếu cả hai cùng quản lý một dữ liệu. Hãy chọn một chủ sở hữu cleanup rõ ràng để tránh xóa nhầm dữ liệu hoặc làm test phụ thuộc thứ tự.

## 5. Principal giả lập và UserDetails từ dữ liệu ứng dụng

Khi service chỉ cần tên người dùng và authorities, `@WithMockUser` thường đủ. Khi test cần principal do `UserDetailsService` của ứng dụng trả về, dùng `@WithUserDetails`.

~~~java
@Test
@WithUserDetails(
        value = "lan",
        userDetailsServiceBeanName = "accountDetailsService"
)
void principalComesFromApplicationUserDetailsService() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.getName()).isEqualTo("lan");
    assertThat(authentication.getPrincipal())
            .isInstanceOf(AccountUserDetails.class);
}
~~~

`@WithUserDetails` gọi `UserDetailsService` để tải người dùng tại thời điểm listener dựng context. Nó không tự tạo record trong database và không thực hiện form login/password authentication. Dữ liệu user phải tồn tại trước khi factory được gọi.

Nếu tài khoản được tạo trong `@BeforeEach`, mặc định `setupBefore = TEST_METHOD` có thể quá sớm vì listener tải user ở callback `beforeTestMethod`, trước JUnit `@BeforeEach`. Có thể trì hoãn việc dựng context:

~~~java
@Test
@WithUserDetails(
        value = "lan",
        userDetailsServiceBeanName = "accountDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void loadsUserAfterBeforeEachCreatesFixture() {
    assertThat(SecurityContextHolder.getContext()
            .getAuthentication().getName()).isEqualTo("lan");
}
~~~

Với `TEST_EXECUTION`, listener dựng context sau `@BeforeEach` và trước thân `@Test`. Hãy dùng chế độ này khi factory phụ thuộc fixture được tạo trong setup. Nếu user đã được seed sẵn trước phương thức test, giữ mặc định sẽ đơn giản hơn.

## 6. Tách cleanup của context khỏi cleanup của database

Có thể phân loại việc cleanup theo loại tài nguyên:

| Tài nguyên được test tạo | Cách cleanup thích hợp | Không nên kỳ vọng |
| --- | --- | --- |
| `SecurityContextHolder` đặt thủ công | `SecurityContextHolder.clearContext()` trong `finally` hoặc `@AfterEach` | Transaction rollback tự dọn ThreadLocal |
| `TestSecurityContextHolder` | `TestSecurityContextHolder.clearContext()` | Chỉ clear security holder sẽ dọn test holder |
| Database rows trong transaction test | Rollback transaction | Listener bảo mật xóa record |
| Database rows ngoài transaction | Script/repository cleanup rõ ràng | Rollback của transaction khác tự hoàn nguyên |
| File tạm | Xóa file trong `@AfterEach` hoặc resource helper | Database rollback xóa file |
| Cache/message broker/external API | Xóa key, purge queue hoặc dùng namespace test | Transaction database rollback hoàn nguyên dịch vụ ngoài |
| Executor/task do test tạo | Dừng executor và chờ tác vụ kết thúc | Context listener tự shutdown worker |

Một ví dụ test tự thiết lập context và tạo file tạm:

~~~java
class ManualContextAndFileTest {

    private Path temporaryFile;

    @BeforeEach
    void setUp() throws IOException {
        temporaryFile = Files.createTempFile("report-test-", ".txt");

        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "lan", "N/A",
                        AuthorityUtils.createAuthorityList("report:read"));

        TestSecurityContextHolder.setAuthentication(authentication);
    }

    @Test
    void processesReportForCurrentUser() {
        // Gọi service với principal "lan" và file tạm.
    }

    @AfterEach
    void tearDown() throws IOException {
        try {
            TestSecurityContextHolder.clearContext();
        } finally {
            if (temporaryFile != null) {
                Files.deleteIfExists(temporaryFile);
            }
        }
    }
}
~~~

Ở ví dụ này, test tự sở hữu cả test context và file. `finally` bảo đảm việc xóa file vẫn được thử ngay cả khi cleanup context ném exception. Trong dự án thật, có thể dùng JUnit `@TempDir` để quản lý thư mục tạm tự động; nguyên tắc vẫn là file và security context có hai cơ chế cleanup riêng.

Nếu chỉ dùng `@WithMockUser` và không sửa context, hãy để listener bảo mật dọn. Nếu test tự gọi `TestSecurityContextHolder.setAuthentication(...)`, dùng `TestSecurityContextHolder.clearContext()` vì API này dọn cả test holder và security holder. Nếu chỉ gọi `SecurityContextHolder.setContext(...)`, cleanup tương ứng là `SecurityContextHolder.clearContext()`.

## 7. @Sql và fixture database

`@Sql` cho phép chạy script SQL trước hoặc sau test. Nó phù hợp khi fixture gồm nhiều bảng hoặc cần dữ liệu có cấu trúc rõ ràng.

~~~java
@SpringBootTest
@Transactional
@Sql(
    scripts = "/sql/report-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class SqlFixtureSecurityTest {

    @Test
    @WithMockUser(username = "lan", authorities = "report:read")
    void readsSeededReport() {
        // Dữ liệu SQL có sẵn; listener security cung cấp principal "lan".
    }
}
~~~

Script SQL và security annotation phục vụ hai mục tiêu khác nhau: `@Sql` chuẩn bị database; `@WithMockUser` chuẩn bị danh tính test. Với `@Transactional`, script có thể tham gia transaction test theo transaction mode được cấu hình. Nếu script chạy độc lập hoặc dùng transaction riêng, dữ liệu có thể không bị rollback cùng test.

Có thể dùng script cleanup sau test:

~~~java
@Sql(
    scripts = "/sql/cleanup-report-fixture.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

Nếu đã dùng transaction rollback và script chạy trong cùng transaction, một cleanup script bổ sung có thể không cần thiết. Ngược lại, nếu dữ liệu được commit hoặc tạo ngoài transaction, cần cleanup tường minh. Kiểm tra transaction mode của `@Sql` thay vì giả định mọi script luôn chạy trong cùng transaction.

## 8. Đừng dùng @DirtiesContext để dọn mọi loại trạng thái

`@DirtiesContext` đánh dấu Spring `ApplicationContext` cần đóng và loại khỏi cache test context. Nó không phải công cụ tổng quát để:

- Rollback database rows.
- Xóa file hoặc cache entry.
- Dừng executor do test tạo.
- Dọn `SecurityContextHolder` trên mọi worker thread.
- Xóa session hoặc token đã được tạo ở hệ thống bên ngoài.

Dùng `@DirtiesContext` khi test thực sự làm thay đổi trạng thái của ApplicationContext khiến context không còn dùng lại an toàn. Với security context, dùng listener hoặc API clear phù hợp. Với database, dùng transaction rollback hoặc fixture cleanup. Với tài nguyên ngoài, cleanup đúng API của tài nguyên đó.

## 9. Ví dụ kết hợp MockMvc, dữ liệu nghiệp vụ và context

Một bài test HTTP có thể vừa cần user giả lập, vừa cần fixture database. Hai phần nên được chuẩn bị riêng:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ReportEndpointFixtureTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    AccountRepository accounts;

    @Autowired
    ReportRepository reports;

    @BeforeEach
    void seedReport() {
        Account lan = accounts.save(new Account("lan", true));
        accounts.save(new Account("mai", true));
        reports.save(new Report("r-100", lan, "Test report"));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "report:read")
    void readerCanReadExistingBusinessRecord() throws Exception {
        mockMvc.perform(get("/api/reports/r-100"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "mai", authorities = "report:read")
    void anotherUserCannotReadLansPrivateReport() throws Exception {
        mockMvc.perform(get("/api/reports/r-100"))
                .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ giả định endpoint kiểm tra quyền sở hữu báo cáo và trả `403` khi principal không phải chủ sở hữu. Dữ liệu account/report được tạo trong transaction test; security listener tạo principal cho từng phương thức test. Khi test kết thúc, transaction rollback dữ liệu, listener dọn context. Hai cleanup không phụ thuộc vào nhau.

Nếu endpoint yêu cầu CSRF chỉ cho request thay đổi trạng thái như POST/PUT/DELETE, không cần thêm `csrf()` vào GET. Khi test POST, dùng `.with(csrf())` cho ca hợp lệ và giữ ca thiếu token để xác minh bảo vệ CSRF.

## 10. Dữ liệu nghiệp vụ và principal có thể không cùng kiểu

Một lỗi thiết kế test là so sánh trực tiếp `authentication.getPrincipal()` với entity database:

~~~java
assertThat(authentication.getPrincipal()).isEqualTo(accountEntity);
~~~

Với `@WithMockUser`, principal thường là `UserDetails` mặc định, không phải entity `Account`. Nếu ứng dụng yêu cầu custom principal, hãy dùng `@WithUserDetails` với `UserDetailsService` trả về custom principal, hoặc viết annotation/factory dựa trên `@WithSecurityContext`.

Ví dụ cách diễn đạt đúng hơn khi chỉ cần liên kết bằng username:

~~~java
assertThat(authentication.getName()).isEqualTo(accountEntity.getUsername());
~~~

Nếu nghiệp vụ yêu cầu tenant ID, account ID hoặc quyền động từ database, hãy tạo fixture tương ứng và để service tải dữ liệu qua repository hoặc dùng custom principal có cấu trúc. Không nên gắn toàn bộ entity mutable vào một authentication giả lập nếu test không cần điều đó.

## 11. Thread, async và dữ liệu ngoài transaction

Trong ứng dụng Servlet, `SecurityContextHolder` mặc định gắn với thread. Transaction test cũng thường gắn với thread thực thi test. Khi test gửi tác vụ sang executor:

- Context không tự truyền sang worker nếu không dùng cơ chế truyền security context.
- Transaction của test không tự truyền sang worker thread.
- Worker có thể chạy sau khi transaction test đã rollback.
- File/cache/message được worker tạo có thể còn lại sau test nếu không cleanup.

Nếu cần kiểm tra tác vụ async, hãy chờ tác vụ hoàn thành trước khi test kết thúc, dùng `DelegatingSecurityContextExecutorService` hoặc wrapper tương ứng cho security context, và thiết kế transaction riêng cho worker. Đừng giả định transaction rollback của test thread sẽ hoàn nguyên các thao tác worker đã commit qua transaction khác.

Với test song song, dùng dữ liệu fixture có định danh riêng hoặc namespace riêng. Không chia sẻ một `SecurityContext` mutable giữa các test và không dùng username cố định nếu database test chạy song song mà có thể xung đột unique constraint.

## 12. Bảng chẩn đoán lỗi vòng đời

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@WithMockUser` chạy được nhưng service không tìm thấy account | Annotation không tạo entity database | Seed account trong fixture hoặc dùng `@WithUserDetails` |
| Database rollback xong nhưng test sau vẫn đọc user cũ | Security context không thuộc transaction | Kiểm tra listener hoặc clear đúng holder nếu tự đặt |
| Security context đã dọn nhưng record vẫn còn | Dữ liệu được commit hoặc nằm ngoài transaction test | Dùng rollback hoặc cleanup database rõ ràng |
| `@WithUserDetails` không tìm thấy user tạo ở `@BeforeEach` | Factory chạy theo `TEST_METHOD` trước setup | Chọn `setupBefore = TEST_EXECUTION` hoặc seed user sớm hơn |
| File/cache vẫn còn sau test | Transaction rollback không quản lý tài nguyên đó | Dùng `@TempDir`, `@AfterEach` hoặc cleanup service |
| Test chạy riêng PASS, suite FAIL | Dữ liệu dùng chung hoặc context thủ công chưa cleanup | Tách fixture, dọn holder, tránh static state |
| `@DirtiesContext` không xóa dữ liệu test | Annotation chỉ quản lý ApplicationContext | Dùng transaction/script/repository cleanup |
| Async worker không thấy principal | SecurityContext không được truyền qua thread | Dùng DelegatingSecurityContext wrapper |
| Async worker ghi dữ liệu không bị rollback | Worker dùng thread/transaction khác | Quản lý transaction worker và cleanup riêng |

## 13. Quy trình thiết kế một test có vòng đời rõ ràng

Trước khi viết test, xác định:

1. **Danh tính:** dùng `@WithMockUser`, `@WithUserDetails` hay authentication tự tạo?
2. **Dữ liệu nghiệp vụ:** test có cần account/report/entity thật không, hay chỉ cần principal và authority?
3. **Fixture setup:** dữ liệu được tạo bằng `@BeforeEach`, `@Sql`, factory hay fixture builder?
4. **Transaction:** dữ liệu có nằm trong transaction test và được rollback không?
5. **Security cleanup:** listener quản lý hay test tự đặt context và phải clear?
6. **External resources:** file/cache/message/executor nào cần cleanup riêng?
7. **Tính song song:** fixture có thể xung đột khi nhiều test chạy đồng thời không?

Một test tốt có điểm bắt đầu rõ, dữ liệu riêng, danh tính riêng và điểm kết thúc dọn đúng tài nguyên. Không cần một cơ chế cleanup duy nhất cho tất cả; cần chọn cơ chế đúng với loại trạng thái mà test tạo ra.

## 14. Bài thực hành

Tạo `ReportService.readOwnReport(reportId)` yêu cầu authority `report:read` và kiểm tra quyền sở hữu báo cáo:

1. Viết test dùng `@WithMockUser(username = "lan", authorities = "report:read")` nhưng không seed account. Quan sát service có thể thất bại ở bước tải entity dù authorization cho phép.
2. Thêm account `lan` và report thuộc account đó trong `@BeforeEach`. Dùng `@Transactional` để rollback dữ liệu sau test.
3. Viết test thứ hai dùng principal `mai` nhưng cố đọc report của `lan`; xác minh policy sở hữu từ chối.
4. Chuyển sang `@WithUserDetails` để principal được tải qua `UserDetailsService`; so sánh principal với custom principal/entity.
5. Tạo một test dùng `@Sql` để seed dữ liệu và xác minh transaction mode ảnh hưởng tới cleanup thế nào.
6. Tạo file tạm hoặc cache key trong test; xác minh rollback database không xóa tài nguyên đó và bổ sung cleanup riêng.
7. Tự đặt context bằng `TestSecurityContextHolder` rồi dọn bằng `TestSecurityContextHolder.clearContext()`; thử chỉ gọi `SecurityContextHolder.clearContext()` và giải thích trạng thái test holder còn lại.
8. Nếu gọi executor, chờ worker hoàn tất, truyền security context có chủ đích và cleanup tài nguyên do worker tạo.

Kết quả cần chứng minh hai điều riêng biệt: **người dùng hiện hành có được authorization cho phép không, và dữ liệu nghiệp vụ cần cho hành động có tồn tại trong vòng đời test không?** Sau đó, hãy chỉ ra cơ chế nào dọn context và cơ chế nào rollback/xóa fixture. Khi tách được hai vòng đời này, test sẽ ít phụ thuộc thứ tự chạy và dễ chẩn đoán hơn.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security API — WithSecurityContextTestExecutionListener](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithSecurityContextTestExecutionListener.html)
- [Spring Security API — TestSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/TestSecurityContextHolder.html)
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html)
- [Spring Framework — @TestExecutionListeners](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html)
