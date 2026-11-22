# Bean chính sách nghiệp vụ và tách biểu thức dài khỏi annotation

> **Ngữ cảnh:** Spring Security – authorization → Biểu thức và chính sách. Bài này tập trung vào việc đóng gói **quy tắc ủy quyền theo nghiệp vụ** trong một Spring bean riêng và gọi bean đó từ `@PreAuthorize`/`@PostAuthorize`. Các ví dụ chính dành cho phương thức đồng bộ dùng Spring AOP, Java 17+ và Spring Security hiện đại.

## 1. Vì sao không nên nhét toàn bộ chính sách vào annotation?

Xét một chức năng đọc tài liệu. Người dùng được xem tài liệu khi **chính họ sở hữu tài liệu**; hoặc tài liệu đã được công bố và người dùng có quyền `DOC_PUBLIC_READ`. Tài liệu không tồn tại phải bị từ chối. Sau này hệ thống còn bổ sung tenant, trạng thái khóa, thời hạn cấp quyền và quyền được ủy nhiệm.

Nếu cố nhét mọi điều kiện vào chuỗi `@PreAuthorize`, mã sẽ có dạng khó kiểm soát như:

~~~java
// Minh họa một biểu thức dần trở nên dài, không phải ví dụ chạy độc lập.
@PreAuthorize(
    "isAuthenticated() and " +
    "(@documentLookup.isOwner(#docId, authentication.name) or " +
    " (@documentLookup.isPublished(#docId) and hasAuthority('DOC_PUBLIC_READ'))) and " +
    "!@documentLookup.isLocked(#docId)"
)
public Document readDocument(long docId) {
    // ...
}
~~~

Vấn đề không nằm ở khả năng tính toán của SpEL mà ở **vị trí đặt chính sách**. Biểu thức dài khiến người đọc khó thấy toàn bộ quy tắc, dễ thiếu ngoặc hoặc sai ưu tiên `and`/`or`, lặp điều kiện ở nhiều service, khó thử riêng từng nhánh, khó phát hiện nhiều lần truy vấn cùng dữ liệu và khó cập nhật khi nghiệp vụ thay đổi.

Cách tổ chức rõ hơn:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public Document readDocument(@P("docId") long docId) {
    // ...
}
~~~

Annotation chỉ thể hiện **ý định cấp quyền**: người gọi được đọc tài liệu này hay không. Bean `documentPolicy` chịu trách nhiệm xác định **vì sao** có hoặc không có quyền. Quy tắc vẫn phải được thực thi qua Spring Method Security; chuyển mã vào một bean thông thường **không tự động** bảo vệ phương thức nếu thiếu annotation hoặc proxy.

### Bốn thành phần và ranh giới trách nhiệm

| Thành phần | Trách nhiệm | Không nên gánh |
| --- | --- | --- |
| `@PreAuthorize` tại service | Đặt chốt trước hành động và chuyển dữ liệu cần xét cho policy | Cây điều kiện nghiệp vụ dài, truy vấn lặp trong SpEL |
| `DocumentPolicy` (`@Component`) | Xét người gọi, quyền, sở hữu, trạng thái tài nguyên và trả quyết định `boolean` | Đổi trạng thái tài liệu như tác dụng phụ của việc kiểm tra |
| `DocumentStore` / repository | Tìm dữ liệu hoặc các thuộc tính tối thiểu cần cho quyết định | Quyết định dựa vào quyền mà chưa biết danh tính người gọi |
| `DocumentService` | Thực hiện nghiệp vụ sau khi được phép; kiểm soát transaction và lỗi nghiệp vụ | Tự tin rằng chỉ controller gọi được, bỏ kiểm tra quyền ở service |

Sơ đồ cho một lệnh đọc có policy:

~~~mermaid
flowchart TD
    A[Controller hoặc service khác gọi bean] --> B[Proxy Method Security]
    B --> C["@PreAuthorize gọi documentPolicy.canRead"]
    C --> D[Policy đọc Authentication và metadata tài liệu]
    D --> E{Quy tắc cho phép?}
    E -- Không --> F[AccessDeniedException]
    E -- Có --> G[DocumentService.read]
    G --> H[Trả Document]
~~~

`@PreAuthorize` đánh giá **trước khi thân phương thức được thực thi**. Nếu policy trả `false`, thân phương thức sẽ không chạy. Nếu policy ném lỗi bất ngờ (ví dụ truy vấn lỗi), lỗi đó không có nghĩa là được phép; tuyệt đối không dùng nhánh bắt ngoại lệ rồi trả `true`.

## 2. Cách Spring Security tìm và gọi policy bean

Giả sử có khai báo:

~~~java
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(/* ... */) {
        // ... 
        return false;
    }
}
~~~

Khi Method Security hoạt động, SpEL trong `@PreAuthorize` hiểu cú pháp sau:

| Thành phần biểu thức | Ý nghĩa |
| --- | --- |
| `@documentPolicy` | Tra cứu Spring bean có tên chính xác `documentPolicy` trong application context |
| `.canRead(...)` | Gọi phương thức public của bean; giá trị trả về quyết định cho phép/từ chối |
| `authentication` | Đối tượng `Authentication` trong ngữ cảnh bảo mật của lời gọi |
| `#docId` | Tham số phương thức được Spring Security tìm thấy với tên `docId` |
| `hasAuthority('DOC_PUBLIC_READ')` | Kiểm tra một `GrantedAuthority` có tên chính xác như vậy |
| `hasRole('ADMIN')` | Theo mặc định, kiểm tra authority `ROLE_ADMIN`; không đồng nghĩa với `hasAuthority('ADMIN')` |

Dấu `@` ở trước tên bean là cú pháp của SpEL để tham chiếu bean; dấu `#` ở trước `docId` là cú pháp tham chiếu biến. Hai ký hiệu này không thể đổi cho nhau. Tên bean có phân biệt ký tự; `@DocumentPolicy` không tự động trỏ tới bean tên `documentPolicy`.

Nếu không đặt tên trong `@Component`, Spring thường đặt tên theo quy tắc mặc định của lớp, nhưng đặt **tên tường minh** giúp annotation ổn định và dễ tìm kiếm trong mã. Một lựa chọn khác là tạo `@Bean(name = "documentPolicy")` trong cấu hình nếu đối tượng được khởi tạo bởi factory.

`@EnableMethodSecurity` kích hoạt các interceptor xử lý `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` (mặc định bật pre/post). Chỉ thêm dependency Spring Security hoặc cấu hình bảo vệ URL **chưa tự kích hoạt Method Security**.

## 3. Thiết kế chính sách: quyết định rõ ràng, mặc định từ chối

Ví dụ đơn giản trong bài này có ba tài liệu:

| ID | Chủ sở hữu | Đã công bố? | Quy tắc đọc |
| --- | --- | --- | --- |
| 1 | `alice` | Không | Chỉ `alice` |
| 2 | `bob` | Không | Chỉ `bob` |
| 3 | `alice` | Có | `alice` hoặc người dùng đã xác thực có authority `DOC_PUBLIC_READ` |

Đây là **quy tắc minh họa**: “đã công bố” không đồng nghĩa cho phép truy cập ẩn danh. Hệ thống giả định quyền `DOC_PUBLIC_READ` vẫn là điều kiện để người không phải chủ sở hữu đọc tài liệu công bố.

Policy cần trả `false` khi:

- Không có người dùng xác thực hợp lệ, hoặc chỉ có anonymous token.
- Tài liệu không tồn tại.
- Không có quyền sở hữu và cũng không thỏa ngoại lệ tài liệu công bố.
- Có yêu cầu vượt ranh giới tổ chức/tenant hoặc tài nguyên bị khóa nếu hệ thống sau này bổ sung những quy tắc đó.

Trong thực tế, không tin `owner`, `tenantId`, `role` do client tự khai trong request làm bằng chứng cấp quyền. Sử dụng định danh/claims đã xác minh từ `Authentication` và trạng thái tài nguyên từ nguồn tin cậy. Không suy đoán quyền của một người chỉ từ ID do họ truyền vào.

Policy tốt có một tên mang ý nghĩa hành động (ví dụ `canRead`, `canEdit`, `canApprove`) và hợp đồng trả về rõ. Không tạo một phương thức `check(Object... args)` chung cho mọi nghiệp vụ nếu nó làm mất thông tin kiểu và khiến quy tắc trở nên khó kiểm thử.

## 4. Ví dụ Spring Boot đầy đủ: một policy bean được gọi từ service

Các tệp dưới đây ghép lại thành ví dụ có thể chạy trong **dự án Spring Boot Gradle đã cấu hình plugin Spring Boot, Java 17+ và JUnit 5**. Spring Boot sẽ quản lý phiên bản Spring Security tương thích qua dependency management. Dữ liệu nằm trong bộ nhớ để minh họa cơ chế; phần repository thật có thể dùng JPA/JDBC với cùng giao diện ý nghĩa.

### 4.1. Dependencies và cấu hình

Trong `build.gradle` của dự án Spring Boot hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu ứng dụng cần HTTP REST thì dùng thêm web starter của ứng dụng, nhưng **kiểm thử Method Security tại service** không yêu cầu tạo controller hay endpoint mẫu.

**`src/main/java/demo/authorization/DemoApplication.java`**

