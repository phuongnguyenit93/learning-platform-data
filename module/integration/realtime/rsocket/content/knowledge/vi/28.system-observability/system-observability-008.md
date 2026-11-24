# Thiết kế cảnh báo cho mất kết nối, quá tải và rò rỉ tài nguyên

RSocket giữ kết nối lâu dài và multiplex nhiều tương tác trên cùng một phiên. Vì vậy, sự cố không chỉ xuất hiện dưới dạng HTTP request lỗi: kết nối có thể liên tục rớt rồi kết nối lại, stream có thể bị treo, requester có thể tiêu thụ chậm, event loop có thể bận, hoặc bộ nhớ direct buffer tăng dần dù heap vẫn ổn định.

Một hệ thống cảnh báo tốt cần phát hiện ba nhóm vấn đề trước khi người dùng chịu ảnh hưởng lớn:

- **Mất kết nối**: kết nối hoặc SETUP thất bại, disconnect bất thường tăng, reconnect không thành công hoặc stream realtime bị gián đoạn.
- **Quá tải**: độ trễ tăng, request bị từ chối, số tác vụ đang chạy và queue tăng, dịch vụ phụ thuộc cạn connection pool.
- **Rò rỉ tài nguyên**: kết nối, stream, buffer, thread hoặc file descriptor không được giải phóng và tăng liên tục theo thời gian.

Không nên gửi cảnh báo cho mọi lần client disconnect. Mạng di động, trình duyệt đóng tab và deploy có thể tạo disconnect bình thường. Cảnh báo nên dựa trên tỷ lệ lỗi, mức ảnh hưởng, thời gian kéo dài và xu hướng tài nguyên; mỗi cảnh báo cần có ngưỡng, mức độ nghiêm trọng và bước điều tra cụ thể.

## 1. Bắt đầu từ SLI và ảnh hưởng người dùng

Trước khi chọn metric, hãy xác định điều gì người dùng cần và cách đo nó. Một số SLI phù hợp với dịch vụ RSocket:

| SLI | Cách đo | Ý nghĩa |
|---|---|---|
| Connection success ratio | Kết nối/SETUP thành công chia tổng lần thử | Client có mở được phiên để sử dụng dịch vụ không? |
| Request success ratio | Request hoàn tất thành công chia tổng request | Các thao tác nghiệp vụ có được phục vụ không? |
| Request latency | p50, p95, p99 theo route và interaction | Người dùng phải chờ bao lâu? |
| Stream continuity | Số lần stream kết thúc bất thường hoặc bị gián đoạn | Dữ liệu realtime có được duy trì không? |
| Rejection ratio | Request bị từ chối chia tổng request | Dịch vụ có đang thiếu năng lực hoặc chặn lưu lượng hợp lệ không? |
| Resource headroom | Mức sử dụng heap, direct memory, thread, file descriptor so với giới hạn | Dịch vụ còn bao nhiêu dư địa trước khi cạn tài nguyên? |

Đặt SLO theo nhu cầu thực tế, ví dụ 99,9% lần mở kết nối thành công trong 30 ngày hoặc 99% request đọc hoàn tất dưới 300 ms. Không dùng một con số mặc định cho mọi route: route tra cứu nhanh và route tạo báo cáo có thể có SLA khác nhau.

Với SLO, cảnh báo theo tốc độ tiêu thụ error budget (burn rate) thường hữu ích hơn một ngưỡng lỗi đơn lẻ. Một đợt lỗi lớn trong 5 phút cần phản ứng nhanh; tỷ lệ lỗi nhỏ nhưng kéo dài hàng giờ cũng cần được phát hiện. Có thể kết hợp cửa sổ ngắn và dài để giảm false positive.

## 2. Các metric nên thu thập

Hãy thu thập metric ở cả transport, RSocket interaction, ứng dụng và JVM/OS. Tên dưới đây là quy ước minh họa cho metric tùy chỉnh; Spring Boot/Micrometer không tự động cung cấp tất cả metric RSocket với đúng các tên này. JVM metrics có thể được lấy từ Micrometer binder, còn connection/stream/request cần instrument tại server, client, gateway hoặc interceptor phù hợp.

