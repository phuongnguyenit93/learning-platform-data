# Account suspension (Tạm ngưng tài khoản)

> **Chương:** Account lifecycle  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Thiết kế trạng thái tạm ngưng tài khoản như một biện pháp kiểm soát vòng đời có phạm vi, lý do, thời hạn và quy trình xem xét rõ ràng; bảo đảm trạng thái được thực thi nhất quán trên đăng nhập, session, token, API và các hệ thống liên kết, đồng thời hỗ trợ khôi phục có kiểm soát.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích account suspension và phân biệt với account lockout, disablement, deactivation, deletion và thu hồi credential.
2. Mô hình hóa trạng thái tài khoản, chuyển trạng thái và điều kiện cho phép đăng nhập hoặc sử dụng tài nguyên.
3. Xác định phạm vi của suspension: toàn tài khoản, một tenant, một ứng dụng, một phương thức xác thực hay một phiên.
4. Thiết kế enforcement nhất quán trên login, session store, access token, refresh token, API và hệ thống federation.
5. Xử lý phiên đang hoạt động, token đã phát hành, request đồng thời và cache phân tán khi tài khoản bị tạm ngưng.
6. Thiết kế quy trình suspend, review, reinstate và recovery có xác thực người yêu cầu, phân quyền và audit.
7. Phòng chống lạm dụng quyền quản trị, giả mạo sự kiện provisioning, account enumeration và việc tự động khóa nhầm.
8. Kiểm thử suspension, propagation, expiry, reactivation, tenant isolation và các tình huống lỗi hoặc race condition.

## 1. Account suspension là gì?

**Account suspension (tạm ngưng tài khoản)** là trạng thái trong đó hệ thống tạm thời hạn chế hoặc ngăn tài khoản sử dụng một phần hay toàn bộ chức năng trong một khoảng thời gian hoặc cho tới khi một điều kiện xem xét được đáp ứng.

Tài khoản có thể bị tạm ngưng vì:

- Có dấu hiệu account takeover hoặc credential compromise.
- Chủ tài khoản yêu cầu tạm dừng truy cập.
- Có yêu cầu điều tra hoặc review bảo mật.
- Tổ chức thay đổi trạng thái nhân sự, hợp đồng hoặc tư cách thành viên.
- Có dấu hiệu lạm dụng, vi phạm chính sách hoặc rủi ro vận hành.
- Hệ thống cần giữ tài khoản trong trạng thái chờ xác minh bổ sung.

Suspension là một quyết định về **quyền sử dụng tài khoản trong vòng đời hiện tại**. Nó không nhất thiết xóa danh tính, lịch sử, credential hoặc dữ liệu của người dùng. Khi nguyên nhân được xử lý, tài khoản có thể được khôi phục theo quy trình được kiểm soát.

### Ví dụ

Một học viên báo rằng điện thoại có passkey đã bị mất. Bộ phận hỗ trợ xác minh yêu cầu và tạm ngưng đăng nhập của tài khoản trong lúc thu hồi authenticator bị mất. Tài khoản vẫn tồn tại, dữ liệu học tập được giữ lại, nhưng các phiên hiện hành bị thu hồi và các lần đăng nhập mới bị từ chối cho đến khi người học hoàn thành quy trình khôi phục.

Tình huống này khác với xóa tài khoản. Mục tiêu là giảm nguy cơ truy cập trái phép trong khi vẫn giữ khả năng phục hồi danh tính và quyền lợi hợp lệ.

## 2. Phân biệt suspension với các trạng thái tài khoản khác

Các hệ thống thường dùng nhiều trạng thái gần nghĩa. Nếu không định nghĩa rõ, một thành phần có thể coi tài khoản bị khóa là tài khoản bị xóa, trong khi thành phần khác vẫn cho phép token tiếp tục truy cập.

| Trạng thái | Ý nghĩa | Phạm vi/thời gian thường gặp |
| --- | --- | --- |
| **Active** | Tài khoản được phép hoạt động theo policy. | Trạng thái bình thường. |
| **Suspended** | Tạm ngưng một phần hoặc toàn bộ khả năng sử dụng. | Có thể có thời hạn hoặc chờ review. |
| **Locked** | Tạm khóa đăng nhập, thường do failed attempts hoặc cơ chế bảo vệ tự động. | Thường ngắn hạn hoặc tới khi unlock. |
| **Disabled** | Tài khoản bị vô hiệu hóa theo quyết định quản trị hoặc nguồn vòng đời. | Có thể kéo dài đến khi được bật lại. |
| **Deactivated** | Tài khoản không còn hoạt động trong nghiệp vụ hoặc tổ chức. | Có thể chờ tái kích hoạt hoặc chuyển sang lưu trữ. |
| **Pending verification** | Chưa hoàn tất xác minh danh tính hoặc điều kiện kích hoạt. | Chờ người dùng hoặc tổ chức hoàn thành bước xác minh. |
| **Deleted** | Tài khoản đã đi qua quy trình xóa theo policy. | Có thể không thể khôi phục; dữ liệu xử lý theo retention/legal rules. |
| **Credential revoked** | Một credential cụ thể không còn được chấp nhận. | Có thể tài khoản vẫn active nếu còn phương thức khác. |

