# Khóa tạm thời, vô hiệu hóa và xóa tài khoản trong Spring Security

## 1. Mục tiêu và bối cảnh

Một người dùng nhập sai mật khẩu liên tiếp, một nhân viên nghỉ việc, một tài khoản bị nghi chiếm đoạt, hoặc người dùng yêu cầu xóa dữ liệu. Cả bốn trường hợp có thể dẫn đến **không cho tài khoản đăng nhập**, nhưng nguyên nhân, thời hạn, chính sách khôi phục và ảnh hưởng đến dữ liệu khác nhau.

Spring Security hỗ trợ kiểm tra những trạng thái cơ bản của tài khoản qua `UserDetails` như `isAccountNonLocked()` và `isEnabled()`. Tuy nhiên, framework **không tự quyết định** thế nào là “tạm khóa sau năm lần sai”, ai được vô hiệu hóa tài khoản, xóa những bảng dữ liệu nào, hay cách thu hồi mọi phiên/token đã cấp. Đó là trách nhiệm của chính sách nghiệp vụ, identity store, session/token infrastructure và quy trình bảo mật của ứng dụng.

Sau bài học, bạn cần:

1. Phân biệt **khóa tạm thời (temporary lock)**, **vô hiệu hóa (disable/suspend)**, **xóa tài khoản (delete/terminate)**, khóa credential và hết hạn credential.
2. Hiểu ánh xạ giữa lifecycle policy của ứng dụng với bốn phương thức của `UserDetails`: `isAccountNonLocked`, `isEnabled`, `isAccountNonExpired` và `isCredentialsNonExpired`.
3. Tạo một model trạng thái có thời gian khóa, lý do, người thực hiện và version; xử lý mở khóa có kiểm soát, không phụ thuộc nút “Unlock” bên frontend.
4. Tích hợp Spring Security Servlet/JDBC hoặc reactive với account-status check và **không lầm rằng đổi cờ DB sẽ tự hủy session**.
5. Thiết kế chống brute force mà không gây user enumeration hay tạo cơ chế DoS bằng account lockout.
6. Phối hợp account status với HTTP sessions, remember-me, OAuth2 access/refresh tokens, API keys, passkeys, OIDC SSO và dịch vụ phụ thuộc.
7. Thực hiện quy trình xóa **có tombstone/retention/cleanup, audit và tránh khôi phục nhầm từ backup**, thay vì chỉ gọi `repository.deleteById(...)`.
8. Viết kiểm thử về trạng thái, concurrency, phiên đã mở, cache, authorization và khôi phục.

**Baseline code:** Java 17+, Spring Boot 3.x, Spring Security 6.x (nhánh Servlet); khái niệm còn phù hợp với phiên bản mới nhưng phải đối chiếu API khi nâng cấp. Phần WebFlux dùng `ServerHttpSecurity` riêng. Không dùng bài này như tư vấn pháp lý: xóa/retention phải theo luật, hợp đồng và chính sách bảo mật áp dụng cho sản phẩm cụ thể.

## 2. Ba trạng thái dễ bị đánh đồng

| Trạng thái | Mục đích | Có thể đảo ngược? | Dữ liệu user còn? | Ai/thứ gì quyết định mở lại? |
| --- | --- | --- | --- | --- |
| **Tạm khóa** | Chặn xác thực một thời gian hoặc cho tới khi điều tra/step-up | Thường **có** | Có | Hết `lockedUntil` theo policy, hoặc quy trình unlock bảo mật |
| **Vô hiệu hóa** | Ngừng quyền sử dụng do offboarding, nghỉ việc, vi phạm chính sách, nghi compromise | Có thể có hoặc không, tùy lý do | Thường có trong giai đoạn chờ xử lý | Admin/IdP/HR/policy owner được ủy quyền |
| **Xóa tài khoản** | Chấm dứt account và xử lý dữ liệu/credential liên quan | Có thể **không thể khôi phục** sau purge | Tùy retention, tombstone, pháp lý và lịch dọn dữ liệu | Workflow deletion/retention, không phải chỉ lật cờ enabled |

**Khóa tạm thời** thường là một thuộc tính có thời hạn: ví dụ `lockUntil=2026-12-01T10:00:00Z`. Tại thời điểm nhỏ hơn mốc này, login bị chặn; sau thời điểm đó policy có thể tự coi lock đã hết hiệu lực, dù bản ghi chưa được cleanup.

**Vô hiệu hóa** thể hiện quyết định không cho account được dùng, thường không dựa vào hết `lockedUntil`. Ví dụ nhân viên rời tổ chức: dù token password còn đúng, account phải bị từ chối theo policy của tổ chức.

**Xóa** liên quan nhiều thứ hơn xác thực: nhận diện, quyền, dữ liệu do user tạo, secrets, session, audit và các quan hệ trong database. Có thể áp dụng “pending deletion” trong một thời gian, nhưng đó là **một trạng thái nghiệp vụ riêng**, không có nghĩa xóa ngay mọi byte dữ liệu. Nếu luật yêu cầu lưu giao dịch trong một thời hạn, data retention và deletion workflow phải thể hiện điều đó minh bạch.

### 2.1. Lock, disable, expire: thuật ngữ chính xác

Một tài khoản cũng có thể bị:

- **Account expired**: hợp đồng/quyền thuê bao có ngày hết hạn; thường ánh xạ `isAccountNonExpired() = false` trong DAO authentication.
- **Credentials expired**: password hoặc một credential phải được thay; thường `isCredentialsNonExpired() = false` khi provider hỗ trợ.
- **Authenticator suspended/revoked**: chỉ một phương thức (passkey, TOTP, API key) bị thu hồi; account có thể còn credential khác.
- **Administratively suspended**: có điều kiện điều tra/phê duyệt; khác với việc hệ thống tự lock do đoán mật khẩu.

Một cờ `enabled=false` duy nhất không đủ giải thích lý do, thời gian, actor, policy, điều kiện restore và hậu quả bảo mật. Nên lưu **business lifecycle state** và dẫn xuất các cờ Spring cần thiết.

## 3. Bức tranh tổng thể: tài khoản ≠ credential ≠ session ≠ token

```text
                  Account / identity record
                    stable user ID, status, version
                            |
          +-----------------+--------------------+
          |                 |                    |
   Authenticators       HTTP sessions       OAuth grants/tokens
   password, passkey,    session cookie,     access/refresh,
   OTP, security key     SecurityContext     API keys, devices
          |                 |                    |
          v                 v                    v
  Can login again?    Can use old session?  Can use old Bearer token?
          |                 |                    |
          +------- each requires policy / enforcement ----------+
```

Ba câu hỏi phải tách rõ:

1. “User không được đăng nhập mới” → kiểm tra account status tại **authentication**.
2. “User đã đăng nhập từ trước không còn truy cập được” → **invalidate sessions** và/hoặc re-check trạng thái ở mỗi request đối với use case yêu cầu mạnh.
3. “Token đã phát hành không còn gọi API được” → chính sách thu hồi tại **Authorization Server**, cache/introspection/denylist hoặc deadline tại **Resource Server**.

**Đổi `users.enabled=false` không tự hủy `HttpSession` đã tồn tại.** Khi session đã giữ một `Authentication` được tạo trước đó, các request tiếp theo có thể không chạy lại `UserDetailsService`/`DaoAuthenticationProvider`. Điều tương tự áp dụng với JWT access token được Resource Server xác minh offline: `UserDetails.isEnabled()` ở ứng dụng phát token không tự chặn JWT đã phát hành.

Lỗi thiết kế nguy hiểm là viết “đã khóa tài khoản thành công” nhưng chỉ đổi flag DB trong khi người dùng vẫn có session active, refresh token còn hợp lệ hoặc API key chưa bị disable.

## 4. Spring Security UserDetails: bốn kiểm tra quan trọng

`UserDetails` của Spring Security biểu diễn thông tin người dùng cần cho một số cơ chế xác thực, đặc biệt `DaoAuthenticationProvider` trong form/username-password login.

