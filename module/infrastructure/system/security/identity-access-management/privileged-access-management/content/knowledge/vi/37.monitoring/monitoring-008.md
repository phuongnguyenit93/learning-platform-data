# Mass privilege assignment: giám sát việc cấp đặc quyền hàng loạt

## 1. Bài toán cần phát hiện trong PAM

Mass privilege assignment là tình huống nhiều danh tính được cấp đặc quyền trong một khoảng thời gian ngắn, hoặc một thay đổi nhỏ làm đặc quyền lan tới rất nhiều danh tính và tài nguyên. Đây là một tín hiệu cần điều tra, chưa phải kết luận rằng có tấn công.

Trong chương Monitoring của Privileged Access Management (PAM), mục tiêu của việc giám sát này là trả lời được bốn câu hỏi:

- Ai hoặc cơ chế nào đã tạo ra thay đổi quyền?
- Những danh tính nào thực sự có thêm khả năng quản trị?
- Khả năng đó áp dụng lên những tài nguyên nhạy cảm nào, trong bao lâu?
- Thay đổi có khớp với phê duyệt, phạm vi và thời hạn đã được cho phép không?

Một thay đổi có thể hợp lệ: triển khai mô hình vai trò mới, chuyển hệ thống PAM, khôi phục dịch vụ, hoặc cấp quyền JIT cho một ca bảo trì. Cũng có thể đó là lỗi đồng bộ, cấu hình nhầm nhóm, tài khoản dịch vụ bị chiếm dụng, hay hành động cố ý tạo nhiều đường truy cập quản trị để duy trì hiện diện.

Ví dụ, thêm một tài khoản vào nhóm quản trị là một sự kiện cấp quyền. Gắn vai trò quản trị cho một nhóm chứa hàng trăm tài khoản cũng chỉ có thể tạo ra một sự kiện ở hệ thống nguồn. Vì vậy, chỉ đếm số dòng log sẽ bỏ qua một trong những trường hợp nguy hiểm nhất: ít thao tác nhưng phạm vi ảnh hưởng rất lớn.

Sau bài học, người học cần có thể thiết kế quy tắc phát hiện, xây dựng dữ liệu điều tra và chọn biện pháp thu hồi phù hợp mà không làm gián đoạn hàng loạt hệ thống chỉ vì một cảnh báo chưa được xác minh.

## 2. Phân biệt thao tác cấp quyền và quyền có hiệu lực

### 2.1. Ba lớp cần theo dõi

| Lớp quan sát | Ví dụ | Câu hỏi chính |
|---|---|---|
| Thao tác quản trị | Thêm thành viên nhóm, gắn role, sửa policy | Điều gì vừa thay đổi? |
| Quan hệ cấp quyền | Danh tính A có role B trong scope C | Có bao nhiêu quan hệ mới? |
| Quyền có hiệu lực | A có thể quản trị máy chủ, lấy secret hoặc phê duyệt quyền | Khả năng thực tế đã tăng thế nào? |

Một thao tác có thể sinh nhiều quan hệ cấp quyền. Một quan hệ cấp quyền có thể mở ra nhiều quyền có hiệu lực. Ngược lại, một người đã có quyền tương đương từ đường khác thì việc thêm một nhóm mới có thể không tăng quyền có hiệu lực ngay lúc đó, nhưng vẫn tạo thêm đường duy trì quyền cần được quản lý.

Giám sát tốt phải lưu cả thay đổi cấu hình lẫn tác động có hiệu lực. Không được bỏ qua một assignment đáng ngờ chỉ vì tại thời điểm đánh giá người nhận đã có quyền tương đương.

### 2.2. Những hình thức thường gặp

- Thêm nhiều người hoặc tài khoản dịch vụ vào nhóm quản trị hệ điều hành.
- Gán role quản trị trên nhiều project, subscription, tenant hoặc vùng tài nguyên.
- Cấp khả năng checkout secret hay truy cập nhiều safes trong vault.
- Gắn quyền truy cập tới nhiều target qua session proxy của PAM.
- Cấp nhiều JIT activation cùng lúc hoặc đổi từ quyền có thời hạn thành thường trực.
- Đổi một policy khiến một nhóm rộng có thể tự phê duyệt hoặc cấp quyền cho người khác.
- Mở rộng scope của một role từ một ứng dụng sang toàn bộ môi trường.
- Gắn quyền cho một nhóm lồng nhau, khiến các thành viên gián tiếp được hưởng quyền.

Các ví dụ trên dùng thuật ngữ trung lập theo sản phẩm. Hệ thống thực tế phải ánh xạ chúng vào cơ chế đánh giá quyền của từng nền tảng; không phải mọi nền tảng đều hỗ trợ nhóm lồng nhau hay cùng một kiểu kế thừa.

### 2.3. Không giới hạn ở tài khoản con người

Danh tính nhận quyền có thể là người dùng, tài khoản máy, workload identity, service account hoặc một nhóm. Với danh tính tự động, việc không có phiên đăng nhập tương tác không làm thay đổi mức nhạy cảm của quyền mới.

Ví dụ, một service account vừa được quyền đọc secret của nhiều ứng dụng có thể tạo ra rủi ro lớn dù nó không được gắn nhãn “administrator”. Phạm vi đặc quyền phải dựa trên khả năng thực tế như quản trị, truy cập credential, sửa chính sách hoặc cấp quyền tiếp, thay vì chỉ tìm tên role chứa chữ `admin`.

## 3. Mô hình tác động: người nhận, quyền và scope

Một mô hình đơn giản để chuẩn hóa một quan hệ quyền là:

```text
grant = (subject_id, permission_set_id, resource_scope_id)
```

