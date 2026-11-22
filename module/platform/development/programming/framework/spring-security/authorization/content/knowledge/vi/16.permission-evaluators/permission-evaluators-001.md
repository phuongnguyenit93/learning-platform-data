# Đặt tên quyền theo hành động trên loại tài nguyên — Spring Security PermissionEvaluator

## 1. Bài toán: một “quyền” cần có tên đủ rõ để thực thi nhất quán

Một hệ thống có nhiều loại tài nguyên: tài liệu (`document`), hóa đơn (`invoice`), đơn đặt hàng (`purchase-order`), báo cáo (`report`). Trên mỗi loại tài nguyên có những hành động khác nhau: xem, tạo mới, chỉnh sửa, xóa, phê duyệt, xuất dữ liệu. Viết chung chung `READ`, `WRITE` hay `ADMIN` không cho biết “đọc cái gì”, trong khi một chuỗi quá cụ thể như `read-document-482-for-alice-in-tenant-7` lại khó quản lý và rất dễ phát sinh quá nhiều authority.

Quy ước hữu ích là:

```text
<resource>:<action>

document:read
document:create
document:edit
document:delete
invoice:read
invoice:approve
report:export
purchase-order:approve
```

Đây là **quy ước do ứng dụng chọn**, **không phải cú pháp bắt buộc** của Spring Security. Điểm mấu chốt là tách rõ:

1. **Loại tài nguyên** (*resource type*): `document`, `invoice`, `purchase-order`.
2. **Hành động** (*action/permission*): `read`, `create`, `edit`, `delete`, `approve`, `export`.
3. **Danh tính/ngữ cảnh**: ai đang đăng nhập, thuộc tenant nào, là owner hay người phê duyệt?
4. **Tài nguyên cụ thể** (*resource instance*): ví dụ document id 42 thuộc tenant A và owner alice.

Một authority như `document:edit` nói rằng người dùng có **năng lực chỉnh sửa loại tài nguyên document**. Nó **chưa** khẳng định người dùng được chỉnh sửa **mọi** document. Muốn kiểm tra quyền trên một tài liệu cụ thể, ta phải kết hợp authority với owner, tenant, trạng thái bản ghi và chính sách nghiệp vụ.

Trong Spring Security, **`PermissionEvaluator`** là một điểm mở rộng dành cho kiểm tra quyền trên đối tượng. Bài này tập trung cách **đặt tên quyền theo hành động và loại tài nguyên** sao cho có thể dùng nhất quán giữa `GrantedAuthority`, `hasPermission(...)`, database quyền, annotation, log audit và kiểm thử.

## 2. Phân biệt năm khái niệm dễ bị nhập nhằng

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Role | `ROLE_DOC_ADMIN` | Vai trò của chủ thể; thường được ánh xạ thành `GrantedAuthority` có tiền tố `ROLE_` |
| Authority | `document:edit` | Chuỗi quyền được cấp cho `Authentication`; `hasAuthority` so khớp đúng chuỗi |
| Resource type | `Document` | Loại đối tượng được kiểm tra bởi `PermissionEvaluator`; có thể là alias do ứng dụng quy định |
| Action/permission | `edit` | Thao tác được hỏi trên một tài nguyên cụ thể |
| Resource instance | `Document(id=42, tenant=t1, owner=alice)` | Bản ghi cụ thể để xét owner, tenant, trạng thái và ràng buộc |

Sự khác biệt cốt lõi xuất hiện ở hai biểu thức:

```java
@PreAuthorize("hasAuthority('document:edit')")
public void editAnyDocument(long documentId) { /* ... */ }

@PreAuthorize("hasPermission(#documentId, 'Document', 'edit')")
public void editOneDocument(@P("documentId") Long documentId) { /* ... */ }
```

Hai method trên là **mẫu minh họa**, chưa chạy độc lập vì thiếu class/import và thân nghiệp vụ. Trong biểu thức đầu, Spring chỉ kiểm tra có `GrantedAuthority("document:edit")`. Trong biểu thức thứ hai, Spring **ủy thác** cho `PermissionEvaluator`, gửi id, targetType và action để ứng dụng quyết định dựa vào tài nguyên thực. Nếu evaluator của bạn được viết đúng, nó có thể yêu cầu **cả** `document:edit`, membership tenant và owner/role phù hợp.

**Không nhầm:** `hasPermission(#id, 'Document', 'edit')` **không tự động** chuyển thành `hasAuthority('document:edit')`. Tên authority và tên action chỉ tương thích khi **chính bạn định nghĩa và thực thi quy tắc ánh xạ** trong evaluator.

## 3. Quy tắc đặt tên có thể mở rộng

### 3.1. Tên type: danh từ ổn định, không dùng nhãn giao diện

Chọn một tên canonical cho mỗi domain resource:

| Tên canonical | Ý nghĩa | Không nên dùng lẫn |
|---|---|---|
| `document` | Tài liệu | `doc`, `documents`, `file` nếu cùng một loại |
| `invoice` | Hóa đơn | `bill` nếu không phân biệt về domain |
| `purchase-order` | Đơn mua hàng | `po`, `purchaseOrder` |
| `report` | Báo cáo | `reports`, `export-file` |

Giá trị này nên **ổn định trong hệ thống cấp quyền**. Nếu đổi tên object Java từ `Document` sang `KnowledgeDocument`, không nhất thiết đổi authority `document:read` nếu domain resource vẫn là tài liệu. Ngược lại nếu domain tách loại đối tượng, hãy lập kế hoạch migration và versioning tên quyền.