| Nhóm | Metric gợi ý | Loại | Nhãn nên dùng |
|---|---|---|---|
| Kết nối | `rsocket_connection_attempts_total` | Counter | `result`, `transport`, `endpoint` |
| Kết nối | `rsocket_connections_active` | Gauge | `instance`, `transport` |
| Kết nối | `rsocket_connections_closed_total` | Counter | `reason`, `transport` |
| Kết nối | `rsocket_setup_duration_seconds` | Histogram | `result`, `transport` |
| Request | `rsocket_server_requests_total` | Counter | `route`, `interaction`, `outcome` |
| Request | `rsocket_server_request_duration_seconds` | Histogram | `route`, `interaction`, `outcome` |
| Tải | `rsocket_server_inflight_requests` | Gauge | `instance` |
| Tải | `rsocket_server_rejected_requests_total` | Counter | `reason`, `route` |
| Stream | `rsocket_server_streams_active` | Gauge | `instance`, `interaction` |
| Stream | `rsocket_server_streams_orphaned` | Gauge | `instance` |
| Buffer | `rsocket_server_buffered_bytes` | Gauge | `instance`, `buffer_type` |
| JVM | `jvm_memory_used_bytes` | Gauge | `area`, `id` |
| JVM | `jvm_buffer_memory_used_bytes` | Gauge | `id` (ví dụ `direct`) |
| JVM | `jvm_threads_live_threads` | Gauge | — |
| Process | `process_files_open_files`, `process_files_max_files` | Gauge | — |

Với counter, ghi nhận outcome có tập giá trị nhỏ như `success`, `error`, `rejected`, `cancelled`. Với disconnect, dùng reason chuẩn hóa như `normal`, `client_close`, `transport_error`, `protocol_error`, `server_shutdown`. Không dùng exception message làm label.

### Tránh cardinality cao

Không gắn các giá trị sau vào label metric:

- `connectionId`, `streamId`, `sessionId`.
- `userId`, email, token hoặc IP đầy đủ.
- `orderId`, `deviceId`, correlation ID hoặc event ID.
- Route động chứa ID như `orders.ORD-1001.watch`.

Thay vào đó, chuẩn hóa route thành tên template như `orders.find` hoặc `orders.watch`, và chỉ dùng `tenant_tier`, `region`, `transport`, `interaction` hoặc outcome có số lượng giới hạn. ID cụ thể thuộc log/tracing có kiểm soát, không phải nhãn metric.

## 3. Instrument RSocket bằng Micrometer

Spring Boot Actuator và Micrometer giúp xuất metric JVM, process và metric do ứng dụng đăng ký. Để quan sát RSocket, instrument tại ranh giới kết nối, handler hoặc interceptor:

- Khi bắt đầu/kết thúc kết nối, cập nhật gauge active connections và counter theo close reason.
- Khi SETUP thành công/thất bại, ghi counter và thời gian setup.
- Khi handler bắt đầu/kết thúc, ghi in-flight request, duration và outcome.
- Khi stream được subscribe/cancel/complete/error, cập nhật active stream và lifetime.
- Khi từ chối request do quota, ghi counter riêng với reason chuẩn hóa.

Ví dụ instrument một handler reactive bằng Micrometer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Controller
class OrderController {

    private final OrderService orderService;
    private final MeterRegistry registry;

    OrderController(OrderService orderService, MeterRegistry registry) {
        this.orderService = orderService;
        this.registry = registry;
    }

