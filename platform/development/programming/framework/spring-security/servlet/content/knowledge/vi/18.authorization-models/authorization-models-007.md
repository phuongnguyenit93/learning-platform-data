# Tách chính sách phân quyền khỏi Controller và logic xử lý dữ liệu trong Spring Security Servlet

**Phạm vi:** Java 17+, Spring Boot 3.x / Spring Security 6.x trên Servlet stack. Bài thuộc chủ đề **Mô hình phân quyền**. Mục tiêu là thiết kế authorization có thể kiểm thử, dùng lại và thay đổi độc lập với HTTP Controller cũng như thao tác dữ liệu; tránh lỗi IDOR/BOLA, nhầm role với quyền trên một bản ghi, và tình trạng một đường vào ứng dụng quên kiểm tra quyền.

Một hệ thống thật thường có các câu hỏi: “Người dùng này có được xem tài liệu không?”, “Có được sửa tài liệu thuộc tenant khác không?”, “Manager được xem tất cả tài liệu cùng tenant nhưng có được sửa thay chủ sở hữu không?”. Đây là **quy tắc nghiệp vụ về quyền**, không phải chi tiết định tuyến HTTP và cũng không phải chỉ là câu lệnh SELECT/UPDATE.

## 1. Vì sao không nên nhét điều kiện phân quyền vào Controller?

Giả sử một controller viết:

~~~java
@GetMapping("/documents/{id}")
public DocumentDto get(@PathVariable long id, Authentication auth) {
    Document doc = repository.findById(id).orElseThrow();
    if (!doc.ownerUsername().equals(auth.getName())) {
        throw new AccessDeniedException("Not allowed");
    }
    return toDto(doc);
}
~~~

Đoạn trên là **minh họa vấn đề**, chưa phải chương trình độc lập. Nó có thể chặn một đường GET, nhưng ngay khi xuất hiện đường xuất PDF, truy cập GraphQL, batch export hoặc service call từ một job, cùng rule rất dễ bị quên hoặc sao chép sai.

Những hệ quả thường gặp:
- Quy tắc quyền bị phân tán giữa nhiều controller, endpoint và handler.
- Một controller được sửa, controller khác vẫn giữ logic cũ.
- Dữ liệu được đọc trước khi kiểm tra quyền và có thể bị log/serialize vô tình.
- Quyền chủ sở hữu bị kiểm tra bằng tham số người dùng tự gửi thay vì identity do server xác thực.
- Business service có thể bị gọi từ nơi khác mà không qua Controller đang kiểm tra quyền.
- Unit test nghiệp vụ phải dựng HTTP request mới kiểm tra được policy.
- Quyền theo tenant, trạng thái tài liệu, nhóm người dùng hay permission mới khiến if/else phình to.

**Mục tiêu không phải xóa mọi điều kiện bảo mật khỏi Controller**, mà là phân công: Controller tiếp nhận HTTP và chuyển đổi dữ liệu; tầng authorization định nghĩa và đánh giá policy; service là nơi bảo đảm các use case chỉ chạy khi được phép; repository chịu trách nhiệm truy cập dữ liệu có phạm vi thích hợp.

## 2. Phân biệt authentication, authorization, policy và enforcement

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang gọi? | Spring Security xác minh alice từ HTTP Basic/session/JWT |
| Identity/principal | Định danh đáng tin của người gọi | <code>Authentication.getName()</code> |
| GrantedAuthority | Quyền/role tổng quát đã được cấp | <code>ROLE_USER</code>, <code>ROLE_MANAGER</code> |
| Authorization policy | Ai được làm gì trên tài nguyên nào, trong ngữ cảnh nào? | Owner được sửa tài liệu; manager chỉ được đọc tài liệu cùng tenant |
| Policy enforcement | Nơi bắt buộc áp dụng kết quả policy | <code>@PreAuthorize</code> trên public service method |
| Data scope | Truy vấn chỉ chạm đến dữ liệu có phạm vi được phép | <code>WHERE tenant_id = :tenantId</code> và owner/status khi cần |
| Audit | Ai đã thử làm gì, quyết định ra sao? | Document 42: read allowed / edit denied |

Trong thuật ngữ kiến trúc, **Policy Decision Point (PDP)** đánh giá cho phép/từ chối; **Policy Enforcement Point (PEP)** từ chối thực thi khi kết quả là deny; **Policy Information Point (PIP)** cấp các thuộc tính như owner, tenant, trạng thái, permission. Chúng có thể là các class trong cùng ứng dụng; không bắt buộc phải có một server policy độc lập.

~~~text
Client
   |
   v
SecurityFilterChain: xác thực và chặn thô theo HTTP
   |
   v
Controller: parse path/body, trả response/DTO
   |
   v
DocumentService: bắt buộc authorization trước use case
   |            |
   |            +--> DocumentPolicy: allow/deny
   |                         |
   |                         +--> TenantDirectory (server trusted)
   |                         +--> DocumentStore (owner, tenant)
   v
Repository / Store: truy vấn và cập nhật đúng phạm vi
   |
   v
Response DTO: chỉ gồm trường được phép trả
~~~

Phần policy quyết định **được phép không**; phần dữ liệu quyết định **lấy và thay đổi bản ghi nào**. Hai phần cần phối hợp, nhưng không được nhập làm một khối controller tùy tiện.

## 3. Một ma trận chính sách rõ ràng trước khi viết code

