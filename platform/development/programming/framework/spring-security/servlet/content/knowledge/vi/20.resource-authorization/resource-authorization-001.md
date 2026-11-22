# Quyền sở hữu tài nguyên và nguy cơ IDOR khi chỉ kiểm tra vai trò

## Mục tiêu bài học

Trong Spring Security Servlet, một request có thể **được xác thực hợp lệ** và người gửi có **vai trò hợp lệ**, nhưng vẫn **không có quyền với tài nguyên cụ thể** mà họ yêu cầu. Ví dụ: Alice có ROLE_USER, được sử dụng chức năng xem tài liệu; tuy nhiên tài liệu số 102 thuộc Bob. Nếu ứng dụng chỉ kiểm tra hasRole("USER") rồi lấy bản ghi theo ID trong URL, Alice có thể đổi /documents/101 thành /documents/102 để đọc dữ liệu của Bob. Đây là lỗi kiểm soát quyền ở cấp đối tượng, thường được gọi là **Insecure Direct Object Reference (IDOR)** hoặc thuộc nhóm **Broken Object Level Authorization (BOLA)**.

Bài học này tập trung vào câu hỏi: **“Đối tượng đang được yêu cầu thuộc về ai, người gọi có quyền gì trên chính đối tượng ấy, và kiểm tra đó có được áp dụng ở mọi đường truy cập không?”**. RBAC, HTTP request matching và xác thực chỉ là các thành phần của câu trả lời.

Sau khi học, bạn có thể:

1. Phân biệt authentication, role-based authorization (RBAC), ownership authorization và tenant isolation.
2. Nhận diện IDOR/BOLA trong URL, body, query, tải file, export, list/search và API thay đổi trạng thái.
3. Giải thích vì sao một API có .authenticated() hoặc hasRole("USER") vẫn có thể lộ dữ liệu.
4. Thiết kế chính sách owner / admin / share / tenant phù hợp, tránh tin các trường owner do client tự gửi.
5. Bảo vệ tài nguyên tại Spring Security Servlet HTTP layer và service layer, đặc biệt bằng @EnableMethodSecurity và @PreAuthorize.
6. Kết hợp kiểm tra quyền với truy vấn database giới hạn theo owner/tenant, thay vì chỉ dựa trên một lần kiểm tra trước.
7. Tạo và chạy ví dụ Java 17, Spring Boot 3.x, Spring Security 6.x, Spring Data JPA và H2, có dữ liệu Alice/Bob và test phủ định.
8. Kiểm tra các trường hợp khó: ADMIN, request anonymous, object không tồn tại, đổi owner đồng thời, multi-tenant, mass assignment và đường đi không qua controller.
9. Lập checklist phòng ngừa và kiểm thử IDOR cho một API thật.

Phạm vi là **Spring Security Servlet + Spring MVC**. Các vấn đề bảo vệ object còn áp dụng cho GraphQL, messaging hoặc API khác, nhưng ví dụ chạy được bên dưới sử dụng HTTP Basic cho dễ thử request; credential demo và H2 in-memory **không dùng cho production**.

## 1. Đúng vai trò chưa chắc đúng chủ sở hữu

Xét hệ thống quản lý tài liệu:

| Tài nguyên | Chủ sở hữu | Nội dung |
| --- | --- | --- |
| document 101 | alice | Ghi chú riêng của Alice |
| document 102 | bob | Kế hoạch riêng của Bob |
| document 103 | alice | Hóa đơn của Alice |

Cả Alice và Bob đều có ROLE_USER. Quy tắc HTTP:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").hasRole("USER")
        .anyRequest().denyAll());
~~~

Chỉ chứng minh người gửi có vai trò USER khi URL khớp rule; **nó không tự hỏi tài liệu 102 thuộc ai**. Nếu controller sau đó gọi repository.findById(102), Alice có thể nhận tài liệu của Bob mặc dù Spring Security đã xác thực và kiểm tra role thành công.

Bốn câu hỏi độc lập:

| Câu hỏi | Cơ chế ví dụ | Chưa giải quyết điều gì? |
| --- | --- | --- |
| Bạn là ai? | AuthenticationManager, session, Basic, OAuth2 Resource Server | Chưa biết bạn có quyền thao tác |
| Bạn thuộc vai trò nào? | hasRole, hasAuthority, RoleHierarchy | Chưa biết bản ghi thuộc ai |
| Tài nguyên nào đang được truy cập? | URI path/query/body → tra database | Chưa biết quyền trên bản ghi đó |
| Bạn có được làm hành động này trên tài nguyên ấy? | Ownership/tenant/ACL/policy, truy vấn ràng buộc | Phải đánh giá theo tài nguyên và hành động cụ thể |

**Authentication là điều kiện cần, không phải quyền sở hữu.** Trường documentId được gửi trong request là **tham chiếu do client kiểm soát**, dù nó có dạng số tăng dần hay UUID khó đoán.

### Tấn công IDOR hoạt động ra sao?

~~~text
Bước 1: Alice đăng nhập hợp lệ => Authentication(name="alice", ROLE_USER)

Bước 2: Alice gọi GET /api/documents/101
        -> Spring Security: ROLE_USER? Có
        -> Controller: repository.findById(101)
        -> trả document 101 của alice

Bước 3: Alice sửa một chữ số: GET /api/documents/102
        -> Spring Security: ROLE_USER? Vẫn có
        -> Controller: repository.findById(102)
        -> trả document 102 của bob  <-- lộ dữ liệu
~~~

Đây không phải lỗi đoán mật khẩu, vượt qua login hay làm giả token. Attacker thường có tài khoản hợp lệ và **chỉ thay tham chiếu đối tượng**. Vì vậy báo cáo “authentication hoạt động” không chứng minh API đã chống IDOR.

### IDOR và BOLA có giống hệt nhau?

- **IDOR** thường mô tả kiểu truy cập trực tiếp tới đối tượng bằng một định danh mà không kiểm tra quyền người gọi trên đối tượng đó.
- **BOLA** nhấn mạnh thiếu/bị lỗi object-level authorization ở API, có thể xảy ra cả khi định danh không lộ rõ hoặc đường truy cập phức tạp.
- Hai thuật ngữ có vùng giao nhau lớn; khi phân tích kỹ thuật, quan trọng hơn là **hành động, nguồn dữ liệu, danh tính và điều kiện cho phép**.

Không dùng nhãn IDOR như một lời kết luận rằng một ID tuần tự tự nó là lỗ hổng. Lỗ hổng là **thiếu kiểm tra quyền**, không phải bản thân định dạng ID.

## 2. Câu chuyện thực tế: tấn công không chỉ nằm ở GET /{id}

### 2.1. Đọc bản ghi của người khác

~~~text
GET /api/orders/7001    -> order của Alice
GET /api/orders/7002    -> order của Bob
~~~

Nếu cả hai đi qua .authenticated() rồi repository.findById(orderId), user khác có thể lấy order, địa chỉ nhận hàng hoặc thông tin thanh toán của Bob.

### 2.2. Thay đổi hoặc xóa bản ghi

~~~text
PUT /api/documents/102
{"title":"Đã bị sửa"}

DELETE /api/documents/102
~~~

Một API chỉ hasRole('USER') có thể cho user xóa/sửa tài liệu của người khác. Đây là **integrity violation** ngoài rủi ro đọc trộm. Phải kiểm tra quyền theo **hành động**: canRead không mặc nhiên là canEdit, và canEdit không mặc nhiên là canDelete.

