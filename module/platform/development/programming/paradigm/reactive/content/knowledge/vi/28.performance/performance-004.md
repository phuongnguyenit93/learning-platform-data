# Nút thắt ở luồng thực thi, kết nối, CPU và dịch vụ phụ thuộc

Một ứng dụng reactive có thể dùng ít thread hơn ứng dụng đồng bộ nhưng vẫn chậm khi một tài nguyên quan trọng bị bão hòa. Request có thể chờ event loop rảnh, chờ worker thread, chờ connection trong pool, chờ CPU xử lý hoặc chờ dịch vụ phụ thuộc phản hồi. Nếu chỉ nhìn thời gian của controller hoặc tăng số thread ngay khi latency cao, ta có thể che triệu chứng mà không tìm được nguyên nhân.

Chẩn đoán bottleneck cần lần theo toàn bộ đường đi của request, từ lúc nhận vào đến khi trả response. Hãy kết hợp latency và throughput với số request đang chạy, queue depth, thread/scheduler, connection pool, CPU, GC và metric của từng dependency. Mục tiêu là xác định tài nguyên đầu tiên không đáp ứng tốc độ công việc đến, rồi thay đổi đúng tầng đó và đo lại.

## 1. Nhận diện triệu chứng trước khi chọn công cụ

Các bottleneck khác nhau có thể tạo ra cùng triệu chứng bên ngoài: p95/p99 tăng, request timeout hoặc throughput không tăng dù offered load tiếp tục tăng. Bảng sau giúp chọn hướng điều tra ban đầu:

| Triệu chứng | Nghi ngờ chính | Bằng chứng cần tìm |
| --- | --- | --- |
| Nhiều route chậm cùng lúc | CPU, event loop hoặc hạ tầng dùng chung | CPU/throttling, event-loop lag, GC pause |
| Một số request chậm đúng lúc gọi dependency | Dịch vụ ngoài, HTTP connection pool hoặc timeout | Span dependency, pending acquire, latency/error của client |
| Thread tăng cao, nhiều task xếp hàng | Blocking hoặc concurrency quá lớn | Thread dump, scheduler queue, blocked/waiting stack |
| Request chờ lâu trước khi query bắt đầu | Connection pool hoặc hàng đợi ở client | Pending acquire, acquire latency, pool active/idle |
| CPU thấp nhưng latency và in-flight tăng | I/O chậm, pool cạn hoặc queue chờ | Dependency latency, pending connections, lock wait |
| CPU cao, throughput đứng yên, p99 tăng | CPU saturation, GC hoặc serialization | CPU profile, allocation, GC pause, flame graph |
| Chỉ chậm sau thời gian dài | Leak, queue tích lũy, connection không được trả | Heap trend, connection usage, pending tasks, soak metrics |

Đây là giả thuyết ban đầu, không phải kết luận. CPU thấp không chứng minh ứng dụng khỏe; CPU cao cũng không tự chứng minh code Java là thủ phạm vì container có thể bị throttling hoặc tiến trình khác đang tranh CPU.

## 2. Lần theo đường đi của một request

Trước khi đọc từng metric, xác định các chặng request đi qua. Một request điển hình có thể gồm gateway, WebFlux handler, service, scheduler, HTTP client, database và một dịch vụ ngoài khác.

    Client
      |
      v
    Gateway / ingress
      |
      v
    WebFlux event loop
      |
      v
    Application pipeline
      |                 \
      v                  v
    R2DBC pool         HTTP client pool
      |                  |
      v                  v
    Database          Dependent service
      \                  /
       \                /
        v              v
         Response composition
                  |
                  v
                Client

Đo latency ở từng ranh giới để phân biệt thời gian xử lý nội bộ với thời gian chờ tài nguyên. Distributed tracing giúp nhìn các chặng trong cùng trace; metric tổng hợp giúp nhận ra xu hướng qua nhiều request. Khi không có tracing, correlation ID cùng log thời điểm bắt đầu/kết thúc ở các adapter vẫn có thể hỗ trợ khoanh vùng, nhưng không nên tạo log đồng bộ dày đặc trên hot path.

Cần phân biệt ít nhất ba khoảng thời gian:

- Queue/acquire time: thời gian chờ thread, connection hoặc slot concurrency.
- Service time: thời gian tài nguyên thực sự xử lý công việc.
- End-to-end latency: thời gian caller chờ toàn bộ request hoàn tất.

Một query mất 30 ms nhưng phải chờ connection 700 ms là bottleneck khác với query mất 700 ms sau khi đã lấy connection.

## 3. Phân biệt event-loop starvation với CPU saturation

WebFlux thường chạy I/O trên một số event-loop thread tương đối nhỏ. Event loop cần callback hoàn tất nhanh để tiếp tục xử lý connection khác. Nếu một callback thực hiện JDBC đồng bộ, gọi HTTP blocking, chờ lock hoặc gọi block(), thread đó bị giữ lại. Một event loop bị chặn có thể làm nhiều request không liên quan cùng chậm.

Ví dụ không phù hợp:

    @GetMapping("/{id}")
    Mono<Customer> find(@PathVariable String id) {
        Customer customer = jdbcRepository.findById(id); // Blocking trên event loop.
        return Mono.just(customer);
    }

Nếu chưa thể thay JDBC bằng driver reactive, cô lập lời gọi blocking:

    Mono<Customer> findBlocking(String id) {
        return Mono.fromCallable(() -> jdbcRepository.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/{id}")
    Mono<Customer> find(@PathVariable String id) {
        return customerService.findBlocking(id);
    }

boundedElastic dành cho công việc blocking có giới hạn. Nó không làm JDBC trở thành non-blocking; nó chỉ chuyển thời gian chờ sang worker thread để event loop không bị giữ. Cần giới hạn concurrency và theo dõi queue/thread của scheduler, vì đưa quá nhiều blocking task vào boundedElastic vẫn có thể tạo backlog.

CPU-bound work có đặc điểm khác. Nếu callback thực hiện mã hóa, tính toán, nén hoặc biến đổi dữ liệu nặng, chuyển sang boundedElastic không phải cách giải quyết mặc định. Có thể dùng parallel scheduler hoặc scheduler riêng có giới hạn để cô lập công việc CPU, nhưng tổng lượng CPU vẫn không tăng. Khi CPU đã bão hòa, thêm thread thường làm tăng context switching và cạnh tranh cache.

## 4. Đọc thread dump và scheduler metrics

Khi latency tăng, lấy thread dump trong đúng khoảng thời gian sự cố và kiểm tra stack của các thread quan trọng. Tìm các dấu hiệu:

- Event-loop thread đang ở JDBC driver, socket read đồng bộ, Thread.sleep, monitor enter hoặc một lời gọi blocking.
- Nhiều worker cùng chờ một lock hoặc chờ tài nguyên dùng chung.
- boundedElastic có nhiều worker bận lâu, queue tăng hoặc task bị từ chối.
- parallel worker đang thực hiện phép tính CPU kéo dài thay vì trả quyền điều khiển nhanh.
- Thread tăng liên tục qua thời gian, gợi ý thread leak hoặc tạo scheduler không được dispose.

Tên thread phụ thuộc cấu hình Reactor Netty và scheduler. Đừng chỉ tìm một chuỗi tên cố định; đọc stack trace và đối chiếu loại scheduler đang dùng. Một thread ở trạng thái WAITING không tự động là lỗi: worker nhàn rỗi trong pool thường chờ công việc. Cần xem số lượng thread, stack, thời gian tồn tại và tương quan với latency.

Các metric hữu ích gồm số worker active, số task đang queued, số task bị reject, thời gian chờ task trước khi bắt đầu và thời gian thực thi. Nếu phiên bản Reactor/Spring không xuất metric scheduler mặc định theo cách cần thiết, có thể instrument scheduler bằng cơ chế Micrometer phù hợp hoặc thêm metric tại ranh giới submit/execute. Tránh gắn tag có cardinality cao như request ID vào metric.

Một bài test với BlockHound có thể phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking trong môi trường test. BlockHound hữu ích để bắt lỗi sớm, nhưng không thay thế profiling và không phát hiện mọi dạng chờ tài nguyên hoặc blocking nằm ngoài các integration mà nó hỗ trợ.

## 5. Phân biệt CPU saturation, GC và CPU throttling

CPU saturation thường thể hiện bằng CPU usage cao kéo dài, throughput đạt plateau và latency tăng khi offered load tiếp tục tăng. Tuy nhiên, cần phân biệt:

- Process CPU cao: ứng dụng đang dùng nhiều CPU; tìm method tiêu tốn CPU bằng profiler.
- Container CPU throttling: container chạm quota CPU, dù biểu đồ host CPU tổng thể có thể chưa cao.
- GC pressure: allocation rate cao hoặc heap thiếu headroom khiến GC chạy thường xuyên, pause dài hoặc CPU dành nhiều cho collector.
- CPU cạnh tranh: tiến trình khác trên cùng node làm giảm CPU mà ứng dụng thực sự nhận được.

Các nguồn tiêu tốn CPU phổ biến trong ứng dụng reactive gồm JSON encode/decode, mapping object lớn, validation phức tạp, compression, TLS, regex, logging payload, serialization và các phép tính lặp trong map/filter.

Dùng Java Flight Recorder (JFR) hoặc async-profiler để lấy CPU profile trong lúc tái hiện tải. Flame graph cho biết stack nào chiếm phần lớn CPU; allocation profile giúp tìm object được tạo quá nhiều. Nếu GC pause tăng, đối chiếu allocation rate, heap occupancy, số lần GC và thời gian dừng. Không kết luận chỉ từ một ảnh chụp CPU tại một thời điểm ngắn.

Ví dụ một phép biến đổi CPU nặng nên được tách rõ khỏi I/O:

    Mono<Report> report = source
        .publishOn(Schedulers.parallel())
        .map(this::computeExpensiveReport);

Đoạn trên chuyển phần downstream của publishOn sang scheduler phù hợp với công việc CPU. Nó không làm phép tính chạy nhanh hơn một cách thần kỳ. Chỉ nên thêm scheduler boundary sau khi profile xác nhận công việc CPU đang chiếm event-loop hoặc làm lẫn lộn loại workload. Mỗi boundary cũng có chi phí scheduling và queue riêng.

## 6. Chẩn đoán connection pool của database

Một request có thể subscribe thành công và tới repository nhưng vẫn chờ lâu trước khi database nhận query vì không lấy được connection. Với R2DBC Pool, theo dõi các metric tương ứng với:

- Acquired/allocated: số connection đang được cấp phát hoặc sử dụng.
- Idle: số connection sẵn sàng.
- Pending acquire: số yêu cầu đang chờ connection.
- Acquire duration: thời gian từ lúc yêu cầu tới lúc lấy được connection.
- Acquire timeout hoặc pending limit exceeded: số lần không lấy được connection trong giới hạn.
- Connection creation/validation: thời gian mở hoặc kiểm tra connection.

Tên metric chính xác phụ thuộc phiên bản pool và cấu hình Micrometer. Dùng metric được exporter công bố trong ứng dụng thay vì giả định tên cố định.

Nếu active connection luôn gần max size, idle gần 0 và pending acquire tăng, pool có thể là điểm nghẽn. Nhưng tăng max size không phải lúc nào cũng đúng: database có giới hạn connection, query có thể đang giữ connection quá lâu hoặc transaction mở qua một lời gọi mạng. Hãy kiểm tra query duration, lock wait, transaction duration và khả năng database xử lý thêm connection trước khi tăng pool.

Một số nguyên nhân làm connection bị giữ lâu:

- Query chậm hoặc thiếu index.
- Transaction bao trùm quá nhiều bước.
- Gọi dịch vụ HTTP hoặc chờ event trong lúc transaction còn mở.
- Cursor/result stream không được tiêu thụ hoặc đóng đúng cách.
- Publisher không hoàn tất và giữ subscription/tài nguyên.
- Nguồn bị cancel nhưng cleanup của driver/adapter không giải phóng connection đúng hạn.

Với query streaming, connection có thể được giữ trong suốt thời gian downstream tiêu thụ dữ liệu. Đây có thể là chủ ý; hãy giới hạn thời gian sống, số dòng và tốc độ consumer. Không dùng collectList trên kết quả lớn chỉ để thuận tiện nếu không cần giữ toàn bộ dữ liệu trong bộ nhớ.

## 7. Chẩn đoán HTTP connection pool và WebClient

WebClient dựa trên Reactor Netty thường sử dụng connection pool. Khi pool đạt giới hạn, request mới có thể chờ pending acquire trước khi được gửi đi. Nếu chỉ đo response time tổng thể, thời gian chờ connection dễ bị nhầm với latency của dịch vụ đích.

Theo dõi các tín hiệu:

| Tín hiệu | Cách diễn giải |
| --- | --- |
| Active connections gần max | Pool đang sử dụng gần hết connection được phép |
| Pending acquire tăng | Request đang chờ connection |
| Acquire timeout tăng | Không lấy được connection trong thời hạn |
| Remote response time tăng, acquire time ổn định | Dependency có thể đang chậm |
| Acquire time tăng nhưng remote time ổn định | Pool size, connection lifecycle hoặc concurrency có thể là vấn đề |
| Connection churn cao | Connection bị đóng/tạo lại thường xuyên, có thể do idle/lifetime/TLS |

Cấu hình pool cần phù hợp với năng lực dịch vụ đích và giới hạn file descriptor/network. Tăng max connections có thể giảm pending acquire nhưng đẩy quá tải sang dependency. Kiểm tra keep-alive, connection lifetime, idle timeout, DNS, TLS handshake và số request đồng thời trước khi thay đổi.

Đối với dịch vụ có giới hạn connection thấp, dùng pool hoặc bulkhead riêng để một dependency không chiếm hết connection của dependency khác. Đặt timeout cho pending acquire và response theo ngân sách latency của request.

## 8. Xác định dịch vụ phụ thuộc đang làm chậm request

Một request có thể gọi nhiều dependency theo chuỗi hoặc song song. Nếu dependency A có p99 tăng, các request chờ A sẽ giữ in-flight state và có thể chiếm connection, scheduler slot hoặc concurrency slot trong ứng dụng.

Distributed tracing nên tạo span riêng cho từng lời gọi dependency. Đối chiếu:

- Thời gian chờ trước khi gửi request.
- Thời gian gửi/nhận ở HTTP client.
- Thời gian xử lý phía dependency nếu có trace liên kết.
- Status code, timeout, reset connection và retry.
- Kích thước request/response nếu có ảnh hưởng tới serialization hoặc network.

Nếu span ứng dụng cho thấy service mất 900 ms nhưng các bước nội bộ chỉ tốn 50 ms, hãy tìm khoảng chờ còn lại: pool acquire, network, retry delay hoặc dependency. Nếu dependency server báo xử lý 30 ms nhưng client thấy 700 ms, có thể phần chờ nằm ở gateway, network, connection setup hoặc queue trước server.

Đo riêng từng dependency theo route và operation. Không gộp tất cả external calls thành một metric chung vì một dịch vụ chậm có thể bị che bởi nhiều dịch vụ nhanh.

## 9. Fan-out, retry và sự khuếch đại tải

Một request đầu vào có thể tạo nhiều lời gọi downstream. Nếu mỗi request gọi 5 dịch vụ, 200 request/giây có thể tạo khoảng 1.000 downstream calls/giây trước khi tính retry. Khi một dependency lỗi, retry có thể làm tải tăng đúng lúc dependency yếu nhất.

Ví dụ:

    Mono<OrderView> view = Mono.zip(
        customerClient.find(customerId),
        paymentClient.status(orderId),
        inventoryClient.check(orderId),
        shippingClient.estimate(orderId)
    ).map(this::toView);

Các nhánh độc lập có thể được subscribe đồng thời. Tuy nhiên, thời gian hoàn tất của zip phụ thuộc vào nhánh chậm nhất; một nhánh lỗi có thể làm nhóm thất bại. Khi fan-out tăng, xác suất một nhánh có tail latency cao cũng tăng.

Để bảo vệ hệ thống:

- Đặt timeout riêng theo dependency và deadline tổng thể cho request.
- Giới hạn concurrency của flatMap theo năng lực dependency.
- Dùng bulkhead để giới hạn số request đồng thời tới một dependency.
- Retry có giới hạn, backoff và jitter; chỉ retry lỗi có thể phục hồi.
- Tránh retry thao tác ghi không idempotent nếu không có idempotency key.
- Dùng circuit breaker để ngừng gửi request khi dependency liên tục thất bại.
- Cung cấp fallback có ngữ nghĩa rõ ràng nếu nghiệp vụ cho phép dữ liệu một phần.

Không đặt retry quá rộng sau một nhóm zip nếu điều đó khiến các nhánh đã thành công bị gọi lại. Retry nên ở sát dependency có thể phục hồi để giảm fan-out lặp.

## 10. Phân biệt queueing với thời gian xử lý

Khi arrival rate cao hơn completion rate, request tích lũy trong một hoặc nhiều hàng đợi. Queue có thể nằm ở gateway, event loop, scheduler, flatMap, HTTP pool, database pool hoặc chính dịch vụ phụ thuộc. Queue depth tăng liên tục là dấu hiệu hệ thống chưa đạt trạng thái ổn định ở mức tải đó.

Little's Law mô tả quan hệ ở trạng thái ổn định:

    L = λ × W

Trong đó L là số công việc trung bình trong hệ thống, λ là throughput trung bình và W là thời gian lưu lại trung bình. Nếu throughput không tăng nhưng in-flight requests tăng, latency thường tăng theo. Công thức dùng giá trị trung bình ở trạng thái ổn định; không thay p99 vào để suy ra số request chính xác.

Hãy đo queue ở từng tầng, không chỉ số request đang chạy trong controller. Nếu pending acquire của pool tăng trong khi scheduler queue thấp, pool là ứng viên rõ hơn. Nếu event-loop lag tăng và nhiều callback bị trì hoãn, kiểm tra blocking hoặc CPU. Nếu queue ở client ổn định nhưng span remote tăng, dependency có thể là điểm nghẽn.

## 11. Dùng metric và tracing để liên kết các tầng

Một bộ metric tối thiểu cho mỗi service nên gồm:

| Nhóm | Metric |
| --- | --- |
| Request | Rate, success/error/timeout/cancel, p50/p95/p99 |
| Concurrency | In-flight request, active inner publisher, bulkhead usage |
| Scheduler | Active worker, queued task, rejected task, execution delay |
| Database pool | Active, idle, pending acquire, acquire latency, timeout |
| HTTP pool | Active, idle, pending acquire, acquire timeout |
| Dependency | Per-service latency, status/error, retry count, circuit state |
| JVM/container | CPU, throttling, heap, allocation, GC pause, thread count |
| Queue/buffer | Queue depth, buffer size, dropped/overflow count |

Dùng OpenTelemetry hoặc tracing tương đương để nối span của request qua service và dependency. Dùng Micrometer để xuất metric theo thời gian. Trace trả lời request cụ thể đã chờ ở đâu; metric trả lời vấn đề có phổ biến và kéo dài hay không.

Tag metric bằng các chiều có cardinality thấp như route template, operation, dependency name và outcome. Tránh gắn ID người dùng, order ID hoặc URL động làm tag. Với trace/log, tuân thủ chính sách dữ liệu nhạy cảm; không ghi token, payload bí mật hoặc thông tin cá nhân không cần thiết.

## 12. Ví dụ đo thời gian một lời gọi dependency

Có thể bọc client bằng timer nếu API cho phép tách việc lấy connection khỏi thời gian response. Nếu client không cung cấp ranh giới acquire tường minh, dùng metric pool do client export và span HTTP để đối chiếu.

    Mono<PartnerResponse> callPartner(String id) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(meterRegistry);
            return partnerClient.fetch(id)
                .doFinally(signal -> {
                    sample.stop(partnerResponseTimer);
                    recordOutcome(signal);
                });
        });
    }

