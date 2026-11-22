# Phân biệt kết quả nhạy và không nhạy với thay đổi dữ liệu trong JDBC

Trong chương **ResultSet nâng cao**, một câu hỏi thường gặp khi đọc dữ liệu qua JDBC là: **Nếu một người khác sửa dữ liệu trong cơ sở dữ liệu sau khi ta đã mở `ResultSet`, kết quả đang đọc có thay đổi theo hay không?**

Câu trả lời phụ thuộc vào **loại `ResultSet`**, hỗ trợ của JDBC driver và DBMS, giao dịch đang chạy, mức cô lập, cũng như cách ứng dụng di chuyển con trỏ. Hai loại quan trọng cần phân biệt là:

- **`ResultSet.TYPE_SCROLL_INSENSITIVE`**: cho phép di chuyển con trỏ qua lại; nhìn chung không phản ánh thay đổi do giao dịch khác thực hiện sau khi kết quả được tạo.
- **`ResultSet.TYPE_SCROLL_SENSITIVE`**: cho phép di chuyển con trỏ qua lại và có khả năng phản ánh một số thay đổi do giao dịch khác thực hiện trong lúc kết quả còn mở.

Cả hai đều thuộc API **JDBC chuẩn**. Tuy nhiên, “sensitive” **không có nghĩa kết quả luôn được cập nhật tức thời hoặc mọi thay đổi đều nhìn thấy**, còn “insensitive” **không đồng nghĩa kết quả được bảo vệ bởi transaction isolation cao nhất**. Bài học hướng dẫn cách hiểu chính xác, kiểm tra hỗ trợ của driver và sử dụng chúng cùng `Connection`, `PreparedStatement`, `ResultSet`.

## 1. Ba loại `ResultSet` theo khả năng di chuyển và tính nhạy

JDBC định nghĩa ba hằng số loại con trỏ trong `java.sql.ResultSet`:

| Loại `ResultSet` | Di chuyển con trỏ | Phản ánh thay đổi từ giao dịch khác khi kết quả đang mở |
| --- | --- | --- |
| `TYPE_FORWARD_ONLY` | Theo hướng tiến tới bằng `next()`; không bảo đảm khả năng quay lại | Không có cam kết chung: có thể nhạy hoặc không nhạy tùy triển khai |
| `TYPE_SCROLL_INSENSITIVE` | Có thể gọi `previous()`, `absolute()`, `relative()`, `first()`, `last()`... | Theo ngữ nghĩa loại này, không nhạy với thay đổi bên ngoài trong khi `ResultSet` đang mở |
| `TYPE_SCROLL_SENSITIVE` | Có thể di chuyển tiến/lùi tương tự loại trên | Có khả năng thấy thay đổi từ bên ngoài; **phạm vi và thời điểm nhìn thấy tùy driver/DBMS** |

Khi ứng dụng chỉ cần đọc từng hàng theo thứ tự, loại `TYPE_FORWARD_ONLY` thường là lựa chọn đơn giản. Hai loại scrollable hữu ích khi cần di chuyển đến một hàng bất kỳ hoặc đọc lại các hàng trước đó.

### Tính nhạy (sensitivity) không phải độ nhạy về bảo mật

Trong tên `TYPE_SCROLL_SENSITIVE`, “nhạy” nghĩa là **nhạy với thay đổi của dữ liệu nguồn** khi kết quả đang mở. Nó không đề cập thông tin cá nhân, dữ liệu bí mật hay chính sách bảo vệ quyền truy cập.

### Ví dụ ngắn

Giả sử lúc ứng dụng A mở kết quả, bảng `products` có:

| id | name | price |
| ---: | --- | ---: |
| 10 | Bàn phím | 300000 |
| 20 | Chuột | 150000 |
| 30 | Màn hình | 2500000 |

Ứng dụng A thực hiện:

~~~sql
SELECT id, name, price
FROM products
ORDER BY id;
~~~

Trong khi A đang giữ `ResultSet` mở, ứng dụng B cập nhật:

~~~sql
UPDATE products SET price = 180000 WHERE id = 20;
COMMIT;
~~~

Nếu A quay lại hàng `id = 20`:

- Với **`TYPE_SCROLL_INSENSITIVE`**, A thông thường vẫn đọc được `150000` từ kết quả đang mở.
- Với **`TYPE_SCROLL_SENSITIVE`**, A **có thể** đọc được `180000` nếu driver/DBMS cho phép thay đổi của B hiển thị và transaction của A đủ điều kiện nhìn thấy.
- Với **`TYPE_FORWARD_ONLY`**, A không thể mặc nhiên quay lại hàng cũ bằng `previous()` hoặc `absolute()`; cần thiết kế truy vấn khác để lấy lại dữ liệu.

Không được suy ra từ tên loại rằng việc thấy `180000` là chắc chắn. Cần kiểm tra capability metadata và thử nghiệm trong điều kiện transaction/isolation thực tế.

## 2. Tính nhạy đối với `UPDATE`, `DELETE`, `INSERT`

Một giao dịch khác có thể thay đổi **giá trị của hàng đã có**, **xóa hàng** hoặc **thêm hàng mới**. Ba loại thay đổi này không nhất thiết được xử lý giống nhau.

