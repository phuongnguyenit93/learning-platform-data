# Tích hợp dịch vụ quyết định quyền bằng `AuthorizationManager` trong Spring Security

## 1. Vì sao cần một dịch vụ quyết định quyền?

Một hệ thống xử lý hóa đơn sử dụng Spring Security. Quy tắc phê duyệt không còn là “có role `APPROVER` thì được duyệt tất cả”:

- Người gọi phải xác thực và có authority chức năng `invoice:approve`.
- Hóa đơn phải thuộc tenant mà người gọi được phép làm việc.
- Hóa đơn đang ở trạng thái `PENDING`.
- Số tiền không vượt hạn mức phê duyệt của người gọi.
- Người tạo hóa đơn không được tự phê duyệt (*maker–checker*).
- Chính sách có thể thay đổi tại runtime, được vận hành bởi một **dịch vụ quyết định quyền**.
- Nếu dịch vụ quyết định quyền không phản hồi, hệ thống **không được mặc định cho phép**.

Đây là **chính sách động**: quyết định phụ thuộc cả identity, resource, action, ngữ cảnh và trạng thái hiện tại. Chỉ dùng:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
```

là **chưa đủ**; annotation này không tự biết tenant, trạng thái hóa đơn, hạn mức, maker–checker hay chính sách bên ngoài.

Spring Security cung cấp `AuthorizationManager<T>` để kết nối một **điểm thực thi quyền** với **dịch vụ ra quyết định**. Ta có thể tự viết `AuthorizationManager` để hỏi policy engine trong cùng process, dịch vụ PDP độc lập qua HTTP/gRPC, hoặc một hệ thống policy khác.

Bài Knowledge thuộc nhóm **Chính sách động** của module *Spring Security – authorization*. Trọng tâm là **tích hợp dịch vụ quyết định quyền bằng `AuthorizationManager`**, không phải chỉ liệt kê role tĩnh hay thay thế một boolean `canApprove()` thủ công.

Sau bài, bạn sẽ:

1. Phân biệt **PEP, PDP, PIP, PAP** và ranh giới tin cậy.
2. Hiểu API `AuthorizationManager<T>`, `Supplier<Authentication>`, `AuthorizationDecision` và kết quả abstain.
3. Biết cách biến `MethodInvocation` thành yêu cầu đánh giá policy có `subject`, `resource`, `action`, `context`.
4. Tạo một `AuthorizationManager<MethodInvocation>` gọi `PolicyDecisionClient` và trả quyết định **explicit allow/deny**.
5. Đăng ký custom **method interceptor** bằng pointcut cho annotation `@RequiresInvoiceApproval`.
6. Thấy cách mở rộng cùng tư duy sang **HTTP `AuthorizationManager<RequestAuthorizationContext>`**.
7. Chạy ví dụ **Java 17 + Spring Boot 3.5.x + Spring Security 6.5.x** có đủ mã nguồn, dữ liệu mẫu, stdout dự kiến và integration tests.
8. Kiểm soát **PDP timeout, 5xx, policy version, cache, multi-tenant, audit, TOCTOU** và giới hạn của remote authorization.
9. Nhận biết lựa chọn `AuthorizationManagers.allOf(...)` và nguy cơ **abstain bị hiểu sai**.
10. Kiểm thử được cả đường cho phép, từ chối, thiếu authority, cross-tenant, self-approval, policy down và trạng thái thay đổi.

**Nguyên tắc an toàn:** Một `ALLOW` chỉ hợp lệ khi request policy được tạo từ dữ liệu **đáng tin**, response từ PDP được xác thực/kiểm chứng, quyết định còn hiệu lực theo consistency contract và thao tác ghi không vượt qua kiểm tra quyền ở thời điểm sử dụng.

---

## 2. Mô hình PEP – PDP – PIP – PAP

Thuật ngữ thường dùng trong hệ thống authorization tách rời:

| Vai trò | Ý nghĩa | Thành phần trong Spring/ứng dụng |
| --- | --- | --- |
| **PEP** – Policy Enforcement Point | Chặn hoặc cho request đi tiếp | `AuthorizationManagerBeforeMethodInterceptor`, filter-chain authorization, service guard |
| **PDP** – Policy Decision Point | Tính quyết định cho phép/từ chối | `PolicyDecisionClient`, OPA/Cedar/policy service hoặc business policy engine |
| **PIP** – Policy Information Point | Cung cấp thuộc tính tin cậy | Directory user/tenant, repository, trạng thái hóa đơn, limit, risk context |
| **PAP** – Policy Administration Point | Tạo/quản lý quy tắc và phiên bản | Công cụ policy management và quy trình phê duyệt thay đổi policy |

Sơ đồ:

```text
Request / Scheduler / Message Consumer
                  |
                  v
          Spring Security PEP
          AuthorizationManager<T>
                  |
       +----------+-----------+
       |                      |
       v                      v
Authentication           Resource context
(server verified)        (DB/server trusted)
       |                      |
       +----------+-----------+
                  |
                  v
         PolicyDecisionClient
           /       |       \
          v        v        v
       PIP      Policy     PDP
     attributes  version   evaluate
                  |
                  v
       ALLOW / DENY / INDETERMINATE
                  |
                  v
       AuthorizationDecision
             |        |
           ALLOW     DENY
             |        |
       method runs   no execution
