# Phân biệt saveAll, batch insert và batch update qua JDBC trực tiếp

Khi cần ghi nhiều bản ghi, ba lựa chọn thường được nhắc đến là ¤saveAll(...)¤, batch insert và batch update bằng JDBC. Chúng đều có thể giảm chi phí khi xử lý nhiều đối tượng, nhưng không có cùng semantics.

- ¤saveAll(...)¤ của Spring Data JDBC lưu nhiều **aggregate** theo mapping và vòng đời persistence của Spring Data.
- ¤JdbcAggregateTemplate.insertAll(...)¤ và ¤updateAll(...)¤ cho biết rõ toàn bộ đầu vào là aggregate mới hay aggregate đã tồn tại.
- ¤JdbcTemplate.batchUpdate(...)¤ hoặc ¤NamedParameterJdbcTemplate.batchUpdate(...)¤ gửi nhiều bộ tham số cho cùng một câu SQL JDBC.
- Một câu ¤UPDATE ... WHERE ...¤ hoặc ¤INSERT ... SELECT ...¤ dạng set-based có thể hiệu quả hơn cả batch nếu nhiều hàng dùng chung một quy tắc SQL.

Chọn cách nào phụ thuộc vào việc dữ liệu có thuộc aggregate hay không, có cần domain invariant/callback/version không, câu lệnh có giống nhau giữa các hàng không, và ứng dụng có cần generated ID hoặc kết quả từng hàng hay không.

Bài học này phân tích semantics, SQL được thực thi, ví dụ Java, transaction, batch size, kết quả update count và các giới hạn cần đo trên database/driver thực tế.

## 1. Ba khái niệm không đồng nghĩa

Giả sử ứng dụng nhập 2.000 mặt hàng vào bảng ¤inventory_items¤.

| Cách ghi | Đơn vị làm việc | Ai tạo SQL? | Có giữ aggregate mapping? |
|---|---|---|---|
| ¤repository.saveAll(items)¤ | Nhiều aggregate root | Spring Data JDBC | Có |
| ¤JdbcAggregateTemplate.insertAll(items)¤ | Nhiều aggregate mới | Spring Data JDBC | Có |
| ¤JdbcAggregateTemplate.updateAll(items)¤ | Nhiều aggregate đã tồn tại | Spring Data JDBC | Có |
| JDBC batch insert | Nhiều bộ tham số cho một INSERT | Ứng dụng cung cấp SQL | Không tự động |
| JDBC batch update | Nhiều bộ tham số cho một UPDATE | Ứng dụng cung cấp SQL | Không tự động |
| Set-based UPDATE | Một câu lệnh tác động nhiều hàng | Ứng dụng cung cấp SQL | Không tự động |

Điểm dễ nhầm là từ “batch”. ¤saveAll¤ có hỗ trợ gom các thay đổi aggregate và nhóm những thao tác tương thích để tối ưu. Nhưng nó vẫn thực hiện persistence theo mô hình aggregate. JDBC batch trực tiếp tập trung vào việc tái sử dụng một prepared statement với nhiều bộ tham số.

Cả hai đều có thể giảm round trip hoặc chi phí thực thi, nhưng cách mapping, callbacks, version và SQL khác nhau.

## 2. saveAll của Spring Data JDBC làm gì?

Repository:

~~~java
@Table("inventory_items")
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private String sku;
    private BigDecimal unitPrice;
    private Integer available;

    // Constructor, getters và domain methods được lược bỏ.
}
~~~

~~~java
public interface InventoryItemRepository
        extends CrudRepository<InventoryItem, Long> {
}
~~~

Ghi nhiều aggregate:

~~~java
@Service
public class InventoryImportService {

    private final InventoryItemRepository repository;

