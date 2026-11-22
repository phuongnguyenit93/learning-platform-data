# Tính chi phí API gateway, workflow, queue và lưu trữ

Một ứng dụng serverless không chỉ phát sinh chi phí từ thời gian chạy Java function. Một request HTTP có thể đi qua API gateway, tạo execution trong workflow engine, gửi nhiều message vào queue, đọc/ghi object hoặc database, rồi sinh log, metric và trace. Mỗi dịch vụ tính phí theo một đơn vị khác nhau: request, state transition, execution duration, message operation, dung lượng lưu trữ, số lần truy xuất, data transfer hoặc mức capacity được giữ sẵn.

Nếu chỉ nhìn hóa đơn Lambda/function, nhóm có thể đánh giá thấp chi phí thực tế của một business transaction. Một workflow có nhiều bước, retry liên tục hoặc ghi nhiều object nhỏ có thể tốn hơn phần compute. Bài toán FinOps là liên kết chi phí kỹ thuật với kết quả nghiệp vụ, xác định driver lớn nhất, dự báo theo tải và tối ưu mà không làm giảm độ tin cậy hay SLA.

Trong module **CLOUD_SERVERLESS**, người học phát triển Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trigger, trạng thái, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Bài này tập trung vào cách tính và phân bổ chi phí API gateway, workflow, queue và storage trong một hệ thống serverless.

## 1. Nhìn toàn bộ chi phí của một request

Một request có thể tạo ra nhiều hoạt động tính phí:

1. API gateway nhận request, xác thực, áp dụng policy và chuyển tiếp.
2. Java function được invoke và tính phí theo request cùng thời gian/tài nguyên thực thi.
3. Function khởi chạy workflow hoặc gọi workflow engine.
4. Workflow đi qua nhiều state/step, có thể chờ timer, retry hoặc gọi service khác.
5. Function gửi message đến queue hoặc event bus.
6. Consumer nhận message, xử lý và xác nhận message.
7. Ứng dụng đọc/ghi object, database hoặc cache.
8. Dữ liệu đi qua network, giữa AZ/Region hoặc ra Internet.
9. Log, metric và trace được ingest, lưu giữ và truy vấn.
10. Một số thành phần có capacity được giữ sẵn như provisioned concurrency, gateway cache, broker hoặc database capacity.

Do đó, chi phí nên được nhìn theo **end-to-end transaction**, không chỉ theo một service.

~~~mermaid
flowchart LR
    U[Client] --> G[API Gateway]
    G --> F[Java Function]
    F --> W[Workflow]
    W --> Q[Queue / Event Bus]
    Q --> C[Consumer Function]
    C --> S[Storage / Database]
    G -. usage .-> M[Cost allocation]
    F -. usage .-> M
    W -. usage .-> M
    Q -. usage .-> M
    C -. usage .-> M
    S -. usage .-> M
~~~

Một hóa đơn có thể gom nhiều tài nguyên cùng loại vào một dòng. Muốn biết một API hoặc một khách hàng tiêu thụ bao nhiêu, cần kết hợp billing export, resource tags, usage metrics và dữ liệu nghiệp vụ.

## 2. Phân biệt giá niêm yết, usage và tổng chi phí

Khi đọc bảng giá cloud, cần phân biệt:

- **Unit price:** đơn giá cho một đơn vị như 1 triệu request, 1 GB-month hoặc 1.000 state transitions.
- **Usage quantity:** số đơn vị thực tế được tính trong kỳ.
- **Tier/discount:** mức giá theo bậc sử dụng, commitment, enterprise discount hoặc free tier.
- **Additional charge:** data transfer, retrieval, logging, encryption key, support hoặc resource phụ.
- **Minimum/rounding rule:** cách làm tròn thời gian, kích thước payload hoặc thời hạn lưu trữ tối thiểu.
- **Tax/currency:** thuế, tiền tệ và tỷ giá trên hóa đơn.

Một service có giá request thấp vẫn có thể đắt nếu mỗi business operation tạo hàng chục request, dữ liệu lớn hoặc nhiều lần retry. Ngược lại, service có đơn giá cao hơn có thể giảm tổng chi phí nếu giúp gom batch, giảm network round-trip hoặc rút ngắn workflow.

Không dùng một bảng giá cũ làm chuẩn lâu dài. Giá, free tier, tier, Region, loại API và cách tính của provider thay đổi theo sản phẩm. Hãy lấy đơn giá từ bảng giá chính thức hoặc calculator cho đúng Region, class, protocol và billing option ở thời điểm lập forecast.

## 3. Mô hình tính chi phí end-to-end

Một mô hình đơn giản:

\[
C_{total} =
C_{gateway} +
C_{compute} +
C_{workflow} +
C_{queue} +
C_{storage} +
C_{network} +
C_{observability} +
C_{other}
\]

Trong đó:

- \(C_{gateway}\): request, data processing, cache và tính năng gateway.
- \(C_{compute}\): function invocations, duration, memory/CPU, provisioned capacity.
- \(C_{workflow}\): state transitions hoặc execution request/duration.
- \(C_{queue}\): publish/send, receive, acknowledge/delete, retention hoặc throughput.
- \(C_{storage}\): dung lượng, operations, retrieval, lifecycle, replication.
- \(C_{network}\): data transfer, NAT, private connectivity, cross-AZ/Region và Internet egress.
- \(C_{observability}\): log ingestion/retention, metrics, traces và query.
- \(C_{other}\): KMS, secrets, WAF, DNS, support hoặc dịch vụ phụ trợ.

Nếu có nhiều loại workload, tách công thức theo từng luồng. Ví dụ API đọc, API ghi, batch consumer và workflow thanh toán có thể có cost profile rất khác nhau.

### Công thức tổng quát theo usage

Với mỗi thành phần \(i\):

\[
C_i = Q_i \times P_i
\]

