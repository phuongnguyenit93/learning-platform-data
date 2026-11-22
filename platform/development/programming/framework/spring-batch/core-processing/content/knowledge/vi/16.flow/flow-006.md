# Flow có điều kiện thành công trong Spring Batch

Một Job Spring Batch thường gồm nhiều Step. Trong quy trình đơn giản, các Step chạy lần lượt. Nhưng trong thực tế, Step tiếp theo chỉ nên chạy khi Step trước đáp ứng điều kiện nhất định. Ví dụ, chỉ publish file sau khi nhập dữ liệu thành công; chỉ đối soát sau khi ghi dữ liệu hoàn tất; hoặc chuyển sang nhánh xử lý lỗi khi bước kiểm tra đầu vào thất bại.

Spring Batch hỗ trợ **conditional flow** để điều khiển đường đi của Job dựa trên kết quả thực thi. Với flow có điều kiện thành công, ứng dụng thường kiểm tra **ExitStatus** của Step. Nếu kết quả là COMPLETED, Job chuyển sang Step tiếp theo. Nếu kết quả là FAILED hoặc một trạng thái không được chấp nhận, Job có thể dừng hoặc đi sang nhánh xử lý phù hợp.

Bài học này trình bày cách cấu hình luồng chỉ đi tiếp khi Step thành công, phân biệt BatchStatus với ExitStatus, xử lý kết quả tùy chỉnh, dùng wildcard và JobExecutionDecider, cũng như tác động của flow đến restart và kiểm thử.

## 1. Flow là gì?

Flow mô tả thứ tự và điều kiện chuyển giữa các Step trong một Job. Một flow có thể chạy tuần tự, rẽ nhánh, kết thúc hoặc dừng tùy theo kết quả của Step và quyết định nghiệp vụ.

Ví dụ Job nhập dữ liệu:

~~~mermaid
flowchart TD
    A["validateInputStep"] -->|COMPLETED| B["importDataStep"]
    A -->|FAILED hoặc trạng thái khác| X["Job FAILED"]
    B -->|COMPLETED| C["publishOutputStep"]
    B -->|FAILED hoặc trạng thái khác| X
    C -->|COMPLETED| D["Job COMPLETED"]
    C -->|FAILED hoặc trạng thái khác| X
~~~

Trong flow này:

- Chỉ khi kiểm tra đầu vào thành công, Step nhập dữ liệu mới chạy.
- Chỉ khi nhập dữ liệu thành công, Step publish mới chạy.
- Nếu một Step không trả về kết quả thành công được chấp nhận, Job đi đến trạng thái thất bại.

Flow giúp đặt điều kiện tại ranh giới giữa các giai đoạn. Mỗi Step vẫn chịu trách nhiệm thực hiện một phần công việc cụ thể; flow quyết định giai đoạn nào được chạy tiếp.

## 2. Phân biệt BatchStatus và ExitStatus

Đây là điểm quan trọng nhất khi cấu hình conditional flow.

**BatchStatus** biểu thị trạng thái vòng đời thực thi của JobExecution hoặc StepExecution. Một số giá trị thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| STARTING | Đang chuẩn bị bắt đầu |
| STARTED | Đang thực thi |
| STOPPING | Đang trong quá trình dừng |
| STOPPED | Đã dừng |
| COMPLETED | Thực thi hoàn tất |
| FAILED | Thực thi thất bại |
| ABANDONED | Execution được đánh dấu không tiếp tục |
| UNKNOWN | Không xác định được trạng thái đáng tin cậy |

**ExitStatus** mô tả kết quả thoát của một Step và được Job flow dùng để so khớp transition. Các giá trị phổ biến là COMPLETED, FAILED, STOPPED, NOOP và các mã tùy chỉnh do ứng dụng định nghĩa.

Khi viết:

~~~java
.on("COMPLETED").to(nextStep)
~~~

điều kiện COMPLETED được so khớp với **ExitStatus exit code** của trạng thái flow hiện tại, thường là Step vừa chạy. Không phải đây là biểu thức so sánh trực tiếp với enum BatchStatus.

Trong trường hợp thông thường, Step thành công có BatchStatus COMPLETED và ExitStatus COMPLETED. Tuy nhiên, listener hoặc logic ứng dụng có thể tạo ExitStatus tùy chỉnh trong khi BatchStatus vẫn là COMPLETED.

Ví dụ, một Step xử lý xong nhưng có một số item bị skip có thể được gán ExitStatus COMPLETED_WITH_SKIPS. Khi đó flow có thể tách riêng nhánh xử lý kết quả có skip.

