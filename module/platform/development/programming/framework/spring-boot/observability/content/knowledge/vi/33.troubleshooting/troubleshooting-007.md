# Chẩn đoán metric bị trùng trong Spring Boot

Metric bị trùng có thể làm dashboard hiển thị request rate cao gấp đôi, counter tăng nhanh bất thường, histogram ghi nhận nhiều observations hơn thực tế hoặc Prometheus lưu nhiều series tưởng như cùng một tín hiệu. Trong Spring Boot, nguyên nhân không chỉ nằm ở Micrometer instrumentation. Một metric có thể được ghi hai lần trong code, cùng một ứng dụng có thể export qua nhiều registry, hoặc Prometheus có thể scrape cùng endpoint qua nhiều targets.

Bài **Metric bị trùng** thuộc chương **Chẩn đoán sự cố** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể phân biệt duplicate instrumentation với duplicate scraping và duplicate export, đọc labels để xác định series thực sự khác nhau, tìm các cấu hình Micrometer gây ghi trùng, sửa đúng owner của meter và thêm regression tests để tránh tái diễn.

## 1. Metric bị trùng biểu hiện như thế nào?

Các dấu hiệu thường gặp:

- Request rate hoặc throughput cao gần gấp đôi sau khi thêm một starter hoặc dashboard.
- Counter tăng nhanh hơn số operation thực tế.
- Cùng một metric xuất hiện ở nhiều dòng với labels khác nhau.
- Prometheus có nhiều targets trỏ tới cùng một application instance.
- Một dashboard cộng hai series cùng phản ánh một traffic source.
- Meter name giống nhau nhưng registry/exporter khác nhau.
- Timer count khác với số request được ghi ở access log hoặc test.

Không kết luận chỉ từ việc hai dòng có cùng metric name. Trong Prometheus, một time series được xác định bởi metric name và toàn bộ label set. Hai series cùng tên nhưng khác instance, job, pod hoặc service có thể là hai instances hợp lệ. Vấn đề xảy ra khi cùng một sự kiện bị ghi hoặc scrape lặp ngoài ý muốn, hoặc query cộng nhầm các bản sao.

## 2. Phân loại ba nhóm nguyên nhân

| Nhóm | Điều gì bị lặp? | Ví dụ |
| --- | --- | --- |
| Duplicate instrumentation | Một operation cập nhật meter nhiều lần | HTTP server instrumentation và custom filter cùng tăng request counter |
| Duplicate scrape/target | Cùng endpoint được scrape nhiều lần | Hai scrape jobs cùng lấy một Actuator endpoint |
| Duplicate export/registry | Cùng meter được publish qua nhiều đường | Một MeterRegistry được scrape qua hai jobs hoặc hai exporter cùng đẩy dữ liệu vào backend |

Ba nhóm có cách sửa khác nhau. Nếu instrumentation tạo hai increments, cần sửa code/handler. Nếu Prometheus scrape cùng target hai lần, cần sửa service discovery/scrape config. Nếu dashboard cộng hai đường export, cần chọn một nguồn dữ liệu hoặc phân biệt rõ các pipeline.

## 3. Bắt đầu từ raw Prometheus series

Trước tiên, xem đầy đủ label set của metric đang bị nghi ngờ. Ví dụ:

```promql
http_server_requests_seconds_count
```

Trong Prometheus UI, mở từng series và so sánh labels như job, instance, service, pod, uri, method, status và outcome. Hỏi:

1. Hai series có cùng job/instance/pod không?
2. Có hai jobs scrape cùng host:port/path không?
3. Khác biệt chỉ là label do relabeling thêm vào?
4. Một series thuộc application registry, series kia thuộc agent/sidecar?
5. Cùng operation có bị instrument hai lần trong một process?

Xem targets page của Prometheus để kiểm tra scrape URL, job, labels, last scrape và scrape health. Đừng bắt đầu bằng cách xóa label hoặc cộng series trong dashboard trước khi xác định nguồn.

