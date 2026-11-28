# Role assignment

## 1. Role assignment cần được audit như thế nào?

**Role assignment** là quan hệ gán một role cho một chủ thể trong một phạm vi xác định. Chủ thể có thể là người dùng, nhóm hoặc workload; phạm vi có thể là tenant, project, một tập tài nguyên hoặc toàn nền tảng theo mô hình của hệ thống.

Trong chương Logging và audit IAM, điều quan trọng không chỉ là biết “ai đang có role nào”, mà còn có thể giải thích:

- Ai đã yêu cầu và ai thực hiện việc cấp role?
- Role được cấp cho chủ thể nào, trong phạm vi nào?
- Việc cấp dựa trên căn cứ và phê duyệt nào?
- Thay đổi đã được ghi nhận thành công hay mới chỉ được yêu cầu?
- Quyền bắt đầu và kết thúc vào thời điểm nào?
- Khi gỡ assignment, chủ thể còn nhận quyền tương tự qua đường khác không?

Ví dụ, một quản trị viên tenant An cấp role REPORT_OPERATOR cho Lan. Một dòng log “role updated” không đủ cho điều tra vì thiếu chủ thể đích, tenant, role cụ thể và trạng thái kết quả.

Audit tốt biến thay đổi quyền thành một chuỗi sự kiện có định danh, nguồn và ý nghĩa rõ ràng. Nó hỗ trợ kiểm soát đặc quyền, điều tra sự cố và rà soát quyền; bản thân log không thay thế kiểm tra quyền cấp role.

## 2. Phân biệt role, assignment và quyền hiệu lực

Ba đối tượng cần được tách rõ:

| Đối tượng | Ý nghĩa | Ví dụ |
|---|---|---|
| Role definition | Tập permission và điều kiện mà role biểu diễn | REPORT_OPERATOR ở phiên bản 7 |
| Role assignment | Quan hệ gán role cho một principal trong một scope | Gán role đó cho Lan tại tenant An |
| Effective permissions | Quyền thực tế sau khi kết hợp mọi nguồn và điều kiện | Lan được tạo lại báo cáo trong tenant An |

Role có thể được sửa mà assignment không đổi. Khi một permission nhạy cảm được thêm vào role, các assignment hiện có có thể bị ảnh hưởng mà không xuất hiện một lần gán mới cho từng người.

Ngược lại, xóa một assignment không chứng minh chủ thể đã mất toàn bộ quyền tương ứng. Chủ thể có thể nhận role qua nhóm, role kế thừa hoặc một grant khác.

Do đó, cần liên kết audit role assignment với:

- Sự kiện thay đổi role definition.
- Thay đổi thành viên nhóm.
- Mapping từ nhóm bên ngoài sang role nội bộ.
- Thay đổi phạm vi hoặc điều kiện của grant.
- Kích hoạt và hết hiệu lực của đặc quyền tạm thời.
- Những điều kiện như trạng thái tài khoản, membership và tenant.

Không có sự kiện gán role trực tiếp cho một user không có nghĩa user đó không từng có quyền.

## 3. Định danh các bên tham gia

Một sự kiện cần phân biệt người hoặc hệ thống thực hiện với người nhận role.

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Actor | Chủ thể đã thực hiện thay đổi ở cấp nghiệp vụ | Quản trị viên `u-009` |
| Caller workload | Phần mềm trực tiếp gọi dịch vụ IAM | `svc-admin-portal` |
| Target principal | Chủ thể nhận hoặc mất role | Người dùng `u-174` |
| Approver | Chủ thể phê duyệt khi workflow yêu cầu | `u-021` |
| Source | Nguồn tạo thay đổi | Tenant admin, provisioning, JIT, automation |
| Scope | Ranh giới áp dụng assignment | Tenant `tenant-an` |
| Assignment | Quan hệ cụ thể được thay đổi | `ra-508` |

Nếu một worker tự động áp dụng phê duyệt, actor thực thi có thể là workload, còn người yêu cầu và người phê duyệt được ghi trong các trường liên quan. Không giả rằng người phê duyệt trực tiếp gửi request cuối cùng.

Actor và caller phải lấy từ ngữ cảnh đã được xác thực. Không lấy `actor_id` trong request body rồi ghi như một sự thật đáng tin cậy.

