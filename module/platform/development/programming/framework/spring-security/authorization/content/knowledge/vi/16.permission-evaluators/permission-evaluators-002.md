# Hợp đồng `PermissionEvaluator` và ngữ cảnh `Authentication` trong Spring Security

## 1. `hasPermission` kiểm tra điều gì?

Hệ thống Spring Security có thể kiểm tra quyền tổng quát bằng `hasAuthority('document:read')`. Tuy nhiên, authority đó chỉ nói rằng người dùng **có năng lực đọc tài liệu nói chung**; nó chưa trả lời người này có được đọc **tài liệu số 11** hay không.

Giả sử:

- `alice` có authority `document:read` và sở hữu tài liệu `11`.
- `bob` cũng có authority `document:read` nhưng sở hữu tài liệu `12`.
- `carol` sở hữu tài liệu `13`, song không được cấp authority `document:read`.
- Người dùng có thể gửi ID hoặc cả một đối tượng/DTO từ client; dữ liệu `owner` do client gửi có thể bị sửa.

Muốn kiểm tra quyền theo từng tài nguyên, Method Security cung cấp biểu thức `hasPermission(...)`. Biểu thức **ủy quyền quyết định** cho một `PermissionEvaluator`. Evaluator nhận **danh tính đã được xác thực** và **tài nguyên/quyền** từ expression system rồi trả `true` hoặc `false`.

Điểm mấu chốt của bài này là **hợp đồng API của `PermissionEvaluator` và cách truyền `Authentication` chính xác**, không chỉ cách viết annotation. Ta sẽ hiểu nguồn gốc của từng đối số, xử lý các kiểu principal, trường hợp `anonymous`, trường hợp target `null`, cách đăng ký evaluator và kiểm thử qua Spring proxy.

Sau bài học, bạn có thể:

1. Viết đúng **hai overload** của `PermissionEvaluator`.
2. Giải thích vì sao `Authentication` có trong Java interface nhưng không viết trong đối số của `hasPermission(...)` trong SpEL.
3. Phân biệt `getName()`, `getPrincipal()`, `getAuthorities()` và `isAuthenticated()`.
4. Kết nối evaluator với `DefaultMethodSecurityExpressionHandler` bằng Spring bean.
5. Cài đặt quyết định quyền theo dữ liệu server, **không tin** `owner`/`tenant` trong DTO từ client.
6. Xử lý `null`, user ẩn danh, ID/loại tài nguyên sai và quyền không được hỗ trợ bằng nguyên tắc **fail closed**.
7. Viết một chương trình Java 17+ / Spring Boot độc lập và test kiểm chứng quyền theo object lẫn ID.

**Phạm vi:** Spring Security 6.x trên Spring Boot 3.x, áp dụng Spring Method Security và Spring AOP proxy. Cơ chế ACL là một lựa chọn cung cấp evaluator, nhưng **không bắt buộc** để triển khai interface này.

## 2. `PermissionEvaluator` là hợp đồng, không phải cơ sở dữ liệu phân quyền

Interface nằm tại `org.springframework.security.access.PermissionEvaluator`. Trong Spring Security 6.x, hai phương thức cốt lõi là:

```java
public interface PermissionEvaluator {

    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        java.io.Serializable targetId,
        String targetType,
        Object permission
    );
}
```

Đoạn trên trình bày **chữ ký hợp đồng rút gọn** để học, không phải file nguồn của Spring Security; khi implement cần `import` đúng interface có sẵn trong thư viện.

| Đối số | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `authentication` | `Authentication` | Danh tính đang được Spring Security sử dụng để xét quyền |
| `targetDomainObject` | `Object` | Đối tượng đích đang có sẵn (có thể `null`) |
| `targetId` | `Serializable` | ID của đối tượng khi không có instance để truyền trực tiếp |
| `targetType` | `String` | Loại domain object: tên lớp hoặc bí danh nhất quán do evaluator/ACL hiểu |
| `permission` | `Object` | Biểu diễn quyền (`"read"`, `"write"`, enum, mask…), phụ thuộc hợp đồng ứng dụng |
| Giá trị trả về | `boolean` | `true`: cho phép; `false`: từ chối |

**Những cam kết cần tôn trọng:**

- Hợp đồng thông thường kỳ vọng `authentication` đã được cung cấp và **không phải `null`**; một evaluator phòng vệ vẫn nên từ chối khi gặp đầu vào bất thường.
- Với overload nhận object, `targetDomainObject` **có thể `null`** và implementation **nên trả `false`**; ứng dụng có thể kiểm tra null tường minh trong SpEL nếu muốn.
- `permission` được truyền **nguyên dạng từ biểu thức**. Nếu biểu thức truyền chuỗi `'read'`, evaluator nhận `String "read"`; nếu truyền một enum/object, evaluator sẽ nhận kiểu tương ứng. Không tự giả định mọi permission là `String` nếu policy hỗ trợ nhiều kiểu.
- Với overload nhận ID, **`targetType` là chuỗi quy ước**: Spring không tự đi tìm entity/repository từ một tên bất kỳ. Nếu dùng ACL, chuỗi này cần phù hợp cơ chế tạo `ObjectIdentity` của ACL.
- Interface **không tự triển khai** rule quyền, không đọc database và không bảo đảm bản ghi được bảo vệ sau lúc trả `true`. Nguồn policy và cách xử lý concurrency vẫn thuộc ứng dụng.

### 2.1. Hai cách gọi SpEL ánh xạ tới hai chữ ký Java

