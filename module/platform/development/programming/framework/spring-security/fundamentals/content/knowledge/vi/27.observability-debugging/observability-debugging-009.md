# Sự kiện xác thực, phân quyền và nhật ký kiểm toán trong Spring Security

> **Phạm vi:** Spring Security fundamentals, nhóm **Quan sát và gỡ lỗi**. Bài học giải thích và thực hành thu nhận **authentication events**, **authorization events**, **audit events/audit trail**, cách tổ chức dữ liệu kiểm toán an toàn, khả năng kiểm chứng, truy vết và khôi phục khi hệ thống lỗi. Ví dụ dùng **Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring MVC/Servlet, Spring Boot Actuator, JUnit 5/MockMvc**. Những điểm liên quan WebFlux/OAuth2/Resource Server được phân biệt riêng, không giả định mọi cơ chế đều phát cùng loại sự kiện.

## 1. Vì sao cần sự kiện bảo mật và nhật ký kiểm toán?

Khi API trả `401», `403» hoặc `200», response HTTP cho biết **kết quả đối với client**, nhưng chưa cung cấp đủ bằng chứng để trả lời:

- Ai đã thử đăng nhập? Xác thực thành công hay thất bại, ở cơ chế nào?
- Vì sao một người dùng đã đăng nhập vẫn bị từ chối truy cập?
- Quyền quan trọng vừa được cấp, thu hồi hoặc một thiết lập bảo mật vừa bị sửa bởi ai?
- Một chuỗi lần đăng nhập thất bại là lỗi mật khẩu, lưu lượng tấn công hay sự cố hệ thống danh tính?
- Sự kiện nào đã xảy ra trước/sau một thay đổi nhạy cảm? Có chứng cứ đủ tin cậy để điều tra hay không?

Spring Security có thể phát **Spring application events** khi xác thực hoặc phân quyền. Spring Boot Actuator có thêm mô hình `AuditEvent» và `AuditEventRepository». Nhưng **một event trong JVM không mặc nhiên là một bản ghi kiểm toán bền vững**: muốn có audit trail phù hợp cần lựa chọn, chuẩn hóa, lưu trữ, bảo vệ và giám sát quá trình ghi.

**Phân biệt trọng tâm:**

| Khái niệm | Đơn vị thông tin | Dùng cho | Giới hạn |
| --- | --- | --- | --- |
| Authentication event | Lần xác thực thành công/thất bại, loại exception | Theo dõi đăng nhập và lỗi nhà cung cấp danh tính | Không đồng nghĩa mọi HTTP request đều phát auth event |
| Authorization event | Quyết định cho phép/từ chối một hành động | Tìm lỗi role/scope, thống kê access denied | Event cho phép có thể quá nhiều; không phải mọi đường 403 đều là authz denial |
| Audit event | Bản ghi có cấu trúc: actor, action/type, outcome, time, context | Tra cứu sự kiện an ninh và thay đổi nghiệp vụ | Cần repository/collector; in-memory không đảm bảo độ bền |
| Application/security log | Dòng log INFO/DEBUG/WARN/ERROR, trace ID | Gỡ lỗi kỹ thuật, điều tra hệ thống | Có thể thiếu chuẩn, bị xoay/xóa, chứa thông tin nhạy cảm |
| Audit trail | Chuỗi sự kiện được lưu, bảo vệ, truy vấn và quản lý vòng đời | Điều tra, giải trình, phát hiện lạm dụng, tuân thủ | Không tự hình thành chỉ nhờ `@EventListener» |
| Metric/trace | Tần suất, độ trễ, span liên dịch vụ | Alert, đo tác động, xác định phụ thuộc | Không thay thế sự kiện chi tiết có actor/action/outcome |

**Thiết kế hợp lý:** dùng event của framework như một **tín hiệu đầu vào**, chuyển các tín hiệu có giá trị thành **audit record đã lọc và giới hạn dữ liệu**; với sự kiện cần bằng chứng mạnh, chọn kênh lưu bền thích hợp thay vì chỉ viết logger thông thường.

## 2. Luồng sự kiện trong Spring Security Servlet

Trong ứng dụng Servlet thông thường:

```text
Request HTTP
    |
    v
SecurityFilterChain
    |
    +--> Authentication filter (Basic/form/Bearer...)
    |      |
    |      v
    |   AuthenticationManager / ProviderManager
    |      |
    |      +--> Thành công -> AuthenticationSuccessEvent
    |      |
    |      +--> Thất bại  -> AbstractAuthenticationFailureEvent
    |                      (subclass theo loại AuthenticationException)
    |
    +--> AuthorizationFilter / AuthorizationManager
    |      |
    |      +--> Bị từ chối -> AuthorizationDeniedEvent
    |      |
    |      +--> Được phép  -> mặc định thường không ghi event granted
    |
    v
Controller / service / method security
    |
    +--> Có thể có thêm authorization event từ điểm mở rộng tương ứng
    |
    v
Spring ApplicationEventPublisher
    |
    +--> @EventListener / custom adapter
    |
    +--> Spring Boot Actuator auditing khi được cấu hình
    |
    v
AuditEventRepository / storage / observability pipeline
```

Sơ đồ cho biết **đường sự kiện thường gặp**, không phải cam kết rằng mọi authentication flow hay mỗi request sẽ phát đúng một event. Tùy filter, provider, session reuse, JWT decoder, method security, cách dựng `AuthenticationManager» và phiên bản, số lần/tên event có thể khác. Cần kiểm thử **flow thật** của ứng dụng.

### 2.1 Một HTTP request không đồng nghĩa một lần authentication

- Với HTTP Basic, filter có thể thực hiện xác thực trên từng request, nên thành công có thể được phát nhiều lần.
- Với session sau form login, request kế tiếp có thể chỉ khôi phục `SecurityContext» từ session mà không chạy lại `AuthenticationManager».
- Với JWT Resource Server, token decoding và authentication flow có cách phát event riêng tùy `AuthenticationManager»/filter.
- Với test `@WithMockUser», context được cài trực tiếp: đó **không phải** đăng nhập thật, nên không dựa vào mock để chứng minh authentication event thật đã được phát.
- Với OAuth2 login, cần kiểm tra các event/handler của chính flow OIDC/OAuth2; không suy luận rằng một sự kiện `AuthenticationSuccessEvent» duy nhất đã mô tả đầy đủ token exchange.

