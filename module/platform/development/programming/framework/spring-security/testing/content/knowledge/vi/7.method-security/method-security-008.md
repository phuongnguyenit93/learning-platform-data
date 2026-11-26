# Quyền theo chủ sở hữu, bean hỗ trợ hoặc PermissionEvaluator

## 1. Từ role đến quyền trên từng đối tượng

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Nhiều nghiệp vụ không thể quyết định chỉ bằng một role hoặc authority chung. Người dùng có thể được phép đọc tài liệu của mình nhưng không được đọc tài liệu của người khác; biên tập viên được sửa bài trong phạm vi được giao; quản trị viên có thể được phép truy cập rộng hơn theo chính sách đã xác định.

Đây là **object-level authorization**: quyết định truy cập phụ thuộc vào đối tượng nghiệp vụ cụ thể, chẳng hạn chủ sở hữu, tenant, trạng thái hoặc ACL của tài liệu.

Spring Security hỗ trợ nhiều cách biểu đạt chính sách:

- **Bean hỗ trợ trong SpEL**: gọi một method Java như @documentAccess.canRead(authentication, #documentId). Cách này linh hoạt, dễ viết unit test và phù hợp khi logic cần truy vấn dữ liệu hoặc nhiều điều kiện nghiệp vụ.
- **PermissionEvaluator**: triển khai hai phương thức hasPermission để đánh giá quyền trên đối tượng đã có hoặc trên cặp ID + loại đối tượng. Sau khi đăng ký evaluator, annotation có thể dùng hasPermission(...).
- **ACL module**: lựa chọn chuyên biệt khi hệ thống cần lưu và quản lý danh sách quyền trên từng đối tượng với mô hình ACL của Spring Security.

Bài học tập trung vào hai lựa chọn đầu tiên, sau đó giới thiệu vị trí của ACL. Sau bài này, bạn có thể:

- Viết chính sách quyền sở hữu dựa trên Authentication và dữ liệu đáng tin cậy ở server.
- Gọi bean hỗ trợ từ @PreAuthorize để giữ logic nghiệp vụ trong Java.
- Triển khai PermissionEvaluator và hiểu hai overload của hasPermission.
- Đăng ký evaluator vào DefaultMethodSecurityExpressionHandler.
- Kiểm thử owner, non-owner, authority thiếu và quyền quản trị bằng @WithMockUser.
- Kiểm chứng qua MockMvc và hiểu cách áp dụng tư duy tương tự trong WebFlux với biểu thức reactive trả Mono<Boolean>.
- Tránh tin dữ liệu owner do client gửi, lọc quyền quá muộn hoặc dùng evaluator đồng bộ để gọi database blocking trong luồng Reactive.

> **Phạm vi phiên bản:** Ví dụ Servlet dùng Spring Security 6.5.x, Spring Boot 3.x và Java 17+. Cấu hình dựa trên @EnableMethodSecurity và MethodSecurityExpressionHandler. WebFlux dùng @EnableReactiveMethodSecurity và Reactor Context. PermissionEvaluator là API đồng bộ; phần Reactive minh họa bean hỗ trợ trả Mono<Boolean>, không chuyển một truy vấn blocking sang event loop.

## 2. Chính sách quyền sở hữu trong ví dụ

Ta dùng hai tài liệu mẫu:

| ID | Chủ sở hữu | Authority cần có |
|---|---|---|
| doc-1 | alice | document:read để đọc, document:write để sửa |
| doc-2 | bob | document:read để đọc, document:write để sửa |

Chính sách được chọn cho bài học:

1. Người dùng thông thường chỉ đọc được tài liệu thuộc mình nếu có document:read.
2. Người dùng thông thường chỉ sửa được tài liệu thuộc mình nếu có document:write.
3. ROLE_ADMIN được đọc và sửa mọi tài liệu.
4. Tài liệu không tồn tại, loại đối tượng không được hỗ trợ, quyền không được nhận diện hoặc authentication không hợp lệ đều bị từ chối.

Đây là **quy tắc minh họa**, không phải mặc định của Spring Security. Ứng dụng thật phải xác định rõ role quản trị có được vượt qua điều kiện tenant/owner hay không. Nếu tenant isolation là ranh giới bắt buộc, ngay cả admin cũng có thể phải thuộc tenant tương ứng.

Sơ đồ quyết định:

~~~mermaid
flowchart TD
    A["Lời gọi service qua Spring proxy"] --> B["Lấy Authentication"]
    B --> C{"Principal hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Tải tài liệu từ nguồn dữ liệu server"]
    D --> E{"Tài liệu tồn tại và loại hợp lệ?"}
    E -- "Không" --> X
    E -- "Có" --> F{"ROLE_ADMIN?"}
    F -- "Có" --> G["Cho phép READ/WRITE theo chính sách"]
    F -- "Không" --> H{"Có phải owner?"}
    H -- "Không" --> X
    H -- "Có" --> I{"Có authority phù hợp?"}
    I -- "Có" --> J["Cho phép"]
    I -- "Không" --> X
~~~

**Không dùng owner do client tự khai** để quyết định quyền. Nếu request gửi JSON như { "id": "doc-1", "owner": "alice" }, người gọi có thể tự sửa owner thành tên của mình. Policy phải lấy chủ sở hữu từ repository hoặc ACL store phía server bằng ID của đối tượng.

## 3. Chuẩn bị model và repository

Bật method security trong application context:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Các biểu thức bên dưới tham chiếu tên tham số như #documentId và #document. Vì vậy, module chứa service cần được biên dịch với -parameters hoặc đặt tên tường minh bằng @P theo phiên bản Spring Security. Ví dụ Maven có thể bật:

~~~xml
<configuration>
    <parameters>true</parameters>
</configuration>
~~~

Với Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Ví dụ model JavaBean:

~~~java
// Document.java
public class Document {

    private final String id;
    private final String owner;
    private final String title;

    public Document(String id, String owner, String title) {
        this.id = id;
        this.owner = owner;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Repository giả lập dữ liệu phía server:

~~~java
// DocumentRepository.java
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private final Map<String, Document> documents = Map.of(
        "doc-1", new Document("doc-1", "alice", "Kế hoạch A"),
        "doc-2", new Document("doc-2", "bob", "Kế hoạch B")
    );

    public Document findById(String id) {
        return documents.get(id);
    }
}
~~~

Map chỉ để ví dụ tự chứa; ứng dụng thật sẽ dùng database hoặc dịch vụ lưu trữ. Repository trả null nếu ID không tồn tại. Các chính sách bên dưới đều từ chối giá trị null, tránh vô tình cấp quyền cho đối tượng không tìm thấy.

## 4. Cách thứ nhất: bean hỗ trợ trong SpEL

Spring Security cho phép gọi method của một bean Spring trong biểu thức. Đây thường là cách dễ tiếp cận nhất khi chính sách có logic Java, truy vấn repository, kiểm tra nhiều điều kiện hoặc cần tái sử dụng giữa các service.

### 4.1. Tách logic quyền vào policy bean

~~~java
// DocumentPermissionPolicy.java
import java.util.Set;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionPolicy {

    private static final Set<String> SUPPORTED_PERMISSIONS =
        Set.of("READ", "WRITE");

    private final DocumentRepository documents;

    public DocumentPermissionPolicy(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean isAllowed(
            Authentication authentication,
            String documentId,
            String targetType,
            String permission) {

        if (!Document.class.getSimpleName().equals(targetType)) {
            return false;
        }

        Document document = documents.findById(documentId);
        return isAllowed(authentication, document, permission);
    }

    public boolean isAllowed(
            Authentication authentication,
            Document document,
            String permission) {

        if (!isValidPrincipal(authentication)
                || document == null
                || permission == null
                || !SUPPORTED_PERMISSIONS.contains(permission)) {
            return false;
        }

        if (hasAuthority(authentication, "ROLE_ADMIN")) {
            return true;
        }

        if (!authentication.getName().equals(document.getOwner())) {
            return false;
        }

        return switch (permission) {
            case "READ" -> hasAuthority(authentication, "document:read");
            case "WRITE" -> hasAuthority(authentication, "document:write");
            default -> false;
        };
    }

    private boolean isValidPrincipal(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean hasAuthority(Authentication authentication, String expected) {
        return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(expected::equals);
    }
}
~~~

Policy nhận Authentication, ID hoặc đối tượng, loại quyền và dữ liệu từ repository. Mọi trường hợp không nhận diện được đều trả false. Ví dụ dùng chuỗi READ/WRITE để dễ đọc; dự án lớn có thể thay bằng enum hoặc permission type riêng, đồng thời vẫn kiểm tra đầu vào không hỗ trợ.

### 4.2. Bean có tên để gọi từ SpEL

~~~java
// DocumentAccess.java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccess {

    private final DocumentPermissionPolicy policy;

    public DocumentAccess(DocumentPermissionPolicy policy) {
        this.policy = policy;
    }

    public boolean can(
            Authentication authentication,
            String documentId,
            String permission) {

        return policy.isAllowed(
            authentication,
            documentId,
            Document.class.getSimpleName(),
            permission
        );
    }
}
~~~

Dùng bean trong annotation:

~~~java
@PreAuthorize("@documentAccess.can(authentication, #documentId, 'READ')")
public Document readWithBean(String documentId) {
    return repository.findById(documentId);
}
~~~

Tên documentAccess trong expression phải trùng tên bean. Tên tham số documentId phải được Spring discover theo cấu hình của dự án; có thể bật -parameters hoặc dùng @P theo phiên bản Spring Security.

### 4.3. Khi nào chọn bean hỗ trợ?

Bean hỗ trợ phù hợp khi:

- Chính sách có nhiều nhánh điều kiện hoặc cần gọi nhiều repository.
- Muốn kiểm thử policy như Java class độc lập, không cần chạy SpEL.
- Cần tái sử dụng cùng một quyết định trong nhiều service hoặc nhiều loại annotation.
- Muốn ghi log/audit có kiểm soát hoặc trả thêm thông tin nội bộ về quyết định.

Không để bean policy trả true khi repository lỗi, không tìm thấy tài liệu hoặc loại quyền lạ. Nếu hệ thống cần phân biệt “không tồn tại” với “không được phép”, hãy thiết kế response/exception ở tầng service hoặc controller; đừng biến lỗi truy vấn thành cấp quyền.

## 5. Cách thứ hai: triển khai PermissionEvaluator

PermissionEvaluator là strategy được expression system gọi khi biểu thức dùng hasPermission. Nó có hai overload:

~~~java
public interface PermissionEvaluator {

    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission
    );
}
~~~

Hai overload tương ứng với hai kiểu biểu thức:

~~~java
// Khi đã có domain object:
@PreAuthorize("hasPermission(#document, 'READ')")
public Document readLoaded(Document document) {
    return document;
}

// Khi chỉ có ID và loại đối tượng:
@PreAuthorize("hasPermission(#documentId, 'Document', 'READ')")
public Document readById(String documentId) {
    return repository.findById(documentId);
}
~~~

Dạng ID hữu ích khi caller chỉ có khóa đối tượng và evaluator cần tự tải dữ liệu để kiểm tra. Dạng object hữu ích khi đối tượng đã được tải từ nguồn tin cậy trước khi authorization được đánh giá.

**Cẩn trọng với overload nhận object:** không lấy một DTO do client gửi, tin các trường owner/tenant của nó rồi gọi hasPermission. Chỉ dùng đối tượng được tải hoặc xác minh từ server; nếu không, caller có thể tự dựng object giả để vượt qua kiểm tra.

### 5.1. Cài đặt cả hai overload

~~~java
// DocumentPermissionEvaluator.java
import java.io.Serializable;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentPermissionPolicy policy;

    public DocumentPermissionEvaluator(DocumentPermissionPolicy policy) {
        this.policy = policy;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        String permissionName = supportedPermission(permission);
        if (permissionName == null) {
            return false;
        }

        return policy.isAllowed(authentication, document, permissionName);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (targetId == null) {
            return false;
        }

        String permissionName = supportedPermission(permission);
        if (permissionName == null) {
            return false;
        }

        return policy.isAllowed(
            authentication,
            targetId.toString(),
            targetType,
            permissionName
        );
    }

    private String supportedPermission(Object permission) {
        if (!(permission instanceof String value)) {
            return null;
        }

        return switch (value) {
            case "READ", "WRITE" -> value;
            default -> null;
        };
    }
}
~~~

Cài đặt này từ chối loại đối tượng khác Document, ID null, permission không được hỗ trợ, principal không hợp lệ, tài liệu không tồn tại và người không có quyền. Nó ủy quyền logic nghiệp vụ cho DocumentPermissionPolicy để bean SpEL và PermissionEvaluator dùng cùng một quy tắc.

Không dùng permission.toString() để tự chấp nhận mọi object tùy ý. Chuyển đổi tường minh giúp chỉ các quyền được định nghĩa mới có thể đi qua policy.

### 5.2. Đăng ký evaluator với MethodSecurityExpressionHandler

Chỉ tạo một bean PermissionEvaluator chưa đủ để hasPermission tự động dùng nó. Phải gắn evaluator vào DefaultMethodSecurityExpressionHandler:

Nếu đã tạo class MethodSecurityConfig tối giản ở mục 3, hãy **thay nội dung class đó** bằng cấu hình dưới đây; không khai báo thêm một class trùng tên.

~~~java
// MethodSecurityConfig.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();

        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
~~~

Phương thức @Bean được khai báo static để Spring công bố expression handler trước khi khởi tạo các cấu hình nội bộ của method security. Đây là chi tiết cấu hình quan trọng trong mô hình @EnableMethodSecurity hiện đại.

Nếu ứng dụng đã có MethodSecurityExpressionHandler để cấu hình RoleHierarchy, trust resolver hoặc một tùy chỉnh khác, hãy hợp nhất các thiết lập vào **một handler**. Không đăng ký nhiều bean cùng kiểu rồi giả định Spring sẽ tự ghép các cài đặt.

Nếu không cấu hình evaluator riêng, Spring Security dùng evaluator mặc định từ chối mọi quyền cho hasPermission. Đây là hành vi an toàn; không nên giả định chỉ cần tạo một @Component implements PermissionEvaluator là đã thay thế được evaluator mặc định.

### 5.3. Dùng hasPermission trong service

~~~java
// DocumentService.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "@documentAccess.can(authentication, #documentId, 'READ')"
    )
    public Document readWithBean(String documentId) {
        return repository.findById(documentId);
    }

    @PreAuthorize(
        "hasPermission(#documentId, 'Document', 'READ')"
    )
    public Document readWithPermissionEvaluator(String documentId) {
        return repository.findById(documentId);
    }

    @PreAuthorize(
        "hasPermission(#document, 'READ')"
    )
    public Document readLoadedDocument(Document document) {
        // Chỉ gọi từ luồng nội bộ đã tải/kiểm tra object từ server.
        return document;
    }
}
~~~

