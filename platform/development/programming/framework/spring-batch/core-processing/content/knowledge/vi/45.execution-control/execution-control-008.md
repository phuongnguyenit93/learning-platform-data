# `JobRegistry` tìm job trong Spring Batch

Trong một ứng dụng Spring Batch có nhiều job, thành phần điều khiển thường không muốn phụ thuộc trực tiếp vào từng bean `Job`: scheduler nhận tên `importOrders`, trang vận hành yêu cầu chạy `archiveLogs`, hoặc một dịch vụ cần liệt kê các job có thể khởi chạy. **`JobRegistry`** cung cấp một nơi đăng ký và tìm các **định nghĩa job đang có trong ứng dụng** theo tên, nhờ đó tầng điều khiển có thể làm việc với một `Job` được chọn tại runtime.

Ví dụ ý tưởng:

```text
Scheduler / CLI / API: "Chạy job importOrders"
                 |
                 v
           JobRegistry
          getJob("importOrders")
                 |
                 v
          Job importOrders
                 |
        +--------+---------+
        |                  |
        v                  v
    JobLauncher         JobOperator
   run(job, params)   quản lý việc chạy
        |                  |
        +--------+---------+
                 v
          JobRepository
        lưu JobExecution
```

**Điểm quan trọng:** `JobRegistry` giúp **tìm định nghĩa `Job`**, không lưu lịch sử chạy job và không tự thực thi job. Việc chạy job thuộc `JobLauncher`/`JobOperator`; lịch sử `JobInstance`, `JobExecution` và `StepExecution` thuộc `JobRepository`, có thể được truy vấn qua `JobExplorer`.

## 1. Phân biệt `JobRegistry` với các thành phần điều khiển khác

| Thành phần | Trả lời câu hỏi | Dữ liệu được quản lý |
| --- | --- | --- |
| `Job` | Công việc batch này gồm những step/flow và quy tắc nào? | Định nghĩa quy trình thực thi |
| `JobRegistry` | Hiện tại có thể tìm định nghĩa job nào theo tên? | Các job được đăng ký trong runtime |
| `JobLauncher` | Làm sao khởi chạy một `Job` với `JobParameters`? | Khởi tạo/điều phối việc thực thi |
| `JobOperator` | Làm sao vận hành job, start/stop/restart theo API quản trị? | Các thao tác điều khiển, dùng nhiều thành phần Batch bên dưới |
| `JobRepository` | Lần chạy nào đã được ghi nhận và có trạng thái gì? | Metadata bền vững về job/step execution |
| `JobExplorer` | Làm sao đọc lại metadata đã lưu? | Truy vấn `JobInstance`, `JobExecution`, `StepExecution` |
| `ApplicationContext` | Bean Spring nào được định nghĩa trong context này? | Vòng đời và dependency của bean Spring |

Ba tình huống giúp thấy sự khác biệt:

1. Job `importOrders` đã từng chạy hôm qua, nhưng ứng dụng hiện tại không còn đăng ký định nghĩa job đó. `JobExplorer` vẫn có thể tìm thấy **lịch sử**, còn `JobRegistry.getJob("importOrders")` không tìm thấy **định nghĩa** để chạy lại.
2. Job `archiveLogs` mới được thêm vào application context và được đăng ký. `JobRegistry` đã có thể trả về `Job` này, dù chưa có `JobExecution` nào trong database.
3. Hai lần chạy cùng `Job` với `JobParameters` khác nhau có hai `JobInstance`; trong registry vẫn chỉ cần một định nghĩa `Job` theo tên.

`JobRegistry` hoạt động như một danh bạ ở **mức cấu hình runtime**. Đừng dùng nó để xác định job đã hoàn tất hay đang chạy; hãy lấy trạng thái từ metadata thực thi.

## 2. API `JobRegistry` ở Spring Batch 5.2.x

Trong **Spring Batch 5.2.x**, `JobRegistry` ở package `org.springframework.batch.core.configuration`. Nó mở rộng các giao diện tra cứu `JobLocator` và `ListableJobLocator`.

Các phương thức quan trọng:

| Phương thức | Kết quả | Ghi chú |
| --- | --- | --- |
| `getJob(String name)` | Trả về `Job` theo tên | Ném `NoSuchJobException` nếu không có |
| `getJobNames()` | Danh sách/tập các tên đã đăng ký | Không phải các job từng chạy trong repository |
| `register(JobFactory factory)` | Đăng ký định nghĩa thông qua factory | Ném `DuplicateJobException` nếu trùng tên |
| `unregister(String jobName)` | Bỏ đăng ký tên job | Không xóa các bản ghi `JobExecution` |

