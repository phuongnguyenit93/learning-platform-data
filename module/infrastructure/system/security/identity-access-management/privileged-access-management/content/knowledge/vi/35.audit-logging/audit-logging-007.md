# Ghi log thay đổi chính sách trong PAM

## 1. Vì sao thay đổi policy phải có audit trail riêng?

Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), một thay đổi chính sách có thể ảnh hưởng đến nhiều tài khoản, tài nguyên và phiên quản trị cùng lúc. Sửa thời hạn JIT từ 30 phút lên 8 giờ, bỏ yêu cầu phê duyệt hoặc cho phép xuất credential đều có thể mở rộng quyền mà không cần tạo một tài khoản quản trị mới.

Log đăng nhập hoặc bản ghi phiên chưa trả lời đầy đủ câu hỏi: **vì sao tại thời điểm đó hệ thống lại cho phép hành động này?** Muốn trả lời, cần biết phiên bản chính sách nào đã được áp dụng và ai đã làm thay đổi nó.

Ví dụ, một phiên quản trị cơ sở dữ liệu được mở lúc 10:15:

- Nhật ký phiên cho biết người dùng và tài nguyên được truy cập.
- Nhật ký cấp quyền cho biết yêu cầu JIT đã được chấp thuận.
- Nhật ký thay đổi chính sách cho biết lúc 10:05, yêu cầu hai người phê duyệt đã bị giảm xuống một người.
- Nhật ký triển khai cho biết chính sách mới đã thực sự có hiệu lực trên gateway xử lý phiên.

Bốn loại bằng chứng liên quan với nhau nhưng không thay thế nhau. Một dòng “policy updated successfully” chỉ cho biết đã có thao tác cập nhật; nó chưa chứng minh phạm vi thay đổi, thẩm quyền, quá trình phê duyệt hay thời điểm hiệu lực.

Bài học này tập trung vào **ghi nhận thay đổi chính sách kiểm soát đặc quyền**. Thay đổi cấu hình audit logging cũng được coi là một nhóm thay đổi chính sách nhạy cảm, vì nó quyết định hệ thống còn nhìn thấy và giữ lại được những bằng chứng nào.

Sau bài học, người học có thể thiết kế sự kiện audit cho vòng đời thay đổi policy, phân biệt ý định với kết quả thực tế, liên kết sự kiện với phiên đặc quyền và kiểm tra khả năng phát hiện việc nới lỏng kiểm soát.

## 2. Xác định đối tượng cần theo dõi

Policy không chỉ là một file cấu hình. Nó có thể được lưu trong cơ sở dữ liệu, Git, một dịch vụ điều khiển hoặc nhiều rule phân tán trên các thành phần PAM. Điều quan trọng là xác định đúng đối tượng kiểm soát và mọi đường có thể thay đổi nó.

| Nhóm chính sách | Ví dụ thay đổi | Tác động cần thể hiện trong log |
| --- | --- | --- |
| Phạm vi quyền | Thêm nhóm quản trị vào một safe/vault hoặc nhóm tài nguyên | Chủ thể nào được thêm quyền, tài nguyên nào bị ảnh hưởng |
| Phê duyệt | Bỏ bước phê duyệt độc lập, thêm người có quyền duyệt | Mức kiểm soát trước/sau và danh tính người phê duyệt |
| JIT/JEA | Tăng TTL, mở thêm tập lệnh hoặc tác vụ cho phép | Thời gian tồn tại quyền và phạm vi thao tác mới |
| Xác thực | Bỏ điều kiện xác thực mạnh cho đường truy cập đặc quyền | Điều kiện nào bị giảm và phạm vi ngoại lệ |
| Credential | Cho phép xem secret, đổi cơ chế checkout hoặc luân chuyển | Cách sử dụng credential thay đổi, không ghi giá trị secret |
| Phiên quản trị | Tắt ghi hình phiên hoặc giảm phạm vi ghi lệnh | Phạm vi mất khả năng quan sát |
| Break-glass | Thêm tài khoản khẩn cấp, kéo dài ngoại lệ | Điều kiện kích hoạt, thời hạn và quy trình rà soát sau sử dụng |
| Audit logging | Tắt một nguồn log, đổi bộ lọc, đích nhận hoặc thời gian lưu | Mức giảm bằng chứng, đích cũ/mới và kết quả áp dụng |
| Quản trị PAM | Thay role có quyền sửa policy hoặc cấu hình collector | Ai có thể thay kiểm soát và ai có thể che giấu thay đổi |

Ngoài thao tác tạo/sửa/xóa trực tiếp, cần theo dõi:

- Gắn hoặc tháo policy khỏi nhóm người dùng, môi trường hay tập tài nguyên.
- Thay đổi độ ưu tiên hoặc thứ tự rule làm kết quả đánh giá quyền khác đi.
- Kích hoạt, vô hiệu hóa, rollback, nhập hàng loạt và khôi phục cấu hình.
- Sửa policy cha hoặc đối tượng dùng chung làm nhiều policy con bị ảnh hưởng.
- Thay giá trị tham chiếu như nhóm danh tính, lịch truy cập hoặc danh sách đích.
- Sửa trực tiếp cấu hình trên node khiến trạng thái chạy lệch khỏi nguồn quản lý.

Một policy không đổi nội dung nhưng được gắn vào nhóm “toàn bộ máy chủ production” vẫn là thay đổi có ý nghĩa bảo mật. Chỉ theo dõi hash của file policy sẽ bỏ sót thay đổi phạm vi áp dụng này.

