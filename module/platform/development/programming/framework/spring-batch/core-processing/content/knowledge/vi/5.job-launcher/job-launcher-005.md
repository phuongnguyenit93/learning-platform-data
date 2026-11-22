# Job đã hoàn tất và hành vi launch lại

Trong Spring Batch, gọi `JobLauncher` với một Job và một bộ `JobParameters` không có nghĩa là hệ thống luôn tạo một lần chạy hoàn toàn mới. Spring Batch trước tiên xác định `JobInstance` tương ứng dựa trên tên Job và các tham số định danh. Sau đó, trạng thái lịch sử của instance quyết định lần gọi sẽ được chấp nhận, được xem là restart hay bị từ chối.

Trường hợp quan trọng là JobInstance đã có một lần thực thi kết thúc với `COMPLETED`. Khi ứng dụng launch lại cùng Job với cùng các tham số định danh, Spring Batch thông thường ném `JobInstanceAlreadyCompleteException`. Một JobInstance đã hoàn tất được xem là đơn vị công việc đã xử lý xong; muốn xử lý một đơn vị công việc mới, cần tạo JobInstance mới bằng bộ tham số định danh khác.

Để hiểu đúng hành vi này, cần phân biệt ba thao tác:

- **Launch một JobInstance mới:** dùng tên Job và bộ identifying JobParameters chưa từng được chạy.
- **Restart một JobInstance:** chạy lại cùng đơn vị công việc sau khi lần thực thi trước thất bại hoặc bị dừng, nếu cấu hình cho phép.
- **Launch lại một JobInstance đã COMPLETED:** không được xem là restart hợp lệ; Spring Batch từ chối lần gọi với cùng danh tính.

## 1. JobLauncher xác định lần chạy trước khi thực thi

`JobLauncher` nhận một đối tượng `Job` và `JobParameters`, sau đó yêu cầu Spring Batch khởi chạy Job. Trong quá trình này, `JobRepository` được dùng để tìm hoặc tạo `JobInstance`, kiểm tra các lần thực thi trước và tạo `JobExecution` mới nếu việc khởi chạy hợp lệ.

```text
Ứng dụng
   |
   | Job + JobParameters
   v
JobLauncher
   |
   v
JobRepository
   |
   +--> Xác định JobInstance từ Job name + identifying parameters
   |
   +--> Kiểm tra JobExecution hiện có
   |
   +--> Quyết định:
          - Tạo JobInstance mới và launch
          - Tạo JobExecution mới để restart
          - Từ chối lần gọi
```

Một lệnh gọi `JobLauncher.run(job, parameters)` không tự động thêm tham số duy nhất cho mỗi lần gọi. Nếu các identifying JobParameters không đổi, các lần gọi vẫn nhắm đến cùng một JobInstance, kể cả khi một tham số không định danh thay đổi.

## 2. Vì sao Job đã COMPLETED không được launch lại với cùng tham số?

Spring Batch xem một JobInstance là một đơn vị công việc logic. Khi JobInstance đã hoàn thành, mục tiêu của đơn vị công việc đó đã đạt được theo luồng và chính sách đã cấu hình. Việc chạy lại cùng instance có thể khiến dữ liệu nghiệp vụ bị xử lý lặp, tạo báo cáo trùng hoặc phát sinh tác dụng phụ không mong muốn.

Ví dụ, Job `dailySalesJob` tổng hợp doanh thu cho một ngày. Tham số `businessDate` là tham số định danh:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

jobLauncher.run(dailySalesJob, parameters);
```

Giả sử lần chạy đầu đã hoàn tất:

```text
Job: dailySalesJob
JobInstance: businessDate=2026-11-15
JobExecution #1: COMPLETED
```

Nếu ứng dụng gọi lại với đúng Job name và cùng identifying parameter `businessDate=2026-11-15`, Spring Batch tìm thấy JobInstance đã hoàn thành và từ chối tạo lần chạy mới cho instance đó:

```text
jobLauncher.run(dailySalesJob, sameParameters)
             |
             v
JobInstance đã COMPLETED
             |
             v
