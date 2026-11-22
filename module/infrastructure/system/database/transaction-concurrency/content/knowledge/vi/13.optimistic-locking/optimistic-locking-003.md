# Sử dụng số hàng bị tác động để phát hiện xung đột

Khóa lạc quan (optimistic locking) giả định rằng xung đột ghi không xảy ra thường xuyên. Thay vì khóa một hàng ngay từ lúc đọc và giữ khóa trong suốt quá trình xử lý, ứng dụng đọc dữ liệu cùng một dấu mốc phiên bản, xử lý ở phía ứng dụng, rồi chỉ cập nhật nếu dấu mốc đó vẫn còn đúng.

Một câu lệnh `UPDATE` có điều kiện phiên bản thường tác động đúng một hàng khi dữ liệu chưa bị thay đổi. Nếu không có hàng nào khớp, ứng dụng biết rằng trạng thái đã khác với trạng thái mà nó dựa vào. **Số hàng bị tác động** vì thế trở thành tín hiệu để phát hiện xung đột.

Kỹ thuật này thường được gọi là compare-and-swap (CAS): so sánh giá trị hiện tại với giá trị kỳ vọng, và chỉ thay đổi dữ liệu nếu phép so sánh thành công. Trong cơ sở dữ liệu, phép so sánh và cập nhật phải nằm trong cùng một câu SQL để tránh khoảng thời gian giữa kiểm tra và ghi.

## 1. Vì sao cần kiểm tra số hàng bị tác động?

Giả sử hai người cùng mở một hồ sơ có phiên bản `version = 7`. Cả hai cùng đọc tên hiển thị là `An`. Người thứ nhất đổi thành `Anh`, người thứ hai đổi thành `An Nguyễn`.

Nếu cả hai cùng chạy câu lệnh chỉ có điều kiện `WHERE id = 42`, lần cập nhật thứ hai có thể ghi đè kết quả của lần thứ nhất. Ứng dụng không biết dữ liệu đã thay đổi kể từ lúc người thứ hai đọc.

Với khóa lạc quan, câu lệnh cập nhật thêm điều kiện `version = 7` và tăng version sau khi ghi:

```sql
UPDATE customer_profile
SET display_name = 'Anh',
    version = version + 1
WHERE id = 42
  AND version = 7;
```

Nếu chưa có transaction khác cập nhật, câu lệnh khớp một hàng, cập nhật tên và tăng version lên 8. Nếu một transaction khác đã cập nhật trước, version hiện tại không còn là 7; câu lệnh khớp không hàng nào và số hàng bị tác động bằng 0.

```text
Ban đầu: id=42, display_name='An', version=7

Transaction A đọc version=7       Transaction B đọc version=7
          |                                  |
          v                                  v
UPDATE ... WHERE version=7        UPDATE ... WHERE version=7
          |                                  |
          v                                  v
Tác động 1 hàng                   Tác động 0 hàng
version chuyển thành 8             vì version hiện tại đã là 8
          |                                  |
          v                                  v
Thành công                         Xung đột cần xử lý
```

Điều kiện version ngăn lần ghi sau âm thầm ghi đè dữ liệu mới. Cơ sở dữ liệu vẫn dùng khóa nội bộ trong lúc thực hiện `UPDATE`, nhưng ứng dụng không phải giữ khóa hàng từ thời điểm đọc đến thời điểm người dùng gửi thay đổi.

## 2. Mẫu SQL cơ bản: đọc version, cập nhật có điều kiện

Một bảng cần có cột phiên bản:

```sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

Ứng dụng đọc dữ liệu và version trong cùng một truy vấn:

```sql
SELECT id, display_name, version
FROM customer_profile
WHERE id = 42;
```

Giả sử kết quả là `display_name = 'An'`, `version = 7`. Khi lưu thay đổi, ứng dụng truyền lại version đã đọc:

```sql
UPDATE customer_profile
SET display_name = :new_name,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Ứng dụng đọc số hàng bị tác động:

| Số hàng | Diễn giải thông thường |
|---:|---|
| `1` | Đúng một hàng có id và version kỳ vọng; cập nhật thành công. |
| `0` | Không có hàng nào khớp. Hàng có thể đã bị cập nhật, bị xóa, không tồn tại hoặc không thỏa điều kiện khác. |
| Lớn hơn `1` | Điều kiện cập nhật không xác định duy nhất một bản ghi hoặc giả định về khóa duy nhất đã sai. Cần điều tra. |

Với `id` là khóa chính, kết quả lớn hơn 1 không nên xảy ra. Ứng dụng nên coi đây là dấu hiệu bất thường thay vì chấp nhận thành công.

Không nên chỉ kiểm tra `version` ở phía ứng dụng rồi mới chạy `UPDATE WHERE id = :id`. Giữa câu `SELECT` và câu `UPDATE`, transaction khác vẫn có thể cập nhật hàng. Điều kiện `id` và `version` trong chính câu `UPDATE` mới khiến phép kiểm tra và thay đổi trở thành một thao tác nguyên tử.

## 3. Ví dụ ngăn cập nhật ghi đè số lượng tồn kho

Một thao tác trừ tồn kho cần bảo đảm hai điều kiện: phiên bản chưa thay đổi và số lượng hiện tại đủ để xuất hàng.

```sql
UPDATE inventory
SET quantity = quantity - :amount,
    version = version + 1
WHERE product_id = :product_id
  AND version = :expected_version
  AND quantity >= :amount;
```

Giả sử ứng dụng đọc được `quantity = 10`, `version = 3` và cần trừ 4. Nếu không có cập nhật cạnh tranh, câu lệnh đổi số lượng thành 6 và version thành 4; số hàng bị tác động bằng 1.

Nếu một transaction khác đã bán hàng hoặc thay đổi tồn kho, version có thể đã thành 4. Câu lệnh với `expected_version = 3` tác động 0 hàng. Ứng dụng cần đọc lại số lượng và version, sau đó quyết định có thể tiếp tục hay cần từ chối nghiệp vụ.

Điều kiện `quantity >= :amount` cũng bảo vệ bất biến tồn kho ngay trong câu lệnh. Không nên chỉ đọc số lượng, kiểm tra ở Java rồi chạy câu `UPDATE` không có điều kiện, vì một giao dịch khác có thể thay đổi số lượng giữa hai bước.

Nếu nghiệp vụ chỉ cần trừ một lượng khỏi giá trị hiện tại mà không cần dựa trên một snapshot đã đọc trước đó, có thể dùng cập nhật số học nguyên tử với điều kiện tồn kho:

```sql
UPDATE inventory
SET quantity = quantity - :amount
WHERE product_id = :product_id
  AND quantity >= :amount;
```

Trong trường hợp này, số hàng bị tác động vẫn cho biết thao tác có thỏa điều kiện hay không. Tuy nhiên, đây là cập nhật có điều kiện nguyên tử, không phải phát hiện xung đột dựa trên version. Hai kỹ thuật có thể được kết hợp nếu nghiệp vụ cần cả hai.

## 4. Version phải thay đổi trong mọi lần ghi cạnh tranh

Một cột version chỉ hữu ích khi mọi đường cập nhật có thể làm thay đổi trạng thái được bảo vệ đều tăng version hoặc thay đổi một dấu mốc tương đương.

Ví dụ, nếu ứng dụng A cập nhật `display_name` và tăng version, nhưng một tác vụ nền B cập nhật `email` mà không tăng version, một ứng dụng khác có thể đọc version cũ rồi ghi dựa trên một trạng thái đã thay đổi mà không phát hiện được.

Các quy tắc cần giữ:

- Mọi lệnh cập nhật liên quan phải kiểm tra version cũ và tăng version mới.
- Các đường ghi qua batch job, SQL thủ công, stored procedure và tác vụ nền cũng phải tuân thủ quy tắc.
- Không cho phép client tự chọn version mới; ứng dụng hoặc database quản lý việc tăng version.
- Cột version nên `NOT NULL` và có kiểu đủ lớn để tránh tràn trong vòng đời dự kiến.
- Nếu dữ liệu được cập nhật từ nhiều ứng dụng, cần thống nhất cùng một giao thức version.