```

`AuthorizationManager` là **bộ chuyển đổi thực thi quyết định trong Spring Security**, không nhất thiết là nơi chứa toàn bộ logic policy. Nếu PDP nằm ở service riêng, manager cần chuẩn hóa đầu vào, xác thực caller, gọi client, diễn giải response và xử lý lỗi theo mặc định **deny**.

**Tách trách nhiệm:**

- Manager biết **cần bảo vệ lời gọi nào** và cách lấy identity/resource/action.
- Policy client biết **gọi và hiểu PDP**.
- Directory/repository cung cấp **facts đáng tin**.
- PDP biết **luật nghiệp vụ/ABAC/RBAC** và phiên bản luật.
- Service/domain/database bảo đảm **mutation sau authorization** không vi phạm trạng thái vừa thay đổi.

## 3. `AuthorizationManager<T>` trong Spring Security 6.5

Interface thuộc:

```java
package org.springframework.security.authorization;
```

Ý tưởng API:

```java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T object
);
```

Đây là chữ ký rút gọn cho Spring Security 6.5. Các type chính:

- `T`: ngữ cảnh cần xét, ví dụ `MethodInvocation` hoặc `RequestAuthorizationContext`.
- `Supplier<Authentication>`: nhà cung cấp authentication hiện tại; không giả định luôn được gọi hoặc memoized.
- `AuthorizationDecision(true/false)`: quyết định rõ ràng.
- `null`: trường hợp **abstain**, nghĩa là manager chưa đưa ra quyết định, **không đồng nghĩa luôn deny**.

**Điểm đáng chú ý theo phiên bản:** Trong Spring Security 6.5, `check(...)` vẫn là phương thức abstract nhưng được đánh dấu **deprecated**; có phương thức default `authorize(...)` trả `AuthorizationResult`. Khi triển khai một class nhắm Spring Security **6.5.x**, override `check(...)` là cách đúng contract để biên dịch. Ở Spring Security **7.x**, `authorize(...)` là điểm mở rộng chính và chữ ký có thể khác; không copy nguyên class 6.5 mà bỏ bước migration.

Ví dụ manager đơn giản:

```java
// MẢNH CODE minh họa; phù hợp interface 6.5.
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        MethodInvocation invocation) {

    return new AuthorizationDecision(
        policyService.decide(authentication.get(), invocation)
    );
}
```

Trong sản phẩm, đoạn trên còn thiếu kiểm tra anonymous, authority, request arguments, timeout, policy response và exception handling. Bản đầy đủ sẽ nằm ở mục 7.

### 3.1. `check`, `authorize` và `verify` khác gì?

| API | Kết quả | Lưu ý |
| --- | --- | --- |
| `check(...)` | `AuthorizationDecision` hoặc `null` | API abstract/deprecated ở 6.5; custom implementation vẫn có thể cần override |
| `authorize(...)` | `AuthorizationResult` hoặc `null` | API được khuyến nghị để viết code mới; default bridge ở 6.5 |
| `verify(...)` | Không trả về; có thể ném `AccessDeniedException` | Dùng khi chỉ cần fail-fast nếu bị từ chối |

Đừng viết:

```java
AuthorizationDecision decision = manager.check(auth, invocation);
if (decision == null || decision.isGranted()) {
    // NGUY HIỂM: null (abstain) bị hiểu là cho phép
}
```

Nếu policy hệ thống yêu cầu luôn có quyết định, hãy trả `new AuthorizationDecision(false)` khi thông tin không hợp lệ, không khớp target hoặc PDP không phản hồi. `null` chỉ thích hợp khi **chủ ý có một cơ chế kết hợp** hiểu abstain và có default rõ ràng.

### 3.2. `AuthorizationManager<T>` không giống `PermissionEvaluator`

`PermissionEvaluator` là SPI cho biểu thức `hasPermission(...)`, điển hình áp dụng ACL cho object. `AuthorizationManager` tổng quát hơn: nó có thể được gọi bởi HTTP authorization hoặc method interceptor và dễ trở thành adapter cho PDP từ xa.

| `PermissionEvaluator` | `AuthorizationManager` |
| --- | --- |
| Chủ yếu được gọi qua `hasPermission(...)` | Được gọi trực tiếp bởi cơ chế authorization |
| Input thường là authentication, object/ID, permission | Input là authentication supplier + generic context `T` |
| Return boolean | Return `AuthorizationDecision`/`AuthorizationResult` hoặc abstain |
| Phù hợp ACL và permission expression | Phù hợp custom policy engine/remote PDP, HTTP, method, messaging |
| Không tự là PEP hoàn chỉnh | Được các interceptor/filter-chain PEP sử dụng |

Có thể dùng cả hai: manager gọi service nội bộ dùng ACL evaluator, hoặc PDP kết hợp ACL với rule khác. Điều quan trọng là **chỉ có một nguồn sự thật hoặc một quy tắc kết hợp rõ ràng** để tránh hai đường cho kết quả trái nhau.

## 4. Thiết kế hợp đồng giữa PEP và PDP

### 4.1. Đầu vào policy gồm gì?

Một policy request dạng khái niệm:

```json
{
  "requestId": "7fd9f2d0-1511-4f2e-a2ad-784cf8b4279d",
  "subject": {
    "id": "u-alice",
    "tenantId": "T1",
    "authorities": ["invoice:approve"]
  },
  "action": "INVOICE_APPROVE",
  "resource": {
    "type": "INVOICE",
    "id": 101,
    "tenantId": "T1",
    "createdBy": "u-bob",
    "state": "PENDING",
    "amount": 250,
    "version": 3
  },
  "context": {
    "policyVersion": "approval-policy-v12"
  }
}
```

Đây là **ví dụ JSON hợp đồng**, không phải request thực tế đã gửi tới dịch vụ bên ngoài. Trong production, không nhất thiết gửi toàn bộ thuộc tính resource hay authorities: chỉ gửi các facts tối thiểu cần để quyết định, có phân loại dữ liệu nhạy cảm và kiểm soát retention.

Nguồn tin cậy cho từng trường:

| Trường | Nguồn nên dùng | Không nên dùng |
| --- | --- | --- |
| `subject.id` | `Authentication` đã được xác minh + mapping server | `"userId"` tùy ý từ body |
| `tenantId` | Membership/tenant directory, active tenant đã verify | Header `X-Tenant` không kiểm chứng |
| `action` | Hằng/enum phía server do endpoint/method xác định | Chuỗi action bất kỳ do client đặt |
| `resource.id` | Argument hợp lệ từ method/path | ID gắn với object chưa xác minh |
| `resource.tenantId`, `createdBy` | Repository hoặc nguồn thuộc tính authoritative | JSON field client tự khai |
| `amount`, `state`, `version` | Bản ghi hiện hành từ DB | DTO được gửi để vượt policy |
| `policyVersion` | Engine/PAP đã triển khai | Version cho client tự chọn để bypass |

**Đừng hỏi PDP bằng một DTO client tự khai `tenantId=MY_TENANT`** rồi mặc định response ALLOW có giá trị. PDP chỉ mạnh bằng **độ tin cậy của input**.

### 4.2. Response cần phân biệt các trạng thái

Một policy engine có thể trả:

```json
{
  "decision": "DENY",
  "reasonCode": "MAKER_CHECKER",
  "policyVersion": "approval-policy-v12",
  "decisionId": "6c78364c-0240-43b4-9711-470e01292b30"
}
```

Nên đặc tả ít nhất:

- `ALLOW`: cho phép theo policy.
- `DENY`: từ chối rõ ràng.
- `NOT_APPLICABLE`: không có policy phù hợp.
- `INDETERMINATE`: thiếu dữ liệu, lỗi engine hoặc kết quả không thể kết luận.

**Mapping an toàn:** chỉ `ALLOW` được biến thành `AuthorizationDecision(true)`. `DENY`, `NOT_APPLICABLE`, `INDETERMINATE`, response rỗng/lỗi schema đều là **không cho phép**, trừ khi ứng dụng có một composition protocol được đặc tả và kiểm thử khác.

`reasonCode` dùng cho audit/observability; không tự đưa tất cả lý do nội bộ ra response HTTP vì có thể làm lộ role, quota, tenant, policy hay sự tồn tại của object.

### 4.3. Tránh gửi dữ liệu nhạy cảm ra ngoài tùy tiện

Nếu PDP là remote service:

- Dùng HTTPS/TLS, mTLS hoặc service-to-service authentication phù hợp.
- Dùng allowlist trường dữ liệu; tránh gửi toàn bộ JWT, secret, nội dung tài liệu và thông tin cá nhân không cần.
- Kiểm soát network egress; không để `PDP_URL` lấy từ input user.
- Xác minh response thuộc đúng policy request (request ID, tenant/scope, signature nếu mô hình yêu cầu).
- Log correlation ID, latency, policy version và reason code có giới hạn; không log credential.
- Có timeout, concurrency limit, circuit breaker và cơ chế giảm tải để tránh request flood làm sập PDP.
- Chỉ cache **quyết định được phép cache**, theo key và TTL gắn policy/resource version.

Một remote ALLOW không cho phép client bỏ qua domain invariants như `state == PENDING` nếu dữ liệu đã thay đổi kể từ lúc PDP xét.

## 5. Chọn điểm tích hợp: HTTP hay Method Security?

Spring Security sử dụng `AuthorizationManager<T>` trong nhiều lớp. Hai lớp quan trọng với ứng dụng servlet:

### 5.1. HTTP authorization

Tạo `AuthorizationManager<RequestAuthorizationContext>` và gắn với:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/api/invoices/{id}/approve")
        .access(invoiceHttpAuthorizationManager)
    .anyRequest().denyAll()
);
```

Đây là **mảnh cấu hình web**, chưa phải ứng dụng chạy độc lập. `RequestAuthorizationContext` cung cấp `HttpServletRequest` và các biến route khi `RequestMatcher` hỗ trợ. HTTP manager có thể dùng đường dẫn/method để xác định action, nhưng phải **parse ID an toàn** và đọc resource authoritative trước khi hỏi PDP.

Ưu điểm: chặn request sớm, không cho controller chạy nếu deny. Rủi ro: nghiệp vụ có thể được gọi từ scheduler, message consumer hoặc một service không đi qua filter chain. Vì vậy với tác vụ ghi nhạy cảm, **bảo vệ service/domain** vẫn cần thiết.

### 5.2. Method Security

Tạo `AuthorizationManager<MethodInvocation>`, rồi đưa vào `AuthorizationManagerBeforeMethodInterceptor` với pointcut khớp method cần bảo vệ.

Ưu điểm:

- Bảo vệ service dù caller đến từ HTTP, batch, scheduled job hoặc Java code đi qua Spring proxy.
- Nhận đúng arguments của method, có thể lấy resource ID và action.
- Phù hợp với policy có phụ thuộc trạng thái dữ liệu nghiệp vụ.
- Có thể test qua `@SpringBootTest` + `@WithMockUser`.

Rủi ro: self-invocation (`this.securedMethod()`), `new Service(...)`, method không được AOP proxy intercept hoặc advisor/pointcut cấu hình sai sẽ bỏ qua enforcement. Phải kiểm thử qua bean Spring thật.

**Khi nào dùng cả hai?** HTTP manager để lọc đường vào và method manager để bảo vệ use case. Nếu cả hai gọi remote PDP, có thể nhân đôi latency; thiết kế điều phối/caching được kiểm soát thay vì bỏ lớp bảo vệ quan trọng.

## 6. Phương pháp tích hợp Method Security

Có ba lựa chọn thường gặp:

| Cách | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| `@PreAuthorize` gọi bean policy | Đơn giản, muốn giữ annotation SpEL | `@PreAuthorize("@policyGuard.canApprove(authentication, #id)")` |
| Custom `AuthorizationManager<MethodInvocation>` + advisor | Muốn logic Java rõ ràng, reuse, audit/tổ hợp manager | `@RequiresInvoiceApproval` và `AuthorizationManagerBeforeMethodInterceptor` |
| Thay `PreAuthorizeAuthorizationManager` của toàn ứng dụng | Muốn thay hành vi annotation sẵn có | `@EnableMethodSecurity(prePostEnabled=false)` + custom advisors |

Bài này dùng **lựa chọn thứ hai** để minh họa đúng `AuthorizationManager`. Không ghi đè toàn bộ `@PreAuthorize` mặc định nếu không có nhu cầu: thay đổi rộng có thể vô hiệu hóa annotations cũ và tăng rủi ro.

### 6.1. Cách kết hợp static authority và dynamic policy

Quy tắc mong muốn:

```text
ALLOW = authenticated
        AND hasAuthority("invoice:approve")
        AND PDP(actor, invoice, "INVOICE_APPROVE") == ALLOW
```

Có hai cách đáng cân nhắc:

1. Manager custom kiểm tra cả authority tĩnh và response PDP, luôn trả ALLOW hoặc DENY rõ ràng.
2. Dùng `AuthorizationManagers.allOf(...)` để kết hợp `AuthorityAuthorizationManager` và custom manager.

