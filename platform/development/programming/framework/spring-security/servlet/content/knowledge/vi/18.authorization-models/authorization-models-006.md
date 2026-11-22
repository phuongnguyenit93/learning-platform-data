# Đối chiếu thuộc tính người dùng, tài nguyên và ngữ cảnh yêu cầu

> **Ngữ cảnh:** Spring Security 6 trên **Servlet stack**, Java 17+ và Spring Boot 3.x. Chủ đề thuộc **Mô hình phân quyền**: cách đánh giá một quyết định cho phép/từ chối dựa trên **thuộc tính người dùng (subject)**, **thuộc tính tài nguyên (resource/object)**, **hành động (action)** và **ngữ cảnh của yêu cầu (environment/request context)**. Cách tiếp cận thường gọi là **ABAC — Attribute-Based Access Control**. Bài giải thích từ mô hình đến điểm đặt chính sách trong Spring Security, ranh giới dữ liệu đáng tin, kiểm soát đa tenant, ví dụ ứng dụng chạy được và kiểm thử phủ cả trường hợp bị từ chối.

## 1. Vì sao chỉ kiểm tra vai trò không đủ?

Giả sử ứng dụng có hàng nghìn tài liệu thuộc nhiều công ty và phòng ban. Một rule:

```java
.requestMatchers("/api/docs/**").hasRole("EMPLOYEE")
```

chỉ trả lời được: “Người này có role `EMPLOYEE` hay không?” Nó **không** trả lời được:

- Tài liệu thuộc tenant nào?
- Người dùng có thuộc tenant đó không?
- Tài liệu có phải tài liệu bí mật với mức phân loại cao hơn quyền xem của user?
- Người dùng có cùng phòng ban với tài liệu không?
- Người dùng có phải người tạo tài liệu, và có được tự phê duyệt tài liệu của mình không?
- Request đang **đọc** hay **phê duyệt**, và active tenant đã được xác minh chưa?
- Trạng thái tài liệu là `DRAFT`, `PENDING` hay `APPROVED`?
- Một điều kiện ngữ cảnh như thời gian, vị trí mạng, mức xác thực MFA có được xác minh từ nguồn đáng tin không?

Nếu chỉ có `hasRole("EMPLOYEE")` cho toàn bộ `/api/docs/**`, nhân viên tenant A có thể xem nhầm tài liệu tenant B. Đó là nguy cơ **IDOR/BOLA** — truy cập đối tượng không được phép bằng cách thay ID trong URL.

**Ý tưởng ABAC:** quyết định dựa trên **quan hệ giữa nhiều thuộc tính**, không chỉ một role tĩnh. Vai trò vẫn hữu ích và có thể là một thuộc tính trong chính sách.

### Câu hỏi trung tâm

Thay vì:

```text
User có ROLE_EMPLOYEE?
       |
      YES -> allow
```

hãy nghĩ:

```text
User thuộc tenant nào? Phòng ban nào? Mức clearance nào?
                       |
Tài liệu thuộc tenant nào? Loại gì? Owner? Trạng thái?
                       |
Action = READ hay APPROVE?
                       |
Request có active tenant được phép? Phương thức HTTP?
                       |
                       v
                  Policy decision
              PERMIT / DENY (mặc định DENY)
```

## 2. Bốn nhóm thuộc tính cần đối chiếu

ABAC thường mô tả bộ thông tin (`subject`, `resource`, `action`, `environment`). Tên gọi có thể khác giữa hệ thống, nhưng ý nghĩa quyết định phải rõ.

| Nhóm | Ví dụ | Nguồn tin cậy |
| --- | --- | --- |
| **Subject (người dùng)** | user ID, tenant memberships, department, role, clearance, trạng thái tài khoản, mức MFA | `Authentication` đã được xác minh và user/profile store phía server |
| **Resource (tài nguyên)** | document ID, tenant sở hữu, department, owner, sensitivity, trạng thái workflow | Database/service repository phía server sau khi load record |
| **Action (hành động)** | read, create, update, approve, delete, export | Endpoint/service operation đã được định nghĩa; method HTTP là một đầu vào nhưng không phải quyền tự phát |
| **Environment / request context** | thời gian server, tenant đang chọn, trusted network/device posture, HTTP method, re-auth freshness | Giá trị server xác nhận; thông tin từ header/query chỉ là dữ liệu cần validation |

Ví dụ công thức chính sách đọc:

```text
allowRead(subject, document, request) =
      isAuthenticated(subject)
  AND subject.tenant == document.tenant
  AND request.selectedTenant == subject.tenant
  AND subject.department == document.department
  AND subject.clearance >= document.minClearance
```

Ví dụ chính sách phê duyệt:

```text
allowApprove(subject, document, request) =
      allowRead(subject, document, request)
  AND subject.hasRole("APPROVER")
  AND document.status == PENDING
  AND subject.username != document.owner
  AND action == APPROVE
  AND requiredStepUpWasVerifiedByServer   (nếu policy yêu cầu)
```

**Không** diễn giải các biểu thức trên là yêu cầu chính xác của mọi doanh nghiệp. Đây là ví dụ minh họa cách tổ hợp thuộc tính. Một hệ thống có thể cho owner truy cập tài liệu khác phòng ban, hoặc dùng nhãn phân loại phi tuyến thay vì số; chính sách phải xuất phát từ nghiệp vụ và threat model.

## 3. RBAC và ABAC: bổ sung, không loại trừ nhau

**RBAC** (Role-Based Access Control) thường kiểm tra role/authority như `ROLE_ADMIN` hoặc `SCOPE_read`.

**ABAC** dùng thuộc tính của nhiều đối tượng và bối cảnh để quyết định một request cụ thể.

| Câu hỏi | RBAC | ABAC |
| --- | --- | --- |
| Có role `REVIEWER` không? | Rất phù hợp | Dùng như một thuộc tính |
| Tài liệu thuộc đúng tenant không? | Role đơn lẻ thường không đủ | Đối chiếu subject tenant và resource tenant |
| User có quyền xem tài liệu với độ nhạy này không? | Cần nhiều roles/chính sách bổ sung | So clearance với classification/label của resource |
| Có phải người tạo đang tự phê duyệt không? | Role không biết owner tài liệu | So subject ID với resource owner |
| Trạng thái resource đang `PENDING`? | Role không biểu đạt trạng thái hiện tại | Đọc state từ repository rồi đánh giá |
| Request xảy ra trong phiên MFA mới xác minh? | Role thô không bảo đảm | Dùng authentication context/freshness đáng tin |
| Độ phức tạp vận hành | Dễ hiểu khi quyền ít | Chính sách phong phú hơn nhưng cần data governance/test/caching |

ABAC **không có nghĩa bỏ `hasRole`**. Một policy thực tế có thể yêu cầu `ROLE_APPROVER` **và** tenant khớp **và** clearance đủ **và** trạng thái đúng. RBAC đóng vai trò “quyền chức năng”; ABAC kiểm tra “được thực hiện với tài nguyên/ngữ cảnh cụ thể này không?”.

### Tránh role explosion

