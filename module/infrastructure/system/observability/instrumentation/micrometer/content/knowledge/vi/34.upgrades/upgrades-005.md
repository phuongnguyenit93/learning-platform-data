# Giữ tương thích dashboard và cảnh báo khi thay đổi phép đo

Metric là một hợp đồng dữ liệu giữa ứng dụng và hệ thống quan sát. Dashboard, PromQL query, recording rule, alert rule và quy trình vận hành đều dựa vào tên metric, loại meter, đơn vị, tag, semantics và cấu hình phân phối. Vì vậy, một thay đổi instrumentation có thể không làm ứng dụng lỗi compile hoặc runtime nhưng vẫn làm dashboard trống, alert không kích hoạt, ngưỡng cảnh báo sai hoặc chuỗi thời gian bị chia thành nhiều nhóm khó so sánh.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, hãy xem mỗi metric được export là một giao diện được tiêu thụ bởi hệ thống bên ngoài. Trước khi đổi phép đo, cần xác định consumer nào đang dùng nó, thay đổi có tương thích không và cần giai đoạn chuyển tiếp nào. Không nên đổi tên, đơn vị hoặc tag chỉ vì code mới trông gọn hơn nếu chưa có kế hoạch cập nhật dashboard và alert.

## 1. Metric schema là hợp đồng vận hành

Một metric contract nên mô tả ít nhất các thành phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Name | Tên metric trong Micrometer và tên sau khi export là gì? | shop.orders.created → tên Prometheus theo convention. |
| Type | Counter, Gauge, Timer hay DistributionSummary? | Counter cho tổng số đơn được tạo. |
| Unit | Giá trị đo bằng giây, byte, item hay đơn vị nào? | Timer export theo giây ở Prometheus. |
| Tags/labels | Có những key nào và mỗi key có tập giá trị nào? | service, route, outcome. |
| Semantics | Giá trị tăng dần, trạng thái hiện tại hay phân phối? | Counter tích lũy; Gauge có thể tăng và giảm. |
| Aggregation | Có thể sum, rate, max hay histogram quantile không? | Rate của counter; p95 từ histogram bucket. |
| Distribution config | Histogram, SLO boundary hoặc percentile nào được xuất? | Bucket tại 100 ms, 300 ms và 1 s. |
| Ownership | Team/service nào chịu trách nhiệm duy trì metric? | Order service team. |
| Consumers | Dashboard, alert, recording rule hoặc SLO nào dùng metric? | Checkout latency dashboard. |

Một metric contract tốt còn ghi rõ ý nghĩa nghiệp vụ và điều kiện cập nhật. Hai metric có cùng tên và type nhưng một metric đếm đơn được tạo, metric kia đếm đơn được chấp nhận sau kiểm tra rủi ro, vẫn không thể thay thế nhau nếu dashboard hoặc alert phụ thuộc ý nghĩa cũ.

## 2. Những thay đổi có thể phá vỡ tương thích

Không phải mọi thay đổi đều có mức rủi ro như nhau. Cần đánh giá tác động đến tên, label set, unit, type và semantics.

| Thay đổi | Rủi ro | Vì sao |
| --- | --- | --- |
| Đổi metric name | Breaking | Query cũ không còn tìm thấy series cũ. |
| Đổi tag key | Breaking | Selector và grouping theo key cũ không còn khớp. |
| Đổi tag value hoặc quy ước value | Có thể breaking | Dashboard có thể lọc theo tập value cũ hoặc phân nhóm sai. |
| Đổi unit nhưng giữ name | Breaking | Threshold và trục dashboard diễn giải sai scale. |
| Đổi Counter thành Gauge hoặc ngược lại | Breaking | Hàm PromQL và ý nghĩa dữ liệu khác nhau. |
| Đổi Timer thành DistributionSummary | Breaking | Exported samples, unit và query histogram có thể thay đổi. |
| Đổi semantics nhưng giữ name/type | Rất nguy hiểm | Query vẫn chạy nhưng trả lời một câu hỏi khác. |
| Thêm tag mới | Có điều kiện | Series identity và grouping thay đổi; cardinality tăng. |
| Bỏ tag | Có điều kiện | Nhiều series có thể gộp hoặc mất khả năng phân biệt. |
| Thay histogram buckets | Có điều kiện | Quantile, SLO calculation và series count có thể thay đổi. |
| Đổi description/help text | Thường ít ảnh hưởng query | Nhưng có thể ảnh hưởng tài liệu và kiểm tra exposition. |

