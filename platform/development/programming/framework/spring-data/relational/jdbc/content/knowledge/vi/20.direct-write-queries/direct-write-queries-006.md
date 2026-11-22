# Cập nhật nguyên tử một cột bằng điều kiện SQL

Trong ứng dụng Spring Data JDBC, đôi khi ta chỉ cần thay đổi **một cột** của một hàng theo điều kiện hiện tại trong database. Ví dụ: trừ số lượng tồn kho nếu vẫn còn đủ hàng, tăng bộ đếm, hoặc chuyển trạng thái đơn hàng chỉ khi trạng thái cũ đúng như mong đợi.

Một cách dễ nghĩ tới là đọc aggregate, thay đổi field trong Java rồi gọi `repository.save`. Nhưng với những phép cập nhật đơn giản cần được thực hiện an toàn khi nhiều request chạy đồng thời, có thể viết một câu **SQL UPDATE có điều kiện** để database kiểm tra điều kiện và thay đổi giá trị trong cùng một statement.

Spring Data JDBC hỗ trợ cách này thông qua `@Query` kết hợp `@Modifying`. Câu lệnh được thực thi trực tiếp trên database và có thể trả về số hàng bị ảnh hưởng. Bài học này trình bày cách sử dụng, ý nghĩa của tính nguyên tử, phạm vi transaction và những tác động cần lưu ý khi cập nhật trực tiếp thay vì lưu aggregate.

## 1. Vì sao cập nhật trực tiếp một cột?

Giả sử bảng tồn kho có một hàng:

```text
inventory
+----+---------+--------------------+
| id | sku     | available_quantity |
+----+---------+--------------------+
|  7 | BOOK-01 |                 10 |
+----+---------+--------------------+
```

Hai request cùng muốn đặt mua một sản phẩm. Nếu mỗi request làm theo quy trình:

1. Đọc `available_quantity` từ database.
2. Kiểm tra số lượng còn đủ.
3. Tính giá trị mới trong Java.
4. Gọi `save` để ghi lại aggregate.

thì cả hai request có thể cùng đọc giá trị 10 trước khi request nào ghi dữ liệu. Cả hai cùng tính 9 và cùng lưu 9. Kết quả cuối chỉ giảm một đơn vị dù có hai lần đặt hàng thành công.

Đây là dạng **lost update** (mất cập nhật): một lần ghi dựa trên dữ liệu cũ ghi đè kết quả của lần ghi khác.

Với một phép cập nhật số học đơn giản, có thể để database tính từ giá trị hiện tại:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE id = 7;
```

Mỗi statement cập nhật trực tiếp giá trị hiện tại của hàng. Database điều phối các lần ghi đồng thời theo cơ chế khóa và transaction của nó, nhờ vậy hai lần giảm được áp dụng tuần tự thay vì cùng ghi lại một giá trị cũ đã tính ở Java.

## 2. Điều kiện và thay đổi nằm trong cùng một câu lệnh

Nếu chỉ viết:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE sku = 'BOOK-01';
```

câu lệnh vẫn có thể làm số lượng tồn kho xuống dưới 0. Ta cần đưa điều kiện nghiệp vụ vào `WHERE`:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE sku = 'BOOK-01'
  AND available_quantity >= 1;