### Suspension và lockout

Lockout thường là biện pháp tự động sau một số lần xác thực thất bại. Suspension thường là trạng thái vòng đời rộng hơn, có thể do người dùng, quản trị viên, tổ chức hoặc risk engine khởi tạo.

Không nên biến mọi lockout thành suspension vĩnh viễn. Kẻ tấn công có thể cố ý nhập sai mật khẩu để khóa tài khoản của nạn nhân, gây denial of service. Lockout cần có giới hạn, rate limit, challenge hoặc quy trình mở khóa phù hợp.

### Suspension và credential revocation

Nếu một passkey bị mất, có thể chỉ cần thu hồi credential đó và yêu cầu đăng ký lại. Nếu có bằng chứng tài khoản bị chiếm, cần cân nhắc tạm ngưng toàn tài khoản, revoke phiên/token và kiểm tra các credential khác.

Phạm vi xử lý cần dựa trên sự cố thực tế. Thu hồi một credential không tự động chứng minh các credential khác an toàn; nhưng tạm ngưng toàn bộ tài khoản cũng có thể gây gián đoạn quá mức nếu rủi ro chỉ giới hạn ở một authenticator.

## 3. Phạm vi của suspension

Một thiết kế tốt phải xác định chính xác điều gì bị ngăn chặn. Từ “suspended” mà không có scope sẽ dễ tạo cách hiểu khác nhau giữa ứng dụng.

| Scope | Ví dụ | Tác động |
| --- | --- | --- |
| **Account-wide** | Tài khoản có dấu hiệu bị chiếm. | Không cho đăng nhập hoặc truy cập tài nguyên trong toàn hệ thống. |
| **Tenant-scoped** | Người dùng không còn tư cách trong một tổ chức. | Chặn truy cập tenant đó; có thể vẫn dùng tenant khác nếu policy cho phép. |
| **Application-scoped** | Tạm ngưng quyền dùng Staff Console. | Không truy cập ứng dụng cụ thể; tài khoản chung có thể còn active. |
| **Credential-scoped** | Một passkey hoặc chứng chỉ bị mất. | Credential đó bị revoke; phương thức khác có thể còn dùng được. |
| **Session-scoped** | Một session có dấu hiệu bị đánh cắp. | Chỉ session đó bị revoke. |
| **Action-scoped** | Tạm dừng thay đổi payout hoặc cấp quyền. | Người dùng vẫn truy cập các chức năng khác. |

### Mô hình hóa trạng thái và scope riêng

Không nên nhồi tất cả trạng thái vào một boolean duy nhất như suspended. Một mô hình có thể gồm:

- Trạng thái tài khoản: active, suspended, disabled, deleted.
- Phạm vi: global, tenant, application, credential, session hoặc action.
- Lý do: security incident, administrative review, user request, policy violation, organization status.
- Thời gian: createdAt, effectiveAt, expiresAt, reviewedAt.
- Nguồn: user, administrator, identity provider, HR/provisioning, risk engine.
- Trạng thái review: pending, approved, rejected, expired.
- Reference: case ID hoặc event ID liên quan.

Một ứng dụng chỉ nên thực thi đúng scope đã được phê duyệt. Không suy diễn account-wide từ một suspension ở tenant hoặc application.

## 4. Mô hình trạng thái tài khoản

Một state machine rõ giúp các thành phần áp dụng cùng một quy tắc và tránh chuyển trạng thái tùy tiện.

~~~mermaid
stateDiagram-v2
    [*] --> PendingVerification
    PendingVerification --> Active: Xác minh và kích hoạt
    Active --> Suspended: User/Admin/Policy decision
    Suspended --> Active: Review và reinstatement
    Suspended --> Disabled: Quyết định vô hiệu hóa dài hạn
    Active --> Disabled: Admin/Organization action
    Disabled --> Active: Reactivation được phê duyệt
    Active --> Deleted: Quy trình xóa
    Suspended --> Deleted: Quy trình xóa được phê duyệt
    Disabled --> Deleted: Quy trình xóa được phê duyệt
    Deleted --> [*]
~~~

Sơ đồ chỉ minh họa các trạng thái chính. Hệ thống thực tế có thể cần trạng thái phụ như suspension pending, under review, expired, appeal pending hoặc recovery required.

### Các nguyên tắc chuyển trạng thái

- Chỉ actor có quyền mới được suspend, lift suspension hoặc delete.
- Mọi chuyển trạng thái cần có event ID, actor, thời điểm, reason code và scope.
- Không tự động chuyển suspended về active chỉ vì hết thời gian nếu policy yêu cầu review.
- Nếu suspension có expiry tự động, phải định nghĩa hành động khi expiry: tự mở lại, chuyển pending review hay tiếp tục suspended.
- Không cho phép client gửi trạng thái tài khoản tùy ý trong request.
- Kiểm tra version/state hiện tại để tránh hai quản trị viên ghi đè quyết định của nhau.
- Các chuyển trạng thái nhạy cảm cần idempotency và audit.