### 2.3. API tải file hoặc xem ảnh riêng tư

~~~text
GET /api/files/f-102/download
GET /api/users/42/private-avatar
~~~

Ngay cả khi file được lưu trong S3/MinIO hoặc local storage, service vẫn phải biết file gắn với owner/tenant nào trước khi cấp quyền. Nếu trả presigned URL, thời hạn, phạm vi object và điều kiện phát hành URL phải được giới hạn; không coi việc object có tên dài là biện pháp xác thực.

### 2.4. List, search và export

~~~text
GET /api/documents?page=1
GET /api/documents?owner=bob
POST /api/reports/export
{"documentIds":[101,102,103]}
~~~

IDOR không chỉ xảy ra với một resource ID trong path. Query owner=bob hoặc danh sách IDs cũng do client chọn. Nếu backend chỉ kiểm tra role rồi truy vấn tất cả bản ghi, Alice có thể nhận hàng loạt dữ liệu của người khác. Một batch request cần **lọc/kiểm tra từng đối tượng hoặc truy vấn có điều kiện owner/tenant cho toàn bộ tập**, không chỉ kiểm tra quyền của bản ghi đầu tiên.

### 2.5. Tham chiếu lồng nhau

~~~text
GET /api/projects/5/tasks/900
~~~

Ngay cả khi Alice được xem project 5, task 900 có thể thuộc project 6 hoặc tenant khác. Phải đảm bảo **mối quan hệ parent-child thực trong database**: task.project_id == projectId và caller có quyền trên task/project, không suy ra từ hai giá trị client đặt trong URL.

### 2.6. Gán quyền bằng body (mass assignment)

~~~json
{
  "title": "Hóa đơn mới",
  "ownerUsername": "admin",
  "tenantId": "another-tenant"
}
~~~

Nếu controller binding thẳng DTO/body vào JPA entity và save, client có thể tự đổi owner/tenant hoặc trường isAdmin. Đó là dạng **mass assignment / broken object property level authorization**, liên quan tới kiểm soát quyền nhưng không hoàn toàn trùng với IDOR. DTO cho phép sửa phải chỉ chứa các field được phép; owner/tenant phải lấy từ identity và dữ liệu server đáng tin, không lấy từ body.

## 3. Thiết kế chính sách truy cập theo đối tượng

Một policy dễ hiểu cho ứng dụng demo:

- **Alice** được đọc và sửa tài liệu do Alice sở hữu.
- **Bob** được đọc và sửa tài liệu do Bob sở hữu.
- **ADMIN** được đọc mọi tài liệu nếu policy của sản phẩm thật sự cho phép, **nhưng không mặc nhiên được sửa tài liệu của người khác**.
- **Anonymous** không được đọc/sửa.
- **Tài liệu không tồn tại** không được trả dữ liệu và không được đánh dấu “đã cấp quyền”.
- **Đối tượng thuộc tenant khác** luôn cần chính sách tenant riêng, kể cả khi username trùng nhau.

Viết dưới dạng predicate:

~~~text
canRead(caller, doc) =
    caller.authenticated
    AND doc.exists
    AND (doc.ownerId == caller.id OR caller.hasPermission("document:read:any"))

canEdit(caller, doc) =
    caller.authenticated
    AND doc.exists
    AND doc.ownerId == caller.id
    AND doc.state allows edit

canDelete(caller, doc) =
    caller.authenticated
    AND doc.exists
    AND policy-specific permission to delete
~~~

Trong demo, ta dùng username từ Authentication như định danh owner vì tài khoản được tạo trong cùng ứng dụng và username cố định. **Production nên ưu tiên immutable user ID**, kết hợp tenant ID và quyền chia sẻ/ACL/ABAC nếu cần.

Một role như ROLE_ADMIN không có nghĩa tự động có toàn quyền với dữ liệu nhạy cảm. Chỉ thêm nhánh admin nếu product requirement nói rõ, có test và audit. Khi một user ở trạng thái suspended hoặc quyền bị thu hồi, phải xem lại chính sách revalidation và dữ liệu Authentication/cache.

### RBAC, ABAC và ReBAC

| Mô hình | Kiểm tra | Ví dụ |
| --- | --- | --- |
| RBAC | Role/authority của caller | ROLE_ACCOUNTANT được mở màn hình báo cáo |
| ABAC | Thuộc tính caller, tài nguyên, hành động, bối cảnh | ownerId, tenantId, status, time, department |
| ReBAC | Quan hệ giữa các thực thể | user là thành viên project, được share document |
| Ownership đơn giản | Tài nguyên thuộc người gọi | doc.ownerUserId == caller.userId |

Trong thực tế, các mô hình thường được phối hợp. RBAC có thể quyết định **ai được dùng chức năng**, ownership hoặc ReBAC quyết định **được dùng chức năng trên bản ghi nào**.

## 4. Nguồn thông tin đáng tin: identity và owner

Cần phân biệt rõ hai nguồn dữ liệu:

1. **Danh tính người gọi:** Authentication đã được Spring Security xác minh qua security chain (trong demo là HTTP Basic). Có thể truy cập qua SecurityContextHolder hoặc truyền Authentication được framework cung cấp.
2. **Chủ sở hữu thực:** trường ownerId/tenantId nằm trong database của tài nguyên, hoặc một nguồn quản lý quyền được tin cậy.

Những giá trị **không đủ tin cậy** khi đứng một mình:

- ID trong path: /api/documents/102.
- Username/ownerId trong query: ?owner=bob.
- Header tự khai: X-User: alice hoặc X-Tenant: t-02.
- Body: {"ownerId":"alice"}.
- Cache key được client chỉ định.
- Tên file/đường dẫn storage do client cung cấp.

Có thể lấy identity qua principal claims từ JWT/OIDC sau khi token được xác minh, nhưng **Authentication.getName() không luôn là username**. Với nhiều identity provider, nó có thể là sub, email hoặc một claim tùy cấu hình. Trước khi so sánh với owner trong database, cần ánh xạ sang internal user ID đúng quy tắc.

Không so sánh hai giá trị cùng do client cung cấp rồi gọi đó là authorization:

~~~java
// Sai về bảo mật nếu cả owner và username đều đến từ request:
if (requestOwner.equals(requestUsername)) {
    return documentRepository.findById(documentId);
}
~~~

Ở đây attacker chỉ cần đặt cả hai là alice hoặc bob. Một policy đúng phải liên kết **caller đã được xác minh** với **owner thực của record**.

### UUID hoặc ID ngẫu nhiên có ngăn IDOR không?

UUID khó đoán làm giảm khả năng đoán ngẫu nhiên, nhưng không thay thế authorization. ID vẫn có thể bị lộ qua URL, log, email, browser history, analytics hoặc nội dung share. **Không kiểm tra ownership vì ID dài** là một lỗ hổng kiểm soát truy cập.

## 5. Đặt kiểm tra quyền ở đâu?

Một request Servlet đi qua các tầng:

~~~text
HTTP client
    |
FilterChainProxy / SecurityFilterChain
    |-- Authentication (ai đang gọi?)
    |-- authorizeHttpRequests (endpoint/method có yêu cầu gì?)
    |
DispatcherServlet
    |
DocumentController
    |
DocumentService
    |-- method security + policy on resource
    |
DocumentRepository
    |-- query gắn owner/tenant, không lấy dữ liệu trái phép
    |
Database
~~~

HTTP authorization có thể chặn sớm request chưa login hoặc chưa có role chức năng. Nhưng một người dùng cùng vai trò vẫn có thể không được phép đọc bản ghi của người khác; vì vậy ta kiểm tra **tài nguyên và hành động cụ thể ở service**.