Trong đó \(Q_i\) là lượng usage tính phí và \(P_i\) là đơn giá tương ứng. Nếu có tier:

\[
C_i = \sum_{k=1}^{n} Q_{i,k} \times P_{i,k}
\]

Không nhân toàn bộ usage với một đơn giá duy nhất nếu bảng giá có bậc, free allowance hoặc mức tối thiểu.

## 4. Đơn vị đo và quy đổi thường gặp

| Đơn vị | Ý nghĩa | Ví dụ |
|---|---|---|
| Request/API call | Một request được gateway/service xử lý | HTTP request |
| Invocation | Một lần function được gọi | Java handler execution |
| GB-second hoặc vCPU-second | Tài nguyên compute nhân thời gian | Memory/CPU trong một invocation |
| State transition | Một lần workflow chuyển state | Task, Choice, Wait hoặc state khác theo engine |
| Execution | Một lần chạy workflow | Một workflow run |
| Message operation | Gửi, nhận, xác nhận hoặc thao tác message | Send/Receive/Delete |
| Payload unit | Đơn vị kích thước message được billing | Kích thước theo block của provider |
| GB-month | Dung lượng lưu trữ trung bình theo thời gian | 100 GB lưu trong tháng |
| Storage request | Thao tác đọc/ghi/list/copy | PUT, GET, LIST |
| Retrieval unit | Dữ liệu lấy từ storage class | GB retrieved |
| Data transfer | Dữ liệu đi giữa network scope | Internet egress, cross-Region |
| Log ingestion | Dữ liệu telemetry được thu thập | GB log ingested |

Không phải provider nào cũng tính tất cả các đơn vị trên. Một số queue tính request theo payload size unit; một số event bus tính event ingestion/delivery; managed Kafka có thể tính broker capacity, storage và network. Phải map từng dịch vụ cụ thể sang đúng billing dimension.

## 5. Tính chi phí API gateway

API gateway có thể tính phí theo:

- Số request nhận hoặc xử lý.
- Loại API/protocol và tier sản phẩm.
- Data transfer hoặc payload size.
- Cache capacity và thời gian cache chạy.
- WebSocket connection và message nếu dùng WebSocket.
- Private networking, custom domain hoặc feature bổ sung tùy provider.
- WAF, authorization, logging và monitoring có thể được tính ở dịch vụ riêng.

### Công thức request-based

Nếu gateway tính theo số request:

\[
C_{gateway,request} =
\frac{N_{requests}}{U} \times P_U
\]

Trong đó:

- \(N_{requests}\): tổng request trong kỳ.
- \(U\): số request trong một billing unit, ví dụ 1.000 hoặc 1.000.000.
- \(P_U\): giá cho billing unit đó.

Nếu có nhiều loại API hoặc tier, tính riêng từng nhóm.

### Ví dụ

Một API nhận 12 triệu request trong tháng. Giả sử bảng giá của môi trường minh họa quy định đơn giá là 1,20 USD cho mỗi 1 triệu request:

\[
C = \frac{12.000.000}{1.000.000} \times 1,20
= 14,40\ USD
\]

Đây chỉ là đơn giá giả định để minh họa phép tính, không phải báo giá của AWS, Azure, Google Cloud hay provider nào. Tổng chi phí thực tế có thể cộng data transfer, cache, WAF, logging và các tính năng khác.

### Đừng nhầm request với business transaction

Một lần người dùng bấm “Tạo đơn hàng” có thể tạo:

- 1 request POST qua gateway.
- 1 request GET để kiểm tra trạng thái.
- 1 request polling mỗi vài giây.
- 1 callback hoặc webhook.
- 1 request retry từ client nếu response timeout.

Nếu chỉ đếm số đơn hàng, bạn sẽ bỏ sót request do polling/retry. Hãy đo cả request per business transaction.

### REST, HTTP và WebSocket API

Một số provider có nhiều loại gateway với mức giá và feature khác nhau. Chẳng hạn, API REST có thể có policy, transformation hoặc integration khác với HTTP API; WebSocket tính theo connection/message duration hoặc message count. Không chọn loại chỉ dựa vào đơn giá. So sánh thêm authorization, throttling, request validation, private integration, observability và khả năng vận hành.

### Cache gateway

Cache có thể giảm request xuống backend và giảm compute/database usage. Nhưng cache thường có chi phí capacity theo thời gian, kể cả lúc ít traffic. Cần so sánh:

\[
Savings_{cache} =
C_{backend\ avoided} - C_{cache} - C_{invalidation}
\]

Đánh giá cache hit ratio, dữ liệu stale, TTL, cache key cardinality và chi phí invalidation. Không cache dữ liệu theo user/tenant nếu key không phân tách đúng; cache leak có thể gây lỗi bảo mật nghiêm trọng.

## 6. Tính chi phí workflow và orchestration

Workflow engine có thể tính theo một hoặc nhiều chiều:

- Số lần workflow execution bắt đầu.
- Số state transition hoặc step transition.
- Thời gian execution hoặc duration theo memory/resource.
- Số task/activity invocation.
- Callback, timer, event hoặc integration operation.
- Data transfer và logging.
- Retry làm phát sinh thêm transition hoặc invocation.

### Mô hình transition-based

Với engine tính theo state transition:

\[
C_{workflow} =
N_{transitions} \times P_{transition}
\]

Nếu có free allowance hoặc tier, trừ/áp dụng theo đúng bảng giá trước khi tính.

Một workflow gồm 8 state được thực hiện 100.000 lần có thể tạo khoảng 800.000 transition nếu mỗi execution đi qua cả 8 state đúng một lần. Nhưng thực tế cần cộng branch, retry, catch/fallback, loop, compensation và các state được chạy lại.

### Mô hình request/duration-based

Một số workflow service hoặc execution mode có thể tính theo request, execution duration, memory hoặc số event. Khi đó:

\[
C_{workflow} =
N_{executions} \times P_{execution}
+
T_{billed} \times P_{duration}
\]

Cần đọc đúng pricing model của Standard/Express hoặc loại workflow tương đương. Không áp dụng công thức state transition cho mọi engine.

### Ví dụ workflow transition

Một workflow xử lý đơn hàng có đường đi thành công:

1. ValidateOrder
2. ReserveInventory
3. AuthorizePayment
4. CreateShipment
5. NotifyCustomer
6. MarkCompleted

Mỗi execution tạo 6 transitions. Nếu 50.000 đơn hàng đi qua đường thành công:

\[
N_{transitions} = 50.000 \times 6 = 300.000
\]

Nếu 4% workflow retry một task thêm 2 lần và mỗi lần retry tạo thêm 1 transition, số transition bổ sung:

\[
50.000 \times 4\% \times 2 = 4.000
\]

Tổng ước lượng:

\[
N_{total} = 300.000 + 4.000 = 304.000
\]

Đây là mô hình minh họa đơn giản. Một engine có thể tạo thêm event/transition cho retry scheduling, wait, catch, timeout hoặc callback; cần đếm theo execution history thực tế.

### Wait state và workflow dài hạn

Một workflow chờ 24 giờ không nhất thiết bị tính phí compute liên tục như một function giữ thread ngủ. Tuy nhiên, workflow engine có thể tính transition lúc vào Wait, lúc resume hoặc execution duration tùy loại dịch vụ. Function không nên giữ invocation mở để chờ timer dài nếu có durable workflow/timer service phù hợp.

Phân biệt thời gian business flow tồn tại với thời gian compute được tính phí. Một workflow sống lâu có thể có chi phí thấp nếu phần lớn thời gian là durable wait; ngược lại, một workflow ngắn có hàng trăm state transitions có thể tốn nhiều hơn dự kiến.

## 7. Retry và error handling làm tăng workflow cost

Retry tạo thêm hoạt động:

- Workflow transition hoặc event.
- Function invocation.
- Queue receive/visibility cycle.
- Database/API call.
- Log/trace ingestion.
- Data transfer.

Một lỗi downstream kéo dài có thể khiến mỗi business transaction tạo ra nhiều lần thử. Đừng chỉ forecast theo happy path.

Nếu xác suất một task thất bại mỗi lần thử là \(p\) và giới hạn tổng số lần thử là \(m\), số lần thực hiện kỳ vọng khi retry cho đến khi thành công hoặc hết lượt (giả định xác suất độc lập và không thay đổi) là:

\[
E[A] = \sum_{k=1}^{m} p^{k-1}
= \frac{1-p^m}{1-p}
\]

Với \(p=0,1\), \(m=3\):

\[
E[A] = 1 + 0,1 + 0,01 = 1,11
\]

Trung bình task cần 1,11 lần thực hiện. Đây là mô hình xác suất đơn giản; trong outage thật, lỗi có tương quan theo thời gian và số lần thử có thể tăng đồng loạt.

Dùng retry budget, exponential backoff, jitter, timeout và circuit breaker để tránh retry storm. Không retry lỗi vĩnh viễn như schema invalid hoặc permission denied mà không có thay đổi cấu hình.

## 8. Tính chi phí queue và event bus

Queue/event service có pricing model khác nhau. Các dimension thường gặp:

- Số request/API operation gửi message.
- Số lần receive/poll.
- Delete/acknowledge hoặc commit offset.
- Payload size và số billing unit theo kích thước.
- FIFO/ordering hoặc feature bổ sung.
- Message retention hoặc backlog storage nếu sản phẩm tính riêng.
- Throughput/broker capacity cho streaming platform.
- Event ingestion, filtering, routing và delivery.
- Data transfer giữa Region hoặc đến consumer.
- DLQ, redrive và replay.

### Queue request-based

Một consumer message flow thường có:

1. Producer gửi message.
2. Consumer poll/receive message.
3. Consumer xử lý.
4. Consumer delete/acknowledge message.

Một số queue tính phí cho cả request send, receive và delete; một số tính theo operation hoặc payload unit. Long polling và batch receive có thể giảm số API calls nhưng không nhất thiết giảm payload units hoặc mọi loại phí.

Công thức khái quát:

\[
C_{queue} =
N_{send}P_{send} +
N_{receive}P_{receive} +
N_{ack}P_{ack} +
C_{payload} +
C_{retention} +
C_{transfer}
\]

Chỉ cộng các thành phần thực sự có trong bảng giá của sản phẩm đang dùng.

### Batch và payload size

Batching cho phép gửi/nhận nhiều message trong một request, có thể giảm API request count. Tuy nhiên, billing có thể dựa trên payload size unit hoặc số message chứ không chỉ số HTTP/API calls. Kiểm tra cách provider tính batch request và kích thước tổng.

Không tăng batch size quá lớn nếu làm tăng latency, memory, timeout hoặc blast radius khi một record lỗi. Partial batch response có thể giảm xử lý lặp, từ đó giảm invocation và downstream cost.

### Ví dụ queue

Giả sử có 2 triệu business events trong tháng. Mỗi event được gửi một lần và xử lý thành công, nhưng consumer cần trung bình 2 receive calls do polling/batching configuration và một acknowledgement. Nếu bảng giá minh họa quy đổi mỗi 1 triệu operations là 0,40 USD:

\[
N_{ops} = 2.000.000 \times (1 + 2 + 1)
= 8.000.000
\]

\[
C_{queue,ops} =
\frac{8.000.000}{1.000.000} \times 0,40
= 3,20\ USD
\]

Đơn giá giả định chỉ để thực hành. Queue thực tế có thể tính theo request, payload chunk, throughput, storage hoặc broker hours. Cần thay số bằng usage metric và giá của dịch vụ cụ thể.

## 9. Queue backlog và chi phí do xử lý chậm

