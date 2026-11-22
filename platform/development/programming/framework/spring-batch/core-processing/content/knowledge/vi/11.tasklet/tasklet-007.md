# Tasklet idempotency khi restart

Trong Spring Batch, `Tasklet` thực hiện một công việc theo từng lần gọi `execute()`. Công việc có thể là xóa dữ liệu cũ, tạo báo cáo, đóng kỳ kế toán, gọi dịch vụ bên ngoài hoặc xử lý một tập dữ liệu. Khi Job bị lỗi và được restart, Step chứa Tasklet có thể được thực thi lại. Nếu Tasklet tạo side effect mỗi lần chạy mà không kiểm tra trạng thái trước đó, hệ thống có thể xóa nhầm dữ liệu, tạo báo cáo trùng, gửi nhiều thông báo hoặc thực hiện một nghiệp vụ hai lần.

**Idempotency** giúp một thao tác có thể được thực hiện lặp lại với cùng định danh nghiệp vụ mà kết quả cuối cùng vẫn đúng và không tạo thêm hiệu ứng ngoài ý muốn. Với Tasklet, cần thiết kế idempotency cùng transaction, checkpoint, JobParameters và các hệ thống bên ngoài mà Tasklet tương tác.

## 1. Vì sao Tasklet cần idempotency khi restart?

Một Tasklet thường được dùng cho một bước công việc có tính chất rõ ràng, chẳng hạn tạo bảng tổng hợp cho một ngày nghiệp vụ:

```text
Job: dailySettlementJob
    |
    +--> Tasklet: prepareSettlement
    |
    +--> Step: calculateTransactions
    |
    +--> Tasklet: publishSettlementReport
```

Giả sử `prepareSettlement` tạo một bản ghi kỳ quyết toán. Tasklet thực hiện thành công, nhưng Step sau thất bại. Khi Job được restart, Spring Batch thường bỏ qua Step đã `COMPLETED` và tiếp tục từ Step chưa hoàn tất. Tuy nhiên, nếu Step Tasklet thất bại sau khi đã tạo side effect, hoặc được cấu hình chạy lại sau khi hoàn tất, Tasklet có thể được gọi lần nữa.

Ví dụ một Tasklet không idempotent:

```java
public class CreateReportTasklet implements Tasklet {

    private final ReportService reportService;

    public CreateReportTasklet(ReportService reportService) {
        this.reportService = reportService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        reportService.createNewReport();
        return RepeatStatus.FINISHED;
    }
}
```

Mỗi lần `execute()` được gọi, service có thể tạo một báo cáo mới. Nếu cùng một công việc nghiệp vụ bị thực thi lại, kết quả có thể xuất hiện nhiều báo cáo giống nhau.

Tasklet idempotent cần nhận diện được công việc logic đang xử lý và xác định liệu side effect tương ứng đã được thực hiện hay chưa. Định danh này nên ổn định qua các lần restart.

## 2. Phân biệt Tasklet invocation, Step execution và Job restart

Có ba mức cần phân biệt:

- **Tasklet invocation:** một lần gọi `Tasklet.execute()`. Nếu Tasklet trả `RepeatStatus.CONTINUABLE`, framework có thể gọi lại `execute()` trong cùng StepExecution.
- **StepExecution:** một lần thực thi cụ thể của Step. Nếu Step thất bại và Job được restart, framework có thể tạo StepExecution mới cho lần thực thi lại.
- **JobInstance:** đại diện cho công việc nghiệp vụ logic, được xác định bởi tên Job và identifying JobParameters. Một JobInstance có thể có nhiều JobExecution qua các lần restart.

Trong `TaskletStep`, mỗi lần gọi Tasklet được thực hiện trong transaction của Step. Khi Tasklet trả `CONTINUABLE`, framework lặp lại lời gọi; mỗi lần lặp có ranh giới transaction riêng. Khi Tasklet trả `FINISHED`, Step kết thúc thành công nếu không có lỗi khác.