Nguyên tắc an toàn: nếu consumer bên ngoài có thể nhìn thấy sự khác biệt và phải thay query, dashboard, alert hoặc diễn giải số liệu, hãy coi đó là thay đổi contract và lập kế hoạch migration.

## 3. Giữ ổn định metric name và semantics

Tên metric nên phản ánh đại lượng đo, không gắn chi tiết triển khai có thể thay đổi thường xuyên. Hãy dùng namespace và quy ước nhất quán, ví dụ:

- shop.orders.created: tổng số đơn được tạo.
- shop.orders.rejected: tổng số đơn bị từ chối.
- shop.checkout.duration: thời gian xử lý checkout.
- shop.payload.size: phân phối kích thước payload.

Không đổi shop.orders.created thành shop.orders.accepted nếu điểm ghi nhận đã chuyển từ “đã tạo” sang “được chấp nhận”. Đây là hai sự kiện khác nhau. Tạo metric mới giúp dashboard phân biệt được thay đổi nghiệp vụ.

Cũng không dùng một metric name cho hai đại lượng khác đơn vị hoặc semantics ở các phiên bản service khác nhau. Một query có thể vẫn trả về số, nhưng kết quả tổng hợp không còn ý nghĩa.

## 4. Đơn vị là một phần của contract

Đơn vị cần được giữ ổn định và khai báo nhất quán. Với Timer, Micrometer nhận duration cùng TimeUnit và registry chuyển đổi sang base unit của backend. Với Prometheus, duration thường được export theo giây. Với DistributionSummary, đơn vị phụ thuộc đại lượng mà ứng dụng ghi nhận và base unit được cấu hình.

Ví dụ ghi Timer đúng đơn vị:

```java
Timer checkout = Timer.builder("shop.checkout.duration")
        .description("Checkout processing duration")
        .register(registry);

checkout.record(250, TimeUnit.MILLISECONDS);
```

Khi xuất sang Prometheus, giá trị duration được chuẩn hóa theo giây theo convention của registry. Không nhân hoặc chia giá trị lần nữa trong query nếu registry đã chuyển đổi đơn vị.

Đổi từ milliseconds sang seconds nhưng giữ metric name và không cập nhật alert threshold có thể tạo lỗi nghiêm trọng. Ví dụ alert từng dùng 500 ms có thể cần chuyển thành 0,5 s nếu query đọc metric theo giây. Hãy kiểm tra đồng thời code, output exposition, query và threshold.

Với custom Gauge hoặc FunctionCounter, tên và base unit cũng phải mô tả đúng giá trị trả về. Không đặt hậu tố _seconds nếu callback thực tế trả về milliseconds.

## 5. Type và semantics quyết định cách query

| Micrometer type | Semantics thường dùng | Cách query thường gặp |
| --- | --- | --- |
| Counter | Tổng tích lũy chỉ tăng | rate(counter_total[5m]) hoặc increase(counter_total[1h]). |
| Gauge | Giá trị hiện tại có thể tăng/giảm | Đọc trực tiếp, aggregate theo trạng thái phù hợp. |
| Timer | Count và tổng thời gian, có thể kèm histogram | Rate của count; histogram quantile nếu bucket được export. |
| DistributionSummary | Count, tổng giá trị và phân phối đại lượng | Histogram query hoặc tổng/đếm theo use case. |
| LongTaskTimer | Số tác vụ đang chạy và thời lượng của tác vụ còn mở | Dùng cho hoạt động kéo dài đang diễn ra. |

Không đổi một Counter thành Gauge rồi giữ nguyên query rate(...). Gauge không có semantics counter monotonic và rate trên gauge không trả lời câu hỏi “số sự kiện mỗi giây” một cách đáng tin cậy.

