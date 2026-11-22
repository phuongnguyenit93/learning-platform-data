# Đánh giá tính khả chuyển và chi phí bảo trì khi dùng thủ tục lưu trữ trong JDBC

**Thủ tục lưu trữ** (*stored procedure*) cho phép đưa một phần logic thao tác dữ liệu vào cơ sở dữ liệu và gọi từ ứng dụng Java. Trong **JDBC**, ta thường dùng `CallableStatement` để truyền tham số, thực thi thủ tục và nhận kết quả. Cách tổ chức này có thể giảm số lượt trao đổi giữa ứng dụng và database, gom những thao tác dữ liệu gần nhau và hỗ trợ kiểm soát quyền thực thi. Đổi lại, mã nghiệp vụ có thêm phần chạy trong hệ quản trị: ngôn ngữ thủ tục, cách xử lý transaction, định nghĩa kiểu dữ liệu, quy trình triển khai và kiểm thử có thể khác đáng kể giữa các sản phẩm.

Bài học thuộc chương **Thủ tục lưu trữ**. Trọng tâm là **đánh giá tính khả chuyển và tổng chi phí bảo trì** khi dùng stored procedure trong một hệ thống Java truy cập cơ sở dữ liệu quan hệ qua driver, `DataSource`, `PreparedStatement`, `CallableStatement` và `ResultSet`. Mục tiêu là có tiêu chí quyết định dựa trên yêu cầu nghiệp vụ, thay vì xem stored procedure luôn tốt hoặc luôn xấu.

## 1. Nhìn stored procedure như một lựa chọn đặt logic ở đâu

Giả sử hệ thống quản lý tồn kho cần trừ một số lượng sản phẩm có điều kiện: chỉ được trừ khi còn đủ hàng. Có ít nhất hai phương án.

**Phương án A — SQL tham số hóa trực tiếp trong Java:**

```java
String sql =
        "UPDATE inventory " +
        "SET available = available - ? " +
        "WHERE product_id = ? AND available >= ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, quantity);
    statement.setLong(2, productId);
    statement.setInt(3, quantity);

    int affectedRows = statement.executeUpdate();
    boolean reserved = affectedRows == 1;
}
```

Câu `UPDATE` này thể hiện thay đổi có điều kiện trực tiếp tại database. Nếu `product_id` là duy nhất, số dòng bị ảnh hưởng cho biết có trừ được hàng hay không. Cần xác thực `quantity > 0` trước khi chạy và xem xét ràng buộc số lượng không âm tại bảng. Khi đơn đặt hàng gồm nhiều thao tác, tầng sở hữu transaction vẫn phải quản lý `commit()`/`rollback()`.

**Phương án B — gọi thủ tục đã triển khai tại database:**

```text
Java service
    │ reserveStock(productId, quantity)
    ▼
InventoryRepository
    │ CallableStatement.execute()
    ▼
Database procedure reserve_stock
    ├─ Kiểm tra điều kiện
    ├─ Cập nhật inventory
    └─ Trả mã kết quả
```

Một stored procedure có thể gom các bước kiểm tra và cập nhật vào phía database. Nhưng **đưa logic vào procedure không tự bảo đảm tính nguyên tử, tính nhất quán hay hiệu năng**: còn phải xem câu SQL bên trong, mức cô lập, khóa, transaction và thiết kế ràng buộc.

Với nghiệp vụ chỉ cần **một câu `UPDATE` nguyên tử**, phương án A đã có lợi thế về độ đơn giản và không nhất thiết tạo nhiều lượt mạng. Stored procedure thường đáng cân nhắc hơn khi **nhiều bước SQL có liên hệ chặt** hoặc khi cần một API dữ liệu ổn định để nhiều ứng dụng dùng chung.

## 2. JDBC chuẩn hóa lệnh gọi, không chuẩn hóa toàn bộ thủ tục

JDBC cung cấp một lớp giao tiếp tương đối thống nhất:

| API JDBC | Vai trò |
| --- | --- |
| `Connection.prepareCall(sql)` | Tạo `CallableStatement` để gọi một routine |
| `CallableStatement.setXxx(index, value)` | Truyền tham số `IN` hoặc phần đầu vào của `INOUT` |
| `CallableStatement.registerOutParameter(index, sqlType)` | Đăng ký tham số `OUT`/`INOUT` trước khi thực thi |
| `execute()` | Chạy thủ tục có thể sinh kết quả dạng dòng, số hàng bị tác động hoặc nhiều kết quả |
| `getXxx(index)` | Nhận tham số đầu ra, theo kiểu tương ứng và hợp đồng của driver |
| `getResultSet()`, `getUpdateCount()`, `getMoreResults()` | Duyệt các kết quả của câu lệnh có nhiều kết quả |
| `DatabaseMetaData` | Khảo sát khả năng hỗ trợ procedures, tham số và những tính năng JDBC được công bố |