**Đề xuất cho authority string:** lowercase ASCII, resource dạng kebab-case khi gồm nhiều từ, ký tự `:` phân tách resource và action, ví dụ `purchase-order:approve`. Hệ thống có thể dùng chuẩn khác, nhưng không trộn hai chuẩn vô tình. Spring Security so khớp authority **phân biệt chữ hoa/thường**.

### 3.2. Tên action: động từ rõ nghĩa, không dùng “write” quá chung

Một tập hành động có thể gồm:

| Action | Nghĩa | Câu hỏi nghiệp vụ |
|---|---|---|
| `read` | Xem nội dung | Người này có được đọc document không? |
| `list` | Xem danh sách/kết quả tìm kiếm | Có được liệt kê các document trong tenant này không? |
| `create` | Tạo bản ghi mới | Có được tạo document trong project/tenant này không? |
| `edit` | Sửa nội dung | Có được thay đổi title/body của document này không? |
| `delete` | Xóa hoặc chuyển trạng thái xóa | Có được xóa document này không? |
| `approve` | Phê duyệt | Có được duyệt invoice/đơn mua này không? |
| `publish` | Công bố | Có được công khai tài liệu đã được review không? |
| `export` | Xuất/tải dữ liệu | Có được xuất dữ liệu hàng loạt không? |
| `assign` | Giao quyền hoặc người phụ trách | Có được phân công tài nguyên cho người khác không? |

Không nên tự động cho `edit` hàm ý `delete` hay `approve`. Đó là hành động có mức rủi ro và quy trình khác nhau. Tên `write` có thể chấp nhận trong API đơn giản, nhưng ứng dụng nghiệp vụ thường cần phân tách `create`, `edit`, `delete`, `approve`.

**Phân biệt `list` và `read`:** quyền xem danh sách có thể khác quyền xem nội dung cụ thể. Một endpoint list phải áp dụng scope trong query và kiểm soát cả metadata/đếm tổng số; không thể dựa vào việc chỉ kiểm tra quyền từng phần tử sau khi đã truy vấn và phân trang.

### 3.3. Không đưa object ID, tenant ID vào tên quyền toàn cục khi không cần

Giữ authority tương đối ổn định:

```text
document:read
document:edit
document:delete
```

Rồi kiểm tra ngữ cảnh:

```text
Authentication.authorities = [
  "document:edit",
  "tenant:t1"
]

Document {
  id = 42
  tenant = "t1"
  owner = "alice"
}
```

Đây là **ví dụ thiết kế**: quyền `document:edit` và membership `tenant:t1` là hai thuộc tính phân biệt. Không nên xây hàng triệu authorities kiểu `document:42:edit` nếu có thể tra quyền theo DB/ACL; số lượng authority trong token/session sẽ phình ra, việc thu hồi quyền khó, khó giới hạn đúng phạm vi.

Đôi khi cần quyền được scope theo tenant như `tenant:t1:document:read`. Khi đó chuẩn này phải được **thiết kế và kiểm soát** rõ ràng, không dùng phép `startsWith("tenant:t1")` vì có thể vô tình khớp `tenant:t10`. Phân tách thành các trường có kiểu hoặc so khớp chính xác chuỗi sau canonicalization.

### 3.4. Tách role khỏi action

Role `ROLE_DOC_ADMIN` không phải action `document:approve`. Nếu role admin được phép duyệt hóa đơn, chính sách có thể ánh xạ role đó sang capability trong security config hoặc kiểm tra rõ nhánh role. Nhưng đừng giả định role nào cũng được phép trên mọi tenant; quyền admin toàn hệ thống và admin theo tenant là **hai mô hình khác nhau**.

Trong ví dụ chạy ở phần 6, vai trò `ROLE_DOC_ADMIN` chỉ cho phép các thao tác theo quy tắc **khi vẫn thuộc tenant của tài nguyên**. Đây là quyết định nghiệp vụ của mẫu; không phải mặc định của Spring Security.

## 4. PermissionEvaluator nhận tên quyền theo cách nào?

Interface `org.springframework.security.access.PermissionEvaluator` định nghĩa **hai overload**:

```java
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
```

Các chữ ký này là **trích yếu API**; muốn biên dịch phải đặt trong interface/class phù hợp và import `Authentication`, `Serializable`.

### 4.1. Dạng đối tượng: hasPermission(target, permission)

```java
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'read')")
public Document read(Long id) {
    return repository.findById(id).orElseThrow();
}
```

Ví dụ trên là **mẫu service**. Phương thức chạy trước, rồi `@PostAuthorize` kiểm tra đối tượng thực đã trả về. Evaluator nhận:
- `Authentication` hiện tại;
- `targetDomainObject` là `Document`;
- `permission` là chuỗi `"read"`.

Dạng này phù hợp với kết quả **đọc dữ liệu đáng tin từ server**. Vì hậu kiểm chạy sau method, tránh áp dụng `@PostAuthorize` như lớp bảo vệ duy nhất cho thao tác ghi hay tác dụng phụ không thể đảo ngược.

Với object do client gửi, **không được tin các trường owner/tenant trên object chưa được xác minh**. Evaluator nên tra lại bản ghi canonical từ repository bằng id hoặc bảo đảm input đã được lấy và xác minh ở tầng tin cậy. Phần code mẫu dưới đây cố ý tra bản ghi canonical.

### 4.2. Dạng ID + type + permission

```java
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
public Document edit(@P("id") Long id, String title) {
    return repository.rename(id, title);
}
```

Đây là **mẫu service**. Evaluator nhận:
- `targetId`: id của document, thường là `Long` hoặc kiểu `Serializable` phù hợp;
- `targetType`: chuỗi `"Document"`;
- `permission`: chuỗi `"edit"`.