```

Database kiểm tra điều kiện và cập nhật trong cùng một thao tác. Khi hai request cùng tranh chấp một hàng, database áp dụng quy tắc đồng thời của mình; sau khi một request cập nhật, request còn lại phải đánh giá điều kiện trên trạng thái hàng hiện hành. Nếu số lượng không còn đủ, câu UPDATE không tác động hàng đó.

Đây là cách thường được gọi là **conditional atomic update** hoặc **compare-and-set** khi điều kiện so sánh trạng thái cũ và thay đổi giá trị mới.

### 2.1. Phân biệt tính nguyên tử của statement và transaction

- **Atomic statement:** một câu UPDATE được database thực hiện như một đơn vị. Điều kiện và thay đổi của câu lệnh không bị tách thành hai thao tác Java độc lập.
- **Transaction:** nhóm nhiều câu lệnh thành một đơn vị commit/rollback. Transaction cần thiết khi use case có thêm thao tác khác phải thành công hoặc thất bại cùng nhau.

Một UPDATE đơn lẻ đã là một statement nguyên tử theo semantics transaction của database. `@Transactional` ở tầng service giúp phối hợp nó với các thao tác database khác trong cùng use case.

Tính nguyên tử của một câu lệnh không tự giải quyết mọi invariant trên nhiều hàng, nhiều bảng hoặc nhiều aggregate. Những trường hợp đó cần transaction, constraint, khóa hoặc mức isolation phù hợp.

## 3. @Modifying và @Query trong Spring Data JDBC

Spring Data JDBC cho phép khai báo SQL tùy chỉnh bằng `@Query`. Với câu lệnh INSERT, UPDATE, DELETE hoặc DDL không trả về tập hàng, cần đánh dấu method là modifying query bằng `@Modifying`.

Các import:

```java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;
```

Ví dụ repository:

```java
public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available_quantity = available_quantity - :quantity
        WHERE sku = :sku
          AND :quantity > 0
          AND available_quantity >= :quantity
        """)
    int reserve(
        @Param("sku") String sku,
        @Param("quantity") int quantity
    );
}
```

Giải thích:

- `@Query` chứa SQL sẽ được thực thi.
- `@Modifying` báo cho Spring Data biết đây là query thay đổi dữ liệu, không phải query đọc entity.
- `:sku` và `:quantity` là named parameters được bind từ tham số method.
- Biểu thức `available_quantity - :quantity` tính giá trị mới trực tiếp trong database.
- Điều kiện `available_quantity >= :quantity` ngăn trừ vượt quá số lượng hiện có.
- Điều kiện `:quantity > 0` ngăn yêu cầu số lượng không hợp lệ ngay ở SQL.
- Kiểu trả về `int` nhận số hàng bị ảnh hưởng.

Spring Data JDBC hỗ trợ kiểu trả về `void`, `int` (số hàng được cập nhật) và `boolean` (có ít nhất một hàng được cập nhật hay không) cho modifying query. Với thao tác cần biết chính xác kết quả, `int` thường hữu ích hơn.

**Lưu ý về tên package:** `@Modifying` của Spring Data JDBC là `org.springframework.data.jdbc.repository.query.Modifying`. Đừng import nhầm annotation cùng tên từ Spring Data JPA.

## 4. Đọc số hàng bị ảnh hưởng

Giá trị trả về từ method `reserve` cho biết điều kiện UPDATE có khớp hàng nào hay không:

| Giá trị trả về | Ý nghĩa trong ví dụ |
| --- | --- |
| `1` | Một hàng tồn kho đã được cập nhật; yêu cầu giữ hàng thành công. |
| `0` | Không có hàng nào thỏa điều kiện: SKU không tồn tại, số lượng không hợp lệ hoặc tồn kho không đủ. |
| Lớn hơn `1` | Có nhiều hàng khớp; có thể schema thiếu unique constraint hoặc điều kiện WHERE chưa đủ chặt. |

Nếu `sku` là duy nhất, một yêu cầu hợp lệ chỉ nên cập nhật tối đa một hàng. Database nên bảo vệ quy tắc đó bằng unique constraint:

```sql
ALTER TABLE inventory
ADD CONSTRAINT uq_inventory_sku UNIQUE (sku);
```

Không nên chỉ dựa vào code Java để bảo đảm một SKU có một hàng tồn kho.

### 4.1. Vì sao số 0 không đồng nghĩa duy nhất với “không đủ hàng”?

Trong câu lệnh trên, `0` có thể xuất hiện khi:

- Không tìm thấy SKU.
- `quantity` bằng 0 hoặc âm.
- SKU tồn tại nhưng số lượng không đủ.

Nếu nghiệp vụ chỉ cần biết thao tác có thành công hay không, một kết quả 0/1 là đủ. Nếu cần thông báo chính xác lý do, service có thể thực hiện một truy vấn đọc bổ sung để xác định trạng thái. Tuy nhiên, kết quả đọc bổ sung phản ánh trạng thái tại thời điểm truy vấn đó; dữ liệu có thể tiếp tục thay đổi bởi request khác.

Với API cần phân biệt rõ từng kết quả ngay trong một round trip, có thể cân nhắc câu lệnh database-specific trả thêm dữ liệu (ví dụ `UPDATE ... RETURNING` trên PostgreSQL) và custom repository. Khả năng này phụ thuộc dialect và cách mapping kết quả; không nên giả định mọi database hỗ trợ cùng cú pháp.

## 5. Đặt transaction ở application service

Một modifying query method là query method được khai báo; nên xác định transaction rõ ràng. Cách thường dùng là đặt transaction ở service để bao trùm toàn bộ use case.

```java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0"
            );
        }

        int updated = inventory.reserve(sku, quantity);

        if (updated == 0) {
            throw new InsufficientStockException(
                "Không thể giữ hàng cho SKU " + sku
            );
        }

        if (updated != 1) {
            throw new IllegalStateException(
                "Số hàng tồn kho được cập nhật không hợp lệ: " + updated
            );
        }
    }
}
```

Trong ví dụ:

1. Service kiểm tra dữ liệu đầu vào.
2. Repository gửi một câu UPDATE có điều kiện.
3. Database trả số hàng bị ảnh hưởng.
4. Service quyết định kết quả nghiệp vụ.
5. Nếu ném exception runtime trong transaction mặc định của Spring, transaction sẽ rollback theo quy tắc rollback mặc định.

Nếu modifying query được gọi trong một repository interface đã đánh dấu `@Transactional(readOnly = true)` ở cấp interface, method ghi cần transaction không read-only (hoặc được gọi bên trong transaction ghi của service). Không nên chạy UPDATE trong transaction chỉ đọc.

### 5.1. Khi nào đặt @Transactional trên repository?

Có thể khai báo trực tiếp:

```java
@Modifying
@Transactional
@Query("""
    UPDATE inventory
    SET available_quantity = available_quantity - :quantity
    WHERE sku = :sku
      AND available_quantity >= :quantity
    """)
int reserve(
    @Param("sku") String sku,
    @Param("quantity") int quantity
);
```

Cách này làm cho method repository tự có transaction. Tuy nhiên, nếu use case còn cần ghi đơn hàng, ghi lịch sử hoặc phát sinh các thao tác database khác, transaction ở service thể hiện ranh giới nghiệp vụ rõ hơn và cho phép nhiều repository cùng tham gia một transaction.

Không nên mở transaction riêng cho từng câu lệnh nếu chúng cần cùng commit hoặc rollback như một use case.

## 6. Cập nhật một cột theo giá trị hiện tại

Một lợi ích quan trọng của UPDATE expression là database tính giá trị mới từ giá trị đang có ở hàng được cập nhật.

Ví dụ bộ đếm:

```sql
UPDATE page_counters
SET view_count = view_count + 1
WHERE page_key = :pageKey;
```

Repository:

```java
@Modifying
@Query("""
    UPDATE page_counters
    SET view_count = view_count + 1
    WHERE page_key = :pageKey
    """)
int incrementViewCount(@Param("pageKey") String pageKey);
```

Cách này thường an toàn hơn quy trình:

```java
Counter counter = repository.findByPageKey(pageKey);
counter.setViewCount(counter.getViewCount() + 1);
repository.save(counter);
```

Nếu hai request cùng đọc `view_count = 10`, cả hai có thể cùng ghi `11`. Với câu UPDATE `view_count = view_count + 1`, database áp dụng hai lần tăng trên giá trị hàng hiện tại; kết quả sẽ là 12 khi cả hai statement thành công.

Các biểu thức tương tự:

```sql
UPDATE accounts
SET balance = balance + :amount
WHERE id = :id;

UPDATE products
SET sold_count = sold_count + :quantity
WHERE id = :id;

UPDATE tasks
SET retry_count = retry_count + 1
WHERE id = :id;
```

Nếu phép tính có điều kiện, hãy thêm điều kiện vào WHERE cùng câu UPDATE thay vì kiểm tra bằng một SELECT tách rời rồi mới ghi.

## 7. Cập nhật trạng thái theo điều kiện cũ

Conditional UPDATE cũng phù hợp với chuyển trạng thái. Ví dụ chỉ cho phép chuyển đơn hàng từ `PENDING` sang `CONFIRMED`:

```sql
UPDATE purchase_orders
SET status = :newStatus
WHERE id = :id
  AND status = :expectedStatus;
```

Repository:

```java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :newStatus
    WHERE id = :id
      AND status = :expectedStatus
    """)
