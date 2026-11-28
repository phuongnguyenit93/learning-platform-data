# Log cấp quyền

Trong quản lý truy cập đặc quyền (PAM), một bản ghi “đã cấp quyền thành công” chưa đủ để giải thích ai được phép làm gì, trên tài nguyên nào, trong bao lâu và dựa trên quyết định nào. Nó cũng chưa chứng minh quyền đã thực sự có hiệu lực trên hệ thống đích. Log cấp quyền phải nối được quyết định quản trị với thay đổi quyền thực tế và với thời điểm quyền hết hiệu lực.

Ví dụ: một kỹ sư được phê duyệt quyền quản trị máy chủ sản xuất trong 20 phút để xử lý sự cố. Hệ thống PAM ghi nhận phê duyệt, nhưng connector cấu hình sai nên thêm kỹ sư vào nhóm quản trị thường trực. Nếu chỉ giữ log phê duyệt, người kiểm tra sẽ thấy một yêu cầu JIT hợp lệ, trong khi quyền còn tồn tại sau khi cửa sổ xử lý sự cố kết thúc.

Bài học này trình bày cách thiết kế và sử dụng log cấp quyền cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Mục tiêu là tạo bằng chứng có thể đối chiếu khi kiểm toán hoặc ứng phó sự cố, đồng thời hỗ trợ phát hiện quyền thừa và lỗi thu hồi.

## 1. Cần trả lời được những câu hỏi nào?

Một chuỗi log cấp quyền có ích cần trả lời được ít nhất các câu hỏi sau:

- Ai khởi tạo yêu cầu? Đây là người dùng, tài khoản dịch vụ hay một tiến trình tự động?
- Quyền được cấp cho chủ thể nào? Chủ thể đó có khác người yêu cầu không?
- Quyền cụ thể là gì, trên tài nguyên nào, thuộc môi trường và miền quản trị nào?
- Ai hoặc chính sách nào cho phép cấp quyền? Quyết định sử dụng phiên bản chính sách nào?
- Thời điểm được phê duyệt, thời điểm hệ thống đích áp dụng và thời điểm xác minh có trùng nhau không?
- Quyền dự kiến kết thúc khi nào? Hệ thống đã thu hồi và kiểm tra kết quả chưa?
- Có đường cấp quyền trực tiếp ngoài PAM, lỗi đồng bộ hoặc dữ liệu audit bị thiếu không?

Log cấp quyền phục vụ hai lớp bằng chứng liên quan nhưng khác nhau:

1. **Bằng chứng quyết định:** yêu cầu, phê duyệt, từ chối, ngoại lệ và điều kiện kèm theo.
2. **Bằng chứng thực thi:** tác vụ thay đổi quyền, phản hồi của hệ thống đích và kết quả kiểm tra trạng thái quyền.

Khi điều tra một quyền quản trị xuất hiện bất thường, phải xem cả hai lớp. Một yêu cầu hợp lệ không bảo đảm việc thực thi đúng; một thay đổi quyền thực tế không chứng minh nó được phê duyệt.

## 2. Phân biệt cấp quyền với các sự kiện gần giống

Trong PAM, nhiều sự kiện có thể cùng xuất hiện nhưng không đồng nghĩa với nhau.

| Sự kiện | Ý nghĩa | Điều không thể suy ra chỉ từ sự kiện đó |
|---|---|---|
| Đăng nhập thành công | Một danh tính đã xác thực với một hệ thống | Danh tính được cấp quyền quản trị hợp lệ |
| Yêu cầu quyền | Chủ thể đề nghị một phạm vi truy cập | Yêu cầu đã được phê duyệt |
| Phê duyệt | Người hoặc chính sách chấp thuận điều kiện truy cập | Hệ thống đích đã thay đổi quyền |
| Thiết lập điều kiện được kích hoạt quyền | Chủ thể đủ điều kiện xin kích hoạt một vai trò | Vai trò đang có hiệu lực |
| Áp dụng quyền | Connector hoặc hệ thống đích ghi nhận thay đổi | Mọi cơ chế ủy quyền đã cập nhật đồng bộ |
| Xác minh quyền | Một phép kiểm tra quan sát trạng thái quyền tại thời điểm xác định | Mọi phiên, token hoặc đường truy cập khác đều bị ràng buộc giống nhau |
| Mở phiên đặc quyền | Phiên truy cập được khởi tạo | Mọi thao tác trong phiên đều được phép |
| Checkout credential | Một credential được giao hoặc cho phép sử dụng | Chủ thể đã thực hiện thao tác quản trị trên tài nguyên |
| Thu hồi quyền | Hệ thống thực hiện yêu cầu loại bỏ quyền | Token hoặc phiên đã tồn tại chắc chắn mất hiệu lực ngay |
| Hết hạn theo lịch | Cửa sổ quyền đã kết thúc theo kế hoạch | Hệ thống đích đã thực sự loại bỏ quyền |

Trong JIT, cần log riêng việc kích hoạt một quyền theo thời gian với việc thiết lập quyền đủ điều kiện kích hoạt. Trong JEA, phạm vi cần thể hiện được các thao tác được phép hoặc một tham chiếu ổn định tới tập thao tác đó, thay vì chỉ ghi nhãn chung “admin”.

