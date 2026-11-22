# `AclPermissionEvaluator` và tích hợp `hasPermission` trong Spring Security

## 1. Bài toán: authority chung không quyết định quyền trên từng tài liệu

Một API có phương thức `readDocument(11L)`. Người gọi đã đăng nhập và có authority `document:read`. Tuy nhiên, trong hệ thống quản lý tài liệu:

- `alice` được đọc tài liệu `11` nhưng không được đọc tài liệu `12`.
- `bob` được đọc cả `11` lẫn `12` vì có những ACE phù hợp.
- `carol` có một ACE `READ` trên tài liệu `13` nhưng **không có authority chung `document:read`**; ứng dụng muốn cô ấy bị từ chối.
- `root` là chủ sở hữu ACL của một số tài liệu nhưng **không tự có ACE `READ`**.
- Client có thể truyền một object tự khai owner, title và ID; metadata do client gửi không đáng tin để cấp quyền.

`hasAuthority('document:read')` chỉ trả lời rằng caller có quyền đọc **ở cấp chức năng**. Nó không trả lời caller có quyền `READ` trên **Document#11** hay không. Spring Security có cơ chế `hasPermission(...)` dành cho phân quyền theo đối tượng.

`AclPermissionEvaluator` là implementation `PermissionEvaluator` do module **spring-security-acl** cung cấp. Nó kết nối biểu thức `hasPermission` của **Spring Method Security** với dữ liệu ACL được nạp qua `AclService` và cơ chế xét **ACE/SID/Permission**.

Mục tiêu bài học:

1. Hiểu **hai overload** `hasPermission` và lúc nào mỗi overload được chọn.
2. Phân biệt `Authentication`, `Sid`, `ObjectIdentity`, `Permission`, `Acl` và `AccessControlEntry`.
3. Đăng ký `AclPermissionEvaluator` vào `DefaultMethodSecurityExpressionHandler` đúng cách, không chỉ tạo bean.
4. Hiểu `ObjectIdentityImpl`, yêu cầu `getId()` của domain object và độ chính xác của `targetType`.
5. Viết được `@PreAuthorize`, `@PostAuthorize`, `@PostFilter` với biểu thức `hasPermission`.
6. Chạy demo Java 17+ / Spring Boot 3.5.x dùng **ACL engine thật** nhưng `AclService` giả lập in-memory để không cần database.
7. Viết integration test chứng minh object overload, ID overload, authority + ACL theo phép AND, denial và dữ liệu object giả mạo.
8. Chuyển kiến trúc sang JDBC ACL thật và kiểm soát tenant, cache, tính nhất quán, hiệu năng.

**Phạm vi:** Spring Security 6.5.x cùng Spring Boot 3.5.x, Method Security dựa trên Spring AOP proxy. Bản demo không có HTTP endpoint; `@PreAuthorize` vẫn hoạt động khi gọi Spring-managed service và có `SecurityContext` hợp lệ. Khi dùng Spring Security 7.x, đối chiếu tài liệu API theo phiên bản triển khai.

## 2. `AclPermissionEvaluator` là gì và không phải là gì?

Interface gốc `PermissionEvaluator` thuộc package `org.springframework.security.access`:

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

Đây là **chữ ký API rút gọn** để học, không phải một file Java độc lập. `AclPermissionEvaluator` thuộc package `org.springframework.security.acls` và implement cả hai chữ ký.

`AclPermissionEvaluator` **không tự quyết định** rằng user nào là owner từ dữ liệu controller gửi, không xác thực password và không tự tạo ACL. Nó sử dụng:

- `AclService` để đọc ACL gắn với `ObjectIdentity`.
- `ObjectIdentityRetrievalStrategy` để tạo identity từ **instance domain object**.
- `ObjectIdentityGenerator` để tạo identity từ **ID và type**.
- `SidRetrievalStrategy` để lấy các SID phù hợp từ `Authentication`.
- `PermissionFactory` để đổi tên/mask quyền thành `Permission`.
- `Acl.isGranted(...)` cùng `PermissionGrantingStrategy` để xét các ACE, deny/grant và kế thừa.

`AclService` có thể dựa trên JDBC hoặc implementation khác. **Chỉ thêm dependency `spring-security-acl` chưa đủ**: ứng dụng phải tạo/lưu ACL, cấu hình service/lookup và gắn evaluator vào Method Security.

### 2.1. Hai chữ ký Java và hai biểu thức SpEL

| Biểu thức trong annotation | Overload Java | Bối cảnh |
| --- | --- | --- |
| `hasPermission(#document, 'READ')` | `hasPermission(Authentication, Object, Object)` | Đã có đối tượng `Document` |
| `hasPermission(#id, 'demo.Document', 'READ')` | `hasPermission(Authentication, Serializable, String, Object)` | Chỉ có ID và loại tài nguyên |
| `hasPermission(returnObject, 'READ')` | Overload nhận object | Dùng với `@PostAuthorize` |
| `hasPermission(filterObject, 'READ')` | Overload nhận object | Dùng với `@PostFilter`/`@PreFilter` |

Với dạng **đối tượng**, ACL evaluator lấy object identity của chính object; constructor mặc định `ObjectIdentityImpl(Object)` đòi hỏi instance cung cấp **`public getId()`**. Một Java record chỉ có accessor `id()` mà không có `getId()` **không đáp ứng mặc định này**, trừ khi bạn tự cấu hình một `ObjectIdentityRetrievalStrategy` phù hợp.

Với dạng **ID**, chuỗi `targetType` nên khớp chính xác loại đã dùng khi lưu ACL, thường là **tên lớp đầy đủ** như `"demo.Document"`; `targetId` là `Serializable` như `Long`. Không có cơ chế tự dò entity bằng tên tùy ý.

**Vì sao annotation không có đối số `Authentication`?** Method Security expression root đã lấy authentication của lời gọi từ Spring Security rồi chuyển nó tới evaluator. Người dùng không được tự gửi tên mình trong request để ứng dụng coi như đã xác thực.

### 2.2. Default permission name: dùng `'READ'`, không tự đoán `'read'`

`DefaultPermissionFactory` mặc định đăng ký những tên thuộc tính public static của `BasePermission`, như `READ`, `WRITE`, `CREATE`, `DELETE`, `ADMINISTRATION`. Vì vậy ví dụ dùng chuỗi **`'READ'` viết hoa**.

Các bit cơ bản:

| Permission | Mask |
| --- | ---: |
| `BasePermission.READ` | 1 |
| `BasePermission.WRITE` | 2 |
| `BasePermission.CREATE` | 4 |
| `BasePermission.DELETE` | 8 |
| `BasePermission.ADMINISTRATION` | 16 |

Không coi tên `'read'`, `'READ'`, `'view'` là tương đương nếu `PermissionFactory` chưa cấu hình mapping. Với custom permission, đăng ký factory tương ứng và kiểm tra mask, tên, ACE thực tế. Tránh tự biến lỗi permission không tồn tại thành mặc định `READ`.

### 2.3. ACL owner không đồng nghĩa READ permission

`Acl.getOwner()` trả SID đại diện người quản trị ACL theo implementation và policy. `AclPermissionEvaluator` hỏi permission cụ thể qua ACE và chiến lược xét quyền. **ACL owner không mặc nhiên có `READ` trên dữ liệu.**

Tương tự `BasePermission.ADMINISTRATION` không mặc nhiên bao gồm `READ`. Nếu nghiệp vụ muốn system admin đọc mọi đối tượng thì phải có một policy riêng và kiểm thử rõ ràng; không tự suy điều đó từ quyền quản trị ACL.

## 3. Luồng từ `@PreAuthorize` đến ACE

```text
Caller -> Spring-managed DocumentService proxy
                    |
                    v
            @PreAuthorize advice
                    |
           lấy MethodInvocation
           lấy Authentication
                    |
                    v
           SpEL hasPermission(...)
                    |
                    v
             AclPermissionEvaluator
                  /         \
                 v           v
     ObjectIdentity        SIDs + Permission
     từ object/ID           từ auth + factory
                 \           /
                  v         v
              AclService.readAclById(...)
                         |
                         v
                   Acl.isGranted(...)
                         |
                         v
              PermissionGrantingStrategy
                 |         |
               GRANT    DENY/không có quyết định
                 |         |
                allow     deny hoặc exception
                 |
                 v
       DocumentService method body
```

Điều kiện quan trọng:

1. `@EnableMethodSecurity` phải được bật.
2. Annotation nằm trên method/class mà Spring Security có thể intercept.
3. Caller phải đi qua **Spring-managed proxy**, không dùng `new Service(...)` hoặc self-invocation `this.securedMethod(...)`.
4. Expression handler phải dùng đúng evaluator, không còn `DenyAllPermissionEvaluator` mặc định.
5. `AclService` phải đọc đúng `ObjectIdentity` với SID/ACE đã được seed hoặc lưu trong database.
6. Permission factory phải hiểu tên/mask trong annotation.
7. Quy tắc tenant, authority cấp chức năng và policy nghiệp vụ phải được kết hợp tại ranh giới phù hợp.

**Với `@PreAuthorize`, body không được chạy khi expression bị từ chối.** Điều này phù hợp cho thao tác đọc/ghi cần chặn trước side effect. `@PostAuthorize` chỉ kiểm tra **sau** khi body hoàn thành, nên không nên dùng làm lớp bảo vệ duy nhất cho các thao tác đã có side effect.

## 4. `Authentication`, SID và nguồn danh tính tin cậy

`AclPermissionEvaluator` nhận `Authentication` của lời gọi hiện tại. Một `Authentication` có thể có:

- `getName()`: định danh được provider trình bày (username, subject token hoặc mapping tùy hệ thống).
- `getPrincipal()`: có thể là `UserDetails`, `Jwt`, `OAuth2User` hay custom principal; không mặc định là `String`.
- `getAuthorities()`: `GrantedAuthority` do identity provider hoặc ứng dụng kiểm chứng cấp.
- `isAuthenticated()`: trạng thái token; cần phân biệt anonymous và real user theo policy.

`SidRetrievalStrategy` có thể tạo `PrincipalSid` và `GrantedAuthoritySid` từ authentication. ACL chứa `PrincipalSid("alice")` khác với `GrantedAuthoritySid("ROLE_EDITOR")`; cả **kiểu SID và giá trị** phải trùng. Không dùng username chỉ unique trong một tenant làm SID global nếu có thể trùng tenant khác.

Nguyên tắc an toàn:

- User/tenant phải được xác minh phía server; không đọc header `X-User` hay trường `owner` của DTO rồi tin ngay.
- Nếu dùng JWT, định nghĩa cách ánh xạ `sub`/issuer/tenant sang stable subject ID và SID thống nhất khi tạo và xét ACL.
- `AnonymousAuthenticationToken` có thể báo `isAuthenticated() == true`; không tự coi một token như vậy là user thật. Spring expressions `isAuthenticated()` có ngữ nghĩa phân biệt anonymous; nên dùng nó và authority policy rõ ràng.
- Không lưu authentication của request vào field mutable của singleton evaluator hoặc custom ACL service.
- Với `@Async`/thread pool, security context không mặc nhiên được truyền; dùng cơ chế propagation có chủ đích nếu thực hiện authorization trong background task.

## 5. Cấu hình cốt lõi để `hasPermission` thực sự gọi ACL evaluator

Spring Security cung cấp một cơ chế tùy biến expression handler. Ví dụ tối thiểu:

```java
@Configuration
@EnableMethodSecurity
class AclExpressionSecurityConfig {

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Đây là **mảnh cấu hình** cần import và một `AclService` thực tế; chương trình đầy đủ nằm ở mục 7. `static @Bean` giúp Spring công bố expression handler sớm, trước khi các class cấu hình Method Security khởi tạo advisor.

**Bẫy thường gặp:** có một bean `AclPermissionEvaluator` nhưng không gọi `handler.setPermissionEvaluator(...)`. Khi đó `hasPermission` có thể vẫn dùng evaluator mặc định từ chối tất cả hoặc một handler khác, dẫn đến test deny đều pass nhưng test allow luôn fail. Luôn có **cả test allow và deny**.

Mã ứng dụng dùng:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:read') and " +
    "hasPermission(#id, 'demo.Document', 'READ')"
)
public String readById(@P("id") Long id) {
    return repository.require(id).getTitle();
}
```

`@P("id")` thuộc `org.springframework.security.access.method.P`, giúp SpEL tìm tên tham số ổn định khi thiếu compiler option `-parameters`. `hasAuthority` yêu cầu năng lực chức năng, `hasPermission` yêu cầu ACE trên object; phép `and` bắt buộc cả hai.

Đây cũng là lý do **không** chỉ dùng `hasPermission` nếu app cần một authority cấp chức năng độc lập. ACE có thể tồn tại nhưng caller vẫn bị từ chối vì tổ chức đã thu hồi quyền vào tính năng đọc.

