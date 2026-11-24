# Khởi chạy phân vùng bất đồng bộ và đóng bộ thực thi

## 1. Bài toán: khởi chạy nhiều worker từ một ứng dụng task hữu hạn

Trong **Spring Cloud Task**, một ứng dụng Spring Boot thường khởi động, thực hiện một công việc hữu hạn, ghi nhận kết quả của lần chạy trong **TaskRepository** rồi dừng. Khi lượng dữ liệu cần xử lý lớn, ứng dụng có thể phối hợp với **Spring Batch remote partitioning**: một **manager** chia công việc thành nhiều phân vùng, mỗi **worker** chạy một Spring Batch `Step` ở tiến trình hoặc container riêng.

Giả sử cần tính toán trên một triệu bản ghi và chia làm tám dải khóa. Nếu việc tạo một Kubernetes Pod mất vài giây, **khởi chạy tám worker lần lượt** có thể khiến manager mất nhiều thời gian chỉ để chờ hạ tầng cấp tài nguyên, trước khi công việc xử lý thật sự diễn ra.

Spring Cloud Task hỗ trợ đưa một **`ThreadPoolTaskExecutor`** vào **`DeployerPartitionHandler`** để **gửi các yêu cầu khởi chạy worker bất đồng bộ**. Cần hiểu đúng điều này: *bất đồng bộ ở giai đoạn khởi chạy* **không có nghĩa** manager được phép đánh dấu Spring Batch Job hoàn tất ngay khi gửi xong các lệnh. Manager vẫn phải theo dõi các `StepExecution` trên **JobRepository** và tổng hợp kết quả.

