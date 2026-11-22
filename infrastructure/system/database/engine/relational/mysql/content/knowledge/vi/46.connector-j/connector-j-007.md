# cachePrepStmts, giới hạn prepared statement và vòng đời tài nguyên

## Mục tiêu

MySQL Connector/J là JDBC driver cho Java. Khi ứng dụng tạo nhiều `PreparedStatement` với cùng câu SQL, việc phân tích và chuẩn bị lặp lại có thể tạo thêm chi phí. Connector/J có cơ chế cache prepared statement để tái sử dụng thông tin chuẩn bị, và có thể tái sử dụng server-side prepared statement khi cấu hình phù hợp. Tuy nhiên, cache được giữ theo từng kết nối vật lý, còn prepared statement phía server tiêu thụ tài nguyên trên toàn instance MySQL. Cấu hình cache quá lớn cùng connection pool đông có thể đẩy máy chủ tới giới hạn `max_prepared_stmt_count`.

Bài học thuộc module **DATABASE_MYSQL**, bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Bài này tập trung vào cách cấu hình `cachePrepStmts`, hiểu giới hạn prepared statement, quản lý vòng đời JDBC và điều chỉnh cache theo số kết nối thực tế.

Sau bài học, bạn có thể:

- Phân biệt prepared statement mô phỏng ở client và prepared statement phía MySQL server.
- Cấu hình `cachePrepStmts`, `prepStmtCacheSize`, `prepStmtCacheSqlLimit` và `useServerPrepStmts`.
- Ước lượng ảnh hưởng của cache trên mỗi kết nối tới giới hạn toàn server.
- Đóng `Connection`, `PreparedStatement` và `ResultSet` đúng cách trong Java.
- Theo dõi số prepared statement, phát hiện rò rỉ và chọn kích thước cache phù hợp.

## 1. PreparedStatement trong JDBC

`PreparedStatement` biểu diễn một câu SQL có tham số. Ứng dụng tạo câu SQL với placeholder `?`, gán giá trị qua setter rồi thực thi. Cách này giúp tách cấu trúc SQL khỏi dữ liệu đầu vào, hỗ trợ tái sử dụng và tránh ghép trực tiếp giá trị người dùng vào chuỗi SQL.

```java
String sql = "SELECT order_id, status FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Xử lý kết quả trong phạm vi ResultSet còn mở.
        }
    }
}
```

Placeholder chỉ dùng cho giá trị, không dùng để thay tên bảng, tên cột, từ khóa hoặc hướng sắp xếp. Nếu cần chọn cột hoặc sort direction động, dùng danh sách cho phép (allowlist) do ứng dụng kiểm soát rồi ghép identifier đã xác thực vào SQL. Không đưa trực tiếp chuỗi từ request vào phần cấu trúc câu lệnh.

Prepared statement không phải query result cache. Nó không lưu kết quả truy vấn để lần gọi sau trả dữ liệu cũ; MySQL vẫn thực thi câu lệnh và đọc dữ liệu theo transaction, isolation level và trạng thái hiện tại.

## 2. Client-side và server-side prepared statement

Connector/J có thể xử lý prepared statement theo hai cách:

- **Client-side emulation:** driver giữ cấu trúc câu lệnh và gửi SQL đã thay tham số tới server. Server không tạo một server prepared statement riêng cho mỗi câu lệnh theo giao thức prepare/execute.
- **Server-side prepared statement:** driver gửi yêu cầu prepare tới MySQL. Server tạo statement gắn với session kết nối, sau đó nhận giá trị tham số trong các lần execute.

Thuộc tính `useServerPrepStmts=true` yêu cầu Connector/J sử dụng server-side prepared statement khi câu lệnh và phiên bản hỗ trợ. Một số câu lệnh hoặc tính năng có thể không hỗ trợ server-side prepare và driver có thể xử lý theo cơ chế tương thích tùy cấu hình, phiên bản.

