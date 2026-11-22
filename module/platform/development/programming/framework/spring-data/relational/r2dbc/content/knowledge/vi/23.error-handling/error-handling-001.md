# Phân loại lỗi kết nối, cú pháp, ánh xạ và ràng buộc dữ liệu

Khi làm việc với Spring Data Relational R2DBC, một lỗi xuất hiện ở repository không nhất thiết bắt nguồn từ câu SQL. Nó có thể xảy ra trước khi kết nối được tạo, trong lúc bind tham số, khi database phân tích câu lệnh, khi database kiểm tra constraint, hoặc sau khi câu lệnh chạy thành công nhưng Spring không ánh xạ được hàng kết quả sang object Java.

Phân loại đúng lỗi giúp chọn cách xử lý phù hợp. Lỗi kết nối tạm thời có thể được retry có giới hạn; lỗi cú pháp cần sửa SQL; lỗi mapping cần sửa entity, projection hoặc converter; lỗi constraint thường cần xử lý theo quy tắc nghiệp vụ. Retry tất cả lỗi sẽ làm tăng tải và có thể lặp lại một thao tác ghi đã thành công ở database.

Bài học này đi qua từng nhóm lỗi trong luồng reactive R2DBC, cách Spring dịch exception, cách đọc SQLSTATE và vendor error code, cách xử lý bằng Reactor, và cách kiểm thử để phân biệt lỗi hạ tầng với lỗi dữ liệu.

## 1. Nhìn lỗi theo từng tầng trong luồng R2DBC

Một thao tác repository có thể đi qua nhiều tầng:

~~~text
Service / reactive chain
        |
Spring Data repository / template
        |
Spring R2DBC mapping and parameter binding
        |
R2DBC SPI
        |
R2DBC driver
        |
Network / connection pool
        |
Database server
        |
SQL execution and constraints
        |
Rows returned by the driver
        |
Spring row-to-object mapping
~~~

Lỗi có thể phát sinh ở bất kỳ tầng nào. Cần xác định lỗi xảy ra trước khi gửi SQL, trong khi database thực thi hay sau khi database đã trả kết quả.

| Nhóm lỗi | Thời điểm thường gặp | Ví dụ |
| --- | --- | --- |
| Kết nối và tài nguyên | Mở connection, lấy connection từ pool, gửi/nhận dữ liệu. | Database down, DNS/TLS, pool timeout, network reset. |
| Cú pháp và sử dụng SQL | Database parse hoặc thực thi câu lệnh. | Sai tên bảng/cột, thiếu bind marker, cú pháp không hợp lệ. |
| Bind và kiểu tham số | Chuẩn bị statement hoặc bind giá trị. | Sai kiểu, thiếu tham số, bind NULL không có type. |
| Ánh xạ dữ liệu | Chuyển row thành entity/projection. | Không chuyển được NUMERIC sang kiểu Java, thiếu constructor parameter. |
| Ràng buộc dữ liệu | Database kiểm tra INSERT/UPDATE/DELETE. | Unique, foreign key, NOT NULL, CHECK violation. |
| Transaction và concurrency | Commit, rollback hoặc xung đột ghi đồng thời. | Deadlock, serialization failure, transaction đã rollback. |

Một exception ở tầng service có thể bọc exception ở tầng driver. Vì vậy, không nên chỉ nhìn class của exception ngoài cùng; hãy xem cause chain, SQLSTATE và mã lỗi của vendor khi có.

## 2. Exception translation của Spring

R2DBC SPI định nghĩa các exception trong package io.r2dbc.spi. Spring R2DBC có cơ chế chuyển một số lỗi của driver thành hệ exception truy cập dữ liệu của Spring trong package org.springframework.dao.

Những exception Spring này thường kế thừa DataAccessException. Chúng giúp code ứng dụng xử lý theo nhóm ý nghĩa thay vì phụ thuộc trực tiếp vào một driver cụ thể.

Ví dụ các nhóm thường gặp:

| Ý nghĩa | Exception phía R2DBC có thể gặp | Exception Spring có thể gặp |
| --- | --- | --- |
| Lỗi cú pháp SQL | R2dbcBadGrammarException | BadSqlGrammarException |
| Vi phạm dữ liệu/constraint | R2dbcDataIntegrityViolationException | DataIntegrityViolationException hoặc DuplicateKeyException |
| Lỗi tài nguyên tạm thời | R2dbcTransientResourceException | TransientDataAccessResourceException hoặc một loại transient khác |
| Lỗi tài nguyên không tạm thời | R2dbcNonTransientResourceException | DataAccessResourceFailureException hoặc loại non-transient khác |
| Timeout | R2dbcTimeoutException | QueryTimeoutException hoặc loại timeout phù hợp |
| Lỗi rollback | R2dbcRollbackException | TransactionSystemException hoặc exception transaction phù hợp |

Bảng trên mô tả các ánh xạ có thể gặp, không phải cam kết một-một cho mọi driver và phiên bản. Exception translator sử dụng thông tin driver cung cấp; nếu driver chỉ trả exception chung hoặc thiếu SQLSTATE/error code, Spring có thể không phân loại chi tiết được.