Nếu một người dùng có sẵn quyền từ nhóm khác, thu hồi grant JIT không đồng nghĩa người đó mất toàn bộ quyền quản trị. Log phải mô tả grant nào bị thu hồi, còn việc đánh giá quyền hiệu lực phải xét các nguồn quyền còn lại.

## 3. Những đường cấp quyền phải quan sát

Một mô hình audit chỉ theo dõi giao diện PAM sẽ bỏ sót những thay đổi xảy ra trực tiếp trên hệ thống đích.

Các đường thường cần đưa vào phạm vi quan sát gồm:

- Cấp quyền quản trị cho người dùng qua workflow PAM.
- Gán vai trò cho tài khoản dịch vụ, workload hoặc tác vụ tự động.
- Thêm thành viên vào nhóm quản trị, kể cả qua nhóm lồng nhau nếu môi trường sử dụng.
- Sửa policy, role binding hoặc tập lệnh được phép thực thi.
- Cấp quyền truy cập vault, quyền checkout hoặc quyền sử dụng một secret.
- Kích hoạt quyền JIT, gia hạn cửa sổ truy cập và thay đổi điều kiện JEA.
- Sử dụng quyền khẩn cấp theo cơ chế break-glass.
- Cấp quyền trực tiếp bằng công cụ quản trị của hệ thống đích.
- Thu hồi, hết hạn, rollback, thất bại và xác minh sau thay đổi.

Đây là một bài toán bao phủ, không chỉ là thêm trường vào JSON. Cần xác định mỗi loại thay đổi có nguồn log nào, chủ sở hữu nguồn đó là ai và cách phát hiện khi nguồn ngừng gửi dữ liệu.

Đối với đường cấp quyền ngoài PAM, log hệ thống đích có thể không chứa `request_id` của PAM. Không được tự tạo một liên kết giả để làm chuỗi sự kiện có vẻ đầy đủ. Hãy ghi nhận thay đổi là chưa tìm thấy yêu cầu tương ứng, rồi đối chiếu với các quy trình quản trị hợp lệ khác.

## 4. Mô hình hóa vòng đời của một lần cấp quyền

Có thể thiết kế một bộ tên sự kiện nội bộ như sau. Đây là quy ước minh họa, không phải tên trường hoặc sự kiện bắt buộc của một sản phẩm.

| Sự kiện minh họa | Điều kiện ghi nhận | Thông tin quan trọng |
|---|---|---|
| `privilege.requested` | Tiếp nhận yêu cầu | Người yêu cầu, chủ thể nhận quyền, phạm vi, lý do, thời lượng |
| `privilege.approved` | Có quyết định chấp thuận | Người duyệt hoặc policy, điều kiện, thời lượng được duyệt |
| `privilege.denied` | Có quyết định từ chối | Lý do đã chuẩn hóa, tham chiếu quyết định |
| `privilege.apply_requested` | Giao tác vụ thực thi | Grant, connector, hệ thống đích, lần thử |
| `privilege.grant_applied` | Có bằng chứng thay đổi đã được áp dụng | Định danh thay đổi trên đích, phạm vi thực tế |
| `privilege.grant_verified` | Kiểm tra sau cấp quyền đạt yêu cầu | Phương pháp kiểm tra, thời điểm quan sát, kết quả |
| `privilege.apply_failed` | Thực thi không thành công hoặc chưa xác định được kết quả | Loại lỗi, trạng thái đã biết, hướng đối soát |
| `privilege.revoke_requested` | Yêu cầu thu hồi hoặc hết hạn kích hoạt thu hồi | Lý do, grant gốc, người hoặc scheduler khởi tạo |
| `privilege.grant_revoked` | Có bằng chứng hệ thống đích loại bỏ grant | Tham chiếu thao tác thu hồi trên đích |
| `privilege.revoke_verified` | Kiểm tra sau thu hồi đạt yêu cầu | Trạng thái quan sát, phạm vi kiểm tra, giới hạn |
| `privilege.revoke_failed` | Thu hồi thất bại hoặc kết quả chưa xác định | Lỗi, tuổi của quyền quá hạn, đường xử lý |
| `privilege.extended` | Thời hạn được thay đổi có kiểm soát | Hạn cũ, hạn mới, quyết định và phê duyệt mới |

Không phải workflow nào cũng phát ra mọi loại sự kiện. Chẳng hạn, một yêu cầu bị từ chối sẽ không có grant đã áp dụng. Tuy nhiên, các sự kiện phải có nghĩa rõ ràng, nhất quán với điều hệ thống thực sự biết.

Một đường thành công có thể là:

```text
requested
   -> approved
   -> apply_requested
   -> grant_applied
   -> grant_verified
   -> revoke_requested
   -> grant_revoked
   -> revoke_verified
```

Nếu connector gửi yêu cầu rồi timeout, không được lập tức kết luận quyền chưa tồn tại. Hệ thống đích có thể đã áp dụng thay đổi nhưng phản hồi bị mất. Trường hợp này cần thể hiện trạng thái kết quả chưa xác định và đối soát trước khi retry hoặc báo thành công.

