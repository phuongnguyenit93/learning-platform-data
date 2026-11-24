# Absolute timeout: giới hạn thời gian sống tối đa của phiên trong IAM

Một nhân viên mở ứng dụng quản trị lúc 09:00. Ứng dụng cấu hình **idle timeout 15 phút**, nhưng mỗi lần người dùng di chuyển chuột, gửi request hoặc gia hạn phiên, đồng hồ không hoạt động lại được đặt về 15 phút. Người này sử dụng liên tục đến 23:00 và vẫn giữ được phiên quản trị từ sáng. Nếu thiết bị đã bị chiếm quyền hoặc cookie phiên bị lộ, cơ chế chỉ dựa vào thời gian không hoạt động có thể kéo dài cửa sổ truy cập rất lâu.

**Absolute timeout** (thời hạn tuyệt đối của phiên) đặt **giới hạn trên cho tuổi thọ của một phiên**, được tính từ một mốc khởi đầu được định nghĩa rõ, **bất kể người dùng có tiếp tục hoạt động hay không**. Hết thời hạn này, phiên phải **không còn được hệ thống chấp nhận** theo chính sách; muốn tiếp tục truy cập, chủ thể cần một quy trình xác thực/thiết lập phiên mới phù hợp. Absolute timeout bổ sung cho **idle timeout**, không thay thế các kiểm soát **thu hồi theo sự kiện Joiner–Mover–Leaver, phát hiện rủi ro, phân quyền và xác thực mạnh**.

Bài thuộc chương **Session management**, chủ đề trực tiếp **Absolute timeout**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun nghiên cứu quản lý vòng đời danh tính **Joiner–Mover–Leaver**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi khi đổi vai trò; có liên hệ **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

Sau bài học, người học có thể:

- Định nghĩa chính xác **absolute timeout**, phân biệt với **idle timeout, token expiration, refresh token lifetime, cookie lifetime, reauthentication interval và session revocation**.
- Thiết kế **deadline không trượt theo hoạt động**, tính ở server/điểm thực thi thay vì chỉ dựa vào JavaScript timer hoặc cookie ở browser.
- Phân tích nhiều phiên/lớp trong **IdP–SSO–ứng dụng**, OAuth 2.0/OIDC, web/API/mobile và nền tảng phân tán.
- Xử lý **absolute timeout đồng thời với idle timeout, token rotation, JIT/PAM, MFA step-up, risk-based access và device trust**.
- Xác minh **Leaver, Mover, tài khoản máy, account disable, logout-all và sự kiện quyền thay đổi** có thể chấm dứt hoặc giảm quyền **trước deadline tuyệt đối**.
- Xây dựng **policy, mô hình dữ liệu, pseudocode, ma trận kiểm thử, tình huống thực tế và chỉ số kiểm toán** để chứng minh phiên thực sự hết hiệu lực.

## 1. Absolute timeout là gì và vì sao cần có?

Một phiên đăng nhập (session) là trạng thái bảo mật cho phép hệ thống liên kết các request tiếp theo với một chủ thể đã được xác thực và bối cảnh tương ứng. Tùy kiến trúc, phiên có thể nằm ở **IdP**, **ứng dụng**, **API gateway**, **BFF (Backend for Frontend)**, **PAM** hoặc trong một cơ chế token.

**Absolute timeout** định nghĩa một mốc cố định cho **phiên cụ thể**:

~~~text
sessionCreatedAt = 09:00
absoluteLifetime = 8 giờ              # ví dụ minh họa, không phải ngưỡng chung
absoluteExpiresAt = 17:00

09:05 request hợp lệ
10:00 request hợp lệ
16:59 request hợp lệ
17:00 trở đi: phiên cũ không còn hợp lệ theo policy
~~~

Các request hợp lệ trong ngày **không được đẩy absoluteExpiresAt từ 17:00 thành một thời điểm muộn hơn**. Nếu hệ thống cho phép xác thực lại và tạo phiên mới, phiên mới có **mốc bắt đầu, identifier, bằng chứng xác thực và deadline riêng**, thay vì âm thầm kéo dài phiên cũ vô hạn.

### 1.1. Rủi ro mà absolute timeout giúp hạn chế

- **Phiên chiếm đoạt kéo dài:** cookie/session ID/token bị đánh cắp có thể tiếp tục được sử dụng lâu nếu chỉ kiểm idle và kẻ tấn công hoạt động đều.
- **Tài khoản dùng chung/thiết bị bỏ quên:** trình duyệt mở suốt nhiều giờ mà không buộc kiểm lại danh tính.
- **Assurance suy giảm theo thời gian:** bằng chứng xác thực lúc đầu không nên được coi hợp lệ vô hạn cho mọi tác vụ.
- **Quyền hoặc ngữ cảnh thay đổi:** vai trò, hợp đồng, device posture và risk có thể đổi trong lúc phiên hoạt động.
- **Session fixation/refresh kéo dài:** cơ chế sliding expiration có thể vô tình làm phiên tồn tại không giới hạn.

Absolute timeout **giảm giới hạn phơi lộ theo thời gian**, nhưng không ngăn mọi tấn công: một cookie bị lấy cắp vẫn có thể bị lạm dụng **trước deadline** nếu thiếu các kiểm soát khác.

### 1.2. Mốc khởi đầu phải được định nghĩa chính xác

Một hệ thống phải xác định tuyệt đối timeout tính từ:

1. **Phiên ứng dụng được tạo** sau xác thực thành công.
2. **Lần xác thực đầy đủ gần nhất** được chính sách chấp nhận.
3. **Lần kích hoạt quyền đặc biệt (privileged activation)** đối với phiên PAM/JIT riêng.

Không nên trộn các mốc tùy tiện. Ví dụ, session ứng dụng tạo lúc 10:00 trên nền IdP đã xác thực lúc 08:00 có thể phải tuân thủ **cả deadline của IdP và deadline riêng của ứng dụng** theo kiến trúc; không tự giả định hai phiên có cùng thời hạn.

## 2. Phân biệt absolute timeout với các bộ đếm khác

| Cơ chế | Khi nào hết hạn? | Hoạt động mới có gia hạn không? | Bảo vệ chính |
| --- | --- | --- | --- |
| **Idle timeout** | Quá khoảng không có hoạt động hợp lệ. | Có thể cập nhật theo hoạt động được phép. | Người dùng bỏ quên phiên. |
| **Absolute timeout** | Tới deadline cố định tính từ sự kiện khởi đầu. | **Không**, nếu chỉ có request thường/refresh. | Phiên tồn tại quá lâu. |
| **Access token expiration** | `exp` của token hoặc quy tắc token tương đương. | Không đổi token cũ; có thể nhận token mới. | Giới hạn thời gian chấp nhận một token. |
| **Refresh token expiration** | Refresh token/family hết hạn hoặc bị thu hồi. | Tùy loại: có thể rotation, idle và hard cap riêng. | Giới hạn cơ chế cấp access token mới. |
| **Cookie Max-Age/Expires** | Trình duyệt bỏ hoặc ngừng gửi cookie theo quy tắc cookie. | Ứng dụng có thể set lại cookie. | Vòng đời lưu trữ cookie phía client. |
| **Reauthentication interval** | Yêu cầu xác thực lại sau một khoảng hoặc sự kiện. | Chỉ sự kiện reauth hợp lệ mới đáp ứng. | Làm mới mức đảm bảo người dùng. |
| **Privilege elevation TTL** | Vai trò/quyền đặc biệt hết hạn. | Chỉ gia hạn theo chính sách JIT/PAM. | Giảm thời gian đặc quyền. |
| **Event-driven revocation** | Sự kiện Leaver, nghi lộ credential, mất thiết bị, admin revoke... | Không phụ thuộc timeout định kỳ. | Chấm dứt truy cập khi nguy cơ thay đổi. |

**Quan trọng:** Có access token 5 phút **không đồng nghĩa session absolute timeout là 5 phút** nếu refresh token có thể liên tục cấp token mới trong nhiều ngày. Ngược lại, session application có absolute lifetime 8 giờ không làm access token đã cấp trở nên tự động vô hiệu lúc giờ thứ 8 trừ khi **resource server thực thi ràng buộc tương ứng**.

### 2.1. Idle timeout là sliding window; absolute timeout là hard deadline

~~~text
sessionCreatedAt = 09:00
idleTimeout      = 15 phút
absoluteTimeout  = 8 giờ

09:00  authenticated
09:10  request hợp lệ -> idle deadline = 09:25
09:20  request hợp lệ -> idle deadline = 09:35
16:50  request hợp lệ -> idle deadline = 17:05

Effective expiry = min(idleDeadline=17:05, absoluteDeadline=17:00)
                 = 17:00
~~~

Thời điểm ví dụ là giả định. Nếu user không hoạt động từ 09:20, phiên hết vì **idle 09:35**, không cần chờ absolute 17:00.

### 2.2. Không nên nhầm browser session cookie với server session

Một cookie **không có Expires/Max-Age** thường được gọi là *session cookie* và trình duyệt có cơ chế lưu theo browser session. Điều đó **không phải bằng chứng** ứng dụng sẽ chặn request sau thời hạn tuyệt đối. Trình duyệt có thể khôi phục session theo chế độ hoạt động và cookie bị chiếm đoạt có thể được gửi bằng client khác. **Deadline phải được xác minh tại server/PEP**.

## 3. Ba điều kiện cần để absolute timeout thực sự có hiệu lực

### 3.1. Mốc hết hạn bất biến theo request thông thường

Hệ thống lưu `createdAt`/`authenticatedAt` và `absoluteExpiresAt`, trong đó `absoluteExpiresAt` **không tự động thay đổi khi user tiếp tục hoạt động**.

~~~text
session.id = randomOpaqueSessionId
session.createdAt = 2026-12-01T09:00:00+07:00
session.absoluteExpiresAt = 2026-12-01T17:00:00+07:00
session.lastActivityAt = 2026-12-01T09:00:00+07:00

onValidActivity:
    update lastActivityAt only
    do not update absoluteExpiresAt
~~~

### 3.2. Kiểm hạn tại điểm chấp nhận request

Server/API/PEP phải từ chối phiên đã hết hạn **trước khi xử lý một tác vụ cần xác thực**. Không dựa duy nhất vào thông báo UI, bộ đếm chạy ở browser hoặc việc trình duyệt xóa cookie.

### 3.3. Sau hết hạn, credential cũ không còn mở lại cùng phiên

Nếu session ID đã hết hạn nhưng một API “renew” trả lại **session ID có deadline mới** mà không qua chính sách xác thực/thiết lập phiên mới, absolute timeout đã bị vô hiệu trên thực tế.

**Bất biến:** Request thường, heartbeat và token refresh trong cùng một phiên **không thể làm hard deadline dịch về sau** nếu policy chưa định nghĩa một sự kiện reauthentication/new-session hợp lệ.

## 4. Công thức hiệu lực của nhiều timeout

Một phiên có thể bị chặn bởi **nhiều deadline và sự kiện**. Ví dụ:

~~~text
now = server time

idleExpiresAt       = lastMeaningfulActivityAt + idleLifetime
absoluteExpiresAt   = sessionStartAt + absoluteLifetime
privilegeExpiresAt  = privilegedActivationAt + elevationLifetime
accountEndAt        = authoritativeEngagementEndAt (nếu áp dụng)

sessionValid =
    now < idleExpiresAt
    AND now < absoluteExpiresAt
    AND not revoked
    AND subject eligibility still permits requested action
    AND device / risk / authorization policy passes

privilegedActionValid =
    sessionValid
    AND now < privilegeExpiresAt
    AND privileged role is still effective
~~~

Đây là **logic minh họa**. Một số session áp dụng các policy khác và có thời gian grace/retry được thiết kế riêng, nhưng phải **định nghĩa rõ** và không để grace lén kéo dài khả năng thao tác nhạy cảm.

### 4.1. Deadline hiệu lực

Với trường hợp các hạn đều là ràng buộc bắt buộc, có thể mô tả:

\[
T_{\mathrm{end}} = \min(T_{\mathrm{idle}}, T_{\mathrm{absolute}},
T_{\mathrm{privileged}}, T_{\mathrm{other\ applicable\ deadlines}})
\]

Phép `min` chỉ mô tả **những deadline thực sự áp dụng cho cùng hành động**. Ví dụ, `T_privileged` hết hạn có thể chỉ chặn thao tác admin, **không bắt buộc chấm dứt toàn bộ phiên đọc tài liệu**.

### 4.2. Quyền thay đổi là một điều kiện, không chỉ là deadline