## 4. Phát hiện cùng endpoint được scrape nhiều lần

Nếu một application endpoint xuất hiện dưới nhiều job/target labels, có thể Prometheus đang scrape trùng.

Đếm số targets theo instance:

```promql
count by (instance) (up{job=~".*orders.*"})
```

Tìm những instance có nhiều hơn một target:

```promql
count by (instance) (up) > 1
```

Query trên chỉ là tín hiệu gợi ý; một instance có thể được scrape hợp lệ bởi nhiều jobs cho các endpoints khác nhau. Kiểm tra thêm metrics path, scheme, port và labels của targets.

Đối chiếu số lần scrape và target identity trong Prometheus targets page. Hai jobs scrape cùng endpoint có thể tạo hai chuỗi series khác job label, rồi dashboard sum by service bỏ job label khiến traffic bị cộng đôi.

## 5. Duplicate instrumentation trong Spring Boot

Spring Boot Actuator/Micrometer có thể tự instrument HTTP server requests, JVM, datasource và nhiều integration khác. Nếu thêm custom filter/aspect để đo cùng operation, có thể xuất hiện hai measurements cho một request.

Ví dụ lỗi khái niệm:

```java
// Framework already records http.server.requests.
// A custom filter also increments another request counter
// for exactly the same server request.
class RequestCountingFilter {
    void afterRequest() {
        // requestCounter.increment();
    }
}
```

Nếu custom meter có tên khác, dashboard có thể cộng hai meter như thể chúng là hai nguồn độc lập. Nếu cùng meter name và tags, count có thể tăng hai lần. Xác định owner của từng metric trước khi thêm instrumentation.

Nguyên tắc:

- Dùng framework instrumentation cho HTTP lifecycle chuẩn.
- Dùng custom Observation cho operation nghiệp vụ mà framework chưa đo.
- Không tạo custom counter chỉ để lặp lại server request count có sẵn.
- Đặt tên khác nhau khi hai metrics đo hai semantics khác nhau.

## 6. @Timed và @Observed cùng đo một method

Một lỗi phổ biến là thêm cả @Timed và @Observed vào cùng method với ý định bật cả metrics lẫn tracing. @Observed có thể tạo Observation được metrics handler và tracing handler xử lý; @Timed có thể tạo Timer riêng qua AOP. Tùy setup, một operation có thể ghi hai Timer hoặc tạo các measurements trùng nghĩa.

Ví dụ cần review:

```java
@Service
class OrderService {
    @Timed("orders.process")
    @Observed(name = "orders.process")
    public void process(Order order) {
        // business operation
    }
}
```

Không phải mọi cấu hình đều tạo đúng cùng meter, nhưng đây là trường hợp phải kiểm tra kỹ. Chọn một cơ chế sở hữu instrumentation cho operation. Nếu cần Observation tạo cả metrics và spans, dùng @Observed với handlers phù hợp; nếu chỉ cần duration Timer đơn giản, dùng @Timed.

## 7. Kiểm tra nhiều filters, aspects và interceptors

Một HTTP request có thể đi qua servlet filters, Spring MVC interceptors, AOP aspects và framework instrumentation. Nếu nhiều lớp cùng tạo request timer, cần xem mỗi lớp đo lifecycle nào.

Các điểm cần kiểm tra:

- Filter được đăng ký bằng component và đồng thời đăng ký qua FilterRegistrationBean?
- Một filter được add vào security chain và servlet container?
- Có hai WebMvcConfigurer đăng ký cùng interceptor?
- Annotation AOP và custom aspect cùng intercept method?
- Một method được instrument ở controller và service với cùng name/tags?
- Test configuration và production configuration có cùng bean registration không?

Một operation có thể có parent/child observations hợp lệ ở các tầng khác nhau. Chỉ xem là duplicate khi hai instruments đo cùng boundary/semantics và cùng được cộng như một metric.

## 8. Multiple MeterRegistry và CompositeMeterRegistry

