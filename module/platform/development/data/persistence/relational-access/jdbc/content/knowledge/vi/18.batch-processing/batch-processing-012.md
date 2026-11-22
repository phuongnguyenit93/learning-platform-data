# Phân biệt batch JDBC và cơ chế nạp hàng loạt riêng của hệ quản trị

Ứng dụng Java thường cần ghi hàng trăm đến hàng triệu bản ghi vào cơ sở dữ liệu quan hệ. Trong **JDBC**, `PreparedStatement.addBatch()` kết hợp với `executeBatch()` là cách chuẩn để gom nhiều lệnh SQL và giảm chi phí trao đổi với cơ sở dữ liệu. Nhưng nhiều hệ quản trị còn có cơ chế **nạp hàng loạt** (*bulk loading*) riêng, chẳng hạn PostgreSQL `COPY`, MySQL `LOAD DATA`, SQL Server `BULK INSERT` hay Oracle SQL*Loader. Hai cách cùng xử lý nhiều dữ liệu, nhưng **đường thực thi, khả năng tương thích, định dạng đầu vào, cách báo lỗi và công cụ tối ưu hóa có thể khác nhau đáng kể**.

Bài thuộc chương **Xử lý theo lô** của module JDBC. Mục tiêu là chọn đúng công cụ cho thao tác CRUD, nhập dữ liệu, đồng bộ hệ thống, xử lý lỗi và tối ưu hiệu năng; đồng thời biết triển khai một phương án Java có thể bảo trì, dùng `DataSource`, SQL tham số hóa, `PreparedStatement`, transaction và kiểm tra kết quả.

## 1. Hai khái niệm cần tách bạch

### JDBC batch: nhiều lần thực thi câu SQL thông qua API chuẩn

Với `PreparedStatement`, bạn chuẩn bị **một mẫu SQL** có dấu `?`, gán nhiều bộ tham số, gọi `addBatch()` cho từng bộ rồi gửi lô bằng `executeBatch()`:

```java
String sql = "INSERT INTO catalog_items (id, name, unit_price) "
           + "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setString(2, "Bàn học");
    ps.setBigDecimal(3, new java.math.BigDecimal("450.00"));
    ps.addBatch();

    ps.setLong(1, 102L);
    ps.setString(2, "Ghế văn phòng");
    ps.setBigDecimal(3, new java.math.BigDecimal("720.00"));
    ps.addBatch();

    int[] counts = ps.executeBatch();
    // Mảng đếm tương ứng với thứ tự hai lần addBatch().
}
```

Đây vẫn là **thực thi SQL thông qua JDBC**. `executeBatch()` gom nhiều thao tác ở API, nhưng **không hứa hẹn** rằng DBMS nhìn thấy một câu `INSERT` duy nhất, một lần truyền mạng duy nhất hay một thuật toán tải dữ liệu đặc biệt. Driver có thể gửi nhiều lệnh dưới dạng gói, pipeline, hoặc **viết lại nhiều INSERT thành một INSERT nhiều VALUES** nếu hỗ trợ và được cấu hình; cơ chế cụ thể không được đảm bảo giống nhau giữa các driver.

JDBC batch dùng được cho nhiều tác vụ `INSERT`, `UPDATE` và `DELETE`, miễn loại câu lệnh/driver hỗ trợ batching. Không dùng nó để gom truy vấn trả về `ResultSet` như một phương pháp đọc nhiều kết quả độc lập; `executeBatch()` được thiết kế cho các lệnh cập nhật hoặc DDL thích hợp, và có thể ném `BatchUpdateException` nếu lệnh không hợp lệ cho batch.

### Bulk loading: đường nhập dữ liệu chuyên dụng của DBMS

Bulk loader thường cho DBMS nhận dữ liệu **theo luồng hoặc từ tệp** với một giao thức/cú pháp riêng để chèn lượng lớn hàng, thay vì yêu cầu ứng dụng Java thiết lập từng bộ tham số `PreparedStatement`.

Ví dụ về ý tưởng:

```text
JDBC batch:
  Các object Java → setXxx(?) → addBatch → executeBatch
  → JDBC driver → SQL engine → bảng đích

Bulk loading của DBMS:
  CSV / stream / tệp dữ liệu → loader hoặc giao thức chuyên dụng
  → bộ đọc và nạp hàng loạt của DBMS → bảng đích / staging
```

