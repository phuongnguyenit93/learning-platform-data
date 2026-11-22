# Chuyển @EnableGlobalMethodSecurity sang @EnableMethodSecurity

## 1. Bối cảnh và mục tiêu

Trong các ứng dụng Spring Security đời cũ, method-level authorization thường được kích hoạt bằng `@EnableGlobalMethodSecurity`. Với kiến trúc method security hiện đại, Spring Security khuyến nghị `@EnableMethodSecurity`. Đây là thay đổi **cách kích hoạt và triển khai cơ chế bảo vệ phương thức**, không đơn thuần là đổi tên annotation. Các cờ bật từng họ annotation, cấu hình biểu thức tùy chỉnh và cách thực thi ủy quyền đều cần được rà soát.

Bài học tập trung vào việc chuyển một ứng dụng Spring Boot/Spring Security đang sử dụng method security cũ sang cấu hình mới mà **không vô tình cấp thừa quyền hoặc khóa nhầm chức năng**. Ví dụ hướng đến Java 17+, Spring Boot 3.x và Spring Security 6.x. Nếu ứng dụng vẫn dùng Boot 2.x/Security 5.x, cần đối chiếu phiên bản đang chạy; việc đổi annotation không tự hoàn tất nâng cấp Spring Framework/Jakarta.

Kết quả cần đạt:

- Nhận ra các khác biệt về default của `prePostEnabled`, `securedEnabled` và `jsr250Enabled`.
- Viết cấu hình `@EnableMethodSecurity` tương ứng với chính sách đã có.
- Giữ nguyên đúng ngữ nghĩa `@PreAuthorize`, `@PostAuthorize`, `@Secured` và `@RolesAllowed`.
- Biết khi nào phải chuyển phần mở rộng từ `GlobalMethodSecurityConfiguration`, voter/metadata cũ sang cách tích hợp `AuthorizationManager` hoặc bean method-security hiện hành.
- Kiểm thử thật trên Spring-managed bean và các trường hợp được phép/bị từ chối.
- Nhận diện các bẫy proxy, self-invocation, role prefix, tham số SpEL, thứ tự transaction và phạm vi ủy quyền dữ liệu.

## 2. So sánh hai annotation

Cấu hình cũ thường có dạng:

```java
import org.springframework.security.config.annotation.method.configuration
        .EnableGlobalMethodSecurity;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableGlobalMethodSecurity(
        prePostEnabled = true,
        securedEnabled = true,
        jsr250Enabled = true
)
public class LegacyMethodSecurityConfig {
}
```

Trong ứng dụng tương ứng với cấu hình mới:

```java
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableMethodSecurity(
        prePostEnabled = true,
        securedEnabled = true,
        jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

Hai ví dụ này có ý nghĩa **bật cùng ba họ annotation**, nhưng vẫn cần kiểm tra customized security logic và hồi quy nghiệp vụ. Nếu cấu hình cũ bật những cờ khác nhau, **không sao chép ví dụ một cách máy móc**.

| Hạng mục | `@EnableGlobalMethodSecurity` cũ | `@EnableMethodSecurity` mới | Tác động khi chuyển |
| --- | --- | --- | --- |
| `prePostEnabled` mặc định | `false` | **`true`** | Các annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` có thể bắt đầu được thực thi dù trước đây chưa bật |
| `securedEnabled` mặc định | `false` | `false` | Phải khai báo `securedEnabled = true` nếu dùng `@Secured` |
| `jsr250Enabled` mặc định | `false` | `false` | Phải khai báo `jsr250Enabled = true` nếu dùng `@RolesAllowed`, `@PermitAll`, `@DenyAll` theo JSR-250 |
| Cơ chế nền tảng | Thường gắn với các thành phần method security cũ như metadata source, voter và `AccessDecisionManager` | Dựa trên `AuthorizationManager` và các interceptor theo annotation | Extension cũ cần đánh giá cách thay thế; không giả định override cũ còn tác dụng |
| Bật method security | Qua cấu hình cũ | Qua cấu hình mới, các interceptor được đăng ký tương ứng | Cần bỏ cấu hình trùng và test proxy thực sự đang được áp dụng |
| Quy tắc URL/HTTP | Tách khỏi method authorization | Vẫn tách khỏi method authorization | Thay annotation không thay cho `SecurityFilterChain` và ngược lại |

