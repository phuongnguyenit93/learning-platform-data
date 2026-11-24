# Truyền tham số, cấu hình và định danh cha con trong remote partitioning

## 1. Bài toán và mục tiêu

Một ứng dụng **Spring Cloud Task** chạy hữu hạn có thể cần xử lý hàng triệu bản ghi theo lịch hoặc yêu cầu. Khi một tiến trình không đáp ứng được thời gian xử lý, ta có thể kết hợp **Spring Batch remote partitioning**: manager chia công việc thành nhiều partition và giao cho các worker chạy độc lập.

Ví dụ, task đối soát giao dịch cho `tenant-A` ngày `2026-11-23`:

- Manager nhận yêu cầu nghiệp vụ, chạy một Batch Job và chia dữ liệu thành bốn khoảng ID.
- Mỗi worker nhận một partition, xử lý đúng khoảng được giao và ghi trạng thái StepExecution.
- Manager chờ kết quả từng worker, tổng hợp JobExecution và kết thúc lần chạy.
- Spring Cloud Task ghi metadata cho ứng dụng manager và các worker nếu mỗi worker cũng là một task được kích hoạt theo đúng cách.

Một triển khai đúng cần trả lời ba câu hỏi: **tham số nào dùng chung cho toàn Job**, **thông tin nào riêng cho từng partition**, và **ID nào nối TaskExecution cha–con với JobExecution/StepExecution**.

Điểm mấu chốt: `TaskExecutionId` là định danh một tiến trình task; `JobExecutionId` là một lần chạy Batch Job; `StepExecutionId` là một lần thực thi Step/partition. Chúng **không thể dùng thay thế cho nhau**, dù có thể cùng được biểu diễn bằng số nguyên.

## 2. Phân biệt remote partitioning và remote chunking

Spring Batch có những mô hình xử lý phân tán khác nhau:

| Khía cạnh | Remote partitioning | Remote chunking |
|---|---|---|
| Đơn vị phân phối | **Partition/StepExecution** | **Chunk** dữ liệu |
| Reader | Worker thường đọc dữ liệu trong ranh giới partition | Manager thường đọc/chia chunk rồi gửi đi |
| Thông tin cốt lõi | `StepExecution` và `ExecutionContext` | Request/reply message chứa chunk |
| Checkpoint | Liên quan đến StepExecution/ExecutionContext từng partition | Phụ thuộc chiến lược chunk, manager, worker và broker |
| Lỗi phổ biến | Sai range hoặc StepExecution, partition bị launch trùng | Message được gửi lại và chunk bị xử lý trùng |

Bài này tập trung **remote partitioning**, nhất là mô hình manager khởi chạy worker dưới dạng **Spring Cloud Task** thông qua một launcher/deployer tương thích.

Về kênh phân phối có hai lựa chọn thường gặp:

- **Messaging-based:** manager gửi thông điệp yêu cầu thực thi một StepExecution qua message broker, worker nhận và cập nhật trạng thái.
- **Task-launching/deployer-based:** PartitionHandler khởi chạy ứng dụng worker qua task launcher/deployer; trong một số dòng Spring Cloud Task Batch có thành phần như `DeployerPartitionHandler`.

Tên bean, constructor, cách chuyển request và thuộc tính cấu hình phụ thuộc phiên bản Spring Batch, Spring Cloud Task và Spring Cloud Deployer. Không nên cho rằng chỉ thêm một dependency là framework tự chia việc đúng cách.

## 3. Kiến trúc: TaskRepository và JobRepository

