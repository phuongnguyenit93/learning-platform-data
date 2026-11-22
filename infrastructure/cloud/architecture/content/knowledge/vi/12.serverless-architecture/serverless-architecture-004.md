# Điều phối quy trình bằng dịch vụ workflow

Trong kiến trúc serverless, một nghiệp vụ thường không kết thúc trong một lần gọi function. Ví dụ, khi khách hàng đặt phòng, hệ thống có thể phải kiểm tra tồn chỗ, giữ chỗ, ủy quyền thanh toán, ghi nhận booking, gửi thông báo và cập nhật hệ thống phân tích. Mỗi bước có thể chạy trong một dịch vụ khác nhau, có thời gian xử lý và cách thất bại riêng. Nếu một bước bị timeout sau khi đã thực hiện xong, hệ thống còn phải xác định kết quả và quyết định có nên thử lại hay hoàn tác.

**Dịch vụ workflow** cung cấp cơ chế mô tả và điều phối một quy trình gồm nhiều bước, thường dưới dạng state machine hoặc workflow definition. Nó theo dõi trạng thái thực thi, kích hoạt function hoặc dịch vụ khác, chờ sự kiện, xử lý timeout/retry, rẽ nhánh và ghi nhận kết quả. Nhờ đó, logic điều phối có thể được quản lý tách biệt khỏi phần code nghiệp vụ của từng function.

Bài học thuộc chương **Kiến trúc serverless** của module **CLOUD_ARCHITECTURE**. Trọng tâm là chọn cách điều phối phù hợp, thiết kế quy trình có thể phục hồi, bảo vệ dữ liệu và danh tính, đồng thời đánh giá độ tin cậy, khả năng mở rộng, chi phí và công sức vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của workflow engine trong kiến trúc serverless và phân biệt orchestration với choreography.
2. Mô hình hóa nghiệp vụ thành state, task, choice, wait, parallel, timeout và nhánh lỗi.
3. Thiết kế retry có giới hạn, idempotency, compensation và xử lý kết quả không xác định.
4. Chọn cách lưu state/payload, kiểm soát thời lượng, giới hạn kích thước và khả năng khôi phục.
5. Xử lý quy trình dài hạn, lịch chạy, callback và phê duyệt thủ công.
6. Bảo vệ workflow bằng IAM, phân vùng tenant, secret, mã hóa và chính sách dữ liệu.
7. Quan sát workflow đầu cuối, kiểm thử lỗi và ước lượng chi phí theo số lần chuyển trạng thái, compute và dịch vụ tích hợp.

## 2. Workflow service giải quyết vấn đề nào?

### 2.1. Điều phối nhiều bước có trạng thái

Một workflow có thể gồm các bước đồng bộ và bất đồng bộ:

- Gọi function kiểm tra dữ liệu đầu vào.
- Gọi API hoặc service để giữ tài nguyên.
- Chờ kết quả từ nhà cung cấp bên ngoài.
- Rẽ nhánh theo điều kiện nghiệp vụ.
- Chạy song song nhiều công việc độc lập.
- Chờ người dùng hoặc phê duyệt viên ra quyết định.
- Thử lại khi lỗi tạm thời và chạy quy trình bù khi nghiệp vụ không thể tiếp tục.
- Ghi kết quả cuối cùng và phát sự kiện hoàn tất.

Nếu tự viết toàn bộ luồng trong một function dài, function có thể phải giữ trạng thái trong bộ nhớ, tự quản lý timeout, retry, lịch thực thi và kết quả của từng bước. Trong serverless, một lần chạy có thể bị giới hạn thời gian, tiến trình có thể bị kết thúc và một request có thể được giao lại. Workflow engine đảm nhận phần điều phối có trạng thái, giúp mỗi bước thực hiện trong thời gian và phạm vi trách nhiệm riêng.

### 2.2. Ví dụ luồng đặt phòng

~~~mermaid
flowchart TD
    START[Nhận yêu cầu đặt phòng] --> VALIDATE[Kiểm tra dữ liệu]
    VALIDATE --> HOLD[Giữ chỗ có thời hạn]
    HOLD --> AVAILABLE{Giữ chỗ thành công?}
    AVAILABLE -->|Không| REJECT[Từ chối đặt phòng]
    AVAILABLE -->|Có| PAY[Ủy quyền thanh toán]
    PAY --> PAID{Thanh toán được xác nhận?}
    PAID -->|Có| CONFIRM[Xác nhận booking]
    PAID -->|Không| RELEASE[Giải phóng giữ chỗ]
    CONFIRM --> NOTIFY[Gửi thông báo]
    RELEASE --> FAILED[Đánh dấu thất bại / đối soát]
    NOTIFY --> DONE[Hoàn tất]
~~~

Workflow mô tả **trình tự và quyết định điều phối**. Quy tắc giữ chỗ, quyền sở hữu booking và trạng thái thanh toán vẫn thuộc các dịch vụ nghiệp vụ tương ứng. Workflow engine không tự làm cho thao tác giữa nhiều database trở thành một transaction ACID.

### 2.3. Workflow engine không phải hàng đợi và cũng không phải function

| Thành phần | Vai trò chính | Ví dụ trách nhiệm |
|---|---|---|
| **Function / serverless compute** | Thực thi một đơn vị công việc | Tính giá, kiểm tra điều kiện, chuyển đổi dữ liệu |
| **Queue / message broker** | Đệm và phân phối thông điệp, tách producer khỏi consumer | Nhận yêu cầu gửi email, xử lý nền theo tốc độ worker |
| **Event bus** | Định tuyến sự kiện đến các subscriber | Phát BookingConfirmed cho nhiều consumer |
| **Workflow service** | Theo dõi tiến trình nhiều bước và điều phối trạng thái | Giữ chỗ → thanh toán → xác nhận → bù trừ nếu cần |
| **Database / state store nghiệp vụ** | Lưu dữ liệu nghiệp vụ có thẩm quyền | Booking, payment, inventory |