**Khác biệt dễ bị bỏ sót nhất là `prePostEnabled` mặc định chuyển từ `false` sang `true`.** Ví dụ ứng dụng cũ chỉ có:

```java
@EnableGlobalMethodSecurity(securedEnabled = true)
```

Để giữ gần đúng phạm vi annotation được kích hoạt trước đây khi chuyển sang mới, cần thể hiện rõ:

```java
@EnableMethodSecurity(
        prePostEnabled = false,
        securedEnabled = true
)
```

Nếu chủ đích là bắt đầu dùng `@PreAuthorize` trong cùng đợt nâng cấp, có thể để `prePostEnabled = true`, nhưng đó là **thay đổi chính sách có chủ đích** và phải bổ sung test. Đừng để mặc định mới vô tình bật những annotation trước đây không hoạt động.

## 3. Các annotation và cách hiểu quyền khi nâng cấp

### 3.1. `@PreAuthorize` và `@PostAuthorize`

`@PreAuthorize` đánh giá biểu thức **trước khi gọi phương thức**. Ví dụ:

```java
@PreAuthorize("hasAuthority('DOCUMENT_EDIT')")
public void updateDocument(UUID documentId, String content) {
    // Kiểm tra quyền cụ thể trên document vẫn cần thiết nếu policy yêu cầu.
}
```

`@PostAuthorize` đánh giá biểu thức sau khi phương thức trả về; có thể dùng `returnObject` trong biểu thức. Tuy nhiên, nó **không quay ngược side effect** đã xảy ra trong phương thức. Không dùng hậu kiểm để bảo vệ ghi dữ liệu, gửi message hoặc gọi API bên ngoài có tác động không đảo ngược được.

`@PreFilter` và `@PostFilter` lọc các phần tử collection theo điều kiện biểu thức khi được bật. Các annotation này có thể ảnh hưởng dữ liệu đầu vào hoặc kết quả trả về, vì vậy sau nâng cấp cần kiểm thử cả số lượng/phạm vi phần tử, không chỉ mã HTTP.