~~~mermaid
flowchart TD
    C["CronJob / API / CLI"] --> M["Manager Spring Cloud Task"]
    M --> MT["TaskRepository: TaskExecution cha"]
    M --> J["Batch JobExecution"]
    J --> P["Manager Step + Partitioner"]
    P --> A["StepExecution partition0"]
    P --> B["StepExecution partition1"]
    P --> D["StepExecution partition2"]
    A --> H["PartitionHandler + launcher"]
    B --> H
    D --> H
    H --> W1["Worker Task 1"]
    H --> W2["Worker Task 2"]
    H --> W3["Worker Task 3"]
    W1 --> WT["TaskRepository: child TaskExecutions"]
    W2 --> WT
    W3 --> WT
    W1 --> JR["Batch JobRepository: step/checkpoint"]
    W2 --> JR
    W3 --> JR
    JR --> M
    W1 --> BD["Business DB / output"]
    W2 --> BD
    W3 --> BD
~~~

| Repository | Đơn vị lưu | Mục đích |
|---|---|---|
| Spring Cloud Task `TaskRepository` | `TaskExecution` của manager và worker | Theo dõi tiến trình, start/end, exit code, parent relationship |
| Spring Batch `JobRepository` | `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` | Nhận diện Job/Step, trạng thái, checkpoint và restart |
| Business database/kho đầu ra | Dữ liệu thực sự đã xử lý | Bảo đảm kết quả, khóa nghiệp vụ và idempotency |

**Manager và worker phải chia sẻ được cùng ngữ cảnh metadata Batch.** Trong mô hình JobRepository chung, worker cần truy cập đúng database và schema chứa StepExecution mà manager đã tạo. Nếu worker trỏ sang JobRepository khác, nó có thể báo không tìm thấy StepExecution hoặc lưu trạng thái vào một kho hoàn toàn khác.

Một manager TaskExecution có thể có nhiều worker TaskExecution; một JobExecution có nhiều StepExecution. Quan hệ này không đơn giản là một-một.

## 4. Bốn nhóm thông tin cần truyền

| Nhóm | Ví dụ | Phạm vi thích hợp |
|---|---|---|
| **JobParameters** | `tenant`, `businessDate`, `revision` | Cùng một JobInstance/JobExecution |
| **Partition ExecutionContext** | `minId`, `maxId`, `shardId` | Riêng một StepExecution |
| **Application/deployment config** | DataSource, Spring profile, worker image, pool size, memory, timeout | Môi trường của worker |
| **Correlation và lineage IDs** | Parent TaskExecution ID, Child TaskExecution ID, JobExecution ID, StepExecution ID | Truy vết cha–con và Job/Step |

Ngoài ra còn **business key** dùng để chống ghi trùng (ví dụ tenant/ngày/giao dịch). Business key không thay đổi chỉ vì lần chạy có TaskExecution ID mới.

Các nguyên tắc:

1. JobParameters **không phải** môi trường JVM. Truyền `--date=...` chưa tự khiến giá trị này thành identifying JobParameter.
2. ExecutionContext **không phải** các biến môi trường dùng chung. Mỗi StepExecution có dữ liệu partition riêng.
3. ParentTaskExecutionId **không phải** JobExecutionId; đây là hai namespace và repository khác nhau.
4. Các secret **không nên nằm trong JobParameters, ExecutionContext hoặc command-line arguments**, vì có thể được lưu trong metadata/log.
5. Platform execution ID của Pod/TaskLauncher hỗ trợ vận hành, nhưng không thay thế ID Task/Batch.

## 5. JobParameters: nhận diện JobInstance chung

Spring Batch định danh một **JobInstance** bằng **tên Job và tập JobParameters có identifying=true**.

Ví dụ:

~~~text
Job name: reconcileTransactionsJob

Identifying:
  tenant       = tenant-A
  businessDate = 2026-11-23
  revision     = 1

Non-identifying:
  traceId      = request-15e7
~~~

Trong Spring Batch 5:

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
    .addString("tenant", "tenant-A", true)
    .addString("businessDate", "2026-11-23", true)
    .addLong("revision", 1L, true)
    .addString("traceId", "request-15e7", false)
    .toJobParameters();
~~~