Để demo dễ chạy và không vướng biến thể abstain, **manager custom áp dụng cả hai điều kiện**. Mục 10 trình bày cách compose.

## 7. Demo hoàn chỉnh: AuthorizationManager gọi dịch vụ quyết định quyền

Dự án sử dụng **Java 17**, **Spring Boot 3.5.8** và các API Spring Security 6.5.x. `PolicyDecisionClient` là ranh giới PDP; implementation demo `InProcessPdp` chạy trong process để kiểm thử có kết quả xác định, **chưa gọi một PDP HTTP thật**.

Quan trọng: dù PDP demo nằm cùng process, kiến trúc manager -> `PolicyDecisionClient` -> policy vẫn giống cách bạn tích hợp remote PDP. Mục 11 giải thích chuyển sang HTTP/gRPC trong production.

### 7.1. Cấu trúc dự án

```text
authorization-manager-pdp-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── AuthorizationManagerPdpApplication.java
    │   ├── Invoice.java
    │   ├── ActorDirectory.java
    │   ├── InvoiceStore.java
    │   ├── PolicyDecisionClient.java
    │   ├── InProcessPdp.java
    │   ├── RequiresInvoiceApproval.java
    │   ├── InvoiceApprovalManager.java
    │   ├── MethodSecurityConfig.java
    │   └── InvoiceService.java
    └── test/java/demo/
        └── InvoiceSecurityTest.java
```

Đây là ví dụ **không dùng HTTP**, chạy bằng `CommandLineRunner` và thử trên Spring-managed `InvoiceService`. Không cần database vì `InvoiceStore` lưu bản ghi trong memory; khi chuyển sang production phải sử dụng transaction/locking DB như mục 12.

### 7.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'authorization-manager-pdp-demo'
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

`spring-boot-starter-security` mang các module authorization và AOP cần thiết; Spring Boot quản lý versions của Spring Framework/Spring Security. Code mẫu dành cho Spring Boot 3.5.x. Nếu dự án đã nâng lên Spring Boot 4/Spring Security 7, phải kiểm tra lại API `AuthorizationManager` theo version đó.

### 7.3. Model hóa hóa đơn

**`src/main/java/demo/Invoice.java`:**

```java
package demo;

public record Invoice(
        Long id,
        String tenantId,
        String creatorId,
        long amount,
        Status status) {

    public enum Status {
        PENDING,
        APPROVED
    }
}
```

`tenantId`, `creatorId`, `amount`, `status` ở đây là facts từ **server store**, không phải dữ liệu để client tự khai nhằm tác động PDP.

### 7.4. User directory và identity được xác minh

**`src/main/java/demo/ActorDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record Actor(String userId, String tenantId, long approvalLimit) {
}

@Component
public class ActorDirectory {

    private final Map<String, Actor> actors = Map.of(
        "alice", new Actor("u-alice", "T1", 500),
        "bob",   new Actor("u-bob", "T1", 1000),
        "carol", new Actor("u-carol", "T2", 900)
    );

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public Actor require(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted user");
        }

        Actor actor = actors.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException(
                "User has no trusted tenant mapping");
        }
        return actor;
    }
}
```

`Actor` là record package-private trong cùng file; Java cho phép một file có một public top-level type và các package-private types khác. Tất cả file demo nằm trong package `demo`.

Directory cố định chỉ dùng cho học và test. Với JWT/OIDC production, map stable `issuer + subject`/user ID nội bộ tới tenant membership, approval limit và account status; không dùng `getName()` nếu nó có thể trùng giữa tenant và không được chuẩn hóa.

`AnonymousAuthenticationToken` có thể báo `isAuthenticated() == true`, vì vậy phải phân biệt anonymous bằng `AuthenticationTrustResolver`, không chỉ đọc boolean thô.

### 7.5. Kho hóa đơn in-memory

**`src/main/java/demo/InvoiceStore.java`:**

```java
package demo;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

@Component
public class InvoiceStore {

    private final Map<Long, Invoice> invoices = new HashMap<>();

    public InvoiceStore() {
        invoices.put(101L, new Invoice(
            101L, "T1", "u-bob", 250, Invoice.Status.PENDING));
        invoices.put(102L, new Invoice(
            102L, "T2", "u-service", 400, Invoice.Status.PENDING));
        invoices.put(103L, new Invoice(
            103L, "T1", "u-bob", 700, Invoice.Status.PENDING));
        invoices.put(104L, new Invoice(
            104L, "T1", "u-bob", 200, Invoice.Status.APPROVED));
        invoices.put(105L, new Invoice(
            105L, "T1", "u-alice", 100, Invoice.Status.PENDING));
        invoices.put(106L, new Invoice(
            106L, "T1", "u-bob", 120, Invoice.Status.PENDING));
    }

    public synchronized Invoice snapshot(Long id) {
        return invoices.get(id);
    }

    public synchronized String approveIfAllowed(
            Long id,
            Actor actor,
            PolicyDecisionClient policyClient) {

        Invoice current = invoices.get(id);
        if (current == null) {
            throw new AccessDeniedException("Resource unavailable");
        }

        try {
            PolicyVerdict verdict = policyClient.decide(
                new DecisionInput(
                    actor, "INVOICE_APPROVE", current)
            );

            if (verdict != PolicyVerdict.ALLOW) {
                throw new AccessDeniedException(
                    "Dynamic policy denied operation");
            }
        } catch (PolicyUnavailableException unavailable) {
            throw new AccessDeniedException(
                "Policy decision unavailable");
        }

        invoices.put(
            id,
            new Invoice(
                current.id(),
                current.tenantId(),
                current.creatorId(),
                current.amount(),
                Invoice.Status.APPROVED
            )
        );

        return "APPROVED";
    }
}
```

**Vì sao kiểm tra lại policy ở `approveIfAllowed`?** Interceptor đánh giá policy **trước khi** gọi service. Giữa lần đó và lúc đổi trạng thái, một thread khác có thể đã phê duyệt hoặc thay resource. Store demo dùng `synchronized` trên cùng instance để kiểm tra lại **và** đổi trạng thái nguyên tử trong một process.

Ở production đa node, `synchronized` **không đủ**. Cần transaction, row lock/conditional UPDATE, policy-version và giao thức revoke nhất quán với nguồn PDP. Điều đó được trình bày ở mục 12.

### 7.6. Hợp đồng của Policy Decision Client

**`src/main/java/demo/PolicyDecisionClient.java`:**

```java
package demo;

record DecisionInput(
    Actor actor,
    String action,
    Invoice invoice) {
}

enum PolicyVerdict {
    ALLOW,
    DENY,
    NOT_APPLICABLE,
    INDETERMINATE
}

interface PolicyDecisionClient {
    PolicyVerdict decide(DecisionInput input);
}

final class PolicyUnavailableException extends RuntimeException {

    PolicyUnavailableException(String message) {
        super(message);
    }
}
```

`DecisionInput` chứa **actor đã qua directory** và **invoice từ server store**. `PolicyVerdict` có bốn trạng thái để mô phỏng semantics một PDP bên ngoài.

`PolicyDecisionClient` là interface package-private, đủ để các thành phần `demo` inject theo type. Trong dự án thật, có thể tách client/api models vào package riêng, thêm requestId, policyVersion, obligation và resourceVersion.

### 7.7. Dịch vụ policy nội bộ mô phỏng PDP

**`src/main/java/demo/InProcessPdp.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Component;

@Component
public class InProcessPdp implements PolicyDecisionClient {

    private final AtomicBoolean available =
        new AtomicBoolean(true);

    public void setAvailable(boolean value) {
        available.set(value);
    }

    @Override
    public PolicyVerdict decide(DecisionInput input) {

        if (!available.get()) {
            throw new PolicyUnavailableException(
                "Simulated PDP outage");
        }

        if (input == null
                || input.actor() == null
                || input.invoice() == null
                || !"INVOICE_APPROVE".equals(input.action())) {
            return PolicyVerdict.NOT_APPLICABLE;
        }

        Actor actor = input.actor();
        Invoice invoice = input.invoice();

        if (!actor.tenantId().equals(invoice.tenantId())) {
            return PolicyVerdict.DENY;
        }

        if (invoice.status() != Invoice.Status.PENDING) {
            return PolicyVerdict.DENY;
        }

        if (invoice.amount() > actor.approvalLimit()) {
            return PolicyVerdict.DENY;
        }

        if (actor.userId().equals(invoice.creatorId())) {
            return PolicyVerdict.DENY;
        }

        return PolicyVerdict.ALLOW;
    }
}
```

Các điều kiện nghiệp vụ:

```text
ALLOW =
  actor.tenant == invoice.tenant
  AND invoice.status == PENDING
  AND invoice.amount <= actor.approvalLimit
  AND actor.userId != invoice.creatorId
```

**Điểm quan trọng:** `InProcessPdp` **không tự lấy role từ client**. `AuthorizationManager` sẽ chặn thiếu authority `invoice:approve` trước khi gọi PDP. Trong một triển khai PDP tách process, role/authority đã được xác minh cũng nên được thể hiện trong policy request theo hợp đồng tin cậy giữa services.

`setAvailable(false)` chỉ dùng để kiểm thử hành vi fail-closed. Trong production, timeout, HTTP 5xx, invalid response hoặc circuit breaker open cũng phải dẫn tới hành vi từ chối/không thực hiện mutation.