**Hệ quả vận hành:** không đo số “phiên đăng nhập thành công” bằng cách đếm vô điều kiện toàn bộ `AuthenticationSuccessEvent» trong mọi kiến trúc. Định nghĩa rõ metric “credential verification”, “interactive login”, “new session” và “request authenticated” là những đại lượng khác nhau.

## 3. Sự kiện xác thực (Authentication Events)

### 3.1 Thành công, thất bại và event publisher

Các lớp/API thường dùng trong Spring Security 6.x:

| Lớp/API | Vai trò |
| --- | --- |
| `AuthenticationEventPublisher» | Hợp đồng phát authentication events |
| `DefaultAuthenticationEventPublisher» | Publisher chuẩn, chuyển thành công và một số lỗi xác thực thành Spring events |
| `AuthenticationSuccessEvent» | Authentication được provider chấp nhận |
| `AbstractAuthenticationFailureEvent» | Lớp cơ sở của các sự kiện xác thực thất bại |
| `AuthenticationFailureBadCredentialsEvent» | Credential không được chấp nhận |
| `AuthenticationFailureLockedEvent», `AuthenticationFailureDisabledEvent» | Account bị khóa/vô hiệu hóa |
| `AuthenticationFailureServiceExceptionEvent» | Lỗi dịch vụ phục vụ xác thực |
| `ApplicationEventPublisher» | Spring event bus nội bộ |
| `@EventListener» | Khai báo phương thức nhận event |

Ví dụ cấu hình tường minh:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
```

Đây là **fragment cấu hình**, cần imports tương ứng; file Java đầy đủ ở phần 7 có tất cả import. Nhiều project Spring Boot đã cung cấp event publisher thông qua auto-configuration; khai báo tường minh một bean giúp demo thể hiện điểm kích hoạt. **Không tạo nhiều publisher trùng chức năng** nếu không biết framework sẽ chọn bean nào hoặc sự kiện có bị nhân đôi.

### 3.2 Bắt sự kiện qua @EventListener

```java
// Fragment: đặt trong một @Component.
// Chỉ chọn trường an toàn, không in toàn Authentication.
@EventListener
public void onSuccess(AuthenticationSuccessEvent event) {
    String principal = event.getAuthentication().getName();
    // Ghi audit event đã lọc qua adapter/repository.
}

@EventListener
public void onFailure(AbstractAuthenticationFailureEvent event) {
    String kind = event.getException().getClass().getSimpleName();
    // Không log raw credentials hoặc event.getAuthentication().toString().
}
```

Một listener nhận `AbstractAuthenticationFailureEvent» sẽ nhận các subclass phù hợp. Khi cần phân biệt loại lỗi, phân loại **exception** (bad credentials, account state, dependency failure) rồi chỉ lưu **category nội bộ**. Tránh dùng message exception nguyên văn vì có thể chứa username, hostname hoặc chi tiết nhạy cảm.

### 3.3 Exception mapping không phải “mọi subclass tự được ghi”

`DefaultAuthenticationEventPublisher» ánh xạ một số exception chuẩn tới event tương ứng. Điểm tinh tế: cơ chế mapping của nó sử dụng **khớp chính xác lớp exception**, nên một subclass tự định nghĩa của `BadCredentialsException» không chắc phát cùng event mặc định.

Ví dụ các nhóm thường gặp:

- `BadCredentialsException» hoặc username không tồn tại đã được provider che → nhóm lỗi credential.
- `LockedException» / `DisabledException» → nhóm trạng thái tài khoản.
- `AuthenticationServiceException» → nhóm lỗi hạ tầng/dịch vụ xác thực.
- `ProviderNotFoundException» → khả năng lỗi cấu hình/provider.
- Exception đặc thù do ứng dụng tự định nghĩa → cần xem mapping, không giả định event mặc định có mặt.

Có thể cấu hình `setAdditionalExceptionMappings(Map<...>)» hoặc fallback event cho những exception chưa map. Cần kiểm tra kỹ constructor của event tùy biến và phiên bản Spring Security, đồng thời viết test để chứng minh sự kiện không bị bỏ sót.

### 3.4 Authentication failure không phải authorization denial

- Đăng nhập sai password là **authentication failure**, thường client nhận 401 hoặc một trang lỗi/redirect tùy giao thức.
- Người dùng đã đăng nhập nhưng không đủ `ROLE_ADMIN» là **authorization denial**, thường nhận 403.
- POST thiếu CSRF token có thể 403 ngay trong security filter, không nhất thiết đi qua `AuthorizationManager».
- Kho danh tính/IdP lỗi có thể phát authentication service failure; không nên gộp với mật khẩu sai trong metric hoặc chính sách lockout.
- Thao tác đổi vai trò bởi quản trị viên có thể thành công và cần một **business audit event** riêng — không thể suy ra chỉ từ authentication/authorization events.

**Phân loại sai gây hại:** tăng failed-login counter do outage có thể khóa oan hàng loạt tài khoản; đếm mọi 403 là thiếu role sẽ nhầm các lỗi CSRF, CORS hoặc gateway; chỉ kiểm tra logger không đảm bảo audit persistence.

## 4. Sự kiện phân quyền (Authorization Events)

Spring Security 6.x có `AuthorizationEventPublisher». `SpringAuthorizationEventPublisher» dùng `ApplicationEventPublisher» để phát các event authorization; mặc định, publisher này chú trọng **`AuthorizationDeniedEvent»** thay vì phát tràn lan mọi grant.

Cấu hình:

```java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new SpringAuthorizationEventPublisher(applicationEvents);
}
```

Để bắt trường hợp từ chối:

```java
// Fragment: đặt trong @Component và imports phù hợp.
@EventListener
public void onDenied(AuthorizationDeniedEvent<?> event) {
    // Không log event.getObject().toString() hoặc toàn bộ
    // authentication: object có thể chứa request/method arguments.
    // Thêm một audit record outcome=DENIED, dữ liệu đã lọc.
}
```

`AuthorizationDeniedEvent» có thông tin về đối tượng được bảo vệ và một `Supplier<Authentication>» theo API Spring Security 6.3. Điều đó không có nghĩa nên serialize toàn bộ đối tượng. Với URL authorization, object có thể liên quan tới request; với method security, object có thể chứa method invocation và đối số nghiệp vụ nhạy cảm.

### 4.1 Tại sao granted event không được bật rộng?

Một ứng dụng phục vụ hàng nghìn request mỗi giây sẽ có rất nhiều quyết định “được phép”. Phát và lưu mọi grant có thể:

- Tăng số record/chi phí lưu trữ, khiến các denial đáng chú ý bị chìm.
- Ghi lặp rất nhiều lần cùng một việc kiểm tra quyền.
- Đưa tài nguyên/tenant/method arguments vào audit nếu serializer quá rộng.
- Làm chậm request nếu listener ghi đồng bộ.
- Tạo nhầm lẫn giữa “được phép đi qua một check” và “nghiệp vụ thực sự hoàn tất”.

Đối với nghiệp vụ nhạy cảm, audit **hành động đã hoàn tất** (ví dụ đổi quyền, xóa tài khoản, xuất dữ liệu) thường hữu ích hơn audit mỗi lần `hasRole» trả true. Nếu cần granted event, phát có chọn lọc theo rule/route/action hoặc tự tạo event nghiệp vụ chứa outcome rõ ràng; đo tải và tránh trùng lặp.