Ví dụ kiểm tra quyền theo tài nguyên:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentDto readDocument(UUID documentId) {
    return repository.loadForView(documentId);
}
```

`documentPolicy` là bean do ứng dụng tự định nghĩa, không phải API mặc định của Spring Security. Nó phải xác minh actor lấy từ `Authentication` đã xác thực, quan hệ quyền của actor với document và tenant liên quan từ nguồn có thẩm quyền. Không tin `ownerId`, `role` hay `tenantId` do client tự khai như bằng chứng authorization.

### 3.2. `@Secured`

Khi dự án còn dùng:

```java
@Secured("ROLE_AUDITOR")
public AuditReport viewAudit() {
    // ...
}
```

Cấu hình mới phải có `securedEnabled = true` để kích hoạt kiểm tra này. Chuỗi trong `@Secured` thường là authority thực tế, chẳng hạn `ROLE_AUDITOR`; không tự động giả định nó được biến đổi giống tham số của `hasRole('AUDITOR')`. Hãy kiểm tra các `GrantedAuthority` thực tế được cấp cho user và role prefix được cấu hình.

Nếu bỏ quên cờ `securedEnabled`, annotation có thể không được method-security infrastructure thực thi và method từng được bảo vệ có thể trở nên truy cập được từ những caller không phù hợp. Kiểm thử trường hợp **không đủ quyền** là bắt buộc.

### 3.3. `@RolesAllowed` và JSR-250 / Jakarta

Ứng dụng cũ có thể import:

```java
import javax.annotation.security.RolesAllowed;
```

Khi chuyển toàn bộ ứng dụng sang Spring Boot 3 / Spring Framework 6, môi trường dùng namespace Jakarta:

```java
import jakarta.annotation.security.RolesAllowed;
```

Đoạn ví dụ:

```java
@RolesAllowed("OPERATIONS")
public void executeOperations() {
    // ...
}
```

Yêu cầu `@EnableMethodSecurity(jsr250Enabled = true)`. Với cấu hình role prefix phổ biến, `@RolesAllowed("OPERATIONS")` kiểm tra authority tương ứng `ROLE_OPERATIONS`. Trong khi đó `@Secured("ROLE_OPERATIONS")` ghi rõ chuỗi authority. Nếu ứng dụng cấu hình custom prefix, phải kiểm tra ngữ nghĩa thực tế bằng test thay vì mặc định chuỗi role luôn giống nhau.

`@PermitAll` và `@DenyAll` cũng thuộc nhóm JSR-250; khi bật nhóm này, cần xác minh các chú thích có đúng phạm vi phương thức hay không. Namespace `javax` → `jakarta` là phần nâng cấp nền tảng, khác với bản thân việc thay annotation kích hoạt.

### 3.4. Kết hợp nhiều annotation trên một phương thức

Không nên đặt một loạt annotation authorization khác họ lên cùng phương thức khi chưa xác định rõ cách chúng kết hợp và thứ tự interceptor. Ví dụ `@Secured` kèm `@PreAuthorize` trên cùng method có thể dẫn đến nhiều kiểm tra riêng; không nên suy diễn chúng kết hợp theo OR chỉ vì mỗi annotation có một danh sách role. Hãy quy về một policy biểu đạt rõ ràng và kiểm thử kết quả mong đợi.

Các phương thức public nhạy cảm như chuyển owner, duyệt tài liệu, tải file, export dữ liệu hoặc quản lý role cần policy cụ thể theo action và resource. Role tổng quát là điều kiện cần trong một số hệ thống, nhưng không luôn đủ để xác định quyền với một document hay tenant.

## 4. Quy trình chuyển đổi có kiểm soát

### Bước 1 — Thống kê toàn bộ điểm kích hoạt và sử dụng

Trong dự án thực, tìm `@EnableGlobalMethodSecurity` và các subclass của `GlobalMethodSecurityConfiguration`. Xác định cấu hình nào là nguồn chính, giá trị hiện tại của `prePostEnabled`, `securedEnabled`, `jsr250Enabled`, proxy settings và các custom bean.

Tiếp theo lập danh sách các loại annotation thực dùng: `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, `@Secured`, `@RolesAllowed`, `@PermitAll` và `@DenyAll`. Chú ý annotation đặt trên interface, class, method kế thừa hoặc meta-annotation do dự án định nghĩa.

Đừng kết luận chỉ từ annotation tồn tại trong source: nếu cấu hình cũ chưa bật họ đó, annotation có thể chưa được thực thi. Đây là điểm cần đưa vào kế hoạch kiểm thử để tránh thay đổi hành vi ngoài dự kiến.

### Bước 2 — Ghi lại hợp đồng authorization hiện tại

Với từng nhóm phương thức nhạy cảm, ghi nhận actor nào được phép và actor nào phải bị từ chối. Tối thiểu gồm principal chưa xác thực, user có role đúng, user có role sai, user có role nhưng tài nguyên thuộc người/tenant khác, admin đúng phạm vi, và các trường hợp sau thu hồi quyền.

Kiểm tra thêm quyền trên cùng action nhưng ở các tenant/resource khác nhau. Nếu chính sách phụ thuộc trạng thái nghiệp vụ (ví dụ `DRAFT`, `PUBLISHED`, `LOCKED`), test cần bao phủ trạng thái hợp lệ và không hợp lệ.

### Bước 3 — Đổi cấu hình và giữ đúng flags

Xóa cấu hình kích hoạt cũ khỏi đường cấu hình đang hoạt động, thay bằng `@EnableMethodSecurity` trong một lớp `@Configuration` được Spring quản lý hoặc trên lớp `@SpringBootApplication`. Viết tường minh các cờ cần thiết. Không giữ hai cấu hình method-security trùng nhau với hy vọng cái mới tự ghi đè cái cũ.

