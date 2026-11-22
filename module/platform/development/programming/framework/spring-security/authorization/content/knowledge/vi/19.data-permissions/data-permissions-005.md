# Chặn thay đổi `ownerId`, `tenantId` và trường nhạy cảm do mass assignment trong Spring Security

## 1. Vấn đề: người dùng chỉ được sửa tiêu đề nhưng lại gửi cả `ownerId`

Giả sử hệ thống lưu một tài liệu:

```json
{
  "id": 11,
  "ownerId": "u-alice",
  "tenantId": "T1",
  "title": "Kế hoạch quý",
  "description": "Bản nháp",
  "state": "DRAFT",
  "sensitivity": "RESTRICTED",
  "version": 1
}
```

Chức năng **Sửa nội dung** cho phép `alice` cập nhật đúng hai trường `title` và `description`. Nhưng một client có thể tự gửi thêm:

```json
{
  "title": "Kế hoạch đã sửa",
  "description": "Nội dung hợp lệ",
  "ownerId": "u-bob",
  "tenantId": "T2",
  "state": "APPROVED",
  "sensitivity": "INTERNAL",
  "version": 999,
  "isAdmin": true
}
```

Nếu controller deserialize toàn bộ JSON thành entity rồi gọi `repository.save(...)` hoặc `BeanUtils.copyProperties(...)` quá rộng, **các thuộc tính không được phép sửa có thể bị ghi đè**. Hậu quả gồm chuyển quyền sở hữu, chuyển tenant, tự duyệt hồ sơ, hạ độ nhạy của dữ liệu, giả mạo thông tin audit hoặc nâng quyền.

Lỗi này được gọi là **mass assignment**, **over-posting** hoặc **unsafe object binding**: framework tự động ánh xạ đầu vào không đáng tin vào các thuộc tính của object nội bộ mà không giới hạn theo trường hợp sử dụng.

Bài học thuộc nhóm **Quyền trên dữ liệu** của Spring Security authorization, với trọng tâm **chặn thay đổi `ownerId`, `tenantId` và các trường nhạy cảm**. Ta sẽ đi từ mô hình tấn công, cách giới hạn dữ liệu nhận vào, thiết kế dịch vụ bảo mật, đến ví dụ Spring Boot/Java 17 có kiểm thử HTTP thật bằng `MockMvc`.

Sau bài này, bạn có thể:

1. Giải thích vì sao authentication và authority **không tự chặn mass assignment**.
2. Phân loại trường **client được sửa** và **server phải quản lý**.
3. Thiết kế **DTO allowlist** và ánh xạ tường minh thay cho bind entity.
4. Hiểu khác biệt giữa JSON `@RequestBody` (Jackson) và form `@ModelAttribute` (`WebDataBinder`).
5. Đặt kiểm tra `ownerId`, `tenantId`, trạng thái và quyền ở **service**, dùng identity đáng tin cậy.
6. Cấu hình reject unknown JSON fields để phát hiện payload cố tình gửi thêm trường.
7. Chạy demo Java 17+ / Spring Boot 3.5.x và integration test các ca allow, deny, cross-tenant, unknown fields, approved state và CSRF.
8. Bảo vệ riêng workflow thay owner, chuyển tenant, phê duyệt, admin và thao tác PATCH.
9. Tránh lỗi nested binding, generic mappers, ORM merge, cache và thao tác đồng thời.

**Quy tắc nền:** Client chỉ được gửi **dữ liệu mà use case chủ động cho sửa**. Chủ sở hữu, tenant, quyền, trạng thái phê duyệt, audit và version đến từ **nguồn server đáng tin**, được thay đổi chỉ qua những workflow có policy riêng.

## 2. Mass assignment khác BOLA/IDOR, nhưng thường xuất hiện cùng nhau

**Mass assignment:** client gửi thêm field và object binding ghi nó vào trạng thái nội bộ.

**BOLA/IDOR (Broken Object Level Authorization):** client thay ID trên URL/request để truy cập hoặc sửa **đối tượng không thuộc quyền**.

Hai lỗi có thể kết hợp:

```text
PUT /api/documents/11
Authorization: token của bob

{
  "title": "Đã chiếm",
  "ownerId": "u-bob",
  "tenantId": "T1"
}
```

Nếu chỉ kiểm tra `hasAuthority('document:edit')` rồi **bind payload vào entity trước khi kiểm tra owner**, bob có thể biến bản ghi của alice thành của mình. Kể cả khi `ownerId` trong payload bị bỏ qua, vẫn phải kiểm tra bob **có quyền sửa tài liệu 11 hay không**.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Người gọi là ai? | JWT/session/Basic đã xác minh |
| Function-level authorization | Có năng lực sửa tài liệu không? | `document:edit` |
| Object-level authorization | Được sửa **tài liệu cụ thể** này không? | User, tenant, owner, ACL và trạng thái |
| Field-level write authorization | Được sửa **thuộc tính nào** của tài liệu? | `title`, `description` |
| State transition policy | Được chuyển trạng thái/owner/tenant không? | `DRAFT -> APPROVED`, chuyển sở hữu |
| Data integrity | Dữ liệu còn hợp lệ khi ghi không? | Validation, version, điều kiện UPDATE |

**Không lớp nào thay thế tất cả lớp còn lại.** `@PreAuthorize("hasRole('USER')")` không ngăn JSON chứa `tenantId` nếu code vẫn copy mọi field. Ngược lại, DTO allowlist không tự ngăn bob sửa document của alice qua ID khác.

## 3. Phân loại trường theo quyền ghi

Một thực hành hữu ích là lập **write-policy matrix** theo từng endpoint/use case:

| Trường | API sửa nội dung | Nguồn giá trị đúng | Cách thay đổi hợp lệ |
| --- | --- | --- | --- |
| `title` | Cho phép | JSON đã validation | `updateContent` |
| `description` | Cho phép | JSON đã validation | `updateContent` |
| `id` | Không cho phép | Định danh từ URL, lookup DB | Không thay sau khi tạo |
| `ownerId` | Không cho phép | DB + actor/policy | `transferOwnership` riêng |
| `tenantId` | Không cho phép | DB + server identity | Quy trình chuyển tenant riêng |
| `state` | Không cho phép | Workflow server | `approve`/`reject` riêng |
| `sensitivity` | Không cho phép | Policy phân loại dữ liệu | `changeClassification` riêng |
| `role`, `authorities`, `isAdmin` | Không cho phép | Identity/permission management | Quản trị danh tính riêng |
| `createdBy`, `createdAt` | Không cho phép | Server auditing | Ghi một lần khi tạo |
| `updatedBy`, `updatedAt` | Không cho phép | Server auditing | Ghi tự động khi cập nhật |
| `version` | Không sửa tùy ý | DB/optimistic locking | DB tăng hoặc kiểm tra precondition |
| `balance`, `approvedAmount`, `price` | Tùy use case | Business rules, nguồn được duyệt | API/domain command riêng |

