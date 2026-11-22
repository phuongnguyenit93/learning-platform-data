# Cô lập tải theo khách hàng hoặc nhóm nghiệp vụ trong Microservices

Trong một nền tảng microservices, nhiều khách hàng (tenant), đối tác hoặc loại công việc cùng sử dụng API Gateway, CPU, memory, worker pool, cơ sở dữ liệu, cache và message broker. Khi một khách hàng tạo lượng request đột biến hoặc một nhóm tác vụ báo cáo chạy quá nặng, toàn bộ tài nguyên chung có thể bị chiếm dụng. Những khách hàng hoặc nghiệp vụ khác bị chậm, timeout, thậm chí mất dịch vụ dù bản thân họ không tăng tải.

Hiện tượng này gọi là **noisy neighbor**. **Cô lập tải (workload isolation)** là kỹ thuật phân bổ, giới hạn, xếp lịch và giám sát tài nguyên theo các ranh giới như tenant, account, gói dịch vụ hoặc nhóm nghiệp vụ. Mục đích là giảm phạm vi ảnh hưởng (blast radius), giữ SLO cho nhóm không gây quá tải và cho phép nền tảng sử dụng hiệu quả phần tài nguyên đang rảnh.

Ví dụ một hệ thống SaaS bán hàng có ba nhóm hoạt động:

- **Checkout/Payment:** giao dịch trực tuyến cần tính đúng và độ trễ thấp.
- **Search/Catalog:** lưu lượng truy vấn lớn, một số phần có thể dùng cache hoặc hạ cấp có kiểm soát.
- **Report/Export:** truy vấn nặng, có thể được xếp hàng và xử lý bất đồng bộ.

Đồng thời, khách hàng A đang mở chiến dịch flash sale, khách hàng B vẫn bán hàng bình thường và khách hàng C đang xuất báo cáo. Nếu cả ba đi qua một hàng đợi hoặc connection pool không có quota, sự bùng nổ của A/C có thể làm B không checkout được.

Bài này trình bày cách nhận diện điểm cạnh tranh tài nguyên, thiết kế quota/rate limit/bulkhead, chia hàng đợi và tài nguyên dữ liệu, kết hợp autoscaling và quan sát để chứng minh khả năng cô lập trong môi trường phân tán.

## 1. Khả năng mở rộng và khả năng cô lập là hai yêu cầu khác nhau

**Scalability** trả lời: có thể tăng throughput hoặc capacity khi traffic tăng không?

**Workload isolation** trả lời: khi một nhóm khách hàng hoặc nghiệp vụ sử dụng bất thường, các nhóm còn lại bị ảnh hưởng tới đâu?

~~~text
Tenant A: 500 requests/s (flash sale)
Tenant B:  20 requests/s
Tenant C:  10 requests/s
             |
             v
        API Gateway
             |
             v
    Shared worker pool
       100 workers
             |
             v
     Shared DB pool
       30 connections
~~~

Nếu A chiếm phần lớn workers và DB connections, B/C có thể timeout dù chỉ gửi ít request. HPA tăng Pod chưa chắc giúp được: thêm replica có thể tạo thêm hàng trăm kết nối tới database đang quá tải. Một hệ thống có throughput tổng cao vẫn có thể phân phối tài nguyên thiếu công bằng.

**Mục tiêu kỹ thuật** là giữ các bất biến có thể đo: trong lúc tenant A phát tải vượt quota, tỷ lệ lỗi và p95 latency của B/C vẫn nằm trong ngưỡng được cam kết; nhóm báo cáo không chiếm hết năng lực thanh toán; khi overload, nền tảng từ chối hoặc trì hoãn công việc có chủ đích thay vì treo tất cả.

## 2. Chọn đơn vị cô lập

Có hai cách chia thường gặp, đôi khi phải dùng đồng thời.

| Góc phân chia | Ví dụ | Mục đích |
| --- | --- | --- |
| Theo tenant | Merchant A, B, C | Tránh một khách hàng làm ảnh hưởng khách hàng khác |
| Theo account/API client | Đối tác thanh toán hoặc đơn vị tích hợp | Áp quota theo hợp đồng và hạn mức bên ngoài |
| Theo gói dịch vụ | Standard, Premium | Phân phối ngân sách theo quyền lợi/SLO |
| Theo nghiệp vụ | Checkout, Search, Reporting | Bảo vệ chức năng quan trọng khỏi việc ít quan trọng hơn |
| Theo workload | HTTP realtime, import, backfill, consumer | Phân biệt deadline và tài nguyên cần dùng |
| Theo vùng | Khu vực, region, shard | Hạn chế phạm vi lỗi và quản lý capacity |
| Theo tenant lớn | Dedicated database/deployment | Cô lập mạnh cho nhóm có nhu cầu đặc biệt |

Một tenant có thể dùng cả checkout và reporting; một nhóm nghiệp vụ có thể phục vụ hàng nghìn tenant. Bởi vậy mô hình thực tế thường có **ma trận quota**:

~~~text
                 Tenant A  Tenant B  Tenant C
Checkout           A-C       B-C       C-C
Search             A-S       B-S       C-S
Export             A-E       B-E       C-E

Mỗi ô có rate/concurrency budget.
Mỗi hàng còn có tổng ngân sách của lane.
Toàn nền tảng có global safety cap.
~~~

Đối với một quy trình thanh toán, định danh tenant phải được lấy từ principal đã xác thực và kiểm tra quyền ở backend. Không tin ngay header tenant_id tùy ý do client cung cấp, vì kẻ tấn công có thể tự xưng tenant premium để vượt quota hoặc truy cập nhầm dữ liệu.

**Cô lập tài nguyên không thay thế phân quyền.** Tenant A có ngân sách cao hơn vẫn không được xem dữ liệu của tenant B.

## 3. Noisy neighbor xuất hiện ở đâu?

Vẽ sơ đồ đường đi của request:

~~~text
Client / Partner
      |
      v
API Gateway         <- Authentication + per-tenant limit
      |
      v
Service ingress     <- Bounded queue / admission
      |
      v
Business handler    <- CPU, threads, memory, locks
      |
      +---> Database    <- Connections, I/O, locks
      +---> Cache       <- Memory, eviction
      +---> Broker      <- Queue, partition, lag
      +---> External API <- Rate/quota của vendor
~~~

Các dạng cạnh tranh quan trọng:

**CPU:** một nhóm thực hiện nhiều phép tính, serialization hoặc mã hóa khiến latency của nhóm khác tăng; nếu container bị CPU throttling, p99 có thể tăng dù request rate không quá lớn.

**Memory:** nhiều payload lớn hoặc request in-flight làm heap/off-heap tăng, GC kéo dài hoặc Pod OOMKilled. Một container restart có thể làm mất request đang chạy của mọi tenant trên Pod đó.

**Thread pool:** tác vụ chờ network hoặc DB giữ hết threads; CPU usage có thể còn thấp, nhưng request mới không lấy được worker.

**DB connection pool:** một nhóm mở giao dịch dài, query nặng hoặc giữ connection; nhóm khác bị timeout khi acquire.

**Database engine:** dù tách pool, các nhóm vẫn có thể tranh lock, I/O, buffer cache, CPU và giới hạn connection của cùng một DB cluster.

**Broker:** một tenant publish hàng triệu event lên cùng queue hoặc một hot Kafka partition, khiến event của tenant khác chờ lâu.

**Cache:** cache pollution do dữ liệu của một tenant làm evict hot keys của tenant khác; cache miss kéo thêm tải xuống DB.

**External API:** một đối tác gọi quá nhiều khiến toàn hệ thống hết quota của payment provider, SMS gateway hoặc API bên thứ ba.

**Disk/network:** export lớn hoặc backup chạy cùng đường với API trực tuyến tạo I/O saturation.

Chỉ thêm một rate limiter ở API Gateway thường không đủ vì **một request cũng có thể rất đắt**. Cần nhận diện bottleneck từ metrics và đặt ranh giới ngay trước tài nguyên khan hiếm.

## 4. Các lớp bảo vệ từ ngoài vào trong

Một kiến trúc minh họa:

~~~text
                 Internet / Partners
                         |
                         v
                 API Gateway / WAF
                  Auth, global quota
                  per-client rate limit
                         |
                         v
                Workload admission
                 +-------+-------+
                 |       |       |
               Checkout Search  Export
               lane     lane    lane
                 |       |       |
           Bounded queues / semaphores
                 |       |       |
                 v       v       v
           Service pods / worker pools
                 |       |       |
                 +-------+-------+
                         |
                 Shared dependencies
                DB / Broker / Cache
                         |
                 Downstream budgets
~~~

| Vị trí | Biện pháp | Điều cần xác minh |
| --- | --- | --- |
| Gateway | Per-tenant token bucket, global cap | Quota có tính trên toàn số gateway instance không? |
| Service | Concurrency limit, bulkhead | Có giới hạn cả request giữ connection lâu không? |
| Hàng đợi | Capacity hữu hạn, fair scheduling | Tenant nhiều message có chặn tenant ít message không? |
| Database | Pool budget, query timeout, index, replica | HPA tăng replica có vượt DB budget không? |
| Broker | Queue/topic, consumer group/worker riêng | Có hot partition, lag và poison message không? |
| Kubernetes | Resource requests, replica, node pool | Workload batch có chiếm CPU/RAM của lane quan trọng không? |
| Monitoring | SLI/SLO theo lane/tier | Có phát hiện tenant nhỏ bị lỗi dù dashboard tổng xanh không? |

Các lớp này có ý nghĩa bổ trợ. Một rate limiter chặn từ sớm, một bulkhead bảo vệ concurrency, còn DB timeout bảo vệ thời gian sử dụng connection. Không lớp nào một mình tạo được cô lập end-to-end.

## 5. Rate limiting theo khách hàng

**Rate limit** quy định tốc độ request được tiếp nhận. Ví dụ tenant standard tối đa 50 requests/giây, cho phép burst ngắn 100 request; tenant premium có ngân sách khác theo hợp đồng.

Các thuật toán:

- **Fixed window:** đếm trong cửa sổ cố định; dễ vận hành nhưng burst ở hai biên cửa sổ có thể vượt mức trung bình kỳ vọng.
- **Sliding window:** đo cửa sổ trượt; mượt hơn nhưng yêu cầu lưu trạng thái và tính toán phù hợp.
- **Token bucket:** token được bổ sung theo tốc độ, request tiêu thụ token; cho phép burst hữu hạn.
- **Leaky bucket/pacing:** điều tiết tốc độ phát công việc ra backend.

Ví dụ token bucket:

~~~text
Tenant B:
  Refill rate:       20 tokens/s
  Bucket capacity:   40 tokens
  Mỗi request nhẹ:    1 token

Còn token -> nhận request.
Hết token -> từ chối hoặc xếp hàng ngắn
             theo chính sách đã thiết kế.
~~~

Rate limit không giống concurrency limit. Một tenant chỉ gửi 5 requests/giây nhưng mỗi request gọi export 30 giây có thể tạo 150 tác vụ cùng lúc. Với truy vấn nặng, cần giới hạn số request đồng thời hoặc chuyển thành batch job.

### 5.1. Chi phí mỗi request không bằng nhau

Có thể dùng **weighted tokens**:

| Thao tác | Chi phí logic minh họa |
| --- | ---: |
| Tra một sản phẩm đã cache | 1 |
| Search có filter phức tạp | 3 |
| Tạo đơn, ghi transaction | 5 |
| Export 1 triệu bản ghi | Không chạy đồng bộ; chuyển sang queue |

Tỷ lệ này là ví dụ, không phải đơn vị CPU cố định. Chi phí nên được hiệu chỉnh theo dữ liệu thực và giới hạn backend.

### 5.2. Hạn mức cục bộ so với toàn cluster

Giả sử mỗi Pod có limiter 100 req/s; hệ thống có 8 Pod. Nếu tất cả Pod đều nhận traffic của cùng tenant, quota thực có thể lớn hơn 100 req/s rất nhiều.

Để kiểm soát **quota toàn cluster**, cần nơi phối hợp trạng thái hoặc chia quota có chủ đích. Các lựa chọn:

- Gateway với bộ đếm phân tán và phép cập nhật atomic.
- Redis hoặc store tương ứng dùng token bucket/limit algorithm an toàn với concurrency.
- Global budget kết hợp local limiter để giảm chi phí truy cập store.
- Phân chia cố định quota giữa các instance kèm cơ chế điều chỉnh khi scale.

Cần tính đến latency, failover, clock, replica, stale state, hot key và khả năng overshoot. Nếu cache/phân phối làm giới hạn chỉ gần đúng, phải mô tả rõ sai số thay vì cam kết tuyệt đối.