| Thao tác của giao dịch B | `TYPE_SCROLL_INSENSITIVE` đang mở ở A | `TYPE_SCROLL_SENSITIVE` đang mở ở A |
| --- | --- | --- |
| `UPDATE` hàng A đã đọc | Thường giữ giá trị ở thời điểm tạo kết quả | Có thể thấy giá trị mới khi con trỏ đọc lại hoặc refresh, nếu hỗ trợ |
| `DELETE` hàng đã nằm trong kết quả | Không tự phản ánh xóa do giao dịch khác | Có thể phát hiện hàng bị xóa hoặc thay đổi cách duyệt, tùy driver |
| `INSERT` hàng mới thỏa `WHERE` | Không tự thêm hàng mới do giao dịch khác vào kết quả hiện có | Khả năng xuất hiện hàng mới phụ thuộc mạnh vào triển khai và kiểu cursor |

**Đặc biệt lưu ý thao tác `INSERT`:** Một `ResultSet` “sensitive” không được hiểu là danh sách hàng luôn tự thêm tất cả bản ghi mới và sắp xếp lại ngay lập tức. Driver có thể phản ánh cập nhật của các hàng hiện có nhưng **không** đưa hàng vừa insert vào cursor đang mở.

Nếu yêu cầu nghiệp vụ là “hiển thị danh sách mới nhất”, cách đáng tin cậy hơn thường là **thực thi lại một câu `SELECT` trong một giao dịch phù hợp**, hoặc dùng cơ chế nhận sự kiện thay đổi chuyên biệt; không dựa toàn bộ vào scroll-sensitive cursor.

### Sơ đồ thời gian

~~~mermaid
sequenceDiagram
    participant A as Kết nối A
    participant DB as CSDL
    participant B as Kết nối B
    A->>DB: SELECT products ORDER BY id
    DB-->>A: ResultSet; giá id=20 là 150000
    A->>A: Đọc hàng id=20
    B->>DB: UPDATE id=20, price=180000
    B->>DB: COMMIT
    A->>A: Di chuyển về hàng id=20
    Note over A,DB: INSENSITIVE thường vẫn là 150000
    Note over A,DB: SENSITIVE có thể thấy 180000 nếu khả năng nhìn thấy cho phép
~~~

Sơ đồ diễn tả thay đổi **đã commit** ở kết nối B. Nếu B chưa commit, A có nhìn thấy hay không còn bị chi phối bởi isolation và đặc điểm DBMS; không được dùng sensitivity như cơ chế đọc dữ liệu chưa commit.

## 3. Khởi tạo `ResultSet` với loại mong muốn

Một `PreparedStatement` thông thường được tạo như sau:

~~~java
PreparedStatement ps = conn.prepareStatement(
    "SELECT id, name, price FROM products ORDER BY id"
);
~~~

Với trường hợp phổ biến này, `ResultSet` có loại `TYPE_FORWARD_ONLY` và chế độ `CONCUR_READ_ONLY` theo mặc định JDBC.

Để yêu cầu kết quả **scroll-insensitive**:

~~~java
PreparedStatement ps = conn.prepareStatement(
    "SELECT id, name, price FROM products ORDER BY id",
    ResultSet.TYPE_SCROLL_INSENSITIVE,
    ResultSet.CONCUR_READ_ONLY
);
~~~

Để yêu cầu **scroll-sensitive**:

~~~java
PreparedStatement ps = conn.prepareStatement(
    "SELECT id, name, price FROM products ORDER BY id",
    ResultSet.TYPE_SCROLL_SENSITIVE,
    ResultSet.CONCUR_READ_ONLY
);
~~~

Các overload tương ứng cũng tồn tại ở `Connection.createStatement(int type, int concurrency)` và `Connection.prepareCall(...)`.

**Không phải cứ yêu cầu là được bảo đảm.** Nếu driver không hỗ trợ, nó có thể ném `SQLException` hoặc trả về kết quả có khả năng thấp hơn, tùy driver và quy tắc JDBC liên quan. Vì thế phải dùng `DatabaseMetaData` để kiểm tra khả năng và **đọc lại loại thực tế bằng `ResultSet.getType()`**.

## 4. Kiểm tra driver/DBMS có hỗ trợ loại con trỏ không

`DatabaseMetaData` cho biết driver và DBMS công bố hỗ trợ các loại `ResultSet` và cơ chế quan sát thay đổi:

| Phương thức | Điều cần biết |
| --- | --- |
| `supportsResultSetType(type)` | Có hỗ trợ loại con trỏ được yêu cầu không? |
| `supportsResultSetConcurrency(type, concurrency)` | Có hỗ trợ kết hợp loại con trỏ với `CONCUR_READ_ONLY` hoặc `CONCUR_UPDATABLE` không? |
| `othersUpdatesAreVisible(type)` | Thay đổi `UPDATE` của transaction khác có thể thấy ở loại kết quả này không? |
| `othersDeletesAreVisible(type)` | Thao tác xóa của transaction khác có thể thấy không? |
| `othersInsertsAreVisible(type)` | Thao tác thêm của transaction khác có thể thấy không? |
| `ownUpdatesAreVisible(type)` | Các cập nhật do **chính result set/transaction hiện tại** thực hiện có thể thấy không? |
| `ownDeletesAreVisible(type)`, `ownInsertsAreVisible(type)` | Cơ chế hiển thị thay đổi của chính ứng dụng |
| `updatesAreDetected(type)` | `ResultSet.rowUpdated()` có khả năng phát hiện cập nhật không? |
| `deletesAreDetected(type)`, `insertsAreDetected(type)` | Khả năng phát hiện xóa/thêm qua các phương thức `rowDeleted()`/`rowInserted()` |