Triển khai thông dụng là **`MapJobRegistry`** (`org.springframework.batch.core.configuration.support.MapJobRegistry`), lưu ánh xạ tên job đến factory trong bộ nhớ và hỗ trợ truy cập từ nhiều thread. Ở Spring Batch 5.2, `register(...)` nhận **`JobFactory`**, không nhận trực tiếp `Job`. Khi đã có một object `Job`, có thể bọc nó bằng `ReferenceJobFactory`.

Ví dụ thao tác độc lập với Spring application context:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.configuration.support.MapJobRegistry;
import org.springframework.batch.core.configuration.support.ReferenceJobFactory;
import org.springframework.batch.core.job.SimpleJob;
import org.springframework.batch.core.launch.NoSuchJobException;

import java.util.Set;

public class JobRegistryLookupExample {

    public static void main(String[] args) throws Exception {
        JobRegistry registry = new MapJobRegistry();

        // SimpleJob chỉ để minh họa việc đăng ký và tìm.
        // Muốn chạy thật cần cấu hình các step và hạ tầng Batch.
        Job importOrders = new SimpleJob("importOrders");
        Job archiveLogs = new SimpleJob("archiveLogs");

        registry.register(new ReferenceJobFactory(importOrders));
        registry.register(new ReferenceJobFactory(archiveLogs));

        Set<String> names = registry.getJobNames();
        System.out.println(names);  // Chứa importOrders, archiveLogs.

        Job found = registry.getJob("importOrders");
        System.out.println(found.getName()); // importOrders

        registry.unregister("archiveLogs");
        System.out.println(registry.getJobNames()); // Chỉ còn importOrders.

        try {
            registry.getJob("archiveLogs");
        } catch (NoSuchJobException ex) {
            System.out.println("Job chưa được đăng ký: archiveLogs");
        }
    }
}
```

Đoạn trên minh họa **đăng ký, tìm, liệt kê và bỏ đăng ký**. Không có job nào được thực thi, cũng không có `JobRepository` nào được sử dụng. `getJobNames()` không bảo đảm một thứ tự hiển thị cố định; khi làm danh sách cho UI hoặc CLI, nên sắp xếp trước khi hiển thị.

### Lỗi trùng tên khi `register`

Registry yêu cầu tên job không bị trùng:

```java
JobRegistry registry = new MapJobRegistry();
Job first = new SimpleJob("importOrders");
Job another = new SimpleJob("importOrders");

registry.register(new ReferenceJobFactory(first));

// Ném DuplicateJobException vì tên đã tồn tại:
registry.register(new ReferenceJobFactory(another));
```

`DuplicateJobException` là lỗi đăng ký định nghĩa tại runtime. Nó khác với `JobInstanceAlreadyCompleteException`, vốn liên quan đến lịch sử thực thi một `JobInstance` đã hoàn tất trong `JobRepository`.

## 3. Cấu hình `JobRegistry` cùng `@EnableBatchProcessing`

Trong Spring Batch 5.2.x, cấu hình dựa trên `@EnableBatchProcessing` cung cấp `JobRegistry` và hạ tầng đăng ký các singleton `Job` vào registry. Khi ứng dụng đã sử dụng cấu hình Batch chuẩn, thông thường ta **inject registry hiện có**, không tạo thêm một `MapJobRegistry` thứ hai rồi tự hỏi vì sao danh sách job rỗng.

Ví dụ Spring configuration tạo một job tối giản có thể thực thi. Ví dụ giả định ứng dụng đã cấu hình hợp lệ `DataSource`, `JobRepository` và `PlatformTransactionManager` cho Spring Batch:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing
public class ImportOrdersBatchConfig {

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager) {
        return new StepBuilder("importOrdersStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    System.out.println("Processing orders...");
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {
        return new JobBuilder("importOrders", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

Spring bean có tên `importOrdersJob`, còn `Job` có tên logic **`importOrders`** do `new JobBuilder("importOrders", ...)` thiết lập. Vì các cơ chế đăng ký và group naming có thể ảnh hưởng tên công khai, khi điều khiển qua registry cần kiểm tra **tên thực tế do `getJobNames()` trả về**, rồi dùng nhất quán tên đó ở scheduler hoặc API. Trong cấu hình dự án, nên đặt tên bean và tên job đủ rõ ràng để tránh nhầm lẫn.

Đọc registry từ bean Spring:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.launch.NoSuchJobException;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class AvailableJobs {

    private final JobRegistry jobRegistry;

    public AvailableJobs(JobRegistry jobRegistry) {
        this.jobRegistry = jobRegistry;
    }

    public List<String> names() {
        return jobRegistry.getJobNames().stream()
                .sorted()
                .toList(); // Java 16+
    }

    public Job require(String name) throws NoSuchJobException {
        return jobRegistry.getJob(name);
    }
}
```