### 5.3. Khi vượt quota

- HTTP 429 thường phù hợp khi **khách hàng vượt chính quota của mình**.
- HTTP 503 có thể phù hợp khi **nền tảng quá tải** dù khách không vượt hạn mức hợp đồng.
- Retry-After có thể được trả khi hệ thống có cách ước lượng thời gian retry hợp lý.
- Client phải dùng backoff/jitter, giới hạn retry và deadline.
- Lệnh có side effect, nhất là thanh toán, phải có idempotency key và cơ chế đối soát trạng thái.

Không retry tức thì mọi response 429/503: retry storm có thể nhân tải nhiều lần và làm mọi tenant bị ảnh hưởng.

## 6. Bulkhead: cô lập concurrency

**Bulkhead Pattern** giới hạn số công việc một nhóm được phép thực thi cùng lúc. Có thể dùng semaphore, thread pool riêng, worker pool riêng hoặc deployment riêng.

~~~text
                   Request Router
                  /      |       \
             Checkout  Search    Export
             40 slots  25 slots   6 slots
                  \      |       /
                   Shared downstream
                   global safety cap
~~~

Nếu export có hàng trăm job chậm, chỉ 6 job được chạy đồng thời trong lane export; checkout vẫn có một phần budget riêng. Tuy vậy các lane vẫn có thể tranh database, memory hoặc CPU bên dưới, nên phải bảo vệ tiếp.

**Phân biệt ba khái niệm:**

- **Reservation:** lượng năng lực tối thiểu một nhóm được bảo vệ khi cạnh tranh.
- **Cap:** lượng tối đa nhóm được phép chiếm.
- **Borrowing:** nhóm đang bận có thể dùng phần capacity nhóm khác chưa sử dụng.
  
Một số semaphore per-lane đơn giản chỉ thực thi cap, **không tự bảo đảm reservation hoặc borrowing**. Muốn công bằng và mượn capacity phải có scheduler/budget manager có chính sách rõ.

### 6.1. Khi dùng semaphore

Lấy permit trước khi gọi tài nguyên cần bảo vệ; nếu không lấy được trong deadline, từ chối có kiểm soát. Giải phóng permit trong finally. Với công việc bất đồng bộ, giữ permit **đến khi tác vụ thật sự hoàn tất**, không trả permit ngay khi tạo CompletableFuture.

Tránh tạo vô hạn semaphore trong map với key tenant tùy ý; với hàng trăm nghìn tenant, việc giữ registry không có TTL/quota có thể thành memory leak.

### 6.2. Thread pool riêng

Thread pool bulkhead có thêm khả năng tách số worker và queue, hữu ích khi report có thể chờ lâu. Nhưng executor threads vẫn tranh CPU/heap của cùng process nếu triển khai chung Pod. Với mức cô lập cao hơn, đưa report worker sang Deployment khác.

**Queue phải có giới hạn.** Queue vô hạn chỉ chuyển lỗi từ “không có worker” sang “memory/latency tăng vô hạn”.

## 7. Ví dụ Java: giới hạn theo nhóm nghiệp vụ

Ví dụ Java minh họa một bulkhead đồng bộ cho checkout, search và report. Có permit từng lane và global cap để bảo vệ đường vào một dependency chung:

~~~java
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class WorkloadGuard {
    public enum Lane { CHECKOUT, SEARCH, REPORT }

    public static final class BusyException
            extends RuntimeException {
        public BusyException(String reason) {
            super(reason);
        }
    }

    private final Semaphore global = new Semaphore(60, true);
    private final Map<Lane, Semaphore> limits = Map.of(
        Lane.CHECKOUT, new Semaphore(35, true),
        Lane.SEARCH, new Semaphore(20, true),
        Lane.REPORT, new Semaphore(5, true)
    );

    public <T> T run(Lane lane, Callable<T> work)
            throws Exception {
        Semaphore local = limits.get(lane);
        if (local == null) {
            throw new IllegalArgumentException("Unsupported lane");
        }

        if (!global.tryAcquire(50, TimeUnit.MILLISECONDS)) {
            throw new BusyException("Global concurrency exceeded");
        }

        boolean acquired = false;
        try {
            acquired = local.tryAcquire(
                50, TimeUnit.MILLISECONDS
            );

            if (!acquired) {
                throw new BusyException("Lane capacity exceeded");
            }

            return work.call();
        } finally {
            if (acquired) {
                local.release();
            }
            global.release();
        }
    }
}
~~~

**Cách hiểu ví dụ:**

1. Các limit 60, 35, 20 và 5 chỉ để minh họa; phải chọn theo throughput, latency và downstream capacity đo được.
2. Semaphore này giới hạn **một JVM process**. Nếu chạy 10 replica, tổng concurrency có thể tăng theo số replica; global quota giữa Pod cần cơ chế phối hợp khác.
3. Fair semaphore chỉ hỗ trợ công bằng thứ tự cấp permit trong cùng semaphore, không bảo đảm fairness xuyên tất cả Pod/tenant.
4. Đối với task async, ví dụ này không còn giới hạn thời gian chạy đúng nếu work chỉ lập lịch rồi trả về; cần wrapper quản lý lifecycle cho Future/Publisher.
5. Khi BusyException phát sinh, controller cần ánh xạ sang response theo hợp đồng, không để thành HTTP 500 chung chung.
6. Nếu việc chạy lại có side effect, không dùng fallback từ lane mới sang lane cũ như một retry không kiểm soát.
7. Cần instrument số permit đang dùng, số lần bị từ chối và thời gian chờ theo lane.

Một service có tenant động thường cần registry/limiter theo tenant được quản trị bởi một thư viện hoặc thành phần riêng, có giới hạn trạng thái, cleanup và quy tắc quota. Đoạn code trên chỉ minh họa **isolation theo ba nhóm nghiệp vụ cố định**.

## 8. Fairness: tại sao FIFO chung không đủ?

Giả sử backend xử lý ổn định 100 jobs/s:

~~~text
Tenant A muốn 120 jobs/s.
Tenant B muốn  20 jobs/s.
Tenant C muốn  10 jobs/s.

Tổng nhu cầu: 150 jobs/s > capacity 100.
~~~

Nếu tất cả event đẩy vào FIFO chung, A có thể chiếm phần lớn backlog và B/C phải chờ rất lâu. Một scheduler chia theo tenant có thể phục vụ B ~20, C ~10 rồi dành phần còn lại ~70 cho A, tùy chính sách và chi phí từng job.

