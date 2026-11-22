# Thiết kế health check, tự phục hồi và graceful shutdown

## 1. Độ tin cậy bắt đầu từ cách phát hiện và xử lý lỗi

Một dịch vụ cloud có thể chạy trên VM, container, Kubernetes, function hoặc nền tảng managed. Dù nền tảng tự cấp tài nguyên, process vẫn có thể treo, startup thất bại, mất kết nối database, cạn thread, hết bộ nhớ hoặc không còn xử lý request trong thời gian mong muốn. Một instance đang tồn tại chưa chắc đang phục vụ tốt; một process trả lời được một endpoint kiểm tra cũng chưa chắc đã sẵn sàng nhận traffic.

Ba năng lực cần phối hợp:

- **Health check:** cung cấp tín hiệu có cấu trúc về việc một thành phần đã khởi động, có thể nhận traffic hoặc cần được khởi động lại hay không.
- **Self-healing (tự phục hồi):** nền tảng hoặc ứng dụng phát hiện trạng thái lỗi và thực hiện hành động phục hồi như restart process/container, thay thế instance, reschedule pod hoặc tái tạo replica.
- **Graceful shutdown:** thành phần ngừng nhận công việc mới, hoàn tất hoặc bàn giao công việc đang xử lý, đóng kết nối và kết thúc trong thời hạn cho phép.

Nếu health check sai, hệ thống có thể restart liên tục một ứng dụng vốn chỉ đang chờ dependency; nếu không có readiness check, load balancer có thể gửi request tới instance đang khởi động; nếu shutdown đột ngột, request hoặc message có thể mất, bị xử lý lặp hay để lại transaction không rõ kết quả.

Trong module **CLOUD_ARCHITECTURE**, health check và lifecycle của workload là một phần của thiết kế độ tin cậy. Chúng phải được xem cùng SLO, failure domain, dependency, autoscaling, deployment strategy, retry, queue semantics và khả năng vận hành.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt startup, readiness và liveness check, đồng thời chọn đúng hành động cho từng tín hiệu.
2. Thiết kế health endpoint an toàn, nhanh và không tạo tải lớn lên dependency.
3. Kết hợp health check của ứng dụng, container platform và load balancer.
4. Thiết kế tự phục hồi theo process, container, node và failure domain.
5. Xử lý crash loop, unhealthy dependency và tránh cascading failure.
6. Thiết kế graceful shutdown với drain, termination signal, deadline và xử lý in-flight work.
7. Bảo vệ queue message, transaction và kết nối khi worker dừng.
8. Kiểm thử failure/recovery, đặt metric, alert và runbook.

## 2. Ba loại probe: startup, readiness và liveness

Không nên gộp mọi câu hỏi về health thành một endpoint trả về 200 hoặc 500. Ba loại probe phục vụ ba quyết định khác nhau.

| Probe | Câu hỏi | Khi thất bại | Dùng để |
|---|---|---|---|
| **Startup** | Ứng dụng đã hoàn tất khởi tạo ban đầu chưa? | Chưa đánh dấu startup thành công; nền tảng có thể tiếp tục chờ hoặc cuối cùng restart theo policy | Bảo vệ ứng dụng có khởi động chậm, model load hoặc migration/init dài |
| **Readiness** | Instance hiện có thể nhận công việc mới an toàn không? | Loại khỏi endpoint/traffic hoặc không cấp task mới | Ngăn request tới instance chưa sẵn sàng hoặc đang drain |
| **Liveness** | Process còn tiến triển và có khả năng tự tiếp tục không? | Restart process/container theo cấu hình nền tảng | Phục hồi process deadlock/treo hoặc trạng thái không thể tự hồi phục |

### 2.1. Startup probe

Startup probe cho phép ứng dụng có thời gian khởi động dài mà không bị liveness probe kết luận quá sớm. Ví dụ một inference service cần tải model, khởi tạo runtime và warm cache. Trước khi startup thành công, nền tảng nên chờ theo ngân sách đã định; không gửi traffic cho service chưa ready.

Startup probe không nên chờ vô hạn. Đặt ngưỡng dựa trên startup duration p95/p99, giới hạn thời gian deployment và SLO phục hồi. Nếu startup thường xuyên vượt ngưỡng, điều tra image size, dependency initialization, model loading hoặc resource limit.

### 2.2. Readiness probe

Readiness xác định instance có thể nhận request mới hay không. Instance có thể sống nhưng chưa ready:

- Đang load cấu hình hoặc warm cache.
- Chưa tạo được connection pool cần thiết.
- Đang drain trước shutdown.
- Đã chạm saturation và chủ động ngừng nhận việc mới.
- Dependency thiết yếu tạm thời không đáp ứng, trong khi restart process không giải quyết được.

Readiness fail thường nên khiến load balancer/service router ngừng gửi traffic mới; không nhất thiết restart instance. Khi điều kiện được khôi phục, instance có thể trở lại ready.

### 2.3. Liveness probe

Liveness kiểm tra process có còn hoạt động và tiến triển hay không. Ví dụ event loop bị deadlock, internal worker thread bị kẹt hoặc main service loop không xử lý được công việc.

