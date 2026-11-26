# API scaling thay đổi theo Spring Batch

**Chương:** Tương thích phiên bản  
**Module:** SPRING_BATCH_SCALING_OPERATIONS  
**Mốc thông tin tham chiếu:** 26/11/2026. Các ví dụ chỉ rõ dòng phiên bản; cần kiểm tra lại tài liệu và Javadoc đúng bản đang triển khai khi nâng cấp.

Spring Batch cung cấp nhiều cách tăng thông lượng: **multi-threaded step**, **parallel steps**, **partitioning**, **remote chunking**, **remote partitioning** và một số hình thức chia việc trong hoặc ngoài JVM. Những mô hình xử lý này vẫn phục vụ cùng nhu cầu: hoàn thành khối dữ liệu lớn trong batch window, nhưng **API cấu hình và ngữ nghĩa concurrency có thể thay đổi giữa các phiên bản**.

Một đoạn mã chạy với Spring Batch 5 không mặc nhiên có cùng hành vi khi biên dịch trên Spring Batch 6. Có thay đổi đơn thuần là package hoặc tên builder, nhưng cũng có thay đổi tác động trực tiếp đến **transaction boundary, thread safety, retry/restart, JobRepository** và cách đo hiệu năng.

Bài này giúp đọc đúng ví dụ scaling trong các thế hệ **Spring Batch 4.x, 5.x, 6.0 và 6.1**, nhận diện điểm cần sửa khi migration, và lựa chọn kiến trúc phù hợp tài nguyên thực tế. Trọng tâm là **API scaling thay đổi theo Spring Batch**, không phải hướng dẫn nâng cấp tùy tiện mọi thư viện của ứng dụng.

## 1. Luôn chốt phiên bản trước khi sao chép ví dụ

Một ví dụ có vẻ hợp lý có thể sai vì người viết đang dùng phiên bản khác. Trước khi áp dụng, cần biết tối thiểu:

- Phiên bản **Spring Batch Core**, **spring-batch-integration** nếu dùng remote processing.
- Phiên bản **Spring Boot**, **Spring Framework**, **Spring Integration** và Java runtime/compiler.
- Cách ứng dụng cấu hình **JobRepository**, **DataSource**, transaction manager và executor.
- Mô hình đang chạy: multi-threaded step, parallel flows, local chunking, local partitioning hay remote worker.
- Ví dụ được lấy từ **tài liệu versioned** hay từ một bài viết không ghi phiên bản.

### 1.1. Bản đồ thế hệ thường gặp