Lưu ý `version` có thể được client **gửi làm precondition** (`If-Match`/expectedVersion) để chống lost update, nhưng nó **không được dùng để gán trực tiếp** vào entity. `expectedVersion` trong request khác với quyền **đặt** version.

Tương tự, có thể có nghiệp vụ cho người quản lý đổi `ownerId`. Điều đó không làm `ownerId` trở thành trường được sửa trong **mọi** API. Hãy tách chức năng và dùng quyền riêng.

### 3.1. Cảnh báo với field mới được thêm trong tương lai

Giả sử hôm nay entity chỉ có `title`, `description`, nhưng tháng sau thêm `publicAccess` hoặc `reviewedBy`. Nếu controller bind **toàn entity** hoặc mapper copy tất cả property mặc định, field mới có thể tự nhiên trở thành một trường client sửa được mà không ai chủ ý thiết kế quyền.

Với **DTO chỉ có trường được cho phép**, thêm field vào entity **không tự mở rộng API ghi**. Đây là lý do allowlist là lựa chọn bền vững hơn blacklist.

## 4. Mẫu code không an toàn: bind thẳng entity

```java
// MẢNH CODE CỐ TÌNH KHÔNG AN TOÀN; không dùng trong production.

@PutMapping("/api/documents/{id}")
public Document update(
        @PathVariable Long id,
        @RequestBody Document incoming) {

    Document existing = repository.findById(id).orElseThrow();

    // Tùy mapper/cấu hình, có thể ghi cả field nhạy cảm.
    BeanUtils.copyProperties(incoming, existing);

    return repository.save(existing);
}
```

Nếu class `Document` có setter cho `ownerId`, `tenantId`, `state`, `sensitivity` hoặc `isAdmin`, việc copy thiếu allowlist có thể ghi đè chúng. Đây là **mảnh minh họa lỗ hổng**, không phải chương trình runnable.

Một biến thể cũng nguy hiểm:

```java
// KHÔNG an toàn: JSON có thể điều khiển nhiều field entity.
@PutMapping("/api/documents/{id}")
public Document replace(
        @PathVariable Long id,
        @RequestBody Document document) {

    return repository.save(document);
}
```

Nó còn có thể bỏ qua việc so ID trên URL với ID trong JSON, hoặc biến `save` thành create/update ngoài dự kiến. Ngay cả khi JPA/Hibernate có `@Column(updatable=false)` ở vài trường, **không được coi đó là object-level/field-level authorization**.

### 4.1. Các đường vào dễ bị bỏ quên

Mass assignment có thể xảy ra qua:

- JSON API `@RequestBody` dùng Jackson deserialize vào entity.
- Form-urlencoded/multipart và query string dùng `@ModelAttribute`.
- `Map<String,Object>` sau đó `ObjectMapper.convertValue(...)` sang entity.
- Generic update service hoặc `BeanUtils.copyProperties`, reflection mapper.
- JSON Merge Patch / JSON Patch cho phép sửa path tùy ý.
- GraphQL input type tái sử dụng entity; message/event consumer nhận payload ngoài ranh giới tin cậy.
- Nested properties như `document.owner.id`, `user.roles[0]`, `account.isAdmin`, `organization.tenantId`.
- ORM update/merge toàn bộ detached entity nhận từ client.

Nguyên nhân không nằm ở một annotation cụ thể; nguyên nhân là **dữ liệu không đáng tin được phép quyết định các thuộc tính vốn thuộc quyền server**.

## 5. Kiến trúc an toàn: DTO allowlist -> service policy -> cập nhật có kiểm soát

```text
Client JSON
    |
    v
@RestController
    |
    +--> Jackson deserialize vào UpdateDocumentRequest
    |       title, description
    |       Không có ownerId/tenantId/state/role
    |
    +--> @Valid / validation cấu trúc
    |
    v
DocumentService (Spring-managed bean)
    |
    +--> @PreAuthorize("hasAuthority('document:edit')")
    +--> Lấy Authentication đáng tin từ SecurityContext
    +--> Tìm userId/tenantId từ server directory
    +--> Tải bản ghi thật theo id
    +--> Kiểm tra tenant + owner + state
    |
    v
DocumentStore / DB update
    |
    +--> Gán đúng title, description
    +--> GIỮ NGUYÊN ownerId, tenantId, state, sensitivity
    +--> Tăng version/audit do server
    |
    v
Response DTO (chỉ dữ liệu được phép trả)
```

**Hai lớp allowlist khác nhau:**

1. **Allowlist cấu trúc request:** chỉ cho phép client khai các trường hợp lệ của command. Nó bảo vệ khỏi việc API âm thầm trở thành universal entity updater.
2. **Allowlist nghiệp vụ ở service:** chỉ gán những trường có trong contract. Dù mapper cấu hình khác hoặc endpoint khác gọi service, quyền vẫn được áp dụng.

**Các giá trị chủ thể và tenant do server xác định:** Không truyền `actorUserId` hoặc `trustedTenant` từ JSON rồi dùng như identity. Với JWT/OIDC phải xác minh chữ ký/issuer/audience và ánh xạ `sub` tới user/tenant đúng chính sách.

### 5.1. Dùng DTO request bất biến

```java
public record UpdateDocumentRequest(
    @NotBlank @Size(max = 120) String title,
    @NotBlank @Size(max = 1000) String description
) {}
```

DTO không có `ownerId`, `tenantId`, `state`, `sensitivity`, `role` hay `isAdmin`. Java record có constructor khai báo đúng dữ liệu được nhận và không có setter để client tác động phần còn lại.

**Không có nghĩa chỉ dùng DTO là đủ.** Nếu service lấy `id` không kiểm tra, một caller vẫn có thể sửa object của người khác; do đó cần object-level authorization.

### 5.2. Ánh xạ tường minh vào entity đã có

```java
// Ý tưởng cho service, giả định đã kiểm tra quyền và record hiện hữu.
Document changed = new Document(
    before.id(),            // Giữ ID
    before.ownerId(),       // Giữ owner từ DB
    before.tenantId(),      // Giữ tenant từ DB
    before.state(),         // Giữ trạng thái
    before.sensitivity(),   // Giữ độ nhạy
    request.title(),        // CHỈ dữ liệu client được sửa
    request.description(),  // CHỈ dữ liệu client được sửa
    before.version() + 1    // Server tăng version
);
```

