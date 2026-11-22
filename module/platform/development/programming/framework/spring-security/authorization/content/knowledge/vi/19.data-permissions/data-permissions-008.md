# Quyền trên tài nguyên cha, tài nguyên con và đường dẫn lồng nhau trong Spring Security

## 1. Bài toán: URL hợp lệ chưa chắc chỉ đúng tài nguyên được phép

Một ứng dụng quản lý tài liệu tổ chức dữ liệu theo cây:

```text
Organization 10 (North)
├── Project 100 (công khai với thành viên organization)
│   ├── Document 1000 (owner: alice, share VIEWER cho bob)
│   ├── Document 1001 (owner: alice, share EDITOR cho bob)
│   └── Document 1002 (owner: manager, không share)
└── Project 110 (private: chỉ alice và manager)
    └── Document 1100 (owner: alice, vẫn có share EDITOR cho bob)

Organization 20 (South)
└── Project 200
    └── Document 2000 (owner: carol)
```

API dùng đường dẫn lồng nhau:

```http
GET /api/orgs/10/projects/100/documents/1000
GET /api/orgs/10/projects/100/documents
PUT /api/orgs/10/projects/100/documents/1001
```

Đây là **các HTTP request minh họa**, không phải lệnh chạy trong shell. Khi Bob gọi `/orgs/10/projects/100/documents/1000`, cần trả lời **ba câu hỏi riêng**:

1. Bob có thuộc **Organization 10** không?
2. Project 100 có **thực sự thuộc Organization 10** và Bob có được đi qua project đó không?
3. Document 1000 có **thực sự thuộc Project 100** và Bob có quyền **read** đối với document này không?

Nếu chỉ kiểm tra `hasAuthority("document:read")` hoặc chỉ xem `projectId` trong URL, một người dùng có thể thay đổi ID cuối cùng để truy cập document khác — lỗ hổng **Broken Object Level Authorization (BOLA/IDOR)**. Nếu chỉ kiểm tra document con, lại có thể bỏ qua việc project cha đã bị giới hạn quyền truy cập.

**Nguyên tắc trung tâm:** Quyền trên cha, quyền trên con và quyền đi qua đường dẫn (traversal) là các chính sách khác nhau. Không mặc định “được xem tổ chức = được xem mọi project = được xem mọi document”. Đường dẫn do client gửi phải được đối chiếu với **quan hệ cha–con canonical trong database**, không chỉ được tin là đúng vì URL có ba tham số.

Bài học trình bày mô hình phân quyền theo cây, nested REST path, inheritance khi được thiết kế rõ ràng, kiểm tra tại tầng Spring Security và repository, các bẫy bảo mật, cùng **ví dụ Java 17/Spring Boot 3.5.6/Spring Security 6.5.x** có integration tests.

## 2. Ba chiều quyền: scope, traversal và operation

### 2.1. Quyền vào cha không đồng nghĩa quyền trên con

Một người có thể:
- **View organization**: biết tên/metadata cơ bản của organization.
- **Traverse project**: được đi vào project, xem metadata hoặc danh sách các document mà mình có quyền.
- **Read document**: đọc nội dung một tài liệu cụ thể.
- **Edit document**: sửa nội dung sau khi kiểm tra owner, grant hoặc vai trò có phạm vi.

Một policy có thể yêu cầu **cả quyền cha và quyền con**:

```text
canReadDocument(user, org, project, document)
  = authenticated(user)
    AND memberOf(user, org)
    AND parentOf(project, org)
    AND canTraverseProject(user, project)
    AND parentOf(document, project)
    AND canReadSpecificDocument(user, document)
```

Đây là **pseudo-code**. Ở đây `parentOf` có nghĩa quan hệ foreign key thực tế từ dữ liệu server, không phải so sánh chuỗi URL. Nếu bất kỳ điều kiện nào sai hoặc không xác định, trả **deny**.

### 2.2. Ma trận minh họa

| Tình huống | GET document | Lý do |
|---|---|---|
| Alice đọc Document 1000 qua Org 10 / Project 100 | Allow | Đúng tenant/project, Alice là owner |
| Bob đọc Document 1000 qua Org 10 / Project 100 | Allow | Thành viên org, project mở, được share VIEWER |
| Bob sửa Document 1000 | Deny | VIEWER không có edit |
| Bob sửa Document 1001 | Allow | Được share EDITOR, đúng chain |
| Bob đọc Document 1002 | Deny | Cùng project nhưng không owner/share/admin |
| Bob đọc Document 1100 | Deny | Dù được share EDITOR trên document, Project 110 là private |
| Bob đọc Document 1000 qua Org 10 / Project 110 | Deny | Document 1000 không thuộc Project 110 |
| Bob đọc Document 1000 qua Org 20 / Project 100 | Deny | Project 100 không thuộc Org 20 |
| Manager quản trị Org 10 đọc Document 1002 | Allow | Role + admin binding đúng Org 10 |
| Manager Org 10 đọc Document 2000 | Deny | Không thuộc Org 20 |

**Policy của demo** cố ý yêu cầu quyền đi qua project cha kể cả khi một document được share trực tiếp. Có hệ thống cho phép link share vượt quyền xem folder cha; nếu chọn thiết kế đó, phải ghi rõ ngoại lệ, chặn lộ metadata cha, và kiểm thử. Spring Security không áp sẵn một quy tắc duy nhất cho mọi mô hình cây.

### 2.3. Ba kiểu kế thừa khác nhau

| Cơ chế | Mục đích | Điều không tự xảy ra |
|---|---|---|
| **Role hierarchy** (ví dụ ROLE_ADMIN bao hàm ROLE_USER) | Mở rộng `GrantedAuthority` | Không xác minh document thuộc project nào |
| **Spring Security ACL parent/child** | Có thể kế thừa ACE qua `parentAcl` và `entriesInheriting` | Không tạo quan hệ URL hoặc FK domain |
| **Business resource hierarchy** | Organization → Project → Document, dựa trên quan hệ DB | Không tự thành policy Spring Security nếu không code |