## 3. Phân biệt các trạng thái của một thay đổi

Không nên gom toàn bộ vòng đời vào một trạng thái `SUCCESS`. Trong môi trường phân tán, một thay đổi có thể được lưu thành công nhưng chưa được gateway nào nạp; cũng có thể được áp dụng một phần rồi bị rollback.

Một mô hình sự kiện có thể gồm:

| Sự kiện minh họa | Điều đã xảy ra | Điều chưa thể kết luận |
| --- | --- | --- |
| `policy.change.requested` | Hệ thống nhận yêu cầu có thể nhận diện và kiểm tra | Yêu cầu được phép hoặc cấu hình đã đổi |
| `policy.change.denied` | Yêu cầu bị từ chối tại một bước kiểm soát | Không có đường thay đổi khác ngoài luồng này |
| `policy.change.approved` | Một người hoặc cơ chế có thẩm quyền đã phê duyệt | Bản đã duyệt chính là bản được triển khai |
| `policy.change.committed` | Phiên bản mới được lưu vào nguồn cấu hình chuẩn | Mọi điểm thực thi đã chạy phiên bản mới |
| `policy.activation.succeeded` | Một điểm thực thi xác nhận đã kích hoạt phiên bản | Toàn bộ phạm vi triển khai đều thành công |
| `policy.activation.failed` | Việc kích hoạt tại một điểm thực thi thất bại | Những điểm khác cũng thất bại |
| `policy.rollback.committed` | Nguồn cấu hình đã nhận một thay đổi phục hồi | Cấu hình phục hồi đã có hiệu lực ở mọi nơi |
| `policy.drift.detected` | Trạng thái quan sát khác trạng thái được mong đợi | Nguyên nhân chắc chắn là hành vi tấn công |

Tên sự kiện là quy ước thiết kế trong bài, không phải API của một sản phẩm cụ thể. Hệ thống có thể dùng tên khác nhưng phải giữ rõ nghĩa.

Một thay đổi cần được theo dõi qua ít nhất ba mốc thời gian:

1. Thời điểm hành động xảy ra tại nguồn.
2. Thời điểm sự kiện được collector tiếp nhận.
3. Thời điểm phiên bản có hiệu lực tại điểm thực thi.

Thêm `scheduled_effective_at` khi thay đổi được hẹn giờ. Không coi thời điểm dự kiến là bằng chứng đã kích hoạt. Khi đồng hồ giữa các hệ thống lệch nhau, dùng thêm phiên bản cấu hình, số thứ tự theo đối tượng và định danh tương quan để dựng lại diễn biến; không chỉ sắp xếp theo timestamp.

## 4. Sự kiện audit phải trả lời những câu hỏi nào?

### 4.1. Ai thực hiện và nhân danh ai?

Cần ghi danh tính đã được xác thực bởi hệ thống, không lấy tên người dùng từ một trường tùy ý trong request.

Các trường hữu ích gồm:

- `actor.principal_id`: định danh ổn định của người hoặc workload gọi thao tác.
- `actor.principal_type`: người dùng, service account hoặc workload.
- `actor.auth_session_id`: liên kết với phiên xác thực phù hợp.
- `actor.delegated_by`: danh tính gốc khi có cơ chế ủy quyền được xác minh.
- `actor.authentication_context`: tham chiếu hoặc mô tả đã chuẩn hóa về ngữ cảnh xác thực.
- `source.channel`: giao diện quản trị, API, pipeline hoặc thao tác khẩn cấp.
- `source.workload_id`, `source.pipeline_run_id`: nguồn tự động hóa nếu có.
- `source.address`: địa chỉ quan sát được tại thành phần tin cậy.

Địa chỉ mạng hỗ trợ điều tra nhưng không chứng minh danh tính con người. Một service account dùng chung cho nhiều pipeline cũng không đủ để quy trách nhiệm nếu thiếu run ID và chuỗi liên kết đến người khởi tạo.

Không ghi access token, cookie phiên hay private key để “làm bằng chứng xác thực”. Chỉ giữ định danh tham chiếu không dùng lại được làm credential.

### 4.2. Đối tượng và phạm vi nào bị thay đổi?

Cần định danh ổn định của policy, loại policy, môi trường, đơn vị quản lý và phạm vi gắn policy. Tên hiển thị có thể đổi; một ID ổn định giúp theo dõi lịch sử qua nhiều lần đổi tên.

Nếu log được thu từ nhiều tenant, `tenant_id` là thành phần phân vùng và kiểm soát truy cập, không chỉ là nhãn tìm kiếm. Cùng một `policy_id` trong hai tenant khác nhau không được coi là cùng một đối tượng.

Với thay đổi hàng loạt, ghi sự kiện cha để mô tả lô và sự kiện con cho từng đối tượng, kèm kết quả riêng. “Bulk update completed” không đủ khi 3 trong 100 policy không cập nhật được.

### 4.3. Nội dung trước và sau là gì?

Một bản ghi có ích thường có:

- Phiên bản trước và phiên bản sau.
- Danh sách đường dẫn trường thay đổi.
- Giá trị trước/sau của các trường an toàn.
- Tham chiếu đến snapshot cấu hình đã được bảo vệ.
- Thông tin phạm vi áp dụng trước/sau nếu phạm vi thay đổi.
- Tóm tắt tác động được tính theo quy tắc có thể giải thích.