Một workflow có thể dùng queue/event bus cho bước bất đồng bộ, nhưng các thành phần này không có cùng semantics. Queue giữ thông điệp để consumer xử lý; workflow giữ ngữ cảnh và tiến độ của một lần thực thi quy trình.

## 3. Orchestration và choreography

### 3.1. Orchestration: một bộ điều phối quản lý trình tự

Trong mô hình orchestration, workflow engine hoặc một orchestrator xác định bước tiếp theo, gọi service tương ứng và ghi trạng thái tiến trình.

~~~mermaid
sequenceDiagram
    participant Client
    participant W as Workflow
    participant A as Availability
    participant P as Payment
    participant B as Booking
    Client->>W: Start booking workflow
    W->>A: Hold availability
    A-->>W: holdId
    W->>P: Authorize payment
    P-->>W: Authorized
    W->>B: Confirm booking
    B-->>W: Confirmed
    W-->>Client: Workflow completed
~~~

**Ưu điểm:** nhìn thấy luồng tổng thể, thứ tự và trạng thái tập trung; dễ biểu diễn timeout, nhánh lỗi, phê duyệt và thời gian chờ.

**Đánh đổi:** workflow definition trở thành một thành phần cần quản lý; thay đổi hợp đồng hoặc thêm bước cần điều chỉnh quy trình. Nếu thiết kế orchestrator gọi mọi dịch vụ cho mọi việc, nó có thể trở thành điểm coupling và trung tâm điều phối quá phức tạp.

### 3.2. Choreography: các dịch vụ phản ứng theo sự kiện

Trong mô hình choreography, các service phát và tiêu thụ sự kiện. Không có một workflow engine trung tâm nắm toàn bộ thứ tự; mỗi service thực hiện logic của mình khi nhận sự kiện phù hợp.

~~~mermaid
flowchart LR
    BOOK[Booking Service] -->|BookingRequested| BUS[(Event Bus)]
    BUS --> AV[Availability Service]
    AV -->|AvailabilityHeld| BUS
    BUS --> PAY[Payment Service]
    PAY -->|PaymentAuthorized| BUS
    BUS --> BOOK2[Booking Service]
    BOOK2 -->|BookingConfirmed| BUS
    BUS --> NOTIFY[Notification Service]
~~~

**Ưu điểm:** các service ít phải gọi trực tiếp lẫn nhau, có thể mở rộng subscriber độc lập và phù hợp với event-driven architecture.

**Đánh đổi:** khó nhìn thấy toàn bộ tiến trình từ một nơi; việc truy vết, xử lý event trùng, event tới sai thứ tự, timeout và compensation có thể phân tán qua nhiều service. Một luồng nghiệp vụ có quá nhiều sự kiện phản ứng dây chuyền có thể khó hiểu và khó vận hành.

### 3.3. So sánh và chọn cách phù hợp

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Nơi quản lý tiến trình | Workflow engine/orchestrator | Phân tán ở các producer/consumer |
| Quan sát tiến trình | Có execution history tập trung | Cần correlation và tổng hợp telemetry từ nhiều service |
| Phụ thuộc | Workflow phụ thuộc vào hợp đồng từng activity | Các service phụ thuộc schema/semantics của event |
| Bước chờ dài / phê duyệt | Thường biểu diễn trực tiếp trong workflow | Cần lưu trạng thái và xử lý event/callback riêng |
| Luồng đơn giản, fan-out | Có thể dùng, nhưng không nhất thiết cần workflow | Thường phù hợp |
| Quy trình nhiều nhánh và compensation | Dễ mô tả thứ tự và kết quả bù trừ | Có thể khó phối hợp khi trạng thái phân tán |
| Rủi ro | Orchestrator thành điểm coupling | Luồng sự kiện khó theo dõi và khó kết thúc rõ ràng |

Không có mô hình luôn tốt hơn. Có thể kết hợp: workflow điều phối các bước có thứ tự và trạng thái quan trọng, còn một bước phát domain event để nhiều consumer độc lập xử lý thông báo, phân tích hoặc cập nhật projection.

## 4. Mô hình hóa workflow như state machine

### 4.1. State, transition và task

Một state machine có tập trạng thái và quy tắc chuyển trạng thái. Mỗi state cần xác định:

- Nó thực hiện công việc hay chỉ biểu diễn trạng thái chờ/rẽ nhánh?
- Input/output là gì, có schema và kích thước giới hạn không?
- Điều kiện thành công/thất bại được quyết định ở đâu?
- Timeout, retry và loại lỗi nào có thể xử lý?
- State có side effect không; chạy lại có an toàn không?
- Chuyển tiếp có được ghi dấu để phục hồi và quan sát không?

Các kiểu state thường gặp (tên gọi cụ thể thay đổi theo workflow engine):

| Kiểu state | Vai trò | Ví dụ |
|---|---|---|
| **Task** | Gọi function, service hoặc activity | Reserve room, authorize payment |
| **Choice / condition** | Rẽ nhánh theo input/result | Nếu còn chỗ thì tiếp tục, nếu hết thì từ chối |
| **Wait / timer** | Dừng đến thời điểm hoặc thời hạn | Chờ thanh toán trong 15 phút |
| **Parallel** | Chạy nhiều nhánh độc lập | Gửi email và cập nhật analytics |
| **Map / fan-out** | Lặp theo danh sách phần tử | Kiểm tra nhiều chặng hoặc nhiều mặt hàng |
| **Pass / transform** | Chuyển tiếp hoặc định hình dữ liệu | Chuẩn hóa payload |
| **Success / fail** | Kết thúc thành công hoặc thất bại | Booking confirmed hoặc rejected |

### 4.2. Trạng thái nghiệp vụ khác trạng thái thực thi workflow

