# JobParametersIncrementer

`JobParametersIncrementer` là cơ chế tạo bộ `JobParameters` cho **JobInstance tiếp theo** của một job. Nó nhận parameters của instance trước và trả về parameters mới, thường bằng cách tăng một giá trị định danh như `run.id`, ngày nghiệp vụ hoặc phiên bản tái xử lý.

Incrementer hữu ích khi ứng dụng cần khởi chạy các instance mới theo chu kỳ hoặc theo một chuỗi có thứ tự. Cần phân biệt thao tác này với restart: restart tiếp tục cùng một JobInstance bằng identifying parameters cũ, còn incrementer thường tạo identifying parameters mới để bắt đầu một JobInstance khác.

## 1. Vai trò và hợp đồng của JobParametersIncrementer

`JobParametersIncrementer` là một interface của Spring Batch với phương thức:

```java
public interface JobParametersIncrementer {
    JobParameters getNext(JobParameters parameters);
}
```

Phương thức `getNext` nhận parameters của lần xử lý trước và trả về bộ parameters cho lần xử lý tiếp theo. Khi chưa có instance trước, đầu vào có thể rỗng hoặc null tùy đường gọi; implementation nên xử lý trường hợp khởi tạo đầu tiên một cách rõ ràng.

Incrementer không thực thi job và không tự lưu metadata. Nó chỉ tạo parameters. `JobLauncher` hoặc `JobOperator` mới yêu cầu thực thi job, còn `JobRepository` lưu JobInstance và JobExecution.

Ví dụ ý tưởng với job tổng hợp dữ liệu hàng ngày:

```text
Job: dailySettlement

Instance 1: businessDate=2026-11-14
Instance 2: businessDate=2026-11-15
Instance 3: businessDate=2026-11-16
```

Mỗi bộ parameters có ngày nghiệp vụ khác nhau nên tạo một JobInstance khác nhau nếu `businessDate` là identifying parameter.

## 2. Cấu hình incrementer cho một job

Có thể gắn incrementer khi xây dựng job bằng `JobBuilder.incrementer(...)`. Spring Batch cung cấp `RunIdIncrementer` cho trường hợp phổ biến cần tăng một số thứ tự.

```java
@Bean
Job dailySettlementJob(
        JobRepository jobRepository,
        Step settlementStep) {

    return new JobBuilder("dailySettlementJob", jobRepository)
        .incrementer(new RunIdIncrementer())
        .start(settlementStep)
        .build();
}
```

Với cấu hình này, job có một incrementer mặc định để tạo parameters cho instance tiếp theo. Việc gắn incrementer không làm cho mọi lần gọi `JobLauncher.run(...)` tự động tăng parameters; cách gọi job quyết định incrementer có được sử dụng hay không.

## 3. RunIdIncrementer hoạt động như thế nào?

`RunIdIncrementer` là implementation có sẵn để tăng parameter dạng số. Mặc định, key được sử dụng là `run.id`. Nếu parameters trước chưa có key này, giá trị đầu tiên thường là `1`; mỗi lần tạo bộ parameters tiếp theo, giá trị được tăng lên.

| Lần tạo instance | `run.id` | Kết quả định danh |
|---|---:|---|
| Lần đầu | 1 | JobInstance mới |
| Lần tiếp theo | 2 | JobInstance mới |
| Lần tiếp theo | 3 | JobInstance mới |

Ví dụ, có thể tự cấu hình incrementer với key khác:

```java
RunIdIncrementer incrementer = new RunIdIncrementer();
incrementer.setKey("reprocessVersion");
```

Khi đó, incrementer tăng `reprocessVersion` thay vì `run.id`. Tên key chỉ nên thay đổi khi có lý do nghiệp vụ hoặc quy ước rõ ràng; tránh để nhiều cơ chế khác nhau cùng tăng những parameter có ý nghĩa chồng lấn.

Parameter do `RunIdIncrementer` tạo được đánh dấu identifying trong cách triển khai chuẩn. Vì vậy, giá trị tăng lên làm thay đổi danh tính JobInstance và cho phép tạo instance mới dù các parameters khác được giữ nguyên.

## 4. Dùng JobOperator.startNextInstance()

Incrementer thường được sử dụng bởi `JobOperator.startNextInstance(jobName)`. Phương thức này yêu cầu Spring Batch tạo parameters tiếp theo dựa trên incrementer đã gắn với job, rồi khởi chạy instance mới.

```java
@Service
public class SettlementScheduler {

    private final JobOperator jobOperator;

    public SettlementScheduler(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public long startNextSettlement() throws Exception {
        return jobOperator.startNextInstance("dailySettlementJob");
    }
}
```

