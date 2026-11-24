# Email recipient privacy — Bảo vệ quyền riêng tư của người nhận email

## Mục tiêu và phạm vi

Quyền riêng tư của người nhận email là yêu cầu bảo đảm mỗi người chỉ nhận thông tin và nhìn thấy danh tính những người khác trong phạm vi nghiệp vụ cho phép. Danh tính ở đây có thể là địa chỉ email, tên, mã khách hàng, tư cách thành viên của một nhóm hoặc mối liên hệ giữa một người với một sự kiện.

Trong module bảo mật logic nghiệp vụ, vấn đề cần giải quyết là: **ai được gửi, ai được nhận, ai được biết những người nhận khác và quyết định đó còn hợp lệ ở thời điểm gửi hay không**. Một email được tạo đúng cú pháp và gửi thành công vẫn có thể vi phạm các quy tắc này.

Sau bài học, bạn có thể:

- Phân biệt người nhận trong SMTP envelope với địa chỉ hiển thị trong thông điệp.
- Thiết kế business invariants cho thông báo riêng tư và thư cộng tác theo nhóm.
- Kiểm tra quyền theo đối tượng, tenant và mục đích gửi.
- Ràng buộc phê duyệt với đúng phiên bản danh sách người nhận, nội dung và địa chỉ.
- Phối hợp transaction, outbox và idempotency để giảm gửi nhầm khi có thay đổi hoặc retry.
- Xây dựng tình huống kiểm thử lạm dụng logic trên email đã được dựng hoàn chỉnh.

## 1. Vì sao danh sách người nhận là dữ liệu nghiệp vụ nhạy cảm?

Giả sử một nền tảng học tập gửi kết quả xét hỗ trợ học phí cho 600 học viên. Mỗi người được phép biết kết quả của chính mình. Nhân viên vận hành có quyền khởi tạo đợt thông báo, nhưng không có nghĩa học viên được phép biết những ai cũng nộp đơn hỗ trợ.

Nếu hệ thống đặt cả 600 địa chỉ vào `To`, người nhận có thể suy ra danh sách người đã tham gia quy trình hỗ trợ học phí. Nếu hệ thống dùng `Bcc` nhưng đính kèm bảng tổng hợp 600 hồ sơ, thông tin vẫn bị lộ.

Một biến thể khó nhận ra hơn: tất cả email chỉ có một địa chỉ trong `To`, nhưng worker dùng lại dữ liệu template của người trước. Học viên B nhận tiêu đề, tên hoặc liên kết hồ sơ của học viên A. Danh sách người nhận đã được giấu, nhưng quyền nhận nội dung vẫn bị vi phạm.

Các tình huống này có chung nguyên nhân: ứng dụng chưa diễn đạt và kiểm tra đầy đủ quy tắc nghiệp vụ ở ranh giới gửi thư.

Cần phân biệt ba quyền độc lập:

| Quyền | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| Quyền khởi tạo gửi | Chủ thể này có được gửi thông báo cho đối tượng này không? | Nhân viên có quyền gửi kết quả cho hồ sơ thuộc tenant của mình |
| Quyền nhận dữ liệu | Người nhận có được tiếp cận nội dung và tài liệu trong thư không? | Chủ hồ sơ được xem kết quả của chính mình |
| Quyền biết danh tính người khác | Người nhận có được biết những ai khác cũng nhận thư không? | Thành viên nhóm dự án có thể được phép thấy các thành viên đã tham gia nhóm |

Không suy ra quyền thứ ba từ quyền thứ nhất hoặc thứ hai. Một người có quyền nhận thông báo không tự động có quyền nhận danh sách những người nhận khác.

## 2. Phân biệt địa chỉ giao thư và địa chỉ hiển thị

### 2.1. SMTP envelope và nội dung thông điệp

