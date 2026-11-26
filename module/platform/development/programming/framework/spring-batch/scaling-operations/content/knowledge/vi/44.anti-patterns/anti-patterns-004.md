# Anti-pattern: Dùng queue vô hạn khi mở rộng Spring Batch

## 1. Tại sao queue vô hạn là một anti-pattern?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, chúng ta mở rộng Spring Batch cho dữ liệu lớn bằng **multi-threaded step**, **parallel steps**, **partitioning** và xử lý phân tán, đồng thời phải bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế. Một sai lầm phổ biến là đặt **queue capacity cực lớn hoặc không giới hạn thực tế** để hệ thống luôn nhận thêm tác vụ, với hy vọng rằng không bị từ chối thì batch job sẽ xử lý nhanh hơn.

**Queue vô hạn (unbounded queue)** là hàng đợi cho phép thêm công việc mà không có giới hạn hữu dụng trước khi hết bộ nhớ, dung lượng lưu trữ, quota của dịch vụ hoặc khả năng phục vụ. Trong Java, một queue có thể có giới hạn số phần tử rất lớn về mặt kỹ thuật, nhưng với heap hữu hạn, nó vẫn hành xử giống queue vô hạn: producer tiếp tục thêm task, còn consumer không theo kịp.

Vấn đề cốt lõi: **queue chứa công việc chưa được xử lý; queue không tạo ra năng lực xử lý mới**. Khi tốc độ đưa việc vào liên tục lớn hơn tốc độ hoàn tất, backlog tăng. Đến một thời điểm, người vận hành gặp OOM, GC kéo dài, timeout, job hoàn thành quá muộn hoặc phải xử lý nhiều công việc đã trở nên lỗi thời.

Sau bài học, bạn có thể:

- Nhận diện các kiểu queue không có giới hạn hiệu quả trong ThreadPoolTaskExecutor, message broker và pipeline batch.
- Giải thích thứ tự **core threads → queue → max threads → rejection** và lý do maxPoolSize không phát huy tác dụng khi queue quá lớn.
- Đo backlog, queue wait, throughput, heap, JDBC contention và thời gian drain sau khi giảm tải.
- Thiết kế **bounded queue**, backpressure, concurrency limit và overload policy phù hợp từng kiến trúc.
- Kiểm thử tính đúng đắn của dữ liệu và khả năng restart khi queue đầy, worker gặp lỗi hoặc bị dừng đột ngột.

> **Thuật ngữ:** Bài này gọi queue là *vô hạn* khi nó có thể phình to vượt ngân sách tài nguyên và thời gian chờ của hệ thống, kể cả khi cấu trúc dữ liệu có sức chứa lý thuyết như Integer.MAX_VALUE. Đây là anti-pattern về **khả năng kiểm soát tải**, không đơn thuần là giá trị một tham số.

## 2. Phân biệt queue với concurrency, chunk và partition

Không thể lựa chọn queue capacity nếu chưa biết queue đang đếm những gì.

| Khái niệm | Đếm gì? | Ý nghĩa khi vận hành |
|---|---|---|
| **Active threads** | Task đang được worker thực thi | Năng lực xử lý đồng thời tại executor |
| **Executor queue depth** | Runnable/task đã nộp nhưng chưa chạy | Backlog bên trong một process |
| **Queue capacity** | Số task được phép **chờ**, không bao gồm task đang chạy | Giới hạn buffer của executor |
| **Chunk size** | Số item mục tiêu được xử lý trong một chunk/transaction | Phạm vi commit, bộ nhớ và rollback |
| **Grid size** | Số partition được chia | Cách chia công việc, không đồng nghĩa worker đồng thời |
| **Broker queue depth / consumer lag** | Message chưa được tiêu thụ/ack hoặc chậm theo cursor, tùy broker | Backlog bền vững/phân tán ở ngoài process |
| **JDBC pool size** | Số kết nối tối đa mà datasource cấp cho application | Giới hạn tài nguyên DB, độc lập queue executor |

Ví dụ, **queueCapacity = 1.000** trong ThreadPoolTaskExecutor không có nghĩa 1.000 item đang được xử lý, cũng không có nghĩa 1.000 thread. Nếu mỗi task đại diện một chunk, số item tương ứng còn phụ thuộc vào lúc task đọc item và những dữ liệu nó giữ. Một Runnable có thể rất nhỏ hoặc giữ cả object graph lớn.

## 3. Cơ chế khiến queue lớn che khuất maxPoolSize

ThreadPoolTaskExecutor của Spring Framework thường dựa trên **ThreadPoolExecutor** của Java. Với hàng đợi dạng LinkedBlockingQueue có capacity dương, trình tự nhận một task mới về cơ bản là:

1. Nếu số worker ít hơn **corePoolSize**, tạo worker để xử lý.
2. Khi đã đủ core worker, thử **đưa task vào queue**.
3. Chỉ khi queue không còn nhận được task, thử mở thêm worker tới **maxPoolSize**.
4. Nếu cả queue và pool đều đã chạm giới hạn, dùng **RejectedExecutionHandler**.

