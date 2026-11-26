# Khi nào dùng RemoteStep? Ma trận lựa chọn kiến trúc Spring Batch

## 1. Bài toán lựa chọn, không phải chỉ là chọn một API

Module **SPRING_BATCH_SCALING_OPERATIONS** hướng tới mở rộng Spring Batch cho workload dữ liệu lớn qua **multi-threaded step**, **parallel steps**, **partitioning** và các mô hình phân tán; đồng thời dạy cách đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc phù hợp tài nguyên thực tế.

Trong chương **Ma trận lựa chọn**, câu hỏi **"Khi nào dùng RemoteStep?"** có nghĩa thực dụng: *khi nào nên để một tiến trình worker từ xa thực thi đơn vị công việc ở mức Step/StepExecution, thay vì giữ tất cả trong JVM của manager?*

Tên gọi **RemoteStep** trong bài được dùng như nhãn kiến trúc cho **step thực thi từ xa**. Không nên mặc định rằng mọi phiên bản Spring Batch đều có một API hay bean tên chính xác `RemoteStep`, hoặc rằng nhãn này đồng nghĩa với mọi hình thức xử lý qua broker. Cách hiện thực cần xác định theo phiên bản Spring Batch/Spring Batch Integration và hệ thống messaging thực tế. Mô hình tiêu biểu để giao **một worker StepExecution** cho tiến trình khác là **remote partitioning**; một số hệ thống tự xây dựng cơ chế giao step ở tầng orchestration riêng.

**Quy tắc nền tảng:** chọn remote execution khi lợi ích của **tách tài nguyên, triển khai độc lập và tăng concurrency trên nhiều process/nút** vượt được **chi phí phân tán, điều phối, mạng, metadata, retry, giám sát và vận hành**. Không dùng RemoteStep chỉ vì một job chạy chậm.

Sau bài học, bạn có thể:

- Phân biệt xử lý Step từ xa với multi-threaded step, parallel steps, local partitioning và remote chunking.
- Đọc ma trận quyết định theo kích thước dữ liệu, loại bottleneck, yêu cầu tách biệt và khả năng restart.
- Lập ngân sách thread, JDBC connection, broker queue, JobRepository và thời gian giao việc.
- Thiết kế thử nghiệm chứng minh lợi ích thực tế thay vì ước lượng từ số worker.
- Nhận diện các tình huống nên **không** phân tán và đề xuất hướng tối ưu đơn giản hơn.

## 2. RemoteStep trong ngữ cảnh Spring Batch

Trong một job Spring Batch, **Job** gồm một hoặc nhiều **Step**. Một Step có thể đọc, xử lý, ghi theo chunk hoặc thực hiện tasklet. Khi đưa công việc của step sang tiến trình worker:

1. **Manager** quyết định bước hoặc partition nào cần thực hiện và lưu/tra cứu tiến độ thông qua cơ chế JobRepository.
2. Một **kênh điều phối** gửi yêu cầu tới worker, thường là message broker nếu dùng remote partitioning qua Spring Batch Integration.
3. **Worker** nhận yêu cầu, khởi tạo đúng worker step, sử dụng dữ liệu định danh/ExecutionContext cần thiết, thực thi rồi ghi nhận trạng thái và phản hồi theo giao thức.
4. **Manager** tổng hợp kết quả và quyết định bước tiếp theo của Job.

~~~mermaid
flowchart LR
    J[Job / manager step] --> P[Partitioner / dispatcher]
    P --> Q[(Request channel / broker)]
    Q --> WA[Worker A: StepExecution]
    Q --> WB[Worker B: StepExecution]
    Q --> WC[Worker C: StepExecution]
    WA --> R[(Reply channel)]
    WB --> R
    WC --> R
    R --> J
    J --- B[(Shared JobRepository)]
    WA --- B
    WB --- B
    WC --- B
~~~

Sơ đồ minh họa **remote partitioning**: manager chia thành nhiều partition, mỗi worker chạy StepExecution tương ứng; trong mô hình tiêu chuẩn manager và worker truy cập một **JobRepository logic dùng chung**. Message request/reply hỗ trợ điều phối, còn dữ liệu trạng thái bền vững nằm tại metadata repository.

**Không nhầm với remote chunking:** Trong remote chunking, manager thường tự **đọc và chia chunk**, sau đó gửi các item cho worker xử lý/ghi rồi nhận chunk response. Đây là phân phối công việc ở **mức chunk và payload item**, không nhất thiết là giao toàn bộ StepExecution sang worker. Chọn sai mô hình có thể khiến data locality, băng thông, semantics transaction và trách nhiệm restart bị hiểu sai.

**Không nhầm với chạy một Job độc lập ở máy khác:** Gọi REST API để khởi chạy một Job riêng trên worker tạo ra bài toán orchestration và định danh JobInstance khác. Đây không tự động là remote partitioning hoặc một JobRepository thống nhất; cần thiết kế hợp đồng riêng nếu đi theo hướng đó.

## 3. So sánh những lựa chọn trước khi chọn RemoteStep