### 7.8. Annotation cho phương thức được bảo vệ

**`src/main/java/demo/RequiresInvoiceApproval.java`:**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RequiresInvoiceApproval {
}
```

Annotation này là marker: “Phương thức này cần đánh giá policy phê duyệt hóa đơn”. Bản demo giả định phương thức được gắn marker có **đúng một tham số `Long invoiceId`**. Trong dự án lớn, nên có một adapter/factory xác định resource ID rõ ràng, không phụ thuộc vào thứ tự arguments nếu method signatures đa dạng.

### 7.9. Custom `AuthorizationManager<MethodInvocation>`

**`src/main/java/demo/InvoiceApprovalManager.java`:**

```java
package demo;

import java.util.function.Supplier;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class InvoiceApprovalManager
        implements AuthorizationManager<MethodInvocation> {

    private final ActorDirectory directory;
    private final InvoiceStore store;
    private final PolicyDecisionClient policyClient;

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public InvoiceApprovalManager(
            ActorDirectory directory,
            InvoiceStore store,
            PolicyDecisionClient policyClient) {
        this.directory = directory;
        this.store = store;
        this.policyClient = policyClient;
    }

    @Override
    @SuppressWarnings("deprecation")
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            MethodInvocation invocation) {

        Authentication actorAuth =
            authentication == null ? null : authentication.get();

        if (actorAuth == null
                || !actorAuth.isAuthenticated()
                || trustResolver.isAnonymous(actorAuth)) {
            return deny();
        }

        boolean hasFunctionalAuthority = actorAuth.getAuthorities()
            .stream()
            .anyMatch(a ->
                "invoice:approve".equals(a.getAuthority()));

        if (!hasFunctionalAuthority) {
            return deny();
        }

        // Fail closed nếu manager bị gọi với method
        // không thuộc contract do ứng dụng quản lý.
        if (invocation == null
                || !invocation.getMethod()
                    .isAnnotationPresent(
                        RequiresInvoiceApproval.class)) {
            return deny();
        }

        Object[] args = invocation.getArguments();

        if (args.length != 1 || !(args[0] instanceof Long id)) {
            return deny();
        }

        try {
            Actor actor = directory.require(actorAuth);
            Invoice invoice = store.snapshot(id);

            if (invoice == null) {
                return deny();
            }

            PolicyVerdict verdict = policyClient.decide(
                new DecisionInput(
                    actor,
                    "INVOICE_APPROVE",
                    invoice
                )
            );

            // Chỉ ALLOW mới tạo quyết định granted.
            return new AuthorizationDecision(
                verdict == PolicyVerdict.ALLOW
            );
        } catch (AccessDeniedException | PolicyUnavailableException denied) {
            return deny();
        }
    }

    private static AuthorizationDecision deny() {
        return new AuthorizationDecision(false);
    }
}
```

**Những điểm kỹ thuật cần đọc kỹ:**

1. Manager nhận `Supplier<Authentication>` của Spring, **không** dùng username client truyền vào.
2. Nó phân biệt anonymous, yêu cầu authority tĩnh và kiểm tra marker annotation.
3. ID phải là `Long` từ method arguments; không nhận object tùy ý hoặc path string chưa parse.
4. `InvoiceStore.snapshot` lấy bản ghi server. Nếu không tìm thấy, **deny**.
5. PDP trả `ALLOW`, `DENY`, `NOT_APPLICABLE` hoặc `INDETERMINATE`. Chỉ `ALLOW` tạo `AuthorizationDecision(true)`.
6. PDP không sẵn sàng -> `PolicyUnavailableException` -> **deny**; không thực hiện service body.
7. `check` **không trả `null`**. Quyết định abstain có thể được manager phối hợp hiểu khác nhau; demo chủ động fail closed.
8. `@SuppressWarnings("deprecation")` chỉ để giảm cảnh báo từ `check(...)` trong Spring Security 6.5; **không có nghĩa nên bỏ migration sang `authorize(...)` khi nâng major version**.

Nếu một implementation remote trả lỗi không phải `PolicyUnavailableException`, nó phải chuẩn hóa lỗi transport/schema thành exception phù hợp **trước khi** đưa kết quả vào manager. Lỗi runtime không được bị diễn giải thành `ALLOW`; nên log/monitor thất bại hệ thống với correlation ID và ẩn thông tin nhạy cảm.

### 7.10. Đăng ký Spring Method Security advisor

**`src/main/java/demo/MethodSecurityConfig.java`:**

```java
package demo;

import org.springframework.aop.Advisor;
import org.springframework.aop.Pointcut;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor invoiceApprovalAdvisor(
            InvoiceApprovalManager authorizationManager) {

        Pointcut pointcut =
            AnnotationMatchingPointcut.forMethodAnnotation(
                RequiresInvoiceApproval.class
            );

        return new AuthorizationManagerBeforeMethodInterceptor(
            pointcut, authorizationManager
        );
    }
}
```

Điểm quan trọng là **advisor** có cả:

- Pointcut xác định **method nào bị intercept**.
- Manager xác định **quyết định quyền** cho `MethodInvocation` tương ứng.

`@EnableMethodSecurity` đảm bảo method security infrastructure hoạt động. `static @Bean` với role infrastructure là pattern giúp advisor được công bố đúng giai đoạn; trong ứng dụng có nhiều advisors, cần kiểm thử thứ tự và các annotation khác.

**Không áp logic của manager cho mọi method rồi đoán ID từ argument đầu tiên**. Một pointcut hẹp giảm nguy cơ ảnh hưởng nhầm các service khác và giúp code review được ranh giới bảo mật.

Nếu method được khai báo ở interface nhưng annotation chỉ đặt ở implementation (hoặc ngược lại), Spring proxy/method resolution có thể khác giữa JDK proxy và CGLIB. Demo dùng class cụ thể, không implement service interface; trong sản phẩm phải kiểm thử điểm match trên cấu trúc thật.

### 7.11. Service thực hiện nghiệp vụ và kiểm tra lại

**`src/main/java/demo/InvoiceService.java`:**

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private final ActorDirectory directory;
    private final InvoiceStore store;
    private final PolicyDecisionClient policyClient;

    public InvoiceService(
            ActorDirectory directory,
            InvoiceStore store,
            PolicyDecisionClient policyClient) {
        this.directory = directory;
        this.store = store;
        this.policyClient = policyClient;
    }

    @RequiresInvoiceApproval
    public String approve(Long invoiceId) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        Actor actor = directory.require(authentication);

        // Kiểm tra policy lại trong critical section của store.
        return store.approveIfAllowed(
            invoiceId, actor, policyClient
        );
    }
}
```

Đây là **lớp thực thi quyền và dữ liệu**, không phải custom logic thay manager. Manager chặn sớm khi thiếu quyền; service giữ domain rule và recheck trong phần cập nhật nguyên tử để tránh trạng thái thay đổi giữa bước authorize và mutation.

Nếu thiếu advisor, method body vẫn có business policy guard; nhưng **authority `invoice:approve` không được service lặp lại**. Vì thế cần integration test cho trường hợp actor có policy conditions hợp lệ nhưng thiếu authority. Test này sẽ phát hiện advisor bị bỏ qua.

Trong sản phẩm thật, nên đặt invariant bảo mật quan trọng ở application/domain/database boundary đủ mạnh cho cả các đường gọi không qua Spring AOP. Không dùng in-memory `synchronized` như bằng chứng quyền đa node.

### 7.12. Chương trình Spring Boot và kịch bản

