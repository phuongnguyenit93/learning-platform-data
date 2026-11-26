# Xử lý response của remote worker trong Spring Batch

## 1. Khi worker báo “xong”, manager thực sự biết điều gì?

Giả sử một job cuối ngày có bước `renderStatementWorker` được chuyển sang một worker service. Manager đã gửi yêu cầu chạy bước đó qua message broker. Worker tạo xong tệp báo cáo và cập nhật metadata. Nhưng ngay sau đó kết nối broker bị đứt, nên manager không nhìn thấy phản hồi nào từ hàng đợi reply.

Tình huống này đặt ra ba câu hỏi rất khác nhau:

1. **Worker đã làm xong việc nghiệp vụ chưa?**
2. **Spring Batch đã lưu trạng thái `StepExecution` tương ứng chưa?**
3. **Có một response/reply message đi tới manager hay chưa?**

Ba câu trả lời không nhất thiết giống nhau. Một message `ACK` từ broker chỉ xác nhận việc giao nhận theo hợp đồng transport; một Java object `StepExecution` được handler trả về chưa chắc đã được gửi qua mạng; một tệp đầu ra tồn tại cũng chưa chắc metadata batch đã ghi nhận `COMPLETED`.

Bài **“Xử lý response của remote worker”** thuộc chương **Remote Step** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module nhằm mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán; do đó xử lý kết quả từ xa phải đi kèm thread safety, retry/restart, đo nút thắt và vận hành job theo tài nguyên thực tế.

Sau bài học, bạn có thể:

- Phân biệt **return value của handler**, **reply message**, **metadata `StepExecution`** và **broker acknowledgment**.
- Hiểu vì sao `RemoteStep` của **Spring Batch 6.x** theo dõi hoàn thành bằng **polling `JobRepository`**, còn remote partitioning có thể dùng reply aggregation.
- Đọc `BatchStatus` và `ExitStatus` mà không nhầm trạng thái kỹ thuật với kết quả nghiệp vụ.
- Thiết kế correlation, timeout, duplicate handling, late reply, dead-letter và đối soát trước restart.
- Xác định hành động đúng khi worker chết, message thất lạc hoặc manager bị khởi động lại.
- Đặt metric/runbook để scale worker nhưng vẫn bảo toàn kết quả.

**Phạm vi phiên bản:** `RemoteStep` xuất hiện từ **Spring Batch 6.0**. `StepExecutionRequestHandler` cũng được dùng trong remote partitioning của các phiên bản trước, nhưng API request/handler giữa 5.x và 6.x khác nhau. Các đoạn mã tích hợp bên dưới ghi rõ mục đích; cấu hình broker thật phải tuân theo phiên bản Spring Batch/Spring Integration đã khóa trong dự án.

## 2. Bốn tầng “kết quả” cần tách biệt

| Tầng | Dữ liệu biểu diễn | Ai cung cấp? | Có đủ để manager kết luận job thành công? |
|---|---|---|---|
| **Kết quả nghiệp vụ** | Bản ghi đã ghi, file đã xuất, sự kiện đã công bố | Worker logic và hệ thống đích | **Chưa**: có thể chưa commit metadata hoặc side effect chưa nhất quán |
| **`StepExecution` trong repository** | `BatchStatus`, `ExitStatus`, read/write count, checkpoint, thời điểm bắt đầu/kết thúc | Spring Batch worker lifecycle | **Nguồn sự thật về execution**, nhưng vẫn cần đối soát nghiệp vụ khi có side effect ngoài transaction |
| **Return từ handler** | `StepExecution` do `StepExecutionRequestHandler.handle(...)` trả về | Worker message endpoint | **Chưa**: chỉ là return của method trong process, không tự bảo đảm đã được deliver |
| **Reply/ACK từ transport** | Response event, AMQP/JMS ACK, correlation/message ID | Message broker và integration adapter | **Chưa**: ACK có thể chỉ xác nhận giao/nhận message; reply có thể trễ, trùng hoặc mất |

Đây là nguyên tắc chủ đạo: **không nâng trạng thái job thành công chỉ vì một message “success” đến trước khi kiểm tra execution và tác động nghiệp vụ cần thiết**. Với `RemoteStep` 6.x, framework không yêu cầu manager lấy trạng thái hoàn thành từ một reply queue riêng; nó dùng metadata repository để theo dõi worker.

### Những khái niệm thường bị gọi chung là “response”

~~~text
Request:        StepExecutionRequest(stepName, stepExecutionId)
Handler return: StepExecution
Repository:     BATCH_STEP_EXECUTION + ExecutionContext
Transport ACK:  Message đã được consumer/broker xử lý theo cơ chế transport
Optional reply: Message được worker publish lại để manager/aggregator nhận
Business result: File/DB/API đã thay đổi
~~~

Tùy kiến trúc, **optional reply** có thể không tồn tại. Khi debug, phải hỏi người vận hành đang đề cập tầng nào thay vì dùng từ “response” không có định danh.

## 3. RemoteStep 6.x: manager theo dõi bằng JobRepository

Trong Spring Batch 6.x, manager đưa một `RemoteStep` vào flow của `Job`. Bước này gửi `StepExecutionRequest` tới worker qua Spring Integration, rồi theo dõi trạng thái execution trong `JobRepository` bằng cơ chế **polling**. Worker dùng `StepExecutionRequestHandler` để tìm bean `Step`, chạy và lưu trạng thái.

~~~mermaid
sequenceDiagram
    participant M as Manager RemoteStep
    participant R as Shared JobRepository
    participant Q as Request broker
    participant H as Worker Handler
    participant W as Worker Step
    M->>R: Tạo/lưu StepExecution
    M->>Q: StepExecutionRequest
    Q->>H: Deliver request
    H->>R: Tra StepExecution và ExecutionContext
    H->>W: Step.execute(stepExecution)
    W->>W: Reader/processor/writer, transaction
    W->>R: Commit trạng thái/checkpoint
    W-->>H: StepExecution sau thực thi
    H-->>Q: Return tại endpoint (reply tùy flow)
    loop Polling cho đến trạng thái kết thúc hoặc timeout
        M->>R: Đọc trạng thái StepExecution
        R-->>M: STARTED/COMPLETED/FAILED/...
    end
    M->>M: Tiếp tục flow hoặc xử lý lỗi
