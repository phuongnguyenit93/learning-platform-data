# Audit event test

## 1. Kiểm thử sự kiện kiểm toán nhằm chứng minh điều gì?

**Audit event test** là kiểm thử việc hệ thống tạo, lưu, chuyển tiếp và cho phép khai thác các sự kiện kiểm toán theo đúng hợp đồng. Trong IAM, sự kiện phải giúp giải thích ai đã thực hiện hoặc thử thực hiện hành động nào, lên đối tượng nào, trong phạm vi nào và với kết quả gì.

Ví dụ, một quản trị viên cấp role cho người dùng. Kiểm tra API trả thành công và role xuất hiện trong database mới chứng minh thay đổi nghiệp vụ. Cần kiểm tra thêm bằng chứng audit có đúng người thực hiện, đúng người nhận quyền, đúng phạm vi và đúng kết quả đã cam kết hay không.

Ngược lại, một dòng log “grant role success” không chứng minh role thật sự được cấp. Giao dịch có thể đã rollback sau khi dòng log được ghi, sự kiện có thể gắn nhầm actor hoặc dữ liệu có thể không bao giờ tới kho audit.

Bộ test cần bao phủ **tính đúng về ngữ nghĩa, độ đầy đủ, độ bền, khả năng liên kết và kiểm soát truy cập**, đồng thời bảo đảm chính đường audit không làm lộ credential hoặc tạo tác động nghiệp vụ ngoài ý muốn.

## 2. Phân biệt audit, log chẩn đoán và metric

| Loại dữ liệu | Mục đích điển hình | Điều không tự thay thế được |
| --- | --- | --- |
| Audit event | Giải thích thao tác, chủ thể, phạm vi và kết quả có ý nghĩa kiểm toán | Toàn bộ chi tiết debug của tiến trình |
| Log chẩn đoán | Tìm nguyên nhân kỹ thuật, lỗi và trạng thái xử lý | Bằng chứng đầy đủ cho từng thay đổi quyền |
| Metric | Quan sát tỷ lệ, số lượng, độ trễ và sức khỏe tổng hợp | Đối soát chính xác ai thay đổi quyền của ai |
| Trace | Theo dõi một đường xử lý qua các thành phần | Độ bền và phạm vi lưu giữ của audit |

Một hệ thống có thể sử dụng chung hạ tầng thu thập cho một số loại, nhưng hợp đồng và vòng đời vẫn khác nhau. Metric đếm 10 lần cấp quyền không cho biết 10 thay đổi cụ thể. Trace lấy mẫu cũng không chứng minh mọi thao tác đặc quyền đã có bằng chứng.

Không coi việc gọi một logger ở mức `INFO` là đã hoàn thành audit. Cần biết sự kiện được phân loại thế nào, có thể bị tắt bởi cấu hình log không, lưu bền ở đâu và ai được truy cập.

## 3. Xây dựng danh mục sự kiện từ hành vi IAM

Trước khi viết assertion, xác định những hành vi nào cần sự kiện và ngữ nghĩa của từng sự kiện.

| Hành vi | Những kết quả cần xem xét | Chi tiết quan trọng trong test |
| --- | --- | --- |
| Đăng nhập | Thành công, thất bại, lỗi phụ thuộc | Không gắn danh tính đã xác thực cho dữ liệu tự khai chưa được chấp nhận |
| Đăng ký/gỡ MFA | Yêu cầu, hoàn tất, bị từ chối | Đúng actor, tài khoản đích và kết quả thay đổi |
| Tạo/thu hồi credential | Hoàn tất, không được phép, lỗi | Không ghi giá trị credential hoặc secret |
| Cấp/thu hồi role | Thay đổi đã cam kết, từ chối, không thay đổi | Đúng role và phạm vi, không ghi success khi rollback |
| Vô hiệu hóa tài khoản | Yêu cầu, áp dụng, kết quả tại đích | Không coi gửi event là mọi nơi đã chặn truy cập |
| Quyết định truy cập | Allow/deny theo nhu cầu, lỗi đánh giá | Phân biệt policy deny với lỗi hệ thống |
| Thay policy/trust | Yêu cầu, phê duyệt, phát hành, thất bại | Đúng phiên bản, phạm vi và người có thẩm quyền |
| Truy cập/xuất audit | Thành công hoặc bị từ chối theo chính sách | Không làm lộ dữ liệu tenant khác |

