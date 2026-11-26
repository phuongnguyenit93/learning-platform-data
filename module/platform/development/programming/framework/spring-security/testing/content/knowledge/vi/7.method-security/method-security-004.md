# Kiểm tra @PostAuthorize theo đối tượng trả về

## 1. Bài toán: quyền truy cập phụ thuộc dữ liệu trả về

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, chúng ta kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Các bài test cần chứng minh cả trường hợp người dùng được phép lẫn trường hợp bị từ chối, từ SecurityContext giả lập đến phản hồi của MockMvc hoặc WebTestClient.

Có một kiểu chính sách mà chỉ nhìn vào đường dẫn, vai trò hoặc tham số phương thức chưa đủ để quyết định quyền: **kết quả trả về mới chứa thông tin để xác định người nào được xem**. Ví dụ, phương thức tìm tài liệu theo mã có thể trả đối tượng với thuộc tính ownerUsername; chỉ chủ sở hữu có authority document:read được nhận kết quả.

Với Spring Security, @PostAuthorize cho phép kiểm tra điều kiện **sau khi thân phương thức đã chạy**, bằng biểu thức SpEL tham chiếu đến biến đặc biệt returnObject. Nếu biểu thức đánh giá thành false, lời gọi bị từ chối và kết quả không được trả về cho người gọi bình thường.

Sau bài học, người học sẽ có thể:

- Phân biệt chính xác thời điểm đánh giá @PreAuthorize và @PostAuthorize.
- Viết biểu thức @PostAuthorize dùng returnObject, authentication, hasRole và hasAuthority; xử lý null theo chủ đích.
- Tạo service với đối tượng trả về có thông tin chủ sở hữu và kiểm tra bằng @WithMockUser trong Spring test context.
- Chứng minh phương thức **đã thực thi trước khi hậu kiểm** và giải thích rủi ro tác dụng phụ, log, tải dữ liệu và giao dịch.
- Kiểm thử hành vi Servlet qua MockMvc, mở rộng sang Mono và WebTestClient trên WebFlux.
- Nhận diện giới hạn của SecurityContext, JWT/OAuth2/OIDC giả lập và các lỗi test khiến quyền truy cập bị đánh giá sai.

> Ví dụ tập trung vào Spring Security 6.x, Spring Boot 3.x và JUnit 5. Spring Security 7.x vẫn sử dụng hướng cấu hình method security hiện đại; một số import cho tính năng test auto-configuration thay đổi khi dùng Spring Boot 4.x. Khi triển khai vào ứng dụng thực tế, hãy đối chiếu API và dependency theo phiên bản Spring Security đã resolve.

## 2. Vòng đời của @PostAuthorize

Method security hoạt động thông qua hạ tầng được Spring đăng ký khi bật @EnableMethodSecurity (Servlet) hoặc @EnableReactiveMethodSecurity (Reactive). Lời gọi tới bean được Spring quản lý phải đi qua proxy/interceptor tương ứng; việc tự tạo đối tượng bằng new hay self-invocation thường không kích hoạt kiểm tra.

~~~mermaid
sequenceDiagram
    participant C as Caller / Test
    participant P as Spring method proxy
    participant S as DocumentService
    participant A as Post-authorization
    C->>P: findDocument("doc-1")
    P->>S: Gọi phương thức nghiệp vụ
    S-->>P: DocumentView(ownerUsername="alice")
    P->>A: Đánh giá SpEL với returnObject
    alt Đủ quyền và đúng chủ sở hữu
        A-->>P: Cho phép
        P-->>C: Trả DocumentView
    else Thiếu quyền hoặc sai chủ sở hữu
        A-->>P: Từ chối
        P-->>C: AccessDeniedException
    end
~~~

So sánh các giai đoạn:

| Nội dung | @PreAuthorize | @PostAuthorize |
|---|---|---|
| Thời điểm | Trước khi gọi thân phương thức | Sau khi có kết quả thực thi |
| Dữ liệu thường dùng | Authentication, role, authority, tham số như #documentId | Authentication, role, authority, **returnObject** |
| Khi từ chối | Thân phương thức không được thực thi do quyết định này | Thân phương thức **đã thực thi** trước khi bị từ chối |
| Phù hợp | Chặn sớm theo quyền, tham số, chính sách nghiệp vụ | Kiểm tra dữ liệu chỉ biết từ kết quả |
| Giới hạn quan trọng | Có thể cần tra cứu dữ liệu trước khi quyết định | Không tự hoàn tác tác dụng phụ hoặc dữ liệu đã được log/phát sự kiện |

Biểu thức mẫu:

~~~java
@PostAuthorize(
    "returnObject != null and " +
    "hasAuthority('document:read') and " +
    "returnObject.ownerUsername == authentication.name"
)
public DocumentView findDocument(String documentId) {
    return repository.findById(documentId);
}
~~~

Trong đoạn này:

1. returnObject là giá trị phương thức trả về để hậu kiểm. Ở ví dụ trên nó là DocumentView.
2. returnObject != null giúp bảo đảm không truy cập thuộc tính của null. Trường hợp không tìm thấy tài liệu sẽ bị từ chối theo biểu thức này; cách ánh xạ sang 403 hoặc 404 cần được thiết kế riêng theo API.
3. hasAuthority('document:read') yêu cầu đúng GrantedAuthority có chuỗi document:read.
4. returnObject.ownerUsername đọc JavaBean property tương ứng với getOwnerUsername().
5. authentication.name là tên của principal hiện tại; @WithMockUser(username = "alice") tạo tên principal alice phục vụ test.

SpEL hỗ trợ toán tử and, or, phép so sánh và truy cập thuộc tính. Biểu thức phải trả về quyết định boolean phù hợp. Một expression thiếu điều kiện null hoặc dựa trên tên thuộc tính sai có thể khiến kiểm tra lỗi trong lúc gọi; hãy dùng test kết quả hợp lệ, kết quả không hợp lệ và kết quả vắng mặt.

### Khi nào không nên dùng hậu kiểm?

Một phương thức vừa xóa dữ liệu, vừa chuyển tiền, vừa gửi email hoặc vừa phát event rồi mới trả đối tượng sẽ **không được bảo vệ khỏi các tác dụng phụ đó** nếu chỉ dùng @PostAuthorize. Người gọi có thể nhận lỗi truy cập nhưng hành động đã xảy ra. Transaction có thể rollback trong một số cấu hình và thứ tự advice, nhưng không có bảo đảm tổng quát rằng mọi thay đổi database, log, email hay dịch vụ bên ngoài được hoàn tác. Không dùng hành vi rollback ngẫu nhiên như một chính sách bảo mật.

Đối với thao tác có tác dụng phụ, hãy ưu tiên @PreAuthorize hoặc kiểm tra quyền nghiệp vụ **trước** hành động. Với thao tác đọc, @PostAuthorize có thể phù hợp khi cần kiểm tra owner trong chính đối tượng vừa tìm được; tuy nhiên truy vấn vẫn thực thi và có thể tiêu tốn tài nguyên.

## 3. Chuẩn bị dự án và bật method security

Trong ứng dụng Spring Boot Servlet, sử dụng spring-security-test cùng các starter tương ứng. Ví dụ Maven khi Spring Boot BOM quản lý phiên bản:

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

Tương đương trong Gradle Kotlin DSL:

~~~kotlin
implementation("org.springframework.boot:spring-boot-starter-web")
implementation("org.springframework.boot:spring-boot-starter-security")
testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.security:spring-security-test")
~~~

Spring Boot BOM thường quản lý phiên bản spring-security-test; không trộn một phiên bản khác với các module Spring Security đã được resolve.

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

@EnableMethodSecurity bật @PreAuthorize và @PostAuthorize theo mặc định trong Spring Security hiện đại. Trong dự án cũ có thể gặp @EnableGlobalMethodSecurity(prePostEnabled = true); đây là cách khai báo ở thế hệ cũ. @Secured và Jakarta @RolesAllowed cần cờ bật riêng nhưng **không cần** để sử dụng @PostAuthorize.