| `UserDetails` method | Trả `false` nghĩa là | Exception điển hình trong luồng DAO |
| --- | --- | --- |
| `isAccountNonLocked()` | Account đang bị khóa | `LockedException` |
| `isEnabled()` | Account bị vô hiệu hóa | `DisabledException` |
| `isAccountNonExpired()` | Account hết hiệu lực | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Password/credential đã hết hiệu lực | `CredentialsExpiredException` |

Trong `AbstractUserDetailsAuthenticationProvider`, các pre-authentication checks mặc định kiểm tra **locked**, **disabled** và **account expired**; post-authentication checks xử lý **credentials expired**. Do đó ngoại lệ thực tế có thể phụ thuộc trạng thái cùng lúc, thứ tự kiểm tra, việc cache user, hoặc custom provider.

Ví dụ constructor của Spring Security `User` có builder:

```java
UserDetails details = User.withUsername("alice")
        .password(passwordHash)
        .roles("USER")
        .accountLocked(accountIsLocked)
        .disabled(accountIsDisabled)
        .accountExpired(accountHasExpired)
        .credentialsExpired(credentialsHaveExpired)
        .build();
```

Đây là **đoạn code trong service** có `passwordHash`/boolean đã được lấy từ trusted repository; không phải chương trình độc lập. Các builder method nhận **“locked/disabled/expired”** theo nghĩa trực tiếp, trong khi getter `isAccountNonLocked()`, `isEnabled()` diễn đạt theo hướng phủ định hoặc tích cực. Nhầm dấu phủ định là bug phổ biến:

```java
// SAI: truyền "nonLocked" vào method đòi "accountLocked".
.accountLocked(accountNonLocked) // đảo ngược trạng thái!

// ĐÚNG: dùng trạng thái đang bị khóa.
.accountLocked(accountLocked)
```

### 4.1. Không tất cả authentication mechanisms đều đọc UserDetails

- `DaoAuthenticationProvider` dùng `UserDetailsService` và kiểm tra account flags trong flow username/password thông thường.
- Một custom `AuthenticationProvider` có thể **không** dùng các flags trừ khi bạn lập trình kiểm tra.
- OAuth2/OIDC login có thể xác thực qua IdP và tạo principal không phải `UserDetails` của local database; cần ánh xạ account nội bộ và lifecycle policy riêng.
- Resource server chỉ xác thực Bearer JWT có thể không đọc `UserDetailsService`; phải dùng token revocation/claims/account-state lookup theo kiến trúc.
- X.509 pre-authenticated, passkey, OTT, API key và custom login cũng cần xác định ở **tầng nào** policy disabled/deleted/locked được áp dụng.

Đừng gắn một `UserDetailsService` bean và kết luận mọi cơ chế đăng nhập đã chịu cùng account policy. Hãy test từng đường đăng nhập thực tế.

### 4.2. Xử lý lỗi không được tiết lộ account existence

Nội bộ có thể ghi nhận `LockedException` hoặc `DisabledException` để audit; nhưng **response công khai** cần tránh thông báo khác nhau quá rõ giữa “username không tồn tại”, “password sai”, “bị khóa” và “vô hiệu hóa”. OWASP Authentication Cheat Sheet khuyến nghị thông điệp chung để chống user enumeration, kể cả khác biệt status và thời gian phản hồi.

Ví dụ UI chung:

> Không thể đăng nhập bằng thông tin hiện tại. Nếu cần hỗ trợ, hãy dùng quy trình khôi phục tài khoản.

Khi user đã được xác minh bằng một kênh tin cậy, có thể giải thích lý do và cách xử lý chi tiết hơn ở luồng riêng. Không trả thông tin “email X thuộc tài khoản đang bị kỷ luật” cho người chỉ biết địa chỉ email đó.

## 5. Thiết kế state machine rõ ràng trước khi viết code

Một model nghiệp vụ có thể định nghĩa các trạng thái:

```text
               +------------------+
               | ACTIVE           |
               +------------------+
                     |       |
      too many wrong |       | admin/HR/risk decision
             attempts|       v
                     |   +------------------+
                     v   | DISABLED         |
           +--------------+                 |
           | TEMP_LOCKED  |                 |
           +--------------+-----------------+
             |         ^        |
     TTL done |         |        | user delete request / policy
  or approved |         |        v
        unlock|         |  +------------------+
             v          |  | PENDING_DELETION |
           ACTIVE       |  +------------------+
                        |        |
                        |        | verified purge/retention workflow
                        |        v
                        |  +------------------+
                        +--| DELETED/TOMBSTONE|
                           +------------------+
```

Sơ đồ chỉ mô tả **một lựa chọn**: tổ chức khác có thể có `SUSPENDED_REVIEW`, `LOCKED_COMPROMISE`, `DELETION_CANCELLED` hoặc `ARCHIVED`. Không bắt buộc dùng mọi trạng thái trên cùng một enum; điều quan trọng là **điều kiện chuyển** được viết rõ và không thể bypass.

Ví dụ bảng quyết định:

| Từ → Đến | Lý do | Ai có quyền | Điều kiện | Side effects bắt buộc hoặc theo policy |
| --- | --- | --- | --- | --- |
| ACTIVE → TEMP_LOCKED | Failed logins vượt ngưỡng | Risk/anti-abuse engine | Rate limiter, ngưỡng, window đã xác định | Chặn auth mới; cảnh báo khi rủi ro |
| TEMP_LOCKED → ACTIVE | Hết hạn hoặc unlock | Policy engine hoặc verified admin | Không có disable/deletion/incident hold | Reset counter theo policy, audit |
| ACTIVE → DISABLED | Offboarding/abuse/compromise | Admin/IdP/HR workflow | Phê duyệt/nguồn tin cậy | Chặn auth mới, hủy phiên/token nếu yêu cầu |
| DISABLED → ACTIVE | Reactivation | Có thẩm quyền, verification | Không phải deleted; risk review | Re-verify recovery channels/credentials, re-issue session |
| ACTIVE/DISABLED → PENDING_DELETION | User request/contract/legal | User verified hoặc privacy admin | Check retention/legal hold; idempotent | Chặn auth, revoke credentials, bắt đầu cleanup |
| PENDING_DELETION → DELETED | Retention/purge workflow | Service được ủy quyền | Không còn blocker cần giữ | Purge/anonymize, delete dependent records, audit completion |
| DELETED → ACTIVE | Không mặc định | Không cấp phép qua “unlock” đơn giản | Chỉ nếu policy có reversible tombstone rõ | Quy trình onboarding mới, không hồi sinh credentials cũ |

**Không** cho phép tạm khóa tự hết `lockedUntil` rồi vô tình mở lại một tài khoản đang `DISABLED` hoặc đang `PENDING_DELETION`. Tạm khóa và vô hiệu hóa có thể được mô hình hóa bằng hai trường độc lập, với thứ tự ưu tiên và logic tổng hợp xác định.

### 5.1. Mapping lifecycle state sang Spring UserDetails

Một lựa chọn minh bạch:

```text
accountLocked =
    currentTime < lockedUntil
    OR manualSuspensionRequiresLock

disabled =
    state in {DISABLED, PENDING_DELETION, DELETED}

UserDetails.isAccountNonLocked = !accountLocked
UserDetails.isEnabled = !disabled
```

Đây là **quy ước ứng dụng**, không phải cài đặt mặc định của Spring Security. Với account `DELETED`, service nên trả **`UsernameNotFoundException`** hoặc từ chối xác thực qua một đường fail closed tương đương thay vì tự tái tạo record bị xóa. Nếu legal hold cần giữ một record tối thiểu, phải chắc chắn record không có credential vẫn có thể được đăng nhập.

## 6. Khóa tạm thời: chống brute force nhưng không tạo DoS

### 6.1. Vấn đề

Nếu ứng dụng có password login, attacker có thể thử hàng nghìn mật khẩu. Một anti-abuse policy thường kết hợp:

- Giới hạn số lần thử theo **account identifier chuẩn hóa**.
- Giới hạn theo IP, thiết bị, ASN hoặc nhóm nguồn với cân nhắc NAT/shared IP.
- Tăng độ trễ hoặc backoff sau thất bại; ngưỡng reset theo sliding window.
- Step-up, bot detection và risk-based controls khi hoạt động bất thường.
- Tạm khóa một authenticator hoặc account trong khoảng thời gian rõ ràng.
- Logging, alerting và abuse metrics không chứa password/token.

**Không lấy “5 lần sai → khóa vĩnh viễn” làm chính sách mặc định cho mọi sản phẩm.** Kẻ tấn công có thể cố tình nhập sai mật khẩu cho những username biết trước và gây **account-lockout denial of service**. OWASP khuyến nghị cân nhắc lockout threshold, observation window, lock duration và rủi ro DoS. NIST SP 800-63B-4 đặt giới hạn trên cho số failed attempts ở một số authenticator để bảo vệ chống đoán mật khẩu, nhưng không biến con số đó thành một cấu hình tối ưu cố định cho mọi ứng dụng.

### 6.2. Thời gian và reset policy

Định nghĩa rõ:

- `failedAttemptWindow`: ví dụ 15 phút qua rolling window.
- `threshold`: số thất bại cho một identity/credential trước khi áp biện pháp.
- `lockedUntil`: Instant UTC; thời điểm hết hạn kiểm tra tại authentication.
- `maxLockDuration` và backoff/cooldown để tránh lock không giới hạn.
- `resetOnSuccess`: chỉ reset bộ đếm của authenticator/phương thức đã được xác thực thành công theo policy.
- `manualUnlock`: chỉ cho actor được ủy quyền; có lý do, ticket và audit.
- **Không** reset `DISABLED` hoặc `PENDING_DELETION` chỉ vì một lần login thành công bằng credential khác.

Mỗi cách unlock cần được test với đồng hồ giả lập (`Clock.fixed`), nhiều node và request đồng thời. Nếu dùng Redis TTL cho lock, phải lưu state/ban policy rõ: mất key do eviction không nên làm mất một suspension có tính bảo mật quan trọng.

### 6.3. Đếm thất bại ở đúng điểm

Khi dùng Spring Security form login, `AuthenticationFailureHandler` và authentication events có thể cung cấp tín hiệu thất bại. Nhưng **không nên tăng failed password counter cho mọi failure**: locked/disabled, network error, bad CSRF, missing second factor hoặc integration error có ý nghĩa khác. Đếm vào một store shared và normalize username để tránh case/confusable/canonicalization.

Ví dụ logic **minh họa** trong failure handler:

```java
// Trích đoạn Servlet - không phải file runnable độc lập.
AuthenticationFailureHandler delegate =
        new SimpleUrlAuthenticationFailureHandler("/login?error");

AuthenticationFailureHandler monitored = (request, response, ex) -> {
    if (ex instanceof BadCredentialsException) {
        String suppliedUsername = request.getParameter("username");
        // attempts.recordFailure(...) phải normalize, rate-limit,
        // dùng shared/atomic store và xử lý tài khoản không tồn tại
        // theo policy chống user enumeration.
        attempts.recordFailure(suppliedUsername, request.getRemoteAddr());
    }
    delegate.onAuthenticationFailure(request, response, ex);
};
```

`attempts` là abstraction nghiệp vụ chưa được định nghĩa trong snippet. Một implementation production cần chống spoofed `X-Forwarded-For`: chỉ tin header từ proxy đã kiểm soát; cũng tránh để attacker biến một chuỗi cực dài/khác biệt Unicode thành hàng triệu keys. Các lỗi do external IdP không nên bị đếm như sai password local.

### 6.4. Transaction và concurrency

Hai request login sai có thể đến cùng lúc. Một flow `SELECT failed_count; failed_count++; UPDATE` không dùng transaction/conditional update có thể mất lượt đếm. Dùng atomic increment/transaction, so sliding window, và nếu lock đã có thì không để một callback thành công cũ xóa lock mới hơn. Một bản ghi lock nên có `version` hoặc transition event id.

## 7. Vô hiệu hóa: offboarding, suspended review, bảo mật

### 7.1. Vì sao không chỉ đặt password thành ngẫu nhiên?

Nếu chỉ đổi password hoặc xóa passwordHash, các phương thức khác có thể vẫn hoạt động: passkeys, OIDC SSO, remembered sessions, client certificate, OAuth refresh token hoặc API key. Vô hiệu hóa account cần policy chung **tại mọi auth path**.

Ví dụ nhân viên rời công ty:

```text
HR/IdP event (source verified)
  -> account status = DISABLED (persisted/versioned)
  -> block new authentication across methods
  -> terminate active sessions and refresh grants
  -> remove privileged roles/API keys/credentials as policy
  -> notify dependent services; reconcile asynchronously
  -> audit, monitor propagation; retain required records
```

Nếu người dùng được đánh dấu disabled ở identity provider nhưng local ứng dụng cache `OidcUser` và session vẫn còn, phải có cơ chế đồng bộ trạng thái hoặc terminate session/refresh. Nếu account đã được cấp quyền trong token JWT, Resource Server không mặc định quay lại local account DB để xem `enabled`. Phải nêu rõ độ trễ hiệu lực theo từng hop.

### 7.2. Temporary disable khác permanent disable

Một số sản phẩm dùng `SUSPENDED_REVIEW` với kỳ hạn/điều kiện rõ cho điều tra; số khác dùng `DISABLED` cho offboarding hoặc hành vi vi phạm. Tách `reasonCode`, `caseId`, `effectiveAt`, `actorId` và `reactivationPolicy`. Không đặt khóa hết hạn tự động cho một disable được lệnh pháp lý/tổ chức yêu cầu kéo dài.

### 7.3. Không cho “self-service reenable” dưới quyền chưa đủ

Người dùng đã disabled không nên có endpoint `POST /enable-me` mở lại chỉ với username/email/OTP rời rạc. Admin reactivation phải dùng vai trò riêng, xác minh từ nguồn quyết định ban đầu (HR/IdP/anti-fraud) và có audit. Trong trường hợp account bị nghi chiếm, re-enable nên yêu cầu reset/re-bind credential đáng tin và revoke những session/token nghi vấn trước khi cho truy cập tiếp.

## 8. Xóa tài khoản: state transition cộng với data lifecycle

### 8.1. Xóa logical account không giống purge toàn bộ dữ liệu

Một lệnh `repository.deleteById(id)` chỉ làm một thao tác lên một bảng/entity. Tài khoản còn có thể xuất hiện trong:

- Authenticator bindings: password hash, passkey credential ID/public key, TOTP secret, recovery codes.
- HTTP sessions, remember-me persistent tokens, refresh/access token grant records.
- Profile, contacts, preferences, address, uploaded files, private messages.
- Order/payment invoices, shipment/tax records, subscriptions, support tickets.
- Authorization roles, organization memberships, admin grants, API keys, webhooks.
- Search indexes, Redis caches, analytics exports, data warehouse, object storage, CDN.
- Logs, backups/snapshots và hàng đợi async jobs.
- Other identity providers, directory/SCIM, partner systems.

Không phải tất cả dữ liệu đều được phép hoặc cần xóa ngay: tài liệu kế toán, giao dịch có thể thuộc nghĩa vụ retention riêng. Cần phân loại **xóa**, **ẩn danh hóa**, **pseudonymize**, **retention with legal basis**, **deny access**, và **backup expiry**. Đừng hứa “xóa vĩnh viễn khỏi mọi backup ngay lập tức” nếu công nghệ và retention policy chưa bảo đảm.

### 8.2. Vòng đời deletion đề xuất

```text
ACTIVE / DISABLED
        |
        | authenticated delete request or verified admin/contract trigger
        v
PENDING_DELETION
        |  block login / reissue, revoke sessions/tokens
        |  check ownership, retention & legal holds
        |  freeze or anonymize sensitive relationships as policy
        v
DELETION_IN_PROGRESS
        |  durable workflow jobs across services
        |  idempotent cleanup, retry, evidence & reconciliation
        v
DELETED / PURGED
        |  minimal tombstone/audit retained only if justified
        |  ensure old account IDs/credentials never revive
        v
Complete / notify
```