Tên và số lượng sự kiện phụ thuộc thiết kế. Không phải một request luôn phải tạo đúng một audit event. Một thao tác bất đồng bộ có thể có sự kiện nhận yêu cầu, áp dụng tại từng đích và hoàn tất, miễn là các trạng thái không bị nhầm lẫn.

Danh mục cần là đầu vào được quản lý của bộ test. Không lấy danh sách log mà implementation hiện tại tình cờ phát ra rồi coi đó là đặc tả đầy đủ.

## 4. Định nghĩa hợp đồng cho một sự kiện

### 4.1. Những trường cần xét

Một hợp đồng sự kiện nên nêu các trường bắt buộc, trường tùy chọn, kiểu dữ liệu, giới hạn kích thước và nguồn tạo giá trị.

| Nhóm trường | Ví dụ | Điều cần chứng minh |
| --- | --- | --- |
| Định danh sự kiện | `event_id`, `schema_version`, `event_type` | Có thể phân loại, đối soát và chống trùng theo thiết kế |
| Thời gian | `occurred_at`, `received_at` | Phân biệt thời điểm hành vi và thời điểm collector tiếp nhận |
| Nguồn | Service, môi trường, instance hoặc nguồn đã được xác thực | Không để client tự giả mạo hệ thống phát hành |
| Chủ thể | `actor_ref`, loại actor, ngữ cảnh đại diện | Đúng principal đã được xác minh, không nhầm người thực hiện với đối tượng |
| Đối tượng/phạm vi | `target_ref`, tenant, resource scope | Gắn với đúng mục tiêu đã xử lý |
| Hành động/kết quả | Action, outcome, reason class | Phản ánh trạng thái thật, không suy từ mã HTTP đơn lẻ |
| Liên kết | Request/job/decision reference | Có thể ghép những bước liên quan mà không chứa credential |
| Thay đổi tối thiểu | Quyền được thêm/gỡ hoặc phiên bản liên quan | Đủ giải thích nghiệp vụ, không dump toàn bộ hồ sơ |

Đây là cách tổ chức hợp đồng minh họa, không phải schema bắt buộc cho mọi hệ thống. OWASP cũng khuyến khích xác định dữ liệu sự kiện theo mục đích và kiểm thử cả cơ chế logging, lỗi hệ thống log và quyền truy cập dữ liệu. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

### 4.2. Sự kiện minh họa cho thay đổi role

```json
{
  "event_id": "audit-test-event-41",
  "schema_version": 1,
  "event_type": "role_assignment_changed",
  "occurred_at": "2026-01-15T08:30:00Z",
  "source": "iam-role-service",
  "environment": "test",
  "actor_ref": "admin-test-7",
  "actor_type": "human",
  "target_ref": "subject-test-42",
  "tenant_ref": "tenant-test-a",
  "action": "role.grant",
  "role": "course_editor",
  "resource_scope": "course-test-12",
  "outcome": "SUCCESS",
  "request_ref": "request-test-52",
  "policy_version": "role-policy-test-v3"
}
```

Trong ví dụ, `SUCCESS` nghĩa là thay đổi role đã được cam kết tại hệ thống nguồn. Nó không có nghĩa mọi ứng dụng downstream đã nhận và áp dụng quyền đó. Nếu cần theo dõi các đích, dùng sự kiện/trạng thái có ngữ nghĩa riêng.

Các định danh thử giúp trình bày quan hệ actor và target. Trong hệ thống thật, những tham chiếu này vẫn có thể liên kết tới một cá nhân và cần được bảo vệ; dùng tham chiếu không tự làm dữ liệu ẩn danh.

## 5. Kiểm tra nguồn gốc của actor, target và kết quả

### 5.1. Không lấy actor từ body hoặc header tự khai

Một request có thể chứa `actorId` hoặc tên người dùng trong dữ liệu đầu vào. Test cần chứng minh giá trị đó không thay thế principal đã xác minh khi tạo audit event.