Target principal nên được định danh ổn định và có loại rõ ràng. Email hoặc tên hiển thị có thể thay đổi và không nên là khóa duy nhất để nối lịch sử.

Nếu nguồn ngoài có định danh riêng, cần giữ đủ thông tin về miền danh tính hoặc kết nối đã xác minh để tránh nhầm hai subject giống chuỗi ID từ hai nguồn khác nhau.

## 4. Các sự kiện trong vòng đời assignment

Một workflow có thể gồm nhiều giai đoạn:

```text
Yêu cầu cấp role
        |
        v
Phê duyệt hoặc từ chối
        |
        v
Áp dụng assignment vào nguồn quyền có thẩm quyền
        |
        v
Kích hoạt và sử dụng trong phạm vi hiệu lực
        |
        v
Thu hồi, hết hạn hoặc thay đổi phạm vi
```

Không nên gọi tất cả các giai đoạn là “role granted”.

| Sự kiện minh họa | Điều nó xác nhận |
|---|---|
| role_assignment.requested | Có yêu cầu cấp quyền, chưa chứng minh đã được cấp |
| role_assignment.approved | Yêu cầu đã được phê duyệt theo workflow |
| role_assignment.denied | Yêu cầu bị từ chối theo chính sách hoặc phê duyệt |
| role_assignment.created | Quan hệ đã được tạo thành công tại nguồn được xác định |
| role_assignment.activated | Assignment đã chuyển sang trạng thái kích hoạt theo mô hình |
| role_assignment.updated | Phạm vi, điều kiện hoặc thời hạn được thay đổi |
| role_assignment.revoked | Assignment đã bị thu hồi ở nơi được sự kiện mô tả |
| role_assignment.expired | Hiệu lực đã kết thúc theo thời hạn được kiểm tra |
| role_assignment.apply_failed | Một lần áp dụng đã thất bại với kết quả xác định |

Tên sự kiện là thiết kế nội bộ. Mỗi tên cần có hợp đồng rõ về thời điểm phát sinh và nguồn trạng thái mà nó mô tả.

Một sự kiện “created” không tự chứng minh mọi service đã vô hiệu hóa cache cũ hoặc mọi token đã phản ánh role mới. Nếu việc truyền trạng thái có độ trễ, cần quan sát riêng thay vì gộp nó vào một trạng thái thành công mơ hồ.

Nếu request timeout và chưa biết giao dịch đã commit hay chưa, không ghi ngay kết luận chắc chắn “không cấp role”. Cần đối soát bằng operation ID hoặc trạng thái tại nguồn có thẩm quyền.

## 5. Thiết kế nội dung sự kiện

Một audit event cho thay đổi role thường cần các nhóm thông tin:

| Nhóm | Trường minh họa | Mục đích |
|---|---|---|
| Định danh | event_id, schema_version, event_type | Nhận biết và diễn giải sự kiện |
| Thời gian | occurred_at, recorded_at | Phân biệt thời điểm thay đổi và ghi nhận |
| Nguồn | producer, environment, source | Biết hệ thống nào phát và ở môi trường nào |
| Chủ thể | actor, caller, target | Phân biệt người thực hiện và người nhận |
| Phạm vi | tenant_id, scope_type, scope_id | Tránh nhầm role giữa các ranh giới |
| Role | role_id, role_version | Xác định role có ý nghĩa gì tại lúc thay đổi |
| Assignment | assignment_id, before, after, version | Theo dõi quan hệ và thay đổi cụ thể |
| Căn cứ | approval_id, reason_code, request_reference | Liên kết với lý do và workflow |
| Kết quả | outcome, reason_code | Biết thành công, từ chối hay lỗi |
| Tương quan | operation_id, request_id, causation_event_id | Nối sự kiện của cùng một quy trình |

Không phải mọi event cần toàn bộ trường. Chẳng hạn, một yêu cầu bị từ chối trước khi tạo assignment có thể chưa có assignment ID. Schema cần diễn tả đúng điều đó, không tạo một ID giả làm người đọc tưởng quan hệ đã tồn tại.

### Ví dụ sự kiện đã tạo assignment

JSON sau là schema minh họa, không phải chuẩn bắt buộc của một sản phẩm.

