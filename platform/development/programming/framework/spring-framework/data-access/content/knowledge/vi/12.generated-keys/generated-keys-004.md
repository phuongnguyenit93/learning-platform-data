# Kiểm tra số hàng bị ảnh hưởng để phát hiện dữ liệu không tồn tại hoặc xung đột

Trong Spring Framework Data Access, lệnh `UPDATE` hoặc `DELETE` có thể thực thi hợp lệ về mặt SQL nhưng **không tác động đến bản ghi nào**. Nếu chỉ kiểm tra rằng phương thức không ném exception, ứng dụng có thể trả lời “cập nhật thành công” dù bản ghi đã bị xóa, trạng thái không còn hợp lệ hoặc một giao dịch khác đã cập nhật dữ liệu trước đó. Cách kiểm soát là đọc **số hàng bị ảnh hưởng** (*affected row count / update count*) và so sánh với số hàng mà nghiệp vụ mong đợi.

Bài này tập trung vào cập nhật một bản ghi, cập nhật có điều kiện và **optimistic locking** trong Spring JDBC và Spring Data JPA. Mục tiêu là biết khi nào `0` nghĩa là “không tìm thấy”, khi nào có thể là “xung đột”, tại sao `1` thường là thành công, và vì sao cần xử lý cả trường hợp lớn hơn `1`.

## 1. Nguồn gốc và ý nghĩa của row count

Với Spring JDBC, `JdbcTemplate.update(...)` trả về `int` là số hàng mà JDBC driver báo đã bị ảnh hưởng bởi lệnh cập nhật. Ví dụ:

```java
int affected = jdbcTemplate.update(
    "UPDATE orders SET status = ? WHERE id = ?",
    "PAID", 101L
);
```

`JdbcTemplate` **không mặc định ném exception khi `affected == 0`**: câu SQL hợp lệ và chạy thành công, chỉ là không có hàng nào đáp ứng điều kiện (hoặc không có hàng nào được tính là đã thay đổi theo quy ước của driver). Việc `0` có được chấp nhận hay phải chuyển thành lỗi nghiệp vụ là trách nhiệm của ứng dụng.

| Kết quả | Diễn giải cho thao tác dự kiến cập nhật đúng một hàng | Hành động thường gặp |
| --- | --- | --- |
| `1` | Đúng một hàng được cập nhật theo quy ước trả kết quả của database/driver | Xác nhận thành công |
| `0` | Không có hàng phù hợp toàn bộ điều kiện `WHERE`, hoặc không có thay đổi được driver tính | Xác định bản ghi vắng mặt, điều kiện không đạt hay phiên bản đã lỗi thời |
| `> 1` | Nhiều hàng bị ảnh hưởng, trái với giả định “một bản ghi” | Ném lỗi, rollback giao dịch, kiểm tra `WHERE` và ràng buộc dữ liệu |

Cần phân biệt **số hàng bị ảnh hưởng** với số hàng của `SELECT COUNT(*)`. Row count là kết quả của chính lệnh DML đã thực thi; nó **không** phải số bản ghi hiện có trong bảng, số bản ghi đọc trước đó, hay số đối tượng trong persistence context của JPA.

### Phải xác định kỳ vọng từ nghiệp vụ

- Cập nhật/xóa một thực thể theo khóa chính: thường mong đợi **đúng 1 hàng**.
- Chuyển trạng thái khi trạng thái cũ phải là `PENDING`: kỳ vọng đúng 1; `0` có thể do đã chuyển trạng thái, bị xóa hoặc sai ID.
- Giảm tồn kho với điều kiện đủ số lượng: `0` có thể là không có sản phẩm **hoặc** không đủ tồn kho.
- Cập nhật hàng loạt có chủ đích: có thể chấp nhận nhiều hàng; so sánh với điều kiện riêng, không áp đặt luôn `== 1`.
- Xóa idempotent: hợp đồng API có thể xem “đã không tồn tại” là kết quả chấp nhận được; việc bỏ qua `0` phải là quyết định có chủ đích.

## 2. Vì sao kiểm tra row count đơn thuần chưa đủ để phát hiện xung đột?