**Cách 1 — có object:**

```java
@PreAuthorize("hasPermission(#document, 'read')")
public String readByObject(@P("document") Document document) {
    // Chỉ chạy sau khi evaluator cho phép.
    return store.require(document.id()).content();
}
```

Thực chất Spring gọi chữ ký:

```text
hasPermission(
    Authentication hiện tại,
    document,
    "read"
)
```

**Cách 2 — chỉ có ID và loại tài nguyên:**

```java
@PreAuthorize("hasPermission(#id, 'Document', 'read')")
public String readById(@P("id") Long id) {
    // Chỉ chạy sau khi evaluator cho phép.
    return store.require(id).content();
}
```

Spring gọi:

```text
hasPermission(
    Authentication hiện tại,
    id,
    "Document",
    "read"
)
```

Hai đoạn Java annotation trên là **mảnh minh họa**, giả định có `Document`, `store` và `@P` như chương trình đầy đủ ở mục 7.

**Không có đối số `authentication` trong `hasPermission(...)` của SpEL.** Expression root của Method Security lấy `Authentication` từ ngữ cảnh bảo mật của lời gọi, rồi truyền nó vào `PermissionEvaluator` như đối số thứ nhất. Bạn không cần yêu cầu controller gửi `Authentication` trong request body.

### 2.2. Khác gì `hasAuthority`, `hasRole` và `hasPermission`?

| Biểu thức | Câu hỏi | Nguồn quyết định |
| --- | --- | --- |
| `hasAuthority('document:read')` | Người gọi có authority chính xác này không? | `Authentication.getAuthorities()` |
| `hasRole('EDITOR')` | Người gọi có role tương ứng (thường `ROLE_EDITOR`) không? | `Authentication.getAuthorities()` + role prefix |
| `hasPermission(#doc, 'read')` | Người gọi được quyền này trên object không? | `PermissionEvaluator` và dữ liệu policy |
| `hasPermission(#id, 'Document', 'read')` | Người gọi được quyền này trên object có ID/type không? | `PermissionEvaluator` và dữ liệu policy |

Một evaluator có thể kết hợp **authority tổng quát** với **điều kiện theo đối tượng**, như ví dụ. Nhưng đừng cho rằng chữ `'read'` trong permission tự động trùng `document:read` trong `GrantedAuthority`. Việc ánh xạ là **quy tắc bạn phải tự định nghĩa**.

## 3. `Authentication` là gì và nó đến từ đâu?

`Authentication` thuộc `org.springframework.security.core.Authentication`, kế thừa `Principal` và `Serializable`. Nó mô tả một yêu cầu xác thực hoặc một principal đã được xác thực. Sau khi cơ chế xác thực hợp lệ xử lý, token thường được đặt vào `SecurityContext`, được truy cập thông qua `SecurityContextHolder`.

Sơ đồ trong ứng dụng Servlet thông thường:

```text
HTTP request
   |
   v
Spring Security filter chain
   |-- xác thực session / JWT / authentication provider
   |-- dựng Authentication đáng tin cậy
   v
SecurityContextHolder -> SecurityContext -> Authentication
                                          |
                                          v
                                    Method Security
                                    @PreAuthorize SpEL
                                          |
                                          v
                                      hasPermission(...)
                                          |
                                          v
                                    PermissionEvaluator
```

Nếu một scheduler hoặc message consumer gọi method được bảo vệ, **không có request HTTP vẫn có thể dùng Method Security**; nhưng nó cần một security context/identity hợp lệ do ứng dụng thiết lập theo cơ chế đáng tin cậy. Không tự coi một job là `ADMIN` nếu chưa có mô hình quyền rõ ràng.

Các API cần biết:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
Object principal = authentication.getPrincipal();
var authorities = authentication.getAuthorities();
boolean authenticated = authentication.isAuthenticated();
```

Đây là mảnh code minh họa; **kiểm tra `authentication != null` trước khi dereference**.

### 3.1. `getName()` và `getPrincipal()` không đồng nhất

- `getName()` trả tên được `Authentication` biểu diễn theo contract `Principal`. Với username/password thường là username; với JWT/OIDC có thể là subject, claim đã được cấu hình hoặc định danh khác.
- `getPrincipal()` trả một đối tượng: có thể là `UserDetails`, `Jwt`, `OAuth2User`, chuỗi username hoặc custom principal. **Không mặc định cast** principal sang `String` hoặc một lớp ứng dụng.
- `getAuthorities()` trả các `GrantedAuthority`, ví dụ `document:read`. Nó không tự chứa quyền theo từng bản ghi nếu hệ thống không ánh xạ như vậy.
- `getDetails()` chứa chi tiết xác thực bổ sung như metadata request tùy provider; **không được tự coi mọi details là danh tính/tenant đáng tin**.
- `getCredentials()` thường chứa dữ liệu bí mật hoặc bằng chứng xác thực. **Không dùng credentials làm cache key, không log**.

Trong ứng dụng nhiều tenant, nên lấy **stable internal subject ID** và tenant đã được kiểm chứng từ principal/claims hoặc repository. Không lấy `X-User`, `X-Tenant` từ request header chưa xác thực làm nguồn quyết định quyền. Nếu `getName()` không phải ID ổn định mà policy dùng, viết một adapter xác định subject đúng từ loại `Authentication` đã chọn.

### 3.2. `isAuthenticated() == true` chưa chắc là người dùng thực

Có một bẫy thường gặp:

```java
if (authentication != null && authentication.isAuthenticated()) {
    return true;
}
```

Kiểm tra trên **không đủ** để cho quyền đọc tài liệu. `AnonymousAuthenticationToken` trong Spring Security có thể báo `isAuthenticated() == true` theo contract của token, dù caller chỉ là người dùng ẩn danh.

Dùng `AuthenticationTrustResolver` để phân biệt anonymous:

```java
AuthenticationTrustResolver trustResolver =
    new AuthenticationTrustResolverImpl();