Liveness failure có thể kích hoạt restart. Vì vậy probe phải kiểm tra điều mà restart thực sự có cơ hội sửa. Không nên cho liveness phụ thuộc trực tiếp vào mọi dịch vụ ngoài như database, payment provider hoặc DNS; một outage ở dependency có thể làm tất cả replica đồng loạt restart, khiến tình trạng xấu hơn.

### 2.4. Quy tắc lựa chọn

~~~mermaid
flowchart TD
    Start["Workload starts"] --> Startup{"Startup complete?"}
    Startup -->|No| Wait["Continue bounded startup checks"]
    Wait --> Startup
    Startup -->|Yes| Ready{"Can accept new work?"}
    Ready -->|No| Out["Keep out of traffic / wait"]
    Out --> Ready
    Ready -->|Yes| Serve["Serve requests"]
    Serve --> Live{"Process making progress?"}
    Live -->|Yes| Serve
    Live -->|No, recoverable by restart| Restart["Restart workload"]
    Restart --> Start
~~~

Đây là mô hình logic. Cách một platform kết hợp probe, health state và restart policy khác nhau; cần kiểm tra semantics thực tế của nền tảng.

## 3. Health endpoint nên kiểm tra điều gì?

Một health endpoint phải phục vụ quyết định rõ ràng, không phải một API tổng hợp tất cả dependency theo cách tốn kém.

### 3.1. Phân biệt process health và dependency health

| Kiểm tra | Có thể thuộc probe nào? | Cách suy nghĩ |
|---|---|---|
| Main event loop/thread còn phản hồi | Liveness | Có tiến triển nội bộ không? |
| Startup/config đã nạp | Startup | Có hoàn tất init bắt buộc không? |
| App có thể xử lý request đơn giản | Readiness | Có đủ điều kiện nhận traffic mới không? |
| DB connection pool dùng được | Readiness hoặc dependency status riêng | DB có bắt buộc cho mọi request không? |
| Payment provider đang down | Thường là dependency status/feature degradation | Restart toàn bộ API không sửa được outage provider |
| Queue consumer còn nhận message | Readiness của worker | Có thể nhận và xử lý work mới không? |
| Disk usage tăng | Monitoring/alert, đôi khi readiness | Xác định threshold và khả năng phục hồi |
| Thread pool cạn | Readiness/saturation signal; điều tra liveness riêng | Instance có thể không đáp ứng request dù process còn chạy |

### 3.2. Không biến health check thành bài load test

Health check thường được gọi định kỳ bởi nhiều control plane, endpoint monitor và load balancer. Nếu mỗi lần probe chạy nhiều query, gọi hàng loạt service hoặc quét toàn bộ cache, chính probe có thể làm hệ thống quá tải.

Nên:

- Giữ probe nhanh và có deadline nhỏ.
- Dùng phép kiểm tra nhẹ, giới hạn query và không tạo side effect.
- Cache dependency health trong thời gian ngắn nếu cần, thay vì mỗi probe fan-out.
- Tránh health check đồng loạt chạy cùng thời điểm ở mọi replica; thêm jitter nếu phù hợp.
- Tách trạng thái chi tiết cho dashboard/diagnostics khỏi endpoint probe đơn giản.
- Không trả thông tin secret, connection string, hostname nội bộ hoặc stack trace ra public endpoint.

### 3.3. Trạng thái health nên có ngữ nghĩa ổn định

Một ứng dụng có thể biểu diễn trạng thái:

~~~json
{
  "status": "NOT_READY",
  "checks": {
    "startup": "READY",
    "request_handler": "READY",
    "database_pool": "DEGRADED",
    "shutdown": "DRAINING"
  }
}
~~~

Đây là ví dụ payload nội bộ; không phải schema chuẩn bắt buộc. Endpoint readiness có thể chỉ trả mã trạng thái phù hợp với platform, còn diagnostics endpoint được bảo vệ để hiển thị chi tiết. Khi đang drain, readiness phải fail hoặc service registry phải đánh dấu instance không nhận request mới.

## 4. Liveness không nên phụ thuộc mù quáng vào database

Một lỗi thiết kế thường gặp là liveness endpoint chạy SELECT 1 tới database. Khi DB gặp sự cố, tất cả replica API trở thành unhealthy và bị restart liên tục. Sau khi DB phục hồi, toàn bộ replica đồng thời khởi động và tạo connection storm.

Nên phân biệt:

- **Process liveness:** ứng dụng có đang tiến triển không?
- **Readiness:** ứng dụng có thể nhận workload mới không?
- **Dependency health:** database, queue, cache hoặc provider đang ở trạng thái nào?
- **Business health:** các luồng nghiệp vụ quan trọng có đạt tỷ lệ thành công/SLO không?

Nếu DB là dependency bắt buộc để xử lý mọi request ghi, readiness có thể ngừng nhận request ghi khi DB không sẵn sàng; nhưng endpoint liveness vẫn có thể báo process sống. Hệ thống có thể trả lỗi có kiểm soát hoặc chỉ phục vụ read path nếu nghiệp vụ cho phép.

### 4.1. Một dependency không nhất thiết làm cả service unhealthy

Ví dụ Booking API có thể đọc reservation từ database chính, gửi email qua notification queue và gọi payment provider. Khi email provider down:

- Booking API có thể tiếp tục tạo booking nếu transaction cốt lõi thành công và notification được lưu vào outbox/queue.
- Notification worker có thể giảm readiness hoặc dừng nhận thêm message nếu backlog/attempt đã chạm ngưỡng.
- Payment flow có thể trả trạng thái pending/unknown nếu provider không phản hồi.
- Liveness của Booking API không nên fail chỉ vì email provider down.

Health semantics cần theo dependency bắt buộc của từng operation, không dùng một danh sách dependency đồng nhất cho toàn ứng dụng.

## 5. Self-healing ở nhiều lớp

Self-healing là phản ứng tự động với lỗi đã được phát hiện. Nó có thể diễn ra tại process, container, node, instance, service routing hoặc tầng dữ liệu.

| Lớp | Tín hiệu | Hành động phục hồi |
|---|---|---|
| Process | Main loop treo, process exit | Supervisor hoặc runtime restart process |
| Container | Liveness fail, container exit | Container runtime restart container theo policy |
| Pod/workload | Pod unhealthy hoặc bị evict | Controller tạo pod thay thế |
| Node/VM | Node mất heartbeat, host failure | Scheduler thay thế workload trên node khác; autoscaler bổ sung node nếu cần |
| Service routing | Endpoint không ready | Load balancer/service mesh loại khỏi traffic |
| Queue consumer | Worker dừng hoặc lease hết hạn | Message có thể được giao lại; consumer khác nhận |
| Database | Node failover/replica promotion | Managed DB hoặc cluster recovery theo cấu hình |
| Region | Regional outage | Failover sang region khác nếu kiến trúc và dữ liệu cho phép |

Restart chỉ là một loại self-healing. Không phải mọi lỗi đều được sửa bằng restart; cần chọn hành động theo failure mode và trạng thái dữ liệu.

### 5.1. Desired state và controller

Trong hệ thống khai báo desired state, controller liên tục so sánh trạng thái thực tế với trạng thái mong muốn. Nếu deployment yêu cầu 5 replica nhưng chỉ còn 4, controller có thể tạo pod mới. Nếu pod bị restart, controller vẫn bảo đảm số replica mong muốn.

Điều này giúp tự phục hồi khi instance chết, nhưng không chứng minh ứng dụng bên trong đang hoạt động đúng về nghiệp vụ. Một pod có thể Running và Ready nhưng trả về dữ liệu sai; cần quality metrics, synthetic checks và business SLI riêng.

## 6. Restart policy và crash loop

Restart có thể khôi phục deadlock hoặc lỗi tạm thời, nhưng restart liên tục có thể gây mất ổn định.

### 6.1. Khi nào restart có ích?

- Process bị deadlock và không thể tiếp tục.
- Memory leak tích lũy đã vượt ngưỡng; restart tạm khôi phục, trong lúc điều tra nguyên nhân.
- Internal state hỏng và không có cách phục hồi trong process.
- Worker bị kẹt ở trạng thái không tiến triển sau timeout.

### 6.2. Khi nào restart có thể làm tệ hơn?

- Database đang down và toàn bộ replica restart cùng lúc.
- Startup phụ thuộc provider đang outage, gây crash loop.
- Credential sai hoặc config lỗi, restart không thay đổi nguyên nhân.
- Memory limit quá thấp, mọi instance mới đều bị OOM.
- Dependency connection storm làm DB quá tải hơn.

### 6.3. Backoff và restart budget

Restart policy nên có backoff để tránh khởi động lặp quá nhanh:

~~~text
Attempt 1 -> wait 1s
Attempt 2 -> wait 2s
Attempt 3 -> wait 4s
Attempt 4 -> wait 8s
...
Cap at a configured maximum delay
~~~

Giá trị chỉ minh họa. Nền tảng có thể áp dụng backoff riêng; ứng dụng cần tránh tự restart thêm một lớp làm retry storm. Có thể đặt giới hạn restart trong một khoảng thời gian, sau đó giữ workload ở trạng thái failed/unhealthy và phát alert để người vận hành xử lý.

Một crash loop cần được phân loại theo exit code, OOMKilled, startup timeout, probe failure, dependency timeout và config error. Đừng chỉ tăng probe threshold để che lỗi khởi động kéo dài.

## 7. Readiness và load balancer

Load balancer thường định kỳ kiểm tra target và chỉ gửi traffic tới endpoint được xem là healthy. Tuy nhiên probe của load balancer, readiness của orchestrator và health check của ứng dụng có thể khác semantics.

### 7.1. Luồng thêm instance mới

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant A as New instance
    participant L as Load balancer
    P->>A: Create instance
    A->>A: Start process and initialize
    P->>A: Startup check
    A-->>P: Startup ready
    P->>A: Readiness check
    A-->>P: Ready
    P->>L: Register / mark target healthy
    L->>A: Health probe
    L->>A: Route production traffic
~~~

Không nên cho load balancer gửi traffic chỉ vì VM đã boot xong. Ứng dụng cần sẵn sàng và có thể phục vụ request.

### 7.2. Target deregistration và connection draining