Đây là mảnh code minh họa; chương trình đầy đủ ở mục 7. Cách xây dựng object mới từ state cũ và hai field được phép làm cho việc thay đổi quyền viết **rõ ràng khi review code**.

Trong JPA, có thể load managed entity rồi gọi **chỉ những setter cho phép** sau authorization. Không `merge` detached entity do client dựng nếu nó chứa nhiều trường hơn use case cho phép.

## 6. Spring MVC: `@RequestBody` khác `@ModelAttribute`

Đây là phần rất quan trọng để tránh áp dụng sai biện pháp bảo vệ.

### 6.1. JSON `@RequestBody` dùng Jackson

Ví dụ:

```java
@PutMapping("/api/documents/{id}")
public UpdateDocumentResponse replace(
        @PathVariable long id,
        @Valid @RequestBody UpdateDocumentRequest request) {
    return service.update(id, request);
}
```

Spring dùng `HttpMessageConverter`/Jackson để deserialize JSON thành DTO, sau đó validate. **`WebDataBinder.setAllowedFields(...)` không phải cơ chế allowlist JSON `@RequestBody`**; nó chủ yếu kiểm soát property binding của `@ModelAttribute`/form.

Với JSON, dùng DTO riêng, Jackson annotations khi thích hợp và **chỉ ánh xạ field được phép** trong service.

### 6.2. Form/query `@ModelAttribute` dùng `WebDataBinder`

Với form binding, Spring Framework khuyến cáo thiết kế object dành riêng cho đầu vào, dùng constructor binding hoặc giới hạn property binding bằng `allowedFields`.

```java
// MẢNH CODE controller cho form @ModelAttribute, không dùng để
// bảo vệ request JSON @RequestBody.
@InitBinder("documentForm")
void allowOnlyFormFields(WebDataBinder binder) {
    binder.setAllowedFields("title", "description");
}
```

Khi cần phát hiện payload chứa field bị suppression, inspect `BindingResult.getSuppressedFields()` và từ chối/log theo policy. Nếu chỉ suppress mà không báo lỗi, người dùng có thể nhận một phản hồi thành công trong khi field nhạy cảm bị bỏ qua; điều này an toàn hơn ghi nhầm nhưng gây khó chẩn đoán.

`DataBinder#setDisallowedFields` dùng **blacklist** dễ bỏ sót field mới hoặc nested path; Spring Framework khuyến cáo ưu tiên `allowedFields`/constructor binding. Đặc biệt `@ModelAttribute` có property path dạng `address.city`, `items[0].name`, `map[key]`; cẩn thận wildcard nếu không muốn mở nested field.

### 6.3. Validation không thay thế authorization

`@NotBlank`, `@Size`, `@Positive`, enum checking... chỉ xác nhận dữ liệu hợp lệ về hình thức. Chúng **không trả lời client có quyền thay `ownerId` không**. Một `tenantId = "T2"` có thể hoàn toàn hợp lệ về định dạng nhưng vẫn là giá trị không được phép sửa.

Tương tự, JSON schema có thể kiểm tra trường lạ và kiểu dữ liệu; vẫn cần policy ở service nếu field đó được phép với **một nhóm người dùng nhưng không phải nhóm khác**.

### 6.4. Từ chối unknown JSON fields là lớp hỗ trợ

Trong Spring Boot 3.x, Jackson thường bỏ qua JSON field không khai báo theo cấu hình mặc định của Boot. Để API demo này **phát hiện ngay** những field như `ownerId`, `tenantId`, bật:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Khi đó JSON gửi field không có trong DTO có thể nhận **HTTP 400** do deserialization thất bại. Đây là defense-in-depth tốt để phát hiện over-posting, nhưng:

- **Không sửa được DTO thiết kế sai.** Nếu `ownerId` đã được khai báo trong DTO và code gán nó, đây không phải *unknown field*; flag không cứu được.
- Nếu có `@JsonAnySetter`, alias hoặc ignore rules riêng, phải xét kết quả thực của cấu hình mapper.
- Tính tương thích API cần cân nhắc: reject unknown fields có thể làm client cũ/mới bị lỗi. Với hành động nhạy cảm, hợp đồng nghiêm ngặt có lợi, nhưng phải có versioning/test rõ.
- Không dựa vào flag này làm **lớp bảo mật duy nhất**. Service mapping vẫn phải allowlist ngay cả khi lenient JSON parsing được bật ở một endpoint khác.

### 6.5. `@JsonProperty(READ_ONLY)`, `@JsonIgnore` và ORM annotations

Có thể dùng Jackson `@JsonProperty(access = JsonProperty.Access.READ_ONLY)` để hạn chế deserialize một thuộc tính; hoặc `@JsonIgnore` để bỏ thuộc tính khỏi JSON binding. Nhưng đây là **hành vi serialization/deserialization**, không phải chính sách quyền nghiệp vụ: nó có thể bị bypass khi update bằng service khác, Mapper, form binding hoặc repository.

`@Column(updatable=false)` của JPA chỉ ảnh hưởng cách ORM phát sinh câu UPDATE cho một cột; nó không ngăn mọi lối cập nhật dữ liệu và có thể cản workflow chuyển quyền hợp pháp. `@CreatedBy`/`@LastModifiedBy` là auditing, không tự là authorization. Nên dùng chúng như defense-in-depth theo ngữ cảnh, không thay DTO và service policy.

## 7. Demo hoàn chỉnh Java 17+/Spring Boot 3.5.8

Demo tạo một endpoint HTTP `PUT /api/documents/{id}` chỉ cho phép cập nhật `title` và `description`. Dữ liệu `ownerId`, `tenantId`, `state`, `sensitivity` và `version` nằm phía server.

**Đặc tả an toàn:**

- Người dùng phải xác thực và có authority `document:edit`.
- Cần có hồ sơ user/tenant trong directory đáng tin do server quản lý.
- Chỉ chủ sở hữu **trong cùng tenant** được sửa tài liệu đang ở trạng thái `DRAFT`.
- Request DTO chỉ chứa `title`, `description` và được validation.
- Unknown JSON fields bị từ chối với HTTP 400.
- Dù client cố gửi `ownerId`, `tenantId`, `state`, `sensitivity`, `version`, những trường đó không được copy vào entity.
- Trả response DTO chỉ chứa thông tin phù hợp; không vô tình serialize toàn bộ entity.
- Bảo vệ CSRF của Spring Security **vẫn được bật**; tests dùng CSRF token.
- `ConcurrentHashMap.compute` giúp việc cập nhật một entry demo nguyên tử. Production cần DB transaction và concurrency policy.

### 7.1. Cấu trúc file

