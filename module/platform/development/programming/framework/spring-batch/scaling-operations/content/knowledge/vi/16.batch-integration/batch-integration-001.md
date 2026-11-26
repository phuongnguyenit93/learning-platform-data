# Vai trò module spring-batch-integration

**Chương:** Spring Batch Integration  
**Module học:** SPRING_BATCH_SCALING_OPERATIONS

Trong một hệ thống Spring Batch, xử lý tuần tự trong một JVM thường đủ tốt khi dữ liệu vừa phải và thời gian hoàn thành rộng rãi. Khi cần xử lý hàng triệu bản ghi trong một cửa sổ batch ngắn, hoặc muốn phân phối công việc đến nhiều tiến trình, bài toán không còn chỉ là thiết lập số thread. Hệ thống phải có cách **giao việc, trao đổi thông điệp, theo dõi trạng thái, nhận kết quả và khôi phục khi một worker bị lỗi**.

Module **spring-batch-integration** nối mô hình batch của **Spring Batch** với khả năng điều phối bằng thông điệp của **Spring Integration**. Vai trò nổi bật của module trong hệ thống scaling là hỗ trợ **remote chunking**, **remote partitioning** và **khởi chạy job từ thông điệp**. Nó giúp các thành phần trao đổi công việc qua message channel theo một giao thức được Spring Batch hiểu, đồng thời vẫn sử dụng những khái niệm Batch quen thuộc như Job, Step, ItemReader, ItemProcessor, ItemWriter, ExecutionContext và JobRepository.

Bài này giải thích module giải quyết vấn đề gì, vị trí của nó trong kiến trúc, khác biệt giữa hai mô hình phân tán, chi phí vận hành và tiêu chí lựa chọn. Trọng tâm là **mở rộng Spring Batch cho workload dữ liệu lớn** mà vẫn kiểm soát thread safety, retry/restart, tính đúng đắn và tài nguyên thực tế.

## 1. spring-batch-integration nằm ở đâu?

Trong hệ sinh thái Spring, ba thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính | Ví dụ khả năng |
| --- | --- | --- |
| **Spring Batch** | Định nghĩa và thực thi batch job; quản lý job/step, chunk transaction, metadata, restart | Job, Step, Reader, Processor, Writer, JobRepository |
| **Spring Integration** | Tổ chức luồng trao đổi thông điệp và kết nối tới hệ thống bên ngoài theo các Enterprise Integration Patterns | MessageChannel, IntegrationFlow, gateway, adapter, router, transformer |
| **spring-batch-integration** | Cung cấp điểm nối giữa thực thi Batch và luồng message của Spring Integration | JobLaunchingMessageHandler, remote chunking, remote partitioning |

**spring-batch-integration không phải message broker.** Module cung cấp các thành phần tích hợp, nhưng độ bền thông điệp, lưu hàng đợi, phân phối tới worker, retry ở tầng truyền tải hay bảo mật kênh phụ thuộc vào cấu hình Spring Integration và transport thực tế như JMS, AMQP hoặc một cơ chế messaging phù hợp khác.

**spring-batch-integration cũng không thay thế JobRepository.** JobRepository quản lý metadata thực thi batch; broker quản lý việc vận chuyển thông điệp. Hai nơi lưu trạng thái này có chức năng khác nhau và cần được thiết kế để phối hợp khi xảy ra lỗi.

### Vì sao cần một module cầu nối?

Giả sử một job phải tính phí cho 18 triệu tài khoản trước 6 giờ sáng. Một step xử lý tuần tự đạt 1.000 tài khoản/giây, tương đương khoảng **5 giờ** chỉ cho 18 triệu item. Nếu cửa sổ xử lý là 2 giờ, hệ thống cần thông lượng trung bình ít nhất **2.500 item/giây** và nên có phần dự phòng.

Nâng concurrency trong một JVM có thể giúp nếu còn tài nguyên; nhưng nếu CPU, RAM hoặc giới hạn process đã hết, có thể phải chia công việc cho nhiều worker ở các máy khác nhau. Lúc này cần trả lời:

- Manager mô tả và gửi đơn vị công việc cho worker bằng cách nào?
- Worker biết phải đọc dữ liệu ở đâu, xử lý phạm vi nào, và báo kết quả ra sao?
- Khi worker lỗi hoặc một thông điệp được gửi lại, việc gì phải được chạy lại?
- JobRepository và trạng thái chunk/partition được cập nhật ở đâu?
- Tăng worker có tăng throughput thật hay khiến database, broker, API đích quá tải?

spring-batch-integration cung cấp các building block cho các câu hỏi điều phối này. Tuy nhiên, nó **không tự động giải quyết** nút thắt hạ tầng hay đảm bảo kết quả không trùng khi nghiệp vụ không idempotent.

## 2. Khi nào cần module này, khi nào không?

