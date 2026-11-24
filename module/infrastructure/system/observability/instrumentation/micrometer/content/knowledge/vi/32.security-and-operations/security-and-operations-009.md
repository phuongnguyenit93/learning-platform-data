# Tài liệu tên meter, đơn vị, tag, chủ sở hữu và cách diễn giải

## Vì sao cần một catalog metric?

Một metric chỉ hữu ích khi người khác hiểu chính xác nó đo điều gì. Tên meter có thể dễ đọc nhưng vẫn gây hiểu nhầm nếu không biết sự kiện nào làm nó tăng, thời điểm ghi nhận, đơn vị, tag, phạm vi tổng hợp hoặc cách diễn giải.

Trong ứng dụng Java dùng Micrometer, Counter, Gauge, Timer, DistributionSummary và các meter khác có thể được đăng ký ở nhiều component. Spring Boot có thể tự động thêm binder; thư viện bên thứ ba cũng có thể tạo meter; nhóm nghiệp vụ có thể tự instrument. Nếu mỗi nhóm đặt tên và tag theo cách riêng, dashboard và alert sẽ khó duy trì, các metric cùng tên có thể mang semantics khác nhau và người trực vận hành không biết liên hệ ai khi số liệu bất thường.

Catalog metric là tài liệu mô tả hợp đồng của từng meter. Nó giúp người phát triển, reviewer, người vận hành và chủ sở hữu nghiệp vụ hiểu:

- Metric đo đại lượng hoặc sự kiện nào.
- Meter được tạo ở component và code path nào.
- Loại meter, đơn vị và quy tắc ghi nhận.
- Tag nào được phép, giá trị nào có thể xuất hiện và cardinality dự kiến.
- Ai chịu trách nhiệm về instrumentation và cách diễn giải.
- Truy vấn, dashboard, alert hoặc SLO nào sử dụng metric.
- Những giới hạn, sai lệch và thay đổi tương thích cần lưu ý.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, tài liệu này áp dụng cho metrics được tạo bằng Micrometer, tích hợp Spring Boot và xuất đến hệ thống giám sát. Một catalog tốt không chỉ liệt kê tên metric; nó giải thích ý nghĩa của số đo để tránh diễn giải sai khi xử lý sự cố.

## Một metric cần có những trường thông tin nào?

Một bản ghi catalog nên có tối thiểu các nhóm thông tin sau:

| Nhóm | Nội dung cần ghi | Câu hỏi được trả lời |
|---|---|---|
| Identity | Tên meter, tên hiển thị, loại | Đang xem metric nào? |
| Semantics | Định nghĩa sự kiện/đại lượng, điểm ghi nhận | Con số thực sự đại diện cho điều gì? |
| Unit | Base unit, quy tắc chuyển đổi | Giá trị được tính bằng đơn vị nào? |
| Dimensions | Tag key, allow-list, giá trị mặc định | Có thể phân tích theo chiều nào? |
| Cardinality | Số giá trị dự kiến, giới hạn, histogram | Chi phí time series là bao nhiêu? |
| Ownership | Service, team, component, người chịu trách nhiệm | Ai duy trì và giải thích metric? |
| Source | Binder, class, method hoặc thư viện tạo meter | Dữ liệu được ghi ở đâu? |
| Interpretation | Công thức, aggregation, query, caveat | Nên đọc số liệu như thế nào? |
| Operations | Dashboard, alert, SLO, runbook | Metric phục vụ quy trình vận hành nào? |
| Lifecycle | Trạng thái, phiên bản, kế hoạch thay đổi | Metric còn được hỗ trợ không? |
| Security | Dữ liệu bị cấm, quyền truy cập, retention | Có rủi ro lộ thông tin không? |

Không phải metric nào cũng cần một tài liệu dài. Tuy nhiên, những trường về semantics, unit, owner, tags và cách diễn giải phải đủ rõ để một người không viết instrumentation ban đầu vẫn sử dụng đúng.

## Đặt tên meter ổn định và có ý nghĩa

### Tên mô tả đại lượng, không mô tả chi tiết triển khai