**`'Document'` không tự động là Java class lookup.** API chỉ cung cấp chuỗi targetType; evaluator/ACL strategy tự quyết định chuỗi này là alias hay fully qualified class name. Trong một hệ thống tự xây, hãy công bố alias canonical và dùng nhất quán. Nếu tích hợp Spring Security ACL, kiểm tra quy tắc `ObjectIdentity`/permission mapping của ACL đang dùng thay vì giả định chung.

Dạng ID rất hữu ích cho **`@PreAuthorize` trên thao tác ghi**: phương thức chưa chạy mà evaluator đã có thể tra dữ liệu tin cậy và quyết định quyền. Tuy nhiên kiểm tra quyền trước rồi mới ghi vẫn có thể gặp race condition nếu record thay owner/tenant giữa hai bước; các thao tác nguy hiểm nên dùng transaction, lock/recheck hoặc câu SQL cập nhật có điều kiện.

### 4.3. Quy ước rõ ràng giữa hai cách gọi

Bài này chọn hai lớp tên khác nhau có chủ đích:

```text
GrantedAuthority: "document:edit"
targetType:       "Document"
permission:       "edit"
targetId:         42L
```

Evaluator ánh xạ:

```text
hasPermission(42L, "Document", "edit")
    ↓
nạp Document #42 từ storage tin cậy
    ↓
kiểm tra Membership trên tenant của Document #42
    ↓
kiểm tra authority "document:edit"
    ↓
kiểm tra owner hoặc ROLE_DOC_ADMIN
    ↓
true / false
```

Điểm lợi: permission action có thể giữ ngắn và cùng dạng trên các resource, trong khi tên authority vẫn phân biệt resource. Điểm rủi ro: nếu một nơi gọi `hasPermission(#id,'Document','document:edit')` nhưng evaluator chỉ hiểu `"edit"` thì sẽ bị deny. Chính sách **fail-closed** cho action lạ là đúng; sửa phía gọi, không mở rộng evaluator mù quáng.

### 4.4. Không mặc định có PermissionEvaluator nghiệp vụ

Spring Security cung cấp hook `hasPermission`, nhưng **không tự suy ra** owner, tenant, quyền trên DB hoặc các action `read`/`edit` do ứng dụng đặt tên. Với `@EnableMethodSecurity`, cần đăng ký và cấu hình evaluator thực sự; khi chưa cung cấp chính sách phù hợp, hệ thống không được tự cấp quyền object-level.

Nếu chỉ kiểm tra một capability toàn cục không cần object, `hasAuthority('document:read')` có thể đủ và đơn giản hơn. Khi xét owner/tenant/resource-state, `hasPermission` hoặc bean policy sẽ phù hợp hơn.

## 5. Chính sách tham chiếu: document:action cộng tenant và owner

Để ví dụ vừa đủ thực tế nhưng kiểm thử được, định nghĩa:

- Loại tài nguyên `Document` có `id`, `tenantId`, `owner`, `title`.
- Ba document: id 1 thuộc tenant `t1`/owner `alice`; id 2 thuộc `t1`/owner `bob`; id 3 thuộc `t2`/owner `carol`.
- Người gọi phải có authority `tenant:<tenantId>` **khớp chính xác** tenant của document.
- `read`: cần tenant membership và `document:read` **hoặc** `ROLE_DOC_ADMIN`.
- `edit`: cần tenant membership, authority `document:edit` và phải là **owner** hoặc có `ROLE_DOC_ADMIN`.
- `delete`: cần tenant membership, authority `document:delete` **và** `ROLE_DOC_ADMIN`.
- Action/type/id không được hỗ trợ hoặc đối tượng không tồn tại: **deny**.

| Action | Required authority | Ràng buộc bổ sung |
|---|---|---|
| `read` | `document:read` hoặc `ROLE_DOC_ADMIN` | Phải thuộc đúng tenant |
| `edit` | `document:edit` | Phải thuộc tenant và là owner hoặc `ROLE_DOC_ADMIN` |
| `delete` | `document:delete` | Phải thuộc tenant và có `ROLE_DOC_ADMIN` |

Đây là **policy mẫu**, không phải chính sách chuẩn của framework. Quyền đọc được cho phép trên mọi document trong cùng tenant nếu có `document:read`, kể cả owner khác; đó là chủ đích để phân biệt read permission với edit owner restriction.

Lưu ý bất biến quan trọng: ngay cả người có `ROLE_DOC_ADMIN` của tenant t1 **không** mặc nhiên vượt qua tenant t2 trong chính sách này. Role toàn hệ thống nếu có cần một chính sách khác được ghi rõ và test riêng.

## 6. Dự án Java 17 chạy được: Spring Boot 3.5.6 + Method Security

Demo là ứng dụng Spring Boot thuần không có HTTP server hay database. Storage trong RAM mô phỏng repository nhằm tập trung vào tên quyền và `PermissionEvaluator`. Kiểm thử dùng `@SpringBootTest` cùng `@WithMockUser` để đi qua proxy Method Security thực.

Cây dự án:

```text
permission-names-demo/
  pom.xml
  src/main/java/com/example/permissions/
    PermissionNamesApplication.java
    MethodSecurityConfig.java
    Document.java
    DocumentStore.java
    DocumentPermissionEvaluator.java
    DocumentService.java
  src/test/java/com/example/permissions/
    DocumentServiceTest.java
```

### 6.1. pom.xml

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
    <artifactId>permission-names-demo</artifactId>
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

Ví dụ chọn Boot 3.5.6 (quản lý Spring Security 6.5.x), không ép phiên bản Spring Security riêng lẻ. Với bản mới hơn hoặc dùng Gradle, kiểm tra dependency tree và tương thích API trước khi áp dụng.

### 6.2. Spring Boot application

