# Thiết kế cập nhật có điều kiện theo phiên bản bản ghi

Trong ứng dụng Java dùng **JDBC**, nhiều người dùng hoặc tiến trình có thể cùng đọc rồi sửa một hàng trong cơ sở dữ liệu quan hệ. Nếu mọi thao tác chỉ chạy `UPDATE ... WHERE id = ?`, thay đổi của người cập nhật sau có thể âm thầm ghi đè kết quả của người cập nhật trước. Đây là một dạng **lost update** (mất cập nhật).

Trong chương **CRUD và khóa sinh**, bài học này hướng dẫn cách thiết kế **cập nhật có điều kiện theo phiên bản bản ghi** (*optimistic locking* hoặc *optimistic concurrency control*): mỗi hàng có một cột `version`, ứng dụng đọc cả dữ liệu và phiên bản, rồi chỉ chấp nhận cập nhật khi phiên bản hiện tại vẫn bằng phiên bản đã đọc.

Kỹ thuật sử dụng các API JDBC quen thuộc: `DataSource` cấp kết nối, `ResultSet` đọc phiên bản, `PreparedStatement` thực hiện SQL tham số hóa, còn `executeUpdate()` cho biết có bao nhiêu hàng được cập nhật. Nó phù hợp với trường hợp xung đột không quá thường xuyên và không muốn giữ khóa cơ sở dữ liệu xuyên suốt thời gian người dùng xem hoặc chỉnh sửa dữ liệu.

## 1. Vấn đề: đọc cùng dữ liệu rồi ghi đè nhau

Giả sử hàng sản phẩm có giá `100.00`. Hai nhân viên cùng mở màn hình chỉnh sửa:

| Thời điểm | Người A | Người B | Giá trong DB |
| --- | --- | --- | --- |
| 1 | Đọc giá `100.00` | | `100.00` |
| 2 | | Đọc giá `100.00` | `100.00` |
| 3 | Lưu giá `110.00` | | `110.00` |
| 4 | | Lưu giá `120.00` | `120.00` |

Nếu cả hai dùng:

```sql
UPDATE products
SET price = ?
WHERE id = ?;
```

thì cả hai câu lệnh có thể thành công. Người A không được cảnh báo rằng thay đổi của mình đã bị ghi đè. Việc chỉ dùng `SELECT` trước `UPDATE` không loại bỏ lỗi này: một transaction khác có thể sửa dữ liệu **giữa lần đọc và lần ghi**.

Giải pháp là lưu thêm một phiên bản nguyên, ví dụ `version = 7`. Khi lưu, A và B cùng gửi phiên bản đã đọc `7`:

```sql
UPDATE products
SET price = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Lần cập nhật thành công trước sẽ đổi `version` từ `7` thành `8`. Lần còn lại không còn khớp `WHERE version = 7` nên cập nhật **0 hàng**. Ứng dụng biết dữ liệu đã thay đổi và có thể yêu cầu người dùng tải lại hoặc giải quyết xung đột.

```mermaid
sequenceDiagram
    participant A as Người A
    participant DB as Cơ sở dữ liệu
    participant B as Người B
    A->>DB: SELECT id, price, version
    DB-->>A: price=100, version=7
    B->>DB: SELECT id, price, version
    DB-->>B: price=100, version=7
    A->>DB: UPDATE ... WHERE id=42 AND version=7
    DB-->>A: 1 hàng; version thành 8
    B->>DB: UPDATE ... WHERE id=42 AND version=7
    DB-->>B: 0 hàng; có xung đột
```

Điểm mấu chốt là **kiểm tra phiên bản và ghi dữ liệu nằm trong cùng một câu `UPDATE`**. Cơ sở dữ liệu thực hiện phép kiểm tra có điều kiện và thay đổi như một thao tác cập nhật nguyên tử trên hàng phù hợp; ứng dụng không thể thay thế nó bằng hai bước kiểm tra/ghi không được bảo vệ.

## 2. Thiết kế bảng và hợp đồng cho cột version

Ví dụ sử dụng một bảng sản phẩm:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(18, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_products_price CHECK (price >= 0),
    CONSTRAINT chk_products_version CHECK (version >= 0)
);
```