Thời hạn, điều kiện sử dụng, trạng thái kích hoạt và đường kế thừa là thuộc tính của quan hệ. Khi so sánh trước và sau, các thuộc tính này vẫn phải được xét; bỏ điều kiện hoặc kéo dài thời hạn có thể làm tăng đặc quyền dù ba định danh trên không đổi.

Với một thao tác đã xác nhận áp dụng tại thời điểm t:

```text
E_before = tập quyền có hiệu lực ngay trước thay đổi
E_after  = tập quyền có hiệu lực sau thay đổi

new_effective_grants = E_after \ E_before
new_subjects = distinct subject_id trong new_effective_grants
```

Phép hiệu tập hợp chỉ có ý nghĩa khi hai snapshot dùng cùng cách chuẩn hóa quyền, scope, điều kiện và cùng phiên bản ngữ nghĩa đánh giá. Nếu thiếu dữ liệu để giải quyết các điều kiện đó, ghi kết quả là chưa xác định hoặc ước lượng; không biểu diễn bằng tập rỗng.

### 3.1. Sự kiện ít nhưng tác động lớn

Giả sử nhóm `ops-oncall` có 40 danh tính và được gắn một vai trò đặc quyền trên một cụm máy chủ. Trước thay đổi, 6 danh tính đã có quyền tương đương trong cùng scope. Nếu tất cả thành viên còn lại đều đủ điều kiện hưởng quyền, kết quả là:

```text
Số sự kiện cấp quyền nguồn:          1
Số thành viên nhóm tại thời điểm đó: 40
Số danh tính tăng quyền có hiệu lực: 34
```

Con số 34 phải được đối chiếu với membership tại thời điểm sự kiện, điều kiện áp dụng, phạm vi tài nguyên và chính sách nền tảng. Nếu chỉ có membership hiện tại, hệ thống chưa thể khẳng định cả 34 người đã nhận quyền tại thời điểm trước đó.

Ngoài 34 người tăng quyền có hiệu lực, cả 40 người đều có thêm một đường cấp quyền. Đường mới này vẫn cần bằng chứng phê duyệt và có thể khiến quyền tồn tại sau khi những đường cũ bị thu hồi.

### 3.2. Nhiều grant không đồng nghĩa nhiều người

Nếu 12 danh tính cùng được cấp hai vai trò đặc quyền khác nhau, hệ thống có thể ghi nhận 24 quan hệ cấp quyền nhưng chỉ có 12 người nhận duy nhất.

| Chỉ số | Giá trị trong ví dụ | Ý nghĩa |
|---|---:|---|
| Thao tác cấp quyền thành công | 24 | Khối lượng thay đổi tại nguồn |
| Quan hệ grant mới | 24 | Số cặp quyền/scope được tạo cho các danh tính |
| Danh tính nhận quyền duy nhất | 12 | Độ rộng về người nhận |
| Vai trò đặc quyền khác nhau | 2 | Độ rộng về khả năng được cấp |
| Scope khác nhau | Phụ thuộc dữ liệu | Độ rộng về tài nguyên |

Nếu mỗi sự kiện được chuyển tiếp hai lần, lượng bản tin có thể tăng lên 48. Sau khử trùng lặp, các chỉ số nghiệp vụ vẫn phải giữ nguyên.

### 3.3. Không dùng số dư cuối cùng để che mất phơi lộ

Trong một cửa sổ năm phút, một danh tính được cấp quyền lúc 10:00 và bị thu hồi lúc 10:03. Cuối cửa sổ, nó không còn quyền, nhưng đã có ba phút để sử dụng quyền đó.

Cần phân biệt:

- `added_during_window`: các quan hệ được thêm trong cửa sổ.
- `removed_during_window`: các quan hệ bị gỡ trong cửa sổ.
- `active_at_window_end`: các quan hệ còn hiệu lực khi kết thúc cửa sổ.
- `exposure_intervals`: khoảng thời gian mỗi quyền có hiệu lực.

Không lấy số cấp trừ số thu hồi rồi kết luận không có rủi ro. Việc cấp rồi gỡ nhanh có thể là kiểm thử hợp lệ, lỗi automation hoặc dấu vết cần điều tra.

## 4. Dữ liệu tối thiểu cho quy tắc phát hiện

### 4.1. Nguồn dữ liệu

Theo dõi audit trail của PAM, hệ thống định danh, nền tảng tài nguyên và công cụ tự động hóa. Nếu tổ chức có thể cấp quyền trực tiếp ngoài PAM, log PAM đơn lẻ không đủ để khẳng định toàn bộ thay đổi đã được quan sát.

Nguồn bổ trợ thường gồm lịch sử membership, danh mục đặc quyền, inventory tài nguyên, thông tin người sở hữu, log phê duyệt JIT/JEA, kết quả luân chuyển credential và hoạt động sử dụng quyền sau khi cấp.

Log ở control plane cho biết thay đổi cấu hình đã xảy ra. Log phiên, truy cập vault hoặc thao tác trên target cung cấp bằng chứng quyền đó đã được sử dụng. Hai nhóm bằng chứng cần được liên kết nhưng không được thay thế lẫn nhau.

### 4.2. Các trường chuẩn hóa

| Nhóm | Trường gợi ý | Lý do cần |
|---|---|---|
| Định danh sự kiện | `source_system`, `tenant_id`, `event_id` | Khử trùng lặp và tách miền tin cậy |
| Thời gian | `event_time`, `ingest_time` | Xử lý log đến muộn và đo độ trễ |
| Chủ thể thực thi | `actor_id`, `actor_type` | Xác định ai thực sự gọi thao tác |
| Người khởi xướng | `initiator_id`, `request_id` | Truy ngược người yêu cầu qua automation |
| Người nhận | `subject_id`, `subject_type` | Đếm người nhận và phân tích tác động |
| Thay đổi | `action`, `result`, `operation_id` | Phân biệt thêm, gỡ, sửa và kết quả |
| Quyền | `role_id`, `permission_set_id`, `privilege_class` | Nhận diện khả năng nhạy cảm |
| Scope | `resource_scope_id`, `environment`, `tier` | Đánh giá độ rộng và mức ảnh hưởng |
| Vòng đời | `valid_from`, `valid_until`, `activation_state` | Phân biệt eligible, active và permanent |
| Phê duyệt | `change_id`, `approval_id`, `policy_version` | Đối chiếu với quyết định đã cho phép |
| Nguồn gọi | `session_id`, `client_id`, `source_ip` | Liên kết hoạt động và ngữ cảnh truy cập |