int changeStatus(
    @Param("id") Long id,
    @Param("expectedStatus") String expectedStatus,
    @Param("newStatus") String newStatus
);
```

Nếu hai request cùng cố chuyển trạng thái từ `PENDING` sang hai trạng thái khác nhau, chỉ request đầu tiên còn thấy trạng thái cũ thỏa điều kiện. Request sau nhận số hàng cập nhật bằng 0.

Đây là một dạng **compare-and-set**:

```text
Nếu trạng thái hiện tại == expectedStatus:
    cập nhật thành newStatus
Ngược lại:
    không thay đổi hàng
```

Service có thể coi kết quả 0 là xung đột trạng thái hoặc đơn hàng không tồn tại. Nếu trạng thái là một phần của state machine phức tạp, cần bảo đảm mọi transition hợp lệ đều được thể hiện bằng điều kiện SQL hoặc được điều phối qua domain logic thích hợp.

## 8. Bảo vệ optimistic locking khi cập nhật trực tiếp

Nếu aggregate root có `@Version`, các thao tác `repository.save` do Spring Data JDBC quản lý sẽ sử dụng version để phát hiện cập nhật dựa trên dữ liệu cũ.

Một câu SQL được đánh dấu `@Modifying` chạy trực tiếp trên database. Nó không tự động áp dụng quy tắc optimistic locking của thao tác lưu aggregate. Nếu muốn giữ optimistic locking cho đường cập nhật này, cần **đưa version vào WHERE và tăng version trong cùng UPDATE**.

Ví dụ:

```sql
UPDATE inventory
SET available_quantity = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND :newQuantity >= 0;
```

Repository:

```java
@Modifying
@Query("""
    UPDATE inventory
    SET available_quantity = :newQuantity,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
      AND :newQuantity >= 0
    """)
