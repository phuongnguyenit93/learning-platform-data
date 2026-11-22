# Xây dựng SLI, SLO và error budget cho hành trình người dùng

Trong serverless, một request có thể đi qua API Gateway, Java function, database, queue và một hoặc nhiều worker trước khi người dùng nhận được kết quả cuối cùng. Function có thể trả HTTP 202 rất nhanh nhưng công việc phía sau thất bại, hoặc mọi invocation đều thành công trong khi người dùng vẫn không hoàn tất được hành trình mua hàng. Vì vậy, chỉ theo dõi số invocation, tỷ lệ lỗi của function hay CPU chưa đủ để biết dịch vụ có đang đáp ứng nhu cầu người dùng hay không.

Cần đo chất lượng ở cấp **hành trình người dùng** bằng SLI (Service Level Indicator), đặt mục tiêu bằng SLO (Service Level Objective), rồi dùng error budget để quyết định mức rủi ro có thể chấp nhận khi phát hành thay đổi. Với Java serverless, các chỉ số này phải nối được request đồng bộ với kết quả bất đồng bộ, tính đúng retry và duplicate, đồng thời phản ánh cả độ trễ lẫn tính đúng đắn của nghiệp vụ.

Bài học trình bày cách chọn hành trình, định nghĩa sự kiện tốt và tổng số sự kiện, xây dựng SLI/SLO cho HTTP và message/event flow, tính error budget, cảnh báo theo burn rate và đưa kết quả vào quy trình vận hành, phát hành.

## 1. Phân biệt SLI, SLO và SLA

Ba khái niệm liên quan nhưng không giống nhau:

- **SLI (Service Level Indicator):** phép đo định lượng chất lượng dịch vụ mà người dùng trải nghiệm, ví dụ tỷ lệ checkout hoàn tất trong 10 giây.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong một cửa sổ thời gian, ví dụ ít nhất 99,9% checkout hợp lệ hoàn tất trong 10 giây trong 30 ngày.
- **SLA (Service Level Agreement):** cam kết dịch vụ với khách hàng hoặc đối tác, thường có điều khoản và hệ quả thương mại nếu không đạt.

SLO thường nên nghiêm ngặt hơn SLA để đội vận hành có khoảng đệm xử lý trước khi vi phạm cam kết bên ngoài. Không phải mọi SLO đều cần trở thành SLA.

Ví dụ:

| Thành phần | Ví dụ |
|---|---|
| Hành trình | Người dùng tạo đơn hàng |
| SLI | Tỷ lệ yêu cầu tạo đơn hợp lệ được xác nhận thành công trong 5 giây |
| SLO | 99,9% trong cửa sổ 30 ngày |
| SLA | Cam kết công khai với khách hàng theo hợp đồng, nếu có |

SLI phải phản ánh kết quả mà người dùng quan tâm. Metric kỹ thuật như CPU utilization, số container, cold start count hoặc queue depth giúp giải thích nguyên nhân, nhưng tự chúng không chứng minh hành trình thành công.

## 2. Bắt đầu từ hành trình người dùng

Chọn một hành trình có ý nghĩa với người dùng và có điểm bắt đầu/kết thúc rõ ràng. Không bắt đầu bằng danh sách metric mà hệ thống đã có.

Ví dụ hành trình trong một ứng dụng serverless:

| Hành trình | Điểm bắt đầu | Kết quả người dùng mong đợi |
|---|---|---|
| Đăng nhập | Gửi thông tin đăng nhập | Nhận session/token hợp lệ và vào được ứng dụng |
| Tạo đơn hàng | Gửi yêu cầu checkout | Đơn hàng được tạo và có trạng thái xác nhận |
| Thanh toán | Bắt đầu payment | Thanh toán được xác nhận hoặc thất bại rõ ràng |
| Tải báo cáo | Yêu cầu export | Nhận được file hợp lệ trước deadline |
| Đồng bộ dữ liệu | Gửi yêu cầu import | Dữ liệu được xử lý và có kết quả cuối cùng |
| Gửi thông báo | Phát sinh sự kiện cần thông báo | Thông báo được nhà cung cấp chấp nhận hoặc gửi theo contract |

Một hành trình có thể gồm nhiều service và nhiều trigger. Ví dụ checkout có thể đi qua HTTP function, database transaction, queue, payment worker và webhook callback. Hãy đo ở điểm người dùng bắt đầu và điểm kết quả cuối cùng được xác nhận.

### Vẽ luồng trước khi chọn SLI

~~~mermaid
flowchart LR
    User[Người dùng]
    API[HTTP API / Java function]
    DB[(Order database)]
    Queue[Queue / event bus]
    Worker[Java payment worker]
    Provider[Payment provider]
    Callback[Webhook / result handler]
    UserResult[Trạng thái cuối cùng]

    User --> API
    API --> DB
    API --> Queue
    API -->|Accepted response| User
    Queue --> Worker
    Worker --> Provider
    Provider --> Callback
    Callback --> DB
    DB --> UserResult