Vòng đời phổ biến:

```text
Spring khởi tạo application context
        |
        +--> Tạo các bean Job
        |
        +--> Thành phần đăng ký đưa Job vào JobRegistry
        |
        v
ApplicationContext sẵn sàng
        |
        v
Service/scheduler gọi getJobNames() hoặc getJob(name)
```

Trong Spring Batch 5.2, cơ chế phù hợp cho việc tự đăng ký là **`JobRegistrySmartInitializingSingleton`**: nó chạy sau khi các singleton đã được khởi tạo, giúp hạn chế tình huống bean được tạo quá sớm. Nếu ứng dụng **không** dùng hạ tầng Batch tạo sẵn registry và phải cấu hình thủ công, có thể khai báo:

```java
@Bean
JobRegistry jobRegistry() {
    return new MapJobRegistry();
}

@Bean
JobRegistrySmartInitializingSingleton jobRegistrar(JobRegistry jobRegistry) {
    return new JobRegistrySmartInitializingSingleton(jobRegistry);
}
```

Hai import tương ứng là `org.springframework.batch.core.configuration.support.MapJobRegistry` và `org.springframework.batch.core.configuration.support.JobRegistrySmartInitializingSingleton`. Đoạn này áp dụng cho **context chưa tự cung cấp các bean tương đương**; không thêm nguyên xi vào một context đang dùng `@EnableBatchProcessing` rồi vô tình tạo trùng bean/đăng ký trùng job. `JobRegistryBeanPostProcessor` là cơ chế cũ, đã **deprecated từ Spring Batch 5.2**, và không nên dùng đồng thời với `JobRegistrySmartInitializingSingleton`.

## 4. Tra cứu theo tên trước khi chạy job

Một trường hợp thực tế của mục **Execution control** là service nhận tên job từ scheduler hoặc một hệ thống vận hành. Service có thể dùng registry để phân giải job, sau đó dùng `JobLauncher` thực thi với tham số rõ ràng:

```java
import java.time.LocalDate;
import java.util.Set;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.stereotype.Service;

@Service
public class NamedJobDispatcher {

    private final JobRegistry registry;
    private final JobLauncher launcher;

    public NamedJobDispatcher(JobRegistry registry, JobLauncher launcher) {
        this.registry = registry;
        this.launcher = launcher;
    }

    // Ví dụ Spring Batch 5.2.x.
    public JobExecution launch(String jobName, LocalDate businessDate)
            throws Exception {
        // Chỉ cho phép những job được expose qua interface này.
        if (!Set.of("importOrders").contains(jobName)) {
            throw new IllegalArgumentException("Job is not allowed: " + jobName);
        }

        Job job = registry.getJob(jobName); // Có thể ném NoSuchJobException.

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString())
                .toJobParameters();

        return launcher.run(job, parameters);
    }
}
```

Từ ví dụ có thể tách rõ trách nhiệm:

1. **Chọn job:** `getJob(jobName)` xác định định nghĩa có đang được đăng ký hay không.
2. **Xác định lần chạy:** `JobParameters` định nghĩa đầu vào và những giá trị identifying dùng cho `JobInstance`.
3. **Điều khiển chạy:** `JobLauncher.run(...)` bắt đầu hoặc điều phối lần thực thi và dùng `JobRepository` quản lý metadata.
4. **Theo dõi:** dùng `JobExecution` trả về hoặc truy vấn qua `JobExplorer`/`JobRepository`. Nếu launcher thực thi bất đồng bộ, `JobExecution` trả về có thể chưa có trạng thái cuối cùng.

