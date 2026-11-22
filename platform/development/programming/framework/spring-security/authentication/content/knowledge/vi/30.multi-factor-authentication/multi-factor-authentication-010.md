# Kiểm thử MFA: thiếu yếu tố, hết hạn, phát lại và chuyển đổi danh tính trong Spring Security

## 1. Tại sao phải kiểm thử trạng thái yếu tố thay vì chỉ kiểm tra “login thành công”?

**Multi-Factor Authentication (MFA)** yêu cầu nhiều bằng chứng thuộc các nhóm yếu tố độc lập, ví dụ mật khẩu (something you know) và một phương thức sở hữu/kiểm soát khác như passkey bảo vệ bởi thiết bị, OTP/OTT qua kênh đã đăng ký (something you have). Một hệ thống MFA đúng phải ngăn một yêu cầu nhạy cảm nếu bằng chứng thiếu, cũ, đã dùng lại hoặc thuộc **người khác**. Chỉ nhìn thấy HTTP 200 sau một lần đăng nhập đẹp không chứng minh được các thuộc tính này.

Phạm vi bài này là **kiểm thử cơ chế nhiều yếu tố trong Spring Security authentication** trên ứng dụng Servlet, với bốn nhóm lỗi chủ đạo:

1. **Thiếu yếu tố:** người dùng đã đăng nhập bằng mật khẩu nhưng chưa có bằng chứng thứ hai; hoặc có một OTT nhưng chưa xác thực bằng mật khẩu mà chính sách đòi hỏi.
2. **Yếu tố hết hạn:** mã OTT/TOTP quá thời hạn sử dụng, hoặc lần xác thực thứ hai đã thành công từ lâu nhưng thao tác nhạy cảm yêu cầu yếu tố **mới được xác minh gần đây**.
3. **Yếu tố bị phát lại:** một OTT đã tiêu thụ, TOTP cùng time step đã dùng, WebAuthn challenge/response bị dùng lại, hoặc hai request đồng thời cùng dùng một token.
4. **Chuyển đổi danh tính:** mật khẩu được xác thực cho Alice nhưng yếu tố thứ hai thuộc Bob, hoặc phiên chuyển từ Alice sang Bob mà vẫn “mang theo” factor authorities của Alice.

**Một quy tắc bất biến:** chỉ cho phép thao tác có MFA khi các yếu tố **đều hợp lệ, đủ mới, thuộc cùng tài khoản/cùng giao dịch cần thiết** và chưa bị tiêu thụ trái phép. Ứng dụng cũng phải kiểm tra **authorization** (roles/tenant/resource ownership) sau khi authentication đạt. MFA không tự cấp quyền admin.

### Cảnh báo phiên bản Spring Security

- **Spring Security 7.0+ (Servlet)** bổ sung mô hình MFA gốc với `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, `AuthorizationManagerFactories.multiFactor()` và các `RequiredFactor` có thời gian hợp lệ. Đó là API được trình bày ở ví dụ Spring chính.
- **Spring Security 6.x** có các authentication mechanism như `formLogin`, `oneTimeTokenLogin` (OTT từ 6.4), nhưng **không có bộ API MFA gốc nêu trên**. Không copy import `FactorGrantedAuthority`/`@EnableMultiFactorAuthentication` của 7.x vào dự án 6.5. Với 6.x cần cơ chế MFA tùy biến hoặc nâng cấp hệ sinh thái tương thích.
- Các ví dụ Spring 7.x cần môi trường tương thích, ví dụ **Spring Boot 4.x + Java 17+**. Phần Java 17 độc lập ở cuối không phụ thuộc Spring và giúp kiểm thử nguyên lý ngay cả khi chưa nâng cấp.

## 2. Mô hình bằng chứng: authentication, yếu tố và policy

Trong Spring Security 7.x, mỗi cơ chế xác thực thành công có thể cung cấp một `FactorGrantedAuthority` trong `Authentication`. Những giá trị được hỗ trợ gồm:

| Giá trị/khái niệm | Ý nghĩa | Dùng trong kiểm thử |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | Có bằng chứng của cơ chế mật khẩu, ví dụ `FACTOR_PASSWORD` | Test chỉ có password chưa đủ khi policy còn cần OTT |
| `FactorGrantedAuthority.OTT_AUTHORITY` | Có bằng chứng của cơ chế One-Time Token, ví dụ `FACTOR_OTT` | Test chỉ có OTT chưa đủ khi policy còn cần password |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | Có bằng chứng của WebAuthn | Test dựa theo passkey credential thực sự đã đăng ký, không giả định mọi device support |
| `FactorGrantedAuthority.getIssuedAt()` | Thời điểm chứng cứ factor được cấp | Test yếu tố đã quá “max age” ở endpoint nhạy cảm |
| `AuthorizationManagerFactories.multiFactor()` | Xây rule kết hợp các yếu tố | Test chỉ đủ tất cả các yếu tố và role mới được đi vào |
| `RequiredFactor.validDuration(Duration)` | Đặt độ mới tối đa được chấp nhận cho một factor tại một authorization rule | Test trước/sau ranh giới thời hạn |

**Phân biệt hai loại “hết hạn”:**

- **Challenge/token expiry:** OTT phát hành lúc 10:00, TTL 5 phút, đến 10:05 chưa tiêu thụ thì token không được dùng nữa. Nó áp dụng **trước** khi bằng chứng OTT được ghi nhận thành công.
- **Factor freshness:** OTT đã được tiêu thụ thành công lúc 10:00, nhưng chuyển khoản lúc 10:04 yêu cầu OTT trong vòng 2 phút. Authority có thể vẫn tồn tại trong phiên, nhưng **policy phải xem factor đã quá cũ**. Đây là kiểm tra ở **authorization**, không thể suy ra từ mỗi việc authority có tên `FACTOR_OTT`.

Tương tự, phiên HTTP có thể sống 8 giờ trong khi password proof dùng cho đổi email cần mới trong 10 phút. **Tuổi thọ session**, **TTL challenge** và **validDuration factor** là ba đồng hồ khác nhau.

Một policy minh họa:

- `GET /dashboard`: chỉ cần user đã authenticated.
- `POST /payments/confirm`: cần mật khẩu trong 30 phút gần đây **và** OTT trong 2 phút gần đây; đồng thời cần permission của người sở hữu giao dịch.
- `POST /admin/users/suspend`: cần vai trò `ROLE_ADMIN` + cả hai factor trong cửa sổ do tổ chức quy định.
- Anonymous hoặc password-only được điều hướng đến nơi cung cấp factor còn thiếu; **không** trả kết quả thao tác nhạy cảm chỉ vì đã đăng nhập bằng một cách nào đó.

Tài liệu Spring Security 7 cho biết `FactorGrantedAuthority` chứa `issuedAt` và các policy có thể định nghĩa `validDuration` khác nhau trên từng route. Không tạo `SimpleGrantedAuthority("FACTOR_OTT")` bằng tay để “lừa” flow test; như vậy không chứng minh factor thực sự đã được cung cấp và không có timestamp đúng.

## 3. Sơ đồ trạng thái và ranh giới tin cậy

```text
[ANONYMOUS]
    | password hợp lệ cho Alice
    v