boolean realAuthenticated =
    authentication != null
    && authentication.isAuthenticated()
    && !trustResolver.isAnonymous(authentication);
```

Đây là mảnh code minh họa cần các import `org.springframework.security.authentication.AuthenticationTrustResolver` và `AuthenticationTrustResolverImpl`. Có thể có thêm chính sách phân biệt **remember-me**, xác thực gần đây hoặc MFA cho thao tác nhạy cảm. Không coi `isAuthenticated()` là bằng chứng đủ quyền đối tượng.

### 3.3. Context được quản lý theo luồng thực thi

Trong cấu hình Servlet phổ biến, `SecurityContextHolder` mặc định gắn context theo thread. Spring Security chủ động thiết lập và làm sạch nó trong luồng request. Nếu bạn chuyển công việc sang `@Async`, executor, `CompletableFuture` hoặc một thread tự tạo, authentication **không mặc nhiên được truyền theo**.

Với tác vụ async thực sự cần danh tính caller, dùng cơ chế `DelegatingSecurityContext...` hoặc cách propagation được Spring Security hỗ trợ, xác định rõ scope và thời điểm dọn context. Không dùng `MODE_INHERITABLETHREADLOCAL` như một giải pháp tổng quát cho thread pool lâu sống nếu chưa hiểu rủi ro rò rỉ identity.

Trong ví dụ dòng lệnh sau, ta tạo context tường minh và **clear trong `finally`** để tránh lưu danh tính sang tác vụ khác. Đó là cách mô phỏng trong demo, **không phải** hướng dẫn tự xác thực user thật.

## 4. Mỗi lời gọi Method Security có `Authentication` riêng

Với `@PreAuthorize`, luồng thường là:

```text
Caller -> Spring-managed service proxy
             |
             v
       @PreAuthorize interceptor
             |
             v
    Security expression evaluation
      |-- đọc MethodInvocation & tham số
      |-- lấy Supplier<Authentication>
      |-- đánh giá hasPermission(...)
             |
             v
      PermissionEvaluator
             |
       true / false
        |      |
        v      v
      body   AccessDeniedException
```

`PermissionEvaluator` thường là một **Spring singleton bean** được tái sử dụng giữa nhiều request. Vì vậy evaluator **không được lưu `Authentication` của request hiện tại vào field mutable** rồi dùng lại ở request sau: sẽ gây race và có thể lấy nhầm identity người dùng khác.

Đúng:

```java
@Override
public boolean hasPermission(
        Authentication authentication,
        Object target,
        Object permission) {
    return policy.canAccess(authentication, target, permission);
}
```

Sai về thiết kế:

```java
// Mảnh code KHÔNG NÊN DÙNG:
private Authentication currentAuthentication;