Ví dụ để `throws Exception` cho dễ tập trung vào vai trò của registry. Trong ứng dụng thực tế, nên xử lý các lỗi Batch cụ thể như `NoSuchJobException`, `JobInstanceAlreadyCompleteException`, `JobExecutionAlreadyRunningException`, `JobRestartException` và lỗi tham số không hợp lệ theo hợp đồng API của hệ thống điều khiển.

Vì tên job có thể đến từ bên ngoài, **không nên phơi toàn bộ registry thành endpoint cho phép khởi chạy tùy ý**. Một API vận hành thực tế phải kiểm tra quyền, giới hạn tập job được phép chạy và validate `JobParameters`; việc job tồn tại trong registry không tự chứng minh người gọi được phép chạy nó.

### Tra cứu khác gì với restart?

Giả sử job `importOrders` thất bại. Muốn restart qua API điều khiển, cần cả hai thông tin:

- Định nghĩa `Job` **vẫn có thể tìm thấy** trong runtime (ví dụ từ registry).
- Metadata lần chạy thất bại **vẫn còn** trong `JobRepository`, và job/step được thiết kế cho restart.

Nếu job đã bị bỏ khỏi registry nhưng execution thất bại vẫn tồn tại trong database, lệnh restart dựa trên tên job có thể không tìm được định nghĩa cần thực thi. Ngược lại, chỉ có định nghĩa trong registry không đủ tái tạo checkpoint của lần chạy cũ.

## 5. Dùng `JobOperator` khi cần điều khiển vận hành

Khi cần nhiều thao tác hơn `JobLauncher.run(...)` — chẳng hạn start, stop, restart, xem thông tin về executions — Spring Batch cung cấp `JobOperator`.

Trong **Spring Batch 5.2.x**, một số API của `JobOperator` cho phép vận hành bằng tên job:

```java
// Ví dụ ở tầng dịch vụ đã inject JobOperator.
Set<String> available = jobOperator.getJobNames();

Properties parameters = new Properties();
parameters.setProperty("businessDate", "2025-01-15");

Long executionId = jobOperator.start("importOrders", parameters);
```

Đoạn trên cần import `java.util.Set`, `java.util.Properties` và bean `org.springframework.batch.core.launch.JobOperator`. Hình thức chuyển đổi `Properties` thành `JobParameters` được định nghĩa bởi API tương ứng; nếu application có yêu cầu kiểu dữ liệu hoặc identifying flags đặc biệt, cần cung cấp tham số đúng định dạng cho phiên bản và converter đang dùng. Cần dùng `try/catch` hoặc khai báo các exception được `start(...)` phát sinh.

Trong cấu hình mặc định của Spring Batch 5.2, `JobOperator` có thể dùng `JobRegistry` để phân giải tên job và kết hợp `JobExplorer`, `JobRepository`, `JobLauncher` cho các thao tác tương ứng. Vì vậy, **job có trong `JobRepository` nhưng thiếu trong `JobRegistry`** là một tình huống cần xem xét khi `start`/`restart` theo tên thất bại.

> Ở Spring Batch 6.x, các overload cũ của `JobOperator` như `start(String, Properties)` đã được đánh dấu deprecated; nên sử dụng API điều khiển nhận `Job` và `JobParameters`, kết hợp `JobRegistry` để tìm `Job` nếu đầu vào ban đầu là tên. Chi tiết về phiên bản ở mục 9.

## 6. Đăng ký động và các module job độc lập

Một ứng dụng Batch lớn có thể gom nhiều nhóm job:

```text
ApplicationContext chính
  |
  +-- JobRegistry (tập trung)
  |
  +-- Child context: sales
  |     +-- importOrders Job
  |     +-- reader, writer, step...
  |
  +-- Child context: finance
        +-- reconcilePayments Job
        +-- reader, writer, step...
```

Mỗi context con có thể dùng lại các **tên bean nội bộ** như `reader` hoặc `writer` mà không đụng nhau, trong khi registry tập trung quản lý các job công khai. Spring Batch 5.2 có `AutomaticJobRegistrar` để tạo/quản lý các context con bằng `ApplicationContextFactory` và `JobLoader`, rồi đăng ký job từ các context ấy.

Trường hợp này có ích khi:

- Các module triển khai định nghĩa job độc lập và được lắp vào cùng một ứng dụng điều khiển.
- Một nhóm job được nạp hoặc gỡ theo vòng đời application context con.
- Hệ thống có nhiều job và cần một điểm tra cứu nhất quán thay vì tự quét bean ở nhiều context.

