# Fetch size, truyền kết quả theo luồng và hành vi riêng của trình điều khiển

Một câu truy vấn có thể trả về hàng trăm nghìn hoặc hàng triệu hàng. Nếu ứng dụng Java nhận toàn bộ kết quả vào bộ nhớ rồi mới xử lý, heap có thể tăng nhanh, GC hoạt động nhiều và ứng dụng dễ gặp lỗi thiếu bộ nhớ. Nếu ứng dụng đọc từng hàng nhưng trình điều khiển JDBC vẫn tải toàn bộ kết quả về client trước, cách viết vòng lặp đó chưa thực sự truyền dữ liệu theo luồng.

Fetch size là gợi ý về số hàng mà trình điều khiển nên lấy trong một lần trao đổi dữ liệu. Kết hợp fetch size với cơ chế cursor hoặc buffering thích ứng của driver, ứng dụng có thể xử lý kết quả theo từng phần, giảm bộ nhớ đỉnh và điều chỉnh số lượt trao đổi qua mạng. Tuy nhiên, JDBC chỉ định nghĩa fetch size như một hint; mỗi driver có thể diễn giải khác nhau. Một số driver dùng server-side cursor, một số dùng row prefetch, một số dùng adaptive buffering, còn một số có thể bỏ qua gợi ý trong một số chế độ.

Bài học thuộc chương **Ứng dụng Java** của module DATABASE_PERFORMANCE. Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, lựa chọn fetch size phải dựa trên kích thước hàng, độ trễ mạng, concurrency, heap của JVM, cách driver truyền dữ liệu và thời gian transaction được giữ mở.

## 1. Fetch size là gì?

Trong JDBC, phương thức Statement.setFetchSize(int rows) đặt gợi ý về số hàng cần lấy khi cần thêm dữ liệu cho ResultSet. Có thể đặt trên Statement hoặc PreparedStatement trước khi thực thi truy vấn:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc và xử lý hàng hiện tại
        }
    }
}
~~~

Giá trị 500 trong ví dụ là số hàng, không phải số byte. Với hàng nhỏ, 500 hàng có thể chiếm ít bộ nhớ; với hàng có nhiều cột văn bản hoặc dữ liệu lớn, cùng fetch size có thể chiếm nhiều bộ nhớ hơn đáng kể.

Fetch size là gợi ý cho driver, không phải bảo đảm rằng:

- Driver sẽ luôn lấy chính xác số hàng đó trong mỗi lần đọc mạng.
- Server sẽ tạo cursor cho mọi truy vấn.
- Client chỉ giữ tối đa đúng số hàng được chỉ định.
- Truy vấn sẽ trả kết quả nhanh hơn trong mọi workload.
- Kích thước fetch được tính theo byte hoặc giới hạn tổng bộ nhớ.

Theo JDBC, fetch size không được là số âm; giá trị 0 có nghĩa là bỏ qua hint và để driver dùng hành vi mặc định. Một số driver cung cấp extension riêng với giá trị đặc biệt, chẳng hạn Connector/J dùng Integer.MIN_VALUE cho chế độ streaming legacy. Đây không phải hành vi portable và không nên dùng trong ứng dụng đa driver nếu chưa xác nhận tài liệu của đúng driver và phiên bản đang triển khai.

## 2. Luồng dữ liệu từ database đến ứng dụng

Khi ứng dụng gọi executeQuery(), dữ liệu không nhất thiết được truyền hết về JVM ngay lập tức. Cách truyền phụ thuộc giao thức và driver:

~~~text
Ứng dụng Java
    |
    | executeQuery()
    v
JDBC Driver
    |
    | gửi SQL và tham số
    v
Database Server
    |
    | thực thi, tạo kết quả
    v
Cursor / response buffer / row prefetch
    |
    | từng lô hoặc theo nhu cầu
    v
JDBC ResultSet
    |
    | rs.next(), đọc cột, xử lý hàng
    v
Ứng dụng tiêu thụ dữ liệu
~~~

Có ba mô hình phổ biến:

| Mô hình | Cách hoạt động | Hệ quả chính |
| --- | --- | --- |
| Client-side buffering | Driver tải phần lớn hoặc toàn bộ kết quả về client | Dễ truy cập kết quả, nhưng heap có thể tăng theo tổng số hàng |
| Server-side cursor hoặc fetch theo lô | Server giữ trạng thái cursor; client yêu cầu thêm hàng theo từng lô | Giảm dữ liệu phải giữ ở client, nhưng cursor và transaction có thể tồn tại lâu |
| Adaptive buffering/row prefetch | Driver quản lý buffer và nạp thêm dữ liệu theo nhu cầu hoặc chính sách riêng | Cân bằng bộ nhớ và số lượt trao đổi, phụ thuộc driver |