Các lựa chọn chính:

- **Service logic thủ công:** lấy caller từ Authentication và truy vấn record theo owner/tenant; đơn giản, rõ với use case không phức tạp.
- **Method security:** @EnableMethodSecurity + @PreAuthorize("@documentPermission.canRead(#id, authentication)") trước khi chạy service.
- **Method security ở controller:** có ích nhưng không đủ bảo vệ nếu service được gọi từ job, consumer, controller khác.
- **Repository query scoping:** findByIdAndOwnerUsername hoặc WHERE owner_user_id = :callerId; ngăn trả sai record và hạn chế TOCTOU.
- **Database row-level security:** thêm lớp bảo vệ khi hệ quản trị hỗ trợ, nhưng phải cấu hình principal/tenant context đúng, kiểm thử mọi query path.
- **Central policy/ACL engine:** phù hợp hệ thống phức tạp có document sharing, hierarchy, organization, project membership.

Các lớp bảo vệ khác nhau là **defense in depth**, không phải lý do sao chép ba bản logic phân quyền không đồng nhất. Một nơi định nghĩa chính sách nghiệp vụ nên được dùng nhất quán ở các điểm vào, đồng thời repository query phải thực thi ranh giới dữ liệu.

### Vì sao HTTP-only không đủ cho mọi đường đi?

Cùng DocumentService.read(id) có thể được gọi bởi REST controller, GraphQL resolver, một message consumer hoặc một service khác. Rule requestMatchers("/api/**") chỉ xét request HTTP đã vào đúng chain, không tự chạy khi scheduled job gọi Java method. Với service method được bảo vệ qua Spring AOP proxy, chính sách gần nghiệp vụ hơn; tuy nhiên self-invocation hoặc controller gọi repository trực tiếp vẫn có thể bỏ qua, cần kiến trúc và test.

## 6. Sai lầm kỹ thuật phổ biến trước khi thực hành

### 6.1. Chỉ dùng hasRole('USER')

~~~java
@PreAuthorize("hasRole('USER')")
public DocumentDto read(Long documentId) {
    return mapper.toDto(repository.findById(documentId).orElseThrow());
}
~~~

Nếu cả Alice và Bob đều ROLE_USER, cả hai có thể đọc mọi document ID. Annotation này chỉ thể hiện role chung, không ràng buộc owner.

### 6.2. Chỉ so sánh path user với Authentication

~~~java
@PreAuthorize("#username == authentication.name")
public DocumentDto read(String username, Long documentId) {
    return mapper.toDto(repository.findById(documentId).orElseThrow());
}
~~~

Dù username đúng với Authentication, documentId có thể thuộc người khác. Tham số username **không chứng minh** document 102 thuộc username ấy. Phải liên kết documentId với bản ghi trong database.

### 6.3. Đọc trước rồi trả dữ liệu, mới kiểm tra ở client

~~~javascript
// Sai: frontend che tài liệu của người khác chỉ bằng nút ẩn.
// Backend đã gửi dữ liệu là đã xảy ra lộ thông tin.
if (loggedInUser !== document.ownerUsername) {
    hideDownloadButton();
}
~~~

Frontend permissions hữu ích cho UX nhưng không phải boundary bảo mật. Backend phải từ chối **trước khi gửi body, file hoặc signed URL**.

### 6.4. Dùng findById thay vì owner-scoped query

~~~java
repository.findById(documentId);
~~~

Không phải mọi lời gọi findById đều sai, nhưng nếu service đang phục vụ user thông thường và không có check owner được bảo đảm, nó dễ trở thành điểm tạo IDOR.

Có thể dùng:

~~~java
repository.findByIdAndOwnerUsername(
        documentId, authentication.getName());
~~~

Hoặc với tenant:

~~~sql
SELECT id, owner_user_id, tenant_id, title
FROM documents
WHERE id = :document_id
  AND owner_user_id = :authenticated_user_id
  AND tenant_id = :authenticated_tenant_id;
~~~

Các tham số authenticated_* phải được lấy từ identity đã xác minh và scope do server xác định, không được lấy trực tiếp từ request.

## 7. Ví dụ hoàn chỉnh: Spring Boot, Spring Security và H2

Ta xây API tài liệu đơn giản:

- GET /api/documents/{id}: yêu cầu người dùng đã đăng nhập ở HTTP layer; service chỉ cho owner hoặc ADMIN đọc bản ghi.
- PUT /api/documents/{id}: yêu cầu người dùng đã đăng nhập; service **chỉ cho owner** đổi title, ngay cả ADMIN không có đặc quyền sửa trong demo.
- Dữ liệu khởi tạo document 101 của Alice và document 102 của Bob.
- Role USER không đủ để gọi vào bản ghi người khác.
- Method security kiểm tra ownership qua Spring Data JPA.
- Repository query gắn owner ở đường đọc/sửa của user thường.
- Kiểm thử cả HTTP/CSRF và lời gọi trực tiếp vào Spring-managed service bean.

Ứng dụng dùng **Java 17**, **Spring Boot 3.3.5**, **Spring Security 6.x theo dependency management của Boot**, Spring Data JPA, H2 in-memory. HTTP Basic dùng để làm demo không cần giao diện; trong production phải dùng HTTPS và quản lý user/credential bằng cơ chế phù hợp.

### 7.1. Cấu trúc

~~~text
resource-ownership-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (Gradle Wrapper nếu có)
  src/main/java/dev/example/ownership/
    OwnershipApplication.java
    SecurityConfig.java
    DocumentEntity.java
    DocumentRepository.java
    DocumentPermission.java
    DocumentService.java
    DocumentController.java
  src/test/java/dev/example/ownership/
    DocumentOwnershipIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'resource-ownership-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot starter quản lý các phiên bản dependency tương thích. Nếu dùng Boot 4 hoặc Spring Security phiên bản khác, hãy xem tài liệu của chính phiên bản đó vì API/config mặc định có thể thay đổi. Không mix spring-security-* versions thủ công.

### 7.2. Main application và data seeding

Tệp src/main/java/dev/example/ownership/OwnershipApplication.java:

~~~java
package dev.example.ownership;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(DocumentRepository documents) {
        return args -> {
            if (!documents.existsById(101L)) {
                documents.save(new DocumentEntity(
                        101L, "alice", "Alice private notes"));
            }
            if (!documents.existsById(102L)) {
                documents.save(new DocumentEntity(
                        102L, "bob", "Bob private plans"));
            }
        };
    }
}
~~~

ID cố định giúp tái hiện tấn công IDOR và viết test có kỳ vọng rõ. H2 in-memory được Boot tạo theo vòng đời ứng dụng; đây là dữ liệu demo, không phải database production. Test sẽ làm sạch và nạp lại dữ liệu trước từng test để tránh phụ thuộc thứ tự chạy.

### 7.3. Entity: owner nằm trong database, không do client quyết định

Tệp src/main/java/dev/example/ownership/DocumentEntity.java:

~~~java
package dev.example.ownership;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "demo_documents")
public class DocumentEntity {

    @Id
    private Long id;