### Vì sao cần hiểu cả hai trạng thái?

- BatchStatus cho biết execution đã thành công, thất bại, dừng hay ở trạng thái khác.
- ExitStatus cung cấp mã kết quả để Job chọn transition.
- Một Step có thể hoàn tất kỹ thuật nhưng có kết quả nghiệp vụ cần xử lý riêng.
- Flow chỉ chạy đúng khi các mã ExitStatus được thiết kế nhất quán.

Không nên dùng chuỗi COMPLETED trong flow rồi giả định mọi trạng thái BatchStatus khác đều được tự động xử lý theo ý muốn. Hãy xác định rõ các ExitStatus có thể xuất hiện và khai báo transition tương ứng.

## 3. Flow tuần tự bằng next()

Nếu Job chỉ cần chạy các Step lần lượt khi Step trước hoàn tất bình thường, có thể dùng next():

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step publishStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
        .next(importStep)
        .next(publishStep)
        .build();
}
~~~

Đây là cách khai báo ngắn gọn cho một flow tuyến tính. Framework điều phối các Step theo thứ tự đã khai báo; nếu Step thất bại, Job thông thường sẽ không tiếp tục như một luồng thành công.

Tuy nhiên, next() không diễn đạt rõ các nhánh theo ExitStatus. Khi cần quy định cụ thể rằng chỉ COMPLETED mới được chuyển tiếp, hoặc cần xử lý các trạng thái khác nhau, hãy dùng conditional transition với on(), to(), fail(), end() hoặc stop().

## 4. Chỉ chuyển sang Step tiếp theo khi kết quả là COMPLETED

Cấu hình conditional flow dùng on("COMPLETED").to(...). Để bảo đảm các kết quả khác không vô tình đi tiếp, cần khai báo nhánh fallback.

Ví dụ Job có ba Step: kiểm tra, nhập và publish:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step publishStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("*").fail()

        .from(importStep)
            .on("COMPLETED").to(publishStep)
        .from(importStep)
            .on("*").fail()

        .from(publishStep)
            .on("COMPLETED").end()
        .from(publishStep)
            .on("*").fail()

        .end()
        .build();
}
~~~

Ý nghĩa:

1. Job bắt đầu bằng validateStep.
2. Nếu ExitStatus của validateStep là COMPLETED, flow chuyển đến importStep.
3. Nếu kết quả không khớp nhánh thành công, on("*").fail() kết thúc Job với trạng thái thất bại.
4. importStep chỉ được chạy khi validateStep trả về kết quả thành công được chấp nhận.
5. publishStep chỉ chạy khi importStep cũng trả về COMPLETED.
6. Khi publishStep thành công, flow kết thúc bình thường.

on("*") là wildcard dùng làm nhánh dự phòng. Trong ví dụ, mọi ExitStatus không khớp COMPLETED đều bị coi là không thành công. Đây là cách thiết kế fail-closed: chỉ các kết quả được cho phép mới được đi tiếp.

Nếu ứng dụng có ExitStatus tùy chỉnh hợp lệ, hãy khai báo các nhánh đó trước fallback thay vì để wildcard đánh dấu thất bại tất cả.

## 5. Cú pháp on(), to() và from()

Conditional flow thường dùng các phương thức:

| Phương thức | Vai trò |
|---|---|
| start(step) | Chọn Step đầu tiên |
| on(pattern) | Chọn transition theo ExitStatus pattern |
| to(step) | Chuyển sang Step hoặc state tiếp theo |
| from(step) | Khai báo thêm transition xuất phát từ Step đã chỉ định |
| end() | Kết thúc Job flow với trạng thái hoàn tất |
| fail() | Kết thúc Job với trạng thái thất bại |
| stop() | Kết thúc flow với trạng thái dừng |

Một Step có thể có nhiều transition:

~~~java
.start(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("FAILED").to(rejectStep)
.from(validateStep)
    .on("*").fail()
~~~

Trong ví dụ:

- COMPLETED chuyển sang nhánh nhập dữ liệu.
- FAILED chuyển sang nhánh xử lý đầu vào bị từ chối.
- Các ExitStatus còn lại đi vào fallback và làm Job thất bại.

from(validateStep) cho biết các transition tiếp theo vẫn xuất phát từ kết quả của validateStep. Nó không chạy lại Step; nó bổ sung quy tắc chuyển flow cho cùng một state.

### Thứ tự và độ cụ thể của pattern

Nên khai báo các transition cụ thể như COMPLETED, FAILED hoặc mã tùy chỉnh trước wildcard *. Nhờ đó người đọc dễ thấy các kết quả đặc biệt được xử lý trước, còn wildcard đóng vai trò dự phòng.

Nếu một Step có nhiều ExitStatus hợp lệ, hãy khai báo rõ từng mã hoặc dùng pattern có chủ đích. Đừng dựa vào wildcard rộng nếu chưa hiểu những trạng thái nào có thể xuất hiện.

## 6. Chỉ cho phép trạng thái thành công được chấp nhận

Trong hệ thống thực tế, không phải mọi kết quả có ý nghĩa "đã kết thúc" đều đồng nghĩa với việc được phép chạy Step tiếp theo.

Ví dụ:

- COMPLETED: xử lý thành công.
- COMPLETED_WITH_SKIPS: xử lý xong nhưng có item bị skip.
- NO_DATA: không có dữ liệu đầu vào.
- VALIDATION_WARNING: đầu vào có cảnh báo cần xem xét.
- FAILED: xử lý thất bại.

Có thể thiết kế flow để chấp nhận một số trạng thái và chuyển các trạng thái khác sang nhánh riêng:

~~~java
return new JobBuilder("customerImportJob", jobRepository)
    .start(importStep)
        .on("COMPLETED").to(publishStep)
    .from(importStep)
        .on("COMPLETED_WITH_SKIPS").to(reviewStep)
    .from(importStep)
        .on("NO_DATA").to(noDataStep)
    .from(importStep)
        .on("FAILED").to(errorStep)
    .from(importStep)
        .on("*").fail()

    .from(publishStep)
        .on("COMPLETED").end()
    .from(publishStep)
        .on("*").fail()

    .from(reviewStep)
        .on("COMPLETED").end()
    .from(reviewStep)
        .on("*").fail()

    .from(noDataStep)
        .on("COMPLETED").end()
    .from(noDataStep)
        .on("*").fail()

    .from(errorStep)
        .on("*").fail()
    .end()
    .build();
~~~

Đây là ví dụ về chính sách flow:

- Chỉ dữ liệu hoàn toàn thành công mới publish.
- Dữ liệu có skip phải qua bước review.
- Không có dữ liệu được chuyển sang nhánh riêng.
- Lỗi được ghi nhận và Job kết thúc thất bại.

Trong ví dụ, reviewStep và noDataStep hoàn tất thì Job kết thúc theo flow end(). Nếu nghiệp vụ yêu cầu Job cuối cùng phải báo FAILED khi có skip hoặc không có dữ liệu, hãy dùng transition terminal phù hợp thay vì end().

## 7. Tạo ExitStatus tùy chỉnh cho điều kiện nghiệp vụ

Một Step có thể hoàn tất kỹ thuật nhưng cần trả mã kết quả riêng cho flow. Có thể dùng StepExecutionListener để bổ sung ExitStatus.

Ví dụ, nếu Step có item bị skip, trả mã COMPLETED_WITH_SKIPS:

~~~java
@Bean
StepExecutionListener importResultListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Không cần thao tác trước Step trong ví dụ này.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getSkipCount() > 0) {
                return new ExitStatus("COMPLETED_WITH_SKIPS");
            }

            return null;
        }
    };
}
~~~

Đăng ký listener:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRecord> reader,
        ItemProcessor<InputRecord, OutputRecord> processor,
        ItemWriter<OutputRecord> writer,
        StepExecutionListener importResultListener) {

    return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(importResultListener)
        .build();
}
~~~

Flow có thể phân nhánh theo mã tùy chỉnh:

~~~java
.start(importStep)
    .on("COMPLETED").to(publishStep)
