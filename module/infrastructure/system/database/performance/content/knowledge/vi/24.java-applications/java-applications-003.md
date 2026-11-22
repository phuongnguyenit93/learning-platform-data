# PreparedStatement, tham số liên kết và tái sử dụng câu lệnh

Ứng dụng Java thường gửi cùng một câu SQL nhiều lần với các giá trị khác nhau: tìm đơn hàng theo mã, cập nhật tồn kho, ghi từng sự kiện hoặc lấy danh sách theo tenant. Nếu ứng dụng ghép giá trị vào chuỗi SQL rồi gửi lại mỗi lần, nó vừa tạo rủi ro SQL injection vừa làm câu lệnh thay đổi liên tục. JDBC cung cấp PreparedStatement để giữ cấu trúc SQL ổn định và truyền giá trị qua các tham số liên kết (bind parameters).

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. PreparedStatement giúp chuẩn hóa cách gửi câu lệnh và kiểu dữ liệu, có thể giảm chi phí phân tích cú pháp hoặc hỗ trợ tái sử dụng kế hoạch tùy driver và hệ quản trị. Hiệu quả thực tế còn phụ thuộc vòng đời Connection, connection pool, kiểu tham số, độ lệch dữ liệu và cách database lập kế hoạch.

Bài học này trình bày cách dùng PreparedStatement đúng cách, liên kết giá trị an toàn, tái sử dụng câu lệnh trong một connection, hiểu statement cache và server-side preparation, xử lý tham số có kiểu, batching và kiểm chứng bằng số liệu.

## 1. Statement và PreparedStatement trong JDBC

JDBC có nhiều loại đối tượng thực thi SQL:

- **Statement:** gửi câu SQL hoàn chỉnh, thường được tạo cho câu lệnh không có tham số bind.
- **PreparedStatement:** đại diện cho câu SQL có placeholder vị trí, dùng các phương thức setXxx để gán giá trị trước khi thực thi.
- **CallableStatement:** gọi stored procedure hoặc function theo cơ chế JDBC.

Ví dụ với Statement:

~~~java
String sql = "SELECT order_id FROM orders WHERE customer_id = " + customerId;
try (Statement st = connection.createStatement();
     ResultSet rs = st.executeQuery(sql)) {
    // Đọc kết quả
}
~~~

Cách ghép chuỗi này tạo ra SQL khác nhau theo customerId. Nếu giá trị đến từ request, người dùng có thể chèn cú pháp SQL ngoài dự kiến. Ngay cả khi giá trị đã được kiểm tra, việc tạo nhiều chuỗi SQL khác nhau có thể làm giảm khả năng tái sử dụng statement hoặc plan ở một số hệ thống.

Dùng PreparedStatement:

~~~java
String sql = "SELECT order_id FROM orders WHERE customer_id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Xử lý orderId
        }
    }
}
~~~

Dấu hỏi là placeholder cho một giá trị. Chỉ số tham số trong JDBC bắt đầu từ 1. Ứng dụng gán giá trị bằng setLong, setString hoặc phương thức tương ứng rồi gọi executeQuery, executeUpdate hoặc execute.

### Cấu trúc SQL ổn định

Câu SQL có cấu trúc cố định:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = ?
~~~

Giá trị customer_id được truyền riêng. Điều này giúp database và driver phân biệt cú pháp SQL với dữ liệu. Nó cũng tạo cơ hội để driver hoặc database chuẩn bị, lưu cache hay tái sử dụng một dạng câu lệnh, nhưng JDBC không bảo đảm mọi driver đều thực hiện server-side prepare hoặc dùng lại execution plan.

## 2. Bind parameter bảo vệ dữ liệu và câu lệnh

Bind parameter truyền giá trị như dữ liệu có kiểu. Giá trị chứa dấu nháy, dấu chấm phẩy hoặc chuỗi trông giống SQL vẫn được xử lý như giá trị của tham số, không được ghép thành cú pháp.

Ví dụ tìm người dùng theo email:

~~~java
String sql = "SELECT user_id FROM users WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);

    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý kết quả
    }
}
~~~

Nếu email có nội dung như chuỗi chứa dấu nháy và biểu thức SQL, database vẫn so sánh toàn bộ chuỗi đó với cột email. Nó không thực thi nội dung chuỗi như một phần của câu lệnh.

### Không nối giá trị vào SQL

Không viết:

~~~java
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
~~~

Cũng không tự escape dấu nháy để thay cho bind parameter. Escape thủ công dễ sai với encoding, kiểu dữ liệu, ký tự đặc biệt và quy tắc của từng engine.

### Placeholder chỉ thay thế giá trị

Không thể dùng placeholder để thay tên bảng, tên cột, từ khóa hoặc hướng sắp xếp:

~~~sql
SELECT * FROM ? ORDER BY ? ?
~~~

