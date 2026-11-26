# Điều chỉnh queue capacity khi mở rộng Spring Batch

## 1. Queue capacity ảnh hưởng đến batch job như thế nào?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, chúng ta mở rộng Spring Batch cho workload lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán. Khi tăng số tác vụ xử lý đồng thời, một quyết định quan trọng là **bao nhiêu công việc được phép chờ trong hàng đợi** trước khi hệ thống phải giảm tốc độ nhận việc hoặc từ chối tác vụ.

**Queue capacity** là giới hạn số **task đang chờ** bên trong một executor có hàng đợi. Nó khác với số thread đang thực thi, số partition được tạo, số item trong chunk và số message tồn đọng ở broker. Nếu queue quá lớn, hệ thống có thể nhận nhiều việc hơn khả năng hoàn thành, làm thời gian chờ và bộ nhớ tăng. Nếu queue quá nhỏ, những đợt tải đột biến có thể tạo ra nhiều lần từ chối task, dù chỉ cần thêm một lượng đệm hợp lý.

Mục tiêu của bài học:

- Hiểu mối quan hệ giữa **core pool size**, **max pool size**, **queue capacity** và chính sách khi executor đầy.
- Chọn queue capacity phù hợp với mức đồng thời thực tế, RAM, JDBC connection pool và hệ thống phía sau.
- Phân biệt queue của executor với queue của message broker hoặc số partition trong Spring Batch.
- Quan sát độ sâu hàng đợi, thời gian chờ, throughput và tín hiệu bão hòa để điều chỉnh có cơ sở.
- Kiểm thử backpressure, lỗi quá tải và restart mà vẫn bảo đảm tính đúng đắn của dữ liệu.

## 2. Cơ chế queue trong ThreadPoolTaskExecutor

Một lựa chọn phổ biến cho Spring Batch là **ThreadPoolTaskExecutor** của Spring Framework. Executor này sử dụng cơ chế quản lý thread của Java. Khi có task mới được gửi đến, cách xử lý cơ bản của thread pool là:

1. Nếu số worker hiện có ít hơn **corePoolSize**, tạo worker mới để chạy task.
2. Khi đã đủ core worker, thử đưa task vào queue.
3. Nếu queue đầy, thử tạo worker bổ sung cho đến **maxPoolSize**.
4. Nếu không còn khả năng tạo worker và queue cũng đầy, áp dụng **RejectedExecutionHandler**.

Đây là thứ tự quan trọng: **queue còn chỗ thường được ưu tiên trước khi executor tăng từ corePoolSize lên maxPoolSize**. Vì vậy cấu hình maxPoolSize lớn không bảo đảm executor sẽ chủ động dùng nhiều thread. Queue càng lớn, việc tăng thread vượt mức core càng có thể xảy ra muộn.

~~~mermaid
flowchart TD
    A[Task mới] --> B{Worker ít hơn core?}
    B -->|Có| C[Tạo worker, chạy task]
    B -->|Không| D{Queue còn chỗ?}
    D -->|Có| E[Đưa task vào queue]
    D -->|Không| F{Worker ít hơn max?}
    F -->|Có| G[Tạo worker bổ sung]
    F -->|Không| H[Áp dụng rejection policy]
~~~

### 2.1. Ví dụ thứ tự sử dụng tài nguyên

Giả sử executor có **corePoolSize = 4**, **maxPoolSize = 8** và **queueCapacity = 16**. Nếu 25 task được gửi gần như cùng lúc và chưa có task nào hoàn thành:

| Nhóm task | Executor xử lý ra sao? |
|---|---|
| 1–4 | Tạo bốn core worker để chạy |
| 5–20 | Đưa 16 task vào hàng đợi |
| 21–24 | Tạo thêm bốn worker vì queue đã đầy |
| 25 | Áp dụng chính sách rejection vì cả pool và queue đã chạm giới hạn |

Đây là ví dụ lý tưởng hóa để hiểu quy tắc; trong thực tế task có thể hoàn thành ngay trong lúc các task khác được gửi vào, nên các con số quan sát tại một thời điểm có thể khác.

### 2.2. Queue capacity bằng 0, dương hoặc rất lớn

Với ThreadPoolTaskExecutor, queueCapacity dương tạo hàng đợi **LinkedBlockingQueue** có sức chứa hữu hạn. Giá trị **0** tạo cơ chế **SynchronousQueue**, nghĩa là không giữ task chờ trong queue; task phải được bàn giao trực tiếp cho worker hoặc executor tạo worker mới nếu còn khả năng. Nên dùng giá trị 0 một cách có chủ đích, không coi đó là cách tăng throughput mặc định.