Không đổi Timer thành DistributionSummary chỉ để đổi cách hiển thị. Timer có semantics thời gian và base unit riêng; DistributionSummary đo đại lượng số tổng quát.

## 6. Tag key và tag value cũng là schema

Dashboard thường lọc theo tag key, ví dụ service, method, route hoặc outcome. Đổi route thành uri có thể làm query cũ không còn khớp. Đổi value từ success sang SUCCESS cũng có thể làm alert không nhận diện được nhóm cũ.

Hãy quy định rõ:

- Tag key có tên ổn định và ý nghĩa đơn nhất.
- Tag value được chuẩn hóa, viết thường/hoa theo một quy tắc.
- Route dùng URI template, không dùng path chứa ID động.
- Outcome/status có tập giá trị hữu hạn.
- Không đưa trace ID, span ID, request ID, user ID hoặc exception message vào metric tag.
- Thêm/bỏ tag phải đánh giá cardinality và ảnh hưởng đến query grouping.

### 6.1. Thêm tag có thể làm thay đổi query dù selector vẫn chạy

Một query chỉ chọn service="order-service" có thể tiếp tục khớp sau khi thêm tag region. Tuy nhiên, query dùng sum by (service) có thể thay đổi số series đầu vào nhưng vẫn tổng hợp được; query dùng sum by (service, route) sẽ bỏ qua chiều mới; dashboard dùng legend hoặc variable có thể hiển thị khác.

Nguy hiểm hơn là query dùng phép so sánh label chính xác, hoặc alert dựa vào một nhóm label set cụ thể. Vì vậy, thêm tag không tự động là breaking trong mọi trường hợp, nhưng phải kiểm tra các consumer có grouping hoặc alert identity phụ thuộc label set.

### 6.2. Bỏ tag có thể gộp các series

Nếu bỏ tag region, các series trước đây phân biệt theo từng region có thể được gộp trong query tổng hợp. Dashboard mất khả năng phân tích theo vùng; alert grouping cũng có thể giảm số alert instance. Đây là thay đổi thông tin có thể truy vấn, dù metric name không đổi.

## 7. Histogram buckets là một phần của hợp đồng SLO

Với Timer hoặc DistributionSummary, histogram bucket boundaries quyết định backend có thể tính quantile và SLO threshold như thế nào. Nếu dashboard dùng histogram_quantile(0.95, ...), thay đổi bucket configuration có thể làm độ chính xác và kết quả quantile thay đổi.

Ví dụ cấu hình Timer có histogram và SLO boundaries:

```java
Timer.builder("shop.checkout.duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1))
        .register(registry);
```

Trước khi thay bucket:

1. Xác định dashboard đang dùng histogram quantile hay chỉ count/sum.
2. Xác định alert/SLO threshold đang dựa vào bucket boundary nào.
3. So sánh bucket cũ và mới trên cùng một khoảng tải thử nghiệm.
4. Ước lượng số series tăng/giảm.
5. Kiểm tra exporter và backend có giữ đủ bucket cần thiết không.

Không loại bỏ bucket đang được alert sử dụng trước khi thay alert. Nếu bucket mới không còn boundary tại SLO threshold, có thể cần tính lại SLO hoặc giữ boundary tương ứng trong cấu hình mới.

## 8. Ví dụ query và những phụ thuộc cần giữ

Counter request:

```promql
sum by (service) (
  rate(shop_orders_created_total[5m])
)
```

Query trên phụ thuộc vào tên exported metric và semantics Counter. Nếu đổi metric name hoặc type, phải cập nhật query.