Nếu ứng dụng chỉ dùng `@PreAuthorize`, thông thường có thể viết:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Trong trường hợp này, `prePostEnabled = true` được kích hoạt mặc định. Nếu cần `@Secured` hoặc JSR-250, bật thêm cờ tương ứng.

### Bước 4 — Chuyển các extension cũ

Nếu trước đây ứng dụng kế thừa `GlobalMethodSecurityConfiguration` để override `createExpressionHandler()`, `accessDecisionManager()` hoặc tạo voter riêng, không sao chép nguyên logic override vào một lớp mới rồi cho rằng nó được dùng tự động. `@EnableMethodSecurity` dựa trên các thành phần `AuthorizationManager` và interceptor mới.

Các hướng chuyển đổi thông dụng:

- **Biểu thức tùy chỉnh:** đăng ký bean service để gọi trong SpEL, ví dụ `@PreAuthorize("@documentPolicy.canEdit(authentication, #id)")`. Với `PermissionEvaluator`, `RoleHierarchy` hoặc trust resolver tùy chỉnh, cấu hình bean `MethodSecurityExpressionHandler` phù hợp và kiểm tra nó được wiring vào đúng infrastructure.
- **Quy tắc từ voter/metadata cũ:** chuyển thành `AuthorizationManager` cho điểm chặn phù hợp hoặc policy service được dùng từ annotation; kiểm tra lại semantics `GRANT`/`DENY`/abstain thay vì giả định tương đương.
- **Expression root và parameter names:** kiểm tra các SpEL `#id`, `#tenantId` và `returnObject`. Metadata tên tham số có thể dựa trên biên dịch với `-parameters` hoặc annotation chỉ định tên; nếu tên không được phát hiện đúng, policy có thể nhận `null`/lỗi.
- **Thứ tự advice:** kiểm tra method-security interceptor với `@Transactional`, caching và custom aspects; một quyết định trước transaction không tự bảo vệ quyền nếu owner/policy thay đổi ngay trước thao tác ghi.