Đừng đặt tên nhầm “role hierarchy” khi muốn phân quyền theo cây dữ liệu. Role, ACL inheritance và business-parent scope là ba khái niệm độc lập.

## 3. Đường dẫn lồng nhau: path variables là dữ liệu do client chọn

Ví dụ:

```http
GET /api/orgs/10/projects/100/documents/1000
GET /api/orgs/10/projects/110/documents/1000
GET /api/orgs/20/projects/100/documents/1000
```

Ba request dùng **cùng document ID** nhưng hai request sau diễn tả chuỗi cha–con **không tồn tại**.

Nếu controller chỉ thực thi:

```java
Document doc = repository.findById(documentId).orElseThrow();
return doc;
```

thì `orgId` và `projectId` trên URL không được xác minh; người gọi có thể thử nhiều ID nhằm đọc trái quyền. Kiểm tra đúng cần một truy vấn hoặc policy xác minh:

```sql
SELECT d.id, d.title
FROM document d
JOIN project p ON p.id = d.project_id
WHERE d.id = :document_id
  AND d.project_id = :project_id
  AND p.organization_id = :organization_id;
```

Đây là SQL **minh họa về quan hệ canonical**: nó chưa kiểm tra user membership, ACL, owner hoặc project private. Chính sách hoàn chỉnh phải kiểm tra thêm **ai** đang gọi và được phép thực hiện **action gì**. Cần bind parameters ở JDBC/ORM, không nối trực tiếp các chuỗi từ URL.

### 3.1. Chọn HTTP status khi mismatch

Khi người dùng đã đăng nhập nhưng không được phép, có thể trả **403 Forbidden**. Với tài nguyên nhạy cảm, nhiều API cố ý trả **404 Not Found** cho cả ID không tồn tại và ID không được phép để giảm tiết lộ existence. Cả hai cách cần policy nhất quán; đừng lộ thông tin “project của tenant khác có tồn tại” qua thông báo lỗi chi tiết trước khi authorize.

Ví dụ phía dưới chọn 403 cho các trường hợp đã xác thực nhưng không đúng đường dẫn hoặc thiếu quyền, vì dễ nhìn kết quả test; anonymous vào route yêu cầu xác thực nhận 401 nhờ HTTP Basic. Đây là **quy ước response của demo**, không phải nghĩa vụ duy nhất của Spring Security.

### 3.2. Matcher order và giới hạn HTTP authorization