**Ba nhóm câu hỏi khác nhau:** driver có tạo được loại con trỏ không, thay đổi có thể hiển thị không, và driver có thể **đánh dấu** trạng thái thay đổi cho ứng dụng không. Chúng không đồng nghĩa nhau.

### Mã Java kiểm tra capability

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ResultSetCapabilities {
    private ResultSetCapabilities() {}

    public static void report(DataSource dataSource)
            throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            DatabaseMetaData meta = conn.getMetaData();

            System.out.println("DBMS: "
                + meta.getDatabaseProductName());
            System.out.println("Driver: "
                + meta.getDriverName());

            int[] types = {
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.TYPE_SCROLL_INSENSITIVE,
                ResultSet.TYPE_SCROLL_SENSITIVE
            };

            for (int type : types) {
                boolean supported = meta.supportsResultSetType(type);

                System.out.println("ResultSet type = " + type
                    + ", supported = " + supported);

                if (!supported) {
                    continue;
                }

                System.out.println("  Read-only concurrency: "
                    + meta.supportsResultSetConcurrency(
                        type, ResultSet.CONCUR_READ_ONLY));

                System.out.println("  Other UPDATE visible: "
                    + meta.othersUpdatesAreVisible(type));

                System.out.println("  Other DELETE visible: "
                    + meta.othersDeletesAreVisible(type));

                System.out.println("  Other INSERT visible: "
                    + meta.othersInsertsAreVisible(type));

                System.out.println("  Own UPDATE visible: "
                    + meta.ownUpdatesAreVisible(type));

                System.out.println("  Updates detected: "
                    + meta.updatesAreDetected(type));
            }
        }
    }
}
~~~

Đây là cách đọc năng lực **trên chính kết nối ứng dụng dùng**, không phải suy đoán theo tên DBMS.

Các giá trị `false` cần được diễn giải trong phạm vi metadata. Ví dụ, `updatesAreDetected(type) == false` không tự động có nghĩa “kết quả không bao giờ nhìn thấy thay đổi”; có thể chỉ là driver không hỗ trợ cách **phát hiện/đánh dấu cập nhật qua `rowUpdated()`**.

Thông tin metadata là cơ sở để chọn API, nhưng với tính năng nhạy với thay đổi dữ liệu, **thử nghiệm hai connection trong cùng DBMS/driver/isolation** vẫn cần thiết nếu nghiệp vụ phụ thuộc vào khả năng quan sát thay đổi.

## 5. Ví dụ Java: tạo cursor và kiểm tra loại thực tế

Ví dụ sau đọc bảng `products` với `DataSource`. SQL dùng `PreparedStatement` và placeholder để bảo đảm tham số hóa. Chương trình ưu tiên loại **scroll-sensitive** nếu driver công bố hỗ trợ cả loại đó lẫn `CONCUR_READ_ONLY`; nếu không, chọn **scroll-insensitive**, cuối cùng về **forward-only**.

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductCursorReader {
    private final DataSource dataSource;

    public ProductCursorReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void readProducts(BigDecimal minimumPrice)
            throws SQLException {
        String sql = """
            SELECT id, name, price
            FROM products
            WHERE price >= ?
            ORDER BY id
            """;

        try (Connection conn = dataSource.getConnection()) {
            DatabaseMetaData meta = conn.getMetaData();
            int requestedType = chooseType(meta);

            try (PreparedStatement ps = conn.prepareStatement(
                    sql,
                    requestedType,
                    ResultSet.CONCUR_READ_ONLY)) {

                ps.setBigDecimal(1, minimumPrice);

                try (ResultSet rs = ps.executeQuery()) {
                    int actualType = rs.getType();
                    System.out.println("Requested type: "
                        + requestedType);
                    System.out.println("Actual type: "
                        + actualType);

                    if (actualType == ResultSet.TYPE_FORWARD_ONLY) {
                        // Forward-only: đi tới bằng next().
                        while (rs.next()) {
                            printCurrentRow(rs);
                        }
                    } else {
                        // Scrollable: có thể di chuyển tới/lùi.
                        if (rs.first()) {
                            printCurrentRow(rs);

                            if (rs.next()) {
                                printCurrentRow(rs);
                                rs.previous();
                                System.out.println(
                                    "Quay lại hàng đầu tiên:");
                                printCurrentRow(rs);
                            }
                        }

                        // Ví dụ di chuyển đến hàng cuối, nếu có.
                        if (rs.last()) {
                            System.out.println("Hàng cuối:");
                            printCurrentRow(rs);
                        }
                    }
                }
            }
        }
    }

    private static int chooseType(DatabaseMetaData meta)
            throws SQLException {
        int[] preferred = {
            ResultSet.TYPE_SCROLL_SENSITIVE,
            ResultSet.TYPE_SCROLL_INSENSITIVE,
            ResultSet.TYPE_FORWARD_ONLY
        };

        for (int type : preferred) {
            if (meta.supportsResultSetType(type)
                    && meta.supportsResultSetConcurrency(
                        type, ResultSet.CONCUR_READ_ONLY)) {
                return type;
            }
        }
        throw new SQLException(
            "Driver không công bố ResultSet phù hợp"
        );
    }

    private static void printCurrentRow(ResultSet rs)
            throws SQLException {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        BigDecimal price = rs.getBigDecimal("price");

        System.out.printf(
            "id=%d, name=%s, price=%s%n",
            id, name, price
        );
    }
}
~~~