Đây là SQL minh họa theo cú pháp SQL phổ biến; khả năng hỗ trợ `CHECK`, cú pháp khóa sinh và kiểu số có thể khác giữa các hệ quản trị (DBMS). Cột `id` định danh hàng bằng khóa chính, còn `version` là **mã phiên bản phục vụ kiểm soát đồng thời**. Hai cột có mục đích riêng: `id` có thể do DBMS sinh khi `INSERT`, nhưng `version` thường bắt đầu bằng `0` và tăng khi hàng được sửa.

Các quy tắc cần thống nhất cho **mọi nơi ghi dữ liệu**:

1. `version` luôn `NOT NULL` và có giá trị khởi tạo rõ ràng.
2. Mọi thao tác sửa hàng có thể xung đột phải dùng điều kiện `WHERE id = ? AND version = ?` và tăng phiên bản, kể cả API khác, job nền hoặc câu lệnh SQL viết thủ công.
3. Phiên bản chỉ tăng **cùng lúc** với cập nhật thành công, trong **chính câu `UPDATE`** hoặc thông qua cơ chế tương đương do DBMS kiểm soát. Không đọc phiên bản rồi gọi `UPDATE` riêng để tăng sau.
4. Không cho client tự quyết định phiên bản mới trong câu `SET`. Dùng `version = version + 1` ở phía DB để tránh gửi sai phiên bản kế tiếp.
5. Phiên bản phải được trả về cùng dữ liệu lúc đọc, rồi được gửi trở lại ở yêu cầu cập nhật. Đây là **phiên bản kỳ vọng** (*expected version*).

Kiểu `BIGINT` giúp giảm đáng kể nguy cơ tràn số, nhưng vẫn cần có chính sách nếu giá trị tiến gần giới hạn. Không tự ý đặt lại `version = 0` trên một hàng đang được sử dụng vì có thể khiến một phiên bản cũ tình cờ khớp trở lại (*ABA problem*).

**Lưu ý:** chỉ những thay đổi đã tham gia cơ chế tăng phiên bản mới được phát hiện. Nếu một job cập nhật `price` nhưng bỏ qua `version`, màn hình cũ của người dùng vẫn có thể cập nhật thành công và ghi đè dữ liệu của job.

## 3. Luồng đọc → sửa → cập nhật có điều kiện

Thiết kế giao tiếp cơ bản gồm ba bước:

1. **Đọc dữ liệu:** `SELECT id, price, version FROM products WHERE id = ?`, trả cả `version` cùng dữ liệu.
2. **Tạo yêu cầu sửa:** người dùng chỉnh giá, client giữ nguyên `expectedVersion` đã đọc. Thời gian người dùng nhập liệu **không nằm trong một giao dịch JDBC mở lâu**.
3. **Cập nhật có điều kiện:** `UPDATE ... WHERE id = ? AND version = ?` và kiểm tra kết quả `executeUpdate()`.

| Số hàng cập nhật | Ý nghĩa trong ví dụ có khóa chính `id` | Cách xử lý |
| --- | --- | --- |
| `1` | Phiên bản khớp, cập nhật đã được thực thi. | Xác nhận thành công sau khi giao dịch commit nếu có transaction. |
| `0` | Không có hàng khớp cả `id` và `expectedVersion`. | Trả kết quả không áp dụng; có thể là hàng bị xóa hoặc phiên bản đã đổi. |
| Lớn hơn `1` | Bất thường với điều kiện khóa chính `id`. | Xem lại SQL/lược đồ, không coi là thành công bình thường. |

Vì có thể không tìm thấy hàng, **`0` không tự chứng minh đã xảy ra xung đột phiên bản**. Một lần `SELECT` tiếp theo có thể giúp thông báo “đã bị xóa” hoặc “đã được cập nhật”, nhưng dữ liệu vẫn có thể tiếp tục thay đổi sau lần truy vấn đó. Kết luận chính xác và ổn định nhất của câu `UPDATE` là: **yêu cầu hiện tại không được áp dụng**.

Ví dụ giao tiếp API có thể trả:

```json
{
  "id": 42,
  "price": 100.00,
  "version": 7
}
```

Khi cập nhật, client gửi `id = 42`, `newPrice = 110.00` và `expectedVersion = 7`. Tùy hợp đồng API, ứng dụng có thể dùng JSON field `expectedVersion` hoặc một HTTP precondition như `If-Match` với ETag được tạo từ phiên bản. Không coi số phiên bản là ETag hợp lệ nếu chưa định nghĩa và xử lý đúng cú pháp/điều kiện HTTP tương ứng.