Bài thực hành quản lý các document có <code>id</code>, <code>tenantId</code>, <code>ownerUsername</code>, <code>title</code> và <code>content</code>. User có tenant do server quản lý:

| User | Tenant | Authorities |
| --- | --- | --- |
| alice | tenant-a | ROLE_USER |
| bob | tenant-a | ROLE_USER |
| carol | tenant-b | ROLE_USER |
| mia | tenant-a | ROLE_USER, ROLE_MANAGER |

Dữ liệu minh họa:

| Document | Owner | Tenant |
| --- | --- | --- |
| 1 | alice | tenant-a |
| 2 | bob | tenant-a |
| 3 | carol | tenant-b |

Chính sách mong muốn:
1. Chưa đăng nhập: không được đọc hoặc sửa document.
2. User cùng tenant **và là owner**: được đọc và sửa tài liệu của mình.
3. Manager của cùng tenant: được **đọc** tài liệu của các owner khác trong tenant.
4. Manager **không tự nhiên được sửa** tài liệu người khác; chức năng sửa dành cho owner.
5. Mọi trường hợp khác, đặc biệt tenant khác: từ chối.
6. Document ID không tồn tại: từ chối ở policy trong demo để không tạo oracle phân biệt “có tài liệu nhưng không có quyền” và “không có tài liệu”.
7. Client không được tự đặt tenantId hoặc ownerUsername khi sửa content.

Ma trận kết quả dự kiến:

| Ai gọi | GET doc 1 | GET doc 2 | GET doc 3 | PUT doc 1 |
| --- | --- | --- | --- | --- |
| alice | Allow | Deny | Deny | Allow |
| bob | Deny | Allow | Deny | Deny |
| carol | Deny | Deny | Allow | Deny |
| mia (manager tenant-a) | Allow | Allow | Deny | Deny |
| Anonymous | Deny | Deny | Deny | Deny |

Một role như <code>ROLE_MANAGER</code> **không phải** quyền đọc mọi tenant. Tenant là ranh giới độc lập; quyền chỉ được cấp khi cả tenant scope và điều kiện business đều đạt. Đây là mô hình **RBAC kết hợp ownership/attribute-based authorization**.

## 4. Tách trách nhiệm theo tầng