Mã minh họa dùng Java 17+ và giả định bảng có các cột `id`, `name`, `price`. Ví dụ gọi:

~~~java
var reader = new ProductCursorReader(dataSource);
reader.readProducts(new java.math.BigDecimal("100000"));
~~~

**Các điểm đáng chú ý:**

1. `PreparedStatement` nhận loại con trỏ **ngay khi tạo statement**. Không thể đổi một `ResultSet` hiện có từ insensitive sang sensitive bằng cách gọi `getType()`.
2. `getType()` cho biết loại kết quả **thực tế** sau khi execute, hữu ích để phát hiện driver hạ cấp tính năng.
3. `rs.first()` và `rs.last()` là thao tác scrollable; tránh gọi chúng khi `actualType == TYPE_FORWARD_ONLY`.
4. Kết quả rỗng khiến `rs.first()`/`rs.last()` trả `false`; không cố đọc cột khi con trỏ không nằm trên hàng hợp lệ.
5. `ORDER BY id` giữ thứ tự truy vấn rõ ràng. Không có `ORDER BY`, vị trí hàng có thể không ổn định giữa các lần truy vấn.
6. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và trả/đóng `Connection`; không giữ cursor mở quá lâu nếu không cần.

Chương trình trên minh họa **lựa chọn type và cách di chuyển**, chưa chứng minh dữ liệu có thực sự thay đổi khi một kết nối khác update. Điều đó cần kịch bản kiểm thử riêng ở phần kế tiếp.

## 6. Kiểm thử tính nhạy bằng hai connection

Muốn kiểm tra một driver có hiển thị thay đổi bên ngoài hay không, nên tạo bài thử nghiệm kiểm soát được **cả dữ liệu, isolation và thời điểm commit**.

Giả sử bảng `products` có bản ghi:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);

INSERT INTO products(id, name, price)
VALUES (20, 'Chuột', 150000.00);
~~~

*Thực hiện trên cơ sở dữ liệu thử nghiệm; không dùng dữ liệu sản xuất để đổi giá chỉ nhằm quan sát cursor.*

### Quy trình kiểm thử

| Bước | Connection A (đang đọc) | Connection B (đang cập nhật) |
| ---: | --- | --- |
| 1 | Xác lập isolation phù hợp với phép thử; tạo `PreparedStatement` nhạy hoặc không nhạy | — |
| 2 | Thực thi `SELECT ... ORDER BY id` và đọc `id = 20` với `price = 150000` | — |
| 3 | Giữ `ResultSet` của A đang mở | `UPDATE price = 180000 WHERE id = 20` |
| 4 | — | `COMMIT` |
| 5 | Di chuyển khỏi hàng rồi quay lại hàng `id = 20` bằng cursor scrollable | — |
| 6 | Đọc lại `price`, ghi nhận loại thực tế, isolation và khả năng hiển thị | — |
| 7 | Đóng cursor; thực thi lại `SELECT` trong transaction mới để đối chiếu | — |

Khi thử với `TYPE_SCROLL_SENSITIVE`, quan sát sau bước 5 có thể:

- **Thấy `180000`:** driver thực sự đưa thay đổi của B vào kết quả ở điều kiện thử nghiệm này.
- **Vẫn thấy `150000`:** chưa thể khẳng định loại sensitive bị lỗi; có thể driver/DBMS không hỗ trợ dạng visibility đó, cursor đã cache giá trị, hoặc transaction của A đang dùng snapshot không thấy commit mới.
- **Thông báo không hỗ trợ hoặc loại thực tế khác:** cần ghi nhận driver và thay đổi chiến lược truy vấn.

Với `TYPE_SCROLL_INSENSITIVE`, giá trị trong kết quả đang mở thường giữ `150000` dù B đã commit. Nhưng **mở một truy vấn mới** sau đó có thể trả `180000` nếu transaction và isolation cho phép. Tính “không nhạy” chỉ mô tả **cursor đang mở**, không có nghĩa những câu `SELECT` trong tương lai sẽ mãi nhìn thấy giá trị cũ.

### Ví dụ truy vấn A và B (dùng SQL client)

Connection A:

~~~sql
SELECT id, price FROM products ORDER BY id;
-- Trong Java, truy vấn phải tạo bằng PreparedStatement yêu cầu
-- TYPE_SCROLL_INSENSITIVE hoặc TYPE_SCROLL_SENSITIVE.
-- Giữ ResultSet mở, đọc giá của id=20.
~~~

Connection B:

~~~sql
UPDATE products SET price = 180000.00 WHERE id = 20;
COMMIT;
~~~

Sau đó ứng dụng Java ở A quay lại hàng `id = 20` trên cursor đã mở để quan sát. Một công cụ SQL client thông thường có thể **không thể tạo cùng kiểu cursor JDBC**; vì vậy thử nghiệm kết luận về sensitivity phải thực hiện bằng JDBC driver thực tế.

**Quan trọng:** nếu `Connection A` dùng transaction mức `REPEATABLE_READ` hoặc `SERIALIZABLE` với cơ chế snapshot phù hợp, việc không nhìn thấy commit của B có thể xuất phát từ isolation, kể cả khi driver báo hỗ trợ loại sensitive. Phải ghi nhận và kiểm soát isolation mới so sánh được.

