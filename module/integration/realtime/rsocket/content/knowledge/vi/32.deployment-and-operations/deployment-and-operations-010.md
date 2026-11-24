# Định nghĩa mục tiêu độ trễ, tỷ lệ lỗi và quy trình ứng phó sự cố

## Mục tiêu bài học

Một dịch vụ RSocket có thể vẫn giữ nhiều kết nối hoạt động nhưng người dùng không nhận được phản hồi đúng thời hạn, stream cập nhật chậm hoặc request bị lỗi. Để vận hành có trách nhiệm, đội ngũ cần định nghĩa rõ điều gì được xem là dịch vụ tốt, ngưỡng nào cần cảnh báo và ai sẽ làm gì khi chất lượng suy giảm.

Sau bài này, bạn có thể:

- Chọn Service Level Indicator (SLI) phản ánh trải nghiệm thực tế của client.
- Định nghĩa Service Level Objective (SLO) cho độ trễ, tỷ lệ lỗi và tính sẵn sàng.
- Tính error budget và tốc độ tiêu thụ ngân sách lỗi (burn rate).
- Thiết kế cảnh báo dựa trên nhiều cửa sổ thời gian thay vì chỉ dùng ngưỡng CPU hoặc một spike ngắn.
- Phân biệt mục tiêu của request-response, fire-and-forget, request-stream và request-channel.
- Tổ chức ứng phó sự cố với vai trò, mức độ nghiêm trọng, kênh liên lạc và runbook.
- Giảm tác động trước, tìm nguyên nhân trong khi sự cố được kiểm soát, rồi xác nhận phục hồi bằng SLI.
- Viết postmortem không đổ lỗi và chuyển bài học thành hành động có người phụ trách.

## SLI, SLO và SLA

Ba khái niệm thường đi cùng nhau nhưng có ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| SLI (Service Level Indicator) | Chỉ số đo chất lượng thực tế mà người dùng cảm nhận | Tỷ lệ request hợp lệ hoàn tất thành công trong 200 ms |
| SLO (Service Level Objective) | Mục tiêu nội bộ cho SLI trong một cửa sổ thời gian | 99,9% request đủ điều kiện hoàn tất thành công trong 200 ms trong 30 ngày |
| SLA (Service Level Agreement) | Cam kết dịch vụ với khách hàng, có thể kèm điều khoản hoặc tín dụng dịch vụ | Hợp đồng quy định availability tối thiểu theo tháng |

SLO giúp đội ngũ ra quyết định kỹ thuật và ưu tiên độ tin cậy. SLA là cam kết bên ngoài có hệ quả thương mại/pháp lý. Không nên lấy một con số SLA làm mục tiêu vận hành duy nhất nếu nó không đủ nhạy để phát hiện suy giảm sớm.

~~~mermaid
flowchart TD
    A[Trải nghiệm người dùng] --> B[SLI: đo chất lượng]
    B --> C[SLO: đặt mục tiêu theo cửa sổ]
    C --> D[Error budget]
    D --> E{Ngân sách còn đủ?}
    E -->|Có| F[Tiếp tục thay đổi có kiểm soát]
    E -->|Sắp cạn hoặc hết| G[Ưu tiên độ tin cậy và giảm rủi ro]
~~~

Một SLI tốt phải có định nghĩa đo lường rõ ràng: sự kiện nào được tính, thời điểm bắt đầu/kết thúc, mẫu số, mẫu số có loại trừ trường hợp nào và nguồn dữ liệu nào là chuẩn. Nếu hai dashboard tính cùng một SLI bằng hai mẫu số khác nhau, đội vận hành không thể dùng chúng để ra quyết định nhất quán.

## Xác định SLI cho RSocket

RSocket có nhiều interaction model và stream có thể sống lâu. Vì vậy, không nên dùng một phép đo latency duy nhất cho mọi loại tương tác.

