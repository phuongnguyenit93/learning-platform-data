# Account disable

## 1. Vì sao cần audit việc vô hiệu hóa tài khoản?

**Account disable** là thay đổi trạng thái để một tài khoản không còn được sử dụng theo chính sách của hệ thống quản lý tài khoản đó. Thao tác này có thể xuất phát từ xử lý sự cố, thay đổi nhân sự, kết thúc hợp đồng hoặc một quyết định quản trị đã được phê duyệt.

Trong Logging và audit IAM, cần trả lời được nhiều hơn câu hỏi “tài khoản có đang DISABLED không”:

- Ai yêu cầu và ai thực hiện vô hiệu hóa?
- Tài khoản nào, thuộc miền danh tính hoặc ứng dụng nào, bị tác động?
- Quyết định có căn cứ và thẩm quyền gì?
- Trạng thái đã được ghi nhận thành công hay mới chỉ gửi yêu cầu?
- Các phiên, token, credential và ứng dụng phụ thuộc được xử lý tới đâu?
- Có đường truy cập nào tiếp tục chấp nhận tài khoản sau thời hạn thu hồi yêu cầu không?
- Tài khoản có được kích hoạt lại không, bởi ai và dựa trên quyết định nào?

Một dòng “user disabled” không đủ để trả lời các câu hỏi này. Audit cần mô tả đúng đối tượng, phạm vi, kết quả và giới hạn của bằng chứng.

## 2. Phân biệt disable với các thay đổi liên quan

| Thay đổi | Phạm vi và ý nghĩa |
|---|---|
| Disable account tại nguồn danh tính | Đổi trạng thái của tài khoản trong nguồn đó; tác động phụ thuộc nơi nào thực thi trạng thái |
| Khóa tạm do đăng nhập thất bại | Hạn chế theo cơ chế chống lạm dụng; không nhất thiết là quyết định quản trị vô hiệu hóa |
| Suspend membership | Ngừng sử dụng quan hệ của subject với một tenant |
| Gỡ role | Thu hồi một đường cấp quyền cụ thể |
| Thu hồi session hoặc token | Làm mất hiệu lực một phiên hoặc credential theo khả năng của cơ chế tương ứng |
| Delete account | Xử lý xóa tài khoản theo vòng đời dữ liệu; khác với giữ tài khoản ở trạng thái không hoạt động |
| Re-enable account | Một quyết định chuyển tài khoản trở lại trạng thái được phép theo chính sách |

Ví dụ, Lan thuộc tenant An và tenant Bình. Suspend membership của Lan trong tenant An không mặc nhiên cho phép khóa tài khoản toàn cục của Lan. Ngược lại, nếu tài khoản bị xác định đã bị chiếm đoạt, một quyết định disable tại miền danh tính chung có thể cần tác động rộng hơn việc gỡ một membership.

Một tài khoản ở nhà cung cấp danh tính bên ngoài cũng khác với tài khoản hoặc phiên cục bộ của ứng dụng. Vô hiệu hóa ở nguồn ngoài không tự chứng minh mọi phiên ứng dụng đã ngừng hoạt động.

Audit phải ghi rõ disable xảy ra ở đâu. Không dùng một event cục bộ để khẳng định trạng thái toàn bộ các hệ thống không nằm trong phạm vi quan sát.

## 3. Định danh tài khoản và các bên thực hiện

Một sự kiện account disable cần phân biệt actor với target.

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Actor | Ai thực hiện quyết định hoặc thao tác hiện tại? | Quản trị viên `u-009` |
| Caller workload | Phần mềm trực tiếp gửi yêu cầu | `svc-identity-operations` |
| Target account | Tài khoản bị vô hiệu hóa | `account-174` |
| Subject liên quan | Danh tính nội bộ mà tài khoản ánh xạ tới | `u-174` |
| Identity domain | Miền định danh của tài khoản | `workforce-main` |
| Requester | Ai khởi tạo yêu cầu nghiệp vụ? | Một bên được phép yêu cầu |
| Approver | Ai phê duyệt khi workflow yêu cầu? | Chủ thể có thẩm quyền |
| Source | Nguồn phát sinh thay đổi | Admin, provisioning, incident response |

Account ID nên ổn định và được diễn giải trong phạm vi nguồn tương ứng. Không dùng email hoặc username hiển thị làm khóa duy nhất để nối lịch sử vì chúng có thể thay đổi hoặc được tái sử dụng.