Khi scale-in hoặc deployment, load balancer cần ngừng gửi request mới tới target. **Deregistration delay / connection draining** cho thời gian request đang chạy hoàn tất trước khi đóng target.

Nếu timeout drain ngắn hơn request hợp lệ dài nhất, request có thể bị cắt. Nếu quá dài, deployment hoặc scale-in bị chậm. Cần dựa trên request duration, streaming, WebSocket, long polling và termination grace period.

Load balancer có thể giữ persistent connection hoặc WebSocket sau khi target bị đánh dấu unhealthy; phải kiểm tra hành vi cụ thể, không giả định mọi kết nối lập tức bị ngắt.

## 8. Graceful shutdown: dừng nhận việc trước khi dừng process

Graceful shutdown là quá trình kết thúc có trật tự. Mục tiêu là ngăn công việc mới đi vào, cho công việc đang xử lý hoàn tất hoặc được bàn giao, sau đó đóng dependency.

Một chu trình điển hình:

1. Nhận tín hiệu termination hoặc thông báo shutdown.
2. Chuyển readiness sang NOT_READY/DRAINING.
3. Gỡ target khỏi load balancer/service routing.
4. Ngừng nhận request/message/job mới.
5. Hoàn tất request/task đang chạy trong grace period.
6. Commit hoặc rollback transaction nội bộ theo trạng thái xác định.
7. Ack/delete message chỉ sau khi side effect đã an toàn; nếu chưa hoàn tất, để message được giao lại.
8. Flush log/telemetry và đóng pool/connection.
9. Thoát process trước deadline của nền tảng.

~~~mermaid
flowchart TD
    Signal["SIGTERM / shutdown event"] --> Mark["Set readiness = NOT_READY"]
    Mark --> Deregister["Deregister / drain traffic"]
    Deregister --> Stop["Stop accepting new work"]
    Stop --> Wait["Wait for in-flight work"]
    Wait --> Finish{"Work completed before deadline?"}
    Finish -->|Yes| Close["Commit, flush telemetry, close connections"]
    Finish -->|No| Safe["Cancel safely / leave message retryable"]
    Safe --> Close
    Close --> Exit["Exit process"]
~~~

Không nên bắt đầu bằng việc đóng database pool trước khi request đang chạy hoàn tất. Những request đó có thể vẫn cần đọc/ghi DB để kết thúc nhất quán.

## 9. Tín hiệu SIGTERM, SIGKILL và termination grace period

Trong nhiều môi trường container/Linux, runtime gửi SIGTERM để yêu cầu process dừng. Nếu process không kết thúc trong khoảng grace period, runtime có thể gửi SIGKILL hoặc cưỡng chế dừng.

- **SIGTERM:** cơ hội cho ứng dụng bắt tín hiệu và shutdown có trật tự.
- **SIGINT:** thường biểu diễn interrupt từ terminal; ứng dụng có thể xử lý tương tự nhưng semantics phụ thuộc runtime.
- **SIGKILL:** không thể bắt hoặc xử lý; process bị kết thúc ngay.
- **Termination grace period:** thời gian nền tảng cho process hoàn tất sau khi bắt đầu termination.

Grace period phải đủ lớn cho request/task đang chạy lâu nhất trong policy, đồng thời không vượt thời gian rollout/scale-in chấp nhận được.

### 9.1. Tính ngân sách shutdown

Ví dụ:

| Bước | Ngân sách minh họa |
|---|---:|
| Đánh dấu readiness và deregister | 5 giây |
| Chờ request in-flight | 25 giây |
| Flush/commit/close | 5 giây |
| Dự phòng | 5 giây |
| **Tổng** | **40 giây** |

Đây là ví dụ. Nếu API có request dài 2 phút hoặc WebSocket sống nhiều giờ, không thể chỉ đặt grace period 40 giây và kỳ vọng mọi kết nối hoàn tất. Cần giới hạn request duration, hỗ trợ reconnect, session resumption hoặc draining theo hợp đồng.

### 9.2. Đăng ký shutdown hook

Ví dụ pseudocode Java:

~~~java
public final class ServiceLifecycle {
    private final ReadinessState readiness;
    private final RequestTracker requests;
    private final ExecutorService executor;
    private final DataSource dataSource;

    public void register() {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            readiness.markDraining();
            stopAcceptingNewRequests();
            requests.awaitInFlight(Duration.ofSeconds(25));
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                executor.shutdownNow();
            }
            closeDataSource(dataSource);
        }));
    }
}
~~~

Đây là pseudocode minh họa; cách đóng server listener, connection pool, transaction manager và executor phụ thuộc framework. Hook phải idempotent, có deadline tổng và không nuốt interruption. Không đảm bảo shutdown hook chạy trong SIGKILL, hard crash hay mất điện.

## 10. Graceful shutdown cho queue worker

Worker xử lý message cần shutdown an toàn hơn một HTTP server đơn giản, vì message có thể được giao lại sau timeout hoặc visibility lease.

### Quy tắc cơ bản