Một số kỹ thuật scaling của Spring Batch có thể được triển khai ngay trong cùng ứng dụng mà không cần giao tiếp giữa các tiến trình.

| Nhu cầu | Hướng triển khai thường gặp | Có cần spring-batch-integration? |
| --- | --- | --- |
| Nhiều chunk của một step chạy bằng các thread cục bộ | Multi-threaded step với TaskExecutor | Không bắt buộc |
| Nhiều step/flow độc lập chạy song song trong một job | Parallel steps/split flows | Không bắt buộc |
| Một step chia nhiều vùng dữ liệu xử lý trên cùng JVM | Local partitioning | Không bắt buộc |
| Manager gửi chunk tới worker chạy ở tiến trình khác | Remote chunking | Có ích trực tiếp; module cung cấp hạ tầng Batch/Integration |
| Manager chia partition cho các worker ở tiến trình/máy khác nhau | Remote partitioning | Có ích trực tiếp; module cung cấp builder và thành phần messaging |
| Dịch vụ khác gửi lệnh bắt đầu một batch job | Message-driven job launching | Module cung cấp JobLaunchingMessageHandler |

Điểm mấu chốt: **phân biệt “chạy đồng thời” với “xử lý phân tán”.** Nhiều thread trong một process chia sẻ một không gian bộ nhớ; nhiều worker phân tán cần thông điệp, giao thức nhận kết quả, triển khai độc lập và ứng phó lỗi mạng.

Việc có khả năng chạy phân tán không có nghĩa lúc nào cũng phải dùng nó. Nếu cải thiện truy vấn, batch write hoặc local partitioning đã đáp ứng batch window, thêm broker và worker có thể tăng chi phí mà không thêm nhiều lợi ích.

## 3. Vai trò thứ nhất: khởi chạy batch job qua thông điệp

Trong nhiều hệ thống, batch job không chỉ chạy theo lịch cố định. Một sự kiện như “đã chốt số liệu ngày”, “đã nhận file đối tác”, hoặc “đơn hàng đã đủ điều kiện đối soát” có thể là tín hiệu bắt đầu job.

Spring Batch có thể được khởi chạy từ mã ứng dụng thông qua **JobLauncher**. Module spring-batch-integration bổ sung **JobLaunchingMessageHandler** và **JobLaunchRequest** để nối hành động khởi chạy job với một luồng thông điệp.

~~~mermaid
flowchart LR
    A["Sự kiện từ scheduler / API / hệ thống khác"] --> B["Message channel"]
    B --> C["JobLaunchingMessageHandler"]
    C --> D["JobLauncher"]
    D --> E["Job / Steps"]
    E --> F[("JobRepository")]
~~~

**Luồng ý tưởng:**

1. Hệ thống nhận một sự kiện hợp lệ và chuyển thành yêu cầu khởi chạy gồm job cần chạy và JobParameters phù hợp.
2. Message đi tới channel được nối với JobLaunchingMessageHandler.
3. Handler gọi JobLauncher để tạo/bắt đầu JobExecution theo quy tắc Spring Batch.
4. Các bước của job chạy và ghi metadata thực thi vào JobRepository.
5. Hệ thống gọi lệnh có thể nhận thông tin về lần thực thi, rồi theo dõi trạng thái thực tế qua JobRepository hoặc cơ chế thông báo trạng thái được thiết kế riêng.

### Ví dụ mã Java tối giản

Ví dụ sau minh họa việc tạo handler và flow trong một ứng dụng đã cấu hình Spring Batch, Spring Integration cùng các bean Job/JobLauncher:

~~~java
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.integration.launch.JobLaunchingMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class BatchLaunchIntegrationConfig {

    @Bean
    public JobLaunchingMessageHandler jobLaunchingMessageHandler(
            JobLauncher jobLauncher) {
        return new JobLaunchingMessageHandler(jobLauncher);
    }

    @Bean
    public IntegrationFlow batchLaunchFlow(
            JobLaunchingMessageHandler handler) {
        return IntegrationFlow
                .from("batchLaunchRequests")
                .handle(handler)
                .get();
    }
}
~~~

Channel **batchLaunchRequests** ở đây là điểm vào của flow. Cách nhận request từ HTTP, queue hoặc scheduler là một cấu hình khác; ví dụ chưa triển khai security, xác thực sự kiện hay định tuyến lỗi.

Để tạo lệnh, hệ thống có thể dùng đối tượng **JobLaunchRequest** mang Job và JobParameters. Đừng dùng một giá trị thời gian ngẫu nhiên làm tham số định danh cho mọi lần nhận lại thông điệp: nếu cùng một sự kiện được gửi hai lần nhưng có JobParameters định danh khác nhau, Spring Batch có thể coi đó là hai JobInstance khác nhau và chạy trùng nghiệp vụ.

