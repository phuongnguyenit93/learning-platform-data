# Đảm bảo dữ liệu không bị nhân đôi

Trong Spring Batch, một item có thể được đọc hoặc xử lý lại khi chunk rollback, khi Job restart, khi retry một thao tác hoặc khi một partition được chạy lại. Vì vậy, ứng dụng cần thiết kế Reader, Processor, Writer và các thao tác bên ngoài sao cho việc xử lý lặp không tạo ra bản ghi trùng hoặc tác dụng phụ lặp ngoài ý muốn.

Mục tiêu thực tế thường là **idempotency**: cùng một yêu cầu nghiệp vụ được thực hiện một lần hay nhiều lần đều đưa hệ thống đến cùng một trạng thái dữ liệu cuối cùng. Spring Batch cung cấp transaction, checkpoint, retry và restart, nhưng không tự bảo đảm mọi thao tác nghiệp vụ chỉ xảy ra đúng một lần. Tính duy nhất của dữ liệu cần được bảo vệ ở tầng ứng dụng và database.

## 1. Vì sao dữ liệu có thể bị nhân đôi?

Một Job không phải lúc nào cũng xử lý mỗi item đúng một lần theo nghĩa tuyệt đối. Có nhiều tình huống hợp lệ khiến cùng một item được đưa qua pipeline nhiều lần:

- Chunk đã ghi một phần nhưng transaction rollback; lần thử tiếp theo phải xử lý lại chunk.
- Job thất bại và được restart từ checkpoint đã commit gần nhất.
- Retry policy gọi lại Processor hoặc Writer sau lỗi tạm thời.
- Worker hoặc partition được chạy lại sau khi tiến trình bị dừng hoặc mất kết nối.
- Scheduler gửi cùng một yêu cầu launch nhiều lần.
- Hệ thống bên ngoài đã nhận request nhưng ứng dụng chưa nhận được phản hồi, nên gửi lại.
- Người vận hành chủ động tạo JobInstance mới để tái xử lý cùng dữ liệu nguồn.

Ví dụ, Writer thêm đơn hàng vào bảng đích bằng câu lệnh `INSERT`. Chunk ghi thành công nhưng ứng dụng mất kết nối trước khi nhận được xác nhận commit. Khi retry, cùng đơn hàng được insert lần nữa. Nếu bảng đích không có khóa duy nhất theo mã đơn hàng nguồn, hai bản ghi có thể cùng tồn tại.

```text
Chunk attempt 1
  Read order ORD-100
  INSERT ORD-100
  Connection lost / transaction outcome chưa rõ
        |
        v
Chunk attempt 2
  Read order ORD-100 again
  INSERT ORD-100 again
        |
        v
Hai dòng cùng đại diện một đơn hàng nghiệp vụ
```

Đây là lý do cần bảo vệ tính duy nhất ngay tại nơi dữ liệu được ghi, thay vì chỉ dựa vào việc Reader không trả lại cùng item.

## 2. Hiểu đúng idempotency và exactly-once

Một thao tác được gọi là idempotent nếu thực hiện nhiều lần với cùng một định danh và cùng ý nghĩa nghiệp vụ không làm thay đổi kết quả cuối sau lần đầu.

Ví dụ:

- `UPDATE account SET status = 'ACTIVE' WHERE account_id = ?` có thể idempotent nếu mục tiêu là đặt trạng thái thành ACTIVE.
- `INSERT INTO payment ...` thường không idempotent nếu mỗi lần gọi tạo một dòng mới.
- `balance = balance + 100` không idempotent nếu cùng yêu cầu được áp dụng hai lần.
- `UPSERT` theo khóa nghiệp vụ có thể idempotent nếu nội dung cập nhật xác định và không cộng dồn ngoài ý muốn.

| Khái niệm | Ý nghĩa |
|---|---|
| At-most-once | Một thao tác được thử tối đa một lần; có nguy cơ mất kết quả nếu lỗi xảy ra trước khi hoàn tất. |
| At-least-once | Hệ thống tiếp tục thử cho đến khi có kết quả hoặc hết chính sách; cùng thao tác có thể xuất hiện nhiều lần. |
| Idempotent processing | Cho phép thực hiện lặp mà kết quả nghiệp vụ không bị nhân đôi. |
| Exactly-once effect | Hiệu ứng nghiệp vụ chỉ xuất hiện một lần; thường phải đạt được bằng transaction, khóa duy nhất, idempotency key hoặc giao thức phối hợp phù hợp. |