Server-side prepare có thể giảm việc gửi lại và phân tích SQL ở một số workload, đồng thời thay đổi cách truyền kiểu dữ liệu và metadata. Nó cũng tạo statement object trên server, vì vậy số lượng bị giới hạn bởi `max_prepared_stmt_count`. Không bật chỉ vì tên gọi nghe tối ưu; hãy benchmark với SQL và driver thực tế.

## 3. `cachePrepStmts` và các thuộc tính liên quan

Connector/J cung cấp một số thuộc tính chính:

| Thuộc tính | Vai trò |
|---|---|
| `cachePrepStmts` | Bật/tắt cache prepared statement ở Connector/J |
| `prepStmtCacheSize` | Số entry tối đa trong cache của mỗi kết nối vật lý |
| `prepStmtCacheSqlLimit` | Giới hạn độ dài SQL được phép đưa vào cache |
| `useServerPrepStmts` | Yêu cầu dùng prepared statement phía server khi hỗ trợ |

Ví dụ URL kết nối:

```text
jdbc:mysql://db.example.net:3306/app?cachePrepStmts=true&prepStmtCacheSize=250&prepStmtCacheSqlLimit=2048&useServerPrepStmts=true
```

Ví dụ cấu hình trên là điểm bắt đầu để thử nghiệm, không phải con số tối ưu cho mọi ứng dụng. Tên thuộc tính và giá trị mặc định có thể khác theo phiên bản Connector/J; kiểm tra tài liệu đúng phiên bản driver đang triển khai.

`cachePrepStmts=true` cho phép driver giữ các prepared statement phù hợp để tái sử dụng. `prepStmtCacheSize` đặt giới hạn entry trên từng kết nối vật lý, không phải một cache chung cho toàn ứng dụng. `prepStmtCacheSqlLimit` loại các câu SQL quá dài khỏi cache; câu lệnh vẫn có thể chạy nhưng không được giữ làm entry cache.

Khi bật server-side prepare, cache có thể giữ server prepared statement sau khi ứng dụng gọi `close()` trên đối tượng JDBC. Driver có thể tái sử dụng statement đó cho lần gọi sau trên cùng kết nối vật lý. Khi entry bị loại khỏi cache hoặc kết nối vật lý bị đóng, server-side statement tương ứng được giải phóng theo cơ chế của driver.

## 4. Cache gắn với kết nối vật lý

Prepared statement phía server thuộc về session MySQL đã tạo nó. Một statement trên connection A không thể được dùng trực tiếp từ connection B. Vì vậy, cache của Connector/J được tổ chức theo kết nối vật lý, thường là connection do connection pool quản lý.

Điều này có một hệ quả quan trọng: tổng số prepared statement tiềm năng tăng theo số kết nối vật lý đang hoạt động và kích thước cache mỗi kết nối. Ví dụ, 80 kết nối vật lý với giới hạn cache 200 entry mỗi kết nối tạo ra sức chứa lý thuyết tới 16.000 entry, nếu các entry đó đều được sử dụng và là server-side statement. Đây chỉ là phép ước lượng sức chứa; cache không được lấp đầy ngay khi tạo connection và số thực tế phụ thuộc workload, eviction, kết nối đang hoạt động và driver.

Nếu có nhiều instance ứng dụng, phải cộng số kết nối vật lý từ tất cả instance vào phép tính. Connection pool có thể giữ connection idle trong thời gian dài, đồng nghĩa cache trên connection đó vẫn tồn tại và server-side prepared statement có thể tiếp tục chiếm quota.

Không chia `prepStmtCacheSize` theo tổng ứng dụng như thể đó là một con số toàn cục. Hãy tính theo từng pool, số replica ứng dụng, số kết nối tối đa và giới hạn trên server.

## 5. Giới hạn `max_prepared_stmt_count` trên MySQL