Ví dụ, quản trị viên A gửi yêu cầu cấp role với body chứa `actorId=B`. Nếu thao tác được phép thực hiện, sự kiện vẫn phải phản ánh actor A theo security context có thẩm quyền, hoặc request phải bị từ chối theo hợp đồng. Không được gắn B là người thực hiện chỉ vì client đề xuất.

Thông tin proxy như địa chỉ nguồn cũng cần phân loại độ tin cậy. Không coi một header chuyển tiếp tùy ý là bằng chứng chắc chắn về thiết bị hoặc người dùng.

### 5.2. Đăng nhập thất bại chưa có danh tính được chấp nhận

Khi xác thực chưa thành công, hệ thống có thể chỉ biết một định danh được khai báo. Nếu cần ghi nhận để điều tra, phải biểu diễn rõ trạng thái chưa xác minh và giới hạn dữ liệu theo chính sách.

Không gán `authenticated=true` hoặc liên kết một tài khoản có quyền chỉ từ claim trong token bị từ chối. Nếu test sửa `sub` của token không hợp lệ, audit không được dùng `sub` đó như actor đã được chứng minh.

### 5.3. Phân biệt actor, subject và mục tiêu

Trong thao tác quản trị, actor là người quản trị, target là người nhận thay đổi. Trong service đại diện người dùng, actor có thể là workload và subject được đại diện là người dùng theo một quan hệ đã xác minh.

Test cần kiểm tra các quan hệ này độc lập. Một thay đổi không nên được ghi như chính người nhận quyền đã tự thực hiện nếu thực tế do quản trị viên hoặc quy trình tự động áp dụng.

Với target được client yêu cầu nhưng chưa tìm thấy hoặc chưa được phép xác minh, không biến dữ liệu tự khai thành metadata có thẩm quyền. Cần schema/phân loại phù hợp cho “mục tiêu được yêu cầu” và “mục tiêu đã xử lý” nếu sự khác nhau có ý nghĩa.

## 6. Thành công, thất bại và rollback phải có ngữ nghĩa đúng

### 6.1. Không ghi thay đổi thành công trước khi commit

Một lỗi phổ biến là phát `role_assignment_changed: SUCCESS` ngay sau khi kiểm tra quyền, trước khi transaction cập nhật role hoàn tất. Nếu database rollback, audit tạo ra lịch sử sai.

Một ca kiểm thử nên cố ý làm bước ghi thất bại hoặc transaction rollback và kiểm tra:

- Role không được thêm vào trạng thái nghiệp vụ.
- Không có sự kiện tuyên bố thay đổi đã cam kết thành công.
- Có sự kiện thử thực hiện/thất bại nếu hợp đồng yêu cầu, với outcome và reason phù hợp.

Sự kiện về attempt có thể cần tồn tại dù transaction nghiệp vụ rollback. Cơ chế ghi attempt phải được thiết kế riêng; đặt mọi loại sự kiện vào cùng transaction rồi rollback có thể làm mất bằng chứng về hành động thất bại.

### 6.2. Denied khác error

Một actor không có quyền cấp role phải nhận kết quả từ chối chính sách. Database không đáp ứng sau khi actor đã được phép là lỗi xử lý. Hai trường hợp đều không hoàn tất thay đổi, nhưng audit cần phân biệt nguyên nhân ở mức phù hợp.

Tương tự, job được tiếp nhận không được ghi như đã áp dụng ở mọi đích. Test nên kiểm tra các mốc `REQUESTED`, `ACCEPTED`, `APPLIED`, `FAILED` theo hợp đồng được sử dụng, thay vì gom tất cả phản hồi thành công thành `SUCCESS` toàn bộ quy trình.

### 6.3. Thao tác không làm thay đổi dữ liệu

Cấp lại một role đã tồn tại có thể được thiết kế là thao tác idempotent thành công nhưng không tạo thay đổi mới. Hợp đồng cần quy định có sự kiện attempt, no-op hoặc chỉ giữ sự kiện thay đổi đầu tiên.

Không yêu cầu mọi retry tạo một sự kiện “đã thêm role” mới nếu role không thay đổi. Cũng không bỏ qua mọi request lặp nếu tổ chức cần bằng chứng về các lần thử. Điều cần kiểm tra là ngữ nghĩa và khóa liên kết đúng cho từng loại sự kiện.

