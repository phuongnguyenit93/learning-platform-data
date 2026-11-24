# Kiểm tra sau deployment

Một deployment chỉ được xem là ổn định khi phiên bản mới nhận được traffic đúng cách, xử lý các luồng nghiệp vụ quan trọng và tiếp tục phát ra telemetry đủ tin cậy để vận hành. Trạng thái rollout thành công hoặc endpoint health trả về `UP` là tín hiệu cần thiết, nhưng chưa chứng minh rằng người dùng không gặp lỗi, độ trễ không tăng hay các dịch vụ phụ thuộc vẫn hoạt động tốt.

Trong Spring Boot, việc kiểm tra sau deployment kết hợp Spring Boot Actuator, Micrometer Observation, metrics, logs và distributed tracing. Quy trình cần trả lời được bốn câu hỏi: phiên bản nào đang chạy; ứng dụng có sẵn sàng phục vụ không; chất lượng request và tài nguyên có thay đổi không; và khi có bất thường, nhóm vận hành có lần theo được nguyên nhân qua các tín hiệu hay không.

## Mục tiêu và phạm vi kiểm tra

Sau bài học, bạn có thể:

- Lập baseline trước khi phát hành và xác định tiêu chí chấp nhận dựa trên SLO của dịch vụ.
- Kiểm tra rollout, liveness, readiness và các luồng nghiệp vụ quan trọng sau khi traffic chuyển sang phiên bản mới.
- Đọc metrics để phát hiện thay đổi về lưu lượng, tỷ lệ lỗi, độ trễ và mức sử dụng tài nguyên.
- Dùng logs và traces để xác minh khả năng tương quan request xuyên suốt các thành phần.
- Quyết định tiếp tục rollout, tạm dừng hay rollback dựa trên bằng chứng quan sát được.

Phạm vi ở đây là kiểm tra ứng dụng Spring Boot sau khi triển khai lên môi trường chạy thực tế. Các lệnh minh họa giả định ứng dụng đã có Spring Boot Actuator và các endpoint cần thiết được cấu hình. Tên metric và nhãn có thể thay đổi theo phiên bản Spring Boot, loại ứng dụng MVC/WebFlux, registry và instrumentation đang dùng.

## Chuẩn bị trước khi phát hành

Kiểm tra sau deployment sẽ khó kết luận nếu không biết trạng thái bình thường trước đó. Trước khi bắt đầu rollout, hãy ghi lại:

1. **Danh tính bản phát hành:** service name, môi trường, version hoặc commit, image digest, thời điểm phát hành, deployment ID và nhóm thay đổi chính.
2. **Phạm vi thay đổi:** cấu hình mới, feature flag, migration dữ liệu, dependency được nâng cấp và các endpoint hoặc luồng nghiệp vụ bị ảnh hưởng.
3. **Baseline vận hành:** request rate, tỷ lệ lỗi, p95/p99 latency, CPU, heap, GC, thread pool, connection pool và các metric nghiệp vụ quan trọng trong một khoảng thời gian đại diện.
4. **Tiêu chí quyết định:** SLO, error budget, ngưỡng cảnh báo hiện hành, điều kiện dừng rollout và cách rollback đã được kiểm tra.
5. **Khả năng quan sát:** xác nhận metrics, logs và traces đang được thu thập trước deployment; kiểm tra dashboard và alert có thể phân biệt phiên bản mới với phiên bản cũ.

Baseline nên lấy từ cùng dịch vụ, cùng môi trường và khoảng thời gian có đặc điểm traffic tương tự. Khi traffic tăng hoặc giảm mạnh, hãy so sánh tỷ lệ và phân vị thay vì chỉ so sánh tổng số request. Với canary, luôn so sánh nhóm instance mới với nhóm stable trong cùng khoảng thời gian và dưới điều kiện tải tương đương.

## Quy trình kiểm tra sau deployment

### 1. Xác nhận rollout và danh tính phiên bản

Trước hết, xác nhận nền tảng triển khai đã đưa đúng image và cấu hình lên đúng môi trường. Kiểm tra số replica mong đợi, số instance đang chạy, trạng thái restart, crash loop, lỗi pull image, lỗi mount secret/config và trạng thái rollout. Với rolling update hoặc canary, cần biết chính xác instance nào đang chạy phiên bản mới và tỷ lệ traffic đang được gửi tới chúng.

