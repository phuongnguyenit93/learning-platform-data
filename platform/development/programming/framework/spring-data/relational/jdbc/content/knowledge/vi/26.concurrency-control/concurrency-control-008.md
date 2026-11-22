# Cập nhật có điều kiện và kiểm tra số hàng thay đổi trong Spring Data JDBC

## 1. Vì sao cần cập nhật có điều kiện?

Khi nhiều request cùng thao tác trên một hàng, cách đọc dữ liệu rồi mới quyết định cập nhật có thể tạo ra race condition.

Giả sử tồn kho ban đầu là 5. Hai request đồng thời đều đọc thấy 5 và mỗi request muốn giữ 4 sản phẩm. Nếu cả hai tính số lượng mới trong Java rồi ghi đè giá trị đã đọc, hệ thống có thể chấp nhận cả hai yêu cầu dù kho không đủ hàng. Đây là lỗi check-then-act: điều kiện được kiểm tra ở một thời điểm, nhưng dữ liệu có thể thay đổi trước khi thao tác ghi xảy ra.

Một cách an toàn hơn là đưa điều kiện kiểm tra vào chính câu UPDATE:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :productId
  AND :quantity > 0
  AND available_quantity >= :quantity;
~~~

Database kiểm tra điều kiện và cập nhật hàng trong cùng một statement. Request chỉ thành công nếu số lượng tại thời điểm UPDATE vẫn đáp ứng điều kiện.

**Cập nhật có điều kiện** kết hợp kiểm tra trạng thái và thay đổi dữ liệu trong một thao tác ở database. Ứng dụng đọc số hàng bị tác động để biết predicate có khớp hay không.

Cách này hữu ích với việc giữ/trừ tồn kho, trừ số dư, chuyển trạng thái đơn hàng, nhận một công việc đang chờ, giới hạn quota hoặc cập nhật khi version vẫn là giá trị caller đã đọc.

## 2. Ý nghĩa của số hàng bị thay đổi

Một lệnh UPDATE thường trả về số hàng mà database/driver báo là bị tác động. Với JDBC, con số này được trả về bởi API như `JdbcTemplate.update` hoặc modifying repository query có kiểu trả về số nguyên.

Ví dụ:

~~~sql
UPDATE customers
SET status = 'INACTIVE'
WHERE id = 42;
~~~

| Update count | Ý nghĩa thường gặp |
|---:|---|
| 1 | Một hàng thỏa điều kiện UPDATE và được báo là đã tác động |
| 0 | Không có hàng nào được báo là tác động |
| Lớn hơn 1 | Nhiều hàng thỏa predicate; có thể hợp lệ hoặc cho thấy thiếu điều kiện/constraint |

Nếu UPDATE nhắm tới một primary key duy nhất, ứng dụng thường kỳ vọng kết quả là 0 hoặc 1. Nếu count lớn hơn 1, cần xem lại predicate hoặc tính duy nhất của dữ liệu.

### 2.1. Count bằng 0 không luôn có một nguyên nhân duy nhất

Với câu UPDATE tồn kho ở trên, count bằng 0 có thể có nghĩa:

- Không có sản phẩm mang productId đó.
- Sản phẩm tồn tại nhưng số lượng hiện tại không đủ.
- Một điều kiện khác trong WHERE không còn đúng tại thời điểm UPDATE.

Không nên tự động chuyển mọi trường hợp count bằng 0 thành “không tìm thấy sản phẩm”. Tên lỗi nghiệp vụ nên phản ánh điều mà statement thực sự chứng minh được, chẳng hạn `StockReservationRejectedException`.

Nếu API phải phân biệt chính xác “không tồn tại” và “không đủ hàng”, cần thiết kế thêm cách lấy thông tin phù hợp. Có thể đọc trạng thái sau khi UPDATE thất bại, dùng SQL trả dữ liệu được database hỗ trợ (ví dụ `RETURNING` trên PostgreSQL), hoặc dùng stored procedure. Một lần đọc sau UPDATE có thể quan sát trạng thái mới hơn nếu request khác tiếp tục thay đổi dữ liệu; hãy chọn semantics theo yêu cầu nghiệp vụ.

### 2.2. Update count phụ thuộc driver và database

