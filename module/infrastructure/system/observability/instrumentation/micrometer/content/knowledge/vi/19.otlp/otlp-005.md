# Ánh xạ Counter, Gauge, Timer hoặc DistributionSummary thành điểm dữ liệu OTLP

Micrometer cung cấp API đo lường thống nhất cho ứng dụng Java, còn OpenTelemetry Protocol (OTLP) định nghĩa cách biểu diễn và truyền metrics giữa các hệ thống. Khi dùng **OtlpMeterRegistry**, meter của Micrometer được chuyển thành các loại điểm dữ liệu trong mô hình Metrics của OpenTelemetry rồi gửi đến Collector hoặc backend hỗ trợ OTLP.

Ánh xạ không phải lúc nào cũng là quan hệ một-một theo tên meter. **Counter** được biểu diễn thành **Sum** có tính đơn điệu; **Gauge** thành **Gauge**; **Timer** và **DistributionSummary** thường thành **Histogram**, nhưng cấu hình percentile phía ứng dụng có thể làm chúng thành **Summary**. Hiểu đúng loại điểm dữ liệu, đơn vị, attributes và aggregation temporality giúp truy vấn và tổng hợp số liệu chính xác ở backend.

## 1. Từ meter Micrometer đến điểm dữ liệu OTLP

Một luồng metrics qua OTLP thường có các bước:

~~~mermaid
flowchart LR
    A["Counter / Gauge / Timer / DistributionSummary"] --> B["MeterRegistry"]
    B --> C["OtlpMeterRegistry"]
    C --> D["Ánh xạ sang OTLP Metric"]
    D --> E["OTLP Data Points"]
    E --> F["HTTP /v1/metrics"]
    F --> G["OpenTelemetry Collector"]
    G --> H["Metrics Backend"]
~~~

Micrometer giữ các meter trong registry. Khi đến chu kỳ xuất, **OtlpMeterRegistry** tổng hợp số đo theo loại meter và cấu hình phân phối, tạo các metric data point rồi gửi payload OTLP protobuf đến địa chỉ cấu hình. Registry mặc định sử dụng HTTP sender; có thể thay sender bằng implementation khác nếu cần. [Micrometer OTLP](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)

Trong OTLP, metric stream được xác định bởi các thuộc tính ở cấp metric như:

- **Resource**: mô tả nguồn phát sinh, ví dụ service, môi trường và instance.
- **Instrumentation Scope**: mô tả thư viện hoặc phạm vi instrumentation tạo ra metric.
- **Metric name**: tên metric.
- **Data point type**: Sum, Gauge, Histogram, ExponentialHistogram hoặc Summary.
- **Unit**: đơn vị đo.
- **Aggregation temporality** và tính đơn điệu nếu loại điểm dữ liệu có áp dụng.

Mỗi data point còn có tập **Attributes** riêng, tương ứng với các chiều phân loại như route, result hoặc region. Trong Micrometer, tag của meter được chuyển thành attributes của điểm dữ liệu. Resource attributes áp dụng cho nguồn phát, còn meter tags phân biệt các chuỗi dữ liệu trong cùng metric stream.

## 2. Bảng ánh xạ các meter phổ biến

Micrometer OTLP registry hỗ trợ những ánh xạ chính sau:

| Meter Micrometer | OTLP data point | Ý nghĩa dữ liệu |
|---|---|---|
| Counter | Sum, monotonic | Tổng sự kiện tăng dần |
| FunctionCounter | Sum, monotonic | Giá trị tích lũy đọc từ hàm của đối tượng nguồn |
| Gauge | Gauge | Giá trị được lấy mẫu tại một thời điểm |
| TimeGauge | Gauge | Giá trị thời gian được lấy mẫu với đơn vị |
| MultiGauge | Gauge | Nhiều giá trị Gauge được phân biệt bằng attributes |
| Timer | Histogram mặc định; Summary nếu chỉ xuất client-side percentile | Phân phối thời lượng, count và sum |
| DistributionSummary | Histogram mặc định; Summary nếu chỉ xuất client-side percentile | Phân phối các giá trị số, count và sum |
| LongTaskTimer | Histogram hoặc Summary | Thống kê thời lượng của tác vụ dài theo cách registry hỗ trợ |
| FunctionTimer | Histogram với sum và count | Tổng thời lượng và số lần đo lấy từ hàm của đối tượng nguồn |