Leaver hoặc khóa account không nên chờ tới `absoluteExpiresAt`. Một sự kiện thu hồi có hiệu lực tại `t_revoke` phải làm PEP chặn theo thời điểm/độ trễ mà hệ thống công bố. **Tuyệt đối timeout là giới hạn thời gian dự phòng, không thay điều kiện thu hồi theo sự kiện**.

## 5. Ví dụ dòng thời gian: so sánh idle và absolute

Giả sử policy minh họa:

~~~text
Session created:       09:00
Idle timeout:          30 phút
Absolute timeout:      8 giờ
Absolute expires:      17:00
~~~

| Mốc | Hành vi | Kết quả mong đợi |
| --- | --- | --- |
| **09:00** | Đăng nhập đầy đủ. | Tạo session, chốt absolute deadline 17:00. |
| **09:10** | Mở trang hợp lệ. | lastActivity 09:10, idle deadline 09:40. |
| **09:35** | Thao tác tiếp. | Idle deadline 10:05, absolute vẫn 17:00. |
| **12:00** | Nếu không có hoạt động từ 09:35. | Session hết từ 10:05 do idle. |
| **16:50** | Giả sử có hoạt động liên tục hợp lệ đến đây. | Idle có thể tới 17:20, absolute vẫn 17:00. |
| **16:59** | API request hợp lệ. | Có thể xử lý nếu đáp ứng tất cả điều kiện khác. |
| **17:00** | Thử request bằng cookie/token/session cũ. | Từ chối do absolute timeout. |
| **17:01** | Người dùng xác thực lại hợp lệ. | Có thể tạo **session mới** với deadline mới. |

### 5.1. Một request bắt đầu trước deadline nhưng hoàn tất sau deadline

Chính sách phải xác định **enforcement tại thời điểm nào**:

- **Request nhỏ:** kiểm session khi xử lý authorization; nếu lúc kiểm đã hết hạn thì từ chối.
- **Tác vụ dài/stream/download:** có thể cần giới hạn phiên stream, recheck trong quá trình xử lý hoặc authorization riêng cho job dài.
- **Giao dịch nhạy cảm:** có thể cần revalidation ngay trước commit, đặc biệt khi quyền/JML/risk thay đổi.

Không có quy tắc chung buộc mọi HTTP response đang truyền phải bị cắt chính xác tới từng mili giây khi absolute deadline đến. Nhưng **không được cho phép các thao tác nhạy cảm mới vượt deadline mà không kiểm theo policy**.

## 6. Chọn thời hạn tuyệt đối theo rủi ro

Không tồn tại một con số `absoluteTimeoutMinutes` phù hợp mọi ứng dụng. Thời hạn phải được xác định từ:

- **Mức nhạy cảm tài nguyên:** dữ liệu public, PII, tài chính, production admin, secrets.
- **Mức quyền của phiên:** đọc, giao dịch tiền, quản trị IAM, thay policy, xuất dữ liệu.
- **Phương thức xác thực:** MFA/phishing-resistant, reauth khả dụng, khả năng nhận diện device.
- **Môi trường sử dụng:** kiosk/shared device, BYOD, managed/compliant, VDI, mobile, server.
- **Tần suất và thời lượng tác vụ:** ca trực, vận hành khẩn, giao dịch nhiều bước.
- **Khả năng thu hồi hiện hữu:** IdP token, SP session, API, PAM, ứng dụng offline.
- **Quy định/chính sách áp dụng:** yêu cầu về thời hạn xác thực, quản trị đặc quyền và audit.

### 6.1. Policy nhiều cấp

| Risk tier (minh họa) | Quy tắc mô tả | Điều cần tránh |
| --- | --- | --- |
| **LOW** | Phiên có giới hạn tuyệt đối phù hợp trải nghiệm, vẫn kiểm role/user. | Phiên không hard cap. |
| **MEDIUM** | Hard cap chặt hơn và idle timeout hợp lý. | Refresh vô hạn hoặc chỉ logout UI. |
| **HIGH** | Hard cap ngắn hơn, reauth/step-up cho thao tác nhạy cảm. | Chỉ dùng cookie expiry. |
| **PRIVILEGED** | Giới hạn phiên PAM/JIT, credential/session theo task. | Nắm standing admin và tự gia hạn elevation không kiểm. |
| **EMERGENCY** | Cơ chế continuity riêng, time-bound, alert và hậu kiểm. | Mở admin vô thời hạn vì IdP outage. |

Tất cả ví dụ chỉ có tính **định hướng**, không định ra số phút chung. **Thời hạn càng ngắn không tự động càng an toàn** nếu tạo vòng lặp đăng nhập, thúc đẩy chia sẻ credential hoặc buộc người dùng lưu token ngoài kiểm soát.

### 6.2. Cần tách session assurance và access authorization

Việc session còn trong hard cap **không có nghĩa** người dùng giữ mãi mọi quyền. RBAC/ABAC, SoD, trạng thái account, device posture và policy vẫn có thể dẫn đến DENY ngay khi một hành động mới được yêu cầu.

## 7. Mô hình vòng đời một phiên

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> ACTIVE: Authentication + policy pass
    ACTIVE --> ACTIVE: Valid activity (idle clock only)
    ACTIVE --> STEP_UP_REQUIRED: Sensitive action / higher assurance
    STEP_UP_REQUIRED --> ACTIVE: Successful step-up, within allowed session policy
    ACTIVE --> EXPIRED_IDLE: Idle deadline reached
    ACTIVE --> EXPIRED_ABSOLUTE: Absolute deadline reached
    ACTIVE --> REVOKED: Leaver / admin revoke / security event
    ACTIVE --> RESTRICTED: Posture or risk changed
    RESTRICTED --> REVOKED: Risk response
    RESTRICTED --> ACTIVE: Re-evaluated according to policy
    EXPIRED_IDLE --> [*]
    EXPIRED_ABSOLUTE --> [*]
    REVOKED --> [*]
~~~

### 7.1. Các trạng thái nên rõ ràng

| Trạng thái | Ý nghĩa | Xử lý request |
| --- | --- | --- |
| **ACTIVE** | Chưa hết hạn, chưa bị thu hồi và các điều kiện còn đạt. | Tiếp tục kiểm authorization từng hành động. |
| **EXPIRED_IDLE** | Vượt giới hạn không hoạt động. | Không dùng session cũ. |
| **EXPIRED_ABSOLUTE** | Vượt tuổi thọ tối đa. | Không dùng session cũ, kể cả refresh/heartbeat. |
| **REVOKED** | Bị chấm dứt chủ động. | Từ chối theo điểm thực thi và cơ chế revoke. |
| **RESTRICTED** | Rủi ro/posture thay đổi; còn phạm vi hẹp. | Chỉ cho thao tác được policy cho phép. |
| **STEP_UP_REQUIRED** | Cần mức xác thực cao hơn cho thao tác. | Không coi step-up thành công là quyền admin tự động. |

Trong một hệ thống thật, có thể dùng trạng thái khác. Quan trọng là phân biệt **lý do phiên không hợp lệ** để xử lý đúng và audit.

### 7.2. Không tái kích hoạt phiên hết hạn bằng update trạng thái

Nếu session đã `EXPIRED_ABSOLUTE` thì việc client gửi request hoặc backend update `lastSeenAt` không được đưa về ACTIVE. Việc xác thực lại có thể tạo session mới **theo policy**, với mốc chứng cứ mới và session identifier mới được cấp an toàn.

## 8. Server-side session: lưu và kiểm hard deadline

Với ứng dụng dùng **opaque session ID** trong cookie, backend thường giữ trạng thái session ở storage có kiểm soát:

~~~text
SessionRecord
  sessionIdHash
  subjectId
  engagementId
  tenantId
  authenticationTime
  createdAt
  lastMeaningfulActivityAt
  absoluteExpiresAt
  idleLifetime
  authStrength / context
  deviceBindingRef? 
  sessionVersion
  state
  revokedAt?
~~~

### 8.1. Vì sao lưu hash của session ID?

Opaque session identifier phải đủ ngẫu nhiên, khó đoán và được vận chuyển/lưu an toàn. Một số thiết kế **lưu hash của session secret** ở server nhằm giảm rủi ro lộ raw session IDs qua database. Đây là khuyến nghị thiết kế, không áp đặt mọi framework có cùng session-store layout.

### 8.2. Session TTL trong cache khác policy deadline

Redis/cache có thể tự xóa record khi TTL kết thúc. Nhưng:

- Nếu ứng dụng **gia hạn TTL theo request**, record có thể không biến mất ở hard deadline.
- Nếu session state được tái tạo từ refresh token, việc record bị xóa chưa đủ.
- Nếu nhiều cache/replica có bản sao, có thể có trạng thái stale.

**Cache eviction là tiện ích vận hành; authorization check đối chiếu absolute deadline mới là ranh giới bảo mật**.

### 8.3. Lưu policy phiên tại thời điểm tạo

Một session có thể có `absoluteLifetime` phụ thuộc risk tier. Có thể lưu:

~~~json
{
  "sessionIdRef": "sess-ref-8402",
  "subjectId": "person-1042",
  "tenantId": "tenant-a",
  "createdAt": "2026-12-01T09:00:00+07:00",
  "lastMeaningfulActivityAt": "2026-12-01T09:20:00+07:00",
  "absoluteExpiresAt": "2026-12-01T17:00:00+07:00",
  "idleTimeoutSeconds": 1800,
  "riskTier": "HIGH",
  "policyVersion": "session-policy-v7",
  "state": "ACTIVE"
}
~~~

JSON chỉ **minh họa metadata nội bộ**. Không lưu raw cookie/session secret trong báo cáo; có thể dùng ID tham chiếu và chính sách truy xuất hạn chế.

## 9. Idle activity: request nào được tính là hoạt động?

Một lỗi thường gặp: mọi request nền đều làm mới `lastActivityAt`. Các cơ chế sau có thể âm thầm giữ phiên sống:

- Polling dashboard mỗi vài giây.
- Heartbeat hoặc keep-alive từ SPA.
- Fetch thông báo, prefetch/link preview.
- Request telemetry, background synchronization.
- Service worker gọi API khi người dùng đã rời máy.

### 9.1. Quy tắc meaningful activity

Policy cần định nghĩa **hoạt động có ý nghĩa** để làm mới idle timer:

~~~text
meaningfulActivity:
    user-initiated action hợp lệ
    OR tương tác được server xác nhận theo thiết kế

notMeaningfulForIdle:
    background heartbeat
    invisible polling
    analytics request
    token-refresh endpoint chỉ chạy tự động
~~~

**Phân biệt idle với absolute:** dù ứng dụng chọn một định nghĩa khác về meaningful activity, **không hoạt động nào được tự động kéo dài absolute deadline**. Bằng chứng activity từ client cũng cần tránh tin hoàn toàn vào dữ liệu tự khai.

### 9.2. Tránh thời điểm giả do timer trên client

JavaScript trong background tab có thể bị throttle; đồng hồ thiết bị có thể bị chỉnh; app mobile có thể bị suspend. Client timer chỉ giúp **UX** như cảnh báo sắp hết hạn. **Server/PEP là nơi quyết định request được chấp nhận hay không**.

## 10. Bảo vệ session cookie và session identifier

Absolute timeout là một phần của session security, cần kết hợp bảo vệ cookie và định danh phiên:

| Kiểm soát | Tác dụng | Điều không thay thế |
| --- | --- | --- |
| **Secure cookie** | Chỉ gửi qua kết nối bảo mật theo semantics cookie. | Không tự giới hạn tuổi session tại server. |
| **HttpOnly** | Hạn chế JS đọc cookie. | Không ngăn mọi XSS thực thi hành động từ browser. |
| **SameSite** | Giúp giảm một số tình huống cross-site request. | Không thay toàn bộ CSRF defense và authorization. |
| **Host/path/domain scoping** | Giảm phạm vi cookie được gửi. | Không tự ràng buộc quyền tenant/resource. |
| **Random session ID** | Giảm khả năng đoán/fixate ID. | Không ngăn lấy cắp cookie qua endpoint bị chiếm. |
| **Session rotation on authentication** | Giảm nguy cơ fixation khi nâng mức xác thực. | Không thay absolute deadline policy. |
| **Server-side expiry/revoke** | Chặn credential cũ sau deadline/sự kiện. | Cần được kiểm ở mọi đường API liên quan. |
| **TLS/HSTS** | Bảo vệ truyền tải và giảm downgrade theo cấu hình. | Không tự bảo vệ malware ở thiết bị. |

