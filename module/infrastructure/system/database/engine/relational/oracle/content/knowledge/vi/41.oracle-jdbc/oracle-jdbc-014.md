# Statement cache, cursor phía server và xử lý ORA-01000

Oracle JDBC cho phép ứng dụng Java gửi SQL tới Oracle Database thông qua các đối tượng Connection, Statement, PreparedStatement, CallableStatement và ResultSet. Mỗi lần thực thi SQL, Oracle có thể tạo hoặc sử dụng lại cursor phía server để parse, execute và fetch dữ liệu. Nếu ứng dụng mở quá nhiều cursor trong một session mà không đóng đúng cách, database có thể trả lỗi ORA-01000: maximum open cursors exceeded.

Statement cache giúp giảm chi phí tạo statement và parse SQL lặp lại. Tuy nhiên, cache cũng giữ lại statement/cursor để tái sử dụng. Nếu cấu hình cache quá lớn, kết hợp với connection pool lớn hoặc code không đóng ResultSet/Statement, số cursor mà mỗi session sử dụng có thể tăng cao.

Cần phân biệt rõ bốn cơ chế:

- **JDBC statement cache:** cache PreparedStatement/CallableStatement ở phía Oracle JDBC connection để tái sử dụng statement.
- **Server-side cursor:** trạng thái cursor mà Oracle duy trì trong session để thực thi SQL và trả kết quả.
- **SESSION_CACHED_CURSORS:** cache cursor ở phía Oracle session nhằm giảm soft parse cho SQL được đóng rồi mở lại.
- **OPEN_CURSORS:** giới hạn số cursor handle mà một session có thể mở.

Các cơ chế này liên quan với nhau nhưng không thay thế nhau. Statement cache không cho phép bỏ qua close; SESSION_CACHED_CURSORS không sửa được leak; tăng OPEN_CURSORS không giải quyết nguyên nhân nếu ứng dụng liên tục mở statement mà không đóng.

## 1. Statement và cursor trong Oracle JDBC

Khi Java thực thi SQL, ứng dụng thường thao tác với một JDBC Statement object. Ở phía Oracle, câu SQL được parse và gắn với một cursor để database quản lý trạng thái thực thi.

Một luồng query điển hình:

~~~text
Java application
      |
      v
JDBC Connection
      |
      v
PreparedStatement
      |
      | executeQuery()
      v
Oracle JDBC driver
      |
      v
Oracle session
      |
      v
Server cursor
      |
      +---- parse
      +---- execute
      +---- fetch
      |
      v
ResultSet returned to Java
~~~

JDBC Statement là đối tượng ở phía client/driver. Server cursor là tài nguyên và trạng thái thực thi ở phía database. Một PreparedStatement không đơn giản chỉ là chuỗi SQL trong Java; nó có thể gắn với cursor phía server và các trạng thái liên quan.

### 1.1 Parse, execute và fetch

Quá trình thực thi SQL thường có các giai đoạn:

1. **Parse:** Oracle kiểm tra cú pháp, tên object, quyền, bind variable và tìm hoặc tạo cursor phù hợp.
2. **Execute:** Oracle thực hiện câu lệnh, thiết lập trạng thái thực thi và xử lý các bind value.
3. **Fetch:** với câu query, Oracle trả từng phần kết quả về JDBC driver.
4. **Close:** ứng dụng đóng ResultSet/Statement; driver và database giải phóng hoặc đưa tài nguyên vào cơ chế cache thích hợp.

Parse có thể gồm hard parse hoặc soft parse. Hard parse tốn chi phí hơn vì Oracle phải phân tích SQL và tạo execution plan khi không tìm được cursor phù hợp trong shared pool. Soft parse có thể sử dụng thông tin đã tồn tại, nhưng vẫn có chi phí parse và quản lý session cursor.

Statement cache giúp tái sử dụng statement phía JDBC và có thể giảm parse round-trip. Nó không có nghĩa Oracle bỏ qua mọi bước execute/fetch ở lần chạy tiếp theo.

### 1.2 Server cursor không đồng nghĩa với SQL text trong shared pool

Oracle có vùng shared SQL area/library cache chứa thông tin SQL dùng chung giữa session khi có thể. Mỗi session vẫn có các cursor handle và trạng thái riêng để thực thi SQL.

Do đó:

- Một SQL text có thể được chia sẻ execution plan trong shared pool.
- Nhiều session có thể cùng thực thi SQL text đó.
- Mỗi session vẫn có cursor handle riêng.
- Đóng một JDBC statement không nhất thiết xóa SQL khỏi shared pool.
- Một cursor được cache trong session vẫn có thể xuất hiện trong các view theo dõi cursor.

Không nên nhìn số lượng dòng trong V$SQL rồi kết luận đó là số cursor đang mở của một session. Muốn điều tra ORA-01000, cần xem đúng session và cursor state.

## 2. JDBC object lifecycle

Các đối tượng JDBC có quan hệ vòng đời:

- Connection tạo ra Statement/PreparedStatement/CallableStatement.
- Statement thực thi SQL và tạo ResultSet.
- ResultSet giữ trạng thái đọc kết quả.
- CallableStatement có thể trả ResultSet hoặc REF CURSOR qua OUT parameter.
- Đóng các đối tượng đúng thứ tự giúp driver giải phóng tài nguyên.

Ví dụ query cơ bản:

~~~java
String sql =
    "SELECT order_id, status FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Xử lý dòng hiện tại.
        }
    }
}
~~~

Try-with-resources gọi close ngay cả khi có exception. Khi ResultSet đóng, cursor kết quả được giải phóng theo cơ chế driver. Khi PreparedStatement đóng, driver có thể đóng hẳn statement hoặc đưa statement vào implicit statement cache nếu cache được bật và statement đủ điều kiện.

### 2.1 Vì sao phải đóng cả ResultSet và Statement?

Đóng Connection không nên được dùng như cách duy nhất để dọn dẹp mọi tài nguyên. Trong ứng dụng có connection pool, Connection.close() thường chỉ trả logical connection về pool; physical database session có thể vẫn tồn tại.

Nếu code không đóng ResultSet/Statement:

- Cursor có thể vẫn mở trong session.
- Statement có thể giữ tham chiếu tới ResultSet.
- Connection pool có thể tái sử dụng physical session với tài nguyên còn sót.
- Lỗi ORA-01000 có thể xuất hiện sau một thời gian, dù từng request riêng lẻ có vẻ chạy bình thường.

Đóng ResultSet ngay sau khi đọc xong, rồi đóng Statement, sau đó mới trả Connection về pool.

### 2.2 Statement.close() và ResultSet.close()

Theo JDBC, đóng Statement sẽ đóng ResultSet hiện tại do statement tạo ra. Tuy nhiên, code nên đóng rõ ResultSet trong try-with-resources để thể hiện ownership và bảo đảm tài nguyên được giải phóng ngay khi vòng đọc kết thúc.

Nếu một Statement trả nhiều result set hoặc update count, hãy xử lý hết các kết quả và đóng chúng theo JDBC API. Không giữ ResultSet lâu hơn thời gian cần thiết.

### 2.3 CallableStatement và REF CURSOR