| Mô hình | Đơn vị song song | Nằm ở đâu? | Phù hợp khi | Cần cảnh giác |
|---|---|---|---|---|
| **Single-thread step** | Một Step tuần tự | Một JVM | Dữ liệu ít, logic đơn giản, cần baseline | Throughput bị giới hạn bởi một luồng |
| **Multi-threaded step** | Nhiều tác vụ/chunk trong một Step | Một JVM | Dữ liệu có thể xử lý song song, reader/writer an toàn | Stateful reader, thứ tự item, contention một StepExecution |
| **Parallel steps** | Nhiều Step/flow độc lập | Một JVM (thường gặp) | Các nhánh job ít phụ thuộc nhau | Phân bổ CPU/JDBC tổng, nhánh lỗi và merge kết quả |
| **Local partitioning** | Nhiều worker StepExecution | Một JVM | Có thể chia dữ liệu rõ ràng nhưng chưa cần nhiều process | Cùng giới hạn heap, CPU, tài nguyên của một tiến trình |
| **Remote partitioning / step ở worker từ xa** | Một StepExecution cho mỗi partition | Nhiều JVM/nút | Cần scale ngang, data locality hoặc fault isolation theo worker | Broker, shared metadata, idempotency, deployment compatibility |
| **Remote chunking** | Chunk/items | Manager và các worker | Muốn manager tập trung việc đọc; worker chuyên xử lý/ghi | Payload lớn qua mạng, deserialize, retry từng chunk |
| **Job độc lập do scheduler điều phối** | Một JobInstance riêng | Nhiều service/nút | Các job có vòng đời độc lập và ranh giới nghiệp vụ riêng | Không được nhầm với một StepExecution trong Job chung |

Thứ tự đánh giá thường là **đo baseline → tối ưu truy vấn/I/O/chunk → thử concurrency cục bộ → partition theo dữ liệu → xem xét remote execution**. Đây là trình tự giảm rủi ro, **không phải quy tắc bắt buộc**: một môi trường có sẵn worker riêng hoặc yêu cầu cách ly bắt buộc có thể cần remote ngay từ đầu.

## 4. Những tín hiệu cho thấy RemoteStep đáng cân nhắc

### 4.1. Một JVM không đủ tài nguyên nhưng nhiều nút còn dư

Job đã được benchmark và chứng minh có phần xử lý song song đáng kể; JVM đơn lẻ chạm **CPU quota**, heap hoặc giới hạn tiến trình, trong khi các worker khác có tài nguyên độc lập. Chia partition qua worker có thể mở rộng tổng năng lực.

Điều kiện cần: phần dữ liệu đủ độc lập; không có một lock hoặc database query chung khiến toàn hệ thống vẫn nối đuôi nhau. **Nhiều worker không khắc phục một database đang khóa, một API giới hạn 100 RPS hay một reader tuần tự duy nhất.**

### 4.2. Dữ liệu có thể chia partition rõ ràng

Có thể chia theo khoảng khóa, hash, tenant, ngày, file hoặc bucket mà mỗi partition:

- Có phạm vi **không chồng lấn**, hoặc có cơ chế chống ghi trùng.
- Có khối lượng công việc gần cân bằng hoặc có phương án xử lý **skew**.
- Có reader/writer độc lập theo StepExecution, với checkpoint/restart được xác định.
- Có thể retry một partition không phụ thuộc vào các partition khác theo cách gây tác dụng phụ ngoài ý muốn.

Nếu các partition tranh cùng hàng dữ liệu, toàn bộ lợi ích của remote có thể biến thành contention và deadlock.

### 4.3. Muốn tách lifecycle, dependency hoặc blast radius

Worker có thể chứa thư viện xử lý ảnh/file lớn, native dependency hoặc workload nặng CPU, trong khi manager chủ yếu điều phối. Chạy worker ở nhóm pod/container riêng giúp đặt **CPU/RAM limit, autoscaling, release và alert** phù hợp.

Tách process có thể giảm ảnh hưởng của OOM ở worker đến manager, nhưng **không mặc nhiên bảo đảm cô lập toàn hệ thống**: worker vẫn có thể làm đầy broker, cạn JDBC connections hoặc gây quá tải JobRepository dùng chung.

### 4.4. Muốn tăng/giảm worker theo backlog có kiểm soát

Khi công việc đến thành đợt và phần xử lý đủ dài, remote worker có thể tăng số instance trong giới hạn tài nguyên, sau đó giảm khi backlog hết. Cần đo **thời gian khởi động worker**, handshake, warm-up, độ trễ dispatch và khả năng drain; không mặc định autoscaling sẽ theo kịp một job chỉ kéo dài vài giây.

### 4.5. Cần xử lý gần nơi dữ liệu nằm

Nếu mỗi worker có thể đọc từ shard, vùng lưu trữ hoặc tập file gần mình, remote partitioning giảm việc chuyển dữ liệu thô qua manager. Ngược lại, nếu mọi worker đều phải kéo cùng dữ liệu qua mạng về một database duy nhất, data locality có thể không mang lại lợi ích.

## 5. Những tín hiệu nên tránh RemoteStep

| Tình huống | Vì sao remote thường chưa phù hợp? | Hướng thử trước |
|---|---|---|
| Job ngắn, chỉ vài giây hoặc vài trăm item | Chi phí broker, startup, scheduling và metadata có thể lớn hơn công việc | Single-thread, batch I/O, chunk tuning |
| CPU còn rảnh, DB đã chạm max connection/lock wait | Thêm worker tăng pressure lên nút thắt | Index/query/transaction, connection budget |
| Writer cần cập nhật một bản ghi/lock chung | Scale chỉ tăng contention, có nguy cơ deadlock | Phân chia vùng ghi, giảm khóa, tuần tự hóa đoạn bắt buộc |
| Reader phụ thuộc một cursor/state đơn không thể chia | Partition không độc lập, restart phức tạp | Thiết kế partitioner/restartable reader trước |
| Tác vụ cần thứ tự tuyệt đối trên toàn dữ liệu | Worker chạy độc lập có thể đảo thứ tự | Thiết kế ordering theo key/bucket hoặc giữ serial |
| Không có idempotency hoặc checkpoint đáng tin | Retry/redelivery có thể làm mất/trùng dữ liệu | Sửa transaction boundary và writer trước |
| Đòi hỏi transaction ACID xuyên nhiều worker/DB | Không có transaction chung mặc định qua broker | Xem lại ranh giới nghiệp vụ/saga, tránh phân tán tùy tiện |
| Không vận hành được broker, certificate, DLQ và trace | Khó điều tra job stuck, replay sai | Cải thiện nền tảng vận hành hoặc ưu tiên local partitioning |
| Chỉ cần nhiều nhánh xử lý khác nhau trong một JVM | Step độc lập phù hợp parallel steps hơn | Parallel flows/steps |
| Cần đẩy item qua mạng nhưng manager là điểm đọc duy nhất | Remote chunking có thể sát nhu cầu hơn | So sánh remote chunking và partitioning bằng PoC |

