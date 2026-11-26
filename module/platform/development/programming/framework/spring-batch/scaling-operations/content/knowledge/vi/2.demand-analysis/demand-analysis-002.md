# Phân biệt CPU-bound và IO-bound

## 1. Phân tích nhu cầu trước khi mở rộng Spring Batch

Một Spring Batch job xử lý hai triệu giao dịch trong bốn giờ không nhất thiết sẽ chạy nhanh gấp bốn lần khi tăng từ một lên bốn luồng. Nếu các luồng dành phần lớn thời gian chờ database, tăng số luồng có thể giúp tận dụng khoảng chờ. Nếu CPU đã bão hòa, tăng số luồng vượt tài nguyên thực chỉ gây thêm chuyển ngữ cảnh và cạnh tranh. Nếu database bị khóa hoặc pool kết nối cạn, cả hai cách tăng luồng đều có thể khiến hệ thống chậm hơn.

Trong chương **Phân tích nhu cầu** của module **SPRING_BATCH_SCALING_OPERATIONS**, việc **phân biệt CPU-bound và IO-bound** là bước đầu để chọn đúng multi-threaded step, parallel steps, partitioning hoặc mô hình xử lý phân tán. Mục tiêu là đo nút thắt, hiểu tác động lên thread safety, retry/restart và vận hành, rồi lựa chọn kiến trúc dựa trên CPU, bộ nhớ, I/O, kết nối và khả năng phục hồi thực tế.

Hai thuật ngữ mô tả **tài nguyên đang giới hạn throughput**, không phải nhãn cố định của một ứng dụng:

- **CPU-bound**: phần thời gian quan trọng của workload dùng CPU để tính toán, chuyển đổi dữ liệu, mã hóa, nén, parse, validate phức tạp. Khi tăng năng lực CPU khả dụng hoặc giảm lượng tính toán, throughput có thể cải thiện rõ rệt.
- **IO-bound**: workload thường phải chờ thao tác I/O như đọc file, truy vấn database, ghi kết quả, gọi API hoặc truyền dữ liệu qua mạng. CPU có thể nhàn rỗi trong lúc luồng đang chờ.
- **Mixed workload**: một pipeline có nhiều giai đoạn khác nhau. Reader có thể đợi database, processor chạy CPU và writer đợi commit. Nút thắt có thể chuyển vị trí khi thay đổi concurrency hoặc tối ưu một giai đoạn.

**Điểm cốt lõi:** phân loại bằng **đo đạc trong điều kiện tải đại diện**, không chỉ nhìn tên `ItemReader` hay `ItemProcessor`.

## 2. Dấu hiệu nhận biết CPU-bound và IO-bound

| Góc nhìn | CPU-bound thường gặp | IO-bound thường gặp | Cần lưu ý |
|---|---|---|---|
| CPU sử dụng | Gần giới hạn core/quota trong thời gian dài | Còn dư CPU trong khi job chậm | CPU thấp cũng có thể do lock, pause hoặc một luồng tuần tự |
| Trạng thái luồng | Nhiều luồng `RUNNABLE` thực sự dùng CPU | Nhiều luồng chờ socket, disk, database, pool | `RUNNABLE` trong JVM không tự chứng minh đang tính toán |
| Profiling | Nhiều CPU samples trong parser, thuật toán, serialization | Nhiều thời gian wall-clock ở JDBC, network, file I/O | Profile CPU và wall-clock phải được đọc riêng |
| Khi tăng luồng | Tăng đến gần số core có ích rồi bão hòa | Có thể tiếp tục tăng đến giới hạn I/O hoặc dependency | Connection pool, rate limit và lock có thể chặn tăng tốc |
| Khi tăng CPU quota/core | Có thể cải thiện nếu thực sự đang thiếu CPU | Thường ít tác dụng khi I/O là nút thắt | GC và CPU throttling làm chẩn đoán khó hơn |
| Khi cải thiện truy vấn/batch write | Ít tác dụng nếu thời gian SQL vốn rất nhỏ | Có thể cải thiện mạnh | Phải đo bằng query timing, execution plan |
| Rủi ro khi scaling | GC, bộ nhớ, context switching | DB saturation, connection timeout, lock và overload API | Hai nhóm rủi ro có thể xuất hiện cùng lúc |