### Xử lý ở mức abstraction của Spring

Khi ứng dụng không cần đọc thông tin riêng của driver, ưu tiên xử lý exception của Spring:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.TransientDataAccessException;

return repository.save(entity)
    .onErrorResume(DuplicateKeyException.class, error ->
        findExistingResult(entity)
    )
    .onErrorMap(TransientDataAccessException.class, error ->
        new TemporaryStorageException("Storage is temporarily unavailable", error)
    )
    .onErrorMap(DataAccessException.class, error ->
        new PersistenceOperationException("Could not persist entity", error)
    );
~~~

Ví dụ chỉ minh họa thứ tự phân loại. Nhánh DuplicateKeyException phải phù hợp với nghiệp vụ idempotent; không phải mọi duplicate đều có nghĩa có thể trả lại bản ghi cũ. Nhánh lỗi transient nên được xử lý ở nơi có đủ thông tin để quyết định retry.

Không bắt DataAccessException rồi trả về giá trị mặc định cho mọi trường hợp. Làm như vậy sẽ che mất lỗi cú pháp, lỗi mapping, vi phạm constraint và sự cố hạ tầng.

## 3. Lỗi kết nối và tài nguyên

Lỗi kết nối xảy ra trước hoặc trong lúc ứng dụng trao đổi dữ liệu với database. Một số nguyên nhân:

- Database server chưa khởi động hoặc đang restart.
- Sai hostname, port, database name hoặc DNS không phân giải được.
- Lỗi TLS/certificate hoặc thông tin xác thực.
- Network reset, socket đóng hoặc firewall ngắt kết nối.
- Connection pool hết connection khả dụng.
- Connection đã hết hạn hoặc bị server đóng.
- Timeout khi lấy connection hoặc khi thực thi câu lệnh.

Không phải mọi lỗi kết nối đều tạm thời. Database restart hoặc network gián đoạn có thể tự hồi phục; sai mật khẩu, sai hostname hoặc certificate không hợp lệ thường cần sửa cấu hình.

### Phân biệt lỗi lấy connection và lỗi chạy SQL

Hai loại timeout có ý nghĩa khác nhau:

| Tình huống | Vị trí | Hướng điều tra |
| --- | --- | --- |
| Pool acquisition timeout | Ứng dụng không lấy được connection từ pool. | Kiểm tra pool size, connection bị giữ lâu, concurrency và rò rỉ subscription. |
| Connect timeout | Driver không thiết lập được kết nối tới server. | Kiểm tra DNS, network, port, TLS và trạng thái server. |
| Statement/query timeout | Connection đã có nhưng câu lệnh chạy quá lâu. | Kiểm tra query plan, lock, tải server và timeout cấu hình. |
| Connection reset trong lúc ghi | Kết quả của thao tác có thể chưa rõ. | Kiểm tra trạng thái commit bằng ID/idempotency key trước khi retry. |

Timeout sau khi gửi lệnh ghi có thể tạo trạng thái không chắc chắn: database có thể đã commit nhưng response bị mất. Retry mù quáng có thể tạo bản ghi hoặc giao dịch nghiệp vụ trùng.

### Phân loại transient và non-transient

R2DBC SPI có các loại exception biểu diễn lỗi tạm thời và không tạm thời, chẳng hạn R2dbcTransientException, R2dbcTransientResourceException và R2dbcNonTransientResourceException. Spring cũng có hệ phân loại transient/non-transient trong DataAccessException.

Tuy nhiên, đừng quyết định retry chỉ dựa trên một class ngoài cùng. Một số lỗi được bọc qua nhiều lớp, và driver có thể phân loại khác nhau. Hãy xem cause chain và SQLSTATE nếu có.

## 4. Lỗi cú pháp SQL và lỗi sử dụng câu lệnh

Lỗi cú pháp xảy ra khi database không thể phân tích hoặc thực thi câu SQL theo cấu trúc được gửi xuống. Các nguyên nhân phổ biến:

- Sai tên bảng, cột, schema hoặc alias.
- Dùng từ khóa dành riêng làm identifier mà không quote đúng.
- Thiếu dấu phẩy, ngoặc hoặc từ khóa.
- Dùng cú pháp chỉ có ở một database khác.
- JOIN hoặc GROUP BY không hợp lệ.
- Dùng function không tồn tại hoặc sai số lượng tham số.
- Placeholder không khớp với tham số đã bind.
- Query method hoặc @Query tham chiếu sai property/column.

Ví dụ:

~~~sql
SELECT id, display_name
FROM customers
WHERE customer_id = :customerId
ORDER BY created_at DESC;
~~~

Nếu bảng customers không có cột customer_id, database có thể báo lỗi cột không tồn tại. Spring có thể dịch lỗi thành BadSqlGrammarException hoặc một exception tương ứng tùy driver.

### Phân biệt tên property và tên cột