~~~java
package demo.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` đặt cùng lớp chính trong ví dụ để tránh bỏ quên. Với dự án nhiều cấu hình, có thể đặt trên một `@Configuration` riêng.

### 4.2. Model và kho lưu tài liệu

**`src/main/java/demo/authorization/Document.java`**

~~~java
package demo.authorization;

// Record dùng được từ Java 16; ví dụ đặt baseline Java 17+.
public record Document(
        long id,
        String owner,
        String title,
        boolean published) {
}
~~~

**`src/main/java/demo/authorization/DocumentStore.java`**

~~~java
package demo.authorization;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {
    private final Map<Long, Document> documents = Map.of(
        1L, new Document(1L, "alice", "Private draft", false),
        2L, new Document(2L, "bob", "Private memo", false),
        3L, new Document(3L, "alice", "Public guide", true)
    );

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }
}
~~~

`Map.of` bất biến và chỉ được dùng để **đọc** ở ví dụ này. Trong hệ thống thật, `DocumentStore` thường là một adapter tới repository/JPA; nó phải lấy dữ liệu theo ID từ cơ sở dữ liệu, không lấy chủ sở hữu do caller tự khai.

### 4.3. Bean chính sách nghiệp vụ

**`src/main/java/demo/authorization/DocumentPolicy.java`**

~~~java
package demo.authorization;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentStore store;

    public DocumentPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (!isRealUser(authentication)) {
            return false;
        }

        return store.findById(documentId)
                .map(document ->
                        document.owner().equals(authentication.getName())
                        || (document.published()
                            && hasAuthority(authentication, "DOC_PUBLIC_READ")))
                .orElse(false);
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean hasAuthority(Authentication authentication, String required) {
        return authentication.getAuthorities().stream()
                .anyMatch(authority -> required.equals(authority.getAuthority()));
    }
}
~~~

**Giải thích quyết định:**

1. `isRealUser` ngăn người gọi thiếu xác thực và anonymous token. Điều kiện `isAuthenticated()` đứng một mình chưa đủ để phân biệt anonymous token trong một số cấu hình; kiểm tra rõ loại token giúp ví dụ có hành vi dễ đoán.
2. `store.findById(documentId)` đọc tài liệu theo ID thực; nếu không thấy, `orElse(false)` áp dụng mặc định từ chối.
3. `document.owner().equals(authentication.getName())` cho phép chủ sở hữu. Hệ thống thật có thể so sánh immutable user ID thay vì username dễ đổi.
4. `document.published() && hasAuthority(...)` cho phép người không phải chủ sở hữu đọc tài liệu đã công bố, nhưng chỉ khi authority phù hợp.
5. Phương thức chỉ **đọc** và trả `boolean`; không xóa, gửi thông báo, cấp role hay thay đổi tài liệu khi làm bước kiểm tra.

Java có cơ chế short-circuit: sau khi nhánh sở hữu đúng, nhánh authority không cần chạy. Điều này không làm cho biểu thức thiếu an toàn; hai nhánh tạo thành một quy tắc `OR` có chủ ý, nằm bên trong các điều kiện đầu vào hợp lệ.

### 4.4. Service công khai hành động cần bảo vệ

**`src/main/java/demo/authorization/DocumentService.java`**

~~~java
package demo.authorization;

import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
    public Document read(@P("docId") long docId) {
        return store.findById(docId)
                .orElseThrow(() -> new NoSuchElementException("Document not found"));
    }
}
~~~

Khi gọi `documentService.read(1L)` qua Spring bean proxy, trình tự diễn ra như sau:

1. Advisor của `@PreAuthorize` lấy `Authentication` và giá trị `#docId` từ lời gọi.
2. SpEL phân giải bean `documentPolicy` và gọi `canRead(authentication, docId)`.
3. `true` → thực thi thân phương thức `read`; `false` → chặn lời gọi và ném `AccessDeniedException`.
4. Service vẫn có cách xử lý dữ liệu không tồn tại để đối phó trường hợp trạng thái thay đổi **sau** bước kiểm tra (ví dụ tài liệu bị xóa đồng thời).

Tại sao dùng `@P("docId")`? Spring Security cần biết tên đối số khi đánh giá `#docId`. Tham số Java có thể được tìm bằng cờ biên dịch `-parameters`, annotation `@P` hoặc một số cơ chế phát hiện tên khác; đặt `@P` trong ví dụ giúp cách liên kết tên rõ ràng và tránh phụ thuộc vào cờ của dự án.

Không gọi `new DocumentService(...)` trong kiểm thử của annotation: đối tượng tạo bằng `new` không được Spring đặt proxy Method Security. Cũng không gọi nội bộ `this.read(...)` từ một phương thức khác trong cùng service rồi mong annotation chạy; lời gọi nội bộ thường đi vòng qua proxy.

### 4.5. Kiểm thử tích hợp: quyết định đúng và chặn thực sự

**`src/test/java/demo/authorization/DocumentServiceTest.java`**

