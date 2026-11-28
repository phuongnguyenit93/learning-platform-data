# Cloud JIT permission

## Mục tiêu bài học

Trong chương Cloud PAM của module Privileged Access Management (PAM), **Cloud JIT permission** là cơ chế cấp quyền cloud khi một công việc cụ thể cần đến, trong một phạm vi và khoảng thời gian xác định. JIT là viết tắt của Just-in-Time. Mục tiêu là giảm thời gian một danh tính nắm giữ quyền đặc biệt thường trực, đồng thời giữ đủ khả năng vận hành, kiểm toán và ứng phó sự cố.

JIT không chỉ là nút “xin quyền admin trong 30 phút”. Một thiết kế đầy đủ phải kiểm soát người được yêu cầu, quyền được cấp, cách tạo phiên, thời điểm hết hạn, đường thu hồi và những thay đổi lâu dài mà người dùng có thể tạo ra trong cửa sổ được phép.

Bài học dùng mô hình trung lập với nhà cung cấp. Các tên role, trạng thái, policy và API là ví dụ khái niệm hoặc mã giả; không phải cấu hình triển khai trực tiếp của một dịch vụ cloud cụ thể.

Sau bài học, bạn có thể:

- Phân biệt quyền đủ điều kiện, quyền đang được kích hoạt và credential của phiên.
- Thiết kế yêu cầu JIT theo danh tính, hành động, tài nguyên, mục đích và thời hạn.
- Áp dụng least privilege, JEA, phê duyệt và phân tách nhiệm vụ cho cloud.
- Xây dựng vòng đời cấp, hết hạn, thu hồi và xác minh quyền.
- Nhận diện đường kéo dài quyền sau thời hạn qua phiên, role, credential và thay đổi IAM.
- Lưu bằng chứng đủ để đối soát mà không làm lộ credential.

## 1. Từ quyền thường trực đến quyền theo công việc

Giả sử nhóm vận hành có quyền quản trị production để xử lý một số sự cố mỗi tháng. Ngoài các lần cần xử lý, quyền đó vẫn tồn tại. Nếu một tài khoản bị chiếm quyền vào ngày bình thường, kẻ tấn công có thể sử dụng ngay quyền quản trị.

Với JIT, thành viên nhóm có thể được xác định là đủ điều kiện xin một tập quyền vận hành. Khi cần, người đó tạo yêu cầu cho công việc cụ thể. Sau khi các điều kiện được đáp ứng, hệ thống cấp quyền tạm thời hoặc cho phép tạo phiên có quyền giới hạn. Hết thời hạn, quyền phải kết thúc theo cơ chế đã thiết kế và được xác minh.

Tuy nhiên, cửa sổ ngắn không bù được phạm vi quyền quá rộng. Một phiên quản trị toàn bộ tổ chức dù chỉ tồn tại ít phút vẫn có thể thay đổi IAM, tạo credential mới hoặc xóa cơ chế ghi log.

Vì vậy, thiết kế cần kết hợp:

- **Least privilege:** chỉ cấp những hành động và tài nguyên thực sự cần.
- **JIT:** chỉ mở quyền trong khoảng thời gian được phép.
- **JEA, Just Enough Administration:** giới hạn thao tác quản trị theo nhiệm vụ, thay vì mở mọi khả năng của một role lớn.
- **Bằng chứng:** gắn quyền và các lần sử dụng với một yêu cầu có thể đối soát.

Một nhiệm vụ “khởi động lại dịch vụ thanh toán ở production” nên dẫn đến quyền thao tác phù hợp trên dịch vụ đó. Nó không nên tự động dẫn đến quyền quản trị IAM, mạng, kho dữ liệu và tổ chức cloud.

## 2. Bốn đối tượng cần phân biệt

Một trong những nguyên nhân triển khai JIT thất bại là gọi tất cả đối tượng dưới đây bằng cùng một từ “quyền”.

| Đối tượng | Ý nghĩa | Điều không được suy luận |
|---|---|---|
| Eligibility | Chủ thể đủ điều kiện yêu cầu một loại quyền | Đã đủ điều kiện không có nghĩa đang được sử dụng quyền |
| Approval | Yêu cầu với phạm vi cụ thể đã được cho phép | Phê duyệt không phải credential và không mặc nhiên cho phép mọi role |
| Active authorization | Binding, grant hoặc đường cấp quyền đang có hiệu lực | Xóa binding không bảo đảm mọi phiên đã phát hành dừng ngay |
| Session credential | Credential giúp phiên gọi API cloud | Credential hết hạn không tự hoàn tác thay đổi đã tạo ra |

Một người có thể được phê duyệt nhưng chưa có binding hoạt động. Một binding có thể đã bị xóa nhưng phiên đã phát hành vẫn còn khả năng gọi API, tùy cơ chế của nền tảng. Một phiên đã hết hạn nhưng role hoặc credential mới do người dùng tạo trước đó có thể vẫn tồn tại.

Do đó, báo cáo “JIT đã kết thúc” phải nói rõ điều gì đã được kết thúc và bằng chứng nào chứng minh việc đó.

### Con người và workload

Con người thường yêu cầu quyền cho một nhiệm vụ vận hành, có thể cần xác thực tăng cường và phê duyệt. Workload không nên giả làm người dùng bằng tài khoản dùng chung để đi qua cùng một quy trình.

Với workload, nên thiết kế danh tính riêng và quyền theo chức năng. Một job đặc biệt có thể nhận quyền ngắn hạn gắn với job ID và tài nguyên cần xử lý. Tuy nhiên, việc một workload có credential ngắn hạn không tự chứng minh quyền của nó là hẹp hoặc đúng mục đích.

