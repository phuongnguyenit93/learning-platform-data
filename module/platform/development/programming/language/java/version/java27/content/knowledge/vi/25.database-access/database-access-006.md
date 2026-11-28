# Batch, fetch size và tối ưu số lượt truy cập

Khi làm việc với cơ sở dữ liệu quan hệ bằng Java 27, độ trễ không chỉ nằm ở việc SQL thực thi nhanh hay chậm. Một ứng dụng còn tốn thời gian ở **số lượt gửi yêu cầu tới database**, **số dòng truyền về**, **số bản ghi giữ trong bộ nhớ**, **thời gian giữ transaction/connection** và **cách driver JDBC xử lý câu lệnh**.

Ba kỹ thuật cần phân biệt rõ:

1. **JDBC batch**: tập hợp nhiều thao tác ghi, thường là `INSERT`, `UPDATE` hoặc `DELETE`, rồi gửi để thực hiện theo nhóm bằng `addBatch` và `executeBatch`.
2. **Fetch size**: gợi ý số dòng JDBC driver nên lấy từ database mỗi lần cần thêm dữ liệu cho một `ResultSet`; đây là **hint**, không phải giới hạn số dòng truy vấn.
3. **Giảm số lượt truy cập**: thay mẫu N+1 bằng truy vấn theo tập hợp, dùng SQL có điều kiện và phân trang phù hợp, tái sử dụng `PreparedStatement`, kiểm soát quy mô mỗi lượt giao tiếp.

Bài thuộc chương **Truy cập cơ sở dữ liệu** của module **Java 27 và các kiến thức liên quan**. Nội dung bám API `java.sql` và `javax.sql` hiện hành trong Java SE 27; không dựa vào cú pháp JDBC cũ đã bị thay thế. Các đặc tính truyền dữ liệu thực tế phải được kiểm chứng bằng **phiên bản JDBC driver + hệ quản trị cơ sở dữ liệu (DBMS)** mà ứng dụng dùng.

**Nguyên tắc quan trọng:** batch và fetch size là hai cơ chế khác nhau. Batch thường dùng để tối ưu **ghi nhiều lệnh**, còn fetch size dùng để điều chỉnh **đọc nhiều dòng từ một ResultSet**. Không cơ chế nào tự giải quyết một câu SQL viết chưa tốt hoặc N+1 queries.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt một câu SQL, một JDBC execution, một network round trip và một transaction.
- Dùng `PreparedStatement.addBatch()`, `executeBatch()`, `executeLargeBatch()` đúng cách.
- Thiết kế batch theo từng phần (*chunk*) để kiểm soát bộ nhớ, giới hạn driver và kích thước transaction.
- Đọc và giải thích update counts, `Statement.SUCCESS_NO_INFO`, `Statement.EXECUTE_FAILED`, `BatchUpdateException`.
- Kết hợp batch với `setAutoCommit(false)`, `commit()` và `rollback()` khi cần tính nguyên tử.
- Sử dụng `Statement.setFetchSize` và `ResultSet.setFetchSize` như gợi ý tối ưu việc lấy dòng.
- Giải thích vì sao `fetchSize` khác `setMaxRows`, phân trang SQL và giới hạn dữ liệu đưa vào heap.
- Nhận diện truy vấn N+1 và chuyển sang `JOIN`, truy vấn theo tập hợp hoặc batch-fetch hợp lý.
- Đánh giá chi phí số lần gọi DB, số bản ghi, độ trễ, transaction duration, heap và tài nguyên connection pool.
- Tránh SQL injection bằng tham số `?`, quản lý vòng đời JDBC bằng `try`-with-resources và biết điểm nào phụ thuộc driver.

## 2. Nhìn đúng vào chi phí truy cập database

### 2.1. Các đơn vị thường bị đánh đồng

| Khái niệm | Ý nghĩa | Điều cần nhớ |
|---|---|---|
| SQL statement | Một câu lệnh SQL logic | Một câu lệnh có thể đọc/ghi nhiều dòng |
| JDBC execution | Một lần gọi `executeQuery`, `executeUpdate`, `executeBatch`... | Không phải lúc nào tương đương một network round trip |
| Network round trip | Một lượt trao đổi request/response trên mạng | Phụ thuộc protocol, driver, batching, fetch/cursor |
| Row | Một bản ghi trong kết quả hoặc đối tượng DML tác động | Nhiều row có thể được xử lý trong một SQL statement |
| Transaction | Phạm vi thay đổi có `commit`/`rollback` | Không đồng nhất với số batch |
| Connection | Phiên giao tiếp với database | Thường được quản lý bằng connection pool |
| Fetch size | Hint về số dòng lấy khi cần thêm dòng | Không phải tổng số dòng query trả về |
| Batch size | Số mục tích lũy trước `executeBatch` | Không phải số bản ghi tối đa của bảng |

Vì driver có thể gộp hoặc chuyển đổi các câu lệnh, không nên viết rằng **1000 lệnh trong một batch chắc chắn chỉ tốn đúng một network round trip**. Một batch giúp giảm overhead trong nhiều cấu hình nhưng số request thực tế phải đo bằng metrics hoặc trace của driver/DB.

### 2.2. Mô hình đơn giản để nhìn độ trễ

Nếu một request cơ sở dữ liệu cần `L` đơn vị thời gian round trip, và ứng dụng phải đợi tuần tự `N` lượt, phần latency mạng có thể xấp xỉ:

~~~text
Chi phí latency tuần tự ≈ N × L
~~~

Khi gom thao tác thành `K` nhóm và driver thực sự giảm giao tiếp mạng, latency có thể giảm đáng kể. Tuy nhiên tổng thời gian còn bao gồm parse, planning, chạy SQL, ghi log transaction, lock, index maintenance và thời gian truyền dữ liệu.

Đây chỉ là mô hình để tư duy, **không phải công thức benchmark JDBC**. Cùng một batch size có thể đạt hiệu năng khác nhau giữa PostgreSQL, MySQL, Oracle Database, SQL Server hoặc các driver/phiên bản khác nhau.

### 2.3. Hai hướng tối ưu bổ trợ nhau

~~~mermaid
flowchart TD
    A[Chậm khi truy cập database] --> B{Đang ghi nhiều bản ghi?}
    B -->|Có| C[PreparedStatement batch và transaction]
    B -->|Không| D{Đang đọc nhiều kết quả?}
    D -->|Có| E[Fetch size, đọc theo dòng, phân trang SQL]
    D -->|Không| F{Có quá nhiều truy vấn nhỏ?}
    F -->|Có| G[Xử lý N+1, JOIN, truy vấn theo tập hợp]
    F -->|Không| H[Đo SQL plan, index, lock, connection pool]
~~~

Trong thực tế một tính năng có thể gặp đồng thời cả ba vấn đề: truy vấn N+1 khi đọc, lưu từng row bằng lệnh ghi riêng lẻ, rồi tải toàn bộ kết quả vào RAM. Mỗi vấn đề cần công cụ đúng.

## 3. JDBC batch là gì?

### 3.1. Thực hiện từng UPDATE độc lập