```text
safe-document-update/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SafeDocumentApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── Document.java
    │   │   ├── UpdateDocumentRequest.java
    │   │   ├── UpdateDocumentResponse.java
    │   │   ├── TrustedUserDirectory.java
    │   │   ├── DocumentStore.java
    │   │   ├── DocumentService.java
    │   │   └── DocumentController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── DocumentApiSecurityTest.java
```

### 7.2. Gradle và configuration

**`settings.gradle`:**

```groovy
rootProject.name = 'safe-document-update'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Trong Boot 3.5.x, key này điều khiển Jackson deserialization feature tương ứng. Nó giúp API **từ chối** field lạ, chứ không tự gắn chính sách quyền cho những field đã tồn tại trong DTO.

### 7.3. Spring Boot và Method Security

**`src/main/java/demo/SafeDocumentApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SafeDocumentApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeDocumentApplication.class, args);
    }
}
```

`@EnableMethodSecurity` là yêu cầu để `@PreAuthorize` trên service hoạt động. Chỉ thêm `spring-boot-starter-security` **không tự bật method-level security**.

### 7.4. HTTP Security: authentication và CSRF

**`src/main/java/demo/SecurityConfig.java`:**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.PUT, "/api/documents/*")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là demo có **HTTP Basic** để Spring Security filter chain có cơ chế authentication. Chưa định nghĩa user thật cho deployment thủ công; tests dùng `@WithMockUser`. Với production, thay bằng JWT/OIDC/session theo yêu cầu, không hardcode password trong code.

**Không disable CSRF chỉ để test dễ hơn.** Với ứng dụng dùng cookie/session, CSRF protection là quan trọng. MockMvc test dùng `.with(csrf())` cho PUT, và có ca test chứng minh thiếu token bị từ chối. Một API stateless bearer-only có threat model CSRF khác, nhưng cần đánh giá cụ thể trước khi thay mặc định.

### 7.5. Domain object với các trường cần bảo vệ

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(
        long id,
        String ownerId,
        String tenantId,
        State state,
        Sensitivity sensitivity,
        String title,
        String description,
        long version) {

    public enum State {
        DRAFT, APPROVED
    }

    public enum Sensitivity {
        INTERNAL, RESTRICTED
    }
}
```

Record bất biến giúp không có setter chung. Nhưng **bất biến không tự loại bỏ mass assignment** nếu bạn deserialize trực tiếp JSON vào record entity có đủ tám constructor parameters. Vì thế vẫn phải dùng request DTO chỉ hai field.

### 7.6. Request DTO chỉ cho sửa nội dung

**`src/main/java/demo/UpdateDocumentRequest.java`:**

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDocumentRequest(
        @NotBlank @Size(max = 120) String title,
        @NotBlank @Size(max = 1000) String description) {
}
```

**`src/main/java/demo/UpdateDocumentResponse.java`:**

```java
package demo;

public record UpdateDocumentResponse(
        long id,
        String title,
        String description,
        long version) {
}
```

Request và response **không bắt buộc giống entity**. Response chỉ có các trường người gọi cần nhận. Không để Jackson serialize entity có các field nhạy cảm rồi hy vọng endpoint filter security tự redaction.

### 7.7. Directory đáng tin từ server

**`src/main/java/demo/TrustedUserDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record Actor(String userId, String tenantId) {
}

@Component
public class TrustedUserDirectory {

    private final Map<String, Actor> accounts = Map.of(
        "alice", new Actor("u-alice", "T1"),
        "bob",   new Actor("u-bob", "T1"),
        "carol", new Actor("u-carol", "T2")
    );

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    public Actor require(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || resolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted identity");
        }

        Actor actor = accounts.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException("Unknown actor");
        }
        return actor;
    }
}
```

`Actor` là định danh nội bộ server, không phải DTO được client điền. `getName()` trong ví dụ ánh xạ tới một account duy nhất; với OIDC/JWT production, nên dùng `sub` ổn định cùng issuer/tenant theo mô hình identity thật.

Một user có `document:edit` không tự được quyền đổi tenant hoặc sửa mọi tài liệu. Quyền đó mới là điều kiện đầu tiên.

### 7.8. Repository in-memory chỉ cập nhật field được phép

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentStore {

    private final Map<Long, Document> data = new ConcurrentHashMap<>();

    public DocumentStore() {
        data.put(11L, new Document(
            11L, "u-alice", "T1",
            Document.State.DRAFT, Document.Sensitivity.RESTRICTED,
            "Alpha", "Alice draft", 1L
        ));
        data.put(12L, new Document(
            12L, "u-bob", "T1",
            Document.State.DRAFT, Document.Sensitivity.INTERNAL,
            "Beta", "Bob draft", 1L
        ));
        data.put(13L, new Document(
            13L, "u-carol", "T2",
            Document.State.DRAFT, Document.Sensitivity.RESTRICTED,
            "Gamma", "Carol draft", 1L
        ));
        data.put(14L, new Document(
            14L, "u-alice", "T1",
            Document.State.APPROVED, Document.Sensitivity.RESTRICTED,
            "Approved", "Locked content", 1L
        ));
    }

    public Document snapshot(long id) {
        return data.get(id);
    }

    public Document updateContent(
            long id,
            Actor actor,
            UpdateDocumentRequest request) {

        return data.compute(id, (key, before) -> {
            if (before == null) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document missing"
                );
            }

            if (!before.ownerId().equals(actor.userId())
                    || !before.tenantId().equals(actor.tenantId())) {
                throw new AccessDeniedException(
                    "Not owner or wrong tenant"
                );
            }

            if (before.state() != Document.State.DRAFT) {
                throw new AccessDeniedException(
                    "Only DRAFT can be edited"
                );
            }

            // Critical allowlist: giữ TẤT CẢ field nhạy cảm
            // từ bản ghi server, chỉ cập nhật hai trường nội dung.
            return new Document(
                before.id(),
                before.ownerId(),
                before.tenantId(),
                before.state(),
                before.sensitivity(),
                request.title(),
                request.description(),
                before.version() + 1
            );
        });
    }
}
```

Trong demo `ConcurrentHashMap.compute` áp dụng kiểm tra và update **cho cùng một key** trong một thao tác nguyên tử, hữu ích để tránh race đơn giản giữa hai lượt sửa. Nó **không phải** database transaction đa bảng; khi chuyển sang JPA/SQL, cần transaction, optimistic lock và conditional update đúng mô hình.

**Quan sát dòng quan trọng:** Không có `request.ownerId()`, `request.tenantId()`, `request.state()`, `request.sensitivity()` hay `request.version()` vì request DTO **không có** những thuộc tính ấy. Tất cả được giữ từ `before` (bản ghi server).