[ALICE: PASSWORD_ONLY] --- GET /dashboard ---> ALLOWED (nếu policy cho phép)
    | POST /payments/confirm
    +---> DENIED / cần OTT (vì thiếu yếu tố)
    |
    | Server phát OTT challenge cho đúng Alice, transaction/session
    v
[ALICE: PASSWORD_ONLY + PENDING_OTT]
    | token sai/hết hạn/Bob/replayed
    +---> DENIED, không cấp FACTOR_OTT
    |
    | POST tiêu thụ OTT hợp lệ đúng Alice, one-time
    v
[ALICE: PASSWORD + OTT_VERIFIED]
    | payment trong freshness windows + quyền nghiệp vụ
    +---> ALLOWED
    |
    | đợi OTT proof quá validDuration
    v
[ALICE: OTT_PROOF_STALE]
    +---> DENIED thao tác nhạy cảm / yêu cầu OTT mới
    |
    | switch principal thành Bob, logout, session reset
    v
[BOB: FACTORS_CLEARED]
    +---> không được thừa kế password/OTT của Alice
```

**Ranh giới bắt buộc:** raw token/challenge từ client là **dữ liệu chưa đáng tin**. Server phải ràng buộc bằng chứng với account ID ổn định, dự án/tenant (nếu có), browser transaction/session hoặc cơ chế xác minh độc lập phù hợp, expiry, trạng thái single-use và policy hiện hành. Không dùng email/display name từ form để đổi principal sau khi đã xác minh yếu tố khác.

Một hệ thống có thể không ràng buộc OTT với đúng browser ban đầu (ví dụ magic link mở ở thiết bị khác), nhưng lúc đó phải có **quy tắc rõ**: login qua link có thể là authentication riêng, không được tự cộng factor đó vào phiên của user khác. Nếu cần ghép vào **giao dịch MFA đang dở**, phải chứng minh challenge gắn với đúng user/transaction. Đừng tự viết code kiểu “có một code hợp lệ là thêm `FACTOR_OTT` vào session hiện tại”.

## 4. Ma trận kiểm thử bắt buộc

| ID | Given / Khi nào | Hành động | Then / điều kiện qua |
| --- | --- | --- | --- |
| M01 | Anonymous, không yếu tố | `POST /payments/confirm` | Không được thực hiện thanh toán; browser tới login, API có status từ chối phù hợp |
| M02 | Alice chỉ xác thực password | Gọi endpoint đòi password+OTT | **Không** trả 2xx; được yêu cầu factor OTT |
| M03 | Alice chỉ xác thực OTT | Gọi endpoint đòi hai factor | **Không** trả 2xx; được yêu cầu password |
| M04 | Alice có cả hai factor, mới và hợp lệ | Gọi endpoint + đúng quyền | Được phép; audit đúng Alice |
| M05 | OTT chưa sử dụng nhưng quá TTL | Submit OTT hết hạn | Từ chối; không thêm proof factor |
| M06 | OTT còn hạn và đã consume lần đầu | Submit lại cùng raw token | Lần hai từ chối, không tạo phiên/lần tăng quyền mới |
| M07 | Hai request cùng dùng một OTT | POST cùng token đồng thời, hai session | Tối đa **một** lần tiêu thụ thành công |
| M08 | Alice có OTP/TOTP ở step X đã xác minh | Submit lại step X | Theo anti-replay policy, từ chối hoặc xử lý đã dùng; không tự cấp proof lần hai |
| M09 | Alice có chứng cứ OTT cũ hơn max age | Gọi endpoint đòi proof mới | Từ chối dù session vẫn authenticated |
| M10 | Alice password hợp lệ, token cấp cho Bob | Gửi Bob token vào flow Alice | Từ chối, không ghi factor cho Alice |
| M11 | Alice hoàn tất MFA, sau đó switch sang Bob | Gọi endpoint nhạy cảm bằng Bob session | Bị yêu cầu xác minh lại; không kế thừa factor của Alice |
| M12 | Alice có factor, logout, login Bob cùng browser | Gọi endpoint | Không giữ evidence của phiên cũ |
| M13 | Alice có MFA, role USER | Gọi admin endpoint | Từ chối dù MFA hợp lệ (role/policy riêng) |
| M14 | Một OTT đã hết hạn nhưng session cũ còn hoạt động | POST token từ browser khác | Từ chối; không mở session |
| M15 | Request thiếu CSRF khi dùng form/cookie | POST challenge/login | Chặn bởi CSRF filter, không tạo proof |
| M16 | Factor của tenant A, user tương tự ở tenant B | Gửi proof vào tenant B | Từ chối do stable identity/tenant mismatch |
| M17 | Reset/revoke đăng ký MFA hoặc đổi mật khẩu | Dùng lại proof cũ theo chính sách revoke | Không được dùng chứng cứ bị thu hồi |
| M18 | Factor đúng nhưng request thuộc object của user khác | Truy cập resource | Từ chối bởi authorization nghiệp vụ |
| M19 | Factor fresh đúng nhưng MFA policy thay đổi | Truy cập endpoint sau thay đổi | Enforce yêu cầu factor hiện hành, không chỉ cache kết quả cũ |
| M20 | Hai tab/requests cạnh tranh trong một session | Đổi identity khi còn pending OTT | Không được cộng proof sai account dù thứ tự response thay đổi |

**Kiểm thử status:** ứng dụng web có thể **302 redirect sang form factor còn thiếu**, API có thể 401/403 tùy authentication entry point/access-denied flow. Test nên assert **không có 2xx/thao tác side effect**, **đúng challenge/redirect** và **không cấp factor**, thay vì hardcode 403 cho mọi ứng dụng.

## 5. Kiểm thử yếu tố bị thiếu: không nhầm partial authentication với full MFA

### 5.1. Password-only

Với Spring Security 7, một user có thể đã đăng nhập hợp lệ nhưng chỉ có `FACTOR_PASSWORD`. Rule `.authenticated()` thông thường có thể cho truy cập endpoint ít rủi ro; rule yêu cầu password + OTT phải từ chối/điều hướng để hoàn thiện. Đừng chỉ kiểm `SecurityContextHolder.getContext().getAuthentication() != null` và quyết định “đủ MFA”.

Trình tự test:

1. Dùng browser/session A mở route bảo vệ; thực hiện POST login password thật với CSRF hợp lệ.
2. Đọc session cookie do server trả; ở request tiếp theo cùng session, gọi `GET /dashboard`, dự kiến pass nếu policy chỉ đòi authenticated.
3. Gọi `POST /payments/confirm` mà chưa tiêu thụ OTT, phải **không thành công**.
4. Kiểm tra bên dưới: không có database payment được tạo, không có email “thành công”, không phát sinh side effect.
5. Xác minh server chuyển sang OTT form hoặc trả lỗi yêu cầu factor; không được âm thầm “thêm `FACTOR_OTT`” chỉ vì user đã nhập password.

### 5.2. OTT-only

Trong cấu hình cho phép OTT làm cách đăng nhập đầu tiên, user có thể có `FACTOR_OTT` nhưng chưa có `FACTOR_PASSWORD`. Phải test chiều ngược lại: route cần cả hai không được đi qua, framework có thể hướng user đến login password. **Hai cơ chế đăng nhập tồn tại không tự tạo MFA**: chỉ cấu hình `formLogin()` và `oneTimeTokenLogin()` mà không có rule kết hợp sẽ có thể cho phép đăng nhập bằng **một trong hai**.

### 5.3. Role không thế chỗ factor

Một tài khoản `ROLE_ADMIN` chỉ xác thực bằng password vẫn phải bổ sung OTT nếu route admin yêu cầu MFA. Tương tự, một user đã có cả hai factor nhưng thiếu `ROLE_ADMIN` không được vào admin. Viết test hai chiều, không chỉ “admin MFA pass”.

### 5.4. Quan sát đúng tài khoản

Khi assert authenticated factor, đối chiếu `Authentication.getName()` và stable account ID. Nếu tenant là một phần danh tính, assert tenant ID và issuer/session tương ứng. Không chấp nhận testcase nơi MockMvc đưa vào `@WithMockUser(authorities={"FACTOR_PASSWORD","FACTOR_OTT"})` rồi nói đã chứng minh password/OTT thật: cách đó **giả lập đã đủ yếu tố** và bỏ qua authentication handlers.

## 6. Hết hạn: challenge expiry và factor freshness là hai testcase khác nhau

### 6.1. OTT challenge quá TTL

Spring Security One-Time Token Login có `OneTimeTokenService.generate(...)` và `consume(...)`. Dùng mã có expiry cụ thể, ví dụ phát 10:00:00, TTL 5 phút. Kỳ vọng:

- Submit 10:04:59 (và token chưa dùng): có thể hợp lệ nếu các điều kiện khác đạt.
- Submit tại hoặc sau **10:05:00**: **không hợp lệ**, không sinh factor hoặc session mới.
- Link đã mở ở 10:04 nhưng POST login tại 10:05:01: vẫn phải từ chối. GET chỉ hiển thị form, **không gia hạn TTL**.
- Token không được “hồi sinh” nếu đồng hồ server lùi; dùng clock nhất quán, chính sách skews rõ và storage đảm bảo expiry.

Đối với test, **không sử dụng Thread.sleep(300_000)**. Tiêm `Clock` giả, đặt `Instant` trong token store test hoặc dùng mutable clock có điều khiển, bảo đảm deterministic; nếu framework service không cho tiêm Clock, dùng fake/test implementation chỉ trong unit/integration test thích hợp và một end-to-end thật cho provider.

### 6.2. Factor proof quá cũ

Spring Security 7.x có `FactorGrantedAuthority.getIssuedAt()` và `validDuration` theo authorization rule. Test ví dụ:

- Alice xác thực password 10:00:00, OTT 10:04:00.
- `/user/settings` đòi password mới trong 30 phút: lúc 10:29 có thể pass với password còn mới (nếu các factor khác/policy khác đạt).
- `/payments/confirm` đòi OTT trong 2 phút: lúc 10:06:01 phải **không được thực hiện** dù OTT đã từng thành công.
- Nếu chính sách yêu cầu mới cả hai factor, chỉ refresh OTT mà password đã quá thời hạn vẫn chưa đủ; phải refresh **yếu tố đang thiếu/đã cũ** theo rule.

Không nhầm **mã OTT hết hạn** với **factor OTT evidence hết độ mới**. Một mã OTT đã tiêu thụ thành công lúc 10:04 không còn để dùng lại, nhưng bằng chứng đã xác thực có thể còn được dùng tới 10:06 theo policy. Ngược lại, mã chưa dùng mà đã qua TTL không trở thành chứng cứ hợp lệ chỉ vì server session còn hoạt động.

### 6.3. Boundary và thời gian

Test ở thời điểm ngay trước, đúng và ngay sau ranh giới. Nếu backend dùng `Instant`/`Clock`, tránh chuyển các thời điểm sang timezone để so trực tiếp; TTL là khoảng thời gian, không phải ngày tháng địa phương. Kiểm tra clock skew, nhiều pod, cache, truyền request chậm. Điều kiện tại đúng mốc hết hạn thường là **now < expiresAt**; so sánh chính xác dựa trên thiết kế/token service và test rõ ràng.

## 7. Phát lại: token, time step và race condition

### 7.1. OTT bị submit hai lần

Sau khi `POST /login/ott` sử dụng OTT T thành công, một POST khác mang T từ browser mới phải thất bại. Kể cả browser GET lại trang `/login/ott?token=T` và nhìn thấy form, POST T đã tiêu thụ không được login nữa. Nếu test lần hai dùng cùng cookie session đã authenticated, nó có thể vẫn truy cập trang bảo vệ do **session trước đó**; vì vậy phải dùng **browser/session tách biệt** để xác định token replay thực sự bị từ chối, tránh false positive.

### 7.2. Concurrent replay

Hai request đồng thời cùng lấy OTT T từ DB. Nếu service làm `SELECT ...` rồi `DELETE ...` không có cơ chế atomic/lock, cả hai có thể đọc T trước khi một bên xóa. Quy tắc mong đợi là **tối đa một lần consume thành công**, được kiểm thử trên database thật dưới concurrency (không chỉ in-memory map).

**Lưu ý bảo mật:** Spring đã công bố **CVE-2026-22751** (21/04/2026) ảnh hưởng đến cách ứng dụng dùng `JdbcOneTimeTokenService` ở một số bản **Spring Security 6.4/6.5/7.0** chưa vá; lỗi TOCTOU có thể cho một token tạo nhiều phiên khi các request chạy đồng thời. Khi triển khai phải dùng bản đã vá như 6.5.10 hoặc 7.0.5 trở lên trong các dòng đó (6.4.16 qua kênh Enterprise Support), kiểm tra BOM thực chạy và **vẫn test concurrency**.

### 7.3. TOTP/HOTP replay

TOTP khác OTT: mã 6 chữ số được sinh từ shared seed và time step, **không phải random token được server lưu rồi xóa**. Một server có thể cho phép một cửa sổ ±1 step để chịu lệch đồng hồ, nhưng chính sách replay phải có trạng thái **last-accepted step/counter** hoặc replay ledger được cập nhật atomic. Nếu không, cùng mã TOTP có thể được nộp lại trong cùng time step và được chấp nhận lần nữa. Với HOTP, phải quản lý counter và chống dùng lại counter cũ. Không tái sử dụng cùng logic `OneTimeTokenService.consume` cho mọi TOTP mà không hiểu chuẩn RFC 6238/RFC 4226.

### 7.4. WebAuthn challenge replay

Một WebAuthn authentication assertion liên quan đến **challenge** do server tạo và RP ID/origin, credential ID, chữ ký authenticator và các kiểm tra khác. Replay assertion cho challenge đã dùng hoặc ở session/giao dịch khác phải bị từ chối. **Sign counter** của authenticator không luôn tăng theo mọi thiết bị; đừng chỉ dựa vào counter để phát hiện mọi replay. Server cần challenge ngẫu nhiên, TTL, single-use, origin/RP ID/credential binding và signature validation.

### 7.5. Không lẫn việc replay token với giữ session sau login

Một OTT dùng một lần **không ngăn phiên vừa login hợp lệ tiếp tục hoạt động** bằng cookie session. Test “gửi lại GET /private rồi vẫn nhận 200” không có nghĩa OTT bị replay: đó là tái sử dụng authenticated **session**. Để kiểm OTT single-use, phải kiểm **POST consume lại T** trong trạng thái chưa có authentication mới.

## 8. Chuyển đổi danh tính: không cộng yếu tố của Alice với Bob

Đây là nhóm lỗi nguy hiểm vì các test “happy path” cùng một user thường không phát hiện.

### 8.1. Mật khẩu Alice + token Bob

Ví dụ:

```text
Session S (Alice đã xác thực password)
  principal = account-id-alice
  FACTOR_PASSWORD issuedAt=10:00
  pending OTT challenge của Alice = T_A