- Sau khi nhận drain signal, ngừng poll/receive message mới.
- Cho message đang xử lý hoàn tất nếu còn đủ thời gian.
- Chỉ ack/delete sau khi side effect được commit hoặc trạng thái operation được lưu bền vững.
- Nếu không thể hoàn tất, không ack; để broker giao lại sau visibility timeout/lease.
- Consumer phải idempotent để xử lý duplicate an toàn.
- Nếu hỗ trợ lease extension, chỉ gia hạn khi worker thực sự còn tiến triển.

### Ví dụ tình huống

Worker nhận message gửi hóa đơn. Process bị SIGTERM sau khi provider tạo hóa đơn nhưng trước khi worker ack message. Broker giao lại message cho worker khác. Nếu không có idempotency key theo invoice operation, hệ thống có thể tạo hai hóa đơn hoặc gửi hai lần thông báo.

Giải pháp là dùng operation ID ổn định, tra cứu provider/reference và ghi trạng thái hoàn tất trước khi ack. Nếu outcome không rõ, worker mới phải reconcile trước khi tạo side effect mới.

## 11. Graceful shutdown cho request dài và streaming

Không phải request nào cũng hoàn tất trong vài giây. Upload/download lớn, WebSocket, server-sent events, long polling và stream consumer có thể sống lâu.

Các phương án:

- Đặt maximum request duration và trả thông tin reconnect khi cần.
- Dừng nhận connection mới nhưng cho connection hiện tại một khoảng drain.
- Gửi close frame/termination event cho WebSocket client, hỗ trợ reconnect và resume cursor.
- Với upload, lưu checkpoint/chunk đã nhận để client tiếp tục.
- Với streaming response, kết thúc theo protocol và không cắt giữa một record nếu có thể.
- Với job dài, chuyển trạng thái operation bền vững để worker khác có thể tiếp tục.

Nếu connection bị cắt, client cần biết retry có an toàn không. Request ghi phải có idempotency key hoặc operation status để không tạo tác động trùng.

## 12. Dependency failure và cascading restart

Một dependency down không nên tự động làm mọi service phụ thuộc restart. Cần phân biệt khả năng phục hồi và cách giảm tải:

- **Timeout:** giới hạn thời gian chờ; tránh thread/connection bị giữ vô hạn.
- **Circuit breaker:** tạm ngừng gọi dependency đang lỗi; cho phép probe phục hồi theo policy.
- **Bulkhead:** giới hạn tài nguyên riêng cho từng dependency hoặc loại request.
- **Retry with backoff/jitter:** chỉ retry lỗi tạm thời và operation an toàn.
- **Fallback/degraded mode:** chỉ trả dữ liệu cache hoặc chức năng rút gọn nếu nghiệp vụ chấp nhận.
- **Readiness:** loại instance khỏi traffic khi chính instance không thể nhận request an toàn; không đánh đồng outage toàn cục với process chết.
- **Admission control:** giảm request mới để tránh làm dependency quá tải.

### Ví dụ

Nếu database đang failover:

1. API áp timeout ngắn và circuit breaker cho DB call.
2. Không tạo hàng loạt thread chờ vô hạn.
3. Liveness vẫn phản ánh process có tiến triển.
4. Readiness phản ánh khả năng phục vụ đúng loại request theo thiết kế.
5. Request ghi có thể bị từ chối có kiểm soát hoặc chuyển sang queue nếu semantics nghiệp vụ cho phép.
6. Khi DB phục hồi, connection pool reconnect với backoff; không để tất cả replica reconnect cùng lúc.

## 13. Self-healing và failure domain

Một hệ thống có nhiều replica nhưng tất cả cùng nằm trong một node, zone hoặc dependency duy nhất vẫn có thể có điểm lỗi chung.

### Phân tầng phục hồi

| Failure domain | Phát hiện | Hành động |
|---|---|---|
| Process | Liveness, process exit, watchdog | Restart process |
| Container/pod | Container exit, probe failure | Restart/recreate pod |
| Node/VM | Heartbeat, node condition | Reschedule sang node khác |
| Availability zone | Health signal và dependency monitoring | Chuyển traffic/workload sang zone còn tốt |
| Region | Regional health và data replication status | Failover theo DR plan |
| External provider | Error rate/timeout, status feed | Circuit breaker, fallback hoặc degraded mode |

Tự động failover phải xét khả năng dữ liệu theo kịp, write authority, split-brain, replication lag và cách quay lại. Chuyển traffic sang region khác mà database chưa sẵn sàng có thể tạo lỗi hoặc mất dữ liệu.

### 13.1. Không restart cả fleet cùng lúc

Nếu mọi replica fail liveness do cùng một dependency timeout, restart đồng loạt gây reconnect storm và cold start tập thể. Nên có jitter, restart budget, max unavailable trong deployment, circuit breaker và backoff để giảm đồng bộ.

## 14. Readiness trong deployment và rolling update

Trong rolling deployment, instance mới chỉ nên nhận traffic khi startup hoàn tất và readiness đạt. Instance cũ cần được drain trước khi process dừng.

Một chu trình:

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant N as New replica
    participant O as Old replica
    participant LB as Load balancer
    C->>N: Start new replica
    N->>N: Startup and initialize
    N-->>C: Startup and readiness pass
    C->>LB: Add new replica
    LB-->>N: Route new traffic
    C->>O: Begin termination
    O->>LB: Mark not ready / deregister
    LB-->>O: Stop new traffic; drain existing
    O->>O: Complete in-flight work
    O-->>C: Exit