Ví dụ về **CPU-bound**:

~~~java
public class RiskScoringProcessor
        implements ItemProcessor<Order, ScoredOrder> {

    @Override
    public ScoredOrder process(Order order) {
        // Giả định engine chấm điểm thực hiện lượng lớn tính toán CPU,
        // không gọi dịch vụ từ xa hoặc database trong phép tính này.
        double score = riskEngine.calculate(order);
        return new ScoredOrder(order.id(), score);
    }
}
~~~

Ở ví dụ này, `riskEngine` chỉ là dependency minh họa. Việc nhiều vòng tính toán, cấp phát và chuyển đổi khiến `process(...)` chiếm phần lớn CPU time là dấu hiệu cần kiểm chứng bằng profiler.

Ví dụ về **IO-bound**:

~~~java
public class CustomerLookupProcessor
        implements ItemProcessor<Order, EnrichedOrder> {

    @Override
    public EnrichedOrder process(Order order) {
        // Phần lớn wall time có thể nằm ở lời gọi remote.
        Customer customer = customerClient.fetch(order.customerId());
        return new EnrichedOrder(order, customer);
    }
}
~~~

Ở đây `customerClient` là client nghiệp vụ minh họa; nếu sử dụng HTTP đồng bộ, mỗi lời gọi có thể chặn một worker thread trong khi chờ network. Tuy nhiên, nếu remote service rate-limit hoặc chậm do chính nó thiếu CPU, tăng luồng Spring Batch chưa chắc tạo thêm throughput.

## 3. Nhìn toàn pipeline, không đánh giá bằng một bước

Với chunk-oriented step, một chunk đi qua quá trình đọc, xử lý, ghi và commit. Mỗi công đoạn có một kiểu chờ/chi phí khác nhau.