Không phải nguồn nào cũng có đủ các trường này. Hệ thống phải ghi rõ trường thiếu, nguồn thay thế và mức tin cậy của phép suy diễn. Địa chỉ IP hoặc tên hiển thị không phải định danh actor ổn định.

Định danh phải có namespace. Ví dụ, cùng một chuỗi `svc-provision` ở hai tenant không được tự động gộp thành một actor. Việc liên kết hai danh tính thuộc cùng một người chỉ thực hiện khi có ánh xạ được quản lý.

### 4.3. Sự kiện minh họa

Đây là cấu trúc nội bộ để học cách phân tích, không phải schema API của một sản phẩm cụ thể:

```json
{
  "source_system": "identity-control",
  "tenant_id": "training-tenant",
  "event_id": "evt-1842",
  "event_time": "2026-01-15T10:00:12Z",
  "ingest_time": "2026-01-15T10:00:16Z",
  "operation_id": "op-907",
  "actor_id": "svc-provision",
  "actor_type": "service_account",
  "initiator_id": "user-operator-17",
  "action": "privileged_role_assignment.add",
  "result": "success",
  "subject_id": "user-041",
  "subject_type": "human",
  "role_id": "server-operator",
  "resource_scope_id": "production-cluster-a",
  "activation_state": "active",
  "valid_until": "2026-01-15T11:00:00Z",
  "change_id": "CHG-TRAIN-204"
}
```

Một chuỗi `change_id` trong log chỉ là khóa để tra cứu. Nó không chứng minh thay đổi được duyệt. Phải đối chiếu bản ghi phê duyệt độc lập về người nhận, quyền, scope, thời gian, người duyệt và điều kiện sử dụng.

Không đưa password, token, private key hay nội dung secret vào sự kiện. Bằng chứng cần tham chiếu tới định danh credential và hệ thống lưu trữ được kiểm soát, thay vì sao chép giá trị bí mật sang SIEM hoặc ticket.

## 5. Thiết kế nhiều phép phát hiện bổ trợ

### 5.1. Phát hiện theo actor

Trong một cửa sổ thời gian, đếm số danh tính nhận đặc quyền từ cùng actor trong cùng tenant. Cách này phù hợp để nhận ra tài khoản quản trị hoặc service account đột ngột cấp quyền cho nhiều người.

Hạn chế: một chiến dịch có thể chia thao tác qua nhiều actor. Một actor tự động hóa dùng chung cũng có thể gộp nhiều yêu cầu độc lập thành một dòng hoạt động lớn. Vì vậy cần giữ `request_id` và người khởi xướng để tách những yêu cầu hợp lệ, đồng thời vẫn giữ tổng thể theo actor để phát hiện lỗi automation.

### 5.2. Phát hiện theo nhóm hoặc role

Theo dõi tổng số thành viên mới của một nhóm đặc quyền hay số người nhận cùng một role, kể cả khi được nhiều actor thêm vào.

Phép phát hiện này có thể bắt được việc nhiều tài khoản bị chiếm dụng cùng bổ sung người vào một nhóm. Tuy nhiên, không được suy ra mọi actor trong cửa sổ đều tham gia cùng một sự cố nếu chưa có bằng chứng liên hệ.

### 5.3. Phát hiện theo scope

Một actor có thể chỉ cấp quyền cho một danh tính nhưng gán trên hàng trăm hệ thống. Đây là khối lượng cấp quyền theo chiều tài nguyên, không phải theo số người nhận.

Theo dõi số scope, mức nhạy cảm, phạm vi kế thừa và thay đổi từ scope hẹp sang scope gốc. Số lượng scope chỉ là một chỉ số: một quyền ở scope quản trị gốc có thể ảnh hưởng lớn hơn nhiều quyền trên các môi trường thử nghiệm riêng biệt.

### 5.4. Phát hiện theo mức lan truyền

Tính số danh tính hoặc tài nguyên bị tác động bởi một thay đổi đơn lẻ: gắn role vào nhóm lớn, sửa policy dùng chung, thêm nhóm vào nhóm có quyền, hay mở rộng quyền của một role đã được sử dụng rộng.

```text
Thay đổi nhỏ ở nguồn
       ↓
Nhóm / role / policy dùng chung
       ↓
Nhiều danh tính và tài nguyên có thêm đặc quyền
```

Với nhánh này, một sự kiện thành công có thể đủ để cảnh báo. Ngưỡng số thao tác không được trở thành điều kiện bắt buộc cho mọi phép phát hiện.

### 5.5. Phát hiện theo tốc độ thấp trong thời gian dài

Ngoài cửa sổ ngắn, theo dõi tổng số người hoặc grant mới trong giờ, ngày hoặc chu kỳ vận hành phù hợp. Điều này giúp nhận ra việc phân tán cấp quyền để không vượt ngưỡng ngắn hạn.

So sánh với baseline của đúng actor, nhóm công việc và loại thay đổi. Không dùng trung bình toàn tổ chức để đánh giá một tài khoản khôi phục hiếm khi hoạt động hoặc một service account provisioning có nhịp chạy định kỳ rõ ràng.