```json
{
  "event_id": "evt-728",
  "schema_version": 1,
  "event_type": "role_assignment.created",
  "occurred_at": "2026-07-03T09:15:00Z",
  "recorded_at": "2026-07-03T09:15:01Z",
  "producer": "iam-service",
  "environment": "production",
  "tenant_id": "tenant-an",
  "actor": {
    "kind": "USER",
    "subject_id": "u-009"
  },
  "caller": {
    "kind": "WORKLOAD",
    "subject_id": "svc-admin-portal"
  },
  "target": {
    "kind": "USER",
    "subject_id": "u-174"
  },
  "assignment_id": "ra-508",
  "role": {
    "role_id": "role-report-operator",
    "version": 7
  },
  "scope": {
    "type": "TENANT",
    "id": "tenant-an"
  },
  "before": null,
  "after": {
    "status": "ACTIVE",
    "valid_from": "2026-07-03T09:15:00Z",
    "expires_at": "2026-07-03T10:15:00Z"
  },
  "assignment_version": 1,
  "authorization_decision_id": "decision-661",
  "approval_id": "approval-302",
  "reason_code": "APPROVED_OPERATION",
  "operation_id": "operation-884",
  "request_id": "req-992",
  "outcome": "SUCCEEDED"
}
```

Các thời điểm và ID là dữ liệu ví dụ. `SUCCEEDED` ở đây xác nhận thay đổi tại nguồn assignment được sự kiện mô tả. Quyền thực tế vẫn phụ thuộc các điều kiện khác như membership, tenant và policy đang áp dụng.

Trường `before: null` chỉ có nghĩa chưa có quan hệ đó theo hợp đồng tạo mới; nó không khẳng định target trước đó không có bất kỳ quyền nào.

## 6. Ghi sự thật đã áp dụng, không chỉ ý định

### 6.1. Quyết định cho phép khác kết quả thực hiện

Một request có thể được phép cấp role nhưng giao dịch ghi dữ liệu thất bại.

Cần phân biệt:

```text
authorization decision = ALLOW
assignment operation = FAILED
```

Nếu ghi “granted” ngay sau ALLOW, audit sẽ mô tả sai quyền đã tồn tại.

Tương tự, trạng thái “đã gửi tới nhà cung cấp” chưa chứng minh hệ thống đích đã áp dụng. Một kết nối provisioning cần phân biệt tiếp nhận yêu cầu, áp dụng và đối soát kết quả.

### 6.2. Liên kết với giao dịch thay đổi quyền

Một mẫu thiết kế thường dùng cho nguồn quyền nằm trong cơ sở dữ liệu là ghi assignment và một bản ghi outbox trong cùng giao dịch.

```text
begin transaction

    kiểm tra quyền cấp role và các điều kiện hiện tại
    ghi thay đổi assignment
    ghi audit event vào outbox bền vững

commit

publisher chuyển event từ outbox sang pipeline audit
```

Nếu giao dịch rollback, không được phát một sự kiện thành công như thể assignment đã được tạo.

Outbox giúp liên kết thay đổi nghiệp vụ với bằng chứng cần phát trong cùng ranh giới giao dịch đó. Nó không tự tạo giao dịch nguyên tử trên mọi dịch vụ bên ngoài hoặc bảo đảm không có event bị phát lặp.

Thay đổi role cũng cần kiểm soát cạnh tranh: actor có thể mất quyền cấp trong lúc request chạy, hoặc assignment đã được một yêu cầu khác thay đổi. Cơ chế giao dịch, khóa hoặc phiên bản phải phù hợp với điều kiện cần bảo vệ. Audit nên ghi phiên bản thực sự được commit, không chỉ payload mà client đề xuất.

### 6.3. Thất bại của pipeline audit

Nếu thao tác cấp đặc quyền bắt buộc có bằng chứng bền vững, thiết kế có thể yêu cầu không commit khi không lưu được bằng chứng đó. Việc collector tạm thời không sẵn sàng có thể được xử lý khác nếu outbox đã lưu thành công và có cơ chế tiếp tục phát.

Không chỉ gọi logger rồi giả định log chắc chắn đã được lưu.

Luồng thu hồi khẩn cấp cũng cần hợp đồng riêng. Không nên vô tình giữ một quyền đã được xác định là nguy hiểm chỉ vì một nơi nhận log đang lỗi, trong khi hệ thống có thể thực hiện thu hồi và lưu bằng chứng bền vững qua phương án đã được phê duyệt. Cách xử lý phải được thiết kế trước, thay vì để một exception bất kỳ quyết định vòng đời đặc quyền.

