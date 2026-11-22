# Đảm bảo toàn vẹn dữ liệu con khi xóa trực tiếp

Trong Spring Data JDBC, aggregate root quản lý vòng đời của các entity con. Khi ứng dụng xóa một hàng con bằng SQL trực tiếp, chẳng hạn qua `@Modifying` hoặc `JdbcTemplate`, thao tác đi thẳng xuống database và có thể bỏ qua hành vi domain của aggregate root.

Xóa trực tiếp có thể cần thiết khi xử lý dữ liệu lớn, thực hiện thao tác hàng loạt hoặc tránh tải toàn bộ aggregate chỉ để xóa một bản ghi. Nhưng để dữ liệu vẫn nhất quán, cần bảo vệ đồng thời nhiều lớp:

- **Toàn vẹn tham chiếu:** không để bản ghi con mồ côi hoặc vi phạm khóa ngoại.
- **Quy tắc nghiệp vụ:** chỉ xóa khi trạng thái aggregate và điều kiện nghiệp vụ cho phép.
- **Đồng thời:** không xóa dựa trên version cũ khi transaction khác đang sửa aggregate.
- **Vòng đời ứng dụng:** xử lý audit, event, cache và dữ liệu phụ thuộc.
- **Tính nguyên tử:** các bước kiểm tra, cập nhật version và xóa phải commit hoặc rollback cùng nhau.

Bài học dùng ví dụ đơn hàng có các dòng hàng để trình bày cách xóa trực tiếp an toàn trong Spring Data JDBC, khi nào nên dùng cascade, cách phối hợp transaction và optimistic locking, cùng những trường hợp nên giữ thao tác qua aggregate root.

## 1. Dữ liệu con và các loại toàn vẹn

Giả sử một đơn hàng sở hữu nhiều dòng hàng:

~~~text
SalesOrder (aggregate root)
    |
    +-- OrderLine #1
    +-- OrderLine #2
    +-- OrderLine #3
~~~

Mỗi dòng hàng nằm trong bảng riêng:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,

    PRIMARY KEY (order_id, line_no),

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_orders(id),

    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_order_line_price
        CHECK (unit_price >= 0)
);
~~~

Khóa ngoại `order_lines.order_id` bảo đảm mỗi dòng hàng tham chiếu đến một đơn tồn tại. Khóa chính ghép `(order_id, line_no)` phân biệt các dòng trong cùng đơn.

Tuy nhiên, khóa ngoại chỉ bảo vệ quan hệ lưu trữ. Nó không thể tự quyết định một đơn đã xác nhận có được xóa dòng hàng hay không, đơn có được phép không còn dòng nào hay không, hoặc ai có quyền xóa dòng.

Cần phân biệt các lớp toàn vẹn:

| Lớp | Ví dụ | Cơ chế bảo vệ |
|---|---|---|
| Referential integrity | Dòng hàng phải thuộc một đơn tồn tại | Primary key, foreign key |
| Data validity | Số lượng phải lớn hơn 0 | CHECK, NOT NULL, kiểu cột |
| Domain invariant | Chỉ đơn nháp mới được xóa dòng | Aggregate behavior, application service, điều kiện SQL |
| Concurrency integrity | Không xóa dựa trên version cũ | `@Version`, version predicate, transaction |
| Audit/side effects | Ghi nhận ai đã xóa dòng | Audit table, outbox, callback hoặc trigger |
| Transactional integrity | Không tăng version nhưng bỏ dở thao tác xóa | `@Transactional`, rollback |

Một lệnh DELETE thành công về mặt SQL chưa chắc đã hợp lệ về mặt nghiệp vụ. Thiết kế an toàn phải xác định rõ các lớp nào cần được bảo vệ.

## 2. Xóa trực tiếp khác gì xóa qua aggregate root?

Cách thao tác thông thường với Spring Data JDBC là tải root, gọi hành vi domain rồi lưu aggregate:

~~~java
@Transactional
public void removeLine(Long orderId, Integer lineNo) {
    SalesOrder order = repository.findById(orderId)
            .orElseThrow(() ->
                    new IllegalArgumentException("Order not found"));

    order.removeLine(lineNo);
    repository.save(order);
}
~~~

Cách này cho phép root kiểm tra các invariant như:

- Đơn phải ở trạng thái `DRAFT`.
- Dòng hàng phải tồn tại.
- Đơn phải còn ít nhất một dòng.
- Dòng đã xuất hóa đơn không được xóa.

Spring Data JDBC lưu trạng thái aggregate theo cơ chế persistence của nó. Với aggregate đã tồn tại, việc lưu collection có thể dẫn đến xóa và chèn lại các entity được tham chiếu để phản ánh trạng thái hiện tại.

Khi xóa trực tiếp:

~~~sql
DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

Database chỉ thực hiện điều kiện SQL và các constraint. Nó không tự gọi phương thức `order.removeLine(...)` trong Java.