Một vấn đề khác cũng quan trọng: thread pool được tạo để khởi chạy phân vùng có thể để lại các thread sống, khiến **JVM của task manager không tự thoát** sau khi xử lý. Vì vậy bài thuộc chương **Phân vùng từ xa** tập trung đồng thời vào **khởi chạy song song có kiểm soát** và **đóng bộ thực thi (executor) khi vòng đời task kết thúc**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Partitioner`, `PartitionHandler`, `TaskLauncher`, `ThreadPoolTaskExecutor` và worker `Step`.
2. Giải thích sự khác nhau giữa **khởi chạy bất đồng bộ**, **worker thực thi song song** và **manager đợi kết quả**.
3. Cấu hình `DeployerPartitionHandler` nhận executor để giảm độ trễ tạo worker.
4. Điều chỉnh `gridSize`, `maxWorkers`, kích thước thread pool, khoảng polling và timeout.
5. Bật `spring.cloud.task.closecontextEnabled=true` và thiết kế graceful shutdown để không rò rỉ thread.
6. Quan sát kết quả qua `TaskRepository`, `JobRepository` và log của manager/worker.
7. Kiểm thử restart, lỗi khởi chạy, worker thất bại và tiến trình bị kết thúc đột ngột.

## 2. Kiến trúc remote partitioning với Spring Cloud Task

~~~mermaid
flowchart LR
    S["Scheduler / yêu cầu chạy"] --> M["Manager Spring Cloud Task"]
    M --> P["Partitioner tạo ExecutionContext"]
    P --> H["DeployerPartitionHandler"]
    H --> E["ThreadPoolTaskExecutor (launch)"]
    E --> L["TaskLauncher / Spring Cloud Deployer"]
    L --> W1["Worker Task A"]
    L --> W2["Worker Task B"]
    L --> W3["Worker Task C"]
    W1 --> J[("Shared JobRepository")]
    W2 --> J
    W3 --> J
    H <--> J
    M --> T[("TaskRepository")]
    W1 --> T
    W2 --> T
    W3 --> T
~~~

| Thành phần | Vai trò | Điều **không** nên nhầm |
| --- | --- | --- |
| **Partitioner** | Chia phạm vi thành các `ExecutionContext` của từng phân vùng, ví dụ khoảng ID | Không tạo pod và không tự xử lý từng item |
| **Manager `PartitionStep`** | Tạo những `StepExecution` con, giao cho partition handler, tổng hợp kết quả | Không nên báo COMPLETED trước khi kết quả worker được xác nhận |
| **DeployerPartitionHandler** | Giao các worker cho Spring Cloud Deployer; truy vấn `JobRepository` để biết kết quả | Không phải bản thân executor xử lý dữ liệu nghiệp vụ |
| **TaskLauncher** | Tạo tiến trình/container cho worker theo một `Resource` và deployment properties | Không phải `TaskExecutor` quản lý thread nội bộ manager |
| **ThreadPoolTaskExecutor** | Thực hiện song song *các lời gọi launch* từ manager | Không phải số lượng worker đang chạy và không thay `maxWorkers` |
| **DeployerStepExecutionHandler** | `CommandLineRunner` ở worker: tìm `StepExecution` được chỉ định trong `JobRepository` rồi chạy `Step` tương ứng | Không tự phân hoạch lại dữ liệu |
| **JobRepository / JobExplorer** | Lưu và đọc `JobExecution` / `StepExecution`, trạng thái từng phân vùng và dữ liệu restart | Khác `TaskRepository` của Spring Cloud Task |
| **TaskRepository / TaskExplorer** | Theo dõi vòng đời từng tiến trình task manager và worker | Không có checkpoint Batch chi tiết cho từng phân vùng |

Trong triển khai qua `DeployerPartitionHandler`, **manager và tất cả worker phải cùng truy cập kho JobRepository**. Theo tài liệu tích hợp Spring Cloud Task, manager và worker cũng cần truy cập đúng kho TaskRepository khi sử dụng liên kết task/batch. Hai tiến trình dùng hai database chỉ có tên bảng giống nhau sẽ **không phối hợp được**.

## 3. “Bất đồng bộ” chính xác nằm ở đâu?

Theo Spring Cloud Task Reference, khi **không đưa `TaskExecutor` vào `DeployerPartitionHandler`**, các lời gọi khởi chạy phân vùng có thể diễn ra tuần tự. Một lời gọi `TaskLauncher.launch(...)` có thể tốn thời gian chuẩn bị môi trường, chẳng hạn yêu cầu Kubernetes tạo pod.

Khi truyền `ThreadPoolTaskExecutor`, handler có thể **gửi đồng thời nhiều lời gọi launch** theo chính sách thread pool. Ví dụ có tám phân vùng, mỗi request tạo pod tốn ba giây:

- Gửi yêu cầu tuần tự: riêng khâu gửi yêu cầu có thể gần **24 giây** trong tình huống minh họa, chưa tính thời gian worker xử lý.
- Gửi bốn yêu cầu song song: khâu gửi có thể xong theo hai đợt, khoảng **6 giây** trong tình huống lý tưởng.

Đây chỉ là ví dụ giải thích, **không phải cam kết hiệu năng**: quota API, thời gian tạo image, queue, database, độ trễ mạng và giới hạn Kubernetes đều làm kết quả khác đi.

~~~mermaid
sequenceDiagram
    participant M as Manager PartitionStep
    participant H as DeployerPartitionHandler
    participant E as ThreadPoolTaskExecutor
    participant L as TaskLauncher
    participant W as Worker tasks
    participant J as Shared JobRepository

    M->>H: handle(partitions)
    H->>E: submit launch(partition0)
    H->>E: submit launch(partition1)
    H->>E: submit launch(partition2)
    par Gửi yêu cầu launch
        E->>L: launch worker 0
        E->>L: launch worker 1
        E->>L: launch worker 2
    end
    L-->>W: Tạo tiến trình/container worker
    W->>J: Chạy Step và cập nhật StepExecution
    H->>J: Poll trạng thái StepExecution
    J-->>H: Một số phân vùng còn RUNNING
    H->>J: Poll lại theo khoảng cấu hình
    J-->>H: Các phân vùng đã có trạng thái cuối
    H-->>M: Trả StepExecution để tổng hợp
    M-->>M: Manager Step kết thúc theo kết quả tổng hợp
~~~

**Điểm cần nhớ:**

- “Launch trả về” chỉ có thể có nghĩa hệ thống triển khai đã **nhận yêu cầu** hoặc đã tạo **execution ID của worker**, **không** chứng minh `workerStep` đã thành công.
- `DeployerPartitionHandler` theo dõi kết quả phân vùng trong shared `JobRepository`; manager vẫn có thể phải **chờ lâu** trong khi worker xử lý.
- `ThreadPoolTaskExecutor` chỉ quản lý **các lời gọi khởi chạy phía manager**. Mỗi worker là tiến trình riêng và có vòng đời riêng.
- `maxWorkers` đặt giới hạn các worker được phép chạy đồng thời theo logic handler; `corePoolSize` đặt khả năng thực hiện song song các tác vụ launch trong **manager**. Hai con số không đồng nghĩa.

## 4. Thiết kế phân vùng và tính độc lập dữ liệu

Ví dụ chia 1.000.000 bản ghi theo khóa `source_id`:

| Phân vùng | Bắt đầu | Kết thúc | Worker xử lý |
| --- | ---: | ---: | --- |
| partition0 | 1 | 125.000 | `source_id BETWEEN 1 AND 125000` |
| partition1 | 125.001 | 250.000 | `source_id BETWEEN 125001 AND 250000` |
| partition2 | 250.001 | 375.000 | `source_id BETWEEN 250001 AND 375000` |
| ... | ... | ... | ... |
| partition7 | 875.001 | 1.000.000 | `source_id BETWEEN 875001 AND 1000000` |

Dải ID là **ExecutionContext của worker StepExecution**, không phải tham số JVM bắt buộc phải đưa trong CLI. Khi worker nhận ID step từ `DeployerPartitionHandler`, nó tra cứu repository để lấy `ExecutionContext` đã phân hoạch.

Một phân vùng an toàn phải có các tính chất:

1. **Không giao nhau:** không có bản ghi nguồn nào thuộc đồng thời hai dải.
2. **Không bỏ sót:** hợp các dải phủ hết phạm vi đã quyết định xử lý.
3. **Nguồn ổn định:** nếu nguồn thay đổi trong khi chạy, phải có snapshot/manifest hoặc quy tắc phiên bản dữ liệu.
4. **Có thể retry:** ghi kết quả có khóa nghiệp vụ duy nhất/idempotent; worker chạy lại không làm phát sinh tác động trùng.
5. **Tự mô tả:** các giá trị `minId`, `maxId` và version nguồn đủ để worker xử lý mà không phụ thuộc trạng thái trong bộ nhớ manager.

Không nên truyền một danh sách đối tượng Java trong RAM từ manager sang worker rồi kỳ vọng có thể restart sau khi manager bị kill; metadata và tài nguyên dữ liệu phải được truy cập bền vững.

## 5. Cấu hình ThreadPoolTaskExecutor cho manager

Ví dụ Java bên dưới áp dụng cách dùng **`DeployerPartitionHandler` trong Spring Cloud Task 3.0.x** được mô tả bởi Javadoc và tài liệu chính thức. Cần chọn release Spring Boot/Spring Batch/Spring Cloud Task tương thích; không trộn API của Batch 6 vào dự án Batch 5 mà chưa đối chiếu.

### 5.1. Bean executor do Spring quản lý

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@Profile("manager")
public class PartitionLaunchExecutorConfig {

    @Bean(name = "partitionLaunchExecutor")
    public ThreadPoolTaskExecutor partitionLaunchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("partition-launch-");

        // Khi context đóng, không cắt ngang ngay các request launch.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(120);

        // Spring khởi tạo và hủy bean đúng vòng đời.
        return executor;
    }
}
~~~

**Giải thích:**

- `corePoolSize=4` và `maxPoolSize=4`: có thể có tối đa bốn thread thực thi những lời gọi launch đồng thời trong ví dụ.
- `queueCapacity=16`: giữ có giới hạn các lời gọi launch chưa được executor xử lý. Khi vượt giới hạn, có thể xảy ra **rejection** thay vì được xếp hàng vô hạn.
- `setWaitForTasksToCompleteOnShutdown(true)`: lúc executor shutdown, các tác vụ đã được chấp nhận có cơ hội hoàn thành; đây **không** có nghĩa chờ toàn bộ worker từ xa chạy xong.
- `setAwaitTerminationSeconds(120)`: giới hạn thời gian đợi pool kết thúc khi Spring đóng context. Không nhầm với timeout của `DeployerPartitionHandler`.
- Đây là **Spring bean**, không phải `ExecutorService` tự tạo bằng `newFixedThreadPool` rồi bỏ quên. Spring có thể gọi cơ chế hủy của bean khi `ApplicationContext` được đóng.

Mức đợi shutdown phải được đánh giá cùng **termination grace period** của container. Nếu Kubernetes chỉ cho 30 giây để dừng pod nhưng ứng dụng cố đợi 120 giây, thời gian đợi ở Java không thể bảo đảm sẽ hoàn tất trước khi pod bị kill.

### 5.2. DeployerPartitionHandler dùng executor

~~~java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.cloud.deployer.spi.task.TaskLauncher;
import org.springframework.cloud.task.batch.partition.DeployerPartitionHandler;
import org.springframework.cloud.task.repository.TaskRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@Profile("manager")
public class RemotePartitionHandlerConfig {

    @Bean
    public PartitionHandler remotePartitionHandler(
            TaskLauncher taskLauncher,
            JobExplorer jobExplorer,
            TaskRepository taskRepository,
            ResourceLoader resourceLoader,
            @Qualifier("partitionLaunchExecutor")
            ThreadPoolTaskExecutor launchExecutor) {

        // Resource phải được TaskLauncher của hạ tầng chấp nhận.
        Resource workerResource =
                resourceLoader.getResource("file:/opt/apps/remote-worker.jar");

        DeployerPartitionHandler handler =
                new DeployerPartitionHandler(
                        taskLauncher,
                        jobExplorer,
                        workerResource,
                        "workerStep",
                        taskRepository,
                        launchExecutor);

        handler.setApplicationName("remote-partition-worker");
        handler.setGridSize(8);
        handler.setMaxWorkers(4);
        handler.setPollInterval(10_000L);
        handler.setTimeout(30 * 60_000L);
        return handler;
    }
}
~~~

**Đoạn mã giả định ứng dụng manager đã có bean `TaskLauncher` thực sự** (chẳng hạn từ một triển khai Spring Cloud Deployer phù hợp với môi trường); chỉ thêm `spring-cloud-starter-task` không có nghĩa tự có `TaskLauncher` cho Kubernetes. `file:/opt/apps/remote-worker.jar` chỉ phù hợp khi launcher truy cập được đường dẫn tệp đó. Với deployer khác, `Resource` có thể là Maven resource hoặc artifact reference tương ứng. Không sao chép path trên vào production nếu hạ tầng không thể đọc tệp.

Ở Spring Cloud Task 3.0.4, constructor sáu tham số của `DeployerPartitionHandler` nhận `TaskLauncher`, `JobExplorer`, `Resource`, tên worker step, `TaskRepository` và `TaskExecutor`. Nếu dùng phiên bản khác, hãy kiểm tra constructor và dependency theo Javadoc phiên bản đó.

### 5.3. Hiểu đúng bốn giới hạn

| Cấu hình | Phạm vi | Ý nghĩa trong ví dụ |
| --- | --- | --- |
| `setGridSize(8)` | Phân hoạch Spring Batch | Gợi ý số phân vùng/worker step cần tạo; Partitioner thực tế quyết định ExecutionContext |
| `setMaxWorkers(4)` | `DeployerPartitionHandler` | Giới hạn bốn worker chạy đồng thời theo handler |
| `setCorePoolSize(4)` | Thread pool phía manager | Có thể gửi tối đa bốn yêu cầu tạo worker cùng lúc |
| `setQueueCapacity(16)` | Hàng đợi lời gọi launch trong JVM manager | Nếu yêu cầu launch đến nhanh hơn thread xử lý, một phần sẽ chờ |
| `setPollInterval(10_000L)` | Theo dõi JobRepository | Thử đọc trạng thái phân vùng khoảng 10 giây một lần |
| `setTimeout(30 * 60_000L)` | Handler/manager | Giới hạn thời gian đợi của manager theo cấu hình; **không tự giết chắc chắn worker** |
| `setAwaitTerminationSeconds(120)` | Shutdown executor ở JVM manager | Đợi các lời gọi launch đã nhận khi context đóng |

`gridSize` không phải một cài đặt thread pool; `maxWorkers` không đảm bảo Kubernetes có đủ tài nguyên cấp số pod đó. Để điều chỉnh hiệu năng, đo **thời gian provisioning**, **số worker thực chạy**, **queue chờ**, **thời gian xử lý phân vùng** và **thời gian polling/tổng hợp** riêng rẽ.

## 6. Manager Job và Partitioner minh họa

Manager cần một Spring Batch `Job` chứa **PartitionStep**. Một `Partitioner` tạo từng dải khóa trong `ExecutionContext`. Ví dụ sau chia 1 đến 1.000.000 thành số dải theo `gridSize` được đề xuất.

### 6.1. Partitioner

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.stereotype.Component;

@Component
public class RangePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long upper = 1_000_000L; // Demo: tập nguồn đã chốt.
        long width = (upper + gridSize - 1) / gridSize;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (int index = 0; index < gridSize; index++) {
            long min = 1L + index * width;
            long max = Math.min(upper, min + width - 1);
            if (min > upper) {
                break;
            }

            ExecutionContext ctx = new ExecutionContext();
            ctx.putLong("minId", min);
            ctx.putLong("maxId", max);
            ctx.putString("sourceVersion", "v1");
            result.put("partition" + index, ctx);
        }

        return result;
    }
}
~~~

**Lưu ý:** trong ứng dụng thực, `upper` và version nguồn nên được **chốt theo JobParameters hoặc snapshot có khả năng restart**, không phải giá trị cố định viết trong code. Đổi cách chia giữa các lần restart cũng cần cân nhắc vì `StepExecution` của các partition đã được nhận diện theo tên.

### 6.2. Job và manager step

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("manager")
public class ManagerJobConfig {

    @Bean
    public Step managerStep(
            JobRepository jobRepository,
            RangePartitioner partitioner,
            PartitionHandler remotePartitionHandler) {

        return new StepBuilder("managerStep", jobRepository)
                .partitioner("workerStep", partitioner)
                .partitionHandler(remotePartitionHandler)
                .build();
    }

    @Bean
    public Job remoteImportJob(
            JobRepository jobRepository, Step managerStep) {

        return new JobBuilder("remoteImportJob", jobRepository)
                .start(managerStep)
                .build();
    }
}
~~~

Manager step không trực tiếp xử lý các bản ghi. Nó chia và điều phối `workerStep`. Số partition mà `Partitioner` tạo phải phù hợp với giới hạn nguồn và cách chạy lại; nếu tạo nhiều phân vùng hơn số worker đồng thời, handler sẽ triển khai chúng theo giới hạn `maxWorkers` và khả năng thực tế.

## 7. Worker thực hiện Step từ xa

Worker là **một ứng dụng Spring Boot Task hữu hạn khác** được hạ tầng tạo ra. Khi sử dụng `DeployerPartitionHandler`, worker được cung cấp ID của JobExecution/StepExecution và tên Step thông qua môi trường/tham số do handler triển khai. `DeployerStepExecutionHandler` khôi phục `StepExecution` từ **shared JobRepository** và chạy bean Step tương ứng.

**Quan trọng:** worker **không tự khởi chạy một Job mới** để thay cho StepExecution đã được manager tạo. Nếu Spring Boot tự chạy Job ngay khi worker khởi động, bạn có thể tạo thêm JobExecution ngoài dự kiến. Ở profile worker, vô hiệu hóa cơ chế tự chạy batch Job và để `DeployerStepExecutionHandler` thực hiện vai trò runner.

### 7.1. Bean DeployerStepExecutionHandler

~~~java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.cloud.task.batch.partition.DeployerStepExecutionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("worker")
public class WorkerLaunchConfig {

    @Bean
    public DeployerStepExecutionHandler stepExecutionHandler(
            BeanFactory beanFactory,
            JobExplorer jobExplorer,
            JobRepository jobRepository) {

        return new DeployerStepExecutionHandler(
                beanFactory, jobExplorer, jobRepository);
    }
}
~~~

`DeployerStepExecutionHandler` là `CommandLineRunner`. Worker cần có bean `workerStep` đúng tên để handler tìm được. Các ID `JobExecution` và `StepExecution` do manager cung cấp được dùng để lấy `ExecutionContext`, chứ không nên tạo lại partition bằng phép tính riêng trong worker.

### 7.2. Step ví dụ xử lý một dải khóa

Ví dụ này giả định `source_input` và `partition_result` đã tồn tại trong database nghiệp vụ, và mỗi hàng nguồn có `source_id` ổn định. Để minh họa gọn, dùng một Tasklet thực hiện SQL cập nhật theo phạm vi; khi xử lý dữ liệu lớn từng item, có thể thay bằng chunk-oriented step.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@Profile("worker")
public class WorkerStepConfig {

    @Bean
    public Step workerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("workerStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {

                    var execution =
                            contribution.getStepExecution();
                    long min = execution
                            .getExecutionContext().getLong("minId");
                    long max = execution
                            .getExecutionContext().getLong("maxId");

                    jdbc.update("""
                        INSERT INTO partition_result
                            (source_id, processed_value)
                        SELECT source_id, payload
                        FROM source_input
                        WHERE source_id BETWEEN ? AND ?
                        ON CONFLICT (source_id) DO UPDATE
                        SET processed_value =
                            EXCLUDED.processed_value
                        """, min, max);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

Bảng đích minh họa:

~~~sql
CREATE TABLE partition_result (
    source_id BIGINT PRIMARY KEY,
    processed_value TEXT NOT NULL
);
~~~

Câu `ON CONFLICT` chỉ có tính idempotent theo `source_id` nếu quy tắc nghiệp vụ cho phép ghi đè bằng cùng dữ liệu nguồn. Trong production cần xét `sourceVersion`, tính bất biến nguồn và khóa nghiệp vụ phù hợp. Nếu database metadata Batch và database nghiệp vụ khác nhau, không mặc định cả hai commit trong một giao dịch nguyên tử.

**Không nhầm worker step hoàn tất với việc gọi TaskLauncher thành công.** Worker phải cập nhật `StepExecution` của nó về trạng thái phù hợp, và manager mới có cơ sở kết luận phân vùng đã kết thúc.

## 8. Cấu hình profile và tài nguyên chạy worker

### 8.1. Profile manager

~~~yaml
# application-manager.yml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: remote-partition-manager
      closecontextEnabled: true
      batch:
        fail-on-job-failure: true
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never
~~~

### 8.2. Profile worker

~~~yaml
# application-worker.yml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: remote-partition-worker
      closecontextEnabled: true
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Cả hai profile còn cần **DataSource, schema và quyền truy cập metadata** được triển khai ngoài những đoạn YAML rút gọn này. Các bảng Batch cần được tạo trước bằng migration; nếu quản lý schema TaskRepository qua migration, phải đồng bộ cả phiên bản và prefix.

Tài liệu dùng `spring.cloud.task.closecontextEnabled=true`. Tùy binding phiên bản Boot, YAML cũng có thể viết dạng chuẩn `closecontext-enabled: true`. Khi cấu hình nhiều profile, hãy kiểm tra giá trị cuối cùng **thật sự được nạp**, đặc biệt nếu hạ tầng ghi đè bằng biến môi trường.

**Worker image / Resource:**

- Worker jar phải chứa bean `DeployerStepExecutionHandler` và `workerStep` cùng các dependency JDBC/Batch cần thiết.
- `TaskLauncher` phải biết cách chạy worker jar trên hạ tầng đích; sử dụng triển khai local/Kubernetes/Cloud Foundry tương ứng.
- Manager phải có quyền tạo worker, truyền environment/deployment properties cần thiết và xem trạng thái hạ tầng.
- **Không chuyển secret qua tham số CLI hoặc log** nếu có thể bị hiển thị ở lịch sử process và metadata Task. Dùng secret manager/biến môi trường được bảo vệ.
- Không để worker truy cập database khác với manager do sai `spring.profiles.active` hoặc sai DataSource URL.

Ở Kubernetes, tài nguyên worker có thể cần quy tắc tên DNS phù hợp. Hãy thiết kế `applicationName` và cách sinh tên tài nguyên theo yêu cầu của deployer đang dùng.

## 9. Đóng executor và ApplicationContext đúng thứ tự

Đây là phần **dễ nhầm nhất** của đề bài. `ThreadPoolTaskExecutor` tạo thread trong manager; sau khi gửi các request launch, thread pool có thể vẫn tồn tại. Tài liệu Spring Cloud Task nói rõ rằng khi dùng executor này để launch partition bất đồng bộ, **cần đóng Spring context** vì thread còn hoạt động có thể ngăn ứng dụng kết thúc.

### 9.1. Bật cơ chế đóng context của Spring Cloud Task

~~~properties
spring.cloud.task.closecontextEnabled=true
~~~

Spring Cloud Task đóng `ApplicationContext` sau khi các runner hoàn tất và metadata TaskExecution được cập nhật. Context đóng sẽ đưa những Spring bean có lifecycle/destroy callback đi qua quá trình dọn tài nguyên, bao gồm `ThreadPoolTaskExecutor` do Spring quản lý.

**Không đồng nhất ba mốc:**

| Mốc | Điều đã xảy ra | Điều chưa thể suy ra |
| --- | --- | --- |
| Một lệnh `TaskLauncher.launch` trả về | Đã hoàn thành một lần gửi yêu cầu khởi tạo worker | Worker đã chạy xong Step |
| `DeployerPartitionHandler.handle` trả về kết quả | Handler đã xử lý việc theo dõi và trả các `StepExecution` theo contract | Dữ liệu nghiệp vụ ngoài repository chắc chắn đúng |
| Manager Spring Batch Job/runner hoàn tất | Manager đã có kết quả JobExecution theo đường lifecycle | JVM chắc chắn thoát |
| Spring context đóng | Bean Spring được yêu cầu dọn tài nguyên | Mọi thread tự tạo ngoài Spring và mọi remote worker chắc chắn đã dừng |
| JVM kết thúc | Tiến trình manager không còn chạy | Không còn worker hoặc side effect ngoài JVM |

### 9.2. Không đóng executor ngay sau khi submit

**Sai:** shutdown pool ngay khi đã gọi các phương thức submit bất đồng bộ mà chưa xác nhận các tác vụ launch đã được chấp nhận/xử lý hoặc `PartitionHandler` đã hoàn thành việc điều phối.

~~~java
// Pseudocode minh họa lỗi thứ tự:
for (Runnable launchCommand : commands) {
    executor.execute(launchCommand);
}
executor.shutdown(); // Có thể cắt ngang luồng điều phối quá sớm.
~~~

Với `ThreadPoolTaskExecutor` khi là Spring bean, **không cần gọi shutdown thủ công** trong `Partitioner` hoặc runner vừa trả kết quả. Để lifecycle của manager và `ApplicationContext` quyết định thời điểm dọn pool sau khi Batch Job kết thúc. Nếu kiến trúc tự tạo executor ngoài Spring, trách nhiệm gọi shutdown/awaitTermination thuộc về bạn và phải có cơ chế xử lý lỗi/ràng buộc thời gian đầy đủ.

**Đúng hướng:** manager để `DeployerPartitionHandler` thực hiện hợp đồng launch + giám sát, để `JobRepository` nhận trạng thái cuối, sau đó mới để vòng đời Spring Cloud Task đóng context và pool.

### 9.3. Graceful shutdown vẫn cần timeout

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(120);
~~~

Hai cấu hình này giúp **các lời gọi launch đã nhận** có thời gian hoàn tất khi Spring đóng executor. Chúng **không chờ thay** `DeployerPartitionHandler` về kết quả worker, và **không điều khiển việc dừng Kubernetes Pod của worker**.

Trong production cần:

- Timeout handler để manager không chờ vô hạn khi một phân vùng bị treo.
- Timeout phù hợp cho I/O và transaction tại worker.
- Giới hạn thời gian shutdown của JVM/container, bảo đảm không nhỏ hơn thời gian dọn mong muốn.
- Chính sách khi manager bị nhận SIGTERM hoặc bị kill trước khi kết quả từ worker cập nhật xong.
- Quy trình đối soát remote worker còn sống sau khi manager dừng.

### 9.4. Trường hợp TaskBatch job lỗi

Theo Spring Cloud Task, giá trị mặc định của **exit code tiến trình task** khi chạy Spring Batch không phải lúc nào cũng phản ánh trực tiếp `BatchStatus.FAILED`. Thuộc tính:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

được dùng để cho phép ánh xạ Batch Job thất bại thành exit code khác 0 trong cấu hình tích hợp được hỗ trợ. **Vẫn phải kiểm chứng trên phiên bản và đường chạy thực tế**; đồng thời đọc `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và log worker, không chỉ tin vào mã thoát của manager.

