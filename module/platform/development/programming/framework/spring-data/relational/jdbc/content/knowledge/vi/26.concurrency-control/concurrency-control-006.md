# Giới hạn @Lock với @Query và lựa chọn khóa bằng SQL

## 1. Vì sao cần khóa khi nhiều transaction cùng truy cập dữ liệu?

Giả sử một sản phẩm còn 5 đơn vị tồn kho. Hai request gần như đồng thời muốn đặt mỗi request 4 đơn vị:

~~~text
Transaction A                         Transaction B
-------------                         -------------
SELECT available = 5
                                      SELECT available = 5
Kiểm tra 5 >= 4
                                      Kiểm tra 5 >= 4
UPDATE available = 1
                                      UPDATE available = 1
COMMIT                                COMMIT
~~~

Nếu ứng dụng đọc giá trị trước, kiểm tra trong Java rồi ghi lại một giá trị được tính từ dữ liệu cũ, hai request có thể cùng vượt qua điều kiện. Đây là một dạng race condition trong quy trình read-modify-write.

Database cung cấp cơ chế khóa để điều phối những transaction đồng thời. Với Spring Data JDBC, có hai hướng thường gặp:

- Dùng @Lock trên **derived query method** để Spring Data tạo câu SELECT có lock clause theo dialect.
- Viết lock clause trực tiếp trong SQL của @Query hoặc JdbcTemplate khi cần một truy vấn SQL tường minh.

Có một giới hạn quan trọng: **Spring Data JDBC hiện không áp dụng @Lock cho query method khai báo bằng @Query dạng chuỗi**. Nếu đặt cả hai annotation trên cùng method, thông tin khóa từ @Lock bị bỏ qua và Spring ghi cảnh báo. Vì vậy, khi đã dùng @Query, hãy đưa cú pháp khóa vào câu SQL nếu database hỗ trợ.

Bài này giải thích giới hạn đó, cách chọn PESSIMISTIC_READ và PESSIMISTIC_WRITE, cách viết FOR UPDATE/FOR SHARE, vòng đời khóa trong transaction và các lựa chọn khác như optimistic locking hoặc conditional UPDATE.

## 2. Pessimistic locking trong Spring Data JDBC

Pessimistic locking giả định rằng có thể xảy ra cạnh tranh và yêu cầu database khóa dữ liệu trong lúc transaction đang xử lý. Transaction khác muốn sửa hoặc khóa cùng hàng có thể phải chờ, hoặc nhận lỗi tùy câu lệnh và cấu hình database.

Spring Data JDBC cung cấp hai lock mode:

| Lock mode | Ý nghĩa |
| --- | --- |
| PESSIMISTIC_READ | Yêu cầu khóa đọc; mục đích là ngăn transaction khác sửa dữ liệu đang được đọc trong thời gian khóa còn hiệu lực. |
| PESSIMISTIC_WRITE | Yêu cầu khóa ghi; phù hợp với quy trình đọc rồi cập nhật dữ liệu. |

Một số database không phân biệt rõ hai mode này; dialect có thể ánh xạ cả hai về dạng khóa ghi. Do đó, tên mode biểu đạt ý định của ứng dụng, còn hành vi thực tế phụ thuộc database và dialect.

Các kiểu Spring Data JDBC dùng trong ví dụ nằm ở package:

~~~java
import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;
~~~

Đây là API của Spring Data Relational. Không nhầm Lock/LockMode này với jakarta.persistence.LockModeType hoặc annotation khóa của Spring Data JPA.

## 3. @Lock được hỗ trợ trên derived query method

Một derived query method được suy diễn từ tên method, chẳng hạn findBySku. Spring Data JDBC phân tích property và tạo SQL. Khi method có @Lock, framework thêm lock clause phù hợp với dialect.

Ví dụ:

~~~java
import java.util.Optional;

import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;
import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Lock(LockMode.PESSIMISTIC_WRITE)
    Optional<Inventory> findBySku(String sku);
}
~~~