Không nên hiểu `JobRegistry` là dịch vụ discovery phân tán. `MapJobRegistry` là **registry trong một process/application context**; việc một instance của ứng dụng đăng ký job không tự đồng bộ danh sách sang instance khác. Nếu các node triển khai job khác nhau, scheduler/gateway cần định tuyến đúng node hoặc có một hệ thống điều phối bên ngoài.

Với các context nhiều nhóm, cần có quy tắc đặt tên để tránh `DuplicateJobException`. Những cơ chế group naming ở lớp đăng ký có thể giúp phân biệt nguồn job, nhưng **tên dùng để tìm job phải khớp tên thực tế đã đăng ký**, không thể tự đoán rằng tên bean hoặc nhãn module luôn bằng job name trong registry.

### Vòng đời đăng ký và gỡ đăng ký

```text
Context/module được khởi tạo
       |
       v
Tạo bean định nghĩa Job
       |
       v
register(...) -> JobRegistry có tên job
       |
       v
Tầng điều khiển tra cứu và khởi chạy khi phù hợp
       |
       v
Context/module kết thúc hoặc được gỡ
       |
       v
unregister(...) -> tên job không còn trong registry
```

`unregister` chỉ thay đổi khả năng **tra cứu định nghĩa job trong runtime**. Nó không tự xóa lịch sử và không phải lệnh dừng job đang chạy. Muốn dừng một execution đang hoạt động, dùng cơ chế điều khiển của Spring Batch và chờ batch xử lý tín hiệu dừng phù hợp. Đừng gỡ job đang chạy với giả định thao tác đó sẽ rollback hoặc cancel tiến trình.

## 7. Kiểm thử việc tìm job và xử lý lỗi

Với việc chỉ cần kiểm tra nghiệp vụ đăng ký/tra cứu, một unit test có thể dùng `MapJobRegistry` trực tiếp, không cần database hay chạy job thật. Ví dụ JUnit Jupiter dành cho **Spring Batch 5.2.x**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.DuplicateJobException;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.configuration.support.MapJobRegistry;
import org.springframework.batch.core.configuration.support.ReferenceJobFactory;
import org.springframework.batch.core.job.SimpleJob;
import org.springframework.batch.core.launch.NoSuchJobException;

import static org.junit.jupiter.api.Assertions.*;

class JobRegistryTest {

    @Test
    void findsJobByNameAndUnregistersIt() throws Exception {
        JobRegistry registry = new MapJobRegistry();
        Job job = new SimpleJob("importOrders");

        registry.register(new ReferenceJobFactory(job));

        assertTrue(registry.getJobNames().contains("importOrders"));
        assertSame(job, registry.getJob("importOrders"));

        registry.unregister("importOrders");

        assertFalse(registry.getJobNames().contains("importOrders"));
        assertThrows(NoSuchJobException.class,
                () -> registry.getJob("importOrders"));
    }

