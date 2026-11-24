# Email invitation lifecycle

## 1. Lời mời qua email là một đề nghị cấp quyền

Một email mời tham gia tổ chức, dự án hoặc không gian làm việc thường chứa liên kết để người nhận gia nhập. Phía sau thao tác tưởng như đơn giản đó là một quy trình cấp quyền: ai được mời ai, vào tenant nào, với vai trò nào, trong phạm vi nào và trước thời hạn nào.

**Email invitation lifecycle** là vòng đời nghiệp vụ của lời mời, từ đề xuất, phê duyệt và phát hành đến chấp nhận, từ chối, hết hạn, thu hồi hoặc thay thế. Gửi email chỉ là một bước chuyển thông tin; nó không tự tạo tư cách thành viên hợp lệ.

Trong bảo mật logic nghiệp vụ, các rủi ro chính gồm:

- Tạo lời mời có quyền cao hơn quyền được phép ủy quyền.
- Dùng token của tenant này để tham gia tenant khác.
- Chấp nhận lời mời bằng tài khoản không phải người nhận dự kiến.
- Dùng liên kết cũ sau khi thu hồi, gửi lại hoặc thay đổi vai trò.
- Chấp nhận đồng thời nhiều lần để tạo trùng thành viên hoặc chiếm sai hạn mức.
- Nhầm thu hồi lời mời với thu hồi quyền của thành viên đã tham gia.

Bài học xây dựng các bất biến, state machine, transaction, idempotency và tình huống kiểm thử cho những rủi ro đó.

### Tình huống xuyên suốt

Tenant “t-acme” có dự án “project-7”. Một quản lý được phép mời cộng tác viên làm READER trong dự án này, nhưng không được cấp TENANT_ADMIN hoặc quyền đối với dự án khác.

Quản lý mời địa chỉ “linh@example.net”. Thiết kế tham chiếu của bài yêu cầu người nhận đăng nhập bằng một tài khoản có địa chỉ đã xác minh khớp người được mời, xác nhận chấp nhận rõ ràng và đáp ứng policy hiện tại. Vai trò nhạy cảm có thể cần phê duyệt hoặc xác thực bổ sung.

Đây là lựa chọn của thiết kế tham chiếu. Một sản phẩm dùng liên kết như capability cho phép người giữ link tham gia cần công bố rõ phạm vi chuyển nhượng và rủi ro; không được vô tình áp dụng mô hình đó trong khi giao diện vẫn hứa “chỉ người nhận email này được tham gia”.

Các trạng thái và schema dưới đây là minh họa, không phải chuẩn bắt buộc của nhà cung cấp email hay hệ thống danh tính.

## 2. Phân biệt lời mời, email, danh tính và membership

| Đối tượng | Vai trò | Không chứng minh được |
| --- | --- | --- |
| Invitation | Đề nghị cấp một tập quyền có điều kiện | Người được mời đã gia nhập |
| Email delivery | Chuyển nội dung đến một kênh liên hệ | Chủ tài khoản đã đọc hoặc đồng ý |
| Invitation token | Chứng cứ để tra và thực hiện quy trình nhận lời mời | Caller được tùy chọn tenant, vai trò hoặc người nhận |
| Authenticated identity | Tài khoản đã được hệ thống xác thực | Tài khoản đó phù hợp mọi lời mời |
| Verified email binding | Ràng buộc địa chỉ với identity theo nguồn tin cậy | Một người duy nhất ngoài đời sở hữu hộp thư |
| Membership | Quan hệ quyền đã được cấp trong tenant/phạm vi | Lời mời tạo ra nó vẫn còn có thể dùng lại |

Email có thể được chuyển tiếp, dùng trong hộp thư chung hoặc được người khác đọc. Hệ thống cần mô hình danh tính phù hợp với mức quyền, không suy “biết link” đồng nghĩa “là đúng người” trong mọi trường hợp.

Địa chỉ có cùng domain với doanh nghiệp cũng không tự chứng minh người dùng thuộc doanh nghiệp đó. Nếu tenant yêu cầu SSO hoặc nguồn danh tính cụ thể, việc so khớp email không thay thế điều kiện đó.

Một membership đã tạo phải được quản lý bằng vòng đời riêng: đổi vai trò, đình chỉ, thu hồi hoặc rời tổ chức. Hủy email hoặc xóa lời mời không tự đảo ngược quyền đã cấp.

## 3. Viết các bất biến trước khi thiết kế endpoint

### 3.1. Bất biến về tenant và quyền ủy quyền

~~~text
invitation.tenant_id là tenant mà actor có quyền mời
mọi resource trong invitation.scope thuộc tenant đó
invitation.roles/scope nằm trong quyền actor hoặc grant được phép ủy quyền
người duyệt có thẩm quyền đối với đúng tập quyền được đề xuất
membership khi chấp nhận chỉ nhận quyền từ bản lời mời hợp lệ trên máy chủ
~~~

Quyền quản lý thành viên không mặc nhiên bao hàm quyền cấp mọi vai trò. Có thể cần một permission matrix xác định vai trò nào được mời vai trò nào, vào tài nguyên nào và có cần người duyệt độc lập hay không.

Không nhận role, tenant hoặc scope từ form chấp nhận làm nguồn cấp quyền. Các trường đó có thể được hiển thị để người nhận hiểu đề nghị; giá trị có hiệu lực phải lấy từ invitation đã được kiểm chứng.

