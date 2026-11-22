# Chính sách chuyển đổi tài khoản không thể nâng cấp trực tiếp

Trong Spring Security Authentication, nâng cấp chính sách băm mật khẩu không có nghĩa hệ thống có thể lấy một password hash cũ, gọi một encoder mới và có ngay hash tương đương. **Password hashing là phép kiểm chứng một chiều**: để tạo password hash mới mà người dùng vẫn đăng nhập bằng mật khẩu ban đầu, ứng dụng thường cần **mật khẩu dạng raw vừa được xác minh thành công**, hoặc người dùng phải **đặt mật khẩu mới** qua một quy trình khôi phục danh tính đáng tin cậy.

Vì vậy, khi đổi thuật toán, tăng work factor, bỏ các format yếu hoặc chuyển từ hệ thống tài khoản cũ sang Spring Security, không phải mọi tài khoản có thể được nâng cấp ngay trong một job chạy nền. Một phần account có thể không đăng nhập nhiều năm, thiếu email khôi phục đã xác minh, dùng hash không rõ format, phụ thuộc vào hệ thống danh tính ngoài, đang bị vô hiệu hóa hoặc có credential được coi là rủi ro. **Cần chính sách chuyển đổi theo trạng thái và mức rủi ro, không cố băm chồng bừa bãi lên giá trị cũ.**

Bài thuộc nhóm **Nâng cấp mật khẩu** và tập trung vào những tài khoản **không thể nâng cấp trực tiếp**: nhận diện, phân nhóm, quyết định giữ login legacy có kiểm soát hay bắt buộc reset, thiết kế đường khôi phục an toàn, tích hợp Spring Security `PasswordEncoder`/`UserDetailsPasswordService`, xử lý concurrency, triển khai nhiều phiên bản, ví dụ Java 17 chạy được và bộ kiểm thử thực tế.

## 1. “Không thể nâng cấp trực tiếp” nghĩa là gì?

Trước tiên phải phân biệt **ba thao tác**:

| Thao tác | Có cần biết raw password? | Điều thật sự thay đổi |
|---|---|---|
| **Gắn nhãn định dạng** | Không, nếu đã xác định chính xác thuật toán cũ | Chẳng hạn `$2a$...` thành `{bcrypt}$2a$...`; hash thực tế giữ nguyên |
| **Rehash/nâng cấp thuật toán hoặc cost** | **Có, thông thường cần raw password đã được kiểm chứng** | Tạo hash mới từ chính password gốc bằng KDF/cost mới |
| **Reset password** | Không cần biết password cũ, nhưng **phải xác minh quyền sở hữu bằng cơ chế khôi phục an toàn** | Người dùng chọn mật khẩu mới, server encode và lưu hash mới |

### 1.1. Vì sao không thể băm hash cũ thành hash mới?

Ví dụ một account lưu:

~~~text
oldHash = bcrypt("UserPassword", saltA, cost10)

Sai ý tưởng:
newHash = argon2id(oldHash, saltB, newParams)

Đăng nhập sau đó:
argon2id("UserPassword", saltB, newParams) != newHash
~~~

Ở luồng sai, server đã tạo hash cho **chuỗi oldHash** chứ không phải mật khẩu `"UserPassword"` mà người dùng nhớ. `matches(rawPassword, newHash)` với raw password ban đầu sẽ không khớp. Do vậy **`encode(storedHash)` không phải nâng cấp password hash**.

Có những chiến lược *hash wrapping* chuyên biệt để quá độ từ hash legacy: chúng yêu cầu một thiết kế xác minh phù hợp, nhận thức rủi ro của thuật toán cũ và chi phí tấn công. Chúng **không tương đương** rehash từ raw password, có thể kéo dài phụ thuộc vào hash yếu, và không nên dùng làm công thức mặc định cho bài toán chuyển đổi tài khoản.

### 1.2. Khi nào có thể nâng cấp trong lúc login?

Nếu hệ thống **vẫn xác minh an toàn được thuật toán/format cũ**, người dùng chủ động nhập đúng password và provider đã kiểm chứng nó, thì tại thời điểm ấy raw password có sẵn cho bước tạo hash mới. Luồng:

~~~text
User nhập password qua HTTPS
    |
    v
Đọc storedHash cũ theo account
    |
    +--> Legacy encoder.matches(raw, storedHash)
    |       |
    |       +-- false -> từ chối xác thực
    |       '-- true  -> raw password đã được kiểm chứng
    |
    +--> Policy: có cần upgradeEncoding?
    |       |
    |       +-- yes -> currentEncoder.encode(raw)
    |       |          -> cập nhật DB có kiểm soát đồng thời
    |       '-- no  -> giữ hash hợp lệ
    |
    v
Tiếp tục login nếu account đạt mọi kiểm tra bảo mật
~~~

**Điểm giới hạn:** “không đăng nhập” nghĩa là server **không có raw password** để tự rehash; còn “không còn khả năng xác minh format cũ” nghĩa là ngay cả raw mà client vừa gửi cũng **không thể được tin là đúng** chỉ bằng so sánh đoán mò. Hai tình huống cần chính sách khác nhau.

## 2. Phân nhóm tài khoản trước khi lập lộ trình chuyển đổi

Một chiến dịch migration nên bắt đầu bằng kiểm kê **có kiểm soát và không đưa hash/secret vào log**. Nhóm tài khoản theo tình trạng credential, khả năng xác minh, rủi ro và khả năng recovery.

| Nhóm | Ví dụ | Có thể rehash từ hash cũ ngay? | Hướng xử lý |
|---|---|---|---|
| **A. Legacy có thể xác minh** | `{bcrypt10}...` hoặc PBKDF2 cũ có decoder đáng tin | **Không** nếu chưa có raw; **có thể** sau login đúng | Giữ decoder trong thời hạn chuyển đổi; upgrade sau xác thực |
| **B. Legacy không thể xác minh** | Hash không biết thuật toán, dữ liệu bị cắt, salt thất lạc | **Không** | Khóa đường password login này; xác minh sở hữu rồi reset |
| **C. Account lâu không hoạt động** | Nhiều tháng/năm không login, hash còn ở định dạng yếu | **Không** khi vắng raw | Chốt thời hạn hỗ trợ; expire credential và yêu cầu reset khi quay lại |
| **D. Không có kênh khôi phục đáng tin** | Email chưa verified, mail cũ mất quyền sở hữu | **Không** | Recovery tăng cường bằng phương thức đã đăng ký; nếu không đủ bằng chứng thì hold |
| **E. External identity / SSO-only** | Account chỉ đăng nhập qua OIDC/SAML, không có password nội bộ | **Không áp dụng** | Không tự tạo local password; quản lý mapping IdP và credential state riêng |
| **F. Account disabled/locked/compromised** | Khóa vì rủi ro, nghi lộ dữ liệu | Không nên mở login chỉ để upgrade | Điều tra, duy trì khóa hoặc yêu cầu recovery theo policy |
| **G. Format đã hợp lệ nhưng ID thiếu** | Bcrypt thuần `$2a$...` đã được kiểm chứng | Có thể **thêm metadata ID**; không phải rehash | Prefix migration đúng thuật toán, rồi nâng cấp khi login |
| **H. Dữ liệu/import lỗi toàn vẹn** | Hai account share sai ID, hash gắn nhầm owner | Không được dựa vào dòng dữ liệu mơ hồ | Quarantine, sửa định danh/provenance trước khi credential flow tiếp tục |