| Cấu hình | Hành vi chủ yếu | Đánh đổi |
|---|---|---|
| queueCapacity = 0 | Không đệm task trong queue; có thể tăng worker từ core lên max sớm hơn | Dễ chạm max và rejection khi task đến theo đợt |
| Queue nhỏ, có giới hạn | Hấp thụ một phần burst; mở thêm worker khi queue đầy | Cần điều chỉnh theo tốc độ xử lý và tài nguyên phía sau |
| Queue lớn | Nhận nhiều task chờ, giảm rejection trong ngắn hạn | Tăng thời gian chờ, bộ nhớ và nguy cơ che giấu quá tải |
| Queue không giới hạn hoặc quá lớn so với tải | Task có thể tích lũy kéo dài | maxPoolSize gần như không phát huy tác dụng trước khi backlog rất lớn |

**Không nhầm capacity với lượng dữ liệu.** Queue capacity = 16 nghĩa là giữ tối đa 16 **Runnable/task** chờ trong executor đó. Một task có thể tham chiếu nhiều object, dữ liệu đệm hoặc trạng thái xử lý. Số item thực tế nằm trong bộ nhớ phụ thuộc cách reader, processor, writer và cơ chế lên lịch task hoạt động.

## 3. Queue trong từng kiến trúc Spring Batch

Tùy kiểu scaling, queue có thể nằm ở nhiều vị trí và mỗi vị trí có giới hạn riêng:

| Kiến trúc | Queue cần quan sát | Điều cần phân biệt |
|---|---|---|
| **Multi-threaded step** | Queue của TaskExecutor nhận các tác vụ xử lý chunk/repeat | Số thread đang xử lý thực tế có thể còn bị giới hạn bởi cấu hình Step, version Spring Batch và khả năng reader/writer |
| **Parallel steps** | Queue của executor dùng để chạy các flow/step đồng thời | Mỗi step có thể lại sở hữu pool riêng; phải tính tổng số task và connection |
| **Local partitioning** | Queue của executor dùng cho worker StepExecution | gridSize là số partition được chia, không đồng nghĩa bằng số partition đang chạy |
| **Remote partitioning** | Queue hoặc broker giữa manager và worker, cùng executor ở mỗi worker | Cần theo dõi consumer concurrency, prefetch, in-flight và tổng connection trên nhiều JVM |
| **Remote chunking** | Broker backlog, số message đang xử lý, worker concurrency | Queue capacity của executor cục bộ không trực tiếp giới hạn lượng message broker có thể tích lũy |

Ví dụ, manager tạo 100 partition và một executor có 8 worker, queue capacity 16. Điều này không có nghĩa tất cả 100 partition chạy đồng thời. Khả năng nộp task, việc xếp hàng và chính sách từ chối có thể phụ thuộc vào cách manager triển khai partition handler. Hãy đo **active worker**, **số task queued** và **trạng thái StepExecution**, không chỉ đếm partition.

Một số phiên bản Spring Batch có cơ chế giới hạn concurrency ở tầng Step, bên cạnh giới hạn của TaskExecutor; API điều tiết này cũng thay đổi giữa các phiên bản. Trước khi giải thích vì sao 8 thread được cấu hình mà chỉ 4 thread hoạt động, cần kiểm tra chính xác **phiên bản Spring Batch đang chạy** và cơ chế nộp công việc của Step.

## 4. Queue không tạo thêm năng lực xử lý

Queue chỉ **dịch chuyển công việc sang thời gian chờ**. Khi tốc độ task đến cao hơn tốc độ xử lý duy trì được, backlog sẽ tăng cho đến khi công việc giảm, worker mạnh hơn hoặc cơ chế giới hạn đầu vào tác động.

Gọi:

- **λ (lambda):** số task được gửi đến mỗi giây.
- **μ (mu):** số task có thể được xử lý xong mỗi giây trong điều kiện hệ thống hiện tại.
- **Q:** giới hạn số task chờ trong queue.
- **Wq:** thời gian task phải đợi trong queue.

Khi tải tạm thời giữ ở mức λ lớn hơn μ, backlog có thể tăng gần đúng:

~~~text
Backlog tăng thêm ≈ (λ - μ) × thời gian burst