### 10.1. Cookie Max-Age không phải hard cap

Nếu backend gửi lại `Set-Cookie: Max-Age=3600` sau mọi request, expiry phía browser có thể trượt. Đây có thể là cơ chế idle/rolling cookie, nhưng **server vẫn cần absoluteExpiresAt cố định**. Nếu cookie đã bị lấy, browser phía nạn nhân xóa cookie không khiến bản sao phía kẻ tấn công tự mất hiệu lực.

### 10.2. Không tiết lộ session secret trong log

Log và audit không nên chứa raw cookie, session ID, bearer token, refresh token hoặc password. Dùng **session reference có tính riêng tư**, reason codes, issuer/audience, timestamps, policy version và thông tin cần điều tra.

## 11. OAuth 2.0: access token, refresh token và hard cap

Trong OAuth, **access token** cho phép client gọi resource server theo scope/quyền đã cấp; **refresh token** (nếu dùng) có thể giúp client nhận access token mới. Chúng **không mặc định đồng nhất với phiên đăng nhập web**.

### 11.1. Ngộ nhận phổ biến

~~~text
Access token TTL = 10 phút
Refresh token rotation = mỗi lần refresh
Refresh-token family = có thể tồn tại nhiều ngày

Nếu refresh tiếp tục được cho tới vô hạn:
    tuổi access token ngắn không bảo đảm
    session absolute timeout đúng nghĩa.
~~~

Phải xác định **hard deadline** cho cơ chế được gọi là *session*, đồng thời áp policy cho refresh-token family hoặc quyền cấp token mới khi tương ứng.

### 11.2. Giới hạn family tuyệt đối

Một kiến trúc có thể lưu:

~~~text
familyCreatedAt       = 09:00
familyAbsoluteExpires = 17:00
currentRefreshToken   = rotated at 10:00, 11:00, 12:00...

at 16:59:
    refresh có thể thành công nếu policy cho
    token mới không được tạo khả năng truy cập vượt
    hard deadline mà resource/PDP không kiểm

at 17:00:
    không cho refresh trong family cũ
    yêu cầu authorization/reauth phù hợp
~~~

**Quan trọng:** Việc chặn refresh sau 17:00 **không tự làm access token đã phát lúc 16:59 hết hiệu lực ngay** nếu token mang `exp` sau 17:00 và resource server chỉ kiểm `exp`. Muốn hard cap chặt tại resource phải ràng buộc token lifetime về deadline, dùng introspection/session lookup, revocation hoặc enforcement tương ứng.

### 11.3. Refresh token rotation không đồng nghĩa absolute lifetime

Rotation giúp phát hiện/giảm một số rủi ro replay và thay credential, nhưng nếu mỗi refresh được cấp family deadline mới, cơ chế có thể tạo **chuỗi phiên không kết thúc**. Nên phân biệt:

- **Refresh token instance lifetime**.
- **Inactivity timeout của refresh token/family** nếu dùng.
- **Absolute lifetime của token family**.
- **Authorization grant lifetime** và chính sách thu hồi.
- **Application/IdP session absolute lifetime**.

### 11.4. Refresh token cấp cho thiết bị hoặc native app

Native mobile app có thể lưu refresh token trong bộ nhớ an toàn của nền tảng theo khả năng; SPAs/BFF có mô hình khác. Bất kể loại client, phải định nghĩa **cửa sổ có thể nhận token mới**, session binding khi hỗ trợ, logout và revocation. Không giả định app mobile bị kill đồng nghĩa server đã thu hồi refresh token.

## 12. OpenID Connect: IdP session, RP session và max_age

Trong OIDC, một **Identity Provider/OpenID Provider (OP)** xác thực người dùng; một **Relying Party (RP)** là ứng dụng tiêu thụ kết quả đăng nhập. Các lớp cần phân biệt:

1. **OP/IdP SSO session**: trạng thái đăng nhập tại nhà cung cấp danh tính.
2. **RP/application session**: cookie hoặc trạng thái đăng nhập cục bộ sau OIDC login.
3. **ID token**: assertion xác thực dành cho RP, có `iat`, `exp` và có thể `auth_time`.
4. **Access/refresh tokens**: dùng cho API hoặc cấp lại token, theo policy khác.

### 12.1. max_age có liên quan gì?

Tham số `max_age` trong OIDC Authentication Request thể hiện **tuổi tối đa cho phép của lần xác thực người dùng** theo yêu cầu; OP có trách nhiệm thực hiện hành vi tương ứng theo chuẩn, và `auth_time` được yêu cầu khi xử lý `max_age`.

**Không đồng nhất `max_age` với cấu hình absolute timeout của toàn bộ RP session**. RP vẫn phải:

- Kiểm ID token đúng issuer/audience/signature/nonce và các ràng buộc áp dụng.
- Kiểm `auth_time` khi policy đòi recent authentication.
- Tự quản lý **application session hard deadline**.
- Phân biệt step-up/reauth với extension của session hiện tại.

### 12.2. SSO tự động không phải bằng chứng reauthentication mới

Một RP có thể redirect sang OP khi phiên local hết hạn; OP còn SSO cookie nên đăng nhập quay lại ngay mà người dùng không nhập credential. Điều này có thể là hành vi hợp lệ ở một số chính sách, nhưng **không nhất thiết đáp ứng yêu cầu tái xác thực mới ở mức assurance cao**. Khi policy cần reauthentication, phải yêu cầu và **kiểm bằng chứng thời điểm/phương thức** phù hợp, không suy từ việc trình duyệt được redirect qua IdP.

### 12.3. Logout ở OP không luôn chấm dứt mọi phiên RP

Một người logout khỏi IdP chưa chắc tất cả RP sessions tự chấm dứt ngay. Cần xác định **logout propagation, front-channel/back-channel logout, session identifiers, resource revoke** theo khả năng tích hợp. **Absolute timeout tại mỗi RP** vẫn phải được enforce độc lập theo policy.

## 13. SAML SSO và session nhiều tầng

Trong SAML, IdP có thể xác thực và phát assertion cho SP. SP sau đó tạo session riêng.

### 13.1. Các thời hạn thường khác nhau

- **SAML assertion conditions** như `NotBefore`/`NotOnOrAfter` xác định điều kiện chấp nhận assertion; không mặc nhiên là SP session expiry.
- **AuthnStatement/SessionNotOnOrAfter** (khi được sử dụng) có thể chuyển thông tin liên quan phiên IdP và được SP xử lý theo thiết kế.
- **SP session absolute timeout** vẫn cần được cấu hình và kiểm bởi SP.
- **IdP SSO session** có thời hạn riêng.

Một assertion được sử dụng hợp lệ lúc 09:00 không có nghĩa SP phải cho người dùng hoạt động tới vô hạn. Ngược lại, assertion hết hạn **không tự động chấm dứt mọi session SP đã tạo từ trước**, trừ khi kiến trúc thực thi điều đó.

### 13.2. Single Logout (SLO) và giới hạn

SAML SLO có thể hỗ trợ đồng bộ logout nhưng phụ thuộc triển khai và khả năng các SP. Cần **test cả đường thành công lẫn thất bại**, không coi đã gửi LogoutRequest là bằng chứng mọi session đã mất quyền. **Hard deadline ở SP** đóng vai trò một lớp bảo vệ ngay cả khi SLO gặp lỗi.

## 14. JWT không lưu state và giới hạn thu hồi tuyệt đối

Một resource server có thể kiểm **JWT access token** bằng chữ ký, `exp`, `iss`, `aud`, phạm vi và quyền liên quan mà **không cần truy vấn session store** trên mọi request. Điều này thuận lợi cho hiệu năng, nhưng có giới hạn:

~~~text
JWT:
    iat = 16:55
    exp = 17:05

Application session:
    absoluteExpiresAt = 17:00

API chỉ kiểm JWT exp:
    Có thể chấp nhận token sau 17:00 tới trước 17:05.

API có kiểm session hard cap hoặc token bound deadline:
    Phải từ chối request ngoài policy từ 17:00.
~~~

Đây là **ví dụ**, không phải hành vi của mọi OAuth resource server. Một JWT có chữ ký hợp lệ **không tự mang thông tin rằng session phía ứng dụng đã bị hủy** nếu không có ràng buộc/enforcement tương ứng.

### 14.1. Ba nhóm phương án

| Phương án | Cách hạn chế cửa sổ | Chi phí/giới hạn |
| --- | --- | --- |
| **Token exp không vượt session deadline** | `exp = min(now + tokenTTL, absoluteExpiresAt)` khi cấp. | Phải bảo đảm issuer nhận và enforce deadline đúng, không cho token khác bypass. |
| **Introspection/session lookup ở API** | Resource server kiểm phiên/token còn active ở nguồn. | Có thêm phụ thuộc mạng, latency, cache và availability. |
| **Revocation/version/denylist** | Gắn session/grant version, kiểm ID hoặc event revoke. | Event propagation và cache có thể tạo cửa sổ stale. |

Những phương án có thể phối hợp. **Hard cap của session ở ứng dụng** vẫn cần nếu user dùng cookie riêng để gọi endpoint không đi qua OAuth access token.

### 14.2. Kiểm JWT không được chỉ dựa vào expiry

Phải xác thực đúng **thuật toán cho phép, chữ ký, issuer, audience, thời gian, scope/authorization và token type**. Không dùng ID token như access token, không nhận token của tenant/resource khác và không thay security check bằng một phép so sánh `exp`.

### 14.3. Clock skew

Resource server có thể cho một mức **clock skew tolerance** nhỏ khi kiểm thời gian token để giảm lỗi đồng hồ. Nếu muốn hard cap nghiêm ngặt tại 17:00, cần xác định **skew tolerance có cho access thêm sau deadline không**, và điều chỉnh thiết kế/enforcement phù hợp. Không mặc định có leeway bằng 0 khi mô tả bảo đảm thời gian nếu thư viện/kiến trúc thực tế dùng leeway.

## 15. Absolute timeout của Browser, SPA, BFF và Mobile

### 15.1. Ứng dụng web server-side

Với web dùng cookie, backend thường giữ session record và kiểm `now >= absoluteExpiresAt` trên request cần xác thực. Khi hết hạn, backend xóa/invalidate session và trả response yêu cầu đăng nhập lại. Browser có thể được thông báo trước để tránh mất công việc chưa lưu, nhưng **không dùng timer browser làm security boundary**.

### 15.2. Single Page Application (SPA)

SPA có thể quản lý access tokens, có silent refresh hoặc redirect OIDC. Các vấn đề:

- `setTimeout` hoặc countdown JS có thể bị dừng khi tab ngủ.
- Người dùng đóng/reopen browser không làm revoke session/token server.
- Multiple tabs có thể dùng chung trạng thái đăng nhập nhưng local timers lệch.
- Silent refresh có thể tiếp tục cho access token mới nếu chưa kiểm hard cap.
- Background refresh và polling không được làm sống lại phiên hết hạn.

**Server/resource phải kiểm deadline**, còn SPA xử lý UX: lưu nháp an toàn, thông báo hết hạn và đưa người dùng qua login khi cần.

### 15.3. Backend for Frontend (BFF)

BFF có thể giữ OAuth tokens ở server, browser chỉ mang cookie tới BFF. Điều này giảm việc lộ token trực tiếp cho JavaScript trong một số kiến trúc, nhưng BFF vẫn phải:

1. Giữ **application session hard deadline**.
2. Ngừng refresh token cho phiên đã hết hạn.
3. Ràng buộc cookie và server record.
4. Không tự động tạo session mới từ token cũ mà bỏ reauth policy.
5. Đóng hoặc thu hồi token/session khi có logout/Leaver.

### 15.4. Native mobile app

Mobile có thể hoạt động offline và lưu refresh tokens trong cơ chế bảo vệ của hệ điều hành. Cần phân biệt:

- **Local UI unlock** bằng biometrics/PIN: có thể chỉ mở khóa app trên thiết bị.
- **Server session/authorization**: vẫn chịu hard deadline và token policy.
- **Offline data/cache**: có thể đọc được cục bộ dù server đã revoke, tùy mô hình.
- **API offline queue**: request cần được kiểm lại khi gửi, không dùng authorization snapshot cũ.

Một app mở lại bằng vân tay **không mặc nhiên là server đã xác thực lại** với mức bảo đảm yêu cầu cho tài nguyên nhạy cảm.

## 16. Reauthentication và việc tạo phiên mới

Khi absolute deadline đến, ứng dụng cần một **hành vi kết thúc rõ** và một **đường xác thực lại hợp lệ**. Không nên:

- Đặt lại `createdAt` theo heartbeat.
- Cho refresh token gia hạn family vô hạn.
- Tạo cookie mới nhưng giữ cùng session ID và cùng authentication assurance cũ.
- Tự redirect qua IdP rồi coi một SSO cookie cũ là “reauth mới” cho mọi mức risk.

### 16.1. Step-up khác hard-cap reset

**Step-up authentication** yêu cầu bằng chứng xác thực mạnh hơn cho một hành động (ví dụ thay policy IAM). Trong một số policy, step-up thành công có thể tạo **subsession/privileged session** với deadline riêng. Nhưng **step-up không tự động kéo dài absolute lifetime của session gốc**, trừ khi policy rõ ràng xác định một quá trình reauthentication và session renewal hợp lệ.

### 16.2. Session regeneration an toàn

Khi một phiên mới được tạo:

1. Xác minh chủ thể và auth context theo policy.
2. Tạo session ID mới đủ entropy, không nhận identifier do client chọn.
3. Lưu `createdAt/authenticatedAt/absoluteExpiresAt` mới phù hợp.
4. Invalidate session cũ nếu thiết kế yêu cầu ngăn session overlap hoặc fixation.
5. Liên kết account/tenant/device/assurance mới theo dữ liệu đáng tin.
6. Ghi audit **oldSessionRef → newSessionRef** nếu cần, không lưu raw secrets.

### 16.3. Các mức reauthentication

Không phải mọi tài nguyên đòi người dùng nhập mật khẩu mỗi lần absolute timeout:

| Ngữ cảnh | Cách tái xác thực minh họa | Điều phải kiểm |
| --- | --- | --- |
| Ứng dụng thông thường. | Luồng OIDC/SAML được chính sách chấp nhận. | Auth time/assurance và session deadline mới. |
| Dữ liệu nhạy cảm. | Recent authentication/MFA phù hợp mức rủi ro. | Không chỉ dựa vào silent SSO nếu policy yêu cầu tương tác. |
| Privileged action. | Step-up/JIT/PAM approval và phiên đặc quyền riêng. | Scope, TTL, SoD và actor. |
| Emergency access. | Quy trình khẩn đã phê duyệt trước, có audit và hậu kiểm. | Không tạo bypass vô thời hạn. |

## 17. Absolute timeout khi có nhiều ứng dụng SSO

Một người dùng có thể đồng thời có:

~~~text
IdP SSO session: 08:00 → 18:00
Application A session: 09:00 → 17:00
Application B session: 10:30 → 14:30
PAM privileged session: 11:00 → 11:30
API access token: 11:05 → 11:15
~~~

Các mốc đều **minh họa**. Điều cần hiểu:

- 17:00 **A hết session**, nhưng B có thể đã hết từ 14:30 và IdP vẫn còn session.
- Một **SSO cookie tại IdP** còn sống có thể giúp mở luồng xác thực vào A lần nữa, tùy policy.
- **PAM 30 phút** không làm A tự hết phiên lúc 11:30; chỉ quyền nâng cao phải hết.
- Access token 10 phút không nói tuổi IdP/App session.

### 17.1. Báo cáo quản trị phải nêu lớp nào

Không viết chung chung “session timeout 8 giờ” nếu chưa chỉ rõ:

1. **IdP/OP session** hay **application/RP/SP session**?
2. Thời điểm tính từ login hay reauthentication?
3. Browser cookie, refresh family hay API access token?
4. User thường hay privileged session?
5. Có logout propagation hay enforcement ở resource không?

### 17.2. Tránh mismatch nguy hiểm

Nếu app hard cap 8 giờ nhưng API bearer token cho 24 giờ, **kẻ có token có thể gọi API sau khi UI hết hạn** nếu API không kiểm ràng buộc khác. Kiểm thử phải bao gồm **đường API trực tiếp**, không chỉ phiên browser.

## 18. PAM/JIT: absolute timeout cho quyền đặc biệt

Phiên quản trị thường có rủi ro cao hơn session đọc thông thường. **PAM/PIM/JIT** có thể cung cấp một giới hạn riêng:

~~~text
User session absolute deadline:     17:00
Privileged elevation activated:     13:00
Privileged elevation hard deadline: 13:30

13:31:
    user có thể còn phiên ứng dụng bình thường
    nhưng thao tác production-admin phải bị từ chối.
~~~

### 18.1. Các điều cần kiểm

| Kiểm soát | Tác dụng |
| --- | --- |
| **Time-bound activation** | Đặc quyền chỉ được kích hoạt trong khoảng được duyệt. |
| **Non-sliding elevation deadline** | Lệnh liên tục không tự kéo dài quyền admin. |
| **Step-up/approval** | Bảo đảm activation đúng actor, authority và SoD. |
| **Session/command monitoring** | Truy vết việc dùng quyền theo phạm vi được phép. |
| **Revoke/readback** | Quyền ở PAM/target đã thực sự bị thu hồi. |
| **Credential/session rotation** | Giảm việc giữ credential mạnh sau task. |
| **JML event controls** | Mover/Leaver chấm dứt eligibility trước thời hạn nếu cần. |

### 18.2. Không nhầm PAM dashboard hết giờ với quyền đích

Nếu PAM session hiển thị ENDED nhưng cloud role-assumption token hoặc SSH connection vẫn còn hiệu lực, phải có **resource/session-level verification**. Không đóng việc với bằng chứng “PAM timer=0” khi đường truy cập thực tế còn hoạt động.

### 18.3. Break-glass

Emergency access có thể phải hoạt động khi IdP/PAM bình thường lỗi, nhưng vẫn cần **thời hạn, phạm vi, cảnh báo, actor accountability, thu hồi và hậu kiểm** theo chính sách. Không sử dụng “cấp cứu” để mặc định bỏ absolute timeout của mọi tài khoản quản trị.

## 19. Joiner: absolute timeout không thay điều kiện Start date

Trong mô hình **Joiner**, IAM có thể tạo account và cấp thiết bị trước ngày nhân viên bắt đầu công việc.

Giả sử `startDate` chưa tới nhưng user đã có cookie/session ứng dụng từ quá trình preboarding:

- Session chưa đạt absolute timeout **không có nghĩa** user được mở quyền dữ liệu production.
- Authorization phải kiểm **Engagement effectiveAt** và role eligibility.
- Khi Start date có hiệu lực, các quyền mới cần được cấp theo JML policy, không tái dùng session cũ như bằng chứng đủ cho mọi quyền.
- Nếu role/assurance thay đổi, có thể cần reauthentication/session refresh hoặc token claims mới theo policy.

### 19.1. Kiểm mới quyền nhưng session cũ

Một browser session được tạo để onboarding có thể có scope thấp. Sau khi Joiner ACTIVE, đừng tự cấp admin cho session đó vì group mới xuất hiện nếu thiếu yêu cầu auth strength. **Role eligibility, session assurance và device trust phải được kiểm riêng**.

## 20. Mover: quyền thay đổi giữa phiên chưa hết hạn

Một nhân viên chuyển từ SRE sang Finance lúc 13:00 nhưng có session quản trị bắt đầu lúc 09:00, absolute deadline là 17:00.

~~~text
09:00  User logs in, session hard cap = 17:00.
13:00  HRIS Mover effective: SRE -> Finance.
13:01  IAM revokes SRE/JIT roles theo policy.
13:05  User dùng session 09:00 gọi production-admin API.

Expected:
    DENY vì quyền admin không còn hợp lệ.
    Không đợi tới 17:00 mới chặn.
~~~

### 20.1. Quyền cũ có thể còn trong token/session

Những đường cần kiểm:

- JWT có role claim cũ còn hạn.
- Server session lưu authorization cache.
- SSO application giữ local role assignment.
- PAM eligible/active role chưa được thu hồi.
- API key/PAT độc lập với phiên web.
- Group lồng nhau hoặc direct local grant không đi qua IGA.

**Hết absolute timeout là lớp giới hạn tối đa**, không đủ cho yêu cầu **MOVER_REVOKE_NOW** nếu policy buộc chặn quyền ngay theo sự kiện.

### 20.2. Reauthentication sau Mover có đủ không?

Reauthentication có thể làm mới claims, nhưng chỉ có ích nếu:

- IdP nhận thay đổi HRIS chính xác.
- SP/API không dùng authorization stale sau khi nhận token mới.
- Grant paths tại ứng dụng đã được xử lý.
- Session cũ không tiếp tục dùng được qua đường khác.

Phải kết hợp **event-driven revoke, entitlement reconciliation và session enforcement**.

## 21. Leaver: không chờ hard deadline để chặn truy cập

Với Leaver, mục tiêu là thu hồi theo **termination effectiveAt** và chính sách bảo mật, kể cả khi session hard cap còn nhiều giờ.

### 21.1. Ví dụ

~~~text
Session created:      09:00
Absolute expires:     17:00
HRIS Leaver effective: 11:30
Last known API use:   11:25
Request at 11:35:     phải bị chặn theo policy Leaver
~~~

Nếu API chỉ kiểm `now < absoluteExpiresAt` thì user vẫn có thể được phép tới 17:00, trái yêu cầu Leaver. Cần **session revoke/account disable, token invalidation hoặc authorization check theo nguồn hiện hành**.

### 21.2. Chuỗi thu hồi

| Thành phần | Thao tác | Xác minh |
| --- | --- | --- |
| **HRIS/IAM** | Phát sự kiện Leaver với Person/Engagement và effectiveAt. | Nguồn/version chính xác. |
| **IdP/SSO** | Disable sign-in, revoke IdP sessions/refresh tokens theo khả năng. | Đường đăng nhập mới bị chặn. |
| **Ứng dụng/SP** | Revoke local sessions, user grants. | Cookie cũ/API bị từ chối. |
| **OAuth issuer** | Revoke refresh families và xử lý access tokens. | API chặn theo policy; ghi cửa sổ token còn hạn. |
| **SCIM** | Disable User/remove Group khi hỗ trợ. | Provider readback và local role mapping. |
| **PAM** | Thu hồi privileged eligibility/sessions. | Không còn admin action. |
| **Device trust** | Xử lý device enrollment/cert/session liên quan. | Không còn đường từ thiết bị cũ. |
| **Non-human credential** | Chuyển owner/rotate nếu principal phụ thuộc người nghỉ. | Workload hợp lệ tiếp tục mà không dùng credential Leaver. |

### 21.3. SCIM và absolute timeout

**SCIM** có thể hỗ trợ disable User hoặc bỏ Group tại ứng dụng nhưng **không phải giao thức quản lý mọi phiên đăng nhập**. `active=false` ở provider không tự chứng minh **cookie local, refresh token, PAT hoặc service principal** đã hết hiệu lực. Cần kiểm nhiều đường và ghi **REVOKED_VERIFIED** theo scope.

### 21.4. Session đã hết hạn vẫn cần kiểm quyền dư

Ngay cả nếu phiên web tự hết hạn 17:00, một PAT 30 ngày hoặc role trực tiếp ở SaaS có thể tồn tại. **Absolute timeout của web session không thay account deprovisioning và credential lifecycle**.

## 22. Rehire, Contractor và nhiều Engagement

Một người được tuyển lại có thể giữ cùng Person ID nếu được xác minh, nhưng **Engagement mới** phải được xét riêng. Session hoặc refresh token của đợt làm việc cũ **không nên được hồi sinh** chỉ vì email/UPN được dùng lại.

### 22.1. Trường hợp rehire

1. HRIS kết thúc Engagement E1; IAM revoke session và quyền liên quan.
2. Sau đó HRIS tạo Engagement E2 cho cùng Person.
3. Role/eligibility thuộc E2 được tính từ policy hiện hành.
4. User phải tạo session mới theo điều kiện xác thực hiện tại.
5. Session/token/approval của E1 không được mặc nhiên chuyển sang E2.

Nếu hệ thống dùng email thay subject/Engagement làm khóa session, **rehire hoặc email tái cấp có thể làm nhầm quyền**. Mô hình session phải lưu identity namespace và chủ thể đúng.

### 22.2. Contractor

Hợp đồng có `endDate`; session hard deadline không được dùng để vượt qua mốc kết thúc hợp đồng. Nếu provider chưa cập nhật trạng thái Contractor, cần có **authorization checks và event propagation** bảo vệ tài nguyên, đặc biệt ngoài giờ khi không có operator theo dõi.

### 22.3. Shared accounts

Một tài khoản dùng chung có thể khiến không xác định ai giữ phiên và ai đã thực hiện hành động. Với phiên nhạy cảm, ưu tiên **named identities, session checkout/recording và time-bound controls**; absolute timeout không tự giải quyết thiếu attribution.