.from(importStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(importStep)
    .on("*").fail()
~~~

Listener giúp chuyển thông tin runtime thành một ExitStatus có ý nghĩa với flow. BatchStatus vẫn phản ánh vòng đời execution; ExitStatus được dùng để điều khiển nhánh.

### Chọn mã ExitStatus ổn định

Mã tùy chỉnh nên:

- Có tên rõ nghĩa và được thống nhất trong ứng dụng.
- Không phụ thuộc vào câu thông báo log hoặc nội dung exception.
- Được xử lý trong Job flow.
- Có tài liệu mô tả ý nghĩa và trạng thái cuối mong đợi.
- Không thay đổi tùy tiện giữa các phiên bản nếu Job flow và công cụ vận hành còn phụ thuộc vào mã đó.

Không nên dùng thông điệp lỗi đầy đủ làm ExitStatus. Hãy dùng mã ngắn, ổn định và lưu chi tiết lỗi trong log hoặc metadata phù hợp.

## 8. Dùng wildcard để xử lý các kết quả khác

Spring Batch hỗ trợ pattern khi so khớp ExitStatus. Một số cách thường gặp:

| Pattern | Ý nghĩa |
|---|---|
| COMPLETED | Khớp mã COMPLETED |
| FAILED | Khớp mã FAILED |
| * | Khớp mọi mã |
| COMPLETED* | Khớp mã bắt đầu bằng COMPLETED |

Ví dụ:

~~~java
.start(importStep)
    .on("COMPLETED*").to(publishStep)
.from(importStep)
    .on("*").fail()
~~~

Pattern COMPLETED* có thể hữu ích nếu ứng dụng chủ động dùng một họ mã như COMPLETED_WITH_SKIPS. Tuy nhiên, chỉ dùng khi mọi mã có tiền tố đó thực sự được chấp nhận để publish. Nếu COMPLETED_WITH_WARNINGS cần review, hãy khai báo riêng thay vì cho phép wildcard chuyển thẳng sang publish.

### Fallback là hàng rào bảo vệ

Nếu chỉ khai báo:

~~~java
.start(validateStep)
    .on("COMPLETED").to(importStep)
.end()
~~~

các ExitStatus khác có thể không có transition tương ứng. Flow có thể kết thúc với lỗi không có transition phù hợp thay vì hành vi nghiệp vụ mà ứng dụng mong muốn.

Với Job quan trọng, hãy khai báo fallback rõ ràng:

~~~java
.start(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("*").fail()
.end()
~~~

Cách này làm rõ rằng chỉ kết quả thành công được phép tiếp tục.

## 9. Phân biệt end(), fail() và stop()

Ba terminal transition có ý nghĩa khác nhau:

| Transition | Trạng thái kết thúc Job | Ý nghĩa |
|---|---|---|
| end() | COMPLETED | Kết thúc flow thành công |
| fail() | FAILED | Kết thúc flow với lỗi |
| stop() | STOPPED | Kết thúc flow ở trạng thái dừng |

### end()

end() kết thúc Job với BatchStatus COMPLETED. Nó thường được dùng khi flow đã xử lý xong và không còn Step nào cần chạy.

Cần chú ý: nếu một Step trả ExitStatus FAILED nhưng transition của nó được cấu hình đi đến end(), Job có thể được đánh dấu hoàn tất theo trạng thái terminal end(). Điều này chỉ nên làm khi ứng dụng thực sự muốn coi lỗi đó là đã được xử lý và Job hoàn thành theo nghiệp vụ.

### fail()

fail() kết thúc Job với BatchStatus FAILED. Dùng khi kết quả không đáp ứng điều kiện để coi Job thành công.

Đây là lựa chọn phù hợp cho fallback trong flow chỉ cho phép COMPLETED đi tiếp.

### stop()

stop() kết thúc Job với BatchStatus STOPPED. Trạng thái này phù hợp với một quy trình cần dừng có kiểm soát và có thể được restart theo quy tắc của Job.

Không dùng stop() như một cách thay thế cho fail() khi dữ liệu đã bị lỗi. Dừng có chủ đích và thất bại là hai trạng thái vận hành khác nhau.

### end() cuối builder và end() của transition

Trong DSL, end() có thể xuất hiện ở cuối cấu hình để hoàn tất khai báo flow trước khi build(). Ngoài ra, on("...").end() là một transition đi đến trạng thái kết thúc Job.

Hãy phân biệt hai vị trí này khi đọc cấu hình. Một cái đóng flow builder; cái còn lại định nghĩa kết quả terminal cho một nhánh.

## 10. Khi điều kiện thành công phụ thuộc dữ liệu: JobExecutionDecider

ExitStatus phù hợp khi điều kiện chuyển nhánh đã được thể hiện trong kết quả của Step. Nếu quyết định phụ thuộc dữ liệu hoặc logic nghiệp vụ cần đánh giá riêng, có thể dùng JobExecutionDecider.

Decider nhận JobExecution và StepExecution hiện tại, sau đó trả về FlowExecutionStatus:

~~~java
public class ImportDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution != null
                && stepExecution.getWriteCount() == 0) {
            return new FlowExecutionStatus("NO_DATA");
        }

        return new FlowExecutionStatus("HAS_DATA");
    }
}
~~~

Đăng ký decider và dùng trong Job:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step publishStep,
        Step noDataStep,
        JobExecutionDecider importDecider) {

    return new JobBuilder("importJob", jobRepository)
        .start(importStep)
        .next(importDecider)
            .on("HAS_DATA").to(publishStep)
        .from(importDecider)
            .on("NO_DATA").to(noDataStep)
        .from(importDecider)
            .on("*").fail()
        .end()
        .build();
}
~~~