int updateQuantity(
    @Param("id") Long id,
    @Param("expectedVersion") Long expectedVersion,
    @Param("newQuantity") int newQuantity
);
```

Nếu version trong database không còn bằng `expectedVersion`, câu UPDATE không khớp hàng và trả 0. Service có thể báo optimistic locking conflict hoặc yêu cầu caller tải lại dữ liệu rồi thử lại theo chính sách nghiệp vụ.

Không được chỉ thêm `version = version + 1` mà bỏ điều kiện version cũ nếu mục tiêu là phát hiện stale update. Cũng không nên để câu UPDATE trực tiếp thay đổi hàng nhưng giữ nguyên version, vì những luồng khác dùng `@Version` có thể không phát hiện rằng hàng đã bị thay đổi.

### 8.1. Không phải lúc nào cũng cần @Version

Nếu câu lệnh chỉ tăng bộ đếm độc lập và biểu thức SQL đã diễn tả đầy đủ phép toán mong muốn, có thể không cần version riêng cho thao tác đó. Ví dụ `view_count = view_count + 1` được database thực hiện trên giá trị hiện tại.

Cần version khi nghiệp vụ yêu cầu phát hiện một client đang cập nhật dựa trên phiên bản cụ thể của aggregate, hoặc khi một thay đổi có thể xung đột với các thao tác ghi aggregate khác.

## 9. Direct UPDATE và aggregate Spring Data JDBC

Spring Data JDBC tổ chức persistence quanh aggregate root. Khi gọi `repository.save(root)`, framework dùng mapping metadata để đồng bộ root và các thành phần được sở hữu.

Một modifying query như:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE sku = :sku
  AND available_quantity >= :quantity;
```

lại tác động trực tiếp vào bảng. Nó không tải aggregate, không gọi domain method và không đồng bộ collection entity con.

Điều đó có thể phù hợp với một cột độc lập, ví dụ:

- Bộ đếm lượt xem.
- Số lượng tồn kho có điều kiện.
- Cờ xử lý hoặc trạng thái được bảo vệ bằng WHERE.
- Timestamp hoặc metadata cập nhật trực tiếp.

Nhưng không nên dùng direct UPDATE để lách qua những invariant phức tạp cần domain method bảo vệ. Nếu thay đổi một cột đòi hỏi cập nhật nhiều đối tượng con hoặc tính lại nhiều giá trị trong aggregate, hãy xem xét lại cách thiết kế use case.

### 9.1. Object đã đọc trước đó không tự cập nhật

Giả sử service đã tải:

```java
InventoryItem item = inventoryRepository.findById(id).orElseThrow();
```

Sau đó một modifying query thay đổi `available_quantity` trong database. Biến `item` trong bộ nhớ vẫn giữ giá trị cũ; Spring Data JDBC không tự thay đổi object đang được giữ trong biến Java.

Nếu cần dùng giá trị mới, hãy đọc lại:

```java
InventoryItem reloaded =
    inventoryRepository.findById(id).orElseThrow();
```