Queue capacity cần cho burst
    ≈ max(0, (λ - μ) × thời gian burst)
       + biên dự phòng hợp lý
~~~

Chẳng hạn hệ thống xử lý bền vững 20 task/giây nhưng trong 2 giây có 35 task/giây gửi đến. Nếu không thay đổi năng lực worker, lượng việc phát sinh thêm là khoảng **30 task**. Queue capacity 32 có thể đệm được phần lớn burst đó trong mô hình đơn giản. Tuy nhiên, executor có thể mở thêm worker sau khi queue đầy và một số task có độ dài khác nhau; vì vậy phép tính chỉ dùng để chọn các giá trị cần benchmark.

Trong trạng thái ổn định, định luật Little biểu diễn quan hệ trung bình giữa số task chờ và thời gian chờ:

~~~text
Lq = λ hiệu dụng × Wq

Lq: số task chờ trung bình
λ hiệu dụng: throughput task rời hàng đợi trong hệ ổn định
Wq: thời gian chờ trung bình của task
~~~

Nếu backlog trung bình 40 task và throughput thực tế 20 task/giây, thời gian chờ trung bình có thể xấp xỉ 2 giây khi các giả định ổn định phù hợp. Queue capacity lớn hơn không làm 2 giây ấy tự biến mất; nó có thể chỉ cho phép nhiều task tiếp tục chờ lâu hơn.

### 4.1. Bộ nhớ và độ trễ

Ước lượng tác động đến heap:

~~~text
RAM dùng bởi queue ≈ số task đang chờ × lượng bộ nhớ giữ bởi một task
                      + overhead của cấu trúc queue
~~~

Không thể thay thế lượng bộ nhớ giữ bởi một task bằng chunkSize × itemSize trong mọi triển khai. Có trường hợp task chưa đọc item, cũng có trường hợp task giữ sẵn dữ liệu hoặc closure tham chiếu đến object lớn. Dùng heap profile/GC metric và đo số task chờ thực tế để xác định.

Queue lớn còn có thể tạo độ trễ “ẩn”: request nộp task thành công tức thời nhưng task bắt đầu chạy rất muộn. Nếu timeout chỉ tính từ khi task bắt đầu chạy, các metric thông thường có thể bỏ sót thời gian nằm trong queue. Nên đo cả **queue wait time** và **execution time**.

## 5. Chọn giá trị theo nút thắt thực tế

Trước khi tăng queue capacity, xác định tốc độ tiêu thụ bị giới hạn bởi đâu:

| Nút thắt | Dấu hiệu | Cách tiếp cận |
|---|---|---|
| CPU | CPU cao kéo dài, runnable threads nhiều, thêm worker không tăng throughput | Giới hạn worker phù hợp CPU quota; queue chỉ đệm burst ngắn |
| Heap/GC | Queue tăng cùng heap, GC pause tăng, có nguy cơ OOM | Giảm queue, giảm dữ liệu giữ mỗi task/chunk và kiểm tra object retention |
| JDBC pool | active connections sát max, pending/timeout tăng | Giới hạn giao dịch đồng thời, giảm thời gian giữ connection, xem DB trước khi tăng pool |
| Database | DB CPU/IO/lock wait cao, rollback tăng | Tối ưu câu lệnh/transaction và giảm áp lực ghi; queue lớn không khắc phục database chậm |
| API/broker | Request 429/timeout, lag và retry tăng | Giới hạn rate, backoff có kiểm soát, consumer concurrency/prefetch phù hợp |
| I/O file | Disk latency, I/O wait và số handle cao | Điều chỉnh tốc độ đọc/ghi, batch size, tài nguyên I/O và cách đóng tài nguyên |

Một executor dùng cùng datasource với JobRepository cần chừa connection cho metadata và các hoạt động quản trị job. Với nhiều instance, năng lực database phải chịu **tổng** connection và tổng concurrency, không chỉ một executor. Nếu một writer gây transaction dài, tăng maxPoolSize từ 8 lên 32 và queue capacity từ 16 lên 1000 có thể tạo thêm chờ, lock và retry, khiến batch chậm hơn.

### Quy tắc chọn giá trị ban đầu

