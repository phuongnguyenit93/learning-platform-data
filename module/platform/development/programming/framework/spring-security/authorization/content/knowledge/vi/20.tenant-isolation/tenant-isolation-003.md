# Kiểm chứng tenant trong URL, header hoặc dữ liệu đầu vào — Spring Security Authorization

## 1. Vấn đề: tenant do client yêu cầu không phải tenant được cấp quyền

Trong hệ thống SaaS nhiều tổ chức, một request có thể mang tenant ở nhiều vị trí:

```http
PUT /api/tenants/t1/documents/101
Authorization: Bearer <access-token>
X-Tenant-Id: t1
Content-Type: application/json

{"tenantId":"t1","title":"Báo cáo mới"}
```

Ví dụ trên chỉ mô tả request, không phải một access token thật. Cả `t1` trong **URL**, `X-Tenant-Id` trong **header** và `tenantId` trong **JSON body** đều là những giá trị do client có thể sửa. Chúng giúp diễn tả *tenant đang được yêu cầu* nhưng **không chứng minh** người gọi có quyền trong tenant đó.

Giả sử Alice là thành viên tenant `t1`, không thuộc `t2`. Nếu Alice đổi mọi giá trị thành `t2`, backend **không được** tự chấp nhận. Ngược lại, nếu Alice yêu cầu `t1` nhưng document ID thuộc `t2`, backend cũng phải từ chối.

Một quyết định đúng cần đối chiếu **ba nguồn sự thật khác nhau**:

1. **Danh tính đã xác thực:** `Authentication` do Spring Security cung cấp sau khi xác thực credential/session/JWT với provider đáng tin.
2. **Membership và role theo tenant:** các tenant mà danh tính này thực sự có quyền, được quản lý từ database/IAM hoặc entitlement được issuer đáng tin phát hành.
3. **Tenant canonical của tài nguyên:** `document.tenant_id` được đọc từ data store phía server, không phải trường tenant trong request.

```text
Request selectors                    Trusted evidence
-----------------                    ----------------
Path /tenants/t1      ──candidate──► Authentication: alice
Header X-Tenant-Id:t1 ──candidate──► Membership(alice,t1) = true
Body tenantId:t1      ──candidate──► Document#101.tenant_id = t1
                                       │
                                       ▼
                           Permission(owner/share/admin, action)
                                       │
                             allow only if ALL pass
```

**Quy tắc:** Tenant từ request là *đề xuất chọn phạm vi*, không phải một credential. Mọi kiểm tra phải **fail-closed** khi dữ liệu sai, thiếu quyền hoặc các nguồn tenant mâu thuẫn.

## 2. Mô hình đe dọa và trust boundary

| Nguồn | Ai điều khiển? | Vai trò hợp lý | Không được dùng để |
|---|---|---|---|
| `/tenants/{tenantId}` | Client | Chọn tenant mong muốn | Cấp role, bỏ qua membership |
| `X-Tenant-Id` | Client, trừ trusted gateway đặc biệt | Chọn scope/đối chiếu path | Tự tạo `Authentication` |
| JSON `tenantId` | Client | Chỉ định tenant của yêu cầu CREATE, hoặc xác nhận scope của UPDATE | Mass-assign tenant lên entity |
| Query `?tenant=t2` | Client | Lọc dữ liệu trong scope đã chứng minh | Truy vấn vượt tenant |
| `Host`/subdomain | Có thể bị ảnh hưởng bởi client/proxy | Tenant routing sau khi kiểm tra hostname | Tự coi hostname là bằng chứng membership |
| `X-User`/`X-Role` | Client nếu không có gateway đáng tin | Không dùng để xác thực | Mạo danh principal/authority |
| JWT đã verify | Identity provider đáng tin | Xác nhận subject, issuer, claims/entitlements | Bỏ qua resource tenant hay revoke policy |
| Database membership | Server/IAM | Quyền thuộc tenant hiện hành | Tin dữ liệu do client tự sửa |
| `document.tenant_id` | Server data store | Tenant sở hữu bản ghi | Được sửa bằng endpoint rename tùy ý |

Bốn kiểu tấn công quan trọng:

- **Horizontal cross-tenant BOLA:** Alice của t1 thay route thành t2 hoặc đoán ID của tài liệu t2.
- **Header spoofing:** client thêm `X-Tenant-Id: t2`, `X-User: manager` hoặc `X-Role: ROLE_ADMIN` để mạo danh.
- **Mass assignment:** JSON update chứa `{"tenantId":"t2","owner":"attacker"}`; nếu mapper ghi thẳng DTO vào entity sẽ đổi scope/owner trái phép.
- **Confused-deputy routing:** gateway/service A kiểm tra path t1 nhưng service B lại chọn database bằng header t2 chưa được kiểm tra. Hai service vô tình dùng **hai tenant context khác nhau**.

Theo nguyên tắc chống Broken Object Level Authorization của OWASP, bất kỳ endpoint nào nhận object ID và truy cập một object đều phải xác minh người dùng có quyền thực hiện hành động trên **chính object đó**, không chỉ xác minh họ đã đăng nhập.

### 2.1. Không nhầm xác thực với ủy quyền