P95 latency từ histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(shop_checkout_duration_seconds_bucket[5m])
  )
)
```

Query này phụ thuộc vào:

- Tên histogram bucket metric.
- Label le do Prometheus histogram sử dụng.
- Label service còn tồn tại.
- Timer được export thành histogram bucket.
- Bucket boundaries đủ để ước lượng p95.
- Unit là giây nếu dashboard hiển thị seconds.

Một query đúng cú pháp vẫn có thể sai về mặt vận hành nếu metric đổi unit hoặc semantics. Test cần kiểm tra cả dữ liệu export và ý nghĩa của query.

## 9. Alert rule cần được nâng cấp cùng metric

Alert rule là consumer quan trọng nhất vì thay đổi metric có thể khiến cảnh báo không kích hoạt hoặc kích hoạt liên tục. Ví dụ rule dựa trên error ratio:

```yaml
groups:
  - name: order-service
    rules:
      - alert: OrderCreationErrorRateHigh
        expr: |
          (
            sum(rate(shop_orders_failed_total[5m]))
            /
            sum(rate(shop_orders_created_total[5m]))
          ) > 0.05
          and
          sum(rate(shop_orders_created_total[5m])) > 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Order creation error rate is above 5 percent
```

Nếu đổi tên một trong hai Counter, đổi semantics của failed/created hoặc thay cách phân loại outcome, phải cập nhật rule và kiểm tra lại denominator. Điều kiện thứ hai trong ví dụ chỉ đánh giá tỷ lệ khi có traffic; khi không có traffic, alert tỷ lệ lỗi không phát sinh. Nếu cần cảnh báo riêng cho tình trạng không có dữ liệu hoặc service không scrape được, hãy tạo alert riêng dùng absent() hoặc up thay vì ép denominator về một hằng số làm sai tỷ lệ ở lưu lượng thấp.

Alert cần giữ ổn định:

- Điều kiện và ý nghĩa nghiệp vụ.
- Đơn vị/ngưỡng so sánh.
- Label dùng để group alert.
- for duration và severity.
- Hành vi khi không có dữ liệu.
- Annotation và runbook link.

Không chỉ sửa tên metric trong expr; hãy kiểm tra alert instance labels và routing sau khi thay đổi tag.

## 10. Recording rules và dashboard query là consumer riêng

Recording rule thường lưu kết quả query dưới một metric name mới. Nếu input metric đổi, recording rule có thể ngừng cập nhật và dashboard vẫn hiển thị dữ liệu cũ cho đến khi retention hết.

Ví dụ:

```yaml
groups:
  - name: order-recording
    rules:
      - record: shop:orders_created:rate5m
        expr: sum by (service) (rate(shop_orders_created_total[5m]))
```

Khi đổi metric nguồn, cần cập nhật recording rule trước hoặc cùng thời điểm triển khai metric mới. Kiểm tra rule evaluation error và xác minh series output mới có mặt.

Recording rule có thể cung cấp một lớp tương thích cho query dẫn xuất. Tuy nhiên, không thể tùy tiện tạo lại một Counter thô từ một rate đã tổng hợp: loại dữ liệu và semantics đã khác. Hãy đặt tên recording rule thể hiện rõ đây là rate, ratio, quantile hoặc aggregate.

Dashboard cũng có thể phụ thuộc vào:

- Metric name và label selector.
- Variable query như label_values(...).
- Legend format và panel transformation.
- Unit, axis min/max và threshold.
- Recording rule thay vì metric gốc.
- Annotation hoặc link mở trace/log.

Kiểm tra tất cả panel, variable và alert thay vì chỉ tìm tên metric trong một dashboard.

## 11. Chiến lược migration: dual-publish trong thời gian chuyển tiếp

Khi thay đổi là breaking, một cách an toàn là phát metric cũ và metric mới song song trong một khoảng thời gian. Cả hai được ghi từ cùng một sự kiện nghiệp vụ, nhưng có metric name riêng để consumer có thể chuyển dần.

Ví dụ đổi tên Counter:

```java
@Component
public class OrderMetrics {
    private final Counter createdV1;
    private final Counter acceptedV2;

    public OrderMetrics(MeterRegistry registry) {
        this.createdV1 = Counter.builder("shop.orders.created")
                .register(registry);
        this.acceptedV2 = Counter.builder("shop.orders.accepted")
                .register(registry);
    }