### 4.2 Không phải mọi deny có cùng nguồn

Một response 403 có thể đến từ CSRF filter, method security, URL authorization, custom `AccessDeniedHandler», reverse proxy hoặc gateway. `AuthorizationDeniedEvent» phụ thuộc **publisher và điểm ra quyết định** có tham gia hay không. Không suy ra “đã có 403 thì chắc đã có AuthorizationDeniedEvent”.

Với nghiệp vụ rất quan trọng, định nghĩa **đường audit bổ sung** tại nơi chịu trách nhiệm ra quyết định hoặc giao dịch, và kiểm thử cả positive/negative path. Nhưng không viết hai bản ghi “một sự kiện” từ hai listener không có deduplication rồi đếm thành hai lần từ chối.

## 5. Nhật ký kiểm toán (audit trail) khác log DEBUG ra sao?

Một log DEBUG thường dành cho người phát triển: nó có thể chứa tên lớp, request matcher, timing, stack trace và thay đổi giữa phiên bản thư viện. **Audit record** nên có cấu trúc ổn định cho kiểm tra và truy vấn, đủ để trả lời *ai – làm gì – lên tài nguyên nào – khi nào – ở đâu – kết quả ra sao – lý do loại nào – liên quan request nào*.

Schema tham khảo:

| Trường audit | Ví dụ | Quy tắc |
| --- | --- | --- |
| `event_id» | UUID | Định danh duy nhất để chống ghi trùng |
| `occurred_at» | ISO-8601 UTC | Thời điểm hành động, đồng bộ thời gian |
| `recorded_at» | ISO-8601 UTC | Thời điểm kho audit nhận bản ghi |
| `category» | AUTHENTICATION, AUTHORIZATION, ACCOUNT_ADMIN | Loại sự kiện cấp cao |
| `event_type» | LOGIN_FAILED, ACCESS_DENIED, ROLE_REVOKED | Mã ổn định, có version/schema |
| `actor_id» | ID nội bộ/pseudonym | Không cần lưu password, full principal hay email |
| `actor_type» | USER, SERVICE, ANONYMOUS | Biết đây là người dùng hay service account |
| `target_type» | REPORT, ACCOUNT, TENANT, API | Tránh ghi nguyên request body |
| `target_id» | Mã nội bộ được phép lưu | Kiểm soát tenant/PII |
| `action» | READ, LOGIN, UPDATE_PERMISSION | Việc được yêu cầu/thực hiện |
| `outcome» | SUCCEEDED, DENIED, FAILED, UNKNOWN | Không dùng mỗi HTTP status làm root cause |
| `reason_code» | BAD_CREDENTIALS, MISSING_ROLE, IDENTITY_STORE_DOWN | Mã phân loại nội bộ đã lọc |
| `request_id», `trace_id» | Correlation ID | Ghép được nhiều thành phần trong hệ thống |
| `service», `environment», `instance» | identity-api, prod, pod-03 | Phục vụ điều tra và phân vùng dữ liệu |
| `source_ip» | IP đã chuẩn hóa nếu chính sách cho phép | Đằng sau proxy chỉ tin forwarding header hợp lệ |
| `schema_version» | 1 | Hỗ trợ thay đổi cấu trúc theo thời gian |

Không phải hệ thống nào cũng cần toàn bộ trường. **Nguyên tắc tối thiểu dữ liệu:** chọn những gì cần thiết cho khả năng giải trình, loại bỏ password/token/authorization header/raw cookie, mã hóa và giới hạn quyền truy cập các định danh còn lại.

### 5.1 Sự kiện “attempted”, “authorized” và “committed” khác nhau

Một ví dụ đổi role:

```text
POST /admin/accounts/42/roles
  |
  +--> Authentication thành công      (danh tính đã xác nhận)
  |
  +--> Authorization cho phép         (có quyền gọi thao tác)
  |
  +--> Nghiệp vụ validate             (có thể thất bại)
  |
  +--> Transaction cập nhật DB        (có thể rollback)
  |
  +--> Commit thành công              (thay đổi thực sự bền vững)
  |
  +--> ROLE_CHANGED audit event       (kết quả đã hoàn tất)
```

Không nên ghi `ROLE_CHANGED success» ngay khi `hasRole("ADMIN")» trả true. Nếu transaction rollback, bản ghi audit sẽ sai thực tế. Với sự kiện phải gắn với commit, cần thiết kế `@TransactionalEventListener(phase = AFTER_COMMIT)» cho side effect phù hợp hoặc dùng **transactional outbox**/sổ ghi giao dịch khi yêu cầu độ tin cậy cao. Lưu ý listener AFTER_COMMIT gửi sang dịch vụ khác vẫn có thể thất bại, nên không tự hứa rằng event bus trong JVM là cơ chế exactly-once bền vững.

### 5.2 Thu thập có ý nghĩa, không chỉ “log mọi thứ”

Nên ưu tiên audit:

- Authentication success/failure quan trọng; thay đổi MFA, reset password, revoke session/token.
- Cấp/thu hồi role, thay đổi policy, tạo/xóa service account, chỉnh cấu hình IdP/OAuth2 client.
- Thao tác quản trị dữ liệu, xuất dữ liệu nhạy cảm, truy cập tài nguyên có yêu cầu audit.
- Nỗ lực truy cập bị chặn lặp lại hoặc từ địa chỉ bất thường; các thay đổi bảo mật thất bại.
- Sự kiện xoay/thu hồi credential — chỉ lưu loại hành động và actor, **không lưu giá trị secret**.

