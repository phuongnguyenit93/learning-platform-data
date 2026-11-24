# Support impersonation: Truy cập hỗ trợ trong ngữ cảnh người dùng

## 1. Tính năng này giải quyết vấn đề gì?

**Support impersonation** cho phép một nhân viên hỗ trợ đã được xác thực sử dụng một phần ngữ cảnh của người dùng để chẩn đoán hoặc thực hiện các thao tác hỗ trợ được cho phép.

Ví dụ, khách hàng báo không nhìn thấy một đơn hàng. Nhân viên cần kiểm tra dữ liệu, quyền và cách ứng dụng phản hồi trong ngữ cảnh khách hàng đó. Nếu nhân viên chỉ nhìn bằng quyền quản trị tổng quát, kết quả có thể khác trải nghiệm của khách.

Tính năng này tạo một ranh giới quyền nhạy cảm: hệ thống đang cho một chủ thể hành động trong ngữ cảnh của chủ thể khác. Một lỗi nhỏ có thể cho phép:

- Nhân viên truy cập khách hàng hoặc tenant ngoài phạm vi phụ trách.
- Gọi API nhạy cảm bằng quyền của người dùng đích.
- Đổi tài khoản nhận tiền, đặt lại thông tin bảo mật hoặc phê duyệt giao dịch.
- Tiếp tục sử dụng quyền sau khi phiên hỗ trợ đã kết thúc.
- Ghi audit như thể chính khách hàng đã thao tác.
- Chuyển quyền hỗ trợ thành token truy cập lâu dài của khách.

Mục tiêu bảo mật là giữ được ba sự thật trong mọi bước:

1. Ai thực sự gửi thao tác?
2. Thao tác đang dùng ngữ cảnh của người dùng nào?
3. Căn cứ nào cho phép thao tác đó trên đối tượng hiện tại?

Trong module bảo mật logic nghiệp vụ, support impersonation phải tuân thủ business invariants, state machine, quyền theo đối tượng, transaction và idempotency như các luồng nghiệp vụ khác.

## 2. Mô hình danh tính: giữ riêng người thực hiện và người được đại diện

Không nên thay toàn bộ principal của nhân viên bằng principal của khách rồi bỏ mất nguồn gốc. Mỗi request cần một ngữ cảnh có cấu trúc:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `real_actor_id` | Người thực sự được xác thực và thao tác | Nhân viên hỗ trợ S |
| `subject_id` | Người dùng có ngữ cảnh được sử dụng | Khách hàng U |
| `tenant_id` | Ranh giới tenant được cấp cho phiên | Tenant T |
| `support_session_id` | Phiên hỗ trợ hoặc grant được cấp | Phiên G |
| `case_id` | Hồ sơ hỗ trợ liên quan, nếu chính sách yêu cầu | Phiếu C |
| `allowed_actions` | Những hành động được cấp cho phiên | Xem đơn, xem cấu hình hiển thị |
| `expires_at` | Hạn hiệu lực của phiên | Một thời điểm do server xác định |

Ngoài ra, đối tượng được truy cập có chủ sở hữu và tenant riêng. Những giá trị đó phải được kiểm tra từ dữ liệu lưu trữ, không suy ra chỉ từ `subject_id` trong request.

Ví dụ:

~~~text
real_actor = support-agent-17
subject = customer-42
session = support-session-805
tenant = tenant-a

action = order.view
object = order-999

Cần kiểm tra:
  phiên thuộc đúng real_actor
  subject và phiên thuộc đúng tenant
  nhân viên được hỗ trợ tenant đó
  subject có quyền xem order-999
  phiên cho phép order.view
  chính sách hỗ trợ cho phép đọc các trường được trả về
~~~

`real_actor_id` không phải một trường thông tin tùy chọn dành riêng cho log. Nó còn tham gia kiểm tra quyền, tách nhiệm vụ, chống lạm dụng và ràng buộc phiên.

Nếu ngữ cảnh thiếu danh tính người thực hiện, hệ thống phải xử lý theo chính sách từ chối. Không tự điền `real_actor = subject` để request tiếp tục chạy.

## 3. Quyền có hiệu lực là phần giao của các giới hạn

Một mô hình an toàn cho thao tác đại diện thông thường:

~~~text
Allow(action, object) =
  nhân viên còn quyền hỗ trợ trong phạm vi liên quan
  AND phiên thuộc đúng nhân viên
  AND phiên ACTIVE và còn hạn
  AND phiên cho phép action và phạm vi object
  AND người dùng đích hiện có quyền tương ứng trên object
  AND chính sách hỗ trợ cho phép action
  AND các bất biến nghiệp vụ vẫn đúng
~~~

Có thể hình dung:

~~~text
quyền đại diện có hiệu lực =
  quyền hiện tại của subject
  ∩ năng lực hỗ trợ được cấp cho real_actor
  ∩ phạm vi của phiên
  ∩ các thao tác được phép đại diện
~~~

“Năng lực hỗ trợ” ở đây là quyền được thực hiện hành động thay mặt người dùng trong một phạm vi, không phải quyền thông thường trên tài khoản cá nhân của nhân viên.

Không lấy hợp của quyền quản trị nhân viên với quyền người dùng đích. Nếu nhân viên có quyền quản lý cấu hình hệ thống, quyền đó không tự trở thành quyền của request đang đại diện khách hàng.

