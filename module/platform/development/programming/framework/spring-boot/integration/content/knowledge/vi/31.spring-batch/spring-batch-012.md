# Nhiều job, chạy đồng thời và nhận diện trùng JobInstance

Một ứng dụng Spring Boot có thể chạy nhiều công việc Spring Batch: đồng bộ đơn hàng từ HTTP API, nhập dữ liệu từ cơ sở dữ liệu đối tác, đối soát thanh toán, tính báo cáo theo ngày và phát sự kiện kết quả lên broker. Khi có scheduler, HTTP endpoint, message consumer và nhiều replica cùng kích hoạt, hai câu hỏi xuất hiện: **job nào được phép chạy song song?** và **hai lệnh chạy có đại diện cho cùng một lần xử lý nghiệp vụ hay không?**

Spring Batch cung cấp `Job`, `JobParameters`, `JobInstance`, `JobExecution` và `JobRepository` để mô tả, lưu trạng thái và quyết định khả năng restart. Hiểu rõ các khái niệm này giúp tránh chạy lại báo cáo đã hoàn tất, trùng dữ liệu khi nhận event từ broker, và tranh chấp tài nguyên khi nhiều job cùng dùng database hoặc HTTP client.

Ví dụ xuyên suốt là hệ thống thương mại điện tử có hai job:

- `importOrdersJob`: nhập đơn hàng theo ngày nghiệp vụ (`businessDate`) và tenant.
- `reconcilePaymentsJob`: đối soát thanh toán cho cùng ngày, có thể chạy độc lập khi điều kiện dữ liệu cho phép.

Các ví dụ Java tập trung vào **Spring Boot 3.x với Spring Batch 5.x**; ở Spring Boot 4.x/Spring Batch 6.x, cần đối chiếu package và API của phiên bản đang được quản lý trước khi áp dụng nguyên code.

