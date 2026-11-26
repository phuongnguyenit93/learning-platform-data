# Test resource exhaustion trong Spring Batch

## 1. Mục tiêu và bối cảnh

**Resource exhaustion** là tình huống một hoặc nhiều tài nguyên cần thiết cho batch job bị dùng hết hoặc tiến sát giới hạn: CPU, heap, thread, JDBC connection, bộ nhớ đệm, dung lượng đĩa, I/O, kết nối mạng hoặc năng lực của dịch vụ phụ thuộc. Trước khi thật sự cạn kiệt, hệ thống thường đã bước vào trạng thái **saturation** (bão hòa): hàng đợi dài hơn, thời gian chờ tăng và throughput không còn tăng khi bổ sung worker.

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, việc mở rộng Spring Batch bằng multi-threaded step, parallel steps, partitioning hoặc xử lý phân tán chỉ có ý nghĩa khi tổng tải nằm trong ngân sách tài nguyên thực tế. Bài kiểm thử này giúp nhận biết điểm bão hòa, thiết kế giới hạn đồng thời, đánh giá khả năng tự phục hồi và chứng minh dữ liệu vẫn đúng khi job bị thiếu tài nguyên.

Sau bài học, bạn có thể:

- Xây dựng phép thử gây áp lực lên từng tài nguyên trong môi trường kiểm thử cô lập.
- Phân biệt nút thắt CPU, heap/GC, connection pool, thread pool, database, disk và hệ thống bên ngoài qua số liệu.
- Đo mức suy giảm throughput, latency, tỷ lệ lỗi và chất lượng restart khi tăng độ đồng thời.
- Chọn giới hạn concurrency, queue, chunk, partition và cơ chế backpressure dựa trên bằng chứng.
- Định nghĩa điều kiện dừng và tiêu chí đạt để phép thử an toàn, tái lập được.

> **Phạm vi:** Kiểm thử tải có kiểm soát trên staging/test với dữ liệu tổng hợp hoặc dữ liệu đã được cho phép sử dụng. Không chủ động gây cạn tài nguyên trên hệ thống production dùng chung.

## 2. Resource exhaustion xuất hiện ở đâu?

Một job có thể đọc dữ liệu nhanh hơn khả năng ghi, sinh nhiều chunk đang xử lý hoặc khiến hàng chục partition cạnh tranh cùng một nguồn kết nối. Các dấu hiệu phổ biến:

| Tài nguyên | Cơ chế gây cạn kiệt | Tín hiệu cần đo | Hệ quả điển hình |
|---|---|---|---|
| CPU | Quá nhiều processor, serialization, compression hoặc thread tranh CPU | CPU utilization, load/runnable threads, throughput | CPU gần 100%, throughput chững, thời gian xử lý mỗi chunk tăng |
| Heap / GC | Chunk lớn, nhiều item đồng thời, queue tích lũy object, cache tăng vô hạn | Heap used/committed, old-gen, GC pause/time, OOM | GC dày, pause dài, OutOfMemoryError |
| Worker thread | Executor quá nhiều tác vụ hoặc queue không giới hạn | Active threads, queue depth, rejected task, thread dump | Task bị dồn, latency tăng, có thể không nhận thêm việc |
| JDBC connection | Số giao dịch đồng thời vượt giới hạn pool hoặc database | Active/idle/pending connections, acquisition latency, timeout | Chờ connection, timeout, rollback, job thất bại |
| Database | Query/transaction cùng tranh lock, CPU, IOPS hoặc connection phía DB | Lock wait, deadlock, slow query, DB CPU/IO, transaction duration | Ghi chậm, retry/rollback tăng, throughput giảm |
| Đĩa và file handle | File tạm, sort/spill, log quá nhiều, reader/writer mở tài nguyên không đóng | Disk free, IOPS, I/O wait, open files/handles | IOException, disk full, đọc/ghi bị chặn |
| Network, API, broker | Quá nhiều request, kết nối, message đang chờ ack hoặc rate limit | Request latency, timeout, 429/5xx, consumer lag, in-flight | Retry storm, backlog tăng, thông lượng giảm |

