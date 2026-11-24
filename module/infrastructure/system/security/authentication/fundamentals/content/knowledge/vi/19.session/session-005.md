# Session expiry

> **Chương:** Session  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Thời hạn phiên xác thực, idle timeout, absolute timeout, gia hạn và xoay vòng session identifier, hết hạn token, thu hồi phiên và xử lý trạng thái phiên trong hệ thống phân tán.

## 1. Session expiry là gì?

**Session expiry (hết hạn phiên)** là thời điểm hoặc điều kiện khiến một phiên xác thực không còn được chấp nhận để truy cập tài nguyên. Sau khi người dùng đăng nhập thành công, ứng dụng thường tạo một session để duy trì trạng thái đã xác thực qua nhiều request. Phiên không nên tồn tại vô thời hạn: nó cần có giới hạn theo thời gian, hoạt động, rủi ro và chính sách của hệ thống.

Ví dụ, một nhân viên đăng nhập vào cổng quản trị lúc 9 giờ sáng. Nếu họ để máy tính không hoạt động, hệ thống có thể yêu cầu đăng nhập lại sau 15 phút không có hoạt động. Ngay cả khi họ sử dụng liên tục, phiên cũng có thể buộc kết thúc sau 8 giờ để giới hạn thời gian một cookie bị đánh cắp còn giá trị.

Session expiry giúp giảm **cửa sổ sử dụng của phiên bị lộ** và giới hạn thời gian một trạng thái xác thực cũ tiếp tục được chấp nhận. Nó là một lớp kiểm soát trong vòng đời phiên, bên cạnh xác thực ban đầu, phân quyền, thu hồi và bảo vệ token.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt idle timeout, absolute timeout và thời hạn của token.
- Thiết kế quy tắc hết hạn và gia hạn cho phiên web, ứng dụng di động và API.
- Giải thích cách cookie, session store và refresh token tham gia vòng đời phiên.
- Xử lý logout, đổi mật khẩu, thu hồi credential và sự cố chiếm phiên.
- Nhận diện lỗi đồng hồ, cache, race condition và cập nhật phiên trong hệ thống phân tán.
- Xây dựng kiểm thử để xác nhận phiên hết hạn và không thể tiếp tục truy cập.

## 2. Session không nên sống mãi

Một session thường gắn với một chủ thể đã xác thực và chứa hoặc tham chiếu đến trạng thái như:

- ID phiên ngẫu nhiên.
- Account/principal ID.
- Thời điểm tạo và thời điểm hoạt động gần nhất.
- Thời điểm hết hạn tuyệt đối.
- Mức hoặc phương thức xác thực đã hoàn tất.
- Trạng thái thu hồi, thiết bị hoặc ngữ cảnh cần thiết.

Client thường chỉ giữ một session identifier trong cookie hoặc một token tương đương. Server tra cứu trạng thái phiên hoặc xác minh token để quyết định request có được tiếp tục không.

Nếu phiên không có giới hạn, một cookie bị đánh cắp có thể tồn tại lâu sau khi người dùng rời máy, đổi vai trò hoặc không còn làm việc tại tổ chức. Hết hạn giúp giảm rủi ro nhưng không thay thế thu hồi chủ động khi phát hiện sự cố.

### Ba câu hỏi khác nhau

1. **Phiên có còn trong thời hạn không?** Kiểm tra idle và absolute expiry.
2. **Phiên có còn được hệ thống chấp nhận không?** Kiểm tra trạng thái thu hồi, tài khoản, credential và chính sách.
3. **Phiên có quyền thực hiện hành động này không?** Kiểm tra authorization đối với tài nguyên cụ thể.

Một phiên chưa hết hạn vẫn có thể bị thu hồi. Một phiên còn active cũng không tự cấp quyền quản trị hoặc quyền đọc mọi dữ liệu.

## 3. Hai loại timeout cơ bản

### Idle timeout — hết hạn do không hoạt động

**Idle timeout** giới hạn thời gian phiên được giữ khi không có hoạt động phù hợp từ người dùng. Nếu thời điểm hoạt động hợp lệ cuối cùng là 10:00 và idle timeout là 20 phút, phiên có thể hết hạn lúc 10:20 nếu không có hoạt động mới được công nhận.