## 7. `refreshRow()` có làm dữ liệu chắc chắn mới nhất không?

JDBC có `ResultSet.refreshRow()` để yêu cầu driver **làm mới dữ liệu của hàng hiện tại từ DBMS** khi driver có cache hoặc prefetch. Nó có thể hữu ích khi cần kiểm tra một hàng đã được người khác cập nhật.

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

static void tryRefreshCurrentRow(ResultSet rs)
        throws SQLException {
    if (rs.getType() == ResultSet.TYPE_FORWARD_ONLY) {
        System.out.println(
            "Không thể mặc định refreshRow trên forward-only"
        );
        return;
    }

    try {
        rs.refreshRow();
        System.out.println(
            "Giá hiện được cursor nhìn thấy: "
            + rs.getBigDecimal("price")
        );
    } catch (SQLFeatureNotSupportedException unsupported) {
        System.out.println(
            "Driver không hỗ trợ refreshRow trong cấu hình này"
        );
    }
}
~~~

**Giới hạn cần ghi nhớ:**

- `refreshRow()` không bắt buộc được hỗ trợ trong mọi cấu hình driver và loại `ResultSet`. Có thể phát sinh `SQLException` khác nếu cursor không ở hàng hợp lệ hoặc DBMS không cho thao tác.
- Không gọi khi cursor ở vị trí *before first*, *after last* hoặc vùng insert row. Cần định vị vào một hàng hiện có trước khi refresh.
- Phương thức có thể làm mới **hàng hiện tại hoặc một nhóm hàng do driver cache**, không được coi là thao tác reload toàn bộ truy vấn với danh sách hàng mới.
- Khi transaction isolation không cho phép nhìn thấy commit mới, refresh không bảo đảm vượt qua quy tắc isolation.
- Nếu bản ghi đã bị xóa bởi giao dịch khác, hành vi khi refresh phụ thuộc driver; cần xử lý lỗi và tình huống hàng không còn tồn tại.

**Muốn bảo đảm truy vấn lại trạng thái mới theo chính sách nhất quán đã định?** Đóng cursor cũ, bắt đầu transaction mới khi cần, và thực thi lại `SELECT` qua `PreparedStatement`. Khi đọc dữ liệu đang thay đổi liên tục, vẫn tồn tại một khoảng thời gian giữa việc đọc và sử dụng; không có bảo đảm “luôn mới nhất” vĩnh viễn.

## 8. Sensitivity khác transaction isolation

Đây là hai chiều điều khiển **khác nhau**:

- **ResultSet sensitivity**: con trỏ đang mở có phản ánh thay đổi bên ngoài khi di chuyển/đọc lại hay không.
- **Transaction isolation**: giao dịch có được nhìn thấy thay đổi chưa commit, snapshot mới hoặc các bất thường đọc/ghi như thế nào theo DBMS và mức isolation.

JDBC dùng:

~~~java
conn.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

và:

~~~java
conn.prepareStatement(
    sql,
    ResultSet.TYPE_SCROLL_SENSITIVE,
    ResultSet.CONCUR_READ_ONLY
);
~~~

Hai lời gọi giải quyết hai câu hỏi khác nhau. Không thay thế cái này bằng cái kia.

### Kết hợp tình huống thường gặp

| Cursor | Isolation / ngữ cảnh | Điều nên kỳ vọng |
| --- | --- | --- |
| Scroll-insensitive | `READ_COMMITTED` | Cursor đang mở nhìn chung giữ dữ liệu đã lấy; một `SELECT` mới có thể đọc commit mới |
| Scroll-sensitive | `READ_COMMITTED` | Có thể phản ánh cập nhật bên ngoài nếu driver/DBMS hỗ trợ |
| Scroll-sensitive | Snapshot transaction hoặc `REPEATABLE_READ` tùy triển khai | Có thể vẫn giữ giá trị cũ vì snapshot/isolation |
| Forward-only | Bất kỳ isolation | Không có khả năng cuộn về hàng cũ được bảo đảm; sensitivity không phải trọng tâm của kiểu này |
| Bất kỳ cursor | Giao dịch khác chưa commit | Khả năng thấy thay đổi do isolation quyết định; không dùng sensitive để vượt qua isolation |

Các hàng trên là **mô hình lập luận**, không phải ma trận bảo đảm cho mọi DBMS. Ví dụ cách triển khai `REPEATABLE_READ` và `SERIALIZABLE` khác nhau giữa các hệ quản trị. Dữ liệu đọc lại bằng statement mới cũng có thể vẫn thấy snapshot cũ nếu giữ nguyên transaction snapshot.

Khi cần cập nhật dữ liệu dựa trên giá trị vừa đọc, tính sensitivity **không tự ngăn lost update**. Có thể cần khóa hàng, điều kiện phiên bản trong `UPDATE` hoặc transaction isolation thích hợp.

## 9. Sensitivity không đồng nghĩa `CONCUR_UPDATABLE`

Khi tạo statement, tham số thứ hai thường là **concurrency mode**:

- `ResultSet.CONCUR_READ_ONLY`: không dùng các API cập nhật hàng thông qua `ResultSet`.
- `ResultSet.CONCUR_UPDATABLE`: cho phép dùng những API như `updateString(...)` và `updateRow()` khi câu truy vấn/driver cho phép.