| Interaction | SLI độ trễ phù hợp | SLI kết quả phù hợp |
|---|---|---|
| Request-response | Thời gian từ lúc server nhận request đến lúc response hoàn tất; đối chiếu thêm client end-to-end latency | Tỷ lệ request hoàn tất thành công |
| Fire-and-forget | Thời gian server tiếp nhận hoặc ghi nhận command, nếu có đo được | Tỷ lệ command được tiếp nhận/xử lý theo hợp đồng ứng dụng |
| Request-stream | Time-to-first-item và độ trễ/freshness giữa các event | Tỷ lệ stream thiết lập thành công; tỷ lệ event đến đúng hạn |
| Request-channel | Thời gian phản hồi từng message hoặc time-to-first-response; thời lượng channel là chỉ số vòng đời riêng | Tỷ lệ message được xử lý/acknowledge theo hợp đồng |

### Request-response latency

Định nghĩa một request đủ điều kiện khi server nhận được interaction thuộc route đang đo và có thể xác định kết quả. Có thể đo:

- Client end-to-end: từ khi client phát request tới khi nhận response/error.
- Server duration: từ lúc server bắt đầu xử lý request tới khi handler kết thúc.
- Dependency duration: thời gian gọi database hoặc service khác bên trong handler.

Client latency và server latency trả lời hai câu hỏi khác nhau. Nếu client thấy 500 ms nhưng server handler chỉ mất 30 ms, cần điều tra transport, proxy, client queue hoặc phần encode/decode. Nếu cả hai đều cao, trace phía server giúp tìm chặng chậm.

### Stream latency và freshness

Một request-stream có thể mở trong nhiều giờ. Dùng toàn bộ stream duration làm latency SLO sẽ tạo ra chỉ số vô nghĩa: stream càng khỏe và sống lâu thì duration càng lớn.

Thay vào đó, đo:

- Time-to-first-item: thời gian từ khi request stream được chấp nhận tới event đầu tiên.
- Inter-event delay: thời gian giữa các event liên tiếp nếu ứng dụng yêu cầu nhịp cập nhật ổn định.
- Data freshness: tuổi của dữ liệu khi client nhận, thường dựa trên event timestamp hoặc source timestamp.
- Stream termination rate: tỷ lệ stream kết thúc bất thường hoặc bị reset.

Một stream có thể giữ kết nối thành công nhưng không phát dữ liệu mới. Nếu nghiệp vụ yêu cầu cập nhật realtime, freshness thường có ý nghĩa hơn việc socket vẫn mở.

### Fire-and-forget cần hợp đồng đo rõ ràng

Fire-and-forget không trả response nghiệp vụ cho requester. Việc gửi publisher hoàn tất không chứng minh command đã được lưu bền vững hoặc xử lý thành công.

Nếu muốn đặt SLO cho fire-and-forget, hãy đo một mốc mà server có thể xác nhận:

- Command đã được handler nhận.
- Command đã được ghi vào durable queue/database.
- Command đã được xử lý hoàn tất.

Chọn đúng mốc theo hợp đồng. Nếu cần chứng minh durable acceptance, ứng dụng cần acknowledgement riêng, receipt, outbox hoặc trạng thái command có thể truy vấn.

## Định nghĩa SLO độ trễ và tỷ lệ lỗi

Một mẫu SLO thực tế cho route request-response:

> Trong cửa sổ 30 ngày, ít nhất 99,9% request đủ điều kiện tới route inventory.lookup phải hoàn tất thành công trong 200 ms.

Cách định nghĩa này kết hợp thành công và latency trong cùng một good event:

- Mẫu số: tất cả request đủ điều kiện đã được server nhận.
- Tử số: request kết thúc thành công và có duration không vượt 200 ms.
- Request lỗi, timeout hoặc thành công nhưng vượt 200 ms đều là bad event.

Có thể định nghĩa riêng SLO tỷ lệ lỗi:

> Tỷ lệ request kết thúc bằng lỗi ứng dụng hoặc lỗi hệ thống không vượt 0,1% trong 30 ngày.

Định nghĩa error cần thống nhất. Ví dụ, lỗi validation do người dùng gửi dữ liệu sai có thể được phân loại riêng với lỗi server. Tuy nhiên, không loại bỏ lỗi chỉ vì nó khó xử lý hoặc làm SLO xấu đi. Nếu lỗi đó khiến thao tác mà người dùng mong muốn không thực hiện được, hãy quyết định dựa trên trải nghiệm và hợp đồng dịch vụ.

### Ví dụ SLI dạng tỷ lệ

Với SLO 99,9%, tính SLI theo công thức:

~~~text
SLI = (Good events / Eligible events) x 100%
~~~

