# JWT trong tác vụ nền, hàng đợi và yêu cầu xử lý kéo dài

## 1. Vì sao ranh giới dịch vụ làm thay đổi cách sử dụng JWT?

Trong một request đồng bộ, client gửi access token đến API, resource server xác minh token, kiểm tra quyền rồi trả kết quả. Request thường kết thúc trong thời gian ngắn và token được sử dụng trong đúng ngữ cảnh mà nó được cấp.

Với tác vụ nền (background job), hàng đợi (message queue) hoặc yêu cầu xử lý kéo dài (long-running operation), vòng đời công việc có thể dài hơn nhiều so với vòng đời access token. Request ban đầu có thể được chấp nhận lúc 10:00, message chỉ được worker xử lý lúc 10:20, và công việc có thể tiếp tục đến 11:00. Trong thời gian đó:

- Access token ban đầu có thể đã hết hạn.
- Quyền của người dùng có thể đã bị thu hồi hoặc thay đổi.
- Worker có thể chạy dưới một danh tính dịch vụ khác với người dùng khởi tạo.
- Message có thể được retry, phát lại hoặc chuyển sang dead-letter queue.
- Job có thể đi qua nhiều dịch vụ và nhiều ranh giới tin cậy.
- Kết quả có thể được tạo ra sau khi phiên đăng nhập ban đầu đã kết thúc.

Vì vậy, không thể xem JWT nhận ở HTTP request là giấy phép có hiệu lực vô thời hạn cho mọi worker xử lý phía sau. Cần xác định rõ **ai khởi tạo công việc, dịch vụ nào thực thi, quyền nào đã được cấp, quyền được đánh giá tại thời điểm nào và công việc còn được phép chạy đến khi nào**.

JWT vẫn có thể tham gia vào kiến trúc bất đồng bộ, nhưng phải dùng đúng loại token, đúng audience, đúng mục đích và đúng thời hạn. Message queue cũng cần cơ chế xác thực, phân quyền, bảo vệ toàn vẹn, chống phát lại và kiểm soát retry riêng.

## 2. Phân biệt danh tính người khởi tạo và danh tính worker

Một job thường có ít nhất hai chủ thể:

| Chủ thể | Vai trò | Ví dụ |
| --- | --- | --- |
| Initiating subject | Người dùng hoặc client yêu cầu tạo job | Người dùng yêu cầu xuất báo cáo |
| Executing workload | Dịch vụ/worker thực thi job | Worker tạo file báo cáo |

Hai danh tính này không nên bị nhập làm một. Worker là tiến trình đang thực hiện công việc; người dùng là chủ thể khởi tạo hoặc được đại diện trong công việc.

Ví dụ:

~~~text
Người dùng Alice
    |
    | Access token dành cho API Reports
    v
Reports API
    |
    | Xác minh token, kiểm tra quyền tạo báo cáo
    | Tạo job J-2048
    v
Message Queue
    |
    | Worker lấy job
    v
Report Worker
    |
    | Danh tính workload: report-worker
    | Actor ban đầu: Alice
    v
Storage / Data API
~~~

Khi worker gọi Data API, Data API cần biết request đến từ workload nào và công việc đang được thực hiện thay mặt ai. Nếu chỉ chuyển tiếp tên người dùng trong một trường JSON, trường đó có thể bị giả mạo. Nếu worker dùng access token của Alice cho mọi dịch vụ, token có thể sai audience hoặc bị lưu trữ quá lâu.

Một mô hình tốt giữ riêng:

- **Actor/subject:** người dùng hoặc client khởi tạo.
- **Workload identity:** dịch vụ đang thực thi.
- **Delegation context:** quyền mà workload được phép sử dụng thay mặt actor, nếu có.
- **Job identity:** định danh duy nhất của công việc.
- **Resource context:** tenant, tài nguyên và thao tác cụ thể mà job được phép thực hiện.

Không phải job nào cũng cần ủy quyền người dùng. Job bảo trì hoặc tác vụ hệ thống có thể chỉ dùng workload identity với quyền dịch vụ giới hạn. Job truy cập dữ liệu riêng của người dùng thường cần giữ ngữ cảnh actor và quy tắc ủy quyền tương ứng.

## 3. Vì sao không nên đưa nguyên access token của request vào queue?

Một cách làm dễ triển khai nhưng rủi ro là đưa nguyên chuỗi bearer access token vào message để worker dùng lại sau này. Cách này tạo ra nhiều vấn đề.

### 3.1. Token có thể hết hạn trước khi worker xử lý

Access token thường có thời hạn ngắn. Message có thể nằm trong queue do tải cao, broker tạm dừng, consumer lỗi hoặc lịch xử lý theo batch. Khi worker nhận message, token có thể đã hết hạn.

Không được bỏ qua kiểm tra exp chỉ vì token được chấp nhận ở API lúc job được tạo. Việc token còn hiệu lực tại thời điểm submit không tự động làm token còn hiệu lực tại thời điểm execute.

