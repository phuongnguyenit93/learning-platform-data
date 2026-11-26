# Tương thích phiên bản khi dùng RemoteStep trong Spring Batch

## 1. Vì sao phiên bản là một phần của kiến trúc phân tán?

Trong một job chạy nội bộ một JVM, lỗi lệch dependency thường xuất hiện sớm khi biên dịch hoặc khởi động ứng dụng. Với **Remote Step**, có ít nhất hai tiến trình có thể được build, deploy và nâng cấp ở những thời điểm khác nhau: **manager** điều phối job và **worker** thực thi step. Giữa chúng còn có message broker, serializer, `JobRepository` dùng chung và dữ liệu nghiệp vụ.

Giả sử manager đã nâng từ Spring Batch 5.x lên 6.x, trong khi một số worker vẫn ở phiên bản cũ. Manager mới gửi request mang `stepExecutionId` nhưng worker cũ kỳ vọng request có cả `jobExecutionId`; hoặc worker đã nâng cấp nhưng repository đang dùng serializer/schema của bản cũ. Hệ thống có thể gặp các triệu chứng rất khác nhau: không deserialize được message, không tìm thấy `StepExecution`, worker im lặng không chạy, job treo khi polling, hoặc job restart nhưng đọc sai checkpoint.

Vì thế, câu hỏi không chỉ là “cùng version thư viện chưa?” mà là:

> **Manager, worker, transport và metadata có cùng một hợp đồng thực thi và khôi phục hay không?**

Bài **“Tương thích phiên bản khi dùng RemoteStep”** thuộc chương **Remote Step** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module tập trung mở rộng Spring Batch với multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và vận hành job theo tài nguyên thực tế. Chính các yêu cầu restart, scale và triển khai độc lập khiến tương thích phiên bản trở thành **điều kiện về tính đúng của dữ liệu**, không chỉ là việc cập nhật dependency.

Sau bài học, bạn có thể:

- Nhận biết mốc xuất hiện của `RemoteStep` và không áp nhầm API 6.x vào Spring Batch 5.x.
- Đối chiếu thay đổi ở `StepExecutionRequest`, `StepExecutionRequestHandler` và `JobRepository` giữa 5.x và 6.x.
- Chốt ma trận version của Spring Batch, Spring Integration, Spring Framework/Boot, Java, broker driver và serializer.
- Kiểm tra tính tương thích của **metadata database**, `ExecutionContext` và các job đang dở trước khi rollout.
- Thiết kế chiến lược nâng cấp **drain → migrate → deploy → verify** với rollback rõ ràng.
- Xây contract test, fault-injection test và runbook cho lỗi version skew trong remote execution.

**Phạm vi:** nội dung đối chiếu chính giữa **Spring Batch 5.2.x** và **6.0.x**, các điểm thay đổi cơ bản khi sang nhánh 6.x. Trong cùng nhánh 6.x, bản 6.1 và các bản sau cũng có thay đổi dependency/API; luôn đọc migration notes và Javadoc đúng **phiên bản cụ thể** mà dự án sẽ deploy.

## 2. Mốc quan trọng nhất: RemoteStep bắt đầu từ 6.0

**`RemoteStep` là một class được giới thiệu trong Spring Batch 6.0**, thuộc package `org.springframework.batch.integration.remote`. Nó đại diện cho một step trong job của manager, gửi yêu cầu thực thi tới worker qua Spring Integration và **poll `JobRepository`** để biết worker step đã kết thúc.

Spring Batch 5.x đã có những cơ chế scale khác, đặc biệt **remote partitioning** và **remote chunking**, nhưng không có cùng API `RemoteStep` 6.x.

| Chủ đề | Spring Batch 5.2.x | Spring Batch 6.0.x |
|---|---|---|
| `RemoteStep` | **Chưa có** API `RemoteStep` nói trên | Có từ `6.0.0` |
| Remote partitioning | Có manager/worker, nhiều `StepExecution` | Vẫn có; API/config có thay đổi |
| `StepExecutionRequest` | Request mang step name, job execution ID, step execution ID | Request tối giản theo step name và step execution ID |
| Handler worker | `setJobExplorer(...)` | `setJobRepository(...)` |
| `JobRepository` và `JobExplorer` | Thường là hai interface/bean riêng | `JobRepository` **mở rộng** `JobExplorer` |
| Hạ tầng repository khi cấu hình bằng Java | Thường giả định JDBC với cấu hình Batch truyền thống | **Có tùy chọn resourceless**, phải cấu hình JDBC repository rõ khi cần chia sẻ metadata |
| Spring Framework / Integration chủ đạo | Thế hệ 6.x tương thích với Batch 5.x | Spring Framework **7.0**, Spring Integration **7.0** ở Batch 6.0 |
| Cách manager phát hiện hoàn tất của `RemoteStep` | Không áp dụng | Poll metadata của worker execution trong repository |

Không suy rằng một worker đang làm **remote partitioning 5.x** có thể tự động phục vụ **RemoteStep 6.x** chỉ vì cả hai đều nhận `StepExecutionRequest`. Chúng có khác biệt về **kiến trúc** (một step từ xa so với nhiều partition), API và metadata.

### Phân biệt version compatibility với feature compatibility

Có hai câu hỏi độc lập:

1. **Có dùng được API không?** Ví dụ `RemoteStep` chỉ tồn tại từ Batch 6.0.
2. **Có cùng ngữ nghĩa thực thi không?** Một `RemoteStep` không tự chia N vùng dữ liệu. Nếu job 5.x trước đây tạo 32 partition, đổi thành một `RemoteStep` có thể làm mất 31 đơn vị song song, ngay cả khi compile thành công.

Một migration đúng cần giữ **contract nghiệp vụ**: số tập dữ liệu, quyền sở hữu từng phần, checkpoint, idempotency và ý nghĩa của “COMPLETED”.

## 3. Tương thích là một ma trận nhiều chiều

~~~mermaid
flowchart TB
    M[Manager image + Batch version] --> C[Request/response contract]
    W[Worker image + Batch version] --> C
    C --> B[(Message broker + converter)]
    M --> R[(Shared JobRepository)]
    W --> R
    R --> S[Metadata schema + ExecutionContext serialization]
    W --> D[(Business data / output)]
    M --> O[Job flow + restart policy]
    S --> O
    D --> O
~~~