Trong đó good event là request thành công trong ngưỡng latency đã định nghĩa.

~~~text
Error budget ratio = 1 - 0.999 = 0.001 = 0.1%
~~~

Nếu có 1.000.000 request đủ điều kiện trong cửa sổ, ngân sách cho phép tối đa 1.000 bad event. Đây là ngân sách theo tỷ lệ sự kiện, không phải lời hứa rằng mọi giờ đều được phép có một số lỗi cố định.

### Ví dụ mục tiêu khởi đầu

Các con số dưới đây chỉ là ví dụ để bắt đầu thảo luận; hãy điều chỉnh bằng dữ liệu tải, trải nghiệm người dùng và cam kết sản phẩm.

| SLI | Ví dụ SLO 30 ngày | Ghi chú |
|---|---:|---|
| Request-response success trong 200 ms | 99,9% | Tính lỗi và request chậm là bad event |
| Request-response error rate | Không quá 0,1% | Phân loại lỗi theo hợp đồng |
| Time-to-first-item của stream trong 500 ms | 99,5% | Đo riêng theo route stream |
| Event freshness dưới 2 giây | 99% event | Phù hợp luồng cập nhật trạng thái |
| Command được durable-accepted trong 300 ms | 99,9% | Chỉ dùng nếu có receipt sau commit |

Không áp dụng cùng ngưỡng 200 ms cho mọi route. Một route đọc cache, route gọi nhiều service và route tạo báo cáo có đặc tính khác nhau. Đặt mục tiêu theo mức quan trọng nghiệp vụ và trải nghiệm mà client cần.

## Chọn mẫu số và phân loại lỗi

Một SLI có thể bị sai lệch nếu mẫu số không được định nghĩa cẩn thận.

| Trường hợp | Cách xử lý cần quyết định |
|---|---|
| Request được server nhận và trả lỗi 5xx tương đương | Thường tính là bad event |
| Handler timeout | Tính là bad event nếu người dùng không nhận được kết quả đúng hạn |
| Request bị từ chối do quota của service | Thường là bad event đối với SLO của service |
| Client gửi route không tồn tại | Có thể phân loại là lỗi hợp đồng/client; công bố rõ có tính vào SLO hay không |
| Client hủy request trước khi server xử lý | Xác định theo hợp đồng; theo dõi riêng cancellation |
| Mạng phía client mất trước khi server nhận request | Không xuất hiện trong server-side denominator; cần client-side SLI nếu trải nghiệm đầu-cuối phải bao gồm trường hợp này |
| Request test/health check | Chỉ loại nếu đã quy định rõ và không dùng health check để thay thế traffic thật |

Đối với SLO trải nghiệm người dùng, client-side SLI thường phản ánh đầy đủ hơn server-side SLI. Có thể dùng cả hai: client SLI làm mục tiêu người dùng, server SLI để chẩn đoán trách nhiệm của service.

## Error budget và burn rate

Error budget là phần bad event được phép xảy ra trong cửa sổ SLO.

Với SLO 99,9%, error budget ratio là 0,1%. Khi service sử dụng hết ngân sách, đội ngũ đã không đạt mục tiêu độ tin cậy của cửa sổ đó.

Burn rate cho biết tốc độ tiêu thụ ngân sách so với tốc độ cho phép:

~~~text
Burn rate = Observed error ratio / Allowed error ratio
~~~

Ví dụ:

- SLO 99,9% cho phép error ratio 0,1%.
- Error ratio thực tế trong một cửa sổ là 0,5%.
- Burn rate là 0,5% / 0,1% = 5x.

Nếu tốc độ này duy trì liên tục, service đang tiêu thụ error budget nhanh gấp năm lần tốc độ cho phép trong toàn kỳ.

### Ví dụ tính ngân sách

Giả sử có 10 triệu request đủ điều kiện trong 30 ngày:

| Mục | Giá trị |
|---|---:|
| SLO | 99,9% |
| Error budget ratio | 0,1% |
| Eligible events | 10.000.000 |
| Bad events tối đa theo ngân sách | 10.000 |
| Bad events quan sát được | 2.000 |
| Budget đã tiêu thụ | 20% |

