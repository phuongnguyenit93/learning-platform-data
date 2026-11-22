# Flow không có nhánh

Trong Spring Batch, flow mô tả thứ tự các step được thực hiện trong một job. Với flow không có nhánh, các step chạy theo một chuỗi cố định: step đầu tiên hoàn tất thì step kế tiếp được thực hiện, rồi tiếp tục theo thứ tự đã khai báo.

Kiểu flow này phù hợp với quy trình có các công đoạn phụ thuộc tuần tự, chẳng hạn kiểm tra file, nhập dữ liệu và lưu trữ file. Không cần quyết định bước tiếp theo dựa trên kết quả nghiệp vụ khác nhau; đường đi đã được xác định từ cấu hình job.

## 1. Flow tuần tự là gì?

Flow không có nhánh là một chuỗi step tuyến tính. Mỗi step có một vị trí cố định trong quy trình và chỉ có một step kế tiếp theo cấu hình.

```text
start
  |
  v
validateInput
  |
  v
importRecords
  |
  v
publishSummary
  |
  v
end
```

Ví dụ, một job xử lý file có thể gồm ba công đoạn:

1. `validateInput`: kiểm tra file và cấu trúc dữ liệu.
2. `importRecords`: đọc, chuyển đổi và ghi các bản ghi.
3. `archiveInput`: chuyển file đầu vào sang thư mục lưu trữ.

Các step chạy theo thứ tự cấu hình. Việc khai báo một bean trước hay sau trong file Java không quyết định thứ tự thực thi; chuỗi `start()` và `next()` mới thể hiện thứ tự của flow.

## 2. Khai báo flow tuần tự bằng start() và next()

Cách đơn giản nhất là dùng `JobBuilder.start(step)` để chọn step đầu tiên và gọi `next(step)` cho từng step tiếp theo.

Ví dụ theo API của Spring Batch 5:

```java
@Bean
Job importFileJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importRecordsStep,
        Step archiveInputStep) {

    return new JobBuilder("importFileJob", jobRepository)
        .start(validateInputStep)
        .next(importRecordsStep)
        .next(archiveInputStep)
        .build();
}
```

Trong ví dụ này:

- `start(validateInputStep)` xác định step bắt đầu.
- `next(importRecordsStep)` nối step nhập dữ liệu sau bước kiểm tra.
- `next(archiveInputStep)` nối bước lưu trữ sau khi nhập dữ liệu hoàn tất.
- `build()` tạo job với thứ tự thực thi đã khai báo.

`next()` không có nghĩa là chạy step kế tiếp ngay lập tức trong cùng một phương thức Java. Nó định nghĩa cấu trúc job; khi job được launch, Spring Batch điều phối từng step theo chuỗi đó.

## 3. Khai báo các Step riêng biệt

Mỗi step nên là một đơn vị công việc có trách nhiệm rõ ràng. Ví dụ:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validationTasklet) {

    return new StepBuilder("validateInput", jobRepository)
        .tasklet(validationTasklet, transactionManager)
        .build();
}

@Bean
Step importRecordsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> reader,
        ItemProcessor<InputRow, Record> processor,
        ItemWriter<Record> writer) {

    return new StepBuilder("importRecords", jobRepository)
        .<InputRow, Record>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}

@Bean
Step archiveInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveTasklet) {

    return new StepBuilder("archiveInput", jobRepository)
        .tasklet(archiveTasklet, transactionManager)
        .build();
}
```

`validateInputStep` và `archiveInputStep` là tasklet step, còn `importRecordsStep` là chunk-oriented step. Job có thể kết hợp hai kiểu step trong cùng một flow tuần tự.

## 4. Thứ tự thực thi và điều kiện chuyển tiếp mặc định

Với chuỗi step tuần tự, Spring Batch thực hiện step đầu tiên rồi chuyển sang step kế tiếp khi step trước hoàn tất bình thường theo luồng đã định nghĩa.

```text
validateInput
     |
     +-- hoàn tất thành công --> importRecords
                                   |
                                   +-- hoàn tất thành công --> archiveInput
                                                                    |
                                                                    v
                                                                   end