| Khía cạnh | Xóa qua aggregate root | Xóa trực tiếp |
|---|---|---|
| Kiểm tra invariant trong domain | Có thể đặt trong root | Phải thực hiện riêng |
| Tải toàn bộ aggregate | Thường có | Có thể không cần |
| SQL được kiểm soát | Spring Data JDBC | Ứng dụng viết trực tiếp |
| `@Version` của root | Được Spring Data JDBC áp dụng khi lưu | Phải phối hợp thủ công |
| Entity callbacks/events | Theo lifecycle của repository | Không tự chạy cho hàng bị SQL trực tiếp xóa |
| Audit và side effect | Có thể xử lý trong domain/service/callback | Phải tổ chức riêng |
| Xóa nhiều bản ghi | Có thể tốn chi phí materialize aggregate | SQL hàng loạt thường hiệu quả hơn |

Xóa trực tiếp là một đường ghi riêng. Hãy xem nó như một use case persistence cần tái hiện những bảo vệ cần thiết của aggregate, không phải một cách viết SQL ngắn hơn cho cùng hành vi domain.

## 3. Khóa ngoại bảo vệ bản ghi con như thế nào?

Foreign key là hàng rào đầu tiên để tránh dữ liệu mồ côi. Khi xóa một dòng hàng, database kiểm tra xem có bảng khác đang tham chiếu đến dòng đó hay không.

Ví dụ bảng chi tiết điều chỉnh giá tham chiếu dòng hàng bằng khóa ghép:

~~~sql
CREATE TABLE order_line_adjustments (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    adjustment_no INTEGER NOT NULL,
    reason VARCHAR(200) NOT NULL,

    PRIMARY KEY (order_id, line_no, adjustment_no),

    CONSTRAINT fk_adjustment_line
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_lines(order_id, line_no)
);
~~~

Nếu có adjustment tham chiếu đến dòng hàng, câu DELETE dòng hàng có thể bị database từ chối. Đây là hành vi mong muốn nếu adjustment phải được giữ lại.

### 3.1. Chọn hành vi ON DELETE phù hợp

Foreign key có thể định nghĩa nhiều chính sách:

| Chính sách | Hành vi khi xóa bản ghi được tham chiếu | Khi phù hợp |
|---|---|---|
| `RESTRICT` | Từ chối xóa khi còn bản ghi con | Dữ liệu phụ thuộc cần được giữ |
| `NO ACTION` | Kiểm tra ràng buộc theo semantics của database | Muốn database chặn tham chiếu không hợp lệ |
| `CASCADE` | Tự xóa các bản ghi tham chiếu | Bản ghi con phụ thuộc hoàn toàn vào cha |
| `SET NULL` | Đặt FK ở hàng con thành NULL | Quan hệ tùy chọn và cột FK cho phép NULL |

Ví dụ cascade từ dòng hàng đến các adjustment:

~~~sql
ALTER TABLE order_line_adjustments
    DROP CONSTRAINT fk_adjustment_line;

ALTER TABLE order_line_adjustments
    ADD CONSTRAINT fk_adjustment_line
    FOREIGN KEY (order_id, line_no)
    REFERENCES order_lines(order_id, line_no)
    ON DELETE CASCADE;
~~~

Khi xóa một dòng hàng, database tự xóa các adjustment thuộc dòng đó.

Cần hiểu hướng của cascade: constraint nằm ở bảng tham chiếu. `ON DELETE CASCADE` trên FK của `order_line_adjustments` được kích hoạt khi một hàng `order_lines` bị xóa. Cascade từ `sales_orders` sang `order_lines` chỉ chạy khi một đơn hàng bị xóa; nó không chạy khi ứng dụng chỉ xóa một dòng hàng.

### 3.2. Không dùng CASCADE để che giấu ownership sai

Nếu một bản ghi được nhiều aggregate độc lập tham chiếu, xóa cascade có thể làm mất dữ liệu ngoài phạm vi aggregate đang xóa.

Ví dụ một `Product` được nhiều đơn hàng tham chiếu. Không nên cấu hình xóa đơn hàng làm xóa sản phẩm. Quan hệ đó thường cần FK `RESTRICT`/`NO ACTION` và tham chiếu ID giữa các aggregate.

Chỉ dùng cascade khi vòng đời bản ghi con thực sự phụ thuộc vào bản ghi cha và việc xóa cùng nhau phù hợp với nghiệp vụ.

### 3.3. SET NULL có thể tạo dữ liệu không còn ý nghĩa

Với entity con được sở hữu, việc đặt FK thành NULL thường làm mất ý nghĩa "thuộc về aggregate nào". Nếu một dòng hàng bắt buộc thuộc về đơn hàng, cột FK phải `NOT NULL` và không nên dùng `ON DELETE SET NULL`.

`SET NULL` phù hợp hơn với tham chiếu tùy chọn, chẳng hạn một bản ghi có thể tồn tại sau khi liên kết đến người phụ trách bị gỡ bỏ.

## 4. Xóa trực tiếp một dòng hàng bằng @Modifying

Spring Data JDBC hỗ trợ câu SQL ghi trực tiếp bằng `@Modifying` kết hợp `@Query`.