Ở phía ứng dụng, hãy xác minh version hoặc build metadata qua dashboard, log khởi động hay endpoint thông tin đã được bảo vệ. Không nên suy ra phiên bản chỉ từ tên pod hoặc thời điểm deploy. Nếu ứng dụng cung cấp build information qua Actuator, endpoint `info` phải được cấu hình và bảo vệ phù hợp; endpoint này không mặc nhiên được bật để công khai mọi thông tin build.

Các dấu hiệu cần điều tra ngay gồm instance liên tục restart, số replica ready thấp hơn mong đợi, instance chạy sai image, thiếu cấu hình, migration thất bại hoặc log khởi động báo lỗi kết nối dependency. Một instance chưa sẵn sàng có thể chưa nhận traffic, vì vậy dashboard tổng hợp toàn dịch vụ đôi khi che khuất lỗi chỉ xuất hiện trên phiên bản mới.

### 2. Kiểm tra health, liveness và readiness

Spring Boot Actuator cung cấp health endpoint để đánh giá tình trạng ứng dụng. Khi health probes được bật, hai nhóm probe có ý nghĩa khác nhau:

- **Liveness** cho biết tiến trình còn hoạt động đủ tốt để tiếp tục chạy hay cần được khởi động lại. Liveness thường nên phản ánh tình trạng bên trong tiến trình.
- **Readiness** cho biết instance đã sẵn sàng nhận request hay chưa. Readiness có thể xét những dependency thiết yếu đối với khả năng phục vụ request.

Ví dụ cấu hình tối thiểu cho một ứng dụng cần công khai health và probe qua HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
```

Trong môi trường Kubernetes, Spring Boot có thể tự cấu hình health probes theo môi trường chạy. Nếu môi trường không tự kích hoạt, có thể bật rõ ràng bằng `management.endpoint.health.probes.enabled=true`. Việc truy cập HTTP còn phụ thuộc cấu hình security và management port của ứng dụng.

Kiểm tra các endpoint tương ứng, điều chỉnh host, port và thông tin xác thực theo môi trường:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Kết quả mong đợi là HTTP status phù hợp và health status `UP` cho các nhóm cần thiết. Endpoint hoặc nhóm probe có thể không tồn tại nếu chưa bật, chưa expose hoặc bị security chặn; khi đó cần kiểm tra cấu hình và quyền truy cập trước khi kết luận ứng dụng lỗi.

Không đưa mọi dependency bên ngoài vào liveness. Ví dụ, nếu database tạm thời mất kết nối mà liveness cũng chuyển sang `DOWN`, nền tảng có thể liên tục restart instance trong khi restart không thể khôi phục database. Điều này làm sự cố nặng hơn. Readiness có thể kiểm tra dependency thực sự cần cho request, nhưng cần cân nhắc dependency dùng theo kiểu tùy chọn, circuit breaker và khả năng phục vụ một phần.

Health `UP` cũng không thay thế smoke test. Nó xác nhận các health indicator đã cấu hình đang đạt điều kiện, nhưng không bảo đảm một API cụ thể trả dữ liệu đúng hoặc giao dịch nghiệp vụ hoàn tất.

### 3. Chạy smoke test trên luồng quan trọng

Sau khi instance ready và traffic đã được chuyển, thực hiện một tập kiểm tra nhỏ, có kiểm soát trên các luồng quan trọng. Ưu tiên các thao tác đại diện cho đường đi của request: xác thực, đọc dữ liệu, tạo hoặc cập nhật một đối tượng thử nghiệm, gọi dependency quan trọng và xử lý thông điệp nếu ứng dụng có message broker.

Smoke test cần xác minh cả:

- HTTP status và response schema đúng như hợp đồng API.
- Dữ liệu trả về đúng, không chỉ là request thành công.
- Side effect xảy ra đúng một lần và không tạo dữ liệu thử nghiệm không kiểm soát.
- Thời gian phản hồi nằm trong giới hạn của luồng nghiệp vụ.
- Request đi qua đúng phiên bản và tạo được logs, metrics, traces như dự kiến.

Ví dụ đo status và tổng thời gian của một URL smoke test đã được chuẩn bị sẵn:

```bash
curl --fail --silent --show-error \
  --output /dev/null \
  --write-out 'status=%{http_code} total=%{time_total}s\n' \
  "$SMOKE_URL"
