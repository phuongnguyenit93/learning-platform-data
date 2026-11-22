# Batch update writer trong Spring Batch

Trong một chunk-oriented step, reader lấy item, processor chuẩn hóa hoặc biến đổi item, rồi writer ghi kết quả ra hệ thống đích. Khi đích là relational database và cần ghi nhiều item bằng cùng một câu SQL, Spring Batch cung cấp JdbcBatchItemWriter. Writer này dùng JDBC batch update để gửi nhiều bộ tham số cho cùng một câu lệnh SQL trong một lần ghi chunk.

Mặc dù tên lớp có chữ Batch, JdbcBatchItemWriter không chỉ dùng cho câu lệnh UPDATE. Nó có thể chạy INSERT, UPDATE hoặc DELETE theo từng item, miễn là mỗi item cung cấp được các tham số cho câu SQL đã cấu hình. Bài học này tập trung vào cách ghi batch, binding tham số, transaction theo chunk, kiểm tra số dòng bị ảnh hưởng, xử lý lỗi và kiểm thử.

## 1. Batch update writer là gì?

Một cách đơn giản để ghi nhiều item là gọi JdbcTemplate.update() trong vòng lặp:

~~~java
for (CustomerUpdate item : items) {
    jdbcTemplate.update(
        "update customer set status = ? where customer_id = ?",
        item.status(),
        item.customerId()
    );
}
~~~

Cách này thực hiện từng update riêng lẻ. Khi số item lớn, ứng dụng có thể tạo nhiều lần gọi JDBC và round trip tới database.

JdbcBatchItemWriter nhận cả chunk, tạo bộ tham số cho từng item rồi dùng cơ chế JDBC batch để thực thi cùng một câu SQL với nhiều bộ giá trị:

~~~text
Chunk<CustomerUpdate>
  |
  v
JdbcBatchItemWriter
  |
  +-- SQL: UPDATE customer SET status = ? WHERE customer_id = ?
  |
  +-- Parameters for item 1
  +-- Parameters for item 2
  +-- Parameters for item 3
  +-- ...
  |
  v
JDBC batchUpdate(...)
  |
  v
Database
~~~

Database driver có thể tối ưu batch execution, giảm overhead so với việc gửi từng câu lệnh độc lập. Mức cải thiện phụ thuộc driver, database, network, SQL và kích thước chunk; không nên giả định mọi batch luôn tương đương một round trip duy nhất.

## 2. Khi nào dùng JdbcBatchItemWriter?

Dùng JdbcBatchItemWriter khi mỗi item tạo ra một lần thực thi của cùng một câu SQL:

- Cập nhật trạng thái nhiều customer.
- Chèn nhiều order hoặc transaction.
- Xóa nhiều record đã xử lý.
- Ghi dữ liệu đã chuẩn hóa sang bảng staging.
- Cập nhật bảng đích theo business key.

Ví dụ, một file chứa nhiều yêu cầu cập nhật customer. Reader trả từng CustomerUpdate; processor kiểm tra và chuẩn hóa; writer gửi toàn bộ các update trong chunk tới database.

Không dùng JdbcBatchItemWriter nếu mục tiêu chỉ là chạy một câu UPDATE duy nhất tác động tới một tập lớn các hàng theo một điều kiện chung, ví dụ cập nhật toàn bộ record quá hạn. Trường hợp đó thường phù hợp với JdbcTemplate.update(), stored procedure hoặc tasklet. JdbcBatchItemWriter là item-oriented: mỗi item cung cấp một bộ tham số cho câu lệnh.

## 3. Cấu hình JdbcBatchItemWriter với named parameters

Named parameters giúp câu SQL dễ đọc hơn placeholder vị trí. Có thể dùng BeanPropertyItemSqlParameterSourceProvider để lấy giá trị từ JavaBean property:

~~~java
@Bean
JdbcBatchItemWriter<CustomerUpdate> customerUpdateWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<CustomerUpdate>()
        .dataSource(dataSource)
        .sql("""
            update customer
            set email = :email,
                status = :status,
                updated_at = :updatedAt
            where customer_id = :customerId
            """)
        .itemSqlParameterSourceProvider(
            new BeanPropertyItemSqlParameterSourceProvider<>()
        )
        .assertUpdates(true)
        .build();
}
~~~