Phân loại phải dựa trên **evidence từ data source đáng tin**, không dựa vào string pattern mơ hồ của một row duy nhất. Ví dụ một chuỗi dài 64 ký tự hex có thể là SHA-256, nhưng cũng có thể là token/format tự chế; gắn `{sha256}` theo phỏng đoán rồi cho login là không an toàn.

### 2.1. Phân biệt “không đủ dữ liệu” với “tài khoản không tồn tại”

Một account có record nhưng không có hash có thể là SSO-only, account đang chờ xác minh, credential bị xóa theo chính sách hoặc dữ liệu migration lỗi. Đừng tự sinh password mặc định hoặc trả cùng một trạng thái nội bộ cho mọi trường hợp mà không có phân loại. Tuy nhiên, phản hồi **công khai** vẫn cần hạn chế tiết lộ account tồn tại để tránh account enumeration.

### 2.2. Trạng thái migration không phải trạng thái tài khoản duy nhất

Một account có thể đồng thời:

~~~text
account.status            = ACTIVE
credential.migrationState = RESET_REQUIRED
credential.hashAlgorithm  = LEGACY_UNKNOWN
mfa.enrollmentState       = ENROLLED
sessions.revocationEpoch  = ...
~~~

`ACTIVE` ở domain không tự cho phép login bằng password. Trạng thái credential cần nằm ở một lớp riêng, đồng thời account có thể bị `DISABLED`, `LOCKED` hoặc `EXPIRED`. Không gộp tất cả thành một boolean `passwordNeedsUpgrade` vì **“nên nâng cấp sau login”** rất khác **“không được xác minh password cũ nữa”**.

## 3. Thiết kế trạng thái chuyển đổi (state machine)

Một mô hình gọn cho credential của một account:

| Migration state | Có xác minh bằng password cũ? | Điều kiện chuyển đi |
|---|---|---|
| `CURRENT` | Có | Hash hiện tại đủ policy; đổi/reset password khi cần |
| `LEGACY_VERIFIABLE` | Có **tạm thời**, theo deadline/risk policy | Login đúng → rehash với encoder mới; hoặc reset thành công |
| `RESET_REQUIRED` | **Không** qua password login cũ | Recovery được xác minh → đặt password mới → `CURRENT` |
| `RECOVERY_HOLD` | Không | Bổ sung bằng chứng sở hữu qua kênh an toàn; hoặc đóng tài khoản |
| `EXTERNAL_ONLY` | Không dùng local password | Xác thực bằng IdP hợp lệ; không tự tạo local secret |
| `SUSPENDED` | Không | Quy trình xử lý trạng thái/sự cố, có thể thêm reset sau đó |

Chuyển đổi quan trọng:

~~~text
LEGACY_VERIFIABLE --(login đúng + CAS rehash)------> CURRENT
LEGACY_VERIFIABLE --(hết deadline/hết quyền đọc)--> RESET_REQUIRED
RESET_REQUIRED ----(recovery đã xác minh + reset)-> CURRENT
RECOVERY_HOLD -----(xác minh danh tính đủ)---------> RESET_REQUIRED
EXTERNAL_ONLY -----(IdP auth)---------------------> External session flow
SUSPENDED --------(quy trình có thẩm quyền)--------> trạng thái được phép phù hợp
~~~

Không có cạnh `RESET_REQUIRED -> CURRENT` chỉ dựa trên việc client gửi `"newPassword"`; bắt buộc có **proof từ recovery flow đã được kiểm chứng**. Không có cạnh `SUSPENDED -> CURRENT` chỉ vì job migration chạy thành công.

### 3.1. Đặt deadline cụ thể và có chủ sở hữu

Policy nên quy định:

- **Ngày cắt hỗ trợ legacy decoder**, có người chịu trách nhiệm và kế hoạch rollback.
- **Loại thuật toán/cost nào bị chặn ngay** do rủi ro cao; loại nào cho phép login và rehash tạm thời.
- **Thời gian thông báo** đến người dùng hợp lệ; kênh in-app/email đã xác minh, ngôn ngữ hỗ trợ và chính sách không chứa link lừa đảo.
- **Khi account dormant quay lại sau deadline**, đi thẳng vào recovery/reset, không tự bật lại decoder yếu.
- **Mốc xóa/quarantine hash yếu** và thời hạn retention/backup hợp pháp; không giữ vô thời hạn “để chắc”.
- **Quy trình ngoại lệ** cho account dịch vụ, user không email, SSO-only hoặc những trường hợp pháp lý đặc biệt.

Không đặt deadline chỉ bằng `System.currentTimeMillis()` rải rác trong nhiều lớp: sử dụng policy được quản lý/versioned, `Clock` để kiểm thử và telemetry để xác minh triển khai.

## 4. Quy tắc ra quyết định theo mức rủi ro

Một policy có thể dùng các tiêu chí:

1. **Khả năng xác minh:** encoder legacy có được hỗ trợ, cấu hình salt/parameters còn đủ, dữ liệu không bị hỏng?
2. **Độ yếu của scheme:** có plaintext/NoOp, MD5/SHA-1 nhanh, PBKDF2 quá ít vòng, bcrypt cost quá thấp hoặc định dạng tự chế?
3. **Lịch sử hoạt động:** last successful login, dấu hiệu credential stuffing, thông tin contact có còn dùng được?
4. **Tầm quan trọng tài khoản:** admin, billing, khả năng truy cập PII/tiền hoặc service account.
5. **Yếu tố bổ sung:** MFA/passkey đã đăng ký, recovery codes, xác minh danh tính đáng tin.
6. **Tính tương thích:** tất cả node có hỗ trợ format mới không, có rollback khiến hash mới không đọc được?
7. **Vòng đời phiên/token:** tài khoản có active session hay refresh token sống lâu cần revoke sau reset?

Ví dụ phân nhánh chính sách:

~~~text
Credential hiện tại và đúng policy?
   |-- Có  -> CURRENT
   '-- Không
        |
        +-- Có decoder đáng tin, không quá deadline, risk cho phép?
        |      |-- Có -> LEGACY_VERIFIABLE
        |      |          -> login đúng -> rehash theo CAS
        |      '-- Không
        |
        +-- Có recovery factor đã được kiểm chứng?
        |      |-- Có -> RESET_REQUIRED -> recovery flow
        |      '-- Không -> RECOVERY_HOLD, cần hỗ trợ định danh an toàn
        |
        +-- Tài khoản chỉ đăng nhập IdP?
               -> EXTERNAL_ONLY, policy IdP riêng