~~~java
package demo.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = DemoApplication.class)
class DocumentServiceTest {
    @Autowired
    private DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadPrivateDocument() {
        assertEquals(1L, service.read(1L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void differentOwnerCannotReadPrivateDocument() {
        assertThrows(AccessDeniedException.class, () -> service.read(1L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_PUBLIC_READ")
    void authorityAllowsReadingPublishedDocument() {
        assertEquals(3L, service.read(3L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void publishedDocumentStillRequiresTheAuthorityForNonOwner() {
        assertThrows(AccessDeniedException.class, () -> service.read(3L));
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownIdIsDeniedBeforeEnteringServiceBody() {
        assertThrows(AccessDeniedException.class, () -> service.read(999L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserCannotReadPublishedDocument() {
        assertThrows(AccessDeniedException.class, () -> service.read(3L));
    }
}
~~~

Các test có ý nghĩa khác nhau: test `alice` xác minh đường **cho phép**, các test `bob` xác minh **không lộ tài liệu riêng tư**, test quyền đọc tài liệu công bố phân biệt authority với sở hữu, test ID không tồn tại kiểm tra **mặc định từ chối**, test anonymous kiểm tra nhánh xác thực. Tất cả đều lấy `DocumentService` từ Spring Context để kiểm tra cả **proxy lẫn policy**.

Từ thư mục dự án Gradle, chạy:

~~~text
./gradlew test --tests demo.authorization.DocumentServiceTest
~~~

Trên Windows:

~~~text
gradlew.bat test --tests demo.authorization.DocumentServiceTest
~~~

Không có stdout riêng được in từ các phương thức mẫu. Khi cấu hình đầy đủ và mọi assertion đúng, tác vụ kiểm thử sẽ kết thúc thành công (Gradle thường hiển thị `BUILD SUCCESSFUL`); không nên tự tuyên bố đã chạy kiểm thử chỉ từ việc đọc ví dụ.

### 4.6. Kiểm thử đơn vị: thử từng nhánh policy mà không cần Spring AOP

Chính sách nằm trong bean nhưng bản chất là một lớp Java được tiêm dependency. Do đó ta có thể kiểm thử **trực tiếp logic** và nhận ra lỗi rẽ nhánh nhanh hơn.

**`src/test/java/demo/authorization/DocumentPolicyTest.java`**

~~~java
package demo.authorization;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPolicyTest {
    private final DocumentPolicy policy =
            new DocumentPolicy(new DocumentStore());

    @Test
    void ownerAndMissingDocument() {
        Authentication alice =
                new UsernamePasswordAuthenticationToken("alice", "unused", List.of());

        assertTrue(policy.canRead(alice, 1L));
        assertFalse(policy.canRead(alice, 2L));
        assertFalse(policy.canRead(alice, 999L));
    }

    @Test
    void publishedDocumentNeedsExplicitAuthorityForOtherUser() {
        Authentication bob = new UsernamePasswordAuthenticationToken(
                "bob", "unused", List.of());
        Authentication bobWithRead = new UsernamePasswordAuthenticationToken(
                "bob", "unused",
                List.of(new SimpleGrantedAuthority("DOC_PUBLIC_READ")));

        assertFalse(policy.canRead(bob, 3L));
        assertTrue(policy.canRead(bobWithRead, 3L));
        assertFalse(policy.canRead(bobWithRead, 1L));
    }

    @Test
    void nullAuthenticationIsDenied() {
        assertFalse(policy.canRead(null, 3L));
    }
}
~~~

Dùng constructor ba đối số của `UsernamePasswordAuthenticationToken` trong unit test tạo đối tượng được đánh dấu là đã xác thực, phù hợp với việc thử logic quyền. Kiểm thử đơn vị **không thay thế** kiểm thử Spring proxy; nếu quên `@EnableMethodSecurity`, unit test của `DocumentPolicy` vẫn có thể xanh, trong khi annotation bị bỏ qua. Phải có cả hai lớp kiểm chứng.

Chạy toàn bộ hai lớp test:

~~~text
./gradlew test --tests demo.authorization.DocumentPolicyTest --tests demo.authorization.DocumentServiceTest
~~~

## 5. Tại sao nên truyền `Authentication` và ID vào policy?

Có nhiều lựa chọn tạo tham số cho chính sách:

| Chữ ký | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- |
| `canRead(Authentication auth, long id)` | Quyết định dựa trên danh tính và tài liệu xác định bằng ID | Policy có thể phải truy vấn dữ liệu; nguy cơ hai lần đọc ở precheck và service |
| `canRead(Authentication auth, Document doc)` | Service đã có đối tượng từ nguồn tin cậy, hoặc kiểm tra ở giai đoạn sau | Không tự tin dữ liệu `Document` do client gửi là chính xác |
| `canRead(Authentication auth, long id, String operation)` | Quy tắc chung cho nhiều hành động có cấu trúc rõ | Kiểm soát tập giá trị operation, đừng so sánh chuỗi tự do khắp nơi |
| `decide(MethodSecurityExpressionOperations root)` | Cần ngữ cảnh SpEL phong phú hoặc tích hợp sâu với expression API | Phụ thuộc Spring Security hơn; tránh nếu tham số tường minh đã đủ |

Ví dụ hiện tại dùng `canRead(Authentication, long)` vì người dùng chỉ truyền ID, còn policy đọc tình trạng thực từ kho dữ liệu. Nó cũng giúp kiểm thử đơn vị chỉ cần tạo `Authentication` và `DocumentStore`.

**Không nên viết** `@PreAuthorize("@documentPolicy.canRead(#owner, #docId)")` nếu `#owner` là tham số người gọi tự truyền để xác nhận họ sở hữu tài liệu. Caller có thể gửi bất kỳ `owner` nào. Kiểm tra phải gắn với danh tính từ `Authentication` đã được Spring Security xác thực.

Với JWT/OIDC, `authentication.name` thường dựa vào claim được cấu hình làm tên, và không phải lúc nào là định danh bền vững cho chủ sở hữu. Nếu policy cần user ID hoặc tenant ID, hãy dùng claim/tài khoản đã được xác minh thông qua thành phần chuyển đổi token hoặc resolver đáng tin cậy. Đừng dùng email dễ đổi hoặc `tenantId` trong URL như bằng chứng duy nhất.

## 6. Trường hợp có nhiều hành động: phân chia policy theo nghiệp vụ

Khi mở rộng sang chỉnh sửa và phê duyệt, nên giữ **tên hành động cụ thể**, thay vì sao chép chuỗi SpEL phức tạp vào nhiều service:

~~~java
// Minh họa thiết kế mở rộng, không phải phần của ví dụ chạy đầy đủ ở mục 4.
@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(Authentication auth, long docId) { /* ... */ return false; }
    public boolean canEdit(Authentication auth, long docId) { /* ... */ return false; }
    public boolean canApprove(Authentication auth, long docId) { /* ... */ return false; }
}
~~~

~~~java
// Minh họa chữ ký ở một service khác.
@PreAuthorize("@documentPolicy.canEdit(authentication, #docId)")
public void edit(@P("docId") long docId, UpdateDocumentCommand command) {
    // Thực thi cập nhật chỉ sau khi được phép.
}

@PreAuthorize("@documentPolicy.canApprove(authentication, #docId)")
public void approve(@P("docId") long docId) {
    // Kiểm tra thêm điều kiện nghiệp vụ ngay khi cập nhật.
}
~~~

Hai đoạn trên chỉ minh họa cách đặt tên. Các lớp `UpdateDocumentCommand` và hành vi cập nhật chưa được triển khai trong ví dụ mục 4; không đưa nguyên hai đoạn vào đó rồi tưởng chúng biên dịch như một chương trình đầy đủ.

Cách phân chia hợp lý là:

- `canRead`: dựa vào chủ sở hữu, trạng thái công bố và quyền đọc.
- `canEdit`: xét quyền sửa, chủ sở hữu, trạng thái đã khóa và phạm vi tổ chức.
- `canApprove`: xét vai trò người duyệt, tránh tự duyệt và trạng thái quy trình.

Nếu một chính sách dùng chung nhiều service, dùng bean trung tâm có tên và phụ thuộc rõ ràng. Nếu vài dòng SpEL đơn giản như `hasAuthority('DOC_READ')` đã đủ, không nhất thiết tạo bean cho điều kiện đó. Đưa vào bean khi **quy tắc nghiệp vụ** cần tái sử dụng, truy vấn, kết hợp nhiều điều kiện hoặc kiểm thử độc lập.

Có thể kết hợp chốt cấp quyền thô với policy:

~~~java
// Chỉ minh họa, khác với chính sách trong ví dụ chạy ở mục 4.
@PreAuthorize(
    "hasAuthority('DOC_READ') and @documentPolicy.canRead(authentication, #docId)")
public Document read(@P("docId") long docId) {
    // ...
}
~~~

Trong ví dụ này, `hasAuthority('DOC_READ')` là **điều kiện bắt buộc thêm**; nó không tự thay thế kiểm tra chủ sở hữu. Đừng sao chép biểu thức trên vào test mục 4 nếu chưa cấp authority `DOC_READ` cho những user được phép, vì điều kiện mới sẽ làm các test đó bị từ chối.

## 7. Khác biệt giữa pre-authorization và post-authorization

Hai dạng annotation thường gặp:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public Document read(@P("docId") long docId) {
    // Chỉ chạy sau khi kiểm tra cho phép.
    // ...
}
~~~

~~~java
// Minh họa biến thể hậu kiểm, cần định nghĩa canReadObject và lookup.
@PostAuthorize("@documentPolicy.canReadObject(authentication, returnObject)")
public Document readThenCheck(long docId) {
    // Thân phương thức chạy trước khi policy xét returnObject.
    // ...
}
~~~

**`@PreAuthorize`** phù hợp khi mục tiêu là chặn trước hành động có tác dụng phụ, ví dụ xóa, sửa, duyệt, chuyển tiền, gửi thông báo. **`@PostAuthorize`** dùng khi cần xét đối tượng trả về thực tế (`returnObject`), ví dụ việc kiểm tra sở hữu chỉ thực hiện được sau khi load dữ liệu. Tuy nhiên thân phương thức đã chạy trước hậu kiểm, nên không dùng `@PostAuthorize` làm biện pháp duy nhất để bảo vệ hành động ghi dữ liệu.

Một số trường hợp service đã phải đọc dữ liệu thì dùng hậu kiểm có thể tiết kiệm một lần lookup so với kiểm tra trước. Đó là sự đánh đổi cần chủ động đánh giá: không chọn hậu kiểm chỉ vì muốn tránh một truy vấn nếu nó khiến tác dụng phụ xảy ra trước khi kiểm tra quyền.

`@PostFilter` và `@PreFilter` lại phục vụ lọc **phần tử** trong tập dữ liệu. Chúng không thay thế hoàn toàn một bean `canRead(...)` quyết định quyền truy cập một tài nguyên. Với danh sách lớn hoặc phân trang, nên lọc ngay trong truy vấn dữ liệu thay vì tải mọi bản ghi rồi bỏ bớt ở bộ nhớ.

## 8. Quy tắc quan trọng trong hệ thống nhiều tenant và dữ liệu thay đổi

### 8.1. Ranh giới tenant phải được kiểm trước ngoại lệ quyền khác

Giả sử tài liệu có `tenantId`. Một biểu thức nguy hiểm là:

~~~java
// KHÔNG dùng nếu ADMIN chỉ được quản trị trong tenant của họ:
boolean allowed = hasAdminAuthority || (sameTenant && isOwner);
~~~

Ở đây người có quyền admin có thể vượt qua `sameTenant`. Cấu trúc đúng khi admin chỉ có quyền trong tenant là:

~~~java
// Minh họa boolean thuần Java, không phải tệp hoàn chỉnh.
boolean allowed = sameTenant && (hasAdminAuthority || isOwner);
~~~

`sameTenant` phải tính từ tenant của tài liệu và tenant thực đã được xác thực/ủy quyền của người dùng; không dùng tenant client tùy ý điền để tạo điều kiện đúng giả.

Nếu ứng dụng có quyền quản trị liên tenant, hãy thể hiện quyền đó bằng một nhánh riêng, có điều kiện và kiểm thử riêng; tránh ngầm cho mọi `ROLE_ADMIN` quyền đọc mọi tenant.

### 8.2. Policy lookup rồi service lookup có thể gặp TOCTOU

Trong ví dụ mục 4, `DocumentPolicy` đọc tài liệu để xét quyền và `DocumentService` đọc lại để trả kết quả. Dữ liệu trong bộ nhớ là bất biến nên không có vấn đề, nhưng với database thật có thể xảy ra:

~~~text
T1: Policy thấy tài liệu 1 thuộc alice -> cho phép
T2: Một giao dịch khác đổi owner/tenant của tài liệu 1
T3: Service đọc lại tài liệu 1 đã thay đổi -> kết quả không còn phù hợp
~~~

Đây là khoảng cách giữa **thời điểm kiểm tra** và **thời điểm sử dụng** (time-of-check/time-of-use). Tùy tính chất nghiệp vụ, cần đưa điều kiện quyền vào chính câu lệnh truy vấn/cập nhật, dùng transaction thích hợp, kiểm soát phiên bản dữ liệu hoặc khóa cần thiết. Không xem `@PreAuthorize` như một hàng rào bảo đảm trạng thái database bất biến giữa hai lệnh.

Với tác vụ ghi cần sự nhất quán mạnh, ví dụ cập nhật chỉ khi đúng owner/tenant, có thể dùng phép cập nhật có điều kiện:

~~~sql
-- Minh họa ý tưởng SQL; cú pháp cụ thể phụ thuộc database và schema.
UPDATE documents
SET title = :new_title
WHERE id = :id
  AND owner_id = :authenticated_user_id
  AND tenant_id = :trusted_tenant_id
  AND locked = false;
~~~

Kiểm tra số hàng bị thay đổi và xử lý kết quả 0 hàng là một phần của hợp đồng nghiệp vụ. Annotation bảo vệ **lời gọi**, còn lệnh database có điều kiện bảo vệ **trạng thái thực tại thời điểm ghi**.

### 8.3. Hiệu năng và giao dịch

Nếu `canRead` truy vấn database mỗi khi đọc, gọi nó trong một vòng lặp danh sách hàng trăm tài liệu có thể tạo N+1 query. Khi trả về danh sách, hãy để repository lọc theo user/tenant ngay từ truy vấn, hoặc thực hiện kiểm tra theo lô với dữ liệu tối thiểu. Tránh gọi repository nhiều lần chỉ vì đặt nhiều điều kiện trong SpEL.

Trong phương thức có `@Transactional`, thứ tự các advisor có thể khiến pre-authorization chạy trước lúc transaction nghiệp vụ mở. Đừng đặt logic policy dựa vào quan hệ JPA lazy mà giả định transaction của thân phương thức đã tồn tại. Nếu policy cần truy vấn, hãy thiết kế truy vấn chuyên biệt hoặc transaction đọc phù hợp và kiểm chứng theo bản cấu hình thực tế. Việc thêm `@Transactional` bừa bãi vào mọi policy có thể tạo chi phí và ngữ nghĩa giao dịch không mong đợi.

### 8.4. Không để lỗi trả về tạo lộ thông tin

Nếu tài liệu không tồn tại hay thuộc người khác đều dẫn tới một kết quả từ chối, người ngoài có thể ít suy đoán được ID tài nguyên. Nhưng `AccessDeniedException` thường được tầng HTTP chuyển thành 403 khi xử lý request, còn `NoSuchElementException` thường cần ánh xạ riêng thành 404. Việc ứng dụng chọn 403/404 cho tài nguyên ngoài quyền phải nhất quán với chính sách chống dò ID, API contract và thiết kế lỗi; bản thân policy bean không tự đảm bảo mã HTTP.

Tránh ghi log token, thông tin riêng tư hoặc toàn bộ đối tượng tài liệu trong đường kiểm tra quyền. Khi cần audit, lưu ID tài nguyên, actor ID, hành động, kết quả và mã lý do an toàn; quyết định chỉ nên được tính từ trạng thái đáng tin cậy.

## 9. Phần nào giữ trong annotation, phần nào đưa vào bean?

| Trường hợp | Lựa chọn phù hợp |
| --- | --- |
| Mỗi phương thức chỉ cần một authority cố định | `@PreAuthorize("hasAuthority('DOC_READ')")` |
| Quy tắc theo owner, trạng thái, tenant, delegated access | `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")` |
| Quy tắc giống nhau ở nhiều phương thức với tên hành động cụ thể | Một policy bean tái sử dụng với phương thức `canRead`, `canEdit`, ... |
| Muốn đổi tên annotation để dễ đọc trong hệ thống | Meta-annotation, ví dụ `@CanReadDocument`, bên dưới vẫn dùng `@PreAuthorize`; cân nhắc nếu tái sử dụng nhiều |
| Muốn thống nhất quyền cho request, method, scheduler hoặc message | Thiết kế `AuthorizationManager` hay một chính sách cốt lõi dùng chung; tránh nhân bản logic |
| Bài toán có tập kết quả rất lớn hoặc phân trang | Ràng buộc quyền tại repository/query; không dựa vào lọc hậu kỳ toàn bộ |
| Chỉ một nhánh kiểm tra ngắn, không có quy tắc nghiệp vụ | Dùng SpEL ngắn trực tiếp, tránh trừu tượng hóa quá mức |

**Bean chính sách nghiệp vụ** thường là lựa chọn cân bằng: tận dụng Method Security đã có, chuyển logic sang Java có kiểu, dùng dependency injection và viết unit test trực tiếp. `AuthorizationManager` thích hợp khi cần tích hợp sâu hơn với hạ tầng quyết định cấp quyền của Spring Security. Không cần xây custom expression handler chỉ để gọi một phương thức Java.

## 10. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@PreAuthorize` không chặn được gì | Thiếu `@EnableMethodSecurity` hoặc gọi ngoài proxy | Bật Method Security, gọi bean do Spring quản lý, thêm test người khác chủ |
| SpEL báo không tìm thấy bean | Sai tên `@documentPolicy`, thiếu `@Component` hoặc bean nằm ngoài vùng component scan | Khớp tên bean và cấu hình quét lớp |
| SpEL không đọc đúng `#docId` | Thiếu metadata tên tham số, tên viết sai, phương thức interface không có tên tham số | Dùng `@P("docId")`, bật `-parameters`, kiểm thử từ context |
| Unit test policy xanh nhưng service vẫn cho truy cập trái quyền | Chỉ test phương thức Java, không chạy annotation/proxy | Thêm integration test `@SpringBootTest` + `@WithMockUser` |
| Người dùng được cấp quyền vì tự truyền `owner` hoặc `tenantId` | Tin tham số không được xác thực | Lấy identity từ `Authentication`, tài nguyên từ repository đáng tin |
| Tài liệu không tồn tại gây lỗi nội bộ hoặc lộ thông tin | Không xử lý `Optional.empty()` hoặc phân biệt trạng thái ngoài ý muốn | Mặc định từ chối; thống nhất API 403/404 |
| Dữ liệu ghi đã bị thay đổi dù cuối cùng bị từ chối | Dùng hậu kiểm sau khi thân phương thức đã chạy | Đặt chốt `@PreAuthorize`; kiểm tra invariant khi ghi DB |
| Chậm vì truy vấn lặp | Mỗi biểu thức lại gọi repository, policy và service cùng đọc dữ liệu | Đọc projection tối thiểu, truy vấn có điều kiện, gom kiểm tra và đo hiệu năng |
| Policy ném ngoại lệ rồi bất ngờ được phép | Bắt mọi exception và trả `true` cho "fallback" | Fail closed; log kỹ thuật phù hợp, không biến lỗi thành quyền |
| Phần kiểm tra lazy JPA lỗi ngoài transaction | Advisor chạy trước transaction nghiệp vụ, dữ liệu chưa load | Truy vấn policy riêng, cấu hình giao dịch rõ và kiểm thử integration |

### Tên tham số, quyền và logic boolean

Dễ nhầm `hasRole('ADMIN')` với `hasAuthority('ADMIN')`. Với prefix mặc định, `hasRole('ADMIN')` tìm `ROLE_ADMIN`, còn `hasAuthority('ADMIN')` chỉ tìm `ADMIN`. Không viết các phép OR mở quá rộng nếu admin vẫn phải tuân thủ tenant hoặc trạng thái tài liệu.

SpEL có toán tử `and`/`or`, nhưng các biến thể như `isAuthenticated() and hasRole('ADMIN') or ...` có thể dẫn đến điều kiện quyền rộng hơn mong muốn nếu thiếu ngoặc. Đưa biểu thức phức tạp vào Java với `if` và hàm tên rõ giúp người review nhìn thấy thứ tự điều kiện. Kiểm thử cả những trường hợp biên như authenticated admin sai tenant, tài liệu khóa, owner đã nghỉ việc, hoặc thiếu quyền.

## 11. Chiến lược kiểm thử và checklist review

| Nhóm tình huống | Kết quả mong đợi | Loại test |
| --- | --- | --- |
| Chủ sở hữu, tài liệu riêng tư | Cho phép | Policy unit + Method Security integration |
| Người khác, tài liệu riêng tư | Từ chối | Policy unit + Method Security integration |
| Người khác, tài liệu công bố, có authority | Cho phép | Unit + integration |
| Người khác, tài liệu công bố, thiếu authority | Từ chối | Unit + integration |
| Anonymous, không có principal, ID không tồn tại | Từ chối | Unit + integration phù hợp |
| Người khác tenant, admin tenant cũ | Từ chối nếu quy tắc không cho vượt tenant | Unit + DB integration cho tenant |
| Thay đổi owner/trạng thái đồng thời lúc ghi | Không ghi dữ liệu sai quyền | Integration với database/transaction |
| Gọi qua Spring proxy, gọi nội bộ cùng bean | Xác nhận chốt có chạy đúng ranh giới | Integration; sửa thiết kế nếu tự gọi cùng bean |
| Nâng cấp Spring Security | Hành vi quyền không thay đổi ngoài chủ đích | Chạy lại regression tests ở dependency mới |

**Hướng kiểm thử:** test logic policy bằng cách khởi tạo class Java và dependency test-double/kho đơn giản, sau đó test **chặn thực tế** qua bean Spring. Unit test không nhận biết cấu hình `@EnableMethodSecurity` thiếu; integration test mới phát hiện được lỗi đó. Test của authorization cần cả đường được phép và bị từ chối; chỉ test happy path không chứng minh được hệ thống chặn truy cập trái quyền.

Khi code review một policy mới, tự trả lời:

1. Tài nguyên nào được bảo vệ, và hành động nào được cho phép?
2. Người gọi được nhận diện bằng nguồn tin cậy nào? ID hay tenant có thể bị giả mạo không?
3. Nếu không tìm thấy tài nguyên, thiếu quyền hoặc lỗi dữ liệu, điều gì xảy ra?
4. Annotation có nằm trên bean/method được proxy chặn thật không?
5. Đọc dữ liệu trong policy có gây query lặp, lazy loading hay race không?
6. Có test người dùng khác, anonymous, dữ liệu không tồn tại, tenant khác và quyền nâng cao chưa?
7. Những đoạn logic nào có thể chuyển từ SpEL sang một phương thức Java rõ tên để dễ bảo trì?

## 12. Bài tập thực hành

**Bài 1 – Thêm quyền sửa.** Bổ sung `canEdit(Authentication auth, long docId)` yêu cầu người gọi là owner **và** có `DOC_EDIT`, tài liệu chưa khóa. Thêm `@PreAuthorize("@documentPolicy.canEdit(authentication, #docId)")` vào phương thức cập nhật. Viết test rằng owner thiếu `DOC_EDIT` cũng bị từ chối, người có `DOC_EDIT` nhưng không sở hữu cũng bị từ chối.

**Bài 2 – Tenant-safe policy.** Mở rộng `Document` thêm `tenantId` và thêm bộ xác định tenant đáng tin cậy cho `Authentication`. Một quản trị viên của tenant A không thể đọc tài liệu của tenant B. Viết test trường hợp tên người dùng trùng nhau ở hai tenant.

**Bài 3 – Chuyển biểu thức dài.** Tìm một annotation nhiều điều kiện đọc dữ liệu từ repository. Viết bảng chân trị, chuyển chính sách vào bean với tên hành động rõ ràng, giữ annotation ngắn, test từng nhánh và so sánh số lượt truy vấn trước/sau.

**Bài 4 – Tự gọi nội bộ.** Tạo hai phương thức trong cùng `@Service`, phương thức thứ nhất gọi `this.read(...)` đang có `@PreAuthorize`. Chứng minh bằng integration test rằng lời gọi nội bộ có thể vượt proxy và thiết kế lại để lời gọi đi qua service bean phù hợp. Không dùng self-injection như giải pháp mặc định cho bài toán kiến trúc.

**Tiêu chí hoàn thành:** người học phân biệt được điều kiện đơn giản trong annotation với quy tắc nghiệp vụ trong policy bean; dùng đúng `@bean`, `authentication`, `#param`; chặn thực tế qua Spring proxy; viết test cả quyền cho phép và từ chối; nhận biết các nguy cơ tenant, thời điểm kiểm tra và truy vấn lặp.

## Tài liệu tham khảo

- Spring Security, **Method Security** – `@EnableMethodSecurity`, `@PreAuthorize`, Spring AOP proxy, parameter names và dùng custom bean từ SpEL: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, **Testing Method Security** – `@WithMockUser`, `@WithAnonymousUser`, test qua Spring Context: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security, **Authorization Architecture** – phân biệt authority và authorization decision: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Framework, **SpEL Bean References** – cú pháp `@beanName`: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html