    public InventoryImportService(InventoryItemRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void importItems(List<InventoryItem> items) {
        repository.saveAll(items);
    }
}
~~~

¤saveAll¤ lưu tất cả aggregate được truyền vào. Với từng aggregate, Spring Data JDBC xác định entity mới hay đã tồn tại dựa trên entity state detection, sau đó chọn insert hoặc update.

Trong implementation hiện hành, ¤JdbcAggregateTemplate.saveAll¤ gom các aggregate change vào một ¤SaveBatchingAggregateChange¤. Các thao tác có thể batch được nhóm lại để dùng đường thực thi tối ưu. Điều đó không có nghĩa mọi aggregate graph được biến thành một câu INSERT duy nhất: một aggregate có thể có nhiều bảng, quan hệ phụ thuộc và nhiều loại database action.

### 2.1. saveAll xử lý cả insert và update

Ví dụ danh sách có thể chứa:

- Item A chưa có ID và được nhận diện là mới.
- Item B có ID do database đã gán và được nhận diện là tồn tại.
- Item C có ID được ứng dụng gán, nhưng entity state vẫn báo là mới theo chiến lược nhận diện đã cấu hình.

Spring Data JDBC quyết định hành động dựa trên trạng thái entity, không chỉ dựa vào việc thuộc tính ID có null hay không. Nếu dùng ID tự gán, hãy triển khai ¤Persistable.isNew()¤ hoặc cơ chế entity state detection phù hợp.

Đừng dùng ¤saveAll¤ như một lệnh “chắc chắn insert”. Nếu muốn ép insert cho tất cả aggregate, dùng ¤insertAll¤ trên ¤JdbcAggregateTemplate¤.

### 2.2. Update aggregate có thể ghi nhiều SQL hơn dự kiến

Spring Data JDBC không theo dõi dirty state như một số ORM. Khi cập nhật một aggregate hiện có, framework thường:

1. Xóa các entity được tham chiếu trong collection.
2. Cập nhật aggregate root.
3. Chèn lại các entity được tham chiếu.

Vì vậy, nếu chỉ một dòng con thay đổi trong một aggregate có nhiều child, thao tác save có thể phát sinh nhiều SQL hơn một câu UPDATE đơn giản.

Đây là lý do ¤saveAll¤ phù hợp khi cần semantics aggregate và dữ liệu không quá lớn, nhưng không mặc nhiên là lựa chọn nhanh nhất cho mọi tác vụ nhập dữ liệu hàng loạt.

### 2.3. saveAll giữ lại trách nhiệm của Spring Data JDBC

Khi lưu qua repository/template, Spring Data JDBC vẫn thực hiện mapping aggregate và các bước lifecycle tương ứng, bao gồm callback, auditing và optimistic locking nếu được cấu hình.

Nếu aggregate có ¤@Version¤, framework kiểm tra version trong quá trình update. Khi version không khớp, thao tác có thể ném ¤OptimisticLockingFailureException¤.

Điều này rất quan trọng khi cập nhật nghiệp vụ. Không nên chuyển một command aggregate sang SQL batch chỉ vì số lượng lớn mà quên các invariant và concurrency rule.

## 3. insertAll và updateAll qua JdbcAggregateTemplate

Ngoài ¤saveAll¤, Spring Data JDBC cung cấp API rõ ràng hơn qua ¤JdbcAggregateTemplate¤ hoặc ¤JdbcAggregateOperations¤.

~~~java
@Service
public class InventoryAggregateWriter {

    private final JdbcAggregateTemplate aggregateTemplate;

    public InventoryAggregateWriter(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public List<InventoryItem> insertNewItems(
            List<InventoryItem> newItems
    ) {
        return aggregateTemplate.insertAll(newItems);
    }

    @Transactional
    public List<InventoryItem> updateExistingItems(
            List<InventoryItem> existingItems
    ) {
        return aggregateTemplate.updateAll(existingItems);
    }
}
~~~

| API | Ý nghĩa | Khi dùng |
|---|---|---|
| ¤saveAll¤ | Tự chọn insert/update theo entity state | Danh sách có thể gồm entity mới và entity cũ |
| ¤insertAll¤ | Ép insert tất cả aggregate | Chắc chắn đầu vào đều là aggregate mới |
| ¤updateAll¤ | Ép update tất cả aggregate | Chắc chắn đầu vào đều đã tồn tại |

¤insertAll¤ hữu ích khi ứng dụng tự cấp ID cho aggregate mới. ¤updateAll¤ hữu ích khi caller biết rõ tất cả aggregate đã tồn tại và muốn tránh bước nhận diện new/existing.

Đây vẫn là aggregate persistence, không phải API thay thế cho ¤JdbcTemplate.batchUpdate¤ trong mọi tình huống.

### 3.1. Đừng dùng insertAll để “thử insert nếu chưa có”

Nếu hàng đã tồn tại, insert có thể thất bại vì primary key hoặc unique constraint. ¤insertAll¤ không tự biến thành upsert.

Nếu cần insert-or-update, hãy xem database dialect có hỗ trợ upsert và API phù hợp hay không, ví dụ ¤JdbcAggregateTemplate.upsert¤ cho một aggregate khi dialect hỗ trợ single-statement upsert. Với nhiều hàng, có thể cần SQL riêng theo database.

### 3.2. Version khi updateAll

¤updateAll¤ vẫn tuân thủ optimistic locking nếu aggregate có ¤@Version¤. Một phần tử có version cũ có thể làm thao tác batch thất bại.

Không tự tăng version trên object rồi gọi updateAll để né conflict. Hãy tải trạng thái mới và áp dụng lại command theo quy tắc nghiệp vụ.

## 4. JDBC batch insert là gì?

JDBC batch insert thực hiện cùng một câu INSERT nhiều lần với các bộ tham số khác nhau trên prepared statement.

Ví dụ bảng:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    unit_price NUMERIC(15, 2) NOT NULL,
    available INTEGER NOT NULL
);
~~~

Với ¤NamedParameterJdbcTemplate¤:

~~~java
@Repository
public class InventoryBatchDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventoryBatchDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] insertBatch(List<NewInventoryRow> rows) {
        String sql = """
            INSERT INTO inventory_items (
                sku,
                unit_price,
                available
            )
            VALUES (
                :sku,
                :unitPrice,
                :available
            )
            """;