    public void recordAccepted() {
        createdV1.increment();   // Compatibility metric during migration
        acceptedV2.increment();  // New metric contract
    }
}
```

Ví dụ này chỉ đúng nếu mỗi lần gọi vẫn mang ý nghĩa tương thích với metric cũ. Nếu metric mới đo một sự kiện nghiệp vụ khác, không được tăng cả hai từ cùng một điểm gọi chỉ để giữ dashboard; hãy ghi mỗi metric ở đúng event tương ứng.

Trong giai đoạn dual-publish:

1. Xác nhận metric mới có name, type, unit, tag và semantics đúng.
2. Deploy code phát metric mới và metric cũ.
3. Xác minh cả hai xuất hiện trong scrape/export.
4. Cập nhật dashboard, recording rules và alert sang metric mới.
5. So sánh hai metric trên cùng khoảng thời gian và cùng population.
6. Theo dõi consumer còn truy vấn metric cũ.
7. Chỉ bỏ metric cũ sau khi consumer đã chuyển và thời gian deprecation đã hết.

Cảnh báo: không cộng metric cũ và mới trong cùng một query nếu chúng đại diện cho cùng sự kiện. Trong thời gian dual-publish, dashboard phải chọn một phiên bản hoặc so sánh riêng; nếu cộng cả hai, số liệu bị nhân đôi.

## 12. Khi nào dùng recording rule thay cho dual-publish?

Nếu không thể thay code ngay hoặc có nhiều consumer cần thời gian chuyển đổi, recording rule có thể tạo một series dẫn xuất tương thích với dashboard cũ. Ví dụ, dashboard cũ cần một rate đã tổng hợp theo service; recording rule mới có thể giữ tên output cũ trong lúc đọc metric nguồn mới.

Tuy nhiên, recording rule chỉ phù hợp khi biểu thức mới có thể tái tạo đúng semantics cũ. Nó không khôi phục được thông tin đã mất như tag bị xóa, bucket boundary không còn hoặc độ phân giải dữ liệu thấp hơn.

Chọn dual-publish khi:

- Có thể sửa instrumentation và deploy code.
- Cần giữ nguyên dữ liệu raw metric cho consumer cũ.
- Cần so sánh trực tiếp metric cũ và mới.

Chọn recording rule hoặc query compatibility layer khi:

- Thay đổi nằm ở query/aggregation.
- Có thể tái tạo đúng output cũ từ dữ liệu mới.
- Muốn chuyển dashboard mà chưa phải cập nhật tất cả cùng lúc.

Nếu metric mới không chứa đủ thông tin để tạo output cũ, hãy cập nhật consumer thay vì giả lập một series tương thích sai nghĩa.

## 13. Quản lý thời gian deprecation và xóa metric cũ

Không xóa metric cũ ngay khi code mới được deploy. Một quy trình deprecation nên có:

- Chủ sở hữu metric và ngày bắt đầu deprecation.
- Tên metric thay thế và mapping tag/unit.
- Danh sách dashboard, alert, recording rule và service consumer.
- Thời gian chạy song song.
- Điều kiện hoàn tất migration.
- Ngày dự kiến loại bỏ metric cũ.
- Runbook xử lý nếu consumer chưa chuyển.

Có thể phát cảnh báo hoặc log khi metric cũ vẫn được query nếu nền tảng hỗ trợ query audit. Nếu không có query audit, hãy kiểm tra repository dashboard/rule, cấu hình alert và trao đổi với owner các consumer.

Retention của backend có nghĩa series cũ có thể còn tồn tại sau khi ngừng export. Điều đó không đồng nghĩa metric vẫn được cập nhật. Phân biệt dữ liệu lịch sử còn lưu với metric mới đang được scrape.

## 14. Kiểm thử metric contract qua exposition

Test chỉ đọc registry.get(...).counter().count() chưa xác minh tên export, unit, label hoặc bucket. Với Prometheus, hãy kiểm tra nội dung PrometheusMeterRegistry.scrape():

```java
@Test
void exportsTheExpectedMetricContract() {
    try (PrometheusMeterRegistry registry =
                 new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
        Counter.builder("shop.orders.created")
                .tag("channel", "web")
                .register(registry)
                .increment();

        String scrape = registry.scrape();

        assertThat(scrape)
                .contains("# TYPE shop_orders_created_total counter")
                .contains("channel=\"web\"");
    }
}
```

Package Prometheus registry thay đổi giữa các dòng Micrometer; dùng package phù hợp với phiên bản Spring Boot/Micrometer của dự án. Assertion nên tập trung vào các thành phần contract cần giữ, không snapshot toàn bộ exposition nếu thứ tự sample/comment không phải hợp đồng.

Với Timer/histogram, kiểm tra:

- Tên sample sau naming convention.
- Unit và scale.
- Count và sum.
- Bucket cần thiết cho SLO.
- Tag keys/values.
- Không xuất tag động như trace ID hoặc order ID.

## 15. Kiểm thử PromQL và alert rule

Metric exposition test không chứng minh PromQL và alert rule vẫn cho kết quả đúng. Nên có rule test bằng promtool test rules cho các trường hợp:

- Tỷ lệ lỗi vượt ngưỡng.
- Không có traffic.
- Counter reset khi process restart.
- Thiếu series hoặc metric bị drop.
- Tag mới xuất hiện hoặc tag cũ bị bỏ.
- Histogram có bucket boundary mới.
- Alert giữ for duration và grouping đúng.

Ví dụ test rule cần tạo input series với label set đại diện, sau đó xác minh alert được kích hoạt đúng thời điểm. Nếu đổi label key, test sẽ phát hiện selector hoặc grouping không còn khớp.

Đối với dashboard, có thể quản lý dashboard JSON/provisioning trong version control và kiểm tra các query quan trọng bằng test hoặc review có checklist. Nếu dashboard được quản lý thủ công trên UI, cần có bước xác minh sau migration và lưu phiên bản có thể rollback.

## 16. Kiểm tra tương thích khi thêm tag

Thêm tag mới không nhất thiết làm query cũ mất dữ liệu, nhưng có thể tăng cardinality và thay đổi cách grouping. Trước khi thêm, tính số giá trị tối đa và tổ hợp với các tag hiện có.

Ví dụ hiện tại có:

- service: 4 giá trị.
- route: 20 giá trị.
- outcome: 3 giá trị.

Số series tiềm năng tối đa là 4 × 20 × 3 = 240 cho một metric family. Nếu thêm region với 10 giá trị, con số có thể tăng lên 2.400.

Không đưa tag có giá trị gần như duy nhất mỗi request vào metric. Nếu cần chiều chi tiết, hãy dùng log field, span attribute hoặc trace context.

Khi thêm tag, kiểm tra dashboard:

- Có cần thêm variable/filter mới không?
- Legend có quá nhiều series không?
- Query có cần sum by hoặc without thay đổi không?
- Alert grouping có tạo quá nhiều alert instance không?
- Có ảnh hưởng giới hạn cardinality ở registry/backend không?

## 17. Kiểm tra unit và threshold của alert

Một alert threshold phải cùng đơn vị với biểu thức được so sánh. Ví dụ p95 latency trong seconds:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(shop_checkout_duration_seconds_bucket[5m])
  )
) > 0.5
```