Có thể dùng timestamp làm dấu mốc, nhưng timestamp có thể có độ phân giải hữu hạn, giá trị trùng hoặc sai lệch do cách tạo thời gian. Một số nguyên tăng dần thường dễ kiểm soát hơn. Không dùng timestamp làm version nếu hệ thống không bảo đảm mỗi lần ghi tạo ra giá trị khác biệt.

## 5. Cách đọc số hàng bị tác động trong JDBC

JDBC trả về số hàng bị tác động từ `executeUpdate()` của `PreparedStatement`:

```java
String sql = """
    UPDATE customer_profile
       SET display_name = ?,
           version = version + 1
     WHERE id = ?
       AND version = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, newDisplayName);
    statement.setLong(2, customerId);
    statement.setLong(3, expectedVersion);

    int affectedRows = statement.executeUpdate();

    if (affectedRows == 1) {
        // Cập nhật thành công.
    } else if (affectedRows == 0) {
        // Không còn khớp với trạng thái đã đọc: xử lý xung đột.
    } else {
        throw new IllegalStateException(
            "Expected one updated row, got " + affectedRows
        );
    }
}
```

Ví dụ này giả định `id` là khóa chính. Trong ứng dụng thực tế, nên đặt phần cập nhật trong transaction phù hợp với các thao tác nghiệp vụ liên quan. Nếu có nhiều câu lệnh cần cùng thành công, số hàng không đúng kỳ vọng phải dẫn đến rollback toàn bộ transaction.

### Chú ý về ngữ nghĩa affected rows của driver

Không phải mọi database và driver đều định nghĩa số hàng giống nhau trong mọi trường hợp. Một số driver báo số hàng thực sự thay đổi; một số chế độ có thể báo số hàng khớp điều kiện. MySQL có khác biệt liên quan đến cờ `CLIENT_FOUND_ROWS` trong giao thức client.

Nếu câu lệnh cập nhật giá trị giống hệt giá trị cũ, một số cấu hình có thể trả về 0 dù hàng đã khớp. Để tránh nhầm trường hợp này với xung đột, mẫu optimistic locking thường tăng cột `version` trong cùng câu lệnh. Việc tăng version khiến một hàng khớp luôn có thay đổi thực tế ở cột version.

Hãy xác minh hành vi của JDBC driver và cấu hình kết nối đang dùng. Không nên thay đổi cấu hình driver mà không đánh giá các đoạn mã khác đang dựa vào số hàng bị tác động.

Với thao tác có thể tác động số lượng lớn, JDBC còn có `executeLargeUpdate()` trả về `long`. Với batch, `executeBatch()` trả về mảng số đếm; một số phần tử có thể là `Statement.SUCCESS_NO_INFO` hoặc `Statement.EXECUTE_FAILED`. Không được giả định mọi phần tử batch luôn là số nguyên không âm chính xác.

## 6. Xử lý xung đột trong Java

Một phương thức lưu có thể trả về kết quả thành công hoặc báo xung đột rõ ràng:

```java
public enum UpdateResult {
    UPDATED,
    CONFLICT
}

public UpdateResult updateProfile(
        Connection connection,
        long id,
        long expectedVersion,
        String newName
) throws SQLException {
    String sql = """
        UPDATE customer_profile
           SET display_name = ?,
               version = version + 1
         WHERE id = ?
           AND version = ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, newName);
        statement.setLong(2, id);
        statement.setLong(3, expectedVersion);

        int affected = statement.executeUpdate();
        if (affected == 1) {
            return UpdateResult.UPDATED;
        }
        if (affected == 0) {
            return UpdateResult.CONFLICT;
        }

        throw new SQLException(
            "Optimistic update affected an unexpected number of rows: " + affected
        );
    }
}
```

Trong hệ thống thật, kết quả `CONFLICT` cần được chuyển thành hành vi phù hợp với nghiệp vụ: thông báo người dùng tải lại dữ liệu, trả HTTP `409 Conflict`, hoặc yêu cầu người dùng hợp nhất thay đổi. Không nên tự động biến mọi trường hợp 0 hàng thành lỗi máy chủ chung chung.