## 6. Ngưỡng, baseline và độ ưu tiên

### 6.1. Ngưỡng minh họa

Giả sử môi trường thực hành đặt các ngưỡng sau:

| Tín hiệu | Điều kiện minh họa |
|---|---|
| Cấp quyền cho nhiều danh tính | Ít nhất 10 người nhận đặc quyền duy nhất trong 5 phút |
| Nhiều quan hệ quyền | Ít nhất 20 grant mới trong 5 phút |
| Lan truyền từ một thay đổi | Ít nhất 25 người có thêm quyền có hiệu lực |
| Mở rộng tài nguyên | Một danh tính nhận quyền quản trị trên ít nhất 15 scope trong 10 phút |

Đây là số liệu để làm bài tập, không phải ngưỡng an toàn hay khuyến nghị dùng chung cho sản xuất. Cần hiệu chỉnh bằng dữ liệu lịch sử, khả năng điều tra và mục tiêu phát hiện của tổ chức.

Một sự kiện dưới tất cả ngưỡng vẫn có thể cần ưu tiên rất cao nếu nó tạo quyền quản trị tầng định danh hoặc quyền sửa cơ chế kiểm soát PAM.

### 6.2. Những yếu tố tăng mức ưu tiên

- Quyền mới cho phép quản lý định danh, thay đổi policy hoặc cấp quyền tiếp.
- Scope chứa hệ thống xác thực, vault, nền tảng quản trị hoặc dữ liệu nhạy cảm.
- Actor, người nhận hoặc cơ chế cấp quyền chưa từng xuất hiện trong quy trình đó.
- Thời hạn mới dài hơn phê duyệt, bỏ ngày hết hạn hoặc đổi sang permanent.
- Thay đổi xảy ra qua đường ngoài quy trình PAM được quản lý.
- Có đăng nhập bất thường, thay đổi phương thức xác thực hoặc truy cập secret liên quan.
- Người nhận sử dụng quyền ngay sau khi được cấp, nhất là để tạo quyền tiếp hoặc sửa audit.
- Có nhiều lần thất bại trước loạt cấp quyền thành công.

Các yếu tố này là ngữ cảnh để ưu tiên, không tự chứng minh ý đồ xấu. Không có hoạt động sử dụng quyền cũng không chứng minh loạt cấp quyền là vô hại.

### 6.3. Tách rủi ro và độ tin cậy dữ liệu

Hai chiều đánh giá cần được giữ riêng:

```text
Risk:       hậu quả tiềm tàng của quyền và scope bị tác động
Confidence: mức chắc chắn về sự kiện, phép tính tác động và liên kết danh tính
```

Một thay đổi trên hệ thống cực kỳ nhạy cảm có thể có rủi ro cao nhưng độ tin cậy trung bình vì thiếu lịch sử membership. Cách xử lý phù hợp là ưu tiên xác minh dữ liệu, không tự hạ mức rủi ro về thấp.

Tương tự, thiếu snapshot không được coi là “không có người bị ảnh hưởng”. Cảnh báo nên hiển thị `impact_state=unknown` cùng số người quan sát được, thay vì xuất một con số 0 có vẻ chính xác.

## 7. Pipeline phát hiện có thể kiểm tra được

Một pipeline thực tế thường có các bước sau:

```text
Audit events
  → kiểm tra nguồn, thời gian, namespace
  → chuẩn hóa hành động và kết quả
  → khử bản tin trùng
  → nhận diện đặc quyền và scope
  → bổ sung membership / policy / approval
  → tính nhiều loại cửa sổ và tác động
  → tạo hoặc cập nhật cảnh báo
  → lưu bằng chứng, phân công xử lý
```

### 7.1. Chọn đúng loại kết quả

Chỉ đưa thao tác đã thành công vào bộ đếm quyền được cấp. Một request được chấp nhận, một workflow được phê duyệt hoặc một API trả về trạng thái đang xử lý chưa nhất thiết có nghĩa quyền đã áp dụng.

Các thao tác thất bại vẫn được lưu và phân tích trong phép phát hiện riêng. Nếu trộn chúng vào số người thực sự nhận quyền, cảnh báo sẽ mô tả sai tác động.

Đối với batch, cần quan sát kết quả từng phần. Một yêu cầu cấp cho 100 danh tính có thể chỉ thành công cho 7. Báo cáo phải phân biệt số người được yêu cầu, số đã xác nhận thành công và số chưa xác định.

### 7.2. Khử trùng lặp có ngữ cảnh

Nếu nguồn bảo đảm `event_id` duy nhất trong một miền đã định nghĩa, có thể dùng khóa gồm nguồn, tenant và ID đó. Nếu bảo đảm khác, adapter phải xây khóa theo đặc tả của nguồn.

Không khử trùng lặp chỉ bằng `(actor, subject, role)` vì hai lần cấp ở thời điểm khác nhau hoặc scope khác nhau có thể là hai thay đổi độc lập. Một operation chứa nhiều người nhận cũng không được thu gọn thành một người chỉ vì dùng chung `operation_id`.

Sau khử trùng lặp bản tin, tiếp tục tính `distinct` cho người nhận và quan hệ grant trong cửa sổ. Hai bước này giải quyết hai vấn đề khác nhau.

### 7.3. Cửa sổ thời gian và log đến muộn

Dùng thời điểm sự kiện để mô tả thứ tự nghiệp vụ, đồng thời lưu thời điểm tiếp nhận để đo độ trễ. Các cửa sổ trượt chồng lấn giúp giảm khả năng bỏ sót một loạt thay đổi nằm hai phía ranh giới cửa sổ cố định.

Nếu engine hỗ trợ event-time và watermark, cần cấu hình giới hạn trễ phù hợp với nguồn. Nếu không, có thể tái tính một khoảng nhìn lại hữu hạn và cập nhật cảnh báo theo khóa tương quan ổn định.