Tương tự, `grant_verified` nên được hiểu là “phép kiểm tra được mô tả đã đạt tại thời điểm quan sát”, không phải lời khẳng định tuyệt đối về mọi đường truy cập.

## 5. Thiết kế các định danh để nối chuỗi bằng chứng

Một chuỗi log dễ điều tra cần nhiều định danh có vai trò khác nhau.

| Định danh | Vai trò | Lưu ý |
|---|---|---|
| `event_id` | Nhận diện một sự kiện logic | Giữ nguyên khi phát lại chính sự kiện đó |
| `request_id` | Nối các bước của một yêu cầu | Một yêu cầu có thể tạo nhiều grant |
| `grant_id` | Nhận diện một lần cấp quyền cụ thể | Không tái sử dụng cho lần cấp quyền mới |
| `decision_id` | Trỏ tới quyết định cho phép hoặc từ chối | Có thể kèm tham chiếu phê duyệt |
| `operation_id` | Nhận diện tác vụ thực thi | Retry cùng tác vụ cần theo dõi được |
| `attempt_id` | Phân biệt từng lần thử | Một operation có thể có nhiều attempt |
| `target_change_id` | Đối chiếu với thay đổi trên hệ thống đích | Có thể không được nguồn đích cung cấp |
| `session_id` | Nối với phiên sử dụng quyền | Không thay thế `grant_id` |
| `trace_id` | Theo dõi xử lý qua các thành phần | Không dùng làm bằng chứng phê duyệt duy nhất |

Một request cấp quyền cho ba máy chủ nên có ba grant hoặc một cấu trúc phạm vi tương đương đủ rõ để xác minh từng đích. Không nên nén toàn bộ thành “cấp quyền hệ thống sản xuất thành công” khi thực tế một máy thành công, một máy thất bại và một máy chưa phản hồi.

Cần phân biệt các vai trò danh tính:

- `actor`: tác nhân gây ra sự kiện đang được ghi.
- `requester`: danh tính gửi yêu cầu ban đầu.
- `subject`: danh tính hoặc workload nhận quyền.
- `approver`: người hoặc cơ chế phê duyệt.
- `executor`: thành phần thực hiện thay đổi trên hệ thống đích.

Trong một sự kiện áp dụng quyền, actor có thể là connector, còn subject là người kỹ sư. Nếu chỉ lưu một trường `user`, quá trình điều tra rất dễ nhầm connector là người nhận quyền hoặc nhầm người yêu cầu là người duyệt.

Dùng định danh nội bộ ổn định cùng miền danh tính, tenant hoặc nguồn phát hành phù hợp. Tên hiển thị và email có thể hỗ trợ đọc log nhưng không nên là khóa duy nhất, vì chúng có thể đổi hoặc bị tái sử dụng.

## 6. Bộ dữ liệu tối thiểu cho log cấp quyền

Một schema tốt nên đủ rõ để truy vấn mà không buộc người điều tra phân tích chuỗi văn bản tự do.

### 6.1. Thông tin sự kiện và nguồn

- Phiên bản schema, loại sự kiện và định danh sự kiện.
- Thời điểm xảy ra tại nguồn, thời điểm thu nhận tại hệ thống log.
- Nguồn phát, instance, miền quản trị và môi trường.
- Kết quả của hành động: thành công, thất bại hoặc chưa xác định.
- Mã lý do có cấu trúc; thông báo mô tả chỉ giữ dữ liệu phù hợp.
- Số thứ tự hoặc phiên bản trạng thái trong phạm vi grant, nếu nguồn hỗ trợ.

Nên dùng thời gian có múi giờ rõ ràng, ví dụ UTC biểu diễn bằng hậu tố `Z`. Phân biệt thời gian phát sinh với thời gian thu nhận để nhận biết sự kiện đến muộn.

Không sắp xếp mọi sự kiện chỉ dựa vào đồng hồ của các máy khác nhau. Kết hợp thời gian với quan hệ nguyên nhân, ID tác vụ và phiên bản trạng thái. Khi có độ lệch đồng hồ, lưu hoặc theo dõi dấu hiệu đó để tránh kết luận sai thứ tự.

### 6.2. Phạm vi quyền

- Chủ thể nhận quyền và miền danh tính.
- Tài nguyên đích cùng định danh ổn định.
- Vai trò, nhóm, binding hoặc tập thao tác được cấp.
- Điều kiện giới hạn: môi trường, nguồn truy cập, phiên hoặc phạm vi tài nguyên.
- Thời điểm bắt đầu và kết thúc đã được duyệt.
- Thời điểm áp dụng thực tế và thời điểm xác minh.
- Trạng thái trước và sau hoặc tham chiếu tới snapshot có thể truy xuất.

Nếu vai trò có thể thay đổi nội dung, chỉ ghi `role=operator` là chưa đủ. Cần lưu phiên bản vai trò hoặc tham chiếu tới bản định nghĩa bất biến để về sau biết “operator” tại thời điểm đó gồm những quyền nào.