Backlog tăng có thể kéo theo chi phí gián tiếp:

- Message tồn tại lâu hơn.
- Consumer phải scale-out để drain backlog.
- Message retry làm tăng receive và function invocation.
- Visibility timeout hết hạn tạo redelivery.
- DLQ và redrive tạo thêm operations.
- SLA bị vi phạm dẫn đến tác động kinh doanh.
- Storage/retention có thể tăng nếu dịch vụ tính theo backlog bytes hoặc thời gian lưu.

Nếu incoming rate là \(\lambda\) message/giây và processing rate là \(\mu\), khi \(\lambda \ge \mu\), backlog không giảm. Nếu \(\mu > \lambda\), thời gian drain gần đúng:

\[
T_{drain} = \frac{B}{\mu-\lambda}
\]

Trong đó \(B\) là backlog hiện tại. Đây là ước lượng cho tải ổn định; retry, batch, partition limits và downstream throttling có thể làm kết quả khác.

Tối ưu queue cost không chỉ là giảm giá operation. Giảm poison message, cải thiện consumer throughput, batch hợp lý và bảo vệ downstream có thể giảm đáng kể số lần nhận lại và compute.

## 10. Tính chi phí object storage

Object storage thường có nhiều thành phần tính phí:

- Dung lượng trung bình lưu theo GB-month.
- PUT/POST/COPY/LIST requests.
- GET/SELECT hoặc retrieval requests.
- Data retrieval theo GB đối với một số storage class.
- Lifecycle transition requests.
- Minimum storage duration hoặc minimum billable object size.
- Replication và cross-Region transfer.
- Inventory, analytics, notification hoặc event integration.
- Data egress ra Internet hoặc Region khác.

### Công thức dung lượng

Nếu lưu trung bình \(S\) GB trong \(D\) ngày của tháng có \(D_m\) ngày:

\[
GB\text{-}month \approx S \times \frac{D}{D_m}
\]

Nếu có nhiều storage class:

\[
C_{storage} =
\sum_j GBMonth_j \times P_{GBMonth,j}
\]

Cần dùng average storage thực tế trong kỳ, không chỉ lấy dung lượng cuối tháng.

### Ví dụ

Một ứng dụng lưu trung bình 800 GB trong 30 ngày của tháng 30 ngày. Giả sử đơn giá giả định là 0,02 USD/GB-month:

\[
C_{capacity} = 800 \times 0,02 = 16\ USD
\]

Nếu có 5 triệu GET và 200.000 PUT, phải tính thêm request charges. Nếu dữ liệu nằm trong storage class có retrieval fee, thêm dung lượng được đọc. Nếu replicate sang Region khác, cộng request và transfer liên vùng theo bảng giá.

### Storage class và lifecycle

Storage class rẻ hơn thường có trade-off về retrieval latency, retrieval fee, minimum retention và transition cost. Lifecycle policy có thể chuyển object cũ sang tier lạnh, nhưng chuyển quá sớm hoặc đọc lại thường xuyên có thể làm tổng chi phí cao hơn.

Phân tích access pattern:

- Hot: đọc thường xuyên, cần latency thấp.
- Warm: đọc thỉnh thoảng.
- Cold/archive: rất ít đọc, chấp nhận restore delay.
- Ephemeral: dữ liệu tạm, có TTL và cần xóa tự động.

Không chuyển dữ liệu sang archive chỉ vì storage rate thấp. Tính tổng storage + transition + retrieval + restore + request + egress.

## 11. Object nhỏ và số lượng request

Một triệu object 1 KB có thể có chi phí khác một object 1 GB dù tổng dung lượng tương đương, vì số request PUT/GET/LIST và metadata operations khác nhau.

Ví dụ, ghi từng event nhỏ thành object riêng có thể tạo hàng triệu PUT. Có thể gom event theo batch hoặc ghi theo partition/time window nếu nghiệp vụ cho phép. Nhưng batching làm tăng latency và cần quản lý partial failure, replay, schema và object size.

Đối với Java function:

- Tránh tạo object nhỏ cho từng log/event nếu có thể dùng batch writer.
- Chọn object key hỗ trợ phân vùng truy vấn và tránh hot prefix nếu storage service có giới hạn liên quan.
- Dùng multipart upload cho object lớn khi phù hợp.
- Đặt lifecycle cho dữ liệu tạm và output có retention hữu hạn.
- Không giữ object dư thừa sau khi workflow hoàn tất.
- Dùng compression khi tiết kiệm storage/transfer lớn hơn chi phí CPU.

## 12. Data transfer và network cost

Một luồng serverless có thể tạo chi phí network ở nhiều chặng:

- Gateway đến function.
- Function đến database hoặc cache.
- Function đến queue/event bus.
- Data transfer giữa AZ.
- Data transfer giữa Region.
- NAT gateway hoặc managed egress.
- Internet egress.
- CDN origin fetch và cache fill.
- Replication và backup transfer.

Một service call nội bộ có thể không có phí request lớn nhưng vẫn tạo data transfer hoặc NAT processing charge. Đặc biệt, function trong private subnet gọi public API qua NAT có thể tạo phí NAT theo giờ và theo GB.

Cần map network path cho mỗi dependency. Dùng private endpoint có thể giảm NAT/egress hoặc tăng security, nhưng endpoint cũng có thể có phí theo giờ/processing. So sánh tổng cost thay vì giả định private luôn rẻ hơn.

### Công thức egress

\[
C_{egress} =
GB_{out} \times P_{egress}
\]

Nếu có tier theo volume hoặc destination:

\[
C_{egress} =
\sum_{destination, tier}
GB_{out,d,t} \times P_{d,t}
\]

Không áp một đơn giá Internet egress cho cross-AZ, cross-Region, CDN hoặc private network. Các destination thường có mức giá và free allowance khác nhau.

## 13. Tính chi phí log, metrics và traces