Nếu hệ thống liên kết nhiều tài khoản ngoài với cùng một subject, cần xác định chính xác tài khoản nào bị disable và quyết định có áp dụng ở mức subject hay không. Không suy ra phạm vi chỉ từ tên người dùng.

Actor và caller phải lấy từ ngữ cảnh đã được xác thực. Target do request đề xuất vẫn phải được máy chủ phân giải và kiểm tra quyền tác động; không ghi một `actor_id` tự khai như sự thật đáng tin cậy.

Nếu thay đổi được thực hiện bởi automation, ghi workload thực thi cùng reference tới yêu cầu hoặc quyết định nguồn. Không biến người phê duyệt thành caller cuối cùng nếu họ không trực tiếp thực hiện request đó.

## 4. Tách ý định, thay đổi trạng thái và hiệu lực truy cập

Một quy trình có thể gồm:

```text
Yêu cầu disable
        |
        v
Xác minh thẩm quyền và điều kiện
        |
        v
Commit trạng thái tài khoản DISABLED
        |
        v
Thu hồi phiên/credential và truyền trạng thái
        |
        v
Đối soát các điểm thực thi liên quan
```

Đây là những mốc khác nhau.

| Sự kiện minh họa | Bằng chứng nó cung cấp |
|---|---|
| account.disable_requested | Có yêu cầu; chưa chứng minh tài khoản đã bị khóa |
| account.disable_denied | Yêu cầu bị từ chối theo quy tắc hoặc phê duyệt |
| account.disabled | Nguồn quản lý tài khoản đã commit trạng thái bị vô hiệu hóa |
| session.revocation_requested | Đã yêu cầu thu hồi phiên, chưa chứng minh hoàn tất |
| session.revoked | Phiên được mô tả đã bị thu hồi theo cơ chế tương ứng |
| account.disable_propagation_completed | Tập đích đã định nghĩa đạt điều kiện truyền trạng thái |
| account.disable_apply_failed | Một lần áp dụng thất bại với kết quả xác định |
| account.reenabled | Tài khoản được kích hoạt lại bằng một thay đổi mới |

Tên và số lượng sự kiện tùy thiết kế. Mỗi loại cần có hợp đồng rõ về nguồn, phạm vi và điều kiện thành công.

Không ghi “all access revoked” chỉ vì cột trạng thái trong một bảng đã đổi. Cũng không ghi “disable failed” chỉ vì request timeout trong khi giao dịch tại nguồn có thể đã commit. Khi chưa rõ kết quả, cần trạng thái chưa xác định và bước đối soát theo operation ID.

Một event thành công về trạng thái tài khoản không phải bằng chứng rằng mọi dữ liệu hoặc tài nguyên của tài khoản đã bị xóa. Disable và xử lý dữ liệu là hai phần vòng đời cần được phân biệt.

## 5. Nội dung của một audit event

Các nhóm trường thường cần:

| Nhóm | Trường minh họa | Mục đích |
|---|---|---|
| Định danh sự kiện | event_id, event_type, schema_version | Phân biệt và diễn giải event |
| Nguồn | producer, environment, identity_domain | Xác định hệ thống và miền tác động |
| Thời gian | occurred_at, recorded_at | Phân biệt lúc thay đổi với lúc ghi nhận |
| Chủ thể | actor, caller, target_account_id, target_subject_id | Biết ai làm gì với tài khoản nào |
| Thay đổi | before, after, account_version | Mô tả trạng thái đã áp dụng |
| Căn cứ | reason_code, approval_id, case_reference | Nối với quyết định nghiệp vụ |
| Kết quả | outcome, failure_code | Phân biệt thành công, từ chối và lỗi |
| Tương quan | operation_id, request_id, causation_event_id | Nối các bước của cùng quy trình |
| Công việc tiếp theo | revocation_workflow_id hoặc reference tương ứng | Theo dõi phần thu hồi chưa hoàn tất |

Không nhất thiết đưa toàn bộ dữ liệu điều tra hoặc hồ sơ nhân sự vào event. Reason code và reference được bảo vệ thường đủ để tìm tới nguồn có thẩm quyền khi cần.

### Ví dụ

JSON sau là schema minh họa cho một thay đổi trạng thái tại nguồn tài khoản nội bộ.

