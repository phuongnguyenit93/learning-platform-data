# Giới hạn concurrency và connection pool trong Spring Integration Adapters

> **Chương:** Production  
> **Bài học:** Giới hạn concurrency và connection pool  
> **Module:** Spring Integration Adapters  
> **Bối cảnh:** Kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và MessageChannel; xử lý file, SFTP, HTTP, JMS, AMQP, Kafka và JDBC với hợp đồng message, lỗi và vòng đời kết nối.

## 1. Mục tiêu học tập và tình huống

Sau khi học xong, bạn có thể:

1. Phân biệt **concurrency**, **parallelism**, **throughput**, **inflight message**, **queue depth**, **thread pool** và **connection pool**.
2. Tính giới hạn xử lý dựa trên tốc độ đến, thời gian giữ tài nguyên, số connection có sẵn và hạn mức downstream.
3. Chọn đúng kênh trong Spring Integration: `DirectChannel`, `ExecutorChannel`, `QueueChannel` và các channel khác, đồng thời hiểu ranh giới đồng bộ/bất đồng bộ.
4. Cấu hình `TaskExecutor`, `TaskScheduler`, poller, số batch và giới hạn inflight mà không tạo queue hoặc thread không kiểm soát.
5. Thiết kế backpressure, bulkhead, rate limiting, fairness và cơ chế giảm tải khi hệ ngoài bị chậm.
6. Xác định các giới hạn đặc thù của File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC.
7. Kiểm tra transaction, acknowledge, ordering, idempotency và retry khi tăng concurrency hoặc scale nhiều instance.
8. Lập kế hoạch load/soak/failure testing, dashboard, runbook và tiêu chí go/no-go trước production.

**Tình huống xuyên suốt:** Dịch vụ Spring Boot dùng Spring Integration nhận file từ SFTP mỗi 5 giây, ghi đơn hàng vào JDBC, gọi HTTP API đối tác rồi phát Kafka event. Khi tăng từ 1 lên 5 replica, số task tăng nhanh nhưng đối tác HTTP chỉ cho phép 40 request đồng thời và database chỉ có 30 connection dùng chung. Kết quả có thể là pool wait tăng, request timeout, Kafka backlog, duplicate file và retry storm. Hệ cần **giới hạn tải theo điểm nghẽn**, không chỉ theo số CPU hay số pod.

**Giới hạn phiên bản:** Tên API và thuộc tính cụ thể khác nhau theo Spring Integration, Spring Boot, Spring Framework, các client/broker và phiên bản thư viện. Ví dụ là mô hình tham khảo; cần kiểm tra tài liệu và thử nghiệm với **đúng version ứng dụng** trước khi copy vào production.

## 2. Hiểu rõ các chỉ số tài nguyên

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Concurrency** | Số thao tác đang diễn ra đồng thời trong một phạm vi | 20 request HTTP đang được gửi/chờ |
| **Parallelism** | Số tác vụ thực sự chạy cùng lúc trên tài nguyên tính toán | 8 CPU-bound tasks trên các core |
| **Throughput** | Số message/tác vụ hoàn thành trên một đơn vị thời gian | 120 messages/s |
| **Arrival rate (λ)** | Tốc độ message đến | 150 messages/s |
| **Service time (W)** | Thời gian một item giữ tài nguyên từ nhận tới hoàn tất bước | 0,25 s/HTTP request |
| **Inflight** | Item đã nhận nhưng chưa hoàn thành/ack theo hợp đồng | 50 broker messages unacked |
| **Queue depth** | Message/task đang chờ thực thi | 200 tasks trong executor queue |
| **Thread pool** | Tập luồng ứng dụng xử lý công việc | 16 worker threads |
| **Connection pool** | Kết nối vật lý/logical đến hệ ngoài được tái sử dụng | HikariCP 24 DB connections |
| **Pool acquisition wait** | Chờ lấy kết nối rảnh từ pool | 300 ms để mượn JDBC connection |
| **Backpressure** | Làm chậm/ngừng nhận mới khi downstream không theo kịp | Pause poller khi queue đầy |
| **Bulkhead** | Tách giới hạn tài nguyên theo đối tác/luồng | Tối đa 8 HTTP calls tới partner A |
| **Rate limit** | Giới hạn số lời gọi theo thời gian | 200 calls/minute |
| **Capacity** | Năng lực bền vững trong điều kiện mục tiêu | 90 orders/s ở p95 dưới SLO |
| **Saturation** | Tài nguyên đã gần/đạt giới hạn | Pool active=24, pending=80 |

### 2.1. Concurrency không đồng nghĩa số connection

Một thread có thể:

- Đang chờ queue và **không giữ connection**;
- Đang gọi JDBC và **giữ DB connection**;
- Đang chờ HTTP response và **giữ pooled HTTP connection**;
- Đang ngủ backoff mà **không cần giữ connection**, nhưng vẫn chiếm thread nếu retry đồng bộ;
- Đang chờ lock, khiến một transaction giữ connection lâu hơn;
- Thực hiện bất đồng bộ/non-blocking I/O, không buộc một thread cho mỗi request.

Ngược lại, một connection pool có thể chứa nhiều kết nối idle; một số client multiplex nhiều request trên một kết nối tùy protocol (ví dụ HTTP/2). Vì vậy không thể đặt `maxThreads = maxConnections` rồi cho là đủ. Phải đo **số connection bị chiếm theo thời gian** và khả năng client thực.

### 2.2. Đồng thời ở nhiều tầng

Một luồng có thể có:

~~~text
SFTP poller -> File/message handler -> ExecutorChannel queue
            -> JDBC transaction -> HTTP outbound gateway -> Kafka publisher
~~~

Mỗi chặng có giới hạn và khả năng giữ tài nguyên riêng. Nếu `ExecutorChannel` nhận 500 task nhưng HTTP pool chỉ có 20 connection, có thể có 20 task đang gọi HTTP, hàng chục task đang chờ pool và hàng trăm task còn trong queue. Hãy ghi rõ **active + waiting + buffered + already acknowledged** thay vì một con số concurrency chung.

## 3. Mô hình năng lực: định lượng trước khi tăng pool

### 3.1. Little’s Law trong trạng thái ổn định

Với hệ tương đối ổn định:

\[
L = \lambda W
\]

Trong đó:

- `L`: số item trung bình đồng thời trong một phạm vi (đang chờ **hoặc** xử lý, tùy định nghĩa);
- `λ`: tốc độ hoàn thành trung bình trong điều kiện ổn định;
- `W`: thời gian trung bình item lưu lại trong phạm vi đó.

**Ví dụ:** 80 HTTP requests/s, trung bình mỗi request giữ một HTTP connection 0,2 s:

\[
L_{\mathrm{connection}} \approx 80 \times 0{,}2 = 16.
\]

Điều này gợi ý khoảng **16 kết nối đang sử dụng trung bình**, nhưng **không** có nghĩa pool 16 luôn đủ: p95/p99 latency, burst, retries, handshake và dự phòng thay đổi nhu cầu. Cần load test để chọn số tối đa dựa trên SLO và hạn mức đối tác.

Một ví dụ khác: khi downstream latency tăng từ 0,2 s lên 1 s mà vẫn đến 80 requests/s, nhu cầu inflight tăng từ khoảng 16 lên **80**. Nếu pool giới hạn 20, phần còn lại phải chờ, backpressure hoặc bị từ chối; không có cấu hình concurrency nào làm downstream tự tăng tốc.

### 3.2. Năng lực chặng chậm nhất

Với luồng nối tiếp, throughput bền vững không thể vượt năng lực chặng chậm nhất (bỏ qua các hiệu ứng pipeline/batching):

\[
R_{\mathrm{flow}} \le \min(R_{\mathrm{SFTP}},R_{\mathrm{DB}},R_{\mathrm{HTTP}},R_{\mathrm{Kafka}},\ldots).
\]

Nếu database commit 120 rows/s và đối tác HTTP giới hạn 50 requests/s, tăng Kafka partitions hoặc executor threads không làm flow hoàn thành hơn 50 requests/s nếu mỗi đơn hàng đều phải gọi HTTP.

### 3.3. Ước tính backlog

Giả sử nguồn đến 150 orders/s nhưng hệ xử lý chỉ hoàn tất 100 orders/s. Nếu tốc độ ổn định và không giảm tải:

\[
\Delta Q / \Delta t \approx 150 - 100 = 50\ \mathrm{orders/s}.
\]

Sau 10 phút, backlog có thể tăng **30.000 orders** (ước tính, không tính biến động/loại bỏ). Nếu mỗi item giữ 4 KiB trong heap, chỉ payload đã chiếm khoảng 117 MiB, chưa gồm object/header, retry state và overhead. Chọn **bounded queue** và chiến lược xử lý khi đầy trước khi cấp phép production.

### 3.4. Quy tắc sizing thực tế

1. Đo arrival rate theo peak và burst, không chỉ trung bình ngày.
2. Đo service time p50/p95/p99 của mỗi dependency.
3. Xác định **quota và max concurrent calls** được phép ở downstream.
4. Ước tính inflight bằng tải × thời gian giữ tài nguyên.
5. Chọn headroom, max pool, bounded queue, rejection và throttle.
6. Thử load/soak; đo pending wait và tăng lỗi khi gần saturation.
7. Điều chỉnh theo dữ liệu đo, không dùng cấu hình “càng lớn càng tốt”.

**Không coi Little’s Law là công thức chọn pool chính xác tuyệt đối** khi hệ đang overload, liên tục retry hoặc tốc độ đến không ổn định. Nó hỗ trợ suy luận và phát hiện bottleneck; quyết định production vẫn cần thử tải thật.

## 4. Sơ đồ giới hạn tại nhiều tầng

~~~mermaid
flowchart LR
    SRC["SFTP / File / HTTP / Broker"] --> IN["Inbound endpoint"]
    IN --> POLL["Poller / listener concurrency"]
    POLL --> CH["Bounded MessageChannel"]
    CH --> EXEC["Bounded TaskExecutor"]
    EXEC --> DB["JDBC pool + transaction limit"]
    DB --> HTTP["HTTP pool + partner bulkhead"]
    HTTP --> PUB["Kafka / JMS / AMQP publisher"]
    PUB --> OUT["External target"]
    CH -. "Queue full" .-> BP["Pause / slow ingress"]
    EXEC -. "Rejection" .-> BP
    DB -. "Pool wait high" .-> BP
    HTTP -. "429 / latency" .-> BP
    PUB -. "Lag / broker errors" .-> BP
    BP --> OBS["Metrics + alerts + runbook"]
    DB --> OBS
    HTTP --> OBS
~~~

Một hệ production nên có **hợp đồng xử lý quá tải** rõ cho mỗi ranh giới:

- **Pause ingress:** Chỉ khi nguồn vẫn lưu message/file/row bền vững và có khả năng tiếp tục.
- **Bounded queue:** Chỉ khi kết quả khi đầy được xử lý; không drop message đã ack.
- **Reject:** Trả lỗi có thể retry cho caller nếu hợp đồng cho phép.
- **Durable buffering:** Lưu message trong broker/outbox/inbox trước khi ack.
- **Bulkhead:** Giới hạn từng dependency/tenant, tránh “noisy neighbor”.
- **Rate limit:** Tuân quota theo thời gian, không chỉ số đồng thời.

## 5. Chọn MessageChannel theo backpressure và transaction

Spring Integration cung cấp nhiều loại channel. Chọn sai channel có thể biến một flow chạy ổn local thành bottleneck hoặc điểm mất message.

