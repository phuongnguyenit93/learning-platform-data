# hasPermission với đối tượng đã được tải

> **Chủ đề:** Spring Security – authorization → **PermissionEvaluator**. Bài học tập trung vào biểu thức `hasPermission(domainObject, permission)` khi đối tượng miền đã có trong bộ nhớ, cách cấu hình `PermissionEvaluator`, khác biệt giữa kiểm tra trước và sau khi thực thi phương thức, và những điều cần làm để không tin một đối tượng do caller tự tạo. Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x; những khái niệm cốt lõi vẫn áp dụng cho các bản hiện hành khi cấu hình và kiểm thử đúng phiên bản.

## 1. Bài toán: có quyền với đúng đối tượng nào?

Giả sử một hệ thống tài liệu có dữ liệu:

| ID | Chủ sở hữu | Chia sẻ? | Đã khóa sửa? |
| --- | --- | --- | --- |
| 101 | `alice` | Không | Không |
| 202 | `bob` | Không | Không |
| 303 | `alice` | Có | Không |
| 404 | `alice` | Không | Có |

Yêu cầu nghiệp vụ:

- `READ`: chủ sở hữu được đọc; người khác chỉ được đọc tài liệu đã chia sẻ **và** có authority `DOC_SHARED_READ`.
- `EDIT`: chủ sở hữu **và** có authority `DOC_EDIT`, đồng thời tài liệu chưa khóa.
- Anonymous, thiếu dữ liệu xác thực, ID không tồn tại, đối tượng bị giả mạo, hoặc permission không được định nghĩa đều phải bị từ chối.

`hasAuthority('DOC_EDIT')` chỉ kiểm tra một authority của người dùng, không trả lời được **tài liệu cụ thể có thuộc người dùng đó hay đang bị khóa không**. `hasPermission` là một hook để chuyển quyết định theo **từng domain object** sang Java, nơi có thể xét người dùng, tài nguyên và chính sách nghiệp vụ.

Hai biểu thức quan trọng:

~~~java
// Minh họa một method nhận object đã tồn tại TRƯỚC lúc gọi.
@PreAuthorize("hasPermission(#document, 'EDIT')")
public void prepareEdit(@P("document") Document document) {
    // Chỉ chạy khi PermissionEvaluator cho phép.
}
~~~

~~~java
// Minh họa một method TỰ TẢI object và kiểm tra trước khi trả cho caller.
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
public Document read(long id) {
    // Tải từ repository...
}
~~~

Hai đoạn trên là **chữ ký minh họa**, chưa tự biên dịch độc lập; ví dụ đầy đủ ở phần sau có đủ package, class, cấu hình và test.

## 2. Hai overload của `PermissionEvaluator`

Spring Security định nghĩa giao diện `org.springframework.security.access.PermissionEvaluator` với hai phương thức có ý nghĩa khác nhau:

~~~java
// HÌNH DẠNG API RÚT GỌN, KHÔNG TẠO LẠI GIAO DIỆN CỦA THƯ VIỆN.
boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission);

boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission);
~~~

| SpEL | Phương thức Java được gọi | Trường hợp |
| --- | --- | --- |
| `hasPermission(#document, 'READ')` | `hasPermission(Authentication, Object, Object)` | `document` đã có ở đầu vào |
| `hasPermission(returnObject, 'READ')` | Cùng overload nhận domain object | Object vừa được method tải và trả về |
| `hasPermission(filterObject, 'READ')` | Cùng overload nhận domain object, lặp cho từng phần tử | `@PreFilter`/`@PostFilter` |
| `hasPermission(#id, 'Document', 'READ')` | `hasPermission(Authentication, Serializable, String, Object)` | Chỉ biết ID + tên loại object, chưa có object |

`Authentication` được Spring Security truyền **ngầm** vào evaluator. Vì thế trong annotation chỉ viết `hasPermission(object, permission)` hoặc `hasPermission(id, type, permission)`. Không thêm `authentication` vào lời gọi SpEL rồi làm sai số đối số.

Overload nhận object chỉ **nhận object hiện có**, không tự lấy dữ liệu từ database. Nếu muốn truy vấn ACL hay đối chiếu owner/tenant, chính implementation của evaluator phải làm việc đó.

Overload nhận ID được dùng khi chỉ có khóa của tài nguyên. `targetType` là một mã tên loại đối tượng nhất quán với cách tìm quyền (thường là class name, nhưng ứng dụng có thể quy ước khác). Không mặc định overload ID sẽ gọi overload object hoặc ngược lại. Trong ví dụ, overload ID **cố ý trả false** vì bài chỉ triển khai chính sách với domain object đã tải; đây là lựa chọn an toàn thay vì cấp quyền ngầm.