Các dấu hỏi trong ví dụ không có nghĩa database sẽ thay bằng tên bảng, tên cột và DESC. Bind parameter được dùng cho biểu thức giá trị, không thay thế cấu trúc SQL.

Nếu cần chọn cột sort động, hãy ánh xạ lựa chọn của người dùng vào danh sách identifier được cho phép:

~~~java
Map<String, String> sortColumns = Map.of(
    "created", "created_at",
    "amount", "total_amount"
);

String sortColumn = sortColumns.get(requestedSort);
if (sortColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT order_id, created_at, total_amount " +
             "FROM orders ORDER BY " + sortColumn + " " + direction;
~~~

Trong ví dụ, sortColumn chỉ có thể nhận giá trị từ allowlist do ứng dụng định nghĩa; direction được tạo từ boolean, không lấy trực tiếp một đoạn SQL tùy ý từ request. Những giá trị dữ liệu khác vẫn phải bind bằng PreparedStatement.

## 3. Liên kết tham số đúng kiểu dữ liệu

JDBC cung cấp nhiều phương thức gán tham số. Chọn kiểu phù hợp với kiểu cột để tránh chuyển đổi ngầm và giữ ngữ nghĩa chính xác.

| Kiểu dữ liệu SQL thường gặp | Phương thức JDBC gợi ý |
|---|---|
| SMALLINT / INTEGER | setShort / setInt |
| BIGINT | setLong |
| DECIMAL / NUMERIC | setBigDecimal |
| REAL / FLOAT / DOUBLE | setFloat / setDouble |
| VARCHAR / TEXT | setString |
| BOOLEAN | setBoolean |
| DATE | setDate hoặc setObject(LocalDate) |
| TIMESTAMP | setTimestamp hoặc setObject(LocalDateTime) |
| TIMESTAMP WITH TIME ZONE | setObject với kiểu thời gian phù hợp driver |
| BINARY / VARBINARY | setBytes |
| SQL NULL | setNull hoặc setObject với SQL type rõ ràng |

Các mapping cụ thể phụ thuộc JDBC driver và hệ quản trị. Với JDBC 4.2 trở lên, nhiều driver hỗ trợ java.time qua setObject/getObject, nhưng vẫn cần xác minh phiên bản driver.

Ví dụ gán số tiền:

~~~java
String sql = "INSERT INTO payments (payment_id, amount) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, paymentId);
    ps.setBigDecimal(2, amount);
    ps.executeUpdate();
}
~~~

Dùng BigDecimal cho giá trị tiền tệ và số thập phân cần độ chính xác. Không chuyển qua double nếu nghiệp vụ yêu cầu phép tính thập phân chính xác.

### Kiểu tham số phải tương thích với cột

Giả sử customer_id là BIGINT nhưng ứng dụng bind nó thành chuỗi VARCHAR. Một số engine có thể chuyển đổi ngầm. Nếu phép chuyển đổi được áp dụng lên cột hoặc làm thay đổi cách so sánh, index có thể không được sử dụng như dự kiến.

Hãy bind đúng kiểu, kiểm tra execution plan và quan sát implicit conversion nếu engine cung cấp cảnh báo. Không dựa vào việc database có thể tự ép kiểu để bỏ qua thiết kế kiểu dữ liệu.

### Gán SQL NULL

Không phải mọi giá trị null trong Java đều được driver suy ra đúng kiểu SQL. Khi cần, dùng setNull với JDBC Types:

~~~java
ps.setNull(1, Types.BIGINT);
~~~

Hoặc dùng setObject với SQL type rõ ràng nếu driver hỗ trợ:

~~~java
ps.setObject(1, null, Types.VARCHAR);
~~~

SQL NULL khác chuỗi rỗng và số 0. Điều kiện so sánh với NULL thường phải dùng IS NULL hoặc IS NOT NULL; không viết cột = NULL để tìm giá trị null.

### Ngày giờ và múi giờ

Với dữ liệu thời gian, cần thống nhất ý nghĩa giữa Java, JDBC driver và kiểu cột. LocalDate biểu diễn ngày lịch không có múi giờ; Instant biểu diễn một thời điểm trên timeline; LocalDateTime không mang thông tin múi giờ. Không chọn kiểu chỉ vì chuyển đổi thuận tiện.

Nếu database lưu thời điểm UTC, hãy quy định rõ cách chuyển đổi và kiểm tra driver/session timezone. Với timestamp có múi giờ, xác minh hành vi của hệ quản trị vì cách lưu và hiển thị khác nhau giữa các engine.

## 4. Gán đầy đủ tham số trong mỗi lần thực thi

Một PreparedStatement có thể được thực thi nhiều lần. Giá trị tham số của lần trước có thể còn được giữ trên đối tượng nếu ứng dụng không gán lại. Vì vậy, phải gán tất cả placeholder cần thiết trước mỗi lần execute.

Ví dụ:

~~~java
String sql = "UPDATE inventory SET quantity = ? WHERE sku = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 20);
    ps.setString(2, "SKU-100");
    ps.executeUpdate();

    ps.setInt(1, 35);
    ps.setString(2, "SKU-200");
    ps.executeUpdate();
}
~~~

Mỗi lần gọi đều gán cả hai tham số. Không dựa vào trạng thái còn lại của statement để bỏ qua một lần setXxx.

### clearParameters

JDBC có clearParameters để xóa các giá trị tham số đã gán. Phương thức này hữu ích trong một số luồng tái sử dụng phức tạp, nhưng không thay thế yêu cầu gán đầy đủ tham số. Nếu mọi placeholder đều được gán trước execute, thường không cần gọi clearParameters giữa mỗi lần chạy.

### Không chia sẻ statement đồng thời

PreparedStatement gắn với một Connection và có trạng thái tham số, ResultSet cùng trạng thái thực thi. Không chia sẻ cùng một đối tượng PreparedStatement cho nhiều thread thực thi đồng thời. Hãy tạo statement trong phạm vi công việc sử dụng connection và đóng tài nguyên sau khi hoàn tất.

## 5. Tái sử dụng PreparedStatement trong một Connection

Nếu cần chạy cùng một câu SQL cho nhiều bản ghi, hãy tạo PreparedStatement một lần rồi gán tham số và thực thi nhiều lần trong cùng connection.

~~~java
String sql = "UPDATE inventory SET quantity = ? WHERE sku = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    for (InventoryChange change : changes) {
        ps.setInt(1, change.quantity());
        ps.setString(2, change.sku());
        ps.executeUpdate();
    }
}
~~~

Cách này tránh gọi prepareStatement lặp lại ở mỗi vòng lặp và giữ cấu trúc SQL ổn định. Tuy nhiên, mỗi executeUpdate vẫn có thể là một lần trao đổi với database. Nếu số dòng lớn, batching có thể giảm round trip.

### Phạm vi sống của statement

PreparedStatement thuộc về Connection tạo ra nó. Khi connection được đóng, statement liên quan cũng không còn được dùng. Với connection pool, close thường trả connection về pool; pool quản lý việc reset trạng thái và có thể tích hợp statement cache tùy cấu hình.

Không giữ PreparedStatement toàn cục trong singleton hoặc static field nếu nó gắn với một connection được chia sẻ. Điều đó có thể làm cạn pool, gây lỗi đồng thời và giữ tài nguyên quá lâu.

### Đóng ResultSet và PreparedStatement

Dùng try-with-resources để đóng ResultSet, PreparedStatement và Connection:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc dòng
        }
    }
}
~~~

ResultSet thường gắn với statement. Đóng đúng thứ tự giúp giải phóng cursor, buffer và tài nguyên phía driver/database. Không giữ ResultSet mở trong khi ứng dụng chờ người dùng hoặc gọi dịch vụ ngoài.

## 6. PreparedStatement, driver cache và server-side prepare

Tên PreparedStatement trong JDBC không đồng nghĩa với một execution plan đã được biên dịch và lưu vĩnh viễn trên server.

Có thể phân biệt các lớp:

1. **JDBC object:** đối tượng PreparedStatement trong ứng dụng.
2. **Driver-side handling:** driver có thể lưu metadata, tái sử dụng giao thức hoặc cache statement.
3. **Server-side prepared statement:** database có thể tạo một statement đã chuẩn bị trong session.
4. **Execution plan cache:** database có thể lưu hoặc tái sử dụng plan, tùy engine và chính sách optimizer.

Một driver có thể mô phỏng prepared statement bằng cách gửi SQL đã bind theo giao thức riêng, hoặc chuyển sang server-side preparation sau một số lần thực thi. Cấu hình, ngưỡng và hành vi phụ thuộc driver/version.

### PreparedStatement không bảo đảm plan cache

Việc dùng PreparedStatement giúp giữ câu SQL ổn định và bind giá trị an toàn. Nó không bảo đảm:

- Database chỉ parse một lần trong toàn bộ vòng đời ứng dụng.
- Plan luôn được tái sử dụng.
- Mọi giá trị tham số đều có cùng một plan tối ưu.
- Một statement object tồn tại sau khi connection đóng.
- Mọi driver đều dùng server-side prepare mặc định.

Hãy kiểm tra tài liệu driver, cấu hình connection string và số liệu server để biết hành vi thật.

### Connection pool và statement cache

Connection pool thường tái sử dụng physical connection. Một số pool hoặc JDBC driver hỗ trợ cache PreparedStatement theo connection. Khi ứng dụng đóng statement, driver có thể giữ statement nội bộ để tái sử dụng thay vì giải phóng hoàn toàn ngay lập tức.

Statement cache có giới hạn và chi phí bộ nhớ. Nếu ứng dụng tạo vô số câu SQL khác nhau do nối literal hoặc sinh nhiều biến thể, cache dễ bị churn. Câu SQL ổn định giúp tăng khả năng cache hit.