~~~mermaid
flowchart TD
    A[Task mới] --> B{Worker ít hơn core?}
    B -->|Có| C[Chạy bằng core worker mới]
    B -->|Không| D{Queue còn sức chứa?}
    D -->|Có| E[Task phải chờ]
    D -->|Không| F{Worker ít hơn max?}
    F -->|Có| G[Tăng worker]
    F -->|Không| H[Overload / rejection policy]
~~~

**Hệ quả:** cấu hình corePoolSize = 4, maxPoolSize = 32, queueCapacity = Integer.MAX_VALUE có thể chỉ dùng khoảng **4 worker** khi hàng đợi còn chỗ, dù CPU vẫn rảnh và queue đã dài hàng nghìn task. Không nên thấy maxPoolSize = 32 rồi suy ra batch chạy 32 chunk cùng lúc.

Với **ThreadPoolTaskExecutor**, cấu hình queueCapacity mặc định trong nhiều phiên bản Spring Framework là **Integer.MAX_VALUE**, có thể hành xử như queue không giới hạn trên thực tế. Cần kiểm tra bean cấu hình hiệu lực và phiên bản thư viện, vì ứng dụng có thể dùng executor khác hoặc có layer hạn chế task submission.

Với queueCapacity = 0, executor sử dụng cơ chế giao việc trực tiếp như **SynchronousQueue**, không giữ task chờ trong hàng đợi, nên pool có thể tăng đến max nhanh hơn. Đây cũng **không phải** giải pháp mặc định: khi task đến theo đợt, hệ thống có thể chạm max và từ chối rất sớm.

### Ví dụ trực quan

Một executor có core = 4, max = 8 và queue = 16. Nếu 25 task được đưa đến nhanh hơn tốc độ hoàn thành, về mặt lý thuyết 4 task đầu dùng core workers, 16 task tiếp theo chờ, 4 task sau làm pool tăng lên 8 và task cuối chạm policy khi đầy. Nếu queue thay thành một triệu, executor có thể chỉ xử lý bằng 4 worker trong thời gian dài, còn task dồn vào hàng đợi.

Đây là mô hình để hiểu hành vi ThreadPoolExecutor; Spring Batch còn có cơ chế điều phối chunk/step, giới hạn đồng thời ở tầng framework tùy phiên bản và TaskExecutor thực tế. **Phải đo active workers và queued tasks của đúng executor đang được dùng**, không chỉ đọc một thuộc tính cấu hình.

## 4. Khi backlog tăng: toán học và hậu quả thực tế

Gọi:

- **λ**: số task được gửi đến trong một giây.
- **μ**: số task executor hoàn tất bền vững trong một giây.
- **Q(t)**: số task chờ tại thời điểm t.

Nếu trong một khoảng đủ dài **λ lớn hơn μ** và chưa chặn producer, backlog tăng gần đúng:

~~~text
Q(t + Δt) ≈ Q(t) + (λ - μ) × Δt
~~~

Giả sử manager đẩy **120 task/giây** nhưng worker chỉ hoàn tất **90 task/giây**. Sau 3 phút, backlog tăng khoảng **(120 - 90) × 180 = 5.400 task**. Nếu mỗi task đang chờ giữ trung bình 12 KiB object, chỉ riêng phần tham chiếu và object còn sống đã vào khoảng **63 MiB**, chưa tính queue node, object trung gian, GC, item buffers, log và business state.

Trong thực tế, lượng bộ nhớ giữ bởi mỗi task rất khác nhau. Có task chỉ chứa callback nhỏ; có task giữ danh sách item, request DTO, byte array hoặc tham chiếu đến một graph lớn. Vì vậy hãy dùng **heap dump/JFR/GC và retained heap** để xác định, không coi phép nhân ví dụ là dự báo RAM chính xác.

Nếu tải trở về bình thường, queue chỉ được xả khi consumer chạy **nhanh hơn** lượng việc mới đến:

~~~text
Thời gian drain ≈ backlog hiện có / (μ - λ_sau_burst)
Điều kiện: μ > λ_sau_burst, throughput tương đối ổn định
~~~

Chẳng hạn backlog còn 900 task, năng lực xử lý 100 task/giây và producer sau burst vẫn đưa tới 70 task/giây, cần khoảng **30 giây** để xả queue trong mô hình đơn giản. Nếu producer tiếp tục 110 task/giây, backlog sẽ **không tự giảm**.

### Định luật Little và "độ trễ ẩn"

Trong trạng thái ổn định, định luật Little đưa ra quan hệ:

~~~text
Lq = λ_effective × Wq

Lq: số task chờ trung bình
λ_effective: tốc độ task đi qua hàng đợi trong hệ ổn định
Wq: thời gian chờ trung bình trước khi task bắt đầu chạy
~~~