1. Xác định throughput mục tiêu, tốc độ task đến trong khoảng tăng đột biến và mức concurrency thực tế mà downstream chịu được.
2. Đặt corePoolSize và maxPoolSize phù hợp CPU, database, heap và workload; đừng đặt max tùy ý rồi kỳ vọng queue điều tiết mọi thứ.
3. Chọn vài mức queue hữu hạn đủ nhỏ để đo được thời gian chờ và đủ đệm cho burst thông thường.
4. Chốt chính sách khi queue đầy: chậm lại, từ chối, retry có giới hạn hoặc điều tiết producer.
5. Chạy benchmark cùng dữ liệu và hạ tầng; chọn mức đạt cả throughput **lẫn** độ trễ, bộ nhớ và khả năng restart.

## 6. Ví dụ cấu hình Spring Batch

Ví dụ sau sử dụng **ThreadPoolTaskExecutor** có core 4, tối đa 8 worker và tối đa 16 task chờ. Step dùng chunk-oriented processing theo phong cách cấu hình Spring Batch 5.x. Reader và writer trong ví dụ phải được triển khai sao cho an toàn khi nhiều thread gọi đồng thời.

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class BatchQueueTuningConfig {

    @Bean("batchChunkExecutor")
    ThreadPoolTaskExecutor batchChunkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("batch-chunk-");

        // Tạo backpressure ở bên nộp task khi pool và queue đã đầy.
        // Đánh giá kỹ ảnh hưởng đến Step và hành vi khi shutdown.
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.CallerRunsPolicy()
        );
        return executor;
    }

    @Bean
    Step tunedImportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<String> threadSafeReader,
            ItemProcessor<String, String> processor,
            ItemWriter<String> threadSafeWriter,
            @Qualifier("batchChunkExecutor")
            ThreadPoolTaskExecutor batchChunkExecutor) {

        return new StepBuilder("tunedImportStep", jobRepository)
            .<String, String>chunk(200, transactionManager)
            .reader(threadSafeReader)
            .processor(processor)
            .writer(threadSafeWriter)
            .taskExecutor(batchChunkExecutor)
            .build();
    }
}
~~~

**Vì sao chọn CallerRunsPolicy?** Khi pool và queue đầy, policy này có thể buộc thread nộp task tự chạy task, khiến tốc độ gửi việc giảm xuống. Nó là một phương án backpressure **cục bộ**; không tự kiểm soát tổng tốc độ message từ broker hoặc tất cả instance. Trong trạng thái executor đã shutdown, chính sách này có thể không thực thi task bị từ chối. Cần thử chính xác hành vi dừng job và restart ở phiên bản framework đang dùng.

Nếu cần phát hiện quá tải bằng lỗi rõ ràng để hệ thống điều phối quyết định retry, có thể cân nhắc **AbortPolicy** (ném RejectedExecutionException) cùng cơ chế xử lý lỗi ở tầng phù hợp. Tuy nhiên, trong một Spring Batch Step, rejection có thể khiến Step **FAILED**; không nên đổi policy một cách tùy tiện trên production. Cả hai chính sách đều phải được kiểm thử đầy đủ.

**Đặc biệt với ItemReader:** một số reader có trạng thái cursor và không thread-safe. Việc đặt @StepScope không mặc nhiên tạo một reader riêng cho mỗi thread trong cùng một StepExecution. Sử dụng reader có hỗ trợ concurrency, đồng bộ hóa theo nhu cầu hoặc chia dữ liệu bằng partition với StepExecution/reader độc lập. Đối với writer, cần xác minh transaction, thứ tự ghi và idempotency trước khi tăng concurrency.

### 6.1. Những điều queue capacity không điều khiển

- **Chunk size:** chunk(200) là số item xử lý cho mỗi chunk/transaction theo cấu hình này; queueCapacity(16) đếm task chờ, không phải 16 × 200 item.
- **Grid size:** số partition cần tạo không được suy ra từ queue capacity.
- **Số worker chạy thực tế:** ngoài core/max, còn chịu ảnh hưởng của cơ chế điều phối Step và việc các task có được gửi đủ nhanh hay không.
- **JDBC connection pool:** executor không biết giới hạn connection của datasource; phải tự tính dự phòng cho database.
- **Broker backlog:** queue cục bộ không giới hạn hàng đợi message bên ngoài hoặc số lượng job được khởi chạy bởi scheduler.

## 7. Đo queue trước và sau khi điều chỉnh