Timer trên đo thời gian toàn bộ publisher của lời gọi partner, có thể bao gồm acquire, network và decode tùy vị trí instrument. Không đặt tên metric này là remote processing time nếu không đo được thời gian xử lý bên trong server đích. Hãy ghi đúng phạm vi metric để dashboard không dẫn tới kết luận sai.

Nếu cần đo thời gian từng bước, instrument ở adapter có quyền quan sát bước đó hoặc dùng tracing instrumentation của HTTP client. Đừng tạo timer quanh publisher assembly rồi tưởng rằng đã đo thời gian thực thi; đặt sample trong defer để mỗi subscription có một lần đo riêng.

## 13. Quy trình điều tra từ triệu chứng tới nguyên nhân

Khi một endpoint chậm, thực hiện theo trình tự:

1. Xác nhận phạm vi: route nào, region/instance nào, thời điểm nào, p95/p99 và error rate tăng từ khi nào.
2. Kiểm tra load: offered RPS, successful RPS, in-flight và queue depth có tăng không; load generator có đủ năng lực không.
3. Đọc trace của request chậm: span nào chiếm thời gian lớn nhất; có khoảng chờ không được instrument không.
4. Kiểm tra thread/scheduler: event-loop lag, blocking stack, active worker, queue và task rejection.
5. Kiểm tra CPU/JVM: process CPU, container throttling, allocation, GC và CPU flame graph.
6. Kiểm tra connection pool: active/idle/pending, acquire duration, timeout và connection lifecycle.
7. Kiểm tra database: query latency, execution plan, lock wait, transaction duration và database CPU.
8. Kiểm tra dependency: per-service p95/p99, error, retry, timeout, circuit breaker và network.
9. Xác định bottleneck đầu tiên theo thời gian và bằng chứng, không chỉ thành phần có metric cao nhất.
10. Thay đổi một yếu tố có giả thuyết rõ, chạy lại cùng workload và so sánh throughput, latency, error cùng tài nguyên.