Queue sâu trung bình 2.000 task với throughput hiệu dụng 100 task/giây có thể tương ứng **20 giây chờ trung bình**, ngay cả khi thời gian xử lý riêng một task chỉ vài trăm mili giây. Khi job có SLA hoàn tất trước giờ báo cáo, loại chờ này rất quan trọng.

**Queue không làm mất overload:** nó chuyển lỗi bị từ chối ngay thành độ trễ, lãng phí RAM/disk và nguy cơ thất bại sau một khoảng thời gian dài.

## 5. Hậu quả điển hình của queue "vô hạn"

| Hậu quả | Chuỗi nguyên nhân | Điều thường quan sát |
|---|---|---|
| **OutOfMemoryError** | Task/object giữ trong queue tăng theo backlog | Heap used sau GC tăng, GC dày, OOM hoặc container OOMKilled |
| **Latency không có trần** | Task chờ quá lâu nhưng producer tưởng nộp việc thành công | Queue wait p95/p99 tăng, job trễ deadline |
| **maxPoolSize không phát huy** | LinkedBlockingQueue nhận task trước khi mở worker ngoài core | Queue dài, active threads chỉ quanh core |
| **Công việc lỗi thời** | Task bị xử lý sau khi dữ liệu/phiên bản/điều kiện nghiệp vụ đã đổi | Kết quả muộn, phải kiểm tra lại quyền và thời hạn nghiệp vụ |
| **Shutdown khó hoàn tất** | Hàng nghìn task đang chờ drain khi deploy/stop | Dừng kéo dài, thời gian recovery lớn |
| **Thất thoát task trong RAM** | Process crash, queue executor không được lưu bền vững | Queue mất; phải dựa vào JobRepository/checkpoint/re-delivery |
| **Tải dồn vào downstream** | Backlog được xả một lượt sau khi DB/API phục hồi | JDBC pending, rate limit, retry, DB lock tăng |
| **Che giấu lỗi vận hành** | Producer không nhận tín hiệu bão hòa nên tiếp tục bơm việc | Input accepted cao nhưng completed rate đứng yên |

Nói "queue vô hạn chắc chắn gây memory leak" là chưa chính xác: backlog có thể là **tồn đọng do tải liên tục cao hơn khả năng xử lý**, khác với leak khi object không được giải phóng dù công việc đã hoàn tất. Tuy nhiên, triệu chứng về retained heap có thể giống nhau; phải đo cả **queue depth và số task hoàn thành**.

## 6. Chọn đúng vị trí queue đang gây hại

### 6.1. Multi-threaded step

Trong multi-threaded step, TaskExecutor có thể nhận công việc xử lý chunk. Nếu queue của nó không giới hạn, một nhịp nộp việc nhanh hơn xử lý có thể tạo backlog nội bộ. Tốc độ nộp việc và số task chờ thực tế phụ thuộc cơ chế Step ở phiên bản Spring Batch chạy thật.

Điểm cần đo: active pool threads, queued tasks, chunk duration, item throughput, read/write/commit/rollback count, heap và thời gian chờ JDBC connection.

### 6.2. Parallel steps

Một Flow có thể chạy nhiều step song song. Executor điều phối flow/step và executor riêng của từng step có thể **cùng tồn tại**. Nếu có nhiều pool, tổng bộ nhớ giữ task, worker đồng thời và connection DB của **mọi pool** mới là tải thực.

Không dùng queue lớn để bù cho việc khởi chạy quá nhiều job/flow đồng thời. Cần điều phối admission ở scheduler/launcher và xác định ngân sách cho từng job.

### 6.3. Local partitioning

Manager có thể tạo nhiều StepExecution cho partition, rồi đưa tác vụ vào TaskExecutorPartitionHandler. **gridSize** thể hiện độ chia công việc; không nhất thiết là số partition đồng thời. Queue dài làm các partition chờ lâu; khi manager hoặc process chết, khả năng restart vẫn phải dựa vào metadata và trạng thái đã commit, không dựa vào queue executor còn nguyên.

Đặc biệt, một partition chứa vùng dữ liệu quá rộng có thể tạo **skew**: một worker chạy rất lâu, các worker khác rảnh, trong khi tổng thời gian job vẫn tệ. Tăng queue capacity không xử lý được skew hay partition sizing.

### 6.4. Remote partitioning và remote chunking

Với topology qua RabbitMQ/Kafka/JMS, có thể có **nhiều tầng queue**: manager executor, request broker, consumer prefetch/in-flight, worker executor và reply channel. Giới hạn một queue **không tự động** giới hạn các queue còn lại.