Hash giúp đối chiếu cấu hình nhưng không thay thế snapshot hoặc diff. Từ một hash đơn lẻ, điều tra viên không thể biết TTL đã tăng hay ghi hình phiên đã bị tắt.

Nếu dùng hash để so sánh đối tượng có cấu trúc, cần xác định cách chuẩn hóa và phiên bản chuẩn hóa. Cùng một JSON có thứ tự key khác nhau có thể tạo byte khác nhau. Hash của snapshot cũng không chứng minh mọi node đã nạp snapshot đó.

### 4.4. Vì sao và dựa trên thẩm quyền nào?

Ghi change request, ticket, lý do, người phê duyệt, thời điểm phê duyệt và phiên bản hoặc hash của nội dung được duyệt.

Một chuỗi `ticket_id` được nhập trong form không tự chứng minh ticket hợp lệ. Hệ thống phải xác minh trạng thái và phạm vi cho phép nếu quy trình dựa vào ticket. Cần phân biệt “tham chiếu do người dùng khai báo” với “phê duyệt đã được hệ thống xác minh”.

Phê duyệt phải gắn với đúng nội dung. Nếu người dùng sửa TTL sau khi đã được duyệt, phiên bản mới cần được đánh giá lại theo quy trình; không mang nguyên phê duyệt của phiên bản cũ sang một cách ngầm định.

### 4.5. Kết quả thực tế ra sao?

Ghi trạng thái và mã nguyên nhân có cấu trúc: từ chối vì thiếu quyền, xung đột phiên bản, lỗi lưu trữ, lỗi triển khai hoặc hết thời hạn phê duyệt.

Thông báo lỗi nên đủ để điều tra nhưng không đổ toàn bộ request, stack trace chứa secret hay thông tin kết nối nhạy cảm vào audit stream.

Cần phân biệt:

- `operation_result`: kết quả của hành động được ghi nhận.
- `activation_state`: trạng thái áp dụng tại điểm thực thi.
- `delivery_state`: trạng thái chuyển sự kiện đến hệ thống log.

Đã gửi log thành công không có nghĩa thay đổi policy thành công, và thay đổi policy thành công cũng không có nghĩa log đã đến kho tập trung.

## 5. Ví dụ sự kiện có cấu trúc

Giả sử một quản trị viên tăng thời hạn JIT tối đa của nhóm cơ sở dữ liệu production từ 30 phút lên 120 phút. Dưới đây là sự kiện minh họa tại thời điểm commit cấu hình:

```json
{
  "schema_version": "pam-policy-audit/1",
  "event_id": "evt-0471",
  "event_type": "policy.change.committed",
  "occurred_at": "2026-01-15T03:05:12Z",
  "received_at": "2026-01-15T03:05:13Z",
  "tenant_id": "tenant-training",
  "correlation_id": "chg-0184",
  "request_id": "req-0823",
  "actor": {
    "principal_id": "user-024",
    "principal_type": "human",
    "auth_session_id": "auth-0502"
  },
  "source": {
    "channel": "admin_api",
    "address": "192.0.2.24"
  },
  "policy": {
    "id": "policy-db-jit",
    "kind": "jit_access",
    "environment": "production",
    "scope_id": "resource-group-db-prod",
    "previous_version": 17,
    "new_version": 18
  },
  "changes": [
    {
      "path": "/access/max_duration_minutes",
      "before": 30,
      "after": 120
    }
  ],
  "authorization": {
    "change_request_id": "CR-0184",
    "approval_id": "approval-052",
    "approval_verified": true,
    "approved_policy_version": 18,
    "approver_ids": ["user-061"]
  },
  "impact": {
    "direction": "privilege_expansion",
    "reasons": ["JIT_MAX_DURATION_INCREASED"]
  },
  "result": {
    "operation_result": "committed",
    "activation_state": "pending"
  }
}
```

Đây là schema minh họa, không yêu cầu sao chép nguyên vào mọi hệ thống. Một triển khai cần quy định rõ kiểu dữ liệu, trường bắt buộc, giới hạn độ dài, trường nhạy cảm và cơ chế nâng phiên bản schema.

Địa chỉ trong ví dụ chỉ phục vụ tài liệu. Khi triển khai, địa chỉ nguồn phải được lấy từ đường truyền hoặc proxy tin cậy theo kiến trúc thực tế; không tin mọi header do client tự gửi.

Khi gateway nạp thành công phiên bản 18, phát sự kiện khác:

```json
{
  "schema_version": "pam-policy-audit/1",
  "event_id": "evt-0472",
  "event_type": "policy.activation.succeeded",
  "occurred_at": "2026-01-15T03:05:19Z",
  "tenant_id": "tenant-training",
  "correlation_id": "chg-0184",
  "causation_event_id": "evt-0471",
  "policy_id": "policy-db-jit",
  "policy_version": 18,
  "enforcement_point_id": "gateway-db-01",
  "operation_result": "activated"
}
```

Nếu có ba gateway, một sự kiện từ `gateway-db-01` chỉ chứng minh kết quả của gateway đó. Một bộ điều phối triển khai có thể tổng hợp trạng thái toàn phạm vi từ các xác nhận riêng, nhưng phải biết tập điểm thực thi mong đợi và thời hạn chờ.

## 6. Thu thập đầy đủ các đường thay đổi

Một lỗi thiết kế phổ biến là chỉ ghi log ở giao diện quản trị. Người dùng qua API hoặc pipeline vẫn sửa được policy nhưng không xuất hiện trong audit trail.