Các mô hình có thể được kết hợp. Ví dụ, driver có thể dùng cursor ở server và vẫn buffer một lô hàng ở client. Một vòng lặp while (rs.next()) chỉ mô tả cách ứng dụng tiêu thụ dữ liệu; nó không chứng minh driver đang dùng server-side cursor.

## 3. Vì sao fetch size ảnh hưởng hiệu năng?

Fetch size tác động đến ba yếu tố chính: số lượt trao đổi, bộ nhớ phía client và thời gian giữ tài nguyên phía server.

### 3.1. Số lượt trao đổi qua mạng

Giả sử kết quả có N hàng và driver thực sự lấy theo lô F hàng. Số lượt lấy lô có thể ước lượng:

\[
\text{Fetch batches} \approx \left\lceil \frac{N}{F} \right\rceil
\]

Ví dụ, kết quả có 100.000 hàng:

| Fetch size | Số lô ước lượng |
| ---: | ---: |
| 50 | 2.000 |
| 200 | 500 |
| 500 | 200 |
| 1.000 | 100 |

Ước lượng này chưa tính lượt gửi câu lệnh, metadata, handshake, retry hoặc khác biệt giao thức. Một số driver có thể gom hoặc tách request khác với công thức đơn giản trên.

Khi độ trễ mạng cao, nhiều lượt lấy lô nhỏ có thể làm tổng thời gian tăng vì ứng dụng phải chờ nhiều lần trao đổi. Tăng fetch size có thể giảm số lượt trao đổi, nhất là khi kết quả lớn và ứng dụng tiêu thụ gần như toàn bộ dữ liệu.

### 3.2. Bộ nhớ phía client

Fetch size lớn thường làm driver giữ nhiều hàng hơn trong buffer tại một thời điểm. Có thể ước lượng sơ bộ:

\[
M_{\text{batch}} \approx F \times S_{\text{row}} \times K
\]

Trong đó:

- F là fetch size.
- S_row là kích thước trung bình của một hàng sau khi giải mã.
- K là hệ số overhead của driver, object Java, chuỗi, mảng byte và cấu trúc buffer.

Đây chỉ là mô hình ước lượng. Driver có thể dùng buffer dạng byte, object hoặc nhiều vùng nhớ; một số kiểu dữ liệu lớn có cơ chế prefetch riêng. Heap thực tế còn phụ thuộc cách ứng dụng tạo object và giữ tham chiếu.

Fetch size nhỏ có thể giảm memory peak nhưng tăng số lần đọc mạng. Fetch size lớn có thể tăng throughput nhưng gây GC pressure, tăng thời gian cấp phát và làm nhiều truy vấn đồng thời cạnh tranh heap.

### 3.3. Tài nguyên phía server

Nếu driver dùng server-side cursor, database có thể phải giữ cursor, snapshot, transaction hoặc tài nguyên thực thi trong suốt quá trình ứng dụng đọc kết quả. Một consumer chậm có thể khiến connection và cursor bị chiếm lâu.

Với hệ MVCC, transaction đọc kéo dài có thể giữ snapshot lâu và trì hoãn dọn dẹp phiên bản cũ. Vì vậy, streaming giảm heap ở JVM nhưng có thể kéo dài thời gian giữ transaction và tài nguyên database. Cần đo cả hai phía.

## 4. Phân biệt fetch size, page size và batch size

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| Fetch size | Số hàng driver gợi ý lấy mỗi lần đọc từ database | JDBC driver và ResultSet |
| Page size | Số hàng ứng dụng yêu cầu trong một trang truy vấn | SQL/API/application |
| Batch size | Số thao tác hoặc bản ghi được gửi cùng một batch | JDBC batch ghi hoặc xử lý theo lô |

Ví dụ:

- LIMIT 500 hoặc FETCH FIRST 500 ROWS ONLY giới hạn số hàng của câu SQL.
- setFetchSize(500) gợi ý driver lấy kết quả theo các lô khoảng 500 hàng; nó không giới hạn tổng số hàng.
- addBatch() kết hợp executeBatch() gom nhiều thao tác ghi; đây là batch ghi, không phải fetch size đọc.

Một truy vấn có thể trả một triệu hàng, fetch size 500 và page size không áp dụng. Ngược lại, một API có thể lấy 500 hàng mỗi trang bằng keyset pagination, sau đó mỗi trang vẫn được driver fetch theo các lô nhỏ hơn hoặc bằng cách riêng.

## 5. Cách dùng fetch size trong JDBC

Đặt fetch size trước executeQuery() để driver có thể sử dụng gợi ý khi thiết lập cách đọc kết quả:

~~~java
String sql = """
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
    WHERE created_at >= ?
    ORDER BY created_at, order_id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql,
         ResultSet.TYPE_FORWARD_ONLY,
         ResultSet.CONCUR_READ_ONLY)) {

    statement.setFetchSize(500);
    statement.setTimestamp(1, Timestamp.from(fromTime));

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            long customerId = resultSet.getLong("customer_id");
            Timestamp createdAt = resultSet.getTimestamp("created_at");
            BigDecimal totalAmount = resultSet.getBigDecimal("total_amount");

            processOrder(orderId, customerId, createdAt, totalAmount);
        }
    }
}
~~~

Ví dụ dùng TYPE_FORWARD_ONLY và CONCUR_READ_ONLY vì luồng xử lý chỉ đi từ hàng đầu đến hàng cuối và không cập nhật trực tiếp qua ResultSet. Đây là lựa chọn thường phù hợp với export hoặc xử lý tuần tự. Nếu ứng dụng cần scroll ngược hoặc cập nhật hàng, phải xác định driver có hỗ trợ hay không; các khả năng đó có thể làm thay đổi cách buffer và tài nguyên cần dùng.

### Không tích lũy toàn bộ kết quả vào collection

Đoạn mã sau vẫn có thể dùng rất nhiều heap dù fetch size nhỏ:

~~~java
List<Order> orders = new ArrayList<>();

while (resultSet.next()) {
    orders.add(mapOrder(resultSet));
}
~~~

Ứng dụng đang giữ tất cả object trong danh sách. Fetch size chỉ điều chỉnh cách driver nạp hàng, không làm danh sách Java tự giải phóng.

Nếu mục tiêu là giảm bộ nhớ, hãy xử lý từng hàng hoặc từng batch nhỏ rồi ghi kết quả ra đích:

~~~java
while (resultSet.next()) {
    Order order = mapOrder(resultSet);
    writer.write(order);
    // Không giữ order trong một collection sống đến cuối truy vấn
}
~~~

Nếu cần tổng hợp, chỉ giữ trạng thái tổng hợp nhỏ thay vì toàn bộ hàng nguồn. Nếu cần chuyển dữ liệu sang dịch vụ khác, cân nhắc ghi vào file hoặc queue theo batch sau khi đã xác định ranh giới transaction phù hợp.

## 6. PostgreSQL JDBC: fetch theo cursor

PostgreSQL JDBC driver thường mặc định lấy toàn bộ kết quả về client khi fetch size bằng 0. Để dùng cursor-based fetching, các điều kiện quan trọng thường gồm:

- Đặt fetch size dương trên Statement/PreparedStatement.
- Connection ở chế độ không auto-commit trong lúc đọc.
- Dùng ResultSet forward-only.
- Giữ transaction mở cho đến khi đọc xong ResultSet.

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean previousAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        String sql = """
            SELECT event_id, account_id, occurred_at, event_type
            FROM account_events
            WHERE occurred_at < ?
            ORDER BY occurred_at, event_id
            """;

        try (PreparedStatement statement = connection.prepareStatement(
                 sql,
                 ResultSet.TYPE_FORWARD_ONLY,
                 ResultSet.CONCUR_READ_ONLY)) {

            statement.setFetchSize(400);
            statement.setTimestamp(1, Timestamp.from(cutoff));

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    consumeEvent(
                        rs.getLong("event_id"),
                        rs.getLong("account_id"),
                        rs.getTimestamp("occurred_at"),
                        rs.getString("event_type")
                    );
                }
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    } finally {
        connection.setAutoCommit(previousAutoCommit);
    }
}
~~~

Đoạn mã minh họa transaction do tác vụ này sở hữu trên một connection sạch lấy từ pool. Trong ứng dụng thực tế, nếu transaction do tầng gọi quản lý, không tự ý commit, rollback hoặc đổi auto-commit ở tầng repository. Hãy để đúng tầng sở hữu transaction quyết định ranh giới.

### Trade-off của cursor PostgreSQL

- Cursor giúp driver lấy từng lô thay vì materialize toàn bộ kết quả ở JVM.
- Transaction phải mở trong lúc cursor còn được sử dụng.
- Nếu ứng dụng đọc chậm hoặc thực hiện công việc mạng trong vòng lặp, snapshot có thể tồn tại lâu.
- Cursor và connection không nên được giữ qua thời gian chờ người dùng hoặc thao tác bên ngoài không cần thiết.
- Cần đóng ResultSet và Statement trước khi kết thúc transaction.

Nếu truy vấn cần hàng triệu bản ghi nhưng xử lý mỗi hàng mất nhiều thời gian, hãy cân nhắc batch theo khóa hoặc watermark để giới hạn tuổi transaction. Cách đó có thể tạo snapshot khác nhau giữa các batch, vì vậy cần quy định tính nhất quán nghiệp vụ.

## 7. MySQL Connector/J: useCursorFetch và chế độ streaming

MySQL Connector/J có hành vi riêng khi truyền ResultSet. Một lựa chọn là bật cursor fetch:

~~~text
jdbc:mysql://db-host:3306/appdb?useCursorFetch=true
~~~

Sau đó đặt fetch size dương:

~~~java
try (PreparedStatement statement = connection.prepareStatement(
         sql,
         ResultSet.TYPE_FORWARD_ONLY,
         ResultSet.CONCUR_READ_ONLY)) {

    statement.setFetchSize(500);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            processRow(rs);
        }
    }
}
~~~

useCursorFetch=true cho phép Connector/J sử dụng cursor-based fetching khi điều kiện và loại statement phù hợp; driver có thể bật server-side prepared statement để hỗ trợ. Hãy xác minh hành vi với phiên bản Connector/J đang dùng, vì URL property, prepared statement mode và các loại ResultSet ảnh hưởng đến cách truyền.

### Chế độ streaming đặc thù

Connector/J cũng có chế độ streaming legacy thường được kích hoạt bằng cách dùng ResultSet forward-only/read-only và đặt fetch size là Integer.MIN_VALUE. Đây là extension riêng của Connector/J, không phải quy tắc JDBC portable. Nó có thể giữ connection bận trong lúc đọc và hạn chế việc thực hiện câu lệnh khác trên cùng connection cho đến khi ResultSet được tiêu thụ hoặc đóng.

Không trộn lẫn hai cách cấu hình mà không hiểu khác biệt:

- Cursor fetch dùng fetch size dương và property useCursorFetch.
- Legacy streaming dùng giá trị đặc biệt Integer.MIN_VALUE theo hành vi của Connector/J.

Ưu tiên cơ chế được driver phiên bản hiện tại hỗ trợ và kiểm thử trên workload thực. Không dựa vào giá trị âm trong ứng dụng đa driver.

## 8. Oracle JDBC: row prefetch và fetch size

Oracle JDBC sử dụng row prefetch để lấy nhiều hàng trong một lần trao đổi. Statement.setFetchSize() là API JDBC tương ứng thường được dùng để điều chỉnh số hàng prefetch cho statement. Có thể đặt giá trị ở cấp statement:

~~~java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setFetchSize(300);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            processRow(rs);
        }
    }
}
~~~

Oracle JDBC cũng có các thuộc tính và API riêng liên quan đến default row prefetch. Giá trị hiệu lực có thể bị thay đổi bởi cấu hình ở connection, statement hoặc ResultSet theo phiên bản driver. Hãy đo thay vì giả định một giá trị fetch size sẽ luôn áp dụng như nhau cho mọi kiểu dữ liệu.

### Lưu ý với LOB và kiểu dữ liệu đặc biệt

LOB, LONG hoặc các kiểu dữ liệu có cách truyền riêng có thể ảnh hưởng đến row prefetch. Một hàng có CLOB/BLOB lớn không tương đương một hàng chỉ chứa vài số nguyên. Nếu ứng dụng cần đọc nội dung LOB, hãy dùng stream/locator theo API phù hợp và tiêu thụ dữ liệu trong thời gian tài nguyên còn hiệu lực.

Không nên tăng row prefetch mạnh chỉ để cải thiện truy vấn trả về nhiều LOB lớn. Có thể tách metadata khỏi nội dung lớn, chỉ lấy LOB khi cần và đo riêng prefetch của dữ liệu LOB.

## 9. Microsoft SQL Server JDBC: adaptive buffering

Microsoft JDBC Driver for SQL Server hỗ trợ response buffering. Chế độ adaptive cho phép driver buffer dữ liệu theo nhu cầu khi ứng dụng đọc ResultSet, giúp tránh phải giữ toàn bộ response lớn trong bộ nhớ client. Đây là chế độ mặc định trong các phiên bản driver hiện đại, nhưng cần xác nhận phiên bản và cấu hình thực tế.

Ví dụ cấu hình connection string:

~~~text
jdbc:sqlserver://db-host:1433;databaseName=appdb;responseBuffering=adaptive
~~~

Chế độ full có thể buffer toàn bộ response trước khi ứng dụng đọc, thuận tiện với một số thao tác nhưng có thể tiêu thụ nhiều heap khi kết quả lớn. Adaptive cho phép đọc dữ liệu theo nhu cầu, song không có nghĩa mọi loại truy vấn hoặc kiểu dữ liệu đều dùng server-side cursor giống PostgreSQL.

setFetchSize() vẫn là API JDBC, nhưng không nên suy ra rằng đặt fetch size tự động bật cùng một cơ chế cursor trên mọi phiên bản Microsoft JDBC Driver. Hãy phân biệt:

- Response buffering điều khiển cách driver giữ dữ liệu trả về.
- Server cursor là cơ chế thực thi và duy trì cursor ở server.
- Fetch size là gợi ý JDBC mà driver có thể diễn giải theo implementation.

Nếu ứng dụng cần scrollable ResultSet, nhiều result set hoặc LOB, cần kiểm tra ảnh hưởng của lựa chọn buffering và kiểu ResultSet. Hãy thử với đúng driver, SQL Server version và connection properties đang triển khai.

## 10. Spring JDBC, Hibernate và JPA

Framework Java có thể cung cấp API thuận tiện nhưng cuối cùng vẫn phụ thuộc JDBC driver và cách framework quản lý transaction.

### Spring JdbcTemplate

JdbcTemplate có thể đặt fetch size mặc định cho các Statement do template tạo:

~~~java
JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
jdbcTemplate.setFetchSize(500);

jdbcTemplate.query(
    "SELECT event_id, event_type FROM account_events ORDER BY event_id",
    (ResultSet rs) -> {
        Event event = mapEvent(rs);
        processEvent(event);
    }
);
~~~

RowCallbackHandler cho phép xử lý từng hàng mà không yêu cầu ứng dụng tạo danh sách toàn bộ kết quả. Tuy vậy, khả năng truyền theo luồng vẫn phụ thuộc driver, transaction và cách cấu hình connection. Đặt fetch size trên template không bảo đảm mọi driver đều dùng server cursor.

### Hibernate

Hibernate có cấu hình fetch size JDBC mặc định và API ở cấp query trong các phiên bản hỗ trợ. Ví dụ cấu hình thường gặp:

~~~properties
hibernate.jdbc.fetch_size=500
~~~

Hoặc đặt ở query bằng API tương ứng của phiên bản Hibernate:

~~~java
query.setFetchSize(500);
~~~

Fetch size điều chỉnh cách JDBC lấy hàng; nó không giống batch fetching association của ORM. Batch fetching quan hệ entity nhằm giảm N+1 SELECT, còn JDBC fetch size nhằm điều chỉnh việc truyền các hàng của một ResultSet.

### JPA Stream

Một API trả về Stream<T> không tự động bảo đảm dữ liệu được đọc từng hàng từ server. Provider có thể triển khai stream bằng cursor hoặc có thể materialize kết quả theo cách riêng. Khi dùng stream:

- Giữ transaction và EntityManager mở trong suốt lúc tiêu thụ nếu provider yêu cầu.
- Đóng stream bằng try-with-resources.
- Đặt fetch size qua hint hoặc API riêng của provider.
- Tránh gọi một truy vấn khác trên cùng persistence context/connection khi cursor đang mở nếu driver không hỗ trợ.
- Không tích lũy toàn bộ entity vào persistence context nếu có thể clear theo batch và nghiệp vụ cho phép.

## 11. Chọn fetch size theo kích thước hàng và độ trễ mạng

Không có một fetch size tối ưu cho mọi truy vấn. Hãy bắt đầu bằng một giá trị vừa phải, sau đó đo các mức tăng/giảm theo workload.

### Khi fetch size quá nhỏ

- Số lượt trao đổi mạng tăng.
- Chi phí round-trip có thể chiếm tỷ trọng lớn khi latency mạng cao.
- CPU ở client/server có thể tăng do xử lý nhiều lần lấy lô.
- Throughput truyền kết quả có thể thấp dù database còn khả năng xử lý.

### Khi fetch size quá lớn

- Driver có thể giữ nhiều hàng hơn trong buffer.
- Heap và GC pressure tăng.
- Thời gian trước khi ứng dụng xử lý được hàng đầu tiên có thể tăng.
- Ứng dụng có thể tải nhiều hàng mà cuối cùng không tiêu thụ nếu dừng sớm.
- Nhiều ResultSet đồng thời có thể nhân mức memory peak.

### Bảng quyết định ban đầu

| Đặc điểm workload | Hướng thử nghiệm |
| --- | --- |
| Hàng nhỏ, mạng có RTT cao, đọc gần hết kết quả | Thử fetch size lớn hơn |
| Hàng rộng hoặc chứa nhiều cột text/LOB | Bắt đầu thấp và đo heap |
| Kết quả thường dừng sớm | Tránh fetch quá nhiều hàng trước nhu cầu |
| Nhiều truy vấn streaming đồng thời | Chọn mức vừa phải, đo tổng heap và connection usage |
| Server cursor giữ snapshot lâu | Cân nhắc batch theo khóa và transaction ngắn |
| Driver materialize toàn bộ kết quả | Tìm đúng cấu hình driver hoặc đổi cách truy vấn; chỉ tăng/giảm fetch size có thể không giúp |

## 12. LOB, dữ liệu lớn và hàng có kích thước không đồng đều

Fetch size đếm số hàng, trong khi dung lượng hàng có thể thay đổi rất lớn. Một ResultSet gồm 1.000 hàng metadata nhỏ khác xa 1.000 hàng chứa CLOB hoặc BLOB nhiều megabyte.

Với dữ liệu lớn:

- Không chọn cột LOB nếu tác vụ không cần nội dung đó.
- Có thể đọc khóa và metadata trước, sau đó tải nội dung lớn theo nhu cầu.
- Dùng getBinaryStream() hoặc getCharacterStream() khi driver hỗ trợ phù hợp.
- Tiêu thụ stream trước khi chuyển sang hàng tiếp theo nếu driver gắn stream với vòng đời ResultSet.
- Đóng stream, ResultSet và Statement đúng thứ tự.
- Đo riêng bộ nhớ heap, direct buffer và dữ liệu được driver prefetch.

Không giữ đồng thời nhiều LOB stream mở nếu driver hoặc giao thức không hỗ trợ tốt. Một số driver dùng locator hoặc yêu cầu round-trip bổ sung khi đọc LOB; fetch size của hàng không nhất thiết điều chỉnh lượng LOB được nạp trước.

## 13. Vòng đời ResultSet, cursor và connection

Streaming thường giữ tài nguyên lâu hơn cách tải toàn bộ kết quả rồi đóng statement ngay. Những tài nguyên có thể tồn tại trong lúc đọc:

- Connection vật lý trong pool.
- Statement và ResultSet.
- Server-side cursor hoặc portal.
- Transaction và snapshot.
- Buffer ở driver và network socket.
- Tài nguyên thực thi hoặc work area ở server.

Nếu ứng dụng đọc một triệu hàng trong 20 phút, connection có thể bị chiếm suốt 20 phút. Với pool chỉ có 30 connection, một vài export lâu có thể chiếm phần lớn pool và khiến request ngắn phải chờ.

### Không thực hiện công việc chậm bên trong vòng đọc nếu có thể tránh

Ví dụ, gọi API từ xa cho từng hàng trong khi cursor còn mở sẽ kéo dài thời gian giữ connection và transaction:

~~~java
while (rs.next()) {
    Row row = mapRow(rs);
    remoteService.send(row); // Có thể chậm và giữ cursor lâu
}
~~~

Có thể tách việc đọc và việc gửi bằng một queue/batch có giới hạn dung lượng:

~~~text
Database cursor
    |
    v
Reader thread
    |
    v
Bounded queue (giới hạn số batch)
    |
    v
Worker gửi dữ liệu
~~~

Queue phải có giới hạn để tạo backpressure. Nếu queue không giới hạn, ứng dụng lại tích lũy dữ liệu trong heap và mất lợi ích streaming. Nếu producer nhanh hơn consumer, queue đầy sẽ làm reader chờ; khi đó cursor vẫn mở. Cần chọn batch size, số worker và transaction boundary theo SLA.

### Transaction ngắn hay snapshot nhất quán?

Cursor có thể cần transaction kéo dài để bảo đảm snapshot. Chia thành nhiều truy vấn theo keyset pagination có thể rút ngắn transaction nhưng các trang có thể nhìn thấy trạng thái dữ liệu khác nhau. Nếu báo cáo phải nhất quán tại một thời điểm, cần dùng snapshot/reporting copy, watermark hoặc cơ chế phù hợp của hệ quản trị.

## 14. Những lỗi thường gặp

### Nghĩ rằng setFetchSize bảo đảm streaming

JDBC định nghĩa fetch size là hint. Driver có thể bỏ qua hoặc dùng cơ chế khác. Hãy kiểm tra tài liệu driver, cấu hình connection và hành vi bộ nhớ trong thử nghiệm.

### Gọi setFetchSize sau khi executeQuery

Một số driver cho phép đổi fetch size trên ResultSet sau khi thực thi, nhưng nhiều quyết định truyền dữ liệu đã được xác lập lúc mở kết quả. Cách portable hơn là đặt trên Statement trước executeQuery().

### Dùng giá trị fetch size quá lớn cho mọi truy vấn

Một giá trị phù hợp với hàng nhỏ có thể làm heap tăng mạnh với hàng rộng hoặc LOB. Cấu hình toàn cục cũng có thể ảnh hưởng các truy vấn không cần đọc nhiều hàng.

### Giữ toàn bộ entity trong bộ nhớ

Tạo List chứa tất cả hàng hoặc giữ entity trong persistence context có thể làm heap tăng theo tổng kết quả, dù driver đọc theo lô.

### Quên đóng ResultSet hoặc Stream

Cursor, connection và server resource có thể bị giữ lâu. Luôn dùng try-with-resources hoặc cơ chế quản lý tài nguyên tương ứng.

### Mở transaction rồi chờ tác vụ ngoài

Transaction có thể giữ snapshot và connection trong thời gian dài. Tránh gọi dịch vụ ngoài, chờ người dùng hoặc ghi file chậm bên trong transaction nếu không cần.

### Chạy truy vấn khác trên cùng connection khi cursor còn mở

Một số driver hoặc chế độ streaming không cho phép nhiều kết quả hoạt động đồng thời trên cùng connection. Có thể xảy ra lỗi streaming result set is still active, kết quả bị đóng hoặc phải tải nốt dữ liệu trước. Kiểm tra hành vi driver và đóng/tiêu thụ ResultSet trước khi dùng lại connection.

### Nhầm fetch size với giới hạn kết quả

setFetchSize(500) không làm SQL chỉ trả 500 hàng. Muốn giới hạn tổng số hàng, phải dùng điều kiện SQL, LIMIT, FETCH FIRST hoặc cú pháp tương ứng của hệ quản trị.

## 15. Đo lường fetch size

Benchmark nên thay đổi một yếu tố mỗi lần. Với cùng truy vấn và dữ liệu, thử một số giá trị như 50, 100, 250, 500 và 1.000; khoảng giá trị phù hợp tùy kích thước hàng, mạng và driver.

Ghi nhận ít nhất:

| Chỉ số | Điều cần quan sát |
| --- | --- |
| Time to first row | Thời gian từ execute đến khi ứng dụng nhận được hàng đầu |
| Total fetch duration | Thời gian đọc hết ResultSet |
| Rows per second | Tốc độ tiêu thụ hàng |
| Network round trips/bytes | Số lượt trao đổi và lượng dữ liệu truyền |
| JVM heap peak | Bộ nhớ heap cao nhất trong lúc đọc |
| GC count/pause | Áp lực thu gom rác |
| Direct/native memory | Buffer ngoài heap nếu driver sử dụng |
| Active connections | Số connection bị giữ trong lúc streaming |
| Transaction age | Thời gian transaction và snapshot tồn tại |
| Database waits/CPU/I/O | Tác động của truy vấn lên server |

### Điều kiện thử nghiệm

- Dùng cùng tập dữ liệu và cùng projection.
- Giữ ổn định read/write mix và concurrency.
- Thử cả hàng nhỏ, hàng rộng và LOB nếu workload có.
- Chạy đủ lâu để quan sát steady state, không chỉ vài trăm hàng đầu.
- Tách warm cache và cold cache nếu hai trạng thái có ý nghĩa.
- Đo nhiều lần và so sánh median, p95/p99 khi có concurrency.
- Không chạy benchmark nặng trên production nếu chưa đánh giá tải và tác động.

### Đọc kết quả

Nếu tăng fetch size làm round trip giảm và throughput tăng nhưng heap peak/GC tăng mạnh, giá trị mới có thể không phù hợp khi chạy đồng thời. Nếu thay đổi fetch size không làm heap hoặc network round trip thay đổi, driver có thể đang bỏ qua hint hoặc dùng một cơ chế buffering khác. Nếu heap thấp nhưng connection occupancy và transaction age tăng, streaming có thể đang chuyển áp lực từ JVM sang database/pool.

## 16. Ví dụ hoàn chỉnh: export dữ liệu lớn có giới hạn bộ nhớ

Một job cần xuất các sự kiện cũ sang file. Bảng có hàng triệu sự kiện. Job không cần giữ toàn bộ kết quả trong RAM.

~~~java
String sql = """
    SELECT event_id, account_id, occurred_at, event_type
    FROM account_events
    WHERE occurred_at < ?
    ORDER BY occurred_at, event_id
    """;

try (Connection connection = dataSource.getConnection()) {
    boolean previousAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(
             sql,
             ResultSet.TYPE_FORWARD_ONLY,
             ResultSet.CONCUR_READ_ONLY)) {

        statement.setFetchSize(500);
        statement.setTimestamp(1, Timestamp.from(cutoff));

        try (ResultSet rs = statement.executeQuery();
             BufferedWriter writer = Files.newBufferedWriter(outputPath)) {

            while (rs.next()) {
                String line = rs.getLong("event_id") + ","
                    + rs.getLong("account_id") + ","
                    + rs.getTimestamp("occurred_at") + ","
                    + escapeCsv(rs.getString("event_type"));

                writer.write(line);
                writer.newLine();
            }
        }

        connection.commit();
    } catch (SQLException | IOException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    } finally {
        connection.setAutoCommit(previousAutoCommit);
    }
}
~~~

Đoạn mã minh họa cách xử lý từng hàng và đóng ResultSet/Writer bằng try-with-resources. Trong ứng dụng thực tế cần quyết định transaction có nên bao trùm toàn bộ export hay không. Nếu ghi file chậm, transaction có thể tồn tại lâu và giữ connection/snapshot. Một thiết kế khác có thể đọc theo từng batch bằng keyset pagination, ghi file rồi đóng transaction giữa các batch; khi đó cần watermark hoặc quy tắc nhất quán để tránh bỏ sót/lặp hàng khi dữ liệu thay đổi.

Với PostgreSQL, fetch size dương cần cursor trong transaction không auto-commit như phần trước. Với MySQL Connector/J, cần xác nhận cursor fetch hoặc streaming mode được bật đúng. Với Oracle và SQL Server, phải đo row prefetch/adaptive buffering theo driver. Cùng một đoạn JDBC có thể có hành vi bộ nhớ và network khác nhau giữa các nền tảng.

## 17. Quy trình lựa chọn và triển khai

1. **Xác định mục tiêu:** giảm heap, tăng throughput, giảm round trip hay giới hạn thời gian giữ connection?
2. **Đo kích thước hàng:** tính cả cột rộng, text, binary và LOB.
3. **Xác định driver/version:** đọc hành vi fetch size, cursor, buffering và các URL property.
4. **Chọn ResultSet phù hợp:** ưu tiên forward-only/read-only khi chỉ đọc tuần tự.
5. **Bắt đầu với fetch size vừa phải:** ví dụ 100–500 hàng, sau đó điều chỉnh bằng benchmark; đây chỉ là điểm bắt đầu.
6. **Bật cơ chế driver khi cần:** PostgreSQL cursor fetch, MySQL cursor fetch, Oracle row prefetch hoặc SQL Server adaptive buffering theo implementation.
7. **Xử lý theo luồng thật:** không tích lũy toàn bộ hàng hoặc entity trong heap.
8. **Quản lý tài nguyên:** đóng ResultSet, Statement, Stream và connection; xác định rõ transaction owner.
9. **Đo concurrency:** kiểm tra heap, GC, pool occupancy, transaction age, network round trips và server waits.
10. **Chọn chiến lược nhất quán:** cursor dài hay batch/keyset pagination với watermark.
11. **Kiểm thử lại:** dùng workload đại diện, nhiều kích thước hàng và trạng thái cache.
12. **Theo dõi sau phát hành:** so p95/p99, throughput, memory peak, GC và tài nguyên database.

## 18. Nguyên tắc cần ghi nhớ

- Fetch size là gợi ý số hàng cho driver lấy mỗi lần; nó không giới hạn tổng số hàng SQL trả về.
- JDBC không bảo đảm mọi driver dùng cùng một cơ chế streaming khi đặt fetch size.
- Client buffering, server-side cursor, row prefetch và adaptive buffering có vòng đời tài nguyên khác nhau.
- Fetch size nhỏ giảm lượng dữ liệu giữ trong mỗi lô nhưng có thể tăng round trip; fetch size lớn có thể tăng throughput nhưng làm heap và GC pressure tăng.
- PostgreSQL JDBC thường cần fetch size dương, forward-only ResultSet và auto-commit tắt để dùng cursor fetching.
- MySQL Connector/J có useCursorFetch và một chế độ streaming legacy riêng; không xem Integer.MIN_VALUE là chuẩn JDBC.
- Oracle JDBC dùng row prefetch; LOB có thể có hành vi và prefetch riêng.
- SQL Server JDBC có response buffering, trong đó adaptive buffering khác với server-side cursor.
- Framework Spring, Hibernate và JPA vẫn phụ thuộc driver; Stream API không tự bảo đảm dữ liệu được đọc từng hàng từ server.
- Streaming có thể giữ connection, cursor và snapshot lâu; cần quản lý transaction, pool và downstream backpressure.
- Benchmark bằng time-to-first-row, throughput, round trips, heap, GC, transaction age và database waits trước khi chọn cấu hình.

Fetch size và streaming là một phần của đường đi dữ liệu giữa ứng dụng Java và database. Khi hiểu rõ driver đang buffer ở đâu, cursor tồn tại bao lâu và mỗi lô ảnh hưởng thế nào đến mạng cùng heap, nhóm phát triển có thể chọn cách đọc kết quả phù hợp. Đo lường cả phía JVM lẫn database giúp bảo đảm việc giảm bộ nhớ client không tạo ra transaction quá dài, connection pool bị chiếm hoặc tải I/O tăng ngoài dự kiến.