Micrometer có thể dùng nhiều registries: Prometheus, OTLP, StatsD hoặc registry in-memory. CompositeMeterRegistry cho phép một meter được đăng ký tới nhiều child registries. Đây là thiết kế hợp lệ nếu mỗi registry phục vụ một backend.

Nhưng cần tránh:

- Đăng ký cùng registry bean hai lần.
- Tạo custom registry ngoài Spring context rồi lại tạo registry auto-configured.
- Gắn cùng registry vào composite nhiều lần.
- Export cùng một registry tới backend bằng hai scrape jobs.
- Dùng agent instrumentation đồng thời với Micrometer bridge cho cùng signal mà không có ownership rõ.

Nhiều registries không nhất thiết nghĩa là meter được increment nhiều lần trong ứng dụng. Một meter update có thể được fan-out tới nhiều registries; duplicate xuất hiện khi các bản sao được đưa về cùng query/backend rồi cộng như hai nguồn.

## 9. Phân biệt duplicate series với label cardinality

Cardinality cao tạo nhiều series khác nhau, không tự động là duplicate. Ví dụ:

```text
http_server_requests_seconds_count{uri="/orders/1",status="200"}
http_server_requests_seconds_count{uri="/orders/2",status="200"}
```

Hai series trên khác URI và có thể phản ánh hai requests hợp lệ; tuy nhiên raw URI chứa ID tạo cardinality không kiểm soát. Duplicate scrape thường tạo cùng nội dung measurement với labels khác như job/replica; duplicate instrumentation có thể tạo cùng series với count cao bất thường.

Phân biệt:

- **Duplicate:** cùng sự kiện hoặc cùng nguồn được ghi/export nhiều lần.
- **High cardinality:** một metric có quá nhiều label combinations.
- **Legitimate multiplicity:** nhiều instances thực sự nhận traffic riêng.

Không giải quyết duplicate bằng cách xóa labels tùy tiện. Việc đó có thể gộp dữ liệu hợp lệ hoặc che khuất instance-level behavior.

## 10. Đối chiếu với số request thực tế

Chọn một time window có traffic dễ xác định và so sánh:

- HTTP access log count (đảm bảo log không bị sample/drop).
- Micrometer HTTP server request Timer count.
- Prometheus scrape target count.
- Gateway/load balancer request count.
- Application-level business operation count.

Các số liệu này không nhất thiết bằng nhau: gateway có thể đếm retries, access log có thể ghi probe, application metric chỉ ghi request sau khi vào server, business operation có thể được gọi nhiều lần trong một request. So sánh cùng scope và semantics.

Một cách kiểm tra là gửi N requests từ test client tới một instance cô lập, sau đó xác minh Timer count tăng gần N theo đúng instrumentation boundary. Loại health probes, retries và background calls khỏi fixture.

## 11. Truy vấn để khoanh vùng metric bị nhân đôi

So sánh request count theo job:

```promql
sum by (job) (
  increase(http_server_requests_seconds_count[10m])
)
```

So sánh theo job và instance:

```promql
sum by (job, instance) (
  increase(http_server_requests_seconds_count[10m])
)
```

Tìm series cùng labels business nhưng khác scrape job:

```promql
count by (service, instance, uri, method, status) (
  http_server_requests_seconds_count
)
```

Query cuối chỉ cho biết số series còn lại sau khi loại job và một số labels. Nếu kết quả lớn hơn 1, xem lại labels đã bỏ có phải phân biệt hai nguồn scrape hợp lệ hay không; đây không phải bằng chứng chắc chắn có duplicate.

Để kiểm tra counter tăng gấp đôi, dùng một test workload có request volume biết trước và so sánh increase() với số request gửi đi trong cùng khoảng thời gian, lưu ý scrape interval và counter reset.

## 12. Sửa theo đúng nguồn gây trùng