Tên meter nên ngắn, ổn định, viết thường và thể hiện đại lượng hoặc hoạt động được đo. Với Micrometer, cách đặt tên dạng phân cấp bằng dấu chấm thường dễ đọc trong code:

- orders.completed
- orders.processing
- http.server.requests
- jobs.queue.depth
- cache.requests
- payment.authorization

Tên nên giữ ổn định qua các lần refactor nội bộ nếu semantics không đổi. Không đưa tên class, method implementation, hostname, pod ID, request ID hoặc giá trị tag vào tên.

Ví dụ, nếu đổi tên class OrderCompletionService thành CheckoutFinalizer nhưng metric vẫn đo số đơn hàng đã hoàn tất, không cần đổi tên meter chỉ vì tên class thay đổi.

### Tên meter và tên xuất ra backend có thể khác nhau

Micrometer dùng NamingConvention của registry để ánh xạ tên và tag sang định dạng backend. Một tên logic có dấu chấm có thể được chuẩn hóa thành dấu gạch dưới ở Prometheus. Timer còn có thể được biểu diễn bằng các sample liên quan đến seconds, count, sum, max hoặc histogram bucket.

Vì vậy, catalog nên ghi cả:

- **Micrometer name:** tên dùng trong code và registry.
- **Backend representation:** tên sample hoặc dạng dữ liệu mà backend nhận, nếu cần tra cứu trực tiếp.

Không giả định mọi registry tạo cùng một tên xuất. Khi thay registry hoặc phiên bản, kiểm tra exposition thực tế trước khi cập nhật dashboard và alert.

### Không nhúng đơn vị vào tên một cách tùy tiện

Đơn vị nên được mô tả bằng base unit của meter và metadata trong catalog. Một số registry tự chuẩn hóa hoặc thêm đơn vị vào tên xuất, đặc biệt với Timer. Nếu tên logic đã có hậu tố đơn vị nhưng registry lại thêm đơn vị lần nữa, tên backend có thể khó đọc hoặc lặp nghĩa.

Chọn một quy ước nhất quán cho module và xác minh kết quả của registry đang dùng. Ví dụ, Timer có thể dùng tên logic orders.processing và đơn vị thời gian do Micrometer/registry quản lý; catalog ghi rõ thời lượng được xuất theo seconds nếu backend quy định như vậy.

### Không dùng cùng tên cho hai semantics khác nhau

Nếu một Counter đo số lần handler được gọi và một Counter khác đo số đơn hàng commit, chúng không nên dùng cùng tên. Một tên metric phải có một định nghĩa duy nhất trong cùng phạm vi hệ thống.

Tương tự, không thay đổi một meter từ đếm attempt sang đếm business completion mà vẫn giữ tên, tag và dashboard cũ. Đây là thay đổi semantics, ngay cả khi kiểu meter vẫn là Counter.

## Ghi rõ loại meter và ngữ nghĩa

### Counter

Counter biểu diễn một đại lượng tích lũy tăng theo sự kiện. Catalog cần nêu rõ sự kiện làm counter tăng và liệu mỗi business operation có thể được đếm nhiều lần do retry hay không.

Ví dụ:

- orders.completed: tăng sau khi đơn hàng được commit thành công.
- payments.failed: tăng cho mỗi lần xử lý thanh toán thất bại.
- messages.consumed: tăng khi consumer nhận message, không nhất thiết khi xử lý thành công.

Không dùng Counter cho trạng thái có thể tăng rồi giảm, như số kết nối hiện tại hoặc số job đang chờ. Những đại lượng đó phù hợp với Gauge.

Khi diễn giải Counter, thường quan tâm rate hoặc increase trong một khoảng thời gian. Giá trị tuyệt đối có thể reset khi process restart hoặc meter được tạo lại.

### Gauge

Gauge biểu diễn giá trị hiện tại tại thời điểm được đọc, ví dụ:

- jobs.queue.depth: số job đang chờ.
- worker.active: số worker đang hoạt động.
- database.connections.active: số connection đang được sử dụng.

Catalog cần chỉ ra nguồn dữ liệu, thời điểm cập nhật, cách đồng bộ và liệu phép đọc có an toàn đa luồng hay không. Gauge không phải bộ đếm sự kiện; không cộng các snapshot theo thời gian để suy ra tổng số sự kiện.