Lưu ý rằng 0 hàng không chứng minh chắc chắn có người khác cập nhật. Hàng có thể đã bị xóa, id không tồn tại hoặc một điều kiện nghiệp vụ khác không còn đúng. Nếu ứng dụng cần phân biệt các trường hợp này, phải thiết kế quy trình kiểm tra bổ sung phù hợp với yêu cầu bảo mật và tính nhất quán. Một câu `SELECT` bổ sung sau khi nhận 0 chỉ cho biết trạng thái ở thời điểm truy vấn bổ sung, không thể tái dựng chắc chắn lịch sử xung đột.

## 7. Optimistic locking trong JPA với `@Version`

JPA hỗ trợ khóa lạc quan qua thuộc tính có annotation `@Version`. Provider sẽ đưa version cũ vào điều kiện cập nhật và tăng version khi ghi.

```java
@Entity
@Table(name = "customer_profile")
public class CustomerProfile {

    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Version
    private Long version;

    // getters/setters
}
```

Khi hai EntityManager đọc cùng một entity ở version 7, lần flush đầu tiên có thể tạo câu SQL tương đương:

```sql
UPDATE customer_profile
SET display_name = ?,
    version = 8
WHERE id = ?
  AND version = 7;
```

Nếu câu lệnh không cập nhật được đúng hàng mong đợi, JPA provider phát hiện optimistic lock conflict và ném ngoại lệ như `OptimisticLockException`. Trong Spring, lỗi có thể được chuyển thành một ngoại lệ thuộc nhóm `ObjectOptimisticLockingFailureException` tùy lớp truy cập dữ liệu và cách dịch ngoại lệ.

```java
@Transactional
public void renameProfile(Long id, String newName) {
    CustomerProfile profile = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Profile not found"));

    profile.setDisplayName(newName);
    // Dirty checking sẽ phát hiện thay đổi và ghi khi flush/commit.
}
```

Ứng dụng không cần tự đọc số hàng bị tác động cho thao tác entity thông thường; provider thực hiện việc kiểm tra. Tuy nhiên, cần hiểu rằng ngoại lệ có thể xuất hiện tại `flush()` hoặc lúc transaction commit, chứ không nhất thiết ngay tại lệnh gọi `save()`.

Nếu muốn phát hiện sớm hơn trong một luồng xử lý, có thể gọi `entityManager.flush()` sau khi thay đổi. Điều này đẩy SQL xuống database tại thời điểm đó, nhưng transaction vẫn có thể thất bại ở commit vì các nguyên nhân khác.

### Bulk update không tự động có cùng hành vi với `@Version`

Các JPQL bulk update hoặc native SQL update thường bỏ qua persistence context và cơ chế dirty checking của entity. Không nên giả định rằng một bulk update tự động áp dụng `@Version` giống cập nhật từng entity.

Ví dụ JPQL có thể đưa version vào điều kiện và tăng version tường minh:

```java
int affected = entityManager.createQuery("""
    update CustomerProfile p
       set p.displayName = :name,
           p.version = p.version + 1
     where p.id = :id
       and p.version = :expectedVersion
    """)
    .setParameter("name", newName)
    .setParameter("id", id)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();

if (affected == 0) {
    throw new OptimisticLockException("Profile was changed or removed");
}
if (affected != 1) {
    throw new IllegalStateException("Unexpected update count: " + affected);
}
```

Sau bulk update, persistence context có thể đang giữ entity cũ. Cân nhắc `clear()` hoặc `refresh()` theo phạm vi phù hợp để tránh đọc lại dữ liệu stale từ bộ nhớ. Thao tác bulk cần được thiết kế và kiểm thử riêng với cơ chế version của provider.

## 8. Kiểm tra số hàng cho DELETE và nhiều hàng

Khóa lạc quan cũng áp dụng cho xóa một hàng:

```sql
DELETE FROM customer_profile
WHERE id = :id
  AND version = :expected_version;
```