Với nhóm lồng nhau hoặc policy có điều kiện, bản ghi nên thể hiện nguồn gốc quyền đủ để phân biệt cấp trực tiếp với quyền kế thừa. Không gắn nhãn “least privilege đã bảo đảm” chỉ vì tên vai trò nghe có vẻ hạn chế.

### 6.3. Căn cứ và trách nhiệm

- Lý do yêu cầu đã được kiểm soát dữ liệu nhạy cảm.
- Tham chiếu ticket, sự cố hoặc yêu cầu thay đổi.
- Policy và phiên bản policy được đánh giá.
- Quyết định, người duyệt và thời điểm duyệt, nếu có.
- Tham chiếu tới bằng chứng xác thực tăng cường khi workflow yêu cầu.
- Dấu hiệu break-glass hoặc ngoại lệ, cùng hạn và người chịu trách nhiệm.

Tham chiếu tới bằng chứng xác thực không có nghĩa là ghi mật khẩu, OTP hoặc token vào log. Với phê duyệt tự động, cần nhận diện chính sách hoặc engine đã quyết định, thay vì điền một người duyệt giả.

### 6.4. Bằng chứng thực thi và thu hồi

- Connector, operation, attempt và định danh thay đổi trên đích.
- Phạm vi thực tế đã áp dụng, kể cả kết quả từng tài nguyên.
- Lỗi thực thi, timeout và trạng thái chưa xác định.
- Phương pháp xác minh cùng thời điểm quan sát.
- Thời hạn dự kiến, lý do thu hồi và kết quả thu hồi.
- Tham chiếu tới xử lý phiên hoặc token nếu cần để quyền hết hiệu lực.

Thông tin “trước/sau” phải có nghĩa chính xác. Nếu connector chỉ biết nó đã thêm một thành viên nhóm, không nên ghi snapshot toàn bộ quyền hiệu lực như thể đã tính đủ mọi policy liên quan.

## 7. Ví dụ một sự kiện áp dụng quyền

Ví dụ sau dùng schema minh họa của một hệ thống nội bộ. Các giá trị đều giả lập và không chứa credential.

```json
{
  "schema_version": "1.0",
  "event_id": "evt-7f02",
  "event_type": "privilege.grant_applied",
  "occurred_at": "2026-06-15T09:00:08Z",
  "ingested_at": "2026-06-15T09:00:09Z",
  "source": {
    "system": "pam-control",
    "instance_id": "connector-prod-02",
    "environment": "production"
  },
  "actor": {
    "type": "service",
    "id": "svc-pam-connector",
    "identity_domain": "operations"
  },
  "requester": {
    "type": "human",
    "id": "user-1042",
    "identity_domain": "workforce"
  },
  "subject": {
    "type": "human",
    "id": "user-1042",
    "identity_domain": "workforce"
  },
  "request_id": "req-184",
  "grant_id": "grant-184-a",
  "decision": {
    "id": "decision-901",
    "approval_ref": "approval-901",
    "policy_id": "prod-maintenance-jit",
    "policy_version": "12"
  },
  "target": {
    "id": "host-prod-17",
    "type": "server",
    "administrative_domain": "payments"
  },
  "privilege": {
    "role_id": "maintenance-limited",
    "role_version": "4",
    "definition_ref": "role-snapshot-184-a",
    "assignment_type": "temporary"
  },
  "validity": {
    "approved_from": "2026-06-15T09:00:00Z",
    "approved_until": "2026-06-15T09:20:00Z"
  },
  "execution": {
    "operation_id": "op-184-apply",
    "attempt_id": "attempt-1",
    "target_change_id": "change-7612",
    "before": "binding_absent",
    "after": "binding_present"
  },
  "reason_code": "INCIDENT_MAINTENANCE",
  "ticket_ref": "INC-DEMO-184",
  "outcome": "success",
  "verification_state": "pending"
}
```

Các điểm đáng chú ý:

- Actor là connector, subject là kỹ sư nhận quyền.
- `approved_until` là giới hạn được duyệt, không phải bằng chứng quyền chắc chắn biến mất lúc đó.
- Kết quả thành công thuộc hành động áp dụng binding; trường xác minh vẫn là `pending`.
- Vai trò có phiên bản và tham chiếu định nghĩa để tránh diễn giải theo cấu hình hiện tại.
- Ticket, approval và snapshot phải tồn tại trong kho bằng chứng được kiểm soát truy cập. Một ID trỏ tới tài liệu đã mất không tạo được khả năng giải trình.

Sau sự kiện này, một sự kiện `privilege.grant_verified` cần mô tả phép kiểm tra sau áp dụng. Ví dụ, hệ thống đọc lại binding trên máy chủ và xác nhận đúng chủ thể, đúng vai trò, đúng hạn. Nếu phạm vi kiểm tra chỉ là binding, nội dung log phải nói rõ như vậy.

Không sửa sự kiện cũ từ `verification_state=pending` thành `passed` rồi xóa dấu vết trước đó. Có thể cập nhật bảng trạng thái vận hành để phục vụ giao diện, nhưng chuỗi audit cần giữ sự kiện xác minh tiếp theo.