Đây là **trục khác với loại forward-only/scroll-insensitive/scroll-sensitive**.

| Tính năng | Quyết định bởi |
| --- | --- |
| Có thể gọi `previous()`, `absolute()`? | ResultSet type có scrollable không |
| Có thể phản ánh thay đổi của transaction khác? | Sensitivity, driver/DBMS, isolation và khả năng visibility |
| Có thể cập nhật bản ghi từ chính cursor? | `CONCUR_UPDATABLE` cùng các điều kiện hỗ trợ của driver/truy vấn |
| Có thể phát hiện hàng thay đổi bằng `rowUpdated()`? | Khả năng detection của driver cho loại result set |
| Có thể giữ cursor mở sau commit? | ResultSet holdability / hành vi giao dịch |

Ví dụ một cursor có thể **scroll-insensitive và updatable**: nó cho phép ứng dụng chỉnh sửa bản ghi **qua chính cursor** dù không tự phản ánh cập nhật của **người khác**. Chi tiết về việc nhìn thấy các cập nhật do chính ứng dụng thực hiện cần kiểm tra `ownUpdatesAreVisible(type)`.

### Minh họa cập nhật qua cursor (khi được hỗ trợ)

~~~java
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT id, name FROM products WHERE id = ?",
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE)) {

    ps.setLong(1, 20L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            rs.updateString("name", "Chuột không dây");
            rs.updateRow();
        }
    }
}
~~~

Đoạn mã chỉ minh họa API; **khả năng thực thi phụ thuộc DBMS/driver và dạng SELECT**, ví dụ có đủ thông tin khóa để xác định hàng cần update. Cần kiểm tra `supportsResultSetConcurrency(type, ResultSet.CONCUR_UPDATABLE)`, kiểm tra loại/concurrency thực tế và quản lý commit/rollback của connection.

Với nghiệp vụ cập nhật thông thường, `PreparedStatement` chạy `UPDATE ... WHERE id = ?` với tham số hóa, kiểm tra số hàng cập nhật và transaction rõ ràng thường dễ kiểm soát và di chuyển giữa DBMS hơn.

## 10. `rowUpdated()`, `rowDeleted()`, `rowInserted()` có thay thế truy vấn lại không?

Ba phương thức này liên quan đến **khả năng phát hiện** hàng bị cập nhật/xóa/thêm trong `ResultSet` theo triển khai driver.

~~~java
if (rs.rowUpdated()) {
    System.out.println("Driver phát hiện hàng đã được cập nhật");
}
if (rs.rowDeleted()) {
    System.out.println("Driver phát hiện hàng đã bị xóa");
}
if (rs.rowInserted()) {
    System.out.println("Driver phát hiện hàng đã được thêm");
}
~~~

Tuy nhiên:

- Chỉ sử dụng khi driver/DBMS hỗ trợ tương ứng, có thể kiểm tra qua `updatesAreDetected(type)`, `deletesAreDetected(type)` và `insertsAreDetected(type)`.
- Các phương thức là kết quả phát hiện theo **cursor và driver**, không đại diện cho một hệ thống audit đầy đủ.
- `false` không tự chứng minh “dữ liệu chưa từng thay đổi” nếu driver không hỗ trợ phát hiện.
- Đừng dùng các cờ này như cơ chế đảm bảo ngăn thay đổi song song hoặc làm căn cứ quyết định tài chính quan trọng.

Nếu cần theo dõi lịch sử thay đổi, dùng cột phiên bản, audit table, event log hoặc change data capture phù hợp với DBMS và nghiệp vụ.

## 11. Holdability, vòng đời cursor và tài nguyên

JDBC còn có **holdability** quyết định cursor được giữ qua `COMMIT` hay đóng sau commit:

- `ResultSet.HOLD_CURSORS_OVER_COMMIT`
- `ResultSet.CLOSE_CURSORS_AT_COMMIT`

Có thể kiểm tra hỗ trợ bằng `DatabaseMetaData.supportsResultSetHoldability(...)` và trạng thái qua `ResultSet.getHoldability()`.

**Holdability không phải sensitivity.** Một cursor được giữ sau commit chưa chắc có thể đọc dữ liệu mới; một cursor sensitive cũng không tự được giữ mở qua commit.

Khi dùng cursor lâu, cần cân nhắc:

- ResultSet scrollable có thể khiến driver **cache hoặc materialize** nhiều hàng để hỗ trợ di chuyển ngược. Với dữ liệu lớn, có thể tốn heap, bộ nhớ DBMS hoặc giữ tài nguyên server.
- `Statement.setFetchSize(...)` chủ yếu là gợi ý kích thước lấy dữ liệu theo đợt, **không** biến cursor thành sensitive hoặc không sensitive.
- Kết nối và ResultSet phải sống đủ lâu để truy cập; khi đóng statement hoặc connection, result set liên quan thường không còn sử dụng được.
- Cursor và transaction mở quá lâu có thể giữ snapshot hoặc khóa, tăng tải, cản trở dọn phiên bản dữ liệu hoặc phát sinh timeout.
- Không chia sẻ cùng `ResultSet` giữa các luồng mà không có thiết kế đồng bộ thích hợp. Hành vi đồng thời của cursor/connection không nên bị giả định là thread-safe.