## 4. Ví dụ JDBC đầy đủ: đọc và cập nhật giá sản phẩm

Ví dụ Java bên dưới dùng `DataSource`, `PreparedStatement`, `ResultSet`, `BigDecimal`, `Optional` và `try-with-resources`. Để dễ nhìn phần kiểm soát phiên bản, mã giả định các thao tác đơn lẻ chạy trên kết nối bật `autoCommit` (thường là cấu hình mặc định của connection pool) và bảng đã tồn tại.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class ProductRepository {
    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<ProductSnapshot> findById(long productId)
            throws SQLException {
        String sql = "SELECT id, price, version "
                   + "FROM products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, productId);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new ProductSnapshot(
                        rows.getLong("id"),
                        rows.getBigDecimal("price"),
                        rows.getLong("version")));
            }
        }
    }

    // true: cập nhật 1 hàng; false: không có hàng nào khớp điều kiện.
    public boolean updatePrice(long productId, long expectedVersion,
                               BigDecimal requestedPrice) throws SQLException {
        Objects.requireNonNull(requestedPrice, "requestedPrice");
        if (productId <= 0 || expectedVersion < 0
                || expectedVersion == Long.MAX_VALUE
                || requestedPrice.signum() < 0) {
            throw new IllegalArgumentException("Đầu vào cập nhật không hợp lệ");
        }

        // Kiểm tra/chuẩn hóa dữ liệu trước khi mượn Connection.
        BigDecimal price = requestedPrice.setScale(
                2, RoundingMode.UNNECESSARY);

        String sql = "UPDATE products "
                   + "SET price = ?, version = version + 1 "
                   + "WHERE id = ? AND version = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, price);
            statement.setLong(2, productId);
            statement.setLong(3, expectedVersion);

            int updatedRows = statement.executeUpdate();
            if (updatedRows == 1) {
                return true;
            }
            if (updatedRows == 0) {
                return false;
            }
            throw new SQLException("Cập nhật bất thường: " + updatedRows);
        }
    }

    public static final class ProductSnapshot {
        public final long id;
        public final BigDecimal price;
        public final long version;

        public ProductSnapshot(long id, BigDecimal price, long version) {
            this.id = id;
            this.price = Objects.requireNonNull(price);
            this.version = version;
        }
    }
}
```

Ví dụ sử dụng:

```java
ProductRepository repository = new ProductRepository(dataSource);

ProductRepository.ProductSnapshot product =
        repository.findById(42L)
                  .orElseThrow(() -> new IllegalStateException(
                          "Không tìm thấy sản phẩm"));

// Người dùng có thể mất nhiều giây hoặc phút trước khi nhấn Lưu.
boolean applied = repository.updatePrice(
        product.id, product.version, new BigDecimal("110.00"));

if (!applied) {
    System.out.println("Dữ liệu đã đổi hoặc sản phẩm không còn tồn tại.");
    // Tải lại bản ghi và cho người dùng quyết định có ghi tiếp không.
}
```

**Vì sao ví dụ an toàn hơn `SELECT` rồi `UPDATE` thông thường?**

- `findById` trả cả `price` và `version` của một lần đọc; `updatePrice` dùng **phiên bản này**, không tự đọc một phiên bản mới ngay trước khi ghi.
- SQL tham số hóa tránh ghép giá và ID trực tiếp vào lệnh SQL.
- Điều kiện `WHERE id = ? AND version = ?` và phép `version = version + 1` thực hiện cùng một câu SQL. Hai yêu cầu cùng gửi một phiên bản sẽ không thể đều cập nhật thành công tuần tự mà không có lần nào phát hiện phiên bản đã đổi.
- `executeUpdate()` phân biệt có áp dụng được yêu cầu hay không. Kết quả `false` là **xung đột điều kiện hoặc không tìm thấy hàng**, khác với lỗi JDBC `SQLException`.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection`; với pool, việc đóng kết nối thường có nghĩa là trả nó về pool.