Hai lưu ý thường bị bỏ sót:

1. **Tài nguyên chia sẻ không chỉ nằm trong worker.** JobRepository, connection pool cho metadata, database nghiệp vụ, message broker và dịch vụ API đều có giới hạn. Nhiều Job chạy cùng lúc phải cộng dồn nhu cầu của chúng.
2. **Cạn kiệt có thể do tải tồn đọng, không phải tải đang xử lý.** Một queue không giới hạn có thể giấu hiện tượng quá tải trong nhiều phút rồi mới làm đầy heap hoặc kéo dài thời gian hoàn tất job.

Ví dụ: một job đọc 2 triệu bản ghi, chia 12 partition và mỗi worker xử lý nhiều chunk. Nếu tất cả partition cùng ghi vào database với pool chỉ có 8 connection, nhiều luồng sẽ chờ connection. Việc tăng từ 12 lên 24 partition có thể làm thời gian chờ và timeout tăng mà số bản ghi ghi thành công mỗi giây lại giảm.

## 3. Xác định ngân sách tài nguyên trước khi thử

Không có một con số thread hay chunk size tối ưu cho mọi workload. Trước mỗi phép thử, ghi rõ các giới hạn:

| Tham số | Ý nghĩa khi kiểm thử |
|---|---|
| Số job/step chạy đồng thời | Tổng số nguồn tạo tải trong một JVM và trên toàn cụm |
| Kích thước chunk | Số item có thể được giữ và xử lý trong một transaction/chunk |
| Số worker hoạt động thực tế | Phụ thuộc cấu hình executor, cơ chế giới hạn tác vụ của Step và trạng thái queue |
| Grid size / số partition | Mức chia nhỏ công việc; không đồng nghĩa luôn có bấy nhiêu worker chạy thực |
| Connection pool | Giới hạn connection của cả ứng dụng; cần dự phòng cho JobRepository và tác vụ khác nếu cùng pool |
| Bộ nhớ cho một item | Bao gồm object graph, dữ liệu tạm trong processor/writer và overhead của JVM |
| External rate limit / DB capacity | Trần năng lực của thành phần chậm nhất trong pipeline |

Với một workload đồng nhất, có thể dùng ước lượng **để thiết kế test**, không coi đó là giới hạn bộ nhớ chính xác:

~~~text
In-flight item memory (xấp xỉ)
  ≈ concurrent chunks × chunk size × average retained bytes per item

Total memory
  ≈ JVM baseline + in-flight item memory + queues/buffers/cache
    + memory của reader/writer/driver + GC overhead

Connection demand (xấp xỉ)
  ≈ số transaction/request DB thực sự đồng thời
    + connection dành cho metadata/health check/tác vụ khác
~~~

Ví dụ giả định: 8 chunk đồng thời, chunk size 500 và mỗi item cùng dữ liệu tạm chiếm trung bình 4 KiB tạo khoảng 15,6 MiB cho phần item đang giữ. Con số này **chưa** tính object retention, kết quả trung gian, JDBC buffer, queue, GC và các batch job khác. Vì vậy cần đo heap thật thay vì quyết định bằng phép nhân duy nhất.

Đối với JDBC, một thread có thể không giữ connection trong toàn bộ vòng đời, nhưng bước ghi đồng thời vẫn có thể đòi hỏi nhiều connection. Nếu nhiều datasource cùng tồn tại, đo từng pool và tổng năng lực của DB. Nếu worker phân tán theo nhiều JVM, nhân ngân sách pool theo số instance, đồng thời xem xét giới hạn connection toàn database.

**Nguyên tắc:** Chọn điểm khởi đầu thấp, sau đó tăng dần độ đồng thời trong khi đo cả ứng dụng và hệ thống phụ thuộc. Khi throughput gần như không cải thiện nhưng thời gian chờ hoặc lỗi tăng, đã có dấu hiệu đi qua vùng hiệu quả.