Một câu hỏi kiểm tra rất hữu ích: **"Nếu thêm hai worker, giới hạn nào của hệ thống thật sự được nới ra?"** Nếu câu trả lời chỉ là "thêm thread" nhưng DB, broker hoặc nguồn dữ liệu đã bão hòa, RemoteStep có thể làm chậm hơn.

## 6. Ma trận quyết định: tiêu chí bắt buộc và tiêu chí cho điểm

Trước tiên, kiểm tra các **điều kiện loại trừ (gates)**; sau đó mới so sánh lợi ích.

| Gate | Phải chứng minh điều gì? | Nếu không đạt |
|---|---|---|
| **G1 — Partition correctness** | Phạm vi partition xác định, tránh overlap/gap, có cách đối soát | Không triển khai remote partitioning |
| **G2 — Restart và idempotency** | Có thể chạy lại partition/chunk không mất hoặc nhân đôi side effect | Thiết kế lại xử lý lỗi trước |
| **G3 — Shared state contract** | JobRepository, step name, ExecutionContext và version manager/worker tương thích | Chặn deploy/hoàn thiện contract test |
| **G4 — Resource budget** | CPU/RAM, tổng JDBC connections, broker và DB đáp ứng concurrency dự kiến | Giảm concurrency/đổi hạ tầng |
| **G5 — Observability** | Truy vết được job/step/partition và message, có alert/job recovery | Chưa nên mở rộng production |
| **G6 — Security & operation** | Danh tính worker, TLS/mTLS theo transport, broker ACL, secret rotation, runbook | Hoàn thiện nền tảng hoặc giữ topology đơn giản |

**Đạt gate không đồng nghĩa phải dùng RemoteStep**. Khi hệ thống an toàn để thử remote, có thể chấm điểm các tiêu chí lựa chọn trên thang 0–2 theo một cách **tự định nghĩa của nhóm**:

| Tiêu chí | 0 điểm | 1 điểm | 2 điểm |
|---|---|---|---|
| Tài nguyên một JVM | Dư dả | Gần giới hạn | Đã đo chạm giới hạn |
| Tính độc lập của partition | Khó chia | Chia được nhưng skew cao | Chia rõ ràng, ít phụ thuộc |
| Khả năng scale downstream | Bão hòa | Còn dư ít | Còn ngân sách rõ ràng |
| Lợi ích fault isolation | Không cần | Có ích | Yêu cầu vận hành quan trọng |
| Lợi ích tách deployment | Không có | Có một số dependency khác | Worker có lifecycle/tài nguyên khác biệt |
| Độ dài công việc | Rất ngắn | Trung bình | Đủ dài để amortize overhead |

Tổng điểm từ 0 đến 12 **không phải chuẩn của Spring Batch** và không nên đặt một ngưỡng tự động cứng. Dùng điểm để minh bạch trade-off, sau đó **PoC và benchmark** mới quyết định: một gate không đạt có thể phủ quyết cả phương án dù điểm tổng rất cao.

## 7. Định lượng khả năng tăng tốc: đừng đếm worker thay cho throughput

Một ước lượng đơn giản cho job có N partition và k worker là:

~~~text
T_remote ≈ T_dispatch + T_queue_wait
           + T_slowest_wave_of_partitions
           + T_aggregate + T_recovery_overhead

T_local  ≈ T_processing_local + T_local_scheduling

Speedup = T_local / T_remote
~~~

**T_slowest_wave_of_partitions** không thể luôn viết thành tổng thời gian/k vì task có độ dài khác nhau. Partition skew, retry hoặc một worker chậm có thể quyết định critical path. Các chi phí dispatch/queue/aggregate phụ thuộc broker, JobRepository và code cụ thể; chúng phải được đo.

Áp dụng **Amdahl's Law** như một kiểm tra giới hạn lý thuyết: nếu p là tỷ lệ có thể song song hóa, tăng tới k đơn vị xử lý thì:

~~~text
Speedup_max ≈ 1 / ((1 - p) + p / k)
~~~

Giả sử 80% thời gian có thể song song hóa, còn 20% do đọc metadata, chuẩn bị/ghi kết quả cuối cùng hoặc bước tuần tự. Với 8 worker, giới hạn lý tưởng xấp xỉ **3,33 lần**, chưa tính mạng và overhead. Không thể tuyên bố "thêm 8 worker = nhanh 8 lần".

### 7.1. Ngân sách database

Ví dụ có 1 manager và 10 worker; mỗi worker đặt JDBC maximum pool size = 8, manager = 6. Tổng connection **tiềm năng** là 10 × 8 + 6 = **86**. Còn phải tính ứng dụng khác, metadata repository, monitoring và khả năng database thực tế. Nếu database chỉ cho phép 70 kết nối ở workload này, cấu hình hiện tại cần đánh giá lại trước khi scale; queue hoặc retry không làm quota tăng.

Con số maximum pool **không bằng số kết nối đang mở tại mọi thời điểm**. Hãy đo `active`, `idle`, `pending`, thời gian lấy connection và lock wait để thấy liệu CPU worker, network hay database thực sự giới hạn throughput.

### 7.2. Ngân sách messaging và JobRepository