## 6. `ObjectIdentity`: phần thường khiến cấu hình đúng mà kết quả vẫn sai

### 6.1. Đối tượng phải có ID phù hợp

Nếu object overload dùng cách trích identity mặc định, domain object có thể khai báo:

```java
package demo;

public final class Document {

    private final Long id;
    private final String title;

    public Document(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Đây cũng là **file Java dùng trong demo đầy đủ** ở phần sau. `getId()` cho phép `ObjectIdentityImpl(Object)` lấy ID từ object bằng reflection và dùng class name `demo.Document`. Khi truyền ID vào expression, phải dùng chuỗi **`'demo.Document'`** để match.

Nếu model dùng Java record:

```java
public record DocumentRecord(Long id, String title) {
}
```

record chỉ có `id()`; muốn dùng object overload với default retrieval strategy thì cần thêm method `getId()` hoặc tùy chỉnh strategy để đọc `id()`. Chữ ký `getId` phải public và trả một `Serializable` phù hợp.

### 6.2. Identity trong ACL storage phải cùng loại

Một ACL tạo như sau:

```java
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 11L);
```

sẽ có type `demo.Document` và ID 11 kiểu `Long`. Nếu expression dùng:

```java
hasPermission(#id, 'Document', 'READ')
```

trong khi database lưu `demo.Document`, lookup có thể không tìm thấy ACL. Nếu ID là `UUID`/String thay vì Long, phải thống nhất schema, mapping và serialization ở mọi đường lưu/đọc. Không suy từ một label UI sang canonical ACL type.

### 6.3. Object đến từ client không phải bằng chứng về owner

Giả sử bob gửi:

```json
{
  "id": 11,
  "title": "Dữ liệu tự khai là của bob",
  "owner": "bob"
}
```

Một evaluator theo Spring ACL mặc định sẽ tạo identity từ **loại object và ID**, sau đó đọc ACE phía server. Nó không nên sử dụng `owner` hoặc `title` giả từ client để tự cho quyền. Sau khi `@PreAuthorize` cho phép, method body trong demo **đọc nội dung thật từ repository**, không trả nguyên object do caller đưa vào.

Với hệ thống thực, object identity có thể phụ thuộc tenant; chỉ ID/type chưa đủ nếu ID chỉ duy nhất trong từng tenant. Hãy thiết kế stable globally unique ID hoặc namespace ACL theo tenant đã xác minh và kiểm tra tenant ở service/repository.

## 7. Demo hoàn chỉnh Spring Boot 3.5.8 / Java 17+

Demo dùng chính các class ACL của Spring Security nhưng thay JDBC `AclService` bằng kho ACL in-memory **chỉ để học và test**. Nhờ đó, nó kiểm tra thật:

- `AclPermissionEvaluator` và cả hai overload.
- `DefaultMethodSecurityExpressionHandler`.
- `@EnableMethodSecurity`, `@PreAuthorize` và `@PostFilter`.
- `AclImpl`, `BasePermission`, `PrincipalSid`, `DefaultPermissionGrantingStrategy`.
- Nhận diện object identity từ `Document.getId()` và từ `(id, type)`.
- Kết hợp authority chung với quyền cụ thể.

Bản demo không thay thế schema/JDBC ACL và không có endpoint HTTP. Để chạy với database thật, xem mục 9.

### 7.1. Cấu trúc dự án

```text
acl-has-permission-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── AclPermissionDemoApplication.java
    │   ├── Document.java
    │   ├── DocumentRepository.java
    │   ├── InMemoryAclService.java
    │   └── DocumentService.java
    └── test/java/demo/
        └── DocumentServiceSecurityTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'acl-has-permission-demo'
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
    implementation 'org.springframework.security:spring-security-acl'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM từ plugin quản lý versions của các Spring dependencies. Ví dụ không cần `spring-boot-starter-web` vì chạy theo `CommandLineRunner`; Method Security là cơ chế áp dụng trên Spring service, không phụ thuộc trực tiếp một HTTP controller. Cần môi trường Gradle có thể tải dependencies và JDK 17+.

### 7.2. Domain class có `getId()`

**`src/main/java/demo/Document.java`:**

```java
package demo;

public final class Document {

    private final Long id;
    private final String title;

    public Document(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

`Document.getId()` cần cho object overload theo `ObjectIdentityImpl(Object)`. `title` chỉ là dữ liệu hiển thị; giá trị này không tham gia quyết định ACE trong demo.

### 7.3. Dữ liệu tài liệu từ server

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.stereotype.Component;

@Component
public class DocumentRepository {

    private final Map<Long, Document> documents = Map.of(
        11L, new Document(11L, "Alpha"),
        12L, new Document(12L, "Beta"),
        13L, new Document(13L, "Gamma")
    );

    public Document require(Long id) {
        Document document = id == null ? null : documents.get(id);
        if (document == null) {
            throw new NoSuchElementException("No document " + id);
        }
        return document;
    }

    public List<Document> all() {
        List<Document> result = new ArrayList<>(documents.values());
        result.sort(Comparator.comparing(Document::getId));
        return result;
    }
}
```

`all()` tạo list **có thể chỉnh sửa** để `@PostFilter` loại phần tử trong demo. Dữ liệu đã được tạo và lưu phía server; method nhận object từ caller **không trả nguyên dữ liệu do caller tự gửi**.

### 7.4. `AclService` in-memory sử dụng `AclImpl` thật

**`src/main/java/demo/InMemoryAclService.java`:**

```java
package demo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class InMemoryAclService implements AclService {

    private final Map<ObjectIdentity, Acl> stored;

    public InMemoryAclService() {
        var changeStrategy = new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_BOOTSTRAP")
        );
        var grantStrategy =
            new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger()
            );

        // Chỉ để seed dữ liệu của DEMO.
        // Production: dùng MutableAclService/transaction và actor thật.
        SecurityContext before = SecurityContextHolder.getContext();
        SecurityContext bootstrap = SecurityContextHolder.createEmptyContext();
        bootstrap.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "bootstrap", "demo-only",
                List.of(new SimpleGrantedAuthority("ROLE_ACL_BOOTSTRAP"))
            )
        );
        SecurityContextHolder.setContext(bootstrap);

        try {
            Map<ObjectIdentity, Acl> mutable = new HashMap<>();

            AclImpl first = create(
                11L, changeStrategy, grantStrategy
            );
            first.insertAce(
                0, BasePermission.READ,
                new PrincipalSid("alice"), true
            );
            first.insertAce(
                1, BasePermission.READ,
                new PrincipalSid("bob"), true
            );
            mutable.put(first.getObjectIdentity(), first);

            AclImpl second = create(
                12L, changeStrategy, grantStrategy
            );
            second.insertAce(
                0, BasePermission.READ,
                new PrincipalSid("bob"), true
            );
            mutable.put(second.getObjectIdentity(), second);

            AclImpl third = create(
                13L, changeStrategy, grantStrategy
            );
            third.insertAce(
                0, BasePermission.READ,
                new PrincipalSid("carol"), true
            );
            mutable.put(third.getObjectIdentity(), third);

            stored = Map.copyOf(mutable);
        } finally {
            // Trả nguyên SecurityContext trước khi bootstrap,
            // không để actor đặc quyền tồn tại sau khởi tạo.
            SecurityContextHolder.setContext(before);
        }
    }

    private static AclImpl create(
            Long id,
            AclAuthorizationStrategyImpl changes,
            DefaultPermissionGrantingStrategy grants) {

        return new AclImpl(
            new ObjectIdentityImpl(Document.class, id),
            id,
            changes,
            grants,
            null,  // Không có parent ACL
            null,  // Không giới hạn tập SID được load
            false, // Không kế thừa ACE
            new PrincipalSid("root") // ACL owner
        );
    }

    @Override
    public Acl readAclById(ObjectIdentity oid) {
        Acl acl = stored.get(oid);
        if (acl == null) {
            throw new NotFoundException("No ACL for " + oid);
        }
        return acl;
    }

    @Override
    public Acl readAclById(ObjectIdentity oid, List<Sid> sids) {
        // Demo trả toàn bộ ACL, không lọc theo SID.
        return readAclById(oid);
    }

    @Override
    public Map<ObjectIdentity, Acl> readAclsById(
            List<ObjectIdentity> objects) {
        return readAclsById(objects, null);
    }

    @Override
    public Map<ObjectIdentity, Acl> readAclsById(
            List<ObjectIdentity> objects, List<Sid> sids) {

        Map<ObjectIdentity, Acl> result = new HashMap<>();
        for (ObjectIdentity oid : objects) {
            result.put(oid, readAclById(oid, sids));
        }
        return result;
    }

    @Override
    public List<ObjectIdentity> findChildren(ObjectIdentity parent) {
        // Demo không có ACL cha/con.
        return List.of();
    }
}
```

**Điểm quan trọng của bản demo:**

- Dùng chính `AclImpl`, `BasePermission`, `DefaultPermissionGrantingStrategy`, `PrincipalSid`; evaluator vẫn gọi logic ACL thật.
- `AclService` chỉ là **adapter lưu trữ giả lập**. Nó bỏ qua tham số lọc `sids`, điều được hợp đồng AclService cho phép vì tối ưu SID là tùy chọn; service JDBC có cơ chế nạp/cache riêng.
- ACL có owner `root`, nhưng không tạo ACE `READ` cho `root`.
- `Document#11`: `alice` và `bob` có `READ`.
- `Document#12`: chỉ `bob` có `READ`.
- `Document#13`: `carol` có `READ`, nhưng ở tầng service còn kiểm tra authority chung.
- Khối bootstrap tự tạo `Authentication` đặc quyền **chỉ để seed ACL trong chương trình học**; không sao chép cách này vào controller hoặc authentication flow production.
- Mọi object identity đều dùng `new ObjectIdentityImpl(Document.class, id)`, tương đương type `"demo.Document"`. Điều đó đảm bảo hai overload tra cùng một ACL.

**Không dùng đoạn này làm ACL storage production**: không có database, persistence, transaction, phân tenant, lifecycle đổi grant/owner, concurrency invalidation hay audit thật. Bản demo giữ ACL bất biến sau bootstrap theo contract ứng dụng.

### 7.5. Spring service gắn `hasPermission`

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.List;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:read') and " +
        "hasPermission(#id, 'demo.Document', 'READ')"
    )
    public String readById(@P("id") Long id) {
        return repository.require(id).getTitle();
    }

    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:read') and " +
        "hasPermission(#document, 'READ')"
    )
    public String readByObject(@P("document") Document document) {
        // Chỉ tin ID khi tìm bản ghi THẬT; không trả title caller gửi.
        return repository.require(document.getId()).getTitle();
    }

    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:browse')"
    )
    @PostFilter(
        "hasAuthority('document:read') and " +
        "hasPermission(filterObject, 'READ')"
    )
    public List<Document> visibleDocuments() {
        return repository.all();
    }
}
```

Phương thức `readById` dùng overload `(Authentication, Serializable, String, Object)`, còn `readByObject` dùng overload `(Authentication, Object, Object)`. Nhờ cùng canonical identity và ACL, chúng cho cùng quyết định với cùng ID.

`visibleDocuments` sử dụng `@PostFilter`: sau khi nhận danh sách, Method Security đánh giá biểu thức **cho từng phần tử**. Điều kiện `hasAuthority` được kiểm tra trong filter để user chỉ có `document:browse` mà thiếu `document:read` **không nhìn thấy object nhờ ACE**. Lọc này phù hợp demo nhỏ; production nên đẩy predicate quyền hoặc batch ACL lookup xuống tầng dữ liệu để tránh N+1 và lỗi phân trang.

**Không được** dùng `this.readById(...)` từ cùng bean rồi kỳ vọng chắc chắn chạy advice. Mọi lời gọi trong CLI/test đều lấy `DocumentService` từ Spring, bảo đảm gọi qua proxy.

### 7.6. Bật Method Security và chạy nhiều principal

**`src/main/java/demo/AclPermissionDemoApplication.java`:**

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
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class AclPermissionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AclPermissionDemoApplication.class, args);
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator aclPermissionEvaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(aclPermissionEvaluator);
        return handler;
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(DocumentService documents) {
        return args -> {
            try {
                signIn("alice", "document:read", "document:browse");
                System.out.println("ALICE_ID_11: "
                    + documents.readById(11L));
                System.out.println("ALICE_OBJECT_11: "
                    + documents.readByObject(
                        new Document(11L, "caller-supplied-fake")));
                System.out.println("ALICE_VISIBLE: "
                    + ids(documents.visibleDocuments()));
                denied("ALICE_ID_12", () -> documents.readById(12L));

                signIn("bob", "document:read", "document:browse");
                System.out.println("BOB_ID_12: "
                    + documents.readById(12L));
                System.out.println("BOB_VISIBLE: "
                    + ids(documents.visibleDocuments()));

                signIn("carol", "document:browse");
                denied("CAROL_ID_13", () -> documents.readById(13L));
                System.out.println("CAROL_VISIBLE: "
                    + ids(documents.visibleDocuments()));

                signIn("root", "document:read", "document:browse");
                denied("ROOT_OWNER_NO_READ", () -> documents.readById(11L));

                anonymous();
                denied("ANONYMOUS_ID_11", () -> documents.readById(11L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static List<Long> ids(List<Document> docs) {
        return docs.stream().map(Document::getId).toList();
    }

    private static void signIn(String name, String... authorityNames) {
        var authorities = Arrays.stream(authorityNames)
            .map(SimpleGrantedAuthority::new)
            .toList();
        var auth = new UsernamePasswordAuthenticationToken(
            name, "demo-only", authorities
        );
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    private static void anonymous() {
        var token = new AnonymousAuthenticationToken(
            "demo-key", "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(token);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`@Profile("!test")` ngăn CLI scenario chạy khi integration test kích hoạt profile `test`. Mọi lần đổi user đều tạo `SecurityContext` mới, cuối chương trình dọn context trong `finally`.

**Cảnh báo:** `UsernamePasswordAuthenticationToken` được tự dựng với authorities chọn sẵn **chỉ dành cho mô phỏng**. Ứng dụng thật không được tạo token đã xác thực từ username/role do HTTP client gửi; phải dùng authentication provider/validated bearer token/session.

### 7.7. Lệnh chạy và kết quả mong đợi

Trong thư mục dự án, nếu có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```bash
.\gradlew.bat bootRun
```

Nếu chưa có wrapper, dùng Gradle đã cài phiên bản tương thích để tạo wrapper hoặc chạy `gradle bootRun`.

**Dự kiến những dòng chương trình tự in**, không tính log Spring Boot:

```text
ALICE_ID_11: Alpha
ALICE_OBJECT_11: Alpha
ALICE_VISIBLE: [11]
ALICE_ID_12: DENIED
BOB_ID_12: Beta
BOB_VISIBLE: [11, 12]
CAROL_ID_13: DENIED
CAROL_VISIBLE: []
ROOT_OWNER_NO_READ: DENIED
ANONYMOUS_ID_11: DENIED
```

Giải thích từng nhóm:

- Alice có authority và ACE READ trên `#11` nên đọc bằng **ID hoặc object** đều được. Dù object client truyền title giả, service trả title server là `Alpha`.
- Alice không có ACE READ trên `#12`, nên bị từ chối. Danh sách sau `@PostFilter` chỉ có `#11`.
- Bob có ACE READ trên cả `#11`/`#12` và có authority nên thấy hai tài liệu.
- Carol có ACE READ trên `#13` nhưng không có authority chung `document:read`, nên method đọc bị từ chối và danh sách bị lọc thành rỗng.
- Root là owner ACL, đã được mô phỏng có authority `document:read`, nhưng vẫn không có ACE READ trên `#11`, nên bị từ chối.
- Anonymous không qua điều kiện `isAuthenticated()` nên không được vào method.

