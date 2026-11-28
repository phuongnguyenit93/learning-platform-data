# Remote access time window — Khung thời gian truy cập từ xa

## 1. Khung thời gian giải quyết vấn đề gì?

Một nhà cung cấp được phép sửa máy chủ vào tối thứ Năm không có nghĩa là họ được phép kết nối vào mọi thời điểm trong tuần. Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), quyền truy cập phải gắn với danh tính, tài nguyên, hành động, lý do và thời gian cụ thể.

**Remote access time window** là khoảng thời gian mà một chủ thể được phép khởi tạo hoặc tiếp tục hoạt động truy cập từ xa theo một chính sách xác định. Chính sách phải nói rõ điều gì xảy ra tại đầu và cuối khoảng thời gian đó; chỉ đặt giờ hết hạn trên yêu cầu phê duyệt là chưa đủ.

Ví dụ: kỹ sư của nhà cung cấp được sửa một dịch vụ từ 22:00 đến 00:00, qua cổng PAM, trên hai máy chủ được chỉ định, bằng vai trò chỉ đủ cho công việc. Sau 00:00, kỹ sư không được mở phiên mới, nối lại phiên cũ hoặc dùng credential đã nhận để kết nối trực tiếp.

Bài học này giúp bạn:

- Phân biệt cửa sổ cho phép truy cập với thời lượng phiên, thời gian không hoạt động và độ mới của xác thực.
- Thiết kế cửa sổ truy cập có ranh giới rõ ràng, xử lý được múi giờ và ca làm qua nửa đêm.
- Ràng buộc yêu cầu, phê duyệt, quyền tạm thời, phiên và credential vào cùng thời hạn.
- Xử lý gia hạn, ngắt kết nối, sự cố hạ tầng và truy cập khẩn cấp.
- Xây dựng bằng chứng để chứng minh quyền thực sự hết hiệu lực.

Khung thời gian bổ sung cho least privilege, JIT và JEA. Nó không thay thế giới hạn tài nguyên, lệnh được phép, xác thực mạnh hoặc giám sát phiên.

## 2. Các loại thời gian thường bị nhầm lẫn

| Khái niệm | Câu hỏi được trả lời | Ví dụ minh họa |
|---|---|---|
| Cửa sổ truy cập được phê duyệt | Được truy cập trong khoảng nào? | 22:00–00:00 cho một yêu cầu bảo trì |
| Thời hạn quyền tạm thời | Quyền trên hệ thống đích tồn tại đến khi nào? | Membership quản trị tạm thời hết lúc 00:00 |
| Thời lượng phiên tối đa | Một phiên được tồn tại tối đa bao lâu kể từ khi tạo? | Tối đa 45 phút mỗi phiên |
| Idle timeout | Phiên không có hoạt động phù hợp bao lâu thì bị đóng? | 10 phút không hoạt động |
| Thời hạn credential hoặc lease | Bí mật, certificate hoặc lease được dùng đến khi nào? | Credential tạm thời hết hạn sau 15 phút |
| Độ mới của xác thực | Người dùng đã xác thực mạnh gần đây đến mức nào? | Yêu cầu bước xác thực mới khi mở phiên nhạy cảm |
| Thời gian lưu bằng chứng | Log và bản ghi được giữ trong bao lâu? | Theo chính sách lưu trữ của tổ chức |

Các giá trị trong bảng là ví dụ, không phải cấu hình chuẩn cho mọi hệ thống.

Giả sử cửa sổ đã được duyệt kết thúc lúc 00:00 và người dùng tạo phiên lúc 23:50. Với giới hạn phiên 45 phút, phiên này **không** được tồn tại đến 00:35. Hạn hiệu lực của nó phải bị chặn bởi 00:00, hoặc sớm hơn nếu một điều kiện khác hết hiệu lực.

Idle timeout cũng không thay thế hạn tuyệt đối. Một người có thể tạo hoạt động liên tục để tránh idle timeout; hoạt động đó không được kéo dài quyền qua thời điểm hết cửa sổ. Ngược lại, TCP keepalive chỉ cho biết kết nối còn sống, không chứng minh có hoạt động nghiệp vụ hợp lệ.

Cần phân biệt thêm:

- **Hạn mở phiên:** sau thời điểm này không cho tạo kết nối mới.
- **Hạn hoạt động:** phiên đã mở không còn được thực hiện thao tác đặc quyền sau thời điểm này.
- **Hạn thu hồi hoàn tất:** thời điểm muộn nhất các điểm thực thi đã vô hiệu hóa quyền, phiên và đường truy cập liên quan theo cam kết vận hành.