Nguyên tắc mặc định từ chối và kiểm tra quyền trên mọi request, đúng đối tượng, được trình bày trong [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Với invitation, áp dụng cho tạo, xem, gửi lại, thay đổi, thu hồi và chấp nhận, không chỉ cho endpoint tạo ban đầu.

### 3.2. Bất biến về người nhận

~~~text
identity đang đăng nhập thỏa recipient binding của invitation
địa chỉ dùng để so khớp đến từ nguồn xác minh tin cậy
recipient binding không bị đổi ngầm khi resend
một invitation không được dùng để chiếm hoặc hợp nhất tài khoản khác
~~~

Không tin trường email_verified do client gửi. Nếu nhận claim từ nhà cung cấp danh tính, phải xác minh issuer, audience, chữ ký và ngữ nghĩa claim theo cấu hình đã chấp nhận.

Chính sách chuẩn hóa địa chỉ phải nhất quán giữa đăng ký, xác minh và lời mời. Không mặc định xóa dấu chấm hoặc phần +tag cho mọi domain. Những phép biến đổi làm hai mailbox khác nhau trở thành một khóa có thể tạo lỗi gắn nhầm danh tính.

Nếu sản phẩm hỗ trợ nhiều email đã xác minh cho một identity, cần quy tắc rõ về địa chỉ nào được dùng nhận lời mời, hiệu lực xác minh và xử lý khi địa chỉ bị gỡ. Việc tài khoản có email hiển thị trùng không đủ nếu email đó chưa được xác minh.

### 3.3. Bất biến về trạng thái và sử dụng một lần

~~~text
Có thể chấp nhận
  => state = ACTIVE
  AND token thuộc generation hiện tại
  AND token chưa bị thu hồi
  AND now < expires_at
  AND approval/grant/policy còn cho phép
  AND recipient binding hợp lệ

Chấp nhận thành công
  => tạo đúng một hiệu ứng membership
  AND invitation chuyển ACCEPTED trong cùng transaction
  AND ghi accepted_by và membership_id không thể bị client tự chọn
~~~

Trạng thái ACCEPTED không được chuyển lại ACTIVE bằng resend. Một membership sau đó bị thu hồi cũng không được tạo lại bằng cách bấm link đã dùng.

Việc hết hạn phải được kiểm tra ở đường chấp nhận. Job dọn dẹp có thể chưa chạy; invitation vẫn không được dùng chỉ vì cột state còn ACTIVE trong database.

## 4. State machine của lời mời

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: Quyền đề xuất cần phê duyệt
    DRAFT --> ACTIVE: Đủ điều kiện phát hành
    PENDING_APPROVAL --> ACTIVE: Duyệt đúng đề xuất
    PENDING_APPROVAL --> REVOKED: Hủy đề xuất
    PENDING_APPROVAL --> EXPIRED: Quá hạn đề xuất
    ACTIVE --> ACTIVE: Resend theo policy, cập nhật generation khi xoay token
    ACTIVE --> ACCEPTED: Đúng người, đúng quyền, còn hạn
    ACTIVE --> DECLINED: Người nhận từ chối có xác thực phù hợp
    ACTIVE --> REVOKED: Thu hồi
    ACTIVE --> EXPIRED: Hết thời hạn
    ACTIVE --> SUPERSEDED: Thay bằng lời mời mới
    DRAFT --> REVOKED: Hủy bản nháp
    ACCEPTED --> [*]
    DECLINED --> [*]
    REVOKED --> [*]
    EXPIRED --> [*]
    SUPERSEDED --> [*]
~~~

Email delivery có vòng đời riêng như QUEUED, PROVIDER_ACCEPTED, BOUNCED hoặc UNKNOWN. Không dùng SENT làm điều kiện bắt buộc duy nhất để chấp nhận: một link đã đến đúng người có thể được sử dụng trước khi callback của nhà cung cấp cập nhật.

Ngược lại, callback delivered hoặc open không được chuyển invitation sang ACCEPTED. Những tín hiệu đó không chứng minh sự đồng ý cấp quyền, và có thể đến từ công cụ quét hoặc tải nội dung tự động.

VIEWED có thể là thông tin quan sát, không nên là trạng thái làm mất token. Người dùng mở link nhiều lần, đổi thiết bị hoặc quay lại sau đăng nhập không được vô tình làm hỏng quy trình chỉ vì một lần xem trang.

### Thay đổi nhạy cảm phải tạo lại căn cứ

Đổi người nhận, tenant, vai trò hoặc scope có thể làm thay đổi bản chất đề nghị. Thiết kế tham chiếu đánh dấu invitation cũ SUPERSEDED, vô hiệu hóa token cũ rồi tạo lời mời mới qua đầy đủ kiểm tra quyền/phê duyệt.

Nếu sản phẩm cho sửa cùng một invitation ID, phải tạo revision/generation mới, vô hiệu hóa các token và approval không còn khớp. Không sửa role trong hàng database rồi để link cũ cấp quyền mới mà người nhận chưa được thông báo.

## 5. Mô hình dữ liệu để giữ được các ràng buộc

| Trường | Ý nghĩa |
| --- | --- |
| invitation_id, tenant_id | Danh tính và ranh giới tenant |
| recipient_email_key | Khóa so khớp theo policy địa chỉ |
| recipient_binding_version | Phiên bản ràng buộc người nhận |
| roles, resource_scope | Đề nghị quyền bất biến trong revision |
| revision, invitation_digest | Phiên bản và digest nội dung ảnh hưởng quyền |
| created_by, authorizing_grant_id | Người tạo và nguồn thẩm quyền duy trì lời mời |
| approval_id, approval_policy_version | Căn cứ phê duyệt nếu cần |
| state, token_generation | Trạng thái và thế hệ token hiện hành |
| token_digest, digest_key_id | Dữ liệu kiểm tra token, không phải secret thô |
| issued_at, expires_at, absolute_deadline | Các hạn do máy chủ kiểm soát |
| accepted_at, accepted_by, membership_id | Kết quả tiêu thụ lời mời |
| seat_reservation_id | Giữ chỗ nếu nghiệp vụ có giới hạn thành viên |
| command_id, idempotency_key_ref | Liên kết retry với hiệu ứng gốc |

Digest của lời mời nên bao gồm tenant, người nhận, roles, scope và điều kiện liên quan theo một biểu diễn chuẩn hóa. Approval phải ràng buộc với digest đó, không chỉ với invitation ID có thể sửa nội dung.

Thẩm quyền có thể gắn với grant tổ chức thay vì phụ thuộc vĩnh viễn vào người bấm tạo. Nếu người tạo nghỉ việc, policy cần xác định lời mời của doanh nghiệp còn hợp lệ hay bị thu hồi. Không âm thầm coi created_by là toàn bộ nguồn quyền; cũng không bỏ qua việc grant đã bị rút.

Role ID cũng có thể đổi ý nghĩa theo thời gian. Với vai trò tùy chỉnh, giữ phiên bản hoặc digest quyền và kiểm tra khi chấp nhận. Nếu quyền thực tế đã mở rộng, không tự cấp phạm vi mới dựa trên một approval cho nội dung cũ.

### Hai loại giới hạn thời gian

expires_at là hạn hiện tại của invitation hoặc generation. absolute_deadline là hạn tối đa của đợt mời theo policy, dùng khi không cho resend kéo dài vô hạn.

Ví dụ chỉ để minh họa: generation được dùng trong 24 giờ nhưng tổng đợt mời không vượt bảy ngày kể từ phát hành đầu tiên. Tại resend, hạn mới không được vượt absolute_deadline. Sản phẩm có thể chọn thời hạn khác dựa trên rủi ro và mục đích.

Lưu UTC, lấy thời gian máy chủ tại điểm quyết định sau thời gian chờ khóa. Không tin timestamp từ trình duyệt. Quy tắc của bài coi đúng expires_at là đã hết hạn.

## 6. Phát hành, lưu và bảo vệ token

Token phải khó đoán, có mục đích rõ, gắn với đúng invitation và chỉ tạo được một hiệu ứng chấp nhận. Một thiết kế đơn giản dùng secret ngẫu nhiên đủ mạnh, ví dụ 32 byte từ CSPRNG, được mã hóa theo dạng phù hợp URL.

Có thể dùng cấu trúc:

~~~text
https://app.example/invitations/open?id=<invitation_id>&token=<random_secret>
~~~

Invitation ID không được coi là bí mật. Secret phải được kiểm tra với digest đã lưu và generation hiện tại. Giới hạn chiều dài, parse chặt và so sánh digest bằng cơ chế phù hợp để tránh so sánh secret tùy tiện.

OWASP hướng dẫn token cho khôi phục tài khoản phải ngẫu nhiên an toàn, lưu có bảo vệ, dùng một lần và có thời hạn. Những nguyên tắc quản lý secret đó hữu ích cho thiết kế token lời mời; quy tắc cấp membership vẫn phải được định nghĩa riêng. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Không dùng chung token cho lời mời, đặt lại mật khẩu và xác minh email nếu thiếu ràng buộc purpose/audience. Với token có chữ ký, chữ ký đúng không thay thế việc kiểm tra state, token generation và thu hồi phía máy chủ.

### Hash ở bảng lời mời và secret trong luồng gửi

Chỉ lưu digest để kiểm tra token giúp hạn chế tác hại khi bảng invitation bị đọc lộ. Tuy nhiên, worker gửi email vẫn cần secret để tạo link. Không thể khôi phục secret từ digest rồi giả định outbox tự có đủ dữ liệu.

Một phương án là:

1. Sinh secret trước khi ghi command phát hành.
2. Lưu digest vào invitation.
3. Lưu packet gửi chứa link dưới dạng mã hóa hoặc tham chiếu đến kho secret được bảo vệ.
4. Ghi packet/outbox cùng transaction với invitation.
5. Xóa hoặc hủy khả năng đọc secret gửi sau thời hạn cần thiết theo policy.

Secret tạm trong tiến trình, queue, dead-letter và backup cũng cần chính sách bảo vệ. Không serialize raw token vào log lỗi để sửa sự cố.

Nếu dùng HMAC làm digest tra token, giữ khóa ngoài database và có kế hoạch phiên bản khóa. Token ngẫu nhiên có entropy cao không phải mật khẩu do người dùng chọn; không áp dụng một công thức lưu mật khẩu rồi bỏ qua quản lý secret trong hệ thống gửi.

### Bảo vệ liên kết

Dùng origin được cấu hình tin cậy để tạo URL, không ghép từ Host header tùy ý hoặc redirect URL không kiểm soát. Link chỉ chứa dữ liệu cần thiết, tránh mang role hay địa chỉ nhạy cảm làm nguồn quyền.

Trang mở lời mời không nên tải tài nguyên bên thứ ba có thể nhận token qua URL/referrer. Áp dụng chính sách referrer, cache và log redaction phù hợp; có thể chuyển sang URL sạch sau bước xử lý an toàn, nhưng việc chuyển đó không được tiêu thụ quyền chấp nhận.

Token có thể vẫn nằm trong lịch sử trình duyệt, email hoặc thiết bị đã bị lộ. Thời hạn, thu hồi, ràng buộc danh tính và quyền tối thiểu phải phối hợp; HTTPS không giải quyết mọi nguồn rò rỉ token.

## 7. Tạo lời mời và gửi email sau commit

Command tạo lời mời cần kiểm tra ít nhất:

1. Actor có quyền mời trong tenant và resource scope cụ thể.
2. Vai trò đề xuất thuộc tập được phép cấp, không phải role tùy ý do client khai.
3. Tenant, tài nguyên và nguồn thẩm quyền còn hoạt động.
4. Điều kiện phê duyệt hoặc xác thực bổ sung đã được đáp ứng.
5. Người nhận được chuẩn hóa theo policy và không vi phạm quy tắc mời.
6. Hạn mức lời mời, số chỗ và giới hạn gửi còn phù hợp.
7. Request trùng không tạo thêm invitation hoặc email ngoài chủ đích.

Với lời mời cần duyệt, tạo PENDING_APPROVAL trước. Không phát hành link có thể chấp nhận ngay rồi dựa vào giao diện để che nút khi chưa duyệt.

Một transaction minh họa:

~~~text
BEGIN
  kiểm tra quyền, policy và expected revision liên quan
  claim idempotency key, kiểm tra request fingerprint
  giữ chỗ hoặc kiểm tra quota theo thiết kế
  INSERT invitation với roles/scope/recipient đã được chấp nhận
  lưu digest token nếu đã đủ điều kiện phát hành
  ghi packet gửi được bảo vệ và outbox
  ghi audit, kết quả command
COMMIT
~~~

Relay gửi email từ dữ liệu đã commit. Nếu transaction rollback, không có email hợp lệ được phát ra từ transaction đó. Không gọi provider trong transaction rồi giả định rollback database sẽ thu hồi được email.

Nếu idempotency key thuộc cùng tenant, actor và operation nhưng request đổi email/role/scope, phải trả conflict thay vì dùng key đó cho một hiệu ứng mới. Request fingerprint giữ nội dung có ý nghĩa và tham chiếu phiên bản, không chứa secret trong log.

Email phải mô tả đúng đề nghị: tổ chức, mục đích và quyền được mời ở mức thông tin được phép công bố. Tránh đính kèm dữ liệu dự án nhạy cảm trước khi có membership. Chuỗi tên tổ chức, người mời và ghi chú do người dùng nhập cần được render an toàn, không cho chèn HTML hoặc giả mạo nội dung.

### Worker gửi cũng cần kiểm tra vòng đời

Trước khi nộp email, kiểm tra invitation/generation vẫn còn được phép gửi và còn đủ hạn hữu ích. Một outbox cũ sau khi revoke không được sinh lại token hoặc tự đưa state về ACTIVE.

Email có thể đã được provider nhận trước khi thu hồi, hoặc được giao chậm. Không hứa có thể xóa mọi bản email cũ; an toàn phải nằm ở bước redeem luôn kiểm tra state/generation hiện hành.

Lỗi bounce hoặc timeout thuộc vòng đời delivery. Policy có thể dừng gửi lại, yêu cầu sửa địa chỉ qua quy trình mới hoặc báo người mời; không tự tạo membership hoặc đổi người nhận từ một callback chưa xác thực.

## 8. Mở liên kết, đăng nhập và xác nhận chấp nhận

### GET chỉ mở trang, không tạo quyền

Công cụ tải trước, kiểm tra liên kết hoặc phần mềm thư có thể thực hiện GET mà không phải hành động đồng ý của người dùng. Không thiết kế GET /accept?... để tiêu thụ token và tạo membership.

RFC 9110 phân biệt safe methods và yêu cầu không thực hiện hành động không an toàn qua phương thức an toàn, bao gồm những trường hợp URI có tham số chọn hành động. Điều này phù hợp với việc để trang mở lời mời chỉ đọc và chuyển thao tác chấp nhận sang command rõ ràng. [RFC 9110, mục 9.2.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1).

Luồng tham chiếu:

~~~text
GET mở link
  -> chỉ hiển thị thông tin tối thiểu và trạng thái có thể công bố
  -> đăng nhập hoặc đăng ký bằng luồng danh tính chuẩn
  -> xác minh recipient binding theo policy
  -> hiển thị tổ chức, scope và vai trò để người dùng xác nhận
  -> POST chấp nhận với chống CSRF nếu dùng session cookie
  -> transaction tạo membership và tiêu thụ invitation
~~~

POST không tự chứng minh người dùng chủ động đồng ý nếu trang tự submit ngay khi tải. Giao diện phải có hành động xác nhận phù hợp, và máy chủ phải kiểm tra đầy đủ thay vì coi method là lớp bảo vệ duy nhất.

Trang trước đăng nhập không nên hiển thị danh sách thành viên, tài liệu hoặc dữ liệu nội bộ chỉ vì người xem biết invitation ID. Secret hợp lệ cũng chỉ cho mức xem được policy công bố.

### Người dùng đang đăng nhập bằng tài khoản khác

Ví dụ link gửi cho “linh@example.net” nhưng trình duyệt đang có session của “an@example.org”. Không lấy user_id từ session hiện tại rồi cấp quyền ngay.

Hiển thị thông báo phù hợp để đổi tài khoản hoặc bổ sung/xác minh địa chỉ theo quy trình chuẩn. Không tự gán email được mời vào tài khoản đang đăng nhập, không hợp nhất tài khoản theo chuỗi email chưa xác minh.

Nếu tạo tài khoản mới, hoàn tất điều kiện danh tính trước khi cấp membership. Đừng tạo ACTIVE membership rồi dựa vào một cờ email chưa xác minh để hy vọng mọi API sau đó đều chặn đúng.

Với tenant yêu cầu SSO, xác thực bổ sung hoặc điều kiện tổ chức, lời mời không được trở thành đường bỏ qua chính sách đó. Một claim email_verified từ issuer chưa được tenant chấp nhận cũng không đủ.

### Giữ ngữ cảnh qua đăng nhập an toàn

Thông tin tiếp tục luồng phải ràng buộc với invitation và session qua cơ chế được bảo vệ, có hạn. Không để callback đăng nhập nhận một tenant_id hoặc role khác rồi áp dụng lên cùng token.

Redirect sau chấp nhận nên dùng đường nội bộ hoặc danh sách đích được chấp nhận. Không chuyển token tới return_url do client tự cung cấp. Nếu dùng một mã tiếp tục ngắn hạn thay raw token, mã đó cũng là dữ liệu nhạy cảm cần kiểm soát mục đích và hạn.

## 9. Chấp nhận bằng transaction: cấp quyền đúng một lần

Các bước kiểm tra ở trang mở link chỉ phục vụ trải nghiệm. Lúc POST, mọi điều kiện có thể thay đổi phải được kiểm tra lại ở máy chủ.

Đoạn Java sau là mã giả ở tầng ứng dụng, mô tả hợp đồng và thứ tự kiểm soát, không phải chương trình hoàn chỉnh để biên dịch:

~~~java
AcceptResult acceptInvitation(AuthContext auth, AcceptCommand cmd) {
    AuthenticatedActor actor = authentication.requireActor(auth);
    csrf.requireValidIfCookieSession(auth, cmd);
    ParsedInviteToken token = tokens.parseWithLimits(cmd.token());

    return unitOfWork.inTransaction(() -> {
        Invitation invite = invitations.lockById(cmd.invitationId());

        // Hợp đồng yêu cầu ID và secret cùng khớp bản invitation hiện tại.
        tokens.requireMatches(invite, token);
        Account account = accounts.lockByAuthenticatedId(actor.accountId());
        account.requireActive();

        if (invite.state() == ACCEPTED) {
            invite.requireAcceptedBy(account.id());
            receiptPolicy.requireCanRead(account, invite);
            return AcceptResult.alreadyApplied(invite.membershipId());
        }

        invite.requireState(ACTIVE);
        recipientPolicy.requireVerifiedBinding(account, invite);

        // Khóa hoặc kiểm tra phiên bản các căn cứ cấp quyền liên quan.
        GrantSnapshot grant = grants.lockAndRequireCurrentAuthority(invite);
        approvalPolicy.requireCurrentApproval(invite, grant);
        tenantPolicy.requireJoinAllowed(invite.tenantId(), account);
        rolePolicy.lockAndRequireExactAuthorizedGrant(invite, grant);

        MembershipSlot slot = memberships.lockSlot(
            invite.tenantId(), account.id());
        slot.requireNoExistingMembershipForCreate();
        SeatAllocation seats = seatPolicy.lockForAcceptance(invite);

        // Đọc thời gian sau các bước có thể chờ khóa.
        Instant now = trustedClock.instant();
        invite.requireNotExpiredAt(now);
        seats.requireUsableAt(now);

        Membership member = memberships.createFromInvitation(
            slot, account.id(), invite.tenantId(),
            invite.rolesSnapshot(), invite.scopeSnapshot());

        seats.consumeFor(member.id());
        invite.markAccepted(account.id(), member.id(), now);
        invitations.save(invite);

        AuditRecord record = audit.invitationAccepted(
            actor, invite, member, grant, now);
        auditRepository.insert(record);
        outboxRepository.insertMembershipCreated(record, member);
        return AcceptResult.applied(member.id());
    });
}
~~~

Token có thể chứa public selector hoặc generation; chúng không được tin độc lập với secret và trạng thái invitation. Người gọi không được chọn tenant/role trong AcceptCommand làm nguồn cấp quyền.

Các repository trong ví dụ có chung unit of work. Tạo membership, tiêu thụ reservation, đổi state invitation và ghi audit/outbox phải commit hoặc rollback cùng nhau. Nếu lỗi xuất hiện sau khi tạo membership nhưng trước khi đánh dấu ACCEPTED, transaction phải rollback toàn bộ.

Việc kiểm tra recipient binding cần phối hợp với các đường sửa địa chỉ tài khoản; dữ liệu đã xác minh ở nguồn ngoài phải có hợp đồng tin cậy rõ. Không coi việc giữ khóa một hàng local là khóa được cả trạng thái bên nhà cung cấp danh tính.

Thứ tự lấy khóa phải thống nhất giữa accept, revoke, resend, cập nhật grant và quản lý membership để tránh deadlock và khoảng hở kiểm tra quyền rồi quyền bị thu hồi. Có thể dùng optimistic concurrency/conditional update với kết quả tương đương nếu xử lý conflict đầy đủ.

### Hai request cùng chấp nhận

Một request thắng việc chuyển ACTIVE sang ACCEPTED và tạo membership. Request còn lại phải nhận kết quả đã áp dụng cho đúng account hoặc conflict an toàn; không chạy lại phần cấp quyền.

Unique constraint trên membership trong miền nghiệp vụ giúp chặn hai đường tạo khác nhau. Chỉ khóa invitation chưa đủ nếu hai invitation khác nhau cùng hướng đến một tài khoản.

Receipt “đã chấp nhận” không phải một lần sử dụng token để cấp quyền mới. Có thể trả kết quả lịch sử cho cùng account đã xác thực, sau kiểm tra quyền đọc, nhưng không re-enable membership nếu nó đã bị thu hồi sau đó.

Nếu xóa digest token đã dùng theo policy, lần đọc kết quả lịch sử nên qua endpoint receipt có xác thực và quyền riêng, không vì không còn secret mà tự phát hành link mới.

### Accept cạnh tranh với revoke

Cả hai thao tác cần tuần tự hóa trên invitation:

~~~text
Revoke commit trước
  => accept thấy REVOKED và không tạo membership.

Accept commit trước
  => invitation đã ACCEPTED;
     revoke invitation không được hứa rằng membership chưa từng tồn tại.
~~~

Trong trường hợp accept thắng, muốn ngừng quyền thì thực hiện command thu hồi/đình chỉ membership có quyền và audit riêng. Không sửa lịch sử ACCEPTED thành REVOKED rồi bỏ quên membership đang hoạt động.

Expires_at được kiểm tra tại điểm quyết định đã định nghĩa trong transaction, sau thời gian chờ khóa. Một lần kiểm tra trước khi chờ không đủ. Nếu hệ thống yêu cầu cam kết thời hạn đúng tại commit hoặc tại hệ thống quyền bên ngoài, phải thiết kế cơ chế tương ứng; không suy bảo đảm đó từ một câu if ở controller.

### Membership đã tồn tại

Không dùng thao tác kiểu “insert nếu trùng thì update role từ invitation” một cách mặc định. Nó có thể biến lời mời thành một đường nâng quyền không đi qua quy trình đổi vai trò.

Thiết kế tham chiếu từ chối xung đột và yêu cầu quy trình thay đổi membership riêng. Một policy khác có thể đóng lời mời dư thừa thành SUPERSEDED và trả “đã là thành viên”, đồng thời giải phóng reservation trong transaction. Trong mọi trường hợp, không tự hợp nhất quyền theo phép union.

## 10. Gửi lại, đổi lời mời, hết hạn và thu hồi

### Resend phải có hợp đồng rõ

Có hai lựa chọn phổ biến:

| Chính sách | Cách xử lý token | Điều cần bảo đảm |
| --- | --- | --- |
| Gửi lại cùng generation | Link cũ vẫn dùng được trong hạn gốc | Không tăng quyền, không gia hạn ngầm, bảo vệ secret để gửi lại |
| Xoay token khi gửi lại | Generation mới thay thế generation cũ | Token và job cũ mất hiệu lực; người dùng biết link mới nhất |

Bài không mặc định cả hai chính sách cùng tồn tại. Chọn một chính sách rõ theo loại invitation, rồi kiểm thử toàn bộ đường resend.

Nếu xoay token, transaction phải kiểm tra quyền, quota và expected revision; tăng generation, thay digest, giới hạn expiry và ghi email intent mới. Không gửi token mới ra ngoài trước khi transaction thay generation commit.

Email cũ có thể đến sau email mới. Bước redeem phải kiểm tra generation hiện tại, trả thông báo phù hợp cho link đã được thay thế và không làm sống lại generation cũ. Callback delivery của email cũ cũng không được ghi đè invitation.

Resend tự động do lỗi vận chuyển không nhất thiết là một command xoay token mới. Nếu mỗi retry đều tăng generation, hệ thống có thể liên tục vô hiệu hóa link đã đến người nhận.

### Đổi email hoặc vai trò không phải resend thông thường

Sửa người nhận từ Linh sang người khác là đổi đối tượng được cấp quyền. Sửa READER thành ADMIN là đổi mức quyền. Cả hai cần kiểm tra lại authority, approval và recipient binding, không núp dưới endpoint “gửi lại”.

Trong mô hình tạo invitation mới, bản cũ SUPERSEDED và token cũ bị chặn. Hành động này phải nguyên tử với các tài nguyên cần quản lý như reservation, hoặc dùng một state machine chuyển giao rõ ràng.

### Hết hạn không phụ thuộc cron

Dù state chưa được job cập nhật từ ACTIVE sang EXPIRED, đường accept vẫn từ chối khi now >= expires_at. Cleanup phục vụ hiển thị, giải phóng tài nguyên và retention, không phải rào chắn bảo mật duy nhất.

Nếu cần mời lại sau hết hạn, tạo một quyết định phát hành mới với quyền hiện tại. Không xóa accepted_at, giảm generation hoặc cập nhật expiry của token đã hết hạn tùy ý.

Một record EXPIRED cũng không nên bị xóa ngay nếu replay hoặc điều tra còn có thể xảy ra. Giữ metadata tối thiểu phù hợp, còn raw secret và packet gửi có thể có thời hạn ngắn hơn.

### Thu hồi lời mời và thu hồi membership

Với invitation chưa được chấp nhận, revoke làm link không còn cấp quyền, dừng các job gửi còn có thể dừng và giải phóng giữ chỗ theo policy. Người gọi phải có quyền trên đúng tenant và invitation.

Với invitation đã ACCEPTED, trả kết quả rõ rằng việc gia nhập đã xảy ra. Muốn xóa quyền cần command membership riêng, có thể gồm thu hồi phiên, token hoặc cache quyền theo kiến trúc hệ thống.

Không hứa email đã gửi có thể bị thu hồi khỏi hộp thư. Thu hồi hiệu lực liên kết và quyền thực tế là các hành động có thể kiểm soát tại máy chủ.

## 11. Quota, giữ chỗ và nhiều lời mời cùng lúc

Idempotency bảo vệ retry của cùng command, nhưng không ngăn actor tạo nhiều command khác nhau. Cần giới hạn số invitation đang chờ, số email gửi, số lần resend và phạm vi quyền được cấp.

Có thể dùng các ràng buộc sau, tùy mô hình:

| Miền ràng buộc | Mục đích |
| --- | --- |
| Tenant + actor + operation + idempotency key | Một request retry không tạo thêm hiệu ứng |
| Tenant + recipient key + mục đích/phạm vi của lời mời đang hoạt động | Hạn chế đề nghị trùng không có ý nghĩa |
| Tenant + account ID đối với membership của tenant | Không tạo trùng membership qua hai invitation |
| Invitation ID + token generation + mail kind | Không nhân email vì nhận lại cùng outbox event |
| Reservation ID hoặc allocation key | Giữ/tiêu thụ/giải phóng một suất không bị lặp |

Uniqueness của invitation đang hoạt động không nên dựa vào việc đọc trước rồi insert không có ràng buộc cạnh tranh. Nếu record đã hết hạn nhưng state chưa được dọn, command tạo mới phải giải quyết trạng thái đó có kiểm soát, không bỏ qua tính duy nhất hoặc làm cron thành điều kiện bắt buộc để hệ thống dùng được.

### Hai mô hình hạn mức thành viên

**Giữ chỗ khi mời:** pending invitation chiếm một reservation có hạn. Khi accept, chuyển reservation thành suất đang dùng trong cùng transaction. Revoke/expire giải phóng bằng thao tác idempotent. Resend không chiếm thêm một suất cho cùng reservation.

**Chỉ kiểm tra khi accept:** lời mời không bảo đảm chắc chắn còn chỗ. Khi chấp nhận, khóa/giữ quota nguyên tử cùng tạo membership. Nếu hết chỗ, trả kết quả rõ và không chuyển invitation thành ACCEPTED.

Không làm count thành viên rồi insert ở hai transaction độc lập. Hai người có thể cùng thấy một suất cuối và vượt hạn mức.

Job dọn reservation và accept cũng cần kiểm soát cạnh tranh. Không để job giải phóng một suất vừa được chuyển thành membership, rồi lần tạo sau dùng lại suất đó. Mỗi reservation có state/version và liên kết kết quả tiêu thụ.

### Nhiều invitation cho cùng tài khoản

Nếu hai invitation thuộc cùng tenant nhưng khác scope, chúng không tự có quyền gộp scope vào một membership. Thiết kế tham chiếu yêu cầu membership mới không được tồn tại từ trước; thay quyền đi qua command riêng.

Nếu sản phẩm cho phép thêm scope qua lời mời, mỗi lần thêm cần kiểm tra authority, approval, quyền hiện có và điều kiện tài khoản bị đình chỉ. Đó là một quy trình cấp thêm quyền, không chỉ là xử lý lỗi duplicate key.

Một thành viên từng bị loại hoặc bị cấm tham gia không được trở lại nhờ một invitation cũ còn sót. Tenant policy phải xác định điều kiện tái gia nhập, người được phép cấp lại và audit cần thiết.

Resend chỉ áp dụng cho invitation còn ACTIVE, chưa hết hạn và còn authority hợp lệ theo policy; không được phục hồi ACCEPTED, REVOKED, DECLINED, EXPIRED hoặc SUPERSEDED bằng một cờ tùy ý.

## 12. Chống lạm dụng, rò rỉ thông tin và giữ audit

### Không biến invitation thành công cụ spam hoặc dò tài khoản

Giới hạn theo tenant, actor, recipient key và operation. Chỉ giới hạn theo IP không đủ khi cùng tài khoản mời đến nhiều địa chỉ, đồng thời có thể ảnh hưởng người dùng chung mạng.

Các thông điệp công khai cần tránh tiết lộ tài khoản có tồn tại, đang thuộc tổ chức nào hoặc vai trò hiện tại. Người quản trị có quyền có thể được xem chi tiết phục vụ quản lý, nhưng mức hiển thị đó không được tự mở cho endpoint nhận link chưa xác thực.

Token sai hoặc invitation ID đoán được không nên trả tên người nhận đầy đủ và thông tin tenant nhạy cảm. Log nội bộ có thể có reason code chính xác trong phạm vi kiểm soát truy cập.

Sai tài khoản nhiều lần không được tự tiêu thụ token hoặc thu hồi invitation, vì người biết link có thể gây từ chối dịch vụ cho người nhận thật. Áp dụng rate limit và phản hồi an toàn theo ngữ cảnh thay vì phá hủy đối tượng nghiệp vụ tùy tiện.

Không tin email open, click-tracking hoặc bounce callback như một command chấp nhận/từ chối. Xác thực nguồn callback và ràng buộc provider message ID với đúng mail generation.

### Audit cần dựng lại được quyết định cấp quyền

| Nhóm | Dữ liệu cần thiết |
| --- | --- |
| Đối tượng | Tenant ID, invitation ID, revision và generation |
| Actor | Người tạo, người duyệt, người resend/revoke và người chấp nhận |
| Đề nghị | Role/scope snapshot hoặc digest và tham chiếu cấu hình có bảo vệ |
| Căn cứ | Authorizing grant, approval, phiên bản policy và role |
| Người nhận | Recipient binding ID/key đã giảm lộ dữ liệu theo policy |
| Thời gian | Issued, expiry, quyết định accept/revoke và thời điểm gửi |
| Kết quả | State trước/sau, membership ID, reason code |
| Liên kết | Command ID, request ID, outbox/mail ID và reservation ID |

Không ghi raw token, cookie, header xác thực hoặc link đầy đủ chứa secret vào audit. Áp dụng redaction cho access log, tracing, lỗi parse, email preview và dead-letter, không chỉ cho một logger ứng dụng.

Ghi audit thay đổi quyền cùng transaction nghiệp vụ. Các attempt bị từ chối hoặc transaction rollback cần kênh sự kiện bảo mật độc lập có giám sát, vì audit nằm trong transaction bị rollback không còn tồn tại.

Đối với quản trị viên thao tác thay mặt người khác, giữ cả actor thực và chủ thể được đại diện. Không cho client tự gửi accepted_by, approved_by hoặc created_by rồi coi đó là sự thật.

API xem/export audit, invitation và packet gửi phải có quyền theo tenant, đối tượng và vai trò. Retention cần phân biệt metadata điều tra với secret hoặc nội dung email; không giữ tất cả raw token chỉ vì muốn có lịch sử.

### Quan sát vận hành

Theo dõi tỷ lệ invitation hết hạn, resend, revoke, mismatch danh tính, token generation cũ và duplicate accept. Quan sát pending invitation không có authority hợp lệ, membership tạo ra nhưng thiếu audit/nguồn invitation, reservation bị treo và email của generation đã bị thay thế.

Tỷ lệ email delivered cao không chứng minh quy trình cấp quyền an toàn. Chỉ số “accepted” cũng phải lấy từ transaction membership thành công, không tính theo số lần người dùng mở link.

## 13. Kiểm thử tình huống tấn công logic

Dùng clock điều khiển được, fake mail provider và barrier/latch cho cạnh tranh. Mỗi ca kiểm tra phản hồi API, state invitation, membership/grant, quota, outbox và audit; không chỉ kiểm tra mã HTTP.

| Tình huống | Cách thử | Kết quả cần khẳng định |
| --- | --- | --- |
| Cấp role vượt quyền | Người chỉ được mời READER gửi ADMIN | Không phát hành lời mời có thể cấp ADMIN |
| Sai scope/tenant | Giữ role hợp lệ nhưng đổi project hoặc tenant | Bị chặn trên đúng đối tượng, không lộ dữ liệu tenant khác |
| Mass assignment | Gửi state=ACTIVE, approved_by, accepted_by | Không gán field đặc quyền từ request |
| Bỏ qua duyệt | Gọi thẳng phát hành/accept khi còn PENDING_APPROVAL | Không có membership và không có token hoạt động ngoài chủ đích |
| Sửa sau duyệt | Duyệt READER rồi sửa quyền/destination | Approval cũ không hợp thức hóa đề nghị mới |
| Sai tài khoản | Link của Linh được mở trong session của An | Không cấp membership cho An, không tự gán email Linh |
| Email chưa xác minh | Account có chuỗi email trùng nhưng chưa được xác minh | Chưa đủ recipient binding |
| Giả claim danh tính | Client tự gửi email_verified=true hoặc issuer khác | Không được dùng làm bằng chứng |
| Bỏ qua SSO | Dùng tài khoản local khi tenant yêu cầu SSO | Không vượt tenant policy |
| Link forwarding | Người giữ link đăng nhập account không khớp | Không nhận quyền theo mô hình tham chiếu |
| GET/prefetch | Gọi GET/HEAD hoặc mô phỏng công cụ quét | Không consume token, không tạo membership |
| CSRF accept | Gửi POST qua session cookie mà không có bằng chứng CSRF phù hợp | Không chấp nhận ngoài ý muốn |
| Sửa field ở accept | Đổi role, scope, tenant hoặc user_id trong body | Quyền chỉ lấy từ invitation hợp lệ |
| Hết hạn chưa dọn | Để state ACTIVE nhưng clock qua expires_at | Accept bị từ chối dù cleanup chưa chạy |
| Biên expiry | Thử trước, đúng và sau expires_at | Đúng biên thời gian đã công bố |
| Hai accept đồng thời | Hai worker cùng token và account | Một hiệu ứng membership, không trừ quota hai lần |
| Accept và revoke | Sắp thứ tự bằng barrier quanh transaction | Kết quả đúng thứ tự commit; không báo thu hồi quyền giả |
| Accept và resend xoay token | Xoay generation cạnh tranh với token cũ | Token cũ không vượt generation hiện hành sau khi resend thắng |
| Email cũ đến muộn | Giao mail generation cũ sau mail mới | Không phục hồi token/state cũ |
| Retry vận chuyển | Gửi lại outbox cùng mail key | Không tạo invitation hoặc generation nghiệp vụ mới |
| Dùng lại sau ACCEPTED | Bấm link lại sau khi membership bị đình chỉ | Không re-enable hoặc cấp lại quyền |
| Membership đã tồn tại | Accept lời mời có role khác | Không upsert/union quyền ngoài quy trình riêng |
| Hai invitation cùng account | Chấp nhận đồng thời hai lời mời khác ID | Không tạo membership trùng hoặc vượt scope |
| Tranh suất cuối | Hai người accept khi chỉ còn một chỗ | Một allocation thành công theo policy, không vượt quota |
| Lỗi giữa transaction | Gây lỗi sau tạo member, trước đánh dấu ACCEPTED | Membership, consumption, quota và audit cùng rollback |
| Resend vô hạn | Resend nhiều lần sát hạn | Không vượt absolute_deadline hoặc quota không dấu vết |
| Retarget trái phép | Dùng endpoint resend để đổi email nhận | Cần quy trình mới và vô hiệu hóa căn cứ cũ |
| Grant bị thu hồi | Rút authority khi invitation còn ACTIVE | Accept tuân policy hiện tại, không dùng quyền đã mất |
| Token khác purpose | Đưa reset/verify token vào accept | Không được chấp nhận |
| Rò token | Dùng secret canary rồi xem log/trace/export | Không có raw token hoặc link chứa secret |
| Dò invitation | Gọi ID ngẫu nhiên hoặc token sai | Không tiết lộ recipient/tenant nhạy cảm |
| Revoke sau accept | Thu hồi invitation đã dùng | Không hứa membership đã bị xóa; yêu cầu command quyền riêng |

Với retry sau khi response bị mất nhưng transaction đã commit, hệ thống phải trả kết quả đã áp dụng cho đúng account hoặc cho phép đọc receipt an toàn. Không tạo membership mới và không kéo dài hiệu lực invitation.

Với race, xác nhận cả số hàng membership, số allocation, state cuối và audit tương ứng. Một kết quả API “thành công” lặp lại có thể hợp lệ nếu cùng trỏ đến hiệu ứng gốc; lỗi cần ngăn là lặp hiệu ứng cấp quyền.

Các phép thử email dùng địa chỉ và provider thử nghiệm do nhóm kiểm soát. Không cần gửi thư thật tới người không liên quan để kiểm tra token, prefetch hoặc vòng đời.

## 14. Phân tích lỗi và tiêu chí hoàn thành

### Lỗi giả định: link cũ cấp một vai trò mới

Thiết kế ban đầu lưu invitation với email và role, nhưng link chỉ chứa invitation ID. Người quản trị đổi role từ READER sang ADMIN rồi gửi lại. Khi người nhận bấm email cũ, API đọc role hiện tại, tạo member và đánh dấu lời mời đã dùng.

Lỗi không chỉ là token dễ đoán. Link cũ đang tham chiếu đến một đề nghị có thể thay đổi, không giữ ràng buộc giữa người nhận, nội dung được duyệt và quyền được cấp. Thêm secret vào URL mà vẫn cho sửa quyền ngầm sẽ giữ lại lỗi nghiệp vụ.

Hướng sửa cần đồng thời:

- Giữ đề nghị quyền theo revision/digest và approval tương ứng.
- Kiểm tra người mời có thẩm quyền cấp đúng quyền đó.
- Khi thay đổi nhạy cảm, thay lời mời hoặc generation và vô hiệu hóa căn cứ cũ.
- Cho người nhận thấy đề nghị hiện hành trước khi xác nhận.
- Chấp nhận đúng một lần, trong transaction cùng membership và audit.
- Quản lý membership bằng quy trình riêng sau khi đã cấp.

### Những câu hỏi phải trả lời được

- Ai được mời ai, vào tenant/resource nào và với vai trò nào?
- Lời mời được ràng buộc với email, identity hoặc capability theo mô hình nào?
- Điều kiện danh tính, SSO, xác thực bổ sung và phê duyệt được kiểm tra ở bước nào?
- State và token generation nào đang có hiệu lực; hết hạn được chặn dù cron chưa chạy ra sao?
- Resend có xoay token, gia hạn hay thay đổi quyền không, và giới hạn tối đa là gì?
- Nếu accept, revoke và resend chạy đồng thời, kết quả được tuần tự hóa thế nào?
- Nếu đã có membership, invitation có quyền thay đổi nó không?
- Quota và reservation có cùng commit/rollback với hiệu ứng cấp quyền không?
- Email cũ, callback muộn, retry hoặc dead-letter có thể làm sống lại lời mời không?
- Audit có chỉ ra được actor, đề nghị quyền, căn cứ, thời hạn và membership kết quả mà không làm lộ secret không?
