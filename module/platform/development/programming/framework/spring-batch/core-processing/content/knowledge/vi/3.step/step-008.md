# Step name phải ổn định như thế nào?

Trong Spring Batch, tên của một `Step` là một phần của định danh được lưu trong metadata. Tên này giúp `JobRepository` nhận diện step đã chạy trong một `JobInstance`, tìm lịch sử thực thi và khôi phục trạng thái khi job được restart. Vì vậy, step name cần mô tả ổn định một công đoạn xử lý trong job qua các lần triển khai.

Nếu đổi tên step tùy tiện, Spring Batch có thể xem step đó là một step mới và chạy lại từ đầu. Nếu giữ nguyên tên cho một công đoạn đã đổi ý nghĩa, Spring Batch có thể xem nó như step cũ và áp dụng lịch sử hoặc checkpoint không còn phù hợp. Cả hai trường hợp đều có thể làm sai hành vi restart.

## 1. Step name là định danh trong metadata

Khi tạo step, tên được truyền vào `StepBuilder` trở thành tên của đối tượng `Step` và được ghi vào `StepExecution` mỗi khi step chạy.

Ví dụ theo API của Spring Batch 5:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    return new StepBuilder("validateInput", jobRepository)
        .tasklet(validateInputTasklet, transactionManager)
        .build();
}
```

Trong ví dụ này, `validateInput` là Step name. Tên method `validateInputStep` là tên method khai báo bean; tên bean Spring cũng có thể được cấu hình riêng. Metadata của Spring Batch sử dụng tên mà `Step` trả về qua `getName()`, tức giá trị truyền cho `StepBuilder`.

Khi step được thực thi, Spring Batch tạo một `StepExecution` chứa thông tin như tên step, trạng thái, thời gian bắt đầu/kết thúc, số bản ghi đọc/ghi và `ExecutionContext`. Trong schema metadata mặc định, tên step được lưu ở cột `STEP_NAME` của bảng `BATCH_STEP_EXECUTION`.

## 2. Tên step ảnh hưởng đến restart như thế nào?

`JobInstance` được xác định bởi tên job cùng các identifying `JobParameters`. Bên trong một JobInstance, Spring Batch dùng step name để tìm lịch sử thực thi của từng công đoạn. Khi restart, framework cần biết step nào đã hoàn thành, step nào cần chạy lại và trạng thái nào có thể được khôi phục.

Ví dụ job có ba step:

```text
JobInstance: importOrders(businessDate=2026-11-15)

  Execution #1
    validateInput  -> COMPLETED
    importOrders   -> FAILED
    archiveFile    -> chưa chạy

  Restart: Execution #2
    validateInput  -> bỏ qua vì đã hoàn thành
    importOrders   -> chạy lại theo chính sách restart
    archiveFile    -> chạy sau khi importOrders hoàn tất
