# Context khi step thất bại trong Spring Batch

Trong Spring Batch, `ExecutionContext` lưu trạng thái cần thiết để một job hoặc step có thể tiếp tục sau khi bị dừng hay thất bại. Khi step xử lý thành công, context có thể chứa checkpoint của reader, khóa cuối cùng đã xử lý hoặc những thông tin cần chuyển sang step tiếp theo. Khi step thất bại giữa chừng, điều quan trọng là biết giá trị nào đã được lưu bền vững, giá trị nào thuộc chunk chưa commit và dữ liệu nào có thể được khôi phục trong lần restart.

`ExecutionContext` không phải một vùng nhớ tự động lưu mọi thay đổi của ứng dụng. Spring Batch quản lý việc lưu context tại các điểm trong vòng đời job/step, thường gắn với ranh giới commit của chunk và quá trình cập nhật execution. Vì vậy, khi điều tra lỗi, cần phân biệt **context của step**, **context của job**, checkpoint đã commit và thay đổi mới chỉ tồn tại trong bộ nhớ.

## 1. ExecutionContext là gì?

`ExecutionContext` là một vùng lưu trữ dạng key-value được gắn với một lần thực thi job hoặc step. Các thành phần batch dùng nó để lưu những giá trị cần tồn tại qua các lần gọi hoặc có thể khôi phục khi restart.

Ví dụ, reader đọc file có thể lưu số dòng đã đọc; step xử lý dữ liệu có thể lưu mã lô hiện tại; một step tổng hợp có thể lưu đường dẫn file báo cáo được tạo.

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putLong("lastProcessedId", 12500L);
context.putString("inputFile", "orders-2026-11-15.csv");
```

`ExecutionContext` hỗ trợ các kiểu giá trị cơ bản và object phù hợp với serializer đang dùng. Dữ liệu được lưu trong repository theo phạm vi execution. Với JDBC repository mặc định, metadata context được lưu trong các bảng như `BATCH_STEP_EXECUTION_CONTEXT` và `BATCH_JOB_EXECUTION_CONTEXT`.

Context nên chứa trạng thái nhỏ, cần thiết để khôi phục. Không nên dùng nó làm nơi lưu toàn bộ dữ liệu nghiệp vụ, object graph lớn, connection, stream, service bean hoặc tài nguyên không thể serialize.

## 2. Phân biệt StepExecutionContext và JobExecutionContext

Spring Batch có hai phạm vi context chính:

| Context | Gắn với | Mục đích |
| --- | --- | --- |
| `StepExecution.getExecutionContext()` | Một `StepExecution` cụ thể | Lưu checkpoint và trạng thái riêng của step đó. |
| `JobExecution.getExecutionContext()` | Một `JobExecution` cụ thể | Lưu trạng thái ở phạm vi job, có thể được dùng giữa các step trong cùng lần thực thi. |

Ví dụ, job có ba step:

```text
JobExecution
  JobExecutionContext
       |
       +-- ValidateStep / StepExecution
       |       StepExecutionContext
       |
       +-- ImportStep / StepExecution
       |       StepExecutionContext
       |
       +-- ReportStep / StepExecution
               StepExecutionContext
```

Mỗi step có context riêng. `ImportStep` không tự động nhìn thấy mọi key trong `ValidateStep` context. Nếu cần chuyển một số giá trị từ step trước sang job context để step sau đọc, có thể dùng `ExecutionContextPromotionListener` hoặc cập nhật job context qua cơ chế phù hợp.

Job context thuộc một `JobExecution`, không phải một kho dữ liệu dùng chung vĩnh viễn cho mọi lần chạy của `JobInstance`. Khi restart, Spring Batch có thể khởi tạo execution mới từ trạng thái đã lưu của execution trước theo cơ chế restart của repository. Vì vậy, cần hiểu rõ dữ liệu nào được kế thừa trong cùng một luồng restart và không coi context là kho lưu trữ nghiệp vụ dài hạn.

## 3. Context được lưu vào lúc nào?

Với chunk-oriented step, Spring Batch cập nhật trạng thái step và execution context ở các ranh giới xử lý chunk. Các reader/writer triển khai `ItemStream` có thể ghi checkpoint qua callback `update(ExecutionContext)`. Step lưu context vào `JobRepository` cùng với thông tin execution theo cơ chế transaction của step.

Vòng đời khái quát của một chunk:

```text
BEGIN CHUNK TRANSACTION
        |
        v