### Phân biệt công cụ hỗ trợ đặc quyền

Có thao tác hỗ trợ cần làm ngay cả khi tài khoản khách bị khóa, chẳng hạn xem trạng thái khóa để xử lý sự cố. Nếu thao tác đó không thuộc quyền của subject, nên mô hình hóa thành công cụ hỗ trợ đặc quyền riêng với kiểm soát riêng.

Không âm thầm nới công thức quyền của mọi phiên impersonation để đáp ứng một ngoại lệ.

### Không kế thừa mọi quyền của tài khoản đích

Nếu subject là quản trị viên tenant, phiên hỗ trợ cũng chỉ nhận những hành động được phiên và chính sách hỗ trợ cho phép. Đích có nhiều quyền không có nghĩa nhân viên được toàn quyền.

Một bearer token hoặc cookie có ngữ cảnh impersonation phải bị giới hạn tương ứng. Không tạo một token đăng nhập đầy đủ của khách rồi chỉ ẩn các nút nhạy cảm trên giao diện.

## 4. Xác định thao tác nào được phép

Một ma trận chính sách minh họa:

| Nhóm thao tác | Cách xử lý minh họa |
| --- | --- |
| Xem trạng thái đơn và lỗi giao diện | Cho phép trong phạm vi hỗ trợ, giới hạn trường dữ liệu |
| Xem dữ liệu cá nhân | Chỉ các trường cần cho hồ sơ hỗ trợ, áp dụng che dữ liệu |
| Đổi tùy chọn hiển thị không có tác động tài chính | Có thể cấp rõ cho một phiên nếu thực sự cần |
| Đổi email đăng nhập, mật khẩu hoặc yếu tố xác thực | Chặn trong phiên đại diện thông thường |
| Tạo API key, token truy cập lâu dài hoặc tích hợp mới | Chặn trong phiên đại diện thông thường |
| Đổi tài khoản nhận tiền, xác nhận chi trả hoặc hoàn tiền | Dùng luồng đặc quyền riêng với phê duyệt phù hợp |
| Phê duyệt giao dịch hoặc chấp thuận điều khoản thay khách | Không tự cho phép bằng quyền của subject |
| Xuất dữ liệu hàng loạt hoặc tải tài liệu nhạy cảm | Cần chính sách riêng theo rủi ro và phạm vi |
| Gửi thông báo ra ngoài dưới danh nghĩa khách | Cần kiểm soát riêng, bảo toàn danh tính người thực hiện |

Đây là ví dụ thiết kế, không phải danh sách bắt buộc cho mọi sản phẩm.

“Chỉ đọc” vẫn có thể gây rủi ro lớn: đọc bí mật, hồ sơ cá nhân, tài liệu tải xuống hoặc dữ liệu nhiều khách hàng. Cần kiểm tra cả tập đối tượng lẫn các trường trả về.

Một trang hiển thị đúng như khách nhìn thấy có thể chứa dữ liệu mà nhân viên không cần biết. Chế độ hỗ trợ có thể sử dụng dữ liệu đã che hoặc view riêng để đáp ứng chính sách.

Chính sách nên từ chối hành động chưa được phân loại cho support impersonation. Khi ứng dụng thêm API mới, API đó không được tự xuất hiện trong tập quyền đại diện chỉ vì subject có quyền gọi.

## 5. Grant và state machine cho phiên hỗ trợ

Một phiên có thể lưu:

~~~text
support_session
  id
  real_actor_id
  subject_id
  tenant_id
  case_id
  reason_code
  allowed_actions
  object_scope
  state
  created_at
  expires_at
  ended_at
  policy_version
  authorization_version
  version
~~~

Một số trường cần dữ liệu bổ sung về người phê duyệt, bằng chứng xác thực tăng cường hoặc sự đồng ý của khách theo chính sách.

Lý do và case ID phục vụ kiểm soát, nhưng không tự cấp quyền. Gõ “khách yêu cầu” trong ô lý do chưa chứng minh nhân viên được truy cập tenant hoặc thao tác đó.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED: Yêu cầu phiên
    REQUESTED --> ACTIVE: Đủ điều kiện cấp
    REQUESTED --> REJECTED: Không đủ điều kiện
    ACTIVE --> ENDED: Nhân viên kết thúc
    ACTIVE --> EXPIRED: Đến hạn và ghi nhận đóng
    ACTIVE --> REVOKED: Thu hồi
    ENDED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
    REJECTED --> [*]
~~~

Không cho phiên đã đóng quay lại `ACTIVE`. Nếu cần làm tiếp, cấp phiên mới và đánh giá lại quyền.

Trạng thái `ACTIVE` trong cơ sở dữ liệu chưa đủ chứng minh còn hiệu lực. Tại mỗi quyết định:

~~~text
session.state == ACTIVE
AND decision_at < session.expires_at
~~~

Đúng tại `expires_at` là hết hiệu lực theo hợp đồng minh họa. Worker cập nhật `EXPIRED` giúp dọn trạng thái, không được quyết định khoảng thời gian được phép truy cập thêm.

Có thể giới hạn một phiên trong một khoảng ngắn, ví dụ mười phút, tùy nhu cầu và rủi ro. Nếu hỗ trợ gia hạn, cần trần tổng thời gian và đánh giá lại điều kiện; không kéo dài vô hạn chỉ vì có request mới.