Nếu tổ chức chỉ kiểm tra hạn mở phiên, phiên tạo trước khi hết hạn có thể tồn tại thêm nhiều giờ. Chính sách phải mô tả riêng việc xử lý phiên đang chạy.

## 3. Mô hình chính sách: từ lịch làm việc đến quyền hiệu lực

### 3.1. Cửa sổ định kỳ không phải phê duyệt vô điều kiện

Lịch “thứ Hai đến thứ Sáu, 08:00–18:00” mô tả thời gian có thể xem xét truy cập. Nó không mặc nhiên cho tất cả nhân viên quyền quản trị trong toàn bộ khoảng đó.

Một quyết định hợp lệ vẫn cần kiểm tra:

1. Danh tính và tình trạng tài khoản.
2. Tài nguyên, vai trò và hành động được yêu cầu.
3. Ticket hoặc lý do nghiệp vụ còn hiệu lực.
4. Phê duyệt đúng thẩm quyền và đúng phạm vi.
5. Điều kiện thiết bị, mạng, xác thực và mức rủi ro theo chính sách.
6. Các giới hạn thời gian đang áp dụng.

Quy tắc cấm truy cập hoặc quyết định thu hồi phải có hiệu lực theo cơ chế ưu tiên chính sách đã định nghĩa. Không để một lịch cho phép rộng vô tình che phủ lệnh thu hồi do sự cố.

### 3.2. Tính giao của các giới hạn áp dụng

Với một lần cấp quyền, có thể biểu diễn khoảng hiệu lực như sau:

~~~text
effective_start = max(
    requested_start,
    approved_start,
    applicable_business_window_start
)

effective_end = min(
    requested_end,
    approved_end,
    applicable_business_window_end,
    entitlement_expiry,
    ticket_expiry
)

Cho phép cấp quyền chỉ khi:
    effective_start < effective_end
    và effective_start <= now < effective_end
    và các điều kiện phi thời gian đều hợp lệ
~~~

Chỉ đưa vào công thức những giới hạn thực sự áp dụng cho loại yêu cầu đó. Nếu có nhiều lịch rời nhau, hệ thống phải tính khoảng phù hợp với từng lần cấp quyền; không ghép điểm bắt đầu của một lịch với điểm kết thúc của lịch khác để tạo ra một khoảng rộng hơn.

Khi phát hành một phiên hoặc credential tạm thời:

~~~text
session_expires_at = min(
    effective_end,
    issued_at + maximum_session_duration
)

credential_expires_at = min(
    effective_end,
    credential_issued_at + maximum_credential_lifetime
)
~~~

Công thức thứ hai áp dụng khi loại credential hỗ trợ hết hạn thực sự. Với mật khẩu tĩnh, một trường “expires_at” trong cơ sở dữ liệu PAM không tự làm hệ thống đích từ chối mật khẩu đó. Cần cơ chế thu hồi hoặc thay đổi credential trên đích và xác minh kết quả.

Mỗi phiên, lease và quyền tạm thời nên tham chiếu cùng một định danh yêu cầu và phiên bản phê duyệt. Đây là cơ sở để truy vết việc gia hạn hoặc thu hồi.

### 3.3. Dùng khoảng nửa mở

Quy ước dễ kiểm thử là **[start, end)**:

- Đúng thời điểm start: có thể được cấp quyền nếu mọi điều kiện khác đạt.
- Trước end: vẫn phải kiểm tra chính sách và trạng thái thu hồi.
- Đúng end và sau end: không còn được phép bắt đầu hoặc tiếp tục thao tác đặc quyền theo cửa sổ cũ.

Quy ước này tránh việc hai ca trực cùng coi một giây ranh giới là thuộc về mình. Độ phân giải thực tế, sai lệch đồng hồ và độ trễ thực thi vẫn cần được quản lý; ký hiệu toán học không tạo ra khả năng ngắt kết nối tức thì trên mọi thành phần.

## 4. Múi giờ, lịch qua nửa đêm và đồng hồ hệ thống

### 4.1. Lưu thời điểm tuyệt đối, giữ ngữ cảnh hiển thị

Với yêu cầu một lần, lưu thời điểm bắt đầu và kết thúc dưới dạng thời điểm tuyệt đối, thường biểu diễn bằng UTC. Đồng thời giữ múi giờ mà người yêu cầu sử dụng để hỗ trợ kiểm tra và giải thích.

Ví dụ một lịch bảo trì tại Việt Nam:

~~~text
Múi giờ yêu cầu: Asia/Ho_Chi_Minh

Bắt đầu hiển thị: 2026-12-10T22:00:00+07:00
Kết thúc hiển thị: 2026-12-11T00:00:00+07:00

Bắt đầu UTC: 2026-12-10T15:00:00Z
Kết thúc UTC: 2026-12-10T17:00:00Z
~~~