Giả sử hai yêu cầu cùng đọc đơn hàng `id = 101` và cả hai đều nhìn thấy `status = 'NEW'`.

```sql
UPDATE orders SET status = 'PAID' WHERE id = 101;
UPDATE orders SET status = 'CANCELLED' WHERE id = 101;
```

Nếu hai lệnh lần lượt thành công, **cả hai có thể trả về 1**, nhưng cập nhật thứ hai đã ghi đè kết quả thứ nhất (*lost update*). Kiểm tra `affected == 1` chỉ chứng minh có một hàng được cập nhật theo điều kiện SQL; nó **không tự phát hiện** xung đột nếu điều kiện `WHERE` không chứa thông tin để nhận ra dữ liệu đã đổi.

Cách phổ biến là **optimistic locking**: lưu cột `version`, truyền phiên bản mà người gọi đã đọc và kiểm tra phiên bản đó ngay trong `WHERE`. Đây là phép kiểm tra và cập nhật **nguyên tử trong một câu SQL**.

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL
);

INSERT INTO orders (id, status, version)
VALUES (101, 'NEW', 4);
```

Khi người gọi đã đọc đơn hàng ở phiên bản `4`, thực thi:

```sql
UPDATE orders
   SET status = 'PAID',
       version = version + 1
 WHERE id = 101
   AND version = 4;
```

- Nếu hàng `101` vẫn ở phiên bản `4`: một hàng khớp, cập nhật trạng thái, tăng phiên bản lên `5`, row count thường là `1`.
- Nếu giao dịch khác đã tăng phiên bản lên `5`: điều kiện `version = 4` không còn đúng, row count là `0`.
- Nếu `id = 101` đã bị xóa: cũng là `0`.

Lược đồ cạnh tranh điển hình:

| Thời điểm | Yêu cầu A | Yêu cầu B | Dữ liệu |
| --- | --- | --- | --- |
| T1 | Đọc `id=101, version=4` | Đọc `id=101, version=4` | `version=4` |
| T2 | `UPDATE ... WHERE id=101 AND version=4` → `1` | — | `version=5` |
| T3 | — | `UPDATE ... WHERE id=101 AND version=4` → `0` | Vẫn là kết quả của A |

B được báo xung đột hoặc phiên bản lỗi thời; nó không âm thầm ghi đè A. Cơ chế này hoạt động trên điều kiện được database kiểm tra ngay lúc cập nhật, không cần đặt một câu `SELECT` trước mỗi `UPDATE`. Một điều kiện `WHERE status = 'NEW'` cũng có thể bảo vệ một phép chuyển trạng thái nhất định, nhưng cột `version` tổng quát hơn khi nhiều thuộc tính có thể thay đổi.

## 3. Thực hiện bằng Spring JDBC: kiểm tra đúng một hàng

Ví dụ sau là một lớp service Java 17+ trong ứng dụng Spring Boot đã cấu hình `DataSource`, có dependency `spring-boot-starter-jdbc` và bảng `orders` ở phần trên. Lớp có thể được đặt tại `src/main/java/example/orders/OrderStatusService.java`; đây là **thành phần của một ứng dụng Spring**, không phải chương trình độc lập để chạy trực tiếp bằng `java OrderStatusService`.

```java
package example.orders;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.JdbcUpdateAffectedIncorrectNumberOfRowsException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderStatusService {
    private static final String UPDATE_SQL = """
            UPDATE orders
               SET status = ?,
                   version = version + 1
             WHERE id = ?
               AND version = ?
            """;

    private final JdbcTemplate jdbcTemplate;

    public OrderStatusService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void changeStatus(long orderId, long expectedVersion, String newStatus) {
        int affected = jdbcTemplate.update(
                UPDATE_SQL, newStatus, orderId, expectedVersion);

        if (affected == 0) {
            throw new OptimisticLockingFailureException(
                    "Order " + orderId
                    + " does not exist or has a different version");
        }

        if (affected != 1) {
            throw new JdbcUpdateAffectedIncorrectNumberOfRowsException(
                    UPDATE_SQL, 1, affected);
        }
    }
}
```

**Điểm cần hiểu trong code:**

1. `UPDATE_SQL` gồm **khóa định danh** và **phiên bản mong đợi**; tăng `version` ngay trong database. Thứ tự tham số khớp ba dấu `?`: trạng thái mới, ID, phiên bản cũ.
2. `affected == 0` được xem là thao tác không thể hoàn tất theo phiên bản mà caller cung cấp. Thông báo cố ý nói “không tồn tại **hoặc** đã thay đổi”, vì từ row count **không thể biết chắc nguyên nhân nào**.
3. `affected > 1` là vi phạm bất biến “chỉ một đơn hàng” và được biểu diễn bằng `JdbcUpdateAffectedIncorrectNumberOfRowsException` (constructor nhận SQL, số kỳ vọng và số thực tế). Với `id` là khóa chính thì trường hợp này không xảy ra nếu lệnh SQL giữ nguyên điều kiện đúng; kiểm tra vẫn hữu ích để tránh bỏ sót sai sót khi thay đổi câu SQL.
4. `@Transactional` giữ các thay đổi liên quan trong một giao dịch. Hai exception trên đều là unchecked exception nên theo cấu hình rollback mặc định của Spring, nếu thoát ra khỏi phương thức được transaction proxy quản lý, giao dịch sẽ rollback. Điều này đặc biệt quan trọng nếu trước lệnh này đã có các lệnh ghi khác.
5. `JdbcTemplate` dùng bind parameter, tránh ghép trực tiếp ID/trạng thái vào câu SQL.

**Trách nhiệm tầng service:** chỉ phát tín hiệu lỗi nghiệp vụ hoặc xung đột dữ liệu. Tầng HTTP/API sau đó mới quyết định trả `404 Not Found`, `409 Conflict` hoặc `412 Precondition Failed` theo giao ước của API và bằng chứng bổ sung. Không nên tự động trả `404` cho mọi trường hợp `affected == 0` khi có điều kiện phiên bản.

### Khi chỉ cần phát hiện “không tồn tại”

Nếu nghiệp vụ chỉ là xóa đúng một ID và không yêu cầu phát hiện cập nhật đồng thời, phép kiểm tra có thể đơn giản hơn:

```java
int affected = jdbcTemplate.update(
        "DELETE FROM orders WHERE id = ?", orderId);