MySQL đặt giới hạn toàn server cho số prepared statement đồng thời bằng biến `max_prepared_stmt_count`. Giới hạn này bao gồm prepared statement server-side từ các session và ứng dụng khác nhau. Giá trị mặc định thường gặp là `16382`, nhưng phải kiểm tra giá trị thực tế của instance vì cấu hình có thể đã thay đổi theo môi trường hoặc phiên bản.

```sql
SHOW GLOBAL VARIABLES LIKE 'max_prepared_stmt_count';
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
```

`Prepared_stmt_count` cho biết số prepared statement hiện đang được server theo dõi. Nếu chạm giới hạn, lệnh prepare mới có thể thất bại với lỗi MySQL `ER_MAX_PREPARED_STMT_COUNT_REACHED` (thường là error 1461). Khi đó, ứng dụng có thể gặp lỗi dù từng connection riêng lẻ vẫn hoạt động.

Có thể kiểm tra các statement đang được Performance Schema ghi nhận:

```sql
SELECT OWNER_THREAD_ID, STATEMENT_ID, SQL_TEXT
FROM performance_schema.prepared_statements_instances;
```

Bảng `performance_schema.prepared_statements_instances` cần Performance Schema được bật và quyền đọc phù hợp. Dữ liệu SQL có thể chứa thông tin nhạy cảm; hạn chế quyền truy cập và không đưa truy vấn có dữ liệu riêng tư vào log không bảo vệ.

Nếu số statement tăng dần theo thời gian và không giảm khi workload ngừng, hãy kiểm tra rò rỉ statement, connection không được đóng, pool giữ quá nhiều connection hoặc cache per-connection quá lớn. Tăng `max_prepared_stmt_count` chỉ nên là quyết định sau khi đã ước lượng bộ nhớ và tải, không phải cách che một lỗi vòng đời.

## 6. Cách tính ngân sách cache

Ước lượng ban đầu cho server-side statement được cache:

```text
Potential cached statements
  ~= total physical connections across all app pools
     x prepStmtCacheSize per connection
```

Ví dụ một dịch vụ có 3 instance ứng dụng, mỗi instance cho phép tối đa 40 kết nối vật lý, và cache size là 100:

```text
3 x 40 x 100 = 12,000 potential cache entries
```

Con số này chưa tính prepared statement đang mở nhưng chưa được trả vào cache, statement từ batch/job/monitoring khác, các dịch vụ dùng chung MySQL và phần dung lượng dự phòng cần thiết. Nó cũng không có nghĩa server sẽ lập tức tạo 12.000 statement; entry chỉ được tạo khi workload dùng các câu SQL tương ứng.

Hãy dành khoảng trống đủ lớn dưới `max_prepared_stmt_count` cho tải tăng đột biến, triển khai rolling, job nền và các session quản trị. Đặc biệt, trong lúc deploy có thể tồn tại đồng thời connection của phiên bản ứng dụng cũ và mới.

## 7. SQL ổn định giúp cache hiệu quả

Cache hoạt động tốt nhất khi cùng một câu SQL được tái sử dụng. Giá trị tham số nên được truyền bằng setter thay vì ghép vào SQL:

```java
String sql = "SELECT order_id FROM orders WHERE customer_id = ? AND status = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);
    try (ResultSet resultSet = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
```

Nếu ghép giá trị trực tiếp vào SQL, mỗi giá trị có thể tạo một chuỗi SQL khác nhau và làm giảm khả năng cache. Whitespace, comment hoặc cách tạo câu lệnh không nhất quán cũng có thể tạo nhiều key cache khác nhau.

Câu lệnh có độ dài vượt `prepStmtCacheSqlLimit` không được cache theo giới hạn đó. Câu SQL động như `IN (?, ?, ?)` với số placeholder thay đổi cũng tạo các dạng câu lệnh khác nhau. Nếu có hàng trăm biến thể hiếm khi lặp lại, tăng cache size có thể chỉ làm tăng bộ nhớ và quota mà không tăng hit rate.