Attacker/bug đưa token T_B của Bob vào POST hoàn thiện MFA:
  T_B tồn tại, có thể còn hạn, nhưng ownerAccountId = bob
  session/principal = alice

KẾT QUẢ BẮT BUỘC:
  Không cấp FACTOR_OTT cho Alice.
  Không đổi principal sang Bob chỉ vì token T_B hợp lệ.
  Không cho phép endpoint nhạy cảm.
```

Khi flow xác thực đa bước cần ghép hai factor, bảo đảm **cùng stable account ID**, và nếu thiết kế cần thì gắn factor challenge với **transaction ID, session ID, tenant ID, authentication epoch**. Đừng so theo tên hiển thị hoặc email input không được canonicalize; cùng `username=admin` có thể tồn tại ở hai tenant/realm.

### 8.2. Switch principal giữa chừng

Alice password thành công, app chuẩn bị OTT. Trong cùng browser user logout, login Bob, hoặc admin dùng cơ chế impersonation `SwitchUserFilter` chuyển sang người dùng khác. Nếu ứng dụng giữ `FACTOR_PASSWORD` của Alice hay pending token T_A trong session rồi áp cho Bob, policy MFA có thể bị vượt qua.

Test cần chứng minh:

- Sau switch/logout, factor evidence của Alice không được mang sang Bob. Cần reset/đánh giá lại transaction, `SecurityContext`, session và cache liên quan đến factor theo chính sách.
- Token được cấp cho Alice trước switch không được dùng làm bằng chứng OTT của Bob dù POST vào đúng endpoint.
- Khi switch **quay lại Alice**, không mặc định tin mọi proof cũ còn tươi: chính sách có thể yêu cầu MFA lại cho hành động nhạy cảm. Đặc biệt phải kiểm soát impersonation cho admin và audit cả actor/subject.
- Hai request đồng thời, một request switch user và một request nhận OTT, phải không thể trộn các factor khác principal khi kết quả được lưu.
- Nếu implement “remember device” hoặc saved authentication, điều kiện này càng quan trọng: marker chỉ có hiệu lực cho **đúng user+device+policy+expiry**, không cho mọi account dùng cùng browser.

### 8.3. Phân biệt user switch và role elevation

- **Đăng nhập người khác:** `Authentication.getPrincipal()` hoặc stable account identity đổi; toàn bộ chứng cứ thuộc user cũ phải được đánh giá lại.
- **Nâng quyền cùng một người:** principal vẫn là Alice nhưng được yêu cầu thêm proof/step-up cho hành động nhạy cảm; có thể dùng factor evidence cùng Alice theo chính sách thời gian.
- **Admin impersonation:** `SwitchUserFilter` giữ thông tin original user thông qua `SwitchUserGrantedAuthority` nhưng không được coi đó là bằng chứng MFA của user bị impersonate. Cần policy riêng cho thao tác admin và ranh giới quyền.
- **Login session fixation:** session ID có thể được rotate khi login; token/giao dịch đang chờ phải gắn với lifecycle session theo cơ chế an toàn, không chỉ lưu định danh session cũ rồi silently bypass.

Cần test cả case **Bob có email/OTP đúng của Bob**, nhưng session đăng nhập đang là Alice. Trả về một “authenticated Bob” không phải là bước thứ hai cho Alice; đó là một danh tính khác, phải là luồng login mới có lifecycle rõ ràng.

## 9. Cấu hình Spring Security 7: yêu cầu hai yếu tố và độ mới

### 9.1. Cấu hình toàn cục đơn giản

Với project **Spring Boot 4.x + Spring Security 7.x + Java 17+ (Servlet/MVC)**, cấu hình dưới đây theo mô hình chính thức. Đặt vào `src/main/java/com/example/mfa/GlobalMfaSecurity.java` trong project đã có `@SpringBootApplication` và các dependencies Spring Web, Security, tests:

```java
package com.example.mfa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class GlobalMfaSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Đây là mã cấu hình Spring **dành cho một project đã tồn tại**, không phải Java standalone có thể chạy bằng `javac`. Phải cấu hình `UserDetailsService`, password encoder, kênh giao OTT, token store và login views thực tế. Khi dùng mặc định, `POST /ott/generate` phát hành, `GET /login/ott` hiển thị submit page, `POST /login/ott` tiêu thụ token. Chỉ bật `oneTimeTokenLogin(Customizer.withDefaults())` **không tự gửi email**; ứng dụng cần `OneTimeTokenGenerationSuccessHandler` đưa token tới email đã xác minh.