Không lưu riêng “22:00–00:00” rồi suy đoán ngày kết thúc. Giao diện phê duyệt phải hiển thị đầy đủ ngày, múi giờ và thời lượng.

Với lịch định kỳ, cần giữ tên múi giờ có quy tắc, chẳng hạn tên vùng IANA, thay vì chỉ giữ một độ lệch UTC cố định. Ở các khu vực có đổi giờ mùa, cùng một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Chính sách phải quy định cách xử lý hoặc yêu cầu chọn thời điểm rõ ràng; không âm thầm mở rộng quyền.

### 4.2. Định nghĩa ca qua nửa đêm

Lịch 22:00 thứ Năm đến 02:00 thứ Sáu phải được biểu diễn thành một khoảng liên tục có ngày kết thúc. Đồng thời xác định lịch nghỉ lễ, ngày đóng băng thay đổi và lịch của tài nguyên được đánh giá theo múi giờ nào.

Nếu người duyệt ở một quốc gia khác, giao diện nên cho thấy cả giờ địa phương của họ và thời điểm theo múi giờ yêu cầu. Việc đổi cách hiển thị không được làm thay đổi thời điểm tuyệt đối đã duyệt.

### 4.3. Không tin đồng hồ của thiết bị người dùng

Quyết định cấp quyền phải dựa trên thời gian từ hạ tầng được quản lý. Chỉnh đồng hồ laptop hoặc sửa tham số thời gian trong yêu cầu không được kéo dài quyền.

Các điểm kiểm soát cần:

- Đồng bộ thời gian và giám sát độ lệch giữa control plane, gateway, vault và hệ thống đích.
- Dùng thời gian tuyệt đối cho lịch nghiệp vụ; dùng bộ đếm thời gian đơn điệu khi phù hợp để đo thời lượng nội bộ.
- Có quy tắc xử lý khi đồng hồ nhảy hoặc độ lệch vượt ngưỡng cho phép.
- Đánh giá lại hạn hiệu lực khi dịch vụ khởi động lại, thay vì chạy lại nguyên TTL cũ.
- Quy định rõ dung sai xác minh thời gian, tránh biến dung sai thành một khoảng gia hạn ngoài ý muốn.

Nếu không xác định được một cách đáng tin cậy rằng quyền còn hiệu lực, hệ thống không nên cấp mới hoặc gia hạn quyền đặc quyền.

## 5. Luồng truy cập có kiểm soát thời gian

Một luồng tham chiếu gồm yêu cầu, phê duyệt, phát hành quyền ngắn hạn, thực thi và thu hồi:

~~~mermaid
flowchart TD
    A[Yêu cầu tài nguyên, quyền, lý do và thời gian] --> B[Phê duyệt phạm vi và cửa sổ]
    B --> C[Đánh giá điều kiện tại lúc kết nối]
    C --> D{Đang trong cửa sổ và còn hợp lệ?}
    D -- Không --> E[Từ chối và ghi lý do]
    D -- Có --> F[Cấp phiên hoặc lease bị chặn bởi hạn cuối]
    F --> G[Theo dõi thời gian, thu hồi và điều kiện rủi ro]
    G --> H{Hết hạn hoặc bị thu hồi?}
    H -- Chưa --> G
    H -- Có --> I[Chặn thao tác mới, kết thúc quyền và phiên theo chính sách]
    I --> J[Xác minh trên các điểm thực thi và lưu bằng chứng]
~~~

### 5.1. Trước khi mở cửa sổ

Phê duyệt trước không đồng nghĩa cấp quyền trước. Với JIT, có thể chuẩn bị yêu cầu nhưng chỉ kích hoạt entitlement hoặc lease khi người dùng thực sự truy cập trong khoảng cho phép.

Cần xử lý trường hợp phê duyệt đến muộn. Nếu yêu cầu 22:00–23:00 được duyệt lúc 22:30, quyền còn lại chỉ là phần giao hợp lệ; không tự dời thời điểm kết thúc sang 23:30. Nếu đã qua 23:00, yêu cầu cũ không còn khoảng hiệu lực để kích hoạt.

### 5.2. Khi mở phiên

Tại thời điểm kết nối, gateway hoặc điểm thực thi phải kiểm tra lại trạng thái hiện hành. Một phê duyệt từng hợp lệ có thể đã bị thu hồi hoặc tài khoản có thể đã bị khóa.

Phiên nên gắn với:

- Danh tính người vận hành, kể cả khi hệ thống đích dùng tài khoản kỹ thuật chung.
- Yêu cầu, ticket, người duyệt và phiên bản chính sách.
- Tài nguyên, vai trò, phạm vi lệnh hoặc tác vụ được phép.
- Thời điểm phát hành và hạn cuối đã tính.
- Trạng thái hoặc định danh lease để hỗ trợ thu hồi.