Các partition của một JobExecution chia sẻ JobParameters của Job; **worker không nên tự khởi chạy một JobInstance mới cho mỗi partition**. Nếu mỗi worker thêm `run.id` hoặc timestamp identifying, Batch có thể coi đó là những JobInstance khác nhau, làm mất khả năng restart cùng JobInstance và checkpoint cũ.

Khi retry do lỗi, giữ nguyên identifying parameters nếu vẫn là **cùng ý định nghiệp vụ**. Nếu cần chạy lại trên snapshot mới hoặc thuật toán mới theo một revision có chủ đích, cập nhật business key/identifying parameters tương ứng.

**Không đặt `partitionId` thành identifying JobParameter để phân biệt các worker trong cùng một JobExecution.** Để phân biệt phần việc của worker đã có StepExecution ID và ExecutionContext riêng.

## 6. ExecutionContext: dữ liệu phân vùng của StepExecution

`Partitioner.partition(int gridSize)` trả một `Map<String, ExecutionContext>`. Mỗi entry gồm **tên partition** và bộ dữ liệu nhỏ mô tả phần việc cho StepExecution tương ứng.

Ví dụ Java chia ID thành các khoảng đóng không chồng lấn:

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
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        if (maxId <= 0) {
            return partitions;
        }

        long size = (maxId + gridSize - 1) / gridSize;
        for (int i = 0; i < gridSize; i++) {
            long first = i * size + 1;
            long last = Math.min(maxId, (i + 1) * size);

            if (first > maxId) {
                break;
            }

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", first);
            context.putLong("maxId", last);
            partitions.put("partition" + i, context);
        }

        return partitions;
    }
}
~~~

Với một triệu ID và `gridSize=4`:

| Partition name | `minId` | `maxId` |
|---|---:|---:|
| `partition0` | 1 | 250.000 |
| `partition1` | 250.001 | 500.000 |
| `partition2` | 500.001 | 750.000 |
| `partition3` | 750.001 | 1.000.000 |

Phải dùng chung quy ước range (ví dụ `id >= minId AND id <= maxId`). Nếu một worker dùng điều kiện `id < maxId`, có thể mất bản ghi ở biên; nếu hai worker cùng tính ranh giới khác nhau, có thể xử lý trùng.

### Những giá trị nên/không nên lưu trong ExecutionContext

**Nên:** ranh giới ID, tên shard, ID snapshot nguồn, tham chiếu file/manifest, thông tin checkpoint nhỏ và có thể serialize.

**Không nên:** toàn bộ hàng triệu bản ghi, credential, datasource object, connection, HTTP client hay dữ liệu nhạy cảm. ExecutionContext được lưu trong JobRepository và cần tương thích serializer khi restart ở worker phiên bản khác.

**Partition name** như `partition0` chỉ có ý nghĩa trong ngữ cảnh manager step/JobExecution, không phải ID duy nhất toàn cluster.

## 7. Worker đọc JobParameters và StepExecutionContext bằng @StepScope

Spring Batch cho phép một bean cấp Step đọc tham số của Job và StepExecution đang chạy bằng **late binding**:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WorkerConfiguration {

    @Bean
    @StepScope
    Tasklet reconcilePartitionTasklet(
            @Value("#{jobParameters['tenant']}") String tenant,
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId,
            ReconcileService service) {

        return (contribution, chunkContext) -> {
            service.reconcileRange(
                tenant, businessDate, minId, maxId);
            return RepeatStatus.FINISHED;
        };
    }
}
~~~

`ReconcileService` là service nghiệp vụ cần xây dựng trong ứng dụng. Dữ liệu đầu vào:

- `tenant` và `businessDate`: **JobParameters chung**.
- `minId` và `maxId`: **ExecutionContext riêng của partition**.
- `@StepScope`: tạo bean đúng context, tránh dùng singleton bị gắn giá trị của partition khác.

Mẫu giả định worker đã được hạ tầng remote partitioning gắn với **StepExecution hợp lệ**. Chỉ truyền `--min-id=123` cho tiến trình Java không tự tạo StepExecution trong JobRepository và không bảo đảm biểu thức `stepExecutionContext['minId']` hoạt động.