- **Broker throughput:** message/giây, request/reply latency, consumer lag, unacked/prefetch, DLQ.
- **Metadata write rate:** số StepExecution/JobExecution update, lock wait, optimistic locking conflicts.
- **Executor backlog:** active tasks, queue depth, queue wait; tránh dùng queue không giới hạn để "giữ mọi request".
- **Recovery cost:** thời gian restart, tần suất retry và replay, thời gian đối soát dữ liệu đã commit.

Một hệ thống có thể scale CPU tốt nhưng không scale **JobRepository** vì quá nhiều partition nhỏ tạo số lần cập nhật metadata lớn. Ngược lại, partition quá lớn gây skew và hồi phục chậm sau lỗi.

## 8. Thiết kế contract cho step thực thi từ xa

Trước khi viết code, xác định **ai sở hữu trạng thái, ai giao việc và worker chạy step nào**. Với remote partitioning điển hình:

| Thành phần | Trách nhiệm | Hợp đồng cần xác minh |
|---|---|---|
| Manager partitioner | Chia dữ liệu thành các partition | Không bỏ sót/trùng phạm vi, key ExecutionContext ổn định |
| Manager step | Tạo/điều phối worker StepExecution | Tên job/step, correlation và JobRepository phù hợp |
| Request transport | Chuyển yêu cầu sang worker | Destination, serializer, retry, TLS/ACL, quá tải |
| Worker step | Đọc partition context, xử lý và cập nhật metadata | Step name, reader/writer, transaction, idempotency |
| Reply transport | Chuyển trạng thái tới manager | Correlation, timeout, redelivery và quy tắc recovery |
| Shared JobRepository | Lưu JobInstance, JobExecution, StepExecution, ExecutionContext | Schema/serializer, isolation, quyền DB, restart compatibility |

Ví dụ **hợp đồng partition do ứng dụng tự định nghĩa**:

~~~yaml
topology: remote-partitioning
workerStepName: importWorkerStep
partitionContract: import-by-id-range-v1
contextKeys:
  lowerInclusive: minId
  upperExclusive: endIdExclusive
requestChannel: import.partition.request
replyChannel: import.partition.reply
metadataStore: shared-job-repository
~~~

YAML trên là **tài liệu hợp đồng**, không phải tập thuộc tính mà Spring Batch tự đọc. Tại mã ứng dụng, manager và worker phải thống nhất rằng `minId` bao gồm cận đầu và `endIdExclusive` loại trừ cận cuối. Nếu nâng phiên bản làm thay đổi key hay semantics, các worker cũ có thể xử lý sai cả những partition đang chờ trên broker.

### 8.1. Ví dụ triển khai worker step theo kiểu Spring Batch 5.x

Trong worker JVM, một **Step bean** xử lý dữ liệu từng chunk có thể có dạng:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class ImportWorkerStepConfiguration {

    @Bean
    Step importWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Long> partitionReader,
            ItemProcessor<Long, Long> processor,
            ItemWriter<Long> writer) {
        return new StepBuilder("importWorkerStep", jobRepository)
            .<Long, Long>chunk(200, transactionManager)
            .reader(partitionReader)
            .processor(processor)
            .writer(writer)
            .build();
    }
}
~~~

Đoạn code là **khung cấu hình worker Step**, **chưa** thiết lập manager, broker, request/reply flow hoặc reader dựa trên partition; không thể chỉ copy là có remote partitioning. Ứng dụng phải cung cấp `partitionReader` hiểu ExecutionContext của từng StepExecution (thường sử dụng step scope), `processor`, `writer` và tích hợp remote partitioning đúng phiên bản. Không biến một ItemReader stateful thành singleton dùng chung nhiều StepExecution nếu không có chiến lược bảo đảm an toàn.

### 8.2. Dữ liệu đi đâu?

Trong **remote partitioning**, manager có thể chỉ giao *định danh partition* và worker tự đọc nguồn dữ liệu. Nếu phải truyền toàn bộ hàng triệu item qua manager đến worker, lợi ích data locality bị giảm; khi đó nên so sánh **remote chunking**.

Lưu ý: **partition context không phải message payload mặc định trong mọi cấu hình**. Một mô hình tiêu chuẩn có thể lưu ExecutionContext tại JobRepository và truyền StepExecutionRequest chứa thông tin nhận diện; worker lấy state tương ứng từ metadata.

## 9. Lựa chọn chiến lược partition để remote thực sự hiệu quả

| Cách chia | Ưu điểm | Rủi ro chính |
|---|---|---|
| **ID range** | Dễ truy vấn theo index, dễ checkpoint | ID thưa, skew, nhầm inclusive/exclusive |
| **Hash bucket** | Có thể cân bằng hơn khi key phân bố rộng | Truy vấn hash có thể không tận dụng index như mong đợi |
| **Theo tenant** | Tách workload/ACL, thuận tiện đối soát | Tenant lớn chiếm phần lớn thời gian |
| **Theo file** | Phân chia và retry theo artifact | File size khác nhau, atomic output, storage permissions |
| **Theo ngày/giờ** | Phù hợp dữ liệu event/log và lưu trữ theo partition | Vùng thời gian và boundary, ngày cao điểm gây lệch tải |
| **Theo shard** | Khai thác locality, giảm chuyển dữ liệu | Năng lực shard không đồng đều, giới hạn kết nối |

Ví dụ query theo khoảng khóa không chồng lấn (giả sử kiểu dữ liệu và index phù hợp):

~~~sql
SELECT id, amount, status
FROM payment_event
WHERE id >= :minId
  AND id < :endIdExclusive
ORDER BY id;
~~~

Các cặp khoảng `[0, 1000)`, `[1000, 2000)` và `[2000, 3000)` không có overlap nếu reader hiểu đúng. Tuy nhiên, ID phân bố không đều có thể khiến một partition đọc hàng triệu row còn partition khác chỉ có vài trăm row. Cần đo **item count và duration theo partition**, không đo mỗi tổng job time.