## 4. Thiết kế phép thử có thể tái lập

### 4.1. Chuẩn bị baseline

Tạo một bộ dữ liệu đại diện: item nhỏ/lớn, phân phối kích thước thực tế, số bản ghi đủ dài để JVM và database qua giai đoạn khởi động, đồng thời có các partition lệch tải nếu hệ thống thực có skew. Mỗi lần chạy phải dùng cùng dữ liệu đầu vào, cùng cấu hình hạ tầng và trạng thái DB tương đương. Dùng job instance/parameters và vùng output riêng để tránh đọc lại kết quả của lần thử trước.

Ghi lại phiên bản JDK, Spring Batch, cấu hình JVM heap, giới hạn CPU/memory container, cấu hình pool, chunk size, mức parallelism, số worker/instance, cấu hình DB, lưu lượng hệ thống khác và thời điểm đo. Chạy warm-up nếu phù hợp; lấy ít nhất vài lần lặp cho mỗi cấu hình để phân biệt biến động ngẫu nhiên với xu hướng thật.

Ở baseline, đo throughput bền vững (item/giây), thời gian hoàn thành, p95/p99 duration mỗi chunk hoặc mỗi lần ghi, mức dùng heap/GC, CPU, connection pending, queue depth và tỷ lệ lỗi. Kiểm tra số bản ghi đầu ra thực tế thay vì chỉ xem trạng thái COMPLETED.

### 4.2. Ma trận phép thử

| Kiểu thử | Cách thực hiện | Câu hỏi cần trả lời |
|---|---|---|
| Load ramp | Tăng 1 → 2 → 4 → 8 → 12 worker hoặc mức tương ứng với kiến trúc | Từ ngưỡng nào throughput không còn tăng tương xứng? |
| Stress | Tăng tải vượt mức dự kiến trong thời gian ngắn, có giới hạn an toàn | Tài nguyên nào bão hòa trước? Lỗi xuất hiện theo thứ tự nào? |
| Spike | Tăng đột ngột số partition/job hoặc lượng item, rồi hạ xuống | Queue có thoát backlog và phục hồi latency không? |
| Soak/endurance | Giữ tải cao nhưng hợp lệ trong nhiều chu kỳ job | Có memory leak, connection leak, tăng handle hoặc suy giảm throughput theo thời gian không? |
| Resource constraint | Giảm **có kiểm soát** CPU quota, heap, pool size hoặc băng thông I/O trên môi trường test | Hệ thống xử lý thiếu tài nguyên thế nào, có backpressure hay timeout có kiểm soát không? |
| Recovery/restart | Làm một lần thử thất bại ở điểm được kiểm soát, khôi phục tài nguyên và restart | Có ghi trùng, bỏ sót, checkpoint sai hoặc retry vô hạn không? |

Chỉ thay đổi **một nhóm biến chính** trong một đợt thử. Ví dụ để đánh giá JDBC pool, cố định số partition và chunk size, thử lần lượt pool size 4, 8, 12; sau đó mới đánh giá tương tác với concurrency. Việc tăng đồng thời cả pool, chunk, CPU và số worker sẽ khiến kết quả khó giải thích.

### 4.3. Guardrail và điểm dừng

Trước khi chạy, định nghĩa **ngưỡng dừng tự động** phù hợp môi trường: heap tiệm cận giới hạn cùng GC liên tục, tỷ lệ timeout vượt mức đã thỏa thuận, database latency ảnh hưởng tới hệ thống dùng chung, disk free xuống thấp hoặc queue tăng không kiểm soát. Đặt timeout cho phép thử, giới hạn số item/job, số lần retry và mức resource quota. Việc gây disk full hoặc cắt kết nối DB phải thực hiện trong tài nguyên test được cô lập.

Thu thập logs, metrics và trạng thái JobRepository ngay cả khi test thất bại; không xóa state trước khi phân tích restart.