Workflow engine có thể báo execution là RUNNING, SUCCEEDED, FAILED hoặc TIMED_OUT. Dịch vụ Booking có thể đồng thời lưu booking là PENDING, CONFIRMED, CANCELLED hoặc RECONCILING. Hai hệ trạng thái liên quan nhưng không nên đồng nhất.

Ví dụ workflow timeout khi gọi Payment không chứng minh thanh toán thất bại. Booking có thể chuyển sang trạng thái RECONCILING, trong khi workflow kích hoạt bước đối soát. Không tự động đánh dấu booking FAILED chỉ vì orchestrator hết thời gian chờ.

### 4.3. Định nghĩa state transition có điều kiện

Tránh các trạng thái mơ hồ như DONE khi chưa rõ thành công ở bước nào. Nên ghi ngữ nghĩa:

~~~text
PENDING
  -> HOLD_REQUESTED
  -> HELD
  -> PAYMENT_PENDING
  -> PAYMENT_AUTHORIZED
  -> CONFIRMATION_PENDING
  -> CONFIRMED

Nhánh lỗi:
  -> REJECTED (không đáp ứng điều kiện)
  -> COMPENSATING (đang thực hiện thao tác bù)
  -> CANCELLED (đã hoàn tác theo quy tắc)
  -> RECONCILING (kết quả bên ngoài chưa xác định)
~~~

Workflow nên có transition terminal rõ ràng, đồng thời có cách xử lý trạng thái cần con người can thiệp thay vì giữ execution chạy vô hạn.

## 5. Thiết kế retry, timeout và idempotency

### 5.1. Lỗi tạm thời và lỗi nghiệp vụ

Không phải lỗi nào cũng nên retry:

| Loại lỗi | Ví dụ | Hành vi thường phù hợp |
|---|---|---|
| Lỗi tạm thời của mạng/dịch vụ | Connection reset, 503 tạm thời | Retry có giới hạn và backoff |
| Quá tải/rate limit | HTTP 429 hoặc service quota | Tôn trọng Retry-After, giới hạn concurrency |
| Lỗi dữ liệu/validation | Ngày trả phòng trước ngày nhận | Không retry; trả lỗi nghiệp vụ |
| Lỗi quyền | Thiếu IAM hoặc tenant permission | Không retry vô hạn; báo và sửa quyền |
| Conflict nghiệp vụ | Chỗ vừa được người khác giữ | Rẽ nhánh hoặc kết thúc theo nghiệp vụ |
| Kết quả không xác định | Timeout sau khi bên ngoài có thể đã commit | Đối soát/query trước khi quyết định thử lại |

### 5.2. Exponential backoff và jitter

Một policy đơn giản có thể dùng thời gian chờ tăng theo cấp số nhân, giới hạn số lần thử và thêm jitter để nhiều execution không cùng retry một lúc.

~~~text
delay(attempt) = min(maxDelay, baseDelay * 2^(attempt - 1))
actualDelay = delay(attempt) + randomJitter
~~~

Ví dụ baseDelay 1 giây, maxDelay 16 giây tạo chuỗi chờ gần 1, 2, 4, 8, 16 giây trước khi cộng jitter. Con số chỉ minh họa. Chọn thời gian theo SLA của dependency, deadline workflow và khả năng xử lý backlog.

Retry phải có **giới hạn**, cả số lần lặp lẫn tổng thời gian. Nếu mỗi lớp (client, gateway, workflow, SDK, service) đều retry độc lập, số lần gọi thực tế có thể nhân lên. Cần quy định một chiến lược retry tổng thể và tránh retry storm.

### 5.3. Timeout phải phù hợp từng bước

Task timeout nên dựa trên thời gian xử lý dự kiến, tail latency, giới hạn function/API và deadline toàn workflow. Tổng thời gian các bước, thời gian chờ, retry và compensation phải nằm trong mục tiêu nghiệp vụ.

Nếu workflow có deadline 20 phút, không nên cho từng task retry tới 15 phút mà không tính thời gian còn lại cho bước bù hoặc thông báo. Nên truyền deadline hoặc remaining time cho activity khi nền tảng hỗ trợ.

### 5.4. Idempotency bảo vệ side effect

Workflow engine có thể giao lại task sau timeout hoặc phục hồi. Một task gửi tiền, tạo đơn hàng hay gửi thông báo phải có khả năng xử lý lặp.

Ví dụ, paymentReference được tạo một lần cho intent thanh toán và dùng xuyên suốt các lần retry:

~~~json
{
  "bookingId": "booking_913",
  "paymentReference": "payref_7f91",
  "amountMinor": 1500000,
  "currency": "VND"
}
~~~

Payment Service phải lưu và kiểm tra reference theo phạm vi tenant/merchant, trả lại kết quả logic phù hợp khi nhận request trùng. Idempotency key cần có thời hạn lưu đủ bao phủ retry và đối soát; không dùng workflow execution ID làm khóa duy nhất nếu nhiều execution có thể đại diện cho cùng một intent nghiệp vụ.

**Exactly-once end-to-end** thường không thể giả định chỉ từ tính năng retry của workflow hay broker. Thiết kế phổ biến là delivery có thể lặp + thao tác idempotent + deduplication + đối soát.

## 6. Compensation và Saga cho quy trình nhiều dịch vụ

### 6.1. Transaction phân tán không tự rollback

Trong một database, transaction có thể rollback các thay đổi chưa commit. Nhưng trong workflow gọi Availability, Payment và Booking, mỗi service đã commit dữ liệu riêng. Nếu bước cuối thất bại, workflow engine không thể tự hoàn tác bằng cách rollback transaction của database khác.

**Saga** là mô hình chia quy trình dài thành các transaction cục bộ. Khi không thể tiếp tục, hệ thống chạy các **compensating action** đã định nghĩa để đưa nghiệp vụ về trạng thái chấp nhận được.

