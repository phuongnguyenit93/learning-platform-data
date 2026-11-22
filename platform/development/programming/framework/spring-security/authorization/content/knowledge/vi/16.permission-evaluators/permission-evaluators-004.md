# hasPermission với targetId, targetType và permission

> **Phạm vi:** Spring Security – authorization, nhóm **PermissionEvaluator**. Trọng tâm là biểu thức ba tham số `hasPermission(targetId, targetType, permission)`, khi ứng dụng biết **ID** tài nguyên nhưng chưa có đối tượng domain đã tải. Bài học sử dụng method security trên Spring Boot Servlet, Java 17+ và `PermissionEvaluator` tùy chỉnh. Các ví dụ code Spring nhằm vào Spring Security 6.x/7.x có API tương ứng; phần mô phỏng Java 17 dùng JDK thuần.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Viết và hiểu `@PreAuthorize("hasPermission(#p0, 'Document', 'read')")` với ba thành phần: ID, kiểu tài nguyên và quyền cần xét.
2. Phân biệt overload ba tham số với `hasPermission(targetObject, permission)` và hai overload trong interface `PermissionEvaluator`.
3. Biết `Authentication` được framework truyền vào evaluator, còn `targetId`/`targetType`/`permission` đến từ biểu thức; không tin ID do client cung cấp là bằng chứng quyền.
4. Cấu hình `DefaultMethodSecurityExpressionHandler` để gọi evaluator thực tế; tránh việc chưa đăng ký evaluator dẫn tới toàn bộ kiểm tra bị từ chối.
5. Thiết kế evaluator không lộ dữ liệu khi tài nguyên không tồn tại, không thuộc tenant, thiếu ACL hoặc permission không được hỗ trợ.
6. Kiểm thử bằng `@WithMockUser` và Spring bean proxy để chứng minh người dùng có quyền, thiếu quyền, sai tenant, ID sai kiểu và nguồn dữ liệu bất hợp lệ đều được xử lý đúng.
7. Đánh giá hiệu năng tra cứu quyền, ranh giới giao dịch và nguy cơ race condition giữa check trước method với lần đọc/ghi dữ liệu sau đó.

## 2. Tình huống: chỉ có ID, chưa có domain object

Giả sử client gọi:

~~~text
GET /api/documents/42
Authorization: Basic ... hoặc Bearer ...
~~~

Controller nhận `42` qua đường dẫn và chuyển tới service. Tại thời điểm **trước khi method chạy**, ứng dụng có thể chưa tải `Document` từ cơ sở dữ liệu. Tuy nhiên, quyền xem có thể phụ thuộc vào ACL, chủ sở hữu, tenant và danh sách chia sẻ của chính document ID 42.

Thay vì gọi service và chỉ kiểm tra kết quả sau đó, ta có thể viết:

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document readDocument(Long id) {
    return documentStore.find(id).orElseThrow();
}
~~~

`#p0` là tham số đầu tiên của method được bảo vệ, tức `id`. `'Document'` là **khóa kiểu tài nguyên do ứng dụng quy ước**. `'read'` là quyền được yêu cầu. Spring Security lấy `Authentication` trong security context và gọi `PermissionEvaluator` đã được đăng ký; evaluator quyết định có cho phép hoặc từ chối **trước khi thân method chạy**.

Nếu evaluator từ chối, lời gọi method bị chặn. Trong web request thông thường, lỗi quyền của người đã xác thực thường được biểu diễn thành HTTP 403; với tài nguyên muốn ẩn sự tồn tại, ứng dụng có thể thiết kế chính sách trả 404 nhất quán. Không suy luận rằng mọi `hasPermission` false đều tự trở thành 404.

## 3. Hai biểu thức tương ứng hai overload

### 3.1. Biểu thức nhận object có sẵn

~~~java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document inspectLoadedDocument(Document document) {
    return document;
}
~~~

Biểu thức **hai tham số** có dạng:

~~~text
hasPermission(targetDomainObject, permission)
~~~

và ánh xạ tới interface:

~~~java
boolean hasPermission(Authentication authentication,
                      Object targetDomainObject,
                      Object permission);
~~~

Phù hợp khi caller đã có một domain object **đáng tin**. Nếu đối tượng được tạo từ JSON client, các trường `owner` và `tenant` có thể bị giả mạo; evaluator phải tải lại bản ghi đáng tin hoặc dùng một cơ chế xác minh khác. Đừng coi việc một object “có trường owner” là bằng chứng thuộc về người đang đăng nhập.

### 3.2. Biểu thức nhận ID, type và permission

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document readDocument(Long id) {
    return documentStore.find(id).orElseThrow();
}
~~~

Biểu thức **ba tham số** có dạng:

~~~text
hasPermission(targetId, targetType, permission)
~~~

và ánh xạ tới:

~~~java
boolean hasPermission(Authentication authentication,
                      Serializable targetId,
                      String targetType,
                      Object permission);
~~~

Interface có package `org.springframework.security.access.PermissionEvaluator`. Tham số `Authentication` được framework cung cấp; **không** thêm Authentication vào biểu thức. Khi biểu thức có ba đối số, Spring Security chuyển sang overload ID–type–permission; khi chỉ có hai đối số, chuyển sang overload object–permission.