~~~java
String sql = "UPDATE orders SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (StatusChange change : changes) {
        ps.setString(1, change.status());
        ps.setLong(2, change.orderId());
        ps.executeUpdate(); // Thực thi riêng từng lần.
    }
}
~~~

Đoạn này giả định `connection`, `changes` và kiểu `StatusChange` được khai báo ở phạm vi tương ứng. Dùng `PreparedStatement` đã tránh việc tạo chuỗi SQL không an toàn, nhưng vẫn thực thi từng lần trong vòng lặp.

Khi có hàng nghìn phần tử, overhead lời gọi DB hoặc round trips có thể lớn. Batch cho phép gửi các bộ tham số theo nhóm.

### 3.2. Đưa nhiều bộ tham số vào cùng PreparedStatement

~~~java
String sql = "UPDATE orders SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (StatusChange change : changes) {
        ps.setString(1, change.status());
        ps.setLong(2, change.orderId());
        ps.addBatch(); // Ghi nhận bộ tham số hiện tại.
    }

    int[] counts = ps.executeBatch();
}
~~~

Trong ví dụ:

1. SQL có cấu trúc cố định và hai placeholder `?`.
2. `setString(1, ...)` và `setLong(2, ...)` gắn giá trị cho bộ tham số hiện tại.
3. `addBatch()` thêm bộ tham số đó vào danh sách batch.
4. `executeBatch()` yêu cầu driver thực hiện các mục trong danh sách.
5. `counts` mô tả kết quả thành công của từng mục theo thứ tự đã thêm, khi không có lỗi batch.

`addBatch()` **không có đối số** là phương thức dành cho `PreparedStatement`. Phương thức `Statement.addBatch(String sql)` là dạng khác cho danh sách SQL text; không dùng `addBatch(String)` trên `PreparedStatement`.

### 3.3. So sánh PreparedStatement và Statement

| API | Cách thêm batch | Dùng khi nào |
|---|---|---|
| `Statement` | `statement.addBatch("UPDATE ...")` | Có thể dùng cho các SQL text cố định, không chứa dữ liệu không tin cậy |
| `PreparedStatement` | `ps.setXxx(...); ps.addBatch();` | Ưu tiên cho một mẫu SQL lặp lại với nhiều bộ tham số |
| `PreparedStatement.executeBatch()` | Thực thi danh sách đã tích lũy | Nhận `int[]` update counts |
| `PreparedStatement.executeLargeBatch()` | Thực thi batch và nhận `long[]` | Hữu ích khi count có thể vượt miền `int` |

`PreparedStatement` giúp tách **cấu trúc câu SQL** với **giá trị dữ liệu**, hỗ trợ an toàn trước SQL injection ở vị trí giá trị bind và có thể cho phép DB/driver tái sử dụng tài nguyên chuẩn bị câu lệnh. Việc driver hay server cache execution plan đến mức nào phụ thuộc cấu hình.

### 3.4. Batch không thích hợp với SELECT trả ResultSet

Theo JDBC, batch update nhằm xử lý những lệnh SQL có update count hoặc không trả result set. Nếu một lệnh trong batch cố trả `ResultSet`, driver có thể ném `BatchUpdateException`.

Để đọc nhiều dòng, hãy thực hiện **một SELECT phù hợp**, mở `ResultSet`, chọn fetch size và xử lý từng dòng hoặc phân trang. Không xếp hàng loạt `SELECT` bằng `Statement.addBatch` rồi mong nhận nhiều `ResultSet` như một batch query thông thường.

## 4. Batch theo chunk thay vì tích lũy vô hạn

### 4.1. Vì sao cần chia nhỏ?

Nếu nạp vài triệu bộ tham số vào một `PreparedStatement` trước khi gọi `executeBatch`, driver có thể giữ lượng dữ liệu rất lớn trong heap hoặc bộ đệm bản địa. Batch quá lớn cũng có thể:

- Gây pressure bộ nhớ hoặc giới hạn request/packet của driver/DBMS.
- Tạo transaction giữ lock quá lâu nếu toàn bộ nghiệp vụ chờ commit.
- Làm chi phí rollback cao khi một mục cuối bị lỗi.
- Khiến chẩn đoán lỗi và retry phức tạp.
- Gặp giới hạn số bind parameters, kích thước SQL hoặc log của hệ thống.

Chia thành `chunk`, ví dụ bắt đầu khảo sát với 100–1000 mục/batch, là **gợi ý benchmark** chứ không phải thông số tối ưu chung. Batch size phải dựa vào kích thước mỗi row, driver, SQL, latency, DBMS và giới hạn bộ nhớ.

### 4.2. Mẫu thực hiện batch theo chunk

~~~java
static int updateInChunks(Connection connection,
                          List<StatusChange> changes,
                          int batchSize) throws SQLException {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    String sql = "UPDATE orders SET status = ? WHERE order_id = ?";
    int submitted = 0;
    int pending = 0;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (StatusChange change : changes) {
            ps.setString(1, change.status());
            ps.setLong(2, change.orderId());
            ps.addBatch();

            submitted++;
            pending++;

            if (pending == batchSize) {
                int[] counts = ps.executeBatch();
                inspectCounts(counts);
                ps.clearBatch();
                pending = 0;
            }
        }

        if (pending > 0) {
            int[] counts = ps.executeBatch();
            inspectCounts(counts);
            ps.clearBatch();
        }
    }
    return submitted;
}
~~~

Đoạn mã là **trích phần logic**: `StatusChange`, `inspectCounts` và import nằm trong ví dụ hoàn chỉnh ở mục 13. `clearBatch()` ở đây nói rõ ý định bắt đầu nhóm mới; sau khi execute thành công, các driver tuân theo contract hiện hành phải xử lý danh sách batch phù hợp.

**Quan trọng:** hoàn tất mỗi chunk không nhất thiết có nghĩa chunk đó đã commit. Việc commit phụ thuộc chế độ transaction của `Connection`. Không tự trộn ý nghĩa “batch size” với “transaction size”.

### 4.3. Cần tránh nhóm cuối bị bỏ sót

Mã chỉ gọi `executeBatch()` khi đếm đủ `batchSize` sẽ bỏ quên các phần tử cuối nếu `N` không chia hết cho `batchSize`.

~~~text
N = 205 mục, batchSize = 100
batch #1: 100
batch #2: 100
batch #3:   5  ← vẫn cần executeBatch
~~~

Nếu danh sách rỗng, không cần gửi một batch không có lệnh.

### 4.4. Giới hạn batch không đồng nghĩa giới hạn transaction

Một transaction có thể gồm nhiều batch. Ví dụ 20 chunk × 500 mục = 10.000 thao tác được commit cuối cùng như một đơn vị nghiệp vụ, nếu DBMS/driver hỗ trợ transaction và mọi thao tác nằm trong cùng một transaction.

Ngược lại, nếu thiết kế ứng dụng cho phép commit từng 500 mục, mỗi chunk trở thành một **đơn vị durability riêng**. Các mục đã commit trước đó không còn được rollback chỉ bằng một lần `rollback()` ở transaction sau.

Chọn transaction boundary theo tính đúng đắn của nghiệp vụ, không chỉ theo mục tiêu throughput.