Ví dụ bean expression handler chỉ minh họa khi ứng dụng **đã có** `PermissionEvaluator` của mình:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {

        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
```

Các import tương ứng là `org.springframework.security.access.PermissionEvaluator`, `org.springframework.security.access.expression.method.MethodSecurityExpressionHandler` và `org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler`. Phương thức `@Bean static` giúp bean này được công bố trước giai đoạn khởi tạo cấu hình method security trong những kịch bản cần thiết. Cần có bean `PermissionEvaluator` do ứng dụng cung cấp; snippet không độc lập. Đừng kết luận mọi custom voter đều chuyển thành một `PermissionEvaluator` — mỗi extension phải được map theo đúng nhiệm vụ của nó.

### Bước 5 — Kiểm thử trước khi xóa cơ chế cũ

Chạy lại test contract quyền với cấu hình mới. Xác minh cả annotation hoạt động lẫn sự thiếu quyền bị từ chối. Kiểm tra các tài nguyên ngoài tenant, quyền chỉ đọc khi gọi write, self-invocation, phương thức gọi từ async/batch, thay role giữa request và xử lý, cũng như logging không rò dữ liệu.

Không chỉ test một controller HTTP đã chặn ở filter chain: nếu controller đã yêu cầu `authenticated()`, request anonymous bị từ chối có thể khiến test **trông như pass dù method security chưa được bật**. Cần gọi bean service thông qua Spring proxy với principal có authority phù hợp/không phù hợp và assert đúng method-level behavior.

## 5. Ví dụ hoàn chỉnh trong ứng dụng Spring Boot 3

Ví dụ dưới đây là các tệp Java có thể chạy trong **dự án Spring Boot 3.x đang hoạt động với Java 17+**, không phải chương trình chỉ cần chạy `javac` thuần vì chúng phụ thuộc Spring Framework, Spring Security, Jakarta và JUnit.

Với dự án Gradle đã có Spring Boot plugin và quản lý version dependency, bảo đảm các dependency phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tệp `src/main/java/com/example/methodsecurity/MethodSecurityDemoApplication.java`:

```java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity(
        prePostEnabled = true,
        securedEnabled = true,
        jsr250Enabled = true
)
public class MethodSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/methodsecurity/DocumentActions.java`:

```java
package com.example.methodsecurity;

import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentActions {

    @PreAuthorize("hasAuthority('DOC_WRITE')")
    public String edit(String id) {
        return "edited:" + id;
    }

    @Secured("ROLE_AUDITOR")
    public String viewAudit() {
        return "audit";
    }

    @RolesAllowed("OPERATIONS")
    public String executeOperations() {
        return "operations";
    }
}
```

Ba phương thức dùng ba họ annotation khác nhau, giúp nhìn rõ vì sao cấu hình phải bật đủ ba cờ.

Tệp `src/test/java/com/example/methodsecurity/DocumentActionsTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class DocumentActionsTest {

    @Autowired
    private DocumentActions actions;

    @Test
    @WithMockUser(authorities = "DOC_WRITE")
    void preAuthorizeAllowsCorrectAuthority() {
        assertEquals("edited:d-1", actions.edit("d-1"));
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void preAuthorizeDeniesWrongAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> actions.edit("d-1"));
    }

    @Test
    @WithMockUser(roles = "AUDITOR")
    void securedAnnotationIsEnabled() {
        assertEquals("audit", actions.viewAudit());
    }

    @Test
    @WithMockUser(roles = "OPERATIONS")
    void jsr250AnnotationIsEnabled() {
        assertEquals("operations", actions.executeOperations());
    }

    @Test
    @WithMockUser(roles = "USER")
    void jsr250DeniesWrongRole() {
        assertThrows(AccessDeniedException.class,
                () -> actions.executeOperations());
    }
}
```

Với dự án Gradle có wrapper, chạy:

```bash
./gradlew test --tests 'com.example.methodsecurity.DocumentActionsTest'
```

Trên Windows PowerShell dùng wrapper tương ứng:

```powershell
.\gradlew.bat test --tests 'com.example.methodsecurity.DocumentActionsTest'
```

**Kết quả mong đợi của bài test:** cả năm test thành công. Hai test có `assertThrows` khẳng định actor thiếu quyền bị từ chối; ba test còn lại khẳng định `@PreAuthorize`, `@Secured` và JSR-250 thực sự cho phép người có quyền. Đây là kỳ vọng khi chạy trong môi trường Boot/Security tương thích với cấu hình và code mẫu; không phải một stdout cố định do `java` in ra.

Nếu bỏ `securedEnabled = true`, test `securedAnnotationIsEnabled` như trên **chưa đủ phát hiện lỗi**, vì một method không bị chặn vẫn trả `"audit"`. Cần bổ sung test negative riêng cho `@Secured`:

```java
@Test
@WithMockUser(roles = "USER")
void securedDeniesWrongRole() {
    assertThrows(AccessDeniedException.class, actions::viewAudit);
}
```

Test này đặt **trong cùng lớp `DocumentActionsTest`**. Tương tự, nếu bỏ `jsr250Enabled = true`, test `jsr250DeniesWrongRole` sẽ phát hiện việc `@RolesAllowed` không được thực thi. Nếu bỏ cấu hình bật pre/post, test `preAuthorizeDeniesWrongAuthority` sẽ phát hiện lỗi tương ứng. Với bổ sung negative cho `@Secured`, bộ test mẫu có sáu trường hợp.

Từ đó mở rộng sang các phương thức có policy theo tài nguyên/tenant thật: `@WithMockUser` chỉ mô phỏng security context, không xác minh cấu hình kiểm chữ ký JWT, JWT authority converter hoặc đường HTTP thực. Khi kiểm thử hệ thống production, bổ sung `MockMvc`/security filter integration test và kiểm tra dữ liệu repository thật.

## 6. Các bẫy thường gặp sau khi đổi annotation

### 6.1. Method được gọi nội bộ nên proxy không chạy

Trong chế độ Spring AOP proxy thông thường, annotation method security có hiệu lực khi lời gọi đi **qua Spring-managed proxy**. Một phương thức trong cùng bean gọi `this.adminAction()` không đi qua proxy, nên annotation trên `adminAction` có thể không được thực thi.

Ví dụ không nên dựa vào:

```java
@Service
public class OperationsService {