Trong hệ thống batch thực tế, at-least-once delivery kết hợp với thao tác idempotent thường dễ triển khai và đáng tin cậy hơn việc cố gắng bảo đảm mỗi lời gọi chỉ xảy ra đúng một lần trên nhiều hệ thống độc lập.

## 3. Chọn business key ổn định cho mỗi item

Để nhận diện một item đã được xử lý, cần có khóa nghiệp vụ ổn định. Khóa này phải đại diện cho cùng một thực thể hoặc yêu cầu qua các lần đọc, retry và restart.

Ví dụ:

| Loại dữ liệu | Business key có thể dùng |
|---|---|
| Đơn hàng từ hệ thống nguồn | `source_system + source_order_id` |
| Giao dịch thanh toán | `payment_reference` hoặc `transaction_id` của nguồn |
| Bản ghi khách hàng theo nguồn | `source_system + source_customer_id` |
| File import | `source_file_id` hoặc checksum kết hợp kỳ dữ liệu |
| Sự kiện từ message broker | `event_id` |
| Bản ghi theo kỳ và tenant | `tenant_id + business_period + record_key` |

Không nên dùng số thứ tự đọc trong Reader làm business key nếu thứ tự nguồn có thể thay đổi. Cũng không nên dùng thời gian hiện tại hoặc UUID mới cho mỗi lần retry, vì như vậy cùng một item có thể nhận một khóa khác và được ghi thành bản ghi mới.

Khóa kỹ thuật của bảng đích và business key có thể khác nhau. Ví dụ bảng dùng `id` tự tăng làm primary key, nhưng vẫn cần unique constraint trên `(source_system, source_order_id)` để ngăn hai dòng đại diện cùng một đơn hàng nguồn.

## 4. Bảo vệ tính duy nhất bằng database constraint

Biện pháp quan trọng nhất để ngăn insert trùng là đặt unique constraint hoặc unique index trên khóa nghiệp vụ. Kiểm tra trùng bằng câu `SELECT` trước khi `INSERT` không đủ an toàn khi nhiều worker chạy đồng thời: hai transaction có thể cùng thấy chưa có dòng và cùng insert.

Ví dụ schema:

```sql
CREATE TABLE imported_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_system VARCHAR(40) NOT NULL,
    source_order_id VARCHAR(100) NOT NULL,
    customer_id VARCHAR(100) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    CONSTRAINT uk_imported_order_source
        UNIQUE (source_system, source_order_id)
);
```

Khi hai worker hoặc hai lần retry cùng ghi một đơn hàng, unique constraint chỉ cho phép một dòng mang business key đó. Ứng dụng cần xử lý xung đột theo chính sách: bỏ qua nếu nội dung giống nhau, cập nhật nếu cho phép sửa, hoặc đánh dấu lỗi nếu cùng key nhưng payload khác.

Constraint ở database là lớp bảo vệ cuối cùng vì nó hoạt động ngay cả khi có nhiều thread, nhiều instance ứng dụng hoặc một tiến trình khác cùng ghi dữ liệu.

## 5. Dùng INSERT ... ON CONFLICT hoặc MERGE theo database

Nhiều database hỗ trợ câu lệnh insert-or-update (upsert). Cú pháp khác nhau tùy hệ quản trị.

Ví dụ PostgreSQL:

```sql
INSERT INTO imported_order (
    source_system,
    source_order_id,
    customer_id,
    amount,
    imported_at
)
VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (source_system, source_order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount = EXCLUDED.amount;
```

Với cách này, cùng một business key không tạo thêm dòng mới. Nếu dữ liệu nguồn thay đổi, câu lệnh cập nhật nội dung theo quy tắc đã định.

Tuy nhiên, upsert không tự động có nghĩa mọi nghiệp vụ đều idempotent. Nếu câu lệnh dùng phép cộng dồn như `amount = imported_order.amount + EXCLUDED.amount`, chạy lại sẽ tiếp tục cộng thêm. Hãy cập nhật về giá trị xác định của nguồn, hoặc lưu version/event ID để chỉ áp dụng thay đổi mới.