`startNextInstance` trả về execution ID để ứng dụng có thể theo dõi JobExecution được tạo. Phương thức này cần job được đăng ký trong `JobRegistry` và job phải có `JobParametersIncrementer` được cấu hình. Các exception cụ thể có thể phát sinh khi không tìm thấy job, parameters không hợp lệ, job đang chạy hoặc không thể tạo instance tiếp theo.

Ở mức khái niệm, quy trình là:

```text
JobOperator.startNextInstance(jobName)
              |
              v
     Tìm job và incrementer
              |
              v
  Lấy parameters của instance trước
              |
              v
     incrementer.getNext(previous)
              |
              v
     Tạo parameters mới
              |
              v
       Khởi chạy JobInstance mới
```

Đây là cách phù hợp cho scheduler hoặc quy trình vận hành muốn yêu cầu “chạy instance tiếp theo” mà không tự tính parameters ở từng caller.

## 5. Phân biệt startNextInstance, JobLauncher.run và restart

Ba thao tác này phục vụ các mục đích khác nhau:

| Thao tác | Parameters được dùng | Kết quả mong muốn |
|---|---|---|
| `JobLauncher.run(job, parameters)` | Bộ parameters caller truyền vào | Chạy hoặc yêu cầu chạy instance được xác định bởi chính parameters đó |
| `JobOperator.startNextInstance(jobName)` | Parameters do incrementer tạo từ instance trước | Tạo và chạy JobInstance tiếp theo |
| Restart một execution thất bại/dừng | Giữ identifying parameters của JobInstance cũ | Tiếp tục cùng công việc logic, tạo JobExecution mới |

Ví dụ, job nhập giao dịch ngày 15/11 đã thất bại giữa chừng. Muốn tiếp tục xử lý đúng tập dữ liệu đó, hãy restart execution hoặc gọi launcher với cùng identifying parameters theo trạng thái repository. Không tăng `run.id` chỉ để vượt qua lỗi; làm vậy sẽ tạo JobInstance mới và có thể xử lý lại dữ liệu từ đầu.

Ngược lại, khi job ngày 15/11 đã hoàn thành và lịch chạy cần xử lý ngày tiếp theo, `startNextInstance` cùng incrementer có thể tạo parameters cho instance mới.

### JobLauncher.run không tự gọi incrementer

Đoạn code sau dùng đúng parameters mà caller cung cấp:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

jobLauncher.run(dailySettlementJob, parameters);
```

Dù job đã được cấu hình `.incrementer(new RunIdIncrementer())`, lời gọi `run` ở trên không tự thêm hoặc tăng `run.id`. Nếu caller cần tạo instance mới bằng `JobLauncher`, caller phải tự tạo một bộ identifying parameters mới hoặc dùng một service chuyên trách gọi incrementer với đầu vào phù hợp.

## 6. Identifying parameters quyết định có tạo JobInstance mới hay không

JobInstance được xác định bởi tên job và các identifying JobParameters. Vì thế, output của incrementer cần thay đổi ít nhất một identifying parameter nếu mục tiêu là tạo JobInstance mới.

Ví dụ:

```java
JobParameters next = new JobParametersBuilder(previous)
    .addLong("run.id", nextRunId, true)
    .toJobParameters();
```

Đối số `true` đánh dấu `run.id` là identifying. Nếu parameter được thêm với identifying là `false`, giá trị đó không tham gia định danh và có thể không tạo ra JobInstance mới. Khi thiết kế custom incrementer, hãy kiểm tra rõ cờ identifying của các parameter được cập nhật.

Không phải mọi parameter đều nên được tăng. Chỉ tăng giá trị đại diện cho một đơn vị công việc mới, chẳng hạn ngày nghiệp vụ tiếp theo hoặc version tái xử lý. Giữ nguyên các parameters cần thiết để xác định phạm vi xử lý, ví dụ mã nguồn dữ liệu hoặc tenant, nếu nghiệp vụ yêu cầu.

## 7. Viết custom JobParametersIncrementer

`RunIdIncrementer` phù hợp khi chỉ cần số thứ tự. Nếu mỗi instance tiếp theo phải dùng ngày nghiệp vụ, kỳ báo cáo hoặc mã lô được tính theo quy tắc riêng, hãy triển khai `JobParametersIncrementer`.

Ví dụ dưới đây tăng `businessDate` thêm một ngày. Với lần đầu chưa có ngày trước đó, ví dụ dùng ngày hiện tại theo `Clock` được cấu hình cho múi giờ nghiệp vụ:

```java
public class BusinessDateIncrementer implements JobParametersIncrementer {