Không cần audit chi tiết mọi request GET thông thường; có thể dùng metrics/traces cho volumetric monitoring và chọn lọc những event có ý nghĩa.

## 6. Spring Boot Actuator: AuditEvent và AuditEventRepository

Spring Boot Actuator có mô hình auditing với:

| API | Vai trò |
| --- | --- |
| `AuditEvent» | Một bản ghi gồm timestamp, principal, type và data map |
| `AuditEventRepository» | Hợp đồng thêm/truy vấn audit event |
| `InMemoryAuditEventRepository» | Kho vòng đệm trong RAM, **dành cho demo/dev**, không phù hợp audit production |
| `AuditApplicationEvent» | Cách phát một custom audit event vào Spring application context |
| `AbstractAuthenticationAuditListener» | Điểm mở rộng chuyển authentication event sang audit |
| `AbstractAuthorizationAuditListener» | Điểm mở rộng chuyển authorization-related event sang audit |
| `/actuator/auditevents» | Endpoint quản trị đọc dữ liệu audit khi có repository và được expose có chủ đích |

Khi Spring Security hiện diện và Actuator auditing được cấu hình, Spring Boot có thể chuyển các security event phổ biến thành audit records (ví dụ authentication success/failure, access denied). **Các event này không nên được giả định bao phủ mọi hành động nghiệp vụ hoặc mọi denial ở mọi filter**. Nếu ứng dụng tự tạo audit listener, có thể nhận **cả event do Boot cung cấp và event tùy biến**; cần quyết định chủ sở hữu record, tránh double count.

Một ví dụ tạo repository dành cho thử nghiệm:

```java
@Bean
AuditEventRepository auditEventRepository() {
    return new InMemoryAuditEventRepository(1000);
}
```

Giới hạn **1000 sự kiện trong RAM** ở ví dụ nhằm tránh tăng bộ nhớ không kiểm soát. Nội dung mất sau restart và có thể bị ghi đè/loại bỏ khi vượt dung lượng. Vì vậy không được coi nó là bằng chứng kiểm toán đủ bền vững trong production.

### 6.1 Endpoint auditevents phải được bảo vệ

Không tự expose `/actuator/auditevents» công khai. Bản ghi có thể chứa principal, đường đi và metadata nhạy cảm. Muốn dùng trong production cần:

1. Quản lý mạng truy cập management (private network, VPN/mTLS, allowlist).
2. Phân quyền chỉ cho security operator/auditor được phép.
3. Kiểm soát truy vấn và giới hạn lưu lượng; lưu audit của chính hành động đọc/export audit nếu chính sách yêu cầu.
4. Kiểm soát retention và số lượng bản ghi trả về để tránh lộ khối lượng lớn dữ liệu.
5. Không xem việc enable endpoint là điều kiện bắt buộc để **ghi** audit: repository có thể thu nhận event mà endpoint không được expose.

Với ứng dụng có `SecurityFilterChain» tùy biến, không mặc định tin rằng actuator endpoints sẽ tự được bảo vệ đúng yêu cầu. Hãy cấu hình management security rõ ràng theo mô hình deployment.

## 7. Dự án Java 17: phát, bắt và kiểm tra sự kiện

Ví dụ sau chạy với Spring Boot 3.3.5, Spring Security 6.3.x đi kèm. Nó có hai user demo `reader» và `admin», endpoint `/public», `/me» và `/ops» (chỉ ADMIN). Ta cấu hình hai publisher, ba listener và một `AuditEventRepository» in-memory. Listener chỉ ghi **loại sự kiện và thông tin tối thiểu**, không ghi password, Authorization header, raw Authentication hoặc đối tượng request.

Ví dụ có thể tạo cả **Actuator audit event mặc định** lẫn **custom event**. Để các bài test ổn định và tránh trộn loại, custom type được đặt prefix `APP_» riêng. Production cần thiết kế cách hợp nhất/deduplicate nếu cả hai nguồn cùng phục vụ một chỉ số.

### 7.1 Cấu trúc thư mục

```text
security-events-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/securityevents/
    │   └── SecurityEventsApplication.java
    └── test/java/com/example/securityevents/
        └── SecurityEventsApplicationTest.java
```

### 7.2 Maven dependencies

Tạo file `pom.xml»:

```xml
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
    <artifactId>security-events-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 7.3 Ứng dụng Spring Boot và listeners