| Bước thành công | Hành động bù có thể có | Điều phải lưu ý |
|---|---|---|
| Giữ chỗ | Release hold | Hold có thể đã hết hạn hoặc đã chuyển trạng thái |
| Ủy quyền thanh toán | Void authorization | Không giống refund sau khi đã capture |
| Capture thanh toán | Refund | Refund có thể bất đồng bộ và thất bại |
| Tạo booking | Hủy booking theo chính sách | Có thể cần thông báo/biên bản và audit |
| Đặt giao hàng | Hủy hoặc tạo yêu cầu thu hồi | Không phải mọi side effect vật lý có thể đảo ngược |

Compensation không nhất thiết xóa sạch lịch sử; nhiều nghiệp vụ cần ghi nhận trạng thái hủy/hoàn tiền để đối soát.

### 6.2. Ví dụ saga đặt phòng

~~~mermaid
flowchart TD
    START[Start] --> HOLD[Hold availability]
    HOLD --> HOK{Hold ok?}
    HOK -->|No| REJECT[Reject booking]
    HOK -->|Yes| AUTH[Authorize payment]
    AUTH --> AOK{Authorization ok?}
    AOK -->|No| REL[Release hold]
    AOK -->|Yes| CONF[Confirm booking]
    CONF --> COK{Confirm ok?}
    COK -->|Yes| EVENT[Publish BookingConfirmed]
    COK -->|No / uncertain| COMP[Void authorization]
    COMP --> REL
    REL --> FAIL[Close or reconcile]
    EVENT --> DONE[Completed]
~~~

Sơ đồ cần được tinh chỉnh theo semantics của nhà cung cấp thanh toán. Nếu Payment timeout mà không rõ đã authorize hay chưa, không nên chạy void mù quáng; phải tra cứu theo paymentReference. Nếu void thất bại, ghi trạng thái cần đối soát và cảnh báo người vận hành.

### 6.3. Compensation có thể thất bại

Workflow phải định nghĩa:

- Số lần retry và deadline cho từng hành động bù.
- Hành động nào được phép thử lại và khóa idempotency nào cần dùng.
- Trạng thái lưu khi compensation thành công, thất bại hoặc chưa xác định.
- Bằng chứng/log/correlation để bộ phận hỗ trợ đối soát.
- Cơ chế cảnh báo và can thiệp thủ công.

Không được kết thúc execution là “đã rollback” nếu một thao tác bù vẫn chưa được xác nhận.

## 7. Lưu state và truyền payload giữa các bước

### 7.1. State có thể gồm dữ liệu gì?

Một workflow cần mang thông tin để xác định bước kế tiếp. Tuy nhiên, không nên nhét toàn bộ dữ liệu nghiệp vụ hoặc tệp lớn vào execution state nếu dịch vụ có giới hạn kích thước, chi phí lưu hoặc quyền truy cập rộng.

Nên ưu tiên:

- ID bền vững: bookingId, tenantId, paymentReference, object key.
- Trạng thái ngắn gọn và các kết quả cần thiết cho bước sau.
- Version hoặc sequence nếu cần kiểm soát cập nhật.
- Correlation ID và trace context phục vụ quan sát.
- Metadata nhạy cảm ở mức tối thiểu; dùng tham chiếu tới secret/data store được bảo vệ thay vì truyền secret qua state.

Đối với payload lớn, lưu dữ liệu trong object storage/database có kiểm soát rồi truyền reference, version và quyền truy cập cần thiết. Cần xử lý trường hợp object bị xóa, thay đổi hoặc quyền đọc hết hạn trong khi workflow còn chạy.

### 7.2. State machine không phải database nghiệp vụ

Execution history có thể lưu input/output của task theo cấu hình nền tảng. Điều đó hữu ích cho debug và audit, nhưng không nên biến lịch sử workflow thành system of record cho booking, payment hoặc inventory.

Database nghiệp vụ vẫn cần giữ dữ liệu có thẩm quyền, ràng buộc unique, audit và chính sách vòng đời. Workflow state theo dõi tiến trình; nó có thể được tái tạo hoặc đối chiếu với dữ liệu owner khi cần.

### 7.3. Kiểm soát dữ liệu nhạy cảm

Không đưa mật khẩu, access token, PAN/thông tin thẻ, secret hoặc dữ liệu cá nhân không cần thiết vào execution input, event, log và error message. Nếu workflow service ghi history tự động, phải hiểu:

- Nội dung nào được lưu, bao lâu và ai có quyền đọc.
- Có cơ chế mã hóa, redaction hoặc giới hạn logging nào.
- Backup/history nằm ở region nào và có đáp ứng chính sách dữ liệu.
- Người vận hành có thể xem payload nào trong console.
- Khi cần xóa dữ liệu, history, event và bản sao được xử lý ra sao.

## 8. Quy trình dài hạn, wait state và callback

### 8.1. Long-running workflow

Một số nghiệp vụ kéo dài nhiều phút, nhiều giờ hoặc nhiều ngày:

- Chờ xác nhận thanh toán hoặc hoàn tiền.
- Chờ người dùng bổ sung hồ sơ.
- Chờ phê duyệt từ quản trị viên.
- Đặt lịch theo thời điểm.
- Chờ đối tác xử lý vận chuyển hoặc kiểm tra giấy tờ.

Không nên giữ function chạy và sleep trong thời gian dài. Workflow engine có thể lưu trạng thái chờ, giải phóng compute và tiếp tục khi timer hoặc callback đến.

### 8.2. Callback và task token

Một mẫu phổ biến: workflow phát yêu cầu tới hệ thống ngoài và tạo correlation/task token. Khi có kết quả, hệ thống ngoài gọi callback với token hợp lệ để tiếp tục execution. Chi tiết triển khai tùy workflow engine.

Điều cần bảo vệ:

- Token phải khó đoán, có thời hạn và gắn với đúng execution/tenant.
- Callback phải xác thực người gửi, chữ ký hoặc mTLS theo mô hình tin cậy.
- Callback duplicate hoặc tới muộn phải được xử lý idempotent.
- Không để token trong URL/log công khai hoặc cho phép một callback hoàn tất task không thuộc tenant.
- Có timeout cho callback và nhánh xử lý khi không nhận được phản hồi.

### 8.3. Human approval

Phê duyệt thủ công cần phân quyền, audit và kiểm tra tính hợp lệ khi quay lại workflow. Ví dụ, yêu cầu refund lớn có thể chờ quản lý duyệt:

1. Workflow tạo approval request cùng thông tin cần xem.
2. Hệ thống gửi thông báo đến đúng nhóm có quyền.
3. Người phê duyệt đăng nhập và xác thực; backend kiểm tra họ có quyền với tenant/giao dịch đó.
4. Quyết định và người thực hiện được ghi audit.
5. Callback hoặc signal hợp lệ tiếp tục state machine.
6. Nếu quá hạn, workflow chuyển sang trạng thái hết hạn hoặc đưa vào quy trình escalation đã định nghĩa.

Không coi link chứa một mã bí mật là đủ để chứng minh người bấm có quyền phê duyệt.

## 9. Workflow type, thời lượng và giới hạn thực thi

Workflow engine serverless thường cung cấp nhiều chế độ thực thi. Tên gọi và giới hạn tùy nhà cung cấp, nhưng các đánh đổi thường gồm:

| Dạng thực thi | Đặc điểm | Khi nào phù hợp |
|---|---|---|
| **Standard / durable workflow** | Lưu trạng thái và history chi tiết, phù hợp tiến trình dài hoặc cần audit/điều phối bền vững | Booking, onboarding, approval, quy trình nhiều bước |
| **Express / high-throughput workflow** | Tối ưu cho lưu lượng lớn và thời lượng ngắn; semantics history/retry/độ bền có thể khác | Ingestion, xử lý sự kiện ngắn, fan-out nhiều lần |
| **Synchronous workflow invocation** | Caller chờ kết quả từ lần chạy workflow trong giới hạn dịch vụ | API cần response trực tiếp cho workflow ngắn |
| **Asynchronous workflow invocation** | Caller nhận execution reference rồi theo dõi kết quả sau | Quy trình nền và dài hạn |

Không được giả định synchronous workflow có thể chờ vô hạn hoặc mọi loại workflow có cùng semantics exactly-once. Trước khi chọn, kiểm tra giới hạn về thời lượng tối đa, số lần transition, kích thước input/output, concurrency, history retention, execution rate và cách tính giá tại sản phẩm cụ thể.

## 10. Bảo mật và quyền sở hữu trách nhiệm

### 10.1. Identity và least privilege

Workflow thường có quyền gọi nhiều dịch vụ. Không nên dùng một execution role có quyền quản trị toàn bộ hệ thống.

- Tách role/permission theo workflow hoặc task khi nền tảng hỗ trợ.
- Chỉ cấp quyền invoke function, publish message, đọc object và update state cần thiết.
- Tách quyền bắt đầu workflow khỏi quyền xem history hoặc sửa trạng thái.
- Ràng buộc tenant/resource trong logic authorization; workflow execution ID không thay thế authorization.
- Quản lý secret qua secret manager và rotation, không hard-code vào workflow definition.
- Kiểm tra quyền của callback, human approval và các integration account.

### 10.2. Network và dependency

Workflow service có thể gọi dịch vụ cloud nội bộ, endpoint private hoặc API công khai. Cần xem:

- Workflow engine có khả năng kết nối VPC/private network theo mô hình nào?
- Function/activity có cần NAT, private endpoint hoặc security group không?
- Callback từ đối tác đi vào điểm nào, xác thực và rate limit ra sao?
- Egress và inter-region transfer có phát sinh chi phí hoặc ràng buộc dữ liệu?
- Timeout/connection pool ở activity có phù hợp thời hạn workflow?

Một task thất bại vì không có route tới private database không nên được retry vô hạn như lỗi mạng tạm thời. Cần phân biệt lỗi cấu hình và lỗi transient.

### 10.3. Data governance

Workflow có thể chạm vào dữ liệu ở nhiều vùng và nhiều dịch vụ. Phải phân loại payload, xác định nơi lưu execution history, event, backup và log; kiểm soát quyền truy cập của operator và bên thứ ba. Nếu có yêu cầu residency/sovereignty, không chỉ kiểm tra region của database mà cả workflow history, queue, event bus, observability và hệ thống callback.

## 11. Quan sát và vận hành workflow

### 11.1. Theo dõi theo workflow và business transaction

Các tín hiệu hữu ích:

| Nhóm | Chỉ số / log | Mục đích |
|---|---|---|
| Throughput | Started/completed/failed/timed-out executions | Biết lượng và kết quả workflow |
| Duration | End-to-end duration, task duration, wait time | Nhận diện bước chậm |
| Retry | Retry count, backoff duration, error type | Phát hiện dependency không ổn định hoặc policy quá rộng |
| Backlog | Workflow pending, callback age, schedule delay | Nhận biết tiến trình không được tiếp tục |
| Compensation | Số lần compensation, tỷ lệ thất bại, age trạng thái bù | Phát hiện giao dịch cần can thiệp |
| Dependency | Error rate/latency theo function, DB, broker, API ngoài | Tìm nguồn lỗi |
| Cost | Transition count, invocation, duration, storage/history | Theo dõi chi phí theo luồng |
| Security | Unauthorized start/callback, access history, policy change | Phát hiện truy cập bất thường |

Mỗi nghiệp vụ nên có correlation ID hoặc business transaction ID xuyên suốt workflow và các service. Tránh dùng execution ID làm định danh nghiệp vụ duy nhất vì một nghiệp vụ có thể tạo nhiều execution do retry/restart hoặc tách quy trình.