## 23. Device trust và absolute timeout

Một thiết bị đã trusted tại 09:00 có thể mất hoặc bị EDR đánh giá high-risk lúc 11:00. Session absolute deadline 17:00 **không nên chặn phản ứng sự kiện sớm**.

| Device event | Phản ứng cần thiết | Không được suy luận |
| --- | --- | --- |
| **Mất máy** | Chặn device credential, sessions/tokens và truy cập nhạy cảm theo policy. | Cookie tự hết hạn đủ để bảo vệ. |
| **EDR HIGH_RISK** | Reassess/deny/quarantine theo khả năng, incident. | Session còn hard cap nên an toàn. |
| **MDM compliance stale** | Hạn chế/step-up theo rủi ro, điều tra telemetry. | Không thấy lỗi nghĩa là compliant. |
| **Device certificate revoked** | PEP/gateway kiểm revocation, đóng phiên theo hỗ trợ. | Certificate NotAfter còn xa là được phép. |
| **Owner đổi sau bàn giao** | Rebind/re-enroll, xử lý session và local credential của chủ cũ. | Device ID không đổi nghĩa là ownership không đổi. |

### 23.1. Sender-constrained tokens

mTLS-bound access tokens hoặc DPoP có thể giảm token replay giữa client khác. Tuy nhiên, **thiết bị bị chiếm** vẫn có thể dùng khóa hợp lệ, và DPoP không tự chứng minh OS posture. Hard cap, JML revoke và device/risk checks vẫn cần thực thi theo policy.

## 24. Service accounts và machine-to-machine sessions

**Absolute timeout** không chỉ liên quan browser. Các máy, script, service principal, API client và workload cũng dùng **token, kết nối, phiên giao thức hoặc credential có thời hạn**.

### 24.1. Không buộc machine login có cùng UX như human login

Workload có thể dùng:

- OAuth 2.0 client credentials hoặc workload federation.
- Short-lived certificates/mTLS.
- Kubernetes service account tokens hoặc platform workload identity theo thiết kế.
- SSH hoặc database sessions có TTL riêng.
- Cloud role-assumption tokens.

**Không phải mọi machine-to-machine token đều gắn với một “human session”**. Cần xác định hard cap cho **credential, token family, connection hoặc privilege lease** mà hệ thống thật hỗ trợ, không áp máy móc cookie web.

### 24.2. Những thuộc tính nên quản lý

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **principalId / workloadId** | Chủ thể máy nào được cấp quyền. |
| **ownerTeam / purpose** | Ai chịu trách nhiệm và job gì cần quyền. |
| **issuer, audience, scope** | Token/certificate dùng cho đâu và quyền gì. |
| **issuedAt/expiresAt** | Giới hạn thời gian credential/token. |
| **keyRotationAt / revocationRef** | Cách xử lý khi lộ hoặc kết thúc workload. |
| **resourceSessionId** | Kết nối dài, SSH/DB session cụ thể. |
| **device/host trust** | Nếu policy yêu cầu môi trường chạy đáng tin. |
| **decommissionAt** | Khi workload không còn lý do tồn tại. |

### 24.3. Kết nối dài và workload không được tự gia hạn đặc quyền

Một service có thể duy trì gRPC/WebSocket hoặc DB connection rất lâu. Nếu connection được cấp quyền quản trị tại thời điểm bắt đầu, cần xác định:

- Có hard limit cho connection/session không?
- Có kiểm quyền lại khi command mới được thực hiện không?
- Khi service principal bị revoke, connection đang sống bị đóng/giới hạn thế nào?
- Token rotate có làm mất hiệu lực session/token cũ theo policy không?
- Có tình huống job dài được cấp quyền thấp hơn qua delegation/scope riêng thay vì giữ toàn quyền?

Không nên giữ credential admin vĩnh viễn chỉ vì “cron job cần chạy qua đêm”.

### 24.4. Chủ sở hữu Leaver

Một workload có thể tiếp tục hợp lệ sau khi kỹ sư tạo nó nghỉ việc, nhưng cần **owner transfer, credential review, role least privilege và sự độc lập với PAT cá nhân**. Không giữ account Leaver ACTIVE để máy tiếp tục làm việc.

## 25. Hệ thống phân tán: clock, cache, replicas và race conditions

Absolute timeout tưởng đơn giản vì chỉ so sánh thời gian, nhưng trong hệ thống phân tán, **mỗi service, cache và token issuer có thể nhìn thấy trạng thái khác nhau**.

### 25.1. Rủi ro đồng hồ

Ví dụ:

~~~text
Session hard deadline: 17:00:00 UTC
Gateway A clock:       17:00:03 UTC
Gateway B clock:       16:59:55 UTC

Gateway A đã từ chối.
Gateway B có thể còn cho phép nếu đồng hồ bị chậm.
~~~

Kiểm soát:

- Đồng bộ thời gian server với nguồn tin cậy và theo dõi **clock drift**.
- Dùng timestamps có timezone rõ, thường lưu UTC trong dữ liệu kỹ thuật.
- Xác định tolerance được phép và **bảo đảm thực tế** của deadline.
- Không lấy `Date.now` do client gửi làm giờ chuẩn.
- Khi dùng monotonic clock trong một process để đo khoảng trôi, vẫn cần quản lý **absolute timestamp** bền vững giữa restart/nodes.

### 25.2. Cache còn session cũ

Một API gateway có thể cache “session ACTIVE” trong 5 phút. Khi hard deadline đến:

~~~text
16:58  Gateway cache validation result ACTIVE.
17:00  Absolute deadline đến.
17:02  Gateway vẫn dùng cache ACTIVE đến 17:03.
~~~

Nếu PEP không kiểm thêm deadline ngay trên mỗi request, **một phiên có thể sống quá hard cap**. Giải pháp có thể là cache **kèm expiresAt chính xác**, tính TTL không vượt deadline, kiểm deadline tại PEP và xử lý invalidation/event revocation.

### 25.3. Concurrent requests quanh mốc hết hạn

| Tình huống | Lỗi có thể có | Kết quả cần kiểm |
| --- | --- | --- |
| Hai request lúc 16:59:59 và 17:00:01. | Node khác nhau có policy khác. | Request sau deadline bị từ chối theo mô hình enforcement. |
| Refresh và expire chạy đồng thời. | Worker refresh tạo session/token mới. | Không cấp credential vượt hard deadline của family cũ. |
| Logout/revoke trùng refresh. | Refresh resurrects revoked session. | Revoke precedence, version/atomic check. |
| Leaver và grant chạy song song. | Một session mới được mở sau termination. | Kiểm lifecycle trước creation và activation. |
| User reauthenticate đúng khi session cũ hết. | Hai session cùng active không kiểm soát. | Áp session rotation/overlap policy và audit. |
| Policy hard cap thay đổi trong lúc session còn active. | Node dùng policy cũ/mới khác nhau. | Quy tắc hiệu lực phiên bản rõ và không bypass quy định khẩn. |

### 25.4. Fail-safe khi session store lỗi

Nếu hệ thống không thể đọc record/deadline cần thiết, **không nên mặc định coi session hợp lệ**. Với resource nhạy cảm có thể DENY hoặc yêu cầu xác thực lại theo policy; với hoạt động ít nhạy cảm có thể dùng cơ chế continuity đã thiết kế, giới hạn chức năng và thời gian. Dù lựa chọn nào cũng phải **ghi nhận nguồn không thể xác minh, rủi ro và giới hạn**.

### 25.5. Đừng gọi mọi độ trễ là “đã revoke”

Một event `EXPIRED_ABSOLUTE` trong session store không chứng minh mọi resource server biết nó. Đối với hệ thống đa gateway hoặc token tự chứa, cần có **verification ở đích** và báo rõ nếu chỉ có thể bảo đảm token hết hạn sau một khoảng hữu hạn.

## 26. Thiết kế phiên nhiều miền và multi-tenant

Absolute timeout phải gắn với **đúng session, đúng tenant và đúng chủ thể**.

### 26.1. Những trường dễ bị nhầm

~~~text
tenantId          = namespace of tenant
issuerId          = nguồn xác thực
subjectId         = định danh của subject trong issuer/tenant
engagementId      = quan hệ làm việc hiện hành
sessionId         = định danh phiên được tạo an toàn
sessionFamilyId?  = nhóm phiên/token khi kiến trúc có định nghĩa
authTime          = thời điểm xác thực có ý nghĩa theo policy
createdAt         = thời điểm tạo session
absoluteExpiresAt = hard deadline
revocationVersion = phiên bản trạng thái thu hồi
~~~

### 26.2. Không tin session từ tenant khác

Một session được tạo ở tenant A không được sử dụng để gọi API tenant B chỉ vì `subjectId` trùng chuỗi. Kiểm issuer, audience, tenant, resource authorization và session reference đúng namespace.

### 26.3. Nhiều session trên nhiều thiết bị

Một người có thể đăng nhập trên laptop và điện thoại; mỗi phiên có deadline riêng. Khi người dùng chọn **“Sign out all devices”** hoặc Security revoke, phải xác định tất cả session/families chịu ảnh hưởng.

| Hành động | Kỳ vọng |
| --- | --- |
| Logout phiên trên laptop. | Ít nhất phiên laptop hết hiệu lực; không tùy tiện revoke máy khác nếu policy không yêu cầu. |
| Logout all devices. | Tất cả session thuộc scope user/tenant bị xử lý. |
| Leaver. | Mọi session và credential gắn engagement mất hiệu lực theo policy. |
| Device lost. | Các phiên/credential liên quan device bị revoke hoặc giới hạn theo khả năng. |
| API key bị lộ. | Thu hồi credential có liên quan; hard cap của browser không đủ. |

## 27. Luồng request tại backend và pseudocode

### 27.1. Kiểm session trước authorization

~~~text
authenticateAndAuthorize(request):
    sessionRef = extractProtectedSessionReference(request)
    session = loadSessionByOpaqueReference(sessionRef)
    if session is missing:
        return UNAUTHENTICATED

    now = trustedServerTime()

    if session.state == REVOKED:
        return UNAUTHENTICATED
    if now >= session.absoluteExpiresAt:
        expireSessionAndRelatedArtifacts(session, ABSOLUTE_TIMEOUT)
        return UNAUTHENTICATED
    if now >= session.lastMeaningfulActivityAt + session.idleTimeout:
        expireSessionAndRelatedArtifacts(session, IDLE_TIMEOUT)
        return UNAUTHENTICATED

    subject = loadCurrentAuthoritativeSubject(session.subjectId)
    if not subject.isEligibleForCurrentAccess(now):
        revokeSession(session, LIFECYCLE_OR_POLICY_CHANGED)
        return UNAUTHENTICATED_OR_DENIED

    if not sessionAssuranceAndDeviceRiskSatisfyPolicy(session, request):
        return REQUIRE_STEP_UP_OR_RESTRICT

    decision = authorizeSubjectForActionAndResource(subject, request)
    if decision != PERMIT:
        return FORBIDDEN

    if isMeaningfulActivity(request):
        updateLastActivityWithoutExtendingAbsoluteDeadline(session, now)

    return CONTINUE_TO_BUSINESS_ACTION
~~~

**Đây là giả mã minh họa**, không phải mã triển khai. Trong thực tế cần xử lý phiên bản dữ liệu, cache, concurrency, token family, CSRF, request idempotency, exception mapping và race giữa authorization với commit.

### 27.2. Điều kiện về thứ tự kiểm

Nên kiểm **session validity trước khi thực hiện hành động nhạy cảm**. Nếu một API ghi thay đổi rồi mới phát hiện hết hạn, việc trả 401 sau đó **không chứng minh dữ liệu chưa bị thay đổi**. Trong các giao dịch nhiều bước, cần ràng buộc authorization tại transaction boundary phù hợp.

### 27.3. Phân biệt UNAUTHENTICATED và FORBIDDEN

- **401 Unauthorized** trong HTTP authentication context thường thể hiện request chưa có thông tin xác thực hợp lệ hoặc cần challenge.
- **403 Forbidden** thể hiện request đã được hiểu nhưng không được phép theo authorization policy.

Không áp cứng mọi framework phải trả chính xác cùng status trong mọi luồng UI/cookie; có thể redirect login cho web. Dù dùng mã gì, **không lộ session secret hoặc chi tiết nhạy cảm** và backend vẫn phải thực thi đúng deny.

### 27.4. Ví dụ TypeScript cho server session