**Các dòng trên là dự kiến từ logic của source, không phải khẳng định đã thực thi trong môi trường này.** Điều cần kiểm chứng khi chạy là cả hai overload và filter đều dùng **cùng** `AclPermissionEvaluator` đã đăng ký; nếu toàn bộ ca allow đều bị từ chối, hãy kiểm tra cấu hình expression handler và ObjectIdentity trước khi thay đổi policy.

## 8. Integration test với `@WithMockUser`

Tạo **`src/test/java/demo/DocumentServiceSecurityTest.java`**:

```java
package demo;

import java.io.Serializable;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService documents;

    @Autowired
    AclPermissionEvaluator evaluator;

    private static List<Long> ids(List<Document> docs) {
        return docs.stream().map(Document::getId).toList();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read", "document:browse"}
    )
    void bothHasPermissionOverloadsAgree() {
        assertEquals("Alpha", documents.readById(11L));
        assertEquals("Alpha", documents.readByObject(
            new Document(11L, "forged-title")));

        assertEquals(List.of(11L), ids(documents.visibleDocuments()));
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(12L));
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = {"document:read", "document:browse"}
    )
    void permissionsDifferBetweenUsers() {
        assertEquals("Alpha", documents.readById(11L));
        assertEquals("Beta", documents.readById(12L));
        assertEquals(
            List.of(11L, 12L),
            ids(documents.visibleDocuments())
        );
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:browse")
    void aclGrantIsNotEnoughWithoutGeneralAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(13L));
        assertEquals(List.of(), ids(documents.visibleDocuments()));
    }

    @Test
    @WithMockUser(
        username = "root",
        authorities = {"document:read", "document:browse"}
    )
    void aclOwnerDoesNotAutomaticallyHaveReadAce() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(11L));
        assertEquals(List.of(), ids(documents.visibleDocuments()));
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(11L));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read", "document:browse"}
    )
    void evaluatorRejectsNullAndUnsupportedPermission() {
        var authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertFalse(evaluator.hasPermission(
            authentication, (Object) null, "READ"
        ));

        assertFalse(evaluator.hasPermission(
            authentication, (Serializable) 12L,
            "demo.Document", "READ"
        ));

        assertTrue(evaluator.hasPermission(
            authentication, (Serializable) 11L,
            "demo.Document", "READ"
        ));
    }
}
```