Với cấu hình 7.x ở trên, Spring Security kết hợp các yêu cầu `FACTOR_PASSWORD` và `FACTOR_OTT` vào các rule. Route admin cần thêm `ROLE_ADMIN`. Khi thiếu factor, framework hỗ trợ đưa user tới cơ chế lấy factor còn thiếu; URL/status thực tế tùy entry point và cấu hình giao diện. Nếu muốn endpoint công khai, thêm `permitAll()` cho đúng route; không tắt CSRF chỉ để bước phát hành/tiêu thụ token chạy.

### 9.2. Chỉ yêu cầu yếu tố mới cho endpoint nhạy cảm

Ví dụ này áp dụng chính sách **password proof không quá 30 phút** và **OTT proof không quá 2 phút** trên route thanh toán, trong khi dashboard chỉ cần authentication thường. Spring Security 7.x cung cấp factory theo `RequiredFactor`; use case dùng `@EnableMultiFactorAuthentication(authorities = {})` để bật support nhưng **không** ép MFA toàn cục:

```java
package com.example.mfa;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {})
public class RecentMfaSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        var recentFactors = AuthorizationManagerFactories.multiFactor()
                .requireFactor(factor -> factor.passwordAuthority()
                        .validDuration(Duration.ofMinutes(30)))
                .requireFactor(factor -> factor.ottAuthority()
                        .validDuration(Duration.ofMinutes(2)))
                .build();

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/payments/**")
                    .access(recentFactors.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**Chỉ chọn một** trong hai class cấu hình để chạy, không để chúng cùng tạo hai chain trùng mọi request trong một ứng dụng. Thêm route authorization nghiệp vụ/CSRF theo sản phẩm; tài khoản Alice có proof mới chưa chắc được chuyển tiền từ tài khoản Bob. Chú ý `validDuration` kiểm *thời điểm proof*, không đặt TTL cho mã OTT chưa được tiêu thụ.

Nếu project thực tế dùng **Spring Security 6.5**: không có `@EnableMultiFactorAuthentication`, `FactorGrantedAuthority` hay `AuthorizationManagerFactories.multiFactor()`. Bạn phải tự xây chính sách factor+freshness và tích hợp vào AuthorizationManager/flow login hoặc nâng cấp đúng hệ sinh thái. Tuyệt đối không mô phỏng bằng cách thêm `FACTOR_OTT` vào danh sách authorities do request parameter tự khai.

## 10. Kiểm thử Servlet integration với MockMvc: tách policy test và end-to-end

### 10.1. Ba tầng kiểm thử, mục tiêu khác nhau

| Tầng | Cách tạo trạng thái | Chứng minh được | Không chứng minh được |
| --- | --- | --- | --- |
| **Unit policy test** | Tự dựng factor evidence giả và clock có điều khiển | Rule từ chối khi thiếu/expired/mismatch theo hàm kiểm tra | Không chứng minh password, OTT, WebAuthn thật hoạt động |
| **MockMvc filter-chain test** | `@SpringBootTest` + `@AutoConfigureMockMvc`, login bằng POST/password và OTT thật qua Spring filter chain | Session, CSRF, redirect và factor authorities được tạo/tiêu thụ đúng | Không nhất thiết kiểm SMTP/DB/cluster thật nếu đã mock |
| **Integration/E2E thật** | Browser, test SMTP, shared token DB, reverse proxy, nhiều node | Challenge giao đúng người, replay/race/cross-user/session thực tế | Vẫn cần test unit boundary/freshness chính xác |

**Không dùng `@WithMockUser` hoặc `.with(user("alice"))` làm bằng chứng OTT đã qua**. Chúng tạo mock authentication trực tiếp; hữu ích để kiểm authorization route, nhưng không đi qua `GenerateOneTimeTokenFilter`, `OneTimeTokenService.consume` và logic giao token.

### 10.2. Các bước test password-only

Trong một test Java JUnit/Spring Test, có thể bắt đầu từ:

```java
// Fragment bên trong @SpringBootTest + @AutoConfigureMockMvc,
// đã có @Autowired MockMvc mvc, test UserDetailsService,
// password hợp lệ của "alice", và static imports formLogin(), get(), status().