JDBC cung cấp update count theo contract của driver, nhưng một số hệ quản trị có khác biệt giữa số hàng khớp điều kiện và số hàng thực sự đổi giá trị.

Ví dụ, cấu hình driver MySQL có thể ảnh hưởng việc báo số hàng changed hay matched. Với UPDATE gán một giá trị bằng đúng giá trị hiện tại, count có thể khác nhau theo database hoặc cấu hình driver.

Khi logic nghiệp vụ dựa vào count chính xác, hãy kiểm thử trên hệ quản trị và driver thực tế. Thiết kế phép biến đổi sao cho thành công có nghĩa là một thay đổi thực sự, đồng thời bảo vệ invariant bằng constraint thích hợp.

## 3. Dùng @Modifying và @Query trong Spring Data JDBC

Spring Data JDBC hỗ trợ câu lệnh ghi tùy chỉnh thông qua `@Query` kết hợp `@Modifying`. Method có thể trả về số hàng bị tác động dưới dạng `int`.

Ví dụ repository giữ tồn kho:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available_quantity = available_quantity - :quantity
        WHERE product_id = :productId
          AND :quantity > 0
          AND available_quantity >= :quantity
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

`@Query` chứa SQL cụ thể; `@Modifying` cho Spring Data biết method thực hiện câu lệnh thay đổi dữ liệu. Tham số được bind, không cần nối giá trị đầu vào vào SQL.

Phần kiểm tra `:quantity > 0` bổ sung bảo vệ ở database. Service vẫn nên validate đầu vào để trả lỗi rõ ràng trước khi gọi repository:

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
}
~~~

Điều kiện ở service cải thiện contract API; điều kiện trong UPDATE giúp bảo vệ invariant ngay tại thao tác ghi.

### 3.1. Kiểm tra update count ở service

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn 0"
            );
        }

        int updated = inventory.reserve(productId, quantity);

        if (updated == 0) {
            throw new StockReservationRejectedException(
                    productId,
                    quantity
            );
        }

        if (updated != 1) {
            throw new IllegalStateException(
                    "Một productId phải xác định đúng một hàng inventory"
            );
        }
    }
}
~~~

Service diễn giải số hàng theo quy tắc nghiệp vụ: 0 nghĩa là điều kiện giữ hàng không được thỏa mãn; 1 nghĩa là giữ hàng thành công; giá trị khác cho thấy giả định một product ID tương ứng một hàng không còn đúng.

`@Transactional` đặt ở service nếu use case còn ghi đơn hàng hoặc dữ liệu khác cần cùng commit/rollback. Nếu chỉ có một UPDATE độc lập, repository method có thể đã có transaction behavior phù hợp; service transaction quan trọng khi cần kết hợp nhiều thao tác.

### 3.2. Không đọc rồi ghi đè số lượng trong Java

Mẫu dễ gặp nhưng không an toàn dưới cạnh tranh:

~~~java
Inventory item = inventory.findByProductId(productId)
        .orElseThrow();

if (item.getAvailableQuantity() >= quantity) {
    item.setAvailableQuantity(
            item.getAvailableQuantity() - quantity
    );
    inventory.save(item);
}
~~~

Hai request có thể cùng đọc một giá trị cũ trước khi một request lưu. Nếu không có optimistic locking hoặc cơ chế khóa thích hợp, một cập nhật có thể ghi đè cập nhật còn lại.

Câu UPDATE có điều kiện đưa phép trừ và điều kiện đủ hàng vào cùng một thao tác ở database. Đây là cách phù hợp khi phép biến đổi có thể biểu diễn trực tiếp bằng SQL.

## 4. Cập nhật trạng thái có điều kiện

Một ứng dụng thường có quy trình trạng thái. Ví dụ đơn hàng chỉ được xác nhận khi đang ở trạng thái PENDING.

Không nên chỉ đọc trạng thái ở Java rồi UPDATE theo ID, vì request khác có thể đổi trạng thái giữa lần đọc và lần ghi. Có thể đưa trạng thái kỳ vọng vào WHERE:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PENDING';
~~~