Nên xuất metric ở cùng một trục thời gian để thấy nguyên nhân và hệ quả. Với ThreadPoolTaskExecutor đã khởi tạo, có thể đọc các số liệu cơ bản từ ThreadPoolExecutor bên dưới:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Gọi khi Spring bean đã được khởi tạo.
ThreadPoolExecutor pool = batchChunkExecutor.getThreadPoolExecutor();
int active = pool.getActiveCount();
int poolSize = pool.getPoolSize();
int queued = pool.getQueue().size();
int remaining = pool.getQueue().remainingCapacity();
long completed = pool.getCompletedTaskCount();
~~~

Đoạn code này dùng để **quan sát**, không nên đặt vào vòng lặp nóng mỗi item. Có thể xuất số liệu qua Micrometer/Actuator hoặc hệ thống metrics đang có. Ngoài các gauge của pool, hãy đo:

| Metric | Câu hỏi cần trả lời |
|---|---|
| Executor active / pool size / max | Worker có đang hoạt động hết công suất không? |
| Queue depth / capacity / remaining | Backlog có tăng liên tục hay được xả sau mỗi burst? |
| Queue wait p50/p95/p99 | Task mất bao lâu từ khi được nộp đến khi bắt đầu chạy? |
| Task execution duration | Task chậm vì xử lý hay chỉ vì đứng chờ? |
| Rejection hoặc CallerRuns count | Có bao nhiêu lần chạm giới hạn? Producer có bị kéo chậm không? |
| Item throughput, chunk duration, commit/rollback | Batch hoàn tất dữ liệu nhanh và đúng đến mức nào? |
| Heap/GC, CPU, JDBC active/pending, DB lock/IO | Nút thắt nằm ở executor hay hệ thống phụ thuộc? |

**Lưu ý:** queue wait và số lần CallerRuns/rejection thường cần instrumentation bổ sung ở điểm nộp/chạy task. Chúng không tự động có trong mọi phiên bản Actuator hoặc metric của Spring Batch. completedTaskCount cũng không tương đương số item thành công hoặc số chunk commit.

Đọc chuỗi metric cùng nhau:

- Queue tăng, pool chỉ ở **core**, CPU/DB còn dư, max chưa đạt: queue có thể quá lớn và đang trì hoãn việc tạo worker.
- Queue đầy, active gần **max**, DB pending/lock wait tăng: downstream đang quá tải; tăng queue thường chỉ kéo dài thời gian chờ.
- Queue gần rỗng, active thấp, throughput vẫn kém: có thể cần kiểm tra cách Step nộp task, reader, query hoặc thời gian I/O; tăng capacity không giúp.
- Queue đầy trong burst ngắn, sau đó nhanh chóng trở về 0 và không có lỗi dữ liệu: một buffer hữu hạn có thể phù hợp.
- Queue và heap đều tăng lâu dài, p99 xấu dần: kiểm tra object retention và thời gian chờ trước khi tăng concurrency.

## 8. Ma trận benchmark queue capacity

Một thí nghiệm có ý nghĩa nên giữ cùng **dataset**, workload, số job đồng thời, chunk size, JDBC pool và tài nguyên CPU/RAM/DB. Chỉ thay queue capacity của **đúng executor đang dùng** rồi so sánh:

| Lần thử | core / max | queue capacity | Điều cần chú ý |
|---|---|---:|---|
| A | 4 / 8 | 0 | Thread tăng nhanh khi có burst; rejection đến sớm hơn |
| B | 4 / 8 | 8 | Một lượng đệm nhỏ, có thể mở thêm worker sớm |
| C | 4 / 8 | 16 | Cân bằng đệm burst và số task chờ, cần xác minh bằng metric |
| D | 4 / 8 | 64 | Có thể giảm rejection nhưng kéo dài queue wait, chậm tạo worker bổ sung |

Đây là **các giá trị thử nghiệm**, không phải benchmark kết quả hay khuyến nghị chung. Mỗi cấu hình nên được đo qua các pha:

1. **Baseline:** tải ổn định, lấy throughput và queue wait sau giai đoạn warm-up.
2. **Ramp:** tăng số job/partition hoặc tốc độ nộp task theo các mức có kiểm soát.
3. **Spike:** tạo một burst đủ ngắn để xem queue hấp thụ và xả tồn đọng ra sao.
4. **Soak:** duy trì tải lâu để phát hiện backlog không xả, heap tăng, leak connection hoặc GC kéo dài.
5. **Recovery:** giảm tải hoặc phục hồi dependency, xác nhận queue trở về mức nền và job xử lý lại đúng dữ liệu.