## 3. Mô hình một yêu cầu Cloud JIT

Một yêu cầu có thể được mô hình hóa như sau:

```text
JIT request = (
  requester,
  eligible_role,
  requested_actions,
  resource_scope,
  cloud_boundary,
  business_purpose,
  requested_start,
  authorization_deadline,
  approval_requirements,
  execution_constraints
)
```

Các trường cần được xác định rõ:

- **Requester:** danh tính đã được xác thực, không phải email tùy ý gửi trong form.
- **Eligible role:** loại quyền mà người này có thể xin, không phải mọi role có trong cloud.
- **Requested actions:** danh sách hành động hoặc một gói thao tác đã được duyệt.
- **Resource scope:** tài nguyên, nhóm tài nguyên hoặc phạm vi triển khai cụ thể.
- **Cloud boundary:** tổ chức, tài khoản, project, subscription hoặc ranh giới tương ứng của nền tảng.
- **Business purpose:** sự cố, thay đổi hoặc tác vụ có người chịu trách nhiệm.
- **Authorization deadline:** mốc thời gian cuối cùng được phép có quyền theo yêu cầu.
- **Approval requirements:** người hoặc cơ chế được phép phê duyệt.
- **Execution constraints:** điều kiện bổ sung như đường truy cập, thiết bị hoặc runbook.

Không dùng tên hiển thị tài nguyên làm định danh duy nhất nếu nền tảng có định danh ổn định hơn. Tên có thể trùng giữa môi trường, còn phạm vi role ở cấp cha có thể bao phủ nhiều tài nguyên hơn người phê duyệt tưởng.

### Phê duyệt phải gắn với kế hoạch không bị sửa ngầm

Kế hoạch được duyệt cần xác định các giá trị có ý nghĩa bảo mật: principal đích, role hoặc hành động, phạm vi, thời gian và các điều kiện thực thi.

Nếu người yêu cầu sửa từ “một project thử nghiệm” thành “tổ chức production” sau khi được duyệt, phê duyệt cũ phải mất hiệu lực. Việc chỉ lưu một cờ approved trên bản ghi có thể thay đổi là không đủ.

Có thể dùng một phiên bản kế hoạch bất biến cùng định danh hoặc giá trị kiểm tra nội dung. Hệ thống phải kiểm tra phiên bản được thực thi đúng là phiên bản đã được duyệt.

## 4. Các cách cấp quyền và giới hạn của từng cách

Cloud JIT có thể được thực hiện bằng nhiều cơ chế. Việc lựa chọn phải dựa trên đặc tính thực tế của nền tảng, không chỉ tên tính năng.

| Cách triển khai khái niệm | Cách hoạt động | Điểm cần xác minh |
|---|---|---|
| Binding hoặc grant có điều kiện thời gian | Quyền có điều kiện hiệu lực tới một mốc thời gian | Điều kiện được kiểm tra ở đâu, với hành động nào và có bao phủ phiên đã tạo không |
| Thêm rồi xóa binding | Bộ điều phối thêm quyền và gỡ khi hết hạn | Nếu bộ điều phối hỏng thì quyền có còn tồn tại không |
| Phiên thông qua role được giới hạn | Chủ thể nhận credential tạm thời theo role | Ai được tạo phiên, phiên sống bao lâu và cách chặn phiên còn sống |
| Broker thực thi thao tác | Người dùng gọi một giao diện hoặc runbook được kiểm soát | Broker có giới hạn thao tác và đầu vào hay chỉ chuyển tiếp quyền rộng |
| Job đặc quyền riêng cho nhiệm vụ | Job được cấp quyền cần thiết rồi kết thúc | Ai được sửa job, image, tham số và credential của job |

Các cách có thể kết hợp. Ví dụ, quyền tạo phiên chỉ được mở khi yêu cầu còn hiệu lực, còn phiên phải được giới hạn để không vượt thời hạn đó.

### Không dựa duy nhất vào một job dọn quyền

Nếu thêm một binding vô thời hạn rồi chỉ đặt lịch xóa sau 30 phút, tính tạm thời phụ thuộc vào việc job xóa chạy thành công.

Cần ưu tiên giới hạn thời gian được nền tảng thực thi nếu có và phù hợp. Khi phải dùng bộ điều phối để gỡ quyền, cần có hàng đợi bền vững, retry, đối soát và cảnh báo nếu quá hạn. Không được mô tả giải pháp ấy là “tự hết hạn chắc chắn” nếu cloud không thực thi thời hạn độc lập.

Ngay cả khi một điều kiện thời gian tồn tại, vẫn phải kiểm chứng ảnh hưởng của nó đối với credential đã phát hành, quyền kế thừa và các đường truy cập khác.

### Quyền của bộ điều phối cũng là quyền đặc biệt

Thành phần có thể cấp role cho người khác là một tài khoản đặc quyền. Không nên cấp cho nó khả năng gán mọi role ở mọi phạm vi chỉ vì nó là “hệ thống JIT”.

Thiết kế nên giới hạn:

- Danh sách role hoặc gói quyền được cấp.
- Phạm vi tài nguyên được quản lý.
- Danh tính đích có thể nhận quyền.
- Mẫu điều kiện và thời hạn cho phép.
- Đường sửa cấu hình và mã nguồn của bộ điều phối.

Nếu API cloud không cho giới hạn đủ chi tiết, cần có kiểm soát bù phù hợp và ghi nhận giới hạn đó. Một phép kiểm tra chỉ nằm trong cùng process bị chiếm quyền không tạo ra ranh giới mạnh bằng một giới hạn độc lập ở nền tảng.

## 5. JIT, thời hạn phiên và mốc kết thúc quyền