Method findBySku là derived query vì không khai báo SQL bằng @Query. Spring Data JDBC tạo câu SELECT dựa trên mapping và thêm khóa ghi theo dialect.

Có thể dùng PESSIMISTIC_READ nếu use case chỉ cần đọc một hàng và muốn ngăn transaction khác sửa hàng đó trong lúc transaction hiện tại còn giữ khóa:

~~~java
@Lock(LockMode.PESSIMISTIC_READ)
Optional<Inventory> findForInspectionBySku(String sku);
~~~

Nếu cần hai chế độ khóa khác nhau, hãy đặt tên method riêng hoặc chọn một mode theo use case. Các method trên đều là derived query; phần property sau By vẫn phải khớp domain property.

### 3.1. SQL được tạo phụ thuộc dialect

Spring Data JDBC dùng dialect để biểu diễn lock mode. Tài liệu Spring Data Relational đưa ví dụ MySQL cho PESSIMISTIC_READ với cú pháp:

~~~sql
SELECT *
FROM user
WHERE lastname = ?
LOCK IN SHARE MODE;
~~~

Đây là ví dụ minh họa từ dialect/tài liệu, không phải cú pháp dùng chung cho mọi database. Một dialect khác có thể dùng FOR SHARE, FOR UPDATE hoặc dạng cú pháp riêng.

Không nên suy luận rằng mọi database đều tạo ra cùng một chuỗi SQL hoặc PESSIMISTIC_READ luôn nhẹ hơn PESSIMISTIC_WRITE. Hãy kiểm tra SQL được sinh và tài liệu của database đang triển khai.

## 4. Giới hạn quan trọng: @Lock bị bỏ qua trên @Query dạng chuỗi

Đây là điểm dễ nhầm khi chuyển từ Spring Data JPA hoặc từ derived query sang query SQL tùy chỉnh.

Ví dụ sau không tạo ra khóa như mong đợi:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
@Query("SELECT id, sku, available FROM inventory WHERE sku = :sku")
Optional<Inventory> findForUpdate(@Param("sku") String sku);
~~~

Method trên là string-based query vì có @Query. Theo tài liệu Spring Data Relational hiện hành, @Lock không được hỗ trợ trên string-based query. Query method vẫn chạy câu SQL đã khai báo, nhưng lock mode từ @Lock bị bỏ qua; framework ghi warning trong log. Tài liệu cũng nêu các phiên bản tương lai có thể chuyển trường hợp này thành exception.

Vì vậy, không dựa vào annotation @Lock để bảo vệ một câu SQL @Query. Nếu muốn dùng @Query, hãy viết lock clause trực tiếp trong SQL:

~~~java
@Query("SELECT id, sku, available FROM inventory WHERE sku = :sku FOR UPDATE")
Optional<Inventory> findForUpdate(@Param("sku") String sku);
~~~

Trong ví dụ này, khóa đến từ FOR UPDATE của database. Không cần thêm @Lock; SQL đã mô tả rõ hành vi khóa.

### 4.1. Phân biệt hai cơ chế

| Khai báo | Spring Data JDBC xử lý khóa thế nào? |
| --- | --- |
| Derived method + @Lock | Được hỗ trợ; Spring Data tạo lock clause theo dialect. |
| @Query dạng chuỗi + @Lock | Lock metadata bị bỏ qua; có warning theo tài liệu hiện hành. |
| @Query có FOR UPDATE trong SQL | Database thực hiện khóa theo cú pháp SQL và transaction. |
| JdbcTemplate với SQL có FOR UPDATE | Database thực hiện khóa theo cú pháp SQL và transaction. |

Không áp dụng kết luận này cho Spring Data JPA. Spring Data JPA có cơ chế lock metadata khác; bài này nói về Spring Data JDBC.

## 5. Khóa bằng SQL trong @Query

