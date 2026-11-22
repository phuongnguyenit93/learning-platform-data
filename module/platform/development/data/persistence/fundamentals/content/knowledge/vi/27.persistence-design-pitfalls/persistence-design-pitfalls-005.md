# Đọc rồi ghi lại giá trị mà không kiểm soát đồng thời

Một ứng dụng bán vé có 10 chỗ trống. Hai request đặt vé đến gần như đồng thời. Cả hai đọc `available_seats = 10`, mỗi request trừ đi 1 và ghi lại `9`. Hệ thống đã nhận **hai vé** nhưng số chỗ chỉ giảm **một**. Không có cú pháp SQL sai, không nhất thiết có exception và cả hai API có thể trả HTTP 200. Đó là một lỗi thiết kế persistence nguy hiểm: **đọc trạng thái, tính kết quả ở ứng dụng, rồi ghi lại mà không bảo vệ thay đổi đồng thời**.

Vấn đề không giới hạn ở phép trừ: cập nhật số dư, điểm thưởng, tồn kho, trạng thái đơn hàng, quota, lịch hẹn, số lượt sử dụng hoặc bộ đếm đều có thể mắc lỗi tương tự. Khi sự cố xảy ra, một kiểm thử tuần tự vẫn xanh, log còn cho thấy “đã UPDATE thành công”, nhưng bất biến nghiệp vụ đã bị phá.

Bài thuộc chương **Lỗi thiết kế** của module **DATA_PERSISTENCE_FUNDAMENTALS**, nơi người học Java tìm hiểu lưu trữ dữ liệu bền vững từ schema, giao dịch, isolation và kiểm soát đồng thời đến tối ưu và phục hồi. Bài giải thích tại sao thao tác **read–modify–write** cần một giao thức đồng thời rõ ràng, so sánh **cập nhật nguyên tử**, **optimistic locking**, **pessimistic locking** và **transaction isolation**, cung cấp ví dụ Java/JDBC/JPA, bài kiểm thử race có thể tái hiện và checklist ra quyết định.

**Thông điệp quan trọng:** Đừng cho rằng “đã đặt trong transaction”, “UPDATE trả về 1 dòng” hoặc “ứng dụng chỉ có một instance” đồng nghĩa dữ liệu an toàn. Điều phải chứng minh là **không hai request nào có thể xác nhận thành công dựa trên cùng một trạng thái đã hết hiệu lực mà làm mất hoặc ghi đè thay đổi của nhau**.

## 1. Read–modify–write là gì và vì sao dễ sai?

Mẫu thao tác:

~~~text
oldValue = readFromDatabase(id)
newValue = calculate(oldValue, request)
writeToDatabase(id, newValue)
return success
~~~

Trong Java/JDBC, nó thường xuất hiện ở dạng:

~~~java
int available = inventoryRepository.findAvailable(productId);
if (available <= 0) {
    throw new SoldOutException();
}
inventoryRepository.saveAvailable(productId, available - 1);
~~~

Ở luồng chạy **đơn lẻ**, mọi thứ hợp lý. Nhưng thao tác đọc, tính và ghi không trở thành nguyên tử chỉ vì ba dòng nằm liên tiếp trong source code. JVM có thể chuyển thread, request khác có thể chạy trên pod khác và database xử lý nhiều transaction đồng thời.

Muốn thiết kế đúng, phải trả lời:

1. **Trạng thái nào** request đã quan sát?
2. **Giá trị nào** còn phải đúng tại thời điểm ghi?
3. Database có **kiểm tra giá trị đó trong thao tác ghi** không?
4. Nếu trạng thái đã thay đổi, request **biết được thất bại như thế nào**?
5. Application có **retry/recompute** hoặc từ chối theo đúng hợp đồng nghiệp vụ không?

Nếu không có câu trả lời rõ, một phép gán `SET available = 9 WHERE product_id = 42` có thể ghi đè một cập nhật hợp lệ xảy ra sau lần đọc.

## 2. Lịch thực thi gây lost update

Giả sử `inventory(product_id=42, available=10)`. Hai transaction A và B cùng đặt một sản phẩm:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as PostgreSQL
    participant B as Request B
    A->>DB: SELECT available (42)
    DB-->>A: 10
    B->>DB: SELECT available (42)
    DB-->>B: 10
    A->>DB: UPDATE SET available=9 WHERE id=42
    DB-->>A: 1 row
    A->>DB: COMMIT
    B->>DB: UPDATE SET available=9 WHERE id=42
    DB-->>B: 1 row
    B->>DB: COMMIT
    Note over DB: Hai đơn đã được nhận nhưng available chỉ còn 9
~~~

| Thời điểm | A | B | Giá trị bền vững |
| --- | --- | --- | --- |
| T0 | | | 10 |
| T1 | Đọc 10 | | 10 |
| T2 | | Đọc 10 | 10 |
| T3 | Tính 9, ghi 9, commit | | 9 |
| T4 | | Tính 9 từ bản đọc cũ, ghi 9, commit | 9 |
| Kết thúc | Xác nhận đặt vé | Xác nhận đặt vé | **9, đáng lẽ 8** |

Đây là **lost update**: một thay đổi hợp lệ bị một phép ghi dựa trên trạng thái cũ che mất. Hai câu `UPDATE` vẫn có thể trả `1 row affected` vì cả hai đều tìm thấy hàng theo `WHERE id = 42`; row count không chứng minh kết quả đúng.

Trong PostgreSQL ở isolation `READ COMMITTED`, câu `UPDATE` thứ hai có thể phải **chờ row lock** của A. Sau khi A commit, B tiếp tục và kiểm tra lại điều kiện tìm hàng theo semantics của engine. Nhưng nếu điều kiện chỉ có `id = 42` và giá trị gán vẫn là **hằng số 9 được Java tính từ trước**, việc chờ khóa **không tự tính lại số 10** hay biến kết quả thành 8.

Điều cần bảo vệ không chỉ là “hai lệnh không ghi cùng lúc”; cần bảo vệ **mối quan hệ nhân quả giữa giá trị đã đọc và phép cập nhật sẽ commit**.

## 3. Phân biệt lost update với các lỗi concurrency liên quan

Các hiện tượng thường bị gom chung thành “race condition”, nhưng cách chữa khác nhau:

| Hiện tượng | Ví dụ | Bất biến bị đe dọa |
| --- | --- | --- |
| **Lost update** | Hai request cùng đọc 10, cùng ghi 9 | Mất một phép trừ/ghi đè trường |
| **Write skew** | Hai bác sĩ cùng thấy người kia trực, cả hai tự bỏ ca ở hai hàng khác nhau | Bất biến liên hàng bị phá dù không ghi cùng hàng |
| **Duplicate effect** | Timeout khiến client gửi lại, hệ thống thu tiền hai lần | Một ý định gây hai tác động |
| **Check-then-act race** | `SELECT EXISTS` thấy email chưa có, hai request cùng INSERT | Trùng tài nguyên nếu không có unique constraint |
| **Non-repeatable read** | Đọc cùng hàng hai lần trong transaction ra hai giá trị | Quyết định trong transaction dựa vào dữ liệu đổi |
| **Phantom** | Query điều kiện lần sau trả thêm/bớt hàng | Quy tắc phụ thuộc một tập hàng có thể không ổn định |
| **Stale cache write** | Đọc từ replica/cache cũ rồi ghi về primary | Ghi dựa trên phiên bản đã lạc hậu |

Không phải mọi update dựa vào đọc đều là lỗi. Ví dụ transaction chỉ ghi một giá trị độc lập, không phụ thuộc trạng thái trước đó, có thể không cần compare-and-set. Ngược lại, với phép **tăng/giảm, chuyển trạng thái, kiểm tra giới hạn hoặc xác nhận đặt chỗ**, trạng thái hiện tại thường là phần thiết yếu của quyết định.

**Idempotency** và **concurrency control** bổ sung cho nhau nhưng không thay thế nhau: idempotency ngăn **một yêu cầu lặp lại** gây hiệu ứng nhiều lần; concurrency control bảo vệ **hai yêu cầu khác nhau** cùng sửa trạng thái chia sẻ.

## 4. Vì sao `@Transactional` chưa đủ?

Một service Spring có thể nhìn rất an toàn:

~~~java
@Transactional
public void reserve(long productId) {
    int oldValue = repository.readAvailable(productId);
    if (oldValue <= 0) {
        throw new SoldOutException();
    }
    repository.writeAvailable(productId, oldValue - 1);
}
~~~