| Lớp cần chốt | Ví dụ nội dung | Rủi ro nếu lệch |
|---|---|---|
| **Runtime** | Java, Spring Framework, Spring Boot | `NoClassDefFoundError`, lỗi bytecode, annotation/auto-configuration khác |
| **Batch core** | `spring-batch-core` cùng một nhánh phù hợp | Domain model, lifecycle, transaction và API thay đổi |
| **Batch Integration** | `spring-batch-integration` cùng release train/phiên bản tương thích | Handler/partition builder/request không khớp |
| **Spring Integration** | Adapter JMS/AMQP, channel/DSL và converter | Không gửi/nhận được message hoặc đổi semantics ACK |
| **Wire format** | DTO `StepExecutionRequest`, headers, serializer, correlation | Worker không deserialize hoặc tìm nhầm execution |
| **Metadata** | Schema và serializer `ExecutionContext`/`JobParameters` | Không đọc checkpoint/parameter, optimistic lock hoặc restart lỗi |
| **Worker code** | Tên bean `Step`, reader/writer và config bean scope | `StepLocator` không tìm thấy step, xử lý sai tập dữ liệu |
| **Nghiệp vụ** | Snapshot, writer, idempotency key, business schema | Trùng/thiếu dữ liệu dù BatchStatus có thể hợp lệ |
| **Vận hành** | Queue, DLQ, timeout, shutdown, deployment image | Redelivery sai, rolling update làm job treo hoặc chạy trùng |

Nguyên tắc vận hành mặc định: **pin một bộ dependency được kiểm thử**, cho manager và worker cùng contract/version; không tự tin rằng hai major version có thể trao đổi object Java trực tiếp. Nếu cần giao tiếp xuyên major version trong giai đoạn chuyển đổi, hãy xây **bridge/adapter có schema riêng** và test nó như một hệ thống phân tán độc lập, không dựa vào Java serialization mặc định.

## 4. API thực tế: StepExecutionRequest 5.x so với 6.x

### 4.1. Định danh execution trong request

Ở **Spring Batch 5.2.x**, constructor request thường dùng ba tham số:

~~~java
// Spring Batch 5.2.x (remote partitioning)
import org.springframework.batch.integration.partition.StepExecutionRequest;

StepExecutionRequest request = new StepExecutionRequest(
        "ordersWorker",
        120L,  // jobExecutionId
        451L   // stepExecutionId
);
~~~

Ở **Spring Batch 6.x**, constructor sử dụng tên step và `stepExecutionId`:

~~~java
// Spring Batch 6.x
import org.springframework.batch.integration.partition.StepExecutionRequest;

StepExecutionRequest request = new StepExecutionRequest(
        "ordersWorker",
        451L   // stepExecutionId
);
~~~

`stepExecutionId` là định danh của `StepExecution` được lưu ở metadata repository. Request chỉ mang **tham chiếu**, không chứa toàn bộ `ExecutionContext` hoặc hàng triệu record. Worker cần load metadata tương ứng từ repository để chạy.

**Không serialize một request 5.x rồi đặt vào queue để worker 6.x đọc như thể đó là cùng một Java object.** Dù tên class trùng, cấu trúc constructor/field và serialization contract có thể khác. Ngược lại, một worker 5.x kỳ vọng `jobExecutionId` có thể không hiểu request 6.x.

### 4.2. Handler worker cũng đổi dependency

**Spring Batch 5.2.x**:

~~~java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.step.StepLocator;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;

// Trong class @Configuration đã có @Bean và các dependency:
@Bean
StepExecutionRequestHandler handler5(
        JobExplorer jobExplorer, StepLocator stepLocator) {
    StepExecutionRequestHandler handler =
            new StepExecutionRequestHandler();
    handler.setJobExplorer(jobExplorer);
    handler.setStepLocator(stepLocator);
    return handler;
}
~~~

**Spring Batch 6.x**:

~~~java
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.StepLocator;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;

// Trong class @Configuration đã có @Bean và các dependency:
@Bean
StepExecutionRequestHandler handler6(
        JobRepository jobRepository, StepLocator stepLocator) {
    StepExecutionRequestHandler handler =
            new StepExecutionRequestHandler();
    handler.setJobRepository(jobRepository);
    handler.setStepLocator(stepLocator);
    return handler;
}
~~~

Hai snippet là **hai biến thể thay thế theo phiên bản**; không cùng khai báo trong một ứng dụng. `StepLocator` phải biết bean `Step` cần gọi. Worker vẫn cần `JobRepository` để lưu trạng thái/chunk transaction kể cả khi handler 5.x được truyền `JobExplorer` để tra cứu.

### 4.3. Cấu hình RemoteStep thuộc nhánh 6.x

Ví dụ worker step tên `ordersWorker`:

~~~java
// Spring Batch 6.x, trong class @Configuration của manager:
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.remote.RemoteStep;
import org.springframework.integration.core.MessagingTemplate;

@Bean
Step remoteOrdersStep(
        JobRepository repository, MessagingTemplate messagingTemplate) {
    return new RemoteStep(
            "remoteOrdersStep", // logical step trong job manager
            "ordersWorker",     // worker step được StepLocator tìm
            repository,
            messagingTemplate);
}
~~~

Đây là **mảnh cấu hình minh họa API**. Để chạy được, `MessagingTemplate` phải gắn với channel/outbound adapter gửi request tới broker, phía worker phải có inbound flow và metadata repository dùng chung. Không khai báo một `RemoteStep` rồi giả định nó tự kết nối đến RabbitMQ/JMS.

### 4.4. Điểm dễ bỏ sót khi nâng cấp import

Spring Batch 6 tái tổ chức một phần class/package; ví dụ `Step` ở `org.springframework.batch.core.step.Step` và `RepeatStatus` dùng trong tasklet ở `org.springframework.batch.infrastructure.repeat.RepeatStatus`. Không nên sửa import hàng loạt theo suy đoán: dùng dependency đúng version rồi compile lại từng manager/worker và kiểm tra API từ Javadoc tương ứng.

Đặc biệt, không kết luận một project đã “tương thích 6.x” chỉ vì handler và `RemoteStep` compile được. Reader/writer, step builder, transaction manager, batch metadata serializer và các listener cũng phải hoạt động đúng khi job **thất bại và restart**.

## 5. Cấu hình JobRepository 6.x: tránh một bẫy rất lớn

Từ Spring Batch 6.0, hạ tầng mặc định có khả năng sử dụng **`ResourcelessJobRepository`** thay vì mặc định giả định một JDBC repository. Đây là lựa chọn hợp lý cho một số job đơn giản không cần lưu metadata, nhưng **không phù hợp để manager và worker từ hai JVM tra `StepExecution` và checkpoint dùng chung**.

Nếu manager tưởng mình đang dùng JDBC repository nhưng worker thực tế sử dụng repository không lưu metadata bền vững, việc gửi request có thể thành công, rồi worker không load được execution hoặc manager polling mãi không thấy completion.

### 5.1. Một ví dụ cấu hình JDBC có chủ đích ở 6.x