Idle timeout giúp giảm nguy cơ phiên bị bỏ quên trên máy dùng chung hoặc thiết bị không được khóa. Tuy nhiên, cần xác định thế nào là hoạt động:

- Request thực sự do người dùng khởi tạo có thể cập nhật last activity.
- Background polling, auto-refresh, telemetry hoặc request tự động không nhất thiết chứng minh người dùng đang hiện diện.
- Request chỉ đọc một tài nguyên không nhất thiết nên kéo dài phiên đặc quyền.
- Hoạt động từ kẻ tấn công đang dùng cookie bị đánh cắp cũng có thể làm phiên tiếp tục sống nếu server tin mọi request.

Vì vậy, hệ thống nên phân loại hoạt động có ý nghĩa, không tự động gia hạn session chỉ vì có bất kỳ request nào.

### Absolute timeout — thời hạn tuyệt đối

**Absolute timeout** giới hạn tổng thời gian sống của phiên tính từ lúc được tạo hoặc từ lần xác thực gần nhất theo chính sách. Hoạt động liên tục không thể kéo dài phiên vượt qua thời hạn này.

Ví dụ, phiên được tạo lúc 09:00 với absolute timeout 8 giờ sẽ kết thúc muộn nhất lúc 17:00. Nếu người dùng có hoạt động lúc 16:59, idle timeout có thể được làm mới nhưng absolute expiry vẫn là 17:00.

Absolute timeout buộc người dùng xác thực lại định kỳ và giới hạn thời gian sử dụng một session identifier bị đánh cắp. Nó đặc biệt hữu ích cho tài khoản đặc quyền, dữ liệu nhạy cảm và thiết bị dùng chung.

### So sánh

| Thuộc tính | Idle timeout | Absolute timeout |
|---|---|---|
| Bắt đầu tính từ | Hoạt động hợp lệ gần nhất | Lúc tạo phiên hoặc lần xác thực gốc |
| Có thể được làm mới? | Có, khi có hoạt động được chính sách chấp nhận | Không, trừ khi tạo phiên mới sau xác thực lại |
| Mục tiêu | Kết thúc phiên bị bỏ quên | Giới hạn tổng thời gian phiên tồn tại |
| Điểm yếu nếu dùng riêng | Phiên có thể sống mãi nếu có request liên tục | Người dùng có thể bị đăng xuất dù đang làm việc |
| Cách dùng phổ biến | Kết hợp absolute timeout | Kết hợp idle timeout và step-up |

~~~mermaid
timeline
    title Ví dụ idle timeout và absolute timeout
    09:00 : Đăng nhập, tạo phiên
    09:10 : Hoạt động hợp lệ, cập nhật idle timer
    09:25 : Không hoạt động
    09:40 : Idle timeout 15 phút đạt ngưỡng, phiên hết hạn
~~~

Trong ví dụ, phiên hết hạn lúc 09:40 dù absolute timeout 8 giờ chưa đạt. Nếu người dùng tiếp tục hoạt động hợp lệ, idle deadline có thể thay đổi nhưng absolute deadline vẫn cố định.

## 4. Sliding expiration và fixed expiration

Hai cách quản lý thời hạn thường gặp:

**Fixed expiration** đặt một deadline cố định. Các request không tự kéo dài deadline. Đây thường là cách áp dụng cho absolute timeout.

**Sliding expiration** dời deadline khi có hoạt động được chấp nhận. Nó thường được dùng cho idle timeout: mỗi hoạt động hợp lệ cập nhật thời điểm hoạt động hoặc thời điểm hết hạn mới.

Ví dụ với sliding idle timeout 20 phút:

| Thời điểm | Hoạt động | Idle deadline sau hoạt động |
|---|---|---|
| 09:00 | Đăng nhập | 09:20 |
| 09:12 | Người dùng mở báo cáo | 09:32 |
| 09:25 | Người dùng lưu thay đổi | 09:45 |
| 09:50 | Không có hoạt động từ 09:25 | Phiên đã hết hạn lúc 09:45 |