```json
{
  "event_id": "evt-728",
  "schema_version": 1,
  "event_type": "account.disabled",
  "occurred_at": "2026-08-14T09:10:00Z",
  "recorded_at": "2026-08-14T09:10:01Z",
  "producer": "identity-service",
  "environment": "production",
  "identity_domain": "workforce-main",
  "actor": {
    "kind": "USER",
    "subject_id": "u-009"
  },
  "caller": {
    "kind": "WORKLOAD",
    "subject_id": "svc-identity-operations"
  },
  "target_account_id": "account-174",
  "target_subject_id": "u-174",
  "before": {
    "status": "ACTIVE"
  },
  "after": {
    "status": "DISABLED"
  },
  "account_version": 19,
  "reason_code": "APPROVED_SECURITY_ACTION",
  "case_reference": "case-302",
  "approval_id": "approval-661",
  "operation_id": "operation-884",
  "request_id": "req-992",
  "revocation_workflow_id": "revoke-508",
  "outcome": "SUCCEEDED"
}
```

Các ID và thời điểm là dữ liệu ví dụ. Event xác nhận phiên bản 19 của tài khoản tại nguồn được chỉ ra đã có trạng thái DISABLED. Reference `revoke-508` cho phép tìm phần việc thu hồi liên quan; nó không khẳng định workflow đó đã xong.

Nếu một request yêu cầu disable tài khoản đang DISABLED, hệ thống có thể ghi kết quả không có thay đổi theo hợp đồng idempotency. Không tạo một chuyển trạng thái ACTIVE sang DISABLED giả để làm log trông đồng nhất.

## 6. Bằng chứng trạng thái phải khớp giao dịch thật

### 6.1. ALLOW không đồng nghĩa đã disable

Một request được phép vô hiệu hóa tài khoản có thể thất bại khi ghi dữ liệu. Cần phân biệt:

```text
quyết định phân quyền: ALLOW
thao tác đổi trạng thái: FAILED hoặc chưa xác định
```

Log thành công chỉ được phát theo điều kiện thành công đã định nghĩa. Payload do client yêu cầu không phải trạng thái cuối cùng.

### 6.2. Ghi cùng giao dịch bằng outbox

Nếu trạng thái tài khoản nằm trong cơ sở dữ liệu có giao dịch, có thể ghi trạng thái và event outbox trong cùng giao dịch:

```text
begin transaction

    kiểm tra thẩm quyền và trạng thái hiện tại
    cập nhật tài khoản sang DISABLED
    tăng phiên bản trạng thái phù hợp
    ghi event account.disabled vào outbox

commit

publisher chuyển event sang pipeline audit
workflow tiếp tục thu hồi theo kế hoạch
```

Khi giao dịch rollback, không được có event thành công khẳng định thay đổi đã được commit.

Outbox giúp liên kết bằng chứng với thay đổi trong cùng ranh giới giao dịch. Nó không làm việc thu hồi tại mọi hệ thống bên ngoài trở thành một giao dịch duy nhất, cũng không tự ngăn event bị phát lặp.

### 6.3. Khi log hoặc thành phần phụ thuộc lỗi

Thiết kế cần xác định bằng chứng nào phải được lưu bền vững trước khi xác nhận thao tác.

Collector tạm ngừng có thể được xử lý bằng outbox bền vững và cơ chế tiếp tục phát. Nếu chỉ ghi vào bộ nhớ rồi tiến trình chết, thông báo “đã ghi log” chưa phải bảo đảm lưu được bằng chứng.

Với disable khẩn cấp, cần tránh để một nơi nhận log lỗi làm mất khả năng ngăn truy cập nguy hiểm ngoài ý muốn. Phương án dự phòng phải được thiết kế trước, có bằng chứng bền vững thích hợp và có đối soát; không bỏ audit âm thầm hoặc để exception tùy ý quyết định việc khóa tài khoản.

## 7. Phiên, token và credential sau khi disable

Vô hiệu hóa tài khoản thường cần được nối với các phần việc khác:

| Thành phần | Điều cần làm rõ | Bằng chứng nên có |
|---|---|---|
| Đăng nhập mới | Nguồn nào sẽ từ chối xác thực tài khoản? | Thay đổi trạng thái tại nguồn và kết quả kiểm tra phù hợp |
| Phiên ứng dụng | Phiên nào thuộc phạm vi phải thu hồi? | Session ID nội bộ và kết quả thu hồi |
| Access token | API phát hiện trạng thái disable bằng cơ chế nào? | Phiên bản hoặc cơ chế thu hồi, log quyết định liên quan |
| Refresh token | Có ngăn phát hành token mới không? | Kết quả thu hồi hoặc từ chối theo chính sách |
| API key cá nhân | Key nào phụ thuộc tài khoản? | Định danh key, phạm vi và kết quả xử lý |
| Kết nối dài | Khi nào stream hoặc subscription ngừng? | Kết quả đóng hoặc đánh giá lại theo thiết kế |
| Job theo ủy quyền người dùng | Quyền chạy còn hiệu lực không? | Trạng thái grant và xử lý tác vụ |
| Workload tổ chức | Có thực sự thuộc vòng đời tài khoản không? | Quyết định riêng theo chủ sở hữu và grant |

Một access token tự chứa có thể vẫn kiểm tra được chữ ký và thời hạn sau khi tài khoản đã bị disable. Để ngăn nó được dùng theo yêu cầu thu hồi, API cần cơ chế phù hợp như kiểm tra trạng thái, phiên bản hoặc danh sách thu hồi theo thiết kế. Chỉ vô hiệu hóa refresh token không chứng minh token đang có đã hết tác dụng.

Audit cần mô tả độ trễ chấp nhận được và kết quả quan sát. Nếu hệ thống chấp nhận một khoảng truyền trạng thái, không thể đồng thời tuyên bố mọi điểm truy cập đã chặn tức thời.

Không tự xóa hoặc thu hồi mọi workload mà user từng tạo. Một service account thuộc tổ chức có thể có vòng đời riêng. Cần xác định chủ sở hữu vận hành, grant và nhu cầu chuyển giao; người tạo ban đầu không nhất thiết là căn cứ duy nhất để quyết định.

Credential dùng chung với nhiều chủ thể cũng cần được xử lý theo tác động thực tế. Không dùng một event disable user làm căn cứ để tuyên bố một secret chung đã được thu hồi an toàn mà chưa xét các bên phụ thuộc.

## 8. Truyền trạng thái qua nhiều hệ thống

Một tổ chức có thể có nguồn danh tính, ứng dụng nội bộ, ứng dụng bên ngoài và các connector provisioning. Mỗi thành phần có trạng thái và độ trễ riêng.

Cần phân biệt:

```text
nguồn đã commit DISABLED
        |
        v
connector nhận thay đổi
        |
        v
ứng dụng đích xác nhận tiếp nhận
        |
        v
ứng dụng đích áp dụng trạng thái
        |
        v
đối soát điều kiện truy cập tại đích
```

HTTP thành công có thể chỉ có nghĩa yêu cầu được tiếp nhận vào hàng đợi. Một event hoàn tất truyền trạng thái phải tham chiếu tập đích và tiêu chí cụ thể mà nó xác nhận.

Mỗi đích có thể được theo dõi bằng:

- Target system ID.
- Operation ID.
- Phiên bản hoặc mốc nguồn đã xử lý.
- Trạng thái PENDING, SUCCEEDED, FAILED hoặc chưa xác định theo schema.
- Số lần thử.
- Thời điểm áp dụng hoặc thời điểm đối soát.
- Mã lỗi không chứa secret.

Không sử dụng absence of logs như bằng chứng chắc chắn ứng dụng đích không còn cho truy cập. Nguồn log có thể chưa được bật, đang chậm hoặc không bao phủ một đường truy cập.

### Chống cập nhật cũ làm đảo trạng thái

Sau event disable, một bản đồng bộ cũ có thể gửi trạng thái ACTIVE. Connector cần quy tắc về phiên bản, nguồn có thẩm quyền và thay đổi được phép, thay vì áp dụng bản đến sau cùng một cách mù quáng.

Audit cần ghi được cập nhật bị bỏ qua vì cũ hoặc bị từ chối theo chính sách. Một event re-enable hợp lệ phải phản ánh một quyết định mới, không chỉ là kết quả replay dữ liệu cũ.

## 9. Retry, cạnh tranh và kích hoạt lại

### 9.1. Idempotency

Hai lần gửi cùng một yêu cầu disable không nên tạo hai chuyển trạng thái giả hoặc hai workflow không kiểm soát.

Có thể dùng operation ID để đối soát một yêu cầu, event ID để nhận biết event logic và account version để nhận biết thay đổi trạng thái. Không dùng chúng thay thế nhau khi ý nghĩa khác nhau.

Một publisher phát lại cùng event không nên làm hệ thống cảnh báo hiểu là tài khoản bị disable nhiều lần độc lập. Nếu giữ thông tin vận chuyển, cần phân biệt lần phát với thay đổi nghiệp vụ.