Chạy:

```bash
./gradlew test
```

Tại sao test này có ý nghĩa?

- `@SpringBootTest` nạp cấu hình thật: `@EnableMethodSecurity`, expression handler, evaluator, ACL service.
- `@WithMockUser` đặt `Authentication` cho từng test qua `spring-security-test`.
- `@Autowired DocumentService` gọi qua **Spring-managed proxy**, nên annotation được thực thi. Tự `new DocumentService(repository)` sẽ bypass advice.
- Test có **allow và deny**; nếu evaluator chưa được kết nối với handler, đường allow sẽ fail thay vì chỉ có test deny pass.
- Test object giả title vẫn trả title server; ACL không sử dụng dữ liệu client để tự cho quyền.
- Test root cho thấy ACL owner không đồng nghĩa READ; test carol cho thấy ACE riêng không thay authority chức năng.

Với production, nên bổ sung test permission `WRITE`, `DELETE`, `ADMINISTRATION`, ACE DENY rõ, group SID, parent ACL, ACL missing, SID missing, tenant-crossing, revoke và cache stale.

## 9. Chuyển từ in-memory `AclService` sang JDBC ACL

Trong ứng dụng Spring Boot thực, không dùng `InMemoryAclService` lưu mãi ACL trong mỗi process. Thay bằng `JdbcMutableAclService` và những thành phần nó phụ thuộc:

```text
Method Security
   |
   v
AclPermissionEvaluator
   |
   v
AclService / JdbcMutableAclService
   |
   +--> AclCache / SpringCacheBasedAclCache
   |
   +--> BasicLookupStrategy
                |
                v
         DataSource + ACL schema
                |
                v
     AclImpl + ACE/SID/owner/parent
```

### 9.1. Những bảng ACL cần có

| Bảng | Vai trò |
| --- | --- |
| `acl_sid` | Principal SID hoặc granted-authority SID |
| `acl_class` | Tên loại domain object |
| `acl_object_identity` | Object ID, owner SID, ACL cha, inheritance |
| `acl_entry` | ACE order, SID, permission mask, grant/deny và audit flags |

ACL JDBC không tự tạo khi bạn lưu một JPA entity. Ứng dụng phải triển khai **lifecycle ACL**: tạo ACL khi object tạo, thêm ACE, đổi/thu hồi ACE, cập nhật owner, xóa ACL khi object xóa. Hãy dùng schema chính thức tương thích DB và có transaction, khóa/index cần thiết.

### 9.2. Mẫu cấu hình JDBC

Đây là **mảnh cấu hình tích hợp**, không phải file demo cần thêm cùng `InMemoryAclService`. Nó giả định bạn đã bỏ bean in-memory và đã có DataSource, driver, ACL schema:

```java
@Configuration
@EnableMethodSecurity
class JdbcAclConfiguration {

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy grants,
            AclAuthorizationStrategy changes) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"), grants, changes);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy changes,
            PermissionGrantingStrategy grants) {
        return new BasicLookupStrategy(
            dataSource, cache, changes, grants);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(
            dataSource, lookup, cache);
    }
}
```

Những import chính cho đoạn minh họa:

```java
import javax.sql.DataSource;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

**Quan trọng về import:** `AclAuthorizationStrategy` là `org.springframework.security.acls.domain.AclAuthorizationStrategy`; còn `PermissionGrantingStrategy` và `AclCache` nằm trong `org.springframework.security.acls.model`. `LookupStrategy` là interface thuộc `org.springframework.security.acls.jdbc`, không ở package `model`.

Phần Gradle cần có thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework:spring-context-support'
    runtimeOnly 'com.h2database:h2'
}
```

Đây chỉ là **mảnh dependency thêm** vào dự án có Spring Security/ACL và dependency management; với DB thật dùng driver phù hợp. `JdbcMutableAclService` cần schema JDBC ACL đầy đủ, cấu hình identity generation và SQL tương thích database.

### 9.3. Tạo ACE bằng `MutableAclService`

```java
// MẢNH CODE thuộc một service quản trị đã được phân quyền và có transaction.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 11L);
MutableAcl acl = mutableAclService.createAcl(oid);

acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    new PrincipalSid("alice"),
    true
);

mutableAclService.updateAcl(acl);
```

**Không dùng đoạn này để chạy lại với ACL đã tồn tại**: `createAcl` được thiết kế cho một identity chưa có ACL. Khi cập nhật ACE, đọc `MutableAcl` hiện tại rồi sửa và `updateAcl`.

Các mutator trên `AclImpl` có `AclAuthorizationStrategy` để kiểm soát quyền sửa ACL, khác với `PermissionGrantingStrategy` dùng xét READ trên object. Service còn phải xác minh tenant, recipient, loại quyền được grant, self-grant, audit và transaction. Đừng cho client gửi `username` rồi tạo một token đặc quyền để tự seed ACE trong production.

### 9.4. Permission factory và SID strategy tùy chỉnh

`AclPermissionEvaluator` có các setter:

```java
evaluator.setPermissionFactory(permissionFactory);
evaluator.setSidRetrievalStrategy(sidRetrievalStrategy);
evaluator.setObjectIdentityRetrievalStrategy(objectStrategy);
evaluator.setObjectIdentityGenerator(identityGenerator);
```

Đoạn trên là **mảnh minh họa**, các biến strategy phải được tạo/cấu hình trước. Khi cần custom masks hay tenant-scoped SID, các chiến lược phải thống nhất từ **lúc tạo ACE** tới **lúc evaluate**.

Ví dụ nếu business có permission `"EXPORT"` hoặc `"APPROVE"`, không nên chỉ đổi string trong annotation rồi mong hệ thống tự hiểu. Định nghĩa `Permission` mask không xung đột, `PermissionFactory` mapping, ACE và test.

Nếu domain object có ID dạng record `id()` mà không có `getId()`, cân nhắc custom `ObjectIdentityRetrievalStrategy` thay vì dựa vào default reflection. Giữ `ObjectIdentity` ổn định xuyên version/schema để không lạc ACL.

## 10. `@PreAuthorize`, `@PostAuthorize`, `@PostFilter`: chọn ranh giới hợp lý