READ -> PROCESS -> WRITE
        |
        v
ItemStream.update(step ExecutionContext)
        |
        v
JobRepository cập nhật execution/context
        |
        v
COMMIT
```

Nếu transaction commit thành công, checkpoint của chunk đó được lưu bền vững. Nếu transaction rollback và metadata cùng tham gia transaction tương ứng, các cập nhật metadata của chunk chưa commit cũng bị rollback. Khi đó, checkpoint đã commit trước đó là mốc đáng tin cậy để restart.

Với tasklet step, mỗi lần thực thi tasklet cũng được điều phối trong transaction theo cấu hình step. Context được lưu theo vòng đời cập nhật của step; không nên giả định mọi thay đổi trong bộ nhớ tự động được ghi xuống repository ngay khi một dòng code gọi `putString()`.

Job context thường được cập nhật và lưu ở các điểm quản lý execution của job, chẳng hạn khi step kết thúc hoặc khi một thành phần chủ động cập nhật repository. Nếu step thất bại, hãy kiểm tra chính xác thời điểm context được cập nhật và transaction nào đã commit trước khi kết luận một key có thể được dùng trong lần restart.

## 4. Điều gì xảy ra với StepExecutionContext khi step thất bại?

Giả sử step đọc dữ liệu theo chunk 100 item. Hai chunk đầu đã commit, nhưng chunk thứ ba gặp lỗi:

```text
Chunk 1: item 1..100    -> ghi dữ liệu + checkpoint 100 -> COMMIT
Chunk 2: item 101..200  -> ghi dữ liệu + checkpoint 200 -> COMMIT
Chunk 3: item 201..300  -> lỗi tại item 260 -> ROLLBACK
```

Nếu reader lưu checkpoint ở ranh giới chunk, `StepExecutionContext` bền vững sẽ phản ánh checkpoint gần nhất đã commit, ví dụ item 200. Các thay đổi context của chunk thứ ba chưa commit sẽ không trở thành checkpoint bền vững. Khi restart, reader có thể khôi phục từ checkpoint sau item 200 và đọc lại phần việc của chunk thứ ba.

Điều này phụ thuộc reader thực sự triển khai và sử dụng checkpoint đúng cách. Một reader chỉ giữ con trỏ trong bộ nhớ, không ghi trạng thái vào `ExecutionContext`, không thể tự khôi phục chính xác vị trí chỉ nhờ Spring Batch.

Step thất bại vẫn có `StepExecution` và context gắn với nó. Context có thể được dùng để chẩn đoán, xem checkpoint cuối cùng hoặc làm đầu vào cho lần restart. Tuy nhiên, không nên coi những giá trị vừa được ghi vào object trong bộ nhớ trước khi lỗi xảy ra là dữ liệu đã lưu bền vững.

## 5. JobExecutionContext khi một step thất bại

Job context có phạm vi toàn job execution. Nó có thể chứa dữ liệu mà các step cần chia sẻ, ví dụ mã lô, tên file đầu vào hoặc đường dẫn kết quả. Khi một step thất bại, job context có thể vẫn chứa những giá trị đã được lưu từ trước đó.

Ví dụ:

```text
JobExecutionContext
  batchId = BATCH-20261115
  inputFile = orders.csv

ValidateStep: COMPLETED
  StepExecutionContext
    validRecordCount = 1200

ImportStep: FAILED
  StepExecutionContext
    lastProcessedId = 800