Khi cần SQL tường minh, dùng FOR UPDATE trong câu SELECT nếu database hỗ trợ.

Repository:

~~~java
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Query("SELECT id, sku, available FROM inventory WHERE sku = :sku FOR UPDATE")
    Optional<Inventory> findForUpdate(@Param("sku") String sku);
}
~~~

Service giữ transaction trong suốt thời gian đọc và cập nhật:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Inventory item = inventory.findForUpdate(sku)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown SKU: " + sku));

        if (item.available() < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }

        inventory.save(item.withAvailable(item.available() - quantity));
    }
}
~~~

Luồng thực thi:

1. Spring mở transaction khi service method được gọi qua transaction proxy.
2. Câu SELECT có FOR UPDATE đọc hàng và yêu cầu database khóa hàng phù hợp.
3. Transaction khác muốn sửa hoặc khóa cùng hàng có thể phải chờ.
4. Service kiểm tra số lượng và lưu trạng thái mới.
5. Khi transaction commit hoặc rollback, database giải phóng khóa.

Các phương thức withAvailable và mapping Inventory là ví dụ domain; cần thay bằng model thực tế. Điểm quan trọng là câu SELECT khóa và câu UPDATE phải chạy trong cùng transaction.

### 5.1. Nếu dùng JdbcTemplate

Khi truy vấn cần SQL đặc thù hoặc không phù hợp với repository method, có thể dùng NamedParameterJdbcTemplate:

~~~java
@Repository
public class InventoryLockDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventoryLockDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public InventoryRow findForUpdate(String sku) {
        String sql = """
                SELECT id, sku, available
                FROM inventory
                WHERE sku = :sku
                FOR UPDATE
                """;

        return jdbc.queryForObject(
                sql,
                Map.of("sku", sku),
                (rs, rowNum) -> new InventoryRow(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getInt("available")
                )
        );
    }
}
~~~

Gọi DAO từ service có @Transactional và cùng DataSource/transaction manager. Không tạo một connection độc lập rồi đóng nó ngay sau câu SELECT nếu muốn giữ khóa cho bước cập nhật tiếp theo.

## 6. SQL lock clause khác nhau theo database

FOR UPDATE phổ biến nhưng không phải cú pháp đồng nhất trên mọi hệ quản trị. Ví dụ:

### PostgreSQL

~~~sql
SELECT id, sku, available
FROM inventory
WHERE sku = :sku
FOR UPDATE;
~~~

PostgreSQL còn hỗ trợ các biến thể như FOR NO KEY UPDATE, FOR SHARE và FOR KEY SHARE. Chúng có mức xung đột khóa khác nhau; chọn theo loại thay đổi cần ngăn chặn.

### MySQL với InnoDB

~~~sql
SELECT id, sku, available
FROM inventory
WHERE sku = :sku
FOR UPDATE;
~~~

MySQL 8 hỗ trợ FOR SHARE cho khóa đọc. Các phiên bản cũ từng dùng LOCK IN SHARE MODE. Kiểm tra phiên bản MySQL, storage engine và cú pháp được hỗ trợ.

### SQL Server

SQL Server thường biểu đạt locking bằng table hints, chẳng hạn:

~~~sql
SELECT id, sku, available
FROM inventory WITH (UPDLOCK, ROWLOCK)
WHERE sku = @sku;
~~~

UPDLOCK yêu cầu update lock khi đọc; ROWLOCK là hint về phạm vi khóa, không phải cam kết tuyệt đối rằng engine luôn chỉ khóa đúng từng row. Cú pháp parameter và hint phụ thuộc SQL Server.

### Oracle

Oracle hỗ trợ SELECT ... FOR UPDATE, đồng thời có các lựa chọn như NOWAIT và SKIP LOCKED theo cú pháp của phiên bản database.

Những ví dụ này chỉ minh họa cách database biểu đạt locking. Câu SQL phải được viết theo dialect thực tế; không sao chép nguyên câu SQL của một database sang database khác mà không kiểm tra.

