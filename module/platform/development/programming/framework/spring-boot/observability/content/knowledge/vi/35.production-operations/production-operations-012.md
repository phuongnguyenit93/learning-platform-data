# Triển khai thay đổi observability theo chiến lược canary

Canary observability change là cách đưa một thay đổi về instrumentation hoặc telemetry vào production theo từng phần nhỏ, quan sát kết quả rồi mới mở rộng. Thay đổi có thể nằm trong mã Spring Boot, cấu hình Micrometer, sampling của tracing, tag của metrics, định dạng log, endpoint exporter hoặc cấu hình collector. Mục tiêu là xác nhận đồng thời hai điều: ứng dụng vẫn đáp ứng SLO và dữ liệu observability vẫn đầy đủ, chính xác, có chi phí chấp nhận được.

Điểm cần chú ý là thay đổi observability tác động trực tiếp đến khả năng đo lường hệ thống. Một bản phát hành có thể không làm request lỗi nhưng lại khiến dashboard mất chuỗi thời gian, trace không còn được gửi, hoặc số lượng time series tăng mạnh. Vì vậy, một canary tốt phải kiểm tra cả hành vi ứng dụng lẫn chất lượng của đường đi telemetry.

## Khi nào nên dùng canary cho thay đổi observability?

Nên triển khai theo canary khi thay đổi có thể ảnh hưởng đến dữ liệu production hoặc chi phí vận hành, chẳng hạn:

- Thêm Observation mới hoặc thay đổi tên, convention và key-value của Observation.
- Thêm, bỏ hoặc đổi tên metric; thay đổi tag chung; bật histogram hoặc đổi bucket.
- Thay đổi tỷ lệ sampling, propagation hoặc cấu hình exporter của distributed tracing.
- Thay đổi cấu trúc log, cách đưa trace ID/span ID vào log hoặc bộ lọc log.
- Chuyển endpoint, giao thức, credential hoặc collector nhận telemetry.
- Nâng cấp thư viện Micrometer, tracing bridge, exporter hoặc agent có thể làm thay đổi định dạng và hành vi phát tín hiệu.

Một thay đổi giao diện hoặc nghiệp vụ cũng có thể dùng canary, nhưng câu hỏi ở đây khác: thay đổi observability có khiến hệ thống được đo khác đi hay khiến tín hiệu không đến được nơi cần đến hay không? Cần tách ảnh hưởng của bản thân ứng dụng khỏi ảnh hưởng của cách đo.

## Xác định điều cần bảo vệ trước khi triển khai

Trước khi phát hành, hãy mô tả thay đổi bằng một giả thuyết có thể kiểm chứng. Ví dụ: “Thêm histogram cho HTTP server request sẽ giúp theo dõi phân vị độ trễ ở Prometheus; số lượng series tăng trong giới hạn đã định và độ trễ xử lý request không tăng đáng kể”.

Ghi lại phạm vi ảnh hưởng:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Metrics | Metric nào được thêm, bỏ hoặc đổi tên? Tag nào thay đổi? Histogram tạo thêm bao nhiêu series dự kiến? |
| Logs | Cấu trúc field có đổi không? Log có còn chứa trace ID và span ID khi có tracing context không? |
| Traces | Sampling rate, propagation, span name, attribute hoặc exporter có đổi không? |
| Export pipeline | Endpoint, protocol, authentication, queue, retry và timeout có thay đổi không? |
| Consumer | Dashboard, alert, recording rule, truy vấn, collector và hệ thống lưu trữ nào phụ thuộc vào schema cũ? |

Chọn trước các chỉ số để quyết định mở rộng hoặc rollback. Nên có ba nhóm:

1. **Sức khỏe ứng dụng:** request rate, error rate, latency p95/p99, saturation của CPU và bộ nhớ, garbage collection, connection pool và các SLO hiện có.
2. **Sức khỏe telemetry:** target scrape có hoạt động không, exporter có lỗi gửi không, queue có đầy không, dữ liệu có bị drop không, độ trễ ingest có tăng không, log và trace có còn đến backend không.
3. **Chất lượng và chi phí dữ liệu:** metric hoặc span dự kiến có xuất hiện không, tag có giá trị hợp lệ không, cardinality và dung lượng ingest có nằm trong ngân sách không.

Đặt ngưỡng theo SLO, baseline và ngân sách thực tế của hệ thống. Không dùng một con số phần trăm chung cho mọi dịch vụ. Với lưu lượng thấp, hãy yêu cầu đủ số request hoặc span để kết quả có ý nghĩa; một canary chạy quá ít traffic không thể chứng minh thay đổi an toàn.