ReportStep: chưa chạy
```

Trong ví dụ này, job context có thể giữ `batchId` và `inputFile` đã được thiết lập trước đó. `ImportStep` có context riêng với checkpoint cuối cùng đã lưu. `ReportStep` chưa chạy nên chưa có kết quả của step đó.

Không nên mặc định rằng mọi key được ghi trong job context ngay trước khi step lỗi đều đã được lưu. Nếu job context được thay đổi trong một callback hoặc logic đang chạy, cần xác định điểm `JobRepository` cập nhật context và trạng thái transaction. Khi cần truyền dữ liệu từ step sang step, hãy dùng cơ chế promotion và kiểm tra trạng thái step trước khi phụ thuộc vào key.

## 6. Ví dụ reader lưu checkpoint bằng ItemStream

Một reader hỗ trợ restart thường triển khai `ItemStreamReader<T>`. Ví dụ sau minh họa reader đọc danh sách bản ghi theo vị trí và lưu vị trí đọc trong step context:

```java
public class CheckpointingOrderReader
        implements ItemStreamReader<Order> {

    private static final String INDEX_KEY = "orderReader.currentIndex";

    private final List<Order> orders;
    private int currentIndex;

    public CheckpointingOrderReader(List<Order> orders) {
        this.orders = orders;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        if (executionContext.containsKey(INDEX_KEY)) {
            currentIndex = executionContext.getInt(INDEX_KEY);
        } else {
            currentIndex = 0;
        }
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }
        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(INDEX_KEY, currentIndex);
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên nếu reader có mở file/connection.
    }
}
```

`open()` khôi phục index từ context đã lưu; `read()` trả về item tiếp theo; `update()` ghi index hiện tại để checkpoint. Ví dụ dùng list cố định để tập trung vào API `ItemStream`. Trong production, reader cần đọc từ nguồn có thứ tự ổn định và lưu checkpoint có ý nghĩa với nguồn đó, chẳng hạn vị trí dòng file hoặc khóa cuối cùng đã đọc.

Nếu chunk chứa item 1 đến 100 commit thành công, context có thể lưu index 100. Nếu chunk kế tiếp thất bại trước commit, lần restart sẽ dùng checkpoint bền vững gần nhất. Không nên tăng checkpoint bền vững ở một hệ thống ngoài trước khi transaction chunk xác nhận dữ liệu tương ứng.

## 7. Cách đọc context sau khi step thất bại

Sau khi job kết thúc với trạng thái `FAILED`, ứng dụng có thể truy vấn execution qua `JobExplorer` hoặc lấy object execution từ luồng khởi chạy. Ví dụ:

```java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    ExecutionContext jobContext = execution.getExecutionContext();

    for (StepExecution stepExecution : execution.getStepExecutions()) {
        ExecutionContext stepContext = stepExecution.getExecutionContext();

        System.out.println("step=" + stepExecution.getStepName());
        System.out.println("status=" + stepExecution.getStatus());

        if (stepContext.containsKey("lastProcessedId")) {
            System.out.println(
                "lastProcessedId=" + stepContext.getLong("lastProcessedId")
            );
        }
    }

    if (jobContext.containsKey("batchId")) {
        System.out.println("batchId=" + jobContext.getString("batchId"));
    }
}
```

Đây là ví dụ đọc context để chẩn đoán. Trong hệ thống thật, không nên in toàn bộ context ra log nếu nó chứa dữ liệu nhạy cảm. Chỉ đọc những key cần thiết và bảo vệ quyền truy cập vào metadata repository.

Khi truy vấn lại bằng `JobExplorer`, kết quả phản ánh dữ liệu được repository lưu. Nó có giá trị hơn việc chỉ đọc một object `StepExecution` còn nằm trong bộ nhớ của thread đã thất bại, vì object trong bộ nhớ có thể chứa thay đổi chưa commit.

## 8. Chuyển dữ liệu từ step context sang job context

Một step có thể tạo ra giá trị cần dùng ở step kế tiếp. Ví dụ `ValidateStep` đếm số bản ghi hợp lệ, còn `ImportStep` cần đọc số lượng đó để ghi log hoặc kiểm tra điều kiện. Có thể dùng `ExecutionContextPromotionListener` để đưa một số key từ step context lên job context.

```java
@Bean
ExecutionContextPromotionListener validationContextPromotionListener() {
    ExecutionContextPromotionListener listener =
        new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"validRecordCount", "validationReport"});
    listener.setStatuses(new String[] {"COMPLETED"});
    return listener;
}
```

Gắn listener vào step:

```java
@Bean
Step validateStep(JobRepository jobRepository,
                  PlatformTransactionManager transactionManager,
                  ItemReader<Record> reader,
                  ItemWriter<Record> writer,
                  ExecutionContextPromotionListener validationContextPromotionListener) {
    return new StepBuilder("validateStep", jobRepository)
        .<Record, Record>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .listener(validationContextPromotionListener)
        .build();
}
```

Theo cấu hình trên, các key được chỉ định chỉ được promote khi exit status của step khớp `COMPLETED`. Đây là mặc định an toàn thường dùng: dữ liệu chỉ được chuyển lên job context khi step kết thúc theo trạng thái được chấp nhận.

Nếu step thất bại, listener mặc định không promote các key vì trạng thái `FAILED` không khớp `COMPLETED`. Có thể cấu hình status khác, nhưng chỉ nên làm vậy khi dữ liệu được promote có ý nghĩa rõ ràng dù step thất bại. Không nên vô tình chuyển một checkpoint chưa hoàn tất thành kết quả nghiệp vụ được step sau tin cậy.

## 9. Điều gì xảy ra khi restart một job?

Restart tạo một `JobExecution` mới cho cùng `JobInstance` nếu job và trạng thái trước đó cho phép restart. Spring Batch dùng metadata execution trước đó để khôi phục trạng thái cần thiết, bao gồm job context và step context phù hợp với quy tắc restart.

Ví dụ:

```text
JobInstance: importOrders (businessDate=2026-11-15)
    |
    +-- JobExecution 1: FAILED
    |      JobExecutionContext: batchId=B-15
    |      ImportStep StepExecution:
    |        StepExecutionContext: lastProcessedId=200
    |
    +-- JobExecution 2: restart
           Context được khôi phục từ metadata restart
           ImportStep tiếp tục từ checkpoint phù hợp