`Authentication.isAuthenticated() == true` chỉ chứng minh phiên gọi đã qua một cơ chế xác thực; nó chưa quyết định tenant nào được phép. Ngay cả token JWT đúng chữ ký vẫn có thể có membership đã bị thu hồi từ sau khi phát hành.

Một mô hình tối thiểu:

```text
Authenticated principal
AND request tenant is well-formed
AND serverMembership(principal, requestTenant)
AND record.tenantId == requestTenant
AND actionAllowed(principal, record)
```

Ở đây điều kiện cuối có thể là owner, share VIEWER/EDITOR, admin binding theo tenant, permission evaluator hoặc ACL. **Membership một tenant không có nghĩa được đọc mọi bản ghi trong tenant đó.**

## 3. Định nghĩa hợp đồng cho URL, header và body

Không có một vị trí tenant bắt buộc cho mọi ứng dụng. Điều cần thiết là chọn một hợp đồng và áp dụng nhất quán.

Bài này chọn:

- **GET:** `/api/tenants/{tenantId}/documents/{id}`. Path là tenant được yêu cầu. Header `X-Tenant-Id` tùy chọn; nếu được gửi phải **trùng chính xác** path.
- **POST:** `/api/tenants/{tenantId}/documents`. Body `tenantId` bắt buộc và phải trùng path. Header nếu có cũng phải trùng.
- **PUT:** `/api/tenants/{tenantId}/documents/{id}`. Body `tenantId` phải trùng path; header nếu có phải trùng; document thật phải thuộc tenant đó.
- **Mọi method:** principal phải có membership phía server và action permission trên dữ liệu tương ứng.

| Path | Header | Body | Membership | DB record tenant | Quyết định |
|---|---|---|---|---|---|
| t1 | không gửi | GET | t1 | t1 | Xét owner/share/action |
| t1 | t1 | t1 | t1 | t1 | Xét owner/share/action |
| t1 | t2 | t1 | t1 | t1 | Deny: header khác path |
| t1 | t1 | t2 | t1 | t1 | Deny: body khác path |
| t2 | t2 | t2 | chỉ có t1 | t2 | Deny: không có membership |
| t1 | t1 | t1 | t1 | t2 | Deny: record thuộc tenant khác |
| t1 | t1 | t1 | t1 | t1 | Vẫn phải xét permission cụ thể |

Nếu các nguồn mâu thuẫn, **không tự ưu tiên header hoặc body**, không lặng lẽ chọn nguồn cuối cùng. API có thể trả 403 hoặc 404 theo chính sách tránh tiết lộ tồn tại; demo dùng 403 cho lời gọi authenticated nhưng bị từ chối.

### 3.1. Tenant ID phải có dạng canonical

Đừng so sánh `t1` với `t10` bằng `startsWith`; đừng coi `t1` và `T1` giống nhau nếu hệ thống không định nghĩa như vậy. Nếu tenant ID dùng UUID, slug hoặc subdomain, kiểm tra định dạng/độ dài và quy tắc normalize tại một chỗ đáng tin.

Header trùng tên hoặc `X-Tenant-Id: t1, t2` phải có cách xử lý rõ (thường là reject đối với header yêu cầu một giá trị). Không lấy một phần tử bất kỳ rồi bỏ qua phần còn lại.

### 3.2. Status 403 và 404

Đối với resource ID tồn tại ở tenant khác, trả **404** có thể tránh để attacker dò sự tồn tại của record. **403** phù hợp khi muốn thông báo rõ user không được phép. Chọn một chính sách và test nhất quán, tránh rò qua thông báo lỗi, total count, thời gian truy vấn hoặc API tìm kiếm. Mã trạng thái không thay thế authorization.

## 4. Cách viết policy trong Spring Security

### 4.1. Sai: dùng tenant input làm authority

```java
// PHẢN VÍ DỤ - không biên dịch độc lập.
String tenant = request.getHeader("X-Tenant-Id");
Authentication auth = new UsernamePasswordAuthenticationToken(
    request.getHeader("X-User"), null,
    List.of(new SimpleGrantedAuthority("tenant:" + tenant))
);
SecurityContextHolder.getContext().setAuthentication(auth);
```

Dữ liệu attacker gửi được nâng thành authority mà không có bằng chứng membership hoặc xác thực danh tính. Đây là **privilege escalation**. Backend không nên tự lắp `Authentication` theo header tùy ý.

### 4.2. Đúng về kiến trúc: request chỉ chọn scope

```text
Spring authentication filter xác thực user
    ↓
Controller lấy tenant candidate từ URL/header/body
    ↓
Service policy: Authentication + server membership
    ↓
Query resource bằng ID VÀ tenant đã verified
    ↓
Kiểm tra owner/share/admin và trạng thái nghiệp vụ
    ↓
Thực hiện READ/EDIT/CREATE có guard ở repository
```

