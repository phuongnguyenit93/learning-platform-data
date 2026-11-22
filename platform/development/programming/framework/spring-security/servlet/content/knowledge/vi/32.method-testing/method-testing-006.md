# Thời điểm thiết lập, dọn SecurityContext và tính độc lập giữa các ca

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Kiểm thử phương thức

## 1. Bài toán: cùng một phương thức, kết quả kiểm thử thay đổi vì context

Khi viết unit test hoặc integration test cho một service có `@PreAuthorize`, `@PostAuthorize` hoặc sử dụng `Authentication`, kết quả không chỉ phụ thuộc dữ liệu đầu vào. Nó còn phụ thuộc **`SecurityContext` đang được gắn với luồng thực thi (thread)**.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
public String readDocument() {
    return "document-visible";
}
~~~

Phương thức này cần được gọi thông qua **Spring-managed proxy** có bật method security. Nếu test đang có authority `DOCUMENT_READ` thì gọi thành công; nếu không đủ quyền thì bị từ chối. Nhưng còn một số tình huống khó thấy:

- `@BeforeEach` chạy **trước** hay **sau** khi Spring Security Test đặt danh tính giả?
- `@AfterEach` có chắc quan sát thấy context đã được dọn sạch hay không?
- Test A tạo authentication thủ công rồi quên xóa: test B có thể chịu tác động khi runner tái sử dụng thread.
- Test chạy song song, đổi `SecurityContextHolderStrategy` toàn cục hoặc dùng thread pool: danh tính có thể bị sai luồng hoặc bị giữ lại ngoài mong muốn.
- Dùng `@WithMockUser` ở method test có chứng minh cấu hình HTTP filter/login thật đúng không?

Bài này phân biệt **lifecycle của Spring TestContext và JUnit Jupiter**, hướng dẫn **thiết lập - sử dụng - cleanup** và trình bày test Java 17/Spring Boot 3/Spring Security 6 để các ca có thể chạy **độc lập, không phụ thuộc thứ tự**.

**Mục tiêu cuối:** Một test cho `@PreAuthorize` phải biểu diễn đúng user/authority cần thử, không vay mượn context của test khác và không để lại trạng thái có thể gây ảnh hưởng về sau.

## 2. SecurityContext, SecurityContextHolder và thread

### 2.1. SecurityContext là gì?

Trong Spring Security:

- `Authentication` đại diện danh tính hiện tại, trạng thái authentication và danh sách `GrantedAuthority`.
- `SecurityContext` là container giữ `Authentication`.
- `SecurityContextHolder` là điểm truy cập context hiện hành qua một **strategy**.
- Mặc định, strategy thường dùng **ThreadLocal**, tức là mỗi thread có context riêng. Đây không phải biến toàn cục duy nhất mà mọi thread đều chia sẻ theo mặc định.

~~~text
JUnit test thread A
  SecurityContextHolder
    -> context A
       -> Authentication(username=alice, DOCUMENT_READ)

JUnit test thread B
  SecurityContextHolder
    -> context B
       -> Authentication(username=bob, ROLE_EDITOR)
~~~

Bên trong test:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

String username = auth.getName();  // Chỉ khi auth khác null
~~~

Đây là **đoạn minh họa nằm trong một method**, chưa phải file Java chạy độc lập.

**Điểm cần nhớ:** `SecurityContextHolder.getContext()` có thể trả một context rỗng; `getAuthentication()` có thể `null`. Không được coi “có SecurityContext object” là bằng chứng user đã đăng nhập.

### 2.2. Vì sao ThreadLocal có thể gây leak?

JUnit có thể tái sử dụng worker thread giữa các ca. Nếu test tự gọi:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

mà không dọn, lần gọi trên **cùng thread** về sau có thể đọc lại authentication cũ, tùy chiến lược và lifecycle đang dùng. Điều này gây:

1. **False positive:** test không chuẩn bị quyền nhưng vẫn được quyền từ test trước.
2. **False negative:** test kiểm tra anonymous nhưng gặp user đã đăng nhập từ ca khác.
3. **Flaky tests:** đổi thứ tự hoặc chạy song song khiến test có lúc xanh, lúc đỏ.
4. **Sai mô phỏng production:** test không còn đo đúng quy tắc truy cập của request độc lập.

Không tự chia sẻ một `SecurityContext` mutable dưới dạng `static` giữa các test. Nếu cần đặt authentication thủ công, hãy tạo context mới, **dọn trong `finally`**, và ưu tiên hỗ trợ của `spring-security-test` thay vì tự thao tác ở mọi test.

## 3. Spring Security Test thiết lập context khi nào?

Spring Security Test cung cấp **`WithSecurityContextTestExecutionListener`** (thuộc TestContext Framework). Listener nhận các annotation như:

- `@WithMockUser`: tạo principal và authorities giả.
- `@WithAnonymousUser`: tạo anonymous authentication cho trường hợp được chỉ định.
- `@WithUserDetails`: lấy UserDetails từ `UserDetailsService` của ứng dụng test.
- Annotation tự định nghĩa dùng `@WithSecurityContext`.

Listener hỗ trợ thuộc tính **`setupBefore`**, với các giá trị `TestExecutionEvent.TEST_METHOD` và `TestExecutionEvent.TEST_EXECUTION`.

### 3.1. TEST_METHOD (mặc định)

Ví dụ:

~~~java
@Test
@WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
void canReadDocument() {
    // Spring Security Test đã thiết lập user trước test method.
}
~~~

Khi không ghi `setupBefore`, `@WithMockUser` dùng **`TEST_METHOD`**. Với JUnit Jupiter + `SpringExtension`, listener đặt security context tại sự kiện **beforeTestMethod**, tức là **trước `@BeforeEach`** của JUnit.

~~~text
SpringExtension / TestContextManager.beforeTestMethod
    -> WithSecurityContextTestExecutionListener thiết lập Authentication
JUnit @BeforeEach
JUnit @Test
JUnit @AfterEach
SpringExtension / TestContextManager.afterTestMethod
    -> WithSecurityContextTestExecutionListener dọn SecurityContext
~~~

Hệ quả: nếu `@BeforeEach` cần gọi service có `@PreAuthorize`, **thiết lập mặc định thường là lựa chọn đúng** vì danh tính đã tồn tại trong quá trình setup test fixture.

### 3.2. TEST_EXECUTION: chỉ sau @BeforeEach

Ví dụ:

~~~java
@Test
@WithMockUser(
    username = "bob",
    authorities = "DOCUMENT_READ",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void canReadAsBob() {
    // Context được thiết lập ngay trước khi bắt đầu @Test.
}
~~~

Với `TEST_EXECUTION`, listener thiết lập context tại sự kiện **beforeTestExecution**:

~~~text
SpringExtension / TestContextManager.beforeTestMethod
JUnit @BeforeEach
SpringExtension / TestContextManager.beforeTestExecution
    -> WithSecurityContextTestExecutionListener thiết lập Authentication
JUnit @Test
SpringExtension / TestContextManager.afterTestExecution
JUnit @AfterEach
SpringExtension / TestContextManager.afterTestMethod
    -> listener cleanup
~~~

Hệ quả: trong `@BeforeEach`, chưa có **authentication do annotation này tạo**. Đây có thể là mục đích mong muốn nếu setup phải chạy như anonymous, không vô tình được cấp quyền hoặc không chạm vào SecurityContext. Nhưng nếu setup gọi service được bảo vệ, test có thể thất bại ở `@BeforeEach` dù body test chưa chạy.

**Đừng hiểu sai:** `TEST_EXECUTION` không có nghĩa `SecurityContext` được tạo sau khi `@Test` bắt đầu. Nó được thiết lập **ngay trước** khi test method chạy, sau các `@BeforeEach` callbacks trong luồng lifecycle thông thường.

### 3.3. Bảng thời điểm

| Giai đoạn | `TEST_METHOD` (mặc định) | `TEST_EXECUTION` |
| --- | --- | --- |
| `@BeforeAll` | Không trông đợi user giả từ annotation của method. | Không trông đợi user giả. |
| `@BeforeEach` | Có thể truy cập authentication do annotation tạo. | Chưa có authentication do annotation tạo. |
| Body `@Test` | Có authentication. | Có authentication. |
| `@AfterEach` | Thường vẫn còn authentication lúc hook chạy. | Thường vẫn còn authentication lúc hook chạy. |
| Sau `TestContextManager.afterTestMethod` | Listener dọn context. | Listener dọn context. |

**Lưu ý thứ tự:** `@AfterEach` thuộc JUnit, còn cleanup của `WithSecurityContextTestExecutionListener` thường diễn ra ở **afterTestMethod**, sau hook `@AfterEach`. Vì vậy assertion “context phải rỗng ngay trong `@AfterEach`” là **sai giả định**. Muốn chứng minh tính độc lập, test trạng thái đầu ca không có annotation, kết hợp cleanup listener và không dựa vào thứ tự test.

Không dùng `@BeforeAll` để lấy `@WithMockUser` method-level. `@BeforeAll` có thể chạy trước sự kiện setup context cho từng method.

## 4. Tự động cleanup: ai chịu trách nhiệm và giới hạn

### 4.1. WithSecurityContextTestExecutionListener

Khi chạy với `SpringExtension` / Spring TestContext và `spring-security-test`:

1. Listener phát hiện annotation phù hợp.
2. Nó dựng security context cho test theo `setupBefore`.
3. Context được cung cấp qua `TestSecurityContextHolder` và `SecurityContextHolder` theo cơ chế Spring Security Test.
4. Sau test, listener dọn context (qua `TestSecurityContextHolder.clearContext()`) ở lifecycle thích hợp.

Điều đó giúp các test với `@WithMockUser` độc lập hơn mà không cần `@AfterEach` thủ công chỉ để xóa user giả. Tuy nhiên **test vẫn có thể leak trạng thái khác**: static fields, dữ liệu trong DB, cache, mutable singleton beans, thread pool tasks hoặc mocks không reset.

Không gọi `@DirtiesContext` chỉ để dọn `SecurityContextHolder`: annotation đó đánh dấu **Spring ApplicationContext** để tái tạo, tốn tài nguyên và không thay quy tắc quản lý ThreadLocal.

### 4.2. TestSecurityContextHolder khác SecurityContextHolder ở đâu?

`SecurityContextHolder` là API sử dụng trong ứng dụng. **`TestSecurityContextHolder`** là utility thuộc `spring-security-test`; nó hỗ trợ quản lý test context và tích hợp với công cụ test web.

Khi chủ động thiết lập context trong test:

~~~java
TestSecurityContextHolder.setContext(context);
~~~

Khi cleanup:

~~~java
TestSecurityContextHolder.clearContext();
~~~

Phương thức `clearContext()` của `TestSecurityContextHolder` dọn context test **và** context trên `SecurityContextHolder`. Nếu chỉ gọi `SecurityContextHolder.clearContext()` sau khi đã đưa context qua `TestSecurityContextHolder`, có thể để lại một bản test context khác được các helper của Spring Security Test tham chiếu.

**Ưu tiên:** annotation `@WithMockUser`/listener cho test thường; nếu bắt buộc tự set test context, dùng **một cơ chế nhất quán** và dọn bằng `finally`.

### 4.3. Cleanup không giải quyết mọi dạng isolation

Cleanup diễn ra trong lifecycle test mà listener quản lý. Không dựa vào nó để:

- Dọn `SecurityContext` đã tự cài lên **thread khác** và không được truyền/copy có kiểm soát.
- Khôi phục một **SecurityContextHolderStrategy` toàn cục** đã bị test thay đổi mà không restore.
- Xóa dữ liệu persistent trong database hoặc các singleton store.
- Khôi phục static `Authentication` do test tự giữ.
- Bảo đảm hậu quả từ một background task đã chạy **sau** khi test kết thúc.

Spring test cleanup là **điều kiện cần cho security context isolation**, không phải phép màu xóa mọi shared state.

## 5. Dự án Java 17 / Spring Boot 3.3.5: method security và JUnit Jupiter

Ví dụ đủ để chạy với Maven, Spring Security 6.x thuộc Spring Boot 3.3.5. Phiên bản này được chọn để minh họa cú pháp; production nên dùng bản có hỗ trợ và cập nhật bản vá.

**Chức năng:** service chỉ cho đọc với `DOCUMENT_READ`, chỉ cho sửa với `ROLE_EDITOR`, cùng các test cho authorized/denied/timing/cleanup. Không cần IdP hay database.

Cấu trúc:

~~~text
method-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── MethodContextApplication.java
    │   └── DocumentService.java
    └── test/java/demo/
        ├── DocumentServiceSecurityTest.java
        └── SecurityContextTimingTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>method-context-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

`spring-boot-starter-security` mang các module security cần thiết. `spring-boot-starter-test` gồm JUnit Jupiter, Spring Test, AssertJ và công cụ test; `spring-security-test` cấp `@WithMockUser`, `TestSecurityContextHolder` và TestExecutionListener tương ứng.

### 5.2. src/main/java/demo/MethodContextApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodContextApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` bật xử lý các annotation như `@PreAuthorize`. Không có annotation này, test có thể gọi service thành công dù đáng lẽ bị cấm, tạo **false positive** nếu chỉ assert output mà không kiểm tra nhánh từ chối.

### 5.3. src/main/java/demo/DocumentService.java

~~~java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOCUMENT_READ')")
    public String readDocument() {
        return "document-visible";
    }

    @PreAuthorize("hasRole('EDITOR')")
    public String editDocument() {
        return "document-edited";
    }
}
~~~

**Quan trọng:** test phải inject **Spring-managed bean** `DocumentService`. Nếu dùng `new DocumentService()` để gọi trực tiếp, đối tượng đó không đi qua proxy method security, nên `@PreAuthorize` có thể không được áp dụng. Tương tự, **self-invocation** từ một method trong bean gọi method được bảo vệ của chính nó có thể bypass proxy tùy cấu hình; cần thiết kế dịch vụ và test đúng đường gọi thực.