~~~

Đây là **mô hình chính sách minh họa**, không phải thuật toán phân quyền của Spring Security có sẵn. Có thể cần nhiều lý do trạng thái hơn và quy trình manual review cho các account nhạy cảm.

### 4.1. Giữ decoder yếu bao lâu?

Cho login legacy rồi rehash có lợi vì người dùng không bị ép reset ngay. Nhưng nếu decoder là thuật toán quá yếu, bị lộ trong incident hoặc không còn đáng tin, một “thời gian quá độ” tùy tiện có thể tiếp tục cho attacker dùng password đã đoán. Trong trường hợp này nên **chặn password login legacy và dùng recovery**. OWASP xem việc expire/delete hash của tài khoản lâu không hoạt động rồi yêu cầu reset là một chiến lược để bỏ hash yếu, dù có đánh đổi trải nghiệm người dùng.

**Không đánh đồng thời hạn sản phẩm với thời hạn an toàn credential.** Một account vẫn còn quyền truy cập dịch vụ có thể phải reset password ngay vì phương thức xác thực cũ không còn chấp nhận được.

## 5. Recovery/reset cho tài khoản không thể tự rehash

Nếu không có raw password được xác minh bằng một decoder đáng tin, con đường hợp lý là **thiết lập một credential mới sau khi chứng minh quyền sở hữu**, không phải giải mã hash cũ hay cho phép một admin tự đặt password của user mà thiếu quy trình.

### 5.1. Một luồng reset an toàn

~~~text
Người dùng gửi yêu cầu khôi phục
      |
      +--> Phản hồi public chung, không lộ account tồn tại
      +--> Throttle / anti-automation / rate limits
      |
      v
Tạo challenge/token ngẫu nhiên dùng một lần
      |
      +--> Gửi tới factor/kênh ĐÃ ĐĂNG KÝ và ĐÃ XÁC MINH
      +--> Lưu token dạng hash, TTL ngắn, ràng buộc account/action
      +--> Không dùng token đăng nhập hoặc refresh token làm reset token
      |
      v
Người dùng trình token/proof
      |
      +--> Kiểm tra TTL, chữ ký/entropy nếu có, số lần thử, one-time use
      +--> Kiểm tra account state / MFA/step-up theo risk policy
      |
      v
Nhận mật khẩu MỚI theo policy
      |
      +--> PasswordEncoder.encode(newPassword)
      +--> Transaction: CAS/version + chuyển state -> CURRENT
      +--> Consume challenge atomically, audit, invalidate cache
      +--> Revoke/rotate session và refresh token theo chính sách
      +--> Gửi thông báo thay đổi mật khẩu
~~~

Trong hệ thống thực, phương thức recovery và yêu cầu step-up phụ thuộc threat model, quy định tuân thủ và tính nhạy cảm của account. **Gửi email tới một địa chỉ chưa được xác minh không đủ chứng minh sở hữu.** Số điện thoại hoặc email có thể đã chuyển chủ, nên account đặc quyền có thể cần nhiều bằng chứng hơn.

### 5.2. Các yếu tố an toàn không được bỏ

- **Token reset phải đủ entropy, khó đoán, ngắn hạn và dùng một lần.** Không dùng username + timestamp có thể đoán hoặc token dài hạn không kiểm soát.
- **Hash token reset trong kho dữ liệu** nếu là token bearer bí mật; tránh log nguyên token hoặc để lộ qua analytics/Referer. Thiết kế so sánh an toàn và giới hạn số lần thử.
- **Cơ chế gửi chung không làm lộ account tồn tại.** Thông báo kiểu “Nếu tài khoản phù hợp tồn tại, chúng tôi sẽ gửi hướng dẫn” là một lựa chọn; vẫn phải cân nhắc latency/response shape/rate limit.
- **Xác minh được accountId thực** và scope (tenant, realm, contact) trước khi cấp quyền reset. Không cho client chọn arbitrary accountId rồi “proof” cho một account khác.
- **Tách reset password khỏi nâng cấp hash sau login.** Reset xác minh danh tính bằng factor khác, không giả vờ người dùng đã đưa đúng password cũ.
- **Không thay hash trong transaction đang lỗi.** Một mã reset dùng hai lần chỉ một lần được thành công; chặn replay bằng transaction và unique/usedAt.
- **Đối với account bị khóa vì nghi compromise**, recovery không được tự động bỏ khóa nếu quy trình điều tra chưa cho phép.

Không dùng câu hỏi bảo mật tĩnh dễ đoán làm đường tắt. Không gửi lại mật khẩu cũ qua email; nếu ứng dụng có thể làm vậy, cơ chế lưu mật khẩu đã sai định hướng.

### 5.3. Không có kênh khôi phục đáng tin

Trường hợp `RECOVERY_HOLD` đòi hỏi quyết định nghiệp vụ và bảo mật:

- Tài khoản cá nhân có thể phải hoàn tất quy trình xác minh bổ sung hoặc không thể khôi phục nếu thiếu bằng chứng.
- Tài khoản doanh nghiệp có thể cần admin của tenant thực hiện quy trình được kiểm soát, nhưng **tenant admin không tự động có quyền chiếm account bất kỳ**.
- Tài khoản dịch vụ cần rotation qua secret manager và người vận hành được ủy quyền; thường không nên ép dùng email reset của người dùng.
- Tài khoản external-only phải quay về IdP hoặc quy trình identity linking đã xác minh.
- Đừng “đoán” contact cũ là hợp lệ hoặc tự gán một email mới mà chưa kiểm chứng.

Những quyết định này nên nằm trong một runbook có kiểm tra hai người/dual control khi rủi ro cao, logging có phân quyền và thời hạn xử lý rõ.

## 6. Tích hợp với Spring Security: nâng cấp khi xác thực thành công

Hai API có vai trò riêng:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là chữ ký **rút gọn**, không phải class bạn cần viết lại. `matches` xác minh mật khẩu ứng viên, `upgradeEncoding` chỉ báo rằng encoded value nên được tạo lại theo policy của encoder. **Nó không tự cập nhật database**.

Spring Security còn có `UserDetailsPasswordService`:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

Ở đây `newPassword` theo contract Spring Security là **mật khẩu đã được `PasswordEncoder.encode(...)`**, không phải raw password; tên tham số dễ gây hiểu nhầm. Implementation cập nhật persistent repository và trả lại `UserDetails` với hash mới.

### 6.1. Cấu hình DaoAuthenticationProvider

Với Spring Security 6.3.x, dạng tích hợp minh họa:

~~~java
DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
provider.setUserDetailsService(userDetailsService);
provider.setPasswordEncoder(passwordEncoder);
provider.setUserDetailsPasswordService(userDetailsPasswordService);
~~~

Đây là **mảnh code trong cấu hình Spring**, cần dependencies/imports/bean đã khai báo. Một số bản Spring Security mới hơn khuyến nghị constructor nhận `UserDetailsService`; đối chiếu JavaDoc đúng version. Khi login thành công và provider quyết định cần upgrade hash, nó có thể gọi `userDetailsPasswordService.updatePassword(...)` nếu được cấu hình; đây **không phải cơ chế tự động nâng cấp mọi loại tài khoản**.

