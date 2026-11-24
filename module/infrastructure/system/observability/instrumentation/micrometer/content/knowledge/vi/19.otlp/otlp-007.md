# Giới hạn tổng hợp khi cấu hình phân vị tính tại ứng dụng

Khi đo độ trễ hoặc phân phối kích thước bằng Micrometer, có thể chọn để ứng dụng tự tính percentile hoặc xuất histogram cho hệ thống nhận tính percentile. Hai cách này không tương đương. Percentile tính tại ứng dụng chỉ mô tả phân phối cục bộ của từng meter ID; backend không thể cộng các giá trị p95 hoặc p99 của nhiều instance hay nhiều nhóm tag để tạo percentile đúng cho toàn dịch vụ.

Với OTLP, khác biệt này còn ảnh hưởng đến kiểu data point được export. Nếu chỉ cấu hình publishPercentiles, OtlpMeterRegistry xuất OTLP Summary chứa các percentile đã tính tại process. Summary là kiểu dữ liệu cũ trong OpenTelemetry Metrics và không được khuyến nghị cho ứng dụng mới. Khi cấu hình histogram hoặc SLO, OTLP registry ưu tiên Histogram hoặc Exponential Histogram để backend có thể tổng hợp bucket trước khi tính percentile.

Bài học này giải thích giới hạn tổng hợp của percentile cục bộ, cách OtlpMeterRegistry ánh xạ cấu hình distribution sang OTLP data point, và cách chọn histogram phù hợp khi cần xem p95/p99 trên toàn cụm.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích percentile tính tại ứng dụng được tính riêng theo meter ID như thế nào.
- Hiểu vì sao không thể lấy trung bình hoặc cộng p95/p99 giữa các instance để có percentile toàn cụm.
- Phân biệt OTLP Summary với Histogram và Exponential Histogram.
- Dự đoán kiểu OTLP data point từ publishPercentiles, publishPercentileHistogram và SLO.
- Chọn histogram khi cần tổng hợp percentile giữa instance hoặc tag dimension.
- Cấu hình OTLP registry và distribution properties trong Spring Boot.
- Kiểm tra data point và truy vấn sau khi metrics đi qua collector.

## Hai cách thu thập percentile trong Micrometer

Timer và DistributionSummary hỗ trợ hai cách phổ biến để quan sát phân phối:

| Cách | Micrometer làm gì? | Backend nhận gì? | Khả năng tổng hợp |
|---|---|---|---|
| Percentile tính tại ứng dụng | Tính xấp xỉ percentile trong process cho từng meter ID | Các giá trị percentile đã tính | Không thể tổng hợp percentile giữa tag hoặc instance |
| Percentile histogram | Tích lũy quan sát vào histogram và xuất các bucket | Count của từng bucket | Có thể tổng hợp bucket rồi tính percentile ở backend |

Một meter ID được xác định bởi tên và tập tag. Vì vậy, percentile tính tại ứng dụng của http.server.requests với route=/orders và route=/checkout là hai kết quả riêng. Tương tự, mỗi process có histogram cục bộ và percentile cục bộ của riêng nó.

~~~mermaid
flowchart TD
    A[Request observations] --> B[Process A]
    A --> C[Process B]
    B --> D[Percentile A p95]
    C --> E[Percentile B p95]
    D --> F[Không thể gộp p95 trực tiếp]
    E --> F
    B --> G[Histogram buckets A]
    C --> H[Histogram buckets B]
    G --> I[Cộng bucket theo ranh giới]
    H --> I
    I --> J[Tính p95 toàn cụm]
~~~

Histogram giữ lại thông tin phân phối dưới dạng các khoảng giá trị. Khi các instance dùng cùng ranh giới bucket và cùng ngữ nghĩa metric, backend có thể cộng số quan sát ở từng bucket rồi ước lượng percentile trên phân phối hợp nhất.

## Vì sao percentile cục bộ không thể tổng hợp?

Percentile là một thống kê thứ hạng, không phải đại lượng cộng được. Giả sử hai instance có số request khác nhau và độ trễ khác nhau:

| Instance | Số request | p95 cục bộ minh họa |
|---|---:|---:|
| A | 10.000 | 120 ms |
| B | 1.000 | 900 ms |

Không thể lấy trung bình 120 ms và 900 ms để kết luận p95 toàn cụm là 510 ms. Cũng không thể lấy max của hai p95 và gọi đó là p95 toàn cụm. Những phép tính này bỏ qua số lượng mẫu và vị trí của từng quan sát trong phân phối.