Nên đặt việc phát sự kiện ở lớp thực hiện thay đổi có thẩm quyền, nơi các đường gọi hợp lệ cùng đi qua. Sau đó bổ sung bằng chứng ở các thành phần khác để kiểm tra chéo.

| Đường thay đổi | Bằng chứng cần liên kết |
| --- | --- |
| Giao diện quản trị | Phiên xác thực, request ID, quyết định kiểm soát, phiên bản policy |
| API | Danh tính gọi API, quyền được dùng, request ID, kết quả thay đổi |
| Pipeline | Commit, run ID, workload identity, artifact cấu hình, phê duyệt |
| Break-glass | Người kích hoạt, lý do, thời hạn, phạm vi và rà soát sau sự kiện |
| Khôi phục backup | Người hoặc workload khôi phục, phiên bản nguồn, phạm vi phục hồi |
| Thay trực tiếp trên node | Bằng chứng hệ điều hành/nền tảng và sự kiện phát hiện drift |

Commit Git cho biết nội dung nguồn đã đổi. Nó không chứng minh cấu hình đã được triển khai, cũng không tự xác định phiên bản đang chạy trên gateway.

Nếu pipeline dùng một workload identity để triển khai, sự kiện thay đổi phải ghi đúng workload đó là actor trực tiếp. Người tạo pull request hoặc bấm chạy pipeline là danh tính liên quan trong chuỗi nguồn gốc, không nên bị gán sai thành người trực tiếp gọi API.

Thay đổi trực tiếp cơ sở dữ liệu hoặc filesystem có thể bỏ qua lớp phát sự kiện thông thường. Cần hạn chế đường này bằng quyền truy cập, giám sát nền tảng và so sánh trạng thái thực tế với nguồn chuẩn. Phát hiện drift là lớp kiểm tra bù, không bảo đảm khôi phục được danh tính tác nhân nếu đường sửa trực tiếp không có log.

## 7. Tránh trạng thái “policy đã đổi nhưng log không có”

### 7.1. Khoảng trống giữa hai thao tác ghi

Thiết kế sau tạo ra khoảng trống:

```text
1. Lưu phiên bản policy mới.
2. Gửi audit event qua mạng.
3. Trả kết quả.
```

Nếu tiến trình dừng giữa bước 1 và bước 2, policy đã thay đổi nhưng sự kiện chưa được gửi. Nếu gửi log trước rồi mới lưu policy, sự kiện có thể tồn tại dù thao tác lưu thất bại.

Vì vậy, cần xác định chính xác điều kiện nào được gọi là “đã ghi audit”. Nó có thể là đã ghi vào hàng đợi bền vững cục bộ, đã commit bản ghi outbox hay đã được kho tập trung xác nhận. Ba điều kiện này khác nhau.

### 7.2. Transactional outbox khi cùng ranh giới giao dịch

Khi cấu hình policy và outbox nằm trong cùng một hệ thống hỗ trợ giao dịch, có thể lưu phiên bản mới và sự kiện commit trong cùng giao dịch:

```text
begin transaction

  current = load_policy_for_update(policy_id)
  assert current.version == expected_version

  verify_authorization(actor, requested_change)
  verify_approval_matches(requested_change)

  next = build_next_version(current, requested_change)
  event = build_sanitized_audit_event(current, next, actor)

  save_policy(next)
  insert_outbox(event_id, event)

commit transaction

dispatcher:
  read_unpublished_outbox()
  send_to_audit_sink()
  mark_delivery_after_acknowledgement()
```

Đây là mã giả mô tả ranh giới giao dịch, không phải triển khai đầy đủ. Nó bảo đảm thay đổi cấu hình và bản ghi outbox cùng commit hoặc cùng rollback **trong ranh giới giao dịch đã nêu**. Nó chưa bảo đảm sự kiện đã đến kho tập trung và chưa bảo đảm policy đã có hiệu lực trên mọi node.

Yêu cầu bị từ chối không làm thay đổi policy và không có bản ghi commit trong giao dịch này. Các yêu cầu bị từ chối vẫn cần được ghi qua luồng audit phù hợp; tránh tạo sự kiện từ chối trong một giao dịch sau đó bị rollback làm mất luôn bằng chứng.

### 7.3. Retry và trùng lặp là trạng thái cần dự kiến

Dispatcher có thể gửi thành công nhưng không nhận được phản hồi, sau đó gửi lại. Vì vậy:

- Gán `event_id` ổn định cho cùng một sự kiện.
- Cho phép consumer xử lý trùng theo định danh sự kiện.
- Không loại trùng bằng cách chỉ so sánh actor, timestamp và policy.
- Theo dõi số bản ghi chưa chuyển, tuổi bản ghi cũ nhất và lỗi đích nhận.
- Bảo vệ hàng đợi lỗi; sự kiện không được coi là đã xử lý chỉ vì bị chuyển sang hàng đợi này.
- Duy trì thứ tự phiên bản theo policy khi cần; không giả định có một thứ tự toàn cục cho mọi đối tượng.

Hai lần người dùng gửi cùng nội dung vẫn có thể là hai lần thử riêng, cần hai request ID. Nếu API hỗ trợ idempotency, phải định nghĩa một request được thực hiện một lần thế nào và các lần retry được liên kết ra sao.

### 7.4. Chính sách khi audit pipeline hỏng