    @Test
    void rejectsDuplicateJobNames() throws Exception {
        JobRegistry registry = new MapJobRegistry();

        registry.register(
                new ReferenceJobFactory(new SimpleJob("importOrders")));

        assertThrows(DuplicateJobException.class, () ->
                registry.register(
                        new ReferenceJobFactory(new SimpleJob("importOrders"))));
    }
}
```

`SimpleJob` trong test chỉ làm nhiệm vụ chứa tên để kiểm tra việc tra cứu. Nó chưa có cấu hình step để khởi chạy một luồng Batch có ý nghĩa. Khi cần kiểm thử `JobLauncher` hoặc `JobOperator` thực sự chạy đúng job, hãy chuyển sang integration test có job/step và `JobRepository` test phù hợp.

Với Spring context, một bài test đơn giản khác là inject `JobRegistry` và kiểm tra tên đã xuất hiện **sau khi context khởi tạo**. Điều này giúp phát hiện cấu hình thiếu thành phần tự đăng ký, đăng ký nhầm registry hoặc xung đột tên job.

Các trường hợp kiểm thử nên cân nhắc:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tên đã đăng ký | Trả về đúng định nghĩa `Job` |
| Tên không tồn tại | Báo lỗi rõ ràng/giá trị không tìm thấy theo đúng phiên bản |
| Hai job trùng tên | Đăng ký bị từ chối |
| Bỏ đăng ký rồi tra cứu | Không còn tìm thấy |
| Context có nhiều job | Liệt kê đúng các tên thực sự có thể tra cứu |
| Chạy job qua service | Tìm đúng job, truyền đúng `JobParameters`; trạng thái được lưu ở repository |

## 8. Sự cố thường gặp khi `JobRegistry` không tìm thấy job

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `NoSuchJobException` ở Spring Batch 5.x | Tên không có trong registry | In `getJobNames()` để kiểm tra tên thực tế; xác nhận bean job đã đăng ký |
| Registry rỗng dù Spring có bean `Job` | Tạo một `MapJobRegistry` riêng chưa được populate, hoặc đăng ký sai context | Inject registry do Batch cung cấp; cấu hình registrar đúng nơi |
| `DuplicateJobException` lúc khởi tạo | Hai định nghĩa dùng cùng tên, hoặc hai thành phần cố đăng ký một job | Sửa quy tắc đặt tên; không dùng đồng thời các cơ chế đăng ký trùng lặp |
| Tên bean `importOrdersJob` tìm thấy nhưng `importOrders` không tìm thấy, hoặc ngược lại | Nhầm lẫn tên bean Spring, tên logic của `Job` và group naming | Lấy danh sách từ `getJobNames()`; thống nhất tên công khai |
| Job có lịch sử trong database nhưng không tìm được định nghĩa | `JobRepository` còn metadata từ deployment cũ, registry hiện tại không có job | Kiểm tra version/deployment và registration; phục hồi định nghĩa tương thích nếu cần restart |
| `JobInstanceAlreadyCompleteException` sau khi đã tìm thấy job | Đang chạy lại cùng job name và identifying parameters của instance đã hoàn tất | Phân biệt việc tìm definition với chính sách tạo/restart `JobInstance` |
| Job không chạy trên node đang nhận yêu cầu | Registry của node này không chứa job được triển khai ở node khác | Điều phối/định tuyến đúng nơi có định nghĩa, không coi registry là kho phân tán |
| Đã `unregister` mà execution vẫn chạy | Bỏ đăng ký không phát lệnh dừng | Dùng API stop của Batch; kiểm tra trạng thái execution |
| Danh sách tên hiển thị thay đổi thứ tự | `getJobNames()` không có hợp đồng sắp xếp | Sắp xếp tên trước khi xuất ra UI/CLI |

Để chẩn đoán, nên kiểm tra theo thứ tự **context đã nạp job chưa → cơ chế đăng ký có hoạt động không → registry được inject có đúng instance không → tên thực tế trong registry là gì → lỗi còn lại thuộc job launch hay repository**. Cách phân tách này tránh nhầm lỗi tra cứu cấu hình với lỗi điều khiển execution.

## 9. Khác biệt đáng chú ý giữa Spring Batch 5.2 và 6.x

Spring Batch 6 thay đổi API `JobRegistry`, vì vậy mã tra cứu/đăng ký cần theo đúng phiên bản.

| Khía cạnh | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| `getJob(name)` khi không tìm thấy | Ném `NoSuchJobException` | Trả về `null` (API `@Nullable`) |
| Đăng ký bằng tay | `register(JobFactory)`; thường dùng `new ReferenceJobFactory(job)` | `register(Job)` trực tiếp |
| `JobLocator`/`ListableJobLocator` | Là các interface kế thừa bởi `JobRegistry` | Các interface cũ được deprecated, ưu tiên `JobRegistry` trực tiếp |
| `MapJobRegistry` | Cần cơ chế populate job, như `JobRegistrySmartInitializingSingleton` | Tự đăng ký các bean `Job` trong `ApplicationContext` bằng cơ chế `SmartInitializingSingleton` |
| `JobRegistrySmartInitializingSingleton` | Là giải pháp thay cho `JobRegistryBeanPostProcessor` | Deprecated; thường chỉ cần `MapJobRegistry` bean |
| `JobOperator.start(String, Properties)` | Hỗ trợ vận hành theo tên | Deprecated, ưu tiên API nhận `Job` và `JobParameters` |

Ví dụ API tra cứu và đăng ký bằng tay ở **Spring Batch 6.x**:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.configuration.support.MapJobRegistry;
import org.springframework.batch.core.job.SimpleJob;

JobRegistry registry = new MapJobRegistry();
Job job = new SimpleJob("importOrders");

registry.register(job); // 6.x: nhận Job trực tiếp.

Job resolved = registry.getJob("importOrders");
if (resolved == null) {
    throw new IllegalArgumentException("Unknown job: importOrders");
}

System.out.println(resolved.getName());
```