## 5. Đọc update counts đúng cách

### 5.1. Thành phần của mảng trả về

Khi `executeBatch()` hoàn tất thành công, `int[]` được trả về có các phần tử theo thứ tự lệnh đã `addBatch`.

Mỗi phần tử có thể là:

| Giá trị | Ý nghĩa |
|---|---|
| `0` | Lệnh thực thi thành công, không có row nào bị tác động |
| Số nguyên dương | Số row được báo cáo bị tác động |
| `Statement.SUCCESS_NO_INFO` | Lệnh thành công nhưng driver không biết/không công bố số row |
| `Statement.EXECUTE_FAILED` | Một mục thất bại; thường thấy trong `BatchUpdateException` nếu driver tiếp tục sau lỗi |

Không được cộng `SUCCESS_NO_INFO` như một số âm vào tổng row count. Nó là **mã trạng thái**, không phải lượng row bị ảnh hưởng.

### 5.2. Ví dụ kiểm tra counts

~~~java
static void inspectCounts(int[] counts) throws SQLException {
    for (int count : counts) {
        if (count == Statement.SUCCESS_NO_INFO) {
            continue; // Thành công nhưng không biết số row.
        }
        if (count == Statement.EXECUTE_FAILED) {
            throw new SQLException("A batch command failed");
        }
        if (count < 0) {
            throw new SQLException("Unexpected update count: " + count);
        }

        // count >= 0: số hàng do driver báo cáo.
    }
}
~~~

Nếu nghiệp vụ đòi hỏi **mỗi UPDATE phải sửa chính xác một row**, `SUCCESS_NO_INFO` không cung cấp đủ bằng chứng để xác nhận yêu cầu đó. Khi đó cần chiến lược kiểm tra khác (ví dụ nghiệp vụ khóa định danh, câu SQL có điều kiện và truy vấn/đối soát phù hợp), không được mặc nhiên coi `SUCCESS_NO_INFO == 1`.

Một lệnh `UPDATE` ảnh hưởng 0 dòng không tự động là lỗi JDBC; có thể do không tồn tại `order_id` hoặc điều kiện WHERE không khớp. Đây là quyết định của contract nghiệp vụ.

### 5.3. executeLargeBatch và getLargeUpdateCounts

~~~java
long[] counts = ps.executeLargeBatch();
~~~

`executeLargeBatch()` dùng `long[]` để biểu diễn update count có thể lớn. Nếu gặp `BatchUpdateException` sau `executeLargeBatch`, sử dụng `getLargeUpdateCounts()` sẽ tránh hạn chế số nguyên 32-bit.

Không phải cứ có nhiều **mục trong batch** thì mỗi update count sẽ vượt `int`; lý do lựa chọn `long[]` là khi **một lệnh có thể ảnh hưởng số lượng row lớn** hoặc cần hợp đồng đếm rộng hơn.

## 6. BatchUpdateException: một mục lỗi có thể ảnh hưởng cả nhóm

### 6.1. JDBC driver có thể dừng hoặc tiếp tục

Khi một mục batch thất bại, `executeBatch` ném `BatchUpdateException`. Theo contract:

- Driver có thể **dừng tại lệnh đầu thất bại**. Mảng `getUpdateCounts()` khi đó chứa counts của các mục đã thực thi thành công trước lỗi.
- Driver cũng có thể **tiếp tục thực thi các mục còn lại**. Khi đó mảng chứa một phần tử cho mỗi mục được gửi, trong đó mục lỗi được đánh dấu bằng `Statement.EXECUTE_FAILED`.

Cách driver chọn xử lý phải nhất quán cho DBMS cụ thể theo hợp đồng JDBC, nhưng ứng dụng không được giả định “lỗi một dòng thì mọi dòng sau không chạy”.

### 6.2. Ví dụ đọc thông tin lỗi

~~~java
try {
    ps.executeBatch();
} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    System.err.println("Batch failed; reported entries: "
            + counts.length);
    System.err.println("SQLState: " + e.getSQLState());

    for (int i = 0; i < counts.length; i++) {
        if (counts[i] == Statement.EXECUTE_FAILED) {
            System.err.println("Failed batch index: " + i);
        }
    }

    throw e;
}
~~~

Đây là ví dụ chẩn đoán đặt trong nơi có `ps`. Chỉ có `getUpdateCounts` **không đủ** để tự xác định trạng thái commit/rollback của toàn bộ đơn vị nghiệp vụ.

Với lỗi mạng trong lúc commit, client thậm chí có thể **không biết chắc** database đã commit hay chưa. Không thể dùng mảng count thay thế chính sách đối soát giao dịch, idempotency key hoặc uniqueness constraint.

### 6.3. Không retry mù toàn bộ batch

Nếu batch lỗi sau khi một số mục đã được DB xử lý, retry toàn bộ danh sách khi chưa xác định transaction outcome có thể làm tạo dữ liệu trùng hoặc lặp side effect.

Thiết kế retry nên xét:

1. Lỗi có tạm thời hay vĩnh viễn (SQLState, vendor error, lỗi constraint)?
2. Có transaction bao quanh và rollback đã hoàn tất chắc chắn không?
3. Các thao tác có **idempotent** không?
4. Có khóa duy nhất/idempotency key để ngăn ghi trùng không?
5. Database có cơ chế upsert/merge phù hợp không và semantics của nó đã được kiểm tra chưa?

Không dùng một quy tắc chung kiểu “bất kỳ `SQLException` nào cũng retry ba lần”.

## 7. Transaction, auto-commit và rollback

### 7.1. Auto-commit mặc định

Theo `java.sql.Connection`, connection mới thông thường ở chế độ auto-commit: mỗi statement được commit khi hoàn tất theo semantics JDBC.

~~~java
boolean autoCommit = connection.getAutoCommit();
~~~

Một chương trình yêu cầu **toàn bộ batch nhiều chunk phải nguyên tử** cần chủ động quản lý transaction:

~~~java
connection.setAutoCommit(false);
try {
    updateInChunks(connection, changes, 500);
    connection.commit();
} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
}
~~~

Đoạn này giả định `connection` là connection mà method **sở hữu transaction**, không bị shared với request khác. Thực tế nên đặt nó trong `try`-with-resources hoặc quản lý vòng đời bằng connection pool/framework theo hợp đồng.

### 7.2. Cần xác định ranh giới sở hữu transaction

Có hai thiết kế phổ biến:

- **Tầng service sở hữu transaction:** lấy connection, đặt `autoCommit=false`, gọi DAO thực hiện nhiều chunk, commit hoặc rollback một lần.
- **Framework sở hữu transaction:** DAO nhận connection/transaction context đã được quản lý, chỉ thực thi JDBC và **không tự commit/rollback** ngoài hợp đồng.

Không nên để một helper nội bộ vừa `commit()` vừa bị một transaction manager bên ngoài điều khiển; điều đó có thể phá tính nguyên tử của nghiệp vụ.

Nếu dùng pooled connection, cần đảm bảo trạng thái `autoCommit`, isolation, read-only và các cấu hình driver được trả về trạng thái mà pool mong đợi. Đổi `autoCommit` giữa một transaction đang hoạt động có thể **commit transaction đó** theo contract; không dùng `setAutoCommit(true)` như “cách đơn giản để dọn dẹp” khi rollback trước đó thất bại.

