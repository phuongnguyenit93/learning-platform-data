# Duyệt nhiều kết quả bằng `getMoreResults`

## 1. Một lần thực thi SQL có thể tạo ra nhiều kết quả

Trong **JDBC (Java Database Connectivity)**, API Java để truy cập cơ sở dữ liệu quan hệ, thông thường một lời gọi SQL trả về **một** tập hàng (`ResultSet`) hoặc **một** số đếm hàng bị ảnh hưởng (*update count*). Tuy nhiên, tùy cơ sở dữ liệu, driver và loại câu lệnh, **một lần thực thi** có thể tạo ra **nhiều kết quả nối tiếp nhau**.

Chẳng hạn, một stored procedure xử lý báo cáo có thể thực hiện các bước sau:

1. Trả về danh sách đơn hàng cần xử lý: kết quả thứ nhất là `ResultSet`.
2. Cập nhật trạng thái đơn hàng: kết quả tiếp theo là update count.
3. Trả về danh sách tổng hợp sau khi cập nhật: kết quả cuối là một `ResultSet` khác.

```text
Một lần CallableStatement.execute()
                  │
                  ▼
      ┌────────────────────┐
      │ Kết quả 1          │  ResultSet: nhiều hàng
      └────────────────────┘
                  │ getMoreResults()
                  ▼
      ┌────────────────────┐
      │ Kết quả 2          │  Update count: ví dụ 4
      └────────────────────┘
                  │ getMoreResults()
                  ▼
      ┌────────────────────┐
      │ Kết quả 3          │  ResultSet: nhiều hàng
      └────────────────────┘
                  │ getMoreResults()
                  ▼
             Hết kết quả
```

Ở đây cần phân biệt **duyệt các hàng trong một `ResultSet`** với **duyệt nhiều kết quả của một lần thực thi**:

- `resultSet.next()` di chuyển con trỏ sang **hàng kế tiếp của cùng một `ResultSet`**.
- `statement.getMoreResults()` di chuyển sang **kết quả kế tiếp của cùng một lần thực thi**; kết quả mới có thể là `ResultSet`, update count hoặc không còn kết quả.

`getMoreResults()` **không tự chạy một câu SQL mới**. Nó chỉ giúp đọc các kết quả do lệnh `execute()` trước đó tạo ra.

## 2. Các phương thức quan trọng và ý nghĩa giá trị trả về

`Statement`, `PreparedStatement` và `CallableStatement` đều cung cấp cơ chế làm việc với nhiều kết quả qua API của `Statement`.

| API | Ý nghĩa | Giá trị cần kiểm tra |
|---|---|---|
| `Statement.execute(String sql)` | Thực thi câu SQL, cho phép xử lý kết quả đầu tiên dù thuộc loại nào | `true` nếu **kết quả đầu tiên** là `ResultSet`; `false` nếu là update count hoặc không có kết quả |
| `PreparedStatement.execute()` | Thực thi câu SQL đã chuẩn bị và kiểm tra loại kết quả đầu tiên | Có cùng quy ước `true`/`false` như trên |
| `CallableStatement.execute()` | Thực thi stored procedure/function theo hợp đồng được driver hỗ trợ | Có cùng quy ước `true`/`false` như trên |
| `getResultSet()` | Lấy `ResultSet` hiện tại | Trả về `ResultSet` khi kết quả hiện tại là tập hàng; ngược lại là `null` |
| `getUpdateCount()` | Đọc số lượng hàng bị ảnh hưởng ở kết quả hiện tại | Số nguyên **không âm** nếu kết quả hiện tại là update count; `-1` nếu hiện tại là `ResultSet` hoặc không còn kết quả |
| `getMoreResults()` | Chuyển sang kết quả tiếp theo, mặc định đóng `ResultSet` hiện tại | `true` nếu **kết quả kế tiếp** là `ResultSet`; `false` nếu là update count hoặc hết kết quả |

Nhầm lẫn quan trọng nhất là: **`getMoreResults() == false` không có nghĩa chắc chắn đã hết tất cả kết quả.** Giá trị `false` còn có thể báo rằng kết quả tiếp theo là một update count.

Do đó, nếu nhận `false`, phải gọi tiếp `getUpdateCount()`:

```text
getMoreResults() == false
           │
           ▼
    getUpdateCount()
           │
    ┌──────┴────────┐
    ▼               ▼
  >= 0             == -1
    │               │
    ▼               ▼
Có update count    Hết kết quả
```