Với Gauge dựa trên object, cần giữ strong reference đến nguồn trong suốt vòng đời cần đo vì Micrometer Gauge thường giữ weak reference. Callback đọc Gauge phải nhẹ và không thực hiện I/O blocking.

### Timer

Timer đo thời lượng của các lần thực thi và cung cấp count cùng total time; tùy cấu hình, nó còn có max, histogram bucket hoặc percentile.

Catalog cần ghi:

- Đo từ thời điểm nào đến thời điểm nào.
- Count gồm success, failure hay cả hai.
- Đơn vị thời gian.
- Histogram/SLO boundaries và percentile được bật.
- Backend dùng count/sum/bucket hoặc cấu trúc tương ứng nào.

Không mặc định Timer chỉ đếm thành công. Nếu Timer bao quanh method và method ném exception, lần thực thi đó vẫn có thể được ghi nhận. Nếu cần phân loại, dùng tag outcome có tập giá trị hữu hạn hoặc tách meter theo semantics rõ ràng.

### DistributionSummary

DistributionSummary ghi nhận phân phối của giá trị số như payload size, batch size hoặc số bản ghi mỗi batch. Catalog cần ghi đơn vị của giá trị được record và cách diễn giải count, total amount, max, histogram hoặc percentile.

Không dùng tag để lưu giá trị đo. Ví dụ payload size 100, 200 và 500 bytes là các observation của cùng DistributionSummary; không tạo tag size=100, size=200, size=500 nếu mục tiêu là đo phân phối.

### FunctionCounter, FunctionTimer và LongTaskTimer

Nếu meter đọc một bộ đếm hoặc thống kê do thư viện khác quản lý, catalog cần chỉ rõ nguồn dữ liệu và semantics của function. Với FunctionCounter, nguồn thường là một giá trị tích lũy đơn điệu. Với FunctionTimer, nguồn cung cấp count và total time đã tích lũy.

LongTaskTimer phù hợp với tác vụ kéo dài đang hoạt động, nơi cần quan sát số tác vụ hiện tại và thời lượng của những tác vụ chưa hoàn tất. Không thay thế Timer thông thường nếu mục tiêu là đo từng operation sau khi kết thúc.

Loại meter quyết định cách diễn giải và aggregation. Ghi rõ loại trong catalog để người dùng không áp dụng rate lên Gauge hoặc cộng các snapshot như Counter.

## Đơn vị: ghi rõ đại lượng và quy tắc chuyển đổi

Đơn vị phải mô tả đại lượng thực sự được đo, không chỉ định dạng hiển thị trên dashboard.

| Đại lượng | Đơn vị gợi ý | Ví dụ |
|---|---|---|
| Thời gian | seconds | Timer đo thời gian xử lý |
| Dung lượng | bytes | DistributionSummary đo payload |
| Số phần tử | items, jobs, orders | Gauge queue depth hoặc Counter completion |
| Tỷ lệ | ratio hoặc percent theo quy ước thống nhất | CPU usage |
| Kích thước batch | records | DistributionSummary ghi số bản ghi |
| Kết nối | connections | Gauge số connection active |

Dùng đơn vị chuẩn và thống nhất giữa các component. Tránh để một meter ghi milliseconds ở instance này nhưng seconds ở instance khác. Micrometer Timer nhận duration và chuyển đổi theo base time unit của registry; code nên dùng API có đơn vị rõ như record(duration, TimeUnit) hoặc Duration.

Với Gauge và DistributionSummary, cần ghi rõ giá trị nguồn là bytes, kilobytes, records hay một đại lượng khác. Backend không thể suy ra unit nếu code và catalog không khai báo đúng.

Nếu dashboard đổi đơn vị để hiển thị, ghi rõ phép chuyển đổi. Ví dụ, backend lưu seconds nhưng dashboard hiển thị milliseconds; người đọc không nên so trực tiếp số trên dashboard với giá trị thô trong exposition.

## Thiết kế tag và allow-list

### Tag là dimension để tổng hợp