Số liệu bên dưới **hoàn toàn giả định**, dùng để luyện phân tích. Cùng một workload và hạ tầng, kết quả thực tế có thể khác:

| Queue | Throughput (item/s) | p95 queue wait | Lần bị quá tải | Heap sau GC |
|---:|---:|---:|---:|---:|
| 0 | 3.100 | 5 ms | 50 | 420 MiB |
| 8 | 3.700 | 80 ms | 8 | 450 MiB |
| 16 | 3.750 | 140 ms | 2 | 470 MiB |
| 64 | 3.500 | 700 ms | 0 | 620 MiB |

Ở ví dụ này, queue = 64 không có rejection nhưng latency và heap xấu hơn. Queue = 8 hoặc 16 có thể là ứng viên phù hợp nếu mục tiêu throughput, latency, lỗi và chính sách backpressure đều chấp nhận được. Phải đo thêm **CPU, active thread, JDBC pending, DB latency và dữ liệu đầu ra** trước khi kết luận.

### 8.1. Xây dựng ngưỡng PASS/FAIL

Đặt tiêu chí dựa trên mục tiêu của hệ thống, chẳng hạn:

- Ở tải thiết kế, throughput đạt ngưỡng mục tiêu và p95 queue wait không vượt SLO.
- Queue có thể tăng trong burst nhưng **xả hết backlog trong thời gian quy định** sau khi tải giảm.
- Heap sau GC, active connection và open file handle không tăng liên tục trong soak test.
- Khi quá tải, queue được giới hạn và lỗi/backpressure rõ ràng; không xuất hiện retry vô hạn hay backlog không thể phục hồi.
- Các bản ghi đích được đối soát, restart hoàn tất mà không mất hoặc ghi trùng side effect nghiệp vụ.

Không dùng một con số queue depth đơn lẻ làm tiêu chí đạt. Queue depth 0 có thể nghĩa là hệ thống thoải mái, nhưng cũng có thể vì producer đã bị chặn hoặc không thể nộp thêm công việc.

## 9. Khi queue đầy: backpressure, retry và restart

Queue đầy là tín hiệu hệ thống đang nhận việc nhanh hơn khả năng xử lý tại thời điểm đó. Cách ứng xử cần được thiết kế chủ động:

**Backpressure:** Giới hạn tốc độ tạo việc hoặc để producer chờ khi downstream bão hòa. CallerRunsPolicy có thể giúp ở một executor trong một JVM; với workload phân tán, cần thêm giới hạn ở scheduler, gateway, broker consumer, prefetch hoặc số partition thực thi.

**Rejection:** Nếu chọn policy từ chối, theo dõi số lần từ chối và xác định tầng nào sẽ chịu trách nhiệm retry. Từ chối liên tục kèm retry ngay lập tức có thể tạo vòng lặp làm quá tải nặng hơn.

**Retry/backoff:** Chỉ retry lỗi tạm thời, đặt max attempts, backoff và jitter phù hợp. Cạn JDBC connection do DB chậm thường không được khắc phục bằng hàng nghìn request retry đồng thời.

**Restart:** Queue trong bộ nhớ **không phải kho tác vụ bền vững**. Nếu JVM dừng đột ngột, task trong queue có thể biến mất. Đừng dùng queue của executor như một cơ chế bảo đảm delivery. Spring Batch sử dụng JobRepository, StepExecution, ExecutionContext và transaction/checkpoint để hỗ trợ restart theo semantics của từng reader/writer; tính đúng đắn cuối cùng còn phụ thuộc khả năng idempotent của thao tác ghi và khả năng xác định tiến độ đã commit.

Trong phép thử lỗi, hãy gây quá tải hoặc ngắt dependency trên môi trường cô lập, sau đó:

1. Thu thập trạng thái Job/Step, lỗi, số commit/rollback và backlog trước khi khôi phục.
2. Khôi phục tài nguyên, restart **đúng JobInstance** theo cơ chế thích hợp.
3. Đối chiếu khóa duy nhất, tổng số bản ghi và side effect với kết quả dự kiến.
4. Xác minh executor queue, connection và heap trở về mức ổn định sau khi kết thúc.

Nếu dùng scheduler tự động khởi chạy lại toàn bộ job với JobParameters khác, bạn có thể vô tình tạo JobInstance mới thay vì restart job lỗi; điều đó làm kết quả kiểm thử sai lệch và tăng nguy cơ xử lý trùng.