**SecurityFilterChain:** thực hiện authentication, CSRF, và điều kiện thô như “chỉ người đã đăng nhập mới được vào <code>/documents/**</code>”. Không cần đưa mọi trường hợp owner/tenant vào danh sách URL matcher.

**Controller:** nhận <code>id</code> từ đường dẫn, đọc body, gọi service, trả DTO/status. Không tự hỏi <code>if (auth.getName().equals(owner))</code> tại từng endpoint.

**Policy:** một class có tên và contract rõ ràng, ví dụ <code>DocumentPolicy.canRead(auth, doc)</code> và <code>canEdit(auth, doc)</code>. Policy hiểu quyền, tenant, owner; không render JSON, không cập nhật dữ liệu.

**Service/use case:** điểm vào bắt buộc policy trước thao tác quan trọng; có thể dùng <code>@PreAuthorize</code>, <code>AuthorizationManager</code> hoặc gọi policy tường minh. Không dựa vào sự tồn tại của HTTP Controller để bảo vệ business operation.

**Repository:** truy vấn có điều kiện theo tenant/owner, giao dịch và khóa phù hợp khi dữ liệu thay đổi đồng thời. Policy check trước thao tác và điều kiện dữ liệu trong SQL bổ sung nhau; một SELECT trước UPDATE không đủ chống TOCTOU.

**DTO/serialization:** lọc những trường được gửi ra. Đã có quyền xem tài liệu không đồng nghĩa được nhận mọi trường nội bộ như password hash, thông tin khách hàng hay audit secrets.

## 5. Nên dùng @PreAuthorize hay kiểm tra trong service?

Spring Security hỗ trợ **method security**:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecuritySetup { }
~~~

Với class được Spring quản lý và public method gọi **qua Spring proxy**, <code>@PreAuthorize</code> đánh giá biểu thức trước khi phương thức chạy:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public DocumentView read(@P("docId") Long docId) {
    // Logic lấy dữ liệu chỉ chạy sau khi policy cho phép.
}
~~~

Trong đoạn này:
- <code>authentication</code> đến từ Spring Security context, không phải chuỗi do client đưa vào.
- <code>@documentPolicy</code> tham chiếu bean chính sách.
- <code>#docId</code> là tham số phương thức, được đánh dấu <code>@P("docId")</code> để SpEL không phụ thuộc tên tham số bị mất khi biên dịch.
- Nếu policy trả false, method-security interceptor ném <code>AccessDeniedException</code>; HTTP stack sẽ xử lý status theo authentication/entry point.
- Code trong method chỉ chạy khi đã được cho phép. Annotation không tự bảo vệ các thao tác repository khác được gọi trực tiếp từ chỗ khác.

**Đặt annotation trên service** giúp enforcement được tái sử dụng khi service được gọi từ HTTP, messaging adapter hoặc một bean khác. Điều này không tự bảo vệ lời gọi nội bộ <code>this.read(...)</code> trong cùng đối tượng do proxy interception có thể bị bỏ qua; phải kiểm thử entry points và kiến trúc gọi bean.

Một cách khác là service trực tiếp gọi policy và ném <code>AccessDeniedException</code>. Cách đó phù hợp khi cần kiểm tra quyền trên một aggregate đã được load hoặc trong cùng transaction. Bài demo dùng <code>@PreAuthorize</code> để minh họa một enforcement point dễ quan sát.

## 6. Dự án hoàn chỉnh: HTTP Basic + method security + DocumentPolicy

Ví dụ sử dụng **Java 17, Spring Boot 3.3.5, Spring Security 6.x và Maven**, chạy trong một tiến trình. Repository và ánh xạ tenant ở bộ nhớ chỉ để thực hành; không phải mẫu persistence production. Mật khẩu cứng dưới đây chỉ dùng ở localhost.

Cấu trúc:

~~~text
document-policy-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/documentpolicy/
    │   ├── DocumentPolicyApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── Document.java
    │   ├── DocumentView.java
    │   ├── DocumentStore.java
    │   ├── TenantDirectory.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/com/example/documentpolicy/
        └── DocumentAuthorizationTest.java
~~~

### 6.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>document-policy-demo</artifactId>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Application class

Tạo <code>src/main/java/com/example/documentpolicy/DocumentPolicyApplication.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DocumentPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(DocumentPolicyApplication.class, args);
    }
}
~~~

### 6.3. Domain record và DTO đầu ra

Tạo <code>src/main/java/com/example/documentpolicy/Document.java</code>:

~~~java
package com.example.documentpolicy;

public record Document(
        Long id,
        String tenantId,
        String ownerUsername,
        String title,
        String content) {
}
~~~

Record <code>Document</code> chứa owner và tenant là **thuộc tính để policy đánh giá**. Những thuộc tính đó phải đến từ nguồn dữ liệu do server quản lý, không được tin từ <code>X-Tenant</code> tự khai.

Tạo <code>src/main/java/com/example/documentpolicy/DocumentView.java</code>:

~~~java
package com.example.documentpolicy;

public record DocumentView(Long id, String title, String content) {
    public static DocumentView from(Document doc) {
        return new DocumentView(doc.id(), doc.title(), doc.content());
    }
}
~~~

DTO này cố ý không lộ <code>tenantId</code> và <code>ownerUsername</code>. Khi sản phẩm cần hiển thị owner hoặc tenant, phải xác định trường nào thật sự cần và được phép trả; DTO là lớp kiểm soát dữ liệu gửi ra, không thay thế authorization ở service.

### 6.4. Repository demo: tách CRUD khỏi quyết định quyền

Tạo <code>src/main/java/com/example/documentpolicy/DocumentStore.java</code>:

~~~java
package com.example.documentpolicy;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {

    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>();

    public DocumentStore() {
        documents.put(1L,
            new Document(1L, "tenant-a", "alice",
                "Alice report", "initial-a"));
        documents.put(2L,
            new Document(2L, "tenant-a", "bob",
                "Bob report", "initial-b"));
        documents.put(3L,
            new Document(3L, "tenant-b", "carol",
                "Carol report", "initial-c"));
    }

    public Optional<Document> find(Long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document updateContent(Long id, String newContent) {
        return documents.computeIfPresent(id, (key, old) ->
            new Document(old.id(), old.tenantId(),
                old.ownerUsername(), old.title(), newContent));
    }
}
~~~

Repository chỉ biết lưu và tìm document; **không quyết định ai được phép đọc**. Trong demo, <code>tenantId</code> và <code>ownerUsername</code> là immutable attributes khi cập nhật content: method update không chấp nhận owner/tenant từ request. Ở database thật, policy enforcement và UPDATE phải cùng thỏa ràng buộc tenant/owner trong transaction hoặc điều kiện SQL nhằm tránh race condition.

### 6.5. Nguồn tenant đáng tin ở server

Tạo <code>src/main/java/com/example/documentpolicy/TenantDirectory.java</code>:

~~~java
package com.example.documentpolicy;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {

    private final Map<String, String> memberships = Map.of(
        "alice", "tenant-a",
        "bob", "tenant-a",
        "carol", "tenant-b",
        "mia", "tenant-a"
    );

    public String tenantOf(String username) {
        return memberships.get(username);
    }
}
~~~

Đây là fixture để demo. Trong production, tenant context phải đến từ membership đã được server/IdP xác minh hoặc database, có kiểm soát với account đa tenant. Header <code>X-Tenant</code> hoặc query parameter <code>tenantId</code> chỉ được xem là yêu cầu chọn tenant, **không** là bằng chứng user có quyền trong tenant ấy.

Với người thuộc nhiều tenant, policy còn phải kiểm tra membership với tenant đích/tenant đang chọn và quyền tương ứng, thay vì suy từ một mapping cố định như demo.

### 6.6. DocumentPolicy: nơi tập trung quy tắc allow/deny

Tạo <code>src/main/java/com/example/documentpolicy/DocumentPolicy.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentStore store;
    private final TenantDirectory tenants;

    public DocumentPolicy(DocumentStore store, TenantDirectory tenants) {
        this.store = store;
        this.tenants = tenants;
    }

    public boolean canRead(Authentication auth, Long id) {
        return store.find(id)
            .map(doc -> canReadDocument(auth, doc))
            .orElse(false);
    }

    public boolean canEdit(Authentication auth, Long id) {
        return store.find(id)
            .map(doc -> canEditDocument(auth, doc))
            .orElse(false);
    }

    boolean canReadDocument(Authentication auth, Document doc) {
        if (!sameTenant(auth, doc)) {
            return false;
        }
        return doc.ownerUsername().equals(auth.getName())
            || hasAuthority(auth, "ROLE_MANAGER");
    }

    boolean canEditDocument(Authentication auth, Document doc) {
        return sameTenant(auth, doc)
            && doc.ownerUsername().equals(auth.getName());
    }

    private boolean sameTenant(Authentication auth, Document doc) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        String trustedTenant = tenants.tenantOf(auth.getName());
        return trustedTenant != null
            && trustedTenant.equals(doc.tenantId());
    }

    private boolean hasAuthority(Authentication auth, String authority) {
        for (GrantedAuthority granted : auth.getAuthorities()) {
            if (authority.equals(granted.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
~~~

Tại sao class này là **policy**:
- Nó trả quyết định boolean, không gọi <code>HttpServletResponse</code>, không build JSON, không redirect.
- Nó không tự cập nhật document; check quyền là hành vi tách biệt.
- Nó dùng principal/authorities **đã xác thực từ server**, tenant từ directory **đáng tin**, owner/tenant từ document **được server lưu**.
- Nếu không tìm thấy document hay thiếu membership, mặc định false (**deny by default**).
- Manager chỉ được đọc khi cùng tenant; chữ MANAGER không đồng nghĩa toàn quyền hệ thống.
- Có thể test trực tiếp canRead/canEdit mà không chạy HTTP.

<code>Authentication.isAuthenticated()</code> một mình chưa đủ để phân biệt anonymous token trong mọi thiết kế Spring Security. Trong demo, anonymous không có membership trong directory nên <code>sameTenant</code> trả false; ngoài ra SecurityFilterChain đã yêu cầu authenticated cho document routes. Ở hệ thống tổng quát, nên dùng cách đánh giá authentication trust phù hợp (ví dụ trust resolver) và bảo đảm identity/tenant không thể do untrusted caller giả mạo.

Một chính sách tinh vi hơn còn có thể xét trạng thái document, classification, delegation, thời gian, nguồn request hoặc action. Giữ những điều kiện này trong policy nhất quán, không sao chép vào mỗi controller.

### 6.7. DocumentService: enforcement point cho use case

Tạo <code>src/main/java/com/example/documentpolicy/DocumentService.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
    public DocumentView read(@P("docId") Long docId) {
        Document doc = store.find(docId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
        return DocumentView.from(doc);
    }

    @PreAuthorize("@documentPolicy.canEdit(authentication, #docId)")
    public DocumentView replaceContent(
            @P("docId") Long docId, String newContent) {

        if (newContent == null || newContent.isBlank()
                || newContent.length() > 1_000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid content");
        }

        Document updated = store.updateContent(docId, newContent);
        if (updated == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        return DocumentView.from(updated);
    }
}
~~~

Service **không chứa câu điều kiện owner/manager/tenant**. Nó chỉ khai báo *policy nào phải được thỏa* để thực hiện use case, sau đó xử lý dữ liệu và trả DTO.

- <code>@PreAuthorize</code> là enforcement **trước khi chạy** read/replaceContent.
- <code>@P("docId")</code> cung cấp tên tham số cho biểu thức Spring Security SpEL.
- <code>DocumentStore</code> vẫn có phương thức cập nhật không biết user là ai, nên hệ thống cần quy định mọi entry point nghiệp vụ phải qua service được bảo vệ. Không inject store trực tiếp vào một controller mới để bypass service.
- Dữ liệu content được kiểm tra ở service; controller không quyết định policy.
- Ở demo, owner/tenant không đổi khi update nên việc policy đọc document rồi service cập nhật không có race trên những thuộc tính quyết định quyền. **Production với mutable ownership/tenant, database/transaction hoặc nhiều node phải chống race ở nguồn dữ liệu** như phần sau.

<code>@PreAuthorize</code> là proxy-based method security: cuộc gọi qua Spring bean proxy được intercept; gọi <code>this.replaceContent()</code> nội bộ trong chính instance có thể bypass proxy. Method mới, scheduled jobs, batch/message consumers và dịch vụ khác cần đi qua enforced service API hoặc có authorization check tương đương.

### 6.8. DocumentController: mỏng, không chứa rule owner/tenant

Tạo <code>src/main/java/com/example/documentpolicy/DocumentController.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    public record UpdateBody(String content) { }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/documents/{id}")
    public DocumentView read(@PathVariable Long id) {
        return service.read(id);
    }

    @PutMapping("/documents/{id}")
    public DocumentView update(
            @PathVariable Long id, @RequestBody UpdateBody body) {
        return service.replaceContent(id, body.content());
    }
}
~~~

Controller chỉ map HTTP GET/PUT, đọc path/body và chuyển sang service. Nó không nhận <code>ownerUsername</code> hay <code>tenantId</code> từ body để quyết định quyền. Việc PUT được chặn bởi service policy (và CSRF ở HTTP layer trong cấu hình demo).

### 6.9. SecurityConfiguration: coarse-grained HTTP và method security

Tạo <code>src/main/java/com/example/documentpolicy/SecurityConfiguration.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass-123"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass-123"))
                .roles("USER").build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-pass-123"))
                .roles("USER").build(),
            User.withUsername("mia")
                .password(encoder.encode("mia-pass-123"))
                .roles("USER", "MANAGER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers("/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

<code>@EnableMethodSecurity</code> rất quan trọng: nếu thiếu annotation này, các <code>@PreAuthorize</code> trong demo có thể không được kích hoạt. HTTP check <code>authenticated()</code> chỉ có nghĩa “đã đăng nhập”; nó **không** đủ để kiểm tra owner/tenant. Tầng service mới thực hiện chính sách theo tài nguyên.

CSRF vẫn được giữ mặc định. Với HTTP Basic chạy trong browser, browser có thể tự gửi lại Authorization header sau khi đã cache credentials, nên không nên mặc định kết luận Basic hoàn toàn miễn rủi ro CSRF. Trong bài, các PUT test sẽ gửi CSRF token bằng Spring Security test helper. Không tắt CSRF toàn ứng dụng chỉ để curl PUT thuận tiện hơn.

URL không biết được dùng <code>anyRequest().denyAll()</code>. Nếu sau này thêm <code>/documents/export</code>, phải xác định đúng use case và enforcement; không được tự cho rằng authenticated là đủ.

## 7. Test bằng MockMvc: policy không nằm trong Controller

Tạo <code>src/test/java/com/example/documentpolicy/DocumentAuthorizationTest.java</code>:

~~~java
package com.example.documentpolicy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAndAuthenticationBoundary() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        mvc.perform(get("/documents/1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownershipTenantAndManagerPolicy() throws Exception {
        // Owner của document 1 được đọc.
        mvc.perform(get("/documents/1")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.content").value("initial-a"));

        // Cùng tenant nhưng không phải owner, không có manager role.
        mvc.perform(get("/documents/2")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isForbidden());

        // Khác tenant vẫn bị từ chối.
        mvc.perform(get("/documents/3")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isForbidden());

        // Manager chỉ được xem tài liệu cùng tenant.
        mvc.perform(get("/documents/1")
                .with(httpBasic("mia", "mia-pass-123")))
            .andExpect(status().isOk());

        mvc.perform(get("/documents/2")
                .with(httpBasic("mia", "mia-pass-123")))
            .andExpect(status().isOk());

        mvc.perform(get("/documents/3")
                .with(httpBasic("mia", "mia-pass-123")))
            .andExpect(status().isForbidden());

        // Document không tồn tại: policy trả false.
        mvc.perform(get("/documents/999")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void modificationEnforcesOwnerAndCsrf() throws Exception {
        // Thiếu CSRF: PUT bị chặn trước business service.
        mvc.perform(put("/documents/1")
                .with(httpBasic("alice", "alice-pass-123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"changed\"}"))
            .andExpect(status().isForbidden());

        // Đúng owner + CSRF hợp lệ.
        mvc.perform(put("/documents/1")
                .with(httpBasic("alice", "alice-pass-123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"changed-by-alice\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content").value("changed-by-alice"));

        // Cùng tenant nhưng tài liệu thuộc Bob.
        mvc.perform(put("/documents/2")
                .with(httpBasic("alice", "alice-pass-123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"forbidden\"}"))
            .andExpect(status().isForbidden());

        // Manager đọc được nhưng không được sửa thay owner.
        mvc.perform(put("/documents/1")
                .with(httpBasic("mia", "mia-pass-123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"forbidden\"}"))
            .andExpect(status().isForbidden());

        // Document của owner vẫn chứa nội dung họ đã cập nhật.
        mvc.perform(get("/documents/1")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content").value("changed-by-alice"));
    }
}
~~~

Các test kiểm tra invariant, không chỉ happy path:
- Anonymous được đọc /health, không được đọc /documents/1 (401 với HTTP Basic).
- Alice được đọc document 1 nhưng không được đọc document 2 của Bob dù cùng tenant (403).
- Alice không được đọc document 3 thuộc tenant khác.
- Manager Mia được đọc doc 1/2 của tenant-a nhưng không được đọc doc 3 của tenant-b.
- Đúng owner nhưng PUT thiếu CSRF vẫn bị 403.
- Owner có quyền và CSRF được sửa content; Alice không sửa được của Bob.
- Manager không tự có quyền sửa document của owner khác.
- Với ID không tồn tại, demo policy từ chối, không phân biệt existence qua GET unauthorized.

<code>@DirtiesContext</code> cô lập in-memory DocumentStore giữa các test. Bộ test qua HTTP filters và method security thực, thay vì chỉ tạo mock principal rồi gọi controller trực tiếp. Trong production cần thêm unit test của policy với nhiều trường hợp role/tenant, test repository và tích hợp database.

**Lưu ý:** ví dụ được trình bày theo API Java/Spring Security 6.x và được soát logic/cú pháp tĩnh, không phải tuyên bố rằng Maven test đã được chạy trong bài này. Hãy chạy trên JDK 17+ để xác thực dependency/runtime thực tế.

## 8. Thử bằng HTTP và giải thích status

Khởi động:

~~~bash
mvn test
mvn spring-boot:run
~~~

Ví dụ các lệnh GET:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/documents/1
curl -i -u alice:alice-pass-123 http://localhost:8080/documents/1
curl -i -u alice:alice-pass-123 http://localhost:8080/documents/2
curl -i -u mia:mia-pass-123 http://localhost:8080/documents/1
curl -i -u mia:mia-pass-123 http://localhost:8080/documents/3
~~~

Kết quả **dự kiến**: /health = 200; anonymous GET document = 401; Alice GET doc1 = 200; Alice GET doc2 = 403; Mia GET doc1 = 200; Mia GET doc3 = 403. Body thành công là JSON từ <code>DocumentView</code>, chỉ gồm <code>id</code>, <code>title</code> và <code>content</code>.

Với PUT trong demo, Spring Security yêu cầu CSRF token. Nếu gọi curl PUT chỉ với HTTP Basic và body JSON nhưng không có CSRF token, nhận 403 là điều được mong đợi theo cấu hình — **không** phải bằng chứng chủ sở hữu không có quyền. Dùng MockMvc <code>.with(csrf())</code> hoặc triển khai client lấy và gửi CSRF token phù hợp. Không tắt CSRF toàn app để “chữa lỗi” mà chưa có threat model.

### 401, 403 và 404

- **401:** chưa được xác thực đúng (HTTP Basic entrypoint trong demo).
- **403:** đã xác thực nhưng policy không cho phép, hoặc request thiếu CSRF token.
- **404:** tài nguyên không tồn tại trong các API có chủ đích được phép tiết lộ kết quả này.

Demo chọn **fail closed với 403** khi id không tồn tại trong policy. Sản phẩm thật có thể chọn trả 404 cho cả “không tồn tại” và “không được xem” nhằm giảm khả năng dò tài nguyên; lựa chọn phải thống nhất, không vô tình lộ existence qua timing/response differences. Không để exception từ repository biến trường hợp forbidden thành 500.

## 9. Tại sao controller-level @PreAuthorize chưa đủ?

Gắn <code>@PreAuthorize</code> tại Controller vẫn có tác dụng khi Spring method security chạy. Tuy nhiên, nếu chỉ bảo vệ endpoint REST mà business service không được bảo vệ, một consumer Kafka, GraphQL resolver, scheduled job, internal RPC hoặc một controller thứ hai có thể gọi service và bỏ qua check.

Mẫu tốt:
- HTTP layer chặn anonymous và các route không thuộc phạm vi.
- Service/use case có enforcement theo action/resource.
- Policy là đơn vị dùng lại cho các entry point.
- Repository/transaction buộc truy vấn và update tuân thủ scope của dữ liệu.

Không nhất thiết mọi repository đều phải dùng <code>@PreAuthorize</code>. Repository có thể là tầng dữ liệu thuần, còn service bảo đảm không có public data access path bỏ qua policy. Trong tổ chức lớn, kiểm soát architecture bằng code review/architecture tests để ngăn Controller hoặc API adapter inject repository trực tiếp rồi vượt qua service.

## 10. Cẩn thận self-invocation và Spring proxy

Spring method security thường chạy qua Spring AOP proxy. Xét:

~~~java
@Service
class BadDocumentService {
    public void bulkUpdate() {
        this.updateOne(); // Gọi nội bộ cùng instance.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void updateOne() {
        // Method có annotation nhưng cuộc gọi this. có thể bypass proxy!
    }
}
~~~

Đây là trích đoạn minh họa **không phải class độc lập chạy được**. Nếu chỉ test <code>proxy.updateOne()</code>, bạn có thể bỏ sót việc <code>this.updateOne()</code> không đi qua interceptor. Giải pháp kiến trúc: tách method được bảo vệ sang một Spring bean riêng và gọi qua proxy, hoặc bắt buộc explicit policy check ở tầng use case trước mọi luồng nội bộ.

Một số tình huống khác cũng cần review: bean không được Spring quản lý, method không public, cấu hình proxy/final class, custom object construction bằng <code>new</code>, hoặc gọi trực tiếp repository. Không dùng một annotation ở controller làm bằng chứng mọi đường vào dữ liệu đã được bảo vệ.

## 11. TOCTOU: policy check trước SELECT/UPDATE chưa luôn đủ

Bài demo dùng DocumentStore in-memory với owner/tenant không thay đổi trong update content. Trong database thật, owner, tenant, document state hoặc membership có thể thay đổi **giữa lúc kiểm tra và lúc update**:

~~~text
t1: Policy đọc doc 42: owner = alice
t2: Alice được allow sửa doc 42
t3: Một transaction khác chuyển owner/tenant của doc 42
t4: UPDATE doc 42 không ràng buộc owner/tenant -> sửa nhầm
~~~

Đây là lỗi *time-of-check to time-of-use* (TOCTOU). Các cách bảo vệ:
1. Đọc và thay đổi dưới một transaction có isolation/lock thích hợp, revalidate policy khi ghi.
2. Optimistic locking bằng <code>@Version</code> khi resource thay đổi.
3. Một câu UPDATE có điều kiện owner/tenant/status phù hợp, lấy tenant/identity từ nguồn server, kiểm tra số dòng cập nhật.
4. Khi policy phức tạp, phối hợp policy layer và persistence constraint; không cho phép DB query rộng hơn phạm vi đã thỏa.

SQL minh họa, không phải file Java chạy trực tiếp:

~~~sql
UPDATE documents
SET content = :newContent
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND owner_username = :authenticatedUsername
  AND status = 'EDITABLE';
~~~

Nếu số dòng cập nhật = 0, không được trả “đã sửa thành công”. Từ chối hoặc xử lý conflict theo contract API. Điều kiện owner/tenant của SELECT và UPDATE phải được tính từ server và ràng buộc dữ liệu thật. Không tin tenant id do body JSON tự gửi.

Lưu ý: SQL trên chỉ phù hợp một chính sách owner-edit; nếu policy cho phép manager sửa theo điều kiện khác, phải thiết kế câu UPDATE tương ứng, không thay thế policy domain bằng một WHERE sao chép thiếu logic.

## 12. Chống IDOR/BOLA: đã đăng nhập không đủ để xem mọi id

Một endpoint <code>GET /documents/{id}</code> dễ mắc **Insecure Direct Object Reference / Broken Object Level Authorization** khi chỉ xét người gọi đã đăng nhập:

~~~java
// KHÔNG ĐỦ: có authentication nhưng không có object authorization.
.requestMatchers("/documents/**").authenticated()
~~~

Rule này là lớp chắn thô đúng đắn trong bài, nhưng nó **chưa** trả lời user có quyền trên id cụ thể hay không. Cần policy so sánh identity, tenant, owner, vai trò, trạng thái tài nguyên.

Không thể dựa vào ID khó đoán, UUID ngẫu nhiên hay ẩn nút “Edit” ở frontend để thay authorization. Kẻ tấn công có thể gọi trực tiếp API, đổi ID trong path hoặc dùng account khác có quyền thấp hơn.

Các trường hợp cần kiểm thử:
- Owner và non-owner cùng tenant.
- Người khác tenant có role giống nhau.
- Manager chỉ có quyền đọc nhưng không phải quyền sửa.
- Tài nguyên không tồn tại.
- User bị khóa/đổi membership/thu hồi role.
- Một request cố đưa owner/tenant tự khai để nâng quyền.
- Các route phụ như export, attachment, history, comment, bulk action.

## 13. Danh sách, tìm kiếm và phân trang cần policy ở query

Policy <code>canRead(document)</code> dùng tốt cho một document, nhưng endpoint liệt kê hàng nghìn document không nên:
1. Chạy SELECT toàn bộ document mọi tenant.
2. Đọc dữ liệu nhạy cảm vào memory.
3. Sau đó lọc bằng Java stream theo owner và role.

Cách làm đó có nguy cơ performance, data leak qua log/cache, pagination sai, total count lộ số lượng và sự thiếu nhất quán. Thay vào đó:
- Derive query scope từ identity đã xác thực và chính sách.
- Dùng <code>WHERE tenant_id = ...</code> cùng điều kiện owner/manager phù hợp.
- Áp sorting, limit/offset hoặc cursor **sau khi** đã thu hẹp phạm vi.
- Tính total count theo **cùng scope**.
- Với search/export/batch, đảm bảo cùng logic hoặc dùng specification/query builder được kiểm soát.

Ví dụ query minh họa:

~~~sql
SELECT id, title, content
FROM documents
WHERE tenant_id = :trustedTenant
  AND (
       owner_username = :authenticatedUsername
       OR :hasManagerRole = TRUE
  )
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

Đây là một cách diễn đạt **riêng cho policy read** của demo. Trong database thật, không tin <code>:hasManagerRole</code> do client tự gửi; nó phải được server suy ra từ Authentication đã được xác minh. Kiểm thử số liệu phân trang và count để không lộ dữ liệu thuộc tenant khác.

## 14. Data masking và quyền theo trường

Được phép đọc document không có nghĩa được đọc mọi trường:
- Người dùng có thể xem title/body nhưng không được xem audit notes.
- Manager có thể xem bản ghi của cả đội nhưng không xem thông tin xác thực cá nhân.
- Auditor có thể xem lịch sử nhưng không sửa content.
- Tenant admin không tự có quyền quản trị tenant khác.

Thiết kế nên dùng response DTO rõ ràng và field-level policies nếu cần. Đừng trả nguyên JPA entity rồi hy vọng Jackson tự bỏ những field nhạy cảm. DTO giúp giới hạn payload; service policy quyết định tài nguyên/action; còn repository query bảo đảm không lấy quá phạm vi cần thiết.

## 15. Khi chính sách thay đổi hoặc phụ thuộc external PDP

Trong sản phẩm thật, quyền có thể đổi theo nhóm, workspace, subscription, trạng thái hồ sơ, phiên làm việc, thời gian, delegation hoặc approval. Lúc đó:
- Policy có thể tách thành những rule nhỏ có tên, nhưng vẫn giữ một entrypoint ra quyết định.
- Dữ liệu membership/permission phải có nguồn đáng tin, versioning và cache invalidation phù hợp.
- Nếu dùng policy engine bên ngoài (OPA, Cedar hoặc dịch vụ authorization), cần thiết kế timeout, availability, decision caching, request context tối thiểu và chính sách **fail closed** cho dữ liệu nhạy cảm.
- Log audit nên có actor ID, action, resource ID, policy version, decision và correlation ID; không log password/access token hoặc toàn bộ nội dung document.
- Khi role bị thu hồi, session/JWT có thể còn giữ authorities cũ. Cần quyết định độ tươi của permission, re-check nguồn chung hoặc token lifetime theo mức độ rủi ro.
- Policy version và tests là một phần của change management; một thay đổi role không được vô ý mở quyền cross-tenant.

Không bắt buộc có policy server mới có separation of concerns. Một Spring bean <code>DocumentPolicy</code> tập trung và được test tốt đã là bước tiến quan trọng so với if/else lặp trong Controller.

## 16. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Hướng giải quyết |
| --- | --- | --- |
| Kiểm tra owner ở từng Controller | Rule phân tán, dễ lệch | Policy bean và enforced service |
| Chỉ dùng <code>authenticated()</code> cho /documents/{id} | IDOR/BOLA | Object-level policy |
| Chỉ dùng <code>hasRole("MANAGER")</code> | Manager thấy dữ liệu tenant khác | Kết hợp tenant membership |
| Nhận tenantId từ request là đáng tin | Cross-tenant access | Tenant lấy từ identity/membership server |
| Controller inject repository trực tiếp | Bỏ qua service policy | Điều chỉnh architecture và tests |
| Quên <code>@EnableMethodSecurity</code> | @PreAuthorize không chạy | Bật method security và test thật |
| Gọi <code>this.protectedMethod()</code> | Có thể bypass proxy | Gọi qua Spring proxy hoặc check policy tường minh |
| Policy cấp quyền khi resource missing | Lộ/cho phép nhầm | Deny by default |
| Query danh sách toàn DB rồi lọc Java | Lộ dữ liệu, count/pagination sai | Query scope từ database |
| Check quyền rồi UPDATE không có điều kiện | TOCTOU, race | Transaction/lock/conditional UPDATE |
| Manager xem được nên được mặc nhiên sửa | Over-permission | Tách action READ và EDIT |
| Coi DTO là authorization | Người gọi vẫn có thể xem record ngoài quyền | Enforce ở service |
| Coi URL ẩn/UUID khó đoán là bảo mật | Endpoint vẫn bị đoán hoặc gọi trực tiếp | Authorization server-side |
| Tests chỉ có owner happy path | Bỏ sót cross-tenant và bypass | Negative matrix tests |
| Policy ở web mà không bảo vệ batch/message | Entry point khác bỏ qua | Enforcement ở use case và service |
| Cache authorities quá lâu | Quyền đã thu hồi vẫn tồn tại | Freshness/version/revalidation policy |

## 17. Checklist thiết kế trước khi triển khai

1. Viết ma trận actor/action/resource/context trước khi code.
2. Xác định principal, roles, tenant và resource attributes đến từ **nguồn đáng tin**.
3. Thiết kế <code>Policy</code> trả quyết định rõ ràng, tách HTTP/serialization/CRUD.
4. Dùng <code>SecurityFilterChain</code> cho authentication và coarse-grained HTTP boundary.
5. Đặt enforcement ở service/use case bằng <code>@PreAuthorize</code> hoặc explicit authorization check.
6. Kiểm tra các lối bypass: self-invocation, non-Spring object, controller inject store trực tiếp, jobs, listeners, GraphQL, batch.
7. Bảo đảm read/update query được ràng buộc tenant/owner; xử lý transaction, optimistic version và race khi cần.
8. Tách read, edit, delete, export, approve và admin actions thành policy actions độc lập.
9. Sử dụng DTO để hạn chế trường trả ra; không expose entity nội bộ tùy tiện.
10. Test owner, non-owner cùng tenant, manager, cross-tenant, anonymous, missing resource, CSRF và bulk/listing.
11. Test 401/403 và semantics 404 một cách nhất quán; không lộ sự tồn tại tài nguyên ngoài quyền.
12. Audit quyết định và thay đổi policy nhưng không log secrets; đánh giá freshness của cache/claims/token.
13. Review policy khi thêm endpoint mới hoặc thay role/tenant model; default deny cho bề mặt chưa phân loại.

## 18. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao Controller không phải nơi duy nhất kiểm tra owner?  
**Trả lời:** Vì business use case có thể được gọi từ nhiều entry point không qua controller đó. Enforcement ở service kết hợp policy riêng giúp kiểm soát tập trung và dễ test.

**Câu 2:** Rule HTTP <code>authenticated()</code> đã đủ bảo vệ GET /documents/2 chưa?  
**Trả lời:** Chưa. Nó chỉ chứng minh người gọi có authentication; còn phải kiểm tra người đó có quyền với document ID 2, tenant và action READ hay không.

**Câu 3:** Manager thuộc tenant-a có thể đọc tài liệu tenant-b không?  
**Trả lời:** Không theo policy demo. Role MANAGER chỉ có ý nghĩa bên trong ranh giới tenant đã được server xác nhận.

**Câu 4:** <code>@PreAuthorize</code> ở DocumentService có tự bảo vệ lời gọi <code>this.replaceContent()</code> nội bộ không?  
**Trả lời:** Không thể mặc định như vậy. Proxy-based method security thường không intercept self-invocation; cần tách bean hoặc explicit check phù hợp.

**Câu 5:** Vì sao policy check trước UPDATE chưa luôn an toàn khi owner có thể đổi?  
**Trả lời:** Có TOCTOU: owner/tenant/status có thể đổi giữa kiểm tra và ghi. Cần transaction/lock, optimistic version hoặc conditional SQL bảo đảm cập nhật vẫn thỏa điều kiện tại thời điểm ghi.

**Câu 6:** Với API danh sách, có nên SELECT tất cả tài liệu rồi lọc quyền trong Java không?  
**Trả lời:** Không nên. Hãy áp data scope ở query, rồi mới tính pagination/count để giảm nguy cơ data leak và kết quả sai.

**Câu 7:** Nếu đã dùng DTO để không lộ tenantId, có thể bỏ service authorization không?  
**Trả lời:** Không. DTO che trường dữ liệu, không ngăn một user lấy nội dung của tài liệu khác mà họ không được phép đọc.

**Ghi nhớ:** **Controller nhận yêu cầu; Policy quyết định quyền; Service bắt buộc thực thi policy; Repository bảo vệ phạm vi và tính nhất quán dữ liệu; DTO kiểm soát payload trả ra.** Sự phân tách này giúp quyền được áp dụng đồng nhất, test độc lập và mở rộng an toàn khi có nhiều tài nguyên, tenant hoặc entry point.