- Tác động 1 hàng: hàng đúng version đã được xóa.
- Tác động 0 hàng: hàng không tồn tại, đã bị xóa hoặc version không còn khớp.

Với cập nhật hàng loạt, số hàng bị tác động cần được so sánh với số lượng kỳ vọng nếu nghiệp vụ yêu cầu tất cả mục tiêu phải được cập nhật:

```sql
UPDATE orders
SET status = 'ARCHIVED',
    version = version + 1
WHERE status = 'COMPLETED'
  AND version = :expected_version;
```

Nếu ứng dụng dự kiến cập nhật 100 hàng nhưng kết quả chỉ là 97, ba hàng còn lại có thể đã thay đổi hoặc không còn thỏa điều kiện. Nếu quy trình đòi hỏi toàn bộ 100 hàng phải thành công, ứng dụng phải rollback transaction khi số đếm không đúng kỳ vọng. Nếu nghiệp vụ cho phép cập nhật một phần, cần trả về danh sách hoặc cách xác định những hàng thất bại để xử lý tiếp.

Một điều kiện version duy nhất cho nhiều hàng thường không đủ để bảo vệ từng hàng độc lập. Nếu mỗi hàng có version riêng, câu lệnh phải so sánh version tương ứng cho từng hàng, hoặc ứng dụng cần cập nhật từng hàng/batch với cặp id-version cụ thể. Đừng dùng một con số affected rows tổng cộng để kết luận rằng mọi bản ghi đều được ghi theo đúng version kỳ vọng.

### JDBC batch và kết quả không xác định

Khi dùng `executeBatch()`, driver trả về một mảng kết quả tương ứng với các lệnh trong batch nếu batch hoàn tất theo cách thông thường. Các giá trị có thể gồm:

| Giá trị | Ý nghĩa |
|---|---|
| Số nguyên không âm | Số hàng bị tác động theo ngữ nghĩa của driver cho lệnh đó. |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Lệnh thành công nhưng driver không biết chính xác số hàng. |
| `Statement.EXECUTE_FAILED` (`-3`) | Lệnh tương ứng thất bại trong kết quả batch được trả về. |

Driver cũng có thể ném `BatchUpdateException`; phương thức `getUpdateCounts()` cung cấp phần kết quả mà driver báo được. Cách batch dừng hoặc tiếp tục sau lỗi phụ thuộc driver và database. Nếu cần xác nhận từng hàng đã vượt qua optimistic lock, hãy chọn cách thực thi và driver có thể cung cấp số đếm đủ chính xác; không coi `SUCCESS_NO_INFO` là bằng chứng mọi hàng khớp version.

## 9. Xung đột khác gì với deadlock và serialization failure?

Số hàng bị tác động bằng 0 là một cách ứng dụng nhận biết điều kiện cập nhật không còn đúng. Nó khác với các lỗi đồng thời khác:

| Hiện tượng | Cách nhận biết | Cách xử lý |
|---|---|---|
| Optimistic conflict | `UPDATE ... WHERE version = ?` tác động 0 hàng | Đọc lại, hợp nhất hoặc yêu cầu người dùng quyết định |
| Deadlock | Database chọn một transaction làm nạn nhân và trả lỗi deadlock | Rollback transaction và retry có giới hạn nếu thao tác an toàn |
| Serialization failure | Database báo transaction không thể hoàn tất ở isolation level yêu cầu | Rollback và chạy lại toàn bộ transaction theo quy tắc ứng dụng |
| Constraint violation | Vi phạm unique, foreign key, check hoặc ràng buộc khác | Xử lý lỗi nghiệp vụ hoặc dữ liệu đầu vào |

Một câu lệnh optimistic update có thể vẫn gặp deadlock hoặc serialization failure. Kiểm tra row count không thay thế xử lý các lỗi mà database trả về.

## 10. Phạm vi transaction khi phát hiện xung đột

Khi câu lệnh cập nhật trả về 0, transaction hiện tại có thể chưa gặp lỗi SQL. Ứng dụng phải chủ động quyết định kết quả đó có làm toàn bộ nghiệp vụ thất bại hay không.