Không được để sliding expiration kéo dài phiên vô hạn nếu chính sách yêu cầu xác thực lại. Một thiết kế thường dùng cả hai:

**Phiên hợp lệ khi:** thời điểm hiện tại nhỏ hơn idle deadline, nhỏ hơn absolute deadline, và trạng thái phiên/tài khoản chưa bị thu hồi.

## 5. Công thức quyết định hết hạn

Một mô hình khái niệm:

~~~text
idle_deadline     = last_qualifying_activity_at + idle_timeout
absolute_deadline = authenticated_at + absolute_timeout

session_expired =
    now >= idle_deadline
    OR now >= absolute_deadline

session_usable =
    NOT session_expired
    AND session.revoked_at IS NULL
    AND account.status == ACTIVE
    AND other_session_policy_checks_pass
~~~

Tên trường và cách tính thực tế tùy hệ thống. Điều quan trọng là **deadline không do client tự quyết định**. Client có thể hiển thị đồng hồ đếm ngược để cải thiện trải nghiệm, nhưng server mới là nơi quyết định phiên còn hợp lệ hay không.

### Server là nguồn thời gian có thẩm quyền

Không tin thời gian do trình duyệt hoặc thiết bị gửi lên để xác định phiên còn hạn. Người dùng có thể thay đổi đồng hồ máy, sửa JavaScript hoặc phát lại request. Server nên dùng đồng hồ hệ thống được đồng bộ và quy tắc nhất quán giữa các node.

Với hệ thống phân tán, cần chú ý:

- Các node phải đồng bộ thời gian đủ tốt.
- Quy định rõ clock skew được chấp nhận ở các giao thức token.
- Không dùng đồng hồ client làm nguồn duy nhất cho idle/absolute expiry.
- Tránh cập nhật last activity từ một node có đồng hồ lệch quá lớn.
- Dùng timestamp UTC hoặc dạng thời gian có quy ước rõ ràng để tránh lỗi múi giờ.

## 6. Cookie và server-side session expiry

Với session phía server, cookie thường chỉ chứa một ID ngẫu nhiên. Server lưu thông tin phiên trong database, cache hoặc session store.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Application
    participant S as Session store
    B->>A: Request + session cookie
    A->>S: Tra session ID
    S-->>A: Principal, createdAt, lastActivity, expiry, status
    A->>A: Kiểm tra idle, absolute, revoked, account status
    alt Phiên hợp lệ
        A->>S: Cập nhật lastActivity nếu request đủ điều kiện
        A-->>B: Response
    else Phiên hết hạn/thu hồi
        A-->>B: 401 hoặc redirect đăng nhập
    end
~~~

### Cookie attributes

Cookie session cần cấu hình phù hợp:

- **Secure:** chỉ gửi qua HTTPS.
- **HttpOnly:** JavaScript không đọc trực tiếp cookie.
- **SameSite:** giảm gửi cookie trong một số request cross-site, hỗ trợ phòng CSRF.
- **Path/Domain:** giới hạn phạm vi gửi cookie; tránh domain quá rộng nếu không cần.

Các thuộc tính này bảo vệ cách cookie được gửi và truy cập, nhưng không thay thế kiểm tra session expiry ở server. HttpOnly không ngăn XSS thực hiện request dưới phiên của người dùng; SameSite không giải quyết mọi trường hợp CSRF.

### Cookie Max-Age/Expires không phải nguồn quyết định duy nhất

Cookie có thể có Max-Age hoặc Expires để trình duyệt biết khi nào nên xóa cookie. Tuy nhiên:

- Cookie hết hạn ở browser không tự xóa trạng thái session ở server.
- Client có thể gửi lại cookie đã lưu trước đó bằng công cụ HTTP.
- Cookie còn ở browser không có nghĩa server phải chấp nhận session.
- Session server-side cần kiểm tra expiry/revocation trên mỗi request hoặc qua cache có giới hạn.

Do đó, **server-side expiry là bắt buộc**. Thuộc tính hết hạn cookie chỉ hỗ trợ đồng bộ trải nghiệm phía client.