Nếu partition xử lý dài, service phải dùng transaction theo chunk hoặc đơn vị có checkpoint và thiết kế idempotent; không chỉ dựa vào việc một Tasklet trả `FINISHED`.

## 8. Manager Step và PartitionHandler

Manager cấu hình một partitioned Step. `PartitionHandler` là lớp phân phối StepExecution sang worker, không đồng nghĩa với Partitioner:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ManagerConfiguration {

    @Bean
    Step managerStep(
            JobRepository jobRepository,
            Partitioner idRangePartitioner,
            PartitionHandler remotePartitionHandler) {

        return new StepBuilder("managerStep", jobRepository)
            .partitioner("reconcileWorkerStep", idRangePartitioner)
            .partitionHandler(remotePartitionHandler)
            .gridSize(4)
            .build();
    }
}
~~~

Đoạn code dành cho **Spring Batch 5** và giả định `idRangePartitioner`, `remotePartitionHandler` đã có bean phù hợp. Nó chưa tạo worker launcher, chưa cấu hình message broker và chưa chọn image worker.

Nếu dùng task launching/deployer, cần chỉ rõ:

- Resource URI/container image và phiên bản worker.
- Cơ chế chuyển StepExecution ID/metadata theo protocol do handler hỗ trợ.
- Deployment properties: resource limits, pool/concurrency, timeout và retry.
- Cách manager thu thập terminal status từ StepExecution khi worker hoàn tất hoặc chết.
- Cách cung cấp config/secrets cho worker.

Nếu dùng messaging, thay bằng cấu hình broker, request/reply channels và adapter tương ứng.

**`gridSize` mô tả số partition mong muốn**, không phải cam kết có đúng `gridSize` worker JVM chạy song song. Khả năng thực thi đồng thời phụ thuộc handler, quota, CPU/DB pool và môi trường triển khai.

## 9. Truyền tham số từ manager sang worker theo đúng kênh

| Thông tin | Kênh thích hợp | Lưu ý |
|---|---|---|
| `tenant`, `businessDate`, `revision` | JobRepository → JobParameters | Một JobInstance có bộ identifying parameters nhất quán |
| `minId`, `maxId`, `shardId` | JobRepository → StepExecutionContext | Riêng từng partition, không copy tùy tiện giữa các worker |
| `StepExecutionId` | Giao thức chính thức của PartitionHandler | Dùng để xác định StepExecution đã được manager tạo |
| Parent TaskExecution ID | Cơ chế Spring Cloud Task parent-execution-id | Liên kết task cha–con nếu worker được launch như task |
| Profiles, log level, timezone, pool size | Environment/config server | Manager và worker là các JVM riêng |
| DB passwords và API tokens | Secret manager / Kubernetes Secret / Vault | Tránh CLI và metadata |
| CPU/memory/retries | Deployment properties của nền tảng | Không phải identifying JobParameter |
| Trace/correlation ID | Tracing context/metadata không nhạy cảm | Dùng để tra log, không thay business key |

~~~mermaid
sequenceDiagram
    participant O as Scheduler
    participant M as Manager Spring Cloud Task
    participant JR as Batch JobRepository
    participant H as PartitionHandler
    participant W as Worker Spring Cloud Task
    participant TR as TaskRepository

    O->>M: tenant/date/revision
    M->>JR: Tạo JobExecution + JobParameters
    M->>JR: Tạo StepExecutions + ExecutionContexts
    M->>H: Giao partition StepExecutions
    H->>W: Launch + deployment config + Step ID
    W->>TR: Tạo TaskExecution con nếu được cấu hình
    W->>JR: Đọc StepExecution/JobParameters/ExecutionContext
    W->>W: Xử lý đúng partition
    W->>JR: Ghi trạng thái/checkpoint
    W-->>H: Hoàn thành hoặc lỗi
    H-->>M: Tổng hợp StepExecutions