### 11.2. Alert phải hướng tới hành động

Ví dụ:

- Tỷ lệ workflow lỗi vượt ngưỡng: phân nhóm theo error type và dependency trước khi paging.
- Execution ở trạng thái chờ quá lâu: kiểm tra callback, đối tác và task token.
- Compensation thất bại: cảnh báo mức nghiêm trọng và tạo quy trình đối soát.
- DLQ tăng nhanh: kiểm tra consumer, schema hoặc quyền.
- Chi phí transition/invocation tăng bất thường: kiểm tra loop, retry không giới hạn hoặc sự kiện trùng.
- Workflow chạy quá deadline nghiệp vụ: xác định bước đang giữ trạng thái và owner xử lý.

### 11.3. Runbook

Runbook cần chỉ ra:

1. Cách xác định execution và business transaction liên quan.
2. Cách xem state/history và error mà không lộ payload nhạy cảm.
3. Cách kiểm tra trạng thái thật tại Booking/Payment/Availability.
4. Điều kiện được phép retry, resume, redrive hoặc chạy compensation.
5. Cách tránh chạy lại side effect đã thành công.
6. Cách escalate và ghi nhận kết quả đối soát.

Không sửa trực tiếp execution state hoặc chạy lại workflow thủ công khi chưa xác định trạng thái của side effect trong các dịch vụ owner.

## 12. Chi phí và hiệu năng

### 12.1. Các thành phần chi phí

Chi phí workflow có thể phụ thuộc:

- Số lần bắt đầu execution.
- Số state transition hoặc request đến workflow engine.
- Số lần function/activity invocation và thời lượng compute.
- Thời gian chờ hoặc tài nguyên bị giữ, nếu mô hình dịch vụ tính phí theo đó.
- Lưu execution history, log, event và payload.
- Message broker, database, API gateway, NAT/egress và các dịch vụ bên ngoài.

Một workflow có vòng lặp retry không giới hạn vừa làm giảm độ tin cậy vừa làm tăng chi phí. Thiết kế cần giới hạn retry, deadline, maximum iteration và kích thước payload.

### 12.2. Latency và số transition

Mỗi state transition hoặc service call có overhead. Nếu một quy trình chỉ cần thực hiện một phép tính nhỏ, dựng workflow riêng có thể tăng latency và chi phí không cần thiết. Ngược lại, ghép 30 thao tác không liên quan vào một function duy nhất có thể làm lỗi khó phục hồi và timeout.

Có thể gom các bước nhỏ, thuần tính toán trong một activity khi ranh giới retry/transaction không cần tách riêng. Tách bước khi có side effect, dependency, thời gian chờ hoặc yêu cầu bù/quan sát độc lập.

### 12.3. Fan-out và concurrency

Parallel/map state có thể khởi chạy rất nhiều activity. Cần giới hạn concurrency, batch size và downstream rate để không làm database hay API bên ngoài quá tải. Nếu workflow engine có quota execution/transition, phải kiểm tra headroom và cơ chế throttling.

## 13. Kiểm thử và phát hành workflow

### 13.1. Test theo state và theo kịch bản lỗi

Không chỉ test happy path. Bộ test cần bao gồm:

- Validation thất bại ngay đầu workflow.
- Một activity timeout trước khi thực thi và timeout sau khi đã commit side effect.
- Lỗi 429/5xx, retry hết số lần và hết deadline.
- Callback hợp lệ, callback trùng, callback sai chữ ký và callback tới muộn.
- Nhánh choice không có trường hợp match và giá trị input thiếu.
- Một nhánh parallel thất bại khi nhánh khác đã có side effect.
- Compensation thành công, thất bại hoặc kết quả không xác định.
- Workflow bị dừng, resume hoặc redrive theo semantics của nền tảng.
- IAM thiếu quyền, secret hết hạn, dependency không truy cập được.

### 13.2. Test state machine bằng fixture

| Fixture | Kết quả cần kiểm tra |
|---|---|
| Booking hợp lệ, còn chỗ, payment authorized | Đi tới CONFIRMED và phát event đúng một hiệu ứng logic |
| Hết chỗ | Kết thúc REJECTED, không gọi Payment |
| Payment bị từ chối | Giải phóng hold nếu có và ghi FAILED/CANCELLED |
| Payment timeout không rõ kết quả | Tra cứu/đối soát, không tạo giao dịch mới tùy tiện |
| Callback phê duyệt tới muộn | Xử lý theo deadline và state hiện tại, không hồi sinh execution sai |
| Activity phát event rồi lỗi | Retry không tạo side effect trùng |

### 13.3. Versioning và triển khai

Workflow definition và activity contract cần được version hóa. Thay đổi định nghĩa có thể ảnh hưởng execution đang chạy; nền tảng có thể áp dụng phiên bản mới cho execution mới trong khi execution cũ tiếp tục theo definition cũ, hoặc có semantics khác. Phải xác nhận hành vi cụ thể của dịch vụ, lập kế hoạch tương thích input/output và không xóa function/version còn được execution hiện hữu tham chiếu.

Release plan nên có:

- Kiểm tra cú pháp/validation và quyền IAM.
- Test workflow local hoặc môi trường tương đương với các fixture.
- Deploy definition/activities theo thứ tự tương thích.
- Canary hoặc chạy thử giới hạn với dữ liệu an toàn.
- Quan sát tỷ lệ fail, duration, retry và chi phí.
- Rollback/forward-fix đã được xác định, lưu lịch sử và owner.

## 14. Ví dụ thiết kế workflow cho nền tảng đặt chỗ

Giả sử hệ thống muốn tiếp nhận yêu cầu đặt phòng và hoàn thành trong một quy trình bất đồng bộ. Mục tiêu minh họa:

- Ghi nhận booking request trong vài giây.
- Giữ chỗ trong thời gian có giới hạn.
- Ủy quyền thanh toán; nếu thành công thì xác nhận booking.
- Nếu thất bại, release hold và cập nhật trạng thái.
- Nếu kết quả thanh toán không xác định, thực hiện đối soát thay vì đoán.
- Gửi thông báo sau khi booking được xác nhận.

### 14.1. Workflow logic

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Booking API
    participant WF as Workflow Engine
    participant AV as Availability
    participant PAY as Payment
    participant DB as Booking Store
    participant MSG as Notification
    C->>API: POST /bookings + idempotency key
    API->>DB: Create PENDING booking
    API->>WF: Start execution with bookingId
    API-->>C: 202 Accepted + bookingId
    WF->>AV: Hold inventory
    AV-->>WF: holdId / rejected
    WF->>PAY: Authorize with paymentReference
    PAY-->>WF: Authorized / Declined / Unknown
    WF->>DB: Confirm or set RECONCILING
    WF->>MSG: Notify after confirmed
~~~

Workflow Engine chỉ nhận các định danh cần thiết; booking và payment data vẫn ở các service owner. Booking API trả 202 khi đã nhận xử lý, client truy vấn trạng thái hoặc dùng kênh thông báo.

### 14.2. Mã giả workflow definition

~~~yaml
# Mã giả trung lập, không phải cú pháp trực tiếp của một cloud provider.
workflow: CreateBooking
input:
  bookingId: string
  tenantId: string
  paymentReference: string
states:
  - task: HoldAvailability
    retry: transient-errors-only
    timeout: 10s
    onFailure: RejectBooking
  - task: AuthorizePayment
    idempotencyKey: paymentReference
    timeout: 20s
    onUnknown: ReconcilePayment
    onDeclined: ReleaseHold
  - task: ConfirmBooking
    onSuccess: PublishBookingConfirmed
    onUnknown: ReconcileBooking
  - task: PublishBookingConfirmed
  - task: NotifyCustomer
  - end: SUCCEEDED
~~~

Mã giả rút gọn nhằm minh họa trách nhiệm. Trong thực tế, workflow cần thể hiện nhánh compensation đầy đủ, policy retry cụ thể, quyền từng task, trạng thái cuối và cách xử lý khi activity có kết quả không xác định.

### 14.3. Bảng trách nhiệm

| Thành phần | Owner dữ liệu/quy tắc | Trách nhiệm |
|---|---|---|
| Booking Service | Booking | Tạo booking, trạng thái nghiệp vụ, kiểm tra tenant và quyền |
| Availability Service | Inventory/hold | Quyết định giữ chỗ, thời hạn hold, release/confirm |
| Payment Service | Payment | Trạng thái authorize/capture/refund, đối soát với provider |
| Workflow definition | Nhóm sở hữu quy trình | Thứ tự bước, timeout, nhánh, retry, compensation và deadline |
| Notification Service | Delivery status | Gửi thông báo, xử lý retry/dedup |
| Platform/Security | Hạ tầng và IAM | Quota, logging, encryption, role và network |

### 14.4. Trạng thái cần đối soát

Giả sử Payment provider đã authorize thành công nhưng response timeout. Workflow không biết kết quả. Activity ReconcilePayment tra cứu paymentReference:

- Nếu provider xác nhận Authorized, workflow tiếp tục confirm booking.
- Nếu provider xác nhận Declined hoặc không có giao dịch, workflow release hold và đóng theo trạng thái phù hợp.
- Nếu provider vẫn trả trạng thái Processing/Unknown, workflow chờ một khoảng thời gian có giới hạn và thử tra cứu lại.
- Nếu hết deadline vẫn không xác định, chuyển sang RECONCILING, tạo cảnh báo và giao owner xử lý; không phát thông báo BookingConfirmed.

Quy trình đối soát phải lưu dấu mọi kết quả và ngăn việc cùng một thanh toán được capture/refund lặp.

## 15. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách thiết kế lại |
|---|---|---|
| Dùng workflow thay database nghiệp vụ | Không có nguồn chuẩn rõ ràng, khó quản trị dữ liệu | Workflow theo dõi tiến trình; service owner lưu sự thật nghiệp vụ |
| Retry mọi lỗi | Lặp lỗi validation/quyền, tăng chi phí | Phân loại retryable/non-retryable và giới hạn tổng thời gian |
| Cho rằng timeout nghĩa là side effect thất bại | Tạo giao dịch kép | Idempotency key và reconciliation |
| Giả định workflow tự rollback nhiều service | Dữ liệu lệch giữa booking, inventory và payment | Saga và compensation có kiểm tra |
| Gửi payload lớn hoặc secret trong state | Vượt giới hạn, lộ dữ liệu qua history/log | Truyền ID/reference, tối thiểu hóa và kiểm soát quyền |
| Chờ bằng function sleep | Tốn tài nguyên và vướng giới hạn runtime | Wait state, timer hoặc callback |
| Fan-out không giới hạn | Quá tải dependency và vượt quota | Concurrency limit, batch và backpressure |
| Không theo dõi execution theo business ID | Khó điều tra và đối soát | Correlation ID và business transaction ID |
| Thay workflow definition không xét execution đang chạy | Tiến trình cũ/new activity không tương thích | Versioning, compatibility và rollout có kiểm soát |
| Coi event/notification là kết quả giao dịch | Gửi thông báo sai khi nghiệp vụ chưa xác nhận | Phát event sau khi owner commit trạng thái chuẩn |