**`src/main/java/com/example/permissions/PermissionNamesApplication.java`**

```java
package com.example.permissions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermissionNamesApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionNamesApplication.class, args);
    }
}
```

### 6.3. Bật Method Security và nối PermissionEvaluator vào expression handler

**`src/main/java/com/example/permissions/MethodSecurityConfig.java`**

```java
package com.example.permissions;

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

**Tại sao cần hai bước?**
- `@EnableMethodSecurity` bật interceptor thực thi `@PreAuthorize`/`@PostAuthorize` trên Spring-managed beans. Chỉ thêm dependency Security không tự bật method authorization.
- `setPermissionEvaluator(...)` cho phép hàm `hasPermission(...)` trong SpEL gọi implementation của bạn.
- `@Bean static` làm expression handler được công bố sớm trước khi hạ tầng Method Security được tạo, đúng mô hình được tài liệu chính thức Spring Security 6.5 đề xuất.

**Không được** tạo một `DefaultMethodSecurityExpressionHandler` mới cho mỗi request rồi mong các annotation đang được Spring quản lý tự thay handler; phải cấu hình ở hạ tầng. Nếu có custom handler hiện tại (role hierarchy, default role prefix...), kết hợp cấu hình trên **cùng handler**, tránh thay thế vô tình những thuộc tính đang dùng.

### 6.4. Domain record

**`src/main/java/com/example/permissions/Document.java`**

```java
package com.example.permissions;

