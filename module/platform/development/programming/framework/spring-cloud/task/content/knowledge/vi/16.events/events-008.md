# Thứ tự listener phát sự kiện

Trong một ứng dụng **Spring Cloud Task** chạy hữu hạn, Spring Cloud Task ghi vòng đời tiến trình vào **TaskRepository**; nếu chạy **Spring Batch**, Batch còn ghi `JobExecution`, `StepExecution` và checkpoint vào **JobRepository**. Khi tích hợp **Spring Cloud Stream**, ứng dụng có thể phát các sự kiện từ listener của Task và Batch để các dịch vụ giám sát hoặc điều phối theo dõi tiến độ.

Một câu hỏi thường gặp là: *nếu trong cùng Job có listener nghiệp vụ và listener phát sự kiện, listener nào được gọi trước?* Spring Cloud Task hỗ trợ các thuộc tính **`spring.cloud.task.batch.events.*-order`** để điều chỉnh ưu tiên của những **Batch event listener** được tự cấu hình. Hiểu sai tham số này dễ dẫn đến giả định không đúng rằng mọi message đến broker theo đúng thứ tự, hoặc cho rằng thay `order` có thể đảo trình tự xử lý Job và Step.

Bài thuộc chương **Sự kiện** và giải thích ba loại thứ tự khác nhau, cấu hình của từng listener, quan hệ với lifecycle Task, ví dụ `Ordered` trong Spring Batch, cách quan sát thứ tự thực thi và giới hạn của delivery qua broker. Từ đó người học biết chọn độ ưu tiên khi một listener cần cập nhật kết quả trước khi listener khác phát sự kiện, đồng thời vẫn đảm bảo tác vụ kết thúc an toàn.

## 1. Ba khái niệm “thứ tự” cần phân biệt

| Loại thứ tự | Câu hỏi trả lời | Ai quyết định? |
| --- | --- | --- |
| **Thứ tự lifecycle** | `beforeJob`, `beforeStep`, `beforeChunk`, item, `afterStep`, `afterJob` xảy ra khi nào? | Luồng thực thi Spring Batch và các Step |
| **Thứ tự ưu tiên listener** | Khi **nhiều listener cùng nhận một callback**, listener nào xử lý trước? | Cơ chế `Ordered`/composite listener và thuộc tính `*-order` |
| **Thứ tự message đến consumer** | Dịch vụ nhận có thấy các message theo đúng thứ tự gửi không? | Broker, partition/queue, producer, consumer, retry và topology |

**Trọng tâm của `spring.cloud.task.batch.events.*-order` là loại thứ hai.** Thuộc tính này không làm Step chạy trước Job, không sắp xếp các bản ghi nghiệp vụ và không đảm bảo consumer xử lý các message trên nhiều channel theo một thứ tự toàn cục.

Ví dụ, một lần chạy báo cáo có thể tạo chuỗi callback tại phía producer như sau:

~~~text
Task bắt đầu
  └─ Batch Job bắt đầu
       ├─ beforeJob
       ├─ Step A
       │    ├─ beforeStep
       │    ├─ beforeChunk
       │    ├─ item read / process / write
       │    ├─ afterChunk
       │    └─ afterStep
       ├─ Step B ...
       └─ afterJob
Task kết thúc
~~~

Chuỗi trên minh họa **một Job tuần tự, một chunk thành công**. Trong Job có Step song song, retry, skip, rollback hoặc item lỗi, callback sẽ nhiều hơn hoặc xen kẽ; không được suy ra luôn tồn tại một timeline tuyến tính duy nhất.

## 2. Listener nào có thể phát sự kiện?

Theo tài liệu Spring Cloud Task, khi có tích hợp Spring Cloud Stream thích hợp, Spring Cloud Task có thể tự cấu hình listener phát sự kiện từ nhiều mức Batch:

| Batch listener | Kênh sự kiện được tài liệu mô tả | Ví dụ nội dung quan sát |
| --- | --- | --- |
| `JobExecutionListener` | `job-execution-events` | Job bắt đầu/kết thúc và `JobExecution` |
| `StepExecutionListener` | `step-execution-events` | Step bắt đầu/kết thúc và `StepExecution` |
| `ChunkListener` | `chunk-events` | Bắt đầu/hoàn tất/lỗi chunk |
| `ItemReadListener` | `item-read-events` | Trước/sau đọc item hoặc lỗi đọc |
| `ItemProcessListener` | `item-process-events` | Trước/sau xử lý item hoặc lỗi xử lý |
| `ItemWriteListener` | `item-write-events` | Trước/sau ghi chunk hoặc lỗi ghi |
| `SkipListener` | `skip-events` | Bản ghi được skip theo chính sách của Step |