    public void doWork() {
        this.deleteSensitiveRecord(); // Self-invocation không qua proxy.
    }

    @PreAuthorize("hasAuthority('RECORD_DELETE')")
    public void deleteSensitiveRecord() {
        // ...
    }
}
```

Đặt ranh giới quyền tại một bean/service được gọi từ bên ngoài qua proxy, hoặc tổ chức kiến trúc sao cho điểm kiểm tra thực sự được thực thi. Kiểm thử phải gọi đúng đường nghiệp vụ, không chỉ gọi trực tiếp phương thức được annotate. Private method, phương thức không được proxy intercept hoặc cách dùng final/proxy không tương thích cũng có thể làm method security không được áp dụng như mong đợi.

### 6.2. Trùng cấu hình cũ và mới

Khi còn cả `@EnableGlobalMethodSecurity` và `@EnableMethodSecurity` trong những configuration cùng active, ứng dụng có nguy cơ tạo các infrastructure/interceptor chồng lắp hoặc hành vi khó phân tích. Xác định nguồn bật method security duy nhất và gỡ đường cũ sau khi xác nhận mới hoạt động.

### 6.3. Quên một flag nên mất bảo vệ

Chuyển `@EnableGlobalMethodSecurity(securedEnabled = true, jsr250Enabled = true)` thành `@EnableMethodSecurity` mặc định làm `@Secured` và `@RolesAllowed` **không được bật**, trong khi `@PreAuthorize` lại được bật mặc định. Đây là thay đổi kép: vừa có thể bỏ chặn endpoint cũ, vừa có thể bật điều kiện chưa từng thực thi. Một bộ test chỉ có phép thử thành công của người hợp lệ không phát hiện được.

### 6.4. Nhầm role và authority

`hasRole('ADMIN')` thường kiểm tra authority `ROLE_ADMIN`, còn `hasAuthority('ADMIN')` kiểm tra chuỗi `ADMIN` chính xác. `@Secured("ROLE_ADMIN")` và `@RolesAllowed("ADMIN")` có cách biểu diễn khác nhau theo mapping prefix. Kiểm tra `GrantedAuthority` thực từ principal/role converter và cấu hình `GrantedAuthorityDefaults`/role hierarchy nếu dự án có custom.

### 6.5. Sai tên tham số SpEL

Nếu `@PreAuthorize("@policy.canUpdate(authentication, #id)")` nhưng tên tham số biên dịch không được giữ/resolve, biểu thức có thể không nhận đúng ID. Với Java hiện đại, cấu hình compiler `-parameters` khi cần; có thể sử dụng annotation chỉ định tên tham số theo API đang hỗ trợ. Sau chuyển đổi test các method expression dùng tham số nhiều kiểu, null, overloaded method và proxy interface nếu có.

### 6.6. Tưởng đã bảo vệ URL thì method cũng được bảo vệ

`SecurityFilterChain` dùng `authorizeHttpRequests` bảo vệ luồng HTTP; method security bảo vệ lời gọi trên bean. Internal job, event consumer hoặc test có thể gọi service mà không đi qua URL filter. Ngược lại, method được bảo vệ không tự cấu hình CSRF, session management, authentication mechanism hay mapping HTTP. Cần cả hai khi nghiệp vụ đòi hỏi.

### 6.7. Tin rằng pre-authorization giữ quyền tới lúc ghi

`@PreAuthorize` ở thời điểm T0 không tự khóa tài liệu cho tới transaction commit. Nếu owner, tenant membership hoặc trạng thái thay đổi trước T1 ghi dữ liệu, policy có thể đã lỗi thời. Với thao tác cần quyền hiện hành lúc ghi, phải dùng conditional UPDATE/optimistic version/locking và transaction phù hợp; `@PostAuthorize` cũng không rollback side effect bên ngoài DB.

### 6.8. Cache kết quả quyền mà thiếu scope

Nếu custom expression `@policy.canRead(...)` có cache, kiểm tra key gồm subject đã xác minh, tenant, resource, action và revision/policy cần thiết. Việc thay annotation không sửa được cache decision dùng chung giữa Alice và Bob, hoặc stale ALLOW sau khi thu hồi role. Đảm bảo proxy cache và proxy security tương tác đúng bằng test hit/miss và revoke.

### 6.9. Di chuyển nhầm sang cấu hình reactive

Với ứng dụng reactive/WebFlux, Spring Security dùng hướng kích hoạt reactive method security riêng (`@EnableReactiveMethodSecurity`) và ngữ cảnh bảo mật reactive. Không chuyển một ứng dụng phản ứng sang `@EnableMethodSecurity` chỉ vì tên annotation mới, cũng không dùng `SecurityContextHolder` kiểu thread-local như nguồn bảo mật mặc định cho pipeline Reactive. Bài này hướng đến method security kiểu imperative/servlet; ứng dụng reactive cần xem cơ chế riêng.

## 7. Ma trận kiểm thử hồi quy trước và sau nâng cấp

| Kịch bản | Hành vi cần kiểm chứng |
| --- | --- |
| `@PreAuthorize` có authority đúng | Method được thực thi và trả kết quả dự kiến |
| `@PreAuthorize` thiếu authority | Bị từ chối, không xảy ra tác động nghiệp vụ |
| `@Secured` có role đúng | Cho phép khi `securedEnabled = true` |
| `@Secured` role sai | Từ chối; test phải thất bại nếu quên bật nhóm annotation |
| `@RolesAllowed` role đúng/sai | Cả cho phép và từ chối tương ứng khi `jsr250Enabled = true` |
| Annotation tiền/hậu kiểm vốn không bật ở cấu hình cũ | Xác định rõ có bật mới hay giữ `prePostEnabled=false`; không thay đổi ngầm |
| Role prefix và authority converter tùy chỉnh | `ROLE_X`, `X` và expression hoạt động theo hợp đồng thực |
| Policy theo tài nguyên | Role hợp lệ vẫn không truy cập document của người khác |
| Tenant khác | Không truy cập tài nguyên tenant ngoài phạm vi, dù ID hợp lệ |
| Self-invocation | Gọi đường nghiệp vụ thực không bypass điểm kiểm tra quyền |
| Method qua interface/implementation/proxy | Annotation đặt ở vị trí được Spring thực sự nhận diện |
| Dữ liệu phụ thuộc SpEL parameter | `#documentId` và `#tenantId` được resolve đúng |
| Custom expression/PermissionEvaluator | Chính sách tùy chỉnh vẫn chạy và nhận đúng actor/resource |
| Method chịu transaction/caching/aspect | Quyền được kiểm tra ở điểm cần thiết; không phát event sai khi từ chối |
| Unauthenticated và authenticated-but-denied | Phân biệt lỗi xác thực và thiếu quyền theo hợp đồng API |
| Multiple method-security configurations | Không có interceptor trùng/đường bảo vệ bị vô hiệu |
| Luồng batch, async, scheduler | Cần principal/context/authorization rõ, không dựa vào HTTP filter |
| Thay role/owner trong lúc xử lý | Không ghi trái phép với quyền đã hết hiệu lực theo hợp đồng |