### 3.2. Audience có thể không phù hợp

Access token được cấp cho API tiếp nhận request có thể có audience là API đó. Worker gọi một dịch vụ khác cần token có audience phù hợp với dịch vụ đích.

Chuyển tiếp token sang một API không nằm trong aud có thể bị từ chối. Nếu API đích chấp nhận token chỉ vì cùng issuer mà không kiểm tra audience, hệ thống có thể gặp lỗi confused deputy hoặc token substitution.

### 3.3. Queue làm tăng thời gian và nơi lưu giữ bí mật

Message có thể được lưu trên disk, replicate giữa broker, ghi vào log, backup, tracing, dead-letter queue hoặc công cụ quan sát. Nếu message chứa bearer token, mọi thành phần có quyền đọc message đều có thể lấy credential để gọi API.

Token trong queue cũng có thể tồn tại lâu hơn dự kiến do retention, retry hoặc xử lý thủ công. Điều này mở rộng phạm vi ảnh hưởng khi broker, log hoặc tài khoản vận hành bị xâm phạm.

### 3.4. Retry có thể phát lại token và hành động

Queue thường cung cấp cơ chế giao message ít nhất một lần (at-least-once delivery). Một message có thể được giao lại khi worker không xác nhận, timeout hoặc mất kết nối. Nếu worker thực hiện side effect trước khi ACK, cùng token có thể được dùng lại nhiều lần.

### 3.5. Token của người dùng không phải credential của worker

Worker có vòng đời và quyền vận hành riêng. Dùng token người dùng làm credential lâu dài khiến quyền của worker phụ thuộc vào phiên đăng nhập, refresh policy và trạng thái tài khoản của người dùng theo cách khó kiểm soát.

**Nguyên tắc khuyến nghị: queue mang định danh job và ngữ cảnh ủy quyền tối thiểu; worker xác thực bằng workload identity và lấy quyền cần thiết theo cơ chế được thiết kế.** Chỉ chuyển token khi có nhu cầu rõ ràng, audience/profile phù hợp và cách bảo vệ vòng đời token được xác định.

## 4. Chọn mô hình ủy quyền cho job

Không có một mô hình duy nhất. Cần quyết định quyền được đánh giá khi submit, khi execute hay tại các checkpoint trong quá trình chạy.

### 4.1. Mô hình authorization snapshot tại thời điểm submit

API tiếp nhận xác minh token và kiểm tra người dùng có quyền yêu cầu công việc. Sau đó, hệ thống lưu một quyết định được giới hạn rõ:

- Actor nào đã yêu cầu job.
- Hành động cụ thể đã được chấp thuận.
- Tài nguyên/tenant nào nằm trong phạm vi.
- Các tham số ảnh hưởng đến quyền.
- Phiên bản policy hoặc thông tin audit cần thiết.
- Job được phép bắt đầu/chạy đến thời điểm nào.

Worker thực thi quyết định đã được ghi nhận, trong phạm vi job và các ràng buộc được phê duyệt.

Mô hình này phù hợp khi yêu cầu có ý nghĩa như một lệnh đã được chấp thuận tại thời điểm submit, ví dụ tạo một báo cáo từ tập dữ liệu đã được xác định.

**Đánh đổi:** nếu quyền người dùng bị thu hồi sau khi job được tạo, job vẫn có thể tiếp tục theo quyết định snapshot. Điều này phải là hành vi có chủ đích, có giới hạn và có khả năng audit.

Snapshot không nên là bản sao nguyên vẹn của mọi role/permission trong access token. Hãy lưu quyết định tối thiểu cho đúng thao tác, resource và phạm vi. Nếu lưu claims quyền rộng rồi để worker tự suy diễn, snapshot có thể trở thành một credential dài hạn khó thu hồi.

Snapshot cũng không nên vô hiệu hóa các lệnh dừng khẩn cấp. Hệ thống cần định nghĩa các điều kiện override như tài khoản bị khóa do sự cố, tenant bị đình chỉ, tài nguyên bị phong tỏa hoặc job bị thu hồi bởi quản trị viên. Khi có điều kiện override, job phải dừng tại checkpoint an toàn dù quyết định ban đầu vẫn còn trong thời hạn.

### 4.2. Mô hình re-authorize tại thời điểm execute

Worker hoặc một authorization service kiểm tra quyền hiện tại khi bắt đầu xử lý. Nếu người dùng đã bị khóa, quyền truy cập bị thu hồi hoặc tài nguyên đổi chủ, job có thể bị từ chối.

Mô hình này phù hợp với:

- Job có thể chờ lâu trước khi thực thi.
- Tác vụ truy cập dữ liệu nhạy cảm.
- Thao tác có hậu quả lớn hoặc khó đảo ngược.
- Chính sách yêu cầu quyền phải còn hiệu lực tại thời điểm hành động.

