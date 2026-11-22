# `hasPermission`: phân quyền theo đối tượng trực tiếp hoặc định danh đối tượng

## 1. Bài toán và mục tiêu

Trong Spring Security, `hasRole('EDITOR')` hoặc `hasAuthority('document:write')` kiểm tra quyền tổng quát của người gọi. Nhưng một người có quyền chỉnh sửa tài liệu **không đồng nghĩa** được chỉnh sửa **mọi** tài liệu. Ví dụ:

- `alice` được đọc và sửa tài liệu `#1` do cô ấy sở hữu.
- `bob` được đọc và sửa tài liệu `#2` do anh ấy sở hữu.
- Cả hai đều có vai trò `USER`; chỉ kiểm tra `hasRole('USER')` sẽ không phân biệt được tài liệu `#1` với `#2`.

`hasPermission(...)` là hàm trong biểu thức bảo mật Spring Security để hỏi một `PermissionEvaluator`: **người đang được xác thực có quyền cụ thể trên đối tượng cụ thể này không?**

Sau bài này, bạn có thể:
1. Phân biệt hai dạng `hasPermission(targetObject, permission)` và `hasPermission(targetId, targetType, permission)`.
2. Hiểu việc truyền `Authentication`, đối tượng/ID, loại tài nguyên và quyền vào `PermissionEvaluator`.
3. Tích hợp một `PermissionEvaluator` tùy chỉnh với `@EnableMethodSecurity` và `@PreAuthorize`.
4. Kiểm thử phân quyền theo quyền sở hữu, trường hợp từ chối và đầu vào giả mạo.
5. Nhận biết giới hạn của kiểm tra trước khi gọi, kiểm tra sau khi gọi, ACL và tác động hiệu năng.

**Phạm vi:** phân quyền cấp đối tượng trong Spring Security Method Security. Bài tập trung vào hai chữ ký `hasPermission`; quản trị ACL và thiết kế hệ thống phân quyền toàn diện là hướng mở rộng.

## 2. Hai cách gọi `hasPermission`

### 2.1. Đã có đối tượng: `hasPermission(targetObject, permission)`

```java
@PreAuthorize("hasPermission(#document, 'read')")
public String readTitle(@P("document") Document document) {
    // Chỉ chạy khi PermissionEvaluator cho phép đọc đối tượng.
    return document.title();
}
```

Biểu thức trên truyền **đối tượng `document`** và quyền `'read'`. Spring Security lấy `Authentication` của người gọi từ security context rồi ủy quyền quyết định cho:

```java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);
```

Dạng này phù hợp khi phương thức đã nhận một domain object **đáng tin cậy** được tải từ phía server, hoặc khi `PermissionEvaluator` có thể dùng ID trong object để đối chiếu với dữ liệu đáng tin cậy.

**Cảnh báo quan trọng:** nếu object là JSON/DTO do client tự tạo, trường như `owner` có thể bị làm giả. Việc viết `document.owner().equals(authentication.getName())` dựa trên DTO từ client không chứng minh người đó sở hữu bản ghi trong database. Ví dụ đầy đủ bên dưới luôn tra chủ sở hữu trong kho dữ liệu của server.

### 2.2. Chỉ có định danh: `hasPermission(targetId, targetType, permission)`

```java
@PreAuthorize("hasPermission(#id, 'Document', 'write')")
public void rename(@P("id") Long id, String title) {
    // Chỉ chạy sau khi người gọi có quyền write trên Document/id.
}
```

Biểu thức trên dùng **ba đối số**, tương ứng chữ ký evaluator:

```java
boolean hasPermission(
    Authentication authentication,
    java.io.Serializable targetId,
    String targetType,
    Object permission
);
```

Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `#id` | ID của bản ghi, phải tương thích với `Serializable` | `1L` |
| `'Document'` | Tên loại tài nguyên mà evaluator hiểu | `Document` |
| `'write'` | Quyền cần kiểm tra | `write` |
| `Authentication` | Người đang đăng nhập, Spring tự cung cấp cho evaluator | `alice` |