**Batch event listener** khác với **TaskExecutionListener**. Ở tầng Task, Spring Cloud Task có các callback `onTaskStartup`, `onTaskFailed` và `onTaskEnd`, cùng cơ chế phát sự kiện Task trên channel `task-events`. Ở tầng Batch, listener được gọi theo vòng đời `Job`, `Step`, `Chunk`, `Item`.

Một ứng dụng chỉ có `ApplicationRunner` xử lý một thao tác đơn giản có thể phát Task events nhưng **không có Batch events**, vì không chạy Spring Batch Job. Ngược lại, nếu một Job có hàng triệu item và bật cả `ItemReadListener` lẫn `ItemProcessListener`, lượng sự kiện có thể rất lớn.

### Điều kiện để có event trên broker

Cần phân biệt **callback được gọi trong JVM** với **message được gửi ra bên ngoài**. Với cơ chế tích hợp được tài liệu mô tả, phải có Spring Cloud Task, Spring Batch nếu cần Batch events, Spring Cloud Stream và một **binder phù hợp** (ví dụ RabbitMQ hoặc Kafka), cùng cấu hình channel/binding của phiên bản đang chạy.

~~~mermaid
flowchart LR
    S["Spring Cloud Task process"] --> T["TaskExecutionListener"]
    S --> J["Spring Batch Job / Step / Chunk"]
    J --> L["Batch listeners"]
    T --> O["Task event publisher"]
    L --> B["Batch event publishers"]
    O --> C[("Spring Cloud Stream binder")]
    B --> C
    C --> M[("Broker destinations")]
    M --> U["Consumer giám sát / điều phối"]
    S --> R[("TaskRepository")]
    J --> Q[("JobRepository")]
~~~

Các trạng thái được lưu trong repository và những message phát ra broker là **hai luồng dữ liệu khác nhau**. Có thể có bản ghi `TaskExecution`/`JobExecution` hoàn tất nhưng event bị thất lạc hoặc consumer chưa đọc được.

## 3. Mặc định của thứ tự phát Batch event

Tài liệu Spring Cloud Task quy định: **listener phát Batch events mặc định dùng `Ordered.LOWEST_PRECEDENCE`**.

Trong Spring Framework, `Ordered` dùng số nguyên để biểu diễn ưu tiên:

- **Số nhỏ hơn** biểu diễn ưu tiên **cao hơn**.
- `Ordered.HIGHEST_PRECEDENCE` là đầu ưu tiên (giá trị số nguyên nhỏ nhất).
- `Ordered.LOWEST_PRECEDENCE` là cuối ưu tiên (giá trị số nguyên lớn nhất).

Ví dụ có hai `JobExecutionListener` được đăng ký trong cùng composite:

~~~text
Listener nghiệp vụ: getOrder() = 10
Listener phát event: order = LOWEST_PRECEDENCE

beforeJob:
    listener nghiệp vụ chạy trước
    listener phát event chạy sau

afterJob:
    trong CompositeJobExecutionListener, lượt gọi đảo thứ tự
    listener phát event chạy trước
    listener nghiệp vụ chạy sau
~~~

**Điểm đáng chú ý:** Spring Batch **`CompositeJobExecutionListener`** gọi listener theo thứ tự ưu tiên ở `beforeJob`, rồi **đảo thứ tự** ở `afterJob`. Với `CompositeStepExecutionListener`, `beforeStep` và `afterStep` cũng có cách gọi tương ứng. Đây là lý do không thể chỉ nhìn số `order` rồi kết luận event sẽ được phát “trước” hoặc “sau” mọi callback trong cả hai pha.

Với `ChunkListener`, item listeners hoặc triển khai Batch ở phiên bản khác, cần xác minh cơ chế đăng ký, sắp xếp và thời điểm callback cụ thể. Không lấy quy tắc đảo thứ tự của `afterJob` áp đặt cho mọi callback hay mọi middleware.

## 4. Các thuộc tính điều chỉnh thứ tự

Spring Cloud Task cung cấp **bảy thuộc tính** cho thứ tự listener phát Batch events:

~~~properties
spring.cloud.task.batch.events.job-execution-order=5
spring.cloud.task.batch.events.step-execution-order=5
spring.cloud.task.batch.events.chunk-order=5
spring.cloud.task.batch.events.item-read-order=5
spring.cloud.task.batch.events.item-process-order=5
spring.cloud.task.batch.events.item-write-order=5
spring.cloud.task.batch.events.skip-order=5
~~~

Các giá trị `5` chỉ là **ví dụ**, không phải khuyến nghị cho mọi ứng dụng.