Bulk loader có thể tối ưu phần truyền và phân tích dữ liệu, và ở một số chế độ có thể tối ưu việc ghi vào bảng. **Không phải mọi bulk loader đều nhanh hơn mọi JDBC batch trong mọi trường hợp**: chỉ mục, trigger, ràng buộc, kích thước dữ liệu, giao dịch, cấu hình log và cơ sở dữ liệu quyết định kết quả thực tế.

## 2. Bảng so sánh theo những tiêu chí thường quyết định lựa chọn

| Tiêu chí | JDBC batch (`addBatch/executeBatch`) | Bulk loader riêng DBMS |
| --- | --- | --- |
| **API** | API JDBC chuẩn, lập trình với Java, `Connection` và `Statement`/`PreparedStatement`. | Lệnh SQL, giao thức driver, tiện ích CLI hoặc API vendor-specific. |
| **Nguồn dữ liệu** | Object Java và tham số SQL đã được chuẩn bị. | Thường là tệp CSV/text/binary hoặc một luồng dữ liệu. |
| **Tính di động** | Tương đối cao, nhưng hiệu năng và chi tiết batch phụ thuộc driver. | Thấp hơn: cú pháp, quyền, định dạng và cách điều khiển khác theo DBMS. |
| **Loại thao tác** | Phù hợp cho `INSERT`, `UPDATE`, `DELETE` có nhiều bộ tham số. | Thường tập trung **nạp/ghi nhiều hàng**, cần staging/merge cho cập nhật phức tạp. |
| **Kiểu dữ liệu** | `setLong`, `setBigDecimal`, `setTimestamp`, `setObject`... giao việc ánh xạ cho driver. | Phải định nghĩa quy tắc giải mã, phân cách cột, quote, `NULL`, số và ngày giờ. |
| **Kiểm soát từng bản ghi** | Ứng dụng biết thứ tự `addBatch`; `executeBatch` có mảng số đếm khi được hỗ trợ. | Chi tiết hàng lỗi phụ thuộc công cụ; có thể ghi log/reject file hoặc dừng toàn lô. |
| **Transaction** | Điều khiển bằng `setAutoCommit(false)`, `commit`, `rollback`. | Tùy DBMS và cách gọi: có công cụ chạy trong transaction, có chế độ commit riêng hoặc giới hạn rollback. |
| **Hiệu năng** | Giảm overhead so với một lần gửi SQL cho mỗi hàng; có thể tối ưu tiếp qua driver. | Có thể có lợi thế lớn khi nạp số lượng lớn từ nguồn phù hợp; cần benchmark đúng cấu hình. |
| **Khóa sinh** | Có `getGeneratedKeys()` nhưng hỗ trợ/ánh xạ khóa theo batch khác nhau giữa driver. | Thường cần cách đối chiếu khóa riêng nếu dữ liệu nguồn không có khóa nghiệp vụ. |
| **Triển khai/vận hành** | Không nhất thiết cần quyền nạp tệp hoặc tiện ích ngoài. | Có thể cần quyền DBMS, quyền đọc tệp trên server/client, cấu hình bảo mật và thư viện/công cụ riêng. |

Điều quan trọng là **batch JDBC và bulk loader không loại trừ nhau**. Một hệ thống có thể dùng batch cho ghi thường xuyên vài trăm hàng, còn nhập hàng triệu bản ghi định kỳ thì dùng loader vào bảng staging rồi chạy SQL để kiểm tra và hợp nhất dữ liệu.

## 3. Ví dụ các cơ chế bulk phổ biến

| Hệ quản trị | Cơ chế tiêu biểu | Lưu ý quan trọng |
| --- | --- | --- |
| **PostgreSQL** | `COPY FROM`, `COPY FROM STDIN`; driver PostgreSQL có Copy API riêng. | `COPY FROM STDIN` nhận dữ liệu từ client qua giao thức chuyên dụng; khác với `COPY FROM 'file'` đọc tệp trên máy chủ DB. |
| **MySQL** | `LOAD DATA INFILE`, `LOAD DATA LOCAL INFILE`. | `LOCAL` đọc tệp phía client và có yêu cầu/cấu hình bảo mật riêng; không được bật tùy tiện. |
| **Microsoft SQL Server** | `BULK INSERT`, tiện ích `bcp`, API bulk-copy của driver. | `BULK INSERT` thường làm việc với nguồn tệp mà máy chủ SQL Server truy cập được; API bulk-copy hỗ trợ truyền dữ liệu từ client. |
| **Oracle Database** | Tiện ích **SQL*Loader**, external tables, direct-path load tùy công cụ/chế độ. | Thường cần cấu hình tệp điều khiển, bảng, quyền, log lỗi và phương thức nạp riêng. |