Không để người dùng cung cấp một TTL lớn hơn thông qua tham số kết nối mà không bị máy chủ kiểm tra và giới hạn.

### 5.3. Trong phiên đang chạy

Hệ thống phải kết hợp kiểm tra hạn tại điểm thực thi với tín hiệu thu hồi. Một tác vụ hẹn giờ ở control plane có thể bị trễ; nó không nên là cơ chế bảo vệ duy nhất.

Ví dụ, gateway kiểm tra quyền trước thao tác nhạy cảm khi giao thức cho phép và áp dụng hạn cuối cho phiên. Với giao thức không hỗ trợ kiểm tra từng lệnh, gateway cần có cơ chế đóng kênh khi hết hạn và kiểm soát riêng những hoạt động có thể tiếp tục trên đích.

Nếu dùng token tự chứa, chữ ký hợp lệ chỉ chứng minh token do bên tin cậy phát hành và chưa bị sửa. Nó không bảo đảm rằng phê duyệt chưa bị thu hồi kể từ lúc phát hành. Thiết kế cần xác định cách kết hợp thời hạn token ngắn, kiểm tra trạng thái hoặc tín hiệu thu hồi tùy kiến trúc.

### 5.4. Tại thời điểm hết hạn

Quy trình hết hạn cần bao phủ các lớp liên quan:

| Lớp | Hành động cần xác định | Điều phải kiểm chứng |
|---|---|---|
| Cổng PAM hoặc bastion | Từ chối phiên mới, đóng hoặc hạn chế phiên hết hạn theo chính sách | Kết nối mới và reconnect không vượt qua được |
| Entitlement trên đích | Xóa role, membership hoặc quyền tạm thời | Quyền thực tế đã biến mất |
| Credential | Thu hồi lease, certificate hoặc thay đổi bí mật theo loại credential | Credential cũ không còn dùng được trên đường truy cập thuộc phạm vi |
| Phiên trên đích | Xử lý token đăng nhập hoặc phiên ứng dụng còn tồn tại | Phiên cũ không tiếp tục duy trì đặc quyền ngoài chính sách |
| Tác vụ đang chạy | Áp dụng quy trình riêng cho tác vụ dài hạn | Không nhầm đóng mạng với dừng mọi tác vụ |
| Bằng chứng | Ghi nhận thời điểm và kết quả từng bước | Có thể chứng minh thu hồi hoàn tất hoặc phát hiện thất bại |

Xóa một thành viên khỏi nhóm không nhất thiết vô hiệu hóa ngay token đăng nhập đã được cấp. Tương tự, đổi mật khẩu không nhất thiết đóng phiên đã xác thực. Phải kiểm thử hành vi cụ thể của hệ thống đích.

Đối với PAM cho người dùng tương tác, ưu tiên không tiết lộ credential khi có thể. Nếu bí mật đã được giao ra ngoài, chỉ thu hồi phiên trên gateway không đủ để kiểm soát mọi bản sao của bí mật đó.

## 6. Hết cửa sổ không đồng nghĩa mọi công việc đã dừng

Một người có thể tạo tác vụ nền, đặt lịch chạy sau hoặc khởi động công việc triển khai trước khi cửa sổ kết thúc. Đóng phiên SSH hoặc RDP không chứng minh rằng các công việc đó đã dừng.

Do đó cần tách hai phạm vi:

**Quyền tương tác của con người:** phải hết theo cửa sổ đã duyệt, bao gồm mở lại phiên hoặc tiếp tục sử dụng quyền tạm thời.

**Quyền thực thi của tác vụ:** phải có chính sách riêng về chủ thể chạy, phạm vi, thời hạn, cơ chế hủy, kiểm toán và xử lý lỗi. Nếu tác vụ được phép tiếp tục, quyết định đó phải thể hiện rõ trong phê duyệt và không được dựa vào credential cá nhân còn sót lại.

Đối với thay đổi có rủi ro khi bị ngắt giữa chừng, chẳng hạn một bước chuyển đổi dữ liệu:

- Ước lượng thời gian và điểm dừng an toàn trước khi bắt đầu.
- Không khởi động bước mới nếu thời gian còn lại không đáp ứng điều kiện vận hành.
- Tách quyền điều phối của con người khỏi danh tính thực thi của hệ thống tự động.
- Định nghĩa ai chịu trách nhiệm theo dõi, hủy hoặc phục hồi khi vượt thời lượng dự kiến.
- Ghi nhận riêng ngoại lệ tiếp tục tác vụ, thay vì âm thầm kéo dài quyền quản trị tương tác.

