# StepExecutionRequestHandler ở worker trong Spring Batch

## 1. Handler giải quyết vấn đề gì?

Khi chạy batch trên một JVM, framework có thể gọi trực tiếp một `Step`. Nhưng nếu một bước cần chạy trên **worker service** độc lập, manager không thể đơn giản gọi một method Java trong tiến trình khác. Thay vào đó, manager gửi một **yêu cầu thực thi** qua message channel hoặc broker. Worker cần một thành phần hiểu yêu cầu, tìm đúng `StepExecution` đã được tạo và thực thi đúng `Step` tương ứng.

`StepExecutionRequestHandler` là thành phần đó. Đây là message endpoint thuộc Spring Batch Integration, có method:

~~~java
StepExecution handle(StepExecutionRequest request);
~~~

Đối tượng đầu vào `StepExecutionRequest` xác định bước cần chạy; đối tượng trả về là `StepExecution` thể hiện kết quả của lần chạy đó. Handler là cầu nối giữa **lớp nhắn tin** và **lifecycle Spring Batch**, không phải `JobLauncher`, `Partitioner` hay phần nghiệp vụ đọc/ghi dữ liệu.

Bài học thuộc chương **Remote Step** của module `SPRING_BATCH_SCALING_OPERATIONS`. Mục tiêu của module là mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán; vì vậy, ngoài API của handler, ta cần hiểu rõ thread safety, retry/restart, đo bottleneck và trách nhiệm của từng service trong môi trường thật.

Sau bài học, bạn có thể:

- Giải thích vai trò của `StepExecutionRequestHandler` ở worker và sự khác nhau giữa `StepExecutionRequest` với `StepExecution`.
- Phân tích cách `StepLocator` tìm worker step và cách handler truy xuất metadata từ kho dùng chung.
- Cấu hình Spring Integration inbound flow cho Spring Batch 6.x và nhận biết điểm khác biệt quan trọng với 5.x.
- Tách lỗi giao nhận message khỏi lỗi thực thi step; xử lý duplicate, retry, restart và phản hồi an toàn.
- Xây dựng kế hoạch kiểm thử và giám sát để tăng số worker theo tài nguyên thực tế.

> **Phạm vi phiên bản:** `RemoteStep` được giới thiệu trong **Spring Batch 6.0**. `StepExecutionRequestHandler` cũng có mặt trong **remote partitioning** ở các bản 5.x. API handler và cấu trúc request **khác nhau giữa 5.x và 6.x**, nên ví dụ bên dưới sẽ ghi rõ phiên bản áp dụng.

## 2. Nhìn handler trong toàn bộ luồng remote step

~~~mermaid
flowchart LR
    A[Job manager / RemoteStep] -->|StepExecutionRequest| B[(Message broker)]
    B --> C[Inbound adapter]
    C --> D[StepExecutionRequestHandler]
    D --> E[StepLocator]
    E --> F[Worker Step]
    D <-->|Đọc metadata| G[(Shared JobRepository)]
    F <-->|Checkpoint / trạng thái| G
    F --> H[(Business data)]
    D --> I[StepExecution kết quả]
    I --> J[Reply flow nếu có]
    G -. Manager có thể polling .-> A
~~~

Đường đi có thể được hiểu theo bảy bước:

1. **Manager tạo metadata** cho một `StepExecution` và gửi request tham chiếu đến lần thực thi đó.
2. **Message adapter** nhận message từ RabbitMQ, JMS hoặc middleware khác và chuyển thành payload kiểu `StepExecutionRequest`.
3. **Handler nhận request** qua method `handle(...)` do Spring Integration gọi.
4. **Metadata được tra cứu** trong repository dùng chung để tìm `StepExecution` đã tồn tại và trạng thái hiện tại.
5. **StepLocator chọn đúng worker step** theo `stepName` trong request; worker step chạy với `StepExecution` đó.
6. **Worker step tự quản lý lifecycle** đọc/ghi, transaction, checkpoint và cập nhật metadata, theo cấu hình của `Step`.
7. **Handler trả về `StepExecution`** cho flow nhắn tin; tùy kiến trúc, kết quả có thể đi qua reply channel hoặc manager đọc trạng thái bằng polling repository.

Điểm phân định trách nhiệm: handler **không tạo job mới**, không tự chia partition, không nhận cả triệu item qua request và không thay thế reader/processor/writer. Nó tái sử dụng cơ chế `Step.execute(StepExecution)` thông thường ở một tiến trình khác.