Ví dụ này minh họa cách quyết định nhánh theo số lượng dữ liệu đã ghi. Trong ứng dụng thực tế, có thể dùng một trạng thái nghiệp vụ được lưu trong ExecutionContext hoặc dữ liệu đối soát.

### Decider khác ExitStatus như thế nào?

- ExitStatus là kết quả thoát của Step.
- FlowExecutionStatus là kết quả mà decider trả về để flow chọn nhánh.
- Decider không thay đổi trực tiếp BatchStatus của Step đã chạy.
- Decider phù hợp với quyết định điều khiển flow cần đọc nhiều thông tin hoặc áp dụng quy tắc nghiệp vụ.

Không nên dùng decider cho mọi trường hợp. Nếu Step đã trả về COMPLETED hoặc FAILED và chỉ cần chuyển tiếp đơn giản, conditional transition theo ExitStatus dễ đọc hơn.

## 11. Skip không nhất thiết làm Step thất bại

Một điểm dễ nhầm là Step có thể kết thúc với BatchStatus COMPLETED dù đã skip một số item, nếu skip được cho phép và giới hạn không bị vượt.

Ví dụ:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(ValidationException.class)
    .skipLimit(20)
    .build();
~~~

Nếu có 3 item bị skip và Step vẫn hoàn tất, ExitStatus mặc định có thể vẫn là COMPLETED. Nếu flow chỉ kiểm tra COMPLETED, nó sẽ tiếp tục sang publish.

Điều đó có đúng hay không phụ thuộc nghiệp vụ:

- Nếu skip được chấp nhận và output vẫn hợp lệ, có thể publish.
- Nếu có skip thì cần người kiểm tra, hãy dùng listener trả ExitStatus tùy chỉnh và chuyển sang review.
- Nếu bất kỳ skip nào đều không chấp nhận, hãy để Step hoặc flow kết thúc thất bại theo chính sách.

Không nên giả định skip count tự động tạo một ExitStatus riêng. Nếu muốn flow phân biệt có skip, hãy thiết kế và gán mã kết quả rõ ràng.

## 12. Flow có điều kiện thành công và restart

Spring Batch lưu JobInstance, JobExecution, StepExecution và trạng thái thực thi trong JobRepository. Khi Job thất bại và được restart với cùng identifying JobParameters, flow được thực hiện lại theo metadata và chính sách restart.

Ví dụ:

~~~mermaid
flowchart TD
    A["validateStep COMPLETED"] --> B["importStep"]
    B -->|COMPLETED| C["publishStep"]
    B -->|FAILED| D["Job FAILED"]
    C -->|FAILED| D
    C -->|COMPLETED| E["Job COMPLETED"]
    D -. "Restart cùng JobInstance" .-> B
~~~

Nếu validateStep đã hoàn tất, Step này thường được bỏ qua khi restart cùng JobInstance theo hành vi mặc định. Step thất bại có thể được chạy lại nếu được phép restart. Sau khi Step đó thành công, flow tiếp tục theo transition phù hợp.

Một số điểm cần lưu ý:

- Step đã COMPLETED thường không chạy lại khi restart cùng JobInstance.
- Step thất bại có thể được thực thi lại nếu không bị giới hạn hoặc đánh dấu không thể restart.
- Reader và writer cần checkpoint phù hợp để tiếp tục phần chưa commit.
- Các identifying JobParameters phải nhất quán khi restart.
- Flow phải có transition rõ cho các ExitStatus mà Step có thể trả về.

### allowStartIfComplete

Nếu một Step cần chạy lại khi JobInstance được restart dù Step đã hoàn tất, có thể cấu hình allowStartIfComplete(true):

~~~java
@Bean
Step refreshValidationStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validationTasklet) {

    return new StepBuilder("refreshValidationStep", jobRepository)
        .tasklet(validationTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
}
~~~

Chỉ bật tùy chọn này khi Step có thể chạy lại an toàn. Nếu Step gửi thông báo, publish file hoặc tạo side effect, cần idempotency hoặc cơ chế chống thực hiện trùng.

### Flow không thay thế idempotency

Flow xác định Step nào được chạy. Nó không tự bảo đảm thao tác của Step có thể lặp lại an toàn.

Nếu Step publish file đã thành công nhưng metadata bị lỗi hoặc Job cần restart, cần có cách xác định file đã publish hay chưa. Dùng tên file theo batch ID, khóa nghiệp vụ, trạng thái publish hoặc cơ chế xác nhận từ hệ thống đích.

## 13. Xử lý nhánh thất bại

Một Job có thể có Step chuyên trách ghi nhận lỗi, lưu báo cáo hoặc giải phóng lock. Tuy nhiên, cần xác định trạng thái cuối cùng của Job sau nhánh xử lý lỗi.

Ví dụ chuyển sang recordFailureStep khi nhập dữ liệu thất bại:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step publishStep,
        Step recordFailureStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("COMPLETED").to(publishStep)
        .from(importStep)
            .on("FAILED").to(recordFailureStep)
        .from(importStep)
            .on("*").fail()

        .from(publishStep)
            .on("COMPLETED").end()
        .from(publishStep)
            .on("*").fail()

        .from(recordFailureStep)
            .on("*").fail()
        .end()
        .build();
}
~~~