## 7. Token expiry không đồng nhất session expiry

Một hệ thống có thể dùng session cookie, access token và refresh token cùng lúc. Mỗi loại có thời hạn và mục đích khác nhau.

| Thành phần | Ý nghĩa của expiry | Điều cần kiểm tra |
|---|---|---|
| Session server-side | Trạng thái phiên không còn được chấp nhận | Idle, absolute, revoked, account status |
| Cookie session | Browser ngừng gửi cookie theo thời hạn | Server vẫn phải kiểm tra session |
| Access token | Token không được chấp nhận sau exp | Chữ ký, issuer, audience, exp, scope và trạng thái nếu cần |
| Refresh token | Không được dùng để xin token mới sau thời hạn/thu hồi | Client, token family, rotation và reuse |
| ID token | Hết hạn cho mục đích xác thực client theo OIDC | Issuer, audience, nonce, exp và quy tắc OIDC |

Access token hết hạn không nhất thiết kết thúc toàn bộ phiên người dùng nếu refresh token còn hiệu lực. Ngược lại, server có thể thu hồi refresh token hoặc session trong khi access token tự chứa vẫn còn hiệu lực đến exp nếu resource server không kiểm tra trạng thái bổ sung.

Vì vậy, cần định nghĩa rõ:

- Session gốc được tạo và kết thúc ở đâu?
- Access token có thời hạn bao lâu?
- Refresh token được cấp và xoay vòng như thế nào?
- Logout hoặc account suspension ảnh hưởng tới từng loại token ra sao?
- API kiểm tra thu hồi ngay hay chấp nhận độ trễ tối đa nào?

## 8. Sliding refresh và refresh token rotation

Refresh token thường có vòng đời dài hơn access token để người dùng không phải đăng nhập lại liên tục. Điều này tạo một tài sản có giá trị cao, nên phải có expiry và cơ chế rotation/revocation.

### Refresh token rotation

Khi client dùng refresh token hiện tại, authorization server cấp refresh token mới và làm token cũ mất hiệu lực theo chính sách. Nếu token cũ xuất hiện lại sau khi đã xoay vòng, có thể đó là dấu hiệu bị sao chép hoặc replay.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: Refresh token R1
    AS->>AS: Kiểm tra R1 active, đúng client và chưa hết hạn
    AS->>AS: Thu hồi R1, phát hành R2 và access token mới
    AS-->>C: Access token mới + R2
    Note over C,AS: Nếu R1 bị dùng lại, phát hiện reuse và xử lý token family theo chính sách
~~~

Rotation không có nghĩa refresh token được gia hạn vô hạn. Nên có giới hạn thời gian tuyệt đối của grant/token family và điều kiện xác thực lại. Nếu mỗi lần refresh lại đặt absolute expiry mới mà không có trần, một token bị đánh cắp có thể giữ quyền truy cập vô thời hạn.

### Race condition khi refresh

Ứng dụng có thể gửi hai request refresh gần như đồng thời, ví dụ nhiều API call cùng nhận 401. Nếu request thứ nhất xoay R1 thành R2, request thứ hai vẫn gửi R1 và bị coi là reuse. Client nên đồng bộ refresh, chỉ có một thao tác refresh đang chạy cho một token family và xử lý retry có kiểm soát.

Authorization server cũng cần định nghĩa hành vi khi phát hiện reuse để tránh khóa nhầm do request hợp lệ bị lặp, đồng thời không mở cửa sổ quá rộng cho replay.

## 9. Re-authentication và step-up

Hết hạn phiên không phải cách duy nhất để yêu cầu người dùng chứng minh danh tính lại. Hệ thống có thể yêu cầu **reauthentication** khi:

- Phiên đã quá lâu kể từ lần xác thực gần nhất.
- Người dùng đổi mật khẩu, email khôi phục hoặc phương thức MFA.
- Người dùng thêm passkey hoặc thiết bị tin cậy mới.
- Thực hiện hành động nhạy cảm như cấp quyền quản trị, xuất dữ liệu hoặc thay tài khoản thanh toán.
- Có tín hiệu rủi ro như thiết bị mới, vị trí bất thường hoặc token reuse.