`@Transactional` — khi được Spring transaction infrastructure áp dụng đúng — gom các thao tác database của service vào một transaction. Nó giúp commit/rollback nguyên tử **các câu lệnh trong transaction**, nhưng không mặc nhiên phát hiện rằng **giá trị `oldValue` đã lỗi thời trước khi UPDATE**.

Hai transaction đều có thể:

- Đọc 10 dưới `READ COMMITTED`.
- Cùng tính 9 trong Java.
- Lần lượt ghi 9 và commit.

Vậy cần phân biệt:

- **Atomicity của transaction:** các thao tác trong **một transaction** cùng commit hoặc rollback.
- **Isolation/concurrency correctness:** kết quả của **nhiều transaction đồng thời** có tuân thủ bất biến cần bảo vệ hay không.
- **Durability:** dữ liệu đã commit tồn tại theo bảo đảm của DB.

Một transaction **nguyên tử và bền vững** vẫn có thể commit một **giá trị tính sai** từ trạng thái cũ nếu thiếu kiểm soát đồng thời. Đừng tăng isolation tùy tiện hoặc thêm annotation mà không kiểm tra hành vi thực tế của database.

### Ranh giới transaction phải thật sự tồn tại

Với Spring proxy-based transaction management, một lời gọi nội bộ tự gọi phương thức `@Transactional` (*self-invocation*) có thể không đi qua proxy như mong đợi. Dùng JDBC trực tiếp bằng một `DataSource.getConnection()` khác cũng có thể vượt khỏi transaction mà Spring đang quản lý nếu không tích hợp đúng.

Kiểm thử phải chứng minh phương thức thực sự dùng cùng connection/transaction boundary, thay vì chỉ xem annotation và giả định.

## 5. Thiết kế một bảng tồn kho và bất biến cần giữ

Một ví dụ PostgreSQL tối thiểu:

~~~sql
CREATE TABLE inventory_items (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0),
    row_version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO inventory_items(product_id, available, row_version)
VALUES (42, 10, 0);
~~~

Bất biến miền:

1. Số lượng khả dụng **không được âm**.
2. Mỗi reservation thành công phải trừ đúng `quantity`, **một lần**, trong phạm vi giao dịch được công nhận.
3. Không được xác nhận reservation thành công khi không còn đủ số lượng.
4. Nếu đồng thời tạo bản ghi `reservation`, việc trừ tồn kho và tạo bản ghi nên nằm trong **cùng transaction** nếu chúng thuộc một bất biến cục bộ.
5. Nếu request được retry, không được trừ thêm lần nữa cho **cùng ý định nghiệp vụ**.

`CHECK (available >= 0)` là lớp bảo vệ quan trọng, nhưng **không phát hiện lost update** khi cả hai lần ghi đều gán `9` — số 9 vẫn hợp lệ. Unique constraint trên reservation ID cũng không tự đảm bảo tồn kho giảm đủ nếu phép ghi tồn kho sai.

### Anti-pattern dễ thấy trong SQL

~~~sql
-- Query 1:
SELECT available FROM inventory_items WHERE product_id = 42;

-- Ứng dụng lấy oldValue và tính newValue.
-- Query 2:
UPDATE inventory_items
SET available = :newValue
WHERE product_id = 42;
~~~

Phép ghi thứ hai không mang theo thông tin “`newValue` chỉ đúng nếu database vẫn ở trạng thái đã đọc”. Bởi vậy nó có thể ghi đè trạng thái đã commit của transaction khác.

## 6. Cách sửa đơn giản nhất: cập nhật nguyên tử ngay trong SQL

Khi tác động có thể diễn đạt như phép biến đổi dựa trên **giá trị hiện tại của hàng**, hãy để database thực hiện phép biến đổi trong **một statement**:

~~~sql
UPDATE inventory_items
SET available = available - :quantity,
    row_version = row_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = :productId
  AND available >= :quantity
RETURNING available, row_version;
~~~

Trong PostgreSQL, hai câu `UPDATE` trên cùng hàng không cùng lúc ghi đè hằng số cũ; engine sử dụng locking/semantics của câu lệnh để áp dụng phép biến đổi từ trạng thái hàng phù hợp. Với `READ COMMITTED`, transaction thứ hai có thể đợi hàng rồi áp dụng điều kiện/biểu thức với phiên bản hàng sau khi transaction đầu hoàn tất.

Giả sử ban đầu `available=10` và hai request đặt mỗi request 1:

~~~text
Request A: UPDATE available=available-1 -> 9, commit.
Request B: UPDATE available=available-1 -> 8, commit.
Kết quả: 8, đúng hai reservation thành công.
~~~

Nếu chỉ còn 1, A có thể trừ thành 0, còn B sau khi kiểm tra lại `available >= 1` sẽ không cập nhật được hàng nào. Application phải xem `0 rows` là **không đủ tồn kho hoặc bản ghi không tồn tại**, không trả thành công tùy tiện.

### Vì sao điều kiện là phần bắt buộc?

~~~sql
-- Thiếu điều kiện guard: CHECK có thể báo lỗi thay vì trả sold-out rõ.
UPDATE inventory_items
SET available = available - 1
WHERE product_id = :productId;
~~~

Đây vẫn là phép trừ nguyên tử của một hàng, nhưng chưa thể hiện hợp đồng “không đặt vé khi hết chỗ”. Trên bảng có `CHECK (available >= 0)`, phép trừ dưới 0 bị từ chối bằng constraint error; ứng dụng nên chủ động dùng điều kiện `available >= quantity` để biến việc hết hàng thành kết quả có kiểm soát.

### Không phải mọi phép đọc-modify-write đều gộp thành một câu SQL

Nếu công thức cập nhật phụ thuộc nhiều bảng, API ngoài, phí vận chuyển hoặc tính toán Java phức tạp, một câu `SET column = column + ...` có thể không đủ. Khi đó cân nhắc **optimistic version check**, **khóa bi quan**, hoặc một **transaction serializable** với retry và thiết kế bất biến liên hàng.

## 7. Java/JDBC: cập nhật nguyên tử và kiểm tra số hàng thực sự thay đổi