~~~

Điều quan trọng của sơ đồ:

- Mũi tên từ `H` về `Q` **không** có nghĩa một reply queue được tự động tạo. Kết quả return từ `handle` có thể được flow sử dụng, bỏ qua có chủ đích hoặc định tuyến ra một channel tùy cấu hình.
- Manager `RemoteStep` có thể biết worker đã `COMPLETED` **dù không có reply message riêng**, miễn metadata được lưu và manager truy cập được repository.
- Nếu worker tạo file thành công nhưng metadata vẫn `STARTED` do sự cố, manager **chưa có căn cứ kỹ thuật để coi step đã hoàn tất**.
- Không dùng `RemoteStep` như tên gọi khác của remote partitioning: một remote step không tự tạo N execution để chia dữ liệu.

### Điều kiện tối thiểu để polling có ý nghĩa

1. Manager và worker dùng cùng **metadata database/schema** Spring Batch tương thích.
2. `StepExecutionRequest` trỏ đúng `stepExecutionId` đã được lưu.
3. Worker đăng ký đúng `stepName` mà `StepLocator` tìm được.
4. Worker thực thi qua lifecycle Spring Batch để trạng thái và checkpoint được cập nhật.
5. Manager có cấu hình polling interval, timeout và cách xử lý lỗi phù hợp với SLA.
6. Không tồn tại hai manager tự ý dispatch cùng một execution mà không có chiến lược chống duplicate.

Nếu chỉ gửi/nhận message qua broker mà mỗi ứng dụng trỏ tới một `JobRepository` riêng, manager có thể chờ mãi mặc dù worker xử lý dữ liệu nghiệp vụ; đây là lỗi **chia tách metadata**, không phải lỗi reply queue.

## 4. Remote partitioning: response có thể được tổng hợp từ nhiều worker

Remote partitioning có **hợp đồng khác**. Manager `Partitioner` tạo nhiều `StepExecution` con, gửi các request riêng và cần tổng hợp kết quả của **tất cả partition liên quan** trước khi manager step kết thúc.

~~~mermaid
flowchart LR
    M[Manager partition step] --> P[Partitioner]
    P --> Q[(N request messages)]
    Q --> W1[Worker 1]
    Q --> W2[Worker 2]
    Q --> W3[Worker 3]
    W1 -->|StepExecution result| RE[(Reply channel nếu cấu hình)]
    W2 -->|StepExecution result| RE
    W3 -->|StepExecution result| RE
    RE --> A[Aggregation / correlation]
    A --> M
    W1 --> JR[(JobRepository)]
    W2 --> JR
    W3 --> JR
    M <-->|Đối soát trạng thái| JR
~~~

Một số cấu hình Spring Batch Integration sử dụng **request/reply channels** để gửi các `StepExecution` trở về manager; một số có thể dùng cách theo dõi từ `JobRepository`. Cần biết chính xác **cơ chế manager step đã chọn**, không ghép đoạn code remote step polling với một aggregator reply không được tiêu thụ.

| Tiêu chí | `RemoteStep` (Spring Batch 6.x) | Remote partitioning |
|---|---|---|
| Số việc của một logical step | Một worker execution được giao xa | Nhiều worker `StepExecution`, một cho mỗi partition |
| Manager biết kết quả | **Poll `JobRepository`** | Reply aggregation hoặc cách theo dõi metadata được cấu hình |
| Handler worker có thể return | `StepExecution` | `StepExecution` |
| Có cần reply queue riêng? | **Không bắt buộc** | Có nếu chọn mô hình reply aggregation |
| Correlation quan trọng | Exact `stepExecutionId` và job/execution identity | Exact execution/partition và tập partition kỳ vọng |
| Sự cố response trễ/trùng | Xử lý qua metadata và dispatch/recovery policy | Aggregator phải xử lý trùng, thiếu và reply của lần chạy cũ |

**Không coi ba reply “COMPLETED” là đủ nếu manager đã tạo bốn partition.** Tập reply hợp lệ phải được đối chiếu với **tập `StepExecution` được tạo cho lần chạy đó**, không chỉ đếm số message.

## 5. Handler worker trả về gì?

Ở worker, `StepExecutionRequestHandler` là cầu nối giữa message adapter và lifecycle Spring Batch. Trong 6.x, nó có thể cấu hình với `JobRepository` và `StepLocator`, rồi gọi:

~~~java
StepExecution handle(StepExecutionRequest request);
~~~

Ý nghĩa logic:

1. **Nhận** request chứa tên step và định danh execution.
2. **Tìm** metadata `StepExecution` đã tồn tại trong repository.
3. **Định vị** bean `Step` theo tên, không tạo một JobInstance mới.
4. **Thực thi** step với context, transaction và checkpoint phù hợp.
5. **Trả về** `StepExecution` cho messaging flow sau khi lời gọi thực thi hoàn tất theo hợp đồng handler.

Một return object là thông tin **ở trong worker process**. Nếu muốn publish ra broker, cần khai báo **output channel/outbound adapter**, message converter, destination và error handling. Không có bước nào mặc nhiên khiến manager bên ngoài nhận được một Java return value chỉ vì nó được trả về từ method.

### Ví dụ handler ở worker — Spring Batch 6.x