**Step-up authentication** yêu cầu phương thức hoặc mức bảo đảm cao hơn cho một hành động cụ thể. Ví dụ, phiên thông thường cho phép xem báo cáo; trước khi xuất toàn bộ dữ liệu, hệ thống yêu cầu passkey với user verification.

Reauthentication không nên chỉ dựa trên việc client gửi timestamp. Server cần biết thời điểm và phương thức xác thực đã hoàn tất, gắn với phiên và nguồn phát hành tin cậy.

### Auth time và freshness

Trong các giao thức liên kết, claim hoặc thông tin như auth_time có thể cho biết lần xác thực gần nhất. Resource server hoặc RP cần hiểu claim này theo giao thức và kiểm tra freshness theo chính sách. Không tự suy luận rằng một token vừa được refresh đồng nghĩa người dùng vừa xác thực lại bằng MFA.

## 10. Logout, expiry và revocation

Ba hành động có liên quan nhưng khác nhau:

- **Logout:** người dùng chủ động kết thúc phiên hoặc ứng dụng thực hiện sign-out.
- **Expiry:** phiên tự mất hiệu lực khi đạt điều kiện thời gian.
- **Revocation:** hệ thống chủ động vô hiệu hóa phiên/credential/token trước thời hạn do sự kiện hoặc quyết định chính sách.

Logout ở một client không tự động thu hồi tất cả phiên ở thiết bị khác nếu hệ thống không có chức năng đó. Đăng xuất khỏi ứng dụng cũng không nhất thiết đăng xuất khỏi IdP hoặc các ứng dụng SSO khác.

### Khi nào nên thu hồi?

- Người dùng báo thiết bị hoặc cookie bị mất.
- Phát hiện token reuse, đăng nhập bất thường hoặc phishing.
- Mật khẩu/MFA/passkey bị thay đổi do nghi ngờ chiếm quyền.
- Tài khoản bị đình chỉ, vô hiệu hóa hoặc nhân viên nghỉ việc.
- Quản trị viên chủ động kết thúc các phiên.
- Quyền hoặc trạng thái tài khoản thay đổi làm phiên cũ không còn phù hợp.

### Logout phía server

Với session store, logout nên đánh dấu phiên revoked hoặc xóa trạng thái phiên. Chỉ xóa cookie ở browser là chưa đủ nếu cookie đã bị sao chép trước đó.

Với JWT tự chứa, xóa token khỏi client không thu hồi bản sao đã bị đánh cắp. Cần thời hạn access token ngắn, refresh token revocation, denylist/jti, token version hoặc kiểm tra trạng thái phiên/tài khoản tùy yêu cầu.

## 11. Hệ thống phân tán và cache session

Trong hệ thống nhiều instance, session có thể được lưu trong Redis, database hoặc dịch vụ session tập trung. Mọi node xử lý request cần nhìn thấy trạng thái phiên nhất quán ở mức phù hợp.

### Các lỗi thường gặp

1. Node A thu hồi phiên nhưng node B vẫn dùng cache active cũ.
2. Một node cập nhật last activity nhưng node khác ghi đè bằng timestamp cũ.
3. Cache TTL dài hơn idle/absolute timeout.
4. Replication lag khiến phiên đã thu hồi vẫn được chấp nhận.
5. Đồng hồ giữa node lệch làm phiên hết hạn sớm hoặc muộn.
6. Request đồng thời cập nhật session sau khi phiên đã bị thu hồi.

### Chính sách nhất quán

| Dữ liệu | Yêu cầu thiết kế |
|---|---|
| Revocation status | Cần lan truyền nhanh; cache phải có giới hạn và invalidation |
| Absolute expiry | Deadline cố định, không bị ghi đè bởi last activity |
| Last activity | Cập nhật nguyên tử/đơn điệu hoặc tránh ghi timestamp cũ |
| Account status | Đồng bộ đủ nhanh theo mức rủi ro |
| Token family state | Rotation/reuse cần thao tác nguyên tử |