~~~mermaid
flowchart LR
    A["Input: file / DB / API"] --> B["ItemReader"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter"]
    D --> E["Transaction commit"]
    B -.-> F["DB / file / network wait"]
    C -.-> G["CPU / allocation / GC"]
    D -.-> H["DB / downstream I/O"]
    E -.-> I["WAL / lock / fsync"]
~~~

Ví dụ một luồng đọc 1.000 bản ghi, xử lý 1.000 bản ghi và ghi thành từng chunk:

| Công đoạn | Wall time đo được | Dấu hiệu |
|---|---:|---|
| Đọc dữ liệu | 2,5 giây | Chờ truy vấn hoặc socket |
| Xử lý | 8,0 giây | CPU bận tính toán |
| Ghi + commit | 4,0 giây | Chờ I/O và transaction |
| Phần khác | 0,5 giây | Mở reader, vòng lặp framework, scheduling |
| **Tổng** | **15,0 giây** | Workload pha trộn |

Các số trên là **minh họa cho một lần đo tuần tự**, không phải tỉ lệ chuẩn của Spring Batch. Nếu đa số thời gian ở processor, bắt đầu từ profiling CPU; nếu đa số thời gian ở JDBC, cần phân tích SQL và database. Sau khi tăng parallelism, các khoảng chờ có thể chồng lấp và tổng thời gian không còn đơn giản bằng tổng thời gian từng công đoạn.

Với multi-threaded step, reader/processor/writer có thể chạy qua các worker threads; với partitioning, mỗi partition có `StepExecution` riêng; với parallel steps, các step khác nhau chạy trong flow độc lập. **Mức song song nào cũng phải chịu giới hạn tài nguyên chung**.

## 4. Đo nút thắt bằng số liệu có thể đối chiếu

### 4.1. Các chỉ số cơ bản

Đặt một đường cơ sở với **một worker**, sau đó đo trước khi tăng concurrency.

| Nhóm | Chỉ số nên ghi | Trả lời câu hỏi gì? |
|---|---|---|
| Kết quả Batch | `readCount`, `writeCount`, `filterCount`, `skipCount`, `rollbackCount` | Bao nhiêu item đã đi qua pipeline, bị lọc, skip hoặc rollback? |
| Thời gian | `JobExecution`/`StepExecution` duration, thời gian mỗi chunk, p95/p99 khi cần | Công đoạn nào làm job chậm? |
| Năng suất | Items/giây, bytes/giây, chunk/giây | Thêm worker có tạo thêm kết quả đúng không? |
| CPU | Process CPU, core utilization, CPU throttling, GC CPU/time | Job có thiếu năng lực tính toán không? |
| Memory | Heap, allocation rate, GC pause, RSS, OOM | Parallelism có làm tăng áp lực cấp phát? |
| Executor | Active threads, queue length, reject, thời gian chờ task | Worker có thiếu luồng hoặc đang dồn hàng? |
| Database | Query latency, DB CPU, wait events, locks, connection pool active/idle/wait | Job có đang đợi tài nguyên dữ liệu? |
| Network / disk | RTT, bytes, IOPS, throughput, throttling | Kênh I/O nào đang giới hạn? |

**Throughput** thường được tính như sau:

\[
\text{write throughput} = \frac{\text{số item ghi thành công trong khoảng đo}}{\text{số giây của khoảng đo}}
\]

Với job có `ItemProcessor` lọc item (trả `null`) hoặc cấu hình skip, số item đọc **không bằng** số item ghi. Nếu một writer ghi nhiều record cho mỗi item hoặc ghi vào các hệ thống khác nhau, cần định nghĩa đơn vị throughput phù hợp nghiệp vụ.

CPU utilization nên hiểu theo **CPU quota/core khả dụng của tiến trình/container**, thay vì chỉ theo tổng CPU vật lý của host. Ví dụ một container bị giới hạn hai vCPU có thể đã bão hòa dù dashboard của host 32-core báo CPU rất thấp.

### 4.2. Phân biệt CPU time và wall-clock time

- **Wall-clock time** là thời gian từ lúc bắt đầu đến lúc kết thúc một thao tác. Nó bao gồm tính toán, chờ I/O, lock, scheduling và các loại pause.
- **CPU time** là lượng thời gian CPU thực sự dùng để chạy mã của luồng/tiến trình trong khoảng đó. Nó không bao gồm phần lớn thời gian block chờ I/O.

Ví dụ thao tác mất 100 ms wall-clock nhưng chỉ dùng 4 ms CPU thì khả năng lớn là đang chờ tài nguyên hoặc bị trì hoãn. Ngược lại, thao tác mất 100 ms wall-clock và tiêu thụ gần 100 ms CPU trên một luồng có thể là CPU-heavy. Không kết luận từ một mẫu duy nhất: hãy đo nhiều lần, loại trừ warmup, GC, lock contention và nghẽn bên ngoài.

**Công cụ quan sát thường dùng:**

- **Java Flight Recorder (JFR)** hoặc profiler hỗ trợ CPU sampling, allocation và event chờ: chỉ ra call stack tốn CPU, GC và blocking behavior.
- **Thread dump** lấy theo nhiều thời điểm: giúp phát hiện luồng đợi JDBC/socket, lock hoặc thread pool. Một snapshot đơn lẻ ít giá trị để khẳng định nút thắt.
- **Micrometer / Spring Boot Actuator** khi đã tích hợp: theo dõi CPU, JVM, executor, connection pool và những metric Batch phù hợp với phiên bản/cấu hình thực tế.
- **Database monitoring**: execution plan, slow query, lock wait, active connections và thống kê I/O; các chỉ số này thường giải thích vì sao CPU của ứng dụng còn rảnh.
- **JobRepository**: đối chiếu `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` hoặc `JobExplorer` với log chứa `jobExecutionId`/`stepExecutionId` để biết đoạn nào chạy lâu, lỗi hoặc restart.

Đừng gắn `jobExecutionId` hay mã item làm **label/tag cho metrics** vì cardinality tăng vô hạn. Đặt các ID riêng trong log/tracing để truy vết; chỉ dùng metric tags có tập giá trị có kiểm soát.

### 4.3. Đo thời gian chunk bằng listener

Một `ChunkListener` có thể cung cấp đường cơ sở về wall time mà không cần thay đổi logic nghiệp vụ. Ví dụ Java 17, Spring Batch 5.x:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class ChunkTimingListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkTimingListener.class);

    // Một giá trị bắt đầu cho mỗi thread chạy chunk.
    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    @Override
    public void beforeChunk(ChunkContext context) {
        startedAt.set(System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        try {
            Long start = startedAt.get();
            if (start == null) {
                return;
            }

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);

            StepExecution step = context
                    .getStepContext()
                    .getStepExecution();

            log.debug(
                    "stepExecutionId={} stepName={} chunkWallMs={} " +
                    "readCount={} writeCount={} rollbackCount={}",
                    step.getId(),
                    step.getStepName(),
                    elapsedMs,
                    step.getReadCount(),
                    step.getWriteCount(),
                    step.getRollbackCount());
        } finally {
            startedAt.remove();
        }
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        startedAt.remove();
    }
}
~~~