Repository:

~~~java
package com.example.shop.order.repository;

import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {

    @Modifying
    @Query("""
        DELETE FROM order_lines
        WHERE order_id = :orderId
          AND line_no = :lineNo
        """)
    int deleteLine(
            @Param("orderId") Long orderId,
            @Param("lineNo") Integer lineNo
    );
}
~~~

`@Modifying` đánh dấu câu query là câu lệnh thay đổi dữ liệu thay vì truy vấn trả về entity. Phương thức trả về `int` để nhận số hàng bị ảnh hưởng.

Ví dụ:

~~~java
int deleted = repository.deleteLine(100L, 2);

if (deleted == 0) {
    throw new IllegalArgumentException("Order line not found");
}
~~~

Số hàng bị xóa là tín hiệu quan trọng:

- `1`: đúng một dòng được xóa.
- `0`: không có dòng nào thỏa điều kiện; có thể không tồn tại hoặc không thuộc đơn được chỉ định.
- Lớn hơn `1`: cần xem lại điều kiện WHERE và tính duy nhất của khóa.

Nếu dùng khóa ghép `(order_id, line_no)`, số hàng xóa hợp lệ cho một dòng thường là 0 hoặc 1.

**Không bỏ điều kiện root ID.** Xóa theo `line_no` đơn lẻ có thể tác động đến dòng của đơn khác nếu `line_no` chỉ duy nhất trong phạm vi một đơn.

## 5. Kiểm tra trạng thái nghiệp vụ ngay trong câu DELETE

Nếu chỉ đơn `DRAFT` mới được phép xóa dòng, có thể đưa điều kiện trạng thái vào câu SQL:

~~~java
@Modifying
@Query("""
    DELETE FROM order_lines
    WHERE order_id = :orderId
      AND line_no = :lineNo
      AND EXISTS (
          SELECT 1
          FROM sales_orders o
          WHERE o.id = order_lines.order_id
            AND o.status = 'DRAFT'
      )
    """)
int deleteDraftLine(
        @Param("orderId") Long orderId,
        @Param("lineNo") Integer lineNo
);
~~~

Điều kiện này khiến database chỉ xóa dòng khi đơn vẫn ở trạng thái `DRAFT` tại thời điểm statement được thực thi.

Tuy nhiên, chỉ thêm `EXISTS` chưa giải quyết toàn bộ vấn đề đồng thời. Một transaction khác có thể đang thay đổi trạng thái hoặc version của root. Nếu hệ thống cần bảo vệ chặt chẽ giữa thao tác xóa và thao tác xác nhận đơn, hãy phối hợp optimistic locking hoặc khóa dòng root trong cùng transaction.

Điều kiện SQL phải bao gồm mọi ràng buộc nghiệp vụ quan trọng mà thao tác trực tiếp cần bảo vệ. Ví dụ nếu không được xóa dòng đã xuất hóa đơn, cần kiểm tra trạng thái invoice hoặc quan hệ liên quan trong cùng câu lệnh hay trong một transaction có kiểm soát.

## 6. Transaction bao trùm kiểm tra và xóa

Một thao tác xóa trực tiếp có thể gồm nhiều bước:

1. Kiểm tra quyền hoặc trạng thái.
2. Cập nhật version của root để đồng bộ concurrency.
3. Xóa bản ghi con.
4. Ghi audit/outbox nếu cần.
5. Commit.

Các bước này phải nằm trong cùng transaction nếu chúng tạo thành một thay đổi nghiệp vụ nguyên tử.

Ví dụ service:

~~~java
@Service
public class OrderLineCommandService {

    private final SalesOrderRepository repository;

    public OrderLineCommandService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deleteLine(Long orderId, Integer lineNo) {
        int deleted = repository.deleteDraftLine(orderId, lineNo);

        if (deleted != 1) {
            throw new IllegalStateException(
                    "Line does not exist or order cannot be changed"
            );
        }
    }
}
~~~

Nếu câu DELETE thất bại hoặc số hàng bị xóa không đúng, ném runtime exception sẽ làm transaction rollback theo cấu hình mặc định của Spring.

Nếu cần xử lý checked exception và vẫn muốn rollback, hãy khai báo chính sách `rollbackFor` phù hợp.

Không nên tách bước kiểm tra trạng thái trong một transaction rồi xóa ở một transaction khác. Trạng thái có thể đổi giữa hai thời điểm, tạo ra race condition.

### 6.1. Cùng transaction manager và cùng datasource

`@Transactional` chỉ bảo vệ các thao tác tham gia cùng transaction manager. Nếu thao tác xóa chạy qua `JdbcTemplate` và repository dùng cùng `DataSource`/transaction manager, chúng có thể tham gia cùng transaction Spring.

Nếu audit ghi sang một database hoặc dịch vụ ngoài, transaction JDBC không tự bảo đảm tính nguyên tử xuyên hệ thống. Khi đó cần outbox hoặc một cơ chế phối hợp phù hợp.

## 7. Optimistic locking khi xóa trực tiếp