Dạng gọi *JDBC escape syntax* thường thấy:

```java
// Procedure nhận ba tham số: IN, IN, OUT.
String call = "{call reserve_stock(?, ?, ?)}";
```

Đối với function có giá trị trả về, cú pháp escape thường dùng `{? = call function_name(?)}`. Tuy nhiên, **procedure và function không phải cùng một loại routine trên mọi hệ quản trị**; cú pháp gọi và cách driver chuyển đổi escape syntax có thể phụ thuộc driver, cấu hình và phiên bản.

Điều JDBC **không chuẩn hóa trọn vẹn** là:

- Ngôn ngữ viết nội dung procedure: PL/pgSQL, PL/SQL, T-SQL, SQL/PSM hay các biến thể riêng.
- Cú pháp `CREATE PROCEDURE`, khai báo biến, rẽ nhánh, vòng lặp, bắt lỗi, trả `ResultSet` hoặc cursor.
- Kiểu SQL do procedure nhận/trả, đặc biệt array, object/record, table-valued parameter, `REF CURSOR` và kiểu do người dùng định nghĩa.
- Quyền tạo/sửa/chạy routine, mô hình `DEFINER`/`INVOKER`, kế thừa vai trò và cách đặt schema.
- Quy tắc có được `COMMIT`/`ROLLBACK` bên trong procedure hay không.
- Số lượng, thứ tự và cách xử lý update count/result set khi một lời gọi tạo nhiều kết quả.

Vì vậy, **biên dịch được mã Java dùng `CallableStatement` không đồng nghĩa thủ tục có thể chuyển nguyên vẹn từ database A sang database B**.

## 3. Một hợp đồng stored procedure từ phía Java

Để hình dung chi phí bảo trì ở ranh giới giữa Java và database, giả sử database đã có routine với hợp đồng **minh họa** sau:

```text
reserve_stock(
    p_product_id  IN  BIGINT,
    p_quantity    IN  INTEGER,
    p_status      OUT INTEGER
)

p_status = 1: đã giữ hàng
p_status = 0: không đủ hàng hoặc không tìm thấy sản phẩm
```

Đây là **hợp đồng khái niệm**. Trước khi chạy, phải tạo routine bằng cú pháp hợp lệ cho hệ quản trị đích; định nghĩa `OUT` và ánh xạ kiểu của driver cần được kiểm thử riêng.

Ví dụ Java:

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;

public final class InventoryProcedureGateway {
    private final DataSource dataSource;

