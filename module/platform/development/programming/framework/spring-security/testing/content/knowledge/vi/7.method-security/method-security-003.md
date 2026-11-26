# Kiểm tra @PreAuthorize với vai trò, authority và tham số phương thức

## 1. Mục tiêu và tình huống thực tế

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, chúng ta kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng thư viện spring-security-test trên ứng dụng Servlet và Reactive. Bài này tập trung vào **viết và kiểm thử biểu thức @PreAuthorize** dựa trên ba loại thông tin: vai trò (*role*), quyền cụ thể (*authority*) và tham số của phương thức.

Giả sử hệ thống quản lý tài liệu có các yêu cầu:

1. Chỉ quản trị viên được xóa tài liệu.
2. Người có quyền document:read mới được xem thông tin tài liệu.
3. Người có document:read cũng chỉ được xem **tài liệu thuộc quyền sở hữu của mình**.

Yêu cầu thứ ba quan trọng nhất: một tài khoản có quyền đọc không có nghĩa được đọc tài liệu của mọi người. Muốn chứng minh kiểm soát truy cập đúng, cần kiểm thử **cùng một tài khoản, cùng một authority, nhưng thay đổi tham số tài liệu** và quan sát được cả kết quả cho phép lẫn từ chối.

Sau bài học, bạn sẽ biết cách:

- Phân biệt hasRole, hasAuthority, hasAnyRole và hasAnyAuthority; hiểu quy ước tiền tố ROLE_ và SCOPE_.
- Lấy tên tham số trong SpEL qua #documentId, kiểm tra biến authentication và gọi policy bean.
- Viết test @WithMockUser chứng minh quyền role, authority và quyền theo đối tượng.
- Kiểm tra mã HTTP bằng MockMvc, JWT/OAuth2/OIDC giả lập; hiểu nguyên nhân kết quả 401, 403, 200.
- Chuyển nguyên tắc sang WebFlux với @EnableReactiveMethodSecurity và WebTestClient.
- Phát hiện test dương tính giả do sai username, thiếu tên tham số, mock service hoặc chặn sớm ở HTTP filter.

> **Phiên bản:** Ví dụ chính dùng Spring Security 6.x, Spring Boot 3.x, JUnit 5 và spring-security-test. Với Spring Security 7.x, nguyên tắc @EnableMethodSecurity và biểu thức @PreAuthorize vẫn phù hợp, nhưng import Spring Boot test auto-configuration có thể khác khi dùng Boot 4.x. Với ứng dụng đời cũ Spring Security 5.x, hãy kiểm tra API có sẵn trước khi dùng cấu hình ví dụ.

## 2. @PreAuthorize thực sự đánh giá điều gì?

@PreAuthorize là annotation khai báo điều kiện **phải đúng trước khi thực thi thân phương thức**. Khi một bean do Spring quản lý được gọi qua cơ chế method-security interceptor, Spring Security đánh giá biểu thức trước khi cho phép phương thức chạy.

~~~mermaid
flowchart TD
    A["Controller / bean khác / test"] --> B["Spring proxy của service"]
    B --> C["Method-security interceptor"]
    C --> D["Lấy Authentication và các tham số phương thức"]
    D --> E{"SpEL @PreAuthorize trả true?"}
    E -- "Đúng" --> F["Chạy phương thức nghiệp vụ"]
    E -- "Sai" --> G["Từ chối truy cập: AccessDeniedException"]
~~~

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public String summary() {
    return "DOCUMENT-SUMMARY";
}
~~~

Điều kiện này kiểm tra tập GrantedAuthority của Authentication hiện tại có chứa chính xác document:read hay không. Nó **không tự kiểm tra** tài liệu nào được truy cập, trừ khi biểu thức cũng nhận biết tham số/phạm vi đối tượng.

Điều kiện chỉ được đánh giá nếu đã bật method security và lời gọi đi qua bean được Spring áp interceptor. Tạo new DocumentService() rồi gọi method hoặc gọi nội bộ this.securedMethod() trong cùng target có thể bỏ qua proxy ở chế độ AOP thông thường. Vì vậy các test bên dưới luôn inject bean từ Spring application context.