## 7. Retry, duplicate và thứ tự sự kiện

### 7.1. Duplicate không đồng nghĩa cấp role hai lần

Publisher có thể phát lại event khi không biết lần gửi trước đã được nhận hay chưa. Một event logic nên giữ event ID ổn định khi phát lại, để hệ thống nhận nhận biết duplicate.

Operation ID và idempotency key phục vụ nhận biết yêu cầu nghiệp vụ; event ID phục vụ nhận biết sự kiện. Chúng có thể liên kết nhưng không nhất thiết có cùng vai trò.

Không dùng request ID làm bằng chứng duy nhất rằng hai thay đổi giống nhau. Một request có thể tạo nhiều event, và request ID từ phía ngoài có thể chưa đáng tin cậy.

Consumer cần có quy tắc xử lý duplicate để không đếm nhầm hai lần cấp quyền hoặc tạo hai cảnh báo cho cùng một thay đổi. Nếu giữ cả thông tin vận chuyển, phải phân biệt bản phát lại với event nghiệp vụ mới.

### 7.2. Thứ tự cần có phạm vi

Hai event có thể tới kho log không đúng thứ tự do retry hoặc chậm mạng. `recorded_at` tại nơi nhận không nhất thiết là thời điểm thay đổi thật.

Các trường hỗ trợ gồm:

- Thời điểm xảy ra do nguồn nghiệp vụ ghi nhận.
- Thời điểm nhận để đo độ trễ.
- Phiên bản tăng của cùng assignment hoặc đối tượng quyền.
- Event nguyên nhân hoặc operation ID.
- Nguồn và phạm vi của chuỗi sự kiện.

Không suy ra một thứ tự toàn cục tuyệt đối chỉ từ timestamp của nhiều máy khác nhau. Khi cần tái dựng trạng thái, cần sử dụng hợp đồng phiên bản và tính nhất quán của nguồn tương ứng.

### 7.3. Không biến event audit thành lệnh cấp lại

Một bản ghi lịch sử “role được cấp” không phải một lệnh có thể phát lại tùy ý vào hệ thống quyền.

Nếu một hệ thống khác dùng event để đồng bộ trạng thái, nó cần giao thức đồng bộ và quy tắc kiểm tra phiên bản, thu hồi, duplicate rõ ràng. Không để replay kho audit cũ làm hồi sinh assignment đã bị gỡ.

## 8. Ghi nhận đặc quyền tạm thời và quyền gián tiếp

### 8.1. Đủ điều kiện khác đang có quyền

Một user có thể đủ điều kiện xin kích hoạt ADMIN nhưng chưa có ADMIN đang hoạt động. Audit cần phân biệt:

```text
eligible -> requested -> approved -> activated -> expired/revoked
```

Chỉ ghi eligible rồi kết luận user có đặc quyền trong cả ngày sẽ làm sai phạm vi điều tra. Chỉ ghi activated mà không có thời hạn hoặc sự kiện kết thúc cũng khiến thời gian hiệu lực không rõ ràng.

Thời hạn trong assignment phải được cơ chế thực thi sử dụng. Một event “scheduled to expire” không chứng minh quyền đã thực sự mất hiệu lực tại các API nếu hệ thống vẫn tin token hoặc cache cũ ngoài giới hạn đã định nghĩa.

### 8.2. Assignment cho nhóm

Nếu role được gán cho nhóm, một user có thể nhận quyền khi được thêm vào nhóm dù không có event role assignment trực tiếp cho user đó.

Để giải thích quyền của user tại một thời điểm, cần nối được:

```text
user là thành viên nhóm
        +
nhóm được gán role trong scope
        +
role definition và điều kiện liên quan
```

Nếu có nhóm lồng nhau hoặc mapping từ directory, cần lưu được lịch sử và nguồn của những quan hệ có ảnh hưởng.

### 8.3. Role definition thay đổi

Giữ mỗi role ID và đọc definition hiện tại có thể tạo kết luận sai về quá khứ. Một role trước đây chỉ đọc báo cáo có thể đã được bổ sung quyền xuất dữ liệu.

Có thể tham chiếu phiên bản role bất biến hoặc một kho lịch sử definition được bảo vệ. Giá trị băm hỗ trợ kiểm tra khớp nội dung, nhưng một hash đơn lẻ không khôi phục được danh sách permission nếu bản definition tương ứng không còn được lưu.