Khi nguồn dữ liệu thay đổi trong lúc job chạy, phải xác định **snapshot/cutoff**, transactional consistency và quy tắc xử lý bản ghi mới. Chia partition đúng về mặt số học chưa bảo đảm quét nguồn nhất quán qua nhiều worker ở các thời điểm khác nhau.

## 10. Retry, restart và tính đúng đắn quyết định khả năng dùng RemoteStep

Trong kiến trúc phân tán, lỗi có thể xảy ra ở **giữa hai bước đã thành công một phần**:

1. Manager tạo StepExecution nhưng request chưa được publish đến broker.
2. Broker lưu request nhưng worker chưa nhận hoặc chưa ack.
3. Worker xử lý và **commit business data**, nhưng chưa kịp cập nhật StepExecution hoặc gửi reply.
4. Worker cập nhật metadata xong nhưng reply mất hoặc manager crash.
5. Worker mới nhận lại một request cũ sau deploy, reconnect hoặc retry.

Không có một transaction ACID chung tự động bao trùm **broker + JobRepository + business DB + external API**. Vì vậy, mấu chốt khi dùng RemoteStep không chỉ là retry, mà là **retry mà vẫn đúng dữ liệu**.

| Trường hợp lỗi | Cần phân tích | Hành động an toàn |
|---|---|---|
| Worker chết trước khi commit | Transaction đã rollback chưa? Message có được giao lại không? | Recovery theo StepExecution/checkpoint và broker policy |
| Worker commit rồi mất reply | Side effect đã tồn tại dù manager chưa thấy COMPLETED | Đối soát state, writer idempotent, không blind replay |
| JobRepository tạm thời unavailable | Worker đã xử lý đến đâu? Meta update thất bại ở pha nào? | Khôi phục DB, phân loại state trước restart |
| ExecutionContext serializer khác phiên bản | Worker mới có đọc được checkpoint cũ? | Contract test/migration có kiểm soát |
| Partition chồng lấn | Có khóa nghiệp vụ duy nhất hoặc quy tắc dedup? | Chỉnh partitioner và đối soát; không chỉ tăng worker |
| Retry storm khi broker/DB lỗi | Số request/redelivery và tải đang dâng? | Backoff, jitter, giới hạn attempts và admission |
| Manager vẫn STARTED nhưng process đã chết | Có worker thực tế còn chạy hay message đang in-flight? | Kiểm tra process, metadata, broker trước khi recovery |

**Restart** phải dựa vào **JobInstance đúng với identifying JobParameters**, trạng thái JobExecution/StepExecution, ExecutionContext và hành vi reader/writer. Tạo JobParameters mới chỉ để chạy lại có thể tạo **JobInstance mới**, không phải restart lần chạy lỗi. Không tự ý `UPDATE BATCH_STEP_EXECUTION SET STATUS='COMPLETED'` hoặc bỏ qua version metadata để "gỡ kẹt".

### 10.1. Chính sách idempotency tối thiểu

- Dùng **khóa nghiệp vụ ổn định** cho output, tránh tạo bản sao khi một partition chạy lại.
- Ưu tiên thao tác ghi có thể lặp như **UPSERT**, hoặc bảng dedup/outbox khi side effect có tính bất đồng bộ.
- Tách **retryable lỗi tạm thời** (timeout) khỏi lỗi schema/protocol không tương thích (poison message).
- Xác định ai chịu trách nhiệm retry: broker, manager, worker hay cơ chế restart; tránh nhiều tầng retry độc lập gây nhân số lần thực thi.
- Có cơ chế **đối soát dữ liệu** chứ không chỉ kiểm tra JobExecution báo COMPLETED.

## 11. Thread safety khi tách step sang worker

Chuyển sang remote không tự sửa lỗi thread safety của reader/processor/writer. Trong remote partitioning, mỗi partition thường có StepExecution riêng, nhờ đó có thể cô lập reader state theo partition; nhưng nếu trong **một worker JVM** còn dùng TaskExecutor để xử lý chunk song song hoặc chia sẻ bean singleton giữa partition thì vẫn phải đánh giá đồng thời.

Các điểm cần kiểm tra:

- Reader cursor, buffer và checkpoint có được sở hữu theo **StepExecution** và restart đúng không?
- Có bao nhiêu partition chạy trong một worker process? Có dùng chung singleton mutable state ngoài ý muốn?
- Writer có thứ tự ghi bắt buộc, lock/counter dùng chung hoặc phụ thuộc transaction của manager không?
- Processor có cache hoặc mutable fields không thread-safe không?
- Có `@StepScope` cho component đọc tham số partition đúng mức scope cần thiết không? `@StepScope` **không** đồng nghĩa một instance riêng cho mỗi thread trong cùng StepExecution.

Nếu người dùng cần bảo toàn thứ tự toàn cục hoặc transaction chung giữa các item, remote fan-out thường tạo thêm bài toán consistency. Có thể dùng partition theo key để bảo toàn thứ tự **trong từng key**, nhưng cần viết rõ rằng không bảo đảm thứ tự **giữa các key**.

## 12. Compatibility, bảo mật và triển khai nhiều phiên bản

Khi manager và worker chạy artifact khác nhau, phát hành đồng thời hoặc rolling upgrade tạo ra một **giao thức giữa hai tiến trình**. Trước khi cho phép old/new cùng tiêu thụ một queue, kiểm tra:

| Lớp | Điều kiện |
|---|---|
| Spring Batch/Integration | Phiên bản dependency và message type được kiểm chứng tương thích |
| Step & partition contract | Step name, ExecutionContext keys/types/semantics không lệch |
| JobRepository | Shared schema, serializer, transaction và metadata version phù hợp |
| Messaging | Request/reply destination, correlation ID, serializer, retry/ack rõ ràng |
| Security | TLS/mTLS theo từng transport, account/broker ACL, secret handling |
| Deployment | Có drain, canary, rollback và cách xử lý request tồn đọng |