    public InventoryProcedureGateway(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserve(long productId, int quantity)
            throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        String call = "{call reserve_stock(?, ?, ?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement statement = connection.prepareCall(call)) {

            statement.setLong(1, productId);
            statement.setInt(2, quantity);
            statement.registerOutParameter(3, Types.INTEGER);

            statement.execute();

            // Hợp đồng minh họa giả định driver đã trả được OUT
            // ở thời điểm này và procedure không trả result sets.
            int status = statement.getInt(3);
            if (statement.wasNull()) {
                throw new SQLException(
                        "reserve_stock returned NULL status");
            }

            if (status == 1) {
                return true;
            }
            if (status == 0) {
                return false;
            }
            throw new SQLException(
                    "Unexpected reserve_stock status: " + status);
        }
    }
}
```

Những điều cần xác nhận khi tích hợp:

1. **Chỉ số tham số bắt đầu từ 1**, và vị trí `IN`, `OUT` phải khớp định nghĩa thực tế trong database. Với function có return value, vị trí tham số có thể dịch chuyển do vị trí giá trị trả về.
2. `registerOutParameter(3, Types.INTEGER)` mô tả kiểu JDBC mong đợi; cột/kiểu đầu ra thực tế phải tương thích với driver.
3. Ví dụ chỉ làm việc với một mã `OUT`, **không có `ResultSet` hoặc update count cần duyệt**. Nếu procedure trả nhiều kết quả, phải xử lý kết quả theo JDBC và yêu cầu của driver trước khi lấy `OUT` khi cần.
4. `try-with-resources` đóng `CallableStatement` rồi `Connection`. Với pool, đóng connection logic thường trả quyền sử dụng về pool.
5. Câu hỏi “procedure có commit hay không?” phải có câu trả lời rõ trong hợp đồng. Ví dụ dùng kết nối do phương thức tự lấy và không chủ động mở transaction nhiều bước; nếu gọi trong transaction của service, nên nhận `Connection` từ bên sở hữu thay vì tự mượn kết nối khác.
6. Hợp đồng trả `0` cho hai tình huống “sản phẩm không tồn tại” và “không đủ hàng” làm mất thông tin phân biệt. Nếu service cần xử lý khác nhau, đây là thay đổi **hợp đồng phiên bản** của procedure, không chỉ là chuyện viết lại SQL bên trong.

Đây là nơi phát sinh chi phí bảo trì: **một thay đổi ở database có thể yêu cầu đổi mã Java, kiểm thử JDBC và điều chỉnh hành vi nghiệp vụ đồng thời**.

## 4. Các tầng của tính khả chuyển

Nói “JDBC hỗ trợ đa cơ sở dữ liệu” là đúng ở lớp API, nhưng phải tách các tầng phụ thuộc.

| Tầng | Khả chuyển tương đối | Những phần dễ phải đổi |
| --- | --- | --- |
| Java gọi JDBC | Khá cao với API chuẩn | Cấu hình driver/DataSource, xử lý kiểu riêng, SQLState |
| SQL quan hệ thông thường | Trung bình | Hàm SQL, kiểu dữ liệu, quoting, phân trang, `RETURNING`, cú pháp upsert |
| Cú pháp gọi procedure | Trung bình đến thấp | `CALL`/`EXEC`, function vs procedure, OUT/INOUT, cách escape syntax được driver diễn giải |
| Mã thân procedure | Thường thấp | Ngôn ngữ, exception handler, cursor, dynamic SQL, transaction, quyền |
| Kiểu dữ liệu đặc biệt và đa kết quả | Thường thấp | `REF CURSOR`, `ARRAY`, kiểu tự định nghĩa, table-valued parameter |
| Triển khai và vận hành | Phụ thuộc hạ tầng | Quyền chạy migration, công cụ schema versioning, giám sát và rollback DDL |

**Tính khả chuyển có nhiều cấp độ:**

- **Chuyển được giao diện Java:** lớp gọi `DataSource` và `CallableStatement` ít thay đổi.
- **Chuyển được hợp đồng routine:** tên, kiểu tham số, lỗi và kết quả giữ tương đương khi đổi database.
- **Chuyển được mã routine:** nội dung stored procedure chạy gần như nguyên vẹn ở sản phẩm mới.

Ba cấp độ trên không đồng nghĩa. Một ứng dụng có thể giữ nguyên interface Java nhưng phải viết lại toàn bộ procedure và bộ kiểm thử tích hợp khi chuyển hệ quản trị.

### Ví dụ khác biệt giữa các hệ quản trị

| Hệ quản trị | Nét riêng ảnh hưởng chi phí chuyển đổi |
| --- | --- |
| **PostgreSQL** | Có `CREATE FUNCTION` và `CREATE PROCEDURE` (procedure/`CALL` từ PostgreSQL 11). PL/pgSQL, kiểu trả về tập hàng, cursor và quy tắc transaction khác sản phẩm khác. Việc driver chuyển escape syntax của procedure/function cần xét cấu hình. |
| **Oracle Database** | PL/SQL, package, overload, `OUT`/`IN OUT` và `REF CURSOR` thường tạo giao diện nhiều đặc tính riêng. Transaction và lỗi PL/SQL có quy tắc riêng. |
| **SQL Server** | T-SQL, `EXEC`, `OUTPUT`, return status, result set/update count và table-valued parameter có quy ước riêng; một routine có thể gửi nhiều kết quả. |
| **MySQL** | `CREATE PROCEDURE`, `IN`/`OUT`/`INOUT` và bộ cú pháp stored program của MySQL; hành vi transaction tùy storage engine. `DELIMITER` nếu gặp trong hướng dẫn là lệnh của client CLI, không phải SQL để gửi qua JDBC. |

Bảng nhằm chỉ rõ **điểm phải thử nghiệm**. Không nên coi mọi trường hợp ở từng sản phẩm hoặc phiên bản đều được thực hiện giống nhau. Ví dụ, gọi procedure, function và nhận cursor trên một driver có thể cần cú pháp hoặc cấu hình riêng dù mã JDBC cùng dùng `CallableStatement`.

### Có thể tránh phụ thuộc bằng cách nào?

Đặt một interface Java rõ ràng:

```java
public interface InventoryGateway {
    boolean reserve(long productId, int quantity);
}
```

Và hai implementation, một dùng `PreparedStatement`, một dùng `CallableStatement`:

```text
       InventoryService
             │
        InventoryGateway
             │
       ┌─────┴─────┐
       ▼           ▼
   SqlGateway  ProcedureGateway
       │           │
 PreparedStatement CallableStatement
       └─────┬─────┘
             ▼
          Database