Đặc biệt, đừng lấy một aggregate cũ, chạy direct UPDATE rồi tiếp tục gọi `save(oldAggregate)` mà không xem xét dữ liệu stale. Lần lưu aggregate sau có thể ghi lại trạng thái cũ của property vừa được cập nhật trực tiếp.

## 10. Entity callbacks và auditing không tự chạy

Modifying queries được thực thi trực tiếp trên database. Spring Data JDBC không gọi entity callbacks hoặc lifecycle events cho các query này. Vì vậy, các trường auditing như `@LastModifiedDate` hoặc `@LastModifiedBy` không tự được cập nhật chỉ vì câu UPDATE đã thay đổi một cột khác.

Nếu cần cập nhật thời điểm sửa đổi, hãy đưa cột vào chính SQL:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity,
    updated_at = CURRENT_TIMESTAMP
WHERE sku = :sku
  AND available_quantity >= :quantity;
```

Hoặc sử dụng trigger do database quản lý. Nếu cần lưu người thực hiện, truyền giá trị đã xác thực vào parameter:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity,
    updated_at = CURRENT_TIMESTAMP,
    updated_by = :actor
WHERE sku = :sku
  AND available_quantity >= :quantity;
```

Không giả định rằng chỉ cần bật Spring Data JDBC auditing là mọi câu SQL viết bằng `@Modifying` sẽ tự thêm các giá trị audit. Câu query trực tiếp phải cập nhật chúng nếu không có trigger/database mechanism khác.

## 11. SQL parameter binding và điều kiện an toàn

Dùng named parameters cho giá trị:

```java
@Modifying
@Query("""
    UPDATE inventory
    SET available_quantity = available_quantity - :quantity
    WHERE sku = :sku
    """)
int decrease(
    @Param("sku") String sku,
    @Param("quantity") int quantity
);
```

Spring Data JDBC bind giá trị qua cơ chế JDBC. Không nối dữ liệu request vào câu SQL:

```java
// Không an toàn: không ghép giá trị người dùng vào SQL.
String sql = "UPDATE inventory SET available_quantity = "
    + quantity + " WHERE sku = '" + sku + "'";
```

Parameter binding bảo vệ giá trị đầu vào khỏi bị diễn giải như cú pháp SQL. Tuy nhiên, bind parameter không thay thế được tên bảng, tên cột hoặc từ khóa SQL. Những identifier đó cần được xác định cố định trong query hoặc chọn từ danh sách được cho phép.

Cũng cần kiểm tra:

- Giá trị quantity phải dương.
- ID/SKU phải có kiểu dữ liệu tương ứng với schema.
- Cột được cập nhật cần có constraint phù hợp.
- Điều kiện WHERE phải đủ chặt để không vô tình cập nhật nhiều hàng.
- SQL cần phù hợp dialect của database đang dùng.

## 12. Kiểm thử conditional update

Test tích hợp nên xác nhận cả trường hợp cập nhật thành công và trường hợp điều kiện không thỏa.

Giả sử repository có phương thức `reserve` ở phần 3 và entity:

```java
@Table("inventory")
public record InventoryItem(
    @Id Long id,
    String sku,
    int availableQuantity
) {}
```

Một test minh họa:

```java
@DataJdbcTest
class InventoryRepositoryTest {

    @Autowired
    InventoryRepository inventory;

    @Test
    void decreasesQuantityWhenEnoughStockExists() {
        InventoryItem item = inventory.save(
            new InventoryItem(null, "BOOK-01", 10)
        );

        int updated = inventory.reserve("BOOK-01", 3);

        assertThat(updated).isEqualTo(1);

        InventoryItem reloaded = inventory.findById(item.id())
            .orElseThrow();

        assertThat(reloaded.availableQuantity()).isEqualTo(7);
    }

    @Test
    void doesNotDecreaseQuantityWhenStockIsInsufficient() {
        InventoryItem item = inventory.save(
            new InventoryItem(null, "BOOK-02", 2)
        );

        int updated = inventory.reserve("BOOK-02", 5);

        assertThat(updated).isZero();

        InventoryItem reloaded = inventory.findById(item.id())
            .orElseThrow();

        assertThat(reloaded.availableQuantity()).isEqualTo(2);
    }
}
```

Các test này cần schema test tương ứng. Với `@DataJdbcTest`, transaction của test slice thường rollback sau test. Nếu cần xác minh hành vi cạnh tranh thực sự, nên có integration test chạy nhiều transaction/connection độc lập trên đúng database và driver của môi trường triển khai.