| Tầng | Đang giới hạn gì? | Cách kiểm soát |
|---|---|---|
| Manager/Scheduler | Số job hoặc partition được tạo/nộp | Admission limit, tránh launch trùng, định mức theo job |
| Request broker | Số lượng message/backlog được lưu và chuyển | Quota, max length/retention, TTL và xử lý overflow có kiểm soát tùy broker |
| Consumer | Số message nhận nhưng chưa ack | Prefetch, consumer concurrency, ack policy |
| Worker executor | Số task đang chạy và đang chờ | Core/max, bounded queue, rejection/backpressure |
| DB/API | Transaction và request thực sự đồng thời | Pool, rate limit, timeout, backoff, DB tuning |

Kafka thường quản lý backlog trên log và consumer lag theo partition/offset; RabbitMQ có queue depth và unacked messages. Không đồng nhất semantics của các broker, đặc biệt **message retention và delivery guarantee**.

Trong **remote chunking**, request có thể chứa item nghiệp vụ. Broker retention và log có thể lưu dữ liệu nhạy cảm; quota/TTL/DLQ phải đi cùng chính sách bảo vệ dữ liệu. Trong **remote partitioning**, request chủ yếu điều phối StepExecution nhưng backlog vẫn ảnh hưởng deadline và khả năng recovery.

## 7. Anti-pattern trong code và cấu hình

Đây là ví dụ **không nên đưa trực tiếp vào production** khi kỳ vọng hệ thống tự giới hạn:

~~~java
@Bean
ThreadPoolTaskExecutor unsafeExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(32);
    executor.setQueueCapacity(Integer.MAX_VALUE);
    executor.setThreadNamePrefix("batch-unsafe-");
    return executor;
}
~~~

Vấn đề ở cấu hình này:

1. Pool có thể tiếp tục dùng khoảng bốn core threads, vì queue khổng lồ thường chưa bao giờ đầy để kích hoạt tăng lên 32 worker.
2. Backlog được chấp nhận không có ngưỡng hữu ích về thời gian chờ và RAM.
3. Không định nghĩa hành vi overload rõ ràng ở ngưỡng phù hợp tài nguyên, nên lỗi có thể chuyển thành GC/OOM hoặc deadline miss.
4. Cấu hình không có bằng chứng rằng downstream database/API chịu được concurrency cao hơn nếu sau này thay queue.

**Không phải cứ dùng LinkedBlockingQueue là sai.** Vấn đề là **capacity thiếu ngân sách và thiếu quan sát**; hàng đợi hữu hạn, có monitoring và chính sách quá tải hợp lý là một công cụ bình thường.

## 8. Thay thế bằng bounded queue và overload policy

Một lựa chọn thực tế là đặt queue **hữu hạn**, giới hạn thread dựa trên CPU/JDBC và chọn policy khi đầy. Ví dụ cho **Spring Batch 5.x** và Spring Framework tương ứng:

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
class BoundedBatchExecutorConfig {

    @Bean("boundedBatchExecutor")
    ThreadPoolTaskExecutor boundedBatchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("batch-worker-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.CallerRunsPolicy()
        );
        return executor;
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<String> threadSafeReader,
            ItemProcessor<String, String> processor,
            ItemWriter<String> threadSafeWriter,
            @Qualifier("boundedBatchExecutor")
            ThreadPoolTaskExecutor executor) {
        return new StepBuilder("importStep", jobRepository)
            .<String, String>chunk(200, transactionManager)
            .reader(threadSafeReader)
            .processor(processor)
            .writer(threadSafeWriter)
            .taskExecutor(executor)
            .build();
    }
}
~~~

Con số **4/8/16/200** chỉ là giá trị thí nghiệm ban đầu, **không phải default khuyến nghị cho mọi workload**. Trước khi áp dụng:

- Reader và writer phải thread-safe khi một StepExecution được nhiều thread xử lý; không giả định **@StepScope** tự tạo reader riêng theo thread.
- JobRepository, datasource, DB và API phải chịu được số transaction/request thực sự đồng thời.
- Một số thế hệ Spring Batch điều tiết concurrency ở tầng Step ngoài executor. Kiểm tra API đang dùng và **đo** active worker thật.
- Trong Java, CallerRunsPolicy khiến **thread nộp task tự thực thi** khi pool/queue đầy và executor chưa shutdown, có thể làm chậm producer. Cần xác minh ngữ nghĩa với Step/chunk scheduling, transaction và shutdown trên phiên bản thực tế.

Nếu chọn policy **AbortPolicy**, khi quá tải có thể phát sinh rejection exception, và trong một Spring Batch Step có thể dẫn đến FAILED. Chỉ chọn nếu hệ thống có xử lý lỗi, alert, retry/restart phù hợp; **không** nuốt exception hoặc mặc nhiên bỏ task để giữ trạng thái job COMPLETED.

## 9. Bounded queue không thay thế admission control

Ngay cả khi worker executor queue hữu hạn, hệ thống vẫn có thể quá tải nếu scheduler tiếp tục tạo vô số job hoặc broker tích lũy message không giới hạn.

Các tầng kiểm soát cần được phối hợp:

| Tầng | Quyết định cần đặt | Ví dụ chính sách |
|---|---|---|
| **Job admission** | Có được khởi chạy thêm job cùng loại không? | Giới hạn job active theo tenant/workload, tránh duplicate JobInstance |
| **Partition scheduling** | Bao nhiêu partition đang hoạt động? | Giới hạn concurrent StepExecution theo DB/CPU |
| **Executor** | Bao nhiêu task chờ trước khi backpressure? | Bounded queue và overload policy có giám sát |
| **Broker** | Backlog tối đa lưu được là bao nhiêu? | Retention/quota/max-length và đường xử lý overflow được thử |
| **Consumer** | Bao nhiêu message in-flight? | Prefetch và ack policy phù hợp |
| **Downstream** | Bao nhiêu giao dịch/request được xử lý đồng thời? | JDBC pool, API rate limiter, timeout, backoff |

Một message broker có thể chặn publish, trả lỗi, bỏ message, chuyển DLQ hoặc giữ lại theo cơ chế khác khi đầy. **Không cấu hình giới hạn rồi mặc định tin rằng không mất dữ liệu**. Với batch cần tính đúng đắn, hãy thử chính xác cơ chế overflow, publisher confirm, retry, deduplication và cơ chế replay. Phải nắm rõ task nào đã được Spring Batch ghi nhận trong JobRepository và task nào chỉ tồn tại ở tầng broker.

### Tại sao CallerRuns không đủ với mô hình phân tán?

CallerRuns làm chậm **một thread producer cục bộ** khi một executor đầy. Nhưng manager replica khác, scheduler khác hoặc consumer broker khác vẫn có thể tạo thêm việc. Với nhiều JVM/replica, cần một chính sách admission trên toàn workload hoặc quota phân tán có thể quan sát, thay vì tin một queue cục bộ sẽ bảo vệ toàn cụm.

## 10. Tính capacity dựa vào burst và thời gian chờ

Không có công thức duy nhất cho mọi workload. Có thể chọn khoảng giá trị để thử bằng hai cách nhìn bổ sung.

**Đệm burst:** nếu producer tăng tạm thời lên λ_burst task/giây, worker xử lý μ task/giây trong thời gian T, backlog có thể tăng:

~~~text
Q_burst ≈ max(0, (λ_burst - μ) × T)
~~~

**Ngân sách thời gian chờ:** với hệ ổn định và throughput hiệu dụng λ_effective, định luật Little gợi ý:

~~~text
Q_wait_budget ≈ λ_effective × Wq_max
~~~

Hai ước lượng giúp nhận ra mâu thuẫn: nếu burst dự kiến cần đệm 1.000 task, nhưng SLA chỉ cho phép chờ trong vài giây, **không thể đạt cả hai chỉ bằng queue**. Cần điều tiết producer, tăng năng lực xử lý thật hoặc thương lượng SLO. Đừng xem Q_wait_budget là giới hạn cứng đảm bảo p99; thời gian task biến động, skew và hàng đợi có thể làm tail latency cao hơn.

Tiếp đó đo **heap retained theo queued task** và đặt ngân sách bộ nhớ:

~~~text
Q_memory_budget ≈ RAM dành cho queue / retained bytes trung bình mỗi task
~~~

Cần chừa RAM cho JVM baseline, chunk đang chạy, JDBC buffers, caches, GC và các job khác. Nếu cùng một máy chạy nhiều executor, cộng tổng retained bytes của **mọi queue**.

Cuối cùng chọn capacity thử nghiệm **không vượt ngân sách bộ nhớ và thời gian chờ**, có guardrail và overload policy rõ ràng. Giá trị phù hợp có thể là 0, 8, 16, 64 hoặc một mức khác tùy workload; không có lý do dùng Integer.MAX_VALUE chỉ để tránh cấu hình.

## 11. Quan sát để phát hiện queue phát triển vô hạn

Các metric cần đặt cùng một trục thời gian:

| Nhóm | Chỉ số | Điều muốn biết |
|---|---|---|
| Executor | activeCount, poolSize, maxPoolSize | Có thực sự chạy nhiều worker không? |
| Queue | depth, capacity, remainingCapacity | Backlog tăng liên tục, chạm giới hạn hay được drain? |
| Độ trễ | submit-to-start p50/p95/p99, task execution duration | Chậm vì chờ hay vì xử lý? |
| Batch | readCount, writeCount, commitCount, rollbackCount, skip/filter count | Có hoàn tất đúng nghiệp vụ không? |
| Runtime | heap used/old-gen, GC pause, CPU, thread count | Queue giữ object hay worker thiếu CPU? |
| Data/backend | JDBC active/pending, DB locks/IO, API 429/5xx | Nút thắt có nằm ở downstream không? |
| Remote | broker queue depth, consumer lag, unacked/prefetch, DLQ | Broker đang tích lũy việc hay worker đang chậm? |
| Reliability | retry count, restart count, rejected tasks, lost/duplicate records | Quá tải có làm sai dữ liệu không? |