```text
JobInstance: closeBusinessDay(businessDate=2026-11-15)
    |
    +-- JobExecution #101
          |
          +-- StepExecution #201
                |
                +-- execute() -> CONTINUABLE -> transaction commit
                +-- execute() -> CONTINUABLE -> transaction commit
                +-- execute() -> exception    -> transaction rollback

Restart cùng JobInstance
    |
    +-- JobExecution #108
          |
          +-- StepExecution mới
                +-- Tasklet được gọi lại theo metadata/checkpoint
```

Với Tasklet chỉ chạy một lần và trả `FINISHED`, nếu lần gọi thất bại trước khi Step hoàn tất, lần restart có thể gọi lại toàn bộ logic từ đầu. Với Tasklet xử lý nhiều phần và trả `CONTINUABLE`, checkpoint có thể giúp tiếp tục từ phần đã commit.

## 3. Idempotency key phải đại diện cho công việc nghiệp vụ

Một cách phổ biến để chống thực hiện trùng là tạo *idempotency key* ổn định cho thao tác. Key nên dựa trên business key, ví dụ ngày quyết toán, mã khách hàng, mã nguồn dữ liệu hoặc loại nghiệp vụ.

Ví dụ:

```text
operationKey = "settlement:2026-11-15"
```

Nếu Tasklet restart cho cùng kỳ quyết toán, key vẫn giữ nguyên. Nếu kỳ nghiệp vụ thay đổi, key sẽ khác.

Không nên dùng `JobExecution.getId()` làm idempotency key cho nghiệp vụ cần chống trùng qua restart. Mỗi lần restart tạo JobExecution mới nên execution ID thay đổi. Có thể dùng `JobInstance` ID nếu key chỉ cần ổn định trong một JobInstance, hoặc tốt hơn là tạo key trực tiếp từ business parameters đã chuẩn hóa để nó vẫn có ý nghĩa khi hệ thống tái tạo metadata.

Ví dụ đọc tham số và tạo key:

```java
JobParameters parameters = contribution.getStepExecution().getJobParameters();
String businessDate = parameters.getString("businessDate");

if (businessDate == null || businessDate.isBlank()) {
    throw new IllegalArgumentException("businessDate is required");
}

String operationKey = "settlement:" + businessDate.trim();
```

Các tham số xác định cùng một công việc phải được chuẩn hóa trước khi tạo key. Nếu một lần gọi dùng `2026-11-15`, lần khác dùng `2026/11/15`, hai chuỗi có thể tạo hai key khác nhau dù cùng biểu diễn một ngày nghiệp vụ.

## 4. Bảo vệ thao tác database bằng unique key và transaction

Nếu Tasklet cập nhật dữ liệu trong cùng database và cùng transaction manager với Step, có thể dùng một bảng ghi nhận thao tác đã thực hiện. Khóa duy nhất ngăn hai lần chạy cùng công việc tạo hai marker giống nhau.

Ví dụ schema:

```sql
CREATE TABLE completed_batch_operation (
    operation_key VARCHAR(200) PRIMARY KEY,
    completed_at TIMESTAMP NOT NULL
);
```

Tasklet dùng thao tác insert có xử lý conflict để chỉ thực hiện nghiệp vụ khi key chưa tồn tại. Ví dụ sau dùng cú pháp PostgreSQL:

```java
public class CloseBusinessDayTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public CloseBusinessDayTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String businessDate = contribution.getStepExecution()
                .getJobParameters()
                .getString("businessDate");

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        String operationKey = "close-business-day:" + businessDate.trim();

        int inserted = jdbcTemplate.update("""
                INSERT INTO completed_batch_operation(operation_key, completed_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT (operation_key) DO NOTHING
                """, operationKey);

        if (inserted == 0) {
            // Công việc này đã được commit trong một lần thực thi trước.
            return RepeatStatus.FINISHED;
        }

        jdbcTemplate.update("""
                UPDATE daily_account
                SET closed = TRUE
                WHERE business_date = ?
                """, businessDate);

        return RepeatStatus.FINISHED;
    }
}
```