Gắn listener vào một chunk step đang có:

~~~java
return new StepBuilder("ordersStep", jobRepository)
        .<Order, Order>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(chunkTimingListener)
        .build();
~~~

`Order`, `reader`, `processor`, `writer`, `transactionManager` và `chunkTimingListener` ở đoạn thứ hai là các dependency/bean nghiệp vụ cần có trước. `ThreadLocal` tránh trộn thời gian giữa các worker chạy song song và được dọn trong callback kết thúc/lỗi.

**Giới hạn của phép đo:** đây là **wall time toàn chunk**, không đo riêng CPU time, reader hay writer. `readCount`/`writeCount` là bộ đếm tích lũy tại thời điểm callback, không phải số item của riêng chunk vừa kết thúc. Log mỗi chunk ở `DEBUG` chỉ nên bật có kiểm soát; trong production có thể lấy mẫu hoặc tổng hợp histogram. Để tìm chính xác vị trí chờ, kết hợp profiling, JDBC metrics và phép đo độc lập cho từng giai đoạn.

## 5. Thí nghiệm phân loại bằng cách tăng concurrency

Giữ nguyên dataset, schema/index, cấu hình DB, loại VM/container, kích thước chunk và điều kiện tải bên ngoài. Sau đó chạy cùng logic với một, hai, bốn worker; ít nhất lặp nhiều lần và ghi trung vị/tốc độ dao động để tránh kết luận từ warmup hoặc noisy neighbor.

**Kịch bản A — thiên về CPU:**

| Worker đồng thời | Throughput giả định | CPU của container bốn vCPU | Nhận định |
|---:|---:|---:|---|
| 1 | 100 item/s | Khoảng 1 vCPU bận | Một luồng đang giới hạn năng lực tính toán |
| 2 | 195 item/s | Khoảng 2 vCPU bận | Tăng gần tuyến tính |
| 4 | 365 item/s | Gần 4 vCPU bận | Có lợi nhưng đã gần giới hạn |
| 8 | 370 item/s | Vẫn gần 4 vCPU, nhiều contention | Tăng luồng không còn lợi ích đáng kể |

**Kịch bản B — thiên về chờ database:**

| Worker đồng thời | Throughput giả định | CPU ứng dụng | DB connection wait |
|---:|---:|---|---|
| 1 | 100 item/s | Thấp | Thấp |
| 2 | 180 item/s | Còn dư | Thấp |
| 4 | 260 item/s | Còn dư | Bắt đầu tăng |
| 8 | 240 item/s | Còn dư | Cao, có timeout/lock |