Giả sử yêu cầu được duyệt tới 10:30. Người dùng bắt đầu tạo phiên lúc 10:29. Nếu hệ thống phát hành credential có thời hạn thêm 30 phút, người dùng có thể giữ khả năng gọi API sau mốc kết thúc yêu cầu.

Cần thiết kế theo một mốc cuối cùng rõ ràng, không chỉ theo thời lượng mỗi lần xin phiên.

```text
request.deadline = 10:30
session.created_at = 10:29

session.expiry <= request.deadline
```

Một cách tính khái niệm:

```text
remaining = request.deadline - trustedNow

if remaining <= 0:
    denyNewSession()

sessionDuration = min(
    requestedSessionDuration,
    configuredSessionLimit,
    remaining
)
```

Công thức chỉ có ý nghĩa nếu nền tảng thực sự chấp nhận và thực thi thời hạn đó. Nếu nhà cung cấp có giới hạn tối thiểu hoặc đặc tính phát hành phiên khiến credential vượt mốc cho phép, phải chọn cơ chế khác, chặn tạo phiên ở khoảng thời gian không còn phù hợp hoặc công khai giới hạn trong thiết kế kiểm soát.

Không tạo ra cảm giác an toàn bằng cách đặt một trường expiresAt trong cơ sở dữ liệu trong khi credential cloud không bị ràng buộc vào trường đó.

### Tách các mốc thời gian

| Mốc | Ý nghĩa |
|---|---|
| Request deadline | Mốc cuối cùng quyền theo yêu cầu được phép tồn tại |
| Latest session creation time | Mốc cuối cùng được tạo phiên theo cơ chế đã thiết kế |
| Credential expiry | Mốc credential cụ thể không còn được nền tảng chấp nhận theo cơ chế của nó |
| Revocation verification time | Thời điểm đã có bằng chứng quyền hoặc phiên mục tiêu bị chặn |
| Cleanup completion time | Thời điểm các binding, grant và đối tượng tạm đã được dọn đúng phạm vi |

Các mốc có thể khác nhau. Hệ thống nên lưu được sự khác nhau đó thay vì một trường “đã hết hạn” duy nhất.

### Gia hạn là một thay đổi quyền

Không tự kéo dài thời hạn khi người dùng refresh trình duyệt, job retry hoặc tạo phiên mới. Nếu cần gia hạn, hãy coi đó là một yêu cầu có phiên bản mới và áp dụng lại điều kiện phê duyệt tương ứng.

Đối với quyền rủi ro cao, gia hạn có thể cần xác thực tăng cường hoặc người phê duyệt mới. Chính sách cần rõ để tránh một chuỗi gia hạn biến quyền JIT thành quyền thường trực.

## 6. Vòng đời cấp và thu hồi quyền

Một mô hình trạng thái có thể dùng:

```text
REQUESTED --> APPROVED --> PROVISIONING --> ACTIVE
    |             |             |             |
    v             v             v             v
 DENIED        CANCELLED      FAILED      REVOKING
                                              |
                                   +----------+----------+
                                   |                     |
                                   v                     v
                            REVOKED_VERIFIED     REVOCATION_PENDING
```

Hết thời hạn là một sự kiện làm mất quyền tiếp tục sử dụng theo yêu cầu và kích hoạt quá trình kết thúc. Nó không tự chứng minh mọi tác động kỹ thuật đã được xử lý.

Có thể lưu riêng:

```text
authorization_state: EXPIRED
enforcement_state: REVOCATION_PENDING
```

Hai giá trị này nói rằng yêu cầu đã hết hiệu lực về mặt chính sách, nhưng hệ thống còn phải xác minh việc chặn quyền thực tế.

### Điều kiện để đánh dấu ACTIVE

Không đánh dấu ACTIVE ngay khi gửi lệnh thêm quyền. Cần biết thao tác đã thành công và cấu hình đích khớp với kế hoạch: principal, role, phạm vi, điều kiện, phiên bản yêu cầu và thời hạn.

Việc đọc lại cấu hình cho biết trạng thái cấu hình. Nó có thể chưa chứng minh mọi đường gọi đã có cùng trạng thái hiệu lực nếu nền tảng có độ trễ lan truyền. Cách xác minh phải phù hợp với cơ chế được sử dụng.

### Điều kiện để đánh dấu REVOKED_VERIFIED

Cần có bằng chứng phù hợp rằng:

1. Không thể tạo phiên đặc quyền mới theo yêu cầu cũ.
2. Binding hoặc grant do yêu cầu đó sở hữu đã được thu hồi đúng cách.
3. Các phiên đã phát hành được xử lý theo khả năng thu hồi của nền tảng.
4. Nếu chưa chặn được phiên còn sống, khoảng thời gian còn lại và kiểm soát bù được xác định.
5. Không còn lỗi dọn quyền chưa xử lý làm thay đổi kết luận.

Khi chưa đủ bằng chứng, giữ trạng thái chờ xác minh và cảnh báo. Không biến một lỗi API thành “đã thu hồi” chỉ để đóng ticket.

## 7. Cấp quyền an toàn khi có retry và xử lý đồng thời

Các thao tác với cloud có thể timeout. Một lệnh cấp quyền có thể đã được áp dụng nhưng phản hồi bị mất. Retry mù có thể tạo nhiều grant hoặc làm lệch trạng thái local và cloud.

Bộ điều phối cần định danh thao tác và đối tượng được quản lý rõ ràng:

```text
request_id: jit-742
request_revision: 3
grant_owner: jit-controller
managed_grant_id: grant-742-r3
principal_id: user-ops-18
role_package: service-restart
resource_scope: production/payment-service
deadline: thời điểm đã được duyệt
```