Không tự động kết luận rằng phải giết mọi tiến trình tại giờ hết hạn. Cách dừng phải đáp ứng cả yêu cầu thu hồi quyền và tính toàn vẹn của hệ thống. Điều này cần được thiết kế trước, không quyết định tùy tiện khi chỉ còn vài giây.

## 7. Cấu hình minh họa và quy tắc đánh giá

Cấu hình sau chỉ là mô hình dữ liệu để trao đổi thiết kế, không phải cú pháp của một sản phẩm PAM cụ thể:

~~~yaml
access_request:
  id: "PAM-REQ-2048"
  principal: "vendor-engineer-17"
  target_group: "payments-maintenance"
  role: "diagnose-and-restart-service"
  ticket: "CHG-2048"
  schedule:
    timezone: "Asia/Ho_Chi_Minh"
    start_at: "2026-12-10T15:00:00Z"
    end_at: "2026-12-10T17:00:00Z"
    interval_semantics: "start-inclusive-end-exclusive"
  limits:
    maximum_session_minutes: 45
    idle_timeout_minutes: 10
    maximum_credential_minutes: 15
  expiry:
    deny_new_sessions: true
    require_active_session_enforcement: true
    revoke_temporary_entitlement: true
    revoke_or_rotate_credential: true
  extension:
    requires_new_approval_version: true
    automatic_extension: false
~~~

Các giá trị thời lượng phải được lựa chọn theo rủi ro và khả năng vận hành. Chúng không thể bù cho role có quyền quá rộng hoặc đường truy cập trực tiếp bỏ qua PAM.

Mã giả kiểm tra một yêu cầu mở hoặc tiếp tục phiên:

~~~text
authorize(request, trusted_now):
    state = load_current_authorization_state(request.id)

    if state is unavailable:
        deny("AUTHORIZATION_STATE_UNAVAILABLE")

    if state.revoked or not state.approved:
        deny("APPROVAL_NOT_ACTIVE")

    if trusted_now < state.effective_start:
        deny("WINDOW_NOT_STARTED")

    if trusted_now >= state.effective_end:
        deny("WINDOW_EXPIRED")

    if not identity_target_action_and_context_match(request, state):
        deny("SCOPE_OR_CONTEXT_MISMATCH")

    expiry = min(
        state.effective_end,
        trusted_now + policy.maximum_session_duration
    )

    issue_bounded_session(
        approval_version = state.approval_version,
        expires_at = expiry
    )
~~~

Mã giả mô tả quyết định logic, chưa phải triển khai hoàn chỉnh. Trong hệ thống phân tán, cần xử lý khoảng đua giữa kiểm tra và cấp phiên: gắn quyết định vào phiên bản trạng thái, kiểm tra lại tại điểm thực thi khi cần và bảo đảm lệnh thu hồi bao phủ phiên vừa phát hành.

Renewal phải là một quyết định mới dựa trên trạng thái hiện hành. “Refresh token thành công” hoặc “kết nối vẫn còn sống” không được mặc nhiên đẩy hạn cuối qua effective_end.

## 8. Gia hạn và truy cập khẩn cấp

### 8.1. Gia hạn là thay đổi quyền

Người dùng có thể được nhắc trước giờ hết hạn để lưu công việc, đánh giá phần còn lại và yêu cầu gia hạn. Cảnh báo chỉ hỗ trợ vận hành; nó không tự thay đổi quyền.

Một yêu cầu gia hạn cần ghi:

- Lý do và phần công việc chưa hoàn thành.
- Thời điểm kết thúc mới, phạm vi tài nguyên và quyền cần giữ.
- Người duyệt và các điều kiện bổ sung nếu có.
- Kết quả đánh giá rủi ro tại thời điểm gia hạn.
- Liên hệ với phê duyệt cũ và phiên bản mới.

Nếu yêu cầu gia hạn đang chờ duyệt khi cửa sổ hết hạn, quyền cũ vẫn phải hết. Sau khi được duyệt, hệ thống chỉ cấp quyền theo khoảng mới hợp lệ. Không suy diễn rằng trạng thái “đang chờ” cho phép tiếp tục.

Phiên hiện hữu chỉ được nhận hạn mới khi cơ chế thực thi hỗ trợ cập nhật có kiểm soát và ghi lại quyết định. Nếu không hỗ trợ, cần một phiên mới theo quy trình. Không sửa đồng hồ hoặc chỉnh trực tiếp trường expiry trong cơ sở dữ liệu vận hành để né phê duyệt.

### 8.2. Break-glass vẫn có thời hạn