Observability có thể là phần chi phí đáng kể trong hệ thống event-driven có volume cao.

Các billing dimension thường gặp:

- Log ingestion theo GB.
- Log retention/archive theo GB-month.
- Log query hoặc scan volume.
- Metric custom theo số metric/time series và API requests.
- Trace ingestion, sampling và retention.
- Dashboard, alert và data export.
- Cross-Region log replication hoặc SIEM integration.

Nếu mỗi invocation ghi 5 KB log và có 10 triệu invocation:

\[
LogVolume = 5KB \times 10.000.000
\]

Xấp xỉ 50 GB theo cách quy đổi thập phân. Nếu retry tạo thêm log, volume còn cao hơn. Đây là ví dụ để tính quy mô; billing có thể tính theo byte thực ingest, compression hoặc đơn vị riêng của provider.

Giảm log volume bằng cách:

- Dùng structured log có field cần thiết.
- Không log toàn bộ request/message payload.
- Dùng batch summary cho record thành công.
- Ghi failure/retry chi tiết có chọn lọc.
- Đặt retention theo mục đích.
- Sampling trace hợp lý.
- Tránh metric labels cardinality cao.
- Không gửi debug log liên tục trong production.

Không tắt telemetry quan trọng chỉ để giảm hóa đơn. Mất khả năng phát hiện retry storm, backlog hoặc lỗi dependency có thể gây chi phí lớn hơn.

## 14. Tính chi phí một business transaction

Cách hữu ích nhất là lập bảng số hoạt động trung bình cho một business transaction.

Ví dụ một đơn hàng thành công:

| Thành phần | Số lượng mỗi đơn | Billing dimension cần đo |
|---|---:|---|
| API gateway | 1 request POST + 1 request status | Gateway requests |
| Java ingress function | 1 invocation | Invocation + duration/resource |
| Workflow | 6 transitions | State transitions/execution |
| Queue | 1 send + 1 receive + 1 ack | Message operations/payload units |
| Worker function | 1 invocation | Invocation + duration/resource |
| Object storage | 1 PUT + 2 GET | Storage requests + capacity |
| Database | 4 read/write operations | Capacity/IO/request model |
| Logs | 6 records | Ingestion + retention |
| Traces | 1 sampled trace | Trace ingestion/retention |
| Network | 250 KB transfer | Transfer by destination |

Bảng này là mô hình ví dụ, không phải số hoạt động bắt buộc. Đo thực tế bằng tracing, application metrics, access log và billing export.

### Công thức unit economics

\[
CostPerTransaction =
\frac{C_{total\ for\ period}}
{N_{successful\ business\ transactions}}
\]

Có thể tách theo thành phần:

\[
CPT =
CPT_{gateway} +
CPT_{compute} +
CPT_{workflow} +
CPT_{queue} +
CPT_{storage} +
CPT_{network} +
CPT_{observability}
\]

Đừng chia cho số request nếu một nghiệp vụ có thể tạo nhiều request. Dùng denominator có ý nghĩa business như order completed, payment authorized, report generated hoặc document processed.

### Ví dụ phân bổ

Giả sử tháng có 100.000 đơn hàng hoàn tất. Sau khi tổng hợp billing và phân bổ, chi phí liên quan là:

| Thành phần | Chi phí giả định |
|---|---:|
| API gateway | 18 USD |
| Function compute | 42 USD |
| Workflow | 25 USD |
| Queue/event | 9 USD |
| Storage | 16 USD |
| Network | 20 USD |
| Observability | 10 USD |
| **Tổng** | **140 USD** |

\[
CPT = \frac{140}{100.000}
= 0,0014\ USD/order
\]

Đây là số giả định để minh họa. Không dùng nó làm benchmark hay dự báo cho provider cụ thể. Trong thực tế, phải phân bổ shared infrastructure và discount một cách nhất quán.

## 15. Chi phí retry, duplicate và poison message

Retry làm tăng chi phí trực tiếp và gián tiếp:

- Thêm function invocation.
- Thêm workflow transition/task.
- Thêm queue receive/ack hoặc redrive.
- Thêm database/API request.
- Thêm log/trace.
- Tăng backlog và capacity cần thiết.

Một message poison có thể retry nhiều lần rồi vào DLQ. Nếu không có max receive count hoặc retry cap, nó có thể tiêu thụ tài nguyên liên tục.

Đo các chỉ số:

- Retry attempts trên mỗi business event.
- Duplicate rate.
- Failure rate theo error code.
- DLQ ingress và age.
- Redrive volume.
- Chi phí compute/queue theo successful event.
- Tỷ lệ side effect đã commit nhưng message bị giao lại.

Idempotency không chỉ bảo vệ correctness; nó còn giúp retry an toàn và tránh thực hiện lại các thao tác đắt như thanh toán, gửi SMS hoặc tạo object. Tuy vậy, idempotency table, conditional write và reconciliation cũng có chi phí riêng; cần tính vào unit economics.

## 16. Free tier, tiered pricing và commitment

Free tier có thể áp dụng cho một lượng request, duration, storage hoặc transfer nhất định. Không nên thiết kế hệ thống chỉ để nằm trong free tier vì:

- Free allowance có thể thay đổi.
- Nhiều account/service không chia sẻ cùng allowance.
- Một số Region hoặc feature không được miễn phí.
- Usage vượt ngưỡng có thể chuyển sang đơn giá khác.
- Free tier có thể hết hạn theo thời gian.
- Chi phí dịch vụ liên quan vẫn phát sinh.

Tiered pricing có thể giảm đơn giá khi usage tăng, nhưng tổng chi phí vẫn tăng. Commitment/discount có thể giảm đơn giá nếu workload ổn định, nhưng tạo ràng buộc về mức sử dụng hoặc thời hạn.

FinOps cần forecast theo nhiều kịch bản: thấp, dự kiến và cao; tính cả tháng peak, burst, retry và DR exercise. Không lấy free tier làm baseline cho production cost lâu dài.