Không mở rộng cache vô hạn. Hãy theo dõi số statement, cache hit/miss nếu driver cung cấp, số connection, memory và server-side prepared statement đang tồn tại.

## 7. Tái sử dụng plan và vấn đề tham số lệch phân bố

Một câu SQL có thể được gọi với nhiều giá trị có độ chọn lọc khác nhau. Ví dụ:

- Tenant A chỉ có 100 đơn hàng.
- Tenant B có 20 triệu đơn hàng.
- Trạng thái CANCELLED rất hiếm.
- Trạng thái PAID chiếm phần lớn bảng.

Một plan index seek có thể phù hợp với tenant nhỏ nhưng không tốt với tenant lớn. Một plan scan có thể hợp lý với tenant lớn nhưng tốn kém cho tenant nhỏ.

### Parameter sniffing và parameter-sensitive plan

Một số hệ quản trị dùng giá trị tham số khi biên dịch hoặc tối ưu để ước lượng cardinality. Plan được tạo dựa trên một nhóm tham số có thể được tái sử dụng cho nhóm khác có phân bố rất khác.

SQL Server thường được nhắc đến với parameter sniffing và có các cơ chế xử lý plan nhạy tham số tùy phiên bản. PostgreSQL có thể chọn custom plan hoặc generic plan cho prepared statement theo cơ chế của phiên bản. MySQL cũng có cơ chế chuẩn bị câu lệnh và optimizer riêng; không áp dụng tên gọi hoặc giả định của engine khác sang MySQL.

### Cách điều tra

1. Ghi nhận các nhóm tham số đại diện, không chỉ một giá trị.
2. So sánh estimated rows và actual rows.
3. Thu thập execution plan cho tenant nhỏ/lớn, trạng thái hiếm/phổ biến và khoảng thời gian ngắn/dài.
4. Xem plan cache hoặc prepared statement behavior của engine.
5. Đo p50/p95/p99 theo từng nhóm tham số.
6. Kiểm tra index, thống kê và điều kiện lọc trước khi dùng hint hoặc ép recompile.

### Không phá tính ổn định SQL bằng literal tùy tiện

Nối giá trị vào chuỗi để buộc database tạo plan riêng có thể làm plan cache phân mảnh và tăng parse/compile CPU. Nếu thực sự cần kế hoạch khác theo nhóm tham số, hãy dùng cơ chế parameter-sensitive plan, query variant, recompile hoặc hint được engine hỗ trợ sau khi đo và hiểu trade-off.

## 8. IN clause và danh sách tham số động

Một placeholder đại diện cho một giá trị, không đại diện cho cả danh sách. Câu lệnh:

~~~sql
SELECT order_id
FROM orders
WHERE order_id IN (?)
~~~

không tự biến một tham số chuỗi như "10,20,30" thành ba giá trị số. Database có thể xem đó là một giá trị duy nhất hoặc ép kiểu theo engine.

### Sinh số placeholder theo kích thước danh sách

Có thể tạo số lượng dấu hỏi dựa trên số phần tử, rồi bind từng giá trị:

~~~java
List<Long> ids = List.of(10L, 20L, 30L);

String placeholders = String.join(
    ",",
    Collections.nCopies(ids.size(), "?")
);

String sql = "SELECT order_id FROM orders WHERE order_id IN (" +
             placeholders + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả
    }
}
~~~

Ở đây chỉ số lượng placeholder được sinh động; giá trị từng phần tử vẫn được bind. Cần giới hạn kích thước danh sách để tránh câu SQL quá dài, vượt giới hạn bind parameter hoặc tạo quá nhiều biến thể statement.

### Danh sách rỗng

Nếu danh sách rỗng, không tạo IN () vì cú pháp này không hợp lệ trên nhiều hệ quản trị. Hãy xác định ý nghĩa nghiệp vụ: trả về rỗng ngay trong ứng dụng, hoặc tạo điều kiện luôn sai như 1 = 0.

### Array parameter và table-valued parameter

Một số engine hỗ trợ truyền array, table-valued parameter hoặc cơ chế tương tự. Đây có thể là lựa chọn tốt hơn cho danh sách lớn, nhưng API và cú pháp không portable. Hãy xem tài liệu driver/database và benchmark so với nhiều placeholder.

## 9. LIKE, wildcard và tham số bind

PreparedStatement bảo vệ giá trị khỏi việc trở thành cú pháp SQL, nhưng không thay đổi ý nghĩa wildcard của LIKE.

Ví dụ:

~~~java
String sql = "SELECT customer_id FROM customers WHERE name LIKE ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, prefix + "%");
    // execute
}
~~~

Nếu prefix là "An", điều kiện tìm các tên bắt đầu bằng An. Nếu người dùng nhập phần trăm hoặc gạch dưới, các ký tự đó vẫn có ý nghĩa wildcard của LIKE.