**Lưu ý về bất đồng bộ:** JobLaunchingMessageHandler sử dụng JobLauncher; hành vi handler trả kết quả trước hay sau khi job hoàn tất phụ thuộc cấu hình JobLauncher. Nhận được phản hồi “đã khởi chạy” không đồng nghĩa job đã hoàn tất thành công. Hệ thống điều phối phải quan sát trạng thái JobExecution theo cách phù hợp.

## 4. Vai trò thứ hai: remote chunking

**Remote chunking** chia một chunk-oriented step thành hai phần: manager đảm nhiệm **đọc dữ liệu, tạo chunk và gửi yêu cầu**, còn worker đảm nhiệm **xử lý và ghi chunk** rồi gửi kết quả về.

~~~mermaid
flowchart TB
    SRC[("Nguồn dữ liệu")] --> READER["Manager: ItemReader"]
    READER --> CHUNK["Đóng gói ChunkRequest"]
    CHUNK --> REQ[("Request channel / broker")]
    REQ --> W1["Worker A: Processor → Writer"]
    REQ --> W2["Worker B: Processor → Writer"]
    REQ --> W3["Worker C: Processor → Writer"]
    W1 --> REP[("Reply channel / broker")]
    W2 --> REP
    W3 --> REP
    REP --> MGR["Manager nhận ChunkResponse"]
    MGR --> META[("Theo dõi trạng thái step")]
~~~

### Cách thực thi

1. **Manager** dùng ItemReader lấy các item và tạo những nhóm item theo chunk size đã cấu hình.
2. Các chunk được chuyển thành message theo giao thức remote chunking và gửi tới một **request channel**.
3. Một trong các **worker** nhận chunk, chạy ItemProcessor/ItemWriter và xử lý giao dịch ghi phù hợp.
4. Worker gửi **response** để manager biết kết quả xử lý.
5. Manager theo dõi các chunk đã gửi, những phản hồi đang chờ và trạng thái step để xác định thời điểm kết thúc hoặc thất bại.

Các thành phần thường thấy ở mức cấu hình là **RemoteChunkingManagerStepBuilder** và **RemoteChunkingWorkerBuilder**. Tên phương thức khởi tạo, yêu cầu transaction manager và wiring cụ thể phụ thuộc phiên bản Spring Batch; cần dùng API tương ứng với phiên bản của dự án.

### Tại sao remote chunking có thể tăng tốc?

Remote chunking hữu ích khi đọc dữ liệu từ nguồn là tương đối nhanh và tập trung được, nhưng phần **process/write** tốn thời gian hoặc cần phân phối tới nhiều máy.

Ví dụ: manager đọc 50.000 bản ghi/giây từ bảng staging, nhưng mỗi item cần tính toán tốn CPU. Nếu có thể phân phối các chunk độc lập cho nhiều worker, tổng throughput xử lý có cơ hội tăng miễn là broker và hệ thống đích đáp ứng được.

Ngược lại, **manager vẫn là nơi đọc và tạo chunk**. Nếu ItemReader chỉ lấy được 800 item/giây thì 20 worker cũng không thể nâng thông lượng đầu-cuối vượt xa giới hạn cung cấp dữ liệu ấy.

### Điều gì thực sự được gửi qua message?

Trong remote chunking, message mang **dữ liệu item của chunk** hoặc biểu diễn của chúng theo giao thức. Vì vậy:

- Item phải được serialize/deserialize tương thích giữa manager và worker.
- Payload lớn gây áp lực lên broker, network, bộ nhớ và chi phí lưu thông điệp.
- Dữ liệu nhạy cảm cần được xử lý theo chính sách bảo mật và khả năng truy cập thông điệp.
- Request và reply phải được định tuyến và liên kết đúng với chunk/step; không tùy tiện làm mất metadata cần cho giao thức.
- Khi worker hoặc broker gặp sự cố, message có thể bị xử lý lại; writer phải chịu được trường hợp replay theo thiết kế hệ thống.

**Không nên hiểu “remote” là tự động exactly-once.** Giao dịch commit ở database đích và xác nhận xử lý message ở broker thường không thuộc một giao dịch nguyên tử chung. Nếu worker ghi thành công nhưng mất reply, hệ thống cần quy tắc rõ ràng để khôi phục và chống trùng tác động nghiệp vụ.

## 5. Vai trò thứ ba: remote partitioning

**Remote partitioning** chia một step logic thành các **partition**, mỗi partition được thực thi bằng một StepExecution riêng. Manager quyết định các vùng dữ liệu; worker được giao vùng dữ liệu và tự thực hiện đầy đủ chu trình **read → process → write**.

~~~mermaid
flowchart TB
    M["Manager: Partitioner"] --> P1["Partition A: ID 1–250000"]
    M --> P2["Partition B: ID 250001–500000"]
    M --> P3["Partition C: ID 500001–750000"]
    M --> P4["Partition D: ID 750001–1000000"]
    P1 --> Q[("Kênh yêu cầu partition")]
    P2 --> Q
    P3 --> Q
    P4 --> Q
    Q --> W1["Worker 1: Reader → Processor → Writer"]
    Q --> W2["Worker 2: Reader → Processor → Writer"]
    Q --> W3["Worker 3: Reader → Processor → Writer"]
    W1 --> JR[("JobRepository chung")]
    W2 --> JR
    W3 --> JR
    JR --> M