| Channel | Giao message | Tác động lên concurrency | Rủi ro nếu cấu hình sai |
|---|---|---|---|
| **DirectChannel** | Đồng bộ trong thread của sender | Handler chậm giữ thread upstream; downstream tự giới hạn qua caller | Chặn poller/HTTP listener, exception truyền ngược |
| **ExecutorChannel** | Dispatch bằng `TaskExecutor` | Tách thread; số worker và hàng chờ do executor quản lý | Queue không giới hạn, task bị reject, transaction context không tự chuyển |
| **QueueChannel** | Buffer message rồi receiver/poller lấy | Điều tiết producer/consumer qua capacity và receive rate | In-memory queue không durable theo mặc định; queue đầy gây block/drop tùy caller |
| **PublishSubscribeChannel** | Fan-out đến nhiều subscriber | Có thể sync hoặc async tùy cấu hình | Một subscriber chậm/lỗi ảnh hưởng các nhánh khác |
| **PriorityChannel** | Sắp thứ tự theo ưu tiên | Có thể starvation khi nhiều message ưu tiên cao | Thứ tự nghiệp vụ bị đảo, nhóm thấp bị đói |
| **RendezvousChannel** | Handoff trực tiếp khi sender/receiver gặp nhau | Sender có thể block chờ receiver | Deadlock hoặc timeout nếu không có receiver |

### 5.1. `DirectChannel`: đơn giản nhưng backpressure truyền ngược

~~~text
SFTP poller thread
  -> DirectChannel
     -> validate
        -> JDBC insert
           -> HTTP outbound gateway
              -> response
~~~

Nếu HTTP mất 20 giây, poller thread có thể bị giữ cho đến khi handler trả về. Đó là backpressure tự nhiên, nhưng nếu cùng scheduler phụ trách nhiều poller, **một dependency chậm có thể khiến các poller khác trễ lịch**.

Ưu điểm: dễ hiểu transaction/error propagation trong đường đồng bộ. Nhược điểm: không tách chặng I/O dài và có thể giữ thread nguồn.

### 5.2. `ExecutorChannel`: tách thread không đồng nghĩa có độ bền

~~~text
Inbound poller -> ExecutorChannel
                     |
               bounded executor
                 8 workers
                queue max 64
                     |
                outbound HTTP
~~~

Cần cấu hình:

- Core/max threads theo workload;
- Queue capacity hữu hạn;
- Rejection policy có thể giải thích;
- Shutdown behavior và await termination;
- Monitoring active threads, queue depth, task rejection;
- Transaction/correlation context propagation có chủ đích.

**Lưu ý:** Transaction thường gắn với thread. Đưa message qua ExecutorChannel có thể làm thay đổi nơi transaction bắt đầu/kết thúc và cách lỗi trả ngược nguồn; không được coi `@Transactional` upstream tự bao mọi handler async.

### 5.3. `QueueChannel`: cần phân biệt memory và persistence

Nếu dùng in-memory QueueChannel, message **có thể mất khi process chết** dù đã được enqueue thành công. Với dữ liệu nghiệp vụ quan trọng cần:

- Dùng persistent `MessageStore` phù hợp hoặc broker durable;
- Hiểu transaction khi enqueue/dequeue và trạng thái message source ack;
- Đặt capacity và send timeout;
- Có chính sách khi buffer đầy;
- Có resume/drain và DLQ/replay;
- Thử crash ngay sau sender nhận “send thành công”.

Tương tự, một queue bền vững không bảo đảm consumer side effect exactly-once. Cần idempotency khi redelivery.

### 5.4. Không chuyển sang async chỉ để tránh timeout

Nếu HTTP inbound gateway chờ reply, thêm ExecutorChannel có thể giải phóng một số thread phía handler nhưng **caller vẫn có reply deadline**. Nếu nghiệp vụ dài, thiết kế request accepted + durable tracking/status có thể phù hợp hơn; thay channel không tự biến nghiệp vụ đồng bộ thành hợp đồng bất đồng bộ hoàn chỉnh.

## 6. Poller: giới hạn lượng lấy và số task phát sinh

### 6.1. Những thuộc tính khác nhau

| Điều khiển | Tác dụng | Không thay thế |
|---|---|---|
| Poll interval / fixed delay | Tần suất kiểm tra nguồn | Timeout của SFTP/JDBC operation |
| Fixed rate/cron | Lịch kích hoạt | Bảo đảm không overlap ở mọi cấu hình |
| `maxMessagesPerPoll` | Giới hạn số message được lấy mỗi lần poll | Giới hạn số worker/chặng downstream |
| Receive timeout | Giới hạn chờ một lần lấy item ở pollable source | Hạn mức side effect toàn luồng |
| Poller `TaskExecutor` | Cho phép xử lý task theo executor được cấu hình | Distributed locking trên nhiều pod |
| Scheduler pool size | Số task polling có thể chạy theo scheduler | Connection pool của hệ nguồn |
| Transactional polling | Quản lý transaction quanh poll theo cơ chế thích hợp | Exactly-once xuyên external systems |

### 6.2. Vì sao `maxMessagesPerPoll` chưa đủ?

Một poller lấy tối đa 20 message mỗi 5 giây có thể phát 20 task vào ExecutorChannel ngay lập tức. Nếu mỗi task cần 30 giây HTTP và executor có queue lớn, số pending tasks tăng qua nhiều lần poll. Phải kết hợp:

- Batch max và poll interval;
- Bounded executor queue;
- Chặng downstream concurrency limit;
- Khi queue gần đầy, pause/throttle nguồn;
- Retry/backoff owner;
- Service-level SLO và backlog age.

**Trong môi trường có 4 replica**, `maxMessagesPerPoll=20` trên mỗi replica có thể tạo nhiều hơn 20 item cho toàn cụm. Cần tính **replica count × per-instance effective work**, không coi cấu hình một pod là cluster quota.

### 6.3. Ví dụ Java DSL cho File inbound

~~~java
import java.io.File;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;

@Configuration
class FileIngressFlowConfig {

    @Bean
    MessageChannel readyFiles() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow readyFileIngress() {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(new File("/srv/inbox/ready"))
                         .patternFilter("*.ready"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofSeconds(5))
                               .maxMessagesPerPoll(10)
                    )
                )
                .channel("readyFiles")
                .get();
    }
}
~~~

Đây là ví dụ **cấu trúc** của inbound adapter và poller, chưa đủ production: cần handler, file-ready protocol, persistent filter/claim, error flow, idempotency, archive/replay, multi-replica và metrics. API của DSL phải được kiểm tra với version Spring Integration trong project.

### 6.4. Checklist poller

- [ ] Lịch đọc nguồn phù hợp arrival rate và xử lý downstream.
- [ ] Có `maxMessagesPerPoll` hoặc batch limit hiệu quả.
- [ ] Có giới hạn tổng inflight cả cluster, không chỉ một replica.
- [ ] Không tạo overlapping scan/transfer nếu remote chưa hoàn tất.
- [ ] Có pause/resume, metric backlog và alert oldest pending.
- [ ] Nguồn có khả năng giữ message khi poller tạm dừng.
- [ ] Có distributed claim/partition nếu nhiều replica đọc cùng file/row.
- [ ] Có test network timeout/slow read và scheduler starvation.
- [ ] Khi queue đầy không ack hoặc đánh dấu source item DONE sai.

## 7. TaskExecutor và TaskScheduler: đặt giới hạn rõ

### 7.1. ThreadPoolTaskExecutor có bounded queue

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean(name = "partnerIoExecutor")
ThreadPoolTaskExecutor partnerIoExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("partner-io-");
    executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    executor.initialize();
    return executor;
}
~~~

**Ý nghĩa minh họa:**

- Pool có ít nhất 8 core threads; max 16 khi áp lực đủ và queue policy cho phép.
- Queue capacity 64 giới hạn số task chờ trong executor.
- Khi executor không nhận được task nữa, `AbortPolicy` từ chối; đường gọi phải **xử lý rejection** và bảo đảm nguồn chưa ack/đã có durable recovery.
- Graceful shutdown cố đợi task đang có trong giới hạn được cấu hình.

**Cảnh báo quan trọng:** Với các ThreadPoolExecutor có queue dương, executor có thể ưu tiên đưa task vào queue **trước khi** tăng thread vượt core pool. Do đó đặt core=8, max=16, queue=64 không có nghĩa vừa có 9 task sẽ lập tức chạy 9 threads. Phải load test hành vi tăng pool/queue của `ThreadPoolTaskExecutor` theo phiên bản.

### 7.2. Chọn rejection policy

| Policy | Hành vi | Rủi ro |
|---|---|---|
| `AbortPolicy` | Ném lỗi khi không nhận task | Cần error/retry/ack handling để không mất message |
| `CallerRunsPolicy` | Chạy task trong thread gọi nếu executor còn hoạt động theo semantics policy | Có thể block poller/HTTP ingress, thay đổi thread/transaction boundary |
| `DiscardPolicy` | Bỏ task mà không báo theo semantics policy | **Không phù hợp** nếu message cần xử lý đáng tin |
| `DiscardOldestPolicy` | Bỏ task đang chờ để thử thêm task mới | Có nguy cơ mất message hoặc đảo thứ tự |

Không chọn `CallerRunsPolicy` tự động cho mọi luồng. Nó có thể tạo backpressure hữu ích nhưng cần test **source ack, transaction, thread ownership và shutdown**; một thread HTTP inbound bị gọi làm xử lý dài có thể vượt gateway SLA.

### 7.3. TaskScheduler có thể thành điểm nghẽn

Một ứng dụng có nhiều poller cùng dùng một scheduler nhỏ. Nếu mỗi poll chiếm scheduler thread lâu vì remote SFTP/JDBC chậm, lịch các poller khác bị trễ.

Checklist:

- [ ] Xác định poller nào dùng scheduler nào.
- [ ] Scheduler pool size dựa trên số task có thể block và service time.
- [ ] Với I/O chậm, cân nhắc tách scheduler và worker executor có bounded queue.
- [ ] Không để thread scheduler chờ vô hạn vào remote.
- [ ] Có metric về poll delay/actual execution duration và skipped/overlapping tasks.
- [ ] Test khi nhiều poller cùng bị lỗi remote.
- [ ] Khi scale nhiều replica, không nhân tổng poll rate vượt quota nguồn.

### 7.4. Tránh trộn CPU-bound và I/O-bound vào một pool

- CPU-bound validation/serialization có thể tận dụng số core hữu hạn.
- I/O-bound HTTP/SFTP/JDBC thường chờ remote; concurrency có thể cao hơn số core nhưng giới hạn bởi connection pool, quota và memory.
- Một pool chung cho công việc CPU nặng và I/O bị treo có thể gây starvation cho cả hai.
- Tách pool theo criticality/target giúp bảo vệ nghiệp vụ quan trọng, nhưng phải quan sát **tổng** thread/memory của process.

## 8. Connection pool: số lượng, vòng đời và phương án khi cạn

### 8.1. Bốn nhóm quyết định

Mỗi pool phải có:

1. **Max active/leased connections:** Tránh mở quá số session downstream chịu được.
2. **Acquisition timeout:** Không cho caller chờ vô hạn khi pool cạn.
3. **Idle eviction/connection lifetime/validation:** Tránh tái sử dụng kết nối chết và rò rỉ.
4. **Shutdown/reconnect policy:** Đóng tài nguyên an toàn, không tạo connection storm khi deployment/recovery.

### 8.2. Connection pool khác retry

Một downstream I/O call timeout có thể làm pool connection bị đánh dấu hỏng và cần reconnect. Nếu retry ở cùng thread với connection vẫn bị giữ, tải sẽ tăng; timeout dài có thể giữ pool đầy trong khi không có request hữu ích.

Pool wait time cao nên được xử lý bằng **giảm inflight hoặc tăng capacity có kiểm chứng**, không bằng cách chỉ nâng acquisition timeout.

### 8.3. Capacity ngân sách toàn cụm

Giả sử database cho phép **100 connections** cho nhóm ứng dụng và còn hệ khác cùng dùng. Sau khi trừ connection cho dịch vụ khác, admin, migration và headroom, nhóm ứng dụng chỉ được phép sử dụng tối đa 60.