## 10. Theo dõi kết quả trong ba lớp metadata

### 10.1. Batch JobExecution của manager

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE,
       START_TIME, END_TIME, EXIT_MESSAGE
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Điều cần xem là Job đã `COMPLETED` hay `FAILED`, có đầy đủ thời gian kết thúc hay không. Nếu manager bị kill đột ngột, JobRepository có thể chưa kịp cập nhật kết quả cuối dù worker đã xử lý một phần.

### 10.2. StepExecution của từng phân vùng

~~~sql
SELECT STEP_EXECUTION_ID, JOB_EXECUTION_ID,
       STEP_NAME, STATUS, EXIT_CODE,
       READ_COUNT, WRITE_COUNT,
       START_TIME, END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = 1001
ORDER BY STEP_EXECUTION_ID;
~~~

`JOB_EXECUTION_ID=1001` chỉ là ID ví dụ. Bạn có thể thấy tên như:

~~~text
managerStep
workerStep:partition0
workerStep:partition1
workerStep:partition2
...
~~~

Các partition có `StepExecution` riêng. Trên đường thành công bình thường, manager chỉ được coi là hoàn tất đúng khi tất cả partition bắt buộc có trạng thái hợp lệ và kết quả đã được tổng hợp.

### 10.3. TaskExecution của manager và worker

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME,
       END_TIME, EXIT_CODE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME IN (
    'remote-partition-manager',
    'remote-partition-worker'
)
ORDER BY START_TIME DESC, TASK_EXECUTION_ID DESC;
~~~