Không chỉ xem budget còn bao nhiêu. Hãy xem tốc độ tiêu thụ gần đây: 2.000 lỗi trải đều trong tháng khác với 2.000 lỗi xảy ra trong 10 phút.

## Cảnh báo theo burn rate nhiều cửa sổ

Cảnh báo chỉ dựa trên error rate tuyệt đối có thể tạo nhiều false positive khi traffic thấp hoặc có một spike ngắn. Cảnh báo burn-rate kết hợp:

- Cửa sổ dài để xác nhận mức tiêu thụ ngân sách đáng kể.
- Cửa sổ ngắn để xác nhận vấn đề vẫn đang xảy ra.
- Ngưỡng burn rate để quyết định mức độ khẩn cấp.

Google SRE Workbook đưa ra các cấu hình mẫu cho SLO 99,9%, chẳng hạn:

| Mức cảnh báo | Cửa sổ dài | Cửa sổ ngắn | Burn rate mẫu | Ý nghĩa |
|---|---:|---:|---:|---|
| Page | 1 giờ | 5 phút | 14,4x | Tiêu thụ nhanh, cần người trực xử lý ngay |
| Page | 6 giờ | 30 phút | 6x | Suy giảm kéo dài và vẫn đang diễn ra |
| Ticket | 3 ngày | 6 giờ | 1x | Vấn đề dài hạn cần điều tra theo quy trình |

Đây là điểm bắt đầu, không phải ngưỡng phù hợp cho mọi dịch vụ. Hãy điều chỉnh theo độ dài cửa sổ SLO, traffic, mức độ quan trọng và khả năng trực vận hành.

### PromQL minh họa

Giả sử instrumentation xuất ra:

- `rsocket_server_requests_total{outcome="success"}` và `rsocket_server_requests_total{outcome="error"}` (hai giá trị tag riêng)
- `rsocket_server_request_duration_seconds_bucket{route="..."}`

Tỷ lệ lỗi trong 5 phút:

~~~promql
sum(rate(rsocket_server_requests_total{outcome="error"}[5m]))
/
sum(rate(rsocket_server_requests_total[5m]))
~~~

Tốc độ request:

~~~promql
sum(rate(rsocket_server_requests_total[5m]))
~~~

p95 latency theo route từ histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(rsocket_server_request_duration_seconds_bucket[5m])
  )
)
~~~

Với SLO latency dạng good-event ratio, có thể đếm request thành công và nằm dưới bucket ngưỡng. Ví dụ nếu ngưỡng là 0,2 giây:

~~~promql
sum(rate(rsocket_server_request_duration_seconds_bucket{le="0.2",outcome="success"}[5m]))
/
sum(rate(rsocket_server_requests_total[5m]))
~~~

Tên metric và tag trong các truy vấn là ví dụ. Kiểm tra tên thật ở registry/Prometheus; Micrometer có thể chuẩn hóa tên và đơn vị khi export. Nếu histogram không có bucket đúng ngưỡng, hãy cấu hình bucket phù hợp trước khi dùng SLI này.

Không tính trung bình p95 của từng instance để ra p95 toàn cụm. Với Prometheus histogram, hãy cộng bucket theo các dimension cần giữ rồi mới gọi `histogram_quantile`.

### Alert rule mẫu

Ví dụ biểu thức burn rate 14,4x trên cả cửa sổ 1 giờ và 5 phút:

~~~yaml
groups:
  - name: rsocket-slo
    rules:
      - alert: RSocketHighErrorBudgetBurn
        expr: |
          (
            (
              sum(rate(rsocket_server_requests_total{outcome="error"}[1h]))
              /
              sum(rate(rsocket_server_requests_total[1h]))
            ) > (14.4 * 0.001)
          )
          and
          (
            (
              sum(rate(rsocket_server_requests_total{outcome="error"}[5m]))
              /
              sum(rate(rsocket_server_requests_total[5m]))
            ) > (14.4 * 0.001)
          )
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "RSocket is burning its error budget rapidly"
          description: "Error ratio is above the 14.4x burn-rate threshold."
~~~

Rule này chỉ minh họa. Cần thêm điều kiện traffic tối thiểu, xử lý mẫu số bằng zero, phân nhóm theo service/route phù hợp và kiểm tra alert trong staging trước khi page production. Với SLO khác 99,9%, phải tính lại ngưỡng từ error budget ratio của mục tiêu đó.