Nếu nghiệp vụ cần tìm chính xác chuỗi con theo nghĩa literal, cần escape ký tự wildcard theo cú pháp của engine và khai báo ESCAPE phù hợp. Bind parameter vẫn phải được sử dụng; escaping wildcard chỉ xử lý ngữ nghĩa tìm kiếm, không thay thế bảo vệ SQL injection.

Index B-tree có thể hỗ trợ LIKE prefix trong một số collation/engine, nhưng LIKE '%text%' thường không dùng được B-tree thông thường để seek theo tiền tố. Cần chọn full-text/trigram hoặc search index phù hợp với workload.

## 10. Batch execution với PreparedStatement

Khi cần ghi nhiều dòng cùng một mẫu SQL, JDBC hỗ trợ addBatch và executeBatch.

~~~java
String sql = "INSERT INTO audit_events (event_id, event_type) VALUES (?, ?)";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    connection.setAutoCommit(false);

    try {
        for (AuditEvent event : events) {
            ps.setLong(1, event.id());
            ps.setString(2, event.type());
            ps.addBatch();
        }

        int[] counts = ps.executeBatch();
        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

Ví dụ minh họa gom nhiều bộ tham số vào một batch. Driver có thể gửi batch bằng nhiều cách: nhiều lệnh, giao thức batch riêng hoặc rewrite thành multi-row insert tùy driver và cấu hình. Không giả định mọi driver có cùng hiệu quả.

### Chia batch thành các chunk

Một batch quá lớn có thể tiêu thụ bộ nhớ ở driver, tạo log burst và làm transaction kéo dài. Với dữ liệu lớn, nên thực thi theo chunk và commit từng chunk nếu nghiệp vụ cho phép.

~~~java
String sql = "INSERT INTO audit_events (event_id, event_type) VALUES (?, ?)";
int batchSize = 500;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int pending = 0;

        for (AuditEvent event : events) {
            ps.setLong(1, event.id());
            ps.setString(2, event.type());
            ps.addBatch();
            pending++;

            if (pending == batchSize) {
                ps.executeBatch();
                connection.commit();
                pending = 0;
            }
        }

        if (pending > 0) {
            ps.executeBatch();
            connection.commit();
        }
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

Đây là ví dụ cơ bản; connection được đóng khi kết thúc khối và connection pool phải reset transaction state trước khi cấp lại physical connection. Nếu ứng dụng quản lý physical connection trực tiếp, cần khôi phục trạng thái auto-commit sau khi transaction đã kết thúc. Nếu rollback hoặc commit thất bại và trạng thái connection không còn xác định, không được tiếp tục tái sử dụng connection đó. Mã production cũng cần xử lý kết quả commit không rõ do mất kết nối.

### BatchUpdateException và update counts

executeBatch có thể ném BatchUpdateException nếu một phần lệnh thất bại. Update counts có thể biểu thị số dòng ảnh hưởng, SUCCESS_NO_INFO hoặc EXECUTE_FAILED tùy driver.

Cần xác định driver tiếp tục hay dừng ở phần tử lỗi, batch có được thực thi một phần hay không và transaction đang ở trạng thái nào. Nếu dùng transaction thủ công, hãy rollback chunk hiện tại khi lỗi và chỉ tiếp tục theo chính sách retry đã thiết kế.

### Batch không đồng nghĩa một transaction nguyên tử

Batch API gom thao tác gửi, nhưng tính nguyên tử phụ thuộc transaction boundary và driver/database. Nếu auto-commit bật, không nên mặc định toàn bộ batch sẽ được commit như một transaction duy nhất. Khi cần all-or-nothing cho một chunk, hãy quản lý auto-commit và commit/rollback tường minh.

## 11. Generated keys và RETURNING

Một số INSERT cần lấy khóa được sinh tự động. JDBC hỗ trợ yêu cầu generated keys:

~~~java
String sql = "INSERT INTO customers (name) VALUES (?)";

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, customerName);
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long customerId = keys.getLong(1);
        }
    }
}
~~~

Khả năng và hiệu năng lấy generated keys theo batch phụ thuộc driver và database. Một số engine có cú pháp RETURNING hoặc OUTPUT riêng. Nếu cần insert nhiều dòng và lấy tất cả key, hãy kiểm tra thứ tự, số lượng key trả về và khả năng ánh xạ đúng với từng input.

Không giả định key được trả về theo thứ tự batch nếu tài liệu driver không bảo đảm.

## 12. PreparedStatement cho truy vấn đọc lớn

PreparedStatement cũng được dùng cho SELECT. Với kết quả lớn, thời gian truy vấn không phải chi phí duy nhất; driver còn phải truyền dữ liệu qua mạng, giải mã và giữ buffer.

JDBC cung cấp setFetchSize để gợi ý số dòng driver lấy mỗi lần:

~~~java
String sql = "SELECT event_id, occurred_at, event_type FROM events " +
             "WHERE tenant_id = ? ORDER BY occurred_at";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý từng dòng
        }
    }
}
~~~

Fetch size là hint; driver có thể bỏ qua hoặc diễn giải khác nhau. Một số driver cần server-side cursor hoặc transaction không auto-commit để streaming thực sự hoạt động. Hãy kiểm tra tài liệu driver.

### Fetch size quá nhỏ hoặc quá lớn

- Quá nhỏ: nhiều round trip và overhead giao tiếp.
- Quá lớn: driver giữ nhiều dữ liệu trong bộ nhớ và tăng áp lực heap.
- Kích thước phù hợp phụ thuộc độ rộng dòng, network latency, số dòng và cách driver buffer.

Không tải toàn bộ ResultSet vào List nếu ứng dụng chỉ cần xử lý tuần tự. Giữ ResultSet mở lâu cũng có thể giữ cursor, connection và transaction; hãy thiết kế vòng đời ngắn và đóng tài nguyên đúng lúc.

## 13. Timeout và hủy câu lệnh

JDBC cho phép đặt query timeout theo giây:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setQueryTimeout(5);
    ps.executeQuery();
}
~~~

Timeout là giới hạn ở tầng JDBC/driver; cách hủy truy vấn và thời điểm server dừng công việc phụ thuộc driver và engine. Cần phân biệt:

- Connection timeout: thời gian chờ lấy hoặc thiết lập connection.
- Query timeout: thời gian cho phép câu lệnh thực thi.
- Lock timeout: thời gian chờ khóa theo cấu hình database hoặc session.
- Socket/network timeout: thời gian chờ giao tiếp mạng.

Một timeout ở client không nhất thiết chứng minh server đã rollback hoặc không thực hiện commit. Nếu connection mất trong lúc commit, kết quả có thể không rõ. Dùng idempotency key hoặc cơ chế tra cứu trạng thái để xử lý retry an toàn.

## 14. PreparedStatement, transaction và connection pool

PreparedStatement chỉ tồn tại trong phạm vi Connection. Trong ứng dụng Java, Connection thường được lấy từ DataSource hoặc connection pool.

Quy trình phổ biến:

~~~text
Request / Job
     |
     v
DataSource.getConnection()
     |
     v
Connection từ pool
     |
     v
prepareStatement(SQL)
     |
     v
bind parameters
     |
     v
execute / read ResultSet
     |
     v
close statement và result set
     |
     v
close Connection (trả về pool)
~~~

### Không giữ connection khi không cần database

Nếu ứng dụng lấy connection rồi thực hiện xử lý CPU, gọi API ngoài hoặc chờ người dùng, connection bị chiếm dụng mà không tạo giá trị cho database. Hãy lấy connection gần thời điểm truy vấn và trả lại ngay khi hoàn tất.

### Statement cache gắn với physical connection

Nếu driver cache prepared statements theo connection, việc tái sử dụng phụ thuộc physical connection được pool cấp lại. Một request có thể nhận connection khác nên không nên giả định cùng một đối tượng PreparedStatement tồn tại xuyên request.

Một số pool hỗ trợ statement cache hoặc phối hợp với driver. Tránh bật nhiều lớp cache trùng lặp mà không hiểu tổng giới hạn và bộ nhớ. Theo dõi cache hit/miss, open cursors, prepared statements trên server và số connection.

### Không chia sẻ Connection giữa các request đồng thời

Connection JDBC thường không được thiết kế để nhiều thread dùng đồng thời cho các transaction độc lập. Dùng connection theo phạm vi request/job hoặc transaction; không chia sẻ Connection và PreparedStatement toàn cục.

## 15. Tên tham số và named parameter

JDBC chuẩn sử dụng placeholder vị trí ? trong PreparedStatement. Cú pháp tên như :customerId không thuộc API PreparedStatement chuẩn.

Một số thư viện như Spring JDBC hoặc ORM cung cấp named parameter và chuyển chúng thành placeholder vị trí trước khi gửi đến driver. Ví dụ về mặt khái niệm:

~~~sql
SELECT order_id FROM orders WHERE customer_id = :customerId
~~~

Thư viện sẽ ánh xạ tên customerId vào vị trí bind tương ứng. Cần phân biệt tính năng của thư viện với JDBC chuẩn, đặc biệt khi debug SQL, đọc log hoặc phân tích execution plan.

## 16. Đọc execution plan và đo lợi ích

Không thể kết luận PreparedStatement nhanh hơn chỉ vì code ít tạo chuỗi hơn. Cần đo cả tầng ứng dụng, driver và database.

### Các chỉ số phía ứng dụng

- Thời gian lấy connection từ pool.
- Thời gian prepare/execute.
- Thời gian bind và serialize tham số nếu có thể đo.
- Số lần execute trên mỗi statement.
- Số round trip và bytes truyền.
- Batch size và rows per second.
- Thời gian đọc ResultSet.
- Heap allocation, GC và số connection đang sử dụng.
- Timeout, retry và lỗi theo nhóm SQL.