Spring Data JDBC dùng `@Version` trên aggregate root để phát hiện cập nhật dựa trên trạng thái cũ.

Ví dụ root:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

Khi repository lưu aggregate, Spring Data JDBC kiểm tra version và cập nhật version theo cơ chế optimistic locking.

Nhưng một câu `@Modifying DELETE` trực tiếp bảng `order_lines` không tự động thực hiện bước kiểm tra version của `sales_orders`. Nếu không phối hợp, transaction A có thể xóa dòng trong khi transaction B đã đọc aggregate ở version cũ và vẫn đang thay đổi đơn.

### 7.1. Ví dụ race condition

~~~text
Transaction A                       Transaction B
-------------                       -------------
Read order #100, version 4          Read order #100, version 4
                                    Change order status
                                    Save root -> version 5
Delete order_lines row
Commit
                                    ...
~~~

Nếu transaction A không kiểm tra version, nó có thể xóa dòng dựa trên trạng thái cũ dù đơn đã chuyển sang trạng thái không cho phép thay đổi.

### 7.2. Cập nhật version có điều kiện trước khi xóa

Một cách là dùng câu UPDATE nguyên tử để kiểm tra root, tăng version và giành quyền thay đổi aggregate:

~~~java
@Modifying
@Query("""
    UPDATE sales_orders
    SET version = version + 1
    WHERE id = :orderId
      AND version = :expectedVersion
      AND status = 'DRAFT'
    """)
int advanceVersionForDirectMutation(
        @Param("orderId") Long orderId,
        @Param("expectedVersion") Long expectedVersion
);
~~~

Sau đó xóa dòng:

~~~java
@Modifying
@Query("""
    DELETE FROM order_lines
    WHERE order_id = :orderId
      AND line_no = :lineNo
    """)
int deleteLine(
        @Param("orderId") Long orderId,
        @Param("lineNo") Integer lineNo
);
~~~

Service phối hợp:

~~~java
@Service
public class OrderLineCommandService {

    private final SalesOrderRepository repository;

    public OrderLineCommandService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deleteLine(
            Long orderId,
            Integer lineNo,
            Long expectedVersion
    ) {
        int claimed = repository.advanceVersionForDirectMutation(
                orderId,
                expectedVersion
        );

        if (claimed != 1) {
            throw new OptimisticLockingFailureException(
                    "Order changed, does not exist, or is not editable"
            );
        }

        int deleted = repository.deleteLine(orderId, lineNo);

        if (deleted != 1) {
            throw new IllegalArgumentException(
                    "Order line not found"
            );
        }
    }
}
~~~

Luồng này có ý nghĩa:

1. UPDATE chỉ thành công nếu ID tồn tại, version vẫn đúng và status còn là `DRAFT`.
2. Việc cập nhật hàng root lấy khóa ghi trên hàng đó theo cơ chế database, giúp các transaction cạnh tranh cùng root phải tuần tự hóa tại điểm cập nhật.
3. Nếu version không khớp hoặc status không hợp lệ, không xóa dòng.
4. Nếu dòng không tồn tại, exception làm rollback cả bước tăng version.
5. Khi commit, root version đã tăng để những object aggregate được tải ở version cũ không thể lưu thành công như thể chưa có thay đổi.

Cách này yêu cầu mọi đường ghi khác cũng tôn trọng version. Nếu có một câu SQL khác thay đổi status hoặc collection mà không tăng version, optimistic locking không thể phát hiện đầy đủ thay đổi đó.

### 7.3. Không dùng object đã tải trước khi direct delete như trạng thái mới nhất

Sau khi direct SQL thay đổi child và tăng version, object `SalesOrder` đã tải trước đó vẫn chứa collection cũ và version cũ. Không tiếp tục sửa object đó rồi gọi `repository.save(order)`.

Hãy bỏ object cũ và tải lại aggregate trong transaction/use case tiếp theo. Nếu ứng dụng có cache aggregate, cần invalidation hoặc cập nhật cache tương ứng.

## 8. Khóa pessimistic và thứ tự khóa

Một lựa chọn khác là khóa root trước khi xóa child. Ví dụ PostgreSQL:

~~~sql
SELECT id, version, status
FROM sales_orders
WHERE id = :orderId
FOR UPDATE;
~~~

`FOR UPDATE` giữ khóa trên hàng root đến khi transaction kết thúc. Transaction khác muốn sửa cùng hàng sẽ phải chờ hoặc bị ảnh hưởng theo isolation/timeout của database.

Cách này hữu ích khi thao tác cần đọc nhiều điều kiện nghiệp vụ rồi mới quyết định xóa. Tuy nhiên:

- Cú pháp khóa phụ thuộc database.
- Transaction phải ngắn để không giữ khóa quá lâu.
- Cần xử lý timeout và deadlock.
- Các đường ghi khác phải dùng chiến lược khóa tương thích.
- Không nên khóa hàng root rồi gọi dịch vụ ngoài hoặc chờ người dùng.

