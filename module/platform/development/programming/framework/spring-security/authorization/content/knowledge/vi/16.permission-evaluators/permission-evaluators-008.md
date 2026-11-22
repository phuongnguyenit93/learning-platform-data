# Phân quyền sở hữu, quyền chia sẻ và quyền quản trị bằng Spring Security PermissionEvaluator

## 1. Vấn đề: cùng một tài liệu, ba con đường có quyền truy cập

Giả sử ứng dụng quản lý tài liệu trong nhiều tenant. Tài liệu `101` thuộc tenant `t1`, được tạo bởi `alice`. Alice có thể đọc, sửa, chia sẻ hoặc xóa tài liệu; Bob chỉ được xem nếu Alice chia sẻ ở mức `VIEWER`; một `TENANT_ADMIN` có thể quản trị tài liệu trong tenant được giao nhưng không tự nhiên có quyền ở tenant khác.

Ba nguồn quyền này **khác nhau**:

1. **Quyền sở hữu (ownership)**: ai là owner của **bản ghi cụ thể**.
2. **Quyền chia sẻ (sharing / ACL)**: người dùng hoặc nhóm khác được cấp mức truy cập trên **bản ghi cụ thể**.
3. **Quyền quản trị (administrative privilege)**: quyền mở rộng trong một **phạm vi được xác định** (tenant/project/organization hoặc toàn hệ thống).

Một kiểm tra đơn giản như:

```java
@PreAuthorize("hasAuthority('document:edit')")
public Document rename(Long documentId, String title) {
    // ...
}
```

là **mẫu method**, không phải ứng dụng độc lập. Nó chỉ hỏi người dùng có authority `document:edit` hay không; không biết người dùng đang sửa tài liệu số mấy, có phải chủ sở hữu, có được chia sẻ hay có thuộc tenant đúng không. Nếu yêu cầu là quyền trên từng bản ghi, cần một **quyết định theo đối tượng (object-level authorization)**.

Spring Security cung cấp `PermissionEvaluator` để thực hiện quyết định này thông qua `hasPermission(...)` trong biểu thức Method Security. Bài học xây dựng chính sách minh bạch cho owner, người được chia sẻ và tenant admin, giải thích các lỗ hổng thường gặp và có ví dụ Spring Boot + Java 17 kiểm thử được.

**Kết quả cần nhớ:** có `ROLE_ADMIN` hay có authority `document:edit` không đồng nghĩa được phép sửa mọi record. Chính sách phải xác định **đối tượng, hành động, danh tính, phạm vi và nguồn dữ liệu đáng tin**.

## 2. Mô hình quyền và ma trận quyết định

### 2.1. Tài nguyên và chủ thể

Giả sử domain có:

```text
Document:
  id         : 101
  tenant     : t1
  owner      : alice
  title      : "Alice draft"

Membership:
  t1: alice, bob, manager1
  t2: carol, dave, manager2

Access grants (trên từng document):
  document_id | username | access_level
  101         | bob      | VIEWER

Authentication:
  alice    → authority tenant:t1
  bob      → authority tenant:t1
  manager1 → authorities tenant:t1, ROLE_TENANT_ADMIN
```

Đây là **dữ liệu minh họa**, không phải tên bảng hay định dạng token bắt buộc của Spring Security. Trong hệ thống thật, membership, owner và grants phải đến từ nguồn phía server đã xác minh; không nhận dữ liệu owner/role do client tự khai rồi dùng để cho phép.

Đối với một tài liệu, chúng ta dùng hai mức chia sẻ:

- `VIEWER`: được **read**.
- `EDITOR`: được **read** và **edit**.

Người được chia sẻ không tự động được cấp `share`, `revoke` hoặc `delete`. Chủ sở hữu hoặc người quản trị trong đúng tenant mới được quản lý các quyền đó. Đây là chính sách của **ví dụ**, không phải quy tắc bất biến của Spring Security.

### 2.2. Ma trận minh bạch

| Loại chủ thể trên đúng tenant | Read | Edit | Share | Revoke | Delete |
|---|---:|---:|---:|---:|---:|
| Owner của document | Có | Có | Có | Có | Có |
| Được share `VIEWER` | Có | Không | Không | Không | Không |
| Được share `EDITOR` | Có | Có | Không | Không | Không |
| `ROLE_TENANT_ADMIN` | Có | Có | Có | Có | Có |
| Thành viên tenant nhưng **chưa** có quyền trên tài liệu | Không | Không | Không | Không | Không |
| Người khác tenant hoặc không thuộc directory tin cậy | Không | Không | Không | Không | Không |

Ma trận giả định **cả hai** điều kiện tenant đều đúng: username là thành viên tenant theo directory phía server và Authentication có authority `tenant:<tenantId>` tương ứng. Nếu thiếu bất kỳ điều kiện nào, kết quả là deny, kể cả khi user có `ROLE_TENANT_ADMIN` hoặc được ghi trong bảng share.

**Vì sao kiểm tra hai điều kiện?** Ví dụ dùng authority `tenant:t1` để chứng minh quyền được đưa vào Authentication, đồng thời kiểm tra directory để ngăn trường hợp quyền trong token bị sai hoặc quá cũ. Ứng dụng thực có thể chọn một nguồn sự thật khác, nhưng phải chỉ rõ cơ chế cấp, cập nhật và thu hồi membership.

### 2.3. Quy tắc tổng hợp

Viết logic như một công thức:

```text
allowed(user, document, action)
  = authenticated(user)
  AND activeTenantMembership(user, document.tenant)
  AND tenantAuthorityMatches(user, document.tenant)
  AND (
       isOwner(user, document) AND action ∈ ownerActions
       OR isTenantAdmin(user, document.tenant) AND action ∈ adminActions
       OR sharedLevel(user, document) permits action
  )
```