```

`SMOKE_URL` cần trỏ tới endpoint phù hợp với ứng dụng. Với endpoint cần xác thực, hãy truyền credential qua cơ chế secret của môi trường; không ghi token hoặc mật khẩu trực tiếp vào script, log hay lịch sử shell. Không chạy thao tác ghi dữ liệu trên production nếu chưa có dữ liệu thử nghiệm và quy tắc dọn dẹp an toàn.

Smoke test nên chạy trên đường traffic thực tế hoặc qua ingress/gateway tương ứng, vì gọi trực tiếp localhost chỉ xác minh instance và bỏ qua DNS, load balancer, TLS, routing hay policy ở lớp ngoài.

### 4. Đọc metrics theo bốn nhóm tín hiệu

Sau smoke test, quan sát metrics trong suốt quá trình rollout và một khoảng thời gian đủ đại diện sau khi hoàn tất. Bốn nhóm tín hiệu thường dùng là traffic, errors, latency và saturation.

| Nhóm | Cần quan sát | Dấu hiệu bất thường sau deployment |
|---|---|---|
| Traffic | Số request, throughput, số message hoặc job được xử lý | Traffic về 0, request lệch giữa instance, consumer không nhận message |
| Errors | HTTP 4xx/5xx, exception, timeout, retry, message thất bại | Tỷ lệ lỗi tăng, lỗi tập trung ở version mới hoặc một dependency |
| Latency | p50, p95, p99 và thời gian xử lý dependency | p95/p99 tăng dù trung bình ít thay đổi; một endpoint chậm rõ rệt |
| Saturation | CPU, heap, GC, thread pool, connection pool, queue depth | Pool cạn, queue tăng, thread chờ lâu, GC kéo dài, CPU hoặc memory tiến sát giới hạn |

Với Spring MVC hoặc WebFlux có instrumentation tương ứng, metric timer `http.server.requests` thường được dùng để quan sát request HTTP. Có thể xem metric qua Actuator nếu endpoint `metrics` đã được expose:

```bash
curl -fsS \
  'http://localhost:8080/actuator/metrics/http.server.requests'

curl -fsS \
  'http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET&tag=status:200'
```

Endpoint metrics trả về các phép đo có sẵn cho meter và các tag tương ứng. Nó không tự động cung cấp mọi percentile. Muốn tính p95/p99 ở hệ thống metrics, cần cấu hình histogram hoặc percentile phù hợp và bảo đảm registry hỗ trợ cách truy vấn đó.

Nếu dùng Prometheus registry, endpoint `/actuator/prometheus` có thể xuất timer HTTP thành các series như `http_server_requests_seconds_count` và `http_server_requests_seconds_sum`; series `_bucket` xuất hiện khi histogram được bật. Ví dụ truy vấn PromQL sau chỉ có ý nghĩa khi metric và histogram tương ứng đã được xuất:

```promql
# Tỷ lệ request HTTP 5xx trên tổng request trong 5 phút
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)