### 9.2. Disable và re-enable đồng thời

Hai actor có thể gửi thay đổi ngược nhau gần cùng thời điểm. Cần có cơ chế nhất quán như kiểm tra phiên bản, giao dịch hoặc quy trình quyết định phù hợp.

Audit nên ghi trạng thái trước và sau thực sự được commit. Nếu một request thất bại do version conflict, không ghi nó thành một thay đổi thành công.

Timestamp trên nhiều máy không tự tạo thứ tự tuyệt đối. Khi tái dựng vòng đời, cần xem account version, nguồn và quan hệ nhân quả, đồng thời ghi nhận sai lệch thời gian khi có.

### 9.3. Re-enable là một quyết định riêng

Kích hoạt lại tài khoản cần căn cứ và thẩm quyền mới. Không xóa event disable hoặc sửa event cũ thành ACTIVE.

Re-enable account cũng không mặc nhiên khôi phục mọi role, credential, phiên và ủy quyền đã bị thu hồi. Cần workflow riêng cho những thành phần cần phục hồi và audit kết quả của chúng.

Nếu username hoặc email được gán cho một người mới, lịch sử không được nhập nhằng với tài khoản cũ. Định danh ổn định và quy tắc vòng đời giúp tránh kết luận người mới từng thực hiện các hành động của tài khoản trước.

## 10. Dùng audit để kiểm tra hiệu lực và điều tra

Một câu hỏi thường gặp: “Tài khoản bị disable lúc 09:10, vì sao còn có request thành công lúc 09:12?”

Cần kiểm tra:

1. Event 09:10 xác nhận trạng thái ở nguồn nào?
2. Request 09:12 dùng loại credential, session và đường truy cập nào?
3. Quyết định truy cập sử dụng account version hoặc snapshot nào?
4. Trạng thái disable đã được truyền tới điểm thực thi chưa?
5. Độ trễ đó có nằm trong giới hạn đã định nghĩa không?
6. Request đã bắt đầu hoặc được chấp nhận trước mốc nào?
7. Log đang dùng thời điểm xảy ra hay thời điểm thu nhận?

Một request đã vào giai đoạn thực hiện trước mốc chặn có thể cần cách xử lý khác với request mới sau mốc chặn. Chính sách đối với công việc đang chạy phải được xác định trước; không kết luận chỉ từ việc hai timestamp nằm gần nhau.

Log quyết định có thể ghi lý do `ACCOUNT_DISABLED`, subject, account ID, tenant nếu có, phiên bản trạng thái và mã tương quan. Không cần ghi token nguyên vẹn để nối sự kiện.

Một request bị từ chối chứng minh đường đó đã từ chối request đó. Nó không chứng minh mọi API, kết nối dài và job đều đã áp dụng cùng kết quả.

Khi tái dựng lịch sử, cần giữ các khoảng thời gian DISABLED và ACTIVE riêng, thay vì chỉ đọc trạng thái hiện tại. Tài khoản đang ACTIVE hôm nay không phủ nhận việc nó đã bị vô hiệu hóa trong một giai đoạn trước.

## 11. Phát hiện bất thường và bảo vệ bằng chứng

Những tín hiệu có thể cần điều tra:

| Dấu hiệu | Câu hỏi cần làm rõ |
|---|---|
| Tài khoản đặc quyền được re-enable nhanh sau disable | Ai phê duyệt và mục đích có hợp lệ không? |
| Nhiều tài khoản bị disable ngoài kế hoạch | Thay đổi tập thể hợp lệ, lỗi automation hay hành vi bất thường? |
| Actor tự vô hiệu hóa hoặc thay đổi tài khoản nhạy cảm | Actor có thẩm quyền và workflow tương ứng không? |
| Đích vẫn chấp nhận credential sau hạn thu hồi | Có khoảng trống truyền trạng thái hoặc enforcement không? |
| Yêu cầu disable bị từ chối lặp lại | Lỗi cấu hình quyền hay cố gắng tác động ngoài phạm vi? |
| Tài khoản tự ACTIVE sau đồng bộ | Có dữ liệu cũ hoặc nguồn cấp quyền xung đột không? |
| Event trạng thái thiếu bằng chứng kết quả | Pipeline bị lỗi hay có đường thay đổi ngoài luồng? |
| Thay đổi IAM đồng thời với việc tắt log | Có nguy cơ mất bằng chứng cần xử lý không? |