### Suspension pending và suspension effective

Một số tổ chức cần quy trình phê duyệt trước khi thay đổi có hiệu lực. Có thể phân biệt:

- **Pending:** yêu cầu đã được tạo nhưng chưa có hiệu lực.
- **Effective:** enforcement đã được áp dụng.
- **Lift pending:** yêu cầu mở lại đang chờ phê duyệt.
- **Lifted:** suspension đã được gỡ.
- **Expired:** hết hạn theo policy và đã được xử lý.

Không nên hiển thị trạng thái “suspended” cho hệ thống downstream trước khi quyết định có hiệu lực, trừ khi policy cố ý dùng trạng thái pending để chặn tạm thời.

## 5. Những thành phần cần enforcement

Suspension chỉ hiệu quả khi mọi đường truy cập có liên quan đều kiểm tra trạng thái tài khoản.

Các điểm thường cần enforcement:

1. Authentication endpoint: không hoàn tất login cho subject bị suspend.
2. Session service: revoke hoặc đánh dấu session không còn hợp lệ.
3. Authorization server: ngừng cấp hoặc refresh token theo policy.
4. Resource server/API: kiểm tra trạng thái account/subject khi xử lý request.
5. Federation/RP: xử lý disable/logout event từ IdP hoặc nguồn quản trị.
6. Provisioning: đồng bộ trạng thái sang ứng dụng downstream.
7. Recovery flow: không cho dùng recovery để vượt qua suspension đang hiệu lực.
8. Administrative console: hiển thị trạng thái và cho phép hành động theo quyền.

### Quy tắc kiểm tra trung tâm

Một policy đơn giản có thể biểu diễn:

~~~text
if account.status != ACTIVE:
    deny_new_authentication()

if session.revoked:
    deny_request()

if account.scope_covers(request.tenant, request.application, request.action):
    deny_or_restrict_request()

otherwise:
    continue_authentication_and_authorization()
~~~

Đây là pseudocode khái niệm. Trạng thái tài khoản và scope phải được xác định từ nguồn server-side đáng tin cậy. Một tài khoản có thể active toàn cục nhưng suspended trong một tenant hoặc ứng dụng cụ thể.

## 6. Điều gì xảy ra với session đang hoạt động?

Một lỗi phổ biến là chỉ chặn lần đăng nhập mới. Người dùng đã có session hoặc cookie từ trước vẫn có thể tiếp tục truy cập.

Khi suspension có hiệu lực, policy cần quyết định:

- Revoke mọi session hiện tại hay chỉ session liên quan?
- Có kết thúc session ở IdP và các RP khác không?
- Có giữ phiên read-only để người dùng xem thông báo hoặc tải dữ liệu cá nhân không?
- Các phiên của administrator/support có bị ảnh hưởng không?
- Các session khác tenant có tiếp tục hoạt động không?

### Revoke session server-side

- Đánh dấu session reference là revoked.
- Xóa hoặc vô hiệu hóa session record.
- Đồng bộ trạng thái revoke tới các node/cache liên quan.
- Xóa cookie phía browser nếu có thể, nhưng không dựa vào việc xóa cookie như biện pháp duy nhất.
- Từ chối cookie cũ ở request tiếp theo.

Nếu session store phân tán, tất cả node cần nhìn thấy trạng thái revoke trong thời gian mục tiêu. Sticky session hoặc xóa cookie ở một browser không đủ để thu hồi session bị sao chép.

### Cần giữ session giới hạn?

Một số ứng dụng có thể cho phép người dùng bị suspend truy cập trang giải thích, tải dữ liệu cá nhân hoặc gửi appeal. Nếu có, hãy tạo một luồng hạn chế riêng:

- Chỉ cấp quyền cho endpoint được allowlist.
- Không giữ session authenticated đầy đủ.
- Không cho phép thay credential hoặc thay đổi dữ liệu nhạy cảm.
- Gắn trạng thái read-only/appeal-only rõ ràng.
- Có timeout ngắn và audit.

Không tái sử dụng session cũ với quyền đầy đủ chỉ để hiển thị trang thông báo.

## 7. Access token, refresh token và API

Suspension cần được áp dụng cả với token đã phát hành. Nếu chỉ chặn trang login, access token có thể tiếp tục gọi API.

### Refresh token

Authorization server nên kiểm tra trạng thái account và grant trước khi cấp access token mới. Khi suspension có hiệu lực, có thể revoke refresh token hoặc token family theo policy.

### Access token dạng opaque

Resource server có thể dùng introspection để hỏi authorization server token còn active không. Nếu trạng thái account hoặc token đã bị thu hồi, authorization server có thể trả active=false.

### JWT access token tự chứa

Resource server thường xác minh chữ ký và claim cục bộ. JWT đã phát hành có thể còn hợp lệ tới exp nếu không có kiểm tra trạng thái bổ sung.

Các lựa chọn:

- TTL access token ngắn.
- Token introspection hoặc kiểm tra trạng thái với cache có giới hạn.
- Denylist theo jti hoặc token/session reference.
- Subject/account version để so sánh với version hiện tại.
- Event-driven cache invalidation khi account bị suspend.
- Sender-constrained token nếu kiến trúc hỗ trợ và phù hợp.

Mỗi lựa chọn có trade-off giữa latency, availability và tốc độ thu hồi. Không tuyên bố token đã bị thu hồi tức thời nếu resource server chỉ kiểm tra chữ ký offline.

### API key và workload identity

Nếu tài khoản là service account hoặc workload identity, suspension cần xét các credential máy:

- API key.
- Client certificate.
- OAuth client credentials.
- Private key dùng ký client assertion.
- Workload identity binding.
- Refresh token hoặc long-lived secret.

Chặn interactive login không có nghĩa API key của service account đã bị thu hồi. Cần policy scope và cơ chế revoke cho từng loại credential.

## 8. Suspension trong SSO và federation

Với OIDC/SAML, IdP có thể là nguồn trạng thái tài khoản. Nhưng mỗi RP thường có local session riêng, nên suspension cần được truyền và thực thi ở các bên.

### Từ IdP tới RP

Một quy trình có thể gồm:

1. IdP ghi nhận account suspension.
2. IdP ngừng xác thực mới và refresh grant theo policy.
3. IdP phát logout notification hoặc event phù hợp tới RP.
4. RP xác minh issuer, audience, chữ ký và session binding.
5. RP revoke local session liên quan.
6. RP kiểm tra trạng thái account khi nhận request tiếp theo.
7. Provisioning service đồng bộ disabled/suspended status tới ứng dụng khác nếu cần.

OIDC Back-Channel Logout có thể kết thúc session liên quan. SAML Single Logout có thể phối hợp logout. Tuy nhiên, logout protocol không tự thay thế provisioning hoặc account status synchronization.

### Không nhầm logout với suspension

Logout kết thúc một hoặc nhiều phiên. Suspension là trạng thái tài khoản ngăn việc sử dụng tiếp hoặc đăng nhập lại theo scope. Nếu chỉ gửi logout mà không lưu trạng thái suspended, người dùng có thể đăng nhập lại ngay khi IdP session vẫn còn hoặc credential vẫn hợp lệ.

Tương tự, nếu chỉ đánh dấu suspended ở IdP nhưng RP không kiểm tra session/token cục bộ, các phiên hiện có có thể còn hoạt động.

## 9. Nguyên nhân và quy trình suspend

Suspension cần có reason code và nguồn khởi tạo rõ. Những lý do phổ biến:

| Nhóm nguyên nhân | Ví dụ | Kiểm soát phù hợp |
| --- | --- | --- |
| Security incident | Credential bị lộ, session bị chiếm, passkey mất. | Tạm ngưng, revoke session/token, xử lý credential và recovery. |
| Risk signal | Nhiều dấu hiệu bất thường, cần review. | Step-up, giới hạn hành động hoặc suspension có thời hạn theo policy. |
| User request | Người dùng yêu cầu tạm dừng tài khoản. | Xác minh người yêu cầu và scope. |
| Organization lifecycle | Nhân viên nghỉ việc, học viên hết tư cách. | Đồng bộ nguồn HR/directory/provisioning đã xác minh. |
| Policy enforcement | Vi phạm điều khoản hoặc hành vi lạm dụng đã được xác minh. | Quy trình review, thông báo và appeal phù hợp. |
| Legal/administrative hold | Có yêu cầu được phê duyệt. | Scope, retention và quyền truy cập theo quy trình pháp lý/quản trị. |

### Quy trình suspend gợi ý

1. Nhận yêu cầu từ actor hoặc hệ thống có thẩm quyền.
2. Xác minh danh tính actor và quyền suspend trong đúng tenant/scope.
3. Xác định subject bằng định danh ổn định, không chỉ email hiển thị.
4. Kiểm tra trạng thái hiện tại và các suspension đang tồn tại.
5. Chọn scope, reason code, effective time, expiry/review date.
6. Ghi quyết định vào nguồn trạng thái có thẩm quyền.
7. Phát event có version/idempotency key tới session, token, RP và provisioning services.
8. Revoke các phiên/token theo policy.
9. Xác minh enforcement trên các đường truy cập.
10. Thông báo cho người dùng hoặc đầu mối tổ chức theo policy, tránh tiết lộ thông tin điều tra.

### Suspend tự động bởi risk engine

Risk engine có thể phát hiện dấu hiệu account takeover, nhưng không nên mặc định mọi high score đều khóa tài khoản dài hạn. Có thể dùng các mức:

- Step-up cho bất thường vừa phải.
- Rate limit khi có automation.
- Tạm giữ hành động nhạy cảm.
- Suspension ngắn hạn khi có bằng chứng đủ mạnh hoặc nguy cơ tức thời.
- Review của con người trước quyết định kéo dài hoặc có tác động lớn.

Cần có ngưỡng, giải thích, audit, khả năng rollback và quy trình hỗ trợ người dùng hợp pháp bị chặn nhầm.