### 10.1. `@PreAuthorize`: biết ID trước khi chạy

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document find(Long id) {
    return repository.require(id);
}
```

Phù hợp khi có ID và cần chặn **trước khi load hoặc ghi dữ liệu**. Trong sản phẩm, thường kết hợp thêm `isAuthenticated`, `hasAuthority` và tenant policy. Với thao tác có side effect, **before-method** authorization là lớp cần thiết.

### 10.2. `@PostAuthorize`: chỉ biết object sau khi chạy

```java
@PostAuthorize(
    "returnObject != null and hasPermission(returnObject, 'READ')"
)
public Document loadDocument(Long id) {
    return repository.require(id);
}
```

Phù hợp khi decision cần instance đã trả về. Nó **không** ngăn body chạy, nên không dùng làm lớp duy nhất bảo vệ lệnh thay dữ liệu đã commit. Nếu object từ repository có lazy references, policy phải tính toán chi phí và tránh lộ metadata qua exception/log.

### 10.3. `@PostFilter`: lọc từng phần tử

```java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> findAllDocuments() {
    return new ArrayList<>(repository.findAll());
}
```

Đây là **mảnh minh họa**, giả định repository có `findAll`. Trong demo ở mục 7, list mutable để interceptor có thể loại phần tử. Một evaluator ACL tra database **trên từng phần tử** có thể tạo N+1 query, đặc biệt khi list lớn.

Với hệ thống thật, ưu tiên SQL/query ACL set-based, batch `AclService.readAclsById(...)` hoặc một authorization service hỗ trợ batch thay vì `findAll` rồi hậu lọc toàn bộ. Nếu phân trang **trước** khi `@PostFilter`, số phần tử/trang và `totalElements` có thể sai. Đẩy điều kiện quyền vào truy vấn **trước phân trang** khi có thể.

### 10.4. `@PreFilter`: lọc phần tử đầu vào

```java
@PreFilter("hasPermission(filterObject, 'WRITE')")
public void processDocuments(List<Document> documents) {
    // Chỉ nhận những phần tử còn lại sau khi filter.
}
```

Mảnh này không độc lập. Với batch update có yêu cầu **all-or-nothing**, `@PreFilter` có thể không phù hợp vì nó **loại phần tử không được phép** thay vì từ chối toàn bộ operation. Kiểm tra semantics và transaction trước khi dùng.

## 11. Các nguy cơ bảo mật khi tích hợp `AclPermissionEvaluator`

### 11.1. Không có ACL không có nghĩa là public

Nếu `AclService` không tìm thấy identity hoặc không có ACE phù hợp, đừng tự fallback thành `permitAll`. `AclPermissionEvaluator` và cơ chế ACL có cách xử lý `NotFoundException`; ở ranh giới ứng dụng, trạng thái thiếu quyền/thiếu dữ liệu phải được xử lý **fail closed**, không biến exception thành `allow=true`.

Tương tự, permission name không hợp lệ, `targetType` sai, authentication chưa xác minh hoặc SID không đủ đều không phải lý do cấp quyền.

### 11.2. Không dùng ACL owner thay thế permission

Một lập trình viên có thể viết:

```java
// KHÔNG nên dùng nếu nghiệp vụ không quy định owner ACL có READ.
return acl.getOwner().equals(new PrincipalSid(auth))
    || acl.isGranted(permissions, sids, false);