## Dashboard SLO cho RSocket

Một dashboard phục vụ cả người trực và người quản lý dịch vụ nên có các panel sau:

| Panel | Nội dung |
|---|---|
| SLO status | SLI hiện tại, mục tiêu và khoảng cách tới SLO |
| Error budget | Budget còn lại và phần đã tiêu thụ trong cửa sổ |
| Burn rate | Burn rate theo cửa sổ 5 phút, 1 giờ, 6 giờ và 24 giờ |
| Latency | p50/p95/p99 theo route và interaction model |
| Success/error | Request rate, error ratio và phân loại lỗi |
| Streams | Active stream, time-to-first-item, event freshness, cancellation |
| Connections | Connection đang mở, connect/disconnect và resume |
| Saturation | CPU, heap, direct memory, GC pause, event-loop pending tasks |
| Dependencies | Latency, error, retry và pool wait của database/service phụ thuộc |

Đặt các panel SLI ở phần đầu. Các metric CPU, heap hoặc connection là tín hiệu chẩn đoán, không thay thế mục tiêu người dùng. Một service có CPU thấp vẫn có thể vi phạm latency SLO vì database hoặc mạng chậm.

## Phân loại mức độ nghiêm trọng của sự cố

Severity phải phản ánh tác động người dùng và phạm vi ảnh hưởng, không chỉ dựa trên một metric kỹ thuật.

| Mức | Tác động | Ví dụ RSocket | Hành động |
|---|---|---|---|
| SEV-1 | Mất dịch vụ diện rộng hoặc rủi ro dữ liệu/an toàn nghiêm trọng | Hầu hết route không thể kết nối; lệnh quan trọng bị mất hoặc xử lý sai | Kích hoạt incident command, page ngay, cập nhật liên tục |
| SEV-2 | Suy giảm lớn ở chức năng hoặc nhóm khách hàng quan trọng | p99 vượt xa SLO, tỷ lệ lỗi cao ở route thanh toán/đặt hàng | Gọi nhóm trực và owner dependency, mitigation khẩn |
| SEV-3 | Ảnh hưởng giới hạn, có workaround | Một route phụ chậm hoặc một vùng gặp lỗi | Tạo incident/ticket, xử lý trong giờ làm việc hoặc theo SLA |
| SEV-4 | Vấn đề nhỏ, chưa có ảnh hưởng người dùng đáng kể | Metric bất thường đơn lẻ, cảnh báo capacity sớm | Ghi nhận và xử lý theo backlog |

Mỗi tổ chức cần quy định thời gian phản hồi, người có quyền tuyên bố severity và điều kiện nâng/hạ mức. Nếu sự cố ảnh hưởng đến bảo mật hoặc tính toàn vẹn dữ liệu, không xếp mức thấp chỉ vì tỷ lệ request bị ảnh hưởng nhỏ.

## Quy trình ứng phó sự cố

~~~mermaid
flowchart TD
    A[Alert hoặc báo cáo người dùng] --> B[Xác nhận và phân loại]
    B --> C[Declare incident, chỉ định vai trò]
    C --> D[Đánh giá phạm vi và timeline]
    D --> E[Mitigate: giảm tác động]
    E --> F{SLI đã phục hồi ổn định?}
    F -->|Chưa| E
    F -->|Rồi| G[Recover và theo dõi]
    G --> H[Resolve incident]
    H --> I[Postmortem và action items]
~~~

### 1. Phát hiện và xác nhận

- Kiểm tra alert có phản ánh SLI thật hay là lỗi telemetry.
- Xác định route, interaction model, region, tenant hoặc phiên bản bị ảnh hưởng.
- So sánh client latency với server handler latency.
- Xem error ratio, burn rate và traffic tối thiểu.
- Tìm thời điểm bắt đầu và thay đổi triển khai gần nhất.

Không mất thời gian tranh luận nguyên nhân trước khi xác định phạm vi và tác động.

### 2. Declare incident và phân vai

Một incident có thể dùng các vai trò sau:

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander (IC) | Điều phối, đặt ưu tiên, phân công, quyết định severity và kết thúc incident |
| Operations/Tech Lead | Điều tra kỹ thuật, chọn mitigation, theo dõi SLI |
| Communications Lead | Cập nhật trạng thái cho khách hàng, support và stakeholder |
| Scribe | Ghi timeline, quyết định, bằng chứng và action item |
| Subject Matter Expert | Hỗ trợ sâu về RSocket, database, network, security hoặc dependency |