# p95 latency từ histogram
histogram_quantile(
  0.95,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
```

Khi đọc kết quả, hãy phân tách theo service, environment, version và endpoint template nếu hệ thống có các nhãn đó. So sánh tỷ lệ lỗi và latency của phiên bản mới với baseline hoặc nhóm stable. Đừng chỉ nhìn giá trị trung bình: một số ít request rất chậm có thể bị che khuất trong average nhưng vẫn làm p95/p99 vượt SLO.

Kiểm tra thêm metric của JVM và dependency, tùy instrumentation đang bật. Các meter thường gặp gồm `jvm.memory.used`, `jvm.gc.pause`, `jvm.threads.live`, `process.cpu.usage`, `system.cpu.usage` và metric connection pool của datasource. Hãy xem cả mức sử dụng lẫn giới hạn hoặc trạng thái chờ: số connection đang dùng cao chỉ trở thành vấn đề rõ ràng khi đối chiếu với max pool, pending request và latency truy vấn.

Nếu dịch vụ có metric nghiệp vụ, ví dụ số đơn được tạo, số thanh toán thành công hoặc số message hoàn tất, hãy kiểm tra chúng cùng với metric kỹ thuật. Một API có thể trả HTTP 200 nhưng nghiệp vụ không tạo được kết quả mong đợi.

**Lưu ý về cardinality:** Không thêm user ID, order ID, email, request ID hoặc giá trị tự do vào tag của metric. Các giá trị thay đổi liên tục có thể tạo ra số lượng time series rất lớn, làm tăng chi phí lưu trữ và khiến hệ thống metrics quá tải. Dùng metric tag có tập giá trị nhỏ, ổn định; đặt định danh chi tiết trong logs hoặc traces khi cần điều tra và khi chính sách dữ liệu cho phép.

### 5. Xác minh logs và khả năng tương quan

Logs sau deployment giúp phát hiện lỗi khởi động, cấu hình không hợp lệ, dependency timeout, retry bất thường, lỗi migration và exception chỉ xuất hiện dưới traffic thực. Tìm log theo service, environment, version, deployment ID và khoảng thời gian rollout. So sánh tần suất lỗi với baseline, đồng thời kiểm tra xem lỗi có tập trung ở một instance hay một phiên bản hay không.

Một log có cấu trúc nên mang đủ ngữ cảnh để lọc và nối với trace. Ví dụ minh họa:

```json
{
  "timestamp": "2026-11-22T07:30:15.421Z",
  "level": "ERROR",
  "service.name": "order-service",
  "service.version": "2.8.1",
  "deployment.id": "deploy-20261122-01",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "message": "Database call timed out"
}
```

Tên field thực tế phụ thuộc logging encoder và cấu hình MDC. Khi Micrometer Tracing được cấu hình, trace ID và span ID có thể được đưa vào MDC để log pattern hoặc JSON encoder xuất ra. Hãy xác minh chúng thật sự xuất hiện trong log của request đã smoke test; chỉ bật tracing dependency mà không kiểm tra log format và pipeline chưa đủ để kết luận correlation hoạt động.

Kiểm tra log ở cả ba thời điểm: startup, lúc bắt đầu nhận traffic và sau khi xử lý các luồng smoke test. Một số lỗi chỉ xuất hiện khi code path được gọi lần đầu hoặc khi connection pool bắt đầu chịu tải. Không tăng log level toàn hệ thống một cách tùy tiện trong lúc điều tra; điều đó có thể làm tăng chi phí, lộ dữ liệu nhạy cảm hoặc ảnh hưởng hiệu năng. Tuyệt đối không ghi access token, password, secret hay dữ liệu cá nhân không cần thiết.

### 6. Xác minh distributed tracing và telemetry pipeline

Chọn một request smoke test có trace được lấy mẫu và mở trace trong backend. Kiểm tra:

- Trace có gắn đúng service và version của bản phát hành mới.
- Span ở gateway, Spring Boot application và dependency xuất hiện theo thứ tự hợp lý.
- Parent-child relationship và thời lượng từng span phản ánh đúng đường đi request.
- Span lỗi có status hoặc exception phù hợp; các khoảng trống bất thường không bị hiểu nhầm là dependency nhanh.
- Trace ID trong log có thể mở đúng trace trong hệ thống tracing.

Với request đi qua nhiều service, kiểm tra context propagation tại ranh giới HTTP hoặc messaging. W3C Trace Context thường dùng header `traceparent`; hệ thống có thể cấu hình propagation format khác như B3. Nếu trace bị tách thành nhiều trace độc lập sau deployment, hãy kiểm tra cấu hình propagator, client instrumentation, message header và cách tạo Observation ở các service liên quan.

Sampling có thể khiến không phải request nào cũng xuất hiện trong trace backend. Vì vậy, hãy dùng request đã biết được lấy mẫu hoặc tạo traffic kiểm thử có kiểm soát theo sampling policy. Không kết luận tracing hỏng chỉ vì một request ngẫu nhiên không có trace; đồng thời cũng không kết luận pipeline tốt chỉ vì thấy một trace cũ. Xác minh trace mới được tạo sau thời điểm deployment và đến được backend.

Kiểm tra cả đường truyền telemetry: exporter có gửi được dữ liệu, collector có nhận và chuyển tiếp, backend có ingest dữ liệu mới, và credentials/TLS/network policy có còn hợp lệ sau khi đổi cấu hình. Nếu metrics tại ứng dụng tăng nhưng dashboard không cập nhật, cần phân biệt lỗi instrumentation với lỗi scrape/export/collector/backend. Quan sát các log exporter và metric sức khỏe của collector nếu có.

### 7. Theo dõi canary và quyết định rollout

Trong canary hoặc rolling deployment, quan sát theo từng version hoặc nhóm instance. Không mở rộng rollout chỉ vì một vài request đầu tiên thành công. Cần có đủ traffic và thời gian để kiểm tra các luồng quan trọng, các dependency và hành vi dưới tải đại diện.

Có thể dùng bảng quyết định sau làm runbook ban đầu:

| Quan sát | Hành động phù hợp |
|---|---|
| Readiness ổn định, smoke test đạt, error rate và latency nằm trong SLO, saturation bình thường | Tiếp tục rollout theo từng bước đã định |
| Chỉ số dao động nhẹ nhưng chưa vượt tiêu chí, dữ liệu chưa đủ để kết luận | Giữ nguyên tỷ lệ canary, thu thập thêm dữ liệu và kiểm tra log/trace |
| 5xx, timeout hoặc p95/p99 xấu đi rõ rệt ở version mới | Tạm dừng rollout, khoanh vùng endpoint/dependency và đánh giá rollback |
| Readiness thất bại, instance restart liên tục, dữ liệu sai hoặc luồng nghiệp vụ bị hỏng | Dừng rollout; thực hiện rollback hoặc biện pháp khôi phục đã được phê duyệt |
| Metrics/logs/traces không đến backend sau deployment | Dừng việc xác nhận phát hành; khôi phục pipeline telemetry hoặc dùng kiểm tra thay thế đã được định nghĩa |

Quyết định cuối cùng phải theo SLO, error budget, mức độ ảnh hưởng và quy trình incident của tổ chức. Không có một ngưỡng phần trăm lỗi hoặc số giây latency phù hợp cho mọi dịch vụ. Khi rollback, tiếp tục theo dõi vì rollback code không tự động đảo ngược migration dữ liệu, message đã phát, cache đã thay đổi hay side effect đã xảy ra. Cần xác minh tương thích ngược và kế hoạch khôi phục dữ liệu riêng.

## Ví dụ điều tra: API chậm sau deployment

Giả sử phiên bản mới đã rollout thành công và `/actuator/health` trả `UP`, nhưng dashboard cho thấy p95 latency của `GET /api/orders` tăng mạnh.

1. Phân tách metric theo version và endpoint template. Nếu p95 chỉ tăng ở version mới, sự cố có liên hệ với bản phát hành và cần giữ rollout ở tỷ lệ hiện tại.
2. Kiểm tra error rate, timeout và saturation. Nếu số connection đang dùng tiến gần giới hạn, pending connection tăng và request latency tăng cùng thời điểm, datasource pool là một hướng điều tra hợp lý.
3. Mở một trace chậm mới của endpoint. Nếu span gọi database chiếm phần lớn thời gian, kiểm tra query, lock, index, số lần gọi database và thời gian chờ lấy connection.
4. Tìm log theo trace ID và deployment ID. Đối chiếu timeout, retry hoặc exception với span tương ứng để xác định request bị chậm ở bước nào.
5. Tạm dừng rollout. Nếu chỉ số tiếp tục vượt SLO và không thể khắc phục an toàn trong thời gian cho phép, thực hiện rollback theo runbook; sau đó xác minh readiness, latency và error rate đã trở lại baseline.

Ví dụ này cho thấy health `UP` và rollout xanh vẫn có thể đi cùng một regression về hiệu năng. Metrics chỉ ra phạm vi và xu hướng; traces định vị đoạn xử lý chậm; logs cung cấp chi tiết lỗi và ngữ cảnh. Kết hợp cả ba giúp quyết định dựa trên bằng chứng.

## Checklist hoàn tất sau deployment

Trước khi đánh dấu deployment ổn định, hãy xác nhận các mục sau:

- [ ] Đúng service, version, image và cấu hình đang chạy; số instance/replica đạt yêu cầu.
- [ ] Không có restart loop, lỗi khởi động hoặc lỗi migration chưa xử lý.
- [ ] Liveness và readiness hoạt động đúng; instance chỉ nhận traffic khi đã sẵn sàng.
- [ ] Smoke test qua đường truy cập thực tế đạt status, dữ liệu và thời gian phản hồi mong đợi.
- [ ] Traffic, error rate, p95/p99 latency và saturation nằm trong tiêu chí SLO/baseline.
- [ ] Metric nghiệp vụ quan trọng phản ánh kết quả đúng.
- [ ] Logs mới có version/deployment context và có thể tương quan với trace khi tracing được bật.
- [ ] Trace mới đi qua các service/dependency quan trọng và đến được tracing backend.
- [ ] Metrics, logs và traces tiếp tục được ingest sau deployment; dashboard và alert hoạt động.
- [ ] Quyết định tiếp tục rollout hoặc rollback được ghi lại cùng thời điểm, bằng chứng và người chịu trách nhiệm.

Một deployment có thể được xác nhận ổn định khi các kiểm tra trên đạt trong khoảng quan sát đã định và không còn dấu hiệu regression vượt tiêu chí vận hành. Hãy lưu lại version, thời điểm, baseline, kết quả smoke test, dashboard liên quan và mọi ngoại lệ để lần phát hành sau có dữ liệu đối chiếu.
