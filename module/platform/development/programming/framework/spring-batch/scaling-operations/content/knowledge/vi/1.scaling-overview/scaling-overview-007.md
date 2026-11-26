# Chi phí phối hợp giữa các worker trong Spring Batch

## Mục tiêu bài học

Một job xử lý 20 triệu bản ghi có thể tăng tốc khi chạy nhiều worker, nhưng kết quả không tăng tuyến tính theo số worker. Manager phải chia và giao việc, các worker phải lấy dữ liệu và cập nhật trạng thái, hệ thống phải chờ phần việc chậm nhất, xử lý lỗi và kiểm soát tài nguyên chung. Phần thời gian, tài nguyên và độ phức tạp phát sinh từ các hoạt động ấy được gọi chung là **chi phí phối hợp giữa các worker** (*coordination overhead*).

Bài học thuộc chương **Tổng quan scaling** của module **SPRING_BATCH_SCALING_OPERATIONS**, hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán. Chủ đề này kết nối việc chọn kiến trúc với đo bottleneck, thread safety, retry/restart, vận hành và giới hạn tài nguyên thực tế.

Sau bài này, bạn có thể:

- Chỉ ra những hoạt động cần phối hợp khi một JobExecution được chạy qua nhiều thread, step, partition hoặc JVM.
- Phân biệt chi phí phối hợp với thời gian xử lý item và thời gian chờ tài nguyên chung.
- So sánh chi phí trong multi-threaded step, parallel steps, local partitioning, remote chunking và remote partitioning.
- Ước lượng ảnh hưởng của kích thước chunk/partition, số worker, độ lệch tải, độ trễ message và cập nhật JobRepository.
- Đo speedup thực tế và tìm điểm mà tăng concurrency gây phản tác dụng.
- Thiết kế dispatch, backpressure, retry/restart và idempotency để workload tăng quy mô mà vẫn đúng dữ liệu.

## 1. “Phối hợp giữa các worker” thực sự gồm những gì?

Worker là đơn vị thực thi một phần việc. Tùy mô hình Spring Batch, worker có thể là thread đang chạy chunk, worker StepExecution của một partition, một flow độc lập hoặc một JVM từ xa.

Phối hợp là mọi hoạt động **cần có để nhiều đơn vị cùng hoàn thành một công việc logic**:

1. **Chia việc:** xác định item hoặc phạm vi nào thuộc worker nào.
2. **Giao việc:** đưa chunk, yêu cầu thực thi hoặc thông tin partition đến đơn vị xử lý.
3. **Quản lý trạng thái:** tạo, đọc và cập nhật JobExecution, StepExecution, ExecutionContext, checkpoint.
4. **Đồng bộ kết quả:** biết phần việc nào đã hoàn thành, phần nào bị lỗi và khi nào có thể tiếp tục job.
5. **Điều tiết tải:** không cho producer, thread pool hoặc manager cấp thêm việc vượt năng lực worker và DB.
6. **Phục hồi:** xử lý timeout, worker chết, rollback, message gửi lại và restart mà không bỏ sót hoặc ghi trùng dữ liệu.
7. **Quan sát:** liên kết log, metric và trace giữa các thread, process và tài nguyên chia sẻ.

Không phải mọi hoạt động đều cần truyền dữ liệu qua mạng. Trong một JVM, chi phí có thể chủ yếu nằm ở scheduling thread, lock, giao dịch và đồng bộ state. Giữa nhiều JVM, còn có serialization, broker, network, heartbeat/timeout và triển khai nhiều tiến trình.

### Phân biệt ba loại thời gian

| Loại chi phí | Ví dụ | Có giảm khi thêm worker không? |
| --- | --- | --- |
| **Xử lý hữu ích** | Đọc record, tính toán nghiệp vụ, ghi kết quả đúng | Có thể giảm trên critical path nếu chia song song tốt |
| **Phối hợp** | Chia partition, dispatch, lưu metadata, message request/reply, join | Thường tăng theo số phần việc hoặc lượt giao tiếp |
| **Tranh chấp/chờ đợi** | Chờ connection, DB lock, hàng đợi, worker chậm, rate limit | Có thể tăng mạnh khi thêm worker |

Ví dụ một step mất 15 phút không đồng nghĩa 15 phút ấy đều dùng CPU xử lý item. Nếu 6 phút là chờ ghi DB, 3 phút là chờ partition cuối, thì tăng CPU worker sẽ không trực tiếp xử lý được hai khoản chờ đó.

**Ý chính:** song song mang lại lợi ích khi thời gian xử lý hữu ích giảm nhiều hơn chi phí phối hợp và tranh chấp tăng thêm.

## 2. Cơ chế phối hợp xuất hiện ở đâu trong Spring Batch?

Các thành phần Spring Batch liên quan có trách nhiệm khác nhau:

| Thành phần | Vai trò phối hợp |
| --- | --- |
| **JobRepository** | Lưu metadata JobInstance, JobExecution, StepExecution và ExecutionContext để theo dõi và hỗ trợ restart |
| **Job/Step** | Định nghĩa luồng điều khiển, trạng thái hoàn thành và các ranh giới xử lý |
| **TaskExecutor** | Cấp thread để thực thi chunk, flow hoặc partition trong một JVM theo cấu hình |
| **Partitioner** | Tạo tên partition và ExecutionContext mô tả vùng dữ liệu từng worker |
| **PartitionHandler** | Điều phối việc thực thi các partition, tại chỗ hoặc qua cơ chế từ xa |
| **Manager** | Chia, gửi hoặc theo dõi phần việc tùy mô hình |
| **Worker** | Thực thi chunk hoặc worker step; báo/lưu kết quả theo cơ chế điều phối |
| **Message middleware** | Vận chuyển yêu cầu và phản hồi trong các mô hình phân tán dùng messaging |
| **Transaction manager** | Quản lý ranh giới transaction của chunk/step và các resource được cấu hình |

Hình dưới mô tả một trường hợp **remote partitioning** có manager, worker và JobRepository chung:

~~~mermaid
flowchart TB
    M["Manager JVM<br/>Partitioner + PartitionHandler"] --> Q[["Kênh điều phối / broker"]]
    Q --> W1["Worker JVM 1<br/>StepExecution A"]
    Q --> W2["Worker JVM 2<br/>StepExecution B"]
    Q --> W3["Worker JVM 3<br/>StepExecution C"]
    W1 --> D[("DB nguồn/đích")]
    W2 --> D
    W3 --> D
    R[("JobRepository bền vững")] --- M
    R --- W1
    R --- W2
    R --- W3
    W1 -. "trạng thái/response" .-> M
    W2 -. "trạng thái/response" .-> M
    W3 -. "trạng thái/response" .-> M