`targetType` là **chuỗi**, không phải một đối tượng Java `Class` được Spring tự ánh xạ. Với evaluator tùy chỉnh, bạn có thể dùng bí danh ổn định `'Document'`; nếu dùng framework ACL, quy ước định danh loại đối tượng phải nhất quán với cấu hình ACL (thường dùng tên lớp). Chỉ vì client cung cấp ID `1` không có nghĩa ID đó thuộc loại tài nguyên hoặc quyền đã khai báo.

### 2.3. Chọn dạng nào?

| Tiêu chí | Có đối tượng | Chỉ có ID |
| --- | --- | --- |
| Cú pháp | `hasPermission(#document, 'read')` | `hasPermission(#id, 'Document', 'read')` |
| Chữ ký Java | `(Authentication, Object, Object)` | `(Authentication, Serializable, String, Object)` |
| Đối tượng đầu vào | Domain object/DTO | ID và loại tài nguyên |
| Tình huống điển hình | Service đã nhận entity từ tầng server | Controller/service nhận ID từ URL hoặc command |
| Yêu cầu bảo mật | Xác minh nguồn tin cậy của object | Tra cứu quyền thật dựa trên ID và loại |
| Chi phí có thể phát sinh | Kiểm tra ACL hoặc truy vấn theo object/ID | Có thể phải tải bản ghi/ACL từ kho dữ liệu |

Cả hai dạng đều hỏi **cùng một chính sách quyền**, nhưng qua hai chữ ký khác nhau. Nên thống nhất logic quyết định ở phía sau thay vì để hai dạng trả kết quả trái nhau cho cùng một bản ghi.

## 3. Luồng xử lý và các thành phần

```text
Caller (HTTP controller / service / test)
                |
                v
        Spring-managed proxy
                |
                v
  @PreAuthorize("hasPermission(...)")
                |
                v
 Spring Method Security expression
  - đọc Authentication hiện tại
  - lấy #document hoặc #id
  - phân giải quyền 'read'/'write'
                |
                v
        PermissionEvaluator
      /                    \
 (object, permission)   (id, type, permission)
      \                    /
       v                  v
     ACL / DB / policy service đáng tin cậy
                |
          true / false
                |
        +-------+--------+
        |                |
      true             false
        |                |
  vào thân method    từ chối lời gọi
                     AccessDeniedException
```

Với `@PreAuthorize`, quyết định xảy ra **trước khi thân phương thức được gọi**. Nếu biểu thức là `false`, interceptor từ chối lời gọi; method đích không chạy. Trong ứng dụng web, cơ chế xử lý lỗi bảo mật có thể chuyển kết quả này thành HTTP 403 hoặc phản hồi khác tùy trạng thái xác thực và cấu hình.

`hasPermission` không phải một annotation riêng hay câu truy vấn SQL có sẵn. Spring Security cung cấp **cơ chế gọi evaluator**; ứng dụng phải định nghĩa chính sách quyền thực tế hoặc tích hợp một evaluator có sẵn (như `AclPermissionEvaluator`).

> Quy tắc đơn giản: **role/authority** thường nói người dùng có loại năng lực gì; **permission trên đối tượng** trả lời người đó được thực hiện hành động nào trên tài nguyên cụ thể.

## 4. Cấu hình Method Security và `PermissionEvaluator`