JobInstanceAlreadyCompleteException
```

Đây là hành vi bảo vệ tính nhất quán của quy trình batch. Nếu ứng dụng muốn tổng hợp ngày 16, đó là một đơn vị công việc khác và cần truyền `businessDate=2026-11-16`, từ đó tạo JobInstance mới.

## 3. Những yếu tố quyết định có được launch hay không

Danh tính JobInstance được xác định bởi tên Job và những JobParameters có cờ identifying. Các tham số không định danh không làm thay đổi danh tính.

| Lịch sử của JobInstance tương ứng | Hành vi thường gặp khi gọi JobLauncher với cùng identifying parameters |
|---|---|
| Chưa tồn tại | Tạo JobInstance và JobExecution mới, sau đó chạy Job. |
| Đang có execution chạy | Từ chối, thường bằng `JobExecutionAlreadyRunningException`. |
| Execution trước đã `COMPLETED` | Từ chối, thường bằng `JobInstanceAlreadyCompleteException`. |
| Execution trước `FAILED` | Có thể tạo JobExecution mới để restart nếu Job cho phép restart. |
| Execution trước `STOPPED` | Có thể restart nếu trạng thái và cấu hình cho phép. |
| Job không cho phép restart sau lần chạy chưa hoàn thành | Có thể bị từ chối bằng `JobRestartException`. |

Các kết quả này được xác định theo JobInstance. Nếu chỉ thay đổi một tham số không định danh, Spring Batch vẫn coi đó là cùng JobInstance và vẫn áp dụng quy tắc theo lịch sử của instance đó.

## 4. Phân biệt restart sau FAILED với launch sau COMPLETED

Restart là tiếp tục một đơn vị công việc logic chưa hoàn thành. Khi một JobExecution thất bại, ứng dụng có thể launch lại cùng Job với cùng identifying parameters. Nếu Job và các Step cho phép restart, Spring Batch tạo một JobExecution mới cho cùng JobInstance.

```text
JobInstance: businessDate=2026-11-15
       |
       +--> JobExecution #1: FAILED
       |
       +--> JobExecution #2: COMPLETED
```

Trong ví dụ này, JobExecution #2 là lần thử mới của cùng JobInstance. Các metadata của lần chạy đầu vẫn được giữ lại. Spring Batch có thể bỏ qua Step đã hoàn thành và khôi phục Step bị lỗi từ checkpoint phù hợp, tùy cấu hình và khả năng lưu trạng thái của từng thành phần.

Ngược lại, nếu JobExecution #1 đã `COMPLETED`, không còn công việc dang dở để restart. Launch cùng tham số định danh sẽ bị từ chối:

```text
JobInstance: businessDate=2026-11-15
       |
       +--> JobExecution #1: COMPLETED
       |
       +--> Launch cùng identifying parameters
                |
                +--> JobInstanceAlreadyCompleteException
```

Nếu nghiệp vụ yêu cầu chạy lại dữ liệu đã hoàn tất, cần thể hiện rõ đây là một lần xử lý mới theo chính sách nghiệp vụ và tạo JobInstance mới bằng identifying parameter phù hợp.

## 5. Tham số định danh và không định danh ảnh hưởng thế nào?

`JobParameters` có thể chứa cả tham số định danh và không định danh. Chỉ các tham số định danh được dùng để tạo khóa của JobInstance.

```java
JobParameters firstCall = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();

JobParameters secondCall = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "admin", false)
        .toJobParameters();
```

Hai bộ tham số trên có `requestedBy` khác nhau nhưng vẫn có cùng danh tính JobInstance vì `businessDate` là identifying parameter và có cùng giá trị. Nếu lần chạy đầu đã `COMPLETED`, lần gọi thứ hai vẫn bị từ chối. Việc thay đổi người yêu cầu chỉ bổ sung metadata đầu vào, không tạo đơn vị công việc mới.

Nếu cần một lần xử lý mới cho cùng ngày nghiệp vụ, có thể bổ sung một tham số định danh thể hiện lần xử lý hoặc phiên bản tái xử lý:

```java
JobParameters reprocessParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("reprocessVersion", 2L, true)
        .toJobParameters();