var loginResult = mvc.perform(formLogin()
        .user("alice")
        .password("password-from-test-fixture"))
        .andReturn();

// Dùng session từ response/login request, không dùng @WithMockUser.
// Sau đó GET/POST route nhạy cảm bằng session này:
// + Assert chưa được thực hiện nghiệp vụ;
// + Assert redirect sang OTT hoặc denial theo policy,
//   không coi mọi status redirect đều là lỗi.
// Password-only không được có đủ hai factor.
```

Đây là **mã minh họa trong test class**; ví dụ cần fixture password thực, import static Spring Security Test và session handling theo version, không phải bài test độc lập. Nếu test đã được framework pre-authorized/Authenticated từ helper, nó có thể bỏ qua chính luồng chúng ta đang đo.

### 10.3. Các bước test OTT thật, không dùng lại mã

1. Thêm `TestOneTimeTokenGenerationSuccessHandler` chỉ trong test, đưa magic link đến fake inbox gắn account, không in token.
2. Gửi `POST /ott/generate` với `username=alice` và CSRF token qua browser/session A; lấy OTT T_A từ inbox giả.
3. `GET /login/ott?token=T_A`; kiểm tra trang GET **không tạo proof**; nếu cần, kiểm tra DB token chưa bị tiêu thụ.
4. `POST /login/ott` với form `token=T_A` + CSRF trong flow đúng; xác nhận `Authentication.getName()=alice`, có factor OTT và request tiếp theo có session/cookie được lưu phù hợp.
5. Mở browser/session B chưa authenticated, `POST /login/ott` với **cùng T_A** + CSRF mới; phải bị từ chối và không tạo authentication cho B.
6. Lặp lại với T_B của account Bob trong browser Alice: nếu flow đang hoàn thiện MFA cho Alice thì không được thêm proof Bob vào Alice. Test cả sự thay đổi principal sau phản hồi, không chỉ HTTP status.
7. Với JDBC/shared store, chạy hai request T_A đồng thời từ hai session rồi assert **đúng một** consume success. Kiểm tra database trạng thái token sau test.

### 10.4. Ví dụ MockMvc: CSRF/HTTP method

Trong test đã có `MockMvc mvc` và import `post`, `csrf`, `status`:

```java
// Missing CSRF: chỉ chứng minh CSRF filter từ chối.
mvc.perform(post("/ott/generate")
        .param("username", "alice"))
   .andExpect(status().isForbidden());