Stored procedure có thể trả cursor thông qua OUT parameter. Ví dụ với Oracle REF CURSOR:

~~~java
String call = "{ call order_api.get_orders(?, ?) }";

try (Connection connection = dataSource.getConnection();
     CallableStatement statement = connection.prepareCall(call)) {

    statement.setLong(1, customerId);
    statement.registerOutParameter(2, oracle.jdbc.OracleTypes.CURSOR);
    statement.execute();

    try (ResultSet resultSet =
             (ResultSet) statement.getObject(2)) {
        while (resultSet.next()) {
            // Đọc dữ liệu.
        }
    }
}
~~~

Ví dụ dùng Oracle JDBC extension OracleTypes.CURSOR. Với driver và API mới hơn, kiểu đăng ký có thể khác; hãy dùng kiểu REF CURSOR được hỗ trợ bởi phiên bản đang chạy.

Đóng ResultSet trả về từ REF CURSOR là quan trọng. Đóng CallableStatement sau khi hoàn tất cũng cần thiết. Nếu procedure mở nhiều REF CURSOR và ứng dụng chỉ đọc một cursor, các cursor còn lại vẫn có thể giữ tài nguyên cho đến khi được đóng.

## 3. Statement cache là gì?

Statement cache lưu statement đã được chuẩn bị để một lần gọi prepareStatement tiếp theo có thể lấy lại statement tương ứng thay vì tạo mới từ đầu.

Oracle JDBC hỗ trợ statement caching trên Oracle connection. Hai hình thức chính:

- **Implicit statement caching:** driver tự tìm statement phù hợp dựa trên SQL và thuộc tính statement.
- **Explicit statement caching:** ứng dụng quản lý cache key và yêu cầu statement theo key thông qua API Oracle JDBC tương ứng.

Với phần lớn ứng dụng, implicit statement caching dễ sử dụng hơn. Ứng dụng vẫn gọi prepareStatement như bình thường và đóng statement sau khi dùng. Khi cache bật, close có thể trả statement vào cache thay vì hủy hoàn toàn.

### 3.1 Lợi ích

Statement cache có thể:

- Giảm chi phí tạo PreparedStatement lặp lại.
- Giảm parse overhead và round-trip cần thiết cho prepare.
- Tái sử dụng cursor/statement đã chuẩn bị.
- Tăng throughput với workload có tập SQL ổn định.
- Giảm áp lực lên shared pool do hạn chế parse lặp, tùy workload.

Cache hữu ích khi ứng dụng thường xuyên thực thi cùng một SQL với các bind value khác nhau:

~~~sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = :status
~~~

Thay vì tạo SQL text khác nhau cho mỗi customer, ứng dụng dùng bind variable và tái sử dụng PreparedStatement.

### 3.2 Statement cache không phải query result cache

Statement cache lưu statement đã chuẩn bị, không lưu kết quả query. Khi gọi executeQuery với bind value mới, Oracle vẫn thực hiện câu SQL và trả dữ liệu theo trạng thái hiện tại.

Không nhầm statement cache với:

- Oracle Database Result Cache.
- JDBC application cache chứa object/kết quả.
- Shared pool/library cache.
- Session cursor cache.
- Connection pool.

Mỗi cơ chế giải quyết một loại chi phí khác nhau.

### 3.3 Statement cache gắn với connection vật lý

Statement cache thuộc về Oracle JDBC connection/session tương ứng. Với connection pool, nhiều logical Connection có thể lần lượt sử dụng cùng physical connection.

Ví dụ pool có 40 physical connections và mỗi connection cache 30 statement, mỗi session có thể giữ một tập statement cache riêng. Không có một cache duy nhất dùng chung cho toàn bộ pool.

Điều này ảnh hưởng đến sizing: cache size là giới hạn theo connection, nên tổng số statement có thể được giữ trên toàn pool có thể xấp xỉ pool size nhân cache size. Mức sử dụng thực tế còn phụ thuộc SQL workload và hành vi driver.

## 4. Implicit statement caching

Implicit caching là lựa chọn thường dùng. Khi bật, ứng dụng không cần tự quản lý cache key. Driver dựa trên SQL text và thuộc tính statement để xác định statement có thể tái sử dụng.

Cấu hình Oracle JDBC minh họa:

~~~java
import java.sql.Connection;
import oracle.jdbc.OracleConnection;

void configureStatementCache(Connection connection)
        throws java.sql.SQLException {

    OracleConnection oracleConnection =
        connection.unwrap(OracleConnection.class);

    oracleConnection.setStatementCacheSize(32);
    oracleConnection.setImplicitCachingEnabled(true);
}
~~~

Ví dụ này minh họa Oracle JDBC API. Trong production, nên cấu hình ở giai đoạn tạo physical connection hoặc cấu hình pool theo hướng dẫn của connection pool đang dùng. Không nên thay đổi kích thước cache trên mỗi request.

### 4.1 Cách statement quay lại cache

Luồng đơn giản:

~~~text
prepareStatement(SQL)
       |
       v
Driver tìm cache entry
       |
       +---- Có entry ----> Lấy statement đã cache
       |
       +---- Không có ----> Tạo/prepare statement
       |
       v
executeQuery / executeUpdate
       |
       v
Đọc kết quả
       |
       v
statement.close()
       |
       v
Driver đưa statement đủ điều kiện vào cache
~~~

Ứng dụng vẫn phải gọi close. Nếu không đóng statement, driver không có tín hiệu bình thường để trả statement về cache. Không đóng còn có thể khiến cursor tiếp tục được giữ ở trạng thái đang sử dụng.

### 4.2 Điều kiện tái sử dụng

Statement cache thường cần SQL text và loại statement tương thích. Các yếu tố như PreparedStatement so với CallableStatement, kiểu ResultSet và thuộc tính statement có thể ảnh hưởng việc cache hit.

Hai SQL text khác nhau về cấu trúc hoặc nội dung literal có thể tạo cache entry riêng:

~~~sql
SELECT * FROM orders WHERE order_id = 1001
SELECT * FROM orders WHERE order_id = 1002
~~~

Dùng bind variable:

~~~sql
SELECT * FROM orders WHERE order_id = ?
~~~

và đặt bind value khác nhau cho mỗi lần thực thi. Cách này vừa hỗ trợ statement reuse, vừa giúp Oracle chia sẻ cursor tốt hơn khi các điều kiện khác phù hợp.

### 4.3 SQL text phải ổn định

Các khác biệt như whitespace, comment, thứ tự predicate hoặc cách viết literal có thể làm SQL text khác nhau và giảm cache hit. Không cần ép mọi SQL có cùng format bằng một quy tắc cứng, nhưng nên tránh sinh hàng nghìn SQL string khác nhau chỉ vì nối giá trị vào chuỗi.

Ví dụ không nên:

~~~java
String sql =
    "SELECT order_id FROM orders WHERE customer_id = " + customerId;
Statement statement = connection.createStatement();
~~~

Nên dùng:

~~~java
String sql =
    "SELECT order_id FROM orders WHERE customer_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    // Execute and process.
}
~~~

Bind variable không chỉ giúp cache. Nó còn tránh SQL injection đối với giá trị dữ liệu và giảm hard parse do literal khác nhau.