## 10. Reinstatement: gỡ suspension và khôi phục tài khoản

**Reinstatement (khôi phục trạng thái hoạt động)** là quá trình đưa tài khoản từ suspended trở lại active sau khi điều kiện đã được đáp ứng và quyết định được phê duyệt.

Không nên chỉ đổi một cột status về active mà bỏ qua nguyên nhân ban đầu. Nếu suspension xuất phát từ credential compromise, attacker có thể vẫn giữ refresh token, passkey hoặc session cũ.

### Các bước khôi phục

1. Xác định suspension nào cần được gỡ và phạm vi của nó.
2. Xác minh yêu cầu đến từ chủ tài khoản hoặc administrator có thẩm quyền.
3. Xem xét nguyên nhân ban đầu và bằng chứng đã xử lý.
4. Thu hồi credential bị mất/lộ và kiểm tra authenticator còn lại.
5. Yêu cầu đăng ký lại hoặc xác thực bằng phương thức phù hợp.
6. Revoke session/token cũ theo policy; không tái kích hoạt chúng.
7. Ghi trạng thái reinstatement, actor, thời điểm và approval reference.
8. Đồng bộ trạng thái mới tới các RP, API và provisioning consumers.
9. Gửi thông báo bảo mật qua kênh đã đăng ký trước nếu phù hợp.
10. Theo dõi đăng nhập đầu tiên và các hành động nhạy cảm sau khôi phục.

### Reinstatement không có nghĩa khôi phục mọi quyền

Nếu tài khoản bị suspend trong một tenant do hết tư cách, việc khôi phục login toàn cục không tự cấp lại membership hoặc role cũ. Quyền cần được tính lại từ nguồn authorization/provisioning hiện tại.

Nếu suspension liên quan đến điều tra, có thể gỡ hạn chế đăng nhập nhưng giữ một số action ở trạng thái review. Scope của suspension và scope của authorization cần được quản lý riêng.

## 11. Quyền quản trị và chống lạm dụng suspension

Quyền suspend tài khoản có thể gây gián đoạn lớn. Kẻ tấn công chiếm được tài khoản quản trị có thể khóa hàng loạt người dùng hoặc nhân viên.

### Kiểm soát quản trị

- Least privilege: chỉ cấp quyền suspend trong phạm vi cần thiết.
- Tenant boundary: admin tenant A không được suspend subject ở tenant B.
- Separation of duties: quyết định kéo dài hoặc account-wide có thể cần hai người phê duyệt.
- Step-up authentication: thao tác suspend hàng loạt hoặc gỡ suspension nhạy cảm cần xác thực mới.
- Reason code bắt buộc và case reference cho quyết định có tác động lớn.
- Rate limit và anomaly detection cho thao tác quản trị.
- Audit append-only hoặc hệ thống log có bảo vệ tính toàn vẹn.
- Break-glass account có kiểm soát, MFA chống phishing và review sau sử dụng.
- Notification tới chủ tài khoản hoặc security team theo policy.
- Quy trình emergency rollback khi thao tác nhầm.

### Không cho phép self-approval nguy hiểm

Một administrator không nên vừa tạo vừa tự phê duyệt một quyết định có thể ảnh hưởng diện rộng nếu policy yêu cầu separation of duties. Tương tự, không nên để một tài khoản bị suspend có thể tự gỡ trạng thái bằng cách gửi request từ chính phiên bị nghi ngờ.

### Bảo vệ khỏi mass suspension

- Giới hạn số tài khoản có thể suspend trong một khoảng thời gian.
- Yêu cầu approval cho bulk action.
- Hiển thị preview số lượng và scope trước khi áp dụng.
- Có dry-run và audit cho job provisioning.
- Phát hiện thay đổi trạng thái bất thường từ integration account.
- Có khả năng dừng rollout và khôi phục trạng thái trước đó bằng event/version.

## 12. Đồng bộ trạng thái trong hệ thống phân tán

Một hệ thống có nhiều service có thể nhận suspension event ở thời điểm khác nhau. Trong khoảng trễ, một API có thể còn cache account active.

### Event model

Một event có thể mang các trường:

~~~json
{
  "eventId": "evt-unique-001",
  "eventType": "account.suspended",
  "subject": "user-42",
  "issuer": "https://identity.example.edu",
  "tenant": "university-a",
  "scope": "account",
  "reasonCode": "SECURITY_REVIEW",
  "effectiveAt": "2026-11-22T08:30:00Z",
  "expiresAt": null,
  "version": 17
}
~~~

Đây là schema minh họa, không phải chuẩn chung. Event không nên chứa password, token, session cookie, recovery code hoặc chi tiết điều tra không cần cho consumer.

### Các yêu cầu đồng bộ

- Event có ID duy nhất và version tăng đơn điệu theo subject/scope.
- Consumer xử lý idempotent.
- Event cũ đến muộn không được ghi đè trạng thái mới.
- Có retry, dead-letter queue và reconciliation.
- Cache TTL phù hợp với thời gian thu hồi yêu cầu.
- Có cơ chế invalidation nhanh cho account-wide suspension.
- Xác thực producer và bảo vệ message integrity.
- Ghi nhận consumer đã nhận/áp dụng event để đo propagation lag.