    @Column(nullable = false, updatable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected DocumentEntity() {
    }

    public DocumentEntity(
            Long id, String ownerUsername, String title) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

Dùng @Column(updatable = false) cho ownerUsername trong demo để chứng minh đổi title không vô tình đổi owner. Trong hệ thống thật, chuyển quyền sở hữu là một **use case riêng** có kiểm tra quyền chặt, transaction và audit; không nên dựa hoàn toàn vào annotation này như một cơ chế bảo mật tuyệt đối.

Không nhận DocumentEntity trực tiếp làm @RequestBody cho thao tác đổi title: client có thể gửi các property không được phép. Tạo request DTO chỉ có title như bên dưới.

### 7.4. Repository

Tệp src/main/java/dev/example/ownership/DocumentRepository.java:

~~~java
package dev.example.ownership;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    boolean existsByIdAndOwnerUsername(
            Long id, String ownerUsername);

    Optional<DocumentEntity> findByIdAndOwnerUsername(
            Long id, String ownerUsername);
}
~~~

Spring Data JPA tạo truy vấn từ tên method theo property của entity. OwnerUsername được lấy từ Authentication trên server; **không** đặt một request parameter ownerUsername vào đây mà chưa xác minh.

### 7.5. SecurityConfig: hai tầng HTTP và method security

Tệp src/main/java/dev/example/ownership/SecurityConfig.java:

~~~java
package dev.example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-demo-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/documents/*")
                        .authenticated()
                        .requestMatchers(
                                HttpMethod.PUT, "/api/documents/*")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

Trong demo, HTTP rule cố ý chỉ yêu cầu authenticated() đối với GET/PUT. Điều này làm rõ **HTTP layer chưa đủ quyết định quyền với document ID**; đó là trách nhiệm của service. anyRequest().denyAll() bảo vệ mọi route/method không khai báo.

@EnableMethodSecurity kích hoạt việc đánh giá các annotation như @PreAuthorize trên Spring-managed bean, không phải tự sinh owner check. Đừng dùng web.ignoring() để bỏ qua Spring Security với endpoint nghiệp vụ.

Mã demo không tắt CSRF. Vì vậy PUT phải gửi token CSRF hợp lệ trong test; nếu bạn thử PUT bằng curl chỉ với HTTP Basic và không có token, CsrfFilter có thể trả 403 **trước** khi service có cơ hội kiểm tra ownership. Không được nhầm “CSRF chặn” với “IDOR đã được phòng”.

### 7.6. DocumentPermission: policy owner/admin lấy dữ liệu thật

Tệp src/main/java/dev/example/ownership/DocumentPermission.java:

~~~java
package dev.example.ownership;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPermission")
public class DocumentPermission {

    private final DocumentRepository documents;

    public DocumentPermission(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean canRead(Long id, Authentication authentication) {
        if (id == null || !isAuthenticatedUser(authentication)) {
            return false;
        }
        if (isAdmin(authentication)) {
            return documents.existsById(id);
        }
        return documents.existsByIdAndOwnerUsername(
                id, authentication.getName());
    }

    public boolean canEdit(Long id, Authentication authentication) {
        return id != null
                && isAuthenticatedUser(authentication)
                && documents.existsByIdAndOwnerUsername(
                        id, authentication.getName());
    }

    public boolean isAdmin(Authentication authentication) {
        return isAuthenticatedUser(authentication)
                && authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        "ROLE_ADMIN".equals(authority.getAuthority()));
    }

    private boolean isAuthenticatedUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

Vì policy đọc thực tế document ID từ repository, một user ROLE_USER không được cấp quyền trên ID không thuộc họ. ADMIN được quyền read theo policy ví dụ; canEdit không có nhánh ADMIN.

Điểm quan trọng về anonymous: AnonymousAuthenticationToken có thể trả isAuthenticated() true về mặt implementation nhưng không đại diện một user thật. Policy loại anonymous và từ chối id null. Nếu môi trường dùng authentication type khác, phải xác định thế nào là authenticated principal đáng tin.

### 7.7. DocumentService: không trả dữ liệu ngoài owner scope

Tệp src/main/java/dev/example/ownership/DocumentService.java:

~~~java
package dev.example.ownership;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository documents;
    private final DocumentPermission permission;

    public DocumentService(
            DocumentRepository documents,
            DocumentPermission permission) {
        this.documents = documents;
        this.permission = permission;
    }

    @PreAuthorize(
            "@documentPermission.canRead(#id, authentication)")
    @Transactional(readOnly = true)
    public DocumentView read(@P("id") Long id) {
        Authentication caller =
                SecurityContextHolder.getContext().getAuthentication();

        DocumentEntity entity;
        if (permission.isAdmin(caller)) {
            entity = documents.findById(id)
                    .orElseThrow(() ->
                            new AccessDeniedException("Access denied"));
        } else {
            entity = documents.findByIdAndOwnerUsername(
                            id, caller.getName())
                    .orElseThrow(() ->
                            new AccessDeniedException("Access denied"));
        }

        return DocumentView.from(entity);
    }

    @PreAuthorize(
            "@documentPermission.canEdit(#id, authentication)")
    @Transactional
    public DocumentView rename(
            @P("id") Long id, String newTitle) {

        if (newTitle == null
                || newTitle.isBlank()
                || newTitle.length() > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Authentication caller =
                SecurityContextHolder.getContext().getAuthentication();

        if (caller == null) {
            throw new AccessDeniedException("No caller");
        }

        DocumentEntity entity =
                documents.findByIdAndOwnerUsername(
                        id, caller.getName())
                .orElseThrow(() ->
                        new AccessDeniedException("Access denied"));

        entity.rename(newTitle.trim());
        return DocumentView.from(entity);
    }

    public record DocumentView(
            Long id, String ownerUsername, String title) {
        static DocumentView from(DocumentEntity entity) {
            return new DocumentView(
                    entity.getId(),
                    entity.getOwnerUsername(),
                    entity.getTitle());
        }
    }
}
~~~

Đây là điểm mấu chốt:

- **@PreAuthorize** đảm bảo policy chạy khi method được gọi **qua Spring proxy**, trước khi body thực thi.
- **@P("id")** làm tên tham số nhất quán cho biểu thức #id ngay cả khi cấu hình compiler parameter names khác nhau.
- **DocumentPermission** đọc owner từ database, không lấy từ body.
- **DocumentService.read** còn dùng truy vấn theo owner cho user thường. Đây là lớp phòng vệ bổ sung nếu dữ liệu owner thay đổi hoặc có code path nguy hiểm; ADMIN đi nhánh riêng theo policy.
- **DocumentService.rename** chỉ lấy một bản ghi thuộc caller, không tự cho phép admin sửa bản ghi của người khác.
- **@Transactional** đảm bảo JPA quản lý entity trong transaction; thay đổi title được Hibernate flush/dirty check khi commit.
- **DocumentView** là DTO trả về client, không trả entity JPA chứa object graph không chủ đích.
- **AccessDeniedException** cho tài liệu không thuộc user giúp tránh trả dữ liệu. Sản phẩm có thể chọn 404 để không lộ sự tồn tại tài nguyên, nhưng phải nhất quán và không truyền chi tiết owner qua lỗi.

Có một điểm cần phân tích ở production: policy existsBy... xảy ra trước khi method body chạy và có thể ngoài transaction của method tùy thứ tự advisors. Nếu owner/tenant thay đổi đồng thời giữa check và use, vẫn có **TOCTOU**. Do đó mẫu còn truy vấn có điều kiện owner trong service; với giao dịch nhạy cảm cần thêm isolation, locking hoặc conditional update theo đúng domain.

### 7.8. Controller chỉ nhận ID và các field được phép sửa

Tệp src/main/java/dev/example/ownership/DocumentController.java:

~~~java
package dev.example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentService.DocumentView read(
            @PathVariable("id") Long id) {
        return service.read(id);
    }

    @PutMapping("/{id}")
    public DocumentService.DocumentView rename(
            @PathVariable("id") Long id,
            @RequestBody RenameDocumentRequest request) {
        return service.rename(id, request.title());
    }

    public record RenameDocumentRequest(String title) {
    }
}
~~~

Controller không nhận ownerUsername trong RenameDocumentRequest, nên client không thể đổi owner qua endpoint này. Nếu JSON gửi thêm field không định nghĩa thì Jackson configuration có thể bỏ qua hoặc từ chối tùy thiết lập; **dù thế nào, DocumentService không dùng giá trị đó**. Nếu API yêu cầu từ chối unknown properties, cấu hình validation/deserialization rõ ràng và test.

Không thêm @PostMapping tự gán ownerUsername từ request để “cho phép gửi tài liệu cho người khác” khi chưa thiết kế use case transfer ownership.

### 7.9. Chạy bằng Gradle

Trong project có Gradle Wrapper, chạy:

~~~bash
./gradlew bootRun
~~~

Với PowerShell Windows dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

Dùng curl với Basic auth chỉ trên localhost cho demo:

~~~bash
curl -i -u alice:alice-demo-pass \
  http://localhost:8080/api/documents/101

curl -i -u alice:alice-demo-pass \
  http://localhost:8080/api/documents/102

curl -i -u bob:bob-demo-pass \
  http://localhost:8080/api/documents/102

curl -i -u admin:admin-demo-pass \
  http://localhost:8080/api/documents/102

curl -i http://localhost:8080/api/documents/101
~~~

Kết quả logic kỳ vọng:

| Request | Kết quả |
| --- | --- |
| Alice đọc document 101 | 200, JSON có id=101, ownerUsername=alice |
| Alice đọc document 102 | 403, không trả title của Bob |
| Bob đọc document 102 | 200, JSON có id=102, ownerUsername=bob |
| ADMIN đọc document 102 | 200, theo ngoại lệ canRead |
| Anonymous đọc document 101 | 401 và WWW-Authenticate theo HTTP Basic |
| Bob sửa document 101 với CSRF hợp lệ | 403, title không thay đổi |
| Bob sửa document 102 với CSRF hợp lệ | 200, title được cập nhật |
| ADMIN sửa document 102 với CSRF hợp lệ | 403 trong policy ví dụ |

**Không dùng HTTP Basic qua HTTP công khai**: Base64 không mã hóa nội dung credential. Localhost chỉ để minh họa; production cần HTTPS và cơ chế account lifecycle phù hợp.

### 7.10. Kiểm thử tích hợp: bắt lỗi IDOR cả ở HTTP và service

Tệp src/test/java/dev/example/ownership/DocumentOwnershipIntegrationTest.java:

~~~java
package dev.example.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentOwnershipIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentRepository documents;

    @Autowired
    DocumentService service;

    @BeforeEach
    void resetData() {
        documents.deleteAll();
        documents.save(new DocumentEntity(
                101L, "alice", "Alice private notes"));
        documents.save(new DocumentEntity(
                102L, "bob", "Bob private plans"));
    }

    @Test
    void ownerCanReadByHttp() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.ownerUsername").value("alice"));
    }

    @Test
    void changingIdCannotRevealOtherUsersDocument()
            throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("bob"));
    }

    @Test
    void adminReadExceptionIsExplicit() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("admin", "admin-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(102));
    }

    @Test
    void anonymousRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void otherUserCannotRenameAndDataDoesNotChange()
            throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("bob", "bob-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Illegal change\"}"))
                .andExpect(status().isForbidden());

        assertThat(documents.findById(101L).orElseThrow()
                .getTitle()).isEqualTo("Alice private notes");
    }

    @Test
    void ownerCanRenameWithCsrf() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Updated title\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated title"));

        assertThat(documents.findById(101L).orElseThrow()
                .getTitle()).isEqualTo("Updated title");
    }

    @Test
    void missingCsrfIsRejectedIndependentlyOfOwner()
            throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .contentType("application/json")
                        .content("{\"title\":\"No csrf\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCannotRenameWithoutExplicitPermission()
            throws Exception {
        mvc.perform(put("/api/documents/102")
                        .with(httpBasic("admin", "admin-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Admin modified\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directServiceCallStillRejectsBobDocument() {
        assertThatThrownBy(() -> service.read(102L))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void directServiceCallAllowsOwner() {
        assertThat(service.read(102L).ownerUsername())
                .isEqualTo("bob");
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void directServiceCallRejectsUnauthorizedEdit() {
        assertThatThrownBy(() ->
                service.rename(102L, "Must not change"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Bộ test này kiểm tra **cả phản hồi lẫn dữ liệu thực tế**: request đổi ID sang tài liệu của người khác phải 403; PUT trái quyền không được âm thầm thay database; owner được sửa khi CSRF hợp lệ; ADMIN không có quyền sửa nếu policy không cấp.

Test trực tiếp DocumentService với @WithMockUser chứng minh method security áp dụng khi gọi **Spring-managed proxy**, không chỉ khi request đi qua SecurityFilterChain của HTTP. Nếu chỉ test controller bằng mock service, bạn có thể bỏ qua đúng lớp kiểm tra quyền quan trọng nhất.

@BeforeEach đặt lại dữ liệu cho từng test, tránh phụ thuộc thứ tự test đổi title. Test này sử dụng H2 in-memory và không thay thế việc kiểm tra locking/concurrency với production database.

## 8. Đặt @PreAuthorize ở đâu cho đúng?

### Trên controller

~~~java
@PreAuthorize("hasRole('USER')")
@GetMapping("/api/documents/{id}")
public DocumentView read(@PathVariable Long id) {
    return documentService.read(id);
}
~~~

Điều kiện trên chỉ kiểm tra role chung, **không kiểm tra owner**. Ngoài ra nếu service được gọi từ một controller mới, job hoặc consumer, annotation ở controller cũ không bảo vệ đường gọi đó.

### Trên service boundary

~~~java
@PreAuthorize(
        "@documentPermission.canRead(#id, authentication)")
public DocumentView read(@P("id") Long id) {
    // ...
}
~~~

Đây là lựa chọn gần nghiệp vụ hơn, khi mọi entrypoint dùng cùng service bean qua proxy. Nhưng nếu controller gọi repository trực tiếp, hoặc một method trong cùng bean gọi protected method bằng this.read(...), interceptor AOP có thể không được áp dụng. Vì thế cần kiến trúc rõ ràng, không chỉ gắn annotation.

### Spring AOP self-invocation là gì?

~~~java
@Service
public class UnsafeDemoService {

    public void exportMany(Long id) {
        readSensitive(id); // gọi nội bộ qua this, thường không qua proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void readSensitive(Long id) {
        // sensitive operation
    }
}
~~~

Nếu exportMany được gọi ngoài bean mà không có policy, lời gọi readSensitive trong cùng object có thể bỏ qua @PreAuthorize. Giải pháp: bảo vệ public entrypoint thật, hoặc tách protected operation sang bean riêng được inject và gọi qua proxy. Không đặt policy duy nhất trên private/final method rồi nghĩ Spring AOP intercept mọi lời gọi.

### @PreAuthorize hay @PostAuthorize?

- **@PreAuthorize:** quyết định trước khi thực thi, phù hợp khi có thể biết policy qua tham số và một truy vấn authorization an toàn.
- **@PostAuthorize:** có thể kiểm tra returnObject sau khi method chạy; phải cẩn trọng nếu method có side effect hoặc tải dữ liệu lớn.
- **@PostFilter:** có thể lọc collection sau khi nạp, nhưng thường kém hiệu quả hơn query database đã lọc theo owner/tenant, và có rủi ro nếu dữ liệu bị log/cache trước khi lọc.
- **Custom AuthorizationManager/policy service:** hữu ích nếu điều kiện phức tạp, cần tái sử dụng giữa nhiều endpoint và method.

Một ví dụ không nên dùng @PostAuthorize như kiểm soát duy nhất cho thao tác sửa dữ liệu:

~~~java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentView rename(Long id, String title) {
    // Có thể đã cập nhật database trước khi policy kiểm tra.
}
~~~

Method đã có thể tạo side effect trước khi bị từ chối. Việc exception ném ra không tự đảo ngược mọi side effect bên ngoài (message, email, external API), và transaction behavior còn phụ thuộc advisor/transaction cấu hình.

## 9. Phòng chống TOCTOU: thời điểm kiểm tra quyền và thời điểm dùng

Giả sử policy đọc owner từ database:

~~~text
T1: canRead(101, alice) -> true vì owner của 101 là alice
T2: transaction khác chuyển owner 101 sang bob
T3: service đọc bản ghi 101 qua findById(101)
~~~

Nếu T3 không gắn owner condition, Alice có thể đọc dữ liệu sau khi ownership đã đổi. Đây là tình huống **time-of-check to time-of-use (TOCTOU)**. @PreAuthorize và @Transactional đặt gần nhau **không tự đảm bảo một phép kiểm tra và truy vấn nguyên tử**; thứ tự AOP advisors và transaction isolation có thể ảnh hưởng.

Các biện pháp:

1. Với đọc dữ liệu, **đưa owner/tenant vào truy vấn lấy dữ liệu**, như findByIdAndOwnerUsername, để không trả row thuộc người khác ở thời điểm truy vấn.
2. Với ghi dữ liệu, cân nhắc **conditional UPDATE** theo id, owner và trạng thái, kiểm tra affected rows.
3. Khi chuyển owner hoặc trạng thái tài nguyên, dùng transaction và locking/version theo quy tắc domain.
4. Với quyền chia sẻ hoặc tenant membership, kiểm tra tính hợp lệ tại thời điểm thực thi, không tin cache quá hạn.
5. Không coi một existsBy... trước transaction là bằng chứng vĩnh viễn cho mọi hành động sau đó.

Ví dụ SQL minh họa:

~~~sql
UPDATE demo_documents
SET title = :new_title
WHERE id = :document_id
  AND owner_username = :authenticated_username;
~~~

Nếu update count = 0, không cấp phép coi như thành công. Trong production, query có thể còn cần tenant_id, trạng thái DRAFT và version/lock column. SQL minh họa không phải một lời hứa rằng mọi loại race đã được giải quyết nếu thiếu isolation hoặc điều kiện khác.

### Cần cẩn trọng với quyền trong cache

Một cache dùng key documentId và lưu DocumentView mà không xét tenant/owner có thể vô tình trả dữ liệu của người dùng khác. Nên cache dữ liệu theo phạm vi bảo mật hoặc cache record nội bộ rồi luôn thực hiện authorization khi trả về caller. Không cache kết quả "hasAccess = true" vô thời hạn khi role/ownership có thể thay đổi.

## 10. Đa tenant: username không phải ranh giới đủ mạnh

Trong SaaS, có thể có hai user cùng tên "alice" thuộc tenant T1 và T2, hoặc một user có quyền ở nhiều tenant khác nhau. Policy chỉ so sánh ownerUsername có thể nhầm quyền nếu dữ liệu không xác định tenant.

Một mô hình an toàn hơn:

~~~text
Caller: userId=U101, activeTenantId=T1
Document 101: ownerId=U101, tenantId=T1  -> có thể cho phép
Document 102: ownerId=U101, tenantId=T2  -> phải kiểm tra membership/quyền ở T2
Document 103: ownerId=U202, tenantId=T1  -> cần sharing/role cụ thể
~~~

Dùng identity provider/database xác minh userId và tenant memberships. Nếu request có X-Tenant hoặc /tenants/{tenantId}, đó chỉ là **tenant được yêu cầu**, không phải bằng chứng user có quyền trong tenant ấy. Service kiểm tra membership và authority theo tenant bằng nguồn dữ liệu đáng tin.

Một truy vấn điển hình:

~~~sql
SELECT id, owner_user_id, tenant_id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :authorized_tenant_id
  AND (
      owner_user_id = :authenticated_user_id
      OR EXISTS (
          SELECT 1
          FROM document_shares
          WHERE document_shares.document_id = documents.id
            AND document_shares.grantee_user_id =
                :authenticated_user_id
      )
  );
~~~

Đây là **SQL thiết kế minh họa**; schema document_shares và các class tương ứng không có trong project demo. Không copy vào H2 demo mà thiếu bảng. Production cần index, query plan, constraints và review quyền share.

### Không trộn quyền "admin của tenant" với "admin toàn hệ thống"

Một người có ROLE_ADMIN ở tenant A không mặc định được đọc tài liệu tenant B. Thiết kế principal/authorities nên thể hiện phạm vi quyền, ví dụ role ở tenant, permission trên resource hoặc ACL. Đừng dùng hasRole("ADMIN") toàn cục như một shortcut trong ứng dụng multi-tenant nếu quyền admin thực sự chỉ cục bộ.

## 11. Khi tài nguyên không tồn tại hoặc không có quyền: 403 hay 404?

Hai cách phản hồi phổ biến:

- **403 Forbidden:** đã biết người gọi được xác thực nhưng không có quyền với object. Dễ chẩn đoán, rõ semantics.
- **404 Not Found:** có thể dùng để không tiết lộ object có tồn tại với user không được phép hay không; đặc biệt trong API tài liệu riêng tư.

Cả hai đều có thể hợp lệ tùy sản phẩm. Điều quan trọng: **không trả body chứa title/owner, stack trace, file metadata hoặc thông báo khác giúp suy ra nội dung tài liệu** khi đã từ chối.

Không coi 404 là biện pháp bảo mật nếu bên cạnh đó một endpoint search/export/preview vẫn trả dữ liệu. Đừng thay AccessDeniedException thành 404 nhưng bỏ kiểm tra quyền.

Khi policy cần xác định có quyền trước khi cho truy cập, có thể dùng cùng một owner-scoped query: nếu không tìm thấy trong phạm vi caller, trả một thông báo thống nhất mà không xác nhận bản ghi tồn tại hay không.

### Rủi ro enumeration

Nếu ID tuần tự và API phản hồi khác nhau rõ rệt giữa ID có thật/không có thật (mã status, timing, response size), attacker có thể dò danh sách tài liệu. Cần định nghĩa response contract nhất quán và rate limiting/monitoring phù hợp. Tuy nhiên biện pháp chống enumeration **không thể thay authorization trên object**.

## 12. Gắn quyền vào các tác vụ ngoài HTTP

HTTP authorization chỉ chạy khi request đi vào SecurityFilterChain có rule tương ứng. Service có thể được gọi trực tiếp từ:

- Scheduled jobs;
- Message consumers;
- Batch processors;
- GraphQL resolvers hoặc gRPC handlers có authentication riêng;
- Background event listeners;
- Service khác trong cùng JVM.

@PreAuthorize trên Spring-managed service bean giúp chặn các lời gọi **qua proxy**, nhưng cần Authentication rõ ràng trong SecurityContext. Với job hệ thống không có browser session, không nên tạo sẵn một Authentication có mọi quyền chỉ để vượt policy. Nên tạo **service identity** có quyền tối thiểu, use case rõ và audit được, hoặc API hệ thống chuyên biệt có chính sách riêng.

SecurityContextHolder thường gắn với thread; @Async hoặc executor có thể không kế thừa context. Có thể dùng DelegatingSecurityContextAsyncTaskExecutor hay cơ chế truyền security context thích hợp, nhưng phải xác định ai được ủy quyền và lifetime của context. Việc thiếu Authentication nên **fail closed**, không tự coi background code đáng tin và bỏ quyền.

Nếu controller hoặc consumer gọi repository trực tiếp mà không qua service được bảo vệ, method security không cứu được. Cần kiến trúc module boundaries và kiểm thử mọi entrypoint.

## 13. Test matrix chống IDOR/BOLA cho ứng dụng thật

Một bộ kiểm thử chỉ có "alice truy cập tài liệu 101 thành công" là chưa đủ. Cần đặt mục tiêu phát hiện user hợp lệ vượt quyền:

| Actor | Hành động | Tài nguyên | Kỳ vọng |
| --- | --- | --- | --- |
| anonymous | GET | Alice doc 101 | 401/challenge |
| alice | GET | Alice doc 101 | Cho phép |
| alice | GET | Bob doc 102 | Từ chối |
| bob | GET | Bob doc 102 | Cho phép |
| bob | PUT | Alice doc 101 | Từ chối và DB không thay |
| admin | GET | Alice doc 101 | Chỉ cho phép nếu policy định nghĩa |
| admin | PUT | Alice doc 101 | Từ chối nếu policy không cấp quyền |
| alice | GET | ID không tồn tại | Không lộ dữ liệu |
| alice | GET | ID có thật tenant khác | Từ chối, không tiết lộ tenant |
| alice | GET list/search | owner=bob | Không thấy dữ liệu Bob |
| alice | POST bulk export | IDs gồm cả Alice và Bob | Không xuất dữ liệu Bob |
| alice | GET download | File của Bob | Không trả file/presigned URL |
| alice | PUT body | owner=admin | Không thể tự chuyển owner |
| alice | GET | Chuỗi ID format khác/encoded | Không bypass route/policy |
| alice | call service trực tiếp | Bob doc 102 | AccessDeniedException |

Cách kiểm tra hiệu quả:

1. **Positive case**: user được quyền thực sự thành công.
2. **Negative cross-user case**: user cùng ROLE_USER nhưng khác owner bị chặn.
3. **Integrity check**: sau PUT/DELETE bị từ chối, database không thay đổi.
4. **Tenant boundary**: cùng user name nhưng khác tenant không thể truy cập.
5. **Bulk list/export**: không lọt item nào ngoài phạm vi được phép.
6. **Alternate endpoint**: preview, download, export, thumbnail, soft-delete, version history, comments, attachments.
7. **Direct service test**: method security không chỉ do HTTP rule từ chối.
8. **Concurrent ownership change**: xem lock/transaction/query có chặn race quan trọng.
9. **Log/monitoring**: các lần bị từ chối không làm lộ raw token hoặc dữ liệu riêng tư.

Khi cần test production database semantics, dùng integration test với container DB (như Testcontainers) và các transaction đồng thời. H2 chỉ là nền tảng nhẹ để minh họa Spring MVC/Spring Security/JPA, không chứng minh đầy đủ isolation/concurrency cho database production.

## 14. Các lỗi thực tế thường gặp

### Lỗi 1 — Đã có hasRole("USER") nên nghĩ mọi tài liệu an toàn

ROLE_USER kiểm tra nhóm quyền chung, không kiểm tra tài liệu 102 của Bob. Thêm object policy theo owner/tenant và test một user có cùng role truy cập ID của user khác.

### Lỗi 2 — So sánh owner trong URL với username login

Nếu URL /users/alice/documents/102, attacker có thể giữ alice trong path nhưng đặt documentId=102 của Bob. Phải tra quan hệ giữa document và owner từ database; đừng tin path user là sự thật về record.

### Lỗi 3 — Dùng request body ownerUsername để cấp quyền

Client tự gửi ownerUsername=alice. So sánh trường này với authentication.name vẫn không xác minh record owner. Chỉ lấy owner từ repository/ACL tin cậy.

### Lỗi 4 — Ngẫu nhiên hóa ID và coi như đã sửa IDOR

UUID khó đoán không thay quyền cấp đối tượng. ID có thể lộ qua link, log hoặc API khác. Vẫn cần object authorization.

### Lỗi 5 — Chỉ check một item rồi xuất cả danh sách

Bulk request chứa IDs [101,102]. Nếu code check owner của 101 rồi repository.findAllById(...) cho cả hai, Bob document có thể bị export. Áp dụng predicate cho **tất cả tài liệu**, hoặc query trực tiếp danh sách trong phạm vi owner/tenant.

### Lỗi 6 — Chỉ test GET, quên PUT/DELETE

RBAC có thể vô tình áp cùng quyền đọc cho hành động xóa. Cần policy theo method/hành động, test không chỉ status mà cả database state.

### Lỗi 7 — Controller bỏ qua DocumentService

Dù @PreAuthorize nằm ở service, một controller dùng repository.findById rồi trả entity đã bypass service. Chặn đường truy cập repository trực tiếp từ controller và review dependency graph/use cases.

### Lỗi 8 — Spring AOP self-invocation

Service gọi this.readSensitive() trong cùng class có thể bypass proxy @PreAuthorize. Bảo vệ public entrypoint hoặc tách protected service bean riêng, thêm test.

### Lỗi 9 — AnonymousAuthenticationToken được hiểu nhầm là login thật

isAuthenticated() của anonymous token có thể true theo implementation. Trong policy tùy biến phải phân biệt anonymous với authenticated user thực sự; có thể sử dụng expression isAuthenticated() hoặc kiểm tra token type rõ.

### Lỗi 10 — Mất CSRF rồi tưởng owner check đã thành công

POST/PUT với browser cookie có thể bị CsrfFilter chặn 403 trước service. Test quyền sở hữu trên method unsafe phải gửi CSRF hợp lệ để chứng minh đúng layer từ chối.

### Lỗi 11 — Admin toàn cục trong SaaS multi-tenant

hasRole('ADMIN') không có scope tenant làm admin ở T1 xem T2. Dùng tenant-specific permission, tenant membership và data scoping.

### Lỗi 12 — Quyền thay đổi giữa policy và truy vấn

existsByIdAndOwner... trước transaction không phải proof vĩnh viễn. Dùng owner-scoped query, conditional update và version/lock theo nghiệp vụ.

### Lỗi 13 — Trả 403 nhưng log chứa bản ghi của người khác

Không log full DocumentEntity, attachment, customer PII hoặc JWT trong access denied handler. Audit chỉ những metadata cần thiết, quyền truy cập log hạn chế.

### Lỗi 14 — Lấy principal name sai sau đổi identity provider

JWT getName có thể là sub thay vì username. Nếu database lưu username và policy so sánh với subject khác, user hợp lệ có thể bị từ chối hoặc ánh xạ nhầm. Dùng internal stable user ID.

### Lỗi 15 — Client gửi tenantId tùy ý

Header X-Tenant hoặc path /tenants/T2 chỉ là tenant yêu cầu. Phải kiểm tra membership của caller và scope trong database; không xem header do client đặt là authority.

### Lỗi 16 — Chỉ dùng @PostAuthorize sau khi đã gửi side effect

Nếu method sửa dữ liệu hoặc gọi external system rồi mới đánh giá returnObject.owner, từ chối có thể quá muộn. Ưu tiên kiểm tra trước khi thao tác và ràng buộc DB/transaction phù hợp.

## 15. Checklist triển khai production

1. **Xác định mọi loại tài nguyên nhạy cảm:** documents, invoices, orders, files, messages, images, comments, exports.
2. **Liệt kê mọi action:** read, create, update, delete, download, share, transfer, approve, export.
3. **Định nghĩa policy trên object:** owner, tenant, status, share permission, admin scope theo đúng yêu cầu.
4. **Xác thực caller bằng nguồn tin cậy:** SecurityContext/validated claims, không tin userId/role tự khai từ request.
5. **Dùng immutable userId và tenantId** trong hệ thống thật, tránh so username có thể đổi hoặc không unique toàn cục.
6. **Bảo vệ HTTP layer:** authentication, method/path matcher, deny-by-default, CSRF khi credentials dựa vào cookie.
7. **Bảo vệ service use cases:** @EnableMethodSecurity + @PreAuthorize hoặc policy service, không chỉ role USER.
8. **Áp query scoping ở repository** với owner/tenant, tránh trả record trước rồi kiểm tra ở frontend.
9. **Không cho mass assignment** lên owner/tenant/admin/state nhạy cảm qua DTO update.
10. **Kết hợp locking/version/isolation** cho thay đổi quyền và dữ liệu nhạy cảm.
11. **Bảo vệ mọi access path:** detail, list, export, download, thumbnails, attachments, search, GraphQL, batch.
12. **Thiết kế API phản hồi an toàn:** 403/404 nhất quán, không tiết lộ owner/title/tồn tại của tài liệu trái quyền.
13. **Kiểm thử cross-user/cross-tenant** với cùng role, không chỉ positive tests.
14. **Kiểm thử dữ liệu không bị sửa** sau request 403, không chỉ dựa vào status.
15. **Kiểm thử service qua Spring proxy** và tránh self-invocation/repository bypass.
16. **Xác nhận admin exception có chủ đích**, có audit và phạm vi tenant/organization.
17. **Kiểm thử quyền bị thu hồi, transfer ownership và concurrency**, không giữ cached access vô hạn.
18. **Giám sát hành vi dò ID**, rate limiting và anomaly detection thích hợp, nhưng không thay object authorization.
19. **Bảo vệ log/cache/backup**, không để tài liệu nhạy cảm đi qua các kênh ít bảo vệ hơn API chính.
20. **Review policy khi thêm endpoint hoặc schema mới**, coi đó là thay đổi bảo mật bắt buộc kiểm thử hồi quy.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Alice và Bob đều có ROLE_USER. Nếu SecurityFilterChain dùng hasRole("USER"), Alice đã chắc chắn bị chặn khi truy cập document của Bob chưa?

**Đáp án:** chưa. Role USER cho phép dùng chức năng, không xác nhận owner của bản ghi. Service/repository phải kiểm tra quyền trên object.

**Câu 2.** Vì sao đổi /api/documents/101 thành /api/documents/102 có thể gây IDOR dù Alice đăng nhập hợp lệ?

**Đáp án:** cả hai request có cùng Authentication. Nếu backend chỉ lấy ID và repository.findById mà không xác minh record 102 thuộc ai, dữ liệu của Bob có thể được trả cho Alice.

**Câu 3.** Dùng UUID thay cho ID tuần tự có đủ không?

**Đáp án:** không. UUID giảm khả năng đoán nhưng không thay authorization; ID có thể bị rò rỉ hoặc được chia sẻ ngoài ý định.

**Câu 4.** Có thể dùng ownerUsername do client gửi trong JSON để kiểm tra quyền không?

**Đáp án:** không như bằng chứng duy nhất. Client có thể giả mạo; owner thực phải lấy từ database/ACL, caller từ Authentication đã xác minh.

**Câu 5.** ADMIN có nên tự động sửa mọi tài liệu không?

**Đáp án:** không mặc định. Mỗi sản phẩm cần policy cụ thể; ví dụ bài học cho ADMIN đọc nhưng không sửa document của người khác.

**Câu 6.** Vì sao @PreAuthorize trên service có ích hơn chỉ đặt ở controller?

**Đáp án:** nhiều entrypoint có thể gọi cùng service qua Spring proxy. Policy ở service gần nghiệp vụ hơn và không phụ thuộc duy nhất vào một URL.

**Câu 7.** Nếu service gọi protected method trong cùng bean bằng this.method(), policy có luôn chạy không?

**Đáp án:** không. Với Spring AOP proxy, self-invocation thường không đi qua interceptor; phải bảo vệ public entrypoint hoặc tách bean.

**Câu 8.** Khi Alice gọi PUT tài liệu của Bob và nhận 403, đã chứng minh không có IDOR chưa?

**Đáp án:** chưa đủ nếu 403 xuất phát từ thiếu CSRF token. Phải gửi CSRF hợp lệ khi test quyền service và kiểm tra database không thay đổi.

**Câu 9.** Khi canRead check owner ở T1 nhưng T2 transaction khác chuyển owner trước lúc read, cần làm gì?

**Đáp án:** giảm TOCTOU bằng truy vấn gắn owner/tenant tại thời điểm lấy dữ liệu, transaction/locking hoặc conditional update đúng use case.

**Câu 10.** Vì sao GET /api/documents?owner=bob vẫn nguy hiểm nếu chỉ kiểm tra role?

**Đáp án:** query owner do client chọn. Backend cần lọc theo caller/tenant đã được xác minh, không tin query owner như quyền truy cập.

**Câu 11.** App multi-tenant có user "alice" tại cả T1/T2. Chỉ so ownerUsername có đủ không?

**Đáp án:** không. Cần internal userId và tenantId/membership rõ để tránh truy cập chéo tenant.

**Câu 12.** Cần kiểm tra gì ở bulk export gồm ID của Alice và Bob?

**Đáp án:** mọi item được xuất phải thuộc phạm vi caller có quyền, không chỉ item đầu. Không cho export silently chứa dữ liệu Bob nếu caller chỉ được phép xem Alice.

## Kết luận

**Role cho biết người dùng thuộc nhóm quyền nào; ownership cho biết người dùng có quyền trên bản ghi cụ thể nào.** Khi API chỉ kiểm tra ROLE_USER hoặc authenticated() rồi truy cập tài liệu theo ID do client chọn, lỗi IDOR/BOLA có thể xảy ra dù login và Spring Security HTTP rules đều hoạt động đúng.

Để phòng ngừa, cần đưa **object-level authorization** vào service/policy, lấy caller từ Authentication đã xác minh, lấy owner/tenant từ database, và ràng buộc truy vấn thực tế theo phạm vi được phép. Không coi ID bí mật, header tự khai, kiểm tra frontend hoặc 403 do CSRF là một phép chứng minh ownership.

Hãy kiểm thử **người có cùng role nhưng khác owner**, các hành động ghi/xóa, danh sách/export/download, tenant boundary, truy cập service trực tiếp và tình huống cập nhật đồng thời. Một cơ chế bảo mật hiệu quả phải từ chối sai người **trước khi bất kỳ dữ liệu riêng tư nào được trả ra hoặc bị thay đổi**.