~~~

Trong sơ đồ, nhiều partition có thể được worker xử lý lần lượt hoặc đồng thời tùy số worker và concurrency cấu hình. Sơ đồ không ngụ ý partition luôn được gán cố định cho một máy.

### Khác với remote chunking ở đâu?

Manager của remote partitioning **gửi mô tả công việc**, chẳng hạn khoảng ID, ngày giao dịch hoặc file cần xử lý. Worker sử dụng thông tin trong **ExecutionContext** của partition để tạo reader riêng, đọc trực tiếp phần dữ liệu cần xử lý, xử lý và ghi kết quả. Thông thường các worker remote partitioning cần quyền truy cập vào **JobRepository chung** của hệ thống Spring Batch và các tài nguyên nguồn/đích cần thiết.

Vì không phải gửi từng item qua manager, remote partitioning thường phù hợp hơn khi dữ liệu đầu vào có thể chia độc lập và worker có thể truy cập nguồn dữ liệu. Chi phí message có thể giảm đáng kể so với chuyển toàn bộ chunk.

Các thành phần hỗ trợ cấu hình có tên **RemotePartitioningManagerStepBuilder** và **RemotePartitioningWorkerStepBuilder**. Chúng kết nối cơ chế partitioning của Spring Batch với các message channel và cơ chế thu thập kết quả worker. Cấu hình cách manager nhận kết quả có thể phụ thuộc cơ chế messaging hoặc metadata repository theo API và phiên bản sử dụng.

### Thiết kế partition an toàn

Ví dụ partition theo khoảng ID của bảng giao dịch:

| Partition | minId | maxId | Điều kiện đọc |
| --- | ---: | ---: | --- |
| p0 | 1 | 250.000 | ID từ 1 đến 250.000 |
| p1 | 250.001 | 500.000 | ID từ 250.001 đến 500.000 |
| p2 | 500.001 | 750.000 | ID từ 500.001 đến 750.000 |
| p3 | 750.001 | 1.000.000 | ID từ 750.001 đến 1.000.000 |

Manager đặt biên trong ExecutionContext, worker đọc đúng phạm vi của mình. Nếu các khoảng không giao nhau và bao phủ đầy đủ đầu vào đã chốt, hệ thống tránh được việc hai worker đọc một bản ghi chỉ vì khoảng partition chồng lấn.

Ví dụ lớp tạo các partition theo khoảng ID (dùng để minh họa thuật toán, chưa bao gồm bước truy vấn dữ liệu hay cấu hình remote messaging):

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class IdRangePartitioner implements Partitioner {

    private final long maxId;

    public IdRangePartitioner(long maxId) {
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        if (maxId <= 0) {
            return partitions;
        }

        int count = Math.max(1, gridSize);
        long blockSize = maxId / count + (maxId % count == 0 ? 0 : 1);

        for (int i = 0; i < count; i++) {
            long minId = 1L + i * blockSize;
            if (minId > maxId) {
                break;
            }
            long maxPartitionId = Math.min(maxId, minId + blockSize - 1);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", minId);
            context.putLong("maxId", maxPartitionId);
            partitions.put("partition-" + i, context);
        }
        return partitions;
    }
}
~~~

Reader của worker cần có phạm vi theo **stepExecutionContext**, chẳng hạn minId/maxId, và phải giới hạn cả hai đầu điều kiện đọc. Ví dụ phân hoạch này giả định ID dương từ 1 đến maxId và dataset cần xử lý đã được xác định; với thực tế có nhiều khoảng trống, dữ liệu đang thay đổi hoặc khối lượng xử lý không đồng đều, cần chọn chiến lược partition khác.

**Điểm rất quan trọng cho restart:** không nên tính lại các biên partition dựa trên dữ liệu đang liên tục thay đổi nếu điều đó làm một JobInstance khi restart có cách chia khác với lúc chạy ban đầu. Tên partition, input snapshot hoặc mốc lọc cần ổn định theo chính sách restart của job.

## 6. So sánh remote chunking và remote partitioning