| Thuộc tính sau tiền tố `spring.cloud.task.batch.events.` | Áp dụng cho listener |
| --- | --- |
| `job-execution-order` | Listener phát `JobExecution` events |
| `step-execution-order` | Listener phát `StepExecution` events |
| `chunk-order` | Listener phát `Chunk` events |
| `item-read-order` | Listener phát `ItemRead` events |
| `item-process-order` | Listener phát `ItemProcess` events |
| `item-write-order` | Listener phát `ItemWrite` events |
| `skip-order` | Listener phát `Skip` events |

Đặt `job-execution-order=5` nghĩa là thay ưu tiên listener phát JobExecution event **so với những JobExecutionListener khác trong cùng cơ chế đăng ký**. Nó **không** bảo đảm Job event luôn tới broker trước mọi Step event; thời điểm phát theo lifecycle vẫn là trách nhiệm của Job/Step, và transport có quy tắc giao hàng riêng.

### 4.1. Ví dụ YAML

~~~yaml
spring:
  application:
    name: orders-import-task
  main:
    web-application-type: none
  cloud:
    task:
      batch:
        events:
          enabled: true
          job-execution-order: 5
          step-execution-order: 5
          chunk-order: 100
          item-read-order: 200
          item-process-order: 200
          item-write-order: 200
          skip-order: 50
~~~

Đây là YAML minh họa các **giá trị cấu hình ưu tiên**. Để sự kiện được phát thực sự, ứng dụng vẫn cần các dependency Batch/Task/Stream, binder, binding và listener được auto-configure đúng theo phiên bản. Không nên suy luận việc đặt `enabled: true` sẽ tự tạo broker hoặc endpoint consumer.

Cũng không nên đọc bảng trên như một thứ tự `job (5) → step (5) → skip (50) → chunk (100) → item (200)`. Mỗi listener thuộc **một loại callback khác nhau**: so sánh `order` của các loại listener không đồng nghĩa sắp xếp một hàng đợi toàn cục.

### 4.2. Nên để mặc định khi nào?

Giữ `Ordered.LOWEST_PRECEDENCE` thường đủ khi sự kiện chỉ phục vụ log/giám sát, các listener nghiệp vụ hoàn tất xử lý trước khi rời callback và không có nhu cầu đặc biệt về thứ tự. Chỉ đổi `*-order` khi:

1. Có **listener nghiệp vụ cụ thể** cần chạy trước hoặc sau listener phát event ở **cùng pha callback**.
2. Đã xác định phiên bản Batch thực sự dùng `Ordered` ở composite/registry tương ứng.
3. Có test xác nhận event chứa trạng thái mong muốn và không phát trước khi kết quả được xác nhận theo quy trình nghiệp vụ.

Tránh chỉnh tất cả bảy thuộc tính chỉ vì một Job event cần thay thứ tự. Càng nhiều callback bị can thiệp, càng khó giải thích một lần chạy có lỗi.

## 5. Ví dụ: listener nghiệp vụ và listener phát JobExecution event

Giả sử `dailyReportJob` cần gửi một event tổng kết cuối Job. Một listener nghiệp vụ sẽ bổ sung `ExitStatus` hoặc ghi thông tin đối soát trước khi event tổng kết được tạo.

Ta viết listener nghiệp vụ với `Ordered`:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ReportAuditListener
        implements JobExecutionListener, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        System.out.printf("AUDIT beforeJob: jobExecutionId=%s%n",
                execution.getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        System.out.printf("AUDIT afterJob: status=%s%n",
                execution.getStatus());
        // Nếu cần đối soát, đặt logic ở tầng đã có dữ liệu và
        // biết rõ transaction/commit boundary.
    }
}
~~~

Để listener này tham gia, Job phải đăng ký nó qua cấu hình Job hoặc cơ chế tương ứng của phiên bản:

~~~java
@Bean
Job dailyReportJob(
        JobRepository jobRepository,
        @Qualifier("reportStep") Step reportStep,
        ReportAuditListener reportAuditListener) {

    return new JobBuilder("dailyReportJob", jobRepository)
            .listener(reportAuditListener)
            .start(reportStep)
            .build();
}
~~~

Đoạn trên dùng phong cách API **Spring Batch 5.x**. Các bean `reportStep`, `JobRepository` và hạ tầng tích hợp Task–Batch/Stream phải được cung cấp trong một dự án hoàn chỉnh. Đăng ký listener nghiệp vụ không tự đăng ký listener phát event; listener phát event đến từ auto-configuration tương ứng.

Bây giờ xét hai phương án **khi cả hai listener cùng nằm trong `CompositeJobExecutionListener` có áp dụng `Ordered`**:

| `ReportAuditListener` | Listener phát event | `beforeJob` | `afterJob` |
| --- | --- | --- | --- |
| `10` | `Ordered.LOWEST_PRECEDENCE` | Audit → Publish | Publish → Audit |
| `10` | `5` | Publish → Audit | Audit → Publish |