Mỗi lần retry phải đối soát theo định danh và trạng thái thực tế. Nếu API có hỗ trợ khóa idempotency hoặc cập nhật có điều kiện, dùng đúng cơ chế đó. Nếu không, thiết kế cần ghi nhận khả năng tạo trùng và cách phát hiện, xử lý.

### Không xóa nhầm quyền của yêu cầu mới

Giả sử job dọn quyền của revision 2 chạy chậm. Trong lúc đó, revision 3 đã được phê duyệt và đang hoạt động. Nếu job cũ chỉ biết “xóa role của người này”, nó có thể xóa quyền hợp lệ của revision mới hoặc của một yêu cầu khác.

Cần kiểm tra ownership và phiên bản của đối tượng quyền được dọn. Ưu tiên đối tượng quyền riêng có định danh rõ. Nếu nhiều yêu cầu dùng chung một binding, phải có mô hình quản lý tham chiếu và đối soát; không xóa cả binding chỉ vì một yêu cầu đã hết hạn.

Một kiểm tra version trong cơ sở dữ liệu không tự bảo đảm lệnh API cloud đang chạy sẽ dừng đúng lúc. Với thao tác cạnh tranh, cần thêm khả năng cập nhật có điều kiện của nền tảng nếu có, cơ chế tuần tự hóa phù hợp và bước đối soát sau thay đổi.

### Lưu ý giao dịch giữa local và cloud

Cơ sở dữ liệu của broker và IAM cloud thường không nằm trong cùng một giao dịch. Cần ghi lại ý định trước khi thực thi, theo dõi kết quả và có vòng đối soát khi tiến trình bị dừng giữa chừng.

Không được coi “đã commit trạng thái local” là bằng chứng cloud đã nhận đúng thay đổi, cũng không coi một lỗi phản hồi là bằng chứng cloud chưa thay đổi.

## 8. Ngăn quyền tạm thời tạo ra đặc quyền lâu dài

JIT giới hạn thời gian sử dụng quyền được cấp. Nó không tự giới hạn tuổi thọ mọi đối tượng mà principal có thể tạo trong thời gian đó.

Ví dụ, nếu role tạm thời cho phép sửa IAM, người dùng có thể tạo một principal khác, cấp quyền cho nó và sử dụng principal mới sau khi phiên ban đầu hết hạn. Nếu role cho phép đọc secret của một service account mạnh hơn, người dùng có thể lấy một credential nằm ngoài vòng đời JIT.

Những đường cần xem xét gồm:

| Khả năng trong cửa sổ JIT | Đường kéo dài quyền có thể xuất hiện | Cách giới hạn theo nhiệm vụ |
|---|---|---|
| Tạo hoặc sửa role, trust, binding | Cấp quyền bền vững cho principal khác | Tách khỏi role vận hành thông thường; kiểm soát thay đổi IAM riêng |
| Tạo access key, token hoặc secret dài hạn | Sử dụng credential sau phiên JIT | Chặn hành động không cần thiết; quản lý credential theo quy trình riêng |
| Chuyển sang role hoặc ủy quyền tiếp | Tạo phiên khác ngoài phạm vi ban đầu | Giới hạn trust, delegation và các đường chuyển danh tính |
| Gắn danh tính mạnh vào máy hoặc job | Chạy mã dưới quyền khác | Kiểm soát quyền gắn danh tính và quyền sửa workload |
| Sửa pipeline, image hoặc script đặc quyền | Mã độc chạy ở lần triển khai sau | Phân tách quyền triển khai, kiểm duyệt thay đổi và kiểm soát artifact |
| Sửa logging hoặc nơi lưu bằng chứng | Giảm khả năng phát hiện lạm dụng | Tách quyền quản trị bằng chứng và bảo vệ cấu hình ghi log |
| Đọc secret hoặc dữ liệu rõ | Giữ bản sao sau khi hết hạn | Chỉ cấp khi nhiệm vụ cần; hạn chế đường xuất và ghi nhận phạm vi |

JEA giúp giảm các đường này. Một runbook chỉ khởi động lại một dịch vụ có thể giảm khả năng mở rộng quyền so với shell hoặc role quản trị rộng. Tuy vậy, phải kiểm soát cả đầu vào runbook: không được cho người gọi thay câu lệnh, image hoặc danh tính thực thi để biến một thao tác hẹp thành chạy mã tùy ý.

### Kết thúc quyền khác với hoàn tác thay đổi

Một người được phép tăng số instance trong thời gian JIT có thể tạo ra một thay đổi còn tồn tại sau khi quyền hết hạn. Đây có thể là kết quả đúng của nhiệm vụ.

Không tự động hoàn tác mọi thay đổi cloud khi hết hạn nếu điều đó không thuộc kế hoạch. Phải tách:

- **Thu hồi quyền:** chặn khả năng tiếp tục thực hiện thao tác.
- **Dọn đối tượng tạm:** loại bỏ tài nguyên được xác định là tạm thời.
- **Rollback nghiệp vụ:** đưa cấu hình trở lại trạng thái trước theo một kế hoạch riêng.
- **Điều tra persistence:** tìm thay đổi tạo ra đường truy cập ngoài thẩm quyền.

Một kế hoạch JIT tốt nói rõ những thay đổi nào được giữ lại, những đối tượng nào phải dọn và ai chịu trách nhiệm xác minh.

## 9. Xác thực, phê duyệt và phân tách nhiệm vụ

### Xác thực phải có ý nghĩa tại thời điểm kích hoạt