Nếu tạo role cho mọi tổ hợp tenant, phòng ban, tài liệu và trạng thái, có thể xuất hiện `ROLE_NORTH_FINANCE_CONFIDENTIAL_APPROVER_PENDING`, `ROLE_SOUTH_FINANCE_CONFIDENTIAL_APPROVER_PENDING`... Số lượng role tăng nhanh, khó thu hồi và khó hiểu. Tách các thuộc tính động của resource ra khỏi role giúp tránh lặp roles vô hạn.

### ABAC không phải “tin toàn bộ claim của client”

Có JWT với claims `tenant`/`roles` **đã được server kiểm chữ ký, issuer, audience, expiry** thì claims có thể là đầu vào subject đáng tin ở mức policy và thời hạn của token. Nhưng một header tùy ý:

```http
X-User-Role: ADMIN
X-User-Tenant: north
```

**không đáng tin** chỉ vì client đã gửi. Nếu ứng dụng lấy `X-User-Role` để cấp quyền trực tiếp, attacker có thể tự tạo quyền. Luôn kiểm chứng nguồn và trust boundary.

## 4. Kiến trúc policy: PEP, PDP, PIP và PAP

ABAC thường dùng bốn vai trò logic:

- **PEP (Policy Enforcement Point):** chặn request hoặc operation khi policy không cho phép; ví dụ `AuthorizationFilter`, method security interceptor.
- **PDP (Policy Decision Point):** đánh giá policy và trả kết quả permit/deny; ví dụ `AuthorizationManager` hoặc bean `DocumentPolicy`.
- **PIP (Policy Information Point):** cung cấp thuộc tính; ví dụ user directory, document repository, trusted risk engine.
- **PAP (Policy Administration Point):** nơi soạn/quản lý chính sách, version, review và phê duyệt thay đổi.

```text
HTTP request
     |
     v
Authentication filters -> principal đã xác thực
     |
     v
PEP: Spring Security AuthorizationFilter / Method Security
     |
     +--> PDP: DocumentPolicy.canRead/canApprove
                |
                +--> PIP subject: UserProfileDirectory
                +--> PIP resource: DocumentRepository
                +--> Context: active tenant đã đối chiếu
                +--> Action: method/service operation
                |
                v
         PERMIT / DENY
     |
     +--> PERMIT: gọi service/tiếp tục xử lý
     +--> DENY: không thực hiện operation
```

Đối với hệ thống nhỏ, PDP/PIP có thể chỉ là vài Spring beans. Với nhiều ứng dụng/microservices, có thể dùng một policy engine trung tâm; dù dùng giải pháp nào, phải xác định rõ **điểm thực thi quyền** và **độ tin cậy của thuộc tính**. Không chỉ có “policy document” mà không có PEP thực thi trong đường request.

### Permit, deny và trường hợp thiếu dữ liệu

Một policy nên **fail closed**: thiếu user profile, không tìm thấy resource, tenant không xác minh được, clearance không xác định, policy backend lỗi → **không tự cấp quyền**.

Ở môi trường lớn, PDP có thể trả thêm `NotApplicable`/`Indeterminate` hoặc obligations/advice. Ứng dụng phải định nghĩa cách chuyển những trạng thái đó thành HTTP, metrics và xử lý lỗi; **không** xem “không biết” như “allow”.

### 401, 403 và 404

- **401 Unauthorized:** thiếu authentication hợp lệ (ví dụ request Basic không có credentials).
- **403 Forbidden:** đã xác thực nhưng policy ABAC từ chối.
- **404 Not Found:** tài nguyên không tồn tại hoặc ứng dụng cố tình che sự tồn tại của resource không được phép theo policy.

Không bắt buộc mọi resource không được phép phải trả 403; nhiều hệ thống chọn 404 để giảm enumeration. Nhưng đừng có response phân biệt giúp attacker đoán tài nguyên nội bộ nếu chính sách muốn che giấu.

## 5. Thuộc tính người dùng: xác thực từ đâu, hiệu lực bao lâu?

Thông tin subject có thể đến từ:

1. `Authentication.getName()` và authorities được tạo sau khi xác thực.
2. `UserDetailsService` hoặc user directory server-side.
3. Các claims OIDC/JWT đã được verify đúng issuer/audience/signature/expiry.
4. Một dịch vụ quản lý tenant memberships/permissions.
5. Authentication context nói rõ khi nào user hoàn thành MFA hoặc re-authentication.

**Nguồn quyết định phải được kiểm chứng.** Nếu token/cookie còn hiệu lực nhưng role/tenant membership đã thay đổi, phải có chính sách cập nhật quyền: đọc profile realtime, cache TTL ngắn, version token hoặc chủ động revoke. ABAC đọc claims từ token cũ không tự có thông tin membership vừa bị thu hồi.

### Thuộc tính có thể không ổn định

Ví dụ user được chuyển từ phòng ban Sales sang Finance. Nếu `Authentication` trong session vẫn chứa authority/department cũ, policy dựa riêng vào session có thể chấp nhận dữ liệu stale. Thiết kế cần trả lời:

- Khi nào user directory được refresh?
- Có cache không, TTL bao lâu?
- Khi chuyển tenant hoặc vô hiệu hóa user, session/tokens cũ bị xử lý ra sao?
- Nếu user directory unavailable, có fail closed không?
- Có chính sách deny-by-default khi không tra được attributes?

### Tránh gán role từ header do client tự gửi

Anti-pattern:

```java
// Sai: dữ liệu client chưa được xác minh không thể trở thành authority.
String role = request.getHeader("X-Role");
if ("ADMIN".equals(role)) {
    // cho phép admin
}
```

Dù header được proxy thêm, phải xác minh proxy trusted, proxy **xóa header do client gửi trước đó**, backend chỉ nhận traffic từ proxy tin cậy và kết nối được bảo vệ. Không suy luận “có proxy” đồng nghĩa header đáng tin.

## 6. Thuộc tính tài nguyên: luôn lấy bản ghi có chủ sở hữu thật

Nếu URL `GET /api/docs/102` chứa ID `102`, **ID là selector**, không phải chứng cứ user có quyền. Server phải tra resource `102`, lấy tenant, department, owner, classification, status từ repository đáng tin, rồi đối chiếu với subject.

```text
GET /api/docs/102
          |
          +--> id=102 (client chọn)
          |
          v
DocumentRepository.find(102) (server-side)
          |
          +--> tenant=north
          +--> department=finance
          +--> owner=alice
          +--> minClearance=2
          +--> status=PENDING
          |
          v
DocumentPolicy đánh giá các thuộc tính này
```

Không lấy `tenant` và `classification` từ body gửi kèm khi **đọc** tài liệu, rồi coi như dữ liệu tài liệu thật.

### IDOR/BOLA và tenant isolation

Một route dạng `/api/docs/{id}` có thể match mọi ID, bất kể tenant. `authenticated()` chỉ biết user đã đăng nhập. Nếu service gọi `repository.findById(id)` và trả thẳng, một user có thể đổi `102` thành `103` để đọc tài liệu tenant khác.

Có hai hướng bảo vệ hợp lý:

- **Scope truy vấn theo tenant/owner ngay từ DB**, ví dụ repository có điều kiện `id AND tenant_id IN allowedTenants`.
- **Load rồi kiểm tra bằng policy** trước khi trả dữ liệu hoặc thay đổi state.

Khi áp dụng cả hai, cần tránh leak thông tin qua response/timing. Với query đa tenant, Row-Level Security (nếu DB hỗ trợ và cấu hình đúng) có thể bổ sung một lớp phòng thủ, nhưng không thay việc kiểm thử application authorization.

### Metadata thay đổi giữa kiểm tra và thao tác

Ví dụ policy kiểm tra `status=PENDING`, rồi một request khác approve tài liệu trước khi request hiện tại cập nhật. Nếu policy check và update không có transaction/locking/compare-and-set, có thể xảy ra **TOCTOU** (time-of-check to time-of-use).

Trong ví dụ học tập, repository dùng `ConcurrentHashMap.compute(...)` để bảo đảm chuyển trạng thái `PENDING → APPROVED` một cách atomic **trong bộ nhớ của một process**. Production cần transaction, optimistic locking, version column hoặc conditional SQL update trên cơ sở dữ liệu thực, với scope tenant/permission được kiểm soát.

## 7. Ngữ cảnh request: quan sát, lựa chọn và dữ liệu đáng tin

Một request có:

- HTTP method do container nhận (GET/POST/DELETE).
- URL/path variables do router trích xuất.
- Headers như `X-Active-Tenant`, `X-Forwarded-For`, `User-Agent`.
- Địa chỉ mạng client được container/proxy xác định.
- Thời gian request theo clock server.
- Session hoặc token authentication có dấu hiệu MFA/freshness nếu hệ thống hỗ trợ.

**Không phải giá trị nào cũng đáng tin như nhau.**

### 7.1. Active tenant do client chọn chỉ là đề xuất

Nếu một user thuộc nhiều tenant, frontend có thể gửi `X-Active-Tenant: north` để chọn không gian làm việc. Nhưng server cần kiểm tra:

1. User có thực sự được phép ở tenant đó không?
2. Resource có thuộc tenant đó không?
3. Action này có được phép trong tenant đó không?
4. Session/token có đủ mức assurance không?

Một user chỉ thuộc `north` tự gửi header `south` **không được phép xem tài liệu south**. Header chọn context không được dùng như nguồn authority tự thân.

Ví dụ:

```text
Subject = alice, tenant được cấp = north
Resource = doc 103, tenant lưu trong DB = south
Header X-Active-Tenant: south

Không match subject membership và resource tenant -> DENY.
```

### 7.2. IP, proxy và forwarded headers

`request.getRemoteAddr()` thường là IP peer kết nối tới container; sau reverse proxy có thể là proxy thay vì client. Header `X-Forwarded-For` do client tùy ý gửi **không đáng tin** nếu gateway chưa xác thực/chuẩn hóa.

Nếu policy phụ thuộc network zone, hãy để **trusted edge/gateway** cung cấp kết quả đã xác thực, cấu hình forwarded header handling chỉ từ proxy tin cậy và kiểm thử qua production-like network. Thông thường không nên dựa duy nhất IP làm điều kiện cấp quyền cao.

### 7.3. Thời gian server và step-up authentication

Một policy có thể giới hạn `APPROVE` vào giờ làm việc hoặc yêu cầu MFA trong 10 phút vừa qua. Nguồn thời gian phải là `Clock` server đáng tin, không phải một header `X-Now` tự khai; mức MFA phải đến từ authentication event/claim được xác minh, không phải header `X-MFA: true`.

Để test policy theo thời gian, inject `java.time.Clock` rồi dùng `Clock.fixed(...)` trong unit tests. Như vậy test không ngẫu nhiên fail vào đêm, ngày nghỉ hoặc các múi giờ khác.

### 7.4. Action: method HTTP không thay quyền nghiệp vụ

Request `POST /api/docs/102/approve` mô tả action `APPROVE`; controller/service phải định nghĩa rõ semantics. Tuy nhiên người dùng có thể cố gửi `GET` hoặc thêm parameter `action=approve`. Đừng tin parameter tùy ý để cấp quyền nâng cao. Ràng buộc mapping method và kiểm tra policy ở **operation/service** thực sự thay đổi state.

## 8. Điểm đặt chính sách trong Spring Security 6

Có các lựa chọn phổ biến:

| Điểm mở rộng | Dùng khi | Điểm cần chú ý |
| --- | --- | --- |
| `authorizeHttpRequests(...requestMatchers(...))` | Policy tĩnh theo URL/method/role | Không đủ resource metadata nếu chưa load object |
| `AuthorizationManager<RequestAuthorizationContext>` | Cần quyết định ở mức request theo path/header và thông tin đáng tin | Có thể cần PIP lookup; xử lý variables và performance |
| `@PreAuthorize` trên service methods | Policy theo resource ID, subject, action sau khi controller parse input | Phải bật `@EnableMethodSecurity`, bảo đảm method được gọi qua Spring proxy |
| `@PostAuthorize` / collection filtering | Một số trường hợp check sau khi trả data | Thận trọng: dữ liệu có thể đã được xử lý/side effect; tránh leak |
| Custom domain authorization service | Complex workflows, tenant/object relations | Gọi bắt buộc ở mọi code path; test không chỉ controller |
| Database Row-Level Security | Defense in depth cho multi-tenant data | Kết nối DB và session tenant identity phải đúng; không thay policy business-level |

**Khuyến nghị trong bài:** dùng `authorizeHttpRequests` để yêu cầu authentication và HTTP-level policy, sau đó đặt ABAC có resource metadata ở **service method boundary** bằng `@PreAuthorize` gọi một policy bean. Điều này giữ domain policy gần operation, tránh copy-paste điều kiện ở mỗi controller.

### 8.1. Tại sao không chỉ làm authorization tại controller?

Nếu cùng `DocumentService` được gọi từ REST controller, GraphQL resolver, message consumer hay scheduled job, một check đặt riêng trong REST controller có thể bị bỏ qua ở các đường khác. Service-layer policy thường giúp giảm nguy cơ bypass.

Tuy nhiên `@PreAuthorize` dùng AOP proxy của Spring: **self-invocation** (method trong cùng bean gọi method khác của chính bean qua `this`) có thể không đi qua method security interceptor. Thiết kế bean boundaries đúng và kiểm thử các entry points không chỉ HTTP.

### 8.2. @PostAuthorize có thể quá muộn cho side effects

Nếu một method đã cập nhật database hoặc gửi email rồi mới bị `@PostAuthorize` từ chối, side effect đã xảy ra. Với thao tác thay đổi state, dùng pre-authorization và transaction/atomic update phù hợp; không dựa vào post-check để “thu hồi” side effect.

### 8.3. Nguyên tắc default deny

Policy nên trả false khi:

- Không có `Authentication` hợp lệ.
- Subject profile không tồn tại/không load được.
- Resource không tồn tại hoặc không load được.
- Active tenant thiếu/mâu thuẫn.
- Clearance/role không đủ.
- Action không nằm trong chính sách cho phép.
- Ngữ cảnh yêu cầu không đạt yêu cầu hoặc không xác minh được.