Một số phương án:

**Round Robin:** xoay vòng giữa queue của các tenant; công bằng theo số lượt, không nhất thiết theo CPU seconds.

**Weighted Round Robin:** mỗi nhóm nhận số lượt theo trọng số; nhóm có SLO cao có thể được cấp thêm.

**Deficit Round Robin / Weighted Fair Queueing:** cố gắng tính đến chi phí công việc và chia capacity công bằng hơn.

**Max-min fairness:** ưu tiên các nhóm có nhu cầu nhỏ nhận đủ trước, sau đó chia phần dư cho nhóm còn yêu cầu.

**Priority queues:** dành ưu tiên cho giao dịch quan trọng, nhưng phải có biện pháp chống starvation của nhóm ưu tiên thấp.

Công bằng phải được định nghĩa bằng chỉ số thực như completion latency, throughput hoặc CPU/DB cost. Nếu job A tốn 10 giây và job B 10 ms, đếm số job bằng nhau chưa chắc hợp lý.

## 9. Bounded queues và backpressure

Khi công việc đến nhanh hơn tốc độ xử lý, queue sẽ tăng. **Little's Law** mô tả trong hệ ổn định: L = λ × W, với L là số công việc trung bình trong hệ, λ là throughput, W là thời gian lưu lại.

Nếu nhận 150 jobs/s nhưng chỉ làm xong 100 jobs/s:

~~~text
Backlog tăng khoảng 50 jobs/giây.
Sau 1 phút có thể thêm ~3.000 jobs chờ.
Nếu mỗi job kèm payload 100 KiB:
  riêng payload có thể ~300 MiB, chưa tính overhead.
~~~

Một queue trong memory không giới hạn có thể gây OOM. Một queue bền vững cũng có giới hạn disk, retention, thời gian chờ và throughput downstream.

Cần định nghĩa:

- Số job tối đa theo queue và theo tenant.
- Thời gian chờ tối đa; job hết deadline phải được xử lý trạng thái ra sao.
- Admission: nhận hoặc từ chối khi queue đầy.
- Retry budget; backoff/jitter và dead-letter handling.
- Ưu tiên và công bằng giữa tenant.
- Idempotency khi client gửi lại hoặc broker redeliver.
- Cancellation và trạng thái job nếu người dùng hủy.

### 9.1. API tương tác và batch khác nhau

**HTTP checkout:** không nên xếp hàng lâu rồi timeout ở gateway. Tốt hơn là chờ rất ngắn hoặc từ chối sớm nếu không có capacity an toàn, kèm ngữ nghĩa retry rõ.

**Export/report:** có thể lưu một job bền vững, trả HTTP 202 cùng job ID và xử lý async. Cần endpoint tra trạng thái và khả năng phục hồi job sau restart.

Không được coi 202 là job đã hoàn thành. Nếu đã chấp nhận job, hệ thống phải có cách lưu và tiếp tục xử lý theo hợp đồng.

## 10. Cô lập trên RabbitMQ và Kafka

### 10.1. RabbitMQ: queue theo lane

~~~text
Event Exchange
      |
      +--> payment.critical queue
      |       +--> payment workers (quota riêng)
      |
      +--> notification.normal queue
      |       +--> notification workers
      |
      +--> report.batch queue
              +--> report workers (giới hạn concurrency)
~~~

Cơ chế này giúp report không đứng ngay trước payment trong cùng một queue FIFO. Cần cấu hình routing key, exchange binding, retry/DLQ và consumer prefetch phù hợp. Với message lỗi, không retry vô hạn để chặn toàn bộ queue.

Tuy nhiên các queue vẫn dùng chung CPU/disk/network nếu cùng broker cluster. Cô lập queue không đồng nghĩa cô lập vật lý toàn broker. Tenant đặc biệt có thể cần queue/consumer hoặc broker resource tier riêng khi chi phí và rủi ro biện minh.

### 10.2. Kafka: topic, partition, consumer group

Kafka xử lý song song chủ yếu theo partition. Key theo tenant có thể đưa sự kiện cùng tenant vào cùng partition (tùy partitioner), giúp giữ thứ tự trong partition nhưng tenant nóng có thể làm một partition nghẽn.

Lưu ý:

- Thêm consumer replica vượt số partition trong cùng consumer group không tự tăng lượng partition được xử lý song song.
- Một hot key có thể tạo hot partition dù cả cluster còn năng lực.
- Tách topic hoặc consumer group theo business lane có thể giúp áp chính sách retention, scaling và retry riêng.
- Queue/topic riêng theo từng tenant nhỏ có thể tạo rất nhiều metadata và chi phí; cân nhắc phân cấp theo nhóm hoặc tenant lớn.
- Consumer lag cần được đo theo group/partition; xử lý lại message có thể sinh duplicate.
- Với side effect, consumer vẫn cần idempotency dù đã tách lane.

**Tenant ID trong Kafka key không tự tạo fairness.** Cần đánh giá phân bố key, số partition, độ dài xử lý và điều phối consumer thực.

### 10.3. Event được giao lại

Cô lập và autoscaling có thể thay đổi lịch xử lý, làm message được giao lại do consumer restart hoặc ack/offset commit lỗi. Consumer cần idempotency key và transaction boundary phù hợp. Với thanh toán hoặc cập nhật tồn kho, không tăng concurrency mà bỏ qua thứ tự và race condition.

## 11. Database: nơi isolation rất dễ bị xuyên thủng

Một service có rate limiter và worker pool riêng vẫn có thể chia sẻ toàn bộ PostgreSQL.

### 11.1. Ngân sách connection

Giả sử database cho phép 250 connections hữu dụng, nhưng có:

~~~text
Order Service:   10 Pod x pool max 20 = 200
Report Workers:   5 Pod x pool max 20 = 100
Other Clients:                         30
                                      ---
Tổng có thể đạt                     330
Budget DB hữu dụng                  250
~~~

Nếu pool mở gần max đồng thời, database có thể cạn connections. HPA thêm Pod lại tăng nguy cơ. Phải tính ngân sách dựa trên **maxReplicas**, không chỉ số Pod hiện tại.

Một giới hạn global tại service không bảo đảm giới hạn DB nếu mỗi request có thể dùng nhiều connection hoặc các job khác cùng truy cập. Cần kết hợp pool sizing, query timeouts và giám sát acquisition wait.

