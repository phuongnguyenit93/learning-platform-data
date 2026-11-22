# Tái hiện cập nhật bị mất và áp dụng kiểm soát phiên bản trong JDBC

Trong chương **Thực hành tổng hợp**, chúng ta kết hợp `Connection`, `DataSource`, `PreparedStatement`, `ResultSet`, transaction, mức cô lập, cập nhật có điều kiện và kiểm thử tích hợp để giải quyết một lỗi đồng thời phổ biến: **lost update – cập nhật bị mất**.

Giả sử một kho hàng đang có **10 sản phẩm**. Nhân viên A đặt giữ 2 sản phẩm và nhân viên B đặt giữ 3 sản phẩm gần như cùng lúc. Kết quả đúng là còn **5 sản phẩm**. Nếu cả hai cùng đọc số lượng 10, A ghi 8 và B ghi 7 theo giá trị cũ, cơ sở dữ liệu cuối cùng có thể lưu **7**. Kho đã quên thao tác giữ hàng của A, dù cả hai lệnh `UPDATE` đều có thể trả về số hàng ảnh hưởng bằng 1 và commit thành công.

Đây không nhất thiết là SQL injection hay lỗi cú pháp. Nó thường bắt nguồn từ quy trình **đọc → tính toán trong Java → ghi đè giá trị** mà không xác nhận dữ liệu có bị thay đổi giữa hai bước.

Bài thực hành hướng dẫn:

- **Tái hiện có kiểm soát** lost update bằng hai `Connection` trong một ứng dụng JDBC.
- Phân biệt giao dịch thành công ở tầng kỹ thuật với **hậu điều kiện nghiệp vụ** đúng.
- Bổ sung **optimistic locking** bằng cột `version` và `WHERE version = ?`.
- Xử lý kết quả `executeUpdate() == 0` như xung đột, không tự bỏ điều kiện kiểm tra.
- Đọc lại trạng thái mới, tính lại và retry trong **transaction mới** với giới hạn rõ ràng.
- So sánh giải pháp với `UPDATE` số học nguyên tử, `SELECT ... FOR UPDATE` và transaction isolation.
- Kiểm thử trên DBMS/driver thực, quản lý rollback, connection pool và trường hợp commit không rõ kết quả.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau bài, bạn nên tự chạy được hai kịch bản trên cơ sở dữ liệu thử nghiệm:

| Kịch bản | Hai tác vụ cùng đọc | Tác vụ A | Tác vụ B | Kết quả mong muốn |
| --- | --- | --- | --- | --- |
| **Không kiểm soát phiên bản** | `quantity=10` | Giảm 2, ghi `8` | Giảm 3, ghi `7` dựa trên dữ liệu cũ | Quan sát lỗi: cuối cùng `7` thay vì `5` |
| **Có kiểm soát phiên bản** | `quantity=10, version=0` | Giảm 2, ghi `8, version=1` | Cố ghi `7` với `version=0`, bị từ chối | Không có ghi đè âm thầm; B đọc lại `8` rồi ghi `5, version=2` |

**Điều kiện thành công của bài thực hành:**

1. Có thể chỉ ra chính xác câu `UPDATE` nào tạo lost update và vì sao.
2. Chứng minh kịch bản lỗi không phụ thuộc vào việc ID có khó đoán hay không.
3. Ghi nhận số hàng cập nhật `1` ở đường thành công và `0` ở đường xung đột.
4. Không commit những thay đổi nghiệp vụ phụ khi bước cập nhật chính thất bại.
5. Khi retry, **đọc lại và tính lại** từ trạng thái mới thay vì lặp lại giá trị cũ.
6. Kiểm chứng tổng số hàng, số lượng và `version` cuối bằng một truy vấn từ connection mới.
7. Thực hiện trên database test, **không tạo race cố ý trên dữ liệu sản xuất**.

## 2. Chuẩn bị bảng và dữ liệu mẫu

Ví dụ dùng SQL tương đối phổ biến trên PostgreSQL, H2 và một số DBMS quan hệ khác. Các chi tiết về isolation và khóa cần kiểm chứng trên hệ quản trị đích.