Bật Method Security:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {
    // ...
}
```

Kiểm tra ở service:

```java
@PreAuthorize(
    "@tenantPolicy.canRead(authentication,#tenantId,#id,#headerTenant)"
)
public DocumentView read(
        @P("tenantId") String tenantId,
        @P("id") Long id,
        @P("headerTenant") String headerTenant) {
    // ...
}
```

Đây là **các đoạn mô hình hóa**, cần project/các class để chạy. `@P` cố định tên tham số SpEL. `@PreAuthorize` chặn trước khi target method chạy, nhưng caller phải đi qua Spring AOP proxy; tự gọi `this.read(...)` trong cùng bean có thể bypass advice ở proxy mode.

Một role admin cũng phải được giới hạn scope. Không viết `hasRole('ADMIN') or @tenantPolicy.canRead(...)` nếu nhánh admin bỏ luôn tenant boundary. Tốt hơn, đặt admin binding theo chính tenant trong policy phía server.

## 5. Ví dụ đầy đủ: Java 17, Spring Boot 3.5.6, Spring Security 6.5.x

Demo lưu data trong RAM để tập trung vào việc xác minh tenant và quyền truy cập. Nó có REST GET/POST/PUT với tenant ở URL, header, body, `@PreAuthorize`, source membership phía server và integration tests MockMvc/JUnit. Production thay RAM bằng JDBC/JPA với tenant-qualified queries như phần 7.

### 5.1. Cấu trúc

```text
tenant-input-verification/
  pom.xml
  src/main/java/com/example/tenant/
    TenantApplication.java
    SecurityConfig.java
    Catalog.java
    TenantPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/tenant/
    TenantVerificationTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>tenant-input-verification</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot quản lý các dependency Spring Security phù hợp; không ép một version Security khác major. Demo dùng HTTP Basic để dễ thấy 401/403. Các test `@WithMockUser` dựng Authentication giả phục vụ **authorization**, không kiểm tra password hay chữ ký JWT.

### 5.3. Main application

**`src/main/java/com/example/tenant/TenantApplication.java`**

```java
package com.example.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantApplication.class, args);
    }
}
```

### 5.4. SecurityConfig

**`src/main/java/com/example/tenant/SecurityConfig.java`**

```java
package com.example.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/tenants/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

HTTP filter yêu cầu đăng nhập ở các route tenant nhưng không quyết định object-level permission; việc đó nằm ở `TenantPolicy`/`DocumentService`. CSRF được giữ mặc định; request POST/PUT trong test dùng `csrf()` để không vô hiệu hóa bảo vệ khi chạy cookie/session-based auth.

### 5.5. Catalog: record, membership và role binding tin cậy

**`src/main/java/com/example/tenant/Catalog.java`**

```java
package com.example.tenant;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
public class Catalog {
    public record Document(
            Long id, String tenantId, String owner, String title) {}