Derived query method và Criteria thường tham chiếu property Java của entity:

~~~java
@Table("customers")
public record Customer(
    @Id Long id,
    @Column("display_name") String displayName,
    @Column("created_at") LocalDateTime createdAt
) {}
~~~

Ví dụ repository dùng property:

~~~java
Flux<Customer> findByDisplayName(String displayName);
~~~

SQL viết tay qua @Query hoặc DatabaseClient phải dùng tên cột thật:

~~~sql
SELECT id, display_name, created_at
FROM customers
WHERE display_name = :displayName;
~~~

Không dùng displayName trong SQL nếu database chỉ có cột display_name. Ngược lại, không dùng tên cột display_name làm tên property trong derived query nếu entity property là displayName.

### Bind marker và named parameter

Khi dùng DatabaseClient hoặc @Query của Spring, named parameter thường được Spring chuyển sang marker mà driver hỗ trợ. Đảm bảo:

- Mỗi named parameter trong SQL có giá trị bind tương ứng.
- Tên tham số trong @Param khớp với tên trong SQL.
- Không bind cùng một tham số bằng kiểu không tương thích.
- Không dùng bind parameter để thay tên bảng, tên cột hoặc từ khóa.
- Danh sách rỗng trong IN phải được xử lý theo chính sách rõ ràng.

Lỗi cú pháp cần được sửa trong query hoặc mapping. Retry cùng một câu SQL không thể làm câu lệnh sai trở thành hợp lệ.

## 5. Lỗi bind tham số và chuyển đổi kiểu

Một truy vấn có cú pháp hợp lệ vẫn có thể thất bại khi bind tham số. Ví dụ:

- Java Integer được bind vào cột/parameter cần UUID.
- Chuỗi ngày giờ không đúng định dạng hoặc kiểu.
- BigDecimal vượt precision/scale của cột.
- Giá trị NULL được bind mà không chỉ rõ kiểu dữ liệu.
- Collection có phần tử NULL hoặc không tương thích.
- Một tham số được khai báo trong SQL nhưng không được bind.

Với DatabaseClient, không truyền Java null trực tiếp vào bind. Dùng bindNull và khai báo kiểu:

~~~java
databaseClient.sql("""
        SELECT id, display_name
        FROM customers
        WHERE deleted_at IS NOT NULL
           OR :includeDeleted = TRUE
        """)
    .bind("includeDeleted", includeDeleted);
~~~

Ví dụ trên giả định includeDeleted luôn có giá trị. Nếu tham số có thể null, cần xác định kiểu và dùng API bindNull tương ứng:

~~~java
spec.bindNull("optionalDate", LocalDateTime.class);
~~~

Đối với tham số bắt buộc, nên validate trước khi xây dựng query thay vì để lỗi xuất hiện sâu trong driver.

### Sai kiểu dữ liệu và lỗi chuyển đổi

Một giá trị có thể hợp lệ ở Java nhưng không phù hợp với kiểu cột:

| Kiểu Java | Kiểu database thường gặp | Rủi ro |
| --- | --- | --- |
| UUID | UUID, BINARY(16), CHAR(36) | Driver/database có cách biểu diễn khác nhau. |
| BigDecimal | NUMERIC/DECIMAL | Vượt precision hoặc scale. |
| LocalDateTime | TIMESTAMP | Khác biệt timezone và độ chính xác. |
| Instant/OffsetDateTime | TIMESTAMP WITH TIME ZONE hoặc kiểu tương ứng | Mapping phụ thuộc database và driver. |
| Enum | VARCHAR, INTEGER hoặc native enum | Giá trị lưu không khớp converter. |
| Boolean | BOOLEAN, BIT hoặc kiểu số | Khác biệt mapping giữa vendor. |

Lỗi xảy ra lúc bind thường thuộc tầng statement/driver. Lỗi xảy ra khi đọc row và chuyển thành object thường thuộc tầng mapping. Phân biệt hai thời điểm này sẽ giúp tìm đúng nơi sửa.

## 6. Lỗi ánh xạ entity và projection

Mapping là quá trình chuyển dữ liệu row do driver trả về thành entity, record hoặc projection Java. Query có thể chạy thành công nhưng mapping vẫn thất bại.

Các nguyên nhân thường gặp:

- Cột kết quả thiếu hoặc alias không khớp với projection.
- Constructor không có tham số phù hợp.
- Cột SQL NULL nhưng constructor parameter/field không cho phép null theo kiểu sử dụng.
- Database trả kiểu dữ liệu mà converter không hỗ trợ.
- Enum trong database có giá trị không tồn tại trong Java enum.
- Converter tùy chỉnh không được đăng ký hoặc không áp dụng đúng chiều.
- Precision/scale hoặc kiểu số không tương thích.
- Mapping kỳ vọng entity đầy đủ nhưng SQL chỉ SELECT một phần cột.

Ví dụ entity:

~~~java
@Table("products")
public record Product(
    @Id UUID id,
    String name,
    BigDecimal price,
    ProductStatus status
) {}
~~~