Nếu remote partitioning qua broker, **mTLS giữa manager và broker** cùng **mTLS giữa worker và broker** là hai kết nối riêng. Nó không tự làm manager/worker xác thực trực tiếp lẫn nhau hoặc cấp quyền truy cập JobRepository. DB còn cần chính sách TLS, identity, secret và phân quyền độc lập.

Một **mixed-version rollout** chỉ an toàn khi có contract test cho cả hai chiều A-manager/B-worker và B-manager/A-worker, hoặc khi routing tách hẳn các nhóm phiên bản. Nếu chưa chứng minh được điều đó, quiesce/drain workload cũ trước khi đổi worker/manager.

## 13. Theo dõi RemoteStep bằng metrics có thể hành động

Chỉ quan sát **số pod READY** hoặc **số worker online** chưa đủ để biết mô hình phân tán đang có lợi. Thu thập metrics tại cả manager, broker, worker, JobRepository và downstream:

| Lớp | Metric | Câu hỏi vận hành |
|---|---|---|
| Job/manager | Job duration, step duration, partition count, failed/restarted executions | Lợi ích cuối cùng là job hoàn tất đúng và nhanh hơn không? |
| Partition | Duration p50/p95/p99, items/partition, skew ratio | Worker nào chậm, dữ liệu chia cân bằng chưa? |
| Broker | Request/reply latency, queue depth, consumer lag, unacked, DLQ | Worker thiếu hay traffic bị kẹt ở message layer? |
| Worker | Active executor threads, CPU, heap/GC, task throughput | Worker có đủ tài nguyên, có bị queue vô hạn không? |
| JDBC pool | Active, idle, pending, acquisition latency | Có thiếu connection khi scale? |
| Database | Query p95, lock waits, transaction duration, IO/CPU | Có bottleneck chung khiến worker thêm vô ích? |
| Reliability | Retry/redelivery, idempotency conflicts, restart time | Tăng tốc có trả giá bằng xử lý trùng hoặc downtime? |

Trong trace/log, nên có `jobExecutionId`, `stepExecutionId`, `partitionName`, worker instance/release và `messageId`/correlation khi có. Đối với remote partitioning qua broker, **reply timeout** có thể do worker chưa xử lý, worker đang chờ DB, broker lỗi hoặc mismatch message contract; không nên tự động xem đó là lỗi CPU.

### Ba chỉ số quyết định sau benchmark

1. **End-to-end duration:** thời gian Job hoàn tất từ lúc được nhận đến lúc trạng thái và output đã đúng.
2. **Cost per completed record/job:** tổng CPU, RAM, DB, broker và chi phí vận hành tương ứng với throughput thật.
3. **Recovery objective:** thời gian phát hiện lỗi, khôi phục và đối soát sau worker/manager crash.

Một kết quả "nhanh hơn 20%" có thể chưa đáng chọn nếu tốn gấp đôi DB connections, tăng chi phí vận hành quá cao hoặc không đáp ứng recovery objective.

## 14. Các tình huống lựa chọn điển hình

### Tình huống A — Import 20 triệu bản ghi, CPU-bound

Nguồn dữ liệu có thể chia theo ID range, processor tính toán nặng CPU, một JVM đạt CPU quota; database còn đủ IOPS/connection; writer hỗ trợ idempotent UPSERT. Khi chia 16 partition và dùng worker scale ngang, **remote partitioning là ứng viên mạnh**.

Điều cần xác minh: partition skew, tổng connection, throughput theo số worker, CPU busy thực tế, metadata write rate và khả năng restart từng partition. Không giả định cứ 16 partition là cần 16 worker.

### Tình huống B — Job 2.000 item gọi API đối tác giới hạn 50 request/s

Thời gian chờ API là nút thắt và đối tác enforce rate limit chung. Tăng số remote worker dễ làm 429/timeout nhiều hơn. **Ưu tiên rate limiting, batching nếu API hỗ trợ, retry/backoff và giới hạn concurrency**, thay vì thêm RemoteStep.

Remote có thể phù hợp nếu cần tách credential/network/security domain, nhưng lợi ích đó phải được đánh giá riêng; nó không tự làm API nhanh hơn.

### Tình huống C — Bốn nhánh xử lý khác nhau, không phụ thuộc nhau

Job có các step chuẩn hóa dữ liệu, xuất báo cáo, đối soát và xây index chạy độc lập, mỗi nhánh vừa tài nguyên một JVM. **Parallel steps** có thể đơn giản hơn remote partitioning, vì không cần broker cho từng StepExecution.

Nếu từng nhánh cần tài nguyên/container khác nhau và release độc lập, cân nhắc job orchestration riêng hoặc remote execution theo hợp đồng thực tế, thay vì cố ép mọi step vào partitioner.

### Tình huống D — 500 file lớn đã nằm ở các storage shard

Mỗi file có thể xử lý độc lập, worker được đặt gần storage shard, kết quả ghi theo file có khóa duy nhất. **Remote partitioning theo file/shard** có thể vừa scale ngang vừa giảm network transfer qua manager.

Trước khi chọn, kiểm tra skew theo kích thước file, quyền truy cập storage từ mỗi worker, atomic output, handling file lỗi và retry không xuất file trùng.

### Tình huống E — Một bảng dữ liệu chung bị row lock khi tăng worker

Mọi partition cùng cập nhật một hàng tổng hợp; khi tăng từ 4 lên 24 worker, lock wait tăng và throughput giảm. **Không nên giải quyết bằng thêm RemoteStep**. Hãy thiết kế lại cách tổng hợp, giảm transaction contention hoặc chuyển aggregation sang step riêng.

### Tình huống F — Manager đọc dữ liệu, worker chỉ xử lý nội dung