## 6. Luồng cấp phiên

### 6.1. Các điều kiện cần xác minh

Server cần:

1. Xác thực nhân viên bằng phiên thật của nhân viên.
2. Kiểm tra quyền bắt đầu impersonation, tenant và nhóm khách được hỗ trợ.
3. Kiểm tra subject đích và trạng thái tài khoản theo chính sách.
4. Kiểm tra hồ sơ hỗ trợ, lý do và điều kiện phê duyệt cần thiết.
5. Xác thực tăng cường nếu chính sách yêu cầu.
6. Tính tập hành động và đối tượng được cấp.
7. Tạo phiên với hạn do server quyết định.
8. Ghi audit cấp phiên.
9. Trả ngữ cảnh truy cập được giới hạn và gắn với người khởi tạo.

Không cho phép bắt đầu một phiên mới bằng cách sử dụng danh tính đã impersonate như danh tính thật. Chính sách nên chặn chuỗi “đại diện người A rồi từ đó đại diện người B” trừ khi có mô hình ủy quyền nhiều bước được thiết kế riêng.

### 6.2. Kiểm soát đầu vào

Client có thể gửi subject hoặc case muốn hỗ trợ, nhưng server phải xác minh quan hệ. Các trường sau không được client tự quyết định:

~~~text
real_actor_id
tenant được cấp
allowed_actions cuối cùng
vai trò của subject
expires_at cuối cùng
trạng thái ACTIVE
bằng chứng phê duyệt
~~~

Không đặt token phiên vào URL để tiện chia sẻ. URL có thể đi vào lịch sử, log hoặc được chuyển cho người khác. Credential cần được bảo vệ bằng cơ chế phù hợp với ứng dụng.

Nếu ứng dụng dùng cookie tự động gửi, cần bảo vệ thao tác cấp, kết thúc và thay đổi dữ liệu trước CSRF theo thiết kế xác thực đang dùng.

### 6.3. Không trao credential lâu dài của người dùng đích

Nhân viên không cần biết mật khẩu, mã xác thực hay refresh token của khách để sử dụng tính năng hỗ trợ.

Ngữ cảnh phiên nên có phạm vi và nơi sử dụng xác định. Credential cấp cho ứng dụng hỗ trợ không được tự dùng ở mọi dịch vụ hoặc đổi thành token đầy đủ của subject.

Một token đã được xác minh tính toàn vẹn vẫn phải được kiểm tra scope, người sử dụng, thời hạn và trạng thái thu hồi theo hợp đồng. Tính hợp lệ về định dạng hoặc chữ ký không tự chứng minh thao tác nghiệp vụ được phép.

## 7. Kiểm tra từng request và quyền theo đối tượng

Ví dụ request muốn xem một đơn hàng:

~~~text
1. Xác minh ngữ cảnh truy cập từ cơ chế xác thực tin cậy.
2. Xác định real_actor và support_session.
3. Đọc phiên có thẩm quyền, đối chiếu actor, subject và tenant.
4. Kiểm tra trạng thái, hạn, quyền hỗ trợ hiện tại và action.
5. Nạp đơn trong đúng tenant.
6. Kiểm tra subject có quyền xem đơn theo quan hệ nghiệp vụ.
7. Áp dụng giới hạn dữ liệu dành cho nhân viên hỗ trợ.
8. Ghi audit truy cập theo chính sách.
~~~

Không chỉ dùng điều kiện `order.owner_id == subject_id` cho mọi sản phẩm. Quyền có thể dựa trên thành viên tổ chức, quyền được chia sẻ hoặc vai trò trên dự án. Cần gọi chính sách quyền theo đối tượng thực tế.

Ngược lại, không dùng quyền quản trị của nhân viên để bỏ qua quan hệ giữa subject và object.

Nếu client đổi `orderId`, `subjectId` hoặc `tenantId`, hệ thống phải phát hiện phạm vi không khớp. Dùng UUID khó đoán không thay thế được kiểm tra đó.

Các giới hạn trường dữ liệu cũng phải nằm phía server. Ẩn thông tin trên trình duyệt trong khi API vẫn trả dữ liệu đầy đủ chưa bảo vệ được thông tin.

### Giữ nguyên bất biến nghiệp vụ

Nếu một thao tác được phép trong phiên, nó vẫn phải tuân thủ trạng thái và quy tắc của miền:

- Không sửa đơn đã khóa chỉ vì đang hỗ trợ.
- Không bỏ qua ngưỡng duyệt.
- Không nhận quyền lợi thêm lần nữa.
- Không dùng tài khoản đích để tự duyệt cho người thực hiện thật.
- Không thay đổi chủ sở hữu chỉ vì có quyền xem.
- Không vượt quota hoặc tài nguyên đã cam kết.

Các quy tắc tách nhiệm vụ phải xem xét danh tính thực sự và nguồn gốc nghiệp vụ. Chỉ so sánh `subject_id` với người tạo có thể che việc cùng một nhân viên thực hiện cả hai vai.

## 8. Transaction cho thao tác thay đổi dữ liệu

Nếu phiên hỗ trợ có một thao tác ghi được cho phép, phải bảo vệ đồng thời hiệu lực phiên và dữ liệu nghiệp vụ.