## 5. Ví dụ cấu hình để kiểm soát áp lực

Đoạn sau minh họa cách cấu hình một **TaskExecutor có số thread và hàng đợi hữu hạn** cho multi-threaded step. API StepBuilder minh họa phong cách cấu hình Spring Batch 5.x; khi sử dụng phiên bản khác, đối chiếu API tương ứng.

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
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class ResourceTestBatchConfig {

    @Bean
    ThreadPoolTaskExecutor batchWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8); // Không để queue phát triển vô hạn
        executor.setThreadNamePrefix("batch-resource-test-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.CallerRunsPolicy()
        );
        return executor;
    }

    @Bean
    Step resourceTestStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<String> threadSafeReader,
            ItemProcessor<String, String> processor,
            ItemWriter<String> writer,
            @Qualifier("batchWorkerExecutor") TaskExecutor executor) {

        return new StepBuilder("resourceTestStep", jobRepository)
            .<String, String>chunk(200, transactionManager)
            .reader(threadSafeReader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(executor)
            .build();
    }
}
~~~

Giải thích các lựa chọn:

- **4 thread và queue 8** là mức khởi đầu giả định để quan sát hệ thống, không phải cấu hình tối ưu. Tăng dần từng mức trong test và đối chiếu với connection pool cùng CPU.
- **CallerRunsPolicy** làm bên nộp task phải thực thi task khi executor đã đầy, có thể tạo áp lực ngược (backpressure). Hãy xác minh hành vi thực tế của Step khi thay đổi rejection policy; nó không thay thế cơ chế kiểm soát tổng lưu lượng của toàn hệ thống.
- **Chunk 200** giới hạn lượng item mỗi chunk và phạm vi transaction. Chunk lớn có thể giảm overhead commit nhưng làm tăng lượng dữ liệu lưu trong bộ nhớ và chi phí rollback.
- **Reader và writer phải an toàn khi gọi đồng thời**. Nhiều ItemReader hoặc ItemWriter có state và không mặc nhiên thread-safe. Với reader stateful, cân nhắc partitioning với reader riêng cho từng StepExecution hoặc giải pháp đồng bộ phù hợp; không giả định rằng thêm @StepScope tự động tạo một reader cho mỗi thread.
- **Pool size không tự chứng minh số chunk đồng thời.** Một số phiên bản/cấu hình Spring Batch còn có giới hạn concurrency ở tầng Step (ví dụ cơ chế throttle trước đây). Hãy đo active threads, chunk in-flight và rà soát API của phiên bản chạy thật, đặc biệt khi muốn thử trên 4 worker.

Trong parallel steps hoặc partitioning, tổng tải là tổng các worker đang hoạt động, không chỉ số thread của executor trong một Step. Với remote partitioning/remote chunking, cũng phải tính số instance, prefetch, consumer concurrency và connection từ mỗi worker. Một queue hữu hạn ở một process không bảo đảm toàn cụm đã có backpressure.

## 6. Thu thập và đọc số liệu

Tối thiểu nên có cùng mốc thời gian cho ba tầng:

| Tầng | Metric / quan sát | Ý nghĩa |
|---|---|---|
| Spring Batch | Job/Step start-end, readCount, writeCount, filterCount, skipCount, commitCount, rollbackCount, exit status | Job tiến triển thế nào, có commit/rollback/skip bất thường không |
| JVM/ứng dụng | CPU, live threads, heap/old-gen, GC time/pause, executor active, queue depth, rejection, retry count | Có bão hòa nội bộ, giữ object lâu hoặc xếp hàng quá mức không |
| Hệ thống phụ thuộc | JDBC active/idle/pending và acquisition timeout, DB CPU/locks/IO, disk, network, API 429/5xx, broker lag | Giới hạn nằm ngoài JVM hay bên trong JVM |