| Tiêu chí | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Manager làm gì? | Đọc item, tạo/gửi chunk, nhận phản hồi | Chia dữ liệu thành partition, phân công và tổng hợp trạng thái |
| Worker làm gì? | Xử lý và ghi các item đã được gửi | Tự đọc, xử lý và ghi phần dữ liệu được giao |
| Payload đi qua message | Thường chứa item/chunk | Thường chứa mô tả partition và metadata điều phối |
| Worker có cần đọc nguồn dữ liệu? | Không bắt buộc, vì item được gửi từ manager | Thường có, vì worker tự chạy ItemReader |
| Nút thắt điển hình | Reader/manager, message throughput và kích thước payload | Data source/target, lệch tải partition, JobRepository, giới hạn worker |
| Mô hình trạng thái chính | Manager theo dõi chunk và phản hồi; worker xử lý từ thông điệp | Mỗi partition có StepExecution/ExecutionContext riêng |
| Khả năng chia việc | Phù hợp khi không dễ chia nguồn đọc nhưng có thể chia chunk | Phù hợp khi input chia được thành các vùng độc lập, ổn định |
| Phục hồi | Cần kiểm tra tình huống gửi lại chunk và tính idempotent của output | Cần kiểm tra trạng thái StepExecution và khả năng chạy lại partition |
| Chi phí messaging | Có thể cao vì gửi nhiều chunk và item | Thường thấp hơn nếu mỗi partition xử lý nhiều item |

### Ví dụ lựa chọn

**Tình huống A – phân tích dữ liệu từ nguồn đọc tập trung:** Một nguồn cung cấp stream dữ liệu chỉ cho phép đọc tuần tự, còn tính toán trên từng item độc lập, tốn CPU. Remote chunking có thể giúp phân tải phần xử lý cho các worker mà không phải chia nguồn đọc.

**Tình huống B – nhập dữ liệu từ các file riêng:** Có 400 file CSV độc lập nằm trong kho lưu trữ mà mọi worker đều truy cập được. Mỗi partition nhận danh sách file hoặc một file cụ thể, tự đọc và ghi dữ liệu. Remote partitioning thường rõ ràng, giảm việc gửi toàn bộ nội dung file qua message.

**Tình huống C – cập nhật một bảng DB đang có lock contention:** Nếu database đã bão hòa vì ghi, cả hai mô hình đều có thể làm tình hình tệ hơn. Cần tối ưu SQL, chiến lược khóa, batch write, index, tần suất commit, hoặc hạ mức đồng thời trước khi mở rộng thêm worker.

## 7. Các khối cấu hình phải phối hợp

Một hệ thống dùng spring-batch-integration thường có các khối sau:

~~~mermaid
flowchart TB
    subgraph CTRL["Điều phối / Manager"]
       JOB["Job / Manager Step"]
       CHANNELS["Request & Reply Channels"]
    end
    subgraph TRANS["Spring Integration + Transport"]
       ADAPTER["Gateway / Adapter / Serialization"]
       BROKER[("Message broker")]
    end
    subgraph WORK["Worker instances"]
       WA["Worker A"]
       WB["Worker B"]
    end
    subgraph PERSIST["Trạng thái và dữ liệu"]
       JR[("JobRepository")]
       DB[("Data source / Data sink")]
    end

    JOB <--> CHANNELS
    CHANNELS <--> ADAPTER
    ADAPTER <--> BROKER
    BROKER <--> WA
    BROKER <--> WB
    JOB <--> JR
    WA <--> JR
    WB <--> JR
    WA <--> DB
    WB <--> DB
~~~

Sơ đồ là kiến trúc tổng quát thiên về remote partitioning. Với remote chunking, manager còn đọc trực tiếp từ data source và worker không nhất thiết cần tương tác với JobRepository giống remote partitioning. Cách nối từng bean hoặc topology chính xác phụ thuộc phiên bản thư viện và thiết kế giao vận.

### 7.1. Dependency

Nếu sử dụng Gradle Kotlin DSL và dự án có cơ chế quản lý phiên bản phụ thuộc Spring nhất quán, dependency có thể được khai báo như sau:

~~~kotlin
dependencies {
    implementation("org.springframework.batch:spring-batch-integration")
    implementation("org.springframework.integration:spring-integration-core")

    // Chỉ bổ sung adapter thực sự sử dụng, ví dụ:
    // implementation("org.springframework.integration:spring-integration-amqp")
}
~~~

Thư viện transport, client broker và cấu hình serialization cần thêm theo môi trường triển khai. Không nên chốt tùy tiện phiên bản riêng cho Batch và Integration nếu đang dùng dependency management của Spring Boot/BOM; phải kiểm tra chúng tương thích trong dự án.

### 7.2. Message channel và adapter

**MessageChannel** là abstraction cho việc gửi và nhận thông điệp trong ứng dụng. Một channel nội bộ không tự đảm bảo bền vững qua restart. **Spring Integration adapter** kết nối message flow với broker hoặc hệ thống bên ngoài.

Trong môi trường production cần xác định rõ:

- **Request channel**: manager gửi yêu cầu cho worker.
- **Reply channel**: kết quả xử lý được gửi về nơi manager theo dõi.
- **Delivery semantics**: khi nào message được xác nhận đã nhận/xử lý; có khả năng gửi lặp không?
- **Correlation**: thông điệp thuộc JobExecution, StepExecution, chunk hoặc partition nào?
- **Serialization**: manager và worker có đọc hiểu cùng payload/context khi triển khai khác phiên bản không?
- **Backpressure**: khi worker chậm, manager có giới hạn số request đang bay (in-flight) và độ dài queue không?
- **Security**: chứng thực broker, phân quyền channel, mã hóa đường truyền và tránh đặt dữ liệu bí mật không cần thiết trong payload.