### 7.3. Đóng connection chưa thay commit/rollback

`Connection.close()` giải phóng tài nguyên, nhưng nếu connection còn transaction đang hoạt động, kết quả có thể phụ thuộc implementation. Cách an toàn là **commit hoặc rollback rõ ràng** trước khi đóng.

Ví dụ lỗi:

~~~java
connection.setAutoCommit(false);
ps.executeBatch();
// Không commit, không rollback rồi giả định close luôn rollback.
~~~

Mặt khác, transaction quá dài có thể giữ lock, phiên bản row hoặc log lâu. Không bao trùm việc chờ mạng/nhập liệu hoặc xử lý CPU kéo dài trong cùng transaction chỉ để giảm số lần commit nếu không cần tính nguyên tử xuyên suốt.

### 7.4. Khi không hỗ trợ transaction

Một số nguồn dữ liệu hoặc câu lệnh có semantics riêng, không giống các thao tác DML thông thường; DDL có thể có quy tắc commit đặc biệt theo DBMS. Nếu định thiết kế atomic multi-batch, hãy xác minh DBMS/driver hỗ trợ transaction và chế độ giao dịch bằng `DatabaseMetaData.supportsTransactions()`, tài liệu vendor và bài kiểm thử integration.

## 8. Fetch size là gì và không phải là gì?

### 8.1. Hint của JDBC driver

`Statement.setFetchSize(int rows)` gợi ý cho driver số dòng nên lấy từ database khi `ResultSet` cần thêm dữ liệu.

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, status FROM orders ORDER BY order_id")) {

    ps.setFetchSize(256);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            String status = rs.getString("status");
            process(orderId, status);
        }
    }
}
~~~

Ví dụ trên là mẫu cấu trúc: `connection` và `process` được cung cấp trong ứng dụng. Ý nghĩa của `setFetchSize(256)` là **gợi ý kích thước mỗi lần nạp**, không phải “chỉ trả về 256 row”.

### 8.2. Các quy tắc API cụ thể

- `rows` phải **không âm**; giá trị âm có thể gây `SQLException`.
- `0` có nghĩa **không áp đặt hint**, cho phép driver tự quyết định.
- Giá trị mặc định của `Statement` khi chưa được thiết lập và cách driver thực thi hint phụ thuộc implementation.
- `ResultSet.setFetchSize(int)` cũng tồn tại; mặc định của `ResultSet` được kế thừa từ `Statement` tạo ra nó.
- Có thể thay đổi fetch size của `ResultSet` trong quá trình đọc theo contract, nhưng driver có thể không thể hiện khác biệt rõ ràng.

Chỉ dựa vào `ps.getFetchSize() == 256` không chứng minh driver đã thực sự tạo cursor và chỉ nạp 256 row mỗi lần.

### 8.3. Không bảo đảm streaming ở mọi driver

Một số JDBC driver có thể preload nhiều hoặc toàn bộ kết quả ngay khi thực thi query; driver khác dùng server-side cursor hoặc prefetch. Một số cấu hình yêu cầu result set forward-only, transaction mode hoặc property riêng của JDBC URL mới stream hiệu quả.

Vì vậy:

**`setFetchSize(256)` không phải bảo đảm cứng rằng heap chỉ chứa tối đa 256 row.**

Nếu cần xử lý tập kết quả rất lớn, phải kiểm thử với **driver, DBMS, phiên bản, connection properties và transaction settings cụ thể**. Không sao chép một cấu hình fetch size từ hệ quản trị khác rồi khẳng định nó luôn có cùng hiệu quả.

### 8.4. Fetch size và số lượt nhận dữ liệu

Giả sử có `R = 10.000` row và driver **thực sự** thực hiện mỗi lượt fetch khoảng `F = 250` row. Một ước lượng thô là khoảng `ceil(R/F) = 40` nhóm lấy dữ liệu, chưa tính metadata, query startup và protocol.

Mô hình này **chỉ hợp lệ khi driver thực hiện kiểu batched fetching ấy**. Nếu driver đọc tất cả từ đầu, số network round trips có thể khác; nếu row kích thước lớn, byte transfer và heap mới là nút thắt chính.

Không sử dụng `ceil(R/F)` như kết quả đo JDBC thực tế.

## 9. Fetch size khác giới hạn số dòng và phân trang

### 9.1. Bảng so sánh quan trọng

| Công cụ | Tác động chính | Điều không bảo đảm |
|---|---|---|
| `setFetchSize(256)` | Gợi ý lượng dòng được driver lấy mỗi lần | Tổng số dòng query trả về, giới hạn heap cứng |
| `setMaxRows(500)` | Giới hạn số dòng tối đa mà JDBC `ResultSet` chứa theo contract | DBMS nhất định sẽ chỉ quét/đọc 500 dòng |
| `SELECT ... FETCH FIRST 500 ROWS ONLY` hoặc `LIMIT` | Giới hạn ở cấp SQL/DBMS nếu cú pháp được hỗ trợ | Query plan tốt nếu thiếu index/sort phù hợp |
| `WHERE order_id > ? ORDER BY order_id` | Chọn vùng dữ liệu theo khóa cho keyset pagination | Không tự đảm bảo tính nhất quán dưới thay đổi đồng thời |
| `while (rs.next())` và xử lý từng dòng | Giảm số object ứng dụng lưu giữ | Driver không buffer toàn bộ ResultSet |
| `setQueryTimeout(...)` | Yêu cầu giới hạn thời gian thực thi theo hợp đồng driver | Deadline end-to-end tuyệt đối cho toàn bộ nghiệp vụ |

### 9.2. Ví dụ giới hạn ở cấp JDBC

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, status FROM orders ORDER BY order_id")) {

    ps.setMaxRows(100);
    ps.setFetchSize(25);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Có tối đa 100 dòng xuất hiện trong ResultSet.
        }
    }
}
~~~

`setMaxRows(100)` là giới hạn số dòng của ResultSet. Nó không thay cho việc tối ưu câu SQL để DB lọc dữ liệu ngay từ đầu. Với truy vấn production, thông thường nên đưa giới hạn vào SQL theo cú pháp DBMS, kết hợp `WHERE` và `ORDER BY` phù hợp.

### 9.3. Keyset pagination cho các trang lớn

Ví dụ theo cú pháp SQL hỗ trợ `FETCH FIRST`:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id > ?
ORDER BY order_id
FETCH FIRST 200 ROWS ONLY
~~~

Bind `?` bằng ID cuối trang trước. Cách này thường ổn định chi phí hơn việc dùng `OFFSET` rất lớn khi có index thích hợp trên `order_id`.

Điều kiện áp dụng:

- `order_id` là khóa/ordering key ổn định, đủ phân biệt thứ tự.
- Có index phục vụ predicate và order.
- Nếu dữ liệu được thêm/xóa/sửa đồng thời, cần định nghĩa semantics trang và isolation/snapshot phù hợp.
- Cú pháp `FETCH FIRST`, `LIMIT`, `OFFSET` và kiểu bind trong giới hạn phụ thuộc DBMS.