Đối với việc nới lỏng kiểm soát đặc quyền, một thiết kế có thể yêu cầu không cho commit nếu không ghi được bằng chứng bền vững. Điều kiện cần rõ: không ghi được outbox khác với kho tập trung tạm thời chưa nhận log.

Không mặc định mọi lỗi chuyển log đều phải làm dừng mọi hoạt động PAM. Cần thiết kế theo mức rủi ro và yêu cầu sẵn sàng:

- Có cho phép thay đổi khi đã ghi bền vững cục bộ nhưng chưa chuyển ra ngoài không?
- Hàng đợi được phép tồn tại bao lâu và lớn đến mức nào?
- Khi dung lượng dự phòng gần hết, loại thay đổi nào bị chặn?
- Break-glass dùng đường ghi bằng chứng độc lập nào?
- Ai được quyền bật ngoại lệ và ngoại lệ tự hết hạn ra sao?

Ngoại lệ không nên trở thành một nút “bỏ qua audit” không có kiểm soát. Nếu có cơ chế khẩn cấp, chính việc sử dụng cơ chế đó phải tạo bằng chứng và cảnh báo ngoài thành phần đang gặp sự cố.

## 8. Ghi diff có ích mà không làm lộ secret

Không dump toàn bộ request hoặc toàn bộ cấu hình vào audit log. Cấu hình PAM có thể chứa thông tin nhạy cảm ngay cả khi người thiết kế nghĩ nó chỉ là policy.

Một cách an toàn hơn là phân loại trường:

| Loại dữ liệu | Cách ghi minh họa |
| --- | --- |
| TTL, số người duyệt, bật/tắt ghi phiên | Giá trị trước/sau có cấu trúc |
| ID nhóm, role, tài nguyên | ID ổn định, có kiểm soát quyền đọc log |
| Tham chiếu secret | ID tham chiếu hoặc phiên bản nếu phù hợp, không ghi giá trị secret |
| Password, token, private key | Không thu thập vào audit event |
| Lý do thay đổi do người dùng nhập | Giới hạn độ dài, xử lý ký tự điều khiển, không cho làm hỏng bản ghi |
| Snapshot cấu hình đầy đủ | Lưu ở kho riêng được bảo vệ; log giữ tham chiếu và thông tin đối chiếu |

Nên có danh sách trường được phép ghi cho từng loại policy. Chỉ dùng blacklist tên như `password` thường không đủ vì secret có thể nằm trong trường khác hoặc cấu trúc lồng nhau.

Thay một giá trị secret bằng hash cũng không tự làm nó an toàn. Dữ liệu bí mật có miền giá trị nhỏ có thể bị dò; hash không nên trở thành cách lách quy tắc cấm ghi credential.

Khi secret bị thay đổi, log có thể ghi “tham chiếu credential chuyển từ phiên bản A sang B” hoặc “credential đã luân chuyển”, tùy mô hình. Không cần biết giá trị credential để chứng minh policy điều khiển credential đã thay đổi.

Đối với dữ liệu tự do, dùng bộ tuần tự hóa có cấu trúc thay vì nối chuỗi thành một dòng log. Ký tự xuống dòng trong lý do thay đổi không được phép tạo ra một sự kiện giả trên màn hình phân tích. Bảo vệ cả khâu hiển thị để dữ liệu không bị diễn giải như mã hoặc markup hoạt động.

## 9. Bảo vệ bằng chứng khỏi chính người có đặc quyền

PAM quản lý người có quyền cao, nên không thể giả định actor bị giám sát không có khả năng tác động đến collector hoặc kho log.

Thiết kế kiểm soát nên phân tách:

- Quyền sửa policy.
- Quyền cấu hình bộ thu và bộ lọc audit.
- Quyền đọc bằng chứng.
- Quyền thay thời gian lưu.
- Quyền xóa hoặc quản lý cơ chế bảo vệ lưu trữ.

Không để một quản trị viên có thể tự nới policy, tắt ghi nhận, xóa dấu vết rồi tự xác nhận là thay đổi hợp lệ.

Một số biện pháp hỗ trợ gồm chuyển log sang miền quản trị độc lập, hạn chế quyền sửa/xóa, dùng khả năng lưu trữ chống sửa theo nhu cầu và giữ bằng chứng kiểm tra tính toàn vẹn. Cấu hình lưu trữ bất biến vẫn cần kiểm tra phạm vi áp dụng và quyền quản trị; tên tính năng không thay cho việc xác minh.

Chuỗi hash có thể giúp phát hiện thay đổi hoặc thiếu mắt xích khi có điểm neo và vật liệu kiểm chứng được bảo vệ. Nếu cùng một actor kiểm soát toàn bộ lịch sử và điểm neo, họ có thể dựng lại chuỗi. Vì vậy, không coi “có hash” là đồng nghĩa với không thể giả mạo.

Bản thân thao tác tìm kiếm, xuất và quản lý audit log cũng cần được theo dõi phù hợp. Bằng chứng có thể chứa danh tính, cấu trúc tài nguyên và thông tin vận hành nhạy cảm; quyền xem log không nên tự động cấp cho mọi người có quyền quản trị PAM.

## 10. Thay đổi chính sách logging cần giám sát đặc biệt

Một sự kiện nguy hiểm là “tắt log thay đổi policy”. Nếu chỉ hệ thống bị tắt mới ghi sự kiện này, có thể mất luôn dấu vết cần thiết để phát hiện hành động.