Không để TTL cache trở thành cơ chế duy nhất xác định session expiry nếu TTL có thể lệch với chính sách. Có thể lưu deadline trong bản ghi và kiểm tra lại thời gian ở mỗi lần truy cập.

## 12. Race condition quanh thời điểm hết hạn

Giả sử phiên hết hạn lúc 10:00. Một request bắt đầu lúc 09:59:59 và request khác bắt đầu lúc 10:00:01. Server cần có quy tắc rõ:

- Request bắt đầu sau deadline phải bị từ chối.
- Request đang xử lý khi deadline tới có thể được hoàn tất hoặc hủy tùy chính sách; cần tránh cấp thêm quyền/phiên mới từ trạng thái đã hết hạn.
- Cập nhật last activity phải kiểm tra phiên chưa hết hạn và chưa bị thu hồi trong cùng giao dịch hoặc thao tác nguyên tử.
- Không cho một request cũ ghi đè trạng thái revoked bằng active.

### Mã giả kiểm tra session

~~~typescript
async function validateSession(sessionId, now) {
  const session = await sessionStore.get(sessionId);
  if (!session) return { valid: false, reason: "not_found" };

  if (session.revokedAt) {
    return { valid: false, reason: "revoked" };
  }
  if (now >= session.absoluteExpiresAt) {
    return { valid: false, reason: "absolute_expired" };
  }
  if (now >= session.lastActivityAt + IDLE_TIMEOUT_MS) {
    return { valid: false, reason: "idle_expired" };
  }

  const account = await accountStore.get(session.accountId);
  if (!account || account.status !== "ACTIVE") {
    return { valid: false, reason: "account_inactive" };
  }

  return { valid: true, session, account };
}
~~~

Đây là pseudocode mô tả điều kiện. Trong triển khai thật, cập nhật activity cần kiểm tra lại trạng thái bằng thao tác nguyên tử để tránh race với logout/revocation. Không lấy now từ client và không chỉ dựa vào TTL cache.

### Gia hạn có điều kiện

Một cập nhật idle activity có thể dùng điều kiện tương đương:

~~~sql
UPDATE sessions
SET last_activity_at = :server_now
WHERE session_id = :session_id
  AND revoked_at IS NULL
  AND absolute_expires_at > :server_now
  AND last_activity_at + :idle_timeout > :server_now;
~~~

Nếu không có hàng nào được cập nhật, request không được tự làm sống lại phiên đã hết hạn. Cú pháp và khả năng tính interval phụ thuộc hệ quản trị dữ liệu; ví dụ chỉ nêu nguyên tắc cập nhật có điều kiện.

## 13. Lựa chọn timeout theo rủi ro

Không có một con số timeout phù hợp cho mọi ứng dụng. Cần cân bằng giữa mức nhạy cảm, thiết bị, môi trường, trải nghiệm và khả năng xác thực lại.

| Loại ứng dụng | Idle timeout tham khảo | Absolute timeout tham khảo | Lưu ý |
|---|---:|---:|---|
| Nội dung ít nhạy cảm | 30–60 phút | 12–24 giờ | Cần đánh giá thiết bị dùng chung |
| Cổng nghiệp vụ nội bộ | 15–30 phút | 8–12 giờ | Tùy chính sách tổ chức và thiết bị |
| Dữ liệu nhân sự/tài chính | 5–15 phút | 4–8 giờ | Step-up cho xuất dữ liệu/thay đổi quan trọng |
| Bảng điều khiển quản trị | 5–15 phút | 1–8 giờ | Ưu tiên xác thực chống phishing, giám sát và re-auth |
| Thiết bị dùng chung/kiosk | Rất ngắn hoặc kết thúc khi rời tác vụ | Theo ca làm việc hoặc tác vụ | Logout rõ ràng, xóa dữ liệu cục bộ |

Các khoảng trên chỉ là ví dụ khởi đầu để thảo luận, **không phải chuẩn bắt buộc**. Hãy đối chiếu tiêu chuẩn, yêu cầu ngành, threat model và nghiên cứu trải nghiệm của tổ chức. Không nên lấy một con số trong bảng áp dụng máy móc.