Nếu triển khai **5 replica**, chọn Hikari maximum pool size 12 mỗi pod đã dùng hết quota 60 trong trường hợp tất cả connection được tạo. Tăng replicas lên 10 mà không điều chỉnh pool size có thể làm DB vượt giới hạn, kể cả mỗi pod chỉ có vài worker đang hoạt động.

| Biến | Giá trị giả định |
|---|---:|
| DB max connections | 100 |
| Dự phòng cho hệ khác/ops/headroom | 40 |
| Ngân sách ứng dụng | 60 |
| Số replica dự kiến | 5 |
| Max pool size/replica | 12 |
| Tổng kết nối tối đa của ứng dụng | 60 |

Các giá trị chỉ là **minh họa về ngân sách**. Database còn có giới hạn CPU, I/O, lock contention và transaction; pool 60 không chứng minh hệ DB chịu được 60 query nặng đồng thời.

### 8.4. Công thức giới hạn đồng thời theo downstream

Nếu mỗi task đang giữ một HTTP/DB connection:

\[
C_{\mathrm{effective}} \le \min(C_{\mathrm{executor}}, C_{\mathrm{pool}}, C_{\mathrm{downstream}}, C_{\mathrm{policy}}).
\]

Nhưng nếu một task giữ **hai connection cùng lúc** hoặc client multiplex nhiều request trên một connection, công thức phải được điều chỉnh theo behavior thực. Đừng giữ JDBC connection trong khi chờ HTTP response nếu có thể tách transaction và side effect hợp lý.

### 8.5. Checklist chung

- [ ] Có owner và quota cho từng pool/target.
- [ ] Tính cả max replica khi autoscaling/rolling deployment.
- [ ] Pool acquisition timeout không vượt request deadline.
- [ ] Có validation/idle/lifetime policy theo client và server.
- [ ] Có metric active, idle, pending và wait duration.
- [ ] Có test connection leak, network half-open và reconnect storm.
- [ ] Không dùng admin credential dùng chung cho tất cả adapter.
- [ ] Khi pool cạn, caller có error/recovery path, không block vô hạn.
- [ ] Pool shutdown đóng socket/session đúng lifecycle.
- [ ] Ghi rõ sự khác biệt giữa connection count và max concurrent operations ở protocol có multiplexing.

## 9. Backpressure: cần cơ chế kết thúc khi hết sức chứa

Một hệ thống không có giới hạn thực tế sẽ chuyển bottleneck thành memory leak, timeout storm hoặc bão retry. Backpressure cần được thiết kế từ ingress tới egress.

### 9.1. Các cách giảm tải

| Cách | Hoạt động | Khi phù hợp |
|---|---|---|
| **Bounded channel/executor queue** | Giới hạn message/task đang chờ | Tránh memory tăng không kiểm soát |
| **Pause/throttle poller** | Giảm số item được lấy từ nguồn | Nguồn file/DB/broker giữ dữ liệu được |
| **Semaphore/bulkhead** | Giới hạn số thao tác đồng thời vào target | HTTP/SFTP/DB partner có quota rõ |
| **Rate limiter** | Giới hạn lời gọi theo thời gian | API quota/minute, broker throughput |
| **Circuit breaker** | Tạm ngưng gọi khi target lỗi nghiêm trọng | Remote outage kéo dài |
| **Durable broker/inbox** | Lưu message bền vững trước xử lý | Chênh lệch tốc độ đến/đi kéo dài |
| **Reject with retryable response** | Trả lỗi có kiểm soát cho caller | HTTP inbound có contract và idempotency |
| **Cooperative consumer pause** | Tạm dừng nhận/processing theo API hỗ trợ | Kafka/JMS/AMQP có hành vi container cụ thể |

### 9.2. Không “đánh rơi” message sau khi đã ack

Nếu message đã được nhận và nguồn coi đã hoàn thành, sau đó `ExecutorChannel` reject task mà không có durable recovery, hệ có nguy cơ **mất message**.

Nguyên tắc:

1. Nếu nguồn còn giữ message, cho phép failure/rollback/nack để redeliver theo chính sách.
2. Nếu đã ack nguồn, phải có một **durable handoff** trước đó.
3. Nếu chỉ lưu in-memory queue, xác định crash-recovery contract; không gọi đó là durable.
4. Nếu retry dài, đẩy vào durable retry queue/outbox thay vì ngủ trong thread giữ connection.
5. Nếu lỗi dữ liệu, chuyển DLQ/quarantine có owner và evidence.

### 9.3. Backpressure không đồng nghĩa rate limit

**Concurrency limit** giữ tối đa 10 request cùng lúc. Nếu mỗi request mất 100 ms, có thể phát 100 request/s. **Rate limit** 30 request/s thì ngăn vượt quota ngay cả khi concurrency thấp. Nhiều đối tác áp cả hai loại. Phải có **hai kiểm soát** khi cả hai giới hạn tồn tại.

### 9.4. Fairness và noisy neighbors

Một tenant gửi một triệu record có thể chiếm hết worker và connection, làm những tenant khác không xử lý được.

- Phân queue/cohort theo tenant hoặc priority được duyệt;
- Đặt per-tenant max inflight và rate limit;
- Duy trì reserved capacity cho luồng quan trọng;
- Tránh starvation của message ưu tiên thấp;
- Giám sát lag/oldest age theo nhóm;
- Không tạo nhiều per-tenant thread pool quá mức khiến tổng thread vượt giới hạn process.

**Fair scheduling là một chính sách vận hành**, cần thực thi bằng cấu trúc queue/worker/limiter phù hợp; không phải tính năng tự động của mọi MessageChannel.

## 10. File adapter: concurrency, filesystem và nhiều replica

File inbound khác broker: file nằm trong một thư mục, không có cơ chế consumer group phân chia công việc mặc định. Mở nhiều poller trên cùng thư mục có thể làm nhiều instance cùng nhận một file.

### 10.1. Các giới hạn cần xác định

| Tài nguyên | Cách tính/sizing | Failure mode |
|---|---|---|
| Số directory scan | Poll interval, scheduler capacity, directory size | Mỗi lượt scan kéo dài, lịch quét chồng |
| Số file được pick mỗi poll | Batch/maxMessagesPerPoll | Bùng nổ task và memory |
| Số file đang parse | CPU, memory, file descriptors | Parser giữ nhiều tệp lớn |
| Số file đang xử lý nghiệp vụ | Worker pool + DB/HTTP capacity | Business commit chậm tạo backlog |
| File descriptors/open streams | OS/container limits | Too many open files |
| Disk/inode space | Source file, archive, failed/quarantine, temp | Ghi/trích xuất thất bại |
| Multi-replica claim | Distributed lock/metadata/inbox | Duplicate hoặc lost handoff |

### 10.2. Một file lớn có thể là tải khác 1.000 file nhỏ

Nếu `maxMessagesPerPoll=20` nhưng mỗi file có 500 MB, việc lấy 20 file vào các handler có thể làm cạn heap/disk/FD. Cần:

- Giới hạn file size, row count và memory dùng cho parse;
- Streaming parser khi khả thi thay vì đọc toàn bộ bytes vào heap;
- Max concurrent files theo kích thước/loại;
- Bounded executor, rate limit downstream;
- Timeout/ready protocol để tránh file đang ghi;
- Archive/quarantine không mất dữ liệu.

### 10.3. Nhiều replica

- Dùng **persistent accept-once metadata** trong store thích hợp khi muốn giữ dấu vết qua restart, nhưng metadata filter không thay thế business idempotency.
- Với multi-replica, cần shared/distributed claim/lock, phân vùng directory hoặc cơ chế coordinator.
- Khi file được claim nhưng worker crash, phải có lease/recovery và business dedupe key.
- Đừng đánh dấu DONE trước khi side effect nghiệp vụ hoàn thành bền vững.
- Nếu dùng NFS/SMB/network mount, thử semantics rename/lock và hành vi khi mất mạng.
- Ghi source file ID + checksum/business ID để điều tra khi hai file trùng tên/nội dung.

### 10.4. Checklist File

- [ ] Scan/poll rate phù hợp quy mô thư mục và tốc độ file mới.
- [ ] Có giới hạn số file đang parse và dung lượng/FD.
- [ ] Có cơ chế file ready, không đọc upload dở.
- [ ] Nhiều pod không cùng xử lý file ngoài thiết kế.
- [ ] File chưa hoàn thành được giữ/recover sau restart.
- [ ] Có idempotency key ở nghiệp vụ, không chỉ accept-once filter.
- [ ] Có metrics oldest pending file, processing files, failure/quarantine và disk capacity.

## 11. SFTP: giới hạn session/transfer trước khi tăng workers

SFTP hoạt động trên SSH session và remote server thường có quota connection/session/channel. Tăng threads của app không đồng nghĩa server cho phép nhiều transfer.

### 11.1. SFTP session và connection pool

Tùy client/session factory, có thể tồn tại:

- TCP/SSH connection tới remote server;
- SSH channels/SFTP subsystem sessions;
- Session cache/pool với giới hạn;
- Thread/blocking I/O đọc remote directory hoặc file;
- Remote upload/download đang inflight;
- Local filesystem destination và disk buffer.

**Không đồng nhất “một session = một TCP connection”** trong mọi underlying SSH implementation. Cần kiểm tra giới hạn thật do library/server công bố và đo số connection/channel thực tế.

Các lớp như `DefaultSftpSessionFactory` và `CachingSessionFactory` xuất hiện trong Spring Integration SFTP, nhưng API và hành vi chi tiết thay đổi theo phiên bản, đặc biệt khi underlying SSH client thay đổi. Kiểm tra cách cấu hình **cache size, wait timeout, shared session, session validation, close/reconnect** theo version.

### 11.2. Công thức ngân sách minh họa

Giả sử đối tác chỉ cho **12 concurrent transfers** trên một account. Ứng dụng có ba replicas, có thể phân bổ tối đa bốn transfer/replica trong trạng thái thông thường. Tuy nhiên cần dự phòng cho reconnect, maintenance, tác vụ khác dùng cùng tài khoản và burst khi rolling deployment.

| Giá trị giả định | Mức |
|---|---:|
| Remote quota concurrent transfers | 12 |
| Replica chạy đồng thời trong rolling deploy | 4 (bao gồm pod cũ + mới) |
| Giới hạn transfer/pod theo ngân sách thận trọng | 2 |
| Tổng concurrency dự kiến | 8 |
| Phần dành cho headroom/ops | 4 |

Đây là ví dụ **chia ngân sách**, không phải khuyến nghị chung. Nếu quota tính theo account trên toàn cluster, local per-pod semaphore **không đủ** khi autoscaler vượt số replica dự kiến; cần distributed coordination hoặc luôn giới hạn HPA/deployment.

### 11.3. Timeout và session lease

- [ ] Session acquisition wait có giới hạn để worker không chờ mãi khi pool đầy.
- [ ] Có connect, SSH handshake, remote operation timeout theo client capabilities.
- [ ] Session lỗi được invalidate/reconnect đúng cách, không trả về cache như connection khỏe.
- [ ] Retry/backoff có jitter, không tạo hàng loạt reconnect khi SFTP vừa phục hồi.
- [ ] Khi worker giữ session trong khi parse file hoặc gọi HTTP, cân nhắc tách giai đoạn: tải hoàn tất rồi đóng/return session sớm.
- [ ] Có max inflight bytes/file size và local disk quota.
- [ ] Có metrics active/idle/waiting session, transfer duration, error và remote throttling.
- [ ] Có test server hạn chế session, rớt mạng giữa transfer, pod scale lên và credential rotation.

### 11.4. SFTP outbound

Nếu outbound adapter ghi file rồi timeout lúc rename, retry có thể tạo bản trùng. Concurrency tăng làm nguy cơ hai workers cùng dùng final filename lớn hơn. Cần deterministic naming, temporary file + rename, điều kiện không ghi đè dữ liệu không cùng version, checksum/manifest và đối soát remote state sau ambiguous outcome.

## 12. HTTP: connection pool, request concurrency và quota đối tác

HTTP outbound gateway có thể dùng `RestTemplate`, `RestClient`, `WebClient` hoặc client khác. Tùy implementation:

- Có thể có **connection pooling** hoặc tạo kết nối mỗi request;
- HTTP/1.1 thường có số socket/connection gắn với concurrent request theo cách client sử dụng;
- HTTP/2 có thể multiplex nhiều streams trên một kết nối;
- Có giới hạn **per-route/per-host** và tổng connections, pending-acquisition queue;
- Non-blocking I/O có thể giảm số threads, nhưng không xóa quota inflight/request hoặc memory.

### 12.1. Những tầng cần kiểm soát

| Tầng | Giới hạn | Rủi ro |
|---|---|---|
| Inbound HTTP server | Request thread/event loop, max connections, request size | Client flood làm cạn tài nguyên |
| Spring Integration gateway | Reply timeout, correlation, concurrent requests | Reply trễ, backlog nhiều |
| Worker executor | Active threads, queue capacity | Hàng chờ vô hạn |
| HTTP connection manager | Total/per-route connection, pending acquire, idle/lifetime | Pool starvation và connection leak |
| Partner API | Max concurrent requests, rate per minute, quota per tenant | 429, 503, ban/throttle |
| Circuit/bulkhead | Max active/queued calls | Đối tác lỗi kéo cả ứng dụng |
| Business idempotency | Request ID, operation state | Retry gây tác động trùng |

### 12.2. Concurrency khác rate limiting

Ví dụ đối tác có **20 concurrent requests** và **100 calls/s**. Với response trung bình 0,5 s, để đạt 100 calls/s có thể cần khoảng 50 inflight; điều này vượt giới hạn 20, nên throughput thực tế bị chặn bởi concurrency. Khi latency tăng đến 2 s, 20 inflight chỉ tương đương khoảng 10 calls/s trong điều kiện đơn giản.

Không chỉnh executor 100 threads chỉ để đạt rate target khi quota/latency không cho phép.

### 12.3. Checklist HTTP outbound

- [ ] Biết client/request factory thật và semantics pooling/multiplexing.
- [ ] Có max total/per-route connections hoặc max streams phù hợp.
- [ ] Có pool acquisition timeout, connect/read/response timeout và overall deadline nếu được hỗ trợ.
- [ ] Max inflight riêng từng partner; không chỉ một pool chung cho cả công ty.
- [ ] Có rate limit theo quota của đối tác, chia ngân sách qua replicas.
- [ ] Retry/backoff dùng jitter, không chiếm toàn bộ worker khi 429/503.
- [ ] Khi timeout/response mất, có idempotency/reconciliation trước retry unsafe operation.
- [ ] Có metrics leased/idle/pending, acquisition wait, 429/503, request latency và request queue.
- [ ] Có test slow server, half-open sockets, pool leak và remote connection limits.

### 12.4. HTTP inbound gateway

Khi ingress nhận nhiều requests mà downstream chậm:

- Trả 429/503/202 hoặc cơ chế phù hợp **theo API contract** thay vì giữ tất cả request trong heap;
- Nếu xử lý bất đồng bộ, phải lưu yêu cầu bền vững trước khi báo Accepted;
- Bảo vệ per-client/tenant quota và authentication;
- Có idempotency key cho request có side effect;
- Không dùng `CallerRunsPolicy` bừa bãi khiến request servlet thread chạy business lâu hơn deadline;
- Theo dõi active requests, rejected requests và business completion latency.

## 13. JMS: consumer concurrency, prefetch và session transaction

Với JMS inbound listener, connection/session/consumer và broker dispatch policy do JMS provider và container chi phối. **Số consumer không phải số connection TCP** một cách phổ quát.

### 13.1. Giới hạn cần phân biệt

| Điều khiển | Ảnh hưởng | Phụ thuộc |
|---|---|---|
| Listener concurrency | Số consumer/session xử lý đồng thời | JMS listener container |
| Connection factory/pool | Connection/session caching, max sessions | Broker/provider/client |
| Prefetch/consumer window | Số message được đưa trước cho consumer | Provider configuration |
| Ack/transaction | Khi message được broker coi hoàn tất | Session mode và transaction manager |
| Queue/topic subscription | Cách phân phối message giữa consumers | JMS semantics, durable subscription |
| Handler executor | Số business tasks và cách propagate lỗi | Spring Integration channel/handler |
| DLQ/redelivery | Số lần broker gửi lại và hành vi khi lỗi | Provider-specific policy |

### 13.2. Prefetch nhiều có thể làm thiếu công bằng

Một consumer có prefetch lớn có thể giữ nhiều message **đã dispatch nhưng chưa xử lý**, khiến consumer khác không nhận đủ việc hoặc queue depth trông nhỏ dù thực tế backlog lớn.

Khi worker xử lý chậm, cần quan sát:

- Queue ready/pending count;
- Dispatched/unacked message;
- Consumer active/idle;
- Processing latency;
- Redelivery và DLQ age.

Không đặt prefetch cao chỉ để tăng throughput. Nếu thông điệp cần ordering, tăng concurrency có thể thay thứ tự xử lý theo cách ứng dụng nhìn thấy.

### 13.3. Checklist JMS

- [ ] Listener concurrency có giới hạn theo capacity business handler và DB/HTTP target.
- [ ] Connection/session pool sizing đúng khả năng JMS provider.
- [ ] Prefetch/consumer window có cơ sở đo tải.
- [ ] Session transaction/ack và redelivery được hiểu rõ.
- [ ] Có idempotent consumer khi broker redeliver sau DB commit.
- [ ] Khi saturation, biết listener có thể pause/stop và broker còn giữ message.
- [ ] Có DLQ, bounded redelivery, runbook replay, owner.
- [ ] Test broker outage, listener crash, scale consumer và ordering/SoD của nghiệp vụ.
- [ ] Có alert ready/unacked, consumer lag/age, connection count và session failures.

## 14. AMQP/RabbitMQ: prefetch, consumers và unacked inflight

Với RabbitMQ, prefetch và số consumer cùng quyết định lượng message có thể được delivery nhưng chưa acknowledged. Một ước lượng đơn giản khi prefetch áp theo consumer:

\[
M_{\mathrm{unacked,upper}} \approx N_{\mathrm{consumers}}\times P_{\mathrm{prefetch}},
\]

với giả định **prefetch count được áp theo từng consumer** trong topology cụ thể. Hành vi chính xác của global vs per-consumer prefetch và client phải được kiểm tra theo RabbitMQ/Spring AMQP version.

Ví dụ 6 consumers × prefetch 20 có thể giữ tới khoảng **120 unacked messages**. Nếu mỗi message chứa payload lớn, memory và thời gian chờ có thể tăng ngay cả khi consumer thread pool nhỏ.

### 14.1. Các tham số cần review

- Số concurrent consumers và max consumers nếu container hỗ trợ dynamic scaling;
- Prefetch count theo queue/consumer và payload size;
- Acknowledgement mode (auto/manual tùy container);
- QoS/consumer dispatch behavior của broker;
- Broker connection/channel limits;
- Publisher connection pool và publisher confirms/returns;
- RabbitMQ queue depth, ready/unacked split, DLQ;
- Requeue/retry/delayed-message behavior khi consumer lỗi.

### 14.2. Checklist AMQP

- [ ] Có quota consumers và prefetch; tính tổng across all replicas.
- [ ] Không tối ưu riêng ready queue depth mà bỏ unacked count.
- [ ] Không ack sớm để làm đẹp metric throughput.
- [ ] Listener retry/error handler không requeue poison message vô hạn.
- [ ] Consumer idempotent với redelivery và publisher duplicate.
- [ ] Có bounded outbound publishes và confirms tracking.
- [ ] Đã thử nhiều replica, broker flow control, queue overload và delayed retry.
- [ ] Khi scale, thứ tự xử lý và hiệu ứng trên per-key sequence được chấp thuận.
- [ ] Có alerts ready, unacked, consumer utilization và message age.

### 14.3. Prefetch bằng 1 có phải luôn tốt?

Không. Prefetch rất thấp giảm số unacked, có thể tăng fairness, nhưng gây throughput kém khi round-trip/processing overhead cao. Prefetch quá lớn tăng inflight và memory, và có thể làm một consumer giữ quá nhiều message. Cần tìm cân bằng bằng **load test với payload, handler duration và ack semantics thực tế**.

## 15. Kafka: partition quyết định concurrency hữu ích

Kafka consumer group nhận partition để đọc. Với một topic có **P partitions**, số consumer trong cùng group vượt quá P thường không làm tăng số partition được xử lý đồng thời cho topic đó, vì mỗi partition được giao cho một consumer tại một thời điểm trong group.

### 15.1. Quy tắc cơ bản

- Ordering được bảo toàn **trong một partition** theo thứ tự log, không có thứ tự toàn topic.
- Nếu cùng business key cần thứ tự, producer phải dùng partitioning phù hợp.
- Tăng listener concurrency vượt số partitions không tăng throughput cho cùng assignment đơn giản.
- Khi một record xử lý quá lâu, consumer có thể gặp vấn đề liên quan `max.poll.interval.ms` hoặc rebalances.
- Processing async nhiều record trong một partition có thể phá ordering/offset safety nếu ack không được điều phối.
- Retry/DLT thay đổi tiến độ partition; phải có policy cho poison record và version gating.

### 15.2. Kafka producer cũng có giới hạn

Kafka producer có buffer, batching, số in-flight requests, retries và delivery timeout. Không phải tăng concurrency ở `ExecutorChannel` là sẽ có thêm nhiều broker connections hoặc throughput tuyến tính. Producer có thể đang bị giới hạn bởi:

- Partition count và broker throughput;
- `buffer.memory`, `batch.size`, `linger.ms` và `max.block.ms` theo client;
- Record size, compression, serialization;
- `max.in.flight.requests.per.connection` và retry/ordering semantics của Kafka client;
- Broker quota, network bandwidth, acks và replication;
- Callback/completion handling và outbox backlog.

### 15.3. Ví dụ partition/consumer

| Cấu hình | Số partitions | Consumer trong group | Ghi chú |
|---|---:|---:|---|
| A | 6 | 1 | Một consumer có thể xử lý nhiều partitions |
| B | 6 | 3 | Chia partitions cho 3 consumers |
| C | 6 | 6 | Tối đa 6 consumers có partitions trong trường hợp đơn giản |
| D | 6 | 12 | Nhiều consumers có thể idle trong group |
| E | 24 | 12 | Có thêm khả năng phân chia, nhưng cần đánh giá tải/broker/key skew |

Ví dụ đơn giản hóa cho một topic và group, không áp dụng máy móc cho consumer subscribe nhiều topic/assignments phức tạp.

### 15.4. Checklist Kafka

- [ ] Concurrency listener phù hợp tổng partitions và tải thực.
- [ ] Producer key theo business ordering requirement.
- [ ] Consumer lag được đo theo partition, phát hiện hot partition.
- [ ] Batch/poll processing time tương thích `max.poll.interval.ms`.
- [ ] Nếu listener async, offset/ack không vượt record chưa xử lý bền vững.
- [ ] Retry/DLT có policy ordering và idempotency.
- [ ] Producer buffer/batching/inflight/retries theo Kafka client version.
- [ ] Có metrics lag, rebalance, bytes in/out, publish latency, error và outbox age.
- [ ] Test consumer group scale-in/out, broker failover, poison record, commit ambiguity.
- [ ] Không dùng quá nhiều consumers chỉ để “tăng throughput” khi bottleneck là database hoặc HTTP.

## 16. JDBC: HikariCP max pool size không thay xử lý contention

JDBC inbound/outbound adapter dùng một `DataSource`/connection pool mà toàn ứng dụng có thể chia sẻ. Trong nhiều dự án Spring Boot, `HikariCP` là implementation phổ biến; phải xem cấu hình thật và tổng các process cùng dùng database.

### 16.1. Connection pool budget