Một phiên đăng nhập cũ không phải lúc nào cũng đủ cho thao tác đặc quyền mới. Tùy mức rủi ro, có thể yêu cầu xác thực tăng cường trước khi kích hoạt quyền và kiểm tra mức bảo đảm từ nguồn danh tính tin cậy.

Không nhận một tham số client như mfa=true làm bằng chứng. Các claim hoặc tín hiệu xác thực cần được kiểm tra nguồn phát hành, đối tượng nhận, thời hạn và ý nghĩa phù hợp trong hệ thống.

Bản ghi phê duyệt cũng không được chỉ dựa vào tên hiển thị hoặc địa chỉ người duyệt do người yêu cầu nhập.

### Ai được phê duyệt?

Người phê duyệt cần có thẩm quyền với đúng môi trường và loại thao tác. Một người phụ trách môi trường thử nghiệm không mặc nhiên được duyệt quyền production.

Các yêu cầu rủi ro cao có thể cần hai bên độc lập, chẳng hạn chủ hệ thống và người phụ trách bảo mật theo quy trình tổ chức. Hai role mà cùng một người có thể tự sử dụng không tạo ra kiểm soát độc lập.

Người duyệt cần thấy:

- Danh tính người yêu cầu.
- Lý do và định danh sự cố hoặc thay đổi.
- Role hoặc hành động thực tế.
- Phạm vi tài nguyên và cấp cha có thể bị ảnh hưởng.
- Mốc bắt đầu, thời hạn và cách kết thúc quyền.
- Các quyền nhạy cảm như sửa IAM, đọc secret hoặc tắt logging.
- Khác biệt với yêu cầu trước nếu đây là gia hạn.

### Không phải mọi yêu cầu đều cần cùng một mức phê duyệt

Một tổ chức có thể cho phép tự kích hoạt một tác vụ hẹp, rủi ro thấp trong điều kiện đã định trước. Điều đó vẫn cần eligibility, xác thực, giới hạn quyền, thời hạn và bằng chứng.

Không nên dùng một bước phê duyệt thủ công mang tính hình thức cho mọi việc rồi cấp cùng một role admin. Mức kiểm soát cần gắn với tác động thực tế và khả năng giới hạn thao tác.

## 10. Luồng điều phối minh họa

Mã giả sau mô tả việc kích hoạt quyền theo một kế hoạch đã được duyệt:

```text
function activateJit(session, requestId):
    actor = authenticate(session)
    request = loadRequest(requestId)
    plan = loadImmutableApprovedPlan(request.approvedPlanId)

    require actor.id == plan.requesterId
    require eligible(actor, plan.rolePackage, plan.resourceScope)
    require approvalValidFor(plan)
    require requiredAuthenticationSatisfied(actor, plan)
    require trustedNow() < plan.deadline

    intent = reserveProvisioningIntentAtomically(
        requestId = request.id,
        revision = plan.revision,
        expectedState = "APPROVED",
        target = exactGrantTarget(plan)
    )

    result = provisionOrReconcileManagedGrant(
        operationId = intent.id,
        owner = intent.owner,
        principal = plan.principalId,
        permissions = plan.permissions,
        scope = plan.resourceScope,
        deadline = plan.deadline
    )

    observed = readManagedGrant(result.grantId)
    require observed.matchesApprovedPlan(plan)

    markActiveIfRevisionStillCurrent(
        requestId = request.id,
        revision = plan.revision,
        grantId = observed.id,
        evidence = observed.metadata
    )
```

Hàm giả định việc kiểm tra quyền, phiên bản và ghi ý định được thiết kế đúng. Nó không giải quyết tất cả lỗi chỉ bằng cách gọi một API.

Nếu trạng thái yêu cầu thay đổi sang hủy trong lúc cloud đang cấp quyền, vòng đối soát phải nhận diện và thu hồi grant vừa được tạo. Không để grant tồn tại vì thao tác cập nhật ACTIVE thất bại.

Một luồng kết thúc có thể là:

```text
function endJit(requestId, revision):
    intent = reserveRevocationIntent(requestId, revision)
    blockNewSessionIssuance(intent.requestId, intent.revision)

    grant = findManagedGrantByExactIdentity(intent.grantIdentity)
    if grant exists and grant.ownedBy(intent.owner, intent.revision):
        removeOrDisableExactGrant(grant)

    sessions = findSessionsAssociatedWith(intent.requestId, intent.revision)
    sessionResult = revokeOrTrackRemainingSessions(sessions)

    observation = verifyRelevantAccessPaths(intent, sessionResult)

    if observation.provesRequiredAccessEnded:
        markRevokedVerified(intent, observation)
    else:
        markRevocationPending(intent, observation)
        alertResponsibleOperator(intent, observation)
```

Không phải nền tảng nào cũng cho tìm hoặc thu hồi riêng từng phiên. Khi thiếu khả năng đó, thiết kế cần ghi nhận chính xác phần có thể xác minh, hạn chế thời hạn phiên từ đầu và có phương án xử lý phù hợp. Không gọi một hàm có tên revokeSessions rồi suy luận rằng mọi dịch vụ cloud đều cung cấp ngữ nghĩa ấy.

### Cần kiểm soát cả lỗi của hệ thống bằng chứng

Nếu hệ thống không lưu được bằng chứng bắt buộc, quyết định có tiếp tục cấp quyền hay không phải theo chính sách rủi ro đã định trước.

Đối với quyền nhạy cảm thông thường, nên tránh cấp quyền mới khi không thể duy trì chuỗi bằng chứng cần thiết. Với đường khẩn cấp, cần cơ chế bằng chứng dự phòng và đối soát sau phục hồi. Không ghi token hay credential vào một file debug để thay thế.