Tạo `src/main/java/com/example/securityevents/SecurityEventsApplication.java»:

```java
package com.example.securityevents;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityEventsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityEventsApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-456"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new DefaultAuthenticationEventPublisher(applicationEvents);
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new SpringAuthorizationEventPublisher(applicationEvents);
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        // Demo/dev only. Không dùng làm kho audit tuân thủ ở production.
        return new InMemoryAuditEventRepository(1000);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/ops").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/me")
        String currentUser(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/ops")
        String operations() {
            return "ops ok";
        }
    }

    @Component
    static class SecurityAuditListeners {
        private final AuditEventRepository repository;

        SecurityAuditListeners(AuditEventRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void authenticationSucceeded(AuthenticationSuccessEvent event) {
            // Không lưu credentials, details, toString() hay principal object.
            String actor = safeActor(event.getAuthentication());
            repository.add(new AuditEvent(
                actor,
                "APP_AUTH_SUCCESS",
                Map.of("outcome", "SUCCEEDED", "source", "spring-security")
            ));
        }

        @EventListener
        public void authenticationFailed(
                AbstractAuthenticationFailureEvent event) {

            String reason = "OTHER_AUTH_FAILURE";
            if (event.getException() instanceof BadCredentialsException) {
                reason = "BAD_CREDENTIALS";
            } else if (event.getException()
                    instanceof AuthenticationServiceException) {
                reason = "AUTH_SERVICE_FAILURE";
            }

            repository.add(new AuditEvent(
                safeActor(event.getAuthentication()),
                "APP_AUTH_FAILURE",
                Map.of("outcome", "FAILED", "reason", reason)
            ));
        }

        @EventListener
        public void accessDenied(AuthorizationDeniedEvent<?> event) {
            String actor = "unknown";
            try {
                // Supplier có thể không trả Authentication nếu không có
                // security context phù hợp; không để audit làm lỗi request.
                actor = safeActor(event.getAuthentication().get());
            } catch (RuntimeException ignored) {
                // Chỉ lưu actor chung thay vì in request/credentials.
            }

            repository.add(new AuditEvent(
                actor,
                "APP_AUTHZ_DENIED",
                Map.of("outcome", "DENIED", "domain", "http-authorization")
            ));
        }

        private static String safeActor(Authentication authentication) {
            if (authentication == null) {
                return "anonymous";
            }
            String name = authentication.getName();
            return (name == null || name.isBlank()) ? "unknown" : name;
        }
    }
}
```

### 7.4 Vì sao implementation này có ý nghĩa?

1. **Authentication publisher** được khai báo tường minh; nếu một `ProviderManager» xử lý Basic authentication với publisher này, nó phát event thành công/thất bại.
2. **Authorization publisher** cũng được khai báo tường minh. `SpringAuthorizationEventPublisher» phát denial khi `AuthorizationFilter» đưa ra quyết định deny; không nhầm denial với mọi HTTP 403.
3. **Listeners** nhận event thông qua `@EventListener», không phải dùng `System.out.println» hay in toàn bộ `Authentication». Data map chỉ chứa outcome/category không có password hay raw token.
4. **AuditEventRepository** dùng in-memory có giới hạn vì dễ học. Trong cùng JVM, JUnit có thể query để xác minh sự kiện. Không có endpoint API tùy biến nào trả toàn bộ audit cho client.
5. **Actor name** chỉ là ví dụ cho môi trường demo. Production có thể cần ID nội bộ/pseudonym, quy trình data minimization/retention hoặc không lưu tên account với mọi sự kiện; tránh ghi username giả của người tấn công không giới hạn.
6. **AuthorizationDenial source** chỉ nói loại domain, không serialize `event.getObject()», vì object có thể chứa URL, method arguments hoặc đối tượng nghiệp vụ nhạy cảm.
7. **Không dùng async executor riêng** trong ví dụ: event listener mặc định xử lý theo đường publish đồng bộ, giúp test đơn giản. Production phải cân nhắc latency và tính bền vững; một repository ghi chậm/throw exception trong listener có thể ảnh hưởng authentication request.
8. **Actuator có thể ghi các audit event chuẩn bên cạnh custom `APP_*»**. Không tính tổng cả hai loại rồi suy ra số login thật. Khi triển khai, chọn nguồn chuẩn, tên/type và quy tắc dedup.
9. **Status HTTP không bị listener điều khiển**: quyền URL vẫn do `authorizeHttpRequests» quyết định; audit chỉ ghi nhận sự kiện đã quan sát. Audit failure không được dùng như cách tự cấp quyền để bỏ qua bảo vệ.

### 7.5 Kiểm thử tích hợp với MockMvc và AuditEventRepository

Tạo `src/test/java/com/example/securityevents/SecurityEventsApplicationTest.java»:

```java
package com.example.securityevents;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityEventsApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AuditEventRepository audit;

    private int count(String actor, String type) {
        return audit.find(actor, null, type).size();
    }

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void loginSuccessProducesAuditEvent() throws Exception {
        int before = count("admin", "APP_AUTH_SUCCESS");

        mvc.perform(get("/me")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello admin"));

        assertThat(count("admin", "APP_AUTH_SUCCESS"))
            .isGreaterThan(before);
    }

    @Test
    void wrongPasswordProducesAuthenticationFailureEvent()
            throws Exception {

        int before = count("admin", "APP_AUTH_FAILURE");

        mvc.perform(get("/ops")
                .with(httpBasic("admin", "wrong")))
            .andExpect(status().isUnauthorized());

        assertThat(count("admin", "APP_AUTH_FAILURE"))
            .isGreaterThan(before);
    }

    @Test
    void deniedAccessProducesAuthorizationAuditEvent()
            throws Exception {

        int before = count("reader", "APP_AUTHZ_DENIED");

        mvc.perform(get("/ops")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isForbidden());

        assertThat(count("reader", "APP_AUTHZ_DENIED"))
            .isGreaterThan(before);
    }

    @Test
    void adminIsAuthorizedToUseOps() throws Exception {
        mvc.perform(get("/ops")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk())
            .andExpect(content().string("ops ok"));
    }

    @Test
    void customAuditDataDoesNotContainPassword() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk());

        List<AuditEvent> records =
            audit.find("admin", null, "APP_AUTH_SUCCESS");

        assertThat(records).isNotEmpty();
        for (AuditEvent item : records) {
            // Chỉ kiểm tra phần dữ liệu custom, không serialize credentials.
            assertThat(item.getData().toString())
                .doesNotContain("admin-demo-456");
        }
    }

    @Test
    void unauthenticatedRequestCannotReadOps() throws Exception {
        mvc.perform(get("/ops"))
            .andExpect(status().isUnauthorized());
    }
}
```

Bộ test gồm **7 ca**. Các test về event đo số record **trước và sau một request**, không giả định số sự kiện toàn ứng dụng bằng đúng 1, vì các test khác hoặc auto-config có thể cùng ghi vào kho dev. Các custom event được phân biệt với audit event mặc định của Boot nhờ prefix `APP_».

**Lưu ý khi chuyển sang async:** Test ở đây dựa trên `@EventListener» đồng bộ và repository in-memory. Nếu thay bằng message broker, hàng đợi hoặc `@Async», kiểm thử phải chờ theo điều kiện có timeout (hoặc dùng test broker) thay vì assert ngay sau response. Không thêm `Thread.sleep» cố định để che điều kiện race.

### 7.6 Chạy thử

Cài Java 17+ và Maven. Từ thư mục dự án:

```bash
mvn test
mvn spring-boot:run
```

Gửi request thật:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/ops
curl -i -u reader:reader-demo-123 http://localhost:8080/ops
curl -i -u admin:admin-demo-456 http://localhost:8080/ops
curl -i -u admin:wrong http://localhost:8080/ops
```