        SqlParameterSource[] batch = rows.stream()
                .map(row -> new MapSqlParameterSource()
                        .addValue("sku", row.sku())
                        .addValue("unitPrice", row.unitPrice())
                        .addValue("available", row.available()))
                .toArray(SqlParameterSource[]::new);

        return jdbc.batchUpdate(sql, batch);
    }
}
~~~

DTO đầu vào:

~~~java
public record NewInventoryRow(
        String sku,
        BigDecimal unitPrice,
        Integer available
) {
}
~~~

Ứng dụng cung cấp một câu INSERT và nhiều bộ tham số. Spring JDBC bind từng bộ vào prepared statement rồi thực hiện batch qua JDBC driver.

### 4.1. Batch insert không phải một câu INSERT nhiều VALUES

JDBC batch thường biểu diễn nhiều lần thực thi cùng prepared statement. Nó không nhất thiết được chuyển thành một câu SQL duy nhất dạng:

~~~sql
INSERT INTO inventory_items (sku, unit_price, available)
VALUES
    ('SKU-001', 10.00, 20),
    ('SKU-002', 15.00, 12),
    ('SKU-003', 25.00, 5);
~~~

Một số driver/database có thể tối ưu batch thành dạng thực thi hiệu quả hơn, nhưng điều đó phụ thuộc driver và cấu hình. Không nên giả định mọi JDBC batch sẽ được chuyển thành một multi-row INSERT.

### 4.2. Generated ID khi batch insert

Ví dụ trên trả về ¤int[]¤ số hàng bị ảnh hưởng cho từng phần tử, không trả về danh sách ¤InventoryItem¤ có ID vừa sinh.

Nếu cần generated keys:

- Kiểm tra API ¤JdbcTemplate.batchUpdate¤ có overload nhận ¤KeyHolder¤ trong Spring Framework version đang dùng.
- Kiểm tra database và JDBC driver hỗ trợ lấy generated keys cho batch như thế nào.
- Không giả định mọi driver trả về đủ keys theo cùng thứ tự.
- Nếu cần mapping aggregate, version, auditing và lifecycle callback, cân nhắc Spring Data JDBC ¤insertAll¤.

Generated key behavior là một điểm cần kiểm chứng với database/driver mục tiêu, đặc biệt khi batch insert nhiều hàng.

## 5. JDBC batch update là gì?

Batch update dùng cùng một câu UPDATE nhưng thay đổi bộ tham số cho từng hàng.

Ví dụ cập nhật giá và số lượng tồn theo SKU:

~~~java
public int[] updateBatch(List<InventoryUpdateRow> rows) {
    String sql = """
        UPDATE inventory_items
        SET unit_price = :unitPrice,
            available = :available
        WHERE sku = :sku
        """;

    SqlParameterSource[] batch = rows.stream()
            .map(row -> new MapSqlParameterSource()
                    .addValue("sku", row.sku())
                    .addValue("unitPrice", row.unitPrice())
                    .addValue("available", row.available()))
            .toArray(SqlParameterSource[]::new);

    return jdbc.batchUpdate(sql, batch);
}
~~~

DTO:

~~~java
public record InventoryUpdateRow(
        String sku,
        BigDecimal unitPrice,
        Integer available
) {
}
~~~

Mỗi phần tử tạo một lần thực thi UPDATE với giá trị riêng. Đây là cách phù hợp khi từng hàng có dữ liệu cập nhật khác nhau nhưng cùng cấu trúc SQL.

### 5.1. Batch update khác set-based update

Nếu mọi hàng cần cùng một thay đổi theo một điều kiện, một câu SQL set-based có thể đơn giản và nhanh hơn.

Ví dụ tắt tất cả sản phẩm đã ngừng kinh doanh:

~~~sql
UPDATE inventory_items
SET available = 0
WHERE discontinued = TRUE;
~~~