## 7. NOWAIT và SKIP LOCKED

Một số database cho phép điều khiển cách xử lý khi hàng đã bị transaction khác khóa.

### 7.1. NOWAIT

NOWAIT yêu cầu truy vấn không chờ khóa đang bị giữ. Nếu không lấy được khóa ngay, database trả lỗi thay vì đợi đến khi transaction kia kết thúc.

Ví dụ trên PostgreSQL:

~~~sql
SELECT id, status
FROM jobs
WHERE id = :id
FOR UPDATE NOWAIT;
~~~

Phù hợp khi ứng dụng muốn trả thông báo “đang được xử lý” hoặc thử lại sau, thay vì để request chờ lâu. Cần bắt và phân loại lỗi lock conflict theo database/driver.

### 7.2. SKIP LOCKED

SKIP LOCKED bỏ qua những hàng hiện đang bị transaction khác khóa. Đây là lựa chọn hữu ích cho worker queue, nơi nhiều worker lấy các job khác nhau:

~~~sql
SELECT id, payload
FROM jobs
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

Thứ tự LIMIT và lock clause có thể khác theo dialect; ví dụ trên cần điều chỉnh theo database cụ thể. Một worker lấy các hàng chưa bị khóa, cập nhật trạng thái và commit. Worker khác có thể lấy những hàng khác mà không phải chờ các hàng đã được worker trước giữ.

SKIP LOCKED cố ý tạo ra một góc nhìn không đầy đủ: hàng đang bị khóa sẽ không xuất hiện trong kết quả của truy vấn đó. Vì vậy, không dùng nó cho màn hình cần danh sách đầy đủ hoặc truy vấn kiểm tra tồn tại thông thường. Nó phù hợp hơn với queue/claim-work pattern có retry và cơ chế phục hồi job bị bỏ dở.

## 8. Transaction quyết định vòng đời khóa

Một câu SELECT có lock clause thường chỉ giữ khóa trong thời gian transaction. Nếu database chạy autocommit và câu SELECT kết thúc cùng statement, khóa có thể được giải phóng ngay sau statement; service không còn được bảo vệ trong bước cập nhật tiếp theo.

Do đó, cần đặt transaction bao trùm toàn bộ critical section:

~~~java
@Transactional
public void updateInventory(String sku, int quantity) {
    Inventory item = dao.findForUpdate(sku);
    // Kiểm tra điều kiện.
    // Thực hiện cập nhật.
}
~~~

Tránh tách việc lấy khóa và cập nhật thành hai service call có transaction riêng:

~~~text
Service A: mở transaction
  SELECT ... FOR UPDATE
Service A: commit, khóa được giải phóng

Service B: mở transaction khác
  UPDATE inventory
Service B: commit
~~~

Giữa hai transaction, một request khác có thể thay đổi hàng. Khóa không còn bảo vệ khoảng thời gian giữa lần đọc và lần ghi.

### 8.1. Gọi qua Spring proxy

@Transactional trong cấu hình proxy thông thường chỉ áp dụng khi lời gọi đi qua Spring proxy. Self-invocation, tức một method trong cùng object gọi trực tiếp method khác có annotation, có thể không mở transaction như dự kiến.

Hãy đặt transaction ở public application service method được gọi từ bean khác, hoặc dùng cách cấu hình transaction phù hợp với kiến trúc ứng dụng.

### 8.2. Không giữ khóa trong lúc gọi dịch vụ ngoài

Không nên giữ row lock trong khi chờ HTTP API, gửi email hoặc xử lý file lớn:

~~~java
@Transactional
public void approve(Long id) {
    Order order = orders.findForUpdate(id).orElseThrow();
    remoteBilling.capture(order); // Có thể mất nhiều giây.
    orders.save(order.approve());
}
~~~