Ví dụ adapter ghi trong PostgreSQL:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JdbcInventoryRepository {
    private final DataSource dataSource;

    public JdbcInventoryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean decrementIfAvailable(
            long productId, int quantity) throws SQLException {
        if (productId <= 0 || quantity <= 0) {
            throw new IllegalArgumentException("Tham số không hợp lệ");
        }

        String sql = """
            UPDATE inventory_items
            SET available = available - ?,
                row_version = row_version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
              AND available >= ?
            RETURNING product_id
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setLong(2, productId);
            statement.setInt(3, quantity);

            try (ResultSet rs = statement.executeQuery()) {
                return rs.next(); // true: một hàng đã được cập nhật.
            }
        }
    }
}
~~~

Đoạn code này **chỉ** phù hợp với contract “trừ tồn kho là thao tác độc lập”, khi connection đang ở chế độ autocommit phù hợp và không cần thêm một bản ghi reservation chung transaction. `RETURNING` là cú pháp PostgreSQL, không mặc định có ở mọi backend. Việc trả `true` ở đây xác nhận statement đã được thực hiện theo transaction của connection; nếu cần ghi nhiều thay đổi nguyên tử, phải **quản lý transaction ở cấp use case**.

### Với reservation cần lưu bản ghi cùng transaction

~~~text
BEGIN
  INSERT reservation(idempotency_key, product_id, quantity, ...)
  UPDATE inventory_items
     SET available = available - quantity
   WHERE product_id = ... AND available >= quantity
  nếu UPDATE không cập nhật hàng: ROLLBACK hoặc trả kết quả SOLD_OUT
COMMIT
~~~

Ứng dụng cần phân biệt **hết hàng**, **không tìm thấy**, **unique conflict do yêu cầu lặp** và **lỗi DB tạm thời**. Không gộp tất cả thành HTTP 500, cũng không trả “thành công” sau khi chỉ INSERT reservation mà UPDATE tồn kho thất bại. Nếu statement đầu đã ghi rồi statement sau thất bại, toàn transaction phải rollback khi đó là một bất biến.

## 8. Optimistic locking: cập nhật chỉ khi version chưa đổi

Khi cần đọc dữ liệu, tính logic Java, rồi ghi, có thể lưu một số phiên bản tăng dần `row_version`:

~~~sql
SELECT product_id, available, row_version
FROM inventory_items
WHERE product_id = :productId;

-- Java tính newAvailable từ bản ghi quan sát.

UPDATE inventory_items
SET available = :newAvailable,
    row_version = row_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = :productId
  AND row_version = :expectedVersion
  AND available >= 0
RETURNING row_version;
~~~

Nếu hai request cùng đọc `row_version=7`:

1. A cập nhật thành công, `row_version` tăng lên 8.
2. B thử `WHERE row_version=7` sẽ **không tìm thấy** hàng phù hợp sau khi A commit.
3. B nhận `0 rows`/optimistic conflict, **không** được trả thành công như thể đã ghi.
4. B có thể tải lại bản mới rồi **tính lại toàn bộ quyết định**, hoặc báo 409/conflict theo API contract.

Đây là kiểu **compare-and-set (CAS)**: ghi chỉ khi dữ liệu vẫn ở phiên bản đã quan sát.

### Bảo vệ cả bất biến miền

Nếu `newAvailable` được tính từ input chưa kiểm tra, chỉ check version chưa đủ. Ví dụ request đặt 100 vé khi còn 10, version khớp nhưng Java ghi `-90`; constraint `CHECK (available >= 0)` sẽ từ chối, hoặc nếu không có constraint thì dữ liệu sai. Do đó cần:

- Validate quantity > 0 và policy.
- Kiểm tra số lượng đủ ở trạng thái đã đọc.
- CAS theo version để không ghi dựa trên phiên bản cũ.
- Constraint tại DB làm hàng rào cuối.
- Nếu CAS fail, tải lại và tính lại điều kiện trên trạng thái **mới**, không chỉ lặp câu `UPDATE` với `expectedVersion` cũ.

### Version khác kiểm tra chính giá trị cũ

Với một số bảng đơn giản, có thể dùng:

~~~sql
UPDATE inventory_items
SET available = :newAvailable
WHERE product_id = :productId
  AND available = :oldAvailable;
~~~

Điều kiện này có thể ngăn một số lost update, nhưng có nguy cơ **ABA**: giá trị thay đổi từ 10 → 9 → 10 rồi request cũ vẫn thấy `available=10` và cho rằng dữ liệu chưa đổi. `row_version` tăng trên **mọi thay đổi có liên quan** giúp phát hiện chuỗi thay đổi dù giá trị hiện tại quay về bằng giá trị cũ. Nếu dùng cột version, **mọi writer** — API, batch, script SQL, ORM adapter — phải tuân thủ cơ chế tăng version khi đổi những trường liên quan.

## 9. Java/JDBC: optimistic update không ghi đè phiên bản mới

Ví dụ dưới đây nhận snapshot đã đọc ở tầng application, chuẩn hóa phép tính và cập nhật có kiểm tra phiên bản:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public record InventorySnapshot(
        long productId, int available, long rowVersion) {}

public final class JdbcOptimisticInventory {
    private final DataSource dataSource;

    public JdbcOptimisticInventory(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int saveIfVersionMatches(
            InventorySnapshot snapshot, int quantity)
            throws SQLException {
        if (snapshot == null || quantity <= 0) {
            throw new IllegalArgumentException("Input không hợp lệ");
        }
        if (snapshot.available() < quantity) {
            throw new IllegalStateException("Không đủ tồn kho");
        }

        String sql = """
            UPDATE inventory_items
            SET available = ?,
                row_version = row_version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
              AND row_version = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setInt(1, snapshot.available() - quantity);
            statement.setLong(2, snapshot.productId());
            statement.setLong(3, snapshot.rowVersion());
            return statement.executeUpdate(); // Kỳ vọng đúng 1 hoặc 0.
        }
    }
}
~~~

Phương thức minh họa trả `1` khi thành công, `0` khi snapshot stale hoặc hàng không tồn tại. **Không tự đánh đồng 0 với hết hàng**: phải tải lại từ DB để phân loại nếu nghiệp vụ cần thông báo chính xác. Trong ứng dụng thật nên định nghĩa kiểu kết quả `UPDATED`/`VERSION_CONFLICT`/`NOT_FOUND` hoặc exception chuyên biệt.

Nếu cần tạo reservation và cập nhật inventory cùng nguyên tử, repository nên nhận **connection/transaction context** do application service sở hữu (hoặc dựa vào transaction manager), thay vì mỗi phương thức tự mượn connection và commit riêng như ví dụ đơn lẻ ở trên.

## 10. JPA/Hibernate: `@Version` và cái bẫy của persistence context

Trong ứng dụng JPA, một lỗi thường gặp là đọc một entity managed, thay field rồi để ORM tự phát SQL lúc flush:

~~~java
@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @Column(name = "product_id")
    private Long id;

    @Column(name = "available", nullable = false)
    private int available;

    @Version
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    protected InventoryItem() {}

    public void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalStateException("Không đủ tồn kho");
        }
        available -= quantity;
    }
}
~~~

Khi provider hỗ trợ optimistic locking theo JPA `@Version` và thao tác đúng ngữ cảnh, ORM thường phát một UPDATE có điều kiện version. Nếu version đã đổi do transaction khác, provider thông báo optimistic lock conflict (loại exception và lúc phát sinh phụ thuộc provider/transaction).

~~~java
@Transactional
public void reserve(long productId, int quantity) {
    InventoryItem item = entityManager.find(
            InventoryItem.class, productId);
    if (item == null) {
        throw new IllegalArgumentException("Không có sản phẩm");
    }
    item.reserve(quantity);
    // SQL UPDATE có thể chạy khi flush/commit,
    // nên xung đột không nhất thiết ném ở dòng reserve().
}
~~~

**Cần nhớ:**

- `entityManager.find()` có thể trả entity từ **first-level cache**. Không nên hiểu mỗi lần gọi `find` là đọc lại version mới nhất từ DB.
- `@Version` chỉ có hiệu lực khi mọi đường ghi liên quan đi qua cơ chế version đúng. `UPDATE` native SQL, `@Modifying` bulk update, script ETL hoặc job backfill có thể **không tự tăng version** theo ý bạn.
- Thay đổi nhiều entity có thể làm conflict xuất hiện tại `flush()` hoặc `commit()`, chứ không ngay tại phương thức domain.
- Sau một optimistic conflict/transaction bị rollback, **không reuse entity managed cũ để retry**; bắt đầu transaction mới và tải lại dữ liệu.
- `@Version` không tự bảo vệ invariant trải qua **những hàng khác nhau** nếu mỗi transaction chỉ cập nhật hàng riêng của nó.

### Bulk update có thể phá hợp đồng optimistic locking

Ví dụ một công cụ thực hiện:

~~~sql
UPDATE inventory_items
SET available = available + 5
WHERE product_id = 42;
~~~

Nếu câu này không tăng `row_version`, một entity JPA đã đọc trước đó vẫn giữ version cũ **khớp**, sau đó flush có thể ghi đè thay đổi từ bulk update. Vì vậy phải kiểm tra tất cả writer và thống nhất chính sách version. Khi cần đồng bộ dữ liệu cũ bằng backfill, có thể phải tăng version theo quy tắc và chấp nhận xung đột optimistic nhiều hơn, hoặc thiết kế một giao thức phối hợp khác.

## 11. Pessimistic locking: khóa hàng trước khi ra quyết định

Nếu quyết định yêu cầu đọc nhiều field hoặc thực hiện nhiều câu SQL dưới một invariant cục bộ, có thể khóa hàng **trong cùng transaction** trước khi tính toán:

~~~sql
BEGIN;

SELECT available
FROM inventory_items
WHERE product_id = 42
FOR UPDATE;

-- Application kiểm tra available >= quantity.
-- Application cập nhật inventory và tạo reservation.

UPDATE inventory_items
SET available = :newAvailable,
    row_version = row_version + 1
WHERE product_id = 42;

INSERT INTO reservations(
    reservation_id, product_id, quantity, state
)
VALUES (:reservationId, 42, :quantity, 'RESERVED');

COMMIT;
~~~

`SELECT ... FOR UPDATE` trong PostgreSQL lấy row-level lock thích hợp và giữ đến khi transaction kết thúc. Transaction khác muốn lấy khóa cập nhật không tương thích trên cùng hàng có thể phải chờ. Sau khi transaction đầu commit, transaction sau cần đọc giá trị mới rồi quyết định dựa trên giá trị đó.

### Vì sao không được khóa trong autocommit rồi xử lý sau?

~~~java
// Sai về ý định locking nếu mỗi câu dùng một transaction autocommit:
int value = repository.selectForUpdate(productId); // Lock nhả khi query xong.
callRemoteService(); // Đang không còn giữ lock.
repository.writeNewValue(productId, value - 1);
~~~