```

Flow tuyến tính không có đường thay thế được khai báo cho kết quả lỗi. Nếu một step thất bại, job thường dừng tại step đó và các step phía sau không được chạy trong JobExecution đó.

Ví dụ, nếu `importRecords` thất bại thì `archiveInput` không chạy. Điều này tránh lưu trữ file như thể việc nhập đã hoàn tất trong khi dữ liệu chưa được ghi đầy đủ.

Đây là đặc điểm quan trọng của flow không nhánh: cùng một chuỗi bước được dùng cho mọi lần chạy, còn lỗi được xử lý bởi cơ chế exception, retry, skip hoặc restart ở cấp step/job.

## 5. Tách một Flow riêng để tái sử dụng

Khi một nhóm step tuần tự có thể được dùng trong nhiều job, có thể định nghĩa nó thành một `Flow` riêng bằng `FlowBuilder`.

```java
@Bean
Flow fileImportFlow(
        Step validateInputStep,
        Step importRecordsStep,
        Step archiveInputStep) {

    return new FlowBuilder<SimpleFlow>("fileImportFlow")
        .start(validateInputStep)
        .next(importRecordsStep)
        .next(archiveInputStep)
        .build();
}
```

Job có thể sử dụng flow này như một thành phần:

```java
@Bean
Job importFileJob(
        JobRepository jobRepository,
        Flow fileImportFlow) {

    return new JobBuilder("importFileJob", jobRepository)
        .start(fileImportFlow)
        .end()
        .build();
}
```

`Flow` gom một chuỗi step thành một đơn vị có tên. Cách này giúp job cấp cao dễ đọc hơn khi có nhiều nhóm công việc, đồng thời cho phép tái sử dụng một flow trong các job khác nhau. Nếu chỉ có vài step và không cần tái sử dụng, khai báo trực tiếp bằng `start()` và `next()` thường dễ theo dõi hơn.

## 6. Truyền dữ liệu giữa các step

Các step trong flow tuần tự có thể cần dùng chung thông tin. Spring Batch cung cấp `ExecutionContext` ở cấp job và cấp step để lưu trạng thái phù hợp.

- Job `ExecutionContext` dùng cho dữ liệu cần chia sẻ giữa các step trong cùng một JobExecution.
- Step `ExecutionContext` dành cho trạng thái riêng của một step, chẳng hạn vị trí reader hoặc checkpoint.

Ví dụ step kiểm tra lưu tên file đã xác nhận vào job context để step nhập dữ liệu sử dụng:

```java
@Component
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String fileName = "orders.csv";
        ExecutionContext jobContext =
            contribution.getStepExecution()
                .getJobExecution()
                .getExecutionContext();

        jobContext.putString("validatedFileName", fileName);
        return RepeatStatus.FINISHED;
    }
}
```

Step tiếp theo có thể đọc giá trị từ `JobExecution` tương ứng, chẳng hạn thông qua `StepExecution` được inject bằng listener hoặc qua một thành phần có scope phù hợp. Không nên dùng biến static hoặc mutable singleton để truyền dữ liệu giữa step vì job có thể chạy đồng thời nhiều instance.

Chỉ lưu dữ liệu nhỏ, ổn định và có thể serialize trong `ExecutionContext`. Không lưu stream, connection, service bean hoặc tài nguyên runtime đang mở.

## 7. Flow tuần tự và restart

Khi một job thất bại ở giữa chuỗi step, Spring Batch lưu lịch sử thực thi trong `JobRepository`. Nếu JobInstance có thể restart, lần chạy tiếp theo tiếp tục theo quy tắc restart của từng step.

Ví dụ lần chạy đầu:

```text
Execution #1
  validateInput  -> COMPLETED
  importRecords  -> FAILED
  archiveInput   -> chưa chạy