Không cố ép mọi SQL vào một câu lệnh khổng lồ để tăng tái sử dụng. Hãy giữ câu lệnh dễ hiểu, tham số hóa giá trị và chỉ chuẩn hóa các mẫu SQL thực sự lặp lại.

## 8. Vòng đời `Connection`, `PreparedStatement` và `ResultSet`

JDBC yêu cầu ứng dụng đóng tài nguyên sau khi dùng. Cách đơn giản và đáng tin cậy trong Java là `try-with-resources`:

```java
String sql = "UPDATE inventory SET quantity = quantity - ? WHERE sku = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, amount);
    statement.setString(2, sku);

    int updatedRows = statement.executeUpdate();
    if (updatedRows != 1) {
        throw new IllegalStateException("Unexpected inventory row count");
    }
}
```

Với truy vấn trả dữ liệu, đóng `ResultSet` trong phạm vi `PreparedStatement`:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT sku, quantity FROM inventory WHERE sku = ?")) {
    statement.setString(1, sku);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            int quantity = resultSet.getInt("quantity");
            // Chuyển dữ liệu cần thiết ra object ứng dụng.
        }
    }
}
```

Đóng `ResultSet` giải phóng cursor và tài nguyên liên quan. Đóng `PreparedStatement` cho phép Connector/J trả statement vào cache nếu phù hợp, hoặc giải phóng statement. Đóng `Connection` trả logical connection về pool hoặc đóng session vật lý nếu không dùng pool. Không bỏ qua `close()` vì đã bật cache.

Không giữ `ResultSet` hoặc `PreparedStatement` trong field toàn cục để dùng lại giữa các request. Statement gắn với connection, không được thiết kế để nhiều thread dùng chung đồng thời. Mỗi đơn vị công việc nên lấy connection, tạo statement, đọc kết quả, đóng statement rồi trả connection.

Với connection pool, gọi `Connection.close()` thường trả logical connection về pool thay vì đóng socket ngay. Pool có thể giữ session vật lý cùng statement cache để tái sử dụng. Khi pool loại bỏ connection vật lý, driver mới giải phóng toàn bộ tài nguyên session trên server.

## 9. Transaction và statement cache

Prepared statement cache không thay đổi ranh giới transaction. Các câu lệnh vẫn chạy trong transaction của connection hiện tại, tuân theo `autocommit`, isolation level và khóa InnoDB.

Ví dụ transaction:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        try (PreparedStatement debit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? WHERE account_id = ?");
             PreparedStatement credit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {
            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromAccount);
            debit.executeUpdate();

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toAccount);
            credit.executeUpdate();
        }
        connection.commit();
    } catch (SQLException exception) {
        try {
            connection.rollback();
        } catch (SQLException rollbackException) {
            exception.addSuppressed(rollbackException);
        }
        throw exception;
    }
}
```

Đây là cấu trúc minh họa; ứng dụng thực tế cần kiểm tra số hàng bị ảnh hưởng, xác thực số dư và xử lý lỗi commit chưa xác định. Không gọi `setAutoCommit(true)` một cách mù quáng trong `finally`: JDBC có thể commit transaction đang mở khi bật lại auto-commit. Pool thường khôi phục trạng thái connection khi trả về; nếu rollback hoặc reset session thất bại, hãy đánh dấu và loại connection vật lý khỏi pool bằng cơ chế của pool đang dùng.

## 10. Cấu hình pool và cache phối hợp với nhau

Connection pool quyết định số session vật lý được mở tới MySQL. Statement cache nhân mức tiêu thụ trên từng session. Vì vậy, phải điều chỉnh pool và cache cùng nhau.