Nếu query trả về:

~~~sql
SELECT id, name, price
FROM products;
~~~

thì cột status bị thiếu. Nếu mapping cần constructor đầy đủ, Spring có thể không tạo được Product. Hãy chọn một trong hai hướng:

- SELECT đầy đủ cột cần thiết để tạo entity.
- Dùng projection riêng mô tả đúng các cột query trả về.

Ví dụ projection:

~~~java
public record ProductSummary(
    UUID id,
    String name,
    BigDecimal price
) {}
~~~

### Alias và tên cột

SQL projection nên đặt alias rõ:

~~~sql
SELECT
    p.id AS id,
    p.name AS name,
    p.unit_price AS price
FROM products p;
~~~

Alias giúp mapping dễ đoán hơn, nhất là khi join nhiều bảng có cột trùng tên. Không nên dùng SELECT * trong truy vấn projection phức tạp vì schema thay đổi có thể làm kết quả ánh xạ bất ngờ.

### Converter tùy chỉnh

Khi kiểu Java và database không có mapping mặc định phù hợp, Spring Data Relational cho phép cấu hình converter. Cần xác định rõ converter đọc hay ghi:

- Converter ghi chuyển object Java thành giá trị database.
- Converter đọc chuyển giá trị database thành object Java.

Một converter chỉ đúng ở một chiều không tự động bảo đảm chiều còn lại. Hãy test cả insert/update lẫn readback.

### Phân biệt lỗi mapping với lỗi dữ liệu

Nếu database trả status = 'ARCHIVED' nhưng Java enum chỉ có NEW, ACTIVE và DISABLED, mapping có thể thất bại. Đây có thể là schema/data drift, deployment không đồng bộ hoặc thiếu giá trị enum trong code. Retry không giải quyết được. Cần quyết định giá trị mới có hợp lệ không, sau đó cập nhật enum, converter hoặc dữ liệu theo migration có kiểm soát.

## 7. Lỗi ràng buộc dữ liệu

Database constraint bảo vệ tính hợp lệ và toàn vẹn của dữ liệu. R2DBC hoặc Spring thường biểu diễn vi phạm bằng R2dbcDataIntegrityViolationException, DataIntegrityViolationException hoặc DuplicateKeyException tùy driver và exception translator.

Các nhóm constraint thường gặp:

| Constraint | Điều kiện vi phạm | Ví dụ |
| --- | --- | --- |
| PRIMARY KEY | Khóa chính trùng hoặc thiếu. | Hai bản ghi cùng id. |
| UNIQUE | Giá trị hoặc tổ hợp giá trị không duy nhất. | Email đã được dùng. |
| FOREIGN KEY | Tham chiếu tới bản ghi không tồn tại hoặc bị xóa trong khi còn phụ thuộc. | order.customer_id không tồn tại. |
| NOT NULL | Ghi NULL vào cột bắt buộc. | Tạo customer thiếu email. |
| CHECK | Giá trị không thỏa biểu thức kiểm tra. | quantity <= 0. |
| EXCLUSION hoặc constraint đặc thù | Vi phạm quy tắc loại trừ/riêng của database. | Hai khoảng thời gian không được chồng lấn. |

### Duplicate key không phải lúc nào cũng là lỗi hệ thống

Ví dụ email đã tồn tại. Nếu nghiệp vụ yêu cầu email duy nhất, đây có thể là xung đột đầu vào cần trả về HTTP 409 hoặc thông báo phù hợp, không nên retry.

~~~java
return customers.save(customer)
    .onErrorMap(DuplicateKeyException.class, error ->
        new EmailAlreadyRegisteredException(customer.email(), error)
    );
~~~

Không nên bắt mọi DataIntegrityViolationException rồi đổi thành “email đã tồn tại”. Lỗi đó có thể là foreign key, NOT NULL hoặc CHECK. Hãy xem constraint name, SQLSTATE và vendor code để phân biệt.

### Foreign key violation

Nếu tạo order tham chiếu tới customer không tồn tại, database có thể từ chối insert. Ứng dụng nên xác thực tham chiếu theo hợp đồng nghiệp vụ và vẫn để database constraint bảo vệ tính toàn vẹn trong trường hợp có race condition.

Không chỉ dựa vào bước kiểm tra trước insert: customer có thể bị xóa giữa lúc kiểm tra và lúc ghi. Foreign key vẫn là lớp bảo vệ cuối cùng.

### NOT NULL và CHECK violation

Các lỗi này thường cho thấy validation ở tầng ứng dụng chưa đầy đủ hoặc dữ liệu từ một luồng khác không tuân thủ hợp đồng. Nên chuyển thành lỗi validation/domain cụ thể khi có thể xác định chính xác constraint.

Không bỏ constraint ở database chỉ để ứng dụng không còn nhận exception. Constraint là hàng rào bảo vệ dữ liệu trước mọi đường ghi, kể cả batch job hoặc service khác.

## 8. SQLSTATE và vendor error code