**Thất bại trong PIP/PDP không phải permit**. Nếu hệ thống policy backend lỗi, ứng dụng có thể trả 5xx theo hợp đồng nhưng không được cho request vượt qua quyền.

## 9. Dự án Spring Boot chạy được: ABAC cho tài liệu đa tenant

Dự án sử dụng **Java 17+**, **Spring Boot 3.3.5**, **Spring Security 6.x**, **Gradle 8.5**. Mục tiêu là thể hiện chính sách rõ ràng, không chỉ demo `hasRole`. Ứng dụng dùng Basic authentication local để tập trung vào ABAC; production cần HTTPS và authentication provider thực.

**Mô hình:**

| Username | Tenant từ server | Phòng ban | Clearance | Roles |
| --- | --- | --- | --- | --- |
| `alice` | `north` | `finance` | 2 | USER |
| `bob` | `north` | `sales` | 1 | USER |
| `carol` | `south` | `finance` | 3 | USER, APPROVER |
| `dana` | `north` | `finance` | 3 | USER, APPROVER |

| Doc ID | Tenant | Department | Min clearance | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| 101 | north | finance | 1 | alice | DRAFT |
| 102 | north | finance | 2 | alice | PENDING |
| 103 | south | finance | 2 | carol | PENDING |
| 104 | north | finance | 3 | dana | PENDING |

**Policy đọc:** user đã xác thực, header active tenant khớp tenant do server cấp, tenant của doc khớp, cùng department và clearance đủ.

**Policy phê duyệt:** phải đủ điều kiện đọc **và** có `ROLE_APPROVER` **và** tài liệu ở `PENDING` **và** người phê duyệt **khác owner** (separation of duties). Một POST thay đổi state phải có CSRF token trong demo.

### 9.1. Cấu trúc project

```text
abac-document-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    UserProfileDirectory.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/demo/
    DocumentAbacTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'abac-document-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`-parameters` giúp Spring method security nhận đúng tên parameters `#id` và `#activeTenant` trong biểu thức `@PreAuthorize`.

### 9.2. Lớp khởi động

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 9.3. SecurityConfig: xác thực trước, method authorization sau

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demoPass!"))
                .roles("USER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demoPass!"))
                .roles("USER")
                .build();
        UserDetails carol = User.withUsername("carol")
                .password(encoder.encode("demoPass!"))
                .roles("USER", "APPROVER")
                .build();
        UserDetails dana = User.withUsername("dana")
                .password(encoder.encode("demoPass!"))
                .roles("USER", "APPROVER")
                .build();
        return new InMemoryUserDetailsManager(alice, bob, carol, dana);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        // CSRF mặc định được giữ bật: POST cần CSRF token.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Điểm cần chú ý:**

- `@EnableMethodSecurity` bật interceptor để `@PreAuthorize` có tác dụng.
- API chain chỉ yêu cầu `authenticated()` ở tầng HTTP; **chưa đủ để được xem một tài liệu**. Chính sách tài nguyên nằm trong `DocumentPolicy`.
- Fallback chain deny-by-default để các URL ngoài `/api/**` không vô tình nằm ngoài phạm vi Spring Security.
- HTTP Basic chỉ dùng cho demo; credentials phải truyền qua HTTPS ngoài localhost.
- CSRF vẫn bật. `POST` với `httpBasic(...)` trong MockMvc cũng cần `with(csrf())` để chứng minh policy approve hoạt động thay vì chỉ bị CSRF chặn.

### 9.4. UserProfileDirectory: thuộc tính subject do server kiểm soát

`src/main/java/demo/UserProfileDirectory.java`:

```java
package demo;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class UserProfileDirectory {

    private final Map<String, UserProfile> profiles = Map.of(
            "alice", new UserProfile("north", "finance", 2),
            "bob", new UserProfile("north", "sales", 1),
            "carol", new UserProfile("south", "finance", 3),
            "dana", new UserProfile("north", "finance", 3));

    public UserProfile find(String username) {
        return profiles.get(username);
    }
}

record UserProfile(String tenant, String department, int clearance) {}
```

Đây là **source of truth server-side dành cho demo**, không phải header do client đưa vào. Production sẽ dùng database/directory/service có quyền truy cập phù hợp; cần giải quyết cache, thu hồi membership, hiệu lực claims và sự cố PIP.

`UserProfile` chỉ chứa tenant/department/clearance. Role `APPROVER` được Spring Security cấp từ `UserDetailsService` sau khi xác thực username/password. Hai nguồn cung cấp các thuộc tính khác nhau nhưng đều do server quản lý.

### 9.5. DocumentRepository: thuộc tính resource đáng tin

`src/main/java/demo/DocumentRepository.java`:

```java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentRepository {

    private final ConcurrentMap<Long, Document> documents =
            new ConcurrentHashMap<>();

    public DocumentRepository() {
        reset();
    }

    public void reset() {
        documents.clear();
        documents.put(101L, new Document(
                101L, "north", "finance", 1, "alice",
                DocumentStatus.DRAFT));
        documents.put(102L, new Document(
                102L, "north", "finance", 2, "alice",
                DocumentStatus.PENDING));
        documents.put(103L, new Document(
                103L, "south", "finance", 2, "carol",
                DocumentStatus.PENDING));
        documents.put(104L, new Document(
                104L, "north", "finance", 3, "dana",
                DocumentStatus.PENDING));
    }

    public Document find(long id) {
        return documents.get(id);
    }

    public Document approve(long id) {
        return documents.compute(id, (key, current) -> {
            if (current == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            if (current.status() != DocumentStatus.PENDING) {
                throw new ResponseStatusException(HttpStatus.CONFLICT);
            }
            return new Document(
                    current.id(),
                    current.tenant(),
                    current.department(),
                    current.minClearance(),
                    current.owner(),
                    DocumentStatus.APPROVED);
        });
    }
}

enum DocumentStatus {
    DRAFT, PENDING, APPROVED
}

record Document(
        long id,
        String tenant,
        String department,
        int minClearance,
        String owner,
        DocumentStatus status) {}
```

Resource ID từ URL chỉ dùng để **tra bản ghi**; tenant, owner, department, mức clearance và status được lấy từ server-side repository.

`approve` dùng `ConcurrentMap.compute` để kiểm tra `PENDING` và cập nhật `APPROVED` trong một thao tác atomic đối với cùng key **trên một JVM**. Điều này có ý nghĩa nếu hai request đồng thời muốn approve. Nhưng nó **không** biến kiểm tra `DocumentPolicy` trước đó thành transaction nguyên tử trên DB; production cần tiếp tục xử lý TOCTOU bằng transaction/locking/conditional update với tenant scope.

`reset()` phục vụ test để mỗi test độc lập; không dùng endpoint public cho phép caller reset dữ liệu.

### 9.6. DocumentPolicy: nơi đối chiếu subject–resource–context