Để tính percentile toàn cụm, cần đủ thông tin về phân phối của các quan sát từ tất cả instance. Một vài percentile đã tính sẵn không chứa đủ thông tin để khôi phục phân phối gốc. Histogram bucket cung cấp cấu trúc có thể cộng được, dù percentile được tính từ histogram vẫn là giá trị xấp xỉ theo độ rộng bucket.

Giới hạn này cũng áp dụng khi muốn gộp theo chiều tag. Nếu mỗi route có p95 riêng, không thể lấy trung bình các p95 route để có p95 toàn bộ request. Nếu cần truy vấn cả p95 theo route lẫn p95 toàn dịch vụ, hãy xuất histogram và tổng hợp bucket theo từng nhóm mong muốn.

## Cấu hình publishPercentiles có ý nghĩa gì?

Ví dụ tạo timer chỉ xuất p50, p95 và p99 được tính tại ứng dụng:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
    .tag("service", "checkout")
    .publishPercentiles(0.50, 0.95, 0.99)
    .register(registry);
~~~

Micrometer tính các percentile xấp xỉ trong process cho meter ID này. Các giá trị có thể được xuất thành các chuỗi hoặc data point riêng theo registry. Khi process khác có cùng metric và tag, nó cũng tính percentile riêng. Backend có thể hiển thị từng kết quả, nhưng không thể hợp nhất chúng thành percentile chính xác của toàn bộ request.

Percentile cục bộ còn phụ thuộc cấu hình phân phối trong ứng dụng như percentilePrecision, expiry và bufferLength. Precision cao hơn có thể cải thiện độ chính xác của cấu trúc histogram nội bộ nhưng tiêu tốn thêm bộ nhớ. Các thống kê phân phối có cửa sổ thời gian và có thể luân chuyển theo expiry cùng buffer length; vì thế chúng không phải bản lưu đầy đủ mọi quan sát kể từ khi process khởi động.

Percentile cục bộ vẫn có ích khi:

- Chỉ cần quan sát từng instance riêng biệt.
- Backend không hỗ trợ tính percentile từ histogram.
- Muốn chẩn đoán sự khác nhau giữa các process.
- Chấp nhận mỗi chuỗi percentile đại diện cho một meter ID và một process.

Không nên chọn cách này nếu yêu cầu chính là một p95/p99 có thể tổng hợp theo service, region, route hoặc toàn cụm.

## OTLP biểu diễn Timer và DistributionSummary như thế nào?

OTLP Metrics có nhiều loại data point. Với Micrometer OTLP registry, các loại liên quan đến bài học gồm:

| OTLP data point | Meter Micrometer có thể ánh xạ | Ý nghĩa chính |
|---|---|---|
| Summary | Timer, DistributionSummary, LongTaskTimer | Count, sum và percentile đã tính tại ứng dụng khi cấu hình phù hợp |
| Histogram | Timer, DistributionSummary, LongTaskTimer, FunctionTimer | Count, sum và bucket tường minh; FunctionTimer chỉ có sum và count |
| Exponential Histogram | Timer, DistributionSummary | Bucket theo thang số mũ, có thể gộp ở backend |

Với Timer và DistributionSummary, OtlpMeterRegistry ưu tiên Histogram data point. Khi chỉ cấu hình publishPercentiles, registry có thể xuất Summary data point chứa các percentile đã tính trước. OTLP Summary được xem là legacy trong OpenTelemetry Metrics và không được khuyến nghị cho ứng dụng mới; loại data point này cũng không có min/max.

Điều này có nghĩa lựa chọn cấu hình distribution ở Micrometer không chỉ quyết định thống kê nào được tính trong process. Nó còn quyết định loại data point mà OTLP registry gửi đi.

## Ma trận cấu hình percentile và data point OTLP

Với OtlpMeterRegistry hiện hành, có thể đọc ma trận sau:

| Cấu hình meter | Data point OTLP được chọn |
|---|---|
| Không cấu hình percentile hoặc histogram | Histogram |
| Chỉ publishPercentiles | Summary |
| Chỉ publishPercentileHistogram | Histogram hoặc Exponential Histogram |
| Chỉ serviceLevelObjectives | Histogram |
| publishPercentiles cùng publishPercentileHistogram | Histogram hoặc Exponential Histogram |
| publishPercentiles cùng serviceLevelObjectives | Histogram |