### 12.1. Kiểm thử cạnh tranh đồng thời

Một test concurrency có thể tạo hai transaction cùng giữ số lượng lớn hơn nhu cầu tổng hợp. Ví dụ tồn kho là 5, hai request mỗi request muốn giữ 4:

- Cả hai cùng gọi `reserve("BOOK-01", 4)`.
- Chỉ một câu UPDATE có thể thỏa điều kiện và cập nhật hàng.
- Câu còn lại thấy số lượng không còn đủ và trả 0.
- Kết quả cuối là tồn kho 1, chỉ một request thành công.

Kịch bản cần dùng hai connection/transaction thực sự độc lập; hai lần gọi tuần tự trong cùng một transaction không mô phỏng đầy đủ tranh chấp đồng thời.

Không nên kiểm tra concurrency chỉ bằng sleep hoặc timing ngẫu nhiên. Dùng barrier/latch để đồng bộ điểm bắt đầu của các thread và kiểm tra số hàng cập nhật, trạng thái cuối trong database.

## 13. Giới hạn của một câu UPDATE

Một conditional UPDATE rất hữu ích nhưng không phải giải pháp cho mọi quy tắc nghiệp vụ.

### 13.1. Điều kiện chỉ dựa trên một hàng

Ví dụ `available_quantity >= :quantity` là điều kiện nằm ngay trên hàng tồn kho được cập nhật. Database có thể kiểm tra và thay đổi hàng trong một statement.

Nếu invariant phụ thuộc tổng dữ liệu của nhiều hàng, ví dụ “tổng số ghế đã đặt trong tất cả phòng không vượt quá sức chứa”, một UPDATE trên một hàng không tự bảo đảm invariant đó nếu các transaction khác cũng có thể ghi những hàng liên quan. Có thể cần constraint, khóa, isolation hoặc một mô hình dữ liệu khác.

### 13.2. Không cập nhật các aggregate khác

Một UPDATE vào `inventory` không tự tạo đơn hàng, không ghi payment và không phát domain event. Nếu use case cần giữ hàng đồng thời tạo đơn hàng trong cùng database, hãy đặt các thao tác cần thiết trong một transaction service phù hợp.

Nếu quy trình trải qua nhiều service/database, cần thiết kế orchestration, outbox hoặc saga. Không thể xem một câu UPDATE JDBC là transaction phân tán.

### 13.3. Trigger và side effects của database

Một UPDATE có thể kích hoạt trigger hoặc constraint. Đây là behavior do database quản lý. Hãy biết rõ các trigger trên bảng, đặc biệt khi chúng ghi audit, cập nhật bảng liên quan hoặc thay đổi giá trị khác.

Câu UPDATE trực tiếp không chạy entity callback của Spring Data, nhưng database trigger vẫn chạy theo cấu hình schema.

## 14. Khi nào dùng modifying query, khi nào dùng save(root)?

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Tăng/giảm một bộ đếm bằng biểu thức trên giá trị hiện tại | `@Modifying` + conditional UPDATE |
| Trừ tồn kho nếu số lượng vẫn đủ | UPDATE với điều kiện `available_quantity >= :quantity` |
| Chuyển trạng thái nếu trạng thái cũ đúng | UPDATE với `WHERE status = :expectedStatus` |
| Thay đổi nhiều thuộc tính và kiểm tra invariant domain | Tải aggregate, gọi domain method, `repository.save(root)` |
| Đồng bộ collection entity con thuộc aggregate | Dùng persistence aggregate root |
| Cần entity callbacks/auditing tự động của Spring Data | Dùng đường persistence aggregate hoặc tự cập nhật audit trong SQL |
| Cần optimistic locking cho direct update | Đưa version cũ vào WHERE và tăng version trong cùng UPDATE |
| Cập nhật nhiều bảng cần commit/rollback cùng nhau | Service transaction điều phối các repository/query |