Khi cấu hình batch infrastructure thủ công, Spring Batch 6 cung cấp annotation chuyên cho kho JDBC:

~~~java
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.configuration.annotation.EnableJdbcJobRepository;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableBatchProcessing
@EnableJdbcJobRepository(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class JdbcMetadataConfiguration {
    // Phải cung cấp bean DataSource tên batchDataSource
    // và bean transaction manager tên batchTransactionManager.
    // Đây không phải một cấu hình đầy đủ có thể chạy độc lập.
}
~~~

**Lưu ý về Spring Boot:** một ứng dụng dùng auto-configuration có thể đã cung cấp `JobRepository` JDBC đúng cách; **không thêm annotation trên một cách máy móc** nếu nó khiến tạo bean trùng hoặc vô hiệu hóa auto-configuration của Boot. Trước deployment, cần **xác minh loại `JobRepository` thực tế**, datasource, schema/table prefix và quyền truy cập ở cả manager lẫn worker.

### 5.2. Không cấu hình hai metadata repository khác nhau

~~~text
ĐÚNG:
Manager pool ─┐
              ├─> metadata DB/schema chung (JDBC JobRepository)
Worker pool ──┘

SAI:
Manager ──> metadata DB A
Worker  ──> metadata DB B / ResourcelessJobRepository
~~~

Mỗi process có thể có **connection pool riêng**, nhưng phải trỏ đúng một metadata store. Nếu có nhiều môi trường/tenant, isolation phải được thể hiện qua DB/schema/prefix và routing kiểm soát rõ; không thể gửi request của môi trường A cho worker chỉ nhìn thấy metadata của môi trường B.

### 5.3. Kiểm tra schema và serializer

Các bảng JDBC thường gồm `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và các bảng context/parameters. Migration giữa version có thể yêu cầu **DDL và chuyển đổi dữ liệu**. Không nên tự nghĩ tên cột hoặc tự đoán script SQL; lấy migration scripts đúng database/version từ Spring Batch rồi chạy thử trên **bản sao dữ liệu thật**.

Ngoài DDL, cần kiểm tra:

- `JobParameters` cũ có đọc được sau nâng cấp không, nhất là kiểu dữ liệu/custom converter.
- `ExecutionContext` cũ có deserialize được không, đặc biệt nếu chứa class Java tùy biến.
- Tên `ItemStream` và các checkpoint key có giữ nguyên không.
- Job/step names và identifying parameters có thay đổi không.
- Optimistic locking/version column và transaction isolation có còn vận hành đúng không.
- Restart một `JobInstance` thất bại **từ trước khi nâng cấp** có cho kết quả chính xác hay không.

**Không trực tiếp `UPDATE STATUS='COMPLETED'` vào metadata để làm job “hết treo”** sau migration. Nếu worker cũ vẫn chạy hoặc side effect chưa nhất quán, sửa status thủ công có thể làm mất tính đúng và phá restart.

## 6. Dependency alignment: không trộn release train

Một ứng dụng Spring Boot thường quản lý phiên bản qua **BOM/parent hoặc dependency management**. Khi có hai ứng dụng manager và worker, cả hai nên dùng một **version catalog/lockfile** đã được CI kiểm thử thay vì để mỗi ứng dụng tự chọn Spring Integration/Batch khác nhau.

| Tập dependency | Hướng tương thích thông dụng | Điều phải kiểm tra |
|---|---|---|
| Spring Batch **5.2.x** | Spring Framework 6.x, Spring Integration 6.x, hệ sinh thái Spring Boot 3.x tương thích | Xem BOM của phiên bản Boot cụ thể; không ép Framework 7 vào Batch 5 |
| Spring Batch **6.0.x** | Spring Framework 7.0, Spring Integration 7.0, hệ sinh thái Spring Boot 4.x tương thích | Kiểm tra BOM, bản vá, JDK và integration adapter |
| Spring Batch **6.1.x** | Dependency được cập nhật tiếp trong nhánh 6.1 | Xem release notes/migration guide 6.1, không đoán rằng BOM 6.0 và 6.1 hoán đổi được |

Nhiều ứng dụng còn dùng Spring AMQP/JMS/Kafka, Jackson, JDBC driver và thư viện monitoring. Một thay đổi major có thể làm ứng dụng **khởi động được** nhưng converter hoặc serializer không đọc được message tồn đọng. Vì vậy kiểm tra **full dependency tree và runtime image**, không chỉ `spring-batch-core`.

### Java và Jakarta

Các thế hệ Spring Framework 6 và 7 đều thuộc hệ sinh thái **Java 17+**, nhưng một số module có yêu cầu JDK cao hơn hoặc cấu hình build khác. Hãy xác định JDK mục tiêu bằng BOM/documentation và chạy cùng JDK ở CI, manager, worker.

Với JMS trong hệ sinh thái Spring hiện đại, các API sử dụng package `jakarta.jms` thay vì `javax.jms`. Nhưng `javax.sql.DataSource` vẫn là interface JDBC trong Java SE. Đây là hai namespace khác nhau:

~~~java
import jakarta.jms.ConnectionFactory; // JMS trong Spring Integration mới
import javax.sql.DataSource;          // JDBC DataSource Java SE
~~~

Không chạy thay thế `javax.` → `jakarta.` trên tất cả source file. Đối chiếu class thực tế, JDK và phiên bản client adapter; sai import có thể khiến một manager compile nhưng worker không khởi động.

### Tác động của serializer

Spring Batch 6.0 hỗ trợ Jackson 3 và cập nhật các thành phần JSON liên quan. Điều đó không chứng minh **`ExecutionContext` cũ, custom JSON object hoặc message broker Java serialization** tự động tương thích. Nếu dự án đang tùy biến mapper/serializer, cần test đọc lại dữ liệu **đã ghi bằng phiên bản cũ**, không chỉ serialize rồi deserialize bằng cùng bản mới.

## 7. Wire protocol: quản trị contract trước khi nâng cấp từng service

Trong hệ thống phân tán, message trên broker có thể tồn tại lâu hơn một pod hoặc một lần deployment. Một request được ghi bằng version A có thể đến tay consumer version B khi rollout đang diễn ra.

### 7.1. Phân biệt message nội bộ của framework và envelope ứng dụng

`StepExecutionRequest` là DTO theo API Spring Batch Integration, không phải một **giao thức JSON xuyên major version** đã được bảo đảm lâu dài. `StepExecutionRequestHandler.handle(...)` mong nhận object hợp lệ đúng version.

Nếu application muốn có contract ổn định khi nâng cấp, có thể bọc một **envelope versioned do ứng dụng tự định nghĩa**:

~~~json
{
  "contractVersion": 2,
  "requestId": "remote-step-901-1",
  "jobExecutionId": 120,
  "stepExecutionId": 901,
  "workerStepName": "ordersWorker",
  "businessKey": "orders/2026-11-26/v1"
}
~~~

Đây là **format minh họa do ứng dụng tự sở hữu**, **không phải payload JSON mặc định của Spring Batch**. Nếu chọn cách này, phải viết adapter:

~~~text
Manager:
  StepExecution đã được lưu
  -> chuyển thành envelope phiên bản hóa
  -> publish lên queue tương ứng

Worker:
  nhận envelope + validate version/schema/ACL
  -> tìm metadata trong JobRepository
  -> map sang StepExecutionRequest của chính phiên bản worker
  -> StepExecutionRequestHandler.handle(...)
  -> cập nhật metadata theo lifecycle
~~~

Không cho phép `businessKey` hoặc `workerStepName` từ message không đáng tin cậy trực tiếp mở file tùy ý/chạy bean tùy ý. Worker nên có allowlist step names, dữ liệu đầu vào đã được kiểm tra và quyền broker tối thiểu.

### 7.2. Giao thức cần những gì?

| Trường | Vai trò | Lưu ý |
|---|---|---|
| `contractVersion` | Kiểm tra khả năng hiểu message | Reject/quarantine version không hỗ trợ |
| `requestId` | Theo dõi và xử lý delivery duplicate | Không thay `stepExecutionId` làm định danh execution |
| `jobExecutionId` | Correlation khi ứng dụng tự dùng | Có thể tra từ metadata; khác với constructor request 6.x |
| `stepExecutionId` | Khóa tham chiếu execution thực | Phải tồn tại trong shared repository |
| `workerStepName` | Chọn đúng worker step | Chỉ chấp nhận tên đã đăng ký |
| `businessKey` | Idempotency / source snapshot | Không thay thế `ExecutionContext` và job parameters |

Với một envelope có trường `jobExecutionId` bổ sung, handler 6.x **không vì vậy nhận constructor ba tham số**. Adapter phải validate trường bổ sung rồi chuyển sang request 6.x đúng API.

### 7.3. Những lựa chọn triển khai

**Một queue theo major contract:** chẳng hạn queue v5 và queue v6 với consumer group được phân tách. Đây là phương án đơn giản và thường an toàn nhất khi không cần backward compatibility.

**Adapter/bridge:** một service chuyên trách đọc message cũ, validate schema, tra metadata và tạo request mới. Cần test idempotency, delivery semantics, failure/restart và phạm vi hỗ trợ; không có bridge “miễn phí”.

**Drain rồi chuyển đổi:** ngừng tạo job mới, đợi queue cũ hết, kiểm tra unacked/DLQ và kết thúc/reconcile execution còn chạy, sau đó nâng cấp cả manager và worker. Với batch workload có khung bảo trì, đây thường là lựa chọn dễ chứng minh tính đúng nhất.

Không dùng một queue chung có cả object serialized 5.x và 6.x rồi kỳ vọng `MessageConverter` tự phân biệt an toàn bằng tên class Java.

## 8. Response handling và version compatibility

Worker handler có thể trả về `StepExecution`. Nhưng **`RemoteStep` 6.x dùng polling `JobRepository`** để xác định hoàn tất, không nhất thiết cần reply queue.

Remote partitioning có thể dùng **reply aggregation**: manager phải nhận kết quả của N partition và đối chiếu với các `StepExecution` kỳ vọng. Nếu trước khi nâng cấp job dùng N partition reply nhưng sau khi đổi kiến trúc lại dùng một `RemoteStep` polling, đây không còn là cùng hợp đồng response.

| Khía cạnh | Manager/worker 5.x remote partitioning | 6.x `RemoteStep` |
|---|---|---|
| Work unit | Một `StepExecution` cho mỗi partition | Một remote worker step execution cho logical step |
| Request | Thường một request cho mỗi partition | Request cho remote step |
| Kết quả | Reply aggregation hoặc theo dõi metadata theo cấu hình | Poll metadata repository |
| Correlation | Job/step execution ID + partition identity | Exact step execution ID; tham chiếu job qua repository |
| Khi reply thất lạc | Manager có thể thiếu một kết quả dù worker đã xong | Reply không phải điều kiện bắt buộc; tra repository |
| Khi manager restart | Giữ tập partition đã tạo; không tính reply cũ thành partition mới | Theo dõi đúng execution; không dispatch mù quáng khi worker cũ còn chạy |

**Tình huống hay bị hiểu sai:** một message `COMPLETED` từ worker cũ không thể dùng để kết luận `StepExecution` mới đã hoàn tất chỉ vì cùng `stepName`. Correlation phải gắn với **exact job/step execution identity**, đặc biệt khi job đã được restart.

## 9. Migration 5.x → 6.x: nâng API không đủ

### 9.1. Đặt mục tiêu kiến trúc trước

| Hệ thống hiện tại | Muốn đạt | Cách tiếp cận |
|---|---|---|
| Local step ở 5.x | Chạy **một step** trên worker 6.x | Thiết kế mới bằng `RemoteStep` 6.x và request transport |
| Remote partitioning 5.x (32 partition) | Giữ 32 phần việc song song | Nâng **remote partitioning** tương thích, không thay bằng một `RemoteStep` |
| Remote chunking 5.x | Manager tiếp tục đọc, worker xử lý chunk | Nâng remote chunking với contract chunk, không đổi thành step request |
| Job cũ cần restart sau nâng cấp | Giữ checkpoint và side effect đúng | Kiểm tra schema, serialization và restart từ metadata cũ |
| Triển khai manager/worker lệch major trong vài giờ | Không mất hoặc chạy trùng việc | Drain, tách queue hoặc viết bridge được kiểm thử; không mix trực tiếp |

Một số nhóm chọn “nâng cả hai ứng dụng lên 6” nhưng quên rằng `JobRepository` hoặc schema nghiệp vụ vẫn nằm trên DB cũ; đây là lỗi tương thích **metadata**, không phải lỗi classpath.

### 9.2. Trình tự nâng cấp an toàn

~~~mermaid
flowchart TD
    A[Inventory: images, dependencies, jobs, queues] --> B[Chụp backup DB + metadata + manifest]
    B --> C[Contract + migration rehearsal trên staging]
    C --> D{Restart dữ liệu cũ đạt?}
    D -->|Không| E[Fix serializer/DDL/step config]
    E --> C
    D -->|Có| F[Đóng cửa nhận job mới]
    F --> G[Drain queue và worker cũ]
    G --> H[Đối soát execution còn STARTED]
    H --> I[Migrate metadata theo tài liệu]
    I --> J[Deploy worker + manager tương thích]
    J --> K[Smoke test end-to-end, failure/restart]
    K --> L{Đạt tiêu chí?}
    L -->|Có| M[Mở scheduler và theo dõi]
    L -->|Không| N[Contain, rollback theo kế hoạch]
~~~

Diễn giải:

1. **Inventory:** ghi chính xác version Batch, Integration, Boot, Framework, Java, driver, broker adapter, serializer, tên queue và trạng thái job đang chạy.
2. **Backup:** sao lưu metadata DB và manifest/input; version DB snapshot phải phù hợp với thời điểm dừng ghi.
3. **Rehearsal:** clone DB/queue input vào staging; chạy cả happy path lẫn restart job đã fail trong version cũ.
4. **Quiesce:** tạm ngừng scheduler/API tạo job mới, chờ manager và worker hoàn tất; dừng consumer nhận request mới.
5. **Drain:** đối soát pending, unacked và DLQ; không chỉ nhìn queue depth bằng 0.
6. **Migrate:** chạy DDL và chuyển đổi serializer/context theo migration guide chính thức, có kiểm tra trước/sau.
7. **Deploy:** khởi động các worker cùng contract, bảo đảm readiness, sau đó kích hoạt manager/scheduler phù hợp.
8. **Verify:** launch một job thử với input bất biến; đối chiếu metadata và output, gây lỗi giữa chunk rồi restart.
9. **Observe:** theo dõi queue age, handler errors, `JobRepository` latency, duplicate processing và business reconciliation.

**Không nên nâng cấp nhiều thành phần tại cùng một thời điểm nếu không thể xác định nguyên nhân rollback.** Có thể chia thay đổi thành nhiều đợt, nhưng mỗi đợt phải giữ manager/worker/metadata contract đồng bộ và được kiểm chứng; không “rolling” qua hai major không tương thích như thể chỉ là thay pod.

## 10. Rollout, rollback và jobs đang chạy dở

### 10.1. Vì sao rolling deployment đơn giản có thể không an toàn?

Giả sử queue đang có 1.000 request version 5.x, rồi deployment worker đổi dần sang 6.x:

~~~text
T0: manager 5.x publish request v5
T1: queue có 1.000 request v5
T2: 30% pod worker đã là 6.x
T3: broker giao request v5 cho pod 6.x
T4: converter/handler không hiểu payload hoặc metadata không tương thích
T5: message được retry / đi DLQ / bị giao lại
~~~

Lỗi có thể xuất hiện “ngẫu nhiên” do broker chọn consumer nào nhận message. Nếu cố khắc phục bằng retry vô hạn, queue age tăng và job treo, còn worker cũ có thể vẫn chạy những execution khác.

### 10.2. Blue/green có cần dùng hai DB metadata không?

Blue/green có thể dùng **hai queue/consumer group khác nhau** và version-specific routing. Tuy nhiên, nếu manager và worker cả hai nhánh cùng đọc/ghi **một metadata DB với schema không tương thích**, hệ thống vẫn có rủi ro. Nếu tách metadata DB thành hai nơi, bạn phải quản lý ranh giới JobInstance/JobExecution hoàn toàn riêng và tránh gửi request qua lại sai kho.

Một cách triển khai an toàn cho migration major:

- **Blue**: manager + worker 5.x, queue v5, metadata theo schema hiện tại; đóng nhận job mới khi cần.
- **Green**: manager + worker 6.x, queue v6, metadata đã migrate hoặc môi trường riêng, chỉ chạy job đã được định tuyến rõ.
- Chỉ cut over sau khi đã đối soát job cũ, đảm bảo không còn request chưa biết trạng thái và xác minh restart strategy.

Không coi một bản sao database đang lag là metadata repository tương đương: worker ghi trạng thái vào nơi khác sẽ khiến manager poll không thấy đúng execution.

### 10.3. Rollback có thể cần phục hồi DB

Rollback image 6.x về 5.x **không chắc** đồng nghĩa hoàn nguyên toàn bộ hệ thống nếu schema hoặc serializer metadata đã nâng và worker mới đã ghi vào đó. Một rollback plan thực sự phải trả lời:

- DDL migration có reversible không? Nếu không, phục hồi backup như thế nào?
- Có job mới đã chạy trên metadata 6.x chưa? Làm sao đối soát output trước khi restore?
- Queue có request `StepExecutionRequest` mới không? Cần drain/quarantine ra sao?
- Worker 6.x có còn đang chạy và ghi side effect không?
- Bản ghi `ExecutionContext` mới có class/format mà 5.x không đọc được không?

**Không restore metadata DB một cách cô lập trong khi business DB/output đã thay đổi mà không có kế hoạch reconciliation.** Metadata và kết quả nghiệp vụ phải được đối soát theo idempotency key/snapshot.

## 11. Retry/restart khi version thay đổi

Không nên mặc định một job đang chạy dở có thể restart xuyên major version mà không kiểm thử. Spring Batch nhận diện `JobInstance` bằng **job name + identifying `JobParameters`**, còn progress reader có thể nằm trong `StepExecutionContext`.

Một restart an toàn cần:

1. **Tên job/step/partition** không đổi ngoài chủ đích; đổi tên làm framework có thể tạo execution khác.
2. `JobParameters` identifying giữ nguyên để tham chiếu đúng instance cũ.
3. `ExecutionContext` cũ có thể deserialize và được reader mới hiểu đúng.
4. Tên `ItemStream`, key checkpoint và thứ tự đọc có ý nghĩa như cũ.
5. Dataset/snapshot không đổi hoặc có version rõ ràng.
6. Writer/side effect idempotent, kể cả nếu chunk cũ đã commit nhưng metadata chưa cập nhật.
7. Không có worker cũ còn giữ execution khi manager mới bắt đầu dispatch.

### Ví dụ: thay tên ItemStream phá checkpoint

~~~java
// Version cũ:
new JdbcCursorItemReaderBuilder<Long>()
        .name("ordersReaderV1")
        // ...
        .build();

// Version mới đổi tên tùy ý:
new JdbcCursorItemReaderBuilder<Long>()
        .name("ordersReaderV2")
        // ...
        .build();
~~~

Ngay cả khi request/handler tương thích, reader mới có thể không tìm thấy các checkpoint key với prefix cũ. Nếu step đã commit 200.000 record, restart từ đầu dễ gây xử lý lại hoặc trùng side effect. Do đó **migration test phải bao gồm lỗi giữa chừng và restart**, không chỉ kiểm tra job mới chạy thành công.

### Duplicate dispatch trong giai đoạn đổi phiên bản

Một message đã được broker giao cho worker A có thể được giao lại cho worker B sau ACK timeout. Nếu worker A chưa dừng hẳn, cả hai có thể cùng gây tác động nghiệp vụ. Bản upgrade không tự giải quyết vấn đề này.

Cần ít nhất: giới hạn một execution trên mỗi worker khi chưa chứng minh thread safety, idempotency key nghiệp vụ, transaction/unique constraint, và khi có tài nguyên độc quyền dài hạn thì lease/fencing thích hợp. `JobRepository` giúp theo dõi lifecycle nhưng không thay một cơ chế exactly-once xuyên broker, database và API ngoài.

## 12. Bảo mật và compatibility của message converter

Một lỗi migration thường gặp không phải constructor sai mà là **deserialize nhầm loại object** hoặc kích hoạt quá rộng các class được phép deserialize. Với broker dùng chung, điều này còn là rủi ro bảo mật.

### Nguyên tắc thực hành

- Chốt **content type/schema/version** ở message header và payload, không dựa vào tên Java class do người gửi tùy ý khai báo.
- Không chấp nhận Java native serialization từ nguồn không tin cậy nếu có lựa chọn khác.
- Nếu cần JSON, dùng DTO envelope ứng dụng với whitelist field rõ, không mở polymorphic deserialization tùy ý.
- Validate `stepName` nằm trong **allowlist** các worker step mà deployment được phép chạy.
- Xác thực broker publisher; chỉ manager hợp lệ có quyền publish request.
- Dùng TLS, secret rotation, service account riêng và môi trường/tenant routing rõ.
- Không ghi raw `ExecutionContext`, token hoặc thông tin nhạy cảm vào DLQ/error log.
- Có giới hạn payload size, schema validation, retry limit và DLQ cho poison message.

**Không dùng DLQ như một kho lưu vô thời hạn mà không có cách replay kiểm soát.** Khi replay message cũ sau deploy, phải biết nó thuộc contract/version nào, job/step execution nào và side effect nào đã xảy ra.

## 13. Ma trận lỗi thường gặp khi không tương thích

| Triệu chứng | Nguyên nhân/version skew khả dĩ | Hướng điều tra và khắc phục |
|---|---|---|
| `NoClassDefFoundError` / `NoSuchMethodError` | Trộn Batch/Integration/Framework libraries | In dependency tree và image SBOM; đồng bộ BOM |
| Không tìm thấy `RemoteStep` | Dự án còn ở Batch 5.x | Nâng cả stack hoặc tiếp tục remote partitioning |
| Không compile `setJobExplorer` | Dùng handler 6.x | Chuyển sang `setJobRepository` và repository phù hợp |
| Không compile `setJobRepository` | Dùng handler 5.x | Cấu hình `JobExplorer` theo API 5.x |
| Constructor `StepExecutionRequest` sai số tham số | Trộn mã 5.x và 6.x | Sửa theo Javadoc đúng major version |
| Worker không deserialize được request | Serializer/schema Java object khác | Quarantine message, đồng bộ wire contract, test đọc payload cũ |
| Worker không tìm thấy `StepExecution` | Sai ID, DB/schema khác, repository resourceless | Kiểm tra repository thực tế, schema/table prefix và request identity |
| Manager polling mãi `STARTED` | Worker chưa chạy, ghi vào DB khác, converter lỗi, metadata commit lỗi | Kiểm tra queue, handler, `JobRepository`, worker log |
| `OptimisticLockingFailureException` | Nhiều updater cùng sửa execution hoặc race | Xác định duplicate dispatch/worker cũ, không sửa version column thủ công |
| `ExecutionContext` deserialize lỗi | Custom object/serializer khác version | Migrate/test context dữ liệu cũ, cố định class/schema |
| Restart chạy lại nhiều item | Đổi reader name, input, sorting/checkpoint | Giữ ItemStream key và snapshot, đối soát dữ liệu |
| Job 6.x tạo nhưng không thấy trong DB | Đang dùng resourceless repository hoặc DB khác | Bật JDBC repository, xác minh quyền schema |
| Reply trễ bị tính là execution mới | Correlation theo stepName thay vì ID | Đối chiếu exact job/step execution ID và attempt |
| Tăng worker nhưng throughput giảm | DB pool/metadata/broker quá tải | Đo active/pending, queue age, lock wait, partition skew |

Không nên xử lý mọi lỗi bằng cách tăng retry. Lỗi **schema/version không tương thích** thường là lỗi có tính **permanent** đối với một message; retry vô hạn chỉ gây vòng lặp và kéo dài thời gian phục hồi.

## 14. Kiểm thử tương thích theo hai chiều

Một CI pipeline tốt cho một hệ thống manager/worker có thể gồm:

~~~text
1. Static/API checks
   -> Compile manager/worker theo BOM đã khóa.
   -> So sánh dependency graph và JDK image.

2. Contract tests
   -> Producer phát một request hợp lệ.
   -> Consumer deserialize và validate đúng stepExecutionId.
   -> Kiểm tra failure khi contractVersion không được hỗ trợ.

3. Metadata compatibility tests
   -> Tạo job/step execution trên DB phiên bản cũ.
   -> Thử đọc với code phiên bản mới sau migration.
   -> Kiểm tra StepExecutionContext và JobParameters.

4. End-to-end
   -> Manager chạy Job, gửi request tới broker.
   -> Worker tra đúng StepExecution, xử lý, cập nhật repository.
   -> Manager phát hiện COMPLETED qua polling.

5. Fault injection
   -> Kill worker giữa chunk / trước ACK.
   -> Kill manager khi worker còn chạy.
   -> Broker mất kết nối, DB metadata mất kết nối.
   -> Kiểm tra retry, restart và idempotency.

6. Upgrade rehearsal
   -> Phát request với version cũ rồi drain.
   -> Nâng manager + worker + metadata trên staging.
   -> Restart job lỗi cũ và đối soát output.
~~~

### 14.1. Contract test cho envelope do ứng dụng sở hữu

Nếu đã định nghĩa envelope versioned, worker nên **reject version lạ trước khi dispatch**. Ví dụ Java 17:

~~~java
public record RemoteWorkEnvelope(
        int contractVersion,
        String workerStepName,
        long stepExecutionId,
        String requestId) {
}

public final class RequestContractValidator {
    private static final int SUPPORTED_VERSION = 2;

    public void validate(RemoteWorkEnvelope request) {
        if (request.contractVersion() != SUPPORTED_VERSION) {
            throw new IllegalArgumentException("Unsupported contractVersion");
        }
        if (!"ordersWorker".equals(request.workerStepName())) {
            throw new IllegalArgumentException("Unknown worker step");
        }
        if (request.stepExecutionId() <= 0 ||
                request.requestId() == null ||
                request.requestId().isBlank()) {
            throw new IllegalArgumentException("Invalid request identity");
        }
    }
}
~~~

**Đây là code ứng dụng minh họa, không phải Spring Batch request class.** Khi đã validate, adapter của worker 6.x mới có thể tạo `new StepExecutionRequest(workerStepName, stepExecutionId)` và gọi `StepExecutionRequestHandler`. Trong thực tế còn cần xác thực publisher, kiểm tra execution thuộc đúng job/tenant và không ghi nhận một duplicate chưa được đối soát là một execution mới.

### 14.2. Test gửi/nhận message qua broker thật

Unit test gọi trực tiếp `handler.handle(...)` **không chứng minh** message converter hoạt động, ACK/redelivery an toàn hay worker có cùng repository. Hãy dùng hai process/container thật với broker và DB test; kiểm tra request chưa ACK khi worker bị kill, message đưa vào DLQ khi sai contract và khả năng xác định đúng execution từ log.

### 14.3. Test restart từ dữ liệu cũ

Một test quan trọng nên có:

1. Bản **5.x** tạo `JobInstance` với xác định `JobParameters` cố định.
2. Một worker xử lý vài chunk, commit checkpoint rồi fail có chủ đích.
3. Sao chép metadata và business data sang staging, áp migration 6.x.
4. Dùng bản **6.x** thử restart đúng job instance nếu migration path hỗ trợ; không tạo `run.id` mới.
5. So sánh **tập khóa nghiệp vụ** thay vì chỉ `readCount`, kiểm tra không trùng/thiếu.
6. Xác minh các job/step đã `COMPLETED` không bị thực thi lại trái chủ đích.

Nếu không bảo đảm restart xuyên major với reader/serializer hiện có, một phương án triển khai là **cho job cũ hoàn tất trên stack cũ**, chỉ bắt đầu job mới trên stack mới. Quyết định phải được ghi vào migration plan, không phó mặc cho vận may.

## 15. Quan sát khi triển khai nhiều phiên bản

Khi sự cố xuất hiện ở một số pod mà không tái hiện trên pod khác, hãy đưa version và contract vào log/metric:

| Trường | Lý do |
|---|---|
| `managerImageDigest`, `workerImageDigest` | Biết chính xác build nào gửi/nhận |
| `springBatchVersion` / `springIntegrationVersion` | Nhận diện version skew |
| `contractVersion` / `serializerName` | Điều tra deserialize và routing |
| `jobExecutionId`, `stepExecutionId` | Tương quan execution thật |
| `workerStepName` | Kiểm tra StepLocator |
| `requestId`, `messageId`, `redelivered` | Phân biệt retry, delivery duplicate |
| `BatchStatus` / `ExitStatus` | Kết quả lifecycle, không chỉ broker ACK |
| `queueAge`, `DLQCount`, `handlerErrors` | Đo hậu quả của poison messages |
| `repositoryLatency`, `dbPoolPending` | Phát hiện bottleneck metadata |

### Cảnh báo nên bật

- Có cùng queue được consume bởi **hai major version không được tuyên bố tương thích**.
- Số lượng deserialize errors hoặc DLQ tăng ngay sau deploy.
- `StepExecution` mới `STARTED` quá SLA trong khi queue còn request không được xử lý.
- Không đọc được metadata/context của job trước nâng cấp.
- Duplicate `stepExecutionId` được xử lý bởi hai worker instance đồng thời.
- Số lượng business key đã ghi không khớp với tập input mong đợi.

**Không ghi raw serializer payload chứa secret vào log.** Với lỗi version, log có thể ghi schema/contract version, hashed request ID, step execution ID và failure class đủ để điều tra.

## 16. Runbook khi nghi ngờ version skew

### Bước 1 — Dừng mở rộng phạm vi lỗi

Tạm dừng scheduler/producer tạo request mới nếu tỷ lệ lỗi bất thường; giữ lại queue, DLQ và log cho forensic. Không xóa message hàng loạt hoặc tăng retry vô hạn.

### Bước 2 — Chụp danh sách thành phần

Lấy image digest, Batch/Integration/Boot version, JDK, broker adapter và converter của manager, tất cả worker. Kiểm tra có pod cũ còn sống trong rolling update hay không.

### Bước 3 — Đối chiếu contract

Với một message lỗi, xác định contract version và `stepExecutionId`. Đối chiếu schema request với constructor/handler của worker. Xác định lỗi xảy ra ở converter, `StepLocator`, metadata lookup hay business step.

### Bước 4 — Xác minh kho metadata

Kiểm tra manager và worker có cùng JDBC `JobRepository` thật không, cùng DB/schema/prefix và data-source credentials. Nếu nghi ngờ bản 6.x đã dùng `ResourcelessJobRepository` ngoài ý muốn, khắc phục configuration trước khi replay.

### Bước 5 — Đối soát execution và side effect

Từ `jobExecutionId`/`stepExecutionId`, kiểm tra trạng thái `STARTED`, `COMPLETED`, `FAILED`, checkpoint, worker còn sống và output nghiệp vụ. **Không replay** nếu worker cũ có thể còn xử lý.

### Bước 6 — Chọn đường phục hồi

- Sai version message nhưng execution chưa chạy: triển khai consumer tương thích hoặc chuyển đổi qua bridge đã kiểm thử, rồi replay có kiểm soát.
- Metadata/context không đọc được: dùng migration/restore rehearsal, không tự sửa raw serialized columns.
- Execution đã commit output nhưng ACK mất: áp idempotency và đối soát trước khi cho xử lý lại.
- Job dở dang không restart được trên stack mới: cân nhắc hoàn tất trên stack cũ hoặc kế hoạch chuyển dữ liệu/bù trừ có review.

### Bước 7 — Mở lại lưu lượng có giám sát

Khởi động một job smoke test, theo dõi queue, metadata, business output và log version. Sau đó mở dần scheduler/worker traffic. Ghi rõ quyết định migration/rollback để tránh lặp sự cố ở lần deploy kế tiếp.

## 17. Checklist tương thích trước production

- [ ] Đã xác định rõ Spring Batch major/minor/patch của manager và worker.
- [ ] Chỉ dùng `RemoteStep` trên Spring Batch **6.0+**; không lẫn với remote partitioning 5.x.
- [ ] `StepExecutionRequest` constructor và `StepExecutionRequestHandler` setter đúng phiên bản.
- [ ] Spring Batch, Integration, Framework, Boot, Java, JMS/AMQP và Jackson theo một BOM đã kiểm thử.
- [ ] Không có worker cũ nhận request mới không tương thích trong rolling update.
- [ ] Có một `JobRepository` JDBC **dùng chung, lưu bền vững** cho remote execution; không vô tình dùng resourceless.
- [ ] Metadata schema, table prefix, serializer và custom `ExecutionContext` đã được kiểm thử với dữ liệu cũ.
- [ ] Wire contract versioned hoặc tách queue rõ ràng; không phụ thuộc Java serialization xuyên major.
- [ ] Worker chỉ chạy step name được đăng ký/cho phép.
- [ ] Message sai schema vào DLQ có cảnh báo, không retry vô hạn.
- [ ] Có kế hoạch drain queue, quiesce manager/worker, backup và restore metadata.
- [ ] Đã kiểm thử restart job cũ đang fail sau migration hoặc chốt phương án hoàn tất trên stack cũ.
- [ ] Không thay tên job, step, ItemStream và partition một cách tùy tiện.
- [ ] Output/side effect idempotent, input snapshot/cutoff ổn định.
- [ ] Có runbook cho lost ACK, duplicate request, manager/worker crash và metadata outage.
- [ ] Đã đo CPU, queue age, DB pool pending, metadata polling/commit và business correctness.

## 18. Bài tập thực hành

### Bài 1 — Phân loại API 5.x và 6.x

Cho các đoạn code dùng `new StepExecutionRequest("worker", 10L, 20L)`, `setJobExplorer(...)`, `setJobRepository(...)`, `new RemoteStep(...)`. Xác định đoạn nào thuộc Spring Batch 5.x và 6.x. Viết lại cấu hình handler đúng theo hai major version và giải thích vì sao không thể copy-paste một bean config từ 5.x sang 6.x.

### Bài 2 — Thiết kế ma trận compatibility

Một hệ thống có manager Batch 6.0, hai worker Batch 6.0 và một worker Batch 5.2 trên cùng request queue. Chỉ ra những cặp có thể bị lỗi, đề xuất ít nhất hai phương án rollout không để worker 5.2 consume request 6.0. Nêu rõ khi nào cần drain, tách queue hoặc bridge.

### Bài 3 — Phát hiện repository sai

Giả lập manager trỏ metadata DB A, worker trỏ DB B hoặc dùng repository không lưu trạng thái. Quan sát vì sao manager poll không thấy completion. Bổ sung startup check/health check để xác nhận loại repository và thông tin routing DB **không lộ secret**.

### Bài 4 — Đọc lại checkpoint cũ

Dùng một reader có `.name("ordersReaderV1")`, tạo job thất bại sau vài chunk, rồi sửa tên thành `ordersReaderV2` trên phiên bản mới. Kiểm tra restart và thiết kế biện pháp giữ/migrate key checkpoint. Giải thích vì sao test job mới chạy thành công không đủ chứng minh tương thích.

### Bài 5 — Nâng phiên bản không mất partition

Một job remote partitioning 5.x có 24 partition. Thiết kế nâng lên 6.x sao cho vẫn có 24 `StepExecution` con và ranh giới đầu vào không thay đổi. So sánh với việc thay hẳn bằng một `RemoteStep` và xác định khác biệt throughput/restart.

### Bài 6 — Fault injection sau deploy

Cho worker 6.x hoàn thành nghiệp vụ rồi mất ACK; broker phát lại request khi pod cũ có thể còn sống. Kiểm thử cách phát hiện cùng execution chạy trùng, idempotency output, lease/fencing khi cần và log `managerVersion`/`workerVersion`/`stepExecutionId` để đối soát.

### Câu hỏi tự kiểm tra

1. `RemoteStep` có từ phiên bản Spring Batch nào?
2. Vì sao Spring Batch 6 có `JobRepository` mặc định không lưu metadata có thể là bẫy khi chạy từ xa?
3. Khác biệt chính giữa `StepExecutionRequest` ở 5.2.x và 6.x là gì?
4. Vì sao Spring Batch và Spring Integration cần được quản lý cùng release train?
5. Một request đang trong queue có thể sống lâu hơn worker deployment thế nào?
6. Tại sao rollback image không đủ nếu metadata schema/serializer đã được nâng cấp?
7. Làm sao chứng minh có thể restart job 5.x đang fail trên hệ thống 6.x mà không xử lý lại dữ liệu sai?
8. Vì sao thêm worker pod và nâng phiên bản thư viện không tự tạo thêm partition?

## 19. Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Batch 6.0 — What's New](https://docs.spring.io/spring-batch/reference/6.0/whatsnew.html): remote step, repository mặc định, JobRepository/JobExplorer và dependency nâng cấp.
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/6.0/scalability.html): `RemoteStep` và remote partitioning.
- [Spring Batch API — RemoteStep](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/remote/RemoteStep.html): constructor và polling.
- [Spring Batch 5.2 API — StepExecutionRequest](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/integration/partition/StepExecutionRequest.html): constructor có `jobExecutionId`.
- [Spring Batch 6.0 API — StepExecutionRequest](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/partition/StepExecutionRequest.html): constructor chỉ cần `stepExecutionId`.
- [Spring Batch 5.2 API — StepExecutionRequestHandler](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/integration/partition/StepExecutionRequestHandler.html): `setJobExplorer`.
- [Spring Batch 6.0 API — StepExecutionRequestHandler](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/partition/StepExecutionRequestHandler.html): `setJobRepository`.
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/6.0/schema-appendix.html): schema, optimistic locking và migration.

Tài liệu versioned giúp kiểm tra **API chính xác của bản sẽ chạy**. Khi sử dụng Spring Batch 6.1 hoặc phiên bản mới hơn, cần xem release notes riêng của nhánh đó, không coi ví dụ 6.0 là toàn bộ danh sách thay đổi.

## 20. Tổng kết

**Tương thích phiên bản khi dùng RemoteStep** không chỉ là trùng số phiên bản của hai thư viện. Đó là sự nhất quán giữa **API manager/worker, request schema, serializer, hạ tầng Spring Integration, metadata repository, checkpoint và quy tắc restart**. `RemoteStep` xuất hiện từ Spring Batch 6.0 và dùng repository polling; Spring Batch 5.x dùng các cơ chế phân tán khác như remote partitioning, với request và handler có API khác.

Trong sản xuất, chiến lược an toàn là **pin dependency, dùng JDBC `JobRepository` chung có lưu bền vững, version hóa hoặc tách queue, drain trước khi đổi major, rehearsal migration và thử restart trên dữ liệu cũ**. Chỉ mở lại lưu lượng khi manager, worker, broker, metadata và kết quả nghiệp vụ đã được kiểm chứng đồng bộ. Đó là điều kiện để nâng cấp Spring Batch mà không đánh đổi khả năng phục hồi và tính đúng của dữ liệu.