Ở sự cố nhỏ, một người có thể kiêm nhiều vai trò. Với SEV-1/SEV-2, tách vai trò giúp người điều tra không phải vừa sửa hệ thống vừa quản lý thông tin.

### 3. Đánh giá tác động

Trả lời nhanh:

- Ai bị ảnh hưởng: toàn bộ khách hàng, một tenant, một region hay một loại client?
- Chức năng nào bị ảnh hưởng: request-response, stream, channel hay fire-and-forget?
- Số request, stream hoặc command bị ảnh hưởng?
- Có nguy cơ mất, trùng hoặc xử lý sai dữ liệu không?
- SLO/error budget đang bị tiêu thụ ở tốc độ nào?
- Có thay đổi gần đây về code, cấu hình, certificate, routing hoặc dependency?

Ghi lại thời điểm phát hiện, thời điểm bắt đầu, các mốc thay đổi và nguồn dữ liệu.

### 4. Mitigation trước khi sửa nguyên nhân gốc

Ưu tiên hành động có thể giảm tác động nhanh và có thể rollback:

- Rollback release hoặc cấu hình vừa triển khai nếu có tương quan rõ.
- Giảm admission/concurrency cho route đang quá tải.
- Tạm ngừng tính năng không thiết yếu hoặc route có lỗi.
- Giới hạn payload size và tốc độ producer để bảo vệ consumer.
- Chuyển traffic sang instance/region khỏe nếu kiến trúc hỗ trợ.
- Mở circuit breaker hoặc bulkhead cho dependency đang lỗi.
- Tăng timeout chỉ khi đã hiểu hệ quả; timeout dài hơn có thể giữ stream và tài nguyên lâu hơn.
- Tạm tắt retry gây khuếch đại tải hoặc điều chỉnh backoff/jitter.
- Dùng fallback/cached response khi nghiệp vụ cho phép.
- Bảo vệ command bằng idempotency key nếu cần replay sau lỗi.

Đừng xóa queue hoặc reset session hàng loạt khi chưa biết dữ liệu đang nằm ở đâu. RSocket resumption giúp tiếp tục session trong điều kiện phù hợp, nhưng không thay thế durable queue hoặc event log. Khi cần restart, drain connection có kiểm soát và bảo đảm client có chính sách reconnect/replay.

### 5. Khôi phục và xác nhận

Sau mitigation:

- Xác nhận error ratio và latency trở lại trong ngưỡng.
- Theo dõi burn rate trên cả cửa sổ ngắn và dài.
- Kiểm tra active stream, connection và queue depth có giảm về mức bình thường.
- Xác nhận dependency đã phục hồi và retry không còn tăng.
- Kiểm tra dữ liệu: command chưa xử lý, event trùng, sequence gap hoặc outbox backlog.
- Theo dõi đủ lâu để phát hiện tái phát trước khi resolve.

Không đóng incident chỉ vì alert tự clear trong vài phút. Hãy xác nhận SLI phục hồi ổn định và các tác vụ tồn đọng đã được xử lý.

## Runbook ứng phó cho RSocket

Một runbook tốt phải chỉ ra hành động cụ thể, dashboard cần mở, lệnh an toàn và điều kiện dừng. Bảng sau là khung ban đầu; điền service name, owner, dashboard và command thực tế của môi trường.

| Triệu chứng | Kiểm tra đầu tiên | Mitigation có thể cân nhắc |
|---|---|---|
| Request-response p99 tăng | Client/server duration, route, dependency span | Rollback, giới hạn concurrency, fallback |
| Error rate tăng sau deploy | Release marker, exception group, route mới | Rollback phiên bản hoặc cấu hình |
| Stream không phát event | Time-to-first-item, source lag, subscription state | Khôi phục producer, replay từ cursor |
| Connection reset hàng loạt | TCP/WebSocket close, proxy, certificate, server restart | Sửa proxy/certificate, chuyển traffic |
| Resume thất bại tăng | Session retention, resume buffer, process restart | Reconnect và phục hồi từ durable cursor |
| Queue/outbox backlog tăng | Publish rate, consumer lag, downstream health | Giảm admission, tăng consumer trong capacity |
| Memory/direct buffer tăng | Heap, direct memory, connection/stream count | Giới hạn stream/payload, kiểm tra leak, rollout có kiểm soát |
| Dependency timeout | Pool wait, remote p95/p99, circuit breaker | Bulkhead, cache/fallback, giảm retry |