Repository:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = 'CONFIRMED',
        confirmed_at = CURRENT_TIMESTAMP
    WHERE id = :orderId
      AND status = 'PENDING'
    """)
int confirmIfPending(@Param("orderId") Long orderId);
~~~

Service:

~~~java
@Transactional
public void confirm(Long orderId) {
    int updated = orders.confirmIfPending(orderId);

    if (updated == 0) {
        throw new OrderCannotBeConfirmedException(orderId);
    }

    if (updated != 1) {
        throw new IllegalStateException(
                "Order ID phải xác định đúng một hàng"
        );
    }
}
~~~

Chỉ một request có thể chuyển hàng từ PENDING sang CONFIRMED theo predicate này. Khi request đầu tiên cập nhật thành công, request tiếp theo đánh giá điều kiện trên trạng thái mới và không còn khớp.

### 4.1. Compare-and-set ở database

Cách cập nhật trên có thể hiểu là compare-and-set:

- Compare: trạng thái hiện tại phải bằng giá trị kỳ vọng.
- Set: nếu điều kiện đúng, cập nhật sang giá trị mới.
- Count: dùng update count để biết có bao nhiêu hàng thỏa điều kiện.

Mẫu tổng quát:

~~~sql
UPDATE some_table
SET value = :newValue
WHERE id = :id
  AND value = :expectedValue;
~~~

Đối với state machine, predicate có thể kiểm tra nhiều điều kiện:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = :id
  AND status IN ('PENDING', 'CONFIRMED')
  AND payment_status = 'UNPAID';
~~~

Database chỉ áp dụng transition nếu trạng thái hiện tại nằm trong tập trạng thái cho phép và điều kiện thanh toán còn đúng.

## 5. Cập nhật có điều kiện kết hợp optimistic locking

Spring Data JDBC hỗ trợ optimistic locking bằng `@Version`. Khi lưu aggregate có version, framework dùng version hiện tại để phát hiện một transaction khác đã cập nhật hàng kể từ lúc entity được đọc.

Ví dụ:

~~~java
@Table("products")
public record Product(
        @Id Long id,
        @Version Long version,
        String name,
        int availableQuantity
) {}
~~~

Khi đọc entity, caller nhận version. Khi gọi repository `save`, Spring Data JDBC sử dụng version để bảo vệ cập nhật và tăng version khi lưu thành công. Nếu version không còn khớp, thao tác có thể ném `OptimisticLockingFailureException`.

### 5.1. Conditional SQL tự viết phải tự quản lý version

Câu UPDATE tự viết bằng `@Modifying @Query` là SQL do ứng dụng kiểm soát. Không nên giả định Spring Data JDBC tự động thêm điều kiện `@Version` hoặc tự tăng version cho câu SQL đó.

Nếu muốn conditional UPDATE có optimistic locking, hãy đưa version vào WHERE và tăng version trong SET:

~~~sql
UPDATE products
SET available_quantity = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND available_quantity >= :requestedQuantity;
~~~

Repository:

~~~java
@Modifying
@Query("""
    UPDATE products
    SET available_quantity = :newQuantity,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
      AND available_quantity >= :requestedQuantity
    """)
int updateQuantityIfVersionMatches(
        @Param("id") Long id,
        @Param("newQuantity") int newQuantity,
        @Param("expectedVersion") Long expectedVersion,
        @Param("requestedQuantity") int requestedQuantity
);
~~~

Nếu count bằng 1, cập nhật thành công và version tăng. Nếu count bằng 0, một trong các điều kiện không còn đúng: hàng không tồn tại, version đã thay đổi hoặc số lượng không đáp ứng predicate.

Nếu application giữ một instance entity cũ sau direct UPDATE, instance đó vẫn chứa version cũ. Hãy đọc lại entity hoặc cập nhật trạng thái trong application một cách có chủ đích; không tiếp tục lưu instance cũ như thể version đã được đồng bộ.

### 5.2. Chọn conditional predicate hay @Version?

| Tình huống | Cơ chế phù hợp |
|---|---|
| Chỉ được trừ kho khi đủ số lượng | Conditional UPDATE với predicate số lượng đủ |
| Chỉ chuyển trạng thái từ PENDING sang CONFIRMED | Conditional UPDATE với predicate trạng thái |
| Cập nhật aggregate theo version đã đọc | `@Version` với repository `save` |
| Cần cả điều kiện nghiệp vụ và version | Custom UPDATE có cả business predicate và version predicate |
| Thay đổi aggregate nhiều bảng theo mapping | Repository `save`/aggregate operations và `@Version` |

Optimistic locking phát hiện thay đổi dựa trên version. Conditional update diễn đạt trực tiếp một điều kiện nghiệp vụ. Có thể kết hợp hai cách khi use case cần cả hai.

## 6. Cập nhật số dư và invariant không được vi phạm

Một ví dụ khác là trừ tiền khỏi tài khoản. Không nên đọc số dư rồi tính số mới trong Java và ghi đè mà không có cơ chế bảo vệ.

SQL:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId
  AND :amount > 0
  AND balance >= :amount;
~~~

Repository:

~~~java
@Modifying
@Query("""
    UPDATE accounts
    SET balance = balance - :amount
    WHERE id = :accountId
      AND :amount > 0
      AND balance >= :amount
    """)
int debit(
        @Param("accountId") Long accountId,
        @Param("amount") BigDecimal amount
);
~~~

Service:

~~~java
@Transactional
public void transfer(
        Long sourceId,
        Long targetId,
        BigDecimal amount
) {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("Số tiền không hợp lệ");
    }

    int debited = accounts.debit(sourceId, amount);

    if (debited != 1) {
        throw new DebitRejectedException(sourceId);
    }

    int credited = accounts.credit(targetId, amount);

    if (credited != 1) {
        throw new CreditRejectedException(targetId);
    }
}
~~~

Cần một transaction bao quanh cả debit và credit. Nếu debit thành công nhưng credit thất bại, transaction phải rollback debit. Nếu không có transaction chung, tiền có thể bị trừ khỏi tài khoản nguồn mà không được cộng vào tài khoản đích.

Lệnh credit cũng nên kiểm tra tài khoản tồn tại và các invariant liên quan. Schema có thể bổ sung constraint phù hợp, nhưng constraint không thay thế transaction của use case chuyển tiền.

## 7. Dùng JdbcTemplate.update khi cần kiểm soát SQL

Không bắt buộc phải đặt mọi conditional UPDATE trong repository. Với bảng kỹ thuật hoặc SQL tùy chỉnh, `JdbcTemplate` và `NamedParameterJdbcTemplate` cung cấp cách thực thi trực tiếp và trả update count.

Ví dụ:

~~~java
@Repository
public class InventoryDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventoryDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int reserve(Long productId, int quantity) {
        String sql = """
                UPDATE inventory
                SET available_quantity = available_quantity - :quantity
                WHERE product_id = :productId
                  AND :quantity > 0
                  AND available_quantity >= :quantity
                """;

        var parameters = new MapSqlParameterSource()
                .addValue("productId", productId)
                .addValue("quantity", quantity);

        return jdbc.update(sql, parameters);
    }
}
~~~

`NamedParameterJdbcTemplate.update` trả về `int` biểu diễn update count do JDBC driver báo. Cách này phù hợp khi cần ghép SQL động có kiểm soát, dùng CTE hoặc tận dụng cú pháp riêng của database.

Nếu dùng JDBC template trực tiếp:

- Ứng dụng tự quản lý SQL.
- Mapping entity không được tự động áp dụng.
- `@Version` không tự thêm điều kiện hoặc tăng version.
- Lifecycle callback của Spring Data repository không tự chạy.
- Ứng dụng phải tự bảo đảm invariant của aggregate và quan hệ bảng.

Nếu thao tác thuộc aggregate và cần semantics mapping của Spring Data JDBC, cân nhắc repository API trước khi chuyển sang SQL trực tiếp.

## 8. Transaction và update count

Update count cho biết statement tác động bao nhiêu hàng; transaction quyết định các thay đổi đó được commit hay rollback.

- Một UPDATE có count bằng 1 có thể vẫn bị rollback nếu transaction sau đó thất bại.
- Một UPDATE có count bằng 0 thường không thay đổi hàng nào, nhưng transaction vẫn có thể tiếp tục.
- Nhiều UPDATE có thể cùng một transaction nếu service đặt ranh giới transaction phù hợp.
- Count được trả về trước khi transaction commit; không nên báo “đã hoàn tất” cho hệ thống ngoài trước khi commit thành công.

Ví dụ:

~~~java
@Transactional
public void placeOrderAndReserveStock(
        Order order,
        Long productId,
        int quantity
) {
    orders.save(order);

    int updated = inventory.reserve(productId, quantity);

    if (updated != 1) {
        throw new StockReservationRejectedException(
                productId,
                quantity
        );
    }
}
~~~

Nếu reservation không thành công, exception runtime thoát khỏi method sẽ làm transaction rollback theo mặc định. Bản ghi order đã lưu trước đó cũng bị rollback nếu dùng cùng transaction manager và DataSource.

### 8.1. Đừng nuốt exception sau khi count thất bại

Ví dụ không phù hợp:

~~~java
@Transactional
public void placeOrder(...) {
    orders.save(order);

    int updated = inventory.reserve(productId, quantity);

    if (updated == 0) {
        log.warn("Không đủ tồn kho");
        return; // Method kết thúc bình thường; order có thể commit.
    }
}
~~~

Nếu không đủ hàng thì đơn hàng không nên được lưu, nhưng method kết thúc bình thường nên transaction có thể commit order. Hãy ném exception phù hợp hoặc trả một kết quả nghiệp vụ được xử lý trước khi ghi order.

Một thiết kế khác là thực hiện conditional UPDATE trước, rồi chỉ lưu order nếu thành công. Dù chọn thứ tự nào, tất cả thao tác phải nằm trong transaction chung nếu chúng cần atomic.

## 9. Race condition: vì sao UPDATE có điều kiện an toàn hơn?

Giả sử tồn kho ban đầu là 5, hai request đồng thời đều muốn lấy 4.

Với cách đọc rồi ghi:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: SELECT quantity = 5
    B->>DB: SELECT quantity = 5
    A->>A: 5 >= 4
    B->>B: 5 >= 4
    A->>DB: UPDATE quantity = 1
    B->>DB: UPDATE quantity = 1
    Note over DB: Hai request có thể cùng được chấp nhận
~~~

Với conditional UPDATE:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: UPDATE ... WHERE quantity >= 4
    B->>DB: UPDATE ... WHERE quantity >= 4
    DB-->>A: update count = 1
    DB-->>B: update count = 0
    Note over DB: Chỉ một request giữ được 4 sản phẩm
~~~

Database điều phối cạnh tranh trên hàng được cập nhật. Một request thành công; request còn lại đánh giá predicate trên giá trị hiện tại sau khi cạnh tranh được giải quyết và không còn đủ điều kiện.

Kết quả cụ thể còn phụ thuộc isolation level và database, nhưng điều kiện và phép cập nhật cùng nằm trong một statement giúp tránh cửa sổ race condition của mô hình đọc rồi ghi riêng rẽ.

## 10. Constraint ở database vẫn cần thiết

Conditional UPDATE bảo vệ một invariant trong một thao tác, nhưng không thay thế các constraint của schema.

Ví dụ:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_quantity_nonnegative
CHECK (available_quantity >= 0);
~~~

Constraint này ngăn mọi đường ghi tạo ra số lượng âm, kể cả khi có một đoạn code khác quên dùng conditional UPDATE.

Một số invariant nên được bảo vệ ở database nếu có thể:

- Số lượng tồn kho không âm.
- Số dư không âm nếu domain không cho phép thấu chi.
- Khóa nghiệp vụ duy nhất.
- Foreign key hợp lệ.
- Trường bắt buộc không null.

Có thể kết hợp nhiều lớp bảo vệ: validate request ở service; conditional UPDATE để kiểm tra điều kiện ngay tại thời điểm ghi; database constraint để bảo vệ invariant trước mọi đường ghi; transaction để gom nhiều thay đổi thành một đơn vị.

## 11. Batch update và mảng update count

Nếu cập nhật nhiều bản ghi bằng JDBC batch, API thường trả về `int[]` thay vì một số duy nhất:

~~~java
int[] counts = jdbcTemplate.batchUpdate(
        "UPDATE inventory SET available_quantity = available_quantity - ? "
                + "WHERE product_id = ? AND available_quantity >= ?",
        items,
        200,
        (ps, item) -> {
            ps.setInt(1, item.quantity());
            ps.setLong(2, item.productId());
            ps.setInt(3, item.quantity());
        }
);
~~~

Mỗi phần tử trong mảng tương ứng một phần tử batch theo contract của driver. Có thể gặp:

- Số hàng bị tác động.
- `Statement.SUCCESS_NO_INFO`: statement thành công nhưng driver không cung cấp số hàng chính xác.
- `Statement.EXECUTE_FAILED`: phần tử batch thất bại trong một số tình huống báo lỗi.

Khi batch ném `BatchUpdateException`, exception có thể chứa update counts của các phần tử đã thực thi trước lúc lỗi được báo. Không giả định mọi driver đều thực thi hoặc báo lỗi theo cùng một cách.

Nếu nghiệp vụ yêu cầu từng item phải thành công đúng một hàng, batch API có thể không đủ để đưa ra quyết định chi tiết nếu driver trả `SUCCESS_NO_INFO`. Có thể cần xử lý từng lệnh, chia batch nhỏ hoặc dùng SQL trả kết quả theo cách database hỗ trợ.

## 12. Phân biệt update count với optimistic locking exception

| Cách cập nhật | Cách báo xung đột |
|---|---|
| Repository `save` với entity có `@Version` | Có thể ném `OptimisticLockingFailureException` khi version không khớp |
| Custom `@Modifying @Query` trả `int` | Ứng dụng kiểm tra count, thường 0 nghĩa predicate không khớp |
| `JdbcTemplate.update` | Trả về update count |
| JDBC batch | Trả mảng update counts hoặc ném `BatchUpdateException` |

Đừng chờ `@Modifying` tự ném optimistic locking exception chỉ vì SQL WHERE có điều kiện version. Nếu custom query trả count bằng 0, ứng dụng phải diễn giải và chuyển thành exception/domain result phù hợp.

Ngược lại, không cần tự so sánh update count của một repository `save` có `@Version` như thể nó là modifying query. Hãy dùng contract của API đang gọi.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai request cùng giữ vượt tồn kho | Đọc rồi ghi trong Java mà không có atomic condition/version | Dùng conditional UPDATE hoặc optimistic locking |
| Update count bằng 0 nhưng báo sai lỗi | Một predicate có thể thất bại vì nhiều nguyên nhân | Dùng lỗi tổng quát hoặc truy vấn bổ sung nếu cần phân biệt |
| Count lớn hơn 1 khi cập nhật một sản phẩm | product_id không unique hoặc predicate thiếu điều kiện | Thêm unique constraint và sửa WHERE |
| Câu UPDATE custom bỏ qua version | Mong đợi Spring tự áp dụng `@Version` cho SQL viết tay | Đưa version vào WHERE và tăng version trong SET |
| Entity trong bộ nhớ vẫn có version cũ | Direct UPDATE không đồng bộ object đã tải | Đọc lại entity hoặc dùng kết quả cập nhật có chủ đích |
| Đơn hàng vẫn được lưu khi giữ kho thất bại | Count bằng 0 nhưng method kết thúc bình thường | Ném exception hoặc xử lý kết quả trước khi commit |
| Debit thành công nhưng credit thất bại | Hai thao tác không nằm trong transaction chung | Đặt `@Transactional` ở service |
| UPDATE gán giá trị cũ trả count khác dự kiến | Database/driver phân biệt matched và changed rows | Kiểm thử semantics của database mục tiêu |
| SQL injection trong điều kiện cập nhật | Nối dữ liệu người dùng vào SQL | Bind mọi giá trị bằng named/positional parameter |
| Batch count là `SUCCESS_NO_INFO` | Driver không cung cấp số hàng chính xác | Chọn chiến lược xử lý phù hợp contract batch |
| Check constraint vẫn bị vi phạm ở đường ghi khác | Chỉ bảo vệ invariant trong một method | Bổ sung constraint ở database |
| Lỗi bị bắt và nuốt trong transaction | Caller không thấy lỗi để rollback theo mặc định | Ném lại exception hoặc đánh dấu rollback-only có chủ đích |

## 14. Quy trình triển khai cập nhật có điều kiện

1. Xác định invariant cần bảo vệ, ví dụ số lượng không âm hoặc trạng thái phải là PENDING.
2. Chuyển điều kiện kiểm tra vào mệnh đề WHERE của UPDATE.
3. Đưa phép biến đổi dữ liệu vào cùng statement.
4. Bind tham số; không nối giá trị request vào SQL.
5. Chọn API phù hợp: `@Modifying @Query`, `JdbcTemplate.update` hoặc repository `save` với `@Version`.
6. Nhận update count và xác định rõ ý nghĩa của 0, 1 hoặc nhiều hơn 1 hàng.
7. Chuyển kết quả thành domain exception hoặc kết quả nghiệp vụ phù hợp.
8. Đặt transaction ở service nếu use case gồm nhiều thao tác cần atomic.
9. Bổ sung constraint ở database cho invariant có thể biểu diễn trong schema.
10. Kiểm thử hai request đồng thời trên database mục tiêu và xác nhận không vượt invariant.

## 15. Bài tập thực hành

### Bài 1 — Conditional stock reservation

Tạo bảng inventory có available_quantity. Viết method `reserve` bằng `@Modifying @Query`, chỉ trừ khi số lượng hiện tại đủ. Kiểm tra update count với sản phẩm tồn tại, không tồn tại và không đủ hàng.

### Bài 2 — Cạnh tranh hai request

Đặt tồn kho ban đầu là 5. Dùng hai thread đồng thời yêu cầu giữ 4 sản phẩm. So sánh cách đọc rồi ghi với conditional UPDATE. Xác nhận tổng số lượng được giữ không vượt quá 5.

### Bài 3 — State transition

Viết UPDATE chỉ chuyển order từ PENDING sang CONFIRMED. Gửi hai request đồng thời và kiểm tra chỉ một request nhận count bằng 1.

### Bài 4 — Optimistic locking

Thêm `@Version` vào entity. Đọc cùng một entity ở hai transaction, lưu lần lượt và quan sát optimistic locking failure. Sau đó viết custom UPDATE có điều kiện version và tự tăng version.

### Bài 5 — Transaction nhiều thao tác

Viết use case tạo order rồi giữ stock. Khi update count bằng 0, ném runtime exception. Xác nhận order được rollback. Sau đó thử bắt exception và không ném lại để quan sát khác biệt.

### Bài 6 — JDBC update count

Viết cùng một conditional UPDATE bằng `JdbcTemplate.update` và repository `@Modifying @Query`. So sánh return value và transaction participation.

### Bài 7 — Database constraint

Thêm CHECK constraint không cho tồn kho âm. Thử một câu UPDATE khác bỏ qua điều kiện đủ hàng và xác nhận database vẫn bảo vệ invariant.

### Bài 8 — Batch update

Cập nhật nhiều sản phẩm bằng `batchUpdate`. Quan sát `int[]`, thử một phần tử không thỏa điều kiện và một phần tử vi phạm constraint. Xử lý `BatchUpdateException` và update counts theo driver.

## 16. Ghi nhớ

- Cập nhật có điều kiện đặt kiểm tra và thay đổi dữ liệu trong cùng câu UPDATE để giảm race condition kiểu đọc rồi ghi.
- Update count cho biết số hàng mà JDBC/database báo bị tác động; với khóa duy nhất, ứng dụng thường kỳ vọng 0 hoặc 1.
- Count bằng 0 có thể do hàng không tồn tại hoặc predicate nghiệp vụ không còn đúng; đừng gán nguyên nhân cụ thể nếu statement không phân biệt được.
- Dùng `@Modifying @Query` cho SQL ghi trong repository hoặc `JdbcTemplate.update` khi cần điều khiển SQL trực tiếp.
- Custom SQL không tự áp dụng optimistic locking `@Version`; nếu cần, hãy thêm version predicate và tăng version trong SET.
- Repository `save` với `@Version` có contract optimistic locking riêng và có thể ném `OptimisticLockingFailureException`.
- Đặt `@Transactional` ở service khi nhiều thao tác database phải cùng commit hoặc rollback.
- Update count khác transaction outcome: statement có thể báo thành công nhưng transaction sau đó vẫn rollback.
- Database constraint tiếp tục bảo vệ invariant trước mọi đường ghi.
- Với batch, kết quả là mảng update counts và có thể chứa `SUCCESS_NO_INFO` hoặc `EXECUTE_FAILED`; hãy hiểu driver đang dùng.