**Đánh đổi:** job có thể thất bại dù người dùng đã có quyền hợp lệ khi gửi yêu cầu. Hệ thống cần trạng thái rõ như authorization_denied, thông báo phù hợp và chính sách retry không lặp vô hạn.

### 4.3. Mô hình hybrid: snapshot cộng kiểm tra lại

Nhiều hệ thống dùng quyết định snapshot để giữ ý định ban đầu, đồng thời kiểm tra lại các điều kiện nhạy cảm trước khi thực hiện side effect:

1. Submit: xác minh actor và tạo job trong phạm vi quyền được chấp thuận.
2. Execute: xác minh workload, job integrity và điều kiện job còn hiệu lực.
3. Trước side effect quan trọng: kiểm tra lại trạng thái tài khoản, tenant, ownership hoặc policy hiện hành.
4. Commit: ghi nhận kết quả và trạng thái idempotency nguyên tử.

Ví dụ, một job xuất báo cáo có thể được phép tiếp tục tạo file tạm sau khi người dùng gửi yêu cầu, nhưng trước khi công bố file hoặc cấp đường dẫn tải, hệ thống kiểm tra lại quyền truy cập hiện tại.

### 4.4. So sánh các mô hình

| Mô hình | Thời điểm quyết định quyền | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- | --- |
| Snapshot | Lúc submit | Job ổn định dù người dùng đăng xuất | Quyền đã thu hồi có thể không ảnh hưởng job đã duyệt |
| Re-authorize | Lúc execute | Tôn trọng trạng thái quyền hiện tại | Job có thể thất bại sau thời gian chờ |
| Hybrid | Submit và checkpoint | Cân bằng ý định ban đầu với policy hiện tại | Nhiều trạng thái và quy tắc cần quản lý |

Không chọn snapshot chỉ vì worker không tiện gọi authorization service. Cũng không re-authorize một cách máy móc nếu nghiệp vụ yêu cầu hoàn tất lệnh đã được chấp thuận. Quy tắc phải xuất phát từ ý nghĩa nghiệp vụ và mức độ rủi ro.

## 5. Các cách cung cấp quyền cho worker

### 5.1. Workload identity với quyền dịch vụ giới hạn

Worker xác thực với dịch vụ đích bằng danh tính workload riêng, chẳng hạn client credentials hoặc cơ chế workload identity của nền tảng. Quyền của worker chỉ bao gồm các thao tác cần để thực thi loại job đó.

Ví dụ:

- report-worker chỉ được đọc dữ liệu đã được job cho phép và ghi file báo cáo vào vùng lưu trữ riêng.
- invoice-worker chỉ được tạo hóa đơn từ đơn hàng đã ở trạng thái đủ điều kiện.
- cleanup-worker chỉ được xóa dữ liệu theo retention policy.

Không cấp một token quản trị tổng quát cho mọi worker chỉ để tránh phải thiết kế authorization theo job.

Nếu worker dùng client credentials, access token được cấp cho workload và resource/audience cụ thể. Token này đại diện cho client/workload, không tự mang quyền của người dùng khởi tạo.

### 5.2. Delegated token hoặc token exchange

Nếu worker cần gọi dịch vụ thay mặt người dùng, hệ thống có thể dùng một cơ chế delegation được authorization server hỗ trợ. OAuth Token Exchange theo RFC 8693 là một ví dụ.

Mô hình khái quát:

1. API tiếp nhận xác minh access token của người dùng.
2. API tạo job với actor và phạm vi được chấp thuận.
3. Worker xác thực bằng workload identity.
4. Worker hoặc broker tin cậy yêu cầu authorization server cấp token mới cho audience/resource đích, kèm ngữ cảnh delegation được phép.
5. Token mới có thời hạn và scope hẹp, phù hợp với dịch vụ cần gọi.

Token exchange không tự động hợp pháp hóa mọi delegation. Authorization server phải kiểm tra subject token, actor/client, audience, requested scope và policy. Resource server cần hiểu đúng claims/profile thể hiện subject và actor.

Token exchange thường phải xác minh subject token theo chính sách của authorization server, bao gồm trạng thái và thời hạn. Nếu job chỉ bắt đầu sau khi access token ban đầu đã hết hạn, worker không thể dùng token đó như một bằng chứng còn hiệu lực; trường subject trong message cũng không thay thế subject token. Với job cần chạy sau thời điểm đó, hệ thống có thể tạo một job authorization grant/reference phía server ngay lúc submit. Grant này phải được ràng buộc với actor, workload/client, job ID, resource, scope, deadline và policy; worker xác thực bằng workload identity rồi yêu cầu cấp delegated token theo grant. Đây là cơ chế do hệ thống thiết kế, không phải hành vi tự động được RFC 8693 bảo đảm. Grant phải có thể thu hồi và được audit.

Không gửi refresh token của người dùng vào queue để worker tự làm mới access token. Nếu cần quyền kéo dài, hãy dùng một cơ chế delegation/job authorization được thiết kế riêng, có thể thu hồi và audit.