Đây là **các số minh họa** để nhận biết dạng xu hướng, không phải benchmark hay ngưỡng chuẩn. Kịch bản B không nên kết luận “tăng DB pool là đủ”: truy vấn có thể đang lock lẫn nhau, database có thể hết CPU/I/O hoặc hệ thống downstream có giới hạn request.

Một quy trình thực nghiệm phù hợp:

1. **Chốt mục tiêu:** ví dụ 2 triệu item trong 30 phút, độ đúng dữ liệu tuyệt đối, không vượt giới hạn 20 kết nối DB của job.
2. **Đo baseline:** thử một worker, thu throughput, wall time, CPU, GC, read/write/skip, SQL latency, connection wait.
3. **Tìm thao tác chiếm thời gian:** dùng profiling + log và số liệu DB để phân biệt tính toán với chờ.
4. **Đổi một biến mỗi lần:** tăng worker hoặc tối ưu SQL hoặc đổi chunk size, không thay tất cả cùng lúc.
5. **Đo lại và so sánh:** theo dõi throughput, p95, phân bố thời gian partition, lỗi, lock, memory và tài nguyên downstream.
6. **Kiểm tra failure/restart:** inject lỗi ở giữa chunk hoặc partition; đảm bảo không trùng/bỏ sót và xác định chi phí recovery.
7. **Chọn cấu hình vận hành:** giữ mức concurrency có hiệu quả ổn định và dư địa tài nguyên, không lấy giá trị nhanh nhất trong một phép thử ngắn.

## 6. Mô hình tính toán và giới hạn tăng tốc

### 6.1. Amdahl’s Law: không phải mọi phần đều song song hóa được

Nếu `s` là tỉ lệ thời gian bắt buộc tuần tự và `N` là số worker xử lý phần còn lại theo giả định lý tưởng:

\[
S(N) = \frac{1}{s + \frac{1-s}{N}}
\]

Ví dụ 20% thời gian của chương trình là tuần tự (`s = 0{,}2`), với bốn worker:

\[
S(4) = \frac{1}{0{,}2 + 0{,}8/4} = 2{,}5
\]

Tức là theo mô hình đơn giản, tốc độ tối đa chỉ khoảng **2,5 lần**, không phải bốn lần. Đây là giới hạn lý tưởng **không tính overhead**, cache miss, DB contention, lock hay giao tiếp mạng. Với Spring Batch, throughput còn bị chặn bởi reader, writer, JobRepository, transaction và nguồn dữ liệu chung.

### 6.2. Little’s Law: liên hệ số việc đang xử lý với độ trễ

Ở trạng thái ổn định, một hệ thống có thể được ước lượng theo:

\[
L = \lambda W
\]

Trong đó `L` là số request/item trung bình đang ở trong hệ thống, `\lambda` là tốc độ hoàn tất (item/giây), `W` là thời gian trung bình mỗi item ở trong hệ thống (giây). Nếu riêng một lời gọi I/O phải giữ 20 ms và muốn hỗ trợ 400 lời gọi/giây ở trạng thái ổn định, số lời gọi I/O đang chờ/xử lý trung bình tối thiểu khoảng `400 × 0,020 = 8`.

Phép tính **không tự suy ra cần đúng tám worker Spring Batch**: mỗi worker còn có CPU, chunk buffering, commit và các lời gọi khác; một worker có thể tạo nhiều request bất đồng bộ hoặc chỉ một request đồng bộ. Dùng mô hình làm điểm khởi đầu cho thí nghiệm, rồi giới hạn bởi connection pool, rate limit và khả năng chịu tải downstream.

## 7. Chọn mô hình mở rộng Spring Batch dựa trên nút thắt