~~~

Sơ đồ minh họa dòng thông tin ở mức logic. Một số handler chuyển thông điệp thay vì trực tiếp launch JVM; cách chuyển ID và thời điểm ghi repository khác nhau theo release.

**Không tự bịa tên cờ CLI `--jobExecutionId`/`--stepExecutionId` rồi coi đó là giao thức chuẩn mọi phiên bản.** Dùng API/handler được hỗ trợ và đối chiếu cách nó dựng worker execution request.

## 10. Định danh TaskExecution cha–con

Khi manager và worker đều là ứng dụng Spring Cloud Task, mỗi tiến trình có thể có TaskExecution riêng:

~~~text
Manager:
  taskExecutionId   = 5001
  taskName          = reconcile-manager

Worker partition0:
  taskExecutionId   = 5002
  parentExecutionId = 5001
  taskName          = reconcile-worker

Worker partition1:
  taskExecutionId   = 5003
  parentExecutionId = 5001
  taskName          = reconcile-worker
~~~

`parentExecutionId` biểu thị quan hệ **TaskExecution của worker → TaskExecution của manager**. Những phiên bản Spring Cloud Task có hỗ trợ sử dụng thuộc tính `spring.cloud.task.parent-execution-id` để truyền parent TaskExecution ID tới child task.

Ví dụ minh họa truyền metadata cha khi launch thủ công:

~~~bash
java -jar reconcile-worker.jar \
  --spring.cloud.task.parent-execution-id=5001 \
  --trace-id=reconcile-2026-11-23
~~~

**Lệnh trên không đủ để chạy remote partitioning**: worker còn cần protocol nhận đúng StepExecution, cấu hình Batch repository và worker Step. Trong triển khai thật, launcher/handler phải tạo đủ ngữ cảnh cần thiết, không chỉ truyền `parent-execution-id`.

| Định danh | Thuộc hệ thống | Ý nghĩa |
|---|---|---|
| `parentTaskExecutionId` | Spring Cloud Task / TaskRepository | Lần chạy cha khởi tạo worker |
| `childTaskExecutionId` | Spring Cloud Task / TaskRepository | Lần chạy tiến trình worker |
| `jobInstanceId` | Spring Batch / JobRepository | Tên Job + identifying JobParameters |
| `jobExecutionId` | Spring Batch / JobRepository | Một lần chạy/restart JobInstance |
| `stepExecutionId` | Spring Batch / JobRepository | Một StepExecution/partition cụ thể |
| `partitionName` | Partitioner | Tên logic trong ngữ cảnh manager Step |
| `externalExecutionId` | Task launcher/deployer | ID container/Pod hoặc lần chạy ngoài framework |
| `businessKey` | Dữ liệu nghiệp vụ | Dedupe kết quả khi retry |

Không dùng `parentTaskExecutionId` thay cho `jobExecutionId`; hai số có thể tình cờ giống nhau nhưng không có quan hệ bằng nhau. Một manager TaskExecution có thể chạy nhiều Job và mỗi Job có nhiều StepExecution.

Nếu tích hợp `spring-cloud-task-batch` và listener liên kết phù hợp, framework có thể ghi mapping TaskExecution–JobExecution vào metadata riêng. Cần xác minh cơ chế này được bật, repository đúng schema và worker thực sự được cấu hình integration; không suy đoán mapping từ tên task.

## 11. Cấu hình môi trường và secret cho worker

Một worker chạy trong JVM/container riêng nên **không tự kế thừa bean, DataSource, transaction hoặc biến Java của manager**. Nó cần config riêng hoặc nhận cấu hình được cung cấp chủ động khi launch.

Ví dụ `application.yml` cho worker:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: reconcile-worker
  datasource:
    url: jdbc:postgresql://db.internal:5432/batchdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: reconcile-worker

logging:
  level:
    root: INFO
~~~