```

Khi thay hệ quản trị hoặc thay chiến lược, service vẫn nói chuyện qua **hợp đồng nghiệp vụ**. Nhưng lớp adapter này chỉ **khoanh vùng phụ thuộc**; nó không loại bỏ công sức chuyển DDL, dữ liệu, ngữ nghĩa transaction, tính đúng đắn đồng thời và kiểm thử.

## 5. Chi phí bảo trì nằm ở những đâu?

Chi phí sở hữu (*total cost of ownership*) của một procedure không chỉ gồm số dòng SQL. Nên tính cả công việc của đội phát triển, DBA, vận hành và kiểm thử trong suốt vòng đời tính năng.

| Hạng mục | Chi phí dễ bị bỏ sót | Câu hỏi khi đánh giá |
| --- | --- | --- |
| Thiết kế hợp đồng | Tên routine, số/thứ tự/kiểu tham số, mã lỗi, shape kết quả | Java có phụ thuộc trực tiếp vào thứ tự tham số hoặc vendor type không? |
| Phát triển | Viết ngôn ngữ thủ tục riêng và review SQL | Đội có đủ khả năng debug PL/SQL, PL/pgSQL hay T-SQL không? |
| Thay đổi schema | Thân procedure phụ thuộc bảng, cột, chỉ mục | Rename cột nào sẽ làm hỏng bao nhiêu procedure? |
| Triển khai | Migration database phải phối hợp release ứng dụng | Có thể triển khai hai phiên bản ứng dụng cùng lúc không? |
| Kiểm thử | Unit test Java không chạy nội dung routine thật | Có test tích hợp với database đúng phiên bản và lỗi đồng thời không? |
| Gỡ lỗi | Stack trace Java dừng tại lời gọi routine | Có log, tracing, plan và số liệu phía database không? |
| Vận hành | Quyền `EXECUTE`, role, lock, timeout, deadlock | Có chính sách phân quyền và quan sát hiệu năng của routine không? |
| Chuyển hệ quản trị | Viết lại routine và quy tắc xử lý dữ liệu | Có cần duy trì song song hai implementation không? |
| Khả năng hồi phục | DDL, version procedure, rollback deployment | Có lộ trình quay lại nếu ứng dụng mới lỗi không? |

### Chi phí thay đổi hợp đồng

Giả sử `reserve_stock` đang nhận `(product_id, quantity, status OUT)`. Nhu cầu mới yêu cầu trả thêm mã lô hàng và phân biệt ba trạng thái: đã đặt, hết hàng, không có sản phẩm. Một thay đổi nhỏ về nghiệp vụ có thể kéo theo:

1. Sửa định nghĩa và thân routine trên database.
2. Cập nhật `CallableStatement`: số placeholder, `registerOutParameter(...)`, `getXxx(...)`, mapping kết quả.
3. Điều chỉnh interface/repository/service và kiểm thử.
4. Phối hợp phiên bản database với các instance Java cũ vẫn đang chạy.
5. Chuẩn bị kế hoạch khôi phục nếu migration hoặc bản ứng dụng mới gặp lỗi.

Nếu đổi chữ ký hiện có khi vẫn có instance cũ gọi, các lời gọi cũ có thể thất bại ngay. Một cách triển khai an toàn là tạo **routine phiên bản mới** hoặc thêm giao diện tương thích theo khả năng hệ quản trị, triển khai ứng dụng mới, chuyển traffic, rồi bỏ phiên bản cũ sau khi đã xác minh không còn người dùng. Không nên giả định mọi sản phẩm có cùng cách overload tên routine hoặc đặt tham số mặc định.

## 6. Transaction và lỗi: tính khả chuyển còn là tính đúng đắn

Đưa nhiều lệnh SQL vào stored procedure không tự quyết định đúng ranh giới transaction. Cần trả lời rõ **ai sở hữu `commit()` và `rollback()`**.

Có hai mô hình cần phân biệt:

- **Ứng dụng sở hữu transaction:** service mượn một `Connection`, đặt `autoCommit=false`, gọi nhiều DAO hoặc procedure bằng cùng kết nối, rồi `commit()` hoặc `rollback()`. Procedure được thiết kế **không tự kết thúc transaction** của bên gọi.
- **Procedure sở hữu transaction:** logic transaction nằm tại database và chịu quy tắc của hệ quản trị; việc gọi routine trong transaction bên ngoài có thể không được phép hoặc hoạt động khác dự kiến.

Hai mô hình không thể tự động thay thế nhau. Ví dụ, một số hệ quản trị chỉ cho phép transaction control bên trong procedure ở những hoàn cảnh gọi nhất định, trong khi sản phẩm khác có cách xử lý riêng. Bởi vậy, hợp đồng routine cần nói rõ **có được phép gọi từ transaction của ứng dụng hay không**.

### Mã Java khi service sở hữu transaction

```java
// Minh họa trong một phương thức service đã xác định
// được quyền sở hữu Connection và transaction.
try (Connection connection = dataSource.getConnection()) {
    boolean oldAutoCommit = connection.getAutoCommit();
    if (!oldAutoCommit) {
        throw new SQLException(
                "Expected a connection outside an active transaction");
    }

    connection.setAutoCommit(false);
    boolean ended = false;
    Throwable primary = null;

    try {
        // Hàm bên trong dùng chính connection này.
        reserveUsingProcedure(connection, productId, quantity);
        insertReservation(connection, orderId, productId, quantity);

        connection.commit();
        ended = true;
    } catch (SQLException | RuntimeException | Error failure) {
        primary = failure;
        try {
            connection.rollback();
            ended = true;
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    } finally {
        if (ended) {
            try {
                connection.setAutoCommit(oldAutoCommit);
            } catch (SQLException restoreFailure) {
                if (primary != null) {
                    primary.addSuppressed(restoreFailure);
                } else {
                    throw restoreFailure;
                }
            }
        }
    }
}
```

Đây là **đoạn minh họa** với `reserveUsingProcedure(...)` và `insertReservation(...)` là helper do ứng dụng triển khai, dùng cùng connection và không tự commit. Giả định procedure **không tự thay đổi transaction**. Nếu rollback thất bại, trạng thái kết nối có thể không chắc chắn; **không bật lại `autoCommit=true`** theo thói quen vì điều đó có thể commit những thay đổi chưa hoàn tác. Khi dùng pool, cần chính sách **loại bỏ kết nối nghi vấn** theo API của pool. Việc `commit()` báo lỗi do mất kết nối cũng có thể khiến kết quả ở server chưa xác định.

### Lỗi nghiệp vụ và lỗi JDBC không phải một

Routine có thể báo kết quả bằng mã `OUT`, ngoại lệ SQL, return status, hoặc tập kết quả. Các cách này không tương đương giữa hệ quản trị. Hãy thiết kế quy ước rõ:

| Sự kiện | Cách diễn đạt nên cân nhắc |
| --- | --- |
| Không đủ tồn kho | Mã kết quả nghiệp vụ đã định nghĩa hoặc một kết quả có cấu trúc |
| Không tồn tại sản phẩm | Kết quả riêng nếu service cần phân biệt |
| Vi phạm unique/foreign key | `SQLException` và bước chuyển thành lỗi truy cập dữ liệu ở DAO |
| Deadlock hoặc serialization failure | Transaction rollback; ứng dụng có thể retry toàn bộ transaction có giới hạn |
| Lỗi kết nối khi chạy hoặc commit | Điều tra khả năng thao tác đã hoàn tất; yêu cầu idempotency nếu thử lại |
| Routine thay đổi chữ ký | Lỗi tích hợp/triển khai; không retry mù quáng |

Không dùng `SQLException.getMessage()` hoặc một số vendor code chưa được kiểm chứng làm hợp đồng nghiệp vụ công khai. Khi dữ liệu quan trọng, hãy giữ `SQLState`, mã lỗi driver, `getNextException()` và nguyên nhân để chẩn đoán nội bộ.

## 7. Stored procedure có nhanh hơn SQL Java không?

**Không có bảo đảm chung.** Phải đo với cùng dữ liệu, chỉ mục, workload và mức cô lập. Một procedure có thể hữu ích khi:

- Giảm nhiều lần qua lại mạng cho một nghiệp vụ gồm nhiều câu SQL.
- Đưa phép tính gần dữ liệu lớn, tránh kéo nhiều hàng về Java rồi gửi kết quả ngược lại database.
- Tái sử dụng cùng logic dữ liệu trong nhiều ứng dụng, giảm nguy cơ mỗi ứng dụng thực thi các bước khác nhau.
- Cho phép truy cập bảng qua một tập quyền thực thi routine theo thiết kế bảo mật đã được kiểm thử.

Nhưng stored procedure cũng có thể có chi phí:

- Câu SQL bên trong vẫn có thể dùng kế hoạch truy vấn kém, thiếu chỉ mục hoặc giữ khóa lâu.
- Logic tuần tự nhiều bước ở database có thể kéo dài transaction và gây tranh chấp tài nguyên.
- Lợi ích giảm lượt mạng không đáng kể nếu nghiệp vụ vốn chỉ dùng một câu `UPDATE` như phần 1.
- Đặc điểm cached plan, parameter sniffing, recompile và công cụ profiling khác giữa các hệ quản trị.
- Hành vi trả nhiều `ResultSet` hoặc lượng dữ liệu lớn có thể làm chi phí truyền dữ liệu không giảm như kỳ vọng.

**Cách benchmark đúng:** so sánh phương án procedure với phương án `PreparedStatement` có cùng ngữ nghĩa transaction, cùng dữ liệu đầu vào, chỉ mục, số bản ghi và điều kiện đồng thời. Đo thời gian đầu-cuối (bao gồm network), CPU/database load, số lượt round trip, p95/p99 latency, lock wait và tỉ lệ lỗi. Thực hiện cả bài thử khi có nhiều yêu cầu đồng thời; một lần chạy thử trên máy lập trình không đủ kết luận.

Tránh kết luận “logic trong database luôn nhanh hơn logic trong Java”. Nếu database đang là tài nguyên giới hạn nhất, thêm công việc vào database có thể làm tổng throughput giảm.

## 8. Bảo mật, quyền và khả năng quan sát

Stored procedure có thể cho phép cấp quyền **EXECUTE** trên một routine mà không cấp mọi quyền trực tiếp lên bảng cho người gọi, tùy mô hình quyền của database. Đây có thể là lợi thế khi cần che một số thao tác dữ liệu. Tuy nhiên cần kiểm tra:

- Routine chạy dưới quyền của **người gọi** hay **người định nghĩa**, và có tự đổi role/schema hay không?
- Dynamic SQL trong thân procedure có ghép dữ liệu đầu vào không? Stored procedure **không tự phòng SQL injection** nếu bản thân nó ghép chuỗi SQL nguy hiểm.
- Quyền `EXECUTE` có dẫn đến truy cập dữ liệu rộng hơn yêu cầu không?
- Có giám sát được thời gian thực thi routine, số dòng cập nhật, lock wait, timeout và các lỗi bên trong không?
- Log có chứa dữ liệu nhạy cảm, SQL text hoặc tham số từ người dùng không?

Ví dụ: Java gọi `CallableStatement` với tham số `?` là một phần thực hành tốt. Nhưng nếu procedure dùng nội suy chuỗi không an toàn trong dynamic SQL, rủi ro injection vẫn tồn tại **bên trong database**.

Với tracing, một span `reserve_stock` tại Java chỉ cho biết thời gian của lời gọi. Muốn thấy từng truy vấn con, lock wait hoặc execution plan, cần công cụ giám sát trên database phù hợp. Đây là khoản chi phí vận hành cần tính khi quyết định đặt logic ở stored procedure.

## 9. Quản lý mã nguồn, schema migration và triển khai an toàn

Mã procedure cần được xem như **mã ứng dụng có phiên bản**, không phải câu lệnh được DBA sửa thủ công ngoài lịch sử thay đổi.

Quy trình thực tế:

1. **Lưu định nghĩa routine trong version control** cùng các migration có thứ tự rõ ràng.
2. **Kiểm thử migration từ trạng thái database cũ** và kiểm thử trên database mới, không chỉ thử chạy thủ công ở một môi trường đã được sửa trước đó.
3. **Xác định quyền deploy** routine, quyền `EXECUTE` cho tài khoản ứng dụng và cách giữ chúng sau khi thay routine.
4. **Quy định hợp đồng tham số/kết quả** (tên, thứ tự, kiểu, `NULL`, mã trả về, ngoại lệ, transaction ownership).
5. **Triển khai tương thích nhiều phiên bản** khi có các instance Java cũ/mới cùng hoạt động: bổ sung routine mới trước, chuyển dần ứng dụng, xóa routine cũ sau.
6. **Giám sát sau phát hành**: lỗi không tìm thấy routine, lỗi sai chữ ký, lock, timeout, sai kết quả và tác động đến các câu SQL liên quan.
7. **Chuẩn bị rollback** ứng dụng và database trong phạm vi hệ quản trị cho phép; một migration không phải lúc nào cũng có thể hoàn tác bằng DDL ngược an toàn.

Các công cụ migration có thể giúp giữ lịch sử và kiểm soát thứ tự thay đổi, nhưng cần cấu hình đúng cú pháp routine của hệ quản trị (ví dụ dấu phân tách nội dung câu lệnh và escape). Không giả định việc chạy nhiều câu DDL được rollback nguyên tử trên mọi database.

### Tương thích ngược trong thực tế

Giả sử `reserve_stock` bản v1 chỉ có một tham số `OUT` kiểu số; bản v2 cần thêm thông tin kho và ngày giao dự kiến. Có thể triển khai:

```text
DB v1:
    reserve_stock_v1(...)

Deploy DB mở rộng:
    reserve_stock_v1(...)
    reserve_stock_v2(...)

Deploy Java mới:
    Java cũ → reserve_stock_v1(...)
    Java mới → reserve_stock_v2(...)

Sau khi kiểm chứng không còn Java cũ:
    loại bỏ reserve_stock_v1(...) theo quy trình release
```

Mẫu “mở rộng → chuyển đổi → thu hẹp” này giúp tránh việc đổi chữ ký đột ngột làm hỏng ứng dụng cũ. Có thể chọn tên routine có phiên bản, schema version hoặc adapter tương thích; cách áp dụng cụ thể tùy hệ quản trị và chuẩn đặt tên của dự án.

## 10. Chiến lược kiểm thử để chi phí bảo trì được đo lường

Chỉ mock `CallableStatement` trong unit test không đủ để chứng minh routine thực thi đúng. Ít nhất cần ba lớp kiểm thử:

| Lớp kiểm thử | Đối tượng cần xác nhận |
| --- | --- |
| Unit test Java | Mapping tham số, xử lý mã `OUT`/`NULL`, hợp đồng repository, hành vi khi nhận `SQLException` |
| Integration test với database thật | Routine tồn tại, đúng chữ ký, kiểu dữ liệu, quyền, transaction, kết quả trên driver và phiên bản cụ thể |
| Kiểm thử cạnh tranh/hiệu năng | Lock, deadlock, lỗi serialization, số vòng mạng, timeout, throughput và tính đúng khi nhiều yêu cầu đồng thời |

Các ca kiểm thử cốt lõi cho `reserve_stock`:

- Sản phẩm có đủ tồn kho → cập nhật đúng số lượng và trả thành công.
- Không đủ tồn kho → không giảm số lượng; trả kết quả nghiệp vụ đúng.
- Sản phẩm không tồn tại → trả trạng thái theo hợp đồng, không nhầm với hết hàng nếu service cần phân biệt.
- Tham số `quantity=0` hoặc âm → validation nhất quán ở Java và database.
- Hai transaction cùng giữ những đơn vị tồn kho cuối → không bán quá mức, xét ràng buộc và mức cô lập thực tế.
- Gọi procedure cùng một transaction với thao tác ghi khác → nếu thao tác sau lỗi, rollback được cả hai theo hợp đồng.
- Routine thay đổi chữ ký hoặc bị thu hồi quyền → DAO phát hiện lỗi tích hợp và báo đúng nhóm.
- Driver trả `OUT` khác kỳ vọng hoặc `NULL` → Java xử lý theo hợp đồng.
- Database bị chậm hoặc mất kết nối → ứng dụng không retry một tác vụ có tác dụng phụ khi chưa biết trạng thái commit.
- Nếu hỗ trợ thêm database thứ hai → **cùng bộ kiểm thử hành vi** phải chạy trên implementation tương ứng ở cả hai.

Đối với routine trả `ResultSet`, cursor hoặc nhiều kết quả, cần thêm thử nghiệm đúng thứ tự đọc, đóng tài nguyên, update counts, và thời điểm driver cho phép lấy tham số `OUT`. Với `CALL` chứa nhiều câu lệnh có tác dụng phụ, cần kiểm thử lỗi giữa chừng và hành vi transaction chứ không chỉ “chạy thành công”.

## 11. Ma trận quyết định: khi nào đáng dùng stored procedure?

Có thể dùng các tiêu chí sau để đánh giá từng trường hợp. Thang 1–5 là **gợi ý thảo luận định tính**, không phải điểm số khách quan hay kết quả benchmark.

| Tiêu chí | Nghiêng về `PreparedStatement` và SQL trong Java | Nghiêng về stored procedure |
| --- | --- | --- |
| Logic dữ liệu | Một vài câu SQL rõ ràng, dễ gom trong transaction Java | Nhiều bước liên quan chặt đến dữ liệu, nhiều ứng dụng cần tái sử dụng |
| Khả chuyển | Có kế hoạch hỗ trợ nhiều DB hoặc thường xuyên đổi sản phẩm | Chấp nhận ràng buộc với một DB lâu dài |
| Năng lực đội ngũ | Java/SQL là năng lực chính; ít hỗ trợ review code routine | Có kinh nghiệm tốt về ngôn ngữ thủ tục, DBA và giám sát |
| Tần suất thay đổi | Quy tắc nghiệp vụ thay đổi liên tục với release Java | Quy tắc dữ liệu tương đối ổn định; quy trình migration đủ mạnh |
| Hiệu năng | Một câu SQL hoặc batch đã đáp ứng latency | Đo thực tế cho thấy giảm round trip/CPU/data transfer đáng kể |
| Quyền truy cập | Quyền bảng và API hiện tại đủ kiểm soát | Cần giao diện thực thi phía database theo chính sách quyền |
| Kiểm thử & vận hành | Chưa có tích hợp kiểm thử DB và quan sát routine | Có CI với database thật, migration có phiên bản, tracing và rollback |

### Ví dụ áp dụng vào hai bài toán

**Tình huống 1: cập nhật trạng thái một đơn hàng.** Một câu:

```sql
UPDATE orders
SET status = ?
WHERE id = ? AND status = ?;
```

`PreparedStatement` giúp mã ngắn, dùng placeholder và kiểm tra số hàng ảnh hưởng. Nếu đây là toàn bộ nghiệp vụ, stored procedure riêng có thể tăng số nơi phải sửa mà chưa có lợi ích hiệu năng đáng kể.

**Tình huống 2: xử lý đối soát dữ liệu lớn, gồm nhiều phép tổng hợp và cập nhật.** Nếu đưa nhiều dữ liệu về Java rồi đẩy trở lại gây round trip và tiêu thụ mạng lớn, một routine có thể đáng thử nghiệm. Tuy nhiên cần so với cách khác như một câu `INSERT ... SELECT`, `UPDATE` có join, batch hoặc một số truy vấn theo lô. Nếu chọn procedure, yêu cầu kế hoạch migration, integration test, theo dõi lock/timeout và quản lý transaction rõ ràng.

Không nên xây dựng routine chỉ để thay mỗi câu `SELECT` bằng một wrapper; cũng không nên đưa **mọi** logic nghiệp vụ nhiều bước sang Java nếu database có cơ chế thích hợp giúp bảo vệ bất biến dữ liệu. Quyết định nằm ở yêu cầu cụ thể và bằng chứng đo đạc.

## 12. Bài thực hành: đánh giá chi phí thay vì chỉ viết thủ tục

Một bài tập nhóm phù hợp cho module JDBC:

1. Xây dựng bảng `inventory(product_id BIGINT PRIMARY KEY, available INTEGER NOT NULL)` với ràng buộc không âm nếu database hỗ trợ phù hợp.
2. Cài đặt `InventoryGateway` bằng `PreparedStatement` với câu `UPDATE` có điều kiện; kiểm tra số hàng ảnh hưởng.
3. Viết routine `reserve_stock` tương đương trong hệ quản trị đang dùng, gọi bằng `CallableStatement` với hai `IN` và một `OUT` theo cú pháp/driver phù hợp.
4. Thiết kế hai bài kiểm thử đồng thời giữ những sản phẩm cuối, xác minh không bán quá tồn kho và xác định cách transaction rollback khi thao tác khác lỗi.
5. So sánh số lần gọi JDBC, số lượt mạng, latency, lock wait, số tệp phải thay đổi khi sửa hợp đồng và công việc migration cho hai phương án.
6. Giả sử cần chuyển từ DB đang dùng sang hệ quản trị khác. Liệt kê cụ thể những chỗ phải sửa: DDL, thân routine, cách gọi, kiểu `OUT`, lỗi và integration test.
7. Viết một *architecture decision record* ngắn: quyết định chọn phương án nào, dữ liệu đo hỗ trợ, rủi ro chấp nhận và điều kiện cần xem lại quyết định.

### Câu hỏi tự đánh giá

- `CallableStatement` là API chuẩn; vì sao điều đó không bảo đảm thân thủ tục có thể chuyển nguyên giữa SQL Server và PostgreSQL?
- Khi `execute()` thành công nhưng `getInt(3)` trả `0`, ứng dụng làm sao phân biệt mã kết quả hợp lệ với SQL `NULL`?
- Nếu procedure bị đổi tên hoặc thứ tự tham số, những tầng nào phải cập nhật và kiểm thử?
- Khi procedure tự `COMMIT`, điều gì có thể xảy ra với transaction đang bao trùm nhiều DAO của service?
- Một procedure chạy nhanh hơn trong benchmark đơn luồng có chắc làm hệ thống nhanh hơn dưới tải ghi đồng thời không?
- Khi app và database được triển khai không đồng thời, cách giữ tương thích phiên bản nào an toàn hơn việc sửa trực tiếp chữ ký procedure đang được sử dụng?

## 13. Tổng kết các nguyên tắc

1. **Tính khả chuyển của JDBC khác với tính khả chuyển của thủ tục.** API `CallableStatement` chuẩn hóa cách gọi ở Java, còn thân procedure, kiểu dữ liệu và transaction phụ thuộc nhiều vào sản phẩm.
2. **Đánh giá cả vòng đời, không chỉ số dòng code.** Tính chi phí migration, schema coupling, kiểm thử, quyền, quan sát lỗi, rollout nhiều phiên bản và rollback.
3. **Giữ hợp đồng ổn định giữa service và DAO.** Một interface nghiệp vụ giúp khoanh vùng phụ thuộc nhưng vẫn cần kiểm chứng implementation trên DB đích.
4. **Bảo đảm đúng transaction và xử lý lỗi.** Làm rõ ai commit/rollback, giữ `SQLException` gốc và retry chỉ khi có điều kiện an toàn.
5. **Đo bằng workload thực tế.** So sánh procedure với SQL tham số hóa, batch và câu SQL tập hợp trước khi chọn vì lý do hiệu năng.
6. **Đưa mã thủ tục vào quy trình phát triển.** Version control, code review, migration, tích hợp kiểm thử với database thật và triển khai tương thích ngược là những yêu cầu bảo trì thiết yếu.

**Kết luận:** stored procedure là công cụ hợp lý khi việc gom logic gần dữ liệu, tái sử dụng giữa nhiều ứng dụng, kiểm soát quyền hoặc giảm round trip đem lại lợi ích đã được xác minh. Với **JDBC**, lựa chọn tốt cần cân bằng lợi ích đó với ràng buộc vào hệ quản trị, chi phí thay đổi hợp đồng, kiểm thử và vận hành lâu dài.