Khi driver cung cấp thông tin, R2dbcException có thể chứa:

- SQLSTATE: mã phân loại lỗi theo chuẩn SQLSTATE.
- Error code: mã lỗi riêng của database vendor.
- SQL: câu lệnh liên quan nếu driver cung cấp.
- Message và cause chain.

Không phải driver nào cũng cung cấp đủ mọi trường. Không nên phụ thuộc message text vì nó có thể thay đổi theo vendor, phiên bản, locale hoặc cấu hình.

Một số lớp SQLSTATE thường hữu ích:

| SQLSTATE class | Ý nghĩa tổng quát | Ví dụ tình huống |
| --- | --- | --- |
| 08 | Connection exception | Mất kết nối hoặc lỗi kết nối. |
| 22 | Data exception | Sai định dạng/giá trị dữ liệu, vượt giới hạn. |
| 23 | Integrity constraint violation | UNIQUE, FK, NOT NULL hoặc CHECK. |
| 28 | Invalid authorization specification | Sai thông tin xác thực hoặc quyền đăng nhập. |
| 40 | Transaction rollback | Deadlock, serialization failure hoặc rollback. |
| 42 | Syntax error or access rule violation | Sai cú pháp, bảng/cột hoặc quyền truy cập. |
| 53 | Insufficient resources | Hết tài nguyên theo cách database phân loại. |
| 57 | Operator intervention | Server hủy thao tác hoặc shutdown theo cách được phân loại. |

SQLSTATE class chỉ là nhóm tổng quát. Mã con cụ thể và cách driver ánh xạ có thể khác. Ví dụ, một deadlock thường có mã thuộc class 40 nhưng cần kiểm tra code cụ thể theo database.

### Đọc thông tin lỗi từ R2dbcException

Nếu cần chẩn đoán ở mức driver:

~~~java
import io.r2dbc.spi.R2dbcException;

Throwable current = error;
while (current != null) {
    if (current instanceof R2dbcException r2dbcError) {
        String sqlState = r2dbcError.getSqlState();
        int vendorCode = r2dbcError.getErrorCode();

        log.warn(
            "R2DBC failure: sqlState={}, vendorCode={}",
            sqlState,
            vendorCode
        );
    }

    current = current.getCause();
}
~~~

Đây là đoạn minh họa truy xuất cause chain. Cần tránh ghi SQL hoặc bind value chứa dữ liệu nhạy cảm vào log. Nếu ứng dụng chỉ cần exception abstraction của Spring, có thể xử lý DataAccessException và chỉ đọc cause driver khi cần thêm chi tiết.

### Không phân loại bằng cách tìm chuỗi message

Không nên viết logic như:

~~~java
if (error.getMessage().contains("duplicate")) {
    // assume duplicate key
}
~~~

Message có thể là ngôn ngữ khác, thay đổi theo phiên bản hoặc chứa tên constraint. Ưu tiên exception type, SQLSTATE và vendor code. Nếu phải phân tích message vì driver không cung cấp metadata, cô lập logic đó trong adapter riêng và kiểm thử theo phiên bản driver cụ thể.

## 9. Chuyển exception kỹ thuật thành lỗi nghiệp vụ

Service/application layer không nên để mọi tầng phía trên phụ thuộc trực tiếp vào tên exception của PostgreSQL, MySQL hay R2DBC driver. Có thể chuyển các lỗi đã hiểu thành exception miền hoặc kết quả API phù hợp.

Ví dụ:

~~~java
public Mono<Customer> register(RegisterCustomerCommand command) {
    Customer customer = Customer.from(command);

    return customers.save(customer)
        .onErrorMap(DuplicateKeyException.class, error ->
            new EmailAlreadyRegisteredException(command.email(), error)
        )
        .onErrorMap(DataIntegrityViolationException.class, error ->
            new CustomerDataRejectedException(error)
        );
}
~~~

Thứ tự xử lý rất quan trọng: DuplicateKeyException thường là subtype của DataIntegrityViolationException. Đặt nhánh cụ thể trước nhánh tổng quát để không làm mất thông tin.

Không chuyển tất cả lỗi database thành lỗi nghiệp vụ chung. Lỗi connection có thể cần trả 503; lỗi validation có thể là 400; duplicate conflict có thể là 409; lỗi mapping hoặc SQL grammar thường là lỗi nội bộ cần cảnh báo và điều tra.

### Gợi ý ánh xạ sang HTTP

| Nhóm lỗi | Phản hồi thường phù hợp | Lưu ý |
| --- | --- | --- |
| Input validation | 400 Bad Request | Trả field/error code có thể hiểu được. |
| Unique conflict | 409 Conflict | Nêu xung đột nghiệp vụ, không lộ SQL. |
| Resource tạm thời không khả dụng | 503 Service Unavailable | Có thể kèm retry guidance nếu an toàn. |
| Query timeout | 503 hoặc 504 tùy vai trò gateway/API | Ghi correlation id, không lộ query nhạy cảm. |
| SQL grammar/mapping bug | 500 Internal Server Error | Đây thường là lỗi triển khai, không đổ trách nhiệm cho client. |
| Lỗi quyền database | 500 và cảnh báo vận hành | Thường là cấu hình/permission của ứng dụng. |