Bật method security bằng `@EnableMethodSecurity`. Để `hasPermission` hoạt động theo quy tắc của ứng dụng, đăng ký `PermissionEvaluator` vào `DefaultMethodSecurityExpressionHandler`:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
```

Các import tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Dùng `static @Bean` cho expression handler theo hướng dẫn Spring Security để bean này sẵn sàng sớm khi cấu hình method security khởi tạo. `PermissionEvaluator` có thể là `@Component` hoặc `@Bean` được quản lý bởi Spring.

Nếu không cấu hình evaluator cấp quyền phù hợp, `hasPermission` **không tự biết** dữ liệu sở hữu hoặc ACL của hệ thống; implementation mặc định `DenyAllPermissionEvaluator` từ chối kiểm tra quyền. Đừng giả định chỉ cần thêm biểu thức là các bản ghi sẽ được tự động bảo vệ.

`@EnableMethodSecurity` hoạt động qua Spring AOP trong cấu hình proxy thông thường; cần gọi phương thức từ **Spring bean/proxy**, không gọi `new Service()` hay tự gọi `this.securedMethod(...)` trong cùng bean rồi tưởng annotation luôn được áp dụng.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai dạng trên cùng một chính sách

Ví dụ là ứng dụng Spring Boot chạy qua dòng lệnh, không cần HTTP server hoặc database. `DocumentStore` mô phỏng dữ liệu server:

- ID `1` có chủ sở hữu `alice`.
- ID `2` có chủ sở hữu `bob`.
- `DocumentPermissionEvaluator` kiểm tra quyền `read`/`write` trên **dữ liệu lưu tại server**, không tin thuộc tính owner người gọi gửi vào.
- `DocumentService.readTitle(document)` dùng dạng **object**.
- `DocumentService.rename(id, title)` dùng dạng **ID + targetType**.

Để cố định API minh họa, ví dụ sử dụng **Java 17, Spring Boot 3.3.13 / Spring Security 6.x**. Đây là phiên bản minh họa; dự án mới nên chọn nhánh Spring Boot hiện được hỗ trợ. Tên lớp và file dưới đây là một chương trình độc lập.

### 5.1. Cấu trúc dự án

```text
permission-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PermissionDemoApplication.java
    │   ├── Document.java
    │   ├── DocumentStore.java
    │   ├── DocumentPermissionEvaluator.java
    │   └── DocumentService.java
    └── test/java/demo/
        └── DocumentServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'permission-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không cần module ACL để chạy ví dụ: đây là một evaluator tùy chỉnh dùng quy tắc ownership trong bộ nhớ.

### 5.2. Domain object và kho dữ liệu đáng tin cậy

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(Long id, String owner, String title) {
}
```

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    private final Map<Long, Document> documents = new ConcurrentHashMap<>();

    public DocumentStore() {
        documents.put(1L, new Document(1L, "alice", "Alpha"));
        documents.put(2L, new Document(2L, "bob", "Beta"));
    }

    public Document find(Long id) {
        return documents.get(id);
    }

    public Document rename(Long id, String newTitle) {
        Document updated = documents.computeIfPresent(
            id,
            (key, old) -> new Document(old.id(), old.owner(), newTitle)
        );
        if (updated == null) {
            throw new NoSuchElementException("Document not found: " + id);
        }
        return updated;
    }
}
```

Trong ứng dụng thật, `DocumentStore` tương ứng repository hoặc lớp đọc quyền/ACL trong database. Đoạn này giữ quyền sở hữu trên server; `owner` trong object người gọi đưa vào không được tin để cấp quyền.

### 5.3. Implement cả hai chữ ký `PermissionEvaluator`

**`src/main/java/demo/DocumentPermissionEvaluator.java`:**

```java
package demo;

import java.io.Serializable;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentStore store;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Lấy bản ghi THẬT theo ID; không tin owner từ object đầu vào.
        return allowed(
            authentication,
            store.find(document.id()),
            permission
        );
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }

        return allowed(authentication, store.find(id), permission);
    }

    private boolean allowed(
            Authentication authentication,
            Document storedDocument,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)
                || storedDocument == null) {
            return false;
        }

        if (!"read".equals(permission) && !"write".equals(permission)) {
            return false;
        }

        return authentication.getName().equals(storedDocument.owner());
    }
}
```

Các quyết định cụ thể:

1. Dạng object chỉ chấp nhận `Document`, sau đó **tra lại bản ghi theo `document.id()`**.
2. Dạng ID chỉ chấp nhận `targetType == "Document"` và ID kiểu `Long`.
3. Cả hai gọi chung `allowed(...)`, nên cùng một người, cùng một bản ghi, cùng một quyền sẽ có cùng kết quả.
4. Nếu không xác thực, người gọi ẩn danh, target không hợp lệ, bản ghi không tồn tại hoặc permission không hỗ trợ thì trả `false` (**fail closed**).
5. Bài này cho chủ sở hữu cả `read` và `write`; một chính sách thật có thể phân biệt editor, viewer, trạng thái tài liệu, người được chia sẻ, tenant và những quyền khác.