~~~

Sơ đồ là mô hình khái niệm: chi tiết payload, kênh phản hồi và thứ tự cập nhật metadata phụ thuộc cấu hình Spring Batch/Spring Batch Integration. Không phải mọi mô hình đều có broker; local partitioning thường dùng TaskExecutor và không phải truyền item qua mạng.

### Vì sao metadata cũng có chi phí?

Mỗi partition thường có StepExecution với trạng thái riêng. Khi worker đọc/ghi chunk và checkpoint, hệ thống cần quản lý dữ liệu thực thi bền vững theo cơ chế JobRepository. Nếu chia một tập thành **hàng chục nghìn partition cực nhỏ**, số lượng StepExecution, tạo bean, cập nhật trạng thái và xử lý hoàn tất có thể thành đáng kể.

JobRepository là công cụ bảo đảm khả năng theo dõi/restart, nhưng nó cũng dùng kết nối DB và có giới hạn throughput. Tăng worker không làm metadata store tự tăng năng lực.

## 3. Mô hình toán đơn giản của chi phí phối hợp

Giả sử một công việc có:

- \(T_s\): thời gian bắt buộc tuần tự.
- \(T_p\): thời gian thực hiện phần có thể chia song song trên một worker.
- \(p\): số đơn vị xử lý song song.
- \(T_c(p)\): chi phí phối hợp nằm trên đường thực thi quyết định thời gian hoàn thành.
- \(T_w(p)\): thời gian chờ tài nguyên/worker chậm và ảnh hưởng mất cân bằng tải.
- \(T_f(p)\): chi phí phát sinh vì lỗi, retry hoặc phục hồi.

Một mô hình ước lượng có thể viết:

\[
T_{\mathrm{job}}(p)
\approx T_s + \frac{T_p}{p}
+ T_c(p) + T_w(p) + T_f(p)
\]

Đây là **mô hình suy luận, không phải công thức benchmark chính xác**. Các hoạt động có thể chồng lấn nhau; khi đo cần phân loại thời gian để tránh cộng trùng. Đặc biệt, thời gian chờ DB có thể xảy ra bên trong công đoạn read/write hoặc coordination.

Nếu lý tưởng \(T_c=T_w=T_f=0\), kết quả gần với định luật Amdahl. Nhưng trong hệ thống thật, tăng \(p\) làm \(T_p/p\) giảm trong khi các chi phí còn lại có thể tăng.

### Ví dụ minh họa

Giả sử chạy tuần tự mất **3.720 giây**: 120 giây là phần tuần tự và 3.600 giây là phần có thể phân phối. Với 8 worker, thời gian lý tưởng là:

\[
120 + 3.600/8 = 570\ \mathrm{giây}
\]

Sau khi đo trên môi trường thử, nhóm ước tính thêm 40 giây trên critical path vì khởi tạo/điều phối, 130 giây vì chờ DB và 70 giây do partition cuối quá nặng, thêm 20 giây xử lý lại vì lỗi:

\[
T_{\mathrm{observed}} \approx 570+40+130+70+20=830\ \mathrm{giây}
\]

Speedup thực là:

\[
S(8) = 3.720/830 \approx 4{,}48
\]

Với tám worker, tốc độ chỉ cải thiện khoảng 4,48 lần thay vì 6,53 lần lý tưởng. Các khoản thời gian trong ví dụ **được giả định không chồng lấn để minh họa**; trong đo thực tế chúng phải được gắn timestamp/trace để tránh cộng trùng.

**Parallel efficiency** tham khảo:

\[
E(p)=\frac{S(p)}{p}
\]

Ở đây \(E(8)\approx56\%\). Efficiency không phải tiêu chí duy nhất, nhưng giúp thấy tác động của phần tuần tự, coordination và tài nguyên chung.

## 4. Multi-threaded step: chi phí phối hợp trong một JVM

**Multi-threaded step** dùng TaskExecutor thực thi các chunk của cùng một step trên nhiều thread. Nó thường không cần broker hoặc worker JVM riêng, nên chi phí điều phối mạng thấp, nhưng có các chi phí nội bộ:

- Scheduling và chuyển ngữ cảnh giữa các thread.
- Đồng bộ truy cập ItemReader hoặc các component mutable dùng chung.
- Nhiều transaction/chunk sử dụng connection pool, writer và DB cùng lúc.
- Chunk hoàn tất khác thứ tự đọc; checkpoint/restart cần được kiểm chứng.
- Lock, queue hoặc thread contention khi tạo quá nhiều thread.
- GC và băng thông bộ nhớ của một JVM có thể bị giới hạn.

~~~mermaid
flowchart TB
    S["Một Step trong một JVM"] --> T["TaskExecutor"]
    T --> A["Thread A: chunk 1"]
    T --> B["Thread B: chunk 2"]
    T --> C["Thread C: chunk 3"]
    A --> DB[("DB chung")]
    B --> DB
    C --> DB
~~~

Độ phức tạp dễ bị đánh giá thấp vì việc cấu hình TaskExecutor chỉ mất vài dòng. Nếu reader giữ cursor hoặc vị trí file mutable, việc thêm thread có thể tạo race condition và sai dữ liệu. **Chỉ đồng bộ hóa read không tự bảo đảm checkpoint/restart đúng** khi chunk được commit lệch thứ tự.

**Chiến lược:** dùng số thread vừa đủ, đánh giá thread safety ở reader/processor/writer, đo connection wait và rollback, đồng thời cân nhắc partitioning nếu dữ liệu có thể chia thành những vùng độc lập.

## 5. Parallel steps: chi phí phối hợp nằm ở điểm join

**Parallel steps** chạy nhiều flow/step độc lập qua cơ chế split với TaskExecutor. Mỗi flow có logic và metadata step riêng; chi phí chính thường là:

- Xác định dependency đúng giữa các flow.
- Khởi tạo và vận hành nhiều flow cùng lúc.
- Chia tài nguyên DB/CPU với các step khác.
- Chờ nhánh chậm nhất tại điểm đồng bộ (*join*).
- Xác định trạng thái fail/restart nếu một nhánh thành công nhưng nhánh khác lỗi.