Đây là **mô hình logic**, không phải cú pháp chạy được trong Spring. Ngoại lệ hay giá trị null ở các điểm kiểm tra bảo mật không được biến thành allow. Một quyết định rõ ràng `false` (fail-closed) là lựa chọn an toàn khi action, resource type, id hoặc membership không hợp lệ.

### 2.4. Quyền quản trị phải có phạm vi

Cần phân biệt:

- `ROLE_TENANT_ADMIN`: quyền quản trị trong tenant mà user được giao.
- `ROLE_SYSTEM_ADMIN`: quyền quản trị toàn hệ thống, nếu nghiệp vụ thực sự định nghĩa.
- `ROLE_SUPPORT`: vai trò hỗ trợ; không tự động được đọc tài liệu riêng tư.
- Owner: quyền trên **một tài liệu**, không phải trên mọi tài liệu cùng tenant.

Ví dụ sẽ **không** có “superuser bypass mọi kiểm tra”. Nếu muốn `ROLE_SYSTEM_ADMIN` vượt tenant, phải thiết kế riêng, ghi mục đích, giới hạn truy cập, audit, test và xác minh quyền cấp role đó. Không viết `hasRole('ADMIN') or hasPermission(...)` một cách máy móc, vì nhánh admin có thể vượt mọi kiểm tra tenant và ACL.

Một vấn đề tinh tế: role `ROLE_TENANT_ADMIN` dạng chuỗi toàn cục kết hợp membership là giải pháp đơn giản để học. Ở ứng dụng thực, nếu một người tham gia nhiều tenant nhưng chỉ quản trị **một** tenant, hãy lưu `role binding` theo tenant (ví dụ `user_role(user, tenant, role)`) thay vì gán một role “admin mọi tenant mà user tham gia”.

## 3. PermissionEvaluator là nơi gắn quyền vào tài nguyên cụ thể

Interface:

```java
package org.springframework.security.access;

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
```

Đây là **bản rút gọn chữ ký API** để giải thích; interface thật nằm trong Spring Security và dùng các imports/extends riêng của framework. Không tự tạo lại interface ở package đó.

Hai biểu thức phổ biến:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
public Document rename(@P("id") Long id, String title) {
    return store.rename(id, title);
}

@PostAuthorize("returnObject != null and hasPermission(returnObject, 'read')")
public Document findOne(Long id) {
    return store.require(id);
}
```

Đây là **đoạn method minh họa**; cần class, imports và `store` để thành chương trình. Điểm cần phân biệt:

- **Overload ID**: evaluator nhận id, chuỗi `targetType = "Document"` và `permission = "edit"`. Phù hợp với `@PreAuthorize` **trước thao tác ghi**.
- **Overload object**: evaluator nhận một instance `Document` và `permission = "read"`. Phù hợp để quyết định có được **trả kết quả đọc** hay không trong `@PostAuthorize`.
- `targetType` **chỉ là chuỗi**; Spring không tự tìm owner hay ACL từ tên `Document`. Evaluator tự chọn mapping và truy vấn nguồn dữ liệu.
- `@PostAuthorize` chạy **sau** khi method trả kết quả; nếu method đã gửi email hoặc ghi DB, việc từ chối sau đó không tự hoàn tác side effects.
- `@PreAuthorize` thường chặn method ngay tại proxy trước khi target chạy. Với dữ liệu và resource ID có sẵn, nó là lựa chọn phù hợp để bảo vệ mutation.

Không tự động giả định Spring Security đã có chính sách ownership/sharing cho bạn. `hasPermission` chỉ là **điểm nối**. Không có evaluator được cấu hình hợp lệ, ứng dụng không tự suy ra ACL hay quyền chia sẻ.

### 3.1. Luồng kiểm tra

```text
Caller → Spring-managed DocumentService proxy
   ↓
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
   ↓
MethodSecurityExpressionHandler
   ↓
DocumentPermissionEvaluator.hasPermission(authentication, id, type, action)
   ├─ Check Authentication không anonymous
   ├─ Validate targetType/action/id
   ├─ Load Document canonical theo id
   ├─ Check membership + tenant scope
   ├─ Check owner / share grant / tenant admin
   └─ Return boolean
   ↓