Với Timer và DistributionSummary, OTLP registry còn có thể xuất **ExponentialHistogram** khi cấu hình histogram flavor phù hợp. Loại histogram thực tế phụ thuộc cấu hình của OtlpMeterRegistry. [Bảng ánh xạ của Micrometer](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)

Cần nhớ rằng **Counter không trở thành một OTLP data point tên Counter**. Trong mô hình OTLP, nó trở thành Sum với cờ monotonic. Tương tự, Timer không được gửi dưới dạng một đối tượng Java Timer; nó được chuyển thành dữ liệu phân phối, thường là Histogram.

## 3. Counter được ánh xạ thành OTLP Sum

Counter của Micrometer biểu diễn số sự kiện tích lũy. Mỗi lần gọi increment làm giá trị tăng; Counter không được dùng để biểu diễn trạng thái có thể tăng rồi giảm.

Trong OTLP, Counter được biểu diễn thành **Sum** với thuộc tính **monotonic=true**. Data point chứa giá trị số, khoảng thời gian tích lũy và tập attributes. Ví dụ:

~~~java
Counter ordersCreated = Counter.builder("orders.created")
    .description("Số đơn hàng được tạo")
    .tag("channel", "web")
    .register(registry);

ordersCreated.increment();
ordersCreated.increment(3);
~~~

Sau các lần ghi, meter có tổng số sự kiện là 4. Khi xuất OTLP, registry biểu diễn số liệu này dưới dạng Sum đơn điệu. Nếu dùng cumulative temporality, giá trị được báo cáo là tổng tích lũy kể từ thời điểm bắt đầu của chuỗi dữ liệu. Nếu dùng delta temporality, giá trị biểu diễn số tăng trong khoảng thời gian vừa kết thúc.

Cumulative Sum có thể được hình dung như sau:

| Lần xuất | Giá trị Counter | Giá trị Sum cumulative |
|---|---:|---:|
| 1 | 4 | 4 |
| 2 | 7 | 7 |
| 3 | 9 | 9 |

Với delta temporality, cùng chuỗi sự kiện có thể được biểu diễn thành các phần tăng thêm giữa hai lần xuất:

| Khoảng xuất | Số sự kiện phát sinh | Giá trị Sum delta |
|---|---:|---:|
| Khoảng 1 | 4 | 4 |
| Khoảng 2 | 3 | 3 |
| Khoảng 3 | 2 | 2 |

Các giá trị trong hai bảng mô tả cùng một tổng số sự kiện nhưng có ngữ nghĩa thời gian khác nhau. Backend cần biết temporality để tính rate, hợp nhất dữ liệu và xử lý reset đúng cách.

## 4. Gauge được ánh xạ thành OTLP Gauge

Gauge biểu diễn giá trị tại thời điểm lấy mẫu. Ví dụ điển hình là số phần tử hiện có trong queue, số kết nối đang mở hoặc mức sử dụng bộ nhớ.

~~~java
Gauge.builder("jobs.queue.size", queue, Queue::size)
    .description("Số job đang chờ xử lý")
    .tag("queue", "priority")
    .register(registry);
~~~

OTLP Gauge chứa giá trị được lấy mẫu và timestamp tương ứng. Nếu nhiều lần thay đổi xảy ra giữa hai chu kỳ xuất, điểm dữ liệu thường đại diện cho giá trị được lấy mẫu gần nhất trong chu kỳ đó. Gauge không có aggregation semantic kiểu cộng dồn như Sum; backend thường dùng giá trị được lấy mẫu gần nhất khi căn chỉnh dữ liệu theo thời gian.

Ví dụ queue thay đổi từ 5 lên 8 rồi xuống 6 trước lần xuất tiếp theo. Gauge có thể công bố giá trị 6 tại lần lấy mẫu. Nó không công bố cả ba thay đổi như một chuỗi sự kiện.

Không cộng Gauge của nhiều instance một cách mặc định. Nếu Gauge biểu diễn queue depth của từng instance, tổng hợp bằng phép cộng có thể có ý nghĩa trong một số bài toán, nhưng cần được cấu hình rõ ở backend. Nếu Gauge biểu diễn nhiệt độ hoặc phần trăm CPU, phép cộng có thể không có ý nghĩa.