```

Dòng này mở một đường READ mới chỉ dựa vào ACL owner. Nếu nghiệp vụ thật sự cần owner được đọc, phải đặc tả và kiểm thử rule riêng; không coi đó là hành vi mặc định của Spring ACL.

### 11.3. Quyền chức năng và quyền đối tượng nên kết hợp AND

Trong demo:

```java
hasAuthority('document:read')
and hasPermission(#id, 'demo.Document', 'READ')
```

đảm bảo hai điều kiện đều cần đúng. Không dùng OR nếu yêu cầu tất cả caller có authority chung **và** ACE riêng. OR có thể bỏ qua ACL hoặc cho một user có ACE nhưng đã bị thu hồi quyền chức năng vẫn truy cập.

### 11.4. Tenant là ranh giới bổ sung

`ObjectIdentity` thường gồm class và ID. Nếu ID chỉ unique **trong từng tenant**, hai tenant có thể có cùng `"demo.Document", 11`, dẫn đến đụng identity. Dùng globally unique ID hoặc định nghĩa namespace đáng tin cho ACL/object identity, và kiểm tra tenant ở service/repository. Chỉ ACL grant chưa đủ để chứng minh caller đang thao tác đúng tenant nếu định danh không được tách.

Nếu tài liệu có field-level visibility, `READ` trên object không nhất thiết được phép xem **mọi trường**. Cần policy theo field hoặc dựng DTO đã được redaction phù hợp.

### 11.5. ACL cache có thể lỗi thời sau revoke

`SpringCacheBasedAclCache` có thể cache ACE và owner. Khi grant, revoke, chuyển owner hoặc đổi parent ACL, phải invalidation đúng. Trong cluster, cache local của node A không tự invalidation node B. Nếu còn cache decision `(user, object, action)`, phải kiểm soát permission version và thời hạn; key chỉ theo object ID là nguy hiểm.

### 11.6. TOCTOU với lệnh ghi

`@PreAuthorize` kiểm tra quyền ở thời điểm T1, còn `UPDATE`/`DELETE` có thể xảy ra T2. Nếu owner/tenant/ACL thay đổi giữa hai thời điểm, có **time of check, time of use**. Với thao tác quan trọng, kiểm tra điều kiện ngay trong transaction/update, dùng locking/version theo nhu cầu và kiểm tra row count. Không tự coi `@Transactional` là giải pháp đủ nếu isolation không phù hợp.

### 11.7. Không chỉ bảo vệ controller

Service có thể được gọi từ HTTP controller, scheduler, message listener hoặc một service khác. Hãy bảo vệ ranh giới nghiệp vụ quan trọng bằng Spring Method Security hoặc `AuthorizationManager` phù hợp; chú ý self-invocation/proxy. Cần test qua Spring context để khẳng định advice đang hoạt động.

## 12. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `hasPermission` luôn từ chối cả user có ACE | Chưa gắn `AclPermissionEvaluator` vào handler | Tạo `static @Bean MethodSecurityExpressionHandler`, gọi `setPermissionEvaluator` |
| Dạng ID chạy, dạng object lỗi | Object thiếu `getId()` hoặc retrieval strategy sai | Thêm public `getId()` hoặc tùy biến strategy |
| Dạng object chạy nhưng dạng ID không tìm ACL | `targetType` không khớp canonical class name | Dùng `"demo.Document"` hoặc mapping đúng |
| `'read'` không nhận diện | Factory đăng ký `READ` nhưng không có alias `read` | Dùng `'READ'` hoặc cấu hình `PermissionFactory` |
| User sai vẫn thấy dữ liệu | Bỏ qua tenant/authority hoặc tin DTO owner | AND với authority/tenant policy, tra dữ liệu server |
| ACL owner được đọc dù không có ACE READ | Code tự bypass bằng `Acl.getOwner()` | Tách quản trị ACL khỏi object permission |
| Không có ACL mà request vẫn thành công | Fallback fail-open | Deny hoặc xử lý lỗi hạ tầng thích hợp |
| `@PreAuthorize` không chạy | Chưa `@EnableMethodSecurity`, gọi bằng `new`, self-invocation | Gọi qua Spring-managed proxy |
| Anonymous được cấp quyền nhầm | Chỉ kiểm tra token `isAuthenticated()` hoặc cấp ACE lạ | Dùng security expression/identity policy có phân biệt anonymous |
| Danh sách 1.000 item chậm | `@PostFilter` và ACL lookup theo từng phần tử | SQL/batch ACL, pagination đúng |
| Cache READ cũ sau revoke | ACL cache hoặc decision cache stale | Invalidation sau commit và trên các node |
| `UnloadedSidException` | ACL nạp một subset SID rồi xét SID khác | Nạp đủ SID hoặc fail closed |
| `NotFoundException` | Không đủ ACL/ACE để quyết định | Không đổi exception thành allow; kiểm tra identity và ACL |
| Quyền thiếu sau đổi username/tenant | SID mapping đã lưu không còn khớp | Stable ID, tenant namespace và migration ACE |
| Custom `PermissionFactory` gây sai quyền | Mask/name không khớp dữ liệu | Kiểm thử mapping cùng ACE thực tế |
| Test chỉ deny pass nhưng allow fail | Evaluator chưa được gọi hoặc ACL thiếu | Test allow và deny, trace bean + identity |
| `@PostAuthorize` không ngăn thay đổi dữ liệu | Hậu kiểm diễn ra sau body | Dùng before-check và consistency ở DB cho side effect |

### Checklist gỡ lỗi nhanh

1. Gọi đúng Spring bean/proxy chưa? `AopUtils.isAopProxy(service)` chỉ là bước hỗ trợ, cần test hành vi thực.
2. `@EnableMethodSecurity` được nạp chưa?
3. Có `MethodSecurityExpressionHandler` tùy chỉnh và nó gọi `setPermissionEvaluator` với **đúng bean** chưa?
4. Expression dùng overload object hay ID? Object có `public getId()`? `targetType` khớp class trong ACL không?
5. Permission factory có tên `'READ'` tương ứng `BasePermission.READ` không?
6. `Authentication` có principal/authorities/SIDs phù hợp ACL đã lưu không?
7. `AclService` có đọc đúng `ObjectIdentity`, ACE, parent, SID đã load không?
8. Có thêm quy tắc authority/tenant/status nào làm `and` trả false không?
9. Cache ACL/permission decision đã invalidation chưa?
10. Test có case cho phép, từ chối, anonymous, thiếu object, cross-tenant và update/revoke không?

## 13. Bài tập tự kiểm tra

1. **`hasPermission(#doc, 'READ')` gọi overload nào?**  
   `(Authentication, Object targetDomainObject, Object permission)`, dùng object identity retrieval.

2. **`hasPermission(#id, 'demo.Document', 'READ')` gọi overload nào?**  
   `(Authentication, Serializable targetId, String targetType, Object permission)`, dùng identity generator.

3. **Vì sao không truyền `Authentication` như tham số SpEL?**  
   Method Security expression root đã lấy authentication hiện tại và truyền cho evaluator.

4. **Có bean `AclPermissionEvaluator` nhưng `hasPermission` vẫn deny: kiểm tra gì đầu tiên?**  
   Expression handler đã gọi `setPermissionEvaluator` chưa; bean được đăng ký đủ sớm chưa.

5. **Một Java record chỉ có accessor `id()` dùng object overload mặc định được không?**  
   Không nên giả định được. `ObjectIdentityImpl(Object)` yêu cầu `getId()`; thêm method hoặc tùy biến strategy.

6. **Dùng `'Document'` thay `'demo.Document'` có sao không?**  
   Có thể không tìm đúng ObjectIdentity đã lưu. Cần canonical type nhất quán.

7. **`BasePermission.ADMINISTRATION` có tương đương `READ` không?**  
   Không. Quyền quản trị ACL và đọc domain object là hai phép kiểm tra khác nhau.

8. **Carol có ACE READ nhưng thiếu `document:read`, với policy AND thì kết quả?**  
   Từ chối, do authority chức năng không đủ.

9. **Vì sao title do client gửi không nên được trả trực tiếp sau khi được authorize?**  
   Vì đó là dữ liệu không tin cậy; service nên lấy bản ghi thật từ server theo ID được bảo vệ.

10. **Tại sao `@PostFilter` trên 1.000 object có thể sinh N+1?**  
    Vì mỗi phần tử có thể khiến evaluator gọi ACL lookup riêng.

11. **`@PostAuthorize` có đủ để bảo vệ thao tác ghi không?**  
    Không. Hậu kiểm diễn ra sau khi thân method chạy và có thể đã có side effect.

12. **Nếu API dùng tenant-scoped IDs, phải làm gì với ACL ObjectIdentity?**  
    Đảm bảo identity unique theo tenant bằng thiết kế phù hợp và kiểm tra tenant từ principal/server.

13. **Nếu revoke ACE nhưng cache chưa cập nhật, rủi ro gì?**  
    Caller có thể nhận quyết định theo quyền cũ; cần invalidation phù hợp transaction và cluster.

14. **Test nào chứng minh cả hai overload dùng cùng ACL?**  
    Cùng principal và ID, assert `readById`/`readByObject` đều allow hoặc cùng deny, kết hợp test fake object.

## 14. Nguồn tham khảo chính thức

1. [Spring Security 6.5 — ACLs](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): mô hình ACL và mẫu cấu hình evaluator/Method Security/JDBC.
2. [Spring Security 6.5 — `AclPermissionEvaluator` Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): hai overload và các strategy setters.
3. [Spring Security 6.5 — `PermissionEvaluator` interface](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html): hợp đồng object và ID.
4. [Spring Security 6.5 — `ObjectIdentityImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/ObjectIdentityImpl.html): constructor từ object đòi `getId()`, hoặc từ class + ID.
5. [Spring Security 6.5 — `DefaultPermissionFactory`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/DefaultPermissionFactory.html): ánh xạ tên/mask permission.
6. [Spring Security 6.5 — `AclService`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclService.html): đọc một hoặc nhiều ACL, có thể theo SID.
7. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, SpEL và static expression handler.
8. [Spring Security 6.5 — `AclImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html): ACE, owner, permission strategy, inheritance.
9. [Spring Security — Spring AOP proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation và giới hạn interception.

**Kết luận:** `AclPermissionEvaluator` là cầu nối từ **`hasPermission(...)` trong Method Security** tới **ACL đã lưu**. Đường object cần `getId()`/identity strategy phù hợp; đường ID cần canonical type; cả hai cần permission factory, SID từ authentication đáng tin và `AclService` đúng. Kết hợp ACL với authority/tenant policy theo phép AND, kiểm thử qua Spring proxy và quản lý cache/transaction khi quyền thay đổi.