Dấu hiệu không tự chứng minh có tấn công. Cần context về lịch vận hành, thay đổi được phê duyệt và chất lượng dữ liệu nguồn.

Kho audit cần giới hạn quyền ghi, đọc, xuất và xóa. Người quản trị tài khoản không nên mặc nhiên có khả năng sửa bằng chứng về chính thao tác của mình.

Có thể dùng lưu trữ hạn chế sửa và cơ chế phát hiện thay đổi, nhưng điều đó không tự làm nội dung do producer phát ra trở thành đúng. Vẫn cần xác thực nguồn, bảo vệ pipeline và đối soát.

### Dữ liệu cần hạn chế

Không ghi:

- Mật khẩu hoặc câu trả lời khôi phục.
- Access token, refresh token hoặc cookie.
- Secret của API key hoặc workload.
- Toàn bộ nội dung hồ sơ nhân sự hoặc điều tra nếu không cần cho mục đích audit.
- Payload không kiểm soát có thể chứa credential.

Dùng reason code và reference để nối tới thông tin chi tiết được phân quyền riêng. Các trường tự do cần được giới hạn kích thước và hiển thị an toàn để tránh làm sai cấu trúc log.

Sự kiện đăng nhập bị từ chối vì account disabled cũng cần bảo vệ thông tin khi phản hồi ra ngoài. Log nội bộ phục vụ điều tra có thể chi tiết hơn thông báo cho caller; không cần tiết lộ trạng thái tài khoản cho mọi bên chỉ để có audit.

## 12. Ví dụ xuyên suốt và các kiểm tra cần có

Giả sử tài khoản Lan cần bị disable theo một quyết định đã được phê duyệt:

1. Hệ thống xác minh actor có quyền tác động tới tài khoản đúng miền.
2. Nguồn tài khoản commit trạng thái DISABLED cùng event bền vững.
3. Workflow thu hồi xác định phiên, credential và đích ứng dụng thuộc phạm vi.
4. Mỗi bước ghi kết quả rõ ràng và retry có kiểm soát khi cần.
5. Các điểm thực thi từ chối request theo cơ chế trạng thái và giới hạn thu hồi đã thiết kế.
6. Hệ thống đối soát phần đã xong, phần lỗi và phần chưa xác định.
7. Nếu sau đó re-enable, một quyết định và sự kiện mới được tạo; quyền cũ không được tự phục hồi ngoài workflow.

Những tình huống cần kiểm chứng:

| Tình huống | Bằng chứng mong đợi |
|---|---|
| Actor không có thẩm quyền | Yêu cầu bị từ chối; không có event disable thành công |
| Giao dịch cập nhật rollback | Không ghi DISABLED thành công cho thay đổi không được commit |
| Request timeout nhưng commit đã xảy ra | Đối soát được theo operation ID |
| Collector tạm ngừng sau commit outbox | Event còn bền vững và được chuyển tiếp khi phục hồi |
| Cùng yêu cầu bị gửi lại | Không tạo chuyển trạng thái hoặc workflow trùng ngoài thiết kế |
| Một đích provisioning không áp dụng | Trạng thái partial hoặc lỗi được thể hiện, không tuyên bố tất cả hoàn tất |
| Token còn hạn được gọi sau disable | Kết quả phản ánh cơ chế thu hồi và độ trễ đã định nghĩa |
| Một connection dài còn hoạt động | Có xử lý theo chính sách đánh giá lại hoặc đóng kết nối |
| Bản đồng bộ ACTIVE cũ tới muộn | Không ghi đè trạng thái mới trái quy tắc nguồn và phiên bản |
| Re-enable hợp lệ | Event mới ghi actor, căn cứ và trạng thái trước/sau |
| Email của tài khoản cũ được tái sử dụng | Lịch sử vẫn phân biệt đúng định danh |
| Có khoảng trống log hoặc đích chưa đối soát | Báo giới hạn bằng chứng thay vì khẳng định không còn truy cập |

Audit account disable đáng tin cậy tách được quyết định vô hiệu hóa, thay đổi trạng thái và hiệu lực thực thi trên các đường truy cập. Khi các sự kiện này được nối bằng định danh ổn định, phiên bản, operation ID và kết quả đối soát, hệ thống có thể giải thích rõ ai đã khóa tài khoản nào, ở đâu, khi nào và khả năng truy cập đã bị thu hồi tới mức nào.