## 5. Explicit statement caching

Explicit caching cho phép ứng dụng xác định key cho statement và lấy lại statement theo key bằng API Oracle JDBC. Cách này có thể hữu ích khi ứng dụng muốn kiểm soát danh tính statement rõ ràng hoặc có một lớp quản lý statement riêng.

Tuy nhiên, explicit caching làm tăng trách nhiệm quản lý:

- Key phải ổn định và duy nhất trong phạm vi cache connection.
- SQL gắn với key phải nhất quán.
- Statement lấy ra phải được đóng/trả về theo API explicit cache.
- Không được để nhiều caller cùng dùng một cached statement đồng thời.
- Phải quản lý trạng thái bind parameter, ResultSet và transaction cẩn thận.

Không nên tự xây một explicit cache bằng Map toàn cục chứa PreparedStatement. Statement thuộc về connection cụ thể, không an toàn để chia sẻ tùy tiện giữa thread hoặc giữa connection khác nhau.

### 5.1 Khi nào dùng implicit và explicit?

| Tiêu chí | Implicit cache | Explicit cache |
|---|---|---|
| Cách sử dụng | Driver tự tìm theo SQL/statement attributes | Ứng dụng quản lý key |
| Độ phức tạp | Thấp hơn | Cao hơn |
| Phù hợp | Phần lớn JDBC workload chuẩn | Framework hoặc workload cần key/ownership rõ |
| Rủi ro | Cache size và lifecycle vẫn cần quản lý | Sai key hoặc chia sẻ statement không đúng có thể gây lỗi |
| Khuyến nghị | Bắt đầu từ đây | Chỉ dùng khi có lý do đo đạc được |

Không bật hai cơ chế chỉ vì nghĩ cache càng nhiều càng tốt. Xác định một chiến lược rõ ràng và đọc tài liệu Oracle JDBC của driver version đang dùng.

## 6. Statement cache và ResultSet

Statement cache không có nghĩa ResultSet cũng được giữ để trả lại cùng dữ liệu cho lần query sau. ResultSet là kết quả của một lần execute và phải được đóng sau khi sử dụng.

Một số điểm cần nhớ:

- Đóng ResultSet trước khi đóng PreparedStatement.
- Không lưu ResultSet trong field static hoặc object sống lâu.
- Không trả ResultSet ra khỏi tầng DAO nếu không có ownership rõ ràng đối với Connection/Statement.
- Không mở ResultSet rồi trả Connection về pool.
- Nếu cần trả dữ liệu cho tầng trên, map sang DTO hoặc stream có lifecycle rõ ràng.
- Không dùng ResultSet sau khi Statement đã đóng hoặc connection đã được trả về pool.

### 6.1 Anti-pattern: trả ResultSet từ DAO

Không nên:

~~~java
public ResultSet findOrders(Connection connection, long customerId)
        throws SQLException {
    PreparedStatement statement =
        connection.prepareStatement(
            "SELECT order_id FROM orders WHERE customer_id = ?"
        );
    statement.setLong(1, customerId);
    return statement.executeQuery();
}
~~~

Method này không trả quyền sở hữu statement cho caller một cách rõ ràng. Caller chỉ nhận ResultSet nhưng không biết cần đóng statement nào; statement có thể bị bỏ quên.

Nên map dữ liệu trong phạm vi method:

~~~java
public List<Long> findOrderIds(
        DataSource dataSource,
        long customerId) throws SQLException {

    String sql =
        "SELECT order_id FROM orders WHERE customer_id = ?";
    List<Long> ids = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                ids.add(resultSet.getLong(1));
            }
        }
    }

    return ids;
}
~~~

Nếu cần streaming lượng dữ liệu lớn, hãy thiết kế API streaming có ownership rõ và bảo đảm caller có thể đóng stream để giải phóng ResultSet, Statement và Connection.

## 7. OPEN_CURSORS là gì?

OPEN_CURSORS là tham số Oracle quy định số lượng cursor handle tối đa mà một session có thể mở cùng lúc. Đây là giới hạn theo session, không phải một giới hạn tổng duy nhất cho cả database.

Khi session vượt giới hạn, Oracle có thể trả:

~~~text
ORA-01000: maximum open cursors exceeded
~~~

Lỗi có thể xuất hiện ở execute, parse hoặc thao tác JDBC khác khi database cần mở thêm cursor nhưng session đã chạm giới hạn.

### 7.1 OPEN_CURSORS không phải số SQL khác nhau

Một ứng dụng có thể chạy một SQL text lặp lại trên nhiều PreparedStatement và vẫn tiêu thụ nhiều cursor handle trong session. Ngược lại, một SQL text có thể được nhiều session sử dụng với cursor handle riêng.

Không chỉ đếm số SQL text trong source code. Hãy đo số cursor theo session ở thời điểm workload đạt đỉnh.

### 7.2 Cursor đang mở và cursor được cache

Cursor có thể tồn tại dưới các trạng thái khác nhau:

- Đang được statement sử dụng.
- ResultSet đang mở và đang fetch.
- Statement đã đóng nhưng cursor được giữ trong session cursor cache.
- Statement được giữ trong JDBC statement cache.
- Cursor nội bộ do PL/SQL, recursive SQL hoặc metadata operation mở.

Các loại cache và cursor state có cách accounting riêng trong Oracle. Khi điều tra, cần đọc V$OPEN_CURSOR cùng session statistics và biết rằng danh sách có thể chứa cursor cached chứ không chỉ các ResultSet mà ứng dụng hiện đang đọc.

### 7.3 Mỗi session có giới hạn riêng

Nếu connection pool có 100 physical connections và OPEN_CURSORS là 500, mỗi session có giới hạn 500 cursor handle. Không có nghĩa toàn pool chỉ được mở 500 cursor.

Tuy nhiên, tổng tài nguyên trên database vẫn tăng theo số session. Một pool quá lớn kết hợp cache statement lớn có thể làm tổng số cursor/cache entry trên instance cao, dù từng session chưa chạm OPEN_CURSORS.

## 8. ORA-01000: nguyên nhân thường gặp

ORA-01000 là tín hiệu session cần mở thêm cursor nhưng không còn slot theo OPEN_CURSORS. Nguyên nhân phổ biến:

1. Không đóng PreparedStatement/Statement.
2. Không đóng ResultSet.
3. Không đóng CallableStatement hoặc REF CURSOR.
4. Exception xảy ra trước khi close.
5. DAO trả ResultSet/Statement ra ngoài nhưng không quản lý ownership.
6. Connection được trả về pool trong khi statement vẫn mở.
7. Statement cache size quá lớn so với OPEN_CURSORS và workload.
8. SESSION_CACHED_CURSORS và statement cache được cấu hình mà không đo tổng cursor.
9. Code sinh quá nhiều SQL text khác nhau.
10. Stored procedure hoặc trigger mở cursor mà không đóng.
11. Batch/loop tạo statement mới ở mỗi vòng lặp.
12. Connection pool tạo nhiều session với cấu hình cache không hợp lý.

### 8.1 Leak trong vòng lặp

Anti-pattern:

~~~java
for (Order order : orders) {
    PreparedStatement statement =
        connection.prepareStatement(
            "UPDATE orders SET status = ? WHERE order_id = ?"
        );

    statement.setString(1, order.status());
    statement.setLong(2, order.id());
    statement.executeUpdate();
}
~~~

Mỗi vòng lặp tạo một PreparedStatement mới mà không đóng. Sau nhiều vòng lặp, session có thể tích lũy cursor.

Nên tạo statement một lần và tái sử dụng:

~~~java
String sql =
    "UPDATE orders SET status = ? WHERE order_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {

    for (Order order : orders) {
        statement.setString(1, order.status());
        statement.setLong(2, order.id());
        statement.addBatch();
    }

    statement.executeBatch();
}
~~~

Nếu batch quá lớn, chia thành các batch nhỏ để kiểm soát memory, transaction duration và redo. Sau mỗi batch có thể executeBatch và clearBatch theo thiết kế.

### 8.2 Leak khi exception xảy ra

Anti-pattern:

~~~java
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet resultSet = statement.executeQuery();

// Nếu xử lý dòng phát sinh exception, close có thể không được gọi.
process(resultSet);

resultSet.close();
statement.close();
~~~

Nếu process() ném exception, hai lệnh close cuối không chạy.

Try-with-resources bảo đảm close:

~~~java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    try (ResultSet resultSet = statement.executeQuery()) {
        process(resultSet);
    }
}
~~~

### 8.3 Leak trong stored procedure

PL/SQL cũng có thể mở cursor. Ví dụ explicit cursor cần được đóng:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id FROM orders WHERE status = 'PENDING';
    l_order_id orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders INTO l_order_id;
        EXIT WHEN c_orders%NOTFOUND;
        -- Process current row.
    END LOOP;

    CLOSE c_orders;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        RAISE;
END;
/
~~~

Cursor FOR loop tự quản lý OPEN/FETCH/CLOSE:

~~~sql
BEGIN
    FOR r IN (
        SELECT order_id
        FROM orders
        WHERE status = 'PENDING'
    ) LOOP
        -- Process current row.
        NULL;
    END LOOP;
END;
/
~~~

Nếu procedure mở SYS_REFCURSOR để trả cho client, ownership chuyển sang caller; caller phải đóng ResultSet/REF CURSOR sau khi đọc xong.

## 9. Phân biệt OPEN_CURSORS, SESSION_CACHED_CURSORS và statement cache

Đây là phần dễ nhầm nhất khi xử lý ORA-01000.

| Cơ chế | Nơi hoạt động | Mục đích | Có thay thế close không? |
|---|---|---|---|
| OPEN_CURSORS | Oracle session | Giới hạn cursor handle đang mở | Không |
| SESSION_CACHED_CURSORS | Oracle session | Cache cursor đã đóng để giảm soft parse | Không |
| JDBC implicit statement cache | Oracle JDBC connection/driver | Tái sử dụng PreparedStatement/CallableStatement | Không |
| JDBC explicit statement cache | Oracle JDBC connection/driver | Tái sử dụng statement theo key do ứng dụng quản lý | Không |
| Shared pool/library cache | Oracle instance | Chia sẻ SQL area, execution plan và metadata | Không |

### 9.1 SESSION_CACHED_CURSORS

SESSION_CACHED_CURSORS cho phép Oracle session giữ cache các cursor đã đóng để giảm chi phí soft parse khi cùng SQL được parse lại.

Nó khác JDBC statement cache:

- Session cursor cache do Oracle database quản lý.
- JDBC statement cache do Oracle JDBC driver quản lý.
- Hai cơ chế có thể cùng hoạt động.
- Cả hai đều không miễn trừ việc đóng ResultSet/Statement.
- Tăng SESSION_CACHED_CURSORS không phải cách chữa leak cursor.

### 9.2 Statement cache và cursor count

JDBC statement cache có thể giữ các statement/cursor đã đóng về mặt API nhưng vẫn được cache để tái sử dụng. Do đó, tăng cache size có thể làm số cursor được giữ trong session tăng.

Khi sizing, phải xem cache size cùng OPEN_CURSORS và số cursor phát sinh bởi workload. Đừng cấu hình cache 200 chỉ vì database OPEN_CURSORS là 300; một request còn có thể mở nhiều cursor khác từ ResultSet, callable statement, metadata và PL/SQL.

### 9.3 Shared pool không phải nơi chữa ORA-01000

Flush shared pool hoặc tăng shared pool không phải biện pháp chuẩn để chữa ORA-01000. Shared pool quản lý SQL area dùng chung; OPEN_CURSORS là giới hạn cursor handle theo session.

Không chạy lệnh flush shared pool trên production chỉ để thử. Việc đó có thể gây hard parse tăng đột biến và ảnh hưởng toàn instance mà không xử lý leak của session.

## 10. Cấu hình statement cache trong ứng dụng Java

Nên cấu hình cache một lần cho mỗi physical connection hoặc tại cấu hình connection pool. Không bật/tắt cache liên tục trong request.

Ví dụ cấu hình trực tiếp trên Oracle JDBC connection:

~~~java
import oracle.jdbc.OracleConnection;
import java.sql.Connection;
import java.sql.SQLException;

public final class OracleJdbcSettings {
    private OracleJdbcSettings() {}

    public static void configure(Connection connection)
            throws SQLException {

        OracleConnection oracle =
            connection.unwrap(OracleConnection.class);

        oracle.setStatementCacheSize(32);
        oracle.setImplicitCachingEnabled(true);
    }
}
~~~

Số 32 chỉ là ví dụ. Giá trị thực tế cần đo theo số SQL lặp lại, số cursor khác trong session và giới hạn OPEN_CURSORS.

### 10.1 Cấu hình ở connection pool

Với pool, physical connection được tạo và tái sử dụng. Nên cấu hình statement cache ở hook tạo physical connection hoặc cấu hình Oracle JDBC properties theo hướng dẫn của pool.

Tránh cấu hình cache ở mỗi lần lấy logical connection nếu việc đó làm thay đổi state liên tục hoặc tạo overhead.

Một số pool có statement cache riêng hoặc wrapper cache. Không nên bật đồng thời nhiều tầng cache mà không hiểu ownership và cách close. Kiểm tra tài liệu của pool đang dùng để biết pool có statement caching riêng hay chỉ chuyển tiếp Oracle JDBC cache.

### 10.2 Không chia sẻ PreparedStatement giữa thread

PreparedStatement có mutable bind values, ResultSet state và gắn với connection cụ thể. Không lưu PreparedStatement vào static field để nhiều thread dùng chung.

Mỗi thao tác nên lấy connection từ pool, tạo/lấy statement trong connection đó, bind value, execute và close. Cache driver thực hiện việc tái sử dụng an toàn trong phạm vi connection theo API của nó.

### 10.3 Cache size bắt đầu nhỏ

Một cách triển khai an toàn:

1. Đo số SQL text lặp lại nhiều nhất trên một physical connection.
2. Bật implicit caching với size nhỏ.
3. Đo cache hit/miss nếu driver/pool cung cấp metrics.
4. Đo cursor count và parse rate.
5. Tăng dần cache nếu throughput cải thiện và cursor headroom còn đủ.
6. Kiểm thử với pool max size và workload peak.