### 11.2. Tách report khỏi OLTP

Report thường quét nhiều dữ liệu và dùng nhiều CPU/IO. Các phương án:

- Dùng read replica khi phù hợp với yêu cầu nhất quán và độ trễ replication.
- Tách analytics store/warehouse cho báo cáo lớn.
- Giới hạn số report concurrent và batch size.
- Yêu cầu pagination hoặc query plan/index hợp lý.
- Đặt statement timeout và kiểm soát truy vấn tùy ý.
- Tránh giữ transaction lâu hoặc lock không cần thiết.

Read replica không phải giải pháp miễn phí: nó vẫn có giới hạn CPU, IO, replication lag; không dùng làm nguồn dữ liệu cập nhật tức thì cho quyết định thanh toán đòi hỏi nhất quán mạnh.

### 11.3. Multi-tenant data models

| Mô hình | Cô lập dữ liệu | Cô lập hiệu năng |
| --- | --- | --- |
| Shared tables với tenant_id | Cần authorization, filter/RLS đúng | Thấp nếu cùng DB CPU/I/O/lock |
| Schema riêng | Namespace riêng, migration phức tạp hơn | Vẫn dùng chung DB engine |
| Database riêng trong cùng server | Tách một số hoạt động quản trị | Có thể vẫn tranh CPU/disk/IO |
| Instance/shard/cluster riêng | Cô lập mạnh hơn | Chi phí, routing, migration và vận hành cao |

**Logical data isolation không đồng nghĩa performance isolation.** Có RLS hoặc tenant_id đúng ngăn truy cập chéo dữ liệu nhưng không tự ngăn tenant A chạy query làm chậm tenant B.

### 11.4. Query budgets

Hãy đo query duration, pool wait, lock wait, I/O, temp file usage và slow queries. Có thể thiết kế riêng quota cho analytical query, giới hạn trang/truy vấn, tránh full scan không cần thiết, index theo access pattern và dùng cancellation khi request đã hết deadline.

Nếu DB đã bão hòa, tăng API Pod không giải quyết vấn đề.

## 12. Cache cũng cần ngân sách

Một tenant có thể đẩy hàng triệu key vào cache chung, làm evict những hot keys của tenant khác. Kết quả là cache miss tăng, kéo tải xuống database và tạo noisy neighbor gián tiếp.

Các biện pháp:

- Đặt key namespace đúng tenant context, không trộn dữ liệu.
- TTL/size limit và tránh cache payload quá lớn.
- Giới hạn bộ nhớ/entry theo tenant hoặc tier khi backend hỗ trợ.
- Tách cache cho workload có mức độ nhạy cảm hoặc tải đặc biệt.
- Theo dõi hit ratio, evictions, memory pressure và DB read rate.
- Thiết kế cache stampede protection để nhiều request cache miss không cùng dồn vào database.

**Prefix key theo tenant chỉ giúp phân tách tên**, không giới hạn tổng RAM tenant có thể chiếm. Nếu cần cô lập cứng phải có quota thực thi hoặc tài nguyên cache tách riêng.

## 13. Kubernetes: tách workload ở mức Pod và node

Có thể chọn mức cô lập tăng dần:

1. Chung Deployment, riêng semaphore/queue logic.
2. Riêng executor/worker pool trong cùng service.
3. Riêng Deployment cho checkout và report, cùng namespace/cluster.
4. Riêng node pool hoặc nhóm nodes có taints/tolerations.
5. Riêng data backend hoặc toàn cluster cho tenant quan trọng.

Tách Deployment cho phép:

- Requests/limits CPU và memory riêng.
- HPA/KEDA theo metrics phù hợp từng workload.
- Rolling update và restart độc lập.
- Giới hạn số replicas và ngân sách connection riêng.
- Bảo vệ workload quan trọng trước burst của batch worker.

Ví dụ thông số **minh họa**:

~~~text
Deployment checkout-api:
  minReplicas = 4, maxReplicas = 20
  CPU request = 500m/Pod
  Memory request = 512Mi/Pod
  SLO = p95 < 300ms

Deployment report-worker:
  minReplicas = 1, maxReplicas = 5
  CPU request = 250m/Pod
  Memory request = 1Gi/Pod
  SLO = job hoàn tất trong 15 phút
~~~

Các thông số phải dựa trên đo đạc; không có con số mặc định hợp lệ cho mọi ứng dụng.

**Resource requests** giúp scheduler tính toán placement, **limits** kiểm soát tiêu thụ theo cơ chế tương ứng. CPU có thể bị throttling khi vượt quota; memory có thể dẫn tới OOMKilled. Nếu checkout và report chung node, chúng vẫn cạnh tranh tài nguyên node dù nằm ở deployment khác.

Kubernetes Namespace ResourceQuota, LimitRange, PriorityClass và NodePool giúp quản trị workload; nhưng không tự bảo đảm SLO end-to-end vì database, broker và vendor quota có thể vẫn chung.

## 14. Autoscaling phải đi cùng downstream budget

HPA theo CPU có thể không nhận biết một service đang nghẽn ở DB connection pool. Queue worker có thể nên scale theo lag/backlog bằng KEDA hoặc external metrics phù hợp; nhưng tăng worker quá nhiều có thể làm database/partner API quá tải.

Một ví dụ:

~~~text
Report worker có 2 replicas,
mỗi replica mở tối đa 10 DB connections.
=> khoảng 20 connections.

KEDA/HPA tăng lên 20 replicas:
=> tối đa khoảng 200 connections.

Nếu DB chỉ có budget 60 connections cho report:
=> Hệ thống tự làm nghẽn downstream.
~~~

Do đó cần giới hạn maxReplicas hoặc một global work budget, cân nhắc pool sizing, concurrency và queue admission. Đặt mục tiêu throughput tại điểm vẫn đạt SLO, không chỉ tối đa số worker.

Khi Pod mới Pending vì requests hoặc node pool thiếu dung lượng, HPA đã yêu cầu tăng replica không có nghĩa capacity thực đã tăng. Theo dõi Pending/Ready, node allocatable và thời gian startup.

## 15. Tenant isolation phải dựa trên danh tính đáng tin cậy

Không chấp nhận một header như X-Tenant-ID do client tự gửi rồi cấp quota premium ngay.

Quy trình:

1. Xác thực người gọi bằng token/session/mTLS theo thiết kế.
2. Xác định tenant ID và quyền thành viên từ claims/backend đáng tin cậy.
3. Kiểm tra API action có được phép trên tenant đó không.
4. Nạp tier/quota của tenant từ nguồn cấu hình được quản lý.
5. Đánh giá admission limit và thực thi logic nghiệp vụ.
6. Khi publish message, giữ tenant context cần thiết, không phát dữ liệu nhạy cảm thừa.
7. Tại consumer, kiểm tra owner/tenant trong dữ liệu đã lưu và chính sách quyền phù hợp.

Một người dùng thuộc nhiều tenant phải chọn tenant context rõ ràng. Không tự lấy quota cao nhất của tất cả tenant họ có quyền sử dụng.

Tenant ID dùng trong logs/traces cũng cần chính sách bảo mật. Nếu số lượng tenant rất lớn, không đưa tenant ID trực tiếp vào mọi metric label vì **high cardinality**.

## 16. Quan sát tải theo nhóm và đo SLO

Dashboard tổng thể có thể che việc một tenant nhỏ hỏng hoàn toàn.

Ví dụ:

~~~text
Tenant A: 10.000 request, 99,99% thành công.
Tenant B:    100 request, 70% thành công.

Tỷ lệ thành công tổng vẫn gần 99,7%,
nhưng B đang gặp sự cố nghiêm trọng.
~~~

Cần đo:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| requests_admitted_total | Lượng request được nhận theo lane/tier |
| requests_rejected_total | Số lần bị quota hay overload chặn |
| in_flight_requests | Số request đang giữ permit/worker |
| queue_wait_seconds | Thời gian chờ trước khi bắt đầu xử lý |
| request_duration_seconds | Độ trễ API/operation |
| pool_acquire_seconds | Thời gian chờ lấy DB/HTTP connection |
| jobs_ready | Backlog theo queue/lane |
| oldest_job_age_seconds | Tuổi job đang chờ |
| consumer_lag | Consumer tụt bao xa so với producer |
| cache_evictions_total | Áp lực và việc đẩy cache |
| cpu_throttled_time | CPU bị giới hạn khi burst |
| payment_pending_total | Giao dịch chưa đạt trạng thái cuối |

Dùng nhãn có tập giá trị giới hạn như lane, tier, route template, region, outcome, status class. Tránh user_id, order_id, trace_id và tenant_id có số lượng rất lớn làm metric label.

Để điều tra tenant cụ thể, dùng log/trace hoặc dữ liệu tổng hợp riêng có RBAC, retention và truy vấn phù hợp. Với một tập tenant quan trọng nhỏ, có thể tạo bảng SLI riêng có giới hạn cardinality.

### 16.1. Các cảnh báo hữu ích

- Payment lane p95/error rate vượt SLO.
- Một tenant bị 429 vượt mức cam kết trong thời gian dài.
- Report backlog lớn nhưng checkout vẫn trong SLO (cơ chế cô lập đang hoạt động).
- Checkout chậm khi report query chạy.
- DB pool wait tăng mạnh sau khi HPA scale.
- Consumer lag bất thường ở một nhóm.
- Cache evictions tăng đồng thời DB read rate tăng.
- Pod Pending hoặc OOMKilled khiến capacity bảo vệ không còn.

Phải phân biệt **quota đang bảo vệ đúng** với **quota quá chặt làm khách hàng hợp lệ bị từ chối trong lúc capacity vẫn dư**.

## 17. Retry, timeout và load shedding

Các cơ chế tăng độ tin cậy phải phối hợp với isolation:

- **Timeout/deadline:** giới hạn thời gian giữ worker, connection và permit.
- **Retry with backoff/jitter:** tránh đợt retry đồng thời; chỉ retry thao tác an toàn hoặc có idempotency.
- **Circuit breaker:** ngừng dồn request vào dependency đang lỗi; không để mọi lane cùng tạo retry storm.
- **Bulkhead:** giới hạn mức độ một nhóm chiếm nguồn lực.
- **Backpressure:** cho upstream thấy downstream không thể xử lý thêm.
- **Load shedding:** từ chối hoặc giảm chức năng thấp ưu tiên theo chính sách.
- **Autoscaling:** tăng capacity khi có thể, không thay admission control.
- **Caching:** giảm tải backend, nhưng cache phải chịu được pollution theo tenant.

Ví dụ một chính sách giảm tải:

~~~text
Normal:
  Checkout, search, report đều được phục vụ.

Moderate overload:
  Giảm report concurrency;
  đưa export vào queue;
  search có thể dùng phương án giảm chất lượng đã chấp nhận.

Severe overload:
  Từ chối công việc không thiết yếu;
  giới hạn checkout theo DB capacity;
  giữ tính đúng đắn của payment.

Recovery:
  Mở lại quota theo từng bước,
  tránh backlog và retry đổ dồn.
~~~

Không tự động bỏ qua thao tác thanh toán, ghi mất sự kiện quan trọng hoặc lưu dữ liệu sai để “bảo đảm availability”. Với tác vụ có side effect và tính đúng đắn cao, cần trạng thái pending bền vững, idempotency và đối soát.

## 18. Cân bằng fairness và hiệu quả sử dụng

Nếu đặt hard reservation cho mọi tenant nhưng nhiều tenant không dùng, capacity có thể bị bỏ phí. Nếu tất cả chia sẻ hoàn toàn, tenant lớn có thể lấn át tenant nhỏ. Một số hệ thống dùng:

**Guaranteed minimum:** nhóm đủ điều kiện có một mức phục vụ tối thiểu khi cạnh tranh.

**Maximum cap:** nhóm không vượt mức tối đa dù tài nguyên còn rảnh.

**Borrowing:** có thể mượn phần capacity chưa được dùng; khi tenant khác cần lại, scheduler phân bổ về mức bảo vệ.

**Global safety cap:** giới hạn hệ thống không vượt năng lực downstream.

Ví dụ backend có khả năng xử lý 200 units/s ở SLO đã kiểm chứng:

| Nhóm | Mức tối thiểu mong muốn | Cap khi có headroom |
| --- | ---: | ---: |
| Checkout | 100 | 150 |
| Search | 30 | 90 |
| Report | 10 | 30 |

Đây là **mục tiêu chính sách**, không tự động được thực thi chỉ bằng các con số trong bảng. Muốn thật sự có reservation và borrowing cần scheduler/queue hoặc tài nguyên tách riêng. Khi tổng nhu cầu lớn hơn capacity, phải có quy tắc ưu tiên và giới hạn rõ.