Nếu transaction kết thúc ngay sau câu SELECT, khóa không bảo vệ giai đoạn tính toán sau đó. Khóa phải thuộc **cùng transaction** với UPDATE và mọi thao tác cần được điều phối.

**Đừng** giữ row lock trong lúc đợi người dùng, gọi API thanh toán hoặc chờ một HTTP request ngoài hệ thống. Transaction dài làm giảm throughput, tăng lock wait và tạo nguy cơ deadlock/timeout. Nếu side effect ngoài DB là cần thiết, hãy tách pha hoặc dùng saga/outbox theo hợp đồng consistency.

### Dùng `NOWAIT` hay `SKIP LOCKED`?

PostgreSQL có các tùy chọn:

~~~sql
SELECT product_id
FROM inventory_items
WHERE product_id = 42
FOR UPDATE NOWAIT;
~~~

`NOWAIT` cho phép thất bại ngay khi không lấy được khóa hàng theo yêu cầu, thay vì chờ. `SKIP LOCKED` bỏ qua các hàng đang bị khóa, thường hữu ích cho **job queue/worker claim**, nhưng **không tự đúng** cho trường hợp khách đặt chính xác sản phẩm 42: bỏ qua hàng có thể bị hiểu nhầm thành “không có sản phẩm” hoặc “hết chỗ”.

Chọn chính sách chờ, fail fast, retry và timeout theo trải nghiệm người dùng, không chỉ vì một cú pháp trông có vẻ nhanh.

## 12. Java/JDBC: transaction có `SELECT FOR UPDATE` đúng phạm vi

Ví dụ tối thiểu về transaction quản lý tường minh khi cần cập nhật tồn kho và lưu reservation cùng nhau:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class JdbcReservationService {
    private final DataSource dataSource;

    public JdbcReservationService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void reserve(
            long productId, int quantity, UUID reservationId)
            throws SQLException {
        if (productId <= 0 || quantity <= 0 || reservationId == null) {
            throw new IllegalArgumentException("Input không hợp lệ");
        }

        try (Connection c = dataSource.getConnection()) {
            c.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
            c.setAutoCommit(false);
            try {
                int available;
                try (PreparedStatement ps = c.prepareStatement(
                        "SELECT available FROM inventory_items " +
                        "WHERE product_id = ? FOR UPDATE")) {
                    ps.setLong(1, productId);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new IllegalArgumentException(
                                    "Sản phẩm không tồn tại");
                        }
                        available = rs.getInt(1);
                    }
                }
                if (available < quantity) {
                    throw new IllegalStateException("Không đủ tồn kho");
                }

                try (PreparedStatement ps = c.prepareStatement(
                        "UPDATE inventory_items " +
                        "SET available = available - ?, " +
                        "row_version = row_version + 1 " +
                        "WHERE product_id = ? AND available >= ?")) {
                    ps.setInt(1, quantity);
                    ps.setLong(2, productId);
                    ps.setInt(3, quantity);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                                "Bất biến tồn kho không còn đúng");
                    }
                }

                try (PreparedStatement ps = c.prepareStatement(
                        "INSERT INTO reservations " +
                        "(reservation_id, product_id, quantity, state) " +
                        "VALUES (?, ?, ?, 'RESERVED')")) {
                    ps.setObject(1, reservationId);
                    ps.setLong(2, productId);
                    ps.setInt(3, quantity);
                    ps.executeUpdate();
                }
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
~~~

Ví dụ giả định bảng `reservations` có các cột trên và có **unique constraint** trên `reservation_id`. Việc chọn lỗi domain hoặc exception cần được định nghĩa trong ứng dụng thực; ở đây dùng exception để thể hiện toàn transaction rollback.

**Vì sao vừa khóa vừa kiểm tra `available >= ?`?** Khóa là cơ chế phối hợp chính khi đọc–quyết định; điều kiện trong UPDATE và `CHECK` bảo vệ thêm trước lỗi code hoặc đường ghi không tuân thủ. Với một phép trừ đơn giản, có thể bỏ `SELECT FOR UPDATE` và dùng **một conditional UPDATE** như phần 6, tránh thêm round trip/lock hold time không cần thiết.

Nếu `c.commit()` ném ngoại lệ vì mất kết nối, kết quả có thể **chưa rõ**. `rollback()` trong catch là nỗ lực làm sạch transaction, không chứng minh server chưa commit. Khi cần retry có tác động nghiệp vụ, phải dùng reservation ID/idempotency key ổn định và kiểm tra trạng thái hiện tại trước.

## 13. Isolation level: không dùng tên mức cô lập như phép màu

Cần hiểu **hành vi thực tế của database** với tổ hợp SELECT/UPDATE, không chỉ học thuộc “READ COMMITTED tốt hay xấu”.

Với PostgreSQL:

| Isolation | Ý nghĩa chính trong bối cảnh này | Lưu ý |
| --- | --- | --- |
| **READ COMMITTED** | Mỗi statement thấy snapshot phù hợp lúc bắt đầu statement; statement ghi có xử lý xung đột khóa theo semantics DB | Một SELECT cũ + UPDATE gán hằng số có thể lost update |
| **REPEATABLE READ** | Transaction dùng snapshot ổn định hơn; xung đột cập nhật hàng đã đổi từ transaction khác có thể gây serialization failure | Phải retry transaction từ đầu; không dùng bản đọc cũ |
| **SERIALIZABLE** | DB cố bảo đảm kết quả tương đương một thứ tự tuần tự; có thể abort transaction khi phát hiện cấu trúc xung đột | Ứng dụng phải xử lý `SQLSTATE 40001` và retry toàn transaction |

Ở PostgreSQL, `READ UNCOMMITTED` thực tế có hành vi tương tự `READ COMMITTED`. Engine khác có thể có quy tắc khác, nhất là cơ chế MVCC/snapshot và lock; không suy từ bảng trên rằng mọi sản phẩm database vận hành giống nhau.

### Vì sao READ COMMITTED không đủ cho đọc–ghi lại?

~~~sql
-- Transaction A:
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT available FROM inventory_items WHERE product_id = 42; -- 10

-- B ở transaction khác cũng đọc 10, rồi commit SET available=9.

UPDATE inventory_items
SET available = 9
WHERE product_id = 42;
COMMIT;
~~~

`UPDATE` cuối có thể ghi 9 sau khi B đã ghi 9. Dù hai transaction có khóa hàng tại thời điểm ghi, **logic tính ở Java đã sử dụng giá trị cũ**.

### Tăng isolation có trade-off

- `SERIALIZABLE` có thể làm tăng lượng transaction bị rollback/retry khi contention cao.
- Retry phải thực hiện lại **toàn bộ transaction và phép đọc**, không chỉ lặp một câu UPDATE trong transaction đã lỗi.
- Không thực hiện thanh toán/email bên ngoài trực tiếp bên trong một transaction có thể bị retry, nếu thao tác đó không thể hoàn tác hoặc không có idempotency.
- Không được đổi isolation trong production chỉ vì một lỗi mà không kiểm tra cả workload, lock duration và các invariant liên quan.

Nhiều trường hợp phép trừ một hàng được giải quyết **đơn giản và hiệu quả hơn** bằng atomic conditional UPDATE ở `READ COMMITTED`. Isolation mạnh hơn là công cụ cho bài toán rộng hơn, không phải biện pháp thay thế thiết kế đúng mọi câu SQL.

## 14. Bất biến liên hàng: khi khóa một hàng chưa đủ

Giả sử yêu cầu của hệ thống trực ca là **luôn có ít nhất một bác sĩ trực**:

~~~text
doctors
  (doctor_id=1, on_call=true)
  (doctor_id=2, on_call=true)
~~~

Hai transaction:

1. A đếm có hai người trực, thấy còn người thứ hai và tắt trạng thái của bác sĩ 1.
2. B cũng đếm hai người trực, thấy còn bác sĩ 1 và tắt trạng thái của bác sĩ 2.
3. A và B cập nhật **hai hàng khác nhau** rồi commit.

Sau cùng không còn ai trực. Một CAS riêng cho mỗi hàng bác sĩ **không phát hiện** vì mỗi transaction ghi một hàng khác, không tranh phiên bản trên cùng hàng.

~~~mermaid
sequenceDiagram
    participant A as Tx A
    participant DB as Database
    participant B as Tx B
    A->>DB: SELECT COUNT on_call = 2
    B->>DB: SELECT COUNT on_call = 2
    A->>DB: UPDATE doctor 1 set false
    B->>DB: UPDATE doctor 2 set false
    A->>DB: COMMIT
    B->>DB: COMMIT
    Note over DB: Bất biến liên hàng bị phá