Để hoạt động đúng, phải có:

- `UserDetailsService` đọc hash cũ **đúng định dạng** kèm ID khi dùng `DelegatingPasswordEncoder`.
- `PasswordEncoder` có decoder thích hợp cho hash legacy và encoder mới cho hash sau upgrade.
- `UserDetailsPasswordService` thực sự ghi hash mới, không chỉ sửa một object trong RAM.
- Chính sách account/credential state cho biết user nào được phép password login cũ; những account `RESET_REQUIRED`/`EXTERNAL_ONLY` không nên được lén đưa qua fallback yếu.
- Kiểm soát concurrent reset/rehash và cache invalidation, không để hash cũ được ghi đè hash mới.

**Điểm tinh tế:** Spring Security không biết “sau ngày X phải chặn user dormant”, “email recovery chưa xác minh”, “credential từ import mơ hồ” hay “admin đang điều tra account”. Tất cả là policy riêng phải thực thi trước hoặc trong một authentication/recovery flow phù hợp, không chỉ dựa vào `upgradeEncoding`.

### 6.2. Tránh ghi đè password mới khi có concurrency

Một implementation `UserDetailsPasswordService` dựa vào repository nên dùng accountId/version hoặc hash cũ đã đọc làm điều kiện optimistic update:

~~~sql
UPDATE account_credentials
SET password_hash = :newEncodedHash,
    version = version + 1
WHERE account_id = :accountId
  AND version = :observedVersion
  AND password_hash = :observedEncodedHash
  AND migration_state IN ('LEGACY_VERIFIABLE', 'CURRENT');
~~~

Đây là **SQL minh họa có bind parameters** và schema giả định; không chạy trực tiếp trên database thiếu bảng/cột. Kiểm tra `affectedRows == 1` để xác nhận thay đổi. Nếu zero row, một password reset, đổi trạng thái hoặc một request khác có thể đã thắng — **không retry ghi đè mù**, không cấp authentication dựa trên credential snapshot cũ khi policy yêu cầu xác minh lại.

Không gọi CAS bằng username có thể đổi làm khóa nếu ứng dụng có account ID ổn định. Trong `UserDetailsPasswordService` tiêu chuẩn, interface nhận `UserDetails`; tùy implementation của app, hãy giữ accountId/row version trong principal hoặc tra lại mapping một cách an toàn. Không dùng `user.getUsername()` làm bằng chứng tuyệt đối về accountId trong mô hình nhiều tenant.

### 6.3. Sau rehash, bản ghi trả về phải phản ánh credential mới

`updatePassword(user,newEncodedPassword)` trả về `UserDetails` đã cập nhật. Nếu DB ghi thành công nhưng bạn trả về `user` cũ mang password hash cũ, có thể khiến principal hoặc cache không nhất quán và khó kiểm thử. Dùng DTO/`UserDetails` per-request an toàn để tránh credential erasure làm mutate object cache dùng chung.

### 6.4. Không cố “sửa” tài khoản không có decoder bằng UserDetailsPasswordService

Nếu `PasswordEncoder.matches(raw,stored)` không thể kiểm tra do ID lạ/format hỏng, **không có xác thực thành công để tạo điều kiện upgrade**. Trạng thái phải đi sang `RESET_REQUIRED` hoặc `RECOVERY_HOLD`. Đừng thêm `NoOpPasswordEncoder` fallback, đừng biến mọi chuỗi unknown thành plaintext và đừng cho user tự yêu cầu update hash mới mà chưa chứng minh sở hữu.

## 7. Ví dụ Java 17 chạy được: các trạng thái không nâng cấp trực tiếp

Ví dụ console dùng Spring Security Crypto để minh họa một chính sách chuyển đổi tối thiểu. Nó phân biệt:

- **`LEGACY_VERIFIABLE`:** vẫn có thể xác minh bcrypt cũ; sau password đúng, chuyển sang hash mới bằng compare-and-set.
- **`RESET_REQUIRED`:** hệ thống không chấp nhận password login cũ; hướng tới recovery.
- **`EXTERNAL_ONLY`:** không có password nội bộ; dùng IdP.
- **`SUSPENDED`:** chặn xác thực dù hash có thể đúng.
- **`ACTIVE`:** hash hiện tại hợp lệ, login bình thường.
- **Hash có ID không biết:** không thử tự đoán; quarantine state thành `RESET_REQUIRED`.

Để có stdout ổn định, chương trình không in raw password, salt, hash hay UUID. Bài demo sử dụng một store trong RAM để biểu diễn CAS **chỉ trong một JVM**. Ứng dụng production phải dùng transaction/conditional update tại database và một recovery verifier thật.

### 7.1. Cấu trúc project Gradle

~~~text
credential-migration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/CredentialMigrationDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'credential-migration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.CredentialMigrationDemo'
}
~~~

Cần JDK 17+ và Gradle tương thích; lần đầu cần tải Spring Security dependencies từ Maven Central. Trong Spring Boot thật, phiên bản Spring Security thường do BOM của Boot quản lý thay vì cố định trực tiếp như demo.

### 7.2. Mã đầy đủ

Tạo `src/main/java/example/CredentialMigrationDemo.java`:

~~~java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class CredentialMigrationDemo {

    enum State {
        LEGACY_VERIFIABLE, ACTIVE, RESET_REQUIRED,
        EXTERNAL_ONLY, SUSPENDED
    }

    record Credential(String encoded, State state, long version) {}

    static final class Store {
        // Chỉ biểu diễn CAS atomic trong cùng một Java process.
        private final ConcurrentMap<String, Credential> rows =
                new ConcurrentHashMap<>();

        Credential get(String username) {
            return rows.get(username);
        }

        void seed(String username, Credential credential) {
            rows.put(username, credential);
        }

        boolean replace(String username,
                        Credential observed, Credential replacement) {
            return rows.replace(username, observed, replacement);
        }
    }

    static String login(Store store, PasswordEncoder encoder,
                        String username, String rawPassword) {
        Credential observed = store.get(username);
        if (observed == null || rawPassword == null) {
            return "DENIED";
        }

        switch (observed.state()) {
            case RESET_REQUIRED:
                return "RECOVERY_REQUIRED";
            case EXTERNAL_ONLY:
                return "FEDERATED_LOGIN_REQUIRED";
            case SUSPENDED:
                return "DENIED";
            case LEGACY_VERIFIABLE:
            case ACTIVE:
                break;
            default:
                return "DENIED";
        }

        if (observed.encoded() == null) {
            return "RECOVERY_REQUIRED";
        }

        try {
            if (!encoder.matches(rawPassword, observed.encoded())) {
                return "DENIED";
            }

            if (!encoder.upgradeEncoding(observed.encoded())) {
                return "OK";
            }

            // Chỉ rehash RAW PASSWORD vừa được matches thành công.
            String replacementHash = encoder.encode(rawPassword);
            Credential replacement = new Credential(
                    replacementHash, State.ACTIVE,
                    observed.version() + 1);

            // Race với reset/change password? Không ghi đè tùy tiện.
            return store.replace(username, observed, replacement)
                    ? "OK_UPGRADED" : "RETRY_AUTH";
        } catch (IllegalArgumentException malformedOrUnknownHash) {
            // Demo: quarantine credential hỏng; không tự cho phép login.
            Credential quarantined = new Credential(
                    observed.encoded(), State.RESET_REQUIRED,
                    observed.version() + 1);
            store.replace(username, observed, quarantined);
            return "RECOVERY_REQUIRED";
        }
    }

    public static void main(String[] args) {
        String demoPassword = "Example!MigrationPass";
        BCryptPasswordEncoder oldBcrypt =
                new BCryptPasswordEncoder(10);
        BCryptPasswordEncoder currentBcrypt =
                new BCryptPasswordEncoder(12);

        Map<String, PasswordEncoder> known = Map.of(
                "bcrypt10", oldBcrypt,
                "bcrypt12", currentBcrypt);
        PasswordEncoder policy =
                new DelegatingPasswordEncoder("bcrypt12", known);

        Store store = new Store();
        store.seed("linh", new Credential(
                "{bcrypt10}" + oldBcrypt.encode(demoPassword),
                State.LEGACY_VERIFIABLE, 1));
        store.seed("hong", new Credential(
                null, State.RESET_REQUIRED, 1));
        store.seed("minh", new Credential(
                null, State.EXTERNAL_ONLY, 1));
        store.seed("khoa", new Credential(
                "{bcrypt10}" + oldBcrypt.encode(demoPassword),
                State.SUSPENDED, 1));
        store.seed("loi", new Credential(
                "{unknown}unverifiable",
                State.ACTIVE, 1));

        System.out.println("linh first -> "
                + login(store, policy, "linh", demoPassword));
        System.out.println("linh current hash -> "
                + store.get("linh").encoded().startsWith("{bcrypt12}"));
        System.out.println("linh second -> "
                + login(store, policy, "linh", demoPassword));
        System.out.println("linh wrong -> "
                + login(store, policy, "linh", "wrong-password"));

        System.out.println("hong -> "
                + login(store, policy, "hong", demoPassword));
        System.out.println("minh -> "
                + login(store, policy, "minh", demoPassword));
        System.out.println("khoa -> "
                + login(store, policy, "khoa", demoPassword));

        System.out.println("loi -> "
                + login(store, policy, "loi", demoPassword));
        System.out.println("loi quarantined -> "
                + (store.get("loi").state() == State.RESET_REQUIRED));
        System.out.println("absent -> "
                + login(store, policy, "absent", demoPassword));
    }
}
~~~

### 7.3. Chạy chương trình và stdout

Với Gradle Wrapper tương thích trong thư mục project:

~~~bash
./gradlew run
~~~

Nếu chưa có wrapper nhưng máy đã cài Gradle phù hợp, dùng `gradle run`. Windows PowerShell có wrapper có thể dùng `.\gradlew.bat run`.

Các dòng output do chính chương trình in ra (bỏ qua log Gradle):

~~~text
linh first -> OK_UPGRADED
linh current hash -> true
linh second -> OK
linh wrong -> DENIED
hong -> RECOVERY_REQUIRED
minh -> FEDERATED_LOGIN_REQUIRED
khoa -> DENIED
loi -> RECOVERY_REQUIRED
loi quarantined -> true
absent -> DENIED
~~~

Diễn giải:

1. `linh` có hash legacy được map theo ID `bcrypt10`. Khi nhập đúng password, `matches` thành công; `upgradeEncoding` nhận thấy ID cũ khác `idForEncode="bcrypt12"`. Ứng dụng `encode(rawPassword)` bằng policy mới, rồi CAS thành công chuyển sang `ACTIVE`.
2. Lần đăng nhập tiếp theo của `linh` dùng hash mới, `matches` đúng và không cần upgrade nữa.
3. `hong` bị `RESET_REQUIRED`, không cho dùng password cũ để bypass recovery. Ví dụ không có dịch vụ recovery thật; nó chỉ **phân luồng**, không cho user tự “xác nhận đã recovery”.
4. `minh` là external-only, phải đi tới IdP hoặc quy trình federated login thực.
5. `khoa` bị suspended, không được mở khóa chỉ để migration.
6. `loi` có ID `unknown`, nên `DelegatingPasswordEncoder.matches` ném `IllegalArgumentException`. Demo chuyển state qua CAS thành `RESET_REQUIRED` thay vì coi chuỗi unknown là plaintext hay cấp login.
7. `absent` bị từ chối. Output có các lý do phân biệt **chỉ để học logic nội bộ**; endpoint login công khai nên dùng thông điệp phù hợp để hạn chế dò account.

**Giới hạn demo:** `Store` chỉ có `ConcurrentHashMap`; nó không bảo vệ update qua nhiều pods. Trong production, dùng accountId + DB transaction/version/CAS; state transition và recover proof phải do server xác minh. Ví dụ không phát session/JWT, không triển khai email reset, không tự xử lý UX hay tài khoản bị xâm phạm. Cost 10 cho legacy chỉ mô phỏng dữ liệu cũ và **không phải** lời khuyên tạo password mới bằng cost thấp.

### 7.4. Bài tập mở rộng

- Thử đổi `"bcrypt10"` thành ID không có trong map: nhánh đó phải không đăng nhập thành công khi chưa có decoder đáng tin.
- Giả lập một request reset password đổi version trong lúc login cũ đang tính rehash: `store.replace(username,observed,replacement)` phải trả false; code trả `RETRY_AUTH` và không ghi đè hash vừa reset.
- Thêm trường `lastLoginAt` và deadline của migration, rồi dùng `Clock.fixed` để test account vượt deadline tự chuyển sang `RESET_REQUIRED` theo policy.
- Dùng integration test PostgreSQL cho `UPDATE ... WHERE version=? AND password_hash=?` để xác nhận hai transaction không thể ghi đè phiên bản thắng cuộc.

## 8. Thiết kế dữ liệu và migration tại database

Một schema minh họa PostgreSQL:

~~~sql
CREATE TABLE account_credentials (
    account_id       UUID PRIMARY KEY,
    password_hash    TEXT,
    migration_state  TEXT NOT NULL,
    hash_scheme_id   TEXT,
    hash_version     INTEGER,
    version          BIGINT NOT NULL DEFAULT 1,
    last_login_at    TIMESTAMPTZ,
    migrated_at      TIMESTAMPTZ,
    CONSTRAINT ck_credential_state
        CHECK (migration_state IN (
            'CURRENT', 'LEGACY_VERIFIABLE', 'RESET_REQUIRED',
            'RECOVERY_HOLD', 'EXTERNAL_ONLY', 'SUSPENDED'
        ))
);
~~~