`${DB_USER}` và `${DB_PASSWORD}` trong ví dụ đại diện cho biến môi trường Spring Boot và cần được cung cấp qua secret/config của hệ triển khai. Không hardcode tài khoản thật; worker phải truy cập được JobRepository schema chung và các bảng nghiệp vụ đúng quyền.

Các yêu cầu quan trọng:

1. **Repository nhất quán:** manager và worker đọc/ghi cùng JobExecution và StepExecution trong JobRepository tương ứng.
2. **Tách DataSource rõ ràng:** TaskRepository, Batch repository và business DB có thể ở ba vị trí khác nhau; chọn đúng datasource/transaction manager.
3. **Tương thích schema/serializer:** các worker phải dùng release được hỗ trợ và cấu trúc ExecutionContext tương thích.
4. **Secret an toàn:** không đưa credential qua command line, JobParameters hoặc ExecutionContext; các giá trị này có thể bị lưu trong repository và log.
5. **Cách ly tenant:** mọi truy vấn worker phải kiểm tra tenant/authorization, không chỉ gắn tenant làm nhãn log.
6. **Giới hạn tài nguyên:** nếu gridSize lớn, pool connection của các worker cộng dồn có thể làm quá tải CSDL.

## 12. Retry và crash windows: metadata khác kết quả nghiệp vụ

| Sự cố | Điều có thể xảy ra | Cách xử lý |
|---|---|---|
| Launcher từ chối worker | Manager biết một partition chưa thực thi | Kiểm tra deployer/image/quota và retry có giới hạn |
| Worker khởi chạy với sai JobRepository | TaskExecution con tồn tại nhưng Batch Step không được cập nhật đúng | So cấu hình DataSource/schema và StepExecution ID |
| Worker bị SIGKILL giữa partition | StepExecution có thể còn `STARTED` hoặc checkpoint cũ | Xác minh process chết và recovery đúng phiên bản |
| Worker commit dữ liệu rồi chết trước khi TaskRepository chốt | Business state có thể đầy đủ, child TaskExecution thiếu `END_TIME` | Đối chiếu các repository và business DB |
| Manager bị kill sau khi launch worker | Worker có thể vẫn hoạt động | Tìm orphan workers và tránh launch trùng |
| Worker nhận partition hai lần | Có thể ghi trùng side effect | Unique business key, transaction, checkpoint, fencing khi cần |
| Hết timeout chờ kết quả | Không chứng minh worker rollback | Tra terminal status theo StepExecution ID và platform ID |
| Nguồn dữ liệu thay đổi giữa restart | Range cũ có thể mang ý nghĩa khác | Cố định snapshot/cutoff và partition mapping |

**Retry của Spring Cloud Task không tự đồng nghĩa restart của Spring Batch.** Một lần chạy lại có TaskExecution ID mới, nhưng có thể cần tiếp tục cùng JobInstance/StepExecution theo các điều kiện Batch. Không thêm timestamp identifying mới chỉ để né lỗi restart.

Nếu một partition xử lý các giao dịch ID `250001..500000` đã commit một số giao dịch rồi crash, retry có thể xử lý lại. Cần unique constraint theo **business key**, transaction/chunk checkpoint phù hợp và idempotency cho mọi HTTP/message side effect. TaskRepository không bảo vệ kết quả nghiệp vụ khỏi nhân đôi.

## 13. Manager phải chờ trạng thái StepExecution

Một lời gọi task launcher trả về “đã nhận yêu cầu” **không có nghĩa** worker xử lý xong.

~~~mermaid
flowchart TD
    A["Manager tạo StepExecutions"] --> B["Launch worker partitions"]
    B --> C{"Có terminal StepExecution status?"}
    C -- "Không" --> D["Poll / reply / wait theo handler"]
    D --> E{"Timeout?"}
    E -- "Không" --> C
    E -- "Có" --> F["Đối chiếu process, Batch repository, retry policy"]
    C -- "Có" --> G{"Tất cả partitions thành công?"}
    G -- "Có" --> H["Manager step hoàn thành"]
    G -- "Không" --> I["Manager step thất bại hoặc theo policy"]