Ví dụ giả mã thay đổi theme hiển thị, một thao tác rủi ro thấp được chính sách cấp rõ:

~~~java
return transaction.execute(() -> {
    TrustedSupportContext context =
        identityResolver.requireTrustedSupportContext();

    SupportSession session = sessions.lockForUpdate(
        context.supportSessionId()
    );

    session.requireSameBinding(
        context.realActorId(),
        context.subjectId(),
        context.tenantId()
    );

    ProtectedAuthorization rights =
        authorization.loadProtectedContext(context, session);

    UserPreferences preferences = preferencesRepository.lockForUpdate(
        session.tenantId(), session.subjectId()
    );

    Instant decisionAt = decisionTimeSource.readAfterLocks();

    session.requireActiveAt(decisionAt);
    rights.requireCurrentSupportAccess();

    supportPolicy.requireAllowed(
        session, "preferences.theme.update", preferences, decisionAt
    );
    subjectPolicy.requireCanUpdateTheme(
        session.subjectId(), preferences, rights
    );

    Optional<UpdateResult> previous = idempotency.findSameIntent(
        context, operationKey, requestFingerprint
    );
    if (previous.isPresent()) {
        return previous.get();
    }

    preferences.changeTheme(validatedTheme);
    preferencesRepository.save(preferences);

    audit.addSupportAction(
        context, session, preferences, decisionAt
    );

    UpdateResult result = UpdateResult.updated(preferences.version());
    idempotency.save(context, operationKey, requestFingerprint, result);

    return result;
});
~~~

Các kiểu và hàm trên là giả mã, chưa phải implementation hoàn chỉnh. Khi hiện thực cần chú ý:

- `TrustedSupportContext` phải đến từ lớp xác thực đã xác minh, không từ một object map trực tiếp từ JSON.
- Quyền hỗ trợ và quyền subject phải được đọc theo cơ chế nhất quán phù hợp; tên `ProtectedAuthorization` không tự tạo tính nguyên tử.
- Thứ tự khóa phiên và đối tượng phải được quy định chung cho mọi đường ghi liên quan.
- Thời gian quyết định được đọc sau các khóa cần thiết.
- Chỉ trường theme đã xác thực được thay đổi; không bind toàn bộ entity từ request.
- Bản ghi idempotency có ràng buộc duy nhất và được ghi cùng transaction.
- Nếu cần outbox, sự kiện cùng commit và mang đủ danh tính người thực hiện.

Thao tác đổi theme chỉ minh họa cấu trúc. Quyền thực hiện nó không được suy rộng sang đổi email, tài khoản nhận tiền hoặc trạng thái đơn.

### Tranh chấp với kết thúc phiên

Một hợp đồng dễ kiểm chứng cho thao tác ghi là: thao tác lấy khóa phiên, kiểm tra và quyết định trong transaction; việc kết thúc hoặc thu hồi cũng điều phối trên cùng phiên.

- Nếu thao tác được quyết định hợp lệ trước khi kết thúc giành được khóa, nó có thể hoàn tất theo hợp đồng.
- Nếu kết thúc đã commit trước, thao tác đến sau phải thấy phiên đóng và bị từ chối.
- Nếu thời gian đã tới hạn khi lấy đủ khóa, không được dùng thời gian lúc nhận HTTP để tiếp tục.

Kết thúc phiên không đồng nghĩa rollback mọi request đã được chấp nhận hoặc mọi tác động bên ngoài đã xảy ra. Giao diện và tài liệu vận hành cần phản ánh đúng giới hạn này.

Nếu cần thu hồi tức thời khi quyền của nhân viên thay đổi, chỉ khóa hàng phiên chưa đủ. Việc cập nhật quyền và kiểm tra cần có cơ chế phối hợp tương ứng, chẳng hạn trạng thái/phiên bản thu hồi được kiểm tra trong ranh giới có tính nhất quán phù hợp. Đọc một epoch từ cache cũ ở đầu request không bảo đảm mục tiêu đó.

## 9. Hết hạn, kết thúc và thu hồi

Cần có ít nhất ba đường đóng phiên:

| Đường đóng | Mục đích |
| --- | --- |
| Nhân viên kết thúc | Hoàn tất công việc hoặc đổi khách đang hỗ trợ |
| Tự hết hạn | Giới hạn khoảng thời gian quyền được sử dụng |
| Thu hồi chủ động | Nhân viên mất quyền, phiên có dấu hiệu bất thường hoặc hồ sơ không còn hợp lệ |

Các đường này phải tác động đến nguồn dữ liệu có thẩm quyền. Chỉ xóa một biến ở giao diện hoặc đóng tab chưa kết thúc được quyền phía server.

### Kiểm tra phía server

Mọi thao tác được bảo vệ cần kiểm tra:

~~~text
state == ACTIVE
AND decision_at < expires_at
AND actor/subject/tenant vẫn khớp
AND quyền hỗ trợ và phạm vi vẫn đáp ứng hợp đồng
~~~

Nếu token tự chứa hạn nhưng hệ thống cần thu hồi trước hạn, phải có cơ chế tra trạng thái, phiên bản quyền hoặc phương án thu hồi tương ứng. Chỉ dựa vào hạn trong token sẽ giữ quyền đến khi token hết hiệu lực.