**Giới hạn:** mã minh họa giả định `id` là khóa chính, giá vừa với `DECIMAL(18, 2)`, không có cơ chế tăng phiên bản ngầm trong trigger và các writer khác tuân thủ cùng quy ước. Nếu `Connection` được cấu hình `autoCommit=false`, phải chủ động `commit` hoặc `rollback`; thành công của `executeUpdate()` lúc đó chưa đồng nghĩa giao dịch đã được xác nhận.

## 5. Quy tắc nghiệp vụ phải nằm trong điều kiện UPDATE khi cần

Kiểm tra `version` giải quyết vấn đề bản ghi thay đổi kể từ lần đọc. Nó **không thay thế** các điều kiện nghiệp vụ như “không bán quá tồn kho”, “chỉ hủy đơn hàng đang chờ xử lý” hoặc “không cho số dư âm”.

Ví dụ trừ tồn kho khi đồng thời phải bảo vệ phiên bản và số lượng:

```sql
UPDATE inventory
SET available = available - ?,
    version = version + 1
WHERE product_id = ?
  AND version = ?
  AND available >= ?;
```

Với `PreparedStatement`, lần lượt truyền `quantity`, `productId`, `expectedVersion` và lặp lại `quantity` ở tham số thứ tư. Điều kiện `available >= ?` đảm bảo việc trừ không làm âm hàng còn lại khi DBMS áp dụng cập nhật theo điều kiện. Một `UPDATE` trả `0` lúc này có thể do **không tồn tại hàng, lệch phiên bản hoặc không đủ hàng**; muốn phân biệt để thông báo người dùng, cần đọc trạng thái hiện tại và chấp nhận rằng trạng thái đó có thể lại thay đổi.

Ví dụ chuyển trạng thái đơn hàng:

```sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE id = ?
  AND version = ?
  AND status = 'PENDING';
```

Trong ví dụ này, phiên bản ngăn thao tác dựa trên ảnh chụp cũ, còn điều kiện `status = 'PENDING'` thể hiện quy tắc “chỉ hủy đơn đang chờ”. Cả hai cần được kiểm tra trong cùng SQL. Không chuyển điều kiện quan trọng thành đoạn `if` chỉ chạy trên dữ liệu đã đọc từ trước.

### Nhiều trường dữ liệu cùng sửa

Khi cập nhật một vài trường, hãy chỉ đặt những trường người dùng thật sự muốn sửa trong `SET`; gửi toàn bộ bản ghi cũ có thể vô tình ghi đè trường không định sửa nếu một đường ghi nào đó bỏ qua kiểm tra phiên bản. Tuy vậy, **cùng một cột `version` cho toàn bộ hàng** nghĩa là thay đổi bất kỳ trường nào làm phiên bản tăng, nên hai thao tác sửa hai trường độc lập cũng có thể xung đột dù cả hai dùng `WHERE version = ?`. Đây là lựa chọn nhất quán được đánh đổi với mức độ cạnh tranh; có thể cân nhắc tách các phần dữ liệu thường xuyên cập nhật độc lập thành các hàng/bảng khác nếu nghiệp vụ phù hợp.

## 6. Kết hợp cập nhật theo version với transaction

Một câu `UPDATE` duy nhất là đơn vị cập nhật nguyên tử ở cấp DBMS. Nhưng nếu thao tác nghiệp vụ yêu cầu **đồng thời sửa sản phẩm và ghi nhật ký kiểm toán**, cả hai SQL phải nằm trong **cùng một JDBC transaction**.