`src/main/java/demo/DocumentPolicy.java`:

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final UserProfileDirectory directory;
    private final DocumentRepository documents;

    public DocumentPolicy(UserProfileDirectory directory,
                          DocumentRepository documents) {
        this.directory = directory;
        this.documents = documents;
    }

    private UserProfile trustedProfile(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return null;
        }

        return directory.find(authentication.getName());
    }

    private boolean canAccess(Authentication authentication,
                              long id,
                              String activeTenant) {

        UserProfile subject = trustedProfile(authentication);
        Document resource = documents.find(id);

        if (subject == null
                || resource == null
                || activeTenant == null) {
            return false;
        }

        return subject.tenant().equals(activeTenant)
                && resource.tenant().equals(subject.tenant())
                && subject.department().equals(resource.department())
                && subject.clearance() >= resource.minClearance();
    }

    public boolean canRead(Authentication authentication,
                           long id, String activeTenant) {
        return canAccess(authentication, id, activeTenant);
    }

    public boolean canApprove(Authentication authentication,
                              long id, String activeTenant) {

        if (!canAccess(authentication, id, activeTenant)) {
            return false;
        }

        Document resource = documents.find(id);

        return resource != null
                && resource.status() == DocumentStatus.PENDING
                && !resource.owner().equals(authentication.getName())
                && authentication.getAuthorities().stream().anyMatch(
                    authority -> "ROLE_APPROVER".equals(
                            authority.getAuthority()));
    }
}
```

**Điểm mấu chốt của mẫu ABAC này:**

- `authentication.getName()` đến từ quá trình xác thực, không phải `X-User` do browser tự gửi.
- `directory.find(...)` tra tenant/department/clearance **ở server**.
- `documents.find(id)` tra thuộc tính tài liệu **ở server**.
- `activeTenant` là **lựa chọn client gửi** qua header, nhưng phải **bằng** tenant subject và tenant resource. Vì vậy client không thể tự đổi header để cấp membership tenant mới.
- Khi không có user profile, không có resource, tenant trống, sai department hoặc thiếu clearance, policy trả `false`.
- Quyền phê duyệt còn cần `ROLE_APPROVER`, state `PENDING` và **khác owner** nhằm thể hiện nguyên tắc bốn mắt (*four-eyes principle*).

**Giới hạn demo:** mỗi user chỉ có một tenant. Với user có nhiều tenant, directory nên cung cấp tập membership được xác minh; active tenant phải thuộc tập và resource phải thuộc cùng tenant được chọn. Quy tắc đơn tenant giúp học bản chất mà không thêm phức tạp.

### 9.7. DocumentService: buộc policy chạy ở boundary nghiệp vụ

`src/main/java/demo/DocumentService.java`:

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #id, #activeTenant)")
    public String read(long id, String activeTenant) {
        Document document = documents.find(id);
        return "doc-" + document.id() + ":" + document.status();
    }

    @PreAuthorize(
        "@documentPolicy.canApprove(authentication, #id, #activeTenant)")
    public String approve(long id, String activeTenant) {
        Document updated = documents.approve(id);
        return "approved-" + updated.id();
    }
}
```

**Lý do dùng method security:**

- Khi controller gọi `service.read` hoặc `service.approve`, Spring proxy kiểm tra `@PreAuthorize` trước khi chạy phương thức.
- `#id` và `#activeTenant` lấy từ parameters của phương thức, nhờ `-parameters` trong Gradle.
- Logic policy không bị copy sang mỗi endpoint.
- `approve` thay đổi state chỉ sau khi `DocumentPolicy` cho phép.

**Lưu ý AOP proxy:** gọi `this.approve(...)` từ một method khác **trong cùng DocumentService** có thể không đi qua `@PreAuthorize`. Hãy gọi từ một bean khác qua Spring proxy, hoặc thiết kế lớp domain authorization không phụ thuộc hoàn toàn AOP, và test mọi entry point.

**Lưu ý race:** `canApprove` đọc state trước khi method chạy. `documents.approve` kiểm tra `PENDING` lần nữa trong update atomic để tránh double transition. Trong hệ thống DB, policy và ghi state cần transaction/concurrency design phù hợp. Đặc biệt phải xác minh **tenant và membership** không bị thay đổi giữa hai bước nếu threat model đòi hỏi nhất quán tức thời.

### 9.8. DocumentController: đọc tenant lựa chọn, không tin làm quyền

`src/main/java/demo/DocumentController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/docs")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public String read(
            @PathVariable long id,
            @RequestHeader("X-Active-Tenant") String activeTenant) {
        return service.read(id, activeTenant);
    }

    @PostMapping("/{id}/approve")
    public String approve(
            @PathVariable long id,
            @RequestHeader("X-Active-Tenant") String activeTenant) {
        return service.approve(id, activeTenant);
    }
}
```

Controller nhận **selector** `id` và **context client chọn** `X-Active-Tenant`, rồi chuyển chúng tới service. Nó không quyết định trực tiếp "header là north nên user có quyền north". Policy mới được phép đối chiếu với user profile và resource.

Với `@RequestHeader` mặc định `required=true`, user đã xác thực nhưng không gửi header sẽ nhận **400 Bad Request** ở bước binding trước khi vào service. Trường hợp gửi giá trị **sai nhưng có header** sẽ đi tới policy và thường nhận **403**. Đây là hai lỗi khác nhau; cả hai đều không được cấp quyền.

## 10. MockMvc: kiểm thử đối chiếu thuộc tính và chặn truy cập chéo

`src/test/java/demo/DocumentAbacTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAbacTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentRepository documents;

    @BeforeEach
    void resetState() {
        documents.reset();
    }

    @Test
    void anonymousCannotReadDocument() throws Exception {
        mvc.perform(get("/api/docs/101")
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadDocumentInHerTenantAndDepartment()
            throws Exception {
        mvc.perform(get("/api/docs/101")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-101:DRAFT"));
    }

    @Test
    void aliceCanReadConfidentialDocumentWithinClearance()
            throws Exception {
        mvc.perform(get("/api/docs/102")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-102:PENDING"));
    }

    @Test
    void bobIsDeniedBecauseDepartmentAndClearanceDiffer()
            throws Exception {
        mvc.perform(get("/api/docs/102")
                        .with(httpBasic("bob", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotReadHigherClassification()
            throws Exception {
        mvc.perform(get("/api/docs/104")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void crossTenantAccessIsDenied() throws Exception {
        mvc.perform(get("/api/docs/103")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void changingTenantHeaderCannotGrantMembership()
            throws Exception {
        mvc.perform(get("/api/docs/103")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "south"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingTenantSelectorIsBadRequest() throws Exception {
        mvc.perform(get("/api/docs/101")
                        .with(httpBasic("alice", "demoPass!")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void legitimateSouthTenantUserCanReadHerDocument()
            throws Exception {
        mvc.perform(get("/api/docs/103")
                        .with(httpBasic("carol", "demoPass!"))
                        .header("X-Active-Tenant", "south"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-103:PENDING"));
    }

    @Test
    void aliceLacksApproverRole() throws Exception {
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("alice", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void carolCannotApproveHerOwnDocument() throws Exception {
        mvc.perform(post("/api/docs/103/approve")
                        .with(httpBasic("carol", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "south"))
                .andExpect(status().isForbidden());
    }

    @Test
    void approverNeedsCsrfTokenInThisDemo() throws Exception {
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("dana", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void danaCanApproveAnotherOwnersPendingDocument()
            throws Exception {
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("dana", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("approved-102"));

        mvc.perform(get("/api/docs/102")
                        .with(httpBasic("dana", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-102:APPROVED"));

        // Không cho approve lần thứ hai khi status đã thay đổi.
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("dana", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownDocumentFailsClosed() throws Exception {
        mvc.perform(get("/api/docs/999")
                        .with(httpBasic("dana", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void fallbackChainDeniesOutsideApi() throws Exception {
        mvc.perform(get("/external")
                        .with(httpBasic("dana", "demoPass!")))
                .andExpect(status().isForbidden());
    }
}
```