Đảm bảo service là Spring bean, class cấu hình có trong ApplicationContext và lời gọi từ controller/bean khác đi qua tham chiếu do Spring inject. Test bằng new DocumentService(...) sẽ không đi qua proxy. Lời gọi this.findDocument(...) từ một phương thức khác trong cùng target cũng có thể bỏ qua proxy trong chế độ AOP thông thường.

## 4. Ví dụ dữ liệu: tài liệu có chủ sở hữu

Ta sẽ kiểm thử một hệ thống tài liệu nhỏ. Dữ liệu nằm ở phía server: doc-1 thuộc alice, doc-2 thuộc bob. Người dùng cần có quyền document:read **và** phải là chủ sở hữu của tài liệu được trả về.

### 4.1. Đối tượng trả về

~~~java
// DocumentView.java
public class DocumentView {

    private final String id;
    private final String ownerUsername;
    private final String title;

    public DocumentView(String id, String ownerUsername, String title) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Ta dùng JavaBean getter getOwnerUsername() để expression returnObject.ownerUsername được diễn giải rõ. Nếu phương thức trả ResponseEntity<DocumentView>, List<DocumentView>, Optional<DocumentView> hoặc kiểu wrapper khác thì returnObject có **kiểu tương ứng với giá trị thực**; không được tự giả định ownerUsername nằm trực tiếp trên wrapper. Hãy thiết kế expression cho kiểu trả về thực tế và kiểm thử các nhánh null/rỗng.

### 4.2. Repository mô phỏng

~~~java
// DocumentRepository.java
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private final Map<String, DocumentView> documents = Map.of(
        "doc-1", new DocumentView("doc-1", "alice", "Kế hoạch A"),
        "doc-2", new DocumentView("doc-2", "bob", "Kế hoạch B")
    );

    public DocumentView findById(String id) {
        return documents.get(id);
    }
}
~~~

Repository này là ví dụ tự chứa; ứng dụng thật dùng database hoặc API phía server. Đặc biệt, **không tin ownerUsername được client gửi kèm request** để kết luận quyền sở hữu. Kết quả trả về phải đến từ nguồn dữ liệu đáng tin cậy theo id đang truy vấn.

### 4.3. Service được bảo vệ bằng @PostAuthorize

~~~java
// DocumentService.java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostAuthorize(
        "returnObject != null and " +
        "hasAuthority('document:read') and " +
        "returnObject.ownerUsername == authentication.name"
    )
    public DocumentView findDocument(String documentId) {
        return repository.findById(documentId);
    }
}
~~~

Điều kiện có tính chất **giao**: người gọi phải có authority document:read và username của họ phải trùng ownerUsername trong đối tượng trả về. Không có nhánh mặc định cho phép ROLE_ADMIN. Nếu quản trị viên thực sự được phép xem mọi tài liệu, cần thiết kế và kiểm thử chính sách đó một cách chủ động, ví dụ:

~~~java
@PostAuthorize(
    "hasRole('ADMIN') or " +
    "(returnObject != null and " +
    "hasAuthority('document:read') and " +
    "returnObject.ownerUsername == authentication.name)"
)
~~~

Biểu thức thay thế này cho phép admin đi qua cả khi returnObject null, vì nhánh hasRole('ADMIN') đã đúng. Do đó nếu nghiệp vụ cần xử lý bản ghi không tồn tại, hãy làm rõ chính sách null ngoài chuyện role. Không thêm nhánh admin chỉ để làm cho test dễ qua.

**Điểm cần nhớ:** Biểu thức không được thực thi chỉ vì annotation có mặt trong source; bean phải được method-security proxy/interceptor bao phủ và phải được gọi đúng đường đi. Test bị từ chối là phép thử phát hiện thiếu cấu hình hiệu quả hơn test thành công đơn lẻ.

## 5. Kiểm thử trực tiếp bằng @WithMockUser