Hai phương thức đầu biểu đạt cùng chính sách nhưng khác điểm mở rộng. readWithBean gọi một bean được đặt tên trong SpEL; readWithPermissionEvaluator gọi strategy chung qua hasPermission. Phương thức readLoadedDocument minh họa overload nhận object và không nên phơi trực tiếp thành endpoint nhận DTO tùy ý.

## 6. Chọn bean hỗ trợ hay PermissionEvaluator?

| Tiêu chí | Bean hỗ trợ trong SpEL | PermissionEvaluator |
|---|---|---|
| Cách gọi | @documentAccess.can(...) | hasPermission(...) |
| Điểm mở rộng | Một bean Java bất kỳ | Strategy chuẩn của Spring Security |
| Phù hợp | Chính sách nghiệp vụ riêng, nhiều điều kiện | Quyền trên domain object theo permission name |
| Tái sử dụng | Có thể gọi từ nhiều annotation hoặc service | Có thể dùng ở các expression có hasPermission |
| Cấu hình | Đăng ký bean và gọi từ SpEL | Cần cấu hình MethodSecurityExpressionHandler |
| Test | Unit test bean và integration test method security | Unit test hai overload và integration test hasPermission |
| Rủi ro thường gặp | Bean expression khó đọc nếu nhồi quá nhiều logic | Quên đăng ký evaluator hoặc xử lý sai targetType/permission |