Đối với database hỗ trợ `MERGE`, có thể dùng `MERGE` để đối chiếu source key và quyết định insert/update. Cần kiểm tra semantics, mức cô lập và hành vi khi có nhiều transaction cùng merge một khóa theo tài liệu của database đang dùng.

## 6. Dùng bảng kiểm soát xử lý (processed-items table)

Một cách phổ biến là lưu dấu vết mỗi business key đã được xử lý. Trước khi thực hiện tác dụng phụ, ứng dụng kiểm tra hoặc ghi nhận khóa xử lý trong một bảng có unique constraint.

Ví dụ:

```sql
CREATE TABLE processed_item (
    idempotency_key VARCHAR(160) PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_reference VARCHAR(160)
);
```

Trong cùng transaction với dữ liệu nghiệp vụ, ứng dụng cố gắng insert `idempotency_key`. Nếu insert thành công, transaction tiếp tục cập nhật dữ liệu. Nếu key đã tồn tại, item đã được xử lý hoặc một transaction khác đang xử lý cùng key; ứng dụng cần đọc trạng thái và quyết định bỏ qua, chờ hoặc xử lý lại theo quy tắc.

Điểm quan trọng là thao tác ghi processed key và thay đổi dữ liệu nghiệp vụ nên nằm trong cùng transaction. Nếu ghi key trước rồi transaction nghiệp vụ thất bại nhưng key vẫn commit độc lập, lần chạy sau có thể bỏ qua item dù dữ liệu đích chưa được cập nhật. Ngược lại, nếu dữ liệu nghiệp vụ commit nhưng processed key chưa ghi, lần chạy sau có thể thực hiện lại.

Một luồng transaction khái quát:

```text
BEGIN TRANSACTION
   |
   +--> INSERT processed_item(idempotency_key)
   |
   +--> Nếu key mới:
   |       cập nhật dữ liệu nghiệp vụ
   |       lưu kết quả/reference
   |
   +--> Nếu key đã tồn tại:
           kiểm tra trạng thái và áp dụng chính sách
   |
COMMIT
```

Với xử lý đồng thời, không dựa vào `SELECT` trước rồi mới `INSERT` mà thiếu constraint. Hãy dùng unique key và xử lý kết quả insert/duplicate một cách an toàn.

## 7. Thiết kế ItemWriter idempotent

Writer là nơi thường tạo ra dữ liệu trùng vì nó ghi kết quả nghiệp vụ. Một Writer an toàn nên xác định khóa cho mỗi item và ghi theo cách có thể chạy lại.

Ví dụ Writer dùng JDBC upsert theo business key:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

public class IdempotentOrderWriter implements ItemWriter<ProcessedOrder> {

    private final JdbcTemplate jdbcTemplate;

    public IdempotentOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends ProcessedOrder> chunk) {
        List<? extends ProcessedOrder> items = chunk.getItems();

        jdbcTemplate.batchUpdate(
                """
                INSERT INTO imported_order
                    (source_system, source_order_id, customer_id, amount, imported_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (source_system, source_order_id)
                DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    amount = EXCLUDED.amount
                """,
                new BatchPreparedStatementSetter() {
                    @Override
                    public void setValues(PreparedStatement ps, int i)
                            throws SQLException {
                        ProcessedOrder item = items.get(i);
                        ps.setString(1, item.sourceSystem());
                        ps.setString(2, item.sourceOrderId());
                        ps.setString(3, item.customerId());
                        ps.setBigDecimal(4, item.amount());
                    }

                    @Override
                    public int getBatchSize() {
                        return items.size();
                    }
                });
    }
}
```

Đây là ví dụ theo cú pháp PostgreSQL và Spring Batch 5. `ProcessedOrder` là kiểu dữ liệu ứng dụng. `JdbcTemplate` cần dùng DataSource tham gia transaction của Step để các câu lệnh ghi được commit/rollback cùng chunk.

Nếu cùng business key nhưng payload thay đổi, ví dụ số tiền khác nhau, upsert sẽ cập nhật theo ví dụ. Nếu nghiệp vụ không cho phép sửa một đơn hàng đã import, thay `DO UPDATE` bằng chính sách bỏ qua hoặc báo conflict. Idempotency cần phản ánh quy tắc nghiệp vụ, không chỉ là kỹ thuật tránh lỗi unique constraint.

## 8. Đảm bảo idempotency khi retry và rollback

Trong chunk processing, một exception có thể làm rollback toàn bộ transaction chunk. Spring Batch có thể retry item hoặc chunk theo cấu hình. Nếu Writer đã gọi dịch vụ ngoài hoặc ghi vào resource không tham gia transaction, thao tác đó có thể đã hoàn tất dù database rollback.

Ví dụ:

```text
Chunk transaction
   |
   +--> UPDATE order in database
   |
   +--> POST payment to external API (success)
   |
   +--> Error on next item
   |
   +--> ROLLBACK database transaction
          |
          +--> Payment API vẫn đã nhận request