Không tự chuyển sang chế độ người dùng thông thường khi kiểm tra phiên thất bại. Đó là một đường có thể biến quyền hạn chế thành quyền rộng hơn.

### Khi nhân viên đăng xuất

Cần định nghĩa phiên hỗ trợ phụ thuộc vào phiên xác thực gốc như thế nào. Nếu chính sách yêu cầu phiên nhân viên vẫn còn hiệu lực, backend phải kiểm tra điều đó; không chỉ lưu `real_actor_id` trong token rồi mặc nhiên coi nhân viên đang đăng nhập.

Một session ID riêng lẻ không phải bằng chứng xác thực. Ngược lại, nếu credential đại diện là bearer credential, việc có tên actor trong đó không tự chống được đánh cắp credential. Cần bảo vệ credential và mô hình xác thực theo mức rủi ro.

### Request dài và luồng dữ liệu

Một lượt tải dữ liệu hoặc stream có thể đã được cho phép trước khi phiên bị thu hồi. Dữ liệu đã gửi không thể được thu lại bằng việc đóng phiên.

Với tác vụ dài hoặc đọc nhiều lô, cần chọn hợp đồng rõ: kiểm tra lại ở mỗi lô, cấm trong chế độ hỗ trợ hoặc dùng một quy trình xuất dữ liệu riêng. Không mặc nhiên coi một lần kiểm tra lúc khởi động là đủ cho tác vụ chạy vô hạn.

## 10. Giữ ngữ cảnh đúng khi gọi dịch vụ khác và xử lý nền

### 10.1. Dịch vụ nhận phải biết nguồn gốc hành động

Khi API hỗ trợ gọi dịch vụ đơn hàng, không chỉ truyền `subject_id` rồi để dịch vụ nhận tưởng khách đang thao tác trực tiếp.

Ngữ cảnh được xác minh cần giữ:

~~~text
real_actor
subject
tenant
support_session / grant reference
action scope
correlation / command reference
~~~

Dữ liệu ngữ cảnh phải được truyền bằng cơ chế mà dịch vụ nhận xác thực được. Một header tùy ý từ client chưa phải bằng chứng.

Dịch vụ nhận cần kiểm tra nơi phát hành hoặc nguồn gọi được tin cậy, nơi được phép sử dụng credential, thời hạn và scope, rồi tiếp tục kiểm tra quyền theo đối tượng. Không cấp quyền chỉ vì request đến từ mạng nội bộ.

Nếu gateway chuyển các header đặc biệt, phải loại bỏ giá trị giả từ bên ngoài và ngăn đường gọi vòng không được kiểm soát.

Không dùng credential đầy đủ của khách hoặc token nhân viên có quyền quản trị rộng để tiện gọi mọi dịch vụ.

### 10.2. Tác vụ nền

Một job được tạo trong phiên hỗ trợ cần lưu nguồn gốc bền vững. Không chỉ ghi `created_by = subject`.

Có thể chọn một trong hai hợp đồng:

- **Job phải tiếp tục phụ thuộc phiên:** consumer kiểm tra phiên còn hiệu lực tại điểm quyết định trước tác động, và từ chối hoặc hủy khi phiên đóng.
- **Một lệnh hẹp được cấp quyền bền vững:** lệnh có nội dung bất biến, phạm vi, thời hạn và chính sách thu hồi riêng; việc cấp lệnh được kiểm tra và audit rõ.

Không âm thầm chuyển từ hợp đồng đầu sang hợp đồng sau chỉ vì worker chạy chậm.

Nếu lệnh đã được hệ thống ngoài chấp nhận, thu hồi phiên chưa tự hoàn tác được tác động. Cần cơ chế đối soát hoặc bù trừ của nghiệp vụ tương ứng.

### 10.3. Idempotency trong ngữ cảnh đại diện

Cùng một key không được áp dụng lẫn cho hai subject hoặc hai ý định. Phạm vi key và fingerprint cần bao gồm ngữ cảnh cần thiết: actor, subject, thao tác, đối tượng và phiên/grant theo hợp đồng.

Bản ghi idempotency không được dùng như vé mở lại quyền sau khi phiên đóng. Retry trả dữ liệu cũ vẫn phải đáp ứng quyền đọc kết quả hiện tại. Nếu muốn cho nhân viên xem biên nhận đã thực hiện sau khi đóng phiên, nên có một endpoint biên nhận riêng với quyền phù hợp và dữ liệu giới hạn.

Retry không được tạo thêm tác động ngay cả khi nhân viên mở một phiên hỗ trợ mới. Các bất biến chống trùng của chính nghiệp vụ vẫn phải tồn tại ngoài namespace của từng phiên.

## 11. Tránh lẫn ngữ cảnh giữa tab, request và phiên

### Giao diện phải hiển thị đúng ngữ cảnh

Nên có dấu hiệu rõ ràng rằng nhân viên đang ở chế độ hỗ trợ:

- Danh tính khách và tenant đang được hỗ trợ.
- Tập thao tác hoặc giới hạn quan trọng.
- Hạn phiên.
- Nút kết thúc phiên.
- Cảnh báo ngữ cảnh trước thao tác ghi được cấp.

Các yếu tố này giúp giảm nhầm lẫn; kiểm soát bảo mật vẫn nằm ở server.