Bằng cách thay đổi từng yếu tố và giữ workload ổn định, ta có thể xác định liệu cải thiện đến từ nguyên nhân dự đoán hay chỉ là dao động tự nhiên.

## 14. Ví dụ: CPU thấp nhưng request vẫn chậm

Giả sử một API có p95 tăng từ 120 ms lên 1,4 giây, CPU chỉ 25%, database query duration khoảng 40 ms. Thread dump không cho thấy event loop bị block. Metric R2DBC cho thấy active connection bằng max size, idle bằng 0 và pending acquire tăng.

Giả thuyết hợp lý là request chờ connection trước khi query bắt đầu. Tiếp theo cần xem transaction duration và query/lock: nếu connection bị giữ trong lúc service gọi HTTP bên ngoài, sửa ranh giới transaction có thể giải phóng pool mà không cần tăng max size. Nếu query thực sự chạy lâu, tối ưu index/plan hoặc giảm dữ liệu đọc sẽ hiệu quả hơn tăng connection.

Ví dụ này cho thấy CPU thấp không loại trừ bottleneck. Tài nguyên đang chờ có thể là connection chứ không phải CPU.

## 15. Ví dụ: CPU cao và throughput không tăng

Giả sử tăng offered load từ 300 lên 500 RPS nhưng successful throughput chỉ tăng từ 280 lên 290 RPS; p99 tăng mạnh, CPU container chạm quota và GC pause tăng. CPU profile cho thấy JSON serialization và mapping chiếm phần lớn thời gian.

