# Độ phức tạp của các mô hình song song trong Spring Batch

## Mục tiêu bài học

Mở rộng Spring Batch cho dữ liệu lớn không chỉ là tăng số thread hoặc worker. Mỗi mô hình song song đưa vào hệ thống những phần việc mới: chia dữ liệu, đồng bộ trạng thái, hạn chế tranh chấp, xử lý lỗi, khởi động lại và vận hành nhiều thành phần. Nếu chỉ quan sát tốc độ ở lần chạy thành công, một kiến trúc tưởng như nhanh hơn có thể hóa ra đắt hơn và khó phục hồi hơn.

Bài này thuộc chương **Tổng quan scaling** của module **SPRING_BATCH_SCALING_OPERATIONS**. Phạm vi tập trung vào **độ phức tạp của các mô hình song song** trong Spring Batch: multi-threaded step, parallel steps, partitioning tại chỗ, remote chunking và remote partitioning. Trọng tâm là đánh giá cân bằng **hiệu năng, tính đúng dữ liệu, thread safety, retry/restart và vận hành** theo tài nguyên thực tế.

Sau bài học, bạn có thể:

- Giải thích vì sao song song làm giảm thời gian xử lý trong một số điều kiện, đồng thời làm tăng chi phí điều phối và số trạng thái lỗi.
- Phân biệt độ phức tạp tính toán với độ phức tạp triển khai, chia dữ liệu, giao dịch, khôi phục và quan sát.
- So sánh các mô hình song song của Spring Batch mà không mặc định mô hình phân tán luôn tốt hơn.
- Ước lượng giới hạn tăng tốc bằng Amdahl, critical path, bottleneck chung và chi phí điều phối.
- Đưa ra lựa chọn kiến trúc từ số đo CPU, DB, I/O, lock, queue, retry và yêu cầu SLA.
- Thiết kế thử nghiệm chứng minh một mô hình vừa nhanh hơn vừa xử lý đúng khi có lỗi.

## 1. “Độ phức tạp” có nhiều chiều

Một job tuần tự có luồng thực thi dễ dự đoán: đọc, xử lý, ghi, commit rồi tiếp tục. Khi song song hóa, một số item có thể được xử lý cùng lúc; nhưng kết quả phụ thuộc vào cách các thread/worker tương tác với dữ liệu và hạ tầng.

Không nên dùng một con số “độ phức tạp” duy nhất để đánh giá các mô hình. Ít nhất cần phân biệt sáu chiều:

| Chiều | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Tính toán** | Tổng lượng công việc và đường thực thi dài nhất thay đổi thế nào? | CPU cho mỗi item; bước tuần tự còn lại |
| **Điều phối** | Ai chia việc, phân phối và thu kết quả? | TaskExecutor; Partitioner; broker |
| **Dữ liệu/trạng thái** | Worker có sở hữu vùng dữ liệu riêng không? | Shared reader, ID range, checkpoint |
| **Đồng thời** | Những thao tác nào tranh chấp tài nguyên chung? | Connection pool, index, lock, heap |
| **Lỗi và khôi phục** | Worker chết giữa chunk thì ai chạy lại, có thể ghi trùng không? | Retry, restart, idempotent writer |
| **Vận hành** | Triển khai và chẩn đoán cần bao nhiêu thành phần? | Nhiều JVM, queue, tracing, alert |

Ví dụ: chuyển từ một step tuần tự sang **multi-threaded step** có thể chỉ thêm TaskExecutor trong cấu hình, nhưng nếu ItemReader có state dùng chung, thiết kế restart có thể trở nên khó hơn đáng kể. Ngược lại, **partitioning** cần viết Partitioner và quản lý nhiều StepExecution, nhưng ranh giới dữ liệu rõ ràng có thể giúp giải thích lỗi và khôi phục dễ hơn.

**Quy tắc định hướng:** chỉ tăng mức phức tạp khi có bottleneck đo được và có lợi ích đủ lớn để bù đắp chi phí triển khai, xử lý lỗi và vận hành.

## 2. Phân biệt song song, đồng thời và phân tán

Ba khái niệm liên quan nhưng không đồng nhất:

- **Concurrency (đồng thời):** nhiều phần việc có thể đang trong tiến trình thực thi và xen kẽ lẫn nhau; không nhất thiết sử dụng nhiều lõi CPU cùng lúc.
- **Parallelism (song song):** các phần việc thực sự được thực thi cùng lúc, chẳng hạn trên nhiều CPU core hoặc nhiều worker.
- **Distribution (phân tán):** các phần việc chạy trong nhiều process/JVM/máy và cần cơ chế giao tiếp hoặc chia sẻ metadata qua ranh giới tiến trình.

**Multi-threaded step** và **parallel steps** thường hoạt động trong một JVM: nhiều thread nhưng vẫn chia sẻ heap và tiến trình. **Local partitioning** cũng chạy các worker StepExecution trên các thread của một JVM. **Remote partitioning** và **remote chunking** bổ sung ranh giới tiến trình và giao tiếp qua mạng.

~~~mermaid
flowchart TB
    J[Spring Batch Job]
    J --> S[Single-process]
    J --> D[Multi-process]
    S --> T[Multi-threaded step]
    S --> F[Parallel steps]
    S --> L[Local partitioning]
    D --> C[Remote chunking]
    D --> R[Remote partitioning]
    T --> B1["Thread safety + chunk concurrency"]
    F --> B2["Phụ thuộc giữa các flow"]
    L --> B3["Chia dữ liệu + nhiều StepExecution"]
    C --> B4["Broker + dữ liệu chuyển qua mạng"]
    R --> B5["Broker/điều phối + worker tự đọc"]
~~~

Một ứng dụng có bốn pod chạy **các job độc lập** cũng là multi-process, nhưng chưa có nghĩa một JobInstance được chia thành bốn phần. Để phân phối một job, kiến trúc phải định nghĩa **ai sở hữu phần dữ liệu nào**, **cách lưu trạng thái** và **cách xử lý khi worker lỗi**.