Đây là gợi ý thiết kế API, không phải quy tắc HTTP bắt buộc. Hãy giữ response ổn định và không trả raw exception message, SQL hay thông tin kết nối cho client.

## 10. Retry: chỉ thử lại lỗi có khả năng hồi phục

Retry có ích khi lỗi thực sự tạm thời, ví dụ deadlock, serialization conflict hoặc connection reset trước khi thao tác được thực hiện. Retry không có ích cho lỗi cú pháp, mapping hoặc constraint do dữ liệu không hợp lệ.

| Nhóm lỗi | Retry mặc định? | Lý do |
| --- | --- | --- |
| Sai SQL/cột không tồn tại | Không | Cần sửa câu lệnh hoặc schema. |
| Mapping/converter lỗi | Không | Cần sửa mapping hoặc dữ liệu. |
| UNIQUE/FK/NOT NULL/CHECK | Không | Dữ liệu hoặc quy tắc nghiệp vụ cần xử lý. |
| Sai credentials/quyền | Không | Cần sửa cấu hình hoặc quyền. |
| Deadlock/serialization failure | Có thể | Có thể thử lại toàn bộ transaction. |
| Connection reset trước khi gửi lệnh | Có thể | Cần xác nhận thao tác chưa xảy ra. |
| Timeout sau khi gửi lệnh ghi | Thận trọng | Kết quả commit có thể chưa rõ. |
| Pool acquisition timeout | Có thể nhưng cần giới hạn | Retry quá nhanh có thể làm pool quá tải thêm. |

### Retry với Reactor

Có thể giới hạn số lần thử và chỉ retry exception được phân loại transient:

~~~java
import java.time.Duration;

import org.springframework.dao.TransientDataAccessException;
import io.r2dbc.spi.R2dbcTransientException;
import reactor.core.Exceptions;
import reactor.util.retry.Retry;

private boolean isRetryable(Throwable error) {
    Throwable current = Exceptions.unwrap(error);

    while (current != null) {
        if (current instanceof TransientDataAccessException
                || current instanceof R2dbcTransientException) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}

private Retry databaseRetry() {
    return Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(this::isRetryable)
        .onRetryExhaustedThrow((spec, signal) -> signal.failure());
}
~~~

Ví dụ gọi:

~~~java
return performRead()
    .retryWhen(databaseRetry());
~~~

Đây là ví dụ cho thao tác đọc có thể lặp an toàn. Không nên coi mọi R2dbcTransientException đều tự động retry được; cần xét loại thao tác và trạng thái commit.

### Retry toàn bộ transaction

Với transaction nhiều bước, nếu deadlock hoặc serialization failure làm transaction rollback, cần retry toàn bộ đơn vị công việc để mọi thao tác được chạy trong transaction mới.

Có thể đặt retry bên ngoài publisher được bọc bởi TransactionalOperator:

~~~java
Mono<Order> oneAttempt =
    transactionalOperator.transactional(
        Mono.defer(() -> createOrderAndLines(command))
    );

return oneAttempt.retryWhen(databaseRetry());
~~~

Mỗi lần resubscribe vào publisher transactional sẽ bắt đầu một lần thực thi transaction mới theo transaction manager. Đặt retry bên trong một transaction đang mở có thể khiến các thao tác tiếp theo tiếp tục dùng transaction đã bị đánh dấu rollback-only hoặc ở trạng thái không thể tiếp tục.

### Retry ghi cần idempotency

Nếu timeout xảy ra sau khi database có thể đã commit, retry có thể tạo dữ liệu trùng. Với thao tác ghi quan trọng, hãy dùng một trong các cơ chế:

- ID nghiệp vụ ổn định được tạo ở ranh giới request.
- Idempotency key có unique constraint.
- Upsert với semantics được định nghĩa rõ.
- Tra cứu trạng thái theo operation ID trước khi thử lại.
- Thiết kế command để thực hiện nhiều lần nhưng chỉ tạo một kết quả nghiệp vụ.

Không tạo ID mới cho mỗi lần retry nếu các lần thử là cùng một thao tác nghiệp vụ.

## 11. Xử lý lỗi trong reactive chain

Reactive code truyền lỗi bằng error signal. Có ba operator thường dùng:

- onErrorMap: đổi loại exception nhưng vẫn giữ đường lỗi.
- onErrorResume: thay lỗi bằng một publisher khác.
- doOnError: quan sát/log/metric nhưng không thay đổi lỗi.

Ví dụ ghi log rồi truyền lỗi tiếp:

~~~java
return repository.save(entity)
    .doOnError(error ->
        log.error(
            "Could not save entity, operationId={}",
            operationId,
            error
        )
    );
~~~

Ví dụ chuyển lỗi duplicate thành lỗi nghiệp vụ:

~~~java
return repository.save(entity)
    .onErrorMap(DuplicateKeyException.class, error ->
        new EntityAlreadyExistsException(entity.id(), error)
    );
~~~

Ví dụ fallback khi dữ liệu không tồn tại:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.error(
        new EntityNotFoundException(id)
    ));
