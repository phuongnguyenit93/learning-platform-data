# Triển khai manager và worker độc lập cho Remote Step trong Spring Batch

## 1. Vì sao cần tách hai ứng dụng?

Giả sử một job cuối ngày gồm ba bước: kiểm tra dữ liệu, dựng bộ báo cáo PDF dung lượng lớn và công bố kết quả. Bước dựng báo cáo cần nhiều RAM, bộ font và thư viện render đặc thù; máy điều phối không nên phải mang các dependency nặng đó. Khi đó, có thể chạy **manager** để điều phối job và **worker** để thực thi bước dựng báo cáo trên một container hoặc máy riêng.

Đây là mô hình **Remote Step**: manager sở hữu job flow và gửi **lệnh thực thi step**; worker nhận lệnh, tìm đúng `StepExecution` trong metadata và chạy logic của `Step`. Khác với **remote partitioning**, một `RemoteStep` không tự chia một dataset thành N partition khi ta tăng số pod worker.

Bài **“Triển khai manager và worker độc lập”** thuộc chương **Remote Step** của module `SPRING_BATCH_SCALING_OPERATIONS`. Mục tiêu module là mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và mô hình phân tán; đồng thời nhận diện bottleneck, đảm bảo thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế.

Sau bài học, bạn có thể:

- Mô tả **ranh giới tiến trình**, dữ liệu và trách nhiệm giữa manager, broker, worker và `JobRepository`.
- Thiết kế hai ứng dụng Spring Boot (hoặc hai profile) triển khai, cấp quyền và scale độc lập.
- Cấu hình `RemoteStep` phía manager và `StepExecutionRequestHandler` phía worker theo **Spring Batch 6.x**.
- Phân biệt **gửi yêu cầu** với **theo dõi hoàn thành bằng polling metadata**, tránh cấu hình reply channel không cần thiết.
- Thiết kế queue, kết nối DB, readiness, shutdown, versioning, retry/restart và idempotency cho môi trường container.
- Kiểm thử lỗi worker, manager và broker, đồng thời đo giới hạn concurrency theo tài nguyên thật.

**Phiên bản:** API `RemoteStep` được giới thiệu từ **Spring Batch 6.0**. Các ví dụ Java dưới đây sử dụng cách cấu hình của **6.x**. Nếu hệ thống dùng Spring Batch 5.x, không có nghĩa chỉ đổi import là áp dụng được `RemoteStep`; hãy cân nhắc remote partitioning và API tương ứng của phiên bản đó.

## 2. Topology: ai sở hữu phần nào?

~~~mermaid
flowchart LR
    O[Scheduler / CLI / Job Operator] --> M[Manager service<br/>Job + RemoteStep]
    M -->|StepExecutionRequest| Q[(Durable request queue)]
    Q -->|Consumer / adapter| H[Worker service<br/>StepExecutionRequestHandler]
    H --> S[Worker Step<br/>reader / tasklet / writer]
    S --> D[(Business DB / object storage)]
    M <-->|Tạo execution, polling| R[(Shared JobRepository)]
    H <-->|Tìm execution| R
    S <-->|Status + checkpoint| R
    M --> N[Next step trong Job flow]
~~~