Nếu muốn **callback `afterJob` của Audit chạy trước callback phát event**, cấu hình `job-execution-order=5` là cách hợp lý trong mô hình composite này. Nhưng hệ quả là **pha `beforeJob` sẽ phát event trước Audit**. Đổi thứ tự có thể giải quyết một mục tiêu ở pha `after*` và làm thay đổi hành vi ở pha `before*`; luôn đánh giá cả hai.

Tuy nhiên, **thứ tự callback không phải bảo đảm event sẽ chứa mọi thay đổi đã commit**: nếu listener Audit còn ghi transaction khác hoặc gửi công việc bất đồng bộ, thông tin có thể chưa sẵn sàng khi publisher hoạt động. Với sự kiện là tín hiệu quan trọng cho nghiệp vụ khác, cần thiết kế bằng chứng đã hoàn tất và đảm bảo phát có thể phục hồi.

### 5.1. Cấu hình thử nghiệm

~~~properties
spring.cloud.task.batch.events.job-execution-order=5
~~~

Khi có `ReportAuditListener` thứ tự `10`, dự kiến ở composite được mô tả:

~~~text
beforeJob:
  PUBLISHER_JOB_EVENT (order=5)
  AUDIT_BEFORE_JOB    (order=10)

afterJob:
  AUDIT_AFTER_JOB     (order=10)
  PUBLISHER_JOB_EVENT (order=5)
~~~

Đây là **dự kiến về lời gọi callback trong JVM**, không phải một log có sẵn được Spring Cloud Task tự in ra, và cũng không dự báo thứ tự consumer sẽ nhìn thấy message trên broker. Phải xác nhận thông qua log/instrumentation của ứng dụng và phiên bản thực tế.

## 6. Thứ tự theo lifecycle Batch vẫn được giữ nguyên

Dù cấu hình thứ tự listener là `5`, `100` hoặc mặc định, callback chỉ có thể được gọi khi Batch đi tới **điểm lifecycle tương ứng**.

### 6.1. Job, Step và Chunk

~~~mermaid
sequenceDiagram
    participant L as JobLauncher
    participant J as JobExecutionListeners
    participant S as StepExecutionListeners
    participant C as Chunk/Item listeners
    participant R as JobRepository

    L->>J: beforeJob
    J->>S: beforeStep
    S->>C: beforeChunk
    loop Item trong chunk
        C->>C: beforeRead / afterRead
        C->>C: beforeProcess / afterProcess
        C->>C: beforeWrite / afterWrite (theo chunk)
    end
    C->>C: afterChunk hoặc afterChunkError
    C->>S: afterStep
    S->>J: afterJob
    J->>R: hoàn tất Job metadata
~~~

Sơ đồ cho thấy một Job/Step chunk-oriented đơn giản; `beforeWrite` và `afterWrite` thường gọi theo **nhóm item/chunk**, không nhất thiết gọi một lần trên mỗi item. Trên lỗi có rollback, Spring Batch có thể lặp lại một số lần đọc/xử lý/ghi, vì vậy số callback không phải luôn đúng bằng số dòng nghiệp vụ duy nhất.

**Không dùng `item-read-order=1` để “cho ItemRead xảy ra trước JobExecution event”**. Nó chỉ đổi vị trí listener phát item-read **giữa các ItemReadListener của cùng callback**, nếu cơ chế listeners có áp dụng ưu tiên đó.

### 6.2. Đăng ký nhiều listener trong cùng loại

Spring Batch có các composite listener để điều phối nhiều callback. Với `CompositeStepExecutionListener` và `CompositeJobExecutionListener`, tài liệu API mô tả rõ **before gọi theo thứ tự ưu tiên, after gọi theo thứ tự ngược**.

Nếu hai listener có **cùng order**, hoặc nếu listener được đăng ký qua những cơ chế không cùng composite, không nên dựa vào thứ tự tình cờ do thứ tự scan bean hay tên class. Khi thứ tự thực sự quan trọng, đặt số order khác biệt, đăng ký rõ ràng và viết test theo hành vi mong muốn.

`@Order` trong Spring có thể ảnh hưởng cách một số danh sách bean được sắp xếp, nhưng đối với listener được điều phối bằng giao diện **`Ordered`**, cung cấp `getOrder()` trực tiếp làm ý nghĩa ưu tiên rõ ràng hơn. Không suy đoán rằng `@Order` trên mọi bean tự động điều khiển các adapter Batch sự kiện.

## 7. Phân biệt với TaskExecutionListener và Task events

Ở tầng Spring Cloud Task, ba callback có thứ tự vòng đời:

~~~text
Thành công:
  onTaskStartup → ApplicationRunner/Batch Job → onTaskEnd