## 10. Sai lầm phổ biến

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Đặt queue rất lớn để “không bao giờ reject” | Task đợi lâu, memory tăng, phát hiện quá tải muộn | Đặt queue hữu hạn theo burst và đo queue wait |
| Tăng maxPoolSize nhưng giữ queue quá lớn | Worker có thể chỉ hoạt động ở mức core trong thời gian dài | Kiểm tra trình tự core → queue → max và thử queue nhỏ hơn |
| Cho rằng queue capacity là số item có thể xử lý | Ước lượng sai heap và concurrency | Phân biệt Runnable, chunk, item, partition và broker message |
| Tăng queue khi database đã đầy connection | Chuyển nghẽn thành thời gian chờ và timeout dài hơn | Điều tiết số transaction đồng thời, tối ưu DB/connection |
| Chỉ đo throughput cuối job | Không thấy p95/p99 queue wait, GC hoặc backlog trong burst | Đo chuỗi metric theo thời gian ở cả ứng dụng và downstream |
| Coi queue là lưu trữ bền vững | Mất task chờ khi tiến trình sập, restart có thể sai | Dựa vào checkpoint, JobRepository, idempotency và broker khi cần |
| Giả định TaskExecutor nào cũng có queueCapacity | Đặt cấu hình sai lớp executor hoặc không có hiệu lực | Kiểm tra đúng implementation; SimpleAsyncTaskExecutor có cơ chế concurrency riêng |

## 11. Bài thực hành

**Tình huống:** Một job import 5 triệu bản ghi được chia thành các partition. Hệ thống có 8 vCPU, JDBC pool tối đa 12 connection và một số connection dành cho JobRepository cùng tác vụ khác. Executor hiện được đặt corePoolSize 4, maxPoolSize 12, queueCapacity 1.000. Dashboard cho thấy queue dài hàng trăm task nhưng số active thread thường chỉ quanh 4; p95 thời gian bắt đầu xử lý tăng dù CPU chưa bão hòa.

Hãy thực hiện theo thứ tự:

1. Nêu giả thuyết vì sao maxPoolSize 12 chưa phát huy hiệu lực. Xác minh giả thuyết bằng pool size, active count, queue depth và số worker/partition thực chạy.
2. Thử queue capacity lần lượt 0, 8, 16 và 64, trong khi cố định workload, chunk size và tài nguyên hệ thống.
3. Với mỗi lần thử, ghi throughput, p95/p99 queue wait, executor rejection/CallerRuns, heap/GC, JDBC pending và thời gian hoàn tất job.
4. Tạo một burst ngắn có giới hạn; kiểm tra queue có được xả sau khi tải giảm không và tác động đến p95.
5. Chọn queue capacity có đủ dự phòng cho burst nhưng không làm che giấu nghẽn database. Kiểm tra restart, dữ liệu đầu ra và số bản ghi trùng sau một lỗi có kiểm soát.

**Câu hỏi tự kiểm tra:**

- Vì sao maxPoolSize = 12 chưa chắc dẫn đến 12 worker hoạt động khi queueCapacity = 1.000?
- Khi nào nên thử queueCapacity = 0, và rủi ro của nó với workload burst là gì?
- Vì sao queue depth tăng đồng thời với JDBC pending là dấu hiệu phải kiểm tra database trước khi tăng queue?
- Khác biệt giữa queue capacity của manager executor và backlog message tại broker trong remote partitioning là gì?
- Nếu throughput cao hơn 5% nhưng p99 queue wait tăng gấp 10 lần, bạn cần thêm số liệu nào để ra quyết định?

## 12. Ghi nhớ

Queue capacity kiểm soát **khối lượng công việc được phép chờ**, còn throughput bền vững phụ thuộc năng lực thật của worker và các hệ thống phía sau. Trong ThreadPoolTaskExecutor, việc **queue trước rồi mới tăng từ core đến max** khiến queue capacity ảnh hưởng trực tiếp đến số thread được tạo và độ trễ. Điều chỉnh queue phải đi cùng giám sát active worker, queue wait, heap/GC, JDBC connection, database và các cơ chế retry/restart. Một giá trị tốt là giá trị hấp thụ được burst cần thiết, làm quá tải xuất hiện rõ ràng và vẫn hoàn thành dữ liệu đúng trong giới hạn tài nguyên thực tế.