Tag cho phép phân tích cùng một meter theo các nhóm có ý nghĩa. Ví dụ orders.completed có thể phân loại theo channel hoặc region nếu số giá trị được kiểm soát.

Tag key nên ổn định và có tên rõ ràng:

- channel
- outcome
- operation
- region
- provider
- cache
- pool

Catalog cần ghi từng tag, ý nghĩa, giá trị được phép và giá trị fallback. Không chỉ ghi rằng tag là string; cần mô tả tập giá trị có thể xuất hiện.

### Ghi allow-list cụ thể

Ví dụ catalog cho metric đơn hàng:

| Tag key | Ý nghĩa | Giá trị được phép | Giá trị ngoài tập |
|---|---|---|---|
| channel | Kênh tạo đơn | web, mobile, partner | other |
| outcome | Kết quả xử lý | success, failure, rejected | unknown |
| region | Vùng triển khai | ap-southeast-1, eu-west-1 | other |

Giá trị fallback giúp tránh tạo series mới khi upstream gửi một giá trị không nhận diện. Tuy nhiên, fallback phải được dùng có chủ đích và có thể cần một metric/log riêng để phát hiện dữ liệu không hợp lệ.

Chuẩn hóa chữ hoa/thường, khoảng trắng, alias và giá trị null trước khi ghi meter. Nếu cùng một outcome xuất hiện dưới các dạng SUCCESS, success và ok, dashboard có thể tách thành nhiều series dù chúng cùng ý nghĩa.

### Không đưa ID hoặc dữ liệu tự do vào tag

Không dùng các giá trị sau làm metric tag:

- request ID, trace ID, span ID.
- user ID, order ID, payment reference.
- URL đầy đủ chứa resource ID.
- SQL statement hoặc exception message.
- Tên file, message ID hoặc key tùy ý.
- Email, token, session cookie hoặc dữ liệu cá nhân.

Các giá trị duy nhất làm cardinality tăng nhanh và có thể lộ thông tin. Dùng route template thay cho URL đầy đủ, error type đã chuẩn hóa thay cho exception message và exemplar/log/trace correlation thay cho trace ID tag.

High-cardinality attribute trong trace cũng cần chính sách bảo vệ dữ liệu; không phải vì nó không phải metric tag mà có thể gửi mọi nội dung.

## Ước tính cardinality trước khi thêm tag

Số series có thể tăng theo tích số giá trị của các tag. Nếu một meter có 4 method, 3 outcome, 5 region và 2 provider, số tổ hợp tối đa là:

~~~text
4 x 3 x 5 x 2 = 120 series cho một meter identity cơ sở
~~~

Với histogram, mỗi tổ hợp tag có thể tạo nhiều bucket và các chuỗi count/sum liên quan. Khi nhân với số instance và số metric, tổng số series tăng nhanh.

Catalog nên ghi cardinality dự kiến, nguồn của mỗi tập giá trị và ngân sách cho histogram. Nếu không thể ước lượng vì một tag có giá trị không giới hạn, tag đó không phù hợp cho metrics.

Resource attributes như service.name, service.instance.id và deployment environment có thể được thêm ở tầng registry/exporter. Catalog cần ghi rõ chúng đến từ đâu và được áp dụng ở phạm vi resource hay meter tag để tránh nhầm lẫn khi aggregation.

## Chủ sở hữu và nguồn tạo metric

### Owner phải là một nhóm chịu trách nhiệm thực tế

Mỗi metric nên có owner có thể trả lời khi semantics thay đổi hoặc dashboard báo bất thường. Tối thiểu cần ghi:

- Service hoặc module sở hữu.
- Team chịu trách nhiệm instrumentation.
- Component/binder tạo meter.
- Code location hoặc tên convention.
- Kênh hỗ trợ hoặc runbook nội bộ nếu có.
- Người/nhóm phê duyệt thay đổi semantics.

Không dùng tên một cá nhân làm owner duy nhất nếu việc bàn giao không được quản lý. Ownership nên gắn với nhóm vận hành hoặc nhóm phát triển duy trì service.

### Ghi nguồn instrumentation

Nguồn có thể là:

- Spring Boot auto-configured binder.
- Micrometer MeterBinder do ứng dụng viết.
- ObservationConvention hoặc ObservationHandler.
- @Timed/@Counted qua AOP.
- Client/server instrumentation của thư viện.
- Code nghiệp vụ gọi Counter, Timer hoặc Gauge trực tiếp.

Catalog cần nêu điểm ghi nhận cụ thể, chẳng hạn sau transaction commit, khi consumer nhận message, khi message xử lý xong hoặc khi request kết thúc. Đây là phần quyết định metric đếm attempt hay business outcome.

Với binder tự động, ghi dependency và điều kiện bean quan trọng. Với meter nghiệp vụ, ghi class/method hoặc sự kiện phát sinh để reviewer tìm được nơi cập nhật.

## Mẫu catalog cho một metric

Ví dụ dưới đây là cấu trúc tài liệu minh họa, không phải file cấu hình Micrometer bắt buộc:

~~~yaml
metric:
  name: orders.completed
  display_name: Completed orders
  type: counter
  description: Number of unique orders committed successfully
  base_unit: orders
  event_definition: Increment once after the order transaction commits
  source:
    service: checkout-service
    component: OrderCompletionMetrics
    instrumentation: explicit-counter
  tags:
    channel:
      description: Order acquisition channel
      allowed_values: [web, mobile, partner, other]
      fallback: other
    region:
      description: Deployment region
      allowed_values: [ap-southeast-1, eu-west-1, other]
      fallback: other
  cardinality:
    max_tag_combinations: 12
    histogram: false
  ownership:
    team: commerce-platform
    contact: checkout-oncall
  interpretation:
    primary_use: Completed order throughput
    query_example: increase(orders_completed_total[5m])
    caveat: Retries do not increment again after idempotent commit
  operations:
    dashboard: Checkout business overview
    alert: Unexpected drop in completed order rate
  lifecycle:
    state: active
    introduced_in: 1.4
    review_owner: commerce-platform
  security:
    prohibited_attributes: [order_id, user_id, payment_reference]
~~~

Tên team, service, version, dashboard và contact trong ví dụ chỉ là giá trị minh họa. Khi áp dụng, thay bằng thông tin thực của hệ thống. Không sao chép nguyên ví dụ thành metric tag hoặc cấu hình runtime.

## Cách diễn giải theo từng loại meter

### Counter: rate, increase và reset

Counter tích lũy theo thời gian. Với Prometheus, thường dùng rate để tính tốc độ trung bình trên cửa sổ hoặc increase để ước lượng mức tăng trong cửa sổ.

Ví dụ:

~~~promql
sum by (channel) (
  rate(orders_completed_total[5m])
)
~~~

Query này tổng hợp throughput theo channel. Tên sample thực tế phụ thuộc naming convention và registry. Catalog cần ghi metric có phải counter cumulative không, tag channel có allow-list nào và query có nên loại bỏ instance dimension trước hay sau rate.

Counter có thể reset khi process restart hoặc meter được tạo lại. Dùng rate/increase theo từng series trước khi tổng hợp để hệ thống nhận biết reset đúng cách. Không so raw counter giữa hai lần restart như thể nó là tổng lịch sử bền vững.

### Gauge: snapshot, không phải tốc độ

Gauge biểu diễn giá trị tại thời điểm scrape/export. Ví dụ queue depth bằng 12 có nghĩa tại thời điểm đọc có khoảng 12 job đang chờ theo nguồn Gauge.

Không dùng rate trên Gauge nếu đại lượng không được định nghĩa như một tín hiệu có ý nghĩa theo thời gian. Không cộng các snapshot của cùng một queue qua nhiều lần scrape để tính tổng job đã xử lý.

Khi tổng hợp nhiều instance, quyết định dùng sum, max, min hoặc average theo semantics. Queue depth toàn hệ thống có thể dùng sum nếu mỗi job chỉ nằm trong một queue; max có thể giúp phát hiện một instance bị nghẽn.

### Timer: count, total time và latency distribution

Timer ghi count và total time của các observation. Mean có thể tính bằng total time chia count, nhưng mean không thay thế percentile khi cần hiểu tail latency.