Thất bại chưa xử lý:
  onTaskStartup → ApplicationRunner/Batch Job lỗi
                → onTaskFailed → onTaskEnd
~~~

Tài liệu Task mô tả:

- `onTaskStartup`/`@BeforeTask` chạy ở giai đoạn bắt đầu, trước khi repository ghi trạng thái khởi chạy.
- `onTaskFailed`/`@FailedTask` chạy khi có exception chưa được xử lý, **trước `onTaskEnd`**.
- `onTaskEnd`/`@AfterTask` chạy trước khi repository cập nhật trạng thái kết thúc.

Trong các phiên bản triển khai, thứ tự thao tác tạo `TaskExecution` và callback startup có thể cần đối chiếu implementation; điều quan trọng với người viết Task là callback startup xảy ra trước runner, còn callback end xảy ra trước trạng thái kết thúc cuối. Một tiến trình bị kill bất thường có thể **không có** callback end.

### 7.1. Thứ tự ưu tiên của exitMessage là chuyện khác

Nếu các callback Task cùng đặt `exitMessage`, Spring Cloud Task quy định thứ tự ưu tiên lưu thông điệp:

~~~text
onTaskEnd  >  onTaskFailed  >  onTaskStartup
~~~

Nghĩa là thông điệp do `onTaskEnd` đặt có thể ghi đè thông điệp thất bại trước đó. **Đây là ưu tiên của trường `exitMessage` trong TaskRepository**, không phải thuộc tính `spring.cloud.task.batch.events.*-order`.

Ví dụ, không nên viết listener tổng kết kiểu:

~~~java
@AfterTask
public void after(TaskExecution execution) {
    execution.setExitMessage("SUCCESS"); // Sai nếu Job/Task đã thất bại.
}
~~~

Nên chỉ ghi thành công sau khi đã kiểm tra điều kiện, và để thông điệp lỗi đã tạo được giữ lại. Việc gán `exitMessage="SUCCESS"` cũng **không tự đổi exit code** từ lỗi sang thành công.

### 7.2. Task events khác Batch events

Spring Cloud Task có cơ chế phát **TaskExecution event** trên kênh `task-events` ở **lúc bắt đầu và kết thúc** khi có tích hợp Spring Cloud Stream. Cơ chế đó dùng một task listener do framework cung cấp.

~~~properties
# Tắt phát Task events qua Stream nếu không cần:
spring.cloud.task.events.enabled=false

# Tắt các Batch events được Task tích hợp:
spring.cloud.task.batch.events.enabled=false
~~~

Hai cờ điều khiển **hai nhóm sự kiện riêng**. Tắt phát event không đồng nghĩa tắt ghi metadata TaskRepository hoặc JobRepository. Cũng không có lý do để tự phát minh thuộc tính `spring.cloud.task.events.job-execution-order`: các khóa `job-execution-order`, `step-execution-order`, v.v. được mô tả dưới tiền tố **`spring.cloud.task.batch.events`**.

Trong cùng một tiến trình, event Task **bắt đầu** xảy ra ở pha Task startup, còn Batch Job events thuộc lần chạy Job bên trong. Event Task **kết thúc** liên quan việc tiến trình hoàn thành. Tuy nhiên, consumer đọc từ nhiều topic/queue khác nhau **không được bảo đảm** nhận đúng trình tự như các callback nội bộ.

## 8. Thứ tự phát và thứ tự nhận qua broker

Giả sử listener trong một Pod gọi theo trình tự:

~~~text
T1  JobExecutionListener.beforeJob → gửi JOB_STARTED
T2  StepExecutionListener.beforeStep → gửi STEP_STARTED
T3  StepExecutionListener.afterStep  → gửi STEP_COMPLETED
T4  JobExecutionListener.afterJob   → gửi JOB_COMPLETED
~~~

Consumer có thể **quan sát khác thứ tự** khi:

- Event `job-execution-events` và `step-execution-events` đi qua **hai destination**.
- Message được phân vào **nhiều partition** hoặc nhiều queue khác nhau.
- Producer có gửi lại, consumer retry hoặc dead-letter/replay.
- Có nhiều instance worker phát sự kiện đồng thời.
- Event bị gửi thành công nhưng consumer xử lý chậm hoặc nhận lỗi tạm thời.

Ví dụ consumer thấy `STEP_COMPLETED` trước `JOB_STARTED` do hai kênh có tốc độ xử lý khác nhau. Điều đó **không chứng minh Batch chạy Step trước Job**.

Nếu nghiệp vụ cần xử lý event **có quan hệ trước–sau**, mỗi event nên có:

| Trường | Mục đích |
| --- | --- |
| `taskExecutionId` | Liên kết một lần chạy Spring Cloud Task, nếu có |
| `jobExecutionId` | Gom các event của cùng lần Batch Job |
| `stepExecutionId` hoặc tên Step | Phân biệt event theo Step |
| `eventType` | `JOB_STARTED`, `STEP_COMPLETED`, `JOB_COMPLETED`, ... |
| `eventTime` | Hỗ trợ điều tra, **không tự bảo đảm thứ tự tuyệt đối** |
| `sequence` trong phạm vi được kiểm soát | Dùng khi producer có thể đánh số thứ tự thật sự |
| `eventId` | Chống xử lý lặp ở consumer |

Đây là **mô hình dữ liệu gợi ý** cho một event envelope tùy biến; các trường trên **không phải cam kết** rằng Spring Cloud Task tự phát mặc định đủ mọi trường theo đúng tên.

### 8.1. Thiết kế consumer chịu được event đến sai thứ tự

Một consumer quản lý dashboard nên đọc event theo cách **idempotent** và chấp nhận event muộn:

1. Phân loại event bằng `eventType`, xác định `JobExecution ID` và các ID liên quan.
2. Kiểm tra `eventId` để tránh xử lý hai lần.
3. Cập nhật tiến độ nếu event mới hơn trạng thái đã biết trong **quy tắc trạng thái hợp lệ**, không chỉ dựa vào timestamp.
4. Nếu nhận `JOB_COMPLETED` trước `STEP_COMPLETED`, vẫn phải xử lý được Step event muộn.
5. Khi cần biết **trạng thái cuối có thẩm quyền**, truy vấn JobRepository/TaskRepository hoặc bảng nghiệp vụ thay vì tin một message đơn lẻ.

Khi consumer dùng broker có **bảo đảm thứ tự trong một partition**, chọn khóa phân vùng ổn định cho cùng `JobExecution ID` có thể giúp duy trì thứ tự **trong phạm vi đó**. Nhưng không có bảo đảm thứ tự toàn cục giữa các partition/topic/destination; retry và tái xử lý tại consumer vẫn cần idempotency.

### 8.2. Event phát ra có đồng nghĩa dữ liệu đã commit?

**Không phải lúc nào cũng vậy.** Listener có thể được gọi **trước khi** trạng thái metadata hoặc transaction nghiệp vụ hoàn tất commit, tùy callback và hạ tầng tích hợp. Một message `JOB_COMPLETED` xuất hiện trên broker không nên tự động được coi là bằng chứng một bảng báo cáo khác đã được ghi bền vững.

Với event mang quyết định nghiệp vụ như “đã phát hành báo cáo”, cần một cơ chế tin cậy hơn, ví dụ:

- Ghi **trạng thái `READY`** và **outbox event** trong cùng transaction của cơ sở dữ liệu nghiệp vụ.
- Worker phát outbox sau commit, có retry và khóa idempotency.
- Consumer kiểm tra artifact/report key đã tồn tại, không phát lại thông báo vô hạn.

Cấu hình `*-order` có thể sắp xếp callback, nhưng **không thay thế distributed transaction, outbox hay xác nhận kết quả**.

## 9. Điều chỉnh độ ưu tiên riêng theo loại event

Không nhất thiết bật tất cả event ở độ chi tiết cao. Có thể dùng các cờ sau:

~~~properties
spring.cloud.task.batch.events.enabled=true

# Chỉ cần Job + Step events, tắt Item/Chunk/Skip nếu không cần:
spring.cloud.task.batch.events.chunk.enabled=false
spring.cloud.task.batch.events.item-read.enabled=false
spring.cloud.task.batch.events.item-process.enabled=false
spring.cloud.task.batch.events.item-write.enabled=false
spring.cloud.task.batch.events.skip.enabled=false

# Ưu tiên listener phát Job event khác listener nghiệp vụ:
spring.cloud.task.batch.events.job-execution-order=5
spring.cloud.task.batch.events.step-execution-order=20
~~~

Các cờ `enabled` kiểm soát **có phát event của loại đó hay không**, còn `*-order` kiểm soát **ưu tiên listener phát event** trong cơ chế đăng ký. Nếu đã tắt loại event đó, đặt `*-order` cho nó thường không mang lại ý nghĩa vận hành.

Đối với môi trường production, việc phát sự kiện cho **mỗi item** có thể tạo lưu lượng message rất lớn. Ví dụ 10 triệu item với các event read, process và write có thể tạo nhiều triệu message tùy số callback, retry và cấu hình. Hãy dự trù broker capacity, retention, chi phí serialization và tải consumer; khi chỉ cần tiến độ theo lô, dùng Chunk/Step events hoặc metric tổng hợp sẽ thích hợp hơn.

### 9.1. Route destination khác nhau