### Hai cách dùng cùng một handler

| Kiến trúc | Manager làm gì? | Worker làm gì? | Cách manager biết kết quả |
|---|---|---|---|
| **Remote partitioning** (có ở 5.x/6.x) | Một partitioned step tạo nhiều `StepExecution`, mỗi execution mang vùng dữ liệu riêng | Handler thực thi cùng một worker step với các `ExecutionContext` khác nhau | Tổng hợp reply hoặc polling metadata, tùy cấu hình |
| **Remote Step** (từ 6.0) | Một `RemoteStep` trong job gửi việc của một logical step sang máy khác | Handler nhận request và chạy `Step` tương ứng | `RemoteStep` polling `JobRepository` để biết khi nào step kết thúc |

Với remote partitioning, có thể có 32 request cho 32 partition. Với một `RemoteStep` đơn lẻ, thường chỉ có **một lần thực thi step** được giao từ xa; muốn song song nhiều phân vùng, cần kiến trúc partitioning riêng. `Remote Step` không tự chia dữ liệu hoặc tự sinh thêm worker.

## 3. Ba đối tượng không được nhầm lẫn

### `StepExecutionRequest`: lệnh nhẹ để xác định execution

Đây là dữ liệu đi trên message channel. Nó chứa **định danh**, không phải bản sao đầy đủ của `StepExecution` hay các bản ghi cần xử lý.

### `StepExecution`: trạng thái tiến độ được lưu trong repository

`StepExecution` mang tên step, ID, trạng thái như `STARTED`/`COMPLETED`/`FAILED`, `ExitStatus`, `readCount`/`writeCount`, rollback và `ExecutionContext` để checkpoint/restart. Manager tạo execution theo lifecycle job; worker dùng execution đó để cập nhật tiến độ, không tự sinh một execution mới mỗi khi nhận lại cùng message.

### `StepLocator`: tìm code của step đã đăng ký

`StepLocator` định vị một bean `Step` trong worker application. Với `BeanFactoryStepLocator`, việc tra cứu dựa trên các step đã được đăng ký trong `BeanFactory`. Tên worker step trong request phải được worker hiểu; **không** dùng nội dung message không đáng tin cậy để gọi tùy tiện bất kỳ method hay bean nào.

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `StepExecutionRequest` | “Thực thi step nào, với execution ID nào?” | `ordersWorker` + execution ID |
| `JobRepository` / `JobExplorer` | “Execution đó đã được tạo chưa, đang ở trạng thái nào?” | Bản ghi metadata của execution |
| `StepLocator` | “Code `Step` nào chạy trên worker?” | Bean `ordersWorker` |
| `StepExecutionRequestHandler` | “Ghép request với metadata và thực thi step ra sao?” | `handle(request)` |
| `Step` | “Đọc, xử lý, ghi và transaction nghiệp vụ thế nào?” | Chunk step hoặc tasklet |

## 4. Sự khác biệt API giữa Spring Batch 5.x và 6.x

Đây là chi tiết ảnh hưởng trực tiếp tới code. Không nên sao chép cấu hình handler từ một major version sang version khác.

| Thành phần | Spring Batch 5.2.x | Spring Batch 6.0+ |
|---|---|---|
| Constructor request | `new StepExecutionRequest(stepName, jobExecutionId, stepExecutionId)` | `new StepExecutionRequest(stepName, stepExecutionId)` |
| Định danh trong request | `stepName`, `jobExecutionId`, `stepExecutionId` | `stepName`, `stepExecutionId` |
| Nguồn metadata cấu hình trực tiếp cho handler | `setJobExplorer(jobExplorer)` | `setJobRepository(jobRepository)` |
| Chọn step | `setStepLocator(stepLocator)` | `setStepLocator(stepLocator)` |
| Trả về từ `handle(...)` | `StepExecution` | `StepExecution` |
| Trường hợp dùng | Chủ yếu remote partitioning | Remote partitioning và `RemoteStep` |

Ví dụ về cấu trúc request (minh họa giá trị, **không phải JSON wire format mặc định**):

~~~text
Spring Batch 5.x:
  stepName:       ordersWorker
  jobExecutionId: 230
  stepExecutionId: 901

Spring Batch 6.x:
  stepName:       ordersWorker
  stepExecutionId: 901
~~~