| Tăng giá trị | Lợi ích có thể có | Chi phí/rủi ro |
|---|---|---|
| `maximumPoolSize` | Nhiều request có thể lấy connection đồng thời | Tăng session, memory, thread và tổng cache entry |
| `prepStmtCacheSize` | Giữ nhiều mẫu SQL hơn trên mỗi connection | Tăng số server-side statement có thể tồn tại và bộ nhớ cache |
| `prepStmtCacheSqlLimit` | Cache được câu SQL dài hơn | Tăng bộ nhớ giữ SQL text và số entry có thể được lưu |
| `useServerPrepStmts` | Dùng prepare/execute phía server cho câu lệnh hỗ trợ | Tạo statement phía server, chịu giới hạn toàn cục và có thể khác hành vi driver |

Không đặt pool size tối đa chỉ dựa trên số thread ứng dụng. Xác định số truy vấn đồng thời thực sự, thời gian giữ connection, khả năng xử lý của MySQL và giới hạn tổng kết nối. Nếu tăng số connection nhưng database đã bão hòa CPU hoặc I/O, throughput có thể không tăng mà chỉ tăng contention.

## 11. Theo dõi cache và phát hiện rò rỉ

Đo trước và sau khi bật cache bằng workload đại diện. Theo dõi:

- `Prepared_stmt_count` so với `max_prepared_stmt_count`.
- Số connection đang mở, active, idle và pending trong từng pool.
- Số lỗi prepare, lỗi 1461 và lỗi đóng connection.
- Latency prepare/execute, throughput và CPU MySQL.
- Hit/miss hoặc chỉ số cache do phiên bản Connector/J cung cấp nếu có.
- Số statement đang mở trong `performance_schema.prepared_statements_instances`.

Truy vấn giám sát cơ bản:

```sql
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
SHOW GLOBAL VARIABLES LIKE 'max_prepared_stmt_count';

SELECT COUNT(*) AS server_prepared_statements
FROM performance_schema.prepared_statements_instances;
```

Để điều tra một session cụ thể, liên kết `OWNER_THREAD_ID` từ `prepared_statements_instances` với thread trong Performance Schema. Quyền truy cập và các cột có thể khác theo phiên bản MySQL; chỉ cấp quyền giám sát cần thiết.

Dấu hiệu rò rỉ thường gặp:

- `Prepared_stmt_count` tăng liên tục dù tải ổn định và không trở về mức nền sau khi request kết thúc.
- Connection pool liên tục tạo connection mới vì connection cũ bị lỗi hoặc không được trả lại.
- Code tạo statement trong vòng lặp nhưng không đóng.
- Kết quả truy vấn được giữ mở lâu khiến statement và connection không được giải phóng.
- Nhiều mẫu SQL gần giống nhau nhưng khác literal, comment hoặc whitespace làm cache phân mảnh.

Cache eviction là một phần của cơ chế quản lý, nhưng không thay thế đóng statement. Hãy dùng connection leak detection của pool, log thời gian mượn connection và kiểm tra đường code có `try-with-resources`.

## 12. Quy trình tuning thực tế

1. Ghi lại phiên bản Connector/J, MySQL, pool, số instance ứng dụng và cấu hình connection tối đa.
2. Kiểm tra `max_prepared_stmt_count` và `Prepared_stmt_count` trong giờ tải cao.
3. Xác định các SQL mẫu lặp lại, độ dài SQL và số lần thực thi; bỏ các mẫu hiếm khi tái sử dụng khỏi phạm vi cache nếu cần.
4. Bắt đầu với cache size vừa phải trên mỗi connection; tính tổng sức chứa tiềm năng trên tất cả pool.
5. Benchmark riêng `cachePrepStmts` và `useServerPrepStmts` với cùng workload, không đổi nhiều biến cùng lúc.
6. So sánh latency, throughput, CPU, số prepared statement, lỗi và bộ nhớ.
7. Thử tải tăng đột biến và rolling deployment để xem tổng connection/cache có vượt quota không.
8. Điều chỉnh cache size, SQL limit hoặc pool size; giữ khoảng trống an toàn dưới giới hạn server.
9. Ghi lại cấu hình đã chọn, lý do và ngưỡng cảnh báo để vận hành.