Có thể có **cancellation window** nếu luật/sản phẩm cho phép, nhưng việc hoãn purge không được đồng nghĩa user vẫn có quyền truy cập bình thường. Để hủy deletion, cần xác minh đúng account owner và policy; đừng chỉ nhận một email link cũ hoặc accountId từ query.

### 8.3. Tombstone và chống tái sử dụng định danh

Một tombstone có thể giữ tối thiểu `accountId`, trạng thái đã xóa, thời điểm, lý do dạng mã và version để ngăn stale event/backup re-import tự tái kích hoạt account. **Không** giữ email/hash/token thô trong tombstone nếu không có mục đích/hạn lưu hợp pháp.

Nếu username/email có thể được tạo lại, đừng dùng email làm khóa phân biệt chính của owner trong lịch sử giao dịch hoặc authorization; stable, không tái sử dụng `accountId` tránh link dữ liệu cũ sang user mới. Nếu có username reuse, phải kiểm tra cách mapping từ JWT `sub`, SCIM ID, Kafka event và audit.

### 8.4. Soft delete và hard delete

| Kỹ thuật | Lợi ích | Rủi ro |
| --- | --- | --- |
| `deletedAt` / soft delete | Có thể support grace period và restore có kiểm soát | Truy vấn quên lọc deleted dẫn tới lộ dữ liệu/restore nhầm |
| Tombstone tối thiểu | Chống stale re-create; giữ bằng chứng xử lý | Có thể bị giữ quá nhiều PII nếu không thiết kế |
| Hard delete / purge | Loại record/credential vật lý sau khi được phép | Mất quan hệ dữ liệu, lỗi foreign key, mất bằng chứng cần retention |
| Pseudonymize/anonymize | Giữ aggregate/legal records khi phù hợp | Pseudonymize chưa chắc thoát phạm vi PII; có thể re-identify |
| Crypto-erasure | Hủy key mã hóa dữ liệu khi mô hình hỗ trợ | Chỉ có tác dụng nếu toàn bộ bản sao chịu cùng key và không tồn tại bản plaintext |

Tùy product, **hard delete** có thể là bước cuối của workflow sau khi chặn auth ngay từ đầu, thay vì làm trước rồi mới gửi yêu cầu tới các dịch vụ phụ thuộc.

## 9. Mẫu database schema cho lifecycle

Để hỗ trợ tính rõ ràng, dùng stable ID, enum/status, lock timestamp, actor, reason, version và delete timestamp:

```sql
-- PostgreSQL example: schema do ứng dụng quản lý, KHÔNG phải DDL Spring Security.
CREATE TABLE app_accounts (
    id UUID PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    lifecycle_state VARCHAR(32) NOT NULL,
    locked_until TIMESTAMPTZ,
    failed_attempts INT NOT NULL DEFAULT 0,
    status_version BIGINT NOT NULL DEFAULT 0,
    last_status_reason VARCHAR(64),
    last_status_actor UUID,
    disabled_at TIMESTAMPTZ,
    deletion_requested_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);
```

Schema này **chỉ minh họa**, không bao gồm các bảng session, roles, passkey, token, contact data, audit và retention policy. Trường `password_hash` chỉ dùng cho password auth; passkey-only users không cần giả vờ có password hợp lệ.

### 9.1. Conditional update tránh ghi đè trạng thái mới

Giả sử admin đọc account version 7 rồi định enable. Trong khi đó risk engine đã disable vì compromise ở version 8. Nếu admin ghi đè không kiểm tra version, tài khoản có thể bị mở lại sai.

```sql
-- Minh họa optimistic concurrency ở PostgreSQL.
UPDATE app_accounts
SET lifecycle_state = 'DISABLED',
    last_status_reason = 'OFFBOARDING',
    status_version = status_version + 1,
    disabled_at = CURRENT_TIMESTAMP
WHERE id = :account_id
  AND status_version = :expected_version
  AND lifecycle_state = 'ACTIVE'
RETURNING id, status_version;
```

Chỉ khi có **đúng một row** cập nhật, transition mới thành công. Zero rows nghĩa là state/version không còn đúng hoặc account không tồn tại: phải đọc lại và áp decision theo chính sách mới, không retry blind thành công. JPA có thể dùng `@Version` cho optimistic locking; nhưng side effects session/token vẫn cần durable events/outbox để không bị bỏ sót.

### 9.2. Khóa tạm thời dùng thời gian server

```sql
-- PostgreSQL sketch: locked_until theo Instant UTC.
UPDATE app_accounts
SET locked_until = GREATEST(
        COALESCE(locked_until, CURRENT_TIMESTAMP),
        CURRENT_TIMESTAMP + INTERVAL '10 minutes'),
    status_version = status_version + 1
WHERE id = :account_id
  AND lifecycle_state = 'ACTIVE';
```

Đây không phải logic đầy đủ để tính failed attempts; là ví dụ tránh một request lock ngắn hơn ghi đè lock dài hơn. Trong triển khai thật, observation window, threshold và backoff cần chung transaction/atomic store. Không lấy thời gian từ trình duyệt hoặc tin giá trị `unlockAt` do client gửi.

## 10. Demo Spring Boot Servlet: mapping trạng thái vào UserDetails

Demo Java 17 sau đây tập trung vào **authentication state**, cố ý **không** có public HTTP endpoint để khóa/xóa account. Nó dùng memory store cho một instance và một user demo; **không phải** hệ thống sản xuất và không thực hiện purge dữ liệu/session revocation.

### 10.1. Gradle dependencies

Dùng một project Spring Boot 3.x Java 17 có Spring Boot Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 10.2. Code đầy đủ

Lưu file `src/main/java/demo/lifecycle/AccountLifecycleApplication.java`:

```java
package demo.lifecycle;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccountLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccountLifecycleApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        return new AccountStore(encoder, Clock.systemUTC());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Open /private and sign in as alice.";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello, " + authentication.getName();
        }
    }

    record Account(String username, String hash, boolean disabled,
                   boolean deleted, Instant lockedUntil) {

        Account withLockUntil(Instant until) {
            return new Account(username, hash, disabled, deleted, until);
        }

        Account withDisabled(boolean value) {
            return new Account(username, hash, value, deleted, lockedUntil);
        }

        Account asDeletedTombstone() {
            // Demo logical tombstone; production needs real data deletion.
            return new Account(username, "unusable", true, true, null);
        }
    }

    static final class AccountStore implements UserDetailsService {
        private final Map<String, Account> accounts =
                new ConcurrentHashMap<>();
        private final Clock clock;

        AccountStore(PasswordEncoder encoder, Clock clock) {
            this.clock = clock;
            accounts.put("alice", new Account(
                    "alice", encoder.encode("local-demo-only"),
                    false, false, null));
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            Account account = accounts.get(username);
            if (account == null || account.deleted()) {
                throw new UsernameNotFoundException("Account unavailable");
            }

            boolean locked = account.lockedUntil() != null
                    && clock.instant().isBefore(account.lockedUntil());

            return User.withUsername(account.username())
                    .password(account.hash())
                    .roles("USER")
                    .accountLocked(locked)
                    .disabled(account.disabled())
                    .build();
        }

        // Nội bộ demo: KHÔNG expose trực tiếp thành public controller.
        void lockFor(String username, Duration duration) {
            if (duration.isNegative() || duration.isZero()) {
                throw new IllegalArgumentException("duration");
            }
            Instant until = clock.instant().plus(duration);
            accounts.computeIfPresent(username,
                    (key, old) -> old.deleted()
                            ? old : old.withLockUntil(until));
        }

        void disable(String username) {
            accounts.computeIfPresent(username,
                    (key, old) -> old.deleted()
                            ? old : old.withDisabled(true));
        }

        void markDeleted(String username) {
            accounts.computeIfPresent(username,
                    (key, old) -> old.asDeletedTombstone());
        }
    }
}
```