Có thể có một TaskExecution cho manager và nhiều TaskExecution cho các process worker. **Không mặc định TaskExecution ID bằng JobExecution ID hoặc StepExecution ID**: đó là ba cấp định danh khác nhau.

Nếu dự án bật tích hợp Spring Cloud Task Batch, bảng `TASK_TASK_BATCH` có thể lưu liên kết `TASK_EXECUTION_ID` và `JOB_EXECUTION_ID`. Đừng dùng tên task đơn lẻ để xác định một partition: nhiều worker có thể dùng chung tên. Log nên chứa `jobExecutionId`, `stepExecutionId`, `partitionName` và ID process/pod bên cạnh `taskExecutionId` khi khả dụng.

## 11. Timeout và thất bại: ai chịu trách nhiệm?

| Triệu chứng | Khả năng xảy ra | Hành động phù hợp |
| --- | --- | --- |
| Manager chậm trước khi thấy worker bắt đầu | `TaskLauncher.launch`/provisioning tuần tự hoặc hạ tầng quá tải | Đo launch latency, cấu hình thread pool, kiểm tra quota/pod scheduling |
| Launch requests bị từ chối | Hàng đợi/thread pool đầy, tài nguyên thiếu hoặc API deployer lỗi | Kiểm tra pool, `maxWorkers`, quota, backoff; không bỏ qua exception |
| Worker xuất hiện nhưng không chạy Step | Sai profile, thiếu `DeployerStepExecutionHandler`, tên `workerStep` không khớp | Kiểm tra runner và environment StepExecution ID |
| Manager poll mãi, không thấy hoàn tất | Worker không cập nhật cùng JobRepository, Step bị treo, DB không sẵn sàng | Kiểm tra DB/schema, step logs, timeout, thread dump/pod status |
| Manager hết timeout nhưng worker vẫn xử lý | Timeout manager **không đồng nghĩa** hủy được remote execution | Xác minh worker thật, quyết định cancel/reconcile qua deployer |
| Manager Batch job `FAILED` nhưng process exit 0 | Exit-code mapping chưa bật hoặc khác đường chạy thực tế | Cấu hình `fail-on-job-failure`, kiểm chứng mã thoát và JobRepository |
| Job đã xong nhưng JVM manager không kết thúc | Thread pool launch còn thread non-daemon, context chưa đóng | Bật `closecontextEnabled=true`, bean executor Spring-managed, xem shutdown |
| Pod bị kill giữa shutdown | Termination grace period quá ngắn hoặc callback chờ lâu | Chỉnh timeout shutdown/termination, thiết kế recovery |
| Retry tạo dữ liệu trùng | Worker ghi ngoài transaction/idempotency thiếu | Unique business key, retry an toàn, outbox cho external side effects |