**Fetch size và pagination có thể dùng cùng nhau**: pagination giảm tổng dữ liệu của một request; fetch size gợi ý cách driver truyền các dòng của request đó.

## 10. Đọc ResultSet đúng cách để không tạo áp lực heap

### 10.1. Xử lý từng row

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, status FROM orders")) {

    ps.setFetchSize(200);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong(1);
            String status = rs.getString(2);
            handleRow(id, status);
        }
    }
}
~~~

Nếu `handleRow` xử lý xong một row rồi giải phóng tham chiếu, ứng dụng không giữ một `List` lớn chứa mọi kết quả. Tuy nhiên driver vẫn có thể buffer; đây mới là **giảm bộ nhớ phía application layer**, không phải bảo đảm streaming end-to-end.

### 10.2. Không collect toàn bộ chỉ để xuất file hoặc tính thống kê

~~~java
List<Order> all = new ArrayList<>();

while (rs.next()) {
    all.add(new Order(rs.getLong(1), rs.getString(2)));
}
~~~

Nếu query trả hàng triệu row, list sẽ phát triển theo kích thước tập dữ liệu. Nếu chỉ cần ghi file, tính aggregate hoặc đẩy message ra downstream, xử lý theo dòng/chunk thay vì giữ toàn bộ.

Nếu mục tiêu chỉ là đếm số row, thường nên để database xử lý:

~~~sql
SELECT COUNT(*) FROM orders WHERE status = ?
~~~

thay vì truyền mọi row về Java rồi tăng biến đếm. Nếu cần biến đổi mỗi row ở ứng dụng, hãy cân nhắc chi phí/độ an toàn của từng lựa chọn.

### 10.3. Đóng ResultSet, PreparedStatement và Connection

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        // Xử lý từng dòng.
    }
}
~~~

`Connection`, `PreparedStatement` và `ResultSet` đều implement `AutoCloseable`. `try`-with-resources đóng tài nguyên theo thứ tự ngược lại thứ tự khởi tạo.

Trong ví dụ này `dataSource` và `sql` là giá trị được khai báo từ trước, và `sql` không có placeholder chưa được bind. Trong phương thức nhận connection do framework truyền vào, **không được tự đóng connection** nếu caller sở hữu vòng đời của nó.

Giữ ResultSet và connection mở quá lâu trong khi gọi service ngoài hoặc thực hiện xử lý nặng có thể cạn pool, giữ transaction/lock và làm tăng tail latency.

## 11. N+1 queries: nguyên nhân lớn hơn cả fetch size

### 11.1. Một query lấy danh sách, N query lấy chi tiết

~~~java
List<Order> orders = loadOrders();

for (Order order : orders) {
    List<OrderItem> items = loadItems(order.id());
    // ...
}
~~~

Ví dụ trên mang tính cấu trúc. Nếu `loadOrders` chạy một SQL và `loadItems` chạy một SQL cho mỗi order, chương trình có **1 + N câu truy vấn**, ngay cả khi từng SQL rất nhanh.

Với N = 500, ứng dụng có thể gửi 501 lần thực thi query. Tăng fetch size của query đầu **không** sửa được 500 query chi tiết.

### 11.2. Giải pháp theo tập hợp: JOIN

~~~sql
SELECT o.order_id, o.status,
       i.item_id, i.product_code
FROM orders o
LEFT JOIN order_items i ON i.order_id = o.order_id
WHERE o.order_id BETWEEN ? AND ?
ORDER BY o.order_id, i.item_id
~~~

Một truy vấn kết hợp có thể thay hàng trăm lần gọi riêng. Tuy nhiên `JOIN` cũng có trade-off:

- Quan hệ một–nhiều có thể làm lặp lại các cột của order trên nhiều dòng kết quả.
- Nhiều quan hệ một–nhiều trong cùng JOIN có thể tạo bội số dòng lớn.
- Cần index, predicate và query plan phù hợp.
- Phải kiểm tra việc xử lý các order không có item.

Không có quy tắc “JOIN mọi bảng trong một SELECT luôn tốt nhất”.

### 11.3. Giải pháp hai pha: query danh sách và query chi tiết theo IN

~~~sql
-- Query 1: lấy danh sách order đã lọc/phân trang.
SELECT order_id, status
FROM orders
WHERE status = ?
ORDER BY order_id

-- Query 2: lấy items cho tập order ID ở trang hiện tại.
SELECT order_id, item_id, product_code
FROM order_items
WHERE order_id IN (?, ?, ?, ?)
~~~

Cách này có thể giữ số query gần mức cố định theo số chunk, thay vì một query trên mỗi order. Nếu IN-list quá dài, hãy chia nhóm theo giới hạn driver/DB hoặc dùng cơ chế bảng tạm/array parameter/TVP phù hợp DBMS.

Đừng ghép ID người dùng thành chuỗi SQL bằng concatenation; hãy tạo **số lượng placeholder** được kiểm soát và bind từng giá trị.

### 11.4. Ví dụ xây IN-clause có tham số

~~~java
static Map<Long, String> loadStatuses(Connection connection,
                                     List<Long> ids)
        throws SQLException {

    if (ids.isEmpty()) {
        return Map.of();
    }

    String placeholders =
            String.join(", ", Collections.nCopies(ids.size(), "?"));

    String sql = "SELECT order_id, status FROM orders "
            + "WHERE order_id IN (" + placeholders + ")";

    Map<Long, String> result = new HashMap<>();

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            ps.setLong(i + 1, ids.get(i));
        }

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                result.put(rs.getLong(1), rs.getString(2));
            }
        }
    }
    return result;
}
~~~

Đây là method minh họa, giả định các import `java.sql.*` và `java.util.*` thích hợp. Với danh sách cực lớn, cách này cần được bọc trong một chính sách chia chunk; không tạo hàng chục nghìn `?` mà không xét giới hạn database.

Trường hợp `ids` rỗng được xử lý trước để tránh SQL `IN ()` không hợp lệ trên nhiều DBMS. Không bảo đảm thứ tự trong `Map` trùng với thứ tự đầu vào; nếu cần thứ tự ổn định, hãy tái sắp xếp ở tầng ứng dụng.

### 11.5. Batch select và batch update khác nhau

Một số ORM dùng cụm “batch fetching” để chỉ việc lấy liên kết nhiều entity qua một câu `IN` hoặc chiến lược riêng. Điều này **không tương đương** `PreparedStatement.addBatch()` cho DML.

| Bài toán | Kỹ thuật |
|---|---|
| Cập nhật 500 bản ghi | PreparedStatement batch |
| Đọc 500 bản ghi theo một cursor | Fetch size/ResultSet |
| Đọc 500 chi tiết theo 500 ID | JOIN/IN theo tập hợp, tránh N+1 |
| Chỉ cần 20 bản ghi trên một trang | SQL pagination/limit |
| Đếm các bản ghi | SQL aggregate như `COUNT(*)` |
| Chỉ cần một vài cột | Projection rõ ràng, tránh `SELECT *` khi không cần |

## 12. Thứ tự ưu tiên khi tối ưu số lượt truy cập