if (affected == 0) {
    throw new IllegalArgumentException("Order not found: " + orderId);
}
if (affected != 1) {
    throw new IllegalStateException(
            "Expected one deleted row, got " + affected);
}
```

Đây là **đoạn trích trong service**, không phải một lớp Java độc lập. Không có cột `version` trong `WHERE` nên nó không phát hiện được người khác đã sửa nội dung hàng trước khi xóa. Nếu cần kiểm soát việc xóa dựa trên bản đã đọc, hãy thêm `AND version = ?` và xử lý `0` là “không tồn tại hoặc xung đột”.

## 4. Xử lý đúng khi kết quả là 0

**`0` chỉ khẳng định câu lệnh không tạo ra số hàng bị ảnh hưởng theo quy ước của database/driver.** Ý nghĩa nghiệp vụ phụ thuộc toàn bộ điều kiện `WHERE` và cách đếm kết quả.

| Điều kiện lệnh cập nhật | Các khả năng khi kết quả là `0` |
| --- | --- |
| `WHERE id = ?` | Không có ID; một số hệ quản trị/driver còn báo `0` khi cập nhật giá trị giống hệt giá trị cũ |
| `WHERE id = ? AND version = ?` | Không có ID; phiên bản đã thay đổi; cần xét quy tắc đếm của driver |
| `WHERE id = ? AND status = 'PENDING'` | Không có ID hoặc trạng thái hiện tại không còn `PENDING` |
| `WHERE sku = ? AND stock >= ?` | Không có SKU hoặc tồn kho không đủ |
| `WHERE id = ? AND deleted = FALSE` | Bản ghi không có hoặc đã soft-delete |

Nếu API cần phân biệt giữa `404` và `409`, có thể truy vấn trạng thái hiện tại **sau khi nhận `0`** (ví dụ tìm theo ID) để có thông tin chẩn đoán. Tuy nhiên, trạng thái có thể thay đổi tiếp giữa hai câu SQL tùy mức cách ly và khóa; do đó kết quả truy vấn bổ sung không nên được mô tả như bằng chứng tuyệt đối về lý do lệnh cập nhật trước đó thất bại. Một API khác có thể chọn thông báo chung “không còn phù hợp để cập nhật” và yêu cầu client tải lại.

**Không kiểm tra tồn tại trước rồi bỏ kiểm tra row count:** hai lệnh `SELECT ... WHERE id = ?` và `UPDATE ... WHERE id = ?` tách rời tạo ra khoảng thời gian mà giao dịch khác có thể sửa/xóa hàng. Kiểm tra số hàng ngay từ chính `UPDATE` có điều kiện là tuyến phòng vệ cốt lõi.

### Chú ý “matched rows” và “changed rows”

Một số database/driver có thể báo số hàng *khớp điều kiện*, trong khi nơi khác hoặc cấu hình khác báo số hàng *thực sự thay đổi*. Ví dụ MySQL thông thường tính số hàng thực sự thay đổi cho `UPDATE`; tùy `CLIENT_FOUND_ROWS` có thể tính số hàng khớp `WHERE`. Do đó:

```sql
UPDATE orders SET status = 'NEW' WHERE id = 101;
```

Khi trạng thái đã là `NEW`, kết quả trả về có thể khác giữa các cấu hình dù ID vẫn tồn tại. Cách tăng `version = version + 1` trong cập nhật có kiểm tra phiên bản giúp câu lệnh có thay đổi thực sự nếu khớp, từ đó giảm sự mơ hồ này. Vẫn phải kiểm chứng hành vi với **database, JDBC driver và cấu hình datasource thực tế**.

Đừng dùng row count của upsert, truy vấn nhiều bảng, trigger hay cascade như thể nó luôn bằng số *thực thể nghiệp vụ* bị thay đổi. Quy tắc trả kết quả của từng cú pháp có thể khác.

## 5. Spring Data JPA: hai con đường và khác biệt quan trọng

### 5.1. Dùng `@Version` với entity được quản lý

Trong JPA, cách ưu tiên khi làm việc với managed entity là khai báo thuộc tính phiên bản:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class OrderEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;

    protected OrderEntity() {
    }

    // Các getter/setter khác được lược bỏ vì đây là đoạn minh họa mapping.
}
```