| Nguyên nhân | Hướng sửa |
| --- | --- |
| Custom filter đo trùng HTTP server metric | Bỏ custom counter hoặc đổi thành operation metric khác semantics |
| @Timed và @Observed cùng instrument method | Chọn một instrumentation owner |
| Filter đăng ký hai lần | Giữ một registration path |
| Duplicate Prometheus scrape jobs | Hợp nhất scrape config hoặc loại target trùng |
| Service discovery tạo hai targets cùng endpoint | Sửa relabeling/selector/annotations |
| Cùng registry được gắn vào composite nhiều lần | Sửa bean wiring và registry lifecycle |
| Agent và Micrometer cùng instrument HTTP | Chọn một nguồn hoặc phân biệt signals rõ |
| Dashboard cộng nhiều export pipelines | Chọn một canonical source hoặc filter theo pipeline |

Sau khi sửa, xác minh raw series và target list trước khi thay dashboard queries. Nếu chỉ sửa query để chia đôi count, nguyên nhân gốc vẫn tồn tại và các dashboard khác tiếp tục sai.

## 13. Regression tests cho duplicate metrics

Test nên chứng minh một operation tạo đúng một measurement ở boundary đã chọn:

| Test | Điều cần chứng minh |
| --- | --- |
| Single request test | N requests tạo đúng N HTTP server observations theo scope |
| Filter registration test | Custom filter chỉ được đăng ký một lần |
| AOP test | Một method không bị hai aspects đo trùng |
| Observation handler test | Một operation tạo đúng số Observation mong đợi |
| Meter registry test | Timer/counter count tăng đúng một lần |
| Composite registry test | Meter fan-out đúng child registries, không đăng ký child trùng |
| Prometheus scrape config test | Một endpoint có một canonical target cho job dự kiến |
| Dashboard query test | Query không cộng cùng pipeline hai lần |