| Thế hệ Batch | Nền tảng chính | Điểm cần nhớ khi học scaling |
| --- | --- | --- |
| **4.x** | Thế hệ Spring Framework 5; thường gặp trong ứng dụng Boot 2.x | Nhiều ví dụ dùng \`StepBuilderFactory\`, \`JobBuilderFactory\`, \`chunk(size)\`; cơ chế step đa luồng kiểu cũ |
| **5.x** | Spring Framework 6, **Java 17+**, Spring Integration 6 và hệ Jakarta EE 9 | Dùng \`new StepBuilder(name, jobRepository)\`, \`chunk(size, transactionManager)\`; đổi kiểu dữ liệu metrics/counter và một số cấu hình metadata |
| **6.0.x** | Spring Framework 7, **Java 17+**, Spring Integration 7 | \`chunk(size).transactionManager(tx)\` dùng chunk engine mới; concurrency model thay đổi; thêm local chunking, phân tách repository JDBC |
| **6.1.x** | Spring Framework 7.1, Spring Integration 7.2 | Bổ sung \`RemoteChunkingManagerBuilder\`; async/local chunking API chuyển sang \`spring-batch-core\`; có thêm các thay đổi builder và metadata |

Bảng trên là **định hướng theo dòng sản phẩm**. Các bản patch/minor có thể bổ sung hoặc loại bỏ API cụ thể. Ở thời điểm cập nhật bài (26/11/2026), **Spring Batch 6.1.0 đã phát hành GA ngày 19/11/2026**; đọc tài liệu [6.1](https://docs.spring.io/spring-batch/reference/) khi dùng 6.1 và đọc tài liệu [5.2](https://docs.spring.io/spring-batch/reference/5.2/) khi duy trì nhánh 5.2.

**Spring Boot cũng quản lý bộ phiên bản phụ thuộc.** Ví dụ Spring Boot 4.2.x thuộc thế hệ tương thích Spring Batch 6.1.x; các bản Boot 3.x thường sử dụng Batch 5.x. Không tự trộn Batch 6 vào một ứng dụng Boot 3 chỉ vì Gradle/Maven cho phép khai báo version: cần kiểm tra toàn bộ Spring Framework, Integration, transaction và runtime. Tham chiếu bảng [Spring project generations](https://spring.io/projects/generations/).

### 1.2. Đừng dùng một tài liệu “latest” để nâng mọi dự án

Một trang \`/reference/scalability.html\` không có số phiên bản rõ ràng thường chuyển đến tài liệu bản ổn định mới. Vì vậy:

- **Dự án Batch 5.2:** dùng \`/reference/5.2/scalability.html\` để xem chính xác ngữ nghĩa step của 5.2.
- **Dự án Batch 6.0:** dùng \`/reference/6.0/scalability.html\`, đối chiếu migration guide 6.0.
- **Dự án Batch 6.1:** dùng \`/reference/scalability.html\` khi trang đang hiển thị 6.1, và Javadoc cùng phiên bản cho builder chuyên biệt.

Trong tài liệu nội bộ nên ghi cụ thể **“ví dụ Spring Batch 5.2.x”** hoặc **“ví dụ Spring Batch 6.1.x”**, nhất là đối với các đoạn tạo step, retry policy, transaction và messaging.

## 2. Vì sao compatibility quan trọng hơn việc biên dịch thành công?

**Source compatibility** là khả năng biên dịch mã nguồn trên API mới. **Binary compatibility** là khả năng mã đã biên dịch hoạt động với thư viện được thay đổi. **Behavioral compatibility** là việc chương trình vẫn cho cùng kết quả, transaction, checkpoint và thứ tự quan sát được khi thực thi.

Đối với scaling, behavioral compatibility đặc biệt quan trọng. Chẳng hạn:

- Cùng một lời gọi \`.taskExecutor(executor)\` nhưng luồng **đọc/xử lý/ghi** tham gia concurrency theo mô hình khác nhau giữa 5.2 và 6.x.
- Mã listener vẫn có thể được chuyển đổi, nhưng thời điểm callback và transaction boundary đã đổi.
- Thư viện remote chunking có thể đổi builder, kiểu dependency hoặc giao thức message.
- Metadata có thể thay đổi; một worker bản cũ không thể được giả định tương thích với manager bản mới dù cả hai đều khởi động được.

~~~mermaid
flowchart TD
    A["Nâng Spring Batch"] --> B["Mã nguồn có biên dịch?"]
    B --> C["Bean/ứng dụng có khởi động?"]
    C --> D["Concurrency và transaction có còn đúng?"]
    D --> E["Retry, checkpoint và restart có còn đúng?"]
    E --> F["Thông lượng, độ trễ, DB/broker có đạt mục tiêu?"]
    F --> G["Đối soát đầy đủ và triển khai an toàn"]
~~~

Nếu một ứng dụng chỉ qua được hai bước đầu, chưa thể khẳng định việc migration scaling đã hoàn tất.

## 3. Thay đổi API xây dựng Job/Step: 4 → 5 → 6

### 3.1. Từ factory tự tiêm sang builder nhận JobRepository

Trong ứng dụng Batch 4.x, ví dụ phổ biến:

~~~java
// Phong cách cũ, điển hình cho Spring Batch 4.x
@Autowired
private StepBuilderFactory stepBuilderFactory;

@Bean
public Step importStep() {
    return stepBuilderFactory.get("importStep")
            .<Input, Output>chunk(100)
            .reader(reader())
            .processor(processor())
            .writer(writer())
            .build();
}
~~~

Trong Batch 5.x, \`JobBuilderFactory\` và \`StepBuilderFactory\` không còn được cung cấp tự động như các bean như trước; chúng bị deprecate để ưu tiên xây builder trực tiếp với JobRepository. Cách dùng mới:

~~~java
// Spring Batch 5.x — phần cấu hình Step minh họa
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Input> reader,
        ItemProcessor<Input, Output> processor,
        ItemWriter<Output> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<Input, Output>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Với **Batch 6.0+**, cách khai báo chunk engine mới:

~~~java
// Spring Batch 6.0/6.1 — dùng engine chunk mới
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Input> reader,
        ItemProcessor<Input, Output> processor,
        ItemWriter<Output> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<Input, Output>chunk(100)
            .transactionManager(transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

**Các đoạn trên là ví dụ cấu hình theo từng version**, với \`Input\`, \`Output\` và bean Reader/Processor/Writer do ứng dụng tự định nghĩa. Khi chép vào dự án thực phải dùng import của đúng version; đặc biệt Batch 6 di chuyển nhiều interface sang \`org.springframework.batch.infrastructure.*\`.

### 3.2. Chữ ký chunk là thay đổi có ý nghĩa

| Mã thường gặp | Thế hệ | Ý nghĩa |
| --- | --- | --- |
| \`stepBuilderFactory.get("s").chunk(100)\` | 4.x | Kiểu cấu hình cũ |
| \`new StepBuilder("s", repo).chunk(100, tx)\` | 5.x | Tạo chunk-oriented tasklet step theo engine cũ |
| \`new StepBuilder("s", repo).chunk(100).transactionManager(tx)\` | 6.x | Tạo chunk-oriented step theo engine mới |
| \`new ChunkOrientedStepBuilder<I,O>("s", repo, 100)\` | 6.x | Builder trực tiếp cho \`ChunkOrientedStep\` |

Theo migration guide Spring Batch 6, dạng \`chunk(size, tx)\` cũ vẫn có đường tương thích **được deprecate trong thế hệ 6**, nhưng không phải lựa chọn để phát triển tính năng mới. Không kết luận “chạy cùng trên 6” đồng nghĩa “ngữ nghĩa giống engine mới”.

### 3.3. Transaction manager: cái gì là tùy chọn?

Spring Batch 5 yêu cầu truyền transaction manager khi cấu hình **tasklet/chunk-oriented step theo API cũ**. Sang Batch 6, khi không truyền transaction manager, một số builder mới có thể dùng **ResourcelessTransactionManager** mặc định.

Điều này **không có nghĩa** được bỏ transaction manager JDBC cho step đọc/ghi database.

Ví dụ một job đối soát ghi DB cần giữ transaction đảm bảo rollback chunk khi lỗi. Nếu dùng một transaction manager không quản lý DB, có thể đánh mất giả định nguyên tử của writer. Khi migration, phải xác định **loại tài nguyên được bảo vệ** và truyền manager phù hợp, dù API không bắt buộc ở compile time.

## 4. Thay đổi lớn nhất: multi-threaded step ở 5.x khác 6.x

Đây là điểm dễ bị bỏ sót nhất trong chương scaling.

### 4.1. Spring Batch 5.2: mỗi chunk có thể chạy trên một worker thread

Tài liệu Spring Batch 5.2 mô tả rằng khi gắn \`TaskExecutor\` vào chunk-oriented step, việc **đọc, xử lý, ghi từng chunk** diễn ra trên các thread thực thi khác nhau. Thứ tự item và ranh giới chunk có thể khác xử lý tuần tự.

~~~mermaid
flowchart LR
    S["Step Batch 5.2"] --> X["TaskExecutor"]
    X --> T1["Thread A: read → process → write chunk A"]
    X --> T2["Thread B: read → process → write chunk B"]
    X --> T3["Thread C: read → process → write chunk C"]
    T1 --> D[("DataSource")]
    T2 --> D
    T3 --> D
~~~

Ví dụ Batch 5.2:

~~~java
// Phần cấu hình Step dành cho Spring Batch 5.2
return new StepBuilder("multiThreadStep", jobRepository)
        .<Trade, Trade>chunk(100, transactionManager)
        .reader(tradeReader)
        .processor(tradeProcessor)
        .writer(tradeWriter)
        .taskExecutor(taskExecutor)
        .build();
~~~

**Hệ quả:** các instance ItemReader, ItemProcessor và ItemWriter được dùng trong step đa luồng phải được đánh giá về trạng thái dùng chung. Nếu reader duy trì cursor hoặc vị trí file, có thể xảy ra đọc lặp/bỏ sót khi được nhiều thread gọi. Tùy implementation, có thể dùng cơ chế đồng bộ, thiết kế reader không trạng thái hoặc chọn partitioning. Việc khóa đồng bộ reader có thể trở thành nút thắt.

Ở Batch 5.x, tài liệu cũ còn nhắc **throttle limit** mặc định và phương thức \`.throttleLimit(...)\`. API này bị **deprecate từ 5.0**, nên không nên đưa nó vào ví dụ mới như lời khuyên mặc định; kiểm soát concurrency nên được thiết kế bằng executor/task queue thích hợp theo đúng version.

### 4.2. Spring Batch 6.x: mô hình producer–consumer mới

Spring Batch 6.0 đưa vào engine \`ChunkOrientedStep\` ổn định với mô hình concurrency dựa trên **producer–consumer**, dùng queue có giới hạn. Với multi-threaded step trên engine mới:

- **Luồng chính** đảm nhận việc **đọc và ghi** item/chunk.
- Các **worker thread** thực hiện phần **ItemProcessor** đồng thời.
- Hệ thống phối hợp kết quả để ghi chunk; khi đến ranh giới ghi, luồng chính có thể phải chờ các xử lý hoàn thành.
- **Spring transaction gắn với thread**. Processor chạy trên worker thread không mặc nhiên tham gia chunk transaction của luồng chính.

~~~mermaid
flowchart TB
    R["Main thread: ItemReader"] --> Q["Bounded queue"]
    Q --> P1["Worker A: ItemProcessor"]
    Q --> P2["Worker B: ItemProcessor"]
    Q --> P3["Worker C: ItemProcessor"]
    P1 --> M["Tập hợp kết quả chunk"]
    P2 --> M
    P3 --> M
    M --> W["Main thread: ItemWriter / chunk transaction"]
~~~

Ví dụ Batch 6.1:

~~~java
// Phần cấu hình Step dành cho Spring Batch 6.1, engine mới
return new StepBuilder("multiThreadStep", jobRepository)
        .<Trade, Trade>chunk(100)
        .transactionManager(transactionManager)
        .reader(tradeReader)
        .processor(tradeProcessor)
        .writer(tradeWriter)
        .taskExecutor(taskExecutor)
        .build();
~~~

**Ngữ nghĩa rất khác:** ItemReader và ItemWriter trong cấu hình trên không bị gọi song song bởi các processor thread theo mô hình này, nhưng **ItemProcessor phải an toàn khi gọi đồng thời**. Nếu processor thực hiện DB write, dùng transaction annotation với propagation kiểu \`MANDATORY\`, hoặc đọc dữ liệu mà cần transaction của chunk, phải kiểm thử và có thể cần tự mở transaction thích hợp trên worker thread.

Không được kết luận chỉ vì Reader/Writer được luồng chính gọi tuần tự nên ứng dụng đã chắc chắn an toàn: chúng vẫn có thể dùng tài nguyên chia sẻ với các step khác, hoặc writer đang ghi ra DB cùng các worker/partition khác.

### 4.3. Nếu muốn chạy **cả chunk** song song trong Batch 6 thì sao?

Spring Batch 6.0 giới thiệu **local chunking**. Mô hình này sử dụng \`ChunkTaskExecutorItemWriter\` để giao chunk cho các worker thread trong cùng JVM; mỗi worker có \`ChunkProcessor\` xử lý chunk.

~~~mermaid
flowchart LR
    M["Manager step / reader"] --> C["ChunkTaskExecutorItemWriter"]
    C --> A["Chunk processor A: process + write"]
    C --> B["Chunk processor B: process + write"]
    C --> D["Chunk processor C: process + write"]
~~~

Local chunking khác multi-threaded step của engine mới ở **đơn vị giao việc**: một bên giao chunk, bên kia song song hóa processing item bên trong chu trình đọc/ghi tập trung. Với local chunking, \`ChunkTaskExecutorItemWriter\` **không tự đảm nhận transaction management và toàn bộ retry/skip cho chunk processor**; delegate processor và cách cấu hình transaction phải làm rõ trách nhiệm này.

### 4.4. Bảng so sánh ngữ nghĩa

| Câu hỏi | Batch 5.2 multi-threaded step | Batch 6.x multi-threaded step (engine mới) | Batch 6.x local chunking |
| --- | --- | --- | --- |
| Đơn vị chạy song song | Cả chunk | Các lời gọi processor | Các chunk giao cho worker |
| Reader được gọi ở đâu? | Trong các worker thực thi chunk | Luồng chính | Luồng manager/reader |
| Writer được gọi ở đâu? | Trong các worker thực thi chunk | Luồng chính | Trong chunk processor của worker |
| Vấn đề thread safety nổi bật | Reader/Processor/Writer và state dùng chung | Processor, state dùng chung, transaction trên worker | ChunkProcessor, writer, transaction riêng cho chunk |
| Có thể thay thế nhau chỉ bằng đổi version? | Không | Không | Không |
| Kiểm thử bắt buộc | Đọc lặp/mất, ordering, rollback | Transaction trong processor, kết quả ghi, throughput | Transaction, retry/skip, kết quả chunk, shutdown |

## 5. Parallel steps: mô hình vẫn giữ, nhưng API và giới hạn cần kiểm tra

**Parallel steps** chạy các flow hoặc step độc lập đồng thời. Ý tưởng vẫn có mặt trong Spring Batch 4/5/6; API thường thấy là \`FlowBuilder\`, \`.split(taskExecutor)\` và \`.add(flow1, flow2)\`.

~~~java
// Ý tưởng chung; cần dùng import đúng phiên bản
Flow parallel = new FlowBuilder<SimpleFlow>("parallel")
        .split(taskExecutor)
        .add(flowOfOrders, flowOfInvoices)
        .build();
~~~

Sự độc lập của từng flow là điều kiện nghiệp vụ, không phải tính năng được bảo đảm bằng compiler. Hai flow ghi cùng một bảng hoặc cùng một file có thể cạnh tranh lock hoặc overwrite output. Khi chuyển từ Batch 5 sang 6, hãy kiểm tra package của \`Step\`, \`Job\`, listener và các bean liên quan; đồng thời đo số DataSource connection cần cho **tổng các flow đang chạy**, không chỉ tính theo một flow.

**Một lỗi migration quen thuộc:** code build được nhưng executor thực tế là synchronous hoặc bean không được gắn vào split flow, khiến các bước lại chạy tuần tự. Hãy kiểm chứng bằng timestamp StepExecution thay vì chỉ đọc cấu hình.

## 6. Partitioning: thay đổi API và package trong Batch 6

Partitioning giữ ý tưởng chia một step thành nhiều **StepExecution** có **ExecutionContext** riêng; manager chia vùng dữ liệu và worker xử lý phần việc của mình. Dù chia trong một JVM hay nhiều JVM, phải bảo đảm biên dữ liệu không chồng lấn và restart xử lý đúng partition chưa hoàn tất.

### 6.1. Đổi package interface ở Spring Batch 6

Một số lớp thuộc partition SPI đã đổi package:

| Tên | Ở Spring Batch 5.x | Ở Spring Batch 6.x |
| --- | --- | --- |
| \`Partitioner\` | \`org.springframework.batch.core.partition.support.Partitioner\` | \`org.springframework.batch.core.partition.Partitioner\` |
| \`PartitionNameProvider\` | \`org.springframework.batch.core.partition.support.PartitionNameProvider\` | \`org.springframework.batch.core.partition.PartitionNameProvider\` |
| \`PartitionStep\` | \`org.springframework.batch.core.partition.support.PartitionStep\` | \`org.springframework.batch.core.partition.PartitionStep\` |
| \`StepExecutionAggregator\` | \`org.springframework.batch.core.partition.support.StepExecutionAggregator\` | \`org.springframework.batch.core.partition.StepExecutionAggregator\` |

Đồng thời \`Step\`, \`StepExecution\` và \`StepContribution\` chuyển từ \`org.springframework.batch.core\` sang \`org.springframework.batch.core.step\`; một số class metadata chuyển sang package \`...job\` hoặc \`...job.parameters\`.

Khi IDE báo \`cannot find symbol\` sau khi nâng Batch 6, **kiểm tra migration guide trước khi thay class bằng một implementation khác có vẻ tương tự**. Nhiều lỗi chỉ là import cũ.

### 6.2. Local partitioning

Cách khai báo thường thấy:

~~~java
// Ví dụ ý tưởng partitioning cho Spring Batch 6.x
return new StepBuilder("partition.manager", jobRepository)
        .partitioner("partition.worker", partitioner)
        .step(workerStep)
        .gridSize(8)
        .taskExecutor(taskExecutor)
        .build();
~~~

\`gridSize(8)\` ảnh hưởng số phần việc được chia, **không tương đương** cam kết tám thread chạy đồng thời: concurrency còn tùy executor và partition handler. Nếu số worker/connection DB không đủ, phần việc có thể được xếp hàng.

### 6.3. Tính restartability không đến từ API builder

Ví dụ một Partitioner theo khoảng ID phải giữ được ngữ nghĩa ổn định:

~~~text
partition0 → id >= 1       AND id < 250001
partition1 → id >= 250001  AND id < 500001
partition2 → id >= 500001  AND id < 750001
partition3 → id >= 750001  AND id < 1000001
~~~

Khi migration, đừng nhân tiện thay logic phân vùng từ ID sang offset, đổi tên partition hoặc đổi kiểu serialization của ExecutionContext rồi mặc định restart job cũ vẫn an toàn. Nếu dữ liệu đang thay đổi, offset có thể làm một item xuất hiện ở partition khác khi restart.

## 7. spring-batch-integration: remote APIs có thể đổi chữ ký

Mô hình **remote chunking** và **remote partitioning** sử dụng Spring Integration để manager và worker giao tiếp bằng message. Hai phần phải thống nhất contract về payload, metadata, serialization và cơ chế xác nhận kết quả.

### 7.1. Không dùng phiên bản spring-batch-integration tùy ý

Với Batch 5.x, các thành phần tích hợp được xây trên hệ sinh thái Spring Integration 6; với Batch 6.0, nền tảng chuyển sang Spring Integration 7, và 6.1 theo Spring Integration 7.2. Cần chọn bộ phiên bản có hỗ trợ lẫn nhau và nhất quán qua dependency management.

~~~kotlin
// Gradle Kotlin DSL, trường hợp dùng Spring Boot dependency management/BOM
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-batch")
    implementation("org.springframework.batch:spring-batch-integration")
    // Adapter broker: chỉ thêm module phù hợp transport thực tế
}
~~~

Đoạn trên cố ý không hardcode version: để bộ quản lý phụ thuộc của Spring Boot phù hợp quyết định. Khi dùng build độc lập không có BOM, phải chốt tất cả version trong một compatibility matrix đã được kiểm thử.

### 7.2. Những thay đổi cụ thể khi chuyển 5 → 6

| API liên quan remote processing | Thay đổi trong Batch 6 | Cách xử lý |
| --- | --- | --- |
| \`ChunkHandler\` | Đổi tên thành \`ChunkRequestHandler\` | Sửa kiểu/import và kiểm tra các adapter dùng interface này |
| \`JobLaunchingMessageHandler(JobLauncher)\` | Constructor nhận \`JobOperator\` | Tiêm \`JobOperator\` theo cấu hình Batch 6 |
| \`JobLaunchingGateway(JobLauncher)\` | Constructor nhận \`JobOperator\` | Cập nhật bean và hợp đồng khởi chạy job |
| \`RemoteChunkingManagerStepBuilder(String)\` | Constructor cũ bị loại bỏ | Dùng builder/constructor hỗ trợ JobRepository của bản đang chạy |
| \`RemotePartitioningManagerStepBuilder(String)\` | Constructor cũ bị loại bỏ | Cấu hình theo API builder 6.x, cung cấp repository |
| \`RemotePartitioningWorkerStepBuilder(String)\` | Constructor cũ bị loại bỏ | Sửa builder theo signature mới |
| \`RemotePartitioningWorkerStepBuilder#repository(...) \` | Một đường cấu hình cũ bị loại bỏ | Dùng constructor/bean phù hợp phiên bản |
| \`RemotePartitioningWorkerStepBuilder#tasklet(tasklet)\` và \`#chunk(completionPolicy)\` | Signature cũ bị loại bỏ | Đối chiếu API 6.x trước khi tạo worker step |

**Ví dụ lỗi:** sau upgrade, IDE báo không tìm thấy constructor \`RemotePartitioningWorkerStepBuilder(String)\`. Vấn đề là signature builder thay đổi, không phải remote partitioning bị xóa khỏi Spring Batch.

### 7.3. Spring Batch 6.1 thêm RemoteChunkingManagerBuilder

Trong Spring Batch **6.1**, \`RemoteChunkingManagerBuilder\` được đưa vào để cấu hình manager dựa trên \`ChunkOrientedStep\` mới. \`RemoteChunkingManagerStepBuilder\` và factory tương ứng bị deprecate theo hướng dùng builder mới.

~~~java
// Ví dụ Spring Batch 6.1 — các biến requests/replies/reader/tx đã được cấu hình
Step managerStep = new RemoteChunkingManagerBuilder("remote.manager", jobRepository)
        .outputChannel(requests)
        .inputChannel(replies)
        .<Trade, Trade>chunk(100)
        .reader(reader)
        .transactionManager(transactionManager)
        .build();
~~~

Lưu ý đặc biệt:

- Phải cấu hình **request/reply channels trước khi gọi \`chunk(int)\`**.
- Builder đã thiết lập writer chuyên dụng gửi chunk; không thay bằng writer nghiệp vụ thông thường.
- Nếu Reader cần transaction JDBC, cung cấp transaction manager phù hợp; engine mới có mặc định resourceless.
- Mọi worker remote cần tương thích payload, serializer, message headers và nghiệp vụ xử lý.

Khi đang chạy Batch 6.0, không nên chép ví dụ \`RemoteChunkingManagerBuilder\` của 6.1 nếu API đó chưa có trên classpath.

### 7.4. Async item APIs và local chunking chuyển module trong 6.1

Các class:

- \`AsyncItemProcessor\`
- \`AsyncItemWriter\`
- \`ChunkTaskExecutorItemWriter\`

được chuyển từ \`spring-batch-integration\` sang **\`org.springframework.batch.core.step.item\` trong \`spring-batch-core\`** ở Batch 6.1. Các class cũ tại \`spring-batch-integration\` vẫn được giữ dưới dạng lớp con đã deprecate để tương thích.

Ý nghĩa: nếu ứng dụng chỉ làm **async item processing** hoặc **local chunking** mà không dùng message channel/remoting, không cần thêm \`spring-batch-integration\` chỉ để sử dụng các API này trên 6.1. Khi migration, sửa import sang module đích trước khi định bỏ dependency cũ.

## 8. JobRepository và cấu hình batch infrastructure đổi theo phiên bản

### 8.1. Spring Batch 5: JDBC infrastructure và cấu hình cũ

Ví dụ khi dùng cấu hình thủ công với Batch 5:

~~~java
// Batch 5 — minh họa cấu hình có repository JDBC
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager"
)
class BatchInfrastructureConfig {
}
~~~

### 8.2. Spring Batch 6: tách lựa chọn kho metadata

Batch 6 bổ sung annotation **\`@EnableJdbcJobRepository\`** và **\`@EnableMongoJobRepository\`**. \`@EnableBatchProcessing\` chịu trách nhiệm thuộc tính chung; cấu hình đặc thù JDBC/Mongo ở annotation tương ứng.

~~~java
// Batch 6 — ví dụ khi chủ động cấu hình JDBC repository
@EnableBatchProcessing
@EnableJdbcJobRepository(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager"
)
class BatchInfrastructureConfig {
}
~~~

Ví dụ này dành cho ứng dụng **tự cấu hình hạ tầng Batch**. Khi dùng Spring Boot auto-configuration, cần tuân theo cơ chế của Boot trước khi thêm annotation thủ công; việc thêm \`@EnableBatchProcessing\` có thể làm thay đổi đường auto-config dự kiến.

Ở Batch 6, \`DefaultBatchConfiguration\` có mặc định **resourceless batch infrastructure**. Nếu một job cần **lưu StepExecution/ExecutionContext bền vững để restart**, đặc biệt trong remote partitioning hoặc khi có nhiều worker, phải chọn **JobRepository có lưu trữ phù hợp**. ResourcelessJobRepository không phải phương án thay thế tự động cho shared JDBC repository trong một job phân tán cần restart.

Với cấu hình programmatic, \`JdbcDefaultBatchConfiguration\` và \`MongoDefaultBatchConfiguration\` là hai lựa chọn mới cho store chuyên biệt.

## 9. Các thay đổi ảnh hưởng trực tiếp đến retry/restart

### 9.1. ChunkListener trong engine mới của Batch 6

Spring Batch 6 thay đổi callback listener ở engine \`ChunkOrientedStep\`:

| Vấn đề | Engine cũ của Batch 5 | Engine mới của Batch 6 |
| --- | --- | --- |
| \`afterChunk\` | Gọi sau khi chunk transaction đã commit | Gọi **bên trong transaction**, trước commit |
| \`afterChunkError\` | Sau rollback trong ngữ cảnh transaction cũ | Thay bằng \`onChunkError(Exception, Chunk)\` khi xử lý thất bại, trước rollback |
| Lỗi ném ra từ item/step listener | Trong một số đường có thể bị xử lý như lỗi item để retry/skip | Với engine mới, listener exception được coi là lỗi nghiêm trọng, làm fail step, không theo retry/skip policy của item |

**Tình huống thực tế:** mã v5 gửi event “chunk đã commit” trong \`afterChunk\`. Nếu chuyển sang engine mới v6, callback có thể chạy **trước commit thực sự**. Hệ thống downstream đã nhận event nhưng DB sau đó rollback: dữ liệu không nhất quán. Khi nâng cấp, phải chuyển việc gửi event sang cơ chế **sau commit thực sự**, hoặc thiết kế transactional outbox phù hợp.

### 9.2. Retry và skip trong chunk engine mới

Trong Batch 6, engine chunk mới sử dụng retry support từ Spring Framework 7; API retry/skip có thể khác cách cấu hình fault tolerance cũ của Batch 5. Không chỉ copy \`.retry(...)\`, \`.retryLimit(...)\` từ code cũ rồi suy đoán chúng có cùng tác dụng trên builder mới.

Trước khi đổi engine, kiểm tra từng nhóm lỗi:

1. Lỗi đọc tạm thời.
2. Lỗi nghiệp vụ trong Processor.
3. Lỗi ghi database và rollback transaction.
4. Lỗi trong listener.
5. Lỗi gửi thông điệp giữa manager/worker.
6. Lỗi xảy ra sau khi DB commit nhưng trước khi manager nhận kết quả.

Bật retry không tạo bảo đảm **exactly-once** cho mọi tác động; cần unique key, idempotent writer, checkpoint và chính sách phát lại.

### 9.3. JobParameters, ExecutionContext và schema

Spring Batch 5 đổi mô hình JobParameters so với 4 và cập nhật định dạng metadata/serializer theo hệ sinh thái mới. Batch 6 tiếp tục thay đổi mô hình tham số, trong đó \`JobParameter\` chứa cả tên và trở thành dạng immutable; một số lớp domain, API repository và package thay đổi.

Đối với job có restart và worker remote, cần đặc biệt kiểm tra:

- **Schema metadata** của database đã nâng cấp bằng migration script/DDL phù hợp chưa.
- JobParameters/ExecutionContext cũ có được deserialize bởi phiên bản mới không.
- Tên job, step, partition và tham số định danh có bị đổi ngoài ý muốn không.
- State của reader (cursor, offset, vùng ID, file name) có còn ý nghĩa tương đương không.
- Worker đang chạy có thể ghi metadata theo schema mới không.
- Một job thất bại ở bản cũ có được phép restart trực tiếp bằng bản mới hay cần hoàn tất trên bản cũ trước.

Không nên xem khả năng *migrate metadata* là bảo đảm rằng mọi job ở trạng thái dở dang đều có thể restart an toàn sau thay đổi ngữ nghĩa ứng dụng.

## 10. Việc đổi package cũng có thể làm vỡ tầng observability

Trong Batch 5, các counter như \`readCount\`, \`writeCount\` trong \`StepExecution\` và \`StepContribution\` chuyển từ \`int\` sang \`long\`. Nếu hệ thống dùng DTO, mapper, SQL hoặc Prometheus rules với kiểu số nhỏ hơn, phải kiểm tra ép kiểu và overflow.

Tag của Micrometer metric Spring Batch được đổi tên từ 4.x sang 5.x (ví dụ tên tag gắn kèm tiền tố metric). Một dashboard cũ có thể **mất biểu đồ** sau upgrade dù job vẫn chạy thành công.

Batch 6 bổ sung quan sát qua **Java Flight Recorder** và tiếp tục thay đổi một số API/metric. Khi nâng version:

- Kiểm tra tên metric/tag thực tế trong phiên bản đang chạy.
- Đảm bảo dashboard đo **item được ghi thành công**, elapsed time, retry/rollback và queue depth.
- Đo **thread executor, DataSource connection pool, broker, database lock waits** cùng với các chỉ số Batch.
- Đánh giá đúng bottleneck trước khi so sánh hiệu năng hai version.

**Ví dụ:** sau nâng version, dashboard hiện 0 item/giây vì query dùng nhãn cũ. Điều này khác hoàn toàn việc job thật sự xử lý 0 item.

## 11. Compatibility của hệ thống phân tán không chỉ là phiên bản thư viện

Một remote partitioning hoặc remote chunking production thường có manager, nhiều worker, broker và JobRepository chung. Khi nâng cấp, cả **wire protocol**, **schema** và **thư viện** đều quan trọng.

~~~mermaid
flowchart TB
    M["Manager: Batch 5.2 / 6.1?"] --> Q["Broker / request-reply channels"]
    Q --> WA["Worker A: version nào?"]
    Q --> WB["Worker B: version nào?"]
    M --> JR[("JobRepository schema")]
    WA --> JR
    WB --> JR
    WA --> DB[("Business data")]
    WB --> DB
~~~

Không giả định rằng **manager Batch 6.1** có thể an toàn trao đổi trực tiếp với **worker Batch 5.2** chỉ vì cùng dùng message broker. Cần xác nhận thông điệp, type serialization, response payload, correlation ID, JobRepository schema và behavior của các chunk/partition có được hỗ trợ chạy lẫn version hay không.

**Cách triển khai ít rủi ro hơn khi có breaking change:**

1. Tạm ngừng nhận job/partition mới hoặc triển khai một luồng xử lý mới độc lập.
2. Để các request cũ hoàn tất, quan sát in-flight và queue backlog.
3. Đảm bảo các job cần restart có kế hoạch xử lý riêng; backup metadata và dữ liệu cần thiết.
4. Nâng các thành phần trong một môi trường kiểm thử dùng cùng contract/version trước.
5. Kiểm tra schema, serializer và metadata của cả manager/worker.
6. Chạy thử lỗi worker/manager và restart.
7. Cutover theo một đơn vị triển khai đã kiểm chứng; quan sát kết quả trước khi tăng concurrency.

Nếu cần rolling deployment hỗn hợp phiên bản, phải có **bằng chứng compatibility cụ thể**, hợp đồng message có version và kế hoạch rollback/cutover rõ ràng. Không suy đoán tương thích xuyên major version.

## 12. Ví dụ migration: 5.2 → 6.1 của một step xử lý hóa đơn

Giả sử job đọc hóa đơn từ DB, tính phí và ghi sổ kết quả. Trên Batch 5.2, nhóm vận hành dùng:

~~~java
// Batch 5.2
return new StepBuilder("invoiceStep", repo)
        .<Invoice, Result>chunk(200, tx)
        .reader(invoiceReader)
        .processor(feeCalculator)
        .writer(resultWriter)
        .taskExecutor(workerExecutor)
        .build();
~~~

Trên Batch 6.1, migration cú pháp sang engine mới là:

~~~java
// Batch 6.1
return new StepBuilder("invoiceStep", repo)
        .<Invoice, Result>chunk(200)
        .transactionManager(tx)
        .reader(invoiceReader)
        .processor(feeCalculator)
        .writer(resultWriter)
        .taskExecutor(workerExecutor)
        .build();
~~~

Dù hai cấu hình nhìn rất giống nhau, cần đánh giá:

| Thành phần | Câu hỏi sau nâng cấp |
| --- | --- |
| Reader | Trước đây bị gọi đồng thời theo chunk; nay đọc trên main thread. Reader có tạo bottleneck mới không? |
| Processor | Có thread-safe không? Có phụ thuộc transaction gắn main thread hoặc ThreadLocal không? |
| Writer | Ghi trên main thread theo engine mới; tác vụ ghi có làm chậm toàn pipeline không? |
| Transaction | \`tx\` có quản lý đúng DB đích? Processor có cần transaction riêng không? |
| Retry/skip | Policy cũ có còn gắn đúng loại lỗi và callback không? |
| JobRepository | Metadata JDBC/serializer/schema có phù hợp 6.1 và yêu cầu restart không? |
| Executor | Queue, số thread, khả năng từ chối task và shutdown có được cấu hình đúng không? |
| Hiệu năng | Throughput và thời gian job có tốt hơn theo bottleneck thực tế không? |

Nếu **writer** mới trở thành nút thắt do chạy tuần tự, cân nhắc **local chunking** hoặc **partitioning** thay vì chỉ tiếp tục tăng \`workerExecutor\`. Nếu **reader** là nút thắt, hãy tối ưu truy vấn, phân trang hoặc chia input có ranh giới ổn định để worker tự đọc.

### Khi nào giữ engine cũ trong giai đoạn chuyển tiếp?

Batch 6 còn cung cấp đường engine chunk cũ đã deprecate nhằm hỗ trợ migration từng bước. Một phương án là nâng build và dependency trước, xác minh restart, sau đó chuyển sang engine mới trong thay đổi có kiểm thử độc lập. Tuy nhiên không nên tiếp tục xây mới dựa vào API legacy chỉ vì code cũ còn chạy.

## 13. Phân biệt lỗi compile với lỗi vận hành

| Triệu chứng sau nâng cấp | Nguồn gốc thường gặp | Cách xác minh |
| --- | --- | --- |
| \`StepBuilderFactory\` không được tiêm | Factory không được expose như trước | Chuyển sang builder nhận JobRepository |
| \`chunk(100, tx)\` bị cảnh báo deprecated trên Batch 6 | API engine cũ | Đổi sang \`chunk(100).transactionManager(tx)\` sau khi kiểm tra behavior |
| Không import được \`Partitioner\` cũ | Package đã chuyển ở 6 | Dùng package \`core.partition\` đúng Javadoc |
| \`JobLaunchingMessageHandler\` constructor mismatch | Cần \`JobOperator\` trong 6 | Đổi collaborator và test launch |
| Thiếu \`RemoteChunkingManagerBuilder\` | Dự án vẫn chạy 6.0 hoặc thấp hơn | Kiểm tra artifact/version; builder mới có từ 6.1 |
| \`AsyncItemWriter\` có cảnh báo deprecated ở integration 6.1 | Class chuyển sang core | Dùng class thuộc \`core.step.item\` |
| Processor mất transaction khi nâng 6 | Engine mới chạy processor trên worker thread | Xác nhận transaction propagation/ThreadLocal |
| Step nhanh nhưng ghi trùng sau restart | Checkpoint, idempotency hoặc semantics thay đổi | Thử fail giữa chunk, đối soát theo business key |
| Dashboard biến mất | Tag/metric đã đổi | Xem metrics thực phát ra theo version |
| Remote worker không nhận được message | Payload, serializer hoặc contract không tương thích | Test end-to-end với manager/worker version đã chốt |

## 14. Quy trình kiểm thử migration scaling

Nâng cấp version là một thay đổi kiến trúc có thể gây lỗi dữ liệu. Một bộ kiểm tra phù hợp gồm bốn lớp:

### Lớp A — Kiểm tra build và dependency

- Xác nhận version được resolve bằng Gradle/Maven và dependency management.
- Không có hai phiên bản khác nhau của \`spring-batch-core\`, \`spring-batch-infrastructure\` hoặc các jar Spring Integration trong cùng classpath.
- Kiểm tra JDK, Spring Framework, Spring Boot và broker adapter tương thích.
- Biên dịch và chạy unit test cho Partitioner, Reader/Processor/Writer, handler, listener.

### Lớp B — Kiểm tra tính đúng đắn

- Dùng tập dữ liệu đã biết số lượng, business key và kết quả tổng hợp mong đợi.
- Chạy tuần tự trước, lưu snapshot đối soát.
- Chạy cấu hình có concurrency, so sánh output theo khóa; **không chỉ so sánh số lượng**.
- Kiểm tra thứ tự nếu nghiệp vụ thực sự cần order.
- Thử một partition chậm, một worker lỗi và một connection timeout.

### Lớp C — Kiểm tra restart/transaction

- Cho job fail **trước commit**, **sau commit**, trong listener, khi broker gửi lại và khi manager shutdown.
- Restart cùng JobParameters theo đúng cơ chế JobInstance; không tạo parameter khác để che lỗi replay.
- Xác nhận item đã commit không tạo tác động trùng; item chưa commit vẫn có thể xử lý lại.
- Quan sát StepExecution/ExecutionContext, retry count, rollback count và trạng thái kết thúc.

### Lớp D — Kiểm tra hiệu năng

Giữ dataset, phần cứng và tải nền gần giống giữa hai version. So sánh:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Total elapsed time | Có đáp ứng batch window không? |
| Read/processed/written item/giây | Nút thắt di chuyển từ Reader sang Processor/Writer không? |
| CPU, heap, GC, active threads | Worker có thực sự chạy đồng thời không? |
| DataSource active/pending và DB waits | Scaling có vượt tài nguyên DB không? |
| Broker backlog, in-flight requests | Remote chunk/partition có bị nghẽn không? |
| Retry/rollback, lỗi listener và duplicate key | Bản mới có giữ độ tin cậy không? |
| Thời gian từng partition | Có skew hoặc partition cuối quá chậm không? |

Một lần chạy nhanh hơn nhưng mất item hoặc không restart an toàn **không đạt yêu cầu migration**.

## 15. Ma trận kiểm thử tối thiểu cho các mô hình scaling

| Mô hình | Kiểm tra khi đổi version | Sự cố cần chủ động tạo |
| --- | --- | --- |
| Multi-threaded step | Reader/Processor/Writer được gọi trên thread nào, transaction nào | Processor exception; timeout DB; thứ tự item |
| Parallel steps | Split flow vẫn chạy đồng thời, transition status đúng | Một flow fail, các flow khác đang chạy |
| Local partitioning | Partitioner import/API, StepExecution và ExecutionContext | Một partition fail và restart |
| Remote partitioning | Message contract, JobRepository, serializer và worker version | Worker mất kết nối, message đến muộn |
| Remote chunking | Builder/handler, request-reply, idempotency | Commit DB xong nhưng mất reply |
| Local chunking (6.x) | ChunkProcessor xử lý transaction, retry/skip | Chunk xử lý lỗi giữa chừng |
| Async item processing (6.1) | Import \`AsyncItemProcessor/Writer\` và xử lý Future/asynchronous results | Lỗi processor bất đồng bộ, shutdown executor |

## 16. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “Tôi đã đổi import; migration xong.” | Còn phải xác minh behavior, transaction, restart và hiệu năng. |
| “\`taskExecutor\` luôn song song hóa cùng một đơn vị công việc.” | Batch 5.2 và engine mới Batch 6 có mô hình concurrency khác nhau. |
| “API deprecated vẫn được duy trì và tối ưu mãi.” | Deprecated là đường chuyển tiếp; cần đọc timeline loại bỏ và nâng có kế hoạch. |
| “Bỏ transaction manager vì constructor cho phép.” | Mặc định resourceless không bảo đảm rollback JDBC cho nghiệp vụ. |
| “Spring Boot 3 có thể tùy tiện dùng Batch 6.” | Phải dùng bộ dependency hỗ trợ và kiểm thử đầy đủ, không ép version một chiều. |
| “Manager và worker khác major version vẫn kết nối qua broker.” | Tương thích messaging và metadata phải được xác minh; không có bảo đảm mặc định. |
| “JobRepository schema cũ chắc chắn dùng được sau upgrade.” | Phải chạy/kiểm tra migration schema, serializer và dữ liệu lịch sử. |
| “Số worker cũ trên Batch 6 sẽ có throughput tương đương.” | Engine khác có thể chuyển bottleneck sang Reader/Writer hay DB. |
| “\`afterChunk\` vẫn chỉ được gọi sau commit.” | Trên engine mới Batch 6, callback này ở trong transaction, trước commit. |
| “Chỉ cần build pass là không cần thử restart.” | Retry/restart là phần thiết yếu của Spring Batch scaling operations. |

## 17. Checklist trước khi đưa bản mới vào vận hành

- [ ] Đã ghi rõ cặp **Spring Boot – Spring Batch – Spring Framework – Spring Integration – JDK** được dùng.
- [ ] Đã dùng **reference/Javadoc đúng version**, không sao chép ví dụ “latest” vào branch cũ.
- [ ] Đã thay các factory, builder, import và constructor bị đổi hoặc loại bỏ.
- [ ] Đã xác định engine chunk đang dùng: **legacy** hay **new**.
- [ ] Đã đánh giá thread safety/transaction theo **ngữ nghĩa concurrency của chính engine đó**.
- [ ] Đã kiểm tra \`@EnableJdbcJobRepository\` hoặc cấu hình Boot tương ứng và DB metadata bền vững.
- [ ] Đã kiểm tra bước chuyển listener và retry/skip, đặc biệt side effect sau commit.
- [ ] Đã bảo đảm JobParameters, ExecutionContext, partition naming và schema được migrate có kế hoạch.
- [ ] Đã kiểm thử manager/worker, contract message, redelivery và trạng thái in-flight nếu có xử lý phân tán.
- [ ] Đã kiểm tra pool/connection DB, executor threads và broker theo **số replica mới**.
- [ ] Đã đo elapsed time, throughput, rollback và đối soát dữ liệu trước/sau.
- [ ] Đã chuẩn bị phương án rollback/cutover, lưu ý metadata đã migrate có thể không thể dùng ngược với bản cũ.

## 18. Tài liệu chính thức để đối chiếu

Các trang dưới đây giúp xác minh chữ ký API và thay đổi theo dòng phiên bản:

1. [Spring Batch 5.0 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-5.0-Migration-Guide) — JDK 17, builder factory, transaction manager, counters, metrics.
2. [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html) — hành vi multi-threaded chunk kiểu cũ.
3. [Spring Batch 6.0 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide) — API đổi package, JobRepository, chunk engine, listener, remote handler/builder.
4. [Spring Batch 6.0 — What's New](https://docs.spring.io/spring-batch/reference/6.0/whatsnew.html) — chunk engine mới, concurrency model, local chunking.
5. [Spring Batch 6.1 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html) — multi-threaded step và các mô hình local/remote ở phiên bản ổn định 6.1 tại thời điểm viết.
6. [Spring Batch 6.1 — What's New](https://docs.spring.io/spring-batch/reference/whatsnew.html) — thay đổi trong minor release mới.
7. [RemoteChunkingManagerBuilder Javadoc 6.1](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/chunk/RemoteChunkingManagerBuilder.html) — builder mới, cấu hình channel và transaction.
8. [Thông báo Spring Batch 6.1 GA ngày 19/11/2026](https://spring.io/blog/2026/11/19/spring-batch-6-1-0-available-now/) — những thay đổi và yêu cầu tương thích của 6.1.
9. [Spring project generations](https://spring.io/projects/generations/) — ma trận tương thích theo thế hệ Spring Boot và các Spring project.

**Khi đọc tài liệu phiên bản khác 6.1**, ưu tiên trang versioned tương ứng và Javadoc của đúng artifact thay vì áp dụng kết luận về chữ ký API mới một cách máy móc.

## 19. Ghi nhớ

Khi mở rộng Spring Batch cho dữ liệu lớn, phải xét **cả mô hình xử lý và phiên bản cung cấp API**. Từ 4.x lên 5.x có những thay đổi lớn về builder và nền tảng Java; từ 5.x lên 6.x còn thay đổi **chunk engine, concurrency semantics, transaction/listener behavior, package và infrastructure**; đến 6.1 có thêm builder remote chunking mới và sự di chuyển của các API async/local chunking vào core.

Quy tắc thực hành là: **chốt version → đọc API đúng version → xác định đơn vị chạy song song và transaction → kiểm thử lỗi/restart → đo throughput và tài nguyên thật**. Một migration chỉ hoàn tất khi kết quả dữ liệu chính xác, job có thể khôi phục theo yêu cầu và công suất xử lý vẫn đáp ứng batch window trong giới hạn hạ tầng.