~~~

Đây là **write skew**, không phải lost update trên một hàng. Các hướng xử lý:

- **Serializable transaction** với retry khi có serialization failure.
- Khóa một **bản ghi điều phối chung** hoặc tập hàng được chọn theo thứ tự nhất quán, nếu giao thức thật sự bao phủ mọi thay đổi liên quan.
- Thiết kế schema hoặc domain invariant có thể thực thi bằng unique/check/foreign key/exclusion constraints khi phù hợp.
- Gom aggregate hoặc bộ đếm invariant về một bản ghi được cập nhật nguyên tử, nếu chấp nhận được contention.

Không thể dùng một `@Version` trên bác sĩ A để bảo vệ quyết định dựa trên bác sĩ B. Phải xác định **bất biến nằm ở đâu** và cơ chế kiểm soát đồng thời phủ đúng phạm vi đó.

## 15. Check-then-insert: kiểm tra tồn tại cũng là read–modify–write

Không chỉ các phép cộng/trừ, thao tác tạo tài nguyên thường sai theo mẫu:

~~~java
if (!users.existsByEmail(email)) {
    users.insert(email); // Hai request có thể cùng vượt qua if.
}
~~~

Giữa câu `SELECT EXISTS` và `INSERT`, request khác có thể đã tạo user cùng email. Một **unique constraint/index** ở DB là hàng rào đúng đắn quan trọng:

~~~sql
CREATE UNIQUE INDEX users_email_unique_idx
ON users (normalized_email);
~~~

Application có thể dùng:

~~~sql
INSERT INTO users(normalized_email, display_name)
VALUES (:email, :displayName)
ON CONFLICT (normalized_email) DO NOTHING
RETURNING user_id;
~~~

Phải phân biệt:

- **Có hàng được tạo:** request này thắng cuộc.
- **Không có hàng được tạo:** hàng cùng email đã tồn tại; đọc lại và quyết định có trả existing user hay từ chối theo hợp đồng.
- **Lỗi khác:** schema/connection/constraint khác, không được nuốt làm “đã tồn tại”.

Tùy nghiệp vụ, việc trùng email có thể là lỗi xác thực hoặc bình thường khi retry; cần thêm **idempotency key/payload fingerprint** nếu không thể đồng nhất trùng email với trùng ý định.

### Vì sao isolation mạnh không thay unique constraint?

Serializable có thể giúp loại một số race, nhưng unique constraint là diễn đạt **bất biến dữ liệu lâu dài** ở điểm lưu trữ, còn hiệu lực với mọi writer. Không nên chỉ dựa vào logic kiểm tra ở API và hy vọng mọi job/import luôn chạy qua cùng service.

## 16. Cập nhật trạng thái: không cho chuyển ngược do bản đọc cũ

Không phải mọi read–modify–write là phép số học. Ví dụ order:

~~~text
PENDING → PAID → SHIPPED
PENDING → CANCELLED
~~~

Hai request cạnh tranh:

- Payment handler đọc `PENDING`, chuẩn bị đổi sang `PAID`.
- Cancellation handler đọc `PENDING`, chuẩn bị đổi sang `CANCELLED`.
- Nếu chỉ `UPDATE orders SET status = ? WHERE id = ?`, request đến sau có thể **ghi đè trạng thái đã xác nhận**.

Sửa bằng chuyển trạng thái có điều kiện:

~~~sql
UPDATE orders
SET status = 'PAID',
    row_version = row_version + 1
WHERE id = :orderId
  AND status = 'PENDING';
~~~

Và lệnh hủy:

~~~sql
UPDATE orders
SET status = 'CANCELLED',
    row_version = row_version + 1
WHERE id = :orderId
  AND status = 'PENDING';
~~~

Nếu cả hai tranh cùng hàng, chỉ một lệnh có thể thành công từ trạng thái `PENDING` theo semantics locking/recheck của PostgreSQL tại `READ COMMITTED`. Lệnh kia nhận `0 rows` và phải xử lý theo quy tắc nghiệp vụ, **không** tự viết đè.

Nếu state machine cho phép nhiều bước chuyển khác nhau hoặc có dữ liệu phụ thuộc, dùng optimistic version hay một aggregate service có transaction rõ ràng. Các tác động ngoài DB như hoàn tiền/gửi hàng cần idempotency và saga/outbox để tránh “DB đã hủy nhưng provider vẫn thu tiền”.

## 17. Cache, replica và distributed lock: đừng dùng nguồn đọc cũ làm thẩm quyền

Một request có thể đọc giá trị từ Redis cache hoặc read replica:

~~~text
Redis: available = 10  (đã cũ)
Primary PostgreSQL: available = 8
Java: tính 9 từ cache rồi UPDATE primary SET available = 9
~~~

Đây là rủi ro **stale read** dẫn đến ghi đè, kể cả khi ứng dụng chỉ có một thread. Cần tách:

- **Nguồn có thẩm quyền** cho việc quyết định và commit.
- **Nguồn phục vụ đọc nhanh** có thể chậm đồng bộ.
- **Giao thức ghi** vẫn phải xác thực điều kiện tại DB có thẩm quyền.

Atomic conditional UPDATE hoặc CAS trên version của primary giúp ngăn một số kiểu ghi cũ. Nhưng để làm đúng, version từ cache phải được kiểm tra với version hiện tại trên primary, không được tin cache khi quyết định “còn đủ hàng”.

### Redis lock hoặc mutex phân tán có giải quyết hết không?

Khóa trong Redis có thể giúp điều tiết concurrency nếu được thiết kế đúng, nhưng **không thay thế guard ở DB**:

- Lock có thể hết lease trong khi worker vẫn chạy, hoặc một worker bị pause rồi tỉnh lại với quyền ghi cũ.
- Một instance có thể đi vòng ngoài cơ chế lock (job/admin script/service khác).
- Network partition và timeout có thể khiến người giữ lock không biết lease còn hiệu lực không.
- Khi cần bảo vệ trước **stale lock holder**, dùng **fencing token/version** được kiểm tra tại nguồn ghi có thẩm quyền; token chỉ có ích khi DB thực sự từ chối token cũ.

Đừng tạo một hệ khóa phân tán phức tạp chỉ để thay thế phép `UPDATE ... SET available = available - ? WHERE available >= ?` vốn có thể làm nguyên tử trong database.

## 18. Idempotency: retry cùng yêu cầu không được trừ tồn kho hai lần

Khi client gửi yêu cầu giữ 1 sản phẩm, server có thể **commit thành công nhưng mất kết nối trước khi trả response**. Client thấy timeout và thử lại. Nếu lần thử lại tiếp tục chạy `available = available - 1`, số tồn kho giảm **hai** dù khách chỉ yêu cầu **một** đơn.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Order Service
    participant DB as PostgreSQL
    C->>S: Reserve (key=R123)
    S->>DB: UPDATE inventory -1 + INSERT reservation
    DB-->>S: COMMIT thành công
    Note over C,S: Phản hồi bị mất
    C->>S: Retry cùng key=R123
    S->>DB: Không được trừ lần hai
    DB-->>S: Trả kết quả đã ghi hoặc trạng thái hiện tại
~~~

Để đạt được mục tiêu **một ý định chỉ tác động một lần**, có thể dùng một unique key bền vững:

~~~sql
CREATE TABLE reservations (
    reservation_id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES inventory_items(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    state TEXT NOT NULL CHECK (state IN ('RESERVED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Hợp đồng:

1. Client cung cấp một `reservation_id` ổn định cho mọi lần retry của **cùng ý định**; server xác minh danh tính/phạm vi và payload gắn với ID này.
2. Trong **cùng transaction**, server claim/check reservation ID và chỉ trừ tồn kho nếu đây là yêu cầu mới hợp lệ.
3. Nếu ID đã tồn tại, kiểm tra payload/fingerprint và trả kết quả cũ khi đúng cùng ý định; nếu ID trùng nhưng payload khác, báo conflict.
4. Nếu UPDATE tồn kho thất bại vì hết hàng, toàn transaction xử lý theo policy đã định; không để reservation “thành công” nhưng inventory không đổi.
5. Nếu kết quả commit chưa rõ, **đọc lại trạng thái bằng connection mới** trước khi retry bất kỳ thao tác có side effect.

**Đừng dùng một unique key mà không kiểm tra payload.** Nếu khách vô tình dùng lại ID cũ cho một sản phẩm khác, trả “đã đặt” có thể xác nhận sai mục tiêu. Đồng thời, unique key **không thay thế CAS/atomic UPDATE** cho những yêu cầu khác nhau tranh cùng inventory.

### Hai câu hỏi tách biệt

- **Concurrency:** A đặt 1, B đặt 1 (hai request ID khác nhau). Cả hai phải trừ tổng cộng 2 hoặc một request bị từ chối khi không đủ.
- **Idempotency:** A gửi lại **cùng request ID** vì timeout. Lần hai không được trừ thêm.

Thiết kế an toàn phải giải quyết **cả hai**. Chỉ thêm `@Version` mà không có idempotency vẫn có thể trừ hai lần sau timeout; chỉ thêm idempotency key mà không kiểm soát update đồng thời vẫn có thể làm mất một phép trừ giữa A và B.

## 19. Retry optimistic conflict, deadlock và serialization failure như thế nào?

Không phải mọi lỗi cần retry. Ví dụ:

| Kết quả | Diễn giải | Hành động |
| --- | --- | --- |
| CAS cập nhật `1 row` | State/version đã thỏa điều kiện tại điểm ghi | Tiếp tục transaction hoặc commit |
| CAS cập nhật `0 row` | Bản ghi đã đổi, không còn, hoặc điều kiện miền không đạt | Đọc lại, tính lại, phân loại; có thể từ chối hoặc retry hữu hạn |
| Unique violation ở reservation ID | Có thể là retry cùng ID hoặc collision payload | Đọc theo ID, đối chiếu payload rồi trả existing/conflict |
| PostgreSQL `40P01` (deadlock detected) | Một transaction bị hủy để phá deadlock | Retry **toàn transaction** nếu an toàn, có backoff |
| PostgreSQL `40001` (serialization failure) | Snapshot/lịch thực thi bị từ chối | Retry transaction mới với các lần đọc mới |
| Lock timeout | Không lấy được tài nguyên trong giới hạn | Phân tích tải; retry giới hạn nếu nghiệp vụ cho phép |
| Lỗi schema, quyền, constraint dữ liệu sai | Không phải transient contention | Sửa code/config/dữ liệu, không retry vô hạn |
| Kết nối mất ở thời điểm `COMMIT` | Kết quả có thể chưa rõ | Reconnect, tra idempotency key/trạng thái, không giả định rollback |

Một retry loop đúng về mặt khái niệm:

~~~text
for attempt = 1..maxAttempts:
    begin NEW transaction
    read fresh state/versions and required domain data
    validate preconditions on this state
    execute conditional/locked updates
    persist idempotency result and related changes
    COMMIT
    return result

    on retriable serialization/deadlock conflict:
        rollback transaction if possible
        backoff + jitter, respect request deadline
        retry with FRESH reads

    on business rule failure (sold out, invalid state):
        return a stable business outcome; do not spin

    on unknown commit outcome:
        lookup durable request ID/result before attempting write
        reconcile with DB/external provider as required
~~~

**Không retry ngay trong transaction đã lỗi**: với PostgreSQL, sau nhiều lỗi SQL, transaction ở trạng thái aborted cho đến rollback. Đọc/ghi tiếp trong transaction đó gây lỗi tiếp và có thể che nguyên nhân ban đầu.

### Retry không được nhân bản external side effects

Giả sử trước khi commit, service gọi payment provider `charge()`. Transaction bị serialization failure rồi retry. Nếu không có protocol idempotency, lần thứ hai có thể thu tiền **lần nữa** dù DB chỉ commit một order.

Tốt hơn, xác định ranh giới phù hợp:

- Transaction cục bộ cập nhật inventory/reservation/outbox atomically.
- Sau commit, worker xử lý event và gọi provider với **idempotency key ổn định**.
- Consumer có inbox/deduplication khi xử lý at-least-once delivery.
- Nếu provider outcome unknown, tra cứu kết quả thực thay vì gọi charge mù.

Đây là một lý do transaction isolation không tự thay thế thiết kế **distributed consistency**.

## 20. Giới hạn tính đúng đắn: một test concurrency phải tái hiện được race

Unit test tuần tự:

~~~java
reserve(42, 1);
reserve(42, 1);
assertEquals(8, inventoryRepository.readAvailable(42));
~~~

có thể **PASS** cả khi implementation read–modify–write sai, vì request thứ hai đọc sau khi request đầu đã ghi.

Một test tốt cần ép hai transaction cùng đọc **cùng bản cũ** rồi ghi theo lịch có kiểm soát:

~~~mermaid
sequenceDiagram
    participant T1 as Tx 1
    participant DB as DB
    participant T2 as Tx 2
    T1->>DB: SELECT available, version
    DB-->>T1: 10, 7
    T2->>DB: SELECT available, version
    DB-->>T2: 10, 7
    Note over T1,T2: Barrier: cả hai đã đọc xong
    T1->>DB: UPDATE CAS version=7
    DB-->>T1: 1 row, commit
    T2->>DB: UPDATE CAS version=7
    DB-->>T2: 0 rows
    Note over T1,T2: Tranh chấp được phát hiện, không lost update
~~~

**Yêu cầu khi test:**

1. Sử dụng **hai connection/transaction khác nhau** với PostgreSQL thật, không phải hai method call dùng chung EntityManager.
2. Dùng `CountDownLatch`/barrier để đặt thời điểm “đã đọc xong”; tránh chỉ `Thread.sleep()` rồi hy vọng race xảy ra.
3. Bắt cả exception và affected row count; không để thread chết im lặng làm test xanh giả.
4. Đặt timeout cho barrier/future để test không treo vô hạn.
5. Kiểm tra **giá trị DB cuối** và **số request được phép xác nhận thành công**.
6. Chạy lại với atomic UPDATE, CAS và pessimistic lock; mỗi chiến lược có kỳ vọng khác nhau.
7. Test một request hết hàng, một request retry cùng idempotency key và trường hợp connection mất sau commit.

## 21. JUnit 5 + PostgreSQL: tái hiện lost update và chứng minh CAS ngăn ghi đè

Ví dụ dưới đây là một integration test tập trung vào race, giả định project đã có **JUnit Jupiter**, **Testcontainers PostgreSQL** và JDBC driver tương thích. Dùng một database test độc lập; không chạy trên dữ liệu production.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class LostUpdateIT {
    @Container
    static final PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");

    Connection connect() throws SQLException {
        return DriverManager.getConnection(
                db.getJdbcUrl(), db.getUsername(), db.getPassword());
    }

    @BeforeEach
    void reset() throws SQLException {
        try (Connection c = connect();
             Statement s = c.createStatement()) {
            s.execute("""
                CREATE TABLE IF NOT EXISTS inventory_items (
                    product_id BIGINT PRIMARY KEY,
                    available INTEGER NOT NULL CHECK (available >= 0),
                    row_version BIGINT NOT NULL DEFAULT 0
                )
                """);
            s.execute("DELETE FROM inventory_items");
            s.execute("""
                INSERT INTO inventory_items(product_id, available, row_version)
                VALUES (42, 10, 7)
                """);
        }
    }

    record Snapshot(int available, long version) {}

    Snapshot read(Connection c) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "SELECT available, row_version FROM inventory_items " +
                "WHERE product_id = 42");
             ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) throw new IllegalStateException("Missing row");
            return new Snapshot(rs.getInt(1), rs.getLong(2));
        }
    }

    int writeIfVersionMatches(Connection c, Snapshot old)
            throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "UPDATE inventory_items SET available = ?, " +
                "row_version = row_version + 1 " +
                "WHERE product_id = 42 AND row_version = ?")) {
            ps.setInt(1, old.available() - 1);
            ps.setLong(2, old.version());
            return ps.executeUpdate();
        }
    }

    @Test
    void twoStaleReadsCannotBothOverwrite() throws Exception {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            java.util.concurrent.Callable<Integer> task = () -> {
                try (Connection c = connect()) {
                    c.setAutoCommit(false);
                    Snapshot snapshot = read(c);
                    bothRead.countDown();
                    if (!mayWrite.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Timed out");
                    }
                    int affected = writeIfVersionMatches(c, snapshot);
                    c.commit();
                    return affected;
                }
            };
            Future<Integer> first = executor.submit(task);
            Future<Integer> second = executor.submit(task);

            assertTrue(bothRead.await(10, TimeUnit.SECONDS));
            mayWrite.countDown();

            int sum = first.get(10, TimeUnit.SECONDS)
                    + second.get(10, TimeUnit.SECONDS);
            assertEquals(1, sum); // Một write bị CAS từ chối.
            try (Connection c = connect()) {
                assertEquals(9, read(c).available());
                assertEquals(8L, read(c).version());
            }
        } finally {
            mayWrite.countDown(); // Không để worker mắc kẹt khi assert lỗi.
            executor.shutdownNow();
        }
    }
}
~~~