## 3. Phân biệt role và authority

Trong Spring Security, Authentication có một tập GrantedAuthority, ví dụ ROLE_ADMIN, document:read, SCOPE_documents.read. **Role thường là một quy ước trên authority**, không phải một kiểu quyền độc lập mà @PreAuthorize tự đi tìm từ database.

| Biểu thức | Authority được kiểm tra theo mặc định | @WithMockUser minh họa |
|---|---|---|
| hasRole('ADMIN') | ROLE_ADMIN | roles = "ADMIN" |
| hasAnyRole('ADMIN', 'AUDITOR') | ROLE_ADMIN **hoặc** ROLE_AUDITOR | roles = "AUDITOR" |
| hasAuthority('document:read') | document:read, so khớp chính xác | authorities = "document:read" |
| hasAnyAuthority('document:read', 'document:write') | Một trong hai chuỗi authority chính xác | authorities = "document:write" |
| hasAuthority('SCOPE_documents.read') | SCOPE_documents.read | authorities = "SCOPE_documents.read" |

Ví dụ hai policy khác nhau:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String deleteDocument(String id) {
    return "DELETED-" + id;
}

@PreAuthorize("hasAuthority('document:read')")
public String readSummary() {
    return "DOCUMENT-SUMMARY";
}
~~~

Các điểm dễ nhầm:

- @WithMockUser(roles = "ADMIN") mặc định cấp ROLE_ADMIN. Không viết roles = "ROLE_ADMIN" để cố gắng tự thêm tiền tố.
- hasAuthority('ADMIN') **không tương đương** hasRole('ADMIN') khi authority của user là ROLE_ADMIN.
- hasAuthority('document:read') không tự chấp nhận ROLE_ADMIN. Nếu quản trị viên cũng cần được đọc, phải cấp authority phù hợp hoặc viết policy được thiết kế rõ ràng.
- Nếu muốn mock đồng thời ROLE_ADMIN và document:read, dùng @WithMockUser(authorities = {"ROLE_ADMIN", "document:read"}); thuộc tính roles và authorities của @WithMockUser không được dùng cùng lúc với giá trị khác rỗng.
- JWT resource server thường chuyển claim scope/scp thành authority có tiền tố SCOPE_, chẳng hạn SCOPE_documents.read, qua converter mặc định. Với custom converter, authority thực tế có thể khác. Test phải phản ánh cách chuyển đổi đang dùng.

**Lưu ý cấu hình nâng cao:** Tiền tố ROLE_ mặc định có thể được tùy biến, vì thế bảng trên mô tả cấu hình phổ biến; hãy kiểm tra cấu hình GrantedAuthorityDefaults hoặc cơ chế role prefix khi dự án có tùy biến.

## 4. Sử dụng tham số phương thức trong SpEL

@PreAuthorize có thể đọc tham số theo tên, ví dụ #documentId, và có thể truy cập authentication, principal hoặc gọi Spring bean khác trong biểu thức.

~~~java
@PreAuthorize("hasAuthority('document:read') and #documentId != null")
public String read(String documentId) {
    return "DOCUMENT-" + documentId;
}
~~~

Biểu thức trên chỉ kiểm tra có quyền đọc và documentId không null. Nó **chưa chứng minh người dùng được xem tài liệu đó**. Đặc biệt, không an toàn nếu tin hoàn toàn vào ownerId, tenantId hoặc username do client truyền:

~~~java
// KHÔNG đủ để xác thực quyền sở hữu nếu ownerName do client tự chọn.
@PreAuthorize("#ownerName == authentication.name")
public String readClaimedDocument(String documentId, String ownerName) {
    return "DOCUMENT-" + documentId;
}
~~~

Client có thể gửi ownerName trùng tài khoản của mình trong khi documentId lại thuộc người khác. Muốn kiểm tra quyền sở hữu, chính sách cần tra cứu từ **nguồn dữ liệu đáng tin cậy** trên server theo documentId.