~~~mermaid
flowchart TB
    J[Job start] --> X[Split]
    X --> F1["Flow A: 8 phút"]
    X --> F2["Flow B: 2 phút"]
    X --> F3["Flow C: 5 phút"]
    F1 --> G[Join/tiếp tục]
    F2 --> G
    F3 --> G
    G --> Z[Step tổng hợp]
~~~

Nếu các flow độc lập và chạy đồng thời đủ tài nguyên, thời gian đến điểm join xấp xỉ **max(8, 2, 5) = 8 phút** cộng overhead. Chạy tuần tự ba flow mất khoảng 15 phút. Nhưng tăng thêm thread không làm Flow A từ 8 phút giảm xuống nếu bản thân nó không được song song hóa.

**Khi nên chọn:** các nhánh nghiệp vụ độc lập rõ ràng. Không dùng parallel steps để chạy các step có phụ thuộc dữ liệu trực tiếp mà chưa xác định điều kiện kết thúc/đồng bộ.

## 6. Local partitioning: thêm StepExecution, giảm chia sẻ reader

Với **local partitioning**, manager tạo Map gồm **partition name → ExecutionContext**. PartitionHandler chạy các worker StepExecution trên các thread trong cùng JVM. Mỗi worker có input và checkpoint riêng, ví dụ range ID hoặc danh sách file.

Đổi lại, hệ thống phải:

- Tính ranh giới partition đủ và không chồng lấn.
- Tạo/quản lý metadata riêng cho từng StepExecution.
- Khởi tạo reader, processor, writer theo vòng đời phù hợp.
- Phân phối partition lên thread đang rảnh.
- Chờ worker chậm nhất và tổng hợp status.
- Giữ partition name/input ổn định qua restart.

Ví dụ 8 triệu bản ghi chia thành 8 partition. Nếu bảy partition xử lý 10 giây nhưng partition thứ tám mất 90 giây, thời gian chờ hoàn tất nhóm vẫn bị partition thứ tám chi phối. Chi phí phối hợp từ **mất cân bằng tải** có thể lớn hơn cả thời gian khởi tạo và metadata.

**Lợi ích:** khi mỗi partition có reader @StepScope theo ExecutionContext riêng, tránh được việc chia sẻ một con trỏ đọc mutable. Do đó, mặc dù cần thêm Partitioner và metadata, logic về ranh giới dữ liệu/restart thường rõ hơn so với một reader stateful chia sẻ giữa nhiều thread.

### Partition name có giá trị vận hành

Tên **partition-0**, **partition-1**... là định danh mà hệ thống dùng để gắn trạng thái StepExecution với phần việc. Nếu restart cùng JobInstance mà cách chia và tên partition thay đổi tùy ý, có nguy cơ dữ liệu đầu vào mới không còn khớp checkpoint của phần việc cũ.

Chốt high-watermark/snapshot và cách chia trước khi chạy; kiểm tra tính ổn định khi restart. Không lấy MAX(id) mới cho mỗi worker rồi thay đổi phạm vi trong cùng lần xử lý logic.

### Ví dụ local partitioning: số partition và số thread là hai tham số

Ví dụ Java DSL Spring Batch 5.x dưới đây chia miền ID cố định thành nhiều partition, trong khi TaskExecutor có thể chỉ có bốn thread xử lý đồng thời:

~~~java
@Bean
public Partitioner orderRangePartitioner() {
    return gridSize -> {
        int count = Math.max(1, gridSize);
        long total = 1_000_000L;
        long width = (total + count - 1) / count;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (int i = 0; i < count; i++) {
            long minId = 1L + i * width;
            if (minId > total) {
                break;
            }
            long maxExclusive = Math.min(total + 1, minId + width);
            ExecutionContext input = new ExecutionContext();
            input.putLong("minIdInclusive", minId);
            input.putLong("maxIdExclusive", maxExclusive);
            result.put("partition-" + i, input);
        }
        return result;
    };
}