## 8. Ví dụ đối chiếu toàn bộ một lần cấp quyền

Giả sử yêu cầu `req-184` được duyệt cho cửa sổ 09:00–09:20 UTC.

| Thời điểm UTC | Sự kiện | Nhận định có thể rút ra |
|---|---|---|
| 08:58:30 | `privilege.requested` | Kỹ sư đề nghị một quyền có thời hạn |
| 08:59:10 | `privilege.approved` | Yêu cầu được chấp thuận theo policy phiên bản 12 |
| 09:00:02 | `privilege.apply_requested` | Connector bắt đầu thực thi |
| 09:00:08 | `privilege.grant_applied` | Binding được ghi nhận đã thêm trên đích |
| 09:00:11 | `privilege.grant_verified` | Phép kiểm tra binding đạt yêu cầu |
| 09:20:00 | `privilege.revoke_requested` | Scheduler khởi tạo thu hồi khi hết hạn |
| 09:20:03 | `privilege.grant_revoked` | Binding được ghi nhận đã xóa |
| 09:20:06 | `privilege.revoke_verified` | Phép kiểm tra sau thu hồi đạt yêu cầu |

Chuỗi này vẫn cần được diễn giải theo cơ chế ủy quyền của hệ thống đích. Nếu một phiên hoặc token đã phát hành giữ quyền độc lập với binding, cần có bằng chứng xử lý hoặc giới hạn hiệu lực của phiên/token đó. Không nên coi thời điểm xóa binding là thời điểm mọi khả năng truy cập đã chấm dứt nếu kiến trúc không bảo đảm điều này.

Nếu sự kiện cuối không xuất hiện, kết luận phù hợp là “chưa có bằng chứng xác minh thu hồi trong dữ liệu đang có”. Điều đó khác với khẳng định “thu hồi chắc chắn thất bại”. Hệ thống có thể đã thu hồi nhưng log đến muộn, nguồn bị gián đoạn hoặc phép kiểm tra chưa chạy.

Một chương trình đối soát nên phân biệt rõ ba tình huống:

1. Đã xác nhận quyền còn tồn tại sau hạn.
2. Đã xác nhận quyền không còn trong phạm vi kiểm tra.
3. Chưa đủ bằng chứng để xác định.

Phân biệt như vậy giúp cảnh báo phản ánh đúng rủi ro và tránh đóng sự cố chỉ dựa trên một nhãn thành công ở control plane.

## 9. Ghi log tin cậy trong luồng cấp quyền

### 9.1. Đừng coi gửi log là thao tác phụ không cần kiểm tra

Nếu hệ thống cấp quyền thành công rồi gọi hàm gửi log nhưng bỏ qua lỗi, quyền có thể tồn tại mà không có bằng chứng audit. Ngược lại, log “thành công” được ghi trước khi hệ thống đích xác nhận có thể tạo ra bằng chứng sai.

Một thiết kế thường dùng là lưu bền ý định thực thi và sự kiện audit liên quan trước khi giao tác vụ cho connector. Nếu trạng thái nghiệp vụ và hàng đợi sự kiện cùng nằm trong một cơ sở dữ liệu hỗ trợ transaction, có thể ghi cả hai trong một transaction theo mô hình outbox.

```text
Trong transaction nội bộ:
    kiểm tra quyết định và điều kiện của grant
    lưu tác vụ thực thi ở trạng thái chờ
    lưu sự kiện apply_requested vào outbox
Commit

Worker thực thi:
    nhận tác vụ với operation_id ổn định
    kiểm tra điều kiện và thời hạn còn hợp lệ
    gọi hệ thống đích theo khả năng chống lặp được hỗ trợ
    lưu bằng chứng kết quả hoặc trạng thái chưa xác định
    phát sự kiện kết quả từ dữ liệu đã lưu bền
    chạy hoặc lên lịch phép kiểm tra sau thay đổi
```

Transaction nội bộ không làm thay đổi trên một hệ thống đích độc lập trở thành nguyên tử với cơ sở dữ liệu PAM. Khoảng trống giữa thực thi trên đích và ghi nhận kết quả vẫn cần xử lý bằng idempotency khi có thể, đọc lại trạng thái và đối soát.

Nếu connector chết sau khi hệ thống đích đã áp dụng quyền, lần phục hồi phải nhận diện được tác vụ cũ. Gửi lại một yêu cầu cấp quyền mới mà không đối chiếu có thể tạo grant trùng hoặc làm mới thời hạn ngoài ý muốn.

### 9.2. Thiết kế cho sự kiện trùng và đến muộn

Cơ chế chuyển log có thể phát lại khi mất phản hồi. Hệ thống nhận nên hỗ trợ phát hiện trùng theo `event_id` trong phạm vi nguồn phù hợp, đồng thời giữ dấu vết cần thiết để điều tra lỗi truyền.

Cần phân biệt:

- **Phát lại cùng sự kiện:** giữ cùng `event_id`.
- **Một lần thử thực thi mới:** có `attempt_id` mới và sự kiện tương ứng.
- **Một grant mới:** có `grant_id` mới dù subject và tài nguyên giống lần trước.

