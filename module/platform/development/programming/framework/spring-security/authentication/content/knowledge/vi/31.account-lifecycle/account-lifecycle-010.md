# Phân biệt trách nhiệm của Spring Security với dịch vụ nghiệp vụ quản lý tài khoản

> **Ngữ cảnh:** Spring Security – Authentication, nhóm **Vòng đời tài khoản**. Bài học dành cho Java 17+, Spring Boot 3.x và Spring Security 6.x trên Servlet stack. Mục tiêu là thiết kế ranh giới đúng giữa **cơ chế xác thực/phân quyền do Spring Security cung cấp** và **quy tắc vòng đời tài khoản do hệ thống nghiệp vụ chịu trách nhiệm**. Những thành phần domain, database và email trong ví dụ là của ứng dụng, không phải những tính năng được Spring Security tự động cung cấp chỉ vì có starter.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng vai trò của `SecurityFilterChain`, `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, `SecurityContextHolder`, `AuthorizationManager` và `SecurityContextRepository`.
2. Phân biệt **xác minh credential** với **đăng ký account**, **xác minh email**, **khóa/mở khóa**, **thay đổi role**, **đặt lại mật khẩu**, **xóa/ẩn danh hóa tài khoản**, **thu hồi phiên** và **audit nghiệp vụ**.
3. Thiết kế mô hình `Account`/`AccountStatus` thuộc domain, sau đó ánh xạ sang `UserDetails` – một **adapter/projection** phục vụ authentication, không phải nguồn chân lý của dữ liệu tài khoản.
4. Đặt đúng ranh giới transaction, event và retry: cập nhật account/credential trong service nghiệp vụ, phối hợp thông báo/email, session invalidation, authorization và log.
5. Viết cấu hình Spring Security 6.x kết nối một `UserDetailsService` tùy chỉnh với user store của ứng dụng mà không đưa toàn bộ logic đăng ký/khôi phục vào filter.
6. Nhận ra thời điểm Spring Security **không tự cập nhật Authentication đang được lưu** khi account bị khóa hoặc role bị thay đổi; bổ sung cơ chế kiểm tra trạng thái hiện tại và revocation.
7. Kiểm thử sự phân tách trách nhiệm bằng unit test, integration test và security test, kể cả các đường đi không qua HTTP.

## 2. Trả lời ngắn: framework và nghiệp vụ chịu trách nhiệm gì?

**Spring Security** là framework giúp ứng dụng thực thi chính sách bảo mật: nhận request, tìm bằng chứng xác thực, kiểm chứng chúng qua provider, quản lý principal/security context, chặn request hoặc method thiếu quyền và bảo vệ các tương tác web thông dụng (CSRF, session fixation, logout, v.v.).

**Dịch vụ nghiệp vụ quản lý tài khoản (Account Service)** quyết định tài khoản **được tạo, kích hoạt, sửa, khóa, gỡ, hợp nhất, vô hiệu, phục hồi hoặc xóa** theo quy tắc sản phẩm; định nghĩa trạng thái và sự kiện, tính hợp lệ của contact, owner/tenant và các điều kiện thay đổi quyền. Account Service phối hợp với Security để quyết định một tài khoản **có đủ điều kiện đăng nhập hay không**.

Hai phía có giao nhau nhưng không được tráo vai trò:

- Spring Security không tự biết email nào cần xác minh, account nào phải được quản trị viên duyệt, trạng thái “đang chờ KYC” có nghĩa gì, ai được phê duyệt nâng role, khi nào phải xóa dữ liệu theo chính sách.
- Account Service không nên tự giải mã JWT bằng Base64, tự so password raw trong controller, tự gửi `SecurityContextHolder` giả hoặc bỏ qua `AuthorizationManager` chỉ vì có một cờ `active=true` ở DB.
- Spring Security có **interfaces** như `UserDetailsManager` với phương thức `createUser`/`updateUser`/`deleteUser`. Sự tồn tại của các API này **không có nghĩa** nó đã xây toàn bộ quy trình account lifecycle của doanh nghiệp. Bạn có thể chọn implementations của framework cho ứng dụng đơn giản, hoặc giữ domain account service riêng khi có nhiều trạng thái, audit, approval, tenant, compliance.

### Bảng phân công trách nhiệm

| Hành động | Spring Security chủ yếu làm | Account Service / nghiệp vụ phải quyết định |
|---|---|---|
| Người dùng gửi password | Filter/provider nhận credential, `PasswordEncoder.matches`, áp dụng status flags | Tài khoản/password hash lấy từ kho nào; trạng thái nào được đăng nhập |
| Sau khi login thành công | Tạo `Authentication`, xử lý security context/session, security handlers | Account nào gắn principal, chính sách rủi ro/assurance, audit bổ sung |
| Đăng ký tài khoản | Bảo vệ endpoint, CSRF và quyền truy cập request | Tạo account, chuẩn hóa định danh, unique constraint, chống lạm dụng, consent |
| Xác minh email | Bảo vệ flow/endpoint theo security policy | Phát và consume token `EMAIL_VERIFY`, cập nhật `verified_at`, xử lý đổi email |
| Khóa/mở khóa account | Có thể từ chối login qua `isAccountNonLocked` / `isEnabled` | Nguyên nhân, thẩm quyền, thời hạn, luật mở khóa, audit và revocation |
| Đổi mật khẩu | Cung cấp `PasswordEncoder`, reauthentication và bảo vệ request | Password policy, credential version, transaction, thông báo, reset grants |
| Quên mật khẩu | Bảo vệ endpoint; có thể hỗ trợ một số primitive | Token reset riêng, giao nhận email, TTL/one-use, trạng thái, thay credential |
| Đổi role | Kiểm tra `GrantedAuthority`, `hasRole`, `@PreAuthorize` | Ai được cấp role, phê duyệt, giới hạn tenant, tính hiệu lực, audit |
| Cấp quyền trên tài nguyên | Request/method authorization và extension points | Ownership, tenant, dữ liệu hiện tại, các luật sản phẩm |
| Logout / thu hồi phiên | Logout handlers, SecurityContext/session management | Chính sách logout mọi thiết bị, revoke token/session sau account event |
| Xóa hoặc ẩn danh hóa account | Chặn authentication và xử lý phiên theo cấu hình | Retention, legal hold, xóa dữ liệu, dependency, audit và chính sách sản phẩm |
| SSO/OIDC | OAuth2/OIDC login/resource-server integrations | Link identity ngoài với local account, provisioning, tenant, consent, offboarding |

**Quy tắc nhớ nhanh:** framework cung cấp **“cách kiểm chứng và thực thi”**; domain cung cấp **“trạng thái nào là hợp lệ, ai có quyền đổi trạng thái và hệ quả nghiệp vụ là gì”**. Sự phối hợp được viết qua adapter và service interfaces, không phải bằng cách để mọi controller tự thao tác Authentication.

## 3. Cấu trúc lớp khuyến nghị

```text
                    HTTPS Request
                         │
                         ▼
               ┌────────────────────┐
               │ Spring Security    │
               │ SecurityFilterChain│
               │ Authentication /   │
               │ Authorization      │
               └──────────┬─────────┘
                          │
                 UserDetailsService
                 (adapter đọc account)
                          │
                          ▼
                 AccountReadRepository
                          │
              stable userId, passwordHash,
              status, roles, tenant...
                          │
         ┌────────────────┴─────────────────────┐
         │                                      │
         ▼                                      ▼
    Authenticated request                Application Controller
    + current principal                      /account/**
         │                                      │
         ▼                                      ▼
    Domain authorization                 AccountService
    (owner, tenant, ACL)                 (use cases)
         │                                      │
         └────────────────┬─────────────────────┘
                          ▼
                    Account Domain
          ┌───────────────────────────────────┐
          │ Account, Credential, Contact,     │
          │ AccountStatus, Membership, Roles  │
          └────────────────┬──────────────────┘
                           ▼
                    Database + Outbox
                      │         │
                 local txn    async worker
                                 │
                      email / notifications /
                      audit / IdP integration
```

Các ranh giới này là **phân chia trách nhiệm**; không bắt buộc tạo microservice riêng cho Security và Account Service. Trong một monolith, chúng có thể là các package/mô-đun với dependency rõ. Quan trọng là **business invariants không nằm rải rác trong filters/controller**.

### Ví dụ cấu trúc package

```text
com.example.account
  domain/
    Account.java
    AccountStatus.java
    AccountCredential.java
  application/
    RegisterAccountUseCase.java
    VerifyEmailUseCase.java
    ChangePasswordUseCase.java
    DisableAccountUseCase.java
    GrantRoleUseCase.java
  port/
    AccountRepository.java
    OutboxPort.java
    NotificationPort.java
  adapter/
    persistence/...
    email/...

com.example.security
  AccountSecurityConfig.java
  AccountLoginLookup.java
  DatabaseUserDetailsService.java
  CurrentAccountPermission.java
  SessionRevocationPolicy.java

com.example.web
  AccountRegistrationController.java
  AccountSettingsController.java
```

Đây là sơ đồ tổ chức, không phải danh sách class Spring có sẵn. “Port” có thể được triển khai bằng Spring Data, JDBC, jOOQ hay một API nội bộ, tùy độ phức tạp. Không cần máy móc tạo tầng repository/service cho mọi getter; mục tiêu là giữ các **business transitions và security guarantees** có chỗ kiểm thử rõ.

## 4. Spring Security thực hiện authentication như thế nào?

Trong Spring Security Servlet, request mang credential đi qua security filters (tùy cơ chế: form login, HTTP Basic, bearer JWT, OAuth2 login…). Filter có thể tạo một `Authentication` **chưa xác thực**, chuyển tới `AuthenticationManager`; một `AuthenticationProvider` hỗ trợ dạng credential kiểm chứng. Sau thành công, kết quả xác thực chứa principal/authorities được đặt trong `SecurityContext` và có thể lưu vào session tùy cơ chế.

```text
Client
  │ POST /login (username, password)
  ▼
UsernamePasswordAuthenticationFilter
  │ UsernamePasswordAuthenticationToken (unauthenticated)
  ▼
AuthenticationManager / ProviderManager
  │
  └── DaoAuthenticationProvider
        ├── UserDetailsService.loadUserByUsername(...)
        │     └── AccountLoginLookup → database
        ├── PasswordEncoder.matches(rawPassword, storedHash)
        └── Account status / authorities checks
                     │
                     ▼
         Authentication (authenticated)
                     │
             SecurityContextHolder
                     │
              HTTP session (nếu cấu hình)
                     │
           AuthorizationManager / method security
```

**Không được nhầm:**

- `UserDetailsService.loadUserByUsername` **chỉ truy xuất dữ liệu** mà password provider cần (username, password hash, flags, authorities). Nó không phải “service đăng ký, tạo token email, đổi password, quản lý role” mặc định.
- `DaoAuthenticationProvider` làm nhiệm vụ kiểm chứng password đối chiếu với hash qua `PasswordEncoder`; không tự biết khách có đủ tuổi, đã xác minh danh tính hoặc đang bị legal hold.
- `Authentication` và `SecurityContextHolder` đại diện cho **trạng thái xác thực ở request/session**, không phải bản ghi account gốc và không nên dùng như ORM entity mutable.
- `GrantedAuthority` mô tả quyền mà Authentication hiện tại sở hữu; nó không tự cập nhật theo DB nếu role được quản trị viên thay đổi sau khi session đã được lưu.

### 4.1. SecurityContextRepository và phiên HTTP

Trong ứng dụng session-based, `SecurityContextRepository` quyết định cách lưu/tải security context (thường qua HTTP session). Với cơ chế token stateless, Spring Security có thể xác thực lại credential theo từng request mà không dùng HTTP session.

**Điểm phiên bản:** Spring Security 6 thiên về cơ chế lưu security context **explicit save**. Khi tự viết custom login controller/provider, chỉ gọi `SecurityContextHolder.getContext().setAuthentication(...)` không đủ để bảo đảm context được lưu qua request sau; cần sử dụng `SecurityContextRepository.saveContext(...)` và phối hợp session authentication strategy. Nếu dùng `formLogin()` sẵn có, các filter/handlers chuẩn sẽ quản lý flow theo cấu hình, không cần viết controller đăng nhập thủ công.

**Không tự gán `Authentication` do browser gửi** hoặc đặt cờ `authenticated=true` sau bước đăng ký. Mọi credential cần đi qua verifier tin cậy.

### 4.2. PasswordEncoder và nơi đặt logic mật khẩu

Spring Security cung cấp interface `PasswordEncoder` để:

```java
String hashed = passwordEncoder.encode(rawNewPassword);
boolean ok = passwordEncoder.matches(rawPresentedPassword, storedHash);
```

- **Ở authentication:** `DaoAuthenticationProvider` gọi `matches` khi kiểm chứng login.
- **Ở business use case:** `RegisterAccountUseCase` hoặc `ChangePasswordUseCase` gọi `encode` trước khi lưu mật khẩu, đồng thời kiểm tra password policy, trạng thái account, transaction và audit.
- Không để controller lưu password thô; không tự gọi `encode(password).equals(storedHash)` vì bcrypt/Argon2 dùng salt và hash mới có thể khác lần trước.
- Không dùng `NoOpPasswordEncoder` hoặc `User.withDefaultPasswordEncoder()` trong production.
- Dùng algorithm/cost thích hợp và chiến lược nâng cấp hash; `DelegatingPasswordEncoder` có prefix thuật toán `{id}` và có thể giúp migration.

**Security cung cấp công cụ hash và kiểm chứng; nghiệp vụ quyết định khi nào credential được phép tạo/thay đổi.**

## 5. Mô hình Account thuộc sở hữu của domain

Một mô hình đơn giản:

```text
Account
 ├── id                       stable local account identifier
 ├── usernameCanonical        unique theo policy
 ├── lifecycleStatus          PENDING_EMAIL, ACTIVE, SUSPENDED, DELETED...
 ├── createdAt
 ├── emailVerification        contact value + verifiedAt + version
 ├── passwordCredential       hash + changedAt + credentialVersion
 ├── memberships              tenant, team, role bindings
 ├── sessionVersion           cho revocation
 └── audit / data-retention state
```

**Không dùng email làm khóa duy nhất trong mọi ranh giới bảo mật**. Email có thể thay đổi, không được xác minh hoặc trùng giữa một số IdP/tenant. `account.id` là khóa domain ổn định; đối với danh tính SSO, liên kết thông qua bộ `(issuer, subject)` đã được IdP xác minh rồi map tới local account.

### 5.1. Business states có ý nghĩa riêng

| Trạng thái domain minh họa | Ý nghĩa nghiệp vụ | Hành vi authentication thường mong muốn |
|---|---|---|
| `PENDING_EMAIL` | Contact chưa được xác minh | Chặn login đầy đủ hoặc chỉ cho khả năng giới hạn, theo policy |
| `PENDING_APPROVAL` | Đang chờ người có quyền duyệt | Không cấp quyền đã đăng ký; chưa cho thao tác yêu cầu phê duyệt |
| `ACTIVE` | Được phép đăng nhập theo loại credential | Provider có thể xác thực nếu credential hợp lệ |
| `TEMPORARILY_LOCKED` | Khóa do bảo vệ/brute force | Từ chối login cho đến khi mở khóa theo policy |
| `SUSPENDED` | Chủ động tạm ngưng vì vi phạm/rủi ro | Chặn login mới và phiên/token cũ nếu policy yêu cầu |
| `CLOSED` | Account đã đóng, đang retention | Không login, xử lý dữ liệu theo policy lưu trữ |
| `DELETED` | Đã xóa/ẩn danh hóa theo quy trình | Không “hồi sinh” từ reset token hoặc SSO provisioning tự động |

Đây là **ví dụ thiết kế domain**, không phải enum do Spring Security cung cấp. Một tài khoản có thể đồng thời `ACTIVE` nhưng có cờ `MFA_REQUIRED`, `EMAIL_CHANGE_PENDING` hoặc `PASSWORD_RESET_REQUIRED`. Không nên nhồi tất cả vào một enum duy nhất nếu trạng thái có chiều độc lập.

### 5.2. UserDetails là projection, không phải Account

Spring Security interface `UserDetails` cung cấp các phương thức như `getUsername()`, `getPassword()`, `getAuthorities()`, `isAccountNonExpired()`, `isAccountNonLocked()`, `isCredentialsNonExpired()`, `isEnabled()`.

**Ánh xạ có chủ ý:**

- `isEnabled=false` có thể dùng để không cho login đầy đủ khi account chưa đủ điều kiện.
- `isAccountNonLocked=false` có thể biểu thị khóa theo policy.
- `isCredentialsNonExpired=false` có thể yêu cầu người dùng xử lý credential đã quá hạn qua flow riêng.
- `getAuthorities` lấy từ role/membership đã được phê duyệt, không lấy thẳng từ form `roles=ADMIN` của client.
- Trạng thái `PENDING_KYC` không nhất thiết map 1-1 với `isEnabled`; nhiều hệ thống cho login cơ bản nhưng chặn giao dịch cần KYC. Khi đó authorization ở tầng nghiệp vụ phải kiểm tra KYC tại **đúng hành động**.

Điều quan trọng là account status domain có thể **chi tiết hơn** bốn flags của `UserDetails`. **Không** ép quy tắc nghiệp vụ phức tạp vào phương thức `isEnabled()` hoặc một chuỗi role `ROLE_PENDING` mà không rõ cách vận hành.

### 5.3. Dữ liệu bền vững và concurrency

PostgreSQL schema minh họa:

```sql
CREATE TABLE app_accounts (
    id UUID PRIMARY KEY,
    canonical_username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    lifecycle_status TEXT NOT NULL,
    email_verified_at TIMESTAMPTZ,
    credential_version BIGINT NOT NULL DEFAULT 0,
    session_version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT app_account_status_valid CHECK (
      lifecycle_status IN (
       'PENDING_EMAIL', 'PENDING_APPROVAL', 'ACTIVE',
       'TEMPORARILY_LOCKED', 'SUSPENDED', 'CLOSED', 'DELETED'
      )
    )
);

CREATE TABLE account_role_bindings (
    account_id UUID NOT NULL REFERENCES app_accounts(id),
    tenant_id UUID NOT NULL,
    role_name TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (account_id, tenant_id, role_name)
);

CREATE INDEX account_role_tenant_idx
    ON account_role_bindings(tenant_id, role_name);
```

Schema là minh họa **không chứa migrations đầy đủ**: production cần chính sách email normalized/unique phù hợp, consent, xử lý xóa mềm/retention, constraints, optimistic locking/version và kiểm soát tenant trong mọi truy vấn. `password_hash` nullable nếu account có SSO-only identity; không cấp login password nếu nó null. Không tự tạo local password cho account SSO chỉ vì email bên ngoài trùng.

**Tenant boundary:** chính sách “có ROLE_ADMIN trong tenant A” không đồng nghĩa “có ROLE_ADMIN toàn hệ thống”. Một `ROLE_ADMIN` toàn cục không đủ biểu diễn mọi ACL theo tenant; dùng role binding + resource ownership. Mọi update role cần chỉ rõ tenant scope và actor quyền duyệt.

## 6. Quy trình vòng đời thuộc Account Service

### 6.1. Đăng ký và xác minh email

Quy trình điển hình:

```text
POST /signup
  → validation/rate limit
  → normalize username/email theo policy
  → kiểm tra unique + DB unique constraint
  → hash password bằng PasswordEncoder
  → transaction tạo Account PENDING_EMAIL
  → tạo verification grant purpose=EMAIL_VERIFY + TTL
  → ghi outbox event
  → commit
  → worker gửi email tới contact đã đăng ký
  → GET verification landing, POST token confirm
  → atomic consume, cập nhật verifiedAt/status theo policy
  → hướng về login bình thường
```

Spring Security có thể kiểm soát quyền đến `/signup`, `/verify-email` và CSRF, nhưng **không tự biết** các bước domain ở trên. Không chuyển account sang `ACTIVE` ngay khi một request khai `emailVerified=true`. Phải xác minh token/callback với nguồn đáng tin, đúng owner/purpose/TTL và update trong transaction.

Có thể dùng OTP/Magic link library của Security cho **đăng nhập một lần**, nhưng **không tái sử dụng token đăng nhập** làm token xác minh email hoặc password reset nếu chúng có purpose khác. Namespace, verifier và side effects phải tách rời.

### 6.2. Đổi email, đổi mật khẩu và phục hồi

- **Đổi email:** xác thực lại/step-up tùy rủi ro, lưu email mới ở trạng thái pending, gửi verification tới contact mới, xác nhận đúng purpose, bảo vệ phiên và thông báo contact cũ. Account Service quyết định contact nào được tin.
- **Đổi mật khẩu khi đã login:** kiểm tra reauthentication, password policy, `PasswordEncoder.encode` và credential version. Không chỉ nhận `newPassword` rồi cập nhật vì user có một session.
- **Quên mật khẩu:** phát recovery token CSPRNG, TTL ngắn, lưu hash, một lần, gắn đúng account, không auto-login. Reset token **không** phải access token/magic login token.
- **Khôi phục MFA/device:** có chính sách riêng bảo vệ enrollment, backup codes và helpdesk. Không cho email reset tự xóa security key.
- **Đăng ký OAuth/OIDC identity:** Security xác minh provider response; Account Service map `(iss, sub)` sang local account qua link policy, không tự liên kết bằng email chưa xác minh.

### 6.3. Khóa và mở khóa

Có hai trường hợp dễ nhầm:

1. **Khóa tự động vì quá nhiều lần login sai:** cơ chế kỹ thuật có thể nhận tín hiệu từ authentication failure event, áp dụng rate limit, tăng counter và đặt thời điểm unlock theo policy.
2. **Suspension do quản trị viên/pháp lý:** đây là quyết định nghiệp vụ có actor, reason, approvals, audit; không phải lỗi password sai.

Account Service quản lý sự chuyển trạng thái, lưu audit và quyết định có revoke toàn bộ sessions/token hay không. Spring Security sử dụng projection mới để **từ chối login mới** và được tích hợp để **chặn phiên cũ**; chỉ đặt `enabled=false` trong DB không tự xóa session đang hoạt động.

### 6.4. Thay đổi role và membership

Business flow thường cần:

```text
Actor request: "Grant BILLING_APPROVER cho user-42 ở tenant-A"
  │
  ├─ authenticate actor + MFA freshness
  ├─ check actor được cấp role này trong tenant-A
  ├─ enforce separation-of-duties (nếu cần)
  ├─ check target account ACTIVE, đúng tenant, limit
  ├─ optional independent approval
  ├─ transaction update account_role_bindings
  ├─ increase authzVersion / revoke stale session rights
  └─ audit + notification
```

Spring `@PreAuthorize("hasRole('ADMIN')")` chỉ là một **điều kiện**; framework không tự biết “ADMIN nào”, “tenant nào”, “được phê duyệt role nào”, “có được tự nâng quyền không” hay “cần hai người chấp thuận không”. Các ràng buộc này nằm trong **business policy** và phải chạy cả khi use case được gọi từ job, listener hoặc một API khác, không chỉ UI.

### 6.5. Xóa/đóng tài khoản

Quy trình xóa account có thể kéo theo:

- Kiểm tra quyền và trạng thái: người dùng tự xóa hay admin thực hiện; có legal hold/retention nghĩa vụ gì?
- Vô hiệu hóa authentication và sessions ngay theo policy.
- Vô hiệu grants/recovery tokens/magic links còn hạn.
- Xóa hoặc ẩn danh hóa dữ liệu theo loại dữ liệu và retention; không xóa nhầm chứng từ cần lưu.
- Thu hồi external identity links, refresh tokens, ứng dụng được ủy quyền theo hợp đồng với IdP.
- Ghi audit tối thiểu, thông báo kênh đủ tin và xử lý retry/idempotency.

Spring Security **không tự thực hiện workflow xóa tài khoản** hay biết tác động tới hóa đơn, đơn hàng và hợp đồng. Domain và các dịch vụ phụ trách phải phối hợp.

## 7. Cấu hình Spring Security 6.x cho form login

Ví dụ dùng **Spring Boot 3.x + Spring Security 6.x, Java 17** và credential nội bộ. Các đoạn Spring là **các mảnh tích hợp trong project**, không chạy bằng một lệnh `javac` vì cần starter, account repository, HTTP app và database.

### 7.1. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Đây là các lựa chọn thông dụng; có thể thay JPA bằng JDBC/jOOQ và Mail bằng queue/notification provider. Tên version được quản lý qua BOM/plugin Spring Boot của dự án.

### 7.2. SecurityFilterChain + PasswordEncoder

File `src/main/java/com/example/security/AccountSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AccountSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/signup", "/verify-email", "/login").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/signup", "/verify-email").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Giữ CSRF mặc định cho các POST của web/session login.
        return http.build();
    }
}
```

**Ý nghĩa:**

- `formLogin()` kích hoạt cơ chế form username/password của Security, dùng `UserDetailsService`/`PasswordEncoder` phù hợp khi cấu hình đầy đủ.
- `requestMatchers` là các rule cho HTTP endpoints; `permitAll()` chỉ cho phép anonymous gọi route, **không** tạo tài khoản hay xác minh email.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` trong `Authentication`. Không tự thực thi chính sách phân quyền tenant hoặc xét duyệt nâng quyền.
- `@EnableMethodSecurity` bật khả năng kiểm soát truy cập method qua `@PreAuthorize`/...; Spring Boot starter Security không tự bật tất cả method security nếu không cấu hình.
- Nếu app dùng templates như Thymeleaf, controller của domain phải cung cấp GET/POST tương ứng và CSRF input. Không tắt CSRF chỉ để form đăng ký hoạt động; cần đưa token vào POST đúng cách.
- Những endpoint riêng như `/admin` (không có dấu slash cuối) hoặc các đường đi tương đương phải được bao phủ bằng rules rõ; không cho một đường khác gọi trực tiếp use case mà bỏ chính sách bảo mật.

### 7.3. Tạo adapter UserDetailsService cho Account store

Một DTO đọc từ account repository; nó **không phải** Spring Security type:

File `src/main/java/com/example/security/AccountLoginSnapshot.java`:

```java
package com.example.security;

import java.util.Set;

public record AccountLoginSnapshot(
        String accountId,
        String canonicalUsername,
        String passwordHash,
        boolean passwordLoginAllowed,
        boolean accountNonLocked,
        Set<String> approvedGlobalRoles) {}
```

File `src/main/java/com/example/security/AccountLoginLookup.java`:

```java
package com.example.security;

import java.util.Optional;

public interface AccountLoginLookup {

    Optional<AccountLoginSnapshot> findForPasswordLogin(
        String canonicalUsername);
}
```

File `src/main/java/com/example/security/DatabaseUserDetailsService.java`:

```java
package com.example.security;

import java.util.List;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountLoginLookup lookup;

    public DatabaseUserDetailsService(AccountLoginLookup lookup) {
        this.lookup = lookup;
    }

    @Override
    public UserDetails loadUserByUsername(String submittedUsername) {
        // Normalize/login-name lookup theo CHÍNH SÁCH DOMAIN.
        // Database lookup phải áp dụng account/tenant boundary đúng.
        AccountLoginSnapshot a = lookup.findForPasswordLogin(
                submittedUsername)
            .orElseThrow(() ->
                new UsernameNotFoundException("Unknown account"));

        if (a.passwordHash() == null) {
            // Account SSO-only: không tự tạo mật khẩu nội bộ.
            throw new UsernameNotFoundException("Password login unavailable");
        }

        List<SimpleGrantedAuthority> authorities =
            a.approvedGlobalRoles().stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .toList();

        return new User(
            a.canonicalUsername(),
            a.passwordHash(),
            a.passwordLoginAllowed(), // enabled
            true,                     // accountNonExpired
            true,                     // credentialsNonExpired
            a.accountNonLocked(),
            authorities
        );
    }
}
```

**Tính biên dịch:** ba files trên có type references đầy đủ trong các mảnh được hiển thị; một bean **triển khai** `AccountLoginLookup` và hạ tầng database thật vẫn cần được cung cấp để app chạy. `approvedGlobalRoles` phải là dữ liệu đã được domain phê duyệt và chuẩn hóa; không nhận chuỗi role do client gửi rồi prefix `ROLE_` mà không kiểm chứng. Role theo tenant/resource nên được giải quyết ở policy layer thay vì biến tất cả thành global role.

**Cách mapper hoạt động:**

- `lookup` chỉ trả **projection tối thiểu** dùng cho password login; không lôi địa chỉ nhà, giao dịch, KYC documents hoặc toàn bộ Aggregate vào SecurityContext/session.
- `passwordLoginAllowed` được tính từ trạng thái domain, loại credential và policy đã xác minh; nó không đơn thuần là user tự bật cờ trong request.
- `accountNonLocked` phản ánh lock theo domain. Mỗi application có thể thêm mapping `accountNonExpired`/`credentialsNonExpired` nếu có chính sách riêng.
- Không coi `UserDetailsService.loadUserByUsername` là nơi ghi `lastLoginAt`. Phương thức có thể được gọi nhiều lần bởi authentication flow/cache; cập nhật last login cần một event hoặc handler sau khi authentication **thực sự thành công**.
- Không gửi chi tiết “account không tồn tại” hoặc “bị khóa” khác biệt đến client khi chính sách chống enumeration yêu cầu response trung tính; exceptions, logs và audit cần tách nội bộ.
- Nếu dùng username có thể đổi, nên có **stable account ID** trong principal/security context để tránh nhầm người; `getName()` mặc định thường là username, không bảo đảm là khóa domain.

### 7.4. Không tự đăng nhập sau khi tạo account

Sai:

```java
// SAI: client vừa POST /signup, account chưa được xác minh
SecurityContextHolder.getContext().setAuthentication(
    UsernamePasswordAuthenticationToken.authenticated(
        submittedEmail, null, List.of(
            new SimpleGrantedAuthority("ROLE_USER"))));
```

Đây là **mã phản ví dụ**, không được dùng production. Việc lấy dữ liệu request rồi tạo `authenticated(...)` cho người chưa được verifier kiểm chứng có thể bỏ qua chính sách kích hoạt, MFA và login. Account Service phải tạo `PENDING_EMAIL` và phát token xác minh; chỉ flow xác thực phù hợp mới cấp Authentication.

Ngay cả khi muốn **auto-login sau đăng ký** vì UX, cần chính sách minh bạch: account đã đáp ứng yêu cầu kích hoạt chưa, verifier nào tin cậy, MFA/session fixation và `SecurityContextRepository` lưu context ra sao. Không tự động làm theo suy đoán.

## 8. Dịch vụ nghiệp vụ: nơi đặt các invariants và transaction

Ví dụ sơ đồ `RegisterAccountUseCase` (pseudocode, không phải Java source độc lập):

```text
register(command):
    validate form + password policy
    normalize username/email bằng domain rules
    check uniqueness; rely on DB unique constraints for race safety
    encoded = PasswordEncoder.encode(command.rawPassword)

    begin transaction
       account = Account.create(PENDING_EMAIL, encoded, verifiedAt=null)
       AccountRepository.save(account)
       token = EmailVerificationToken.issueRandomFor(account.id)
       VerificationRepository.storeHashAndExpiry(token)
       OutboxPort.save(EmailVerificationRequested(account.id, tokenReference))
       commit
    worker retrieves protected delivery data; sends one-time link
    return generic registration response
```

**Chi tiết quan trọng về email outbox:** Không nên đưa **raw token** trực tiếp vào event log có nhiều consumer/retention dài. Nếu cần worker gửi mail bất đồng bộ, thiết kế một kênh delivery data được mã hóa, hạn chế truy cập và xóa sau khi gửi; hoặc phát token tại bước phù hợp với guarantee transaction. Tính nhất quán giữa ghi DB và gửi email là một quyết định nghiệp vụ, không do `SecurityFilterChain` giải quyết.

### 8.1. Account transition cần atomic

Ví dụ verify email:

```text
verifyEmail(rawToken):
    find verification grant by hash, purpose=EMAIL_VERIFY
    begin transaction
       claim unconsumed grant with expiresAt > now atomically
       lock account and confirm ownership/contact version
       set account.emailVerifiedAt
       if other activation gates satisfied → account.ACTIVE
       save account and event
       commit
    return a neutral success/failure page
```

Cần xử lý **hai requests cùng token**, **token hết hạn**, **contact đổi trong lúc token đang sống**, **tài khoản bị admin suspended**. “Mở link” không tương đương “login thành công”; mail scanners có thể GET URL trước user, nên tránh tiêu thụ token ở GET nếu flow có tương tác confirm.

### 8.2. Thay đổi mật khẩu

Trong `ChangePasswordUseCase` hoặc `ResetPasswordUseCase`:

- Validate authorization/reauth hoặc reset token riêng purpose-bound.
- Verify policy mật khẩu; dùng `PasswordEncoder.encode` trước khi lưu.
- Trong một transaction: update `passwordHash`, tăng `credentialVersion` và/hoặc `sessionVersion`, invalidate reset grants theo policy, ghi event.
- Không tự cấp full login session từ reset token; yêu cầu login/MFA đúng quy trình.
- Thu hồi session/tokens cũ **thực tế** theo cơ chế đang dùng. Nếu JWT self-contained xác minh cục bộ, thay password DB không tự sửa JWT cũ.

### 8.3. Approvals và kiểm soát quyền

`GrantRoleUseCase` nên tự kiểm tra actor, tenant và quyền cấp role trước khi save. `@PreAuthorize("hasRole('ADMIN')")` là lớp bảo vệ tốt nhưng có thể không đủ nếu “admin không được tự nâng mình” hoặc “phê duyệt role tài chính cần hai người”. Những ràng buộc này phải nằm trong policy có thể unit-test mà không phụ thuộc request path.

Ví dụ domain policy:

```text
canApproveRoleGrant(actor, target, role, tenant):
    actor authenticated and currently active
    actor has GRANT_ROLE capability for this tenant
    target belongs to same tenant and is ACTIVE
    actor != target if separation-of-duties required
    role is assignable (not immutable/system owner)
    approval workflow state is satisfied
    no conflicting role grants under risk policy
```

Không lấy `roleName`/`tenantId` từ UI rồi chạy trực tiếp `user.setAuthorities(...)` trên principal hiện tại; cập nhật đúng binding trong DB và xử lý hiệu lực với sessions.

## 9. Phân quyền nghiệp vụ: Security là cơ chế thực thi, domain là nguồn quy tắc

### 9.1. hasRole không thay kiểm tra ownership

Giả sử một account có `ROLE_USER`. Với endpoint `GET /orders/815`:

```java
@PreAuthorize("hasRole('USER')")
public OrderView readOrder(long orderId) {
    return orders.load(orderId);
}
```

Mã trên có thể cho mọi `ROLE_USER` đọc tất cả đơn nếu `orders.load` không kiểm tra chủ sở hữu/tenant. Đây là lỗi **broken object level authorization (BOLA/IDOR)**. Quy tắc sản phẩm có thể yêu cầu:

```text
user is authenticated
AND user has global ability to read orders
AND order.tenantId == user's active tenant
AND order.ownerId == user's stable account ID
AND order not restricted by business status
```

Có thể triển khai qua `@PreAuthorize` gọi bean policy, hoặc gộp điều kiện ownership vào câu query đã được kiểm soát:

```java
// Snippet của domain service, cần OrdersRepository và Policy bean.
public OrderView readOrder(long id, AuthenticatedActor actor) {
    return orders.findVisibleToActor(id, actor.accountId(),
            actor.tenantId())
        .orElseThrow(() -> new OrderNotAccessibleException());
}
```

Mảnh code trên dùng các **types do ứng dụng định nghĩa**, không phải Java chạy độc lập. Nó diễn đạt quy tắc query tenant-scoped; cần kiểm thử repository để bảo đảm không có nhánh gọi `findById` rồi bỏ qua ownership.

### 9.2. @PreAuthorize cần được bật và áp dụng đúng

Spring Security 6.x hỗ trợ:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

Khi bật, `@PreAuthorize`, `@PostAuthorize` và các method interceptors theo policy được áp dụng cho **Spring-managed beans**. Vì dùng Spring AOP, lời gọi **self-invocation** từ một method tới method annotated khác trong cùng object có thể đi vòng proxy; không dựa vào annotation trên private/internal method như bảo vệ duy nhất. Không phải mọi lời gọi từ scheduler/queue sẽ có một HTTP security context; với các tác vụ backend, yêu cầu actor/service identity phải được truyền và xác minh một cách phù hợp.

**Phân lớp hợp lý:** request security chặn request chưa auth, method security kiểm tra quyền chức năng, domain service đảm bảo tenant/owner/approval và cập nhật trạng thái qua transaction. Không phải mọi rule đều cần được diễn đạt bằng SpEL; business policy Java độc lập dễ test hơn.

### 9.3. Tác động khi role thay đổi sau đăng nhập

`Authentication` chứa một snapshot các `GrantedAuthority`. Nếu admin gỡ `ROLE_ADMIN` khỏi DB, một phiên cũ có thể vẫn giữ authority cũ. Tương tự JWT access token có `scope`/`roles` cũ có thể vẫn còn hạn.

Các giải pháp cần chọn theo mức rủi ro:

- Invalidate HTTP sessions khi role/account status thay đổi.
- Tăng `sessionVersion`/`authzVersion` và kiểm tra ở từng request hoặc trong cache có invalidation/TTL ngắn.
- Đối với JWT, dùng denylist/opaque introspection/version lookup/TTL ngắn; chỉ đổi password hoặc role ở DB không thu hồi offline JWT ngay.
- Truy vấn quyền hiện tại cho các thao tác nhạy cảm ngay tại business service; chú ý cache và consistency.
- Phát audit/notification từ Account Service và kết nối hệ thống session/security qua event với điều kiện **không fail open** ở endpoint quan trọng.

Không được ghi “account suspended ⇒ tất cả JWT đã phát tự hết hiệu lực” trừ khi Resource Servers **thực sự kiểm tra** trạng thái revoke.

## 10. Nguồn chân lý, cache và consistency

Một trong những lỗi phổ biến nhất là để ba nguồn dữ liệu khác nhau trả lời cùng một câu hỏi về account:

```text
users table: account.status = SUSPENDED
JWT:         roles = ["ADMIN"]  (phát trước khi khóa)
Session:     Authentication.authorities = ROLE_ADMIN
Cache:       user.enabled = true (chưa bị invalidated)
```

**Cách xác định ranh giới:**

1. Account database/service là **source of truth** cho trạng thái nghiệp vụ (trừ khi hợp đồng IdP là nguồn authoritative cho một thuộc tính xác định).
2. `UserDetails`, `Authentication` và JWT claims là **biểu diễn phục vụ authentication**, có thể là snapshot với độ trễ.
3. Policy engine/business service quyết định khi nào phải đọc trạng thái mới nhất, khi nào cache được phép dùng và SLO chậm cập nhật tối đa.
4. Event-driven propagation phù hợp cho thông báo, cache invalidation, analytics; nhưng nếu event bị trễ hoặc queue downtime, endpoint nhạy cảm không thể ngầm chấp nhận quyền cũ.
5. Định nghĩa chính sách fail closed khi không thể kiểm tra trạng thái hoặc permission.

Đừng load toàn bộ Aggregate vào SecurityContext và giữ nó nhiều ngày; entity JPA có thể stale, lazy-loading ngoài transaction và chứa nhiều PII. Nên dùng stable principal ID cùng projection tối thiểu, rõ vòng đời và version.

### 10.1. Cache UserDetailsService có thể làm login stale

Một `CachingUserDetailsService` hoặc cache tự viết có thể giữ trạng thái `enabled=true` sau khi account bị khóa. Cần làm rõ TTL, cache eviction khi account event, cơ chế version hoặc bỏ cache với hành động nhạy cảm. Cache password hash cũng có các vấn đề xóa credentials sau authenticate mà framework đã lưu ý; phải kiểm thử cho từng cấu hình.

### 10.2. Account deleted và external identity provisioning

Với `oauth2Login()`, Spring Security xác minh quy trình OIDC/OAuth2 login và cung cấp principal/claims; hệ thống nghiệp vụ quyết định local account tương ứng **được phép tồn tại** hay phải chờ approval. Nếu account đã xóa hoặc bị cấm, không tự tạo lại một user có email giống email claim từ IdP. Liên kết external identity dựa trên `(issuer, subject)` và consent/ownership policy, không chỉ email match.

## 11. Ví dụ Java 17 độc lập: phân tách đăng nhập, trạng thái và quyền

Chương trình sau **biên dịch và chạy độc lập với JDK 17+**, không cần Spring. Nó không mô phỏng cryptographic password verification; biến `passwordVerified` là kết quả giả định mà một verifier tin cậy (ví dụ `DaoAuthenticationProvider`) đã kiểm tra. Mục tiêu là chứng minh **trạng thái account và quyền thay đổi do domain quyết định**, còn credential verification chỉ là một điều kiện của login.

Lưu file `AccountResponsibilityDemo.java`:

```java
import java.util.Set;

public class AccountResponsibilityDemo {

    enum State {
        PENDING_EMAIL, ACTIVE, SUSPENDED, DELETED
    }

    record Account(
        String id,
        State state,
        Set<String> approvedRoles,
        long sessionVersion
    ) {}

    record SessionProof(
        String subjectId,
        long issuedSessionVersion
    ) {}

    // Giai đoạn xác thực chỉ nên hoàn tất nếu domain cho login.
    static boolean canCompleteLogin(
            Account account, boolean passwordVerified) {
        return account != null
            && passwordVerified
            && account.state() == State.ACTIVE;
    }

    // Business policy: chỉ actor đủ quyền được xin cấp role.
    static boolean canRequestAdminGrant(
            Account actor, Account target) {
        return actor != null
            && target != null
            && actor.state() == State.ACTIVE
            && target.state() == State.ACTIVE
            && actor.approvedRoles().contains("SECURITY_ADMIN")
            && !actor.id().equals(target.id());
    }

    // Security session phải tôn trọng tình trạng và version mới.
    static boolean sessionStillAllowed(
            Account account, SessionProof session) {
        return account != null
            && session != null
            && account.state() == State.ACTIVE
            && account.id().equals(session.subjectId())
            && account.sessionVersion()
                == session.issuedSessionVersion();
    }

    public static void main(String[] args) {
        Account pending = new Account(
            "user-42", State.PENDING_EMAIL, Set.of("USER"), 1L);
        Account active = new Account(
            "user-42", State.ACTIVE, Set.of("USER"), 1L);
        Account operator = new Account(
            "operator-9", State.ACTIVE,
            Set.of("SECURITY_ADMIN"), 1L);
        Account suspended = new Account(
            "user-42", State.SUSPENDED, Set.of("USER"), 2L);
        SessionProof oldSession = new SessionProof("user-42", 1L);

        System.out.println("Pending email login: " +
            canCompleteLogin(pending, true));
        System.out.println("Active correct password: " +
            canCompleteLogin(active, true));
        System.out.println("Wrong password: " +
            canCompleteLogin(active, false));
        System.out.println("Self-grant request: " +
            canRequestAdminGrant(active, active));
        System.out.println("Operator grant request: " +
            canRequestAdminGrant(operator, active));
        System.out.println("Suspended login: " +
            canCompleteLogin(suspended, true));
        System.out.println("Old session blocked: " +
            !sessionStillAllowed(suspended, oldSession));
    }
}
```

Lệnh chạy:

```bash
javac AccountResponsibilityDemo.java
java AccountResponsibilityDemo
```

Stdout chính xác:

```text
Pending email login: false
Active correct password: true
Wrong password: false
Self-grant request: false
Operator grant request: true
Suspended login: false
Old session blocked: true
```

**Ý nghĩa của từng quyết định:**

- `PENDING_EMAIL` không được login đầy đủ trong policy demo, dù password đã được verify.
- Một account `ACTIVE` với password đã verify có thể hoàn tất login.
- Một account `ACTIVE` nhưng password sai không được login; business state không thay cryptographic verifier.
- Actor không được tự xin cấp quyền admin cho chính mình theo **quy tắc separation-of-duties minh họa**.
- `operator-9` có quyền gửi yêu cầu cấp role cho target đang ACTIVE; đây **không phải bằng chứng role đã được grant hoặc đã qua approval**.
- Suspended account bị chặn login mới.
- Session của user phát ở version 1 không còn hợp lệ khi account bị suspended và version tăng lên 2.

**Giới hạn của demo:** mã chỉ mô phỏng quyết định theo state; không đọc database, không có Spring Security, HTTP session, password hashing hay domain event. `Set.of` chỉ chứa roles cố định để thể hiện logic, không phải kho permissions production; các policy về tenant, phê duyệt và audit phải bổ sung trong hệ thống thật.

## 12. Các vấn đề giao thoa: ai sở hữu trách nhiệm cuối cùng?

### 12.1. Đăng ký thành công nhưng login bị từ chối

Đây **không mặc nhiên là bug**. Account vừa tạo có thể ở `PENDING_EMAIL` hoặc `PENDING_APPROVAL`; account service đã ghi dữ liệu đúng nhưng authentication vẫn từ chối tới khi điều kiện kích hoạt hoàn tất.

Cần UX rõ: “Đăng ký đã nhận, kiểm tra email” thay vì “Tài khoản đã đăng nhập”. Tránh trả lỗi chi tiết “email chưa xác minh” trên endpoint login công khai nếu nó giúp dò tài khoản ngoài chính sách.

### 12.2. Security kiểm tra được mật khẩu nhưng Account bị khóa

`DaoAuthenticationProvider` có thể tìm thấy hash hợp lệ; song `UserDetails.isEnabled/isAccountNonLocked` hoặc custom provider/policy chặn kết quả. Account Service chịu trách nhiệm tính chính xác status và quyền khóa; Security thực thi quyết định ở authentication.

Nếu account bị khóa sau khi user đã có session, còn phải giải quyết các phiên cũ (không chỉ lần login kế tiếp).

### 12.3. Xác minh email từ IdP có đủ để kích hoạt local account?

**Không mặc định.** Với SSO, `email_verified` chỉ là thông tin theo hợp đồng provider. Ứng dụng phải xác minh issuer, subject và chính sách linking, không tự cho chiếm account local có cùng email. Kích hoạt account còn có thể cần invitation, admin approval, tenant membership và consent.

### 12.4. Đăng xuất ở browser có xóa mọi OAuth token không?

Không. Spring Security logout thường làm sạch SecurityContext/session/cookies theo cấu hình. Nếu có refresh token ở Authorization Server hoặc access token JWT còn hạn ở Resource Servers, logout app không tự thu hồi tất cả credential. Account Service/Security integration phải quy định mức thu hồi cần đạt và gọi revocation endpoints/check versions phù hợp.

### 12.5. Có thể dùng UserDetailsManager làm Account Service không?

Với ví dụ nhỏ/in-memory/JDBC đơn giản, `UserDetailsManager` hỗ trợ thêm, cập nhật, xóa, kiểm tra sự tồn tại và đổi mật khẩu theo implementation. Nhưng nó không thay một **business account aggregate** khi cần email verification, multi-tenant memberships, approval, legal holds, deletion workflow, audit và integration. Có thể bọc/adapter vào kiến trúc application nếu phù hợp, nhưng không ép domain business phụ thuộc trực tiếp vào Spring Security user record.

## 13. Anti-patterns cần tránh

| Anti-pattern | Vì sao nguy hiểm | Cách thay thế |
|---|---|---|
| Controller `/signup` tự gán `Authentication` authenticated | Bỏ qua identity proof / activation / MFA | Domain tạo account; Security login đúng cơ chế |
| `UserDetailsService` tự gửi email kích hoạt hoặc cập nhật last login | Lookup có thể bị gọi nhiều lần/cache, side effects khó kiểm soát | Gửi email từ AccountUseCase và outbox; login-success handler/event cho audit |
| Mọi quy tắc nghiệp vụ nằm trong `SecurityFilterChain` | Security config cồng kềnh, không test domain độc lập | Domain policies + application service + adapters |
| `ROLE_ADMIN` lấy từ JSON đăng ký | Privilege escalation | Default role cố định/được duyệt, role-grant use case |
| Dùng username/email làm stable ID | Có thể đổi, trùng tenant/provider và bị reuse | Stable local account ID và external (iss,sub) mapping |
| Account lock chỉ cập nhật DB | Session/JWT cũ có thể còn quyền | Version check, revoke, invalidate sessions |
| Cache `UserDetails` không invalidated | Tình trạng enabled/role stale | TTL/invalidation, kiểm tra state hiện hành |
| Controller trực tiếp cập nhật `password_hash` | Thiếu password policy/transaction/audit | Change/ResetPasswordUseCase + PasswordEncoder |
| Reset password xong tự bật MFA off | Đường recovery phá vỡ bảo mật login | MFA recovery riêng và step-up đúng policy |
| Tạo account SSO-local chỉ vì email trùng | Account takeover / identity confusion | Verify issuer+subject, explicit safe account linking |
| `hasRole("USER")` đủ cho đọc mọi resource | IDOR/BOLA | Per-resource/tenant ownership policy |
| `@PreAuthorize` trên private/self-invoked method | Bypass Spring AOP interceptor | Proxy/service boundary và domain invariants |
| DB transaction cộng gửi email trực tiếp | Có thể email đã gửi nhưng transaction rollback | Outbox + protected delivery + retry |
| Cứ gửi event async rồi coi revoked ngay | Token/session cũ có thể còn hợp lệ trong propagation window | Live version checks hoặc fail-closed revocation |
| Lưu JPA Account trong session | Stale data, lazy-loading, PII leak | Principal tối thiểu (stable ID, scoped claims) |
| “Framework lo hết bảo mật” | Thiếu onboarding, recovery, account states và authz tài nguyên | Threat model và ownership matrix rõ ràng |

## 14. Ma trận kiểm thử trách nhiệm và ranh giới

### 14.1. Authentication/authorization

- Account `ACTIVE`, password hash hợp lệ: `DaoAuthenticationProvider` xác thực; Authentication có principal và authorities đúng policy.
- Password sai: bị từ chối; không vì account active mà bypass `PasswordEncoder.matches`.
- Account `PENDING_EMAIL` hoặc `SUSPENDED`: login đầy đủ bị từ chối theo policy, kể cả password đúng.
- Account SSO-only có `password_hash=null`: không login qua password provider.
- Admin grant mới: session cũ không tự nhận quyền nếu chính sách không có refresh/version; test chính xác cách hiệu lực mong muốn.
- Admin revoke quyền: API nhạy cảm phải từ chối trước khi policy latency tối đa; không tin scope/roles stale.
- User thường đọc đơn user khác cùng tenant hoặc tenant khác: phải từ chối dù có `ROLE_USER`.
- HTTP route bị chặn nhưng method service có thể được job gọi: test policy ở service/domain, không phụ thuộc duy nhất URL filter.

### 14.2. Vòng đời account

- Request đăng ký email chưa verified: tạo `PENDING_EMAIL`, không tạo login session.
- Xác minh email token đúng purpose, đúng owner, chưa hạn và chưa dùng: cập nhật verifiedAt/status qua transaction.
- Email verification token sai purpose hoặc replay: từ chối, không thay account.
- Hai request đăng ký cùng canonical username/email: chỉ một transaction thành công nhờ DB unique constraint.
- Đổi email: địa chỉ mới ở pending, không thay contact đáng tin trước verify; old-email notice theo policy.
- Admin suspension: ghi actor/reason, thay status, tăng sessionVersion hoặc revoke sessions theo policy.
- Unlock account: chỉ actor có quyền hoặc đúng recovery process; không tự unlock admin suspension do password reset.
- Xóa account: chặn login và phiên cũ, giữ đúng retention, không hồi sinh từ SSO login/email reset token còn hạn.
- Role grant qua domain use case: kiểm tra actor/tenant/approval, từ chối self-elevation không được duyệt.
- Request giả `role=ADMIN` ở signup: bị bỏ qua/từ chối; không xuất hiện trong authorities.

### 14.3. Cross-component, cache và failure

- Account service commit thay status nhưng cache user chưa invalidated: đo độ trễ trước khi security chặn và xử lý theo SLO.
- Event bus downtime khi user bị khóa: endpoint rủi ro cao phải fail closed hoặc check version authoritative.
- Password reset hoàn tất nhưng invalidate token ở dịch vụ khác thất bại: outbox/retry và cơ chế chặn không cho stale session vượt policy.
- Authentication thành công ở node A, account suspended ở node B: node A phải từ chối lại theo chính sách khi xử lý request tiếp.
- SecurityContext session được tạo bởi custom login controller: phải được lưu theo Spring Security 6 `SecurityContextRepository`, không chỉ đặt ThreadLocal.
- Service tự gọi method annotated `@PreAuthorize` trong cùng class: kiểm thử để phát hiện proxy bypass.
- Tài khoản ở tenant A có quyền admin nhưng tenant B không: domain policy từ chối admin action tenant B.
- Domain Account entity chứa PII không được serialize vào principal/session hoặc error response.
- Phát email/outbox với token: không để raw token xuất hiện ở log, queue chia sẻ hoặc hệ thống analytics thiếu bảo vệ.

### 14.4. Tests gợi ý

```text
registerCreatesPendingAccountNotAuthentication()
unverifiedEmailDoesNotAutomaticallyActivateAccount()
daoProviderValidatesPasswordHashAndAccountFlags()
suspendedAccountCannotLoginEvenWithValidPassword()
existingSessionDoesNotBypassAccountRevocation()
userDetailsServiceLookupHasNoBusinessSideEffects()
roleApprovalCannotBeBypassedByClientSuppliedRole()
tenantAdminCannotGrantRoleAcrossTenants()
methodSecurityDoesNotReplaceDomainOwnershipCheck()
passwordResetDoesNotLogInOrDisableMfa()
verificationAndResetTokensArePurposeSeparated()
concurrentEmailVerificationIsSingleUse()
deletionBlocksSsoReProvisioningForForbiddenIdentity()
repositoryProjectionExcludesSensitiveAccountData()
```

Đây là tên ca kiểm thử minh họa, không phải bộ test tự chạy; cần triển khai dựa trên business policy thực tế.

## 15. Checklist thiết kế trước khi phát hành

1. **Vẽ ranh giới:** ai sở hữu Account aggregate/state machine, ai sở hữu security integration, ai chịu trách nhiệm nhận event và revoke.
2. **Stable identity:** dùng account ID và `(iss,sub)` đã xác minh cho external provider; email là contact, không tự là trust anchor.
3. **Chia read/write:** `UserDetailsService` đọc projection tối thiểu, `AccountUseCase` ghi và bảo toàn invariants.
4. **Password:** `PasswordEncoder` cho hash/check, policy/migration/recovery do app quy định; không lưu plaintext.
5. **States:** map cẩn thận business status sang enabled/locked/credential-expired và authorization; không gộp mọi trạng thái.
6. **Token lifecycle:** email verification, password reset, magic login, access/refresh token có purpose/TTL/verifier riêng.
7. **Authorization:** request-level, method-level và domain resource/tenant policy; không coi `hasRole` là toàn bộ kiểm soát.
8. **Sessions/token cũ:** xác định cơ chế thu hồi có hiệu lực đo được; tránh tin rằng chỉ đổi account status đã revoke hết.
9. **Database correctness:** unique constraints, row locking/optimistic concurrency, idempotency, transactions và outbox cho events.
10. **MFA/recovery:** bảo vệ việc thay yếu tố, role, email, password, account closure bằng reauthentication/step-up phù hợp.
11. **Privacy và vận hành:** retention, audit, thông báo, rate limits, user enumeration, dữ liệu nhạy cảm trong principal/logs.
12. **Kiểm thử:** wrong credentials, account states, ownership, multi-node race, cache stale, role change, incident revocation và SSO identity confusion.

## 16. Tự kiểm tra kiến thức

**Câu 1.** `UserDetailsService` có tự tạo Account, gửi email kích hoạt và xóa dữ liệu khi khách yêu cầu không?  
**Trả lời:** Không. Nó là interface truy xuất dữ liệu phục vụ authentication username/password. Quy trình account lifecycle thuộc Account Service; một implementation riêng có thể chọn kết hợp thêm việc khác nhưng sẽ tạo coupling và side effects khó kiểm soát.

**Câu 2.** Người dùng đăng ký thành công, có password hash trong DB. Vì sao vẫn bị từ chối login?  
**Trả lời:** Domain account có thể còn `PENDING_EMAIL`/`PENDING_APPROVAL`; `UserDetails` projection hoặc policy authentication phải ngăn cấp phiên đầy đủ cho đến khi các điều kiện này đạt.

**Câu 3.** Có thể cho khách gửi `roles=["ADMIN"]` tới endpoint đăng ký rồi trả `ROLE_ADMIN` trong `UserDetails`?  
**Trả lời:** Không. Role là quyền do domain approval/grant policy quyết định và được lưu trong source of truth đáng tin; input user không được tự nâng quyền.

**Câu 4.** Nếu người dùng bị admin khóa trong DB, liệu HttpSession đang có tự hết hiệu lực?  
**Trả lời:** Không mặc định. Cần invalidate/revoke hoặc kiểm tra account/session version ở các request tiếp theo.

**Câu 5.** `@PreAuthorize("hasRole('USER')")` có bảo đảm user không đọc được hóa đơn của người khác không?  
**Trả lời:** Không. Cần check owner/tenant/ACL ở business policy hoặc database query đúng scope.

**Câu 6.** Tại sao không nên viết cập nhật `lastLoginAt` trong `UserDetailsService.loadUserByUsername`?  
**Trả lời:** Lookup có thể xảy ra cả khi credential sai hoặc nhiều lần qua cache/provider. Chỉ ghi sự kiện đăng nhập thành công từ success event/handler tin cậy, với semantics rõ.

**Câu 7.** `PasswordEncoder` thuộc Spring Security. Vậy ai chịu trách nhiệm quy tắc “mật khẩu mới không trùng mật khẩu cũ”?  
**Trả lời:** Account/password use case quyết định business policy và sử dụng encoder đúng cách để kiểm tra/hashing; Spring không tự áp dụng toàn bộ luật sản phẩm.

**Câu 8.** Ứng dụng xác thực người dùng qua OIDC đã có email giống account local bị khóa. Có được tự tạo local account mới không?  
**Trả lời:** Không mặc định. Cần liên kết bằng `(iss,sub)` đã xác minh, xét lifecycle/tenant/allowlist và policy chống account takeover.

**Câu 9.** Trong một dự án nhỏ, dùng `JdbcUserDetailsManager` có sai không?  
**Trả lời:** Không. Với nhu cầu đơn giản nó có thể phù hợp. Chỉ không nên nhầm một CRUD user store cơ bản với toàn bộ nghiệp vụ onboarding, approval, recovery, deletion và audit.

**Câu 10.** Cách nhận biết ranh giới đúng khi có sự cố?  
**Trả lời:** Domain giải thích trạng thái và ai được phép thay đổi nó; Security giải thích credential/Authentication/authorization checks thực tế. Audit, metrics và tracing cần nối hai phần nhưng không lộ secrets hoặc dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, `AuthenticationManager`, `AuthenticationProvider`, authorities.
- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): interface đọc thông tin xác thực và implementations.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): sự phối hợp của `UserDetailsService` và `PasswordEncoder`.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): password hash, `DelegatingPasswordEncoder`.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và Spring AOP.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context persistence, sessions và concurrent session controls.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account states, anti-enumeration, reauthentication.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery tokens, expiry/single-use, reset flows.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): authorization per resource/tenant và nguyên tắc least privilege.