Tăng boundedElastic hoặc connection pool sẽ không giải quyết nguyên nhân. Hãy xem kích thước payload, số lần serialize, object allocation, cấu hình codec và khả năng giảm trường dữ liệu. Nếu container bị throttling, xem xét quota và phân bổ CPU sau khi đã tối ưu code. Chạy lại cùng workload để xác minh CPU/request giảm và tail latency cải thiện.

## 16. Ví dụ: một dependency chậm làm nghẽn toàn bộ request

Giả sử một request gọi customer, payment và shipping bằng zip. Customer và payment hoàn tất trong 50 ms, shipping mất 1,2 giây. Vì zip chờ tất cả nhánh, response cũng chậm khoảng 1,2 giây cộng overhead. Nếu nhiều request đồng thời chờ shipping, in-flight tăng và connection pool của HTTP client có thể đầy.

Đo span riêng của shipping, acquire latency của pool và error/timeout. Sau đó đặt timeout phù hợp, giới hạn concurrency tới shipping và áp dụng fallback chỉ khi nghiệp vụ cho phép. Circuit breaker có thể ngăn tiếp tục gửi tải vào dependency đang lỗi. Không dùng fallback giả thành công nếu dữ liệu shipping là bắt buộc để thực hiện nghiệp vụ.

## 17. Biện pháp khắc phục theo loại bottleneck