### Những yếu tố ảnh hưởng

- Giá trị và độ nhạy của dữ liệu.
- Khả năng chiếm thiết bị và khả năng khóa màn hình.
- Người dùng có làm việc trên thiết bị cá nhân hay thiết bị dùng chung.
- Có MFA/passkey và mức xác thực gần nhất hay không.
- Phiên có quyền quản trị hoặc thực hiện giao dịch không.
- Khả năng thu hồi session/token nhanh ở mọi dịch vụ.
- Yêu cầu vận hành như job dài, upload/download hoặc tác vụ kéo dài.

## 14. Phiên dài và tác vụ nền

Một số công việc kéo dài hơn idle timeout: tải tệp lớn, xử lý báo cáo, chỉnh sửa tài liệu hoặc chạy job. Không nên kéo dài session chỉ vì tiến trình nền vẫn gửi heartbeat.

Thiết kế có thể:

- Tách tác vụ nền khỏi phiên tương tác; job chạy bằng service identity hoặc token riêng có phạm vi hẹp.
- Cho phép hoàn tất một request đã được ủy quyền trước deadline theo chính sách, nhưng không cấp quyền mới sau khi phiên hết hạn.
- Yêu cầu người dùng xác thực lại trước khi tiếp tục thao tác nhạy cảm.
- Dùng cơ chế lưu nháp và khôi phục công việc sau đăng nhập lại.
- Cảnh báo trước khi hết hạn để người dùng lưu thay đổi, nhưng server vẫn phải áp dụng deadline.

Không để một request polling ẩn hoặc websocket heartbeat vô hạn kéo dài phiên người dùng nếu người dùng đã rời thiết bị. Xác định rõ tín hiệu nào được tính là hoạt động tương tác.

## 15. Tình huống thực hành: phiên quản trị bị bỏ quên

**Bối cảnh:** Một quản trị viên đăng nhập bằng passkey vào dashboard. Session cookie có idle timeout 30 phút, nhưng không có absolute timeout. Frontend gửi request kiểm tra thông báo mỗi phút và middleware cập nhật last activity với mọi request.

### Phân tích rủi ro

1. Quản trị viên rời máy nhưng browser vẫn chạy.
2. Request polling tiếp tục gửi cookie mỗi phút.
3. Server cập nhật last activity cho mỗi request tự động.
4. Idle timeout không bao giờ đạt ngưỡng.
5. Nếu cookie bị đánh cắp, phiên có thể sống rất lâu.

### Cách sửa

- Thêm absolute timeout để giới hạn tổng thời gian phiên.
- Không tính polling/telemetry là hoạt động người dùng.
- Có thể yêu cầu xác nhận hiện diện hoặc re-auth trước hành động đặc quyền.
- Khi người dùng logout hoặc tài khoản bị thu hồi, đánh dấu session revoked phía server.
- Đảm bảo cache/session store trên mọi node nhận trạng thái thu hồi đủ nhanh.
- Kiểm thử rằng cookie cũ bị từ chối sau deadline, kể cả khi client vẫn gửi request.

### Bảng quyết định

| Sự kiện | Idle deadline | Absolute deadline | Kết quả |
|---|---|---|---|
| Đăng nhập 09:00 | 09:30 | 17:00 | Phiên active |
| Người dùng thao tác 09:10 | 09:40 | 17:00 | Phiên tiếp tục |
| Polling 09:20 | Không đổi nếu không phải qualifying activity | 17:00 | Không kéo dài phiên |
| Người dùng thao tác 09:35 | 10:05 | 17:00 | Phiên tiếp tục vì thao tác trước idle deadline |
| Người dùng thao tác 10:06 | 10:05 đã qua | 17:00 | Phải đăng nhập lại |
| Phiên mới sau re-auth 10:10 | 10:40 | 18:10 | Deadline mới theo chính sách |

Các mốc chỉ minh họa idle timeout 30 phút và absolute timeout 8 giờ. Hệ thống có thể chọn cách xử lý khác cho request đã bắt đầu trước deadline, nhưng phải quy định nhất quán.

## 16. Kiểm thử session expiry