### Race condition

Giả sử request API bắt đầu ngay trước thời điểm suspension có hiệu lực. Có thể request đã qua kiểm tra account status nhưng chưa hoàn thành tác vụ. Với thao tác nhạy cảm, cần xác định điểm commit và kiểm tra trạng thái lần cuối hoặc dùng version/fencing token để tránh một request cũ hoàn tất sau suspension.

Không phải mọi thao tác đọc đều cần cùng độ nghiêm ngặt. Policy cần định nghĩa mức nhất quán theo rủi ro và hậu quả.

## 13. Bảo vệ dữ liệu và trải nghiệm người dùng

Suspension có thể ảnh hưởng tới quyền truy cập dữ liệu, dịch vụ học tập, công việc và khả năng liên hệ hỗ trợ.

### Thông báo cho người dùng

Thông báo nên đủ rõ để người dùng hiểu:

- Tài khoản hoặc chức năng nào đang bị tạm ngưng.
- Trạng thái có thời hạn hay đang chờ review.
- Người dùng cần làm gì tiếp theo.
- Kênh hỗ trợ/appeal chính thức.
- Cách xác minh an toàn nếu cần recovery.

Không tiết lộ chi tiết indicator, tài khoản báo cáo, phương pháp điều tra hoặc dữ liệu có thể giúp attacker né phát hiện. Đồng thời, không dùng thông báo quá mơ hồ khiến người dùng không biết cách khôi phục quyền truy cập.

### Dữ liệu và retention

Suspension không tự động cho phép xóa hoặc giữ mọi dữ liệu vô thời hạn. Cần áp retention policy riêng cho:

- Hồ sơ tài khoản.
- Dữ liệu nghiệp vụ.
- Audit/security event.
- Case và bằng chứng điều tra.
- Credential metadata.
- Dữ liệu cá nhân cần xuất hoặc xóa theo quyền hợp lệ.

Không lưu raw token, session cookie, mật khẩu, OTP hoặc recovery secret trong case suspension. Nếu cần tham chiếu, lưu identifier đã bảo vệ hoặc event ID.

### Trạng thái read-only hoặc export

Một số sản phẩm có thể cho phép người dùng bị suspend tải dữ liệu cá nhân hoặc xem lý do/appeal. Cần tách endpoint và authorization riêng, có rate limit, audit và giới hạn dữ liệu. Không cấp lại session đầy đủ chỉ để hỗ trợ một chức năng read-only.

## 14. Các mối đe dọa và lỗi triển khai thường gặp

| Rủi ro | Cách xảy ra | Biện pháp |
| --- | --- | --- |
| **Login-only enforcement** | Chặn login mới nhưng session cũ vẫn gọi API. | Revoke session/token và kiểm tra account status tại resource server. |
| **Stale cache** | Node còn cache active sau suspension. | Versioned event, cache invalidation, TTL và kiểm tra trạng thái theo risk. |
| **Token survival** | JWT đã phát hành còn hợp lệ tới exp. | TTL ngắn, introspection, denylist hoặc account version. |
| **Scope confusion** | Suspension một tenant bị hiểu thành toàn tài khoản hoặc ngược lại. | Lưu scope rõ và kiểm tra tenant/application/action. |
| **Admin abuse** | Attacker chiếm admin và suspend hàng loạt. | MFA, least privilege, approval, rate limit và audit. |
| **Self-unlock** | User bị suspend tự gỡ qua endpoint không kiểm tra quyền. | Reinstatement workflow và authorization server-side. |
| **Provisioning spoofing** | Event giả hoặc producer bị compromise đổi trạng thái tài khoản. | Xác thực producer, chữ ký/message integrity, version và allowlist. |
| **Lockout DoS** | Attacker cố tình gây failed attempts để khóa nạn nhân. | Tách lockout khỏi suspension, rate limit và recovery an toàn. |
| **Recovery bypass** | Recovery flow tạo session đầy đủ dù suspension còn hiệu lực. | Kiểm tra account status ở mọi recovery step; yêu cầu review/lift riêng. |
| **Reactivation with old tokens** | Gỡ suspension khiến token/session cũ tự hoạt động lại. | Revoke phiên cũ; reinstatement không khôi phục credential/session đã thu hồi. |
| **Account enumeration** | Login response tiết lộ chính xác tài khoản suspended. | Thông báo có kiểm soát, không làm lộ trạng thái nhạy cảm cho người không xác thực. |
| **Audit tampering** | Admin sửa/xóa lý do hoặc lịch sử suspension. | Log append-only, integrity protection và quyền truy cập tách biệt. |

## 15. Ví dụ thực tế: nền tảng học tập

Learning Platform phục vụ nhiều trường đại học. Một tài khoản học viên có thể dùng cùng identity để truy cập Learning Portal và Support Desk; quyền học tập được gắn theo tenant.

### Tình huống A: passkey bị mất