@Override
public boolean hasPermission(
        Authentication authentication,
        Object target,
        Object permission) {
    this.currentAuthentication = authentication;
    return evaluateLater(target, permission);
}
```

Nếu nhiều request đồng thời, field `currentAuthentication` bị ghi đè. Hãy giữ evaluator **stateless đối với identity của mỗi request** và truyền `Authentication` theo tham số; cache kết quả authorization nếu có phải tách theo principal/tenant/resource/action và có chiến lược invalidation khi quyền đổi.

### 4.1. `PermissionEvaluator` không phải `AuthenticationManager`

- `AuthenticationManager`/`AuthenticationProvider` giải quyết **ai đang gọi** và tạo/kiểm chứng authentication.
- `PermissionEvaluator` giải quyết **principal đã xác thực có quyền gì trên tài nguyên**.
- `AuthorizationManager` là cơ chế authorization tổng quát hiện đại, được Spring Security dùng ở request/method level. `hasPermission` là một hook trong **Method Security expression evaluation** dẫn tới `PermissionEvaluator`.
- `AclPermissionEvaluator` là một implementation tích hợp hệ thống Spring Security ACL; interface không bắt buộc bạn dùng thư viện ACL.

Không cho `PermissionEvaluator` tự kiểm tra password, làm token login hoặc dựng `UsernamePasswordAuthenticationToken` chỉ dựa trên ID client gửi. Phân chia trách nhiệm rõ làm chính sách dễ audit và test hơn.

## 5. Cách nối `PermissionEvaluator` với Method Security

Cần **hai việc riêng**:

1. Bật Method Security bằng `@EnableMethodSecurity`.
2. Đăng ký evaluator vào `MethodSecurityExpressionHandler` được dùng bởi Spring Security.

Ví dụ cấu hình:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Dùng phương thức `@Bean static` để expression handler được xuất bản **sớm** khi Spring Security khởi tạo các class cấu hình method security. Việc có một `@Component PermissionEvaluator` nhưng **chưa gắn nó vào expression handler** không bảo đảm SpEL sẽ sử dụng implementation của bạn.

Nếu không cấu hình evaluator cho policy của mình, `hasPermission` không tự suy ra owner hay ACL. `DefaultMethodSecurityExpressionHandler` có evaluator từ chối tất cả (`DenyAllPermissionEvaluator`) làm mặc định bảo thủ. Hãy test ít nhất một lượt **được phép** và một lượt **bị từ chối**, vì test chỉ các ca từ chối có thể “pass” dù evaluator chưa bao giờ được gọi.

`@EnableMethodSecurity` phải nằm trong một configuration được nạp vào `ApplicationContext`. Đối tượng gọi phải nhận service được **Spring quản lý**. Tự khởi tạo bằng `new`, self-invocation `this.protectedMethod(...)`, hoặc đặt annotation trên method không thể intercept trong proxy tương ứng sẽ làm bảo vệ không chạy như kỳ vọng.

## 6. Thiết kế policy: đối số đến từ đâu thì có thể tin?

Hãy coi đầu vào chia thành hai nhóm:

**Tin cậy sau khi xác minh phía server:** `Authentication` do security filter/provider tạo, database record, repository metadata, ACL, tenant và quyền xuất phát từ hệ thống quản trị đã xác thực.

**Không được tự động tin:** ID, object/DTO, `claimedOwner`, `tenantId`, role, hạn mức và tên người dùng do request gửi. Client có thể thay đổi những giá trị đó.

Xét DTO gửi từ client:

```json
{
  "id": 11,
  "owner": "bob",
  "content": "Nội dung tự điền"
}
```

Nếu database xác định `id=11` thuộc `alice`, `bob` **không được** cấp quyền đọc chỉ vì object tự khai `owner=bob`. Một evaluator an toàn có thể lấy **ID từ object** nhưng tra **owner thật từ repository** trước khi quyết định. Hơn nữa, service sau khi được cho phép phải trả **nội dung server lưu**, không trả nguyên nội dung do client tự điền.

Trong ứng dụng đa tenant, owner trùng tên ở hai tenant là chuyện bình thường; rule nên kiểm tra cả tenant đã xác minh. Với dữ liệu nhạy cảm, còn phải xử lý policy về share, trạng thái, field-level permissions và quyền thu hồi.

| Trường hợp | Hành vi evaluator được mong đợi |
| --- | --- |
| `targetDomainObject == null` | `false` |
| Object không đúng kiểu domain | `false` |
| `targetId == null` hoặc ID không tồn tại | `false` |
| `targetType` khác loại đã hỗ trợ | `false` |
| Permission khác tập đã định nghĩa | `false` |
| `Authentication` không có hoặc anonymous | `false` |
| Principal có authority nhưng không sở hữu bản ghi | `false` |
| Principal sở hữu bản ghi nhưng thiếu authority | `false` |
| Principal có authority **và** được policy tài nguyên cho phép | `true` |

**Fail closed** không có nghĩa giấu mọi lỗi hạ tầng dưới `false` mà không ghi nhận. Ở production, lỗi database/ACL cần được observability và xử lý lỗi đúng cách, nhưng tuyệt đối không chuyển failure thành `true`.

## 7. Ví dụ hoàn chỉnh: cùng một `PermissionEvaluator` cho object và ID

Ví dụ dùng **Java 17 + Spring Boot 3.5.8 / Spring Security 6.x**. Ứng dụng chạy bằng Gradle, không cần HTTP server hay database. Dữ liệu in-memory để thấy rõ contract và identity.

Quy tắc demo:

- Chỉ cho phép permission `"read"` trên loại tài nguyên `Document`.
- Người gọi phải có authority chính xác `"document:read"`.
- Người gọi phải là chủ sở hữu **theo bản ghi server**, không theo object truyền vào.
- `alice` sở hữu `11`, `bob` sở hữu `12`, `carol` sở hữu `13`.
- Mọi thiếu sót về authentication/đối tượng/permission phải từ chối.

### 7.1. Cấu trúc tệp

```text
permission-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PermissionContextApplication.java
    │   ├── Document.java
    │   ├── DocumentStore.java
    │   ├── DocumentPermissionEvaluator.java
    │   └── DocumentReadService.java
    └── test/java/demo/
        └── DocumentReadServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'permission-context-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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

Đây là cấu hình để build với Gradle (Gradle Wrapper cần được tạo nếu dự án chưa có). Spring Boot `3.5.8` là phiên bản cố định phục vụ demo, không có nghĩa dự án production mới nên chọn patch này thay vì bản vá mới hơn đang được hỗ trợ.

### 7.2. Domain object và nguồn dữ liệu đáng tin cậy

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(Long id, String owner, String content) {
}
```

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    private final Map<Long, Document> records = Map.of(
        11L, new Document(11L, "alice", "Alpha"),
        12L, new Document(12L, "bob", "Beta"),
        13L, new Document(13L, "carol", "Gamma")
    );

    public Document find(Long id) {
        return id == null ? null : records.get(id);
    }

    public Document require(Long id) {
        Document found = find(id);
        if (found == null) {
            throw new NoSuchElementException("Document not found: " + id);
        }
        return found;
    }
}
```

`DocumentStore` đóng vai trò database in-memory. Hệ thống thật nên tra theo `(tenant, id)` và áp dụng quyền sở hữu/ACL trên dữ liệu server. API `require` chỉ được service gọi **sau khi Method Security đã cho phép**.