**Không nên:** khắc phục bằng `System.exit(0)` ngay khi gửi lệnh tạo worker, vì làm mất khả năng tổng hợp kết quả và có thể báo thành công giả. Cũng không nên tự sửa `BATCH_STEP_EXECUTION.STATUS` từ `STARTED` thành `COMPLETED` để “giải phóng” phân vùng.

## 12. Chạy lại sau lỗi, gián đoạn và xử lý trùng

Spring Batch hỗ trợ **restart** của Job thất bại, và theo quy tắc phân vùng, những step đã hoàn tất được nhận diện đúng sẽ **không cần chạy lại**; các step lỗi có thể được chạy lại theo cấu hình restart. Điều này đòi hỏi metadata JobRepository còn nguyên và nhận diện `JobInstance`/partition nhất quán.

Tuy nhiên, worker là tiến trình độc lập:

1. Manager tạo `StepExecution` và ra lệnh launch.
2. Worker có thể commit dữ liệu nghiệp vụ.
3. Worker hoặc manager bị kill trước khi JobRepository ghi trạng thái cuối.
4. Khi restart, framework có thể cần xử lý lại một partition có trạng thái chưa hoàn tất.

**Yêu cầu bắt buộc:** worker phải **idempotent** hoặc có checkpoint/transaction phù hợp. Một partition xử lý lại không được gửi lại thanh toán, email hoặc ghi thêm kết quả trùng mà không có kiểm soát.