Khi publishPercentiles được bật cùng publishPercentileHistogram hoặc serviceLevelObjectives, Histogram được ưu tiên và các percentile tính sẵn không được tạo thêm. Không nên bật cả hai với giả định OTLP sẽ gửi đồng thời Summary và Histogram cho cùng meter.

Kiểu Histogram hay Exponential Histogram được chọn theo histogramFlavor và histogramFlavorPerMeter của OtlpConfig. Nếu dùng Exponential Histogram, cấu hình maxScale giới hạn scale và maxBuckets giới hạn số bucket; maxBucketsPerMeter cho phép đặt giới hạn riêng theo tên meter.

Exponential Histogram không hỗ trợ các SLO boundary tùy chỉnh. Khi cấu hình serviceLevelObjectives, OTLP registry sử dụng explicit bucket Histogram để biểu diễn các ranh giới đó.

## Ví dụ: chỉ dùng percentile tính tại ứng dụng

Ví dụ này yêu cầu p50, p95 và p99 ở phía ứng dụng:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
    .description("Thời gian xử lý HTTP request")
    .tag("route", "/orders/{id}")
    .publishPercentiles(0.50, 0.95, 0.99)
    .register(registry);
~~~

Với OtlpMeterRegistry, cấu hình chỉ có publishPercentiles làm meter được xuất thành OTLP Summary. Các percentile là kết quả cục bộ của meter ID trên process hiện tại. Nếu có 8 replica, backend nhận kết quả cục bộ từ các replica; không có phép toán hợp lệ để gộp tám p95 thành một p95 toàn service.

Summary data point không có min/max. Nếu dashboard cần min/max hoặc backend cần tính percentile từ dữ liệu hợp nhất, hãy chuyển sang cấu hình histogram.

## Ví dụ: xuất histogram để tổng hợp percentile

Khi cần p95/p99 toàn cụm, bật percentile histogram:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
    .description("Thời gian xử lý HTTP request")
    .tag("route", "/orders/{id}")
    .publishPercentileHistogram()
    .register(registry);
~~~

OTLP registry xuất Histogram hoặc Exponential Histogram tùy cấu hình. Backend có thể cộng bucket của các instance có cùng metric và cùng ranh giới, sau đó tính percentile xấp xỉ trên phân phối chung.

Nếu muốn kiểm soát ngưỡng phục vụ SLO, khai báo serviceLevelObjectives:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
    .tag("route", "/orders/{id}")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Khi SLO boundary được cấu hình, registry phải dùng explicit bucket Histogram để giữ các ranh giới tùy chỉnh. Các bucket này giúp trả lời câu hỏi như “bao nhiêu phần trăm request hoàn tất trong 300 ms?” và cũng có thể được tổng hợp giữa các instance.

## Ví dụ: cấu hình OTLP trong Spring Boot

Khi dùng Spring Boot Actuator và Micrometer OTLP registry, có thể cấu hình endpoint và resource attributes trong application.yml:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        step: 30s
        aggregation-temporality: cumulative
        resource-attributes:
          service.name: checkout
          deployment.environment: production
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,1s
~~~

Trong ví dụ, histogram được bật và có các SLO boundary. OTLP registry xuất Histogram; backend hoặc collector có thể tổng hợp bucket để tính percentile trên nhiều instance. Không khai báo percentiles nếu mục tiêu chỉ là percentile tổng hợp từ histogram.

Nếu chỉ cấu hình percentiles mà không bật histogram hoặc SLO, OTLP registry sẽ chọn Summary data point. Ví dụ:

~~~yaml
management:
  metrics:
    distribution:
      percentiles:
        http.server.requests: 0.5,0.95,0.99
~~~

Đây là lựa chọn cho percentile cục bộ. Khi thêm percentiles-histogram hoặc SLO cho cùng meter, OTLP registry ưu tiên Histogram và không tạo các percentile tính sẵn.

Các thuộc tính export khác như step, batch-size, compression, headers và resource-attributes ảnh hưởng đến chu kỳ gửi, kích thước batch, nén, xác thực và nhận diện service. Chúng không làm cho percentile cục bộ trở thành percentile có thể tổng hợp.

## Tính percentile ở backend từ histogram

Khi backend nhận histogram, nó có thể cộng bucket trước khi tính percentile. Với Prometheus hoặc backend cung cấp truy vấn tương đương, logic có dạng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Truy vấn này tính p95 từ bucket đã được tổng hợp giữa các instance. Nếu muốn p95 theo route, giữ thêm label route trong phép tổng hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Tên metric và label trong ví dụ là dạng Prometheus minh họa. Khi dùng OTLP, collector hoặc backend có thể giữ tên OTLP, chuẩn hóa tên hoặc ánh xạ sang tên khác. Hãy kiểm tra metric thực tế ở backend trước khi dùng truy vấn.