Không dùng tổ hợp “user + role + ngày” để gộp trùng. Hai lần cấp quyền hợp lệ trong cùng ngày có thể bị gộp thành một, làm sai thời lượng và chuỗi thu hồi.

Khi sự kiện đến muộn, bảng trạng thái hiện tại không được lùi từ “đã thu hồi được xác minh” về “đã cấp quyền” chỉ vì log áp dụng quyền được ingest sau. Cần dựa vào trạng thái hợp lệ và quan hệ sự kiện, không chỉ thời điểm nhận.

### 9.3. Khi pipeline audit bị lỗi

Cần có quyết định vận hành rõ ràng cho từng loại hành động. Với quyền rủi ro cao, có thể yêu cầu bằng chứng được ghi bền trước khi thực thi cấp quyền. Nếu kho log tập trung không sẵn sàng nhưng nguồn vẫn có hàng đợi bền, phải theo dõi dung lượng, độ trễ và khả năng phát lại của hàng đợi.

Nếu không còn khả năng ghi bền bằng chứng, hệ thống phải thực hiện phương án đã được phê duyệt cho tình huống đó. Ngoại lệ khẩn cấp cần giới hạn quyền, giới hạn thời gian và cơ chế lưu bằng chứng thay thế cụ thể.

Không áp dụng máy móc cùng một cách xử lý cho cấp quyền và thu hồi. Chặn một tác vụ thu hồi chỉ vì hệ thống log tập trung đang lỗi có thể kéo dài quyền nguy hiểm. Luồng thu hồi cần có thiết kế để thực hiện và lưu lại bằng chứng qua kênh bền phù hợp khi xảy ra sự cố.

## 10. Những dữ liệu không nên đưa vào log

Log cấp quyền cần mô tả việc cấp và sử dụng quyền, không trở thành một kho secret thứ hai.

Không ghi:

- Mật khẩu, private key, secret value, OTP hoặc recovery code.
- Access token, refresh token, cookie phiên và header xác thực.
- URL có credential hoặc query string chứa dữ liệu nhạy cảm.
- Toàn bộ request/response của API vault mà chưa được lọc.
- Nội dung command, biến môi trường hoặc ticket tự do có thể chứa secret mà không qua kiểm soát.
- Dữ liệu cá nhân không cần cho mục tiêu truy vết đã xác định.

Thay vì ghi giá trị secret, lưu định danh secret, phiên bản, loại thao tác và subject được phép dùng. Không coi băm một mật khẩu hoặc token rồi ghi vào log là biện pháp mặc định an toàn: dữ liệu băm vẫn có thể tạo khả năng dò đoán hoặc liên kết không cần thiết.

Một cách triển khai thực tế là dùng schema cho phép rõ từng trường, áp dụng kiểm soát kích thước và xử lý trường văn bản tự do. Khi cần liên kết tới tài liệu nhạy cảm, lưu tham chiếu và kiểm soát quyền đọc tài liệu riêng.

Với log dạng văn bản, dữ liệu do người dùng nhập có thể chứa ký tự xuống dòng hoặc chuỗi giả mạo cấu trúc. Ưu tiên log có cấu trúc với serializer phù hợp; không ghép trực tiếp lý do yêu cầu vào một dòng log theo cách làm sai ranh giới sự kiện.

## 11. Bảo vệ bằng chứng khỏi sửa, xóa và lộ lọt

Người có khả năng cấp quyền đặc quyền không nên mặc nhiên có khả năng xóa dấu vết về chính hành động đó. Cần phân tách quyền quản trị PAM, quyền quản trị pipeline log và quyền truy cập kho bằng chứng theo rủi ro của môi trường.

Các biện pháp cần cân nhắc gồm:

- Truyền log qua kênh có xác thực nguồn và bảo vệ nội dung.
- Kho lưu trữ hạn chế sửa hoặc xóa, có cơ chế lưu giữ phù hợp.
- Phân quyền đọc theo phạm vi điều tra; audit cả hành động truy cập và xuất bằng chứng.
- Lưu phiên bản schema, định nghĩa vai trò và policy đủ lâu để diễn giải sự kiện lịch sử.
- Theo dõi thao tác đổi cấu hình audit, tắt nguồn log, thay retention và xóa dữ liệu.
- Kiểm tra khả năng tìm kiếm, truy xuất và phục hồi dữ liệu đã lưu.

Nếu dùng chữ ký, manifest hoặc chuỗi băm để hỗ trợ phát hiện sửa đổi, cần quản lý khóa và điểm tin cậy riêng. Một trường hash được lưu cùng log, trong cùng nơi mà người tấn công có quyền sửa cả hai, không đủ để chứng minh log nguyên vẹn.

Cơ chế phát hiện sửa đổi cũng không tự chứng minh tính đầy đủ. Kẻ tấn công có thể tìm cách ngăn sự kiện được tạo hoặc được gửi ngay từ đầu. Vì vậy, vẫn cần đối soát với trạng thái quyền thực tế và giám sát sức khỏe nguồn log.