Các cơ chế đi kèm:

- Chia phân vùng theo **business range/snapshot** ổn định, không phụ thuộc `TASK_EXECUTION_ID`.
- Chọn writer có **unique key**, UPSERT có điều kiện hoặc retry logic theo work key.
- Nếu worker sử dụng chunk reader, bảo đảm `ExecutionContext` và `ItemStream` được cấu hình cho restart.
- Nếu side effect ở ngoài DB, dùng idempotency key/outbox hoặc cơ chế đối soát.
- Chống đồng thời hai worker xử lý cùng một partition sau timeout khi chủ cũ có thể vẫn đang chạy; cân nhắc lease/fencing.
- Phân biệt timeout launch, timeout manager chờ job và deadline nghiệp vụ ở worker.

## 13. Bài thực hành: so sánh khởi chạy tuần tự và bất đồng bộ

Chuẩn bị môi trường thử nghiệm có manager/worker artifact, `TaskLauncher` hợp lệ, database dùng chung và bảng nghiệp vụ đủ nhỏ để kiểm chứng. Không cần dùng dữ liệu thật hoặc cố tình kill production pod.

### Thực hành A — Khởi chạy tuần tự

1. Cấu hình `DeployerPartitionHandler` **không truyền executor tùy chỉnh** theo API phiên bản đang dùng.
2. Chạy một job chia bốn phân vùng và ghi lại thời điểm gọi launcher cho từng partition.
3. Đo khoảng thời gian từ khi manager bắt đầu launch đến khi tất cả worker được tạo.
4. Tra cứu JobRepository để biết thời điểm các partition thật sự bắt đầu và kết thúc.
5. Xác nhận kết quả nghiệp vụ không trùng và job có trạng thái đúng.