Điểm quan trọng là insert marker và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction. Nếu cập nhật nghiệp vụ thất bại, transaction rollback cả marker lẫn thay đổi nghiệp vụ; lần restart có thể thử lại. Nếu transaction commit, marker và thay đổi nghiệp vụ cùng tồn tại; lần gọi tiếp theo thấy conflict và kết thúc mà không lặp side effect.

Ví dụ dùng PostgreSQL `ON CONFLICT`. Với database khác, hãy dùng cú pháp upsert hoặc cơ chế insert-if-absent tương ứng. Cần có unique constraint thực sự ở database; chỉ kiểm tra `SELECT` trước khi insert không đủ chống hai execution đồng thời cùng vượt qua bước kiểm tra.

Đảm bảo `JdbcTemplate` dùng `DataSource` thuộc transaction manager của Step. Nếu marker và dữ liệu nghiệp vụ dùng hai transaction manager khác nhau, tính atomic nêu trên không còn được bảo đảm.

## 5. Cập nhật theo trạng thái thay vì tạo mới mỗi lần

Một số Tasklet không cần marker riêng mà có thể thiết kế thao tác theo hướng đặt trạng thái cuối cùng một cách idempotent.

Ví dụ, thay vì cộng thêm một khoản điều chỉnh mỗi lần Tasklet chạy:

```sql
UPDATE account
SET balance = balance + 100
WHERE account_id = ?;
```

có thể ghi nhận điều chỉnh theo một business key duy nhất:

```sql
CREATE TABLE account_adjustment (
    adjustment_key VARCHAR(200) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL
);
```

Tasklet chỉ thêm adjustment nếu key chưa tồn tại, sau đó tính hoặc cập nhật số dư từ tập adjustment đã ghi nhận. Việc chạy lại cùng key không tạo khoản điều chỉnh thứ hai.

Một thao tác kiểu `SET status = 'CLOSED'` thường dễ idempotent hơn thao tác kiểu `SET balance = balance + 100`, nhưng vẫn cần xem side effect đi kèm và quy tắc nghiệp vụ. Nếu mỗi lần set trạng thái lại phát ra email hoặc event, các side effect đó vẫn có thể bị lặp.

## 6. Tasklet xử lý nhiều phần bằng CONTINUABLE và checkpoint

Tasklet có thể xử lý dữ liệu theo từng page hoặc batch nhỏ. Mỗi lần `execute()` xử lý một phần rồi trả `RepeatStatus.CONTINUABLE` để framework gọi tiếp. Khi một phần hoàn tất, Tasklet lưu checkpoint vào Step `ExecutionContext`.

Ví dụ xử lý bản ghi theo ID tăng dần:

```java
public class ProcessOrdersTasklet implements Tasklet {

    private static final String LAST_ID_KEY = "processOrders.lastId";
    private static final int PAGE_SIZE = 200;

    private final OrderRepository orderRepository;
    private final OrderService orderService;

    public ProcessOrdersTasklet(
            OrderRepository orderRepository,
            OrderService orderService) {
        this.orderRepository = orderRepository;
        this.orderService = orderService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context = contribution.getStepExecution()
                .getExecutionContext();
        long lastId = context.getLong(LAST_ID_KEY, 0L);

        List<Order> page = orderRepository.findNextPage(lastId, PAGE_SIZE);
        if (page.isEmpty()) {
            return RepeatStatus.FINISHED;
        }

        for (Order order : page) {
            orderService.processIdempotently(order);
        }

        long newLastId = page.get(page.size() - 1).getId();
        context.putLong(LAST_ID_KEY, newLastId);

        return RepeatStatus.CONTINUABLE;
    }
}
```

Trong ví dụ:

1. Lần đầu, context chưa có `LAST_ID_KEY`, nên Tasklet bắt đầu từ ID `0`.
2. Tasklet lấy tối đa 200 bản ghi có ID lớn hơn checkpoint.
3. Tasklet xử lý page, cập nhật checkpoint thành ID cuối cùng và trả `CONTINUABLE`.
4. Spring Batch hoàn tất transaction của lần gọi đó rồi gọi `execute()` tiếp.
5. Khi không còn bản ghi, Tasklet trả `FINISHED`.