## 5. Timer được ánh xạ thành Histogram hoặc Summary

Timer ghi nhận thời lượng của các hoạt động. Một Timer có count, total time và có thể có histogram, percentile, min/max hoặc các thống kê phân phối khác tùy cấu hình.

~~~java
Timer checkoutTimer = Timer.builder("checkout.duration")
    .description("Thời lượng xử lý checkout")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);

checkoutTimer.record(() -> checkoutService.checkout(command));
~~~

Theo cấu hình mặc định của OTLP registry, Timer được xuất thành **Histogram** ngay cả khi không cấu hình percentile histogram riêng. Histogram OTLP gom nhiều lần quan sát thành một điểm dữ liệu có các trường như:

- **count**: tổng số quan sát.
- **sum**: tổng thời lượng của các quan sát.
- **min/max**: các trường tùy chọn; khả năng xuất phụ thuộc temporality và implementation.
- **bucket counts**: số quan sát rơi vào từng khoảng, nếu histogram có bucket.

Với Timer, sum là tổng thời lượng đã đo và được biểu diễn theo đơn vị thời gian của registry. Các bucket giúp backend tính percentile hoặc tỷ lệ request nằm dưới một ngưỡng.

### Khi nào Timer trở thành Summary?

Nếu chỉ cấu hình percentile phía ứng dụng bằng **publishPercentiles(...)**, OTLP registry có thể xuất **Summary** chứa các quantile đã được tính trước. Ví dụ:

~~~java
Timer.builder("checkout.duration")
    .publishPercentiles(0.50, 0.90, 0.99)
    .register(registry);
~~~

Summary chứa các quantile đã tính ở phía ứng dụng. Theo tài liệu OTLP, Summary là kiểu tương thích cũ và không được khuyến nghị cho ứng dụng mới; Summary cũng không có trường min/max như Histogram. Micrometer vì vậy ưu tiên xuất Timer dưới dạng Histogram.

Nếu cấu hình cả publishPercentiles và một trong các tùy chọn histogram như publishPercentileHistogram hoặc serviceLevelObjectives, Histogram được ưu tiên và percentile tính sẵn không được xuất thành Summary riêng. [Chi tiết lựa chọn Histogram/Summary](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)

## 6. DistributionSummary được ánh xạ thành Histogram hoặc Summary

DistributionSummary dùng để đo phân phối của một đại lượng số không phải thời lượng, ví dụ kích thước payload, số bản ghi trong batch hoặc dung lượng dữ liệu đã xử lý.

~~~java
DistributionSummary payloadSize = DistributionSummary
    .builder("message.payload.size")
    .description("Kích thước payload được xử lý")
    .baseUnit("bytes")
    .publishPercentileHistogram()
    .serviceLevelObjectives(1_024, 16_384, 65_536)
    .register(registry);

payloadSize.record(payload.length);
~~~

OTLP registry thường xuất DistributionSummary thành Histogram. Data point chứa count, sum và các bucket count nếu histogram được cấu hình. Với ví dụ trên:

- count cho biết có bao nhiêu payload được ghi nhận.
- sum cho biết tổng kích thước payload đã quan sát.
- bucket count cho biết số payload thuộc từng khoảng kích thước.
- unit là **bytes**, giúp backend và người đọc diễn giải đúng đại lượng.

Nếu chỉ cấu hình client-side percentile bằng publishPercentiles, DistributionSummary có thể được xuất thành Summary. Nếu cấu hình histogram hoặc SLO, Histogram được ưu tiên.

Không dùng cùng một metric name cho hai đại lượng có đơn vị hoặc ý nghĩa khác nhau. Ví dụ, message.payload.size đo byte không nên dùng chung tên với số lượng message. Trong OTLP, data point type và unit là các thuộc tính định danh của metric stream; xung đột type hoặc unit có thể gây semantic error ở backend.

## 7. Histogram thường và ExponentialHistogram

OTLP hỗ trợ hai kiểu histogram chính:

- **Histogram** sử dụng các ranh giới bucket tường minh.
- **ExponentialHistogram** sử dụng bucket theo công thức tăng trưởng lũy thừa, phù hợp với dữ liệu có dynamic range rộng và cần biểu diễn gọn.