~~~

Các tham số như max unavailable, max surge, readiness period và termination grace period phải phối hợp. Nếu max unavailable quá lớn, capacity có thể giảm dưới mức tối thiểu; nếu max surge quá lớn, database connection và compute quota có thể bị vượt.

## 15. Health check và autoscaling

Health check ảnh hưởng đến autoscaling và placement:

- Instance mới chỉ được tính vào usable capacity sau readiness.
- Instance unhealthy có thể bị thay thế, làm số replica khởi động tăng đột biến.
- Pod Pending không phải lỗi liveness; thường là scheduler/node capacity issue.
- Readiness fail do dependency toàn cục có thể khiến toàn bộ endpoint bị loại khỏi service.
- Scale-in cần đồng thời drain target và chờ workload hoàn tất.

Dashboard nên phân biệt desired replicas, running replicas, ready replicas, unhealthy replicas và pending replicas. Chỉ số “replica count” không thể hiện trực tiếp năng lực đang phục vụ.

## 16. Bảo mật endpoint health và lifecycle

Health endpoint có thể tiết lộ thông tin hạ tầng nếu public quá rộng:

- Không trả stack trace, version package nhạy cảm, DB host, IP nội bộ hay credential.
- Tách endpoint probe tối giản khỏi endpoint diagnostics chi tiết.
- Giới hạn diagnostics bằng authentication/network policy.
- Dùng identity riêng cho agent/monitor khi cần.
- Không cho caller bên ngoài kích hoạt restart qua health endpoint.
- Log health-check volume hợp lý, tránh tạo noise và chi phí.
- Đảm bảo endpoint probe không có side effect hoặc thay đổi dữ liệu.

Tín hiệu shutdown cũng phải được bảo vệ. Chỉ control plane hoặc runtime đáng tin mới được phép yêu cầu drain/terminate; API quản trị cần authorization và audit.

## 17. Quan sát và vận hành

### 17.1. Metric chính

| Metric | Ý nghĩa |
|---|---|
| Startup duration p50/p95/p99 | Mất bao lâu để workload khởi động |
| Readiness transition count | Instance thường xuyên vào/ra khỏi ready |
| Liveness failure/restart count | Process/container có bị restart bất thường |
| CrashLoopBackOff / OOMKilled | Lỗi lặp hoặc vượt memory limit |
| Unready endpoint count | Số endpoint bị loại khỏi traffic |
| In-flight request at termination | Bao nhiêu request đang xử lý khi shutdown |
| Drain duration | Thời gian hoàn tất graceful shutdown |
| Forced termination count | Số process bị kill khi hết grace period |
| Queue redelivery/visibility timeout | Message được giao lại do worker không ack |
| Dependency error/timeout | Lỗi upstream có thể gây mất readiness |
| Recovery time | Thời gian từ incident tới phục hồi service |

### 17.2. Alert cần có

- Restart count tăng bất thường hoặc crash loop kéo dài.
- Tỷ lệ readiness fail tăng ở nhiều replica cùng lúc.
- Startup duration vượt ngưỡng hoặc deployment không đạt desired ready count.
- Số endpoint healthy giảm xuống dưới mức dự phòng.
- Forced termination hoặc request aborted tăng.
- Queue redelivery/DLQ tăng sau scale-in hoặc deployment.
- Dependency timeout tăng cùng lúc với readiness/liveness failure.
- Recovery time vượt SLO.

Đừng alert cho từng probe timeout đơn lẻ nếu có thể làm nhiễu. Alert nên gắn với tỷ lệ, thời lượng, số replica ảnh hưởng và business SLI.

### 17.3. Runbook điều tra

1. Xác định phạm vi: một process, một node, một zone hay nhiều service.
2. Kiểm tra startup/readiness/liveness event và thời điểm chuyển trạng thái.
3. Xem restart reason, exit code, OOM, probe timeout và log trước shutdown.
4. Kiểm tra CPU, memory, thread, connection pool, disk và network.
5. Kiểm tra dependency timeout/rate limit/failover.
6. Xác định request/message nào đang in-flight hoặc được giao lại.
7. Kiểm tra deploy/config/secret change gần thời điểm xảy ra.
8. Giảm tải hoặc cô lập dependency nếu cần; tránh restart toàn fleet không có kế hoạch.
9. Xác nhận readiness và business SLI trở lại bình thường.
10. Ghi root cause, recovery action và cách ngăn tái diễn.

## 18. Case study: Booking API và notification worker

**Bối cảnh:** nền tảng đặt phòng chạy Booking API trên nhiều replica và Notification worker đọc message từ queue. Booking API cần p95 dưới 300 ms. Worker gửi email qua provider có lúc chậm hoặc trả 429. Khi deployment, hệ thống cần không làm gián đoạn request và không gửi email trùng.

### 18.1. Health design