Giả sử một thao tác chuyển đơn hàng cần cập nhật cả bảng `orders` và ghi một dòng vào `audit_log`. Nếu cập nhật `orders` thất bại do version không khớp, ứng dụng không được commit audit record mô tả rằng thao tác đã thành công.

```text
BEGIN
  UPDATE orders WHERE id=? AND version=?
       |
       +-- affected = 1 --> INSERT audit_log --> COMMIT
       |
       +-- affected = 0 --> ROLLBACK --> báo xung đột
```

Trong Java, nên để ngoại lệ hoặc kết quả lỗi đi qua ranh giới transaction để transaction manager rollback. Với Spring `@Transactional`, cần chú ý quy tắc rollback theo loại exception và không bắt rồi nuốt lỗi bên trong phương thức nếu muốn transaction rollback.

Nếu ứng dụng chỉ trả `CONFLICT` nhưng transaction có các thay đổi khác đã thực hiện trước đó, cần rollback các thay đổi đó trước khi trả kết quả. Không để một phần thao tác nghiệp vụ được commit vô tình.

## 11. Xử lý sau khi phát hiện xung đột

Khi số hàng bị tác động bằng 0, có một số lựa chọn:

1. **Tải lại và yêu cầu người dùng xác nhận:** phù hợp với biểu mẫu chỉnh sửa, nơi người dùng cần xem các thay đổi mới nhất trước khi ghi tiếp.
2. **Hợp nhất thay đổi:** nếu các trường người dùng sửa không xung đột về mặt nghiệp vụ, ứng dụng có thể kết hợp thay đổi trên phiên bản mới, nhưng phải đánh giá lại các quy tắc nghiệp vụ.
3. **Retry có giới hạn:** phù hợp với thao tác có thể tính lại an toàn từ trạng thái mới, ví dụ cập nhật một bộ đếm theo phép cộng nguyên tử. Mỗi lần thử phải đọc lại dữ liệu và version mới.
4. **Từ chối thao tác:** phù hợp khi dữ liệu đã chuyển sang trạng thái không cho phép sửa hoặc xóa.

Không nên tự động đọc version mới rồi gửi lại nguyên giá trị cũ mà không xem xét ý nghĩa nghiệp vụ. Làm vậy chỉ biến xung đột được phát hiện thành một lần ghi đè có chủ ý của ứng dụng.

Retry cần có giới hạn số lần, backoff phù hợp và bảo đảm tính idempotent của các tác dụng phụ. Nếu transaction đã gửi email, phát sự kiện hoặc gọi dịch vụ ngoài database trước khi phát hiện xung đột, chạy lại toàn bộ phương thức có thể gửi lặp. Hãy trì hoãn tác dụng phụ đến sau commit hoặc dùng transactional outbox/idempotency key khi cần bảo đảm giao nhận.

## 12. Các giới hạn và trường hợp cần chú ý

### Không có version predicate thì row count không phát hiện được ghi đè

`UPDATE customer_profile SET display_name = ? WHERE id = ?` thường tác động một hàng dù một transaction khác vừa sửa dữ liệu. Số hàng bằng 1 chỉ chứng minh hàng khớp điều kiện SQL; nó không chứng minh dữ liệu vẫn ở version mà ứng dụng đã đọc.

### Điều kiện nghiệp vụ cũng có thể làm count bằng 0

Nếu câu lệnh có `AND status = 'DRAFT'`, kết quả 0 có thể do status đã chuyển sang `SUBMITTED`, dù version không thay đổi. Ứng dụng cần phân loại đây là trạng thái nghiệp vụ không còn hợp lệ hay xung đột dữ liệu.

### Một hàng có thể không tồn tại

Khi `UPDATE` trả 0, không thể mặc định thông báo “người khác vừa sửa”. Hàng có thể đã bị xóa, chưa từng tồn tại hoặc bị lọc bởi điều kiện phân quyền. Trong hệ thống nhiều tenant, việc phân biệt tồn tại/không tồn tại cần cân nhắc tránh tiết lộ dữ liệu của tenant khác.

### Trigger và driver có thể ảnh hưởng cách diễn giải