**Cách kiểm thử:** tạo dữ liệu và principal có quyền/không quyền độc lập; gọi Spring-managed bean qua proxy; assert cả exception/HTTP status và trạng thái DB, audit/outbox/side effect; với phương thức có write, có ít nhất một integration test dùng DB thật và transaction/lock đúng kiến trúc. Trong web test, HTTP 401/403 phụ thuộc authentication entry point, exception translation và cấu hình filter; đừng giả định cùng một status cho mọi ngữ cảnh method call.

Nên chạy test trước chuyển đổi làm baseline, chuyển config, chạy lại cùng bộ test và bổ sung các case kích hoạt cờ mới. Nếu có khác biệt, đánh giá đó là thay đổi chính sách có chủ đích hay regression, không sửa bằng cách vô hiệu hóa toàn bộ method security.

## 8. Khi nào cần giữ, chuyển hoặc loại bỏ phần mở rộng cũ?

**Chỉ dùng annotation chuẩn:** nếu ứng dụng chỉ có `@PreAuthorize`/`@Secured`/JSR-250 và không override `GlobalMethodSecurityConfiguration`, bước chuyển có thể gọn: thay cấu hình, bật đúng flags và chạy test.

**Có custom `PermissionEvaluator` hoặc expression handler:** cần khai báo bean method security phù hợp; không chỉ chuyển import mà bỏ mất expression root, permission lookup hoặc role hierarchy. Nếu custom policy có thể được biểu đạt dễ hơn bằng bean expression như `@policy.canAct(authentication, #resourceId)`, cân nhắc giảm cơ chế extension riêng nhưng vẫn giữ contract.