## 1. Phân biệt Job, JobInstance, JobExecution và StepExecution

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Job` | Định nghĩa công việc gồm tên, steps và chính sách restart | `importOrdersJob` |
| `JobParameters` | Dữ liệu đưa vào khi khởi chạy; một phần tham gia nhận diện instance | `businessDate=2026-11-20`, `tenantId=shop-a` |
| `JobInstance` | **Lần xử lý logic** được nhận diện bằng job name và các tham số identifying | Nhập đơn của `shop-a` cho ngày `2026-11-20` |
| `JobExecution` | **Một lần thử thực thi** của một `JobInstance` | Thử lần 1 FAILED, lần 2 COMPLETED |
| `StepExecution` | Một lần thực thi của một step trong một `JobExecution` | `loadOrdersStep` xử lý 5.000 bản ghi |
| `ExecutionContext` | Trạng thái có thể persist để checkpoint và restart | Trang cuối đã đọc, vị trí file, cursor cần khôi phục |
| `JobRepository` | Kho metadata lưu instance, execution, trạng thái và checkpoint | Các bảng `BATCH_JOB_*`, `BATCH_STEP_*` |

Công thức nền tảng:

~~~text
JobInstance identity = Job name + identifying JobParameters

JobInstance("importOrdersJob", businessDate=2026-11-20, tenantId=shop-a)
    ├── JobExecution #101: FAILED
    └── JobExecution #116: COMPLETED  (restart cùng instance)

JobInstance("importOrdersJob", businessDate=2026-11-21, tenantId=shop-a)
    └── JobExecution #117: COMPLETED  (instance khác)
~~~

Một `JobExecution` mới sau lỗi **không bắt buộc** đồng nghĩa một `JobInstance` mới. Spring Batch phân biệt “chạy lại để khôi phục” với “xử lý một tập dữ liệu logic mới” dựa trên identity và lịch sử execution.

~~~mermaid
flowchart TD
    A[Trigger: scheduler / HTTP / broker] --> B[Job name + identifying JobParameters]
    B --> C{JobInstance đã tồn tại?}
    C -->|Chưa| D[Tạo JobInstance mới]
    C -->|Có| E{Execution trước ở trạng thái nào?}
    E -->|COMPLETED| F[Từ chối chạy lại cùng instance]
    E -->|Đang chạy| G[Từ chối chạy đồng thời cùng instance]
    E -->|FAILED hoặc STOPPED| H[Kiểm tra có được restart]
    H -->|Có| I[Tạo JobExecution mới, khôi phục checkpoint]
    H -->|Không| J[Trả lỗi restart]
    D --> K[Chạy các Step]
    I --> K
~~~

Đây là mô hình logic tổng quát. Một lần khởi chạy còn có thể thất bại do parameters không hợp lệ, JobRepository bị lỗi, tình trạng `UNKNOWN` hoặc metadata chưa được phục hồi. Việc chạy có thể đồng bộ hoặc bất đồng bộ; kết quả từ lời gọi launch chưa chắc là trạng thái cuối của job.

## 2. Chọn identifying JobParameters theo khóa nghiệp vụ

Mặc định, một tham số trong `JobParametersBuilder` là **identifying**. Có thể truyền cờ `false` để tham số phục vụ quan sát mà không tạo instance mới.

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-20", true)
        .addString("tenantId", "shop-a", true)
        .addString("requestedBy", "scheduler", false)
        .addString("correlationId", "trace-abc", false)
        .toJobParameters();
~~~

Với `importOrdersJob`, hai tham số `businessDate` và `tenantId` tạo khóa nghiệp vụ. `requestedBy` và `correlationId` giúp theo dõi trigger; thay giá trị của chúng không biến một instance cũ thành instance mới.

| Lệnh chạy | Job name | Identifying parameters | Non-identifying parameters | Quan hệ |
| --- | --- | --- | --- | --- |
| A | `importOrdersJob` | date=20/11, tenant=A | requestedBy=scheduler | Instance X |
| B | `importOrdersJob` | date=20/11, tenant=A | requestedBy=HTTP | **Cùng instance X** |
| C | `importOrdersJob` | date=21/11, tenant=A | requestedBy=scheduler | Instance Y |
| D | `importOrdersJob` | date=20/11, tenant=B | requestedBy=scheduler | Instance Z |
| E | `reconcilePaymentsJob` | date=20/11, tenant=A | requestedBy=scheduler | Instance của job **khác** |

**Cách chọn khóa:** hãy tự hỏi “tập công việc nào phải có tối đa một `JobInstance` logic?”. Với file import, câu trả lời có thể là `tenantId + fileChecksum + schemaVersion`; với báo cáo ngày có thể là `tenantId + businessDate + reportType`. Nếu dữ liệu nguồn thay đổi nhưng identity không thay, một job đã COMPLETED có thể chặn việc tái xử lý dữ liệu mới. Ngược lại, nếu đưa thời gian hiện tại hoặc UUID ngẫu nhiên vào identifying parameters, *mỗi retry của cùng yêu cầu* lại tạo instance mới.

Không nên tạo tham số identifying là `System.currentTimeMillis()` chỉ để tránh `JobInstanceAlreadyCompleteException`. Cách đó loại bỏ khả năng chống trùng ở cấp instance. `RunIdIncrementer` hữu ích khi **chủ đích** muốn instance mới trong chuỗi lần chạy độc lập, nhưng phải được sử dụng theo hợp đồng nghiệp vụ, không làm cách chữa lỗi duplicate.

### 2.1. Chuẩn hóa khóa trước khi launch

Nên chuẩn hóa và kiểm tra:

1. Ngày nghiệp vụ theo múi giờ đã thỏa thuận; phân biệt `businessDate` với thời điểm job được kích hoạt.
2. Tenant, mã file, version và khoảng thời gian có định dạng ổn định; tránh `SHOP-A` và `shop-a` vô tình được coi khác nhau.
3. Không đưa password, token, dữ liệu cá nhân hoặc toàn bộ JSON payload vào JobParameters vì chúng được lưu trong metadata.
4. Chỉ đánh dấu `false` cho giá trị **không quyết định tập dữ liệu hoặc logic khôi phục**. Không thay đổi input cốt lõi khi restart cùng instance.
5. Nếu chấp nhận tái xử lý có chủ đích, thiết kế tham số identifying `revision` hoặc `sourceSnapshotId` rõ ràng và yêu cầu người vận hành phê duyệt theo quy trình.

JobParameters chỉ nhận diện execution; nó **không tự lọc dữ liệu**. ItemReader/Tasklet phải thực sự dùng những tham số để chọn dữ liệu đúng ngày và tenant. Một job dùng đúng key nhưng reader đọc toàn bộ bảng vẫn có thể gây xử lý trùng xuyên ngày.

## 3. Spring Boot có nhiều Job bean: tách định nghĩa khỏi kích hoạt

Khi Spring Boot tự cấu hình Spring Batch và chỉ có một `Job` bean, job đó thường được launcher chạy khi ứng dụng khởi động. Khi có nhiều job bean, phải chỉ định job cần chạy thông qua `spring.batch.job.name` nếu muốn hành vi launch khi startup. Đối với ứng dụng API hoặc worker luôn chạy, cách rõ ràng là **tắt launch tự động** và giao quyền khởi chạy cho scheduler, HTTP endpoint nội bộ hoặc message handler.

~~~yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

`initialize-schema: never` là ví dụ production nơi schema Batch đã được quản lý bằng migration. Ở môi trường thử nghiệm, có thể khởi tạo schema một lần bằng script phù hợp database/version; không để nhiều replica tự tạo hoặc xóa schema mỗi lần khởi động. Các thuộc tính khác hoặc vị trí auto-configuration có thể thay đổi theo Spring Boot version.

Nếu muốn chạy **một** job cụ thể khi startup:

~~~yaml
spring:
  batch:
    job:
      name: importOrdersJob
~~~

Thiết lập thứ hai thể hiện một chế độ vận hành khác với `enabled: false`; nếu tắt launch tự động thì `name` không làm job tự chạy. Khi triển khai nhiều replica của một web service, chạy job ở mọi lần start có thể gây cạnh tranh không mong muốn. Dùng scheduler có điều phối và JobRepository chia sẻ thay vì dựa vào side effect khi ứng dụng khởi động.

### 3.1. Định nghĩa hai job độc lập

Ví dụ dưới đây tập trung vào cách tạo **hai tên job khác nhau** và mỗi job có step riêng; `tasklet` chỉ là placeholder để minh họa, logic nhập và đối soát thực tế phải được cài đặt bằng reader/processor/writer hoặc tasklet chuyên dụng.

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class OrderBatchJobs {

    @Bean
    Step importOrdersStep(JobRepository repository, PlatformTransactionManager tx) {
        return new StepBuilder("importOrdersStep", repository)
                .tasklet((contribution, context) -> {
                    // Minh họa: gọi dịch vụ nhập liệu có transaction/idempotency.
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
    }

    @Bean
    Step reconcilePaymentsStep(JobRepository repository, PlatformTransactionManager tx) {
        return new StepBuilder("reconcilePaymentsStep", repository)
                .tasklet((contribution, context) -> {
                    // Minh họa: đọc snapshot thanh toán, tạo bản đối soát.
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
    }

    @Bean
    Job importOrdersJob(JobRepository repository,
                        @Qualifier("importOrdersStep") Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
    }

    @Bean
    Job reconcilePaymentsJob(JobRepository repository,
                             @Qualifier("reconcilePaymentsStep") Step reconcilePaymentsStep) {
        return new JobBuilder("reconcilePaymentsJob", repository)
                .start(reconcilePaymentsStep)
                .build();
    }
}
~~~

Mỗi `Job` có tên ổn định, duy nhất trong repository chung; tên bean dễ bảo trì nhất khi khớp tên job. Không đổi tên job theo mỗi lần deploy nếu mong giữ lịch sử restart. Các step dùng chung state/reader phải được đánh giá về thread-safety và checkpoint; ở sản phẩm thật, nên tách xử lý nghiệp vụ khỏi phần cấu hình job.

Spring Boot 3.x thường cung cấp `JobRepository`, `JobLauncher` và transaction manager qua auto-configuration khi có dependency và datasource phù hợp. Không thêm `@EnableBatchProcessing` tùy tiện vào một ứng dụng đang dựa trên auto-configuration vì nó có thể thay đổi cách các bean hạ tầng được cấu hình. Kiểm tra contract và phiên bản Boot đang dùng.

## 4. Khởi chạy có kiểm soát bằng JobLauncher

Trong Spring Batch 5.x, ứng dụng có thể tiêm `JobLauncher` và đúng `Job` bean. Tránh nhận tên job tự do từ URL rồi chạy theo tên do client cung cấp; nên dùng allowlist và kiểm tra quyền/tenant.

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class ImportBatchLauncher {

    private final JobLauncher launcher;
    private final Job importOrdersJob;

    ImportBatchLauncher(JobLauncher launcher,
                        @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.launcher = launcher;
        this.importOrdersJob = importOrdersJob;
    }

    JobExecution launch(LocalDate businessDate, String tenantId, String actor)
            throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("tenantId", tenantId, true)
                .addString("requestedBy", actor, false)
                .toJobParameters();

        return launcher.run(importOrdersJob, params);
    }
}
~~~

Trong code production, nên khai báo các exception khởi chạy cụ thể (`JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException`, `JobRestartException`, `JobParametersInvalidException`) và ánh xạ theo hợp đồng API. `throws Exception` ở đây giúp đoạn minh họa tập trung vào cách chọn job và tạo identity.

**Quan trọng:** `JobLauncher.run(...)` đồng bộ hay bất đồng bộ tùy cấu hình launcher. Khi đồng bộ, lời gọi có thể giữ HTTP thread đến khi job xong; với job chạy hàng phút/giờ, nên đưa yêu cầu vào cơ chế launch riêng có giới hạn, trả `jobExecutionId`/mã yêu cầu để client kiểm tra trạng thái. Khi bất đồng bộ, `JobExecution` trả về có thể còn ở `STARTING`/`STARTED`, không được diễn giải thành COMPLETED.

Ví dụ HTTP contract:

| Tình huống | Cách phản hồi gợi ý | Lý do |
| --- | --- | --- |
| Yêu cầu mới được nhận | `202 Accepted` cùng request/execution ID | Client kiểm tra trạng thái về sau |
| Đã có instance đang chạy | `200`/`202` trỏ tới execution hiện tại hoặc `409 Conflict` | Chọn một hợp đồng idempotent rõ ràng |
| Instance đã COMPLETED | `200 OK` trả kết quả trước, hoặc `409` nếu API muốn từ chối chạy lặp | Không tạo execution mới |
| Instance FAILED và được phép restart | Khởi chạy JobExecution mới trên **cùng instance** | Tiếp tục từ checkpoint hợp lệ |
| Parameters sai hoặc không được phép | `400`/`403` | Không tạo execution nghiệp vụ ngoài phạm vi |

Chỉ trả trạng thái “đang chạy” hoặc “đã hoàn tất” sau khi xác minh JobRepository, không suy diễn từ cache ứng dụng. Không bắt mọi exception rồi âm thầm chèn `run.id` để ép job khởi chạy.

## 5. Điều gì xảy ra khi launch trùng JobInstance?

Spring Batch nhận diện `JobInstance` bằng tên job và **tập identifying parameters**. Dưới đây là hành vi điển hình khi gọi `JobLauncher.run` với cùng identity:

| Trạng thái của instance hiện có | Yêu cầu launch cùng identity | Kết quả điển hình |
| --- | --- | --- |
| Chưa tồn tại | Lần đầu | Tạo JobInstance và JobExecution mới |
| Có JobExecution đang chạy | Lệnh trùng | `JobExecutionAlreadyRunningException` |
| JobExecution cuối đã COMPLETED | Lệnh trùng | `JobInstanceAlreadyCompleteException` |
| JobExecution FAILED | Lệnh launch lại | JobExecution mới để **restart**, nếu job/steps hỗ trợ |
| JobExecution STOPPED | Lệnh launch lại | Có thể restart sau khi trạng thái dừng ổn định |
| Job không restartable | Lệnh launch lại sau thất bại | `JobRestartException` hoặc lỗi restart tương ứng |
| Trạng thái UNKNOWN, metadata bất nhất | Lệnh launch lại | Không tự ép tiếp tục; cần điều tra và xử lý vận hành |

Lời gọi chạy đụng độ ở đúng thời điểm hai transaction cùng tạo metadata có thể phát sinh exception phụ thuộc DB/isolation và implementation bên cạnh các exception Spring Batch chuẩn. Hợp đồng bên ngoài nên xem đó là “đụng độ cùng identity” sau khi kiểm tra lại trạng thái repository, thay vì dựa vào chỉ một class exception.

Có hai quy tắc đặc biệt:

- **FAILED khác COMPLETED:** cùng identity sau FAILED có thể được restart đúng nơi đã checkpoint; nếu cố làm instance mới bằng timestamp, job có thể đọc lại từ đầu và làm trùng side effect.
- **Đã COMPLETED nhưng muốn chạy lại:** phải xác định có thay đổi business input hoặc nhu cầu reprocess chính đáng không, rồi dùng identifying parameter dành cho revision hoặc nguồn dữ liệu mới. Không xóa thủ công metadata để “giải phóng” instance.

Các JobInstance khác nhau được phép chạy đồng thời nếu không có ràng buộc thêm, ngay cả khi cùng một job definition; Spring Batch không tự tuần tự hóa tất cả instance của một job.

## 6. Đồng thời có nhiều mức khác nhau

Đừng gộp mọi loại song song thành một tính năng.

| Mức đồng thời | Đối tượng chạy song song | Ai kiểm soát | Điều kiện cần kiểm tra |
| --- | --- | --- | --- |
| **Nhiều job** | `importOrdersJob` và `reconcilePaymentsJob` | Scheduler, job launcher/executor | Tranh chấp DB, thứ tự phụ thuộc dữ liệu |
| **Nhiều instance** | Cùng `importOrdersJob` cho hai ngày/tenant khác | JobLauncher, JobRepository | Input có giao nhau không, xử lý có idempotent không |
| **Parallel steps** | Hai step độc lập trong một job | `split`, `TaskExecutor` | Hai step có thật sự độc lập về transaction/state không |
| **Multi-threaded step** | Nhiều đơn vị xử lý trong một step | Step task executor và concurrency | Reader/processor/writer thread-safety, chunk transaction |
| **Partitioning** | Các partition của một step | `Partitioner`/`PartitionHandler` hoặc worker | Chia dữ liệu không chồng lấn, restart từng partition |
| **Remote chunking** | Phát chunk qua broker cho worker | Messaging middleware/adapter | At-least-once delivery, ack, dedup, timeout |

Bài này tập trung ở **nhiều Job và JobInstance**. Nếu chỉ muốn hai job chạy đồng thời, không nhất thiết phải multi-thread một step. Ngược lại, việc khởi chạy hai job bằng hai thread không bảo đảm hai job không tranh chấp bảng DB hoặc cổng HTTP phía đối tác.

### 6.1. Các loại phụ thuộc cần mô hình hóa

- `reconcilePaymentsJob` chỉ chạy sau khi dữ liệu import của ngày đó đủ: dùng trạng thái hoàn tất trong DB, workflow scheduler hoặc một flow được định nghĩa rõ; chạy song song tùy tiện có thể đối soát dữ liệu thiếu.
- Hai job cùng cập nhật một bảng có row lock: cần chọn transaction boundary, index và thứ tự cập nhật để tránh deadlock, hoặc tuần tự hóa theo khóa nghiệp vụ.
- Nhiều instance import từ chung một file: identity phải bao gồm file/snapshot để tránh đọc chồng nhau; nếu không thể phân vùng, cần cơ chế khóa tài nguyên riêng.
- Nhiều job cùng gọi API đối tác có quota: dùng shared rate limiter/bulkhead thay vì để mỗi job tự bắn request không giới hạn.

**JobRepository chống hai execution đang hoạt động cho cùng instance**, nhưng không cấm hai instance khác nhau cùng ghi vào một tài nguyên nghiệp vụ. Quy tắc “không xử lý cùng hóa đơn hai lần” phải được thực thi bằng key, ràng buộc DB, idempotency và transaction tại domain.

## 7. JobRepository JDBC là điểm phối hợp giữa các replica

Trong ứng dụng chạy nhiều pod, cần JobRepository **chia sẻ và bền vững**. Với Spring Batch 5.x dùng JDBC repository, metadata được lưu tại các bảng tiêu biểu:

| Bảng | Nội dung |
| --- | --- |
| `BATCH_JOB_INSTANCE` | ID của instance, job name, job key |
| `BATCH_JOB_EXECUTION` | Mỗi lần chạy thử, status, timestamp |
| `BATCH_JOB_EXECUTION_PARAMS` | Các tham số và cờ `IDENTIFYING` |
| `BATCH_JOB_EXECUTION_CONTEXT` | Trạng thái job cần khôi phục |
| `BATCH_STEP_EXECUTION` | Trạng thái, số item read/write/skip của từng step |
| `BATCH_STEP_EXECUTION_CONTEXT` | Checkpoint của từng step |

Ví dụ production với PostgreSQL/MySQL dùng một database chung cho metadata, được quản lý bằng migration tương ứng phiên bản. Nếu nhiều instance ghi vào JobRepository khác nhau, mỗi bên có thể nghĩ cùng identity chưa tồn tại và cùng thực hiện tác vụ — Spring Batch không thể chống trùng xuyên các repository tách biệt.

Tầng repository sử dụng transaction, khóa/unique constraints và cơ chế isolation khi tạo `JobExecution` để giải quyết cạnh tranh khởi chạy. **Đọc “chưa có JobInstance” rồi mới tự insert/launch không phải thao tác nguyên tử**. Hai pod hoàn toàn có thể cùng thấy “chưa có”; phải để repository quản lý việc tạo hoặc áp dụng một khóa nghiệp vụ bên ngoài có transaction.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant A as Pod A
    participant B as Pod B
    participant R as JDBC JobRepository
    S->>A: launch(importOrdersJob, date=20/11, tenant=A)
    S->>B: launch(importOrdersJob, date=20/11, tenant=A)
    par Cùng lúc
        A->>R: Tạo/check JobExecution theo identity
        B->>R: Tạo/check JobExecution theo identity
    end
    R-->>A: Một yêu cầu được tạo execution
    R-->>B: Yêu cầu còn lại: trùng hoặc đang chạy
    Note over R: DB transaction/isolation quyết định xung đột
~~~

Cấu hình isolation khi tạo metadata ảnh hưởng hành vi hai launcher đụng độ. Mặc định và cách cấu hình cụ thể thay đổi theo phiên bản, loại repository và database; cần đọc cấu hình Spring Batch đang dùng, kiểm tra transaction của các lệnh `create*` và thử race test trên **chính database production tương ứng**. Không hạ isolation hay gỡ unique constraint chỉ để job dễ chạy song song.

Nếu môi trường bị crash, metadata có thể còn `STARTED` dù tiến trình đã chết. Đừng tự sửa cột `STATUS` thành `FAILED` bằng SQL để khởi chạy tiếp. Cần xác minh pod/worker thật sự đã ngừng, tình trạng transaction và side effect cuối cùng, sau đó dùng quy trình recovery được hỗ trợ của phiên bản vận hành.

### 7.1. Cẩn trọng với schema và vòng đời DB

- Tách metadata repository khỏi dữ liệu nghiệp vụ bằng schema hoặc quyền phù hợp; tài khoản ứng dụng cần quyền chính xác trên bảng metadata.
- Không để init schema của nhiều pod chạy như migration tự do trong production.
- Tính kích thước connection pool cho số job đồng thời, chunk transactions và transaction metadata; tránh pool starvation.
- Định kỳ archive/purge metadata theo chính sách vận hành có tham chiếu đến execution đang chạy và yêu cầu restart; không xóa record lịch sử đang cần để checkpoint.
- Nếu chia sẻ JobRepository giữa các ứng dụng, quản lý **unique job name** theo miền hệ thống để tránh hai định nghĩa job khác nhau dùng cùng tên và bộ identifying parameters.

## 8. Thiết kế launcher bất đồng bộ có giới hạn

Trong ứng dụng phục vụ HTTP, việc gọi `JobLauncher.run` đồng bộ cho job kéo dài nhiều phút có thể chiếm request thread và gây timeout ở client. Có thể cấu hình launcher chạy qua task executor hoặc nhận yêu cầu vào queue/scheduler nội bộ.

**Tuy nhiên, bất đồng bộ không phải vô hạn đồng thời.** Cần có executor với số worker và queue được giới hạn; khi queue đầy, trả trạng thái quá tải có kiểm soát. Nếu job launch từ nhiều pod, thread pool chỉ giới hạn trong mỗi pod, không thay thế giới hạn tổng số instance ở cấp cluster.

Một luồng xử lý hợp lý:

~~~text
POST /internal/batch/import-orders {businessDate, tenantId}
  -> authenticate/authorize + validate input
  -> chuẩn hóa identifying parameters
  -> nhận yêu cầu và trả requestId (nếu đã lưu bền vững)
  -> bounded launch executor / scheduler
  -> JobLauncher tạo JobExecution qua shared JobRepository
  -> client GET /internal/batch/executions/{id} để xem trạng thái
~~~

Nếu cần chống mất lệnh khi pod chết trước khi thread pool nhận việc, request phải được **ghi bền vững trước khi trả accepted**, ví dụ inbox table hoặc broker có ack đúng lúc. Một `CompletableFuture.runAsync` thuần trong memory không đảm bảo yêu cầu còn lại sau restart.

Đừng gắn kết quả HTTP status với `BatchStatus.COMPLETED` khi launcher chạy bất đồng bộ; đầu ra của lệnh launch là “đã tạo/đang thực hiện”, còn trạng thái cuối nằm ở `JobRepository`.

## 9. Scheduler, HTTP và broker cùng kích hoạt một ngày nghiệp vụ

Giả sử job import đơn ngày `2026-11-20` do ba nguồn kích hoạt:

1. Scheduler chạy lúc 01:00.
2. Đối tác gọi endpoint yêu cầu chạy lại lúc 01:00:01.
3. Consumer nhận lại message `StartImport` vì ack trước đó bị mất.

Nếu cả ba nguồn dùng **cùng** `jobName`, `businessDate` và `tenantId` là identifying parameters, mọi trigger đều hướng đến **một JobInstance logic**. Chúng có thể nhận thông báo “đang chạy” hoặc “đã hoàn tất”, thay vì tự ý tạo ba instance khác nhau.

~~~mermaid
flowchart LR
    A[Scheduler] --> D[Chuẩn hóa JobParameters]
    B[HTTP retry] --> D
    C[Broker redelivery] --> D
    D --> E[Shared JobRepository]
    E --> F[Một JobInstance logic]
    F --> G[JobExecution 1, restart nếu cần]
~~~

**Sự thống nhất tham số là bắt buộc:** nếu scheduler dùng `2026-11-20` còn message handler dùng thời gian hiện tại hoặc một UUID mới, Spring Batch sẽ thấy hai identity khác nhau và có thể chạy song song.

Đối với trigger từ broker:

- Message cần chứa business key ổn định, schema version và event/command ID.
- Consumer nên ghi yêu cầu launch bền vững (inbox/command table) trước khi ack khi yêu cầu là quan trọng; nếu chỉ ack sau `launcher.run` mà job đồng bộ kéo dài, redelivery có thể xảy ra.
- Đường nhận message có thể chạy **at-least-once**; dùng dedup ở command table hoặc business key, ngoài JobRepository.
- Nếu cần một job mới cho revision dữ liệu, ghi rõ revision trong identity; không tự đổi thành timestamp lúc nhận message.

`JobRepository` giúp kiểm soát lịch sử job; nó **không phải** transactional inbox cho broker và không bảo đảm đúng-một-lần ở side effect của HTTP/DB/broker.

## 10. Restart và checkpoint: giữ cùng identity khi khôi phục

Khi một step bị lỗi sau khi xử lý một phần dữ liệu, Spring Batch có thể tạo một `JobExecution` mới thuộc cùng `JobInstance`. Để resume đúng, cần:

1. Job/step được cấu hình restartable và metadata được ghi bền vững.
2. Reader/writer lưu đủ checkpoint trong `ExecutionContext`, theo hợp đồng `ItemStream` khi áp dụng.
3. Các tham số quyết định nguồn dữ liệu và business scope **không đổi** giữa lần chạy lỗi và lần restart.
4. Transaction của chunk bảo đảm rollback phần chưa commit; side effect ngoài transaction được xử lý idempotent.
5. Dữ liệu nguồn có snapshot/version hoặc thứ tự đọc ổn định; nếu dữ liệu thay đổi tùy ý giữa các lần chạy, vị trí checkpoint có thể không còn đúng.

Ví dụ đối soát đọc file theo thứ tự cố định, chunk size=100. Job thất bại sau khi commit 1.200 dòng: khi restart cùng instance, reader có thể tiếp tục theo checkpoint đã commit. Nếu lại chạy **instance mới** bằng `run.id`, nó có thể đọc từ đầu và ghi bản đối soát trùng.

Với writer gọi HTTP API hoặc publish Pulsar/Kafka, rollback transaction DB không đồng nghĩa side effect ngoài đã rollback. Cần idempotency key cho mỗi record/event, outbox hoặc cơ chế gửi bền vững. `skip`, `retry` và `restart` ở step có thể làm processor/writer được gọi thêm lần nữa.

### 10.1. Thế nào là chạy lại có chủ đích?

Phân biệt hai nghiệp vụ:

| Tình huống | Identity đề xuất | Mục tiêu |
| --- | --- | --- |
| Restart job lỗi của ngày 20/11 | **Giữ** `businessDate=2026-11-20` và tenant | Tiếp tục từ checkpoint |
| Chạy báo cáo ngày 21/11 | **Đổi** `businessDate` | Tập dữ liệu mới |
| Nguồn ngày 20/11 được sửa, cần bản báo cáo revision 2 | Thêm `revision=2` hoặc `sourceSnapshotId` làm identifying | Reprocess có chủ đích, phân biệt bản cũ |
| Chỉ request lại vì HTTP timeout | **Giữ** identity cũ | Chống khởi chạy trùng |
| Thử chạy lại vì job đã COMPLETED mà không thay đổi input | Không tạo instance mới | Trả lại trạng thái/kết quả hiện có |

Điều này giúp phân biệt **restart** với **rerun**. Một job có thể cần chính sách xoá/sửa bản kết quả cũ khi tạo revision mới; việc tạo JobInstance mới không tự đảm bảo dữ liệu đầu ra không xung đột.

## 11. Giới hạn đồng thời theo tài nguyên thực tế

Spring Batch cho phép chạy các JobInstance khác nhau đồng thời, nhưng concurrency phải nằm trong ngân sách hạ tầng. Khi nhiều job cùng đọc database, gọi REST API đối tác, dùng cache và phát event, các hàng đợi có thể khuếch đại lỗi.

| Tài nguyên | Rủi ro khi tăng đồng thời | Biện pháp |
| --- | --- | --- |
| JDBC connection pool | Hết connection, timeout, deadlock | Giới hạn job/step concurrency; đo pool; tối ưu transaction và index |
| CPU/JVM heap | GC, OutOfMemory, xử lý chậm | Chunk size phù hợp, streaming reader, bounded executor |
| HTTP client đối tác | `429`, timeout, circuit breaker mở | Rate limit/bulkhead theo đối tác, retry có jitter |
| Broker producer | Pending queue đầy, message trùng khi retry | Outbox, giới hạn in-flight, idempotency event |
| Cache | Thundering herd khi nhiều job cùng miss | Single-flight, jitter, giới hạn tải nguồn |
| Bảng nghiệp vụ | Nhiều job cập nhật cùng row/range | Phân vùng business key, unique constraint/optimistic locking |
| Metadata repository | Transaction cạnh tranh, sequence/row lock | Shared DB đủ tài nguyên, chỉ định identity đúng, đo latency |

Một giới hạn thường hữu ích là `maxConcurrentJobs` riêng cho từng nhóm công việc: nhập dữ liệu nặng, đối soát, xuất báo cáo. Với nhiều replica, cần cơ chế giới hạn **toàn cluster** nếu cùng chia sẻ một nguồn quá tải; `ThreadPoolTaskExecutor` của một pod chỉ giới hạn cục bộ.

Nếu job dùng parallel steps hoặc partitioning, **tổng** số worker có thể là số pod × số job × số step/partition × số thread. Cần so sánh với DB pool, số partition và quota API thực tế, thay vì chỉ cấu hình số thread của một job.

## 12. Kiểm thử trùng instance và race condition

Các test chỉ gọi `jobLauncher.run(...)` tuần tự không chứng minh race condition giữa hai pod đã được xử lý. Test nên có:

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Hai job khác tên, cùng ngày | Launch `importOrdersJob` và `reconcilePaymentsJob` | Có hai identity riêng; chạy đồng thời nếu không vướng tài nguyên |
| Cùng job, ngày khác | Launch 20/11 và 21/11 | Hai JobInstance riêng |
| Cùng job, cùng identifying params | Hai thread bắt đầu cùng lúc | Không tạo hai execution hợp lệ chạy đồng thời cho cùng instance |
| Khác non-identifying params | Đổi `requestedBy` nhưng giữ tenant/date | Vẫn là **cùng** JobInstance |
| Launch lại sau COMPLETED | Lặp lại đúng identifying params | Bị từ chối tạo execution mới hoặc API trả kết quả cũ |
| Restart sau FAILED | Chạy lỗi giữa chunk, launch lại cùng identity | JobExecution mới thuộc cùng JobInstance; không nhân side effect |
| Tạo instance mới có revision | Thêm `revision` identifying | Có instance mới, xử lý theo quy trình reprocess |
| Hai pod chia sẻ JDBC repository | Cùng kích hoạt tại barrier | Chỉ một launch giành quyền; bên còn lại biết đụng độ |
| Hai pod dùng hai repository | Cố tình cấu hình khác datasource | Phát hiện duplicate processing nguy hiểm; test chứng minh giới hạn |
| Crash/restart worker | Ngắt tiến trình khi đang xử lý | Metadata/checkpoint được đánh giá, recovery không làm mất hoặc trùng dữ liệu |
| Broker redelivery | Gửi lại cùng command/event ID | Không sinh thêm logical run/side effect ngoài hợp đồng |
| Tải đồng thời lớn | Nhiều tenant/date và nhiều job | DB pool, latency, retry, queue ở trong ngưỡng cho phép |

Cách đo test trùng: dùng barrier/`CountDownLatch` để đồng bộ thời điểm bắt đầu, giữ step chạy đủ lâu để hai launcher thực sự tranh chấp, rồi đọc repository kiểm tra **số JobInstance, số JobExecution và trạng thái**. Khi kiểm tra trên PostgreSQL/MySQL giống production, quan sát cả exception từ Spring Batch lẫn lỗi transaction/unique key của DB; không viết assertion cứng rằng mọi cạnh tranh đều ném một exception giống nhau.

Test restart phải kiểm tra **dữ liệu đầu ra không trùng**, chẳng hạn ràng buộc unique trên `(tenant_id, order_id, business_date)`, không chỉ kiểm tra `BatchStatus.COMPLETED`.

## 13. Quan sát và vận hành nhiều job

Các tín hiệu cần theo dõi theo cả hạ tầng và hợp đồng nghiệp vụ:

| Metric/log | Ý nghĩa |
| --- | --- |
| `job.name`, `batch.status`, thời gian chạy, thời gian chờ launch | Job chậm, lỗi hoặc xếp hàng lâu |
| Lượt launch trùng và trạng thái instance hiện có | Scheduler/HTTP/broker đang phát lại bao nhiêu |
| Số JobExecution restart cho một instance | Phát hiện job flapping |
| `StepExecution` read/write/filter/skip/rollback count | Phân biệt dữ liệu lỗi và xử lý bị nghẽn |
| Connection pool, deadlock, HTTP `429`, broker publish latency | Đo tranh chấp tài nguyên do concurrency |
| Số record thực sự xử lý và business reconciliation mismatch | Xác minh kết quả nghiệp vụ |
| Execution còn `STARTED` quá lâu, heartbeat/last update (nếu có) | Nghi ngờ worker chết hoặc job treo |

Không dùng raw `tenantId`, `orderId`, `businessDate`, `jobExecutionId` làm metric label nếu chúng tạo cardinality lớn. Đưa correlation ID, execution ID và business key vào log/trace có kiểm soát truy cập; metric tổng hợp theo nhóm job/trạng thái/loại lỗi.

`JobExecutionListener`/`StepExecutionListener` có thể ghi metric vào lúc bắt đầu/kết thúc; riêng hệ thống bất đồng bộ cần có lối tra cứu cuối cùng từ `JobExplorer`/JobRepository, không phụ thuộc vào response của HTTP trigger. Khi một execution nằm ở trạng thái bất thường, cần runbook xác minh tiến trình, dữ liệu đã commit, checkpoint và khả năng restart.

### 13.1. Lệnh quan sát metadata (chỉ dùng để đọc)

Một truy vấn SQL tham khảo cho JDBC repository:

~~~sql
SELECT
    i.JOB_INST_ID,
    i.JOB_NAME,
    e.JOB_EXEC_ID,
    e.STATUS,
    e.START_TIME,
    e.END_TIME
FROM BATCH_JOB_INSTANCE i
JOIN BATCH_JOB_EXECUTION e
    ON e.JOB_INST_ID = i.JOB_INST_ID
WHERE i.JOB_NAME = 'importOrdersJob'
ORDER BY e.CREATE_TIME DESC;
~~~

Truy vấn dùng tên cột của schema JDBC Spring Batch 5.x. Cần đối chiếu DDL đúng database và phiên bản của dự án trước khi dùng; với ứng dụng Java, có thể dùng `JobExplorer` để truy vấn thông qua API framework. Không chỉnh sửa metadata bằng SQL thủ công để sửa trạng thái job.

## 14. Một quy trình thiết kế nhiều job đáng tin cậy

1. **Liệt kê jobs:** mỗi job làm việc gì, nguồn DB/HTTP/broker nào, lịch chạy và phụ thuộc giữa các job.
2. **Định nghĩa identity:** chọn identifying parameters từ business key, thống nhất định dạng giữa scheduler, HTTP và message trigger.
3. **Xác định retry/rerun:** cùng identity dùng để restart; input revision mới có instance mới được quản trị rõ.
4. **Chọn kích hoạt:** tắt auto-start ở ứng dụng luôn chạy nếu cần; scheduler hoặc command inbox chịu trách nhiệm request.
5. **Dùng shared JobRepository:** kiểm tra JDBC schema, transaction, isolation và môi trường nhiều replica.
6. **Thiết lập ngân sách:** giới hạn số job đồng thời, step concurrency, DB pool, HTTP rate và broker backlog.
7. **Đảm bảo side effect idempotent:** transaction DB, unique key, outbox/inbox và event ID bảo vệ tác vụ bị retry.
8. **Định nghĩa lỗi:** trùng-running, trùng-completed, FAILED restartable, invalid params, worker crash đều có phản hồi/runbook.
9. **Kiểm thử race:** hai launcher thật sự chạy đồng thời trên DB tương ứng production; test khôi phục checkpoint, dữ liệu trùng và event redelivery.
10. **Quan sát:** theo dõi execution, business date, status, retry, tài nguyên, kết quả nghiệp vụ và phát hiện job chạy quá hạn.

**Nguyên tắc cốt lõi:** `JobInstance` trả lời “đây là cùng một lần xử lý logic hay một lần xử lý mới?”, còn `JobExecution` trả lời “lần thử chạy này diễn ra thế nào?”. Dùng identifying parameters ổn định, JobRepository chung và chính sách restart rõ ràng để ngăn launch trùng. Sau đó, kiểm soát concurrency, transaction và idempotency tại DB/HTTP/broker để các job khác nhau có thể chạy song song mà vẫn tạo kết quả đúng.

### Tài liệu tham khảo

- [Spring Batch Reference — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobParameters`, `JobExecution` và restart.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): nhiều Job bean, startup runner và `spring.batch.job.name`/`enabled`.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): JDBC metadata, transaction và isolation khi launch.
- [Spring Batch Reference — Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): launcher, parameters và cách chạy job.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): parallel steps, multi-threaded step, partitioning và thread-safety.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng metadata và cờ `IDENTIFYING`.

Các đoạn code dùng conventions Spring Batch 5.x; tài liệu tham khảo `current` có thể phản ánh Spring Batch 6.x ở thời điểm đọc. Kiểm tra đúng phiên bản trong Spring Boot BOM và DDL metadata trước khi dùng trực tiếp trên dự án.