Không cần cache mọi câu SQL. Statement dùng một lần, SQL động quá đa dạng hoặc statement có lifecycle đặc biệt có thể không đem lại lợi ích.

## 11. Sizing OPEN_CURSORS và statement cache

Không có một giá trị đúng cho mọi ứng dụng. Cần tính số cursor đồng thời theo session ở tải cao điểm.

Các thành phần cần tính đến:

- Statement/PreparedStatement đang thực thi.
- ResultSet đang mở.
- CallableStatement và REF CURSOR.
- JDBC statement cache entries đang giữ.
- Session cursor cache.
- Cursor do PL/SQL, trigger, recursive SQL và metadata operation.
- Framework hoặc driver có thể mở cursor nội bộ.

Không cộng các số liệu một cách máy móc vì cách Oracle accounting và view thể hiện cache có thể khác nhau. Hãy đo current cursor count và peak cursor count trên session đại diện trong workload thật.

### 11.1 Headroom

Giữ khoảng dự phòng cho các luồng hiếm như báo cáo, batch, metadata, migration và thao tác quản trị. Nếu peak đã sát OPEN_CURSORS, một thay đổi nhỏ trong code có thể làm lỗi xuất hiện.

Có thể dùng mô hình ước lượng ban đầu:

~~~text
OPEN_CURSORS target
  >= peak active cursor demand
   + retained statement cache demand
   + operational headroom
~~~

Đây là mô hình sizing, không phải công thức accounting chính xác. Hãy validate bằng session statistics và V$OPEN_CURSOR trong môi trường có tải.

### 11.2 Tác động của connection pool

Giả sử:

- Pool tối đa 60 physical connections.
- Statement cache size là 40 cho mỗi connection.
- Một số request mở thêm 20 cursor ngoài cache.

Một session có thể giữ nhiều cursor hơn mức dự kiến nếu cache entries và cursor đang hoạt động cùng tồn tại. OPEN_CURSORS áp dụng riêng cho từng session; pool size không trực tiếp nhân OPEN_CURSORS của một session, nhưng tổng cursor trên database tăng theo số session.

Pool quá lớn cũng làm tăng số session, PGA/session state, network connection và cursor cache tổng thể. Sizing pool và statement cache cần được xem cùng nhau.

### 11.3 Khi nào tăng OPEN_CURSORS?

Chỉ tăng khi:

- Code đã đóng tài nguyên đúng cách.
- Không có leak tăng dần theo thời gian.
- Peak workload thực sự cần nhiều cursor đồng thời.
- Statement cache size được đặt có chủ đích.
- Session cursor cache và PL/SQL workload đã được xem xét.
- Có headroom phù hợp với bộ nhớ và tài nguyên database.
- Đã kiểm thử thay đổi trên môi trường tương đương.

Tăng OPEN_CURSORS không tự phân bổ toàn bộ cursor limit thành memory cố định, nhưng session có thể sử dụng thêm tài nguyên khi mở thêm cursor. Không tăng vô hạn và không dùng thay đổi tham số để che một leak.

## 12. Chẩn đoán ORA-01000 trong Oracle

Bắt đầu bằng xác định session gây lỗi, thời điểm và workload. Cần biết lỗi đến từ application service, batch, scheduler job hay stored procedure.

### 12.1 Kiểm tra cấu hình

~~~sql
SHOW PARAMETER open_cursors;
SHOW PARAMETER session_cached_cursors;
~~~

Các giá trị này cho biết giới hạn và session cursor cache hiện tại. So sánh với cấu hình pool, statement cache và số cursor quan sát được.

### 12.2 Lấy SID của session hiện tại

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid
FROM dual;
~~~

Nếu điều tra từ DBA session khác, tìm session ứng dụng trong V$SESSION theo username, machine, program, module, service_name hoặc client_identifier.

~~~sql
SELECT sid,
       serial#,
       username,
       machine,
       program,
       module,
       action,
       status,
       sql_id,
       logon_time
FROM v$session
WHERE username = 'APP_USER'
ORDER BY logon_time;
~~~

Thay APP_USER bằng schema ứng dụng. Trong RAC, dùng GV$SESSION và chú ý INST_ID.

### 12.3 Xem số cursor hiện tại của session

~~~sql
SELECT s.sid,
       s.value AS opened_cursors_current
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name = 'opened cursors current'
  AND s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'));
~~~

Có thể xem thêm peak:

~~~sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name IN (
    'opened cursors current',
    'opened cursors cumulative'
)
AND s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'));
~~~

opened cursors current cho biết số cursor đang được session giữ theo accounting của Oracle. opened cursors cumulative là tổng số cursor đã mở trong vòng đời session, không phải số đang mở tại thời điểm truy vấn.

### 12.4 Xem danh sách cursor của session

~~~sql
SELECT sid,
       cursor_type,
       sql_id,
       COUNT(*) AS cursor_count
FROM v$open_cursor
WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
GROUP BY sid, cursor_type, sql_id
ORDER BY cursor_count DESC, sql_id;
~~~

Xem chi tiết:

~~~sql
SELECT sid,
       cursor_type,
       sql_id,
       last_sql_active_time,
       sql_text
FROM v$open_cursor
WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
ORDER BY last_sql_active_time DESC;
~~~

V$OPEN_CURSOR có thể liệt kê cursor đang mở, cursor đã parse hoặc cursor nằm trong cache tùy loại. Vì vậy, không coi mọi dòng là một ResultSet đang được ứng dụng đọc. Kết hợp cursor_type, current statistic, SQL_ID và hành vi application để suy luận.

### 12.5 Tìm session có số cursor cao

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.machine,
       s.program,
       st.value AS opened_cursors_current
FROM v$session s
JOIN v$sesstat st
  ON st.sid = s.sid
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
WHERE sn.name = 'opened cursors current'
  AND s.username IS NOT NULL
ORDER BY st.value DESC
FETCH FIRST 20 ROWS ONLY;
~~~

FETCH FIRST yêu cầu phiên bản Oracle hỗ trợ row limiting clause. Với release cũ hơn, dùng inline view và ROWNUM.

Trong RAC, thay V$ bằng GV$ và join theo cả INST_ID lẫn SID.

### 12.6 Xem SQL và module

Nếu session có SQL_ID:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       parse_calls,
       loads,
       invalidations,
       sql_text
FROM v$sql
WHERE sql_id = :sql_id;
~~~

SQL trong V$SQL giúp hiểu câu lệnh, parse và execution. Nó không chứng minh một SQL_ID duy nhất gây leak. Một session có thể mở nhiều cursor cho nhiều SQL khác nhau; cần liên hệ với module/action và call stack ứng dụng.

## 13. Theo dõi leak theo thời gian

Một snapshot đơn lẻ có thể không đủ. Leak thường biểu hiện bằng số cursor tăng dần theo request hoặc theo thời gian và không giảm sau khi request hoàn tất.

Có thể lấy mẫu định kỳ:

- SID và SERIAL#.
- MODULE/ACTION.
- OPENED_CURSORS_CURRENT.
- SQL_ID.
- Cursor type và số lượng.
- Pool connection identity nếu ứng dụng ghi nhận.
- Số request đang xử lý và thread name.