## 11. Kiểm chứng thu hồi và đối soát quyền

### Đọc lại cấu hình là cần nhưng chưa đủ

Một lệnh đọc IAM cho thấy binding đã biến mất có thể chưa trả lời:

- Người dùng có một binding khác ở cấp cha hay không.
- Một nhóm khác còn cấp cùng quyền hay không.
- Phiên đã phát hành có còn được chấp nhận hay không.
- Người dùng đã chuyển sang danh tính khác hay chưa.
- Có một resource policy hoặc đường ủy quyền khác đang cho phép hay không.

Vì vậy, đánh giá quyền hiệu lực cần nhìn qua các đường cấp quyền liên quan. Không đồng nhất “grant của yêu cầu đã bị xóa” với “principal không có bất kỳ quyền nào”.

Đồng thời, cần phân biệt quyền đã có trước với quyền do JIT tạo. Nếu principal đã có quyền thường trực tương đương, yêu cầu JIT có thể không đem lại lợi ích giảm quyền như thiết kế mong muốn.

### Kiểm chứng phù hợp với mức rủi ro

Có thể kết hợp:

1. Đọc lại đối tượng quyền do hệ thống quản lý.
2. Phân tích policy và quyền kế thừa liên quan.
3. Kiểm tra khả năng tạo phiên mới.
4. Thử một hành động an toàn, có phạm vi hẹp để kiểm chứng đường truy cập nếu phù hợp.
5. Đối soát log sau mốc hết hạn.

Một API đọc thành công không chứng minh API ghi cũng được cho phép. Một API bị từ chối cũng không chứng minh mọi quyền đặc biệt đã bị chặn. Kịch bản xác minh phải nói rõ điều đã được chứng minh và giới hạn của bằng chứng.

Không thử một thao tác phá hủy trên production chỉ để chứng minh rằng quyền đã được thu hồi.

### Vòng đối soát độc lập

Ngoài worker cấp và thu hồi, cần một vòng đối soát phát hiện:

- Grant do JIT quản lý nhưng không có yêu cầu hợp lệ.
- Yêu cầu đã hết hạn nhưng binding hoặc phiên liên quan còn cần xử lý.
- Quyền thực tế rộng hơn kế hoạch.
- Thời hạn bị sửa hoặc bị mất điều kiện.
- Nhiều grant phát sinh do retry.
- Đối tượng được gắn nhãn quản lý sai hoặc ownership không rõ.

Đối soát không nên tự xóa mọi quyền “trông có vẻ giống” quyền tạm thời. Chỉ sửa những đối tượng có phạm vi và ownership được xác định, theo chính sách đã được phép.

## 12. Vận hành khi có sự cố

### Bộ điều phối cấp quyền ngừng hoạt động

Nếu cloud có cơ chế thực thi thời hạn độc lập, kiểm tra quyền sẽ kết thúc theo điều kiện nào và phiên đã phát hành bị ảnh hưởng ra sao.

Nếu hệ thống phụ thuộc vào job gỡ binding, cần phục hồi hàng đợi, chạy đối soát và cảnh báo khi quyền vượt hạn. Việc khởi động lại broker không được làm mất danh sách quyền phải thu hồi.

### Identity provider hoặc PAM không sử dụng được

Đường break-glass cần được thiết kế trước với danh tính, phạm vi, cách truy cập và bằng chứng phù hợp. Không phát sinh một tài khoản admin dùng chung vô thời hạn ngay trong lúc sự cố mà không có trách nhiệm theo dõi.

Sau khi phục hồi, đối soát mọi quyền khẩn cấp, phiên còn sống và thay đổi IAM. Kết thúc đường khẩn cấp là một phần của xử lý sự cố.

### Tài khoản đang có quyền JIT bị chiếm quyền

Không chờ hết thời hạn như một biện pháp duy nhất. Có thể cần:

- Chặn tạo phiên mới và thu hồi eligibility tạm thời.
- Thu hồi grant, phiên và credential liên quan theo khả năng nền tảng.
- Cô lập workload hoặc đường truy cập bị xâm nhập.
- Kiểm tra role, trust, secret và các đối tượng được tạo trong cửa sổ quyền.
- Bảo vệ log và lưu bằng chứng điều tra.
- Xác minh hiệu lực thu hồi và phần rủi ro còn lại.

Nếu credential của một principal khác đã bị đọc, việc kết thúc phiên JIT ban đầu không xử lý được credential ấy. Phạm vi ứng phó phải theo dữ liệu và quyền thực tế đã bị tiếp cận.

### Thao tác cloud bị chậm qua thời hạn

Một tác vụ đã được nền tảng chấp nhận trước thời hạn có thể tiếp tục chạy sau khi credential hết hiệu lực, tùy ngữ nghĩa dịch vụ. Cần xác định quyền được kiểm tra lúc gửi yêu cầu hay còn được kiểm tra trong quá trình thực thi.

Mốc hết hạn quyền không phải lời hứa tự động hủy mọi hoạt động dài hạn đã được khởi tạo. Nếu yêu cầu nghiệp vụ cần hủy tác vụ, phải có cơ chế hủy và bằng chứng riêng.

## 13. Bằng chứng và chỉ số vận hành

Một chuỗi bằng chứng nên liên kết được:

```text
Yêu cầu
  --> kế hoạch được duyệt
  --> quyết định kích hoạt
  --> grant hoặc binding thực tế
  --> phiên và hoạt động cloud
  --> kết thúc quyền
  --> xác minh và đối soát
```