Quy tắc này áp dụng cả khi `execute()` trả về `false` cho kết quả **đầu tiên**. `getUpdateCount()` có thể trả `0`: đây vẫn là **một update count hợp lệ**, không phải dấu hiệu kết thúc.

## 3. Thuật toán duyệt đúng: đọc kết quả hiện tại, rồi chuyển tiếp

Có thể mô tả thuật toán tổng quát như sau:

```text
hasResultSet = statement.execute(...)

LẶP:
    nếu hasResultSet == true:
        lấy statement.getResultSet()
        duyệt từng hàng bằng resultSet.next()
        đóng ResultSet khi đọc xong
    ngược lại:
        count = statement.getUpdateCount()
        nếu count == -1:
            THOÁT VÒNG LẶP
        xử lý count (kể cả khi count == 0)

    hasResultSet = statement.getMoreResults()
```

Đây là một vòng lặp **theo kết quả**, bên trong có thể chứa vòng lặp **theo hàng** nếu kết quả là `ResultSet`. Trình tự này không bỏ sót update count xuất hiện giữa hai tập hàng.

Một phương thức Java có thể nhận một `Statement` đã được thiết lập và thực thi một câu SQL **cố định, đáng tin cậy**:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public static void processAllResults(Statement statement, String sql)
        throws SQLException {
    boolean hasResultSet = statement.execute(sql);
    int ordinal = 0;

    while (true) {
        ordinal++;

        if (hasResultSet) {
            try (ResultSet rs = statement.getResultSet()) {
                System.out.println("Kết quả " + ordinal + ": ResultSet");

                while (rs.next()) {
                    // Ví dụ này giả định mỗi ResultSet có cột đầu tiên.
                    System.out.println(rs.getObject(1));
                }
            }
        } else {
            int count = statement.getUpdateCount();
            if (count == -1) {
                break; // Không còn kết quả nào.
            }

            System.out.println("Kết quả " + ordinal +
                               ": update count = " + count);
        }

        hasResultSet = statement.getMoreResults();
    }
}
```

Đoạn mã minh họa cách duyệt; nó giả định mỗi tập hàng có ít nhất một cột, và `sql` đến từ mã ứng dụng đã kiểm soát. Không ghép dữ liệu người dùng trực tiếp vào chuỗi SQL; với tham số đầu vào, nên dùng `PreparedStatement` hoặc `CallableStatement` tương ứng.

Lưu ý: biến `ordinal` chỉ đánh số các lần quan sát kết quả. Khi đã đến trạng thái kết thúc, vòng lặp tăng biến này thêm một lần trước khi `break`, nhưng không in thêm kết quả nào. Với logic nghiệp vụ cần lưu số lượng chính xác, có thể tách phép đếm ra sau khi xác nhận kiểu kết quả.

## 4. Ví dụ dùng `CallableStatement` với stored procedure

Một tình huống nhiều kết quả dễ gặp là stored procedure trả về các tập hàng cùng với số đếm cập nhật. Giả sử cơ sở dữ liệu đã có procedure `build_customer_report` nhận `customer_id` và driver hỗ trợ trả nhiều kết quả qua JDBC.

Ví dụ Java sau **không giả định số lượng hoặc loại kết quả cố định**. Mỗi `ResultSet` có thể có danh sách cột khác nhau, vì vậy dùng `ResultSetMetaData` để đọc các cột hiện có:

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerReportRunner {
    private final DataSource dataSource;

    public CustomerReportRunner(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void run(long customerId) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             CallableStatement call = connection.prepareCall(
                     "{call build_customer_report(?)}")) {

            call.setLong(1, customerId);

            boolean hasResultSet = call.execute();
            int resultNumber = 0;

            while (true) {
                if (hasResultSet) {
                    resultNumber++;
                    System.out.println("ResultSet #" + resultNumber);

                    try (ResultSet rs = call.getResultSet()) {
                        ResultSetMetaData metadata = rs.getMetaData();
                        int columnCount = metadata.getColumnCount();

                        while (rs.next()) {
                            for (int column = 1; column <= columnCount; column++) {
                                String label = metadata.getColumnLabel(column);
                                Object value = rs.getObject(column);
                                System.out.print(label + "=" + value + " ");
                            }
                            System.out.println();
                        }
                    }
                } else {
                    int count = call.getUpdateCount();
                    if (count == -1) {
                        break;
                    }

                    resultNumber++;
                    System.out.println("Update count #" + resultNumber +
                                       " = " + count);
                }

                hasResultSet = call.getMoreResults();
            }
        }
    }
}
```