Ngưỡng 0.5 ở đây là 0,5 giây. Nếu metric cũ được biểu diễn bằng milliseconds và threshold là 500, đổi sang seconds mà giữ threshold 500 sẽ làm alert gần như không hoạt động đúng.

Khi đổi unit, cập nhật đồng thời:

- Metric description và base unit.
- Dashboard axis/unit.
- Query conversion nếu có.
- Alert threshold.
- SLO calculation và error budget.
- Runbook và tài liệu vận hành.

Không dựa vào hậu tố metric name một mình; xác minh sample thực tế và convention của registry.

## 18. Rollout và rollback

Một migration metrics nên được triển khai như một thay đổi API:

1. **Inventory:** liệt kê metric và consumer đang dùng.
2. **Contract review:** xác định name/type/unit/tag/semantics/buckets mới.
3. **Test:** thêm exposition test và rule test cho schema mới.
4. **Dual-publish:** xuất cũ và mới nếu cần tương thích.
5. **Deploy:** triển khai instrumentation trước hoặc cùng thời điểm consumer migration theo thứ tự đã chọn.
6. **Switch consumers:** chuyển dashboard, recording rules và alerts.
7. **Observe:** so sánh sample, rate, histogram và alert behavior.
8. **Deprecate:** thông báo metric cũ sắp bị loại bỏ.
9. **Remove:** ngừng metric cũ sau khi hết consumer.
10. **Rollback:** giữ khả năng bật lại metric cũ hoặc revert consumer nếu output mới sai.