Dù chọn optimistic hay pessimistic locking, nên thống nhất thứ tự khóa. Ví dụ mọi thao tác sửa aggregate đều khóa/kiểm tra root trước rồi mới thay đổi child. Thứ tự nhất quán giúp giảm nguy cơ deadlock do hai transaction khóa bảng theo thứ tự ngược nhau.

## 9. Xóa một child có child riêng

Giả sử một dòng hàng có nhiều ghi chú điều chỉnh:

~~~text
SalesOrder
    |
    +-- OrderLine
            |
            +-- OrderLineAdjustment
            +-- OrderLineAdjustment
~~~

Nếu muốn xóa `OrderLine`, cần xử lý các adjustment theo chính sách đã chọn.

### 9.1. Database cascade

Nếu adjustment không có ý nghĩa tồn tại độc lập, có thể khai báo FK `ON DELETE CASCADE`.

Một câu DELETE trên `order_lines` sẽ xóa các adjustment tham chiếu đến dòng đó.

Ưu điểm:

- Database tự bảo đảm không còn adjustment mồ côi.
- Không cần viết nhiều câu DELETE thủ công.
- Hành vi áp dụng cho mọi đường xóa SQL, không phụ thuộc code gọi.

Nhưng cascade chỉ thực hiện hành động database. Nó không gọi Java callback cho từng adjustment, không tự ghi application event và không chạy domain method của aggregate.

### 9.2. Xóa thủ công theo thứ tự phụ thuộc

Nếu cần kiểm soát audit hoặc không muốn cascade, có thể xóa theo thứ tự con trước cha:

~~~sql
DELETE FROM order_line_adjustments
WHERE order_id = :orderId
  AND line_no = :lineNo;

DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

Hai câu lệnh phải nằm trong cùng transaction. Nếu câu thứ hai thất bại, câu đầu phải rollback.

Với cây nhiều tầng, xóa từ lá đi lên:

~~~text
DELETE grandchildren
        |
        v
DELETE children
        |
        v
DELETE parent row
~~~

Không xóa parent trước khi các FK tham chiếu được xử lý, trừ khi database cascade đã được thiết kế và kiểm thử đúng.

## 10. Xóa trực tiếp cả một nhóm dữ liệu con

Một số use case cần xóa nhiều dòng cùng lúc, ví dụ hủy toàn bộ các dòng tạm của một đơn nháp.

SQL:

~~~sql
DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no IN (:lineNumbers);
~~~

Có thể dùng `NamedParameterJdbcTemplate` để bind collection:

~~~java
@Repository
public class OrderLineSqlRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderLineSqlRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int deleteLines(Long orderId, Collection<Integer> lineNumbers) {
        if (lineNumbers.isEmpty()) {
            return 0;
        }

        String sql = """
            DELETE FROM order_lines
            WHERE order_id = :orderId
              AND line_no IN (:lineNumbers)
            """;

        return jdbc.update(
                sql,
                new MapSqlParameterSource()
                        .addValue("orderId", orderId)
                        .addValue("lineNumbers", lineNumbers)
        );
    }
}
~~~

Cần xử lý collection rỗng trước khi tạo câu SQL. Không nên dựa vào cách driver/database diễn giải một danh sách rỗng trong mệnh đề IN.

Khi xóa hàng loạt:

- Kiểm tra tổng số hàng bị ảnh hưởng.
- Xác định thao tác có được phép xóa một phần hay phải xóa toàn bộ.
- Cập nhật version root một lần theo chính sách.
- Ghi audit cho từng dòng hoặc cho command tổng hợp, tùy yêu cầu.
- Đảm bảo FK cascade/restrict cho các bảng phụ thuộc.
- Dùng transaction để rollback nếu một bước quan trọng thất bại.

Nếu cần phân biệt chính xác từng dòng bị xóa, có thể truy vấn trước các ID cần xóa trong cùng transaction hoặc dùng cú pháp `RETURNING` trên database hỗ trợ. Đừng giả định mọi database đều có cú pháp đó.

## 11. Xóa vật lý hay soft delete?

Không phải lúc nào xóa vật lý cũng phù hợp.

### 11.1. Xóa vật lý

~~~sql
DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

Hàng bị loại khỏi bảng. Phù hợp khi:

- Dữ liệu chỉ có ý nghĩa tạm thời.
- Không cần lưu lịch sử.
- Không có nghĩa vụ kiểm toán hoặc khôi phục.
- Các tham chiếu phụ thuộc được xử lý rõ ràng.

### 11.2. Soft delete

~~~sql
ALTER TABLE order_lines
    ADD COLUMN deleted_at TIMESTAMP NULL,
    ADD COLUMN deleted_by VARCHAR(100) NULL;
~~~

Thay vì xóa hàng:

~~~sql
UPDATE order_lines
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = :actor
WHERE order_id = :orderId
  AND line_no = :lineNo
  AND deleted_at IS NULL;
~~~

Soft delete giữ lại dữ liệu để audit hoặc khôi phục. Nhưng nó tạo ra trách nhiệm bổ sung:

- Mọi query đọc phải lọc bản ghi đã xóa khi phù hợp.
- Unique constraint có thể cần điều chỉnh để cho phép tạo lại bản ghi tương đương.
- Báo cáo phải phân biệt dữ liệu active và deleted.
- FK vẫn tồn tại vì hàng vật lý chưa bị xóa.
- Aggregate mapping mặc định có thể vẫn đọc hàng soft-deleted nếu query loading không có bộ lọc phù hợp.

Đừng xem soft delete là giải pháp miễn phí. Nó thay đổi semantics của dữ liệu và cần một quy ước đọc/ghi nhất quán.

## 12. Direct DELETE bỏ qua những hành vi nào của Spring Data JDBC?

Một modifying query thực hiện SQL trực tiếp, không đi qua quá trình save/delete aggregate tiêu chuẩn. Do đó, các hành vi sau không tự xảy ra cho từng hàng bị xóa:

### 12.1. Domain behavior và invariant

Không có lời gọi tự động đến `order.removeLine(lineNo)`. Các điều kiện như trạng thái đơn, số dòng tối thiểu, hóa đơn đã phát hành hoặc giới hạn quyền phải được kiểm tra ở application service hoặc thể hiện an toàn trong SQL/transaction.

### 12.2. Entity callbacks và lifecycle events

SQL trực tiếp không materialize entity bị xóa để gọi callback tương ứng. Các lifecycle events/callback của Spring Data JDBC không tự chạy cho từng hàng bị xóa bằng `@Modifying` hoặc `JdbcTemplate`.

Nếu cần audit hoặc event, hãy tạo chúng rõ ràng trong use case hoặc dùng cơ chế database-level phù hợp.

### 12.3. Optimistic locking

Một DELETE child trực tiếp không tự kiểm tra `@Version` của root. Cần thêm version predicate hoặc khóa root trong cùng transaction.

### 12.4. Auditing

Các trường như `lastModifiedAt`, `lastModifiedBy` của root không tự được cập nhật chỉ vì một hàng con bị xóa trực tiếp.

Nếu việc xóa child được xem là thay đổi aggregate, hãy cập nhật root audit/version theo quy tắc nghiệp vụ.

### 12.5. Cache và read model

Nếu ứng dụng cache aggregate, số lượng dòng hoặc tổng tiền, direct delete có thể làm cache và dữ liệu đọc bị cũ. Cần invalidate/update cache sau commit hoặc phát event qua outbox.

### 12.6. Domain event và thông báo ngoài hệ thống

Nếu xóa dòng làm phát sinh nghiệp vụ như hủy reservation hoặc cập nhật tồn kho, câu DELETE không tự phát event. Hãy ghi outbox record trong cùng transaction để worker gửi thông báo sau commit.

## 13. Audit và outbox cho thao tác xóa

Một audit record có thể lưu ai đã xóa dòng, lúc nào và lý do:

~~~sql
CREATE TABLE order_line_audit (
    audit_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(300),
    occurred_at TIMESTAMP NOT NULL
);
~~~

Trong transaction:

1. Kiểm tra root/version.
2. Ghi audit record.
3. Xóa child.
4. Commit.

Nếu audit là yêu cầu bắt buộc, không để việc ghi audit chạy sau commit theo kiểu best-effort mà không có cơ chế retry. Nếu xóa thành công nhưng audit thất bại, hệ thống sẽ mất dấu thao tác.

Với event cần gửi ra message broker, dùng transactional outbox:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Ứng dụng ghi outbox cùng transaction xóa child. Một publisher riêng đọc outbox và gửi event; nếu gửi thất bại, có thể retry mà không làm mất event nghiệp vụ.

Không gọi message broker trực tiếp ở giữa transaction rồi giả định việc gửi và DELETE luôn cùng commit. Database transaction không tự bao trùm một broker thông thường.

## 14. Quyền truy cập và tenant boundary

Một câu DELETE phải ràng buộc đúng aggregate và đúng phạm vi người dùng. Trong hệ thống multi-tenant, chỉ có `order_id` có thể chưa đủ nếu ID không được bảo vệ theo tenant context.

Ví dụ:

~~~sql
DELETE FROM order_lines l
WHERE l.order_id = :orderId
  AND l.line_no = :lineNo
  AND EXISTS (
      SELECT 1
      FROM sales_orders o
      WHERE o.id = l.order_id
        AND o.tenant_id = :tenantId
        AND o.status = 'DRAFT'
  );
~~~

Điều kiện tenant giúp database chỉ xóa dòng thuộc đơn trong tenant được chỉ định.

Tuy nhiên, không nên coi một tham số `tenantId` do client gửi là bằng chứng quyền truy cập. Lấy tenant từ security context đã được xác thực và kiểm tra authorization ở application layer. SQL predicate là lớp bảo vệ bổ sung để tránh thao tác sai phạm vi.

Cũng cần cân nhắc không tiết lộ cho client liệu một dòng không tồn tại hay thuộc tenant khác nếu chính sách bảo mật yêu cầu che giấu sự khác biệt.