**`src/main/java/demo/AuthorizationManagerPdpApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
public class AuthorizationManagerPdpApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            AuthorizationManagerPdpApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(
            InvoiceService service,
            InProcessPdp pdp) {

        return args -> {
            try {
                as("alice", "invoice:view");
                denied("ALICE_NO_AUTHORITY_101",
                    () -> service.approve(101L));

                as("alice", "invoice:approve");
                System.out.println("ALICE_101: "
                    + service.approve(101L));

                denied("ALICE_REPEAT_101",
                    () -> service.approve(101L));

                denied("ALICE_CROSS_TENANT_102",
                    () -> service.approve(102L));

                denied("ALICE_OVER_LIMIT_103",
                    () -> service.approve(103L));

                denied("ALICE_ALREADY_APPROVED_104",
                    () -> service.approve(104L));

                denied("ALICE_SELF_APPROVAL_105",
                    () -> service.approve(105L));

                as("bob", "invoice:view");
                denied("BOB_NO_AUTHORITY_106",
                    () -> service.approve(106L));

                as("carol", "invoice:approve");
                System.out.println("CAROL_T2_102: "
                    + service.approve(102L));

                as("alice", "invoice:approve");
                pdp.setAvailable(false);

                denied("PDP_DOWN_ALICE_106",
                    () -> service.approve(106L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void as(
            String username, String authority) {

        var authentication =
            new UsernamePasswordAuthenticationToken(
                username,
                "demo-only",
                List.of(
                    new SimpleGrantedAuthority(authority))
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(
            String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`UsernamePasswordAuthenticationToken` được tự dựng với authority đã chọn **chỉ để mô phỏng trong CLI/test**. Nó **không phải authentication provider** để dùng trong HTTP production. Ở web thực, Spring Security filters xác thực credentials/session/JWT và tạo `Authentication` tin cậy; không đọc role do caller khai rồi tạo token đặc quyền.

Chạy tại thư mục chứa `build.gradle`:

```bash
./gradlew bootRun
```

PowerShell:

```bash
.\gradlew.bat bootRun
```

Nếu dự án chưa có Gradle Wrapper, dùng Gradle phù hợp đã cài hoặc tạo wrapper trước.

**Các dòng do `System.out.println` của ứng dụng dự kiến là** (không tính log Spring/Gradle):

```text
ALICE_NO_AUTHORITY_101: DENIED
ALICE_101: APPROVED
ALICE_REPEAT_101: DENIED
ALICE_CROSS_TENANT_102: DENIED
ALICE_OVER_LIMIT_103: DENIED
ALICE_ALREADY_APPROVED_104: DENIED
ALICE_SELF_APPROVAL_105: DENIED
BOB_NO_AUTHORITY_106: DENIED
CAROL_T2_102: APPROVED
PDP_DOWN_ALICE_106: DENIED
```

**Giải thích:**

- Alice thiếu authority `invoice:approve` nên manager chặn trước khi gọi PDP dù hóa đơn 101 thỏa điều kiện nghiệp vụ.
- Sau khi có authority, Alice duyệt 101 thành công vì tenant T1, `PENDING`, hạn mức 500 đủ cho số tiền 250, maker là Bob.
- Lần duyệt lại 101 bị từ chối do trạng thái đã là `APPROVED`.
- Hóa đơn 102 thuộc T2 nên Alice bị từ chối dù có role chức năng.
- Hóa đơn 103 có số tiền 700 vượt limit 500 của Alice.
- Hóa đơn 104 đã `APPROVED`, không thể duyệt lại.
- Hóa đơn 105 do chính Alice tạo, vi phạm maker–checker.
- Bob thiếu authority nên không vào service, bất kể trạng thái invoice 106.
- Carol thuộc T2, hạn mức 900 và invoice 102 do service tạo, nên được phép duyệt.
- Khi PDP mô phỏng không sẵn sàng, Alice bị từ chối trên invoice 106; không có fallback sang `permitAll`.

**Lưu ý:** Đây là stdout **dự kiến theo mã nguồn**, không phải kết quả đã chạy được xác nhận trong môi trường của bài viết. Hành vi được kiểm chứng đầy đủ sau khi chạy Gradle/test và kiểm tra Spring Method Security advisor thực sự được áp dụng.

## 8. Integration test với Spring Method Security thật

**`src/test/java/demo/InvoiceSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class InvoiceSecurityTest {

    @Autowired
    InvoiceService service;

    @Autowired
    InvoiceStore store;

    @Autowired
    InProcessPdp pdp;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:approve"
    )
    void allowsOnlyWhenStaticAndDynamicPoliciesPass() {
        assertEquals("APPROVED", service.approve(101L));
        assertEquals(
            Invoice.Status.APPROVED,
            store.snapshot(101L).status()
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:view"
    )
    void detectsMissingAuthorizationManagerAdvisor() {
        // Chính sách nghiệp vụ của invoice 101 cho phép Alice,
        // nhưng cô không có authority invoice:approve.
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(101L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:approve"
    )
    void deniesCrossTenantAndOverLimitAndMakerChecker() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(102L)
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(103L)
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(104L)
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(105L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(103L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "carol",
        authorities = "invoice:approve"
    )
    void tenantT2ApproverCanApproveItsOwnScope() {
        assertEquals("APPROVED", service.approve(102L));
        assertEquals(
            Invoice.Status.APPROVED,
            store.snapshot(102L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:approve"
    )
    void failsClosedWhenPdpIsUnavailable() {
        pdp.setAvailable(false);

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(106L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(106L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "ghost",
        authorities = "invoice:approve"
    )
    void userWithoutTrustedDirectoryMappingIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(101L).status()
        );
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDeniedEvenIfTokenIsAuthenticated() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test dùng `@SpringBootTest` nên tạo Spring application context, bean advisor, service proxy và policy client **thật của ví dụ**. `@WithMockUser` thiết lập security context cho mỗi test; `@DirtiesContext` reset dữ liệu hóa đơn/PDP sau từng test. Runner chỉ bật khi profile khác `test`, nên test không vô tình chạy kịch bản CLI.

**Vì sao test `detectsMissingAuthorizationManagerAdvisor` đặc biệt quan trọng?** Alice có đầy đủ điều kiện dynamic cho invoice 101 nhưng **thiếu authority**. Nếu custom advisor không được áp dụng, service body vẫn có thể cho Alice duyệt qua policy nội bộ; test sẽ fail. Chỉ test các trường hợp dynamic DENY không thể chứng minh advisor thật sự hoạt động.

### 8.1. Ma trận quyết định cần giữ khi phát triển tiếp

| Người gọi | Authority | Invoice | PDP đánh giá | Kết quả |
| --- | --- | ---: | --- | --- |
| Alice/T1 | `invoice:view` | 101 | Dynamic allow nếu được hỏi | **DENY** trước khi gọi PDP |
| Alice/T1 | `invoice:approve` | 101, PENDING | Allow | **ALLOW** |
| Alice/T1 | `invoice:approve` | 101, sau approve | Deny – không còn PENDING | **DENY** |
| Alice/T1 | `invoice:approve` | 102/T2 | Deny – cross tenant | **DENY** |
| Alice/T1 | `invoice:approve` | 103/700 | Deny – vượt limit 500 | **DENY** |
| Alice/T1 | `invoice:approve` | 104/APPROVED | Deny – trạng thái | **DENY** |
| Alice/T1 | `invoice:approve` | 105 do Alice tạo | Deny – maker checker | **DENY** |
| Bob/T1 | `invoice:view` | 106 | Chưa cần hỏi PDP | **DENY** |
| Carol/T2 | `invoice:approve` | 102/T2 | Allow | **ALLOW** |
| Alice/T1 | `invoice:approve` | 106, PDP down | Không có quyết định tin cậy | **DENY** |

Với remote PDP thật, nên mở rộng test matrix: HTTP 500, connection timeout, TLS error, malformed JSON, `NOT_APPLICABLE`, `INDETERMINATE`, policy version mismatch, stale cache, caller không có mapping tenant, mất authentication, resource không tồn tại và grant bị thu hồi đồng thời.

## 9. Tích hợp vào HTTP `SecurityFilterChain`

Method adapter là lựa chọn tốt cho use case; đôi khi bạn cũng muốn kiểm tra policy sớm ngay từ route HTTP.

Một mẫu **`AuthorizationManager<RequestAuthorizationContext>`**:

```java
// MẢNH CODE minh họa dùng cho Servlet web application.
// Cần thêm spring-boot-starter-web, các import tương ứng,
// Controller, và cấp dependency phù hợp với dự án.
final class InvoiceHttpAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ActorDirectory directory;
    private final InvoiceStore store;
    private final PolicyDecisionClient client;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    InvoiceHttpAuthorizationManager(
            ActorDirectory directory,
            InvoiceStore store,
            PolicyDecisionClient client) {
        this.directory = directory;
        this.store = store;
        this.client = client;
    }

    @Override
    @SuppressWarnings("deprecation")
    public AuthorizationDecision check(
            Supplier<Authentication> authSupplier,
            RequestAuthorizationContext context) {

        Authentication auth =
            authSupplier == null ? null : authSupplier.get();

        if (auth == null || trustResolver.isAnonymous(auth)
                || !auth.isAuthenticated()
                || auth.getAuthorities().stream().noneMatch(
                    a -> "invoice:approve".equals(a.getAuthority()))) {
            return new AuthorizationDecision(false);
        }

        Object rawId = context.getVariables().get("id");
        if (!(rawId instanceof String text)) {
            return new AuthorizationDecision(false);
        }

        try {
            Long id = Long.valueOf(text);
            Invoice invoice = store.snapshot(id);
            if (invoice == null) {
                return new AuthorizationDecision(false);
            }

            Actor actor = directory.require(auth);
            PolicyVerdict verdict = client.decide(
                new DecisionInput(
                    actor, "INVOICE_APPROVE", invoice));

            return new AuthorizationDecision(
                verdict == PolicyVerdict.ALLOW
            );
        } catch (NumberFormatException
                | AccessDeniedException
                | PolicyUnavailableException denied) {
            return new AuthorizationDecision(false);
        }
    }
}
```

Ví dụ wiring mảnh:

```java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        InvoiceHttpAuthorizationManager invoiceAuthz)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            HttpMethod.POST,
            "/api/invoices/{id}/approve"
        ).access(invoiceAuthz)
        .anyRequest().denyAll()
    );

    return http.build();
}
```

**Lưu ý:**

- `context.getVariables()` phụ thuộc `RequestMatcher` có hỗ trợ path variables; nếu route/matcher thực tế không cung cấp `id`, manager trả **DENY**, không cố tự đoán từ path string tùy ý.
- `RequestAuthorizationContext` không phải `MethodInvocation`, nên không dùng trực tiếp method manager như HTTP manager mà thiếu adapter.
- HTTP manager chỉ chạy khi request đi qua filter chain được cấu hình. Scheduler hoặc lời gọi service trực tiếp **không** đi qua nó.
- Không tắt CSRF mặc định nếu ứng dụng dùng browser cookie/session. Với API bearer-only, đánh giá threat model trước khi chọn cơ chế CSRF.
- Nếu HTTP và Method Security đều gọi PDP cho một hành động, tính latency có thể gấp đôi. Tối ưu cần giữ security boundary và invalidation đúng.

Thực tiễn thường là **HTTP coarse-grained guard** (authenticated, route/authority) và **method policy guard** xét dữ liệu tin cậy, tránh hai lần remote call nếu không thật cần thiết.

## 10. Kết hợp nhiều `AuthorizationManager` bằng `AuthorizationManagers`

Spring Security có:

```java
AuthorizationManagers.allOf(...);
AuthorizationManagers.anyOf(...);
AuthorizationManagers.not(...);
```

**`allOf`** phù hợp với rule dạng AND. Ví dụ mảnh cấu hình:

```java
// MẢNH CODE minh họa, không phải bean thay thế trực tiếp
// cho MethodSecurityConfig ở mục 7.
AuthorizationManager<MethodInvocation> staticRule =
    AuthorityAuthorizationManager.<MethodInvocation>hasAuthority(
        "invoice:approve"
    );

AuthorizationManager<MethodInvocation> combined =
    AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        staticRule,
        dynamicInvoiceManager
    );
```

Ở đây:

- `staticRule` kiểm tra authority.
- `dynamicInvoiceManager` kiểm tra PDP.
- `new AuthorizationDecision(false)` là **default DENY nếu mọi delegate đều abstain** theo overload có tham số default (có từ Spring Security 6.3).
- Cần bảo đảm các delegate nhạy cảm **không** abstain trên trường hợp không hợp lệ, vì ý nghĩa “abstain” trong composition có thể khác “deny”.

**Bẫy quan trọng:** `AuthorizationManagers.allOf(manager1, manager2)` ở một số phiên bản chấp nhận các manager **abstain** và có thể granted khi toàn bộ abstain. Vì vậy đừng nghĩ `null` đồng nghĩa DENY rồi trả null mỗi khi PDP timeout.

**`anyOf`** chỉ phù hợp khi **một trong các chính sách đủ để cho phép** theo đặc tả. Không đặt `isAdmin` và `tenantPolicy` vào `anyOf` nếu admin không được truy cập chéo tenant. Cách kết hợp AND/OR phải đến từ security requirements, không phải từ tính tiện dụng của API.

### 10.1. Không dùng AND cho mọi trường hợp một cách máy móc

Một hệ thống có rule:

```text
ALLOW =
  sameTenant
  AND (
        owner
        OR sharedByAcl
      )
  AND notDeleted
```

Có thể biểu diễn bằng cách compose `allOf(sameTenant, anyOf(owner, sharedByAcl), notDeleted)` nhưng phải định nghĩa mặc định **deny** ở các điểm thiếu dữ liệu. Nếu có deny-overrides/obligations/phê duyệt nhiều cấp, có thể phù hợp hơn khi PDP thực hiện phép kết hợp và manager chỉ thực thi decision cuối.

## 11. Đổi `InProcessPdp` sang remote PDP thật

Trong production, `PolicyDecisionClient` có thể triển khai bằng `RestClient`, gRPC hoặc SDK của policy engine. Không thêm đồng thời hai `@Component` implements cùng interface nếu chưa chọn implementation qua `@Profile`, `@ConditionalOnProperty` hoặc `@Primary` có chủ đích.

### 11.1. Mẫu request/response remote

```java
// MẢNH DTO minh họa cho adapter remote; không phải file của demo.
record RemoteDecisionRequest(
    String subjectId,
    String tenantId,
    String action,
    Long resourceId,
    String resourceTenant,
    String resourceCreator,
    long resourceAmount,
    String resourceStatus,
    long approvalLimit,
    String requestId
) {}

record RemoteDecisionResponse(
    String decision,
    String policyVersion,
    String decisionId,
    String reasonCode
) {}
```

Sử dụng server-side `Actor` và `Invoice` để tạo DTO, không serialize nguyên `Authentication`, HTTP request hoặc entity graph có secret.

### 11.2. `RestClient` adapter: phác thảo có fail-closed

```java
// MẢNH CODE tích hợp, KHÔNG độc lập:
// cần spring-web/RestClient, authentication service-to-service,
// cấu hình timeout, exception mapping, observability và DI.
public PolicyVerdict decide(DecisionInput input) {

    RemoteDecisionRequest request = requestFactory.fromTrusted(
        input.actor(), input.invoice(), input.action());

    RemoteDecisionResponse result;

    try {
        result = restClient.post()
            .uri("/v1/decisions")
            .body(request)
            .retrieve()
            .body(RemoteDecisionResponse.class);
    } catch (RestClientException transportProblem) {
        throw new PolicyUnavailableException(
            "Remote policy decision unavailable");
    }

    if (result == null || result.decision() == null) {
        return PolicyVerdict.INDETERMINATE;
    }

    return switch (result.decision()) {
        case "ALLOW" -> PolicyVerdict.ALLOW;
        case "DENY" -> PolicyVerdict.DENY;
        case "NOT_APPLICABLE" -> PolicyVerdict.NOT_APPLICABLE;
        default -> PolicyVerdict.INDETERMINATE;
    };
}
```

**Đây không phải file độc lập**: `restClient`, `requestFactory`, DTO classes/imports và cơ chế cấu hình chưa được định nghĩa trong project demo. Nó mô tả cách map transport failure và response lạ sang **không được cấp quyền**.

Để dùng thật:

1. Khởi tạo `RestClient` bằng **base URL cố định** do server cấu hình, không phụ thuộc request.
2. Thiết lập `connectTimeout`, `readTimeout`/request deadline và connection pool phù hợp.
3. Dùng mTLS hoặc token service-to-service có phạm vi quyền hẹp; không gửi secret người dùng tùy tiện.
4. Gắn `requestId` và ghi policy version/decision ID để truy vết.
5. Xác minh schema, trạng thái/phiên bản response, input attribute provenance.
6. Đặt circuit breaker/bulkhead để tránh nghẽn toàn bộ service khi PDP lỗi.
7. Map cả timeout, 429, 5xx, response invalid sang **deny** hoặc lỗi hạ tầng không cho thao tác thực hiện.
8. Kiểm thử offline/chaos để xác nhận **không có fallback allow**.

### 11.3. Timeout: đâu là lựa chọn hợp lý?

Timeout tùy SLA và độ nhạy của thao tác, không có một số mili-giây đúng cho mọi hệ thống. Nguyên tắc:

- Deadline PDP phải nhỏ hơn HTTP/request tổng để có thời gian từ chối/ghi audit.
- Không retry vô hạn; một request policy có thể phát nhiều calls và gây thác lũ.
- Với READ ít rủi ro, có thể cân nhắc cache policy hợp lệ có bounded TTL nếu contract cho phép.
- Với WRITE/APPROVE/TRANSFER/DELETE nhạy cảm, đừng dùng stale ALLOW sau khi PDP down nếu không có chính sách **stale-while-revalidate** được phê duyệt và cơ chế revoke tương ứng.
- Khi circuit breaker mở, **không tự chuyển sang default allow** để “giữ tính sẵn sàng”.

Một hệ thống muốn hoạt động offline phải **đặc tả trước** phạm vi operations và thời hạn policy snapshot; đó là một security trade-off có chủ đích, không phải nhánh `catch (Exception) { return true; }`.

## 12. Dynamic policy và TOCTOU: ALLOW không phải giấy phép vĩnh viễn

Bài toán lớn nhất của một PDP tách rời là **quyết định đúng tại lúc T1** có thể đã cũ tại lúc T2:

```text
T1: PDP ALLOW invoice#101 khi PENDING, hạn mức 500
T2: Admin hạ hạn mức Alice còn 100
T3: Worker gọi approve(invoice#101)
T4: DB cập nhật status = APPROVED
```

Một `AuthorizationManagerBeforeMethodInterceptor` không tự tạo transaction chung giữa remote PDP và resource DB. `@PreAuthorize` hay custom advisor có thể chạy trước transaction của service. Vì vậy:

- Chỉ dùng manager để **chặn sớm**.
- Khi ghi, kiểm tra lại **resource state, tenant, owner/creator, amount, permission và policy version** gần điểm mutation theo contract.
- Sử dụng conditional UPDATE, row locks, optimistic version hoặc policy epoch để tránh cập nhật khi dữ liệu đã đổi.
- Nếu policy ở service khác và cần revoke tức thời, phải có giao thức nhất quán giữa PDP và DB, không chỉ thêm `@Transactional` cục bộ.

### 12.1. Conditional UPDATE

Ví dụ SQL minh họa:

```sql
UPDATE invoices
SET status = 'APPROVED',
    approved_by = :trustedApproverId,
    version = version + 1
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId
  AND status = 'PENDING'
  AND amount <= :trustedApprovalLimit
  AND created_by <> :trustedApproverId
  AND version = :expectedVersion;
```

Lệnh này guard các facts **nằm trong cùng hàng resource**. Kiểm tra affected rows: `1` thành công, `0` là không đủ điều kiện hoặc version đã thay đổi. Với role/tenant/limit lấy từ bảng khác, cần đảm bảo chúng có consistency theo policy đã thỏa thuận.

### 12.2. Khóa và kiểm tra lại đối với grant động

Nếu quyền duyệt phụ thuộc bảng `approval_grants`, `acl_entry` hoặc membership được cập nhật riêng:

```text
Transaction APPROVE                 Transaction REVOKE
--------------------------------    --------------------------------
Lock invoice row                    Lock same invoice row
Read grant/policy version           Modify grant / bump authzVersion
Recheck dynamic authorization       Commit
Conditional update invoice
Commit
```

Thứ tự có thể đảo, nhưng **mọi đường thay grant ảnh hưởng invoice phải dùng cùng giao thức khóa/version**. Nếu revoke trực tiếp sửa bảng grant mà không lock invoice, writer đang giữ invoice lock **không bảo vệ được quyền**.

Đối với Redis/cache và nhiều node, `synchronized` trong demo chỉ an toàn **trong một JVM**. Quyết định quyền có TTL/version phải được invalidated khi actor role, tenant membership, resource status hoặc policy thay đổi.

### 12.3. Policy decision token và phiên bản

Một số hệ thống PDP trả:

```json
{
  "decision": "ALLOW",
  "policyVersion": "approval-policy-v12",
  "resourceVersion": 3,
  "expiresAt": "2026-11-05T10:20:30Z"
}
```

Đây là ví dụ minh họa, không phải yêu cầu API chuẩn của Spring. Nếu mang quyết định tới bước ghi, phải kiểm tra lại:

- Decision thuộc đúng `subject + tenant + action + resource`.
- `policyVersion` và `resourceVersion` còn hiệu lực theo authoritative source.
- Token/decision được xác thực/không bị giả mạo.
- `expiresAt` không quá hạn và clock-skew được xử lý.
- Trạng thái nghiệp vụ hiện tại vẫn hợp lệ.

**Không dựa duy nhất vào TTL ngắn** để bảo đảm revoke tức thời. Với tác vụ cực nhạy cảm có thể cần chính sách “fresh PDP decision trong transaction” hoặc approval workflow nhiều người.

## 13. Caching và chính sách động

Cache có thể giảm latency PDP nhưng làm tăng nguy cơ stale authorization. Một cache key hợp lý thường cần:

```text
(subjectId,
 tenantId,
 action,
 resourceType,
 resourceId,
 resourceVersion,
 policyVersion,
 relevantAttributesHash)
```

Không dùng `resourceId` một mình khi quyết định phụ thuộc người dùng, tenant, hạn mức hoặc action. Nếu ID chỉ unique theo tenant, phải đưa tenant vào key; nếu decision phụ thuộc trạng thái hóa đơn, phải đưa version hoặc invalidation tương ứng.

### 13.1. Tích lũy quyền do cache sai

Ví dụ:

```text
ALICE / T1 / invoice#101 / APPROVE -> ALLOW
Cache key = "invoice:101"
BOB / T1 / invoice#101 / APPROVE -> cache hit ALLOW
```

Cache key như vậy là **lỗ hổng phân quyền**. Cũng nguy hiểm nếu cache allow của `version=3` rồi áp vào `version=4` đã bị `APPROVED` hoặc chuyển tenant.

### 13.2. Positive vs negative caching

- **ALLOW cache:** hiệu năng cao nhưng rủi ro stale grant; cân nhắc TTL ngắn, policy version và invalidation.
- **DENY cache:** có thể làm quyền mới cấp chưa có hiệu lực ngay; cần contract về độ trễ.
- **INDETERMINATE / ERROR:** không nên cache như một ALLOW; thường cần backoff/circuit-breaker.
- **Policy deploy:** mọi cache phải nhận biết `policyVersion` hoặc được flush phù hợp.

Đối với approval/payment/privileged actions, chiến lược đơn giản an toàn thường là **không cache ALLOW giữa các resource versions**, hoặc đọc lại policy ngay tại điểm mutation.

## 14. Observability và audit của PEP/PDP

Authorization failures là một nguồn tín hiệu quan trọng, nhưng phải tránh log secrets. Có thể ghi:

| Trường audit | Ví dụ |
| --- | --- |
| `requestId` | ID correlation |
| `subjectId` | Internal stable ID đã mã hóa/bảo vệ |
| `tenantId` | Tenant canonical |
| `action` | `INVOICE_APPROVE` |
| `resourceRef` | `"INVOICE:101"` với retention phù hợp |
| `decision` | ALLOW/DENY/INDETERMINATE |
| `reasonCode` | `OVER_LIMIT`, `CROSS_TENANT` |
| `policyVersion` | `approval-policy-v12` |
| `decisionLatency` | Thời gian gọi PDP |
| `enforcementPoint` | HTTP / METHOD / DOMAIN |
| `resourceVersion` | Phiên bản lúc được quyết định |
| `outcome` | MUTATION_COMMITTED / ROLLED_BACK / NOT_RUN |

**Phân biệt hai sự kiện:**

1. **Authorization decision:** PDP trả ALLOW ở T1.
2. **Business mutation:** transaction thật commit/rollback ở T2.

Một ALLOW nhưng transaction rollback không phải bằng chứng hành động đã thành công. Ngược lại, DENY mà DB state vẫn thay đổi là **lỗ hổng nghiêm trọng**. Integration tests phải assert trạng thái resource sau denial.

**Không log:** raw access token, refresh token, password, session cookie, toàn bộ invoice metadata chứa PII và request body nhạy cảm.

## 15. Phân quyền theo tenant, maker–checker và hạn mức

### 15.1. Tenant scope phải từ server

Một caller có thể gửi:

```json
{
  "invoiceId": 102,
  "tenantId": "T2",
  "actorId": "u-carol"
}
```

Nếu manager lấy `tenantId`/`actorId` này để hỏi PDP, Alice có thể giả làm Carol. Manager phải dùng identity đã xác thực và directory; invoice tenant phải được lấy từ DB.

### 15.2. Maker–checker không phải role tĩnh

Ngay cả khi một user có `invoice:approve`, policy phải chặn:

```text
invoice.creatorId == actor.userId
```

Nếu actor/creator chỉ lưu bằng username có thể trùng, dùng stable subject ID. Không so sánh display name hoặc email chưa verified.

### 15.3. Hạn mức cần đúng đơn vị

Demo dùng `long amount` và `long approvalLimit` cùng một đơn vị số nguyên để tránh lỗi số thực. Trong hệ thống thanh toán thật:

- Dùng minor units (ví dụ đồng xu) hoặc `BigDecimal` với scale/currency đúng.
- Hạn mức có thể tính theo currency, tenant, sản phẩm, loại giao dịch và thời gian.
- Không cho client tự khai hạn mức/approval roles.
- Khi policy limit thay đổi, cache/decision version phải phản ánh.
- Nếu hạn mức theo ngày hoặc tổng giao dịch, một kiểm tra read-then-write không đủ; cần transaction/atomic budget reservation.

## 16. Khi nào nên dùng `@PreAuthorize("@bean...")` thay custom manager?

Một cách ngắn hơn:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicyGuard.canApprove(authentication, #invoiceId)"
)
public String approve(Long invoiceId) {
    return invoiceService.approve(invoiceId);
}
```

Đây là **mảnh design**, không phải đoạn nằm trong demo. `invoicePolicyGuard` là bean cần viết, trả boolean theo `Authentication` và ID. Nó có thể gọi cùng `PolicyDecisionClient` đã dùng ở trên.

Ưu điểm:

- Nhanh cho một vài rule.
- Gần với Spring Method Security quen thuộc.
- Ít boilerplate advisor.

Nhược điểm:

- SpEL chứa logic phức tạp dễ khó kiểm thử/reuse.
- Có thể khó thống nhất policy mapping và audit giữa HTTP và method.
- Bypass nếu method không đi qua Spring proxy.
- Chưa có lợi thế của custom `AuthorizationManager<T>` để compose/quan sát ở cấp abstraction.

**Chọn custom `AuthorizationManager`** khi cần chuẩn hóa nhiều loại context, tái sử dụng PDP adapter, trả quyết định có cấu trúc, kiểm thử rõ ràng, kết hợp các manager hoặc tích hợp với HTTP/message authorization.

Đừng thay thế một cơ chế đang hoạt động chỉ vì “custom manager nghe hiện đại hơn”. Giá trị là ranh giới bảo mật và contract policy rõ ràng.

## 17. Lỗi thường gặp và cách sửa

| Vấn đề | Triệu chứng | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra role tĩnh | Approver phê duyệt mọi tenant/hóa đơn | Hỏi PDP bằng resource/tenant authoritative |
| Lấy `actorId` từ JSON | Client giả danh người khác | Lấy từ `Authentication` và trusted directory |
| Lấy `tenantId` từ header không verify | Truy cập chéo tenant | Verify membership trước khi tạo policy request |
| Manager trả `null` khi PDP down | Composition có thể abstain rồi allow | Explicit `AuthorizationDecision(false)` |
| Catch exception rồi return allow | PDP outage mở quyền | Fail closed, ghi log và alert |
| Response không nhận diện | `"UNKNOWN"` được hiểu là true | Chỉ map đúng `ALLOW`; mọi trạng thái khác deny |
| Thiếu timeout | Worker thread bị block kéo dài | Deadline/connection/request timeout, bulkhead |
| Retry không giới hạn | PDP overload lan sang app | Retry bounded theo request deadline |
| Cache key chỉ theo resource ID | Quyền của Alice áp cho Bob | Key theo subject/tenant/action/version |
| Cache allow sau revoke | User vẫn duyệt sau khi bị thu quyền | Version/invalidation/recheck |
| Dùng stale resource attributes | Invoice đã approved vẫn được duyệt | Snapshot có version và DB conditional write |
| Dùng `@PostAuthorize` cho write | Có thể commit trước deny | Before-method + transaction guard |
| Custom advisor không match | Method chạy mà PDP không được hỏi | Test allow và deny qua Spring-managed proxy |
| Self-invocation `this.approve()` | Bỏ qua AOP authorization | Tách secured service/bean, test đường gọi thực |
| Manager đọc tham số sai vị trí | Đánh giá resource khác | Dùng annotation contract/typed adapter |
| Policy service kiểm tra ID nhưng không tenant | BOLA/cross-tenant | Tenant-scoped resource lookup |
| Coi `isAuthenticated()` của anonymous là user thật | Anonymous bypass | AuthenticationTrustResolver/security expressions |
| `anyOf` dùng sai | Một manager allow vượt rào tenant | Phép AND ở ranh giới bắt buộc |
| ALL abstain với `allOf` | Có thể mặc định granted | Overload với default deny và explicit denials |
| Cấu hình 2 manager beans không chọn rõ | DI ambiguity | `@Qualifier`, `@Primary`, `@Profile` |
| HTTP-only policy | Scheduler/batch bypass | Method/domain guards |
| Mất policy version khi ghi | Quyết định cũ vẫn dùng | Compare version hoặc re-evaluate |
| Unit test gọi `new InvoiceService()` | Không có interceptor | `@SpringBootTest`/proxy integration |
| Test chỉ DENY | Advisor luôn deny vẫn pass | Test ALLOW, DENY và state changes |
| Audit ghi ALLOW = commit | Báo cáo sai sự kiện | Tách PDP decision và mutation outcome |

### Checklist trước khi release

1. `AuthorizationManager<T>` đúng generic type cho request hoặc method?
2. `Supplier<Authentication>` đến từ Spring Security, không từ JSON?
3. Anonymous/unknown principal bị deny?
4. `action` do server xác định và được whitelist?
5. Resource/tenant/creator/state/amount từ DB/server authoritative?
6. PDP có authentication giữa services, TLS và kiểm soát egress?
7. Client có timeout, circuit breaker và bounded retry?
8. `ALLOW` chỉ được công nhận khi response hợp lệ, đúng scope/version?
9. `DENY`, `NOT_APPLICABLE`, `INDETERMINATE`, timeout, 5xx đều fail closed?
10. Advisor/pointcut có match đúng method trên Spring proxy?
11. Có test allow/deny/missing role/cross-tenant/self-approve/over-limit?
12. Có test trạng thái DB bất biến sau denial?
13. Có recheck/conditional write/locking cho state hoặc grant thay đổi giữa check và use?
14. Có cache key theo subject/tenant/action/resource/policy version và invalidation?
15. Có audit decision + mutation outcome + policy version nhưng không log secrets?
16. Khi tăng major Spring Security, đã kiểm tra `check()`/`authorize()` migration chưa?

## 18. Bài tập

### Bài 1 – Một role nhưng hai tenants

Alice ở `T1`, có `invoice:approve`. Hóa đơn `102` thuộc `T2`. `@PreAuthorize("hasAuthority('invoice:approve')")` cho phép nhưng PDP phải trả gì?

**Đáp:** `DENY`, vì tenant của resource khác trusted tenant của actor. Chính sách chức năng và tenant là phép AND.

### Bài 2 – Policy trả `NOT_APPLICABLE`

Một request mới có action `INVOICE_EXPORT` mà PDP chỉ biết `INVOICE_APPROVE`. Manager nên trả gì?

**Đáp:** Trong contract bài này, explicit deny. Không biến “không có policy” thành allow.

### Bài 3 – Timeout PDP

Remote policy service không trả trong deadline. Nếu code có `catch (Exception) { return new AuthorizationDecision(true); }`, nguy cơ gì?

**Đáp:** Tính sẵn sàng của PDP trở thành cơ chế bypass tất cả kiểm tra quyền. Phải fail closed và phân loại sự cố.

### Bài 4 – Resource đổi sau quyết định

PDP ALLOW vì invoice `PENDING`, nhưng transaction khác đã chuyển nó sang `APPROVED` trước update. Chỉ có manager đủ không?

**Đáp:** Không. Khi ghi cần guard trạng thái/version bằng transaction/conditional UPDATE hoặc lock/recheck thích hợp.

### Bài 5 – Cache không chứa tenant

Cache key `(invoiceId, action)` chứa ALLOW của Alice. Bob gọi cùng ID. Vì sao nguy hiểm?

**Đáp:** Quyết định phụ thuộc **subject, tenant, limit và policy version**; cache key thiếu chúng có thể dùng chung kết quả qua principal.

### Bài 6 – Manager không chạy khi test

Test `@WithMockUser` gọi service bằng `new`, hay tự gọi một method nội bộ `this.approve`. Vì sao PDP không được gọi?

**Đáp:** Spring Method Security dùng AOP proxy. Phải gọi Spring-managed bean qua proxy hoặc có boundary domain độc lập để không thể bypass.

### Bài 7 – `allOf` nhưng manager trả null

Hai manager đều trả null. Có chắc request bị từ chối không?

**Đáp:** Không nên giả định. `allOf` có thể dùng semantics abstain; hãy đặt all-abstain default DENY và ưu tiên explicit DENY cho trường hợp thiếu thông tin.

### Bài 8 – HTTP-only bảo vệ approval

Controller có HTTP manager, nhưng scheduled job gọi trực tiếp service approval. Có được bảo vệ không?

**Đáp:** HTTP filter không chạy ở luồng job. Cần Method Security/domain guard hoặc một authoritative mutation path có kiểm soát.

### Bài 9 – Chuyển Spring Security 6.5 sang 7.x

Tại sao implementation override `check(...)` cần xem lại?

**Đáp:** Spring Security 6.5 đánh dấu `check` deprecated, dần chuyển sang `authorize(...)` trả `AuthorizationResult`. Major version mới có thể thay abstract contract; dùng API/version-migration docs.

### Bài 10 – PDP trả ALLOW nhưng dữ liệu tenant do client gửi

Có nên tin response?

**Đáp:** Không. PDP không thể sửa nguồn facts sai; request policy phải được xây từ verified authentication và authoritative resource attributes.

### Bài 11 – Remote PDP trả deny nhưng service đã cập nhật DB

Mã HTTP 403 có đủ chứng minh an toàn không?

**Đáp:** Không. Cần kiểm tra trạng thái DB thực tế, transaction rollback và thứ tự enforcement so với side effect.

### Bài 12 – Maker–checker và role

Một người có role `invoice:approve`, hạn mức đủ nhưng tự tạo invoice. Policy nào phải chặn?

**Đáp:** `actor.userId != invoice.creatorId`; role/limit hợp lệ không xóa quy tắc phân tách nhiệm vụ.

## 19. Tài liệu tham khảo chính thức

1. [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `AuthorizationManager`, PEP context, static/dynamic composition.
2. [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `AuthorizationManagerBeforeMethodInterceptor`, custom managers, pointcuts, proxy/annotation behavior.
3. [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): tích hợp policy agent/remote service với `AuthorizationManager<RequestAuthorizationContext>`.
4. [Spring Security 6.5 API – `AuthorizationManager<T>`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check`, `authorize`, `verify` và deprecation.
5. [Spring Security 6.5 API – `AuthorizationDecision`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationDecision.html): explicit granted/denied result.
6. [Spring Security 6.5 API – `AuthorizationManagers`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`/`anyOf`, xử lý all-abstain default.
7. [Spring Security 6.5 API – `AuthorizationManagerBeforeMethodInterceptor`](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html): constructor pointcut + manager, advisor.
8. [Spring Framework 6.2 API – `AnnotationMatchingPointcut`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html): `forMethodAnnotation`.
9. [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `@Transactional`, self-invocation, transaction boundaries.
10. [Spring Security – Test Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser` và Method Security integration tests.
11. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, resource-level checks.

**Kết luận:** `AuthorizationManager<T>` là một điểm mở rộng nhất quán để **Spring Security thực thi quyết định từ policy service**. Manager cần xác định đúng action/resource, lấy authentication và thuộc tính tin cậy, hỏi PDP, hiểu chính xác `ALLOW`/`DENY`/lỗi và trả explicit authorization result. Khi dữ liệu quyền và resource thay đổi theo thời gian, thêm transaction/recheck/conditional write; với remote PDP, phải có timeout, cache/version, audit và fail-closed. Chỉ một role đúng, một token hợp lệ hoặc một ALLOW đã cũ **không đủ** để đảm bảo quyết định authorization cuối cùng.