### 7.9. Service có quyền chức năng và identity check

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentStore store;
    private final TrustedUserDirectory directory;

    public DocumentService(
            DocumentStore store,
            TrustedUserDirectory directory) {
        this.store = store;
        this.directory = directory;
    }

    @PreAuthorize("hasAuthority('document:edit')")
    public UpdateDocumentResponse update(
            long id,
            UpdateDocumentRequest request) {

        var authentication = SecurityContextHolder.getContext()
            .getAuthentication();

        Actor actor = directory.require(authentication);
        Document saved = store.updateContent(id, actor, request);

        return new UpdateDocumentResponse(
            saved.id(), saved.title(),
            saved.description(), saved.version()
        );
    }
}
```

`@PreAuthorize` kiểm tra authority **trước khi chạy body** khi service được gọi qua Spring proxy. `directory.require` kiểm tra identity đáng tin; `DocumentStore` xác minh object-level authorization và chỉ cập nhật hai field. Ba cơ chế hỗ trợ nhau.

Trong production nên đưa rule owner/tenant/state vào domain service hoặc authorization policy phù hợp với repository và test mọi đường gọi, thay vì coi `DocumentStore` in-memory là một security boundary duy nhất.

### 7.10. Controller chỉ nhận command DTO

**`src/main/java/demo/DocumentController.java`:**

```java
package demo;

import jakarta.validation.Valid;

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

    @PutMapping("/{id}")
    public UpdateDocumentResponse replace(
            @PathVariable long id,
            @Valid @RequestBody UpdateDocumentRequest request) {
        return service.update(id, request);
    }
}
```

Controller **không nhận** `Document` entity làm `@RequestBody`, không có API generic `saveEverything`, không copy trường lạ. Người dùng muốn thay ownership phải dùng workflow riêng được kiểm tra quyền; không thể đưa `ownerId` vào API này.

## 8. Test HTTP với `MockMvc`: kiểm chứng bảo mật ở nhiều lớp

**`src/test/java/demo/DocumentApiSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DocumentApiSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentStore store;

    private static final String SAFE_JSON =
        "{\"title\":\"Updated\",\"description\":\"Allowed body\"}";

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void onlyEditableFieldsChange() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(11))
            .andExpect(jsonPath("$.title").value("Updated"))
            .andExpect(jsonPath("$.version").value(2))
            .andExpect(jsonPath("$.ownerId").doesNotExist())
            .andExpect(jsonPath("$.tenantId").doesNotExist());

        Document after = store.snapshot(11L);

        assertEquals(before.ownerId(), after.ownerId());
        assertEquals(before.tenantId(), after.tenantId());
        assertEquals(before.state(), after.state());
        assertEquals(before.sensitivity(), after.sensitivity());
        assertEquals(2L, after.version());
        assertEquals("Updated", after.title());
        assertEquals("Allowed body", after.description());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void rejectsOverpostingOfOwnerTenantAndSensitiveFields()
            throws Exception {

        Document before = store.snapshot(11L);

        String malicious = """
            {
              "title": "Attacker title",
              "description": "Modified by attacker",
              "ownerId": "u-bob",
              "tenantId": "T2",
              "state": "APPROVED",
              "sensitivity": "INTERNAL",
              "version": 999,
              "isAdmin": true
            }
            """;

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(malicious))
            .andExpect(status().isBadRequest());

        // Deserialization đã reject, không có update.
        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:edit")
    void rejectsEditingSomebodyElsesDocument() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:edit")
    void rejectsCrossTenantEdit() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void requiresEditAuthority() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void rejectsEditAfterApproval() throws Exception {
        Document before = store.snapshot(14L);

        mvc.perform(put("/api/documents/14")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(14L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void csrfProtectionStillApplies() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }
}
```

Chạy tại thư mục dự án:

```bash
./gradlew test
```

Trên Windows PowerShell:

```bash
.\gradlew.bat test
```

Nếu chưa có Wrapper, cần tạo từ Gradle tương thích hoặc dùng `gradle test` đã cài. Với cấu hình demo, **kỳ vọng bảy ca test đều pass**, mỗi test có ApplicationContext riêng sau khi test trước được đánh dấu dirty. Không đưa ra số milliseconds hoặc Gradle stdout giả vì build thực tế phụ thuộc môi trường.

### 8.1. Ma trận kết quả HTTP dự kiến

| User/điều kiện | Request | HTTP dự kiến | Bản ghi có bị thay? |
| --- | --- | ---: | --- |
| Alice có `document:edit` và là owner T1 | Chỉ `title`, `description` | `200` | Chỉ hai field; version tăng |
| Alice có `document:edit` | Gửi thêm `ownerId`, `tenantId`, `state`, `sensitivity`, `isAdmin` | `400` | Không |
| Bob có `document:edit` | Sửa document của alice | `403` | Không |
| Carol có `document:edit` nhưng thuộc T2 | Sửa document T1 của alice | `403` | Không |
| Alice chỉ có `document:read` | Sửa document của chính mình | `403` | Không |
| Alice có `document:edit` | Sửa bản ghi đã `APPROVED` | `403` | Không |
| Alice có `document:edit` | PUT không kèm CSRF token | `403` | Không |

Lưu ý HTTP status của lỗi authentication trong hệ thống thật còn phụ thuộc cơ chế entry point (Basic/Bearer/session), exception handling và tránh lộ sự tồn tại của object. Demo dùng `403` cho policy deny, `400` cho request JSON có field không thuộc DTO.

### 8.2. Kết quả quan trọng hơn mã HTTP

Sau một request cố gắng gán `ownerId = u-bob` và `tenantId = T2`, điều phải kiểm tra là **dữ liệu lưu thực** vẫn có:

```text
document 11:
  ownerId     = u-alice
  tenantId    = T1
  state       = DRAFT
  sensitivity = RESTRICTED
  version     = 1
```

Trong ca request hợp lệ, chỉ `title` và `description` thay đổi, còn `ownerId`, `tenantId`, `state`, `sensitivity` giữ nguyên và `version` do server tăng lên `2`.

**Không chỉ assert `HTTP 403`/`HTTP 400`.** Nếu hệ thống đã thay DB rồi mới ném exception, bạn vẫn có lỗ hổng. Phải readback state của bản ghi, kể cả sau lỗi validation, denied policy và transaction rollback.

## 9. Vì sao cách này hiệu quả dù Jackson bỏ qua unknown fields?

Hai cơ chế độc lập:

- **DTO allowlist**: request không có property `ownerId`, `tenantId` và service không có cách đọc chúng từ DTO. Nếu JSON parser bỏ qua unknown, những giá trị này cũng không được đưa vào domain update.
- **Strict unknown-field handling**: trong demo, parser báo lỗi `400` ngay khi JSON khai field không thuộc contract, giúp phát hiện tấn công/bug và không cập nhật gì.

Giả sử một endpoint khác không bật `FAIL_ON_UNKNOWN_PROPERTIES`: DTO và service mapping vẫn chặn được việc gán field ngoài allowlist. Ngược lại, một endpoint deserialize entity với `ownerId` có setter thì strict-unknown **không giúp** vì field đã được định nghĩa. Vì vậy **DTO + service policy là biện pháp chính**, strict parsing chỉ bổ trợ.

### Phép thử bạn nên có

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "ownerId": "u-attacker"
}
```

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "tenantId": "other-tenant",
  "state": "APPROVED"
}
```

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "role": "ADMIN",
  "authorities": ["ROLE_ADMIN"],
  "isAdmin": true
}
```

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "audit": {
    "createdBy": "attacker",
    "approvedBy": "attacker"
  }
}
```

Ở endpoint strict, cả bốn payload phải bị từ chối vì trường lạ. Với endpoint lenient, mọi trường lạ vẫn phải **không bao giờ được lưu**. Trường hợp nested object cần test riêng nếu request DTO có các cấu trúc lồng nhau.

## 10. Nếu cần chuyển owner hoặc tenant hợp lệ thì làm thế nào?

Không mở rộng generic `UpdateDocumentRequest` thành:

```java
// THIẾT KẾ NÊN TRÁNH:
record UpdateDocumentRequest(
    String title,
    String description,
    String ownerId,
    String tenantId,
    String state
) {}
```

Thay bằng **use case riêng**, ví dụ:

```text
PUT  /api/documents/{id}            -> sửa title/description
POST /api/documents/{id}/transfer    -> chuyển owner, quyền document:transfer
POST /api/documents/{id}/approve     -> duyệt, quyền document:approve
POST /api/documents/{id}/classify    -> đổi sensitivity, quyền document:classify
```

### 10.1. Lệnh chuyển owner

Command chuyên biệt:

```java
public record TransferOwnershipRequest(String newOwnerId) {
}
```

Mảnh service:

```java
// MẢNH CODE THIẾT KẾ, giả định repository/policy/transaction đã có.
@PreAuthorize("hasAuthority('document:transfer')")
@Transactional
public void transferOwner(
        long documentId,
        TransferOwnershipRequest request) {

    Document before = documentRepository.requireForUpdate(documentId);
    var actor = trustedDirectory.currentActor();

    transferPolicy.requireCanTransfer(
        actor, before, request.newOwnerId()
    );

    // Policy kiểm tra owner mới tồn tại và thuộc tenant hợp lệ.
    documentRepository.transferOwner(
        documentId, before.tenantId(), request.newOwnerId()
    );

    audit.recordOwnershipTransfer(
        actor.userId(), documentId,
        before.ownerId(), request.newOwnerId()
    );
}
```

Đây **không phải file demo runnable**; `documentRepository`, `trustedDirectory`, `transferPolicy`, `audit`, transaction và các method này là thành phần cần xây dựng trong sản phẩm.

**Quyền `document:transfer` không đủ nếu không kiểm tra target object.** Business policy phải xét actor, owner hiện tại, tenant, trạng thái, owner nhận chuyển, các hạn chế maker–checker và audit. Nếu owner mới ở tenant khác, có thể cần workflow migration riêng thay vì chỉ đổi `ownerId`.

### 10.2. Chuyển tenant nhạy cảm hơn thay owner

`tenantId` thường là **ranh giới bảo mật và partition dữ liệu**. Đổi tenant có thể ảnh hưởng:

- Membership và authority của người dùng.
- `ACL`/SID/object identity, khóa cache và document shares.
- Encryption key, data residency, file storage bucket.
- Foreign keys và quan hệ với project/customer ở tenant cũ.
- Index/unique constraints, audit trail, billing.
- Search indexes, events, analytics và các replica.

Vì vậy, **không** cho thay `tenantId` bằng một setter trong generic update. Hãy dùng migration/transfer workflow có kiểm tra, giao dịch hoặc saga phù hợp và giữ nguyên bất biến tenant sau mỗi bước.

### 10.3. Tự duyệt bằng cách gán state

Với hệ thống phê duyệt, `state = APPROVED` thường không phải một “field edit” thông thường. Nó là **transition nghiệp vụ** cần quyền `document:approve`, kiểm tra trạng thái trước, maker–checker, idempotency, audit và điều kiện transaction. Dùng method như `approveDocument(id)` thay vì đưa `state` vào DTO sửa nội dung.

## 11. PATCH và JSON Merge Patch: bề mặt tấn công khác

Một API PATCH có thể nhận **path** do client điều khiển:

```json
[
  {"op": "replace", "path": "/title", "value": "New title"},
  {"op": "replace", "path": "/ownerId", "value": "u-attacker"}
]
```

Với JSON Patch (RFC 6902), đừng áp toàn bộ patch trực tiếp lên entity rồi save. Hãy kiểm tra **danh sách path được phép** và operation hợp lệ trước khi áp dụng.

Ví dụ mảnh thiết kế:

```java
private static final Set<String> EDITABLE_PATHS =
    Set.of("/title", "/description");