### 5.3. Job-scoped capability

Một lựa chọn khác là cấp một credential hoặc capability chỉ cho một job:

- Được ràng buộc với job ID.
- Chỉ cho phép một tập thao tác cụ thể.
- Chỉ áp dụng cho resource/tenant đã xác định.
- Có audience là worker hoặc API thực thi.
- Có thời hạn tối đa hoặc thời điểm không còn hiệu lực.
- Có thể thu hồi khi job bị hủy hoặc policy thay đổi.

Capability này có thể là JWT theo profile riêng hoặc một reference tra cứu trạng thái phía server. Nếu dùng JWT, chữ ký không làm nó tự one-time-use; server vẫn cần trạng thái khi cần thu hồi, giới hạn số lần sử dụng hoặc kiểm soát tiến trình job.

### 5.4. So sánh lựa chọn

| Mô hình | Dùng khi | Điểm cần kiểm soát |
| --- | --- | --- |
| Workload identity | Job thực hiện công việc thuộc trách nhiệm của dịch vụ | Quyền service tối thiểu và ranh giới resource |
| Delegated token/token exchange | Job thực sự cần quyền thay mặt actor | Subject, actor, audience, scope, expiry và delegation policy |
| Job-scoped capability | Cần quyền hẹp gắn với một job cụ thể | Job binding, TTL, thu hồi, replay và audit |
| Authorization snapshot | Quyền được quyết định tại thời điểm submit | Nội dung quyết định tối thiểu, policy version, expiry và semantics khi quyền đổi |

Các mô hình có thể kết hợp. Ví dụ worker luôn xác thực bằng workload identity, sau đó dùng job-scoped delegated token để gọi một API cụ thể.

## 6. Thiết kế message: truyền ngữ cảnh, không truyền quyền quá rộng

Message nên mang đủ dữ liệu để worker tìm job và xác định ngữ cảnh, nhưng không cần chứa toàn bộ access token hoặc refresh token của người dùng.

Ví dụ một message envelope:

~~~json
{
  "message_id": "msg-7f31",
  "job_id": "job-2048",
  "job_type": "report.generate",
  "initiated_by": {
    "issuer": "https://identity.example.org",
    "subject": "user-42",
    "client_id": "web-client-123"
  },
  "tenant_id": "tenant-17",
  "resource": {
    "type": "account-set",
    "id": "accounts-2026-q4"
  },
  "authorization": {
    "mode": "recheck_at_execution",
    "policy_version": "reports-policy-12"
  },
  "payload_ref": "job-payload-2048",
  "created_at": 1893456000,
  "not_after": 1893463200,
  "correlation_id": "req-98ab"
}
~~~

Đây là ví dụ hợp đồng message do ứng dụng định nghĩa, không phải một schema JWT chuẩn. Message không chứa bearer access token. Worker dùng job_id để lấy payload hoặc trạng thái từ kho dữ liệu được bảo vệ.

### 6.1. Những trường cần được định nghĩa

- message_id: định danh lần phát message, dùng cho deduplication/audit.
- job_id: định danh công việc logic, ổn định qua retry.
- job_type: loại tác vụ worker được phép xử lý.
- initiated_by: actor ban đầu, có issuer namespace rõ ràng.
- tenant_id/resource: phạm vi dữ liệu hoặc tài nguyên.
- authorization.mode: snapshot, recheck hoặc hybrid theo hợp đồng.
- policy_version: phiên bản policy đã áp dụng nếu cần audit.
- payload_ref: tham chiếu đến dữ liệu công việc; không nhúng bí mật không cần thiết.
- created_at và not_after: thời điểm tạo và hạn xử lý của job.
- correlation_id: liên kết log/tracing qua các dịch vụ.

Không tin các trường này chỉ vì chúng xuất hiện trong JSON. Producer phải được xác thực, queue ACL phải giới hạn quyền publish/consume và message phải được bảo vệ toàn vẹn theo threat model. Consumer phải kiểm tra schema, nguồn phát, loại job, trạng thái job và các ràng buộc cần thiết.

### 6.2. Message signature và access-token signature là hai việc khác nhau

Có thể ký message envelope hoặc dùng JWS để bảo vệ tính toàn vẹn của một message đi qua nhiều ranh giới. Nhưng chữ ký message không thay thế access token:

- Chữ ký message xác nhận message được tạo bởi producer/key được tin cậy và không bị sửa theo profile.
- Access token thể hiện quyền truy cập một resource theo issuer/audience/scope.
- Workload authentication xác định dịch vụ đang publish hoặc consume message.
- Authorization quyết định worker có được thực hiện thao tác được nêu trong message hay không.

Nếu dùng JWT làm message envelope, cần profile riêng, audience phù hợp với consumer, thời hạn và quy tắc chống replay. Không dùng một access token cho API làm chữ ký tổng quát của mọi message.