So sánh:

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Mỗi hàng có giá trị mới khác nhau | JDBC batch update |
| Nhiều hàng nhận cùng giá trị theo một predicate | Một set-based UPDATE |
| Mỗi aggregate có domain rule riêng | Repository/domain operation |
| Chỉ cập nhật vài cột kỹ thuật với SQL xác định | JDBC batch hoặc set-based SQL |

Set-based SQL tránh gửi từng bộ giá trị từ ứng dụng và để database xử lý tập dữ liệu ngay trong một statement. Nếu invariant có thể biểu diễn an toàn trong SQL, hãy benchmark phương án này trước khi chọn batch update.

## 6. Batch trực tiếp bằng JdbcTemplate

Nếu muốn kiểm soát kiểu JDBC parameter rõ hơn, có thể dùng ¤BatchPreparedStatementSetter¤.

~~~java
@Repository
public class InventoryJdbcBatchDao {

    private final JdbcTemplate jdbcTemplate;

    public InventoryJdbcBatchDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int[] insertBatch(List<NewInventoryRow> rows) {
        String sql = """
            INSERT INTO inventory_items (
                sku,
                unit_price,
                available
            )
            VALUES (?, ?, ?)
            """;

        return jdbcTemplate.batchUpdate(
                sql,
                new BatchPreparedStatementSetter() {

                    @Override
                    public void setValues(
                            PreparedStatement ps,
                            int index
                    ) throws SQLException {
                        NewInventoryRow row = rows.get(index);

                        ps.setString(1, row.sku());
                        ps.setBigDecimal(2, row.unitPrice());
                        ps.setInt(3, row.available());
                    }

                    @Override
                    public int getBatchSize() {
                        return rows.size();
                    }
                }
        );
    }
}
~~~

¤BatchPreparedStatementSetter¤ có hai trách nhiệm:

- ¤getBatchSize()¤ cho Spring biết số bộ tham số.
- ¤setValues(...)¤ gán tham số cho lần thực thi tại index tương ứng.

Cách này hữu ích khi cần chỉ định JDBC type rõ ràng hoặc xử lý giá trị NULL theo kiểu dữ liệu cụ thể.

Với named parameter, ¤NamedParameterJdbcTemplate¤ thường dễ đọc hơn khi câu SQL có nhiều cột.

## 7. Kết quả batch update count phải được hiểu đúng

Các API batch thường trả ¤int[]¤, mỗi phần tử tương ứng một lệnh trong batch.

Ví dụ:

~~~text
[1, 1, 0, 1]
~~~

Có thể hiểu:

- ¤1¤: một hàng bị ảnh hưởng.
- ¤0¤: không có hàng nào khớp điều kiện.
- ¤Statement.SUCCESS_NO_INFO¤ (¤-2¤): driver báo lệnh thành công nhưng không cung cấp số hàng chính xác.
- ¤Statement.EXECUTE_FAILED¤ (¤-3¤): lệnh batch tương ứng thất bại trong kết quả được driver cung cấp.

Không nên luôn giả định mọi phần tử chỉ có thể là 0 hoặc 1. JDBC driver có thể trả các giá trị đặc biệt theo hợp đồng JDBC.

Nếu ứng dụng cần biết chính xác từng hàng có được cập nhật hay không, hãy kiểm tra khả năng của driver. Với ¤SUCCESS_NO_INFO¤, không thể suy ra chính xác số hàng bị tác động.

### 7.1. Batch update có thể che khuất optimistic locking conflict

Giả sử mỗi update có điều kiện version:

~~~sql
UPDATE inventory_items
SET available = :available,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu một phần tử trả về 0, có thể ID không tồn tại hoặc version không còn khớp. Nếu driver trả ¤SUCCESS_NO_INFO¤, ứng dụng biết lệnh đã thành công theo thông tin driver nhưng không biết chính xác số hàng.

Nếu cần phản hồi conflict riêng cho từng aggregate, hãy thiết kế kết quả và cơ chế kiểm tra phù hợp; đừng dựa vào giả định update count luôn chính xác.

## 8. Batch size và chia lô

Không nên mặc định đưa toàn bộ dữ liệu vào một batch duy nhất. Batch quá lớn có thể:

- Tốn bộ nhớ để giữ parameter objects.
- Tạo transaction dài.
- Giữ lock lâu.
- Tăng lượng log/WAL và áp lực replication.
- Vượt giới hạn bind parameters hoặc packet size của database.
- Làm một lỗi nhỏ ảnh hưởng đến lượng dữ liệu lớn.

Chia dữ liệu thành từng lô:

~~~java
public void insertInChunks(List<NewInventoryRow> rows, int batchSize) {
    for (int start = 0; start < rows.size(); start += batchSize) {
        int end = Math.min(start + batchSize, rows.size());

        List<NewInventoryRow> chunk = rows.subList(start, end);
        insertBatch(chunk);
    }
}
~~~