~~~

Không dùng onErrorResume để biến mọi lỗi database thành Mono.empty(). Cách đó khiến caller không phân biệt được “không có dữ liệu” với “database không hoạt động”.

### Không nuốt lỗi trước transaction boundary

Nếu một thao tác ghi lỗi nhưng code fallback bằng giá trị bình thường bên trong transaction, transaction manager có thể thấy publisher hoàn tất bình thường và commit. Chỉ phục hồi lỗi khi nghiệp vụ cho phép và trạng thái transaction còn hợp lệ.

Với constraint violation, một số database đánh dấu transaction cần rollback hoặc không thể tiếp tục trước khi rollback. Với savepoint, cần rollback đúng về savepoint trước khi xử lý lỗi và tiếp tục. Không giả định catch exception là đủ để transaction trở lại trạng thái bình thường.

## 12. Chẩn đoán theo cause chain và điểm phát sinh

Khi một API trả lỗi, hãy ghi nhận đủ thông tin để tìm lỗi gốc:

1. Operation name và correlation/request id.
2. Repository method hoặc tên use case.
3. Loại exception ngoài cùng.
4. Cause chain và root cause.
5. SQLSTATE và vendor error code nếu có.
6. Database vendor/version và R2DBC driver/version.
7. Thời điểm lỗi: lấy connection, execute, commit hay map result.
8. Transaction state và retry attempt.
9. Thời gian chờ connection và thời gian chạy query nếu có metric.

Tránh log:

- Password, access token hoặc connection URL có credential.
- Bind values chứa email, địa chỉ, số điện thoại hoặc dữ liệu cá nhân.
- Raw payload của request nếu không có chính sách bảo vệ.
- Toàn bộ SQL có literal nhạy cảm.
- Exception message trả thẳng cho client.

Có thể log tên statement, query fingerprint, tên constraint, SQLSTATE và vendor code. Khi cần bind value để điều tra, hãy dùng dữ liệu đã mask và chỉ bật trong môi trường có kiểm soát.

## 13. Phân biệt lỗi kết nối, SQL, mapping và constraint qua tình huống

| Tình huống quan sát | Nhóm nên kiểm tra trước | Câu hỏi chẩn đoán |
| --- | --- | --- |
| API timeout trước khi có SQL log | Pool/connectivity | Pool có connection trống không? DNS/TLS/server có ổn định? |
| SQL log xuất hiện rồi báo relation/table not found | SQL/schema | Tên schema/table và migration có đúng môi trường? |
| INSERT báo duplicate key | Constraint | Constraint nào bị vi phạm? Đây là request trùng hay bug? |
| INSERT thành công nhưng trả lỗi converter | Mapping | Row đã được ghi chưa? Kiểu/alias/converter nào thất bại? |
| SELECT trả lỗi enum conversion | Mapping/data drift | Database có giá trị enum mới chưa được code hỗ trợ? |
| UPDATE báo foreign key violation | Constraint | Bản ghi tham chiếu có tồn tại và có bị xóa đồng thời? |
| Deadlock hoặc serialization failure | Transaction/concurrency | Có thể retry toàn bộ transaction không? |
| Timeout sau khi gửi lệnh ghi | Kết quả không xác định | Kiểm tra operation ID trước khi retry. |
| Sai bind marker hoặc thiếu named parameter | Bind/query definition | SQL và danh sách tham số có khớp? |
| Connection reset khi đang stream Flux | Connection/lifecycle | Server/network/pool có đóng connection giữa stream? |

Một điểm quan trọng: nếu lỗi mapping xảy ra sau khi INSERT đã được database thực hiện, việc retry insert có thể tạo duplicate. Hãy xác định lỗi xảy ra trước hay sau khi statement đã có hiệu lực. Khi không chắc chắn, tra cứu bằng ID ổn định hoặc idempotency key.

## 14. Kiểm thử các nhóm lỗi

Unit test có thể kiểm tra cách service chuyển exception thành lỗi nghiệp vụ. Integration test trên database thật cần xác nhận phân loại lỗi, SQLSTATE, constraint và mapping theo driver thực tế.

Các trường hợp nên có:

| Test case | Kết quả cần xác nhận |
| --- | --- |
| Database không khả dụng | Lỗi kết nối được truyền ra và không bị biến thành kết quả rỗng. |
| Pool hết connection | Timeout được phân biệt với SQL timeout. |
| SQL sai tên cột | Nhận lỗi grammar/usage, không retry. |
| Thiếu bind parameter | Lỗi được phát hiện ở tầng bind/execute. |
| Sai kiểu dữ liệu | Lỗi bind hoặc database data exception được phân loại. |
| Projection thiếu cột | Mapping thất bại và được chẩn đoán ở tầng chuyển đổi. |
| Enum không nhận diện giá trị | Phát hiện schema/data drift. |
| Unique constraint | Chuyển thành conflict nghiệp vụ phù hợp. |
| Foreign key constraint | Không retry và không bỏ constraint. |
| Deadlock/serialization | Retry có giới hạn toàn transaction nếu được xác định an toàn. |
| Timeout sau write | Idempotency/operation ID ngăn tạo kết quả trùng. |