~~~ts
type SessionRecord = {
  id: string;
  subjectId: string;
  createdAtMs: number;
  absoluteExpiresAtMs: number;
  lastMeaningfulActivityAtMs: number;
  idleTimeoutMs: number;
  revoked: boolean;
};

function validateSessionTime(
  session: SessionRecord,
  nowMs: number
): "VALID" | "REVOKED" | "ABSOLUTE_EXPIRED" | "IDLE_EXPIRED" {
  if (session.revoked) return "REVOKED";
  if (nowMs >= session.absoluteExpiresAtMs) return "ABSOLUTE_EXPIRED";

  const idleExpiresAtMs =
    session.lastMeaningfulActivityAtMs + session.idleTimeoutMs;
  if (nowMs >= idleExpiresAtMs) return "IDLE_EXPIRED";

  return "VALID";
}

// Khi xử lý request: cập nhật lastMeaningfulActivityAtMs có điều kiện.
// Không cập nhật createdAtMs/absoluteExpiresAtMs do hoạt động thường.
~~~

Code chỉ minh họa **logic thời gian**, **chưa đủ** để làm auth middleware an toàn. Nó không kiểm signature/cookie/session ID, user lifecycle, token issuer, resource authorization, CSRF hoặc concurrency.

## 28. Các sai lầm triển khai khiến hard cap trở thành sliding timeout

### 28.1. Sliding TTL ngầm qua middleware

Một session library có thể reset cookie TTL hoặc TTL trong session store ở mỗi request. Nếu dùng nó làm nguồn duy nhất cho absolute timeout, phiên có thể tồn tại vô hạn.

**Kiểm cần có:** một trường `absoluteExpiresAt` **không được cập nhật** bởi sliding middleware, và server check trường đó.

### 28.2. Silent SSO re-login mà không kiểm auth time

RP thấy session local hết hạn, tự redirect OP và nhận ID token mới từ SSO cookie cũ. Nếu chính sách yêu cầu **reauthentication freshness**, phải kiểm `auth_time`/assurance, không chỉ nhìn `iat` của ID token mới.

### 28.3. Refresh token rotation reset family deadline

Rotation phát refresh token mới nhưng đồng thời cập nhật `familyAbsoluteExpiresAt = now + maxAge` mỗi lần. Kết quả: refresh liên tục → **family không bao giờ hết hạn**.

**Kiểm cần có:** giữ `familyCreatedAt`/`familyAbsoluteExpiresAt` bất biến cho family; nếu cần tạo family mới, phải qua quy trình có thẩm quyền.

### 28.4. Token cuối cùng vượt deadline

Một access token được cấp **ngay trước hard cap**, chứa `exp` sau deadline. API chỉ kiểm `exp` sẽ tiếp tục cho truy cập sau deadline.

**Kiểm cần có:** hạn token/PEP/session consistency và test access trực tiếp qua API, không chỉ refresh endpoint.

### 28.5. Background requests giữ idle sống

Polling/heartbeat làm `lastActivityAt` trượt ngay cả khi user đã rời máy. Không phải lỗi absolute timeout, nhưng có thể khiến hệ thống **chỉ còn hard cap** và không đạt yêu cầu idle.

**Kiểm cần có:** định nghĩa hoạt động có ý nghĩa và test khi tab/background service chạy.

### 28.6. Logout UI nhưng API vẫn cho phép

Frontend xóa local state/cookie nhưng server session/refresh token chưa bị thu hồi. Kẻ có token khác vẫn truy cập.

**Kiểm cần có:** server-side invalidation và kiểm thực tế tại resource.

### 28.7. Session record mới được tạo từ secret cũ

Session expired nhưng endpoint bootstrap chấp nhận session ID cũ để tạo record mới. Đây có thể là lỗ hổng tái tạo quyền không có authentication.

**Kiểm cần có:** các credential đã expired/revoked không đủ tư cách mở session mới.

### 28.8. Cron cleanup bị nhầm là security enforcement

Cleanup job chạy 5 phút/lần để xóa session hết hạn. Nếu API không kiểm deadline trực tiếp, nó có thể cho phép truy cập trong 5 phút chờ job.

**Kiểm cần có:** enforcement theo `now >= absoluteExpiresAt` ngay tại request, cleanup chỉ phụ trợ.

## 29. Kịch bản kiểm thử Absolute timeout

Một bộ kiểm thử đầy đủ cần cả **positive**, **negative**, **boundary**, **concurrency**, **SSO**, **JML** và **effective API authorization**.

### 29.1. Ma trận test

| Test ID | Tiền điều kiện | Hành động | Expected |
| --- | --- | --- | --- |
| **AT-01** | Session hợp lệ, chưa tới idle/absolute deadline. | Gọi API đúng quyền. | ALLOW, audit theo policy. |
| **AT-02** | Session còn hoạt động liên tục, đến hard deadline. | Gọi API sau deadline. | DENY/re-auth; hard cap không trượt. |
| **AT-03** | Không hoạt động quá idle timeout, absolute chưa tới. | Gọi API. | Session expired do IDLE. |
| **AT-04** | Request lúc ngay trước deadline. | Gọi API cần xác thực. | Theo rule về thời điểm check, chưa expired nếu đủ điều kiện. |
| **AT-05** | Request tại chính xác `absoluteExpiresAt`. | Gọi API. | EXPIRED; dùng so sánh `now >= expiresAt`. |
| **AT-06** | Polling/heartbeat chạy liên tục. | Đợi tới hard deadline. | Hard deadline vẫn cố định. |
| **AT-07** | Cookie `Max-Age` được middleware refresh. | Gọi API sau server hard deadline. | DENY dù browser còn cookie. |
| **AT-08** | Refresh token family gần hard cap. | Rotate/refresh sau hard deadline. | Không cấp quyền vượt family deadline. |
| **AT-09** | Access token phát sát hard cap, `exp` còn sau. | Gọi resource trực tiếp sau hard deadline. | Theo bảo đảm hard cap đã thiết kế; không bypass. |
| **AT-10** | JWT đã expired nhưng session record ACTIVE. | Gọi API bằng token cũ. | DENY do token expiry. |
| **AT-11** | RP session expired, IdP SSO session vẫn active. | Silent SSO redirect. | Chỉ tạo session mới khi policy/reauth được đáp ứng. |
| **AT-12** | OIDC `max_age` yêu cầu recent auth. | SSO token có `auth_time` quá cũ. | Không coi recent auth là đạt. |
| **AT-13** | SAML assertion expired nhưng SP session còn. | Gọi SP API. | Theo SP session policy, không suy tự động hai deadline giống nhau. |
| **AT-14** | Role PAM hết sau 30 phút, user session còn. | Gọi privileged endpoint. | DENY privilege; session thường có thể còn. |
| **AT-15** | Mover có hiệu lực trước hard deadline. | Dùng quyền cũ từ token/session. | DENY theo role hiện hành. |
| **AT-16** | Leaver có hiệu lực trước hard deadline. | Thử cookie, API token, refresh. | Các đường còn trong scope bị chặn/revoked theo policy. |
| **AT-17** | Device báo LOST/HIGH_RISK. | Dùng session trước deadline. | Deny/restrict và ghi security evidence. |
| **AT-18** | Hai request quanh hard deadline đến hai gateway. | Kiểm kết quả. | Không có stale cache cho phép sai deadline. |
| **AT-19** | Session revoked cùng lúc refresh. | Gọi refresh. | Không tái tạo phiên bị revoke. |
| **AT-20** | User reauth hợp lệ sau hard deadline. | Tạo session mới. | ID/deadline mới, session cũ không sống lại. |
| **AT-21** | Người dùng có hai thiết bị, logout-all. | Thử cả hai session. | Cả hai bị xử lý theo scope logout-all. |
| **AT-22** | User rehire có Engagement mới. | Dùng cookie cũ của E1. | DENY; không kế thừa phiên cũ. |
| **AT-23** | MDM/HRIS/session store outage. | Gọi resource high-risk. | UNKNOWN/FAIL-SAFE theo policy, không mặc định ALLOW. |
| **AT-24** | Long-running job từ phiên hết hạn. | Thử commit hành động nhạy cảm sau deadline. | Revalidation/ủy quyền riêng đúng chính sách. |
| **AT-25** | Machine client credential/token hết hạn. | Dùng connection/API với credential cũ. | Enforcement đúng token/connection policy. |
| **AT-26** | Browser đóng/reopen với session restoration. | Dùng cookie cũ sau hard deadline. | Server DENY. |
| **AT-27** | Session record hết cache TTL nhưng refresh còn hợp lệ sai policy. | Thử mở lại session bằng old refresh. | Không mở lại vượt hard cap. |
| **AT-28** | Admin đổi session policy/risk tier lúc user active. | Thử hành động sau thay đổi. | Áp policy effective version và revocation thích hợp. |

Expected trong bảng là **mục tiêu kiểm soát theo kiến trúc/policy**, không phải mọi sản phẩm phải trả cùng HTTP code hoặc cùng cơ chế reauth. Với JWT tự chứa không có revoke tức thời, phải ghi rõ **cửa sổ không thể enforce** và đánh giá liệu thiết kế có thỏa policy hay không.

### 29.2. Biên thời gian và fake clock

Test có thể dùng **fake clock/controllable time source** trong unit test:

~~~text
createdAt = 09:00:00
absoluteExpiresAt = 17:00:00

now = 16:59:59.999 -> VALID nếu các điều kiện khác đạt
now = 17:00:00.000 -> ABSOLUTE_EXPIRED
now = 17:00:00.001 -> ABSOLUTE_EXPIRED
~~~

Đừng chỉ kiểm log “expired” mà bỏ qua API actual. Integration test phải chứng minh **request ở resource bị từ chối**, session cũ không nhận token mới và không có side effects sau deadline.

### 29.3. Test refresh vượt deadline

Một test quan trọng:

~~~text
Family created at:      09:00
Family hard deadline:   17:00
Refresh at:             16:59
New access token exp:   17:04  (tình huống lỗi giả định)
Resource request at:    17:02

Expected:
    Nếu policy hard cap strict tại 17:00:
    resource phải DENY, dù token signature/exp còn hợp lệ.
~~~

Nếu resource thực tế ALLOW, test FAIL đối với yêu cầu hard cap strict; cần sửa **issuer TTL cap hoặc API enforcement**.

### 29.4. Không kiểm trên production bằng cách chặn phiên thật

Ưu tiên tenant staging, session test, clock injection hoặc các token giả do test issuer cấp trong hệ thống cho phép. Không thu hồi phiên của nhân viên thật, phá IdP hay cố lấy cookie người khác để test. Với production, dùng phương pháp được tổ chức cấp quyền và có kế hoạch rollback, giới hạn tác động.

## 30. Ghi nhận bằng chứng test và audit phiên

Một session audit record giúp trả lời **phiên nào, thuộc ai, hết hạn khi nào, bị chặn ở đâu và vì sao**.

### 30.1. Trường gợi ý

| Trường | Ý nghĩa |
| --- | --- |
| **sessionRef** | Tham chiếu session không lộ raw secret. |
| **subjectId, engagementId, tenantId** | Danh tính và quan hệ làm việc. |
| **applicationId / resourceId** | Phiên thuộc SP/RP/API nào. |
| **createdAt, authTime** | Mốc tạo phiên và xác thực. |
| **lastMeaningfulActivityAt** | Mốc kiểm idle. |
| **absoluteExpiresAt** | Hard deadline đã chốt. |
| **effectiveExpiresAt** | Deadline hiệu lực cho hành động theo policy, nếu tính được. |
| **state, stateReason** | ACTIVE, EXPIRED_ABSOLUTE, REVOKED, IDLE... |
| **policyVersion / riskTier** | Quy tắc nào đã áp. |
| **deviceBindingRef / authStrength** | Bối cảnh xác thực và thiết bị, nếu dùng. |
| **revokedAt / revokedBy / eventRef** | Thu hồi theo JML/admin/security. |
| **tokenFamilyRef / issuer** | Liên kết refresh family và token issuance khi áp dụng. |
| **PEPDecision / observedAt** | Bằng chứng thực thi ở resource. |
| **exceptionId / owner** | Đường chưa thể xác minh hoặc rủi ro còn mở. |

### 30.2. Log minh họa

~~~json
{
  "eventType": "SESSION_AUTHORIZATION_DENIED",
  "traceId": "trace-session-20261201-881",
  "sessionRef": "session-ref-1042",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "tenantId": "tenant-a",
  "applicationId": "finance-reporting",
  "createdAt": "2026-12-01T09:00:00+07:00",
  "absoluteExpiresAt": "2026-12-01T17:00:00+07:00",
  "requestAt": "2026-12-01T17:00:01+07:00",
  "reason": "ABSOLUTE_TIMEOUT",
  "decision": "DENY",
  "policyVersion": "session-policy-v7",
  "pepId": "finance-api-gateway"
}
~~~