Histogram percentile vẫn là ước lượng. Độ chính xác phụ thuộc ranh giới bucket, kiểu histogram, số bucket và phân phối dữ liệu. Bucket quá thưa làm kết quả kém chính xác ở vùng có độ dốc lớn; quá nhiều bucket làm tăng payload, bộ nhớ, số chuỗi và chi phí truy vấn.

## Chọn explicit hay exponential histogram

OtlpMeterRegistry hỗ trợ hai kiểu histogram khi percentile histogram được bật:

| Kiểu | Đặc điểm | Khi cân nhắc |
|---|---|---|
| Explicit bucket Histogram | Dùng ranh giới bucket cụ thể; phù hợp với SLO boundary tùy chỉnh | Khi cần các ngưỡng cố định, dễ diễn giải trong dashboard và alert |
| Exponential Histogram | Bucket theo thang số mũ; hỗ trợ miền giá trị rộng với số bucket được giới hạn | Khi cần phân phối trên dải giá trị rộng và không cần custom SLO boundary |

Với Exponential Histogram, OtlpConfig có các giới hạn như maxScale và maxBuckets; maxBucketsPerMeter có thể đặt số bucket riêng cho từng nhóm meter. Giảm số bucket có thể giảm chi phí nhưng cũng giảm độ phân giải. Hãy chọn dựa trên dải dữ liệu và nhu cầu truy vấn.

Nếu có serviceLevelObjectives tùy chỉnh, registry chọn explicit bucket Histogram vì Exponential Histogram không thể biểu diễn các SLO boundary tùy chỉnh theo cách đó.

## Giới hạn khác cần tính đến

Ngoài việc không thể gộp percentile cục bộ, còn một số giới hạn cần hiểu khi thiết kế:

- **Không khôi phục được phân phối gốc:** vài giá trị p50/p95/p99 không chứa đủ thông tin để dựng lại histogram hoặc tính percentile khác.
- **Không đổi được percentile sau khi export:** nếu chỉ xuất p95, backend không thể suy ra p90 hoặc p99 chính xác từ p95 đó.
- **Không hợp nhất được các chiều tùy ý:** percentile theo route không thể gộp thành percentile toàn service bằng phép average; phải có histogram hoặc dữ liệu quan sát đủ chi tiết.
- **Không so sánh trực tiếp khi cửa sổ khác nhau:** percentile cục bộ phụ thuộc cấu hình expiry/buffer và thời điểm scrape; cần hiểu cửa sổ thống kê của từng process.
- **Tốn tài nguyên ở cả hai phía:** histogram tăng bucket và payload; percentile cục bộ duy trì cấu trúc thống kê trong process và tạo các giá trị export bổ sung.
- **Summary không có min/max:** OTLP Summary data point không mang min/max, nên dashboard cần các giá trị này phải dùng data point phù hợp khác hoặc histogram.
- **Không thể sửa ở Collector bằng phép cộng percentile:** Collector có thể định tuyến, xử lý hoặc chuyển đổi telemetry, nhưng không thể tạo percentile toàn cụm chính xác chỉ từ các percentile cục bộ đã mất phân phối gốc.

## Chiến lược chọn cấu hình

| Yêu cầu vận hành | Cấu hình nên cân nhắc |
|---|---|
| Chỉ xem p95 của từng process | publishPercentiles(0.95) |
| Cần p95 toàn service qua nhiều replica | publishPercentileHistogram() |
| Cần p95 toàn service và các ngưỡng latency cụ thể | Histogram cùng serviceLevelObjectives(...) |
| Backend cần histogram cho miền giá trị rộng | Exponential Histogram với maxScale/maxBuckets phù hợp |
| Chỉ cần count và sum, không cần percentile | Dùng histogram mặc định của OTLP hoặc cấu hình tối giản phù hợp |
| Thư viện dùng chung không nên áp percentile toàn cục | Cấu hình per-meter bằng properties hoặc MeterFilter ở ứng dụng |

Không nên bật client-side percentiles trong thư viện nền tảng chỉ vì một ứng dụng cần p95. Ứng dụng triển khai nên quyết định metric nào cần histogram, SLO hoặc percentile cục bộ theo nhu cầu thực tế. Điều này tránh tăng series và chi phí cho mọi consumer của thư viện.