```

Với bộ tham số này, `reprocessVersion=2` tham gia định danh và tạo JobInstance khác với instance chỉ có `businessDate=2026-11-15`. Chỉ nên làm vậy khi nghiệp vụ thực sự cho phép tái xử lý. Các Step cần có cơ chế tránh ghi trùng hoặc phải ghi đè kết quả cũ theo quy tắc được xác định rõ.

Không nên thêm một timestamp hoặc UUID định danh mới cho mọi lần gọi chỉ để né `JobInstanceAlreadyCompleteException`. Cách đó biến mọi lần gọi thành JobInstance mới, có thể làm mất khả năng nhận diện lần chạy trùng và khiến dữ liệu bị xử lý lặp mà không có kiểm soát.

## 6. Cách tạo JobInstance mới có chủ đích

Có một số cách phổ biến để tạo JobInstance mới sau khi instance trước đã hoàn tất.

### Dùng tham số nghiệp vụ mới

Đây là cách tự nhiên nhất khi đơn vị công việc thay đổi. Ví dụ, Job xử lý doanh thu theo ngày:

```java
JobParameters day15 = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobParameters day16 = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .toJobParameters();
```

Hai bộ tham số tạo hai JobInstance riêng. Mỗi instance có thể được theo dõi, hoàn tất và restart độc lập.

### Dùng tham số phiên bản hoặc mã lần tái xử lý

Nếu nghiệp vụ cho phép chạy lại cùng một kỳ dữ liệu như một công việc mới, có thể dùng thêm tham số định danh như `reprocessVersion`, `correctionBatchId` hoặc mã yêu cầu tái xử lý. Giá trị này phải được quản lý theo quy trình nghiệp vụ để tránh tạo instance trùng ngoài ý muốn.

### Dùng JobParametersIncrementer

Spring Batch cung cấp `JobParametersIncrementer` để sinh bộ tham số cho JobInstance kế tiếp. Một lựa chọn có sẵn là `RunIdIncrementer`, thường dùng tham số `run.id` tăng dần.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.support.RunIdIncrementer;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailySalesJobConfig {

    @Bean
    public Job dailySalesJob(
            JobRepository jobRepository,
            Step aggregateSalesStep) {

        return new JobBuilder("dailySalesJob", jobRepository)
                .incrementer(new RunIdIncrementer())
                .start(aggregateSalesStep)
                .build();
    }
}
```

Khi dùng incrementer, mỗi bộ tham số kế tiếp có thể mang `run.id` mới và vì vậy tạo JobInstance mới. Cơ chế này hữu ích cho các Job mà khái niệm “lần chạy kế tiếp” có ý nghĩa. Tuy nhiên, tăng `run.id` không tự bảo đảm nghiệp vụ an toàn: Job vẫn có thể xử lý lại cùng dữ liệu. Ứng dụng cần xác định rõ dữ liệu nào được phép chạy lại và cách quản lý kết quả của từng lần.

Với `JobOperator`, có thể yêu cầu khởi chạy instance kế tiếp của một Job có incrementer:

```java
jobOperator.startNextInstance("dailySalesJob");
```

`startNextInstance` sử dụng `JobParametersIncrementer` của Job để lấy bộ tham số tiếp theo. Nếu Job không cấu hình incrementer phù hợp, thao tác này không thể tự tạo bộ tham số kế tiếp.

## 7. Các exception thường gặp khi launch lại

`JobLauncher.run` có thể từ chối lần gọi nếu lịch sử JobInstance không cho phép khởi chạy. Các exception thường gặp gồm:

| Exception | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `JobInstanceAlreadyCompleteException` | JobInstance với identifying parameters tương ứng đã `COMPLETED`. | Nếu chỉ cần restart, kiểm tra lại yêu cầu vì instance đã xong. Nếu cần một lần xử lý mới, tạo JobInstance mới bằng tham số định danh phù hợp. |
| `JobExecutionAlreadyRunningException` | Một JobExecution của cùng JobInstance đang chạy. | Kiểm tra execution hiện tại; tránh gửi thêm lần launch trùng. |
| `JobRestartException` | Không thể restart instance, ví dụ Job được cấu hình không restart hoặc trạng thái cũ không cho phép. | Kiểm tra cấu hình restart và trạng thái metadata; chỉ tạo instance mới nếu nghiệp vụ xác định đó là công việc mới. |
| `JobParametersInvalidException` | Bộ JobParameters không hợp lệ theo validator của Job. | Bổ sung hoặc sửa tham số đầu vào theo quy tắc của Job. |

Không nên bắt tất cả exception rồi âm thầm tạo tham số ngẫu nhiên để thử lại. Điều đó có thể che giấu việc Job đang chạy, đã hoàn tất hoặc đang ở trạng thái không thể restart. Ứng dụng nên phân biệt lỗi do trùng lần gọi, lỗi do trạng thái instance và lỗi do dữ liệu tham số.

## 8. Ví dụ xử lý kết quả khi gọi JobLauncher

Ví dụ dưới đây minh họa việc bắt riêng trường hợp JobInstance đã hoàn tất. Các exception khác được khai báo để tầng gọi xử lý theo chính sách của ứng dụng.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.stereotype.Service;