~~~sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL
        CHECK (available_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

INSERT INTO inventory_items (
    id, sku, available_quantity, version
)
VALUES (1001, 'SKU-KEYBOARD', 10, 0);
~~~

**Ý nghĩa các cột:**

| Cột | Vai trò |
| --- | --- |
| `id` | Khóa chính xác định hàng đang được cập nhật |
| `sku` | Mã sản phẩm duy nhất phục vụ nghiệp vụ |
| `available_quantity` | Số lượng còn có thể đặt giữ |
| `version` | Phiên bản logic của hàng, tăng khi dữ liệu được thay đổi theo quy tắc optimistic locking |

Ràng buộc `CHECK (available_quantity >= 0)` ngăn việc lưu số lượng âm, nhưng **không phát hiện mất cập nhật**: cả 8 và 7 đều không âm. Tương tự, `PRIMARY KEY` và `UNIQUE` không tự ngăn hai câu `UPDATE` cùng ghi đè một hàng có sẵn.

Bài dùng **số nguyên `INTEGER` cho số lượng** vì hàng hóa đếm theo đơn vị. Nếu miền nghiệp vụ dùng số thập phân, khối lượng hoặc tiền, hãy chọn `DECIMAL` và `BigDecimal` cùng chính sách scale/rounding phù hợp.

### Dữ liệu chuẩn để chạy lại bài

Trên database test có thể đặt lại hàng:

~~~sql
UPDATE inventory_items
SET available_quantity = 10,
    version = 0
WHERE id = 1001;
~~~

Không chạy câu reset đồng thời với các test khác. Với CI, nên tạo database/schema hoặc khóa fixture riêng cho từng test để tránh trường hợp hai bài kiểm thử cùng ghi một ID.

## 3. Phân tích lost update theo dòng thời gian

Hai tác vụ A và B đều muốn **giảm số lượng** nhưng thực hiện tính toán dựa vào giá trị đọc trước đó.

~~~mermaid
sequenceDiagram
    participant A as Connection A
    participant DB as CSDL
    participant B as Connection B
    A->>DB: SELECT quantity → 10
    B->>DB: SELECT quantity → 10
    Note over A: Tính 10 - 2 = 8
    Note over B: Tính 10 - 3 = 7
    A->>DB: UPDATE SET quantity = 8
    A->>DB: COMMIT
    B->>DB: UPDATE SET quantity = 7
    B->>DB: COMMIT
    Note over DB: Còn 7, nhưng đúng phải là 5
~~~

Truy vấn gây vấn đề:

~~~sql
UPDATE inventory_items
SET available_quantity = ?
WHERE id = ?;
~~~

Vì điều kiện `WHERE` chỉ dựa trên `id`, câu `UPDATE` của B **không kiểm tra** rằng hàng đã bị A thay đổi sau lần B đọc.

Điều đáng chú ý: B có thể cập nhật **sau khi A đã commit**, nên hai lệnh ghi không nhất thiết đụng nhau ở mức khóa đồng thời. Lost update ở đây đến từ **giá trị cũ trong ứng dụng Java**.

### Vì sao `autoCommit=false` vẫn chưa đủ?

Một transaction có thể chứa nhiều câu SQL và commit/rollback như một đơn vị, nhưng chỉ bật:

~~~java
conn.setAutoCommit(false);
~~~

**không có nghĩa transaction tự biết cách hòa giải mọi phép tính dựa trên dữ liệu cũ**. Cơ chế isolation/locking của DBMS, loại câu SQL và cách ứng dụng tổ chức đọc–ghi vẫn quyết định liệu cập nhật có bị mất hay không.

Ở một số DBMS hoặc isolation cao hơn, một trong hai transaction có thể bị chặn hoặc trả lỗi thay vì tạo lost update. Đó là lý do phải **ghi rõ DBMS và mức isolation trong test**; không được tuyên bố mọi hệ quản trị đều tái hiện cùng lịch theo cùng cách.

## 4. Tái hiện lỗi với hai `Connection` theo thứ tự xác định

Không cần tạo hai thread để minh họa lost update. Ta có thể mở **hai connection độc lập**, cho cả hai đọc số lượng ban đầu, sau đó điều khiển thứ tự ghi bằng mã Java. Cách này dễ tái hiện hơn một test phụ thuộc `Thread.sleep()`.

Ví dụ chạy với PostgreSQL ở mức `READ_COMMITTED`, nơi hai câu `SELECT` riêng và hai câu `UPDATE` tuần tự có thể minh họa rõ hành vi dưới đây.

### 4.1. Lớp Java đọc và ghi không an toàn

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class LostUpdateDemo {
    private LostUpdateDemo() {}

    static int readQuantity(Connection conn, long id)
            throws SQLException {
        String sql = """
            SELECT available_quantity
            FROM inventory_items
            WHERE id = ?
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không tìm thấy item: " + id);
                }
                return rs.getInt("available_quantity");
            }
        }
    }

    static int writeQuantityWithoutVersion(
            Connection conn, long id, int newQuantity
    ) throws SQLException {
        String sql = """
            UPDATE inventory_items
            SET available_quantity = ?
            WHERE id = ?
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, newQuantity);
            ps.setLong(2, id);
            return ps.executeUpdate();
        }
    }

    public static void reproduce(DataSource ds)
            throws SQLException {

        final long id = 1001L;

        // Pool cần cấp được ít nhất hai connection đồng thời.
        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);

            a.setAutoCommit(false);
            b.setAutoCommit(false);

            boolean aEnded = false;
            boolean bEnded = false;

            try {
                // Cả hai cùng đọc số lượng 10 trước khi có UPDATE.
                int seenByA = readQuantity(a, id);
                int seenByB = readQuantity(b, id);

                int desiredByA = seenByA - 2;
                int desiredByB = seenByB - 3;

                // Chỉ cho A ghi trước để không bị lock wait.
                int changedA = writeQuantityWithoutVersion(
                    a, id, desiredByA);
                if (changedA != 1) {
                    throw new SQLException("A sửa không đúng một hàng");
                }

                a.commit();
                aEnded = true;

                // B ghi bằng số lượng tính từ giá trị 10 đã cũ.
                int changedB = writeQuantityWithoutVersion(
                    b, id, desiredByB);
                if (changedB != 1) {
                    throw new SQLException("B sửa không đúng một hàng");
                }

                b.commit();
                bEnded = true;

                System.out.println(
                    "A đọc " + seenByA + ", ghi " + desiredByA);
                System.out.println(
                    "B đọc " + seenByB + ", ghi " + desiredByB);
            } finally {
                if (!aEnded) {
                    try { a.rollback(); }
                    catch (SQLException cleanup) {
                        System.err.println(
                            "Không rollback được A: " + cleanup);
                    }
                }
                if (!bEnded) {
                    try { b.rollback(); }
                    catch (SQLException cleanup) {
                        System.err.println(
                            "Không rollback được B: " + cleanup);
                    }
                }
            }
        }

        try (Connection verify = ds.getConnection()) {
            int actual = readQuantity(verify, id);
            System.out.println("Kết quả DB: " + actual);
            System.out.println("Đáp án nghiệp vụ: " + (10 - 2 - 3));
        }
    }
}
~~~

**Dữ liệu đầu vào:** trước khi gọi `LostUpdateDemo.reproduce(ds)`, reset `id=1001` về `available_quantity=10, version=0`. Sau khi chạy, trên DBMS/mức isolation phù hợp bạn sẽ quan sát:

~~~text
A đọc 10, ghi 8
B đọc 10, ghi 7
Kết quả DB: 7
Đáp án nghiệp vụ: 5
~~~

Đây là **đoạn mã diễn giải**, không phải thư viện transaction production. Nó cố tình dùng hai thao tác ghi sai logic để quan sát lỗi. Trong sản phẩm thật, cần xử lý đầy đủ lỗi cleanup, khôi phục trạng thái connection trước khi trả về pool và không ghi thông tin nhạy cảm vào `System.err`.

### 4.2. Vì sao không dùng hai lần `getConnection()` rồi tưởng là một transaction?

`DataSource.getConnection()` có thể cấp hai connection khác nhau; mỗi connection có `autoCommit`, isolation, transaction và session state riêng. Không có transaction JDBC cục bộ nào tự bao phủ hai connection độc lập.

Sơ đồ của bài không nói A và B thuộc **cùng transaction**. Chúng là hai transaction cạnh tranh cập nhật **cùng bản ghi**.

Nếu dùng HikariCP hoặc connection pool khác, hãy bảo đảm pool có thể cung cấp ít nhất hai kết nối cho phép thử. Nếu pool chỉ có `maximumPoolSize=1`, lời gọi lấy connection B có thể phải chờ và test treo/hết timeout trước khi bắt đầu.

### 4.3. Tại sao `READ_COMMITTED` chưa chắc cứu được?

Ở PostgreSQL, `READ COMMITTED` cho phép mỗi câu SQL thấy snapshot phù hợp với thời điểm bắt đầu câu đó. Nhưng ứng dụng B đã **lưu giá trị 10 trong biến Java**, rồi chạy:

~~~sql
UPDATE inventory_items
SET available_quantity = 7
WHERE id = 1001;
~~~

Lệnh này không yêu cầu DBMS kiểm tra “giá trị ban đầu phải vẫn là 10”. DBMS có thể thi hành câu `UPDATE` hợp lệ và commit giá trị 7.

Nếu B viết `SET available_quantity = available_quantity - 3` thay vì giá trị hằng 7, ý nghĩa và cơ chế khóa sẽ khác (xem phần 10). Đây là **khác biệt giữa cập nhật dựa trên giá trị cũ của client và cập nhật số học trên giá trị hiện thời ở DBMS**.

## 5. Kiểm soát phiên bản: cơ chế optimistic locking

**Optimistic locking** không giữ khóa từ lúc đọc đến lúc người dùng quyết định ghi. Thay vào đó, mỗi bản ghi có một giá trị **`version`** thể hiện trạng thái đã quan sát.

Quy trình:

1. Đọc `available_quantity` và `version` trong cùng hàng.
2. Tính kết quả mới theo nghiệp vụ.
3. Chạy `UPDATE` có điều kiện: `WHERE id = ? AND version = ?`.
4. Khi ghi thành công, tăng phiên bản bằng `version = version + 1`.
5. Kiểm tra `executeUpdate()`:
   - `1`: hàng vẫn ở phiên bản đã đọc và được cập nhật.
   - `0`: hàng đã bị xóa, phiên bản thay đổi hoặc điều kiện bảo vệ khác không còn đúng.
6. Nếu `0`, **không commit nghiệp vụ như thể thành công**. Rollback, đọc lại hoặc báo conflict.

SQL trọng tâm:

~~~sql
UPDATE inventory_items
SET available_quantity = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Hai điều kiện độc lập:

- `id = ?`: chọn đúng hàng.
- `version = ?`: chỉ ghi nếu trạng thái nguồn **chưa đổi từ lần đọc**.

`version = version + 1` được DBMS tính trong câu UPDATE; ứng dụng không nên ghi một phiên bản mới được dự đoán bằng cách **đặt hằng số từ dữ liệu cũ** khi không có điều kiện kiểm tra.

### Hành vi sau khi thêm version

~~~mermaid
sequenceDiagram
    participant A as Connection A
    participant DB as CSDL
    participant B as Connection B
    A->>DB: SELECT quantity,version → 10,0
    B->>DB: SELECT quantity,version → 10,0
    A->>DB: UPDATE quantity=8, version=version+1 WHERE version=0
    DB-->>A: updateCount=1
    A->>DB: COMMIT
    B->>DB: UPDATE quantity=7, version=version+1 WHERE version=0
    DB-->>B: updateCount=0
    B->>DB: ROLLBACK
    B->>DB: SELECT quantity,version → 8,1
    B->>DB: UPDATE quantity=5, version=version+1 WHERE version=1
    DB-->>B: updateCount=1
    B->>DB: COMMIT
    Note over DB: Đúng: quantity=5, version=2
~~~

**Điểm khác biệt quan trọng:** Không phải hệ thống “tự biết cả hai người muốn trừ bao nhiêu”. Nó chỉ **ngăn một writer dùng dữ liệu cũ ghi đè âm thầm**. Chính ứng dụng phải làm mới dữ liệu và tính lại theo quy tắc nghiệp vụ.

## 6. Tạo repository JDBC có thao tác kiểm tra phiên bản

Dùng `record` để biểu diễn dữ liệu đã đọc cùng phiên bản:

~~~java
record InventorySnapshot(
    long id, int availableQuantity, long version
) {}
~~~

Repository đọc hai trường cần thiết và cập nhật có điều kiện:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public final class InventoryRepository {
    public Optional<InventorySnapshot> find(
            Connection conn, long id
    ) throws SQLException {
        String sql = """
            SELECT id, available_quantity, version
            FROM inventory_items
            WHERE id = ?
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new InventorySnapshot(
                    rs.getLong("id"),
                    rs.getInt("available_quantity"),
                    rs.getLong("version")
                ));
            }
        }
    }

    /**
     * Trả 1 nếu thành công, 0 nếu không còn đúng phiên bản.
     */
    public int updateIfCurrent(
            Connection conn,
            InventorySnapshot expected,
            int newQuantity
    ) throws SQLException {
        if (newQuantity < 0) {
            throw new IllegalArgumentException(
                "Số lượng mới không thể âm");
        }

        String sql = """
            UPDATE inventory_items
            SET available_quantity = ?,
                version = version + 1
            WHERE id = ?
              AND version = ?
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, newQuantity);
            ps.setLong(2, expected.id());
            ps.setLong(3, expected.version());

            return ps.executeUpdate();
        }
    }
}
~~~

Trong bài này, `InventorySnapshot` được khai báo cùng package để `InventoryRepository` sử dụng được.

**Các cam kết của hàm:**

- Nó không tự gọi `commit()` hoặc `rollback()`. Chủ sở hữu transaction quyết định.
- Nó không tự thực hiện retry sau xung đột; caller phải quyết định theo nghiệp vụ.
- Nó không dùng giá trị `version` từ client như nguồn tin cậy tuyệt đối nếu client có thể giả mạo yêu cầu. Khi nhận dữ liệu từ bên ngoài, phải kiểm tra quyền truy cập, thuộc tenant nào và quy tắc cập nhật.
- Nó phụ thuộc vào **mọi đường ghi** đều phải tăng `version` khi thay đổi dữ liệu có ý nghĩa. Nếu một chức năng khác cập nhật `available_quantity` nhưng không tăng version, cơ chế có thể bỏ sót xung đột.
- Với hàng có nhiều trường, quyết định trường nào làm thay đổi version phải được thống nhất. Version của cả hàng sẽ tạo xung đột cả khi hai writer sửa hai trường độc lập.

### Vì sao phải kiểm tra `updateCount`?

Một câu `UPDATE` trả `0` không nhất thiết ném `SQLException`. JDBC chỉ nói rằng không có hàng nào được cập nhật theo điều kiện truy vấn.

Nếu mã viết:

~~~java
ps.executeUpdate();
conn.commit();
return "SUCCESS";
~~~

thì khi version không khớp, ứng dụng có thể **báo thành công giả** dù không ghi được gì. Vì thế kiểm tra `executeUpdate() == 1` là một phần hợp đồng nghiệp vụ.

Vì `id` là khóa chính, truy vấn trên chỉ có thể ảnh hưởng tối đa một hàng nếu lược đồ đúng. Nếu `executeUpdate() > 1` trong mô hình có khóa duy nhất thì cần xem đó là dấu hiệu bất thường về schema/query, không coi là thành công.

## 7. Tái hiện cùng lịch với optimistic locking

Có thể sử dụng hai connection như phần trước, nhưng thay câu ghi không an toàn bằng `InventoryRepository.updateIfCurrent(...)`:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public final class VersionCheckDemo {
    private VersionCheckDemo() {}

    public static void run(DataSource ds)
            throws SQLException {

        InventoryRepository repo = new InventoryRepository();
        long id = 1001L;

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            try {
                InventorySnapshot initialA = repo.find(a, id)
                    .orElseThrow(() ->
                        new SQLException("A không thấy hàng"));

                InventorySnapshot initialB = repo.find(b, id)
                    .orElseThrow(() ->
                        new SQLException("B không thấy hàng"));

                // Hai bản sao đều là quantity=10, version=0.
                int aCount = repo.updateIfCurrent(
                    a, initialA,
                    initialA.availableQuantity() - 2
                );

                if (aCount != 1) {
                    throw new SQLException(
                        "A gặp xung đột không mong muốn");
                }
                a.commit();

                // B vẫn dùng bản sao cũ quantity=10, version=0.
                int bCount = repo.updateIfCurrent(
                    b, initialB,
                    initialB.availableQuantity() - 3
                );

                if (bCount != 0) {
                    throw new SQLException(
                        "Kịch bản kỳ vọng B xung đột");
                }

                // Không giữ transaction thất bại để cố sửa tiếp.
                b.rollback();

                // Sau rollback, READ_COMMITTED cho phép
                // câu SELECT mới thấy bản A đã commit.
                InventorySnapshot fresh = repo.find(b, id)
                    .orElseThrow(() ->
                        new SQLException("Hàng đã bị xóa"));

                int retryCount = repo.updateIfCurrent(
                    b, fresh,
                    fresh.availableQuantity() - 3
                );

                if (retryCount != 1) {
                    throw new SQLException(
                        "B lại gặp xung đột");
                }

                b.commit();

            } catch (SQLException | RuntimeException error) {
                try { a.rollback(); }
                catch (SQLException cleanup) {
                    error.addSuppressed(cleanup);
                }
                try { b.rollback(); }
                catch (SQLException cleanup) {
                    error.addSuppressed(cleanup);
                }
                throw error;
            }
        }

        try (Connection verify = ds.getConnection()) {
            InventorySnapshot finalState =
                repo.find(verify, id).orElseThrow();

            System.out.printf(
                "quantity=%d, version=%d%n",
                finalState.availableQuantity(),
                finalState.version()
            );
        }
    }
}
~~~