~~~

Trong luồng này, HTTP 202 chỉ có nghĩa hệ thống đã tiếp nhận công việc theo contract. Nó chưa chứng minh thanh toán thành công. Nếu hành trình người dùng là “thanh toán được xác nhận”, SLI phải theo dõi kết quả cuối cùng chứ không dừng ở response 202.

## 3. Định nghĩa SLI bằng tử số và mẫu số

Một SLI dạng tỷ lệ thường có cấu trúc:

```text
SLI = số sự kiện tốt / tổng số sự kiện đủ điều kiện
```

Cần định nghĩa chính xác hai phần:

- **Tổng số sự kiện (eligible events):** những thao tác nào được tính vào mẫu số?
- **Sự kiện tốt (good events):** điều kiện nào chứng minh thao tác đáp ứng yêu cầu?

Ví dụ SLI availability cho checkout:

```text
Good event:
  Request hợp lệ được chấp nhận và tạo order đúng contract.

Eligible event:
  Mọi request checkout hợp lệ được gửi đến endpoint trong thời gian đo.

Availability SLI:
  Good checkout requests / Eligible checkout requests
```

Với SLI latency, sự kiện tốt cần thỏa cả điều kiện thành công và ngưỡng thời gian:

```text
Good latency event:
  Checkout thành công trong <= 5 giây.

Latency SLI:
  Successful checkout requests completed within 5s
  / Eligible checkout requests
```

Cách định nghĩa này tránh một hệ thống có thể đạt latency tốt bằng cách trả lỗi nhanh. Request thất bại không được tính là good chỉ vì nó hoàn tất trong vài mili giây.

### Không thay đổi mẫu số để làm đẹp SLI

Nếu loại bỏ quá nhiều request khỏi mẫu số, SLI có thể trông tốt trong khi người dùng vẫn gặp lỗi. Hãy viết rõ các trường hợp loại trừ:

- Request sai cú pháp hoặc thiếu trường bắt buộc có thể được loại khỏi availability SLI của backend nếu đó là lỗi caller, nhưng cần theo dõi riêng để phát hiện client integration hỏng.
- Request bị từ chối do thiếu quyền có thể không phải lỗi availability, nhưng nếu lỗi IAM do cấu hình dịch vụ khiến người dùng hợp lệ bị từ chối thì đó là lỗi dịch vụ.
- Request bị người dùng chủ động hủy có thể được xử lý riêng, nhưng timeout do backend chậm không được gắn nhãn là user cancellation.
- Traffic test/synthetic chỉ nên loại khỏi SLI production nếu được nhận diện rõ và không dùng để che lỗi thật.

Không loại bỏ lỗi dependency, timeout, throttling hoặc cold start do nền tảng gây ra khỏi SLI chỉ vì chúng không nằm trong code Java.

## 4. Chọn loại SLI phù hợp với hành trình

Một hành trình có thể cần nhiều SLI để phản ánh các khía cạnh khác nhau.

| Loại SLI | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Availability | Người dùng có hoàn thành thao tác được không? | Tỷ lệ tạo đơn thành công |
| Latency | Có hoàn thành đủ nhanh không? | Tỷ lệ API trả kết quả trong 500 ms |
| Correctness | Kết quả có đúng không? | Tỷ lệ đơn hàng có tổng tiền và trạng thái hợp lệ |
| Freshness | Dữ liệu có được cập nhật kịp không? | Tỷ lệ sự kiện được phản ánh trong 60 giây |
| Completion | Công việc bất đồng bộ có kết thúc không? | Tỷ lệ export hoàn tất trước 5 phút |
| Durability | Yêu cầu đã được chấp nhận có bị mất không? | Tỷ lệ job được lưu bền vững và có trạng thái cuối |
| Coverage | Hệ thống có xử lý đủ phạm vi cần thiết không? | Tỷ lệ tenant/region có thể hoàn thành hành trình |

Không cần tạo SLO riêng cho mọi metric. Chọn những chỉ số có liên hệ trực tiếp với trải nghiệm hoặc cam kết sản phẩm. Một số metric nên dùng để chẩn đoán thay vì đặt thành mục tiêu dịch vụ.

## 5. SLO cho HTTP API

Với API đồng bộ, request thường có điểm bắt đầu và response rõ ràng. Một SLI availability có thể tính số request hợp lệ trả về kết quả thành công theo contract chia cho tổng request hợp lệ.

Ví dụ:

```text
Availability SLI =
  eligible requests with expected success outcome
  / eligible requests
```

Không nên định nghĩa mọi HTTP 2xx là thành công nếu response chỉ xác nhận tiếp nhận công việc. Với endpoint tạo export trả 202, thành công của request đồng bộ là job đã được lưu bền vững và trả job ID hợp lệ. Thành công của hành trình export là file hoàn tất trước deadline; đó là SLI riêng cho phần bất đồng bộ.

### Latency SLI

Có thể đo tỷ lệ request hoàn tất trong ngưỡng:

```text
Latency SLI =
  eligible requests completed within threshold
  / eligible requests
```

Ví dụ SLO: 99% request tra cứu trạng thái đơn hàng hoàn tất trong 400 ms trong 30 ngày.

Percentile như p95/p99 hữu ích để quan sát phân phối latency, nhưng SLO dạng tỷ lệ trong ngưỡng thường dễ liên hệ với error budget hơn. p99 có thể được theo dõi như diagnostic metric; đừng nhầm “p99 dưới 400 ms” với “99% request dưới 400 ms” nếu cách tổng hợp hoặc cửa sổ khác nhau.

### Correctness SLI

Một API có thể trả 200 nhưng trả sai dữ liệu. Với hành trình quan trọng, cần đo correctness bằng kiểm tra nghiệp vụ:

- Tổng tiền tính đúng.
- Trạng thái chuyển hợp lệ.
- Response gắn đúng tenant và resource.
- Idempotency key không tạo hai đơn hàng.
- Dữ liệu được ghi bền vững trước khi xác nhận.

Correctness thường cần business invariant, reconciliation hoặc sampled validation. Không chỉ dựa vào status code.

## 6. SLO cho message và event-driven function

Với queue hoặc stream, một record có thể được giao nhiều lần. Invocation thành công không đồng nghĩa message đã hoàn tất đúng một lần. Một consumer có thể trả thành công nhưng chỉ ghi nhận một phần tác dụng phụ; hoặc message được retry sau khi database đã commit.

Đối với hành trình bất đồng bộ, định nghĩa SLI theo **business operation/event**, không theo số lần invocation.

Ví dụ:

```text
Eligible event:
  Một yêu cầu export hợp lệ đã được ghi bền vững và có operationId.

Good event:
  File export hoàn tất, kiểm tra được và sẵn sàng tải
  trong vòng 5 phút từ thời điểm chấp nhận.

Completion SLI:
  Good export operations / Eligible export operations
```

Nếu một message được giao ba lần nhưng chỉ tạo một export thành công, mẫu số vẫn là một business operation, không phải ba invocation. Retry là chi tiết thực thi, không phải ba người dùng khác nhau.

### Định nghĩa deadline

Đối với async journey, phải có deadline hoặc cửa sổ hoàn tất:

- 95% thông báo được gửi trong 30 giây.
- 99% export hoàn tất trong 5 phút.
- 99,9% payment events được xử lý và phản ánh trạng thái trong 2 phút.

Một operation chưa hoàn tất khi hết deadline được tính là bad hoặc pending quá hạn theo quy tắc đã định. Không bỏ operation khỏi mẫu số chỉ vì nó vẫn đang ở trạng thái processing.

### Queue age không phải completion SLI

Metric queue age hoặc iterator age cho biết consumer đang tụt lại bao nhiêu, rất hữu ích để chẩn đoán. Nhưng nó không cho biết từng operation có hoàn tất đúng contract hay không. Một queue có age thấp vẫn có thể chứa message poison bị retry; queue age cao có thể ảnh hưởng một nhóm tenant cụ thể mà metric tổng thể che khuất.

Kết hợp:

- Business completion rate.
- Time-to-completion.
- Queue age/iterator age.
- Retry count và DLQ count.
- Tỷ lệ operation quá deadline.
- Tỷ lệ operation được đối soát thành công.

## 7. Theo dõi một hành trình xuyên nhiều invocation

Một operation có thể đi qua HTTP handler, queue producer, worker, webhook handler và database. Cần một định danh nghiệp vụ ổn định để nối các bước.

Ví dụ envelope event:

~~~json
{
  "operationId": "export-2026-00418",
  "eventId": "evt-91a2",
  "tenantId": "tenant-42",
  "eventType": "report.export.requested",
  "occurredAt": "2026-11-17T09:00:00Z",
  "schemaVersion": 1
}
~~~

- `operationId` định danh hành trình nghiệp vụ.
- `eventId` định danh một event cụ thể để deduplicate.
- `tenantId` giúp phân tích phạm vi tenant, nhưng cần được xác minh theo contract tin cậy.
- `traceparent` hoặc trace context có thể được truyền trong message attributes để nối distributed trace.

Không dùng operationId hoặc tenantId làm metric label có cardinality cao. Chúng phù hợp với log, trace hoặc event store có kiểm soát. Metric nên dùng dimension giới hạn như journey, outcome, region hoặc service version.

### Thời điểm bắt đầu và kết thúc

Ghi nhận timestamp ở nguồn tạo operation và timestamp hoàn tất cuối cùng. Dùng đồng hồ hệ thống có đồng bộ tốt; với thời gian đo trong một process, dùng monotonic clock. Khi so timestamp giữa nhiều service, cần tính đến clock skew và ưu tiên trace duration hoặc timestamp được chuẩn hóa.

Nếu một operation có thể được retry sau nhiều giờ, lưu mốc bắt đầu bền vững trong database/event store. Không dựa vào biến static hoặc thời gian tạo instance.