## 16. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi thiết kế workflow | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Ai sở hữu definition, execution, runbook và can thiệp thủ công? | Version hóa, dashboard, correlation, alert; nhiều state làm vận hành phức tạp hơn |
| **Security** | Workflow/task được quyền làm gì, payload nào lưu trong history và ai xem được? | Least privilege, secret manager, data minimization, audit và kiểm soát callback |
| **Reliability** | Retry, timeout, compensation và trạng thái UNKNOWN được xử lý ra sao? | Idempotency, saga, reconciliation, DLQ và kiểm thử failure path |
| **Performance Efficiency** | Có quá nhiều transition hoặc service call không? | Gom task thuần tính toán, chọn concurrency và tối ưu fan-out |
| **Cost Optimization** | Execution, transition, function duration, history và log tiêu thụ bao nhiêu? | Giới hạn loop/retry, payload nhỏ, chọn loại workflow phù hợp |
| **Sustainability** | Workflow có chạy lặp, polling hoặc giữ tài nguyên không cần thiết? | Callback/timer, dedup, batch và xử lý hiệu quả |

Workflow làm quy trình dễ phục hồi hơn khi được thiết kế đúng, nhưng cũng tạo một lớp nền tảng mới cần bảo vệ, theo dõi và tính chi phí. Nên chọn workflow engine khi lợi ích của điều phối bền vững lớn hơn overhead của nó.

## 17. Bài tập áp dụng

### Bài tập A — Chọn orchestration hay choreography

Một quy trình onboarding có 9 bước, trong đó có bước phê duyệt thủ công, chờ đối tác, timeout và yêu cầu hoàn tác một số thao tác nếu bị từ chối.

**Câu hỏi:** Mô hình nào phù hợp hơn để quản lý trạng thái tổng thể?

**Gợi ý:** Orchestration thường dễ biểu diễn tiến trình dài, nhánh và compensation tập trung. Các sự kiện sau khi hoàn tất vẫn có thể dùng choreography để thông báo tới analytics, notification và những consumer độc lập.

### Bài tập B — Timeout sau thanh toán

Task authorize payment timeout. Workflow retry ngay bằng paymentReference mới, kết quả xuất hiện hai giao dịch.

**Câu hỏi:** Cần thay đổi những gì?

**Gợi ý:** Giữ reference ổn định theo một intent, Payment Service hỗ trợ idempotency, tra cứu trạng thái trước khi phát sinh request mới, phân biệt transient error với UNKNOWN và có reconciliation khi hết deadline.

### Bài tập C — Compensation thất bại

Booking đã được tạo và payment authorize; bước confirm inventory thất bại. Task void authorization cũng timeout.

**Câu hỏi:** Workflow có thể đánh dấu CANCELLED ngay không?

**Gợi ý:** Không khi kết quả void chưa xác định. Chuyển sang trạng thái compensation/reconciliation, query Payment theo reference, retry có giới hạn, cảnh báo owner và chỉ kết luận sau khi có bằng chứng. Không khẳng định đã hoàn tác nếu chưa xác nhận.

### Bài tập D — Workflow dài hạn

Quy trình kiểm duyệt hồ sơ có thể chờ quản lý phê duyệt trong 5 ngày.

**Câu hỏi:** Vì sao không nên để function chạy và sleep? Cần bảo vệ callback thế nào?

**Gợi ý:** Function sleep chiếm runtime, vướng giới hạn thời gian và không bền khi tiến trình bị dừng. Dùng wait/callback state; callback phải xác thực người gửi và quyền người duyệt, gắn với execution/tenant, chống replay, hết hạn và có audit.

### Bài tập E — Fan-out tạo tải đột biến

Một workflow xử lý 50.000 dòng và khởi chạy một function cho mỗi dòng cùng lúc. Database downstream chỉ chịu được 500 concurrent request.

**Câu hỏi:** Cần kiểm soát gì?

**Gợi ý:** Chia batch, giới hạn concurrency, rate limit và backpressure, theo dõi queue/backlog và giới hạn retry. Không tăng fan-out đến khi database bão hòa.

## 18. Checklist trước khi đưa workflow vào production

- [ ] Mục tiêu nghiệp vụ, owner quy trình, deadline và điều kiện kết thúc được xác định.
- [ ] Đã chọn orchestration/choreography theo độ phức tạp và khả năng quan sát.
- [ ] State, transition, input/output, nhánh lỗi và trạng thái không xác định được mô tả rõ.
- [ ] Task có timeout và retry giới hạn; lỗi nghiệp vụ không bị retry vô hạn.
- [ ] Side effect có idempotency và reconciliation cho tình huống timeout sau commit.
- [ ] Quy trình nhiều dịch vụ có compensation/Saga, bao gồm trường hợp compensation thất bại.
- [ ] Payload nhỏ, có schema và không chứa secret/dữ liệu nhạy cảm không cần thiết.
- [ ] Execution history, log, callback và backup có retention, mã hóa và phân quyền.
- [ ] IAM từng task theo least privilege; callback và human approval có xác thực/ủy quyền/audit.
- [ ] Fan-out có concurrency limit, downstream quota và backpressure.
- [ ] Có correlation/business ID, dashboard, alert, DLQ và runbook đối soát.
- [ ] Workflow definition và activity contract được version hóa; execution đang chạy được xử lý khi deploy.
- [ ] Đã test happy path, failure path, duplicate, out-of-order, timeout, callback muộn và failover.
- [ ] Chi phí transition, invocation, duration, storage và dịch vụ phụ thuộc đã được ước tính.
- [ ] Có kế hoạch review, diễn tập và cập nhật khi nghiệp vụ hoặc dependency thay đổi.

**Điểm cốt lõi:** workflow service điều phối **tiến trình**, còn các dịch vụ nghiệp vụ vẫn sở hữu **dữ liệu và quy tắc của mình**. Quy trình đáng tin cậy phải có trạng thái rõ, retry có giới hạn, side effect idempotent, compensation và đối soát có bằng chứng. Khi kết hợp đúng với IAM, observability, quota và kiểm thử lỗi, workflow giúp các thành phần serverless phối hợp thành một nghiệp vụ hoàn chỉnh mà vẫn có thể vận hành và phát triển an toàn.