Batch size phù hợp phụ thuộc:

- Kích thước mỗi row và số bind parameters.
- JDBC driver và database.
- Độ trễ mạng.
- Khả năng connection pool.
- Mức tải đồng thời.
- Thời gian lock và log cần chấp nhận.

Hãy đo với dữ liệu gần production thay vì chọn một con số cố định theo ví dụ trên.

### 8.1. Một transaction cho toàn bộ hay từng chunk?

Có hai chiến lược khác nhau:

| Chiến lược | Ưu điểm | Đánh đổi |
|---|---|---|
| Một transaction bao toàn bộ batch | Tất cả thành công hoặc rollback cùng nhau | Transaction dài, nhiều lock/log, rollback tốn kém |
| Một transaction mỗi chunk | Có thể resume và giới hạn tài nguyên | Có thể commit một phần dữ liệu |

Nếu yêu cầu all-or-nothing, đặt toàn bộ thao tác trong một transaction phù hợp và kiểm tra thời gian thực tế.

Nếu nhập dữ liệu rất lớn, có thể commit từng chunk, nhưng cần checkpoint, idempotency và khả năng chạy lại. Khi đó kết quả toàn job không còn là một transaction nguyên tử duy nhất.

## 9. Dùng @Transactional với JDBC batch

Spring JDBC template tham gia transaction Spring khi dùng cùng ¤DataSource¤ và transaction manager.

Ví dụ:

~~~java
@Service
public class InventoryBatchService {

    private final InventoryBatchDao dao;