### Các chỉ số phía database

- Parse/compile time hoặc số lần prepare nếu engine cung cấp.
- Plan cache hit/miss và prepared statement count.
- Estimated rows so với actual rows.
- Index seek/scan, table scan và số rows đọc.
- Logical reads, physical reads và buffer hit.
- CPU time, execution time và wait events.
- Lock wait, temp spill, sort/hash memory.
- Commit latency và log flush nếu có ghi.

### Ví dụ PostgreSQL

Có thể kiểm tra truy vấn với tham số cụ thể:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực thi truy vấn. Trong môi trường production, cân nhắc tác động của việc chạy lại truy vấn. Với server-side prepared statement, PostgreSQL có thể dùng custom hoặc generic plan theo cơ chế của phiên bản; hãy kiểm tra plan thực tế trong cùng session khi điều tra.

### Ví dụ SQL Server

Actual Execution Plan và Query Store có thể giúp so sánh plan, runtime statistics và biến thể theo tham số. Theo dõi parameter sniffing, implicit conversion, logical reads, CPU và duration.

### Ví dụ MySQL

EXPLAIN hoặc EXPLAIN ANALYZE tùy phiên bản giúp xem access path, estimated/actual rows và iterator time. Performance Schema và statement digest có thể hỗ trợ phân tích tần suất, latency và hành vi prepared statement.

Tên view, công cụ và khả năng hiển thị phụ thuộc phiên bản. Dùng tài liệu driver và database đang chạy.

## 17. Ví dụ tổng hợp: truy vấn đơn hàng theo tenant

Giả sử bảng orders có 100 triệu dòng, với các cột order_id, tenant_id, status, created_at và total_amount. Ứng dụng thường truy vấn 50 đơn mới nhất theo tenant và trạng thái.

SQL ổn định:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?
~~~

Java:

~~~java
String sql = "SELECT order_id, created_at, total_amount " +
             "FROM orders " +
             "WHERE tenant_id = ? AND status = ? " +
             "ORDER BY created_at DESC, order_id DESC LIMIT ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setLong(1, tenantId);
    ps.setString(2, status);
    ps.setInt(3, 50);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            Timestamp createdAt = rs.getTimestamp("created_at");
            BigDecimal amount = rs.getBigDecimal("total_amount");
            // Chuyển thành DTO hoặc xử lý tiếp
        }
    }
}
~~~

Một index có thể được đánh giá:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC, order_id DESC);
~~~

Index này có thể hỗ trợ hai điều kiện equality và thứ tự trong phạm vi tenant/status. Tuy nhiên, cần kiểm tra phân bố tham số. Tenant nhỏ và status hiếm có thể có plan khác tenant lớn và status phổ biến.

Ví dụ dùng cú pháp LIMIT phổ biến trong PostgreSQL và MySQL. SQL Server dùng TOP hoặc OFFSET/FETCH tùy cách phân trang; placeholder vẫn bind các giá trị giới hạn theo cú pháp của engine.

### Cách đánh giá

1. Thu thập plan và số liệu cho tenant nhỏ/lớn.
2. So sánh status hiếm và phổ biến.
3. Xem actual rows, buffers, rows read và sort.
4. Kiểm tra kiểu bind có khớp kiểu cột không.
5. So sánh PreparedStatement với cách gọi hiện tại ở cùng query mix.
6. Đo p50/p95/p99, connection pool wait và throughput.
7. Đánh giá plan cache hoặc server-side prepare của driver.
8. Xác nhận index mới không làm chi phí ghi tăng quá mức.

PreparedStatement giúp SQL ổn định và truyền tham số an toàn; index và execution plan mới quyết định database đọc dữ liệu hiệu quả ra sao.

## 18. Những sai lầm thường gặp