Không nên tùy ý thay đổi những header/correlation identifier mà các thành phần remote chunking hoặc partitioning yêu cầu; nếu adapter tự định nghĩa envelope, cần bảo toàn phần metadata giao thức.

### 7.3. JobRepository và ExecutionContext

**JobRepository** lưu thông tin JobInstance, JobExecution và StepExecution. **ExecutionContext** lưu trạng thái cần thiết để step/partition có thể khôi phục theo cơ chế Spring Batch.

Trong remote partitioning, manager và worker thường được cấu hình kết nối tới cùng kho metadata Batch, nhưng phải xác định topology cụ thể cho phiên bản và cách triển khai. Việc dùng chung metadata store **không đồng nghĩa** các worker phải dùng cùng một object Java hay bộ nhớ JVM.

ExecutionContext nên chứa dữ liệu mô tả công việc **ngắn, ổn định, có thể serialize**, chẳng hạn biên ID hoặc tên file. Không nên nhét hàng triệu item, kết nối DB đang mở hay object không hỗ trợ serialize vào context.

## 8. Thread safety: điều gì thay đổi khi có nhiều worker?

Việc tách worker thành nhiều process tránh được một số race condition do nhiều thread cùng sửa **một instance** Reader/Writer trong JVM. Tuy nhiên vẫn còn các rủi ro khi nhiều worker cùng truy cập **tài nguyên bên ngoài**.

Ví dụ hai partition cùng cập nhật một tài khoản tổng hợp có thể xảy ra lost update hoặc lock contention dù mỗi worker có bộ nhớ hoàn toàn riêng. Ranh giới partition phải dựa trên khóa nghiệp vụ, không chỉ dựa trên việc chia số lượng item cho đều.

Các nguyên tắc quan trọng:

1. **Độc lập đầu vào:** mỗi partition xử lý đúng phạm vi, không bỏ sót hoặc lặp item vì chia vùng chồng nhau.
2. **An toàn đầu ra:** unique key, upsert, transaction, versioning hoặc cơ chế chống ghi trùng theo yêu cầu nghiệp vụ.
3. **Không giả định thứ tự toàn cục:** chunk/partition khác nhau có thể hoàn thành theo thứ tự khác nhau.
4. **Giới hạn tài nguyên chia sẻ:** số worker, DB connection pool, API quota, disk/network và khả năng chịu tải của metadata database.
5. **Cấu hình StepScope đúng:** tạo state gắn với StepExecution/partition tương ứng; tránh giữ state biến đổi trong singleton dùng chung không kiểm soát.

Remote chunking đặc biệt cần xem xét mọi side effect mà Processor hoặc Writer tạo ra. Một yêu cầu được phát lại sau sự cố broker có thể gọi API hoặc ghi DB lần nữa nếu không được kiểm soát.

## 9. Retry, restart và xử lý lỗi

Một hệ thống batch phân tán có ít nhất **hai kiểu lỗi**: lỗi nghiệp vụ hoặc dữ liệu trong step và lỗi giao tiếp/triển khai giữa manager, broker, worker. Một chính sách retry duy nhất không thể giải quyết tất cả.

| Tình huống lỗi | Rủi ro | Điều cần thiết kế/kiểm thử |
| --- | --- | --- |
| Worker chết trước khi ghi kết quả | Partition/chunk chưa hoàn tất | Cơ chế phát hiện timeout, redelivery, khôi phục trạng thái |
| Worker commit DB rồi mất reply | Manager chưa biết kết quả, có thể nhận xử lý lại | Idempotent write, khóa nghiệp vụ, cách đối soát kết quả |
| Manager restart khi còn request in-flight | Mất tracking hoặc gửi trùng request | Kho metadata bền vững, trạng thái broker, quy tắc restart |
| Broker tạm mất kết nối | Request/reply trễ hoặc thất lạc nếu channel không bền vững | Retry transport có giới hạn, queue durability, monitoring |
| Một partition có dữ liệu lỗi | StepExecution thất bại hoặc skip nhiều item | Chính sách skip/retry theo lỗi, báo cáo bản ghi lỗi |
| Hai worker cùng ghi một bản ghi tổng hợp | Lock contention hoặc sai lệch kết quả | Thiết kế partition theo khóa, kiểm soát transaction và locking |
| Worker xử lý quá chậm | Queue backlog, quá batch window | Giới hạn in-flight, phân phối lại, giảm batch size khi phù hợp |
| Phiên bản payload giữa worker/manager lệch | Không deserialize được message | Versioning dữ liệu, quy trình triển khai tương thích |