```

Khi restart cùng JobInstance với cùng identifying JobParameters, Spring Batch thường bỏ qua step đã hoàn thành và chạy lại step thất bại. Sau khi `importRecords` hoàn tất, flow tiếp tục đến `archiveInput`.

```text
Execution #2 (restart cùng JobInstance)
  validateInput  -> đã hoàn thành, mặc định bỏ qua
  importRecords  -> chạy lại theo checkpoint/policy restart
  archiveInput   -> chạy sau khi importRecords hoàn tất
```

Step đã hoàn thành có thể được cấu hình chạy lại khi restart bằng `allowStartIfComplete(true)`. Chỉ dùng tùy chọn này khi việc chạy lại step là cần thiết và an toàn, đặc biệt nếu step tạo side effect.

Restart không phải là tạo JobInstance mới. Khi cần xử lý một tập dữ liệu nghiệp vụ mới, hãy dùng identifying parameters mới. Khi cần tiếp tục công việc đang dang dở, giữ nguyên identifying parameters để Spring Batch tìm lại JobInstance cũ.

## 8. Xử lý lỗi trong flow không nhánh

Flow tuyến tính không khai báo nhánh phục hồi riêng. Nếu step lỗi, có thể xử lý nguyên nhân ở cấp step bằng retry/skip hoặc restart job sau khi khắc phục sự cố.

Ví dụ một chunk step có retry cho lỗi tạm thời và skip cho dữ liệu không hợp lệ:

```java
return new StepBuilder("importRecords", jobRepository)
    .<InputRow, Record>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidInputException.class)
    .skipLimit(20)
    .build();