Thời gian lưu giữ phải xuất phát từ nhu cầu điều tra, chính sách tổ chức và nghĩa vụ áp dụng trong bối cảnh cụ thể. Không có một số ngày duy nhất phù hợp với mọi hệ thống. Cũng cần bảo đảm các tài liệu được tham chiếu trong log còn truy xuất được trong khoảng thời gian cần dùng bằng chứng.

## 12. Đối soát và cảnh báo dựa trên log cấp quyền

### 12.1. Đối soát định kỳ

Đối soát nên kết hợp ít nhất ba tập dữ liệu:

1. Những grant mà PAM cho rằng đang hoặc đã có hiệu lực.
2. Quyền quan sát trên hệ thống đích.
3. Chuỗi sự kiện quyết định và thực thi liên quan.

Các sai lệch đáng chú ý gồm:

| Sai lệch | Khả năng cần kiểm tra | Hành động điều tra |
|---|---|---|
| Có quyền trên đích nhưng không tìm thấy grant | Cấp trực tiếp, dữ liệu thiếu hoặc đường quản trị khác | Xác định nguồn thay đổi và căn cứ cho phép |
| Có phê duyệt nhưng không có kết quả thực thi | Tác vụ treo, lỗi connector hoặc log thất lạc | Kiểm tra operation và trạng thái trên đích |
| Có log áp dụng nhưng sai vai trò hoặc tài nguyên | Mapping lỗi hoặc phạm vi bị mở rộng | So sánh quyết định với thay đổi thực tế |
| Quyền còn sau thời hạn | Lỗi scheduler, thu hồi thất bại hoặc quyền từ nguồn khác | Kiểm tra nguồn gốc quyền và cơ chế hết hiệu lực |
| Có log thu hồi nhưng quyền vẫn hiệu lực | Cache, phiên/token cũ hoặc grant khác | Kiểm tra đúng đường ủy quyền và phép xác minh |
| Không nhận log từ một nguồn | Pipeline lỗi hoặc nguồn bị vô hiệu hóa | Kiểm tra heartbeat, hàng đợi và cấu hình nguồn |

Với nguồn có độ trễ thông thường, cần dành một cửa sổ chờ hợp lý trước khi kết luận thiếu sự kiện. Tuy nhiên, cửa sổ đó không nên che khuất tình huống đã xác nhận quyền đặc quyền còn hiệu lực quá hạn.

### 12.2. Quy tắc cảnh báo minh họa

Một số quy tắc hữu ích:

- Cấp quyền vào phạm vi nhạy cảm mà không có quyết định cho phép có thể xác minh.
- Phạm vi áp dụng rộng hơn phạm vi được duyệt.
- Gia hạn quyền mà không có căn cứ hoặc người chịu trách nhiệm theo workflow.
- Quyền còn tồn tại sau thời điểm hết hạn và thời gian xử lý cho phép.
- Thu hồi thất bại nhiều lần cho cùng grant.
- Break-glass được sử dụng hoặc được gia hạn ngoài quy trình.
- Cấu hình audit bị tắt gần thời điểm thay đổi quyền.
- Tài khoản dịch vụ nhận quyền mạnh hơn hồ sơ được chấp thuận.
- Một nguồn ngừng gửi log trong khi vẫn có hoạt động thay đổi quyền trên đích.

Không kết luận gian lận chỉ dựa vào việc requester và approver giống nhau. Đây là dấu hiệu cần kiểm tra theo chính sách phân tách trách nhiệm của tổ chức; một số loại yêu cầu tự động hoặc ngoại lệ có quy tắc riêng.

Ví dụ logic đối soát quá hạn có thể viết ở mức giả mã:

```text
Với mỗi grant đã từng được áp dụng:
    nếu hiện tại chưa vượt hạn được duyệt:
        chưa phân loại là quá hạn
    nếu đã có quyết định gia hạn hợp lệ:
        đánh giá theo hạn mới và lưu chuỗi thay đổi
    nếu phép kiểm tra trên đích xác nhận quyền từ grant còn tồn tại:
        cảnh báo quyền quá hạn đã xác nhận
    nếu chưa có bằng chứng kiểm tra đủ mới:
        tạo việc đối soát, phân loại chưa xác định
    nếu quyền từ grant đã được xác nhận không còn:
        kiểm tra yêu cầu xử lý phiên/token theo cơ chế đích
```

Phân loại như vậy tốt hơn một phép tìm kiếm đơn giản “không thấy log revoke”, vì vắng log chưa cho biết chắc trạng thái quyền.

## 13. Cách dùng log khi điều tra một sự cố

Giả sử lúc 10:00 có thao tác quản trị trái phép trên `host-prod-17`. Một quy trình điều tra có thể đi theo chuỗi sau:

1. Xác định danh tính thực thi thao tác và nguồn bằng chứng của thao tác đó.
2. Tìm các grant, vai trò và nguồn quyền có thể áp dụng cho danh tính tại thời điểm 10:00.
3. Với từng grant, truy ngược request, quyết định, phê duyệt, policy và phạm vi được duyệt.
4. Đối chiếu với log hệ thống đích để xác định thay đổi quyền thực tế.
5. Kiểm tra lịch sử gia hạn, thu hồi và bằng chứng xác minh.
6. Đối chiếu phiên, token, credential hoặc đường truy cập đã được sử dụng.
7. Ghi rõ đoạn chuỗi đã xác nhận, đoạn chưa đủ bằng chứng và độ lệch thời gian giữa các nguồn.