Có thể xuất metric qua Micrometer/Actuator, JFR, GC logs, datasource pool metrics và dashboard hệ thống tùy stack. Tên metric cụ thể phụ thuộc thư viện và phiên bản; đừng xây dashboard chỉ dựa trên một tên có thể thay đổi. Với ThreadPoolTaskExecutor, kiểm tra trực tiếp **activeCount**, **poolSize** và **queue.size** của executor đang chạy cũng rất hữu ích.

Các chỉ số dẫn xuất:

~~~text
Throughput (item/s) = số item ghi thành công / thời gian đo (giây)
Error rate           = số thao tác lỗi / tổng số thao tác thử
CPU efficiency       = item ghi thành công / CPU-second tiêu thụ
Backlog trend        = lượng đang chờ cuối khoảng - đầu khoảng
Restart recovery     = thời gian từ lúc có lại tài nguyên đến khi job hoàn tất đúng dữ liệu
~~~

Đếm **item ghi thành công** theo kết quả được commit và trạng thái đầu ra có thể đối soát. Một số processor lọc item, có retry và rollback; vì vậy không lấy readCount trừ writeCount rồi coi phần chênh lệch là mất dữ liệu. Với hệ thống có skip có chủ đích, công thức đối soát phải tuân theo quy tắc nghiệp vụ.

Đọc các chuỗi metric **theo thời gian**, không chỉ snapshot:

- CPU cao ổn định, runnable thread nhiều, connection không phải nút thắt: nghiêng về CPU saturation hoặc tranh CPU.
- Heap dạng răng cưa sau GC nhưng mức đáy tiếp tục tăng, full GC dày hơn: xem lại object retention, buffer, cache và queue.
- JDBC pending tăng, active luôn sát max, acquisition time tăng: pool hoặc database đang quá tải. Tăng pool bừa bãi có thể đẩy nút thắt sang database.
- Queue tăng liên tục trong khi throughput đứng yên: producer nhanh hơn consumer; cần giảm đầu vào hoặc tăng năng lực xử lý thật.
- Rollback/retry tăng cùng với lock wait, query latency: có thể xảy ra contention ở database và retry storm.

Một log có dạng "connection timeout" cho biết thao tác lấy connection thất bại, nhưng **chưa đủ** kết luận chỉ cần tăng maximumPoolSize. Cần phân biệt pool bị giới hạn, transaction giữ connection quá lâu, lock contention hoặc chính database không phục vụ nổi tải.

## 7. Phân tích kết quả minh họa

Giả sử chạy cùng bộ dữ liệu và chunk size 200, chỉ tăng số worker thực tế. Bảng sau là **số liệu giả định để luyện cách suy luận**, không phải benchmark của Spring Batch:

| Worker hoạt động | Throughput (item/s) | p95 chunk (ms) | JDBC pending trung bình | Rollback |
|---:|---:|---:|---:|---:|
| 2 | 1.800 | 240 | 0 | 0 |
| 4 | 3.300 | 260 | 0 | 0 |
| 8 | 4.100 | 520 | 3 | 2 |
| 12 | 3.700 | 1.400 | 9 | 28 |

Từ 2 lên 4 worker, throughput tăng mạnh. Từ 4 lên 8, mức tăng giảm và p95 gần gấp đôi. Từ 8 lên 12, throughput **giảm** dù worker nhiều hơn; đồng thời JDBC pending và rollback tăng. Đây là tín hiệu vùng bão hòa hoặc vượt tải ở đường truy cập dữ liệu. Bước tiếp theo là kiểm tra thời gian giữ transaction, pool max, DB locks/IO/CPU và các workload đang chia sẻ DB.

Không nên kết luận ngay "4 là con số tốt nhất" chỉ từ bảng này: còn phải so sánh mục tiêu SLO, độ ổn định qua nhiều lần lặp, tài nguyên dự phòng và tác động lên các job khác. Nếu tăng pool làm pending giảm nhưng DB lock wait vẫn tăng, tối ưu query/index, thời gian transaction hoặc phân vùng ghi có thể hiệu quả hơn tăng số kết nối.

### Một quy trình chẩn đoán ngắn