Không dùng tên hiển thị duy nhất để nhận diện khách. Hai khách có thể trùng tên; cần thông tin phân biệt phù hợp và tránh lộ dữ liệu không cần thiết.

### Nhiều tab và chuyển khách

Nếu tất cả tab dùng một biến “khách hiện tại” có thể thay đổi toàn cục, request từ tab cũ có thể chạy dưới subject mới.

Nên gắn request với một ngữ cảnh phiên xác định, rồi backend kiểm tra lại binding. Khi chuyển khách, cần xử lý phiên cũ rõ ràng theo chính sách, thay vì chỉ đổi một trường subject trong cùng credential.

Kết thúc phiên phải trở về ngữ cảnh nhân viên đã được xác thực. Không phục hồi ngữ cảnh dựa trên một URL hoặc user ID do client tùy ý chọn.

### Context trong mã ứng dụng

Không lưu subject impersonation trong một biến static dùng chung cho mọi request.

Nếu dùng cơ chế context theo thread, phải nạp và dọn đúng ranh giới request, kể cả khi có exception. Với xử lý bất đồng bộ hoặc thread pool, phải truyền ngữ cảnh một cách có kiểm soát; không giả định nó tự theo sang thread khác hoặc luôn được xóa.

Cache quyền hoặc dữ liệu cũng phải phân biệt các chiều cần thiết. Cache chỉ theo `subject_id` có thể trả view đầy đủ của khách cho phiên hỗ trợ vốn cần che dữ liệu.

Các request phải độc lập: kết thúc hoặc chuyển phiên ở một tab không được làm backend nhầm người thực hiện hoặc người đích của request khác.

## 12. Audit phải ghi đúng người chịu trách nhiệm

Một bản ghi hành động nên có:

~~~text
event_id
event_type: session_started / action_allowed / action_denied /
            session_ended / session_revoked
real_actor_id
subject_id
tenant_id
support_session_id
case_id / reason_code
action
object_type, object_id
decision_at
policy_version
outcome, reason_code
correlation_id
command_id / idempotency_reference nếu có
~~~

Có thể bổ sung trạng thái trước/sau và các thay đổi được phép ghi nhận. Không ghi password, token, mã xác thực hoặc toàn bộ nội dung dữ liệu nhạy cảm.

Ví dụ:

~~~json
{
  "eventType": "support.action.allowed",
  "realActorId": "support-agent-17",
  "subjectId": "customer-42",
  "tenantId": "tenant-a",
  "supportSessionId": "support-session-805",
  "caseId": "case-208",
  "action": "preferences.theme.update",
  "objectId": "preferences-customer-42",
  "outcome": "ALLOWED"
}
~~~

Đây chỉ là phần minh họa danh tính và đối tượng; bản ghi thực tế cần các mốc và tham chiếu theo chính sách.

### Độ bền của audit

Với thao tác ghi thành công, audit hoặc outbox audit có thể được lưu cùng transaction để tránh dữ liệu đã đổi nhưng không có dấu vết.

Sự kiện bị từ chối cần đường ghi phù hợp. Nếu ghi nó trong cùng transaction rồi transaction rollback, dấu vết từ chối có thể mất. Cần thiết kế kênh audit bền vững cho trường hợp đó.

Nếu audit là điều kiện bắt buộc cho một thao tác nhạy cảm, chính sách cần xác định hành vi khi không ghi được audit. Không chỉ báo thành công rồi hy vọng log sẽ xuất hiện sau.

Log nên được bảo vệ khỏi sửa hoặc xóa tùy ý, có phân quyền truy cập và chính sách lưu trữ. Dữ liệu lý do do người dùng nhập cần được xử lý để không gây chèn nội dung log hoặc lộ thông tin không cần thiết.

### Theo dõi hành vi bất thường

Các tín hiệu hữu ích:

- Một nhân viên mở nhiều phiên cho nhiều tenant trong thời gian ngắn.
- Nhiều lần bị từ chối khi gọi thao tác nhạy cảm.
- Truy cập lặp ngoài phạm vi hồ sơ hỗ trợ.
- Tải nhiều đối tượng hoặc xuất dữ liệu bất thường.
- Gia hạn liên tục hoặc dùng credential sau khi đóng phiên.
- Thử bắt đầu phiên lồng nhau.
- Job nền thiếu `real_actor` hoặc thiếu session/grant reference.

Giới hạn số phiên và tốc độ truy cập có thể giảm lạm dụng, nhưng không thay thế kiểm tra quyền trên từng đối tượng.

Sản phẩm cũng có thể hiển thị lịch sử hỗ trợ hoặc thông tin truy cập cho khách theo chính sách. Thông báo hoặc lịch sử đó phải phản ánh nhân viên là người thực hiện, tránh ghi như thể khách tự làm.

## 13. Ví dụ xuyên suốt: kiểm tra một đơn hàng bị thiếu

Khách U thuộc tenant T báo không nhìn thấy đơn O.

### Bước 1: Cấp phiên

Nhân viên S được phân công hồ sơ C, có quyền hỗ trợ T. Server cấp phiên G cho U với:

~~~text
allowed_actions = [order.view]
object_scope = dữ liệu U được phép xem trong T
expires_at = một mốc ngắn do chính sách xác định
~~~

Phiên chưa có quyền đổi đơn, hoàn tiền hoặc phê duyệt.