Khi entity được tải và sửa trong một transaction, JPA provider dùng `@Version` để thực hiện optimistic locking; nếu dữ liệu đã bị giao dịch khác thay đổi, provider có thể ném `OptimisticLockException` và Spring thường chuyển thành exception thuộc nhóm optimistic locking. **Thời điểm phát hiện có thể là lúc flush hoặc commit**, không nhất thiết ngay khi gọi `save(...)`. Không tự tăng phiên bản trong code cập nhật managed entity khi provider đã quản lý `@Version`.

### 5.2. Dùng `@Modifying @Query` khi cập nhật trực tiếp

Spring Data JPA cho phép phương thức truy vấn sửa dữ liệu trả về `int`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           UPDATE OrderEntity o
              SET o.status = :newStatus,
                  o.version = o.version + 1
            WHERE o.id = :id AND o.version = :expectedVersion
           """)
    int updateIfVersionMatches(
            @Param("id") Long id,
            @Param("expectedVersion") long expectedVersion,
            @Param("newStatus") String newStatus);
}
```

Phương thức này là **đoạn thành phần trong ứng dụng JPA** và giả định `OrderEntity` có các thuộc tính đã khai báo phù hợp. Gọi nó từ một service có `@Transactional`, kiểm tra `0`/`1`/`>1` như ví dụ JDBC.

Lưu ý quan trọng:

- Bulk JPQL update của `@Modifying` **bỏ qua cơ chế dirty checking và kiểm tra phiên bản tự động trên từng managed entity**. Vì vậy, khi chọn bulk update để thực hiện optimistic locking, điều kiện `o.version = :expectedVersion` và việc tăng `o.version` phải được viết rõ ràng trong JPQL (hoặc dùng cơ chế phù hợp của provider).
- `flushAutomatically = true` yêu cầu flush thay đổi đang chờ trước khi chạy bulk query; `clearAutomatically = true` xóa persistence context sau đó để giảm nguy cơ đọc entity đã cũ. Việc clear cũng detach các entity đang quản lý, nên chỉ bật với hiểu biết về luồng transaction và dữ liệu chưa flush.
- `@Modifying` áp dụng cho phương thức repository có `@Query` sửa dữ liệu; nó không biến `save(...)` thành một phương thức trả row count.
- Không trộn cách cập nhật entity có `@Version` với bulk update bỏ qua phiên bản mà không có chính sách nhất quán: rất dễ tạo ra các đường ghi âm thầm đè nhau.

## 6. Phân biệt exception và lỗi nghiệp vụ

Một SQL statement không lỗi cú pháp vẫn có thể trả `0`. Spring JDBC không xem `0` là SQL exception tự nhiên. Application cần chuyển kết quả thành một lỗi phù hợp khi điều kiện hậu kiểm không đạt.

- `JdbcUpdateAffectedIncorrectNumberOfRowsException`: lựa chọn rõ nghĩa khi kỳ vọng số hàng cụ thể mà thực tế không đúng. Nó thuộc hệ `DataAccessException` và cung cấp `getExpectedRowsAffected()`, `getActualRowsAffected()`. Có thể dùng cho mọi trường hợp khác `1` nếu không cần phân biệt nguyên nhân.
- `OptimisticLockingFailureException`: tín hiệu hợp lý cho thao tác có phiên bản cũ không còn áp dụng được; khi row count là `0` vẫn cần tránh tuyên bố chắc chắn bản ghi có tồn tại.
- `IllegalArgumentException`, `IllegalStateException` hoặc domain exception riêng: dùng khi tầng nghiệp vụ muốn thể hiện “không tìm thấy”, “trạng thái không hợp lệ” hoặc vi phạm bất biến. Nên chọn một quy ước nhất quán để tầng API ánh xạ.
- Với JPA managed entity, exception optimistic locking có thể xuất hiện khi flush/commit; code gọi repository không nên giả định lúc nào cũng nhận được một số nguyên.

Nếu nghiệp vụ cần **mọi thao tác trong transaction cùng thất bại**, phải để exception phù hợp thoát ra ngoài boundary của transaction hoặc chủ động đánh dấu rollback. Mặc định Spring rollback với `RuntimeException` và `Error`, không mặc định rollback với mọi checked exception. Tránh bắt exception rồi lặng lẽ trả “OK”, vì điều đó có thể khiến những ghi trước đó được commit.

## 7. Phát hiện và xử lý xung đột trong luồng API

Một luồng cập nhật có phiên bản có thể được mô tả như sau:

```text
Client đọc: id=101, status=NEW, version=4
       |
Client gửi: id=101, status=PAID, expectedVersion=4
       |
Service: UPDATE ... WHERE id=101 AND version=4
       |
       +-- affected = 1  --> Thành công; phiên bản tăng lên 5
       |
       +-- affected = 0  --> Không còn khớp điều kiện:
       |                    không tồn tại hoặc phiên bản/trạng thái đã đổi
       |
       +-- affected > 1  --> Sai bất biến; rollback và điều tra
```

Tầng API có thể xử lý:

| Tình huống đã được xác định | Phản hồi minh họa |
| --- | --- |
| ID thật sự không tồn tại theo chính sách tra cứu của API | `404 Not Found` |
| Bản ghi tồn tại nhưng `expectedVersion` cũ | `409 Conflict` |
| API dùng HTTP conditional request với `If-Match`/ETag và điều kiện không còn đúng | `412 Precondition Failed` |
| Có nhiều hàng bị sửa ngoài ý muốn | Lỗi máy chủ, rollback, log và cảnh báo điều tra; không trả thành công |

Khi gặp xung đột, client nên tải lại dữ liệu và cho người dùng quyết định áp dụng thay đổi trên phiên bản mới. **Không tự động thử lại bằng cách lấy version mới rồi ghi lại giá trị cũ mà không hòa giải**, vì thao tác đó có thể cố tình ghi đè cập nhật của người khác.

## 8. Các trường hợp cần cân nhắc riêng

### Cập nhật có điều kiện theo trạng thái

```sql
UPDATE orders
   SET status = 'PAID'
 WHERE id = ?
   AND status = 'NEW';
```

`0` có thể là không tồn tại, đã thanh toán, đã hủy hoặc trạng thái khác. Nếu nghiệp vụ quy định chỉ cho phép chuyển `NEW -> PAID`, đây là cách bảo vệ điều kiện chuyển trạng thái ngay tại database. Khi nhiều thuộc tính liên quan thay đổi, hãy cân nhắc kết hợp version để phát hiện xung đột tổng quát.

### Trừ tồn kho nguyên tử

```sql
UPDATE inventory
   SET available = available - ?
 WHERE sku = ?
   AND available >= ?;
```

Truyền cùng số lượng cần trừ vào tham số thứ nhất và thứ ba. `1` nghĩa là phép trừ được áp dụng cho một SKU phù hợp; `0` nghĩa là điều kiện không được đáp ứng, có thể thiếu SKU hoặc không đủ hàng. Điều kiện `available >= ?` tránh âm kho khi nhiều yêu cầu cạnh tranh, nếu bảng có ràng buộc định danh SKU thích hợp.

### Soft delete hoặc thao tác idempotent

```sql
UPDATE orders
   SET deleted = TRUE
 WHERE id = ?
   AND deleted = FALSE;
```

Nếu `0`, bản ghi có thể đã bị xóa mềm hoặc chưa từng tồn tại. Với một API có hợp đồng “xóa nhiều lần vẫn thành công”, `0` có thể hợp lệ. Với API bắt buộc thực sự chuyển trạng thái, `0` cần được báo rõ.

### Batch update

`JdbcTemplate.batchUpdate(...)` thường trả về mảng đếm theo từng lệnh. **Không cộng hoặc so sánh mù quáng** vì JDBC còn có giá trị đặc biệt `Statement.SUCCESS_NO_INFO` (`-2`: thực thi thành công nhưng không biết số hàng) và `Statement.EXECUTE_FAILED` (`-3`: lệnh thất bại trong các ngữ cảnh batch tương ứng). Khi cần bảo đảm *mỗi* cập nhật đúng một hàng, kiểm tra từng phần tử và chọn chiến lược giao dịch/driver phù hợp; đừng mặc định `-2` là “0 hàng”.

## 9. Kiểm thử bắt buộc cho hành vi row count

Nên thực hiện integration test với **cùng loại database và driver như môi trường thật**, nhất là khi logic phụ thuộc số hàng bị ảnh hưởng.

| Kịch bản | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Thành công | `id=101` có `version=4`; cập nhật với `expectedVersion=4` | `affected=1`, trạng thái mới, `version=5` |
| Phiên bản cũ | Sau ca trên, tiếp tục cập nhật với `expectedVersion=4` | `affected=0`, không ghi đè thay đổi trước |
| ID không tồn tại | Cập nhật `id=999` với phiên bản bất kỳ | `affected=0` |
| Cạnh tranh | Hai transaction dùng cùng phiên bản ban đầu | Chỉ một cập nhật có điều kiện thắng; giao dịch còn lại nhận xung đột hoặc lỗi liên quan theo DB |
| Trạng thái không phù hợp | `WHERE status='NEW'` nhưng hàng đang `PAID` | `affected=0` |
| Sai `WHERE` | Thử trên bảng test có nhiều hàng cùng thỏa điều kiện quá rộng | `affected>1` và transaction rollback |
| Không đổi giá trị | Cập nhật cùng giá trị cũ, không tăng version | Kiểm chứng quy ước đếm thực tế của DB/driver |

Ví dụ kiểm tra bằng SQL trên **database thử nghiệm riêng**:

```sql
INSERT INTO orders (id, status, version)
VALUES (202, 'NEW', 7);

UPDATE orders
   SET status = 'PAID', version = version + 1
 WHERE id = 202 AND version = 7;
-- Kỳ vọng: 1 hàng; version trở thành 8.

UPDATE orders
   SET status = 'CANCELLED', version = version + 1
 WHERE id = 202 AND version = 7;
-- Kỳ vọng: 0 hàng; trạng thái PAID và version 8 vẫn giữ nguyên.

SELECT id, status, version FROM orders WHERE id = 202;
-- Hàng kỳ vọng: (202, 'PAID', 8).
```

Phần ghi chú sau dấu `--` chỉ là **kỳ vọng kết quả** để kiểm thử, không phải bản sao stdout của một công cụ SQL cụ thể. Trong automated test, hãy kiểm tra cả **database state sau commit/rollback** chứ không chỉ kiểm tra giá trị trả về từ service. Với ca rollback do `affected>1`, dùng transaction thực và xác nhận những thay đổi không được commit.

## 10. Lỗi thường gặp và checklist áp dụng

| Lỗi triển khai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Không đọc `affected` sau `JdbcTemplate.update` | Báo thành công dù không sửa hàng nào | So sánh với số hàng nghiệp vụ mong đợi |
| Coi mọi `0` là “không tìm thấy” | Che giấu xung đột version/trạng thái | Diễn giải theo toàn bộ `WHERE` và hợp đồng API |
| Chỉ dựa vào `affected == 1`, không có version | Không chặn lost update | Thêm điều kiện version hoặc điều kiện trạng thái thích hợp |
| `SELECT` kiểm tra tồn tại rồi `UPDATE` không điều kiện | Race condition giữa hai câu lệnh | Kiểm tra điều kiện ngay trong `UPDATE` và row count |
| Bỏ qua `affected > 1` | Có thể sửa nhiều hàng sai và vẫn trả OK | Chặn bằng khóa/ràng buộc, rollback nếu vi phạm |
| Dùng bulk JPQL mà quên version | Vô hiệu hóa bảo vệ optimistic locking | Thêm `WHERE version` và tăng version, hoặc dùng managed entity |
| Bắt lỗi bên trong transaction rồi vẫn trả thành công | Có nguy cơ commit các ghi không mong muốn | Để unchecked exception thoát boundary hoặc đánh dấu rollback |
| Tự retry trên version mới mà không hợp nhất | Có thể ghi đè dữ liệu của người khác | Yêu cầu reload và giải quyết xung đột |
| Giả định mọi database đếm UPDATE như nhau | Hiểu sai trường hợp “no-op update” | Kiểm thử chính driver/configuration đang dùng |
| Coi `-2` từ batch là thất bại hoặc 0 | Kết luận sai | Xử lý riêng `SUCCESS_NO_INFO` |

**Checklist trước khi hoàn thành một API cập nhật:**

1. Câu `WHERE` đã bao gồm ID/khóa duy nhất và điều kiện bảo vệ cạnh tranh cần thiết chưa?
2. Số hàng kỳ vọng là `0`, `1`, một khoảng, hay một tập giá trị có ý nghĩa nghiệp vụ?
3. Đã xử lý riêng `0`, `1` và `>1` mà không giả định sai nguyên nhân chưa?
4. Có `@Transactional` đúng boundary và exception khiến rollback khi thao tác không đạt bất biến không?
5. Có đường ghi nào (JPQL bulk, native SQL, scheduled job) bỏ qua cơ chế version không?
6. Đã kiểm thử concurrent update, row count no-op, rollback và hành vi driver thực tế chưa?

**Nguyên tắc cốt lõi:** row count là bằng chứng trực tiếp về **lệnh ghi vừa thực hiện**. Nó trở thành công cụ phát hiện dữ liệu không tồn tại hoặc xung đột khi được kết hợp với `WHERE` đúng, phiên bản hoặc điều kiện trạng thái, quy tắc đánh giá `0/1/>1` và quản lý transaction.

## Tài liệu tham khảo

- Spring Framework `JdbcTemplate.update(...)` (Java API): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework `JdbcUpdateAffectedIncorrectNumberOfRowsException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/JdbcUpdateAffectedIncorrectNumberOfRowsException.html
- Spring Data JPA, `@Modifying` query: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.modifying-queries
- Spring Framework, transaction rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- MySQL affected rows (`ROW_COUNT()`): https://dev.mysql.com/doc/refman/8.4/en/information-functions.html
- JDBC `Statement.executeBatch()` / `SUCCESS_NO_INFO`: https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html