Nếu histogram được bật, có thể dùng bucket để tính percentile tổng hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Catalog phải ghi route/status/outcome dimensions, histogram boundaries và cách query tổng hợp. Không tính percentile bằng cách lấy trung bình các p95 của từng instance; cần tổng hợp bucket đúng cách trước khi tính quantile.

### DistributionSummary: phân phối của giá trị số

DistributionSummary ghi count, total amount và thống kê phân phối cho đại lượng như bytes hoặc records. Catalog cần chỉ rõ giá trị được record là payload size, batch size hay số item; không nhầm tổng amount với số operation.

Nếu đo payload size bằng bytes, total amount là tổng bytes của các observation trong chu kỳ/temporality tương ứng. Mean là total amount chia count. Max hoặc percentile phụ thuộc cấu hình và cửa sổ thống kê.

## Tài liệu truy vấn, dashboard và alert

Metric catalog nên liên kết đến nơi metric được sử dụng. Một metric không cần dashboard riêng, nhưng nếu nó phục vụ SLO hoặc cảnh báo thì phải ghi cách truy vấn và điều kiện diễn giải.

Với mỗi dashboard/alert, tài liệu nên nêu:

- Query hoặc biểu thức chính.
- Khoảng thời gian và aggregation.
- Các tag được giữ hoặc loại khi group.
- Ngưỡng cảnh báo và lý do.
- Điều kiện thiếu dữ liệu hoặc không có traffic.
- Runbook cần mở khi cảnh báo kích hoạt.

Không tạo alert chỉ dựa trên một giá trị metric mà không hiểu traffic baseline. Ví dụ, rate bằng 0 có thể là sự cố hoặc đơn giản là không có request trong cửa sổ. Alert nên kết hợp điều kiện availability, traffic hoặc business schedule phù hợp.

Nếu metric được dùng để tính SLO, catalog phải nêu numerator, denominator, outcome được tính và cách xử lý request bị loại. Người vận hành cần biết chính xác tỷ lệ đang đo request thành công, operation hoàn tất hay transaction commit.

## Bảo mật và quyền riêng tư trong metric metadata

Tag và resource attributes có thể được gửi đến backend, lưu lâu dài, lập chỉ mục và chia sẻ cho nhiều nhóm. Catalog cần liệt kê dữ liệu không được phép thu thập:

- Credential, token, cookie hoặc secret.
- Payload request/response.
- Email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân không cần thiết.
- User/order/payment identifier nếu không có use case và chính sách phê duyệt.
- SQL literal hoặc exception message có thể chứa dữ liệu đầu vào.

Không dùng hash đơn giản để mặc định biến dữ liệu nhạy cảm thành an toàn. Hash ổn định vẫn có thể cho phép liên kết hoặc suy ra giá trị, đặc biệt khi miền đầu vào nhỏ. Nếu thật sự cần correlation, dùng định danh giả danh được thiết kế và quản lý theo chính sách bảo mật.

Catalog nên chỉ rõ metric backend nào có thể truy cập bởi ai, retention bao lâu và dữ liệu nào được phép index. Dữ liệu high-cardinality trong trace cũng cần đánh giá tương tự vì nó có thể được lưu và tìm kiếm.

## Versioning, thay đổi và ngừng metric

### Khi nào thay đổi được xem là breaking?

Các thay đổi sau có thể phá vỡ dashboard, alert hoặc consumer:

- Đổi tên meter.
- Đổi loại meter hoặc semantics.
- Đổi đơn vị hoặc scale.
- Đổi tên tag key.
- Thay allow-list hoặc cách chuẩn hóa tag.
- Đổi thời điểm ghi nhận sự kiện.
- Đổi histogram bucket hoặc temporality.
- Thay đổi phạm vi tổng hợp hoặc resource identity.

Ngay cả khi code compile, thay đổi semantics vẫn có thể làm biểu đồ mất tính liên tục. Không đổi tên hoặc semantics âm thầm.

### Quy trình deprecate

Khi cần thay metric:

1. Tạo metric mới với định nghĩa và catalog rõ ràng.
2. Trong giai đoạn chuyển tiếp, có thể ghi cả metric cũ và mới nếu chi phí cho phép.
3. Cập nhật dashboard, alert, SLO và truy vấn consumer.
4. Thông báo owner và nhóm phụ thuộc.
5. Xác minh metric mới đủ dữ liệu qua một chu kỳ vận hành phù hợp.
6. Đánh dấu metric cũ deprecated với ngày ngừng dự kiến.
7. Xóa instrumentation cũ sau khi consumer đã chuyển.
8. Giữ ghi chú về tên cũ và metric thay thế để tra cứu lịch sử.

Không tái sử dụng tên cũ cho một semantics khác sau khi deprecate. Người dùng có thể vẫn truy vấn dữ liệu lịch sử trong retention window và hiểu sai nếu tên đó đổi nghĩa.

### Review định kỳ

Catalog cần được review khi thêm tag, bật histogram, thay exporter, đổi owner hoặc thay đổi nghiệp vụ. Có thể kiểm tra định kỳ các metric không còn được truy vấn, không có owner, có tag vượt allow-list hoặc có series tăng bất thường.

Metric không còn được dùng nên được deprecate có kiểm soát, không xóa tùy tiện trong một lần refactor. Trước khi loại bỏ, kiểm tra dashboard, alert, SLO và các consumer ngoài service.

## Checklist review một metric mới

Trước khi merge instrumentation, reviewer nên xác minh:

1. Tên meter có ổn định và mô tả đúng đại lượng không?
2. Loại meter có phù hợp với semantics không?
3. Đơn vị và phép chuyển đổi có rõ ràng không?
4. Sự kiện ghi nhận và thời điểm ghi có được mô tả chính xác không?
5. Counter có phân biệt attempt với business outcome không?
6. Timer có định nghĩa rõ ranh giới start/stop và tập operation được đếm không?
7. Gauge có nguồn dữ liệu ổn định, an toàn và callback nhẹ không?
8. Tag key/value có allow-list và fallback không?
9. Có ID duy nhất hoặc dữ liệu nhạy cảm trong tên/tag không?
10. Cardinality và histogram bucket có nằm trong ngân sách không?
11. Service, component và team owner đã được ghi chưa?
12. Có query, dashboard, alert hoặc runbook liên quan không?
13. Resource attributes có bị nhầm với meter tags không?
14. Metric có được kiểm thử về semantics, tags và exporter không?
15. Có quy trình versioning/deprecation nếu thay đổi không?

## Checklist vận hành và đọc metric

Khi dùng metric trong dashboard hoặc điều tra sự cố, hãy xác minh:

1. Đang xem đúng service, environment và instance scope chưa?
2. Tên backend có tương ứng với Micrometer name trong catalog không?
3. Đơn vị hiển thị có đúng với base unit không?
4. Counter đang được đọc bằng rate/increase hay raw value?
5. Gauge có được hiểu là snapshot tại thời điểm scrape không?
6. Timer count/sum/bucket có cùng phạm vi và temporality không?
7. Histogram percentile được tính sau khi tổng hợp bucket đúng cách không?
8. Tag values có đúng allow-list và không bị tách do khác cách viết không?
9. Metric có reset hoặc mất dữ liệu do instance restart không?
10. Owner và runbook có còn đúng với service hiện tại không?

## Kết luận

Tài liệu metric phải mô tả hợp đồng đo lường, không chỉ liệt kê tên meter. Mỗi metric cần có tên ổn định, loại phù hợp, đơn vị rõ ràng, định nghĩa sự kiện, tag có allow-list, cardinality dự kiến, nguồn instrumentation, owner và cách diễn giải. Những thông tin này giúp người phát triển ghi đúng dữ liệu và người vận hành đọc đúng tín hiệu.

Hãy ghi riêng semantics của Counter, Gauge, Timer và DistributionSummary; phân biệt Micrometer name với tên xuất ở backend; mô tả resource attributes và meter tags; đồng thời liên kết query, dashboard, alert và runbook. Catalog cũng cần có quy tắc bảo mật, review, versioning và deprecation để thay đổi instrumentation không âm thầm phá vỡ hệ thống giám sát. Khi metric có hợp đồng rõ ràng và owner cụ thể, dashboard và cảnh báo trở thành công cụ vận hành đáng tin cậy thay vì những con số khó giải thích.