Tình huống khẩn cấp có thể cần truy cập ngoài lịch thông thường, nhưng phải qua một nhánh chính sách riêng:

- Xác định ai được kích hoạt và bằng cách nào.
- Giới hạn tài nguyên, quyền và thời lượng.
- Áp dụng xác thực, thông báo và giám sát phù hợp với kịch bản.
- Ghi lý do, định danh sự cố và bằng chứng sử dụng.
- Thu hồi, xử lý credential và hậu kiểm sau sự cố.

Quy trình khẩn cấp phải được chuẩn bị cho trường hợp một số thành phần PAM không khả dụng. Điều đó không có nghĩa là duy trì một tài khoản quản trị vĩnh viễn mà không quản lý việc sử dụng và hết hạn.

## 9. Lỗi hạ tầng và các đường vượt cửa sổ

### 9.1. Control plane mất kết nối

Quy tắc nên được xác định trước:

- Không cấp mới hoặc gia hạn khi không xác minh được trạng thái cần thiết.
- Phiên hiện hữu phải có hạn cục bộ đã được xác thực và không tự kéo dài.
- Nếu cần thu hồi trước hạn, thiết kế phải nêu mức phụ thuộc vào kết nối và độ trễ thu hồi tối đa chấp nhận được.
- Khi quá hạn kiểm tra trạng thái hoặc mất độ tin cậy về đồng hồ, áp dụng hành vi đã quy định và ghi bằng chứng.

Một lease ngắn giúp giới hạn thời gian tồn tại khi mất kênh điều khiển, nhưng độ dài lease phải phù hợp với cam kết thu hồi. Không thể vừa cho phép phiên hoạt động ngoại tuyến rất lâu vừa khẳng định mọi lệnh thu hồi có hiệu lực tức thì.

### 9.2. Dịch vụ thu hồi lỗi hoặc gateway khởi động lại

Việc hết hạn phải được khôi phục từ trạng thái bền vững. Sau khi restart, gateway không được coi một phiên cũ là phiên mới và cấp lại toàn bộ thời lượng.

Quy trình thu hồi nên chạy lặp an toàn: thực hiện lại việc xóa một entitlement đã bị xóa không tạo thêm quyền hoặc gây sai trạng thái. Nếu một bước thất bại, cần retry có giới hạn, cảnh báo và theo dõi đến kết quả xác định.

Không đánh dấu “đã thu hồi” chỉ vì đã đưa một thông điệp vào hàng đợi. Cần phân biệt thời điểm yêu cầu thu hồi, thời điểm điểm thực thi nhận lệnh và thời điểm xác minh hoàn tất.

### 9.3. Đường truy cập trực tiếp

Cửa sổ trên cổng PAM không có tác dụng đầy đủ nếu người dùng vẫn kết nối trực tiếp bằng VPN, SSH key, API token hoặc mật khẩu cũ.

Phải kiểm tra các đường truy cập liên quan đến tài nguyên được quản lý:

- Mạng và tài khoản có buộc phiên quản trị đi qua đường kiểm soát hay không.
- Có credential dài hạn hoặc khóa chưa được đưa vào quản lý hay không.
- Có token ứng dụng hoặc phiên đăng nhập còn hiệu lực sau khi cửa sổ đóng hay không.
- Reconnect và session resume có đánh giá lại quyền hiện hành hay không.
- Tài khoản nhà cung cấp bị ngừng hợp đồng có bị chặn độc lập với lịch truy cập hay không.

Cửa sổ thời gian chỉ có ý nghĩa khi các điểm thực thi và đường truy cập thuộc phạm vi đều thực sự áp dụng nó.

## 10. Bằng chứng kiểm toán và giám sát

Một chuỗi bằng chứng tốt cho phép trả lời: ai yêu cầu, ai duyệt, được làm gì, từ khi nào đến khi nào, đã thực hiện gì và quyền thực tế kết thúc khi nào.

Các trường hữu ích gồm:

| Nhóm | Dữ liệu gợi ý |
|---|---|
| Liên kết | Request ID, approval version, ticket ID, session ID, entitlement hoặc lease ID |
| Danh tính và phạm vi | Người dùng, tổ chức nhà cung cấp nếu có, tài nguyên, role, hành động |
| Thời gian | Khoảng được yêu cầu, khoảng được duyệt, khoảng hiệu lực, thời điểm cấp và hết hạn |
| Quyết định | Cho phép hoặc từ chối, lý do, phiên bản chính sách, điểm thực thi |
| Thay đổi | Gia hạn, thu hồi sớm, break-glass, người quyết định và lý do |
| Kết quả thu hồi | Thời điểm yêu cầu, nhận lệnh, thực thi và xác minh; lỗi hoặc retry |
| Hoạt động | Tham chiếu log hoặc bản ghi phiên theo quyền truy cập và chính sách lưu trữ |