Đây là schema **đơn giản hóa**. Ứng dụng thật cần foreign key đến account, multi-tenant scope, constraints ứng với external-only và reset state, owner/recovery factors, audit, TTL, import provenance; không nên coi `hash_scheme_id` là nguồn duy nhất nếu prefix `{id}` đã nằm trong hash.

### 8.1. Những cột cần hiểu rõ

- `password_hash` có thể **NULL** ở account không có phương thức login password. Không vì thế tự tạo password mặc định.
- `migration_state` mô tả **quyền dùng credential trong giai đoạn chuyển đổi**; không thay account `locked/disabled` hoặc quyền tài nguyên.
- `hash_scheme_id` chỉ là metadata đã xác minh; nếu có, phải đồng bộ với prefix/format thực, không suy từ input client.
- `version` phục vụ optimistic locking và chống request login cũ ghi đè password vừa được reset.
- `last_login_at` phải được cập nhật trong luồng đáng tin; không dùng dấu mốc này như bằng chứng sở hữu account.
- `migrated_at` hỗ trợ audit. Ghi sự kiện theo accountId và policy version mà không cần log hash.

### 8.2. Migration theo lô không thể "rehash tất cả"

Một kế hoạch thực tế:

1. Backup mã hóa và kiểm thử restore theo quy định dữ liệu.
2. Kiểm kê số lượng account ở mỗi scheme/state, không xuất toàn bộ password hash vào tài liệu chia sẻ.
3. Đánh dấu `LEGACY_VERIFIABLE` cho format mà encoder hiện hành **đã được xác minh** có thể kiểm tra.
4. Đánh dấu `RESET_REQUIRED` hoặc `RECOVERY_HOLD` cho format không thể/không được tiếp tục xác minh.
5. Duy trì capability đọc format cũ ở node thích hợp trong cửa sổ migration được phê duyệt.
6. Cho user login đúng và rehash qua `PasswordEncoder`; hỗ trợ reset riêng.
7. Sau deadline, expire hoặc xóa hash yếu của dormant account theo retention/risk policy.
8. Chỉ gỡ decoder legacy khi DB và các hệ thống phụ thuộc không còn cần nó.
9. Kiểm tra các bản sao backup/exports/analytics cũ còn chứa hash yếu và xử lý theo lịch bảo vệ dữ liệu.

**Không tự động gộp tài khoản hoặc thay accountId** trong password migration: identity là một lớp khác, liên quan audit, tenant membership và permissions. Migration credential không cấp quyền sở hữu cho người tìm thấy username/email trong danh sách cũ.

### 8.3. Truy vấn kiểm kê an toàn

~~~sql
SELECT migration_state, hash_scheme_id, count(*) AS accounts
FROM account_credentials
GROUP BY migration_state, hash_scheme_id
ORDER BY migration_state, hash_scheme_id;
~~~

Đây là query thống kê theo trạng thái, **không xuất hash hoặc password**. Nếu cần kiểm kê những hash thiếu prefix, chỉ nên kiểm tra mẫu/nhóm an toàn với truy vấn có quyền hạn và chính sách data minimization; tránh dashboard hiển thị raw hash từng account.

### 8.4. Xóa hash yếu cũ phải có chính sách

Đối với `RESET_REQUIRED`, lựa chọn giữ hash cũ để hỗ trợ rollback hay xóa sớm phụ thuộc security policy, incident status, recovery khả dụng và retention. Nếu hash cũ quá yếu hoặc đã lộ, để nguyên trong DB thêm nhiều năm vẫn có nguy cơ offline cracking, dù login cũ đã bị chặn.

Thực hiện loại bỏ dữ liệu theo policy và kiểm soát backup/replicas; không chạy `UPDATE password_hash=NULL` đại trà trước khi bảo đảm recovery flows thực sự hoạt động. Nếu có yêu cầu pháp lý/forensic preservation, cần quản lý truy cập và retention có cơ sở.

## 9. Phối hợp account state, session, token và IdP

### 9.1. Credential reset không có nghĩa session cũ tự biến mất

Nếu user bị buộc reset password vì hash cũ quá yếu, những session/JWT đã cấp từ trước có thể tiếp tục hoạt động đến hết hạn. Cần policy rõ về mức độ khẩn cấp:

| Trường hợp | Tùy chọn xử lý session/token |
|---|---|
| Nâng cost bcrypt định kỳ, không nghi compromise | Có thể giữ phiên theo risk policy, nhưng login mới dùng hash mới |
| Credential bị xác định compromised | Revoke/invalidate session và refresh token liên quan theo chính sách |
| Account bị khóa vì gian lận | Chặn cả các request hiện hữu khi yêu cầu, không chỉ login mới |
| Bắt buộc recovery với account dormant | Có thể vô hiệu hóa phiên cũ hoặc yêu cầu reauthentication theo policy |
| External-only | Token/sessions được quản lý bởi cả IdP và RP; cần kiểm tra sự kiện thu hồi và local account status |

Với JWT self-contained còn `exp` hợp lệ, backend sẽ **không tự biết credential đã reset** nếu không có check về session version, token version, denylist, introspection hoặc trạng thái account tại request. Đừng chỉ cập nhật cột `migration_state` rồi tuyên bố toàn bộ phiên cũ đã bị thu hồi.

### 9.2. Account dùng IdP không phải tài khoản quên password local

Với OIDC/SAML, một user có thể có mapping `(issuer, subject) -> accountId`. Nếu không có local password, không nên tạo một hash giả chỉ để API `UserDetailsService` “có password”. Chính sách account/IdP linking, MFA và resource authorization nên được triển khai ở đường xác thực federated riêng.

Nếu chuyển account từ password login sang IdP-only, phải xác minh liên kết chủ thể, có cutover và rollback; không tự liên kết theo email chưa xác minh hoặc tự giữ password login fallback vô thời hạn.

### 9.3. Service account và API key

Tài khoản máy-máy có thể dùng client secret, private key, mTLS certificate hoặc API key. `PasswordEncoder`/`UserDetailsPasswordService` dành cho password login không tự mô tả vòng đời tất cả các secret này. Rotation cần runbook riêng: tạo credential mới, thử nghiệm, phân phối qua secret manager, chồng lấn ngắn có kiểm soát, thu hồi credential cũ và audit.

Không ép service account vào email-based human password reset nếu nó không có owner/kênh xác minh phù hợp.

## 10. Triển khai theo giai đoạn và rollback

### 10.1. Thứ tự rollout an toàn

~~~text
Phase 0: Khảo sát dữ liệu, threat model, policy, kênh recovery
Phase 1: Triển khai decoder/reader mới lên mọi node, chưa đổi writer
Phase 2: Tạo state, telemetry và recovery/force-reset flow đã kiểm thử
Phase 3: Đổi encoder cho hash MỚI, cho login hợp lệ auto-upgrade
Phase 4: Theo dõi rehash %, login error, support, recovery completion
Phase 5: Đến deadline, chặn legacy verifier/expire dormant credentials
Phase 6: Gỡ decoder yếu, giảm/xóa hash yếu theo retention, hậu kiểm
~~~