Trong ví dụ, recordFailureStep có thể hoàn tất việc ghi audit, nhưng Job vẫn kết thúc FAILED do transition terminal của nhánh đó là fail().

Điều này giúp phân biệt:

- Step xử lý lỗi đã hoàn tất.
- Job nghiệp vụ ban đầu vẫn thất bại.

Nếu dùng .on("*").end() cho nhánh lỗi, Job có thể kết thúc COMPLETED. Chỉ làm vậy khi nghiệp vụ xác định việc xử lý lỗi đã là kết quả thành công của Job, ví dụ một Job phân loại và cách ly file đầu vào không hợp lệ.

### Không để nhánh lỗi vô tình chạy publish

Với flow quan trọng, hãy khai báo rõ transition của từng Step. Nếu chỉ có nhánh thành công mà không có fallback, các ExitStatus bất ngờ có thể dẫn đến lỗi flow không có transition. Nếu wildcard chuyển mọi kết quả sang publish, dữ liệu lỗi có thể bị phát hành.

Nguyên tắc an toàn là chỉ các ExitStatus được chấp nhận mới đi vào Step tạo tác động bên ngoài như publish, gửi thông báo hoặc cập nhật hệ thống downstream.

## 14. Flow có điều kiện theo trạng thái kiểm tra dữ liệu

Một ví dụ khác là Job kiểm tra file trước khi nhập. Step validation có thể trả một trong ba kết quả:

- COMPLETED: file hợp lệ.
- NO_DATA: file không có dòng dữ liệu.
- FAILED: file sai định dạng hoặc không thể đọc.

Flow:

~~~java
return new JobBuilder("fileImportJob", jobRepository)
    .start(validateFileStep)
        .on("COMPLETED").to(importStep)
    .from(validateFileStep)
        .on("NO_DATA").to(noDataStep)
    .from(validateFileStep)
        .on("FAILED").to(rejectFileStep)
    .from(validateFileStep)
        .on("*").fail()

    .from(importStep)
        .on("COMPLETED").to(publishStep)
    .from(importStep)
        .on("*").fail()

    .from(noDataStep)
        .on("COMPLETED").end()
    .from(noDataStep)
        .on("*").fail()

    .from(rejectFileStep)
        .on("*").fail()
    .end()
    .build();
~~~

Flow chỉ nhập dữ liệu khi file hợp lệ và có dữ liệu. File rỗng được xử lý theo nhánh riêng. File sai định dạng được chuyển sang nhánh từ chối, sau đó Job vẫn báo FAILED để scheduler hoặc hệ thống giám sát nhận biết lỗi đầu vào.

Để có ExitStatus NO_DATA, Step validation cần chủ động trả mã tùy chỉnh, ví dụ qua StepExecutionListener hoặc logic điều khiển phù hợp. Không nên giả định Spring Batch tự tạo mã này chỉ vì reader không đọc được item nào.

## 15. Điều kiện thành công ở nhiều Step liên tiếp

Với một quy trình có nhiều giai đoạn, mỗi Step cần có điều kiện thành công rõ ràng trước khi flow đi tiếp.

Ví dụ:

| Step | Điều kiện để đi tiếp | Step tiếp theo |
|---|---|---|
| validateInputStep | COMPLETED | loadReferenceStep |
| loadReferenceStep | COMPLETED | processStep |
| processStep | COMPLETED | reconcileStep |
| reconcileStep | COMPLETED | publishStep |
| publishStep | COMPLETED | Kết thúc Job |

Nếu bất kỳ Step nào trả ExitStatus khác COMPLETED, flow chuyển sang thất bại hoặc nhánh xử lý được khai báo.

Không nên gom quá nhiều trách nhiệm vào một Step chỉ để giảm số transition. Step có ranh giới rõ giúp xác định chính xác giai đoạn nào thất bại và restart từ đâu.

## 16. Kiểm thử conditional flow