Với ThreadPoolTaskExecutor đã được Spring khởi tạo, có thể đọc snapshot:

~~~java
ThreadPoolExecutor pool = batchExecutor.getThreadPoolExecutor();
int running = pool.getActiveCount();
int waiting = pool.getQueue().size();
int availableQueueSlots = pool.getQueue().remainingCapacity();
long finishedTasks = pool.getCompletedTaskCount();
~~~

Đây là code **quan sát**, giả sử batchExecutor là bean ThreadPoolTaskExecutor đang chạy. Muốn có **queue wait duration** hoặc số task thực thi qua CallerRuns, thường phải thêm instrumentation tại điểm submit/chạy task. completedTaskCount không đồng nghĩa số chunk đã commit hay số item ghi thành công.

Các mẫu tín hiệu:

1. **Queue tăng, active ≈ core, CPU còn dư:** kiểm tra quy tắc queue-before-max, Step throttling và producer scheduling; tăng maxPoolSize riêng lẻ có thể vô tác dụng.
2. **Queue tăng, active ≈ max, JDBC pending cao:** downstream có thể bão hòa; tăng pool/queue không nên là phản xạ đầu tiên.
3. **Queue tăng và heap after-GC tăng:** ước lượng retained bytes, phân biệt backlog hợp lệ với object leak, kích hoạt guardrail.
4. **Queue bằng 0 nhưng throughput thấp:** có thể không đủ việc được nộp, reader/DB bị nghẽn hoặc producer bị chặn; queue nhỏ không nhất thiết là lỗi.
5. **Queue tăng đột biến rồi tự hết sau một thời gian ngắn:** đây có thể là burst bình thường nếu queue wait, RAM và deadline đều trong ngân sách.

## 12. Bảng kết quả minh họa: queue càng lớn chưa chắc càng nhanh

Giả sử một job nhập cùng dataset, chunk size 200, executor core 4/max 8 và JDBC pool không đổi. Số liệu sau là **giả định phục vụ học tập**, không phải benchmark thực của Spring Batch:

| Queue capacity | Throughput (item/s) | p95 queue wait | Queue depth cực đại | Heap sau GC | Quá tải được báo |
|---:|---:|---:|---:|---:|---|
| 0 | 3.150 | 4 ms | 0 | 420 MiB | Nhiều lần trong burst |
| 8 | 3.680 | 70 ms | 8 | 445 MiB | Một số lần |
| 16 | 3.730 | 130 ms | 16 | 470 MiB | Rất ít |
| 64 | 3.540 | 650 ms | 64 | 570 MiB | Không |
| Rất lớn | 3.100 | 4.800 ms | 3.200 | 1.450 MiB | Chưa có tín hiệu overload rõ |

Không nên kết luận queue = 16 là tối ưu nếu chưa có mục tiêu SLO và phép thử lặp lại. Nhưng bảng cho thấy queue **rất lớn** có thể ghi nhận ít sự kiện rejection hơn trong khi throughput, latency và heap đều tệ hơn.

Nếu số rejected thấp hơn nhưng hệ thống đạt p99 chờ vài phút và không hoàn tất batch đúng deadline, thì "không bị từ chối" **không phải** thước đo thành công.

## 13. Kiểm thử anti-pattern và phương án thay thế

### 13.1. Chuẩn bị

Chạy trên staging/cụm kiểm thử cô lập, dữ liệu cố định đủ đại diện cho production, có cách đối soát output. Ghi rõ JDK, Spring Batch, số replica, CPU/RAM quota, chunk size, pool, grid size, broker, DB và thời gian chạy. Đảm bảo không ảnh hưởng dịch vụ khác dùng chung database hoặc broker.

### 13.2. Ma trận test

| Pha | Thao tác | Dữ liệu cần quan sát |
|---|---|---|
| Baseline | Tải ổn định dưới năng lực hệ thống | Throughput, queue wait, heap, active workers |
| Ramp | Tăng tốc độ task đến hoặc số job/partition | Điểm queue bắt đầu tăng kéo dài |
| Spike | Gửi burst ngắn rồi hạ tải | Queue đạt đỉnh bao nhiêu, drain mất bao lâu |
| Soak | Duy trì tải cao hợp lệ nhiều chu kỳ | Heap sau GC, queue drift, leak connection |
| Downstream slowdown | Cố ý làm chậm DB/API test, có giới hạn timeout | Queue tăng thế nào, backpressure hoạt động không |
| Overload | Tăng tải quá mức trong guardrail | Có rejection/fail rõ, timeout và retry có giới hạn không |
| Recovery | Khôi phục downstream, restart job lỗi | Đối soát output, queue trở về mức nền |

**Chỉ thay queue capacity trong một loạt thử**, giữ core/max, dataset, CPU và DB quota cố định. Sau đó mới thực hiện loạt riêng để thay max workers, chunk size hoặc JDBC pool. Nếu đổi tất cả cùng lúc, không phân tích được nguyên nhân.