| Nhóm bằng chứng | Trường dữ liệu điển hình |
|---|---|
| Yêu cầu | Request ID, revision, requester, mục đích, phạm vi, deadline |
| Xác thực và phê duyệt | Danh tính, thời điểm, mức bảo đảm, kế hoạch được duyệt |
| Cấp quyền | Grant ID, principal đích, role hoặc hành động, phạm vi thực tế |
| Sử dụng | Session reference, principal cloud, API, resource, kết quả |
| Kết thúc | Lý do, thời điểm chặn phiên mới, thao tác thu hồi |
| Xác minh | Phương pháp, quan sát, thời điểm và giới hạn kết luận |
| Ngoại lệ | Lỗi, retry, thời gian quyền vượt hạn và người xử lý |

Không lưu access token, private key, credential phiên hoặc secret vào bằng chứng. Một session reference dùng để đối soát không được biến thành credential có thể dùng lại.

Bằng chứng cần có quyền đọc, thời hạn lưu và cơ chế bảo vệ phù hợp. Người đang sử dụng quyền JIT không nên có khả năng tự xóa toàn bộ dấu vết của chính mình.

### Một số chỉ số có ích

- Số principal còn quyền đặc biệt thường trực so với mục tiêu thiết kế.
- Số yêu cầu đang ACTIVE, đã hết hạn nhưng chưa xác minh thu hồi và bị lỗi cấp quyền.
- Độ trễ từ deadline tới thời điểm xác minh thu hồi.
- Số lần cấp quyền rộng hơn phạm vi được duyệt.
- Tỷ lệ quyền được cấp nhưng không được sử dụng.
- Số phiên hoặc grant không liên kết được với yêu cầu.
- Số lần dùng break-glass và thời gian đối soát hoàn tất.

Nếu chưa có phương pháp xác minh quyền thực tế, chỉ số “thu hồi trong một giây” có thể chỉ đang đo thời gian cập nhật cơ sở dữ liệu. Cần ghi rõ điểm bắt đầu, điểm kết thúc và nguồn đo.

## 14. Tình huống minh họa: khởi động lại dịch vụ production

### Bối cảnh

Một kỹ sư cần khởi động lại dịch vụ thanh toán để xử lý sự cố. Người này không có quyền quản trị production thường trực.

Yêu cầu xác định:

```text
Người yêu cầu: engineer-18
Nhiệm vụ: khởi động lại payment-service
Môi trường: production
Phạm vi: đúng định danh dịch vụ được chọn
Gói quyền: service-restart
Thời hạn: cửa sổ được phê duyệt theo sự cố
Loại trừ: sửa IAM, đọc secret, thay image, thay danh tính workload
```

### Luồng thực hiện

Người phê duyệt kiểm tra sự cố và phạm vi. Hệ thống yêu cầu xác thực phù hợp rồi kích hoạt gói quyền. Kỹ sư thực hiện qua giao diện hoặc runbook đã giới hạn.

Nếu nền tảng không có một quyền “restart” hẹp tương ứng, cần đánh giá các hành động thực tế cần thiết và cách broker hoặc runbook giữ giới hạn. Không gọi một tập quyền quản trị triển khai rộng là “restart-only” chỉ vì nút trên giao diện có tên Restart.

Sau thao tác, hệ thống ghi nhận API, tài nguyên, kết quả và session reference. Quyền được kết thúc sớm khi nhiệm vụ hoàn thành hoặc hết hạn theo mốc đã duyệt, tùy sự kiện đến trước.

### Điều cần kiểm chứng

- Người dùng không tác động được dịch vụ khác.
- Không thay image hoặc danh tính thực thi để chạy mã ngoài nhiệm vụ.
- Không tự cấp quyền IAM hoặc lấy secret.
- Không tạo phiên vượt deadline.
- Retry của hệ thống không nhân đôi grant.
- Lệnh thu hồi chỉ tác động grant của yêu cầu này.
- Những lần gọi sau kết thúc được xử lý đúng theo cơ chế quyền và phiên đã thiết kế.

Dịch vụ tiếp tục chạy sau khi quyền kết thúc là kết quả bình thường. Không cần dừng dịch vụ chỉ vì kỹ sư không còn quyền thao tác.

## 15. Bài thực hành trong môi trường thử nghiệm

Dùng một ranh giới cloud thử nghiệm, tài nguyên không chứa dữ liệu thật và danh tính được tạo cho bài thực hành. Bài học không yêu cầu chạy các thao tác này trên production.

### Bước 1: Xác định một nhiệm vụ hẹp

Chọn một tác vụ có thể kiểm chứng an toàn, chẳng hạn đọc một loại telemetry hoặc thực hiện một thao tác quản trị được giới hạn trên tài nguyên thử.

Viết ra principal, hành động, tài nguyên, thời hạn, người phê duyệt và đường thu hồi. Xác định rõ những khả năng không cần cho nhiệm vụ, đặc biệt là sửa IAM, tạo credential và thay logging.

### Bước 2: Chọn cơ chế cấp quyền

Ghi rõ:

- Quyền được tạo bằng binding, role session hay broker.
- Thành phần nào thực thi thời hạn.
- Credential đã phát hành sống tới khi nào.
- Có chặn được phiên còn sống hay chỉ chặn phiên mới.
- Cách xử lý khi API cấp hoặc thu hồi timeout.
- Cách xác định ownership của grant.
- Cách phát hiện quyền còn sót khi broker ngừng hoạt động.

Nếu không trả lời được một câu hỏi, đánh dấu đó là giới hạn cần kiểm chứng, không tự suy đoán từ tên tính năng.

### Bước 3: Kiểm tra các trường hợp

