# Queue backlog load — Kiểm thử tải khi hàng đợi tồn đọng

Bài học thuộc chương **Load Testing** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Trọng tâm là kiểm tra hệ thống xử lý bất đồng bộ khi công việc đến nhanh hơn khả năng xử lý, đồng thời bảo vệ các quy tắc về quyền, trạng thái, giá, thời hạn và số lần thực hiện nghiệp vụ.

Một API vẫn trả nhanh trong khi hàng đợi tăng không có nghĩa toàn bộ nghiệp vụ đang hoạt động tốt. Job có thể nằm chờ đến lúc báo giá hết hạn, quyền đã bị thu hồi hoặc đối tượng đã đổi version. Khi worker phục hồi, một lượng lớn job cũ có thể cùng được thực hiện, tạo tác động sai hoặc trùng.

Bài kiểm thử cần trả lời đồng thời hai câu hỏi:

- Hệ thống tiếp nhận, giới hạn và giải phóng tồn đọng như thế nào?
- Trong và sau thời gian tồn đọng, từng thao tác nghiệp vụ có kết quả đúng theo hợp đồng không?

Sau bài học, bạn cần có thể thiết kế workload gây backlog có kiểm soát, đo thời gian chờ và thời gian phục hồi, đối soát các thao tác đã nhận, và phát hiện lỗi logic bị che khuất bởi chỉ số throughput.

## 1. Backlog là công việc nào đang tồn đọng?

### 1.1. Phân biệt message và thao tác nghiệp vụ

Một thao tác phê duyệt đơn hàng có thể tạo nhiều message:

```text
API nhận command
  → outbox chờ phát
  → message gửi tới broker
  → worker nhận và xử lý
  → message được gửi lại nếu mất acknowledgement
  → event kết quả gửi tới downstream
```

Một message bị giao lại ba lần vẫn có thể thuộc một thao tác nghiệp vụ. Ngược lại, một message batch có thể chứa nhiều thao tác.

Vì vậy, cần đo hai lớp:

| Lớp | Đại lượng cần quan sát |
|---|---|
| Vận chuyển và xử lý message | Ready, in-flight/unacknowledged, delayed retry, DLQ, delivery rate |
| Nghiệp vụ | Thao tác duy nhất đã nhận, đang chờ, thành công, bị từ chối, hết hạn hoặc chưa được giải quyết |

Không cộng số message ở tất cả queue rồi gọi đó là số đơn hàng chưa hoàn tất nếu một thao tác có thể xuất hiện ở nhiều vị trí.

### 1.2. Những nơi backlog có thể bị ẩn

- Outbox chưa phát dù queue chính còn trống.
- Message đã được worker lấy nhưng chưa xử lý xong.
- Bộ đệm trong tiến trình hoặc executor.
- Retry được lên lịch ở queue khác.
- Job chờ quota của hệ thống ngoài.
- Message đã vào DLQ nhưng thao tác nghiệp vụ chưa có kết quả.
- Callback chưa được xử lý hoặc trạng thái chưa được đối soát.

Queue chính bằng 0 chưa đủ để kết luận đã xử lý xong.