JWS không mã hóa payload. Nếu message chứa dữ liệu nhạy cảm, cần bảo vệ confidentiality bằng mã hóa phù hợp, broker/transport encryption và quyền truy cập kho payload. Không xem việc ký message là che giấu dữ liệu.

## 7. Audience và token profile giữa các dịch vụ

Mỗi dịch vụ nhận token cần xác định token được phát hành cho nó. Ví dụ:

| Thành phần | Token/credential phù hợp |
| --- | --- |
| Public API nhận request | Access token có audience của API |
| Queue broker | Workload credential được broker chấp nhận |
| Report worker | Workload token hoặc delegated token có audience của worker/API dữ liệu |
| Storage API | Token có audience của storage service và quyền ghi đúng vùng |
| Notification service | Token có audience của notification service và scope gửi thông báo phù hợp |

Không chuyển tiếp access token có audience của API A đến API B chỉ vì hai API cùng thuộc một hệ thống hoặc cùng tin một issuer. Mỗi resource server phải xác minh audience và profile riêng.

Nếu worker gọi nhiều dịch vụ, có thể cần nhiều token với audience khác nhau. Token exchange hoặc cấp token theo workload/resource giúp giới hạn quyền ở từng chặng. Tránh một token có audience quá rộng nếu các dịch vụ có ranh giới bảo mật độc lập.

## 8. Token hết hạn khi job còn đang chờ hoặc chạy

Thời hạn token và thời hạn job là hai khái niệm khác nhau:

- **Token expiry:** thời điểm credential không còn được chấp nhận.
- **Job deadline:** thời điểm công việc không còn được phép bắt đầu hoặc hoàn tất theo nghiệp vụ.
- **Lease/visibility timeout:** khoảng thời gian worker tạm giữ quyền xử lý message trước khi queue có thể giao lại.
- **Authorization validity:** khoảng thời gian quyết định quyền hoặc delegation còn được phép áp dụng.

Không kéo dài exp của token cũ hoặc bỏ qua expiration chỉ vì job chưa xong.

### 8.1. Job bắt đầu sau khi access token ban đầu hết hạn

Nếu authorization được snapshot tại thời điểm submit, worker không cần dùng access token ban đầu để xác minh lại. Nó xác minh workload identity, job state và quyết định snapshot được bảo vệ, rồi thực thi trong phạm vi job đã chấp thuận.

Nếu policy yêu cầu re-authorize tại execution, worker phải lấy một quyết định/token mới từ authorization service dựa trên danh tính workload và delegation được phép. Token cũ đã hết hạn không được xem là bằng chứng quyền hiện tại.

### 8.2. Job chạy lâu hơn access token

Một job có thể chạy hàng giờ hoặc nhiều ngày. Không nên giữ access token người dùng trong bộ nhớ hoặc storage rồi tiếp tục dùng sau khi hết hạn. Thay vào đó:

- Dùng workload identity cho các thao tác thuộc trách nhiệm của worker.
- Xin delegated token mới theo policy khi cần gọi dịch vụ thay mặt actor.
- Chia job thành các bước có checkpoint và kiểm tra quyền trước side effect quan trọng.
- Giới hạn thời gian job bằng deadline độc lập.
- Hỗ trợ cancel hoặc revoke theo job/session khi nghiệp vụ yêu cầu.

Việc cấp token mới phải dựa trên nguồn authority tin cậy và policy hiện tại. Không tự phát hành token mới chỉ bằng cách sao chép claims từ token cũ đã hết hạn.

### 8.3. Job đã được chấp thuận có tiếp tục sau logout không?

Logout thường kết thúc phiên đăng nhập hoặc vô hiệu hóa khả năng tiếp tục phiên; nó không mặc nhiên xác định mọi job đã được submit phải dừng. Hệ thống cần quy định semantics:

- Job snapshot có thể tiếp tục vì lệnh đã được chấp thuận trước logout.
- Job delegated theo phiên có thể bị hủy khi session bị revoke.
- Job nhạy cảm có thể phải kiểm tra session/account state tại checkpoint.

Không có đáp án chung. Hãy công bố hành vi, lưu audit và cung cấp cơ chế hủy/thu hồi phù hợp.

## 9. Long-running operation cần trạng thái và checkpoint riêng

Với công việc kéo dài, trạng thái job thường được quản lý ngoài JWT:

~~~text
QUEUED
  |
  v
CLAIMED
  |
  v
RUNNING
  | \
  |  \--> RETRY_WAIT
  |          |
  |          +--> RUNNING
  |
  +--> SUCCEEDED
  |
  +--> FAILED
  |
  +--> CANCEL_REQUESTED
             |
             +--> CANCELLED
             +--> COMPLETED_WITH_WARNING
~~~

JWT có thể xác thực một request hoặc capability, nhưng không nên là nguồn duy nhất lưu trạng thái job. Trạng thái job cần thể hiện:

- Job có còn tồn tại và đang được phép chạy không.
- Worker nào đang giữ lease.
- Job đã thực hiện đến checkpoint nào.
- Job có bị cancel, revoke hoặc quá deadline không.
- Bước nào đã tạo side effect.
- Kết quả đã được commit hay cần retry/compensation.

Worker nên kiểm tra trạng thái tại các checkpoint quan trọng, nhất là trước khi tạo side effect không thể đảo ngược. Không cần gọi authorization service cho mọi dòng xử lý nếu policy không yêu cầu, nhưng phải có điểm kiểm tra phù hợp với rủi ro.

## 10. Queue delivery, retry và chống xử lý trùng

Queue thường ưu tiên độ bền và khả năng giao lại message hơn bảo đảm exactly-once. Worker có thể xử lý message rồi crash trước khi ACK; broker sẽ giao lại. Vì vậy:

- message_id giúp nhận diện bản message.
- job_id giúp nhận diện công việc logic.
- Idempotency key theo bước giúp ngăn side effect bị lặp.
- Job state/checkpoint giúp worker tiếp tục đúng vị trí.

Không dùng jti của access token làm idempotency key cho mọi bước. Một token có thể hợp lệ cho nhiều job và nhiều request. Định danh nghiệp vụ phải gắn với thao tác cụ thể.

### 10.1. Retry an toàn

Một worker nên:

1. Xác thực workload và nguồn message.
2. Kiểm tra message schema, job state và deadline.
3. Kiểm tra message/job đã được xử lý hay chưa.
4. Lấy quyền đúng phạm vi và kiểm tra authorization.
5. Thực hiện một bước với idempotency key ổn định.
6. Lưu kết quả/checkpoint.
7. ACK message sau khi trạng thái cần thiết đã được commit.

Nếu worker timeout sau khi dịch vụ đích đã thực hiện side effect nhưng trước khi worker nhận response, worker phải tra cứu kết quả theo idempotency key hoặc operation ID trước khi thử lại. Gửi lại một lệnh tạo thanh toán mà không biết kết quả lần đầu có thể tạo giao dịch trùng.

### 10.2. Dead-letter queue

Message lỗi lặp lại có thể được chuyển sang dead-letter queue (DLQ). DLQ cần cùng mức bảo vệ hoặc cao hơn queue chính vì message có thể chứa dữ liệu nghiệp vụ và metadata định danh.

- Không để raw access token, refresh token hoặc secret trong DLQ.
- Giới hạn ai có thể đọc, replay hoặc xóa message.
- Lưu lý do thất bại và số lần retry mà không ghi credential.
- Khi replay thủ công, xác minh job còn hợp lệ, authorization còn phù hợp và side effect trước đó đã được đối soát.
- Không coi việc đưa message từ DLQ trở lại queue là một giao dịch mới được tự động cấp quyền.

## 11. Hủy job, thu hồi quyền và thay đổi policy

Job có thể tiếp tục chạy sau khi actor bị khóa, quyền bị thu hồi hoặc tài nguyên đổi trạng thái. Với job nhạy cảm, cần định nghĩa điều kiện dừng:

- Actor/session bị revoke.
- Tenant bị vô hiệu hóa.
- Tài nguyên bị xóa, chuyển chủ sở hữu hoặc đổi trạng thái.
- Delegated token/capability hết hạn hoặc bị thu hồi.
- Job vượt deadline hoặc bị người dùng yêu cầu cancel.
- Policy version mới không còn cho phép hành động.

Một yêu cầu cancel thường là trạng thái bất đồng bộ. API có thể trả cancel_requested; worker dừng ở checkpoint an toàn rồi cập nhật cancelled. Không nên hứa rằng side effect đã gửi đến hệ thống bên ngoài có thể được đảo ngược ngay.

Nếu một job đã tạo side effect không thể đảo ngược, cần quy trình compensation hoặc reconciliation. Ví dụ, nếu lệnh gửi thanh toán đã được chấp nhận ở hệ thống bên ngoài, hủy job nội bộ không đồng nghĩa thanh toán đã bị hủy.

## 12. Bảo vệ dữ liệu và credential trong message

### 12.1. Giảm dữ liệu nhạy cảm

Message nên chứa reference đến payload đã được bảo vệ thay vì nhúng toàn bộ dữ liệu cá nhân hoặc bí mật. Worker chỉ đọc payload sau khi xác thực workload và kiểm tra quyền trên job.

Nếu cần lưu token hoặc delegated credential:

- Ưu tiên lưu server-side trong vault/credential store và chỉ đưa reference vào message.
- Mã hóa khi lưu và giới hạn quyền đọc theo workload/job.
- Đặt TTL và chính sách xóa phù hợp.
- Không lưu refresh token trong message queue.
- Không ghi token vào application log, trace, error report hoặc DLQ.
- Audit mọi lần đọc và sử dụng credential.

Reference đến credential cũng là dữ liệu nhạy cảm nếu nó cho phép truy xuất bí mật. Nó phải có namespace, authorization và khả năng thu hồi.