| Bối cảnh đo được | Hướng tiếp cận | Điều kiện và rủi ro cần kiểm soát |
|---|---|---|
 Processor CPU-heavy, có nhiều core rảnh | Partitioning trên cùng JVM hoặc multi-threaded step | Reader/writer thread-safe, overhead vừa phải; CPU/heap không bị cạn |
 CPU đã bão hòa một host, workload chia được | Remote partitioning / nhiều JVM hoặc nâng CPU quota | Data locality, chi phí message, job metadata, retry, restart, idempotency |
 DB/API chậm nhưng còn khả năng xử lý song song | Local partitioning với số worker có giới hạn | DB pool, lock, rate limit, index, transaction duration |
 Một SQL query hoặc write bị nghẽn | Tối ưu SQL, index, batch write, giảm round trip | Tăng thread chưa chắc giúp; kiểm chứng execution plan và khóa |
 Nhiều step độc lập về dữ liệu và thứ tự | Parallel steps / flows | Bảo đảm không tranh chấp cùng bảng/record và thứ tự phụ thuộc |
 Dữ liệu có vùng khóa tách biệt | Partition theo ID, ngày, tenant hoặc hash | Cân bằng khối lượng, không trùng/bỏ sót, tên partition ổn định để restart |
 I/O phụ thuộc dịch vụ có rate limit nghiêm | Giới hạn concurrency, retry có backoff và điều tiết | Tránh retry storm, timeout, làm quá tải dịch vụ |
 Mức tải thấp, overhead parallel lớn | Giữ step đơn luồng | Cấu hình đơn giản, dễ kiểm chứng, ít tranh chấp tài nguyên |

**CPU-bound không có nghĩa luôn phải dùng multi-threaded step.** Với một `ItemReader` stateful không an toàn khi gọi đồng thời, partitioning thường giúp tạo reader scoped riêng cho từng partition và rõ ràng hơn về checkpoint. Nếu job có nhiều bước độc lập, parallel flows có thể phù hợp hơn cách chia các item của một step.

**IO-bound cũng không mặc nhiên cần hàng trăm thread.** Với DB có 16 kết nối, 100 worker cùng giữ cursor và ghi transaction có thể làm pool nghẽn, tăng latency và giảm throughput. Số connection cần cho reader, writer, JobRepository và những tác vụ khác có thể lớn hơn một connection mỗi worker.

### Ví dụ Java config: giới hạn tài nguyên khi partition

Giả sử `workerStep` và `partitioner` đã được khai báo, có thể thử một manager step với tám partition nhưng chỉ bốn worker chạy đồng thời:

~~~java
@Bean
public ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("orders-part-");
    return executor;
}