### Quyền `permission` là kiểu `Object`

SpEL truyền giá trị `'READ'` dưới dạng String. Nhưng tham số `permission` trong `PermissionEvaluator` có kiểu Object vì framework cho phép các hình thức biểu diễn quyền khác, ví dụ đối tượng ACL permission hoặc enum. Khi tự thiết kế, hãy kiểm tra loại và giá trị, từ chối action lạ. Không chuyển mọi thứ bằng `toString()` rồi vô tình nhận một đối tượng không được phép.

Trong ví dụ này, hai chuỗi `'READ'` và `'EDIT'` là hợp đồng tường minh; mọi giá trị khác trả false.

## 3. Từ annotation đến quyết định quyền

~~~text
Caller gọi bean có Spring AOP proxy
              |
              v
@PreAuthorize / @PostAuthorize / @PostFilter
              |
              v
MethodSecurityExpressionHandler
              |
              v
SpEL: hasPermission(domainObject, 'READ')
              |
              v
PermissionEvaluator.hasPermission(
    authentication, domainObject, "READ"
)
              |
          +---+---+
          |       |
        true    false
          |       |
       Cho qua  Từ chối
~~~

`@EnableMethodSecurity` đăng ký các interceptor để áp dụng annotation ở phương thức Spring bean. Chỉ có dependency `spring-boot-starter-security` **chưa tự kích hoạt Method Security**. Caller phải gọi qua proxy; `new MyService(...)` hoặc `this.someMethod()` tự gọi trong target có thể bỏ qua interceptor.

Đối với `hasPermission`, việc đặt `@Component` lên một evaluator chỉ tạo bean Java. **Phải đưa evaluator vào `DefaultMethodSecurityExpressionHandler`** để expression root biết nó được dùng cho quyết định object permission. Spring Security documentation minh họa việc này khi nối `AclPermissionEvaluator` vào Method Security.

## 4. Chọn lúc kiểm tra: pre, post hay từng phần tử

### 4.1. `@PreAuthorize` khi object đã được truyền vào

~~~java
@PreAuthorize("hasPermission(#doc, 'EDIT')")
public String prepare(@P("doc") Document doc) {
    return "ready:" + doc.id();
}
~~~

Spring lấy `#doc` từ tham số và đánh giá expression **trước** khi thân method chạy. Nếu người gọi không đủ quyền, method không được thực thi. Đây là lựa chọn phù hợp cho hành động có tác dụng phụ, **nếu đối tượng đầu vào là dữ liệu đã xác minh hoặc evaluator tự xác minh lại**.

Rủi ro: một DTO hoặc record tạo từ JSON request có thể mang `owner = "alice"` tùy ý. Nếu evaluator chỉ kiểm tra `doc.owner().equals(authentication.getName())`, caller có thể tự làm giả owner. Bài này sẽ xác minh snapshot với kho tin cậy trước khi xét chính sách.

### 4.2. `@PostAuthorize` khi method vừa tải object

~~~java
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
public Document read(long id) {
    return store.findById(id).orElse(null);
}
~~~

`returnObject` là giá trị target method trả về. Expression được chạy **sau** khi target đọc dữ liệu nhưng **trước** khi proxy trả giá trị ra bên ngoài. Nếu quyền bị từ chối, thường xuất hiện `AccessDeniedException`. Không có tác vụ ghi nên trường hợp đọc này phù hợp với hậu kiểm.

Không dùng hậu kiểm làm biện pháp duy nhất cho phương thức **xóa, sửa, tạo giao dịch tiền, gửi thông báo**: lúc evaluator kiểm tra thì những tác dụng phụ đã có thể xảy ra. Ngoài ra, đừng ghi log dữ liệu nhạy cảm trong thân method trước khi hậu kiểm quyền.

### 4.3. `@PostFilter` với tập object đã tải

~~~java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> listVisible() {
    return new ArrayList<>(store.findAll());
}
~~~

`filterObject` biểu thị từng phần tử. Evaluator được gọi riêng cho từng đối tượng để giữ phần tử được phép. Tạo `ArrayList` mới vì một số đường xử lý lọc cần thay đổi collection. Không trả trực tiếp list cache dùng chung rồi để filter chỉnh sửa nó.