**Có voter, AccessDecisionManager hoặc metadata source custom:** đây là thay đổi kiến trúc. Thiết kế lại theo `AuthorizationManager` hoặc interception phù hợp, so sánh logic cấp/từ chối/abstain và thứ tự chính sách. Không có phép đổi annotation một-một nào bảo đảm mọi voter custom được giữ lại.

**Có cơ chế bảo vệ thông qua AOP/AspectJ đặc biệt:** kiểm tra `proxyTargetClass`, mode, pointcut, thứ tự advice và kiểm thử ở runtime. Chỉ chuyển sang AspectJ hoặc thay chiến lược proxy nếu có lý do và hạ tầng tương ứng; không tự thêm weaving vào quá trình nâng cấp thông thường.

**Có component không qua Spring container:** annotation không tự bảo vệ object do code gọi `new`. Cần đưa service vào Spring quản lý hoặc đặt authorization ở ranh giới thực sự được gọi; migration không khắc phục thiếu proxy.

## 9. Checklist hoàn tất

1. Đã xác định các cấu hình method security hiện hành; loại bỏ đường bật cũ khi chuyển.
2. Đã so sánh default `prePostEnabled` và cờ `securedEnabled`/`jsr250Enabled` với chính sách trước nâng cấp; bật/tắt tường minh.
3. Đã chuyển import Jakarta cho JSR-250 trong môi trường Boot 3, đồng thời đảm bảo dependency phù hợp.
4. Đã rà soát custom expression, evaluator, role hierarchy, voter và cách nối `AuthorizationManager`.
5. Đã kiểm tra proxy/self-invocation, SpEL parameter names, lời gọi nội bộ, transaction và caching.
6. Đã test cho phép **và** từ chối trên bean được Spring quản lý với từng họ annotation.
7. Đã test authorization theo owner/tenant/resource/status và xác minh không ghi dữ liệu khi bị từ chối.
8. Đã kiểm tra quyền với luồng ngoài HTTP, cache stale và xử lý đồng thời nếu nghiệp vụ có liên quan.
9. Đã chạy test integration cho các API nhạy cảm, ghi lại thay đổi chính sách chủ đích và không có regression ngoài ý muốn.

**Điểm cần nhớ:** `@EnableMethodSecurity` là lựa chọn hiện đại cho method security kiểu imperative trong Spring Security; `prePostEnabled` được bật theo mặc định, nhưng `@Secured` và JSR-250 **không** tự bật. Một migration thành công phải giữ đúng quyết định ALLOW/DENY đối với actor, tài nguyên và hành động thật — và chứng minh bằng test — chứ không dừng ở việc ứng dụng khởi động sau khi đổi annotation.