```

Khi retry, cùng payment request có thể được gửi lần nữa. Cách xử lý là tạo idempotency key ổn định, ví dụ `payment:<sourceTransactionId>`, và gửi cùng key cho mọi lần thử:

```http
POST /payments
Idempotency-Key: payment:TX-2026-000123
Content-Type: application/json
```

Hệ thống nhận request cần lưu key và kết quả đã xử lý. Nếu cùng key được gửi lại, hệ thống trả kết quả cũ hoặc xác nhận đã xử lý, không tạo một payment mới.

Nếu hệ thống ngoài không hỗ trợ idempotency key, cần dùng một bảng outbox hoặc cơ chế tra cứu trạng thái trước khi gửi lại. Không thể bảo đảm không có duplicate chỉ bằng cách bắt exception ở phía client, vì timeout không cho biết chắc server đã thực hiện request hay chưa.

## 9. Transactional outbox cho message và tác dụng phụ ngoài database

Khi một chunk vừa cập nhật database vừa cần phát message, gửi email hoặc gọi hệ thống ngoài, không nên giả định hai thao tác này cùng rollback. Transactional outbox giải quyết bằng cách ghi dữ liệu nghiệp vụ và một sự kiện cần phát vào cùng transaction database.

```text
Chunk transaction
   |
   +--> UPDATE imported_order
   |
   +--> INSERT outbox_event(event_id, payload, status='NEW')
   |
COMMIT
   |
   v
Outbox dispatcher
   |
   +--> Gửi event đến message broker / API
   |
   +--> Đánh dấu event đã gửi
```

Nếu chunk rollback, cả thay đổi nghiệp vụ và outbox event đều rollback. Nếu chunk commit, event tồn tại bền vững và dispatcher có thể gửi sau. Dispatcher vẫn có thể gửi lặp nếu bị dừng sau khi broker nhận message nhưng trước khi đánh dấu đã gửi. Vì vậy, consumer cũng nên deduplicate theo `event_id` hoặc dùng idempotency key.

Outbox không làm cho toàn bộ hệ thống có exactly-once delivery. Nó giúp bảo đảm sự kiện không bị mất giữa commit database và việc gửi, còn việc nhận lặp vẫn cần được xử lý idempotent.

## 10. Dùng staging table và bước promote dữ liệu

Với import file lớn, có thể ghi dữ liệu vào staging table trước, sau đó dùng một Step khác để hợp nhất dữ liệu sang bảng chính. Staging giúp tách dữ liệu thô khỏi dữ liệu đã được chấp nhận và cho phép deduplicate trước khi promote.

Một flow ví dụ:

```text
read source file
      |
      v
load staging table
      |
      v
validate and deduplicate
      |
      v
merge into target table by business key
      |
      v