| Thuộc tính | Ý nghĩa | Sai lầm thường gặp |
|---|---|---|
| `maximumPoolSize` | Số connection tối đa trong pool | Đặt 100 mỗi pod dù DB chỉ chịu 100 tổng |
| `minimumIdle` | Mức idle connection tối thiểu khi được cấu hình | Nhầm với max active workload |
| `connectionTimeout` | Chờ lấy connection từ pool | Nhầm thành query timeout |
| `validationTimeout` | Chờ kiểm tra connection hợp lệ | Nhầm thành transaction timeout |
| `idleTimeout` | Vòng đời connection idle theo semantics pool | Dùng để cắt query treo |
| `maxLifetime` | Giới hạn vòng đời pool connection | Nhầm thành thời hạn của mỗi SQL |
| Leak detection threshold | Hỗ trợ phát hiện connection giữ bất thường | Thay thế việc close/transaction đúng |

### 16.2. Ví dụ Spring Boot Hikari property

~~~yaml
# Ví dụ Spring Boot + HikariCP; phải đối chiếu version và DB quota.
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 2000
      validation-timeout: 1000
      max-lifetime: 1800000
~~~

Các con số **mang tính minh họa**; một số thuộc tính trên sử dụng **mili-giây** theo Hikari config. Không copy làm cấu hình tối ưu chung. `maxLifetime` nên phối hợp với timeout phía DB/proxy/network và cần xác minh với vendor.

### 16.3. Giữ connection càng ngắn càng tốt

**Thiết kế dễ gây nghẽn:**

~~~text
BEGIN DB transaction
 -> SELECT/UPDATE order
 -> gọi HTTP đối tác 8 giây (giữ DB connection + lock)
 -> publish Kafka
 -> COMMIT
~~~

Nếu HTTP chậm, toàn bộ DB pool có thể bị giữ, gây lock contention và timeouts.

**Thiết kế nên cân nhắc:**

~~~text
BEGIN DB transaction
 -> validate/UPDATE order
 -> INSERT outbox event
COMMIT

Outbox worker -> HTTP/Kafka with independent retry and idempotency
~~~

Không phải lúc nào cũng có thể tách quy trình như vậy vì business consistency; nhưng nếu dùng transaction dài, phải chứng minh timeout, lock, retry, connection capacity và deadlock behavior.

### 16.4. JDBC inbound polling với nhiều workers

Nếu nhiều poller cùng thực hiện `SELECT ... WHERE status='NEW'` rồi xử lý ngoài transaction, cùng một row có thể bị chọn nhiều lần. Phải có cơ chế:

- Claim/lock row theo database dialect;
- Lease owner và `leaseUntil` cho recovery;
- Unique processing key/idempotent business mutation;
- Giới hạn batch và max in-progress rows;
- Reclaim lease quá hạn, nhưng tránh hai workers đồng thời thực thi side effect mà không có fencing;
- Index/SQL plan phù hợp và giới hạn lock duration;
- Metrics NEW/PROCESSING/FAILED row age.

~~~sql
-- Pseudo-SQL: cú pháp locking và giới hạn row phụ thuộc DB.
BEGIN TRANSACTION;

SELECT id
FROM integration_inbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;

-- Giới hạn batch theo dialect.
-- UPDATE ID đã claim -> PROCESSING với lease owner/version.

COMMIT;
~~~

`SKIP LOCKED` không được hỗ trợ giống nhau ở mọi database, và claim thành công không thay thế idempotency. Cần test failure window khi worker hết lease nhưng vẫn gọi HTTP remote.

### 16.5. Checklist JDBC

- [ ] Tính tổng `maxPoolSize` theo max replicas, rolling deploy và các app dùng chung DB.
- [ ] Pool acquisition timeout nhỏ hơn operation deadline phù hợp.
- [ ] Query/lock/transaction timeout, index và batch size được thử trên dữ liệu production-like.
- [ ] Connection pool shared giữa web requests và integration jobs được phân bổ hợp lý hoặc tách khi cần.
- [ ] Không giữ connection qua remote I/O dài ngoài yêu cầu.
- [ ] Có claim/lease và idempotency khi nhiều pollers.
- [ ] Có metrics active/idle/pending/wait, slow SQL, deadlock/lock wait.
- [ ] Thử DB failover, pool saturation, connection leak, crash giữa commit/ack.

## 17. Luồng nhiều chặng: sizing theo bottleneck và tài nguyên chồng lấp

### 17.1. Case topology

~~~mermaid
flowchart LR
    S["SFTP 4 transfers"] --> F["File parse 8 workers"]
    F --> D["JDBC pool 12/pod"]
    D --> Q["Outbox persistent queue"]
    Q --> K["Kafka publisher bounded"]
    Q --> H["HTTP partner bulkhead 10"]
    H --> R["Partner API"]
    D --> DB["Database"]
~~~

Đây là số liệu mô phỏng theo **một pod**, không phải khuyến nghị. Hãy xác minh toàn cụm và nguồn phát tải thực tế.

### 17.2. Không giữ đồng thời hai tài nguyên đắt

Nếu một handler giữ JDBC connection trong khi chờ HTTP response, một request có thể chiếm **cả hai pool** trong một khoảng dài. Khi tải tăng:

- DB pool cạn dù truy vấn DB rất nhanh;
- HTTP pool pending tăng;
- Thread pool bị giữ bởi pool acquisition;
- Retry tăng và giữ thêm resources;
- Outbound event bị trễ hoặc mất nếu xử lý không có durable boundary.

Tách transaction và I/O bằng outbox hoặc workflow có checkpoint giúp giảm thời gian giữ DB connection, nhưng làm tăng yêu cầu idempotency, ordering và reconciliation.

### 17.3. Ngân sách nhiều replica

Giả sử thiết kế có 5 pods, mỗi pod:

| Tài nguyên | Giới hạn/pod | Tổng lý thuyết 5 pods |
|---|---:|---:|
| SFTP transfer | 2 | 10 |
| File parse workers | 8 | 40 |
| JDBC connections | 10 | 50 |
| HTTP concurrent partner A | 6 | 30 |
| Kafka consumer concurrency | 3 | 15 consumer threads |

Các tổng chỉ đúng nếu mỗi pod chạy đủ tải; với Kafka, tổng consumer threads vượt số partitions có thể không tăng số partitions xử lý. Với SFTP/HTTP quota toàn cụm, phải tính cả autoscaling tối đa và rolling deployments.

### 17.4. Tránh cache vô hạn ở ranh giới chặng

Một stage parse nhanh có thể tạo 1.000 messages/s trong khi stage HTTP chỉ hoàn tất 50 requests/s. Nếu message được buffer trong memory:

- Queue tăng tới capacity;
- Payload lớn làm heap/GC tăng;
- Shutdown để lại nhiều message chưa durable;
- Latency đầu cuối tăng dù step parse nhanh.

Cần bounded queues, durable state, throttle ingress hoặc phân luồng để backlog nằm ở hệ **có thể lưu bền vững, giám sát và replay**.

## 18. Concurrency ảnh hưởng transaction, ack, ordering và idempotency

### 18.1. Tăng threads làm cửa sổ lỗi phức tạp hơn

Với xử lý đồng bộ:

~~~text
poller -> handler -> DB commit -> ack source
~~~

Với `ExecutorChannel`:

~~~text
poller -> enqueue async task -> poller tiếp tục
                               worker -> DB commit -> ack?
~~~

Nếu poller coi việc gửi vào executor là hoàn tất nguồn, nhưng task chỉ nằm trong memory, pod crash có thể làm mất message. Phải xác định **ai ack nguồn và khi nào**; không giả định transaction từ poller tự bao worker khác thread.

### 18.2. At-least-once vẫn là nền tảng

Các sự cố như:

- Consumer commit DB rồi chết trước Kafka offset commit;
- JMS/AMQP handler commit DB rồi mất connection trước broker ack;
- SFTP file đã download nhưng business commit thất bại;
- HTTP POST thành công ở đối tác nhưng client mất response;

đều có thể dẫn tới retry/redelivery. Cần business idempotency key và phương án đối soát side effect, không tuyên bố exactly-once end-to-end chỉ vì thêm lock hoặc dùng một pool duy nhất.

### 18.3. Ordering khi song song

- Kafka có thứ tự trong partition; gửi nhiều record cùng key tới nhiều task async có thể hoàn thành khác thứ tự nếu không điều phối.
- JMS/AMQP có thể bị đảo thứ tự xử lý/hoàn tất khi nhiều consumers và redelivery.
- File/SFTP poller quét theo tên/ngày không mặc định bảo đảm business ordering.
- JDBC query không có `ORDER BY` không có thứ tự kết quả ổn định.
- Nếu workflow yêu cầu revision 1→2→3, cần partition by key, sequence checks hoặc per-key serialization.

### 18.4. Lock không bảo vệ mọi side effect

Distributed lock hoặc DB lease giúp giảm hai workers cùng claim một item, nhưng:

- Lease có thể hết hạn khi worker cũ vẫn gọi HTTP.
- Một worker khác claim lại, tạo **concurrent side effects**.
- Redis/DB lock có thể mất do network partition.
- Callback/retry từ client có thể vẫn thực hiện sau khi lock đã nhả.

Với thao tác rủi ro cao cần **fencing token/version check, idempotency key và kiểm chứng trạng thái đích**, không chỉ dựa vào mutex.

### 18.5. Checklist tính đúng đắn khi tăng concurrency

- [ ] Ranh giới source ack/commit và durable handoff rõ.
- [ ] Idempotency hoạt động khi hai workers cùng business key.
- [ ] Transaction scope không vượt thread boundary ngoài thiết kế.
- [ ] Có unique constraint hoặc state-machine kiểm soát side effect.
- [ ] Ordering theo key/tenant được giữ hoặc có cơ chế xử lý out-of-order.
- [ ] Retry/backoff không nhân số inflight vô hạn.
- [ ] Lease/claim có recovery sau crash và chống worker stale nếu cần.
- [ ] DLQ/replay không tạo duplicate sau khi hệ phục hồi.

## 19. Autoscaling, rolling deployment và vòng đời kết nối

### 19.1. Scale ngang phải tính cả tài nguyên downstream

Tăng pod có thể làm:

- Tăng số polling scans của File/SFTP/JDBC;
- Tăng số session/connection ở SFTP/DB/HTTP;
- Tăng consumer group members, rebalances và nguồn redelivery;
- Tăng số concurrent requests tới API đối tác;
- Tăng lượng retry khi dependency lỗi;
- Tăng tốc độ ghi/đọc disk hoặc message broker.

**HPA dựa trên CPU không đủ** để suy ra downstream capacity. Một service I/O-bound có thể CPU thấp nhưng DB/HTTP pool pending cao. Hệ cần scale metrics thích hợp như lag, backlog age, busy workers, queue depth, throughput và external capacity.

### 19.2. Rolling deployment có thể tạm tăng replicas

Một Deployment muốn 5 pods nhưng rolling update có thể tồn tại pod cũ + pod mới đồng thời theo maxSurge/maxUnavailable. Nếu mỗi pod có DB pool 12, số connection lý thuyết có thể vượt 60 trong giai đoạn chuyển. Hãy tính **peak concurrent replicas**, không chỉ desired replicas.

Checklist:

- [ ] Có bảng max replicas trong autoscaling và rolling deploy.
- [ ] Tổng maximum pool sizes không vượt DB/partner quota sau headroom.
- [ ] Pollers không cùng xử lý một file/row khi pod cũ chưa tắt.
- [ ] Kafka group rebalances được test khi scale in/out.
- [ ] JMS/AMQP consumers, prefetch và unacked messages được quan sát trong rollout.
- [ ] Dừng ingress/consumer đúng thứ tự, chờ inflight hoặc recovery theo contract.
- [ ] Secret/connection rotation không tạo reconnect storm.
- [ ] Có khả năng scale xuống mà không mất message đang chờ trong memory.

### 19.3. Graceful shutdown không phải phép màu

Một worker có thể đang:

- Giữ JDBC connection trong transaction;
- Tải file SFTP và ghi local temp file;
- Gọi HTTP đối tác đã commit;
- Chờ Kafka publisher callback;
- Giữ JMS/AMQP message chưa ack.

Khi container nhận SIGTERM, phải dừng nhận mới, cho một khoảng grace period và có recovery sau khi process kết thúc. Không nên cố cho mỗi operation chạy vô hạn để “không mất message”; cần bounded timeout, durable checkpoint và idempotency.

### 19.4. Kịch bản kill thật

1. Start load test có business IDs duy nhất.
2. Khi đang có khoảng 50 inflight messages, kill một replica.
3. Bảo đảm source có thể redeliver/reclaim phần chưa hoàn tất.
4. Worker khác không nhân đôi business side effects.
5. Đối soát DB, file, Kafka/JMS/AMQP và HTTP remote state.
6. Đo backlog drain, reconnect rate và số exception sau failover.
7. Kiểm tra threads/connections của instance còn sống không tăng vô hạn.

## 20. Observability: phát hiện saturation trước khi mất dữ liệu

### 20.1. Metrics quan trọng

| Tầng | Metric nên theo dõi | Dấu hiệu |
|---|---|---|
| Inbound File | Pending files, oldest age, scan duration, processing files | Scan chậm, file kẹt |
| SFTP | Active sessions, waiting/acquire time, transfer duration, remote failures | Session pool cạn |
| HTTP client | Leased/idle/pending connections, request latency, 429/503 | Pool starvation/quota |
| HTTP server | Active requests, request queue, reject/429/503, p95/p99 | Ingress quá tải |
| TaskExecutor | Active threads, pool size, queue depth, tasks rejected | Bounded queue đầy |
| TaskScheduler | Poll task duration, schedule delay, missed/overlap polls | Scheduler bị chiếm |
| QueueChannel | Depth, oldest age, enqueue/dequeue rate, send timeout | Backlog tăng |
| JMS | Consumers, ready/dispatched/unacked, redelivery, DLQ age | Prefetch/tải lệch |
| AMQP | Ready/unacked, consumers, prefetch, publish/ack rate, DLQ | Unacked cao |
| Kafka | Consumer lag per partition, rebalances, publish latency/errors | Hot partition, broker chậm |
| JDBC/Hikari | Active, idle, pending, acquisition wait, query/lock duration | Pool/DB saturation |
| End-to-end | Business completion rate, latency, duplicate no-op count | Thành công kỹ thuật khác nghiệp vụ |

Tên metric thực tế phụ thuộc stack, version và cấu hình Micrometer/Actuator/connector. Không giả định chỉ thêm dependency là số liệu đã được thu thập đầy đủ. Phải xác minh từng biểu đồ và alert hoạt động.

### 20.2. Những tỷ lệ giúp chẩn đoán

**Utilization** có thể hiểu đơn giản là active resources / configured capacity ở một thời điểm. Tuy nhiên:

- 100% CPU dùng cho batch CPU-bound có thể là bình thường nếu latency vẫn đạt.
- 100% DB pool active cùng pending tăng và request timeout là dấu hiệu xấu.
- Queue depth bằng 0 có thể là **không có dữ liệu đến** hoặc **consumer đang giữ nhiều unacked messages**; cần xem ingress, unacked và business completion.
- Số consumers tăng mà throughput không tăng cho thấy bottleneck khác hoặc consumer idle.
- Retries làm arrival rate **hiệu dụng** tới downstream tăng cao hơn số business messages mới.

### 20.3. Structured log và trace

| Trường | Mục đích |
|---|---|
| `correlationId`, `businessId` | Theo dõi một message giữa các adapter |
| `sourceEndpoint`, `targetEndpoint` | Khoanh vùng bottleneck |
| `flowStep`, `threadName`, `podId` | Phân biệt thread/pod |
| `poolName`, `acquisitionWaitMs` | Phân biệt chờ pool với slow remote response |
| `queueAgeMs`, `serviceTimeMs` | Phân biệt thời gian chờ và xử lý |
| `attempt`, `retryBackoffMs` | Tính tải retry |
| `sourceAckState`, `outcome` | Điều tra redelivery và partial failure |
| `messageSchemaVersion` | Phân tích sự cố hợp đồng |
| `concurrencyLimit`, `currentInflight` | Giải thích sự kiện bị reject/pause |

Không đưa businessId/userId vào metric tags với cardinality cao; dùng log/trace được bảo vệ. Không log credential, raw token hay PII không cần thiết.

### 20.4. Alert mẫu có runbook

- Pool acquisition p95 tăng cùng pending > 0 kéo dài.
- Active workers gần max và queue age tăng.
- SFTP oldest ready file vượt SLO.
- Kafka lag per partition tăng khi consumer count không thay.
- AMQP/JMS unacked tăng mà completion rate giảm.
- HTTP partner 429 tăng khi concurrency vượt quota.
- Database lock waits/deadlocks tăng sau khi mở rộng worker.
- Task rejection có nguy cơ mất message sau ack.
- Outbox/retry queue tăng bất thường hoặc event age vượt SLA.
- Graceful shutdown thường xuyên hết grace period khi inflight còn nhiều.

Mỗi alert có severity, owner, dashboard và hướng xử lý. Tránh alert chỉ nói “CPU > 80%” mà không liên hệ queue/latency/business throughput.

## 21. Ma trận load test và fault injection

Chỉ chạy một benchmark “100 messages thành công” không đủ. Kiểm thử phải kích hoạt **saturation, slow downstream, retry và crash** ở từng lớp.

### 21.1. Cách dựng bộ test

1. Tạo nguồn input có stable business ID và nhiều nhóm payload size.
2. Đo baseline với một instance, một consumer, concurrency thấp.
3. Tăng arrival rate từng mức, ghi throughput, queue wait, service time và utilization.
4. Làm chậm dependency HTTP/SFTP/DB/broker một cách có kiểm soát.
5. Tăng replicas và kiểm tra tổng quota, duplicate claim, ordering.
6. Thử saturation đến ngưỡng reject/backpressure, kiểm tra message durability.
7. Kill process ở những thời điểm commit/ack.
8. Đo thời gian backlog drain và số errors/unknown outcomes.
9. Đối soát business records thực tế, không chỉ số messages được nhận.
10. Lặp soak test đủ dài để quan sát connection/thread leak và GC/memory.

### 21.2. Bộ kiểm thử 60 ca

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| **T01** | DirectChannel handler chạy chậm | Upstream backpressure đúng, không mất message |
| **T02** | ExecutorChannel có hàng đợi bounded đầy | Rejection được xử lý, nguồn chưa ack sai |
| **T03** | QueueChannel in-memory rồi pod chết | Recovery contract rõ; không giả định durable |
| **T04** | Persistent MessageStore dùng đúng transaction | Message vẫn có thể recover theo hợp đồng |
| **T05** | CallerRunsPolicy khi executor đầy | Không phá SLA/thread/ack/transaction |
| **T06** | AbortPolicy khi executor đầy | Có error routing/retry, không silent drop |
| **T07** | Hai loại workload dùng chung executor | Critical workload không bị starvation ngoài policy |
| **T08** | TaskScheduler nhỏ, nhiều poller chậm | Schedule delay có metric, không mất nguồn |
| **T09** | Poller maxMessagesPerPoll tăng từ 5 tới 100 | Bounded downstream vẫn an toàn |
| **T10** | Poller bị pause 10 phút | Backlog bền vững và drain có kiểm soát |
| **T11** | Số replica tăng 1→5 | Tổng capacity/quota không vượt giới hạn |
| **T12** | Rolling deploy có pod cũ và mới | Tổng pool connections không vượt budget |
| **T13** | Autoscaler tăng pod khi downstream quá tải | Không gây overload/retry storm |
| **T14** | CPU-bound parse dùng I/O executor | Test phát hiện starvation và phân pool hợp lý |
| **T15** | HTTP client pool hết connection | Pool acquisition timeout, bulkhead và alert |
| **T16** | HTTP response chậm, connection bị giữ | Pending/latency tăng, không OOM |
| **T17** | HTTP/2 multiplexed connections | Sizing dựa trên streams/requests thực tế |
| **T18** | API quota 20 inflight, 100 calls/s | Cả concurrency/rate limit được thực thi |
| **T19** | API trả 429/503 kéo dài | Retry có jitter và circuit/limiter |
| **T20** | HTTP POST timeout sau remote commit | Idempotency/reconciliation ngăn duplicate |
| **T21** | HTTP inbound flood | Có giới hạn concurrent request và response phù hợp |
| **T22** | SFTP session cache cạn | Acquisition wait bounded, throughput/alert rõ |
| **T23** | SFTP server chỉ cho 8 transfers | Cluster không mở quá quota |
| **T24** | SFTP session chết vẫn trong cache | Invalid/reconnect đúng, không leak |
| **T25** | SFTP network stall trong download | Session/worker được phục hồi hoặc cách ly an toàn |
| **T26** | Nhiều pod quét cùng remote directory | Distributed claim + idempotency bảo vệ file |
| **T27** | File 1 GB được lấy bởi 10 workers | RAM/disk/FD có giới hạn |
| **T28** | File đang upload dở | Chỉ xử lý sau ready protocol |
| **T29** | File business commit xong nhưng archive lỗi | Không tạo business record thứ hai |
| **T30** | NFS shared volume disconnect | Không silent drop, có recovery/runbook |
| **T31** | JMS consumer concurrency tăng | Throughput/ordering theo contract, không leak session |
| **T32** | JMS prefetch quá lớn | Dispatched/unacked được đo, chỉnh fairness |
| **T33** | JMS broker redelivery sau crash | Idempotent consumer giữ business correctness |
| **T34** | JMS handler retry và broker retry chồng nhau | Attempts bounded, không storm |
| **T35** | JMS queue có poison record | DLQ/recovery, không chặn vĩnh viễn |
| **T36** | AMQP consumers × prefetch tăng mạnh | Unacked/memory có giới hạn |
| **T37** | AMQP ack chưa gửi khi process chết | Redelivery không nhân đôi side effect |
| **T38** | AMQP publish confirm mất | Retry idempotent, consumer dedupe |
| **T39** | AMQP queue ready thấp nhưng unacked rất cao | Dashboard không kết luận nhầm queue rỗng |
| **T40** | AMQP delayed retry làm backlog tăng | Có DLQ/age alert và quota |
| **T41** | Kafka 6 partitions, 12 consumer threads | Idle consumers được phát hiện, không hứa throughput tăng |
| **T42** | Kafka hot partition | Phân tích key skew và business ordering |
| **T43** | Kafka consumer xử lý quá lâu giữa poll | Rebalance/max.poll.interval được xử lý |
| **T44** | Kafka async handler hoàn tất sai thứ tự | Offset/ack chỉ tiến theo policy an toàn |
| **T45** | Kafka poison record sang DLT | Ordering/version gating theo business |
| **T46** | Kafka producer buffer cạn | Backpressure/max.block/delivery failures có kiểm soát |
| **T47** | JDBC tổng maximum pool size vượt quota DB | Test phát hiện và giảm pool/replicas |
| **T48** | JDBC 100 workers tranh 10 connections | Pending/acquisition wait có alert, không treo |
| **T49** | JDBC transaction giữ lock khi gọi HTTP | Load test phát hiện pool/lock starvation |
| **T50** | JDBC hai pollers claim cùng row | Chỉ một claim hợp lệ theo thiết kế |
| **T51** | JDBC lease hết hạn khi worker cũ còn chạy | Fencing/idempotency ngăn double effect |
| **T52** | JDBC deadlock khi concurrency tăng | Retry transaction giới hạn, không tạo duplicate |
| **T53** | DB failover khi pool đang active | Connection recovery và error routing đúng |
| **T54** | Outbox worker tăng concurrency | Một event có thể retry nhưng side effect downstream an toàn |
| **T55** | Quota per tenant, một tenant flood | Tenant khác vẫn có mức phục vụ đã duyệt |
| **T56** | Circuit breaker mở, nguồn vẫn gửi | Ingress throttle/durable buffer, không mất message |
| **T57** | Retry storm khi dependency phục hồi | Jitter/limiter bảo vệ downstream |
| **T58** | SIGTERM giữa transfer/DB commit/ack | Graceful shutdown hoặc replay an toàn |
| **T59** | Soak test kéo dài với failures ngắt quãng | Không leak thread/session/connection |
| **T60** | Rollback sau khi đã xử lý một phần backlog | Reconciliation không làm trùng hoặc mất side effects |