// MẢNH CODE minh họa; cần validate op/value, JSON Pointer,
// duplicates và nested path theo thư viện patch thực tế.
if (!EDITABLE_PATHS.contains(operation.getPath())) {
    throw new AccessDeniedException(
        "Forbidden patch path"
    );
}
```

Lưu ý JSON Pointer có escaping `~0` và `~1`, unicode, index và path nesting; không chỉ so prefix `startsWith("/title")` vì có thể mở nhầm trường khác. Nên parse/normalize path bằng thư viện đã kiểm chứng, whitelist **path cụ thể** và áp vào command DTO, không thao tác entity nhạy cảm.

Với JSON Merge Patch (RFC 7396), `null` có thể có nghĩa **xóa property**. Phải định nghĩa rõ `null` là “giữ nguyên”, “xóa”, hay “không hợp lệ” theo từng field. Không để payload nested `{"owner":{"id":"..."}}` tự tạo quan hệ owner mới.

## 12. ORM/JPA, MapStruct và cơ chế defense-in-depth

### 12.1. JPA entity không phải input contract

Trong JPA/Hibernate, dùng:

```java
// MẢNH CODE: sau khi load managed entity và đã authorize.
entity.setTitle(request.title());
entity.setDescription(request.description());
```

Không dùng `entityManager.merge(detachedFromRequest)` khi detached object lấy trực tiếp từ JSON và chứa các field client không được phép sửa. Merge có thể đưa trạng thái không mong muốn vào entity managed.

### 12.2. `BeanUtils` và generic mappers

`BeanUtils.copyProperties(source, target)` mặc định copy những property có cùng tên và type phù hợp. Nếu input DTO vô tình thêm `ownerId`, một thao tác copy tự động có thể cập nhật owner mà không cần ai sửa code service.

Có thể whitelist bằng mapper:

```java
// MẢNH CODE thiết kế mapper: chỉ gán field được cho phép.
target.setTitle(request.title());
target.setDescription(request.description());
```

MapStruct có thể cấu hình `@BeanMapping(ignoreByDefault = true)` và chỉ `@Mapping` cho các field được phép, nhưng phải kiểm tra generated code và test khi model thay đổi. Generic reflection mapper không được thay cho field-level policy.

### 12.3. Trường nhạy cảm trong nested object

Ngay cả khi DTO không có `ownerId` top-level, một nested DTO như `ProjectUpdateRequest { User owner; }` hoặc `DocumentUpdateRequest { Organization tenant; }` có thể mở đường cho thay ID qua nested binding. Hãy dùng nested input DTO cũng theo **allowlist**, giới hạn chiều sâu, kích thước collection và property path.

Với `@ModelAttribute`, `setAllowedFields("title","description")` không tự bao phủ JSON; với JSON, request DTO riêng và server mapping vẫn là trọng tâm.

### 12.4. Database constraints và auditing

Các cơ chế bổ trợ:

- `NOT NULL`, foreign key, CHECK, unique constraint cho dữ liệu hợp lệ.
- ORM `@Version`/optimistic locking để chống lost update, **không cấp quyền**.
- Row-level security (RLS) ở DB khi phù hợp để giảm tác động của lỗi query tenant.
- Trigger/audit log đối với những trường thay đổi nhạy cảm.
- DB account least privilege; tách quyền thay ACL, owner, tenant.
- Database policies/conditional UPDATE để ràng buộc owner/tenant tại thời điểm ghi.

**Database constraints kiểm tra tính hợp lệ, không thay thế business authorization.** `ownerId = "u-attacker"` có thể trỏ tới một user tồn tại hợp lệ nhưng vẫn là một chuyển quyền trái phép.

## 13. Đa tenant, cache và TOCTOU

### 13.1. Tenant phải đến từ identity đã xác minh

Không lấy:

```java
// KHÔNG đáng tin nếu tenant do client tự quyết định.
String tenant = request.getHeader("X-Tenant");
```

rồi dùng để chọn toàn bộ phạm vi truy cập. Header có thể được xác minh trong một kiến trúc gateway cụ thể, nhưng **không mặc định tin nó**. Nếu ứng dụng cho user chọn tenant đang làm việc, phải kiểm tra user có membership/role ở tenant được chọn.

Trong demo, `TrustedUserDirectory` ánh xạ authentication name sang Actor và tenant thuộc server. DocumentStore so sánh với tenant của bản ghi thật trước khi update.

### 13.2. Khi database bị ghi đồng thời

Giả sử:

```text
T1: alice được phép sửa document #11 khi owner=u-alice, tenant=T1
T2: admin chuyển document #11 cho bob
T1: ghi đè nội dung theo quyết định quyền cũ
```

Đây là **TOCTOU**. Trong DB quan hệ, một giải pháp là conditional UPDATE:

```sql
UPDATE documents
SET title = :newTitle,
    description = :newDescription,
    version = version + 1