mark batch completed
```

Staging table có thể dùng khóa `(batch_id, source_record_key)` để ngăn cùng một dòng file được nạp nhiều lần trong cùng batch. Step promote dùng `MERGE` hoặc upsert theo business key của bảng đích.

Thiết kế này hữu ích khi cần kiểm tra số lượng bản ghi, phát hiện duplicate trong file nguồn, xử lý lỗi từng dòng và chạy lại một bước promote mà không phải đọc lại file. Tuy nhiên, vẫn cần xác định chính sách nếu cùng source key xuất hiện với payload khác nhau.

## 11. Đảm bảo không nhân đôi khi scheduler launch Job nhiều lần

Duplicate không chỉ xuất hiện trong Writer. Scheduler, API hoặc người vận hành có thể gửi cùng yêu cầu launch nhiều lần. Spring Batch nhận diện JobInstance bằng tên Job và identifying JobParameters:

- Cùng tên Job và cùng identifying parameters: cùng JobInstance.
- JobInstance đang chạy: lần launch trùng thường bị từ chối.
- JobInstance đã COMPLETED: launch lại với cùng định danh thường bị từ chối.
- JobInstance FAILED hoặc STOPPED: có thể restart nếu Job cho phép.
- Tham số định danh khác: tạo JobInstance mới.

Ví dụ, Job xử lý file nên dùng `sourceFileId` hoặc `businessDate + sourceFileId` làm identifying parameters. Không nên thêm timestamp hoặc UUID mới vào identifying parameters cho mỗi lần scheduler gửi lại cùng yêu cầu, vì như vậy mỗi lần gọi sẽ tạo JobInstance mới và có thể nhập dữ liệu lần nữa.

Nếu ứng dụng nhận yêu cầu từ API, có thể lưu `request_id` với unique constraint trong bảng `batch_request`. API chỉ tạo một yêu cầu cho cùng idempotency key; dispatcher launch Job dựa trên yêu cầu bền vững đó. Đây là lớp chống trùng ở cấp orchestration.

## 12. Partitioning và concurrency cũng cần chống duplicate

Khi partitioning hoặc multi-threaded Step, nhiều worker có thể ghi dữ liệu đồng thời. Cần bảo đảm partition không chồng lấn và Writer an toàn khi nhiều worker cùng xử lý.

Các nguyên tắc:

- Phân chia nguồn theo phạm vi không chồng lấn, ví dụ ID range, tenant hoặc file.
- Nếu partition dùng hash, mọi lần restart phải dùng cùng thuật toán và cùng số partition để giữ phân phối nhất quán, hoặc lưu sẵn partition plan.
- Dùng unique constraint trên business key ở bảng đích, vì lỗi chia partition vẫn có thể xảy ra.
- Không dựa vào biến `Set` trong memory của một worker để deduplicate toàn Job; các worker khác không chia sẻ trạng thái đó và restart sẽ làm mất dữ liệu trong memory.
- Dùng upsert, processed-item table hoặc idempotency key ở nơi lưu trữ bền vững.

Nếu hai partition có thể chứa cùng business key, unique constraint sẽ ngăn insert trùng nhưng có thể làm một worker nhận duplicate-key exception. Writer cần xử lý exception theo chính sách phù hợp hoặc partitioner cần được sửa để dữ liệu không chồng lấn.

## 13. Những trường hợp cần xác định chính sách rõ ràng

| Tình huống | Câu hỏi cần trả lời |
|---|---|
| Cùng key, cùng payload | Bỏ qua, trả kết quả cũ hay cập nhật lại timestamp? |
| Cùng key, payload khác | Nguồn mới hơn có được phép ghi đè không? Dựa trên version nào? |
| Cùng file được gửi hai lần | Coi là cùng batch hay hai lần import riêng? |
| Job restart sau khi external API thành công | API có hỗ trợ idempotency key hoặc tra cứu kết quả không? |
| Hai partition cùng ghi một key | Partitioning có bị chồng lấn hay dữ liệu nguồn có duplicate? |
| Một item đã xử lý nhưng Job chưa lưu checkpoint | Writer có thể chạy lại mà không tạo hiệu ứng thứ hai không? |
| Người dùng yêu cầu tái xử lý | Tạo version/correction ID mới hay cập nhật kết quả cũ? |

Không có một câu lệnh upsert duy nhất giải quyết mọi trường hợp. Quy tắc trùng phải được xác định theo ý nghĩa nghiệp vụ và lưu vết đủ để giải thích vì sao một item được bỏ qua, cập nhật hoặc xử lý lại.

## 14. Kiểm thử khả năng chống duplicate

Kiểm thử không chỉ nên chạy Job thành công một lần. Cần tạo các tình huống retry, restart và concurrency để xác nhận dữ liệu cuối cùng không bị nhân đôi.

Các kịch bản hữu ích:

1. **Chạy cùng JobParameters hai lần:** xác nhận Spring Batch nhận diện cùng JobInstance và xử lý theo trạng thái trước đó.
2. **Restart sau lỗi giữa chunk:** làm Writer ghi một phần rồi ném exception; restart Job và xác nhận business key chỉ có một dòng ở bảng đích.
3. **Retry lỗi tạm thời:** làm service hoặc Writer thất bại lần đầu rồi thành công; xác nhận tác dụng phụ chỉ có một hiệu ứng nghiệp vụ.
4. **Gửi cùng idempotency key nhiều lần:** xác nhận API hoặc consumer trả kết quả cũ thay vì tạo bản ghi mới.
5. **Chạy hai worker cùng business key:** xác nhận unique constraint ngăn dữ liệu trùng và ứng dụng xử lý conflict theo chính sách.
6. **Tái xử lý file đã import:** xác nhận batch request hoặc file key ngăn import lặp ngoài ý muốn.
7. **Outbox dispatcher dừng giữa gửi và đánh dấu:** xác nhận consumer deduplicate event theo ID.

Ví dụ assertion sau khi Job hoàn tất:

```java
Integer count = jdbcTemplate.queryForObject(
        "select count(*) from imported_order "
                + "where source_system = ? and source_order_id = ?",
        Integer.class,
        "ERP",
        "ORD-100");