Kiểm thử cần bao phủ thời gian, trạng thái, thiết bị và nhiều node:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không có hoạt động đến idle deadline | Request tiếp theo bị từ chối |
| Có hoạt động hợp lệ trước idle deadline | Idle deadline được gia hạn theo chính sách |
| Polling/telemetry chạy liên tục | Không kéo dài idle nếu không được tính là hoạt động |
| Người dùng hoạt động liên tục qua absolute deadline | Phiên vẫn hết hạn |
| Cookie có Max-Age còn hiệu lực nhưng server session hết hạn | Server từ chối |
| Cookie bị xóa ở browser nhưng session server còn active | Browser không gửi ID đó nữa; server vẫn cần TTL/cleanup hoặc revocation cho bản ghi phiên |
| Session bị thu hồi ở node A | Node B không tiếp tục chấp nhận quá giới hạn nhất quán |
| Request đồng thời với logout | Không được tái kích hoạt phiên đã revoked |
| Refresh token đã xoay vòng bị dùng lại | Phát hiện reuse và xử lý token family |
| Tài khoản bị đình chỉ trước expiry | Phiên bị từ chối theo trạng thái tài khoản |
| Đồng hồ client bị chỉnh | Không làm thay đổi quyết định expiry server-side |
| Request sau deadline gửi từ client tự tạo | Server vẫn từ chối |
| Phiên đặc quyền thực hiện thao tác nhạy cảm | Yêu cầu freshness/step-up nếu chính sách quy định |

### Đồng hồ trong kiểm thử

Không cần chờ thật nhiều phút trong mỗi test. Có thể dùng clock abstraction hoặc fake clock ở unit/integration test để kiểm tra trước, đúng và sau deadline. Cần thêm kiểm thử tích hợp cho cache, database và nhiều node vì fake clock đơn lẻ không phát hiện replication lag hoặc race condition.

## 17. Checklist thiết kế session expiry

- [ ] Phân biệt idle timeout, absolute timeout, token expiry và revocation.
- [ ] Deadline được tính và kiểm tra ở server, không tin đồng hồ client.
- [ ] Idle activity chỉ cập nhật bởi hoạt động được chính sách chấp nhận.
- [ ] Có absolute timeout để sliding expiration không kéo dài phiên vô hạn.
- [ ] Cookie có Secure, HttpOnly, SameSite và phạm vi domain/path phù hợp.
- [ ] Server kiểm tra expiry ngay cả khi cookie phía browser chưa hết hạn.
- [ ] Refresh token có expiry, rotation, reuse detection và revocation phù hợp.
- [ ] Logout và account suspension xử lý session/token ở mọi dịch vụ liên quan.
- [ ] Re-auth/step-up được yêu cầu cho thao tác nhạy cảm và phiên quá cũ.
- [ ] Cache và các node phân tán đồng bộ trạng thái expiry/revocation trong giới hạn yêu cầu.
- [ ] Cập nhật last activity không thể ghi đè trạng thái revoked hoặc làm sống lại phiên hết hạn.
- [ ] Có chính sách cho request dài, websocket, polling và tác vụ nền.
- [ ] Log đủ để điều tra nhưng không ghi cookie/session ID/token có thể sử dụng.
- [ ] Có kiểm thử idle, absolute, logout, refresh reuse, clock skew và race condition.

## Ghi nhớ

Session expiry giới hạn thời gian một trạng thái xác thực còn được chấp nhận. **Idle timeout** kết thúc phiên sau một khoảng không có hoạt động hợp lệ; **absolute timeout** giới hạn tổng thời gian kể từ khi xác thực. Kết hợp hai loại giúp vừa kết thúc phiên bị bỏ quên, vừa tránh sliding expiration kéo dài vô hạn.

Cookie expiry ở browser không thay thế kiểm tra server. Access token, refresh token và session có vòng đời khác nhau; logout, expiry và revocation cũng là những hành động khác nhau. Hãy kiểm tra deadline ở server, xử lý trạng thái nhất quán trong hệ thống phân tán, thu hồi khi có rủi ro và yêu cầu xác thực lại trước hành động nhạy cảm.