### Ba lớp retry phải phân biệt

- **Retry trong step** cho lỗi xử lý item hoặc ghi dữ liệu tạm thời, ví dụ deadlock có thể phục hồi. Cần giới hạn số lần và áp dụng backoff phù hợp.
- **Redelivery của transport** cho lỗi tiếp nhận/xác nhận message. Message được gửi lại không đồng nghĩa nghiệp vụ chưa chạy.
- **Restart của Spring Batch** cho JobExecution/StepExecution thất bại. Restart theo metadata, checkpoint và JobParameters có thể tái thực hiện một phần công việc.

Ba lớp trên có thể tương tác. Nếu mỗi lớp retry ba lần không được phối hợp, một lỗi có thể dẫn tới nhiều lần gọi downstream ngoài dự kiến. Vì vậy phải xác định ai sở hữu retry của từng loại lỗi, giới hạn tổng tác động và cách theo dõi replay.

**Checkpoint chỉ giải quyết phần việc thuộc giao dịch và trạng thái được Spring Batch kiểm soát.** Nếu Worker gọi một dịch vụ ngoài rồi database rollback, lời gọi ấy có thể đã thành công. Với side effect không transaction chung, nên dùng idempotency key, transactional outbox/inbox hoặc cơ chế đối soát thích hợp.

### Dead-letter queue (DLQ) có vai trò gì?

Một thông điệp không thể xử lý sau số lần thử hữu hạn có thể được đưa vào DLQ theo chính sách broker/adapter. Điều này giúp nhóm vận hành điều tra dữ liệu và lỗi giao vận. Tuy nhiên DLQ **không tự đánh dấu StepExecution thành COMPLETED**, cũng không sửa dữ liệu nghiệp vụ. Cần quy trình xác định có được phát lại, sửa dữ liệu, restart job hay hủy job.

## 10. Đo hiệu năng và quan sát toàn tuyến

Khi chia việc qua message, thời gian job không chỉ còn là thời gian Reader/Processor/Writer. Phải đo **toàn tuyến**, từ lúc manager tạo yêu cầu đến khi worker commit và manager ghi nhận hoàn thành.

| Chỉ số | Câu hỏi hỗ trợ |
| --- | --- |
| Job/step elapsed time, read/write/skip/rollback count | Job có đạt batch window và xử lý đủ dữ liệu không? |
| Throughput cuối tuyến (item/giây) | Scale thêm worker có cải thiện thực tế không? |
| Request queue depth và tuổi message | Broker có đang tích backlog không? |
| Worker active/idle, item/giây theo worker | Worker có được phân tải đều không? |
| Số request in-flight, thời gian chờ reply | Manager có đang gửi nhanh hơn khả năng hoàn tất không? |
| Thời gian từng partition và phân bố item/partition | Có partition bị lệch tải hoặc bị “đuôi dài” không? |
| Retries, redeliveries, timeout, DLQ count | Có lỗi bị che dưới throughput nhìn có vẻ cao không? |
| CPU, heap, GC, DB connections, lock waits, IOPS | Tài nguyên nào đã chạm trần? |
| Sai lệch đối soát và duplicate business key | Tốc độ có đánh đổi tính đúng đắn không? |

Không được chỉ nhìn tổng số message được broker chuyển đi. **Message throughput khác với item throughput và khác với số item được commit thành công.** Một message có thể là một chunk lớn, một partition hoặc một lệnh retry; còn hệ thống đích có thể đã rollback một phần.

### Ví dụ đánh giá thử nghiệm

Giả sử một step cần xử lý 6 triệu item. Nhóm thử remote partitioning với các mức worker khác nhau:

| Số worker | Thời gian hoàn tất | Throughput gần đúng | Diễn giải |
| ---: | ---: | ---: | --- |
| 1 | 150 phút | 667 item/giây | Baseline giả định |
| 2 | 82 phút | 1.220 item/giây | Tăng rõ rệt |
| 4 | 48 phút | 2.083 item/giây | Có lợi nhưng không tuyến tính |
| 8 | 45 phút | 2.222 item/giây | Lợi ích giảm mạnh, cần kiểm tra DB/queue |

Các con số là **ví dụ minh họa, không phải benchmark của Spring Batch**. Nếu ở mức tám worker, DB connection pool gần cạn và rollback tăng, chọn bốn worker có thể đem lại vận hành ổn định và tiết kiệm chi phí hơn. Mục tiêu tối ưu là **thông lượng ổn định với kết quả đúng**, không phải số worker lớn nhất.

## 11. Quy trình chọn kiến trúc phù hợp