### 7.3. Implement đúng hai overload

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

        // Chỉ dùng ID để tra record THẬT, không tin document.owner().
        return allowed(authentication, document.id(), permission);
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

        return allowed(authentication, id, permission);
    }

    private boolean allowed(
            Authentication authentication,
            Long id,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)
                || !"read".equals(permission)) {
            return false;
        }

        boolean hasGeneralReadAuthority =
            authentication.getAuthorities().stream()
                .anyMatch(authority ->
                    "document:read".equals(authority.getAuthority()));

        if (!hasGeneralReadAuthority) {
            return false;
        }

        Document fromServer = store.find(id);
        return fromServer != null
            && authentication.getName().equals(fromServer.owner());
    }
}
```

**Giải thích contract:**

1. Hàm nhận `Object` chỉ chấp nhận một `Document`. Khi target `null` hoặc khác kiểu, `instanceof` trả `false`; không có `NullPointerException`.
2. Hàm nhận `Serializable, String` yêu cầu `targetType` đúng chuỗi `"Document"` và ID là `Long`. Nếu hệ thống dùng UUID, cần bổ sung nhánh `UUID` và quy ước riêng.
3. Cả hai overload gọi **cùng một `allowed(...)`**, tránh một cách gọi cho phép còn cách kia từ chối với cùng bản ghi.
4. `authentication` được dùng **ngay trong lời gọi**; không đưa vào field mutable. Authentication có thể là kiểu triển khai khác nhau; logic dùng `getName()` và `getAuthorities()` theo interface.
5. `isAuthenticated()` chưa đủ do anonymous có thể trả `true`; `AuthenticationTrustResolver` chặn anonymous.
6. Permission không nhận diện được, thiếu authority, record không tồn tại hoặc owner không trùng đều trả `false`.
7. Dữ liệu `owner`/`content` trên object từ caller **không quyết định quyền**. Chỉ bản ghi do `store.find(id)` trả về được dùng để cấp quyền.

Nếu dự án có nhiều loại tài nguyên, đừng chỉ xét `"Document"` rồi cho phép mọi thứ. Tách policy theo type hoặc có một registry định tuyến quyền; không hỗ trợ loại nào thì từ chối.

### 7.4. Service dùng `hasPermission` ở hai dạng

**`src/main/java/demo/DocumentReadService.java`:**

```java
package demo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {

    private final DocumentStore store;

    public DocumentReadService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#document, 'read')")
    public String readByObject(@P("document") Document document) {
        // Trả lại content thật của server sau khi được cấp quyền.
        return store.require(document.id()).content();
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'read')")
    public String readById(@P("id") Long id) {
        return store.require(id).content();
    }
}
```

`@P` giúp Spring Security tìm đúng tên tham số trong SpEL, ngay cả khi quá trình biên dịch không giữ tên tham số Java. Không nhầm `@P` (annotation của Spring Security) với `@Param` trong JPA. Có thể dùng `-parameters` khi phù hợp, nhưng annotation giúp ví dụ dễ tái lập.

Với `readByObject`, người gọi **có thể gửi object với owner giả**. Evaluator chỉ dựa ID để tra owner thật, và method body cũng trả content từ store. Với `readById`, caller chỉ cung cấp ID; evaluator chọn overload thứ hai. Dù gọi cách nào, authorization phải trả cùng kết quả với cùng bản ghi.

### 7.5. Ứng dụng Spring Boot, expression handler và security context

**`src/main/java/demo/PermissionContextApplication.java`:**

```java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(PermissionContextApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demonstrate(DocumentReadService service) {
        return args -> {
            try {
                authenticateAs("alice", "document:read");

                // Cố tình truyền owner=bob; ID 11 thật sự thuộc alice.
                System.out.println("ALICE_OBJECT_11: "
                    + service.readByObject(
                        new Document(11L, "bob", "fake-content")));

                System.out.println("ALICE_ID_11: "
                    + service.readById(11L));

                expectDenied("ALICE_ID_12",
                    () -> service.readById(12L));

                authenticateAs("bob", "document:read");

                System.out.println("BOB_ID_12: "
                    + service.readById(12L));

                // Bob giả mạo owner=bob cho tài liệu ID 11 của alice.
                expectDenied("BOB_FORGED_OBJECT_11",
                    () -> service.readByObject(
                        new Document(11L, "bob", "fake-content")));

                authenticateAs("carol");

                // Carol sở hữu #13 nhưng không có document:read.
                expectDenied("CAROL_NO_AUTHORITY_13",
                    () -> service.readById(13L));

                authenticateAs("alice", "document:read");
                expectDenied("MISSING_ID_99",
                    () -> service.readById(99L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticateAs(
            String username,
            String... authorityNames) {

        List<SimpleGrantedAuthority> authorities =
            Arrays.stream(authorityNames)
                .map(SimpleGrantedAuthority::new)
                .toList();

        var authentication = new UsernamePasswordAuthenticationToken(
            username, "demo-only", authorities
        );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    private static void expectDenied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

Trong chương trình, `UsernamePasswordAuthenticationToken` được tạo trực tiếp với danh sách `GrantedAuthority` **chỉ để mô phỏng principal trong môi trường học tập**. Không làm vậy với username/role do HTTP client tự gửi; ứng dụng production phải có cơ chế xác thực đã được kiểm chứng và đặt authentication vào context đúng cách.

`@Profile("!test")` tránh chạy đoạn trình diễn khi Spring Boot integration test kích hoạt profile `test`. Context được dựng mới khi đổi user và được giải phóng trong `finally`, tránh truyền nhầm danh tính giữa lượt mô phỏng.

### 7.6. Chạy chương trình và đọc kết quả

Trong thư mục gốc dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```bash
.\gradlew.bat bootRun
```

Nếu chưa có Gradle Wrapper nhưng đã cài Gradle phiên bản tương thích: dùng `gradle bootRun` hoặc tạo wrapper trước khi chạy. Ngoài log Spring Boot, **bảy dòng do chương trình in ra** phải là:

```text
ALICE_OBJECT_11: Alpha
ALICE_ID_11: Alpha
ALICE_ID_12: DENIED
BOB_ID_12: Beta
BOB_FORGED_OBJECT_11: DENIED
CAROL_NO_AUTHORITY_13: DENIED
MISSING_ID_99: DENIED
```

Phân tích:

1. `alice` gọi overload nhận object với `Document(11, owner=bob, content=fake)` nhưng evaluator vẫn tra owner thực `alice` từ server; kết quả trả content thật `Alpha`.
2. `alice` gọi overload nhận ID `11L` và type `"Document"`; kết quả cũng `Alpha`. Hai đường gọi thống nhất.
3. `alice` có authority nhưng **không sở hữu** `12`: bị từ chối.
4. `bob` được đọc `12` do sở hữu và có authority.
5. `bob` giả `owner=bob` cho object có ID `11`: bị từ chối vì store xác định chủ thật là `alice`.
6. `carol` sở hữu `13` nhưng thiếu authority: bị từ chối; owner không đủ thay thế authority trong policy này.
7. ID `99` không tồn tại: bị từ chối theo fail closed.

Đây là **mô phỏng security context không có HTTP**: nó minh họa rằng Method Security có thể lấy `Authentication` từ `SecurityContextHolder` dù ứng dụng không có endpoint web.

## 8. Integration test: xác nhận evaluator và proxy thật sự hoạt động

Tạo file **`src/test/java/demo/DocumentReadServiceTest.java`**:

```java
package demo;

import java.io.Serializable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DocumentReadServiceTest {

    @Autowired
    DocumentReadService service;

    @Autowired
    PermissionEvaluator evaluator;

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void supportsBothOverloadsAndIgnoresForgedOwner() {
        assertEquals("Alpha", service.readById(11L));

        // Owner/content từ object không được dùng làm bằng chứng.
        assertEquals("Alpha", service.readByObject(
            new Document(11L, "bob", "invented")));

        var auth =
            SecurityContextHolder.getContext().getAuthentication();
        assertFalse(evaluator.hasPermission(
            auth,
            (Object) null,
            "read"
        ));
        assertFalse(evaluator.hasPermission(
            auth,
            (Serializable) 11L,
            "UnknownType",
            "read"
        ));
        assertFalse(evaluator.hasPermission(
            auth,
            (Serializable) 11L,
            "Document",
            "write"
        ));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void deniesCrossOwnerAccessDespiteForgedDto() {
        assertEquals("Beta", service.readById(12L));

        assertThrows(AccessDeniedException.class,
            () -> service.readById(11L));

        assertThrows(AccessDeniedException.class,
            () -> service.readByObject(
                new Document(11L, "bob", "fake")));
    }

    @Test
    @WithMockUser(username = "carol", roles = "USER")
    void deniesOwnerWhoLacksReadAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> service.readById(13L));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:read")
    void allowsOwnerWithReadAuthority() {
        assertEquals("Gamma", service.readById(13L));
    }

    @Test
    @WithAnonymousUser
    void deniesAnonymousCaller() {
        assertThrows(AccessDeniedException.class,
            () -> service.readById(11L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void deniesMissingIdAndNullTarget() {
        assertThrows(AccessDeniedException.class,
            () -> service.readById(99L));

        assertThrows(AccessDeniedException.class,
            () -> service.readByObject(null));
    }
}
```

Chạy:

```bash
./gradlew test
```

Test dùng `@SpringBootTest` để tạo ApplicationContext, `@ActiveProfiles("test")` để không chạy CLI demo, và `@WithMockUser`/`@WithAnonymousUser` từ `spring-security-test`. Khi tiêm `DocumentReadService` từ Spring, lời gọi đi qua bean/proxy và annotation `@PreAuthorize` có cơ hội thực thi.

Test trực tiếp trên `evaluator` chứng minh ba hợp đồng quan trọng: **object null**, **target type sai** và **permission không hỗ trợ** đều trả `false`. Test qua service chứng minh Method Security thực sự gọi evaluator đúng với `Authentication` theo từng principal. Nếu chỉ tạo `new DocumentReadService(store)`, annotation sẽ không tự chặn lời gọi và test phân quyền không còn giá trị.

Các test cùng dùng in-memory store **bất biến** (chỉ đọc), nên không có mutation gây phụ thuộc thứ tự test.

## 9. `Authentication` trong SpEL không phải tham số dịch vụ

Có thể viết một điều kiện kết hợp:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "hasPermission(#id, 'Document', 'read')"
)
public String readById(@P("id") Long id) {
    // ...
}
```

Đây là **phương án minh họa thay thế** cho method `readById`, không phải code phải thêm đồng thời vào file demo. Biểu thức `hasAuthority` nhìn `Authentication.getAuthorities()` còn `hasPermission` nhìn evaluator; dùng `and` để bắt buộc cả hai. Trong ví dụ đầy đủ, evaluator đã tự kiểm tra authority để mọi lối gọi nhất quán, nên thêm `hasAuthority` ngoài SpEL là **trùng lặp hợp lệ nhưng không cần thiết**.

Có thể dùng `authentication.name` trong security expression:

```java
@PreAuthorize(
    "authentication.name == #owner and " +
    "hasPermission(#id, 'Document', 'read')"
)
```

Nhưng mảnh này **không nên dùng với `#owner` do client tự khai**: so sánh như vậy chỉ xác nhận user có thể gõ tên mình. Quyền đối tượng phải so với owner của bản ghi server.

### `@PostAuthorize` và `returnObject`

Nếu chỉ tải đối tượng sau khi method chạy:

```java
@PostAuthorize(
    "returnObject != null and hasPermission(returnObject, 'read')"
)
public Document load(Long id) {
    return store.find(id);
}
```

Đây là mảnh code minh họa trong một service có `store`. `returnObject` là kết quả phương thức. `@PostAuthorize` kiểm tra **sau** khi method hoàn thành; không dùng nó như biện pháp duy nhất bảo vệ thao tác có side effect đã ghi vào database. Trong ví dụ của mục 7, `@PreAuthorize` hợp lý vì method chỉ cần ID/đối tượng trước khi chạy.

### `@PreFilter` và `@PostFilter`

`hasPermission(filterObject, 'read')` có thể dùng để lọc từng phần tử với `@PreFilter`/`@PostFilter`:

```java
@PostFilter("hasPermission(filterObject, 'read')")
public java.util.List<Document> visibleDocuments() {
    return new java.util.ArrayList<>(repository.findAll());
}
```

Đây là **mảnh code minh họa**, cần một `repository` có `findAll()`. Đừng tải toàn bộ dữ liệu rồi kiểm tra từng phần tử cho tập rất lớn; evaluator có thể gây N+1 query. Nên lọc theo owner/tenant/ACL ở repository khi chính sách cho phép và vẫn kiểm tra đúng ranh giới truy cập.

## 10. Lỗi thường gặp khi implement `PermissionEvaluator`

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| Chỉ implement một overload đúng | Dạng object chạy nhưng dạng ID luôn sai hoặc ngược lại | Implement cả hai; test cả hai biểu thức |
| Không gắn evaluator vào expression handler | `hasPermission` không dùng policy ứng dụng | `@Bean static MethodSecurityExpressionHandler` + `setPermissionEvaluator(...)` |
| Dựa hoàn toàn vào `isAuthenticated()` | Anonymous token có thể được coi là đã xác thực | Dùng `AuthenticationTrustResolver`, thêm policy cụ thể |
| Cast `getPrincipal()` thành `String` bất kể provider | `ClassCastException` với `UserDetails`, JWT, OAuth2 principal | Dùng API phù hợp loại token hoặc principal adapter |
| Lấy owner/tenant từ client DTO | Truy cập chéo người dùng hoặc tenant | Tra quyền/owner từ server-side store |
| Trả `true` cho target không biết | Mở quyền khi gặp ID/type/permission lạ | Fail closed với `false` |
| Sai `targetType` | Overload nhận ID luôn từ chối hoặc đọc nhầm loại | Quy định canonical type, nhất quán với ACL/repository |
| Lưu `Authentication` trong field singleton | Race và lộ identity giữa request | Truyền auth theo tham số mỗi lần gọi |
| Test với object tạo bằng `new` | Bỏ qua proxy và `@PreAuthorize` | Test bằng Spring-managed bean |
| Self-invocation `this.readById(id)` | Không chạy interceptor của method được gọi nội bộ | Tách service bảo mật hoặc đi qua Spring proxy |
| Lấy `SecurityContext` sai thread | Không có auth hoặc sai principal trong async | Dùng security-context propagation đúng |
| Cache permission quá lâu | Quyền đã thu hồi vẫn cho phép | Key theo user/tenant/target/action; invalidation và thời hạn |
| Chỉ kiểm tra trước update | Quyền/owner/ACL thay đổi giữa check và write | Conditional update, transaction/lock/version phù hợp |
| Lạm dụng `getName()` làm ID liên tenant | Trùng username giữa tenant | Dùng stable principal ID và tenant đáng tin cậy |

**Câu hỏi chẩn đoán quan trọng:** method đã **được intercept** hay evaluator đã được **gọi và trả false**? Đây là hai vấn đề khác nhau. `AccessDeniedException` sau một cuộc gọi có thể đến từ policy hoặc tầng khác; cần test/trace đúng đường gọi, nhưng tránh log token/credential hoặc dữ liệu nhạy cảm.

## 11. Bảo mật dữ liệu, transaction và hiệu năng

### 11.1. ACL và custom evaluator

Spring Security có `AclPermissionEvaluator` làm một implementation có thể kiểm tra ACL theo object identity và permission mask. Nó yêu cầu cấu hình ACL storage, identity, quyền và lookup tương ứng; interface `PermissionEvaluator` **không có phụ thuộc trực tiếp** đến ACL. Custom evaluator như demo phù hợp khi quyền dựa trên owner, tổ chức, tenant, trạng thái hoặc domain policy riêng.

`targetType` trong ACL thường cần phản ánh tên lớp hoặc mapping `ObjectIdentity` đã được cấu hình; bí danh `"Document"` chỉ có ý nghĩa khi evaluator/ACL hiểu nó.

### 11.2. Không cho quyết định quyền phụ thuộc một snapshot quá cũ

Một lượt gọi `hasPermission` có thể truy vấn owner lúc `t1`; giữa lúc đó và khi thao tác cập nhật tại `t2`, quyền/owner/tenant có thể đổi. Đây là rủi ro **TOCTOU (time of check, time of use)**. Với thao tác ghi, nên bảo vệ điều kiện ngay trong transaction/câu lệnh update:

```sql
UPDATE documents
SET title = :newTitle
WHERE id = :documentId
  AND owner_id = :trustedPrincipalId
  AND tenant_id = :trustedTenantId;
```

Đây là SQL **minh họa**, cần điều chỉnh theo schema và nghiệp vụ. Kiểm tra số hàng ảnh hưởng để biết update thành công. Với chính sách phức tạp có thể cần lock, version, isolation hoặc kiểm tra quyền lại cùng trạng thái dữ liệu được cập nhật. `@PreAuthorize` không tự thay thế các điều kiện nhất quán ở database.

### 11.3. Kiểm tra N phần tử có thể phát sinh N truy vấn

Nếu `PermissionEvaluator` gọi database ở mỗi đối tượng và `@PostFilter` lọc 1.000 tài liệu, nguy cơ có 1.000 lookup ACL/owner. Hãy cân nhắc đẩy điều kiện xuống truy vấn, batch ACL lookup, phân trang và cache có invalidation đúng. Đừng vì hiệu năng mà lưu một kết quả `allowed=true` chung cho mọi principal; cache policy phải gồm đủ scope người dùng và phiên bản quyền.

### 11.4. Không coi `Authentication` tự thân là dữ liệu vĩnh viễn

Authority của token có thể được cấp lúc đăng nhập, nhưng quyền trên object có thể thay đổi trong database. Nếu tài liệu bị chia sẻ lại hoặc quyền bị thu hồi, policy phải có cách nhìn thấy cập nhật phù hợp với độ nhạy nghiệp vụ. Với JWT sống lâu hoặc hệ thống nhiều instance, cân nhắc revocation, ACL version và chính sách cache rõ ràng.

## 12. Bài tập tự kiểm tra

1. **`hasPermission(#document, 'read')` sử dụng overload nào?**  
   `(Authentication, Object targetDomainObject, Object permission)`.

2. **`hasPermission(#id, 'Document', 'read')` sử dụng overload nào?**  
   `(Authentication, Serializable targetId, String targetType, Object permission)`.

3. **Vì sao annotation không viết đối số `Authentication`?**  
   Method Security expression root đã lấy authentication từ security context của lời gọi và cung cấp cho evaluator.

4. **`getPrincipal()` có luôn là username kiểu `String` không?**  
   Không; tùy provider có thể là `UserDetails`, `Jwt`, `OAuth2User` hoặc đối tượng khác.

5. **`isAuthenticated() == true` có chứng minh không phải user anonymous không?**  
   Không. Kiểm tra `AuthenticationTrustResolver` và chính sách cấp quyền.

6. **Client gửi object ID 11, owner = bob trong khi server lưu owner = alice. `bob` có được cấp quyền không?**  
   Không. Dữ liệu owner tự khai không được tin; evaluator phải đối chiếu bản ghi server.

7. **Có cần cài Spring Security ACL để implement `PermissionEvaluator`?**  
   Không. Interface có thể dùng policy/repository của ứng dụng.

8. **Nếu `targetDomainObject` là `null`, evaluator nên làm gì?**  
   Trả `false`, trừ khi expression đã tự xử lý null theo nhánh chính sách rõ ràng.

9. **Nếu có bean `PermissionEvaluator` nhưng `hasPermission` luôn bị deny, hãy kiểm tra gì?**  
   `MethodSecurityExpressionHandler` có gắn evaluator chưa; `@EnableMethodSecurity`, proxy, tên SpEL, type/ID/permission và dữ liệu policy có khớp không.

10. **Vì sao không lưu `Authentication` vào field của singleton evaluator?**  
    Vì nhiều request có thể chạy đồng thời, làm rò hoặc trộn thông tin của các principal khác nhau.

11. **Vì sao owner check trước method chưa đủ cho một lệnh update cực kỳ nhạy cảm?**  
    Vì trạng thái quyền có thể đổi giữa check và update; cần điều kiện ở thời điểm ghi/transaction phù hợp.

12. **Một job không có HTTP request có dùng `hasPermission` được không?**  
    Có, nếu gọi qua Spring proxy và có security context/identity đáng tin được thiết lập đúng.

## 13. Tài liệu chính thức và điểm cần nhớ

- [Spring Security — `PermissionEvaluator` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): hai chữ ký, `targetDomainObject`, `Serializable`, `targetType`, `permission` và contract trả `boolean`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `hasPermission`, SpEL, cấu hình expression handler, proxy và testing.
- [Spring Security — `Authentication` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html): `getName`, `getPrincipal`, authorities và `isAuthenticated`.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): roles/authorities và authorization mechanism.
- [Spring Security — `AuthenticationTrustResolver` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): phân biệt anonymous và các mức xác thực.
- [Spring Security — Method Security Tests](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`.
- [Spring Security — ACL](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): lựa chọn ACL khi cần permission theo từng domain object.

**Kết luận:** `PermissionEvaluator` là một **hợp đồng ra quyết định cấp đối tượng**, không phải bộ máy xác thực. `Authentication` đến từ Spring Security của **lời gọi hiện tại**, không đến từ DTO client; biểu thức `hasPermission` tự truyền nó vào overload phù hợp. Một evaluator tốt xử lý cả object lẫn ID, không tin owner/tenant tự khai, từ chối trường hợp không rõ và không giữ identity trong trạng thái singleton. Sau cùng, hãy kiểm thử qua Spring-managed proxy và bảo vệ nhất quán dữ liệu khi trạng thái/quyền thay đổi.