Reader duy nhất phải chạy tại manager vì ràng buộc kết nối tới nguồn và item có thể được serialize an toàn. Worker xử lý CPU và ghi kết quả với idempotency. **Remote chunking** có thể phù hợp hơn remote partitioning, nhưng cần đo kích thước payload, băng thông, serializer và ranh giới transaction.

## 15. Quy trình PoC trước khi chọn RemoteStep

Một PoC có giá trị không chỉ chứng minh "worker chạy được" mà phải trả lời **có nhanh hơn và ổn định hơn với chi phí chấp nhận được không?**

1. **Chọn dataset đại diện:** bao gồm bản ghi lớn/nhỏ, phân bố key không đều, dữ liệu lỗi, tình huống retry và đối soát được.
2. **Đo baseline:** single-thread hoặc local partitioning hợp lý trên cùng năng lực tài nguyên; ghi p95 chunk, DB latency, CPU/heap và thời gian job.
3. **Chốt hợp đồng partition:** khóa, semantics inclusive/exclusive, checkpoint, idempotency, step names, JobRepository, message protocol.
4. **Chạy remote ở nhiều mức:** ví dụ 2, 4, 8, 16 worker; giữ dữ liệu, DB quota và broker config nhất quán để kết quả có thể so sánh.
5. **Đo theo từng lớp:** job duration, partition skew, broker lag, DB locks, total JDBC pending và CPU/heap tổng.
6. **Tiêm lỗi có kiểm soát:** ngắt một worker giữa transaction, mất reply, restart manager, DB/broker gián đoạn ngắn. Xác minh recovery.
7. **Đối soát:** số bản ghi, khóa duy nhất, tổng giá trị nghiệp vụ, file/message side effects, commit/restart count.
8. **Tổng hợp:** speedup, thời gian drain backlog, chi phí/năng lực, failure recovery và độ phức tạp release/observability.

### Ví dụ bảng kết quả PoC giả định

Các số sau **chỉ là dữ liệu minh họa**, không phải benchmark thực của Spring Batch:

| Kiến trúc | Worker song song | Thời gian job | DB connection peak | Lỗi/retry | Nhận xét |
|---|---:|---:|---:|---|---|
| Single-thread | 1 | 120 phút | 4 | 0 | Baseline |
| Local partitioning | 4 | 42 phút | 12 | 0 | Tăng tốc rõ, ít thành phần |
| Remote partitioning | 4 | 44 phút | 16 | 0 | Overhead chưa được bù |
| Remote partitioning | 8 | 26 phút | 30 | 1 retry an toàn | Ứng viên phù hợp |
| Remote partitioning | 16 | 24 phút | 58 | Lock wait tăng | Lợi ích biên thấp, DB căng |

Trong ví dụ, **8 worker remote** có thể đáng cân nhắc vì nhanh hơn local đáng kể; 16 worker tăng speedup ít nhưng tiêu tốn thêm connections và gặp lock wait. Nếu doanh nghiệp không cần hoàn tất dưới 30 phút, local partitioning có thể vẫn là lựa chọn kinh tế hơn.

### Tiêu chí PASS tối thiểu

- Job hoàn tất nhanh hơn mức baseline theo một **ngưỡng mục tiêu đã thống nhất**, không chỉ nhanh trong một lần chạy.
- Kết quả dữ liệu giống baseline, không thiếu/trùng sau worker crash và restart.
- Broker, JobRepository và database không vượt ngưỡng CPU/connection/lock wait/backlog.
- Có thể vận hành rollout, rollback, drain và quan sát lỗi từ đầu đến cuối.
- Chi phí triển khai/giám sát/recovery phù hợp với SLA và năng lực đội ngũ.

## 16. Kế hoạch triển khai RemoteStep an toàn

Nếu PoC PASS, nên triển khai theo các bước:

1. **Phân nhóm artifact:** manager và worker có image, runtime/dependency, resource limits và service identity rõ ràng.
2. **Kiểm tra compatibility:** cùng contract StepExecution/ExecutionContext, schema JobRepository, request/reply và serializer; khóa version nếu rolling không được hỗ trợ.
3. **Đặt guardrails:** giới hạn số job đang chạy, worker concurrency, consumer prefetch, queue capacity, JDBC pool và retry attempts.
4. **Thiết lập security:** TLS/mTLS theo hop, broker read/write ACL và quyền DB tối thiểu, secret rotation.
5. **Canary bằng partition nhỏ:** kiểm tra end-to-end dispatch → worker → reply → metadata và đối soát output.
6. **Tăng worker theo ngưỡng:** quan sát throughput và p95/p99 partition duration, DB contention, broker lag và tài nguyên.
7. **Chuẩn bị rollback:** xác định trạng thái job và message còn tồn, khả năng đọc context cũ, hướng drain thay vì xóa queue.
8. **Vận hành định kỳ:** định nghĩa alert, ownership, diễn tập restart và báo cáo cost/throughput qua các kỳ.

Nếu có phiên bản manager/worker không tương thích, **đừng** để hai release tùy ý consume cùng request queue. Dùng drain/quiesce hoặc tách routing theo version sau khi đã thử nghiệm contract. Rollback image không tự phục hồi metadata/side effects đã được bản mới ghi.

## 17. Những anti-pattern khi chọn RemoteStep