WHERE id = :id
  AND owner_id = :trustedActorId
  AND tenant_id = :trustedTenantId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

Đây là SQL **minh họa**, cần bind tham số an toàn theo DB driver. Kiểm tra số hàng cập nhật được: 1 = thành công, 0 = thay đổi trạng thái, quyền hoặc version không còn khớp. Không phân biệt rõ nguyên nhân bằng cách tự động lộ sự tồn tại của object cho user chưa được quyền.

Transaction isolation, row lock, optimistic locking và outbox có thể cần thiết khi các invariant nằm ở nhiều bảng hoặc services. `@Transactional` một mình không đảm bảo mọi phép kiểm tra nằm trong cùng snapshot phù hợp với workflow.

### 13.3. Cache theo quyền

Không cache `canEdit(documentId)=true` chung cho mọi người dùng. Quyết định phụ thuộc:

```text
(principalId, tenantId, documentId, action, policyVersion)
```

Khi owner/tenant/ACL/role/status thay đổi, cache phải invalidation phù hợp. Nếu một response cache theo URL mà thiếu identity/authorization scope, user khác có thể thấy dữ liệu cập nhật hoặc metadata không thuộc quyền.

Một nguyên tắc đơn giản: **không cache quyết định cấp quyền ghi quá lâu nếu không bảo đảm revoke/owner transfer**.

## 14. Những lỗi phổ biến và dấu hiệu phát hiện

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Client gửi `ownerId` và DB đổi owner | Bind entity/copy toàn property | Request DTO allowlist, server mapping tường minh |
| `tenantId` đổi khi sửa title | Generic update/JSON Patch không giới hạn | Tenant từ server, không cho tenant trong update DTO |
| Có `@PreAuthorize` nhưng vẫn đổi role/status | Chỉ kiểm tra quyền chức năng | Field-level policy + riêng endpoint nhạy cảm |
| DTO không có owner nhưng service vẫn nhận `Map<String,Object>` | Mapping thứ cấp bypass DTO | Cấm generic entity binding trong service |
| Form update bị khai thác qua `profile.roles[0]` | `@ModelAttribute` binder quá rộng | Dedicated form DTO/allowedFields |
| `@InitBinder` đặt rồi JSON vẫn bind field nhạy cảm | Nhầm binder form với `@RequestBody` Jackson | JSON DTO + Jackson policy |
| Jackson bỏ qua `ownerId` lạ mà trả 200 | Unknown fields đang bị ignore | Có thể bật strict unknown fields, vẫn giữ DTO allowlist |
| Bật strict unknown nhưng vẫn bị đổi owner | DTO/entity vẫn khai `ownerId` | Thu hẹp DTO và mapping, không chỉ dựa strict |
| `@JsonIgnore` mà một job vẫn sửa owner | Annotation chỉ áp cho JSON binding | Service/domain authorization |
| `@Column(updatable=false)` nhưng một query khác sửa tenant | DB/ORM lớp khác vẫn có quyền | Policy + DB permissions/constraints |
| User cùng role sửa record tenant khác | Thiếu object/tenant policy | Kiểm tra owner + tenant của DB record |
| Chuyển owner hợp lệ bị chặn mọi nơi | Không có workflow chuyển quyền riêng | Endpoint/command có quyền `transfer` và audit |
| `@PostAuthorize` kiểm tra sau update | Side effect xảy ra trước deny | Dùng trước-method và DB guard |
| PATCH sửa `/role` hoặc `/ownerId` | Patch áp trực tiếp lên entity | Whitelist normalized path/action |
| Mass assignment qua nested properties | DTO nested quá rộng | Allowlists cả nested DTO/collections |
| Test `403` pass nhưng owner vẫn thay | Mutation trước khi ném exception | Assert DB state không đổi sau lỗi |
| Quyền đã thu hồi vẫn update được | Cache stale / TOCTOU | Invalidate và conditional DB update |
| Self-invocation bỏ qua `@PreAuthorize` | Spring AOP proxy bị bypass | Tách secured bean, test qua proxy |