Giải thích:

- `AccountStore` là `UserDetailsService` được đăng ký thành Spring bean. Mỗi login username/password qua DAO authentication sẽ đọc account và trả flags dựa trên trạng thái hiện tại.
- `.accountLocked(locked)` nhận boolean “đang khóa”; `UserDetails.isAccountNonLocked()` sẽ là phủ định.
- `.disabled(account.disabled())` ngăn login mới khi account bị vô hiệu hóa.
- `deleted=true` → `UsernameNotFoundException`; không có đường tự kích hoạt lại trong class.
- `Clock` được inject cho phép unit test không ngủ chờ. `Instant` tránh lỗi timezone và so sánh tại đúng thời điểm.
- `ConcurrentHashMap.computeIfPresent` giúp update một entry trong **một process** có tính atomic giữa threads demo; **không** là distributed transaction giữa nhiều nodes.
- `BCryptPasswordEncoder` chỉ phục vụ password demo; không in/sao chép mật khẩu thật hoặc password hash ra response.
- `markDeleted` cố ý là **tombstone demo, không phải delete dữ liệu theo pháp luật**. Nó không xóa profile, credential, audit hoặc session.
- Không có logic đếm failed login trong demo. Anti-abuse engine và persistence production phải được thiết kế riêng như mục 6, tránh đưa “unlock/admin” thiếu bảo vệ lên Internet.

### 10.3. Chạy demo

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Mở `http://localhost:8080/private`. Với account mặc định `alice` và mật khẩu local `local-demo-only`, khi đăng nhập thành công body:

```text
Hello, alice
```

Tuy nhiên **đăng nhập form thành công ở demo không đồng nghĩa trạng thái future session sẽ tự bị thu hồi** khi code nội bộ gọi `disable(...)`. Để minh họa lock/disable/delete, dùng unit test của mục 11 thay vì tự thêm unprotected admin controller.

## 11. JUnit kiểm tra lock, disabled và logical delete

Trong project demo mục 10, thêm file `src/test/java/demo/lifecycle/AccountStoreTest.java`:

```java
package demo.lifecycle;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class AccountStoreTest {

    private final Clock fixedTime = Clock.fixed(
            Instant.parse("2026-01-01T10:00:00Z"), ZoneOffset.UTC);

    @Test
    void lockBlocksNewAuthentication() {
        var store = new AccountLifecycleApplication.AccountStore(
                new BCryptPasswordEncoder(), fixedTime);

        assertTrue(store.loadUserByUsername("alice")
                .isAccountNonLocked());

        store.lockFor("alice", Duration.ofMinutes(10));

        assertFalse(store.loadUserByUsername("alice")
                .isAccountNonLocked());
    }

    @Test
    void disableBlocksEvenWithoutTemporaryLock() {
        var store = new AccountLifecycleApplication.AccountStore(
                new BCryptPasswordEncoder(), fixedTime);

        store.disable("alice");

        assertFalse(store.loadUserByUsername("alice").isEnabled());
    }

    @Test
    void deletedAccountIsNotReturnedAsLoginPrincipal() {
        var store = new AccountLifecycleApplication.AccountStore(
                new BCryptPasswordEncoder(), fixedTime);

        store.markDeleted("alice");

        assertThrows(UsernameNotFoundException.class,
                () -> store.loadUserByUsername("alice"));
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.lifecycle.AccountStoreTest
```

Kỳ vọng ba test **PASS** với dependency/JDK phù hợp. Chúng chỉ kiểm tra mapping từ trạng thái demo sang `UserDetails`; **không chứng minh** distributed persistence, session invalidation, OAuth token revocation hoặc xóa dữ liệu thật.

Để test đúng ngưỡng hết khóa, có thể inject một `Clock` giả lập điều chỉnh được rồi chuyển từ `t0` sang `t0+11 phút`, assert `isAccountNonLocked()=true`, trong khi `isEnabled()` phải vẫn phụ thuộc trạng thái disabled. Tránh `Thread.sleep` vì làm test chậm và dễ flaky.

## 12. Khóa/vô hiệu hóa có tác động thế nào lên session đã đăng nhập?

### 12.1. Vì sao chỉ kiểm tra UserDetails lúc login là chưa đủ?

Spring Security Servlet dùng `SecurityContextRepository` để phục hồi `Authentication` từ HTTP session sau khi người dùng đăng nhập. Nếu bạn disable account sau khi session được cấp, các request tiếp theo **không mặc nhiên gọi lại `DaoAuthenticationProvider`**. Điều kiện `isEnabled()` được kiểm tra lúc xác thực không có nghĩa account sẽ được revalidated tự động ở mỗi request.

```text
t0: alice login -> Authentication valid -> HttpSession S1
t1: admin disables alice in DB
t2: alice sends S1 cookie -> RP may still restore SecurityContext
                             -> request may continue unless session
                                invalidated/rechecked by app policy
```

### 12.2. Hủy phiên trên server

Có nhiều chiến lược:

1. **Invalidate active sessions** bằng Spring Session/shared store khi disabled/deleted/incident xảy ra.
2. **Session registry** khi dùng tính năng concurrent session management; chỉ `expireNow()` trên registry có thể đánh dấu session expired để filter xử lý ở request tiếp theo, không mặc nhiên xóa mọi record ở Redis tức thì.
3. **Version/recheck account status** tại những endpoint nhạy cảm hoặc request interceptor, ví dụ compare `account.statusVersion` với `session.authVersion`; fail closed nếu mismatch.
4. **Short session lifetime** giảm cửa sổ tồn tại nhưng không thay thế hoạt động thu hồi tức thời nếu chính sách yêu cầu.

Với Spring Session `FindByIndexNameSessionRepository`, có thể tra sessions theo principal rồi xóa:

```java
// Trích đoạn trong service backend, không phải controller public.
// Dùng Spring Session package org.springframework.session.*
Map<String, ? extends Session> sessions =
        indexedRepository.findByPrincipalName(principalName);

for (String sessionId : sessions.keySet()) {
    indexedRepository.deleteById(sessionId);
}
```

Đây là snippet minh họa, cần repository đúng generic type và dependency Spring Session phù hợp. Quan trọng: **principal-name index phải được populate đúng**; Spring Session không tự hiểu mọi cách authentication của ứng dụng. Nếu không có index hoặc có session ở nhiều namespace, kết quả có thể thiếu. Dùng stable internal identity/session index phù hợp tenant, không chỉ email dễ thay đổi. Trong production, cân nhắc pagination/scale, race giữa login mới và deletion, và kiểm thử session đã cấp ngay trước status transition.

### 12.3. Quy tắc thứ tự

Với disable/delete do security incident:

```text
Persist state: DENY NEW LOGIN FIRST
   |
   v
Invalidate / revoke sessions and credentials
   |
   v
Notify other services, reconcile pending tasks
   |
   v
Confirm effective access termination
```

Nếu workflow hủy session trước rồi mới lưu `disabled=true`, một request login mới có thể chen vào khoảng trống và tạo phiên mới. Cần state transition có tính durable trước, sau đó session revocation; đối với yêu cầu gần real-time hãy re-check status/version trên critical requests.

## 13. Token và các đường xác thực khác phải được đóng riêng

### 13.1. Remember-me

`PersistentTokenBasedRememberMeServices` có thể cho phép khôi phục authentication từ persistent token nếu credential/record còn. Nếu disable/delete account, phải xóa/thu hồi remember-me tokens và đảm bảo provider kiểm tra account status khi phục hồi. Việc xóa phiên đăng nhập hiện tại không đủ nếu remember-me còn.

### 13.2. OAuth2/OIDC access & refresh tokens