Đây là **schema ví dụ**, không phải response của OAuth, OIDC, SAML hoặc một SIEM cụ thể. Không đưa raw session ID, cookie, JWT, PAT, refresh token, password hoặc OTP vào log.

### 30.3. Event chronology

Một cuộc điều tra có thể cần:

~~~text
AUTHENTICATION_SUCCEEDED
  -> SESSION_CREATED (hard deadline established)
  -> SESSION_USED
  -> SESSION_STEP_UP (if applicable)
  -> ROLE_CHANGED or DEVICE_RISK_CHANGED
  -> SESSION_RESTRICTED / REVOKED / EXPIRED_ABSOLUTE
  -> RESOURCE_DENIED (verified at PEP)
~~~

Ghi nhận **thứ tự và thời điểm của sự kiện**; nếu event đến muộn, dùng source version/effectiveAt thay vì tin thứ tự ghi log duy nhất.

## 31. Case study 1 – Dashboard tự refresh khiến idle không bao giờ hết

**Bối cảnh giả định:** một dashboard quản trị tài chính dùng cookie và idle timeout 15 phút. Frontend tự polling số liệu mỗi 60 giây, backend ghi tất cả request vào `lastActivityAt`. Người dùng đóng laptop nhưng không logout; session cứ được gia hạn.

### 31.1. Quan sát

| Thời điểm giả định | Sự kiện | Kết quả của thiết kế lỗi |
| --- | --- | --- |
| **09:00** | Người dùng đăng nhập. | Session tạo, idle deadline 09:15. |
| **09:01** | Polling nền chạy. | Idle deadline bị kéo tới 09:16. |
| **09:02–12:00** | Polling chạy liên tục. | Idle deadline trượt mãi, không có hard cap. |
| **12:05** | Một request dùng cookie đã bị lấy cắp. | Có thể được chấp nhận nếu không có kiểm soát khác. |
| **17:00** | Nếu thêm hard cap 8 giờ từ 09:00. | Session phải hết theo absolute dù polling vẫn chạy. |

### 31.2. Cách xử lý

1. Cập nhật policy để **không coi heartbeat/polling vô hình là meaningful activity** nếu mục tiêu idle là phát hiện người dùng vắng mặt.
2. Lưu `absoluteExpiresAt` cố định khi tạo session.
3. Backend kiểm hard cap trên mọi request cần xác thực.
4. Khi deadline đến, không để refresh/cookie middleware kéo dài phiên.
5. Trước deadline, UI có thể cảnh báo và hỗ trợ lưu nháp an toàn; không thay server enforcement.
6. Chạy test AT-02, AT-06, AT-07, AT-26 và kiểm kết quả từ API.

### 31.3. Bài học

**Idle timeout và absolute timeout giải quyết hai bài toán khác nhau**. Sửa cách đếm hoạt động có ý nghĩa giúp xử lý idle; thiết lập hard cap bảo đảm **phiên không được kéo dài vô hạn ngay cả khi hoạt động hợp lệ liên tục**.

## 32. Case study 2 – OIDC refresh token kéo dài phiên sau hard cap

**Bối cảnh giả định:** ứng dụng ERP đặt absolute timeout 8 giờ cho phiên người dùng, access token TTL 10 phút. Client có cơ chế refresh rotation; issuer cấp access token mới bất cứ lúc nào refresh token family còn hoạt động, không kiểm hard cap.

### 32.1. Tình huống

~~~text
09:00  User login, application session expires 17:00.
16:59  Client refresh, issuer creates token exp=17:09.
17:00  Browser UI reports "Session expired".
17:05  Client calls ERP API directly with token exp=17:09.
17:05  API only verifies JWT exp/signature; request succeeds.
~~~

### 32.2. Lỗ hổng thực chất

Backend web session đã hết hạn nhưng **API authorization không chịu cùng giới hạn**. Việc UI logout không bảo vệ endpoint. Cần xác định policy muốn:

- Chặn **mọi API action từ user session** tại 17:00?
- Chặn refresh family từ 17:00 nhưng chấp nhận token cuối còn hạn vài phút?
- Có bất kỳ ngoại lệ nào cho long-running jobs không?

Nếu policy nêu **hard cap nghiêm ngặt 17:00**, đường API còn cho phép tới 17:09 là **không đáp ứng**.

### 32.3. Khắc phục

| Thành phần | Điều cần sửa/kiểm |
| --- | --- |
| **Authorization server** | Gắn refresh family với deadline không trượt, không cấp token vượt giới hạn theo policy. |
| **Resource server** | Kiểm session/deadline hoặc token boundary phù hợp. |
| **BFF/Client** | Không coi silent refresh là reauth mới. |
| **IdP/OP** | Khi policy đòi reauthentication, xác minh `auth_time` và yêu cầu phù hợp. |
| **Audit** | Ghi token issuance/refresh/PEP decision bằng metadata, không log raw token. |

### 32.4. Retest

- AT-08: Refresh sau 17:00 không cho family cũ sống lại.
- AT-09: Token cuối cấp trước 17:00 không vượt hard cap strict tại API.
- AT-11/12: Reauthentication hợp lệ tạo session mới nếu policy cho.
- AT-19/20: Revoke và reauth race không hồi sinh phiên cũ.

**Bài học:** **Token TTL ngắn không đảm bảo session TTL ngắn**. Phải bảo vệ toàn bộ **refresh lifecycle và resource enforcement**, không chỉ nút logout.

## 33. Case study 3 – Leaver vẫn truy cập SaaS bằng session cũ

**Bối cảnh giả định:** nhân viên Bình đăng nhập SaaS lúc 09:00, absolute timeout 12 giờ. HRIS gửi Leaver có hiệu lực 11:00. IAM disable IdP account và SCIM cập nhật User `active=false`, nhưng SaaS dùng local cookie 12 giờ và chưa nhận session revocation.

### 33.1. Dòng thời gian

| Thời điểm giả định | Sự kiện | Kiểm chứng |
| --- | --- | --- |
| **09:00** | Bình đăng nhập; SP session tạo tới 21:00. | SP createdAt/hard deadline. |
| **11:00** | Leaver effectiveAt từ HRIS. | Person/Engagement và source version. |
| **11:01** | IdP disable account. | Sign-in mới bị chặn theo IdP. |
| **11:03** | SCIM `active=false`, HTTP 204. | Provider ACK, chưa chứng minh session. |
| **11:05** | Cookie SaaS cũ được gửi tới API. | Nếu API vẫn cho phép, đó là residual access. |
| **11:07** | App owner xử lý local session/API access. | Revoke/deny theo khả năng sản phẩm. |
| **11:10** | API kiểm chứng từ chối các đường thuộc phạm vi. | REVOKED_VERIFIED với evidence. |

### 33.2. Phát biểu đúng trong báo cáo

**Không nên:** “Leaver an toàn vì session sẽ tự hết lúc 21:00”.

**Nên:** “Từ 11:00, user không còn đủ tư cách. Đăng nhập mới đã bị chặn; phiên cũ đã được phát hiện còn quyền tới khi ứng dụng xử lý. Cần ghi cửa sổ quyền tồn dư, owner, action và verifiedAt; đồng thời sửa tích hợp thu hồi phiên theo sự kiện Leaver.”

### 33.3. Những rủi ro bổ sung

- PAT/API key độc lập với session web.
- SaaS app-local grants và các group kế thừa.
- Người dùng có nhiều ứng dụng SP và phiên trên nhiều thiết bị.
- Cache authorization hoặc JWT có claims cũ.
- Một request dài bắt đầu trước 11:00 nhưng commit sau 11:00.

**Bài học:** Absolute timeout chỉ giới hạn **độ dài tối đa**; các sự kiện **Leaver và security revoke phải có cơ chế chặn sớm hơn**.

## 34. Case study 4 – PAM JIT hết hạn trước session web

**Bối cảnh giả định:** một quản trị viên có phiên SSO vào portal tới 17:00. Lúc 13:00, họ được duyệt quyền JIT production-admin trong 30 phút để xử lý sự cố.

### 34.1. Hai deadline khác nhau

~~~text
Web session:
    createdAt = 09:00
    absoluteExpiresAt = 17:00

PAM privileged activation:
    activatedAt = 13:00
    privilegeExpiresAt = 13:30

13:29 - User xem dashboard thông thường: có thể ALLOW.
13:29 - User sửa production IAM policy: có thể ALLOW nếu đủ approvals.
13:31 - User xem dashboard thông thường: có thể ALLOW.
13:31 - User sửa production IAM policy: phải DENY do JIT expired.
17:00 - Web session cũng hết hard cap.
~~~

### 34.2. Lỗi thường gặp

PAM UI ghi `ELEVATION_EXPIRED` lúc 13:30, nhưng một cloud role-assumption token phát lúc 13:20 vẫn cho phép sửa IAM tới 14:20 vì cloud API chỉ kiểm token. Nếu chính sách JIT yêu cầu **quyền đặc biệt chấm dứt lúc 13:30**, hệ thống phải dùng token/session/enforcement phù hợp; không thể coi một trạng thái UI là chứng cứ đủ.

### 34.3. Kiểm SoD

Nếu user được phép tự xin và tự duyệt elevation, hard cap 30 phút **không giải quyết vấn đề self-approval**. Cần kết hợp approver độc lập, approval scope, JIT TTL, session monitoring, readback và audit.

### 34.4. Bài học

Một người có thể giữ session thông thường sau khi đặc quyền đã hết; **hard cap của session và TTL của entitlement không phải cùng một bộ đếm**. Test phải ở **điểm thực thi hành động production**.

## 35. KPI và giám sát hiệu quả Absolute timeout

Một dashboard quản trị cần đo **kết quả thực thi**, không chỉ số lượng session đã ghi log hết hạn.

| KPI | Định nghĩa/đo lường gợi ý | Rủi ro phản ánh |
| --- | --- | --- |
| **Sessions with absolute deadline** | Session thuộc scope có `absoluteExpiresAt` hợp lệ ÷ tất cả session phải có. | Thiếu hard-cap policy. |
| **Deadline immutability** | Session không bị cập nhật hard deadline bởi hoạt động/refresh thường. | Sliding timeout vô hạn. |
| **Expired session deny rate** | Request dùng session đã hết hard cap bị PEP từ chối ÷ số request kiểm được. | Hiệu lực enforcement. |
| **Post-deadline access count** | Request/giao dịch được chấp nhận sau hard deadline trái policy. | Lỗi critical cần ưu tiên. |
| **Expired refresh family misuse** | Các lần family cũ tiếp tục cấp token sau hard cap. | Refresh lifecycle bị bypass. |
| **Token overshoot distribution** | Token `exp` vượt session deadline bao lâu. | Cửa sổ API access sau timeout. |
| **Cross-node expiry consistency** | Tỷ lệ gateway/PEP đưa ra quyết định nhất quán ở deadline. | Clock/cache stale. |
| **Idle vs absolute expiry reasons** | Phân bố lý do hết phiên, không gộp chung. | Khả năng đặt policy đúng nhu cầu. |
| **Reauthentication success/friction** | Tỷ lệ reauth hợp lệ, lỗi và tác vụ người dùng bị gián đoạn. | Cân bằng UX và bảo mật. |
| **Revocation propagation latency** | Từ JML/security revoke đến khi PEP thực sự từ chối. | Quyền tồn dư theo sự kiện. |
| **Privileged session overrun** | JIT/PAM action được phép sau privilege TTL. | Rủi ro admin quyền cao. |
| **Unverifiable session paths** | Các API/app/session không có cách xác minh hard cap. | Giới hạn coverage kiểm soát. |
| **Session store availability** | Lỗi đọc deadline và cách policy xử lý. | Fail-open rủi ro. |
| **Clock skew alerts** | Node/issuer/PEP vượt ngưỡng đồng bộ giờ. | Sai so sánh timeout. |

### 35.1. Mẫu số và giới hạn phải công bố

Một báo cáo “100% sessions expire” chỉ có ý nghĩa khi biết:

- Những ứng dụng, tenants và API nào thuộc scope.
- Bao nhiêu phiên là cookie server-side, JWT stateless, refresh family hoặc PAM.
- Bao nhiêu đường access có kiểm PEP thực tế.
- Thời điểm `asOf`, thời gian delay của log và ngưỡng clock skew.
- Những nơi **không thể quan sát token/session** hoặc chỉ có provider ACK.