Với truy vấn lớn và phân trang, cần đưa điều kiện quyền vào truy vấn database. Tải toàn bộ dữ liệu rồi mới lọc có thể chậm, làm sai số phần tử trang và tốn bộ nhớ.

### 4.4. Bảng quyết định nhanh

| Dữ liệu có sẵn lúc nào? | Cách kiểm tra | Hệ quả |
| --- | --- | --- |
| Trước thân method, object từ nguồn tin cậy | `@PreAuthorize("hasPermission(#doc,'EDIT')")` | Chặn hành động sớm |
| Sau khi thân method tải xong | `@PostAuthorize("hasPermission(returnObject,'READ')")` | Tốt cho thao tác đọc |
| Danh sách đã được tạo | `@PostFilter("hasPermission(filterObject,'READ')")` | Lọc từng phần tử; phù hợp tập nhỏ |
| Chỉ biết ID, không có object | Overload ID hoặc tự load/check tại service/repository | Không giả làm object đã tải |
| Có ghi dữ liệu nhạy cảm | Tiền kiểm + transaction/update có điều kiện | Chặn quyền và ràng buộc trạng thái lúc ghi |

## 5. Ví dụ hoàn chỉnh trên Spring Boot 3.x / Java 17+

Các file sử dụng package `demo.permissionobject`. Dự án Gradle đã có plugin Spring Boot/Java và quản lý phiên bản dependency của Spring Boot. Để học cơ chế Method Security, ví dụ chỉ dùng service và kho in-memory, không cần tạo HTTP endpoint.

### 5.1. Dependencies

Trong `build.gradle` hiện có:

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

Không trộn trực tiếp phiên bản Spring Security 7 với Spring Boot 3 trong bài mẫu. Dùng bộ phiên bản do dependency management của Boot chọn.

### 5.2. Ứng dụng

**`src/main/java/demo/permissionobject/PermissionObjectApplication.java`**

~~~java
package demo.permissionobject;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermissionObjectApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionObjectApplication.class, args);
    }
}
~~~

### 5.3. Domain object đã tải

**`src/main/java/demo/permissionobject/Document.java`**

~~~java
package demo.permissionobject;

public record Document(
        long id,
        String owner,
        String title,
        boolean shared,
        boolean locked) {
}
~~~

`record` có `equals/hashCode` dựa trên tất cả các thành phần. Đây là một **snapshot bất biến** minh họa cho bài; hệ thống thật có thể dùng JPA entity, projection hoặc DTO được xây từ dữ liệu tin cậy. Không dùng bản sao từ client làm nguồn sự thật.

### 5.4. Kho giả lập

**`src/main/java/demo/permissionobject/DocumentStore.java`**

~~~java
package demo.permissionobject;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {
    private final Map<Long, Document> documents = Map.of(
        101L, new Document(101L, "alice", "Draft A", false, false),
        202L, new Document(202L, "bob", "Private B", false, false),
        303L, new Document(303L, "alice", "Shared Guide", true, false),
        404L, new Document(404L, "alice", "Locked Draft", false, true)
    );

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public List<Document> findAll() {
        return documents.values().stream()
                .sorted(Comparator.comparingLong(Document::id))
                .toList();
    }
}
~~~

`findAll()` sắp xếp theo ID để test không phụ thuộc thứ tự của `Map`. `toList()` tạo danh sách không cho sửa cấu trúc; service sẽ sao chép sang `ArrayList` trước khi `@PostFilter` xử lý.

### 5.5. Evaluator chỉ cấp quyền cho bản object đã được xác minh

**`src/main/java/demo/permissionobject/DocumentPermissionEvaluator.java`**

~~~java
package demo.permissionobject;