Ví dụ này chỉ minh họa tra cứu; để chạy job thực tế vẫn cần cấu hình step và hạ tầng thực thi. `SimpleJob` ở Spring Batch 6 thuộc `org.springframework.batch.core.job.SimpleJob`; các API của những đối tượng Batch khác có thể đã di chuyển package hoặc thay đổi chữ ký, vì vậy cần theo đúng dependency và tài liệu của project.

Với Spring Batch 6, `MapJobRegistry` trong Spring context có thể tự nhận những `Job` bean khi các singleton đã sẵn sàng. Với một registry được `new` trực tiếp ngoài Spring context như ví dụ, cần gọi `register(job)` thủ công vì không có lifecycle Spring để tự quét bean. Nếu thay bằng một triển khai `JobRegistry` tùy chỉnh, cũng cần tự bảo đảm cơ chế populate tương thích.

**Không sao chép mã 5.x và chỉ đổi dependency thành 6.x**: lệnh `register(new ReferenceJobFactory(job))`, giả định `getJob` ném `NoSuchJobException`, hoặc cấu hình `JobRegistrySmartInitializingSingleton` từ ví dụ cũ có thể không còn phù hợp. Tách rõ đoạn code theo phiên bản sẽ làm các lỗi migration dễ nhận biết hơn.

## 10. Thực hành thiết kế cho tầng Execution control

Khi sử dụng `JobRegistry` trong một ứng dụng điều phối batch nhiều job, nên giữ hợp đồng rõ ràng:

1. **Tên job là hợp đồng:** chọn tên ổn định, duy nhất, dễ tra cứu; công khai tên được registry trả về. Thay tên job có thể ảnh hưởng scheduler và quy trình restart.
2. **Đăng ký trước khi điều khiển:** chỉ chấp nhận yêu cầu chạy sau khi context/registrar đã sẵn sàng; nếu registry được nạp động, có thể có giai đoạn job chưa xuất hiện.
3. **Tách lookup khỏi launch:** một hàm tìm `Job` và một hàm validate/khởi chạy giúp kiểm tra lỗi rõ ràng.
4. **Không dùng registry làm monitoring store:** trạng thái `STARTED`, `FAILED`, `COMPLETED`, lịch sử chạy và restart lấy từ `JobRepository`/`JobExplorer`.
5. **Không nhầm tên job với instance:** cùng một tên job có thể có rất nhiều lần chạy với các bộ `JobParameters` khác nhau.
6. **Giới hạn quyền điều khiển:** không cho người dùng tự chọn bất kỳ job nội bộ nào chỉ vì nó nằm trong registry; phân quyền theo đối tượng và kịch bản vận hành.
7. **Theo dõi trạng thái khi chạy bất đồng bộ:** kết quả trả về khi gọi launcher không luôn là trạng thái cuối cùng; lấy kết quả cuối từ metadata.
8. **Quản lý đăng ký theo vòng đời:** khi gỡ module/context con, dọn registration phù hợp, đồng thời quản lý các execution đang chạy bằng cơ chế riêng.

## 11. Tài liệu tham khảo

- [Spring Batch 5.2 — Advanced Metadata Usage: JobRegistry, AutomaticJobRegistrar, JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 API — JobRegistry](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/configuration/JobRegistry.html)
- [Spring Batch 5.2 API — MapJobRegistry](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/configuration/support/MapJobRegistry.html)
- [Spring Batch 5.2 API — JobRegistrySmartInitializingSingleton](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/configuration/support/JobRegistrySmartInitializingSingleton.html)
- [Spring Batch 5.2 API — JobOperator](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html)
- [Spring Batch 6 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch 6 API — JobRegistry](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/configuration/JobRegistry.html)
- [Spring Batch 6 API — MapJobRegistry](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/configuration/support/MapJobRegistry.html)

Khi một hệ thống cần **tìm job theo tên để quyết định điều khiển thực thi**, `JobRegistry` là điểm kết nối giữa cấu hình Batch và tầng vận hành. Hãy dùng registry để lấy định nghĩa `Job` đang khả dụng, dùng `JobLauncher`/`JobOperator` để chạy hoặc quản lý execution, và dùng `JobRepository`/`JobExplorer` để đọc lịch sử thực tế. Đồng thời phải phân biệt API Spring Batch 5.2 và 6.x, vì chính thao tác `getJob`/`register` đã thay đổi giữa hai dòng phiên bản.