Chạy sau khi reset dữ liệu về 10 và version 0. Khi không có tác vụ thứ ba cùng sửa hàng, kết quả kỳ vọng:

~~~text
quantity=5, version=2
~~~

**Giải thích tại sao B không bị mất cập nhật:**

- B đọc `version=0` trước khi A ghi.
- A tăng version lên `1` rồi commit.
- SQL của B yêu cầu `WHERE version = 0` nên không còn hàng phù hợp, trả `0`.
- B rollback, đọc lại số lượng `8` và version `1`, tính `8 - 3 = 5`, ghi với `WHERE version = 1`.
- Hai tác vụ cùng được áp dụng **mỗi tác vụ đúng một lần** trong kịch bản mô phỏng.

**Giới hạn:** Mã demo có thể bị ảnh hưởng nếu có writer thứ ba cùng chạm `id=1001`, nếu driver không hỗ trợ mức isolation yêu cầu hoặc DBMS có trạng thái transaction khác. Các đường rollback/cleanup sau `commit()` lỗi phải được thiết kế kỹ hơn trong production, vì **kết quả commit có thể không xác định khi mất kết nối**. Bài sẽ đề cập ở phần 12.

## 8. Xử lý xung đột đúng trong service thật

Trong hệ thống thực, việc “đọc lại và retry” không phải lúc nào cũng được phép:

- Nếu người dùng muốn **giảm tồn kho 3 đơn vị** và chưa làm side effect nào khác, có thể tính lại trên trạng thái mới.
- Nếu người dùng nhập **giá bán chính xác 120.000** dựa trên bảng giá cũ, tự động ghi đè phiên bản mới có thể sai; cần yêu cầu người dùng xem lại.
- Nếu đã gửi email, gọi cổng thanh toán hoặc gửi message ngoài DB, retry lại toàn thao tác có thể tạo side effect trùng.

Vì thế, một service tốt cần xác định:

1. Các lỗi nào là **optimistic conflict**, khác `SQLException` về network/constraint/deadlock.
2. Có được retry tự động không?
3. Retry tối đa bao nhiêu lần?
4. Dữ liệu và luật nghiệp vụ cần đọc lại thế nào?
5. Có bảo đảm idempotency khi retry sau kết quả commit không xác định không?

### Định nghĩa kết quả nghiệp vụ

~~~java
enum ReservationStatus {
    RESERVED,
    NOT_FOUND,
    INSUFFICIENT_STOCK,
    CONFLICT
}
~~~

Không nên trả `true/false` chung cho mọi tình huống. `NOT_FOUND`, `INSUFFICIENT_STOCK` và `CONFLICT` có ý nghĩa khác nhau; API có thể ánh xạ chúng thành mã phản hồi và thông báo phù hợp mà không tiết lộ dữ liệu ngoài quyền.

## 9. Ví dụ service hoàn chỉnh: retry có giới hạn, transaction mới cho từng lần thử

Ví dụ dưới đây tổ chức việc đặt giữ tồn kho qua `DataSource`. Mỗi attempt dùng **connection/transaction riêng**. Bất kỳ lần đọc lại nào đều dựa trên dữ liệu mới, không dùng snapshot cũ.

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Objects;

public final class InventoryReservationService {
    private static final int MAX_ATTEMPTS = 3;

    private final DataSource dataSource;
    private final InventoryRepository repository;

    public InventoryReservationService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
        this.repository = new InventoryRepository();
    }

    public ReservationStatus reserve(
            long itemId, int requestedUnits
    ) throws SQLException {

        if (itemId <= 0 || requestedUnits <= 0) {
            throw new IllegalArgumentException(
                "itemId và requestedUnits phải dương");
        }

        for (int attempt = 1;
             attempt <= MAX_ATTEMPTS;
             attempt++) {

            try (Connection conn = dataSource.getConnection()) {
                // Trước khi transaction bắt đầu chạy SQL.
                conn.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
                conn.setAutoCommit(false);

                try {
                    var maybe = repository.find(conn, itemId);

                    if (maybe.isEmpty()) {
                        conn.rollback();
                        return ReservationStatus.NOT_FOUND;
                    }

                    InventorySnapshot current = maybe.get();

                    if (current.availableQuantity() < requestedUnits) {
                        conn.rollback();
                        return ReservationStatus.INSUFFICIENT_STOCK;
                    }

                    int nextQuantity =
                        current.availableQuantity() - requestedUnits;

                    int updated = repository.updateIfCurrent(
                        conn, current, nextQuantity
                    );

                    if (updated == 1) {
                        conn.commit();
                        return ReservationStatus.RESERVED;
                    }

                    if (updated != 0) {
                        throw new SQLException(
                            "UPDATE vượt số hàng mong đợi");
                    }

                    // Optimistic conflict: bỏ attempt này.
                    conn.rollback();

                } catch (SQLException | RuntimeException failure) {
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                    // Không retry bừa lỗi SQL hoặc lỗi commit.
                    throw failure;
                }
            }

            // Chỉ tới đây khi UPDATE trả 0 và rollback đã thành công.
            // Attempt tiếp theo sẽ lấy connection/transaction mới.
        }

        return ReservationStatus.CONFLICT;
    }
}
~~~

**Một số chi tiết thiết kế đáng lưu ý:**

- `MAX_ATTEMPTS=3` là giới hạn minh họa. Production có thể dùng backoff ngắn có jitter và kiểm soát deadline/cancellation, không retry vô hạn.
- Chỉ **`updated==0`** được xem là optimistic conflict cho phép lặp lại trong ví dụ. SQL exception từ commit/network không được tự gộp vào loại này.
- Nếu `rollback()` thất bại ở đường conflict, phương thức ném lỗi; nó **không chạy retry trên trạng thái không đáng tin**.
- `try-with-resources` đóng/trả connection cho pool. Khi rollback lỗi hoặc mất kết nối, cần cơ chế pool loại connection lỗi và giám sát phù hợp.
- `setTransactionIsolation(...)` có thể không được hỗ trợ bởi mọi driver. Nếu ứng dụng đã có transaction manager (ví dụ Spring), ranh giới nên được quản lý tại service và tránh tự điều khiển connection bên trong repository.
- Khi return `INSUFFICIENT_STOCK`, ta chỉ biết **snapshot mới đọc** thiếu hàng. Một writer khác có thể bổ sung tồn kho ngay sau đó; đó là trạng thái đúng tại thời điểm kiểm tra, không phải sự thật bất biến.
- Trong môi trường có phân quyền theo tenant, SQL của repository cũng phải có `tenant_id`/`owner_id` phù hợp. Version không thay thế kiểm tra quyền.