import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {
    private final DocumentStore store;

    public DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!isRealUser(authentication)) {
            return false;
        }
        if (!(targetDomainObject instanceof Document supplied)) {
            return false;
        }
        if (!(permission instanceof String action)) {
            return false;
        }

        // Xác minh ID và snapshot theo nguồn tin cậy.
        // Không tin owner/shared/locked do caller tự gửi.
        return store.findById(supplied.id())
                .filter(stored -> stored.equals(supplied))
                .map(stored -> canPerform(authentication, stored, action))
                .orElse(false);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {
        // Chưa triển khai dạng ID trong bài này -> mặc định từ chối.
        return false;
    }

    private boolean canPerform(
            Authentication authentication,
            Document document,
            String action) {
        boolean owner = document.owner().equals(authentication.getName());

        return switch (action) {
            case "READ" -> owner
                    || (document.shared()
                        && hasAuthority(authentication, "DOC_SHARED_READ"));
            case "EDIT" -> owner
                    && !document.locked()
                    && hasAuthority(authentication, "DOC_EDIT");
            default -> false;
        };
    }

    private boolean hasAuthority(Authentication authentication, String name) {
        return authentication.getAuthorities().stream()
                .anyMatch(a -> name.equals(a.getAuthority()));
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

**Giải thích luồng đánh giá:**

1. Nếu người dùng không xác thực hoặc là anonymous token, false.
2. Nếu đối tượng không phải `Document` (bao gồm `null`), false.
3. Nếu permission không phải String, false.
4. Xác minh đối tượng theo `id` với bản record từ `DocumentStore`. Nếu không tồn tại hoặc snapshot khác, false.
5. Tính chính sách READ/EDIT dựa trên **bản được lưu**, không dựa vào trường do caller tự điền.
6. Permission chưa hỗ trợ đi vào `default -> false`.

Đọc lại store ở bước 4 giúp bài mẫu không tin một object giả. Nó cũng tạo truy vấn bổ sung; ở JPA/SQL thực, có thể tối ưu bằng truy vấn projection chủ sở hữu/tenant, kiểm tra row version, hoặc tổ chức transaction để không dùng snapshot cũ. Đừng bỏ việc xác minh nguồn dữ liệu khi API nhận DTO không tin cậy.

### 5.6. Đăng ký expression handler

**`src/main/java/demo/permissionobject/MethodSecurityConfig.java`**

~~~java
package demo.permissionobject;

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

`@Bean static` là cách Spring Security reference sử dụng để cung cấp expression handler đủ sớm cho cấu hình Method Security. Handler được tiêm đúng `PermissionEvaluator` qua tham số bean factory method rồi gọi `setPermissionEvaluator(...)`.

Nếu project đã có expression handler riêng để điều chỉnh role hierarchy, expression root hoặc ACL, **tích hợp vào cấu hình hiện có** thay vì tạo nhiều bean handler không rõ bean nào đang hoạt động. Nếu có nhiều `PermissionEvaluator`, dùng `@Qualifier` để chọn chính xác.

### 5.7. Service dùng `returnObject` và `filterObject`

**`src/main/java/demo/permissionobject/DocumentQueryService.java`**

~~~java
package demo.permissionobject;

import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {
    private final DocumentStore store;

    public DocumentQueryService(DocumentStore store) {
        this.store = store;
    }

    @PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
    public Document read(long id) {
        return store.findById(id).orElse(null);
    }

    @PostFilter("hasPermission(filterObject, 'READ')")
    public List<Document> listVisible() {
        return new ArrayList<>(store.findAll());
    }
}
~~~

Ở `read`, object được **tải trước** rồi chuyển cho evaluator thông qua `returnObject`. Nếu trả null hoặc policy false, kết quả bị chặn qua proxy. Ở `listVisible`, evaluator được gọi cho từng phần tử của tập nhỏ in-memory.

Ví dụ chọn trả null ở `read` để giải thích xử lý `returnObject != null`. Trong ứng dụng thật, muốn phân biệt 404 cho tài liệu không tồn tại và 403 cho tài liệu không được phép phải định nghĩa hợp đồng HTTP và tránh lộ sự tồn tại tài nguyên theo yêu cầu nghiệp vụ.

### 5.8. Service dùng `#doc` ở tham số đã tải

**`src/main/java/demo/permissionobject/DocumentActionService.java`**

~~~java
package demo.permissionobject;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentActionService {

    @PreAuthorize("hasPermission(#doc, 'EDIT')")
    public String prepareEdit(@P("doc") Document doc) {
        return "edit:" + doc.id();
    }
}
~~~

`@P("doc")` làm rõ tên tham số SpEL, tránh phụ thuộc hoàn toàn vào cờ compiler `-parameters`. Method chỉ tạo một chuỗi preview, không có tác dụng phụ. Quy tắc `EDIT` được đánh giá trước thân method, và evaluator sẽ xác minh record theo repository nên không cấp quyền dựa vào một DTO bị thay owner.

Không xem `prepareEdit` là một lệnh cập nhật database. Nếu triển khai ghi thật, phải thêm ràng buộc owner/tenant/locked/version trong transaction và câu lệnh cập nhật; một chốt đầu lời gọi không thể tự ngăn race giữa thời điểm kiểm tra và ghi.

## 6. Test tích hợp qua Spring proxy

Test dưới đây được Spring tạo application context và inject service thật, khác hoàn toàn với việc gọi `new SomeService(...)`. `@WithMockUser` cung cấp `Authentication` cho từng test.

**`src/test/java/demo/permissionobject/DocumentMethodSecurityTest.java`**

~~~java
package demo.permissionobject;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = PermissionObjectApplication.class)
class DocumentMethodSecurityTest {
    @Autowired
    private DocumentQueryService query;