## 17. Phân bổ chi phí: tag, account và cost center

Để biết team hoặc sản phẩm nào tạo chi phí, cần thiết kế cost allocation từ đầu.

Tag/label thường dùng:

- application hoặc product.
- service.
- environment: dev, test, staging, production.
- team/owner.
- cost_center.
- business_unit.
- tenant hoặc customer segment nếu policy cho phép.
- data_classification.
- managed_by/IaC stack.

Không phải mọi tài nguyên hoặc billing line đều hỗ trợ tag trực tiếp. Với dịch vụ shared như API gateway, event bus hoặc log platform, có thể cần phân bổ qua usage metric, resource mapping hoặc cost allocation rule.

Tránh dùng user ID/email làm cost tag hoặc metric dimension vì cardinality và privacy. Dùng tenant tier, product group hoặc cost center đã được quản trị.

### Shared cost allocation

Ví dụ một log workspace dùng chung cho 5 service. Có thể phân bổ theo bytes ingested, GB retained hoặc query volume thay vì chia đều. Một NAT gateway dùng chung có thể phân bổ theo bytes/flow hoặc theo service network path. Chọn driver phản ánh mức tiêu thụ thực tế và ghi rõ giả định.

## 18. Budgets, alerts và anomaly detection

Budget nên được đặt ở nhiều cấp:

- Toàn module/product.
- Environment.
- Team/cost center.
- Service/resource group.
- Unit cost như cost per order hoặc cost per 1.000 events.

Alert hữu ích:

- Forecast cuối tháng vượt budget.
- Chi phí tăng nhanh so với baseline.
- Gateway request tăng bất thường.
- Workflow transitions per transaction tăng.
- Queue receive/retry operations tăng.
- Storage growth hoặc retrieval tăng.
- Log ingestion tăng đột biến.
- NAT/egress/cross-Region transfer bất thường.
- Cost per successful transaction vượt ngưỡng.

Một alert billing có thể đến trễ vì dữ liệu cost không realtime. Kết hợp billing export với operational metric để phát hiện sớm nguyên nhân, sau đó xác nhận bằng cost data khi được cập nhật.

## 19. Forecast theo traffic và business volume

Dự báo nên dựa trên driver nghiệp vụ thay vì ngoại suy tổng hóa đơn.

Ví dụ, nếu dự kiến 200.000 đơn hàng/tháng và mỗi đơn trung bình tạo 2 gateway requests, 1 workflow với 7 transitions, 3 queue operations và 4 storage operations, có thể tính usage dự kiến từng service.

Nếu campaign tăng gấp 3 số đơn, không phải mọi chi phí đều tăng chính xác 3 lần:

- Gateway request thường tăng gần tuyến tính.
- Function duration có thể tăng do contention.
- Queue backlog có thể làm consumer scale-out.
- Workflow retry có thể tăng khi downstream quá tải.
- Storage capacity tích lũy theo retention.
- Egress có thể tăng theo payload size và cache hit ratio.
- Provisioned capacity có thể giữ nguyên trong giờ thấp điểm.

Forecast cần mô hình traffic shape, peak concurrency, retry rate, retention và data growth, không chỉ business volume.

## 20. FinOps cho Java serverless

Một số tối ưu ở tầng ứng dụng:

- Giảm thời gian khởi tạo Java và cold start nếu nó làm tăng billed duration hoặc latency.
- Chọn memory/CPU phù hợp; benchmark duration và total cost thay vì luôn chọn memory thấp nhất.
- Tái sử dụng SDK client và connection trong execution environment khi an toàn.
- Giảm số network round-trip bằng batching.
- Tránh N+1 query và gọi dependency lặp.
- Cache dữ liệu phù hợp với TTL và invalidation.
- Giảm payload size, nén dữ liệu khi có lợi.
- Dùng queue cho burst thay vì giữ function synchronous chờ lâu.
- Thiết kế workflow với số state hợp lý và tránh polling quá dày.
- Dùng idempotency để giảm side effect lặp khi retry.
- Đặt timeout, retry cap và concurrency theo capacity downstream.
- Tối ưu log/trace volume nhưng giữ đủ khả năng điều tra.

Không tối ưu cost bằng cách giảm memory đến mức function chạy lâu hơn hoặc timeout nhiều hơn. Với billing theo GB-second, memory thấp hơn nhưng duration cao hơn có thể không rẻ hơn. Cần benchmark toàn bộ workload.

### Ví dụ chọn memory

Giả sử hai cấu hình function có cùng request count:

| Cấu hình | Memory giả định | Duration trung bình | GB-second tương đối |
|---|---:|---:|---:|
| A | 512 MB | 1.000 ms | 0,5 |
| B | 1.024 MB | 400 ms | 0,4 |

Cấu hình B dùng memory gấp đôi nhưng duration ngắn hơn; lượng GB-second tương đối thấp hơn. Đây chỉ là phép so sánh đơn giản, chưa tính CPU architecture, billing granularity, free tier, provisioned capacity và giá cụ thể.

## 21. Tối ưu API gateway và client behavior

- Dùng cache khi dữ liệu có thể cache an toàn và hit ratio đủ cao.
- Giảm polling bằng callback, WebSocket hoặc long polling phù hợp.
- Dùng pagination và response projection để giảm payload.
- Hạn chế client retry vô hạn; dùng backoff/jitter.
- Tránh gửi request trùng do double-click hoặc retry thiếu idempotency key.
- Chọn API type theo feature thực sự cần.
- Đặt throttling để bảo vệ backend và tránh retry storm.
- Nén response khi payload lớn và client hỗ trợ.
- Theo dõi request per business transaction và cache hit ratio.

Nếu một client polling trạng thái mỗi giây trong 10 phút, một operation tạo 600 request status. Một callback hoặc polling theo exponential interval có thể giảm đáng kể gateway requests, compute và network. Tuy nhiên, cần giữ UX và SLA.