## 3. Giới hạn tăng tốc: Amdahl và critical path

### 3.1. Định luật Amdahl

Nếu tỷ lệ \(s\) trong tổng thời gian chạy bắt buộc tuần tự và phần còn lại có thể song song hoàn hảo trên \(p\) đơn vị xử lý, giới hạn speedup là:

\[
S(p) \leq \frac{1}{s + \frac{1-s}{p}}
\]

Ví dụ giả định **20% thời gian job phải tuần tự**:

| Số đơn vị xử lý \(p\) | Speedup lý tưởng tối đa | Nhận xét |
| ---: | ---: | --- |
| 1 | 1,00× | Baseline |
| 2 | 1,67× | Chưa thể đạt 2× |
| 4 | 2,50× | Chưa thể đạt 4× |
| 8 | 3,33× | Lợi ích biên giảm |
| 16 | 4,00× | Tăng nhiều đơn vị nhưng lợi ích nhỏ |
| Tiến tới vô hạn | 5,00× | Giới hạn do phần tuần tự 20% |

Công thức **chưa tính** broker, serialization, tranh chấp DB, GC và rollback; speedup thực tế thường thấp hơn. Nó cũng không khẳng định cứ tăng worker là tốc độ sẽ tăng: hệ thống có thể chậm đi khi contention lớn.

Phần tuần tự không chỉ là mã chạy bằng một thread. Nó còn có thể là một reader trung tâm, bước tổng hợp cuối, thao tác cập nhật trạng thái bắt buộc hoặc tài nguyên chung chỉ cho phép một số giao dịch cùng lúc.

### 3.2. Tổng công việc và đường dài nhất

Với nhiều flow hoặc partition, cần phân biệt:

- **Total work:** tổng số phép tính, I/O và giao dịch cần làm trên mọi phần việc.
- **Critical path:** chuỗi công việc phụ thuộc nhau dài nhất, quyết định cận dưới của thời gian hoàn thành.
- **Coordination overhead:** thời gian chia việc, khởi tạo worker, gửi message, cập nhật trạng thái và tổng hợp.
- **Contention/recovery:** thời gian chờ tài nguyên chung và xử lý lại khi lỗi.

Một mô hình gần đúng có ích khi thiết kế:

\[
T_{\mathrm{job}}
\approx T_{\mathrm{setup}}
+ T_{\mathrm{critical}}
+ T_{\mathrm{coordination}}
+ T_{\mathrm{contention}}
+ T_{\mathrm{recovery}}
\]

Đây là mô hình định tính, **không phải công thức dự đoán chính xác**: các thành phần có thể chồng thời gian lên nhau và phụ thuộc vào dữ liệu. Mục đích là buộc người thiết kế tính đủ chi phí ngoài thời gian xử lý một item.

### 3.3. Nút thắt tài nguyên chung

Nếu một job có các công đoạn đọc, xử lý và ghi, throughput bền vững không thể vượt quá năng lực công đoạn chậm nhất, sau khi quy đổi cùng đơn vị item/giây:

\[
R_{\mathrm{end-to-end}} \leq
\min(R_{\mathrm{read}},\,R_{\mathrm{process}},\,R_{\mathrm{write}},\,R_{\mathrm{transport}})
\]

Trong mô hình không dùng broker, có thể bỏ giới hạn transport khỏi phép so sánh. Công thức giả định dữ liệu đi qua các công đoạn một cách tương ứng; nếu processor lọc/sinh thêm item thì cần quy đổi lưu lượng trước khi so.

Ví dụ nguồn dữ liệu đọc tối đa 15.000 item/s, các worker xử lý 40.000 item/s, nhưng DB đích ghi tối đa 12.000 item/s: thêm worker xử lý khó giúp end-to-end throughput vượt **12.000 item/s** nếu không cải thiện bước ghi.

## 4. Baseline: một step tuần tự

**Single-threaded chunk-oriented step** thường là điểm bắt đầu hợp lý vì đường đi dữ liệu, thứ tự thực hiện và checkpoint dễ kiểm tra hơn:

~~~mermaid
flowchart LR
    A[Read] --> B[Process]
    B --> C[Write]
    C --> D[Commit]
    D -. "Chunk tiếp" .-> A
~~~

Ưu điểm là ít state chia sẻ đồng thời, ít cấu hình, dễ xác định nguyên nhân lỗi. Nhược điểm là một thread có thể không khai thác hết nhiều CPU core hoặc thời gian chờ I/O.

Baseline phải có số đo: **số item, thời gian job/step, throughput, CPU, heap/GC, query latency, write latency, connection wait và rollback**. Nếu CPU chỉ 10% và DB đang lock nặng, thêm thread chỉ có thể làm vấn đề tệ hơn.

Đừng coi “job có nhiều triệu dòng” là lý do tự động chuyển sang mô hình phân tán. Quyết định phải dựa trên **khả năng chia việc và điểm nghẽn thực tế**.

## 5. Multi-threaded step: ít thành phần, khó hơn về state

Multi-threaded step dùng TaskExecutor để thực hiện nhiều chunk của cùng step trên các thread. Đây là dạng song song hóa tương đối gần với kiến trúc tuần tự, vì vẫn dùng một process/JVM và hạ tầng job hiện hữu.

~~~mermaid
flowchart TB
    S[Multi-threaded Step] --> T1["Thread 1: chunk A"]
    S --> T2["Thread 2: chunk B"]
    S --> T3["Thread 3: chunk C"]
    T1 --> DB[(Database)]
    T2 --> DB
    T3 --> DB
~~~

### Chi phí phát sinh

**Thread safety:** nếu reader giữ cursor, vị trí file, biến đếm hoặc buffer mutable, nhiều thread có thể đọc trùng hoặc bỏ sót item. ItemProcessor và ItemWriter cũng cần được xem xét nếu chia sẻ state. Không mặc định rằng mọi Spring Batch ItemReader đều thread-safe.