## 7. Kiểm thử độ bền và đường đi của sự kiện

### 7.1. Tách các mốc thay vì gọi chung là “đã log”

```text
Thao tác được đánh giá/thực hiện
  → tạo event theo hợp đồng
  → lưu bền tại điểm cam kết đã chọn
  → chuyển tiếp qua pipeline
  → collector tiếp nhận và lưu
  → sự kiện xuất hiện qua truy vấn được phép
```

Test spy nhìn thấy lời gọi `recordAudit()` chỉ chứng minh lời gọi đã được thực hiện. Nó chưa chứng minh sự kiện còn tồn tại sau khi tiến trình chết, được collector lưu hoặc có thể truy vấn qua bộ lọc tenant chính xác.

Mỗi lớp test nên ghi rõ mốc được chứng minh. Những lời khẳng định như “audit end-to-end đạt” chỉ phù hợp khi đã kiểm tra đủ đường đi và điều kiện thời gian của hợp đồng.

### 7.2. Transactional outbox và kết quả nghiệp vụ

Nếu thiết kế dùng outbox, thay đổi nghiệp vụ và ý định phát sự kiện thành công có thể được lưu trong cùng transaction cục bộ. Test cần kiểm tra tính nguyên tử: commit có cả hai; rollback không để lại một outbox event tuyên bố thay đổi thành công.

Sau đó dispatcher có thể phát lại event khi lỗi. Lưu outbox bền không tự chứng minh collector đã nhận; cần các ca riêng cho chuyển tiếp và xác minh cuối cùng. Outbox cũng không phải bằng chứng cho mọi loại attempt nếu attempt bị rollback theo cùng transaction.

### 7.3. Điểm crash và mất phản hồi

Một ma trận lỗi minh họa:

| Thời điểm lỗi | Điều cần kiểm chứng |
| --- | --- |
| Trước commit nghiệp vụ/outbox | Không có thay đổi hoặc event success đã cam kết |
| Sau commit, trước dispatcher gửi | Event vẫn còn để được chuyển tiếp khi khôi phục |
| Collector đã lưu nhưng phản hồi bị mất | Gửi lại không biến thành hai thay đổi logic khác nhau |
| Dispatcher restart | Tiếp tục từ trạng thái bền, không bỏ sót công việc |
| Collector nhận nhưng index chậm | Phân biệt lưu bền và độ trễ truy vấn; không báo mất dữ liệu chỉ vì index chưa hội tụ |
| Payload không hợp lệ | Có đường xử lý/cảnh báo, không âm thầm bỏ sự kiện bắt buộc |

Các ca này giúp xác định nơi nào cần xác nhận, idempotency hoặc cơ chế đối soát. Không suy ra khả năng chịu crash chỉ từ việc chạy nhiều lần happy path đều thành công.

## 8. Retry, trùng sự kiện và thứ tự

### 8.1. Chống trùng theo đúng đơn vị logic

Một pipeline giao ít nhất một lần có thể chuyển cùng event nhiều lần. `event_id` ổn định cho cùng sự kiện logic giúp consumer chống trùng. Test nên mô phỏng việc giao lại và xác minh kết quả truy vấn/đối soát theo hợp đồng.

Một lần đăng nhập thất bại mới là một sự kiện mới, dù cùng người khai báo và cùng nguyên nhân. Không chống trùng bằng username và action rồi làm mất các lần thử thật. Tương tự, một request quản trị lặp có thể tạo attempt riêng nhưng chỉ một thay đổi role đã cam kết.

Nếu cùng `event_id` đến với nội dung khác, không mặc định ghi đè bản trước. Cần xử lý như xung đột hoặc điều kiện cần điều tra theo thiết kế; test phải chứng minh cơ chế chống trùng không trở thành đường sửa bằng chứng.

### 8.2. Không ép thứ tự toàn cục từ timestamp

Sự kiện của nhiều service có thể đến lệch thứ tự, đồng hồ có sai lệch và index có độ trễ. Giữ rõ thời điểm xảy ra, thời điểm tiếp nhận và quan hệ nhân quả cần thiết.