Spring Cloud Task cho phép cấu hình binding/destination của các sự kiện Batch thông qua Spring Cloud Stream. Ví dụ, nếu muốn thay binding name của Step events, tài liệu mô tả thuộc tính:

~~~properties
spring.cloud.task.batch.events.step-execution-events-binding-name=my-step-execution-events
~~~

Sau đó cấu hình Spring Cloud Stream binding tương ứng theo model và phiên bản, ví dụ `spring.cloud.stream.bindings.my-step-execution-events.destination=monitoring-step-events`.

**Thay destination không làm thay đổi callback order.** Ngược lại, đổi `step-execution-order` không di chuyển message sang topic khác. Hai cơ chế được cấu hình độc lập.

## 10. Những tình huống thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy bất kỳ Batch event nào | Thiếu dependency Task–Batch/Stream, binder hoặc binding; feature bị tắt | Xem startup logs, classpath, `spring.cloud.task.batch.events.enabled` |
| Có Task event nhưng không có Job event | Task có chạy nhưng không khởi chạy Batch Job hoặc thiếu Batch integration | Kiểm tra `JobExecution` trong JobRepository |
| Event phát trước listener kiểm toán ở `afterJob` | Listener publisher ưu tiên thấp mặc định, callback after gọi ngược | Xác nhận composite/registration; thử `job-execution-order=5` so với audit `10` |
| Thay `job-execution-order` mà không thấy thay đổi | Không cùng loại listener/composite, hoặc listener không được đăng ký | Kiểm tra Spring Batch listeners, dependency, cấu hình thực tế |
| `STEP_COMPLETED` đến consumer trước `JOB_STARTED` | Khác topic/queue, độ trễ, retry | Tách **producer callback order** và **consumer delivery order** |
| Nhận trùng event sau retry | Broker redelivery hoặc consumer xử lý xong nhưng ack thất bại | Dùng `eventId`/idempotent processing |
| Task/Job FAILED nhưng dashboard vẫn xanh | Consumer đánh giá bằng message thay vì trạng thái chính thức | Đối chiếu TaskRepository, JobRepository, mã thoát |
| Một Step lỗi nhưng không thấy event `afterChunk` thành công | Lỗi/rollback kích hoạt callback lỗi | Kiểm tra `afterChunkError`, retry/skip policy |
| Tăng `*-order` làm thay đổi số event | Thứ tự callback có thể ảnh hưởng logic khác, hoặc lỗi listener | Test riêng listener nghiệp vụ, tránh phụ thuộc side effect |
| Consumer chậm khiến queue tồn đọng | Phát event quá chi tiết hoặc consumer yếu | Tắt loại event không cần, tổng hợp theo Step/Chunk |

### Khi một listener tự ném exception

Spring Cloud Task ghi nhận rằng exception ở một **`TaskExecutionListener`** có thể làm **ngừng các listener còn lại của cùng callback**, đồng thời ảnh hưởng kết quả/mã thoát Task. Với Batch listeners, exception cũng có thể ảnh hưởng Step/Job tùy loại callback và cơ chế xử lý.

Vì vậy, **listener dùng cho quan sát nên ngắn, ổn định và tránh phụ thuộc đồng bộ vào mạng không đáng tin cậy**. Không nên gọi API ngoài vài chục giây trong `beforeJob` chỉ để ghi log; nếu API chậm/hỏng, cả Job có thể bị ảnh hưởng.

Đừng tự catch mọi exception rồi báo “event thành công” khi message chưa tới nơi. Hãy xác định rõ yêu cầu tin cậy của event: quan sát best-effort hay đầu ra nghiệp vụ bắt buộc. Với loại thứ hai, dùng outbox/idempotency và có quy trình đối soát.

## 11. Bài thực hành: đo thứ tự listener và kiểm chứng broker

Thiết kế một Spring Cloud Task `daily-report-task` chạy một `Job` gồm một `Step` tạo báo cáo từ 1.000 bản ghi. Job có:

- `AuditJobListener`: triển khai `JobExecutionListener` và `Ordered` với `getOrder()=10`.
- Listener phát `job-execution-events` của Spring Cloud Task khi tích hợp Stream.
- `StepExecutionListener` nghiệp vụ ghi số bản ghi đã xử lý.
- Một consumer đọc Job/Step events và ghi log có `JobExecution ID`.

Thực hiện các phép thử sau:

| Thử nghiệm | Cấu hình | Điều cần quan sát |
| --- | --- | --- |
| **A — Mặc định** | Không đặt `job-execution-order` | Listener phát event dùng `LOWEST_PRECEDENCE` nếu auto-configured; quan sát trước/sau Audit |
| **B — Đổi ưu tiên** | `job-execution-order=5`, Audit `10` | Pha `beforeJob` và `afterJob` đổi vị trí tương đối theo composite |
| **C — Đổi Step listener** | `step-execution-order=5` | Chỉ tác động ưu tiên của Step event listener, không tự thay Job event order |
| **D — Tắt Item events** | `item-read.enabled=false` | Không còn event read ở kênh tương ứng, Job/Step events vẫn có |
| **E — Khác destination** | Route Job/Step tới hai queue/topic | Consumer có thể quan sát trễ/xen kẽ; đối chiếu callback logs ở producer |
| **F — Đảo tình huống lỗi** | Làm Step throw exception | Job/Task phải báo lỗi phù hợp; không được có giả định mọi callback thành công đều chạy |
| **G — Redelivery** | Tạo consumer retry cùng message | Consumer không cập nhật tiến độ hai lần cho cùng event |

### 11.1. Log listener để quan sát nội bộ

Ví dụ Java đơn giản, dùng trong Job test đã đăng ký listener:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.core.Ordered;

public class AuditJobListener
        implements JobExecutionListener, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        System.out.printf("AUDIT beforeJob id=%s%n", execution.getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        System.out.printf("AUDIT afterJob id=%s status=%s%n",
                execution.getId(), execution.getStatus());
    }
}
~~~

Cần **tự thêm log/instrumentation ở điểm gửi sự kiện** hoặc dùng trace của Spring Cloud Stream để đối chiếu thời điểm listener phát; Spring Cloud Task không có cam kết rằng nó tự in những dòng `PUBLISHER_JOB_EVENT` đã dùng ở ví dụ trên. Các phép thử nên dùng broker thử nghiệm và sample Job ngắn để quan sát dễ dàng.

### 11.2. Kết quả giải thích đúng

Một lời giải đạt cần phân biệt:

1. **Callback order**: Audit/publisher được gọi theo `Ordered` trong composite; với Job listeners, `beforeJob` và `afterJob` có chiều thứ tự khác nhau.
2. **Lifecycle order**: `beforeJob` xuất hiện trước Step thực thi, `afterJob` sau khi các Step của Job đó kết thúc.
3. **Message delivery order**: consumer không mặc nhiên thấy thứ tự của hai channel khác nhau giống như producer callback.
4. **Result correctness**: event phục vụ quan sát; trạng thái JobExecution, TaskExecution và bảng kết quả nghiệp vụ vẫn cần đối soát.
5. **Failure behavior**: listener ném lỗi, broker mất kết nối hoặc tiến trình bị kill có thể làm thiếu event, vì vậy cần giám sát độc lập.

## 12. Các điểm cần ghi nhớ

- **Thứ tự ưu tiên phát Batch events** được cấu hình qua `spring.cloud.task.batch.events.*-order` cho Job, Step, Chunk, ItemRead, ItemProcess, ItemWrite và Skip. **Mặc định là `Ordered.LOWEST_PRECEDENCE`**.
- **Số `order` nhỏ hơn biểu diễn ưu tiên cao hơn.** Với `CompositeJobExecutionListener`/`CompositeStepExecutionListener`, **before theo chiều ưu tiên, after theo chiều ngược**.
- Thuộc tính này chỉ điều chỉnh **listener phát sự kiện**, không thay thứ tự xử lý Step hoặc bảo đảm mọi message được tiêu thụ theo cùng thứ tự trên broker.
- `TaskExecutionListener` với `onTaskStartup`, `onTaskFailed`, `onTaskEnd` thuộc vòng đời Task; các `*-order` nói trên thuộc **Batch event listeners**, còn ưu tiên `exitMessage` là một cơ chế khác.
- **Spring Cloud Task quản lý vòng đời tiến trình**, **Spring Batch quản lý Job/Step**, còn **Spring Cloud Stream/broker** chuyển message. Quan sát và kiểm soát giao hàng phải tính đến cả ba tầng.
- Sự kiện có thể **đến trễ, đến lặp hoặc thiếu**. Với quyết định nghiệp vụ bắt buộc, cần outbox, idempotency, xác nhận commit và đối soát repository.
- Trước khi đổi thứ tự, kiểm chứng **listener registration, version, binder, callback logs và trạng thái thực thi** trên một môi trường thử nghiệm.

### Tài liệu tham khảo chính thức

- [Spring Cloud Task — Spring Cloud Stream Integration: Emit Order for Batch Events](https://docs.spring.io/spring-cloud-task/reference/stream.html)
- [Spring Cloud Task — Features: Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Batch — CompositeJobExecutionListener Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/listener/CompositeJobExecutionListener.html)
- [Spring Batch — CompositeStepExecutionListener Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/listener/CompositeStepExecutionListener.html)
- [Spring Batch — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html)