`TaskletStep` quản lý việc lưu ExecutionContext và metadata Step tại các ranh giới transaction của vòng lặp. Nếu một lần gọi thất bại trước commit, checkpoint của lần gọi đó không được xem là đã hoàn tất. Khi restart, Tasklet có thể đọc checkpoint gần nhất đã lưu.

Tuy nhiên, nếu `orderService.processIdempotently()` ghi ra hệ thống ngoài transaction, một số order có thể đã được xử lý trước khi lỗi xảy ra. Khi Tasklet chạy lại page, service vẫn phải nhận diện từng order bằng idempotency key ổn định. Checkpoint không thay thế idempotency cho side effect bên ngoài.

## 7. Transaction và thứ tự cập nhật checkpoint

Với Tasklet nhiều phần, thứ tự quan trọng là: xử lý phần dữ liệu, cập nhật checkpoint, rồi để transaction của lần gọi commit. Khi business update và ExecutionContext được lưu trong cùng transaction phù hợp, chúng có thể được commit nhất quán.

```text
Một lần execute()
       |
       +--> Đọc page sau checkpoint cũ
       |
       +--> Thực hiện cập nhật nghiệp vụ
       |
       +--> Ghi checkpoint mới vào Step ExecutionContext
       |
       +--> Transaction commit
```

Nếu exception xảy ra trước commit và cả business update lẫn metadata tham gia cùng transaction, chúng được rollback cùng nhau. Nếu business side effect nằm ngoài transaction, side effect có thể đã xảy ra trong khi checkpoint chưa được lưu. Lần restart sẽ xử lý lại phần đó; do vậy side effect phải idempotent.

Không cập nhật checkpoint trước khi xử lý xong page. Nếu checkpoint tiến lên nhưng xử lý nghiệp vụ thất bại, lần restart có thể bỏ qua dữ liệu chưa được xử lý. Ngược lại, nếu nghiệp vụ hoàn tất nhưng checkpoint chưa được lưu, một phần dữ liệu có thể được xử lý lại; idempotency giúp lần xử lý lặp an toàn.

Với nguồn dữ liệu thay đổi trong lúc chạy, cần dùng sort key ổn định và điều kiện truy vấn nhất quán. ID tăng dần, watermark hoặc snapshot có thể giúp tránh bỏ sót/đọc lặp khi page tiếp theo được lấy sau một lần commit.

## 8. Side effect bên ngoài: API, message và email

Transaction database của Step không tự động thu hồi một HTTP request đã được dịch vụ bên ngoài xử lý, một message đã được broker nhận hoặc một email đã gửi.

Ví dụ, Tasklet gọi API thanh toán:

```java
paymentClient.capture(
        paymentId,
        amount,
        "capture:" + paymentId
);
```

API đích cần hỗ trợ idempotency key và lưu kết quả theo key. Khi Tasklet gọi lại cùng `capture:<paymentId>`, API trả về kết quả đã có thay vì capture lần nữa. Nếu API không có cơ chế này, Tasklet không thể tự bảo đảm thao tác thanh toán chỉ xảy ra một lần bằng cách kiểm tra một biến trong bộ nhớ.

### Outbox pattern cho message

Nếu Tasklet vừa cập nhật database vừa cần phát event, có thể ghi event vào bảng outbox trong cùng transaction với dữ liệu nghiệp vụ:

```text
Tasklet transaction
    |
    +--> Cập nhật trạng thái settlement
    +--> Insert event vào outbox với eventId ổn định
    +--> Commit

Publisher riêng
    |
    +--> Đọc event chưa gửi
    +--> Publish event
    +--> Đánh dấu đã gửi
```

Publisher có thể gửi lại event nếu process dừng sau khi broker nhận message nhưng trước khi trạng thái outbox được cập nhật. Consumer nên deduplicate theo `eventId`. Outbox giúp bảo đảm dữ liệu nghiệp vụ và ý định phát event được ghi atomically trong database; nó không tự biến toàn bộ hệ thống thành exactly-once.

Email thường không có cơ chế rollback. Thay vì gửi email trực tiếp trong Tasklet rồi đánh dấu hoàn tất, có thể ghi yêu cầu gửi email vào outbox hoặc bảng notification trong cùng transaction. Một worker riêng gửi và ghi nhận kết quả, dùng key để chống tạo yêu cầu trùng.