**Guardrail:** tự dừng thử khi heap/GC vượt ngưỡng an toàn, database/pool pending kéo dài, queue tăng không kiểm soát hoặc lỗi ảnh hưởng tới người dùng khác. Đặt max duration, retry limits, giới hạn đầu vào và rollback plan; không cố làm OOM production để chứng minh anti-pattern.

### 13.3. Tiêu chí PASS/FAIL

Ví dụ tiêu chí cho môi trường thử có SLO rõ ràng:

- Ở tải mục tiêu, throughput và thời gian hoàn tất đạt deadline.
- p95/p99 queue wait nằm trong ngưỡng đã chọn và backlog được drain trước thời hạn quy định.
- Không có OOM, long GC stall hay retained heap tăng không dừng.
- Khi vượt tải, hệ thống **phản hồi theo policy dự kiến**, không âm thầm bỏ item hoặc tạo retry storm.
- Khi worker/broker/DB gặp lỗi có kiểm soát, restart xử lý đúng JobInstance và đối soát không mất/trùng dữ liệu.

Trong stress test cố ý vượt năng lực hệ thống, **có lỗi bị từ chối đúng chính sách có thể là kết quả chấp nhận được**; mục đích là chứng minh overload hữu hạn, có thể quan sát và phục hồi.

## 14. Retry, restart và tính đúng đắn khi queue đầy

Một bounded queue có thể khiến việc nộp task bị chậm hoặc bị từ chối. Điều này phải được thiết kế như một **trạng thái vận hành hợp lệ**, không phải tình huống bị nuốt exception.

- **Retry có phân loại:** chỉ retry lỗi tạm thời với backoff/jitter và max attempts, tránh dồn thêm tải vào DB/broker vốn đã bão hòa.
- **JobRepository:** dùng metadata để xác định execution/partition đã được ghi nhận; queue trong RAM **không phải** nguồn sự thật về tiến độ.
- **Restart đúng JobInstance:** không tạo JobParameters mới chỉ để vượt lỗi JobExecutionAlreadyRunning hoặc trạng thái FAILED; phải kiểm tra trạng thái persisted, checkpoint và worker cũ có còn chạy không.
- **Idempotent writer:** khi message/chunk bị redeliver hoặc partition chạy lại sau lỗi, phải tránh ghi trùng side effect. Dùng khóa nghiệp vụ, UPSERT hoặc deduplication theo đặc tính hệ thống.
- **Broker confirmation:** một lần publish được ứng dụng gọi không đồng nghĩa chắc chắn message đã được broker lưu bền vững. Kiểm tra confirm/ack/reply theo transport, cùng khả năng xử lý race khi đã commit business DB nhưng reply mất.
- **Shutdown/drain:** trước rolling deployment, đo in-flight và queue backlog, tránh dừng hàng loạt worker mà không có kế hoạch replay/restart. Nếu dùng queue trong RAM, task đang chờ có thể biến mất khi JVM chết.

**Đặc biệt nguy hiểm:** policy tự động **DiscardPolicy/DiscardOldestPolicy** có thể âm thầm bỏ task. Trong một batch job cần bảo đảm tính đúng đắn, chúng chỉ có thể được cân nhắc nếu ứng dụng có semantics bù đắp và kiểm chứng cực kỳ rõ; mặc định không dùng để che dấu overload.

## 15. Các giải pháp sai thường gặp

| Cách chữa sai | Vì sao không giải quyết gốc rễ? | Thay bằng |
|---|---|---|
| Tăng queue từ 1.000 lên 100.000 | Chỉ cho phép backlog lớn hơn, tăng latency và memory | Tính backlog budget, điều tiết producer |
| Tăng maxPoolSize nhưng giữ queue khổng lồ | Worker vẫn có thể chỉ quanh core | Đo pool/queue thật và thử bounded queue |
| Tăng worker liên tục khi DB đã lock hoặc hết connection | Tạo thêm waiting transactions và retry | Giảm concurrency, đo DB lock/acquisition time |
| Đặt queue = 0 mà không xử lý overload | Dễ phát sinh nhiều rejection khi burst | Chọn policy, admission limit và test |
| Nuốt RejectedExecutionException | Có nguy cơ mất công việc mà job vẫn báo thành công | Báo lỗi có kiểm soát, xác định retry/restart owner |
| Dùng DiscardPolicy để giữ hệ thống "êm" | Có thể bỏ task không được đối soát | Bảo toàn dữ liệu và cảnh báo khi vượt tải |
| Chỉ đo số job COMPLETED | Không thấy queue wait, GC và backlog đang phình | Theo dõi throughput, p95/p99, depth, heap và retry |
| Coi queue broker là chỗ lưu vô hạn | Đầy disk/quota, retention quá lâu hoặc replay phức tạp | Policy retention/overflow, DLQ và backpressure |
| Đồng nhất queue executor với số item trong chunk | Đánh giá sai RAM và concurrency | Đo retained bytes và thực tế submit/chunk |