~~~

Giới hạn launch timeout, processing timeout, retry backoff, memory/CPU, DB connections và concurrency. Khi manager bị dừng, phải có chính sách cho các worker đã launch nhưng chưa kết thúc. Khi container worker tự restart, phải bảo toàn cách gắn với StepExecution và không tạo tác động nghiệp vụ trùng.

Không dựa vào thứ tự các partition hoàn thành. `partition3` có thể hoàn tất trước `partition0`.

## 14. Quan sát và truy vết theo chuỗi ID

Ví dụ định dạng log đề xuất ở manager:

~~~text
event=partition.launched
managerTaskExecutionId=5001
jobInstanceId=201
jobExecutionId=340
stepExecutionId=890
partitionName=partition2
businessDate=2026-11-23
~~~

Tương ứng ở worker:

~~~text
event=partition.completed
parentTaskExecutionId=5001
childTaskExecutionId=5004
jobExecutionId=340
stepExecutionId=890
partitionName=partition2
processedCount=250000
~~~

Đây là **log gợi ý**, không phải cấu trúc log mặc định. Lấy ID từ đúng repository/context; không in password, token, arguments nhạy cảm hoặc toàn bộ ExecutionContext.

SQL minh họa với tên bảng metadata mặc định quen thuộc:

~~~sql
-- Tìm các TaskExecution con của một lần chạy manager.
SELECT TASK_EXECUTION_ID, TASK_NAME, PARENT_EXECUTION_ID,
       START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE PARENT_EXECUTION_ID = :parent_task_execution_id
ORDER BY TASK_EXECUTION_ID;

-- Tìm StepExecutions của một lần chạy Batch Job.
SELECT STEP_EXECUTION_ID, JOB_EXECUTION_ID, STEP_NAME,
       STATUS, READ_COUNT, WRITE_COUNT,
       START_TIME, END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :job_execution_id
ORDER BY STEP_EXECUTION_ID;
~~~

Nếu cấu hình table prefix/schema riêng, điều chỉnh theo **DDL đang triển khai**. Bảng TASK và BATCH lưu metadata khác nhau và không mặc nhiên có foreign key nối trực tiếp hai bảng trên.

Một chuỗi truy vết hữu ích:

~~~text
business key / request ID
  -> manager TaskExecution
     -> JobInstance + JobExecution
        -> partition StepExecutions
           -> child TaskExecutions + platform execution IDs
              -> checkpoint / log / business result
~~~

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Worker không thấy `minId`/`maxId` | Sai StepExecution/ExecutionContext hoặc thiếu StepScope | Kiểm tra handler, JobRepository và bean StepScope |
| Mọi worker xử lý cùng range | Cấu hình min/max chung qua env/CLI | Đọc partition ExecutionContext riêng |
| JobInstance mới được tạo cho từng worker | Tự gọi JobLauncher với identifying params khác | Worker chạy StepExecution do manager tạo |
| Retry tạo JobInstance mới | `run.id`/timestamp identifying | Giữ bộ identifying params ổn định |
| TaskRepository có worker nhưng Batch không có Step | Worker không truy cập đúng JobRepository | Kiểm tra datasource/schema/StepExecution ID |
| Mất parent link | Không truyền parent TaskExecution ID | Xác minh launcher và property parent-execution-id |
| Nhầm parent ID với JobExecution ID | Dùng sai namespace ID | Đối chiếu bảng định danh mục 10 |
| Secret xuất hiện trong metadata | Đưa password/token vào JobParameters | Dùng secret manager |
| Manager báo hoàn tất sau launch | Chưa chờ terminal StepExecution status | Điều chỉnh PartitionHandler/wait/reply policy |
| Worker vẫn chạy sau manager crash | Không có chính sách orphan | Query trạng thái worker trước retry |
| Dữ liệu chồng lấn/thiếu | Ranh giới partition/reader sai | Kiểm tra hợp và giao của các range |
| Nhiều JVM quá tải DB | Grid size hoặc concurrency quá lớn | Giới hạn worker/pool và đo throughput |
| StepExecution còn STARTED sau crash | Chưa kịp chốt metadata | Recovery theo Batch release sau khi xác minh tiến trình |