Không được bỏ im lặng sự kiện đến quá muộn. Ghi nhận vào luồng xử lý bổ sung, tạo cảnh báo bổ sung hoặc đánh dấu báo cáo trước đó cần điều chỉnh theo chính sách đã định.

Một cảnh báo có thể có nhiều phiên bản khi dữ liệu mới làm số người nhận tăng. Phân biệt cập nhật cảnh báo với một sự cố mới để tránh vừa gửi trùng vừa mất lịch sử tác động.

### 7.4. Snapshot quyền và lịch sử membership

Lưu mốc hoặc phiên bản dữ liệu dùng để giải quyết quyền tại thời điểm sự kiện. Khi nhóm thay đổi sau đó, kết quả điều tra trước đây vẫn phải giải thích được.

Nếu hệ thống chỉ cho biết thời điểm kiểm tra hiện tại, kết luận nên là “quan sát quyền hiện tại” và tách khỏi “tái dựng quyền tại thời điểm thay đổi”. Độ trễ lan truyền chính sách cũng có thể khiến control plane và target tạm thời khác nhau.

Không giả định gỡ một assignment ở nguồn đồng nghĩa mọi session, token hoặc credential đã hết khả năng sử dụng. Đây là việc cần kiểm tra riêng trong quá trình ứng phó.

## 8. Thuật toán minh họa không phụ thuộc sản phẩm

Đoạn giả mã dưới đây mô tả một phép phát hiện theo actor. Nó giả định nguồn đã cung cấp kết quả áp dụng và lớp chuẩn hóa có thể nhận diện đặc quyền. Đây không phải mã cấu hình để triển khai trực tiếp lên SIEM.

```text
on_event(event):
    validate_source_and_namespace(event)
    persist_original_evidence_reference(event)

    if duplicate_delivery(event):
        return

    normalized = normalize(event)

    if normalized.result != CONFIRMED_SUCCESS:
        send_to_attempt_or_unknown_result_analysis(normalized)
        return

    changes = extract_privilege_increases(normalized)

    for change in changes:
        # Bao gồm add, mở scope, bỏ điều kiện, tăng thời hạn...
        if not change.is_privileged_increase:
            continue

        impact = resolve_effective_impact_at_event_time(change)
        approval = match_independent_approval(change)

        append_to_event_time_store(change, impact, approval)

        for window in affected_sliding_windows(change.event_time):
            data = load_actor_window(
                tenant=change.tenant_id,
                actor=change.actor_id,
                window=window
            )

            subjects = distinct_confirmed_subjects(data)
            grants = distinct_confirmed_grants(data)

            threshold_hit = (
                count(subjects) >= 10
                or count(grants) >= 20
            )

            if threshold_hit:
                upsert_correlated_alert(
                    scope=(change.tenant_id, change.actor_id),
                    window=window,
                    evidence=data,
                    risk=assess_privilege_and_resource_risk(data),
                    confidence=assess_data_confidence(data)
                )

        evaluate_single_change_fanout(change, impact)
        evaluate_critical_privilege_change(change, impact)

    evaluate_role_scope_and_long_window_correlations(normalized)
```

Việc `approval` được tìm thấy không làm dừng pipeline. Kết quả đối chiếu được đưa vào cảnh báo và luồng phân loại. Một thay đổi có ticket hợp lệ nhưng vượt danh sách người nhận hoặc vượt scope vẫn phải lộ rõ.

Khi `impact` chưa xác định đầy đủ, phép phát hiện theo thao tác hoặc grant quan sát trực tiếp vẫn hoạt động. Nhánh lan truyền cần nêu rõ kết quả là xác nhận, giới hạn dưới hay chưa xác định; không tự tạo danh sách người bị tác động để lấp dữ liệu thiếu.

Để triển khai thuật toán này, tổ chức còn phải xác định state retention, khóa cập nhật cảnh báo, chính sách log đến muộn và khả năng tái xử lý. Những quyết định đó phải được kiểm thử bằng đặc tính nguồn dữ liệu thực tế.

## 9. Nhận diện thay đổi được phê duyệt đúng cách

### 9.1. Phê duyệt phải khớp phạm vi

Một thay đổi hàng loạt chỉ được coi là khớp kế hoạch khi kiểm tra được ít nhất:

- Actor thực thi hoặc đường automation nằm trong phạm vi cho phép.
- Người nhận cụ thể hoặc tiêu chí lựa chọn người nhận khớp bản phê duyệt.
- Tập quyền, scope và môi trường đúng với yêu cầu.
- Khoảng thời gian thực thi và thời hạn quyền đều hợp lệ.
- Người duyệt đủ thẩm quyền, đáp ứng yêu cầu tách nhiệm vụ của quy trình.
- Điều kiện đi kèm như JIT, MFA hoặc session monitoring được áp dụng khi quy trình yêu cầu.

Việc cùng xuất hiện một ticket ID trên nhiều sự kiện không đủ để coi tất cả đều được duyệt. Phải phát hiện ticket hết hạn, được tái dùng hoặc được gắn vào thay đổi ngoài nội dung ban đầu.

### 9.2. Ngoại lệ có thời hạn và có bằng chứng

Trong một đợt migration hợp lệ, có thể áp dụng ngoại lệ hẹp cho actor, nhóm người nhận, loại quyền, scope và thời gian xác định. Ngoại lệ cần chủ sở hữu, hạn hết hiệu lực và tiêu chí kết thúc.

Một ngoại lệ có thể chuyển cảnh báo sang hàng đợi kiểm tra thay đổi dự kiến hoặc giảm thông báo lặp. Nó không nên làm mất sự kiện nguồn, bỏ đối chiếu thực tế hay che những thay đổi vượt kế hoạch.