### 5.4. src/test/java/demo/DocumentServiceSecurityTest.java

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.TestSecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerMayRead() {
        assertThat(documents.readDocument())
            .isEqualTo("document-visible");
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorMayEdit() {
        assertThat(documents.editDocument())
            .isEqualTo("document-edited");
    }

    @Test
    @WithMockUser(username = "writer", authorities = "DOCUMENT_WRITE")
    void insufficientAuthorityIsDenied() {
        assertThatThrownBy(documents::readDocument)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void noAnnotationStartsWithoutAuthentication() {
        assertThat(
            SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }

    @Test
    void manualContextMustBeClearedInFinally() {
        try {
            var context = SecurityContextHolder.createEmptyContext();
            var authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                    "manual-reader",
                    "N/A",
                    List.of(
                        new SimpleGrantedAuthority("DOCUMENT_READ")
                    )
                );

            context.setAuthentication(authentication);
            TestSecurityContextHolder.setContext(context);

            assertThat(documents.readDocument())
                .isEqualTo("document-visible");

            assertThat(
                SecurityContextHolder.getContext()
                    .getAuthentication().getName()
            ).isEqualTo("manual-reader");
        } finally {
            // Dọn cả test holder lẫn application holder.
            TestSecurityContextHolder.clearContext();
        }

        assertThat(
            SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }
}
~~~

**Giải thích từng test:**

1. `readerMayRead`: annotation tạo principal giả và đúng `DOCUMENT_READ`; proxy method security cho phép gọi.
2. `editorMayEdit`: `roles = "EDITOR"` tạo authority `ROLE_EDITOR`, khớp `hasRole("EDITOR")`.
3. `insufficientAuthorityIsDenied`: `DOCUMENT_WRITE` không có nghĩa `DOCUMENT_READ`; kiểm tra Spring method security thực sự từ chối.
4. `noAnnotationStartsWithoutAuthentication`: không có `@WithMockUser`; trong luồng TestContext chuẩn đã được cleanup, test kỳ vọng không có authentication. **Không dựa vào thứ tự chạy** để test này “đến sau” một test cụ thể.
5. `manualContextMustBeClearedInFinally`: trình bày trường hợp bắt buộc tự dựng context; dùng `createEmptyContext()` và `try/finally`, không dùng context `static` chia sẻ.

`@WithMockUser` **không xác thực password hay gọi UserDetailsService**; chỉ tạo authentication giả cho test authorization. Để kiểm thử login thật, dùng integration test với authentication provider, `formLogin()` và HTTP filter chain tương ứng.

### 5.5. src/test/java/demo/SecurityContextTimingTest.java

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class SecurityContextTimingTest {

    private String nameSeenDuringBeforeEach;

    @BeforeEach
    void capturePrincipalBeforeTest() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        nameSeenDuringBeforeEach =
            authentication == null ? null : authentication.getName();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
    void defaultTestMethodIsAlreadySetBeforeBeforeEach() {
        assertThat(nameSeenDuringBeforeEach).isEqualTo("alice");

        assertThat(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()
        ).isEqualTo("alice");
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "DOCUMENT_READ",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void lateSetupHappensAfterBeforeEach() {
        assertThat(nameSeenDuringBeforeEach).isNull();

        assertThat(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()
        ).isEqualTo("bob");
    }

    @Test
    void withoutAnnotationThereIsNoUser() {
        assertThat(nameSeenDuringBeforeEach).isNull();
        assertThat(
            SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }
}
~~~

**Ý nghĩa:** hai test có `@WithMockUser` đều có authentication trong body `@Test`, nhưng chỉ setup mặc định làm `@BeforeEach` thấy authentication `alice`. Với `TEST_EXECUTION`, `@BeforeEach` chưa thấy `bob`. Test thứ ba xác nhận không tự thừa kế danh tính từ test khác. **Không cần đặt `@TestMethodOrder`** để ba test chạy theo một thứ tự.

### 5.6. Lệnh chạy và kết quả dự kiến

Trong thư mục có `pom.xml`:

~~~bash
mvn test
~~~

Kỳ vọng JUnit Jupiter chạy **8 test** (5 test của `DocumentServiceSecurityTest`, 3 test của `SecurityContextTimingTest`) và báo **0 failures, 0 errors** nếu cấu hình và dependency phù hợp. Đây là **kết quả dự kiến**, không phải log đã thực sự chạy.

Muốn chạy riêng một lớp:

~~~bash
mvn -Dtest=SecurityContextTimingTest test
~~~

Maven command trên minh họa kiểm tra thứ tự setup trước/sau `@BeforeEach`. Trên một số shell, cần quote giá trị option khi có ký tự đặc biệt; ở đây không có.

**Lưu ý phạm vi:** đây là test của **Spring service method security**, không tự chứng minh URL authorization, CSRF, Servlet filter order hay session hoạt động. Dùng MockMvc riêng nếu cần kiểm thử request HTTP.

## 6. @BeforeEach và @AfterEach: lỗi thiết kế thường gặp

### 6.1. Test fixture cần có danh tính trước setup

Ví dụ một `@BeforeEach` gọi service bảo vệ:

~~~java
@BeforeEach
void createFixtures() {
    // Giả sử fixtureService.prepareForCurrentUser() có @PreAuthorize.
    fixtureService.prepareForCurrentUser();
}
~~~

Đây là **đoạn code rời minh họa**, chưa đủ class/bean để chạy. Với `@WithMockUser` mặc định (`TEST_METHOD`), setup có thể gọi phương thức bảo vệ với user giả. Với `TEST_EXECUTION`, setup chạy **trước khi user giả được đặt**, nên việc gọi service có thể bị từ chối. Chọn thời điểm dựa trên điều kiện thật của test.

### 6.2. Setup không được dựa trên quyền test

Đôi khi cần tạo dữ liệu test như một thao tác quản trị **không thuộc hành vi user đang kiểm thử**. Nếu `@BeforeEach` vô tình được cấp quyền user nhờ setup mặc định, fixture có thể nhận identity sai hoặc không phát hiện được authorization bug.

Hai cách xử lý:

- Dùng `setupBefore = TEST_EXECUTION` để setup chạy trước khi annotation thiết lập user, nhưng vẫn phải viết fixture an toàn khi không có authentication.
- Tạo fixture qua repository/test data builder độc lập với current user, sau đó thực hiện hành động dưới user được khai báo tại body `@Test`.

Không dùng “test nào cũng admin” chỉ vì fixture cần quyền: dễ che mất lỗi phân quyền thật.

### 6.3. Không assert cleanup ngay trong @AfterEach

Ví dụ **sai giả định**:

~~~java
@AfterEach
void assertContextAlreadyCleared() {
    // Không nên bắt buộc điều kiện này khi dùng @WithMockUser:
    // assertThat(SecurityContextHolder.getContext()
    //     .getAuthentication()).isNull();
}
~~~

Vì listener thường dọn sau `@AfterEach`, assertion này có thể thất bại dù cleanup hoạt động đúng.

**Nếu `@AfterEach` cần truy cập danh tính để thu dọn fixture**, hãy xem timing thực tế; nên viết cleanup fixture độc lập khỏi principal nếu có thể, tránh việc trạng thái security ảnh hưởng teardown. Tách trách nhiệm: teardown dữ liệu trong JUnit hooks, teardown SecurityContext để Spring Security Test listener đảm nhiệm.

### 6.4. Có cần tự thêm @AfterEach clearContext()?

Với các test **chỉ dùng `@WithMockUser` và Spring TestContext đúng cách**, thường **không cần** thêm:

~~~java
@AfterEach
void cleanup() {
    SecurityContextHolder.clearContext();
}
~~~

Listener tự dọn trong lifecycle. Nếu test **tự set** context hoặc chạy code ngoài lifecycle listener, cần `try/finally`/teardown phù hợp. Khi có `TestSecurityContextHolder`, ưu tiên `TestSecurityContextHolder.clearContext()` để tránh một holder còn chứa authentication.

**Không** dùng cleanup thủ công bừa bãi trong `@BeforeEach` cùng `TEST_METHOD`, vì nó có thể xóa chính user giả mà listener vừa thiết lập, khiến test đột nhiên mất quyền.

## 7. @WithMockUser, @WithUserDetails và @WithSecurityContext

### 7.1. @WithMockUser

~~~java
@WithMockUser(
    username = "auditor",
    authorities = {"DOCUMENT_READ", "AUDIT_VIEW"}
)
~~~

Tạo authentication test với principal kiểu mock. Không truy vấn DB, không kiểm tra password, không tự phản ánh mọi custom principal của ứng dụng. Khi dùng `roles`, framework thêm role prefix mặc định `ROLE_`. Không nhập `ROLE_ADMIN` vào `roles` nếu annotation yêu cầu tên role không có prefix; dùng `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"` theo nhu cầu.

### 7.2. @WithUserDetails

Nếu hệ thống có `UserDetailsService` được cấu hình trong test context, có thể dùng:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void readsRealUserDetailsFromTestService() {
    // UserDetails được lookup từ bean UserDetailsService.
}
~~~

Đây là **snippet bổ sung**, không thuộc project chạy đủ ở mục 5 (ví dụ đó chưa định nghĩa `UserDetailsService` với user `alice`). `@WithUserDetails` phù hợp khi method phụ thuộc custom `UserDetails` hoặc attributes của user, nhưng vẫn **không chứng minh password login thực**.

Khi setup thời điểm `TEST_EXECUTION`, listener lookup và tạo context sau `@BeforeEach`. Điều này có thể hữu ích nếu fixture user được tạo trong `@BeforeEach` và cần tồn tại trước khi lookup. Ngược lại, nếu user được tạo trong test body thì lookup vẫn diễn ra quá sớm.

### 7.3. Custom @WithSecurityContext

Khi `@WithMockUser` không biểu diễn đủ authentication (ví dụ custom principal có `tenantId`), có thể tạo annotation sử dụng `@WithSecurityContext(factory = ...)` để dựng security context riêng. Factory phải tạo **context mới cho từng test** và authentication với authorities đúng schema. Không giữ một static context mutable hoặc chia sẻ chính Authentication object giữa các ca.

Mô hình:

~~~text
@WithTenantUser(tenant = "alpha", role = "READER")
        |
        v
WithSecurityContextFactory tạo principal + authorities
        |
        v
SecurityContextHolder.createEmptyContext()
        |
        v
TestSecurityContextHolder.setContext(...)
        |
        v
Test method -> listener cleanup
~~~

Đây là sơ đồ kiến trúc, không phải API code độc lập. Khi tạo annotation, phải dùng đúng retention/runtime, target và import tương ứng. Dù principal có tenant ID, service vẫn phải kiểm tra **resource thuộc tenant đó**; chỉ có attribute tenant không tự là authorization đủ.

## 8. Method security test khác với Servlet HTTP / MockMvc test

**Method test** gọi Spring-managed service trực tiếp:

~~~java
@WithMockUser(authorities = "DOCUMENT_READ")
@Test
void readAsAuthorizedUser() {
    assertThat(documents.readDocument())
        .isEqualTo("document-visible");
}
~~~

Nó kiểm tra AOP/method authorization. Nó **không** chạy toàn bộ HTTP filter chain.

**MockMvc test** gửi HTTP request giả qua MVC và, nếu tích hợp Spring Security, kiểm tra filter/session/CSRF/URL policies:

~~~java
// Đoạn minh họa trong test có MockMvc mvc được cấu hình với Security.
// Endpoint /api/documents phải tồn tại, đây không phải phần project mục 5.
mvc.perform(get("/api/documents")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("DOCUMENT_READ")
        )))
    .andExpect(status().isOk());
~~~

Với test MVC:

- `@AutoConfigureMockMvc` + Spring Boot Security test integration thường cấu hình filter; nếu dùng `MockMvcBuilders.standaloneSetup(...)`, bạn phải chủ động tích hợp `springSecurity()` và filter chain phù hợp.
- `@WithMockUser` đặt danh tính ở TestContext; `.with(user(...))` đặt principal cho **request MockMvc cụ thể**. Đừng nhầm chúng với login thật.
- `csrf()` của `SecurityMockMvcRequestPostProcessors` tạo CSRF token test hợp lệ cho POST khi cần; không dùng để tự phát token ở client production.
- `@WithMockUser` tự nó không chứng minh Servlet session lifecycle, redirect login, token repository hay logout.

Muốn kiểm thử controller và service cùng nhau, viết `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc test slice phù hợp; bảo đảm security config và filters thực sự tham gia. Đừng mock chính service được gắn `@PreAuthorize` rồi cho rằng test đã kiểm tra method interception: mock có thể bỏ qua method-security advice.

## 9. Chạy song song và chuyển thread: hai lớp isolation khác nhau

### 9.1. JUnit chạy song song

Nếu JUnit cấu hình parallel execution, test có thể chạy ở nhiều thread. Với strategy ThreadLocal mặc định, context của thread A không tự xuất hiện ở thread B. Điều này hữu ích nhưng **không thay cleanup**: thread pool có thể tái sử dụng thread.

Không thay `SecurityContextHolder.setStrategyName(SecurityContextHolder.MODE_GLOBAL)` trong một test để “đỡ mất quyền” khi chạy song song. `MODE_GLOBAL` chia sẻ context trên toàn JVM, có thể gây rò authentication giữa test và request khác.

`MODE_INHERITABLETHREADLOCAL` có thể truyền context cho thread con được tạo tại thời điểm nhất định nhưng không phù hợp để mặc định áp dụng với **thread pool**, vì thread sống lâu và được tái sử dụng. Đừng dựa vào nó làm giải pháp cho `@Async`/executor.

Nếu một test thực sự thay `SecurityContextHolderStrategy` toàn cục để thử behavior riêng, nó phải **khôi phục chiến lược cũ**, cô lập khỏi parallel test và hiểu tác động lên code đang chạy. Ưu tiên không đổi global strategy trong unit tests.

### 9.2. @Async, CompletableFuture và Executor

Giả sử test đang mang user `alice` trong thread JUnit, nhưng service gọi task chạy trên thread pool:

~~~text
JUnit thread: SecurityContext(alice)
    |
    +-> Executor worker thread: chưa chắc có context alice
~~~

Một raw `new Thread(...)` hoặc `CompletableFuture.supplyAsync(...)` không tự đảm bảo truyền SecurityContext theo cách an toàn. Spring Security cung cấp helper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable` và `DelegatingSecurityContextExecutor` để **thiết lập và dọn context quanh task**.

Các test async cần:

1. Xác định context có thực sự cần được truyền sang task không.
2. Dùng executor/wrapper đúng contract, không đặt context toàn cục.
3. Chờ task hoàn tất trong test và không để task chạy tiếp sau khi kết thúc test.
4. Assert user/authority trong worker thread nếu đó là yêu cầu.
5. Dọn thread-bound state trong `finally` khi bạn tự thực hiện propagation.
6. Tránh kiểm thử thứ tự ngẫu nhiên hoặc phụ thuộc scheduling không xác định.

**Cảnh báo:** test chỉ assert context trên thread JUnit **không chứng minh** behavior của service thực hiện authorization trong thread khác.

### 9.3. Phân biệt SecurityContext leak với dữ liệu test leak

Ngay cả khi SecurityContext đã được dọn, hai test cùng dùng `@SpringBootTest` có thể chia sẻ **ApplicationContext cache**, database, filesystem, singleton hoặc in-memory repository. Ví dụ test A tạo bản ghi của Alice và không rollback, test B có thể gặp dữ liệu đó.

Giải pháp tùy nguồn state:

- DB: transaction rollback/test cleanup hoặc fixture cô lập.
- Stateful bean: reset qua API test/fixture, tạo bean mới hay tổ chức context riêng hợp lý.
- Mockito mock: reset hoặc khởi tạo lại theo integration của Spring Test.
- Static variables: hạn chế, reset rõ ràng nếu không thể tránh.
- SecurityContext: dùng listener + `TestSecurityContextHolder.clearContext()` khi thao tác thủ công.
- Async work: chờ task xong và cleanup context trong worker.

**`@DirtiesContext` là công cụ cuối cùng** nếu thực sự cần tái tạo ApplicationContext; nó không phải thay thế cho việc code test kiểm soát trạng thái có thể thay đổi.

## 10. Anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Cách đúng |
| --- | --- | --- |
| Tự gọi `SecurityContextHolder.getContext().setAuthentication(...)` rồi không dọn. | Leak khi thread được tái sử dụng. | Dùng `@WithMockUser` hoặc context mới + `try/finally`. |
| `@BeforeEach` gọi service bảo vệ nhưng annotation đặt `TEST_EXECUTION`. | Setup chưa có user được khai báo. | Dùng `TEST_METHOD` hoặc tách fixture khỏi authentication. |
| Assert context rỗng trong `@AfterEach` của test có `@WithMockUser`. | Hiểu nhầm thời điểm cleanup listener. | Kiểm tra lifecycle thực; dọn bởi TestExecutionListener sau test. |
| Dùng `@TestMethodOrder` để test B kế thừa identity của test A. | Test phụ thuộc thứ tự và tạo lỗi tiềm ẩn. | Mỗi test khai báo identity riêng. |
| Dùng `new DocumentService()` test `@PreAuthorize`. | Bỏ qua proxy, false positive. | Autowire Spring-managed service. |
| Chỉ test case được phép, không test denied. | `@EnableMethodSecurity` tắt vẫn có thể khiến test xanh. | Có test `AccessDeniedException` cho quyền thiếu. |
| Dùng `@WithMockUser` để tuyên bố login/password provider đúng. | Không kiểm tra authentication thật. | Integration test login/filter riêng. |
| Dùng `MODE_GLOBAL` hoặc static SecurityContext để chia sẻ trong test suite. | Danh tính lẫn giữa ca/thread. | ThreadLocal + context per test + cleanup. |
| Tự assume `@WithMockUser` được truyền vào executor thread. | Task có thể không có auth hoặc dùng context khác. | Propagation wrapper có cleanup + async test. |
| Dùng `@DirtiesContext` cho mọi test để “xóa user”. | Test chậm, không xử lý đúng leak thread. | Dựa listener và dọn state cụ thể. |
| Dùng một role quá rộng cho mọi test. | Bỏ lỡ kiểm tra nguyên tắc least privilege. | Tạo mỗi test role/authority tối thiểu đúng tình huống. |
| `@WithUserDetails` nhưng test context không có user. | Lookup thất bại trước body `@Test`. | Cấu hình UserDetailsService và fixture đúng lifecycle. |

## 11. Checklist QA để test độc lập thật sự

Trước khi merge một test class có method security:

1. `spring-security-test` đã nằm trong **test scope**; TestContext/Extension được áp dụng đúng.
2. `@EnableMethodSecurity` được bật trong context nếu đang test `@PreAuthorize`.
3. Service được gọi qua **bean/proxy**, không tạo bằng `new`.
4. Mỗi test tự khai báo `@WithMockUser`, `@WithUserDetails` hoặc authentication factory phù hợp.
5. Chọn đúng `setupBefore`: cần context trong `@BeforeEach` thì dùng mặc định `TEST_METHOD`; chỉ cần trong test body thì xem xét `TEST_EXECUTION`.
6. Không giả định context đã được dọn ở `@AfterEach`; hiểu Spring listener dọn sau hook này.
7. Không đặt shared `SecurityContext` hoặc `Authentication` mutable vào static fields.
8. Mọi setup thủ công có **`finally`** dọn cả test holder khi cần.
9. Có cả test **được phép** và **bị từ chối**, tránh test xanh giả khi method security vô hiệu.
10. Không có sự phụ thuộc vào thứ tự test hoặc thread chạy.
11. Nếu chạy async, xác minh propagation và hoàn tất task; không dùng strategy global tùy tiện.
12. Nếu có DB/stateful services, cô lập fixture độc lập với security context.
13. Dùng MockMvc riêng cho URL authorization/CSRF/session thay vì suy từ service test.
14. Không đưa password, token, session ID hoặc thông tin thật vào log test.
15. Có thể chạy lặp lại class test và cả suite theo thứ tự khác mà không cần reset thủ công ngoài contract fixture.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với `@WithMockUser` mặc định, user được thiết lập trước hay sau `@BeforeEach`?

**Trả lời:** Trước `@BeforeEach`, qua TestContext `beforeTestMethod` (`TEST_METHOD`).

**Câu 2.** Muốn `@BeforeEach` không có user giả nhưng body `@Test` có user, phải làm gì?

**Trả lời:** Đặt `setupBefore = TestExecutionEvent.TEST_EXECUTION`. Khi đó listener thiết lập context ở `beforeTestExecution` sau setup JUnit.

**Câu 3.** Vì sao không assert SecurityContext rỗng ngay trong `@AfterEach`?

**Trả lời:** Listener của Spring Security Test thường dọn ở `afterTestMethod`, sau hook `@AfterEach` theo lifecycle JUnit/SpringExtension.

**Câu 4.** `@WithMockUser(username = "alice")` có xác minh password Alice từ DB không?

**Trả lời:** Không. Nó tạo authentication giả cho kiểm thử. Muốn test login thật phải kiểm thử authentication provider/HTTP flow riêng.

**Câu 5.** Vì sao test đọc document phải dùng `@Autowired DocumentService`?

**Trả lời:** `@PreAuthorize` được áp dụng bởi Spring method-security AOP/proxy. Tạo service bằng `new` có thể bypass security advice.

**Câu 6.** `SecurityContextHolder.clearContext()` có luôn đủ nếu test dùng `TestSecurityContextHolder.setContext()`?

**Trả lời:** Không nên dựa vào điều đó. Khi dùng test holder, gọi `TestSecurityContextHolder.clearContext()` để dọn cả hai holder theo contract của utility.

**Câu 7.** Test chạy ở thread JUnit có user Alice thì `CompletableFuture` trên executor mặc nhiên cũng có Alice không?

**Trả lời:** Không. ThreadLocal context không tự truyền an toàn qua mọi executor; dùng propagation wrapper/context-aware executor phù hợp và cleanup.

**Câu 8.** `@DirtiesContext` và dọn SecurityContext khác nhau thế nào?

**Trả lời:** `@DirtiesContext` yêu cầu Spring làm mới ApplicationContext cached. Dọn SecurityContext xóa authentication gắn thread/test; đây là hai loại state khác nhau.

---

**Kết luận:** Kiểm thử phương thức trong Spring Security Servlet phải kiểm soát **thời điểm đặt Authentication**, **thời điểm cleanup**, và **tính cô lập của từng test**. `@WithMockUser` mặc định được thiết lập **trước `@BeforeEach`**; `TEST_EXECUTION` được thiết lập **sau `@BeforeEach`, ngay trước body `@Test`**. Listener của Spring Security Test dọn context sau test; với setup thủ công, dùng context mới và `finally`. Duy trì cả test authorized và denied, không chia sẻ context mutable, không phụ thuộc thứ tự, và kiểm thử async/HTTP ở đúng lớp tương ứng.