~~~java
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.StepLocator;
import org.springframework.batch.integration.partition.BeanFactoryStepLocator;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkerHandlerConfiguration {

    @Bean
    public StepLocator workerStepLocator(BeanFactory beanFactory) {
        BeanFactoryStepLocator locator = new BeanFactoryStepLocator();
        locator.setBeanFactory(beanFactory);
        return locator;
    }

    @Bean
    public StepExecutionRequestHandler workerRequestHandler(
            JobRepository jobRepository, StepLocator workerStepLocator) {

        StepExecutionRequestHandler handler =
                new StepExecutionRequestHandler();
        handler.setJobRepository(jobRepository); // Spring Batch 6.x
        handler.setStepLocator(workerStepLocator);
        return handler;
    }
}
~~~

Trong Spring Batch **5.x**, một biến thể handler sử dụng `setJobExplorer(...)` và request thường chứa thêm `jobExecutionId`. Đừng ghép wire-serialized `StepExecutionRequest` của manager 5.x với handler 6.x khi chưa có chiến lược tương thích và kiểm thử.

### Inbound flow: không bắt buộc gửi kết quả ra broker

Giả sử manager đang sử dụng `RemoteStep` 6.x và polling metadata. Worker chỉ cần inbound adapter đưa request tới handler:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

// Trong cấu hình Spring Integration của worker:
@Bean
public IntegrationFlow remoteStepInbound(
        ConnectionFactory jmsConnectionFactory,
        StepExecutionRequestHandler workerRequestHandler) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(jmsConnectionFactory)
                    .destination("batch.remote.step.requests"))
            .handle(workerRequestHandler, "handle")
            .get();
}
~~~

Ví dụ chỉ minh họa **đường inbound** và cần adapter/converter/credentials/broker configuration đầy đủ. Framework xử lý return của `handle` tùy topology channel; nếu không có nhu cầu reply, đừng tạo một “reply queue” rồi chờ manager `RemoteStep` sử dụng nó mà không có code tương ứng. Phải kiểm thử với Spring Integration version và loại inbound adapter thực tế để xác định behavior khi handler trả response nhưng flow không có consumer kế tiếp.

### Khi thật sự cần reply channel

Nếu ứng dụng dùng remote partitioning request/reply, cấu hình flow nên có đường đi rõ ràng:

~~~text
request queue
  -> inbound adapter / converter
  -> StepExecutionRequestHandler.handle(request)
  -> StepExecution response
  -> outboundReplies message channel
  -> outbound adapter
  -> reply queue
  -> manager inbound reply adapter
  -> aggregator của partition manager
~~~

Đây là **sơ đồ wiring**, không phải lời khuyên tự serialize `StepExecution` thành JSON tùy ý rồi gửi cho manager. Spring Batch Integration có các builder và hợp đồng messaging theo phiên bản; khi tự định nghĩa serializer, phải giữ đủ thông tin mà aggregator cần, bảo đảm tin cậy của correlation và kiểm thử compatibility.

## 6. BatchStatus và ExitStatus: hai trục kết quả

`StepExecution` có cả **`BatchStatus`** và **`ExitStatus`**.

- **`BatchStatus`** phản ánh **lifecycle vận hành** của execution: đang bắt đầu, đang chạy, đã hoàn tất, thất bại, dừng, v.v.
- **`ExitStatus`** là kết quả dùng cho **flow decision** và diễn giải outcome. Nó có thể có exit code/description được custom hóa, không phải chỉ là bản sao của `BatchStatus`.

| `BatchStatus` | Cách hiểu cơ bản | Hành động của manager/operator |
|---|---|---|
| `STARTING` / `STARTED` | Execution đang được khởi tạo hoặc chạy | Tiếp tục theo dõi, kiểm tra progress nếu quá lâu |
| `STOPPING` | Đã yêu cầu dừng nhưng chưa kết thúc | Chờ trạng thái terminal hoặc điều tra worker |
| `COMPLETED` | Step đã hoàn tất theo lifecycle Spring Batch | Kiểm tra `ExitStatus` và điều kiện business trước khi công bố thành công ngoài hệ thống |
| `FAILED` | Step thất bại | Ghi nhận nguyên nhân, phân loại transient/permanent, xử lý restart theo chính sách |
| `STOPPED` | Step kết thúc ở trạng thái dừng | Chỉ resume khi đã bảo đảm worker cũ dừng và checkpoint hợp lệ |
| `ABANDONED` | Execution không nên restart theo quy ước batch | Điều tra trước khi tạo job mới hoặc thao tác phục hồi |
| `UNKNOWN` | Trạng thái không xác định | Không coi là success; đối soát metadata/side effect thủ công |

**Không đồng nhất `ExitStatus=COMPLETED` với mọi điều kiện business đã đạt**, và cũng không kiểm tra chỉ `BatchStatus` rồi bỏ qua exit code tùy chỉnh dùng để điều hướng flow. Ví dụ step kết thúc kỹ thuật với `BatchStatus.COMPLETED` nhưng `ExitStatus` có mã `COMPLETED_WITH_WARNINGS`: manager phải quyết định đó là success chấp nhận được hay yêu cầu bước rà soát.

### Tình huống output tồn tại nhưng execution FAILED

Worker có thể đã upload một báo cáo lên object storage, sau đó lỗi khi ghi một bước hậu xử lý. `BatchStatus` vẫn có thể là `FAILED`, nhưng output đã xuất hiện. Nếu manager gửi lại request mà không kiểm tra `reportKey` và checksum/version, hệ thống có thể tạo **bản báo cáo trùng** hoặc phát event hai lần.

Vì vậy, response handling có hai lớp quyết định:

1. **Lớp Spring Batch:** dùng status/exit status, metadata, checkpoint và lifecycle hợp lệ.
2. **Lớp nghiệp vụ:** dùng key bất biến, unique constraint, checksum, outbox và đối soát downstream.

## 7. Xử lý state transition mà không kết luận sớm

Không nên suy luận `STEP_FINISHED` chỉ từ “đã nhận một response” không định danh. Một bộ quan sát có thể phân loại status như sau (đây là **pseudocode**, không phải API polling của Spring Batch):