Cần giám sát riêng các thay đổi:

- Tắt hoặc giảm nguồn sự kiện.
- Thêm bộ lọc loại bỏ actor, resource hoặc loại hành động.
- Đổi đích nhận sang hệ thống ngoài phạm vi quản lý.
- Giảm thời gian lưu hoặc tăng quyền xóa log.
- Giảm khả năng ghi chi tiết, làm mất before/after hoặc danh tính nguồn.
- Tắt kiểm tra toàn vẹn, heartbeat hoặc cảnh báo mất nguồn.
- Thay quyền truy cập credential của collector.

Một đường điều khiển độc lập có thể ghi nhận yêu cầu cấu hình trước khi thay đổi được kích hoạt, cùng kết quả kiểm tra sau đó. Kết hợp heartbeat, số thứ tự nguồn, đối chiếu phiên bản cấu hình và sự kiện thử nghiệm để kiểm tra kênh audit còn hoạt động.

Không có log trong một khoảng thời gian không tự chứng minh bị tắt audit: hệ thống có thể không có hoạt động, đường mạng bị lỗi hoặc collector chậm. Cảnh báo nên dựa trên tín hiệu có ngữ cảnh, ví dụ nguồn thường gửi heartbeat nhưng đã vượt ngưỡng trễ, đồng thời cấu hình filter vừa đổi.

Đích nhận log mới cần được kiểm soát như một thay đổi luồng dữ liệu. Việc đổi endpoint có thể vừa làm mất bằng chứng tại kho cũ vừa làm rò rỉ thông tin sang nơi không được phép.

## 11. Liên kết policy với phiên đặc quyền và quyết định cấp quyền

Để điều tra một phiên truy cập, chỉ biết “policy hiện tại là gì” không đủ. Policy hiện tại có thể đã khác thời điểm phiên được mở.

Mỗi quyết định cấp quyền hoặc mở phiên nên giữ được tham chiếu đến:

- Policy và phiên bản đã được dùng để đánh giá.
- Điểm thực thi đưa ra quyết định.
- Yêu cầu truy cập hoặc entitlement liên quan.
- Danh tính người dùng và tài nguyên đích.
- Thời điểm đánh giá và thời hạn của quyền được cấp.

Nếu hệ thống đánh giá lại policy trong khi phiên đang chạy, ghi sự kiện đánh giá lại hoặc thu hồi riêng. Không mặc định thay đổi policy sẽ tự động cập nhật mọi phiên đang tồn tại.

Tương tự, tăng TTL tối đa trong policy có thể chỉ ảnh hưởng đến yêu cầu mới. Thu hồi policy có thể hoặc không chấm dứt phiên đã mở, tùy cơ chế thực thi. Log cần cho biết hành vi thực tế, thay vì để điều tra viên đoán từ tên policy.

Ví dụ timeline:

```text
03:05:12  Policy v18 được commit; max JIT TTL: 30 -> 120 phút
03:05:19  gateway-db-01 xác nhận kích hoạt v18
03:06:02  Yêu cầu JIT req-access-77 được đánh giá theo v18
03:06:05  Phiên pam-session-88 được mở trên gateway-db-01
03:20:00  Policy v19 phục hồi max JIT TTL về 30 phút
03:20:08  gateway-db-01 xác nhận kích hoạt v19
03:20:10  Hệ thống rà soát riêng quyền và phiên đã cấp dưới v18
```

Dòng cuối là một hoạt động cần thực hiện và ghi nhận theo thiết kế; không được suy ra là đã xảy ra chỉ vì v19 đã kích hoạt.

## 12. Phát hiện thay đổi rủi ro và cấu hình lệch

### 12.1. Phát hiện theo ý nghĩa thay đổi

Các rule phát hiện nên nhìn vào cấu trúc before/after thay vì chỉ tìm từ khóa trong thông báo.

Ví dụ các điều kiện cần chú ý:

| Điều kiện | Vì sao đáng chú ý | Ngữ cảnh cần bổ sung |
| --- | --- | --- |
| Số người phê duyệt giảm | Giảm kiểm soát độc lập | Chính sách ngoại lệ và phạm vi production |
| TTL tăng vượt ngưỡng nội bộ | Kéo dài cửa sổ sử dụng quyền | Thời hạn cho phép, ticket, phạm vi áp dụng |
| Bật xem hoặc xuất credential | Tăng khả năng sử dụng secret ngoài kênh quản lý | Actor, tài nguyên và thời điểm hết hiệu lực |
| Tắt ghi phiên hoặc giảm audit | Giảm bằng chứng quan sát | Kênh thu độc lập, heartbeat, thay đổi liên quan |
| Thêm nhóm quá rộng | Mở rộng số người hưởng quyền | Thành viên nhóm, policy binding và môi trường |
| Sửa rồi rollback trong thời gian ngắn | Có thể tạo cửa sổ quyền ngắn | Hoạt động đặc quyền trong cửa sổ đó |
| Đổi policy ngoài pipeline chuẩn | Có khả năng bypass quy trình | Break-glass đã xác minh hoặc cấu hình drift |

Đây là tín hiệu cần đánh giá, không phải bằng chứng chắc chắn có tấn công. Một thay đổi khẩn cấp hợp lệ vẫn có thể cần cảnh báo và rà soát.

### 12.2. Ví dụ logic phát hiện