Với danh sách lớn, **phân trang bằng điều kiện ổn định** (ví dụ keyset pagination theo khóa sắp xếp) và truy vấn mới thường dễ kiểm soát hơn việc giữ scroll-sensitive ResultSet mở trong thời gian dài.

## 12. Chọn loại `ResultSet` theo nghiệp vụ

| Nhu cầu | Hướng phù hợp | Lý do |
| --- | --- | --- |
| Đọc và xử lý một lượt hàng nghìn bản ghi | `TYPE_FORWARD_ONLY` kết hợp streaming/fetch size phù hợp | Không cần khả năng quay lại |
| Hiển thị một tập kết quả có thể điều hướng trước/sau, muốn giữ tập dữ liệu ổn định | `TYPE_SCROLL_INSENSITIVE` nếu driver hỗ trợ | Dễ dự đoán với thay đổi từ connection khác |
| Cần thử quan sát thay đổi bên ngoài khi con trỏ còn mở | `TYPE_SCROLL_SENSITIVE` nếu driver công bố hỗ trợ và đã kiểm thử | Có thể phản ánh cập nhật mà không thực thi lại truy vấn |
| Cần luôn lấy dữ liệu mới theo hợp đồng đọc tại một thời điểm | Thực thi lại `SELECT` trong transaction/isolation phù hợp | Không phụ thuộc timing của cursor sensitivity |
| Cần cập nhật hàng qua chính ResultSet | Kiểm tra `CONCUR_UPDATABLE` và yêu cầu truy vấn | Là trục concurrency, độc lập sensitivity |
| Cần bảo vệ khỏi ghi đè dữ liệu đồng thời | `UPDATE ... WHERE id = ? AND version = ?`, kiểm tra update count | Cursor sensitivity không tự giải quyết lost update |

Không cần mặc định chọn `TYPE_SCROLL_SENSITIVE` cho mọi ứng dụng. Nó có thể không được hỗ trợ, làm tăng chi phí, và kết quả nhìn thấy thay đổi bên ngoài khó dự đoán nếu nghiệp vụ không kiểm soát tốt transaction.

### Mẫu đọc lại có chủ đích thay vì phụ thuộc cursor đang mở

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

record ProductPrice(long id, BigDecimal price) {}

static Optional<ProductPrice> readCurrentPrice(
        DataSource dataSource, long id
) throws SQLException {
    String sql = "SELECT id, price FROM products WHERE id = ?";

    try (Connection conn = dataSource.getConnection();
         PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }

            return Optional.of(new ProductPrice(
                rs.getLong("id"),
                rs.getBigDecimal("price")
            ));
        }
    }
}
~~~

Đoạn mã tạo một câu truy vấn mới; kết quả phản ánh trạng thái mà **giao dịch mới được phép nhìn thấy**. Nếu connection pool cấp một connection có transaction đã mở hoặc isolation snapshot được cấu hình từ trước, vẫn cần xác định transaction boundary rõ ràng; bản thân việc lấy connection mới không phải bảo đảm tuyệt đối rằng mọi thay đổi mới đều nhìn thấy.

## 13. Những lỗi diễn giải thường gặp

| Ngộ nhận | Vấn đề | Cách sửa |
| --- | --- | --- |
| `TYPE_SCROLL_SENSITIVE` chắc chắn thấy mọi update ngay lập tức | Phụ thuộc driver, visibility, isolation, cache | Kiểm tra capability và kiểm thử thực tế |
| `TYPE_SCROLL_INSENSITIVE` làm DBMS ngừng thay đổi dữ liệu | Chỉ mô tả cursor đang mở | Phân biệt cursor với transaction và bản ghi nguồn |
| Scroll-insensitive đồng nghĩa snapshot transaction serializable | Hai cơ chế khác nhau | Chọn isolation theo quy tắc nghiệp vụ |
| Scroll-sensitive đồng nghĩa có thể gọi `updateRow()` | Cần `CONCUR_UPDATABLE` riêng | Kiểm tra concurrency và dạng query |
| `TYPE_FORWARD_ONLY` chắc chắn không thấy thay đổi bên ngoài | JDBC không cam kết một kiểu sensitivity chung cho forward-only | Không phụ thuộc vào giả định đó |
| `supportsResultSetType(...) == true` bảo đảm mọi sự kiện insert/update/delete đều thấy | Driver có khả năng khác nhau cho từng loại thay đổi | Kiểm tra `others...AreVisible(...)` và thử thực tế |
| `updatesAreDetected() == false` có nghĩa mọi update đều vô hình | Detection khác visibility | Kiểm tra riêng các phương thức metadata |
| `refreshRow()` chắc chắn trả bản ghi mới nhất | Có thể không hỗ trợ; vẫn chịu isolation | Xử lý ngoại lệ và query lại nếu cần |
| Có `ORDER BY` thì thứ tự vị trí không bao giờ đổi khi người khác sửa dữ liệu | Cursor sensitive có thể thay đổi dữ liệu đang xem, DBMS khác nhau | Dựa vào khóa chính và truy vấn lại khi cần |
| Giữ ResultSet lớn mở suốt phiên làm việc sẽ hiệu quả | Có thể dùng nhiều bộ nhớ và giữ tài nguyên DB | Phân trang và đóng tài nguyên sớm |
| `setFetchSize()` thay đổi tính nhạy | Chỉ là gợi ý về số hàng fetch | Chọn đúng ResultSet type |
| Nếu đọc được giá mới thì có thể ghi mà không lo người khác sửa tiếp | Có thể có race condition sau khi đọc | Optimistic locking/transaction/locking phù hợp |