Mỗi case phải có **môi trường/version, payload và business key thử nghiệm, cấu hình concurrency/pool/replicas, expected/actual result, metrics/log/correlation, actual business state, người kiểm tra và kết luận PASS/FAIL**. Một thông báo “đã gửi message thành công” không đủ để xác nhận dữ liệu không trùng hoặc không mất.

### 21.3. Định nghĩa điểm saturation

Một điểm saturation có thể được xem là khi tăng tải đầu vào không làm tăng throughput bền vững, trong khi latency, queue depth, pending acquisition hoặc error rate tiếp tục tăng. Hãy xác định **knee point** từ biểu đồ throughput–latency và vận hành với headroom, thay vì đẩy đến ngưỡng saturation trong điều kiện ổn định.

## 22. Runbook khi thấy connection pool hoặc workers bị cạn

### 22.1. Quy trình 10 bước

1. **Xác định bottleneck:** HTTP pool, HikariCP, SFTP sessions, JMS consumers, Kafka partitions hay executor?
2. **Xem ingress rate:** Lưu lượng mới, spike, batch replay hoặc retry storm?
3. **Xem pending:** Queue depth/age, pool acquisition wait và active tasks đang ở mức nào?
4. **Xem latency downstream:** Query/lock, HTTP p95/p99, remote transfer, broker ack?
5. **Kiểm tra hot keys/tenant:** Một tenant/partition/file lớn có giữ worker bất thường?
6. **Xem retry và lỗi:** 429/503, timeouts, deadlock, broker redelivery, poison messages?
7. **Kiểm tra quota:** Tổng max connections toàn cluster có vượt DB/partner capacity?
8. **Giảm tải có kiểm soát:** Pause poller, rate limit, bulkhead, giảm concurrency hoặc circuit breaker.
9. **Đối soát side effects:** Message đã ack/commit chưa, retry có thể lặp nghiệp vụ không?
10. **Phục hồi và hậu kiểm:** Drain backlog, sửa sizing/code, lưu evidence và cập nhật runbook.

### 22.2. Bảng phản ứng theo dấu hiệu

| Dấu hiệu | Không nên làm | Hướng xử lý |
|---|---|---|
| Hikari pending cao | Tăng pool cho mọi pod không xem quota DB | Tìm slow SQL/lock, giảm inflight, phân bổ quota |
| HTTP pool pending cao | Chỉ tăng connect timeout | Đo partner latency/rate limit, bulkhead và queue |
| SFTP session lỗi hàng loạt | Tắt host-key verification hoặc reconnect dồn | Xác minh server/cert/quota, bounded retry với jitter |
| Executor queue dài | Đặt queue vô hạn | Throttle nguồn, durable buffering và sizing |
| Kafka lag cao | Tăng consumers vượt partitions | Phân tích hot partition và DB/HTTP bottleneck |
| AMQP unacked cao | Ack sớm cho nhanh | Giảm prefetch/concurrency, sửa handler/latency |
| JMS consumer xử lý chậm | Bỏ idempotency để tăng tốc | Tối ưu downstream, cân nhắc prefetch/consumers |
| File được quét lại liên tục | Xóa file/metadata tùy tiện | Kiểm tra claim/filter và business state |
| Retry làm tải tăng | Tăng attempts không giới hạn | Jitter, circuit breaker, deferred retry |
| DB transaction quá dài | Tăng timeout vô hạn | Rút ngắn transaction, tách external I/O có kiểm soát |

### 22.3. Khi cần pause và resume

- Xác định endpoint ID và owner của poller/listener.
- Dừng nhận mới hoặc giảm tốc mà không làm sai broker ack.
- Giữ durable backlog, tránh xóa pending items.
- Đợi inflight trong thời gian bounded hoặc để recovery xử lý sau crash.
- Xác minh side effect trước khi replay.
- Khi dependency phục hồi, mở lại **từng bước**, theo dõi pending wait và error rate.
- Điều chỉnh hạn mức tạm thời có expiry và audit.
- Chỉ đóng incident khi business completion và backlog age trở lại ngưỡng được phê duyệt.

## 23. Case study: SFTP → JDBC/outbox → Kafka và HTTP logistics

Một hệ giả định nhận đơn hàng từ đối tác SFTP theo file CSV; xử lý và ghi DB; outbox phát Kafka event; worker khác gọi HTTP logistics. Dự kiến đạt 100 orders/s trong peak, có tối đa 4 replicas và muốn mở rộng lên 8.

### 23.1. Cấu hình ban đầu gây sự cố

- Mỗi pod có executor 64 threads và queue không giới hạn.
- SFTP poller 1 giây/lần, không có distributed claim.
- Mỗi pod mở tối đa 20 SFTP transfers; remote server chỉ cho 30 transfers toàn tenant.
- Hikari maximumPoolSize=30 mỗi pod, database dành khoảng 80 connections cho ứng dụng.
- HTTP partner chỉ chấp nhận tối đa 25 concurrent requests, không có rate limiter.
- Một số JDBC transaction giữ connection trong khi gọi HTTP.
- Kafka topic có 6 partitions nhưng 8 replicas × 4 consumer threads.
- Retry ở client, advice và broker đều được bật với số lần lớn.

Khi 4 pods đang chạy, pool JDBC có khả năng yêu cầu **120 connections**, SFTP có thể yêu cầu **80 transfers**, và HTTP có thể đẩy lượng lớn concurrent requests vào quota 25. Tăng replicas lên 8 làm giới hạn lý thuyết còn tệ hơn.

### 23.2. Kế hoạch thiết kế lại

1. **Chốt quota thực:** Xác nhận cùng owner của DB, SFTP server, HTTP partner và Kafka broker.
2. **Lấy baseline:** Đo arrival rate, p95 processing time, Hikari active/pending, HTTP 429/503, SFTP transfer duration, Kafka lag.
3. **Tách transaction:** DB transaction ngắn để ghi order và outbox; HTTP logistics xử lý ở worker riêng với idempotency.
4. **Đặt bounded executor:** Ví dụ 8 core, 12 max, queue 32 cho partner I/O và xử lý rejection có durable recovery.
5. **Giới hạn DB:** Phân bổ tổng pool qua peak replicas, để headroom cho migration/ops và hệ khác.
6. **Giới hạn SFTP:** Tổng transfer across replicas dưới quota và có distributed claim.
7. **Giới hạn HTTP:** Per-partner max inflight 25 trên toàn cluster và quota calls/s theo hợp đồng.
8. **Kafka consumer:** Sizing theo partitions, key skew và downstream DB capacity; không scale consumer threads vô ích.
9. **Tách retry owner:** Backoff/jitter khi SFTP/HTTP lỗi; DB deadlock retry ngắn; Kafka outbox có ledger/idempotent consumer.
10. **Bảo vệ business:** Business IDs/unique constraint, side-effect reconciliation, error flow/quarantine.

### 23.3. Bảng ngân sách minh họa sau cải thiện

| Tài nguyên | Quota giả định toàn cụm | Lựa chọn cần thử |
|---|---:|---|
| SFTP transfers | 30 | Giới hạn thấp hơn quota, tính cả rolling pods |
| JDBC connections cho app | 80 | Tổng max pool khi scale tới 8 pods + headroom không vượt 80 |
| HTTP concurrent logistics | 25 | Distributed limiter hoặc phân quota per pod với giới hạn HPA |
| Kafka partitions | 6 | Tổng consumers active hữu ích theo partitions/bottleneck |
| File parse | Theo CPU/memory | Bounded worker queue, file size limits |
| Outbox queue | Theo DB/storage/retention | Durable pending, age alert và retry capacity |

Không có một “cấu hình vàng” như 8 threads hoặc 12 connections áp dụng mọi trường hợp. Kết quả cuối dựa trên test tải của luồng thực tế.

### 23.4. Failure drills

**Drill A — HTTP logistics chậm gấp 5 lần:** Bulkhead giới hạn 25 inflight, backlog ở durable queue, DB transaction không bị giữ và không OOM.

**Drill B — SFTP server từ chối session vượt quota:** Poller giảm concurrent transfers và backoff; không tạo reconnect storm; file pending còn nguyên.

**Drill C — Kill một pod giữa DB commit và Kafka publish:** Outbox replay an toàn, không sinh order trùng.

**Drill D — Autoscale lên 8 pods:** Tổng DB/SFTP/HTTP quota không bị vượt; rolling deploy + surge cũng được tính.

**Drill E — Kafka consumer rebalance:** Ordering theo key được quản lý, offsets không commit trước durable business success.

### 23.5. Điều kiện chấp nhận

- Đạt business throughput/SLO với headroom đã được duyệt.
- Không mất message hoặc duplicate side effect ở failure drills.
- Không vượt downstream connection/concurrency quotas.
- Queue/backlog age được đo và có thể drain.
- Hàng đợi, worker và session pool đều có giới hạn.
- Restart/rolling deployment/scale-out không làm mất hoặc xử lý trùng file/record.
- Retry không gây bão khi dependency khôi phục.
- Có owner/on-call, runbook, dashboard và phê duyệt go-live.

## 24. Mẫu phiếu review capacity trước go-live

Đây là một **tệp YAML minh họa để review**, không phải định dạng cấu hình mà Spring Integration/Spring Boot tự nhận. Phải bind/implement, đo và điền bằng chứng thực.

~~~yaml
flow: supplier-orders
owners:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations

topology:
  minReplicas: 2
  desiredReplicas: 4
  maxReplicasIncludingRollingSurge: 8

ingress:
  adapter: sftp-inbound
  pollInterval: 5s
  maxMessagesPerPoll: 10
  distributedClaim: required
  sourceDurableBeforeAck: true

executors:
  partnerHttpIo:
    corePoolSize: 8
    maxPoolSize: 12
    queueCapacity: 32
    rejectionPolicy: fail-to-durable-retry
    shutdownGrace: 30s

connectionBudgets:
  sftp:
    maxClusterTransfers: REVIEW_WITH_PARTNER
    maxPerReplica: REVIEW_REQUIRED
    acquisitionTimeout: REVIEW_REQUIRED
  jdbc:
    maxClusterConnectionsForApp: REVIEW_WITH_DBA
    maxPerReplica: REVIEW_REQUIRED
    acquisitionTimeout: 2s
  httpPartner:
    maxClusterInflight: 25
    maxRequestsPerSecond: REVIEW_WITH_PARTNER
    limiterScope: cluster

kafka:
  partitions: 6
  consumerGroup: supplier-orders-v1
  listenerConcurrencyPerReplica: REVIEW_REQUIRED
  orderingKey: orderId

reliability:
  stableBusinessId: source-orderId-revision
  businessIdempotency: unique-constraint
  outbox: required
  durableBackpressure: required
  errorRecovery: DLQ-and-replay

observability:
  poolActiveIdlePending: required
  executorQueueAndRejection: required
  backlogAgeAndLag: required
  businessCompletionLatency: required

testing:
  saturationTestsPassed: PENDING
  failureDrillsPassed: PENDING
  rollingScaleTestPassed: PENDING

approval:
  businessOwner: PENDING
  databaseOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

### 24.1. Quy tắc review