1. Học viên báo mất điện thoại qua kênh hỗ trợ.
2. Support xác minh yêu cầu theo quy trình recovery.
3. Security service tạm ngưng account-wide hoặc tạm khóa credential liên quan theo mức rủi ro.
4. Passkey bị mất được revoke.
5. Các session đang hoạt động và refresh token liên quan được xử lý theo policy.
6. Học viên hoàn thành recovery và đăng ký passkey mới.
7. Administrator hoặc workflow có thẩm quyền gỡ suspension.
8. Học viên đăng nhập lại; hệ thống tạo session mới và thông báo bảo mật.

### Tình huống B: nhân viên nghỉ việc ở một trường

1. HR system gửi sự kiện kết thúc hợp đồng đã xác thực.
2. Provisioning service xác định tenant và subject.
3. Quyền ở tenant của trường đó bị suspend/deprovision theo policy.
4. Learning Portal và Staff Console của tenant nhận trạng thái mới.
5. Tài khoản có thể tiếp tục hoạt động ở tenant khác nếu membership riêng còn hiệu lực.
6. Audit ghi event nguồn, version và kết quả từng consumer.

Đây là ví dụ tenant-scoped. Không được chuyển thành account-wide suspension chỉ vì một membership hết hiệu lực.

### Tình huống C: phát hiện account takeover

1. Risk engine phát hiện session bất thường và credential compromise có bằng chứng.
2. Security workflow áp dụng suspension account-wide tạm thời.
3. Authentication service chặn login mới; session store revoke phiên hiện có.
4. Authorization server revoke refresh token family.
5. API kiểm tra account version hoặc trạng thái revoke để chặn token còn lại theo SLA.
6. Người dùng xác minh danh tính, thu hồi credential bị lộ và đăng ký phương thức mới.
7. Security reviewer phê duyệt reinstatement.
8. Hệ thống tạo session mới và giám sát các hành động nhạy cảm sau khôi phục.

## 16. Kiểm thử account suspension

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Login khi suspended | Đăng nhập bằng credential hợp lệ của subject suspended. | Không tạo phiên authenticated. |
| Existing session | Dùng cookie đã tạo trước khi suspend. | Server từ chối sau khi suspension có hiệu lực theo SLA. |
| Refresh token | Dùng refresh token của subject suspended. | Authorization server từ chối hoặc token family đã bị revoke. |
| JWT access token cũ | Gọi API bằng token đã phát hành trước suspension. | Resource server từ chối theo revocation design/SLA đã định nghĩa. |
| Tenant-scoped suspension | Suspend subject ở tenant A, truy cập tenant B. | Chỉ tenant A bị chặn nếu policy cho phép tenant B. |
| Application-scoped suspension | Suspend Staff Console. | Ứng dụng khác không bị ảnh hưởng ngoài policy. |
| Credential-scoped suspension | Revoke một passkey. | Passkey đó không còn dùng được; account policy xử lý credential còn lại. |
| Session-scoped suspension | Revoke một session bị nghi ngờ. | Session khác không bị revoke nhầm. |
| Lockout vs suspension | Tạo nhiều failed login. | Lockout policy hoạt động; không tự chuyển thành suspension dài hạn ngoài policy. |
| Recovery trong suspension | Thử password reset/recovery khi account còn suspended. | Không dùng recovery để bypass; trạng thái cần được lift đúng quy trình. |
| Expiry | Đưa suspension tới thời điểm hết hạn. | Hành động đúng policy: review, auto-lift hoặc tiếp tục suspended. |
| Reinstatement | Gỡ suspension sau review. | Tài khoản active theo scope; session/token cũ không tự sống lại. |
| Duplicate event | Gửi cùng event ID nhiều lần. | Consumer xử lý idempotent. |
| Out-of-order event | Gửi event version cũ sau event mới. | Trạng thái mới hơn không bị ghi đè. |
| Stale cache | Một node giữ cache active khi account bị suspend. | Invalidation/TTL đưa node về trạng thái đúng trong SLA. |
| Concurrent request | Request bắt đầu trước suspension và commit sau đó. | Enforcement theo consistency policy; action nhạy cảm không vượt qua fencing/version check. |
| Forged provisioning event | Gửi event từ producer không tin cậy. | Event bị từ chối và audit. |
| Admin privilege boundary | Admin tenant A thử suspend user tenant B. | Authorization từ chối. |
| Bulk suspension | Thử suspend số lượng lớn không có approval. | Rate limit/approval ngăn thao tác trái phép. |
| Audit integrity | Thử sửa hoặc xóa audit record. | Bị ngăn hoặc phát hiện theo cơ chế integrity. |
| Account enumeration | Thử dò trạng thái tài khoản qua login response. | Không tiết lộ thông tin nhạy cảm cho người chưa xác thực. |

## 17. Checklist triển khai