## 14. Tự kiểm tra bằng tình huống

**Tình huống 1.** A mở `TYPE_SCROLL_INSENSITIVE` đọc giá sản phẩm là 150000. B cập nhật giá thành 180000 rồi commit. A di chuyển con trỏ trở lại hàng cũ. Nên kỳ vọng gì?

**Đáp án:** Kết quả đang mở thường vẫn trả giá đã quan sát trước đó, vì insensitive không phản ánh thay đổi từ connection khác. Một câu `SELECT` mới, trong transaction phù hợp, có thể đọc được 180000.

**Tình huống 2.** A mở `TYPE_SCROLL_SENSITIVE` nhưng sau khi B commit, A vẫn đọc giá 150000. Có thể kết luận driver triển khai sai JDBC không?

**Đáp án:** Chưa. Cần kiểm tra `rs.getType()`, `othersUpdatesAreVisible(type)`, transaction isolation, thời điểm đọc lại, hỗ trợ `refreshRow()` và tài liệu driver. Sensitive không bảo đảm mọi thay đổi hiển thị tức thời.

**Tình huống 3.** Driver hỗ trợ `TYPE_SCROLL_INSENSITIVE` nhưng không hỗ trợ `TYPE_SCROLL_SENSITIVE`. Ứng dụng cần `previous()` và `absolute(5)`. Có thể đáp ứng không?

**Đáp án:** Có thể yêu cầu `TYPE_SCROLL_INSENSITIVE` với concurrency được hỗ trợ. Khả năng scroll và sensitivity là hai khía cạnh khác nhau.

**Tình huống 4.** Ứng dụng muốn gọi `updateString()` rồi `updateRow()`. Chỉ cần tạo `TYPE_SCROLL_SENSITIVE` là đủ không?

**Đáp án:** Không. Còn phải yêu cầu và được hỗ trợ `CONCUR_UPDATABLE`. SQL và driver cũng phải cho phép cập nhật hàng qua cursor.

**Tình huống 5.** `meta.updatesAreDetected(TYPE_SCROLL_SENSITIVE)` trả false. Có thể kết luận người khác update hàng thì cursor sensitive chắc chắn không nhìn thấy không?

**Đáp án:** Không. Phương thức này liên quan khả năng phát hiện và đánh dấu cập nhật, còn `othersUpdatesAreVisible(...)` liên quan khả năng nhìn thấy dữ liệu cập nhật.

**Tình huống 6.** Ứng dụng cần hiển thị danh sách người dùng theo từng trang, mỗi trang 50 hàng, trong phiên có thể kéo dài nhiều phút. Nên giữ một scroll-sensitive ResultSet cho cả phiên không?

**Đáp án:** Thường không nên. Nên phân trang theo truy vấn có thứ tự ổn định, giải phóng statement/connection sớm và quy định cách làm mới dữ liệu theo yêu cầu giao diện.

**Tình huống 7.** A dùng `REPEATABLE_READ` dựa trên snapshot và cursor scroll-sensitive, B commit một thay đổi. A không nhìn thấy thay đổi sau khi di chuyển con trỏ. Vì sao?

**Đáp án:** Isolation/snapshot của A có thể giới hạn những phiên bản dữ liệu được phép thấy; kiểu cursor không tự vượt qua isolation.

**Tình huống 8.** `rs.getType()` trả `TYPE_FORWARD_ONLY` dù ứng dụng đã yêu cầu scroll-sensitive. Có thể an toàn gọi `rs.last()` và `rs.previous()` không?

**Đáp án:** Không. Phải dựa vào loại thực tế, xử lý hạ cấp hoặc không hỗ trợ bằng cách dùng `next()` hay chọn chiến lược khác.

**Tình huống 9.** Tính năng `HOLD_CURSORS_OVER_COMMIT` có nghĩa cursor sẽ tự cập nhật giá khi người khác commit không?

**Đáp án:** Không. Holdability quyết định cursor có được giữ qua commit của connection hiện tại hay không; không thay thế sensitivity.

## Ghi nhớ

- **`TYPE_SCROLL_INSENSITIVE`** cho phép điều hướng tiến/lùi và không nhạy với thay đổi do giao dịch khác thực hiện khi `ResultSet` đang mở.
- **`TYPE_SCROLL_SENSITIVE`** cho phép điều hướng tương tự và có thể nhìn thấy thay đổi bên ngoài, nhưng phải kiểm tra **driver/DBMS, visibility và isolation**.
- **`TYPE_FORWARD_ONLY`** phục vụ đọc một chiều; không đảm bảo scroll hay một ngữ nghĩa sensitivity cố định.
- **Kiểm tra `DatabaseMetaData` trước khi dùng và `ResultSet.getType()` sau khi thực thi.** Phân biệt `supportsResultSetType`, `others...AreVisible` và `...AreDetected`.
- **Sensitivity, concurrency, holdability và isolation là bốn chiều riêng.** Đừng coi một cursor sensitive là công cụ bảo vệ transaction hoặc cho phép cập nhật hàng.
- **Nếu nghiệp vụ cần trạng thái mới có chủ đích, hãy thực thi lại SELECT trong transaction phù hợp**, kết hợp khóa phiên bản hoặc kiểm soát đồng thời khi ghi.