| Request | HTTP kỳ vọng | Lớp tín hiệu chính |
| --- | --- | --- |
| `GET /public» | 200 | Public route, không bắt buộc auth event |
| `GET /ops» không credential | 401 | Entry point; không khẳng định có bad-credentials event |
| `GET /ops» với reader | 403 | Role thiếu; `AuthorizationDeniedEvent» với publisher được cấu hình |
| `GET /ops» với admin | 200 | Authentication hợp lệ; có thể phát auth success |
| `GET /ops» với admin + password sai | 401 | Authentication failure; custom audit `APP_AUTH_FAILURE» |

Dữ liệu audit không có API công khai trong demo. Test đọc `AuditEventRepository» trực tiếp để chứng minh những event đã được ghi. Nếu muốn tra cứu từ vận hành, cấu hình endpoint quản trị có kiểm soát, không tạo `GET /all-audit» public.

Các kết quả ở bảng là kỳ vọng dựa trên source và API đã nêu; muốn xác nhận chạy được trên máy người học, thực thi `mvn test». Đừng dùng một kết quả status đơn lẻ làm bằng chứng event và audit trail đã bền vững.

## 8. Thêm audit cho hành động nghiệp vụ quan trọng

Event xác thực/phân quyền không bao phủ “admin vừa đổi role của người khác”. Ví dụ publish custom audit event cho hành động đổi quyền **sau commit**:

```java
// FRAGMENT MINH HỌA: roleService/accountId/actorId do dự án định nghĩa.
// Dùng khi đã có transaction và luồng ghi durable phù hợp.
@Transactional
public void changeRole(long accountId, String role, String actorId) {
    roleRepository.updateRole(accountId, role);
    applicationEvents.publishEvent(
        new RoleChangeRequestedEvent(accountId, actorId, role)
    );
}

// Listener có thể chỉ chạy sau commit khi transaction thực sự thành công.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onRoleChange(RoleChangeRequestedEvent event) {
    auditSink.recordRoleChange(event.accountId(), event.actorId());
}
```

Đây là **fragment, không phải mã Java độc lập**: các loại `RoleChangeRequestedEvent», `roleRepository», `auditSink» và import cần được dự án cung cấp. Tên event `RoleChangeRequestedEvent» chỉ là tên domain mẫu; nếu phát trước commit, listener `AFTER_COMMIT» mới có cơ hội ghi nhận sau khi giao dịch thành công.

**Không nhầm AFTER_COMMIT với đảm bảo lưu bền:** Process có thể crash sau khi commit database nhưng trước khi audit sink nhận record. Với yêu cầu “không được mất bản ghi” cần **transactional outbox** (ghi business change và outbox record trong cùng transaction) rồi một worker đáng tin cậy đẩy event từ outbox sang kho audit. Consumer phải có idempotency theo `event_id» vì at-least-once delivery có thể lặp.

### Ba cách ghi audit và trade-off

| Cách | Ưu điểm | Hạn chế |
| --- | --- | --- |
| `@EventListener» đồng bộ + DB audit | Đơn giản, test trực tiếp | Tăng request latency; lỗi ghi audit có thể tác động nghiệp vụ |
| `@Async»/queue nội bộ + log collector | Giảm chặn request | Crash/restart có thể mất event; thứ tự và context cần truyền rõ |
| Transactional outbox + broker/collector | Có thể bảo vệ record khi commit, retry, replay | Tốn thiết kế, vận hành, idempotency, dead-letter và giám sát |

Nếu chính sách kiểm toán quy định **phải có audit mới cho phép giao dịch**, phải quyết định điều gì xảy ra khi storage audit không hoạt động (fail closed, block giao dịch hoặc degradation theo quy định) và kiểm tra dữ liệu không bị mất. Không có một câu trả lời kỹ thuật chung cho mọi mức rủi ro.

## 9. Bảo vệ sự kiện, PII và dữ liệu nhạy cảm

### 9.1 Không ghi gì?

**Không ghi** password, OTP, PIN, raw Basic `Authorization», access/refresh token, session cookie, CSRF token, OAuth authorization code, API key, client secret, private key, token signing key, toàn bộ request body login hoặc stack trace chứa dữ liệu nhạy cảm.

Cũng tránh serialize các đối tượng nguyên vẹn:

```java
// SAI: có thể ghi credential/details/claims/đối số nghiệp vụ.
log.info("authentication={}", event.getAuthentication());
log.info("denied event={}", deniedEvent);
auditRepository.add(new AuditEvent(
    principal, "ALL_DETAILS", Map.of("request", request.toString())));
```

Đây là các **fragment phản ví dụ** — biến do project định nghĩa, không phải code chạy độc lập. `toString()» của principal, Authentication, request, method invocation hoặc exception có thể lộ nhiều thông tin hơn mong đợi.

### 9.2 Thay bằng allowlist dữ liệu

Một record hợp lý để gửi tới collector (minh họa JSON):

```json
{
  "schema_version": 1,
  "event_type": "AUTHORIZATION_DENIED",
  "outcome": "DENIED",
  "actor_type": "USER",
  "actor_id": "user-internal-932",
  "target_type": "REPORT",
  "action": "READ",
  "reason_code": "MISSING_ROLE",
  "request_id": "req-62ad",
  "occurred_at": "2026-01-01T09:00:00Z",
  "service": "reports-api"
}
```