Trong servlet security, `AuthorizationFilter` áp dụng các `requestMatchers` theo thứ tự, **rule khớp đầu tiên** có hiệu lực. Chẳng hạn:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/orgs/**").authenticated()
    .anyRequest().denyAll()
);
```

Đây là đoạn **cấu hình**, không biên dịch độc lập. Nó kiểm tra có Authentication, **không thể tự xác minh** orgId, projectId và documentId thuộc nhau. Vì vậy demo bật `@EnableMethodSecurity` và kiểm tra quan hệ dữ liệu tại **service layer**. Nếu có nhiều servlet, custom context path, dispatcher hoặc path matching, cần test chính xác đường đi trong `SecurityFilterChain`.

Bẫy khác là quy tắc tổng quát `/api/**` đặt trước rule admin hẹp, khiến rule admin không còn được xét. Với endpoint lồng nhau, hãy giữ HTTP layer như một cửa xác thực/định tuyến và service policy là nơi quyết định object-level access.

## 4. Thiết kế chính sách cho cây dữ liệu

### 4.1. Bắt đầu từ bản ghi canonical

Không lấy organization của document chỉ từ query parameter. Mô hình quan hệ:

```text
organization(id)
project(id, organization_id, is_private)
document(id, project_id, owner_id, title)
organization_membership(organization_id, user_id)
organization_admin(organization_id, user_id)
private_project_membership(project_id, user_id)
document_share(document_id, user_id, level)
```

Trong ứng dụng thật, khóa ngoại:
- `project.organization_id → organization.id`.
- `document.project_id → project.id`.
- Các bảng membership/share dùng khóa ngoại đến user, project và document.
- Nếu có tenant_id trong nhiều bảng, dùng composite FK hoặc truy vấn ràng buộc phù hợp để tránh tạo document lệch tenant.

Không được cho client sửa `project_id`/`tenant_id` qua payload không kiểm tra. Nếu tài liệu được move sang project khác, cần xác thực quyền trên **source và destination**, xử lý ACL/share grants và update canonical parent trong transaction.

### 4.2. Project private: quyền cha là điều kiện chặn

Trong demo:
- Project 100: mọi thành viên Organization 10 có thể **đi qua**.
- Project 110: chỉ user nằm trong `private_project_membership` hoặc tenant admin có binding hợp lệ được **đi qua**.
- Project 200: tương tự Project 100, nhưng thuộc Organization 20.

Bob được share EDITOR trên Document 1100, nhưng Project 110 private và Bob không có project membership, nên Bob **không** có quyền đọc/sửa Document 1100. Chỉ khi policy quyết định “direct link sharing bypass parent” thì mới được khác; phải làm thành branch có chủ ý, không phải một bug do thiếu check.

### 4.3. Quyền trên một document riêng lẻ

Đối với đường đi hợp lệ, demo cho:
- **READ** nếu caller là owner, có share VIEWER/EDITOR, hoặc là org admin có binding trong đúng organization.
- **EDIT** nếu caller là owner, có share EDITOR, hoặc là org admin đúng phạm vi.
- **LIST documents của project** nếu caller đi qua được project **và** có authority `project:list` (hoặc là org admin đúng phạm vi); sau đó chỉ trả về các document caller **được READ riêng lẻ**.

Điều này tách **list** khỏi **read**. Cho phép list project không đồng nghĩa trả toàn bộ nội dung con. Một số sản phẩm có quyền `list-metadata` khác `read-content`; nếu cần, tách riêng cả metadata và aggregate count.

### 4.4. Admin phải gắn scope

Một principal có `ROLE_ORG_ADMIN` nhưng chỉ được quản trị Org 10 không được đọc tài liệu Org 20. Demo yêu cầu đồng thời:
1. Caller là thành viên org theo danh sách tin cậy.
2. Authentication có `ROLE_ORG_ADMIN`.
3. Database có admin binding cho **chính orgId đó**.

Không dùng `hasRole('ADMIN') OR canRead(...)` làm policy tổng quát, vì nhánh OR có thể bỏ qua tenant boundary. Nếu cần system administrator, tạo use case và permission riêng, audit/approval và test thật chặt.

## 5. Tài nguyên cha có thể cấp quyền cho con không?

Có ba lựa chọn thường gặp:

**A. Strict intersection (mặc định ở demo):**
```text
canAccessChild = canTraverseParent AND canAccessChildDirectly
```

Ưu điểm: ít quyền bất ngờ, dễ giải thích. Nhược: share một child cho user chưa vào parent sẽ không có hiệu lực.

**B. Explicit inheritance:**
```text
canAccessChild =
    parentBoundarySatisfied
    AND (directChildGrant OR inheritedGrantFromParent)
```

Cần định nghĩa parent grant nào được phép kế thừa; có thể cho `project:read-children` thừa xuống document, nhưng không tự cho `project:edit` suy thành xóa document. Ghi rõ độ sâu, mức quyền, ngoại lệ, revoke và cách cache.

**C. Share-link exception:**
```text
canAccessChild =
    (validScopedShareTokenWithNoParentMetadataLeak)
    OR (ordinaryParentAndChildPolicy)
```

Cần token khó đoán, expiry, revoke, permission scope và chống rò parent information. Không suy luận từ `?shared=true` hoặc URL tự chọn rằng user được bỏ qua parent authorization.

### 5.1. Với Spring Security ACL inheritance

Spring Security ACL lưu `parent_object` và `entries_inheriting` trong `acl_object_identity`. Một thiết lập khái niệm (phải đặt trong service có cấu hình ACL phù hợp):

```java
ObjectIdentity parentId =
    new ObjectIdentityImpl(Project.class, 100L);
ObjectIdentity childId =
    new ObjectIdentityImpl(Document.class, 1000L);

Acl parentAcl = aclService.readAclById(parentId);
MutableAcl childAcl =
    (MutableAcl) aclService.readAclById(childId);

childAcl.setParent(parentAcl);
childAcl.setEntriesInheriting(true);
mutableAclService.updateAcl(childAcl);
```

Đây là **mẫu tích hợp**, cần classes và imports từ Spring Security ACL, DB schema, ACL admin policy và transaction. Nó làm ACL child được phép xét ACE inherited từ parent (tùy granting strategy); **không** kiểm tra canonical `document.project_id` hoặc tự thêm `tenant_id` vào policy. Để giữ an toàn:
- Không nối ACL parent từ tenant khác nếu không có một chính sách cho phép rõ ràng.
- Test deny ACE, order, local ACE so với inherited ACE và thu hồi quyền cha.
- Khi move document sang project mới, xem lại ACL parent, grants cũ và cache.
- Không nhầm `roleHierarchy` với `parentAcl`.

Demo chạy được bên dưới **không dùng ACL module** để người học thấy rõ mối quan hệ parent path, tenant membership, role scope và child-level sharing. ACL inheritance ở đây là giải pháp mở rộng, không phải “tính năng được bật tự động”.

## 6. Demo chạy được: Java 17, Spring Boot 3.5.6, Spring Security 6.5.x

Ứng dụng lưu fixture bằng `Map`, có controller REST với đường dẫn lồng nhau, policy bean thực thi đúng quan hệ canonical, service `@PreAuthorize` và JUnit + MockMvc. Nó không cần DB nên dễ chạy. Phần 8 sẽ trình bày cách thay bằng JDBC/JPA truy vấn có ràng buộc.

### 6.1. Cây file

```text
nested-resource-authorization/
  pom.xml
  src/main/java/com/example/nested/
    NestedAuthorizationApplication.java
    SecurityConfig.java
    Catalog.java
    TreeAuthorization.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/nested/
    NestedAuthorizationTest.java
```

### 6.2. pom.xml

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
  <artifactId>nested-resource-authorization</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

`spring-boot-starter-security` hỗ trợ Method Security nhưng **không tự bật** nó; `@EnableMethodSecurity` sẽ được khai báo ở `SecurityConfig`. Test dùng `@WithMockUser`, không triển khai password hoặc JWT thật.

### 6.3. Spring Boot entrypoint

**`src/main/java/com/example/nested/NestedAuthorizationApplication.java`**

```java
package com.example.nested;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NestedAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedAuthorizationApplication.class, args);
    }
}
```

### 6.4. HTTP Security và Method Security

**`src/main/java/com/example/nested/SecurityConfig.java`**

```java
package com.example.nested;

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
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`SecurityFilterChain` yêu cầu xác thực trên tất cả đường `/api/**` và deny phần còn lại. Nó **không tự cấp** quyền trên tài liệu. Phần đó nằm ở `DocumentService`, để những lời gọi từ service/batch/job vẫn phải qua object-level authorization nếu được gọi qua Spring proxy.

Demo giữ mặc định CSRF của Spring Security: khi test HTTP PUT, phải cung cấp `csrf()`. Không vô hiệu hóa CSRF chỉ để test dễ viết; trong REST API dùng bearer token thuần không dựa trên cookie, chiến lược CSRF có thể khác và cần cấu hình dựa trên cơ chế authentication thật.

### 6.5. Catalog: quan hệ cha–con và grants phía server

**`src/main/java/com/example/nested/Catalog.java`**

```java
package com.example.nested;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class Catalog {
    public record Project(Long id, Long orgId, boolean privateProject) {}
    public record Document(
            Long id, Long projectId, String owner, String title) {}
    public enum ShareLevel { VIEWER, EDITOR }

    private final Map<Long, Project> projects = Map.of(
        100L, new Project(100L, 10L, false),
        110L, new Project(110L, 10L, true),
        200L, new Project(200L, 20L, false)
    );

    private final Set<String> orgMembers = Set.of(
        "10:alice", "10:bob", "10:manager",
        "20:carol", "20:dave"
    );

    private final Set<String> adminBindings = Set.of(
        "10:manager", "20:carol"
    );

    private final Set<String> privateProjectMembers = Set.of(
        "110:alice", "110:manager"
    );

    private final Map<String, ShareLevel> documentShares = Map.of(
        "1000:bob", ShareLevel.VIEWER,
        "1001:bob", ShareLevel.EDITOR,
        "1100:bob", ShareLevel.EDITOR
    );

    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>();

    public Catalog() {
        reset();
    }

    public synchronized void reset() {
        documents.clear();
        documents.put(1000L,
            new Document(1000L, 100L, "alice", "Alice notes"));
        documents.put(1001L,
            new Document(1001L, 100L, "alice", "Team draft"));
        documents.put(1002L,
            new Document(1002L, 100L, "manager", "Manager plan"));
        documents.put(1100L,
            new Document(1100L, 110L, "alice", "Private strategy"));
        documents.put(2000L,
            new Document(2000L, 200L, "carol", "South report"));
    }

    public Project project(Long id) {
        return id == null ? null : projects.get(id);
    }

    public Document document(Long id) {
        return id == null ? null : documents.get(id);
    }

    public boolean isOrgMember(Long orgId, String username) {
        return orgId != null
            && username != null
            && orgMembers.contains(orgId + ":" + username);
    }

    public boolean isOrgAdminBinding(Long orgId, String username) {
        return orgId != null
            && username != null
            && adminBindings.contains(orgId + ":" + username);
    }

    public boolean isPrivateProjectMember(
            Long projectId, String username) {
        return projectId != null
            && username != null
            && privateProjectMembers.contains(projectId + ":" + username);
    }

    public ShareLevel shareLevel(Long id, String username) {
        if (id == null || username == null) {
            return null;
        }
        return documentShares.get(id + ":" + username);
    }

    public List<Document> documentsForProject(Long projectId) {
        return documents.values().stream()
            .filter(d -> d.projectId().equals(projectId))
            .sorted(Comparator.comparing(Document::id))
            .toList();
    }

    public Document rename(Long projectId, Long id, String newTitle) {
        Document updated = documents.computeIfPresent(id, (key, old) ->
            old.projectId().equals(projectId)
                ? new Document(old.id(), old.projectId(),
                    old.owner(), newTitle)
                : old
        );

        if (updated == null || !updated.projectId().equals(projectId)) {
            throw new IllegalStateException("Path relation changed");
        }
        return updated;
    }
}
```

Đây là **storage demo**, không phải database bảo mật production. `Catalog` chỉ lưu những mối quan hệ và share đã seed từ server; các method không nhận một chuỗi `owner`/`role` do client tùy ý tự khai để làm căn cứ.

Hãy quan sát:
- Project 100 thuộc Org 10.
- Project 110 thuộc Org 10 nhưng private.
- Document 1000/1001/1002 thuộc Project 100.
- Document 1100 thuộc Project 110; dù Bob được share EDITOR, Bob không thuộc project private.
- Document 2000 thuộc Project 200 của Org 20.
- Manager có binding admin ở Org 10; role trong Authentication sẽ được kiểm tra thêm.
- `reset()` phục vụ kiểm thử trước mỗi test; trong production, thay bằng repository/JPA, FK và transaction.

### 6.6. TreeAuthorization: kiểm tra từng cấp, fail-closed

**`src/main/java/com/example/nested/TreeAuthorization.java`**

```java
package com.example.nested;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("treeAuth")
public class TreeAuthorization {
    private final Catalog catalog;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public TreeAuthorization(Catalog catalog) {
        this.catalog = catalog;
    }

    private boolean hasAuthority(Authentication auth, String expected) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (expected.equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    private boolean isOrgAdmin(Authentication auth, Long orgId) {
        return hasAuthority(auth, "ROLE_ORG_ADMIN")
            && catalog.isOrgAdminBinding(orgId, auth.getName());
    }

    private boolean canTraverse(
            Authentication auth, Long orgId, Long projectId) {

        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)
                || orgId == null || projectId == null) {
            return false;
        }

        Catalog.Project project = catalog.project(projectId);

        // Kiểm tra quan hệ project -> organization CANONICAL.
        if (project == null || !orgId.equals(project.orgId())) {
            return false;
        }

        if (!catalog.isOrgMember(orgId, auth.getName())) {
            return false;
        }

        // Project private yêu cầu quyền đi qua cha.
        return !project.privateProject()
            || catalog.isPrivateProjectMember(projectId, auth.getName())
            || isOrgAdmin(auth, orgId);
    }

    public boolean canList(
            Authentication auth, Long orgId, Long projectId) {
        return canTraverse(auth, orgId, projectId)
            && (hasAuthority(auth, "project:list")
                || isOrgAdmin(auth, orgId));
    }

    public boolean canRead(
            Authentication auth, Long orgId,
            Long projectId, Long documentId) {

        if (!canTraverse(auth, orgId, projectId)) {
            return false;
        }

        Catalog.Document doc = catalog.document(documentId);

        // Kiểm tra document -> project CANONICAL.
        if (doc == null || !projectId.equals(doc.projectId())) {
            return false;
        }

        return auth.getName().equals(doc.owner())
            || catalog.shareLevel(documentId, auth.getName())
                == Catalog.ShareLevel.VIEWER
            || catalog.shareLevel(documentId, auth.getName())
                == Catalog.ShareLevel.EDITOR
            || isOrgAdmin(auth, orgId);
    }

    public boolean canWrite(
            Authentication auth, Long orgId,
            Long projectId, Long documentId) {

        if (!canTraverse(auth, orgId, projectId)) {
            return false;
        }

        Catalog.Document doc = catalog.document(documentId);
        if (doc == null || !projectId.equals(doc.projectId())) {
            return false;
        }

        return auth.getName().equals(doc.owner())
            || catalog.shareLevel(documentId, auth.getName())
                == Catalog.ShareLevel.EDITOR
            || isOrgAdmin(auth, orgId);
    }
}
```

**Luồng deny quan trọng:**
1. Authentication null, anonymous hoặc chưa authenticated → deny.
2. Project ID không tồn tại hoặc không thuộc `orgId` trong URL → deny.
3. Caller không là member Org đó → deny.
4. Project private và caller không là member riêng/admin đã được bind → deny.
5. Document ID không tồn tại hoặc không thuộc `projectId` trong URL → deny.
6. Caller không là owner, share recipient phù hợp hoặc org admin có binding → deny.

Bộ kiểm tra này **không** dùng `startsWith("/orgs/10")` để quyết định tenant; nó so sánh ID dựa vào records tin cậy. Một người có chuỗi `ROLE_ORG_ADMIN` mà không có admin binding đúng org cũng không được bỏ qua kiểm tra cha.

### 6.7. DocumentService: object-level authorization nằm ở service

**`src/main/java/com/example/nested/DocumentService.java`**

```java
package com.example.nested;

import java.util.List;
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
    public record DocumentView(Long id, String title) {}

    private final Catalog catalog;
    private final TreeAuthorization policy;

    public DocumentService(Catalog catalog, TreeAuthorization policy) {
        this.catalog = catalog;
        this.policy = policy;
    }

    private static DocumentView view(Catalog.Document d) {
        return new DocumentView(d.id(), d.title());
    }

    @PreAuthorize(
        "@treeAuth.canRead(authentication, " +
        "#orgId, #projectId, #documentId)"
    )
    public DocumentView read(
            @P("orgId") Long orgId,
            @P("projectId") Long projectId,
            @P("documentId") Long documentId) {
        return view(catalog.document(documentId));
    }

    @PreAuthorize(
        "@treeAuth.canList(authentication, #orgId, #projectId)"
    )
    public List<DocumentView> list(
            @P("orgId") Long orgId,
            @P("projectId") Long projectId) {

        Authentication caller =
            SecurityContextHolder.getContext().getAuthentication();

        // LIST được cấp quyền nhưng mỗi phần tử phải qua READ riêng.
        return catalog.documentsForProject(projectId).stream()
            .filter(d -> policy.canRead(
                caller, orgId, projectId, d.id()))
            .map(DocumentService::view)
            .toList();
    }

    @PreAuthorize(
        "@treeAuth.canWrite(authentication, " +
        "#orgId, #projectId, #documentId)"
    )
    public DocumentView rename(
            @P("orgId") Long orgId,
            @P("projectId") Long projectId,
            @P("documentId") Long documentId,
            String title) {

        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Title required"
            );
        }

        Authentication caller =
            SecurityContextHolder.getContext().getAuthentication();

        // Recheck tại service. Production cần row lock/version/SQL predicate.
        if (!policy.canWrite(caller, orgId, projectId, documentId)) {
            throw new AccessDeniedException("Permission changed");
        }

        return view(catalog.rename(projectId, documentId, title));
    }
}
```

`@P` cố định tên biến SpEL `#orgId`, `#projectId` và `#documentId`. `@EnableMethodSecurity` cho Spring AOP proxy chặn lời gọi trước thân method; nếu một caller dùng `new DocumentService(...)` hoặc self-invocation trong cùng bean thì annotation có thể bị bỏ qua.

**Vì sao bảo vệ service thay vì chỉ controller?** Cùng nghiệp vụ có thể được gọi bởi HTTP, scheduler, message consumer hay API khác. Service-level check làm ranh giới quyền dễ tái sử dụng; tuy nhiên phải bảo đảm các entry points không bypass proxy và repo/query vẫn có tenant predicate khi chuyển sang database thật.

**Vì sao LIST phải lọc từng tài liệu?** Quyền nhìn vào Project 100 không có nghĩa được trả Document 1002 của manager. Đây là ví dụ trong RAM; với database lớn, đưa điều kiện READ/tenant/ACL vào SQL trước phân trang để tránh N+1 và rò metadata/count.

### 6.8. DocumentController: ba endpoint lồng nhau

**`src/main/java/com/example/nested/DocumentController.java`**

```java
package com.example.nested;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orgs")
public class DocumentController {
    public record RenameBody(String title) {}

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{orgId}/projects/{projectId}/documents/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable("orgId") Long orgId,
            @PathVariable("projectId") Long projectId,
            @PathVariable("documentId") Long documentId) {
        return service.read(orgId, projectId, documentId);
    }

    @GetMapping("/{orgId}/projects/{projectId}/documents")
    public List<DocumentService.DocumentView> list(
            @PathVariable("orgId") Long orgId,
            @PathVariable("projectId") Long projectId) {
        return service.list(orgId, projectId);
    }

    @PutMapping("/{orgId}/projects/{projectId}/documents/{documentId}")
    public DocumentService.DocumentView rename(
            @PathVariable("orgId") Long orgId,
            @PathVariable("projectId") Long projectId,
            @PathVariable("documentId") Long documentId,
            @RequestBody RenameBody body) {
        return service.rename(
            orgId, projectId, documentId,
            body == null ? null : body.title()
        );
    }
}
```

Controller không tự suy luận quyền từ path. Nó chuyển nguyên ba ID vào service, nơi `TreeAuthorization` so sánh với canonical hierarchy. Endpoint đọc/list trả JSON; endpoint sửa dùng PUT và một body JSON như:

```json
{"title":"Revised draft"}
```

API demo chưa có validator ở DTO, audit log hoặc optimistic locking; `DocumentService` đã từ chối title rỗng và kiểm tra quyền trước khi cập nhật.

## 7. Kiểm thử tích hợp Spring Security và các đường dẫn giả

**`src/test/java/com/example/nested/NestedAuthorizationTest.java`**

```java
package com.example.nested;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NestedAuthorizationTest {
    @Autowired MockMvc mvc;
    @Autowired Catalog catalog;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        catalog.reset();
    }

    private static String documentPath(
            long org, long project, long document) {
        return "/api/orgs/" + org
            + "/projects/" + project
            + "/documents/" + document;
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerReadsSharedDocument() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1000))
            .andExpect(jsonPath("$.title").value("Alice notes"));
    }

    @Test
    @WithMockUser(username = "bob")
    void editorAlsoReadsSharedDocument() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1001)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob")
    void sameProjectDoesNotGrantReadOnEveryChild() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1002)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void privateProjectBlocksDirectDocumentShare() throws Exception {
        mvc.perform(get(documentPath(10, 110, 1100)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void fakeProjectInUrlCannotMoveDocument() throws Exception {
        mvc.perform(get(documentPath(10, 110, 1000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void fakeOrganizationInUrlCannotMoveProject() throws Exception {
        mvc.perform(get(documentPath(20, 100, 1000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void userCannotReadDifferentOrganization() throws Exception {
        mvc.perform(get(documentPath(20, 200, 2000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "project:list")
    void listingShowsOnlyReadableDocuments() throws Exception {
        mvc.perform(get("/api/orgs/10/projects/100/documents"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].id").value(1000))
            .andExpect(jsonPath("$[1].id").value(1001));
    }

    @Test
    @WithMockUser(username = "bob")
    void documentReadDoesNotGrantProjectList() throws Exception {
        mvc.perform(get("/api/orgs/10/projects/100/documents"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "project:list")
    void privateProjectListStillDenied() throws Exception {
        mvc.perform(get("/api/orgs/10/projects/110/documents"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerCannotEdit() throws Exception {
        mvc.perform(put(documentPath(10, 100, 1000))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
        assertEquals("Alice notes", catalog.document(1000L).title());
    }

    @Test
    @WithMockUser(username = "bob")
    void editorCanEditSharedDocument() throws Exception {
        mvc.perform(put(documentPath(10, 100, 1001))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Revised\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Revised"));
        assertEquals("Revised", catalog.document(1001L).title());
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadChildInPrivateProject() throws Exception {
        mvc.perform(get(documentPath(10, 110, 1100)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "ORG_ADMIN")
    void boundOrgAdminReadsAnyChildInOwnOrg() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isOk());
        mvc.perform(get(documentPath(10, 110, 1100)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "ORG_ADMIN")
    void orgAdminCannotCrossOrgScope() throws Exception {
        mvc.perform(get(documentPath(20, 200, 2000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "ORG_ADMIN")
    void roleWithoutOrgAdminBindingIsNotEnough() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1002)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mallory", roles = "ORG_ADMIN")
    void roleWithoutOrgMembershipIsNotEnough() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestIsChallenged() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownDocumentFailsClosed() throws Exception {
        mvc.perform(get(documentPath(10, 100, 9999)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void missingCsrfBlocksPutEvenForOwner() throws Exception {
        mvc.perform(put(documentPath(10, 100, 1000))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Cannot bypass CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void methodSecurityWorksWithoutHttpController() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(10L, 100L, 1002L));
    }

    @Test
    @WithMockUser(username = "alice")
    void methodSecurityRejectsForgedParentIds() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(20L, 100L, 1000L));
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn test
```

**Kết quả dự kiến:** 22 bài test JUnit pass (không có failures/errors) nếu sử dụng đúng các dependencies và cấu hình trên. Đây là **kỳ vọng dựa trên code**, không phải khẳng định đã chạy Maven. Các test dùng `@WithMockUser` để kiểm thử authorization, không giả lập một hệ thống đăng nhập JWT hay password thật.

Các điểm có giá trị nhất:
- **Sai orgId hoặc projectId trên URL** → deny dù document ID có thật.
- **Cùng project** không suy ra được đọc tất cả document.
- **Share EDITOR trên con** không tự đi xuyên project private cha.
- **Quyền list** tách biệt quyền đọc: chỉ trả document đã có READ, không trả cả cây.
- **Admin role không có org binding** → deny.
- **Admin đúng Org 10 nhưng gọi Org 20** → deny.
- **PUT thiếu CSRF** → deny theo cấu hình web security mặc định.
- **Lời gọi service trực tiếp** vẫn qua `@PreAuthorize` và bị chặn khi dùng Spring bean.

### 7.1. Ma trận kết quả trọng tâm

| Caller | URL/hành động | Kỳ vọng |
|---|---|---|
| bob | GET Org10/Project100/Document1000 | 200 |
| bob | GET Org10/Project100/Document1002 | 403 |
| bob | GET Org10/Project110/Document1100 | 403 |
| bob | GET Org20/Project100/Document1000 | 403 |
| bob có `project:list` | GET danh sách Project100 | 200; chỉ 2 document |
| bob không có `project:list` | GET danh sách Project100 | 403 |
| bob | PUT Document1000 với CSRF | 403 |
| bob | PUT Document1001 với CSRF | 200 |
| manager/ROLE_ORG_ADMIN | GET document trong Org10 | 200 |
| manager/ROLE_ORG_ADMIN | GET document thuộc Org20 | 403 |
| anonymous | GET bất kỳ `/api/**` được bảo vệ | 401 |

HTTP 403 ở các tình huống deny là kết quả của authentication đầy đủ nhưng method authorization không pass; 401 là challenge của HTTP Basic cho request chưa xác thực. Thay login form, exception handler hoặc API gateway có thể làm mapping HTTP khác.

## 8. Dùng JDBC/JPA thay Map: query phải bảo vệ cả cha và con

Ví dụ Map đơn giản giúp thấy policy, nhưng một API production thường có database hàng triệu documents. Nếu lấy tất cả tài liệu về RAM rồi `filter(d -> canRead(...))`, có thể có:
- **N+1 queries** để kiểm tra share/ACL cho từng row.
- Sai phân trang: lấy 20 rows rồi lọc còn 3, trong khi tổng page/count không phản ánh quyền.
- Rò metadata qua total count, facet, sorter hoặc các aggregate không được scope.
- Race: giữa bước kiểm tra quyền và bước tải/sửa dữ liệu, project đã đổi parent hoặc share đã bị revoke.

### 8.1. Query một document với canonical parent path

```sql
SELECT d.id, d.title
FROM document d
JOIN project p ON p.id = d.project_id
WHERE d.id = :documentId
  AND p.id = :projectId
  AND p.organization_id = :orgId;
```

Sau đó vẫn cần kiểm tra caller có membership, private-project access và document read grant. Không dùng kết quả query về quan hệ như bằng chứng mọi user đều được đọc tài liệu đó.

### 8.2. Query danh sách đã lọc quyền trước phân trang

Mẫu SQL dưới đây thể hiện **ý tưởng predicate**, không phải file migration độc lập. `:userId` đến từ authenticated principal; `:isBoundOrgAdmin` là boolean được **server tính** từ role và binding trong đúng org, tuyệt đối không lấy từ client:

```sql
SELECT d.id, d.title
FROM document d
JOIN project p ON p.id = d.project_id
WHERE p.id = :projectId
  AND p.organization_id = :orgId
  AND EXISTS (
      SELECT 1 FROM org_membership om
      WHERE om.org_id = :orgId
        AND om.user_id = :userId
  )
  AND (
      p.is_private = FALSE
      OR :isBoundOrgAdmin = TRUE
      OR EXISTS (
          SELECT 1 FROM project_membership pm
          WHERE pm.project_id = p.id
            AND pm.user_id = :userId
      )
  )
  AND (
      d.owner_id = :userId
      OR :isBoundOrgAdmin = TRUE
      OR EXISTS (
          SELECT 1 FROM document_share ds
          WHERE ds.document_id = d.id
            AND ds.user_id = :userId
            AND ds.access_level IN ('VIEWER', 'EDITOR')
      )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :pageOffset;
```

SQL minh họa cần được điều chỉnh cho schema và dialect thật. Permission `project:list` vẫn phải được kiểm tra ở service/SQL policy **trước khi** chạy query. Count query phải áp dụng **cùng** scope và permission predicates; nếu không có thể rò số lượng tài liệu mà user không có quyền.

### 8.3. Update dữ liệu có điều kiện và kiểm tra affected rows

```sql
UPDATE document
SET title = :newTitle
WHERE id = :documentId
  AND project_id = :projectId
  AND EXISTS (
      SELECT 1
      FROM project p
      WHERE p.id = :projectId
        AND p.organization_id = :orgId
  );
```

Đây mới chỉ là điều kiện **path**, chưa đủ user authorization. Để tránh BOLA/TOCTOU, bổ sung membership/private-project/owner/share predicate đúng với quyền EDITOR, dùng row lock hoặc isolation/version thích hợp và bắt buộc kiểm tra **affected rows = 1**. Một service đã vượt `@PreAuthorize` không có nghĩa SQL update được phép bỏ tenant và authorization predicate.

Nếu chuyển document sang project khác, xác minh cả parent cũ và parent mới, tenant, project privacy và ACL inheritance; không cho đổi `project_id` qua endpoint rename bất kỳ.

## 9. Lỗi thường gặp trong quyền cha–con

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `hasRole('ADMIN') OR canReadChild(...)` | Admin có thể bypass tenant | Kiểm tra tenant/parent scope trước mọi nhánh role |
| GET document bằng ID, bỏ qua org/project trong URL | IDOR/BOLA qua path giả | JOIN/verify canonical parent chain |
| Có quyền xem project thì trả toàn bộ documents | Lộ child không được share | Kiểm tra READ từng child, lọc tại query |
| Share child thì tự bỏ qua project private | Vượt policy cha | Chọn inheritance/exception rõ ràng, test |
| Trust `organizationId` từ JSON/header | Caller tự khai tenant | Lấy scope từ auth + dữ liệu DB tin cậy |
| Dùng `startsWith` trên URL để so tenant | Sai prefix, encoding và route matching | So sánh typed IDs từ DB |
| Role hierarchy thay thế resource hierarchy | Có ROLE_ADMIN rồi đọc mọi record | Giữ business object policy riêng |
| ACL inheritance áp dụng tự động cho domain tree | Quyền cha rơi xuống con ngoài ý định | Cấu hình parent/entriesInheriting có chủ đích |
| Chỉ kiểm tra `@PostAuthorize` cho mutation | Tác dụng phụ xảy ra trước deny | `@PreAuthorize` và DB conditional update |
| Chỉ ẩn nút ở UI | Client gọi API trực tiếp | Check tại server và repository |
| Lọc sau phân trang | Thiếu item, rò total count | Filter trong SQL trước paging/count |
| Không check khi chuyển parent/project | ACL/share cũ còn hiệu lực sai | Transaction, verify source + destination |
| User rời org nhưng token role còn hạn | Quyền stale | Recheck membership/revoke/caching |
| Không test method service độc lập | Job/batch có thể bypass HTTP policy | Bảo vệ service boundary và integration test |
| Lẫn organization admin với system admin | Quyền lan sang org khác | Role binding theo org và audit |
| Cache decision thiếu parent ID | Dùng quyền của cây khác | Key gồm principal/tenant/project/document/action/version |
| User biết ID child nên đoán parent tồn tại | Enumeration thông qua lỗi | Deny/404 nhất quán, hạn chế lộ metadata |

### 9.1. Đường dẫn thay đổi không phải bằng chứng quyền kế thừa

Một route như `/api/orgs/10/projects/100/documents/1000` chỉ biểu diễn **ý định truy cập**. Nó không thay database và không tạo ACE. Dù API có hỗ trợ path variables trong `WebExpressionAuthorizationManager`, một biểu thức so sánh tham số path chỉ xử lý giá trị lấy từ URL; nó cần lookup dữ liệu canonical mới chứng minh được quan hệ parent/child.

### 9.2. Không cho phép escalation bằng move/clone

Nếu user được WRITE Document 1000 nhưng không được quản trị Project 110, họ không được tự move document sang Project 110 rồi gọi vào đường mới để có thêm quyền. Move/clone phải được kiểm tra theo cả nguồn và đích, và xác định ownership, ACL grants, inheritance, tenant boundary cho object mới. Với clone, **không mặc nhiên copy tất cả ACE** nếu nội dung có dữ liệu nhạy cảm hoặc owner chuyển.

### 9.3. Deny và inheritance cần quyết định rõ

Một số ACL policy có thể diễn giải local deny/allow, inherited allow/deny và `ace_order` theo thứ tự. Không suy luận rằng “parent có READ thì child luôn READ” khi ACL child có deny ACE, `entries_inheriting=false` hoặc strategy riêng. Khi người dùng báo “tôi có quyền trên project mà không xem được document”, cần truy nguyên **quyền effective** trên cả cha và con thay vì chỉ xem một hàng `acl_entry`.

## 10. Checklist áp dụng

- [ ] Mô hình canonical Organization → Project → Document có FK/ID đáng tin.
- [ ] Chính sách xác định rõ quyền traverse cha, quyền trên child và hành động read/edit/list.
- [ ] Membership và admin binding có scope theo đúng organization, không dùng role global như bypass.
- [ ] Khi lấy document bằng ID, đối chiếu `doc.projectId == URL.projectId` và `project.orgId == URL.orgId`.
- [ ] Project private được kiểm tra trước document grant, trừ ngoại lệ chia sẻ được thiết kế chính thức.
- [ ] `@EnableMethodSecurity` đã bật; `@PreAuthorize` trên Spring-managed service boundary.
- [ ] Đường đọc trực tiếp, list, edit, batch và background đều có object-level guard.
- [ ] Query list áp dụng permission predicate trước paging/count, không lộ aggregate dữ liệu ngoài scope.
- [ ] Update có tenant/project/authorization predicates, affected-row check và concurrency control.
- [ ] ACL parent/entriesInheriting/role hierarchy được phân biệt và kiểm thử riêng nếu dùng.
- [ ] Đường dẫn không tồn tại/sai cha/khác org/action sai có deny an toàn, không lộ quá nhiều thông tin.
- [ ] API move/clone/reparent kiểm tra cả source và destination và chính sách ACL sau move.
- [ ] User bị remove khỏi org/project hoặc share bị revoke được ngăn theo SLA cache/token.
- [ ] Integration test bao phủ giả path, child không share, private parent, list lọc, admin scope, CSRF và method calls không qua controller.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Bob có `project:list` trên Project 100. Bob được đọc mọi Document trong project không?

**Trả lời:** Không. Quyền list là quyền mở danh sách, nhưng từng document vẫn cần điều kiện owner/share/admin READ. Nếu trả cả nội dung hoặc metadata nhạy cảm, phải lọc tại query.

**Câu 2.** Bob được share EDITOR cho Document 1100. Tại sao vẫn không đọc được?

**Trả lời:** Project 110 là private và demo yêu cầu đi qua cha trước. Bob chưa được phép traverse Project 110; child grant không bypass parent.

**Câu 3.** User đổi URL từ `/orgs/10/projects/100/documents/1000` thành `/orgs/20/projects/100/documents/1000`. Chỉ có role kiểm tra trên document là đủ không?

**Trả lời:** Không. Project 100 thực tế thuộc Org 10; policy phải so sánh dữ liệu canonical, không tin orgId client chọn.

**Câu 4.** ACL parent inheritance có tự xác thực `document.project_id` không?

**Trả lời:** Không. `parentAcl`/`entriesInheriting` là cơ chế kế thừa ACE, không phải xác minh domain foreign key hoặc tenant.

**Câu 5.** Có `ROLE_ORG_ADMIN` nhưng không có admin binding cho Org 20; có được đọc Document 2000 không?

**Trả lời:** Không theo demo. Quyền quản trị được giới hạn bằng org membership và binding phía server, không phải role string toàn cục.

## 12. Tài liệu chính thức

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, matcher order, URI templates và request authorization.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, bean policy, `@P` và các giới hạn của `@PostAuthorize`.
- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): ACL object identity, parent, inheritance và ACE.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `Authentication`, `GrantedAuthority` và `AuthorizationManager`.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm tra object ID tại mọi endpoint nhận ID do client kiểm soát.

**Ghi nhớ:** Quyền truy cập cha không tự biến thành quyền đọc/sửa con; quyền trên con có thể bị giới hạn bởi project/organization cha. Đường dẫn lồng nhau chỉ là dữ liệu do client gửi. Để chống BOLA/IDOR, hãy **xác minh từng quan hệ cha–con từ dữ liệu canonical**, kiểm tra membership và scope của admin, áp dụng quyền trên từng object và đẩy điều kiện vào SQL khi cần phân trang, ghi dữ liệu hoặc bảo vệ khỏi cạnh tranh.