    public InventoryBatchService(InventoryBatchDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void updatePrices(List<InventoryUpdateRow> rows) {
        dao.updateBatch(rows);
        // Có thể thực hiện thêm thao tác cùng transaction.
    }
}
~~~

Khi cần nhiều thao tác ghi cùng commit/rollback, transaction boundary nên được đặt ở application service. Không tự mở connection bằng ¤DriverManager.getConnection(...)¤ bên trong một phương thức đã tham gia transaction Spring.

Với chiến lược commit từng chunk, cần thiết kế transaction boundary riêng cho mỗi chunk. Không giữ một transaction bên ngoài bao trùm tất cả chunk nếu mục tiêu là commit từng phần.

### 9.1. Batch không tự bảo đảm mọi statement đã được commit

¤batchUpdate¤ là cơ chế gửi nhiều lệnh qua JDBC. Tính nguyên tử phụ thuộc transaction và database.

Nếu chạy ngoài transaction với autocommit, driver/database có thể commit theo cách riêng của từng lần thực thi. Nếu cần tất cả lệnh cùng thành công, hãy dùng transaction rõ ràng và kiểm thử rollback với database thật.

## 10. Batch insert trực tiếp có giữ aggregate invariant không?

Không tự động.

Ví dụ một aggregate ¤PurchaseOrder¤ có các invariant:

- Chỉ đơn nháp mới được thêm dòng.
- Tổng số lượng không vượt giới hạn.
- Giá đơn hàng được chốt theo quy tắc nghiệp vụ.
- Mỗi SKU chỉ xuất hiện một lần trong đơn.

Một JDBC batch INSERT vào bảng ¤order_lines¤ chỉ kiểm tra những constraint mà database khai báo. Nó không tự gọi ¤purchaseOrder.addLine(...)¤.

Nếu các bản ghi thuộc cùng aggregate, hãy thực hiện domain validation trước khi ghi. Nếu cần thay đổi aggregate state, repository/template thường là đường ghi phù hợp.

Direct batch SQL nên dùng cho use case có ranh giới và invariant được thiết kế rõ, chẳng hạn import dữ liệu đã được validate, đồng bộ kỹ thuật hoặc cập nhật một read model.

## 11. Auditing, callbacks và generated values

Spring Data JDBC repository/template có thể áp dụng entity lifecycle callbacks, auditing và mapping theo cấu hình.

JDBC batch trực tiếp không tự đi qua lifecycle của aggregate. Vì vậy, các trường như:

- ¤createdBy¤.
- ¤createdAt¤.
- ¤modifiedBy¤.
- ¤modifiedAt¤.
- ¤version¤.

phải được xử lý tường minh nếu SQL trực tiếp cần cập nhật chúng.

Tương tự, converter cho enum, custom type, embedded object và aggregate child không tự được áp dụng khi bạn tự viết SQL và bind tham số.

Nếu cần database default hoặc trigger, xác định rõ trường nào được database tạo và cách ứng dụng đọc lại giá trị đó.

## 12. Optimistic locking trong batch update trực tiếp

Khi batch update aggregate root có ¤@Version¤, SQL phải kiểm tra version cũ và tăng version mới trong cùng statement.

Ví dụ:

~~~sql
UPDATE inventory_items
SET available = :available,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Mỗi parameter set cần có ¤expectedVersion¤ đã đọc trước đó.

Tuy nhiên, batch update trực tiếp chỉ bảo vệ đúng câu SQL này. Nó không tự gọi domain method, kiểm tra các invariant khác hoặc cập nhật child table theo aggregate mapping.

Nếu một aggregate gồm nhiều bảng, phải xác định cách khóa/version và transaction bao trùm toàn bộ các câu lệnh liên quan.

## 13. Xử lý lỗi và retry

Batch có thể thất bại vì:

- Unique constraint hoặc foreign key.
- Dữ liệu không hợp lệ.
- Deadlock hoặc lock timeout.
- Network failure.
- Driver không hỗ trợ một kiểu batch/generation key.
- Một parameter set có kiểu dữ liệu không tương thích.

Không nên retry mù toàn bộ batch khi không biết statement nào đã được database thực thi hoặc transaction đã commit hay chưa.

Chiến lược phù hợp:

1. Nếu dùng transaction all-or-nothing, để lỗi làm rollback và xác nhận trạng thái transaction.
2. Nếu commit theo chunk, ghi checkpoint cho chunk đã commit.
3. Làm thao tác có thể chạy lại an toàn bằng unique key hoặc idempotency key.
4. Phân loại lỗi transient và lỗi dữ liệu.
5. Không retry lỗi constraint như thể đó là lỗi mạng.
6. Ghi nhận ID/khóa nghiệp vụ của hàng lỗi để xử lý lại.

Với deadlock, database có thể rollback transaction. Retry phải chạy lại toàn bộ transaction với dữ liệu và thứ tự khóa phù hợp, không tiếp tục giữa chừng trong transaction đã bị rollback.

## 14. Chọn giữa saveAll và JDBC batch

Bảng so sánh:

| Tiêu chí | Spring Data JDBC saveAll | JDBC batch trực tiếp |
|---|---|---|
| Mô hình dữ liệu | Aggregate | Hàng/bảng |
| New/existing detection | Có | Ứng dụng tự quyết |
| Aggregate mapping | Có | Tự viết SQL |
| Child entities | Framework xử lý theo mapping | Tự ghi theo thứ tự phụ thuộc |
| Domain invariant | Có thể gọi qua domain method trước save | Ứng dụng phải kiểm soát |
| Lifecycle callbacks/auditing | Có theo cấu hình | Không tự chạy |
| Optimistic locking | Tự xử lý qua @Version | Phải viết version predicate |
| SQL control | Framework tạo SQL | Ứng dụng kiểm soát |
| Batch SQL | Spring Data nhóm action có thể batch | JDBC batch rõ ràng cho statement |
| Generated ID | Mapping/framework xử lý theo strategy | Phụ thuộc driver/API và cách lấy key |
| Use case tiêu biểu | Lưu aggregate nghiệp vụ | Import/ETL/update hàng loạt có SQL cố định |

Một lựa chọn trung gian là ¤JdbcAggregateTemplate.insertAll/updateAll¤: vẫn giữ aggregate mapping và nói rõ ý định insert/update, đồng thời dùng API batch-aware của Spring Data JDBC.

## 15. Đo hiệu năng đúng cách

Không kết luận JDBC batch nhanh hơn chỉ vì số dòng code ít hơn. Hãy đo các yếu tố:

- Số round trip tới database.
- Số SQL statement thực tế.
- Thời gian bind và execute.
- Batch size.
- Transaction duration.
- Lock wait và deadlock.
- Database CPU, I/O và WAL.
- Connection pool utilization.
- Bộ nhớ phía ứng dụng.
- Generated key retrieval.
- Khối lượng child rows của aggregate.

Benchmark nên so sánh cùng dữ liệu, cùng schema, cùng index và cùng transaction policy.

Ví dụ so sánh ba cách:

1. Gọi ¤repository.save¤ trong vòng lặp.
2. Gọi ¤repository.saveAll¤.
3. Dùng ¤NamedParameterJdbcTemplate.batchUpdate¤.

Đo riêng insert mới và update aggregate hiện có. Không trộn hai trường hợp vì update aggregate trong Spring Data JDBC có thể xóa/chèn lại referenced entities.

## 16. Kiểm thử batch

Các bài test nên bao gồm:

| Tình huống | Điều cần xác nhận |
|---|---|
| Danh sách rỗng | Không phát sinh SQL ngoài dự kiến |
| Batch insert hợp lệ | Số hàng và dữ liệu chính xác |
| Trùng unique key | Lỗi được phân loại và transaction xử lý đúng |
| Một update không tìm thấy hàng | Update count tương ứng được hiểu đúng |
| Driver trả SUCCESS_NO_INFO | Không giả định count luôn là 1 |
| Version không khớp | Conflict được phát hiện theo thiết kế |
| Một chunk thất bại | Rollback hoặc partial commit đúng policy |
| Retry một chunk | Không tạo dữ liệu trùng |
| Generated keys | Key được lấy đúng theo driver/database |
| Aggregate có child | Thứ tự insert/update và FK đúng |
| Callback/auditing | Có chạy với repository/template; không giả định với direct SQL |

Dùng database engine và JDBC driver gần production. H2 có thể khác PostgreSQL, MySQL hoặc SQL Server về batch, generated keys, DDL và update count.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng saveAll luôn là một INSERT duy nhất | Hiểu sai SQL và chi phí aggregate persistence | Xem nó là batch-aware aggregate save |
| Dùng saveAll cho hàng triệu aggregate trong một lần | Giữ nhiều object/change trong bộ nhớ và transaction lớn | Chia lô có transaction policy rõ |
| Dùng insertAll cho dữ liệu có thể đã tồn tại | Lỗi primary key/unique constraint | Xác định new/existing hoặc dùng upsert có chủ đích |
| Dùng updateAll cho entity mới | UPDATE không tìm thấy root | Chỉ dùng với aggregate đã tồn tại |
| Gọi save trong vòng lặp mà không đo | Nhiều lần thực thi riêng và round trip | So sánh saveAll/template batch |
| Nghĩ batchUpdate chỉ dành cho UPDATE | Bỏ lỡ khả năng batch INSERT/DELETE | Dùng cùng API với SQL phù hợp |
| Giả định batch luôn là một câu SQL | Đánh giá sai behavior driver | Kiểm tra SQL/driver thực tế |
| Không kiểm tra update count đặc biệt | Phân loại sai kết quả | Xử lý SUCCESS_NO_INFO/EXECUTE_FAILED |
| Batch SQL bỏ qua version/audit | Dữ liệu mất đồng bộ | Ghi metadata/version rõ ràng |
| Một transaction quá lớn | Lock/log/rollback tốn kém | Chọn chunk và checkpoint |
| Retry cả batch không idempotent | Ghi trùng hoặc cập nhật lặp | Dùng unique key/idempotency và checkpoint |
| Batch child trước parent | Vi phạm FK | Tôn trọng thứ tự phụ thuộc |

## 18. Quy trình chọn và triển khai

Khi cần ghi nhiều bản ghi, hãy đi theo trình tự:

**Bước 1 — Xác định đơn vị dữ liệu.** Đây là aggregate hay chỉ là các hàng kỹ thuật?

**Bước 2 — Xác định loại thao tác.** Dữ liệu gồm entity mới, entity cũ hay hỗn hợp?

**Bước 3 — Kiểm tra invariant.** Có domain method, child mapping, auditing hoặc version cần giữ không?

**Bước 4 — Chọn API.** Dùng saveAll cho aggregate hỗn hợp; insertAll/updateAll khi biết rõ trạng thái; JDBC batch khi cần SQL trực tiếp.

**Bước 5 — Xác định generated values.** Có cần generated ID, default, trigger hoặc callback không?

**Bước 6 — Thiết kế SQL.** Cùng một statement có thể áp dụng cho mọi hàng không? Có set-based statement tốt hơn không?

**Bước 7 — Chọn batch size.** Bắt đầu với lô vừa phải và benchmark theo driver/database.

**Bước 8 — Chọn transaction policy.** All-or-nothing hay commit theo chunk?

**Bước 9 — Xử lý kết quả.** Kiểm tra update counts, lỗi constraint, version conflict và generated keys.

**Bước 10 — Đo và quan sát.** So sánh latency, round trip, lock, log, bộ nhớ và khả năng phục hồi.

~~~text
Cần ghi nhiều bản ghi
        |
        v
Dữ liệu thuộc aggregate?
      /          \
    Có            Không
    |               |
    v               v
Có cả mới/cũ?   SQL cùng cấu trúc?
  /      \          /       \
Có        Không    Có        Không
|           |      |           |
v           v      v           v
saveAll   insertAll / updateAll  JDBC batch  Tách use case
           qua JdbcAggregateTemplate
        |
        v
Cần cùng một giá trị cho nhiều hàng?
        |
       Có
        |
        v
Cân nhắc set-based SQL
        |
        v
Chọn transaction + chunk size
        |
        v
Kiểm thử driver/database và đo hiệu năng
~~~

## 19. Bài tập tự suy luận

**Tình huống A — Danh sách có cả mới và cũ**

Một danh sách có 10 aggregate mới và 5 aggregate đã tồn tại. Nên bắt đầu với API nào?

**Gợi ý:** ¤saveAll¤ nếu entity state detection được cấu hình đúng. Spring Data JDBC chọn insert/update theo trạng thái từng aggregate.

**Tình huống B — Tất cả đều là aggregate mới có ID tự gán**

Có nên dùng ¤saveAll¤ không?

**Gợi ý:** Có thể, nếu entity state detection nhận diện đúng. Nếu caller muốn ép insert rõ ràng, ¤JdbcAggregateTemplate.insertAll¤ phù hợp hơn.

**Tình huống C — Cập nhật 5.000 giá trị khác nhau**

Mỗi SKU có giá mới riêng nhưng câu SQL giống nhau. Nên dùng gì?

**Gợi ý:** JDBC batch update là ứng viên phù hợp. Mỗi parameter set chứa SKU và giá tương ứng.

**Tình huống D — Đặt cùng available = 0**

Tất cả sản phẩm có cờ discontinued cần đặt available bằng 0. Nên gửi 10.000 parameter sets không?

**Gợi ý:** Có thể dùng một set-based UPDATE với predicate discontinued nếu invariant cho phép.

**Tình huống E — Cần generated IDs**

Batch INSERT trực tiếp thành công nhưng ứng dụng cần ID của từng hàng. Có thể mặc định driver trả về đầy đủ keys theo thứ tự input không?

**Gợi ý:** Không. Kiểm tra API, database và driver. Nếu cần mapping aggregate, cân nhắc Spring Data JDBC insertAll.

**Tình huống F — Version conflict trong batch**

Batch update có WHERE version = expectedVersion nhưng driver trả SUCCESS_NO_INFO. Có thể kết luận từng aggregate đã cập nhật đúng một hàng không?

**Gợi ý:** Không. Driver chỉ báo lệnh thành công mà không cung cấp số hàng chính xác. Cần cách kiểm tra/reconcile khác nếu phải xác định conflict từng item.

## 20. Ghi nhớ

| Thành phần | Trách nhiệm |
|---|---|
| ¤CrudRepository.saveAll¤ | Lưu danh sách aggregate, tự chọn insert/update theo entity state |
| ¤JdbcAggregateTemplate.insertAll¤ | Insert nhiều aggregate mới |
| ¤JdbcAggregateTemplate.updateAll¤ | Update nhiều aggregate đã tồn tại |
| ¤SaveBatchingAggregateChange¤ | Gom aggregate changes và nhóm action có thể batch |
| ¤JdbcTemplate.batchUpdate¤ | JDBC batch với prepared statement và positional parameters |
| ¤NamedParameterJdbcTemplate.batchUpdate¤ | JDBC batch với named parameters |
| ¤BatchPreparedStatementSetter¤ | Cung cấp tham số cho từng phần tử batch |
| ¤int[] update counts¤ | Kết quả từng lệnh, có thể gồm giá trị đặc biệt của JDBC |
| Set-based SQL | Một statement tác động nhiều hàng theo predicate |
| ¤@Transactional¤ | Bảo vệ tính nguyên tử theo transaction policy |
| Batch size | Cân bằng round trip, bộ nhớ, lock và log |
| ¤@Version¤ | Optimistic locking cho aggregate; direct SQL phải phối hợp rõ |

**saveAll, aggregate insert/update và JDBC batch giải quyết các bài toán khác nhau.** Dùng ¤saveAll¤ khi cần lưu nhiều aggregate và giữ mapping/lifecycle của Spring Data JDBC; dùng ¤insertAll¤ hoặc ¤updateAll¤ khi trạng thái đầu vào đã rõ; dùng JDBC batch khi cần lặp cùng một câu SQL với nhiều bộ tham số; và ưu tiên set-based SQL khi một predicate có thể cập nhật cả tập dữ liệu. Luôn xét generated IDs, version, auditing, update counts, transaction và batch size trên driver/database thực tế.

## Tài liệu tham khảo

- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): semantics của save aggregate, update root và xử lý referenced entities.
- [Spring Data Relational — JdbcAggregateOperations Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): saveAll, insertAll, updateAll và upsert.
- [Spring Data Relational — JdbcAggregateTemplate Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html): API persistence aggregate.
- [Spring Data Relational — SaveBatchingAggregateChange Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/conversion/SaveBatchingAggregateChange.html): nhóm các aggregate action có thể batch để tối ưu.
- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): batch với JdbcTemplate và NamedParameterJdbcTemplate.
- [Spring Framework — JdbcOperations Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): batchUpdate, update counts và fallback khi driver không hỗ trợ batch.