**Thứ tự:** chunk có thể hoàn tất không theo thứ tự đọc. Nếu nghiệp vụ yêu cầu thứ tự tuyệt đối hoặc ghi phụ thuộc giữa các record, cần thiết kế lại hoặc giữ xử lý tuần tự phù hợp.

**Transaction:** từng chunk đồng thời có thể dùng giao dịch/connection khác nhau; DB phải chịu số transaction đang hoạt động tăng. Cần giới hạn TaskExecutor và connection pool cùng nhau.

**Restart:** đồng bộ hóa lời gọi read không tự bảo đảm checkpoint chính xác khi chunk hoàn tất lệch thứ tự. Phải thử kill process, rollback và chạy lại với dữ liệu thật.

### Ví dụ cấu hình minh họa Spring Batch 5.x

~~~java
@Bean
public TaskExecutor batchExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-");
    executor.initialize();
    return executor;
}

@Bean
public Step concurrentStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> reader,
        ItemProcessor<InputRow, OutputRow> processor,
        ItemWriter<OutputRow> writer,
        @Qualifier("batchExecutor") TaskExecutor batchExecutor) {

    return new StepBuilder("concurrentStep", jobRepository)
            .<InputRow, OutputRow>chunk(250, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(batchExecutor)
            .build();
}
~~~

Ví dụ giả định InputRow, OutputRow, các bean và import tương ứng đã được khai báo; **reader/processor/writer phải được đánh giá thread safety trước khi dùng**. Các API, tùy chọn giới hạn concurrency và cách cấu hình có thể khác giữa các phiên bản Spring Batch.

**Khi nên chọn:** chunk có thể xử lý độc lập, thành phần dùng chung an toàn luồng, CPU/I/O còn dư, và một JVM vẫn đủ tài nguyên.

**Khi không nên chọn:** reader giữ state khó đồng bộ, thứ tự xử lý bắt buộc, yêu cầu restart khắt khe hoặc DB đã bão hòa.

## 6. Parallel steps: dễ khi các flow độc lập, khó khi có phụ thuộc

Parallel steps cho phép chạy các **flow/step độc lập** cùng lúc, thường thông qua split flow và TaskExecutor trong một JVM. Khác với multi-threaded step, mô hình này không bắt buộc chia một tập item thành nhiều chunk đồng thời; nó tận dụng tính độc lập giữa **các nhánh nghiệp vụ**.

Ví dụ:

~~~mermaid
flowchart TB
    J[Job start] --> A[Split]
    A --> S1[Flow 1: tính báo cáo bán hàng]
    A --> S2[Flow 2: tính báo cáo tồn kho]
    S1 --> C[Tiếp tục khi các nhánh đạt điều kiện hoàn tất]
    S2 --> C
    C --> E[Step xuất kết quả cuối]
~~~

### Độ phức tạp xuất phát từ đồ thị phụ thuộc

Nếu hai flow đọc các bảng riêng và ghi vào đích riêng, complexity tương đối thấp. Nếu flow A cung cấp dữ liệu tạm cho flow B, chạy chúng đồng thời có thể tạo race condition hoặc dữ liệu thiếu. Nếu cả hai cùng ghi một bảng tổng hợp, vẫn phải kiểm soát unique key, isolation và transaction.

Thời gian lý tưởng của hai nhánh độc lập:

\[
T_{\mathrm{parallel\ flows}}
\approx \max(T_A, T_B) + T_{\mathrm{join}} + T_{\mathrm{overhead}}
\]

So với chạy tuần tự xấp xỉ \(T_A + T_B\), phần có thể tiết kiệm bị giới hạn bởi nhánh dài hơn và tài nguyên chia sẻ. Nếu một nhánh mất 40 phút, nhánh kia 2 phút, chạy song song không làm nhánh 40 phút biến mất.

**Khi nên chọn:** job có các nhánh nghiệp vụ độc lập, số nhánh không quá lớn, mỗi step tự quản lý input/checkpoint rõ ràng.

**Cần tránh:** tạo quá nhiều flow nhỏ chỉ để tăng thread; chi phí cấu hình đồ thị và phụ thuộc có thể vượt lợi ích. Các bước phải kết thúc theo điều kiện flow phù hợp trước khi chạy bước tổng hợp.

## 7. Local partitioning: thêm điều phối, giảm state dùng chung

Partitioning chia một **worker step** thành nhiều vùng dữ liệu độc lập. Manager tạo tên partition và **ExecutionContext** cho từng phần; các worker StepExecution thực thi cùng định nghĩa step nhưng nhận input riêng. Ở **local partitioning**, các worker chạy trên thread trong cùng JVM.

~~~mermaid
flowchart TB
    M[Manager Step] --> P[Partitioner]
    P --> A["partition-0<br/>ID [1, 1001)"]
    P --> B["partition-1<br/>ID [1001, 2001)"]
    P --> C["partition-2<br/>ID [2001, 3001)"]
    A --> W1[Worker StepExecution 0]
    B --> W2[Worker StepExecution 1]
    C --> W3[Worker StepExecution 2]
    W1 --> DB[(Nguồn và đích)]
    W2 --> DB
    W3 --> DB
~~~

### Độ phức tạp mới

1. **Định nghĩa ranh giới:** mỗi item phải thuộc đúng một partition, tránh vừa chồng lấn vừa bỏ sót.
2. **Cân bằng tải:** khoảng ID bằng nhau không chắc có cùng số record; một partition nặng có thể kéo dài toàn job.
3. **Định danh ổn định:** partition name, phạm vi và high-watermark cần nhất quán khi restart cùng JobInstance.
4. **Metadata:** manager và từng worker StepExecution cần trạng thái và checkpoint riêng trong JobRepository.
5. **Tài nguyên:** nhiều reader cùng truy vấn DB có thể tăng connection, I/O và lock contention.

### Ví dụ Partitioner rút gọn

~~~java
@Bean
public Partitioner rangePartitioner() {
    return gridSize -> {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        long minInclusive = 1L;
        long maxExclusive = 1_000_001L;
        long total = maxExclusive - minInclusive;
        int count = Math.max(1, gridSize);
        long width = (total + count - 1L) / count;

        for (int index = 0; index < count; index++) {
            long from = minInclusive + index * width;
            if (from >= maxExclusive) {
                break;
            }
            long to = Math.min(from + width, maxExclusive);

            ExecutionContext input = new ExecutionContext();
            input.putLong("minIdInclusive", from);
            input.putLong("maxIdExclusive", to);
            partitions.put("part-" + index, input);
        }
        return partitions;
    };
}
~~~

Ví dụ minh họa theo kiểu API phổ biến của Spring Batch 5.x, với import cần thiết từ Java và Spring Batch. Worker reader cần đọc đúng minIdInclusive/maxIdExclusive bằng **@StepScope** và truy vấn có điều kiện; chỉ tạo Partitioner chưa làm dữ liệu tự động tách. Trên hệ thống thật, các cận cần được chốt ổn định cho lần chạy thay vì truy vấn MAX(id) khác nhau khi restart.

Local partitioning thường có **chi phí triển khai lớn hơn multi-threaded step**, nhưng lại dễ suy luận về dữ liệu nếu reader trong mỗi partition độc lập. Cả manager và các worker vẫn cùng chịu rủi ro khi JVM chết.

### Grid size không bằng số worker thực thi đồng thời

**Grid size** liên quan đến cách phân chia số partition; mức đồng thời thực tế còn phụ thuộc TaskExecutor, PartitionHandler và cấu hình triển khai. Có thể có **nhiều partition hơn số thread** để các thread rảnh nhận phần tiếp theo, nhưng quá nhiều partition nhỏ làm tăng chi phí tạo/quản lý metadata.

## 8. Remote chunking: phức tạp ở vận chuyển dữ liệu

Trong **remote chunking**, manager thường thực hiện **read** và hình thành chunk; các worker qua mạng nhận dữ liệu để **process/write** rồi phản hồi. Đây là lựa chọn khi phần xử lý/ghi dễ phân phối và reader trung tâm đủ nhanh.

~~~mermaid
flowchart LR
    DB[(Nguồn)] --> M["Manager JVM<br/>read + tạo chunk"]
    M --> Q[[Message middleware]]
    Q --> W1["Worker JVM 1<br/>process/write"]
    Q --> W2["Worker JVM 2<br/>process/write"]
    Q --> W3["Worker JVM 3<br/>process/write"]
    W1 --> T[(Đích)]
    W2 --> T
    W3 --> T
    W1 -. "kết quả" .-> M
    W2 -. "kết quả" .-> M
    W3 -. "kết quả" .-> M
~~~

### Những lớp complexity bổ sung

- **Serialization và payload:** item/chunk phải có biểu diễn tương thích giữa manager và worker; payload lớn tạo chi phí mạng, bộ nhớ và broker.
- **Broker và queue:** cần giám sát độ sâu hàng đợi, message age, retry, timeout, dead-letter và khả năng xử lý khi broker gián đoạn.
- **Idempotency:** có tình huống worker commit thành công nhưng phản hồi bị mất; gửi lại phần việc có thể làm side effect xảy ra lần nữa nếu writer không chống trùng.
- **Compatibility:** khi manager/worker không cùng phiên bản DTO hoặc giao thức, message có thể không giải mã được.
- **Điểm nghẽn manager:** dù tăng số worker, một tiến trình manager vẫn đọc và gửi toàn bộ item; tốc độ reader/transport tạo ra giới hạn.

Về độ phức tạp, việc thêm worker từ 4 lên 8 tương đối thuận tiện **nếu** broker và DB đích còn dư tài nguyên. Nhưng vận hành phải chuẩn bị phương án xử lý message tồn đọng, worker mất kết nối và trạng thái không khớp giữa ghi DB và ack.

**Khi nên chọn:** item có kích thước đủ nhỏ để chuyển qua broker, reader không phải bottleneck, process/write tiêu tốn CPU hoặc I/O đáng kể và dễ làm lặp lại an toàn.

**Khi không nên chọn:** nguồn đọc quá lớn/chậm, item tải nhiều dữ liệu qua mạng, hoặc yêu cầu giao dịch chéo DB và broker nhưng chưa có thiết kế nhất quán.

## 9. Remote partitioning: phức tạp ở chia phạm vi và metadata phân tán

Trong **remote partitioning**, manager phân chia dữ liệu bằng **ExecutionContext** rồi điều phối các worker JVM tự đọc, xử lý và ghi phần dữ liệu của mình. Khác remote chunking, manager không cần đọc và gửi toàn bộ item qua message.

~~~mermaid
flowchart TB
    M["Manager JVM<br/>Partitioner"] --> Q[[Điều phối partition]]
    Q --> W1["Worker JVM 1<br/>range A"]
    Q --> W2["Worker JVM 2<br/>range B"]
    Q --> W3["Worker JVM 3<br/>range C"]
    W1 --> DB[(Nguồn / đích)]
    W2 --> DB
    W3 --> DB
    R[(JobRepository bền vững)] --- M
    R --- W1
    R --- W2
    R --- W3
~~~

### Độ phức tạp cần quản lý

**Chia việc đúng:** tên partition và phạm vi nguồn phải ổn định; kiểm tra không chồng lấn, không mất item và cân bằng dữ liệu. Worker đọc trực tiếp nên có thể tăng tổng áp lực lên DB nguồn.

**Điều phối phân tán:** cần cơ chế manager gửi yêu cầu thực thi, worker nhận đúng StepExecution, cập nhật trạng thái và phản hồi. Tùy giải pháp, có thể dùng Spring Batch Integration với messaging/partition handler; phải kiểm tra cấu hình tương thích phiên bản đang dùng.

**Metadata và restart:** JobRepository bền vững, có thể truy cập theo kiến trúc, giúp quản lý StepExecution và ExecutionContext. Worker chết giữa chunk cần có chiến lược nhận diện, timeout, retry/restart an toàn.

**Triển khai:** manager và worker có thể dùng bộ package/config khác nhau; cần thống nhất tên step, serializer, dữ liệu context, transaction và chính sách bảo mật.

**Capacity planning:** mỗi worker mở connection, giữ heap, truy vấn index và ghi đích. Scale-out CPU không giúp nếu DB và mạng đã bão hòa.

Vì manager thường gửi **mô tả phần việc** thay vì chuyển cả tập item, remote partitioning hấp dẫn khi có thể chia nguồn dữ liệu theo ID, ngày, tenant hoặc shard. Nhưng nếu ranh giới dữ liệu không ổn định, có record chuyển vùng giữa các lần đọc hoặc mỗi worker tranh chấp cùng bảng đích, khó khăn về tính đúng sẽ tăng đáng kể.

## 10. So sánh độ phức tạp của các mô hình

Bảng sau là **đánh giá định tính tương đối**, dựa trên giả định job dữ liệu lớn với chunk-oriented step, hạ tầng DB chung và yêu cầu restart. “Thấp”, “trung bình”, “cao” không phải điểm số tuyệt đối; kết quả thay đổi theo tính chất dữ liệu và hệ thống.

| Mô hình | Chia dữ liệu | Concurrency / state | Điều phối và triển khai | Xử lý lỗi / restart | Giới hạn thường gặp |
| --- | --- | --- | --- | --- | --- |
| **Một step tuần tự** | Thấp | Thấp | Thấp | Thường dễ nhất | Một luồng, I/O |
| **Multi-threaded step** | Ít cơ chế tách dữ liệu tự thân | **Cao** nếu reader mutable dùng chung | Thấp–trung bình | Khó hơn khi chunk lệch thứ tự | Thread safety, DB |
| **Parallel steps** | Thấp nếu flow độc lập; cao nếu phụ thuộc | Trung bình | Trung bình | Theo từng flow và điều kiện join | Critical path, tài nguyên chung |
| **Local partitioning** | **Trung bình–cao**: cần ranh giới đúng | Trung bình khi reader riêng | Trung bình | Theo partition/StepExecution | Cùng một JVM, DB |
| **Remote chunking** | Manager tiếp tục đọc item | Trung bình tại worker | **Cao**: broker, payload, worker | **Cao**: giao nhận, retry, idempotency | Manager, broker, DB đích |
| **Remote partitioning** | **Cao**: partition đúng và ổn định | Trung bình tại từng worker | **Cao**: manager, worker, repository | **Cao**: metadata và worker mất kết nối | Nguồn/đích, điều phối |

Không thể xếp mọi mô hình theo một “thứ bậc tốt hơn” cố định. Ví dụ:

- Với ba báo cáo hoàn toàn độc lập, **parallel steps** có thể đơn giản hơn viết partitioning.
- Với một bảng lớn có khóa ID rõ, **local partitioning** có thể dễ kiểm tra tính đúng hơn multi-threaded step chia sẻ cursor.
- Với dữ liệu rất lớn mà reader trung tâm chậm, **remote partitioning** thường hợp lý hơn remote chunking.
- Với CPU của một JVM còn dư và DB đã bão hòa, **không** nên chuyển sang remote partitioning chỉ vì muốn nhiều worker.

### Mức tăng độ phức tạp theo kiến trúc

~~~mermaid
flowchart LR
    A["Step tuần tự<br/>baseline"] --> B["Multi-threaded step<br/>state/thread safety"]
    A --> C["Parallel steps<br/>phụ thuộc flow"]
    B --> D["Local partitioning<br/>range + metadata"]
    C --> D
    D --> E["Remote partitioning<br/>network + worker lifecycle"]
    A --> F["Remote chunking<br/>broker + payload"]
~~~

Mũi tên minh họa **những hướng mở rộng có thể cân nhắc**, không phải các bước bắt buộc. Có thể đi trực tiếp từ baseline đến mô hình đáp ứng đúng bài toán; không phải triển khai từng cấp.

## 11. Những nguồn phức tạp ẩn thường bị bỏ qua

### 11.1. Shared mutable state

Các đối tượng như file cursor, bộ đệm writer, cache mutable, biến đếm trong processor hoặc singleton không thread-safe có thể tạo lỗi hiếm xuất hiện khi tăng concurrency. Vì vậy, kiểm tra thread safety ở cấp **component và tài nguyên mà component sử dụng**, không chỉ kiểm tra StepBuilder.

Với partitioning, dùng **@StepScope** cho reader phụ thuộc ExecutionContext để mỗi StepExecution có reader phù hợp. Điều này giúp giảm chia sẻ state nhưng không tự bảo đảm tính an toàn của các bean khác hoặc truy vấn DB.

### 11.2. Dữ liệu thay đổi khi job đang chạy

Chia thành các khoảng ID chỉ đúng nếu đầu vào có định nghĩa ổn định. Nếu đơn hàng được thêm, cập nhật hoặc chuyển tenant trong khi các worker đang đọc, việc “mỗi ID thuộc một khoảng” chưa đủ để quyết định bản ghi nào cần tính.

Có thể cần high-watermark, snapshot transaction, cutoff timestamp hoặc chiến lược xử lý thay đổi. Những giá trị điều khiển này phải nhất quán qua restart. Không lấy MAX(id) mới mỗi khi worker bị khởi động lại rồi âm thầm đổi phạm vi.

### 11.3. Tranh chấp ở đích

Worker có thể đọc các range độc lập nhưng vẫn cập nhật cùng một dòng tổng hợp, cùng index hoặc cùng batch key. Việc chia dữ liệu ở nguồn không bảo đảm không tranh chấp ở đích.

Ví dụ 10 partition đều cập nhật một record “tổng doanh thu ngày” khiến giao dịch xếp hàng trên cùng hàng DB. Thường hợp lý hơn khi mỗi partition ghi kết quả độc lập, sau đó một bước tổng hợp có kiểm soát hợp nhất kết quả.

### 11.4. Idempotency và giao nhận lại

Ở hệ thống phân tán, có thể xảy ra:

1. Worker nhận partition/chunk.
2. Worker ghi dữ liệu và commit thành công.
3. Worker chết trước khi manager nhận xác nhận.
4. Manager hoặc bộ điều phối thử thực hiện lại phần việc.

Nếu writer không lặp lại an toàn, dữ liệu có thể bị ghi trùng hoặc cộng dồn hai lần. JobRepository hỗ trợ quản lý trạng thái nhưng không tự biến side effect qua nhiều tài nguyên thành giao dịch “exactly once”.

Giải pháp tùy nghiệp vụ: unique business key, upsert, idempotency key cho API, transactional outbox hoặc quy trình đối soát. **Retry và restart phải được thiết kế cùng với logic ghi dữ liệu.**

### 11.5. Số trạng thái lỗi tăng nhanh

Một job tuần tự thường tập trung phân tích trạng thái step, exception và checkpoint. Khi có nhiều JVM, có thêm trạng thái network, broker, worker, repository và DB. Một worker **có thể đang xử lý** trong khi manager **đang chờ phản hồi**, hoặc một message được gửi lại sau timeout.

Tăng số worker cũng tăng số giao dịch song song, số kết nối và số nguồn log cần liên kết. Vì vậy complexity vận hành có thể tăng dù thuật toán xử lý mỗi item không đổi.

## 12. Đánh giá bằng một ma trận quyết định

Để chọn mô hình, bắt đầu từ một số câu hỏi cụ thể:

| Câu hỏi | Nếu câu trả lời là… | Hướng cần cân nhắc |
| --- | --- | --- |
| Nhiều step có hoàn toàn độc lập? | Có | Parallel steps |
| Item/chunk có độc lập, component thread-safe? | Có và một JVM còn dư | Multi-threaded step |
| Có thể chia input theo ID, ngày, tenant, file? | Có, ranh giới ổn định | Local/remote partitioning |
| Bị giới hạn CPU/RAM một JVM? | Có sau khi tối ưu nội bộ | Remote partitioning hoặc remote chunking |
| Manager đọc nguồn rất nhanh, process/write nặng? | Có; item gửi qua mạng hợp lý | Remote chunking |
| Input rất lớn, mỗi worker có thể tự đọc nguồn? | Có; DB chịu được tải | Remote partitioning |
| Database đích đã bão hòa? | Có | Tối ưu write, SQL, connection/lock trước |
| Nguồn không thể đọc đồng thời an toàn? | Có | Giữ concurrency thấp hoặc thay cách phân phối nguồn |

### Cây lựa chọn minh họa

~~~mermaid
flowchart TD
    A[Đo baseline tuần tự] --> B{Bottleneck nào?}
    B -->|DB hoặc API| C["Tối ưu query, batch write,<br/>quota, lock"]
    B -->|CPU/JVM| D{Phần việc độc lập?}
    B -->|Nhiều flow độc lập| E[Parallel steps]
    D -->|Không| F["Thiết kế lại ranh giới<br/>dữ liệu hoặc thuật toán"]
    D -->|Có| G{Một JVM còn dư tài nguyên?}
    G -->|Có, component thread-safe| H[Thử multi-threaded step]
    G -->|Có, chia range rõ| I[Thử local partitioning]
    G -->|Không| J{Worker có thể tự đọc nguồn?}
    J -->|Có| K[Remote partitioning]
    J -->|Không; manager đọc đủ nhanh| L[Remote chunking]
    C --> M[Benchmark lại + fault injection]
    E --> M
    F --> M
    H --> M
    I --> M
    K --> M
    L --> M
~~~

Đây là khung tư duy, không phải một thuật toán tự động chọn kiến trúc. Cần kiểm tra yêu cầu thứ tự, tính nhất quán, mức phức tạp của deployment và khả năng vận hành của đội ngũ trước khi quyết định.

## 13. Bài toán thực tế: xử lý 12 triệu giao dịch

Một hệ thống xử lý **12 triệu giao dịch**, làm giàu thông tin khách hàng và ghi kết quả vào kho dữ liệu. SLA là **15 phút** sau khi dữ liệu đầu vào được chốt.

Throughput lý tưởng tối thiểu để đáp ứng SLA:

\[
R_{\mathrm{required}} = \frac{12.000.000}{15 \times 60}
\approx 13.333\ \mathrm{item/s}
\]

Thực tế cần dự phòng thời gian khởi tạo, retry, các bước tổng hợp và sai số tải. Giả sử nhóm đã đo được các năng lực sau (đều là **số liệu giả định**):

| Công đoạn | Throughput tối đa đã đo | Ý nghĩa |
| --- | ---: | --- |
| Đọc DB nguồn qua nhiều query độc lập | 17.000 item/s | Còn dư so với SLA |
| Xử lý mỗi worker JVM | 5.000 item/s | Có thể mở rộng bằng thêm worker |
| Ghi DB đích | 15.000 item/s | Giới hạn chung toàn job |
| Broker cho metadata partition | Đủ khả năng xử lý trong thí nghiệm | Không phải bottleneck hiện tại |

Nếu có **bốn worker**, năng lực xử lý tổng lý thuyết đạt 20.000 item/s nhưng throughput cuối không vượt quá:

\[
\min(17.000,\ 4 \times 5.000,\ 15.000) =
15.000\ \mathrm{item/s}
\]

Ngay cả lý tưởng, thời gian xử lý tối thiểu khoảng **800 giây (13 phút 20 giây)**, chưa tính overhead và lỗi. SLA 15 phút có rất ít dư địa. Thêm từ bốn lên tám worker không vượt được giới hạn ghi 15.000 item/s.

### Lộ trình thực hiện

**Giai đoạn 1 — Baseline:** một step tuần tự chỉ đạt 5.500 item/s. CPU một JVM cao, DB đích còn dự phòng. Nhóm xác nhận có thể đọc theo các khoảng ID ổn định.

**Giai đoạn 2 — Local partitioning:** thử bốn partition và bốn thread trong một JVM. Throughput tăng nhưng CPU/RAM tiến gần giới hạn host; cần kiểm tra heap/GC và DB query. Chọn partitioning giúp mỗi worker có reader, checkpoint và phạm vi dữ liệu riêng.

**Giai đoạn 3 — Remote partitioning:** tách worker ra nhiều JVM, giữ nguyên hợp đồng input theo ID. Thử hai rồi bốn worker; throughput tiến tới trần 15.000 item/s của DB đích.

**Giai đoạn 4 — Tối ưu nút thắt mới:** cải thiện write batching/index và chính sách ghi. Nếu DB đích đạt 18.000 item/s, nguồn đọc 17.000 item/s sẽ thành nút thắt tiếp theo; tối đa lý thuyết khi đó là 17.000 item/s, tức **khoảng 706 giây (11 phút 46 giây)** trước overhead.

**Giai đoạn 5 — Kiểm tra lỗi:** dừng worker giữa chunk, restart partition chưa hoàn tất, đối soát business key và đo tổng thời gian khôi phục. Chỉ coi kiến trúc đạt yêu cầu nếu cả lần chạy bình thường lẫn sự cố thực tế đều đáp ứng mức độ tin cậy mong muốn.

Tình huống cho thấy độ phức tạp tăng từ local lên remote partitioning chỉ đáng giá khi **giới hạn JVM là thật**. Sau đó, bottleneck chuyển tới DB đích; tăng worker tiếp không giúp.

## 14. Benchmark đúng để đánh giá độ phức tạp có đáng giá hay không

Tăng tốc phải được đo cùng chi phí và rủi ro. Tối thiểu cần thu thập:

| Nhóm | Metric và bằng chứng |
| --- | --- |
| **Kết quả** | Job elapsed time, read/write throughput, SLA đạt hay không |
| **Song song** | Worker/thread active, queue depth, partition chưa hoàn tất |
| **CPU/bộ nhớ** | CPU mỗi JVM/host, heap usage, allocation, GC pause |
| **Database** | Query latency, active connections, lock wait, deadlock, transaction duration, write latency |
| **Điều phối** | Broker lag, message age, dispatch/response latency, timeout, metadata latency |
| **Tính đúng** | Số business key duy nhất, số record thiếu/trùng, số skip/retry/rollback |
| **Phục hồi** | Thời gian restart, số phần việc làm lại, khả năng resume đúng |
| **Chi phí** | CPU giờ, RAM, số replica, broker/DB capacity, công sức vận hành |

### Quy trình thử nghiệm

1. Chạy **baseline** với dữ liệu đại diện, lưu cấu hình và kết quả.
2. Tối ưu query, reader, writer, commit interval, index trước khi nhân worker.
3. Giữ nguyên dataset và chỉ thay **một biến quan trọng mỗi lần**: số thread, số partition hoặc số worker.
4. Thử các mức 1, 2, 4, 8 (chỉ khi hạ tầng cho phép), đo speedup và **parallel efficiency**.
5. Quan sát bottleneck dịch chuyển từ CPU sang DB, network hoặc broker.
6. Thực hiện fault injection: dừng worker, ngắt kết nối, làm chậm DB, gây lỗi dữ liệu.
7. Đối soát business key và kiểm tra restart, sau đó mới quyết định có nên giữ kiến trúc phức tạp hơn.

Với \(p\) đơn vị xử lý và throughput baseline \(R_1\), có thể tham khảo:

\[
\mathrm{Speedup}(p) = \frac{R_p}{R_1}, \qquad
\mathrm{Efficiency}(p) = \frac{\mathrm{Speedup}(p)}{p}
\]

Các phép tính có ý nghĩa khi so cùng loại workload, cùng đơn vị và kết quả nghiệp vụ tương đương. Efficiency thấp có thể do phần tuần tự, contention hoặc overhead; không dùng riêng nó để kết luận mô hình “sai”.

**Chú ý:** việc nhân số worker có thể giảm tổng thời gian nhưng tăng đáng kể tài nguyên và chi phí. Nếu SLA đã đạt với 4 worker mà 8 worker chỉ nhanh hơn 3%, cần cân nhắc giá trị thực tế so với chi phí vận hành và failure surface lớn hơn.

## 15. Retry/restart và tính đúng dữ liệu là một phần của complexity

Tốc độ không có giá trị nếu một lỗi làm job bỏ sót hoặc ghi trùng record.

### Trách nhiệm của từng mô hình

- **Multi-threaded step:** kiểm soát reader/processor/writer chia sẻ state, thứ tự chunk và checkpoint khi commit lệch thứ tự.
- **Parallel steps:** xác định phụ thuộc giữa flow, điều kiện join và các bước có được chạy lại độc lập không.
- **Local partitioning:** partition input phải ổn định; mỗi StepExecution có ExecutionContext và reader riêng, không chồng lấn dữ liệu.
- **Remote chunking:** quản lý khả năng message gửi lại, worker commit nhưng ack mất, payload và phản hồi qua broker.
- **Remote partitioning:** quản lý partition ownership, StepExecution metadata, worker mất kết nối và đồng bộ phiên bản manager/worker.

### Tình huống worker chết sau khi commit

Giả sử worker ghi thành công chunk nhưng chết trước khi báo trạng thái về manager. Tùy mô hình điều phối, phần việc có thể bị kiểm tra, retry hoặc chạy lại. Cần:

- **Writer idempotent** theo business key, ví dụ dùng unique constraint/upsert khi phù hợp.
- **Input ổn định** qua restart (snapshot, high-watermark, khoảng ID/tenant rõ ràng).
- **Checkpoint bền vững**, ItemStream đúng cách và JobRepository được cấu hình phù hợp.
- **Retry có giới hạn** và phân loại lỗi có thể phục hồi.
- **Đối soát** record và business key sau khi job hoàn tất, không chỉ dựa vào trạng thái COMPLETED.

Với side effect qua HTTP/email hoặc hệ thống ngoài transaction DB, cần idempotency key, outbox hoặc cơ chế chuyên biệt. Không giả định JobRepository và message broker biến nhiều tài nguyên độc lập thành transaction “exactly once”.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| “Tám thread thì job nhanh gấp tám.” | Có phần tuần tự, contention, overhead và giới hạn resource chung; Amdahl chỉ cho cận trên lý tưởng. |
| “Multi-process luôn nhanh hơn single-process.” | Nếu DB/broker/API đã bão hòa, thêm process có thể làm chậm hơn. |
| “Multi-threaded step có ít code nên đơn giản nhất.” | Reader mutable và checkpoint lệch thứ tự có thể khiến tính đúng/restart khó hơn partitioning. |
| “Có TaskExecutor tức là phân tán.” | TaskExecutor trong cùng JVM chỉ tạo concurrency nội bộ; phân tán cần nhiều process và điều phối phù hợp. |
| “Nhiều pod cùng chạy một job sẽ tự chia dữ liệu.” | Cần phân vùng hoặc xác định JobInstance và input độc lập; replica không tự chia phạm vi nguồn. |
| “Remote chunking giúp nhiều worker cùng đọc DB.” | Trong mô hình chuẩn, manager đọc và gửi item/chunk; worker xử lý/ghi. |
| “Remote partitioning chỉ việc tăng số worker.” | Phải thiết kế Partitioner, ExecutionContext, StepExecution, giao thức điều phối và restart. |
| “Phân vùng nguồn không chồng lấn nghĩa là ghi không tranh chấp.” | Worker có thể cùng cập nhật một key/bảng/index ở đích. |
| “Broker đã ack nên không còn nguy cơ ghi trùng.” | Ack và commit DB có thể không atomic; phải thiết kế idempotency. |
| “Số partition phải đúng bằng số worker.” | Có thể có nhiều partition hơn worker để cân bằng tải, nhưng quá nhiều partition tạo overhead. |
| “Thời gian chạy happy path đủ để chọn kiến trúc.” | Phải xét retry, restart, correctness, SLA, chi phí và vận hành. |

## 17. Checklist trước khi tăng cấp mô hình

- [ ] Có baseline và bottleneck được xác định bằng metric thật.
- [ ] Đã biết phần việc độc lập nào có thể thực hiện song song và phần nào bắt buộc tuần tự.
- [ ] Reader, processor, writer và các object dùng chung đã được đánh giá thread safety.
- [ ] Có ranh giới input rõ ràng, không chồng lấn và ổn định khi restart nếu dùng partitioning.
- [ ] Chunk size, thread/worker count và tổng connection pool được cân đối với DB.
- [ ] JobRepository, StepExecution/ExecutionContext và checkpoint đáp ứng yêu cầu khôi phục.
- [ ] Message transport, serialization, retry, timeout và idempotency được kiểm tra nếu dùng mô hình phân tán.
- [ ] Có log/metric theo JobExecution ID, StepExecution ID, partition/chunk và worker.
- [ ] Đã thử dừng worker, rollback, mất kết nối và chạy lại để đối soát dữ liệu.
- [ ] Có số đo throughput, elapsed time, speedup, chi phí tài nguyên và khả năng đáp ứng SLA trước khi quyết định.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao một step chạy bốn thread có thể khó restart hơn bốn partition có reader riêng?**

Multi-threaded step có thể dùng chung reader mutable và các chunk hoàn tất lệch thứ tự, làm checkpoint và đọc lại khó suy luận. Partitioning tách input/StepExecution theo phạm vi ổn định, giúp quản lý riêng trạng thái từng phần. Tuy nhiên partitioning vẫn phải thiết kế chia dữ liệu và retry đúng.

**2. Với 20% thời gian tuần tự, tại sao 16 worker không thể bảo đảm nhanh gấp 16 lần?**

Theo Amdahl, speedup lý tưởng với 16 đơn vị tối đa khoảng 4 lần; thêm overhead và contention còn làm giảm kết quả thực.

**3. Khi nào parallel steps thích hợp hơn partitioning?**

Khi job có nhiều flow nghiệp vụ độc lập, mỗi flow xử lý tập dữ liệu hoặc đầu ra riêng. Partitioning phù hợp hơn khi cần chia **một step hoặc một tập dữ liệu lớn** thành nhiều phần độc lập.

**4. Remote chunking và remote partitioning khác nhau ở chi phí truyền dữ liệu thế nào?**

Remote chunking thường chuyển item/chunk mà manager đã đọc qua broker, nên chịu chi phí payload và bottleneck reader trung tâm. Remote partitioning chuyển thông tin phần việc; worker tự đọc nguồn, giảm tải truyền item nhưng có thể tăng áp lực đọc DB từ nhiều worker.

**5. Vì sao scale từ bốn lên tám worker không làm throughput tăng nếu DB đích đã đạt giới hạn?**

Vì thông lượng toàn pipeline không vượt quá công đoạn chậm nhất. Tăng worker chỉ tăng tốc xử lý ở công đoạn không còn là nút thắt, có thể còn tăng lock và connection contention.

**6. Một job báo COMPLETED sau retry có đủ để kết luận dữ liệu chính xác không?**

Chưa. Cần đối soát bản ghi/khóa nghiệp vụ, kiểm tra side effect ngoài DB, idempotency và tính ổn định của input qua restart.

**7. Có nên chọn mô hình nhiều tiến trình ngay khi dữ liệu đạt 100 triệu dòng?**

Không có ngưỡng số dòng chung cho mọi hệ thống. Cần xét kích thước item, throughput yêu cầu, reader/writer, bottleneck đo được, khả năng phân chia dữ liệu, độ tin cậy và chi phí vận hành.

---

**Ghi nhớ:** Các mô hình song song trong Spring Batch đánh đổi **thời gian chạy** lấy **độ phức tạp điều phối, quản lý trạng thái và xử lý lỗi**. Multi-threaded step tăng concurrency trong một step; parallel steps khai thác các flow độc lập; partitioning chia dữ liệu thành phần việc rõ ràng; các mô hình remote mở rộng qua nhiều JVM nhưng thêm network và vận hành phân tán. Hãy chọn mô hình đơn giản nhất **đã được đo và kiểm chứng** là đáp ứng throughput, tính đúng dữ liệu và yêu cầu restart của workload.