| Thành phần | Trách nhiệm chính | Không nên làm |
|---|---|---|
| **Manager service** | Chạy `Job`, xây job flow, tạo metadata, gửi remote request, chờ và quyết định bước tiếp theo | Không tự dựng báo cáo hoặc giữ trạng thái thực thi của worker trong biến RAM |
| **Broker/transport** | Chuyển `StepExecutionRequest` tới đúng nhóm worker; hỗ trợ durability, ACK/redelivery và quan sát | Không được coi ACK message là bằng chứng nghiệp vụ đã thành công |
| **Worker service** | Nhận request, tra `StepExecution`, tìm bean `Step`, thực thi business logic | Không tự launch cả job mới cho từng message |
| **JobRepository** | Lưu `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và trạng thái checkpoint | Không phải cơ chế distributed lock/idempotency hoàn chỉnh cho hệ thống ngoài |
| **Business storage** | Lưu snapshot đầu vào, file báo cáo, trạng thái nghiệp vụ, outbox | Không nên phụ thuộc filesystem tạm bên trong manager/worker pod |
| **Observability** | Log/metrics/trace theo execution và worker instance | Không log secret hay nội dung `ExecutionContext` nhạy cảm |

**Một nguyên tắc bắt buộc:** manager và worker phải truy cập được **cùng kho metadata Spring Batch** với schema và cấu hình tương thích. Hai ứng dụng cùng tên `Job` nhưng mỗi ứng dụng có một `JobRepository` khác nhau **không** tạo thành một remote step hoạt động đúng.

## 3. Vòng đời thực thi khi manager và worker tách process

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant M as Manager / RemoteStep
    participant R as Shared JobRepository
    participant Q as Request queue
    participant W as Worker / Handler
    participant D as Business storage
    S->>M: Launch Job với identifying JobParameters
    M->>R: Tạo JobExecution / StepExecution
    M->>Q: Gửi StepExecutionRequest(stepName, stepExecutionId)
    Q->>W: Deliver request
    W->>R: Load StepExecution + ExecutionContext
    W->>W: StepLocator tìm worker Step
    W->>D: Thực thi nghiệp vụ
    W->>R: Commit checkpoint, cập nhật StepExecution
    loop Theo polling interval
        M->>R: Đọc trạng thái StepExecution
        R-->>M: STARTED / COMPLETED / FAILED ...
    end
    M->>M: Chuyển sang bước tiếp theo hoặc fail
~~~

Ở **Spring Batch 6.x**, `StepExecutionRequest` dùng `stepName` và `stepExecutionId` để định danh công việc. Manager tạo `StepExecution` rồi gửi định danh; worker không cần nhận toàn bộ dữ liệu đầu vào qua message. Worker truy xuất metadata và tự lấy dữ liệu nghiệp vụ từ nguồn mà nó có quyền truy cập.

`StepExecutionRequestHandler` gọi worker `Step` đã được đăng ký qua `StepLocator`, còn `RemoteStep` ở manager **poll `JobRepository`** để biết step kết thúc. Handler có thể trả `StepExecution` cho Spring Integration flow, nhưng **RemoteStep không bắt buộc phải có một reply queue chuyên dụng** như một số kiểu remote partitioning dùng reply aggregation.

Đặt tên rõ ràng:

~~~text
Job:              dailyReportJob
Logical step:     renderReportRemotely    (manager)
Remote step name: renderReportWorker      (worker)
Request queue:    batch.remote.render.requests
Business key:     reportKey = reports/2026-11-26/v1
~~~

Tên `renderReportWorker` trong request phải khớp chính xác bean `Step` mà worker `StepLocator` có thể tìm. Tên broker queue và business key là contract cấu hình ứng dụng, không phải tên mặc định do Spring Batch tự tạo.

## 4. Hai cách đóng gói để triển khai độc lập

### Phương án A: hai ứng dụng và hai image

~~~text
manager-application
  ManagerMain
  Job flow / RemoteStep / JobOperator hoặc launch adapter
  Spring Integration outbound adapter
  JobRepository / observability

worker-application
  WorkerMain
  StepExecutionRequestHandler + StepLocator
  Worker Step + reader / processor / writer
  Spring Integration inbound adapter
  JobRepository / business datasource / observability

shared-contract
  Tên step, tên queue, schema event/request, version compatibility
  Model nghiệp vụ dùng chung khi thực sự cần
~~~

**Ưu điểm:** quyền truy cập riêng, image worker nhỏ/gọn cho tài nguyên đặc thù, phát hành/scale độc lập. **Đánh đổi:** cần kiểm soát tương thích version và giao thức giữa hai ứng dụng; đừng copy toàn bộ code manager vào worker chỉ để tái sử dụng vài class.

### Phương án B: cùng image, hai profile/role

~~~text
batch-app.jar
  --spring.profiles.active=manager
  --spring.profiles.active=worker
~~~

Cách này dễ đồng bộ dependency và tái dùng cấu hình. Tuy nhiên, mỗi role phải **chỉ bật các bean của chính nó**: manager không tự nhận request; worker không tự chạy job orchestration. Cùng image cũng làm worker phải chứa dependency của manager (hoặc ngược lại), nên có thể tăng kích thước và phạm vi quyền.

| Tiêu chí | Hai image | Một image, hai role |
|---|---|---|
| Build và release | Tách biệt, cần compatibility matrix | Đơn giản hơn nhưng có thể phải deploy cả hai role cùng phiên bản |
| IAM/quyền DB | Dễ cô lập theo ứng dụng | Vẫn phải cô lập theo service account/secret khi chạy |
| Phụ thuộc native/renderer | Chỉ chứa ở worker | Image chung có thể bị phình |
| Version drift | Cần quản lý chặt | Ít hơn nếu chạy cùng image digest |
| Scale worker | Scale deployment riêng | Vẫn scale deployment của profile worker riêng |

Trong bài này dùng **hai role riêng** về mặt triển khai; tùy tổ chức, có thể tạo hai image hoặc dùng cùng image với profile.

## 5. Dependency, metadata và hợp đồng tích hợp

Hai ứng dụng nên dùng **cùng bộ Spring Batch/Spring Integration tương thích**, được quản lý qua BOM/dependency management của Spring Boot. Manager cần `RemoteStep` và outbound messaging; worker cần `StepExecutionRequestHandler`, bean `Step` và inbound messaging. Cả hai cần cấu hình `JobRepository` và transaction phù hợp.

Các thành phần cần dự kiến:

- Spring Batch core + Spring Batch Integration đúng phiên bản.
- Spring Integration core và adapter cho broker (ví dụ JMS/AMQP) cùng message converter.
- Driver JDBC và schema metadata Spring Batch được quản lý bằng migration.
- Transaction manager cho worker step và connection pool có giới hạn.
- Logging/Micrometer/trace và cơ chế health check theo role.
- Secret/identity, TLS, network policy, quyền đọc/ghi broker và database.

### Shared JobRepository phải nhất quán

Giả sử metadata DB có endpoint logic `batch-meta-db`. Hai ứng dụng có thể có **connection pool riêng**, nhưng đều phải trỏ tới **cùng database/schema** và cấu hình cùng table prefix khi dùng JDBC repository.

~~~text
Manager Hikari pool ---\
                        +--> batch-meta-db / Spring Batch metadata tables
Worker Hikari pool  ----/

Worker business pool ----> business-db / report data
~~~

Có thể tách metadata DB và business DB để cô lập tải, nhưng khi đó cần hiểu ranh giới transaction: commit side effect nghiệp vụ và cập nhật metadata có thể không đồng thời trong mọi tích hợp.

Không cho worker tự tạo lại schema metadata khi startup. Việc schema migration nên do một quy trình điều hành có kiểm soát thực hiện trước deployment, và các worker phải tương thích với schema mới. Tránh deploy đồng thời hai major version mà metadata/request không tương thích.

### Contract cần chốt giữa hai nhóm

| Contract | Ví dụ | Kiểm tra bắt buộc |
|---|---|---|
| Worker step name | `renderReportWorker` | Bean name/Step name khớp request |
| Request DTO/version | `StepExecutionRequest` của Spring Batch 6.x | Serializer/deserializer cùng hợp đồng |
| Broker destination | `batch.remote.render.requests` | Publisher và consumer cùng địa chỉ/tenant |
| Metadata DB | `batch-meta-db` | Cùng schema, quyền và version |
| Identifying parameters | `reportKey`, `businessDate` | Chốt được JobInstance khi restart |
| Business input | URI hoặc snapshot key | Worker truy cập được và đầu vào bất biến |
| Output semantics | Upsert/outbox/object version | Retry không gây tác động kép |
| Timeout policy | Send timeout, poll interval, step deadline | Đủ dài cho step, có cảnh báo tiến độ |

## 6. Manager: định nghĩa RemoteStep theo Spring Batch 6.x

Ví dụ sau tập trung vào **wiring của manager**, không tự động chạy job nếu chưa có scheduler/launcher gọi. Đoạn sử dụng `RemoteStep`, `MessagingTemplate` và một outbound `MessageChannel`. Các số timeout minh họa cần hiệu chỉnh theo SLA; kiểm tra đơn vị và default cụ thể của patch version đang chạy.

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.remote.RemoteStep;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ManagerRemoteJobConfiguration {

    @Bean("managerOutboundRequests")
    public MessageChannel managerOutboundRequests() {
        return new DirectChannel();
    }

    @Bean
    public Step renderReportRemotely(
            JobRepository jobRepository,
            MessagingTemplate messagingTemplate,
            @Qualifier("managerOutboundRequests")
            MessageChannel outboundRequests) {

        RemoteStep remote = new RemoteStep(
                "renderReportRemotely",
                "renderReportWorker",
                jobRepository,
                messagingTemplate
        );
        remote.setMessageChannel(outboundRequests);
        remote.setPollInterval(5_000L);
        remote.setTimeout(1_800_000L);
        return remote;
    }

    @Bean
    public Job dailyReportJob(
            JobRepository jobRepository,
            @Qualifier("renderReportRemotely") Step remoteStep) {
        return new JobBuilder("dailyReportJob", jobRepository)
                .start(remoteStep)
                .build();
    }
}
~~~

**Điểm dễ bỏ sót:** `DirectChannel` chỉ là channel trong **JVM manager**. Phải có **outbound adapter** subscribe channel rồi publish tới broker. Nếu không, message không hề đi tới worker. `MessagingTemplate` cũng phải được cấu hình để send qua channel phù hợp; `RemoteStep` không tự mở TCP connection đến broker khi bạn chỉ tạo bean trên.

Một cấu hình tối thiểu cho luồng outbound với JMS (đây là **mảnh ghép** dùng cùng các bean trên):

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageChannel;

@Bean
public IntegrationFlow publishRemoteRequests(
        ConnectionFactory jmsConnectionFactory,
        @Qualifier("managerOutboundRequests")
        MessageChannel requests) {
    return IntegrationFlow.from(requests)
            .handle(Jms.outboundAdapter(jmsConnectionFactory)
                    .destination("batch.remote.render.requests"))
            .get();
}
~~~

Trong ứng dụng thật, thêm cấu hình broker URL, credentials/TLS, message converter/serializer, delivery mode, send timeout, error channel và queue lifecycle. `ConnectionFactory` của ví dụ là **JMS**; nếu bạn dùng RabbitMQ AMQP, thay adapter bằng loại AMQP tương ứng, không chỉ sửa tên class.

### Ai thực sự launch job?

`@Bean Job` chỉ **định nghĩa job**, không phải một lời gọi launch. Manager deployment cần một tác nhân kích hoạt:

~~~text
Scheduler/CronJob/API
  -> truyền businessDate, reportKey và các identifying JobParameters
  -> JobOperator / launch service (tùy phiên bản)
  -> chạy dailyReportJob
  -> ghi lại jobExecutionId và kết quả cuối cùng
~~~

Nếu dùng Spring Boot auto-launch, cần hiểu cách job parameters được chuyển từ argument, điều kiện job được chọn và mã thoát container. Nếu dùng `ApplicationRunner`/service chủ động, thường **tắt auto-launch** để không chạy cùng job hai lần. Không giả định một command-line property như `--app.report-key=...` tự trở thành Spring Batch `JobParameter`; ứng dụng cần ánh xạ rõ ràng.

## 7. Worker: handler, StepLocator và Step thực thi

Worker không cần định nghĩa `dailyReportJob` của manager. Nó cần **bean `Step`** đúng tên và **message endpoint** để gọi step đó khi nhận request.

### 7.1. Đăng ký handler theo API 6.x

~~~java
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.StepLocator;
import org.springframework.batch.integration.partition.BeanFactoryStepLocator;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkerRequestHandlerConfiguration {

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
        handler.setJobRepository(jobRepository);
        handler.setStepLocator(workerStepLocator);
        return handler;
    }
}
~~~

`StepLocator` tìm một bean `Step` được đăng ký trên worker. Tên trong request phải là `renderReportWorker`. Không cấp quyền cho message bất kỳ chỉ định và thực thi một bean tùy ý: hạn chế step registry, broker ACL và caller có thể publish vào queue.

**Khác biệt quan trọng:** `StepExecutionRequestHandler` trong Spring Batch **5.x** thường được cấu hình bằng `setJobExplorer(...)` và request gồm nhiều ID hơn; trong **6.x** sử dụng `setJobRepository(...)`. Đừng trộn class/serialized request giữa hai major version. Worker và manager cần một protocol + metadata schema tương thích.

### 7.2. Nối inbound adapter với handler

Ví dụ JMS inbound flow đặt trong worker (không chạy ở manager):

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow remoteStepInboundFlow(
        ConnectionFactory jmsConnectionFactory,
        StepExecutionRequestHandler workerRequestHandler) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(jmsConnectionFactory)
                    .destination("batch.remote.render.requests"))
            .handle(workerRequestHandler, "handle")
            .get();
}
~~~

Flow này minh họa **đường gọi handler**. Adapter/container listener cần cấu hình converter để payload giải mã đúng `StepExecutionRequest`, chính sách ACK/redelivery và concurrency phù hợp. Không gửi Java object tùy ý qua broker mà chưa thống nhất security, serialization và compatibility. Một message không deserialize được phải đi qua error handling/DLQ có quan sát, không được lặp vô hạn làm nghẽn queue.

**RemoteStep dùng repository polling:** kết quả trả về từ `handle(...)` không nhất thiết phải được gửi thành reply message. Nếu vô tình dùng một mẫu remote partitioning có reply aggregation, hãy kiểm tra hợp đồng manager trước khi tạo thêm reply queue không được tiêu thụ.

### 7.3. Worker step thật: xử lý nghiệp vụ và idempotency

Ví dụ tasklet gọi một service dựng báo cáo. `ReportRenderer` là interface ứng dụng cần triển khai; phần side effect xuất file/object storage **không** trở nên nguyên tử chỉ vì tasklet chạy trong transaction Spring:

~~~java
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.infrastructure.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

interface ReportRenderer {
    // Phải dùng reportKey làm idempotency key / tên output ổn định.
    void render(String reportKey) throws Exception;
}

@Configuration
public class WorkerReportBusinessConfiguration {

    @Bean("renderReportWorker")
    public Step renderReportWorker(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ReportRenderer renderer) {

        return new StepBuilder("renderReportWorker", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    Object key = chunkContext.getStepContext()
                            .getJobParameters().get("reportKey");

                    if (!(key instanceof String reportKey)
                            || reportKey.isBlank()) {
                        throw new IllegalArgumentException(
                                "Missing job parameter: reportKey");
                    }

                    renderer.render(reportKey);
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

`ReportRenderer` là interface ứng dụng minh họa, **cần có implementation được đăng ký làm bean Spring**; nó không phải class có sẵn của Spring Batch. Trong production, hàm `render` nên ghi đầu ra bằng **khóa bất biến** (ví dụ object key theo report version), dùng bản ghi trạng thái hoặc outbox, đối soát sau crash và không phát hành cùng một báo cáo hai lần ngoài ý muốn.

Nếu worker xử lý nhiều row/chunk thay vì một tasklet, có thể dùng chunk-oriented `Step`. Reader có cursor phải có lifecycle `ItemStream`, snapshot bất biến và checkpoint; với state theo execution, cân nhắc `@StepScope`. Không đặt `currentReportKey` mutable trong singleton service rồi set lại cho từng message.

## 8. Hợp đồng dữ liệu đầu vào/đầu ra giữa hai ứng dụng

Remote step **không gửi toàn bộ input data** từ manager tới worker. Request nên là thông tin điều phối có dung lượng nhỏ, còn business input lấy từ `JobParameters`, `ExecutionContext` hoặc snapshot/manifest được worker truy cập.

Ví dụ:

~~~text
JobParameters:
  reportKey      = "reports/2026-11-26/v1"
  businessDate   = "2026-11-26"

Business storage:
  snapshot: "orders/2026-11-26/v1"
  output:   "reports/2026-11-26/v1.pdf"

Transport:
  stepName       = "renderReportWorker"
  stepExecutionId = <ID do JobRepository cấp>
~~~

Nếu worker chạy container khác, `/tmp/report.csv` trên manager **không** tự xuất hiện ở worker. Chọn shared volume với mount nhất quán hoặc object storage có version/key rõ ràng. Không lưu một URL có token dài hạn hoặc toàn bộ dữ liệu nhạy cảm trong metadata/log.

### Cách dùng context theo nguồn

| Nguồn | Mục đích | Ví dụ |
|---|---|---|
| `JobParameters` | Đầu vào do scheduler cung cấp, có identifying values để định danh job instance | `reportKey`, `businessDate` |
| `JobExecutionContext` | Thông tin do bước trước chuẩn bị, dùng cho bước sau trong một job execution | `snapshotVersion`, `manifestKey` |
| `StepExecutionContext` | Checkpoint/trạng thái riêng của worker step | Vị trí đọc, file offset, tiến độ |
| Business DB/object store | Dữ liệu lớn và kết quả cần lưu lâu dài | Input snapshot, bảng tổng hợp, PDF |

Một step trước ghi key vào **step context của nó** không tự động khiến worker step khác nhìn thấy. Nếu cần truyền kết quả giữa các step, có thể dùng cơ chế promotion vào job context hoặc manifest bền vững, với thứ tự thực thi rõ. Trong môi trường phân tán, đừng dùng in-memory singleton/`ThreadLocal` phía manager để “truyền” dữ liệu cho worker.

## 9. Cấu hình runtime tách biệt

Hai ứng dụng cần các nhóm thuộc tính **riêng theo role**, dù một số giá trị như metadata DB và queue destination phải trùng logic:

~~~yaml
# application-manager.yml — minh họa, không tự tạo broker adapter
spring:
  batch:
    job:
      enabled: false

app:
  batch:
    role: manager
    requestDestination: batch.remote.render.requests
    remoteStep:
      pollIntervalMs: 5000
      timeoutMs: 1800000
~~~

~~~yaml
# application-worker.yml — minh họa, không tự tạo listener
spring:
  batch:
    job:
      enabled: false

app:
  batch:
    role: worker
    requestDestination: batch.remote.render.requests
    consumerConcurrency: 1
    shutdownDrainSeconds: 120
~~~

Các khóa `app.batch.*` là **custom application properties**: phải được bind vào bean cấu hình do ứng dụng cài đặt. Chúng không tự cấu hình `RemoteStep`, JMS listener hoặc Kubernetes resource. `spring.batch.job.enabled=false` là cách dùng khi ứng dụng chủ động launch job và không muốn Spring Boot tự chạy lúc startup; với worker service chỉ nhận message, đây thường là lựa chọn hợp lý.

Giữ timeout manager đủ lớn để step hợp lệ chạy xong, nhưng có giới hạn để phát hiện execution bị treo. Polling quá dày tăng load metadata DB; polling quá thưa làm manager nhận biết hoàn tất trễ. Broker send timeout và job/worker execution deadline cần được thiết kế **riêng**, không lấy một con số áp cho mọi lớp.

## 10. Ví dụ triển khai trên Kubernetes

Với Kubernetes, **manager** thường là `Job` được tạo bởi scheduler/orchestration, còn **worker** là `Deployment` luôn sẵn sàng nhận request. Ví dụ các manifest sau chỉ diễn tả topology và giới hạn tài nguyên; tổ chức cần bổ sung image thật, secret, config map, service account, network policy và cơ chế launch job tương ứng.

### 10.1. Manager dưới dạng Kubernetes Job

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: report-manager-20261126
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: batch-manager
      containers:
        - name: manager
          image: registry.example.invalid/batch-manager:6x-example
          args:
            - "--spring.profiles.active=manager"
            - "--app.batch.report-key=reports/2026-11-26/v1"
          envFrom:
            - secretRef:
                name: batch-manager-runtime
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
~~~

**Quan trọng:** Kubernetes `Job` không tự biết phải gọi `JobOperator`/launcher nào; Java manager application phải có **đường khởi chạy job có chủ đích**, ánh xạ `app.batch.report-key` thành `JobParameters` phù hợp và trả mã thoát có ý nghĩa. Cấu hình `backoffLimit: 0` trong ví dụ tránh Kubernetes mù quáng khởi động lại manager khi chưa đối soát worker cũ; đây là **lựa chọn mẫu**, không phải một quy tắc chung cho mọi SLA.

### 10.2. Worker dưới dạng Kubernetes Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: report-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: report-worker
  template:
    metadata:
      labels:
        app: report-worker
    spec:
      serviceAccountName: batch-worker
      terminationGracePeriodSeconds: 150
      containers:
        - name: worker
          image: registry.example.invalid/batch-worker:6x-example
          args:
            - "--spring.profiles.active=worker"
          envFrom:
            - secretRef:
                name: batch-worker-runtime
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
~~~

Một `Deployment` với 2 replica có 2 process worker, **không** làm một `RemoteStep` đơn lẻ chạy hai lần song song. Một request thường được một consumer nhận; replica còn lại cung cấp capacity cho các request/job khác hoặc giúp phục hồi khi consumer cũ ngừng. Broker cần cơ chế single-consumer delivery thích hợp và phải xử lý redelivery an toàn.

**Không chỉ tăng `replicas` rồi kết luận throughput của một step tăng.** Nếu mục tiêu là phân phối một dataset lớn sang nhiều worker đồng thời, dùng **remote partitioning** hoặc mô hình chia dữ liệu khác, không phải một remote step với nhiều pod nhàn rỗi.

### 10.3. Startup, readiness, liveness và graceful shutdown

Worker nên chỉ được xem là **ready** khi có thể nhận việc an toàn (broker kết nối, metadata DB truy cập được, dependency thiết yếu đã khởi tạo). Nhưng liveness quá hung hăng có thể kill process trong lúc tasklet đang chạy nặng. Cần:

1. Startup probe hoặc warmup phù hợp nếu khởi tạo thư viện render lâu.
2. Readiness phản ánh khả năng **nhận thêm request**, không phải trạng thái “đã hoàn tất job”.
3. Liveness chỉ phát hiện process thực sự kẹt, tránh kill worker vì một query tạm chậm.
4. Khi nhận SIGTERM: ngừng consumer nhận việc mới, chờ execution hiện tại hoàn tất đến deadline, đóng transaction/adapter.
5. Nếu không thể hoàn tất trước `terminationGracePeriodSeconds`, dựa vào checkpoint, trạng thái metadata và idempotency để phục hồi.

Một worker bị kill giữa việc ghi file và cập nhật metadata vẫn có thể tạo output rồi bị broker giao lại request. Không có readiness/liveness nào thay thế thiết kế idempotency.

## 11. Security: phân quyền theo role

Tách manager và worker có ý nghĩa khi quyền hạ tầng cũng được tách:

| Tài nguyên | Manager | Worker |
|---|---|---|
| JobRepository metadata | Truy cập theo API repository để tạo job/step, polling và cập nhật lifecycle | Truy cập repository để tra execution và ghi trạng thái/checkpoint |
| Request queue | Publish | Consume; không cần publish nếu không thuộc contract |
| Business DB | Chỉ quyền cần cho các step manager thực sự sở hữu | Quyền đọc/ghi đúng bảng phục vụ worker step |
| Object storage | Có thể chỉ đọc manifest/metadata | Đọc input snapshot, ghi output theo prefix cho phép |
| Secret/credentials | Secret riêng của manager | Secret riêng của worker |
| Logs/metrics | Quan sát job flow, send, polling | Quan sát handler, step và business processing |

Sử dụng TLS và authentication cho DB/broker, service account riêng, Kubernetes NetworkPolicy và nguyên tắc **least privilege**. Không hardcode password hoặc connection string có token trong image, YAML checked-in, `JobParameters` hay `ExecutionContext`. Queue publish phải được bảo vệ: một actor gửi tùy ý `StepExecutionRequest` có thể khiến worker kích hoạt step ngoài dự kiến.

Khi nhiều nhóm job chia sẻ queue, cần routing/tenant isolation, ACL, versioned destination và theo dõi correlation. Không cho phép một request của môi trường staging tiêu thụ bởi worker production.

## 12. Retry, redelivery, restart và ranh giới giao dịch

Manager, broker, worker, metadata DB và business storage thường **không nằm trong một transaction phân tán duy nhất**. Do đó, không thể kết luận “message ACK một lần” đồng nghĩa “nghiệp vụ đã thực hiện exactly-once”.

| Sự cố | Trạng thái có thể xảy ra | Biện pháp an toàn |
|---|---|---|
| Manager gửi request nhưng broker tạm lỗi | Execution đã có trong metadata, worker chưa nhận | Xem send error, queue và status trước khi retry |
| Worker chết trước khi chạy step | Request có thể đang pending hoặc chờ redelivery | Consumer khác nhận theo cấu hình broker; không tạo job instance mới bừa bãi |
| Worker chết sau vài chunk commit | Metadata đã có checkpoint từng chunk | Restart đúng execution/job instance, giữ input bất biến |
| Worker ghi output thành công nhưng mất ACK | Broker có thể phát lại request | Idempotency output và kiểm tra metadata trước khi thực thi lại |
| Manager timeout nhưng worker còn chạy | Manager không quan sát kịp, worker vẫn ghi dữ liệu | Không tự dispatch lại cùng execution khi worker cũ chưa được xác minh đã dừng |
| Broker reply không tồn tại | `RemoteStep` vẫn có thể hoàn tất bằng repository polling | Đừng thêm reply queue chỉ vì thấy ví dụ remote partitioning |
| Metadata DB tạm không truy cập được | Worker không ghi được checkpoint/status, manager polling lỗi | Retry có giới hạn; chống write trùng ở business store |
| Rolling upgrade worker giữa job | Serializer/API/step behavior không tương thích | Pin image, drain request và kiểm tra schema contract |

### Restart đúng JobInstance

`JobInstance` được xác định bằng job name và các identifying `JobParameters`. Khi job lỗi, restart theo **cùng identifying parameters** nếu muốn Spring Batch sử dụng metadata cũ. Tự thêm `run.id` mới có thể sinh job instance khác, khiến worker xử lý lại từ đầu.

Với một tasklet tạo PDF, bản thân tasklet không nhất thiết có checkpoint theo chunk; nên thiết kế workflow dạng:

~~~text
reportKey bất biến
  -> kiểm tra output theo reportKey/version
  -> tạo file tạm (staging) hoặc object có khóa duy nhất
  -> xác nhận kết quả bền vững
  -> publish trạng thái/metadata theo cơ chế idempotent
~~~

Nếu output đã có và checksum/version hợp lệ, worker có thể trả về thành công theo quy tắc nghiệp vụ thay vì sinh báo cáo thứ hai. Nếu cần phát event, cân nhắc **transactional outbox** và idempotency key ở consumer downstream.

### Duplicate delivery không đồng nghĩa hai worker được chạy song song an toàn

Broker có thể chuyển một message tới một consumer tại một thời điểm, nhưng khi ACK bị trễ hoặc connection mất, worker cũ **có thể còn đang chạy** trong khi broker giao lại message cho worker khác. Metadata `StepExecution` giúp nhận biết trạng thái, nhưng không đủ để cam kết mọi side effect ngoài hệ thống đúng một lần. Đừng dựa vào lock `synchronized` trong một JVM để điều phối các pod.

Cần một chiến lược đồng bộ phù hợp với nghiệp vụ: writer idempotent, unique key, lease/fencing token khi cần, transaction/outbox và runbook chỉ re-dispatch sau khi xác minh trạng thái thực tế.

## 13. Thread safety và sizing khi triển khai nhiều worker

Một worker application có thể nhận nhiều message, nhưng **không nên mặc định thực thi đồng thời nhiều `StepExecution` trên cùng một bean `Step`**. `Step` và reader/writer stateful có lifecycle; singleton mutable có thể khiến các execution ảnh hưởng lẫn nhau. Với cấu hình đầu tiên, **một execution hoạt động mỗi worker process** là giới hạn dễ kiểm chứng hơn; chỉ tăng concurrency sau khi có isolation và thử nghiệm chứng minh an toàn.

| Mô hình | Trần hoạt động | Cần chú ý |
|---|---|---|
| Một RemoteStep, hai worker pod rảnh | Thường một execution cho một lần gọi remote step | Hai pod không tự chia một step |
| Mười job đồng thời, năm worker pod mỗi pod một consumer | Tối đa khoảng năm worker request đang chạy | Queue wait, worker memory và metadata polling |
| Remote partitioning có 30 partition, năm pod mỗi pod hai execution an toàn | Trần scheduling tối đa 10 partition | Partition skew, resource pool và thread safety |
| Chạy một worker có CPU khỏe hơn | Một step có thể nhanh hơn nếu bị giới hạn CPU | Không nên mong hiệu năng tăng nếu nghẽn DB/I/O |

Nếu `N` worker pod, mỗi pod có `C` consumer thực thi đồng thời một cách an toàn, capacity lý thuyết là `N × C` request; thực tế còn giới hạn bởi số job/partition cần chạy và các pool.

Một ước lượng sơ bộ về sức chứa JDBC toàn cụm:

\[
\mathrm{ConnectionBudget} \approx
N_{\mathrm{workerPods}}\times P_{\mathrm{workerPool}}
+P_{\mathrm{managerPool}}+P_{\mathrm{otherServices}}
\]

Đây là **số connection có thể mở**, không phải khẳng định các connection đều active. Phải đo active/pending/idle, query latency, lock wait và giới hạn `max_connections` của DB. `RemoteStep` manager polling metadata quá dày cũng có thể làm tăng query load, nhất là khi hàng trăm job chạy song song.

### Khi nào không nên tách process?

Nếu step nhỏ và chạy vài giây, overhead broker/network/startup/polling có thể lớn hơn lợi ích. Nếu DB đã bão hòa, chuyển step sang worker khác không tạo thêm IOPS. Nếu một dataset lớn có thể chia độc lập, **remote partitioning** có thể phù hợp hơn việc nhân nhiều worker cho một `RemoteStep` đơn lẻ.

## 14. Logging, metrics và cảnh báo

Khó khăn lớn nhất của một remote step là log bị phân tán giữa ít nhất hai process. Nên gắn trường tương quan vào cả manager và worker:

~~~text
jobName
jobExecutionId
stepExecutionId
logicalStepName
workerStepName
workerInstanceId
requestMessageId / correlationId
businessKeyHash hoặc reportKey đã được lọc thông tin nhạy cảm
~~~

| Lớp | Chỉ số cần có | Dấu hiệu bất thường |
|---|---|---|
| Manager | Job/step duration, request send failures, polling count/latency, timeout | Step không hoàn tất dù đã có worker |
| Broker | Queue depth, oldest message age, unacked/redelivered, DLQ, consumer count | Request kẹt, consumer ngắt hoặc poison message |
| Worker handler | Request count, conversion errors, `StepLocator` misses, handler duration | Sai tên step/schema DTO |
| Worker business step | `BatchStatus`, `ExitStatus`, checkpoint age, read/write/rollback, output bytes | Nghiệp vụ lỗi, OOM hoặc side effect chưa đối soát |
| Metadata DB | Query latency, pool pending, lock wait, connection usage | Polling/commit là bottleneck |
| Kubernetes | Pod restart/OOMKilled, CPU throttling, heap/GC, termination | Worker bị kill do tài nguyên hoặc health check |

Với step xử lý vài chục phút, nên có **progress heartbeat ở tầng nghiệp vụ hoặc metric phù hợp**, nhưng không tự cập nhật metadata của Spring Batch bằng SQL thủ công chỉ để tạo heartbeat. Dùng listener/metric có kiểm soát, tránh ghi quá thường xuyên vào `JobRepository`.

### Query điều tra chỉ đọc

Nếu dùng JDBC schema mặc định (có thể tùy chỉnh table prefix), query như sau giúp liên hệ các execution:

~~~sql
SELECT STEP_EXECUTION_ID,
       JOB_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       READ_COUNT,
       WRITE_COUNT,
       START_TIME,
       END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Tên bảng/cột cần đối chiếu với schema version thực tế. Query phục vụ **chẩn đoán read-only**; không sửa `STATUS` hoặc `EXIT_CODE` trực tiếp bằng SQL để “cứu” job, vì có thể làm metadata lệch khỏi worker đang chạy.

## 15. Runbook triển khai và khôi phục

### Trình tự triển khai phiên bản mới

1. **Chốt version contract:** Spring Batch, Spring Integration, serializer, queue, tên worker step và schema metadata.
2. **Migration có kiểm soát:** backup và áp schema migration tương thích trước khi boot các phiên bản mới.
3. **Kiểm tra hạ tầng:** broker destination/ACL, TLS, DB pool, storage permission và secret từng role.
4. **Khởi động worker trước:** worker phải ready nhận message, `StepLocator` đăng ký đúng `renderReportWorker`.
5. **Smoke test:** launch một job test với `reportKey` bất biến và đầu ra nhỏ, xác minh request tới worker, metadata chuyển trạng thái và output chính xác.
6. **Cho scheduler gửi job thật:** ghi lại `jobExecutionId` và version image của manager/worker.
7. **Quan sát trong rollout:** queue age, handler error, metadata polling, memory và output.
8. **Drain trước nâng cấp:** ngừng publish job mới nếu cần, dừng nhận request, đợi execution hoàn tất hoặc có kế hoạch restart.

### Khi manager timeout

1. Xác định `jobExecutionId`/`stepExecutionId` và tên worker step.
2. Đọc metadata trong `JobRepository`: `STARTED`, `COMPLETED`, `FAILED` hay trạng thái khác? Cập nhật cuối khi nào?
3. Kiểm tra queue: request đang chờ, unacked, redelivery hay DLQ; kiểm tra adapter send/receive.
4. Tra worker log theo `stepExecutionId`. Worker có còn chạy hay đã bị kill?
5. Nếu worker **còn chạy**, không phát lại cùng execution theo kiểu thủ công. Nếu worker đã chết, kiểm tra side effect và checkpoint trước khi restart.
6. Dùng cùng identifying `JobParameters` và dữ liệu đầu vào bất biến cho restart phù hợp lifecycle.
7. Sau khi hoàn tất, đối soát output/reportKey, database/outbox và thông báo downstream.

### Khi worker không tìm thấy step

Xác minh request có `stepName=renderReportWorker`, trong worker có bean `Step` được `StepLocator` đăng ký và profile worker thực sự bật. Nếu API/version/serializer không khớp, không requeue vô hạn; chuyển sang DLQ có cảnh báo rồi khắc phục deployment/config.

### Khi tăng replica nhưng job không nhanh hơn

Hỏi trước: “Có **bao nhiêu remote step execution độc lập** đang cần chạy?” Nếu chỉ có một, replica phụ không giúp chia work. Nếu có nhiều job song song, kiểm tra queue pending, consumer count, CPU, JDBC pool pending và business I/O. Nếu workload chia được theo ID/file/tenant, đánh giá remote partitioning thay vì cố tăng consumer concurrency của một step stateful.

## 16. Ma trận kiểm thử trước production

| Test | Thao tác | Điều kiện đạt |
|---|---|---|
| Happy path | Manager launch, worker nhận request và xuất kết quả | `StepExecution` kết thúc thành công, report tồn tại một phiên bản đúng |
| Worker chưa sẵn sàng | Launch khi worker scale về 0 | Message tồn tại trong queue theo policy; timeout/alert rõ ràng |
| Sai `stepName` | Gửi request tới worker thiếu bean tương ứng | Lỗi được ghi nhận, không chạy nhầm step |
| Metadata DB khác nhau | Cho worker trỏ nhầm schema | Test phải thất bại rõ, không tự tạo execution mới |
| Duplicate request | Gửi lại cùng request sau commit | Không tạo side effect trùng; metadata và output nhất quán |
| Worker crash | Kill process giữa lúc đang render | Có thể phục hồi theo runbook, output tạm không bị công bố sai |
| Manager crash | Dừng manager khi worker còn thực thi | Không có hai manager cùng điều phối một execution khi khởi động lại |
| Broker disconnect | Ngắt kết nối ngắn, cho adapter reconnect | Retry/redelivery được giới hạn, không mất trace |
| Rolling upgrade | Chạy worker có version/serializer khác | Có chiến lược pin/compatibility; không deserialize nhầm |
| Resource exhaustion | Giảm DB pool, CPU hoặc RAM trong test | Cảnh báo và failure mode rõ, không dữ liệu sai im lặng |
| Restart | Restart cùng identifying params và immutable snapshot | Không tạo report trùng, metadata đúng job instance |

Nên kiểm thử các tình huống này bằng **hai JVM/container thật**, message broker và database metadata thật trong môi trường test. Một unit test trực tiếp gọi `handler.handle(request)` không tái tạo được ACK, redelivery, worker SIGTERM hay manager polling timeout.

## 17. Checklist vận hành

- [ ] Manager và worker có thể deploy/scale riêng và chỉ bật các bean phù hợp role.
- [ ] `RemoteStep` dùng Spring Batch 6.x; manager trỏ đúng worker step name.
- [ ] `StepExecutionRequestHandler` có `JobRepository` và `StepLocator` hợp lệ.
- [ ] Outbound/inbound adapter nối tới đúng request queue; converter và serializer tương thích.
- [ ] Cả hai role dùng **cùng metadata DB/schema** với migration/version đúng.
- [ ] Worker đọc được snapshot/file và ghi được output, không dựa vào filesystem tạm manager.
- [ ] Có nguồn launch job rõ; không tự chạy job đôi khi startup.
- [ ] Manager dùng polling/timeout phù hợp và có cảnh báo khi job đứng lâu.
- [ ] Worker drain request trước shutdown; pod restart không làm mất tính đúng.
- [ ] Output có idempotency key/version và kế hoạch đối soát khi broker redeliver.
- [ ] Concurrency và connection pool có giới hạn theo tài nguyên của toàn cụm.
- [ ] Service account, broker ACL, TLS, secrets và network policy tách theo role.
- [ ] Log/metric theo job/step execution và worker instance, không lộ dữ liệu nhạy cảm.
- [ ] Đã thử worker crash, manager crash, mất broker và restart giữa job.

## 18. Bài tập thực hành

### Bài 1 — Chia ứng dụng theo role

Phác thảo hai ứng dụng `report-manager` và `report-worker`. Ghi rõ bean nào nằm ở manager (`Job`, `RemoteStep`, outbound adapter) và bean nào nằm ở worker (`StepExecutionRequestHandler`, `StepLocator`, `renderReportWorker`, inbound adapter). Chỉ ra thành phần hai bên bắt buộc chia sẻ thông tin cấu hình.

### Bài 2 — Nối broker và metadata

Dùng một request destination `batch.remote.render.requests` và một metadata database. Kiểm tra manager xuất được request, worker tìm thấy `StepExecution` và cập nhật trạng thái, manager phát hiện hoàn thành qua polling. Thử dùng một DB metadata khác ở worker và giải thích lỗi.

### Bài 3 — Tách deployment trên Kubernetes

Từ hai manifest minh họa, thêm service account, secret, TLS, resource quota và readiness/liveness phù hợp. Triển khai 1 manager + 2 worker pod. Giải thích vì sao hai worker pod không có nghĩa một báo cáo được render song song hai lần.

### Bài 4 — Mất ACK sau khi xuất báo cáo

Cho worker hoàn tất xuất file, sau đó dừng process trước ACK. Quan sát message bị giao lại và thiết kế `ReportRenderer` dùng `reportKey` làm idempotency key. Nêu cách xử lý output tạm, output đã tồn tại và việc công bố báo cáo xuống downstream.

### Bài 5 — Đo giới hạn tài nguyên

Chạy cùng snapshot trên ba cấu hình: step local, RemoteStep một worker pod, RemoteStep nhiều replica phục vụ nhiều job đồng thời. Đo manager duration, worker duration, queue wait, metadata polling, CPU/RAM và DB pool pending. Xác định overhead của phân tán và khi nào nên chuyển sang remote partitioning.

**Tự kiểm tra:** Tại sao manager và worker cần cùng `JobRepository`? Vì sao một outbound `DirectChannel` chưa đủ để gửi request tới service khác? `RemoteStep` biết worker đã xong bằng cơ chế nào? Khi manager timeout, vì sao không được gửi lại mù quáng? Một worker bị kill sau khi ghi output nhưng trước ACK đặt ra rủi ro gì? Khi nào scale worker replica mang lại lợi ích, và khi nào phải chuyển sang partitioning?

## 19. Tài liệu tham khảo

- [Spring Batch 6.0 — Scaling and Parallel Processing: Remote Step execution](https://docs.spring.io/spring-batch/reference/6.0/scalability.html).
- [Spring Batch API — RemoteStep](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/remote/RemoteStep.html).
- [Spring Batch API — StepExecutionRequestHandler](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/partition/StepExecutionRequestHandler.html).
- [Spring Batch API — StepExecutionRequest](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/partition/StepExecutionRequest.html).
- [Spring Batch — TaskletStep](https://docs.spring.io/spring-batch/reference/6.0/step/tasklet.html).

## 20. Kết luận

Triển khai **manager và worker độc lập** với Remote Step giúp Spring Batch điều phối job ở một process và thực thi bước nặng trên process khác. Thiết kế đúng cần **request transport rõ ràng, worker `Step` đúng tên, `JobRepository` dùng chung, startup/shutdown có kiểm soát và contract phiên bản nhất quán**. `RemoteStep` trong Spring Batch 6.x theo dõi kết quả qua polling metadata; nó không tự chia một bước thành nhiều partition chỉ vì worker Deployment có nhiều replica.

Trong sản xuất, kết quả thành công không chỉ là request đến được worker. Cần bảo đảm **restart không tạo tác động trùng, input/output được định danh bất biến, security tách theo role, hệ thống chịu được worker/manager crash, và bottleneck được đo theo CPU, DB, broker cùng tài nguyên thực tế**. Khi cần chia một dataset thành nhiều phần chạy đồng thời, hãy xem remote partitioning như một quyết định kiến trúc riêng, không phải một tùy chọn số replica của Remote Step.