```

Các step có tên ổn định giúp Spring Batch đối chiếu execution mới với lịch sử của cùng JobInstance. Nếu đổi `importOrders` thành `loadOrders` giữa lúc JobInstance còn dang dở, framework có thể không tìm thấy lịch sử của step theo tên cũ. Step mới có thể được xem là chưa từng chạy và bắt đầu lại từ đầu.

Điều đó đặc biệt quan trọng nếu step đã tạo side effect trước khi thất bại, chẳng hạn ghi dữ liệu vào hệ thống ngoài hoặc gửi thông báo. Chạy lại từ đầu có thể tạo bản ghi trùng hoặc lặp thao tác.

## 3. Đổi tên step có thể làm mất liên kết với lịch sử cũ

Giả sử phiên bản đầu của job dùng tên `importOrders`:

```java
new StepBuilder("importOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();
```

Sau một lần triển khai, nhóm phát triển đổi tên thành `processOrders` chỉ để tên code dễ đọc hơn:

```java
new StepBuilder("processOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();
```

Với một JobInstance đã chạy bằng phiên bản cũ nhưng chưa hoàn thành, tên mới không còn khớp với `StepExecution` trước đó. Khi restart, `processOrders` có thể được xem như một công đoạn mới. Spring Batch không tự hiểu rằng `processOrders` chính là `importOrders` được đổi tên trong mã nguồn.

Vì vậy, đổi tên step không đơn thuần là đổi nhãn hiển thị. Nó có thể thay đổi cách framework tìm execution trước đó, cách áp dụng giới hạn số lần chạy và cách quyết định step đã hoàn thành có cần chạy lại hay không.

## 4. Giữ tên ổn định qua các lần refactor

Khi chỉ đổi tên class, method, package hoặc cấu trúc cấu hình Java mà công đoạn nghiệp vụ vẫn là cùng một step, hãy giữ nguyên tên được truyền vào `StepBuilder`.

Ví dụ, có thể đổi tên method bean mà không đổi định danh metadata:

```java
// Tên method bean mới
@Bean
Step inputValidation(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    // Giữ Step name đã được dùng trong các lần chạy trước
    return new StepBuilder("validateInput", jobRepository)
        .tasklet(validateInputTasklet, transactionManager)
        .build();
}
```

Các thay đổi sau thường không đòi hỏi đổi Step name:

- Đổi tên method `@Bean` hoặc tên biến trong Java.
- Chuyển cấu hình step sang class cấu hình khác.
- Tách tasklet hoặc reader/writer thành các bean riêng.
- Refactor nội bộ nhưng vẫn giữ cùng trách nhiệm xử lý và khả năng khôi phục checkpoint.
- Cải thiện hiệu năng mà không làm thay đổi ý nghĩa của dữ liệu trạng thái đã lưu.

Tên step nên đại diện cho vai trò ổn định của công đoạn, không phản ánh chi tiết triển khai tạm thời.

## 5. Quy tắc đặt tên dễ duy trì

Chọn tên ngắn, có nghĩa, nhất quán và mô tả công việc. Ví dụ:

| Tên nên dùng | Ý nghĩa |
|---|---|
| `validateInput` | Kiểm tra dữ liệu đầu vào |
| `readOrders` | Đọc đơn hàng |
| `transformOrders` | Chuyển đổi đơn hàng |
| `writeOrders` | Ghi đơn hàng |
| `archiveInputFile` | Lưu trữ tệp đầu vào |
| `publishSummary` | Công bố báo cáo tổng hợp |

Nên áp dụng các nguyên tắc sau:

1. **Dùng tên theo trách nhiệm nghiệp vụ.** Người đọc metadata hoặc log có thể hiểu step đang làm gì mà không cần mở code.
2. **Giữ một quy ước đặt tên.** Chẳng hạn dùng lower camel case cho tất cả step trong dự án.
3. **Tránh tên quá chung.** `step1`, `process`, `taskA` không cho biết vai trò của công đoạn.
4. **Tránh gắn dữ liệu runtime vào tên.** Ngày xử lý, tenant, tên tệp, UUID hoặc timestamp nên là JobParameters hay dữ liệu trong `ExecutionContext`.
5. **Đặt tên riêng cho các công đoạn logic khác nhau.** Không dùng một tên cho hai step khác trách nhiệm chỉ vì chúng cùng gọi một service.
6. **Không dùng tên hiển thị hoặc tên dịch theo ngôn ngữ người dùng.** Step name là định danh kỹ thuật cần ổn định.

Ví dụ không nên tạo tên theo ngày chạy:

```java
// Không nên: mỗi ngày tạo ra một định danh step khác nhau
String stepName = "importOrders-" + businessDate;
```

Thay vào đó, giữ tên step cố định và truyền ngày nghiệp vụ qua JobParameters:

```java
new StepBuilder("importOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();

// businessDate được truyền trong JobParameters của JobExecution
```

JobParameters xác định đơn vị công việc; Step name xác định công đoạn trong đơn vị công việc đó. Không nên dùng một khái niệm để thay thế khái niệm còn lại.

## 6. Step name cần duy nhất trong phạm vi job

Về mặt thiết kế, mỗi công đoạn logic trong cùng một job nên có Step name riêng. Tránh khai báo hai step khác nhau với cùng tên, kể cả khi chúng dùng chung một loại tasklet hoặc cùng gọi một service.

Ví dụ hai công đoạn có chung cách triển khai nhưng có trách nhiệm khác nhau:

```java
@Bean
Step validateCustomerFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet customerValidationTasklet) {
    return new StepBuilder("validateCustomerFile", jobRepository)
        .tasklet(customerValidationTasklet, transactionManager)
        .build();
}

@Bean
Step validateProductFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet productValidationTasklet) {
    return new StepBuilder("validateProductFile", jobRepository)
        .tasklet(productValidationTasklet, transactionManager)
        .build();
}
```

Không cần tạo tên toàn cục duy nhất cho mọi job trong ứng dụng. Hai job khác nhau có thể có step cùng tên nếu chúng là hai định nghĩa job riêng. Tuy nhiên, trong cùng một JobInstance, tên cần phân biệt các công đoạn để lịch sử và chính sách restart không bị nhập nhằng.

Nếu muốn tái sử dụng logic, hãy tái sử dụng tasklet, reader, writer hoặc service; mỗi vị trí xử lý logic trong job vẫn nên có Step name thể hiện vai trò của nó.

## 7. Tên step và ExecutionContext

`ExecutionContext` chứa trạng thái mà step cần lưu để tiếp tục sau khi restart, chẳng hạn vị trí đọc cuối cùng, số trang đã xử lý hoặc mã lô hiện tại. Trạng thái này được lưu gắn với `StepExecution` trong JobRepository.

Khi Step name thay đổi, Spring Batch có thể tạo một `StepExecution` mới thay vì tìm lại execution cũ theo tên. Khi đó, execution mới có `ExecutionContext` riêng và không tự động khôi phục checkpoint của step cũ.

Ví dụ reader có lưu vị trí đọc:

```text
Step name: readOrders

Execution #1
  chunk 1 -> commit
  chunk 2 -> commit
  chunk 3 -> lỗi
  ExecutionContext lưu vị trí sau chunk 2

Restart cùng Step name
  tìm lại StepExecution trước
  khôi phục trạng thái reader
  tiếp tục sau chunk 2
```

Nếu đổi tên `readOrders` thành `loadOrders` trước khi restart, step mới có thể không dùng lại checkpoint được lưu cho tên cũ. Nó có thể đọc lại từ đầu hoặc khởi tạo trạng thái mới, tùy reader và cấu hình.

Ngoài Step name, cấu trúc dữ liệu trong `ExecutionContext` cũng cần tương thích giữa các phiên bản code. Giữ nguyên tên step không bảo đảm restart thành công nếu phiên bản mới không còn hiểu các key hoặc kiểu dữ liệu đã lưu. Khi thay đổi cấu trúc checkpoint, hãy thiết kế chiến lược tương thích hoặc xử lý các JobInstance cũ trước khi triển khai.

## 8. Ảnh hưởng đến startLimit và allowStartIfComplete

Một số chính sách step dựa trên lịch sử `StepExecution` của JobInstance:

- `startLimit(n)` giới hạn số lần step được bắt đầu.
- `allowStartIfComplete(true)` cho phép step đã hoàn thành được chạy lại khi job được restart.

Ví dụ:

```java
Step refreshReferenceData = new StepBuilder("refreshReferenceData", jobRepository)
    .tasklet(refreshTasklet, transactionManager)
    .allowStartIfComplete(true)
    .startLimit(3)
    .build();
```

Các chính sách này dựa vào lịch sử thực thi của step. Nếu đổi tên step, lịch sử theo tên mới có thể không chứa những lần bắt đầu hoặc trạng thái hoàn thành của tên cũ. Hệ quả có thể là step chạy lại ngoài dự kiến hoặc giới hạn chạy không còn phản ánh số lần thử trước đó.

Ngược lại, nếu giữ nguyên tên cho một step mới có ý nghĩa khác, Spring Batch có thể áp dụng lịch sử hoàn thành hoặc giới hạn của công đoạn cũ cho công đoạn mới. Vì thế, tên phải ổn định khi trách nhiệm không đổi và phải được thay đổi có chủ đích khi định nghĩa công việc thực sự thay đổi.

## 9. Khi nào nên đổi tên step?

Không phải mọi thay đổi code đều yêu cầu tên mới. Hãy phân biệt thay đổi triển khai với thay đổi định nghĩa công việc.

| Thay đổi | Khuyến nghị |
|---|---|
| Đổi tên method hoặc class cấu hình | Giữ Step name |
| Tối ưu reader/writer nhưng checkpoint vẫn tương thích | Giữ Step name |
| Sửa lỗi xử lý nhưng vẫn cùng trách nhiệm và có thể restart an toàn | Thường giữ Step name |
| Tách một step thành hai công đoạn có trách nhiệm riêng | Đặt tên riêng cho các step mới và lập kế hoạch cho JobInstance đang dang dở |
| Gộp nhiều step thành một step có trạng thái khác | Xử lý rõ các execution cũ trước khi thay đổi flow và tên |
| Thay đổi ý nghĩa nghiệp vụ hoặc định dạng checkpoint không tương thích | Xem đây là thay đổi phiên bản quy trình và thiết kế chuyển đổi có chủ đích |

Đổi tên step khi trách nhiệm của nó đã thay đổi đáng kể có thể giúp phân biệt metadata của quy trình mới. Tuy nhiên, với các JobInstance cũ chưa hoàn thành, tên mới có thể khiến công đoạn chạy lại từ đầu. Hãy xác định cách xử lý các instance này trước khi phát hành.

## 10. Chiến lược triển khai khi cần thay đổi Step name

Khi thực sự cần đổi tên hoặc thay đổi cấu trúc các step, hãy lập kế hoạch dựa trên trạng thái job đang tồn tại:

1. **Xác định JobInstance còn dang dở.** Kiểm tra các execution đang chạy, thất bại hoặc dừng có thể cần restart.
2. **Đánh giá khả năng tương thích.** Xác định code mới có thể tiếp tục từ `ExecutionContext` cũ hay không và các side effect nào có thể bị lặp.
3. **Chọn cách chuyển tiếp.** Có thể để các instance cũ hoàn tất bằng phiên bản cũ, duy trì logic tương thích trong giai đoạn chuyển đổi, hoặc tạo định nghĩa job mới nếu đây thực sự là quy trình mới.
4. **Kiểm tra tính idempotent.** Nếu step có thể chạy lại từ đầu, bảo đảm việc ghi dữ liệu hoặc gọi dịch vụ ngoài không gây kết quả trùng lặp.
5. **Thử restart với metadata đại diện.** Kiểm tra cả trường hợp step trước đã hoàn thành, step hiện tại thất bại giữa chừng và step có checkpoint.

Đổi Job name hoặc thêm identifying JobParameter phiên bản có thể tạo JobInstance mới. Đây là lựa chọn để tách một định nghĩa quy trình mới khỏi lịch sử cũ, nhưng execution mới sẽ không phải là restart của JobInstance trước. Nếu cần tiếp tục một JobInstance đang dang dở, việc tạo định danh mới sẽ không giải quyết nhu cầu đó.

Không nên sửa trực tiếp cột `STEP_NAME` trong bảng metadata chỉ để làm cho tên mới khớp với lịch sử cũ. Metadata có quan hệ với StepExecution, ExecutionContext và các bảng liên quan; cập nhật thủ công có thể làm sai liên kết hoặc trạng thái. Nếu bắt buộc phải di chuyển metadata, cần một quy trình migration được thiết kế, sao lưu và kiểm chứng riêng.

## 11. Step name trong job partitioned

Với partitioned step, Spring Batch tạo nhiều `StepExecution` cho các partition. Tên execution của worker thường được tạo từ tên step nền cùng tên partition, ví dụ `processOrders:partition0` và `processOrders:partition1`.

```text
processOrders
  +-- processOrders:partition0
  +-- processOrders:partition1
  +-- processOrders:partition2
```

Tên step nền vẫn cần ổn định. Tên partition cũng nên xác định ổn định cùng một đơn vị dữ liệu giữa các lần restart, để framework có thể đối chiếu trạng thái partition tương ứng. Không tự thêm timestamp hoặc UUID vào tên partition nếu mục tiêu là khôi phục cùng partition ở lần chạy sau.

Quy tắc cụ thể của tên worker phụ thuộc vào partition handler và cách đặt tên partition. Hãy để cơ chế partition tạo tên theo quy ước nhất quán, đồng thời bảo đảm partition key đại diện cho một phân vùng công việc ổn định.

## 12. Checklist khi khai báo Step name

Trước khi đưa một step vào job, hãy tự kiểm tra các câu hỏi sau:

- Tên có mô tả rõ trách nhiệm của công đoạn không?
- Tên có giữ nguyên qua các lần deploy khi trách nhiệm và định nghĩa checkpoint vẫn tương thích không?
- Tên có vô tình chứa ngày, tệp, tenant, UUID hoặc dữ liệu runtime không?
- Có step logic khác trong cùng job đang dùng trùng tên không?
- Nếu tên thay đổi, các JobInstance cũ đang chạy hoặc cần restart sẽ được xử lý thế nào?
- Nếu giữ tên cho logic mới, lịch sử hoàn thành và ExecutionContext cũ có còn phù hợp không?
- Với partitioned step, tên partition có ổn định giữa các lần restart không?

Có thể kiểm tra tên Step ở mức cấu hình bằng `step.getName()` và kiểm tra metadata trong cơ sở dữ liệu khi điều tra vấn đề restart. Các kiểm tra tích hợp nên dùng một JobRepository có lưu metadata thật để xác nhận hành vi qua nhiều JobExecution.

## Kết luận

Step name là định danh metadata của một công đoạn trong Spring Batch. `JobRepository` dùng tên này cùng lịch sử của JobInstance để nhận diện StepExecution trước đó, quyết định step đã hoàn thành hay cần chạy lại và khôi phục trạng thái phù hợp.

Hãy đặt tên mô tả trách nhiệm nghiệp vụ, duy nhất cho từng công đoạn logic trong cùng job và giữ ổn định qua các lần refactor, triển khai và restart. Chỉ đổi tên khi định nghĩa công việc thực sự thay đổi, đồng thời phải có kế hoạch cho các JobInstance cũ, checkpoint và side effect có thể được thực hiện lại.