| Thành phần | Startup | Readiness | Liveness |
|---|---|---|---|
| Booking API | Config, route, schema/client init hoàn tất | Có thể xử lý operation cốt lõi, dependency bắt buộc sẵn sàng theo policy | Event loop và request handler còn tiến triển |
| Notification worker | Load config, queue client và provider policy | Có thể nhận message mới và có concurrency budget | Consumer loop/worker process còn tiến triển |
| Payment integration | Khởi tạo client/credential | Trạng thái dependency riêng; outage không nhất thiết restart API | Không dùng provider availability làm liveness của API |

### 18.2. Shutdown API

1. Platform gửi SIGTERM.
2. API đổi readiness sang DRAINING.
3. Load balancer ngừng gửi request mới và drain persistent connection theo policy.
4. API chờ in-flight request trong grace period.
5. Request hoàn tất transaction/outbox; request quá deadline bị hủy an toàn theo hợp đồng.
6. API flush telemetry, đóng DB pool và thoát.

### 18.3. Shutdown worker

1. Worker đổi readiness để không nhận message mới.
2. Dừng polling/receive.
3. Chờ message đang xử lý trong grace period.
4. Nếu side effect thành công, lưu operation state rồi ack message.
5. Nếu chưa hoàn tất hoặc outcome không rõ, không ack; khi message được giao lại, consumer tra idempotency key/provider reference.
6. Đóng queue client và provider connection rồi thoát.

### 18.4. Khi email provider bị lỗi

- Worker giới hạn retry và tôn trọng Retry-After/backoff.
- Queue giữ backlog; oldest message age được theo dõi.
- Worker không restart liên tục chỉ vì provider trả 429.
- Khi backlog chạm ngưỡng, giảm concurrency hoặc tạm ngừng nhận thêm message.
- Booking API vẫn xác nhận booking nếu nghiệp vụ core đã commit và event được lưu an toàn; notification có thể ở trạng thái pending.
- Khi provider phục hồi, worker tiếp tục xử lý và deduplicate.

### 18.5. Tiêu chí nghiệm thu

- Instance chưa ready không nhận traffic.
- Liveness failure chỉ restart process khi điều kiện có thể phục hồi bằng restart.
- Provider outage không tạo restart storm trên toàn bộ Booking API.
- Rolling deployment không làm giảm ready capacity dưới ngưỡng yêu cầu.
- API drain hoàn tất request trong grace period hoặc trả kết quả xác định.
- Worker không ack message trước khi side effect được lưu an toàn.
- Message redelivery không tạo email trùng ngoài ý muốn.
- Dashboard cho thấy restart, readiness, drain, queue age và dependency health.

## 19. Kiểm thử health, self-healing và shutdown

| Bài test | Cách tạo lỗi trong môi trường kiểm soát | Kết quả mong muốn |
|---|---|---|
| Startup chậm | Tăng thời gian load config/model | Startup probe cho đủ thời gian, chưa nhận traffic |
| Readiness fail | Làm worker mất khả năng nhận việc mới | Endpoint bị loại khỏi routing nhưng không restart vô lý |
| Liveness hang | Tạo deadlock/test endpoint không tiến triển | Runtime restart theo policy, alert được phát |
| Dependency outage | Chặn DB/provider trong test | Không tạo cascading restart; timeout/circuit breaker hoạt động |
| OOM | Giới hạn memory trong test | Restart được phân loại; alert và root cause rõ |
| Node drain | Evict workload có kế hoạch | Pod mới ready, pod cũ drain an toàn |
| Rolling deployment | Thay phiên bản dưới tải | Ready capacity và error budget được giữ |
| SIGTERM khi request chạy | Terminate instance trong test | Request hoàn tất hoặc hủy có kiểm soát |
| SIGTERM khi xử lý message | Dừng worker giữa message | Không ack sớm; redelivery idempotent |
| Grace period hết hạn | Kéo dài task vượt deadline | Forced termination được đo và không gây dữ liệu sai |
| Fleet restart | Mô phỏng nhiều instance mất đồng thời | Jitter/backoff và capacity recovery tránh storm |

Kiểm thử cần có dữ liệu giả lập và dependency sandbox; không gây lỗi chủ động trên production nếu chưa có phạm vi/ủy quyền và kế hoạch rollback.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng một health check cho mọi quyết định | Restart nhầm hoặc route traffic tới instance chưa ready | Tách startup, readiness và liveness |
| Liveness gọi mọi dependency | DB/provider outage làm restart toàn fleet | Liveness tập trung vào progress nội bộ |
| Readiness chỉ trả 200 khi process tồn tại | Instance đang khởi động vẫn nhận traffic | Kiểm tra khả năng nhận workload thực |
| Probe fan-out tới nhiều service mỗi vài giây | Tạo tải và khuếch đại outage | Probe nhẹ, cache health và diagnostics riêng |
| Restart ngay khi timeout ngắn | Crash loop và cold-start storm | Threshold, timeout, backoff và restart budget |
| Chỉ dựa vào container Running | Process có thể không ready hoặc đang treo | Theo dõi readiness và business SLI |
| Shutdown đóng DB pool trước drain | Request in-flight thất bại | Ngừng nhận việc mới, đợi xử lý rồi đóng dependency |
| Worker ack trước commit | Message mất dù side effect chưa hoàn tất | Ack sau durable completion |
| Giả định shutdown hook luôn chạy | Mất dữ liệu khi SIGKILL/hard failure | Thiết kế idempotency, lease và recovery |
| Grace period ngắn hơn request/task | Forced termination thường xuyên | Đo duration và lập shutdown budget |
| Tất cả replica restart cùng lúc | Connection storm và outage kéo dài | Jitter, max unavailable, circuit breaker |
| Health endpoint public tiết lộ dependency | Rò thông tin nội bộ | Tách probe/diagnostics, auth và redaction |