### Khi latency SLO bị vi phạm

1. Mở dashboard SLO và xem route/interaction nào vi phạm.
2. So sánh client end-to-end với server duration.
3. Mở trace mẫu để xác định handler hay dependency chậm.
4. Kiểm tra release/configuration marker.
5. Nếu có thay đổi tương quan, đánh giá rollback.
6. Nếu dependency chậm, áp dụng bulkhead/circuit breaker và giới hạn concurrency.
7. Theo dõi burn rate tới khi ổn định.

### Khi error rate tăng

1. Phân loại lỗi theo transport, setup, decode, authorization, application và dependency.
2. Kiểm tra lỗi có tập trung vào một route hoặc một phiên bản client không.
3. Xác định lỗi có làm command bị xử lý một phần hoặc không rõ kết quả không.
4. Giảm tải hoặc rollback nếu lỗi do release/cấu hình.
5. Với command có unknown outcome, tra cứu trạng thái bằng command ID trước khi retry.
6. Kiểm tra outbox/inbox, duplicate và event sequence sau khi phục hồi.

### Khi stream hoặc connection tăng bất thường

1. So sánh active streams với connection count và traffic.
2. Kiểm tra stream duration, cancellation và time-to-first-item.
3. Tìm client không cancel subscription hoặc không đọc dữ liệu.
4. Kiểm tra event-loop pending tasks, direct memory và buffer.
5. Giới hạn số stream/connection theo tenant hoặc client nếu cần.
6. Dùng drain/graceful close để client reconnect có kiểm soát.

## Giao tiếp trong incident

Thông tin trạng thái cần ngắn, nhất quán và tập trung vào tác động.

Mẫu cập nhật nội bộ:

~~~text
Incident: RSocket inventory latency
Severity: SEV-2
Status: Investigating / Mitigating / Monitoring / Resolved
Started: 10:05 UTC
Impact: 18% request inventory.lookup tại region A vượt 200 ms
Current evidence: Server handler p95 ổn định; pricing dependency p99 tăng
Mitigation: Đã bật bulkhead và fallback cache
Next update: 10:20 UTC
Owner: Incident Commander
~~~

Mẫu thông báo khách hàng:

~~~text
Chúng tôi đang điều tra tình trạng chậm phản hồi khi truy vấn tồn kho tại một số khu vực.
Một số request có thể mất nhiều thời gian hơn bình thường hoặc phải thử lại.
Dữ liệu tồn kho đã ghi nhận không bị ảnh hưởng theo kiểm tra hiện tại.
Chúng tôi đang áp dụng biện pháp giảm tác động và sẽ cập nhật khi có thông tin xác nhận.
~~~

Chỉ đưa ra khẳng định về dữ liệu hoặc phạm vi ảnh hưởng khi đã có bằng chứng. Không công bố suy đoán nguyên nhân như kết luận cuối cùng.

## Postmortem không đổ lỗi

Sau khi incident được resolve, tổ chức postmortem để tìm điều kiện hệ thống cho phép sự cố xảy ra và vì sao cơ chế phát hiện/mitigation chưa đủ nhanh.

Một postmortem nên có:

1. **Summary:** điều gì xảy ra và tác động tới ai.
2. **Impact:** số request, thời lượng, vùng, tenant, dữ liệu hoặc doanh thu bị ảnh hưởng.
3. **Detection:** alert nào phát hiện, alert có trễ hoặc thiếu tín hiệu nào?
4. **Timeline:** các mốc phát hiện, declare, mitigation, recovery và resolve.
5. **Contributing factors:** code, cấu hình, capacity, dependency, quy trình hoặc thiếu guardrail.
6. **What went well:** cơ chế nào giúp giảm tác động.
7. **What made it harder:** tín hiệu thiếu, quyền hạn không rõ, runbook lỗi thời.
8. **Action items:** hành động cụ thể, owner, due date và cách xác minh.