| Trong SpEL | Trong evaluator | Vai trò |
| --- | --- | --- |
| Không truyền tường minh | `Authentication authentication` | Người dùng/authorities từ security context |
| `#p0` | `Serializable targetId` | Định danh tài nguyên, thường `Long`/`UUID`/`String` nếu implementation hỗ trợ |
| `'Document'` | `String targetType` | Phân biệt miền/kiểu đối tượng mà ID thuộc về |
| `'read'` | `Object permission` | Quyền cụ thể: đọc, sửa, xóa, duyệt... |

**Quan trọng:** `targetType` không được Spring tự biến thành một class rồi kiểm tra mọi quyền. Nó chỉ là string được evaluator hoặc ACL implementation diễn giải. Ứng dụng phải quy ước nhất quán về type, ví dụ `'Document'` hay `'com.example.Document'`, và xử lý unknown type bằng DENY.

### 3.3. Vì sao phải có targetType?

Một hệ thống có thể đồng thời có Document ID 42, Invoice ID 42, Project ID 42. Chỉ so `42` mà không có type có thể truy vấn nhầm ACL hoặc chia sẻ quyền giữa các miền không liên quan.

~~~text
(authentication=alice, targetId=42, targetType="Document", permission="read")
≠
(authentication=alice, targetId=42, targetType="Invoice",  permission="read")
~~~

Kết hợp khóa kiểu và ID theo một danh tính tài nguyên nhất quán là cần thiết; trong ứng dụng nhiều tenant, tenant cũng thường phải nằm trong **phạm vi tra cứu quyền**. Đừng dựa vào việc ID “đủ dài/ngẫu nhiên” để thay kiểm tra quyền.

## 4. Luồng đánh giá từ annotation đến PermissionEvaluator

~~~text
HTTP request hoặc caller khác
       |
       v
Spring bean proxy của DocumentService
       |
       v
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
       |
       +-- đọc #p0 từ MethodInvocation (ID dạng Long)
       +-- lấy Authentication từ SecurityContext
       +-- gọi MethodSecurityExpressionHandler
       |        |
       |        +-- PermissionEvaluator.hasPermission(
       |                authentication, id, "Document", "read")
       |             |
       |             +-- chọn policy theo type/permission
       |             +-- tra metadata/ACL/tenant đáng tin
       |             +-- GRANT hoặc DENY (boolean)
       |
       +-- false: chặn method, phát lỗi access denied
       |
       +-- true: thân readDocument(id) được thực thi
                     |
                     +-- tra resource và trả dữ liệu được phép
~~~

Vì `@PreAuthorize` chạy trước thân method khi proxy intercept thành công, evaluator phải tự tiếp cận nguồn dữ liệu cần cho quyết định (ví dụ repository hoặc ACL service). Spring không tự truyền một `Document` chưa tải vào overload nhận ID.

**Không nhầm “đánh giá permission” với “xác thực danh tính”.** Authentication và quyền cấp tính năng có thể được xác định qua filter chain, nhưng evaluator vẫn cần kiểm tra quyền đối với **đúng bản ghi**.

### 4.1. Khi nào annotation không chạy?

- Method bị gọi qua `this.readDocument(id)` từ cùng bean trong proxy mode thông thường: self-invocation không đi qua Spring proxy.
- Một object được tạo bằng `new DocumentService(...)` trong test: không phải Spring-managed proxy.
- Chưa bật `@EnableMethodSecurity`: annotation không tự kích hoạt chỉ vì đã thêm `spring-boot-starter-security`.
- Đặt evaluator bean nhưng chưa nối vào `MethodSecurityExpressionHandler` phù hợp: expression có thể dùng evaluator mặc định chặn mọi quyền.
- Cố dùng URL authorization thay cho service authorization: cùng service có thể được gọi từ job, message listener hay endpoint khác.

## 5. Chính sách của một PermissionEvaluator tốt

Một evaluator nhận cả `Authentication`, ID, type và permission nhưng phải dùng **dữ liệu đáng tin** để xác định kết quả. Ví dụ quy tắc cho `Document`:

~~~text
canReadDocument(actor, id):
  actor đã xác thực thật?
  actor có "document:read"?
  id là kiểu ID được hỗ trợ và > 0?
  type có đúng "Document"?
  permission có đúng "read"?
  bản ghi id có tồn tại trong kho tin cậy?
  actor có tenant scope hợp lệ cho bản ghi?
  actor là owner (hoặc có ACL chia sẻ hợp lệ)?
  nếu bất kỳ điều kiện bắt buộc không đạt => DENY
~~~

Trong hệ thống thật, câu hỏi về owner và ACL có thể được tách thành các policy nhỏ hơn. Cốt lõi ở đây là **không có bằng chứng quyền thì không cấp quyền**.