~~~java
// Pseudocode cho observer/dashboard ngoài batch framework.
// exactExecution là StepExecution vừa đọc từ JobRepository.
switch (exactExecution.getStatus()) {
    case COMPLETED -> {
        // Kiểm tra ExitStatus và điều kiện nghiệp vụ trước khi publish.
    }
    case FAILED, STOPPED, ABANDONED, UNKNOWN -> {
        // Ghi nhận nguyên nhân; dùng runbook/restart policy phù hợp.
    }
    case STARTING, STARTED, STOPPING -> {
        // Tiếp tục theo dõi với timeout, không tự coi là thất bại ngay.
    }
    default -> {
        // Không suy đoán; xác minh trạng thái mới/khác.
    }
}
~~~

Đây chỉ là mô hình phân loại để giải thích tư duy. **Không tự viết một polling loop và trực tiếp sửa trạng thái `StepExecution` trong DB** nếu đã dùng `RemoteStep` của Spring Batch: framework chịu trách nhiệm flow/lifecycle, còn custom observer chỉ giám sát, cảnh báo và hỗ trợ điều hành.

### Phải kiểm tra cả thời điểm và danh tính execution

Trong môi trường restart, một `JobInstance` có thể có nhiều `JobExecution`, và các `StepExecution` tương ứng không được giả định có cùng ID qua mọi lần thử. Nếu có một reply muộn từ execution cũ, **không được gán nó cho execution mới chỉ vì tên step giống nhau**.

Các trường correlation tối thiểu nên xem xét:

~~~text
jobName
jobInstanceId
jobExecutionId
stepExecutionId
stepName
partitionName (nếu remote partitioning)
attempt/restart identity (nếu dùng envelope tùy chỉnh)
requestMessageId hoặc correlationId do transport cung cấp
workerInstanceId (để log, không thay cho execution ID)
~~~

Với `RemoteStep` 6.x, `stepExecutionId` là định danh chính trong `StepExecutionRequest`. Các trường khác có thể tra trong repository và thêm vào log. **Không được dùng worker pod name làm khóa chính để map response**: pod có thể restart, bị thay thế hoặc nhận nhiều execution khác nhau.

## 8. Reply trễ, trùng, thất lạc hoặc sai correlation

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý đúng |
|---|---|---|
| Không nhận reply | Manager không cấu hình reply queue, adapter lỗi, broker mất message | Với `RemoteStep`: kiểm tra `JobRepository` polling; với request/reply: kiểm tra toàn bộ reply flow |
| Reply đến sau timeout | Worker chạy lâu, queue lag, manager ngắt kết nối | Đối chiếu **exact StepExecution** và job attempt; không gán status của attempt cũ cho attempt mới |
| Hai reply cùng một execution | Broker redelivery, publish retry, consumer trả lại | Dedupe theo execution identity; không tính hai reply là hai partition hoàn tất |
| Reply của step khác | Correlation routing sai hoặc queue dùng chung không cô lập | Reject/quarantine; kiểm tra stepName, job execution và authorization |
| Reply báo success nhưng DB báo `STARTED` | Message được tạo quá sớm, repository lag, transaction chưa commit | Không mark success từ message; đọc lại repository theo policy và điều tra |
| DB `COMPLETED` nhưng không có reply | Reply publish lỗi sau khi step commit | Với polling: có thể hoàn tất; với aggregator: cần reconciliation và recovery policy |
| Reply deserialize lỗi | Khác version/schema, object serialization không tương thích | DLQ có cảnh báo; sửa converter/contract, không retry vô hạn |
| Worker cũ vẫn chạy khi request bị phát lại | Mất ACK/connection; broker giao message cho consumer mới | Ngăn side effect trùng bằng idempotency, lease/fencing nếu cần, đối soát trạng thái |

**Dedupe message không đồng nghĩa ngăn chạy trùng hoàn toàn.** Nếu hai worker đang thực sự xử lý cùng một execution hoặc cùng khóa nghiệp vụ, việc bỏ reply trùng ở manager chỉ xử lý **triệu chứng giao nhận**, không sửa được tác động kép ở dữ liệu đích.

### Ví dụ reply envelope tùy chỉnh — chỉ dùng để quan sát

Ứng dụng có thể gửi thêm event vận hành để dashboard hoặc incident system theo dõi:

~~~json
{
  "eventType": "worker-step-finished",
  "jobExecutionId": 452,
  "stepExecutionId": 901,
  "stepName": "renderStatementWorker",
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED",
  "workerInstanceId": "worker-b7",
  "resultKey": "reports/2026-11-26/v1",
  "eventVersion": 1
}
~~~

Đây là **format minh họa của ứng dụng**, **không phải JSON wire protocol mặc định của Spring Batch** và không thay thế payload `StepExecution` mà remote partitioning aggregator yêu cầu. Message cần được xác thực, dùng schema/version ổn định và không chứa secret hoặc dữ liệu khách hàng nhạy cảm.

Nếu phải tiếp nhận event dạng này:

1. Verify schema/version và nguồn gửi.
2. Resolve `jobExecutionId`/`stepExecutionId` trong repository.
3. Bỏ event sai môi trường, sai job, sai step hoặc thuộc attempt cũ.
4. So sánh trạng thái trong repository; event là **gợi ý quan sát**, không được tùy ý overwrite metadata.
5. Ghi nhận duplicate theo key ổn định và TTL/retention phù hợp.
6. Chỉ publish kết quả nghiệp vụ khi mọi điều kiện nhất quán đã được xác minh.

## 9. Timeout: hết giờ chờ không đồng nghĩa worker đã thất bại

Trong một hệ thống phân tán, có ít nhất **bốn loại timeout**:

| Timeout | Nơi cấu hình | Nó cho biết điều gì? |
|---|---|---|
| **Send timeout** | Manager messaging template/outbound adapter | Gửi yêu cầu không hoàn tất trong khoảng chờ; chưa chắc worker chưa nhận |
| **Broker/consumer timeout hoặc lease** | Middleware/container/adapter | Hết thời gian giao nhận/ACK theo transport; có thể phát lại |
| **Remote step polling/overall timeout** | Manager `RemoteStep` | Manager không quan sát được hoàn tất đúng hạn; worker **có thể vẫn chạy** |
| **Transaction/API/DB timeout** | Worker step và dependency | Một thao tác nghiệp vụ hết thời gian, có thể rollback hoặc để lại side effect |

Đừng đặt tất cả timeout bằng một con số giống nhau. Một tasklet tạo báo cáo mất 20 phút có thể có send timeout tính bằng giây, worker deadline tính bằng hàng chục phút, polling interval vài giây và API call timeout ngắn hơn. Các con số là **ví dụ về lớp**, không phải giá trị mặc định phải dùng.

### Chọn polling interval

Polling quá dày làm tăng query tới metadata DB; polling quá thưa làm manager nhận biết hoàn tất chậm. Với `K` remote steps đang hoạt động và interval `I` giây, mức truy vấn lý thuyết của riêng thao tác poll xấp xỉ:

\[
R_{\mathrm{poll}} \approx \frac{K}{I}
\]

Nếu có `K=600` execution được poll mỗi `I=5` giây, có thể phát sinh khoảng **120 lượt kiểm tra trạng thái/giây**, chưa tính các query bổ sung, transaction và ứng dụng khác. Đây là ước lượng sơ bộ, không phải phép đo query count thực tế của framework.

Khi DB metadata đã nghẽn, cần xem `active/pending JDBC connections`, query latency, lock wait và số job đang chạy trước khi giảm interval hoặc tăng worker. Tăng replica worker không giải quyết bottleneck polling tại manager.

### Timeout escalation an toàn

Thay vì ngay lập tức gửi request mới, ưu tiên:

1. Lấy **exact `stepExecutionId`** và `jobExecutionId` mà manager đang đợi.
2. Đọc trạng thái, checkpoint và thời gian cập nhật metadata.
3. Đối chiếu queue pending/unacked/redelivery với worker log và output nghiệp vụ.
4. Nếu worker vẫn còn hoạt động, chưa re-dispatch cùng execution.
5. Nếu worker không còn hoạt động, xác định side effect đã commit và điều kiện restart.
6. Áp dụng chính sách restart/stop rõ ràng, có backoff và idempotency.

## 10. ACK và reply không có một transaction chung với business output

Giả sử worker xử lý một request, viết file rồi trả kết quả:

~~~text
T1: Broker giao request cho worker A
T2: Worker A ghi file vào object storage
T3: Worker A cập nhật StepExecution = COMPLETED
T4: Worker A mất kết nối trước khi ACK
T5: Broker redeliver request cho worker B
~~~

Ở `T5`, việc broker giao lại **không** có nghĩa file chưa tồn tại. Nếu `worker B` không kiểm tra metadata/tác động nghiệp vụ mà chạy lại, có thể ghi đè file hoặc phát event hai lần. Ngay cả khi handler tra `StepExecution`, vẫn có tình huống race nếu worker A thực sự còn chạy nhưng broker nghĩ nó đã chết.

Một trường hợp khác:

~~~text
T1: Worker A ghi business DB
T2: Worker A mất điện trước metadata checkpoint
T3: StepExecution chưa phản ánh đầy đủ side effect
T4: Job được restart và item được đọc lại
~~~

Không thể suy ra exactly-once chỉ từ `StepExecution` hay ACK. Cần dùng:

- **Khóa nghiệp vụ/idempotency key:** cùng `reportKey` hoặc transaction key dẫn tới một kết quả cuối.
- **Unique constraint/upsert/compare-and-set:** database từ chối hoặc xử lý an toàn bản ghi trùng.
- **Transactional outbox** nếu cần publish event sau khi dữ liệu DB commit.
- **Fencing token/lease** khi có nguy cơ hai worker thực hiện cùng tác vụ dài trên một tài nguyên.
- **Đối soát** giữa metadata, dữ liệu đích và trạng thái downstream khi có sự cố.

Đây là phần của thiết kế retry/restart, không phải một bước “bổ sung tùy chọn” sau khi scale lên nhiều worker.

## 11. Recovery theo từng trạng thái thực tế

| Metadata và bằng chứng | Việc nên làm trước tiên | Việc không nên làm |
|---|---|---|
| `COMPLETED`, output hợp lệ, không reply | Cho manager/cơ chế polling đối soát; với reply aggregator, điều tra đường reply và recovery | Gửi lại worker chỉ để có thêm một reply |
| `STARTED`, worker còn hoạt động | Theo dõi tiến độ, kiểm tra timeout/DB wait | Đánh dấu `FAILED` thủ công rồi dispatch song song |
| `STARTED`, pod đã chết | Kiểm tra transaction, checkpoint, output và quy trình restart hợp lệ | Giả định mọi side effect đã rollback |
| `FAILED`, lỗi transient rõ ràng | Phân loại retry/skip; restart cùng job instance khi an toàn | Tạo `run.id` mới để né trạng thái lỗi |
| `STOPPING` hoặc `STOPPED` | Xác minh drain/stop hoàn tất, cân nhắc resume theo lifecycle | Khởi chạy bản sao trong khi bản cũ có thể còn ghi |
| `UNKNOWN` hoặc metadata mâu thuẫn | Incident/reconciliation, kiểm tra DB/broker/business result | Tự overwrite status bằng SQL hoặc coi là success |
| Reply `COMPLETED` của attempt cũ | Bỏ/quarantine reply cũ, dựa vào metadata attempt hiện tại | Gán nó cho execution mới cùng `stepName` |

### Tại sao không sửa metadata trực tiếp?