Micrometer OTLP registry có thể chọn giữa explicit bucket Histogram và ExponentialHistogram khi bật percentile histogram. Cấu hình **histogramFlavor** hoặc **histogramFlavorPerMeter** quyết định loại được dùng. Với ExponentialHistogram, registry hỗ trợ giới hạn scale và số bucket để kiểm soát độ phân giải cũng như kích thước dữ liệu.

Một số quy tắc quan trọng:

- SLO boundary tùy chỉnh yêu cầu explicit bucket Histogram.
- ExponentialHistogram không hỗ trợ custom SLO boundary theo cách này.
- **maxScale** giới hạn scale tối đa của ExponentialHistogram.
- **maxBuckets** giới hạn số bucket của ExponentialHistogram; có thể ghi đè theo từng meter bằng maxBucketsPerMeter.
- Histogram có trường max chỉ được Micrometer hỗ trợ trong delta aggregation temporality vì max của dữ liệu cumulative sẽ dần ổn định và ít hữu ích khi tích lũy suốt vòng đời ứng dụng.

Ví dụ cấu hình SLO cho Timer:

~~~java
Timer.builder("http.server.request.duration")
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Khi có SLO boundary, registry sử dụng explicit bucket Histogram để giữ đúng các ngưỡng đã khai báo. Nếu không cần ngưỡng SLO tùy chỉnh mà cần histogram có khả năng biểu diễn dải giá trị rộng, ExponentialHistogram có thể là lựa chọn phù hợp.

## 8. Aggregation temporality: cumulative và delta

Aggregation temporality xác định một Sum hoặc Histogram mô tả dữ liệu theo khoảng thời gian như thế nào.

| Temporality | Ý nghĩa | Hình dung |
|---|---|---|
| Cumulative | Giá trị tích lũy từ thời điểm bắt đầu chuỗi | Mỗi lần xuất báo tổng kể từ start time |
| Delta | Giá trị chỉ thuộc khoảng giữa hai lần xuất liên tiếp | Mỗi lần xuất báo phần tăng trong interval vừa qua |

Với cumulative, hai lần xuất liên tiếp có các khoảng dữ liệu chồng lấn vì lần sau chứa cả những quan sát trước đó. Với delta, các khoảng thời gian liên tiếp không chồng lấn; sau khi xuất, bộ tích lũy cho interval kế tiếp được bắt đầu lại.

OpenTelemetry dùng start timestamp và end timestamp để diễn giải các khoảng dữ liệu. Start timestamp giúp nhận biết một chuỗi dữ liệu liên tục và hỗ trợ xử lý restart. Temporality ảnh hưởng đến cách backend tính rate, xử lý khoảng trống và hợp nhất các chuỗi. [OpenTelemetry Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)

Micrometer OTLP registry cho phép chọn **cumulative** hoặc **delta** qua cấu hình aggregationTemporality. Mặc định hiện tại là cumulative. Hãy chọn theo khả năng tiếp nhận của backend và yêu cầu vận hành; không trộn dữ liệu cumulative và delta của cùng metric stream nếu backend không có cơ chế chuyển đổi phù hợp.

## 9. Resource attributes và meter tags

OTLP phân biệt Resource attributes với attributes của từng data point.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Resource attributes | Mô tả service hoặc process phát metrics | service.name, deployment.environment, service.instance.id |
| Meter tags | Phân loại chuỗi dữ liệu của meter | route, method, result, region |
| Instrumentation Scope | Mô tả thư viện/phạm vi tạo metric | Tên và phiên bản instrumentation library |
| Metric metadata | Mô tả đại lượng | Name, description, unit và data point type |

Ví dụ, một Counter có tag result=success và Resource service.name=order-service sẽ được phân biệt với chuỗi result=failure trong cùng service, đồng thời có thể phân biệt với metric cùng tên từ một service khác.

Micrometer OTLP registry mặc định bổ sung một số Resource attributes như telemetry.sdk.name=io.micrometer, telemetry.sdk.language=java, phiên bản Micrometer và service.name=unknown_service. Có thể cấu hình Resource attributes bằng OtlpConfig hoặc các biến môi trường OTEL_RESOURCE_ATTRIBUTES và OTEL_SERVICE_NAME. Biến OTEL_SERVICE_NAME có ưu tiên khi đặt service.name.

Không đưa request ID, user ID, order ID hoặc nội dung exception vào tag. Các giá trị này tạo ra nhiều tổ hợp attributes và làm tăng cardinality. Nếu cần liên kết metrics với một trace cụ thể, hãy cân nhắc **exemplar** thay vì biến trace ID thành tag.