Không miễn toàn bộ service account provisioning chỉ vì nó thường xuyên cấp quyền. Đây chính là tài khoản có thể gây tác động rộng khi cấu hình sai hoặc bị chiếm dụng.

Tài khoản break-glass cũng cần giám sát. Quy trình khẩn cấp có thể thay đổi tốc độ phê duyệt và cách liên hệ người chịu trách nhiệm, nhưng không xóa nhu cầu lưu bằng chứng, giới hạn thời gian và rà soát sau sử dụng.

### 9.3. JIT và JEA không tự loại bỏ rủi ro hàng loạt

Nhiều quyền ngắn hạn đồng thời vẫn có thể gây tác động lớn trong thời gian chúng hoạt động. JIT giúp giới hạn thời gian, nhưng không thay thế kiểm soát người nhận và scope.

JEA giới hạn khả năng thực thi theo mô hình được áp dụng, nhưng hàng loạt người cùng được phép thực hiện một tác vụ nhạy cảm vẫn cần được giám sát. Theo dõi cả sự thay đổi từ quyền eligible sang active, từ tập lệnh hạn chế sang quyền rộng hơn, hoặc từ thời hạn ngắn sang quyền thường trực.

## 10. Nội dung cần có trong một cảnh báo

Một cảnh báo hữu ích không chỉ ghi “đã vượt ngưỡng 10”. Nó cần giúp người xử lý xác định nguyên nhân và phạm vi mà không phải tự ghép lại toàn bộ dữ liệu ban đầu.

```text
Alert: Mass privileged assignment
Tenant: training-tenant
Actor: svc-provision
Initiator: user-operator-17
Event interval: 10:00:00Z–10:04:59Z
Observed successful operations: 24
Distinct recipients: 12
Distinct new grants: 24
Affected scopes: production-cluster-a
Privilege classes: server administration, credential retrieval
Approval match: partial; 4 recipients outside approved set
Effective impact: confirmed for 12 recipients
Active now: 8 recipients; 4 already removed
Risk: high
Confidence: high
Evidence: source event references, grant diff, approval version
```

Ví dụ này mô tả 12 người được cấp quyền trong cửa sổ và chỉ còn 8 người có quyền khi kiểm tra. Cả 12 vẫn thuộc phạm vi điều tra lịch sử sử dụng quyền.

Phần bằng chứng cần giữ định danh sự kiện, thời điểm truy vấn, phiên bản policy hoặc membership, kết quả trước/sau, lý do đánh giá mức ưu tiên và thay đổi của chính cảnh báo. Quyền truy cập danh sách người nhận phải phù hợp vì dữ liệu này có thể tiết lộ cấu trúc quản trị của tổ chức.

## 11. Quy trình điều tra và ứng phó

### 11.1. Xác minh sự kiện trước khi sửa trạng thái

Kiểm tra nguồn log, kết quả áp dụng, lỗi parsing, bản tin lặp và độ lệch thời gian. Đối chiếu một mẫu thay đổi với control plane hoặc nguồn audit độc lập nếu có.

Phân biệt “quyền vừa được cấp” với “pipeline vừa nhận được log cũ”. Cả hai đều có thể cần xử lý, nhưng mức khẩn cấp và câu hỏi điều tra khác nhau.

### 11.2. Xác định người và cơ chế tạo thay đổi

Liên kết actor tới phiên quản trị, workload hoặc pipeline. Nếu dùng tài khoản dịch vụ, tìm người khởi xướng, phiên chạy, phiên bản cấu hình và nguồn phê duyệt.

Không quy trách nhiệm cho chủ sở hữu service account chỉ từ tên tài khoản. Chủ sở hữu là đầu mối điều tra; người thực hiện thực tế cần được chứng minh bằng bằng chứng tương quan.

### 11.3. Khoanh phạm vi được duyệt và phạm vi vượt

Tạo ba tập riêng: thay đổi khớp phê duyệt, thay đổi chắc chắn vượt phê duyệt và thay đổi chưa đủ dữ liệu để kết luận. So sánh người nhận, quyền, scope, điều kiện và thời hạn.

Kiểm tra cả khả năng cấp quyền tiếp. Một người nhận có thể đã tạo credential, thêm thành viên khác, sửa policy hoặc mở session trong thời gian có đặc quyền.

### 11.4. Chọn biện pháp ngăn chặn có phạm vi

Tùy bằng chứng và thẩm quyền đã được tổ chức cấp, biện pháp có thể bao gồm tạm dừng workflow đang tiếp tục cấp quyền, khóa đường automation bị lạm dụng, thu hồi các grant vượt phê duyệt hoặc cô lập phiên liên quan.

Không tự động vô hiệu hóa toàn bộ danh tính trong cảnh báo chỉ vì đạt ngưỡng số lượng. Danh sách người nhận có thể chứa tài khoản vận hành thiết yếu, tài khoản được duyệt và tài khoản chưa xác minh cùng lúc.

Nếu cần giữ một phần quyền để duy trì dịch vụ, dùng một đường truy cập thay thế được kiểm soát, có phạm vi và thời hạn rõ ràng. Mọi quyết định giữ quyền trong sự cố phải có người chịu trách nhiệm và bằng chứng.

### 11.5. Thu hồi quyền và xác minh khả năng truy cập còn lại

Trước khi gỡ, kiểm tra trạng thái hiện tại và đường cấp quyền cụ thể. Tránh dùng snapshot cũ để ghi đè toàn bộ membership, vì thao tác đó có thể xóa thay đổi hợp lệ đã phát sinh sau đó.

Ưu tiên thao tác thu hồi nhắm đúng assignment, kiểm tra phiên bản hoặc điều kiện tiền đề khi nền tảng hỗ trợ. Sau khi thu hồi, xác minh quyền có hiệu lực trên hệ thống liên quan và xem còn đường kế thừa nào khác không.