**Kết quả dự kiến:** 15 JUnit tests PASS theo dự án và dependencies đã nêu. Đây là kết quả **kỳ vọng từ việc phân tích mã**, không phải khẳng định đã chạy test tại máy của người học.

### Các biên được chứng minh

1. **Authentication:** anonymous request không vào được tài liệu bảo vệ.
2. **Subject attributes:** Bob đúng tenant nhưng sai department/clearance; Alice thiếu clearance cho doc 104.
3. **Resource attributes:** doc 103 ở tenant south, Alice tenant north không được đọc.
4. **Request context:** Alice đổi `X-Active-Tenant` thành `south` vẫn bị từ chối; header chỉ là context selection, không cấp membership.
5. **Context missing:** không có header bị chặn khi binding, trả 400.
6. **Legitimate access:** Carol xem được tài liệu tenant south đúng clearance.
7. **Action and role:** Alice đọc được doc 102 nhưng không phê duyệt vì thiếu `ROLE_APPROVER`.
8. **Separation of duties:** Carol là approver nhưng **không được phê duyệt tài liệu của mình**.
9. **CSRF:** Dana đủ quyền nhưng POST thiếu CSRF vẫn bị 403.
10. **Stateful resource:** Dana phê duyệt doc 102 thành công, sau đó state thành `APPROVED` và không approve lại được.
11. **Unknown resource:** policy fail closed, trả 403 theo lựa chọn demo.
12. **Chain coverage:** path ngoài `/api/**` bị fallback chain từ chối.

**Tại sao dùng `@BeforeEach resetState()`?** Vì tài liệu được lưu trong bộ nhớ và một test phê duyệt làm state đổi. Mỗi test cần baseline độc lập, không phụ thuộc thứ tự chạy. Ở integration tests với database thật, dùng transaction rollback hoặc test fixture reset có kiểm soát.

**Đừng dùng chỉ `@WithMockUser` để test ABAC** nếu cần chứng minh subject profile được tìm từ username thật sau HTTP Basic và các filters làm việc. `httpBasic(...)` trong test đưa request qua authentication và authorization flow, còn unit tests policy riêng giúp kiểm tra mọi tổ hợp thuộc tính hiệu quả hơn.

### 10.1. Chạy dự án

Từ thư mục `abac-document-demo`, với JDK 17+, Gradle tương thích:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper, có thể dùng `./gradlew test`/`./gradlew bootRun` (macOS/Linux) hoặc `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows).

Thử request local:

```bash
curl -i -u alice:demoPass! \
     -H 'X-Active-Tenant: north' \
     http://localhost:8080/api/docs/101

curl -i -u alice:demoPass! \
     -H 'X-Active-Tenant: south' \
     http://localhost:8080/api/docs/103

curl -i -u bob:demoPass! \
     -H 'X-Active-Tenant: north' \
     http://localhost:8080/api/docs/102

curl -i -u carol:demoPass! \
     -H 'X-Active-Tenant: south' \
     http://localhost:8080/api/docs/103
```

Kết quả dự kiến theo thứ tự: **200**, **403**, **403**, **200**. Các credentials chỉ dành cho localhost. Trên môi trường thật, Basic auth yêu cầu HTTPS vì Base64 trong header **không bảo vệ bí mật**.

Để thử `POST /api/docs/102/approve` qua HTTP client, cần gửi CSRF token hợp lệ theo cơ chế Spring Security. `with(csrf())` chỉ dùng trong MockMvc, không phải một token cố định cho curl. Không tắt CSRF trong demo chỉ để POST 200.

## 11. Khi nào nên dùng AuthorizationManager cho ABAC ở mức HTTP?

`@PreAuthorize` phù hợp khi policy cần resource metadata đã load ở service boundary. Nếu policy phụ thuộc sớm vào method/path/context mà chưa cần resource object, có thể dùng `AuthorizationManager<RequestAuthorizationContext>`:

```java
// Fragment minh họa API, chưa phải bean độc lập hoàn chỉnh.
AuthorizationManager<RequestAuthorizationContext> manager =
        (authenticationSupplier, context) -> {

            Authentication authentication =
                    authenticationSupplier.get();

            String id = context.getVariables().get("id");

            // Chỉ có thể quyết định sau khi kiểm tra subject/profile,
            // resource metadata và context bằng nguồn đáng tin.
            boolean allowed = false; // fail closed trước khi có policy thật
            return new AuthorizationDecision(allowed);
        };
```

Dùng fragment này để hiểu **hình dạng API**; nếu dán nguyên nó vào cấu hình, mọi request sẽ bị từ chối vì `allowed=false`. Phải implement một policy thật và kiểm thử trước khi sử dụng.

Có thể gắn với:

```java
// Fragment trong authorizeHttpRequests:
.requestMatchers("/api/docs/{id}").access(manager)
```

Nhưng với dữ liệu resource phức tạp, method security thường dễ tích hợp repository/service và transaction hơn. Đừng tạo hai policy mâu thuẫn ở HTTP và service rồi chỉ test một lớp.

### RequestAuthorizationContext variables không phải trusted claims

`context.getVariables().get("id")` trả selector từ URL; nó không xác minh resource owner/tenant. Nếu muốn kiểm tra role cùng resource, authorization manager vẫn phải tra resource server-side hoặc gọi PIP đáng tin rồi mới quyết định.

## 12. Multi-tenant: quy tắc đối chiếu cần chống nhầm lẫn

Một lỗi dễ mắc:

```java
// Anti-pattern: tin selected tenant do client tự gửi.
if ("north".equals(request.getHeader("X-Active-Tenant"))) {
    return northRepository.findById(id);
}
```

Điều này không chứng minh user thuộc north; client có thể đổi header.

Mẫu đúng về ý tưởng:

```text
selectedTenant = header do client chọn
allowedTenants = server-side memberships của authenticated user
resourceTenant = server-side metadata của tài liệu

Cho phép tiếp tục xét:
    selectedTenant IN allowedTenants
    AND resourceTenant == selectedTenant
    AND các thuộc tính khác thỏa policy