Không đưa mật khẩu, private key hoặc token có thể dùng lại vào log. Bản ghi phiên có thể chứa dữ liệu nhạy cảm nên cần kiểm soát truy cập, bảo vệ tính toàn vẹn và thời gian lưu phù hợp.

Các tín hiệu cần điều tra:

- Có phiên đặc quyền còn hoạt động quá hạn thực thi đã cam kết.
- Có lần sử dụng entitlement hoặc credential sau khi yêu cầu hết hạn.
- Thu hồi bị lỗi, bị tồn đọng hoặc không có xác nhận trên đích.
- Chênh lệch đồng hồ vượt ngưỡng.
- Yêu cầu gia hạn lặp lại hoặc break-glass ngoài lịch thông thường.
- Có kết nối đi thẳng đến tài nguyên thay vì qua đường kiểm soát.

Chỉ số nên phản ánh kết quả, chẳng hạn số phiên vượt hạn và phân bố độ trễ thu hồi. “100% yêu cầu có trường end_at” chưa chứng minh quyền đã hết đúng lúc.

## 11. Tình huống thực hành: nhà cung cấp bảo trì ban đêm

Đội vận hành duyệt yêu cầu PAM-REQ-2048 từ 22:00 đến 00:00. Nhà cung cấp được chẩn đoán và khởi động lại một dịch vụ; không được tạo tài khoản hoặc thay đổi chính sách IAM.

Diễn biến:

1. Lúc 21:55, người dùng thử kết nối. Hệ thống từ chối vì cửa sổ chưa bắt đầu.
2. Lúc 22:05, người dùng hoàn thành xác thực và mở phiên. Hạn phiên là 22:50 do giới hạn 45 phút.
3. Lúc 22:50, phiên hết thời lượng tối đa. Một phiên mới chỉ được tạo sau khi đánh giá lại các điều kiện còn hiệu lực.
4. Lúc 23:50, người dùng mở phiên khác. Hạn của phiên này là 00:00, không phải 00:35.
5. Lúc 23:55, người dùng gửi yêu cầu gia hạn đến 00:30.
6. Đến 00:00, chưa có phê duyệt mới. Hệ thống chặn tiếp tục thao tác theo cửa sổ cũ, xử lý phiên, entitlement và credential bằng cơ chế đã cấu hình.
7. Lúc 00:03, người duyệt chấp thuận khoảng mới còn hợp lệ. Người dùng kết nối theo quyết định mới; không tự phục hồi quyền cũ trong ba phút đã hết hạn.

Nếu công việc triển khai đã được chuyển cho một hệ thống tự động, quyền thực thi của công việc đó phải được xét theo chính sách riêng đã duyệt. Không dùng sự tồn tại của công việc nền để biện minh cho việc giữ phiên quản trị tương tác quá hạn.

Khi đóng yêu cầu, đội vận hành đối chiếu log quyết định với kết quả trên gateway và hệ thống đích. Nếu membership đã xóa nhưng token cũ vẫn sử dụng được, việc thu hồi chưa đáp ứng yêu cầu thiết kế và cần được xử lý như một lỗi kiểm soát.

## 12. Kiểm thử cửa sổ trước khi áp dụng

Kiểm thử cần chứng minh cả quyết định và hiệu lực trên đích. Không chỉ kiểm tra giao diện hiển thị “expired”.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Kết nối ngay trước start | Bị từ chối với lý do chưa đến cửa sổ |
| Kết nối đúng start | Chỉ được phép khi mọi điều kiện khác hợp lệ |
| Kết nối đúng end | Bị từ chối theo quy ước [start, end) |
| Mở phiên gần end | Hạn phiên không vượt end |
| Phiên liên tục có hoạt động | Vẫn hết theo hạn tuyệt đối |
| Chỉ có keepalive | Không tự được coi là hoạt động nghiệp vụ để né idle timeout |
| Phê duyệt đến sau end | Không kích hoạt cửa sổ cũ |
| Gia hạn còn chờ duyệt | Không kéo dài quyền hiện hành |
| Thu hồi sớm | Điểm thực thi phản ánh thu hồi trong giới hạn đã cam kết |
| Reconnect hoặc resume sau end | Phải đánh giá lại và từ chối quyền cũ |
| Gateway restart gần end | Không reset TTL hoặc khôi phục phiên đã hết hạn |
| Control plane không khả dụng | Không cấp mới hoặc gia hạn trái chính sách; phiên cũ bị giới hạn bởi cơ chế cục bộ |
| Tác vụ thu hồi gặp lỗi | Có cảnh báo, retry và trạng thái chưa hoàn tất rõ ràng |
| Sử dụng credential cũ qua đường trực tiếp | Không vượt được kiểm soát đã thiết kế |
| Ca qua nửa đêm hoặc đổi múi giờ hiển thị | Thời điểm tuyệt đối và thời lượng không thay đổi |
| Đồng hồ sai lệch hoặc nhảy thời gian | Không tạo thêm quyền ngoài cửa sổ |
| Xóa quyền nhưng giữ token đích cũ | Xác minh token cũ không tiếp tục duy trì đặc quyền trái chính sách |