Lời gọi bên ngoài kéo dài sẽ giữ connection, transaction và lock lâu hơn cần thiết. Điều này làm tăng lock contention và nguy cơ timeout/deadlock. Với workflow nhiều hệ thống, cân nhắc cập nhật trạng thái/outbox trong transaction ngắn rồi xử lý side effect sau commit.

## 9. Khóa SQL khóa hàng nào?

Một câu SELECT ... FOR UPDATE khóa các hàng mà database thực sự chọn theo semantics và execution plan của nó. Không nên suy luận rằng khóa một aggregate root tự động khóa mọi hàng trong aggregate.

Ví dụ aggregate có:

~~~text
PurchaseOrder (root row)
  |
  +-- purchase_order_lines (child rows)
  |
  +-- order_notes (child rows)
~~~

Nếu query chỉ chọn hàng từ purchase_orders, database lock clause có thể chỉ khóa hàng root. Các bảng con không tự động được khóa chỉ vì Spring Data JDBC ánh xạ chúng thành một aggregate.

Nếu nghiệp vụ cần bảo vệ cả nhiều hàng:

- Khóa các hàng liên quan bằng câu lệnh phù hợp.
- Dùng thứ tự khóa ổn định giữa các transaction.
- Cân nhắc cập nhật/kiểm tra bằng constraint hoặc một câu SQL nguyên tử.
- Thiết kế lại aggregate boundary nếu nhiều transaction thường xuyên phải sửa nhiều phần dữ liệu cùng lúc.

Phạm vi khóa thực tế còn phụ thuộc index, isolation level và engine. Chẳng hạn InnoDB có thể dùng record lock, gap lock hoặc next-key lock trong một số truy vấn/range predicate. Không coi row lock là cam kết luôn chỉ khóa đúng một row vật lý.

## 10. Khóa nhiều hàng và tránh deadlock

Deadlock có thể xảy ra khi hai transaction lấy các khóa theo thứ tự ngược nhau:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Lock row 1                    Lock row 2
Request lock row 2            Request lock row 1
Wait                          Wait
~~~

Database phát hiện vòng chờ và hủy một transaction để giải phóng deadlock. Để giảm nguy cơ:

1. Khóa các hàng theo cùng một thứ tự, ví dụ ID tăng dần.
2. Giữ transaction ngắn.
3. Chỉ khóa đúng phạm vi dữ liệu cần thiết.
4. Tạo index cho điều kiện tìm hàng để tránh quét và khóa quá rộng.
5. Không thực hiện network I/O khi đang giữ khóa.
6. Theo dõi lock wait, deadlock và thời gian transaction trong production.

Không phải mọi deadlock đều có thể loại bỏ hoàn toàn. Nếu retry, chỉ retry lỗi transient phù hợp, giới hạn số lần và dùng backoff. Use case cần idempotent để một lần thử lại không tạo tác dụng phụ trùng lặp.

## 11. Khi nào nên dùng pessimistic lock?

Pessimistic locking phù hợp khi:

- Một transaction phải đọc rồi cập nhật một hoặc một nhóm hàng.
- Xung đột xảy ra tương đối thường xuyên.
- Việc để hai transaction cùng vượt qua bước kiểm tra có thể gây lỗi nghiệp vụ.
- Có thể giữ transaction ngắn trong critical section.

Ví dụ: giữ chỗ tồn kho, chuyển trạng thái một job đang được claim hoặc cập nhật một tài nguyên có số lượng giới hạn.

Không nên khóa pessimistic cho mọi truy vấn đọc. Khóa làm giảm concurrency và có thể khiến request khác chờ. Với một màn hình chỉ đọc dữ liệu để hiển thị, thường không cần khóa; với cập nhật ít xung đột, optimistic locking có thể phù hợp hơn.

## 12. Các lựa chọn khác ngoài SELECT FOR UPDATE

Khóa pessimistic không phải giải pháp duy nhất cho mọi race condition.

### 12.1. Optimistic locking với @Version