`DataSource` được giả định đã cấu hình từ trước. Procedure, cú pháp khai báo procedure và khả năng trả nhiều kết quả phụ thuộc DBMS; một số driver có quy tắc riêng khi gọi procedure hoặc khi xử lý tham số `OUT`.

Mã trên có ba đặc điểm cần nhớ:

1. **Chỉ gọi `execute()` một lần.** Mọi lần `getMoreResults()` tiếp theo đều đọc từ cùng lần thực thi đó.
2. **Duyệt hết và đóng `ResultSet` hiện tại** trước khi chuyển sang kết quả tiếp theo. Điều này tránh giữ tài nguyên không cần thiết.
3. **Kiểm tra `getUpdateCount() == -1` khi `hasResultSet` là `false`**, để phân biệt kết quả cập nhật với trạng thái kết thúc.

`ResultSetMetaData.getColumnCount()` trả về số cột; chỉ số cột của JDBC bắt đầu từ **1**. Nếu hai tập hàng có cấu trúc khác nhau, đọc metadata riêng cho từng `ResultSet` sẽ tránh việc giả định sai rằng các tập kết quả đều có cùng số cột hoặc tên cột.

## 5. Lần theo từng bước một chuỗi kết quả

Giả sử procedure vừa nêu lần lượt trả về:

- Tập hàng A: hai khách hàng.
- Update count: `3` hàng vừa cập nhật.
- Tập hàng B: một hàng thống kê.
- Sau đó không còn kết quả.

| Thao tác | Kết quả trả về | Kết quả hiện tại | Xử lý |
|---|---|---|---|
| `execute()` | `true` | `ResultSet A` | `getResultSet()` và đọc hai hàng |
| `getMoreResults()` lần 1 | `false` | Update count `3` | `getUpdateCount()` trả `3`; chưa được dừng |
| `getMoreResults()` lần 2 | `true` | `ResultSet B` | `getResultSet()` và đọc một hàng |
| `getMoreResults()` lần 3 | `false` | Không còn kết quả | `getUpdateCount()` trả `-1`; kết thúc |

Nếu update count giữa hai tập hàng là **`0`**, vẫn phải xử lý như một kết quả cập nhật hợp lệ. Chỉ **`-1` ở vị trí không phải `ResultSet`** mới cho phép kết luận đã hết kết quả theo mô hình này.

Một chuỗi khác có thể **bắt đầu bằng update count**. Trong trường hợp đó, `execute()` trả `false`, nhưng `getUpdateCount()` trả một số không âm. Khi xử lý xong, chương trình tiếp tục gọi `getMoreResults()` để tìm kết quả sau. Đừng giả định rằng lần thực thi đầu tiên luôn là `ResultSet`.

## 6. Vòng đời của `ResultSet` khi gọi `getMoreResults()`

Theo hợp đồng JDBC, **`getMoreResults()` không tham số sẽ đóng `ResultSet` hiện tại** (nếu có) trước khi chuyển sang kết quả kế tiếp. Nếu ứng dụng cần đọc tiếp dữ liệu của tập hàng cũ, nó phải hoàn thành việc đó trước khi gọi phương thức này hoặc chọn một chiến lược giữ kết quả phù hợp.

`Statement` còn cung cấp phiên bản có tham số:

```java
boolean hasNextResultSet = statement.getMoreResults(
        Statement.CLOSE_CURRENT_RESULT);
```

Các hằng số điều khiển cách xử lý kết quả cũ:

| Tham số `getMoreResults(int)` | Hành vi dự kiến |
|---|---|
| `Statement.CLOSE_CURRENT_RESULT` | Đóng `ResultSet` hiện tại trước khi chuyển tiếp; tương đương cách mặc định |
| `Statement.KEEP_CURRENT_RESULT` | Giữ `ResultSet` hiện tại mở khi chuyển tiếp, nếu driver hỗ trợ |
| `Statement.CLOSE_ALL_RESULTS` | Đóng mọi `ResultSet` đang mở từ statement này trước khi chuyển tiếp |

Không phải driver nào cũng hỗ trợ giữ **nhiều `ResultSet` mở đồng thời** từ cùng một statement. Có thể kiểm tra bằng `connection.getMetaData().supportsMultipleOpenResults()`. Nếu driver không hỗ trợ, phương thức có thể ném `SQLFeatureNotSupportedException` khi yêu cầu tính năng chưa triển khai.