public record Document(
        Long id,
        String tenantId,
        String owner,
        String title) {
}
```

Record Java 17 bảo đảm dữ liệu không bị chỉnh sửa tại chỗ; nếu đổi title, storage sẽ thay instance. Đối với evaluator, `Document` là **type Java thực** ở overload object, còn chuỗi `"Document"` là **alias do ứng dụng quy ước** ở overload id.

### 6.5. Storage tin cậy trong RAM

**`src/main/java/com/example/permissions/DocumentStore.java`**

```java
package com.example.permissions;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {
    private final Map<Long, Document> documents = new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    public synchronized void reset() {
        documents.clear();
        documents.put(1L, new Document(1L, "t1", "alice", "Alice notes"));
        documents.put(2L, new Document(2L, "t1", "bob", "Bob notes"));
        documents.put(3L, new Document(3L, "t2", "carol", "Carol notes"));
    }

    public Optional<Document> findById(Long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document rename(Long id, String title) {
        return documents.computeIfPresent(id,
            (key, previous) -> new Document(
                previous.id(),
                previous.tenantId(),
                previous.owner(),
                title
            )
        );
    }

    public boolean delete(Long id) {
        return documents.remove(id) != null;
    }
}
```

Đây là storage mô phỏng, không có transaction hoặc đồng bộ phân tán. Nó cho phép test deterministic dựa trên ba bản ghi đã biết. Trong hệ thống thật, dùng repository/SQL, tenant filter, lock hoặc query có điều kiện quyền; `ConcurrentHashMap` không đại diện cho transactional database.

### 6.6. PermissionEvaluator thực thi cách đặt tên

**`src/main/java/com/example/permissions/DocumentPermissionEvaluator.java`**

```java
package com.example.permissions;

import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {
    private static final String TYPE_DOCUMENT = "Document";
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

        // Không tin owner/tenant trong đối tượng do bên ngoài truyền vào.
        // Luôn kiểm tra lại Document thật dựa trên ID từ storage tin cậy.
        return hasPermission(
            authentication, document.id(), TYPE_DOCUMENT, permission
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

        // Fail-closed khi ID/type/action không đúng hợp đồng tên quyền.
        if (!(targetId instanceof Long id)
                || !TYPE_DOCUMENT.equals(targetType)
                || !(permission instanceof String action)) {
            return false;
        }

        Document document = store.findById(id).orElse(null);
        if (document == null) {
            return false;
        }

        // Mọi action đều bị giới hạn vào đúng tenant của tài nguyên.
        if (!hasAuthority(authentication, "tenant:" + document.tenantId())) {
            return false;
        }

        boolean admin = hasAuthority(authentication, "ROLE_DOC_ADMIN");
        return switch (action) {
            case "read" ->
                hasAuthority(authentication, "document:read") || admin;
            case "edit" ->
                hasAuthority(authentication, "document:edit")
                    && (document.owner().equals(authentication.getName())
                        || admin);
            case "delete" ->
                hasAuthority(authentication, "document:delete") && admin;
            default -> false;
        };
    }

    private static boolean hasAuthority(
            Authentication authentication, String required) {
        for (GrantedAuthority authority : authentication.getAuthorities()) {
            if (required.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

**Đọc logic theo thứ tự:** xác thực hợp lệ → đối số và target type hợp lệ → record tồn tại → đúng tenant → permission action đã biết → authority + điều kiện owner/admin. Mọi nhánh bất thường **trả false**. Spring Security sẽ từ chối khi `@PreAuthorize`/`@PostAuthorize` nhận `false`.

Nhiều chi tiết ở đây là lựa chọn thiết kế cần ghi rõ:
- `"Document"` (chữ D hoa) là **alias chính thức**; `"document"` không được chấp nhận bởi evaluator này.
- `permission = "read"` (chữ thường) là **action**, không phải `"document:read"`.
- `"document:read"` là tên `GrantedAuthority` phải khớp chính xác, không có quy tắc tự thêm prefix.
- `"tenant:t1"` chỉ được coi là đáng tin nếu authentication provider/converter đưa vào sau khi đã xác thực membership; **không** tin header tùy ý do client gửi.
- `ROLE_DOC_ADMIN` **không** bỏ qua tenant membership. Nó cho phép bypass owner ở nhánh `edit` nhưng không bỏ yêu cầu `document:edit`; nhánh `read` chấp nhận role admin thay cho `document:read`; nhánh `delete` đòi cả role admin và `document:delete`.
- Object overload tra lại `Document` từ storage thay vì tin owner/tenant của object đầu vào; điều này giúp tránh giả mạo các trường metadata trong đối tượng được truyền từ client.
- Dạng id không tự trả về 404: nó trả deny với record không tồn tại. Controller có thể chọn cách chuyển thành 403/404 theo chính sách không tiết lộ tồn tại tài nguyên.
- Ví dụ dùng exact case matching, không dùng `contains`, `startsWith` hay wildcard permission vô hạn.

### 6.7. Service với cả hai cú pháp hasPermission

**`src/main/java/com/example/permissions/DocumentService.java`**

```java
package com.example.permissions;

import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'read')")
    public Document readById(@P("id") Long id) {
        return store.findById(id)
            .orElseThrow(NoSuchElementException::new);
    }

    @PostAuthorize(
        "returnObject != null and hasPermission(returnObject, 'read')"
    )
    public Document readByObject(Long id) {
        return store.findById(id)
            .orElseThrow(NoSuchElementException::new);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'edit')")
    public Document rename(@P("id") Long id, String title) {
        Document updated = store.rename(id, title);
        if (updated == null) {
            throw new NoSuchElementException();
        }
        return updated;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'delete')")
    public boolean delete(@P("id") Long id) {
        return store.delete(id);
    }
}
```

`@P("id")` giúp bảo đảm biến `#id` trong SpEL nhận đúng tham số, kể cả khi chương trình không giữ metadata tên tham số lúc compile. Các method `rename` và `delete` dùng **tiền kiểm** để không thực thi thay đổi khi bị deny. `readByObject` dùng **hậu kiểm** chỉ cho thao tác đọc thuần, vì evaluator cần object được lấy từ storage.

**Không suy luận rằng `@PostAuthorize` là một dạng rollback.** Nếu `readByObject` thực hiện ghi, gửi email hoặc publish event trước khi return, những tác dụng phụ có thể đã xảy ra trước khi quyền bị từ chối.

## 7. Kiểm thử Spring Security: tên đúng, quyền đúng, tài nguyên đúng

Chỉ unit test một function trả true/false là chưa đủ: phải xác nhận annotation `@PreAuthorize` đi qua AOP proxy và gọi đúng evaluator. Dùng `@SpringBootTest` cùng `@WithMockUser` để tạo security context cho các test.

**`src/test/java/com/example/permissions/DocumentServiceTest.java`**

```java
package com.example.permissions;

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
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DocumentServiceTest {
    @Autowired
    DocumentService service;

    @Autowired
    DocumentStore store;

    @Autowired
    DocumentPermissionEvaluator evaluator;

    @BeforeEach
    void reset() {
        store.reset();
    }

    private Authentication currentAuthentication() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void readInOwnTenantIsAllowed() {
        assertEquals(1L, service.readById(1L).id());
        assertEquals(2L, service.readById(2L).id());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void crossTenantReadIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readById(3L)
        );
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"tenant:t1"})
    void missingReadAuthorityIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readById(1L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:edit"}
    )
    void ownerCanEdit() {
        Document updated = service.rename(1L, "New title");
        assertEquals("New title", updated.title());
        assertEquals("New title", store.findById(1L).orElseThrow().title());
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = {"tenant:t1", "document:edit"}
    )
    void nonOwnerCannotEdit() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.rename(1L, "Forbidden")
        );
        assertEquals("Alice notes", store.findById(1L).orElseThrow().title());
    }

    @Test
    @WithMockUser(
        username = "manager",
        authorities = {"tenant:t1", "document:edit", "ROLE_DOC_ADMIN"}
    )
    void adminCanEditSameTenant() {
        assertEquals("Managed", service.rename(1L, "Managed").title());
    }

    @Test
    @WithMockUser(
        username = "manager",
        authorities = {"tenant:t1", "document:edit", "ROLE_DOC_ADMIN"}
    )
    void adminCannotBypassTenantBoundary() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.rename(3L, "Cross tenant")
        );
    }

    @Test
    @WithMockUser(
        username = "manager",
        authorities = {"tenant:t1", "document:delete", "ROLE_DOC_ADMIN"}
    )
    void adminWithDeleteAuthorityMayDelete() {
        assertTrue(service.delete(2L));
        assertTrue(store.findById(2L).isEmpty());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:delete"}
    )
    void nonAdminCannotDelete() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.delete(1L)
        );
        assertTrue(store.findById(1L).isPresent());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void objectBasedPostAuthorizeAllowsTrustedDocument() {
        assertEquals(1L, service.readByObject(1L).id());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void objectBasedPostAuthorizeRejectsCrossTenantDocument() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readByObject(3L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void unknownIdIsDeniedBeforeRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readById(999L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void unknownActionIsFailClosed() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Document", "share"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void uppercaseActionDoesNotMatchCanonicalAction() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Document", "READ"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void inconsistentPermissionNameIsDenied() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Document", "document:read"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void unknownTargetTypeIsDenied() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Invoice", "read"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void forgedObjectTenantIsNotTrusted() {
        Document forged = new Document(
            3L, "t1", "alice", "Fake metadata"
        );
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), forged, "read"
        ));
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn test
```

**Kết quả kỳ vọng:** 17 test pass, 0 failures/errors. Đây là kết quả suy ra từ policy và fixture trong code; nhật ký Maven/JUnit có thể khác theo môi trường. Bài học **không tuyên bố đã thực thi Maven**.

Điểm đáng kiểm tra:
- `@WithMockUser(authorities = {...})` tạo đúng các tên authority chỉ định; không tự bổ sung `ROLE_` vào `document:read`.
- `@WithMockUser(roles = "DOC_ADMIN")` sẽ tạo authority `ROLE_DOC_ADMIN`, nhưng nếu cần kết hợp tenant và action cụ thể, dùng `authorities` ghi tường minh trong test.
- Test `forgedObjectTenantIsNotTrusted` chứng minh object giả mạo id 3 với tenant `t1` **vẫn không được phép**: evaluator tra lại bản ghi id 3 canonical thuộc tenant `t2`.
- Test `inconsistentPermissionNameIsDenied` chứng minh `"document:read"` **không** phải action `"read"` trong API evaluator này.
- Test `unknownIdIsDeniedBeforeRead` thể hiện failure mode của dạng ID khi record không tồn tại; không chạy vào service đích.
- Thay đổi state trong test `rename`/`delete` được reset trước mỗi test để tránh phụ thuộc thứ tự thực thi.

Trong hệ thống thật, các test tương tự cần chạy với database và role/tenant mappings thực; mock Authentication chỉ kiểm tra authorization, không thay thế test token validation hoặc đăng nhập end-to-end.

## 8. Naming cho create, list, export và quyền trên tập kết quả

### 8.1. CREATE: tài nguyên chưa tồn tại thì không có ID để tra

Khi tạo document trong tenant t1, thường **chưa có document id** và chưa có owner lưu trong DB. Do đó biểu thức sau là một mẫu nghiệp vụ hợp lý:

```java
@PreAuthorize(
    "hasAuthority('document:create') and " +
    "@tenantPolicy.canCreate(authentication, #tenantId)"
)
public Document create(
        @P("tenantId") String tenantId, String title) {
    // Tạo record sau khi kiểm tra được quyền trên tenant.
}
```

Đây là **mẫu tích hợp không độc lập**: cần bean `tenantPolicy`, imports, service và repository. Ý nghĩa: capability toàn cục `document:create` và quyền create trong tenant phải cùng thỏa. Không cho rằng `hasPermission(#newId,'Document','create')` sẽ hoạt động khi tài nguyên chưa tồn tại và evaluator hiện tại trả false cho ID lạ.

Tương tự, tạo invoice có thể bị giới hạn theo organization/project, hạn mức và workflow; policy cần đối tượng cha hoặc request scope đã được xác minh, không phải chỉ action string.

### 8.2. LIST và dữ liệu nhạy cảm trong aggregate

`document:list` có thể cho phép truy vấn các bản ghi thuộc tenant nhưng không có nghĩa tự được xem mọi nội dung. Khi viết query:

```sql
SELECT id, owner_id, title
FROM document
WHERE tenant_id = :authenticated_tenant_id
ORDER BY id
LIMIT :page_size;
```

Đây là **mẫu SQL** với tham số bind, không phải schema hoàn chỉnh. Tenant id phải đến từ security context đã kiểm chứng, không lấy vô điều kiện từ header hoặc query string. Số dòng, tổng count, facet và metadata đều có thể là dữ liệu nhạy cảm; cần cùng điều kiện phạm vi.

`@PostFilter("hasPermission(filterObject, 'read')")` lọc kết quả theo từng phần tử, nhưng nó xảy ra sau khi dữ liệu đã được tải và có thể gây N+1 queries, phân trang thiếu chính xác hoặc vấn đề collection bất biến. Với khối lượng lớn, đưa điều kiện quyền vào SQL/ACL query trước khi phân trang sẽ hiệu quả hơn.

### 8.3. EXPORT, APPROVE, DELETE nên có action riêng

`report:export` thường rủi ro hơn `report:read` vì dữ liệu được mang ra ngoài hệ thống. `invoice:approve` khác `invoice:edit` vì có thể yêu cầu separation of duties (người tạo không được tự phê duyệt). `document:delete` khác `document:edit` vì khả năng khôi phục và retention.

Đừng gom cả ba thành `write` khi nghiệp vụ cần audit chính xác. Với một hành động nhạy cảm, ngoài authority và owner/tenant còn có thể cần:
- Workflow state, ví dụ chỉ hóa đơn `PENDING` mới được `approve`.
- Kiểm tra người duyệt khác người tạo.
- Giới hạn amount và time window.
- Fully authenticated/MFA/step-up tùy mức rủi ro.
- Audit decision gồm user, resource type, resource id, action, outcome và policy version.

## 9. Kế hoạch lưu trữ permission và mapping role/authority

Một hệ thống quản trị quyền có thể lưu catalog quyền:

```text
permission_definition
  resource_type | action  | authority_name
  --------------+---------+-----------------------
  document      | read    | document:read
  document      | edit    | document:edit
  document      | delete  | document:delete
  invoice       | approve | invoice:approve
  report        | export  | report:export
```

Vai trò và quyền có quan hệ many-to-many:

```text
role
role_permission(role_id, permission_id)
user_role(user_id, role_id, scope_id)
resource_acl(resource_id, principal_id, action)
```

Đây chỉ là **sơ đồ khái niệm**, không phải DDL cụ thể. Có thể dùng database, IAM, OPA, Spring Security ACL hoặc policy bean tùy hạ tầng; đừng cho rằng `PermissionEvaluator` đòi đúng các bảng này.

Khi người dùng đăng nhập, authentication provider có thể tổng hợp role thành authorities, hoặc evaluator truy cập permission service tại thời điểm kiểm tra. Cần cân bằng:
- **JWT chứa sẵn authorities**: kiểm tra nhanh nhưng quyền có thể stale đến khi token hết hạn; cần chiến lược revoke/version.
- **DB lookup mỗi lần**: phản ánh quyền mới hơn nhưng có latency và rủi ro N+1 khi lọc tập; cần index/cache, invalidation và test fault handling.
- **ACL per-resource**: chính xác nhưng dữ liệu/bộ nhớ đệm lớn và khó quản lý nếu không chuẩn hóa resource identity.
- **Policy theo thuộc tính (ABAC)**: tenant, owner, trạng thái và thời gian có thể quan trọng hơn danh sách quyền tĩnh.

Trong mọi trường hợp, **nguồn authority phải đáng tin**. Không biến `X-Role: admin` hoặc `X-Permission: document:delete` do client tự gửi thành `GrantedAuthority` nếu không có xác thực và cấp quyền từ phía server.

## 10. Quy ước tên quyền như một hợp đồng API nội bộ

Một danh mục permission có thể được quản lý bằng constants hoặc enum ở Java:

```java
package com.example.permissions;

public final class PermissionNames {
    public static final String DOCUMENT_READ = "document:read";
    public static final String DOCUMENT_EDIT = "document:edit";
    public static final String DOCUMENT_DELETE = "document:delete";

    public static final String TARGET_DOCUMENT = "Document";
    public static final String ACTION_READ = "read";
    public static final String ACTION_EDIT = "edit";
    public static final String ACTION_DELETE = "delete";

    private PermissionNames() {
    }
}
```

**Đây là file Java tùy chọn** (không nằm trong cây demo chạy được ở trên vì code mẫu cố ý viết literal dễ đọc); có thể thêm vào project để tránh typo trong code Java. Lưu ý annotation `@PreAuthorize("...")` yêu cầu biểu thức ở dạng string literal hằng; bạn không thể đơn giản truyền biến runtime vào annotation. Nếu muốn tham chiếu constants trong SpEL, có thể dùng `T(com.example.permissions.PermissionNames).ACTION_EDIT` khi cấu hình SpEL cho phép, nhưng cách đó khiến annotation dài; một meta-annotation cố định hoặc bean policy có thể rõ ràng hơn.

**Versioning:** Thay `"document:edit"` bằng `"document:update"` có thể làm mất quyền của user/JWT đã cấp theo tên cũ. Khi đổi:
1. Công bố naming catalog mới và ràng buộc phân quyền.
2. Inventory mọi consumer: token converter, service annotation, UI permission hints, batch job, gateway, DB và integration test.
3. Di chuyển dữ liệu cấp quyền theo kế hoạch và kiểm soát cùng policy version.
4. Duy trì tương thích ngắn hạn nếu bắt buộc, nhưng không cấp rộng hơn vô ý; dọn quyền cũ sau cutover.
5. Test positive/negative, đặc biệt trường hợp token cũ và user thiếu quyền.

Trong logging/audit, ghi **tên action canonical** và resource type/id thay vì copy nguyên một chuỗi SpEL dài; điều này giúp phân tích sự kiện như “ai bị từ chối `invoice:approve` trên invoice 123” mà không gắn logic với chi tiết implementation.

## 11. Rủi ro: tên chuẩn không đủ nếu kiểm tra quyền sai

### 11.1. Không kiểm tra IDOR/BOLA

Một endpoint có `hasAuthority('document:read')` nhưng cho request đọc `/documents/42` mà không đối chiếu tenant/owner/ACL vẫn có thể bị **Broken Object Level Authorization (BOLA/IDOR)**. Quy ước resource:action chỉ là tên capability, không bảo vệ một instance cụ thể nếu không có điều kiện instance-level.

### 11.2. Không có quyền thì mặc định deny

Nếu một code mới gọi `hasPermission(#id,'Document','archive')` mà evaluator chưa hỗ trợ action `archive`, kết quả đúng nên là **false**. Không đặt default action sang `edit` hoặc `read`. Chỉ thêm action mới sau khi có policy rõ ràng, cấp quyền và test.

### 11.3. So khớp chuỗi không nhất quán

`Document`, `document`, `DOCUMENT` là ba chuỗi khác nhau trong evaluator demo. `read` không phải `READ`. Nếu hệ thống muốn cho phép alias hay normalize, hãy thực hiện ở điểm đầu vào tin cậy, kiểm tra chặt whitelist và test cả dữ liệu lỗi. Không dùng lowercasing vô tội vạ cho các định danh có phân biệt chữ hoa/thường.

### 11.4. SQL query bỏ qua tenant

Ngay cả khi evaluator kiểm tra tenant trước thao tác, giữa check và update có thể có race hoặc nhánh code khác bỏ qua evaluator. Với thao tác ghi quan trọng, xem xét SQL có điều kiện:

```sql
UPDATE document
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :authenticated_tenant_id
  AND owner_id = :authenticated_user_id;
```

Kiểm tra affected row count để phát hiện không có bản ghi phù hợp. Nếu cho admin sửa mọi document trong tenant, điều kiện owner cần được nới theo policy admin **đã xác minh**, không được bỏ luôn tenant restriction.

### 11.5. Nhầm role hierarchy với permission trên record

Một role hierarchy có thể cho `ROLE_ADMIN` bao hàm `document:read`, nhưng nó **không** chứng minh user được đọc tài liệu tenant khác. Role hierarchy giải quyết quan hệ giữa authorities; resource-level policy vẫn phải xét dữ liệu.

### 11.6. Self-invocation bỏ qua proxy

`@PreAuthorize` trong Spring thường chạy qua AOP proxy. Nếu method `service.outer()` gọi `this.rename(...)` trên cùng bean, interceptor có thể không được kích hoạt. Không tạo service bằng `new` khi muốn bảo vệ bằng annotation. Kiểm thử các entry point thật, tách service boundary và cân nhắc method security tại tầng API nghiệp vụ.

### 11.7. Không cân bằng policy cache và quyền bị thu hồi

Nếu evaluator cache kết quả `hasPermission` nhưng cache key thiếu tenant, action hoặc resource id, có thể trả quyền của request khác. Cache key tối thiểu phải phản ánh principal/role version, tenant, resource id, action và các yếu tố trạng thái quan trọng. Khi owner/ACL đổi, invalidation phải được thiết kế hoặc TTL ngắn phù hợp với rủi ro.

### 11.8. PostAuthorize và side effects

Vì `@PostAuthorize` chạy sau target, nó thích hợp hơn cho kiểm tra **kết quả đọc**. Nếu target tạo/sửa dữ liệu, gửi email hoặc gọi API bên ngoài trước khi quyền bị từ chối, việc ném `AccessDeniedException` không tự hoàn tác những tác động này. Với hành động ghi, ưu tiên `@PreAuthorize`/kiểm tra trong transaction và bảo vệ update bằng dữ liệu tin cậy.

### 11.9. Tenant membership có thể stale

Ví dụ demo dùng `tenant:t1` như authority trên Authentication. Trong hệ thống thực, membership có thể đổi sau khi JWT được ký hoặc session được tạo; cần revoke strategy, token lifetime, permission version hay DB lookup tùy độ nhạy cảm. Quyết định dựa trên member scope phải đi kèm chính sách làm mới quyền.

### 11.10. Không để UI là bộ kiểm tra quyền cuối cùng

Một SPA ẩn nút Delete dựa vào `document:delete` giúp UX, nhưng client có thể gọi API trực tiếp. Server phải thực thi cùng policy trên mọi điểm truy cập, kể cả batch job và message consumer.

## 12. Ma trận QA cần có cho mỗi permission mới

Khi thêm một action như `invoice:approve`, kiểm thử ít nhất:

| Đầu vào | Điều cần chứng minh |
|---|---|
| Đúng resource + action + authority + tenant | Allow nếu mọi điều kiện nghiệp vụ thỏa |
| Sai authority | Deny |
| Thiếu tenant membership | Deny |
| Đúng authority nhưng khác tenant | Deny |
| Đúng tenant nhưng không đúng owner/role | Deny nếu policy cần owner/role |
| ID không tồn tại | Deny hoặc xử lý not-found theo hợp đồng; không vô tình allow |
| targetType không được hỗ trợ | Deny |
| action không được hỗ trợ/viết sai hoa thường | Deny |
| Tham số object bị giả mạo owner/tenant | Deny dựa trên storage canonical |
| Quyền đã bị thu hồi | Deny sau khi cơ chế revoke/invalidation có hiệu lực |
| Nhiều role/authorities đồng thời | Không bị cấp rộng hơn policy |
| Gọi từ đường entry point khác | Không bypass AOP/authorization |
| Hệ thống phụ trợ lỗi/timeout | Không cấp quyền mặc định vì lỗi lookup |

Tài liệu một permission mới nên trả lời được năm câu: **tên canonical là gì, ai được cấp, áp dụng cho resource nào, điều kiện owner/tenant/state gì, và kiểm thử deny nào bảo vệ ranh giới?**

## 13. Checklist áp dụng

- [ ] Catalog các loại resource và action theo tên canonical nhất quán.
- [ ] Phân biệt rõ `GrantedAuthority("document:edit")`, `targetType="Document"` và `permission="edit"`.
- [ ] Role có prefix `ROLE_` không bị đồng nhất với action permission.
- [ ] Unknown type/action/id và dữ liệu null bị từ chối (fail-closed).
- [ ] `@EnableMethodSecurity` đã bật; evaluator đã được nối vào `MethodSecurityExpressionHandler`.
- [ ] `hasPermission(#id,'Document','edit')` được áp dụng **trước** side effect; object overload chỉ dùng với dữ liệu đáng tin hoặc reload canonical.
- [ ] Tenant/owner lấy từ tài nguyên và security context tin cậy, không từ trường request tùy ý.
- [ ] Quyền create/list/export/approve/delete được định nghĩa riêng theo mức rủi ro.
- [ ] Quyền trên danh sách lớn được lọc trong query khi cần hiệu năng/phân trang chính xác.
- [ ] Role mapping, JWT authority converter, DB ACL và annotation dùng cùng naming catalog.
- [ ] Integration test đi qua Spring-managed proxy và bao phủ allow/deny, record khác tenant, action lạ, sai case, object giả.
- [ ] Tên permission đổi có migration/versioning và không cấp rộng trong thời gian chuyển tiếp.

## 14. Tài liệu chính thức

- [Spring Security 6.5 — Method Security: Expressing Authorization with SpEL](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `hasPermission`, tham số method với `@P` và cấu hình `MethodSecurityExpressionHandler`.
- [Spring Security 6.5 — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html) — hai overload cho domain object hoặc (targetId, targetType, permission).
- [Spring Security 6.5 — SecurityExpressionOperations API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/SecurityExpressionOperations.html) — `hasPermission(Object,Object)` và `hasPermission(Object,String,Object)`.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html) — authorities, authentication, cách mô hình hóa ủy quyền.

**Ghi nhớ:** `resource:action` là **tên capability nhất quán**, còn `PermissionEvaluator` biến câu hỏi “có quyền `action` trên `resource instance` này không?” thành một quyết định dựa vào **dữ liệu tin cậy**. Tên rõ ràng giúp quản trị, audit và kiểm thử; quyền thực sự chỉ an toàn khi evaluator còn kiểm tra đúng **tenant, owner, record state và thời điểm thực thi**.