@Bean
public Step localManagerStep(
        JobRepository jobRepository,
        @Qualifier("workerStep") Step workerStep,
        Partitioner orderRangePartitioner,
        @Qualifier("partitionExecutor") TaskExecutor partitionExecutor) {
    return new StepBuilder("managerStep", jobRepository)
            .partitioner("workerStep", orderRangePartitioner)
            .step(workerStep)
            .gridSize(12)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

Ví dụ giả định đã có các import, bean workerStep, partitionExecutor và hạ tầng Spring Batch tương ứng. Worker reader cần dùng **@StepScope**, nhận các giá trị minIdInclusive/maxIdExclusive qua **stepExecutionContext** và chỉ đọc miền ID đó. Cấu hình **gridSize(12)** chỉ truyền độ lớn lưới dự kiến cho Partitioner; số worker thực thi đồng thời do executor và hạ tầng giới hạn. Nếu partitionExecutor có bốn thread, có thể có 12 phần việc nhưng chỉ tối đa khoảng bốn worker step chạy đồng thời. Manager còn phải theo dõi cả 12 StepExecution, vì vậy tăng partition sẽ phát sinh thêm chi phí quản lý ngay cả khi số thread không tăng.

## 7. Remote chunking: chi phí chuyển item qua mạng

Trong **remote chunking**, manager thường đọc item, tạo chunk và gửi qua middleware cho các worker xử lý/ghi, rồi nhận phản hồi. Đây là mô hình có chi phí phối hợp **theo số chunk và kích thước dữ liệu vận chuyển**.

~~~mermaid
flowchart LR
    SRC[("Nguồn")] --> M["Manager JVM<br/>read + tạo chunk"]
    M --> Q[["Broker / message channel"]]
    Q --> W1["Worker JVM A<br/>process/write"]
    Q --> W2["Worker JVM B<br/>process/write"]
    W1 --> DEST[("Đích")]
    W2 --> DEST
    W1 -. "response" .-> M
    W2 -. "response" .-> M
~~~

Các khoản chi phí:

1. **Serialize/deserialize** item và payload chunk.
2. **Gửi message/nhận phản hồi**, network latency, broker throughput và persistence tùy middleware.
3. **Ghi nhận ack, retry, timeout**, quản lý message lỗi/đến trễ.
4. **Điều tiết inflight** khi manager đọc nhanh hơn worker ghi.
5. **Quản lý phiên bản payload** giữa manager và worker.
6. **Trần reader trung tâm:** mọi item đầu vào vẫn đi qua manager.

### Số message tăng theo commit interval

Trong kịch bản đơn giản không lỗi và mỗi chunk mang tối đa \(c\) item, số chunk khoảng:

\[
N_{\mathrm{chunks}} \approx \left\lceil\frac{N}{c}\right\rceil
\]

Với 2 triệu item:

| Chunk size | Chunk request xấp xỉ | Ý nghĩa |
| ---: | ---: | --- |
| 100 | 20.000 | Nhiều lượt điều phối/message |
| 500 | 4.000 | Ít request hơn |
| 1.000 | 2.000 | Payload mỗi request lớn hơn |
| 5.000 | 400 | Ít request nhưng payload/retry có thể quá lớn |

Số message thực tế còn có response, lỗi, retry và protocol metadata. **Không** coi số chunk bằng tổng message của hệ thống.

Nếu một item được serialize thành 2 KiB, chunk 1.000 item có dữ liệu thô khoảng **1,95 MiB**, chưa tính metadata và overhead. Kích thước này có thể vượt giới hạn message của một số hạ tầng hoặc gây allocation/GC lớn; cần đo hoặc kiểm tra cấu hình thực tế của broker.

### Khi nào remote chunking hợp lý?

Reader ở manager đủ nhanh, item không quá lớn để gửi qua mạng và phần process/write tốn tài nguyên hơn read. Nếu manager chỉ đọc được 5.000 item/s, thêm worker có tổng năng lực 30.000 item/s không tự làm read throughput tăng tới 30.000 item/s.

## 8. Remote partitioning: chi phí điều phối theo partition

Trong **remote partitioning**, manager tạo partition và đưa yêu cầu thực thi tới worker JVM. Worker tự đọc phạm vi dữ liệu của mình theo StepExecution/ExecutionContext. Manager **không gửi toàn bộ item** qua broker như remote chunking.

Chi phí phối hợp thường gắn với:

- Tạo/lưu StepExecution cho từng partition.
- Dispatch yêu cầu và nhận/truy xuất kết quả.
- Worker tải metadata, tạo bean @StepScope và quản lý transaction/checkpoint.
- Quản lý worker chậm, bị lỗi hoặc không còn kết nối.
- JobRepository dùng chung theo kiến trúc triển khai.
- Phiên bản message, serializer/context và danh tính step.

Chi phí truyền dữ liệu **trên kênh điều phối** thường nhỏ hơn remote chunking nếu chỉ gửi định danh/mô tả phần việc. Nhưng **tổng tải DB nguồn** có thể lớn hơn do mỗi worker tự mở kết nối và thực thi query.

### Local và remote partitioning khác ở đâu?

| Tiêu chí | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Worker thực thi | Thread trong cùng JVM | JVM/process riêng |
| Giao việc | PartitionHandler và TaskExecutor nội bộ | PartitionHandler/cơ chế điều phối từ xa |
| Dữ liệu truyền trên mạng để giao việc | Thường không cần | Có yêu cầu/response hoặc metadata theo giao thức |
| Metadata | Các worker StepExecution | Các worker StepExecution, cần chia sẻ/đồng bộ đúng giữa process |
| Khi worker ngừng | Lỗi thread/step; JVM chết ảnh hưởng toàn bộ process | Một JVM có thể chết riêng; cần timeout và phục hồi |
| Scale tài nguyên | CPU/heap trong một host/JVM | Có thể trải ra nhiều host |
| Chi phí đặc trưng | Scheduling, shared pool, metadata | Thêm network, worker lifecycle, triển khai và metadata |

**Điểm dễ nhầm:** remote partitioning **không** làm một database nguồn tự nhanh hơn. Nếu 12 worker cùng query một bảng chưa được index phù hợp, DB có thể bão hòa, và tổng job còn chậm hơn local partitioning với bốn thread.

## 9. Kích thước phần việc: quá nhỏ và quá lớn đều có giá

Kích thước chunk hoặc partition quyết định tỷ lệ giữa **công việc hữu ích** và **chi phí cấp phát/điều phối**.

Giả sử một worker lặp lại các phần việc, mỗi phần cần \(t_{\mathrm{work}}\) giây xử lý và \(t_{\mathrm{coord}}\) giây phối hợp nằm trên đường thực thi của worker. Tỷ lệ chi phí trong mô hình đơn giản:

\[
f_{\mathrm{coord}} =
\frac{t_{\mathrm{coord}}}{t_{\mathrm{work}}+t_{\mathrm{coord}}}
\]

Ví dụ giả định chi phí phối hợp cho một phần việc là **0,5 giây**:

| Thời gian xử lý hữu ích/phần | Phối hợp/phần | Tỷ lệ phối hợp |
| ---: | ---: | ---: |
| 0,1 giây | 0,5 giây | 83,3% |
| 1 giây | 0,5 giây | 33,3% |
| 5 giây | 0,5 giây | 9,1% |
| 30 giây | 0,5 giây | 1,6% |

Số liệu chỉ minh họa, không phải chi phí mặc định của Spring Batch. Trên nhiều worker, một số thao tác có thể chồng lấn nên không được lấy tổng overhead mọi phần việc làm **wall-clock overhead** chính xác.

Nếu partition quá nhỏ, hệ thống tốn nhiều lần tạo reader, giao việc, cập nhật StepExecution và kết thúc partition. Nếu quá lớn, worker chậm có thể giữ toàn job; rollback và restart mất nhiều công, khó cân bằng tải.

### Quy tắc chọn kích thước

- Thời gian thực thi mỗi partition nên đủ lớn để amortize chi phí dispatch/khởi tạo.
- Số partition có thể **lớn hơn số worker** để worker rảnh xử lý phần tiếp theo và giảm lệch tải.
- Không để quá nhiều partition nhỏ làm metadata/broker trở thành bottleneck.
- Chunk size bên trong worker cần được tune riêng với partition size: một partition có thể chứa hàng nghìn chunk.
- Cân nhắc độ dài tối đa chấp nhận được khi một partition thất bại và phải chạy lại.

Không có một tỷ lệ partition/worker hoặc một thời gian partition tối ưu cho mọi job. Cần đo thông lượng và độ phân tán thời gian xử lý từng partition.

## 10. Mất cân bằng tải và worker chậm nhất

Trong thực tế, dữ liệu không phân bố đều. Một partition chứa 200.000 đơn hàng nhỏ, partition khác chứa 200.000 đơn hàng phải gọi dịch vụ tính thuế chậm; số record bằng nhau nhưng thời gian khác nhau.

Với một đợt partition chạy song song, thời gian hoàn tất thường gần với **thời gian partition cuối cùng hoàn thành**, chứ không phải thời gian trung bình.

~~~mermaid
flowchart TB
    M[Manager giao bốn partition] --> A["Worker A: 2 đơn vị thời gian"]
    M --> B["Worker B: 3 đơn vị thời gian"]
    M --> C["Worker C: 2 đơn vị thời gian"]
    M --> D["Worker D: 9 đơn vị thời gian"]
    A --> J["Join chỉ hoàn tất ở mốc 9"]
    B --> J
    C --> J
    D --> J
~~~

Sơ đồ thể hiện ba worker hoàn tất sớm và một worker giữ toàn bộ nhóm tới đơn vị thời gian 9 (thời gian mang tính minh họa). Đơn giản thêm worker có thể không cứu được trường hợp partition lớn không thể chia tiếp.

### Cách hạn chế straggler

- Chia thành **nhiều partition vừa phải hơn số worker** để tạo cơ hội cân bằng động.
- Chọn partition key dựa trên lượng record hoặc chi phí xử lý, không chỉ chia đều khoảng ID.
- Theo dõi read/write count và thời gian theo từng partition.
- Chia riêng tenant hoặc file có tải bất thường.
- Với workload có phụ thuộc đặc biệt, xác định phần nào không thể chạy song song mà không phá vỡ thứ tự/tính nhất quán.

Cần phân biệt **worker chậm do dữ liệu nặng** với **worker chậm do hạ tầng** như CPU throttling, GC, disk hay connection wait. Chẩn đoán sai có thể dẫn tới chia thêm partition nhưng vẫn không giải quyết điểm nghẽn.

## 11. JobRepository và connection pool là tài nguyên chung

Nhiều worker không chỉ đọc/ghi dữ liệu nghiệp vụ. Chúng còn cần metadata của Spring Batch để theo dõi trạng thái và restart. Trong remote partitioning, các thành phần liên quan thường phải dùng repository bền vững và truy cập nhất quán StepExecution.

### Vì sao metadata store có thể thành bottleneck?

Mỗi partition và chunk có thể phát sinh cập nhật metadata/checkpoint theo vòng đời do framework quản lý. Khi tăng số partition, số worker và tần suất commit, tổng tải lên JobRepository cũng tăng. Chi phí gồm:

- Thời gian tạo, cập nhật StepExecution và ExecutionContext.
- Connection acquisition, transaction của metadata và I/O.
- Tranh chấp cập nhật trạng thái hoặc phiên bản metadata.
- Chi phí serialize trạng thái; context quá lớn hoặc chứa đối tượng phức tạp làm vấn đề nặng thêm.
- Thời gian manager tổng hợp trạng thái nhiều worker.

Điều này **không có nghĩa** mỗi item đều được ghi riêng xuống JobRepository. Tần suất thực tế phụ thuộc chunk, transaction, reader state, phiên bản Spring Batch và cấu hình repository.

**Nguyên tắc:** ExecutionContext giữ thông tin điều khiển nhỏ và state checkpoint cần thiết. Không lưu toàn bộ hàng triệu item vào context để truyền dữ liệu cho worker.

### Tính tổng connection pool

Ví dụ manager và 6 worker JVM, mỗi worker cấu hình pool tối đa 12 kết nối, manager tối đa 8 kết nối:

\[
6\times12+8=80\ \mathrm{connections}
\]

Đây là **tổng hạn mức cấu hình**, không phải số kết nối đang sử dụng thực tế. DB còn phục vụ ứng dụng khác, và một số thành phần có thể dùng pool khác nhau cho business DB/JobRepository. Khi giám sát, cần đo active/idle/waiting connections ở từng pool và giới hạn toàn database.

Nếu DB chỉ chịu được mức concurrency thấp hơn, tăng worker có thể làm thời gian chờ connection hoặc lock tăng, giảm throughput và làm retry nhiều hơn.

## 12. Backpressure: điều tiết khi producer nhanh hơn consumer

Giả sử manager tạo phần việc với tốc độ **4.000 item/s**, trong khi worker và DB đích chỉ xử lý được **3.000 item/s**. Nếu có queue trung gian cho phép tồn đọng, backlog tăng gần:

\[
4.000-3.000=1.000\ \mathrm{item/s}
\]

Sau một phút, có thể còn **60.000 item** chờ nếu tốc độ giữ nguyên. Trong remote chunking, backlog có thể xuất hiện dưới dạng message/chunk chưa được xử lý; cần quy đổi số item/message khi xem queue depth.

Nếu mỗi chunk chứa 200 item, chênh lệch tạo thành khoảng **5 chunk/s** bổ sung vào backlog theo giả định trên. Queue có capacity 500 chunk sẽ đầy sau khoảng **100 giây** nếu bắt đầu rỗng, không có thay đổi tốc độ và chỉ chênh lệch ấy là nguyên nhân tăng queue.

### Biện pháp backpressure

- Giới hạn số chunk hoặc partition được giao đồng thời (*inflight work*).
- Giới hạn worker concurrency, thread pool và số transaction DB.
- Dùng queue có giới hạn, xác định rõ hành vi khi full.
- Điều tiết manager/producer khi broker lag hoặc write latency vượt ngưỡng.
- Retry có backoff và giới hạn, tránh tạo retry storm.
- Giám sát queue age và thời gian hoàn tất, không chỉ độ sâu hàng đợi.

Trong chunk-oriented step đồng bộ không có queue trung gian vô hạn, vòng read/process/write thường tự tạo mức điều tiết; không nên áp mô hình backlog của broker lên mọi step mà không xét kiến trúc.

**Little's law** mô tả hệ thống ổn định:

\[
L=\lambda W
\]

Với \(L\) là số công việc trung bình trong hệ thống, \(\lambda\) là tốc độ hoàn tất trung bình và \(W\) là thời gian lưu lại trung bình. Nếu throughput là 200 request/s, thời gian mỗi request trung bình 0,1 giây, số request trung bình đang tồn tại khoảng **20**. Công thức giúp suy luận về concurrency cần thiết nhưng không bảo đảm hệ thống đích có thể phục vụ 200 request/s; khi quá tải, latency có thể tăng rất nhanh.

## 13. Retry, restart và idempotency làm thay đổi chi phí phối hợp

Một hệ thống phân tán phải tính tới tình huống **worker hoàn thành công việc nhưng manager chưa biết**.

Ví dụ:

1. Manager giao partition P3 cho worker.
2. Worker đọc dữ liệu, ghi chunk và commit DB.
3. Kết nối bị gián đoạn trước khi trạng thái/response hoàn tất tới manager.
4. Manager hoặc cơ chế restart phát hiện phần việc chưa xác định kết quả.
5. Phần việc có thể cần kiểm tra metadata và được thử lại theo chính sách.

Nếu writer không idempotent, phần dữ liệu đã commit có thể được ghi trùng. Metadata và ack có vai trò quan trọng nhưng không tự biến một giao dịch DB và một message xác nhận thành một giao dịch nguyên tử.

### Chi phí của retry

Retry làm tăng:

- Số lần đọc/ghi và giao dịch.
- Lượng CPU, network và broker traffic.
- Thời gian giữ tài nguyên và contention với worker khác.
- Số bước điều tra lỗi và đối soát.
- Thời gian hoàn thành tới trạng thái cuối cùng.

Một mô hình benchmark chỉ đo lần chạy **không lỗi** sẽ bỏ qua chi phí này. Chỉ cần vài partition lớn phải chạy lại cũng có thể xóa hết lợi ích tăng tốc thu được nhờ thêm worker.

### Thiết kế để phục hồi an toàn

- Dùng unique business key hoặc upsert có ngữ nghĩa đúng khi phù hợp.
- Dùng idempotency key với API ngoài nếu được hỗ trợ.
- Với side effect qua DB và message, cân nhắc transactional outbox hoặc cơ chế phối hợp phù hợp.
- Cố định high-watermark/snapshot và ranh giới partition qua restart.
- Đảm bảo ItemReader/ItemWriter/ItemStream xử lý checkpoint đúng.
- Phân loại lỗi retryable và non-retryable, có giới hạn/backoff.
- Theo dõi StepExecution ID, partition name, attempt và kết quả đối soát.

**Chỉ số cần quan sát:** số lượt retry, rollback, phần việc chạy lại, thời gian phục hồi và số business key cuối kỳ; không chỉ throughput khi job báo COMPLETED.

## 14. Đo chi phí phối hợp như thế nào?

Đừng tạo một metric chung “coordination time” rồi phỏng đoán. Nên đo những mốc có thể kiểm chứng:

| Mốc / metric | Câu hỏi giải đáp |
| --- | --- |
| **Partition creation duration** | Manager mất bao lâu để chốt phạm vi và tạo partition? |
| **Dispatch latency** | Từ lúc yêu cầu sẵn sàng tới khi worker nhận việc mất bao lâu? |
| **Worker startup latency** | Worker mất bao lâu để tải StepExecution, tạo bean và bắt đầu đọc? |
| **Queue age / broker lag** | Công việc nằm chờ bao lâu vì thiếu worker hoặc nghẽn broker? |
| **Chunk duration** | Một chunk hoàn tất read/process/write/commit mất bao lâu? |
| **Read/write throughput** | Có tăng công việc hữu ích không hay chỉ tăng số request? |
| **JobRepository latency** | Metadata load/save/update có chậm khi nhiều partition? |
| **Connection wait/lock wait** | Worker chậm vì DB dùng chung hay vì tính toán? |
| **Partition elapsed time** | Có một vài straggler giữ job ở điểm join không? |
| **Retry/rollback rate** | Phối hợp và contention có gây thêm lỗi không? |
| **End-to-end job time** | Toàn bộ thay đổi có thực sự rút ngắn thời gian hoàn thành? |

### Định danh để nối sự kiện

Log/trace nên có thông tin:

~~~text
jobExecutionId=5812
stepExecutionId=6021
partition=orders-2026-11-25-03
worker=worker-jvm-04
dispatchLatencyMs=17
startupLatencyMs=49
chunkSize=500
readCount=125000
writeCount=125000
rollbackCount=0
status=COMPLETED
~~~

Các giá trị trên là ví dụ. Nên thống nhất correlation ID qua manager và worker, hạn chế ghi dữ liệu nhạy cảm và kiểm soát cardinality của nhãn metric (không đưa mọi ID động làm label có số giá trị không giới hạn).

### Phân tích trước và sau khi thêm worker

Một phép so sánh nên giữ nguyên dataset, code, DB/index, chunk size và cấu hình pool. Thay số worker từ 2 lên 4 rồi quan sát:

- Tổng throughput tăng bao nhiêu?
- Dispatch latency/queue age có tăng không?
- p95/p99 thời gian chunk và connection wait thay đổi thế nào?
- Thời gian partition cuối hoàn tất giảm hay đứng yên?
- Số retry/rollback tăng không?
- Chi phí CPU/RAM/broker và tài nguyên DB có chấp nhận được không?

Đo **tổng elapsed time** là quan trọng nhất; metric chi tiết giải thích vì sao nó thay đổi.

## 15. Benchmark điểm bão hòa của số worker

Bảng dưới đây là **số liệu giả định** cho cùng một tập input và cùng nghiệp vụ. Mục đích là minh họa cách đọc dấu hiệu chi phí phối hợp tăng.

| Worker | Write throughput | p95 dispatch latency | DB connection wait | Speedup theo throughput |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1.500 item/s | 1 ms | Thấp | 1,00× |
| 2 | 2.700 item/s | 2 ms | Thấp | 1,80× |
| 4 | 4.200 item/s | 8 ms | Trung bình | 2,80× |
| 8 | 4.700 item/s | 35 ms | Cao | 3,13× |
| 16 | 4.100 item/s | 120 ms | Rất cao | 2,73× |

Giá trị **speedup theo throughput** chỉ so sánh có ý nghĩa khi cùng kiểu dữ liệu, số lượng và định nghĩa item. Với tám worker, hiệu suất tham khảo khoảng \(3{,}13/8\approx39\%\). Thêm từ 8 lên 16 worker làm throughput **giảm**, đồng thời dispatch và connection wait tăng.

Các khả năng cần điều tra:

- DB đã sát giới hạn connection/CPU/lock.
- Manager hoặc broker không cấp việc nhanh hơn.
- Metadata update trở thành phần đáng kể.
- Partition quá nhỏ hoặc có straggler.
- Retry/timeouts gây thêm công việc không hữu ích.

Kết luận thực nghiệm phải dựa trên metric đủ chi tiết; từ một bảng như trên chưa thể biết chắc thủ phạm là DB hay broker. Nhưng có thể nói rằng **16 worker không đem lại lợi ích throughput trong giả định ấy**.

### Một quy trình benchmark có kiểm soát

1. Chốt dữ liệu đầu vào, business key và cách đối soát output.
2. Đo baseline một worker; tối ưu query, index, writer và commit interval trước.
3. Tăng worker theo nấc 1 → 2 → 4 → 8 khi tài nguyên cho phép.
4. Giữ chunk size và số partition hợp lý, thay **một biến tại một thời điểm**.
5. Ghi metric ứng dụng, JobRepository, DB, broker và hệ thống ngoài.
6. Thử kill worker giữa chunk, timeout và restart để đo chi phí phục hồi.
7. Chọn vùng đạt SLA với dự phòng tài nguyên, ít rollback và dễ vận hành.

## 16. Tình huống thực tế: 12 triệu đơn hàng trong 20 phút

Một doanh nghiệp muốn xử lý **12.000.000 đơn hàng** trong 20 phút sau khi đóng cửa sổ dữ liệu. Mức throughput đầu vào trung bình tối thiểu:

\[
R_{\mathrm{required}} =
\frac{12.000.000}{20\times60}
=10.000\ \mathrm{item/s}
\]

Để có dư địa cho khởi tạo, retry và bước tổng hợp, cần năng lực cao hơn mức lý tưởng này.

### Giai đoạn 1 — Đo giới hạn nguồn/đích

Giả sử benchmark cho kết quả:

| Thành phần | Năng lực đo được |
| --- | ---: |
| DB nguồn đọc qua nhiều range ID | 15.000 item/s |
| Mỗi worker JVM xử lý nghiệp vụ | 2.500 item/s |
| DB đích ghi với cấu hình ban đầu | 9.000 item/s |
| DB đích sau khi tối ưu batch write | 12.500 item/s |

Các số liệu là **giả định**, không phải benchmark thực tế của Spring Batch. Nếu một input tạo một output, với 6 worker năng lực xử lý lý thuyết là **15.000 item/s**. Khi DB đích mới chỉ ghi 9.000 item/s, trần toàn pipeline theo mô hình không vượt 9.000 item/s; tăng worker chưa thể đáp ứng SLA.

### Giai đoạn 2 — Tối ưu đích rồi chọn remote partitioning

Sau khi tối ưu batch write và query/index phù hợp, đích đạt 12.500 item/s. Khi đó cận trên lý tưởng:

\[
R_{\mathrm{job}}
\leq\min(15.000,\ 6\times2.500,\ 12.500)
=12.500\ \mathrm{item/s}
\]

Thời gian lý tưởng để xử lý 12 triệu item:

\[
T_{\mathrm{ideal}}\geq
12.000.000/12.500 = 960\ \mathrm{giây}
=16\ \mathrm{phút}
\]

Còn khoảng 4 phút trước SLA để gánh overhead, tải dao động và lỗi. Chia khoảng 120 partition, trung bình 100.000 item/partition, cho 6 worker có thể là một điểm bắt đầu benchmark nếu dữ liệu phân bố đủ đều.

**Vì sao remote partitioning?** Mỗi worker tự đọc range ID nên manager chỉ gửi yêu cầu phân công; phù hợp khi nguồn hỗ trợ nhiều reader và một JVM không đủ CPU. Tuy nhiên cần kiểm tra nguồn chịu được tổng 6 worker và các partition không tạo full scan.

### Giai đoạn 3 — Đo chi phí phối hợp

Giả sử tổng thời gian hữu ích gần trần là 16 phút, còn dispatch/startup, straggler và contention đưa thời gian đo thực tế lên **18 phút**. Đây là giả định minh họa; phần chênh 2 phút phải được truy dấu trước khi quy cho riêng coordination.

Nếu tăng từ 6 lên 12 worker nhưng DB đích vẫn tối đa 12.500 item/s, phần xử lý worker dư thừa chỉ làm tăng khả năng tranh chấp. Cách có ích hơn có thể là cân bằng partition, giảm metadata overhead hoặc tiếp tục tối ưu đích.

### Giai đoạn 4 — Kiểm tra phục hồi

Kill một worker khi xử lý, sau đó restart partition chưa hoàn tất. Kiểm tra rằng:

- Không bỏ sót hoặc ghi trùng business key.
- Ranh giới partition và high-watermark không bị thay đổi.
- Metadata StepExecution phản ánh đúng trạng thái.
- Tổng thời gian phục hồi có thể được dự báo và đáp ứng SLA vận hành.
- Queue/DB connection trở lại ổn định, không tạo retry storm.

Trường hợp này minh họa rằng **chi phí phối hợp là biến phải đo cùng với giới hạn dữ liệu và CPU**. Giá trị của multi-process nằm ở khả năng hoàn thành đúng, ổn định trong thời hạn, không phải số worker lớn nhất.

## 17. Chọn mô hình theo mức chi phí chấp nhận được

| Nhu cầu/bottleneck | Mô hình nên xem xét | Chi phí phối hợp cần kiểm tra |
| --- | --- | --- |
| Một step có chunk độc lập, JVM còn dư, component an toàn luồng | Multi-threaded step | State dùng chung, scheduling, connection, checkpoint |
| Các nhánh nghiệp vụ riêng biệt | Parallel steps | Dependency, điểm join, flow chậm nhất |
| Một dataset chia được theo ID/file/tenant, một JVM đủ CPU | Local partitioning | Partitioner, StepExecution, lệch tải |
| Manager đọc nhanh, process/write nặng, payload item vừa phải | Remote chunking | Serialization, broker, request/reply, queue, idempotency |
| Một JVM thiếu CPU/RAM, worker tự đọc range độc lập | Remote partitioning | Dispatch, metadata dùng chung, worker lifecycle, DB contention |
| DB/API nguồn hoặc đích đã bão hòa | Tối ưu đọc/ghi trước khi tăng worker | Query/index, batching, lock, quota, pool |

**Các quyết định thực tế:**

- Nếu worker đa số chờ DB, tăng số worker chưa chắc hữu ích.
- Nếu manager/broker chậm khi giao nhiều chunk nhỏ, tăng kích thước phần việc trong giới hạn payload/retry có thể giúp.
- Nếu worker cuối kéo dài job, cân bằng partition có thể hiệu quả hơn nhân thêm process.
- Nếu rollback tăng theo concurrency, kiểm tra transaction, lock và idempotency trước.
- Nếu JobRepository trở thành nút thắt, giảm số partition quá nhỏ và đánh giá hạ tầng metadata.
- Nếu SLA đã đạt ổn định, cân nhắc chi phí vận hành trước khi thêm độ phức tạp phân tán.

## 18. Những nhầm lẫn thường gặp

| Nhận định | Điều cần hiểu |
| --- | --- |
| “Tăng worker từ 4 lên 8 sẽ nhanh gấp đôi.” | Phần tuần tự, coordination và tài nguyên chung giới hạn speedup. |
| “Không qua mạng thì không có chi phí phối hợp.” | Thread scheduling, lock, transaction, StepExecution và join vẫn có chi phí. |
| “Remote partitioning luôn ít overhead hơn remote chunking.” | Khác biệt phụ thuộc số partition, tải DB, broker, metadata và kích thước item. |
| “Chia càng nhiều partition càng cân bằng tốt.” | Quá nhiều partition rất nhỏ làm tăng khởi tạo, dispatch và metadata. |
| “Partition bằng số ID thì chắc có tải bằng nhau.” | Dữ liệu có khoảng trống hoặc item nặng nhẹ khác nhau. |
| “Queue dài cho thấy hệ thống tận dụng worker tốt.” | Backlog lớn có thể chỉ là producer vượt consumer và latency tăng. |
| “Đã ack message thì chắc chắn ghi đúng một lần.” | Ack có thể không atomic với commit DB; vẫn cần idempotency. |
| “TaskExecutor biến job thành multi-process.” | Thread trong cùng JVM vẫn là single-process. |
| “JobRepository không ảnh hưởng hiệu năng vì chỉ giữ trạng thái.” | Metadata cũng cần I/O, connection, transaction và có trần throughput. |
| “Worker chết chỉ việc chạy lại toàn bộ partition.” | Cần xét checkpoint, input ổn định, writer idempotent và side effect. |
| “Thấy CPU rảnh thì nên thêm worker.” | Worker có thể đang chờ DB, mạng, lock hoặc rate limit. |
| “Đo throughput happy path là đủ.” | Recovery time và tính đúng sau lỗi cũng là điều kiện của scaling. |

## 19. Checklist trước khi tăng số worker

- [ ] Có baseline tuần tự và bottleneck đã được đo.
- [ ] Đã phân biệt CPU processing, coordination, DB wait và queue wait.
- [ ] Component dùng chung được đánh giá thread safety.
- [ ] Có ranh giới partition/input không chồng lấn, ổn định qua restart nếu chia dữ liệu.
- [ ] Kích thước chunk/partition đủ để giảm overhead nhưng không quá lớn khi rollback.
- [ ] Tổng connection pool và transaction đồng thời phù hợp database.
- [ ] JobRepository chịu được số StepExecution và cập nhật checkpoint.
- [ ] Nếu phân tán, broker, serialization, queue capacity và timeout được đo/giới hạn.
- [ ] Có backpressure và retry/backoff để tránh producer hoặc retry làm nghẽn đích.
- [ ] Có metric theo JobExecution ID, StepExecution ID, partition/chunk và worker.
- [ ] Đo thời gian partition chậm nhất, không chỉ thời gian trung bình.
- [ ] Đã thử kill worker, mất kết nối, rollback và restart.
- [ ] Writer idempotent và có đối soát business key.
- [ ] Scale được xác nhận bằng end-to-end elapsed time, SLA và chi phí tài nguyên.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao một job có 16 worker vẫn có thể chậm hơn tám worker?**

Vì có thể tăng DB connection wait, lock contention, metadata I/O, broker queue và retry. Khi tài nguyên chung bão hòa, thêm worker chỉ làm tăng hàng chờ và số transaction cạnh tranh.

**2. Khi remote chunking dùng chunk rất nhỏ, khoản coordination nào tăng?**

Số request/response, serialization, broker operations và việc theo dõi chunk tăng. Chunk quá lớn lại tăng payload, memory và chi phí retry, nên cần tìm điểm cân bằng qua benchmark.

**3. Với local partitioning, vì sao nhiều StepExecution được tạo dù chỉ có một JVM?**

Mỗi partition là phần việc độc lập với ExecutionContext và trạng thái/checkpoint riêng. Số worker thread đồng thời không nhất thiết bằng tổng số partition.

**4. Làm sao nhận biết straggler?**

Ghi thời gian thực thi, số item và trạng thái theo partition. Nếu đa số partition đã hoàn thành nhưng một số ít vẫn chạy lâu, chúng có thể quyết định thời gian job; cần phân biệt do dữ liệu lệch hay hạ tầng chậm.

**5. Khi một worker commit thành công rồi mất xác nhận, vì sao retry có thể tạo dữ liệu sai?**

Nếu manager không biết chắc kết quả, phần việc có thể được thực hiện lại. Writer không idempotent có thể tạo bản ghi trùng hoặc cộng dồn hai lần; cần khóa nghiệp vụ, checkpoint và chính sách phục hồi đúng.

**6. Khi nguồn đọc chỉ phục vụ 8.000 item/s, có nên tăng số worker xử lý lên gấp ba?**

Chỉ có ích nếu chính phần xử lý là nút thắt trước đó. Nếu nguồn đã đạt trần 8.000 item/s thì tăng worker xử lý không tự nâng trần toàn pipeline.

**7. Trong benchmark, nên đo thời gian trung bình của worker hay tổng elapsed time?**

Cần cả hai, nhưng tổng elapsed time quyết định SLA. Thời gian trung bình và phân bố p95/p99 theo partition giúp giải thích straggler, contention và chi phí phối hợp.

**8. Khi nào nên tăng số partition mà không tăng số worker?**

Khi phân bố tải không đều và một số partition lớn kéo dài job, chia thành nhiều phần vừa phải có thể cho worker rảnh nhận thêm việc. Cần cân bằng với overhead dispatch và JobRepository.

---

**Ghi nhớ:** Chi phí phối hợp giữa các worker là phần giá phải trả để chia việc, giao việc, đồng bộ trạng thái, chờ phần chậm nhất, kiểm soát tải và phục hồi lỗi. Trong Spring Batch, chi phí ấy thay đổi theo mô hình song song, số worker, kích thước chunk/partition, JobRepository, broker và năng lực đọc/ghi chung. **Tăng số worker chỉ có ý nghĩa khi tổng thời gian hoàn thành giảm và tính đúng dữ liệu được giữ vững.**