Ở 6.x, `stepExecutionId` đã đủ để tìm execution trong repository. Vì vậy, việc cố gọi `setJobExplorer` trên handler 6.x hoặc khởi tạo request với ba tham số như 5.x có thể gây lỗi biên dịch. Bên cạnh đó, model và package của một số domain object đã thay đổi trong major version; hãy kiểm tra import và dependency BOM đúng phiên bản.

**Không gửi message object đã Java-serialize giữa worker 5.x và manager 6.x.** Thay đổi chữ ký, class model và serializer có thể khiến message không deserialize hoặc metadata bị hiểu sai. Khi nâng cấp, cần kế hoạch tương thích schema/queue/consumer, drain message tồn đọng và kiểm tra job restart đang chạy dở.

## 5. Cấu hình handler thủ công ở worker Spring Batch 6.x

Ví dụ này tập trung vào **handler và IntegrationFlow**, giả định ứng dụng đã có `JobRepository` dùng chung, bean worker `Step` tên `ordersWorker` và nguồn message đầu vào. Đây là phần wiring chính của worker, không phải ứng dụng đầy đủ kết nối đến broker.

~~~java
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.StepLocator;
import org.springframework.batch.integration.partition.BeanFactoryStepLocator;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
public class RemoteWorkerHandlerConfiguration {

    @Bean
    public StepLocator stepLocator(BeanFactory beanFactory) {
        BeanFactoryStepLocator locator = new BeanFactoryStepLocator();
        locator.setBeanFactory(beanFactory);
        return locator;
    }

    @Bean
    public StepExecutionRequestHandler requestHandler(
            JobRepository jobRepository, StepLocator stepLocator) {
        StepExecutionRequestHandler handler =
                new StepExecutionRequestHandler();
        handler.setJobRepository(jobRepository); // Spring Batch 6.x
        handler.setStepLocator(stepLocator);
        return handler;
    }

    @Bean
    public MessageChannel workerRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow workerRequestsFlow(
            MessageChannel workerRequests,
            StepExecutionRequestHandler requestHandler) {
        return IntegrationFlow.from(workerRequests)
                .handle(requestHandler, "handle")
                .get();
    }
}
~~~

Ở đây, `workerRequests` là Spring Integration channel **bên trong JVM**. Một inbound adapter từ broker phải gửi vào channel này. Ví dụ: adapter JMS/AMQP nhận request rồi chuyển payload đã deserialize thành `StepExecutionRequest`.

`DirectChannel` gọi handler đồng bộ trên thread gửi message vào channel; nếu adapter dùng listener thread thì mỗi listener có thể giữ thread đó đến khi step hoàn tất. Để chạy nhiều request đồng thời, phải giới hạn consumer concurrency và hiểu liệu adapter/flow có sử dụng executor hay không. Không tự tăng concurrency của `DirectChannel` bằng một thuộc tính không tồn tại.

### Nếu dùng Spring Batch 5.x

Thay **duy nhất phần cấu hình handler** bằng API tương ứng; worker step vẫn phải có `JobRepository` để lưu transaction và checkpoint:

~~~java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.step.StepLocator;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;

@Bean
public StepExecutionRequestHandler requestHandler(
        JobExplorer jobExplorer, StepLocator stepLocator) {
    StepExecutionRequestHandler handler =
            new StepExecutionRequestHandler();
    handler.setJobExplorer(jobExplorer); // Spring Batch 5.x
    handler.setStepLocator(stepLocator);
    return handler;
}
~~~

`JobExplorer` đọc metadata để handler xác định execution; `JobRepository` của worker `Step` vẫn thực hiện cập nhật trạng thái trong quá trình chạy. Ở cả hai phiên bản, manager và worker cần nhìn thấy **cùng metadata thực thi** qua repository được cấu hình tương thích.

### Đăng ký worker step

Handler không chứa business logic. Worker phải đăng ký một bean `Step` có tên mà `StepLocator` tìm được. Ví dụ tasklet dưới đây dùng SQL cập nhật lặp an toàn; đây là minh họa thao tác nhỏ, không phải phương án tối ưu cho một partition hàng triệu dòng:

~~~java
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.infrastructure.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("ordersWorker")
public Step ordersWorker(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbc) {
    return new StepBuilder("ordersWorker", repository)
            .tasklet((contribution, chunkContext) -> {
                Object raw = chunkContext.getStepContext()
                        .getStepExecutionContext().get("orderId");
                long orderId = ((Number) raw).longValue();
                jdbc.update(
                        "UPDATE orders SET processed = TRUE WHERE id = ?",
                        orderId
                );
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
~~~

Ví dụ chỉ chạy được nếu **`ExecutionContext` của `StepExecution` đã có `orderId`**, do manager hoặc partitioner chuẩn bị trước. Nếu thiếu key, sẽ lỗi và worker step phải được đánh dấu thất bại theo lifecycle. Trong hệ thống lớn, nên thay bằng chunk-oriented step hoặc tasklet xử lý một đơn vị công việc có ranh giới rõ ràng. Để xử lý file, range ID hoặc tenant, lấy thông tin từ `stepExecutionContext` bằng `@StepScope` và tạo reader có state riêng cho mỗi execution.

SQL `SET processed = TRUE` minh họa *idempotency*: gọi lại với cùng ID vẫn dẫn tới trạng thái cuối giống nhau. Nếu writer chuyển tiền, gửi email hay phát sự kiện, cần thêm khóa nghiệp vụ, outbox hoặc bảng deduplication; không thể thay bằng một câu SQL idempotent đơn giản.

## 6. Nối message broker vào handler

Một kiến trúc worker thực tế có hai phần:

~~~text
Broker request queue
    |
    v
Inbound adapter (JMS/AMQP)
    |
    v
Deserializer / message converter
    |
    v
MessageChannel workerRequests
    |
    v
StepExecutionRequestHandler.handle(request)
    |
    +--> JobRepository + worker Step
    |
    +--> StepExecution result
             |
             +--> Reply adapter (nếu manager cần aggregate reply)
             +--> Hoặc manager polling JobRepository
~~~

Với Spring Batch 6.x, tài liệu chính thức minh họa inbound flow JMS sử dụng `Jms.messageDrivenChannelAdapter(...)`:

~~~java
// Spring Batch 6.x / Spring Integration JMS, minh họa phần transport.
// Cần cung cấp JMS ConnectionFactory, converter và broker/queue tương ứng.
@Bean
public IntegrationFlow workerJmsInbound(
        jakarta.jms.ConnectionFactory connectionFactory,
        StepExecutionRequestHandler handler) {
    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("batch.remote.step.requests"))
            .handle(handler, "handle")
            .get();
}
~~~

Trong cùng ứng dụng, **chọn một đường inbound thực tế**: adapter chuyển vào `workerRequests` rồi `workerRequestsFlow` gọi handler, *hoặc* một flow trực tiếp như `workerJmsInbound` ở trên. Không bật cả hai để tiêu thụ cùng message hai lần. Với ví dụ trực tiếp, cần import `org.springframework.integration.jms.dsl.Jms`, `IntegrationFlow` và định nghĩa cơ chế serialization/deserialization có thể tạo `StepExecutionRequest`.

### Cần phản hồi về manager khi nào?

- **Remote partitioning + reply aggregation:** handler trả `StepExecution`; flow route kết quả ra reply queue/channel để manager tổng hợp nhiều partition. Reply cần correlation tương ứng đúng job/step execution.
- **Remote partitioning + repository polling:** manager đọc trạng thái ở metadata DB; không cần cấu hình reply từ worker nếu đã chọn đúng cơ chế polling.
- **`RemoteStep` của Spring Batch 6.x:** `RemoteStep` dùng repository polling để chờ worker step kết thúc; ví dụ inbound flow chính thức chỉ gọi handler và không yêu cầu reply channel riêng.

Không tự coi message đã ACK hoặc handler đã trả về object là **job đã hoàn thành**. Metadata và logic chờ của manager mới quyết định trạng thái của toàn job. Với reply asynchronous, cần kiểm tra output adapter thực sự publish reply thành công.

## 7. Cách manager gọi một remote step trong 6.x

Để hiểu request được tạo từ đâu, xem khung cấu hình manager tương ứng. `RemoteStep` là một `Step` đặt trong job ở manager, nhưng logic thực tế được giao cho `ordersWorker` từ xa.

~~~java
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.remote.RemoteStep;
import org.springframework.integration.core.MessagingTemplate;

@Bean
public Step remoteOrdersStep(
        JobRepository jobRepository,
        MessagingTemplate messagingTemplate) {
    return new RemoteStep(
            "remoteOrdersStep", // Tên logical step trong manager job
            "ordersWorker",     // Tên worker Step để StepLocator tìm
            jobRepository,
            messagingTemplate
    );
}
~~~

Đây là **phác thảo cấu hình**: `MessagingTemplate` phải được nối với kênh request của broker, có thể bằng `RemoteStep.setMessageChannel(...)` hoặc một template đã cấu hình destination thích hợp. `RemoteStep` hỗ trợ polling interval và timeout, cần chọn giá trị theo thời gian xử lý thực tế.

Đừng nhầm tên logical step ở manager (`remoteOrdersStep`) với tên bean worker (`ordersWorker`). Message phải yêu cầu tên step mà worker `StepLocator` thực sự giải quyết được.

**Đặc biệt:** `RemoteStep` là API từ Spring Batch 6.0; không áp dụng nguyên đoạn này cho project Spring Batch 5.x. Trên 5.x, người học có thể thực hành handler qua **remote partitioning** với `RemotePartitioningManagerStepBuilder` và `RemotePartitioningWorkerStepBuilder`.

## 8. Thread safety và vòng đời bean khi handler chạy trên nhiều worker thread

Handler có thể được dùng như một bean singleton trong worker service. Điều đó **không có nghĩa** mọi bean mà step gọi đều thread-safe. Khi adapter nhận nhiều message đồng thời, nhiều `StepExecution` có thể chạy trên những thread khác nhau. **API `Step` của Spring Batch 6 cảnh báo không an toàn nếu dùng lại cùng một instance `Step` để xử lý nhiều execution đồng thời**. Vì vậy, với một bean `Step` duy nhất được locator trả về, mặc định nên giới hạn một execution đang chạy trên mỗi worker process, rồi mở rộng bằng nhiều instance độc lập. Chỉ cho phép concurrency lớn hơn khi kiến trúc và framework cụ thể đã bảo đảm cách ly instance/lifecycle và được kiểm chứng qua thử nghiệm.

| Loại đối tượng | Cách tổ chức thường phù hợp | Nguy cơ cần kiểm tra |
|---|---|---|
| `StepExecutionRequestHandler`, `StepLocator` | Bean dùng chung để dispatch | Cấu hình bất biến sau startup, không tùy tiện thay step registry lúc đang chạy |
| `JobRepository` / `DataSource` | Hạ tầng dùng chung có giới hạn pool | Contention metadata, connection exhaustion, transaction timeout |
| `JdbcCursorItemReader`, `FlatFileItemReader` | Tạo cho từng `StepExecution` bằng `@StepScope` | Cursor/state đọc dùng chung gây trùng/thiếu dữ liệu |
| `ItemProcessor` / `ItemWriter` | Singleton nếu stateless và an toàn, nếu không thì cô lập theo step | Biến đếm mutable, buffer, formatter hoặc client không an toàn |
| JMS `Session`, RabbitMQ raw `Channel` | Dùng theo lifecycle và contract của provider | Không tự giữ một session/channel rồi chia sẻ cho nhiều thread |

Với reader step-scoped, ví dụ expression:

~~~java
@Bean
@StepScope
public ItemReader<Order> reader(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {
    return createRangeReader(minId, maxId);
}
~~~

`createRangeReader(...)` là hàm ứng dụng cần cài đặt. Ví dụ này áp dụng khi manager/partitioner đã chốt các range. Nếu là `RemoteStep` không partition thì context có thể chứa `businessDate`, `fileKey` hoặc giá trị nghiệp vụ khác; chọn key thực sự tồn tại trong execution đó.

### Công thức giới hạn concurrency

Nếu có `N` worker instance, mỗi instance cấu hình `L` listener thread thực thi đồng thời, thì trần bước từ xa đang chạy xấp xỉ:

\[
C_{\max} \le N \times L
\]

Với remote partitioning có `P` partition, số partition active đồng thời còn bị giới hạn:

\[
C_{\text{active}} \le \min(P, N \times L)
\]

Ví dụ 32 partition, 4 pod, 2 consumer/pod thì **listener có thể nhận tới 8 request đồng thời**, nhưng chỉ nên chạy 8 `StepExecution` nếu đã chứng minh các `Step` instance thực sự được cô lập an toàn. Nếu mỗi pod chỉ có một instance `Step` dùng chung, giới hạn một execution/pod cho độ an toàn ban đầu sẽ đưa trần thực tế xuống 4. Phải tính tổng kết nối DB/broker, CPU/heap và pool theo toàn cụm; tăng listener concurrency quá mức có thể khiến job chậm hoặc lỗi.

## 9. Retry, restart và message nhận lặp

### Ba thời điểm lỗi cần phân biệt

| Thời điểm | Rủi ro | Cách suy luận đúng |
|---|---|---|
| **Trước khi handler chạy** | Broker đã nhận message nhưng converter/StepLocator lỗi | Kiểm tra payload, classpath, tên step, error channel và DLQ |
| **Trong khi `Step.execute(...)`** | Transaction rollback, reader/writer lỗi, step thất bại | Đọc `StepExecution`, checkpoint và error log; áp chính sách retry/skip ở step |
| **Sau khi step đã commit nhưng trước ACK/reply** | Broker có thể giao lại cùng request | Kiểm tra trạng thái repository và bảo đảm idempotency trước khi chạy lại |

Một message được broker giao lại không tự tạo một lần chạy mới. Handler có cơ chế tra cứu trạng thái `StepExecution`, nhưng metadata và ACK của broker thường **không nằm trong cùng transaction**. Nếu worker cũ mất kết nối nhưng còn sống và worker khác nhận lại message, có thể xuất hiện race. Đừng coi bước kiểm tra `COMPLETED` là distributed lock tuyệt đối.

### Giữ nguyên job instance khi restart

Spring Batch nhận diện `JobInstance` thông qua job name và identifying `JobParameters`. Khi worker thất bại, quản trị nên restart đúng job instance theo metadata và giữ ổn định những ranh giới xử lý đã chốt; không tùy tiện đổi `run.id` để tạo một job instance hoàn toàn mới. Với reader restartable, checkpoint thuộc `ExecutionContext` của đúng `StepExecution` và tên `ItemStream` cần ổn định.

Nếu worker thực hiện side effect ngoài transaction (gửi email, HTTP, publish Kafka/RabbitMQ), có thể đã hoàn thành side effect trước khi step thất bại. Giải pháp nghiệp vụ gồm:

- Khóa nghiệp vụ/idempotency key ổn định qua các lần retry.
- Unique constraint hoặc compare-and-set ở đích.
- Transactional outbox và consumer deduplication cho event.
- Retry có giới hạn, backoff và jitter, tránh toàn bộ worker cùng tạo retry storm.
- Đối soát số item và kết quả ngoài hệ thống sau khi job phục hồi.

### ACK, redelivery và DLQ

Một quy tắc kinh nghiệm là **không ACK sớm trước khi có kết quả xử lý phù hợp với hợp đồng broker**. Tuy nhiên, thời điểm ACK chính xác phụ thuộc inbound adapter, transaction của broker và chiến lược recovery; không phải cấu hình mặc định nào cũng dùng manual ACK. Nếu bỏ qua ACK hoặc gửi NACK vô hạn, poison message có thể gây vòng lặp và làm nghẽn queue. Cần định nghĩa retry limit, DLQ, cảnh báo và quy trình xử lý thủ công đối với request không hợp lệ.

Đối với request gửi lại, xử lý an toàn phải kết hợp **kiểm tra metadata, giới hạn thực thi trùng và idempotency ở hệ thống đích**. Chỉ dùng message broker hoặc chỉ dùng `JobRepository` riêng lẻ không thay thế toàn bộ ba lớp này.

## 10. Vận hành và chẩn đoán StepExecutionRequestHandler

Khi debug, cần theo dõi cả **request path** và **batch execution path**:

| Thành phần | Chỉ số / log cần thu | Câu hỏi nên đặt ra |
|---|---|---|
| Inbound adapter | Số request nhận, lỗi converter, thời gian từ enqueue đến consume, redelivery | Message có vào đúng worker không? |
| Handler | `stepName`, `stepExecutionId`, thời gian `handle`, exception | Có tìm được step và execution không? |
| StepLocator | Số lỗi step not found, danh sách step được phép chạy | Manager và worker có cùng contract tên step? |
| Worker step | `BatchStatus`, `ExitStatus`, `readCount`, `writeCount`, retry/skip/rollback | Lỗi ở routing hay business logic? |
| `JobRepository` | Query/commit latency, connection wait, lock contention | Metadata có là bottleneck khi tăng worker? |
| Broker | Queue depth, oldest-message age, unacked, DLQ, số consumer | Thiếu consumer, message kẹt hay broker bão hòa? |
| JVM / Kubernetes | CPU, heap, GC, thread pool, pod restart và shutdown | Worker nghẽn CPU, DB, network hay bị restart? |

Tối thiểu nên gắn các trường `stepName`, `stepExecutionId`, `jobExecutionId` (lấy từ metadata đối với 6.x), `workerInstanceId` và thời gian xử lý vào log/trace. **Không log nguyên `ExecutionContext` nếu chứa thông tin nhạy cảm**.

### Bảng xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / xử lý |
|---|---|---|
| `handle` không được gọi | Adapter không chạy, sai queue, converter lỗi | Xem inbound listener/error channel, quyền broker và kiểu payload |
| Không tìm thấy worker step | `stepName` sai hoặc bean `Step` chưa đăng ký | Kiểm tra `BeanFactoryStepLocator`, tên bean và profile worker |
| Không tìm thấy `StepExecution` | ID sai hoặc repository khác môi trường | Đối chiếu ID và DB metadata mà manager/worker đang dùng |
| Worker chạy lại step đã xử lý | Duplicate request, tạo job instance mới, idempotency kém | Đối soát metadata và khóa nghiệp vụ; kiểm tra ACK/redelivery |
| Worker xong nhưng manager timeout | Lost reply, polling/timeout chưa phù hợp hoặc repository chậm | Kiểm tra trạng thái step trong DB trước khi re-dispatch |
| `ClassCastException` / deserialize lỗi | Message converter sai hoặc manager–worker khác major version | Đồng bộ contract, version, serializer và xử lý message tồn đọng |
| Tăng worker nhưng throughput không tăng | DB pool, broker, SQL lock hoặc business API bão hòa | So sánh active worker, connection wait và throughput từng step |
| Tắt pod gây request treo | Không drain listener, thời hạn shutdown ngắn | Stop nhận request mới, hoàn tất chunk hoặc restart có kiểm soát |

### Runbook khi một request dừng lâu

1. Truy tìm `stepExecutionId` từ message hoặc log. Kiểm tra tồn tại và trạng thái của execution trong repository.
2. Kiểm tra worker nào đã nhận request, message đang pending/unacked hay đã chuyển DLQ.
3. Nếu metadata `STARTED`, xác minh worker thực sự còn xử lý hay đã chết trước khi cho phép giao lại.
4. Nếu `COMPLETED` nhưng manager chưa nhận kết quả, kiểm tra reply/polling và độ trễ DB; tránh gửi lại công việc khi chưa đối soát.
5. Nếu `FAILED`, xác định lỗi dữ liệu hay hạ tầng, áp dụng retry/restart đúng job instance và ranh giới.
6. Đối soát dữ liệu và side effect sau phục hồi, rồi ghi nhận nguyên nhân ở cả broker, handler và step.

## 11. Kiểm thử theo tình huống thay vì chỉ kiểm tra code handler

Một số phép thử nên có trước production:

1. **Đường đi bình thường:** tạo sẵn `StepExecution` hợp lệ trong repository, gửi request đến đúng worker step, xác minh worker thực thi và metadata chuyển sang trạng thái kết thúc phù hợp.
2. **Step name không tồn tại:** request tìm đến một `stepName` chưa đăng ký. Xác minh error channel/DLQ và log có định danh, worker không chạy một step khác để thay thế.
3. **Execution ID không tồn tại:** request hợp lệ về cú pháp nhưng không tra được metadata. Xác minh không có job hay step mới được tự tạo.
4. **Request lặp:** gửi lại cùng request sau khi step đã `COMPLETED`; kiểm tra side effect không bị nhân đôi.
5. **Crash sau commit trước ACK:** dừng worker ngay sau commit rồi cho broker redeliver; xác minh dữ liệu đích vẫn đúng và recovery có thể đối soát.
6. **Concurrency:** gửi nhiều request khác nhau, đo CPU, JDBC pool, broker channel và trạng thái reader/processor/writer; phát hiện bean có state bị chia sẻ sai.
7. **Lỗi tạm thời:** mô phỏng DB/broker mất kết nối, kiểm tra timeout, backoff, giới hạn retry, restart và shutdown.
8. **Nâng cấp phiên bản:** kiểm tra request format, handler setter, metadata schema, serialization và message tồn đọng khi di chuyển từ 5.x sang 6.x.

Một phép thử unit gọi trực tiếp `handler.handle(request)` có ích để kiểm tra việc tìm `Step`/`StepExecution`. Tuy nhiên, các lỗi quan trọng như redelivery, mất ACK, reply thất lạc và worker bị terminate chỉ xuất hiện khi chạy tích hợp với broker, database và worker process thực tế.

## 12. Checklist thiết kế trước khi triển khai

- [ ] Đã xác định đang dùng Spring Batch **5.x hay 6.x**; handler setter và request schema khớp phiên bản.
- [ ] Manager tạo execution trước khi gửi request; worker không tự tạo job instance cho mỗi message.
- [ ] `StepLocator` chỉ tìm đúng các worker step đã đăng ký và được phép thực thi.
- [ ] Manager và worker truy cập metadata của **cùng `JobRepository`** với schema tương thích.
- [ ] Inbound adapter deserialize chính xác `StepExecutionRequest`; policy ACK, retry và DLQ được xác định.
- [ ] Chọn rõ **reply aggregation** hoặc **repository polling** ở manager; timeout hợp lý với workload.
- [ ] Reader stateful dùng `@StepScope`, processor/writer và client dùng chung được kiểm tra thread safety.
- [ ] Dữ liệu nguồn ổn định theo một job instance; writer/side effect có idempotency.
- [ ] Concurrency, connection pool, prefetch và retry được giới hạn theo ngân sách toàn cụm.
- [ ] Có log/metric theo execution ID, khả năng tra cứu trạng thái và runbook phục hồi.

## 13. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Lắp ghép handler

Tạo một worker service với bean `Step` tên `ordersWorker`, một `StepLocator` và `StepExecutionRequestHandler`. Dùng Spring Integration channel nhận `StepExecutionRequest`. Chuẩn bị metadata execution trước khi gửi message, quan sát kết quả trả về `StepExecution` và các thay đổi trong `JobRepository`.

### Bài tập 2 — So sánh 5.x và 6.x

Viết hai đoạn cấu hình `requestHandler`: một dùng `setJobExplorer`, một dùng `setJobRepository`. Giải thích tại sao request của 5.x cần `jobExecutionId` còn request 6.x dùng `stepExecutionId`, và vì sao không thể ghép tùy ý client/worker ở hai major version khác nhau.

### Bài tập 3 — Mất ACK và duplicate

Cho worker cập nhật một bản ghi rồi chủ động dừng ngay trước ACK message. Khi broker giao lại cùng request, kiểm tra metadata step và thay đổi nghiệp vụ. Thêm ràng buộc idempotency để kết quả cuối không đổi khi thử lại. So sánh nếu writer phát thêm một event ra broker thứ hai.

### Bài tập 4 — Đo giới hạn worker

Tạo 24 partition và worker deployment có 3 pod, mỗi pod 2 consumer. Thử tăng từ 3 lên 6 pod với cùng snapshot dữ liệu; đo số partition thực sự active, thời gian job, CPU, JDBC pool wait, broker unacked và phân bố duration theo partition. Xác định nút thắt trước khi quyết định mở rộng.

**Tự kiểm tra:** Handler lấy dữ liệu nghiệp vụ từ request hay từ reader của worker step? Tại sao `StepLocator` cần tên step ổn định? Vì sao `RemoteStep` 6.x không nhất thiết cần reply queue? Khi manager bị timeout, tại sao phải tra `JobRepository` trước khi cho chạy lại? Vì sao `StepExecutionRequestHandler` một mình không đảm bảo exactly-once?

## 14. Tài liệu kỹ thuật tham khảo

- [Spring Batch 6.x — Scaling and Parallel Processing, Remote Step execution](https://docs.spring.io/spring-batch/reference/6.0/scalability.html).
- [Spring Batch 6.x — API StepExecutionRequestHandler](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/partition/StepExecutionRequestHandler.html).
- [Spring Batch 5.x — API StepExecutionRequestHandler](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/partition/StepExecutionRequestHandler.html).
- [Spring Batch 5.x — Remote Partitioning Worker Step Builder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/partition/RemotePartitioningWorkerStepBuilder.html).

`StepExecutionRequestHandler` là mắt xích đưa yêu cầu từ middleware vào lifecycle của Spring Batch trên worker: **nhận định danh execution, tìm step, thực thi và trả trạng thái**. Khi dùng đúng API theo phiên bản, ghép với repository nhất quán, transport có chính sách lỗi rõ ràng và nghiệp vụ idempotent, handler giúp việc chạy step ở worker process trở thành một phần có thể quan sát và phục hồi của job phân tán.