## 8. Tránh đếm sai do retry, duplicate và cancellation

Đây là phần quan trọng với serverless at-least-once.

### Retry

Nếu lần đầu worker timeout nhưng downstream đã commit, lần retry có thể thấy operation đã hoàn tất. Business outcome chỉ nên được tính một lần. Dùng operation state và idempotency marker để xác định kết quả cuối cùng.

### Duplicate delivery

Cùng một event có thể được giao lại. Không tăng số eligible business operations mỗi khi handler nhận message. Deduplicate theo eventId hoặc operationId tùy contract.

### Partial batch failure

Với stream consumer có partial batch response, một số record thành công và record khác được retry. Đếm outcome theo từng record/business operation, không coi toàn bộ invocation là một event tốt hoặc xấu.

### Cancellation

Phân biệt user cancellation hợp lệ với cancellation do timeout hoặc shutdown của function. Nếu backend chủ động hủy vì quá tải, đây có thể là lỗi dịch vụ và cần tính vào SLI theo contract. Không gắn mọi trạng thái CANCELLED thành excluded.

### Operation không có kết quả cuối

Nếu event bị đưa vào DLQ hoặc hết retry, operation vẫn phải có trạng thái cuối có thể quan sát. Nếu không, nó có thể biến mất khỏi báo cáo và làm SLI sai. Cần reconciliation để phát hiện operation đã accepted nhưng không có completion record sau deadline.

## 9. Chọn cửa sổ SLO và mục tiêu

SLO thường được tính trên rolling window, ví dụ 7 ngày hoặc 30 ngày. Cửa sổ dài giúp đo độ tin cậy ổn định; cửa sổ ngắn giúp phản ứng nhanh hơn với regression.

Một SLO cần xác định:

- SLI chính xác và công thức.
- Mục tiêu phần trăm.
- Cửa sổ thời gian.
- Nguồn dữ liệu và quy tắc deduplication.
- Điều kiện loại trừ.
- Cách xử lý event chưa hoàn tất.
- Phạm vi dịch vụ, tenant hoặc region.
- Owner chịu trách nhiệm.

Ví dụ:

| Hành trình | SLI | SLO minh họa | Cửa sổ |
|---|---|---:|---|
| Đăng nhập | Tỷ lệ login hợp lệ hoàn tất trong 1 giây | 99,9% | 30 ngày |
| Tra cứu đơn hàng | Tỷ lệ request thành công trong 500 ms | 99,5% | 30 ngày |
| Export báo cáo | Tỷ lệ export hoàn tất trong 5 phút | 99% | 30 ngày |
| Xử lý payment event | Tỷ lệ event được phản ánh trạng thái trong 2 phút | 99,9% | 30 ngày |

Đây là mục tiêu minh họa, không phải mặc định cho mọi sản phẩm. Mục tiêu phải dựa trên nhu cầu người dùng, baseline, khả năng kỹ thuật và chi phí đạt được.

### Không đặt SLO 100% một cách tùy tiện

Mục tiêu 100% thường không thực tế với hệ thống phân tán có dependency và network failure. SLO quá cao có thể tạo chi phí lớn, làm giảm tốc độ phát triển mà không mang lại giá trị tương ứng cho người dùng.

Hãy hỏi: người dùng có thực sự nhận thấy khác biệt giữa 99,9% và 99,95% không? Chi phí và độ phức tạp để đạt mục tiêu tăng thêm là bao nhiêu? Một số hành trình như thanh toán có thể cần độ tin cậy cao hơn trang tìm kiếm, nhưng phải dựa trên tác động thực tế.

## 10. Error budget là gì?

Error budget là phần lỗi được phép xảy ra theo SLO trong cửa sổ đo.

Nếu SLO availability là 99,9%, error budget là:

```text
Error budget = 100% - 99.9% = 0.1%
```

Với 100.000 eligible operations trong cửa sổ, ngân sách lỗi tương ứng là:

```text
100,000 × 0.1% = 100 bad operations
```

Nếu đã có 60 bad operations, còn 40 operation trong ngân sách. Nếu số bad vượt 100, SLO không đạt trong cửa sổ đó.

Công thức tổng quát cho request-based SLO:

[
B = N 	imes (1 - S)
]

Trong đó:

- (B): số bad events được phép.
- (N): số eligible events.
- (S): SLO dưới dạng tỷ lệ, ví dụ 0,999.

Với time-based SLO, cách tính có thể dựa trên tổng phút hoặc khoảng thời gian dịch vụ không đạt điều kiện. Không trộn lẫn error budget request-based với downtime minutes nếu SLI và denominator khác nhau.

### Ví dụ ngân sách theo mục tiêu

| SLO | Error budget | Bad events trên 100.000 operations |
|---:|---:|---:|
| 99% | 1% | 1.000 |
| 99,5% | 0,5% | 500 |
| 99,9% | 0,1% | 100 |
| 99,95% | 0,05% | 50 |
| 99,99% | 0,01% | 10 |