Mục tiêu là tối ưu **chi phí trên một giao dịch đạt SLO**, không chỉ CPU utilization trung bình. Cho report sử dụng tài nguyên rảnh có thể tốt, miễn là nó không cản checkout khi traffic quay lại.

## 19. Tính toán capacity ban đầu

Một cách ước lượng CPU-bound:

~~~text
CPU demand trung bình
≈ request_rate × CPU_seconds_per_request

300 requests/s × 0,010 CPU seconds/request
≈ 3 CPU cores trung bình.
~~~

Cần headroom cho burst, GC, độ không đều giữa replicas, thay phiên bản và mất một Pod.

Với công việc chờ I/O:

~~~text
Concurrent operations trung bình
≈ arrival_rate × average_duration

100 requests/s × 0,2 s ≈ 20 in-flight requests.
~~~

Đây là ước lượng ở trạng thái ổn định; p95/p99 và burst có thể đòi số slot lớn hơn. Nếu DB pool chỉ có 25 connection, mức trung bình 20 đã tương đối sát capacity.

Ví dụ tính giới hạn connection:

~~~text
Database có budget: 200 connections.
Dự phòng vận hành:  20.
Service khác:       60.
Còn lại cho Order: 120.

Nếu Order có thể scale tới 12 Pod:
  Pool tối đa mỗi Pod <= 120 / 12 = 10
  trước khi xét các workload khác của Order.
~~~

Cần tính cả worker batch, migration và các service dùng cùng database. Không nên chỉ nhìn maxReplicas ở thời điểm hiện tại; phải xem các cấu hình scaling có thể chạy đồng thời.

## 20. Các bậc cô lập và chi phí

Có một phổ lựa chọn:

~~~text
Shared everything
   -> global + per-tenant rate limit
   -> per-lane concurrency/bounded queues
   -> worker/deployment riêng
   -> data cache/DB pool/queue riêng
   -> shard/DB instance riêng
   -> cluster riêng
~~~

Mức càng mạnh thường càng tốn chi phí vận hành, monitoring, migration, backup và capacity dự phòng. Một platform với vài chục tenant nhỏ chưa cần tạo mỗi tenant một Kubernetes namespace và database riêng. Trong nhiều trường hợp, **logical quotas + queue isolation + DB budget** đã giảm đáng kể noisy neighbor.

Tuy nhiên tenant có giao dịch cực lớn, yêu cầu SLA/tuân thủ hoặc tải ổn định chiếm phần lớn hạ tầng chia sẻ có thể phù hợp với dedicated capacity. Khi chuyển tenant phải thiết kế routing, migration, cutover, tương thích schema, dữ liệu và phương án rollback.

**Cô lập dữ liệu và cô lập hiệu năng khác nhau:** schema riêng vẫn có thể dùng chung DB CPU/IO; deployment riêng vẫn dùng chung vendor quota; cluster riêng vẫn có thể gọi cùng payment gateway.

## 21. Kiểm thử noisy neighbor thực tế

Không thể chứng minh isolation chỉ bằng unit test từng limiter. Cần bài kiểm thử gây tải đối nghịch có kiểm soát.

### Kịch bản A: Tenant lớn vượt quota

~~~text
Given:
  Tenant B/C đang chạy tải bình thường và đạt SLO.
When:
  Tenant A gửi traffic gấp 10 lần quota.
Then:
  A bị giới hạn theo hợp đồng.
  B/C vẫn đạt latency và error SLO.
  Không cạn DB connections hoặc worker pool.
  Hệ thống không OOM hay restart hàng loạt.
~~~

### Kịch bản B: Report làm nghẽn checkout

~~~text
Given:
  Checkout ổn định.
When:
  Report jobs đổ vào queue và chạy query nặng.
Then:
  Report bị xếp hàng hoặc từ chối theo capacity.
  Checkout vẫn đạt SLO.
  DB pool wait/lock wait được kiểm soát.
~~~

Nếu checkout vẫn chậm, có thể thiếu ranh giới ở database I/O, không nhất thiết semaphore report bị hỏng.

### Kịch bản C: Broker có poison message

~~~text
Given:
  Các tenant gửi events vào hệ thống.
When:
  Event của tenant A liên tục gây lỗi deserialize.
Then:
  Retry/DLQ theo policy.
  Event của B không bị chặn vô hạn.
  Không có duplicate business side effect.
~~~

### Kịch bản D: Scale vượt downstream

~~~text
Given:
  HPA/KEDA muốn tăng worker từ 3 lên 15 replicas.
When:
  Queue lag tăng.
Then:
  Tổng DB/API concurrency không vượt ngân sách.
  Số job hoàn thành tăng nếu downstream còn capacity.
  Không phát sinh retry storm, pool exhaustion.
~~~

### Kịch bản E: Identity giả mạo

Thử client giả mạo X-Tenant-ID của tenant premium. Sau xác thực/phân quyền, họ không được nhận quota của tenant khác hoặc truy cập dữ liệu khác. Đồng thời log không được tiết lộ token và thông tin nhạy cảm.

## 22. Chẩn đoán khi isolation thất bại

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| B chậm khi A tăng tải | Shared worker/DB pool bị chiếm | In-flight, queue wait, pool acquire |
| HPA tăng Pod rồi DB tệ hơn | Tổng connections vượt budget | Số replica, max pool, DB sessions |
| CPU thấp nhưng timeout | Chờ lock/DB/network | Thread state, lock wait, query time |
| Kafka lag tập trung | Hot partition/consumer skew | Partition lag, key distribution |
| Queue dài nhưng CPU còn rảnh | Worker thiếu, I/O-bound hoặc policy cap | Consumer concurrency, downstream |
| Tenant bị 429 khi cluster còn rảnh | Quota sai hoặc chưa có borrowing | Admission metrics, policy |
| Cache của B miss tăng | A gây eviction/pollution | Cache keys, evictions, DB read |
| Pod OOM lúc export | Queue/payload không giới hạn | Heap, off-heap, message size |
| Quota bị nhân theo số Pod | Local limiter không có state chung | Gateway/instance count |
| Tenant dùng tier trái phép | Không xác thực tenant context | Claims, authz, config source |

Luôn đối chiếu triệu chứng của nhóm gây tải với **SLO của nhóm bị ảnh hưởng**, không chỉ tổng request rate của service.

## 23. Quy trình triển khai từng bước