assertEquals(1, count);
```

Với test restart, cần dùng cùng identifying JobParameters cho lần chạy đầu và lần restart để kiểm tra đúng JobInstance. Sau khi restart, kiểm tra cả JobExecution history và dữ liệu đích. Không chỉ kiểm tra trạng thái `COMPLETED`, vì Job có thể hoàn tất nhưng dữ liệu vẫn trùng.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `INSERT` thuần cho Writer có retry/restart | Cùng item có thể tạo nhiều dòng. | Unique constraint và upsert theo business key. |
| Chỉ `SELECT` kiểm tra trước khi insert | Race condition khi nhiều worker cùng kiểm tra. | Để database unique constraint quyết định tính duy nhất. |
| Tạo UUID mới cho mỗi lần retry | Hệ thống không nhận ra cùng một yêu cầu. | Tạo idempotency key ổn định từ khóa nghiệp vụ. |
| Ghi processed key ở transaction riêng trước dữ liệu chính | Có thể đánh dấu đã xử lý dù dữ liệu chính chưa commit. | Ghi marker và dữ liệu nghiệp vụ trong cùng transaction. |
| Gọi API trong Writer mà không có idempotency | Retry có thể tạo tác dụng phụ bên ngoài nhiều lần. | Dùng API idempotency key hoặc transactional outbox. |
| Dùng collection trong memory để deduplicate | Mất trạng thái khi restart và không chia sẻ giữa worker. | Dùng database hoặc kho trạng thái bền vững. |
| Partition không có ranh giới ổn định | Hai worker có thể xử lý cùng record. | Lưu partition plan hoặc tạo phạm vi không chồng lấn. |
| Cho rằng checkpoint tự ngăn mọi duplicate | Tác dụng phụ ngoài transaction có thể đã xảy ra trước rollback. | Kết hợp checkpoint với idempotent Writer và external key. |

## Kết luận

Đảm bảo dữ liệu không bị nhân đôi trong Spring Batch cần kết hợp checkpoint/restart với thiết kế idempotent ở nơi ghi dữ liệu. Hãy chọn business key ổn định, bảo vệ bằng unique constraint, dùng upsert hoặc processed-item table trong cùng transaction với dữ liệu chính, và áp dụng idempotency key hoặc transactional outbox cho tác dụng phụ bên ngoài. Khi có retry, rollback, scheduler gửi trùng hoặc partition chạy đồng thời, cùng một item vẫn có thể xuất hiện nhiều lần; hệ thống phải nhận diện và xử lý lặp an toàn. Kiểm thử restart và concurrency bằng cách kiểm tra dữ liệu đích thực tế là cách xác nhận quan trọng nhất.