| Anti-pattern | Tác hại | Thay bằng |
|---|---|---|
| "Job chậm thì thêm remote worker" | Bottleneck DB/API vẫn giữ nguyên, tăng connection/lock | Profiling và benchmark trước |
| Tạo rất nhiều partition nhỏ | Metadata overhead, broker traffic và scheduling tăng | Chọn partition granularity theo workload |
| Một partition khổng lồ còn các partition khác rỗng | Tail latency do skew | Chia theo khối lượng thực, dynamic work distribution nếu phù hợp |
| Queue manager/worker không giới hạn | Backlog, memory, queue wait tăng | Bounded queue, admission, rate limits |
| Dùng chung mutable reader giữa worker threads | Mất thứ tự, checkpoint sai, duplicate | Scoped reader, partition state riêng |
| Dựa vào message reply làm nguồn trạng thái duy nhất | Mất reply có thể khiến manager suy diễn sai | Kiểm tra JobRepository và recovery policy |
| Giả định exactly-once chỉ vì dùng Spring Batch | Redelivery sau commit có thể ghi trùng | Idempotent write và đối soát |
| Dùng bản manager/worker khác version chưa thử | Không deserialize hoặc không đọc context cũ | Contract test, version routing |
| Tăng JDBC pool trên mọi replica không tính tổng | Cạn DB connection, lock wait | Resource budget toàn cụm |
| Auto-restart ngay khi worker mất liên lạc | Worker cũ có thể vẫn xử lý, tạo overlap | Kiểm tra in-flight/metadata và fencing/lease nếu thiết kế cần |
| Dùng remote chunking dù item payload khổng lồ | Broker và mạng thành bottleneck | Cân nhắc remote partitioning để worker đọc dữ liệu gần nguồn |

## 18. Bài tập: lập quyết định kiến trúc có bằng chứng

**Tình huống:** Job cuối ngày xử lý 12 triệu giao dịch, hiện chạy 150 phút. Một JVM 8 vCPU; CPU thường 90%, còn database 50–60% I/O và có 100 connection quota cho toàn hệ thống. Dữ liệu có thể phân chia theo vùng thời gian nhưng phân bố không đều (một vùng có 45% giao dịch). Người quản lý muốn giảm thời gian xuống dưới 45 phút và đang cân nhắc 12 worker remote.

Hãy lập bảng quyết định:

1. Xác định **đoạn xử lý tuần tự** và những metrics cần thu để ước lượng giới hạn speedup.
2. Lựa chọn giữa multi-threaded step, local partitioning và remote partitioning; nêu ít nhất ba giả thuyết cần kiểm chứng.
3. Thiết kế partition sao cho vùng chiếm 45% dữ liệu không làm toàn job chờ một worker.
4. Tính ngân sách JDBC **tiềm năng** khi mỗi worker pool 8 connection và manager pool 6; giải thích vì sao 12 × 8 + 6 = **102** đã vượt quota 100 trước khi tính ứng dụng khác.
5. Đề xuất workload PoC ở 4/8/12 worker, giữ dataset/DB quota ổn định và đo cost/throughput/lock wait.
6. Mô phỏng worker crash sau khi ghi 70% một partition, mất reply và broker redeliver; trình bày biện pháp không nhân đôi output.
7. Đề xuất rollout, version compatibility và rollback cho JobRepository, ExecutionContext và request/reply đang tồn.

### Câu hỏi tự kiểm tra

- Một Step có thể chạy ở JVM khác mà vẫn thuộc cùng JobInstance bằng cơ chế nào trong remote partitioning?
- Điểm khác biệt quan trọng nhất giữa **remote partitioning** và **remote chunking** là gì?
- Vì sao 16 worker không đồng nghĩa job nhanh gấp 16 lần?
- Khi CPU manager thấp nhưng worker JDBC pending cao, tăng worker có giúp không?
- Với một yêu cầu xử lý cần thứ tự toàn cục, tại sao fan-out theo partition có thể không phù hợp?
- Những điều kiện nào khiến việc **giữ local partitioning** hợp lý hơn dù remote PoC có tốc độ tương đương?
- Vì sao không thể tuyên bố "rollback an toàn" nếu bản cũ không đọc được ExecutionContext do bản mới ghi?

## 19. Checklist quyết định nhanh

- [ ] Đã đo bottleneck và xác định tài nguyên nào được nới rộng khi đưa Step sang worker từ xa.
- [ ] Dữ liệu phân chia được thành partition không overlap/gap, có cách xử lý skew và snapshot/cutoff phù hợp.
- [ ] Reader/writer đúng scope, thread-safe theo mô hình thực thi và có checkpoint/idempotency.
- [ ] Đã so sánh single-thread, multi-thread/parallel/local partitioning và remote partitioning/remote chunking.
- [ ] Tổng CPU/RAM/JDBC connections của toàn cụm nằm trong năng lực thực tế của broker/DB/API.
- [ ] Có shared JobRepository hoặc hợp đồng orchestration tương ứng và manager/worker version được kiểm thử.
- [ ] Có bounded queue, retry/backoff, DLQ/recovery policy và khả năng drain khi deploy.
- [ ] Có TLS/mTLS/ACL theo transport, secret management và phân quyền worker/DB rõ ràng.
- [ ] Có metrics end-to-end, correlation giữa JobExecution và StepExecution, alert backlog/timeout.
- [ ] PoC chứng minh speedup, dữ liệu đúng sau lỗi và chi phí vận hành chấp nhận được.

## 20. Kết luận

**Dùng RemoteStep khi cần mở rộng hoặc cô lập việc thực thi một StepExecution trên nhiều tiến trình và đã chứng minh phần việc có thể phân tán an toàn.** Với Spring Batch, **remote partitioning** là mô hình tiêu biểu cho việc giao partition/worker step qua ranh giới JVM; **remote chunking** phù hợp một bài toán khác khi item/chunk được chuyển cho worker. Nếu bottleneck nằm tại database, API giới hạn, logic tuần tự hoặc yêu cầu transaction/thứ tự không thể tách, remote thường không giúp và đôi khi còn làm hệ thống khó vận hành hơn. Quyết định đúng phải dựa trên **ma trận tiêu chí, phép đo end-to-end, ngân sách tài nguyên, restart/idempotency và khả năng vận hành thực tế**, không dựa vào số worker hay một tên kỹ thuật hấp dẫn.