1. **Phân loại nhóm:** tenant/tier, nghiệp vụ realtime/batch, mức quan trọng và deadline.
2. **Vẽ dependency map:** gateway, executor, DB pool, broker, cache, node và external APIs.
3. **Đo baseline:** CPU, memory, queue wait, DB pool, p95/p99, rate, business outcomes theo nhóm.
4. **Đặt global cap:** giới hạn toàn nền tảng tại bottleneck để tránh sập khi một nhóm bùng nổ.
5. **Thêm quota tenant/tier:** rate, burst và concurrency theo hợp đồng.
6. **Tách lane:** checkout, search, report; áp bulkhead và bounded queues.
7. **Bảo vệ downstream:** DB pool, query timeout, broker concurrency, cache limits và vendor quota.
8. **Thiết kế fairness:** round robin/weighted scheduler hoặc reservation/cap/borrowing tùy mục tiêu.
9. **Autoscaling có điều kiện:** tăng replicas khi backend còn headroom và metrics phản ánh đúng tải.
10. **Kiểm thử đối nghịch:** một tenant quá tải trong khi những tenant khác chạy nền ổn định.
11. **Quan sát:** đo rejected, in-flight, queue wait và business SLO theo lane/tier; có drilldown theo tenant an toàn.
12. **Vận hành quota:** RBAC, audit, cảnh báo, cơ chế thay đổi khẩn cấp và rà soát định kỳ.

Một chính sách quota chỉ có giá trị khi được thực thi thống nhất giữa instance, có thể kiểm thử, và có cơ chế xử lý khi control plane bị lỗi.

## 24. Bài tập thực hành

Hệ thống SaaS có ba tenants:

- A: cửa hàng lớn, flash sale có 400 checkout requests/s.
- B: cửa hàng vừa, khoảng 30 checkout requests/s, cần SLO p95 dưới 300 ms.
- C: cửa hàng nhỏ, khoảng 20 checkout requests/s và 50 export jobs.
- Backend checkout xử lý bền vững khoảng 250 operations/s ở SLO giả định.
- PostgreSQL dành tối đa 100 connections cho nhóm dịch vụ này.
- Report Worker đọc dữ liệu nặng, RabbitMQ giữ jobs.

**Yêu cầu:**

1. Định nghĩa rate/concurrency quota cho tenant và global cap, giải thích cách bảo vệ B/C khi A quá tải.
2. Phân chia checkout và export thành lane có deadline/queue/worker riêng.
3. Nêu phương pháp fairness, tránh để FIFO chung làm C phải chờ sau hàng nghìn request của A.
4. Tính DB connection budget khi số replica tối đa của checkout và report thay đổi.
5. Đề xuất HPA/KEDA metrics phù hợp mà không làm DB quá tải.
6. Xác định hành vi 429, 503, 202 và retry cho các trường hợp tương ứng.
7. Đề xuất SLI của B/C và bài load test chứng minh noisy neighbor được giới hạn.
8. Giải thích cách ngăn client giả mạo tenant premium.
9. Mô tả ứng xử với export job bị giao lại hoặc tồn tại quá deadline.
10. Khi A ít traffic và B/C đang rảnh, mô tả cách cho mượn capacity mà vẫn bảo đảm mức phục vụ tối thiểu khi các tenant quay lại.

**Hướng giải tham khảo:** Gateway xác thực tenant và dùng quota phân tán; service có global cap và bulkhead theo lane; report xử lý qua queue bền vững và worker có concurrency riêng; DB pool được tính theo maxReplicas; autoscaling có giới hạn downstream; fairness chia ngân sách trong tình huống cạnh tranh; theo dõi SLO B/C dưới tải A; trả lỗi/công việc chờ theo hợp đồng với retry/idempotency an toàn.

## 25. Các ngộ nhận thường gặp

**“Thêm nhiều Pod là tự hết noisy neighbor.”** Nếu DB/Redis/broker vẫn chung, nhiều Pod có thể tạo nhiều tranh chấp hơn.

**“Có rate limit là đủ.”** Request dài hoặc query đắt có thể chiếm hết connection dù request rate thấp.

**“Một semaphore cho mỗi tenant sẽ đảm bảo mọi thứ.”** Semaphore cục bộ không quản lý CPU, memory, DB hoặc toàn cluster; registry tenant không giới hạn còn có thể gây leak.

**“Đã tách queue là tách hoàn toàn tải.”** Queue có thể vẫn ở cùng broker node và consumer cùng database.

**“FIFO là công bằng.”** Tenant gửi nhiều message có thể chiếm đa số queue; cần fairness theo nhóm.

**“Không giới hạn queue vì sợ mất job.”** Queue vô hạn có thể khiến hệ thống sập; với job quan trọng cần lưu bền vững và admission policy rõ.

**“HPA nhìn CPU là biết mọi bottleneck.”** Worker có thể chờ DB, network, broker trong khi CPU thấp.

**“Schema riêng là cô lập tài nguyên.”** Các schema cùng DB engine vẫn tranh CPU/IO/cache.

**“Đặt tenant ID từ request header là đủ.”** Tenant identity phải được xác thực và phân quyền.

**“Nhóm premium được phép dùng vô hạn.”** Quota cao hơn vẫn cần global safety cap và downstream budget.

**“Dashboard tổng xanh thì tất cả tenant ổn.”** Các tenant ít request có thể bị lỗi lớn nhưng tổng trung bình che khuất.

**“Retry nhiều sẽ giúp service phục hồi nhanh.”** Retry có thể làm overload nặng hơn; cần backoff, jitter, retry budget, idempotency.

**“Cô lập mạnh nhất luôn là tốt nhất.”** Tài nguyên dedicated có thể rất đắt và khó vận hành; chọn mức cô lập tương ứng rủi ro/SLO.

---

**Điểm cốt lõi:** Cô lập tải giúp một tenant hoặc nghiệp vụ tăng tải, chậm hoặc lỗi không làm mất năng lực phục vụ của phần còn lại. Cách làm hiệu quả là xác thực đúng nhóm tải, giới hạn rate và concurrency, dùng bulkhead và bounded queues, xếp lịch công bằng, bảo vệ ngân sách database/broker/cache, autoscale có kiểm soát và đo SLO theo phân khúc. Mục tiêu không chỉ là xử lý được nhiều request hơn mà là **giữ các nhóm quan trọng hoạt động đúng khi một nhóm khác trở thành noisy neighbor**.