## 9. Tạo file và publish báo cáo một cách idempotent

Tasklet tạo file báo cáo có thể thất bại sau khi đã ghi một phần file. Khi restart, nếu Tasklet nối thêm dữ liệu vào cùng file mà không kiểm tra trạng thái, file có thể chứa các dòng trùng.

Một chiến lược phổ biến:

1. Tạo đường dẫn file tạm dựa trên business key, ví dụ `settlement-2026-11-15.tmp`.
2. Mỗi lần tạo lại, xóa và dựng lại file tạm hoặc resume bằng writer có checkpoint được hỗ trợ.
3. Ghi hoàn chỉnh, flush và đóng file.
4. Kiểm tra số dòng hoặc checksum nếu nghiệp vụ yêu cầu.
5. Đổi tên/publish file tạm thành file chính thức sau khi hoàn tất.
6. Nếu file chính thức đã tồn tại cho cùng business key, xác định đó là kết quả đã hoàn tất hay là trạng thái cần đối soát.

Đổi tên file có thể atomic trong cùng filesystem, nhưng không nên giả định thao tác rename atomic giữa hai filesystem hoặc object storage. Với object storage, có thể dùng object key theo version hoặc manifest pointer để chỉ công bố bản hoàn tất.

## 10. Step hoàn tất và allowStartIfComplete

Khi restart cùng JobInstance sau khi một Step trước đó đã `COMPLETED`, Spring Batch mặc định không chạy lại Step hoàn tất đó. Điều này giúp tránh lặp side effect của Step đã thành công khi một Step phía sau thất bại.

Nếu cấu hình Step với `allowStartIfComplete(true)`, Step đã hoàn tất có thể được chạy lại trong lần restart. Khi đó, Tasklet phải idempotent vì nó có thể thực hiện cùng công việc nghiệp vụ lần nữa.

Ví dụ:

```java
@Bean
public Step publishReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PublishReportTasklet tasklet) {

    return new StepBuilder("publishReportStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Chỉ bật `allowStartIfComplete(true)` khi nghiệp vụ yêu cầu Step được thực hiện lại trong lần restart. Nếu Step đã hoàn tất và không cần chạy lại, để mặc định thường phù hợp hơn. Dù không bật tùy chọn này, Tasklet vẫn cần an toàn với trường hợp lỗi xảy ra sau side effect nhưng trước khi Step metadata được xác nhận hoàn tất.

## 11. Phân biệt JobParameters, ExecutionContext và idempotency key

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| JobParameters identifying | Xác định JobInstance và công việc logic | `businessDate=2026-11-15` |
| Step ExecutionContext | Lưu checkpoint/tiến độ của Step | `lastProcessedOrderId=4200` |
| Job ExecutionContext | Lưu trạng thái cần chia sẻ giữa các Step | `reportLocation=...` |
| Idempotency key | Nhận diện side effect cụ thể để chống thực hiện trùng | `close-business-day:2026-11-15` |

Một idempotency key có thể được tạo từ JobParameters nhưng cần xác định theo nghiệp vụ. ExecutionContext lưu tiến độ không tự thay thế một khóa duy nhất ở database hoặc idempotency key được hệ thống ngoài hỗ trợ.

Không dùng `JobExecutionId` làm khóa nghiệp vụ ổn định qua restart vì ID thay đổi giữa các lần thực thi. Không dùng `StepExecutionId` làm key chống trùng cho cùng lý do.

## 12. Những lỗi thiết kế thường gặp

**Dùng timestamp hiện tại làm idempotency key.** Mỗi lần restart có thể tạo timestamp khác nhau, khiến hệ thống coi cùng một công việc là thao tác mới. Hãy dùng business key ổn định.

**Đánh dấu hoàn tất trước khi thực hiện side effect.** Nếu marker được commit trước nhưng thao tác nghiệp vụ thất bại, lần restart có thể thấy marker và bỏ qua công việc chưa hoàn tất. Marker và business update cần cùng transaction hoặc có state machine phục hồi rõ ràng.

**Thực hiện side effect ngoài transaction rồi chỉ lưu checkpoint.** Nếu side effect thành công nhưng checkpoint chưa commit, thao tác sẽ được gọi lại. Cần idempotency ở đích hoặc outbox.

**Coi ExecutionContext là cơ chế exactly-once.** Context giúp lưu checkpoint; nó không thu hồi side effect ngoài transaction và không chống hai execution đồng thời nếu thiếu khóa/constraint ở nơi ghi dữ liệu.

**Bắt exception và trả `FINISHED`.** Spring Batch sẽ xem Tasklet hoàn tất bình thường, dù công việc có thể chỉ được thực hiện một phần. Hãy để exception truyền ra hoặc ghi nhận trạng thái lỗi theo một thiết kế rõ ràng.

**Dùng mutable field làm checkpoint.** Field trong object mất khi process khởi động lại và có thể không khớp với tiến độ đã commit. Dùng Step ExecutionContext hoặc kho trạng thái bền vững.

**Bật `allowStartIfComplete(true)` mà không bảo vệ side effect.** Step đã thành công có thể được chạy lại khi restart. Hãy chỉ bật khi cần và thiết kế thao tác idempotent.

## 13. Kiểm thử idempotency của Tasklet

Không chỉ kiểm tra Tasklet chạy thành công một lần. Cần kiểm tra hành vi khi cùng công việc được gọi nhiều lần:

- Gọi Tasklet hai lần với cùng business key: chỉ có một kết quả nghiệp vụ được tạo.
- Gây lỗi sau khi ghi marker hoặc trong lúc cập nhật dữ liệu: transaction rollback đúng và lần gọi lại hoàn tất được.
- Gây lỗi sau side effect ngoài transaction nhưng trước khi checkpoint được lưu: lần gọi lại không tạo side effect trùng.
- Restart sau khi một page đã commit: Tasklet tiếp tục từ checkpoint đã lưu.
- Gọi đồng thời hai execution có cùng business key: unique constraint hoặc idempotency service ngăn xử lý trùng.
- Restart với business key khác: công việc mới được thực hiện độc lập.

Ví dụ test ở mức khái niệm:

```java
@Test
void repeatedExecutionDoesNotCloseBusinessDayTwice() throws Exception {
    Tasklet tasklet = new CloseBusinessDayTasklet(jdbcTemplate);

    StepContribution contribution = contributionWithBusinessDate("2026-11-15");
    ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

    tasklet.execute(contribution, chunkContext);
    tasklet.execute(contribution, chunkContext);

    assertEquals(1, countCompletedOperations("close-business-day:2026-11-15"));
    assertEquals(1, countBusinessDayCloseEvents("2026-11-15"));
}
```

Test thực tế nên chạy với database transaction phù hợp và mô phỏng cả exception giữa chừng. Với API hoặc broker, dùng fake server hoặc test container có thể kiểm tra idempotency key và số side effect được ghi nhận.

## 14. Cách thiết kế Tasklet idempotent

Trước khi viết Tasklet, xác định business key của thao tác, nơi lưu trạng thái đã hoàn tất và transaction nào bao phủ side effect. Với database cùng transaction, dùng unique constraint và ghi marker cùng thay đổi nghiệp vụ trong một transaction. Với công việc dài, xử lý theo page, lưu checkpoint sau mỗi phần đã hoàn tất và bảo đảm từng item có thể xử lý lặp an toàn. Với API/message/email, dùng idempotency key ở hệ thống đích hoặc outbox; với file, ghi tạm rồi publish kết quả hoàn chỉnh.

Tasklet nên để lỗi thực sự làm thất bại lần thực thi được truyền đến Spring Batch, để framework rollback và ghi metadata đúng trạng thái. Khi restart, cùng một công việc logic phải được nhận diện bằng key ổn định và mọi side effect cần an toàn khi được thử lại. Đây là nền tảng để Tasklet có thể phục hồi sau lỗi mà không tạo dữ liệu trùng hoặc bỏ sót nghiệp vụ.