## 16. Bài tập thực hành

**Tình huống:** Một hệ thống import 5 triệu bản ghi có manager và 10 worker. Một executor ở manager đặt corePoolSize = 4, maxPoolSize = 24, queueCapacity = Integer.MAX_VALUE. Trong giờ chạy batch, dashboard báo queue dài 9.000 task, active threads chỉ khoảng 4, heap tăng đều, còn database có một ít tài nguyên dự phòng.

Hãy:

1. Giải thích vì sao executor chưa tăng đến maxPoolSize dù queue dài. Kiểm tra giả thuyết bằng runtime metrics và cơ chế điều phối của Spring Batch.
2. Tính backlog tăng thêm nếu producer nộp 180 task/giây, consumer hoàn tất 120 task/giây trong 2 phút.
3. Nếu sau burst producer còn 90 task/giây, consumer 120 task/giây, ước lượng thời gian drain phần backlog vừa tăng.
4. Đề xuất ma trận cấu hình queueCapacity = 0, 8, 16, 64 và một mức đủ lớn để đối chứng; giữ worker count và downstream quota cố định.
5. Nêu metric và giới hạn an toàn phải có trước khi chạy thử. Giải thích cách phân biệt retained heap do queue và memory leak trong reader/writer.
6. Thiết kế overload policy cho manager/worker và broker, có quy định ai retry, cách bảo đảm message/job không mất và giới hạn số lần thử.
7. Mô phỏng một worker crash sau khi business data đã commit nhưng trước khi manager nhận reply; trình bày cách đối soát và restart tránh ghi trùng.

**Gợi ý tính toán:** backlog tăng 60 × 120 = **7.200 task**. Khi producer giảm còn 90, consumer vẫn hoàn tất 120 task/giây, chỉ riêng 7.200 task mới tích lũy có thể mất khoảng **240 giây** để xả với tốc độ ròng 30 task/giây, nếu các giả định giữ đúng.

### Câu hỏi tự kiểm tra

- Tại sao một queue có capacity Integer.MAX_VALUE vẫn không phải bộ nhớ vô tận?
- Khi nào queue hữu hạn có thể tốt hơn so với mở thêm worker?
- Vì sao p99 queue wait và thời gian drain quan trọng đối với batch SLA?
- Nếu JDBC pending tăng cùng queue depth, nên kiểm tra những chỉ số nào trước khi tăng capacity?
- CallerRunsPolicy có thay thế admission control toàn hệ thống hay không?
- Điều gì xảy ra với Runnable còn chờ khi process crash? Vì sao checkpoint/idempotency quyết định khả năng khôi phục?

## 17. Checklist trước khi triển khai cấu hình mới

- [ ] Xác định **đúng executor** và các queue broker/consumer mà job đang dùng.
- [ ] Đo active workers, queue depth, queue wait, task completion, heap/GC và JDBC pending trên cùng trục thời gian.
- [ ] Chứng minh tải ổn định có λ thấp hơn năng lực μ ở mức concurrency mục tiêu.
- [ ] Chọn queue capacity theo ngân sách **burst, thời gian chờ và RAM**.
- [ ] Có overload policy rõ ràng; kiểm thử rejection/CallerRuns, timeout, shutdown và retry giới hạn.
- [ ] Không dùng cơ chế discard làm mất task hoặc dấu vết nghiệp vụ.
- [ ] Kiểm tra thread safety của reader/writer, checkpoint và giới hạn đồng thời thực tế.
- [ ] Với phân tán, cấu hình producer admission, broker quota/retention, consumer prefetch và worker concurrency.
- [ ] Có phép thử spike, soak, downstream slowdown và phục hồi tại tải đại diện.
- [ ] JobRepository, message ack/reply và writer idempotency bảo đảm restart/đối soát đúng.
- [ ] Đặt cảnh báo queue depth tăng kéo dài, queue wait vượt SLO, heap tăng, JDBC timeout và broker DLQ.

## 18. Ghi nhớ

**Dùng queue vô hạn là anti-pattern vì nó cho phép hệ thống nhận thêm công việc vượt khả năng xử lý và ngân sách tài nguyên.** Với ThreadPoolTaskExecutor, queue lớn còn có thể khiến maxPoolSize không được sử dụng trong thời gian dài. Giải pháp đúng là **đo tốc độ nộp/hoàn tất, đặt bounded queue phù hợp burst và latency budget, kiểm soát concurrency toàn pipeline và thiết kế backpressure có thể quan sát**. Trong Spring Batch, mọi quyết định xử lý quá tải phải đi cùng JobRepository, checkpoint, retry/restart và idempotency để bảo đảm tốc độ xử lý cao không đánh đổi bằng dữ liệu sai hoặc mất công việc.