Đây là **các ví dụ nhận diện công nghệ**, không phải danh sách mọi lựa chọn hay lời khẳng định chúng có cùng đặc tính. Ngay trong một DBMS, nhiều chế độ bulk khác nhau về khóa, trigger, constraint, transaction log, quyền truy cập và cách kiểm tra dữ liệu.

### Ví dụ SQL theo cú pháp PostgreSQL

```sql
COPY staging_items (import_id, item_id, name, unit_price)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

Lệnh này biểu thị luồng CSV được gửi từ **client** đến PostgreSQL bằng giao thức `COPY`; riêng đoạn SQL **không** có nghĩa là chỉ cần gọi `PreparedStatement.executeBatch()` hoặc `executeUpdate()` rồi truyền từng hàng CSV vào tham số `?`. Từ ứng dụng Java dùng PostgreSQL JDBC Driver, có thể sử dụng API `CopyManager`/`PGConnection.getCopyAPI()` của driver sau khi bổ sung phụ thuộc PostgreSQL tương ứng. Đây là **API riêng PostgreSQL**, không có phương thức `copyIn` tiêu chuẩn trên mọi `java.sql.Connection`.

Khi nguồn là **tệp trên máy chủ**, PostgreSQL có biến thể `COPY ... FROM '/đường-dẫn-trên-máy-chủ'`. Cần quyền truy cập file phía server và các đặc quyền của DBMS; đường dẫn tệp trên máy chạy ứng dụng Java không tự nhiên trở thành đường dẫn tệp trên server DB.

### Ví dụ minh họa với MySQL và SQL Server

```sql
-- MySQL: cú pháp minh họa; driver/server phải cho phép LOCAL.
LOAD DATA LOCAL INFILE '/duong-dan/phia-client/items.csv'
INTO TABLE staging_items
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(import_id, item_id, name, unit_price);
```

```sql
-- SQL Server: minh họa cơ chế đọc file phía server.
BULK INSERT dbo.staging_items
FROM 'C:\data\items.csv'
WITH (FORMAT = 'CSV', FIRSTROW = 2);
```

Các câu lệnh minh họa **không thể dùng thay thế cho nhau**. Bộ mã ký tự, dòng kết thúc, dấu quote, quyền file, thư mục và các tùy chọn parsing cần được hiệu chỉnh cho DBMS cụ thể. Không lấy giá trị đường dẫn tệp/SQL điều khiển loader từ đầu vào không tin cậy rồi nối chuỗi trực tiếp.

## 4. Ví dụ JDBC chuẩn: nạp theo từng batch có kiểm soát

Giả sử bảng đích như sau:

```sql
CREATE TABLE catalog_items (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Đoạn Java dưới đây minh họa cách xử lý một `List` sản phẩm bằng JDBC, **gửi từng batch 500 hàng nhưng chỉ `commit` một lần khi toàn bộ dữ liệu hợp lệ và được DBMS chấp nhận**. Mọi `INSERT` dùng tham số, đồng thời kiểm tra số đếm trước khi xác nhận.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class CatalogBatchImporter {
    private static final int BATCH_SIZE = 500;
    private final DataSource dataSource;

    public CatalogBatchImporter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void importAll(List<Item> items) throws SQLException {
        Objects.requireNonNull(items, "items");
        if (items.isEmpty()) {
            return;
        }

        // Kiểm tra dữ liệu độc lập với DB trước khi lấy Connection.
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.id <= 0 || item.name == null
                    || item.name.isBlank() || item.name.length() > 200
                    || item.price == null || item.price.signum() < 0) {
                throw new IllegalArgumentException("Item không hợp lệ");
            }
        }

        String sql = "INSERT INTO catalog_items (id, name, unit_price) "
                   + "VALUES (?, ?, ?)";

        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ tự sở hữu transaction, giả định pool trả autoCommit=true.
            if (!connection.getAutoCommit()) {
                throw new SQLException("Ví dụ cần Connection có autoCommit=true");
            }
            connection.setAutoCommit(false);
            boolean transactionFinished = false;
            Throwable primaryFailure = null;

            try {
                try (PreparedStatement ps = connection.prepareStatement(sql)) {
                    int pending = 0;
                    int firstIndex = 0;
                    for (Item item : items) {
                        ps.setLong(1, item.id);
                        ps.setString(2, item.name);
                        ps.setBigDecimal(3, item.price);
                        ps.addBatch();
                        pending++;

                        if (pending == BATCH_SIZE) {
                            verify(ps.executeBatch(), pending, firstIndex);
                            firstIndex += pending;
                            pending = 0;
                        }
                    }
                    if (pending > 0) {
                        verify(ps.executeBatch(), pending, firstIndex);
                    }
                }

                connection.commit();
                transactionFinished = true;
            } catch (SQLException | RuntimeException failure) {
                primaryFailure = failure;
                try {
                    connection.rollback();
                    transactionFinished = true;
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            } finally {
                if (transactionFinished) {
                    // Chỉ đổi autoCommit sau commit/rollback thành công.
                    try {
                        connection.setAutoCommit(true);
                    } catch (SQLException resetError) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(resetError);
                        } else {
                            throw resetError;
                        }
                    }
                }
                // Nếu trạng thái transaction chưa rõ, đóng Connection;
                // pool phải reset/loại connection hỏng theo cấu hình của nó.
            }
        }
    }

    private static void verify(int[] counts, int expected, int offset)
            throws SQLException {
        if (counts == null || counts.length != expected) {
            throw new SQLException("Thiếu số đếm của batch tại " + offset);
        }
        for (int i = 0; i < counts.length; i++) {
            int count = counts[i];
            if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                throw new SQLException(
                        "Batch vị trí " + (offset + i)
                        + " có kết quả không mong đợi: " + count);
            }
        }
    }

    public static final class Item {
        public final long id;
        public final String name;
        public final BigDecimal price;

        public Item(long id, String name, BigDecimal price) {
            this.id = id;
            this.name = name;
            this.price = price;
        }
    }
}
```

Trong ví dụ:

1. `DataSource` cung cấp `Connection`; `PreparedStatement` tái sử dụng mẫu `INSERT` với nhiều bộ tham số. `try-with-resources` đóng statement và trả kết nối khi xong.
2. Chương trình gửi `executeBatch()` mỗi 500 hàng để không tích lũy vô hạn dữ liệu batch trong bộ nhớ. Con số **500 chỉ là điểm khởi đầu thử nghiệm**, không phải giá trị tối ưu chung.
3. `verify` kiểm tra đúng thứ tự mảng số đếm. `Statement.SUCCESS_NO_INFO` (`-2`) nghĩa là driver báo thực thi thành công nhưng không biết số hàng; ví dụ chấp nhận nó cho một `INSERT` một hàng theo bộ tham số. Nếu nghiệp vụ **bắt buộc chứng minh chính xác một hàng được chèn** bằng số đếm, phải từ chối `SUCCESS_NO_INFO` hoặc xác minh bằng phép kiểm tra riêng sau đó.
4. Nếu `executeBatch()` ném `BatchUpdateException` (lớp con của `SQLException`), nhánh `catch` sẽ rollback và truyền lỗi lên. Có thể bắt riêng `BatchUpdateException` ở tầng báo lỗi để đọc `getUpdateCounts()` và `getNextException()`.
5. Nếu có lỗi dữ liệu sau ba batch thành công, **cả ba batch trước vẫn có thể được rollback** vì tất cả nằm trong một transaction chưa `commit`. Việc chia kích thước batch **không tự chia transaction**.

**Giới hạn của ví dụ:** tập dữ liệu là `List` đã có trong bộ nhớ, nên chỉ có kích thước batch được khống chế, không phải bộ nhớ dành cho toàn bộ nguồn dữ liệu. Khi nhập tệp lớn, nên **đọc theo luồng** và chuyển từng hàng thành bộ tham số, hoặc dùng cơ chế bulk loader. Ngoài ra, kiểu cột `DECIMAL(18, 2)` có độ chính xác/giới hạn riêng; ứng dụng thật cần kiểm tra giá và quy tắc làm tròn trước khi ghi.

Nếu `commit()` ném lỗi do kết nối bị mất, có thể **không biết kết quả commit đã xảy ra chưa**. `rollback()` tiếp theo không tự chứng minh dữ liệu chắc chắn chưa được ghi. Khi nhập có khả năng retry, nên có khóa nghiệp vụ/idempotency và bước kiểm tra dữ liệu đã tồn tại.

## 5. Nạp bulk vào staging rồi hợp nhất dữ liệu

Với nhập dữ liệu lớn và có yêu cầu kiểm soát chất lượng, **nạp thẳng vào bảng nghiệp vụ cuối cùng** đôi khi quá rủi ro: một hàng sai định dạng, một ID trùng hoặc một bản ghi không hợp lệ có thể làm gián đoạn quá trình mà khó giải thích cho người vận hành.

Một luồng dễ kiểm soát hơn:

```mermaid
flowchart LR
    A[Tệp hoặc stream nguồn] --> B[Bulk loader riêng DBMS]
    B --> C[Bảng staging theo import_id]
    C --> D[Kiểm tra kiểu dữ liệu, khóa trùng, quy tắc nghiệp vụ]
    D --> E{Dữ liệu đạt yêu cầu?}
    E -->|Có| F[INSERT SELECT hoặc MERGE/UPSERT]
    E -->|Không| G[Ghi bảng lỗi và xử lý lại]
    F --> H[Xác nhận và đối soát kết quả]