Ví dụ rút gọn (giả sử `dataSource`, `productId`, `expectedVersion` và `price` đã được kiểm tra từ trước):

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        int changed;
        try (PreparedStatement update = connection.prepareStatement(
                "UPDATE products "
              + "SET price = ?, version = version + 1 "
              + "WHERE id = ? AND version = ?")) {
            update.setBigDecimal(1, price);
            update.setLong(2, productId);
            update.setLong(3, expectedVersion);
            changed = update.executeUpdate();
        }

        if (changed == 0) {
            connection.rollback();
            return false; // Xung đột/không tìm thấy.
        }
        if (changed != 1) {
            throw new SQLException("Số hàng cập nhật bất thường: " + changed);
        }

        try (PreparedStatement audit = connection.prepareStatement(
                "INSERT INTO price_audit (product_id, new_price) "
              + "VALUES (?, ?)")) {
            audit.setLong(1, productId);
            audit.setBigDecimal(2, price);
            audit.executeUpdate();
        }

        connection.commit();
        return true;
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            failure.addSuppressed(rollbackError);
        }
        throw failure;
    }
}
```

Đây là **đoạn thân phương thức minh họa**, không phải cả lớp Java để biên dịch độc lập. Nó giả định bảng `price_audit` đã tồn tại và các tên biến được truyền đúng kiểu vào phương thức. Nhánh `changed == 0` trả kết quả không áp dụng; `changed > 1` được coi là lỗi bất thường, không đánh đồng với xung đột.

Nếu câu ghi audit thất bại, nhánh `catch` rollback cả cập nhật giá lẫn nhật ký. Nếu phiên bản đã thay đổi, không nên ghi nhật ký về một cập nhật chưa hề thành công. `commit` chỉ được gọi sau khi mọi SQL bắt buộc hoàn tất.

Không cần giữ transaction mở trong lúc người dùng nhập giá: hãy đọc dữ liệu, trả kết nối, cho người dùng sửa, rồi mở giao dịch mới chỉ cho phần ghi thực tế. Khi thao tác còn gồm gọi API bên ngoài, không thể đạt tính nguyên tử xuyên hệ thống chỉ bằng JDBC; cần thiết kế bổ sung (ví dụ transactional outbox và idempotency).

## 7. Ứng xử khi có xung đột và chính sách retry

**Xung đột phiên bản là kết quả nghiệp vụ bình thường**, không nhất thiết là lỗi hệ thống. Khi `executeUpdate() == 0`, ứng dụng có thể:

- **Thông báo và tải lại:** hiển thị phiên bản mới để người dùng kiểm tra trước khi lưu lại. Phù hợp cho màn hình chỉnh sửa văn bản, giá và thông tin quan trọng.
- **Hợp nhất có kiểm soát:** nếu người dùng sửa những trường độc lập, so sánh dữ liệu mới với bản cũ rồi cho phép quyết định hợp nhất. Phải cập nhật lại với **phiên bản mới**, không bỏ điều kiện `version`.
- **Thử lại có giới hạn:** chỉ khi quy tắc nghiệp vụ cho phép tính toán lại trên dữ liệu mới (ví dụ một phép cộng có điều kiện) và thao tác an toàn khi lặp. Cần giới hạn số lần thử, có chiến lược tránh tranh chấp liên tục.

**Không được** giải quyết xung đột bằng cách bỏ `AND version = ?` rồi `UPDATE` vô điều kiện. Làm vậy khôi phục đúng lỗi ghi đè mà phiên bản được thiết kế để ngăn.

Ví dụ khi API nhận một yêu cầu đặt giá mới cụ thể, sau xung đột nên hỏi người dùng có tiếp tục đặt giá đó trên bản dữ liệu mới hay không. Tự động tải phiên bản mới và cập nhật giá cũ ngay có thể bỏ qua thay đổi hợp lệ của người khác. Ngược lại, phép cộng `stock = stock + ?` theo yêu cầu sự kiện đã có định danh duy nhất có thể được thiết kế để retry, nhưng phải chống xử lý lặp cùng một sự kiện.

Lỗi `SQLException` như mất kết nối, deadlock hoặc serialization failure **khác** kết quả `0` hàng. Nếu lỗi xảy ra khi `commit`, có thể không biết giao dịch đã được xác nhận chưa; thử lại vô điều kiện có thể gây hiệu ứng kép. Với thao tác có tiền, hàng tồn hoặc side effect, dùng mã định danh yêu cầu và cơ chế idempotency trước khi retry.

Ở HTTP, một API có thể chọn `409 Conflict` cho xung đột phiên bản của tài nguyên hoặc `412 Precondition Failed` khi dùng precondition như `If-Match`. Cách mã hóa cụ thể phải nhất quán với hợp đồng API; `404 Not Found` chỉ phù hợp khi đã xác định tài nguyên không tồn tại theo chính sách của hệ thống.

## 8. So sánh với các cách khác

| Cách kiểm soát | Đặc điểm | Khi nên cân nhắc |
| --- | --- | --- |
| **Optimistic locking bằng `version`** | Không giữ khóa DB trong khoảng người dùng chỉnh sửa; xung đột được phát hiện lúc ghi. | Thao tác đọc nhiều, ghi ít, xung đột không quá dày. |
| **Pessimistic locking** như `SELECT ... FOR UPDATE` | Khóa được giữ trong transaction; giao dịch tranh chấp có thể phải chờ. | Cần khóa ngay trong một transaction ngắn và kiểm soát tài nguyên tranh chấp cao. |
| **Cập nhật nguyên tử theo điều kiện nghiệp vụ** | `UPDATE SET count = count + 1 WHERE ...`; DB xử lý thay đổi có điều kiện mà không nhất thiết đọc trước. | Phép tăng/giảm hoặc điều kiện đơn giản, không cần toàn bộ snapshot trước đó. |
| **So sánh cột `updated_at`** | Có thể phát hiện thay đổi nếu thời gian đủ chính xác và mọi writer cập nhật đúng. | Chỉ khi đã kiểm soát đầy đủ độ chính xác, quy tắc thời gian và tất cả đường ghi. |

`updated_at` không phải lúc nào cũng là thay thế tốt cho `version`. Hai cập nhật có thể mang cùng timestamp do độ chính xác cột, hoặc lệch vì thời gian của máy ứng dụng và DBMS khác nhau. Bộ đếm phiên bản nguyên được DB tăng cùng lệnh `UPDATE` tránh các vấn đề so sánh thời gian này.

Không có một kỹ thuật duy nhất phù hợp mọi nghiệp vụ. Chẳng hạn, việc cấp một số lượng vé rất khan hiếm có thể dùng câu `UPDATE ... WHERE available > 0` trực tiếp. Nếu quyết định cập nhật phụ thuộc vào **tập trường đã đọc trước đó**, điều kiện `version` giúp phát hiện dữ liệu cũ. Nếu toàn bộ nhiều hàng cần nguyên tử, vẫn phải dùng transaction.

## 9. Liên hệ với khóa chính sinh tự động

Trong chương CRUD và khóa sinh, cần phân biệt:

- **Khóa chính `id`:** xác định hàng; có thể được DBMS tạo khi `INSERT` và lấy bằng `Statement.RETURN_GENERATED_KEYS` nếu driver hỗ trợ.
- **Khóa phiên bản `version`:** không phải ID mới và không phải giá trị từ `getGeneratedKeys()`; nó thay đổi qua mỗi lần cập nhật được kiểm soát.

Ví dụ minh họa khi DBMS tự sinh khóa `id`:

```java
String insert = "INSERT INTO products (name, price, version) "
              + "VALUES (?, ?, 0)";
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             insert, java.sql.Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "Bàn học");
    ps.setBigDecimal(2, new java.math.BigDecimal("450.00"));
    ps.executeUpdate();

    try (ResultSet generated = ps.getGeneratedKeys()) {
        if (generated.next()) {
            long newId = generated.getLong(1);
            // Hàng mới có version ban đầu 0 theo câu INSERT.
            System.out.println("ID mới: " + newId);
        }
    }
}
```

Đoạn mã này **giả định** cột `id` đã được cấu hình tự sinh theo cách riêng của DBMS. Lược đồ SQL ở phần 2 chỉ khai báo `id` là `PRIMARY KEY`, chưa khai báo cơ chế sinh khóa; nếu dùng đúng lược đồ ấy mà không bổ sung cấu hình, câu `INSERT` bỏ `id` có thể thất bại. Hỗ trợ `RETURN_GENERATED_KEYS` và cách trả khóa còn phụ thuộc driver.

Sau khi tạo sản phẩm, các yêu cầu sửa dùng `id` để tìm hàng và `version` để bảo vệ khỏi ghi đè đồng thời.

## 10. Kiểm thử xung đột và những lỗi triển khai thường gặp

Nên thử ít nhất các tình huống sau trên DBMS và driver thực tế:

| Tình huống | Kết quả cần thấy |
| --- | --- |
| Một client đọc `version=3`, cập nhật với `expectedVersion=3`. | Một hàng thay đổi; phiên bản trở thành `4`. |
| Hai client cùng đọc `version=3`; client A cập nhật trước. | A cập nhật `1` hàng; B dùng phiên bản `3` cập nhật `0` hàng. |
| Cập nhật với ID không tồn tại. | `0` hàng; không kết luận nhầm đó chắc chắn là xung đột phiên bản. |
| Dữ liệu mới vi phạm `CHECK (price >= 0)` hoặc kiểu cột. | DBMS có thể từ chối và trả lỗi SQL; không nhầm với `0` hàng do phiên bản. |
| Job nền sửa giá nhưng không tăng version. | Bài kiểm thử phải phát hiện lỗ hổng quy ước; cập nhật cũ có thể ghi đè job. |
| Nhiều SQL trong cùng transaction, lệnh thứ hai lỗi. | Rollback tất cả; không còn cập nhật sản phẩm dở dang. |
| Giao dịch khác thay đổi phiên bản ngay trước khi client lưu. | Kiểm tra và ghi trong cùng câu `UPDATE` bảo vệ khỏi lost update. |

Một số bẫy điển hình:

1. **Kiểm tra phiên bản bằng Java trước rồi cập nhật không điều kiện:** vẫn có khoảng hở giữa `SELECT` và `UPDATE`.
2. **Đặt `version = ?` với phiên bản client tự cộng:** dễ quên tăng hoặc cho phép client gửi phiên bản sai; nên để DB cộng từ giá trị hiện tại.
3. **Chỉ tăng version ở một API:** các đường ghi khác làm mất tính nhất quán của hợp đồng.
4. **Coi `0` hàng là SQLException:** xung đột điều kiện là kết quả hợp lệ; để riêng với lỗi DB.
5. **Retry mãi hoặc retry bằng một snapshot cũ:** gây tranh chấp liên tục hoặc ghi đè ý định người khác.
6. **Giữ transaction khi đợi người dùng chỉnh sửa:** làm chiếm kết nối và giữ khóa lâu; optimistic locking được thiết kế để tránh điều đó.
7. **Tin rằng version giải quyết tất cả quy tắc nghiệp vụ:** vẫn cần ràng buộc DB, điều kiện trong `WHERE` và transaction nhiều bước.

## 11. Bài tập thực hành

**Tình huống:** bảng `orders(id, status, total_amount, version)` có đơn hàng `id=81`, `status='PENDING'`, `total_amount=250.00` và `version=5`. Hai nhân viên cùng mở đơn.

1. Viết SQL đổi `status` thành `'APPROVED'`, chỉ khi đơn vẫn là `'PENDING'` và phiên bản vẫn `5`. SQL phải tăng `version` khi cập nhật thành công.
2. Nếu nhân viên A xác nhận trước, `executeUpdate()` của nhân viên B (vẫn gửi phiên bản `5`) trả gì?
3. Nếu câu `UPDATE` trả `0`, bạn sẽ phân biệt “đơn đã bị xóa”, “phiên bản đổi” và “trạng thái không còn PENDING” thế nào? Tại sao lần truy vấn để phân biệt chỉ phản ánh trạng thái tại thời điểm đọc?
4. Nếu việc duyệt đơn còn phải ghi một hàng `order_audit`, cần bổ sung những thao tác JDBC nào để hai bước nguyên tử?

**Đáp án tham khảo:**

```sql
UPDATE orders
SET status = 'APPROVED',
    version = version + 1
WHERE id = ?
  AND version = ?
  AND status = 'PENDING';
```

Với tham số `id=81`, `version=5`, nhân viên A thành công làm phiên bản lên `6`. Yêu cầu của B với phiên bản `5` cập nhật `0` hàng. Đọc lại `id, version, status` có thể hỗ trợ phân loại lý do, nhưng không biến lần đọc ấy thành ảnh chụp bất biến. Nếu ghi audit phải thành công cùng cập nhật đơn, mở transaction bằng `setAutoCommit(false)`, kiểm tra số hàng, thực hiện `INSERT audit`, rồi `commit`; lỗi thì `rollback`, đóng tài nguyên bằng `try-with-resources`.

**Ghi nhớ:** Thiết kế cập nhật theo phiên bản luôn gồm **đọc version → gửi expectedVersion → `UPDATE ... WHERE id = ? AND version = ?` → tăng version cùng câu UPDATE → kiểm tra số hàng cập nhật**. Cơ chế này giúp ứng dụng JDBC phát hiện yêu cầu dựa trên dữ liệu cũ, giảm nguy cơ lost update và cho phép phản hồi xung đột rõ ràng mà không phải giữ transaction mở trong lúc người dùng chỉnh sửa.