Ví dụ integration test unique constraint:

~~~java
@Test
void mapsDuplicateEmailToDomainConflict() {
    StepVerifier.create(customerService.register(commandWithExistingEmail()))
        .expectError(EmailAlreadyRegisteredException.class)
        .verify();
}
~~~

Test phải chuẩn bị dữ liệu trùng trong database test và gọi service qua bean Spring thật. Mock repository chỉ xác nhận nhánh xử lý exception; nó không chứng minh database/driver thực sự phát đúng exception.

Ví dụ test mapping cần query dữ liệu có giá trị không thể chuyển sang enum hoặc kiểu projection mong đợi. Xác nhận lỗi được quan sát ở tầng mapping, đồng thời kiểm tra xem thao tác ghi trước đó đã commit hay chưa nếu lỗi xảy ra sau một write.

## 15. Các lỗi xử lý thường gặp

| Cách xử lý sai | Rủi ro | Cách làm phù hợp |
| --- | --- | --- |
| Retry mọi exception | Lặp lại lỗi vĩnh viễn và tăng tải database. | Chỉ retry lỗi transient đã phân loại. |
| Retry từng statement trong transaction đã rollback | Các lệnh tiếp theo chạy trong transaction hỏng. | Retry toàn bộ transaction trong subscription mới. |
| Bắt DataIntegrityViolationException và trả thành công | Che giấu dữ liệu không hợp lệ. | Chuyển constraint cụ thể thành lỗi domain. |
| Parse message để tìm duplicate | Phụ thuộc ngôn ngữ/vendor/version. | Dùng exception type, SQLSTATE và vendor code. |
| Bỏ qua lỗi mapping | Có thể đã ghi dữ liệu nhưng response thất bại. | Kiểm tra trạng thái ghi, sửa converter/projection. |
| Dùng SELECT * cho projection | Mapping thay đổi khi schema đổi hoặc cột trùng. | Liệt kê cột và alias rõ. |
| Bind Java null bằng bind | Lỗi bind hoặc thiếu type. | Dùng bindNull với kiểu cụ thể. |
| Trả raw SQL error cho client | Rò rỉ schema, tên bảng và dữ liệu nội bộ. | Trả error code ổn định, log chi tiết có kiểm soát. |
| Bỏ constraint để hết lỗi | Làm mất bảo vệ toàn vẹn dữ liệu. | Sửa validation, mapping hoặc quy tắc nghiệp vụ. |
| Nuốt mọi lỗi bằng Mono.empty | Mất phân biệt giữa không có dữ liệu và sự cố. | Chỉ fallback cho lỗi đã xác định rõ. |

## 16. Quy trình phân loại và xử lý lỗi

Khi một publisher R2DBC phát lỗi, có thể làm theo trình tự:

1. **Xác định thời điểm:** lỗi xảy ra khi lấy connection, bind, execute, commit hay map row?
2. **Đọc exception type:** kiểm tra DataAccessException, R2dbcException và cause chain.
3. **Đọc metadata:** lấy SQLSTATE, vendor error code và constraint name nếu có.
4. **Phân nhóm:** connection/resource, SQL grammar, bind/type, mapping, integrity constraint hoặc transaction.
5. **Quyết định khả năng retry:** chỉ retry lỗi transient và thao tác có thể lặp an toàn.
6. **Chuyển lỗi sang domain/API:** dùng error code ổn định, không để lộ chi tiết database.
7. **Ghi log có kiểm soát:** operation id, statement fingerprint, driver, SQLSTATE và thời điểm phát sinh.
8. **Kiểm tra trạng thái ghi:** đặc biệt khi timeout hoặc mapping lỗi xảy ra sau write.
9. **Bổ sung integration test:** dùng đúng database và R2DBC driver đang triển khai.
10. **Theo dõi metric:** số lỗi theo nhóm, tỷ lệ retry, pool wait, query latency và constraint conflict.

Phân loại lỗi đúng giúp ứng dụng phản hồi có ý nghĩa và phục hồi an toàn. Lỗi kết nối có thể cần retry hoặc cảnh báo hạ tầng; lỗi SQL cần sửa câu lệnh; lỗi mapping cần đồng bộ entity/projection/converter với schema; lỗi constraint cần xử lý theo nghiệp vụ. Trong Spring Data Relational R2DBC, hãy kết hợp exception translation của Spring, metadata từ R2DBC driver, SQLSTATE và integration test trên database thật để quyết định cách xử lý thay vì dựa vào message hoặc retry chung cho mọi lỗi.