```

Restart không có nghĩa mọi step đều chạy lại từ đầu. Step đã hoàn thành có thể được bỏ qua theo quy tắc flow/restart; step thất bại hoặc step cần chạy lại được điều phối dựa trên trạng thái và metadata. Nếu cần thực hiện lại một step đã hoàn thành, cần thiết kế flow và restart behavior tương ứng, không sửa context thủ công để ép framework.

Các giá trị context được khôi phục phải còn tương thích với code hiện tại. Nếu đổi tên key, kiểu dữ liệu hoặc cấu trúc object đã serialize, execution cũ có thể không đọc được. Khi nâng cấp ứng dụng, cần giữ tương thích ngược hoặc có quy trình chuyển đổi context đã lưu.

## 10. Context trong failed chunk và retry trong cùng execution

Restart sau khi một `JobExecution` kết thúc và retry trong lúc execution còn đang chạy là hai tình huống khác nhau.

- **Retry trong cùng execution:** framework xử lý lại thao tác/chunk theo fault-tolerance policy. Các cập nhật transactional chưa commit cần được rollback hoặc phục hồi theo cơ chế của step.
- **Restart sau khi execution thất bại:** framework tạo execution mới và khôi phục trạng thái từ metadata bền vững của execution trước.

Không nên dựa vào giá trị mutable trong `ExecutionContext` object còn ở bộ nhớ sau một rollback. Transaction rollback bảo vệ dữ liệu repository khi các cập nhật tham gia cùng transaction, nhưng object Java đã bị sửa không tự động quay về snapshot cũ chỉ vì database rollback. Cơ chế retry của framework và `ItemStream` quản lý trạng thái đọc theo vòng đời step; reader tùy chỉnh phải tuân theo hợp đồng này và không tự duy trì checkpoint sai lệch.

Nếu một processor hoặc listener tự ghi một key vào step context rồi ngay sau đó ném exception, đừng giả định key đó đã được lưu. Hãy kiểm tra repository sau khi execution kết thúc và thiết kế logic dựa trên checkpoint đã commit.

## 11. Context không thay thế dữ liệu nghiệp vụ

`ExecutionContext` phù hợp cho checkpoint và trạng thái điều phối. Nó không nên trở thành nơi duy nhất lưu kết quả nghiệp vụ mà người dùng cần truy vấn lâu dài.

Ví dụ, lưu `lastProcessedOrderId` trong step context là hợp lý để reader tiếp tục. Nhưng lưu toàn bộ thông tin thanh toán, nội dung đơn hàng hoặc kết quả báo cáo vào context là không phù hợp. Những dữ liệu đó nên nằm trong bảng nghiệp vụ, file kết quả hoặc kho dữ liệu được quản lý riêng.

Lý do:

- Context được gắn với execution và có thể được sao chép khi restart; nó không phải mô hình dữ liệu nghiệp vụ ổn định.
- Payload lớn làm metadata phình to và tăng chi phí serialize/deserialize.
- Dữ liệu có thể chứa thông tin nhạy cảm và khó áp dụng chính sách retention phù hợp.
- Schema/class thay đổi có thể khiến context cũ không deserialize được.
- Xóa metadata để dọn lịch sử có thể làm mất checkpoint hoặc context cần cho restart.

Hãy lưu trong context một định danh hoặc checkpoint nhỏ, rồi truy vấn dữ liệu nghiệp vụ từ nơi lưu trữ chính thức.

## 12. Quy tắc đặt key và kiểu dữ liệu

Key context cần có tên rõ ràng, ổn định và tránh trùng giữa các reader/listener/step. Có thể dùng tiền tố theo thành phần:

```java
private static final String LAST_ID_KEY = "orderReader.lastId";
private static final String FILE_NAME_KEY = "orderReader.fileName";
private static final String VALID_COUNT_KEY = "validation.validCount";
```

Nên ưu tiên kiểu dữ liệu đơn giản như string, số, boolean, ngày giờ được biểu diễn ổn định hoặc object nhỏ có serializer tương thích. Với object tùy chỉnh, cần cân nhắc serializer, versioning và khả năng đọc lại sau khi deploy phiên bản mới.

Không lưu:

- `DataSource`, `Connection`, `EntityManager` hoặc repository.
- `InputStream`, `Reader`, cursor hoặc file handle đang mở.
- Spring bean, service, proxy hoặc object có tham chiếu đến application context.
- Collection rất lớn hoặc toàn bộ dữ liệu của chunk.
- Object có cấu trúc thay đổi không có chiến lược tương thích.

Lưu định danh và trạng thái cần khôi phục, sau đó tái tạo resource trong `open()` hoặc khi step được khởi tạo.

## 13. Lỗi thường gặp khi step thất bại

**Cho rằng mọi key trong context đều đã lưu:** chỉ các cập nhật đã được repository ghi bền vững mới là checkpoint đáng tin cậy. Thay đổi trong chunk chưa commit có thể bị rollback.

**Nhầm step context với job context:** hai phạm vi khác nhau. Step sau không tự động nhận mọi key của step trước; dùng promotion listener hoặc cơ chế chia sẻ rõ ràng.

**Promote dữ liệu của step thất bại:** listener mặc định chỉ promote khi exit status khớp `COMPLETED`. Nếu mở rộng status, hãy xác định key có còn hợp lệ khi step thất bại hay không.

**Dùng context làm database nghiệp vụ:** context nên nhỏ và phục vụ restart/điều phối. Dữ liệu nghiệp vụ phải được lưu ở kho chính thức.

**Lưu object không serialize được:** connection, stream hoặc Spring bean không phù hợp để lưu trong context. Lưu định danh và khôi phục resource khi mở step.

**Đổi kiểu hoặc tên key khi deploy:** execution cũ có thể không đọc được. Giữ tương thích hoặc chuyển đổi có kiểm soát.

**Tin vào object trong bộ nhớ sau rollback:** object context có thể vẫn giữ giá trị vừa được sửa dù transaction database đã rollback. Đọc lại từ repository để xác định checkpoint bền vững.

**Không kiểm tra context khi restart:** job có thể tiếp tục từ vị trí sai nếu reader lưu checkpoint không đúng. Kiểm thử lỗi giữa chunk và restart với dữ liệu thật hoặc fixture có trạng thái xác định.

## 14. Kiểm thử context khi step thất bại

Nên có test mô phỏng step commit một hoặc nhiều chunk rồi thất bại ở chunk kế tiếp. Test cần xác nhận:

1. Step có trạng thái `FAILED` và execution được lưu trong repository.
2. Step context chứa checkpoint cuối cùng đã commit.
3. Giá trị được ghi trong chunk thất bại chưa được xem là checkpoint bền vững.
4. Job context chỉ chứa các key đã được lưu theo đúng vòng đời.
5. Khi restart cùng `JobInstance`, reader khôi phục từ checkpoint đã lưu.
6. Các step đã hoàn thành được xử lý theo restart behavior dự kiến.

Ví dụ assertion sau khi lấy execution từ repository:

```java
JobExecution failedExecution = jobExplorer.getJobExecution(executionId);
assertThat(failedExecution).isNotNull();
assertThat(failedExecution.getStatus()).isEqualTo(BatchStatus.FAILED);