| Bottleneck được xác nhận | Biện pháp có thể thử | Điều cần đo lại |
| --- | --- | --- |
| Blocking trên event loop | Thay bằng API reactive hoặc cô lập blocking ở boundedElastic | Event-loop lag, scheduler queue, latency |
| CPU-bound callback | Profile và tối ưu thuật toán/serialization; tách scheduler CPU khi phù hợp | CPU/request, throughput, p99 |
| Database pool pending cao | Rút ngắn transaction, tối ưu query, xử lý leak; cân nhắc pool size sau khi đánh giá DB | Acquire latency, pending, query/lock |
| HTTP pool pending cao | Giới hạn concurrency, tối ưu lifecycle connection, tách pool theo dependency | Acquire time, remote time, active/pending |
| Dependency chậm | Timeout, bulkhead, circuit breaker, retry có kiểm soát, fallback hợp lệ | Dependency p95/p99, error, retry, queue |
| Queue tăng liên tục | Giảm arrival/concurrency, backpressure/buffer policy, tăng capacity đúng tầng | Queue depth, dropped work, throughput |
| GC/allocation cao | Giảm allocation, payload, buffer và object trung gian | Allocation rate, GC pause, heap trend |

Không áp dụng tất cả biện pháp cùng lúc. Mỗi thay đổi nên có giả thuyết, metric kỳ vọng và tiêu chí rollback. Ví dụ tăng pool size chỉ hợp lý khi database còn khả năng nhận thêm connection và pending acquire thực sự là nút thắt; nếu database đã bão hòa, tăng pool có thể làm query chậm hơn.