Tên parameter trong SQL phải tương ứng với property mà parameter source cung cấp. Ví dụ :customerId lấy giá trị từ property customerId. Với JavaBean, property thường được phát hiện qua getter; hãy bảo đảm DTO có accessor tương thích.

Ví dụ item:

~~~java
public class CustomerUpdate {

    private String customerId;
    private String email;
    private String status;
    private LocalDateTime updatedAt;

    public String getCustomerId() {
        return customerId;
    }

    public String getEmail() {
        return email;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Nếu dùng record, immutable object hoặc naming convention đặc biệt, kiểm tra khả năng introspection của phiên bản Spring Framework đang dùng. Khi cần kiểm soát chính xác, tạo ItemSqlParameterSourceProvider riêng hoặc dùng ItemPreparedStatementSetter.

## 4. Cấu hình bằng ItemPreparedStatementSetter

Nếu muốn dùng placeholder vị trí ?, có thể cung cấp ItemPreparedStatementSetter. Setter nhận item hiện tại và PreparedStatement, sau đó gán từng tham số:

~~~java
@Bean
JdbcBatchItemWriter<CustomerUpdate> customerUpdateWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<CustomerUpdate>()
        .dataSource(dataSource)
        .sql("""
            update customer
            set email = ?,
                status = ?,
                updated_at = ?
            where customer_id = ?
            """)
        .itemPreparedStatementSetter((item, ps) -> {
            ps.setString(1, item.getEmail());
            ps.setString(2, item.getStatus());
            ps.setTimestamp(
                3,
                Timestamp.valueOf(item.getUpdatedAt())
            );
            ps.setString(4, item.getCustomerId());
        })
        .assertUpdates(true)
        .build();
}
~~~

Với PreparedStatementSetter, thứ tự tham số trong code phải khớp tuyệt đối với thứ tự dấu ? trong SQL. Nếu đổi thứ tự cột trong câu SQL, phải đổi thứ tự binding tương ứng.

Named parameters thường dễ bảo trì khi câu SQL có nhiều cột. PreparedStatementSetter hữu ích khi cần binding kiểu dữ liệu đặc biệt hoặc muốn kiểm soát chính xác cách set parameter.

## 5. Bean mapping và custom parameter source

Spring Batch hỗ trợ nhiều cách tạo tham số:

| Cách binding | Khi phù hợp |
| --- | --- |
| BeanPropertyItemSqlParameterSourceProvider | Property JavaBean khớp tên named parameter |
| ItemSqlParameterSourceProvider tùy chỉnh | Cần chuyển đổi hoặc tính parameter trước khi bind |
| ItemPreparedStatementSetter | Dùng placeholder vị trí và kiểm soát JDBC type |

Custom provider có thể trả về MapSqlParameterSource:

~~~java
ItemSqlParameterSourceProvider<CustomerUpdate> provider = item ->
    new MapSqlParameterSource()
        .addValue("customerId", item.getCustomerId())
        .addValue("email", item.getEmail())
        .addValue("status", item.getStatus())
        .addValue("updatedAt", item.getUpdatedAt());
~~~

Sau đó cấu hình:

~~~java
new JdbcBatchItemWriterBuilder<CustomerUpdate>()
    .dataSource(dataSource)
    .sql("""
        update customer
        set email = :email,
            status = :status,
            updated_at = :updatedAt
        where customer_id = :customerId
        """)
    .itemSqlParameterSourceProvider(provider)
    .build();
~~~

Custom provider hữu ích khi tên field khác tên cột, khi cần áp dụng conversion hoặc khi item chứa nested object. Giữ provider stateless và không thực hiện query hoặc side effect trong quá trình tạo parameter source.

## 6. Dùng JdbcBatchItemWriter cho INSERT

JdbcBatchItemWriter có thể chèn một hàng cho mỗi item:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderInsertWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order
                (source_order_id, customer_id, total, status)
            values
                (:sourceOrderId, :customerId, :total, :status)
            """)
        .itemSqlParameterSourceProvider(
            new BeanPropertyItemSqlParameterSourceProvider<>()
        )
        .assertUpdates(true)
        .build();
}
~~~

Mỗi item tạo một bộ tham số cho cùng câu INSERT. Nếu một item vi phạm unique constraint, database có thể báo lỗi batch. Cách driver báo update counts và chi tiết câu lệnh thất bại có thể khác nhau.

Nếu input có thể chứa duplicate business key, quyết định trước nên:

- Từ chối duplicate và để step fail hoặc skip item theo policy.
- Dùng upsert nếu nghiệp vụ cho phép ghi đè.
- Deduplicate trước writer.
- Lưu record trùng vào bảng quarantine.

Không giả định JdbcBatchItemWriter tự xử lý duplicate hoặc tự chuyển INSERT thành UPDATE.

## 7. Dùng JdbcBatchItemWriter cho UPDATE

Một update thường có điều kiện WHERE theo business key hoặc primary key:

~~~sql
update customer
set status = :status,
    updated_at = :updatedAt
where customer_id = :customerId
~~~

Ví dụ item chứa dữ liệu cần cập nhật:

~~~java
public record CustomerStatusChange(
    String customerId,
    String status,
    LocalDateTime updatedAt
) {}
~~~

Nếu dùng record, có thể tạo ItemSqlParameterSourceProvider rõ ràng:

~~~java
ItemSqlParameterSourceProvider<CustomerStatusChange> provider = item ->
    new MapSqlParameterSource()
        .addValue("customerId", item.customerId())
        .addValue("status", item.status())
        .addValue("updatedAt", item.updatedAt());
~~~

Writer:

~~~java
new JdbcBatchItemWriterBuilder<CustomerStatusChange>()
    .dataSource(dataSource)
    .sql("""
        update customer
        set status = :status,
            updated_at = :updatedAt
        where customer_id = :customerId
        """)
    .itemSqlParameterSourceProvider(provider)
    .assertUpdates(true)
    .build();
~~~

Điều kiện WHERE cần đủ chọn đúng record. Nếu chỉ lọc theo một field không duy nhất, một item có thể cập nhật nhiều hàng. Hãy dùng primary key hoặc business key có unique constraint nếu mỗi item phải đại diện cho đúng một hàng.

## 8. Dùng JdbcBatchItemWriter cho DELETE

Writer cũng có thể xóa record theo từng item:

~~~java
@Bean
JdbcBatchItemWriter<ExpiredRecord> expiredRecordDeleteWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ExpiredRecord>()
        .dataSource(dataSource)
        .sql("""
            delete from temporary_record
            where record_id = :recordId
            """)
        .itemSqlParameterSourceProvider(
            new BeanPropertyItemSqlParameterSourceProvider<>()
        )
        .assertUpdates(true)
        .build();
}
~~~

Nếu record không tồn tại, DELETE có thể ảnh hưởng 0 hàng. Đó có thể là lỗi cần phát hiện, hoặc có thể là kết quả hợp lệ nếu thao tác được thiết kế idempotent. Quyết định này ảnh hưởng đến assertUpdates.

## 9. assertUpdates và update count

Builder có tùy chọn assertUpdates. Khi bật, JdbcBatchItemWriter kiểm tra update count trả về cho từng item và báo lỗi nếu một câu lệnh không ảnh hưởng hàng nào. Đây là hành vi mặc định thường dùng; nên cấu hình rõ trong code để thể hiện ý định:

~~~java
.assertUpdates(true)
~~~

Ví dụ UPDATE theo customerId:

~~~sql
update customer
set status = :status
where customer_id = :customerId
~~~

Nếu customerId không tồn tại, update count có thể là 0. Với assertUpdates bật, writer ném EmptyResultDataAccessException thay vì âm thầm coi item đã được cập nhật.

assertUpdates kiểm tra ít nhất một hàng bị ảnh hưởng; nó không phải cơ chế bảo đảm chính xác một hàng bị cập nhật. Nếu WHERE có thể khớp nhiều hàng và nghiệp vụ yêu cầu đúng một hàng, cần unique constraint hoặc kiểm tra update count bằng writer tùy chỉnh.

Một số JDBC driver có thể trả SUCCESS_NO_INFO khi biết batch statement thành công nhưng không cung cấp số hàng chính xác. Không nhầm giá trị này với 0. Hành vi update count cần được kiểm chứng với driver/database thực tế.

## 10. Khi nào dùng assertUpdates(false)?

Có thể tắt kiểm tra:

~~~java
.assertUpdates(false)
~~~

Điều này phù hợp khi update count bằng 0 là kết quả được chấp nhận, chẳng hạn:

- Xóa một record đã bị xóa trước đó.
- Cập nhật trạng thái chỉ khi record đang ở một trạng thái cụ thể; không khớp điều kiện có thể là no-op hợp lệ.
- Writer được dùng cho câu SQL mà không ảnh hưởng hàng là kết quả bình thường.

Tuy nhiên, tắt assertUpdates có thể che giấu business key sai, record nguồn không tồn tại hoặc query WHERE bị lỗi. Nếu mỗi item bắt buộc phải cập nhật một hàng, giữ assertUpdates bật và xử lý lỗi rõ ràng.

Nếu cần phân biệt record không tồn tại với version conflict hoặc trạng thái không phù hợp, một writer tùy chỉnh có thể truy vấn/kiểm tra chi tiết hơn. Không nên tắt assertion rồi bỏ qua mọi update count bằng 0.

## 11. Optimistic locking trong batch update

Khi nhiều tiến trình có thể cập nhật cùng một hàng, optimistic locking giúp phát hiện dữ liệu đã thay đổi kể từ lúc đọc. Một bảng có cột version:

~~~sql
update customer
set status = :status,
    version = version + 1
where customer_id = :customerId
  and version = :version
~~~

Item mang version đã đọc:

~~~java
public record CustomerUpdate(
    String customerId,
    String status,
    long version
) {}
~~~

Nếu version trong database không còn khớp, câu UPDATE ảnh hưởng 0 hàng. Với assertUpdates(true), writer phát hiện việc update không thành công. Đây có thể là optimistic locking conflict, không nhất thiết là record bị thiếu.

Không retry mù một version conflict bằng cùng item và cùng version; điều kiện sẽ tiếp tục không khớp. Cần đọc lại dữ liệu, áp dụng lại nghiệp vụ hoặc đưa record vào luồng xử lý conflict riêng.

Nếu cần phân biệt conflict và missing row, kiểm tra bằng truy vấn bổ sung hoặc custom writer, đồng thời cân nhắc race condition giữa kiểm tra và update. Unique key/version predicate vẫn là phần bảo vệ chính ở database.

## 12. Batch update và upsert

Upsert có nghĩa insert nếu chưa tồn tại hoặc update nếu đã tồn tại. Cú pháp phụ thuộc database:

- PostgreSQL hỗ trợ INSERT ... ON CONFLICT ... DO UPDATE.
- MySQL có INSERT ... ON DUPLICATE KEY UPDATE.
- Một số database hỗ trợ MERGE với cú pháp riêng.

Ví dụ PostgreSQL:

~~~sql
insert into customer_summary
    (customer_id, total_orders, updated_at)
values
    (:customerId, :totalOrders, :updatedAt)
on conflict (customer_id)
do update set
    total_orders = excluded.total_orders,
    updated_at = excluded.updated_at
~~~

JdbcBatchItemWriter có thể gửi câu SQL upsert này cho từng item như một batch. Cần kiểm tra update count và semantics cụ thể của database; một số upsert có thể trả count khác nhau cho insert và update.

Không dùng cú pháp upsert chung cho mọi database. Hãy viết SQL theo dialect đang triển khai và có integration test trên đúng engine.

## 13. Batch update với null và SQL type

Named parameter source hoặc PreparedStatementSetter phải bind null đúng kiểu. Với một số driver, null không có kiểu rõ ràng có thể gây lỗi khi database không thể suy ra SQL type.

Với MapSqlParameterSource, có thể chỉ định SQL type:

~~~java
new MapSqlParameterSource()
    .addValue("customerId", item.customerId(), Types.VARCHAR)
    .addValue("status", item.status(), Types.VARCHAR)
    .addValue("updatedAt", item.updatedAt(), Types.TIMESTAMP);
~~~

Với PreparedStatementSetter, dùng setter phù hợp hoặc setNull:

~~~java
if (item.getEmail() == null) {
    ps.setNull(1, Types.VARCHAR);
} else {
    ps.setString(1, item.getEmail());
}
~~~

Null parameter thường được gửi như SQL NULL. Nó không tương đương với việc bỏ cột khỏi câu INSERT để database tự áp dụng DEFAULT. Nếu cần database default, hãy bỏ cột khỏi SQL hoặc dùng cú pháp DEFAULT phù hợp.

Với số tiền, dùng BigDecimal; với thời gian, chọn LocalDate, LocalDateTime, Instant hoặc JDBC type phù hợp với schema và driver. Tránh chuyển số tiền qua double hoặc format thời gian thành chuỗi nếu không cần.

## 14. Chunk size và kích thước JDBC batch

JdbcBatchItemWriter nhận một Chunk từ step và tạo batch parameters cho các item trong chunk. Nếu processor lọc item bằng cách trả về null, số item thực sự tới writer sẽ ít hơn số item reader đã đọc.

Ví dụ:

~~~java
return new StepBuilder("updateCustomersStep", jobRepository)
    .<CustomerInput, CustomerUpdate>chunk(200, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(customerUpdateWriter)
    .build();
~~~

Với chunk size 200, writer thường nhận tối đa 200 output item cho một lần write. Kích thước chunk cũng ảnh hưởng tần suất commit, phạm vi rollback, thời gian giữ lock và lượng dữ liệu cần giữ trong memory.

Không nhầm chunk size với page size của reader. Page size quyết định lượng dữ liệu reader lấy trong một page query; chunk size quyết định số item được xử lý trong transaction chunk.

Chunk lớn có thể tăng hiệu quả batch nhưng làm transaction dài hơn và rollback tốn hơn. Chunk nhỏ giảm thời gian transaction nhưng tăng số lần commit và overhead. Hãy đo với dữ liệu, database và driver gần production.

## 15. Tối ưu hiệu năng JDBC batch

Các yếu tố ảnh hưởng hiệu năng:

- Kích thước chunk và số parameter set trong mỗi batch.
- JDBC driver có hỗ trợ batch tốt hay không.
- Database có tối ưu/rewrite batch statement hay không.
- Index trên cột trong WHERE.
- Trigger, foreign key và constraint của bảng.
- Network latency giữa ứng dụng và database.
- Số connection sẵn có trong pool.
- Độ rộng hàng và kiểu dữ liệu cần bind.

Một số hướng thực tế:

1. Dùng một câu SQL cố định cho các item trong cùng writer.
2. Chỉ cập nhật các cột thực sự cần thay đổi.
3. Đảm bảo cột tìm kiếm trong WHERE có index phù hợp.
4. Chọn chunk size bằng benchmark có kiểm soát.
5. Tránh gọi JdbcTemplate.update() riêng cho từng item nếu có thể dùng batch writer.
6. Tránh query bổ sung cho từng item trong parameter provider.
7. Theo dõi thời gian ghi, lock wait và database CPU.

Driver có thể có tùy chọn tối ưu batch riêng, chẳng hạn rewrite nhiều INSERT thành một dạng SQL tối ưu. Các tùy chọn này phụ thuộc vendor và có thể không áp dụng cho UPDATE. Chỉ bật sau khi đọc tài liệu driver và đo trên workload thực tế.

## 16. JdbcBatchItemWriter và transaction của step

JdbcBatchItemWriter không tự bắt đầu hoặc commit một transaction cho từng item. Trong chunk-oriented step, transaction manager của step quản lý transaction bao quanh quá trình đọc/xử lý/ghi chunk theo cấu hình.

~~~text
BEGIN CHUNK TRANSACTION
  Read items
  Process items
  JdbcBatchItemWriter.write(chunk)
    -> JDBC batchUpdate
  Update execution context
COMMIT CHUNK
~~~

Nếu writer ném exception và exception được cấu hình rollback, transaction chunk được rollback. Các update đã thực hiện trong cùng transaction database sẽ không được commit.

Để điều này đúng, datasource mà JdbcBatchItemWriter dùng phải tham gia transaction do transaction manager của step quản lý. Cấu hình phổ biến là dùng cùng DataSource cho writer và transaction manager tương ứng.

Nếu writer dùng một datasource khác hoặc connection tự mở ngoài transaction, thao tác có thể commit độc lập. Khi đó rollback của step không bảo đảm hoàn tác batch update đó.

## 17. BatchUpdateException và lỗi một phần

JDBC driver có thể ném BatchUpdateException khi một hoặc nhiều câu lệnh trong batch thất bại. Exception có thể chứa update counts cho các lệnh đã chạy trước lỗi hoặc trạng thái của các lệnh trong batch.

Không nên giả định batch luôn thất bại trước khi có bất kỳ statement nào được thực thi. Hành vi cụ thể phụ thuộc driver và database.

Nếu tất cả statement tham gia cùng transaction chunk và database hỗ trợ rollback, transaction rollback sẽ hoàn tác các thay đổi chưa commit. Nếu dùng autocommit, non-transactional table hoặc resource ngoài database, một phần side effect có thể đã tồn tại.

Khi điều tra lỗi:

- Ghi nhận SQLState, vendor error code và nguyên nhân gốc.
- Xác định item/business key liên quan nếu driver cung cấp được.
- Kiểm tra transaction manager và autocommit.
- Không log toàn bộ parameter nhạy cảm.
- Dùng integration test với driver thật để xác nhận behavior.

## 18. Retry và skip khi batch update lỗi

Không phải mọi lỗi JDBC đều phù hợp với retry hoặc skip:

| Lỗi | Xử lý thường phù hợp |
| --- | --- |
| Deadlock tạm thời | Retry có giới hạn |
| Connection reset hoặc resource tạm thời unavailable | Retry nếu exception được phân loại transient |
| Duplicate key | Skip/quarantine nếu record trùng được phép loại bỏ; nếu không thì fail |
| Không tìm thấy hàng cần update | Skip hoặc fail tùy business rule |
| Version conflict | Đọc lại và xử lý conflict; không retry cùng version vô hạn |
| Sai tên cột hoặc SQL syntax | Fail nhanh |
| Database hết dung lượng | Fail và xử lý hạ tầng |

Ví dụ cấu hình:

~~~java
return new StepBuilder("updateCustomersStep", jobRepository)
    .<CustomerUpdate, CustomerUpdate>chunk(200, transactionManager)
    .reader(reader)
    .writer(customerUpdateWriter)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .skip(EmptyResultDataAccessException.class)
    .skipLimit(20)
    .build();
~~~

Ví dụ này chỉ phù hợp nếu update count bằng 0 được xem là record có thể bỏ qua. Nếu không tìm thấy customer là lỗi nghiêm trọng, đừng skip exception đó.

Đừng cấu hình skip cho DataAccessException tổng quát. Điều đó có thể bỏ qua lỗi kết nối, SQL sai hoặc lỗi schema khiến dữ liệu không được ghi.

## 19. Idempotency và restart

Spring Batch có thể đọc lại item của chunk chưa commit khi retry hoặc restart. Với writer database, transaction chunk cùng datasource giúp rollback batch update chưa commit. Tuy nhiên, nếu writer ghi sang datasource khác, gọi remote service hoặc có side effect ngoài transaction, cùng item có thể được xử lý lại.

Để update an toàn khi chạy lại:

- Dùng business key ổn định.
- Thiết kế UPDATE để đặt giá trị trạng thái cuối cùng thay vì cộng dồn ngoài ý muốn.
- Dùng version column nếu cần phát hiện concurrent modification.
- Dùng unique constraint hoặc idempotency key cho insert/upsert.
- Lưu batch ID/source ID để phân biệt một lần import với lần import khác.

Ví dụ UPDATE đặt status thành COMPLETED thường idempotent nếu lặp lại không tạo thêm side effect. Nhưng câu lệnh set balance = balance + :amount không idempotent; chạy lại sẽ cộng tiền hai lần. Với thao tác cộng dồn, cần operation ID và cơ chế deduplication bền vững.

## 20. Không tự động lấy generated keys vào item

JdbcBatchItemWriter được thiết kế để thực thi batch statement, không phải cơ chế tổng quát để lấy generated key của từng item rồi cập nhật ngược vào object đầu vào.

Nếu cần ID do database sinh:

- Có thể để database tạo ID và truy vấn lại bằng business key.
- Dùng sequence/service tạo ID trước khi writer chạy.
- Dùng writer tùy chỉnh với JDBC API hỗ trợ generated keys và xác nhận mapping key-to-item.
- Tách insert và bước đọc lại/lookup thành các step phù hợp.

Không giả định JdbcBatchItemWriter tự gán generated ID vào item sau INSERT. Nếu các bước sau cần ID, thiết kế rõ cách lấy ID và kiểm thử với database/driver thực tế.

## 21. Upsert và SQL theo database

SQL batch writer dùng câu lệnh cố định cho mọi item. Nếu cú pháp phụ thuộc database, có thể cấu hình writer theo profile/dialect hoặc repository phù hợp.

Không ghép tên bảng/cột trực tiếp từ dữ liệu item vào SQL. Named parameter chỉ bind giá trị, không bind identifier SQL. Nếu cần chọn table theo tenant hoặc route, dùng mapping whitelist từ cấu hình và chọn writer/query đã định nghĩa sẵn.

Không nối chuỗi input trực tiếp vào câu SQL. Dùng named parameter hoặc PreparedStatement để bind values, tránh SQL injection và lỗi quoting.

## 22. Dùng JdbcBatchItemWriter trong step có processor

Processor thường chuyển input thành command/update model:

~~~java
public class CustomerUpdateProcessor
        implements ItemProcessor<CustomerInput, CustomerUpdate> {

    @Override
    public CustomerUpdate process(CustomerInput input) {
        if (input.customerId() == null) {
            throw new InvalidCustomerException("customerId is required");
        }

        return new CustomerUpdate(
            input.customerId(),
            normalizeStatus(input.status()),
            LocalDateTime.now()
        );
    }
}
~~~

Step:

~~~java
return new StepBuilder("updateCustomersStep", jobRepository)
    .<CustomerInput, CustomerUpdate>chunk(200, transactionManager)
    .reader(customerReader)
    .processor(customerUpdateProcessor)
    .writer(customerUpdateWriter)
    .build();
~~~

Writer chỉ cần biết CustomerUpdate và SQL. Nó không cần biết input đến từ JSON, CSV, JDBC hay message source. Tách command/update model giúp SQL binding và business validation có ranh giới rõ ràng.

Nếu processor trả null, item bị lọc và không được gửi tới writer. Hãy tính số item filter riêng nếu cần reconciliation giữa số hàng đọc và số hàng cập nhật.

## 23. Thread safety và lifecycle của writer

JdbcBatchItemWriter được thiết kế thread-safe sau khi các property đã được cấu hình. Vì vậy, thông thường có thể khai báo một singleton bean dùng trong step.

Tuy nhiên, các thành phần do ứng dụng cung cấp cũng phải an toàn khi dùng đồng thời:

- ItemSqlParameterSourceProvider không nên giữ mutable state theo item.
- ItemPreparedStatementSetter chỉ nên ghi vào PreparedStatement được truyền vào.
- Không lưu item hiện tại hoặc parameter source vào field dùng chung.
- Không dùng chung object DTO mutable giữa các worker nếu có khả năng bị sửa.

Writer không cần tự mở và giữ một connection lâu dài. Nó dùng template/data source để thực hiện batch; transaction manager quản lý connection theo transaction. Không gọi close connection thủ công trong provider hoặc setter.

## 24. Kiểm thử JdbcBatchItemWriter

Unit test provider/setter có thể xác nhận cách item được chuyển thành parameter. Nhưng để kiểm tra SQL, batch execution, update count, null binding và transaction, nên dùng integration test với database.

Các tình huống cần bao phủ:

- Ghi nhiều item trong một chunk và kiểm tra tất cả hàng được cập nhật.
- UPDATE theo business key không tồn tại.
- INSERT vi phạm unique constraint.
- DELETE khi record không còn tồn tại.
- Null parameter và kiểu dữ liệu thời gian/số.
- SQL có điều kiện version để phát hiện optimistic locking conflict.
- Một item lỗi trong batch và transaction rollback.
- Restart/retry không tạo duplicate hoặc áp dụng side effect hai lần.

H2 có thể phù hợp cho test SQL cơ bản, nhưng cú pháp upsert, update count, type conversion và batch error behavior có thể khác database production. Dùng Testcontainers hoặc môi trường integration với đúng database/driver cho những tính năng phụ thuộc vendor.

## 25. Ví dụ integration test cho batch update

Giả sử bảng customer có hai hàng:

~~~sql
insert into customer(customer_id, status)
values ('C-1', 'NEW'), ('C-2', 'NEW');
~~~

Chạy writer với hai update:

~~~java
Chunk<CustomerStatusChange> chunk = new Chunk<>(List.of(
    new CustomerStatusChange("C-1", "ACTIVE", now),
    new CustomerStatusChange("C-2", "SUSPENDED", now)
));

writer.write(chunk);
~~~

Sau khi transaction commit, kiểm tra:

~~~sql
select customer_id, status
from customer
where customer_id in ('C-1', 'C-2')
order by customer_id;
~~~

Kết quả mong đợi là C-1 có ACTIVE và C-2 có SUSPENDED. Test cũng nên xác nhận update count hoặc trạng thái khi thêm một item có customerId không tồn tại.

Trong test Spring Batch hoàn chỉnh, launch step/job qua JobLauncherTestUtils để xác nhận writer được gọi trong chunk transaction và StepExecution có status, writeCount, rollback/skip count đúng mong đợi.

## 26. Kiểm thử rollback khi một update thất bại

Để chứng minh batch update tham gia transaction chunk:

1. Chuẩn bị nhiều customer và trạng thái ban đầu.
2. Để JdbcBatchItemWriter thực hiện update trong chunk.
3. Cố ý ném exception trước khi chunk commit, ví dụ qua một writer tiếp theo trong composite hoặc thành phần test được thiết kế để fail.
4. Xác nhận step rollback.
5. Đọc lại database và xác nhận các update của chunk chưa commit không còn hiệu lực.

Test cần dùng đúng datasource và transaction manager như cấu hình production. Nếu một writer mở connection riêng với autocommit, kết quả có thể khác và rollback chunk không hoàn tác update đó.

## 27. Những lỗi thường gặp khi dùng batch update writer

**Gọi update từng item trong vòng lặp:** làm mất lợi ích batch. Dùng JdbcBatchItemWriter khi nhiều item chạy cùng một SQL template.

**Tên named parameter không khớp property:** parameter source không tìm được giá trị. Kiểm tra SQL, getter và custom provider.

**Sai thứ tự dấu hỏi:** PreparedStatementSetter gán nhầm cột. Đối chiếu thứ tự placeholder và setter.

**Tắt assertUpdates tùy tiện:** update không tìm thấy hàng có thể bị bỏ qua âm thầm. Chỉ tắt khi zero-row update là kết quả hợp lệ.

**Cho rằng assertUpdates kiểm tra đúng một hàng:** nó kiểm tra ít nhất một hàng bị ảnh hưởng, không bảo đảm chính xác một hàng. Dùng unique constraint hoặc kiểm tra riêng.

**Coi null như database default:** parameter null thường là SQL NULL. Muốn dùng DEFAULT, cần điều chỉnh câu SQL.

**Retry lỗi dữ liệu cố định:** duplicate key, version conflict hoặc business key sai không tự hết. Phân loại lỗi trước khi retry.

**Cho rằng JDBC batch luôn atomic:** atomicity phụ thuộc transaction, database và driver. Dùng transaction chunk và kiểm thử với engine thật.

**Dùng chunk quá lớn:** transaction dài, lock lâu và rollback tốn kém. Đo và điều chỉnh theo workload.

**Dùng SQL identifier từ input:** named parameter chỉ bind giá trị, không bảo vệ identifier được nối vào SQL. Dùng whitelist cấu hình.

**Kỳ vọng writer tự trả generated key:** JdbcBatchItemWriter không tự gán key về item. Thiết kế lookup hoặc writer riêng.

**Dùng writer cho một bulk UPDATE duy nhất:** khi chỉ cần một câu SQL set-based, tasklet/JdbcTemplate thường phù hợp hơn.

## 28. Quy trình triển khai batch update writer trong production

Trước tiên, xác định mỗi item tương ứng với một INSERT, UPDATE hay DELETE và chọn business key/điều kiện WHERE phù hợp. Dùng SQL cố định, bind giá trị bằng named parameter provider hoặc PreparedStatementSetter. Nếu mỗi item cần một kiểu binding riêng, tạo provider/adapter stateless và kiểm soát rõ null cùng SQL type.

Tiếp theo, cấu hình JdbcBatchItemWriter bằng datasource và câu SQL. Bật assertUpdates nếu mỗi item phải tác động ít nhất một hàng; chỉ tắt khi zero-row update là một kết quả được nghiệp vụ chấp nhận. Đăng ký writer trong chunk step dùng transaction manager gắn với datasource đó. Chọn chunk size dựa trên hiệu năng, lock và rollback scope.

Cuối cùng, kiểm thử trên database tương thích production: nhiều item trong một batch, zero-row update, constraint violation, null binding, optimistic locking, rollback, retry và restart. Dùng idempotency key hoặc update semantics an toàn khi item có thể được xử lý lại. Theo dõi thời gian write, batch size, update failure, deadlock và connection pool để điều chỉnh vận hành.

JdbcBatchItemWriter giúp Spring Batch ghi nhiều item bằng một mẫu SQL và nhiều bộ tham số trong mỗi chunk. Nó hỗ trợ insert, update và delete; named parameter hoặc prepared statement setter quyết định cách bind dữ liệu, còn transaction manager của step quyết định commit/rollback. Khi hiểu đúng update count, null binding, optimistic locking, retry và batch size, batch update writer có thể ghi dữ liệu hiệu quả mà vẫn giữ được tính nhất quán và khả năng phục hồi của job.
