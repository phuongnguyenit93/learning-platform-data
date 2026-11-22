# Kiểm thử biểu thức theo tham số, chủ sở hữu và thuộc tính đầu vào trong Spring Security

Bài thực hành này tập trung vào **kiểm thử quyền truy cập ở tầng phương thức** (method security), khi quyết định cho phép hoặc từ chối phụ thuộc vào tham số gọi hàm, **chủ sở hữu thực tế của tài nguyên**, và các thuộc tính của đối tượng đầu vào. Ví dụ dùng Java 17, Spring Security 6.x, JUnit 5 và Spring Security Test; các khái niệm `@PreAuthorize`, `@PostAuthorize` và `@EnableMethodSecurity` cũng áp dụng cho Spring Security 7.x.

## 1. Mục tiêu và ranh giới kiểm thử

Sau bài học, bạn có thể:

- Kiểm tra biểu thức SpEL tham chiếu đối số phương thức như `#username`, `#id`, `#input.title`, kết hợp với `authentication.name` và `hasAuthority(...)`.
- Chứng minh người dùng chỉ thao tác trên tài nguyên **thuộc quyền sở hữu của họ theo dữ liệu đáng tin cậy**, không chỉ theo `owner` do client khai trong request.
- Kiểm thử cả trường hợp được phép và bị chặn: đúng/sai tham số, tài nguyên của người khác, thiếu quyền, dữ liệu đầu vào rỗng/sai và người dùng ẩn danh.
- Phân biệt `@PreAuthorize` (quyết định **trước** khi thực thi phương thức) với `@PostAuthorize` (kiểm tra **sau** khi đã có kết quả).
- Viết test gọi **Spring bean đã được proxy** và xác nhận phương thức bị chặn không tạo ra thay đổi dữ liệu.

Giả sử hệ thống có tài liệu số 10 thuộc `alice` và tài liệu số 20 thuộc `bob`. Nếu `alice` gửi yêu cầu sửa tài liệu 20 kèm `declaredOwner="alice"`, bài kiểm thử phải chứng minh hệ thống vẫn **từ chối**. Đây là tình huống kiểm tra vượt quyền theo ID (IDOR/BOLA).

## 2. Cơ chế hoạt động và dữ liệu nào đáng tin

Bật bảo vệ phương thức bằng `@EnableMethodSecurity` trên cấu hình Spring. Khi lời gọi đi qua proxy của bean, Spring Security lấy `Authentication` từ `SecurityContext`, lấy tham số của lời gọi, đánh giá SpEL và quyết định có cho thực thi thân phương thức hay không.

| Thành phần biểu thức | Nguồn giá trị | Điều cần kiểm thử |
| --- | --- | --- |
| `#username`, `#id`, `#input` | Tham số phương thức do caller đưa vào | Đúng/sai giá trị, `null`, biên, giả mạo |
| `authentication.name` | Danh tính của người đang đăng nhập | So khớp với tham số hoặc chủ sở hữu |
| `hasAuthority('DOC_WRITE')` | Authorities trên `Authentication` | Có và không có quyền cụ thể |
| `@docPolicy.isOwner(authentication, #id)` | Bean chính sách tra cứu chủ sở hữu từ kho dữ liệu tin cậy | ID của mình, ID người khác, ID không tồn tại |
| `#input.declaredOwner`, `#input.title` | Thuộc tính trên đối tượng client gửi | Phù hợp/không phù hợp, chuỗi rỗng, quá dài |
| `returnObject.owner` | Thuộc tính trên đối tượng đã được phương thức trả về | Có/không có quyền xem kết quả |

Ví dụ:

~~~java
@PreAuthorize("#username == authentication.name")
public String profile(@P("username") String username) { /* ... */ }

@PreAuthorize("@docPolicy.isOwner(authentication, #id)")
public String read(@P("id") long id) { /* ... */ }

@PreAuthorize("hasAuthority('DOC_WRITE') && " +
              "@docPolicy.isOwner(authentication, #id) && " +
              "#input != null && #input.title != null")
public void update(@P("id") long id, @P("input") EditInput input) { /* ... */ }
~~~