## 18. Những cách xử lý dễ làm tình hình xấu hơn

- Tăng số thread khi CPU đã bão hòa: tạo thêm context switching và tranh chấp CPU.
- Tăng connection pool mà không kiểm tra giới hạn database: chuyển hàng đợi sang database và tăng contention.
- Retry không giới hạn hoặc retry đồng loạt: khuếch đại tải khi dependency đang suy yếu.
- Dùng buffer không giới hạn: biến quá tải thành heap growth và GC pressure.
- Chuyển mọi thao tác sang boundedElastic: che giấu blocking và tạo một hàng đợi lớn khó kiểm soát.
- Đặt timeout quá ngắn: tạo lỗi giả và retry không cần thiết; quá dài lại giữ tài nguyên lâu.
- Gộp metric mọi dependency: che khuất dịch vụ chậm nhất.
- Chỉ xem average latency: bỏ qua tail latency mà người dùng cảm nhận.
- Tối ưu code trước khi có profile: có thể sửa phần không phải bottleneck.
- Đo trong khi load generator bị quá tải: kết luận sai về capacity của server.

## 19. Checklist kết luận bottleneck

Trước khi báo cáo nguyên nhân, hãy trả lời được:

- Request chậm ở chặng nào và số liệu nào chứng minh?
- Thời gian là queue/acquire, service time hay network/dependency wait?
- Event loop có bị blocking hoặc scheduler có backlog không?
- CPU thực sự bận, bị throttling hay đang chờ I/O?
- Connection pool có pending acquire; database/HTTP client có còn headroom không?
- Dependency nào có latency/error/retry tăng đồng thời?
- Throughput có đạt plateau trong khi in-flight/queue tiếp tục tăng không?
- Thay đổi đã kiểm chứng bằng cùng workload và có cải thiện p95/p99, error rate không?

## 20. Áp dụng vào vận hành ứng dụng Reactor

Một ứng dụng reactive không loại bỏ giới hạn tài nguyên; nó làm rõ hơn cách công việc được điều phối qua subscription, scheduler và demand. Event loop có thể bị chặn, boundedElastic có thể đầy queue, CPU có thể bão hòa, connection pool có thể hết slot và dịch vụ phụ thuộc có thể trở thành điểm chậm nhất. Vì vậy, chẩn đoán phải đi theo request và đối chiếu các tầng thay vì quy mọi vấn đề về số thread.

Hãy dùng tracing để tìm chặng chờ, metric để xác định xu hướng, thread dump/profiler để hiểu execution, pool metrics để thấy thời gian acquire và metric dependency để đo phần bên ngoài. Sau khi xác nhận bottleneck, thay đổi đúng tài nguyên hoặc ranh giới xử lý, rồi chạy lại workload tương đương. Cách làm dựa trên bằng chứng giúp giữ throughput ổn định, kiểm soát tail latency và tránh đẩy quá tải từ một tầng sang tầng khác trong hệ sinh thái Java reactive.