Spring Data JDBC hỗ trợ optimistic locking bằng thuộc tính số trên aggregate root được đánh dấu @Version:

~~~java
@Table("inventory")
public record Inventory(
        @Id Long id,
        String sku,
        int available,
        @Version Long version
) {
}
~~~

Khi lưu aggregate, Spring Data JDBC kiểm tra version hiện tại trong database. Nếu một transaction khác đã cập nhật hàng, thao tác save có thể ném OptimisticLockingFailureException thay vì âm thầm ghi đè.

Optimistic locking phù hợp khi xung đột hiếm và ứng dụng có thể yêu cầu caller tải lại dữ liệu hoặc retry use case.

### 12.2. Conditional UPDATE

Với thao tác giảm tồn kho, có thể không cần đọc rồi khóa riêng:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku
  AND available >= :quantity;
~~~

Service kiểm tra số hàng bị ảnh hưởng:

- 1: cập nhật thành công.
- 0: SKU không tồn tại hoặc số lượng không đủ.

Database kiểm tra điều kiện và cập nhật trong một statement. Đây thường là lựa chọn gọn và hiệu quả cho một phép biến đổi đơn giản có điều kiện.

### 12.3. So sánh lựa chọn

| Cơ chế | Cách phát hiện/điều phối xung đột | Phù hợp khi |
| --- | --- | --- |
| PESSIMISTIC_WRITE / FOR UPDATE | Khóa trước khi đọc/sửa; transaction khác có thể phải chờ | Xung đột tương đối thường xuyên, critical section ngắn |
| PESSIMISTIC_READ / FOR SHARE | Khóa đọc theo khả năng database | Cần ngăn thay đổi trong khi đọc và dialect có semantics phù hợp |
| @Version | Phát hiện version đã đổi khi save | Xung đột hiếm, có thể xử lý retry/reload |
| Conditional UPDATE | Điều kiện và thay đổi diễn ra trong một statement | Một phép cập nhật nguyên tử có predicate rõ |
| Unique/check/foreign key constraint | Database từ chối trạng thái vi phạm ràng buộc | Bất biến có thể biểu diễn bằng schema constraint |

Có thể kết hợp các cơ chế. Ví dụ, unique constraint bảo đảm không có hai reservation trùng khóa nghiệp vụ; transaction và conditional update bảo vệ phép giảm tồn; @Version phát hiện ghi cạnh tranh ở các luồng cập nhật aggregate khác.

## 13. Lưu ý với @Lock và transaction của repository

Khóa chỉ có ý nghĩa trong khoảng thời gian database giữ nó. Một repository method trả về entity đã đọc không có nghĩa khóa sẽ tiếp tục tồn tại sau khi transaction kết thúc.

Với derived query có @Lock, nên gọi từ một service có @Transactional bao trùm các thao tác tiếp theo:

~~~java
@Service
public class AccountService {

    private final AccountRepository accounts;

    public AccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void debit(Long id, BigDecimal amount) {
        Account account = accounts.findForUpdate(id)
                .orElseThrow();

        if (account.balance().compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient balance");
        }

        accounts.save(account.debit(amount));
    }
}
~~~

Method repository:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<Account> findForUpdateById(Long id);
~~~

Method trên là derived query nếu property path được parser nhận diện và không có @Query string. Nếu cần viết SQL riêng, dùng @Query với lock clause trong SQL thay cho việc gắn @Lock.

## 14. Kiểm thử locking bằng database thật

Unit test đơn luồng không chứng minh được khóa hoạt động khi hai transaction cạnh tranh. Nên có integration test dùng database và isolation level gần với production.

### 14.1. Kịch bản kiểm thử