Đây là **minh họa các phần của phương thức**, không phải ba lớp Java độc lập. `@P` (gói `org.springframework.security.access.method`) gắn tên tham số rõ ràng cho SpEL. Với mã biên dịch có cờ `-parameters`, Spring còn có thể tìm tên tham số qua reflection; `@P` giúp ví dụ không phụ thuộc thiết lập compiler. Khi chỉ có một số tham số đơn giản, SpEL cũng hỗ trợ truy cập theo vị trí như `#p0`, nhưng tên có ý nghĩa dễ bảo trì hơn.

**Nguyên tắc tin cậy:** `#input.declaredOwner == authentication.name` chỉ chứng minh client đã *khai* tên người sở hữu trùng tên đăng nhập. Điều đó **không** chứng minh tài liệu đích thật sự thuộc người dùng. Quy tắc an toàn phải đối chiếu `#id` với chủ sở hữu lưu trên server (hoặc bằng chính sách kiểm tra tài nguyên tương đương) trước khi sửa.

## 3. Ví dụ chạy được: một Spring context nhỏ, không cần server HTTP

Tạo dự án Maven gồm hai file:

~~~text
method-expressions-test/
├── pom.xml
└── src/test/java/com/example/security/MethodExpressionsTest.java
~~~

`pom.xml` — dùng Spring Boot 3.5.7 để quản lý phiên bản thư viện tương thích, nhưng chạy test trên Spring Test context thuần, không khởi động ứng dụng web:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-expressions-test</artifactId>
    <version>1.0.0</version>
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
</project>
~~~

`src/test/java/com/example/security/MethodExpressionsTest.java` — tất cả lớp hỗ trợ được đặt trong cùng file để dễ chạy độc lập:

~~~java
package com.example.security;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(MethodExpressionsTest.TestConfig.class)
class MethodExpressionsTest {

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class TestConfig {
        @Bean
        DocRepository repository() {
            return new DocRepository();
        }

        @Bean("docPolicy")
        DocPolicy docPolicy(DocRepository repository) {
            return new DocPolicy(repository);
        }

        @Bean
        DocumentService documentService(DocRepository repository) {
            return new DocumentService(repository);
        }
    }

    public static class DocView {
        private final String owner;
        private final String title;

        public DocView(String owner, String title) {
            this.owner = owner;
            this.title = title;
        }

        public String getOwner() { return owner; }
        public String getTitle() { return title; }
    }

    public static class EditInput {
        private final String declaredOwner;
        private final String title;

        public EditInput(String declaredOwner, String title) {
            this.declaredOwner = declaredOwner;
            this.title = title;
        }

        public String getDeclaredOwner() { return declaredOwner; }
        public String getTitle() { return title; }
    }

    public static class DocRepository {
        private final Map<Long, DocView> docs = new HashMap<>();

        public void reset() {
            docs.clear();
            docs.put(10L, new DocView("alice", "Alpha"));
            docs.put(20L, new DocView("bob", "Beta"));
        }

        public DocView find(long id) {
            return docs.get(id);
        }

        public String ownerOf(long id) {
            DocView doc = find(id);
            return doc == null ? null : doc.getOwner();
        }

        public void rename(long id, String title) {
            DocView before = docs.get(id);
            docs.put(id, new DocView(before.getOwner(), title));
        }
    }

    public static class DocPolicy {
        private final DocRepository repository;

        public DocPolicy(DocRepository repository) {
            this.repository = repository;
        }

        public boolean isOwner(Authentication authentication, long id) {
            String owner = repository.ownerOf(id);
            return owner != null
                    && authentication != null
                    && owner.equals(authentication.getName());
        }
    }

    public static class DocumentService {
        private final DocRepository repository;

        public DocumentService(DocRepository repository) {
            this.repository = repository;
        }

        // Quyền dựa vào một tham số so với danh tính đã xác thực.
        @PreAuthorize("#username == authentication.name")
        public String profile(@P("username") String username) {
            return "profile:" + username;
        }

        // Quyền sở hữu đến từ repository; caller chỉ cung cấp ID.
        @PreAuthorize("@docPolicy.isOwner(authentication, #id)")
        public String readTitle(@P("id") long id) {
            return repository.find(id).getTitle();
        }