`JobRepository` quản lý trạng thái và optimistic concurrency theo lifecycle Spring Batch. Thay `STATUS` hoặc `EXIT_CODE` trực tiếp trong bảng metadata để “tháo kẹt” có thể khiến framework nghĩ execution đã kết thúc trong khi worker còn chạy. Nếu phải can thiệp đặc biệt, cần runbook, backup, kiểm tra process đang active và quy trình vận hành được kiểm soát. **Mặc định không dùng SQL UPDATE metadata làm thao tác recovery.**

### Restart và identifying parameters

Một `JobInstance` được nhận diện bằng **job name + identifying `JobParameters`**. Restart sau lỗi nên dùng cùng identifying values theo API vận hành chính thức của Spring Batch; tự sinh `run.id` mới có thể tạo `JobInstance` khác và xử lý lại từ đầu.

Không giả định `stepExecutionId` của lần thử trước bằng với lần thử sau. Reply cũ phải gắn với chính execution đã sinh ra nó. Nếu đã có output nghiệp vụ từ lần thử cũ, worker mới cần kiểm tra idempotency trước khi ghi lại.

## 12. Điểm khác biệt giữa “response success” và hoàn tất cả job

Một job có thể có flow:

~~~mermaid
flowchart TD
    A[validateInput] --> B[renderRemoteStep]
    B --> C{BatchStatus / ExitStatus}
    C -->|Phù hợp| D[publishReport]
    C -->|Thất bại| E[Handle failure / incident]
    D --> F{Publish có idempotent?}
    F -->|Có| G[Job hoàn tất]
    F -->|Không| H[Nguy cơ publish hai lần khi restart]
~~~

`renderRemoteStep` báo `COMPLETED` chỉ là kết quả của một bước. `publishReport` vẫn có thể thất bại sau đó, khiến **JobExecution** không `COMPLETED`. Nếu job được restart, Spring Batch có thể bỏ qua step đã hoàn tất theo chính sách step nhưng cần chạy bước publish còn lỗi. Không đồng nhất **worker step success** với **job success**, cũng không đồng nhất **job success** với việc downstream đã nhận đủ side effect nếu không có bằng chứng nghiệp vụ.

### ExitStatus tùy chỉnh và flow transition

Một worker có thể kết thúc với exit code `COMPLETED_WITH_WARNINGS` hoặc `NO_DATA` theo quy ước ứng dụng. Manager flow phải có transition phù hợp nếu cần rẽ nhánh. Khi dùng `RemoteStep`, **không phát minh một cơ chế custom reply event rồi bỏ qua exit status đã lưu trong repository**.

Ví dụ logic thiết kế, không phải cú pháp cấu hình đầy đủ:

~~~text
Remote worker executes:
  BatchStatus = COMPLETED
  ExitStatus  = NO_DATA

Manager job policy:
  NO_DATA -> skip publish, record audit
  COMPLETED -> publish report
  FAILED -> stop and investigate/restart
~~~

Không tự động dùng một `ExitStatus` “tự đặt tên” nếu job flow/mapper không biết cách xử lý nó.

## 13. Thread safety, concurrency và số lượng response

Giả sử manager có 1 `RemoteStep` đang chạy, broker có 8 worker pod. Mặc dù 8 pod có thể nhận message từ một queue, một step execution **không tự phân thành 8 phần**. Một request được một consumer xử lý theo delivery semantics của broker; số reply hợp lệ cho execution đó không được kỳ vọng bằng 8.

Ngược lại, với remote partitioning có `P=32` partition và 4 worker pod mỗi pod xử lý an toàn 2 execution, trần scheduling là:

\[
C_{\mathrm{active}} \le \min(P, N\times L)
=\min(32,4\times 2)=8
\]

Manager cần **32 kết quả partition hợp lệ** (hoặc cơ chế đối soát tương ứng), không chỉ 8 response đang active cùng lúc.

### Lưu ý về Step và bean scope

- Một instance `Step` có lifecycle và không mặc nhiên an toàn khi nhiều `StepExecution` gọi đồng thời. Nếu muốn mỗi worker process nhận nhiều execution, cần cách ly instance/đánh giá contract theo phiên bản và test thực tế.
- Reader có cursor dùng `@StepScope` để tạo target theo `StepExecution` trong partitioning; scope không tự biến reader thành thread-safe khi một execution được nhiều thread chia sẻ.
- Stateless processor/writer có thể dùng singleton nếu các dependency của chúng cũng an toàn.
- `JobRepository` và connection pool được dùng chung giữa execution nhưng phải đo lock/connection wait; không tăng concurrency chỉ vì queue có nhiều message.

### Backpressure và queue lag

Worker càng nhiều, tốc độ trả response có thể tăng; nhưng metadata DB có thể trở thành nút thắt vì mỗi worker ghi `StepExecution`/checkpoint và manager polling. Theo dõi queue depth, unacked, worker active, DB pool pending, transaction latency và độ trễ tổng hợp.

Nếu worker xử lý nhanh nhưng reply queue tích tụ, lỗi có thể nằm ở **aggregator/manager consumer** chứ không phải logic worker. Nếu `RemoteStep` polling repository, reply queue không dùng đến có thể chỉ là cấu hình thừa gây khó hiểu. Cần biết chính xác kiến trúc để đo đúng chỗ.

## 14. Observability: response nào thuộc execution nào?

Không thể vận hành remote worker chỉ với log “done successfully”. Ít nhất mỗi log/span/metric liên quan nên có:

~~~text
jobName
jobExecutionId
stepExecutionId
stepName
partitionName (nếu có)
workerInstanceId
requestMessageId / correlationId (nếu broker cung cấp)
attempt / restart identity
batchStatus, exitCode
elapsedMs
businessResultKey đã ẩn thông tin nhạy cảm
~~~