- **Nối giá trị vào SQL:** gây rủi ro injection và tạo nhiều SQL text khác nhau.
- **Nghĩ rằng dấu hỏi thay được tên bảng/cột:** placeholder chỉ dành cho giá trị.
- **Bind mọi thứ bằng setString:** có thể gây implicit conversion và làm thay đổi access path.
- **Không gán lại mọi tham số:** giá trị cũ có thể còn trên statement.
- **Dùng một PreparedStatement cho nhiều thread:** gây race trên trạng thái tham số và ResultSet.
- **Giữ statement/connection quá lâu:** chiếm tài nguyên pool và cursor.
- **Cho rằng PreparedStatement luôn tạo server-side plan:** hành vi phụ thuộc driver và engine.
- **Cho rằng plan được cache luôn tối ưu:** dữ liệu lệch có thể khiến plan dùng lại không phù hợp.
- **Tạo SQL text khác nhau cho từng giá trị:** làm giảm khả năng tái sử dụng và tăng parse/compile.
- **Dùng một placeholder cho danh sách IN:** không bind được cả danh sách bằng một chuỗi.
- **Không xử lý danh sách rỗng:** có thể tạo SQL không hợp lệ.
- **Đặt wildcard LIKE mà không hiểu ngữ nghĩa:** bind an toàn nhưng % và _ vẫn là wildcard.
- **Dùng batch quá lớn:** tăng memory, log, transaction duration và rollback cost.
- **Bật auto-commit rồi giả định batch nguyên tử:** transaction boundary phụ thuộc cấu hình và driver.
- **Không xử lý BatchUpdateException:** có thể bỏ qua việc batch đã thực hiện một phần.
- **Đọc ResultSet quá lớn vào bộ nhớ:** gây heap pressure và GC.
- **Chọn fetch size mà không đo:** quá nhỏ tăng round trip, quá lớn tăng bộ nhớ.
- **Retry khi commit chưa rõ kết quả:** có thể áp dụng thao tác hai lần nếu không có idempotency.

## 19. Quy trình áp dụng PreparedStatement trong ứng dụng Java

1. **Xác định SQL shape:** viết câu SQL ổn định và tách các giá trị thành placeholder.
2. **Rà soát identifier động:** dùng allowlist cho tên cột, bảng và sort direction.
3. **Chọn kiểu bind:** khớp kiểu SQL, đặc biệt với số, decimal, date/time và NULL.
4. **Quản lý lifecycle:** lấy Connection từ DataSource, tạo PreparedStatement, đóng ResultSet/statement và trả connection.
5. **Tái sử dụng đúng phạm vi:** dùng một statement cho nhiều lần thực thi cùng SQL trong một connection khi phù hợp.
6. **Đánh giá batch:** dùng addBatch/executeBatch cho thao tác lặp; chọn chunk size theo transaction duration và commit cost.
7. **Quản lý transaction:** xác định rõ auto-commit, commit, rollback và checkpoint.
8. **Kiểm tra driver:** xác minh server-side prepare, statement cache, batch rewrite và fetch behavior.
9. **Đọc execution plan:** xem cardinality, index, implicit conversion, sort và actual rows.
10. **Benchmark workload:** đo nhiều nhóm tham số và mức concurrency.
11. **Theo dõi production:** quan sát p95/p99, pool wait, parse/plan, I/O, timeout và retry.
12. **Điều chỉnh có kiểm soát:** chỉ thay cache, batch size, fetch size hoặc plan behavior sau khi xác định bottleneck.

## 20. Checklist kiểm tra

Trước khi đưa một truy vấn JDBC vào production, hãy xác nhận:

- SQL dùng placeholder cho mọi giá trị đầu vào.
- Identifier động được chọn từ allowlist.
- Tất cả placeholder được gán trong mỗi lần thực thi.
- Kiểu bind tương thích kiểu cột.
- SQL NULL được gán với kiểu phù hợp.
- Ngày giờ có quy ước timezone rõ ràng.
- PreparedStatement không được chia sẻ giữa các thread.
- Connection và ResultSet được đóng đúng lúc.
- Statement được tái sử dụng trong phạm vi connection hợp lý.
- Driver và pool có cấu hình statement cache đã được hiểu rõ.
- Không giả định server-side prepare hoặc plan cache nếu chưa xác minh.
- Danh sách IN, LIKE và generated keys được xử lý theo đúng ngữ nghĩa.
- Batch size và transaction boundary phù hợp.
- BatchUpdateException, rollback và retry được xử lý.
- Query timeout và network failure có chính sách rõ.
- Execution plan được kiểm tra với nhiều nhóm tham số.
- Benchmark đo latency, throughput, pool wait, CPU, I/O và p95/p99.
- Log không làm lộ giá trị nhạy cảm của bind parameter.

## Kết luận

PreparedStatement là cách chuẩn trong JDBC để tách cấu trúc SQL khỏi dữ liệu đầu vào. Bind parameter giúp chống SQL injection ở vị trí giá trị, giữ câu SQL ổn định và tạo cơ hội để driver/database tái sử dụng statement hoặc plan. Việc tái sử dụng cần diễn ra trong phạm vi Connection phù hợp; statement không nên được chia sẻ đồng thời giữa nhiều thread và mọi tài nguyên JDBC phải được đóng đúng lúc.

Hiệu năng không chỉ đến từ việc thay Statement bằng PreparedStatement. Kiểu bind, driver, connection pool, server-side preparation, plan cache, phân bố tham số, index, batching và fetch size đều ảnh hưởng kết quả. Hãy đo execution plan cùng chỉ số phía ứng dụng và database, thử nhiều nhóm tham số dưới tải đại diện, rồi xác nhận thay đổi cải thiện latency và throughput mà vẫn giữ tính đúng, độ an toàn và khả năng phục hồi của giao dịch.