**Điều test chứng minh:** khi hai request đã đọc cùng `version=7` và cố ghi kết quả tính từ snapshot cũ, chỉ **một** ghi được commit. Application còn phải quyết định có retry transaction còn lại với snapshot mới để đạt tổng `available=8` hay trả conflict. Test này **không** coi cả hai yêu cầu đã đặt vé thành công; nếu use case yêu cầu cả hai thành công khi còn đủ hàng, hãy bổ sung vòng retry có giới hạn hoặc dùng atomic UPDATE.

### Những giới hạn của ví dụ

- `@BeforeEach` xóa dữ liệu test theo điều kiện dùng riêng một container/table; không chạy đồng thời những test khác dùng chung bảng với fixture tương tự.
- `Connection.close()` khi chưa commit có rollback theo driver/DB semantics tương ứng, nhưng ứng dụng thật nên chủ động rollback trong catch và đóng connection có kiểm soát.
- Nếu worker gặp SQLException, future sẽ ném `ExecutionException`; test sẽ thất bại thay vì coi như một CAS conflict hợp lệ. Với isolation cao hơn, cần xây dựng kỳ vọng retry cho `40001`.
- Version của PostgreSQL, cấu hình isolation và driver trong CI phải tương thích môi trường cần kiểm chứng. H2/SQLite không thay thế được ngữ nghĩa lock/MVCC của PostgreSQL.
- Đây là test với **CAS**. Muốn chứng minh anti-pattern thực sự mất cập nhật, viết test riêng cố tình dùng `SET available = ? WHERE product_id = 42` với hai snapshot đã đọc: thường cả hai thành công và giá trị cuối là 9, nhưng test đó chỉ nên chạy trên DB thử nghiệm.

### Test invariant nghiệp vụ đầy đủ

Sau khi xây API thực có reservation IDs, đừng chỉ assert `available`. Kiểm tra đồng thời:

~~~text
initial_available = 10
successful_distinct_reservations = 2
final_available = 8
reservation_rows_created = 2
duplicate_reservation_ids = 0
failed_reservations_have_no_inventory_effect = true
~~~

Nếu kết quả commit hoặc network bị mất, đối chiếu trạng thái bền vững theo reservation ID trước khi đếm thành công/thất bại. Quan sát một counter in-memory của Java không đủ để chứng minh toàn bộ workflow đúng.

## 22. Giám sát: nhận diện lỗi đã xảy ra và rủi ro đang tăng

Lost update thường là **silent data corruption**: không có exception, chỉ số DB CPU và error rate vẫn bình thường. Cần quan sát **bất biến nghiệp vụ** kết hợp chẩn đoán transaction:

| Chỉ số/kiểm tra | Ý nghĩa | Cảnh giác |
| --- | --- | --- |
| `inventory_negative_rows` | Có hàng tồn kho âm | Bắt một loại lỗi, **không** bắt lost update ghi 9 thay vì 8 |
| Số reservation thành công so với lượng tồn kho đã trừ | Phát hiện thiếu decrement | Cần xác định baseline, replenishment và cancellation |
| `optimistic_conflict_total` | Bao nhiêu CAS cập nhật 0 hàng vì stale version | Conflict nhiều không tự chứng minh dữ liệu sai |
| Deadlock/serialization retries | Tải contention/transaction design | Retry thành công có thể không ảnh hưởng người dùng |
| Row lock wait / transaction duration | Cơ chế chờ và critical section | Cao có thể gây timeout, không đồng nghĩa lost update |
| Duplicate effect reconciliation | Có charge/reservation trùng request ID | Cần nguồn bền vững và payload fingerprint |
| `unknown_commit_outcomes` | Bao nhiêu kết quả chưa xác định được | Không mặc định unknown là rollback |
| Consistency-check last success | Job đối soát có còn hoạt động? | Metric mismatch bằng 0 khi job đã chết không đáng tin |

Ví dụ với hệ chỉ trừ tồn kho cho reservation và cho phép replenishment/cancel, invariant phải xét **đầy đủ các loại thay đổi**:

~~~text
expected_available
  = initial_stock
  + committed_replenishments
  + released_reservations
  - committed_new_reservations
  - other_authorized_adjustments
~~~

Không thể chỉ lấy count của bảng reservations rồi trừ từ tồn đầu ngày nếu có nhập kho, hủy đơn hoặc sửa lịch sử. Nếu phát hiện mismatch, giữ bằng chứng và correction theo giao thức kiểm soát; không chạy `UPDATE inventory SET available = ...` đại trà chỉ từ một metric chưa được đối chiếu.

### Log kỹ thuật không đồng nghĩa bằng chứng nghiệp vụ

Một log `"executeUpdate success, affectedRows=1"` không chứng minh số lượng trừ đúng. Gắn audit event với `reservation_id`, product ID, version trước/sau và trạng thái commit theo chính sách bảo mật; tránh đưa dữ liệu cá nhân hoặc request ID vào Prometheus labels có cardinality cao.

## 23. Chọn giải pháp theo hình dạng bài toán

| Bài toán | Lựa chọn ưu tiên | Vì sao | Khi phải cân nhắc thêm |
| --- | --- | --- | --- |
| Tăng counter, trừ tồn một hàng | **Atomic conditional UPDATE** | Ít round trips, điều kiện kiểm tra ngay tại DB | Idempotency, ghi record liên quan trong transaction |
| Tính logic Java trên một aggregate có version | **Optimistic locking** | Không giữ lock qua thời gian tính, phát hiện snapshot stale | Conflict/retry, các writer native SQL |
| Đọc–đổi nhiều field/hàng đã biết, tranh chấp vừa phải | **SELECT FOR UPDATE** trong transaction ngắn | Ra quyết định sau khi giữ khóa cần thiết | Deadlock, lock ordering, throughput |
| Invariant phụ thuộc nhiều hàng hoặc predicate động | **Serializable / schema redesign** | Phạm vi xung đột lớn hơn một version/hàng | Retry, chi phí isolation, constraint |
| Tạo resource duy nhất | **UNIQUE constraint + insert** | DB thực thi bất biến mọi writer | ID/payload của request retry |
| Nhiều service/DB hoặc side effect ngoài | **Transaction local + outbox/saga/idempotency** | Không có atomic commit chung mặc định | Reconciliation và unknown outcome |
| Đọc qua replica/cache rồi ghi primary | **CAS/guard tại primary** | Không tin snapshot cũ để ghi mù | Read-your-writes và cache invalidation |

**Không tồn tại một lựa chọn tối ưu cho mọi tình huống.** Cập nhật nguyên tử đơn giản thường là điểm xuất phát tốt cho counter một hàng; optimistic lock phù hợp khi xung đột hiếm; khóa bi quan có thể tốt khi xung đột cao và xử lý ngắn; invariant liên hàng cần cơ chế bao phủ tập dữ liệu lớn hơn.

Những tiêu chí quyết định nên đo:

- Tỷ lệ conflict và phần trăm retry thành công trước deadline.
- Độ dài transaction, lock wait và throughput dưới tải đồng thời.
- Số row/aggregate phải được cập nhật atomically.
- Nhu cầu kết hợp với side effect bên ngoài.
- Rủi ro dữ liệu sai và yêu cầu audit.
- Số writer độc lập có thể bỏ qua cơ chế version/lock nếu không được quản trị.

## 24. Những anti-pattern cần nhận diện trong review