### 12.1. Trước hết giảm lượng công việc không cần thiết

Tối ưu thường có hiệu quả khi đi từ mức cao xuống thấp:

1. **Chọn đúng dữ liệu:** projection chỉ các cột cần thiết, predicate sớm, tránh tải BLOB/CLOB không dùng.
2. **Giảm N+1:** query theo tập hợp và tránh round trips lặp.
3. **Chọn truy vấn/plan:** index, execution plan, thống kê DB và join order.
4. **Batch các phép ghi:** tái sử dụng SQL template, kiểm soát batch size.
5. **Điều chỉnh fetch size:** đo latency/memory/driver behavior khi xử lý nhiều row.
6. **Điều chỉnh transaction và pool:** tránh transaction dài và connection bị giữ khi không cần.
7. **Đo lại trong điều kiện thực:** không chọn tham số dựa trên benchmark mô phỏng khác workload.

Tăng fetch size từ 100 lên 1000 không sửa được một câu query cần full-table scan không mong muốn hoặc một vòng lặp N+1.

### 12.2. Query plan và index

Nếu `WHERE status = ? ORDER BY order_id` trả hàng triệu bản ghi, việc tối ưu index phụ thuộc tỷ lệ chọn lọc, dữ liệu, database engine và workload cập nhật. Cần xem `EXPLAIN`/query plan của DBMS thay vì tự thêm index một cách máy móc.

Đọc query plan cũng giúp biết liệu DB đang sort nhiều row, scan toàn bảng hoặc join không hiệu quả. Một JDBC round trip ít hơn không bảo đảm database CPU và I/O ít hơn.

### 12.3. Tránh SELECT *

~~~sql
SELECT order_id, status, amount
FROM orders
WHERE status = ?
~~~

Khi chỉ cần ba trường, đừng mặc định đọc cả những cột lớn như text/blob hoặc payload JSON. Kích thước từng row ảnh hưởng chi phí mạng và bộ đệm; cùng fetch size 1000 có thể rất nhẹ với vài integer nhưng rất nặng với nhiều trường văn bản lớn.

## 13. Ví dụ Java hoàn chỉnh: batch UPDATE + đọc ResultSet

Ví dụ `JdbcBatchFetchDemo.java` được thiết kế để **biên dịch chỉ với API Java SE**, còn lúc **chạy** cần JDBC driver và một database thật. Không phụ thuộc framework hoặc tính năng Java Preview.

Giả định database có bảng:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);
~~~

DDL trên là ví dụ mô tả lược đồ, cần điều chỉnh theo DBMS thực tế nếu cú pháp/kiểu dữ liệu khác. Để minh họa, các `order_id` 101 và 102 có thể đã tồn tại; nếu chưa có, `UPDATE` tác động 0 row nhưng bản thân câu SQL vẫn có thể được thực thi thành công.

### 13.1. Mã nguồn

~~~java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public final class JdbcBatchFetchDemo {

    record StatusChange(long orderId, String status) {
        StatusChange {
            Objects.requireNonNull(status, "status");
        }
    }

    record OrderView(long orderId, String status) {}

    static int updateInChunks(Connection connection,
                              List<StatusChange> changes,
                              int batchSize) throws SQLException {

        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be > 0");
        }
        Objects.requireNonNull(changes, "changes");

        if (connection.getAutoCommit()) {
            throw new IllegalStateException(
                    "Caller must own a manual transaction");
        }
        if (!connection.getMetaData().supportsBatchUpdates()) {
            throw new SQLException("JDBC driver does not support batches");
        }

        String sql = "UPDATE orders SET status = ? WHERE order_id = ?";
        int pending = 0;
        int submitted = 0;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setQueryTimeout(30); // Hint/semantics depend on driver.

            for (StatusChange change : changes) {
                ps.setString(1, change.status());
                ps.setLong(2, change.orderId());
                ps.addBatch();

                submitted++;
                pending++;

                if (pending == batchSize) {
                    inspectCounts(ps.executeBatch(), pending);
                    ps.clearBatch();
                    pending = 0;
                }
            }

            if (pending > 0) {
                inspectCounts(ps.executeBatch(), pending);
                ps.clearBatch();
            }
        }

        // Số bộ tham số đã gửi, không phải tổng row bị tác động.
        return submitted;
    }

    private static void inspectCounts(int[] counts, int expected)
            throws SQLException {

        if (counts.length != expected) {
            throw new SQLException(
                    "Unexpected batch update count length: "
                            + counts.length);
        }

        for (int count : counts) {
            if (count == Statement.SUCCESS_NO_INFO) {
                continue;
            }
            if (count == Statement.EXECUTE_FAILED) {
                throw new SQLException("A batch command failed");
            }
            if (count < 0) {
                throw new SQLException("Unexpected count: " + count);
            }
        }
    }

    static int readOrders(Connection connection,
                          int fetchSize,
                          int maxRows,
                          Consumer<OrderView> visitor)
            throws SQLException {

        if (fetchSize <= 0 || maxRows <= 0) {
            throw new IllegalArgumentException(
                    "fetchSize and maxRows must be > 0");
        }
        Objects.requireNonNull(visitor, "visitor");

        String sql = "SELECT order_id, status "
                + "FROM orders ORDER BY order_id";

        try (PreparedStatement ps = connection.prepareStatement(
                sql,
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.CONCUR_READ_ONLY)) {

            ps.setFetchSize(fetchSize); // Driver hint.
            ps.setMaxRows(maxRows);     // JDBC ResultSet row limit.

            try (ResultSet rs = ps.executeQuery()) {
                int seen = 0;

                while (rs.next()) {
                    OrderView row = new OrderView(
                            rs.getLong(1),
                            rs.getString(2));
                    visitor.accept(row);
                    seen++;
                }

                return seen;
            }
        }
    }

    public static void main(String[] args) throws SQLException {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java JdbcBatchFetchDemo <jdbc-url>");
            return;
        }

        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user == null || password == null) {
            System.err.println(
                    "Set JDBC_USER and JDBC_PASSWORD environment variables");
            return;
        }

        String url = args[0];

        // GHI: transaction độc lập, commit/rollback tường minh.
        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {

            connection.setAutoCommit(false);
            try {
                int submitted = updateInChunks(
                        connection,
                        List.of(
                                new StatusChange(101, "READY"),
                                new StatusChange(102, "READY")),
                        100);

                connection.commit();
                System.out.println("Submitted updates: " + submitted);
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }

        // ĐỌC: connection riêng, resource tự đóng.
        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {

            int seen = readOrders(
                    connection,
                    5, 10,
                    row -> System.out.println(
                            row.orderId() + " -> " + row.status()));

            System.out.println("Rows returned: " + seen);
        }
    }
}
~~~

### 13.2. Biên dịch và chạy

~~~bash
javac JdbcBatchFetchDemo.java
~~~

Để chạy, cần cung cấp JDBC driver tương ứng với DBMS trên runtime classpath/module path, tạo bảng `orders` và cấu hình biến môi trường:

~~~text
JDBC_USER=<database-user>
JDBC_PASSWORD=<database-password>
~~~