Tránh viết “người vận hành quên kiểm tra” như nguyên nhân gốc. Hãy hỏi vì sao quy trình, công cụ hoặc thiết kế cho phép một lỗi đơn lẻ tạo tác động lớn. Ví dụ: “Một route có thể mở số stream không giới hạn vì chưa có quota theo tenant” là mô tả điều kiện hệ thống có thể cải thiện.

Action item tốt có kết quả kiểm chứng được, ví dụ:

- Thêm SLI time-to-first-item cho route event stream.
- Thêm burn-rate alert 1h/5m và 6h/30m.
- Đặt giới hạn active stream theo tenant.
- Bổ sung test reconnect và replay sau server restart.
- Thêm release marker vào dashboard latency.
- Cập nhật runbook để xác định outbox backlog và command unknown outcome.

## Diễn tập sự cố và kiểm chứng quy trình

Không chờ production có sự cố mới thử runbook. Thực hiện game day hoặc chaos exercise trong môi trường kiểm thử/staging:

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Dependency tăng latency | SLO alert kích hoạt, bulkhead/fallback giảm tác động |
| Server restart | Client reconnect, resume hoặc replay theo thiết kế |
| Certificate hết hạn/sai chain | Alert phát hiện, runbook xác định TLS failure |
| Một route trả lỗi tăng | Dashboard phân biệt route và error type |
| Stream consumer chậm | Backpressure/limit hoạt động, memory không tăng vô hạn |
| Outbox publisher dừng | Backlog được phát hiện, event không mất |
| Release gây regression | Release marker và burn-rate alert giúp rollback sớm |

Sau diễn tập, ghi lại thời gian phát hiện (MTTD), thời gian mitigation (TTM) và thời gian phục hồi (MTTR) để tìm điểm cần cải thiện. Không dùng MTTR làm thước đo cá nhân; dùng nó để đánh giá khả năng của hệ thống và quy trình.

## Checklist định nghĩa SLO và ứng phó sự cố

### SLO

1. SLI có phản ánh trải nghiệm client không?
2. Mẫu số và good event được định nghĩa rõ chưa?
3. Request-response, stream và fire-and-forget có SLI phù hợp riêng chưa?
4. Latency threshold có dựa trên dữ liệu và nhu cầu nghiệp vụ không?
5. Error classification có nhất quán giữa client và server không?
6. Cửa sổ SLO và error budget đã được công bố cho owner chưa?
7. Histogram có bucket phù hợp với latency objective không?
8. Có dashboard theo route, interaction và region với cardinality giới hạn không?

### Incident response

1. Alert có thể hành động và có runbook đi kèm không?
2. Severity và người có quyền declare incident đã rõ chưa?
3. Incident Commander, Tech Lead và Communications Lead có thể được chỉ định không?
4. Có bước đánh giá tác động và kiểm tra dữ liệu không?
5. Mitigation có thể rollback và không làm mất command/event không?
6. Client retry có backoff/jitter và idempotency không?
7. Có điều kiện xác nhận phục hồi trước khi resolve không?
8. Postmortem có owner và deadline cho action item không?
9. Runbook đã được diễn tập gần đây chưa?

SLO biến chất lượng RSocket thành mục tiêu có thể đo và quản lý. Error budget giúp cân bằng tốc độ phát hành với độ tin cậy; burn-rate alert giúp phát hiện khi ngân sách bị tiêu thụ quá nhanh. Khi có sự cố, ưu tiên xác định tác động, phân vai rõ ràng, giảm ảnh hưởng và xác nhận SLI phục hồi. Postmortem và game day giúp chuyển sự cố thành cải tiến cụ thể cho kiến trúc, telemetry và quy trình vận hành.

## Tài liệu tham khảo

- [Google SRE Workbook: Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google SRE Book: Being On-Call](https://sre.google/sre-book/being-on-call/)
- [Google SRE Book: Managing Incidents](https://sre.google/sre-book/managing-incidents/)
- [Google SRE Book: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [Prometheus: Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
- [Prometheus: Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [OpenTelemetry: Semantic conventions for RPC metrics](https://opentelemetry.io/docs/specs/semconv/rpc/rpc-metrics/)
- [Spring Boot: Metrics and Micrometer](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)