## 10. Cấu hình OTLP registry trong Spring Boot

Thêm dependency registry OTLP vào ứng dụng. Nếu dự án dùng BOM của Micrometer hoặc Spring Boot, không cần khai báo version riêng cho dependency:

~~~gradle
implementation("io.micrometer:micrometer-registry-otlp")
~~~

Ví dụ cấu hình endpoint OTLP HTTP:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        aggregationTemporality: cumulative
        compressionMode: gzip
        resourceAttributes:
          service.name: order-service
          deployment.environment: production
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa | Mặc định theo Micrometer OTLP |
|---|---|---|
| url | Endpoint nhận metrics | localhost:4318/v1/metrics |
| step | Khoảng thời gian publish | 1 phút |
| aggregationTemporality | Cumulative hoặc delta | cumulative |
| compressionMode | Nén payload | none |
| batchSize | Số Meter tối đa trong một payload | 10.000 |
| headers | Header gửi kèm, ví dụ thông tin xác thực | Lấy từ cấu hình hoặc biến môi trường |
| resourceAttributes | Attributes dùng chung cho Resource | Có các giá trị mặc định của Micrometer |

Các biến môi trường như OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE, OTEL_METRIC_EXPORT_INTERVAL và OTEL_RESOURCE_ATTRIBUTES có thể tham gia cấu hình theo quy tắc của OtlpConfig. Tên property và hành vi cụ thể cần đối chiếu với phiên bản Micrometer đang dùng. [Micrometer OTLP configuration](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)

OtlpMeterRegistry mặc định gửi payload OTLP protobuf qua HTTP. Có thể thay HttpSender hoặc cung cấp OtlpMetricsSender riêng. Micrometer hiện không cung cấp sẵn một implementation gRPC cho OtlpMetricsSender; nếu hệ thống yêu cầu sender gRPC, cần tích hợp implementation phù hợp.

## 11. Exemplars liên kết metrics với traces

Exemplar là metadata gắn với một quan sát metrics để tham chiếu đến dữ liệu bên ngoài, thường là trace ID và span ID. Exemplar không phải tag/attribute của chuỗi thời gian nên không tạo thêm một tổ hợp cardinality mới.

Micrometer OTLP hỗ trợ exemplar cho Counter, Timer và DistributionSummary. Để bật, cần cung cấp ExemplarContextProvider cho OtlpMeterRegistry:

~~~java
OtlpConfig config = OtlpConfig.DEFAULT;

ExemplarContextProvider contextProvider =
    new TracingExemplarContextProvider();

OtlpMeterRegistry registry = OtlpMeterRegistry.builder(config)
    .exemplarContextProvider(contextProvider)
    .build();
~~~

Provider chịu trách nhiệm lấy trace context hiện tại và cung cấp traceId, spanId cùng các thuộc tính cần thiết. Nếu không có span hiện hành hoặc span không được lấy mẫu, provider có thể không tạo exemplar. Exemplar giúp người vận hành đi từ biểu đồ metric đến trace của một quan sát cụ thể mà không cần đưa trace ID vào tag. [Micrometer OTLP Exemplars](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)

## 12. Kiểm chứng ánh xạ ở đầu nhận OTLP

Kiểm thử bằng SimpleMeterRegistry chỉ xác nhận logic ghi meter trong bộ nhớ; nó không xác nhận payload OTLP. Khi kiểm tra ánh xạ, cần chạy OtlpMeterRegistry thật hoặc môi trường tích hợp có OpenTelemetry Collector.

Có thể dùng các bước sau:

1. Khởi động Collector hoặc backend nhận OTLP HTTP.
2. Cấu hình endpoint /v1/metrics và Resource attributes rõ ràng.
3. Tạo một Counter, một Gauge, một Timer và một DistributionSummary với tên riêng.
4. Ghi các giá trị mẫu vào từng meter.
5. Chờ ít nhất một chu kỳ publish hoặc kích hoạt publish theo khả năng của registry.
6. Kiểm tra payload hoặc dữ liệu sau Collector để xác nhận data point type, unit, attributes, timestamps và temporality.
7. Bật histogram hoặc SLO cho Timer/DistributionSummary rồi xác minh bucket thực tế.
8. Thử cumulative và delta trong môi trường kiểm thử để bảo đảm backend hiểu đúng khoảng thời gian.