Thời điểm, ID và giá trị trong ví dụ là **dữ liệu giả lập** để minh họa schema, không phải bản ghi thật. Không bắt buộc ghi `actor_id» rõ danh tính cho mọi sự kiện; cân nhắc mã định danh nội bộ/pseudonym, quyền giải mã/tham chiếu và chính sách bảo vệ dữ liệu.

Các nguyên tắc:

- **Minimize:** chỉ thu trường thật sự cần cho audit, không copy request body.
- **Protect:** TLS/mTLS tới collector, mã hóa at rest, chính sách RBAC và audit cả quyền truy vấn/export.
- **Separate duties:** ứng dụng phát sự kiện không nên tự xóa/sửa audit record đã ghi; tách quyền admin ứng dụng và người quản lý audit.
- **Retain appropriately:** TTL theo yêu cầu pháp lý và rủi ro; cân nhắc quyền xóa/chỉnh sửa dữ liệu theo luật và chính sách nội bộ.
- **Verify:** schema version, event ID, checksum/chữ ký hoặc append-only/WORM storage nếu mức bảo đảm cần thiết.
- **Limit volume:** kiểm soát event burst, suppression và sampling cho loại ít giá trị — nhưng không sampling các record bắt buộc cho kiểm toán.
- **Classify:** log auth failure do credential khác sự cố IdP/database; không tạo alert “tấn công” chỉ từ một loại lỗi chưa phân loại.

### 9.3 Correlation ID và tracing

Dùng `request_id» hoặc `trace_id» để ghép browser/gateway/auth service/permission service với audit event. ID không nên chứa username, email hoặc token. Với Spring MVC, log có thể dùng MDC trong thread request, nhưng sự kiện phát không đồng bộ có thể chạy ở thread khác; phải **chuyển correlation context rõ ràng** vào event envelope, không dựa vào ThreadLocal luôn có mặt.

Trong WebFlux, Reactor Context là cơ chế phù hợp hơn `SecurityContextHolder» kiểu Servlet. Không gọi `block()» hoặc JDBC đồng bộ trong listener reactive event loop; dùng client reactive hoặc kênh ghi phù hợp.

## 10. Lưu audit đáng tin cậy trong hệ thống phân tán

### 10.1 Những điểm có thể mất bản ghi

- Process crash trước khi listener chạy hoặc trước khi gửi tới collector.
- Listener throw exception; nếu đồng bộ, request có thể lỗi hoặc event bị bỏ dở.
- Message broker bị ngắt hoặc acknowledgment bị mất.
- Log collector đầy queue, disk full, index lỗi, retention không đúng.
- Một sự kiện phát nhiều lần qua retry, consumer restart hoặc cơ chế at-least-once.
- Clock skew giữa các instance làm thứ tự timestamp gây hiểu nhầm.
- Gateway cắt request trước khi tới Spring Security, nên không có event framework nội bộ.

Để audit có ý nghĩa, đo **số event tạo ra/nhận được/ghi bền/thất bại**, độ trễ end-to-end, queue depth, oldest event age, retry và dead-letter. Phải có cảnh báo khi pipeline mất khả năng ghi, không chỉ khi auth 401/403 tăng.

### 10.2 Idempotency và thứ tự

Một event `event_id» ổn định giúp consumer xử lý lại mà không ghi trùng. Cần thiết kế khóa duy nhất và mô hình truy vấn: ví dụ `(tenant_id,event_id)». Khi nhiều service phát sự kiện, **timestamp không luôn xác định chính xác tổng thứ tự**; có thể cần sequence theo aggregate/transaction hoặc causal links.

Không hứa “exactly once” chỉ vì dùng Kafka, database hoặc annotation; thực tế phải chứng minh tính nhất quán từ business commit, publisher, broker, consumer đến kho kiểm toán.

### 10.3 Không phá độ sẵn sàng của authentication vì listener sai

Spring `ApplicationEventPublisher» với event multicaster mặc định có thể gọi listener đồng bộ ngay trong luồng phát. Vì vậy:

- Listener không được thực hiện truy vấn chậm, ghi network không timeout hoặc heavy JSON serialization trên đường đăng nhập.
- Listener không được ném exception vô tình khiến đăng nhập thất bại, trừ khi chính sách audit bắt buộc yêu cầu fail closed và được thiết kế/test rõ ràng.
- Không dùng `@Async» như “đảm bảo không mất dữ liệu”. Cần queue/buffer bền, backpressure, retry và chiến lược lỗi.
- Không bỏ qua audit writer failures; metric và cảnh báo phải mô tả sự kiện nào bị ảnh hưởng.
- Test các trường hợp collector down, retry, duplicate, backlog, restart và rollback.

## 11. Kiểm thử sự kiện bảo mật và audit trail

Một bộ test đầy đủ nên tách thành các nhóm:

| Nhóm test | Điều muốn chứng minh | Kỹ thuật |
| --- | --- | --- |
| Authentication success | Login hợp lệ phát tín hiệu và lưu record mong muốn | MockMvc/httpBasic hoặc flow thật; `AuditEventRepository» |
| Authentication failure | Credential sai phát failure; không lộ password | Auth provider thật + kiểm tra trường audit |
| Account status | User locked/disabled khác bad credentials | Test `UserDetailsService»/provider và category |
| Infrastructure failure | Timeout IdP/database không bị tính thành wrong password | Fault injection/test double + mapping |
| Authorization denied | User có login nhưng thiếu role bị từ chối và sinh denial record | Request HTTP 403 + event listener |
| Authorization granted | Admin đủ quyền qua route, không bùng số record | HTTP 200, kiểm tra phạm vi auditing |
| CSRF/CORS/gateway | 403 do CSRF, CORS hay upstream không bị gán sai | Integration test theo filter/route |
| Business audit | Đổi quyền ghi event sau commit, rollback không ghi success | Transactional integration test |
| Durability | Broker/DB down vẫn có chính sách mất mát/retry xác định | Test retry/idempotency/chaos |
| Data protection | Không lưu token/password/PII không cần | Schema assertions + kiểm tra log |
| Access control | Chỉ auditor có quyền đọc/export audit | Security test cho management endpoints |
| Retention | Event được giữ/xóa theo vòng đời | Repository/pipeline integration |

**Không dùng `@WithMockUser» để chứng minh authentication event:** annotation tạo SecurityContext giả; muốn thử `ProviderManager» và `DefaultAuthenticationEventPublisher» phải có request xác thực thật hoặc gọi provider/manager một cách được kiểm soát.

Khi thêm asynchronous audit, test không nên assert kết quả ngay lập tức mà không có cơ chế đồng bộ; dùng test queue/transaction và poll có timeout. Với pipeline production, bổ sung test số lượng record sau retry, trùng message và partial failure.

## 12. Những lỗi phổ biến

### Lỗi 1 — Chỉ thêm @EventListener rồi coi là audit trail bền vững

Event Spring trong JVM không mặc định tồn tại qua restart. `InMemoryAuditEventRepository» cũng mất dữ liệu. **Sửa:** phân biệt tín hiệu và lưu bền, chọn audit store/collector, retention và monitoring.

### Lỗi 2 — Nhầm 401 với một event cụ thể

Chưa gửi credential, password sai, token hết hạn, IdP hỏng có thể đều dẫn đến phản hồi 401 tùy cấu hình. **Sửa:** phân loại root cause và cơ chế xác thực; không dùng HTTP status làm metric duy nhất.

### Lỗi 3 — Xem mọi 403 là AuthorizationDeniedEvent

CSRF và gateway có thể 403 mà không qua AuthorizationManager. **Sửa:** test từng đường security, xử lý audit ở đúng nguồn.

### Lỗi 4 — Giả định mọi grant đều có event

`SpringAuthorizationEventPublisher» ở Spring Security 6.3 tập trung vào denial; granted event không phát mặc định để tránh volume. **Sửa:** chỉ thêm granted auditing có chọn lọc khi có yêu cầu cụ thể, ưu tiên event kết quả nghiệp vụ.