| Dữ liệu đầu vào/evaluator | Cách xử lý có chủ đích |
| --- | --- |
| `targetId == null` | DENY; không coi là “tất cả tài nguyên” |
| `targetId` khác kiểu canonical (ví dụ evaluator chỉ chấp nhận `Long` nhưng nhận `Integer`) | DENY hoặc chuyển đổi chặt chẽ đã thiết kế; không đoán |
| `targetType == null` hoặc không phải `Document` | DENY |
| `permission` thiếu/không nằm trong allow-list | DENY |
| Authentication không hợp lệ, thiếu authority | DENY |
| Không tìm thấy record/ACL | DENY trong permission layer; HTTP mapping được thiết kế riêng |
| Record ở tenant khác | DENY, không trả metadata nhạy cảm |
| Record thuộc đúng tenant nhưng không được cấp quyền | DENY |
| Repository lỗi kết nối | Xử lý thất bại an toàn; không bắt lỗi rồi trả true |
| Có bằng chứng quyền hợp lệ | GRANT, sau đó method vẫn tuân thủ business/transaction constraints |

Chú ý lỗi khác với kết quả permission. Nếu repository không truy cập được, code có thể phát exception để báo sự cố hệ thống; điều quan trọng là **không chuyển lỗi hạ tầng thành GRANT hoặc trả dữ liệu không kiểm soát**. Đừng trả `false` rồi che mọi lỗi như lỗi không có quyền nếu ứng dụng cần quan sát/khắc phục sự cố.

### 5.1. Permission string là giao thức nội bộ

`Object permission` có thể là string, enum hoặc đối tượng permission khác nếu evaluator hiểu. Ví dụ dưới đây **cố ý chỉ chấp nhận đúng string `"read"`**. `"READ"`, `"write"` hoặc một object có `toString() == "read"` không được tự động cho qua. Dùng allow-list chính xác và kiểm thử permission không hỗ trợ.

Nếu sử dụng Spring ACL module với `AclPermissionEvaluator` và `BasePermission`, representation và cách map permission khác ví dụ string đơn giản. Không tráo mẫu demo này với ACL bitmask khi chưa tích hợp `AclService`.

## 6. Cấu hình MethodSecurityExpressionHandler

Để Spring Security biết implementation `PermissionEvaluator` nào được dùng, expose `MethodSecurityExpressionHandler` và gọi `setPermissionEvaluator`. Mẫu chuẩn dùng `static @Bean` giúp handler được đăng ký sớm trước khi method-security configuration khởi tạo:

~~~java
// Trích đoạn trong @Configuration có @EnableMethodSecurity.
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        PermissionEvaluator permissionEvaluator) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(permissionEvaluator);
    return handler;
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
~~~

Spring Security không yêu cầu dùng ACL module để tự triển khai `PermissionEvaluator`. Bạn có thể dùng repository/ACL của ứng dụng; lúc đó chính code của bạn chịu trách nhiệm chuẩn hóa type, ID và permission.

Trường hợp triển khai ACL thật, Spring Security có `AclPermissionEvaluator` phối hợp với `AclService`; cần dependency/schema/cấu hình riêng. Chỉ gọi `hasPermission(...)` **không tự tạo ACL table**, không tự load và kiểm tra mọi owner.

## 7. Ví dụ Spring Boot đầy đủ: kiểm tra theo ID, type và permission

Ví dụ dùng repository trong bộ nhớ để minh họa một policy có thể kiểm thử. Document có ID, tenant và owner; người dùng muốn xem phải đồng thời có authority `document:read`, quyền ở tenant và là owner. Với production, dùng stable principal/tenant claim đã xác minh, policy ACL/owner thực tế và repository query áp tenant.

Cấu trúc hai file:

~~~text
src/main/java/demo/permission/PermissionDemoApplication.java
src/test/java/demo/permission/PermissionDemoApplicationTest.java
~~~

### 7.1. Ứng dụng Spring Boot

Lưu nội dung sau thành `src/main/java/demo/permission/PermissionDemoApplication.java` trong một dự án Spring Boot Servlet (Java 17+) có dependency `spring-boot-starter-web` và `spring-boot-starter-security`. File chứa một public application class và các kiểu package-private cùng package:

~~~java
package demo.permission;

import java.io.Serializable;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionDemoApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                         "/api/documents/*")
                            .hasAuthority("document:read")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo")
                        .authorities("document:read", "tenant:alpha")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}demo")
                        .authorities("document:read", "tenant:beta")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}demo")
                        .authorities("tenant:alpha")
                        .build());
        // {noop} CHỈ dành cho demo; production dùng encoder an toàn.
    }
}

record Document(long id, String tenant, String owner, String title) {
}

@Component
class DocumentStore {
    private final Map<Long, Document> data = Map.of(
            1L, new Document(1L, "alpha", "alice", "Plan A"),
            2L, new Document(2L, "beta",  "bob",   "Plan B"),
            3L, new Document(3L, "alpha", "alice", "Plan C")
    );

    Optional<Document> find(Long id) {
        return Optional.ofNullable(data.get(id));
    }
}

@Component
class DocumentPermissionEvaluator implements PermissionEvaluator {
    private final DocumentStore store;

    DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(Authentication authentication,
                                 Object targetDomainObject,
                                 Object permission) {
        // Không tin owner/tenant của object caller cung cấp.
        // Re-check đối tượng lưu trữ theo ID thật.
        if (!(targetDomainObject instanceof Document doc)) {
            return false;
        }
        return store.find(doc.id())
                .map(saved -> isAllowed(authentication, saved, permission))
                .orElse(false);
    }