```

Các chính sách này quyết định step có thể tiếp tục xử lý trong cùng execution hay không. Nếu exception không được retry/skip hoặc vượt giới hạn, step thất bại và flow tuần tự dừng tại đó.

Khi cần một nhánh xử lý lỗi riêng, chẳng hạn chuyển file không hợp lệ sang thư mục reject rồi kết thúc job theo trạng thái khác, flow cần được mở rộng bằng transition có điều kiện. Đó là một kiểu thiết kế khác với flow không nhánh.

## 9. Phân biệt flow tuần tự với conditional flow

Flow tuần tự phù hợp khi step tiếp theo luôn cố định. Conditional flow phù hợp khi kết quả của step hoặc một quyết định runtime làm thay đổi đường đi.

| Nhu cầu | Cách khai báo |
|---|---|
| A rồi B rồi C trong mọi lần chạy | `start(A).next(B).next(C)` |
| Nếu A hoàn tất thì chạy B, nếu dữ liệu sai thì chạy C | Transition với `on(...)` và `to(...)` |
| Chọn step theo JobParameters hoặc dữ liệu runtime | `JobExecutionDecider` |
| Gom một chuỗi step dùng lại | Định nghĩa `Flow` riêng |

Không cần tạo conditional flow nếu mọi lần chạy đều có cùng thứ tự và lỗi chỉ cần làm job dừng. Việc thêm nhiều nhánh không cần thiết khiến cấu hình khó đọc và khó kiểm thử hơn.

## 10. Flow tuần tự không phải vòng lặp Tasklet

`next(step)` chuyển từ một step sang step kế tiếp trong job flow. `RepeatStatus.CONTINUABLE` lại yêu cầu Spring Batch gọi lại `Tasklet.execute()` trong cùng một tasklet step.

| Cơ chế | Phạm vi lặp/chuyển |
|---|---|
| `.next(nextStep)` | Chuyển sang step khác trong flow |
| `RepeatStatus.CONTINUABLE` | Gọi lại cùng tasklet trong cùng StepExecution |
| Chunk-oriented processing | Lặp qua các chunk cho đến khi reader hết dữ liệu |

Không dùng `CONTINUABLE` để thay thế `next()` và không tạo một step riêng cho mỗi vòng lặp item. Chọn cơ chế dựa trên đơn vị công việc: một step mới, một lượt tasklet hay một chunk dữ liệu.

## 11. Đặt tên và tổ chức step trong chuỗi

Tên step nên mô tả trách nhiệm của công đoạn và giữ ổn định qua các lần triển khai nếu định nghĩa công việc không thay đổi.

Ví dụ tên có ý nghĩa:

- `validateInput`: kiểm tra đầu vào.
- `importRecords`: nhập bản ghi.
- `archiveInput`: lưu trữ nguồn.
- `publishSummary`: công bố kết quả.

Tránh các tên chung chung như `step1`, `step2` hoặc tên phụ thuộc ngày chạy. Step name được lưu trong metadata và ảnh hưởng đến việc Spring Batch nhận diện lịch sử step khi restart.

Khi tách một chuỗi step thành flow riêng, giữ tên step ổn định để metadata của các JobInstance cũ có thể được đối chiếu. Nếu thay đổi lớn cấu trúc flow hoặc trách nhiệm step, cần lập kế hoạch cho các instance còn dang dở.

## 12. Kiểm thử flow không nhánh

Kiểm thử tích hợp nên xác nhận thứ tự thực thi và hành vi khi một step thất bại.

Các tình huống chính:

1. Tất cả step hoàn tất: xác nhận thứ tự là A, B, C và JobExecution hoàn thành.
2. Step đầu thất bại: xác nhận step thứ hai và thứ ba không chạy.
3. Step giữa thất bại: xác nhận step cuối không chạy trong execution đó.
4. Restart sau lỗi: xác nhận step đã hoàn thành được xử lý theo restart policy và flow tiếp tục đúng vị trí.
5. Có nhiều JobInstance đồng thời: xác nhận state giữa các lần chạy không bị chia sẻ ngoài ý muốn.
6. Step có retry/skip: xác nhận lỗi được xử lý theo policy trước khi flow chuyển tiếp hoặc dừng.

Có thể dùng `JobLauncherTestUtils` hoặc cơ chế test tương ứng của phiên bản Spring Batch trong dự án để launch job và kiểm tra `JobExecution`, `StepExecution` cùng thứ tự step. Test nên dùng `JobRepository` phù hợp để kiểm tra metadata và restart.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ thứ tự bean quyết định thứ tự chạy | Job có thể chạy sai thứ tự mong đợi | Khai báo thứ tự bằng `start()` và `next()` |
| Bỏ qua step bắt đầu hoặc khai báo next sai | Flow thiếu công đoạn hoặc không đúng quy trình | Xác định rõ step đầu và từng step tiếp theo |
| Mong step sau chạy dù step trước thất bại | Job dừng tại step lỗi | Cấu hình retry/skip hoặc conditional transition nếu nghiệp vụ yêu cầu |
| Dùng `CONTINUABLE` để chuyển step | Tasklet bị gọi lại thay vì chuyển flow | Dùng `.next(step)` |
| Dùng biến static truyền dữ liệu giữa step | Job chạy song song có thể ghi đè state | Dùng Job `ExecutionContext` hoặc cơ chế truyền dữ liệu phù hợp |
| Đổi Step name tùy tiện | Metadata cũ không còn khớp khi restart | Giữ tên ổn định hoặc lập kế hoạch chuyển đổi |
| Tạo Flow riêng cho chuỗi quá ngắn không tái sử dụng | Cấu hình phức tạp hơn cần thiết | Khai báo trực tiếp trong JobBuilder |

## Kết luận

Flow không có nhánh biểu diễn một chuỗi step có thứ tự cố định. Trong Spring Batch 5, dùng `start(step)` để chọn điểm bắt đầu và `next(step)` để khai báo từng bước tiếp theo. Spring Batch thực thi chuỗi đó khi job được launch; step thất bại thường làm flow dừng tại vị trí lỗi.

Khi cần tái sử dụng một nhóm step, có thể đóng gói chúng thành `Flow` riêng. Hãy giữ trách nhiệm và tên step rõ ràng, truyền dữ liệu giữa step qua `ExecutionContext` khi cần, và kiểm thử cả đường chạy thành công lẫn restart. Nếu bước kế tiếp phụ thuộc vào kết quả hoặc quyết định runtime, khi đó mới cần conditional flow.