Bảng kiểm tra mong đợi:

| Meter thử nghiệm | Loại OTLP mong đợi | Trường cần kiểm tra |
|---|---|---|
| Counter | Sum, monotonic | value, temporality, start/end timestamp, attributes |
| Gauge | Gauge | sampled value, timestamp, attributes |
| Timer mặc định | Histogram | count, sum, unit thời gian, bucket nếu có |
| Timer chỉ có publishPercentiles | Summary | quantile, count, sum |
| DistributionSummary mặc định | Histogram | count, sum, unit đại lượng, bucket nếu có |
| DistributionSummary có SLO | Histogram explicit bucket | boundary và bucket count |

Không chỉ kiểm tra metric name. Một metric có đúng tên nhưng sai unit, data point type hoặc temporality vẫn có thể bị backend từ chối hoặc diễn giải sai. OpenTelemetry xem data point type, unit và một số thuộc tính nội tại là phần định danh của metric stream. [OpenTelemetry Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ Counter được xuất thành OTLP Gauge | Mất ngữ nghĩa đơn điệu và reset | Dùng ánh xạ Sum monotonic |
| Nghĩ Timer luôn là Summary | Không hiểu dữ liệu histogram và bucket | Kiểm tra cấu hình percentile/histogram |
| Chỉ bật publishPercentiles rồi mong backend tổng hợp nhiều instance | Percentile phía ứng dụng không thể cộng gộp chính xác | Dùng histogram để backend tổng hợp |
| Dùng SLO với ExponentialHistogram | Không có bucket đúng boundary tùy chỉnh | Dùng explicit bucket Histogram |
| Dùng cùng tên metric với unit hoặc type khác nhau | Tạo semantic conflict | Giữ metric name, type và unit nhất quán |
| Trộn cumulative và delta trong cùng chuỗi | Backend tính sai rate hoặc tổng | Chọn temporality phù hợp và giữ nhất quán |
| Đưa trace ID vào tag | Cardinality tăng theo request | Dùng exemplar khi cần liên kết trace |
| Không cấu hình service.name | Khó phân biệt nguồn phát metrics | Đặt Resource attribute hoặc OTEL_SERVICE_NAME |
| Chỉ kiểm tra meter trong SimpleMeterRegistry | Bỏ sót lỗi serialize hoặc exporter | Kiểm thử tích hợp với Collector/backend |

## 14. Checklist triển khai

- [ ] Đã thêm dependency micrometer-registry-otlp và đồng bộ version qua BOM.
- [ ] Đã cấu hình endpoint OTLP HTTP hoặc sender riêng.
- [ ] Đã hiểu Counter được ánh xạ thành Sum monotonic.
- [ ] Đã hiểu Gauge là giá trị được lấy mẫu, không phải tổng tích lũy.
- [ ] Đã xác định Timer/DistributionSummary xuất Histogram hay Summary.
- [ ] Đã chọn explicit Histogram hay ExponentialHistogram theo nhu cầu.
- [ ] Đã cấu hình unit và Resource attributes, đặc biệt service.name.
- [ ] Đã chọn cumulative hoặc delta temporality theo backend.
- [ ] Đã giới hạn cardinality của meter tags.
- [ ] Đã cân nhắc exemplar thay cho trace ID trong tag.
- [ ] Đã kiểm tra payload hoặc dữ liệu tại OTLP Collector/backend.
- [ ] Đã kiểm tra hành vi export theo step và lỗi kết nối trong môi trường kiểm thử.

Micrometer chuyển meter sang OTLP dựa trên ngữ nghĩa của từng loại đo: Counter thành Sum đơn điệu, Gauge thành giá trị lấy mẫu, Timer và DistributionSummary thành Histogram hoặc Summary tùy cấu hình. Resource, attributes, unit và temporality quyết định cách backend nhận diện và diễn giải metric stream. Hãy kiểm chứng payload tại Collector, giữ type và unit nhất quán, chọn temporality có chủ đích và kiểm soát tag để dữ liệu OTLP có thể tổng hợp và truy vấn chính xác.

## Tài liệu tham khảo

- [Micrometer OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)
- [OpenTelemetry Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)
- [OpenTelemetry Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/)