Với kiểm thử thu hồi, ghi rõ thời điểm quyết định, thời điểm kết thúc hiệu lực tại từng lớp và sai số đo. Không tuyên bố thu hồi tức thì nếu hệ thống chỉ kiểm tra trạng thái theo chu kỳ.

Các bài kiểm thử tích hợp nên thực hiện trong môi trường được phép, bằng tài khoản và dữ liệu thử nghiệm, đồng thời kiểm tra khả năng phục hồi sau thao tác ngắt phiên.

## 13. Lỗi thiết kế thường gặp

**Chỉ chặn đăng nhập mới:** phiên mở trước hạn vẫn có thể thao tác sau hạn. Cần chính sách cho phiên đang hoạt động và quyền trên đích.

**Dùng idle timeout làm giới hạn duy nhất:** người dùng hoặc tiến trình có thể liên tục tạo hoạt động. Cần hạn tuyệt đối độc lập.

**Cấp TTL đầy đủ mỗi lần reconnect:** kết nối lại có thể kéo dài quyền vô hạn. Mọi phiên mới phải bị chặn bởi cửa sổ còn lại.

**Tin rằng đăng xuất SSO sẽ đóng mọi phiên đích:** các phiên PAM, hệ điều hành và ứng dụng có vòng đời khác nhau. Cần cơ chế phối hợp và kiểm chứng.

**Cho phép gia hạn tự động khi công việc chưa xong:** biến quyền JIT thành quyền thường trực. Gia hạn cần quyết định có thẩm quyền và bằng chứng.

**Đồng nhất mật khẩu hết hạn trong vault với mật khẩu vô hiệu trên đích:** hai trạng thái có thể khác nhau. Thu hồi phải được thực hiện và xác minh tại nơi credential được chấp nhận.

**Bỏ qua công việc nền:** phiên đã đóng nhưng tác vụ hoặc quyền đã tạo ra còn tồn tại. Cần giới hạn hành động và chính sách thực thi cho tác vụ.

**Chỉ ghi nhận lịch mà không đo kết quả:** lịch là ý định; trạng thái ở điểm thực thi mới phản ánh hiệu lực.

## 14. Tự kiểm tra mức hiểu

1. Một phiên mở lúc 17:55 có thời lượng tối đa 60 phút, nhưng cửa sổ kết thúc lúc 18:00. Hạn hiệu lực muộn nhất của phiên là khi nào?

   Hạn muộn nhất là 18:00, trừ khi một điều kiện khác yêu cầu kết thúc sớm hơn. Giới hạn phiên không cho phép vượt cửa sổ.

2. Vì sao xóa tài khoản khỏi nhóm đặc quyền chưa đủ để kết luận quyền đã thu hồi hoàn toàn?

   Token hoặc phiên đã được cấp có thể tiếp tục mang quyền cũ. Cần xác minh cơ chế của hệ thống đích và xử lý vòng đời phiên, token liên quan.

3. Nếu yêu cầu gia hạn đang chờ duyệt tại thời điểm hết hạn, hệ thống nên làm gì?

   Để quyền cũ hết theo chính sách. Chỉ cấp lại hoặc cập nhật quyền khi có quyết định mới hợp lệ và cơ chế thực thi tương ứng.

4. Đóng kết nối PAM có bảo đảm một tác vụ nền trên máy chủ đã dừng không?

   Không. Tác vụ có thể tồn tại độc lập với kết nối; cần chính sách quyền thực thi và quy trình quản lý tác vụ riêng.

5. Bằng chứng nào cho thấy cửa sổ được thực thi?

   Quyết định từ chối ngoài cửa sổ, kết quả chặn hoặc kết thúc phiên, xác nhận entitlement và credential đã bị thu hồi, cùng thời điểm thực thi tại các lớp liên quan.

Khung thời gian truy cập từ xa có giá trị khi thời hạn được truyền xuyên suốt từ phê duyệt đến quyền, credential và phiên thực tế. Thiết kế tốt làm cho ranh giới thời gian rõ ràng, cơ chế thu hồi kiểm chứng được và ngoại lệ có người chịu trách nhiệm.