    @MessageMapping("orders.find")
    Mono<OrderView> find(@Payload FindOrderRequest request) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            return orderService.findById(request.orderId())
                .doOnSuccess(value -> registry.counter(
                    "rsocket.server.requests", "route", "orders.find",
                    "interaction", "request_response", "outcome", "success").increment())
                .doOnError(error -> registry.counter(
                    "rsocket.server.requests", "route", "orders.find",
                    "interaction", "request_response", "outcome", "error").increment())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        registry.counter("rsocket.server.requests", "route", "orders.find",
                            "interaction", "request_response", "outcome", "cancelled").increment();
                    }
                    sample.stop(Timer.builder("rsocket.server.request.duration")
                        .tag("route", "orders.find")
                        .tag("interaction", "request_response")
                        .register(registry));
                });
        });
    }
}
```

Đây là ví dụ tại handler, chưa phải bộ instrument đầy đủ cho connection lifecycle. Trong production nên dùng helper/interceptor dùng chung để tránh lặp code và bảo đảm outcome `cancelled`/`rejected` được ghi riêng. Timer trong ví dụ đo thời gian từ lúc handler được subscribe tới khi kết thúc; nó không bao gồm thời gian kết nối hoặc chờ SETUP.

Với Timer, bật histogram/percentile phù hợp nếu cần Prometheus tính p95/p99. Chỉ bật bucket cần thiết vì histogram tạo thêm series. Không đăng ký gauge từ object request/connection ngắn hạn rồi giữ tham chiếu vô tình; quản lý vòng đời gauge để tránh chính instrumentation gây leak.

## 4. Quan sát kết nối và SETUP

Một lần disconnect không đồng nghĩa sự cố. Hãy phân biệt:

- Đóng bình thường do client đóng tab hoặc ứng dụng chuyển nền.
- Disconnect do deploy hoặc server shutdown có kế hoạch.
- Lỗi transport, reset TCP, WebSocket close bất thường.
- SETUP thất bại do xác thực, MIME type, protocol version hoặc cấu hình không tương thích.
- Reconnect liên tục (connection flapping) khiến người dùng không giữ được phiên ổn định.

Metric quan trọng gồm connection attempts theo kết quả, setup duration, active connections và close reason. Nếu có client-side telemetry, đo thêm tỷ lệ reconnect thành công và thời gian từ lúc mất kết nối tới lúc khôi phục.

Không cảnh báo chỉ vì `active_connections` giảm trong deploy hoặc ban đêm. Hãy kết hợp với synthetic probe, request success ratio hoặc số kết nối lỗi bất thường. Với dịch vụ có lưu lượng thấp, một vài lỗi có thể tạo tỷ lệ cao; cần có điều kiện số mẫu tối thiểu hoặc kiểm tra probe độc lập.

## 5. Cảnh báo mất kết nối

Một cảnh báo kết nối nên tập trung vào lỗi có ảnh hưởng:

1. Tỷ lệ mở kết nối/SETUP thất bại vượt ngưỡng trong một khoảng thời gian.
2. Số disconnect bất thường tăng đột biến.
3. Synthetic client không thể mở phiên hoặc thực hiện một request kiểm tra.
4. Reconnect không phục hồi được trong thời gian SLO cho phép.

Ví dụ PromQL giả định counter `rsocket_connection_attempts_total` có label `result="failed"` hoặc `result="success"`:

```promql
sum(rate(rsocket_connection_attempts_total{result="failed"}[5m]))
/
clamp_min(sum(rate(rsocket_connection_attempts_total[5m])), 0.001)
> 0.05
```

Biểu thức này cảnh báo khi hơn 5% lần thử kết nối thất bại trong cửa sổ 5 phút. Chọn ngưỡng theo SLO và chỉ kích hoạt khi có đủ traffic; với dịch vụ ít traffic, kết hợp synthetic probe thay vì chỉ dựa trên tỷ lệ.

Phát hiện disconnect bất thường:

```promql
sum(increase(rsocket_connections_closed_total{
  reason=~"transport_error|protocol_error"
}[5m])) > 30
```

Ngưỡng `30` chỉ là ví dụ. Hãy điều chỉnh theo quy mô, số kết nối bình thường và lịch deploy. Nếu cần phân biệt deploy, thêm annotation hoặc silence có thời hạn từ pipeline triển khai; không loại bỏ mọi lỗi trong một khoảng dài.

### Phân biệt sự cố server và mạng client

Nếu nhiều client ở nhiều vùng cùng thất bại, nghi ngờ server, load balancer, DNS hoặc chứng chỉ. Nếu chỉ một mạng di động hoặc một phiên bản client bị ảnh hưởng, điều tra mạng và client trước. Thu thập transport, region, client version ở log/tracing hoặc label có cardinality thấp để phân vùng lỗi.

## 6. Cảnh báo quá tải

Quá tải thường biểu hiện đồng thời qua độ trễ, tỷ lệ từ chối, số request đang chạy và queue. Không nên chỉ cảnh báo CPU cao: CPU có thể cao trong một batch hợp lệ mà latency vẫn nằm trong SLO; ngược lại, dịch vụ có thể quá tải vì chờ database hoặc connection pool dù CPU thấp.

Theo dõi tối thiểu:

- p95/p99 request duration theo route/interaction.
- Tỷ lệ `REJECTED` hoặc lỗi do quota/concurrency.
- In-flight requests so với capacity.
- Queue depth và tuổi của phần tử chờ lâu nhất.
- Event-loop lag, thread pool saturation và GC pause.
- Connection pool của database/HTTP client.
- CPU, heap, direct memory và network throughput.

Ví dụ p99 vượt 1 giây trong 10 phút:

```promql
histogram_quantile(
  0.99,
  sum by (le) (rate(rsocket_server_request_duration_seconds_bucket[5m]))
) > 1
```

Biểu thức yêu cầu Timer được xuất thành histogram bucket. Có thể lọc theo route hoặc interaction khi cần xác định nhóm request bị ảnh hưởng; không tạo một alert riêng cho từng ID động.

Cảnh báo tỷ lệ request bị từ chối:

```promql
sum(rate(rsocket_server_requests_total{outcome="rejected"}[5m]))
/
clamp_min(sum(rate(rsocket_server_requests_total[5m])), 0.001)
> 0.02
```

Ví dụ cảnh báo khi tỷ lệ từ chối vượt 2%. Nếu `rejected` là counter riêng thay vì outcome của counter tổng, hãy điều chỉnh mẫu số cho đúng; mẫu số phải đại diện tổng request được quan sát.

### Theo dõi năng lực đang sử dụng

Nếu ứng dụng có gauge capacity:

```promql
rsocket_server_inflight_requests
/
clamp_min(rsocket_server_inflight_capacity, 1)
> 0.90
```

Tỷ lệ trên 90% trong thời gian kéo dài có thể báo trước khi request bị từ chối. Đừng đặt capacity thành một hằng số sai với cấu hình runtime; cập nhật gauge khi số slot thay đổi.

## 7. Cảnh báo rò rỉ tài nguyên

Rò rỉ thường không xuất hiện như một đỉnh ngắn. Dấu hiệu đáng chú ý là tài nguyên không quay về mức nền sau khi tải giảm, hoặc tăng đều qua nhiều chu kỳ tải dù traffic và số kết nối ổn định.

### Heap và garbage collection

Theo dõi heap used sau GC, old generation, allocation rate và GC pause. Một đợt tăng heap trong lúc tải cao là bình thường; cảnh báo leak cần thấy xu hướng sau nhiều chu kỳ GC hoặc khi lưu lượng đã giảm.

### Direct memory và Netty buffers

RSocket trên Netty có thể sử dụng direct buffer ngoài heap. Heap thấp không có nghĩa direct memory còn an toàn. Theo dõi `jvm_buffer_memory_used_bytes{id="direct"}` và giới hạn direct memory mà JVM/container được cấp. Micrometer gắn tên buffer pool bằng tag `id`; khi exporter hoặc naming convention khác, hãy kiểm tra nhãn thực tế. Nếu có Netty allocator metrics, theo dõi số buffer đang active, số allocation/deallocation và arena usage theo phiên bản runtime.

### Kết nối và stream bị giữ lại

Theo dõi active connections, active streams, tuổi stream lâu nhất và số stream idle/orphaned. Nếu client đã disconnect nhưng stream/listener vẫn tồn tại, kiểm tra cancellation propagation và cleanup trong `doFinally`, `usingWhen` hoặc lifecycle hook tương ứng.

### Thread và file descriptor

Thread count tăng dần có thể cho thấy thread leak hoặc tạo scheduler/executor không được shutdown. File descriptor gần giới hạn có thể khiến không mở được socket mới, kể cả khi CPU và heap còn thấp.

## 8. Ví dụ cảnh báo rò rỉ bằng PromQL

Direct memory tăng theo xu hướng và dự báo vượt 90% giới hạn trong một giờ:

```promql
predict_linear(jvm_buffer_memory_used_bytes{id="direct"}[30m], 3600)
> on(instance) (0.90 * rsocket_direct_memory_limit_bytes)
```

Metric `rsocket_direct_memory_limit_bytes` là gauge ứng dụng cần xuất theo giới hạn thực tế của JVM/container và phải có label `instance` khớp với metric direct buffer để phép so sánh `on(instance)` hoạt động. `predict_linear` chỉ dự báo tuyến tính từ dữ liệu gần đây, không chứng minh có leak; dùng `for` và đối chiếu với traffic, GC, buffer pool cùng deploy.

File descriptor gần giới hạn:

```promql
process_files_open_files
/
clamp_min(process_files_max_files, 1)
> 0.85
```

Metric process file descriptor phụ thuộc OS binder/runtime; nếu môi trường không xuất metric này, dùng exporter của node hoặc metric hệ điều hành tương ứng.

Stream đang hoạt động tăng liên tục:

```promql
rsocket_server_streams_active > 500
and
deriv(rsocket_server_streams_active[30m]) > 0.2
```

Đây là tín hiệu nghi ngờ, không phải kết luận leak: traffic tăng cũng làm active stream tăng. Hãy đối chiếu với active connections, số request mới, stream lifetime và số stream idle/orphaned. Ngưỡng `500` và slope `0.2` phải được hiệu chỉnh theo tải bình thường của dịch vụ.

## 9. Mẫu Prometheus alert rules

Ví dụ sau minh họa cách khai báo thời gian duy trì (`for`), severity và runbook. Các metric tên `rsocket_*` là metric tùy chỉnh cần được instrument như phần trên; hãy thay ngưỡng theo SLO và năng lực thực tế.

```yaml
groups:
  - name: rsocket-availability
    rules:
      - alert: RSocketConnectionFailureRatioHigh
        expr: |
          sum(rate(rsocket_connection_attempts_total{result="failed"}[5m]))
          / clamp_min(sum(rate(rsocket_connection_attempts_total[5m])), 0.001) > 0.05
        for: 5m
        labels:
          severity: warning
          service: integration-realtime-rsocket
        annotations:
          summary: "RSocket connection attempts are failing"
          description: "More than 5% of connection attempts failed for 5 minutes."
          runbook_url: "https://runbooks.example.invalid/rsocket/connection-failures"

      - alert: RSocketRequestLatencyP99High
        expr: |
          histogram_quantile(0.99,
            sum by (le) (rate(rsocket_server_request_duration_seconds_bucket[5m]))) > 1
        for: 10m
        labels:
          severity: warning
          service: integration-realtime-rsocket
        annotations:
          summary: "RSocket p99 request latency is high"
          description: "p99 request duration exceeded 1 second for 10 minutes."

      - alert: RSocketRequestRejectionRatioHigh
        expr: |
          sum(rate(rsocket_server_requests_total{outcome="rejected"}[5m]))
          / clamp_min(sum(rate(rsocket_server_requests_total[5m])), 0.001) > 0.02
        for: 5m
        labels:
          severity: critical
          service: integration-realtime-rsocket
        annotations:
          summary: "RSocket requests are being rejected"
          description: "More than 2% of observed requests were rejected for 5 minutes."

      - alert: RSocketDirectMemoryProjectedHigh
        expr: |
          predict_linear(jvm_buffer_memory_used_bytes{id="direct"}[30m], 3600)
          > on(instance) (0.90 * rsocket_direct_memory_limit_bytes)
        for: 10m
        labels:
          severity: critical
          service: integration-realtime-rsocket
        annotations:
          summary: "RSocket direct memory may be exhausted"
          description: "Recent direct-memory growth projects usage above 90% of its limit."