```text
when event.type == "policy.change.committed"
 and event.policy.environment == "production"
 and any change where
       path == "/session/recording_enabled"
       and before == true
       and after == false:

    create_alert(
        policy_id,
        previous_version,
        new_version,
        actor,
        correlation_id,
        approval_reference
    )
```

Logic minh họa chỉ xét một trường đơn giản. Trong thực tế, policy có thể có kế thừa, ngoại lệ và nhiều điều kiện kết hợp. Một rule trông có vẻ siết quyền ở cấp con vẫn có thể mở quyền nếu đồng thời đổi policy cha hoặc thứ tự ưu tiên.

Cần kiểm soát cả dữ liệu thiếu: sự kiện “committed” không có actor, phiên bản hoặc diff bắt buộc là lỗi chất lượng audit cần xử lý, không nên lặng lẽ bỏ qua vì rule không khớp.

### 12.3. Phát hiện drift

Định kỳ so sánh phiên bản hoặc cấu hình quan sát tại điểm thực thi với trạng thái mong đợi. Cần phân biệt:

- Độ trễ triển khai trong giới hạn cho phép.
- Triển khai thất bại hoặc node bị bỏ sót.
- Thay đổi ngoài luồng.
- Lỗi thu thập hoặc sai khác do chuẩn hóa cấu hình.

Sự kiện drift nên ghi trạng thái mong đợi, trạng thái quan sát, nguồn quan sát và thời điểm kiểm tra. Không gán actor khi chưa có bằng chứng; dùng trạng thái “chưa xác định” và liên kết với log nền tảng để điều tra.

## 13. Tình huống thực hành: tắt ghi phiên rồi phục hồi

Một nhóm vận hành phát hiện sự cố hiệu năng trên gateway. Quản trị viên dùng tài khoản khẩn cấp để tắt ghi phiên trong 20 phút, sau đó bật lại.

Nếu chỉ nhìn trạng thái cuối cùng, policy vẫn là “bật ghi phiên”. Thay đổi tạm thời biến mất khỏi cách nhìn hiện tại nhưng có thể đã ảnh hưởng đến nhiều phiên.

### 13.1. Những bằng chứng cần dựng lại

1. Danh tính thật liên quan đến việc sử dụng tài khoản khẩn cấp và cách xác thực.
2. Yêu cầu thay đổi, lý do, phạm vi, thời hạn ngoại lệ và thẩm quyền cho phép.
3. Policy trước/sau, phiên bản và diff của lần tắt.
4. Thời điểm từng gateway thực sự tắt ghi phiên.
5. Các phiên mở mới hoặc đang tồn tại trong khoảng bị ảnh hưởng.
6. Kết quả bật lại trên từng gateway, không chỉ trạng thái trên control plane.
7. Tín hiệu độc lập cho biết collector và hệ thống audit vẫn hoạt động.
8. Người rà soát hậu kiểm và các hành động xử lý phần bằng chứng bị thiếu.

### 13.2. Cách xử lý dựa trên bằng chứng

Trước hết xác định cửa sổ ảnh hưởng tại từng điểm thực thi. Nếu gateway A tắt lúc 09:00 nhưng gateway B chỉ tắt lúc 09:04, không dùng một mốc chung tùy tiện cho mọi phiên.

Sau đó liên kết log cấp quyền, log mở/đóng phiên, log ứng dụng đích và bằng chứng nền tảng còn lại. Những nguồn này có thể giúp dựng lại hoạt động nhưng không tạo ra bản ghi phiên vốn chưa được thu.

Việc bật lại ghi phiên không phục hồi được dữ liệu đã không ghi trong 20 phút. Báo cáo phải nêu rõ khoảng trống và độ chắc chắn của kết luận.

Cuối cùng, kiểm tra việc tự hết hạn hoặc phục hồi ngoại lệ có thực sự áp dụng. Nếu công việc chỉ dừng ở “ticket đã đóng”, vẫn chưa chứng minh điểm thực thi đã trở về trạng thái yêu cầu.

### 13.3. Cải thiện thiết kế

Một thiết kế có thể thay thao tác tắt rộng bằng ngoại lệ có phạm vi nhỏ, thời hạn rõ và cơ chế phục hồi được giám sát. Nếu có giải pháp vận hành phù hợp, duy trì các loại bằng chứng khác trong thời gian giảm ghi phiên.

Mỗi ngoại lệ vẫn cần sự kiện tạo, kích hoạt, hết hạn, phục hồi và rà soát. Cơ chế tự động cũng có thể thất bại nên phải theo dõi kết quả, không chỉ cấu hình thời hạn.

## 14. Kiểm tra kỹ thuật cho luồng audit policy change