Ví dụ lấy số cursor current theo session:

~~~sql
SELECT s.sid,
       s.serial#,
       s.module,
       s.action,
       s.machine,
       st.value AS current_cursors
FROM v$session s
JOIN v$sesstat st
  ON st.sid = s.sid
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
WHERE sn.name = 'opened cursors current'
  AND s.username = 'APP_USER'
ORDER BY st.value DESC;
~~~

Lấy mẫu ở các thời điểm sau khi pool ổn định, sau tải bình thường và sau tải cao. Nếu cursor count tăng theo số request nhưng không trở về baseline sau khi request hoàn tất, hãy kiểm tra resource lifecycle.

### 13.1 Dùng MODULE và ACTION

Ứng dụng có thể đặt module/action để DBA phân biệt workload:

~~~java
try (Connection connection = dataSource.getConnection()) {
    try (var call = connection.prepareCall(
            "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(?, ?); END;")) {
        call.setString(1, "order-service");
        call.setString(2, "find-orders");
        call.execute();
    }

    // Execute application SQL on this connection.
}
~~~

Ví dụ chỉ minh họa. Cần reset module/action hoặc đặt giá trị phù hợp khi connection được trả về pool để tránh request sau bị gắn nhầm nhãn. Có thể dùng wrapper/interceptor của ứng dụng để quản lý.

### 13.2 Phân biệt leak với workload peak

Cursor count cao không luôn là leak. Một report có thể cố ý mở nhiều cursor đồng thời; procedure có thể mở nhiều REF CURSOR; một transaction có thể dùng nhiều PreparedStatement.

Dấu hiệu leak:

- Cursor count tăng theo thời gian mà không giảm.
- Cùng một SQL text xuất hiện lặp nhiều lần trong cursor list.
- Lỗi xuất hiện sau một số lượng request tương đối ổn định.
- Restart connection pool làm số cursor giảm mạnh nhưng sau đó tăng trở lại.
- Heap/thread dump cho thấy object Statement/ResultSet còn được giữ.

Dấu hiệu workload peak:

- Cursor count tăng trong lúc batch/report chạy rồi giảm sau khi hoàn tất.
- Số cursor tương ứng với số query/REF CURSOR được mở có chủ đích.
- Lỗi chỉ xảy ra ở tải đồng thời cao và không tăng theo thời gian.
- Resource cleanup hoạt động nhưng concurrency vượt capacity.

## 14. Điều tra từ phía Java

Database view cho biết session và cursor; Java heap/thread diagnostics giúp tìm object chưa được đóng.

Các hướng điều tra:

- Bật logging hoặc leak detection của connection pool.
- Kiểm tra code path có prepareStatement/createStatement/prepareCall.
- Tìm mọi ResultSet được mở và vị trí close.
- Kiểm tra exception path và early return.
- Kiểm tra method trả Statement/ResultSet ra ngoài.
- Kiểm tra static field, cache ứng dụng hoặc collection giữ JDBC object.
- Kiểm tra thread bị block trong lúc giữ ResultSet.
- Kiểm tra streaming response chưa được đóng.
- Kiểm tra framework ORM/native query và cursor-based pagination.

### 14.1 Pool leak detection

Một số connection pool có leak detection threshold để ghi log khi Connection được giữ quá lâu. Tính năng này chủ yếu phát hiện connection checkout không được trả lại; nó không luôn phát hiện mọi Statement leak nếu logical connection vẫn được trả về.

Một số pool có statement tracking hoặc cleanup wrapper. Hãy đọc tài liệu pool cụ thể và bật diagnostic trong môi trường kiểm thử trước khi dùng ở production vì instrumentation có thể tăng overhead.

### 14.2 Java Flight Recorder và heap dump

Nếu nghi ngờ Java giữ JDBC object:

- Dùng Java Flight Recorder để quan sát allocation, thread và thời gian giữ resource.
- Lấy heap dump trong môi trường kiểm soát.
- Tìm PreparedStatement, OraclePreparedStatement, ResultSet và wrapper references.
- Truy ngược GC root để tìm collection, singleton hoặc thread đang giữ object.
- Dùng thread dump để xác định code đang fetch hoặc chờ I/O.

Không kết luận leak chỉ từ heap object count cao; cache có thể giữ object có chủ đích. Cần so sánh object count theo thời gian và trạng thái connection.

### 14.3 Instrumentation close

Trong test, có thể wrap DataSource/Connection/Statement để ghi nhận thời điểm tạo và close, SQL fingerprint và request ID. Không log bind value nhạy cảm.

Instrumentation giúp tìm statement không được close theo call path. Tắt hoặc giảm mức logging sau khi tìm được nguyên nhân để tránh overhead và log volume.

## 15. Sử dụng statement cache đúng cách

Một quy trình sử dụng tốt:

1. Tạo statement trong phạm vi connection.
2. Bind parameter.
3. Execute.
4. Đọc hết kết quả cần thiết.
5. Đóng ResultSet.
6. Đóng Statement.
7. Trả Connection về pool.

Với implicit cache, bước close là tín hiệu để driver đưa statement vào cache nếu phù hợp.

### 15.1 Tái sử dụng trong một method

~~~java
String sql =
    "SELECT order_id, total_amount " +
    "FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    for (long customerId : customerIds) {
        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                long id = resultSet.getLong("order_id");
                BigDecimal amount =
                    resultSet.getBigDecimal("total_amount");
                // Map or process.
            }
        }
    }
}
~~~

Statement được dùng lại trong cùng connection, còn ResultSet được đóng sau từng lần execute. Khi đóng PreparedStatement ở cuối, driver có thể cache nó.

### 15.2 Clear parameters và batch state

Khi tái sử dụng PreparedStatement, bind lại mọi parameter cần thiết cho mỗi lần execute. JDBC có thể giữ bind value từ lần trước nếu code không ghi đè mọi vị trí.

Với batch, quản lý addBatch/executeBatch/clearBatch đúng cách. Không để batch command cũ vô tình được gửi lại. Nếu dùng statement cache, driver xử lý reset trạng thái theo hợp đồng API, nhưng ứng dụng vẫn phải dùng statement đúng quy tắc.

### 15.3 ResultSet concurrency và holdability

ResultSet type, concurrency và holdability ảnh hưởng hành vi statement và khả năng cache. Nếu ứng dụng yêu cầu scrollable/updatable ResultSet hoặc giữ cursor qua commit, hãy xác minh driver có hỗ trợ caching cho loại statement đó và hiểu tác động tới cursor lifecycle.

Mặc định FORWARD_ONLY và READ_ONLY thường đủ cho phần lớn truy vấn ứng dụng. Chỉ chọn scrollable/updatable khi nghiệp vụ thực sự cần.

## 16. Tối ưu SQL để giảm statement/cursor churn

Statement cache hoạt động tốt nhất khi workload có SQL text ổn định.

Các thực hành:

- Dùng bind variables cho giá trị dữ liệu.
- Tránh nối literal vào SQL string.
- Tránh tạo câu SQL khác nhau chỉ vì thứ tự điều kiện thay đổi.
- Chỉ tạo dynamic SQL khi cấu trúc thật sự thay đổi.
- Giới hạn số dạng SQL động.
- Dùng PreparedStatement cho câu lệnh lặp.
- Không tạo statement mới trong vòng lặp nếu có thể tái sử dụng.
- Không cache statement dùng một lần nếu không có lợi ích.

### 16.1 Bind variable và cursor sharing

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
~~~

SQL dùng bind variable có thể được tái sử dụng với nhiều giá trị. Oracle có thể chia sẻ cursor nếu các điều kiện về SQL text, bind metadata, optimizer environment và object metadata phù hợp.

Bind variable không bảo đảm mọi execution dùng đúng một child cursor. Bind peeking, adaptive cursor sharing, datatype mismatch và optimizer environment có thể tạo nhiều child cursor. Tuy nhiên, nó vẫn là thực hành tốt để tránh literal SQL proliferation.

### 16.2 Datatype consistency

Bind parameter nên dùng kiểu dữ liệu tương thích với cột. Ví dụ cột NUMBER nên bind bằng setLong/setBigDecimal phù hợp thay vì setString nếu không cần chuyển đổi.

Datatype mismatch có thể gây implicit conversion, ảnh hưởng index access và cursor sharing. Hãy kiểm tra JDBC setter tương ứng với kiểu Oracle column.

## 17. ResultSet fetch và cursor lifetime

Một query lớn có thể giữ server cursor mở trong toàn bộ thời gian ứng dụng fetch kết quả. Đây không nhất thiết là leak nếu ứng dụng đang đọc dữ liệu, nhưng có thể tiêu thụ cursor lâu và giữ connection khỏi pool.

### 17.1 Fetch size

JDBC fetch size gợi ý số hàng driver lấy mỗi round-trip:

~~~java
statement.setFetchSize(200);
~~~

Fetch size có thể giảm số lần network round-trip và ảnh hưởng memory client. Nó không trực tiếp giảm số cursor đang mở: ResultSet vẫn gắn với cursor cho đến khi đóng.

Chọn fetch size theo kích thước row, latency mạng, memory và workload. Giá trị quá lớn có thể làm tăng memory; quá nhỏ tăng round-trip.

### 17.2 Streaming và connection pool

Nếu API trả stream cho caller, connection có thể bị giữ đến khi caller đọc xong hoặc đóng stream. Một client chậm có thể giữ cursor và connection lâu, làm pool cạn.

Có thể cân nhắc:

- Đọc và map thành page nhỏ rồi đóng connection.
- Dùng keyset pagination.
- Giới hạn thời gian đọc.
- Đảm bảo stream có AutoCloseable và được caller đóng.
- Không giữ ResultSet mở qua nhiều tầng ứng dụng không kiểm soát.

### 17.3 Pagination

Offset pagination có thể yêu cầu database đọc/bỏ qua nhiều dòng ở page sâu. Keyset pagination thường hiệu quả hơn với thứ tự ổn định:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE order_date < :last_order_date
   OR (order_date = :last_order_date
       AND order_id < :last_order_id)
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Pagination không tự sửa cursor leak, nhưng giúp giảm thời gian giữ ResultSet và Connection cho mỗi request.

## 18. Các view và chỉ số cần biết

| View/parameter | Dùng để làm gì |
|---|---|
| V$SESSION | Tìm session, user, module, SQL_ID và trạng thái |
| V$SESSTAT | Xem statistic theo session |
| V$STATNAME | Tra tên statistic |
| V$OPEN_CURSOR | Xem cursor được ghi nhận trong session |
| V$SQL | Xem SQL text, executions, parse calls và child cursor |
| V$PARAMETER | Xem giá trị parameter trong instance/session context |
| GV$SESSION / GV$OPEN_CURSOR | Điều tra nhiều instance trong RAC |
| OPEN_CURSORS | Giới hạn cursor handle mỗi session |
| SESSION_CACHED_CURSORS | Kích thước session cursor cache |

Các view V$ thường yêu cầu quyền catalog hoặc quyền SELECT phù hợp. Tài khoản ứng dụng không nên được cấp quyền rộng chỉ để tự chạy chẩn đoán production. DBA có thể cung cấp view/report giới hạn theo session.

### 18.1 Cursor type trong V$OPEN_CURSOR

V$OPEN_CURSOR có cột CURSOR_TYPE giúp phân biệt loại cursor được theo dõi, chẳng hạn cursor đang mở, cursor được session cache hoặc cursor liên quan PL/SQL tùy release. Tập giá trị và cách diễn giải cần kiểm tra theo phiên bản Oracle.

Đừng dựa vào một loại cursor duy nhất để kết luận. So sánh với opened cursors current và thử đóng tài nguyên trong session thử nghiệm để hiểu hành vi driver.

### 18.2 RAC

Trong RAC, session tồn tại trên một instance cụ thể. Dùng GV$ views và ghép theo INST_ID, SID, SERIAL# để không nhầm session có SID trùng ở instance khác.

Nếu connection pool kết nối qua service RAC, request có thể được phân phối đến nhiều instance. Hãy kiểm tra cả instance đang có session gây lỗi và module/action của nó.

## 19. Quy trình xử lý ORA-01000 theo từng bước

Khi nhận lỗi ORA-01000:

### Bước 1: Xác định phạm vi

- Lỗi xuất hiện ở một service hay nhiều service?
- Chỉ một endpoint/batch hay toàn hệ thống?
- Xảy ra sau bao nhiêu request hoặc bao lâu?
- Có trùng với deployment hoặc thay đổi pool/cache không?
- Chỉ một RAC instance hay tất cả instance?

### Bước 2: Xác định session

Dùng V$SESSION/GV$SESSION để lấy SID, SERIAL#, USERNAME, MACHINE, PROGRAM, MODULE, ACTION và SQL_ID.

### Bước 3: Đo cursor count

Lấy opened cursors current và danh sách V$OPEN_CURSOR cho session. So sánh với OPEN_CURSORS.

### Bước 4: Tìm SQL và loại cursor lặp

Nhóm theo SQL_ID/CURSOR_TYPE. Kiểm tra có nhiều cursor lặp từ cùng code path hay procedure không.

### Bước 5: Kiểm tra Java lifecycle

Tìm statement/resultset không được đóng, đặc biệt trong exception path, loop, async callback, streaming và REF CURSOR.

### Bước 6: Kiểm tra statement cache và pool

Ghi nhận:

- Pool max/min size.
- Số physical connection.
- Oracle JDBC driver version.
- Implicit/explicit cache enabled hay không.
- Statement cache size trên mỗi physical connection.
- Pool có statement cache riêng không.
- Session cursor cache size.

### Bước 7: Sửa code và kiểm thử

Bổ sung try-with-resources, đóng REF CURSOR, sửa ownership và giới hạn concurrency. Chạy workload lặp đủ lâu để xem cursor count có ổn định không.

### Bước 8: Điều chỉnh tham số nếu cần

Sau khi xác nhận workload hợp lệ cần nhiều cursor đồng thời, DBA có thể điều chỉnh OPEN_CURSORS và cache size theo capacity plan. Ghi lại giá trị trước/sau và theo dõi tài nguyên.