```

Ví dụ cấu trúc staging tối giản, nếu dữ liệu đã được parse đúng kiểu:

```sql
CREATE TABLE staging_items (
    import_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL
);
```

Sau khi loader đã ghi dữ liệu, có thể đối soát bằng các truy vấn:

```sql
-- Số dòng được nạp cho một lần import.
SELECT COUNT(*) FROM staging_items WHERE import_id = ?;

-- Tìm ID sản phẩm bị lặp trong cùng lần import.
SELECT item_id, COUNT(*) AS occurrences
FROM staging_items
WHERE import_id = ?
GROUP BY item_id
HAVING COUNT(*) > 1;

-- Tìm giá trị vi phạm điều kiện nghiệp vụ.
SELECT COUNT(*) FROM staging_items
WHERE import_id = ? AND unit_price < 0;
```

Cuối cùng, có thể chuyển dữ liệu sang bảng chính bằng một câu `INSERT ... SELECT`:

```sql
INSERT INTO catalog_items (id, name, unit_price)
SELECT item_id, name, unit_price
FROM staging_items
WHERE import_id = ?;
```

Đoạn `INSERT ... SELECT` chỉ áp dụng khi đã **kiểm tra tính hợp lệ, không trùng khóa chính và không xung đột với bảng đích**. Khi cần cập nhật bản ghi đã tồn tại, sử dụng `MERGE`/UPSERT theo **cú pháp DBMS thực tế**, với hợp đồng rõ ràng cho trường hợp trùng khóa và kiểm soát đồng thời. Không mặc định tất cả DBMS có cùng cú pháp `ON CONFLICT` hay `ON DUPLICATE KEY UPDATE`.

Để hỗ trợ retry, nên gắn `import_id` duy nhất cho một lần xử lý logic và dùng ràng buộc/khóa phù hợp để tránh nạp trùng. Cần phân biệt **nạp xong staging** với **hợp nhất xong bảng chính**; hệ thống nên ghi trạng thái nhập liệu và số bản ghi đã đối soát trước khi thông báo thành công.

**Staging chứa dữ liệu thô hay dữ liệu đã parse?** Nếu file có thể sai kiểu số/ngày, nạp thẳng các trường vào `DECIMAL` hoặc `TIMESTAMP` có thể làm loader lỗi trước khi bạn ghi nhận được từng dòng không hợp lệ. Khi cần cách ly dữ liệu lỗi chi tiết, có thể dùng staging với cột dạng chuỗi, kiểm tra/chuyển kiểu ở bước kế tiếp (với hàm/cú pháp theo từng DBMS), rồi chỉ chuyển bản ghi hợp lệ sang bảng đích.

## 6. Transaction và lỗi có cùng ngữ nghĩa hay không?

**Không.** Batching chỉ nói về cách gửi/thực thi nhiều lệnh; bulk loading nói về một cơ chế nạp dữ liệu. **Tính nguyên tử và rollback phụ thuộc transaction và khả năng của công cụ/DBMS**.

| Tình huống | Điều cần hiểu |
| --- | --- |
| `executeBatch()` trên kết nối `autoCommit=true` | Không nên giả định các lệnh trong batch là một transaction nguyên tử; có driver/DBMS đã xác nhận một phần trước khi lỗi. |
| `executeBatch()` trong transaction do Java mở | Nếu DBMS hỗ trợ transaction cho thao tác và transaction chưa commit, có thể `rollback` toàn bộ công việc thuộc transaction đó. |
| Bulk loader chạy qua kết nối và transaction DBMS | Có thể có tính nguyên tử theo transaction, nhưng phải kiểm tra cú pháp/chế độ thực tế và cách driver tham gia transaction. |
| Tiện ích bulk chạy độc lập từ CLI | Có thể tự quản lý kết nối, kích thước commit, reject file và checkpoint; transaction JDBC của một kết nối Java khác **không bao bọc** được nó. |
| Chế độ nạp có commit theo lô hoặc bỏ qua hàng lỗi | Có khả năng có thành công một phần; cần quy trình đối soát, phục hồi và retry riêng. |

### Lỗi JDBC batch: số đếm không phải trạng thái commit

Khi `executeBatch()` thất bại, JDBC có thể ném `BatchUpdateException`. `getUpdateCounts()` phản ánh các lệnh đã được driver báo cáo theo thứ tự `addBatch()`:

```java
try {
    int[] counts = statement.executeBatch();
} catch (java.sql.BatchUpdateException failure) {
    int[] counts = failure.getUpdateCounts();
    // Driver có thể dừng ở lệnh lỗi hoặc tiếp tục sau lỗi.
    // Statement.SUCCESS_NO_INFO (-2): thành công, không rõ số hàng.
    // Statement.EXECUTE_FAILED (-3): lệnh thất bại.
    throw failure;
}
```

Với driver dừng ở lỗi đầu tiên, mảng có thể ngắn hơn số lệnh đã thêm. Với driver tiếp tục sau lỗi, mảng có thể có phần tử cho toàn bộ lô và đánh dấu `Statement.EXECUTE_FAILED` tại vị trí thất bại. Không dựa vào `counts.length` để suy diễn toàn bộ hàng đã commit hay chưa; phải xem transaction và tình trạng kết nối.

### Lỗi bulk loader: khả năng phát hiện hàng lỗi tùy công cụ

Bulk loader có thể dừng toàn bộ file, chấp nhận một số hàng trước lỗi, bỏ qua hàng lỗi theo giới hạn, hoặc ghi reject file riêng. Các khả năng này **không có chuẩn chung tương đương `BatchUpdateException.getUpdateCounts()`** trên mọi DBMS. Cần đọc trạng thái loader, báo cáo số hàng đã chấp nhận, số hàng bị từ chối, log, và kiểm tra bảng đích/staging sau lần nạp.

Nếu cần **all-or-nothing**, hãy chọn cơ chế và transaction thật sự hỗ trợ, kiểm tra lỗi trong transaction rồi `commit` khi toàn bộ dữ liệu đạt yêu cầu. Nếu dữ liệu quá lớn để giữ một transaction, có thể chia thành những import nhỏ với checkpoint và khả năng chạy lại an toàn; đây là thay đổi **ngữ nghĩa giao dịch**, không chỉ tối ưu hiệu năng.

## 7. Định dạng, quyền truy cập và bảo mật khi dùng bulk

Nhiều lỗi bulk không đến từ tốc độ mà từ **cách hiểu dữ liệu nguồn**:

- **CSV không đơn giản là `split(",")`:** giá trị có dấu phẩy trong dấu quote, dấu xuống dòng bên trong trường, dấu quote được escape và header đều cần parser đúng quy tắc.
- **`NULL` khác chuỗi rỗng:** DBMS có thể xem chuỗi rỗng, token `NULL` và trường bị thiếu theo các cách khác nhau; phải cấu hình rõ.
- **Mã hóa ký tự:** chọn UTF-8 hay encoding đúng của nguồn; lưu ý dấu tiếng Việt, BOM, ký tự điều khiển, quy tắc cuối dòng.
- **Số và thời gian:** dấu thập phân, precision, timezone và định dạng ngày phải thống nhất; không giả định locale của Java và DB giống nhau.
- **Schema thay đổi:** thứ tự cột, cột mặc định, khóa sinh, ràng buộc `NOT NULL`, `CHECK` và unique key ảnh hưởng kết quả nạp.
- **Quyền đọc file:** server-side loader cần quyền phù hợp trên máy DB; client-side loader cần quyền phía ứng dụng/driver và có thể tăng bề mặt rủi ro bảo mật.

**Không bật tùy chọn client-file loading nếu ứng dụng không cần.** Với MySQL `LOAD DATA LOCAL INFILE`, tùy cấu hình server/driver, cơ chế cho phép client gửi nội dung file và cần được kiểm soát chặt quyền, nguồn lệnh và phiên bản driver. Khi dùng đường dẫn file hoặc SQL đặc thù, chỉ sử dụng đường dẫn và lệnh từ cấu hình đã được kiểm soát; không nối giá trị không đáng tin cậy vào câu lệnh điều khiển bulk.

Tránh đưa dữ liệu nhạy cảm vào log lỗi bulk, file reject hoặc bản sao staging mà không có kiểm soát truy cập và thời hạn lưu trữ. Cơ chế bulk có thể tạo thêm file tạm/log; cần đưa chúng vào quy trình vận hành và dọn dẹp.

## 8. Hiệu năng: đừng chỉ nhìn số hàng/giây của riêng câu lệnh

**Tốc độ thực tế** chịu ảnh hưởng của nhiều yếu tố:

1. **Chi phí truyền:** latency giữa ứng dụng và DBMS, số lần gọi lệnh, định dạng tham số, tốc độ đọc tệp hoặc gửi stream.
2. **Chi phí ghi:** transaction log/WAL, chỉ mục, trigger, constraint, khóa và I/O của DBMS.
3. **Chi phí chuyển đổi:** parse CSV, chuyển sang kiểu SQL, chuẩn hóa ngày giờ, kiểm tra dữ liệu.
4. **Kích thước batch/transaction:** batch nhỏ quá gây overhead; lớn quá dùng nhiều bộ nhớ, giữ khóa lâu hoặc làm transaction log tăng mạnh.
5. **Cách xử lý lỗi:** báo lỗi từng bản ghi, rollback toàn bộ hay lọc dữ liệu trước khi nạp sẽ có chi phí khác nhau.
6. **Sự đồng thời:** nhiều luồng nạp cùng lúc có thể cạnh tranh pool, bảng/khóa, CPU và I/O.

Hai phép đo khác nhau có thể dẫn đến kết luận sai:

| Cách đo | Điểm thiếu |
| --- | --- |
| Đo riêng thời gian gọi `executeBatch()` | Bỏ chi phí đọc/chuẩn bị object, validation, commit và xử lý lỗi. |
| Đo riêng tốc độ `COPY`/`LOAD DATA` | Bỏ chi phí tạo CSV, truyền file, kiểm tra staging, merge, rebuild index hay xác nhận kết quả. |

Khi benchmark, hãy chạy trên cùng tập dữ liệu, cùng schema/chỉ mục/trigger, cùng cấu hình transaction và cùng độ bền dữ liệu. Ghi nhận tổng thời gian **từ lúc nhận nguồn đến khi dữ liệu hợp lệ đã được commit và đối soát**, số hàng thực sự được chấp nhận, độ trễ p95/p99 nếu có, CPU, RAM, I/O, số lần retry và thời gian chờ khóa. Sau mỗi thử nghiệm phải đưa DB về trạng thái có thể so sánh để tránh tác động của cache, dữ liệu trùng và kích thước bảng tăng.

Driver JDBC có thể có tùy chọn **viết lại batch INSERT** thành câu SQL lớn hơn; chỉ bật/cấu hình khi đã đối chiếu tài liệu driver và xác minh điều kiện tương thích, hành vi generated keys, SQL nhiều tham số và số đếm. **Đừng xem “JDBC batch” mặc nhiên là một đường thực thi chậm**: với bảng nhỏ hoặc vài nghìn thay đổi có điều kiện, nó thường đơn giản và đủ nhanh.

## 9. Chọn giải pháp cho từng bài toán

| Bài toán | Gợi ý ban đầu | Lý do |
| --- | --- | --- |
| API thường xuyên ghi vài chục đến vài nghìn hàng, mỗi hàng là object Java | `PreparedStatement` + `addBatch`/`executeBatch`. | Đơn giản, tham số hóa, giữ logic Java và tương đối di động. |
| Đồng loạt cập nhật trạng thái/giá theo ID khác nhau | JDBC batch hoặc SQL cập nhật tập hợp theo DBMS. | Bulk importer hướng INSERT có thể không phù hợp; cần bảo vệ điều kiện cập nhật. |
| Nhập CSV rất lớn vào một DBMS cố định | Thử bulk loader vào staging, sau đó validate/merge. | Có thể giảm overhead parse/truyền SQL và tận dụng khả năng nạp của DBMS. |
| Dự án phải chạy trên nhiều DBMS | Bắt đầu với JDBC batch chuẩn; tùy chọn adapter bulk cho DBMS cụ thể. | Hạn chế phụ thuộc công nghệ riêng và giữ đường dự phòng. |
| Dữ liệu lỗi nhiều, cần báo cáo từng hàng | Staging + bước kiểm tra/ghi nhận lỗi có cấu trúc. | Loader/driver không nhất thiết cho lỗi chi tiết giống nhau. |
| Cần transaction nhiều bảng và quy tắc nghiệp vụ phức tạp | JDBC transaction với SQL phù hợp hoặc staged merge cùng transaction. | Yêu cầu nhất quán quyết định ranh giới transaction. |
| Cần xử lý file cực lớn nhưng bộ nhớ Java giới hạn | Stream từng dòng để batch hoặc bulk streaming API. | Tránh dựng toàn bộ danh sách object trong RAM. |

Không đặt ngưỡng cố định như “trên 10.000 hàng luôn phải dùng COPY”: tùy loại hàng, DBMS, driver, vị trí dữ liệu và chi phí validation, điểm hòa vốn sẽ khác nhau. Nên bắt đầu từ **yêu cầu tính đúng đắn và vận hành**, sau đó đo để chọn giải pháp.

### Kết hợp hai cơ chế trong cùng hệ thống

Một thiết kế thực tế có thể tách thành hai đường xử lý:

```text
Thao tác người dùng / service Java:
  validate → PreparedStatement.addBatch → executeBatch → commit