Mục tiêu kiểm tra là chứng minh sự kiện đúng, đủ, liên kết được và không làm lộ dữ liệu. Không chỉ kiểm tra “có một dòng log”.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Sửa policy hợp lệ qua UI | Actor, request, diff, phiên bản, phê duyệt và kết quả liên kết được |
| Cùng thao tác qua API/pipeline | Không mất dấu đường thay đổi; nhận diện đúng workload và nguồn gốc |
| Yêu cầu không có quyền | Có sự kiện từ chối phù hợp; policy không đổi |
| Gửi version cũ khi policy đã đổi | Phát hiện xung đột; không ghi nhầm before/after của phiên bản khác |
| Thay nội dung sau phê duyệt | Không tái sử dụng phê duyệt cho nội dung khác |
| Commit thành công, một gateway lỗi | Log thể hiện áp dụng một phần, có điểm thực thi thất bại |
| Tiến trình dừng sau commit outbox | Sự kiện còn bền vững và có thể được chuyển tiếp |
| Dispatcher gửi lại | Consumer không đếm thành hai thay đổi thực tế |
| Kho log tập trung không khả dụng | Có buffering/cảnh báo/giới hạn đúng chính sách đã thiết kế |
| Outbox hoặc vùng đệm không ghi được | Thay đổi được xử lý đúng chính sách lỗi audit đã định nghĩa |
| Request có secret trong trường lồng nhau | Secret không xuất hiện trong event, lỗi hoặc hàng đợi phụ |
| Lý do chứa xuống dòng và ký tự đặc biệt | Không chèn được sự kiện giả; cấu trúc log giữ nguyên |
| Tắt filter hoặc đổi đích log | Có bằng chứng và cảnh báo qua đường kiểm soát phù hợp |
| Thay đổi rồi rollback nhanh | Cả hai thay đổi được giữ và liên kết; không mất cửa sổ ảnh hưởng |
| Sửa trực tiếp trên node | Cơ chế đối chiếu phát hiện drift trong điều kiện thử nghiệm |
| Tìm phiên cũ sau nhiều lần đổi policy | Truy hồi được phiên bản đã dùng lúc quyết định cấp quyền |

Với bài thử phục hồi, kiểm tra cả trạng thái policy và bằng chứng audit. Một hệ thống khôi phục cấu hình đúng nhưng làm mất lịch sử thay đổi vẫn chưa đáp ứng mục tiêu điều tra.

Đặt thêm chỉ số vận hành cho luồng audit: tỷ lệ lỗi schema, độ trễ tiếp nhận, backlog, nguồn ngừng gửi, sự kiện thiếu trường bắt buộc và tỷ lệ đối chiếu thành công giữa phiên bản mong đợi với phiên bản đang chạy. Ngưỡng cụ thể do yêu cầu vận hành quyết định, không sao chép một con số cố định cho mọi hệ thống.

## 15. Những nhầm lẫn thường gặp

**“Đã có Git history nên không cần log thay đổi policy.”** Git history mô tả nguồn cấu hình, còn audit trail cần nối được người hoặc workload thực hiện, quyết định kiểm soát và kết quả áp dụng thực tế.

**“Có người phê duyệt trong payload là đủ.”** Danh tính do người gửi khai báo khác với phê duyệt được hệ thống xác minh và gắn với đúng phiên bản.

**“Log success chứng minh mọi gateway đã cập nhật.”** Thành công tại control plane cần tách khỏi xác nhận kích hoạt tại từng điểm thực thi.

**“Ghi thật nhiều dữ liệu sẽ dễ điều tra hơn.”** Đổ toàn bộ cấu hình có thể lộ secret và làm bằng chứng khó dùng. Nên giữ diff có cấu trúc, tham chiếu snapshot và định danh tương quan.

**“Rollback nghĩa là thay đổi chưa từng xảy ra.”** Trong cửa sổ trước rollback có thể đã cấp quyền hoặc mở phiên. Rollback là một thay đổi mới cần được ghi và đánh giá tác động riêng.

**“Audit log tồn tại thì không thể bị sửa.”** Cần cơ chế bảo vệ lưu trữ, tách quyền, kiểm chứng và giám sát. Sự tồn tại của một file log không bảo đảm tính toàn vẹn.

**“Không thấy log là không có thay đổi.”** Cần loại trừ mất nguồn, cấu hình filter, backlog và các đường thay đổi ngoài luồng.

## 16. Bài tập tự kiểm tra

### Bài tập 1 — Sửa bản ghi thiếu bằng chứng

Bạn nhận được sự kiện:

```json
{
  "message": "admin changed production policy",
  "status": "success"
}
```

Hãy xác định các câu hỏi không thể trả lời từ bản ghi này, rồi thiết kế lại thành sự kiện có cấu trúc. Tối thiểu phải xác định được actor ổn định, policy và phạm vi, before/after hoặc phiên bản có thể truy hồi, thời điểm, kết quả và liên kết tới thẩm quyền thay đổi.

Không thêm password, token hoặc toàn bộ HTTP header vào sự kiện.

### Bài tập 2 — Phân tích kích hoạt một phần

Policy v22 đã commit. Hai gateway chạy v22, một gateway vẫn chạy v21. Một phiên được mở trong lúc triển khai.

Hãy mô tả bằng chứng cần có để xác định policy đã dùng cho phiên đó. Câu trả lời phải dựa vào điểm thực thi và phiên bản quyết định, không chỉ vào thời điểm commit v22.

### Bài tập 3 — Điều tra thay đổi ngắn hạn

Một service account bỏ yêu cầu phê duyệt lúc 14:00 và khôi phục lúc 14:03. Ticket ghi “kiểm tra tích hợp”.

Hãy lập kế hoạch kiểm tra tính hợp lệ của thay đổi, nguồn pipeline, quyền và phiên được tạo trong cửa sổ đó, cùng trạng thái phục hồi. Việc có ticket là một tham chiếu cần xác minh, chưa phải kết luận thay đổi hợp lệ.

Khi thiết kế hoàn tất, hãy thử trả lời từ bằng chứng: **ai đã thay đổi kiểm soát nào, dựa trên thẩm quyền nào, từ trạng thái nào sang trạng thái nào, có hiệu lực ở đâu, và những hoạt động đặc quyền nào đã chịu ảnh hưởng?**