Error budget không phải mục tiêu để cố tình sử dụng hết. Nó là công cụ cân bằng độ tin cậy và tốc độ thay đổi.

## 11. Burn rate và tốc độ tiêu thụ error budget

Burn rate cho biết tốc độ lỗi hiện tại so với tốc độ được phép theo SLO.

```text
Burn rate = observed error ratio / allowed error ratio
```

Với SLO 99,9%, error ratio cho phép là 0,1%. Nếu trong một cửa sổ quan sát có error ratio 1%, burn rate là 10 lần.

Burn rate 1 nghĩa là tiêu thụ ngân sách đúng tốc độ tương ứng với cửa sổ SLO. Burn rate 10 nghĩa là ngân sách bị tiêu thụ nhanh gấp 10 lần. Nếu tình trạng đó kéo dài, hệ thống sẽ cạn error budget sớm.

### Ví dụ

SLO 99,9% trong 30 ngày:

- Error ratio cho phép: 0,1%.
- Observed error ratio trong một giờ: 1,44%.
- Burn rate: 1,44% / 0,1% = 14,4.

Một giờ ở burn rate 14,4 tiêu thụ xấp xỉ 2% ngân sách 30 ngày, nếu tỷ lệ đó tiếp tục ổn định. Đây là tín hiệu đáng chú ý dù một giờ chưa đủ để kết luận SLO tháng đã vi phạm.

### Multi-window burn-rate alert

Dùng cả cửa sổ ngắn và dài giúp tránh cảnh báo do một spike rất ngắn, đồng thời phát hiện sự cố đang tiếp diễn.

Ví dụ chính sách minh họa cho SLO 30 ngày:

| Cảnh báo | Cửa sổ ngắn | Cửa sổ dài | Ý nghĩa |
|---|---|---|---|
| Critical | 5 phút ở burn rate rất cao | 1 giờ vẫn ở burn rate cao | Có thể đang tiêu thụ nhanh một phần đáng kể ngân sách |
| Warning | 30 phút ở burn rate trung bình-cao | 6 giờ duy trì burn rate đáng kể | Cần điều tra trước khi ngân sách cạn |
| Budget low | Error budget còn dưới ngưỡng nội bộ | Theo rolling window | Cần điều chỉnh mức rủi ro phát hành |

Ngưỡng cụ thể cần dựa trên SLO window, tỷ lệ traffic, mức độ ảnh hưởng và khả năng phản ứng của đội. Tránh sao chép một con số burn rate mà không tính xem nó tiêu thụ bao nhiêu phần trăm budget trong thời gian tương ứng.

## 12. Đưa error budget vào quyết định phát hành

Error budget giúp đội sản phẩm và kỹ thuật có quy tắc chung khi quyết định tiếp tục phát hành hay ưu tiên độ tin cậy.

Một policy ví dụ:

| Trạng thái budget | Hành động |
|---|---|
| Budget còn nhiều, burn rate bình thường | Tiếp tục phát hành theo quy trình chuẩn |
| Budget giảm nhanh | Tăng kiểm tra, thu hẹp canary, yêu cầu theo dõi sau deploy |
| Budget gần cạn | Tạm hoãn thay đổi rủi ro cao; ưu tiên reliability work |
| Budget cạn hoặc SLO liên tục vi phạm | Dừng release tính năng không khẩn cấp, tập trung khắc phục nguyên nhân |
| Security/data-loss incident | Xử lý theo incident policy, không chờ budget |

Policy cần nêu rõ ai có quyền quyết định ngoại lệ, cách ghi nhận rủi ro và điều kiện mở lại release. Error budget không nên biến thành cơ chế phạt cá nhân hoặc lý do che giấu incident.

Không phải mọi thay đổi đều có cùng rủi ro. Một bản vá bảo mật khẩn cấp có thể cần triển khai ngay cả khi budget thấp, nhưng cần kế hoạch giảm rủi ro và giám sát chặt hơn.

## 13. Instrumentation trong Java serverless

Metric cần được ghi ở nơi biết kết quả nghiệp vụ. Function runtime metric thường chỉ cho biết invocation thành công hoặc lỗi; nó không biết order có được thanh toán hay export có hoàn tất trước deadline.