Conditional flow cần được kiểm thử bằng cách xác nhận Step nào thực sự chạy theo từng ExitStatus.

Các trường hợp quan trọng:

| ExitStatus của Step đầu | Kết quả mong đợi |
|---|---|
| COMPLETED | Step thành công tiếp theo được chạy |
| FAILED | Không chạy Step publish; Job đi nhánh fail hoặc error |
| STOPPED | Job đi nhánh stop nếu đã cấu hình |
| NO_DATA | Chạy nhánh xử lý dữ liệu rỗng |
| COMPLETED_WITH_SKIPS | Chạy nhánh review nếu được khai báo |
| Mã không được hỗ trợ | Fallback xử lý, thường là fail |

### Kiểm thử flow thành công

Với trường hợp thành công:

1. Cấu hình Step đầu trả ExitStatus COMPLETED.
2. Chạy Job.
3. Xác nhận Step tiếp theo được thực thi.
4. Xác nhận Step publish chỉ chạy khi mọi Step trước đó trả trạng thái được chấp nhận.
5. Xác nhận Job kết thúc COMPLETED.

### Kiểm thử flow thất bại

Với trường hợp lỗi:

1. Cấu hình Step đầu ném exception hoặc trả ExitStatus thất bại theo cách phù hợp.
2. Chạy Job.
3. Xác nhận Step publish không chạy.
4. Xác nhận nhánh error được chạy nếu có.
5. Xác nhận trạng thái Job cuối cùng đúng với fail(), end() hoặc stop() đã khai báo.

### Kiểm thử mã tùy chỉnh và wildcard

Cần kiểm tra cả:

- Mã custom được khai báo rõ có đi đúng nhánh.
- Mã bất ngờ không bị wildcard chuyển nhầm sang nhánh publish.
- COMPLETED_WITH_SKIPS có được xử lý đúng theo chính sách.
- Không có trạng thái hợp lệ nào bị bỏ quên khiến flow không có transition.

### Kiểm thử restart

Tạo một lần chạy mà Step xử lý thành công nhưng Step publish thất bại. Restart cùng JobInstance và xác nhận:

- Step đã hoàn tất được bỏ qua theo mặc định.
- Step thất bại được chạy lại.
- Flow tiếp tục đúng transition.
- Publish không tạo tác động trùng nếu lần đầu đã có side effect một phần.
- Job kết thúc với trạng thái đúng.

Có thể dùng các tiện ích kiểm thử Spring Batch như JobLauncherTestUtils và JobRepositoryTestUtils để chạy Job trong test context. Nên kiểm tra cả JobExecution, StepExecution và dữ liệu đầu ra thay vì chỉ kiểm tra exception.

## 17. Theo dõi flow khi Job chạy

Khi một Job có nhiều nhánh, cần ghi nhận đủ thông tin để biết vì sao flow chọn một Step.

Các thông tin hữu ích:

- Job name và JobExecution ID.
- Step name và StepExecution ID.
- BatchStatus của Step.
- ExitStatus và exit code.
- Thời điểm bắt đầu và kết thúc.
- Bộ đếm read, write, filter và skip.
- Transition hoặc nhánh được thực hiện.
- Mã batch và identifying JobParameters đã được làm sạch dữ liệu nhạy cảm.

Có thể ghi ExitStatus trong StepExecutionListener hoặc dùng công cụ vận hành dựa trên JobExplorer. Không nên chỉ log thông báo "Step hoàn tất" mà không ghi mã ExitStatus nếu flow có nhiều nhánh.

Với mã tùy chỉnh, nên duy trì tài liệu hoặc enum hằng số để tránh lỗi chính tả giữa nơi tạo ExitStatus và nơi cấu hình transition.

## 18. Những lỗi thiết kế thường gặp

### Nhầm BatchStatus với ExitStatus

Flow transition so khớp ExitStatus. Một Step có thể có BatchStatus COMPLETED nhưng ExitStatus tùy chỉnh. Hãy kiểm tra đúng mã flow đang nhận.

### Dùng next() khi cần rẽ nhánh

next() phù hợp với flow tuần tự. Khi cần điều kiện thành công, lỗi hoặc trạng thái nghiệp vụ, hãy khai báo transition tường minh.

### Chỉ khai báo nhánh COMPLETED mà không có fallback

ExitStatus tùy chỉnh hoặc trạng thái bất ngờ có thể không có transition phù hợp. Thêm wildcard fallback để xác định hành vi cho mọi kết quả còn lại.

### Dùng wildcard quá rộng cho nhánh publish