        // Phải đủ quyền + là chủ sở hữu thật + thuộc tính input hợp lệ.
        @PreAuthorize("hasAuthority('DOC_WRITE')"
                + " && @docPolicy.isOwner(authentication, #id)"
                + " && #input != null"
                + " && #input.declaredOwner == authentication.name"
                + " && #input.title != null"
                + " && !#input.title.isBlank()"
                + " && #input.title.length() <= 120")
        public void rename(@P("id") long id, @P("input") EditInput input) {
            repository.rename(id, input.getTitle());
        }

        // Chỉ dùng cho truy vấn không gây tác dụng phụ.
        @PostAuthorize("returnObject != null"
                + " && returnObject.owner == authentication.name")
        public DocView viewAfterRead(@P("id") long id) {
            return repository.find(id);
        }
    }

    @Autowired
    DocumentService service; // Bean Spring đã được method-security proxy.

    @Autowired
    DocRepository repository;

    @BeforeEach
    void resetFixtures() {
        repository.reset();
    }

    @Test
    @WithMockUser(username = "alice")
    void expressionFromParameterAllowsMatchingIdentityOnly() {
        assertEquals("profile:alice", service.profile("alice"));
        assertThrows(AccessDeniedException.class,
                () -> service.profile("bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownershipComesFromTrustedRepository() {
        assertEquals("Alpha", service.readTitle(10L));
        assertThrows(AccessDeniedException.class,
                () -> service.readTitle(20L));
        assertThrows(AccessDeniedException.class,
                () -> service.readTitle(999L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_WRITE")
    void validOwnerAuthorityAndInputAllowChange() {
        service.rename(10L, new EditInput("alice", "New title"));
        assertEquals("New title", repository.find(10L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_WRITE")
    void forgingOwnerInBodyCannotChangeForeignResource() {
        assertThrows(AccessDeniedException.class,
                () -> service.rename(20L, new EditInput("alice", "Attack")));
        assertEquals("Beta", repository.find(20L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_WRITE")
    void invalidInputIsRejectedBeforeMutation() {
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("bob", "Valid")));
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("alice", " ")));
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("alice", null)));
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, null));
        assertEquals("Alpha", repository.find(10L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerWithoutWriteAuthorityCannotUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("alice", "New")));
        assertEquals("Alpha", repository.find(10L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeUsesActualReturnedObject() {
        assertEquals("alice", service.viewAfterRead(10L).getOwner());
        assertThrows(AccessDeniedException.class,
                () -> service.viewAfterRead(20L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserCannotReadOwnedResource() {
        assertThrows(AccessDeniedException.class,
                () -> service.readTitle(10L));
    }
}
~~~

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven đã cài đặt, chạy:

~~~bash
mvn test
~~~

**Kết quả mong đợi:** Maven kết thúc thành công, có 8 phương thức `@Test` được chạy và không có assertion thất bại. Maven có thể in log khác nhau tùy phiên bản/plugin; bài này không phụ thuộc một chuỗi stdout cố định. Spring Security chặn các lời gọi không đủ điều kiện bằng exception thuộc họ `AccessDeniedException`; bản thân test xác nhận exception đó bằng `assertThrows`.

### Vì sao ví dụ này kiểm tra authorization thực sự?

1. `@SpringJUnitConfig` tạo ApplicationContext, `@EnableMethodSecurity` đăng ký bộ chặn phương thức. `service` được `@Autowired` từ Spring nên lời gọi đi qua proxy. Nếu dùng `new DocumentService(repository)` để test, annotation sẽ không được áp dụng và test có thể cho kết quả sai.
2. `@WithMockUser` tạo `Authentication` cho từng test với `username`/`authorities` chỉ định. Nó không yêu cầu có tài khoản thật trong database. Spring Security Test đặt/thu dọn `SecurityContext` quanh quá trình chạy test.
3. `DocPolicy` tra cứu chủ sở hữu theo `id` từ `DocRepository`. Đầu vào `declaredOwner` có thể bị giả mạo nhưng không sửa được giá trị chủ sở hữu ở repository.
4. `@BeforeEach` khôi phục dữ liệu ban đầu; test cập nhật hợp lệ không làm test sau bị phụ thuộc thứ tự thực thi.
5. Với các ca bị từ chối, test kiểm cả exception và trạng thái tài liệu giữ nguyên. Chỉ xác nhận HTTP status/exception mà không kiểm tác dụng phụ có thể bỏ sót lỗi bảo mật.

## 4. Phân tích chính xác từng nhóm biểu thức

### 4.1. So sánh tham số với danh tính

Biểu thức `#username == authentication.name` phải được test ít nhất với chuỗi trùng, chuỗi khác và `null`. Khi `username` khác tên đăng nhập, phương thức phải bị chặn **trước** khi tạo kết quả. So sánh phân biệt hoa/thường nếu chưa có quy tắc chuẩn hóa: `"Alice"` và `"alice"` là hai chuỗi khác nhau. Không tự thêm logic `toLowerCase()` trong biểu thức nếu danh tính ứng dụng chưa có quy ước chuẩn hóa rõ ràng.

Đối với ID số, tránh so sánh trực tiếp `Long` với `String` từ principal khi không cùng miền dữ liệu. Hãy lấy user ID từ custom principal phù hợp hoặc gọi policy có kiểu tham số cụ thể; không mặc định `authentication.name` là ID database.

### 4.2. Chủ sở hữu: nguồn tin cậy nằm ở server

Cùng một người dùng `alice` có thể gọi:

- `readTitle(10)`: repository trả `owner="alice"` nên cho phép.
- `readTitle(20)`: repository trả `owner="bob"` nên từ chối.
- `readTitle(999)`: tài nguyên không tồn tại, policy trả `false` nên từ chối.

Chủ sở hữu thực không nên suy ra từ `EditInput.getDeclaredOwner()` hoặc query parameter do caller có thể thay đổi. Trường `declaredOwner` trong ví dụ chỉ dùng để dạy cách kiểm thử thuộc tính đầu vào; trong thiết kế sản xuất, tốt hơn là **không cho client khai trường owner nếu không cần thiết**. Với API đa tenant, thêm kiểm tra tenant vào policy, chẳng hạn `document.tenantId == currentTenantId`, rồi viết test truy cập chéo tenant.

Nếu policy cần database, có thể mock repository để điều khiển các owner khác nhau trong test, nhưng ít nhất một kiểm thử tích hợp nên kiểm đường đi thực: security proxy → policy bean → repository → service.

### 4.3. Thuộc tính đối tượng đầu vào

Biểu thức của `rename` kết hợp nhiều điều kiện với `&&`:

1. Người dùng có authority `DOC_WRITE`.
2. Tài liệu được tra từ `id` thật sự thuộc người dùng.
3. `input` khác `null`, người client khai không mâu thuẫn với danh tính.
4. `title` khác `null`, không toàn khoảng trắng, độ dài tối đa 120 ký tự.

SpEL đánh giá `&&` theo kiểu ngắn mạch, nên kiểm tra `#input != null` đứng trước truy cập `#input.title` để tránh truy cập thuộc tính trên `null`. Test trường hợp `null` giúp phát hiện biểu thức thiếu guard. Dù vậy, **authorization không thay thế validation**: độ dài, định dạng, ký tự hợp lệ thường thuộc Bean Validation và nghiệp vụ; biểu thức authorization nên chứa các điều kiện thực sự liên quan đến quyền.

Kiểm tra cả trường hợp gần ranh giới, ví dụ tiêu đề 120 ký tự được phép và 121 ký tự bị từ chối nếu đó là quy tắc đã được chọn. Có thể mở rộng bằng `@ParameterizedTest` để tránh lặp test, nhưng cần giữ rõ kỳ vọng security và validation độc lập.

### 4.4. Quyền theo vai trò/authority

`@WithMockUser(roles = "ADMIN")` sẽ tạo authority `ROLE_ADMIN`. Ngược lại, `@WithMockUser(authorities = "DOC_WRITE")` tạo đúng authority `DOC_WRITE`, không tự thêm tiền tố `ROLE_`. Do đó `hasRole('ADMIN')` khác `hasAuthority('ADMIN')`, và test phải mô phỏng chính xác cách ứng dụng ánh xạ JWT, session hoặc user database sang authorities.

Ca `ownerWithoutWriteAuthorityCannotUpdate` rất quan trọng: **sở hữu tài nguyên chưa chắc đã đủ quyền sửa**. Điều kiện kết hợp phải bị từ chối nếu thiếu một vế, kể cả owner đúng và input hoàn toàn hợp lệ.

### 4.5. Kiểm tra đối tượng trả về

`@PostAuthorize("returnObject.owner == authentication.name")` phù hợp với thao tác **đọc** khi chỉ sau khi lấy tài nguyên mới biết owner. Biểu thức được đánh giá sau thân phương thức; nếu không đạt, Spring Security không cho caller nhận kết quả và ném exception từ chối.

Không dùng cách này như lớp bảo vệ duy nhất cho phương thức **ghi dữ liệu**: cập nhật hoặc gửi thông báo có thể đã xảy ra trước khi `@PostAuthorize` chặn kết quả. Với thao tác ghi, hãy kiểm tra quyền trước khi thay đổi bằng `@PreAuthorize` hoặc policy trong transaction, tùy mô hình nhất quán dữ liệu.

## 5. Ma trận ca kiểm thử bắt buộc

| Actor / authority | Tài nguyên hoặc tham số | Thuộc tính đầu vào | Kỳ vọng |
| --- | --- | --- | --- |
| `alice` | `profile("alice")` | — | Cho phép |
| `alice` | `profile("bob")` | — | Từ chối |
| `alice` | Tài liệu 10, owner thật `alice` | — | Cho đọc |
| `alice` | Tài liệu 20, owner thật `bob` | — | Từ chối |
| `alice` | ID 999 không tồn tại | — | Không cấp quyền |
| `alice` + `DOC_WRITE` | Tài liệu 10 | `declaredOwner="alice"`, title hợp lệ | Cho sửa |
| `alice` + `DOC_WRITE` | Tài liệu 20 | Giả `declaredOwner="alice"` | Từ chối, không đổi dữ liệu |
| `alice` không có `DOC_WRITE` | Tài liệu 10 | Title hợp lệ | Từ chối |
| `alice` + `DOC_WRITE` | Tài liệu 10 | `declaredOwner="bob"` | Từ chối |
| `alice` + `DOC_WRITE` | Tài liệu 10 | `input=null` hoặc `title=null` / toàn dấu cách | Từ chối |
| Anonymous | Tài liệu 10 | — | Từ chối |
| `alice` | `viewAfterRead(20)` | Result có owner `bob` | `@PostAuthorize` từ chối |

Các hàng này kiểm **đường cho phép** và **đường từ chối** cho từng vế của biểu thức. Một bài test chỉ dùng `@WithMockUser` rồi gọi một phương thức trả dữ liệu thành công không chứng minh rằng điều kiện ownership, tham số hoặc thuộc tính đầu vào đang được thực thi.

## 6. Các lỗi dễ gặp và cách phát hiện

**Test không đi qua proxy.** Tạo service bằng `new`, gọi trực tiếp bean target, gọi một phương thức được bảo vệ thông qua `this.method()` trong cùng bean, hoặc gọi private/final method khiến advice proxy không chạy như mong đợi. Khắc phục bằng test Spring context, inject bean, đặt phương thức bảo vệ ở bean/lời gọi phù hợp. Nếu test trái phép vẫn trả dữ liệu thay vì ném `AccessDeniedException`, kiểm tra `@EnableMethodSecurity`, bean proxy và đường đi của lời gọi trước.

**Sai tên tham số SpEL.** Viết `#documentId` nhưng phương thức nhận `id` mà không có `@P("documentId")` hoặc thông tin `-parameters`. Khi đó biểu thức có thể không thấy giá trị như mong đợi. Giữ tên nhất quán, khai `@P` và thêm ca test cho nhánh được phép để phát hiện tình trạng luôn từ chối vì lỗi binding.

**Chỉ tin owner từ request.** `@PreAuthorize("#input.owner == authentication.name")` có thể bị vượt qua nếu client sửa `owner` trong payload. Test phản ví dụ: user `alice` gửi ID thuộc `bob` nhưng khai `owner="alice"`. Quy tắc đúng phải hỏi server về owner của **ID được yêu cầu**.

**Chỉ test exception.** Nếu code ghi dữ liệu trước khi quyền bị kiểm tra, request vẫn có thể bị từ chối nhưng hệ thống đã thay đổi trạng thái. Bổ sung `assertEquals`/`verify(..., never())` cho các phương thức ghi, thông điệp được gửi hoặc số bản ghi thay đổi. Kèm theo test ranh giới transactional khi cần.

**Mock mất chính sách thật.** Mock toàn bộ service có `@PreAuthorize` rồi xác nhận mock trả 200 không kiểm được authorization ở service. Mock phụ thuộc ở phía sau service (repository, policy dependency), để lời gọi vẫn đi qua proxy và biểu thức thực.

**Principal khác kiểu.** `@WithMockUser` tạo principal chuẩn của Spring Security; nếu ứng dụng dùng custom `UserDetails`/JWT claims, test loại này có thể không phản ánh principal thật. Dùng `@WithUserDetails` khi có `UserDetailsService`, hoặc `@WithSecurityContext` tùy chỉnh để tạo `Authentication` phù hợp; bổ sung integration test với cơ chế xác thực thực tế.

**Nhầm tầng HTTP và phương thức.** `MockMvc` có thể kiểm 401/403 ở tầng web, nhưng filter hoặc route chưa chắc chứng minh service method security đã chạy. Test trực tiếp Spring service bean để chứng minh SpEL; sau đó dùng HTTP test để đảm bảo endpoint ánh xạ đúng lỗi truy cập. Trong test gọi service trực tiếp, nhận `AccessDeniedException`; HTTP exception handling thường chuyển lỗi truy cập đã xác thực thành 403, còn thiếu xác thực có thể dẫn tới 401 tùy cấu hình.

**Không giải quyết race condition.** Owner hoặc tenant có thể thay đổi giữa bước kiểm tra ở policy và câu lệnh update. Với nghiệp vụ nhạy cảm, thêm điều kiện owner/tenant vào câu lệnh update có ràng buộc, locking hoặc cơ chế kiểm soát đồng thời; test cả thay đổi quyền trong lúc xử lý. Annotation một mình không bảo đảm tính nguyên tử.

## 7. Checklist trước khi chấp nhận test

- [ ] `@EnableMethodSecurity` hiện diện trong Spring context của test; service được lấy qua dependency injection.
- [ ] Có ít nhất một ca **được phép** và một ca **bị từ chối** cho từng biểu thức quyền.
- [ ] Đã kiểm tra owner lấy từ nguồn đáng tin cậy, gồm cả ID của người khác và ID không tồn tại.
- [ ] Đã thử giả mạo owner/tenant ở dữ liệu đầu vào, không chỉ username trong annotation test.
- [ ] Đã kiểm tra cả thiếu authority lẫn input `null`/rỗng/biên.
- [ ] Trường hợp bị chặn không làm thay đổi state hoặc gây tác dụng phụ.
- [ ] Biểu thức SpEL tìm đúng tham số; hiểu sự khác nhau giữa `roles` và `authorities`.
- [ ] `@PostAuthorize` chỉ dùng ở nơi việc chạy phần thân trước khi kiểm tra là chấp nhận được.
- [ ] Nếu có custom principal, đã viết thêm test với kiểu `Authentication` sát thực tế.
- [ ] Từng test độc lập về dữ liệu, không dựa vào thứ tự hoặc trạng thái bảo mật từ test trước.

## 8. Tài liệu đối chiếu

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — `@WithMockUser` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html
- OWASP — Insecure Direct Object Reference Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html

**Kết quả cần đạt:** Một ca positive chứng minh đúng người có đủ quyền thực thi được phương thức; các ca negative chứng minh *đổi tham số*, *đổi ID tài nguyên*, *khai sai thuộc tính đầu vào* hoặc *thiếu authority* đều không thể vượt qua chính sách. Với phương thức ghi, xác nhận trạng thái dữ liệu không đổi sau mọi lần bị từ chối.