## 15. Kiểm thử toàn vẹn khi xóa trực tiếp

Unit test cho service có thể kiểm tra nhánh xử lý số hàng bị ảnh hưởng, nhưng các ràng buộc FK và hành vi cascade cần được kiểm thử với database thực tế hoặc database tương thích.

Các tình huống quan trọng:

| Tình huống | Kết quả mong đợi |
|---|---|
| Xóa một child tồn tại | Đúng một hàng bị xóa |
| Xóa child không tồn tại | Không có hàng bị xóa; service trả lỗi phù hợp |
| Xóa child không thuộc root chỉ định | Không ảnh hưởng đơn khác |
| Xóa child khi root đã xác nhận | Bị từ chối |
| Child còn bản ghi tham chiếu với FK RESTRICT | Database từ chối, transaction rollback |
| Child có descendants với FK CASCADE | Descendants bị xóa theo chính sách |
| Version không khớp | Không xóa child |
| Xóa child thất bại sau khi tăng version | Transaction rollback cả version |
| Audit/outbox insert thất bại | Toàn bộ thao tác rollback nếu cùng transaction |
| Hai transaction cùng sửa root | Một transaction phải phát hiện conflict hoặc chờ theo chiến lược khóa |

### 15.1. Kiểm tra rollback

Ví dụ một use case tăng version rồi xóa dòng. Hãy cố tình dùng `lineNo` không tồn tại để câu DELETE trả về 0 và service ném exception.

Sau khi transaction rollback, kiểm tra:

- Version root vẫn giữ giá trị trước thao tác.
- Các child khác vẫn tồn tại.
- Không có audit/outbox record chưa hoàn chỉnh.
- Không có descendant bị xóa ngoài dự kiến.

Đây là cách kiểm tra tính nguyên tử của cả chuỗi thao tác, không chỉ kiểm tra câu DELETE riêng lẻ.

### 15.2. Kiểm tra concurrency

Dùng hai transaction độc lập:

~~~text
A: đọc order #100, version 7
B: đọc order #100, version 7

A: advance version where version = 7 -> thành công, version 8
B: save hoặc advance version where version = 7 -> conflict
A: delete child -> commit
~~~

Test cần xác nhận transaction B không thể ghi dựa trên version cũ sau khi A đã thay đổi aggregate.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Xóa child chỉ theo `line_no` | Có thể xóa dòng của đơn khác | Luôn ràng buộc cả root ID và child key |
| Nghĩ FK bảo vệ mọi invariant | Đơn đã xác nhận vẫn có thể bị sửa | Kiểm tra domain state và điều kiện nghiệp vụ |
| Dùng `ON DELETE CASCADE` cho mọi quan hệ | Xóa lan sang dữ liệu ngoài ownership | Chỉ cascade theo vòng đời thực sự phụ thuộc |
| Xóa child nhưng bỏ qua descendants | DELETE bị FK từ chối hoặc dữ liệu phụ thuộc còn lại | Cascade đúng hướng hoặc xóa từ lá lên |
| Kiểm tra trạng thái rồi xóa ở transaction khác | Race condition khi trạng thái đổi giữa hai bước | Cùng transaction và kiểm soát version/lock |
| Direct DELETE không tăng version root | Transaction khác có thể lưu aggregate cũ | Cập nhật version có điều kiện hoặc khóa root |
| Tiếp tục dùng aggregate đã load trước direct DELETE | Object graph và version bị stale | Tải lại aggregate, invalidate cache |
| Mong `@Modifying` gọi callbacks | Audit/event không được ghi | Ghi audit/outbox rõ ràng |
| Chỉ kiểm tra câu DELETE trả 1 | Bỏ sót FK, cascade, rollback và concurrency | Integration test với database |
| Soft delete nhưng query không lọc | Dữ liệu đã xóa vẫn xuất hiện | Chuẩn hóa điều kiện đọc và unique constraint |

## 17. Quy trình thiết kế một thao tác xóa trực tiếp an toàn

Khi cần xóa dữ liệu con bằng SQL, hãy đi theo trình tự:

**Bước 1 — Xác định phạm vi xóa.** Child thuộc root nào? Khóa nhận diện đầy đủ gồm những cột nào?

**Bước 2 — Liệt kê các tham chiếu.** Bảng nào tham chiếu child? Có descendants hoặc aggregate khác đang tham chiếu không?

**Bước 3 — Chọn chính sách FK.** Dùng `CASCADE`, `RESTRICT`/`NO ACTION` hoặc `SET NULL` theo vòng đời dữ liệu.

**Bước 4 — Xác định invariant.** Trạng thái nào cho phép xóa? Có giới hạn số child tối thiểu? Có invoice, reservation hoặc quy trình bên ngoài không?

**Bước 5 — Chọn concurrency strategy.** Cập nhật version có điều kiện hoặc khóa root; bảo đảm mọi đường ghi khác tuân theo quy tắc.

**Bước 6 — Viết SQL có phạm vi chặt.** Bao gồm root ID, child key, tenant và điều kiện nghiệp vụ cần thiết.