- Một giá trị cấu hình per-pod phải được quy đổi sang **tổng theo max replicas + surge**, và ghi nhận quota đối tác.
- Chỉ đặt limits sau khi biết tải thực tế và dependency capacity.
- Mọi `REVIEW_REQUIRED`, `REVIEW_WITH_...` và `PENDING` phải được giải quyết trước khi chấp thuận triển khai.
- Một cơ chế `rejectionPolicy` trong phiếu chỉ là yêu cầu logic; phải có đường xử lý trong code để không làm mất message.
- Không cho phép “GO” chỉ vì `maximumPoolSize` hoặc `maxThreads` đã được đặt thành số dương.

## 25. Checklist go/no-go

### Trước production

- [ ] Có sơ đồ flow, MessageChannel, poller, listener và outbound adapters.
- [ ] Có số liệu peak arrival rate, service time p50/p95/p99 và bottleneck.
- [ ] Có bảng ngân sách thread/queue/connection/broker consumer theo từng dependency.
- [ ] Tổng ngân sách đã tính max replicas và rolling surge.
- [ ] Executor queue bounded, rejection có đường recovery.
- [ ] Pool acquisition timeout, max size và lifecycle được review.
- [ ] Có backpressure/limiter/bulkhead cho downstream chậm và per-tenant quota nếu cần.
- [ ] Poller có batch limit và multi-replica claim khi dùng file/SFTP/JDBC.
- [ ] JMS/AMQP consumer concurrency, prefetch/ack và Kafka partitions/offset được kiểm thử.
- [ ] Có idempotency, transaction boundary, DLQ và replay khi redelivery/retry.
- [ ] Có metric active/idle/pending, queue depth/age, retries và business completion.
- [ ] Load, soak, outage, scale-out, crash và rollback drills đã pass.
- [ ] Owner, alert, runbook và on-call nhận bàn giao.

### Trong rolling rollout

- [ ] Deploy canary/giảm inflight ban đầu, xác minh metrics hoạt động.
- [ ] Tăng traffic/batch/concurrency từng bước, quan sát latency và saturation.
- [ ] Không mở pool vượt quota khi pod cũ và mới cùng tồn tại.
- [ ] Theo dõi queue age, redelivery/duplicate rate, DB locks và HTTP 429/503.
- [ ] Có thể pause intake an toàn khi nguồn dữ liệu được giữ bền vững.
- [ ] Các ngoại lệ có owner, expiry và biện pháp giảm rủi ro.
- [ ] Chỉ mở rộng sau khi business correctness và throughput đạt mục tiêu.

### Quyết định

| Trạng thái | Điều kiện |
|---|---|
| **GO** | Kiểm thử chứng minh an toàn, throughput/SLO đạt, quotas đúng, recovery có bằng chứng |
| **GO WITH EXCEPTION** | Ngoại lệ nhỏ có owner, expiry, mitigation và phê duyệt |
| **HOLD / RETEST** | Chưa đo đủ tải, chưa test multi-replica/connection leak hoặc chưa rõ source ack |
| **NO-GO** | Silent drop sau ack, pool vượt quota, duplicate side effect, không có backpressure/recovery hoặc rủi ro bảo mật |

## 26. Những anti-pattern thường gặp

**“Càng nhiều threads càng nhanh.”** Khi downstream là bottleneck, tăng threads làm tăng pool waits, memory, retry và latency. Sizing theo service time và capacity thực.

**“Queue vô hạn giúp không mất message.”** Queue in-memory vô hạn có thể gây OOM và mất task khi process chết. Cần bounded queue và durable boundary.

**“Một pod dùng pool 20 thì 10 pods cũng được.”** Tổng max connections thành 200, có thể vượt DB quota. Tính theo max replicas và rolling surge.

**“DirectChannel kém hơn ExecutorChannel.”** DirectChannel đồng bộ có transaction/error propagation dễ hiểu và backpressure tự nhiên; ExecutorChannel cần quản lý async, queue và ack. Chọn theo hợp đồng.

**“ExecutorChannel giúp transaction chạy song song mà không thay semantics.”** Thread boundary có thể làm transaction upstream không lan sang handler. Phải kiểm tra transaction/ack sau thay đổi.

**“CallerRunsPolicy luôn là backpressure tốt.”** Có thể khiến HTTP listener/poller thread thực thi handler dài, vượt SLA hoặc đổi transaction boundary. Test có chủ đích.

**“Kafka tăng consumer threads vượt partitions sẽ tăng throughput.”** Có thể làm nhiều consumers idle; bottleneck vẫn nằm ở partition hoặc downstream.

**“RabbitMQ prefetch lớn luôn tốt.”** Làm tăng unacked, memory và giảm fairness. Test mức phù hợp.

**“JMS consumer = một kết nối TCP.”** Provider có thể quản lý session/connection khác nhau. Đọc tài liệu implementation.

**“SFTP session cache lớn giúp tải file nhanh hơn.”** Remote quota và bandwidth có thể hạn chế; cache lớn gây connection storm.

**“Hikari maxLifetime là query timeout.”** Nó quản lý vòng đời connection trong pool, không cắt query chạy chậm.

**“Chỉ đặt rate limit là đủ.”** Rate limit không kiểm soát số requests cùng chờ khi remote latency tăng; còn cần concurrency/bulkhead limit.

**“Giữ DB transaction khi gọi HTTP để mọi bước nhất quán.”** Không tạo transaction ACID xuyên hệ và dễ giữ connection/lock quá lâu. Xem xét outbox và orchestration.

**“Chỉ lock file/row là exactly-once.”** Lease có thể hết hạn, duplicate side effect vẫn có thể xảy ra sau retry. Cần business idempotency và đối soát.

**“Canary là một pod nên không thể vượt quota.”** Consumer group, poller và broker topology có thể không phân traffic theo ý muốn; rolling surge làm tổng connection tăng.

**“Pool active thấp nghĩa không có bottleneck.”** Có thể worker đang chờ ở tầng khác hoặc message chưa vào pipeline; đọc ingress, queue depth, lag và business completion cùng lúc.

## 27. Câu hỏi tự kiểm tra và tài liệu tham khảo

### 27.1. Câu hỏi

1. Concurrency khác parallelism và throughput như thế nào?
2. Nếu arrival rate là 80 requests/s và response time trung bình 0,2 s, Little’s Law gợi ý bao nhiêu requests inflight trung bình?
3. Vì sao kết quả trung bình của Little’s Law chưa đủ để chọn max pool size?
4. Nếu HTTP latency tăng 5 lần nhưng arrival rate giữ nguyên, điều gì xảy ra với nhu cầu inflight?
5. DirectChannel và ExecutorChannel khác nhau thế nào về thread và transaction?
6. QueueChannel in-memory có sống sót qua process restart không?
7. Vì sao `maxMessagesPerPoll` không bảo đảm downstream chỉ xử lý từng ấy message đồng thời?
8. `corePoolSize=8, maxPoolSize=16, queueCapacity=64` có luôn tạo 16 threads khi có 16 tasks không?
9. Khi executor reject task, điều kiện nào giúp không mất message?
10. Rate limiting và concurrency limiting khác nhau ra sao?
11. Tại sao HTTP/2 có thể khiến số connections và số requests inflight khác nhau?
12. Vì sao SFTP session pool phải xem quota server và số replicas?
13. Điều gì xảy ra khi hai File pollers cùng đọc một shared directory?
14. JMS prefetch có thể ảnh hưởng fairness và memory thế nào?
15. Với AMQP, vì sao queue ready=0 chưa đủ nói hệ không có backlog?
16. Kafka topic 6 partitions có được tăng throughput bằng 12 consumers trong cùng group không?
17. Vì sao Kafka hot partition vẫn là bottleneck dù tổng partition count lớn?
18. Hikari `connectionTimeout` khác `maximumPoolSize` và query timeout thế nào?
19. Tại sao cần tính số connection trong rolling deployment, không chỉ desired replicas?
20. Nếu một worker hết DB lease nhưng HTTP side effect vẫn đang chạy, cần bảo vệ bằng gì?
21. Khi DB transaction giữ connection trong suốt HTTP call, pool saturation có thể lan truyền ra sao?
22. Những metric nào giúp biết queue đang tăng vì source burst hay downstream chậm?
23. Một loạt retry có thể khiến throughput mới thấp nhưng số requests thực tế vào downstream vẫn tăng như thế nào?
24. Khi nào nên pause poller thay vì tăng executor queue size?
25. Test nào chứng minh tăng 1 lên 5 pods không gây duplicate file, row hoặc broker record?

**Gợi ý:** Với mỗi câu hỏi, tách ba phạm vi **per-task → per-instance → toàn cụm** và kiểm tra **thread/queue/connection → business side effect → source ack/commit**.

### 27.2. Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Concurrency** | Số thao tác đang diễn ra đồng thời |
| **Throughput** | Số tác vụ hoàn tất trong đơn vị thời gian |
| **Inflight** | Message/request chưa hoàn thành theo hợp đồng |
| **TaskExecutor / TaskScheduler** | Executor cho tác vụ / scheduler kích hoạt định kỳ |
| **MessageChannel** | Kênh giao message trong Spring Integration |
| **Bounded queue** | Hàng đợi có sức chứa hữu hạn |
| **Rejection policy** | Hành vi khi executor không nhận task |
| **Backpressure / bulkhead** | Giảm tải đầu vào / cô lập tài nguyên theo dependency |
| **Rate limiter** | Giới hạn yêu cầu trong một cửa sổ thời gian |
| **Pool acquisition** | Chờ lấy connection/session từ pool |
| **Prefetch** | Message được chuyển sớm cho consumer trước khi ack |
| **Consumer group / partition** | Cơ chế phân chia Kafka record cho consumers |
| **Idempotency** | Xử lý lặp mà không tạo tác động nghiệp vụ lặp |
| **Outbox** | Ghi nghĩa vụ publish trong DB transaction |
| **Lease / fencing token** | Quyền claim có hạn / cơ chế ngăn worker cũ ghi sai |
| **Little’s Law** | Quan hệ số item trong hệ = throughput × thời gian lưu lại |
| **Graceful shutdown** | Dừng intake và kết thúc/khôi phục inflight có kiểm soát |
| **Saturation** | Điểm tăng tải làm latency/backlog tăng mà throughput không tăng đáng kể |

### 27.3. Tài liệu nền tảng

Khi triển khai thực tế, đối chiếu **đúng phiên bản**:

- **Spring Integration Reference Guide:** Message Channels, Polling Consumer, Endpoint Lifecycle, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC adapters, Message Store và Error Handling.
- **Spring Framework Reference:** TaskExecutor, TaskScheduler, ThreadPoolTaskExecutor, transaction management, messaging gateway.
- **Spring Boot Reference:** Configuration properties, Actuator, Micrometer, graceful shutdown và DataSource pool settings.
- **Spring AMQP Reference / RabbitMQ Documentation:** Listener containers, concurrent consumers, prefetch, ack/requeue, publisher confirms và broker quotas.
- **Spring for Apache Kafka Reference / Apache Kafka Documentation:** Consumer concurrency, partitions, offsets, producer settings, retries và group rebalances.
- **JMS/Jakarta Messaging specification và provider documentation:** Session/connection pooling, acknowledgement, prefetch, transactions, redelivery.
- **HikariCP Configuration Guide và database vendor documentation:** Pool sizing, acquisition wait, connection lifecycle, SQL locks và deadlocks.
- **Spring Integration SFTP / underlying SSH client documentation:** Cached sessions, connection/channel limits, host-key verification và reconnect.
- **HTTP client documentation (Apache HttpClient/Reactor Netty/đối tác):** Max connections/streams, per-route pooling, timeouts, quota và HTTP/2 multiplexing.

**Kết luận:** Cấu hình concurrency và connection pool chỉ an toàn khi **năng lực của từng chặng phù hợp với toàn bộ luồng**, tài nguyên được giới hạn theo cả per-instance lẫn cluster, message đã nhận có đường phục hồi khi quá tải, và việc tăng song song không phá transaction, ordering hay idempotency. Hãy dùng số liệu đo tải, giới hạn downstream, backpressure, failure testing và bằng chứng vận hành để quyết định, thay vì tăng threads/connections theo cảm tính.