### 12.2. Bảo vệ message và broker

- Xác thực producer và consumer bằng workload identity.
- Dùng ACL theo topic/queue, không cấp quyền publish/consume toàn broker mặc định.
- Mã hóa kết nối và dữ liệu lưu trữ theo threat model.
- Bảo vệ tính toàn vẹn message nếu broker hoặc trung gian không nằm hoàn toàn trong trust boundary.
- Kiểm tra schema và giới hạn kích thước message.
- Chống replay/deduplication theo message ID và job ID.
- Hạn chế quyền truy cập queue, DLQ, backup và công cụ quản trị.

Chữ ký message có thể giúp xác minh producer nhưng không mã hóa dữ liệu, không bảo đảm message chưa bị phát lại và không thay thế authorization tại worker.

## 13. Audit: giữ được chuỗi actor và workload

Khi một job đi qua nhiều dịch vụ, log chỉ ghi subject hoặc chỉ ghi tên worker sẽ thiếu thông tin. Audit nên liên kết:

| Trường | Ý nghĩa |
| --- | --- |
| job_id | Công việc logic |
| message_id | Lần phát message |
| initiating_issuer + initiating_subject | Người dùng/client khởi tạo |
| client_id | Ứng dụng yêu cầu |
| workload_id | Worker/service thực thi |
| actor/delegation | Danh tính được đại diện nếu có |
| tenant_id + resource_id | Phạm vi dữ liệu |
| authorization_mode | Snapshot, recheck hoặc hybrid |
| policy_version | Policy dùng khi quyết định |
| correlation_id | Liên kết request, message và downstream call |
| operation_id/idempotency_key | Theo dõi side effect |
| result và timestamps | Kết quả, thời gian submit/execute/finish |

Không ghi raw JWT hoặc secret để thuận tiện debug. Có thể ghi issuer, subject đã được chuẩn hóa, kid, jti hoặc fingerprint phù hợp theo chính sách dữ liệu. Log cần chống sửa đổi và giới hạn quyền truy cập.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đưa access token người dùng vào queue | Credential bị lưu ở nhiều nơi và có thể hết hạn | Truyền job context, dùng workload/delegated token phù hợp |
| Worker dùng token của API đầu vào gọi API khác | Sai audience hoặc token confusion | Cấp token theo resource/audience đích |
| Coi tên subject trong JSON là danh tính đã xác minh | Có thể giả mạo actor | Ràng buộc message với producer tin cậy và job record |
| Dùng service account quyền quản trị cho mọi job | Worker vượt quá quyền cần thiết | Workload identity và scope tối thiểu |
| Snapshot toàn bộ roles của người dùng | Quyền rộng tồn tại lâu và khó thu hồi | Lưu quyết định tối thiểu theo job/resource |
| Giả định logout tự hủy mọi job | Job tiếp tục ngoài mong đợi | Định nghĩa semantics session/job và cancellation |
| Re-authorize bằng token đã hết hạn | Bỏ qua vòng đời token | Dùng authorization service hoặc token mới theo policy |
| Ký message rồi bỏ qua queue ACL | Bất kỳ producer nào vẫn có thể gửi message giả | Xác thực producer, ACL và kiểm tra chữ ký/profile |
| Cho rằng chữ ký message bảo vệ bí mật | Payload vẫn có thể bị đọc | Mã hóa và giới hạn quyền truy cập |
| Retry message không có idempotency | Side effect bị lặp | Idempotency theo job/operation/step |
| Replay DLQ mà không kiểm tra quyền | Job cũ có thể chạy với policy mới hoặc dữ liệu đã đổi | Revalidate trạng thái, deadline và authorization |
| Không lưu actor ban đầu | Audit không biết ai yêu cầu hành động | Lưu actor và workload riêng biệt |

## 15. Quy trình tham chiếu cho một job bất đồng bộ

Một luồng tổng quát có thể tổ chức như sau:

~~~text
1. Client gửi request + access token
   |
   v
2. API xác minh token và authorization
   |
   v
3. Tạo job record:
   actor, workload target, resource, policy mode,
   deadline, payload reference, job ID
   |
   v
4. Publish message theo schema đã định
   |
   v
5. Worker xác thực workload và message producer
   |
   v
6. Kiểm tra job state, deadline, deduplication
   |
   v
7. Lấy workload/delegated credential đúng audience
   |
   v
8. Re-authorize hoặc áp dụng snapshot theo policy
   |
   v
9. Thực hiện bước với idempotency key
   |
   v
10. Lưu checkpoint và kết quả
   |
   +--> Retry có kiểm soát nếu cần
   +--> Dừng nếu cancel/revoke/deadline
   |
   v
11. Hoàn tất, audit và thông báo kết quả
~~~