Việc gỡ role hoặc membership không bảo đảm chấm dứt mọi khả năng truy cập đã phát sinh. Cần xem xét session đang mở, token còn hạn, bản sao credential và khả năng truy cập ngoài PAM. Luân chuyển credential hoặc kết thúc phiên theo phạm vi phơi lộ đã xác minh và quy trình ứng phó của tổ chức.

### 11.6. Hoàn tất điều tra và cải thiện kiểm soát

Lưu mốc cấp, sử dụng, thu hồi và xác minh; các hành động đã thực hiện; người phê duyệt ứng phó; cùng phần tác động còn chưa biết. Xác định nguyên nhân là thay đổi hợp lệ, lỗi quy trình, lỗi automation hay sự cố bảo mật dựa trên bằng chứng.

Nếu là hoạt động hợp lệ, điều chỉnh baseline hoặc ngoại lệ hẹp. Nếu là lỗi, bổ sung giới hạn người nhận, scope, thời hạn và cơ chế kiểm tra trước khi áp dụng batch. Nếu là sự cố, tìm các đường quyền phát sinh tiếp theo thay vì kết thúc ngay khi grant đầu tiên đã bị gỡ.

## 12. Bài thực hành với dữ liệu giả lập

### 12.1. Bối cảnh và giới hạn

Dùng log giả lập trong môi trường học tập, không cấp quyền thật trên production. Một service account `svc-provision` thực hiện yêu cầu cấp hai loại đặc quyền trên `production-cluster-a` cho 12 danh tính giả lập.

Phê duyệt độc lập `CHG-TRAIN-204` chỉ cho phép 8 người trong danh sách `user-001` đến `user-008`, với đúng hai loại quyền đó và thời hạn một giờ. Bốn người từ `user-009` đến `user-012` nằm ngoài danh sách được duyệt.

Giả định baseline xác nhận cả 12 chưa có các quyền tương đương trong scope này. Mỗi grant có một sự kiện thành công riêng, định danh sự kiện duy nhất, và kết quả lan truyền đã được xác nhận. Mỗi sự kiện được chuyển tiếp hai lần để kiểm tra khử trùng lặp.

### 12.2. Chuỗi dữ liệu

| Thời điểm | Dữ liệu giả lập | Kết quả cần nhận ra |
|---|---|---|
| 10:00–10:03 | 24 sự kiện cấp thành công cho 12 người × 2 quyền | 24 grant mới, 12 người nhận |
| 10:00–10:04 | Các bản sao chuyển tiếp của cùng 24 sự kiện | Không tăng số grant hay người nhận |
| 10:04 | Gỡ hai quyền của từng người trong nhóm 4 người ngoài phê duyệt | 8 grant đã thu hồi, lịch sử phơi lộ vẫn còn |
| 10:06 | Một sự kiện cấp thành công có event-time 10:02 đến muộn | Cập nhật cửa sổ hoặc xử lý đến muộn theo chính sách |
| 10:07 | 30 lần cấp quyền bị từ chối cho các danh tính khác | Phân tích nỗ lực riêng, không tính vào quyền đã cấp |

Để kiểm tra số liệu cơ sở, chạy trước ba dòng đầu. Dòng sự kiện đến muộn là một ca kiểm thử độc lập; khai báo rõ người nhận và grant mới hay trùng trước khi tính kết quả mong đợi.

### 12.3. Kết quả mong đợi của ca cơ sở

Với cửa sổ từ 10:00 đến trước 10:05:

```text
Bản tin cấp quyền nhận được:             48
Sự kiện cấp thành công sau khử trùng:     24
Grant mới trong cửa sổ:                  24
Người nhận đặc quyền duy nhất:           12
Người nhận khớp phê duyệt:                8
Người nhận ngoài phê duyệt:               4
Grant đã thu hồi trước cuối cửa sổ:       8
Grant còn hiệu lực ở cuối cửa sổ:        16
Người còn quyền ở cuối cửa sổ:            8
```

Ngưỡng 10 người hoặc 20 grant đều bị vượt. Cảnh báo phải giữ 12 người trong phạm vi điều tra, đánh dấu 4 người ngoài phê duyệt và cho biết các grant của họ đã được gỡ. Không đóng cảnh báo chỉ vì quyền hiện tại của bốn người đó đã hết.

### 12.4. Ca lan truyền qua nhóm

Thay bộ dữ liệu bằng một sự kiện gắn role đặc quyền vào nhóm có 40 thành viên, trong đó 6 người đã có quyền tương đương từ trước. Giả định đã giải quyết đầy đủ điều kiện và membership tại thời điểm thay đổi.

Kết quả cần nhận ra là 1 sự kiện nguồn, 40 người có đường cấp quyền mới và 34 người tăng quyền có hiệu lực. Nhánh phát hiện lan truyền phải hoạt động dù nhánh đếm 10 thao tác không đạt ngưỡng.

Sau đó bỏ lịch sử membership và chỉ giữ membership hiện tại. Kết quả tái dựng phải chuyển sang chưa xác định hoặc ước lượng có ghi rõ cơ sở; không tiếp tục khẳng định 34 là số người tăng quyền trong quá khứ.

### 12.5. Các kiểm thử bổ sung quan trọng