1. **Giữ nguyên workload**, đối chiếu thời gian chạy và throughput với baseline.
2. **Xác định metric tăng trước**: CPU, heap/GC, executor queue, JDBC pending, DB lock hay network timeout.
3. **Kiểm tra tài nguyên được chia sẻ** giữa nhiều step/job/instance; xem có hoạt động ngoài test đang chiếm quota không.
4. **Thay đổi một giới hạn** (worker, chunk, pool, prefetch, rate limit) và chạy lại cùng dữ liệu.
5. **Đối soát đầu ra và restart**, kể cả khi throughput đã cải thiện.

## 8. Kiểm tra hành vi khi cạn kiệt và khả năng restart

Resource exhaustion còn là bài kiểm thử tính đúng đắn, không chỉ đo tốc độ. Khi connection pool hết chỗ, ứng dụng có thể nhận timeout; khi heap thực sự hết, tiến trình có thể dừng trước khi ghi đầy đủ trạng thái checkpoint. Với chunk-oriented step, commit và trạng thái ExecutionContext có vai trò quan trọng trong việc tiếp tục xử lý, nhưng tính restart được còn phụ thuộc reader/writer và transaction boundary.

Kịch bản kiểm thử phục hồi:

1. Chạy một job có **đầu vào cố định** và khóa định danh output rõ ràng.
2. Khi job đã commit một phần, tạo hạn chế tài nguyên có kiểm soát trong môi trường test (ví dụ giảm pool/CPU quota hoặc ngắt dependency test). Ghi lại thời điểm và trạng thái StepExecution.
3. Xác minh job dừng/lỗi theo kỳ vọng, timeout và retry có giới hạn; thu thập last committed progress, lỗi và số lần rollback.
4. Khôi phục dependency, restart theo cơ chế phù hợp của Spring Batch. Đảm bảo job instance/parameters không vô tình tạo một lần xử lý độc lập làm nhiễu kết quả.
5. Đối soát số lượng, khóa duy nhất, checksum/tổng giá trị nghiệp vụ và các side effect. Quan sát xem queue, thread, connection, heap có trở về mức nền sau khi job kết thúc không.

Đặc biệt chú ý:

- **Idempotency:** Chunk có thể được xử lý lại sau thất bại hoặc restart; thao tác ghi nên có khóa nghiệp vụ/UPSERT/deduplication hoặc cơ chế tương đương để tránh ghi trùng.
- **Retry:** Chỉ retry lỗi tạm thời và có max-attempt/backoff/jitter hợp lý. Retry liên tục khi DB đã bão hòa làm tình hình xấu hơn. Lỗi như cấu hình sai, dữ liệu không hợp lệ cần phân loại riêng.
- **Timeout:** Connection acquisition, truy vấn, I/O ngoài và job/test timeout cần có chính sách nhất quán. Timeout quá dài khiến thread bị giữ; quá ngắn gây lỗi giả.
- **Skip:** Không dùng skip không giới hạn để làm job chuyển sang COMPLETED trong lúc hệ thống đang thiếu tài nguyên. Skip phải dựa trên quy tắc dữ liệu và được kiểm toán.
- **Leak:** Sau nhiều lần job thành công và thất bại, open connections, threads, file handles và mức heap sau GC nên trở về vùng ổn định.

Nếu mất toàn bộ tiến trình do OOM, logs cuối cùng và metadata có thể không được flush đúng lúc. Khi đánh giá khả năng restart, cần xét cả trường hợp bị kill/terminate có kiểm soát và xác minh state thực sự được commit, thay vì giả định một lỗi JVM luôn có exit status đẹp trong JobRepository.

## 9. Đặt tiêu chí PASS/FAIL cho phép thử

Tiêu chí nên được chốt trước khi chạy theo SLO của hệ thống. Ví dụ **chỉ để minh họa**:

| Hạng mục | Tiêu chí đạt ví dụ |
|---|---|
| Throughput | Ở tải mục tiêu duy trì ít nhất 3.000 item/giây trong cửa sổ đo ổn định |
| Latency | p95 xử lý chunk dưới 800 ms trong tải mục tiêu |
| Ổn định tài nguyên | Không có OOM, tăng heap sau GC kéo dài hoặc queue tăng liên tục |
| Dependency | Không có connection acquisition timeout; DB lock wait không vượt ngưỡng đã thống nhất |
| Tính đúng đắn | Đầu ra được đối soát đúng; không mất hoặc nhân đôi side effect nghiệp vụ |
| Khả năng phục hồi | Sau khi bỏ hạn chế tài nguyên, restart hoàn tất trong thời gian mục tiêu và không tạo bản ghi trùng |
| Chịu tải quá mức | Khi vượt tải, áp lực được giới hạn, lỗi được quan sát rõ, hệ thống trở về trạng thái bình thường sau khi giảm tải |

Với stress test, **không nhất thiết đòi hỏi zero error ở mọi mức tải**. Điều cần chứng minh là ngưỡng bão hòa được định lượng, lỗi có giới hạn, hệ thống không sụp đổ dây chuyền và có thể phục hồi. Nếu tải vượt quota làm job fail đúng với timeout và cảnh báo rõ ràng, đó có thể là hành vi mong đợi của test.

Mỗi báo cáo test nên ghi: workload và dữ liệu đầu vào; topology và version; worker/chunk/partition/pool/quota; đồ thị throughput, p95/p99, heap/GC, CPU, queue/JDBC; thời điểm xuất hiện bão hòa; lỗi đầu tiên và chuỗi lỗi tiếp theo; kết quả đối soát/restart; thay đổi cấu hình được đề xuất và phép thử cần chạy lại.

## 10. Bài thực hành

**Tình huống:** Một job import 5 triệu bản ghi đang chạy với 4 partition, chunk size 250, pool JDBC tối đa 10 connection. Nhóm muốn tăng lên 16 partition để rút ngắn thời gian chạy, trong khi ứng dụng còn cần connection cho metadata và các tác vụ khác.

Hãy thực hiện trên môi trường test:

1. Đo baseline ở 4 partition; ghi throughput, p95 chunk, heap, CPU, active/pending JDBC connections, rollback và số record đích.
2. Thử 8 rồi 16 partition, cố định chunk size và workload. Đo **số worker đang hoạt động thực tế**, không dùng grid size để suy ra concurrency.
3. Lặp lại phép thử với giới hạn concurrency phù hợp với pool và DB, theo dõi queue cùng thời gian chờ connection.
4. Tạo một lần lỗi dependency có kiểm soát; sau khi khôi phục, restart job và đối soát output với baseline.
5. Đề xuất cấu hình tối đa có dự phòng, nêu bằng chứng cụ thể vì sao nó phù hợp hơn các cấu hình còn lại.

**Câu hỏi tự kiểm tra:** Nếu tăng worker từ 8 lên 16 làm CPU chỉ tăng nhẹ nhưng JDBC pending, rollback và p99 tăng mạnh, bạn sẽ ưu tiên quan sát chỉ số nào ở database trước khi tăng connection pool? Vì sao? Nếu heap sau mỗi lần GC đều cao hơn lần trước trong soak test, bạn sẽ kiểm tra object retention ở queue, cache và reader/writer bằng cách nào?

## 11. Ghi nhớ

Kiểm thử resource exhaustion phải xác định được **tài nguyên giới hạn đầu tiên**, **ngưỡng bắt đầu suy giảm**, **cách hệ thống phản ứng khi quá tải** và **khả năng hoàn tất đúng dữ liệu sau phục hồi**. Tăng concurrency có thể làm batch nhanh hơn đến một điểm; vượt điểm đó, queue, tranh chấp và retry sẽ làm toàn hệ thống chậm đi. Quyết định scaling nên dựa trên chuỗi metric và phép thử tái lập được, đồng thời giữ đủ tài nguyên dự phòng cho JobRepository và các thành phần chia sẻ.