**Chọn bean hỗ trợ** khi chính sách mang ngữ nghĩa nghiệp vụ cụ thể, ví dụ canApproveInvoice, canReadDocument hoặc belongsToTenant. Tên method làm biểu thức dễ đọc và class Java dễ kiểm thử.

**Chọn PermissionEvaluator** khi ứng dụng có mô hình quyền thống nhất trên nhiều domain object và muốn expression có dạng hasPermission(target, permission). Cách này đặc biệt phù hợp khi tích hợp Spring Security ACL hoặc một kho quyền riêng.

Hai cách không loại trừ nhau. Ví dụ này cho cả hai cùng gọi DocumentPermissionPolicy để tránh tạo hai phiên bản logic khác nhau. Trong một dự án thực tế, hãy chọn một điểm gọi chính cho từng chính sách để người đọc biết nơi cần sửa khi yêu cầu quyền thay đổi.

## 7. Kiểm thử policy và method security với @WithMockUser

### 7.1. Kiểm thử trực tiếp policy bean

Vì DocumentPermissionPolicy là Java class, có thể unit test độc lập với SpEL. Ví dụ dùng TestingAuthenticationToken:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;

class DocumentPermissionPolicyTest {

    private final DocumentRepository repository = new DocumentRepository();
    private final DocumentPermissionPolicy policy =
        new DocumentPermissionPolicy(repository);