@Service
public class DailySalesLauncher {

    private final JobLauncher jobLauncher;
    private final Job dailySalesJob;

    public DailySalesLauncher(JobLauncher jobLauncher, Job dailySalesJob) {
        this.jobLauncher = jobLauncher;
        this.dailySalesJob = dailySalesJob;
    }

    public JobExecution launch(JobParameters parameters)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobParametersInvalidException {
        try {
            return jobLauncher.run(dailySalesJob, parameters);
        } catch (JobInstanceAlreadyCompleteException ex) {
            // Instance đã hoàn tất: không tự tạo identifying parameter mới.
            throw ex;
        }
    }
}
```

Trong ứng dụng thực tế, tầng gọi có thể chuyển exception thành phản hồi API, thông báo cho người vận hành hoặc ghi log có cấu trúc. Nếu launcher được cấu hình bất đồng bộ, `JobExecution` trả về có thể vẫn đang ở trạng thái `STARTING` hoặc `STARTED`; không được coi trạng thái đó là kết quả cuối cùng.

## 9. JobLauncher không tự quyết định chính sách chạy lại dữ liệu

`JobLauncher` điều phối việc khởi chạy theo metadata và quy tắc của Spring Batch. Nó không biết một yêu cầu tái xử lý có được phép về mặt nghiệp vụ hay không. Quyết định đó thuộc về ứng dụng.

Trước khi tạo JobInstance mới cho dữ liệu đã hoàn tất, cần xác định:

1. Vì sao cần chạy lại: dữ liệu đầu vào đã thay đổi, kết quả trước cần sửa, hay chỉ có người dùng gửi yêu cầu trùng?
2. Kết quả cũ sẽ được giữ lại, thay thế hay đánh dấu hết hiệu lực?
3. Writer có thể ghi trùng hoặc gửi thông báo trùng không?
4. Có cần mã yêu cầu tái xử lý để truy vết và chống gửi lặp không?
5. Các Step có thể chạy độc lập với dữ liệu đã được xử lý trước đó không?

Nếu Job cập nhật dữ liệu nghiệp vụ, nên thiết kế thao tác ghi có tính idempotent hoặc có khóa nghiệp vụ phù hợp. Nếu Job tạo file, gửi email hoặc gọi dịch vụ bên ngoài, cần có cơ chế kiểm soát tác dụng phụ khi tạo một JobInstance mới cho cùng dữ liệu nguồn.

## 10. Các tình huống dễ nhầm lẫn

| Tình huống | Kết quả đúng cần hiểu |
|---|---|
| Gọi lại Job đã COMPLETED với cùng Job name và identifying parameters | Bị từ chối bằng `JobInstanceAlreadyCompleteException`. |
| Chỉ đổi tham số không định danh sau khi Job COMPLETED | Vẫn là cùng JobInstance; lần gọi vẫn bị từ chối. |
| Đổi tham số định danh sang ngày dữ liệu khác | Tạo JobInstance mới. |
| Gọi lại Job sau khi FAILED với cùng identifying parameters | Có thể restart bằng JobExecution mới nếu Job cho phép. |
| Gọi lại khi execution hiện tại vẫn đang chạy | Bị từ chối để tránh chạy trùng cùng instance. |
| Tăng `run.id` sau khi Job COMPLETED | Tạo JobInstance mới; Job có thể xử lý lại dữ liệu và cần chính sách nghiệp vụ rõ ràng. |
| Thêm UUID mới cho mọi lần gọi | Mỗi lần gọi có thể trở thành instance mới, làm mất khả năng phát hiện yêu cầu trùng. |

## Kết luận

Khi JobInstance đã kết thúc với `COMPLETED`, Spring Batch không cho `JobLauncher` chạy lại cùng Job với cùng identifying JobParameters. Đây là cơ chế bảo vệ một đơn vị công việc logic khỏi bị xử lý lặp. Nếu lần chạy trước `FAILED` hoặc `STOPPED`, ứng dụng có thể restart cùng JobInstance bằng JobExecution mới khi cấu hình cho phép. Nếu cần thực hiện một lần xử lý mới sau khi đã hoàn tất, hãy tạo JobInstance mới bằng tham số định danh có ý nghĩa nghiệp vụ hoặc dùng incrementer phù hợp. Việc tạo instance mới cần đi cùng chính sách kiểm soát dữ liệu và tác dụng phụ để tránh ghi trùng.