// Có CSRF mới có thể tới GenerateOneTimeTokenFilter.
// Expected status cụ thể tùy custom success handler:
// mvc.perform(post("/ott/generate")
//         .with(csrf())
//         .param("username", "alice"))
//    .andExpect(status().is3xxRedirection());
```

Không dùng test 403 do CSRF fail để nói “MFA đã từ chối yếu tố hết hạn”: đó là một **lỗi ở tầng khác**. Khi test expiry/replay, phải đảm bảo CSRF hợp lệ và token thực sự đi tới authentication provider/service rồi mới assert lỗi MFA.

### 10.5. Assert cả quyền và side effect

Với hành động thanh toán trong test, nếu request bị deny cần assert **bảng payments không thêm bản ghi**, không phát event/đơn hàng, không chạy payment processor. Một HTTP redirect 302 có thể có body hoặc message; chỉ kiểm status mà quên side effect có thể bỏ sót bug controller chạy trước rule. Spring filter chain phải chặn **trước** business side effect.

## 11. Java 17 độc lập: bộ test tự chạy cho bốn nhóm lỗi

Lưu thành `MfaNegativeCasesDemo.java`. Ví dụ dưới đây là **mô hình trạng thái MFA thu nhỏ**: nó mô phỏng password evidence + token thứ hai, nonce ngẫu nhiên, TTL, freshness, one-time atomic consume, session và principal binding. Dùng JDK 17+, không phụ thuộc Spring. Nó không kiểm chứng password thật, không gửi OTP/email và **không thay thế** authentication flow, database hoặc Spring `SecurityContext` production.

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class MfaNegativeCasesDemo {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Duration TOKEN_TTL = Duration.ofMinutes(5);
    private static final Duration PASSWORD_FRESH = Duration.ofMinutes(30);
    private static final Duration OTT_FRESH = Duration.ofMinutes(2);

    record Challenge(String account, String session, long epoch,
                     Instant expiresAt) {}

    // Đây là fake token store của một JVM, không phải database.
    private static final ConcurrentHashMap<String, Challenge> PENDING =
            new ConcurrentHashMap<>();

    static String randomToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    static boolean fresh(Instant proof, Duration maxAge, Instant now) {
        return proof != null
                && !now.isBefore(proof)
                && now.isBefore(proof.plus(maxAge));
    }

    static final class BrowserSession {
        private final String sessionId;
        private String account;
        private long epoch;
        private Instant passwordAt;
        private Instant ottAt;

        BrowserSession(String sessionId) {
            this.sessionId = sessionId;
        }

        synchronized void passwordLogin(String id, Instant now) {
            // Nhập username/password của một user khác là identity switch.
            if (!Objects.equals(this.account, id)) {
                this.account = id;
                this.epoch++;
                this.passwordAt = null;
                this.ottAt = null;
            }
            this.passwordAt = now;
        }

        synchronized String issueOtt(Instant now) {
            if (this.account == null) {
                throw new IllegalStateException("No account in session");
            }
            String token = randomToken();
            PENDING.put(token, new Challenge(this.account,
                    this.sessionId, this.epoch, now.plus(TOKEN_TTL)));
            return token;
        }

        synchronized boolean submitOtt(String token, Instant now) {
            Challenge proof = PENDING.get(token);
            if (proof == null
                    || !Objects.equals(proof.account(), this.account)
                    || !proof.session().equals(this.sessionId)
                    || proof.epoch() != this.epoch) {
                return false;
            }
            if (!now.isBefore(proof.expiresAt())) {
                PENDING.remove(token, proof);
                return false;
            }
            // Atomic compare-and-remove: chỉ một request thắng.
            if (!PENDING.remove(token, proof)) {
                return false;
            }
            this.ottAt = now;
            return true;
        }

        synchronized boolean canPerformSensitiveAction(Instant now) {
            return this.account != null
                    && fresh(this.passwordAt, PASSWORD_FRESH, now)
                    && fresh(this.ottAt, OTT_FRESH, now);
        }

        synchronized void switchIdentity(String nextAccount) {
            this.account = nextAccount;
            this.epoch++; // pending challenge cũ không còn hợp lệ
            this.passwordAt = null;
            this.ottAt = null;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Instant t0 = Instant.parse("2026-11-06T00:00:00Z");
        BrowserSession alice = new BrowserSession("browser-A");
        alice.passwordLogin("alice", t0);

        System.out.println("missingOtt=" +
                alice.canPerformSensitiveAction(t0));

        String expired = alice.issueOtt(t0);
        System.out.println("expiredToken=" +
                alice.submitOtt(expired, t0.plusSeconds(301)));

        String valid = alice.issueOtt(t0.plusSeconds(10));
        System.out.println("validToken=" +
                alice.submitOtt(valid, t0.plusSeconds(20)));
        System.out.println("bothFresh=" +
                alice.canPerformSensitiveAction(t0.plusSeconds(21)));
        System.out.println("replay=" +
                alice.submitOtt(valid, t0.plusSeconds(22)));
        System.out.println("staleFactor=" +
                alice.canPerformSensitiveAction(t0.plusSeconds(180)));

        BrowserSession bob = new BrowserSession("browser-B");
        bob.passwordLogin("bob", t0);
        String bobsToken = bob.issueOtt(t0);
        System.out.println("otherIdentityToken=" +
                alice.submitOtt(bobsToken, t0.plusSeconds(30)));

        String alicePending = alice.issueOtt(t0.plusSeconds(30));
        alice.switchIdentity("bob");
        System.out.println("afterIdentitySwitch=" +
                alice.canPerformSensitiveAction(t0.plusSeconds(31)));
        System.out.println("oldChallengeAfterSwitch=" +
                alice.submitOtt(alicePending, t0.plusSeconds(32)));

        BrowserSession carol = new BrowserSession("browser-C");
        carol.passwordLogin("carol", t0);
        String shared = carol.issueOtt(t0);
        CountDownLatch begin = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger accepted = new AtomicInteger();
        Runnable attempt = () -> {
            try {
                begin.await();
                if (carol.submitOtt(shared, t0.plusSeconds(1))) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };
        new Thread(attempt).start();
        new Thread(attempt).start();
        begin.countDown();
        done.await();
        System.out.println("concurrentSuccess=" + accepted.get());
    }
}
```