Điểm quan trọng ở Phase 1: **đưa khả năng đọc trước khi ghi**. Nếu node A bắt đầu lưu `{argon2}...` nhưng node B còn ở version không có mapping Argon2, người dùng có thể login được ở A nhưng bị lỗi ở B. Khi có nhiều backend/worker/portal đọc cùng DB, mọi reader phải tương thích trước write switch.

### 10.2. Rollback không được mở lại lỗ hổng cũ

Nếu migration gặp sự cố, rollback application version có thể làm node cũ không đọc được hash mới. Nhưng không vì thế được:

- Phục hồi hash yếu cũ lên trên hash mạnh mới như một phương pháp rollback.
- Bật `NoOpPasswordEncoder` toàn hệ thống để hết lỗi ID.
- Hủy bỏ flag `RESET_REQUIRED` cho account bị nghi compromise mà chưa được thẩm định.
- Cho phép raw password hoặc reset token in logs để debug.
- Reset password hàng loạt thành một giá trị dùng chung.

Cần chuẩn bị tương thích reader/writer, feature flags có quyền kiểm soát, đường rollback migration state riêng và khả năng tạm dừng **rehash writes** mà không cho phép login trái policy.

### 10.3. Đo thành công dựa trên trạng thái, không dựa vào số job chạy

Các chỉ số cần theo dõi:

- Số account/credential theo `migration_state` và `hash_scheme_id`.
- Tỷ lệ legacy còn lại theo cohort, gồm dormant account.
- Số login thành công có rehash, và số CAS conflict.
- Số reset request được phát, hoàn tất, bị từ chối và trường hợp recovery hold.
- Tỷ lệ login lỗi vì unmapped ID/format, khác với password sai.
- Số account đặc quyền còn dùng credential legacy.
- Thời gian latency và chi phí KDF sau nâng cost.
- Mức độ khiếu nại/support và tín hiệu tấn công/password spraying.

Không lưu/password hash/raw reset token vào metrics labels vì tăng nguy cơ rò dữ liệu. Dữ liệu telemetry có thể dùng accountId đã được bảo vệ/aggregate theo policy, không in username/email nếu không cần.

## 11. Lỗi thường gặp và hậu quả

| Lỗi | Hậu quả | Cách đúng |
|---|---|---|
| `encode(oldHash)` rồi lưu đè | Password gốc không đăng nhập được | Chỉ encode raw đã xác minh hoặc reset mới |
| Nghĩ “batch job có thể rehash mọi account” | Không có plaintext, tạo hash không đúng | Cho login-time upgrade và policy dormant/reset |
| Gán `{bcrypt}` vào mọi hash không ID | Format legacy bị đọc sai | Kiểm kê và xác định algorithm thực tế |
| Bật `NoOpPasswordEncoder` fallback cho hash không rõ | Có nguy cơ chấp nhận plaintext | Chặn unknown; recovery có xác minh |
| Cho login bằng mật khẩu cũ sau deadline | Duy trì hash/decoder yếu vô thời hạn | Có policy hết hạn và cưỡng chế reset |
| Bắt account dormant dùng password cũ để yêu cầu recovery | Không giải quyết được quên password | Recovery độc lập và xác minh sở hữu |
| Dùng email chưa verified làm reset factor | Nguy cơ chiếm account | Xác minh factor đã đăng ký hoặc thủ tục tăng cường |
| Reset token dùng nhiều lần hoặc hết hạn dài | Có thể bị replay/chiếm tài khoản | TTL ngắn, entropy cao, consume atomic |
| Cấp login khi encoder ném IllegalArgumentException | Lỗi format trở thành bypass | Fail closed, quarantine/log sự cố |
| Rehash ghi DB không CAS | Có thể ghi đè password vừa reset | Version/hash conditional update |
| Upgrader tự mở khóa account suspended | Bỏ qua điều tra/phân quyền | Tách account status và migration state |
| Coi hash mới có nghĩa JWT cũ đã bị revoke | Phiên cũ tiếp tục quyền | Revoke/session version/introspection theo risk |
| Đổi ID mới trước khi toàn bộ node đọc được | Login thất bại thất thường | Đưa decoder mới tới mọi reader trước |
| Hardcode policy vào từng service | Các node quyết định trạng thái khác nhau | Policy versioned, tập trung và kiểm thử |
| Không thống kê dormant account | Hash yếu tồn tại lâu không được nâng cấp | Cohort, deadline, expire/delete hoặc reset |
| Tự nối hash cũ vào hash mới rồi coi mạnh tuyệt đối | Legacy weakness có thể vẫn ảnh hưởng | Thiết kế có thẩm định, tránh wrapping tùy tiện |
| Đưa account hash vào log troubleshooting | Tăng khả năng offline cracking khi log lộ | Dùng error code, ID có kiểm soát và aggregate |
| Để admin tự đặt mật khẩu user bằng một form ít bảo vệ | Account takeover qua hỗ trợ | Two-person/step-up, audit và recovery proof |

## 12. Bộ kiểm thử cần có

### 12.1. Ma trận unit/integration

| Trường hợp | Kết quả mong đợi |
|---|---|
| Hash legacy hợp lệ + raw đúng | `matches` true; `upgradeEncoding` báo cần nâng cấp theo policy |
| Hash legacy hợp lệ + raw sai | Không rehash, không xác thực thành công |
| Legacy ID không mapped | Không tự dùng NoOp/plaintext; fail closed |
| Legacy hash bị cắt/sai salt | Không coi raw là đã xác minh; đi đường policy phù hợp |
| Account CURRENT | Login bình thường, không rehash không cần thiết |
| Account RESET_REQUIRED | Không được password login cũ; chỉ recovery được xác minh |
| Account RECOVERY_HOLD | Không mở bằng reset token gửi tới factor chưa verified |
| Account EXTERNAL_ONLY | Đăng nhập qua provider liên kết danh tính hợp lệ, không tạo local password |
| Account SUSPENDED | Không tự mở khóa nhờ migration |
| Login và reset password song song | CAS ngăn rehash cũ ghi đè hash sau reset |
| Hai login cùng account cùng upgrade | Chỉ một update thắng; request còn lại xử lý policy nhất quán |
| Reset token sử dụng hai lần | Một lần hợp lệ, lần thứ hai bị từ chối |
| Reset token hết hạn | Từ chối, không thay hash |
| AccountId/tenant mapping không khớp | Không reset/upgrade account của người khác |
| Đổi cost bcrypt | Encoder đọc cost cũ, encode mới với cost phù hợp |
| Node cũ đọc hash mới | Được kiểm chứng trước khi writer mới bật |
| Hash `{noop}` từ legacy | Không được lưu/nhận trong policy production lâu dài |
| Dormant account qua deadline | Chuyển RESET_REQUIRED, không dùng decoder yếu |
| Đổi password từ phiên đã compromise | Revoke/notify theo policy, session/token xử lý riêng |
| KDF tăng cost với lượng login lớn | Performance/rate limit không gây DoS |
| Public recovery | Response không dễ làm lộ account tồn tại |
| Audit/logging | Không xuất raw password, hash hay reset token |