- **OAuth refresh token:** nếu còn hiệu lực, client có thể xin access token mới. Phải revoke grant/refresh token tại Authorization Server hoặc chặn token issuance theo account status.
- **Opaque access token/introspection:** Resource Server có thể gọi AS để biết token còn active hay không; thời điểm thu hồi phản ánh phụ thuộc AS và cache/TTL.
- **JWT access token tự chứa:** RS có thể chỉ kiểm tra chữ ký, issuer, audience, expiry offline. Đổi state user ở DB **không tự vô hiệu JWT đã phát hành**; nếu cần khóa ngay, dùng denylist, token version/security stamp, AS event, introspection hoặc deadline ngắn theo thiết kế.
- **OIDC SSO session tại IdP:** local app disabled không đồng nghĩa IdP session bị hủy; cần IdP account lifecycle/SCIM/offboarding và logout/revocation integration thích hợp.

### 13.3. API keys, service accounts và client credentials

Có thể có API keys hoặc service-to-service access không gắn với HTTP session người dùng. Hãy kiểm tra ai thực sự là owner và permission namespace của key. Disable human account không nhất thiết phải xóa service account còn thuộc một tổ chức, nhưng phải hủy delegation/quyền do cá nhân đó kiểm soát theo chính sách.

### 13.4. Passkeys, TOTP và các phương thức đăng nhập

Khi account bị disable hoặc đang pending deletion, bất kỳ đường đăng nhập nào bằng passkey/TOTP/password/OTT/OIDC cũng phải chịu **chung account policy**. Xóa passwordHash không đủ vì một passkey còn bind vẫn có thể sinh WebAuthn assertion hợp lệ. Account-status enforcement phải nằm ở trust boundary được gọi bởi từng authentication mechanism.

Khi **xóa account**, phải xóa hoặc revoke WebAuthn credential bindings, recovery codes, authenticator records và tránh việc “passkey còn trên thiết bị” có thể tạo lại binding mà không qua registration mới. Dữ liệu giữ lại để legal/audit không được biến thành principal có quyền đăng nhập.

## 14. WebFlux / Reactive Security: khác biệt cần biết

Với Spring WebFlux, dùng `ReactiveUserDetailsService` và `ServerHttpSecurity` thay vì `UserDetailsService` blocking trong event loop và `HttpSecurity` Servlet:

```java
// Trích đoạn @Configuration trong dự án Spring Boot WebFlux.
@Bean
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Reactive repository:

```java
// Trích đoạn với ReactiveAccountRepository tự định nghĩa.
@Bean
ReactiveUserDetailsService reactiveUsers(
        ReactiveAccountRepository repository) {
    return username -> repository.findByUsername(username)
            .filter(account -> !account.deleted())
            .map(account -> User.withUsername(account.username())
                    .password(account.passwordHash())
                    .roles("USER")
                    .accountLocked(account.isLockedNow())
                    .disabled(account.disabled())
                    .build());
}
```

`ReactiveAccountRepository` và `account.isLockedNow()` là **application abstractions**, không phải Spring Security API có sẵn; snippet không compile độc lập nếu chưa định nghĩa. Ở WebFlux, dùng `ReactiveSecurityContextHolder`/Reactor Context để truy cập principal; không phụ thuộc `SecurityContextHolder` thread-local kiểu Servlet.

Quan trọng: reactive repository phải thực sự non-blocking (ví dụ R2DBC/Reactive Redis) hoặc cô lập blocking call trên scheduler phù hợp; `Mono.just(jdbcCall())` vẫn chạy JDBC blocking trước khi tạo publisher. State transition/session invalidation phải phối hợp `WebSession`/Spring Session reactive và tokens theo kiến trúc, không chỉ gọi một bean `UserDetailsService`.

## 15. Admin API và self-service: kiểm tra quyền chặt chẽ

### 15.1. Tại sao `hasRole("ADMIN")` chưa đủ?

Khi khóa/xóa tài khoản, ngoài role còn cần:

- **Scope**: admin tổ chức A không khóa được tài khoản tổ chức B.
- **Object ownership**: self-service xóa chỉ tác động đúng tài khoản đang đăng nhập, không tin `userId` trong body.
- **Separation of duties**: khóa admin cấp cao hoặc legal-hold có thể đòi hai người phê duyệt.
- **Recent reauthentication/step-up**: không cho phiên lâu ngày hoặc cookie bị đánh cắp xóa hàng loạt account.
- **CSRF protection**: thao tác thay đổi qua cookie-authenticated browser phải dùng POST/PATCH/DELETE + CSRF theo cấu hình.
- **Audit**: actor, target, reason, ticket/case, status version và nguồn lệnh.
- **Rate limiting** và replay/idempotency: không cho một request lỗi được gửi lặp vô hạn tạo side effect ngoài dự kiến.

Ví dụ DSL chỉ là **lớp chặn ngoài**, không thay thế kiểm tra target-level permission trong service:

```java
// Trích đoạn trong HttpSecurity configuration của Servlet app.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/admin/accounts/*/disable")
        .hasAuthority("ACCOUNT_DISABLE")
        .requestMatchers(HttpMethod.POST, "/admin/accounts/*/unlock")
        .hasAuthority("ACCOUNT_UNLOCK")
        .anyRequest().authenticated());