Biên dịch và chạy:

```bash
javac MfaNegativeCasesDemo.java
java MfaNegativeCasesDemo
```

Stdout dự kiến là **xác định** vì test dùng thời gian cố định và in Boolean/đếm, không in secret/token ngẫu nhiên:

```text
missingOtt=false
expiredToken=false
validToken=true
bothFresh=true
replay=false
staleFactor=false
otherIdentityToken=false
afterIdentitySwitch=false
oldChallengeAfterSwitch=false
concurrentSuccess=1
```

Giải thích kết quả:

- `missingOtt=false` dù password đã thành công, policy nhạy cảm vẫn cần factor thứ hai.
- `expiredToken=false` ở 301 giây: mã OTT quá TTL 5 phút.
- `validToken=true` chứng minh token hợp lệ được dùng đúng **một lần**; `bothFresh=true` ở 21 giây.
- `replay=false`: mã đã bị xóa không thể nộp lần hai. Lần replay không có nghĩa session đang xác thực tự động bị thu hồi; đó là quyết định incident policy riêng.
- `staleFactor=false` ở giây 180: password vẫn mới 30 phút nhưng OTT proof thành công ở giây 20 đã quá cửa sổ 2 phút.
- `otherIdentityToken=false`: token của Bob/session B không được cộng vào evidence của Alice/session A.
- `afterIdentitySwitch=false`: đổi principal Bob xóa cả password và OTT evidence cũ.
- `oldChallengeAfterSwitch=false`: pending token của Alice không còn dùng cho Bob trong cùng browser.
- `concurrentSuccess=1`: hai thread cùng submit một token trong một JVM, chỉ một remove thành công.

**Không suy rộng quá mức:** thread lock trong code demo là mô hình của **một session trong JVM**; production nhiều node/DB phải bảo đảm atomicity bằng transaction/unique constraint/conditional update. Token trong demo được map ở dạng raw string để dễ quan sát; production nên hạn chế exposure, có hash at rest, TTL cleanup và thiết kế phân phối token an toàn. **Dòng `passwordLogin` không kiểm tra mật khẩu thật**: nó giả định một bước password authentication đã pass và chỉ phục vụ test state machine.

## 12. Kiểm thử chuyển danh tính trong hệ thống thật

Để tránh test giả, nên tổ chức fixture có **hai account độc lập** với ID ổn định:

| Account | Password | Kênh yếu tố 2 | Role/tenant |
| --- | --- | --- | --- |
| Alice | Test password của Alice | Inbox A / credential A | ROLE_USER, tenant A |
| Bob | Test password của Bob | Inbox B / credential B | ROLE_USER, tenant B |
| Admin | Test password admin | Inbox admin / passkey admin | ROLE_ADMIN, tenant A |

Test cụ thể:

1. Login password Alice trong session A; tạo pending OTT Alice.
2. Tạo OTT Bob trong session B. Submit OTT Bob ở session A. Kỳ vọng: **không** cấp factor cho Alice; không tạo phiên Bob như thể đó là step 2 của Alice. Audit phải ghi lỗi wrong-account/transaction một cách an toàn.
3. Alice hoàn thành MFA với OTT Alice; assert quyền với resource Alice. Chuyển session A sang Bob bằng logout/login hoặc chức năng switch-user được phép, rồi gọi endpoint yêu cầu MFA. Kỳ vọng: **không** còn factor cũ áp dụng cho Bob.
4. Thử gửi pending OTT Alice cũ sau switch. Kỳ vọng: không thêm factor Bob. Nếu OTP service chỉ ràng buộc user chứ không ràng buộc session, test phải tách rõ đó là luồng đăng nhập riêng hay step-up cho current user.
5. Đối với `SwitchUserFilter` admin impersonation: verify chỉ admin có quyền switch, original authentication được quản lý theo filter, và **factor requirements được đánh giá theo principal/actor phù hợp**; không mặc nhiên coi OTT của admin là proof của user bị impersonate.
6. Logout cả hai session, thử refresh cookie/session cố định cũ; không được tự “khôi phục” factor evidence từ cache.
7. Đặt hai request race: POST OTT Alice và switch session sang Bob, rồi kiểm tra kết quả cuối cùng không bao giờ là Bob với factor OTT của Alice.

**Phản ví dụ nguy hiểm:** request handler chỉ dùng `session.setAttribute("mfaPassed", true)`. Sau khi user switch, giá trị Boolean vẫn true và Bob có thể vượt MFA. Nếu phải lưu trạng thái trong session, lưu **account ID + factor type + issuedAt + transaction ID/epoch**, kiểm tra lại ở mỗi thao tác quan trọng, đồng thời clear state khi logout/identity switch. Với Spring Security 7, ưu tiên factor-aware authorization tích hợp thay cho Boolean tùy tiện.

## 13. Cách tổ chức test để tránh false positive

### Phân biệt “deny do MFA” với “deny do thứ khác”

Khi muốn test yếu tố hết hạn, dùng request có **CSRF hợp lệ**, account đúng role, business object đúng owner, session hợp lệ và token đi đến đúng handler. Nếu không, test có thể trả 403 vì thiếu CSRF/role, làm bạn tưởng MFA expiration đang hoạt động. Đặt assertions về event/log reason (không in secret), token consumption và data side effects.

### Đồng hồ có điều khiển

Không dùng `Thread.sleep` chờ token hết hạn trong CI. Hãy dùng injectable `Clock`/fake token store/fixed Instant hoặc điều chỉnh factor `issuedAt` ở unit test cho `RequiredFactor.validDuration`. Integration test thực tế cần xác nhận library version đang dùng có đúng clock semantics. Kiểm trường hợp `expiry.minusNanos(1)`, `expiry` và `expiry.plusNanos(1)` nếu được hỗ trợ.

### Browser/session tách biệt

Một browser đang authenticated có thể nhận 200 dù bạn gửi lại link sai, chỉ vì **session cũ** vẫn còn hợp lệ. Luôn có browser chưa authenticated hoặc session khác để kiểm replay login. Test factor mixing phải dùng **hai account và hai inbox**, không dùng mỗi Alice.

### Concurrency thật