### Thực hành B — Khởi chạy bất đồng bộ

1. Tạo `ThreadPoolTaskExecutor` với `corePoolSize=2`, `maxPoolSize=2`, queue hữu hạn.
2. Truyền executor vào constructor `DeployerPartitionHandler`.
3. Giữ `maxWorkers=2` và `gridSize=4`; chạy lại trên tập nguồn mới/snapshot mới để so sánh công bằng.
4. Đối chiếu log tên thread `partition-launch-*` với thời điểm yêu cầu tạo worker.
5. Xác nhận thời gian gửi launch có thể giảm, nhưng **manager chỉ kết thúc job sau khi đã nhận kết quả phân vùng**.
6. Giảm `maxWorkers=1` để quan sát hiệu ứng giới hạn worker thực, tách khỏi số thread gửi launch.

### Thực hành C — Đóng executor

1. Bật `spring.cloud.task.closecontextEnabled=true` cho manager.
2. Giữ `setWaitForTasksToCompleteOnShutdown(true)` và cấu hình thời gian chờ hữu hạn.
3. Chạy Job bình thường, xác nhận JobRepository đã có kết quả cuối.
4. Quan sát manager đóng Spring context và process kết thúc; kiểm tra không còn thread pool giữ JVM.
5. Thử tắt `closecontextEnabled` trong lab để thấy khác biệt khi executor còn thread sống; **không lấy ví dụ lab làm bảo đảm rằng false luôn làm JVM treo**.
6. Quan sát riêng worker process kết thúc sau `workerStep`; nếu worker vẫn sống, điều tra context hoặc thread nền của worker.