Nếu grant JIT kết thúc lúc 09:20 nhưng tài khoản vẫn thao tác quản trị lúc 10:00, có nhiều giả thuyết: quyền chưa được thu hồi, phiên cũ vẫn giữ quyền, tài khoản có grant khác hoặc dữ liệu danh tính đã bị nối sai.

Không chọn ngay một giả thuyết chỉ vì nó phù hợp với nhãn trong PAM. Log cấp quyền cung cấp chuỗi căn cứ để kiểm tra giả thuyết, còn kết luận cần dựa trên nguồn bằng chứng đủ tin cậy về hành động và quyền thực tế.

## 14. Bài thực hành thiết kế log cấp quyền

### Tình huống

Một kỹ sư được yêu cầu sửa cấu hình dịch vụ trên một máy chủ sản xuất. Quyền chỉ cho phép tập thao tác bảo trì đã xác định trong 15 phút. Connector thực hiện cấp quyền; scheduler chịu trách nhiệm thu hồi. Tài khoản dịch vụ triển khai cũng sử dụng cùng nền tảng PAM nhưng nhận quyền theo danh tính workload.

### Yêu cầu

Thiết kế bộ sự kiện cho hai loại subject mà không trộn người yêu cầu với chủ thể nhận quyền. Sau đó mô tả cách xử lý các trường hợp:

1. Yêu cầu bị từ chối.
2. Được phê duyệt nhưng connector không liên lạc được với đích.
3. Đích đã thêm binding nhưng connector mất phản hồi.
4. Retry nhận lại cùng một tác vụ.
5. Thu hồi binding thành công nhưng vẫn có phiên đang tồn tại.
6. Log từ hệ thống đích đến muộn.
7. Hàng đợi audit đầy khi có yêu cầu cấp quyền mới.
8. Một quản trị viên cấp cùng quyền trực tiếp trên đích.

### Tiêu chí tự kiểm tra

- Mỗi sự kiện có ý nghĩa rõ ràng và phản ánh đúng bằng chứng nguồn cung cấp.
- Có thể nối request, quyết định, grant, operation, attempt và thay đổi trên đích.
- Phạm vi quyền có định danh và phiên bản đủ để diễn giải về sau.
- Kết quả chưa xác định được thể hiện riêng với thất bại và thành công.
- Thời hạn được duyệt không bị nhầm với thời điểm quyền đã hết hiệu lực thực tế.
- Phát lại sự kiện không làm mất lần cấp quyền hợp lệ khác.
- Không có credential hoặc token trong payload.
- Có cách phát hiện sự kiện thiếu và đối chiếu với hệ thống đích.
- Có người hoặc cơ chế chịu trách nhiệm với quyền quá hạn và thu hồi thất bại.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng điều chỉnh |
|---|---|---|
| Chỉ ghi “grant success” | Không xác định được phạm vi và căn cứ | Tách chủ thể, tài nguyên, quyền, quyết định và kết quả |
| Dùng một trường `user` cho mọi vai trò | Nhầm người yêu cầu, người nhận và connector | Mô hình hóa từng vai trò danh tính |
| Chỉ giữ policy hiện tại | Không tái dựng được quyết định lịch sử | Giữ phiên bản hoặc snapshot có kiểm soát |
| Ghi thành công ngay sau phê duyệt | Che khuất lỗi áp dụng quyền | Tách quyết định với thực thi và xác minh |
| Coi timeout là chưa thay đổi | Retry có thể cấp trùng hoặc gia hạn ngoài ý muốn | Dùng trạng thái chưa xác định và đối soát |
| Coi hết hạn là thu hồi hoàn tất | Bỏ sót quyền còn tồn tại | Theo dõi thực thi thu hồi và kiểm tra sau thu hồi |
| Chỉ xem log PAM | Bỏ sót thay đổi trực tiếp trên đích | Thu thập log đích và đối soát trạng thái |
| Ghi toàn bộ API payload | Làm lộ secret hoặc dữ liệu không cần thiết | Dùng schema cho phép rõ trường và kiểm soát văn bản tự do |
| Dùng hash thay cho mọi biện pháp bảo vệ | Không phát hiện được sự kiện bị bỏ từ nguồn | Kết hợp bảo vệ lưu trữ, nguồn, truyền và đối soát |
| Chỉ đếm số bản ghi nhận được | Nguồn im lặng vẫn có thể trông bình thường | Giám sát heartbeat, độ trễ và khoảng trống chuỗi |

Một thiết kế log cấp quyền đạt mục tiêu khi người vận hành có thể nối được căn cứ cho phép với thay đổi thực tế, biết bằng chứng đang thiếu ở đâu và theo dõi được quyền đến khi kết thúc hiệu lực trong phạm vi đã xác minh. Đó là nền tảng để kiểm chứng JIT, JEA và least privilege bằng dữ liệu vận hành thay vì chỉ bằng cấu hình dự kiến.