### Spring tìm tên tham số từ đâu?

Để đánh giá #documentId, Spring Security phải biết tên của argument. Những cách phổ biến:

- Dùng @P("documentId") của Spring Security để đặt tên tham số tường minh.
- Biên dịch Java với tùy chọn -parameters để tên tham số có trong metadata của bytecode.
- Dùng cơ chế nhận diện tên tham số được Spring Security hỗ trợ trong dự án, ví dụ một số annotation @Param tương thích.

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('document:read') and #documentId != null")
public String read(@P("documentId") String documentId) {
    return "DOCUMENT-" + documentId;
}
~~~

Trong biểu thức phương thức cũng có thể tham chiếu argument theo vị trí qua #p0 hoặc #a0 khi thích hợp. Tuy vậy, tên có ý nghĩa và @P thường giúp code dễ đọc hơn, nhất là khi method nhận nhiều tham số. Nếu #documentId đột ngột là null hoặc expression không đánh giá đúng sau khi build, hãy kiểm tra -parameters và annotation tên tham số trước khi thay đổi dữ liệu test.

Một số biểu thức kết hợp:

~~~java
// Cần cả hai điều kiện.
@PreAuthorize("hasRole('ADMIN') and hasAuthority('document:delete')")

// Chỉ cần một trong hai loại quyền.
@PreAuthorize("hasRole('ADMIN') or hasAuthority('document:read')")

// Dựa vào đối tượng trả lời từ một policy bean.
@PreAuthorize("@documentAccess.canRead(authentication, #documentId)")
~~~

Điều kiện and/or phải phản ánh đúng nghiệp vụ. Không dùng or để vô tình cho phép người có role rộng bỏ qua điều kiện sở hữu nếu đó không phải chủ đích. Khi logic phức tạp hoặc cần truy cập database, nên chuyển nó vào policy bean có thể kiểm thử riêng.

## 5. Xây dựng ví dụ Servlet tự chứa: role + authority + sở hữu tài liệu

### 5.1. Dependency và bật method security

Dự án Spring Boot Servlet cần web starter, security starter, JUnit test starter và spring-security-test. Ví dụ khai báo Maven khi dùng Spring Boot BOM:

~~~xml
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
~~~

Không gắn version spring-security-test riêng nếu BOM đã quản lý các module Spring Security. Bật method security trong class được Spring nạp:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

@EnableMethodSecurity bật hỗ trợ @PreAuthorize mặc định trên Spring Security hiện đại. Điều này khác với @EnableGlobalMethodSecurity(prePostEnabled = true) từng dùng trong dự án Spring Security đời cũ. Không cần kích hoạt securedEnabled hoặc jsr250Enabled chỉ để dùng @PreAuthorize.

### 5.2. Policy bean tra cứu chủ sở hữu từ phía server

Để bài thực hành chạy độc lập database, ta dùng Map chứa dữ liệu mô phỏng lưu **trong server**. Đây là dữ liệu giả lập cố định cho bài học; ứng dụng thật phải thay Map bằng repository có kiểm tra tenant/quyền phù hợp.

~~~java
// DocumentAccess.java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccess {

    private final Map<String, String> ownerById =
        Map.of("doc-1", "alice", "doc-2", "bob");

    public boolean canRead(Authentication authentication, String documentId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        String owner = ownerById.get(documentId);
        return owner != null && owner.equals(authentication.getName());
    }
}
~~~

Nếu documentId không tồn tại, owner là null và policy từ chối; tránh mặc định trả true cho giá trị không biết. Map chỉ giúp minh họa logic, không phải mô hình phân quyền sản xuất. Với repository thật, nên xem xét ranh giới tenant, trạng thái tài liệu và xử lý bản ghi không tồn tại.

### 5.3. Service chứa ba chính sách

~~~java
// DocumentService.java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(String documentId) {
        return "DELETED-" + documentId;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public String summary() {
        return "DOCUMENT-SUMMARY";
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentAccess.canRead(authentication, #documentId)"
    )
    public String readOwn(@P("documentId") String documentId) {
        return "DOCUMENT-" + documentId;
    }
}
~~~