Nếu consumer được deploy trước producer, query có thể không có dữ liệu trong khoảng chuyển tiếp. Nếu producer bị gỡ metric cũ trước consumer, dashboard/alert cũ có thể hỏng ngay. Hãy chọn thứ tự dựa trên khả năng dual-publish và backward compatibility.

## 19. Bảng triệu chứng sau khi thay đổi metric

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Dashboard trống sau deploy | Metric name hoặc tag key đổi | So sánh raw exposition và query selector. |
| Dashboard hiển thị giá trị lớn/nhỏ bất thường | Unit hoặc scale thay đổi | Kiểm tra sample và threshold conversion. |
| Error rate về 0 hoặc không có dữ liệu | Counter semantics/label outcome đổi | Kiểm tra numerator, denominator và no-data behavior. |
| P95 nhảy đột ngột | Histogram bucket hoặc unit thay đổi | So sánh bucket, count, sum và quantile query. |
| Alert không còn kích hoạt | Selector không khớp hoặc rule chưa cập nhật | Chạy rule test và kiểm tra alert expression. |
| Alert tạo nhiều instance hơn | Tag/grouping mới làm tăng label combinations | Kiểm tra group labels và cardinality. |
| Tổng số request tăng gấp đôi | Query cộng cả metric cũ và mới trong dual-publish | Chọn một metric version trong query. |
| Recording rule không có sample mới | Input metric name/tag đã đổi | Kiểm tra rule evaluation và raw series. |
| Dashboard cũ còn dữ liệu nhưng đứng yên | Backend còn giữ lịch sử sau khi producer ngừng export | Kiểm tra timestamp sample mới nhất. |

## 20. Checklist giữ tương thích dashboard và alert

- [ ] Ghi metric contract gồm name, type, unit, tags, semantics và distribution config.
- [ ] Liệt kê dashboard, alert, recording rule, SLO và consumer liên quan.
- [ ] Đánh giá thay đổi nào là breaking.
- [ ] Giữ tên và semantics ổn định nếu không có nhu cầu thay đổi rõ ràng.
- [ ] Khi đổi name/type/unit/tag, tạo metric version mới hoặc migration tương thích.
- [ ] Dual-publish trong thời gian chuyển tiếp khi cần giữ consumer cũ.
- [ ] Không cộng metric cũ và mới nếu cùng đo một sự kiện.
- [ ] Kiểm tra histogram bucket và SLO boundary trước khi thay.
- [ ] Cập nhật PromQL, dashboard unit/legend/threshold và alert grouping.
- [ ] Chạy exposition test và Prometheus rule test.
- [ ] Theo dõi output mới trước khi xóa metric cũ.
- [ ] Ghi thời gian deprecation và owner chịu trách nhiệm.
- [ ] Có kế hoạch rollback nếu query hoặc alert thay đổi sai.
- [ ] Kiểm soát cardinality và không đưa ID động vào metric labels.

Giữ tương thích dashboard và cảnh báo bắt đầu từ việc xem metric như một contract có người tiêu thụ. Tên, type, unit, tag, semantics và histogram đều có thể ảnh hưởng query hoặc threshold. Với thay đổi breaking, hãy tạo đường chuyển tiếp có thể quan sát: phát metric mới song song, chuyển dashboard và alert, kiểm tra dữ liệu cùng rule behavior, rồi mới ngừng metric cũ. Cách làm này giữ cho số đo vận hành có ý nghĩa xuyên suốt quá trình nâng cấp instrumentation, thay vì chỉ bảo đảm code mới chạy thành công.