Đây là mô hình tham chiếu, không phải một giao thức bắt buộc. Có hệ thống dùng event bus, workflow engine hoặc scheduler thay queue; các nguyên tắc về identity, authorization, token lifetime, integrity và idempotency vẫn áp dụng.

## 16. Kiểm thử ranh giới dịch vụ và vòng đời job

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Access token hết hạn trước khi worker nhận job | Worker không dùng token cũ như credential còn hiệu lực |
| Token đầu vào có audience của API submit, worker gọi API dữ liệu | Token sai audience bị từ chối; worker lấy credential phù hợp |
| Message bị sửa actor hoặc tenant | Integrity/schema/job binding phát hiện và từ chối |
| Producer không được phép publish topic | Broker từ chối |
| Worker không có workload identity hợp lệ | Không consume hoặc không thực thi job |
| Người dùng bị revoke sau submit trong snapshot mode | Hành vi theo semantics snapshot đã công bố |
| Người dùng bị revoke trước execute trong recheck mode | Authorization bị từ chối |
| Job hết deadline khi còn trong queue | Worker đánh dấu expired và không bắt đầu side effect |
| Cùng message được giao hai lần | Deduplication/job state ngăn thực thi trùng |
| Worker crash sau side effect trước ACK | Retry tra cứu idempotency/operation result trước khi thực hiện lại |
| Job bị cancel giữa hai checkpoint | Worker dừng ở checkpoint an toàn |
| Delegated token có sai audience hoặc scope quá rộng | Từ chối hoặc chỉ cấp token theo policy |
| Token/capability hết hạn giữa job | Worker renew theo authority hợp lệ hoặc dừng an toàn |
| Message chuyển sang DLQ rồi được replay | Kiểm tra lại deadline, authorization và side effect đã có |
| Credential xuất hiện trong log/DLQ | Kiểm thử phát hiện và loại bỏ/redact |
| Actor metadata không có issuer namespace | Không suy diễn danh tính từ subject đơn lẻ |

## 17. Tình huống tự kiểm tra

Alice có quyền tạo báo cáo tài chính tại thời điểm 09:00. API xác minh access token và đưa job vào queue. Do queue quá tải, worker chỉ nhận job lúc 09:30; access token đã hết hạn lúc 09:10. Trong thời gian chờ, quyền của Alice với tenant cũng đã bị thu hồi. Worker cần gọi Data API để lấy dữ liệu và Storage API để ghi báo cáo.

**Câu hỏi 1:** Worker có nên gửi lại access token ban đầu dù token đã hết hạn không?

**Trả lời:** Không. Token đã hết hạn và audience có thể không phù hợp với các API downstream. Worker phải dùng workload identity và cơ chế delegated authorization/job authorization được thiết kế cho công việc.

**Câu hỏi 2:** Worker có được tiếp tục job sau khi quyền của Alice bị thu hồi không?

**Trả lời:** Phụ thuộc semantics đã chọn. Snapshot mode có thể cho phép hoàn tất lệnh đã được duyệt lúc 09:00 trong phạm vi snapshot và deadline. Recheck mode phải từ chối khi quyền hiện tại không còn. Hybrid mode có thể cho phép tạo dữ liệu trung gian nhưng kiểm tra lại trước khi công bố báo cáo.

**Câu hỏi 3:** Nếu worker nhận cùng message hai lần thì sao?

**Trả lời:** Job ID và operation/idempotency key phải giúp worker nhận ra công việc hoặc side effect đã được xử lý. Chỉ dựa vào chữ ký JWT hoặc message signature không ngăn queue giao lại message.

**Câu hỏi 4:** Worker có thể tự tạo access token mới từ subject Alice trong message không?

**Trả lời:** Không. Subject trong message không phải bằng chứng ủy quyền. Token mới phải được cấp bởi authorization server theo delegation policy, subject token hoặc job authorization đáng tin cậy và workload identity của worker.

## 18. Ghi nhớ

Tác vụ nền và queue kéo dài vòng đời của công việc qua nhiều dịch vụ, trong khi access token có thời hạn và audience cụ thể. Không coi token của request đầu vào là credential bền vững cho worker. Hãy tách actor ban đầu khỏi workload thực thi, xác định quyền được snapshot hay re-authorize, và cấp credential đúng audience theo từng chặng.

Message cần mang job identity và ngữ cảnh tối thiểu, được bảo vệ bằng workload authentication, broker ACL, integrity/confidentiality và kiểm soát replay. Worker cần kiểm tra job state, deadline, authorization và idempotency trước side effect. Với job dài, dùng checkpoint, cancellation và cơ chế renew/delegation có kiểm soát.

**JWT xác thực một credential trong một ngữ cảnh; nó không tự quản lý vòng đời của job, không thay thế danh tính workload và không bảo đảm message chỉ được xử lý một lần.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh issuer, audience, thuật toán và phân biệt token profile.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, client và authorization grant.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject token, actor token và delegation/token exchange.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access token/refresh token và sender-constrained token.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa HTTP và tính idempotent.