Không nên lạm dụng modifying query chỉ để giảm vài dòng code. Nó là công cụ phù hợp cho những thao tác dữ liệu có semantics rõ ràng, thường là một thay đổi nhỏ có điều kiện và có thể biểu diễn chính xác trong SQL.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| UPDATE không chạy hoặc bị xem như query đọc | Thiếu `@Modifying` trên method `@Query`. | Đánh dấu modifying query bằng đúng annotation của Spring Data JDBC. |
| Import nhầm @Modifying của JPA | Có nhiều annotation cùng tên trong các module Spring Data. | Dùng `org.springframework.data.jdbc.repository.query.Modifying`. |
| Method trả entity nhưng SQL không có result set | Modifying query chỉ trả void, số hàng hoặc boolean theo contract. | Dùng `int`/`boolean` hoặc query đọc riêng sau update. |
| Số lượng tồn kho bị âm | Điều kiện kiểm tra không nằm trong WHERE hoặc điều kiện không đủ chặt. | Đưa invariant vào cùng câu UPDATE và thêm CHECK constraint nếu phù hợp. |
| Hai request làm mất một lần tăng bộ đếm | Đọc, tính trong Java rồi ghi giá trị cũ. | Dùng biểu thức `column = column + :delta`. |
| Method trả 0 nhưng ứng dụng tưởng lỗi SQL | Không có hàng thỏa điều kiện. | Diễn giải row count thành kết quả nghiệp vụ. |
| @LastModifiedDate không đổi | Modifying query không gọi entity callbacks/auditing. | Cập nhật cột audit trong SQL hoặc dùng trigger. |
| Lần save tiếp theo ghi lại dữ liệu cũ | Aggregate đang giữ trong bộ nhớ được tải trước direct UPDATE. | Reload trước khi tiếp tục lưu aggregate. |
| Optimistic locking không phát hiện direct update | SQL không kiểm tra/tăng version. | Thêm version predicate và increment version trong cùng UPDATE. |
| Cập nhật nhiều hàng ngoài ý muốn | WHERE không đủ điều kiện hoặc thiếu unique constraint. | Siết predicate, thêm constraint và kiểm tra row count. |
| Query method chạy trong transaction read-only | Transaction cấp repository/service được đánh dấu read-only. | Đặt transaction ghi ở service hoặc method modifying. |

## 16. Quy trình thiết kế một atomic column update

Khi cần cập nhật một cột trực tiếp:

1. Xác định chính xác cột cần thay đổi và kiểu phép tính (gán, tăng, giảm, chuyển trạng thái).
2. Viết điều kiện bảo vệ invariant trong `WHERE` cùng câu UPDATE.
3. Dùng biểu thức SQL dựa trên giá trị hiện tại nếu phép toán cần an toàn trước lost update.
4. Khai báo `@Query` và `@Modifying` trong repository Spring Data JDBC.
5. Dùng named parameter để bind các giá trị.
6. Chọn kiểu trả về `int` nếu cần biết số hàng bị ảnh hưởng.
7. Đặt transaction ở service nếu use case phối hợp nhiều thao tác; không chạy modifying query trong transaction read-only.
8. Nếu aggregate có `@Version`, tự quản lý version trong SQL khi direct update cần giữ optimistic locking.
9. Cập nhật audit column trong SQL/trigger vì entity callbacks không tự chạy.
10. Reload aggregate nếu code cần trạng thái mới sau direct update.
11. Kiểm thử cả điều kiện thành công, điều kiện thất bại và concurrency trên database phù hợp.
12. Đảm bảo thao tác trực tiếp không phá vỡ invariant hoặc ownership của aggregate.

> **Cập nhật nguyên tử một cột có điều kiện nghĩa là đặt phép thay đổi và điều kiện kiểm tra trong cùng một câu UPDATE.** Trong Spring Data JDBC, dùng `@Modifying` kết hợp `@Query`, bind tham số an toàn và đọc số hàng bị ảnh hưởng để xác định kết quả. Khi thao tác cần giữ optimistic locking, auditing hoặc nhiều invariant của aggregate, hãy đưa những quy tắc đó vào SQL/transaction một cách tường minh hoặc dùng đường lưu aggregate phù hợp.

### Tài liệu tham khảo

- [Spring Data JDBC — Query Methods: Modifying Query](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): khai báo modifying query bằng `@Modifying` và các kiểu trả về được hỗ trợ.
- [Spring Data JDBC — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction cho CRUD và query methods, cách đặt transaction cho thao tác ghi.
- [Spring Data JDBC — @Modifying API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Modifying.html): package và mục đích của annotation `@Modifying`.
- [Spring Data JDBC — @Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Query.html): khai báo SQL và named parameter cho repository method.
- [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): cú pháp UPDATE, biểu thức SET và điều kiện WHERE.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): hành vi transaction khi nhiều session cập nhật đồng thời.