Với readOwn, có **hai cổng**: người gọi phải có authority document:read và documentId phải thuộc người có Authentication hiện tại. @P giúp biểu thức đọc được tên tham số mà không phụ thuộc vào tùy chọn biên dịch.

Ở ứng dụng thật, @PreAuthorize cần được gắn lên phương thức public của **Spring bean được gọi qua proxy**. Logic này chỉ để mô tả kiểm soát quyền; bản thực tế nên có repository, nghiệp vụ đọc/xóa, kiểm thử không bị thực thi khi bị từ chối và các xử lý lỗi phù hợp.

## 6. Test service trực tiếp bằng @WithMockUser

Test này rất quan trọng vì nó tách kết quả @PreAuthorize khỏi chuyện filter HTTP có chặn request trước khi vào service hay không. @SpringBootTest nạp Spring context; test inject DocumentService thay vì tạo bằng new.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleCanDelete() {
        assertEquals("DELETED-doc-1", documents.delete("doc-1"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userRoleCannotDelete() {
        assertThrows(AccessDeniedException.class,
            () -> documents.delete("doc-1"));
    }

    @Test
    @WithMockUser(authorities = "document:read")
    void matchingAuthorityCanReadSummary() {
        assertEquals("DOCUMENT-SUMMARY", documents.summary());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleAloneDoesNotGrantCustomReadAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> documents.summary());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void ownerWithReadAuthorityCanRead() {
        assertEquals("DOCUMENT-doc-1", documents.readOwn("doc-1"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void anotherUserWithSameAuthorityCannotReadAliceDocument() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readOwn("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void ownerCannotReadOtherOwnersDocument() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readOwn("doc-2"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void ownerWithoutReadAuthorityCannotRead() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readOwn("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void unknownDocumentIsNotAuthorized() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readOwn("missing-doc"));
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerCannotReadSummary() {
        assertThrows(AccessDeniedException.class,
            () -> documents.summary());
    }
}
~~~

Các phép thử biểu diễn **những trục độc lập của authorization**. Ví dụ cùng một Alice có document:read: readOwn("doc-1") thành công nhưng readOwn("doc-2") bị từ chối. Nhờ đó test phát hiện được lỗi biểu thức chỉ kiểm tra authority mà bỏ qua documentId.

Cẩn thận với giá trị mặc định của @WithMockUser: nếu không khai báo username, username mặc định thường là "user". Trong ví dụ chủ sở hữu là alice/bob, nên một test thiếu username có thể bị từ chối dù authority đúng, dẫn đến suy luận sai về chính sách.

**Với @PreAuthorize**, lời gọi bị từ chối thường ném AccessDeniedException hoặc lớp con phù hợp, trước khi nghiệp vụ chạy. Ở tầng Java method không có HTTP status 401/403. Nếu test không nạp Spring bean thật hoặc lời gọi bỏ qua interceptor, test thiếu quyền có thể thành công một cách nguy hiểm. Khi cần kiểm tra tác dụng phụ, dùng fake repository hoặc spy của dependency bên dưới service để chứng minh không có ghi dữ liệu sau quyết định từ chối.

### Bảng đối chiếu các ca quyết định

| Principal | GrantedAuthority | Gọi phương thức | Kết quả |
|---|---|---|---|
| admin | ROLE_ADMIN | delete("doc-1") | Được phép |
| alice | ROLE_USER | delete("doc-1") | Từ chối |
| alice | document:read | summary() | Được phép |
| admin | ROLE_ADMIN | summary() | Từ chối do thiếu document:read |
| alice | document:read | readOwn("doc-1") | Được phép |
| alice | document:read | readOwn("doc-2") | Từ chối vì sai chủ sở hữu |
| bob | document:read | readOwn("doc-1") | Từ chối vì sai chủ sở hữu |
| alice | document:write | readOwn("doc-1") | Từ chối vì thiếu document:read |

Một test chỉ kiểm tra kết quả được phép chưa đủ: nếu @EnableMethodSecurity bị bỏ quên, nhiều test “happy path” vẫn xanh. Luôn duy trì ít nhất một negative test ở tầng method, tốt nhất có cả tình huống quyền đúng nhưng tài liệu sai.

## 7. MockMvc: kiểm chứng @PreAuthorize qua HTTP Servlet

Để từ HTTP tới service, tạo controller inject DocumentService:

~~~java
// DocumentController.java
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/documents")
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/summary")
    public String summary() {
        return documents.summary();
    }

    @GetMapping("/{id}")
    public String read(@PathVariable String id) {
        return documents.readOwn(id);
    }

    @DeleteMapping("/{id}")
    public String delete(@PathVariable String id) {
        return documents.delete(id);
    }
}
~~~

Cấu hình HTTP sau **cố ý cho request vào controller để quan sát method security**. HTTP Basic cung cấp entry point phù hợp cho trường hợp không xác thực. Trong hệ thống thật, hãy định nghĩa policy HTTP theo nhu cầu và không dùng permitAll() toàn cục như một mặc định an toàn.

~~~java
// DemoHttpSecurityConfig.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoHttpSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Test HTTP với Spring Boot 3.x:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void aliceCanReadHerDocument() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("DOCUMENT-doc-1"));
    }

    @Test
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/documents/doc-2")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void aliceWithoutReadAuthorityGets403() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedCallerGets401WithBasic() throws Exception {
        mvc.perform(get("/documents/summary"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanDeleteWhenCsrfIsPresent() throws Exception {
        mvc.perform(delete("/documents/doc-1")
                .with(csrf())
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("DELETED-doc-1"));
    }

    @Test
    void ordinaryUserCannotDeleteEvenWithCsrf() throws Exception {
        mvc.perform(delete("/documents/doc-1")
                .with(csrf())
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Vì sao có 401, 403 và 200?** Với đúng HTTP Basic filter chain trong ví dụ, người chưa xác thực bị chặn ở phương thức và HTTP entry point chuyển thành 401; người đã xác thực nhưng thiếu quyền nhận 403; người đủ điều kiện nhận 200. Kết quả HTTP có thể khác nếu ứng dụng dùng form login (ví dụ redirect), Bearer authentication, exception handling tùy chỉnh hoặc URL rule chặn request trước khi vào method.

Đối với DELETE, nếu thiếu csrf() thì CSRF filter của Servlet có thể trả 403 trước khi @PreAuthorize được đánh giá; test như vậy không chứng minh quyền xóa đã được cấu hình đúng. Tương tự, nếu @WebMvcTest thay service bằng mock, 200/403 của controller có thể không kiểm tra policy thật. Dùng @SpringBootTest với bean service thật cho bài toán này. Khi tự tạo MockMvc từ WebApplicationContext, tích hợp .apply(springSecurity()) để đưa security filter chain vào test.

## 8. JWT, OAuth2/OIDC giả lập: authority phải khớp chính sách

Trong Servlet resource server, spring-security-test cung cấp request post-processor jwt() để mô phỏng Authentication dựa trên Jwt. Khi ứng dụng thật dùng converter biến scope thành SCOPE_documents.read, chính sách nên kiểm tra đúng authority mà converter tạo:

~~~java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public String readByScope() {
    return "SCOPE-READ";
}
~~~

Trong MockMvc, có thể dùng:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Bên trong một test MockMvc tại endpoint gọi readByScope():
mvc.perform(get("/documents/scope")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isOk());
~~~

Đoạn minh họa cuối yêu cầu một endpoint /documents/scope thực sự gọi readByScope(); cần thêm endpoint đó vào controller nếu muốn chạy. Nó dùng **policy scope riêng**, không thay thế policy document:read trên readOwn. Nếu test cần giữ nguyên readOwn, có thể truyền jwt().authorities(new SimpleGrantedAuthority("document:read")), nhưng khi đó đang mock đúng custom authority và không thử converter scope thật.

Với OAuth2 Login hoặc OIDC Login, Spring Security Test có oauth2Login() và oidcLogin() trên MockMvc; trên WebFlux có mockOAuth2Login() và mockOidcLogin(). Các helper tạo trạng thái đăng nhập giả lập để kiểm tra authorization, nhưng **không xác minh** chữ ký JWT, issuer, audience, luồng redirect/code exchange hay identity provider thực tế. Muốn chứng minh quá trình chuyển claims và scopes thành authorities đúng, phải có test riêng cho converter/decoder hoặc integration test theo cấu hình xác thực đang chạy.

## 9. WebFlux: @PreAuthorize trên publisher và WebTestClient

WebFlux sử dụng @EnableReactiveMethodSecurity, security context được truyền qua Reactor Context. Phương thức được bảo vệ thường trả Publisher như Mono hoặc Flux, và test phải subscribe để quan sát quyết định.

Ví dụ một **ứng dụng WebFlux riêng** (dùng spring-boot-starter-webflux thay vì spring-boot-starter-web):

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {
}
~~~

Service Reactive tối thiểu:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDocumentService {

    @PreAuthorize("hasAuthority('document:read')")
    public Mono<String> summary() {
        return Mono.just("DOCUMENT-SUMMARY");
    }
}
~~~

Controller Reactive inject bean thật:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveDocumentController {

    private final ReactiveDocumentService documents;

    public ReactiveDocumentController(ReactiveDocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/reactive/documents/summary")
    public Mono<String> summary() {
        return documents.summary();
    }
}
~~~

Để cô lập method authorization, WebFlux HTTP security có thể được cấu hình (cho mục đích thực hành) cho phép request đi tới controller:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class DemoReactiveHttpConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex.anyExchange().permitAll())
            .build();
    }
}
~~~

Test WebTestClient với spring-security-test:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class ReactiveDocumentHttpSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void init() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void readerIsAllowed() {
        client.mutateWith(mockUser("alice").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("DOCUMENT-SUMMARY");
    }

    @Test
    void writerWithoutReadPermissionIsDenied() {
        client.mutateWith(mockUser("alice").authorities(
                new SimpleGrantedAuthority("document:write")))
            .get().uri("/reactive/documents/summary")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Test này dựa trên một WebFlux application context thực sự nạp ReactiveSecurityConfig, DemoReactiveHttpConfig, service và controller nêu trên. Nếu dự án cùng có Servlet và WebFlux dependency, cần xác định Spring Boot đang chạy web application type nào. Test riêng cho method trả Mono có thể dùng StepVerifier để subscribe và kiểm tra lỗi/giá trị trong Reactor Context được tạo bởi test security. Chỉ tạo Mono mà không subscribe không đủ để kết luận @PreAuthorize đã hoạt động.

Đối với **tham số phương thức trên Reactive**, vẫn cần dùng #documentId đúng tên hoặc @P; nếu chính sách có tra cứu dữ liệu bất đồng bộ, hãy thiết kế authorization policy tương thích Reactive thay vì gọi repository blocking ngay trong thread xử lý Reactor. Kiểm thử phải bao gồm đúng authority/sai authority và cùng authority nhưng khác documentId, tương tự Servlet.

## 10. Gỡ lỗi biểu thức và những phép thử dễ gây hiểu nhầm

| Hiện tượng | Nguyên nhân có thể | Cách kiểm chứng |
|---|---|---|
| Có @PreAuthorize nhưng method luôn chạy | Chưa bật @EnableMethodSecurity, bean không do Spring quản lý hoặc self-invocation bỏ qua proxy | Inject bean từ context, gọi qua đường thực tế và có negative test. |
| @WithMockUser(roles = "ADMIN") bị từ chối bởi hasAuthority('ADMIN') | Authority cấp là ROLE_ADMIN | Dùng hasRole('ADMIN') hoặc kiểm tra đúng authority ROLE_ADMIN. |
| User có document:read vẫn không đọc được doc-1 | Username test mặc định "user", trong khi chủ sở hữu là alice | Đặt username = "alice", kiểm tra data policy. |
| Quyền sở hữu không thay đổi khi đổi documentId | Biểu thức bỏ qua tham số hoặc policy tin vào ownerName do client gửi | Kiểm tra cùng user/cùng authority với doc-1 và doc-2. |
| #documentId là null hoặc biểu thức lỗi | Tên tham số không được giữ trong bytecode, nhầm tên hoặc thiếu @P | Thêm @P("documentId") hoặc bật -parameters. |
| Test HTTP trả 403 dù method cho phép | URL rule hoặc CSRF filter chặn trước khi vào service | Kiểm tra filter chain, gửi csrf() khi phù hợp và test trực tiếp service. |
| Test HTTP trả 302 thay vì 401 | HTTP entry point cấu hình form login | Đối chiếu cấu hình; status 401 phụ thuộc HTTP Basic/Bearer và handler. |
| Test chỉ có 200 dù mất @EnableMethodSecurity | Happy-path không chứng minh interceptor đã chạy | Thêm test sai authority và sai ownership ở tầng service. |
| jwt() cấp SCOPE_documents.read nhưng policy đòi document:read | Convention authority không khớp | Dùng converter/chính sách đúng hoặc tạo authority giả lập đúng mục tiêu test. |
| @WebMvcTest vẫn xanh dù service thiếu bảo mật | Service thật bị thay mock trong test slice | Dùng Spring context nạp bean service có method security. |
| WebFlux test không quan sát lỗi quyền | Mono chưa được subscribe hoặc Reactive SecurityContext không được truyền đúng | Dùng WebTestClient với springSecurity()/mockUser() hoặc StepVerifier kèm context phù hợp. |

**Không dùng duy nhất kết quả HTTP 403 để khẳng định method security đúng.** Filter URL, CSRF, handler hoặc validation có thể tạo ra lỗi trước khi method interceptor được chạy. Tập hợp bằng chứng nên có test trực tiếp bean thật và test request HTTP qua controller thực tế.

## 11. Bài tập thực hành

1. Cài @EnableMethodSecurity, DocumentService và DocumentAccess. Viết test xác nhận ROLE_ADMIN được phép xóa, ROLE_USER bị từ chối. Thử thay hasRole('ADMIN') bằng hasAuthority('ADMIN') và giải thích vì sao kết quả khác.
2. Với summary(), thử @WithMockUser(authorities = "document:read") và @WithMockUser(roles = "ADMIN"); giải thích sự khác biệt giữa role và authority.
3. Với readOwn(documentId), dùng Alice và authority document:read. Chứng minh doc-1 thành công nhưng doc-2 bị từ chối. Sau đó đổi Alice thành Bob, giữ nguyên documentId, xác minh kết quả.
4. Gỡ @P("documentId") và biên dịch bằng/tắt -parameters trong một nhánh thử nghiệm để quan sát biểu thức nhận tên tham số như thế nào; khôi phục cấu hình sau khi hiểu kết quả.
5. Tạo MockMvc test cho 200/403/401 theo cấu hình HTTP Basic. Với DELETE, gửi csrf() hợp lệ để đo riêng quyết định @PreAuthorize.
6. Trên WebFlux, dùng @EnableReactiveMethodSecurity, ReactiveDocumentService và WebTestClient để so sánh document:read với document:write. Mở rộng policy theo documentId và kiểm tra thêm cùng authority với hai tài liệu khác chủ sở hữu.
7. Với một endpoint dùng JWT/OIDC, mô phỏng authorities bằng helper của spring-security-test, rồi kiểm thử riêng converter hoặc token validation thực tế của dự án.

**Tiêu chí hoàn thành:** test phải chứng minh vai trò, authority và tham số được đánh giá đúng trên **bean Spring thật**; cả lời gọi đủ điều kiện lẫn lời gọi thiếu quyền hoặc không sở hữu đối tượng đều được kiểm chứng. Khi có HTTP, phản hồi phải phản ánh đúng filter chain của ứng dụng, không che khuất việc @PreAuthorize có thật sự chạy hay không.