true  → chạy method
false → AccessDeniedException (hoặc subclass), không chạy target
```

Lưu ý `@PreAuthorize` vẫn cần **Spring AOP proxy**. Tự gọi method cùng bean qua `this` hoặc tự `new DocumentService(...)` sẽ không tự đi qua interceptor theo proxy mode thông thường.

## 4. Thiết kế quyền chia sẻ an toàn

### 4.1. Grants là dữ liệu server-side, không phải “owner” do client sửa được

Một bảng ACL tối giản có thể gồm:

```text
document_share(
  document_id,
  grantee_user_id,
  access_level,      -- VIEWER | EDITOR
  granted_by,
  granted_at,
  expires_at,        -- tùy yêu cầu
  revoked_at         -- tùy yêu cầu
)
```

Các trường giải thích nghiệp vụ, không phải DDL hoàn chỉnh. Cần lưu trên nguồn tin cậy và tham chiếu resource ID thực. Đừng tin JSON `{"owner":"alice","sharedWith":["bob"]}` do client gửi là ACL đã được phê duyệt.

**Cấp quyền:** chỉ owner/admin tenant được cấp; người nhận phải thuộc tenant và có tài khoản hợp lệ. Có thể cấm chia sẻ cho chính owner, phân biệt yêu cầu chờ chấp nhận, giới hạn thời hạn và audit người cấp.

**Thu hồi quyền:** chỉ owner/admin tenant được thu hồi; token/session hoặc cache của người nhận phải phản ánh việc thu hồi theo SLA. Với đường link chia sẻ công khai, cần một cơ chế riêng: token đoán không được, hết hạn, scope tối thiểu, revoke, rate-limit và không đưa link vào log công khai.

### 4.2. Quyền được chia sẻ không có tính chuyển giao mặc định

`EDITOR` không được tự cấp `EDITOR` cho user khác; nếu muốn, thêm action `delegate` hay `share` riêng, giới hạn chiều sâu và điều kiện cấp. Không dùng logic “có edit ⇒ có share” nếu domain không quy định vậy.

Một người có `VIEWER` cũng không tự có `export`, `download-original` hoặc `publish`. Trong hệ thống nhiều mức dữ liệu, có thể cần thêm các action `read-metadata`, `download`, `export`, `comment`; giữ ma trận ngắn cho demo và mở rộng theo rủi ro.

### 4.3. Quyết định phải xem trạng thái hiện tại

Grants có thể hết hạn, document bị khóa, user rời tenant hoặc tài liệu chuyển trạng thái `ARCHIVED`. PermissionEvaluator cần kiểm tra những điều kiện này theo policy. **Deny khi không chắc**, đặc biệt khi dịch vụ membership/ACL bị lỗi. Trả `true` chỉ vì không truy vấn được DB là một lỗi fail-open nguy hiểm.

## 5. Dự án Java 17 chạy được với Spring Boot 3.5.6

Ví dụ sau cung cấp đầy đủ các file Java, Maven và JUnit 5, dùng Spring Security 6.5.x do Spring Boot 3.5.6 quản lý. Không cần database hoặc HTTP server; storage `ConcurrentHashMap` và directory cố định giúp bài test xác minh đúng quyết định của `PermissionEvaluator`.

Mục tiêu của demo là **thực thi chính sách**, không phải thay thế ACID transaction, row lock, hệ thống IAM hay ACL database. Những giới hạn production sẽ được phân tích ở phần sau.

### 5.1. Cây file

```text
ownership-share-admin-demo/
  pom.xml
  src/main/java/com/example/ownership/
    OwnershipApplication.java
    MethodSecurityConfig.java
    Document.java
    ShareAccess.java
    TenantDirectory.java
    DocumentStore.java
    DocumentPermissionEvaluator.java
    DocumentService.java
  src/test/java/com/example/ownership/
    DocumentServiceTest.java
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
    <artifactId>ownership-share-admin-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### 5.3. Spring Boot application

**`src/main/java/com/example/ownership/OwnershipApplication.java`**

```java
package com.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
```

### 5.4. Domain và mức chia sẻ

**`src/main/java/com/example/ownership/Document.java`**

```java
package com.example.ownership;

public record Document(
        Long id,
        String tenant,
        String owner,
        String title) {
}
```

**`src/main/java/com/example/ownership/ShareAccess.java`**

```java
package com.example.ownership;

public enum ShareAccess {
    VIEWER,
    EDITOR
}
```

Không dùng một boolean `isShared`: boolean không phân biệt xem và sửa, cũng không lưu được người nhận, thời hạn và người cấp. Mức `EDITOR` **không bao gồm** share/delete ở chính sách này.

### 5.5. TenantDirectory: danh sách thành viên tin cậy

**`src/main/java/com/example/ownership/TenantDirectory.java`**

```java
package com.example.ownership;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final Map<String, Set<String>> memberships = Map.of(
        "t1", Set.of("alice", "bob", "manager1"),
        "t2", Set.of("carol", "dave", "manager2")
    );

    public boolean isMember(String username, String tenant) {
        Set<String> members = memberships.get(tenant);
        return username != null
            && members != null
            && members.contains(username);
    }
}
```

Fixture bất biến này đóng vai trò “nguồn dữ liệu membership đáng tin” phục vụ test. Trong ứng dụng thật, membership cần tồn tại trong DB/IAM và có chiến lược revoke, không nên hardcode trong Java. Việc có một authority `tenant:t1` trong token **không thay thế** kiểm tra membership nếu token có thể stale hoặc được ánh xạ sai.

### 5.6. DocumentStore: tài liệu và ACL trong bộ nhớ

**`src/main/java/com/example/ownership/DocumentStore.java`**

```java
package com.example.ownership;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {
    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>();

    private final ConcurrentMap<Long, ConcurrentMap<String, ShareAccess>> grants =
        new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    public synchronized void reset() {
        documents.clear();
        grants.clear();

        documents.put(101L,
            new Document(101L, "t1", "alice", "Alice draft"));
        documents.put(102L,
            new Document(102L, "t1", "bob", "Bob notes"));
        documents.put(201L,
            new Document(201L, "t2", "carol", "Carol plan"));
    }

    public Document find(Long id) {
        return id == null ? null : documents.get(id);
    }

    public Document require(Long id) {
        Document document = find(id);
        if (document == null) {
            throw new NoSuchElementException("Document not found");
        }
        return document;
    }

    public ShareAccess sharedLevel(Long documentId, String username) {
        Map<String, ShareAccess> entries = grants.get(documentId);
        return entries == null ? null : entries.get(username);
    }

    public void grant(Long id, String username, ShareAccess access) {
        if (find(id) == null || username == null || access == null) {
            throw new IllegalArgumentException("Invalid share");
        }
        grants.computeIfAbsent(id, ignored -> new ConcurrentHashMap<>())
            .put(username, access);
    }

    public void revoke(Long id, String username) {
        Map<String, ShareAccess> entries = grants.get(id);
        if (entries != null) {
            entries.remove(username);
        }
    }

    public Document rename(Long id, String title) {
        return documents.computeIfPresent(id, (key, old) ->
            new Document(old.id(), old.tenant(), old.owner(), title)
        );
    }

    public boolean delete(Long id) {
        if (documents.remove(id) == null) {
            return false;
        }
        grants.remove(id);
        return true;
    }
}
```