## 20. Ví dụ điều tra và xử lý

Giả sử một ứng dụng Java chạy nhiều request tìm đơn hàng. Sau vài phút, log xuất hiện:

~~~text
java.sql.SQLException: ORA-01000: maximum open cursors exceeded
~~~

DBA thấy session APP_USER có OPEN_CURSORS là 300 và opened cursors current tăng dần từ 80 lên 280.

V$OPEN_CURSOR cho thấy nhiều SQL_ID lặp lại với cursor type liên quan statement/PLSQL. Điều tra Java tìm được method sau:

~~~java
public Order findOrder(Connection connection, long orderId)
        throws SQLException {

    PreparedStatement statement =
        connection.prepareStatement(
            "SELECT order_id, status FROM orders WHERE order_id = ?"
        );

    statement.setLong(1, orderId);
    ResultSet resultSet = statement.executeQuery();

    if (resultSet.next()) {
        return new Order(
            resultSet.getLong("order_id"),
            resultSet.getString("status")
        );
    }

    return null;
}
~~~

Method không đóng ResultSet hoặc PreparedStatement. Sửa:

~~~java
public Order findOrder(Connection connection, long orderId)
        throws SQLException {

    String sql =
        "SELECT order_id, status FROM orders WHERE order_id = ?";

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, orderId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (resultSet.next()) {
                return new Order(
                    resultSet.getLong("order_id"),
                    resultSet.getString("status")
                );
            }
        }
    }

    return null;
}
~~~

Sau khi triển khai, đo lại opened cursors current theo session. Nếu số cursor trở về baseline sau mỗi request và không tăng liên tục, dấu hiệu leak đã được xử lý. Nếu số cursor vẫn cao nhưng ổn định, kiểm tra cache size và workload peak.

Không nên chỉ tăng OPEN_CURSORS từ 300 lên 1000 rồi kết luận đã sửa lỗi. Nếu leak còn tồn tại, session sẽ tiếp tục tích lũy cursor và lỗi chỉ xuất hiện muộn hơn.

## 21. Kiểm thử statement cache và cursor lifecycle

Kiểm thử nên đo cả hiệu năng và tài nguyên.

Một kế hoạch kiểm thử:

1. Chạy workload baseline khi statement cache tắt.
2. Ghi throughput, latency, parse calls và opened cursors current.
3. Bật implicit cache với size nhỏ.
4. Chạy cùng workload và cùng số physical connections.
5. So sánh cache hit/parse reduction nếu có metric.
6. Đo peak và steady-state cursor count.
7. Tăng concurrency và thời gian chạy.
8. Thử exception, timeout, cancellation và connection return.
9. Thử REF CURSOR, batch và streaming query.
10. Kiểm tra cursor count sau khi workload kết thúc.

### 21.1 Tiêu chí thành công

- Không có ORA-01000.
- Cursor count không tăng vô hạn theo số request.
- Sau khi request hoàn tất, active cursor giảm về mức baseline phù hợp.
- Cache không chiếm phần lớn OPEN_CURSORS headroom.
- Throughput/latency cải thiện hoặc ít nhất không suy giảm đáng kể.
- Pool không bị cạn connection do query/stream giữ lâu.
- Không có statement/resultset được dùng lại sau close.

### 21.2 Kiểm thử pool recycle

Thử đóng logical connection rồi lấy lại connection từ pool. Xác nhận:

- Physical session có thể được tái sử dụng.
- Statement cache hoạt động theo cấu hình.
- Module/action được reset hoặc gắn lại đúng.
- Không có ResultSet/Statement từ request cũ còn được caller sử dụng.
- Cursor count ổn định qua nhiều vòng checkout/return.

## 22. Checklist phòng ngừa ORA-01000

### Trong Java code

- [ ] Dùng try-with-resources cho Connection, Statement và ResultSet.
- [ ] Đóng CallableStatement và REF CURSOR.
- [ ] Không trả ResultSet ra ngoài nếu ownership không rõ.
- [ ] Không giữ PreparedStatement trong static field.
- [ ] Không chia sẻ Statement giữa thread.
- [ ] Tái sử dụng statement trong loop khi phù hợp.
- [ ] Dùng bind variable và SQL text ổn định.
- [ ] Đóng ResultSet trước khi trả connection về pool.
- [ ] Kiểm tra exception path, cancellation và early return.
- [ ] Kiểm tra streaming API và ORM/native query.

### Statement cache và pool

- [ ] Bật cache có chủ đích, bắt đầu bằng size nhỏ.
- [ ] Cấu hình trên physical connection theo hướng dẫn pool.
- [ ] Biết cache size áp dụng trên từng connection.
- [ ] Không bật nhiều tầng statement cache không cần thiết.
- [ ] Đo cache hit/miss nếu có metric.
- [ ] Sizing pool cùng statement cache và OPEN_CURSORS.
- [ ] Không thay đổi cache size trên mỗi request.

### Oracle database

- [ ] Theo dõi OPEN_CURSORS và SESSION_CACHED_CURSORS.
- [ ] Đo opened cursors current theo session.
- [ ] Dùng V$OPEN_CURSOR để điều tra loại cursor và SQL_ID.
- [ ] Dùng GV$ views trong RAC.
- [ ] Kiểm tra PL/SQL explicit cursor và REF CURSOR.
- [ ] Giữ headroom cho workload peak.
- [ ] Chỉ tăng OPEN_CURSORS sau khi đo và loại trừ leak.

### Vận hành

- [ ] Có cảnh báo khi cursor count tiến gần giới hạn.
- [ ] Có module/action để xác định code path.
- [ ] Có log pool leak detection phù hợp.
- [ ] Có test tải kéo dài, không chỉ test ngắn.
- [ ] Có quy trình thu thập session, SQL_ID và cursor detail khi sự cố.
- [ ] Ghi lại thay đổi driver, pool, cache và database parameter.

## 23. Kết luận

Oracle JDBC statement cache giúp tái sử dụng PreparedStatement/CallableStatement và giảm chi phí prepare/parse cho SQL lặp lại. Implicit caching thường là lựa chọn đơn giản: ứng dụng vẫn đóng statement như bình thường, driver đưa statement đủ điều kiện trở lại cache. Cache gắn với physical connection, vì vậy cache size cần được tính theo từng session và tổng quy mô connection pool.

Server-side cursor là tài nguyên theo session dùng để thực thi SQL và fetch kết quả. OPEN_CURSORS đặt giới hạn số cursor handle mỗi session; SESSION_CACHED_CURSORS là cơ chế cache cursor riêng của Oracle. Cả hai không thay thế JDBC resource cleanup.

ORA-01000 thường xuất phát từ Statement/ResultSet/REF CURSOR không được đóng, cursor đồng thời vượt capacity hoặc cache được cấu hình quá lớn. Hãy xác định session, đo opened cursors current, xem V$OPEN_CURSOR, truy vết SQL/module về Java code, sửa lifecycle bằng try-with-resources và kiểm thử tải kéo dài. Chỉ điều chỉnh OPEN_CURSORS sau khi hiểu peak cursor demand và đã loại trừ leak.