### Tránh đặt các tác dụng phụ ngoài DB trong vòng retry

Sai:

~~~java
for (...) {
    sendConfirmationEmail();
    reserveStockWithRetry();
}
~~~

Nếu attempt thứ nhất xung đột, email có thể đã được gửi dù transaction chưa commit; attempt khác lại gửi tiếp.

Cách đúng hơn là xác nhận transaction **thành công rõ ràng** rồi xử lý side effect với idempotency. Nếu cần bảo đảm message/event không bị mất giữa commit và gửi, hãy cân nhắc **transactional outbox** hoặc mô hình tương ứng thay vì gửi trực tiếp trong transaction.

## 10. Khi nào dùng một câu SQL số học nguyên tử thay vì version?

Với yêu cầu đơn giản “giảm số lượng thêm `n` đơn vị nếu đủ tồn kho”, có thể để DBMS tính trực tiếp trên giá trị hiện tại:

~~~sql
UPDATE inventory_items
SET available_quantity = available_quantity - ?,
    version = version + 1
WHERE id = ?
  AND available_quantity >= ?;
~~~

JDBC:

~~~java
static boolean reserveAtomically(
        Connection conn, long itemId, int units
) throws SQLException {
    if (units <= 0) {
        throw new IllegalArgumentException(
            "units phải dương");
    }

    String sql = """
        UPDATE inventory_items
        SET available_quantity = available_quantity - ?,
            version = version + 1
        WHERE id = ?
          AND available_quantity >= ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setInt(1, units);
        ps.setLong(2, itemId);
        ps.setInt(3, units);
        return ps.executeUpdate() == 1;
    }
}
~~~

**Vì sao khác với kịch bản lost update?**

- Java **không truyền giá trị số lượng đã tính từ snapshot cũ**.
- DBMS thực hiện `available_quantity - ?` dựa trên hàng mà câu UPDATE thực sự cập nhật, theo cơ chế khóa và isolation của nó.
- Điều kiện `available_quantity >= ?` giúp từ chối khi không đủ tồn kho.
- Hai câu UPDATE hợp lệ trong một DBMS có khóa hàng/transaction phù hợp thường lần lượt giảm 2 và 3, thay vì ghi đè 8 và 7.

Tuy nhiên, cần kiểm thử hành vi đồng thời trên DBMS mục tiêu. Với mức isolation cao, một transaction có thể nhận serialization failure/deadlock và phải được retry từ đầu.

**Atomic UPDATE không thay thế optimistic locking cho mọi nghiệp vụ.** Nếu số lượng mới phụ thuộc nhiều bảng, một quy tắc giá hoặc trường cấu hình khác đã đọc từ trước, chỉ cập nhật số học một cột sẽ không chứng minh các điều kiện đó còn đúng.

### So sánh ba giải pháp

| Giải pháp | Cách chống mất cập nhật | Phù hợp | Giới hạn |
| --- | --- | --- | --- |
| **Version-based optimistic locking** | `UPDATE ... WHERE id=? AND version=?`; từ chối dữ liệu cũ | Biểu mẫu người dùng, thao tác đọc–sửa–ghi, nhiều trường | Cần kiểm tra `updateCount`, xử lý conflict và tăng version ở mọi đường ghi |
| **Atomic SQL update** | DBMS tính trên giá trị hiện tại ngay trong một lệnh SQL | Tăng/giảm số lượng, counter và điều kiện cục bộ của hàng | Không giải quyết tự động quy tắc đa bảng hoặc side effect ngoài DB |
| **Pessimistic locking** | Khóa hàng trước khi đọc–tính–ghi | Giao dịch ngắn, contention cao và yêu cầu khóa có chủ đích | Chờ khóa, deadlock, timeout; SQL/semantics khác giữa DBMS |

Không có một phương án luôn tốt hơn. Chọn theo **độ dài giao dịch, quy tắc nghiệp vụ, mức tranh chấp và khả năng DBMS**.

## 11. Pessimistic locking: `SELECT ... FOR UPDATE`

Một lựa chọn khác là đọc hàng trong transaction với khóa ghi phù hợp:

~~~sql
SELECT id, available_quantity, version
FROM inventory_items
WHERE id = ?
FOR UPDATE;
~~~

Trong PostgreSQL và MySQL/InnoDB, `FOR UPDATE` thường yêu cầu khóa hàng phù hợp để ngăn transaction khác cập nhật hàng đó đồng thời, nhưng chi tiết phụ thuộc DBMS/isolation.

Quy trình:

1. Transaction A `SELECT ... FOR UPDATE` hàng `id=1001` và nhận quantity 10.
2. Transaction B cũng `SELECT ... FOR UPDATE` hàng đó, có thể phải chờ.
3. A tính 8, UPDATE rồi commit.
4. B tiếp tục sau khi có khóa, đọc trạng thái mới 8, tính 5, UPDATE rồi commit.

Điểm cần lưu ý:

- Phải giữ **cùng connection và transaction** từ câu SELECT khóa tới câu UPDATE.
- Nếu `autoCommit=true`, khóa có thể được giải phóng khi statement/transaction kết thúc; không dùng nó như một khóa kéo dài tùy ý qua nhiều request.
- Không giữ transaction mở trong lúc đợi người dùng suy nghĩ hoặc gọi API ngoài mất nhiều giây/phút.
- Có thể xảy ra deadlock/lock timeout, cần handling và retry có giới hạn.
- `SELECT ... FOR UPDATE` không phải cú pháp tương đương trên mọi DBMS; SQL Server có cơ chế locking hint riêng, SQLite có cơ chế ghi/transaction khác.

**Không nên dùng khóa DB để bảo vệ một màn hình chỉnh sửa đang mở hàng giờ**. Optimistic locking phù hợp hơn với tình huống lưu thay đổi sau một khoảng thời gian dài.

## 12. Transaction isolation, MVCC và kết quả commit chưa rõ

Các mức isolation JDBC phổ biến:

~~~java
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
~~~

JDBC định nghĩa hằng số, nhưng **DBMS triển khai concurrency control khác nhau**. Ví dụ:

- PostgreSQL `READ COMMITTED` có thể thể hiện lost update do Java ghi một giá trị cũ theo lịch đã mô tả.
- PostgreSQL `REPEATABLE READ`/`SERIALIZABLE` có thể từ chối những transaction ghi xung đột bằng lỗi serialization; cần retry **toàn transaction**, không chỉ lệnh UPDATE.
- MySQL/InnoDB có hành vi khóa, consistent read và retry khác PostgreSQL; không coi cùng tên isolation bảo đảm cùng kết quả.
- DB nhúng như H2 có thể có lịch khóa và xử lý lỗi khác DBMS sản xuất.

### Version check bảo vệ điều gì?

`WHERE version = ?` bảo vệ hành động ghi trong một hàng **khi mọi writer phối hợp tăng version**. Nó không tự bảo vệ:

- Một transaction khác cập nhật bảng liên quan mà không chạm version của hàng này.
- Một quy tắc tổng hợp nhiều hàng (write skew).
- Một transaction đã commit nhưng phản hồi không đến client.
- Một dịch vụ ngoài DB đã xử lý thành công hay chưa.
- Quyền truy cập tenant/owner của người gọi.

### `commit()` ném lỗi mạng: phải làm gì?

Giả sử một lần `UPDATE` thành công và mã gọi `conn.commit()`, nhưng socket bị ngắt trước khi Java nhận phản hồi.

Có thể DBMS **đã commit** hoặc **chưa commit**. Chỉ dựa trên exception, không phải lúc nào ứng dụng biết chính xác.

**Không tự động retry toàn yêu cầu ghi như thể chắc chắn rollback.** Với thao tác đặt giữ hàng, retry có thể trừ tồn kho lần thứ hai.

Cần:

1. Định danh yêu cầu duy nhất, ví dụ `reservation_id`/idempotency key.
2. Một bản ghi/constraint tại DB biểu thị kết quả xử lý yêu cầu.
3. Khi kết quả commit không rõ, truy vấn lại bằng connection lành mạnh theo idempotency key và kiểm tra hậu điều kiện.
4. Chỉ retry khi đã xác định an toàn, hoặc đưa vào cơ chế đối soát theo nghiệp vụ.

**Version khác idempotency:** version ngăn ghi đè một phiên bản cũ, còn idempotency ngăn cùng một yêu cầu được áp dụng lặp lại do retry/network.

## 13. Bổ sung idempotency cho nghiệp vụ đặt giữ hàng

Một thiết kế production có thể ghi lại định danh tác vụ **trong cùng transaction với cập nhật tồn kho**:

~~~sql
CREATE TABLE stock_reservations (
    reservation_id VARCHAR(100) PRIMARY KEY,
    item_id BIGINT NOT NULL,
    units INTEGER NOT NULL CHECK (units > 0),
    status VARCHAR(20) NOT NULL
);
~~~

Ý tưởng giao dịch:

~~~mermaid
flowchart TD
    A["Nhận reservation_id duy nhất"] --> B{"ID đã tồn tại?"}
    B -- "Có" --> C["Kiểm tra payload/kết quả trước và trả kết quả idempotent"]
    B -- "Không" --> D["BEGIN transaction"]
    D --> E["Ghi reservation_id có ràng buộc UNIQUE"]
    E --> F["Trừ tồn kho bằng version hoặc SQL nguyên tử"]
    F --> G{"Thành công?"}
    G -- "Không" --> H["ROLLBACK / báo conflict"]
    G -- "Có" --> I["COMMIT cùng reservation"]
    I --> J{"Phản hồi commit rõ?"}
    J -- "Có" --> K["Trả kết quả"]
    J -- "Không" --> L["Đối soát reservation_id ở DB"]
~~~

Khi có hai request cùng `reservation_id`, ràng buộc unique giúp chống áp dụng trùng; cách xử lý xung đột phải được thiết kế theo DBMS và isolation. Không chỉ `SELECT` kiểm tra trước rồi `INSERT` vì sẽ có race giữa kiểm tra và ghi.

Trong DB có transaction, việc ghi reservation record và trừ tồn kho phải thuộc **cùng transaction**. Nếu có gọi cổng thanh toán hoặc gửi sự kiện sang hệ thống ngoài, cần cơ chế riêng (ví dụ outbox) để bảo đảm toàn bộ quy trình nghiệp vụ nhất quán.

## 14. Kiểm thử tái hiện bằng JUnit 5

Không nên tin một bài test concurrency chỉ vì nó lặp qua 100 lần và “thỉnh thoảng” tạo lỗi. Phép thử tốt cần **điều khiển được thứ tự quan sát và ghi**.

Với ví dụ này, ta có thể kiểm tra tuần tự hai transaction:

### 14.1. Kiểm tra đường không an toàn

Các bước:

1. Reset `inventory_items(1001)` về `quantity=10, version=0`.
2. Lấy hai connection và đặt `READ_COMMITTED`.
3. Cả hai thực hiện `SELECT` và đều thấy 10.
4. A cập nhật 8, commit.
5. B cập nhật 7 từ bản đọc cũ, commit.
6. Connection mới kiểm tra cuối cùng bằng 7, trong khi **nghiệp vụ đúng phải là 5**.

Dòng 6 không phải mong muốn của sản phẩm; đó là **bằng chứng lỗi** của thuật toán không có version. Hãy giữ test này trong suite minh họa/đào tạo, không dùng thuật toán ấy trong code production.

### 14.2. Kiểm tra đường có kiểm soát phiên bản

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

public final class OptimisticLockContract {
    private final DataSource dataSource;

    public OptimisticLockContract(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Test
    void staleWriterMustNotOverwriteNewerState()
            throws SQLException {
        resetFixture();

        InventoryRepository repo = new InventoryRepository();

        try (Connection a = dataSource.getConnection();
             Connection b = dataSource.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            try {
                InventorySnapshot oldA = repo.find(a, 1001L)
                    .orElseThrow();
                InventorySnapshot oldB = repo.find(b, 1001L)
                    .orElseThrow();

                assertEquals(10, oldA.availableQuantity());
                assertEquals(0L, oldA.version());
                assertEquals(oldA, oldB);

                assertEquals(1, repo.updateIfCurrent(
                    a, oldA, oldA.availableQuantity() - 2));
                a.commit();

                assertEquals(0, repo.updateIfCurrent(
                    b, oldB, oldB.availableQuantity() - 3));
                b.rollback();

                InventorySnapshot fresh = repo.find(b, 1001L)
                    .orElseThrow();
                assertEquals(8, fresh.availableQuantity());
                assertEquals(1L, fresh.version());

                assertEquals(1, repo.updateIfCurrent(
                    b, fresh, fresh.availableQuantity() - 3));
                b.commit();

            } finally {
                // Cleanup các transaction chưa hoàn tất nếu có lỗi.
                // Trong suite thật hãy lưu lỗi chính và suppress lỗi rollback.
                try { a.rollback(); }
                catch (SQLException ignored) { /* Test cleanup */ }
                try { b.rollback(); }
                catch (SQLException ignored) { /* Test cleanup */ }
            }
        }

        try (Connection verify = dataSource.getConnection()) {
            InventorySnapshot result = new InventoryRepository()
                .find(verify, 1001L).orElseThrow();
            assertEquals(5, result.availableQuantity());
            assertEquals(2L, result.version());
        }
    }

    private void resetFixture() throws SQLException {
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(
                 """
                 UPDATE inventory_items
                 SET available_quantity = 10,
                     version = 0
                 WHERE id = 1001
                 """)) {
            assertEquals(1, ps.executeUpdate());
        }
    }
}
~~~

**Chú ý về wiring:** Lớp trên là **hợp đồng test nhận `DataSource` qua constructor**, không phải một lớp JUnit 5 tự chạy độc lập nếu chưa cấu hình test framework giải quyết constructor parameter. Trong Spring Boot có thể dùng `@SpringBootTest` cùng cơ chế `@Autowired` phù hợp; trong JUnit thuần có thể dùng fixture/factory hoặc extension. Không được dùng constructor này rồi mặc định JUnit biết tự tạo DataSource.

**Đây cũng là bài test trên database riêng:** không chạy song song với một test khác cùng reset `id=1001`. Nếu dùng PostgreSQL ở production, kiểm tra bằng đúng pgJDBC và PostgreSQL test container/instance; không chỉ chạy H2.

### 14.3. Những assertion nên bổ sung

| Trường hợp | Hậu điều kiện |
| --- | --- |
| Writer A ghi thành công | `updateCount=1`; quantity=8, version=1 |
| Writer B dùng version cũ | `updateCount=0`; không ghi đè quantity=8 |
| B đọc lại và retry | Sau commit quantity=5, version=2 |
| Hàng bị xóa trong lúc chờ | `updateCount=0`; retry báo không tồn tại |
| Số lượng không đủ | Không ghi âm và không commit reservation |
| Có writer thứ ba | Một writer có thể conflict, không mất cập nhật |
| Hai request cùng idempotency key | Chỉ một tác vụ được áp dụng |
| DB/network lỗi khi commit | Không tự retry mù, phải đối soát |
| Batch có một item conflict | Rollback toàn batch nếu nghiệp vụ all-or-nothing |
| SQL lỗi constraint | Rollback và không dùng connection khi transaction còn lỗi |

Một test chỉ assert rằng `executeUpdate()` ném ngoại lệ **không đủ**: optimistic conflict thông thường được biểu diễn bằng **`0` hàng bị cập nhật**, không nhất thiết có SQL exception.

### 14.4. Nếu muốn dùng hai thread thật

Có thể dùng `CountDownLatch` hoặc `CyclicBarrier` để buộc A và B **cùng hoàn tất bước đọc** trước khi được phép ghi. Kết hợp thêm latch kiểm soát thứ tự commit để test deterministic.

Không dùng một lệnh `Thread.sleep(100)` rồi cho rằng B chắc chắn đã SELECT; scheduling của OS, JVM, network và DBMS không được bảo đảm theo số mili giây bạn ngủ.

Với hai thread, mỗi task phải sở hữu connection riêng. Tránh chia sẻ một `Connection` hoặc `PreparedStatement` cho hai task chỉ để đơn giản hóa code. Đặt deadline và cleanup để test lock/deadlock không chạy vô hạn.

## 15. Vai trò của batch, transaction và optimistic locking

Nếu một yêu cầu cần đặt giữ nhiều item trong một đơn hàng, mỗi dòng có version riêng:

~~~sql
UPDATE inventory_items
SET available_quantity = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Một chuỗi `PreparedStatement.addBatch()`/`executeBatch()` có thể trả các update counts. Nhưng:

- Driver có thể trả số hàng thực tế, hoặc `Statement.SUCCESS_NO_INFO`.
- Nếu một item có `updateCount=0`, item đó có thể đã thay đổi phiên bản.
- Nếu nghiệp vụ muốn giữ **toàn bộ giỏ hàng hoặc không giữ gì**, cần rollback toàn transaction khi một item thất bại.
- Không coi `SUCCESS_NO_INFO` là bằng chứng đúng một hàng đã thay đổi; nếu phải xác minh chính xác, lựa chọn SQL/API hoặc kiểm tra hậu điều kiện phù hợp.
- Driver có thể xử lý batch khác nhau khi SQL lỗi; `BatchUpdateException.getUpdateCounts()` không phải bằng chứng mọi lệnh đã commit.

Với một giỏ hàng nhiều item, có thể phát sinh deadlock nếu các transaction cập nhật item theo thứ tự khác nhau. Nên cân nhắc **sắp xếp các ID theo thứ tự ổn định** trước khi cập nhật, kết hợp retry transaction khi DBMS báo deadlock/serialization failure.

Không giải quyết lost update bằng cách gọi `setAutoCommit(true)` trong lúc transaction dở dang: đổi auto-commit có thể làm thay đổi trạng thái commit theo quy tắc JDBC.

## 16. Khi dùng Spring `@Transactional`

Trong hệ Spring JDBC, optimistic locking vẫn là **SQL có điều kiện phiên bản**; annotation không tự thêm điều kiện này.

Ví dụ repository với `JdbcTemplate`:

~~~java
int updated = jdbc.update(
    """
    UPDATE inventory_items
    SET available_quantity = ?,
        version = version + 1
    WHERE id = ? AND version = ?
    """,
    nextQuantity, itemId, expectedVersion
);

if (updated != 1) {
    throw new OptimisticConflictException(
        "Hàng đã thay đổi, cần tải lại"
    );
}
~~~

`OptimisticConflictException` là exception nghiệp vụ do dự án tự định nghĩa, thường là `RuntimeException` để Spring rollback theo quy tắc mặc định.

**Những cảnh báo:**

- `@Transactional` kiểm soát ranh giới transaction nếu lời gọi đi qua Spring proxy và `JdbcTemplate` dùng đúng DataSource/transaction manager; nó không tự kiểm soát phiên bản.
- Nếu catching conflict và **nuốt exception** bên trong method transactional, transaction có thể commit những bước trước đó. Phải rollback hoặc đánh dấu rollback-only theo hợp đồng.
- Mỗi lần retry cần **transaction mới**. Không tiếp tục trong transaction PostgreSQL đã bị aborted do lỗi SQL.
- Nếu dùng JPA/Hibernate, `@Version` có cơ chế riêng của ORM; bài này trình bày **JDBC thuần** và điều kiện `version` viết tường minh.
- Không chia sẻ cùng entity snapshot stale giữa các lần retry.

## 17. Các lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Đọc 10 rồi UPDATE số lượng bằng hằng 7 | Ghi đè kết quả writer khác | Version check hoặc SQL số học nguyên tử |
| Chỉ bật `autoCommit=false` | Không tự phát hiện giá trị đã cũ | Kiểm tra version/isolation/locking |
| Chỉ dùng `PRIMARY KEY` | Ngăn trùng hàng, không ngăn lost update | `WHERE id=? AND version=?` |
| Cập nhật quantity nhưng quên tăng version | Writer khác không phát hiện thay đổi | Tất cả đường ghi phải tuân thủ version contract |
| Gọi `executeUpdate()` nhưng không kiểm counts | Báo thành công dù conflict trả 0 | Kiểm tra đúng số hàng |
| Nếu 0 hàng thì UPDATE lại không có version | Vô hiệu hóa cơ chế bảo vệ | Rollback, reload, giải quyết xung đột |
| Retry nguyên giá trị mới `7` | Vẫn ghi từ dữ liệu cũ | Đọc lại và tính `current - requested` |
| Retry vô hạn dưới contention | Tăng tải, kéo dài latency | Retry bounded, backoff/deadline |
| Retry sau lỗi commit chưa rõ | Có thể thực hiện trừ tồn kho hai lần | Idempotency key và đối soát |
| Rollback từ thread khác khi query đang chạy | Race trên connection/transaction | Transaction owner xử lý cleanup |
| Giữ connection khi user mở form hàng giờ | Tốn tài nguyên và giữ khóa/snapshot | Optimistic locking với phiên bản được lưu |
| Dùng `SELECT FOR UPDATE` ở mọi DBMS không đổi cú pháp | Syntax/locking semantics khác nhau | Kiểm thử dialect/DBMS |
| Tin rằng `READ_COMMITTED` luôn cấm lost update | Không đúng với mọi read–modify–write | Test lịch thực tế và đặt version predicate |
| Dùng `SERIALIZABLE` rồi không xử lý SQLState retry | Giao dịch có thể bị từ chối | Retry toàn transaction theo chính sách |
| Test concurrency chỉ `Thread.sleep` | Race không tái hiện xác định | Latch/barrier hoặc thứ tự hai connection |
| Dùng H2 thay PostgreSQL làm kết luận cuối | Transaction/lock khác engine | Test trên DBMS và driver mục tiêu |
| Không giới hạn tenant trong `UPDATE` | Có thể ghi vượt quyền dù version khớp | Điều kiện tenant/owner bổ sung |
| Gửi email ở mỗi attempt | Side effect trùng dù attempt rollback | Outbox/idempotency sau commit |

## 18. Câu hỏi và bài tập tự luyện

**Bài 1.** Hai người cùng đọc quantity=10. A cập nhật còn 9, B cập nhật còn 8 bằng `WHERE id=?`. Giá cuối cùng là 8. Có phải cả hai yêu cầu đều đã được áp dụng không?

**Gợi ý đáp án:** Không. Nếu hai yêu cầu lần lượt trừ 1 và 2, kết quả đúng là 7; B đã ghi dựa trên giá trị 10 cũ, làm mất cập nhật của A.

**Bài 2.** Hai writer đọc `version=5`. A ghi bằng `WHERE version=5` và thành công. B ghi bằng cùng điều kiện được `0` hàng. Đó có phải SQL lỗi không?

**Gợi ý đáp án:** Không nhất thiết. `UPDATE` hợp lệ nhưng phiên bản không còn khớp; ứng dụng phải xử lý như optimistic conflict.

**Bài 3.** B gặp conflict và lập tức chạy lại `UPDATE SET quantity=8 WHERE id=?` không có version. Tại sao cách này nguy hiểm?

**Gợi ý đáp án:** Nó bỏ kiểm soát phiên bản và có thể ghi đè kết quả hiện tại của A. Cần rollback/reload và tính lại hoặc báo người dùng.

**Bài 4.** Nếu mọi writer cập nhật bằng `SET available_quantity=available_quantity-?` và kiểm `available_quantity>=?`, khi nào không cần đọc trước?

**Gợi ý đáp án:** Với phép trừ nguyên tử chỉ phụ thuộc quantity của hàng đó, có thể thực hiện trực tiếp một câu UPDATE; vẫn kiểm tra update count, transaction và quy tắc nghiệp vụ khác.

**Bài 5.** Version chỉ tăng trong màn hình sửa tồn kho, còn job nhập hàng dùng `UPDATE available_quantity=...` nhưng không tăng version. Có còn ngăn lost update không?

**Gợi ý đáp án:** Không đầy đủ. Một writer không tăng version phá hợp đồng, khiến các writer khác có thể không phát hiện dữ liệu đã đổi.

**Bài 6.** Sau `UPDATE` phiên bản trả `1`, `commit()` ném lỗi mạng. Có nên retry ngay phép trừ 3 đơn vị không?

**Gợi ý đáp án:** Không. Không rõ commit đã thành công hay chưa; retry có thể trừ hai lần. Cần idempotency key và đối soát.

**Bài 7.** Hai connection cùng ở `TRANSACTION_READ_COMMITTED`, cả hai đọc 10 trước rồi A commit 8, B ghi hằng 7 sau đó. Vì sao vẫn có thể lost update?

**Gợi ý đáp án:** READ_COMMITTED không tự kiểm giá trị cũ nằm trong biến Java. B không đưa `version`/giá trị cũ vào điều kiện UPDATE.

**Bài 8.** Đặt `@Transactional` trên service Spring có tự động tăng cột `version` cho JDBC thuần không?

**Gợi ý đáp án:** Không. Ứng dụng phải tự viết SQL versioned update; `@Transactional` chỉ điều phối transaction theo cấu hình Spring.

**Bài 9.** User để form mở 30 phút rồi nhấn Lưu. Nên khóa hàng suốt 30 phút hay dùng version?

**Gợi ý đáp án:** Thường dùng optimistic version check khi lưu; giữ transaction/row lock suốt thời gian người dùng suy nghĩ gây nghẽn tài nguyên và rủi ro timeout.

**Bài 10.** Một transaction cập nhật 10 mặt hàng, trong đó mặt hàng thứ 7 conflict. Yêu cầu all-or-nothing nên làm gì?

**Gợi ý đáp án:** Rollback toàn transaction, không commit 6 món đầu. Sau đó có thể đọc lại toàn giỏ và retry theo chính sách hoặc báo xung đột.

**Bài 11.** `UPDATE` theo version trả `0` hàng. Có chắc là vì một writer khác sửa version không?

**Gợi ý đáp án:** Không. Có thể hàng đã bị xóa, ID sai hoặc một điều kiện khác (tenant, owner, business status) không còn thỏa. Không dùng một giả định duy nhất để tiết lộ thông tin hay retry vô hạn.

**Bài 12.** Test hai thread chạy không ổn định: 20 lần chỉ 1 lần tái hiện lost update. Làm sao biến thành test có thể tin cậy?

**Gợi ý đáp án:** Điều khiển để cả hai đọc cùng snapshot trước khi cho A ghi, rồi B ghi sau A commit; dùng latch/barrier hoặc hai connection điều phối tuần tự. Ghi nhận DBMS/isolation và kiểm tra hậu điều kiện từ connection mới.

## Ghi nhớ

- **Lost update là ghi đè từ dữ liệu đã cũ**, điển hình khi ứng dụng đọc → tính toán → `UPDATE SET value=? WHERE id=?` mà không kiểm tra state.
- **Transaction không tự bảo đảm mọi phép đọc–sửa–ghi đều an toàn**. Isolation/locking khác nhau theo DBMS và cách viết SQL.
- **Optimistic locking dùng `version` trong điều kiện UPDATE**, tăng version khi ghi; `updateCount=0` là tín hiệu không được commit như thành công.
- **Xung đột cần rollback, tải lại và tính lại trong transaction mới** nếu nghiệp vụ cho phép; không bỏ điều kiện version và không retry vô hạn.
- **Atomic SQL arithmetic update** có thể giải quyết bài toán tăng/giảm đơn giản trực tiếp tại DBMS; `SELECT FOR UPDATE` phù hợp giao dịch ngắn cần khóa.
- **Version không thay idempotency hoặc phân quyền**. Với commit không rõ kết quả, đối soát bằng định danh yêu cầu; với nhiều tenant, luôn thêm predicate quyền.
- **Kiểm thử bằng hai connection và lịch xác định**, xác minh số lượng cuối, version và rollback; chạy trên driver/DBMS thực tế được triển khai.