| Kịch bản | Kết quả mong đợi |
|---|---|
| Người không đủ eligibility gửi yêu cầu | Từ chối |
| Người đủ điều kiện xin ngoài phạm vi được phép | Từ chối |
| Người yêu cầu tự duyệt trường hợp cần độc lập | Từ chối |
| Sửa tài nguyên sau phê duyệt | Phê duyệt cũ không còn hợp lệ |
| Kích hoạt đúng kế hoạch và còn hạn | Chỉ cấp tập quyền đã duyệt |
| Gọi hành động ngoài gói nhiệm vụ | Bị chặn theo thiết kế |
| Tạo phiên sát deadline | Không tạo khả năng truy cập vượt mốc cho phép |
| Refresh giao diện sau deadline | Không tự gia hạn |
| Retry sau timeout cấp quyền | Đối soát, không tạo grant thừa |
| Job dọn revision cũ chạy sau khi có revision mới | Không xóa nhầm quyền của revision mới |
| Bộ điều phối ngừng trước giờ hết hạn | Giới hạn thời gian hoặc cơ chế phục hồi hoạt động như đã công bố |
| API thu hồi trả lỗi | Giữ trạng thái chờ xử lý và cảnh báo |
| Thu hồi binding trong khi còn phiên | Xử lý hoặc theo dõi phiên theo khả năng đã xác minh |
| Principal có quyền kế thừa khác | Phát hiện, không tuyên bố đã mất mọi quyền chỉ vì grant JIT bị xóa |
| Grant xuất hiện nhưng không có yêu cầu hợp lệ | Vòng đối soát phát hiện và xử lý theo ownership |
| Kiểm tra log | Đủ liên kết request, grant, session và kết thúc; không lộ credential |

Các kiểm tra phải phù hợp khả năng nền tảng được dùng. Một kết quả bị giới hạn bởi phiên hoặc độ trễ cần được ghi nhận đúng, không làm cho báo cáo đẹp hơn bằng cách bỏ qua.

### Bước 4: Hoàn thiện hồ sơ thực hành

Hồ sơ nên có mô hình quyền, sơ đồ trạng thái, một lần cấp và kết thúc thành công, một lỗi thu hồi, một tình huống cạnh tranh phiên bản và bằng chứng đối soát.

Không cần đưa credential thật vào báo cáo. Dùng định danh thay thế khi thông tin hạ tầng hoặc danh tính không cần xuất hiện đầy đủ.

## 16. Lỗi thiết kế thường gặp

**Chỉ giảm thời hạn credential nhưng giữ đường tạo phiên vô thời hạn.** Người dùng có thể liên tục lấy credential mới. Cần giới hạn eligibility hoặc quyền kích hoạt, kiểm tra deadline ở mỗi lần tạo phiên và đánh giá toàn bộ đường cấp quyền.

**Cấp role admin cho mọi nhiệm vụ.** JIT giảm thời gian nhưng không giảm đầy đủ phạm vi tác động. Thiết kế gói quyền theo công việc và kiểm soát đường leo thang.

**Coi phê duyệt ticket là bằng chứng quyền cloud đúng.** Cần đọc lại principal, phạm vi, điều kiện và đối tượng quyền thực tế; liên kết chúng với phiên bản kế hoạch.

**Đánh dấu đã thu hồi ngay khi gửi API.** Phải đối soát kết quả, quyền kế thừa, phiên và giới hạn thực thi trước khi kết luận.

**Xóa binding chung mà không biết ownership.** Một yêu cầu kết thúc có thể làm gián đoạn yêu cầu khác. Cần định danh grant hoặc quản lý quyền dùng chung có phiên bản và đối soát.

**Cho phép phiên tạo credential hoặc role mới ngoài nhiệm vụ.** Quyền tạm thời có thể sinh đặc quyền lâu dài. Giới hạn hành động và theo dõi những thay đổi tạo đường truy cập.

**Giấu giới hạn dưới trạng thái EXPIRED.** Hết hạn yêu cầu không chứng minh phiên đã bị chặn. Lưu riêng trạng thái chính sách và trạng thái thực thi.

**Đặt toàn bộ quyền cấp, phê duyệt và xóa log vào một principal.** Khi principal đó bị chiếm quyền, chuỗi kiểm soát có thể bị phá vỡ. Phân tách nhiệm vụ và bảo vệ bằng chứng ở ranh giới phù hợp.

## 17. Các câu hỏi trước khi đưa Cloud JIT vào vận hành

Một thiết kế cần trả lời được:

1. Principal nào được xin loại quyền nào và phạm vi tối đa là gì?
2. Người phê duyệt đang duyệt quyền thực tế hay chỉ một tên role khó hiểu?
3. Ai có thể sửa kế hoạch, bộ điều phối và policy cấp quyền?
4. Mốc cuối cùng quyền được phép tồn tại là gì?
5. Phiên tạo sát giờ kết thúc có vượt mốc đó không?
6. Điều gì kết thúc quyền khi broker hoặc lịch dọn gặp lỗi?
7. Có phân biệt quyền bị thu hồi với phiên còn sống và thay đổi còn tồn tại không?
8. Principal có đường tạo quyền bền vững, chuyển danh tính hoặc lấy credential khác không?
9. Retry và job cũ có thể tạo thừa hoặc xóa nhầm quyền không?
10. Bằng chứng nào cho phép kết luận việc cấp và kết thúc đã đúng phạm vi?

Cloud JIT permission đạt mục tiêu khi quyền được gắn với một công việc cụ thể, chỉ có hiệu lực trong phạm vi đã duyệt và có đường kết thúc có thể kiểm chứng. Thời hạn ngắn là một phần của thiết kế; khả năng giới hạn thẩm quyền và đối soát quyền thực tế mới quyết định mức kiểm soát mà PAM cung cấp.