Chúng ta tách tài liệu và grants để mô phỏng quyền được chia sẻ có thể cấp/thu hồi độc lập. `ConcurrentHashMap` chỉ hỗ trợ một số thao tác concurrent đơn lẻ; **không** bảo đảm tính nguyên tử của toàn bộ “kiểm tra quyền → sửa document → cập nhật ACL” giữa nhiều map. Hệ thống thật phải bảo vệ các invariant bằng transaction, ràng buộc dữ liệu và locking phù hợp.

### 5.7. PermissionEvaluator: owner OR share OR tenant admin, nhưng không vượt tenant

**`src/main/java/com/example/ownership/DocumentPermissionEvaluator.java`**

```java
package com.example.ownership;

import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {
    private static final String DOCUMENT_TYPE = "Document";

    private final DocumentStore documents;
    private final TenantDirectory tenants;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public DocumentPermissionEvaluator(
            DocumentStore documents,
            TenantDirectory tenants) {
        this.documents = documents;
        this.tenants = tenants;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {
        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Chỉ dùng ID; không tin owner/tenant trên object do client có thể tạo.
        return hasPermission(
            authentication,
            document.id(),
            DOCUMENT_TYPE,
            permission
        );
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            return false;
        }

        if (!(targetId instanceof Long id)
                || !DOCUMENT_TYPE.equals(targetType)
                || !(permission instanceof String action)) {
            return false;
        }

        Document document = documents.find(id);
        if (document == null) {
            return false;
        }

        String username = authentication.getName();

        // Tenant membership và tenant authority đều phải chính xác.
        if (!tenants.isMember(username, document.tenant())
                || !hasAuthority(
                    authentication, "tenant:" + document.tenant())) {
            return false;
        }

        boolean owner = document.owner().equals(username);
        boolean tenantAdmin = hasAuthority(
            authentication, "ROLE_TENANT_ADMIN");
        ShareAccess shared = documents.sharedLevel(id, username);

        return switch (action) {
            case "read" ->
                owner || tenantAdmin
                    || shared == ShareAccess.VIEWER
                    || shared == ShareAccess.EDITOR;

            case "edit" ->
                owner || tenantAdmin || shared == ShareAccess.EDITOR;

            case "share", "revoke", "delete" ->
                owner || tenantAdmin;

            default -> false;
        };
    }

    private static boolean hasAuthority(
            Authentication authentication, String expected) {
        for (GrantedAuthority authority : authentication.getAuthorities()) {
            if (expected.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

**Phân tích các hàng bảo vệ quan trọng:**

1. `Authentication` phải tồn tại, có trạng thái xác thực hợp lệ và không phải anonymous.
2. Target ID phải là `Long`, type phải đúng `Document`, permission phải là `String`.
3. Evaluator tải **document canonical theo ID từ server-side store**, không tin owner/tenant do bên gọi nhét vào một instance giả.
4. Membership và authority `tenant:<id>` phải cùng khớp tenant của bản ghi.
5. Chỉ sau khi qua tenant boundary mới xét owner, share grant hoặc `ROLE_TENANT_ADMIN`.
6. `VIEWER` chỉ cho read; `EDITOR` thêm edit; chỉ owner/admin được share/revoke/delete.
7. Action không biết, ID không tồn tại, type sai, null hoặc thiếu membership đều trả `false`.

Đây là policy **của ví dụ**. Nếu doanh nghiệp yêu cầu owner không được xóa hồ sơ đã phê duyệt, phải thêm điều kiện trạng thái; nếu admin chỉ được hỗ trợ đọc, hãy thu hẹp adminActions. Không để tên “admin” là một giấy phép bao trùm không được kiểm toán.

#### Vì sao không chỉ dùng hasRole hoặc hasAuthority?

`hasRole('TENANT_ADMIN')` theo cấu hình mặc định tìm authority `ROLE_TENANT_ADMIN`, nhưng **không biết tenant nào**. `hasAuthority('tenant:t1')` biết scope mà caller được cấp, nhưng **không biết document ID thuộc tenant nào**. Evaluator kết hợp được cả hai dữ liệu với owner và grant cụ thể.

#### Vì sao object overload cũng tra lại document?

Giả sử Bob gửi một object giả `new Document(101L, "t1", "bob", "...")` để tự nhận là owner. Nếu evaluator tin `document.owner()` trên object do client tạo, Bob có thể tự cho mình quyền. Ở đây overload object chỉ lấy `id` rồi gọi overload ID tra lại record thật. Nếu không tìm thấy, deny.

## 6. Bật Method Security và kết nối evaluator

**`src/main/java/com/example/ownership/MethodSecurityConfig.java`**

```java
package com.example.ownership;

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
```

Đây là cơ chế tích hợp được Spring Security 6.5 minh họa: khai báo `@EnableMethodSecurity` và xuất bản `static MethodSecurityExpressionHandler` sớm để framework sử dụng evaluator khi đánh giá `hasPermission(...)`.

Spring Boot Security **không tự bật Method Security chỉ nhờ dependency**. Nếu quên `@EnableMethodSecurity`, annotation có thể vẫn biên dịch mà không tạo interceptor cần thiết. Nếu dự án đã có custom expression handler, không vô tình thay handler đó và làm mất cấu hình role hierarchy, default role prefix hay evaluator sẵn có; hãy gộp cấu hình vào một handler nhất quán.

## 7. Service: phân tách hành động đọc, sửa, chia sẻ và quản trị

**`src/main/java/com/example/ownership/DocumentService.java`**

```java
package com.example.ownership;