StepExecution failedStep = failedExecution.getStepExecutions().stream()
    .filter(step -> step.getStepName().equals("importStep"))
    .findFirst()
    .orElseThrow();

assertThat(failedStep.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(failedStep.getExecutionContext().getLong("lastProcessedId"))
    .isEqualTo(200L);
```

Giá trị `200` chỉ là kỳ vọng của fixture: hai chunk đầu đã commit và chunk thứ ba thất bại. Test thực tế phải cấu hình reader và writer sao cho checkpoint được cập nhật đúng ở ranh giới commit.

Để kiểm tra promotion, có thể tạo một step hoàn tất và một step thất bại, sau đó xác nhận listener chỉ đưa key lên job context cho các exit status được cấu hình. Dùng `JobExplorer` đọc lại execution đã lưu thay vì chỉ assertion trên object còn trong bộ nhớ.

## 15. Quy trình điều tra context sau sự cố

Khi step thất bại, hãy xác định `JobExecutionId`, tên step, trạng thái, thời điểm lỗi và node thực thi. Sau đó truy vấn `JobExecution` và các `StepExecution` qua `JobExplorer` để đọc context đã lưu.

Đối chiếu các thông tin sau:

- Checkpoint trong step context có khớp với số item đã commit không?
- Job context có chứa các key được promote từ step trước không?
- Step trước đó kết thúc `COMPLETED` hay cũng thất bại?
- Reader có thể khôi phục từ checkpoint với nguồn hiện tại không?
- File, cursor, page token hoặc dữ liệu nguồn có bị thay đổi sau lần chạy trước không?
- Dữ liệu nghiệp vụ đã ghi có khớp với checkpoint không?
- Phiên bản code hiện tại có thể deserialize context được tạo bởi phiên bản cũ không?

Không sửa trực tiếp bảng `BATCH_STEP_EXECUTION_CONTEXT` hoặc `BATCH_JOB_EXECUTION_CONTEXT` để ép job tiếp tục. Nếu context bị hỏng hoặc không tương thích, cần xác định checkpoint có thể phục hồi từ backup, dữ liệu nguồn hoặc quy trình reprocess; mọi thay đổi phải theo quy trình vận hành có kiểm soát.

## 16. Cách thiết kế context để step có thể phục hồi

Khi xây dựng step, hãy xác định rõ trạng thái tối thiểu cần lưu để tiếp tục sau sự cố. Reader nên triển khai `ItemStream` nếu cần checkpoint; `update()` phải ghi trạng thái phản ánh tiến độ đã được xác nhận tại ranh giới commit. Dùng step context cho trạng thái riêng của step và job context cho dữ liệu cần chia sẻ giữa các step.

Nếu step sau cần giá trị từ step trước, dùng `ExecutionContextPromotionListener` với danh sách key và exit status được chấp nhận. Không promote dữ liệu chưa hoàn tất trừ khi có quy tắc nghiệp vụ rõ ràng. Giữ context nhỏ, key ổn định và kiểu dữ liệu tương thích qua các lần triển khai.

Cuối cùng, kiểm thử failure giữa chunk, rollback và restart. Đọc lại context từ repository để xác nhận checkpoint bền vững, rồi xác nhận reader tiếp tục đúng vị trí và writer không tạo dữ liệu trùng. Khi phân biệt được context đã commit với thay đổi chưa commit, ứng dụng có thể dùng `ExecutionContext` đúng mục đích và phục hồi step thất bại một cách có kiểm soát.