1. Tạo một inventory row với available = 5.
2. Mở transaction A và gọi SELECT ... FOR UPDATE.
3. Giữ transaction A chưa commit.
4. Từ transaction B, thử cập nhật hoặc khóa cùng hàng.
5. Xác nhận transaction B phải chờ, bị timeout hoặc nhận lỗi theo database và cấu hình.
6. Commit/rollback transaction A.
7. Xác nhận transaction B tiếp tục hoặc xử lý lỗi như thiết kế.

Để test concurrency ổn định, dùng hai thread và hai transaction độc lập. Không dùng cùng một transaction test bao quanh cả hai luồng vì chúng cần quan sát trạng thái cạnh tranh thật.

### 14.2. Kiểm thử giới hạn @Lock với @Query

Tạo một derived query có @Lock và một string-based query có @Query cùng @Lock. Quan sát log và SQL thực tế:

- Derived query: dialect tạo lock clause.
- String-based query: warning cho biết lock metadata không được áp dụng theo hành vi tài liệu.
- String-based query có FOR UPDATE: database nhận câu SQL có lock clause tường minh.

Không chỉ assert kết quả trả về; cần xác nhận transaction thứ hai thực sự bị chặn hoặc xử lý theo semantics mong muốn.

### 14.3. Kiểm thử trên đúng database

H2 có thể hữu ích cho kiểm thử repository cơ bản nhưng không chứng minh locking semantics giống PostgreSQL, MySQL hoặc SQL Server. Dùng Testcontainers hoặc môi trường integration tương ứng nếu khóa là một phần quan trọng của correctness.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Gắn @Lock nhưng query @Query vẫn không chặn transaction khác | @Lock bị bỏ qua trên string-based query | Đưa FOR UPDATE/lock clause phù hợp vào SQL hoặc chuyển sang derived query. |
| Khóa được giải phóng ngay sau SELECT | Không có transaction bao trùm bước đọc và cập nhật; autocommit kết thúc statement | Đặt @Transactional ở service giữ critical section. |
| SQL FOR UPDATE chạy trên database này nhưng lỗi ở database khác | Lock clause phụ thuộc dialect | Viết SQL theo database đích hoặc dùng derived query với @Lock. |
| Request chờ quá lâu | Transaction khác giữ lock lâu hoặc truy vấn khóa quá nhiều hàng | Rút ngắn transaction, thu hẹp predicate và cấu hình timeout phù hợp. |
| Deadlock khi cập nhật nhiều hàng | Các transaction khóa hàng theo thứ tự khác nhau | Khóa theo thứ tự ổn định và retry lỗi deadlock có giới hạn. |
| PESSIMISTIC_READ chặn cả writer như khóa ghi | Database/dialect không phân biệt read lock và write lock | Kiểm tra semantics của database; không dựa vào tên mode để dự đoán chính xác. |
| Chỉ khóa root nhưng dữ liệu con vẫn thay đổi | SQL chỉ khóa hàng được chọn; aggregate mapping không tự khóa mọi bảng con | Khóa thêm hàng cần thiết hoặc thiết kế lại thao tác/aggregate boundary. |
| SKIP LOCKED bỏ qua một số job | Những hàng đó đang bị transaction khác giữ khóa | Đây là semantics có chủ đích cho queue; cần retry/claim recovery. |
| Retry làm xử lý trùng | Use case không idempotent hoặc retry cả side effect đã thành công | Dùng idempotency key, checkpoint và retry có giới hạn. |

## 16. Quy trình chọn cách khóa

Khi thiết kế một thao tác có cạnh tranh, hãy lần lượt trả lời:

1. **Có thật sự cần khóa không?** Một constraint hoặc conditional UPDATE có giải quyết được vấn đề không?
2. **Xung đột thường xuyên hay hiếm?** Thường xuyên có thể nghiêng về pessimistic lock; hiếm có thể dùng @Version.
3. **Query là derived hay SQL tùy chỉnh?** Derived query có thể dùng @Lock; @Query dạng chuỗi phải chứa lock clause trong SQL.
4. **Database nào đang chạy?** Kiểm tra cú pháp, isolation, lock mode và driver.
5. **Transaction giữ khóa trong bao lâu?** Giữ phạm vi ngắn và không gọi dịch vụ ngoài trong critical section.
6. **Khóa những hàng nào?** Xác định root row, child row, index và predicate.
7. **Nếu không lấy được khóa thì sao?** Chờ, timeout, NOWAIT, SKIP LOCKED hay trả lỗi nghiệp vụ?
8. **Có thể deadlock không?** Dùng thứ tự khóa nhất quán.
9. **Đã kiểm thử cạnh tranh trên database mục tiêu chưa?** Xác nhận bằng hai transaction thực sự độc lập.

## 17. Bài tập tự thực hành

**Bài tập 1 — Derived query với @Lock.** Tạo findForUpdateBySku với PESSIMISTIC_WRITE. Bật log SQL và xác định dialect thêm lock clause nào.

**Bài tập 2 — @Lock với @Query.** Thêm cả @Lock và @Query vào một method. Quan sát warning và chứng minh lock metadata bị bỏ qua trên phiên bản Spring Data JDBC đang dùng.

**Bài tập 3 — SQL FOR UPDATE.** Bỏ @Lock, thêm FOR UPDATE vào câu SQL @Query. Dùng hai transaction để kiểm tra transaction thứ hai phải chờ như thế nào.

**Bài tập 4 — Giữ transaction.** Đặt query khóa trong service @Transactional, rồi thử chuyển annotation sang một method chỉ trả entity. So sánh thời điểm khóa được giải phóng.

**Bài tập 5 — NOWAIT và SKIP LOCKED.** Trên database hỗ trợ, thử cả hai tùy chọn. Ghi nhận khác biệt giữa trả lỗi ngay và bỏ qua hàng đang bị khóa.

**Bài tập 6 — Optimistic locking.** Thêm @Version vào aggregate và chạy hai transaction cùng đọc rồi lưu. So sánh với FOR UPDATE.

**Bài tập 7 — Conditional UPDATE.** Thay read-lock-update bằng câu UPDATE ... WHERE available >= :quantity. Kiểm tra row count khi hai request đồng thời đặt hàng.

**Bài tập 8 — Deadlock.** Tạo hai transaction khóa hai hàng theo thứ tự ngược nhau. Quan sát deadlock và sửa bằng cách khóa theo ID tăng dần.

## 18. Ghi nhớ

Trong Spring Data JDBC, @Lock được hỗ trợ cho derived query method. Hai mode là PESSIMISTIC_READ và PESSIMISTIC_WRITE; dialect quyết định câu SQL khóa được sinh và một số database có thể ánh xạ cả hai mode về cùng hành vi.

@Lock hiện không áp dụng cho string-based query khai báo bằng @Query; Spring Data bỏ qua lock metadata và ghi warning theo tài liệu hiện hành. Khi cần SQL tùy chỉnh, hãy đưa FOR UPDATE, FOR SHARE hoặc cú pháp khóa của database trực tiếp vào câu SQL. Giữ SELECT khóa và thao tác cập nhật trong cùng transaction, vì khóa thường được giải phóng khi transaction kết thúc.

Pessimistic lock phù hợp với critical section ngắn và xung đột thường xuyên. Với xung đột hiếm, cân nhắc @Version; với phép cập nhật đơn giản có điều kiện, conditional UPDATE thường gọn hơn. Luôn kiểm thử locking trên đúng database, thu hẹp phạm vi khóa và thiết kế xử lý timeout/deadlock phù hợp.

### Tài liệu tham khảo

- [Spring Data Relational – JDBC Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html)
- [Spring Data Relational – Lock Annotation API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/repository/Lock.html)
- [Spring Data Relational – LockMode API](https://docs.spring.io/spring-data/data-jdbc/docs/current/api/org/springframework/data/relational/core/sql/LockMode.html)
- [PostgreSQL – Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [MySQL – InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