JDBC/cluster race cần song song ở mức request và transaction DB; `synchronized` ở một object test không chứng minh toàn hệ thống. Đo chính xác số session mới và số lần tiêu thụ thành công, không chỉ số lần HTTP 302. Cấu hình retry/redirect ở client test không được làm biến dạng số yêu cầu.

### Hiệu ứng nghiệp vụ

Dù MFA fail, hệ thống không được thực hiện payment, đổi email hay quản lý user. Đặt assertion “không có side effect” song song assertion HTTP response. Lưu ý role/tenant/resource ownership tách khỏi xác thực factor.

### Security context lifecycle

Trên Spring Security 6/7, một custom authentication filter tự đặt SecurityContext còn phải lưu đúng theo `SecurityContextRepository` nếu muốn persist qua request; thay đổi principal phải thay/reset state phù hợp. Session fixation protection, concurrent session control, logout và cache invalidation cần integration test cùng authentication flow. Không để một partial authentication bị “đóng băng thành full MFA” trong session cũ.

## 14. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Password-only vẫn vào endpoint admin | Chỉ kiểm `authenticated()`/role; thiếu rule factor | Dùng Spring 7 MFA factory hoặc custom factor-aware authorization |
| Bật form+OTT nhưng không yêu cầu hai factor | Hai cơ chế tồn tại chỉ như **các cách login thay thế** | Khai báo yêu cầu MFA rõ trên route |
| Token OTT hết hạn nhưng vẫn được chấp nhận | Store không kiểm expiresAt hoặc clock sai | Assert expired challenge tại/sau TTL |
| Mã OTT đã consume vẫn tạo thêm session | Store không atomic; race trong JDBC/cluster | Update bản vá và test hai requests song song |
| GET magic link tiêu thụ token | Custom handler tự login bằng GET | Giữ GET display, POST consume, có CSRF |
| Authority tồn tại mãi dù factor cũ | Check tên authority thay vì `issuedAt+validDuration` | Dùng `RequiredFactor.validDuration` theo route |
| User Bob có đủ factor của Alice | Không kiểm stable principal/tenant/transaction khi cộng proof | Bind proof vào account+session/epoch, clear khi switch |
| Test replay vẫn trả 200 | Test dùng session đã authenticated trước | Dùng session mới và assert token store |
| Unit test pass nhưng production fail | `@WithMockUser` bỏ qua OTP provider và email | Chạy integration test với filter/service thật |
| Test expired fail vì CSRF trước | Thiếu `csrf()` khiến request chưa đến provider | Cấp CSRF hợp lệ rồi mới assert expiry |
| Token nằm trong logs/referrer | Magic link query bị log đầy đủ, script bên thứ ba | HTTPS, policy referrer, mask token, hạn TTL |
| MFA pass nhưng user đọc data người khác | Nhầm authentication và authorization | Assert role/tenant/object ownership riêng |
| Đổi user vẫn thấy full MFA | Boolean `mfaPassed` lưu trong session | Xóa/kiểm lại factor theo principal và generation |
| Multi-pod dùng InMemory OTT store | Token tạo ở A không có ở B | Dùng shared store có atomic consume |
| Spring 6.5 không biên dịch API FactorGrantedAuthority | API MFA gốc giới thiệu từ 7.0 | Nâng version tương thích hoặc dùng custom MFA policy |
| Factor validDuration không cho route như mong muốn | Clock/policy/time window sai, required factors bị áp dụng toàn cục | So sánh rules, test trước/sau boundary và endpoint |
| Session thay đổi ID khiến OTP mất | Session fixation migration hoặc cookie/path | Kiểm tra session persistence, transaction binding và redirect |
| Chưa kiểm account locked/disabled lúc factor 2 | Chỉ tin OTT token tồn tại | Enforce account state và recheck quyền khi hoàn thành |

## 15. Checklist chấp nhận

Một hệ thống có MFA được kiểm thử đầy đủ khi:

- [ ] **Thiếu yếu tố:** password-only và OTT-only bị chặn ở route cần hai factor; route public/dashboard vẫn đúng chính sách.
- [ ] **Độ mới:** phân biệt TTL của mã chưa dùng và freshness của proof đã xác minh; boundary trước/đúng/sau expiry có test deterministic.
- [ ] **Replay:** mã OTT/TOTP/challenge đã dùng không tăng quyền lần nữa; hai concurrent requests không thể cùng tiêu thụ.
- [ ] **Chuyển danh tính:** Alice factor không trở thành Bob factor, kể cả session switch, logout, impersonation hoặc request race.
- [ ] **Principal/tenant:** cùng stable identity với transaction hiện hành; user khác hoặc tenant khác bị từ chối.
- [ ] **CSRF/session:** test POST với CSRF hợp lệ, browser cookie đúng, session fixation/logout/re-auth được kiểm riêng.
- [ ] **Role/ownership:** đủ MFA nhưng không đủ role/resource permission vẫn bị từ chối.
- [ ] **Quan sát:** có audit events về missing/stale/replayed/mismatch nhưng không log raw OTP/token/PII nhạy cảm.
- [ ] **Spring version:** ví dụ built-in dùng Spring Security 7.x; dự án 6.x không bị áp sai API.
- [ ] **E2E:** có kiểm thử thực với email/OTP/WebAuthn provider, database dùng chung, nhiều instance và concurrency.

**Nguyên tắc gói gọn:** Đừng chỉ hỏi “user có authenticated không?” mà hãy hỏi **“đúng user này đã cung cấp đủ các yếu tố được yêu cầu, đủ mới, chưa từng sử dụng lại, và chứng cứ có thuộc đúng giao dịch/phiên đang được kiểm tra không?”**. Sau đó vẫn cần kiểm authorization cho tài nguyên.

### Tài liệu tham khảo

- [Spring Security — Multi-Factor Authentication (Servlet, Spring Security 7.x)](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html)
- [Spring Security 7.0 — What's New (MFA support)](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Spring Security API — EnableMultiFactorAuthentication (since 7.0)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html)
- [Spring Security API — FactorGrantedAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html)
- [Spring Security API — AuthorizationManagerFactories](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagerFactories.html)
- [Spring Security — One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security — Authentication Persistence / Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — MockMvc Authentication Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — SwitchUserFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/switchuser/SwitchUserFilter.html)
- [Spring Security — CVE-2026-22751 (JDBC OTT concurrent use)](https://spring.io/security/cve-2026-22751/)
- [RFC 6238 — Time-Based One-Time Password Algorithm (TOTP)](https://www.rfc-editor.org/rfc/rfc6238)
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226)