Với RabbitMQ, giới hạn độ dài queue không tính message đang unacknowledged; cách tính các trạng thái khác còn phụ thuộc loại queue. Do đó phải hiểu rõ ý nghĩa metric và cấu hình của broker đang dùng. [RabbitMQ: Queue Length Limit](https://www.rabbitmq.com/docs/maxlength).

### 1.3. Định nghĩa backlog nghiệp vụ

Trong một phạm vi test, có thể định nghĩa:

```text
B(t) = số thao tác đã được nhận bền vững
       nhưng chưa có kết quả nghiệp vụ cuối cùng tại thời điểm t
```

Những thao tác bị cách ly vì lỗi vẫn có thể nằm trong phần chưa giải quyết. Việc chuyển message vào DLQ không tự làm nghiệp vụ hoàn tất.

Một trạng thái `EXPIRED` chỉ là kết quả cuối hợp lệ nếu hệ thống đã ghi nhận hết hạn theo hợp đồng và không còn tác động trái phép tiếp tục chạy sau đó.

## 2. Vì sao backlog là vấn đề bảo mật logic nghiệp vụ?

Khoảng cách giữa lúc nhận và lúc thực hiện tạo ra nhiều điều kiện thay đổi:

| Khi tiếp nhận | Trong lúc chờ | Rủi ro nếu worker dùng giả định cũ |
|---|---|---|
| Đơn chờ phê duyệt | Đơn đã bị hủy | Thực hiện trên trạng thái không còn hợp lệ |
| Báo giá còn hạn | Báo giá hết hạn | Dùng giá hoặc điều kiện không còn hiệu lực |
| Actor có quyền | Quyền thay đổi | Thực hiện trái chính sách ủy quyền hiện hành |
| Version là 7 | Dữ liệu chuyển sang version 8 | Dùng quyết định cho dữ liệu cũ |
| Yêu cầu chưa được thực hiện | Client retry hoặc broker redeliver | Tạo tác động nhiều lần |
| Còn hạn mức | Job khác đã dùng phần còn lại | Vượt hạn mức tổng |
| Tenant có quota | Tenant khác tạo tải lớn | Mất công bằng hoặc bỏ qua giới hạn để xử lý nhanh |

Một cách tối ưu làm queue giảm nhanh nhưng bỏ kiểm tra quyền hoặc trạng thái là thất bại về nghiệp vụ. Tương tự, bỏ message cũ mà không cập nhật kết quả của các thao tác đã nhận có thể làm mất công việc.

Các bất biến quan trọng:

```text
Không có tác động nghiệp vụ từ chuyển trạng thái bị cấm.
Không dùng dữ liệu đã mất hiệu lực ngoài hợp đồng.
Một thao tác duy nhất không tạo tác động thành công trùng.
Không vượt giới hạn tổng khi nhiều worker cùng xử lý.
Mọi thao tác đã nhận phải có trạng thái truy vết được.
Giới hạn tải không được tạo quyền vượt tenant hoặc bỏ guard.
```

## 3. Phân biệt command đang chờ với event đã xảy ra

Đây là bước cần làm trước khi xác định expected.

### 3.1. Command là ý định cần quyết định

Ví dụ `ApproveOrder` hoặc `RequestRefund` yêu cầu hệ thống thực hiện một nghiệp vụ.

Worker phải kiểm tra những điều kiện mà hợp đồng yêu cầu tại thời điểm thực hiện, chẳng hạn:

- Đối tượng vẫn ở trạng thái cho phép.
- Version hoặc dữ liệu cần phê duyệt còn phù hợp.
- Quyết định ủy quyền còn áp dụng.
- Hạn mức còn đủ.
- Yêu cầu chưa được thực hiện trước đó.

### 3.2. Event là sự kiện đã được ghi nhận

Ví dụ `OrderApproved` có thể biểu diễn một quyết định đã commit. Consumer không nên tùy tiện phủ nhận sự kiện lịch sử chỉ vì actor hiện tại đã đổi quyền.

Consumer cần xử lý đúng nguồn gốc event, thứ tự/version, tính idempotent và hợp đồng của tác động downstream. Nếu bước downstream cần một quyết định mới, quyết định đó phải được mô hình hóa riêng.

Không áp cùng một quy tắc “kiểm tra lại mọi quyền hiện tại rồi bỏ message” cho cả command lẫn event. Việc đó có thể làm mất các sự kiện hợp lệ đã xảy ra.

### 3.3. Chính sách quyền phải rõ ràng

Một job có thể dùng:

- Quyền hiện hành tại lúc thực hiện.
- Một ủy quyền đã cấp có thời hạn và phạm vi cụ thể.
- Một quyết định đã hoàn tất được biểu diễn thành event tin cậy.

Hợp đồng quyết định cách xử lý khi role bị thu hồi hoặc token client hết hạn. Token hết hạn không tự đồng nghĩa mọi job đã nhận phải bị hủy; cũng không có nghĩa job được bỏ qua kiểm tra quyền.

Nên truyền ngữ cảnh nguồn gốc có thể kiểm chứng và định danh cần thiết theo thiết kế. Không coi role hoặc tenant tùy ý trong payload là principal tin cậy.

## 4. Mô hình tải và khả năng giải phóng backlog

### 4.1. Chọn đúng đơn vị

Trong mô hình đơn giản:

```text
λ = số thao tác duy nhất được nhận bền vững mỗi giây
μ = số thao tác đi đến kết quả cuối mỗi giây
B = số thao tác chưa có kết quả cuối
```

Nếu các tốc độ gần như không đổi trong một khoảng:

```text
B(t + Δt) ≈ max(0, B(t) + (λ - μ) × Δt)
```

Đây là xấp xỉ ở mức công việc tổng hợp. Nó chưa mô tả thứ tự, ưu tiên, retry, batch hoặc các nhóm job có chi phí khác nhau.

Cần tách thêm `μ_success`, `μ_rejected` và `μ_expired`. Một hệ thống giải phóng queue bằng cách làm hết hạn mọi job không đạt cùng mục tiêu với hệ thống hoàn tất nghiệp vụ hợp lệ.

### 4.2. Ví dụ ước lượng

Giả sử ban đầu không có backlog:

```text
Pha quá tải:
  λ = 400 thao tác/giây
  μ = 240 thao tác/giây
  thời gian = 60 giây

Backlog tăng xấp xỉ:
  (400 - 240) × 60 = 9.600 thao tác
```

Khi giảm tải mới xuống 80 thao tác/giây, nếu khả năng xử lý vẫn là 240:

```text
Tốc độ giải phóng ròng:
  240 - 80 = 160 thao tác/giây

Thời gian giải phóng ước lượng:
  9.600 / 160 = 60 giây
```

Nếu ngừng hoàn toàn công việc mới:

```text
9.600 / 240 = 40 giây
```

Những con số này chỉ đúng với giả định năng lực xử lý ổn định, không tăng retry hoặc phát sinh thêm nút thắt. Phải so sánh với quan sát thực tế.

### 4.3. Backlog chia throughput không phải p95

Trong điều kiện gần FIFO, chi phí tương tự và năng lực ổn định, `B/μ` có thể cho một ước lượng thô về thời gian giải phóng lượng việc đang đứng trước một vị trí.

Nó không tự cho ra thời gian chờ trung bình, p95 hoặc p99 của mọi job. Prefetch, ưu tiên, nhiều consumer và job có chi phí khác nhau có thể làm trải nghiệm từng job rất khác.

Nếu dùng quan hệ Little `L = λW`, phải giữ cùng ranh giới đo và điều kiện trung bình ổn định phù hợp. Không lấy độ sâu tức thời trong pha backlog tăng rồi suy ra p95 bằng công thức đó.

### 4.4. Không suy throughput tuyến tính theo số worker

Xấp xỉ `số worker / thời gian xử lý trung bình` chỉ hữu ích khi các worker hoạt động độc lập và không tranh nút thắt chung.

Thêm worker có thể làm tăng:

- Tranh chấp khóa hoặc xung đột version.
- Sử dụng connection pool.
- Rate limit của nhà cung cấp.
- Retry và timeout.
- Áp lực CPU, bộ nhớ hoặc I/O.

Đo kết quả nghiệp vụ duy nhất hoàn tất theo giây thay vì chỉ đếm số lần worker bắt đầu xử lý.

## 5. Metric cần thu thập

### 5.1. Ba loại độ trễ

```text
admission_latency = responseAt - requestAt
queue_wait        = processingStartedAt - acceptedAt
processing_time   = terminalAt - processingStartedAt
end_to_end        = terminalAt - acceptedAt
```

Nếu có nhiều lần thử, cần ghi từng attempt và thời gian toàn bộ vòng đời. `processing_time` của một attempt không bao gồm toàn bộ thời gian retry.

Các mốc từ nhiều máy cần có cách xử lý lệch đồng hồ. Khi có thể, đo khoảng thời gian trong cùng nguồn hoặc ghi rõ sai số và cách đồng bộ.

### 5.2. Dashboard tối thiểu

| Nhóm | Metric |
|---|---|
| Tiếp nhận | Offered rate, request thực gửi, nhận bền vững, từ chối rõ ràng, kết quả chưa biết |
| Queue | Ready, in-flight/unacknowledged, retry chờ, DLQ, tuổi công việc cũ nhất |
| Worker | Active, thời gian xử lý, timeout, lỗi theo loại, số lần thử |
| Nghiệp vụ | Thành công duy nhất, từ chối, hết hạn, hủy, chưa giải quyết |
| Tính đúng | Tác động trùng, sai trạng thái, sai tenant, version cũ được thực hiện |
| Phụ thuộc | DB/pool, khóa, độ trễ provider, quota và lỗi tích hợp |
| Công bằng | Độ trễ và kết quả theo tenant hoặc nhóm tải |
| Phục hồi | Tốc độ giảm backlog, thời gian drain, công việc còn lại sau tải |

Không gắn mọi operation ID thành nhãn metric có cardinality rất cao. Dùng metric tổng hợp để theo dõi tải, còn ID chi tiết nằm trong trace, log hoặc bảng đối soát theo phạm vi test.

### 5.3. Tuổi công việc cần đo từ đúng điểm

Một retry được phát lại có thể có thời điểm enqueue mới nhưng vẫn là thao tác rất cũ. Vì vậy nên giữ:

```text
operationAcceptedAt
attemptEnqueuedAt
attemptStartedAt
terminalAt
```

Đo tuổi thao tác từ lần nhận đầu, không chỉ tuổi message ở attempt gần nhất. Nếu không, retry có thể làm dashboard “trẻ hóa” giả tạo.

## 6. Ma trận kịch bản gây backlog

| Kịch bản | Cách tạo tồn đọng | Điều cần kiểm tra |
|---|---|---|
| Baseline | Tải thấp hơn năng lực ổn định | Hợp đồng đúng và số liệu nền |
| Step overload | Tăng arrival rate có giới hạn | Backpressure, tuổi job và dữ liệu được bảo vệ |
| Consumer pause/resume | Tạm dừng worker rồi khôi phục | Job cũ, burst khi chạy lại, thời gian drain |
| Downstream chậm | Tăng độ trễ hoặc giới hạn sandbox/fake | Retry, pool, timeout và tác động trùng |
| Worker crash | Dừng sau một ranh giới đã chọn | Redelivery, idempotency và trạng thái dở dang |
| Job không thể xử lý | Một nhóm lỗi vĩnh viễn có kiểm soát | Không retry vô hạn, DLQ truy vết được |
| Nhiều tenant | Một tenant tải lớn, tenant khác tải nhỏ | Không vượt phạm vi hoặc làm đói nhóm còn lại |
| Hot object | Nhiều job trên cùng đối tượng | Version, thứ tự và hạn mức tổng |
| Redrive | Đưa công việc cách ly trở lại theo quy trình | Kiểm tra lại điều kiện và không tạo tác động trùng |

Không trộn mọi lỗi ngay trong lần đầu. Chạy baseline, sau đó thay đổi một yếu tố để xác định nút thắt và loại vi phạm.

Workload nhiều đối tượng độc lập đo năng lực khác với workload nhiều request cùng tranh một đơn. Cần có cả hai nếu hệ thống có rủi ro contention, nhưng báo cáo riêng kết quả.

## 7. Kiểm tra dữ liệu và quyền đã thay đổi khi job đang chờ

### 7.1. Chia nhóm có expected xác định

Ví dụ với command phê duyệt:

- Nhóm A: quyền, version và dữ liệu còn hợp lệ.
- Nhóm B: đơn bị hủy trước khi worker được phép tiếp tục.
- Nhóm C: version thay đổi và quyết định cũ không còn áp dụng.
- Nhóm D: báo giá hết hạn theo chính sách lúc thực hiện.
- Nhóm E: actor mất quyền, trong hợp đồng yêu cầu quyền hiện hành.
- Nhóm F: cùng operation được giao lại nhiều lần.

Dùng barrier hoặc điểm điều phối trong môi trường test để xác định điều kiện đã thay đổi trước khi thực hiện nhóm tương ứng. Không phụ thuộc hoàn toàn vào may rủi thời gian.

### 7.2. Kết quả cần kiểm tra

```text
Nhóm hợp lệ:
  hoàn tất đúng một lần theo hợp đồng

Nhóm bị hủy / mất hiệu lực:
  kết quả từ chối, hết hạn hoặc hủy được ghi nhận rõ
  không có chuyển trạng thái hoặc tác động thành công trái phép

Nhóm giao lại:
  không thêm tác động thành công
  vẫn truy được về cùng thao tác
```

Nếu hợp đồng cho phép xử lý theo một ủy quyền đã cấp, expected phải phản ánh phạm vi và thời hạn của ủy quyền đó. Không dùng test để áp một chính sách khác với sản phẩm.

### 7.3. Không tạo đường nhanh bỏ guard

Trong pha backlog, kiểm tra rằng worker vẫn dùng nguồn dữ liệu và guard cần thiết. Những tối ưu như cache quyền, batch, giảm truy vấn hoặc chạy nhiều worker cần giữ tính đúng của quyết định.

Có thể quan sát số quyết định từ chối theo nhóm và trạng thái thật sau xử lý. Chỉ đo số lần gọi hàm guard không đủ chứng minh guard áp dụng đúng dữ liệu.

## 8. Retry, acknowledgement và prefetch

### 8.1. Ack không phải bằng chứng nghiệp vụ đúng

Một message được ack nghĩa là broker có thể kết thúc trách nhiệm của delivery theo giao thức đang dùng. Nó không tự chứng minh đơn đã được duyệt đúng người hoặc khoản hoàn không bị lặp.

Trong luồng dùng transaction ứng dụng, cần quyết định rõ lúc nào có thể ack: kết quả nghiệp vụ hoặc bản ghi cần thiết để tiếp tục an toàn phải được lưu theo thiết kế.

Nếu worker commit rồi chết trước ack, message có thể được giao lại. Nếu ack trước khi dữ liệu cần thiết được lưu, lỗi sau đó có thể làm mất công việc.

### 8.2. Redelivery phải nằm trong workload

RabbitMQ có thể requeue các delivery chưa được ack khi consumer mất kết nối. Tài liệu cũng lưu ý vòng requeue/redelivery tức thời có thể tiêu tốn tài nguyên; consumer cần chuẩn bị cho việc nhận lại message. [RabbitMQ: Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms).

Kiểm tra ít nhất:

```text
Commit kết quả → mất kết nối trước ack → nhận lại
Nhận message → lỗi trước commit → nhận lại
Nhận lại cùng operation trên worker khác
```

Expected là tiếp tục hoặc trả kết quả đã có theo hợp đồng, không tạo tác động thành công mới.

### 8.3. Prefetch có thể dời backlog vào consumer

Prefetch giới hạn delivery chưa ack theo phạm vi cấu hình. Tăng prefetch có thể làm queue ready giảm trong khi nhiều công việc vẫn chờ trong worker. [RabbitMQ: Channel Prefetch Setting](https://www.rabbitmq.com/docs/confirms#channel-qos-prefetch).

Vì vậy đo ready cùng unacknowledged, bộ nhớ worker, thời gian bắt đầu thực thi và tuổi thao tác. Không coi việc ready giảm nhờ lấy trước message là tăng throughput nghiệp vụ.

Chọn cấu hình qua đo đạc với loại job thực tế. Prefetch cao không đảm bảo tăng số nghiệp vụ hoàn tất khi worker đang chờ cùng một DB pool hoặc provider quota.

### 8.4. Phân loại lỗi để retry đúng

| Loại lỗi | Hành vi minh họa |
|---|---|
| Kết nối tạm thời | Retry có backoff và ngân sách |
| Hết hạn nghiệp vụ | Ghi kết quả hết hạn, không retry như lỗi mạng |
| Sai quyền hoặc trạng thái | Kết quả từ chối theo hợp đồng |
| Dữ liệu không thể xử lý | Cách ly có lý do và liên kết operation |
| Kết quả provider chưa biết | Đối soát/retry bằng định danh chống trùng phù hợp |

Retry cần có số lần, khoảng thời gian và chính sách xử lý cuối. Nếu một lỗi vĩnh viễn được requeue liên tục, delivery rate có thể rất cao trong khi không có thêm thao tác nào hoàn tất.

## 9. Thiết kế bộ phát tải mở bằng k6

### 9.1. Vì sao cần arrival rate?

Với mô hình chỉ giữ một số client cố định, khi response chậm hơn, số request mới mỗi giây có thể tự giảm. Điều này dễ làm phép thử không tạo đủ áp lực để đánh giá backlog.

Executor `constant-arrival-rate` của k6 khởi chạy iteration theo tốc độ mục tiêu độc lập với thời gian response, trong giới hạn VU có sẵn. Một iteration có thể gồm nhiều request; cần biết chính xác script phát bao nhiêu request. [Grafana k6: Constant Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/).

### 9.2. Giả định của script minh họa

- Chỉ dùng trên môi trường test đã dựng.
- Fixture đã có các đơn độc lập ở trạng thái chờ, cùng version 7.
- Actor trong token có quyền yêu cầu phê duyệt các đơn đó.
- Endpoint bất đồng bộ minh họa là `POST /orders/{id}/approval-requests`.
- Hợp đồng môi trường quy định 202 trả operation ID; 429 từ chối trước khi nhận bền vững.
- Timeout hoặc lỗi gateway được coi là kết quả chưa biết, cần đối soát theo client operation ID.
- Một iteration gửi đúng một request, không tự retry.
- Script chỉ đo tiếp nhận; observer riêng đo worker và kết quả nghiệp vụ.

Các tên endpoint, header và trường dữ liệu là thiết kế minh họa, cần thay bằng hợp đồng thực tế.

```javascript
import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const acceptedResponses = new Counter('accepted_responses');
const backpressureResponses = new Counter('backpressure_responses');
const uncertainResponses = new Counter('uncertain_responses');
const unexpectedResponses = new Counter('unexpected_responses');

const baseUrl = (__ENV.BASE_URL || '').replace(/\/$/, '');
const runId = __ENV.RUN_ID;
const token = __ENV.TEST_TOKEN;
const rate = Number(__ENV.RATE || 120);

if (!baseUrl || !runId || !token) {
  throw new Error('BASE_URL, RUN_ID and TEST_TOKEN are required');
}
if (!Number.isInteger(rate) || rate <= 0) {
  throw new Error('RATE must be a positive integer');
}

export const options = {
  scenarios: {
    backlog_admission: {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 40,
      maxVUs: 120,
      gracefulStop: '10s',
    },
  },
  thresholds: {
    dropped_iterations: ['count==0'],
    unexpected_responses: ['count==0'],
    uncertain_responses: ['count==0'],
    http_req_duration: ['p(95)<300'],
    checks: ['rate==1'],
  },
};

export default function () {
  const index = exec.scenario.iterationInTest;
  const orderId = runId + '-order-' + index;
  const clientOperationId = runId + ':approve:' + index;

  const response = http.post(
    baseUrl + '/orders/' + encodeURIComponent(orderId)
      + '/approval-requests',
    JSON.stringify({
      clientOperationId,
      expectedVersion: 7,
    }),
    {
      headers: {
        Authorization: 'Bearer ' + token,
        'Content-Type': 'application/json',
        'Idempotency-Key': clientOperationId,
        'X-Test-Run-Id': runId,
      },
      tags: {
        name: 'POST /orders/:id/approval-requests',
        phase: 'backlog_admission',
      },
      timeout: '5s',
    }
  );

  let operationId;
  if (response.status === 202) {
    try {
      operationId = response.json('operationId');
    } catch (_) {
      operationId = undefined;
    }
  }

  const accepted = response.status === 202
    && typeof operationId === 'string'
    && operationId.length > 0;
  const backpressured = response.status === 429;
  const uncertain = response.status === 0
    || response.status === 502
    || response.status === 503
    || response.status === 504
    || (response.status === 202 && !accepted);

  if (accepted) {
    acceptedResponses.add(1);
  } else if (backpressured) {
    backpressureResponses.add(1);
  } else if (uncertain) {
    uncertainResponses.add(1);
  } else {
    unexpectedResponses.add(1);
  }

  check(response, {
    'admission outcome is explicit': () => accepted || backpressured,
  });
}
```

### 9.3. Đọc đúng kết quả script

- `http_req_duration` là thời gian request tiếp nhận, không phải end-to-end của job.
- `accepted_responses` là số response đủ điều kiện, chưa phải số thao tác duy nhất hoàn tất.
- 429 là backpressure theo hợp đồng minh họa; vẫn cần đối soát không có công việc được nhận trái với response từ chối.
- Timeout hoặc 503 có thể xuất hiện sau khi hệ thống đã nhận việc. Không tự gửi lại bằng operation ID mới.
- Header test chỉ hỗ trợ liên kết dữ liệu, không thay thế xác thực hay cấp quyền.
- Fixture cần đủ đối tượng cho không gian index được dùng. Không modulo về một tập nhỏ nếu mục tiêu là đo các đơn độc lập.

`iterationInTest` là định danh iteration theo scenario; khi dùng nhiều scenario, cần thêm tên scenario vào khóa. Chạy phân tán có thể có khoảng trống index, nên cách cấp fixture phải tương thích thay vì chỉ giả định một dãy cục bộ liên tục. [Grafana k6: Execution Context](https://grafana.com/docs/k6/latest/javascript-api/k6-execution/).

### 9.4. Threshold của bộ phát không phải tiêu chí pass toàn bài

Script chấp nhận cả response 202 lẫn 429 để mô tả hợp đồng tiếp nhận. Nếu hệ thống trả 429 cho mọi request, phần kiểm tra response có thể pass nhưng không tạo backlog nào.

Bài test tổng thể vẫn phải yêu cầu lượng nhận bền vững tối thiểu, độ sâu/tuổi backlog mục tiêu và kết quả nghiệp vụ phù hợp. Ngưỡng thời gian và VU trong script chỉ là ví dụ.

Trong k6, `dropped_iterations` có thể cho thấy không đủ VU hoặc iteration kéo dài khiến bộ phát không giữ được tốc độ mục tiêu. Khi metric này tăng, tải thực gửi khác tải dự kiến và phải được báo cáo. [Grafana k6: Dropped Iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/).

Không đặt sleep cuối iteration để điều chỉnh tốc độ của executor này. Muốn đo pha giảm tải và drain, điều phối các pha hoặc lần chạy riêng và tiếp tục observer sau khi bộ phát ngừng gửi.

## 10. Đối soát từng thao tác sau khi drain

### 10.1. Không chỉ đối soát tổng đếm

Trong phạm vi một test run, có thể yêu cầu:

```text
Tập operation đã nhận bền vững
  = tập operation có trạng thái truy vết được
```

Với các trạng thái loại trừ nhau tại một snapshot:

```text
N_accepted_unique
  = N_succeeded
  + N_rejected
  + N_expired
  + N_cancelled
  + N_unresolved
```

`N_unresolved` gồm thao tác đang chờ, đang xử lý, chờ retry hoặc đang cách ly chưa giải quyết. Không thay nó bằng phép cộng đơn giản các queue depth.

Khi đã tới ranh giới drain theo hợp đồng, kiểm tra `N_unresolved` về mức cho phép, thường bằng 0 trong tình huống không cố ý để lại công việc cách ly.

Timeout phía client có thể tạo tập operation chưa biết đã được nhận hay chưa. Đối soát nhóm này theo client operation ID/key trước khi kết luận mất việc hoặc gửi thêm.

### 10.2. Oracle cần expected theo nhóm

Chỉ kiểm tra “mọi job có một trạng thái cuối” chưa đủ. Nếu mọi job hợp lệ đều bị hết hạn, queue vẫn có thể trống và phép đối soát số lượng vẫn cân.

Cần expected riêng cho các nhóm hợp lệ, bị hủy, stale version, hết hạn và replay. So sánh cả kết quả, dữ liệu được bảo vệ và tác động tương ứng.

### 10.3. Mẫu oracle bằng Java

Đoạn mã dùng Java 17 trở lên và JUnit Jupiter. Đây là utility minh họa cho **command phê duyệt**, trong đó một thao tác thành công có đúng một tác động phê duyệt bền vững. Nó không tự chạy broker hoặc tạo tải.

```java
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

final class BacklogOutcomeAssertions {
    enum Status {
        PENDING, RUNNING, RETRY_WAIT, QUARANTINED,
        SUCCEEDED, REJECTED, EXPIRED, CANCELLED
    }

    record Expected(
            String tenantId,
            Status status,
            long approvalEffects) {}

    record Observed(
            String tenantId,
            Status status,
            long approvalEffects) {}

    private static final Set<Status> TERMINAL = Set.of(
            Status.SUCCEEDED,
            Status.REJECTED,
            Status.EXPIRED,
            Status.CANCELLED);

    static void verifyAfterDrain(
            Map<String, Expected> acceptedOperations,
            Map<String, Observed> observedOperations) {
        assertEquals(
                acceptedOperations.keySet(),
                observedOperations.keySet(),
                "Every accepted operation must remain traceable");

        acceptedOperations.forEach((operationId, expected) -> {
            Observed actual = observedOperations.get(operationId);

            assertNotNull(actual, operationId);
            assertTrue(
                    TERMINAL.contains(expected.status()),
                    "Expected outcome must be terminal: " + operationId);

            assertAll(
                    operationId,
                    () -> assertEquals(
                            expected.tenantId(), actual.tenantId()),
                    () -> assertEquals(
                            expected.status(), actual.status()),
                    () -> assertEquals(
                            expected.approvalEffects(),
                            actual.approvalEffects()),
                    () -> assertTrue(
                            actual.approvalEffects() >= 0
                                    && actual.approvalEffects() <= 1));
        });
    }
}
```

Map phải được dựng từ các thao tác duy nhất đã nhận, lọc đúng test run. Khi query tạo map, không được âm thầm ghi đè các bản ghi trùng khóa rồi làm mất bằng chứng. Số `approvalEffects` phải đến từ nguồn có thể phát hiện tác động trùng.

Expected được dựng từ hợp đồng và điều kiện nhóm test, không đọc lại status của SUT rồi chép sang. Utility này cũng chưa kiểm tra tổng tiền, version hoặc nguồn event; bổ sung những trường đó nếu chúng thuộc phạm vi cần bảo vệ.

## 11. Backpressure, giới hạn queue và sự thật về nhận bền vững

### 11.1. Nêu rõ điểm nhận trách nhiệm

Một hợp đồng có thể quy định API chỉ trả 202 sau khi lưu operation và outbox bền vững. Hợp đồng khác có thể dựa vào publisher confirm của broker.

Phải kiểm tra đúng thiết kế:

- Điều gì đã được lưu khi client nhận 202?
- Nếu broker chưa nhận hoặc publish thất bại, operation ở trạng thái nào?
- Worker có thể tìm lại công việc từ nguồn bền vững không?
- Client truy vấn kết quả bằng định danh nào?
- Một retry sau response chưa biết được gắn với cùng thao tác ra sao?

Mã HTTP 202 không tự tạo bảo đảm bền vững. Bảo đảm đến từ implementation và hợp đồng đã được kiểm thử.

### 11.2. Queue đầy không được làm mất việc âm thầm

Broker có thể được cấu hình từ chối publish, loại message hoặc dead-letter khi chạm giới hạn. Chính sách khác nhau cho kết quả khác nhau.

Test cần xác nhận:

```text
Nếu việc chưa được nhận:
  client nhận kết quả rõ theo hợp đồng

Nếu việc đã được nhận:
  vẫn có bản ghi truy vết và đường xử lý/khôi phục
  không biến mất chỉ vì queue chạm giới hạn
```

Độ sâu giảm do loại message không phải throughput nghiệp vụ. Message vào DLQ cũng không phải thành công.

### 11.3. Giới hạn theo tenant và nguồn tải

Một tenant tải lớn không được làm actor vượt quyền hoặc dùng quota của tenant khác. Nếu thiết kế có mục tiêu công bằng, đo riêng độ trễ và tỷ lệ nhận của nhóm tải nhỏ.

Rate limit ở ingress, giới hạn queue và quota downstream giải quyết các ranh giới khác nhau. Không giả định chỉ một trong số đó bảo vệ toàn bộ chuỗi.

## 12. Idempotency phải bao phủ thời gian chờ và phục hồi

Một job chờ lâu có thể được nhận lại sau:

- Timeout của client.
- Worker crash.
- Broker redelivery.
- Retry có độ trễ.
- Redrive từ DLQ.
- Khôi phục hệ thống sau sự cố.

Nếu bản ghi chống trùng hết hạn trong khi cùng thao tác vẫn có thể được giao lại, có nguy cơ tác động bị tạo lại. Thiết kế cần xác định thời hạn giữ, ràng buộc nghiệp vụ bền vững và cách xử lý thao tác quá cũ.

Không đơn giản chọn một TTL rồi coi an toàn với mọi lịch phục hồi. Cần kiểm tra quan hệ giữa:

```text
thời gian tồn đọng tối đa dự kiến
+ cửa sổ retry/redelivery
+ cửa sổ redrive hoặc phục hồi
+ chính sách lưu kết quả và ràng buộc nghiệp vụ
```

Đây là các đầu vào để thiết kế, không phải công thức bắt buộc cộng mọi khoảng trong mọi hệ thống.

Key mới vẫn phải chịu bất biến của đối tượng. Idempotency theo key không thay thế việc bảo vệ “đơn chỉ được duyệt hợp lệ một lần” hoặc “tổng hoàn không vượt số đã thu”.

## 13. Kế hoạch thực hành với các pha rõ ràng

Một kế hoạch minh họa:

| Pha | Tải và điều kiện | Mục tiêu |
|---|---|---|
| Chuẩn bị | Fixture sạch, observer hoạt động, dependency ở cấu hình nền | Xác nhận nguồn đo và quyền |
| Baseline | Tải dưới năng lực đã đo | Kiểm tra luồng hợp lệ và độ trễ nền |
| Tạo backlog | Tăng tải hoặc tạm giảm consumer trong giới hạn | Đạt số lượng/tuổi công việc mục tiêu |
| Biến đổi điều kiện | Hủy, đổi version hoặc hết hạn một số nhóm đã chọn | Kiểm tra quyết định lúc thực hiện |
| Phục hồi | Khôi phục consumer/dependency, giảm tải mới | Đo tốc độ giải phóng và burst |
| Drain | Ngừng hoặc giữ tải thấp đã định | Theo dõi tới ranh giới kết luận |
| Đối soát | So tập operation, trạng thái và tác động | Phát hiện mất việc, trùng và sai expected |

Những con số như 400 thao tác/giây hoặc backlog 9.600 trong bài chỉ để minh họa. Bắt đầu từ môi trường và giới hạn đã biết, rồi tăng có kiểm soát.

Đặt điểm dừng theo tài nguyên, tuổi job, số công việc chưa giải quyết hoặc vi phạm nghiệp vụ. Khi phải dừng sớm, giữ observer để biết công việc đã nhận còn đi đâu; không chỉ tắt bộ phát rồi bỏ qua phần tồn.

Không cleanup queue, outbox hoặc ledger trước khi đối soát. Nếu cần hủy công việc test, làm theo cơ chế có trạng thái rõ và xác nhận không có tác động muộn ngoài ý muốn.

## 14. Tiêu chí pass/fail nên có hai nhóm

### 14.1. Hiệu năng và phục hồi

Ví dụ tiêu chí nội bộ cho một môi trường cụ thể:

- Bộ phát đạt offered rate đã định hoặc báo rõ phần không gửi được.
- Tiếp nhận đạt tỷ lệ tối thiểu theo mục tiêu từng pha.
- Backlog và tuổi công việc không vượt giới hạn đã chốt.
- End-to-end của nhóm hợp lệ đạt SLO.
- Backlog được giải phóng trong cửa sổ phục hồi đã định.
- Tenant tải nhỏ đạt mục tiêu riêng nếu có hợp đồng công bằng.

### 14.2. Tính đúng nghiệp vụ

- Không có tác động thành công trái quyền, trái trạng thái hoặc dữ liệu mất hiệu lực.
- Không có tác động trùng theo operation/nghiệp vụ.
- Không vượt tổng hạn mức khi nhiều worker cùng xử lý.
- Không mất truy vết thao tác đã nhận.
- Nhóm hợp lệ không bị chuyển hết thành từ chối để làm đẹp throughput.
- Job hết hạn, bị hủy hoặc cách ly có kết quả và trách nhiệm xử lý rõ.
- Retry/redrive không đi đường bỏ qua các kiểm soát.

Một bài test fail về tính đúng dù p95 API rất thấp hoặc queue được dọn nhanh. Ngược lại, tính đúng được giữ nhưng thời gian drain vượt mục tiêu vẫn là vấn đề cần báo cáo riêng.

## 15. Đọc các dấu hiệu dễ gây hiểu nhầm

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| Ready giảm mạnh, unack tăng | Công việc chuyển vào consumer, chưa chắc xử lý nhanh hơn |
| Ack rate cao, thành công nghiệp vụ thấp | Từ chối/hết hạn hoặc xử lý sai điểm ack |
| Delivery rate tăng, backlog không giảm | Requeue/redelivery loop |
| Queue chính trống, operation vẫn pending | Outbox, retry, DLQ hoặc trạng thái bị bỏ quên |
| Throughput tăng khi thêm worker nhưng lỗi version tăng mạnh | Contention hoặc hot object |
| API vẫn nhanh, end-to-end tăng | Tồn đọng bị che sau lớp tiếp nhận |
| Tất cả job có trạng thái cuối nhưng tỷ lệ thành công giảm | Hết hạn hoặc từ chối hàng loạt |
| Không có request mới nhưng backlog tăng | Retry, fan-out hoặc công việc nội bộ phát sinh |
| Idempotency test tuần tự pass, crash test có tác động trùng | Khoảng trống giữa commit, tác động ngoài và ack |
| Chỉ tenant lớn đạt throughput | Starvation hoặc phân bổ tài nguyên không phù hợp |

Không chọn một nguyên nhân chỉ từ một biểu đồ. Dùng tương quan thời gian, loại job và dữ liệu đối soát để xác định điều đã thực sự xảy ra.

## 16. Mẫu báo cáo kết quả

Một báo cáo có thể gồm:

```text
Phạm vi:
  Command/luồng nghiệp vụ, broker, worker, database và dependency liên quan

Cấu hình:
  Số worker, prefetch, pool, giới hạn queue, retry và chính sách hết hạn

Workload:
  Offered rate, tải thực gửi, số operation duy nhất, mix tenant và hot object

Diễn biến:
  Thời điểm tăng tải, tạo backlog, thay đổi điều kiện và phục hồi

Hiệu năng:
  Admission latency, queue wait, end-to-end, tuổi công việc và thời gian drain

Đối soát:
  Accepted unique = succeeded + rejected + expired + cancelled + unresolved

Tính đúng:
  Tác động trùng, sai trạng thái, sai quyền, version cũ và vượt hạn mức

Bằng chứng:
  Operation IDs/correlation, snapshot, provider/ledger nếu thuộc phạm vi

Giới hạn:
  Phần dùng fake, kết quả chưa biết, pha bị dừng sớm và đường chưa kiểm tra
```

Giữ các metric và kết quả theo cùng cửa sổ thời gian. Nếu còn operation chưa giải quyết, không báo “đã drain hoàn toàn” chỉ vì queue chính hết message.

## 17. Bài tập thực hành

### Bài tập 1: Tính backlog và thời gian phục hồi

Với tốc độ nhận 300 thao tác/giây, tốc độ kết thúc 180 thao tác/giây trong 90 giây, ước lượng lượng tồn đọng tăng thêm.

Sau đó giảm nhận xuống 60 thao tác/giây. Tính thời gian giải phóng theo mô hình đơn giản và liệt kê ba điều kiện có thể làm số đo thực tế khác dự đoán.

### Bài tập 2: Báo giá hết hạn khi chờ

Một nhóm command cần báo giá còn hiệu lực ở thời điểm thực hiện. Dựng backlog sao cho một phần báo giá hết hạn.

Xác định cách chia nhóm expected, metric cần đo và cách chứng minh worker không dùng giá cũ. Nêu khác biệt nếu message là event của một quyết định đã commit.

### Bài tập 3: Crash sau commit trước ack

Dừng worker sau khi lưu kết quả nhưng trước ack. Cho message được giao lại và xác định các bằng chứng để kết luận không tạo tác động thành công lần hai.

Phân biệt điều fake trong bộ nhớ chứng minh được với điều cần broker/database thật.

### Bài tập 4: Công bằng giữa tenant

Tenant A tạo phần lớn tải, tenant B tạo ít request hợp lệ. Đề xuất mục tiêu độ trễ/kết quả cho B và cách giữ ranh giới tenant trong toàn bộ luồng.

Không chỉ báo throughput tổng của cả hai tenant.

### Bài tập 5: Queue trống nhưng chưa hoàn tất

Sau pha phục hồi, queue chính bằng 0 nhưng còn operation pending và một số message trong DLQ. Thiết kế phép đối soát xác định công việc nào chưa được giải quyết.

Giải thích vì sao việc đưa toàn bộ DLQ sang trạng thái “thành công” không phải một cách hoàn tất bài test.

## 18. Tiêu chí tự kiểm tra bài làm

- Phân biệt được message backlog và backlog thao tác nghiệp vụ.
- Metric bao gồm outbox, in-flight, retry và công việc cách ly liên quan.
- Có offered rate, tải thực gửi và số nhận bền vững.
- Đo thời gian chờ và end-to-end, không chỉ API latency.
- Có baseline, pha tạo tồn và pha phục hồi/drain.
- Expected phản ánh đúng command/event và chính sách ủy quyền.
- Có kiểm tra dữ liệu thay đổi, hết hạn, bị hủy và stale version.
- Redelivery, retry và crash không tạo tác động trùng.
- Đối soát từng operation, không chỉ tổng số message.
- Tính đúng và hiệu năng có tiêu chí riêng, cùng được đánh giá.
- Các trường hợp chưa kết luận và giới hạn môi trường được ghi rõ.

Queue backlog load có giá trị khi chứng minh hệ thống vẫn giữ đúng hợp đồng nghiệp vụ trong thời gian chờ và lúc phục hồi. Một queue giảm nhanh chỉ là một tín hiệu; kết quả cần đạt là mọi thao tác đã nhận được xử lý hoặc kết thúc đúng chính sách, có thể truy vết và không tạo tác động trái phép.