Không nhất thiết sao chép toàn bộ role definition vào mọi event. Cần có cách truy xuất đúng phiên bản và giữ nó trong khoảng thời gian phục vụ mục đích audit đã xác định.

## 9. Tái dựng và đối soát lịch sử

Một câu hỏi điều tra thường là: “Vì sao Lan có quyền tạo lại báo cáo lúc 09:40?”

Các bước phân tích có thể gồm:

1. Xác định subject ổn định và tenant.
2. Tìm assignment trực tiếp, qua nhóm hoặc qua ủy quyền có hiệu lực.
3. Xác định phiên bản role và policy liên quan.
4. Kiểm tra trạng thái tài khoản, membership và tenant theo dữ liệu có sẵn.
5. Đối chiếu thời hạn, kích hoạt, thu hồi và độ trễ thực thi.
6. Nối với log quyết định và hành động tạo lại báo cáo.
7. Ghi rõ những phần thiếu bằng chứng hoặc chưa thể kết luận.

Audit assignment cho biết đường cấp quyền, nhưng không tự chứng minh user đã sử dụng mọi permission được cấp. Cần event truy cập hoặc thực thi hành động để trả lời câu hỏi sử dụng.

Ngược lại, một event DENY sau khi thu hồi có thể cho thấy một request đã bị chặn, nhưng không chứng minh mọi đường truy cập khác đều đã được kiểm tra.

Đối soát định kỳ có thể so sánh trạng thái nguồn quyền với những thay đổi đã được audit. Nếu có assignment trong kho quyền mà không tìm thấy bằng chứng tương ứng, cần điều tra khoảng trống nguồn, thời gian, pipeline hoặc thao tác ngoài luồng. Không tự xóa assignment chỉ vì truy vấn log hiện tại không tìm thấy nó.

Nếu phát hiện event sai, có thể thêm sự kiện đính chính liên kết với event gốc. Không sửa âm thầm lịch sử khiến người điều tra không biết dữ liệu đã thay đổi.

## 10. Phát hiện thay đổi quyền đáng chú ý

Dữ liệu role assignment có thể hỗ trợ các phát hiện như:

| Dấu hiệu | Câu hỏi cần điều tra |
|---|---|
| Actor tự cấp role đặc quyền | Actor có được phép tự cấp và có phê duyệt phù hợp không? |
| Nhiều assignment đặc quyền trong thời gian ngắn | Là triển khai hợp lệ hay thay đổi bất thường? |
| Role có phạm vi toàn nền tảng được cấp qua luồng tenant | Có vượt ranh giới quản trị không? |
| Quyền tạm thời được kéo dài nhiều lần | Có đang biến thành đặc quyền thường trực không? |
| Một nguồn provisioning mới cấp role mạnh | Mapping và nguồn kết nối đã được phê duyệt chưa? |
| Role bị gỡ rồi được cấp lại nhanh | Có retry, nguồn đồng bộ xung đột hoặc cố ý duy trì quyền không? |
| Cấp role nhưng thiếu reference phê duyệt bắt buộc | Workflow có bị bỏ qua hay dữ liệu audit bị thiếu không? |
| Role definition mở rộng nhưng không có đánh giá phù hợp | Những chủ thể nào chịu ảnh hưởng? |

Một dấu hiệu không tự chứng minh có tấn công. Lịch trực vận hành, migration và thay đổi tổ chức có thể tạo biến động hợp lệ. Cảnh báo cần có context và quy trình đánh giá thay vì chỉ đếm một loại event.

Không dùng trường lý do tự do như bằng chứng duy nhất của phê duyệt. Người thực hiện có thể nhập nội dung bất kỳ; cần nối tới nguồn phê duyệt có thẩm quyền và trạng thái phù hợp.

## 11. Bảo vệ và tối thiểu hóa audit data

Audit về role assignment có thể tiết lộ cấu trúc tổ chức, tài khoản đặc quyền và các mối quan hệ truy cập. Kho log cần được phân quyền như một tài nguyên nhạy cảm.

Các biện pháp cần xem xét:

- Giới hạn ai được ghi, đọc, xuất và quản lý thời hạn lưu.
- Xác thực producer và bảo vệ kênh truyền.
- Tách quyền quản trị role với khả năng sửa hoặc xóa bằng chứng.
- Giữ event theo cơ chế hạn chế sửa và có khả năng phát hiện thay đổi.
- Theo dõi truy cập và thao tác quản trị chính kho audit.
- Giới hạn quyền xem theo tenant và nhu cầu công việc.
- Kiểm soát bản xuất log và dữ liệu được đưa sang hệ thống phân tích.

Append-only hoặc lưu trữ hạn chế ghi đè không làm sự kiện tự đúng về mặt nội dung. Một nguồn bị chiếm quyền có thể phát thông tin sai; cần kết hợp bảo vệ nguồn, đối soát và các bằng chứng khác.

Không ghi password, access token, refresh token, session cookie hoặc secret của workload. Để nhận biết credential liên quan, dùng định danh nội bộ thích hợp thay vì giá trị bí mật.

Trường lý do và dữ liệu do client nhập cần được kiểm tra kích thước, mã hóa và biểu diễn an toàn trong công cụ xem log. Không nối chuỗi đầu vào thành dòng log có thể bị hiểu nhầm là event khác.

Thời gian lưu và phạm vi dữ liệu cần dựa trên mục đích và chính sách đã được tổ chức xác định. Không mặc định giữ mọi thuộc tính hồ sơ hoặc mọi payload vô thời hạn chỉ vì đây là audit.

## 12. Ví dụ xuyên suốt và các kiểm tra cần có

Giả sử tenant An cần cho Lan tạo lại một báo cáo trong một giờ:

1. Người có thẩm quyền gửi yêu cầu cấp REPORT_OPERATOR cho Lan trong tenant An.
2. Workflow ghi sự kiện yêu cầu và phê duyệt, nếu chính sách cần phê duyệt.
3. IAM service kiểm tra lại quyền cấp và điều kiện rồi commit assignment cùng bằng chứng bền vững.
4. Event created hoặc activated tham chiếu đúng role version, scope và thời hạn.
5. Khi Lan tạo lại báo cáo, log quyết định và thực thi nối với subject, tenant và quyền liên quan.
6. Khi hết hạn, hệ thống ngừng chấp nhận quyền theo cơ chế đã thiết kế và ghi nhận sự kiện tương ứng.
7. Nếu Lan còn role qua một nhóm khác, báo cáo nêu rõ đường cấp còn lại thay vì tuyên bố mọi quyền đã bị xóa.

Các tình huống kỹ thuật cần cho kết quả rõ ràng:

| Tình huống | Bằng chứng mong đợi |
|---|---|
| Actor không có quyền cấp role | Event bị từ chối với actor và scope đã xác minh; không có event cấp thành công |
| ALLOW nhưng giao dịch assignment rollback | Không ghi created thành công cho một assignment không được commit |
| Outbox commit, collector tạm ngừng | Event còn bền vững và được phát lại theo cơ chế đã thiết kế |
| Publisher gửi lặp | Consumer nhận biết cùng event logic |
| Request timeout, chưa rõ commit | Đối soát theo operation ID, không kết luận sai trạng thái |
| Event thu hồi tới trước event cấp | Dùng phiên bản và hợp đồng nguồn để diễn giải |
| Role definition được sửa | Có thể truy đúng definition tại lúc assignment được sử dụng |
| Gỡ role trực tiếp nhưng nhóm vẫn cấp quyền | Phân biệt assignment đã gỡ với quyền hiệu lực còn lại |
| Quyền tạm hết hạn nhưng cleanup job chậm | Kiểm tra cơ chế hiệu lực thực tế, không chỉ lịch chạy job |
| Truy vấn audit từ tenant khác | Không trả bằng chứng ngoài phạm vi được cấp |
| Event có dữ liệu tự do chứa ký tự đặc biệt | Không làm giả cấu trúc hoặc hiển thị sai trong công cụ log |
| Có khoảng trống event | Được phát hiện và điều tra, không suy ra tự động rằng không có thay đổi |

Audit role assignment có giá trị khi gắn được thay đổi thực sự với actor, target, role version, scope và vòng đời hiệu lực. Khi kết hợp với lịch sử nhóm, policy, trạng thái quyền và log hành động, hệ thống mới có thể giải thích đáng tin cậy ai đã cấp quyền gì, cho ai, trong phạm vi nào và quyền đó đã được sử dụng ra sao.