Số đếm được trả về là theo ngữ nghĩa của câu lệnh và driver. Trigger có thể thực hiện thêm thao tác; các hệ quản trị có quy tắc khác nhau về số hàng được báo. Cần kiểm tra tài liệu của database/driver nếu trigger, stored procedure hoặc câu lệnh nhiều bước tham gia vào cập nhật.

### Version có thể bị tái sử dụng hoặc quay ngược

Nếu version bị đặt lại về giá trị cũ, một client cũ có thể vô tình khớp lại dấu mốc đã đọc. Đây là dạng vấn đề ABA. Dùng version tăng đơn điệu, không tái sử dụng và không cho phép client tự ghi version giúp giảm nguy cơ.

## 13. Quy trình triển khai khóa lạc quan

1. Chọn đối tượng cần bảo vệ và xác định mọi đường ghi có thể thay đổi đối tượng đó.
2. Thêm cột version `NOT NULL` hoặc dấu mốc có tính duy nhất theo từng lần cập nhật.
3. Trả version cùng dữ liệu khi đọc; giữ version này trong DTO hoặc trạng thái biểu mẫu.
4. Thêm điều kiện `AND version = :expectedVersion` vào câu `UPDATE` hoặc `DELETE`.
5. Tăng version ngay trong cùng câu lệnh thành công.
6. Kiểm tra số hàng bị tác động: một hàng là thành công với khóa duy nhất; không hàng nào là xung đột hoặc điều kiện không còn khớp; nhiều hơn một hàng là bất thường.
7. Rollback các thay đổi liên quan nếu kết quả không đúng kỳ vọng.
8. Trả lỗi xung đột có ý nghĩa cho tầng gọi và thiết kế cách tải lại, hợp nhất hoặc retry.
9. Kiểm thử hai transaction cùng đọc một version rồi ghi đồng thời; xác nhận chỉ một lần cập nhật thành công.
10. Kiểm tra driver, trigger, batch update và các tác vụ nền để bảo đảm số đếm được diễn giải đúng.

## 14. Tự kiểm tra

**Vì sao câu `UPDATE` có `WHERE id = ?` nhưng không có version predicate không đủ để phát hiện xung đột?**

Vì hàng vẫn tồn tại và khớp id sau khi transaction khác cập nhật. Câu lệnh có thể tác động một hàng và ghi đè giá trị mới mà không biết client đang dùng dữ liệu cũ.

**`UPDATE ... WHERE id = ? AND version = ?` trả về 0 có luôn có nghĩa người khác đã sửa hàng không?**

Không. Hàng có thể đã bị xóa, không tồn tại hoặc không thỏa một điều kiện khác. Cần diễn giải theo toàn bộ predicate và yêu cầu nghiệp vụ.

**Vì sao nên tăng version trong câu UPDATE?**

Việc tăng version tạo dấu mốc mới cho lần ghi thành công tiếp theo. Nó cũng giúp tránh trường hợp driver báo 0 cho một hàng khớp nhưng các giá trị nghiệp vụ không thay đổi.

**JPA báo optimistic lock exception ở thời điểm nào?**

Ngoại lệ thường xuất hiện khi provider flush SQL hoặc khi transaction commit; không nhất thiết xuất hiện ngay tại lời gọi `save()`.

**Có nên retry ngay với version mới mà không đọc lại và tính lại nghiệp vụ không?**

Không. Cần đọc trạng thái mới, đánh giá lại thay đổi và chỉ retry nếu thao tác vẫn hợp lệ, an toàn và không lặp tác dụng phụ.

Khóa lạc quan dựa vào một quy tắc đơn giản: **chỉ ghi nếu dữ liệu vẫn ở phiên bản mà ứng dụng đã đọc**. Câu SQL mang điều kiện version thực hiện phép so sánh nguyên tử; số hàng bị tác động cho biết phép so sánh có thành công hay không. Ứng dụng cần biến kết quả đó thành quyết định nghiệp vụ rõ ràng và giữ toàn bộ thay đổi liên quan trong ranh giới transaction thích hợp.