@Bean
public Step ordersManagerStep(
        JobRepository jobRepository,
        @Qualifier("ordersWorkerStep") Step workerStep,
        @Qualifier("ordersPartitioner") Partitioner partitioner,
        @Qualifier("partitionExecutor") ThreadPoolTaskExecutor executor) {

    return new StepBuilder("ordersManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(8)
            .taskExecutor(executor)
            .build();
}
~~~

Đoạn này cần các import chuẩn của Spring Batch, Spring Framework và những bean nghiệp vụ tương ứng; nó chỉ trình bày phần manager của Java config. **`gridSize=8` chỉ là số phần việc đề nghị**, không phải tám luồng đồng thời. `Partitioner` quyết định cách tạo context và số partition thực tế, trong khi `ThreadPoolTaskExecutor` giới hạn mức đồng thời tại bốn.

Khi thử tăng lên tám worker, phải kiểm tra **CPU/core quota, JDBC pool, DB wait, GC và wall time của partition chậm nhất**. Nếu partition lệch dữ liệu (ví dụ 90% item dồn vào một khoảng ID), worker chậm nhất có thể quyết định tổng thời gian job dù có nhiều worker rảnh.

## 8. Các bẫy thường làm sai kết luận

### “CPU thấp nghĩa là IO-bound”

Sai trong nhiều trường hợp. CPU thấp còn có thể do `synchronized` lock, thread pool thiếu worker, task bị deadlock, scheduler throttling, database transaction lock hoặc chỉ một worker đang chạy trên máy nhiều core. Cần kiểm tra trạng thái luồng, queue và các nguồn wait.

### “CPU 100% nghĩa là processor cần tối ưu”

Chưa chắc. CPU có thể nằm ở GC, nén/giải nén driver, serialization, log formatter hoặc vòng retry lỗi. CPU profiling phải chỉ ra stack thực tế. Với container, CPU throttling có thể khiến tiến trình đạt quota và wall time vẫn cao.

### “I/O chậm thì tăng luồng là xong”

Nếu DB bị giới hạn IOPS, hot row lock hoặc API rate limit, tăng concurrency chỉ tạo thêm hàng đợi và lỗi timeout. Cần tối ưu truy vấn, batching, backpressure và cách chia dữ liệu. Retry không có backoff còn có thể làm trạng thái overload nghiêm trọng hơn.

### “Đọc/ghi đạt nhiều item hơn là job đã nhanh hơn”

`readCount` có thể tăng trong khi `writeCount` không tăng tương ứng do filter/skip hoặc rollback. Một benchmark chỉ đo số đọc cũng có thể bỏ qua lỗi dữ liệu và side effect. Hãy so sánh **kết quả nghiệp vụ được commit/đối soát**, không chỉ tốc độ gọi processor.

### “Tăng partition luôn tốt cho restart”

Partitioning lưu `StepExecution` theo partition, giúp restart vùng lỗi. Nhưng nếu thay đổi ranh giới hoặc tên partition giữa lần chạy lỗi và lần restart, việc khớp metadata trở nên rủi ro. Phải chốt phạm vi dữ liệu, thiết kế writer idempotent và giữ tên partition ổn định.

### “Benchmark chạy ngay trên laptop là đại diện production”

Laptop khác server ở CPU quota, cache, disk I/O, độ trễ mạng, connection pool và dữ liệu. Dùng môi trường tải đại diện, log cấu hình, đo nhiều lượt và kiểm soát các tiến trình khác. Nếu chạy benchmark sau khi cache đã nóng, cần ghi nhận rõ vì kết quả có thể khác lần chạy lạnh.

## 9. Kịch bản thực hành: quyết định mở rộng một job xử lý đơn hàng

**Bài toán:** Spring Batch đọc 3 triệu đơn hàng từ database, tính phí rồi ghi bảng kết quả. SLA là hoàn thành trong 45 phút; hiện mất 90 phút. Ứng dụng có giới hạn bốn vCPU, DB chỉ cấp tối đa 20 connection cho batch.

**Bước 1 — Thu số liệu:** chạy với một worker và đo thời gian reader/processor/writer, process CPU/core quota, GC, SQL latency, kết nối DB, throughput và các lỗi. Giả sử số liệu cho thấy 70% wall time nằm ở truy vấn đọc không có index phù hợp, CPU ứng dụng chỉ dùng dưới một vCPU.

**Bước 2 — Khắc phục nguyên nhân chính:** phân tích execution plan và bổ sung index phù hợp (sau kiểm tra ảnh hưởng ghi), dùng paging/keyset/partition boundaries ổn định nếu hợp với schema, giảm query round trips. Đo lại trước khi đổi kiến trúc.

**Bước 3 — Thử partition:** chia dữ liệu thành các vùng ID hoặc ngày không giao nhau; bắt đầu với hai rồi bốn worker. Ghi thêm `jobExecutionId`, `stepExecutionId` và vùng dữ liệu vào log để xem worker chậm. Không chia dải ID chỉ dựa trên giả định dữ liệu phân bố đều nếu thực tế khóa bị khuyết.

**Bước 4 — Kiểm soát tài nguyên:** đảm bảo số connection thực tế cho reader, writer và JobRepository nằm trong hạn mức 20; xem lock, p95 SQL latency và queue wait. Nếu sau bốn worker database bão hòa, dừng tăng concurrency và tối ưu I/O tiếp.

**Bước 5 — Kiểm chứng đúng dữ liệu:** dùng khóa nghiệp vụ duy nhất, writer idempotent, dữ liệu nguồn có cutoff/snapshot rõ ràng và kế hoạch restart khi partition lỗi. So sánh count và tổng giá trị tiền trước/sau.

**Bước 6 — Quyết định:** nếu sau tối ưu query và bốn worker job hoàn thành trong 35–40 phút ổn định, đạt SLA mà vẫn còn tài nguyên dự phòng, không cần mở rộng phân tán chỉ vì có thể triển khai thêm JVM. Nếu CPU của host tiếp tục là nút thắt sau tối ưu và workload tách được, mới cân nhắc tăng core hoặc remote partitioning.

Kết quả trong kịch bản chỉ minh họa cách ra quyết định; không phải cam kết một mức tăng tốc cụ thể.

## 10. Checklist vận hành và câu hỏi tự kiểm tra

Trước khi chấp nhận một thay đổi concurrency:

1. Có baseline đủ đại diện và đo **CPU time, wall time, throughput** cùng lúc không?
2. Đã phân tích reader, processor, writer, commit và dependency ngoài JVM chưa?
3. Có nhìn thấy DB connection wait, lock, query latency, queue, GC và container CPU throttling không?
4. Thử lần lượt một, hai, bốn worker có cải thiện throughput **ghi thành công** hay chỉ tạo thêm hàng chờ?
5. Reader/processor/writer có thread-safe hoặc được tách instance bằng `@StepScope`/partition đúng cách không?
6. Khi restart, dữ liệu đầu vào, tên partition và checkpoint có còn ổn định không?
7. Writer/side effect có cơ chế chống trùng, retry có giới hạn và skip có quy trình đối soát không?
8. Kết quả đã đáp ứng SLA đồng thời giữ đủ tài nguyên cho hệ thống khác chưa?

**Câu hỏi 1:** CPU ứng dụng chỉ 25%, nhưng một luồng xử lý nén dữ liệu luôn dùng tối đa một core trên host bốn core. Đây có chắc là IO-bound?

**Trả lời:** Không. Một phần tuần tự hoặc chỉ một worker có thể bị giới hạn bởi **một core**, dù trung bình tổng CPU còn rảnh. Cần xem CPU theo thread/core và khả năng song song hóa phần nén.

**Câu hỏi 2:** Chạy tám worker nhanh hơn một worker hai lần, sau đó SQL timeout tăng mạnh. Nên tăng tiếp lên 16 worker?

**Trả lời:** Chưa có cơ sở. Nên kiểm tra DB saturation, connection pool, lock, index, transaction và giới hạn downstream trước; thêm worker có thể chỉ làm tăng queue và lỗi.

**Câu hỏi 3:** `ItemProcessor` mất 10 ms mỗi item. Như vậy có chắc là CPU-bound?

**Trả lời:** Không. 10 ms là wall time, có thể bao gồm chờ gọi API, database hoặc lock. Cần profiling, CPU time và instrument các lời gọi trong processor.

**Câu hỏi 4:** Vì sao hai job có cùng số item và chunk size lại cần mức concurrency khác nhau?

**Trả lời:** Vì chi phí CPU/item, độ trễ I/O, cách phân bố dữ liệu, số kết nối, transaction, side effect, memory và yêu cầu restart có thể khác nhau. Concurrency là một quyết định dựa trên đo đạc, không phải hằng số áp dụng cho mọi job.

## 11. Ghi nhớ

**CPU-bound** là tình huống năng lực tính toán giới hạn throughput; **IO-bound** là tình huống thời gian chờ đọc, ghi, database, disk hoặc mạng chi phối tốc độ xử lý. Spring Batch thực tế thường **mixed**, và nút thắt có thể thay đổi sau khi tối ưu. Vì vậy, trước khi dùng multi-threaded step, parallel steps, partitioning hay remote workers, hãy đo throughput, CPU/core quota, wall time từng giai đoạn, queue, DB wait và chi phí retry/restart. Mô hình mở rộng tốt nhất là mô hình cải thiện **kết quả nghiệp vụ chính xác** trong giới hạn tài nguyên và SLA đo được.