Nếu chỉ kiểm session store của portal nhưng không kiểm cloud API bearer tokens, không được kết luận hệ thống toàn doanh nghiệp tuân thủ hard cap.

### 35.2. Báo cáo vận hành minh họa

~~~text
SESSION ABSOLUTE TIMEOUT – EXAMPLE REPORT
Report as-of: 2026-12-01 10:00 +07:00
Scope: 5 web applications, 3 protected APIs

In-scope session families: 2,000
Families with configured hard deadline: 2,000
Expired-session requests observed: 240
Expired-session requests denied by PEP: 238
Accepted after deadline: 2 (critical findings)

Refresh tokens issued beyond family deadline: 1 family
Unknown/unverifiable API access paths: 1

Priority actions:
  1. Investigate the two accepted requests and their side effects.
  2. Fix refresh-family deadline handling.
  3. Add verification for the uncovered API path.
  4. Retest across gateways and session state caches.
~~~

Các số **hoàn toàn giả định**. 238/240 request bị chặn **không thể coi là đạt** nếu hai request còn lại cho phép thay cấu hình nhạy cảm. Severity và kiểm chứng thực tế quan trọng hơn một tỷ lệ trung bình đẹp.

## 36. Runbook khi phát hiện session vượt hard deadline

### Bước 1 – Xác nhận bằng chứng

Lấy **sessionRef, tenant, subject, createdAt, absoluteExpiresAt, requestAt, PEP decision và policy version**. Không lấy raw cookie/JWT vào ticket. Kiểm timezones/clock skew và liệu session có thực sự được tạo mới qua reauthentication hợp lệ không.

### Bước 2 – Kiểm đường truy cập và tác động

Xác định **UI, API, refresh token, PAM, mobile, workload** nào đang chấp nhận phiên/credential ngoài deadline. Phân biệt:

- Chỉ UI hiển thị sai countdown.
- Backend nhận request nhưng chưa thực thi action.
- Backend cho phép thao tác thật sau deadline.
- Token gia hạn hoặc phiên bị hồi sinh dù đã revoked.

### Bước 3 – Giảm thiểu theo rủi ro

Theo quy trình được ủy quyền, có thể **revoke session/token family, giảm quyền tại API, chặn session renewal, khóa credential bị nghi lộ và áp gateway rules**. Không xóa bằng chứng hoặc sửa policy thành deadline dài hơn chỉ để hết cảnh báo.

### Bước 4 – Tìm nguyên nhân

Các nguồn lỗi thường gặp:

- Middleware sliding `expiresAt`.
- Cache TTL không xét hard deadline.
- Refresh token family rotation reset max age.
- JWT `exp` vượt hard cap và API không có session check.
- IdP/RP timeout mismatch và silent login.
- Clock skew, lag từ token revoke/SCIM/HRIS.
- Worker async tiếp tục grant hoặc commit sau revoke.
- Session store fail-open khi mất kết nối.

### Bước 5 – Sửa và retest

Chạy lại **negative/positive/boundary tests**, xác minh quyền thực tế và ghi:

~~~text
Defect ID: SES-ABS-2026-007
Policy: session-policy-v7
Affected layer: ERP API gateway + refresh issuer
Expected: No request from old session after 17:00.
Observed: API authorized request at 17:02.
Cause: Last-issued JWT exp exceeded session hard deadline.
Mitigation: Revoke affected token family and block stale sessions.
Fix: Bound token issuance + enforce deadline at resource.
Retest: AT-05, AT-08, AT-09, AT-18, AT-19.
Evidence: traceId, sessionRef, policyVersion, API readback.
Status: OPEN UNTIL VERIFIED
~~~

### Bước 6 – Đóng có xác minh

Chỉ kết luận **RESOLVED** khi đã kiểm đường bị lỗi và các đường liên quan không còn chấp nhận session/refresh trái chính sách, đồng thời mọi side effects/rủi ro được xử lý. Nếu không thể kiểm một API, ghi **UNVERIFIABLE** với owner, mitigation và hạn thay vì đánh dấu PASS.

## 37. Những sai lầm thường gặp khi thiết kế Absolute timeout

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Chỉ cấu hình idle timeout** | Hoạt động liên tục giữ phiên vô hạn. | Thêm hard deadline bất biến. |
| **Refresh reset createdAt** | Absolute trở thành sliding timeout. | Giữ family/session start và deadline cố định. |
| **Chỉ dùng cookie Max-Age** | Browser hoặc client khác vẫn có thể gửi session ID/token. | Kiểm expiry/revoke tại server/PEP. |
| **Chỉ dùng JavaScript countdown** | Tab ngủ, clock client sai, API bypass. | Server authoritative time. |
| **Chỉ dùng cleanup job** | Session được chấp nhận trong lúc chờ xóa. | Request-time deadline validation. |
| **JWT exp dài hơn session cap** | API sống sau khi web logout. | Cap token lifetime hoặc resource session enforcement. |
| **Token rotation không có family max age** | Cấp token mới liên tục. | Tách sliding refresh với hard cap. |
| **Silent SSO = reauth mới** | Assurance cũ được dùng vô hạn. | Kiểm auth_time và yêu cầu reauth phù hợp. |
| **Nhầm SAML assertion expiry với SP session expiry** | Phiên SP kéo dài ngoài dự định. | SP absolute timeout riêng. |
| **PAM UI hết giờ nhưng cloud token còn sống** | Privileged action ngoài JIT TTL. | Kiểm quyền tại resource, xử lý credential/session. |
| **Background polling tính thành hoạt động người dùng** | Idle timeout không hoạt động. | Định nghĩa meaningful activity. |
| **Leaver chờ hard deadline** | Quyền còn sau termination. | Event-driven revoke và effective-access verification. |
| **Mover chỉ đổi group mà không chặn session cũ** | Quyền cũ còn trong token/local role. | Revalidate authorization và revoke target grants. |
| **Không phân biệt nhiều phiên/thiết bị** | Logout-all hoặc device revoke chưa đầy đủ. | Session/family inventory theo principal/tenant/device. |
| **Gateway cache result ACTIVE quá lâu** | Session sống quá hard deadline. | TTL cap và local deadline check. |
| **Không theo dõi clock skew** | Node chấp nhận request khác nhau. | Trusted time, skew monitoring và test. |
| **Chỉ báo logout UI thành công** | Resource API có thể vẫn chấp nhận token. | Test API và trạng thái đích. |
| **Gia hạn session bằng approval đã hết hiệu lực** | Self-approval/privilege creep. | Reauth/approval authority và policy checks. |
| **Đăng nhập lại làm sống token family cũ** | Revoked credentials có thể tái sử dụng. | New session family, invalidate old refs. |
| **Không báo đường không kiểm chứng** | Kết luận tuân thủ sai. | Exception/coverage rõ và deadline khắc phục. |

## 38. Checklist triển khai Absolute timeout

### 38.1. Policy và định nghĩa

1. Đã xác định **session nào** có absolute timeout: IdP, SP/RP, BFF, API, PAM, workload không?
2. Đã định nghĩa **mốc bắt đầu** `createdAt/authTime` và **hard deadline** cho từng phiên/nhóm không?
3. `absoluteExpiresAt` có được giữ **bất biến theo request thường/heartbeat/refresh** không?
4. Có phân biệt **idle timeout, access-token exp, refresh family, reauthentication interval và JIT TTL** không?
5. Có risk tier theo **resource/action, role/privilege, device trust và yêu cầu nghiệp vụ** không?
6. Có quy tắc về **reauthentication/new session** thay vì âm thầm kéo dài phiên cũ không?

### 38.2. Enforcement và giao thức

7. Server/PEP có từ chối request khi `now >= absoluteExpiresAt` không?
8. Tất cả đường **web/API/mobile/BFF** thuộc scope có thực thi cùng ranh giới security không?
9. Cookie `Max-Age/Expires` có được hiểu là **client storage**, không thay server expiry không?
10. Có chống **session fixation**, dùng session ID ngẫu nhiên và rotation khi cần không?
11. OAuth access token `exp` có thể vượt hard cap không; nếu có, resource kiểm bằng gì?
12. Refresh token/family có **absolute max age** không trượt và revoke đúng không?
13. OIDC `max_age/auth_time` có được sử dụng đúng để kiểm recent authentication khi policy yêu cầu không?
14. SAML assertion/IdP session có được phân biệt với SP session và có logout integration test không?
15. Có quản lý **JWT introspection/denylist/version cache và leeway** theo giới hạn thực tế không?
16. Với long-running job/WebSocket/DB session, có quy tắc revalidation và hard connection cap không?

### 38.3. Lifecycle và rủi ro

17. **Joiner** có bị chặn trước Start date nếu session preboarding còn sống không?
18. **Mover** có bị thu hồi quyền cũ giữa phiên ngay khi có hiệu lực theo policy không?
19. **Leaver** có bị chặn trước hard deadline, bao gồm IdP, app, token, SCIM và PAM không?
20. **Rehire** có tránh tái sử dụng session/token family của Engagement cũ không?
21. Device LOST/HIGH_RISK có thể làm revoke/restrict session đang sống không?
22. Privileged elevation/PAM có TTL riêng, SoD, approval và target verification không?
23. Workload/service accounts có token/certificate/connection lifetime và owner phù hợp không?
24. Có phương án emergency access kiểm soát khi hạ tầng SSO/IdP gặp sự cố không?

### 38.4. Kỹ thuật phân tán và kiểm toán

25. Đồng hồ server/issuer/PEP có được giám sát **clock skew và timezone** không?
26. Cache/replica có giới hạn TTL không vượt session deadline không?
27. Concurrent refresh/revoke/expiry có chống **resurrection hoặc double issuance** không?
28. Khi session store/IdP/SCIM lỗi, có policy **UNKNOWN/FAIL-SAFE** theo risk không?
29. Background polling có làm trượt idle nhưng không được làm trượt absolute không?
30. Có audit **sessionRef, start, deadline, decision, reason, policyVersion và PEP** mà không lộ token không?
31. Có kiểm thử tại **trước, đúng, sau deadline**, kể cả token cấp sát hết hạn không?
32. Có test nhiều ứng dụng SSO, cross-tenant, device, reauth và logout-all không?
33. Có test **session/API actual access** sau deadline, không chỉ UI hoặc provider ACK không?
34. Có phân biệt **PASS/FAIL/INDETERMINATE/NOT_RUN** và nêu giới hạn coverage không?
35. KPI có đo **post-deadline access, refresh-family overrun, revoke latency, privileged-session overrun và unverifiable paths** không?
36. Khi phát hiện vi phạm, có owner, severity, remediation, evidence và verified closure không?

## 39. Kết luận: Absolute timeout là hard boundary, không phải nút logout trang trí

Một thiết kế session an toàn cần kết hợp:

~~~text
AUTHENTICATION / SESSION CREATION
    subject + tenant + authTime + sessionId
                   ↓
FIXED ABSOLUTE DEADLINE
    createdAt + hard lifetime (not sliding)
                   ↓
ONGOING REQUEST VALIDATION
    min(idle, absolute, applicable privilege TTL)
    + current authorization/device/risk checks
                   ↓
EVENT-DRIVEN REVOCATION
    Leaver / Mover / incident / device lost / policy change
                   ↓
SERVER / RESOURCE ENFORCEMENT
    cookie + refresh family + access token + API + PAM
                   ↓
VERIFICATION AND AUDIT
    expired/revoked session no longer authorizes protected actions
~~~

**Ghi nhớ:** **Absolute timeout đặt tuổi thọ tối đa không trượt theo hoạt động cho một phiên được xác định rõ**. Nó khác **idle timeout**, thời hạn cookie, `exp` của một access token và giới hạn reauthentication; các lớp **IdP/SSO, RP/SP, OAuth refresh family, API và PAM/JIT** có thể có deadline độc lập. **Hard deadline phải được thực thi tại server/PEP**, không chỉ hiện countdown hoặc xóa cookie trên trình duyệt. Khi **Joiner–Mover–Leaver**, thiết bị bị mất, session rủi ro cao hoặc privilege bị thu hồi, **quyền phải bị chặn theo sự kiện trước deadline nếu policy yêu cầu**. Chỉ có thể tuyên bố kiểm soát hiệu quả khi **đường truy cập thực tế ở API/ứng dụng bị từ chối đúng thời điểm**, có evidence, giám sát độ trễ, xử lý refresh/revoke và giới hạn quan sát được báo cáo minh bạch.