Trong phần lớn mã ứng dụng, nên **đọc hết và đóng từng `ResultSet` ngay**, sau đó chuyển tiếp. Tránh dùng `KEEP_CURRENT_RESULT` chỉ để giữ dữ liệu lâu hơn khi không có nhu cầu thật sự. Nếu phải giữ kết quả cũ, ứng dụng cần quản lý và đóng tất cả `ResultSet` đã giữ, không chỉ tập cuối cùng.

## 7. Kiểm tra khả năng driver và cơ sở dữ liệu hỗ trợ

Không phải mọi cơ sở dữ liệu, driver hoặc loại câu lệnh đều có thể trả nhiều kết quả trong một lần `execute()`.

JDBC cung cấp các phương thức `DatabaseMetaData` giúp khảo sát khả năng hỗ trợ:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public static void printMultiResultCapabilities(Connection connection)
        throws SQLException {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println("Nhiều ResultSet từ một lần execute: " +
            metadata.supportsMultipleResultSets());
    System.out.println("Giữ nhiều ResultSet mở cùng lúc: " +
            metadata.supportsMultipleOpenResults());
}
```

Hai khả năng này **khác nhau**:

- `supportsMultipleResultSets()` liên quan tới việc nhận **nhiều tập kết quả** từ cùng một lần thực thi.
- `supportsMultipleOpenResults()` liên quan tới việc **giữ nhiều tập kết quả mở đồng thời** khi dịch chuyển giữa các kết quả.

Đối với một ứng dụng cần kết quả hỗn hợp gồm `ResultSet` và update count, vẫn phải xét hành vi thực tế của stored procedure/câu lệnh cùng driver, kể cả khi metadata báo có hỗ trợ nhiều kết quả. Có driver phát sinh hoặc bỏ qua một số update count tùy cấu hình; không nên dựa vào số vị trí kết quả cố định khi yêu cầu nghiệp vụ không bảo đảm điều đó.

Nếu thực sự cần chạy nhiều câu lệnh SQL độc lập, một giải pháp khác là **thực thi từng câu lệnh bằng `PreparedStatement` riêng**, quản lý giao dịch theo yêu cầu. Đừng suy từ việc driver hỗ trợ `getMoreResults()` ra rằng có thể ghép một chuỗi `SELECT ...; UPDATE ...; SELECT ...` vào một lệnh và chạy như nhau trên mọi hệ quản trị. Việc chấp nhận nhiều câu lệnh trong một chuỗi SQL và các thiết lập an toàn liên quan là **tính năng riêng của driver/DBMS**.

## 8. Phân biệt với `executeQuery()`, `executeUpdate()` và batch

| API | Trường hợp sử dụng chính | Quan hệ với nhiều kết quả |
|---|---|---|
| `executeQuery()` | Khi mong đợi một kết quả dạng bảng | Trả `ResultSet` cho lần thực thi thông thường; không phải lựa chọn tổng quát cho chuỗi hỗn hợp |
| `executeUpdate()` | Khi mong đợi số hàng bị ảnh hưởng, ví dụ `INSERT`/`UPDATE`/`DELETE` | Trả update count cho lệnh phù hợp; không phải cách duyệt một chuỗi nhiều loại kết quả |
| `execute()` | Khi loại kết quả đầu tiên không biết trước hoặc câu lệnh có thể trả nhiều kết quả | Kết hợp `getResultSet()`, `getUpdateCount()` và `getMoreResults()` |
| `executeBatch()` | Thực thi một nhóm lệnh đã được `addBatch()` | Trả một mảng update count hoặc các mã trạng thái theo hợp đồng batch; không duyệt bằng `getMoreResults()` |

Một `ResultSet` có **nhiều hàng** không phải là **nhiều `ResultSet`**. Ví dụ, truy vấn `SELECT * FROM orders` trả hàng nghìn bản ghi vẫn thường chỉ là **một** kết quả `ResultSet`; vòng lặp xử lý đúng là `while (rs.next())`.

Ngược lại, stored procedure có thể phát ra hai `SELECT` khác nhau, tạo hai tập kết quả độc lập; khi driver hỗ trợ, ta dùng `getMoreResults()` để đi từ tập thứ nhất sang tập thứ hai.

Với hệ thống có thể cập nhật một số lượng hàng vượt giới hạn `int`, JDBC còn có API như `getLargeUpdateCount()` (trả `long`) và `executeLargeUpdate()`. Khi xử lý update count rất lớn, phải kiểm tra driver/JDBC version và chọn API thích hợp thay vì giả định mọi số đếm đều vừa `int`.

## 9. Các lỗi triển khai dễ gặp

| Mã hoặc giả định sai | Hệ quả | Cách khắc phục |
|---|---|---|
| `while (statement.getMoreResults()) { ... }` | Vòng lặp dừng ngay khi kết quả kế tiếp là update count | Sau mỗi `false`, kiểm tra `getUpdateCount()`; chỉ kết thúc khi `-1` |
| `if (!statement.execute(sql)) return;` | Bỏ mất update count đầu tiên hoặc các kết quả phía sau | Kiểm tra `getUpdateCount()` khi `execute()` trả `false` |
| `if (statement.getUpdateCount() == 0) break;` | Bỏ mất các kết quả sau một update count bằng `0` | `0` là giá trị hợp lệ; dấu kết thúc là `-1` |
| Chỉ dùng `rs.next()` để sang “bảng kết quả thứ hai” | `next()` chỉ duyệt hàng trong một tập kết quả | Dùng `getMoreResults()` để sang kết quả khác |
| Giữ `ResultSet` cũ rồi gọi `getMoreResults()` mặc định | `ResultSet` cũ có thể đã bị đóng | Đọc/đóng tập cũ trước, hoặc dùng cơ chế giữ kết quả nếu được hỗ trợ |
| Giả định mọi driver hỗ trợ nhiều kết quả | Procedure hoạt động trên DB này nhưng khác trên DB khác | Kiểm tra metadata, tài liệu driver và thử nghiệm tích hợp |
| Ghép SQL động từ đầu vào người dùng để tạo nhiều lệnh | Nguy cơ SQL injection, hành vi phụ thuộc driver | Dùng lệnh đã kiểm soát và ràng buộc giá trị bằng `PreparedStatement` |
| Quên đóng `ResultSet`/`Statement`/`Connection` | Tốn tài nguyên cursor, statement và connection pool | Dùng `try-with-resources`; đóng từng kết quả khi không còn cần |

## 10. Bài tập lần theo `getMoreResults()`

Giả sử một lần gọi stored procedure tạo ra chuỗi sau:

```text
Kết quả 1: update count = 0
Kết quả 2: ResultSet gồm 3 hàng
Kết quả 3: update count = 5
Kết quả 4: ResultSet rỗng (0 hàng)
Kết thúc
```

Hãy dự đoán giá trị trả về của các lời gọi quan trọng:

| Lời gọi | Trả về | Giải thích |
|---|---|---|
| `execute()` | `false` | Kết quả đầu tiên là update count `0` |
| `getUpdateCount()` sau `execute()` | `0` | Có một kết quả cập nhật hợp lệ |
| `getMoreResults()` lần 1 | `true` | Sang `ResultSet` có 3 hàng; dùng `next()` để duyệt |
| `getMoreResults()` lần 2 | `false` | Sang update count `5`; vẫn chưa hết |
| `getUpdateCount()` sau lần 2 | `5` | Xử lý số hàng cập nhật |
| `getMoreResults()` lần 3 | `true` | Sang `ResultSet` rỗng; `getResultSet()` vẫn là một tập kết quả hợp lệ |
| `rs.next()` đầu tiên trên tập thứ 4 | `false` | Không có hàng trong tập hiện tại, **không có nghĩa** đã hết chuỗi kết quả |
| `getMoreResults()` lần 4 | `false` | Sau tập kết quả rỗng không còn tập kết quả tiếp |
| `getUpdateCount()` sau lần 4 | `-1` | Đã kết thúc chuỗi kết quả |

**Ghi nhớ:** Với nhiều kết quả trong JDBC, `execute()` và `getMoreResults()` chỉ cho biết **kết quả hiện tại có phải `ResultSet` hay không**. Khi nhận `true`, đọc tập hàng qua `getResultSet()` và `next()`. Khi nhận `false`, đọc `getUpdateCount()` để phân biệt **một update count hợp lệ** với **hết kết quả (`-1`)**. Luôn quản lý vòng đời `ResultSet` và kiểm tra khả năng hỗ trợ của driver trước khi dựa vào hành vi nhiều kết quả trong ứng dụng.