    @Override
    public boolean hasPermission(Authentication authentication,
                                 Serializable targetId,
                                 String targetType,
                                 Object permission) {
        // "Document" là tên type do ứng dụng định nghĩa.
        // Chỉ chấp nhận Long đã được binding/canonicalize đúng.
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id) || id <= 0) {
            return false;
        }
        return store.find(id)
                .map(saved -> isAllowed(authentication, saved, permission))
                .orElse(false);
    }

    private boolean isAllowed(Authentication authentication,
                              Document document, Object permission) {
        if (authentication == null || !authentication.isAuthenticated()
                || !("read".equals(permission))) {
            return false;
        }

        boolean hasReadAuthority = authentication.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));
        boolean inTenant = authentication.getAuthorities().stream()
                .anyMatch(a -> ("tenant:" + document.tenant())
                        .equals(a.getAuthority()));
        boolean isOwner = document.owner().equals(authentication.getName());

        return hasReadAuthority && inTenant && isOwner;
    }
}

@Service
class DocumentService {
    private final DocumentStore store;

    DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasAuthority('document:read') and "
            + "hasPermission(#p0, 'Document', 'read')")
    public Document readDocument(Long id) {
        return store.find(id).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    // Cùng evaluator, lần này đi qua overload nhận object.
    @PreAuthorize("hasPermission(#p0, 'read')")
    public Document readAlreadyLoaded(Document candidate) {
        // Không trả dữ liệu candidate do caller tự cấu tạo.
        return store.find(candidate.id()).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Document get(@PathVariable Long id) {
        return service.readDocument(id);
    }
}
~~~

**Lưu ý để tránh hiểu sai:**

- `@PreAuthorize` chạy trên `DocumentService` qua Spring proxy. Controller và evaluator là các bean khác nên lời gọi HTTP→service đi qua proxy.
- `#p0` ổn định cho tham số đầu tiên, không cần biên dịch Java với `-parameters`. Với tên `#id`, phải bảo đảm cách khám phá tên tham số tương thích.
- `DocumentPermissionEvaluator` xử lý **cả hai overload**. Nếu chỉ viết overload object rồi gọi biểu thức ba tham số, Java sẽ không có implementation đầy đủ; hoặc bạn có thể viết overload ID luôn trả false nhưng khi đó biểu thức ba tham số luôn từ chối.
- In-memory data chỉ minh họa. Việc kiểm tra object overload bằng cách tải lại từ store ngăn caller giả owner/tenant trong một object tự tạo. Với object thật đã được tải từ repository và đáng tin, evaluator có thể tránh lookup lặp tùy threat model.
- `readDocument` có một lần lookup trong evaluator và một lần trong thân service. Với DB, cân nhắc query kết hợp quyền/dữ liệu hoặc transaction/locking phù hợp để không tốn hai lần truy vấn và tránh race.
- Endpoint GET ở demo vẫn không phải API cấp tài nguyên đa tenant hoàn chỉnh: kiểm tra quyền trong service và scope của repository là cần thiết cho mọi đường truy cập.

### 7.2. Dependency cần có

Khối sau là trích đoạn `build.gradle` của một dự án **đã có Spring Boot Gradle plugin, dependency management và Java 17+**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không thể chỉ copy khối trên rồi chạy như file `build.gradle` hoàn chỉnh. Khi dự án đã được tạo bằng Spring Initializr, có thể dùng `./gradlew bootRun` trên Unix hoặc `gradlew.bat bootRun` trên Windows.

### 7.3. Gọi endpoint

Giả sử ứng dụng chạy ở `localhost:8080`:

~~~bash
curl -i -u alice:demo http://localhost:8080/api/documents/1
curl -i -u alice:demo http://localhost:8080/api/documents/2
curl -i -u bob:demo http://localhost:8080/api/documents/2
curl -i -u viewer:demo http://localhost:8080/api/documents/1
curl -i http://localhost:8080/api/documents/1
~~~

Kỳ vọng trong cấu hình HTTP Basic mẫu:

| Request | URL permission | ID/type/permission evaluator | Kết quả |
| --- | --- | --- | --- |
| Alice xem ID 1 | Alice có `document:read` | Owner Alice, tenant alpha, permission read | HTTP 200, JSON Document 1 |
| Alice xem ID 2 | Qua URL | Owner Bob, tenant beta → DENY | HTTP 403 |
| Bob xem ID 2 | Qua URL | Owner Bob, tenant beta → GRANT | HTTP 200, JSON Document 2 |
| Viewer xem ID 1 | Thiếu `document:read` | Method chưa được gọi | HTTP 403 |
| Anonymous xem ID 1 | Chưa xác thực | Method chưa được gọi | Thông thường HTTP 401 với Basic |
| Alice xem ID 999 | Qua URL | Bản ghi không tồn tại → false | HTTP 403 do `@PreAuthorize` trong demo |

Dòng cuối là chủ ý: trong example `readDocument(999)`, evaluator trả false trước khi thân method có thể phát 404. Đừng nhầm nó với cam kết mọi ứng dụng phải trả 403 cho resource không tồn tại. Với API cần che giấu sự tồn tại, nên thiết kế 404 đồng nhất bằng policy ở tầng có đủ ngữ cảnh và kiểm thử cả “không tồn tại” lẫn “tồn tại nhưng trái quyền”.

## 8. Integration test kiểm chứng đúng overload

Đặt test dưới `src/test/java/demo/permission/PermissionDemoApplicationTest.java`:

~~~java
package demo.permission;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionDemoApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentService service;

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void aliceReadsOwnDocumentById() throws Exception {
        mvc.perform(get("/api/documents/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void aliceCannotReadBobDocument() throws Exception {
        mvc.perform(get("/api/documents/2"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob",
                  authorities = {"document:read", "tenant:beta"})
    void bobReadsOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    @WithMockUser(username = "viewer",
                  authorities = {"tenant:alpha"})
    void featureAuthorityIsRequired() throws Exception {
        mvc.perform(get("/api/documents/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void forgedLoadedObjectIsDenied() {
        Document forged = new Document(
                2L, "alpha", "alice", "Forged");
        assertThrows(AccessDeniedException.class,
                () -> service.readAlreadyLoaded(forged));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void unknownDocumentIdIsDeniedBeforeMethodBody() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isForbidden());
    }
}
~~~

Test trên kiểm tra:
- Method security hoạt động thực qua Spring bean/proxy.
- Overload `hasPermission(#p0, 'Document', 'read')` dùng ID và type.
- Overload `hasPermission(#p0, 'read')` không bị đánh lừa bởi object có owner giả.
- Hợp đồng URL + quyền cấp tài nguyên và lỗi “không tồn tại” của demo.
- Kết quả HTTP từ `MockMvc`; unit test service có thể bắt `AccessDeniedException` thay vì mã 403.

Các test cần dependency `spring-security-test`, Spring Boot Test, Spring Web, Spring Security. Với Spring Boot 4, một số dependency hoặc package MockMvc auto-configuration có thể khác; ví dụ này bám vào Spring Boot 3.x/Spring Security 6.x để có đường chạy rõ. Khi nâng version, giữ nguyên bài test hành vi thay vì giả định tên package không đổi.

### 8.1. Unit test trực tiếp evaluator cho các trường hợp dữ liệu bẩn

Bên cạnh integration test, nên có test không qua web cho `DocumentPermissionEvaluator`:

| Input | Kỳ vọng |
| --- | --- |
| Alice, `1L`, `"Document"`, `"read"` | true |
| Alice, `2L`, `"Document"`, `"read"` | false |
| Alice, `1L`, `"Invoice"`, `"read"` | false |
| Alice, `Integer.valueOf(1)`, `"Document"`, `"read"` | false vì demo chỉ chấp nhận Long |
| Alice, `1L`, `"Document"`, `"write"` | false |
| Alice, `null` ID hoặc permission | false theo policy/null-handling đã thiết kế |
| Principal mất authority `document:read` | false |
| Principal thiếu tenant alpha | false |
| Document bị xóa/chuyển tenant giữa check và read | Không trả dữ liệu trái quyền; yêu cầu bảo vệ tại điểm đọc/ghi |
| Database hỏng/timeout | Fail closed/exception có log, không cho phép vì lỗi |

Đặc biệt với ID `String` do API truyền vào, hãy quyết định **convert trước khi gọi expression** (controller binding sang Long) hay hỗ trợ string canonical trong evaluator. Không tự `String.valueOf` mọi Object rồi thử khớp ID vì có thể tạo collision hoặc bỏ qua validation.

## 9. Java 17 độc lập: giải thích ý nghĩa ba tham số

Ví dụ này không yêu cầu Spring; nó mô phỏng policy `Authentication + ID + type + permission` để kiểm chứng các trường hợp GRANT/DENY bằng JDK thuần. Lưu thành `PermissionIdDemo.java`:

~~~java
import java.io.Serializable;
import java.util.Map;
import java.util.Set;

public class PermissionIdDemo {
    record Actor(String name, String tenant, Set<String> permissions) {}
    record Doc(long id, String tenant, String owner) {}

    static final Map<Long, Doc> DOCUMENTS = Map.of(
            1L, new Doc(1L, "alpha", "alice"),
            2L, new Doc(2L, "beta", "bob"));

    static boolean hasPermission(Actor actor, Serializable targetId,
                                 String targetType, Object permission) {
        if (actor == null || !(targetId instanceof Long id)
                || !"Document".equals(targetType)
                || !"read".equals(permission)
                || !actor.permissions().contains("document:read")) {
            return false;
        }

        Doc doc = DOCUMENTS.get(id);
        return doc != null
                && doc.tenant().equals(actor.tenant())
                && doc.owner().equals(actor.name());
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "alpha",
                Set.of("document:read"));
        Actor bob = new Actor("bob", "beta",
                Set.of("document:read"));

        System.out.println("alice-id1=" +
                hasPermission(alice, 1L, "Document", "read"));
        System.out.println("alice-id2=" +
                hasPermission(alice, 2L, "Document", "read"));
        System.out.println("bob-id2=" +
                hasPermission(bob, 2L, "Document", "read"));
        System.out.println("wrong-type=" +
                hasPermission(alice, 1L, "Invoice", "read"));
        System.out.println("wrong-permission=" +
                hasPermission(alice, 1L, "Document", "write"));
        System.out.println("wrong-id-type=" +
                hasPermission(alice, Integer.valueOf(1), "Document", "read"));
        System.out.println("missing-id=" +
                hasPermission(alice, 999L, "Document", "read"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PermissionIdDemo.java
java PermissionIdDemo
~~~

**stdout chính xác:**

~~~text
alice-id1=true
alice-id2=false
bob-id2=true
wrong-type=false
wrong-permission=false
wrong-id-type=false
missing-id=false
~~~

Cơ chế chính: cùng ID nhưng sai **targetType**, sai **permission** hoặc sai loại dữ liệu ID đều bị từ chối trước hoặc trong lúc tra cứu; authority cấp chức năng không đủ thay quyền trên đối tượng. Đây là mô hình minh họa **không phải** implementation `PermissionEvaluator` của Spring, nhưng kiểm tra được ý nghĩa các tham số một cách độc lập.

## 10. Các trường hợp đặc biệt của overload ID

### 10.1. targetId bắt buộc Serializable

Java signature nhận `Serializable`: `Long`, `String`, `UUID` triển khai Serializable; một custom ID class cần đáp ứng và có quy tắc equality/serialization thích hợp. Trong SpEL, hàm `hasPermission(targetId, targetType, permission)` nhận Object rồi chuyển tiếp theo contract của framework; không giả định mọi Object bất kỳ có thể ép sang `Serializable` thành công.

Một số lỗi diễn giải:
- `1L` trong Java là Long khi boxing, còn `1` là Integer. Evaluator mẫu chỉ chấp nhận Long nên `Integer(1)` bị từ chối.
- `@PathVariable Long id` đưa type rõ cho method. Nếu nhận `String id`, convert chặt chẽ và xử lý lỗi 400 trước khi check quyền.
- Nếu một ID là UUID, đổi evaluator sang `UUID` đồng nhất giữa controller, repository, ACL; đừng chuyển thành String tùy chỗ.
- Nếu domain có composite key, tạo kiểu ID rõ ràng hoặc biểu thức/policy khác; không ghép chuỗi bằng cách có thể va chạm.

### 10.2. targetType không phải “phép đổi class” mặc định

`'Document'` chỉ là một chuỗi. Nếu Spring ACL được cấu hình theo tên lớp đầy đủ như `com.example.domain.Document`, việc truyền `'Document'` có thể không khớp ACL. Nếu custom evaluator của bạn chấp nhận `'Document'` thì nó hoạt động, nhưng **phải dùng cùng một quy ước ở tất cả nơi gọi**.

Không bao giờ biến `targetType` từ request thành một câu lệnh `Class.forName`, table name SQL hay type resolver không giới hạn. Với API public, chọn type theo route/server policy thay vì tin client cung cấp arbitrary type. Dùng allow-list để chống bypass, confused deputy hoặc dữ liệu sai miền.

### 10.3. permission là Object, không phải authority của user

`'read'` nói **hành động mong muốn trên Document ID X**. Nó không nhất thiết là GrantedAuthority `document:read`; evaluator có thể dùng một authority tổng quát *và* ACL per-resource. Ví dụ:

~~~text
GrantedAuthority "document:read"      -> có quyền sử dụng tính năng
PermissionEvaluator("Document", 42, "read")
                                       -> có quyền đối với bản ghi 42
~~~

Một người có thể có authority đọc tài liệu nhưng không có quyền đối với tài liệu của tenant khác. Ngược lại, một record ACL cấp quyền đọc không thay thế mọi yêu cầu xác thực, khóa tài khoản hoặc chính sách cấp tính năng.

### 10.4. Không tồn tại và không có quyền

`hasPermission(... ) == false` khi ACL/record không tồn tại là lựa chọn dễ bảo vệ. Tuy nhiên nếu code trả 403 cho tài nguyên không tồn tại và 404 cho tài nguyên có nhưng không được xem, người gọi có thể dò sự tồn tại bằng phản hồi khác nhau. Đặt chính sách phân biệt/che giấu tài nguyên ở nơi có đủ ngữ cảnh và kiểm thử response code nhất quán. Không rò rỉ title, owner, tenant hay trạng thái qua thông điệp của evaluator.

### 10.5. Quyền có thể thay đổi giữa check và thực thi

Khi evaluator tải Document ID 42 để check quyền rồi service đọc lại, một transaction khác có thể đổi owner/tenant hoặc thu hồi ACL. `@PreAuthorize` không tạo transaction tự động, không đóng băng dữ liệu và không bảo đảm kết quả cũ còn đúng.

Với thao tác chỉ đọc, có thể áp tenant/owner predicate trong query để bảo đảm phạm vi dữ liệu ngay lúc truy vấn. Với thao tác ghi, kiểm tra quyền bên trong transaction gắn với update, dùng optimistic/pessimistic locking hoặc conditional update và kiểm tra số dòng cập nhật; chọn isolation phù hợp. Không đặt duy nhất rào chắn ở controller rồi bỏ qua data layer.

### 10.6. N+1 query và permission check theo danh sách

Nếu dùng:

~~~java
@PostFilter("hasPermission(filterObject.id(), 'Document', 'read')")
public List<Document> listAll() {
    return repository.findAll();
}
~~~

evaluator có thể truy vấn ACL **mỗi phần tử**, gây N+1 và tải dữ liệu không thuộc quyền vào memory trước khi lọc. Với số lượng lớn, dùng query có scope tenant/owner/ACL ngay trong DB, batch ACL lookup hoặc hệ thống row-level security; dùng `@PostFilter` như lớp bảo vệ bổ sung khi hợp đồng phù hợp. Pagination và tổng số record có thể sai nếu lọc sau khi lấy page.

### 10.7. Khi muốn dùng AclPermissionEvaluator của Spring

Spring Security ACL module hiện thực hóa `PermissionEvaluator` với `AclService`, ACL entries và object identity. Nó là một giải pháp riêng cho per-object permission phức tạp; cần dependency `spring-security-acl`, schema ACL, cấu hình service/cache/permission factory phù hợp.

Custom evaluator in-memory của bài này **không có ACL inheritance**, không có bitmask `BasePermission`, không có persistence, audit hoặc tenant routing ngoài những gì code viết. Đừng hiểu rằng chỉ cần cài `AclPermissionEvaluator` rồi không chuẩn bị dữ liệu ACL là permission check sẽ tự biết owner của entity.

## 11. Chọn giữa @PreAuthorize và @PostAuthorize khi cần target object

### 11.1. Dùng ID trước lời gọi

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document loadById(Long id) {
    // Chỉ vào method nếu evaluator cho phép.
}
~~~

Phù hợp nếu ID đủ để tra metadata/ACL và bạn muốn chặn truy cập trước khi service load/trả tài nguyên. Nếu evaluator và service cùng query DB, có thêm chi phí; cân nhắc policy query hoặc transaction để tránh race.

### 11.2. Dùng object sau lời gọi

~~~java
@PostAuthorize("hasPermission(returnObject, 'read')")
public Document loadThenCheck(Long id) {
    return store.find(id).orElseThrow();
}
~~~

Ở đây body chạy trước, sau đó evaluator nhận `returnObject`. Có thể thuận tiện nếu quyền phụ thuộc vào thuộc tính object đã tải. Nhưng body đã chạy, và nếu body ghi DB hoặc gửi event thì hậu kiểm không tự hoàn tác mọi side effect. Với mutation, ưu tiên tiền kiểm và authorization gần điểm ghi.

### 11.3. Không dùng nhầm overload

~~~java
// Một target object, hai đối số:
@PreAuthorize("hasPermission(#p0, 'read')")

// Một ID, ba đối số:
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
~~~

Nếu ID `Long` bị truyền vào overload **object** với hai đối số, evaluator có thể nhận `Long` như một targetDomainObject chứ không có type rõ ràng; custom evaluator ở trên chỉ hỗ trợ object `Document` và sẽ trả false. Đây không phải lỗi của Spring mà do viết sai biến thể expression.

## 12. Lỗi phổ biến và cách sửa

### Lỗi 1 — Viết ba tham số nhưng chỉ implement overload object

Interface yêu cầu hai method; nếu overload ID luôn trả false hoặc chưa được đăng ký, mọi request qua `hasPermission(id, type, permission)` bị deny. Implement đầy đủ hai overload theo hợp đồng hoặc cố ý tách hỗ trợ, có test đảm bảo expression thực sự gọi nhánh ID.

### Lỗi 2 — Nhầm targetType với class resolver tự động

`"Document"` là literal do app quyết định. Spring không tự biến nó thành entity và tra owner; evaluator/ACL resolver mới làm việc đó. Dùng allow-list và quy tắc type thống nhất.

### Lỗi 3 — Coi ID đoán khó là quyền truy cập

Đoán được UUID không có nghĩa được phép xem resource. Kiểm tra principal, tenant, owner/ACL và permission ở tầng đáng tin; không dựa vào entropy của ID làm security model duy nhất.

### Lỗi 4 — Lấy tenant từ header và tin ngay

Client có thể gửi `X-Tenant: victim`. So tenant selector với tenant đáng tin của principal và record; giới hạn repository query theo tenant, tránh lộ dữ liệu cross-tenant.

### Lỗi 5 — Chuyển mọi lỗi thành true để “không chặn nghiệp vụ”

Một timeout ACL/DB phải không dẫn đến GRANT. Xử lý lỗi quan sát được và fail closed theo threat model; không nuốt exception rồi trả true hoặc fallback admin.

### Lỗi 6 — Không xử lý null và kiểu ID

`targetId` null hoặc `Integer` thay vì `Long` cần bị từ chối hoặc chuẩn hóa hợp lệ. Không ép kiểu mù gây `ClassCastException` không có thông điệp hoặc vô tình so trùng tài nguyên khác.

### Lỗi 7 — Object overload tin dữ liệu client

`hasPermission(candidate, 'read')` mà chỉ nhìn `candidate.owner == authentication.name` dễ bị giả owner. Kiểm tra target đến từ kho dữ liệu đáng tin hoặc dùng ID overload + retrieval trong evaluator.

### Lỗi 8 — Cho phép dựa trên authority tính năng mà bỏ ACL tài nguyên

`hasAuthority('document:read')` không chứng minh người dùng được xem tất cả document. Kết hợp authority với quyền per-resource hoặc thiết kế query scope/ACL rõ.

### Lỗi 9 — Quên @EnableMethodSecurity hoặc gọi self-invocation

Test `new Service` hay `this.securedMethod()` có thể bỏ qua proxy. Đảm bảo gọi bean qua Spring và test trường hợp DENY để phát hiện annotation không hoạt động.

### Lỗi 10 — Đọc/ghi sau check mà quên race/transaction

Permission đúng ở thời điểm t1 nhưng owner/tenant thay đổi ở t2; method vẫn sử dụng dữ liệu t2. Kiểm tra tại điểm truy cập/ghi cùng ranh giới transaction hoặc query điều kiện và locking.

### Lỗi 11 — Trả status hoặc chi tiết lỗi không nhất quán

“Không có quyền” thường là 403, “chưa xác thực” thường là 401, “ẩn existence” có thể là 404, nhưng method security tự nó không hứa mọi response đều như nhau. Thiết kế exception handling và test HTTP để tránh enumeration.

### Lỗi 12 — Dùng @PostFilter hàng nghìn phần tử thay query đúng scope

Điều kiện `hasPermission` theo mỗi phần tử có thể gây N+1 query, sai total/pagination và tăng tải. Thực hiện scope/filter ở truy vấn DB, batch ACL checks và dùng post-filter khi kích thước hợp lý.

## 13. Checklist kiểm thử thực tế

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| User có authority, tenant, owner, permission read | Cho phép đúng document |
| User thiếu authority | DENY, dù owner trùng |
| User có authority nhưng tenant khác | DENY |
| User có authority và tenant nhưng owner khác | DENY |
| Target type sai | DENY |
| Permission sai hoặc chưa hỗ trợ | DENY |
| ID null / sai kiểu / không tồn tại | DENY hoặc lỗi đầu vào được kiểm soát |
| Domain object giả owner | DENY nếu dữ liệu lưu trữ không xác nhận |
| Không cấu hình evaluator thực | Test DENY/GRANT giúp phát hiện đường gọi sai |
| User gọi service qua bean proxy | Annotation thực sự được thi hành |
| Method được self-invoke | Phát hiện rủi ro bypass, tái cấu trúc |
| ACL hoặc tenant thay đổi đồng thời | Không trả/ghi dữ liệu ngoài quyền theo chính sách transaction |
| Tập danh sách lớn | Không có N+1/over-fetch hoặc pagination thiếu dữ liệu |
| Lỗi database/ACL provider | Fail closed, có monitoring, không lộ dữ liệu |

**Bài tập:** Alice có authority `document:read` và tenant alpha. Document ID 42 nằm tenant beta. `@PreAuthorize("hasPermission(#id, 'Document', 'read')")` có nên trả true nếu Alice biết chính xác ID 42?

**Đáp án:** Không. Tính hợp lệ của ID không phải quyền. Evaluator phải đọc owner/tenant/ACL từ dữ liệu đáng tin và deny khi Alice không thuộc scope. Nếu cần ẩn tài nguyên, API phải thiết kế response 403/404 nhất quán, không đưa metadata của document 42 vào thông báo lỗi.

**Bài tập nâng cao:** Alice xem một Document ID 1 hợp lệ qua evaluator, nhưng ACL bị thu hồi ngay trước khi service đọc lại. Chỉ có `@PreAuthorize` có đủ không?

**Đáp án:** Không bảo đảm khi dữ liệu thay đổi giữa check và use. Cần bảo vệ quyền tại nơi đọc/ghi thật hoặc trong transaction với scope/locking và chính sách nhất quán, đặc biệt với thao tác cập nhật/xóa.

## 14. Tóm tắt kỹ thuật

Biểu thức ba tham số `hasPermission(targetId, targetType, permission)` giúp diễn đạt quyền trên một tài nguyên **chưa tải** bằng ID cùng một tên type được ứng dụng/ACL quy ước. Spring gọi `PermissionEvaluator.hasPermission(Authentication, Serializable, String, Object)`; evaluator phải kiểm tra danh tính, resource scope, ACL và hành động trên dữ liệu đáng tin, rồi trả true/false có chủ đích.

Biểu thức hai tham số `hasPermission(targetObject, permission)` dùng overload nhận object, nhưng chỉ an toàn khi object đã được tin cậy hoặc được xác minh lại. Cả hai đều phụ thuộc vào `MethodSecurityExpressionHandler`, Spring proxy và việc bật `@EnableMethodSecurity`. Quan trọng nhất: **ID + type + permission chỉ là yêu cầu kiểm tra quyền; không phải bằng chứng quyền đã được cấp**.

## Tài liệu chính thức

- [Spring Security API – PermissionEvaluator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): hai overload, kiểu tham số `Serializable targetId` và `targetDomainObject`, ngữ nghĩa quyền.
- [Spring Security API – SecurityExpressionOperations](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/SecurityExpressionOperations.html): `hasPermission(target, permission)` và `hasPermission(targetId, targetType, permission)`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, Spring AOP và tùy biến expression.
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ví dụ `AclPermissionEvaluator`, `AclService`, ACL records và `MethodSecurityExpressionHandler` dạng `static @Bean`.
- [DefaultMethodSecurityExpressionHandler Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html): expression handler cho method security.