## 21. Checklist review kiến trúc

### Health check

- [ ] Startup, readiness và liveness có mục đích riêng.
- [ ] Startup timeout dựa trên số liệu khởi tạo thực tế.
- [ ] Readiness phản ánh khả năng nhận workload mới và trạng thái DRAINING.
- [ ] Liveness kiểm tra tiến triển nội bộ, không phụ thuộc mù quáng vào mọi dependency.
- [ ] Probe nhanh, không có side effect và không tạo tải lớn.
- [ ] Endpoint diagnostics chi tiết được bảo vệ và không lộ secret.

### Self-healing

- [ ] Restart policy, backoff và restart budget được định nghĩa.
- [ ] Có controller/replica replacement ở đúng failure domain.
- [ ] Desired, running, ready, pending và unhealthy capacity được quan sát riêng.
- [ ] Dependency outage không gây restart storm.
- [ ] Có giới hạn concurrency/connection khi workload được thay thế.
- [ ] Failover zone/region có dữ liệu, write authority và recovery plan rõ.

### Graceful shutdown

- [ ] Termination signal chuyển readiness sang NOT_READY/DRAINING.
- [ ] Routing/load balancer ngừng nhận request mới và drain connection.
- [ ] In-flight request/task có deadline và hành vi hủy rõ.
- [ ] Worker dừng polling và chỉ ack message sau khi kết quả bền vững.
- [ ] Side effect có idempotency và unknown outcome được đối soát.
- [ ] Grace period đủ cho drain/close nhưng không vượt deployment budget.
- [ ] Có fallback khi SIGKILL hoặc hard failure không chạy shutdown hook.

### Vận hành

- [ ] Dashboard theo startup, readiness, liveness, restart, drain và recovery time.
- [ ] Alert theo impact/SLO, không chỉ từng probe failure.
- [ ] Có runbook cho crash loop, dependency outage, node drain và message redelivery.
- [ ] Đã fault-injection test dưới tải đại diện.
- [ ] Có owner cho health policy, restart policy và termination configuration.

## 22. Bài tập thực hành

**Bối cảnh:** một ứng dụng đặt phòng chạy 8 replica trên Kubernetes. Startup cần 40 giây do tải cấu hình và khởi tạo client. API gọi database để xác nhận booking; notification worker xử lý message và gọi email provider. Database có thể failover trong 20 giây. Rolling deployment yêu cầu luôn có ít nhất 6 replica ready. Một số request chạy tới 25 giây; worker có message xử lý trong 45 giây. Platform gửi termination signal và cho grace period 30 giây.

Hãy thiết kế lifecycle:

1. Đề xuất startup/readiness/liveness probe và giải thích điều gì không nên đưa vào liveness.
2. Định nghĩa hành vi readiness khi database failover nhưng process vẫn sống.
3. Tính shutdown budget phù hợp với request 25 giây và worker task 45 giây; chỉ ra điểm chưa đáp ứng trong grace period hiện tại.
4. Thiết kế rolling update để không giảm dưới 6 replica ready.
5. Mô tả cách Booking API chuyển DRAINING, load balancer drain và đóng DB pool.
6. Mô tả cách worker dừng polling, hoàn tất/không ack message và xử lý duplicate.
7. Đề xuất restart backoff/budget để tránh toàn fleet restart khi database outage.
8. Xác định metric/alert cho startup duration, ready replicas, restart, drain time và queue age.
9. Viết fault-injection test cho DB failover, SIGTERM khi request chạy và worker chết sau side effect.
10. Xác định runbook và tiêu chí nghiệm thu theo SLO.

**Gợi ý tự kiểm tra:** Readiness không đồng nghĩa process còn sống; liveness không nên biến outage database thành restart storm. Grace period 30 giây ngắn hơn worker task 45 giây, nên cần drain sớm hơn, hỗ trợ checkpoint/lease hoặc điều chỉnh deadline. Message chỉ được ack sau khi side effect đã bền vững và có thể chống duplicate.

## 23. Ghi nhớ

Health check phải trả lời đúng câu hỏi: startup đã xong chưa, instance có thể nhận việc mới không, và process còn tiến triển không. Startup, readiness và liveness dẫn tới hành động khác nhau; probe sai có thể làm outage nhỏ trở thành restart storm.

Self-healing cần được thiết kế theo failure domain và trạng thái mong muốn, kết hợp restart, reschedule, routing, backoff và giới hạn dependency. Graceful shutdown bắt đầu bằng việc ngừng nhận việc mới, drain request/message đang chạy, lưu kết quả an toàn rồi đóng kết nối trong termination deadline. Thiết kế đáng tin phải tính cả hard failure khi shutdown hook không chạy, dùng idempotency cho công việc có thể giao lại, và kiểm chứng bằng fault injection, metric, alert và runbook.