SMTP sử dụng địa chỉ giao thư trong envelope, thông qua lệnh `RCPT TO`. Các trường `To` và `Cc` thuộc nội dung thông điệp. Hai tập địa chỉ này không bắt buộc trùng nhau; vì vậy, kiểm tra riêng `To` chưa đủ để xác định ai thực sự được gửi thư. [RFC 5321, mục 7.2](https://www.rfc-editor.org/rfc/rfc5321.html#section-7.2).

Ví dụ rút gọn của một lần gửi riêng tư:

~~~text
SMTP envelope:
  MAIL FROM:<notifications@platform.example>
  RCPT TO:<an@recipient.example>

Thông điệp:
  From: Learning Platform <notifications@platform.example>
  To: An <an@recipient.example>
  Reply-To: support@platform.example
  Subject: Ket qua ho so cua ban

  Noi dung chi thuoc ho so cua An.
~~~

Ứng dụng cần kiểm tra cả thông điệp lẫn tập người nhận thực tế truyền cho SMTP client hoặc API của nhà cung cấp. Nếu adapter bổ sung `audit@other.example` vào envelope, việc `To` vẫn chỉ chứa An không làm lần gửi đó trở nên hợp lệ.

### 2.2. Bcc có ích nhưng không thay thế chính sách riêng tư

`To` và `Cc` biểu diễn địa chỉ trong thông điệp. `Bcc` phục vụ gửi bản sao mà không tiết lộ địa chỉ theo cách thông thường; RFC cho phép nhiều cách xử lý trường này. Vì vậy, không mặc định mọi thư viện sẽ luôn tạo cùng một bản thư cho người nhận Bcc. Cần kiểm tra thông điệp sau khi dựng và hành vi adapter. [RFC 5322, mục 3.6.3](https://www.rfc-editor.org/rfc/rfc5322.html#section-3.6.3).

Trong thiết kế của bài này, thông báo riêng tư cho những người không cần biết nhau được gửi thành **các thông điệp độc lập**, mỗi thông điệp có một người nhận trực tiếp. Đây là lựa chọn chính sách của ứng dụng.

Bcc không giải quyết được:

- Gửi đến người không có quyền nhận nội dung.
- Lộ danh sách trong body, attachment, tiêu đề hoặc header tùy biến.
- Dùng chung liên kết truy cập có quyền của người khác.
- Lộ dữ liệu qua log, dashboard của nhà cung cấp hoặc trang xem thư trên web.
- Nhà cung cấp giao thư và các bên vận hành có quyền truy cập dữ liệu xử lý.

Không xem Bcc là mã hóa hoặc sự ẩn danh tuyệt đối. Với dữ liệu quá nhạy cảm để đưa vào email, có thể gửi thông báo tối thiểu và yêu cầu đăng nhập vào ứng dụng để xem chi tiết.

## 3. Biến yêu cầu riêng tư thành business invariants

### 3.1. Mô hình hóa các tập dữ liệu cần bảo vệ

Với một lần gửi `d`:

- `R_env(d)`: tập địa chỉ thực tế được adapter yêu cầu giao thư.
- `r(d)`: chủ thể nghiệp vụ dự kiến nhận thông báo.
- `V(d)`: thông tin nhận diện người nhận mà người đọc có thể quan sát qua thông điệp, file đính kèm và tài nguyên liên quan.
- `A(r, object, purpose)`: tập thông tin nhận diện được phép tiết lộ cho chủ thể `r` trong ngữ cảnh cụ thể.

Bất biến tổng quát:

~~~text
V(d) ⊆ A(r(d), object(d), purpose(d))
~~~

Đây là mô hình phân tích, không phải thuật toán tìm chuỗi email trong body. Danh tính có thể xuất hiện dưới dạng mã hồ sơ, tên file hoặc URL, nên việc thực thi phải bắt đầu từ chính sách và nguồn dữ liệu.

Đối với chế độ `PRIVATE_INDIVIDUAL` trong ví dụ:

~~~text
R_env(d) = {địa chỉ đã được cho phép của r(d), tại phiên bản đã kiểm tra}
To(d)    = {cùng địa chỉ đó}
Cc(d)    = ∅
Bcc(d)   = ∅
~~~

Các quy tắc này áp dụng cho thông báo cá nhân của ví dụ. Thư nhóm có thể có nhiều người nhận, nhưng phải tuân theo chính sách tiết lộ danh tính riêng.

### 3.2. Những bất biến cần có trong dịch vụ gửi

| Bất biến | Cách diễn đạt có thể kiểm tra |
| --- | --- |
| Đúng tenant | Hồ sơ, người nhận, sự kiện và quyền gửi đều thuộc tenant được xác thực |
| Đúng đối tượng | Người nhận có quan hệ được phép với hồ sơ, ví dụ chủ sở hữu hoặc người đại diện hợp lệ |
| Đúng mục đích | Địa chỉ và loại thông báo được phép dùng cho mục đích gửi cụ thể |
| Đúng mức tiết lộ | Danh tính trong mọi phần của thư nằm trong phạm vi người nhận được phép biết |
| Đúng nội dung cá nhân | Dữ liệu template, attachment và liên kết đều thuộc đúng người nhận và đối tượng |
| Đúng phê duyệt | Phiên bản nội dung, tập người nhận và chính sách gửi khớp bản đã duyệt |
| Đúng thời điểm | Các điều kiện có thể bị thu hồi được kiểm tra tại ranh giới dispatch đã định nghĩa |
| Không mở rộng khi retry | Retry giữ nguyên lần gửi logic, đích nhận và phiên bản nội dung đã đóng băng |

Địa chỉ đã xác minh chỉ chứng minh một điều kiện về địa chỉ theo quy trình xác minh của ứng dụng. Nó không tự chứng minh người đó có quyền nhận một hóa đơn, một hồ sơ hỗ trợ hoặc một tài liệu cụ thể.

### 3.3. Chính sách phải phân biệt các mục đích gửi

| Tình huống | Chính sách phù hợp trong ví dụ | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Kết quả hồ sơ cá nhân | `PRIVATE_INDIVIDUAL` | Mỗi thư một người, dữ liệu riêng cho đúng hồ sơ |
| Mời tham gia nhóm kín | Thư riêng cho từng người được mời | Không lộ danh sách người được mời trước khi chính sách cho phép |
| Thảo luận nhóm dự án | `VISIBLE_GROUP` | Thành viên được phép thấy nhau và nhận nội dung cuộc thảo luận |
| Thông báo diện rộng cho khách hàng | Các thư riêng; Bcc chỉ khi chính sách đã đánh giá cho phép | Không biến danh sách khách hàng thành dữ liệu công khai |
| Báo cáo nội bộ nhiều khách hàng | Kênh báo cáo có kiểm soát quyền riêng | Người nhận có quyền xem từng phần dữ liệu được tổng hợp |

Chế độ hiển thị người nhận phải do backend suy ra từ loại nghiệp vụ hoặc cấu hình được quản trị. Không cho client tùy ý chuyển thông báo cá nhân sang `VISIBLE_GROUP`.

## 4. Ranh giới tin cậy và các cách lạm dụng logic

### 4.1. Không cho client quyết định tùy ý danh sách đích

Thiết kế dễ bị lạm dụng:

~~~http
POST /api/support-results/send

{
  "applicationId": "application-42",
  "to": ["an@recipient.example"],
  "cc": ["outsider@recipient.example"],
  "tenantId": "tenant-A",
  "privacyMode": "VISIBLE_GROUP"
}
~~~

Nếu backend chỉ kiểm tra nhân viên đã đăng nhập, nhân viên có thể thêm địa chỉ bên ngoài, đổi tenant hoặc chọn chế độ làm lộ danh tính.

API theo ý định nghiệp vụ có thể gọn hơn:

~~~http
POST /api/applications/application-42/notify-result
Idempotency-Key: result-notice-42-v3

{
  "resultVersion": 3
}
~~~

Backend lấy tenant từ ngữ cảnh xác thực, kiểm tra quyền trên hồ sơ, tìm người nhận từ quan hệ nghiệp vụ và chọn chính sách gửi tương ứng. Trường không được hỗ trợ cần bị xử lý theo hợp đồng API; với yêu cầu nhạy cảm, nên từ chối các trường như `cc`, `bcc` hoặc `privacyMode` thay vì âm thầm áp dụng chúng.

Nếu sản phẩm thực sự cho phép thêm người nhận, thao tác đó cần quyền riêng và phải kiểm tra từng người theo đối tượng, mục đích, tenant và giới hạn tiết lộ.

OWASP khuyến nghị từ chối mặc định, kiểm tra quyền trên mỗi yêu cầu và trên đúng đối tượng được truy cập. Áp dụng vào bài toán này, quyền gọi endpoint chưa đủ để quyết định ai được nhận hồ sơ qua email. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#validate-the-permissions-on-every-request).

### 4.2. Những điểm mở rộng người nhận ít được chú ý

- Tùy chọn tự động CC người tạo yêu cầu hoặc người quản lý.
- Địa chỉ lưu trữ thư do adapter, gateway hoặc nhà cung cấp bổ sung.
- Mailing list và alias phân phối lại cho nhiều người.
- Chức năng gửi thử cho phép chọn địa chỉ bất kỳ nhưng dùng dữ liệu thật.
- Nút gửi lại dựng danh sách từ dữ liệu mới thay vì lần gửi đã được duyệt.
- Hệ thống ticket tự động thêm người tham gia khi nhận thư trả lời.
- Trang xem email trên web trả về cả metadata của chiến dịch.

Mỗi nơi có thể tạo thêm người nhận đều là một điểm thực thi chính sách. Nếu cần bản sao phục vụ kiểm toán, phải có mục đích, quyền truy cập và chính sách lưu giữ rõ ràng; không âm thầm nối một mailbox vào mọi thư.

Với mailing list hoặc alias, ứng dụng có thể chỉ biết địa chỉ đầu vào mà không biết tập người nhận cuối cùng. Chính sách cho dữ liệu nhạy cảm phải quyết định có chấp nhận loại đích này hay không. Không tuyên bố rằng một `RCPT TO` bảo đảm chỉ một con người có thể đọc email.

### 4.3. Xác thực địa chỉ không thay thế kiểm tra quyền

Dùng thư viện địa chỉ email để phân tích cú pháp; không tự ghép header từ chuỗi không tin cậy. Hợp đồng nhập một địa chỉ cần từ chối danh sách nhiều mailbox, ký tự CR/LF và dữ liệu không phù hợp với kiểu trường.

Khi chuẩn hóa, không tự áp dụng quy tắc riêng của một nhà cung cấp cho mọi địa chỉ: xóa dấu chấm hoặc phần sau dấu `+` có thể làm thay đổi định danh. Cũng không gộp hai người dùng chỉ vì họ dùng chung mailbox. Danh tính nghiệp vụ và địa chỉ giao thư là hai khái niệm khác nhau.

Quy trình đổi email cần kiểm soát quyền thay đổi, xác minh địa chỉ mới theo chính sách và làm rõ tác động lên các thông báo đang chờ.

## 5. Phê duyệt phải gắn với một phiên bản bất biến

### 5.1. Lỗi “duyệt danh sách A, gửi danh sách B”

Một luồng lỗi điển hình:

1. Người duyệt xem danh sách 100 người thuộc tenant A.
2. Hệ thống ghi `approved = true`.
3. Người tạo sửa bộ lọc hoặc thêm địa chỉ ngoài hệ thống.
4. Worker đọc danh sách hiện tại gồm 101 người rồi gửi.
5. Kiểm tra vẫn thấy `approved = true`, nên chấp nhận gửi.

Bước phê duyệt tồn tại, nhưng không ràng buộc với dữ liệu thực sự được gửi.

Một bản phê duyệt nên gắn với ít nhất:

~~~text
tenantId
businessEventId + eventVersion
purpose
privacyMode
recipientSnapshotId + snapshotVersion
templateVersion + contentSnapshotHash
attachmentManifestVersion
policyVersion
~~~

Snapshot người nhận nên xác định cả chủ thể, địa chỉ đích và phiên bản địa chỉ. Chỉ lưu `recipientId` rồi lấy địa chỉ hiện tại khi gửi có thể tạo ra một đích nhận chưa từng được duyệt.

Fingerprint hoặc hash giúp phát hiện dữ liệu khác bản đã duyệt; nó không tự cấp quyền. Hệ thống vẫn phải bảo vệ snapshot và bắt buộc kiểm tra quyền trước khi tạo hoặc chấp thuận snapshot.

### 5.2. State machine đề xuất

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> REVIEW_READY: Đóng băng nội dung và người nhận
    REVIEW_READY --> APPROVED: Duyệt đúng phiên bản
    APPROVED --> QUEUED: Ghi dispatch và outbox trong transaction
    QUEUED --> DISPATCHING: Claim công việc và kiểm tra điều kiện hiện tại
    DISPATCHING --> PROVIDER_ACCEPTED: Nhà cung cấp xác nhận nhận yêu cầu
    DISPATCHING --> RETRYABLE_FAILURE: Biết chắc chưa được chấp nhận
    RETRYABLE_FAILURE --> QUEUED: Retry cùng dispatch
    DISPATCHING --> UNKNOWN_OUTCOME: Timeout hoặc mất kết nối
    UNKNOWN_OUTCOME --> PROVIDER_ACCEPTED: Đối soát xác nhận đã nhận
    UNKNOWN_OUTCOME --> QUEUED: Xác định có thể retry an toàn
    REVIEW_READY --> NEEDS_REVIEW: Có thay đổi cần duyệt
    APPROVED --> NEEDS_REVIEW: Snapshot hoặc chính sách thay đổi
    QUEUED --> NEEDS_REVIEW: Điều kiện gửi không còn hợp lệ
    DISPATCHING --> NEEDS_REVIEW: Bị chặn trước khi gọi nhà cung cấp
    NEEDS_REVIEW --> DRAFT: Tạo phiên bản mới
    QUEUED --> CANCELLED: Hủy trước ranh giới dispatch
~~~

`PROVIDER_ACCEPTED` nghĩa là nhà cung cấp đã nhận yêu cầu gửi. Nó chưa chứng minh email đã vào hộp thư đến hay người dùng đã đọc. Các trạng thái giao thư, trả lại thư và khiếu nại có thể được quản lý riêng.

Khi có thay đổi, không sửa lặng lẽ một dispatch cũ để nó trở thành thư cho người khác. Tạo phiên bản phù hợp và duyệt lại theo chính sách.

### 5.3. Chọn rõ chính sách cho thay đổi trong lúc chờ

Có hai cách thường gặp:

| Cách xử lý | Hành vi | Điều kiện |
| --- | --- | --- |
| Giữ snapshot | Gửi đến đích đã được duyệt | Snapshot vẫn được phép dùng tại thời điểm dispatch |
| Hủy và lập phiên bản mới | Chặn dispatch cũ rồi xét duyệt đích mới | Đổi địa chỉ, thu hồi quyền hoặc thay đổi nội dung cần cập nhật |

Với thông báo riêng tư nhạy cảm trong ví dụ, nếu địa chỉ hoặc quyền nhận thay đổi, worker chuyển sang `NEEDS_REVIEW`. Worker không tự chuyển sang địa chỉ mới, cũng không tiếp tục gửi tới địa chỉ cũ chỉ vì nó có trong snapshot.

## 6. Thiết kế transaction, outbox và idempotency

### 6.1. Transaction bảo vệ ý định gửi trong cơ sở dữ liệu

Trong cùng một transaction:

1. Kiểm tra sự kiện nghiệp vụ đủ điều kiện thông báo.
2. Kiểm tra bản phê duyệt còn khớp phiên bản.
3. Tạo một dispatch cho từng người nhận được phép.
4. Ghi outbox tham chiếu các dispatch đó.
5. Commit.

Email được gửi bởi worker sau commit. Transaction này giúp bản ghi nghiệp vụ và ý định gửi không bị tách rời; nó không rollback được email đã được nhà cung cấp chấp nhận.

Không giữ transaction cơ sở dữ liệu mở xuyên suốt lời gọi SMTP chỉ để tạo cảm giác gửi thư có tính nguyên tử. Lời gọi bên ngoài vẫn có thể thành công trong khi cập nhật trạng thái trong cơ sở dữ liệu thất bại.

### 6.2. Phân biệt khóa idempotency của API và định danh lần gửi

Khóa idempotency của API cần được giới hạn theo tenant, chủ thể hoặc phạm vi hành động thích hợp. Backend lưu fingerprint của yêu cầu: nếu cùng khóa nhưng nội dung khác, trả lỗi xung đột theo hợp đồng thay vì tái sử dụng kết quả cho một người nhận khác.

Một ràng buộc duy nhất cho dispatch nghiệp vụ có thể là:

~~~text
UNIQUE (
  tenant_id,
  business_event_id,
  event_version,
  purpose,
  recipient_principal_id,
  recipient_snapshot_version,
  channel
)
~~~

Đây là ví dụ cho chính sách “một thông báo trên mỗi chủ thể trong mỗi phiên bản sự kiện”. Nếu sản phẩm cần gửi lại có chủ đích, thao tác đó phải tạo ý định nghiệp vụ mới có quyền và giới hạn rõ ràng.

Sau khi tạo dispatch, các lần thử gửi dùng cùng `dispatchId`, cùng đích và cùng nội dung. Nếu nhà cung cấp hỗ trợ idempotency, có thể dùng định danh ổn định này làm khóa theo đúng phạm vi và thời hạn mà nhà cung cấp cam kết.

Không dùng một khóa chung cho toàn bộ chiến dịch khi mỗi người có payload riêng. Không tạo khóa mới ở mỗi lần retry, vì như vậy nhà cung cấp không thể nhận ra đó là cùng một yêu cầu logic.

### 6.3. Retry sau timeout là kết quả không xác định

Tình huống:

1. Worker gửi email cho An.
2. Nhà cung cấp chấp nhận.
3. Kết nối đứt trước khi worker nhận phản hồi.
4. Worker không biết lần gửi đã thành công hay chưa.

Outbox và unique constraint trong cơ sở dữ liệu không tự giải quyết được khoảng trống này. Có thể cần idempotency từ nhà cung cấp, API tra cứu trạng thái hoặc cơ chế đối soát trước khi quyết định retry. Nếu kênh không hỗ trợ, phải thừa nhận rủi ro gửi trùng.

`Message-ID` trong email có thể hỗ trợ theo dõi, nhưng không phải cam kết chống trùng của nhà cung cấp. Không tuyên bố “exactly once” chỉ vì đã tạo một giá trị duy nhất trong hệ thống.

Retry không được dựng lại danh sách chiến dịch, tái sử dụng một đối tượng thư đang bị thread khác sửa, hoặc trộn attachment giữa các dispatch.

### 6.4. Xử lý cạnh tranh với việc thu hồi quyền

Kiểm tra quyền lúc enqueue chưa đủ nếu công việc nằm trong hàng đợi lâu. Worker cần một ranh giới quyết định dispatch có thể kiểm chứng:

- Việc đổi địa chỉ hoặc thu hồi quyền cập nhật phiên bản và vô hiệu hóa các dispatch chưa vượt ranh giới đó.
- Worker dùng cơ chế claim và so sánh phiên bản để quyết định được phép gửi.
- Quy trình thu hồi và claim cần phối hợp bằng khóa, điều kiện cập nhật hoặc cơ chế tuần tự hóa phù hợp.
- Trước lời gọi nhà cung cấp, worker kiểm tra đích, phiên bản và khả năng bị hủy theo hợp đồng đã chọn.

Cần nói rõ giới hạn: sau khi email được chuyển ra ngoài hệ thống, việc thu hồi quyền trong ứng dụng không thu hồi được bản thư đã giao. Ngay cả một lần đọc lại quyền ngay trước lời gọi mạng cũng có một khoảng thời gian cạnh tranh; bảo đảm nghiệp vụ phải xác định thời điểm chấp nhận dispatch và thứ tự với thao tác thu hồi, thay vì hứa “luôn gửi theo quyền mới nhất”.

## 7. Ví dụ Java: chỉ dựng thông điệp từ kế hoạch đã được cấp quyền

### 7.1. Mẫu triển khai gây lộ dữ liệu

~~~java
// Sai với thông báo cá nhân: mọi người đều thấy toàn bộ danh sách.
mail.setTo(allRecipients);
mail.setHtml(renderSummary(allApplications));
mailGateway.send(mail);
~~~

Chuyển `allRecipients` sang Bcc chỉ xử lý một phần bề mặt lộ danh tính. `renderSummary(allApplications)` vẫn chứa hồ sơ của nhiều người.

Một mẫu lỗi khác là dùng một đối tượng mutable chung cho nhiều tác vụ:

~~~java
// Không chia sẻ đối tượng thư đang thay đổi giữa các tác vụ song song.
sharedMail.setTo(currentRecipient.email());
sharedMail.setAttachment(currentRecipient.document());
executor.submit(() -> mailGateway.send(sharedMail));
~~~

Khi tác vụ chạy, `sharedMail` có thể đã mang địa chỉ hoặc attachment của người tiếp theo.

### 7.2. Tạo mô hình hẹp cho thư riêng tư

Đoạn dưới là mã minh họa thiết kế, lược bỏ repository, xử lý lỗi và tích hợp nhà cung cấp. Các kiểu nghiệp vụ biểu diễn dữ liệu backend đã phân giải; chúng không phải DTO nhận trực tiếp từ client.

~~~java
record PrivateDispatchPlan(
        UUID tenantId,
        UUID dispatchId,
        UUID recipientId,
        UUID objectId,
        long recipientSnapshotVersion,
        String destination,
        String templateVersion) {}

record RenderedContent(String subject, String html) {}

record PrivateMessage(
        UUID dispatchId,
        String envelopeRecipient,
        String to,
        String subject,
        String html) {}

PrivateMessage buildPrivateMessage(PrivateDispatchPlan plan) {
    // Kiểm tra tenant, quan hệ với đối tượng, mục đích, phiên bản,
    // đích đã duyệt và điều kiện hiện tại trước ranh giới dispatch.
    dispatchPolicy.requireDispatchable(plan);

    // Bắt buộc truy vấn bằng cả tenant, đối tượng và chủ thể.
    RecipientView view = contentRepository.loadRecipientView(
            plan.tenantId(),
            plan.objectId(),
            plan.recipientId());

    // Context không chứa danh sách người nhận hay toàn bộ hồ sơ chiến dịch.
    RenderedContent content = renderer.render(
            plan.templateVersion(),
            view);

    return new PrivateMessage(
            plan.dispatchId(),
            plan.destination(),
            plan.destination(),
            content.subject(),
            content.html());
}
~~~

Mô hình `PrivateMessage` không có trường CC/BCC hoặc API thêm tùy ý người nhận. Điều này làm giảm khả năng mở rộng đích nhận ngoài ý định của thông báo cá nhân.

Đây chưa phải toàn bộ cơ chế bảo vệ. Adapter vẫn phải dựng header bằng thư viện chuẩn, giới hạn người nhận envelope, kiểm soát các header bổ sung và kiểm tra phiên bản tại thời điểm dispatch theo cơ chế phối hợp đã chọn.

Nếu có attachment, nên tạo manifest gắn với `tenantId`, `objectId`, `recipientId`, phiên bản và định danh nội dung. Không nhận đường dẫn attachment bất kỳ từ client hoặc lấy “file mới nhất” bằng một cache key thiếu định danh người nhận.

### 7.3. Kiểm tra tại ranh giới adapter

Có thể xây dựng một kiểm tra bắt buộc trước khi gọi nhà cung cấp:

~~~java
void enforcePrivateRecipients(
        PrivateDispatchPlan plan,
        Set<String> envelopeRecipients,
        Set<String> to,
        Set<String> cc,
        Set<String> bcc) {

    Set<String> expected = Set.of(plan.destination());

    if (!envelopeRecipients.equals(expected)
            || !to.equals(expected)
            || !cc.isEmpty()
            || !bcc.isEmpty()) {
        throw new PrivacyPolicyViolation(
                "PRIVATE_RECIPIENT_POLICY_VIOLATION");
    }
}
~~~

Trong triển khai thật, các tập trên phải được lấy từ cấu trúc địa chỉ đã phân tích và request cuối cùng mà adapter sẽ gửi, dùng cùng quy tắc so sánh địa chỉ. Không chỉ kiểm tra một DTO rồi cho lớp bên dưới tự thêm người nhận.

Không dùng từ khóa Java `assert` cho quy tắc bắt buộc vì assertion có thể bị tắt. Lỗi chính sách cần chặn lần gửi, ghi sự kiện tối thiểu và đưa công việc vào luồng xử lý phù hợp.

Việc kiểm tra người nhận ở adapter không chứng minh body an toàn. Ranh giới dựng nội dung, attachment và liên kết vẫn phải được kiểm soát độc lập.

## 8. Những kênh rò rỉ ngoài To/Cc/Bcc

### 8.1. Body, attachment và tài nguyên liên quan

Một thư riêng tư có thể lộ người khác qua:

- Tên hoặc mã hồ sơ nằm trong tiêu đề và đoạn preview.
- File CSV chứa danh sách người nhận.
- Tên file, thuộc tính tài liệu, sheet ẩn hoặc trang dư trong báo cáo xuất.
- Ảnh chèn và URL có tham số chứa địa chỉ hoặc mã của người khác.
- Liên kết “xem trên web” dẫn tới trang chiến dịch dùng chung.
- Lịch mời họp hiển thị danh sách người tham dự.

Khi chọn kênh lịch hoặc trang web, phải đánh giá lại chính sách hiển thị riêng của kênh đó. Một email riêng không làm danh sách trên trang đích tự trở thành riêng tư.

Với link xem hồ sơ, dịch vụ đích cần kiểm tra quyền theo đối tượng khi người dùng truy cập. Không xem việc đã nhận email là bằng chứng người đang mở link có quyền. Nếu dùng bearer link, phải chủ động chấp nhận mô hình bất kỳ ai giữ link có thể dùng theo phạm vi và thời hạn đã thiết kế.

### 8.2. Hủy đăng ký và tracking

Link hủy đăng ký hoặc thay đổi tùy chọn cần giới hạn đúng người, đúng mục đích và đúng tenant. Không cho phép thay một `userId` tuần tự trong URL để tác động lên tùy chọn của người khác. Không tái sử dụng token hủy đăng ký làm token đăng nhập hoặc token xem hồ sơ.

Tracking URL và metadata của nhà cung cấp chỉ nên chứa định danh mờ cần thiết. Định danh mờ vẫn có thể là dữ liệu liên kết được; cần kiểm soát ánh xạ, thời hạn lưu và quyền truy cập. Tránh đưa địa chỉ email hoặc danh sách người nhận vào query string.

### 8.3. Reply, reply-all và forward

Với thông báo cá nhân, `Reply-To` nên hướng tới địa chỉ hỗ trợ hoặc luồng phản hồi đã được cấp quyền. Không đặt nó thành một mailing list rộng chỉ để thuận tiện vận hành.

Nếu email trả lời đi vào hệ thống ticket, hệ thống đó phải kiểm tra việc thêm người tham gia, trích dẫn nội dung và đính kèm. Không tự động chuyển cuộc trao đổi riêng thành hội thoại nhóm vì một địa chỉ lạ xuất hiện trong CC của thư đến.

Ứng dụng không thể ngăn người nhận tự chuyển tiếp hoặc chụp lại toàn bộ nội dung email. Vì vậy, giảm dữ liệu trong thư và đặt tài liệu nhạy cảm sau kiểm tra quyền là những lựa chọn hữu ích khi yêu cầu nghiệp vụ cần kiểm soát chặt hơn.

### 8.4. Log, preview, cache và webhook

| Bề mặt | Lỗi thường gặp | Kiểm soát cần có |
| --- | --- | --- |
| Log và trace | Ghi toàn bộ request gửi thư hoặc HTML đã render | Ghi dispatch ID, trạng thái và mã lý do; che dữ liệu cần thiết |
| Preview và gửi thử | Cho người xem chiến dịch truy cập mọi bản cá nhân | Kiểm tra quyền xem nội dung, dùng dữ liệu giả cho thử template |
| Cache | Khóa chỉ gồm template ID nên trả nhầm nội dung | Cache template độc lập; nếu cache bản cá nhân, dùng đủ ngữ cảnh và chính sách lưu |
| Queue hoặc dead-letter queue | Payload chứa danh sách, token và attachment | Giảm payload, giới hạn quyền worker và vận hành, có thời hạn lưu |
| Webhook | Tin vào tenant ID hoặc địa chỉ trong sự kiện tùy ý | Xác minh nguồn, chống phát lại theo hợp đồng và đối chiếu message ID với dispatch nội bộ |
| Dashboard nhà cung cấp | Nhân viên mọi tenant xem chung dữ liệu | Giới hạn quyền và khả năng tra cứu theo mô hình vận hành |
| API lịch sử gửi | Trả về toàn bộ recipient list cho người chỉ xem được trạng thái | Tách quyền xem trạng thái với quyền xem danh tính và nội dung |

Che một phần email chỉ là giảm lộ dữ liệu, không tự biến dữ liệu thành vô danh. Hash email thông thường cũng có thể bị dò bằng danh sách địa chỉ có sẵn. Nếu cần định danh phục vụ đối soát, cân nhắc ID nội bộ hoặc HMAC có quản lý khóa và vẫn áp dụng kiểm soát truy cập.

## 9. Kiểm thử theo tình huống tấn công logic

### 9.1. Quan sát sản phẩm cuối cùng của pipeline

Kiểm thử chỉ nhìn vào `EmailRequest` đầu vào dễ bỏ sót lỗi do template, adapter và cấu hình gateway tạo ra. Một mail sink hoặc transport giả có thể thu thập:

- Tập envelope recipient hoặc các trường nhận trong request gửi cuối cùng.
- Header và toàn bộ MIME đã serialize.
- Body HTML, plain text, attachment và tài nguyên liên quan.
- Liên kết, metadata và khóa idempotency gửi cho nhà cung cấp.
- Dispatch ID, snapshot version và các lần thử gửi.

Nếu nhà cung cấp tự bổ sung footer hoặc biến đổi nội dung, cần kiểm tra thêm bằng cấu hình thử nghiệm tương đương. Dùng địa chỉ và dữ liệu giả, không gửi tình huống tấn công vào người dùng thật.

### 9.2. Ma trận tình huống quan trọng

| Tình huống thử | Kết quả cần có |
| --- | --- |
| Nhân viên tenant A yêu cầu gửi hồ sơ của tenant B | Bị từ chối, không có dispatch hợp lệ hoặc lần gửi ra ngoài |
| Thêm `cc`, `bcc` hoặc đổi chế độ bằng request thủ công | Không mở rộng người nhận; yêu cầu bị xử lý theo hợp đồng chặt chẽ |
| Thư riêng cho A và B có dữ liệu đánh dấu khác nhau | Bản gửi cho A không chứa dữ liệu, attachment hoặc token của B và ngược lại |
| Chuyển danh sách từ To sang Bcc nhưng giữ bảng tổng hợp | Kiểm thử nội dung vẫn phát hiện vi phạm |
| Adapter tự thêm mailbox lưu trữ | Kiểm tra chính sách chặn đích ngoài tập được phép |
| Sửa danh sách hoặc template sau phê duyệt | Bản duyệt không còn hợp lệ; không gửi phiên bản thay đổi |
| Đổi địa chỉ sau enqueue | Áp dụng chính sách snapshot; ví dụ này yêu cầu xét lại |
| Thu hồi quyền trước ranh giới dispatch | Dispatch bị chặn theo thứ tự phối hợp đã định nghĩa |
| Chạy nhiều worker cho cùng dispatch | Claim và cơ chế idempotency không tạo các ý định gửi độc lập |
| Timeout sau khi nhà cung cấp đã nhận | Chuyển kết quả không xác định; đối soát hoặc retry với bảo đảm đã thiết kế |
| Dùng lại idempotency key với payload khác | Trả lỗi xung đột, không đổi người nhận của dispatch cũ |
| Tái sử dụng đối tượng thư hoặc cache giữa A và B | Không có nội dung chéo người nhận |
| Sửa ID trong link xem hồ sơ hoặc hủy đăng ký | Không truy cập hay thay đổi đối tượng ngoài phạm vi cho phép |
| Gửi thử tới mailbox bên ngoài bằng dữ liệu thật | Bị chặn nếu chưa có quyền nhận dữ liệu đó |
| Gửi thư vào ticket với người lạ trong CC | Không tự cấp quyền tham gia hoặc làm lộ lịch sử hội thoại |

Một phép thử hữu ích là đặt các giá trị mồi như `PRIVATE_MARKER_A` và `PRIVATE_MARKER_B` vào dữ liệu giả. Kiểm tra chúng trong MIME, attachment và trang đích giúp phát hiện trộn ngữ cảnh. Đây chỉ là kỹ thuật kiểm thử; tìm chuỗi mồi không thay thế việc kiểm tra quyền và nguồn dữ liệu trong sản phẩm thật.

Đối với property-based testing, có thể sinh nhiều tổ hợp người nhận, tenant, trạng thái phê duyệt và thứ tự retry. Thuộc tính cần giữ là: mỗi dispatch chỉ mang dữ liệu được phép cho chủ thể của nó và không tự mở rộng tập đích trong mọi thứ tự xử lý được hỗ trợ.

## 10. Vận hành và xử lý sự cố lộ người nhận

Các tín hiệu hữu ích gồm số lần chặn vì sai tập đích, snapshot hết hiệu lực, yêu cầu mở rộng CC/BCC, tỷ lệ gửi trùng và công việc bị kẹt ở `UNKNOWN_OUTCOME`. Không đưa nguyên danh sách email vào metric label hoặc thông báo cảnh báo.

Nếu phát hiện lộ danh tính:

1. Tạm dừng chiến dịch và các dispatch chưa vượt ranh giới gửi; chặn retry tự động liên quan.
2. Xác định các message ID, dispatch, phiên bản nội dung và tập người thực tế đã được yêu cầu giao.
3. Kiểm tra cả header, body, attachment, trang xem thư và log; không chỉ kiểm tra To/Cc.
4. Thu hồi token hoặc quyền trang đích nếu có thể, đồng thời giữ chứng cứ trong phạm vi truy cập cần thiết.
5. Thực hiện quy trình xử lý sự cố và thông báo đã được tổ chức xác định.
6. Sửa đường mở rộng người nhận hoặc trộn nội dung, rồi xác minh bằng tình huống tái hiện trước khi tiếp tục gửi.

Không dựa vào chức năng thu hồi email để bảo đảm người nhận không còn bản sao. Khi lập báo cáo sự cố, phân biệt rõ thư đã được yêu cầu giao, thư được nhà cung cấp chấp nhận và thư có bằng chứng giao thành công.

## 11. Quy tắc thiết kế cần ghi nhớ

- Cấp quyền nhận nội dung và quyền biết danh tính người nhận khác là hai quyết định riêng.
- Mỗi loại thông báo cần chính sách rõ ràng về đích nhận, dữ liệu và mức hiển thị.
- Thông báo cá nhân nên được dựng bằng ngữ cảnh riêng và một kế hoạch gửi không thể bị client mở rộng tùy ý.
- Bản phê duyệt phải gắn với phiên bản nội dung, danh sách và địa chỉ thực sự được gửi.
- Outbox bảo vệ ý định gửi trong transaction; idempotency và đối soát xử lý các lần thử ở ranh giới nhà cung cấp.
- Kiểm thử phải quan sát thông điệp cuối cùng và đích giao thực tế, đồng thời kiểm tra attachment, link, log và luồng phản hồi.

Quyền riêng tư của người nhận được giữ khi toàn bộ đường đi từ ý định nghiệp vụ đến đích giao thư cùng tuân theo một chính sách có thể kiểm chứng. Một checkbox “ẩn người nhận” chỉ là một phần nhỏ của đường đi đó.