    private final Clock clock;

    public BusinessDateIncrementer(Clock clock) {
        this.clock = clock;
    }

    @Override
    public JobParameters getNext(JobParameters parameters) {
        JobParameters previous = parameters == null
            ? new JobParameters()
            : parameters;

        String previousDate = previous.getString("businessDate");
        LocalDate nextDate = previousDate == null
            ? LocalDate.now(clock)
            : LocalDate.parse(previousDate).plusDays(1);

        return new JobParametersBuilder(previous)
            .addString("businessDate", nextDate.toString(), true)
            .toJobParameters();
    }
}
```

Đăng ký incrementer với job:

```java
@Bean
JobParametersIncrementer businessDateIncrementer(Clock businessClock) {
    return new BusinessDateIncrementer(businessClock);
}

@Bean
Job dailySettlementJob(
        JobRepository jobRepository,
        Step settlementStep,
        JobParametersIncrementer businessDateIncrementer) {

    return new JobBuilder("dailySettlementJob", jobRepository)
        .incrementer(businessDateIncrementer)
        .start(settlementStep)
        .build();
}
```

Trong production, `Clock` nên được cấu hình theo múi giờ của lịch nghiệp vụ. Nếu ngày làm việc bỏ qua cuối tuần hoặc ngày nghỉ, không dùng `plusDays(1)` đơn giản; hãy lấy ngày tiếp theo từ business calendar hoặc dịch vụ lịch đã được quản lý.

Custom incrementer cũng nên giữ lại các parameters cũ cần cho instance tiếp theo. `new JobParametersBuilder(previous)` sao chép bộ parameters trước rồi cập nhật key `businessDate`. Cần cân nhắc kỹ nếu bộ parameters trước có thông tin chỉ hợp lệ cho lần chạy cũ.

## 8. Các nguyên tắc khi thiết kế incrementer

### Kết quả phải có ý nghĩa nghiệp vụ

Incrementer không nên tăng một giá trị ngẫu nhiên chỉ để né lỗi `JobInstanceAlreadyCompleteException`. Nếu cần chạy lại cùng một dữ liệu vì yêu cầu nghiệp vụ, hãy dùng một identifying parameter thể hiện version hoặc mã tái xử lý, đồng thời ghi nhận lý do và quy tắc xử lý dữ liệu đã có.

### Giữ parameters cần thiết

Khi tạo parameters mới, đừng vô tình bỏ các thông tin cần để xử lý đúng phạm vi dữ liệu. Ví dụ, job xử lý theo tenant có thể cần giữ `tenantId`; job tạo báo cáo có thể cần giữ `reportType`. Tuy nhiên, không nên giữ lại parameter tạm thời hoặc bí mật của lần chạy trước.

### Không đưa secret vào JobParameters

JobParameters được lưu trong metadata và có thể được hiển thị bởi công cụ quản trị hoặc log. Không dùng incrementer để sao chép password, access token, private key hoặc credential. Hãy tham chiếu secret qua secret manager hoặc cấu hình bảo mật của ứng dụng.

### Tránh phụ thuộc trạng thái bên ngoài không được kiểm soát

Incrementer nên tính kết quả từ parameters trước và nguồn dữ liệu có quy tắc rõ ràng. Nếu nó đọc ngày hệ thống, business calendar hoặc sequence bên ngoài, cần xác định múi giờ, thời điểm chốt và hành vi retry để cùng một yêu cầu không tạo ra kết quả khó dự đoán.

### Cẩn thận với nhiều caller đồng thời

Nếu hai scheduler hoặc operator gọi `startNextInstance` gần như đồng thời, cả hai có thể cùng quan sát một bộ parameters trước và tính ra cùng một bộ parameters kế tiếp. Repository có các cơ chế bảo vệ tính duy nhất và trạng thái, nhưng caller vẫn cần xử lý xung đột khi yêu cầu đồng thời.

Với quy trình yêu cầu số thứ tự tuyệt đối duy nhất, hãy phối hợp launch bằng lock, hàng đợi hoặc nguồn cấp sequence có tính nguyên tử. Có thể dùng request ID/idempotency key để nhận diện yêu cầu gửi lại. Không giả định một custom incrementer tự nó là bộ điều phối concurrency.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cấu hình incrementer nhưng gọi `JobLauncher.run` với parameters cũ | Không có parameter mới được tự động tạo; có thể gặp lỗi instance đã hoàn thành | Dùng `JobOperator.startNextInstance` hoặc tự tạo parameters mới |
| Dùng incrementer để restart execution thất bại | Tạo JobInstance khác và không tiếp tục checkpoint của instance cũ | Restart với identifying parameters cũ |
| Parameter được tăng không phải identifying | Không tạo danh tính JobInstance mới như mong muốn | Đánh dấu parameter mới là identifying |
| Bỏ mất parameter phạm vi như tenant hoặc report type | Instance mới xử lý sai hoặc thiếu phạm vi dữ liệu | Sao chép và cập nhật parameters có chủ đích |
| Tăng timestamp/UUID không có ý nghĩa nghiệp vụ | Khó truy vết và dễ tạo instance trùng lặp về dữ liệu | Dùng business key hoặc version tái xử lý rõ ràng |
| Nhiều caller cùng yêu cầu next instance | Có thể tính ra parameters giống nhau và gặp xung đột | Điều phối yêu cầu hoặc cấp sequence nguyên tử |
| Incrementer dựa vào ngày hệ thống không đúng múi giờ | Chọn nhầm kỳ xử lý ở ranh giới ngày | Dùng Clock và business calendar được cấu hình rõ |
| Sao chép secret vào parameters mới | Secret bị lưu trong metadata hoặc log | Lấy credential từ secret manager khi thực thi |

## 10. Kiểm thử JobParametersIncrementer

Incrementer là thành phần có thể kiểm thử độc lập. Với `RunIdIncrementer`, kiểm tra trường hợp parameters rỗng, trường hợp đã có `run.id` và việc các parameters khác được giữ lại.

Ví dụ kiểm tra custom incrementer:

```java
@Test
void shouldIncrementBusinessDateAndPreserveTenant() {
    Clock clock = Clock.fixed(
        Instant.parse("2026-11-16T00:00:00Z"),
        ZoneOffset.UTC);

    JobParameters previous = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("tenantId", "tenant-42", true)
        .toJobParameters();

    JobParameters next = new BusinessDateIncrementer(clock).getNext(previous);

    assertEquals("2026-11-16", next.getString("businessDate"));
    assertEquals("tenant-42", next.getString("tenantId"));
    assertTrue(next.getParameters().get("businessDate").isIdentifying());
}
```

Ngoài unit test, nên kiểm tra luồng tích hợp với `JobRepository` và `JobOperator`: tạo instance đầu, gọi `startNextInstance`, xác nhận instance mới có identifying parameters mong đợi và có execution ID riêng. Kiểm tra cả trường hợp job trước đang chạy, parameters không hợp lệ và hai yêu cầu next instance cạnh tranh.

## 11. Khi nào nên dùng JobParametersIncrementer?

| Nhu cầu | Cách làm phù hợp |
|---|---|
| Tạo các lần chạy tuần tự, mỗi lần có `run.id` mới | `RunIdIncrementer` |
| Chạy kỳ nghiệp vụ tiếp theo | Custom incrementer dựa trên ngày/kỳ và business calendar |
| Tái xử lý cùng dữ liệu theo một version mới | Custom incrementer hoặc service tạo version identifying rõ ràng |
| Restart job thất bại từ checkpoint | Dùng restart với JobInstance và identifying parameters cũ |
| Caller tự chỉ định một bộ parameters cụ thể | `JobLauncher.run(job, parameters)` |
| Nhiều tenant có lịch chạy độc lập | Điều phối parameters theo tenant; tránh dựa vào một chuỗi global không phân biệt tenant |

Incrementer đặc biệt hữu ích khi quy trình vận hành có khái niệm “instance kế tiếp” rõ ràng. Nếu caller đã biết chính xác ngày, mã lô hoặc phạm vi dữ liệu cần xử lý, một service tạo parameters tường minh có thể dễ hiểu hơn.

## Kết luận

`JobParametersIncrementer` tạo bộ parameters cho JobInstance tiếp theo dựa trên parameters của instance trước. `RunIdIncrementer` cung cấp cách đơn giản để tăng `run.id`, còn custom incrementer có thể áp dụng quy tắc theo ngày nghiệp vụ, kỳ báo cáo hoặc version tái xử lý. `JobOperator.startNextInstance` là đường gọi tiêu biểu sử dụng incrementer đã cấu hình.

Hãy phân biệt rõ tạo instance mới với restart cùng instance, bảo đảm parameter được tăng là identifying, giữ lại các parameters cần thiết và điều phối các yêu cầu đồng thời. Incrementer chỉ tạo parameters; nó không thay thế JobLauncher, JobRepository, authorization hoặc quy trình vận hành job.