| Lớp quan sát | Metrics/log quan trọng | Gợi ý chẩn đoán |
|---|---|---|
| Manager `RemoteStep` | Poll count, poll latency, timeout, elapsed time | DB metadata chậm hay worker chưa xong? |
| Worker handler | Request received, step lookup errors, handle duration | Sai stepName hoặc execution ID? |
| Worker step | `readCount`, `writeCount`, commit/rollback, exit code, checkpoint | Worker đã xử lý đúng chưa? |
| Request broker | Pending/unacked, redelivery, DLQ, oldest age | Request chưa tới worker hay bị giao lại? |
| Reply broker (nếu dùng) | Pending, duplicate, reply age, consumer count | Manager/aggregator có nhận và đối soát đủ reply? |
| Metadata DB | JDBC pool pending, query/commit latency, lock wait | Polling/metadata contention? |
| Nghiệp vụ | Số file/row kỳ vọng, key trùng/thiếu, checksum, publish status | Job success có tương ứng dữ liệu đúng? |
| Container/JVM | CPU/GC, heap, pod restarts, readiness, graceful shutdown | Worker bị kill hoặc nghẽn tài nguyên? |

### Query chẩn đoán chỉ đọc

Với metadata schema JDBC phổ biến, có thể tìm execution trong bảng tương ứng (tên và cột tùy phiên bản/table prefix):

~~~sql
SELECT STEP_EXECUTION_ID,
       JOB_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       EXIT_CODE,
       READ_COUNT,
       WRITE_COUNT,
       START_TIME,
       END_TIME
FROM BATCH_STEP_EXECUTION
WHERE STEP_EXECUTION_ID = :stepExecutionId;
~~~

Đây chỉ là query **đọc phục vụ vận hành**, không nên trở thành API quản lý lifecycle chính. Ứng dụng nên dùng `JobRepository`/`JobExplorer`/`JobOperator` tương ứng với phiên bản để thao tác batch. Không dùng SQL `UPDATE BATCH_STEP_EXECUTION` trong flow nhận reply.

## 15. Mô hình xử lý sự cố: một runbook thống nhất

### Kịch bản A — Worker hoàn tất, manager không có reply

1. Xác định hệ thống đang dùng **`RemoteStep` polling** hay **remote partitioning reply aggregation**.
2. Tra `stepExecutionId` trong metadata DB. Nếu đã `COMPLETED`, kiểm tra exit status và output nghiệp vụ.
3. Nếu là `RemoteStep` polling, xem manager còn sống, đang trỏ đúng DB và đang poll đúng execution hay không; **không bắt buộc phải có reply**.
4. Nếu là reply aggregation, kiểm tra outbound adapter worker, reply queue, inbound adapter manager và correlation.
5. Không gửi lại cùng việc chỉ để có một reply mới trước khi bảo đảm không gây side effect trùng.

### Kịch bản B — Manager timeout, worker vẫn đang chạy

1. Xác minh worker instance còn sống và đang xử lý `stepExecutionId` đó.
2. Xem long-running SQL, API, file I/O và checkpoint latency.
3. Nếu có giới hạn deadline, stop/drain theo policy; không tạo manager mới điều phối cùng execution trong lúc worker cũ chưa dừng.
4. Sau khi biết trạng thái cuối, quyết định retry/restart; đối soát các output đã ghi.

### Kịch bản C — Hai reply cùng `stepExecutionId`

1. Kiểm tra redelivery/retry trong broker, so sánh request/reply message IDs.
2. Dedupe response theo **execution identity**, không theo worker pod hay timestamp.
3. Nếu metadata và output hợp lệ, duplicate reply có thể được bỏ qua ở tầng observation/aggregation phù hợp.
4. Nếu phát hiện hai worker đã cùng chạy một execution, đây là sự cố **concurrent duplicate processing**, phải đối soát business data và bổ sung fencing/idempotency.

### Kịch bản D — Reply của lần chạy cũ đến sau restart

1. So sánh `jobExecutionId`/`stepExecutionId` của reply với execution hiện tại.
2. Bỏ hoặc quarantine stale reply, không cộng vào tập kết quả mới.
3. Đối soát output của attempt cũ trước khi worker mới xử lý, đặc biệt với side effect ngoài transaction.
4. Kiểm tra chính sách giữ message cũ trong queue, correlation và cleanup group của aggregator.

### Kịch bản E — Worker báo FAILED nhưng đã ghi một phần dữ liệu

1. Xác định chunk nào đã commit và side effect ngoài transaction nào đã xảy ra.
2. Đối chiếu `ExecutionContext`, checkpoint và dữ liệu đích.
3. Khắc phục lỗi gốc (input, DB, quota, network).
4. Restart đúng `JobInstance` với input/cutoff bất biến, writer idempotent.
5. Đối soát tập khóa nghiệp vụ sau phục hồi, không chỉ tổng read/write count.

## 16. Kiểm thử response handling theo fault injection

| Test | Cách gây lỗi | Điều kiện đạt |
|---|---|---|
| **Happy path** | Gửi một request hợp lệ, worker hoàn tất | Metadata đúng status/exit, manager tiếp tục flow |
| **Không có reply queue** | Chạy `RemoteStep` với polling và worker inbound | Manager vẫn hoàn tất khi metadata chính xác |
| **Worker crash trước commit** | Kill process trong chunk | Transaction rollback/checkpoint phù hợp, restart an toàn |
| **Worker crash sau commit trước ACK** | Kill trước ACK | Broker redelivery không gây tác động nghiệp vụ trùng |
| **Reply thất lạc** | Chặn outbound reply với mô hình request/reply | Manager phát hiện thiếu và có quy trình đối soát |
| **Reply trễ** | Delay reply sau restart/timeout | Không gán reply cũ cho execution mới |
| **Reply trùng** | Publish hai response cho cùng execution | Aggregator không đếm đôi; dữ liệu vẫn đúng |
| **Sai correlation** | Đổi stepExecutionId/jobExecutionId | Reply bị từ chối/quarantine |
| **Metadata DB tạm lỗi** | Ngắt kết nối manager/worker | Timeout/recovery rõ; không tự kết luận thành công |
| **Worker chạy rất lâu** | Cố ý sleep/call slow API | Có progress metric, timeout và runbook đúng |
| **Custom ExitStatus** | Worker trả `NO_DATA` hoặc warning | Job flow quyết định đúng theo mapping |
| **Nhiều partition** | Tạo N partition, một partition FAILED | Manager tổng hợp đúng N execution, không chỉ đếm số message |
| **Mất manager** | Kill manager khi worker vẫn hoạt động | Không có hai manager cùng dispatch execution; khôi phục/đối soát |