Sau đó chạy (thay phần JDBC URL bằng URL của hệ quản trị đang dùng):

~~~bash
java -cp "<driver-jar>:." JdbcBatchFetchDemo "<jdbc-url>"
~~~

Lệnh classpath trên dùng dấu `:` theo Unix; trên Windows thường dùng dấu `;`, hoặc cấu hình run classpath qua IDE/build tool. Ví dụ không đưa một URL, user hay mật khẩu cụ thể vì môi trường kết nối khác nhau. **Không nên lưu mật khẩu thật trong tài liệu, source code hoặc shell history.** Biến môi trường có ích cho demo nhưng với hệ thống production nên tích hợp cơ chế quản lý bí mật thích hợp.

### 13.3. Điều gì được bảo đảm và không được bảo đảm?

- `PreparedStatement` giữ mẫu SQL cố định với giá trị bind, không nối dữ liệu trực tiếp vào SQL text.
- Các thao tác ghi dùng **một transaction** với `setAutoCommit(false)` và chỉ `commit` sau khi toàn bộ logic ghi thành công.
- Khi có lỗi JDBC/runtime trong khối ghi, code cố rollback và giữ lỗi rollback như suppressed nếu rollback cũng thất bại.
- `readOrders` xử lý từng row, không tạo list lớn ở Java.
- `setFetchSize(5)` là hint; `setMaxRows(10)` đặt giới hạn row ở ResultSet.
- Code **không bảo đảm** số network round trips, heap của driver, hiệu năng trên mọi DBMS hoặc cách server xử lý prefetch.
- `submitted` là số bộ tham số nộp vào batch, **không phải số row đã thực sự thay đổi**.
- Nếu mất kết nối vào đúng lúc commit, cần kiểm tra trạng thái transaction bằng chính sách ứng dụng; rollback attempt không luôn chứng minh kết quả cuối.
- Việc `setQueryTimeout(30)` tác động lên toàn batch hay từng lệnh có thể phụ thuộc JDBC driver; không được coi nó là deadline end-to-end.

### 13.4. Thiết kế giao dịch khi dùng connection pool

Trong hệ thống production, thay `DriverManager` đơn giản bằng `DataSource`/connection pool có cấu hình rõ ràng. Nên để service hoặc transaction manager sở hữu việc commit/rollback, còn DAO chỉ thực hiện `PreparedStatement`.

Ví dụ method nhận connection:

~~~java
static void saveWithExistingTransaction(Connection connection,
                                        List<StatusChange> changes)
        throws SQLException {

    // Caller sở hữu connection và transaction.
    updateInChunks(connection, changes, 500);

    // KHÔNG commit ở đây; caller quyết định.
}
~~~

Không trộn ví dụ “method nhận connection” với việc method tự đóng hoặc commit connection mà caller đang dùng cho nhiều thao tác nghiệp vụ.

## 14. Tối ưu batch size và fetch size bằng đo đạc

### 14.1. Chiến lược thử nghiệm

Một benchmark có ý nghĩa cần giữ ổn định:

- Cùng version JDK, JDBC driver, DBMS, schema và index.
- Cùng kích thước payload mỗi row, tỷ lệ insert/update, transaction isolation.
- Cùng số lượng connection, concurrency, hardware và điều kiện mạng.
- Warm-up phù hợp cho ứng dụng và database, tránh đo lần đầu tạo connection như latency chung.
- Cùng chính sách commit/rollback và dữ liệu đủ lớn để phản ánh workload.
- Theo dõi throughput, p50/p95/p99 latency, CPU/IO của DB, heap/GC của Java, lock wait và pool wait.

Ví dụ các batch sizes **chỉ để thử nghiệm**, không phải khuyến nghị cố định:

~~~text
Batch size: 1, 32, 128, 512, 1000
Fetch size: driver default (0), 32, 128, 512
~~~

Một driver có thể tăng tốc khi batch size từ 1 lên 128, nhưng giảm hiệu quả khi lên 1000 vì packet, lock contention hoặc bộ nhớ. Đánh giá bằng kết quả đo trên workload thật.

### 14.2. KPI nên quan sát

| Chỉ số | Nói lên điều gì |
|---|---|
| JDBC executions / request | Một nghiệp vụ đang gửi bao nhiêu lệnh |
| DB round trips / request | Số lượt trao đổi mạng, nếu driver/DB cho phép đo |
| Rows read / rows returned | SQL quét nhiều row không cần thiết không |
| Rows affected / batch | Hiệu quả và trạng thái các update |
| Batch throughput (rows/s) | Năng suất ghi tổng thể |
| p95/p99 latency | Trải nghiệm ở những request chậm |
| Heap/GC | Driver/application có giữ quá nhiều dữ liệu không |
| Connection-pool wait | Có giữ connection quá lâu không |
| Transaction duration / lock wait | Batch/đọc có làm tăng tranh chấp không |
| DB CPU, disk IO, network bytes | Nút thắt thực nằm ở DB hay phía ứng dụng |

Chỉ tối ưu một chỉ số dễ gây đánh đổi không mong muốn. Batch throughput cao nhưng lock wait lớn có thể làm các request online chậm hơn.

### 14.3. Driver configuration là một phần của thí nghiệm

Một số driver hỗ trợ chuyển batch thành multi-row insert, server-side prepared statements hoặc server-side cursor thông qua các cấu hình vendor. Các lựa chọn này **không phải chuẩn chung của `java.sql`**, và có thể tác động đến generated keys, thông báo update counts hoặc giao dịch.

Hãy kiểm tra tài liệu **đúng phiên bản driver** trước khi bật các tùy chọn vendor; không giả định property của một driver áp dụng cho driver khác.

## 15. Các sai lầm thường gặp