```

Nếu user thuộc nhiều tenant, `Set<String> allowedTenants` nên được cấp từ nguồn đáng tin; không ghép chuỗi tùy ý hay so tên tenant bằng contains (ví dụ `north` không được coi là chứa `north-admin`).

### Scope query theo tenant ở tầng repository

Một repository thực tế có thể triển khai:

```sql
SELECT *
FROM documents
WHERE id = :id
  AND tenant_id = :trusted_active_tenant
```

Đây là **pseudocode SQL có named parameters**, cần binding an toàn qua JDBC/JPA. `:trusted_active_tenant` phải là giá trị **đã được đối chiếu với user membership**, không phải raw header. Sau query, vẫn cần kiểm tra clearance, trạng thái và quyền action.

Để giảm nguy cơ IDOR/BOLA, tránh trả về resource cross-tenant rồi phụ thuộc một if ở controller để không lộ dữ liệu. Tùy kiến trúc, có thể phối hợp repository scoping, method security và DB Row-Level Security.

## 13. Chính sách yêu cầu ngữ cảnh nâng cao

Không phải điều kiện môi trường nào cũng nên viết thành if ở controller. Những trường hợp thực tế:

### 13.1. Thời gian và lịch làm việc

Ví dụ: chỉ phê duyệt trong khung giờ công ty. Dùng `Clock` server và policy về timezone. Nếu không có timezone thống nhất, user ở Việt Nam và server UTC có thể khác ngày. Với test, inject `Clock.fixed(...)`, không phụ thuộc `LocalTime.now()` trực tiếp.

### 13.2. MFA và step-up authentication

Một tài liệu nhạy cảm có thể yêu cầu MFA trong 5 phút vừa qua. Attribute “đã MFA” phải là thông tin **do authentication subsystem chứng minh**, có issuer/timestamp/assurance đáng tin, không phải request header `X-MFA-Passed: true`.

Nếu user vừa hoàn thành MFA nhưng session bị vô hiệu, phải có cách kiểm chứng context hợp lệ cho request mới. Không chỉ dùng role `ROLE_MFA` tồn tại vô hạn nếu policy yêu cầu freshness.

### 13.3. Vị trí mạng và thiết bị

Chỉ cho hành động nhạy cảm từ trusted network/device posture có thể là một điều kiện bổ sung. IP có thể bị NAT, proxy, VPN, thay đổi; device posture phải đến từ một hệ thống đã xác thực. Không dùng `User-Agent` hoặc raw `X-Forwarded-For` như bằng chứng danh tính đáng tin.

### 13.4. Phân tách trách nhiệm

Người tạo tài liệu không tự phê duyệt, dù có role approver. Đây là mối quan hệ **subject.username != resource.owner**. Kiểm tra role đơn lẻ không biểu đạt ràng buộc này.

### 13.5. Resource state và transitions

`APPROVE` chỉ có nghĩa với resource `PENDING`, `REOPEN` chỉ với `APPROVED`, `DELETE` có thể bị cấm khi đã xuất hóa đơn. Policy action phải xét trạng thái server-side, rồi update phải kiểm tra lại state atomically. Đừng để hai request đi qua pre-check rồi gây chuyển state trái phép.

## 14. Policy testing: ma trận thay vì chỉ happy path

Một ABAC policy có nhiều chiều. Test một request thành công không chứng minh policy đúng.

Ma trận tối thiểu:

| Subject | Resource | Context | Action | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Alice (north/finance/2) | Doc 101 (north/finance/1) | north | READ | ALLOW |
| Alice (north/finance/2) | Doc 102 (north/finance/2) | north | READ | ALLOW |
| Bob (north/sales/1) | Doc 102 (north/finance/2) | north | READ | DENY |
| Alice | Doc 104 (minClearance 3) | north | READ | DENY |
| Alice | Doc 103 (south) | north | READ | DENY |
| Alice | Doc 103 (south) | south do client gửi | READ | DENY |
| Carol (south/finance/3) | Doc 103 | south | READ | ALLOW |
| Alice (không APPROVER) | Doc 102 PENDING | north | APPROVE | DENY |
| Carol (APPROVER, là owner) | Doc 103 PENDING | south | APPROVE | DENY |
| Dana (APPROVER, khác owner) | Doc 102 PENDING | north | APPROVE | ALLOW |
| Dana | Doc 102 sau APPROVED | north | APPROVE | DENY |
| Anonymous | Bất kỳ tài liệu protected | bất kỳ | READ | DENY |

### Test trực tiếp policy bean

Bên cạnh MockMvc, có thể unit test `DocumentPolicy` với các `Authentication` đã được xây dựng có kiểm soát. Unit test giúp tạo nhiều tổ hợp thuộc tính mà không phải gửi HTTP request. Tuy nhiên unit test không đủ chứng minh `@EnableMethodSecurity` và `@PreAuthorize` đã nối đúng qua Spring proxy; cần integration tests.

### Property-based và mutation tests

Với nhiều chính sách phức tạp, có thể phát sinh hàng trăm tổ hợp: tenant, role, department, clearance, status, ownership, action và thời gian. Property-based testing hữu ích để diễn đạt bất biến như:

- Đổi tenant resource sang tenant khác **không tự biến DENY thành ALLOW**.
- Giảm clearance user không thể mở thêm tài liệu nhạy cảm.
- Một user tự phê duyệt không bao giờ được cấp phép nếu SoD policy cấm.
- Resource không tồn tại luôn fail closed.
- Bỏ một điều kiện cần thiết khỏi policy phải khiến test bắt lỗi (mutation testing).

Test từng ràng buộc **độc lập**; nếu một test vừa sai tenant vừa sai role, nó không chứng minh cả hai điều kiện đều được kiểm tra.

## 15. Caching, consistency và audit cho ABAC

### 15.1. Tránh quyền stale

Nếu dùng cache cho `UserProfileDirectory`/`DocumentRepository`, phải hiểu TTL và invalidation. Một user bị xóa khỏi tenant nhưng cache vẫn cho là thành viên có thể tiếp tục truy cập cho đến khi cache hết hạn. Với hành động nhạy cảm, policy có thể phải bypass cache hoặc dùng version/epoch của permission.

### 15.2. Cân nhắc latency PIP

Mỗi request cần load user profile và document metadata, dễ tạo N+1 queries. Có thể batch/cache thuộc tính nhưng không được giảm an ninh. Đo latency, rate limit, circuit breaker và khả năng fail closed khi PIP unavailable. Với hệ thống nhiều dịch vụ, policy engine tập trung có thể thêm network hop.

### 15.3. Ghi audit nhưng không rò dữ liệu

Ghi nhận actor đã xác thực, resource identifier ở mức phù hợp, action, policy version, decision và request correlation ID. Không log access token, password, session ID, header bí mật hay toàn bộ nội dung tài liệu. Nếu request bị deny vì cross-tenant, audit có thể cần sự kiện bảo mật nhưng response không nên tiết lộ metadata nhạy cảm của tenant khác.

### 15.4. Version hóa chính sách

ABAC là logic nghiệp vụ quan trọng. Thay đổi `clearance>=2` thành `>=1` có thể mở dữ liệu nhạy cảm; cần code review, automated tests, change approval, deployment canary và khả năng rollback. Trên nhiều service, tránh mỗi service có bản policy drift dẫn đến kết quả trái ngược.

### 15.5. Hiệu lực tức thời vs eventual consistency

Không phải lúc nào thay role/membership cũng có thể đồng bộ mọi token/cache/session tức thì. Hãy xác định SLA thu hồi quyền và phương án với action nhạy cảm, ví dụ tra trạng thái realtime hoặc revoke sessions. Không tuyên bố “ABAC đảm bảo thu hồi ngay” chỉ vì policy code có điều kiện tenant.

## 16. Các lỗi phổ biến

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra `authenticated()` với `/api/docs/{id}` | IDOR/BOLA | Đối chiếu resource tenant/owner/clearance |
| Coi `X-Active-Tenant` là authority | User tự đổi tenant header để đọc dữ liệu | So header với memberships từ server |
| Dùng `X-Role` làm roles | Client tự nâng quyền | Authorities đến từ Authentication/IdP đã verify |
| Chỉ kiểm tra role `APPROVER` | Tự duyệt tài liệu của mình hoặc tenant khác | Thêm resource state/owner/tenant |
| Trust body `resource.tenant` khi cập nhật | Attacker sửa metadata để đi qua policy | Load resource thật và bảo vệ mutation |
| Policy đặt riêng ở một controller | GraphQL/job/service khác có thể bypass | Bảo vệ ở service boundary hoặc centralized PEP |
| Quên `@EnableMethodSecurity` | `@PreAuthorize` không được kích hoạt | Bật và test integration |
| Method gọi `this.securedMethod()` | Self-invocation bỏ qua AOP proxy | Thiết kế bean boundary và test |
| Dựa vào `@PostAuthorize` sau side effect | Kiểm tra quá muộn | Pre-check và transaction/atomic update |
| Thiếu profile hoặc resource thì allow | Fail-open | Fail closed, xử lý unavailable rõ |
| Một test cross-tenant cũng sai role | Không chứng minh từng điều kiện | Test một biến thay đổi mỗi lần |
| Dùng JWT claims đã cũ mãi mãi | Permission stale | Revoke, expiry, refresh hoặc server lookup |
| Check status PENDING rồi update không atomic | TOCTOU/double approval | Conditional update/optimistic locking |
| Tin `X-Forwarded-For` tùy ý | Giả mạo network context | Trusted proxy/forwarded-header config |
| Dùng clock client cho time-based policy | Client giả mạo thời gian | `Clock` server và timezone rõ |
| Cho lỗi deny trả metadata resource khác tenant | Information disclosure | Error contract/404 masking phù hợp |

## 17. Checklist triển khai an toàn

- [ ] Authentication đã verify subject (không lấy user từ raw header).
- [ ] Tenant memberships/roles/clearance lấy từ nguồn có độ tin cậy phù hợp.
- [ ] Resource metadata lấy bằng ID từ repository server-side, không tin thuộc tính trong request.
- [ ] Action được định nghĩa theo operation/service, không qua query tùy ý.
- [ ] Request context từ client được validation, không coi header là authority.
- [ ] Chính sách thể hiện tenant, department, clearance, ownership, status và role khi cần.
- [ ] `@EnableMethodSecurity` được bật và `@PreAuthorize` thực sự chạy qua Spring proxy.
- [ ] HTTP security và method security có fallback deny-by-default.
- [ ] Không có bypass từ self-invocation, background jobs, GraphQL hoặc service call khác.
- [ ] CSRF phù hợp cho state-changing browser/session requests.
- [ ] Unknown resource, missing profile và lỗi PIP đều không được permit.
- [ ] Resource transitions/check+update dùng transaction/locking/conditional write.
- [ ] Role/tenant thay đổi có policy cache invalidation và revocation.
- [ ] Unit tests policy và MockMvc integration tests phủ allow/deny độc lập.
- [ ] Audit không log secrets hay tài liệu nhạy cảm.
- [ ] Có policy version, code review và quy trình rollback.

## 18. Câu hỏi tự kiểm tra

1. **ABAC khác RBAC ở đâu?** ABAC đối chiếu nhiều thuộc tính của subject/resource/action/environment; RBAC chủ yếu tập trung role.
2. **Role APPROVER có đủ để phê duyệt mọi tài liệu không?** Không. Còn tenant, classification, trạng thái, ownership, SoD và các điều kiện khác.
3. **Có thể tin X-Active-Tenant do frontend gửi không?** Chỉ như lựa chọn context, không phải chứng cứ user là thành viên tenant đó.
4. **Vì sao cần load tài liệu từ DB khi authorization?** Để đối chiếu tenant, owner, status và phân loại tài liệu đáng tin.
5. **Lấy id từ URL có nghĩa user sở hữu tài liệu không?** Không; id là selector, phải kiểm tra object-level authorization.
6. **Nên đặt resource policy ở đâu?** Thường ở service/method authorization boundary; HTTP rules bổ sung authentication và coarse access.
7. **`@PreAuthorize` có tự hoạt động khi chưa bật method security không?** Không; cần `@EnableMethodSecurity` trong cấu hình phù hợp.
8. **Self-invocation là vấn đề gì?** Lời gọi nội bộ qua `this` có thể bỏ qua Spring AOP proxy và interceptor.
9. **Kiểm tra quyền sau khi gửi email hoặc update DB có đủ không?** Không, side effect đã xảy ra; phải pre-check và cập nhật an toàn.
10. **Nếu user directory down thì có cho phép tạm không?** Không được fail open; cần error/availability policy rõ.
11. **Nếu tài liệu chuyển PENDING sang APPROVED cùng lúc hai request?** Cần atomic transition/DB locking, không chỉ pre-check.
12. **Có thể dùng X-MFA-Passed: true làm bằng chứng MFA không?** Không, trừ khi nó đến từ cơ chế đáng tin được xác minh; thông thường dùng authentication context của identity subsystem.
13. **Token đã verify signature nhưng tenant membership bị thu hồi thì sao?** Cần kế hoạch cập nhật/revoke/caching; claims còn hạn có thể stale.
14. **Test ABAC nên kiểm tra gì ngoài happy path?** Cross-tenant, thiếu clearance/role, sai phòng ban, owner tự phê duyệt, sai context, unknown resource, CSRF và concurrency.
15. **Có cần bỏ RBAC khi dùng ABAC không?** Không. Role vẫn có thể là thuộc tính trong chính sách ABAC.

**Ghi nhớ:** Quyền truy cập tài nguyên không chỉ phụ thuộc “người dùng là ai”, mà còn “tài nguyên thuộc ai, thuộc tenant nào, nhạy cảm ra sao, đang ở trạng thái gì, action gì và request context nào đã được xác minh”. Với Spring Security Servlet, hãy **xác thực subject trước**, **load thuộc tính resource từ server**, **đối chiếu ngữ cảnh yêu cầu có kiểm chứng**, sau đó thực thi policy tại điểm không dễ bị bypass như `@PreAuthorize` trên service. Mặc định từ chối khi không đủ dữ liệu, kiểm tra mọi chiều độc lập và cập nhật resource atomically để giảm TOCTOU.