Nếu hợp đồng cần thứ tự theo một tài khoản, có thể sử dụng version/sequence trong phạm vi được quản lý. Test nên kiểm tra cấp role rồi thu hồi role vẫn có thể được giải thích đúng khi transport giao đảo thứ tự, thay vì sắp xếp theo thời điểm collector nhận và kết luận quyền đã được cấp lại.

Không dùng thứ tự trong một mảng log của test đơn luồng làm bằng chứng rằng hệ thống phân tán sẽ luôn phát ra cùng thứ tự đó.

## 9. Kiểm thử khi đường audit gặp sự cố

### 9.1. Hành vi cần được định nghĩa theo loại thao tác

Không có một lựa chọn duy nhất cho mọi lỗi logging. Với thao tác yêu cầu bằng chứng bền trước khi chấp nhận thay đổi, thiết kế có thể yêu cầu commit nguyên tử với audit/outbox và từ chối hoặc rollback nếu không thể lưu.

Với đường chuyển tiếp bất đồng bộ đã có dữ liệu bền, collector tạm lỗi có thể cho phép xử lý tiếp trong giới hạn buffer, thời gian và dung lượng đã xác định. Phải phân biệt collector chưa nhận với việc hệ thống không còn khả năng giữ bằng chứng mới.

Bộ test cần lấy expected từ hợp đồng của thao tác. Không mặc định tắt mọi chức năng khi log lỗi, cũng không mặc định bỏ audit bắt buộc để tiếp tục cấp đặc quyền.

### 9.2. Các lỗi nên mô phỏng

| Lỗi | Assertion quan trọng |
| --- | --- |
| Không ghi được điểm lưu bền bắt buộc | Không có thay đổi đặc quyền thiếu bằng chứng theo hợp đồng |
| Collector không đáp ứng | Retry và queue có giới hạn, có quan sát backlog |
| Hết dung lượng/pool | Hành vi quá tải rõ ràng, không làm rơi event âm thầm |
| Serializer lỗi ở một field | Không dump raw payload nhạy cảm vào fallback log |
| Một event bị lỗi lặp | Không chặn vô hạn mọi event khác; có trạng thái điều tra được |
| Chứng thư/kết nối collector không hợp lệ | Không tự chuyển sang endpoint hoặc kênh không đáng tin |

Một cảnh báo lỗi pipeline chỉ được gửi vào chính pipeline đang hỏng có thể không đến được ai. Cần kiểm tra đường quan sát lỗi phù hợp và có giới hạn, không tạo vòng lặp log lỗi sinh thêm log lỗi vô hạn.

## 10. Dữ liệu nhạy cảm và log injection

### 10.1. Kiểm tra theo giá trị bí mật, không chỉ theo tên field

Dùng các giá trị giả lập riêng làm sentinel trong môi trường thử, đặt chúng vào credential hoặc phần dữ liệu không được phép ghi. Sau thao tác, kiểm tra chúng không xuất hiện nguyên dạng trong audit, error log, trace hoặc dead-letter payload thuộc phạm vi test.

Không chỉ tìm field tên `password`, vì secret có thể bị nhúng trong URL, thông báo lỗi hoặc chuỗi mô tả. Ngược lại, event type `password_reset_requested` có thể hợp lệ dù chứa từ “password”; assertion cấm từ khóa chung dễ tạo kết quả sai.

Không đưa mật khẩu thật, token người dùng thật, MFA seed hoặc khóa riêng thật vào bộ test. Sentinel phải có thể nhận diện mà không có khả năng truy cập tài nguyên thực.

### 10.2. Đầu vào không được tạo sự kiện giả

Kiểm tra các field có nguồn từ client, chẳng hạn tên hiển thị hoặc mô tả yêu cầu, với ký tự xuống dòng, dấu phân cách, ký tự điều khiển và nội dung dài. Mục tiêu là một đầu vào không thể tách thành nhiều bản ghi, sửa `outcome`, giả mạo actor hoặc phá parser phía collector.

Structured logging không tự loại bỏ mọi rủi ro: serializer, định dạng transport, bước chuyển đổi và giao diện hiển thị đều cần xử lý đúng dữ liệu. Nội dung hiển thị trong trang xem audit cũng không được thực thi như HTML/script do client cung cấp.