### Lỗi 5 — Logger in toàn bộ Authentication/exception

Authentication object, claims hoặc exception message có thể chứa bí mật/PII. **Sửa:** allowlist data và reason code, hạn chế quyền đọc log/audit.

### Lỗi 6 — Không cấu hình AuthenticationEventPublisher

`ProviderManager» có thể dùng publisher không phát event nếu không được cấu hình theo cách tích hợp cụ thể. **Sửa:** kiểm tra publisher bean/injection và dùng test credential thật xác nhận event được nhận.

### Lỗi 7 — Mapping exception subclass bị bỏ qua

Publisher mặc định sử dụng exact match cho một số exception. **Sửa:** thêm mapping/fallback có chủ đích và test custom exception.

### Lỗi 8 — Nhầm audit event với số lần login của con người

HTTP Basic có thể phát nhiều authentication success theo số request; session có thể tái sử dụng authentication không có event mới. **Sửa:** định nghĩa metric và event type rõ: login flow, credential verification, request, session.

### Lỗi 9 — Listener ghi đồng bộ vào hệ thống chậm

Event listener có thể chặn request hoặc throw lỗi làm hỏng authentication. **Sửa:** tách đường ghi, timeout, bounded queue/reliable broker và chính sách lỗi phù hợp; không chuyển thành fail-open.

### Lỗi 10 — Thêm @Async rồi cho rằng không mất event

Queue in-memory có thể mất dữ liệu khi crash. **Sửa:** transactional outbox hoặc durable queue khi audit bắt buộc; giám sát lag/retry/dead-letter.

### Lỗi 11 — Audit “đã thay đổi role” trước khi commit

Business transaction rollback nhưng audit ghi success. **Sửa:** phân biệt attempt và committed action; sử dụng transaction after-commit/outbox theo mức tin cậy cần thiết.

### Lỗi 12 — Không giới hạn quyền xem /actuator/auditevents

Endpoint có thể trả thông tin danh tính và sự kiện nhạy cảm. **Sửa:** không expose public; bảo vệ network/RBAC, audit quyền truy vấn và retention.

### Lỗi 13 — Không xử lý duplicate và schema version

Replay hoặc retry có thể tạo bản ghi trùng, thay đổi cấu trúc làm hệ thống truy vấn hỏng. **Sửa:** event_id, idempotency, schema_version và test migration.

### Lỗi 14 — Coi log DEBUG/TRACE là kho kiểm toán duy nhất

Logging verbosity có thể tắt, message nội bộ không ổn định, rotation/retention khác yêu cầu. **Sửa:** audit event type ổn định, lưu bền có kiểm soát; DEBUG chỉ bổ sung cho gỡ lỗi.

### Lỗi 15 — “Dữ liệu kiểm toán càng nhiều càng an toàn”

Ghi raw request, token và PII có thể tăng hậu quả khi audit store bị lộ. **Sửa:** data minimization, encryption, access separation, audit-only schema và review privacy.

## 13. Checklist áp dụng trong dự án thật

1. Xác định rõ **authentication event**, **authorization event** và **business audit event** nào cần thu, event nào không nên thu.
2. Kiểm tra Spring Security version, đã khai báo `AuthenticationEventPublisher»/`AuthorizationEventPublisher» chưa và mọi flow có đi qua publisher mong muốn không.
3. Định nghĩa schema ổn định: event ID, UTC timestamp, actor, target, action, outcome, reason code, correlation ID, schema version.
4. Không sao chép `Authentication», request, token, password, cookie hay method arguments vào audit.
5. Với access denied, test cả URL authorization, method security, CSRF và lỗi gateway; đừng chỉ đếm 403.
6. Với authentication failure, tách sai credential, trạng thái account và lỗi identity dependency; tránh khóa oan user khi backend down.
7. Với thao tác nghiệp vụ, phân biệt attempted/authorized/committed; chỉ đánh dấu success nếu thật sự commit.
8. Chọn kho lưu trữ có durability/retention/immutability phù hợp; **không dùng InMemoryAuditEventRepository làm bằng chứng production**.
9. Kiểm soát truy cập người quản trị/auditor, encryption, network và endpoint truy vấn audit; audit cả hành động đọc/export khi cần.
10. Bảo vệ đường gửi: retry có giới hạn, idempotency, dead-letter, metric cho dropped events và gap detection.
11. Kiểm thử đồng thời các trường hợp 200/401/403, event emission, content redaction, failure/restart và dedup.
12. Sau khi triển khai, so sánh số liệu event theo định nghĩa với dashboard/traces, phát hiện sai khác và cập nhật runbook điều tra.

## 14. Tóm tắt

- Spring Security có thể phát **authentication success/failure events** và **authorization denied events**, nhưng phải cấu hình publisher/hook phù hợp và kiểm tra flow thực tế.
- `@EventListener» nhận tín hiệu; nó **không tự tạo audit log bền vững**. Spring Boot Actuator cung cấp `AuditEventRepository» để lưu và truy vấn audit events.
- `SpringAuthorizationEventPublisher» ở Spring Security 6.3 chủ yếu phát denial; không bật mọi granted event theo thói quen vì volume và privacy.
- Audit trail tốt có cấu trúc **ai – làm gì – với tài nguyên nào – khi nào – kết quả – lý do – correlation ID**, giới hạn dữ liệu nhạy cảm.
- Sự kiện “được phân quyền” khác “giao dịch đã commit”; cần after-commit/outbox khi audit gắn với thay đổi quan trọng.
- `InMemoryAuditEventRepository» là công cụ học/dev, không đáp ứng yêu cầu độ bền cho production. Audit cần lưu, kiểm soát truy cập, retention, deduplication và giám sát mất mát.
- Kiểm thử không chỉ HTTP status mà còn event phát ra, actor/outcome, thiếu secrets, phân loại lỗi và đường ghi khi hệ thống gặp sự cố.

## Tài liệu tham khảo chính thức

- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/events.html
- Spring Security — Authorization Events: https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/events.html
- Spring Security 6.3 API — `SpringAuthorizationEventPublisher»: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html
- Spring Security 6.3 API — `AuthorizationDeniedEvent»: https://docs.spring.io/spring-security/site/docs/6.3.2/api/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorization for HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot — Auditing (Actuator): https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html
- Spring Boot — Audit Events Endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/auditevents.html
- Spring Boot — Actuator Endpoint Security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html