Trong Spring Security Test, @WithMockUser tạo Authentication thử nghiệm trong SecurityContext. Ta có thể kiểm thử từng tổ hợp username, authority và đối tượng trả về mà không phải gọi HTTP hoặc truy cập identity provider.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentPostAuthorizeTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void ownerWithReadAuthorityCanSeeHerDocument() {
        DocumentView view = documents.findDocument("doc-1");

        assertEquals("doc-1", view.getId());
        assertEquals("alice", view.getOwnerUsername());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void anotherOwnerWithSameAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.findDocument("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void ownerCannotReadDocumentBelongingToBob() {
        assertThrows(AccessDeniedException.class,
            () -> documents.findDocument("doc-2"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void bobCanReadHisOwnDocument() {
        DocumentView view = documents.findDocument("doc-2");

        assertEquals("bob", view.getOwnerUsername());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void ownerWithoutReadAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.findDocument("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminRoleAloneDoesNotGrantDocumentReadAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> documents.findDocument("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void nullReturnObjectIsDeniedByOurExpression() {
        assertThrows(AccessDeniedException.class,
            () -> documents.findDocument("missing"));
    }
}
~~~

Ở test cuối, repository trả null và biểu thức chính sách tự chọn từ chối null. Đó là một quyết định nghiệp vụ **của ví dụ**, không phải quy tắc rằng mọi API dùng @PostAuthorize phải biến bản ghi không tồn tại thành 403. Một API có thể muốn báo 404 bằng exception trước khi trả kết quả; khi phương thức ném exception, không có returnObject thành công để hậu kiểm theo cách minh họa. Hãy thống nhất semantics của API và kiểm thử nó.

Ma trận quyết định rõ hơn:

| Username | Authorities | Đối tượng được repository trả về | Kết quả |
|---|---|---|---|
| alice | document:read | doc-1, owner alice | Được phép |
| alice | document:read | doc-2, owner bob | Từ chối vì sai owner |
| bob | document:read | doc-1, owner alice | Từ chối vì sai owner |
| bob | document:read | doc-2, owner bob | Được phép |
| alice | document:write | doc-1, owner alice | Từ chối vì thiếu document:read |
| alice | ROLE_ADMIN | doc-1, owner alice | Từ chối vì chính sách không cho phép riêng role này |
| alice | document:read | null | Từ chối theo biểu thức kiểm tra null |

@WithMockUser(roles = "ADMIN") mặc định tạo ROLE_ADMIN; hasAuthority('document:read') kiểm tra chuỗi chính xác, nên không coi ROLE_ADMIN là document:read. Tương tự, scope OAuth2 thường được converter thành authority SCOPE_..., không tự khớp custom authority trừ khi đã cấu hình chuyển đổi.

**Vì sao cần cả test được phép và bị từ chối?** Nếu bỏ @EnableMethodSecurity, phương thức findDocument vẫn có thể trả DocumentView và test happy path vẫn xanh. Các test kỳ vọng AccessDeniedException sẽ thất bại, chỉ ra rằng interceptor không có hiệu lực.

## 6. Chứng minh hậu kiểm chạy sau thân phương thức

Khi một lời gọi bị từ chối bởi @PostAuthorize, cần tránh kết luận sai rằng phương thức chưa được thực thi. Có thể ghi nhận thời điểm đọc dữ liệu bằng một dependency kiểm chứng số lần gọi.

Ví dụ bổ sung một repository interface dùng trong bài test minh họa:

~~~java
// ReadGateway.java
public interface ReadGateway {
    DocumentView findById(String id);
}
~~~

~~~java
// ObservedDocumentService.java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ObservedDocumentService {

    private final ReadGateway gateway;

    public ObservedDocumentService(ReadGateway gateway) {
        this.gateway = gateway;
    }

    @PostAuthorize(
        "returnObject != null and " +
        "returnObject.ownerUsername == authentication.name"
    )
    public DocumentView findDocument(String id) {
        return gateway.findById(id);
    }
}
~~~

Trong **một test context riêng** chỉ nạp ObservedDocumentService và ReadGateway mock, có thể xác minh logic sau bằng Mockito:

~~~java
// gateway được cấu hình trả DocumentView("doc-1", "alice", "Kế hoạch A")
// service là bean thật được Spring proxy, không phải Mockito mock.

@Test
@WithMockUser(username = "bob")
void methodIsExecutedEvenWhenPostAuthorizationDenies() {
    assertThrows(AccessDeniedException.class,
        () -> service.findDocument("doc-1"));

    verify(gateway).findById("doc-1");
}
~~~

Đây là **đoạn test minh họa**, không phải một test class độc lập hoàn chỉnh. Khi chuyển thành bài test chạy được, hãy tạo Spring test context có @EnableMethodSecurity, ObservedDocumentService thật và một @Bean ReadGateway Mockito mock; thiết lập when(gateway.findById("doc-1")).thenReturn(new DocumentView(...)) trước khi gọi, rồi verify. Spring Boot 3.4+/4.x có @MockitoBean trong bộ Spring Test; các bản Boot 3.x cũ có thể sử dụng @MockBean. Lựa chọn annotation phụ thuộc phiên bản project.

Kết quả cần thấy là **có lời gọi repository trước khi AccessDeniedException được ném**. Nếu gateway là nơi ghi database hoặc phát event thay vì đọc, tác dụng phụ đã xảy ra. @PostAuthorize không được dùng làm lớp chặn duy nhất cho các thao tác đó.

### Kết hợp hậu kiểm với chặn sớm

Nếu có một điều kiện rẻ và rõ ngay từ đầu, có thể thêm @PreAuthorize để tránh đọc dữ liệu khi người gọi thiếu quyền:

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and " +
    "returnObject.ownerUsername == authentication.name"
)
public DocumentView findDocument(String documentId) {
    return repository.findById(documentId);
}
~~~

Trong trường hợp này:

- Người thiếu document:read bị chặn **trước** truy vấn.
- Người có document:read nhưng không phải chủ sở hữu vẫn có thể thực hiện truy vấn, sau đó bị hậu kiểm từ chối.
- Nếu chính sách quyền sở hữu có thể được kiểm tra trước từ server bằng một policy bean và documentId, @PreAuthorize với policy đó có thể phù hợp hơn, nhất là với tác vụ ghi.

Một phiên bản hoàn toàn chặn sớm có thể viết:

~~~java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView findDocument(String documentId) {
    return repository.findById(documentId);
}
~~~

Khi dùng #documentId trong SpEL, Java cần giữ metadata tên tham số (thường biên dịch với -parameters) hoặc dùng @P("documentId") của Spring Security. documentPolicy là bean đọc dữ liệu đáng tin cậy từ server; không dựa vào owner name do client tự khai.

## 7. Kiểm thử HTTP Servlet bằng MockMvc

Test method cho thấy proxy/interceptor ra quyết định thế nào. Test HTTP giúp xác minh controller đã inject service thật và Spring Security chuyển lỗi thành status thích hợp.

Controller gọi DocumentService:

~~~java
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

    @GetMapping("/{id}")
    public DocumentView find(@PathVariable String id) {
        return documents.findDocument(id);
    }
}
~~~

Để kiểm tra riêng tác dụng của method security, cấu hình minh họa này cho phép tất cả GET đi tới controller và bật HTTP Basic làm entry point:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình permitAll() toàn cục ở đây **chỉ dành cho bài thực hành cô lập method security**. Ứng dụng thật phải có các điều kiện HTTP, xác thực, CSRF và chính sách tương ứng theo yêu cầu. Khi dùng GET, CSRF mặc định không phải yếu tố cần bổ sung; với POST/PUT/DELETE, phải kiểm tra các điều kiện CSRF riêng.

Test MockMvc trong Spring Boot 3.x:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentPostAuthorizeHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerWithReadAuthorityReceivesDocument() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("doc-1"))
            .andExpect(jsonPath("$.ownerUsername").value("alice"));
    }

    @Test
    void sameAuthorityButDifferentOwnerGets403() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("bob").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerWithoutReadAuthorityGets403() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedCallerGets401WithHttpBasic() throws Exception {
        mvc.perform(get("/documents/doc-1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void absentDocumentGets403UnderThisExamplePolicy() throws Exception {
        mvc.perform(get("/documents/missing")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Với cấu hình trên, người có Authentication hợp lệ nhưng không qua @PostAuthorize nhận **403 Forbidden**; người chưa xác thực nhận **401 Unauthorized** theo entry point HTTP Basic của ví dụ. Người đủ điều kiện nhận **200 OK** cùng JSON do Jackson serialize từ DocumentView.

Đây là kết quả phụ thuộc cấu hình HTTP: form login có thể redirect, resource server dùng Bearer entry point, hoặc exception handler riêng có thể trả response khác. Một test nhận 403 cũng có thể do URL policy hoặc CSRF filter chặn sớm, chưa chứng minh @PostAuthorize đã chạy. Vì vậy cần song song test **bean thật** và các ca khác owner trong mục 5.

Nếu tự tạo MockMvc bằng MockMvcBuilders.webAppContextSetup(context), áp .apply(springSecurity()) để filter chain được đưa vào test. Nếu dùng @WebMvcTest và thay DocumentService bằng mock, test controller có thể bỏ qua interceptor method security của bean thật. Với mục tiêu bài này, dùng @SpringBootTest nạp service thực, chỉ mock dependency lưu trữ nếu cần.

## 8. WebFlux: hậu kiểm đối tượng trả về từ Mono

Trên Spring WebFlux, cấu hình method security Reactive:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Ứng dụng WebFlux sử dụng spring-boot-starter-webflux, spring-boot-starter-security và spring-security-test, đồng thời phải chạy đúng reactive web application type. Reactive SecurityContext nằm trong **Reactor Context**, nên không giả định SecurityContextHolder ThreadLocal của Servlet truyền tự động qua mọi luồng xử lý bất đồng bộ.

Với phương thức trả Mono<DocumentView>, Spring Security Reactive hỗ trợ kiểm tra giá trị được phát ra ở bước hậu kiểm. Ví dụ:

~~~java
// ReactiveDocumentService.java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDocumentService {

    @PostAuthorize(
        "returnObject != null and " +
        "hasAuthority('document:read') and " +
        "returnObject.ownerUsername == authentication.name"
    )
    public Mono<DocumentView> findDocument(String id) {
        if ("doc-1".equals(id)) {
            return Mono.just(
                new DocumentView("doc-1", "alice", "Kế hoạch A"));
        }
        if ("doc-2".equals(id)) {
            return Mono.just(
                new DocumentView("doc-2", "bob", "Kế hoạch B"));
        }
        return Mono.empty();
    }
}
~~~

Mẫu trên cố ý kiểm tra hai publisher **có phát ra đúng một đối tượng**; hành vi đối với Mono.empty(), Flux nhiều phần tử hoặc wrapper khác cần được kiểm chứng riêng theo bản Spring Security thực tế. Đừng suy ra quy tắc null của ví dụ Servlet tự động tương đương tín hiệu empty trong Reactive.

Controller WebFlux inject bean:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/reactive/documents")
public class ReactiveDocumentController {

    private final ReactiveDocumentService documents;

    public ReactiveDocumentController(ReactiveDocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{id}")
    public Mono<DocumentView> find(@PathVariable String id) {
        return documents.findDocument(id);
    }
}
~~~

Để cô lập quyết định tại service trong bài test, ta có thể dùng SecurityWebFilterChain cho phép request đi tới controller. Chỉ dùng cấu hình này trong bối cảnh thực hành:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class DemoReactiveHttpConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .anyExchange().permitAll())
            .build();
    }
}
~~~

Test với WebTestClient tích hợp Spring Security:

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
class ReactiveDocumentPostAuthorizeHttpTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void ownerCanReadEmittedDocument() {
        client.mutateWith(mockUser("alice").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ownerUsername").isEqualTo("alice");
    }

    @Test
    void anotherOwnerWithSameAuthorityIsDenied() {
        client.mutateWith(mockUser("bob").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void ownerWithWrongAuthorityIsDenied() {
        client.mutateWith(mockUser("alice").authorities(
                new SimpleGrantedAuthority("document:write")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các test này giả định ứng dụng WebFlux nạp đúng ReactiveMethodSecurityConfig, DemoReactiveHttpConfig, controller và service ở trên, đồng thời request được phép qua tầng HTTP để method interceptor đánh giá quyền. Nếu ứng dụng đặt chính sách HTTP bắt xác thực hoặc dùng exception handler riêng, hãy điều chỉnh kỳ vọng theo cấu hình thực tế.

WebTestClient gửi request và subscribe publisher, nên mới quan sát được phép hậu kiểm. Với test trực tiếp service trả Mono, cần StepVerifier hoặc một subscriber tương đương; chỉ gọi findDocument() để nhận Mono rồi không subscribe thì chưa chứng minh kết quả bảo mật. Khi dùng Flux hay thao tác Reactive phức tạp, phải xem xét chính sách trên từng tín hiệu và khả năng áp dụng @PostAuthorize của phiên bản thực tế, tránh dựa vào cùng một giả định như đối tượng đồng bộ.

## 9. JWT, OAuth2 và OIDC giả lập ở bài test hậu kiểm

Trong ứng dụng thật, Authentication có thể xuất phát từ session, HTTP Basic, JWT bearer, OAuth2 Login hoặc OIDC Login. @PostAuthorize nhìn vào Authentication và granted authorities mà Spring Security đã thiết lập; logic không tự xác minh lại JWT.

Ví dụ Servlet MockMvc với jwt() có authority document:read và principal name được chỉ định:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Trong test MockMvc có endpoint GET /documents/{id} đã nêu:
mvc.perform(get("/documents/doc-1")
        .with(jwt()
            .jwt(token -> token.subject("alice"))
            .authorities(
                new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().isOk());
~~~

Ở mẫu trên jwt().jwt(token -> token.subject("alice")) nhằm tạo subject alice cho JwtAuthenticationToken giả lập; cần đối chiếu với cách ứng dụng thật xây dựng authentication.getName() (có thể tùy biến claim tên). Helper jwt() cho phép kiểm thử authorization với authority do test cung cấp; nó **không kiểm tra chữ ký, issuer, audience hoặc tương tác với identity provider**.

JWT resource server mặc định thường chuyển scope thành authority SCOPE_documents.read, còn ví dụ service đòi document:read. Nếu mục tiêu là test cách scope hoạt động, phải đổi policy hoặc cấu hình converter đúng theo ứng dụng, ví dụ hasAuthority('SCOPE_documents.read'), rồi tạo test scope đúng/sai. Không coi các authority này tự động giống nhau.

MockMvc còn có oauth2Login() và oidcLogin(); WebTestClient có mockJwt(), mockOAuth2Login() và mockOidcLogin() trong bộ test Reactive. Với OIDC, tên người dùng và authorities cần được thiết lập khớp kiểu Authentication thực sự; nếu policy dựa vào authentication.name, test cần xác định getName() trả về giá trị nào sau khi mapper chạy. Muốn xác minh luồng login/OIDC hoặc validation JWT thật, cần integration test riêng.

## 10. Những sai lầm điển hình

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| Có @PostAuthorize nhưng Bob vẫn nhận tài liệu của Alice. | Chưa bật method security hoặc controller gọi đối tượng không qua proxy. | Inject service Spring bean thật, thêm test khác owner bị từ chối. |
| User hợp lệ bị từ chối dù có document:read. | @WithMockUser không đặt username, mặc định thường là user thay vì alice. | Khai báo username = "alice" trong test; kiểm tra authentication.name. |
| Lỗi SpEL khi truy cập returnObject.ownerUsername. | Kiểu trả về không có property ownerUsername, hoặc getter/visibility không phù hợp. | Kiểm tra class DocumentView và kiểu return thực tế. |
| Từ chối do returnObject null. | Expression minh họa quy định null là không được phép. | Xác định rõ semantics 403/404 rồi test nhánh missing. |
| Service vẫn ghi dữ liệu dù caller nhận 403. | @PostAuthorize chạy sau thân phương thức. | Chặn sớm bằng @PreAuthorize/chính sách nghiệp vụ, tránh hậu kiểm duy nhất cho lệnh ghi. |
| ROLE_ADMIN không qua hasAuthority('document:read'). | Role và custom authority khác nhau. | Cấp đúng authority hoặc định nghĩa chính sách admin chủ động. |
| Test HTTP trả 403 nhưng method test lại cho phép. | HTTP filter, URL rule hoặc CSRF chặn trước method. | Kiểm thử bean thật, filter chain và đường request riêng. |
| @WebMvcTest chỉ dùng mock service nên test luôn 200. | Mock không đại diện cho method-security proxy thật. | Dùng Spring context với service thật cho test @PostAuthorize. |
| jwt() tạo SCOPE_documents.read nhưng service đòi document:read. | Converter scope và expression không đồng nhất. | Đồng bộ authority hoặc converter và viết test cho cả hai trường hợp. |
| Reactive test không quan sát denial. | Mono chưa subscribe, Reactor Context không có authentication, hoặc cấu hình method security không được nạp. | Sử dụng WebTestClient với springSecurity()/mockUser(), kiểm tra app type và cấu hình. |
| Lời gọi nội bộ từ cùng service bỏ qua hậu kiểm. | Self-invocation không qua Spring AOP proxy. | Đặt phương thức bảo mật trên bean riêng và gọi qua dependency injection. |
| Chỉ thử người đúng quyền. | Nếu interceptor tắt, test vẫn có thể xanh. | Thêm negative test quyền sai và owner sai. |

Một phép thử thực tiễn là tạm vô hiệu @EnableMethodSecurity trên nhánh thử nghiệm: nếu test người sai quyền **không còn thất bại như kỳ vọng**, tức bộ test thật sự phát hiện khi policy không được áp dụng. Khôi phục cấu hình sau thử nghiệm.

## 11. Thực hành và tiêu chí hoàn thành

1. Tạo DocumentView, DocumentRepository và DocumentService như ví dụ, bật @EnableMethodSecurity. Viết test Alice đọc doc-1 thành công, Bob đọc doc-1 bị từ chối dù có cùng document:read.
2. Dùng cùng principal Alice, cùng authority document:read, thay documentId từ doc-1 sang doc-2. Giải thích vì sao thay đổi **chỉ dữ liệu trả về** cũng làm kết quả phân quyền khác.
3. Gỡ điều kiện returnObject != null trong một nhánh thử nghiệm, gọi id không tồn tại để quan sát vấn đề expression hoặc semantics. Khôi phục và quyết định có muốn 403 hay 404 theo yêu cầu API.
4. Thêm một dependency quan sát lời gọi vào service, chứng minh repository đã được gọi trước khi @PostAuthorize trả AccessDeniedException. Giải thích vì sao không dùng hậu kiểm đơn lẻ để bảo vệ lệnh xóa/chuyển tiền.
5. Thêm @PreAuthorize("hasAuthority('document:read')") để chặn quyền thiếu từ đầu, giữ @PostAuthorize cho owner. So sánh số lần repository được gọi khi thiếu authority và khi sai owner.
6. Dùng MockMvc cho 200 (đúng chủ), 403 (sai chủ/thiếu quyền), 401 (chưa đăng nhập) với đúng cấu hình HTTP Basic minh họa. Đảm bảo controller gọi service bean thật.
7. Trong ứng dụng WebFlux riêng, bật @EnableReactiveMethodSecurity và dùng WebTestClient mockUser để thử đối tượng được phát từ Mono: cùng authority nhưng username khác phải cho kết quả khác.
8. Thử JWT/OAuth2/OIDC giả lập theo hệ thống đang dùng. Kiểm tra authentication.name và authorities mà policy thực sự nhìn thấy; tách test xác thực token thật ra khỏi test policy.

**Tiêu chí hoàn thành:** Bộ kiểm thử chứng minh @PostAuthorize được đánh giá **trên đối tượng trả về** của Spring bean được bảo vệ, cho phép đúng người có quyền và từ chối người thiếu quyền hoặc sai chủ sở hữu. Người học cũng phải chứng minh được rằng thân phương thức đã chạy trước khi bị hậu kiểm và chọn @PreAuthorize hoặc policy chặn sớm khi có bất kỳ tác dụng phụ nào cần bảo vệ.