## 22. Tối ưu workflow và orchestration

- Giảm state/transition không mang lại giá trị nghiệp vụ.
- Dùng native service integration nếu nó giảm function invocation và boilerplate, nhưng so sánh pricing.
- Tránh workflow step chỉ để chuyển tiếp một giá trị đơn giản nếu có thể gộp an toàn.
- Dùng Wait/Callback thay vì giữ function chạy hoặc polling liên tục.
- Đặt retry policy theo loại lỗi và giới hạn số lần thử.
- Tránh nested workflow không cần thiết.
- Giữ payload nhỏ; lưu dữ liệu lớn ở object storage và truyền reference.
- Chọn execution mode theo duration, throughput, history và billing model.
- Dùng execution history để đo transition count thực tế.

Gộp step có thể giảm transition nhưng làm tăng độ phức tạp trong một function, giảm khả năng retry riêng lẻ và tăng blast radius. Tối ưu phải cân bằng cost, reliability, maintainability và latency.

## 23. Tối ưu queue và event bus

- Dùng batch send/receive nếu provider hỗ trợ và workload phù hợp.
- Chọn batch size cân bằng throughput, latency và partial failure.
- Dùng long polling để giảm empty receive nếu queue hỗ trợ.
- Đặt visibility timeout phù hợp để tránh redelivery giả.
- Giảm message payload bằng cách lưu object lớn ở storage và gửi reference.
- Chọn retention đủ cho recovery nhưng không giữ message vô hạn.
- Dùng DLQ và redrive policy để poison message không retry mãi.
- Hạn chế fan-out không cần thiết.
- Chọn event filtering/routing để consumer chỉ nhận event cần thiết.
- Theo dõi queue age, receive count và cost per successful message.

Một event bus có thể tính phí theo event delivery tới từng target. Fan-out một event đến 10 target có thể tạo chi phí khác một queue chỉ có một consumer. Tính số delivery thực tế, không chỉ số event producer gửi.

## 24. Tối ưu storage và data lifecycle

- Chọn storage class theo access pattern.
- Đặt lifecycle transition/expiration rõ ràng.
- Xóa object tạm sau khi workflow hoàn tất hoặc hết TTL.
- Gom object nhỏ khi phù hợp.
- Nén dữ liệu lớn.
- Tránh LIST toàn bộ bucket thường xuyên; dùng index/manifest hoặc event metadata.
- Hạn chế GET lặp bằng cache hoặc giữ kết quả trong một flow khi an toàn.
- Đo retrieval và egress, không chỉ GB-month.
- Đánh giá replication theo RPO/DR requirement.
- Xác định retention theo compliance và business need.

Storage class lạnh có thể giảm chi phí dung lượng nhưng tăng phí truy xuất và thời gian restore. Nếu báo cáo đọc dữ liệu cũ thường xuyên, class nóng có thể rẻ hơn tổng thể.

## 25. Ví dụ tính chi phí tổng hợp

Giả sử một ứng dụng xử lý 100.000 business transactions trong tháng. Các đơn giá sau đều là **số giả định**, chỉ để minh họa cách lập bảng.

| Thành phần | Usage giả định | Đơn giá giả định | Chi phí |
|---|---:|---:|---:|
| API gateway | 200.000 requests | 1 USD / 100.000 requests | 2,00 USD |
| Workflow | 700.000 transitions | 0,30 USD / 100.000 transitions | 2,10 USD |
| Queue | 600.000 operations | 0,20 USD / 100.000 operations | 1,20 USD |
| Storage capacity | 500 GB-month | 0,02 USD / GB-month | 10,00 USD |
| Storage requests | 300.000 operations | 0,05 USD / 100.000 operations | 0,15 USD |
| Network egress | 40 GB | 0,08 USD / GB | 3,20 USD |
| Observability | 25 GB log ingest | 0,50 USD / GB | 12,50 USD |
| **Tổng** |  |  | **31,15 USD** |

\[
CostPerTransaction =
\frac{31,15}{100.000}
= 0,0003115\ USD
\]

Trong ví dụ này, log ingestion và storage capacity lớn hơn các thành phần request-based. Điều đó cho thấy chỉ tối ưu API gateway hoặc function invocation có thể không tạo khác biệt lớn nhất.

Bảng chưa bao gồm function compute, database, WAF, KMS, cache, NAT hourly, support, tax, discount và free tier. Trong thực tế, cần thêm tất cả dòng phù hợp từ billing export.

## 26. Cách đối chiếu estimate với hóa đơn thực tế

Quy trình FinOps hàng tháng:

1. Export billing/cost usage theo account, project, subscription và Region.
2. Chuẩn hóa service name và SKU/billing dimension.
3. Map resource ARN/ID sang application, environment, team và cost center.
4. So sánh usage thực tế với request, invocation, transition, queue và storage metrics.
5. Tính cost per successful transaction.
6. Tách fixed/shared cost khỏi variable cost.
7. Xác định top cost drivers và anomaly.
8. Kiểm tra retry, data transfer, log ingestion và retention.
9. Ghi nhận thay đổi traffic, deploy hoặc policy có thể giải thích biến động.
10. Tạo action có owner, expected saving, risk và cách đo kết quả.

Đừng coi estimate và hóa đơn là phải khớp tuyệt đối nếu khác thời điểm, rounding, discount, tax hoặc shared allocation. Nhưng chênh lệch lớn phải được giải thích bằng usage hoặc billing dimension cụ thể.

## 27. Cost anomaly và unit economics

Một hệ thống có thể có tổng bill ổn định nhưng cost per transaction tăng vì business volume giảm. Ngược lại, bill tăng có thể là kết quả tốt nếu số transaction tăng nhanh hơn.

Theo dõi đồng thời:

- Total cost.
- Cost per successful transaction.
- Cost per API request.
- Cost per workflow execution.
- Cost per successful message.
- Cost per GB stored.
- Cost per GB retrieved/egress.
- Retry/duplicate rate.
- Failure rate và SLA.

Một thay đổi tối ưu được coi là thành công khi tiết kiệm có thể đo được mà không làm tăng lỗi, latency hoặc công sức vận hành quá mức. Ghi lại baseline trước thay đổi và đo sau cùng một traffic profile.

## 28. Những lỗi FinOps thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ tính function compute | Bỏ sót gateway, workflow, queue, storage và network | Tính end-to-end transaction |
| Dùng giá cũ | Forecast sai do giá/tier/Region thay đổi | Dùng bảng giá và calculator hiện hành |
| Đếm business transaction thay request | Bỏ sót polling, retry và callback | Đo request per transaction |
| Đếm queue message thay operations | Bỏ sót receive/ack/redrive và payload units | Map đúng billing dimension |
| Chỉ tính GB-month của storage | Bỏ sót PUT/GET, retrieval, transition và egress | Tính toàn bộ storage lifecycle |
| Cho rằng Wait state luôn miễn phí | Bỏ sót transition/execution charge | Kiểm tra billing model của workflow engine |
| Bỏ qua retry | Ước lượng thấp usage và compute | Đưa retry rate vào forecast |
| Tắt log để tiết kiệm | Mất khả năng điều tra và tăng MTTR | Tối ưu schema, volume và retention |
| Không gắn tag | Không biết team/service tạo chi phí | Thiết kế allocation từ IaC |
| Chia shared cost đều | Unit cost sai | Phân bổ theo usage driver |
| Chỉ nhìn tổng bill | Bỏ lỡ cost per transaction tăng | Theo dõi unit economics |
| Giảm memory không benchmark | Function chạy lâu hơn hoặc timeout | Benchmark GB-second và SLA |
| Giữ warm capacity quá mức | Tốn chi phí idle | Dựa trên traffic và latency objective |
| Lưu object vô thời hạn | Storage tăng không kiểm soát | Lifecycle và retention policy |
| Không đo egress/NAT | Network cost bất ngờ | Map dependency path và data volume |

## 29. Quy trình xây dựng cost model

1. **Vẽ luồng nghiệp vụ:** API, function, workflow, queue, storage, database và observability.
2. **Chọn denominator:** order completed, payment authorized, event processed hoặc business transaction.
3. **Đếm usage per transaction:** request, invocation, transition, message operation, storage request và byte.
4. **Xác định pricing dimension:** đúng provider, Region, tier, class và execution mode.
5. **Tính fixed cost:** provisioned capacity, cache, broker, NAT, database baseline và support.
6. **Tính variable cost:** request, duration, transition, message, storage, retrieval và transfer.
7. **Tính retry/failure:** duplicate, DLQ, replay và timeout.
8. **Tính observability:** log ingestion, retention, metrics và trace.
9. **Phân bổ shared cost:** tag, cost center hoặc usage driver.
10. **Forecast:** baseline, expected, peak và DR scenario.
11. **Đối chiếu billing:** kiểm tra estimate với usage/cost export.
12. **Tối ưu và đo lại:** đặt owner, baseline, expected saving và guardrail SLA.

## 30. Checklist production

- **End-to-end:** cost model bao gồm gateway, compute, workflow, queue, storage, network và observability.
- **Pricing:** đơn giá đúng provider, Region, API type, storage class và execution mode.
- **Usage:** request, invocation, transition, message operation, payload và storage request được đo.
- **Workflow:** transition/execution/duration và retry được tính đúng billing model.
- **Queue:** send/receive/ack, payload unit, retention, DLQ và redrive được xem xét.
- **Storage:** GB-month, PUT/GET/LIST, retrieval, lifecycle, minimum duration và replication được tính.
- **Network:** Internet egress, cross-AZ/Region, NAT và private endpoint được kiểm tra.
- **Observability:** log ingestion/retention, metric cardinality và trace sampling có budget.
- **Unit economics:** có cost per successful business transaction.
- **Allocation:** resource tags, team, environment và cost center nhất quán.
- **Shared cost:** có allocation rule dựa trên usage driver.
- **Budget:** có forecast, alert và anomaly detection.
- **Retry:** có retry budget, DLQ và idempotency để tránh chi phí lặp vô hạn.
- **Lifecycle:** object, log, workflow history và queue retention có chính sách.
- **Testing:** load test và failure test ghi nhận cost driver.
- **Review:** mỗi thay đổi tối ưu có baseline, owner, saving estimate và SLA guardrail.

## 31. Kết luận

Chi phí serverless là tổng của nhiều dịch vụ trong một business flow. API gateway có thể tính theo request, data hoặc feature; workflow có thể tính theo transition, execution hoặc duration; queue có thể tính theo operation, payload, throughput hoặc broker capacity; storage có thể tính theo dung lượng, request, retrieval, lifecycle và replication. Network và observability thường là những phần dễ bị bỏ sót.

Hãy lập cost model từ số hoạt động trên mỗi business transaction, sau đó nhân với volume dự kiến và đơn giá đúng của provider/Region. Cộng cả retry, duplicate, backlog, data transfer, retention, warm capacity và shared infrastructure. Theo dõi cost per successful transaction song song với latency, failure rate và SLA để tránh tối ưu hóa một hóa đơn bằng cách làm giảm chất lượng dịch vụ.

FinOps là vòng lặp liên tục: đo usage, phân bổ chi phí, dự báo, phát hiện bất thường, tối ưu và xác nhận kết quả bằng dữ liệu billing. Với Java serverless, batching hợp lý, workflow transitions vừa đủ, queue consumer idempotent, storage lifecycle rõ ràng và structured telemetry có kiểm soát giúp hệ thống vừa đáng tin cậy vừa có chi phí dự đoán được.