Giới hạn kích thước phải giữ được phần ngữ nghĩa bắt buộc. Không cắt một chuỗi JSON giữa chừng rồi làm mất toàn bộ sự kiện, và không để một field quá dài làm che actor, action hoặc outcome trong kết quả tra cứu.

### 10.3. Tối thiểu hóa có mục đích

Chỉ giữ thuộc tính cần để giải thích sự kiện. Có thể dùng tham chiếu thay cho email hoặc toàn bộ hồ sơ, nhưng cần xét khả năng liên kết và quyền truy cập ánh xạ. Dữ liệu đã băm cũng không tự trở thành ẩn danh hoặc hết nhạy cảm.

Với thay đổi quyền, ghi quyền/phạm vi được thêm hoặc gỡ thường hữu ích hơn dump nguyên principal. Với thay đổi credential, ghi loại và tham chiếu credential phù hợp thay vì nội dung bí mật của nó.

## 11. Quyền đọc, ghi, xuất và bảo vệ bằng chứng

### 11.1. Ma trận truy cập audit

| Chủ thể | Hành vi cần thử | Kết quả theo mô hình minh họa |
| --- | --- | --- |
| Người dùng ứng dụng thông thường | Truy vấn audit quản trị | Không được tự động đọc |
| Người xem audit tenant A | Đọc/xuất sự kiện tenant A trong phạm vi được cấp | Chỉ nhận dữ liệu được phép |
| Người xem audit tenant A | Đổi bộ lọc sang tenant B | Không làm lộ sự kiện, thống kê hoặc tệp xuất của B |
| Service phát event | Gửi sự kiện trong namespace được quản lý | Chỉ được phát trong phạm vi cho phép |
| Service phát event | Sửa/xóa sự kiện lịch sử | Không được mặc định có quyền này |
| Quản trị vòng đời lưu trữ | Thực hiện tác vụ đã phê duyệt | Theo quyền và điều kiện lưu giữ được thiết kế |

Ma trận thật phụ thuộc tổ chức. Cần kiểm tra cả API, trang xem, tìm kiếm, aggregation và export; một endpoint chi tiết có kiểm tra tenant không bảo đảm tệp export cũng được lọc đúng.

### 11.2. Tính toàn vẹn có mô hình đe dọa

Nếu hệ thống có cơ chế append-only, chữ ký, MAC, chuỗi băm hoặc checkpoint bên ngoài, test cần nêu loại thay đổi nào phải phát hiện: sửa nội dung, thay actor, xóa event, chèn event hoặc đổi thứ tự trong phạm vi được bảo vệ.

Một checksum lưu cạnh event không tự chống được kẻ có quyền sửa cả event lẫn checksum. Một chuỗi băm cũng không tự chứng minh mọi hành vi thật đều được phát thành sự kiện ở nguồn. Phải xét quyền sửa kho, quyền dùng khóa và nơi neo bằng chứng độc lập.

Không gọi audit là “không thể chối bỏ” chỉ vì có timestamp hoặc chữ ký. Test chỉ chứng minh các thuộc tính trong phạm vi cơ chế và mô hình đe dọa đã kiểm tra; không tự chứng minh người thật đã chủ ý làm mọi thao tác hoặc nguồn chưa từng bị chiếm quyền.

## 12. Mẫu ca test từ thay đổi quyền đến truy vấn audit

```yaml
id: AUDIT_ROLE_GRANT_SUCCESS
initialState:
  actor: tenant_a_role_admin
  target: tenant_a_user_without_course_editor
  resourceScope: course_test_12
operation:
  action: role.grant
  role: course_editor
expected:
  businessChange: committed
  audit:
    eventType: role_assignment_changed
    actor: tenant_a_role_admin
    target: tenant_a_user_without_course_editor
    tenant: tenant_a
    outcome: SUCCESS
    scope: course_test_12
    rawCredentials: absent
  delivery:
    durableRecord: present
    queryableWithin: test_contract_deadline
```

Schema là minh họa dữ liệu ca test, không phải cấu hình chuẩn. Deadline phải là giá trị cụ thể từ hợp đồng của môi trường test, không phải một trạng thái chờ vô thời hạn.

Trình tự thực hiện về mặt thiết kế:

```text
given: fixture, policy và danh tính thử được kiểm soát
given: mốc/namespace test để tách khỏi sự kiện khác
when:  thực hiện thao tác qua đường cần kiểm tra
then:  đọc lại thay đổi nghiệp vụ
then:  xác minh event ở điểm lưu bền cần chứng minh
then:  chờ có giới hạn và truy vấn bằng quyền audit phù hợp
then:  đối chiếu actor, target, scope, outcome và dữ liệu bị cấm
```

Thêm biến thể request không có quyền, transaction rollback, gửi lại cùng event và collector tạm lỗi. Các biến thể phải kiểm tra kết quả riêng, không chỉ thay tên case trong khi vẫn đi cùng một đường happy path.

## 13. Tránh test bất đồng bộ không ổn định hoặc đạt giả

### 13.1. Đối chứng và namespace riêng

Một truy vấn “có event cấp role” có thể đọc nhầm event của test trước hoặc của một worker chạy song song. Gắn ca với request/job reference do test quản lý và dùng dữ liệu tách biệt. Không chỉ lọc theo action chung.

Không phụ thuộc vào một buffer log tĩnh dùng chung mà không có cơ chế cô lập. Actor của ca A và target của ca B xuất hiện trong cùng collector không được xem là một bằng chứng ghép hợp lệ.

### 13.2. Chờ theo điều kiện với thời hạn hữu hạn

Ở lớp có đồng hồ điều khiển được, kiểm tra thời gian và retry bằng clock thử. Ở integration test, chờ điều kiện truy vấn với deadline hữu hạn và báo rõ mốc nào chưa đạt: chưa lưu, chưa gửi, chưa nhận hay chưa index.

Một lần ngủ cố định không chứng minh pipeline đã hội tụ. Hết timeout cũng không nên được ghi đơn giản là “event không tồn tại vĩnh viễn”; nó cho biết chưa đáp ứng điều kiện trong cửa sổ test và cần bằng chứng trạng thái hỗ trợ.

### 13.3. Kiểm tra sự vắng mặt đúng phạm vi

Để khẳng định không có event success sau rollback, cần xác định tập event liên quan và mốc xử lý đã ổn định hoặc checkpoint phù hợp. Truy vấn quá sớm có thể cho kết quả rỗng dù một success sai đang nằm trong queue.

Với pipeline giao lại, kiểm tra tính duy nhất logic theo `event_id` và hợp đồng chống trùng, không yêu cầu số lần truyền vật lý luôn bằng một. Ngược lại, không dùng việc chống trùng để bỏ qua các attempt thật có định danh khác.

## 14. Những lỗi mà bộ test cần phát hiện

- Có dòng log nhưng không có bản ghi bền hoặc không truy vấn được ở đích.
- Actor lấy từ request body, target và actor bị đảo hoặc tenant lấy từ nguồn không đáng tin.
- Ghi success trước commit, sau đó transaction rollback.
- Ghi toàn bộ quy trình đã hoàn tất khi mới tiếp nhận job hoặc gửi lệnh downstream.
- Retry tạo hai thay đổi logic hoặc chống trùng làm mất các lần thử thật.
- Dựa vào thứ tự timestamp nhận để giải thích sai cấp rồi thu hồi quyền.
- Collector lỗi làm mất event âm thầm hoặc kích hoạt vòng lặp log không giới hạn.
- Fallback log và dead-letter queue chứa raw token, secret hoặc toàn bộ hồ sơ.
- Bộ lọc tenant đúng ở trang xem nhưng sai ở tìm kiếm, thống kê hoặc export.
- Tài khoản ghi event có quyền sửa/xóa bằng chứng lịch sử không cần thiết.
- Test đọc nhầm sự kiện cũ, mock mất điểm cần kiểm tra hoặc truy vấn quá sớm.

Audit event test hiệu quả nối trạng thái nghiệp vụ với bằng chứng đúng ngữ nghĩa và có vòng đời rõ ràng. Kiểm tra cả nguồn sự kiện, commit, chuyển tiếp, truy vấn, quyền truy cập và dữ liệu nhạy cảm giúp hệ thống IAM tạo được lịch sử có thể sử dụng để điều tra thay vì chỉ tạo thêm các dòng log.