```

Đừng dùng `permitAll()` cho endpoint unlock/reset/delete vì “khách hàng bị khóa không thể đăng nhập”. Account recovery cần **một flow riêng**, token/session scope hẹp, xác minh identity theo mức assurance yêu cầu và kiểm tra lại trước khi re-enable.

### 15.2. Không xóa bằng GET

`GET /accounts/delete?id=123` là nguy hiểm vì browser prefetch, crawler, hyperlink, CSRF và caching. Dùng thao tác thay đổi có method phù hợp, CSRF khi cookie-based session, confirmation và step-up; backend không được dựa vào JavaScript confirm đơn thuần.

### 15.3. HTTP API idempotency và status

Một API disable có thể trả thành công nếu account đã disabled đúng trạng thái, nhưng không được âm thầm biến **DELETED** thành **DISABLED** hoặc tạo lại user. Dùng conditional update; nếu state/version lệch thì trả 409 Conflict hoặc lỗi nghiệp vụ được chuẩn hóa. Đối với delete async có thể dùng HTTP 202 Accepted khi workflow đã được ghi nhận bền vững và trả operation ID; không trả “deleted everywhere” khi job mới nằm trong queue.

## 16. Khôi phục: unlock khác reactivation và deletion cancellation

### 16.1. Unlock sau temporary lock

Nếu lock do failed password attempts và hết hạn, hệ thống có thể tự mở với đúng `lockedUntil` đã lưu; không cần phải xóa toàn bộ profile hoặc passwordHash. Nhưng nếu phát hiện credential compromise, chỉ hết thời gian không đủ: cần đổi/thu hồi authenticator, có step-up và risk review.

### 16.2. Reactivate sau disable

Reactivation sau offboarding hoặc chính sách tổ chức cần xác minh **nguồn có thẩm quyền** cho trạng thái mới, có thể re-provision roles, xác minh email/phone đã đổi, reset credentials hoặc enroll MFA/passkey mới. Không phục hồi tất cả roles/admin grants cũ mặc định.

Nếu disable do suspected takeover, trước khi mở lại phải revoke phiên cũ, rotate recovery secrets, kiểm tra hoạt động đáng ngờ và yêu cầu xác thực người dùng theo quy trình đáng tin. Một email link gửi tới email bị attacker kiểm soát có thể là đường yếu hơn.

### 16.3. Hủy deletion khi còn grace period

Nếu có khoảng chờ trước purge, cancellation phải có policy, xác minh owner và audit; không dùng token cũ trong email không giới hạn thời gian. Sau hard purge, account có thể không khôi phục được; nếu cần tạo user mới, đó là **new onboarding** với accountId mới và không được tự gắn dữ liệu/quyền của user đã xóa.

### 16.4. Đừng nhầm khôi phục account với password reset

Một password reset chỉ đổi credential. Nó không tự mở account disabled vì pháp lý/offboarding, cũng không tự xóa incident hold. Các bước recovery cần đi qua state transition policy, chứ không ghi `enabled=true` ở mọi code path gọi “forgot password”.

## 17. Bài tập Java 17 độc lập: state machine khóa, disable, xóa

Ví dụ sau không phụ thuộc Spring, database hay server; nó mô phỏng logic **khác nhau** của ba trạng thái. Bảo đảm được mô hình hóa bằng `Clock` cố định để stdout tái lập chính xác. Lưu `AccountLifecycleModel.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class AccountLifecycleModel {
    enum State { ACTIVE, DISABLED, PENDING_DELETION, DELETED }

    static final class Account {
        private State state = State.ACTIVE;
        private Instant lockedUntil;

        boolean mayLoginAt(Instant now) {
            boolean locked = lockedUntil != null
                    && now.isBefore(lockedUntil);
            return state == State.ACTIVE && !locked;
        }

        void lockFor(Instant now, Duration period) {
            if (state != State.ACTIVE || period.isNegative()
                    || period.isZero()) {
                throw new IllegalStateException("Cannot lock");
            }
            lockedUntil = now.plus(period);
        }

        void disable() {
            if (state == State.DELETED) {
                throw new IllegalStateException("Deleted");
            }
            state = State.DISABLED;
        }

        void requestDeletion() {
            if (state == State.DELETED) {
                return;  // idempotent
            }
            state = State.PENDING_DELETION;
        }

        void completeDeletion() {
            if (state != State.PENDING_DELETION) {
                throw new IllegalStateException("Not pending");
            }
            state = State.DELETED;
            lockedUntil = null;
        }
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-01-01T10:00:00Z");
        Account alice = new Account();

        System.out.println("active: " + alice.mayLoginAt(t0));

        alice.lockFor(t0, Duration.ofMinutes(10));
        System.out.println("during lock: " + alice.mayLoginAt(
                t0.plusSeconds(300)));
        System.out.println("lock expired: " + alice.mayLoginAt(
                t0.plusSeconds(600)));

        alice.disable();
        System.out.println("disabled: " + alice.mayLoginAt(
                t0.plusSeconds(601)));

        alice.requestDeletion();
        System.out.println("pending deletion: " + alice.mayLoginAt(
                t0.plusSeconds(602)));

        alice.completeDeletion();
        System.out.println("deleted: " + alice.mayLoginAt(
                t0.plusSeconds(603)));
    }
}
```

Chạy JDK 17+:

```bash
javac AccountLifecycleModel.java
java AccountLifecycleModel
```

Stdout chính xác:

```text
active: true
during lock: false
lock expired: true
disabled: false
pending deletion: false
deleted: false
```

Bài tập làm rõ: khóa tự hết hạn, nhưng **disabled/pending deletion/deleted không tự mở** khi thời gian trôi đi. Model không có HTTP session, OAuth tokens, transaction, legal retention hoặc kiểm tra admin quyền — chúng được giải quyết ở các lớp riêng.

## 18. Đồng bộ, race condition và outbox cho hệ thống nhiều dịch vụ

Một lifecycle change thường có nhiều side effects: DB state, Redis sessions, Authorization Server grants, file deletion jobs, search indexes và thông báo. Không thể giả định tất cả service cùng tham gia một database transaction.

### 18.1. Transactional outbox

Workflow đáng tin có thể:

1. Trong **một DB transaction**, update account state/version và ghi sự kiện outbox `ACCOUNT_DISABLED` hoặc `ACCOUNT_DELETION_REQUESTED` với event ID.
2. Publisher phát outbox event tới các consumer theo ít nhất một lần.
3. Consumer invalidate sessions/revoke token/xóa dữ liệu; xử lý **idempotently** theo event ID và target version.
4. Reconciler quét các job chưa hoàn thành, retry/backoff, báo lỗi và không đánh dấu “completed” khi còn steps quan trọng fail.
5. UI/admin thấy trạng thái **pending/in progress/partial failure** thay vì một “success” giả.

### 18.2. Stale event không được mở lại account

Ví dụ event `ACCOUNT_ENABLED(version=3)` đến sau `ACCOUNT_DISABLED(version=4)`. Consumer phải so version để không re-enable account. Event sequencing một partition không thay thế điều kiện version khi có nhiều nguồn/consumer.

### 18.3. Restore từ backup

Backup của ngày trước có thể chứa account `ACTIVE` dù hôm nay đã `DELETED`. Sau restore, phải replay deletion/disable ledger hoặc có tombstones/decision authority ngăn khôi phục credential/PII cũ. Test restore và migration, không chỉ test normal delete.

### 18.4. Cache consistency

Nếu mỗi authentication node cache `UserDetails` hoặc mapping account status, disable ở node A có thể chưa có hiệu lực ở node B. Chỉ TTL không đủ cho yêu cầu “disable ngay”. Cần cache invalidation/event hoặc trạng thái phiên bản kiểm tra ở critical actions. Khi không truy cập được source of truth trong tình huống rủi ro cao, áp **fail closed** thay vì mặc định enabled.

## 19. Bảo mật vận hành và audit

Một audit event thay đổi lifecycle nên chứa:

| Thuộc tính | Ví dụ / mục đích |
| --- | --- |
| `accountId`, `tenantId` | Stable target, tránh nhầm email/trùng tên |
| `actorId`, `actorType` | Admin, HR integration, user self-service, risk engine |
| `fromState`, `toState` | Transition có thể kiểm toán |
| `reasonCode`, `caseId` | Business reason đã chuẩn hóa, ticket nếu có |
| `occurredAt`, `effectiveAt` | Thời gian yêu cầu và thời điểm hiệu lực |
| `version`, `eventId` | Chống stale write/event, idempotency |
| `sessionRevocation`, `tokenRevocation` | Số lượng, trạng thái/độ trễ, lỗi còn lại |
| `deletionJobId`, `retentionPolicy` | Phân biệt pending deletion và hoàn thành |
| `result` | Applied, rejected, partial, retrying; không giả định tất cả thành công |

Không log password, raw access/refresh tokens, session cookies, recovery codes hoặc personal data không cần thiết. Tài khoản đã xóa có thể còn audit metadata tối thiểu theo retention hợp pháp; kiểm soát quyền truy cập và thời gian lưu audit.

Khi admin khóa/xóa user, gửi thông báo đến kênh đã xác minh trước theo chính sách. Với abuse/legal investigation, có thể có hạn chế thông báo theo luật — cần policy minh bạch thay vì mặc định gửi chi tiết có thể làm lộ điều tra.

## 20. Ma trận kiểm thử bắt buộc trước production

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | ACTIVE, password đúng | Login thành công, role đúng |
| 2 | Sai password nhiều lần dưới ngưỡng | Không login; rate limiter/attempt count đúng |
| 3 | Đạt ngưỡng lock | Trả lỗi chung; account bị chặn auth mới |
| 4 | Hai failure cùng lúc | Atomic counter, không mất update |
| 5 | Sai nhiều lần vào account không tồn tại | Chống enumeration/DoS, response chung |
| 6 | Clock trước/đúng/sau `lockedUntil` | Lock có boundary rõ, không phụ thuộc timezone |
| 7 | Account vừa locked vừa disabled | TTL hết không mở lại disabled |
| 8 | Password reset khi disabled | Không tự set enabled=true |
| 9 | Admin unlock account khác tenant | Bị 403/404 theo policy; không thay state |
| 10 | Admin có role nhưng thiếu step-up | Không đổi trạng thái nhạy cảm |
| 11 | Disable khi có HTTP session active | Session đã cấp bị chặn/invalidated theo SLA |
| 12 | Disable khi có remember-me token | Token bị thu hồi/không phục hồi đăng nhập |
| 13 | Disable khi có refresh token | Không đổi token mới sau thời hạn chính sách |
| 14 | Disable khi có JWT access token | RS thực hiện revoke/denylist/version/expiry đúng SLA |
| 15 | Disable khi user có passkey/OIDC login | Không bypass qua phương thức khác |
| 16 | Concurrent enable và disable | Status version/precondition ngăn stale write |
| 17 | Offboarding từ HR/SCIM | Event idempotent và multi-node state đúng |
| 18 | Self-service request deletion | Owner, CSRF, recent step-up, audit hợp lệ |
| 19 | DELETE bằng GET/cross-site | Không xóa account |
| 20 | PENDING_DELETION user thử login | Bị từ chối; không phát new session/token |
| 21 | Deletion worker retry | Không xóa nhầm account khác, idempotent |
| 22 | Legal retention/hold | Dữ liệu phải giữ được giữ tối thiểu và không thể login |
| 23 | Account deletion + username reuse | Không gắn token/history/roles của user cũ sang user mới |
| 24 | Restore backup trước deletion | Không hồi sinh user/credential đã xóa |
| 25 | Multi-node/cache | Node khác nhìn thấy disable/revoke trước SLA |
| 26 | Partial AS/Redis outage | Không công bố hoàn tất; có retry/alert, fail closed |
| 27 | Reactivation từ disabled | Có nguồn thẩm quyền, proofing và không tự phục hồi roles cũ |
| 28 | Browser public error messages | Không tiết lộ account unknown/locked/disabled bằng response hoặc timing rõ |
| 29 | Audit logs và telemetry | Có actor/reason/version; không log credential |
| 30 | OAuth/OIDC logout độc lập | Local disable không bị nhầm với OP session/token revocation |

Phân tách **unit tests** cho trạng thái thuần Java, **Spring Security tests** cho authentication/authorization/CSRF, **integration tests** cho DB/Redis/AS, và **end-to-end tests** với trình duyệt/IdP khi cần. Mock `UserDetails` bị disabled chứng minh checker của DAO, nhưng không chứng minh session cũ đã bị invalidate hay JWT ở RS đã bị từ chối.

## 21. Troubleshooting theo triệu chứng

### 21.1. `isEnabled=false` mà user vẫn dùng ứng dụng

Kiểm tra loại authentication thực tế. Nếu đã có `HttpSession`, request có thể khôi phục `SecurityContext` cũ. Nếu Bearer JWT, RS có thể không đọc user DB. Cần session invalidation/status recheck và token revocation riêng, không sửa bằng cách gọi `loadUserByUsername` một lần ở controller login.

### 21.2. Account bị khóa mãi dù quá `lockedUntil`

Kiểm tra so sánh thời gian UTC, dùng `Instant`, cache stale, persisted `disabled`/incident hold và trạng thái source of truth. Logic lock phải là `now.isBefore(lockedUntil)`, không dùng chuỗi ngày cục bộ hoặc một flag `locked=true` không có cơ chế reset.

### 21.3. Xóa rồi user vẫn đăng nhập qua SSO

OP/IdP có thể vẫn còn SSO session, và local app chưa map disabled/deleted account. Kiểm tra account linkage/SCIM deprovisioning, OIDC user mapping, session invalidation và refresh grants. Không cho đăng nhập lại tự tạo user local đã bị xóa chỉ vì email trùng.

### 21.4. Admin vô hiệu hóa rồi vẫn có API traffic

Có thể là API key, service principal, OAuth Bearer token, refresh grant hoặc cache. Định danh từng request theo issuer/client/accountId; tìm access path chưa gắn lifecycle policy. Không dùng email làm phương pháp duy nhất để liên kết client credentials với human account.

### 21.5. Xóa account làm mất dữ liệu bắt buộc lưu

Deletions phải qua data inventory, retention/legal hold và foreign-key strategy. Không chỉ bật cascade delete trên mọi table. Cân nhắc anonymize, hard delete đúng thời hạn và lưu minimal audit theo chính sách.

### 21.6. Đã disable nhưng cache khác node vẫn enabled

Kiểm tra event propagation, TTL, security stamp/version, stale Spring `UserCache`, session registry và consistency giữa nodes. Viết integration test: disable ở node A rồi login/request ở node B ngay sau đó; đo latency theo yêu cầu nghiệp vụ.

### 21.7. Kẻ tấn công có thể khóa account của người khác

Đó là account-lockout DoS. Bổ sung rate limit theo nhiều chiều, backoff/risk assessment, thông báo và recovery không dễ bị social engineering; không để bất kỳ username nào cũng có thể bị khóa vĩnh viễn bằng vài yêu cầu giả.

### 21.8. Pending deletion bị rollback thành ACTIVE

Xem stale event/retry, default enum mới, repository soft-delete filters và backup restore. Dùng transition preconditions/version, tombstone và reconciliation ledger; không re-create user từ OIDC login/SCIM mà không kiểm tra state đã xóa.

## 22. Checklist thiết kế trước khi đưa vào production

1. **State taxonomy:** định nghĩa tách TEMP_LOCKED, DISABLED/SUSPENDED, PENDING_DELETION, DELETED và credential expired; ghi ràng buộc transition.
2. **Mapping Spring:** kiểm tra đúng `UserDetails` flags và custom providers/OIDC/passkey/API-key paths; không chỉ test form login.
3. **Anti-brute-force:** account+IP/device rate limiting, threshold/window/backoff, xử lý lockout DoS và generic error messages.
4. **Time consistency:** dùng `Instant`, `Clock`, ngưỡng lock rõ; test trước/đúng/sau expiry.
5. **Authorization:** state-changing admin endpoints có RBAC+tenant/object permission, step-up, CSRF, audit, idempotency; không có GET delete.
6. **Concurrency:** optimistic version/conditional update, không để enable stale ghi đè security disable; atomic attempt count.
7. **Sessions:** invalidate server-side session, remember-me, cache; có SLA rõ cho hiệu lực tại mọi node.
8. **Tokens:** revoke refresh grants, API keys, access tokens theo AS/RS policy; JWT offline cần strategy riêng.
9. **Deletion inventory:** biết dữ liệu ở DB, file, search, analytics, downstream services, backups và retention/legal holds.
10. **Durable workflow:** pending deletion, outbox, retry/reconciliation, completion criteria, tombstone chống hồi sinh từ backup.
11. **Recovery:** unlock bằng đúng policy, reactivation bằng nguồn có thẩm quyền, không đồng nhất với reset password; không revive deleted principal.
12. **Observability:** audit actor/reason/time/version, trạng thái session/token/purge và lỗi partial; không log credentials/PII không cần thiết.
13. **Tests:** thử đồng thời, multi-node, fail-closed, IdP/SCIM, old HTTP sessions và JWT vẫn còn hạn, backup restore, user enumeration và user-initiated delete.

**Tóm lại:** khóa tạm thời là quyết định có thời hạn; vô hiệu hóa là quyết định quản trị/nghiệp vụ; xóa tài khoản là một workflow dữ liệu và an toàn danh tính. **Spring Security có thể ngăn lần xác thực mới thông qua các account flags, nhưng chấm dứt mọi quyền truy cập cần xử lý thêm sessions, tokens, credentials, cache và hệ thống phụ thuộc.**

## 23. Tài liệu chính thức để đối chiếu

- [Spring Security 6.5 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): các kiểm tra enabled/non-locked/non-expired.
- [Spring Security 6.5 — User.UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html): `disabled`, `accountLocked`, `accountExpired` và `credentialsExpired`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): load UserDetails, password verification và account-status checks.
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext persistence, concurrent session control, session expiration.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): SecurityContextLogoutHandler, session invalidation và remember-me cleanup.
- [Spring Session — FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html): `findByPrincipalName` và lưu ý về principal index.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token/grants theo khả năng AS.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active state được RS kiểm tra qua AS.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): lockout, brute-force defense và generic authentication errors.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): invalidation và timeout của sessions.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): phục hồi credential, chống account enumeration và abuse.
- [NIST SP 800-63B-4 — Authentication & Authenticator Lifecycle](https://pages.nist.gov/800-63-4/sp800-63b.html): chống online guessing, authenticator suspension/invalidations và recovery.
- [NIST SP 800-63A-4 — Subscriber Account Suspension or Termination](https://pages.nist.gov/800-63-4/sp800-63a/accounts/): account termination, notification và hành vi theo identity assurance.