## Thiết kế dữ liệu để so sánh được

Canary chỉ có giá trị khi so sánh được phiên bản mới và phiên bản ổn định dưới điều kiện tương đương. Gắn một định danh release ổn định vào tài nguyên telemetry hoặc metrics nếu backend và chính sách cardinality cho phép. Với metrics, tag phiên bản giúp tách hai nhóm để so sánh; với traces, resource attribute như service version giúp lọc theo phiên bản. Không dùng user ID, order ID, trace ID, URL thô, exception message hoặc giá trị ngẫu nhiên làm low-cardinality metric tag.

Micrometer phân biệt low-cardinality và high-cardinality key-value trong Observation. Low-cardinality key-value phù hợp với giá trị có tập hữu hạn, chẳng hạn provider hoặc outcome. High-cardinality key-value có thể mang thông tin chi tiết cho trace, nhưng vẫn phải tuân thủ quy định dữ liệu nhạy cảm và giới hạn kích thước. Không đưa dữ liệu cá nhân, token, nội dung request hoặc bí mật vào telemetry.

Ví dụ, tên provider nên lấy từ một tập giá trị đã kiểm soát như **visa**, **bank_transfer** hoặc **wallet**. Không dùng tên merchant tùy ý hoặc mã giao dịch làm metric tag. Nếu cần truy vết một giao dịch, hãy dùng cơ chế correlation có kiểm soát và chính sách bảo vệ dữ liệu phù hợp.

Đặc biệt chú ý các thay đổi schema:

- Đổi tên metric có thể làm dashboard và alert cũ không còn dữ liệu.
- Thêm một tag chung có thể tạo lại chuỗi thời gian cho rất nhiều meter. Truy vấn đang nhóm theo tập tag cũ có thể không còn khớp.
- Bật histogram tạo thêm chuỗi cho bucket, count và sum; tác động phụ thuộc số meter, số tag và cấu hình bucket.
- Thay đổi sampling làm thay đổi số trace được lưu. Không so sánh tổng số trace giữa hai phiên bản như thể đó là tổng số request.
- Khi hai phiên bản phát cùng một metric nhưng khác tập tag hoặc bucket, truy vấn tổng hợp cần xử lý rõ sự khác biệt đó.

Nếu consumer cần thời gian chuyển tiếp, duy trì khả năng tương thích trong một khoảng thời gian: cập nhật dashboard và alert để đọc được cả schema cũ lẫn mới, hoặc phát song song metric mới trong thời gian giới hạn. Việc phát song song làm tăng ingest và cardinality, vì vậy phải có thời điểm kết thúc và điều kiện xóa schema cũ.

## Cấu hình Spring Boot làm ví dụ

Ứng dụng Spring Boot có thể expose health probe và Prometheus endpoint để hệ thống vận hành kiểm tra trạng thái ứng dụng và scrape metrics. Ví dụ cấu hình sau minh họa việc bật HTTP request histogram, thêm nhãn phiên bản và đặt tỷ lệ sampling cho tracing:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  metrics:
    tags:
      application: checkout-api
      version: canary-2026-11-22
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

Đây là cấu hình minh họa cho ứng dụng có Actuator, Micrometer registry tương ứng và tracing bridge/exporter đã được cấu hình. Prometheus endpoint chỉ khả dụng khi có registry Prometheus phù hợp trên classpath. Sampling probability chỉ có tác dụng khi tracing được bật và có đường xuất trace. Tên property và khả năng tích hợp cụ thể cần được kiểm tra theo phiên bản Spring Boot đang dùng.

Không nên đưa nguyên cấu hình này vào mọi dịch vụ mà không đánh giá tác động:

- **management.metrics.tags.version** thêm tag phiên bản vào các meter được áp dụng. Điều này hỗ trợ so sánh canary nhưng có thể nhân số series và làm truy vấn hiện tại phải điều chỉnh.
- **percentiles-histogram.http.server.requests** tạo dữ liệu histogram cho HTTP server request. Hãy kiểm tra số bucket và cardinality ở backend trước khi mở rộng.
- **tracing.sampling.probability** điều chỉnh lượng trace được lấy mẫu. Tăng sampling có thể tăng chi phí ingest; giảm sampling có thể làm thiếu dữ liệu cho điều tra lỗi hiếm.
- Chỉ expose endpoint quản trị trên mạng nội bộ hoặc qua cơ chế xác thực và phân quyền phù hợp. Không mở Prometheus hay actuator endpoint nhạy cảm trực tiếp ra Internet.