import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore documents;
    private final TenantDirectory tenants;

    public DocumentService(
            DocumentStore documents,
            TenantDirectory tenants) {
        this.documents = documents;
        this.tenants = tenants;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'read')")
    public Document read(@P("id") Long id) {
        return documents.require(id);
    }

    // Hậu kiểm thích hợp cho kết quả đọc thuần, không dùng để bảo vệ ghi.
    @PostAuthorize(
        "returnObject != null and hasPermission(returnObject, 'read')"
    )
    public Document readAfter(@P("id") Long id) {
        return documents.require(id);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'edit')")
    public Document rename(@P("id") Long id, String newTitle) {
        Document result = documents.rename(id, newTitle);
        if (result == null) {
            throw new NoSuchElementException("Document not found");
        }
        return result;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'share')")
    public void share(
            @P("id") Long id,
            String recipient,
            ShareAccess access) {
        Document document = documents.require(id);

        if (access == null
                || recipient == null
                || recipient.isBlank()
                || !tenants.isMember(recipient, document.tenant())
                || document.owner().equals(recipient)) {
            throw new IllegalArgumentException(
                "Recipient/access not allowed"
            );
        }

        documents.grant(id, recipient, access);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'revoke')")
    public void revoke(@P("id") Long id, String recipient) {
        Document document = documents.require(id);

        if (recipient == null || document.owner().equals(recipient)) {
            throw new IllegalArgumentException(
                "Cannot revoke the owner"
            );
        }

        documents.revoke(id, recipient);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'delete')")
    public boolean delete(@P("id") Long id) {
        return documents.delete(id);
    }
}
```

Các annotation tiền kiểm **chỉ** quyết định người gọi có quyền thực hiện action dựa trên trạng thái tài nguyên hiện tại. Riêng `share` còn xác minh **người nhận** thuộc tenant; nếu không, owner có thể vô tình cấp cho người ngoài tenant. Dù evaluator vẫn chặn truy cập cross-tenant, ràng buộc cấp share ngay từ đầu giúp tránh grant sai, giảm dữ liệu ACL rác và tăng khả năng audit.

**Không có “share tới owner”** trong ví dụ, vì owner có quyền theo ownership; nếu owner cần chuyển nhượng thật, hãy thiết kế thao tác **transferOwnership** riêng, có reauthentication/approval/audit nếu nghiệp vụ yêu cầu. Không dùng `share(…, EDITOR)` làm cách trá hình để đổi owner.

Khi owner bị thay đổi hoặc document chuyển tenant, hệ thống thật phải xác định số phận grants cũ. Ví dụ không triển khai transfer; vì vậy không có quy tắc chuyển quyền bị ẩn trong code.

## 8. Kiểm thử tích hợp: không chỉ có allow, phải chứng minh deny

Đặt file kiểm thử:

**`src/test/java/com/example/ownership/DocumentServiceTest.java`**

```java
package com.example.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DocumentServiceTest {
    @Autowired DocumentService service;
    @Autowired DocumentStore store;
    @Autowired DocumentPermissionEvaluator evaluator;

    @BeforeEach
    void reset() {
        store.reset();
    }

    private Authentication currentUser() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanReadWithoutExplicitShare() {
        assertEquals("Alice draft", service.read(101L).title());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanEdit() {
        assertEquals("Updated", service.rename(101L, "Updated").title());
        assertEquals("Updated", store.require(101L).title());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanShareWithTenantMember() {
        service.share(101L, "bob", ShareAccess.VIEWER);
        assertEquals(ShareAccess.VIEWER,
            store.sharedLevel(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanRevokeSharing() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        service.revoke(101L, "bob");
        assertNull(store.sharedLevel(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanDelete() {
        assertTrue(service.delete(101L));
        assertNull(store.find(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void unsharedMemberCannotReadOthersDocument() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCanReadSharedDocument() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertEquals("Alice draft", service.read(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCannotEdit() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertThrows(AccessDeniedException.class,
            () -> service.rename(101L, "Forbidden"));
        assertEquals("Alice draft", store.require(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCannotShareFurther() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertThrows(AccessDeniedException.class,
            () -> service.share(101L, "manager1", ShareAccess.VIEWER));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCannotDelete() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertThrows(AccessDeniedException.class,
            () -> service.delete(101L));
        assertEquals("Alice draft", store.require(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void editorCanReadAndEdit() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertEquals("Alice draft", service.read(101L).title());
        assertEquals("Edited", service.rename(101L, "Edited").title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void editorCannotDelegate() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertThrows(AccessDeniedException.class,
            () -> service.share(101L, "manager1", ShareAccess.EDITOR));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void editorCannotDelete() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertThrows(AccessDeniedException.class,
            () -> service.delete(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void revokedShareStopsFurtherAccess() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertEquals("Alice draft", service.read(101L).title());
        store.revoke(101L, "bob");
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminReadsUnsharedDocument() {
        assertEquals("Alice draft", service.read(101L).title());
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminCanEditAndDeleteWithinTenant() {
        assertEquals("Managed", service.rename(101L, "Managed").title());
        assertTrue(service.delete(102L));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminMayManageShares() {
        service.share(101L, "bob", ShareAccess.EDITOR);
        assertEquals(ShareAccess.EDITOR,
            store.sharedLevel(101L, "bob"));
        service.revoke(101L, "bob");
        assertNull(store.sharedLevel(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminCannotCrossTenantBoundary() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(201L));
        assertThrows(AccessDeniedException.class,
            () -> service.delete(201L));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminWithoutTenantAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "mallory",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void forgedTenantAuthorityCannotReplaceMembership() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void crossTenantGrantDoesNotBypassTenantRule() {
        store.grant(201L, "bob", ShareAccess.EDITOR);
        assertThrows(AccessDeniedException.class,
            () -> service.read(201L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCannotShareToAnotherTenant() {
        assertThrows(IllegalArgumentException.class,
            () -> service.share(101L, "carol", ShareAccess.VIEWER));
        assertNull(store.sharedLevel(101L, "carol"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void forgedDomainObjectCannotMakeBobOwner() {
        Document forged = new Document(
            101L, "t1", "bob", "Fake owner"
        );
        assertFalse(evaluator.hasPermission(
            currentUser(), forged, "edit"
        ));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void unknownActionAndTypeAreDenied() {
        assertFalse(evaluator.hasPermission(
            currentUser(), 101L, "Document", "transfer"
        ));
        assertFalse(evaluator.hasPermission(
            currentUser(), 101L, "Invoice", "read"
        ));
        assertFalse(evaluator.hasPermission(
            currentUser(), 101L, "Document", null
        ));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void missingDocumentIdIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(999L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void postAuthorizeAllowsOwnerRead() {
        assertEquals("Alice draft", service.readAfter(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void postAuthorizeRejectsUnsharedRead() {
        assertThrows(AccessDeniedException.class,
            () -> service.readAfter(101L));
    }

    @Test
    void nullAuthenticationCannotBeGranted() {
        assertFalse(evaluator.hasPermission(
            null, 101L, "Document", "read"
        ));
    }
}
```

Các test dùng **Spring-injected service bean** nên annotation chạy qua Spring AOP proxy thật. `@WithMockUser` xây Authentication giả lập để test **authorization**, không phải một lần đăng nhập bằng password/JWT thật. Dữ liệu reset trước mỗi test; không dựa vào thứ tự thực thi.

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kết quả dự kiến theo mã nguồn:** 28 bài test, tất cả pass, 0 failures/errors. Số lượng test và thông báo Maven/Surefire có thể thay đổi nếu bạn mở rộng bộ test. Đây là **kết quả kỳ vọng theo thiết kế**, không phải tuyên bố đã chạy Maven trong nội dung bài học.

Những bất biến quan trọng mà test kiểm chứng:

- Owner luôn có quyền trên document của chính mình trong **đúng tenant**.
- Quyền viewer/editor khác nhau; editor **không tự có quyền share**.
- Thu hồi grant có hiệu lực trong lần kiểm tra kế tiếp ở storage mô phỏng.
- Tenant admin chỉ quản trị trong tenant của mình; có role admin mà thiếu authority tenant vẫn deny.
- Một chuỗi authority có vẻ hợp lệ nhưng username không thuộc directory tin cậy không được cấp quyền.
- Một share grant bị lưu sai sang tenant khác không mở được quyền cross-tenant.
- Object giả owner không được nâng quyền vì evaluator tra record canonical.
- Action, type, document id không hợp lệ bị deny; không có fallback thành allow.
- Hậu kiểm trên kết quả đọc hoạt động, nhưng không thay thế bảo vệ trước thao tác ghi.

## 9. Production: ACL, tenant và ownership cần transaction

Ví dụ dùng hai map nên có thể đọc được mọi nhánh chính sách, nhưng một ứng dụng thực phải giữ consistency giữa quyền và dữ liệu.

### 9.1. Lược đồ tham khảo

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    owner_user_id VARCHAR(80) NOT NULL,
    title VARCHAR(500) NOT NULL
);

CREATE TABLE document_share (
    document_id BIGINT NOT NULL,
    grantee_user_id VARCHAR(80) NOT NULL,
    access_level VARCHAR(20) NOT NULL,
    granted_by VARCHAR(80) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (document_id, grantee_user_id),
    FOREIGN KEY (document_id) REFERENCES document(id)
);

CREATE TABLE tenant_membership (
    tenant_id VARCHAR(80) NOT NULL,
    user_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE tenant_role_binding (
    tenant_id VARCHAR(80) NOT NULL,
    user_id VARCHAR(80) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, user_id, role_name)
);
```

Đây là **schema minh họa**, chưa có các index/foreign key cho user, loại tài liệu, version columns, thời hạn grant, soft delete, business audit và database-specific constraints. Trên hệ thống thực, role binding nên có **tenant_id rõ ràng** để người làm admin ở t1 không tự thành admin ở t2 khi họ đồng thời là member hai tenant.

### 9.2. Nguy cơ TOCTOU: kiểm tra quyền trước khi sửa, nhưng quyền thay giữa hai bước

Xét một lời gọi:

```text
T1  PermissionEvaluator: Bob đang được share EDITOR trên document 101
T2  Alice thu hồi quyền của Bob
T3  Method của Bob chạy UPDATE document 101
```

Nếu transaction hoặc isolation không giữ bất biến giữa T1 và T3, Bob vẫn có thể sửa sau khi bị thu hồi. `@PreAuthorize` **không tự ngăn** race condition này, dù nó có thể chặn nhiều truy cập trái phép ngay từ đầu.

Các lựa chọn tùy nghiệp vụ:
- Kiểm tra quyền và ghi trong **cùng transaction** với khóa hàng/optimistic version tương ứng; chú ý order advisor để transaction thực sự bao quanh lúc kiểm tra.
- Đưa điều kiện owner/ACL/tenant vào câu SQL update để thao tác trở thành conditional update và kiểm tra affected row count.
- Áp dụng resource version, tenant condition và permission version; test conflict/revoke concurrent.
- Chấp nhận một khoảng trễ revoke được mô tả rõ nếu dữ liệu không nhạy cảm, nhưng phải quyết định dựa trên rủi ro.

Ví dụ SQL bảo vệ owner:

```sql
UPDATE document
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :current_tenant_id
  AND owner_user_id = :current_user_id;
```

Đây là một **mẫu SQL** với named parameters do data layer bind; tenant/user phải đến từ security context đã được xác minh. Với chia sẻ EDITOR hoặc admin, cần predicate tương đương theo ACL/role binding; đừng vô tình bỏ điều kiện tenant khi thêm nhánh admin.

### 9.3. Thu hồi quyền, cache và JWT

Nếu access grants nằm trong DB nhưng evaluator cache kết quả:
- Cache key phải bao gồm user, tenant, document id, action và version/thời hạn quyền quan trọng.
- Thay đổi owner, revoke grant, remove membership và remove tenant-admin role phải invalidate kết quả liên quan.
- Nếu JWT chứa sẵn role hoặc tenant membership, token cũ có thể còn hiệu lực sau khi quyền bị thu hồi; cần chiến lược expiration/revocation hoặc lookup online theo yêu cầu bảo mật.
- Với permission server timeout hoặc cache miss, không dùng `catch (Exception ex) { return true; }`. Đánh dấu lỗi/deny và giám sát hệ thống.

Không coi `ROLE_TENANT_ADMIN` trong một token còn hạn là bằng chứng vai trò vẫn hợp lệ nếu policy đòi thu hồi tức thì.

### 9.4. Quyền quản trị và nguyên tắc tối thiểu

Có thể phân tách:
- `TENANT_CONTENT_ADMIN`: quản lý nội dung, không quản lý user.
- `TENANT_USER_ADMIN`: quản lý thành viên/role, không tự đọc nội dung riêng tư.
- `SYSTEM_AUDITOR`: chỉ đọc log, không chỉnh sửa.
- `SUPPORT_BREAK_GLASS`: truy cập khẩn cấp với approval, thời hạn ngắn và audit đặc biệt.

Không cấp một `ROLE_ADMIN` chung rồi bypass mọi policy ở tất cả nghiệp vụ. Nếu có khả năng “break glass”, yêu cầu lý do, reauthentication/step-up, ghi audit và cơ chế phát hiện lạm dụng.

### 9.5. Sharing qua nhóm hoặc link công khai

Khi share cho **group**, evaluator cần biết membership hiện tại của nhóm và giới hạn scope, tránh group chồng chéo gây leo thang quyền. Khi share qua link, khả năng truy cập không còn là quyền của `Authentication#getName()` đơn thuần; phải kiểm tra capability token, expiry, scope, revoke và việc client có thể rò rỉ URL.

Không biến một URL `/document/101?share=true` thành quyền truy cập. Cờ boolean do client chọn không thể chứng minh họ được cấp share.

## 10. Chọn vị trí kiểm tra: HTTP, service và database

Có ba cấp:

| Cấp | Có thể bảo vệ gì? | Không nên giả định |
|---|---|---|
| HTTP `authorizeHttpRequests` | Ai có thể gọi một nhóm URL, có role/authority gì | Không tự biết mọi document ID và owner trên database |
| Method Security `@PreAuthorize`/`@PostAuthorize` | Quyền theo tham số method hoặc kết quả, gọi `PermissionEvaluator` | Không tự có transaction/race protection hoặc chặn self-invocation |
| Database query/row policy | Khóa data scope, tenant, owner, ACL ngay khi đọc/ghi | Không tự thay thế quy tắc nghiệp vụ ở service và audit |

Một API tốt có thể kết hợp:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
public void updateDocument(@P("id") Long id, String title) {
    // Sau khi qua Method Security, DB vẫn update với
    // tenant predicate và kiểm tra version/row count.
}
```

Đây là **mẫu cấu trúc**; cần service, repository và transaction phù hợp mới triển khai production. Không dùng quyền UI (ẩn nút Edit) làm lớp bảo vệ duy nhất. HTTP rule bảo vệ route, nhưng service cũng có thể được gọi từ scheduler, message consumer hoặc endpoint khác.

### 10.1. Hậu kiểm trên kết quả đọc và quyền trên danh sách

`@PostAuthorize("hasPermission(returnObject, 'read')")` có thể hữu ích khi chỉ sau khi load object mới biết owner/ACL. Nhưng nó xảy ra **sau khi method chạy**, nên không phải lựa chọn để bảo vệ mutation hay gửi email.

`@PostFilter("hasPermission(filterObject, 'read')")` lọc từng item của tập kết quả; nếu truy vấn trước rồi lọc, có thể gây N+1 queries, pagination sai, count nhạy cảm hoặc chi phí lớn. Với dữ liệu thật, tốt hơn là áp dụng tenant/ACL filter **tại query** trước phân trang hoặc xây access-controlled repository.

## 11. Các lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `hasRole('ADMIN') or isOwner(...)` bỏ qua tenant | Admin có thể truy cập chéo tenant | Đặt tenant boundary bên ngoài nhánh OR; dùng role binding theo tenant |
| Dùng `document.owner` do client gửi | Client tự nhận ownership | Tra record canonical bằng ID ở server |
| `VIEWER` được cho `edit` vì “đã share” | Leo thang quyền | Ma trận từng access level/action |
| `EDITOR` được share lại cho người khác | Chia sẻ lan truyền trái phép | `share` là action riêng, chỉ owner/admin |
| Có `ROLE_TENANT_ADMIN` là admin mọi tenant | Lộ dữ liệu khác tenant | Ràng buộc admin role theo scope |
| Dùng `@PostAuthorize` cho thao tác xóa | Xóa xong mới từ chối | Dùng `@PreAuthorize` và DB conditional update |
| Chỉ kiểm tra quyền khi tạo token | Quyền revoke có hiệu lực trễ | Token policy, membership lookup/cache invalidation |
| Unknown action trả true | Cấp quyền mặc định không chủ ý | `default -> false`, test negative |
| Cache thiếu tenant hoặc resource ID trong key | Dùng nhầm quyết định của record khác | Cache key đủ scope/version, invalidation |
| Gọi method cùng bean qua `this` | Bỏ qua proxy Method Security | Tách bean hoặc thiết kế gọi qua Spring proxy |
| Xác thực tenant bằng request header tùy ý | Client chọn tenant được phép | So khớp server-side membership và resource |
| Thiếu log grant/revoke/admin | Không truy được ai đã cấp quyền | Audit với actor, target, before/after, reason, timestamp |
| Đổi owner mà giữ grants không kiểm soát | Người được share bởi owner cũ vẫn truy cập | Xác định quy tắc transfer + revoke/migrate ACL trong transaction |
| So sánh ID sai loại hoặc sai case action | Từ chối ngẫu nhiên hoặc cấp rộng | Chuẩn hóa interface, xử lý id/type/action fail-closed |

### 11.1. Chủ sở hữu có cần mọi quyền không?

Không nhất thiết. Owner là một **thành phần của chính sách**, không phải quyền tối thượng. Ví dụ document `LOCKED` có thể không cho owner edit; tài liệu thuộc diện lưu trữ pháp lý không cho delete; invoice đã duyệt không cho owner hủy. Phân tách status, action và các điều kiện compliance ngay trong evaluator hoặc policy service.

### 11.2. Có thể chỉ dùng role và authority mà không dùng PermissionEvaluator?

Có, nếu hệ thống chỉ yêu cầu năng lực chung như `report:export` cho toàn bộ dữ liệu hoặc không có quyền trên từng record. Nhưng với chia sẻ/owner/tenant trên từng document, `PermissionEvaluator` hoặc một custom authorization bean/manager là mô hình phù hợp hơn. Giao diện `PermissionEvaluator` là hook; không bắt buộc mọi hệ thống phải dùng nó nếu có policy engine khác kiểm soát đúng.

### 11.3. Shared EDITOR có được đổi owner không?

Không theo chính sách này. Đổi owner là **transfer ownership**, có hậu quả với ACL, audit, billing và ràng buộc tenant; nên có action riêng, xác minh người nhận, thời điểm chuyển, loại bỏ hoặc giữ grants theo quy tắc rõ ràng, test negative và audit.

### 11.4. Vì sao kiểm tra membership cả trong service.share lẫn evaluator?

Chúng có mục đích khác nhau: evaluator kiểm tra **người gọi có quyền thao tác**; service.share kiểm tra **người nhận có hợp lệ để được cấp grant**. Đây là hai bất biến. Một user là owner không có nghĩa mọi tên người nhận là hợp lệ.

### 11.5. Share bị revoke có làm mất quyền của owner hoặc admin không?

Không. Đây là các nguồn quyền **độc lập**; revoke một grant chỉ xóa quyền từ grant đó. Nếu Bob đồng thời là tenant admin, revoke grant EDITOR của Bob không làm Bob mất role admin. Khi audit và UI giải thích quyền, nên chỉ rõ người dùng được phép do owner, share hay admin để tránh hiểu sai.

## 12. Checklist kiểm tra chính sách ownership, share, admin

- [ ] Domain có resource ID, tenant, owner canonical từ nguồn server đáng tin.
- [ ] Phân biệt owner, shared viewer, shared editor, tenant admin và system admin (nếu có).
- [ ] Chính sách được viết dưới dạng ma trận action cụ thể; không suy quyền share/delete từ edit.
- [ ] Tenant boundary áp dụng **trước** các nhánh owner/share/admin.
- [ ] Tenant-admin role được gắn đúng scope; không dựa duy nhất vào role toàn cục ở ứng dụng multi-tenant thật.
- [ ] PermissionEvaluator triển khai cả hai overload cần thiết, unknown input trả false.
- [ ] Object overload reload resource canonical; không tin object do client tự tạo.
- [ ] Grant/revoke xác minh cả người gọi và người nhận; có audit và xử lý thời hạn.
- [ ] Method Security bật, expression handler được gắn PermissionEvaluator, caller đi qua proxy.
- [ ] Dùng `@PreAuthorize` cho ghi/xóa/cấp share; `@PostAuthorize` chỉ cho kết quả đọc khi thích hợp.
- [ ] Query ghi có tenant/ACL predicate hoặc kiểm tra trong transaction để hạn chế TOCTOU.
- [ ] Token/permission cache có chính sách refresh/invalidation khi revoke, chuyển tenant hoặc đổi owner.
- [ ] Integration test bao phủ owner, viewer, editor, tenant admin, khác tenant, user không thuộc directory, share bị revoke, object giả, action lạ, ID không tồn tại.
- [ ] Không cấp quyền khi dịch vụ policy/ACL gặp lỗi, và có log để phân tích quyết định bị từ chối.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`, tham số method và cấu hình `MethodSecurityExpressionHandler`.
- [Spring Security 6.5 — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html): hai overload kiểm tra đối tượng hoặc ID/type/action.
- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): mô hình ACL và tích hợp `AclPermissionEvaluator`.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `Authentication`, `GrantedAuthority` và các lớp authorization.
- [Spring Security 6.5 — SecurityExpressionRoot API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/SecurityExpressionRoot.html): các hàm `hasPermission(...)` của SpEL root.

**Ghi nhớ:** Ownership, quyền chia sẻ và quyền quản trị là **ba nguồn quyền** có phạm vi khác nhau. `PermissionEvaluator` kết hợp chúng để trả quyết định trên **một resource cụ thể**; quyền admin không nên trở thành một đường tắt vượt tenant, quyền EDITOR không mặc nhiên cho phép chia sẻ tiếp, và owner cũng phải tuân thủ trạng thái nghiệp vụ. Mọi quyết định phải dựa trên dữ liệu tin cậy, fail-closed khi thiếu thông tin và được kiểm thử cả các trường hợp bị từ chối.