- [ ] Đã định nghĩa rõ suspended, locked, disabled, deactivated, pending và deleted.
- [ ] Suspension có scope, reason code, source, actor, effective time và review/expiry policy.
- [ ] State transition được kiểm tra quyền và version; không tin trạng thái từ client.
- [ ] Đã xác định enforcement ở login, session, authorization server, resource API và provisioning.
- [ ] Existing session bị revoke hoặc hạn chế theo policy.
- [ ] Refresh token và access token được xử lý với giới hạn thu hồi thực tế.
- [ ] Có xử lý riêng cho service account, API key, certificate và workload credential.
- [ ] SSO/RP nhận logout hoặc account-status event và xác minh nguồn.
- [ ] Recovery không bypass suspension.
- [ ] Reinstatement có review, identity proof và xử lý credential/session cũ.
- [ ] Tenant/application/credential/session scope không bị nhầm lẫn.
- [ ] Admin có least privilege, step-up, approval và audit.
- [ ] Có rate limit và chống mass suspension/lockout DoS.
- [ ] Event có ID/version, consumer idempotent và xử lý out-of-order.
- [ ] Cache invalidation và propagation lag đáp ứng SLA.
- [ ] Có policy cho partial failure, retry và reconciliation.
- [ ] Thông báo người dùng rõ ràng nhưng không tiết lộ thông tin điều tra.
- [ ] Dữ liệu, audit và retention được bảo vệ; không lưu raw credential/token.
- [ ] Có test existing session, refresh/JWT, recovery, expiry, reinstatement và tenant isolation.

## 18. Tự kiểm tra

**Câu 1.** Account suspension khác account lockout như thế nào?

**Đáp án:** Lockout thường là cơ chế tạm khóa đăng nhập sau failed attempts; suspension là trạng thái vòng đời có scope và lý do rộng hơn, có thể do user, admin, tổ chức hoặc security workflow khởi tạo.

**Câu 2.** Chặn login mới có đủ để thực thi suspension không?

**Đáp án:** Không. Session cũ, refresh token, access token và API key có thể tiếp tục hoạt động. Cần enforcement trên các đường truy cập và xử lý credential/token liên quan.

**Câu 3.** Suspension ở một tenant có phải chặn toàn bộ tài khoản không?

**Đáp án:** Không nhất thiết. Scope phải được lưu rõ; tenant-scoped suspension chỉ tác động tenant tương ứng nếu policy cho phép.

**Câu 4.** Vì sao cần revoke session server-side?

**Đáp án:** Cookie có thể đã bị sao chép. Xóa cookie trên browser không làm server ngừng chấp nhận bản cookie attacker đang giữ.

**Câu 5.** JWT access token đã phát hành có tự mất hiệu lực khi account bị suspended không?

**Đáp án:** Không nhất thiết. Nếu resource server chỉ xác minh chữ ký cục bộ, token có thể còn hợp lệ tới exp. Cần TTL ngắn, introspection, denylist, account version hoặc cơ chế tương đương.

**Câu 6.** Logout event có thay thế account suspension không?

**Đáp án:** Không. Logout kết thúc phiên; suspension ngăn việc sử dụng hoặc đăng nhập lại theo scope. Cần lưu trạng thái suspension và thực thi ở các đường truy cập.

**Câu 7.** Khi reinstatement, có nên khôi phục session cũ không?

**Đáp án:** Không. Session/token cũ cần được xử lý theo policy và thường phải tạo phiên mới sau khi xác minh. Gỡ suspension không tự làm credential đã revoke sống lại.

**Câu 8.** Vì sao phải tách lockout khỏi suspension?

**Đáp án:** Attacker có thể cố ý gây failed login để khóa nạn nhân. Tách hai trạng thái giúp giảm denial of service và cho phép dùng rate limit/challenge phù hợp.

**Câu 9.** Làm thế nào để tránh event cũ ghi đè trạng thái suspension mới?

**Đáp án:** Dùng event ID và version tăng đơn điệu, consumer idempotent và từ chối event có version cũ hơn trạng thái đã áp dụng.

**Câu 10.** Vì sao reinstatement cần xem lại nguyên nhân ban đầu?

**Đáp án:** Nếu credential hoặc session bị compromise mà chưa được thu hồi, việc bật lại tài khoản có thể mở đường cho attacker tiếp tục truy cập. Cần xử lý nguyên nhân và xác minh trước khi khôi phục.

## Ghi nhớ

**Account suspension** là trạng thái tạm ngưng sử dụng tài khoản theo một scope, lý do và thời hạn hoặc điều kiện review xác định. Nó khác lockout, disablement, deactivation, deletion và credential revocation. Hệ thống phải thực thi trạng thái trên login, session, refresh/access token, API và các RP liên kết; chỉ chặn đăng nhập mới là chưa đủ.

Thiết kế suspension cần state transition có quyền, audit, version và idempotency; xử lý session/token đang tồn tại; truyền trạng thái nhất quán trong hệ thống phân tán; bảo vệ khỏi admin abuse và lockout DoS. Reinstatement phải xử lý nguyên nhân ban đầu, xác minh người yêu cầu, thu hồi credential/phiên cũ và tạo phiên mới theo policy. **Tạm ngưng tài khoản là một quyết định vòng đời có thể kiểm tra và khôi phục; mọi thành phần truy cập phải hiểu cùng một scope và trạng thái có thẩm quyền.**