    public enum ShareLevel { VIEWER, EDITOR }

    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice", "bob", "manager"),
        "t2", Set.of("carol", "dave")
    );

    private final Set<String> adminBindings = Set.of("t1:manager");

    private final Map<String, ShareLevel> shares = Map.of(
        "101:bob", ShareLevel.VIEWER,
        "102:alice", ShareLevel.EDITOR
    );

    private final ConcurrentMap<Long, Document> docs =
        new ConcurrentHashMap<>();

    private final AtomicLong ids = new AtomicLong(300);

    public Catalog() {
        reset();
    }

    public synchronized void reset() {
        docs.clear();
        ids.set(300);
        docs.put(101L, new Document(
            101L, "t1", "alice", "Alice notes"));
        docs.put(102L, new Document(
            102L, "t1", "bob", "Bob plan"));
        docs.put(103L, new Document(
            103L, "t1", "manager", "Manager private"));
        docs.put(201L, new Document(
            201L, "t2", "carol", "Carol report"));
    }

    public boolean member(String tenant, String username) {
        Set<String> usernames = members.get(tenant);
        return usernames != null && usernames.contains(username);
    }

    public boolean adminBinding(String tenant, String username) {
        return tenant != null && username != null
            && adminBindings.contains(tenant + ":" + username);
    }

    public ShareLevel share(Long id, String username) {
        return id == null || username == null ? null
            : shares.get(id + ":" + username);
    }

    public Document find(Long id) {
        return id == null ? null : docs.get(id);
    }

    public synchronized Document create(
            String tenant, String owner, String title) {
        long id = ids.incrementAndGet();
        Document doc = new Document(id, tenant, owner, title);
        docs.put(id, doc);
        return doc;
    }

    public synchronized Document rename(
            Long id, String tenant, String title) {
        Document previous = find(id);
        if (previous == null
                || !tenant.equals(previous.tenantId())) {
            return null;
        }
        Document updated = new Document(
            id, previous.tenantId(), previous.owner(), title
        );
        docs.put(id, updated);
        return updated;
    }
}
```

Fixture:
- Alice/Bob/manager là thành viên t1; Carol/Dave thuộc t2.
- Manager là admin t1 **khi có thêm** authority `ROLE_TENANT_ADMIN`, không được quản trị t2.
- Document#101 thuộc Alice/t1, Bob được share VIEWER.
- Document#102 thuộc Bob/t1, Alice được share EDITOR.
- Document#103 thuộc manager/t1, không share.
- Document#201 thuộc Carol/t2.

Đây là storage học tập, không phải database thực. Trong production phải dùng repository, ràng buộc FK, transaction và chiến lược invalidation membership/ACL.

### 5.6. TenantPolicy: chỉ tin Authentication và server data

**`src/main/java/com/example/tenant/TenantPolicy.java`**

```java
package com.example.tenant;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {
    private final Catalog data;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public TenantPolicy(Catalog data) {
        this.data = data;
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (required.equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    private boolean context(
            Authentication auth, String tenant, String headerTenant) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)
                || tenant == null || tenant.isBlank()) {
            return false;
        }

        // Header chỉ là selector. Có thì bắt buộc trùng path.
        if (headerTenant != null && !tenant.equals(headerTenant)) {
            return false;
        }

        // Bằng chứng membership đến từ server.
        return data.member(tenant, auth.getName());
    }

    private boolean scopedAdmin(Authentication auth, String tenant) {
        return hasAuthority(auth, "ROLE_TENANT_ADMIN")
            && data.adminBinding(tenant, auth.getName());
    }

    public boolean canRead(
            Authentication auth, String tenant, Long docId,
            String headerTenant) {
        if (!context(auth, tenant, headerTenant)) {
            return false;
        }
        Catalog.Document doc = data.find(docId);
        if (doc == null || !tenant.equals(doc.tenantId())) {
            return false;
        }
        String user = auth.getName();
        return doc.owner().equals(user)
            || data.share(docId, user) == Catalog.ShareLevel.VIEWER
            || data.share(docId, user) == Catalog.ShareLevel.EDITOR
            || scopedAdmin(auth, tenant);
    }

    public boolean canEdit(
            Authentication auth, String tenant, Long docId,
            String headerTenant, String bodyTenant) {
        if (!context(auth, tenant, headerTenant)
                || bodyTenant == null
                || !tenant.equals(bodyTenant)) {
            return false;
        }
        Catalog.Document doc = data.find(docId);
        if (doc == null || !tenant.equals(doc.tenantId())) {
            return false;
        }
        String user = auth.getName();
        return doc.owner().equals(user)
            || data.share(docId, user) == Catalog.ShareLevel.EDITOR
            || scopedAdmin(auth, tenant);
    }

    public boolean canCreate(
            Authentication auth, String tenant,
            String headerTenant, String bodyTenant) {
        return context(auth, tenant, headerTenant)
            && bodyTenant != null
            && tenant.equals(bodyTenant)
            && (hasAuthority(auth, "document:create")
                || scopedAdmin(auth, tenant));
    }
}
```

Đọc policy theo thứ tự:
1. Authentication không null, đã authenticated, không phải anonymous.
2. Tenant route hợp lệ và header nếu có phải trùng route.
3. Caller là thành viên đúng tenant trong nguồn server.
4. READ/EDIT: document phải tồn tại và có tenant canonical đúng route.
5. EDIT/CREATE: tenant body phải trùng tenant route.
6. Action permission: owner hoặc share đúng mức hoặc admin có cả role và tenant binding. CREATE cần `document:create` hoặc scoped admin.

Không có nhánh nào biến header `X-User`, `X-Role` hay body tenant thành role/authority. Unknown ID/tenant và mọi mismatch trả false.

### 5.7. DocumentService: tiền kiểm, không nhận owner từ body

**`src/main/java/com/example/tenant/DocumentService.java`**

```java
package com.example.tenant;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(
            Long id, String tenantId, String owner, String title) {}

    private final Catalog data;
    private final TenantPolicy policy;

    public DocumentService(Catalog data, TenantPolicy policy) {
        this.data = data;
        this.policy = policy;
    }

    private static Authentication caller() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    private static DocumentView toView(Catalog.Document doc) {
        return new DocumentView(
            doc.id(), doc.tenantId(), doc.owner(), doc.title());
    }

    @PreAuthorize(
        "@tenantPolicy.canRead(authentication," +
        "#tenantId,#documentId,#headerTenant)"
    )
    public DocumentView read(
            @P("tenantId") String tenantId,
            @P("documentId") Long documentId,
            @P("headerTenant") String headerTenant) {

        if (!policy.canRead(
                caller(), tenantId, documentId, headerTenant)) {
            throw new AccessDeniedException("Permission changed");
        }
        Catalog.Document doc = data.find(documentId);
        if (doc == null || !tenantId.equals(doc.tenantId())) {
            throw new AccessDeniedException("Tenant changed");
        }
        return toView(doc);
    }

    @PreAuthorize(
        "@tenantPolicy.canEdit(authentication," +
        "#tenantId,#documentId,#headerTenant,#bodyTenant)"
    )
    public DocumentView rename(
            @P("tenantId") String tenantId,
            @P("documentId") Long documentId,
            @P("headerTenant") String headerTenant,
            @P("bodyTenant") String bodyTenant,
            String title) {

        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Title required");
        }
        if (!policy.canEdit(
                caller(), tenantId, documentId,
                headerTenant, bodyTenant)) {
            throw new AccessDeniedException("Permission changed");
        }
        Catalog.Document result =
            data.rename(documentId, tenantId, title);
        if (result == null) {
            throw new AccessDeniedException("Tenant changed");
        }
        return toView(result);
    }

    @PreAuthorize(
        "@tenantPolicy.canCreate(authentication," +
        "#tenantId,#headerTenant,#bodyTenant)"
    )
    public DocumentView create(
            @P("tenantId") String tenantId,
            @P("headerTenant") String headerTenant,
            @P("bodyTenant") String bodyTenant,
            String title) {

        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Title required");
        }
        if (!policy.canCreate(
                caller(), tenantId, headerTenant, bodyTenant)) {
            throw new AccessDeniedException("Permission changed");
        }

        // Tenant = route đã xác minh; owner = principal đã xác thực.
        return toView(data.create(
            tenantId, caller().getName(), title));
    }
}
```

`@P` cho SpEL biết tên các method parameters. `@PreAuthorize` từ chối trước khi target chạy. Các nhánh recheck trong thân method giúp giảm nguy cơ trạng thái thay đổi nhưng **không thay thế** transaction/row lock khi production có cập nhật quyền đồng thời.

`rename` chỉ thay title, giữ nguyên tenant và owner. Nếu cần chuyển document sang tenant khác, phải có use case chuyển riêng kiểm tra quyền tại **tenant nguồn và đích**, các ràng buộc dữ liệu và mọi grants/ACL liên quan.

### 5.8. Controller: chuyển input sang service, không tự phong quyền

**`src/main/java/com/example/tenant/DocumentController.java`**

```java
package com.example.tenant;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants")
public class DocumentController {
    public record WriteBody(String tenantId, String title) {}

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{tenantId}/documents/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("documentId") Long documentId,
            @RequestHeader(
                name = "X-Tenant-Id", required = false
            ) String headerTenant) {
        return service.read(tenantId, documentId, headerTenant);
    }

    @PutMapping("/{tenantId}/documents/{documentId}")
    public DocumentService.DocumentView rename(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("documentId") Long documentId,
            @RequestHeader(
                name = "X-Tenant-Id", required = false
            ) String headerTenant,
            @RequestBody WriteBody request) {
        return service.rename(
            tenantId, documentId, headerTenant,
            request.tenantId(), request.title());
    }

    @PostMapping("/{tenantId}/documents")
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentService.DocumentView create(
            @PathVariable("tenantId") String tenantId,
            @RequestHeader(
                name = "X-Tenant-Id", required = false
            ) String headerTenant,
            @RequestBody WriteBody request) {
        return service.create(
            tenantId, headerTenant,
            request.tenantId(), request.title());
    }
}
```

`WriteBody` chỉ chấp nhận các field được sử dụng: tenantId và title. Owner không đến từ client. Nếu muốn **từ chối cả JSON có trường lạ** để chặn mass-assignment, cấu hình Jackson/Bean Validation tương ứng; demo bảo đảm không **sử dụng** trường owner do client khai.

## 6. Kiểm thử tích hợp: URL/header/body và quyền thật

Dùng `@SpringBootTest`, `@AutoConfigureMockMvc` và `@WithMockUser` để đi qua security filter và Method Security proxy. Các test stateful gọi `catalog.reset()` trước mỗi test. Test dùng CSRF token cho POST/PUT; vì HTTP Basic + Spring Security mặc định vẫn bật CSRF, bỏ token sẽ cho 403 trước khi kiểm tra tenant.

**`src/test/java/com/example/tenant/TenantVerificationTest.java`**

```java
package com.example.tenant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantVerificationTest {
    @Autowired MockMvc mvc;
    @Autowired Catalog catalog;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        catalog.reset();
    }

    private static String doc(String tenant, long id) {
        return "/api/tenants/" + tenant + "/documents/" + id;
    }

    private static String createPath(String tenant) {
        return "/api/tenants/" + tenant + "/documents";
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerReadsWithoutTenantHeader() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("t1"));
    }

    @Test
    @WithMockUser(username = "alice")
    void matchingHeaderIsAccepted() throws Exception {
        mvc.perform(get(doc("t1", 101))
                .header("X-Tenant-Id", "t1"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice")
    void headerTenantMismatchIsDenied() throws Exception {
        mvc.perform(get(doc("t1", 101))
                .header("X-Tenant-Id", "t2"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void routeCannotForgeResourceTenant() throws Exception {
        mvc.perform(get(doc("t1", 201)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void routeCannotGrantTenantMembership() throws Exception {
        mvc.perform(get(doc("t2", 201)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "carol")
    void actualMemberMayReadOwnTenant() throws Exception {
        mvc.perform(get(doc("t2", 201)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerShareCanReadWithinTenant() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob")
    void membershipDoesNotGrantEveryDocument() throws Exception {
        mvc.perform(get(doc("t1", 103)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mallory")
    void forgedTenantHeaderCannotCreateMembership() throws Exception {
        mvc.perform(get(doc("t1", 101))
                .header("X-Tenant-Id", "t1"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void forgedIdentityHeaderDoesNotMakeUserAdmin() throws Exception {
        mvc.perform(get(doc("t1", 103))
                .header("X-User", "manager")
                .header("X-Role", "ROLE_TENANT_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminReadsOwnTenantDocument() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminCannotReadOtherTenant() throws Exception {
        mvc.perform(get(doc("t2", 201)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "TENANT_ADMIN")
    void roleWithoutAdminBindingIsDenied() throws Exception {
        mvc.perform(get(doc("t1", 103)))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestGets401() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownRecordIsDenied() throws Exception {
        mvc.perform(get(doc("t1", 999)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "alice", authorities = "document:create")
    void createUsesVerifiedTenantAndAuthenticatedOwner()
            throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .header("X-Tenant-Id", "t1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"New note\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.tenantId").value("t1"))
            .andExpect(jsonPath("$.owner").value("alice"));
        assertEquals("alice", catalog.find(301L).owner());
    }

    @Test
    @WithMockUser(username = "alice")
    void createWithoutCapabilityIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "alice", authorities = "document:create")
    void createBodyTenantMismatchIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t2\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "alice", authorities = "document:create")
    void createHeaderTenantMismatchIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .header("X-Tenant-Id", "t2")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "mallory", authorities = "document:create")
    void createAuthorityWithoutMembershipIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCanEditWithMatchingSelectors() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .header("X-Tenant-Id", "t1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Revised\"}"))
            .andExpect(status().isOk());
        assertEquals("Revised", catalog.find(101L).title());
    }

    @Test
    @WithMockUser(username = "alice")
    void editBodyTenantMismatchIsDenied() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t2\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
        assertEquals("Alice notes", catalog.find(101L).title());
    }

    @Test
    @WithMockUser(username = "alice")
    void editHeaderTenantMismatchIsDenied() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .header("X-Tenant-Id", "t2")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
        assertEquals("Alice notes", catalog.find(101L).title());
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerCannotEditSharedDocument() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void editorMayEditAnotherOwnerDocument() throws Exception {
        mvc.perform(put(doc("t1", 102))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Edited\"}"))
            .andExpect(status().isOk());
        assertEquals("Edited", catalog.find(102L).title());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminMayEditOwnTenant() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Managed\"}"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminCannotEditOtherTenant() throws Exception {
        mvc.perform(put(doc("t2", 201))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t2\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void csrfProtectsPutEvenForOwner() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"No CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void serviceMethodRejectsUnauthorizedRead() {
        assertThrows(AccessDeniedException.class,
            () -> service.read("t1", 103L, null));
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn test
```

Số bài test trong file được xác định bằng số phương thức có `@Test`; kỳ vọng tất cả pass nếu project sử dụng đúng dependency/configuration trên. Đây là **kết quả dự kiến sau khi đọc mã nguồn**, không phải tuyên bố Maven đã chạy. `@WithMockUser` mô phỏng danh tính nhằm kiểm tra authorization; JWT thật còn cần bộ test ký số, issuer, audience, hết hạn và membership revoke.

Các kết luận từ test:
- Path t2 không tự cấp membership; header t2 không override path t1.
- Body tenant t2 không được đổi tenant của Document#101 ở t1.
- Document#201 dù tồn tại không thể bị Alice truy cập qua route t1.
- Bob ở t1 chỉ được READ trên Document#101 được share VIEWER; không được EDIT.
- Manager có role và binding t1 không được truy cập record t2.
- Header `X-User`/`X-Role` do client gửi không thay Authentication.
- `@PreAuthorize` vẫn chặn lời gọi vào Spring-managed service ngoài đường HTTP.
- Thiếu CSRF trên PUT bị từ chối theo servlet security config hiện tại.

## 7. Khi dùng database thật: tenant predicate là lớp phòng vệ bắt buộc

### 7.1. READ theo ID và tenant đã verified

```sql
SELECT id, tenant_id, owner_id, title
FROM document
WHERE id = :documentId
  AND tenant_id = :verifiedTenantId;
```

`:verifiedTenantId` là tenant candidate đã đối chiếu với Membership/Authentication, **không** phải bản sao trực tiếp của một raw header. Nếu không có record thì trả deny/not-found theo policy; không tiết lộ rằng ID này thuộc tenant khác.

Với Spring Data JPA:

```java
public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {
    Optional<DocumentEntity> findByIdAndTenantId(
        Long id, String tenantId);
}
```

Đây là đoạn **minh họa repository**, cần Spring Data JPA, entity và datasource. Nó không nằm trong dự án RAM ở phần 5. Query tenant-qualified giảm nguy cơ một method khác vô tình bỏ tenant filter.

### 7.2. UPDATE không được chỉ có `WHERE id=?`

```sql
UPDATE document
SET title = :newTitle
WHERE id = :documentId
  AND tenant_id = :verifiedTenantId
  AND (
    owner_id = :authenticatedUserId
    OR EXISTS (
        SELECT 1
        FROM document_share s
        WHERE s.document_id = document.id
          AND s.user_id = :authenticatedUserId
          AND s.access_level = 'EDITOR'
    )
  );
```

Đây là mẫu SQL minh họa, chưa gồm nhánh scoped-admin; nếu thêm, phải xác minh role binding theo chính tenant. Sau update, kiểm tra affected row count = 1. Nếu quyền owner/share bị thu hồi đồng thời hoặc document chuyển tenant, cần transaction/isolation, row lock hay optimistic version theo mức rủi ro. `@PreAuthorize` đơn lẻ không loại bỏ hoàn toàn race **TOCTOU**.

### 7.3. CREATE phải gán tenant/owner phía server

Thao tác tạo một record mới chưa có object ID. Có thể xác minh `canCreate(authentication,tenant)` rồi insert:

```sql
INSERT INTO document(tenant_id, owner_id, title)
VALUES (:verifiedTenantId, :authenticatedUserId, :title);
```

Không viết `entity.setTenantId(request.tenantId())` trước khi xác minh membership/permission, càng không sao chép `request.ownerId` thành owner. Với schema có bảng organization, nên dùng FK và ràng buộc tenant cho resource cha.

### 7.4. List, search, count và export phải cách ly tenant

Cùng một policy cần áp dụng cho:
- `GET /documents` với phân trang, sort và aggregate.
- File download, attachment, báo cáo và export CSV.
- Search index, background job, batch delete, webhook/event consumer.
- Cache key, object storage key và presigned URL generation.

Đừng truy vấn mọi tenant rồi lọc sau pagination: số lượng, metadata và kết quả có thể bị rò. Mẫu:

```sql
SELECT d.id, d.title
FROM document d
WHERE d.tenant_id = :verifiedTenantId
  AND (
      d.owner_id = :authenticatedUserId
      OR EXISTS (
          SELECT 1 FROM document_share s
          WHERE s.document_id = d.id
            AND s.user_id = :authenticatedUserId
      )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

COUNT/facet query phải dùng **cùng tenant/permission predicates**. Nếu hệ thống dùng ACL parent/child, vai trò hay business workflow, cần thêm các điều kiện đó trước phân trang.

## 8. JWT đa tenant, proxy và TenantContext

### 8.1. Trusted issuers, không lấy JWKS từ header tùy ý

Spring Security 6.5 hỗ trợ `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` cho resource server đa issuer. Một JWT hợp lệ phải được xác minh signature, issuer, audience, expiry và các validators tương ứng. Issuer/JWKS endpoint cần xuất phát từ **allowlist/registry được quản lý từ server**.

Đừng đọc `X-Tenant-Id: attacker` rồi tự xây URL `https://attacker/.well-known/jwks.json` để tin public key tùy ý. Nếu claim `tenantId` từ JWT sau verify làm cơ sở entitlement, vẫn cần đối chiếu tenant của resource và xem xét chiến lược revoke/membership lookup.

### 8.2. Header từ reverse proxy có thể tin chỉ khi đã xác thực

Một gateway có thể phát header nội bộ chứa user/tenant, nhưng chỉ an toàn khi:
1. Gateway bỏ toàn bộ header cùng tên do client gửi.
2. Backend không thể bị truy cập trực tiếp để bypass gateway.
3. Backend xác thực gateway bằng mTLS/chữ ký/credential nội bộ.
4. Tenant/role trong header được gateway xác minh và có phạm vi rõ.
5. Có test header spoofing và duplicate headers.

Ngoài mô hình này, `Host`, `X-Forwarded-Host`, `X-User`, `X-Role`, `X-Tenant-Id` phải được xem là dữ liệu client-controlled. Không dùng chúng để thay principal hoặc cấp role.

### 8.3. TenantContext, schema-per-tenant và database-per-tenant

Với shared tables, mọi query cần tenant predicate. Với schema-per-tenant hoặc database-per-tenant, một `TenantResolver` có thể chọn schema/DataSource, nhưng **không được chọn từ raw header trước khi kiểm tra membership**. Cần registry tenant có whitelist và routing rõ, ngăn ghép raw input thành SQL identifier hoặc tên DataSource bất kỳ.

Nếu dùng `ThreadLocal` lưu selected tenant cho JDBC/Hibernate:

```java
try {
    // Đã xác thực người gọi và verify membership trước đó.
    tenantContext.set(verifiedTenant);
    filterChain.doFilter(request, response);
} finally {
    tenantContext.clear();
}
```

Đây là **pseudo-code** cho filter, không phải class độc lập. Không quên `finally`: thread pool có thể tái sử dụng tenant của request cũ. Trong `@Async`, Reactor hoặc job/message consumer, SecurityContext/tenant context không tự được truyền theo cùng một cách; phải có propagation strategy và kiểm chứng riêng.

### 8.4. Cache và audit

Cache key phải phân biệt tenant: `(tenantId, documentId, principal/permission version)` khi nội dung phụ thuộc quyền. Một key `document:101` có thể rò dữ liệu nếu ID chỉ unique trong từng tenant. Khi membership bị revoke, cache và token cũ cần có kế hoạch invalidation/TTL.

Log audit nên chứa actor được xác thực, requested tenant, canonical tenant (nếu có), resource ID, action, outcome và policy version; tránh ghi token/secret hoặc trả về thông báo khác nhau làm lộ nội dung tenant khác.

## 9. Lỗi thường gặp

| Sai lầm | Hậu quả | Sửa |
|---|---|---|
| `X-Tenant-Id` tự trở thành authority | Privilege escalation | Membership/role từ nguồn đáng tin |
| Body `tenantId` ghi thẳng vào entity | Đổi tenant trái phép | Whitelist DTO, server-set tenant/owner |
| Route `/tenants/t1` nhưng query chỉ `WHERE id=?` | Cross-tenant BOLA | Tra với `tenant_id=? AND id=?` |
| Tenant header khác route nhưng service tự ưu tiên header | Confused deputy | Reject mismatch |
| `hasRole('ADMIN') or policy(...)` | Admin bypass tenant boundary | Scope admin binding trong đúng tenant |
| JWT chưa verify issuer/audience/signature | Chấp nhận token giả/sai audience | Trusted JWT validators |
| Mọi member tenant đều được READ | Lộ record nội bộ | Thêm owner/share/action |
| Cache thiếu tenant | Trả dữ liệu của tenant khác | Key có tenant và permission scope |
| Tenant ThreadLocal không clear | Rò scope giữa request | `finally.remove()` |
| Chỉ test URL, không test header/body | Bỏ sót spoofing/mass assignment | Negative matrix cho mọi input |
| Filter list sau pagination | Lộ aggregate, sai page size | Tenant/permission predicate trước paging |
| Chỉ bảo vệ Controller | Batch/service path bypass | Service-level Method Security |
| `@PostAuthorize` cho mutation | Side effect xảy ra trước deny | `@PreAuthorize` và guarded update |
| Client tự chọn JWT issuer/JWKS | Trust attacker-controlled signer | Issuer allowlist |
| Tự `trim()/lowercase` mọi tenant ID | Scope nhầm nhau | Canonicalization theo hợp đồng |
| Tin `X-Forwarded-Host` mọi nơi | Host spoofing | Chỉ tin proxy chain được xác thực |

## 10. Checklist code review

- [ ] Tenant URL/header/query/body/subdomain đều được coi là selectors cần verify.
- [ ] Authentication đến từ credential/session/JWT đã xác minh, không từ `X-User` hay `X-Role` tùy ý.
- [ ] Role admin được bind theo đúng tenant; membership bị revoke có cơ chế làm mới.
- [ ] Các selectors cùng request mâu thuẫn thì từ chối, không silent override.
- [ ] Resource ID có canonical tenant, tra bằng tenant-qualified query.
- [ ] Đủ permission cho read/edit/create/delete, không chỉ membership.
- [ ] DTO không cho sửa tenant/owner qua thao tác không được cấp quyền.
- [ ] CREATE gán owner từ Authentication và tenant đã verified.
- [ ] UPDATE/DELETE kiểm tra affected rows và concurrency policy.
- [ ] List/count/search/export cùng tenant/permission predicates.
- [ ] Header duplicate, tenant ID format, Unicode/case và path encoding có test.
- [ ] Trusted issuer/JWKS, audience, expiration và allowed tenants được validate.
- [ ] Gateway xóa incoming identity headers, backend có bảo vệ chống bypass.
- [ ] TenantContext không rò qua thread/async/connection pool; cache key phân tenant.
- [ ] Test cross-tenant trên URL, header, body, ID, owner/share/admin và service calls.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Alice thuộc t1; request dùng URL t2, header t2 và body t2. Vì sao vẫn bị deny?

**Đáp án:** Ba giá trị khớp nhau nhưng đều do client chọn; membership server không cấp quyền t2 cho Alice.

**Câu 2.** Alice ở t1 gọi URL t1 nhưng document ID thuộc t2; chỉ kiểm tra membership t1 có đủ không?

**Đáp án:** Không. Phải kiểm tra tenant canonical của record bằng truy vấn có tenant predicate.

**Câu 3.** Bob có `ROLE_TENANT_ADMIN` nhưng không có binding admin ở t1; có được đọc Document#103 không?

**Đáp án:** Không theo policy demo. Role string không tự định nghĩa tenant scope; còn cần membership/binding và quyền trên resource.

**Câu 4.** Body có `owner:"mallory"` trong CREATE, backend nên gán owner nào?

**Đáp án:** Principal đã xác thực (ví dụ Alice), không phải trường do client khai. Nếu strict schema, còn có thể từ chối unknown fields.

**Câu 5.** `@PreAuthorize` đã cho EDIT, tại sao SQL vẫn nên có `WHERE tenant_id=?`?

**Đáp án:** Để bảo vệ các code paths khác và thu hẹp TOCTOU. Precheck không tự đảm bảo tenant/ACL không đổi giữa hai bước.

## 12. Tài liệu tham khảo

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): HTTP request authorization, matcher order, URI variables, deny-by-default.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và policy bean.
- [Spring Security 6.5 — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html): trusted issuer, tenant resolution và propagation.
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer và token validation.
- [OWASP API Security Top 10 (2023) — API1 BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object-level authorization cho các API có ID từ client.
- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` và kiểm thử quyết định quyền.

**Ghi nhớ:** Tenant trong URL, header, body hoặc query là **đầu vào cần kiểm chứng**, không phải bằng chứng ủy quyền. Chỉ cho phép thao tác sau khi đã đối chiếu **Authentication đáng tin, membership/role binding theo tenant, tenant canonical của tài nguyên và permission của hành động**. Từ chối mọi mismatch, giữ tenant predicate tại repository và kiểm thử riêng từng nguồn tenant do client có thể sửa.