Nếu thêm Observation tùy chỉnh, hãy đặt tên ổn định và chỉ thêm low-cardinality key-value có tập giá trị hữu hạn:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class PaymentService {
    private final ObservationRegistry observationRegistry;
    private final PaymentGateway gateway;

    public PaymentService(
            ObservationRegistry observationRegistry,
            PaymentGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    public PaymentResult authorize(PaymentCommand command) {
        return Observation.createNotStarted(
                        "payment.authorize",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "payment.provider",
                        command.provider().metricValue())
                .observe(() -> gateway.authorize(command));
    }
}
~~~

Trong ví dụ, **metricValue()** phải trả về một giá trị thuộc tập provider đã kiểm soát. Không thay bằng mã giao dịch hoặc chuỗi do người dùng nhập. Nếu thao tác đã được instrument tự động ở cùng một ranh giới, tránh bọc thêm Observation trùng lặp khiến latency và số operation bị đếm hai lần. Observation chỉ tạo được metrics hoặc trace tương ứng khi registry đã được cấu hình các handler và exporter cần thiết.

## Quy trình rollout canary

### 1. Lập baseline

Thu thập dữ liệu của phiên bản hiện tại trong một khoảng thời gian đại diện. Ghi lại traffic, error rate, latency, tài nguyên, số series, tỷ lệ scrape thành công, exporter failure, log volume và trace volume. Đảm bảo dashboard có thể lọc theo service, môi trường, vùng triển khai và phiên bản.

Kiểm tra trước các truy vấn và alert đang phụ thuộc vào metric hoặc tag sắp thay đổi. Nếu thay đổi tên metric hoặc histogram, chuẩn bị truy vấn tương thích trước khi deploy.

### 2. Đưa thay đổi đến một phần nhỏ

Triển khai canary lên một instance hoặc một phần nhỏ traffic có tính đại diện. Giữ phiên bản cũ hoạt động để có nhóm đối chứng. Nếu có thể, đặt hai nhóm trong cùng vùng và cùng loại hạ tầng để giảm sai lệch do network, tải hoặc cấu hình khác nhau.

Không chọn canary chỉ dựa trên một nhóm người dùng hoặc một route có traffic khác biệt rõ rệt. So sánh cùng endpoint, vùng, thời điểm và loại request. Khi traffic được phân phối không đều, chuẩn hóa theo request count hoặc chia theo cohort trước khi kết luận.

### 3. Xác minh cả ứng dụng và đường đi telemetry

Trước hết xác nhận ứng dụng khởi động, readiness và liveness bình thường. Sau đó kiểm tra:

- Metrics mới xuất hiện đúng tên, đúng tag và có giá trị thay đổi theo traffic.
- Prometheus scrape thành công; target không biến mất và scrape duration không tăng bất thường.
- Histogram có các bucket cần thiết; dashboard và alert trả về kết quả hợp lệ.
- Trace được tạo, propagation qua service boundary hoạt động và exporter gửi được dữ liệu.
- Log vẫn parse được, có correlation ID/trace ID khi có context, và không phát sinh lỗi định dạng.
- Cardinality, queue, retry, drop và ingest cost nằm trong giới hạn.

Một endpoint trả về HTTP 200 chưa chứng minh telemetry đã được lưu thành công. Hãy kiểm tra cả phía ứng dụng, collector và backend nhận dữ liệu.

### 4. So sánh theo cùng điều kiện

So sánh canary và stable trên cùng khoảng thời gian và nhóm traffic. Dùng tỷ lệ thay vì chỉ nhìn tổng số: error/request, request/giây, CPU/request hoặc số span được gửi trên một request đã lấy mẫu. Với latency, dùng histogram có cấu hình tương thích và so sánh cùng endpoint. Nếu bucket khác nhau, không diễn giải hai phân vị như cùng một phép đo.

Khi sampling rate khác nhau, số trace được lưu sẽ khác ngay cả khi hành vi ứng dụng giống nhau. Dùng metrics không lấy mẫu để đánh giá request volume và error rate; dùng trace để kiểm tra cấu trúc span, propagation và khả năng điều tra. Ghi rõ sampling rate của từng phiên bản trên dashboard.

### 5. Mở rộng từng bước

Chỉ tăng tỷ lệ traffic hoặc số instance khi cả ba nhóm kiểm tra — sức khỏe ứng dụng, sức khỏe telemetry và ngân sách dữ liệu — đều đạt ngưỡng đã thống nhất. Có thể đi từ một instance sang một tỷ lệ nhỏ, rồi tăng dần theo từng đợt. Thời gian giữ mỗi đợt phải đủ để quan sát tải đại diện và đủ mẫu; không mở rộng chỉ vì canary vừa khởi động thành công.

Nếu một tín hiệu chưa có đủ dữ liệu, giữ nguyên tỷ lệ canary và chờ thêm hoặc tạo tải kiểm thử an toàn. Không xem “không thấy lỗi” là bằng chứng khi metrics hoặc traces cũng đang bị mất.

### 6. Hoàn tất và dọn schema cũ

Sau khi toàn bộ rollout đạt yêu cầu, theo dõi thêm trong khoảng thời gian phù hợp với chu kỳ traffic. Cập nhật dashboard, alert, runbook và tài liệu để phản ánh schema mới. Chỉ xóa metric, tag hoặc cấu hình cũ sau khi xác nhận không còn consumer phụ thuộc và thời gian tương thích đã kết thúc.

## Tiêu chí dừng và rollback

Rollback hoặc dừng mở rộng khi xuất hiện một trong các tình huống sau:

- Error rate, latency hoặc saturation của canary vượt ngưỡng SLO/baseline đã thống nhất.
- Request thành công nhưng metrics, logs hoặc traces dự kiến không đến backend.
- Exporter liên tục lỗi, queue tăng không giảm, dữ liệu bị drop hoặc ingest delay vượt ngưỡng.
- Cardinality hoặc chi phí tăng vượt ngân sách; tag mới nhận giá trị không giới hạn.
- Dashboard, recording rule hoặc alert quan trọng mất khả năng đọc dữ liệu trong thời gian canary.
- Trace context không được propagation đúng, log mất correlation hoặc span bị tạo trùng.

Khi rollback, đưa traffic về phiên bản ổn định và khôi phục cấu hình instrumentation/exporter đã biết là hoạt động tốt. Kiểm tra lại dữ liệu sau rollback vì việc dừng gửi telemetry có thể để lại khoảng trống lịch sử. Nếu nguyên nhân là schema không tương thích, giữ dashboard và alert ở chế độ đọc cả hai schema cho đến khi quá trình chuyển đổi hoàn tất.

Không nên để lỗi của hệ thống telemetry làm hỏng request nghiệp vụ. Export và gửi dữ liệu cần có timeout, queue, retry và giới hạn phù hợp; tránh tự gọi backend observability đồng bộ trong đường xử lý request. Tuy nhiên, cần theo dõi lỗi export rõ ràng để cơ chế cô lập telemetry không biến thành mất dữ liệu âm thầm.

## Đọc dấu hiệu khi canary có vấn đề

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Dashboard xuất hiện khoảng trống sau deploy | Đổi metric name/tag, endpoint scrape hoặc lỗi exporter | Kiểm tra target, schema mới, truy vấn và log exporter |
| Số series tăng đột biến | Thêm tag chung, tag có nhiều giá trị hoặc bật histogram | Xem series theo metric/tag, loại bỏ dimension không giới hạn và đánh giá bucket |
| Trace ít hơn nhưng request metrics ổn định | Sampling rate thay đổi hoặc exporter drop span | So sánh sampling config, queue, retry và send failure |
| Log không còn liên kết với trace | MDC/correlation context hoặc propagation bị thay đổi | Kiểm tra trace context ở từng service boundary và cấu hình log |
| Latency canary tăng nhưng stable bình thường | Instrumentation tạo overhead, exporter blocking hoặc traffic lệch | So sánh CPU/request, allocation, endpoint và điều kiện traffic |
| Alert báo lỗi dù dịch vụ khỏe | Query chưa hỗ trợ tag/schema mới hoặc thiếu series ở một phiên bản | Kiểm tra biểu thức alert với dữ liệu của cả stable và canary |

## Checklist trước khi mở rộng canary

- [ ] Có baseline và ngưỡng dừng cho ứng dụng, telemetry và chi phí.
- [ ] Có cách phân biệt phiên bản canary với stable bằng dimension có cardinality kiểm soát.
- [ ] Dashboard, alert và recording rule đã xử lý schema cũ và mới.
- [ ] Metrics, logs và traces dự kiến đều xuất hiện ở backend.
- [ ] Sampling rate và cấu hình histogram đã được ghi nhận để so sánh đúng.
- [ ] Không có tag chứa ID hoặc dữ liệu do người dùng kiểm soát với cardinality cao.
- [ ] Exporter không làm chậm hoặc làm lỗi đường xử lý nghiệp vụ.
- [ ] Có thao tác rollback và biết cách xác minh dữ liệu sau rollback.

Một thay đổi observability chỉ nên được coi là hoàn tất khi đã chạy trên toàn bộ phạm vi dự kiến, tín hiệu vẫn đầy đủ và có thể so sánh, các consumer đã tương thích, và chi phí vận hành nằm trong ngân sách.