| Sai lầm | Rủi ro | Cách cải thiện |
|---|---|---|
| Vòng lặp `executeUpdate()` cho hàng nghìn record | Nhiều overhead gọi DB | Cân nhắc `PreparedStatement.addBatch()` và `executeBatch()` |
| Giữ toàn bộ hàng triệu bộ tham số trước khi execute | Áp lực bộ nhớ, batch/transaction lớn | Chia chunk và đo giới hạn |
| Chỉ execute batch đủ `B` phần tử | Bỏ mất chunk cuối | Gửi phần còn lại sau vòng lặp |
| Nhầm batch size với transaction size | Commit không đúng ranh giới nghiệp vụ | Tách rõ batch và commit |
| Giả định batch = một network round trip | Đánh giá hiệu năng sai | Kiểm tra driver và đo round trips |
| Cộng cả `SUCCESS_NO_INFO` vào tổng row count | Tổng số row sai | Xử lý như mã trạng thái thành công |
| Coi update count 0 là luôn thất bại | Không đúng với mọi nghiệp vụ | Định nghĩa contract cho UPDATE 0 dòng |
| Retry toàn bộ batch sau `BatchUpdateException` | Trùng dữ liệu/side effect | Idempotency, rollback, xác minh outcome |
| Chỉ đóng connection, không commit/rollback | Kết quả transaction phụ thuộc implementation | Commit hoặc rollback tường minh |
| Đổi `setAutoCommit(true)` sau lỗi để “dọn dẹp” | Có thể commit một transaction chưa xử lý | Xử lý transaction state đúng cách |
| Cho rằng `setFetchSize(100)` trả 100 dòng | Sai semantics | Dùng SQL pagination hoặc `setMaxRows` cho giới hạn |
| Cho rằng fetch size bảo đảm driver streaming | Có thể preload tất cả | Kiểm tra cấu hình driver và đo heap |
| Query N+1 nhưng chỉ tăng fetch size | N+1 không được sửa | JOIN/batch fetch/truy vấn theo tập |
| Ghép ID người dùng vào `IN (...)` bằng chuỗi | SQL injection, khó cache SQL | Tạo placeholders và bind |
| `SELECT *` trên row nhiều cột lớn | Tăng network, buffer, GC | Projection chỉ các cột cần |
| Đếm record bằng tải hết về Java | Giao tiếp và heap không cần thiết | `COUNT(*)` hoặc aggregate SQL |
| Giữ transaction khi gọi service ngoài | Lock và pool bị giữ lâu | Tối thiểu hóa transaction scope |
| Mặc định batch size càng lớn càng tốt | Nút thắt chuyển sang DB locks/heap | Benchmark các kích thước hợp lý |
| Bỏ qua khả năng `supportsBatchUpdates()` | Lỗi khác nhau giữa drivers | Kiểm tra DatabaseMetaData và test integration |
| Dùng `setQueryTimeout` như deadline tuyệt đối | Cách áp dụng tùy driver | Giới hạn ở các tầng app/driver/DB thích hợp |

## 16. Checklist thiết kế truy cập database hiệu quả

Trước khi đưa chức năng vào production:

1. **Đếm số SQL executions** cho một request, tìm N+1 và những thao tác lặp có thể gom.
2. **Chọn đúng phạm vi dữ liệu:** chỉ những row/column cần thiết; có predicate và index phù hợp.
3. **Phân biệt READ và WRITE:** SELECT cần fetch size/pagination; DML lặp có thể cần batch.
4. **Tái sử dụng PreparedStatement** trong cùng phạm vi hợp lý và bind các giá trị qua `?`.
5. **Chia batch thành chunk** có kích thước đo đạc được và nhớ xử lý chunk cuối.
6. **Đọc update counts** đúng, kể cả `SUCCESS_NO_INFO` và các nhánh `BatchUpdateException`.
7. **Chọn transaction boundary** theo nguyên tử nghiệp vụ; commit/rollback rõ ràng.
8. **Không retry không kiểm soát:** định nghĩa idempotency và cách xác minh trạng thái sau lỗi mạng.
9. **Chọn fetch size** bằng benchmark trên đúng driver/DBMS; không dùng nó thay giới hạn kết quả.
10. **Streaming thật hay không?** Kiểm tra behavior, connection options, loại ResultSet và heap.
11. **Hạn chế N+1** bằng JOIN/truy vấn theo tập hoặc cơ chế ORM tương đương.
12. **Giới hạn số result rows** bằng SQL pagination/khoảng khóa, không giữ list toàn bộ.
13. **Đóng JDBC resources** đúng với `try`-with-resources và hợp đồng ownership.
14. **Kiểm soát thời gian/khối lượng**: query timeout, pool wait, transaction length, network failure.
15. **Đo cả DB và Java**: plan, round trips, p95 latency, memory và lock contention.
16. **Kiểm thử lỗi**: duplicate key, batch giữa chừng thất bại, rollback lỗi, timeout và generated keys theo driver.

## 17. Câu hỏi tự kiểm tra

1. Sự khác nhau giữa một SQL statement, một JDBC execution và một network round trip là gì?
2. `PreparedStatement.addBatch()` khác `Statement.addBatch(String)` như thế nào?
3. Vì sao batch không thích hợp để gửi một danh sách SELECT trả `ResultSet`?
4. Nếu có 205 mục và batch size 100, cần bao nhiêu lần `executeBatch()` để gửi hết?
5. Mảng `executeBatch()` tương ứng với các lệnh theo thứ tự nào?
6. `Statement.SUCCESS_NO_INFO` có nghĩa một lệnh làm thay đổi bao nhiêu row?
7. Nếu một mục batch thất bại, driver có bắt buộc ngừng mọi mục còn lại không?
8. Vì sao rollback transaction và retry batch là hai quyết định khác nhau?
9. `setAutoCommit(false)` giúp đạt tính chất gì khi nhiều chunk thuộc một nghiệp vụ?
10. Tại sao không nên chỉ gọi `Connection.close()` rồi giả định transaction được rollback?
11. `setFetchSize(256)` có giới hạn query trả đúng tối đa 256 dòng không?
12. `setMaxRows(100)` khác phân trang ở cấp SQL như thế nào?
13. Một driver có thể ignore hoặc diễn giải fetch size theo cách khác cấu hình mong đợi không?
14. `fetchSize=250` trên 10.000 row có chắc chắn tạo đúng 40 network round trips không?
15. Vì sao tăng fetch size không sửa được N+1 queries?
16. Khi nào JOIN có thể tạo row multiplication và vì sao query hai pha đôi khi hợp lý?
17. Lý do nào khiến `IN (?, ?, ...)` an toàn hơn ghép ID trực tiếp vào SQL?
18. Tại sao không nên đọc toàn bộ row vào `ArrayList` chỉ để tính `COUNT`?
19. Trong `JdbcBatchFetchDemo`, `submitted` có phải số row thực sự bị cập nhật không?
20. Những metrics nào bạn sẽ kiểm tra trước khi kết luận batch size 1000 tốt hơn 100?
21. Nếu mất kết nối khi commit, vì sao kết quả cuối của transaction có thể không rõ ràng?
22. Cần lưu ý gì khi dùng transaction manager hoặc pooled connection thay vì `DriverManager`?

## 18. Tài liệu chính thức cho Java SE 27

- [Java SE 27 API — PreparedStatement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html): `addBatch()`, bind parameters, statement re-use và execute methods.
- [Java SE 27 API — Statement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Statement.html): `executeBatch`, `executeLargeBatch`, `setFetchSize`, `setMaxRows`, `setQueryTimeout` và các hằng số update counts.
- [Java SE 27 API — BatchUpdateException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/BatchUpdateException.html): update counts khi batch gặp lỗi, driver stop/continue, `getLargeUpdateCounts`.
- [Java SE 27 API — ResultSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/ResultSet.html): cursor, `next()`, `setFetchSize` và vòng đời kết quả.
- [Java SE 27 API — Connection](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html): auto-commit, transaction, `commit`, `rollback` và tài nguyên.
- [Java SE 27 API — DatabaseMetaData](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/DatabaseMetaData.html): `supportsBatchUpdates` và khả năng DBMS/driver.
- [Java SE 27 API — DriverManager](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/DriverManager.html): kết nối JDBC mức cơ bản.
- [Java SE 27 API — DataSource](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html): abstraction quản lý nguồn kết nối.
- [Java SE 27 API — SQLException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html): `SQLState`, mã lỗi vendor, cause và chuỗi exceptions.
- [Java SE 27 API — SQLTimeoutException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLTimeoutException.html): lỗi timeout từ driver.