~~~mermaid
flowchart TD
    A["Xác định batch window và đo baseline"] --> B{"Nút thắt ở đâu?"}
    B -->|"SQL, write hoặc API đích"| C["Tối ưu nguồn/đích và đo lại"]
    B -->|"Có nhiều step độc lập"| D["Parallel steps"]
    B -->|"Một step xử lý nặng"| E{"Có chia nguồn thành vùng ổn định không?"}
    E -->|Có| F{"Một JVM đủ tài nguyên?"}
    F -->|Có| G["Local partitioning"]
    F -->|Không| H["Remote partitioning"]
    E -->|"Không dễ chia"| I{"Manager đọc đủ nhanh và item có thể chuyển qua message?"}
    I -->|Có| J["Đánh giá remote chunking"]
    I -->|Không| K["Tối ưu/chuyển đổi chiến lược đọc hoặc xử lý"]
    A --> L{"Chỉ cần khởi chạy theo sự kiện?"}
    L -->|Có| M["Message-driven job launching"]
~~~

### Trước khi chọn remote chunking

Hãy kiểm tra rằng nguồn đọc tập trung có đủ throughput, payload có thể gửi qua broker trong giới hạn kích thước, tỷ lệ thời gian process/write đủ lớn để bù chi phí messaging và writer có phương án xử lý replay.

### Trước khi chọn remote partitioning

Hãy kiểm tra ranh giới dữ liệu độc lập, nguồn đọc được từng worker truy cập, metadata JobRepository có thể sử dụng ổn định, các partition không chồng lấn và chiến lược restart giữ được cùng một tập dữ liệu logic.

### Trước khi đưa hệ thống lên production

Cần có kiểm thử job chạy bình thường, dừng manager, dừng một worker giữa chunk, ngắt broker tạm thời, lỗi ghi DB sau khi đã có side effect ngoài transaction, phát lại thông điệp và restart job. Sau mỗi tình huống, đối soát dữ liệu và kiểm tra không còn partition hoặc chunk treo.

## 12. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Thêm spring-batch-integration là job tự chạy đa máy.” | Cần cấu hình manager/worker, transport, channel, môi trường triển khai và chính sách lỗi. |
| “Spring Integration là broker.” | Nó cung cấp messaging abstraction, flow và adapter; broker bền vững là thành phần khác nếu kiến trúc yêu cầu. |
| “Remote chunking và remote partitioning chỉ khác tên.” | Remote chunking gửi các item/chunk; remote partitioning gửi mô tả phạm vi và worker tự đọc. |
| “Càng nhiều worker càng nhanh.” | Manager, DB, broker, network, lock và API đích có thể trở thành giới hạn. |
| “Có JobRepository thì side effect chắc chắn exactly-once.” | Giao dịch và checkpoint không đảm bảo atomicity với mọi broker hoặc dịch vụ ngoài. |
| “Mỗi partition là một thread dùng chung Reader.” | Trong remote partitioning, mỗi partition có StepExecution và có thể chạy ở JVM khác với state Reader riêng. |
| “Broker nhận message nghĩa là job đã hoàn thành.” | Phải theo dõi kết quả worker và trạng thái JobExecution/StepExecution thực tế. |
| “Retry nhiều lần là an toàn.” | Cần tính đến trùng tác động, giới hạn retry, DLQ, backoff và idempotency. |

## 13. Kết luận và câu hỏi tự kiểm tra

Vai trò của **spring-batch-integration** trong chương **Spring Batch Integration** là giúp Batch phối hợp với cơ chế messaging để **khởi chạy job theo sự kiện** và **phân tán công việc giữa manager và worker**. Hai mô hình đáng phân biệt nhất là:

- **Remote chunking:** manager đọc và gửi chunk; worker xử lý/ghi. Phù hợp khi đọc tập trung nhưng xử lý hoặc ghi có thể tách sang nhiều worker.
- **Remote partitioning:** manager chia các vùng dữ liệu; mỗi worker tự read/process/write trong phạm vi partition. Phù hợp khi dữ liệu chia được một cách ổn định và worker có thể tự truy cập đầu vào.

Khi lựa chọn, hãy bắt đầu bằng số liệu về throughput, batch window và nút thắt, sau đó xem xét độ độc lập của dữ liệu, khả năng chia partition, chi phí truyền message và giới hạn CPU/DB/network. Cuối cùng, đánh giá **thread safety, idempotency, retry/restart, JobRepository, monitoring và khả năng đối soát** như các yêu cầu bắt buộc của hệ thống production.

Để kiểm tra mức hiểu, hãy tự trả lời: **(1)** Worker remote chunking và remote partitioning khác nhau ở bước đọc dữ liệu như thế nào? **(2)** Vì sao một message được gửi lại có thể tạo bản ghi trùng? **(3)** Khi manager đã đủ CPU nhưng database ghi chậm, thêm worker có giúp ích không? **(4)** Khi partitioning, vì sao cần giữ biên dữ liệu ổn định khi restart?

Trả lời chắc chắn được các câu hỏi này là nền tảng để triển khai scaling operations Spring Batch theo kiến trúc có thể vận hành và khôi phục đáng tin cậy.