    @Test
    void ownerWithReadAuthorityCanRead() {
        Authentication alice = new TestingAuthenticationToken(
            "alice", "password", "document:read"
        );

        assertTrue(policy.isAllowed(
            alice, "doc-1", "Document", "READ"
        ));
    }

    @Test
    void anotherUserCannotReadDocument() {
        Authentication bob = new TestingAuthenticationToken(
            "bob", "password", "document:read"
        );

        assertFalse(policy.isAllowed(
            bob, "doc-1", "Document", "READ"
        ));
    }

    @Test
    void unknownDocumentIsDenied() {
        Authentication alice = new TestingAuthenticationToken(
            "alice", "password", "document:read"
        );

        assertFalse(policy.isAllowed(
            alice, "missing", "Document", "READ"
        ));
    }
}
~~~

TestingAuthenticationToken ở đây chỉ tạo Authentication cho unit test. Nó không kiểm tra password hoặc quá trình xác thực thật. Với các test method security ở mục tiếp theo, @WithMockUser sẽ thiết lập SecurityContext theo cơ chế Spring Security Test.

### 7.2. Kiểm thử service thật qua Spring proxy

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentObjectAuthorizationTest {

    @Autowired
    DocumentService documents;

    @Autowired
    DocumentRepository repository;

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void ownerCanReadThroughHelperBean() {
        assertEquals(
            "doc-1",
            documents.readWithBean("doc-1").getId()
        );
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void ownerCanReadThroughPermissionEvaluator() {
        assertEquals(
            "doc-1",
            documents.readWithPermissionEvaluator("doc-1").getId()
        );
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void nonOwnerIsDeniedByHelperBean() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readWithBean("doc-1"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void nonOwnerIsDeniedByPermissionEvaluator() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readWithPermissionEvaluator("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void ownerWithoutReadAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readWithPermissionEvaluator("doc-1"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadAnotherUsersDocument() {
        assertEquals(
            "doc-2",
            documents.readWithPermissionEvaluator("doc-2").getId()
        );
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void loadedObjectOverloadChecksTrustedDomainObject() {
        Document document = repository.findById("doc-2");

        assertEquals(
            "doc-2",
            documents.readLoadedDocument(document).getId()
        );
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void loadedObjectOverloadRejectsDifferentOwner() {
        Document document = repository.findById("doc-2");

        assertThrows(AccessDeniedException.class,
            () -> documents.readLoadedDocument(document));
    }
}
~~~

Các test trên cần @EnableMethodSecurity, DocumentPermissionEvaluator và MethodSecurityExpressionHandler đã được nạp trong Spring context. Chúng gọi DocumentService được inject, không tạo service bằng new; nhờ vậy method-security proxy thực sự đánh giá annotation.

Các trường hợp được chứng minh:

- Alice có document:read đọc doc-1 qua cả bean hỗ trợ và evaluator.
- Bob có cùng authority nhưng không sở hữu doc-1 nên bị từ chối.
- Alice có document:write nhưng thiếu document:read nên không thể đọc.
- ROLE_ADMIN được phép đọc tài liệu của Bob theo quy tắc minh họa.
- Overload nhận object cho phép Bob đọc object doc-2 của mình và từ chối Alice đọc cùng object.

Nếu bỏ bean handler hoặc không đăng ký PermissionEvaluator, test dùng hasPermission phải thất bại; đây là negative test quan trọng để phát hiện cấu hình evaluator bị quên.

### 7.3. Kiểm tra cả hai overload của evaluator

Nên có unit test trực tiếp cho DocumentPermissionEvaluator để xác minh:

- Object null bị từ chối.
- Object không phải Document bị từ chối.
- targetId null bị từ chối.
- targetType khác Document bị từ chối.
- Permission ngoài READ/WRITE bị từ chối.
- Principal không phải owner và không có ROLE_ADMIN bị từ chối.

Những ca này giúp tránh lỗi do biểu thức hoặc dữ liệu không hợp lệ. Không nên chỉ test happy path với admin, vì quyền quản trị có thể che khuất việc policy owner không hoạt động.

## 8. Kiểm thử qua HTTP với MockMvc

Controller chỉ chuyển ID từ URL vào service. Service vẫn là nơi quyết định quyền theo chủ sở hữu.

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

    @GetMapping("/{id}/bean")
    public Document readWithBean(@PathVariable String id) {
        return documents.readWithBean(id);
    }

    @GetMapping("/{id}/evaluator")
    public Document readWithEvaluator(@PathVariable String id) {
        return documents.readWithPermissionEvaluator(id);
    }
}
~~~

Để cô lập method authorization trong bài thực hành, có thể cho request đi tới controller và dùng request post-processor để cung cấp principal giả lập:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
            .build();
    }
}
~~~

Test MockMvc với Spring Boot 3.x:

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
class DocumentObjectAuthorizationHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerCanReadWithPermissionEvaluator() throws Exception {
        mvc.perform(get("/documents/doc-1/evaluator")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("doc-1"));
    }

    @Test
    void anotherUserGetsForbidden() throws Exception {
        mvc.perform(get("/documents/doc-1/evaluator")
                .with(user("bob").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanReadWithHelperBean() throws Exception {
        mvc.perform(get("/documents/doc-1/bean")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }
}
~~~

Các assertion trên giả định filter chain cho request qua controller, controller gọi service thật và method-security configuration được nạp. Cấu hình permitAll() toàn cục chỉ dùng để cô lập method security trong bài học; ứng dụng thật vẫn cần xác thực và quy tắc URL phù hợp. Nếu dùng form login, HTTP Basic hoặc bearer token, phản hồi khi chưa xác thực có thể khác.

Không dùng @WebMvcTest thay DocumentService bằng mock rồi kết luận PermissionEvaluator hoạt động. Test slice đó có thể chỉ chứng minh controller gọi mock. Để xác minh object-level authorization, hãy gọi service bean thật trong @SpringBootTest và dùng MockMvc như bước bổ sung cho đường request.

## 9. ACL: khi cần quản lý quyền chi tiết trên từng đối tượng

Nếu mỗi tài liệu có nhiều principal hoặc nhóm với quyền khác nhau, một chính sách owner + authority đơn giản có thể không còn đủ. Ví dụ:

- Alice được READ và WRITE doc-1.
- Bob chỉ được READ doc-1.
- Nhóm auditors được READ nhiều tài liệu.
- Một số quyền được kế thừa từ container hoặc thư mục cha.

Đây là bài toán phù hợp với **Access Control List (ACL)**. Spring Security ACL cung cấp mô hình lưu quan hệ giữa đối tượng, SID (principal hoặc authority) và permission. AclPermissionEvaluator triển khai PermissionEvaluator để biểu thức hasPermission sử dụng ACL store.

Ở mức cấu hình, evaluator ACL cũng được gắn vào MethodSecurityExpressionHandler:

~~~java
@EnableMethodSecurity
@Configuration
public class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator aclPermissionEvaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();

        handler.setPermissionEvaluator(aclPermissionEvaluator);
        return handler;
    }
}
~~~

Sau đó service có thể viết:

~~~java
@PreAuthorize("hasPermission(#documentId, 'Document', 'READ')")
public Document read(String documentId) {
    return repository.findById(documentId);
}
~~~

Trong trường hợp này, AclPermissionEvaluator tra quyền từ AclService và các cấu hình ACL tương ứng. Chỉ tạo evaluator mà chưa cấu hình ACL persistence, object identity, SID strategy, permission mapping và schema cần thiết thì chưa có một hệ thống ACL hoạt động hoàn chỉnh.

Không cần đưa ACL vào một ứng dụng nhỏ chỉ có owner và hai quyền READ/WRITE. Bean policy hoặc PermissionEvaluator tùy chỉnh thường đơn giản hơn. Chọn ACL khi thực sự cần quản lý quan hệ quyền trên nhiều đối tượng ở mức dữ liệu.

## 10. WebFlux: dùng policy bean trả Mono<Boolean>

PermissionEvaluator có hai method đồng bộ trả boolean. Nếu implementation gọi repository blocking, việc đó có thể chặn event loop trong ứng dụng Reactive. Vì vậy, không bê nguyên evaluator đồng bộ có truy vấn blocking sang WebFlux.

Spring Security Reactive hỗ trợ bean trong SpEL trả Mono<Boolean> để đưa quyết định authorization vào Reactor pipeline. Có thể lấy Authentication từ ReactiveSecurityContextHolder trong publisher:

~~~java
// ReactiveDocumentRepository.java
import reactor.core.publisher.Mono;

public interface ReactiveDocumentRepository {
    Mono<Document> findById(String id);
}
~~~

Policy Reactive:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component("reactiveDocumentAccess")
public class ReactiveDocumentAccess {

    private final ReactiveDocumentRepository documents;

    public ReactiveDocumentAccess(ReactiveDocumentRepository documents) {
        this.documents = documents;
    }

    public Mono<Boolean> canRead(String documentId) {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context -> Mono.justOrEmpty(context.getAuthentication()))
            .filter(this::isValidPrincipal)
            .flatMap(authentication ->
                documents.findById(documentId)
                    .map(document ->
                        document.getOwner().equals(authentication.getName())
                        && hasAuthority(authentication, "document:read")
                    )
            )
            .defaultIfEmpty(false);
    }

    private boolean isValidPrincipal(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean hasAuthority(Authentication authentication, String expected) {
        return authentication.getAuthorities().stream()
            .anyMatch(authority -> expected.equals(authority.getAuthority()));
    }
}
~~~

Service Reactive:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDocumentService {

    private final ReactiveDocumentRepository documents;

    public ReactiveDocumentService(ReactiveDocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@reactiveDocumentAccess.canRead(#documentId)")
    public Mono<Document> read(String documentId) {
        return documents.findById(documentId);
    }
}
~~~

Cấu hình WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .anyExchange().permitAll())
            .build();
    }
}
~~~

Trong ví dụ, reactiveDocumentAccess trả Mono<Boolean>, và Spring Security Reactive đánh giá kết quả trong Reactor Context. Không gọi block() trong policy; hãy dùng Reactive Repository/WebClient và giữ toàn bộ đường dữ liệu ở dạng reactive.

Test WebTestClient cần controller WebFlux gọi ReactiveDocumentService.read(id), application context nạp cấu hình trên và test security configurer:

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
class ReactiveDocumentAuthorizationTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void ownerCanRead() {
        client.mutateWith(mockUser("alice").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void nonOwnerIsDenied() {
        client.mutateWith(mockUser("bob").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đây là mẫu tích hợp: dự án cần có ReactiveDocumentController với GET /reactive/documents/{id}, repository reactive trả dữ liệu doc-1 thuộc alice và cấu hình WebFlux như trên. WebTestClient subscribe publisher nên quyết định authorization được quan sát. Với test service thuần, dùng StepVerifier và thiết lập Reactor SecurityContext tương ứng.

**Giới hạn quan trọng:** PermissionEvaluator là API đồng bộ và không phải adapter tự động cho Reactive Repository. Trong WebFlux, dùng custom bean trả Mono<Boolean> như trên hoặc một ReactiveAuthorizationManager khi cần chính sách phức tạp hơn. Không gọi repository blocking từ SpEL để cố dùng lại evaluator Servlet.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| hasPermission luôn từ chối dù đã tạo @Component PermissionEvaluator. | Evaluator chưa được gắn vào MethodSecurityExpressionHandler. | Đăng ký DefaultMethodSecurityExpressionHandler và gọi setPermissionEvaluator. |
| Spring không dùng expression handler tùy chỉnh. | Handler được công bố quá muộn hoặc có nhiều handler cạnh tranh. | Khai báo bean static; hợp nhất role hierarchy và evaluator vào một handler. |
| Bean SpEL không tìm thấy. | Tên bean trong annotation không trùng tên component. | Dùng @Component("documentAccess") và gọi đúng @documentAccess. |
| Owner có quyền vẫn bị từ chối. | Authentication.name khác owner hoặc authority không đúng chuỗi. | Kiểm tra username và GrantedAuthority trong test. |
| Người không phải owner đọc được. | Policy tin owner do client gửi hoặc bỏ qua kiểm tra owner. | Tải owner từ repository server-side và viết test khác principal cùng authority. |
| Permission lạ vẫn được cấp. | Evaluator chuyển mọi giá trị permission bằng toString hoặc default allow. | Chỉ chấp nhận READ/WRITE đã định nghĩa; mọi giá trị khác trả false. |
| targetType khác vẫn được xử lý. | Evaluator không kiểm tra loại đối tượng. | So sánh targetType với type được hỗ trợ trước khi truy vấn. |
| Đối tượng null gây lỗi SpEL. | Expression hoặc evaluator không xử lý null. | Từ chối null trong evaluator/policy; cân nhắc kiểm tra null rõ ràng trong expression. |
| Admin vô tình vượt qua tenant boundary. | Quy tắc admin override được viết quá rộng. | Xác định rõ tenant là ranh giới bắt buộc hay admin có quyền toàn hệ thống; kiểm thử cả hai. |
| Test service trực tiếp không thấy AccessDeniedException. | Tự tạo service bằng new hoặc gọi self-invocation bỏ qua proxy. | Inject bean từ Spring context và gọi qua bean proxy. |
| MockMvc trả 403 nhưng policy không chạy. | Filter chain hoặc CSRF chặn request trước method. | Kết hợp test service trực tiếp với request HTTP; kiểm tra cấu hình URL/CSRF. |
| WebFlux bị block hoặc mất authentication. | Policy gọi repository blocking hoặc lấy SecurityContext từ ThreadLocal Servlet. | Dùng Reactive Repository, ReactiveSecurityContextHolder và Mono<Boolean>. |
| Dữ liệu không tồn tại lại được cho phép. | Policy coi lỗi lookup là allow hoặc không kiểm tra null. | Quy định fail closed cho ID/target không tìm thấy. |

## 12. Bài thực hành và tiêu chí hoàn thành

1. Tạo DocumentRepository chứa doc-1 của Alice và doc-2 của Bob. Xây dựng DocumentPermissionPolicy với quyền READ/WRITE và quy tắc ROLE_ADMIN đã nêu.
2. Tạo DocumentAccess bean, dùng @PreAuthorize("@documentAccess.can(authentication, #documentId, 'READ')"). Kiểm tra Alice được phép, Bob bị từ chối.
3. Triển khai DocumentPermissionEvaluator với đủ hai overload: object đã tải và ID + targetType. Từ chối null, targetType không hỗ trợ và permission không hợp lệ.
4. Đăng ký evaluator bằng MethodSecurityExpressionHandler static bean. Thử bỏ cấu hình để thấy hasPermission bị từ chối theo mặc định.
5. Dùng @PreAuthorize("hasPermission(#documentId, 'Document', 'READ')") và kiểm tra kết quả tương đương bean hỗ trợ.
6. Viết @SpringBootTest với @WithMockUser cho owner, non-owner, thiếu authority và ROLE_ADMIN. Gọi service bean thật để đi qua proxy.
7. Dùng MockMvc kiểm tra 200 cho owner và 403 cho non-owner ở endpoint gọi service thật.
8. Thử overload hasPermission(#document, 'READ') với object được repository tải từ server; không nhận object tùy ý từ client.
9. Với WebFlux, tạo policy bean trả Mono<Boolean> lấy Authentication từ ReactiveSecurityContextHolder, rồi dùng WebTestClient mockUser để kiểm tra owner/non-owner.
10. Nếu ứng dụng cần ACL theo từng principal/nhóm trên nhiều đối tượng, nghiên cứu AclPermissionEvaluator và AclService; xác định rõ schema, SID, permission mapping và cache trước khi triển khai.

**Tiêu chí hoàn thành:** Bộ test phải chứng minh người sở hữu với authority đúng được phép, người khác có cùng authority bị từ chối, người thiếu authority bị từ chối và quyền quản trị tuân theo đúng phạm vi đã định. Cả bean hỗ trợ và PermissionEvaluator phải được kiểm tra qua Spring method-security proxy; test HTTP phải đi qua controller thật. Với Reactive, quyết định cần chạy trong Reactor Context bằng publisher không blocking.

## Tài liệu tham khảo

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5.11 — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html)
- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)