Nhập file định kỳ:
  stream/file → bulk load vào staging → kiểm tra
  → hợp nhất bằng SQL trong transaction phù hợp → đối soát → hoàn tất
```

Điểm chung quan trọng hơn tên công cụ: xác định **đơn vị công việc nào phải thành công cùng nhau**, thiết lập khóa/idempotency để tránh nạp trùng, đo chính xác số hàng thực tế và kết thúc transaction theo đúng hợp đồng của DBMS.

## 10. Bài thực hành: chọn giữa JDBC batch và bulk load

Một hệ thống quản lý kho có ba yêu cầu:

1. Mỗi khi người dùng bấm “Cập nhật”, service nhận 200 thay đổi số lượng khác nhau. Mỗi lần cập nhật phải kiểm tra `available >= ?` và cập nhật đúng một hàng.
2. Mỗi đêm hệ thống nhận file CSV 3 triệu sản phẩm từ nhà cung cấp. File có thể có ID trùng, giá âm và một số dòng sai kiểu dữ liệu. Hệ thống dùng PostgreSQL.
3. Một dịch vụ mới phải hỗ trợ đồng thời PostgreSQL và SQL Server; lượng ghi thường chỉ khoảng 500 bản ghi mỗi lần nhưng không được mất dữ liệu khi thất bại ở giữa.

Hãy xác định:

- Dùng công cụ gì cho mỗi yêu cầu và vì sao?
- Với yêu cầu 1, `executeBatch()` trả các số đếm `{1, 1, 0, 1}` thì có thể `commit` không nếu cả 4 cập nhật phải thành công?
- Với yêu cầu 2, nên bulk-load trực tiếp bảng sản phẩm cuối cùng hay staging? Có nên dùng cột text ở staging khi cần ghi nhận lỗi parse?
- Với yêu cầu 3, muốn tất cả 500 dòng thành công hoặc không dòng nào được lưu, cần đặt `autoCommit` và `commit`/`rollback` như thế nào?

**Đáp án định hướng:** (1) JDBC batch với SQL cập nhật có điều kiện; phải kiểm tra số đếm, `0` không thỏa quy tắc nên rollback toàn giao dịch. (2) Thử PostgreSQL `COPY FROM STDIN` vào staging, kiểm tra dòng trùng/giá âm/parse trước khi chuyển sang bảng chính; nếu dữ liệu sai kiểu, staging text và bước chuyển đổi có kiểm soát giúp báo lỗi từng dòng. (3) Dùng JDBC batch chuẩn trên hai DBMS, `setAutoCommit(false)` trước lệnh đầu, chỉ `commit` khi mọi batch đạt điều kiện, còn thất bại thì `rollback`; kiểm thử hành vi driver khi `BatchUpdateException`.

**Ghi nhớ:** **JDBC batch** là cách chuẩn của Java để gửi nhiều lệnh SQL qua `Statement`/`PreparedStatement`, còn **bulk loader** là đường nạp dữ liệu đặc thù của DBMS, thường tối ưu cho khối lượng lớn từ file/stream. Batch không tự bảo đảm một transaction, còn bulk loader không tự bảo đảm mọi hàng đều hợp lệ hay có thể rollback như nhau. Chọn giải pháp dựa trên dữ liệu nguồn, loại CRUD, tính di động, yêu cầu transaction, xử lý lỗi và benchmark **đầu đến cuối**, rồi mới quyết định tối ưu theo DBMS.