```

Không sao chép nguyên xi `runbook_url` giả định vào production. Thay bằng URL runbook thật của tổ chức. Với cảnh báo critical, nên bổ sung notification routing, owner và escalation policy trong Alertmanager hoặc hệ thống quản lý sự cố.

## 10. Chọn severity và thời gian duy trì

Severity nên phản ánh mức ảnh hưởng và thời gian cần phản ứng:

| Mức | Khi nào dùng | Ví dụ |
|---|---|---|
| Critical / page | Người dùng diện rộng bị ảnh hưởng hoặc nguy cơ mất dịch vụ trong vài phút | Connection success gần 0%, direct memory sắp chạm giới hạn, request rejection nghiêm trọng |
| Warning / ticket | SLI suy giảm nhưng còn khả năng phục vụ hoặc có headroom | p99 tăng, reconnect tăng nhẹ, in-flight gần capacity |
| Info / dashboard | Xu hướng cần theo dõi, chưa cần hành động ngay | Số stream, traffic hoặc buffer tăng theo giờ cao điểm |

Dùng `for` để loại bỏ dao động ngắn. Cảnh báo mất kết nối có thể cần 3–5 phút duy trì; cảnh báo dự báo direct memory nên cần xu hướng 10–15 phút. Không đặt `for` quá dài với sự cố có thể làm dịch vụ ngừng trong vài phút.

Đặt ngưỡng theo baseline và SLO. Cảnh báo nên có cả điều kiện số mẫu tối thiểu hoặc synthetic probe cho hệ thống traffic thấp. Nếu một alert phụ thuộc vào hai metric, bảo đảm cả hai cùng có dữ liệu và cùng phạm vi label để phép toán PromQL không tạo kết quả rỗng.

## 11. Multi-window và burn-rate alerting

Với SLO availability hoặc request success, có thể dùng nhiều cửa sổ để phát hiện cả sự cố nhanh lẫn suy giảm kéo dài:

- Cửa sổ ngắn, ví dụ 5 phút: phát hiện đợt lỗi lớn cần phản ứng ngay.
- Cửa sổ trung bình, ví dụ 1 giờ: phát hiện lỗi kéo dài ở mức vừa.
- Cửa sổ dài, ví dụ 6 hoặc 24 giờ: theo dõi việc tiêu thụ error budget.

Burn rate được tính từ tỷ lệ lỗi thực tế chia tỷ lệ lỗi cho phép theo SLO. Nếu SLO cho phép 0,1% lỗi, tỷ lệ lỗi 1% tương ứng burn rate 10. Một alert multi-window có thể yêu cầu burn rate cao ở cả cửa sổ ngắn và dài để tránh page do một spike rất ngắn.

Không dùng một công thức burn rate chung cho mọi dịch vụ. Chọn cửa sổ, ngưỡng và mức tiêu thụ budget theo thời gian phản ứng mong muốn, độ dài SLO window và mức độ quan trọng của dịch vụ.

## 12. Phân biệt mất kết nối bình thường và sự cố

Các nguyên nhân disconnect khác nhau cần cách xử lý khác nhau:

| Nguyên nhân | Dấu hiệu | Cách xử lý cảnh báo |
|---|---|---|
| Client đóng tab/app | Close reason bình thường, phân bố rải rác | Ghi metric, không page từng lần |
| Mobile chuyển mạng | Reconnect thành công sau một khoảng ngắn | Theo dõi reconnect success và thời gian phục hồi |
| Deploy có kế hoạch | Disconnect tập trung theo thời điểm rollout | Silence có thời hạn, vẫn giữ cảnh báo nếu lỗi vượt ngưỡng sau deploy |
| Load balancer timeout | Nhiều kết nối bị đóng theo tuổi gần giống nhau | Kiểm tra idle timeout, ping/keepalive và cấu hình proxy |
| Server quá tải | Disconnect đi kèm latency/rejection/CPU hoặc pool saturation | Cảnh báo overload và connection failure theo cùng incident |
| DNS/TLS/certificate | SETUP/connect fail ở nhiều client | Kiểm tra DNS, certificate chain, expiry và endpoint |

Nếu client có keepalive hoặc heartbeat, theo dõi timeout và missed heartbeat theo phiên bản giao thức/client. Không tạo metric label từ connection ID; hãy log/tracing có sampling để điều tra một phiên cụ thể.

## 13. Runbook cho cảnh báo mất kết nối

Khi `RSocketConnectionFailureRatioHigh` hoặc disconnect surge kích hoạt:

1. Xác định phạm vi: một instance, một region, một transport hay toàn hệ thống.
2. Kiểm tra thời điểm bắt đầu so với deploy, scale event, thay đổi DNS, certificate hoặc load balancer.
3. So sánh connection attempts, setup failures, close reason, synthetic probe và request success ratio.
4. Kiểm tra server có lắng nghe đúng port/path, gateway có health và upstream còn reachable.
5. Kiểm tra TLS, WebSocket upgrade, protocol version, MIME type và authentication nếu SETUP thất bại.
6. Nếu chỉ một instance lỗi, drain traffic và restart có kiểm soát theo quy trình vận hành.
7. Sau khắc phục, xác nhận connection success và request success trở lại baseline; kiểm tra reconnect storm không còn.

Không restart hàng loạt instance ngay khi thấy disconnect spike. Nếu nguyên nhân là client reconnect đồng loạt, restart có thể làm tải kết nối tăng thêm.

## 14. Runbook cho cảnh báo quá tải

Khi latency, rejection hoặc in-flight utilization vượt ngưỡng:

1. Xác định route/interaction nào có p95/p99 cao và tỷ lệ lỗi tăng.
2. Kiểm tra in-flight requests, active streams, queue depth, event-loop lag và CPU.
3. Kiểm tra downstream: database pool, HTTP connection pool, broker lag và timeout.
4. Xác định tải tăng do traffic hợp lệ, retry storm, batch quá lớn hay một route tốn tài nguyên.
5. Áp dụng load shedding/rate limit hoặc giảm concurrency nếu đã có chính sách được kiểm thử.
6. Scale out nếu bottleneck có thể phân tán; không scale khi dependency chung đã cạn capacity.
7. Xác nhận latency, rejection và queue depth giảm trước khi đóng incident.

Không tăng thread pool hoặc queue vô hạn như phản ứng mặc định. Việc đó có thể làm context switching và bộ nhớ tăng, khiến sự cố nặng hơn.

## 15. Runbook cho nghi ngờ rò rỉ tài nguyên

Khi direct memory, heap, active stream hoặc file descriptor tăng liên tục:

1. So sánh xu hướng với traffic, active connections và thời điểm deploy.
2. Kiểm tra heap sau GC, direct buffer pool, thread count, open file descriptors và container memory limit.
3. Xem stream/connection lifetime và số stream idle/orphaned; xác nhận cancel/close có giải phóng tài nguyên.
4. Lấy heap dump hoặc native memory diagnostics theo quy trình an toàn và giới hạn dung lượng.
5. Kiểm tra Netty `ByteBuf` retain/release, callback/listener, scheduler/executor và resource cleanup.
6. Nếu gần chạm giới hạn, drain instance và restart có kiểm soát theo runbook; giữ artifact phục vụ phân tích sau sự cố.
7. Chạy soak test sau khi sửa để xác nhận mức tài nguyên quay về baseline và không tiếp tục tăng.

Không kết luận leak chỉ từ một lần heap/direct memory cao. Cache có thể tăng tới kích thước ổn định; leak thể hiện ở xu hướng không hồi phục hoặc tăng khi tải và số đối tượng hoạt động đã trở về mức cũ.

## 16. Giảm false positive và alert fatigue

Một cảnh báo chỉ hữu ích khi người nhận biết cần làm gì. Các nguyên tắc sau giúp giảm nhiễu:

- Alert theo tỷ lệ lỗi và SLI thay vì mỗi exception hoặc disconnect.
- Dùng `for`, cửa sổ nhiều độ dài và số mẫu tối thiểu.
- Loại close reason bình thường khỏi nhóm abnormal disconnect.
- Silence deploy có thời hạn và có owner; không tắt alert vô thời hạn.
- Group các cảnh báo cùng nguyên nhân thành một incident, ví dụ overload kéo theo disconnect.
- Dùng inhibition để không page đồng thời cho các triệu chứng phụ khi đã có alert nguyên nhân gốc.
- Có runbook, service owner, dashboard và mức severity cho mỗi alert.
- Đánh giá alert sau incident: cảnh báo nào phát hiện muộn, cảnh báo nào không cần hành động.

Tránh alert trên metric không có owner hoặc không có hành động cụ thể. Một dashboard có thể chứa nhiều chỉ số; một alert nên chỉ ra điều gì đang đe dọa SLO và bước đầu tiên để kiểm tra.

## 17. Kiểm thử cảnh báo

Đừng chờ production gặp sự cố mới biết alert có hoạt động. Hãy kiểm thử bằng tải và lỗi có kiểm soát:

1. Ngắt transport ở một tỷ lệ nhỏ client và xác nhận connection failure alert hoạt động đúng ngưỡng.
2. Làm SETUP thất bại do endpoint hoặc xác thực trong môi trường test.
3. Tạo tải vượt concurrency limit và xác nhận rejection/latency alert kích hoạt.
4. Làm chậm downstream để kiểm tra queue, in-flight và timeout alert.
5. Tạo stream dài hạn rồi cancel/disconnect để xác nhận active stream trở về baseline.
6. Chạy soak test với buffer/connection churn để quan sát heap, direct memory, thread và file descriptor.
7. Mô phỏng direct memory hoặc file descriptor tiến gần giới hạn trong môi trường cô lập.
8. Kiểm tra Alertmanager routing, dedup, inhibition, silence và runbook link.
9. Xác nhận alert tự resolve khi metric trở lại bình thường.
10. Đo thời gian từ lúc lỗi bắt đầu tới khi alert được gửi và người trực nhận được.

Thực hiện fault injection trong staging hoặc môi trường được cô lập, có giới hạn tải và kế hoạch dừng. Không cố ý làm cạn bộ nhớ hoặc file descriptor trên production để thử alert.

## 18. Dashboard vận hành nên có gì?

Một dashboard tổng quan RSocket có thể chia thành các hàng:

| Hàng | Panel |
|---|---|
| Availability | Connection success, setup failures, abnormal disconnects, synthetic probe |
| Traffic | Request rate theo interaction/route, active connections, active streams |
| Latency/errors | p50/p95/p99, outcome ratio, rejected và application errors |
| Capacity | In-flight/capacity, queue depth, event-loop lag, downstream pool utilization |
| JVM/OS | Heap after GC, direct memory, GC pause, live threads, open file descriptors |
| Stream lifecycle | Stream duration, cancel/complete/error, orphaned/idle streams |
| Deployment | Version, instance restart, rollout marker và cấu hình transport |

Dashboard cần cho phép chuyển từ tổng quan sang instance/route/transport có cardinality giới hạn. Log và trace mới chứa các ID cụ thể để điều tra từng request hoặc connection.

## 19. Checklist thiết kế cảnh báo production

- [ ] Có SLI cho connection success, request success, latency và stream continuity.
- [ ] Có metric cho setup, active connection, disconnect reason và reconnect.
- [ ] Có request counter, duration histogram, in-flight, rejected và active stream.
- [ ] Có heap, direct buffer, thread, file descriptor và queue metrics.
- [ ] Metric RSocket tùy chỉnh có lifecycle rõ ràng và không giữ tham chiếu làm leak.
- [ ] Label dùng route template và outcome hữu hạn; không dùng connection/user/request ID.
- [ ] Alert mất kết nối loại trừ close reason bình thường và có synthetic probe.
- [ ] Alert overload kết hợp latency, rejection, concurrency và dependency saturation.
- [ ] Alert leak dựa trên xu hướng sau GC/tải giảm, không dựa vào một điểm cao.
- [ ] Có `for`, severity, owner, runbook và notification routing.
- [ ] Có multi-window/burn-rate alert cho SLO quan trọng.
- [ ] Có silence/inhibition cho deploy và triệu chứng phụ với thời hạn rõ ràng.
- [ ] Đã diễn tập connection loss, overload, cancellation và resource leak trong staging.
- [ ] Có kiểm tra alert resolve và thời gian phát hiện.

Thiết kế cảnh báo RSocket cần nhìn cả kết nối lâu dài lẫn các stream và tài nguyên bên dưới. Cảnh báo mất kết nối nên dựa trên tỷ lệ setup/reconnect thất bại và ảnh hưởng người dùng; cảnh báo quá tải nên kết hợp latency, rejection, in-flight và dependency; cảnh báo rò rỉ cần theo dõi xu hướng heap, direct memory, stream, thread và file descriptor qua nhiều chu kỳ tải. Khi metric có cardinality thấp, ngưỡng gắn với SLO và runbook rõ ràng, đội vận hành có thể phát hiện sớm sự cố mà không bị ngập trong cảnh báo nhiễu.

## Tài liệu tham khảo

- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Alertmanager — Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