### Checklist review code

1. Endpoint có nhận entity/JPA model trực tiếp làm `@RequestBody` hoặc `@ModelAttribute` không?
2. Request DTO có field nào client không được phép sửa không? Kể cả nested DTO và collection?
3. Mapper có `copyProperties`, `merge`, reflection, generic JSON patch hay `Map<String,Object>` không?
4. Service có tự tải bản ghi thật và kiểm tra owner/tenant/state trước khi cập nhật không?
5. Actor và tenant lấy từ `Authentication`/directory đã xác minh hay từ request không tin cậy?
6. `@EnableMethodSecurity` có bật, caller có đi qua proxy, và policy có kiểm tra object-level authorization không?
7. Các hành động thay owner, tenant, trạng thái duyệt, role và classification có workflow/authority riêng không?
8. Sau request bị từ chối, DB state có **chắc chắn không thay đổi** không?
9. Trường mới thêm vào entity có vô tình tự xuất hiện ở input contract không?
10. Có race giữa kiểm tra quyền và UPDATE? Có cache permission stale sau owner transfer không?
11. Validation, CSRF, error handling, request size limit và audit có phù hợp API không?
12. Có test negative cases cho malformed JSON, unknown fields, missing authority, cross-tenant, wrong owner và approved state không?

## 15. Bài tập và câu hỏi tự đánh giá

1. **Mass assignment khác việc client cố gửi JSON field không tồn tại thế nào?**  
   Mass assignment nguy hiểm khi một field được **binding và sử dụng để cập nhật state** dù use case không cho phép. JSON field lạ chỉ là một dấu hiệu thử nghiệm; nếu bị ignore thì chưa chắc có mutation.

2. **Có `@PreAuthorize("hasAuthority('document:edit')")` rồi, vì sao vẫn cần DTO?**  
   Vì authority chức năng không nói người đó được sửa field nào; DTO allowlist giới hạn input contract.

3. **Vì sao không nhận `ownerId` từ client ở API sửa tiêu đề?**  
   Chuyển owner là nghiệp vụ nhạy cảm riêng, cần authorization, audit và kiểm tra người nhận.

4. **`@InitBinder#setAllowedFields` có chặn JSON của `@RequestBody` không?**  
   Không. Nó bảo vệ property binding kiểu form/`@ModelAttribute`; JSON cần DTO/Jackson/service mapping.

5. **Bật `FAIL_ON_UNKNOWN_PROPERTIES` có đủ để chống mass assignment không?**  
   Không. Nếu DTO có property nhạy cảm, nó không còn là unknown. Phải thu hẹp DTO và mapping.

6. **Nếu request có `tenantId="T2"` nhưng JWT cho thấy user thuộc T1 thì sao?**  
   Không tin tenant do request tự khai. API sửa nội dung không nhận tenant; kiểm tra tenant được xác minh với bản ghi server.

7. **`@Column(updatable=false)` có thay cho field authorization không?**  
   Không. Nó chỉ ảnh hưởng một đường ghi ORM, không bảo vệ mọi đường thay đổi hay entity mapping.

8. **Vì sao `id` trên URL và `id` trong payload không nên tùy ý khác nhau?**  
   Vì dễ cập nhật nhầm object, tạo IDOR hoặc duplicate identity. Tốt nhất payload sửa nội dung không mang ID; service lookup theo path ID và authorize bản ghi đó.

9. **Một user có quyền sửa nội dung có được chuyển `state` sang `APPROVED` bằng JSON không?**  
   Không. Phải gọi use case phê duyệt có permission và state-transition policy riêng.

10. **Nếu test nhận 403 nhưng dữ liệu đã đổi owner trước khi lỗi thì đã an toàn chưa?**  
    Chưa. Phải đọc lại state, xác nhận không mutation và kiểm tra transaction rollback/ordering.

11. **Nếu owner đổi ngay sau khi check nhưng trước DB write thì sao?**  
    Có TOCTOU. Dùng conditional UPDATE/lock/version/transaction phù hợp và kiểm tra số hàng ảnh hưởng.

12. **Tại sao cần test cả ca cho phép?**  
    Chỉ test deny không chứng minh chức năng update hợp lệ hoạt động hay đúng hai field được sửa; cả allow và deny đều cần.

13. **Một mapper có `ignoreByDefault=true` đã đủ chưa?**  
    Nó giúp mapping allowlist, nhưng vẫn cần kiểm tra caller có quyền trên object và workflow nhạy cảm có guard riêng.

14. **Trường `version` có thể do client gửi không?**  
    Có thể gửi làm `expectedVersion` để kiểm tra concurrency, nhưng không để client đặt giá trị `entity.version` tùy ý.

15. **Một form chứa `owner.address.city` có thể an toàn nếu top-level chỉ allow `owner` không?**  
    Không nên suy luận vậy. Property path/nested binding cần allowlist chi tiết; tốt nhất input DTO riêng không chứa quan hệ owner nếu không cần sửa.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework — Web MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): rủi ro bind object không tin cậy, dedicated objects, constructor binding, `allowedFields` và declarative binding.
- [Spring Framework — `@ModelAttribute` binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): form binding, constructor/field mapping và các giới hạn của property binding.
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialize HTTP body thông qua message converters và validation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, service proxy và expression-based authorization.
- [Spring Boot 3.5 — Spring Security](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): Boot security defaults và bật method security.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token cho state-changing requests.
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): security testing và integration với MockMvc.
- [OWASP — API Security: Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/): property-level authorization và mass assignment.
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html): allowlist, input DTO và các biện pháp phòng vệ.

**Kết luận:** chống mass assignment không phải chỉ ẩn một field bằng Jackson hay thêm một `@PreAuthorize` chung. Cần kết hợp **request DTO allowlist**, **explicit field mapping**, **quyền chức năng và quyền trên bản ghi**, **identity/tenant server-side**, **workflow riêng cho trường nhạy cảm**, **kiểm thử state sau lỗi** và **ràng buộc nhất quán khi DB ghi**. API sửa nội dung chỉ nên sửa đúng nội dung; `ownerId`, `tenantId`, trạng thái, quyền và audit chỉ được thay đổi qua các use case được cấp phép rõ ràng.