**Bước 7 — Mở transaction.** Gộp kiểm tra/claim version, audit/outbox và DELETE vào cùng transaction.

**Bước 8 — Kiểm tra số hàng bị ảnh hưởng.** Phân biệt không tồn tại, conflict và trạng thái không cho phép theo chính sách API.

**Bước 9 — Đồng bộ side effects.** Invalidate cache, cập nhật read model hoặc phát outbox event sau commit.

**Bước 10 — Kiểm thử database.** Kiểm tra FK, cascade/restrict, rollback, version conflict và trường hợp xóa nhiều bản ghi.

~~~text
Yêu cầu xóa child
       |
       v
Xác định root + child key + tenant
       |
       v
Kiểm tra FK và descendants
       |
       v
Kiểm tra invariant nghiệp vụ
       |
       v
Claim root version / lock root
       |
       v
Ghi audit hoặc outbox nếu cần
       |
       v
DELETE child (và descendants theo FK)
       |
       v
Kiểm tra affected row count
       |
       v
Commit transaction
       |
       v
Invalidate cache / xử lý event sau commit
~~~

## 18. Bài tập tự suy luận

**Tình huống A — Xóa một dòng hàng**

Một đơn có `order_id = 100`, dòng hàng có `line_no = 2`. Vì sao câu DELETE chỉ dùng `line_no = 2` không an toàn?

**Gợi ý:** `line_no` chỉ duy nhất trong phạm vi một đơn. Phải dùng cả `order_id` và `line_no`.

**Tình huống B — Adjustment tham chiếu dòng hàng**

Một `OrderLine` có ba adjustment. Khi xóa dòng hàng, database cần làm gì?

**Gợi ý:** Nếu adjustment thuộc vòng đời dòng hàng, có thể dùng FK `ON DELETE CASCADE`. Nếu phải giữ lịch sử, dùng RESTRICT và xử lý archive/audit trước.

**Tình huống C — Đơn đã xác nhận**

SQL DELETE có FK hợp lệ nhưng đơn đã ở trạng thái `CONFIRMED`. Có nên cho phép xóa không?

**Gợi ý:** FK chỉ bảo vệ tham chiếu. Cần kiểm tra invariant nghiệp vụ; có thể chặn bằng điều kiện status trong SQL và concurrency control.

**Tình huống D — Version không khớp**

Ứng dụng đã tải đơn ở version 4, nhưng database hiện là version 5. Câu DELETE child có tự phát hiện xung đột không?

**Gợi ý:** Không. Direct DELETE phải kiểm tra hoặc claim version root trong cùng transaction.

**Tình huống E — Audit sau khi xóa**

Ứng dụng xóa child thành công rồi gọi HTTP service để ghi audit. HTTP service lỗi. Điều gì xảy ra?

**Gợi ý:** DELETE đã commit có thể không còn audit. Nếu audit là bắt buộc, ghi audit/outbox trong cùng transaction database.

**Tình huống F — Cache aggregate**

Một object aggregate đang được cache có ba dòng hàng. SQL trực tiếp xóa một dòng. Cache có tự cập nhật không?

**Gợi ý:** Không. Cần invalidate hoặc cập nhật cache sau commit và không tiếp tục dùng object graph cũ.

## 19. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| Foreign key | Ngăn bản ghi con tham chiếu đến cha không tồn tại |
| `ON DELETE CASCADE` | Xóa descendants tham chiếu khi parent bị xóa |
| `RESTRICT` / `NO ACTION` | Chặn xóa khi còn dữ liệu phụ thuộc |
| `@Modifying` | Thực thi INSERT/UPDATE/DELETE trực tiếp qua repository |
| Affected row count | Xác nhận số bản ghi thực sự bị thay đổi |
| `@Transactional` | Bảo vệ tính nguyên tử của kiểm tra, version, audit và DELETE |
| `@Version` | Optimistic locking khi repository lưu aggregate |
| Version predicate | Cách phối hợp concurrency cho direct SQL |
| Audit/outbox | Ghi nhận thao tác và đồng bộ sự kiện |
| Soft delete | Giữ lịch sử nhưng cần quy ước đọc/ghi nhất quán |
| Integration test | Xác nhận FK, cascade, rollback và concurrency trên database |

**Xóa trực tiếp an toàn khi database bảo vệ tham chiếu và ứng dụng bảo vệ quy tắc nghiệp vụ.** Khóa ngoại, cascade và CHECK ngăn dữ liệu sai cấu trúc; transaction cùng version/lock ngăn thao tác dựa trên trạng thái cũ; audit và outbox giữ lại dấu vết cần thiết. Nếu một thao tác xóa cần tái hiện quá nhiều invariant của aggregate, hãy cân nhắc đưa nó trở lại domain method trên aggregate root.

## Tài liệu tham khảo

- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): modifying queries, `@Modifying`, `@Query` và custom SQL.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate persistence, entity lifecycle và optimistic locking.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, transaction boundaries và rollback.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary key, foreign key, CHECK và referential actions.