### 12.2. Kiểm thử ranh giới thời gian và rollout

Dùng `Clock.fixed` trong unit test cho deadline: **trước deadline** còn `LEGACY_VERIFIABLE` nếu policy cho phép, **bằng deadline** đã chuyển `RESET_REQUIRED`, **sau deadline** không cho password login legacy. Tách khái niệm *thời hạn migration* khỏi ngày hết hạn account/domain, hạn session, hạn JWT và thời hạn recovery token.

Dùng integration test có database thật hoặc môi trường gần production để kiểm tra transaction rollback, unique constraints, optimistic update và concurrent reset/rehash. Không dựa vào `Thread.sleep` ngẫu nhiên làm giải pháp test race.

### 12.3. Câu hỏi tự đánh giá

**Câu 1.** Có thể lấy bcrypt hash cost 10 và gọi Argon2id.encode(hash) để nâng cấp password người dùng không?  
**Trả lời:** Không theo cơ chế rehash thông thường. Kết quả là hash của chuỗi bcrypt, không phải hash của raw password người dùng nhớ.

**Câu 2.** Vì sao một account không đăng nhập suốt ba năm không thể tự động nâng cost ngay?  
**Trả lời:** Server không có raw password được xác minh. Có thể cho login-time rehash nếu còn decoder đáng tin, hoặc bắt buộc reset khi quay lại theo policy.

**Câu 3.** Hash thiếu tiền tố nhưng biết chắc nó là bcrypt thì có cần reset ngay?  
**Trả lời:** Không chỉ vì thiếu ID. Có thể migrate metadata bằng cách thêm `{bcrypt}` đúng thuật toán; rehash tăng cost vẫn cần raw đã xác minh hoặc reset.

**Câu 4.** Hash legacy không rõ thuật toán; client đưa một password và yêu cầu ghi hash mới. Có chấp nhận không?  
**Trả lời:** Không. Nếu không thể xác minh raw bằng scheme cũ, cần chứng minh quyền sở hữu qua recovery trước.

**Câu 5.** `UserDetailsPasswordService.updatePassword` nhận raw password hay encoded?  
**Trả lời:** Theo contract Spring Security, nhận **newPassword đã được encoder mã hóa**, và implementation phải cập nhật repository.

**Câu 6.** Nếu một login đang rehash và reset password vừa commit thì xử lý sao?  
**Trả lời:** CAS/version update không được ghi đè. Request login dựa trên credential cũ phải xử lý lại authentication theo policy, không tự ghi/cho phép dựa vào snapshot lỗi thời.

**Câu 7.** Tài khoản bị `SUSPENDED` nhưng đã rehash thành công; có nên mở khóa không?  
**Trả lời:** Không. Migration state không có quyền override account status, nhất là trong vụ nghi compromise.

**Câu 8.** Đã chuyển toàn bộ code ghi hash mới, có thể gỡ ngay legacy encoder không?  
**Trả lời:** Chưa. Cần xác minh account nào vẫn có hash cũ, node nào còn cần đọc, deadline/dormant flow và rollback compatibility.

**Câu 9.** JWT còn hạn sau khi account bắt buộc reset password có bị chặn tự động không?  
**Trả lời:** Không nhất thiết; cần session/token revocation hoặc checks tương ứng với yêu cầu an toàn.

## 13. Checklist triển khai chính sách chuyển đổi

- [ ] Xác định lý do thật sự không thể nâng cấp: thiếu raw, không có decoder, format lỗi, account dormant, SSO-only hay account bị khóa.
- [ ] Phân biệt **gắn metadata ID** với **rehash** và **reset**; không thay thế cái này bằng cái kia.
- [ ] Xây state machine có `CURRENT`, `LEGACY_VERIFIABLE`, `RESET_REQUIRED`, `RECOVERY_HOLD`, `EXTERNAL_ONLY` và trạng thái chặn liên quan.
- [ ] Định nghĩa deadline, owner, risk exceptions và chính sách xóa/expire hash yếu.
- [ ] Nếu cho login legacy, chỉ nâng cấp sau `matches` thành công với raw password thực, không rehash hash cũ.
- [ ] Có `PasswordEncoder` đọc format cũ đáng tin và tạo hash mới mạnh; không fallback NoOp.
- [ ] Nếu dùng `DaoAuthenticationProvider` automatic upgrade, cấu hình `UserDetailsPasswordService` và kiểm thử DB update thật.
- [ ] Dùng accountId/tenant đúng phạm vi, CAS/version/transaction để chống race với reset.
- [ ] Có recovery/reset flow xác minh danh tính, token dùng một lần và hạn ngắn, rate limiting và audit.
- [ ] Xác minh contact/factor recovery, không reset account của người khác qua email chưa verified.
- [ ] Giữ chính sách suspended/locked/compromised độc lập, không mở khóa vì migration.
- [ ] Phối hợp phiên/JWT/refresh token/IdP theo risk policy, không coi đổi hash tự revoke token.
- [ ] Triển khai reader compatibility trên mọi node trước writer hash format mới.
- [ ] Theo dõi dormant cohort, reset success, rehash success, CAS conflict và lỗi unmapped ID.
- [ ] Không ghi raw password, hash, reset token, secret manager values ra logs/metrics.
- [ ] Test production-like cả deadline, concurrency, recovery, nhiều nodes và rollback.
- [ ] Gỡ bỏ legacy decoder theo kế hoạch, giải quyết hash yếu trong DB/backup phù hợp với retention.

**Ghi nhớ:** **Tài khoản không thể nâng cấp trực tiếp không phải lý do để bỏ bảo mật hoặc tạo password mặc định.** Khi có **raw password đã được xác minh**, rehash theo encoder mới và cập nhật atomically; khi **không thể xác minh an toàn**, chặn password login cũ và yêu cầu **recovery/reset đã chứng minh quyền sở hữu**. Chính sách hiệu quả phải xử lý cả tài khoản lâu không hoạt động, tài khoản SSO, tình trạng account, phiên còn sống, concurrency và lộ trình bỏ thuật toán yếu.

### Tài liệu chính thức

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): one-way password transformations, `DelegatingPasswordEncoder`, hash format và kế hoạch mã hóa an toàn.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService` và `PasswordEncoder` trong login username/password.
- [Spring Security — UserDetailsPasswordService JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): `updatePassword` nhận encoded password, cập nhật repository và trả UserDetails mới.
- [Spring Security — DaoAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `setUserDetailsPasswordService` và password encoder.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): tăng work factor, upgrade legacy hash khi user login và chiến lược yêu cầu reset dormant account.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery token, hạn dùng, account enumeration và reset an toàn.
- [NIST SP 800-63B (Rev. 4)](https://pages.nist.gov/800-63-4/sp800-63b.html): password verifier storage, recovery/authenticator lifecycle và session management.