- Chia 12 người nhận qua hai actor để kiểm tra tương quan theo role và scope.
- Đặt một nửa sự kiện trước ranh giới phút thứ năm và một nửa sau ranh giới để kiểm tra cửa sổ trượt.
- Dùng cùng tên actor ở hai tenant để xác nhận dữ liệu không bị gộp sai.
- Giữ số người nhận bằng một nhưng mở rộng tới nhiều scope để kiểm tra chiều tài nguyên.
- Gắn ticket hợp lệ nhưng kéo dài quyền thành thường trực để kiểm tra đối chiếu thời hạn.
- Chỉ gửi trạng thái đang xử lý để xác nhận pipeline chưa tính quyền là đã áp dụng.
- Gửi sự kiện sửa policy làm tăng quyền mà không có hành động `add` để kiểm tra chuẩn hóa ngữ nghĩa.
- Mô phỏng lỗi nguồn membership để kiểm tra việc hiển thị tác động chưa xác định.

## 13. Đo chất lượng vận hành của phép giám sát

Theo dõi chất lượng dữ liệu cùng với số cảnh báo. Ít cảnh báo có thể do hoạt động ổn định, nhưng cũng có thể do mất log hoặc thay đổi schema làm detector ngừng nhận diện hành động cấp quyền.

| Chỉ số | Câu hỏi mà chỉ số giúp trả lời |
|---|---|
| Độ bao phủ nguồn cấp quyền | Các đường thay đổi trực tiếp ngoài PAM có được quan sát không? |
| Độ trễ tiếp nhận | Quyền có thể bị sử dụng bao lâu trước khi sự kiện tới nơi phân tích? |
| Tỷ lệ giải quyết tác động | Bao nhiêu thay đổi có đủ membership, policy và scope để đánh giá? |
| Tỷ lệ gắn được người khởi xướng | Có truy ngược automation tới yêu cầu cụ thể được không? |
| Thời gian phát hiện | Mất bao lâu từ thay đổi đầu tiên tới cảnh báo có thể xử lý? |
| Thời gian xác minh và ngăn chặn | Quy trình có thu hẹp phơi lộ đủ nhanh không? |
| Cảnh báo trùng và đóng sai | Tương quan và cập nhật trạng thái có làm tăng tải hoặc bỏ sót không? |
| Tỷ lệ ngoại lệ hết hạn đúng lúc | Ngoại lệ có trở thành miễn trừ lâu dài ngoài ý muốn không? |

Tỷ lệ cảnh báo không phải sự cố cần được phân loại theo nguyên nhân: thay đổi đúng kế hoạch, ngưỡng chưa phù hợp, thiếu dữ liệu hay lỗi chuẩn hóa. Không gộp tất cả thành một lý do “false positive” rồi miễn toàn bộ actor.

Việc kiểm thử định kỳ có thể dùng replay log và tình huống tổng hợp. Một bài kiểm tra tốt phải chứng minh được cả ca gây cảnh báo lẫn ca không gây cảnh báo, cùng tác động của log trùng, log muộn và dữ liệu thiếu.

## 14. Sai lầm thường gặp

**Chỉ đếm sự kiện.** Một thay đổi trên nhóm lớn có thể mở đặc quyền cho nhiều người nhưng chỉ tạo một dòng audit. Bổ sung phân tích mức lan truyền và quyền có hiệu lực.

**Chỉ nhìn tên role.** Quyền đọc credential, quản lý policy hay phê duyệt truy cập có thể đặc biệt nhạy cảm dù không mang tên quản trị. Duy trì danh mục đặc quyền theo khả năng.

**Tin vào ticket ID do sự kiện tự khai.** Một mã yêu cầu không thay cho bản phê duyệt độc lập. Đối chiếu nội dung và thời hạn của quyết định được duyệt.

**Miễn mọi hoạt động của automation.** Tài khoản automation thường có khả năng cấp quyền rộng. Giữ giám sát và ngoại lệ theo phạm vi cụ thể.

**Trừ hết quyền đã thu hồi khỏi số phơi lộ.** Cách này che đi khoảng thời gian quyền đã được sử dụng. Giữ lịch sử cấp, thu hồi và sử dụng quyền.

**Dùng membership hiện tại như lịch sử chắc chắn.** Thay đổi nhóm sau sự kiện làm sai phép tái dựng. Gắn phiên bản dữ liệu và mức tin cậy vào kết quả.

**Tự động gỡ toàn bộ quyền theo snapshot cũ.** Thao tác có thể ảnh hưởng thay đổi hợp lệ mới hơn hoặc dịch vụ thiết yếu. Thu hồi đúng assignment, kiểm tra trạng thái hiện tại và xác minh sau thao tác.

**Cho rằng thu hồi role đã kết thúc mọi truy cập.** Session, token hoặc credential đã được lấy ra có thể cần xử lý riêng. Xác minh khả năng truy cập thực tế và phần phơi lộ tiếp theo.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một sự kiện gắn role vào nhóm có thể cần ưu tiên hơn 30 sự kiện cấp quyền riêng lẻ?
2. Khác biệt giữa số bản tin, số thao tác, số grant và số người nhận duy nhất là gì?
3. Một người đã có quyền tương đương có làm assignment mới trở nên không đáng quan tâm không?
4. Vì sao gỡ toàn bộ quyền trước khi kết thúc cửa sổ không xóa được rủi ro của cửa sổ đó?
5. Cần đối chiếu những gì trước khi kết luận loạt cấp quyền khớp ticket được duyệt?
6. Khi thiếu lịch sử membership, cảnh báo nên mô tả tác động như thế nào?
7. Làm sao phát hiện một chiến dịch chia việc cấp quyền qua nhiều actor?
8. Sau khi thu hồi assignment, những loại khả năng truy cập nào còn phải kiểm tra?

Hướng trả lời: tập trung vào tác động có hiệu lực, đường cấp quyền mới, scope, vòng đời và bằng chứng tại thời điểm thay đổi. Một quy tắc giám sát Mass privilege assignment có giá trị khi nó chỉ ra được ai đã tăng quyền, tăng quyền trên đâu, có khớp phê duyệt không và điều gì cần xác minh để kiểm soát phần phơi lộ còn lại.