### Điều không nên làm

Không dùng `Thread.sleep` để “chờ cho worker xong”, không thay `stepExecutionId` bằng `taskExecutionId`, không tự tạo JobExecution riêng trong worker rồi xem như remote partition, và không chỉ dựa vào mã thoát worker để xác định Job đã hoàn tất.

## 16. Bài thực hành

Tạo một ứng dụng manager Spring Cloud Task và một worker image chạy Spring Batch worker Step:

1. Cấu hình **JobRepository chung** có schema đúng version; cấu hình TaskRepository cho mỗi tiến trình nếu muốn xem task cha–con.
2. Chọn `tenant`, `businessDate`, `revision` làm identifying JobParameters.
3. Tạo Partitioner chia bốn khoảng ID và đảm bảo không trùng/không bỏ sót.
4. Tạo worker Step/Tasklet dùng `@StepScope` đọc đúng JobParameters và ExecutionContext.
5. Cấu hình PartitionHandler tương thích với nền tảng deployer hoặc messaging đã chọn.
6. Chuẩn bị image, config, secret, transaction manager và giới hạn tài nguyên cho worker.
7. Bật parent TaskExecution ID propagation và quan sát worker TaskExecution.
8. Chạy Job, lưu danh sách JobInstance ID, JobExecution ID, StepExecution ID, parent/child TaskExecution IDs.
9. Gây lỗi ở `partition2` rồi xác minh manager xử lý kết quả đúng.
10. Restart cùng identifying parameters; kiểm tra checkpoint và kết quả không bị nhân đôi.
11. Diễn tập kill một worker và kill manager; xác minh orphan worker trước khi retry.
12. Kiểm tra dữ liệu nghiệp vụ, secret trong metadata/log và behavior khi nguồn dữ liệu thay đổi.

| Điều kiểm tra | Kết quả kỳ vọng |
|---|---|
| Parent và child TaskExecutions | Có thể lần theo khi đã truyền parent ID |
| Một JobExecution nhiều StepExecutions | Worker cập nhật đúng StepExecution của mình |
| JobParameters | Nhất quán trên các partition cùng Job |
| ExecutionContext | Mỗi partition có range riêng |
| Manager và worker JobRepository | Trỏ đúng cùng metadata |
| Retry | Không tạo JobInstance sai hay ghi trùng dữ liệu |
| Worker hoặc manager crash | Có quy trình đối chiếu và phục hồi |
| Bí mật | Không nằm trong Task/Batch arguments hoặc ExecutionContext |

## 17. Kết luận

Kết hợp **Spring Cloud Task** với **Spring Batch remote partitioning** đòi hỏi phân biệt rõ:

- **Job-level:** `JobParameters`, `JobInstance`, `JobExecution` quyết định danh tính và khả năng restart.
- **Partition-level:** `StepExecutionId`, `partitionName` và `ExecutionContext` quyết định worker đang xử lý phần nào.
- **Process-level:** TaskExecution của manager và các worker, `parentExecutionId`, external execution ID cùng deployment config quyết định truy vết và vận hành tiến trình.

Manager phải cung cấp đủ ngữ cảnh để worker **gắn vào StepExecution đã được tạo**, chứ không đơn thuần chạy một JVM với vài tham số CLI. TaskRepository giúp theo dõi vòng đời cha–con, JobRepository giúp quản lý partition/checkpoint, còn unique business key và transaction bảo vệ kết quả. Khi hệ thống gặp lỗi, đối chiếu **cả ba lớp metadata và dữ liệu nghiệp vụ** trước khi restart để tránh bỏ sót hoặc xử lý lặp.