    @Autowired
    private DocumentActionService actions;

    @Autowired
    private DocumentStore store;

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadLoadedDocument() {
        assertEquals(101L, query.read(101L).id());
        assertEquals(303L, query.read(303L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void anotherOwnerCannotReadPrivateDocument() {
        assertThrows(AccessDeniedException.class, () -> query.read(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_SHARED_READ")
    void sharedReaderCanReadSharedDocument() {
        assertEquals(303L, query.read(303L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void sharedDocumentStillRequiresAuthority() {
        assertThrows(AccessDeniedException.class, () -> query.read(303L));
    }

    @Test
    @WithMockUser(username = "alice")
    void absentDocumentIsDenied() {
        assertThrows(AccessDeniedException.class, () -> query.read(999L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserIsDenied() {
        assertThrows(AccessDeniedException.class, () -> query.read(101L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_EDIT")
    void ownerCanPrepareEditWhenUnlocked() {
        Document trusted = store.findById(101L).orElseThrow();
        assertEquals("edit:101", actions.prepareEdit(trusted));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerWithoutEditAuthorityIsDenied() {
        Document trusted = store.findById(101L).orElseThrow();
        assertThrows(AccessDeniedException.class, () -> actions.prepareEdit(trusted));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_EDIT")
    void lockedDocumentCannotBeEdited() {
        Document locked = store.findById(404L).orElseThrow();
        assertThrows(AccessDeniedException.class, () -> actions.prepareEdit(locked));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_EDIT")
    void forgedOwnerDoesNotGrantPermission() {
        Document forged = new Document(101L, "bob", "Draft A", false, false);
        assertThrows(AccessDeniedException.class, () -> actions.prepareEdit(forged));
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilterReturnsOnlyAllowedObjects() {
        List<Long> ids = query.listVisible().stream().map(Document::id).toList();
        assertEquals(List.of(101L, 303L, 404L), ids);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_SHARED_READ")
    void postFilterIncludesOwnedAndShared() {
        List<Long> ids = query.listVisible().stream().map(Document::id).toList();
        assertEquals(List.of(202L, 303L), ids);
    }
}
~~~

**Điều test chứng minh:**

- `@PostAuthorize` đánh giá object đã tải và chặn việc trả dữ liệu của người khác.
- `@PreAuthorize` bảo vệ hành động cần EDIT ngay khi nhận object, đồng thời evaluator đối chiếu trạng thái chuẩn.
- `@PostFilter` gọi evaluator theo từng domain object.
- Người anonymous, ID không tồn tại, authority không phù hợp, object có owner bị sửa và tài liệu khóa đều bị từ chối.

Nếu code test dùng `new DocumentQueryService(store)`, annotation có thể không được Spring proxy xử lý; đó là lý do test method security phải kiểm tra qua bean được inject.

## 7. Test đơn vị evaluator và cả overload ID

**`src/test/java/demo/permissionobject/DocumentPermissionEvaluatorTest.java`**

~~~java
package demo.permissionobject;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPermissionEvaluatorTest {
    private final DocumentStore store = new DocumentStore();
    private final DocumentPermissionEvaluator evaluator =
            new DocumentPermissionEvaluator(store);

    private Authentication auth(String user, String... authorities) {
        List<SimpleGrantedAuthority> granted = java.util.Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toList();

        return new UsernamePasswordAuthenticationToken(user, "unused", granted);
    }

    @Test
    void knownPermissionOnLoadedObject() {
        Document doc = store.findById(101L).orElseThrow();
        assertTrue(evaluator.hasPermission(auth("alice"), doc, "READ"));
        assertFalse(evaluator.hasPermission(auth("bob"), doc, "READ"));
    }

    @Test
    void editRequiresAllConditions() {
        Document draft = store.findById(101L).orElseThrow();
        Document locked = store.findById(404L).orElseThrow();

        assertTrue(evaluator.hasPermission(auth("alice", "DOC_EDIT"), draft, "EDIT"));
        assertFalse(evaluator.hasPermission(auth("alice"), draft, "EDIT"));
        assertFalse(evaluator.hasPermission(auth("bob", "DOC_EDIT"), draft, "EDIT"));
        assertFalse(evaluator.hasPermission(auth("alice", "DOC_EDIT"), locked, "EDIT"));
    }

    @Test
    void unknownActionWrongTypeAndNullFailClosed() {
        Authentication alice = auth("alice", "DOC_EDIT");
        Document doc = store.findById(101L).orElseThrow();

        assertFalse(evaluator.hasPermission(alice, doc, "DELETE"));
        assertFalse(evaluator.hasPermission(alice, doc, Integer.valueOf(7)));
        assertFalse(evaluator.hasPermission(alice, "not-document", "READ"));
        assertFalse(evaluator.hasPermission(alice, null, "READ"));
        assertFalse(evaluator.hasPermission(null, doc, "READ"));
    }

    @Test
    void objectWithFakeOwnerIsRejected() {
        Document fake = new Document(101L, "bob", "Draft A", false, false);
        assertFalse(evaluator.hasPermission(auth("bob"), fake, "READ"));
    }

    @Test
    void idOverloadIsDeliberatelyDenied() {
        assertFalse(evaluator.hasPermission(
                auth("alice"), 101L, "Document", "READ"));
    }
}
~~~

Constructor ba tham số `UsernamePasswordAuthenticationToken(user, credentials, authorities)` tạo đối tượng authentication đã xác thực để thử **logic Java**. Unit test không biết Spring đã đăng ký expression handler hay chưa; phải giữ test tích hợp ở mục 6.

### Chạy từ dự án Gradle

Trên macOS/Linux:

~~~text
./gradlew test --tests demo.permissionobject.DocumentPermissionEvaluatorTest --tests demo.permissionobject.DocumentMethodSecurityTest
~~~

Trên Windows:

~~~text
gradlew.bat test --tests demo.permissionobject.DocumentPermissionEvaluatorTest --tests demo.permissionobject.DocumentMethodSecurityTest
~~~

Các ví dụ không in `System.out.println` nên không có stdout nghiệp vụ cố định. Khi dependencies/cấu hình đúng và mọi assertion đạt, Gradle hoàn thành `test` thành công. Đây là mã ví dụ cần người học chạy trong dự án tương thích; không coi việc chỉ đọc source là đã thực thi tests.

## 8. Đọc từng đường đi để hiểu đúng thời điểm

### 8.1. `alice` đọc tài liệu 101 qua `@PostAuthorize`

~~~text
1. Caller gọi query.read(101) qua proxy.
2. Thân method tải Document(101, owner=alice, ...) từ store.
3. @PostAuthorize thấy returnObject.
4. SpEL gọi hasPermission(returnObject, 'READ').
5. Evaluator xác minh snapshot 101 với store.
6. owner=alice => true.
7. Proxy trả Document cho caller.
~~~

### 8.2. `bob` đọc tài liệu 101

~~~text
1. Thân method vẫn tải Document 101.
2. @PostAuthorize nhận returnObject.
3. Evaluator xác minh snapshot nhưng owner != bob, shared=false.
4. Trả false.
5. Proxy ném AccessDeniedException, không trả Document.
~~~

Chính vì đã tải trước bước 3, hậu kiểm **không ngăn được công việc nội bộ** hay tác dụng phụ. Chỉ sử dụng cách này khi phương thức đọc an toàn hoặc đã thiết kế cơ chế kiểm tra bổ sung.

### 8.3. `bob` chuyển một đối tượng giả vào `@PreAuthorize`

~~~text
1. Caller tạo Document(id=101, owner=bob, ...).
2. Gọi actions.prepareEdit(fake) qua proxy.
3. @PreAuthorize gọi hasPermission(#doc, 'EDIT').
4. Evaluator tải bản chuẩn của ID 101 -> owner=alice.
5. Snapshot giả không bằng bản chuẩn -> false.
6. prepareEdit không chạy.
~~~

Nếu evaluator chỉ nhìn trường `owner` trên object caller gửi, dữ liệu giả có thể làm phép kiểm tra sai. Mục tiêu của `PermissionEvaluator` không phải “tin mọi object đã có”, mà là **đưa logic quyền cho object vào một nơi có thể dùng dữ liệu đáng tin cậy**.

## 9. Các giới hạn cần hiểu trước khi triển khai thật

### 9.1. Đối tượng null

Javadoc `PermissionEvaluator` cho phép `targetDomainObject` là null và khuyến nghị trả false. Ví dụ dùng `instanceof` nên null trở thành false. Biểu thức `returnObject != null and hasPermission(...)` giúp người đọc biết ý định chặn null, tránh ngoại lệ do dereference.

### 9.2. Không hiểu nhầm authority/role

`hasRole('ADMIN')` thường tìm authority `ROLE_ADMIN` theo prefix mặc định; `hasAuthority('DOC_EDIT')` tìm chính xác `DOC_EDIT`. Trong ví dụ evaluator so sánh authority trực tiếp, không thêm role prefix. Nếu hệ thống có quyền quản trị xuyên tenant hoặc override theo vai trò, phải diễn đạt thành chính sách cụ thể và test nhánh ưu tiên/ngoại lệ.

### 9.3. Nguồn gốc object và ranh giới tin cậy

Một domain object do repository tải bên trong method khác với một record do client xây từ JSON. Với object do caller cung cấp, nguy cơ là **insecure direct object reference (IDOR)** hoặc giả mạo owner, tenant, trạng thái. Cách xác minh có thể là truy vấn state từ database theo ID và actor/tenant, so sánh immutable version, hoặc chỉ truyền một reference đã được tạo qua use case đáng tin; chọn cách phù hợp với thiết kế thật.

### 9.4. Nhiều tenant

Nếu tài liệu có `tenantId`, hãy kiểm tra same-tenant từ claims/principal đã được xác thực **trước khi** áp dụng ngoại lệ owner/shared. Không dùng `tenantId` từ query parameter/header do người dùng tự gửi làm bằng chứng. Khi thêm quyền ADMIN, xác định rõ admin có thể vượt tenant hay chỉ quản trị trong tenant của họ; một điều kiện `admin || sameTenant` viết thiếu ngoặc có thể vô tình mở quyền quá rộng.

### 9.5. Truy vấn lặp, lazy JPA và transaction

Evaluator có thể được gọi hàng loạt trong `@PostFilter`. Nếu mỗi phần tử lại truy vấn database, số query có thể tăng nhanh. Với JPA, truy cập lazy relation ở thời điểm hậu kiểm đôi khi ngoài transaction tùy advisor order. Ưu tiên truy vấn có điều kiện ở database, projection tối thiểu, batch lookup hoặc policy service dùng transaction đọc phù hợp. Đo query count và thời gian thực; tránh “cache allow” chỉ theo ID mà quên actor, tenant, action và phiên bản chính sách.

### 9.6. Khoảng cách kiểm tra – sử dụng (TOCTOU)

Trình tự rủi ro:

~~~text
T1: Evaluator thấy document 101 thuộc alice, locked=false -> allow.
T2: Một giao dịch khác chuyển owner hoặc locked=true.
T3: Service ghi tài liệu theo kết quả kiểm tra cũ.
~~~

Đây là `time-of-check/time-of-use` (TOCTOU): trạng thái có thể thay đổi giữa lúc kiểm tra và lúc sử dụng. Với lệnh cập nhật nhạy cảm, kết hợp tiền kiểm và điều kiện owner/tenant/locked/version tại database, transaction/optimistic locking hoặc khóa thích hợp. Đừng dùng `@PostAuthorize` để bảo vệ hành động đã commit.

Ví dụ ý tưởng SQL:

~~~sql
UPDATE documents
SET title = :new_title
WHERE id = :id
  AND owner_id = :authenticated_user_id
  AND tenant_id = :trusted_tenant_id
  AND locked = FALSE;
~~~

Kiểm tra số hàng bị thay đổi để biết cập nhật có thực hiện không; các tham số phải được bind an toàn và danh tính lấy từ authentication đáng tin.

### 9.7. ACL chính thức và custom evaluator

`PermissionEvaluator` là hợp đồng chung. Khi ứng dụng cần chia sẻ từng bản ghi, danh sách kiểm soát truy cập, quyền theo user/group, có thể dùng `AclPermissionEvaluator` trong module ACL của Spring Security. Khi chính sách đơn giản hơn và dựa vào owner/state/tenant, một evaluator tự viết như ví dụ có thể phù hợp. `BasePermission.READ` của ACL và String `'READ'` của mẫu này không mặc nhiên tương đương; phải cấu hình mapping theo implementation.

### 9.8. Proxy và lời gọi nội bộ

`@PreAuthorize`/`@PostAuthorize` chạy khi lời gọi đi qua Spring AOP proxy. Nếu một method trong cùng bean gọi `this.read(...)`, annotation riêng của `read` có thể không được áp dụng. Đặt điểm chặn ở public service boundary, gọi qua bean được inject từ Spring Context, và dùng integration tests với người có/không có quyền để chứng minh chốt hoạt động.

## 10. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `hasPermission` luôn false | Handler chưa được gắn custom evaluator | Cấu hình `MethodSecurityExpressionHandler` và `setPermissionEvaluator` |
| Unit evaluator pass nhưng service không chặn | Thiếu `@EnableMethodSecurity` hoặc lời gọi bỏ proxy | Integration test qua bean Spring và user thiếu quyền |
| `#doc` bị null | Sai tên biến hoặc thiếu metadata tham số | `@P("doc")`, hoặc bật `-parameters` đúng |
| `returnObject` là null | Object không tồn tại hoặc method trả null | Kiểm tra null và thiết kế 403/404 phù hợp |
| Người khác tự đổi owner rồi được phép | Tin trực tiếp object/DTO do client gửi | Xác minh bản lưu chuẩn và tenant từ nguồn tin cậy |
| Overload ID không hoạt động | Chỉ implement overload object | Cài riêng `hasPermission(Authentication, Serializable, String, Object)` |
| Permission lạ vẫn được phép | Default permissive hoặc ép kiểu tùy tiện | Kiểm tra exact permission, `default -> false` |
| Hậu kiểm chặn sau khi dữ liệu đã thay đổi | Dùng `@PostAuthorize` cho hành động có side effect | Tiền kiểm và điều kiện transaction/database |
| `@PostFilter` lọc rất chậm | Mỗi object gọi lại repository | Truy vấn có điều kiện, batch, đo query count |
| Test cho qua owner thiếu authority EDIT | Chỉ kiểm tra ownership mà quên authority | Tách rõ READ và EDIT, viết negative tests |
| Owner không sửa được bản ghi khóa | Chính sách `locked` chặn đúng như thiết kế | Sửa yêu cầu nếu cần hành động unlock riêng |
| JPA lazy loading lỗi | Evaluator chạy ngoài ranh giới transaction | Thiết kế truy vấn policy/transaction rõ ràng |
| Đổi version khiến quyền khác | Khác proxy/advisor cấu hình hoặc permission mapping | Chạy regression tests qua Spring Context |

## 11. Bài tập thực hành

**Bài 1 – Thêm DELETE.** Quyền `DELETE` yêu cầu owner, authority `DOC_DELETE`, tài liệu chưa khóa và chưa chia sẻ. Thêm test khi thiếu từng điều kiện, bảo đảm một nhánh bất kỳ sai đều từ chối.

**Bài 2 – Object giả.** Tạo `Document(101,"bob",...)` khi trong store ID 101 vẫn thuộc alice. Viết test cho caller bob, chứng minh evaluator không tin trường owner được sửa. So sánh với implementation nguy hiểm chỉ kiểm tra thuộc tính object do caller đưa.

**Bài 3 – ID overload.** Cài `hasPermission(#id,'Document','READ')` với kiểm tra targetType, ID và repository lookup; so sánh kết quả với overload object, kể cả ID không tồn tại.

**Bài 4 – Tenant.** Thêm `tenantId` vào Document và principal đáng tin. Tạo hai tài liệu ở tenant khác nhau có owner cùng username; test không đọc chéo tenant.

**Bài 5 – Thao tác cập nhật.** Tạo service ghi dữ liệu với `@PreAuthorize` và update có điều kiện owner/tenant/locked/version. Test trường hợp trạng thái đổi sau khi kiểm tra quyền, bảo đảm không cập nhật sai.

**Bài 6 – Phân trang.** Thay `@PostFilter` bằng repository query chỉ đọc các document có quyền cho principal; so sánh số query, tổng bản ghi và hiệu năng trên tập dữ liệu lớn.

**Tiêu chí hoàn thành:** nhận biết đúng overload nhận domain object; giải thích `#doc`, `returnObject`, `filterObject`; đăng ký evaluator vào expression handler; có test cho phép/từ chối qua Spring proxy; không tin owner của object do client gửi; dùng transaction/query để kiểm soát trạng thái thực khi ghi dữ liệu.

## Tài liệu tham khảo

- Spring Security – **Method Security**, `@PreAuthorize`, `@PostAuthorize`, `@PostFilter` và `hasPermission`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Domain Object Security (ACLs)**, ví dụ cấu hình `PermissionEvaluator` và expression handler: https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security – **PermissionEvaluator API**, hai overload và trường hợp object null: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html
- Spring Security – **Testing Method Security**, `@WithMockUser` và `@WithAnonymousUser`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