Không tối ưu dựa trên một truy vấn đơn lẻ hoặc một lần chạy ngắn. Cache có thể giúp workload có nhiều lần lặp SQL, nhưng ít tác dụng với SQL động hoặc truy vấn chỉ chạy một lần. Luôn đo trong điều kiện gần production.

## 13. Những lỗi thường gặp

- **Bật cache nhưng không đóng statement:** cache không thể tái sử dụng statement chưa được trả lại. Dùng `try-with-resources`.
- **Nhầm cache per-connection là cache toàn cục:** tổng entry có thể nhân với số connection của mọi instance. Tính ngân sách trên toàn server.
- **Đặt cache size quá lớn:** connection pool giữ hàng nghìn server-side statement. Bắt đầu nhỏ và đo `Prepared_stmt_count`.
- **SQL luôn khác nhau:** literal được ghép vào chuỗi khiến cache miss. Dùng placeholder cho giá trị và giữ SQL template ổn định.
- **SQL dài vượt cache limit:** statement chạy nhưng không được cache. Kiểm tra `prepStmtCacheSqlLimit` và chỉ tăng khi có lợi ích đo được.
- **Cho rằng server-side prepare luôn nhanh hơn:** overhead và kiểu workload có thể làm kết quả khác. Benchmark `useServerPrepStmts`.
- **Giữ statement giữa các thread hoặc connection:** statement gắn với session và không an toàn để chia sẻ tùy tiện. Tạo statement trong phạm vi công việc.
- **Tăng `max_prepared_stmt_count` để che rò rỉ:** quota cao hơn không sửa vòng đời sai. Tìm nguyên nhân và tính lại giới hạn.
- **Không theo dõi rolling deployment:** pool cũ và mới cùng hoạt động có thể làm số connection/statement tăng tạm thời. Đưa giai đoạn deploy vào bài kiểm tra tải.

## 14. Bài tập thực hành

Trong một ứng dụng Java dùng MySQL Connector/J và connection pool:

1. Ghi nhận phiên bản Connector/J, loại pool, maximum pool size và giá trị `max_prepared_stmt_count` của MySQL.
2. Tạo một endpoint chạy lặp lại cùng một câu `SELECT ... WHERE id = ?` và một câu `UPDATE` có tham số.
3. Chạy benchmark với cache tắt, sau đó bật `cachePrepStmts=true` với cache size nhỏ.
4. Thử thêm `useServerPrepStmts=true`; so sánh latency, throughput và `Prepared_stmt_count`.
5. Tăng số connection pool và quan sát số prepared statement tiềm năng khi nhiều connection được sử dụng.
6. Tạm thời tạo một nhánh code không đóng statement trong môi trường thử nghiệm để quan sát dấu hiệu rò rỉ, sau đó sửa bằng `try-with-resources`.
7. Thử SQL dài hơn `prepStmtCacheSqlLimit` và SQL có nhiều biến thể placeholder; quan sát ảnh hưởng đến cache.
8. Kiểm tra sau khi connection được trả về pool và sau khi pool đóng connection vật lý.

**Tiêu chí hoàn thành:** giải thích được cache nằm ở phạm vi connection nào, tính được ngân sách prepared statement trên toàn server, mọi tài nguyên JDBC được đóng đúng cách và cấu hình được chọn dựa trên số đo thực tế.

## Kết luận

`cachePrepStmts` có thể giảm chi phí lặp lại khi ứng dụng thường xuyên chạy cùng mẫu SQL, nhưng cache gắn với từng kết nối vật lý và server-side prepared statement dùng chung giới hạn toàn MySQL instance. Hãy phối hợp cache size với connection pool, SQL limit và `max_prepared_stmt_count`; đóng `ResultSet`, `PreparedStatement` và `Connection` bằng `try-with-resources`; sau đó đo hit/miss, số statement và hiệu năng trước khi áp dụng production.