Không nhầm `permission` với `GrantedAuthority`: trong ví dụ này `'read'` và `'write'` là chuỗi do **evaluator** hiểu, chứ không mặc định là `ROLE_READ` hoặc authority được Spring tự ánh xạ.

### 5.4. Service dùng hai dạng trong `@PreAuthorize`

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#document, 'read')")
    public String readTitle(@P("document") Document document) {
        // Đọc dữ liệu server quản lý; không trả trường title từ DTO giả.
        return store.find(document.id()).title();
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'write')")
    public Document rename(@P("id") Long id, String newTitle) {
        return store.rename(id, newTitle);
    }
}
```

`@P("document")` và `@P("id")` làm tên tham số trong SpEL rõ ràng, kể cả khi quy trình biên dịch không giữ tên tham số. Có thể dùng `-parameters` thay thế; tuy nhiên cần bảo đảm tên SpEL trùng tên đã được Spring Security phát hiện.

`readTitle` minh họa authorization trên **đối tượng đã có**, còn `rename` minh họa trường hợp chỉ có ID; cả hai từ chối trước khi thân phương thức chạy nếu evaluator trả `false`.

### 5.5. Cấu hình, dựng security context mô phỏng và gọi qua Spring bean

**`src/main/java/demo/PermissionDemoApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PermissionDemoApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    CommandLineRunner demonstrate(DocumentStore store, DocumentService service) {
        return args -> {
            try {
                authenticateAs("alice");

                System.out.println("OBJECT alice/1: "
                    + service.readTitle(store.find(1L)));

                System.out.println("ID alice/1: "
                    + service.rename(1L, "Alpha edited").title());

                try {
                    service.rename(2L, "Unauthorized change");
                    throw new IllegalStateException("Access should be denied");
                } catch (AccessDeniedException expected) {
                    System.out.println("ID alice/2: DENIED");
                }

                authenticateAs("bob");
                System.out.println("ID bob/2: "
                    + service.rename(2L, "Beta edited").title());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticateAs(String username) {
        var auth = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        SecurityContextHolder.getContext().setAuthentication(auth);
    }
}
```

Chạy tại thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows dùng `.\gradlew.bat bootRun`. Nếu chưa tạo Gradle Wrapper và máy có Gradle, dùng `gradle bootRun`. Bốn dòng được code demo in ra, bên cạnh log Spring Boot, phải là:

```text
OBJECT alice/1: Alpha
ID alice/1: Alpha edited
ID alice/2: DENIED
ID bob/2: Beta edited
```

Diễn giải:

- `alice` đọc đối tượng `Document(1, alice, Alpha)` thành công qua chữ ký object.
- `alice` sửa ID `1` thành công qua chữ ký ID/type.
- `alice` không sửa được ID `2` vì bản ghi server xác định owner là `bob`; `AccessDeniedException` được bắt để minh họa.
- `bob` sửa ID `2` thành công dù cả hai đều có cùng `ROLE_USER`.

**Giới hạn ví dụ:** `UsernamePasswordAuthenticationToken` được tạo thủ công **chỉ phục vụ mô phỏng kiểm thử**. Ứng dụng thật phải xác thực người gọi bằng cấu hình Spring Security thích hợp (session, resource server JWT, v.v.) và không nhận username tự khai rồi tự tạo token đã xác thực.

## 6. Kiểm thử tích hợp: kiểm tra lời gọi qua proxy

**`src/test/java/demo/DocumentServiceTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentServiceTest {

    @Autowired DocumentService service;
    @Autowired DocumentStore store;

    @Test
    @WithMockUser(username = "alice")
    void objectFormUsesTrustedOwner() {
        assertEquals(
            store.find(1L).title(),
            service.readTitle(store.find(1L))
        );

        // Dù object khai owner là alice, ID 2 thật ra thuộc bob.
        var forged = new Document(2L, "alice", "Forged");
        assertThrows(
            AccessDeniedException.class,
            () -> service.readTitle(forged)
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void idFormAllowsOwnerButRejectsOtherOwner() {
        assertEquals(
            "Allowed edit",
            service.rename(1L, "Allowed edit").title()
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.rename(2L, "Should not persist")
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void idFormAllowsBobOnHisOwnDocument() {
        assertEquals(
            "Bob edit",
            service.rename(2L, "Bob edit").title()
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test dùng `@WithMockUser` từ `spring-security-test`. Mỗi test gọi `@Autowired DocumentService`, nghĩa là lời gọi đi qua bean Spring có method-security interceptor. Chúng chứng minh:

- Chữ ký object được gọi với object thật thì cho phép, với object giả owner thì từ chối.
- Chữ ký ID cho phép sửa đúng chủ sở hữu, từ chối sai chủ sở hữu.
- Thay đổi user hiện hành thay đổi kết quả trên cùng một loại tài nguyên.

Ngoài ra nên kiểm thử target `null`, ID không tồn tại, targetType không được hỗ trợ, permission lạ và người dùng ẩn danh. Đừng kiểm thử bằng cách gọi `new DocumentService(store)` rồi kết luận `@PreAuthorize` đang bảo vệ, vì cách đó bỏ qua proxy.

## 7. `hasPermission` trong các annotation khác

`hasPermission` là hàm SpEL dùng được với những annotation method security khác, miễn dữ liệu và thời điểm đánh giá phù hợp.

### 7.1. `@PostAuthorize` — kiểm tra kết quả trả về

```java
@PostAuthorize(
    "returnObject != null and hasPermission(returnObject, 'read')"
)
public Document findDocument(Long id) {
    return documentStore.find(id);
}
```

`returnObject` là đối tượng được phương thức trả về. Kiểm tra xảy ra **sau khi thân phương thức chạy**, phù hợp cho các truy vấn cần nạp object rồi mới quyết định quyền đọc. Đừng dùng `@PostAuthorize` như biện pháp duy nhất để bảo vệ thao tác có side effect: cập nhật dữ liệu có thể đã diễn ra trước khi trả về kết quả bị từ chối. Với thao tác ghi, ưu tiên kiểm tra trước khi thực hiện và ràng buộc ở tầng dữ liệu.

Đoạn trên minh họa cú pháp trong một bean có `documentStore` đã được tiêm; nó không phải file Java độc lập.

### 7.2. `@PreFilter` — lọc đầu vào theo từng đối tượng

```java
@PreFilter("hasPermission(filterObject, 'write')")
public void updateAllowed(java.util.List<Document> documents) {
    // Chỉ nhận những phần tử còn lại sau lọc.
}
```

`filterObject` đại diện từng phần tử đầu vào. Tùy kiểu collection và cách Spring thực thi, danh sách đầu vào có thể bị thay đổi; cần dùng danh sách có thể xóa phần tử và định nghĩa rõ nghiệp vụ có chấp nhận **xử lý một phần** hay không. Một phép lọc không đồng nghĩa từ chối cả lời gọi.

### 7.3. `@PostFilter` — lọc đầu ra theo từng đối tượng

```java
@PostFilter("hasPermission(filterObject, 'read')")
public java.util.List<Document> listVisibleDocuments() {
    return new java.util.ArrayList<>(documentStore.findAll());
}
```

`@PostFilter` trả cho người gọi tập kết quả đã lọc. Đây chỉ là ví dụ cú pháp; `findAll()` cần do repository của ứng dụng cung cấp. Tải **toàn bộ** bảng rồi lọc từng bản ghi có thể tốn nhiều truy vấn và bộ nhớ; với dữ liệu lớn nên lọc ngay ở truy vấn theo tenant, owner, quyền hoặc ACL.

### 7.4. Kết hợp quyền toàn cục và quyền trên object

```java
@PreAuthorize(
    "hasAuthority('document:write') and " +
    "hasPermission(#id, 'Document', 'write')"
)
public void updateDocument(@P("id") Long id) {
    // ...
}
```

Điều kiện thứ nhất yêu cầu authority tổng quát; điều kiện thứ hai yêu cầu quyền **trên đúng ID**. Đây là các điều kiện độc lập, được kết hợp bằng `and` để chỉ cho phép khi cả hai đúng. Cần bảo đảm tầng xác thực cấp `GrantedAuthority` chính xác; permission trong evaluator vẫn là một khái niệm khác với authority.

## 8. Lỗi phổ biến và cách khắc phục

| Vấn đề | Vì sao xảy ra | Cách khắc phục |
| --- | --- | --- |
| Mọi lời gọi `hasPermission` bị từ chối | Chưa đăng ký evaluator có chính sách phù hợp; mặc định deny-all | Cấu hình `MethodSecurityExpressionHandler.setPermissionEvaluator(...)` |
| Annotation không có tác dụng | Chưa bật method security; service được tạo bằng `new`; self-invocation | Bật `@EnableMethodSecurity`; gọi qua Spring bean/proxy |
| `#id` hoặc `#document` không lấy đúng giá trị | SpEL không tìm được tên tham số | Dùng `@P("id")`, `@P("document")` hoặc biên dịch với `-parameters` |
| Dạng ID luôn `false` | `targetType` không đúng quy ước, ID khác kiểu, evaluator chưa implement chữ ký thứ hai | Thống nhất targetType, kiểu ID và hai overload |
| Dạng object cho phép sai người | Tin `owner` do client gửi thay cho owner thật | Tra cứu bản ghi/ACL server quản lý trước khi cấp quyền |
| Có thể sửa dữ liệu dù đã dùng `@PostAuthorize` | Kiểm tra sau khi thân method đã làm side effect | Dùng `@PreAuthorize`, transaction và ràng buộc dữ liệu ở bước ghi |
| Quyền `read`/`write` không có hiệu lực như dự kiến | Evaluator xử lý chuỗi khác tên/case hoặc bỏ qua permission | Định nghĩa tập permission rõ ràng, default-deny và test |
| Lấy dữ liệu chậm khi trả danh sách dài | Gọi evaluator và truy vấn ACL N lần | Lọc theo DB, truy vấn theo lô, cache hợp lệ hoặc phân trang |
| Không tìm thấy đối tượng nhưng lại cho phép | Logic evaluator mặc định true khi null/not found | Trả `false` khi thiếu target, loại, permission hoặc người dùng |
| User bị từ chối nhưng mutation đã xảy ra | Quyền thay đổi giữa check và update (TOCTOU) | Kiểm tra/ràng buộc lại trong transaction hoặc câu lệnh update có điều kiện |

Một quy ước an toàn là **fail closed**: nếu không giải được `targetId`, không nhận diện được `targetType`, không xác thực được người gọi hoặc không biết permission thì từ chối. Đừng dùng quy tắc `return true` làm fallback để “sửa lỗi” cấu hình.

## 9. Đối tượng trực tiếp, ID và ACL: chọn nơi lưu chính sách

`PermissionEvaluator` là interface chiến lược. Bạn có thể:

1. **Viết evaluator riêng** dùng owner, organization, tenant hoặc danh sách chia sẻ lưu trong database. Ví dụ ở mục 5 là phiên bản giản lược.
2. **Dùng Spring Security ACL** khi mỗi domain object có danh sách quyền/ACE riêng. `AclPermissionEvaluator` tích hợp được với các biểu thức `hasPermission(...)`, nhưng cần thêm thư viện ACL, kho ACL (`AclService`), identity, permission mask và các thành phần liên quan. Chỉ bật `@EnableMethodSecurity` không tự tạo ACL.
3. **Dùng bean phân quyền chuyên biệt** trong SpEL, chẳng hạn `@documentAuthorization.canWrite(authentication, #id)`, nếu chính sách có nghiệp vụ phong phú hơn interface `PermissionEvaluator`. Cách này cũng cần kiểm thử và dữ liệu server đáng tin cậy.

Nếu dùng ACL, tên `targetType` trong dạng ID phải khớp `ObjectIdentity`/mapping của ACL. Nếu dùng evaluator riêng như bài này, bí danh `'Document'` hoàn toàn hợp lệ vì chính evaluator đã định nghĩa cách hiểu nó.

### Chi phí và tính nhất quán

Với `hasPermission(#id, 'Document', 'write')`, evaluator thường phải đọc quyền hoặc metadata trước khi gọi service. Giữa lần kiểm tra đó và lần cập nhật, chủ sở hữu/ACL có thể bị thay đổi. Trong hệ thống nhiều người dùng, cần xét transaction, kiểm tra trong truy vấn cập nhật (`UPDATE ... WHERE id = ? AND owner_id = ?`), optimistic locking hoặc cơ chế tương đương. `@PreAuthorize` là hàng rào trước lời gọi, **không tự cung cấp sự nguyên tử của DB**.

Với hàng trăm hoặc hàng nghìn object, kiểm tra từng object có thể gây N+1 query. Khi chính sách cho phép, đẩy điều kiện owner/tenant xuống repository hoặc sử dụng truy vấn ACL theo lô và cache có chiến lược hết hạn/invalidation đúng.

### Nhiều tenant

Trong ứng dụng đa tenant, điều kiện `authentication.name.equals(owner)` thường chưa đủ. Cần kiểm tra thêm tenant của principal **và** tenant của bản ghi từ nguồn đáng tin cậy; không chấp nhận tenant ID do caller tự khai như bằng chứng quyền.

## 10. Bài tập tự kiểm tra

1. **`hasPermission(#document, 'read')` chuyển vào overload nào?** → Overload `(Authentication, Object targetDomainObject, Object permission)`.
2. **`hasPermission(#id, 'Document', 'write')` chuyển vào overload nào?** → Overload `(Authentication, Serializable targetId, String targetType, Object permission)`.
3. **Ai cấp `Authentication` cho evaluator?** → Spring Security lấy từ ngữ cảnh xác thực hiện tại khi đánh giá biểu thức; không cần truyền `authentication` bằng tay trong annotation.
4. **Client gửi `{id:2, owner:"alice"}` trong khi bản ghi `#2` thật thuộc `bob`; có nên cho `alice` sửa không?** → Không. Kiểm tra owner/ACL từ server, không tin DTO.
5. **Thêm `hasPermission` mà quên cấu hình evaluator cấp quyền có đủ không?** → Không. Biểu thức chỉ là điểm móc; cần policy thực tế, và mặc định deny-all không tự suy ra ownership.
6. **Muốn kiểm tra quyền ghi trước mutation thì chọn annotation nào?** → Thường là `@PreAuthorize` kết hợp ràng buộc an toàn ở tầng dữ liệu. `@PostAuthorize` được đánh giá sau thân phương thức.
7. **`targetType = 'Document'` có bắt buộc là tên lớp đầy đủ không?** → Không với custom evaluator; đó là chuỗi do evaluator diễn giải. Với ACL/framework khác phải tuân theo quy ước định danh của framework.
8. **Vì sao test cần `@Autowired DocumentService`?** → Để gọi qua Spring proxy, nơi các interceptor Method Security thực sự được áp dụng.

## 11. Tài liệu chính thức

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): bật method security, SpEL, `hasPermission`, tham số trong biểu thức và cấu hình expression handler.
- [Spring Security — `PermissionEvaluator` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): hai chữ ký `hasPermission`, kiểu `Serializable`, `targetType`, `permission` và hành vi đối với object null.
- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL và tích hợp `AclPermissionEvaluator`.
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` và kiểm thử phân quyền trên Spring bean.

**Điểm cần nhớ:** `hasPermission(object, permission)` dành cho lúc có object; `hasPermission(id, type, permission)` dành cho lúc có ID. Cả hai đều chuyển quyết định sang `PermissionEvaluator` với `Authentication` hiện tại. An toàn của quyết định phụ thuộc vào việc evaluator dùng **quyền và dữ liệu đáng tin cậy phía server**, xử lý trường hợp không xác định bằng từ chối và bảo đảm thao tác ghi không vượt qua kiểm tra khi dữ liệu thay đổi.