### Bước 2: Kiểm tra đơn

S gửi yêu cầu xem O trong G. Server xác minh:

- Actor thực sự là S và G thuộc S.
- Subject là U, tenant là T.
- G còn hiệu lực.
- S còn quyền hỗ trợ T.
- O thuộc T và U có quyền xem O.
- Response chỉ chứa trường được phép trong chế độ hỗ trợ.

Nếu O thực tế thuộc người khác và U không được chia sẻ quyền, request bị từ chối. Việc S có thể xem O ở công cụ quản trị riêng không làm phiên G được quyền xem.

Một công cụ chẩn đoán đặc quyền riêng có thể hỗ trợ xác minh lỗi phân quyền nếu chính sách cho phép, nhưng cần căn cứ và audit riêng. Không mở rộng ngầm quyền impersonation để xử lý tình huống này.

### Bước 3: Thử gọi đường ghi

S gửi request cập nhật địa chỉ giao hàng hoặc hoàn tiền bằng G.

Expected: bị từ chối vì G chỉ cho phép `order.view`, ngay cả khi U có quyền thực hiện một số thao tác đó ở trạng thái đơn hiện tại.

Nếu cần xử lý tiếp, dùng quy trình hỗ trợ có quyền phù hợp hoặc yêu cầu khách thao tác theo chính sách.

### Bước 4: Kết thúc và phát lại request

S kết thúc G. Sau đó trình duyệt hoặc công cụ khác gửi lại request xem O bằng credential cũ.

Expected: không có quyền truy cập mới qua G. Nếu có bản ghi idempotency trước đó, nó không được tự mở lại phiên hoặc trả dữ liệu khách ngoài quyền hiện tại.

### Bước 5: Đối chiếu audit

Người kiểm tra phải xác định được S đã dùng ngữ cảnh U, truy cập hoặc thử truy cập O trong hồ sơ C, bằng phiên G và với kết quả nào.

Nếu audit chỉ ghi `user = U`, hệ thống đã mất khả năng phân biệt thao tác hỗ trợ với thao tác trực tiếp của khách.

## 14. Kiểm thử tình huống tấn công logic

### 14.1. Ma trận kiểm thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Nhân viên không có quyền bắt đầu phiên | Không cấp grant hoặc credential |
| Nhân viên được hỗ trợ tenant A, yêu cầu tenant B | Không truy cập chéo phạm vi |
| Đổi subject hoặc tenant trong request sau khi cấp phiên | Không thay binding đã cấp |
| Dùng session ID của nhân viên khác | Không vượt xác thực hoặc ràng buộc actor |
| Subject là quản trị viên tenant | Phiên vẫn bị giới hạn bởi tập thao tác hỗ trợ |
| Gửi `role=admin`, `allowedActions` hoặc `expiresAt` giả | Server không cấp quyền theo dữ liệu client |
| Xem object không thuộc phạm vi quyền của subject | Bị từ chối theo chính sách đối tượng |
| Đường xem hợp lệ nhưng có trường nhạy cảm | Dữ liệu được lọc đúng chế độ hỗ trợ |
| Gọi API đổi mật khẩu, tạo key hoặc đổi người nhận | Bị chặn theo chính sách impersonation |
| Gọi thao tác mới chưa được phân loại | Không tự thừa hưởng quyền |
| Thử tự duyệt qua subject khác | Không vượt tách nhiệm vụ |
| Bắt đầu phiên từ một phiên impersonation đang có | Không tạo chuỗi đại diện ngoài chính sách |
| Trước hạn, đúng tại hạn và sau hạn | Đúng toán tử biên của hiệu lực |
| Worker chưa ghi EXPIRED nhưng đã quá hạn | Request vẫn bị từ chối |
| Phiên đã ENDED hoặc REVOKED, token chưa hết hạn | Thu hồi được thực thi theo hợp đồng |
| Quyền nhân viên hoặc subject thay đổi | Quyền mới được áp dụng theo mô hình nhất quán đã chọn |
| Hai tab hỗ trợ hai khách khác nhau | Không lẫn subject, tenant hoặc dữ liệu cache |
| Exception xảy ra trước khi dọn request context | Request sau không nhận context cũ |
| Dịch vụ nhận thiếu real_actor hoặc grant | Không coi là request khách thông thường để tiếp tục |
| Header nội bộ bị giả từ bên ngoài | Không tạo ngữ cảnh hỗ trợ tin cậy |
| Credential dùng sai dịch vụ hoặc phạm vi | Bị từ chối |
| Job chạy sau khi phiên đóng | Theo đúng hợp đồng phụ thuộc phiên hoặc lệnh hẹp đã cấp |
| Retry cùng key cho subject khác | Không trả nhầm kết quả hoặc thực hiện sai đối tượng |
| Retry sau đóng phiên | Không hồi sinh quyền hoặc lộ dữ liệu từ cache idempotency |
| Lỗi sau đổi dữ liệu trước ghi audit/commit | Không có cập nhật một phần trái hợp đồng |
| Audit hành động bị từ chối | Không mất dấu chỉ vì transaction rollback |

### 14.2. Kiểm thử tranh chấp với thu hồi

Dùng hai transaction hoặc hai luồng thực, có cơ chế điều phối:

~~~text
Kịch bản A:
  T1 khóa phiên, kiểm tra hợp lệ và quyết định thao tác
  T2 yêu cầu thu hồi, chờ khóa
  T1 hoàn tất theo hợp đồng
  T2 thu hồi và commit
  request mới bị từ chối

Kịch bản B:
  T1 thu hồi và commit trước
  T2 lấy khóa phiên, thấy REVOKED
  T2 không đổi dữ liệu
~~~

Khẳng định trạng thái cuối, dữ liệu nghiệp vụ, idempotency và audit. Đừng chỉ kiểm tra mã HTTP.

Với thay đổi quyền nhân viên, cần một test riêng cho cơ chế thu hồi quyền thực sự. Test khóa phiên không chứng minh được một bảng phân quyền hoặc identity provider khác cũng đã được phối hợp đúng.

### 14.3. Kiểm thử nguồn thời gian và phục hồi

Dùng clock điều khiển được ở test chính sách để đặt đúng tại hạn mà không chờ thực tế. Với thời gian cơ sở dữ liệu, cần kiểm tra adapter và điểm lấy thời gian trong integration test.

Sau khi một phiên đã chuyển trạng thái cuối, đưa clock thử nghiệm lùi về trước hạn rồi gọi lại. Phiên không được hồi sinh.

Cho worker khởi động lại hoặc consumer nhận thông điệp trùng. Hệ thống phải duy trì danh tính nguồn gốc và không tạo thêm tác động.

### 14.4. Kiểm thử giới hạn thông tin

Cần kiểm tra cả response, file tải về, cache, log và thông báo lỗi. Một endpoint từ chối thao tác ghi nhưng trả toàn bộ thông tin tài khoản trong lỗi vẫn có thể làm lộ dữ liệu.

Fixture nên có ít nhất hai nhân viên, hai khách và hai tenant, cùng các quyền khác nhau. Nếu mọi test đều dùng một tài khoản quản trị và một khách, lỗi trộn quyền rất dễ bị bỏ sót.

## 15. Những thiết kế dễ gây lạm dụng

| Thiết kế yếu | Hệ quả | Hướng thiết kế |
| --- | --- | --- |
| Đổi principal thành subject và bỏ actor | Không xác định được người thực hiện | Giữ hai danh tính xuyên suốt |
| Tạo token đầy đủ của khách | Vượt tập thao tác hỗ trợ | Credential đại diện có phạm vi hẹp |
| Chỉ ẩn nút nhạy cảm | Có thể gọi API trực tiếp | Policy gate phía server |
| Tin `subjectId` hoặc header do client gửi | Giả mạo người đích hoặc tenant | Xác minh context và binding |
| Chỉ kiểm tra role hỗ trợ tổng quát | Truy cập sai tổ chức hoặc hồ sơ | Quyền theo phạm vi và đối tượng |
| Chỉ kiểm tra khi mở phiên | Quyền cũ tiếp tục sau thay đổi | Kiểm tra hiệu lực tại điểm quyết định |
| Đóng tab để kết thúc | Credential vẫn dùng được | Đóng phiên tại nguồn có thẩm quyền |
| Token còn hạn nên bỏ qua trạng thái phiên | Thu hồi không có tác dụng | Cơ chế thu hồi đúng hợp đồng |
| Cache chỉ theo subject | Trả view sai hoặc lộ dữ liệu | Key và chính sách cache phân biệt ngữ cảnh |
| Job ghi người tạo là subject | Mất nguồn gốc hỗ trợ | Ghi actor, subject và grant |
| Dùng key idempotency để trả mọi kết quả cũ | Lộ dữ liệu sau khi quyền kết thúc | Kiểm tra quyền đọc hiện tại |
| Fallback thành request khách khi thiếu context | Chuyển quyền hẹp thành quyền rộng | Từ chối ngữ cảnh không hợp lệ |

## 16. Các câu hỏi cần trả lời trước khi triển khai

1. Ai được mở phiên, cho những tenant và nhóm khách nào?
2. Những hành động nào được phép, bị chặn hoặc cần luồng đặc quyền riêng?
3. Quyền theo đối tượng của subject có được kiểm tra cùng quyền hỗ trợ không?
4. Actor thật có được giữ ở mọi service, job và audit không?
5. Có thể dùng credential hỗ trợ để tạo quyền truy cập lâu dài của khách không?
6. Mốc hết hạn, thời gian tối đa và cách gia hạn được quy định ra sao?
7. Kết thúc và thu hồi được thực thi phía server bằng cơ chế nào?
8. Quyền nhân viên bị thu hồi thì các phiên đang có phản ứng thế nào?
9. Request hoặc tác vụ đang chạy được xử lý ra sao khi phiên đóng?
10. Hai tab, cache và thread pool có thể làm lẫn context không?
11. Retry có thể tạo thêm tác động hoặc trả dữ liệu sau khi quyền hết không?
12. Có đủ bằng chứng để phân biệt khách tự thao tác với nhân viên đang hỗ trợ không?

Support impersonation an toàn cần duy trì danh tính người thực hiện, giới hạn quyền theo từng phiên và bảo vệ mọi thao tác bằng chính sách phía server. Khả năng hỗ trợ chỉ đáng tin khi việc đại diện không làm mất quyền theo đối tượng, quy tắc nghiệp vụ và trách nhiệm kiểm toán.