Nên chạy integration test bằng **hai process/container thực**, broker và metadata DB riêng biệt khỏi dữ liệu nghiệp vụ. Unit test gọi trực tiếp `handler.handle(request)` không mô phỏng được mất ACK, redelivery hoặc manager polling timeout.

## 17. Checklist trước production

- [ ] Đã xác định đang dùng `RemoteStep` 6.x **polling** hay remote partitioning **reply aggregation**.
- [ ] `StepExecutionRequestHandler` và message converter tương thích Spring Batch/Spring Integration version.
- [ ] Manager/worker trỏ tới **cùng metadata DB/schema**.
- [ ] Worker `StepLocator` tìm đúng `stepName` từ request.
- [ ] `StepExecution` status và exit status được đánh giá độc lập; có mapping business outcome rõ.
- [ ] Không dùng ACK hoặc reply message như bằng chứng duy nhất để đánh dấu job thành công.
- [ ] Reply (nếu có) được correlated theo **exact execution identity**, không dùng tên pod.
- [ ] Reply trùng/trễ/cũ không được đếm hoặc gán sai sau restart.
- [ ] Timeout từng lớp được cấu hình và có runbook đối soát trước re-dispatch.
- [ ] Writer/side effect idempotent; khi cần có outbox, deduplication, lease/fencing.
- [ ] Reader restartable, checkpoint và input/snapshot ổn định cho cùng job instance.
- [ ] Không có mutable singleton state không an toàn khi tăng concurrency.
- [ ] Đã đo queue lag, DB pool pending, polling latency, rollback và partition skew.
- [ ] Có log/metric/cảnh báo theo jobExecutionId/stepExecutionId, không rò secret.
- [ ] Đã thử worker crash, manager crash, DB outage và duplicate response.

## 18. Bài tập thực hành

### Bài 1 — Vẽ luồng không reply

Dựng sơ đồ `RemoteStep` manager và worker với `StepExecutionRequestHandler`. Đánh dấu đường request qua broker, đường worker ghi trạng thái vào `JobRepository` và đường manager polling. Giải thích vì sao return từ `handle(...)` chưa phải một reply đã giao qua mạng.

### Bài 2 — Phân loại ba kết quả khác nhau

Giả sử worker tạo PDF thành công, metadata còn `STARTED` và broker đã ACK message. Kết luận nào manager có thể đưa ra ngay? Đề xuất bước điều tra tiếp theo và cơ chế idempotency để xử lý khi metadata không được cập nhật.

### Bài 3 — Ứng dụng với reply aggregation

Manager tạo 12 partition; sau một đợt xử lý nhận 11 reply `COMPLETED`, một reply bị trễ và một trong 11 reply bị gửi lặp. Thiết kế cách đối chiếu reply với **12 `StepExecution` kỳ vọng**, không nhầm số message với số partition. Thêm kịch bản reply cũ đến sau restart.

### Bài 4 — Tính tải polling

Có 240 `RemoteStep` đang được manager theo dõi, poll mỗi 3 giây. Ước lượng số lượt poll/giây, sau đó xem điều gì xảy ra khi giảm interval còn 1 giây. Mô tả metric DB phải đo trước khi thay đổi.

### Bài 5 — Fault injection sau commit

Cho worker ghi một bản ghi nghiệp vụ với business key cố định, cập nhật metadata, rồi mất ACK. Broker giao lại request; thiết kế idempotency ở DB và chính sách phân biệt duplicate delivery với execution mới. Kiểm tra cả trường hợp worker cũ chưa thực sự dừng.

### Bài 6 — Lập runbook theo trạng thái

Viết quy trình xử lý cho bốn trường hợp: `COMPLETED` nhưng không có reply; `STARTED` và worker còn sống; `FAILED` sau vài chunk commit; `UNKNOWN` vì metadata DB mất kết nối. Mỗi trường hợp nêu rõ dữ liệu cần kiểm tra và hành động nguy hiểm cần tránh.

**Câu hỏi tự kiểm tra:** Vì sao `RemoteStep` không bắt buộc reply queue? `StepExecutionRequestHandler.handle` trả gì và điều đó có phải một broker message không? `BatchStatus` khác `ExitStatus` thế nào? Tại sao reply `COMPLETED` của attempt trước không thể dùng cho execution mới? Vì sao ACK rồi mà output vẫn có thể chưa nhất quán? Khi nào phải chuyển từ kiểm tra status sang đối soát nghiệp vụ?

## 19. Tổng kết

Xử lý **response của remote worker** trong Spring Batch không phải chỉ là nhận một message có chữ “success”. Cần phân biệt **return của `StepExecutionRequestHandler`, reply/ACK ở middleware, metadata `StepExecution` và tác động nghiệp vụ**. Trong **`RemoteStep` của Spring Batch 6.x**, manager có thể xác định kết quả bằng **polling `JobRepository`** mà không cần reply queue riêng; còn remote partitioning có thể dùng **reply aggregation** để tổng hợp nhiều partition execution.

Thiết kế vận hành bền vững phải gắn kết **correlation chính xác, xử lý reply trễ/trùng/thất lạc, timeout có giới hạn, restart cùng job instance, idempotency và quan sát tài nguyên thực tế**. Chỉ khi metadata, workflow và dữ liệu nghiệp vụ nhất quán, hệ thống mới có căn cứ chắc chắn để công bố một remote step đã thành công.