Nếu on("*").to(publishStep), mọi ExitStatus đều có thể đi đến publish. Chỉ dùng pattern cho các trạng thái đã được xác định là an toàn.

### Không xử lý ExitStatus tùy chỉnh

Nếu listener trả COMPLETED_WITH_SKIPS nhưng flow chỉ có COMPLETED, Step có thể không đi vào nhánh mong đợi. Khai báo rõ các mã tùy chỉnh.

### Dùng end() trên nhánh lỗi mà không hiểu trạng thái cuối

end() kết thúc Job với trạng thái hoàn tất. Nếu dùng trên nhánh FAILED, Job có thể được đánh dấu COMPLETED dù Step trước thất bại. Chỉ dùng khi lỗi đã được xử lý và nghiệp vụ xác định Job hoàn thành.

### Coi skip là thất bại tự động

Skip được cấu hình có thể cho phép Step hoàn tất bình thường. Nếu có skip phải review, hãy tạo ExitStatus tùy chỉnh hoặc dùng điều kiện riêng.

### Dùng Decider cho điều kiện đơn giản

Nếu chỉ cần kiểm tra COMPLETED, transition theo ExitStatus rõ ràng và ngắn hơn. Dùng Decider khi quyết định cần logic hoặc dữ liệu bổ sung.

### Không kiểm thử nhánh thất bại

Chỉ kiểm thử đường thành công không chứng minh Job sẽ dừng đúng khi validation, import hoặc publish thất bại. Hãy kiểm tra các nhánh lỗi và fallback.

## 19. Quy trình xây dựng flow có điều kiện thành công

Khi thiết kế một Job, có thể làm theo trình tự:

1. **Liệt kê Step:** xác định các giai đoạn nghiệp vụ và thứ tự phụ thuộc.
2. **Định nghĩa kết quả:** xác định ExitStatus mặc định và mã tùy chỉnh của từng Step.
3. **Định nghĩa thành công:** quyết định chính xác trạng thái nào được phép chạy Step tiếp theo.
4. **Cấu hình transition:** dùng on("COMPLETED").to(...) hoặc các mã được chấp nhận.
5. **Thêm fallback:** xử lý mọi ExitStatus khác bằng nhánh lỗi, dừng hoặc kết thúc có chủ đích.
6. **Tách nhánh nghiệp vụ:** xử lý NO_DATA, COMPLETED_WITH_SKIPS hoặc cảnh báo theo yêu cầu.
7. **Chọn terminal state:** quyết định dùng end(), fail() hay stop() dựa trên kết quả Job mong muốn.
8. **Xem xét restart:** bảo đảm Step và side effect có thể chạy lại an toàn.
9. **Ghi nhận trạng thái:** log ExitStatus và StepExecution để vận hành có thể truy vết.
10. **Kiểm thử mọi nhánh:** thành công, thất bại, mã tùy chỉnh, wildcard và restart.

## 20. Những điểm cần nhớ

- Flow điều khiển thứ tự và nhánh thực thi của các Step trong Job.
- Conditional transition thường so khớp **ExitStatus**, không phải trực tiếp BatchStatus.
- on("COMPLETED").to(nextStep) cho phép chuyển tiếp khi ExitStatus là COMPLETED.
- from(step) dùng để khai báo thêm transition xuất phát từ cùng Step.
- Dùng wildcard on("*") làm fallback cho các mã chưa được khai báo cụ thể.
- Chỉ cho phép các ExitStatus đã xác định đi đến Step publish hoặc các thao tác có side effect.
- ExitStatus tùy chỉnh giúp tách COMPLETED_WITH_SKIPS, NO_DATA hoặc cảnh báo thành các nhánh riêng.
- end() kết thúc Job với trạng thái hoàn tất; fail() kết thúc với thất bại; stop() kết thúc ở trạng thái dừng.
- Skip không tự động làm Step thất bại; cần định nghĩa rõ chính sách nghiệp vụ.
- JobExecutionDecider phù hợp khi quyết định nhánh cần logic hoặc dữ liệu bổ sung.
- Restart phụ thuộc JobRepository, identifying JobParameters, trạng thái Step và khả năng chạy lại an toàn.
- Kiểm thử cả đường thành công, thất bại, trạng thái tùy chỉnh, fallback và restart.

Một flow có điều kiện thành công giúp Job chỉ thực hiện giai đoạn tiếp theo khi kết quả trước đó đáp ứng hợp đồng đã định nghĩa. Khi ExitStatus, nhánh fallback và trạng thái kết thúc được cấu hình rõ ràng, quy trình Spring Batch sẽ dễ theo dõi, an toàn khi publish và dễ khôi phục khi có lỗi.