Có thể dùng Micrometer hoặc OpenTelemetry để instrument journey. Ví dụ Micrometer đơn giản:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class CheckoutSliRecorder {

    private final MeterRegistry registry;

    public CheckoutSliRecorder(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String outcome,
            long elapsedNanos,
            boolean withinLatencyTarget) {

        registry.counter(
                "user_journey_operations_total",
                "journey", "checkout",
                "outcome", outcome
        ).increment();

        registry.counter(
                "user_journey_good_events_total",
                "journey", "checkout",
                "good", Boolean.toString(
                        "success".equals(outcome)
                                && withinLatencyTarget)
        ).increment();

        Timer.builder("user_journey_duration")
                .tag("journey", "checkout")
                .tag("outcome", outcome)
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Ở đây, outcome chỉ nên nhận một tập giá trị hữu hạn như success, validation_error, dependency_error hoặc timeout. Trong production, hãy định nghĩa rõ loại lỗi nào thuộc eligible denominator và loại nào là bad event. Ví dụ trên minh họa cách ghi metric; không tự động biến mọi outcome thành một SLI đúng nếu chưa thống nhất semantics.

Gọi `record()` đúng một lần cho mỗi eligible business operation tại điểm ghi nhận authoritative. Request bị loại khỏi mẫu số theo định nghĩa SLI cần metric riêng, không gọi recorder này. Khi đó tổng `user_journey_operations_total` là denominator và counter `user_journey_good_events_total{good="true"}` là numerator.

### Đo một operation trong handler

```java
long started = System.nanoTime();

try {
    CheckoutResult result = checkoutService.createOrder(command);

    long elapsedNanos = System.nanoTime() - started;
    boolean withinTarget = elapsedNanos <= targetNanos;

    sliRecorder.record(
            result.isSuccessful() ? "success" : "business_failure",
            elapsedNanos,
            withinTarget);

    return toResponse(result);
} catch (DependencyTimeoutException ex) {
    long elapsedNanos = System.nanoTime() - started;
    sliRecorder.record(
            "timeout",
            elapsedNanos,
            false);
    throw ex;
}
```

Đoạn minh họa cần được đặt ở ranh giới nơi biết operation có hợp lệ và outcome cuối cùng. Nếu validation lỗi do caller, hãy ghi metric riêng hoặc loại theo định nghĩa SLI. Nếu dependency timeout, đây thường là bad event của hành trình.

Không ghi cùng một operation nhiều lần ở cả controller, service và repository vào cùng counter. Chọn một điểm ghi nhận authoritative để tránh double counting.

### Metric label phải có cardinality thấp

Không dùng các giá trị sau làm metric labels:

- user ID.
- tenant ID nếu số tenant lớn.
- order ID hoặc operation ID.
- email, URL đầy đủ hoặc request ID.
- message payload hoặc exception message.

Các giá trị đó phù hợp hơn với log hoặc trace có kiểm soát. Metric labels nên là journey, outcome, region, service/revision hoặc nhóm plan có số lượng giới hạn.

## 14. Instrumentation cho async journey

Với async workflow, cần lưu trạng thái operation bền vững. Một bảng hoặc event store có thể chứa:

~~~sql
CREATE TABLE user_operations (
    operation_id VARCHAR(128) PRIMARY KEY,
    journey      VARCHAR(64) NOT NULL,
    accepted_at  TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    status       VARCHAR(32) NOT NULL,
    result_code  VARCHAR(64) NULL
);
~~~

Khi API chấp nhận công việc, tạo operation record và publish message theo outbox pattern nếu cần bảo đảm database commit và event publish nhất quán.

Worker cập nhật trạng thái terminal khi công việc hoàn tất hoặc thất bại. Một evaluator hoặc stream processor có thể tính completion SLI:

- Đếm operation được accepted trong cohort/cửa sổ.
- Xác định operation hoàn tất tốt trước deadline.
- Tính operation thất bại, quá hạn hoặc vào DLQ là bad theo policy.
- Không đếm lại operation do message retry.
- Đối soát operation không có trạng thái terminal sau deadline.

Không chỉ dùng thời gian message nằm trong queue làm end-to-end duration. Journey có thể bắt đầu trước khi message được publish và kết thúc sau nhiều bước xử lý.

### Eventual consistency của SLI

Completion SLI có độ trễ vì cần chờ operation hoàn tất hoặc deadline trôi qua. Dashboard gần thời gian thực có thể hiển thị hai nhóm:

- **Provisional:** operation vẫn trong thời gian deadline, chưa đủ dữ liệu kết luận.
- **Finalized:** operation đã thành công hoặc đã quá deadline/terminal failure.

Nếu tính SLI chỉ trên operation đã hoàn tất, các job đang bị kẹt có thể bị bỏ khỏi mẫu số và làm tỷ lệ đẹp giả tạo. Phải giữ chúng trong cohort và đánh dấu bad khi vượt deadline.

## 15. Distributed tracing nối hành trình

Trace giúp tìm nguyên nhân của một operation chậm hoặc thất bại qua nhiều function và dependency.

Với HTTP request, dùng OpenTelemetry context propagation qua header chuẩn như `traceparent`. Khi publish message, inject trace context vào message attributes; consumer extract context để tạo span liên quan. Nếu workflow kéo dài hoặc fan-out, có thể dùng span links thay vì tạo một trace cha-con quá dài.

Một trace có thể gồm:

- API Gateway/HTTP ingress.
- Java function handler.
- Database transaction.
- Queue publish.
- Queue receive/consumer invocation.
- External API call.
- Webhook callback.
- Final state update.

Trace hỗ trợ chẩn đoán latency và dependency, nhưng không thay thế SLI. Sampling có thể bỏ qua một số trace; SLI cần metric/event accounting đầy đủ hoặc một nguồn dữ liệu có thể đối soát.

Không dùng trace count làm denominator của SLO nếu trace được sample.

## 16. Dashboard SLO

Một dashboard hữu ích nên trả lời được ba câu hỏi: người dùng có đang gặp vấn đề không, error budget còn bao nhiêu, và thành phần nào gây ra vấn đề?

Các panel gợi ý:

1. SLI hiện tại và SLO target.
2. Good events, bad events và eligible events.
3. Error budget còn lại theo số lượng và phần trăm.
4. Burn rate ở các cửa sổ ngắn/dài.
5. Latency distribution p50/p95/p99 và tỷ lệ dưới threshold.
6. Completion time của async operation.
7. Queue age/iterator age, retry và DLQ.
8. Error breakdown theo service, region và release.
9. Business outcome như checkout success hoặc export completion.
10. SLI theo journey/tenant cohort quan trọng với cardinality được kiểm soát.

Metric tổng thể có thể che lỗi một region hoặc một nhóm khách hàng. Hãy phân tích theo các phân đoạn có ý nghĩa, nhưng tránh tạo metric dimension không giới hạn. Dùng log/trace để drill down đến một tenant hoặc operation cụ thể.

## 17. Cảnh báo theo SLO thay vì chỉ theo CPU

CPU, memory và invocation count là tín hiệu hạ tầng. Cảnh báo người trực nên ưu tiên triệu chứng ảnh hưởng đến người dùng và error budget.

Ví dụ:

- Alert khi checkout availability SLI giảm.
- Alert khi completion SLI của export burn budget nhanh.
- Alert khi operation quá deadline tăng.
- Alert khi queue age tăng và completion latency cùng xấu đi.
- Alert khi DLQ tăng đột biến hoặc có operation bị mất trạng thái cuối.
- Alert khi một release làm business success rate giảm.

Có thể giữ alert CPU/memory như cảnh báo chẩn đoán hoặc capacity. Nhưng CPU 90% không nhất thiết là incident nếu SLI vẫn tốt; ngược lại CPU thấp không chứng minh dịch vụ khỏe nếu function bị IAM deny hoặc dependency lỗi.

### Alert cần có hành động rõ

Một alert tốt nên có:

- Hành trình và SLI bị ảnh hưởng.
- Phạm vi region/revision nếu xác định được.
- Error budget/burn rate hiện tại.
- Link dashboard và trace/log liên quan.
- Hướng dẫn kiểm tra dependency, queue, release và config.
- Owner và mức độ ưu tiên.

Tránh alert chỉ nói “Lambda errors increased” mà không cho biết người dùng bị ảnh hưởng thế nào.

## 18. Segmentation và fairness

Một SLO tổng thể có thể che lỗi chỉ xảy ra với tenant lớn, region xa hoặc một loại client. Cần phân tích các nhóm có ý nghĩa:

- Region hoặc zone.
- API version hoặc release revision.
- Journey type.
- Tenant tier/plan theo nhóm giới hạn.
- Client platform hoặc version.
- Loại operation hoặc payment provider.

Nếu một tenant quan trọng bị lỗi trong khi hàng triệu tenant khác vẫn tốt, SLI tổng có thể không phản ánh trải nghiệm của họ. Có thể đặt SLO riêng cho nhóm tier hoặc hành trình quan trọng nếu có lý do sản phẩm.

Không đặt SLO cho từng tenant theo mặc định nếu số lượng lớn và traffic thấp; dữ liệu ít tạo tỷ lệ biến động mạnh. Dùng alert theo anomaly, support signal hoặc aggregate cohort cho tenant nhỏ.

## 19. Những lỗi thiết kế SLI/SLO thường gặp

- **Dùng invocation success làm user success:** function trả 200/202 nhưng workflow phía sau có thể thất bại; đo kết quả cuối.
- **Đếm invocation thay vì business operation:** retry và duplicate làm mẫu số sai; deduplicate theo operation/event ID.
- **Bỏ operation đang pending:** job bị kẹt biến mất khỏi SLI; giữ trong cohort và đánh dấu bad sau deadline.
- **Chỉ đo latency trung bình:** tail latency có thể rất xấu; đo tỷ lệ dưới threshold và phân phối percentile.
- **Coi mọi 2xx là thành công:** 202 chỉ xác nhận tiếp nhận; xác định outcome theo contract.
- **Loại mọi 4xx:** một số lỗi 4xx do IAM/config của service hoặc auth flow có thể ảnh hưởng người dùng hợp lệ; phân loại rõ.
- **Đặt SLO 100%:** mục tiêu không thực tế có thể tạo chi phí không cần thiết; chọn theo trải nghiệm và risk.
- **Đặt SLO mà không có owner:** không ai chịu trách nhiệm khi budget cạn; gắn owner và policy.
- **Chỉ theo dõi CPU/queue depth:** đây là diagnostic metrics; cần business SLI.
- **Dùng trace sampled làm denominator:** trace có thể bị sample; dùng metric/event accounting đầy đủ.
- **Dùng tenantId/orderId làm metric label:** cardinality tăng mạnh; dùng logs/traces cho drill-down.
- **Không nối async trace context:** khó chẩn đoán end-to-end; truyền context qua message.
- **Không tính clock skew:** duration giữa service có thể sai; dùng monotonic duration và timestamp được đồng bộ.
- **Không định nghĩa cancellation:** lỗi backend có thể bị loại nhầm; phân biệt user cancel và system timeout.
- **Không đối soát operation mất trạng thái:** job có thể biến mất khỏi báo cáo; có reconciliation.

## 20. Quy trình xây dựng SLO cho Java serverless

Có thể triển khai theo trình tự:

1. Chọn một hành trình người dùng quan trọng, có điểm bắt đầu và kết thúc rõ.
2. Vẽ các HTTP, database, queue, worker và external dependency trong hành trình.
3. Xác định business operation ID và cách deduplicate retry/duplicate.
4. Định nghĩa eligible events, good events, bad events và các trường hợp loại trừ.
5. Chọn SLI phù hợp: availability, latency, correctness, freshness hoặc completion.
6. Với async flow, xác định deadline và cách xử lý operation pending/DLQ.
7. Chọn SLO target và rolling window dựa trên nhu cầu người dùng, baseline và chi phí.
8. Tính error budget theo denominator của SLI.
9. Instrument metric ở điểm biết outcome nghiệp vụ; dùng trace để chẩn đoán.
10. Xây dashboard SLI, budget và burn rate.
11. Thiết lập multi-window alert và hành động ứng phó.
12. Đưa error budget vào release policy và incident review.
13. Kiểm thử duplicate, retry, timeout, event mất, operation quá deadline và clock skew.
14. Rà soát định nghĩa SLI khi sản phẩm hoặc contract thay đổi.

Bắt đầu với một vài hành trình quan trọng sẽ dễ duy trì hơn việc tạo hàng chục SLO không có người sở hữu.

## 21. Ví dụ hoàn chỉnh: SLO cho hành trình tạo đơn

Giả sử một hệ thống có Java HTTP function nhận checkout, ghi order và phát message để worker xử lý thanh toán.

Định nghĩa:

- **Journey:** checkout.
- **Start:** request hợp lệ được nhận tại API.
- **Eligible:** request vượt qua validation nghiệp vụ cơ bản và có tenant/customer hợp lệ.
- **Good:** order được tạo đúng một lần, trạng thái cuối cùng là PAID hoặc một trạng thái kết quả được contract chấp nhận, và kết quả được phản ánh cho người dùng trong 2 phút.
- **Bad:** payment failure do lỗi hệ thống, operation quá deadline, message vào DLQ hoặc trạng thái không thể đối soát.
- **SLO:** 99,9% eligible checkout operations đạt good trong rolling 30 ngày.
- **Latency companion SLI:** 99% request được accept và trả operation ID trong 500 ms.
- **Diagnostic metrics:** API p95, queue age, worker retry, provider latency, DB errors và DLQ.

Nếu có 50.000 checkout eligible trong 30 ngày, error budget của SLO 99,9% là:

```text
50,000 × 0.001 = 50 bad checkout operations
```

Nếu có 30 operation quá deadline, 12 payment operation lỗi do dependency và 8 operation vào DLQ, tổng cộng 50 bad operations; ngân sách đã dùng hết. Không được tính lại cùng operation khi nó được retry ba lần.

Đây là ví dụ policy. Trong thực tế, cần quyết định payment decline do người dùng/issuer từ chối có phải bad service event hay là kết quả nghiệp vụ hợp lệ. Nếu payment provider trả decline đúng contract, có thể coi đó là business outcome hợp lệ; nếu provider timeout hoặc integration lỗi, đó thường là bad event. Định nghĩa phải phản ánh đúng cam kết sản phẩm.

## 22. Ghi nhớ

SLI đo chất lượng người dùng thực sự trải nghiệm; SLO đặt mục tiêu cho SLI trong một cửa sổ thời gian; error budget lượng hóa mức lỗi được phép trước khi mục tiêu bị vi phạm. Với Java serverless, cần đo theo business operation và hành trình end-to-end, không chỉ theo invocation của function.

HTTP 202 có thể chỉ là tiếp nhận công việc. Với queue và event, retry/duplicate không tạo thêm business operation, còn pending quá deadline phải được tính là bad. Dùng operation ID để nối các bước, metric có cardinality thấp để tính SLI, trace để tìm nguyên nhân và reconciliation để phát hiện công việc bị mất.

Burn rate cho biết error budget đang bị tiêu thụ nhanh đến đâu. Kết hợp cảnh báo theo nhiều cửa sổ, dashboard theo journey và release policy rõ ràng để đội có thể cân bằng tốc độ phát hành với độ tin cậy. SLO có giá trị khi nó gắn với trải nghiệm người dùng, có định nghĩa đo lường kiểm chứng được và dẫn đến hành động vận hành cụ thể.