### Thực hành D — Lỗi có kiểm soát

1. Cấu hình một worker cố ý ném exception khi gặp dải khóa cụ thể trong môi trường lab.
2. Kiểm tra `BATCH_STEP_EXECUTION` của phân vùng đó chuyển sang thất bại trên đường lifecycle hợp lệ.
3. Kiểm tra trạng thái manager Job, `EXIT_CODE` của task và log worker.
4. Khôi phục code hoặc dữ liệu lỗi và restart đúng `JobInstance` theo quy tắc Batch.
5. Xác nhận phân vùng đã hoàn tất không tạo kết quả trùng; kết quả cuối khớp phạm vi nguồn.

### Checklist đạt yêu cầu

- [ ] Nêu được **bất đồng bộ ở lời gọi launch** khác với **worker xử lý song song**.
- [ ] Có `TaskLauncher` thực sự cho hạ tầng và worker Resource hợp lệ.
- [ ] Manager/worker trỏ tới **cùng JobRepository** và TaskRepository phù hợp.
- [ ] `Partitioner` sinh các dải không giao nhau, có nguồn đã chốt.
- [ ] `gridSize`, `maxWorkers` và thread pool được cấu hình và đo riêng.
- [ ] `DeployerPartitionHandler` nhận `ThreadPoolTaskExecutor` do Spring quản lý.
- [ ] Worker có `DeployerStepExecutionHandler` và bean `workerStep` đúng tên.
- [ ] Worker không tự chạy Batch Job ngoài ý muốn khi nhận StepExecution.
- [ ] Manager chỉ kết thúc sau khi giám sát/tổng hợp trạng thái các phân vùng.
- [ ] `closecontextEnabled=true` giúp đóng context và executor sau vòng đời task.
- [ ] Có timeout cho manager, worker, shutdown và quy trình cancel/recovery.
- [ ] Dữ liệu đích có idempotency hoặc transaction/checkpoint phục vụ restart.
- [ ] Có thể tra cứu Batch JobExecution/StepExecution và TaskExecution tương ứng.
- [ ] Đã thử trường hợp lỗi, worker timeout, task bị ngắt và khôi phục an toàn.

## 14. Ghi nhớ

Trong **Spring Cloud Task remote partitioning**, `DeployerPartitionHandler` có thể nhận **`ThreadPoolTaskExecutor`** để **khởi chạy các worker bất đồng bộ**, giảm độ trễ gửi yêu cầu triển khai trên những hạ tầng tạo container chậm. Đây là khả năng riêng với việc worker xử lý dữ liệu song song và **không miễn trách nhiệm chờ/tổng hợp kết quả `StepExecution` trong JobRepository**.

Vì executor tạo thread có thể giữ manager JVM sống, cần **Spring-managed executor**, chính sách shutdown hữu hạn và `spring.cloud.task.closecontextEnabled=true` để đóng context khi task hoàn tất. Phải kiểm tra cả ba lớp: **JobRepository** (phân vùng và restart), **TaskRepository** (vòng đời process) và **dữ liệu nghiệp vụ thật**. Không coi launch thành công là xử lý thành công, cũng không để đóng thread pool sớm làm đứt chu trình giám sát.

### Tài liệu tham khảo

- [Spring Cloud Task Reference — Asynchronously launch remote batch partitions](https://docs.spring.io/spring-cloud-task/docs/current/reference/htmlsingle/#_asynchronously_launch_remote_batch_partitions)
- [Spring Cloud Task — DeployerPartitionHandler Javadoc](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/batch/partition/DeployerPartitionHandler.html)
- [Spring Cloud Task — DeployerStepExecutionHandler Javadoc](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/batch/partition/DeployerStepExecutionHandler.html)
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