| Anti-pattern | Vấn đề | Hướng sửa |
| --- | --- | --- |
| `find() → set(x−1) → save()` không điều kiện | Lost update | Atomic UPDATE hoặc CAS |
| Cho rằng `@Transactional` tự khóa mọi dữ liệu đã đọc | Transaction không tự bảo đảm mọi invariant | Xác định isolation và locking |
| `UPDATE ... WHERE id=?` với hằng số tính từ bản đọc cũ | Che mất cập nhật đồng thời | `SET field=field+delta` hoặc guard version |
| CAS trả `0 row` nhưng API vẫn báo thành công | Không phát hiện request không ghi được | Trả conflict/retry sau khi đọc lại |
| CAS fail thì lặp UPDATE với same expected version | Conflict lặp vô ích | Reload và revalidate |
| So old value thay cho version mà bỏ qua ABA | Có thể nhìn nhầm dữ liệu quay lại giá trị cũ | Version/fencing token đúng nghĩa |
| `SELECT FOR UPDATE` trên autocommit rồi xử lý sau | Khóa đã nhả trước UPDATE | Giữ cùng transaction |
| Giữ DB transaction khi gọi payment/email | Lock lâu, timeout, deadlock | Outbox/saga, tách side effect |
| Chỉ tăng version ở ORM, quên raw SQL/backfill | Entity giữ version cũ có thể ghi đè cập nhật mới | Thống nhất mọi writer |
| Dùng CAS một hàng cho invariant hai hàng khác nhau | Không chặn write skew | Serializable/coordination |
| `SELECT EXISTS` rồi INSERT không unique constraint | Trùng resource | Unique key, conflict handling |
| Đọc cache/replica cũ rồi ghi đè primary | Stale write | Guard tại nguồn có thẩm quyền |
| Tưởng Redis lock giải quyết mọi tranh chấp | Lease expiry/stale holder | Fencing/version ở DB |
| Retry giao dịch có gọi provider mà không idempotency | Thu tiền/gửi event trùng | Idempotent provider call + outbox |
| Dùng `synchronized` trong một pod và coi toàn cluster an toàn | Chỉ khóa JVM cục bộ | DB concurrency protocol |
| Test tuần tự rồi kết luận concurrency đúng | Không ép interleaving gây lỗi | Barrier + hai transaction thật |
| Chỉ nhìn CHECK non-negative để kết luận đủ tồn | Lost update có thể để lại số dương hợp lệ | Đối soát reservation và stock movements |

### Một câu hỏi review hữu ích

Khi gặp code:

~~~java
var current = repository.findById(id);
var next = calculate(current, command);
repository.save(next);
~~~

Hãy hỏi: **“Nếu một request khác commit vào cùng thời điểm giữa `find` và `save`, câu `save` sẽ phát hiện điều đó bằng cách nào?”** Nếu không trả lời được bằng SQL có điều kiện, version, lock hoặc một giao thức đồng thời tương đương, có khả năng tồn tại lỗ hổng.

## 25. Bài tập: hai request đặt vé cuối cùng

Một hệ đặt vé có bảng `ticket_inventory(show_id, available, row_version)`, ban đầu:

~~~text
show_id = 77
available = 1
row_version = 12
~~~

Hai khách A và B cùng gửi request giữ **một** vé, mỗi request có một `reservation_id` riêng.

**Câu hỏi:**

1. Nếu cả hai đọc `available=1` rồi cùng ghi `0` theo `WHERE show_id=77`, có thể xảy ra kết quả sai nào?
2. Viết một câu PostgreSQL `UPDATE` nguyên tử để chỉ một request có thể thành công khi còn 1 vé.
3. Với optimistic version, điều kiện `WHERE` cần chứa gì? Request còn lại nhận kết quả nào?
4. Nếu sử dụng `SELECT ... FOR UPDATE`, transaction bắt đầu và kết thúc ở đâu? Có nên gọi payment provider khi đang giữ khóa không?
5. Tại sao `CHECK (available >= 0)` không đủ chặn lost update của hai lệnh gán `0`?
6. Nếu client A timeout sau `COMMIT` rồi retry cùng `reservation_id`, làm sao không giữ thêm một vé?
7. Nếu A cập nhật inventory nhưng INSERT reservation thất bại, cơ chế nào giúp dữ liệu không lệch?
8. Nếu chỉ chạy test gọi `reserve()` hai lần liên tiếp, tại sao vẫn bỏ sót bug?
9. Nếu reservation tồn tại ở DB nhưng event gửi kho vé bị mất, transaction isolation có tự giải quyết không?
10. Nếu một job sửa inventory bằng native SQL mà không tăng `row_version`, điều gì có thể xảy ra với entity JPA dùng `@Version`?

### Hướng giải và ví dụ SQL

Một câu UPDATE nguyên tử:

~~~sql
UPDATE ticket_inventory
SET available = available - 1,
    row_version = row_version + 1
WHERE show_id = 77
  AND available >= 1
RETURNING available, row_version;
~~~

Một request nhận một hàng, request kia nhận **0 hàng** sau khi điều kiện được kiểm tra trên trạng thái mới; chỉ request nhận một hàng mới được xác nhận giữ vé, nếu toàn transaction liên quan commit thành công.

Với optimistic locking, hai request cùng đọc `row_version=12`; chỉ một lệnh UPDATE có `WHERE show_id=77 AND row_version=12` thành công. Request còn lại phải tải lại, thấy không còn vé và trả kết quả hết vé, **không** báo conflict rồi tự retry vô hạn.

Với pessimistic lock, khóa tồn kho bằng `FOR UPDATE` và ghi reservation trong **cùng transaction ngắn**, commit rồi mới thực hiện side effects ngoài qua một giao thức thích hợp. Unique `reservation_id` cùng transaction bảo vệ retry; outbox bảo vệ ý định phát event sau commit; consumer dùng dedupe nếu nhận lặp.

`CHECK (available >= 0)` không thấy lỗi khi hai request cùng gán `0`: giá trị 0 hợp lệ nhưng một vé đã bị xác nhận cho hai khách. Integration test cần ép hai transaction cùng đọc 1, cho ghi cạnh tranh, đối chiếu số reservation thành công với lượng vé đã trừ. Một job native SQL không tăng version có thể làm một snapshot JPA cũ **vẫn khớp version** và ghi đè trạng thái mới.

## 26. Checklist trước khi triển khai read–modify–write

1. **Bất biến:** nói được điều kiện dữ liệu nào phải luôn đúng, phạm vi một hàng hay nhiều hàng?
2. **Nguồn sự thật:** giá trị quyết định được đọc từ primary, cache hay replica; nguồn có thể stale không?
3. **Giao thức ghi:** dùng atomic mutation, CAS/version, lock hoặc serializable; có lý do chọn rõ ràng không?
4. **Điều kiện nghiệp vụ:** `WHERE` kiểm tra quyền, trạng thái, số lượng, giới hạn và version thích hợp?
5. **Kết quả ghi:** affected row count bằng 0 hay optimistic exception được xử lý như thế nào?
6. **Transaction:** các thay đổi tạo cùng bất biến commit/rollback cùng nhau? Có giữ lock quá lâu không?
7. **Mọi writer:** API, import, backfill, admin script, job và ORM có tuân thủ version/guard không?
8. **Isolation:** đã xác minh semantics của PostgreSQL/driver/isolation level thực tế, không chỉ tên mức?
9. **Retry:** có giới hạn, backoff, deadline, tải lại trạng thái; không retry lỗi nghiệp vụ vô tận?
10. **Unknown commit:** có ID yêu cầu bền vững để biết đã commit trước khi retry side effect?
11. **Idempotency:** cùng request ID không trừ/thu tiền hai lần; payload khác cùng ID bị conflict?
12. **Ngoài DB:** outbox, broker, payment, cache và các consumer có cơ chế đối soát/khử trùng?
13. **Schema:** constraints/unique/version đúng và có migration trên dữ liệu cũ?
14. **Concurrency test:** có hai transaction thật, barrier, timeout, race khi hết hàng và sau commit?
15. **Quan sát:** có metric optimistic conflicts, retries, lock wait và invariant reconciliation?
16. **Khôi phục:** khi phát hiện sai, có runbook bảo toàn bằng chứng, đối soát và correction an toàn?

**Kết luận:** lỗi **đọc rồi ghi lại giá trị mà không kiểm soát đồng thời** không xuất phát từ việc Java tính sai `10 - 1`, mà từ việc nhiều request **cùng dựa vào một snapshot cũ nhưng đều có thể commit**. Chữa đúng bằng cách đưa điều kiện kiểm soát đến **nguồn ghi có thẩm quyền**: atomic conditional UPDATE cho phép cộng/trừ đơn giản, optimistic version/CAS cho quyết định tính từ snapshot, khóa trong transaction ngắn khi cần phối hợp, và isolation đủ mạnh cho invariant liên hàng. Sau đó bổ sung idempotency cho retry, xử lý kết quả commit chưa rõ, kiểm thử race có điều khiển và đối soát dữ liệu. Chỉ khi mọi yêu cầu đã được xác nhận đều tương ứng với đúng một thay đổi bền vững, thiết kế persistence mới thực sự an toàn trước concurrency.