Ví dụ test meter count với SimpleMeterRegistry:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class RequestMetricTest {
    @Test
    void incrementsCounterOncePerRecordedOperation() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Counter counter = registry.counter("orders.processed");

        counter.increment();

        assertThat(counter.count()).isEqualTo(1.0);
    }
}
```

Đây là test meter cơ bản, không thay thế integration test cho filter/aspect thực tế. Test hoàn chỉnh cần gọi application boundary, capture meter từ registry được Spring quản lý và xác minh count sau mỗi invocation.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| HTTP request count gần gấp đôi | Framework và custom filter cùng đếm | Kiểm tra filter/interceptor và server instrumentation |
| Series lặp dưới hai job labels | Prometheus scrape cùng endpoint hai lần | Kiểm tra targets page và scrape configs |
| @Observed tạo thêm timer sau khi thêm @Timed | Hai AOP instrumentation cùng method | Capture meter names/count và chọn một owner |
| Chỉ một dashboard bị gấp đôi | Query cộng hai pipeline/export sources | Kiểm tra labels job/agent/registry |
| Count tăng gấp đôi sau khi thêm agent | Agent và Micrometer cùng instrument | Xác định ownership cho HTTP/JDBC/tracing |
| Nhiều series nhưng count từng series bình thường | Cardinality cao hoặc nhiều instances | Kiểm tra labels và route templates |
| Metrics khác access log | Scope gồm probes/retries hoặc log sampling | Đồng bộ scope và semantics |
| Composite registry export hai lần | Child registry được đăng ký lặp | Kiểm tra bean graph và registry lifecycle |
| Timer count lớn nhưng business count thấp | HTTP retries hoặc method được gọi nhiều lần | So sánh server boundary và business operation |
| Query giảm một nửa vẫn sai | Chỉ che biểu hiện ở dashboard | Sửa instrumentation hoặc scrape source gốc |

## 15. Tình huống thực tế: request rate tăng gấp đôi sau khi thêm monitoring agent

**Bối cảnh giả định:** Sau khi triển khai một monitoring agent, dashboard orders-service tăng từ 500 lên gần 1.000 requests/giây. Load balancer và access logs vẫn cho thấy khoảng 500 requests/giây.

Quy trình điều tra:

1. **Kiểm tra raw series:** so sánh job, instance, pod, uri và method; xác định có hai series từ hai pipeline hay count một series tăng gấp đôi.
2. **Kiểm tra targets:** mở Prometheus targets page, tìm hai scrape URLs cùng trỏ vào management endpoint của một pod.
3. **Kiểm tra agent:** xác định agent có tự instrument HTTP server và export cùng metric family hay không.
4. **Kiểm tra application beans:** rà soát custom filters, MeterRegistry beans và Observation handlers vừa được thêm.
5. **Khoanh vùng:** dùng test instance với N requests và capture meter count ở từng registry.
6. **Sửa ownership:** giữ một canonical HTTP instrumentation/export path hoặc tách pipeline bằng labels rõ ràng nếu thực sự cần hai backend.
7. **Xác minh:** target count trở về mong đợi, request rate khớp nguồn traffic và dashboard không cộng duplicate series.

Không kết luận agent là nguyên nhân chỉ vì thời điểm trùng với deployment. Cần chứng minh đường dữ liệu nào đã tạo hoặc scrape bản sao.

## 16. Bài tập tự kiểm tra

**Bài 1.** Hai series cùng metric name có luôn là duplicate không?

*Gợi ý:* Không. Prometheus series identity gồm metric name và toàn bộ labels; hai instances khác nhau có thể là hợp lệ.

**Bài 2.** Duplicate instrumentation khác duplicate scrape thế nào?

*Gợi ý:* Instrumentation ghi measurement nhiều lần trong process; duplicate scrape đọc cùng endpoint qua nhiều targets/jobs.

**Bài 3.** Vì sao thêm @Timed cạnh @Observed cần review?

*Gợi ý:* Cả hai có thể instrument cùng method và tạo duration measurements trùng semantics tùy handlers/aspects.

**Bài 4.** CompositeMeterRegistry có nghĩa meter được increment nhiều lần không?

*Gợi ý:* Không nhất thiết. Một update được fan-out tới child registries; vấn đề phát sinh nếu cùng dữ liệu được gom/export lại và cộng như nhiều nguồn.

**Bài 5.** Làm sao phát hiện cùng endpoint bị scrape hai lần?

*Gợi ý:* So sánh Prometheus targets, scrape URL, job, instance, metrics path và labels.

**Bài 6.** Vì sao không nên chia đôi metric trong dashboard để sửa duplicate?

*Gợi ý:* Nó che nguyên nhân gốc và làm sai khi traffic hoặc số pipeline thay đổi.

**Bài 7.** Nhiều URI labels có phải duplicate metric?

*Gợi ý:* Không nhất thiết; có thể là cardinality cao do raw URI. Dùng route template và kiểm tra từng label set.

**Bài 8.** Test nào chứng minh HTTP instrumentation chỉ ghi một lần?

*Gợi ý:* Gửi số request biết trước tới test instance, capture registry meter count và kiểm tra filter/aspect registration.

## 17. Ghi nhớ

- Metric bị trùng có thể do duplicate instrumentation, duplicate Prometheus scraping hoặc duplicate export/query aggregation; xác định nhóm trước khi sửa.
- Prometheus series được định danh bằng metric name và toàn bộ label set; cùng metric name không đồng nghĩa cùng series.
- Spring Boot Actuator/Micrometer đã cung cấp nhiều instrumentation; custom filter/aspect cần đo operation khác semantics.
- Review cẩn thận @Timed, @Observed, filters, interceptors, agents, registries và Observation handlers để tránh đo cùng boundary hai lần.
- CompositeMeterRegistry fan-out meter updates tới nhiều registries; kiểm tra wiring/export paths trước khi kết luận counter increment bị lặp.
- Dùng raw series, Prometheus targets page và labels job/instance/pod để phân biệt scrape duplication với legitimate instances.
- Không sửa dashboard bằng cách chia đôi count hoặc xóa labels trước khi sửa nguồn tạo dữ liệu trùng.
- Viết regression tests ở application boundary và registry, đồng thời kiểm tra scrape config/dashboard query để ngăn duplicate quay lại.