## Kiểm tra OTLP data point thực tế

Đừng chỉ nhìn cấu hình trong code. Hãy xác minh loại data point mà registry gửi và backend nhận:

1. Kiểm tra dependency và phiên bản micrometer-registry-otlp được resolve cùng phiên bản Micrometer Core.
2. Xác nhận endpoint OTLP, protocol HTTP/gRPC mà sender hỗ trợ và đường dẫn nhận metrics.
3. Kiểm tra resource attributes như service.name, deployment.environment và service.version.
4. Xác nhận cấu hình percentile, histogram và SLO được áp dụng cho đúng tên meter.
5. Quan sát payload hoặc telemetry ở Collector để biết metric đang là Summary, Histogram hay Exponential Histogram.
6. Kiểm tra số bucket và số chuỗi theo từng meter ID.
7. Truy vấn percentile trên backend bằng histogram aggregation; không average các p95 được gửi từ từng instance.

Trong OTLP, OtlpMeterRegistry mặc định gửi metrics bằng HTTP tới URL trong OtlpConfig; endpoint mặc định là localhost:4318/v1/metrics nếu không cấu hình khác. Chu kỳ step mặc định là một phút. Khi triển khai thật, hãy cấu hình endpoint, authentication headers, compression, resource attributes và temporality theo collector/backend.

## Kiểm thử cấu hình ở cấp ứng dụng

Có thể kiểm thử logic meter builder và các thống kê cục bộ bằng SimpleMeterRegistry, nhưng kiểm thử đó không xác nhận OTLP data point. Ví dụ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Timer localTimer = Timer.builder("http.server.requests")
    .publishPercentiles(0.50, 0.95, 0.99)
    .register(registry);

localTimer.record(100, TimeUnit.MILLISECONDS);
localTimer.record(200, TimeUnit.MILLISECONDS);

assertEquals(2, localTimer.count());
assertEquals(300.0, localTimer.totalTime(TimeUnit.MILLISECONDS));

registry.close();
~~~

Để xác nhận OTLP mapping, cần integration test với OtlpMeterRegistry và một sender/receiver thử nghiệm có thể kiểm tra payload protobuf. Test nên xác nhận:

- Chỉ publishPercentiles tạo Summary data point theo phiên bản registry đang dùng.
- publishPercentileHistogram tạo Histogram hoặc Exponential Histogram theo OtlpConfig.
- serviceLevelObjectives tạo explicit bucket Histogram.
- Khi percentile và histogram/SLO cùng bật, registry chọn Histogram và không xuất percentile Summary riêng.
- Resource attributes, temporality và tên metric đúng với cấu hình.

Không suy luận kiểu data point từ kết quả của SimpleMeterRegistry; đó là registry trong bộ nhớ, không phải OTLP exporter.

## Ghi nhớ

- Percentile tính tại ứng dụng được tính riêng cho từng meter ID và không thể gộp giữa instance hoặc tag dimension.
- Không lấy trung bình, cộng hoặc lấy max của các p95 cục bộ để tạo p95 toàn cụm.
- Với OTLP, chỉ publishPercentiles chọn Summary data point; Summary là kiểu legacy và không có min/max.
- Khi bật publishPercentileHistogram hoặc SLO, OTLP registry ưu tiên Histogram/Exponential Histogram và không tạo percentile tính sẵn.
- Histogram bucket có thể được tổng hợp giữa instance trước khi backend tính percentile xấp xỉ.
- Explicit Histogram phù hợp khi cần SLO boundary; Exponential Histogram phù hợp với dải rộng và giới hạn bucket.
- maxScale, maxBuckets và maxBucketsPerMeter giúp kiểm soát chi phí của Exponential Histogram.
- Xác minh data point thực tế qua Collector/backend; cấu hình code không thay thế kiểm thử tích hợp.

Khi mục tiêu là percentile của toàn dịch vụ, hãy giữ thông tin phân phối đủ để backend tổng hợp. Percentile tính tại ứng dụng chỉ nên dùng khi kết quả cục bộ theo từng meter ID là điều bạn thực sự muốn quan sát.

## Tài liệu tham khảo

- [Micrometer OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html) — mapping meter sang OTLP data point, quy tắc chọn Summary/Histogram, cấu hình histogram và Spring Boot.
- [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html) — giới hạn tổng hợp của client-side percentile và cách dùng histogram.
- [OpenTelemetry Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/) — định nghĩa Sum, Gauge, Histogram, Exponential Histogram và Summary data point.
