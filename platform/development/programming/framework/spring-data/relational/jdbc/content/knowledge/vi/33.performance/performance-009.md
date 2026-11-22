# Bộ nhớ, fetch size và thời gian giữ connection khi streaming

Khi một truy vấn trả về rất nhiều hàng, cách đọc kết quả ảnh hưởng trực tiếp đến bộ nhớ heap, thời gian giữ connection và khả năng phục vụ request khác. Trong **Spring Data Relational JDBC**, ứng dụng có thể dùng kiểu trả về `Stream<T>` cho query method nếu phiên bản Spring Data JDBC đang dùng hỗ trợ, hoặc dùng API streaming của Spring JDBC để xử lý từng hàng.

Streaming giúp ứng dụng tiêu thụ kết quả theo từng phần thay vì luôn tạo một danh sách chứa toàn bộ kết quả. Tuy nhiên, `Stream<T>` không tự bảo đảm JDBC driver sẽ tải dữ liệu theo từng batch. Hành vi thực tế còn phụ thuộc `fetch size`, driver, database, transaction và cách code tiêu thụ stream.

Một stream đọc từ database thường giữ ResultSet, Statement và connection cho đến khi stream được đóng. Vì vậy, streaming có thể giảm áp lực bộ nhớ nhưng kéo dài thời gian chiếm connection. Bài học này giải thích cách cân bằng hai yếu tố đó, cách đặt fetch size, cách đóng stream đúng cách và khi nào nên dùng keyset pagination thay cho một stream kéo dài.

## 1. Đọc toàn bộ kết quả và streaming khác nhau thế nào?

Với cách đọc thông thường, repository trả về một collection:

~~~java
List<PurchaseOrder> orders =
    repository.findByStatus(OrderStatus.SUBMITTED);
~~~

Ứng dụng nhận một danh sách đã được materialize. Tất cả object trong kết quả cần được giữ trong heap trong thời gian danh sách còn được tham chiếu.

Với query trả về stream:

~~~java
try (Stream<PurchaseOrder> orders =
         repository.streamByStatus(OrderStatus.SUBMITTED)) {
    orders.forEach(this::process);
}
~~~

Ứng dụng có thể xử lý từng phần tử trong lúc đọc kết quả. Khi được hỗ trợ bởi Spring Data JDBC và JDBC driver, cách này tránh phải giữ toàn bộ danh sách trong bộ nhớ.

| Cách đọc | Bộ nhớ phía ứng dụng | Vòng đời tài nguyên |
|---|---|---|
| `List<T>` | Thường tỷ lệ với số hàng và kích thước object | Có thể giải phóng connection sau khi query materialize xong |
| `Stream<T>` | Có thể giữ ít object hơn nếu tiêu thụ tuần tự | Thường giữ ResultSet, Statement và connection đến khi đóng stream |
| Keyset pagination theo batch | Giới hạn số object mỗi batch | Có thể đóng query/connection sau từng batch |

Streaming không có nghĩa toàn bộ dữ liệu luôn nằm ngoài heap. Driver có thể buffer một phần hoặc toàn bộ kết quả; object đã được xử lý cũng có thể bị code giữ lại trong collection, cache hoặc closure.

## 2. Stream từ query method của Spring Data JDBC

Nếu phiên bản Spring Data JDBC của dự án hỗ trợ repository query method trả về `Stream<T>`, có thể khai báo một phương thức stream:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT *
        FROM purchase_orders
        WHERE status = :status
        ORDER BY id
        """)
    Stream<PurchaseOrder> streamByStatus(
        @Param("status") String status
    );
}
~~~

Đây là ví dụ minh họa cho aggregate có mapping phù hợp với câu SELECT. Nếu query chỉ lấy một phần cột hoặc dữ liệu báo cáo, hãy dùng projection/DTO phù hợp với khả năng mapping của phiên bản Spring Data JDBC thay vì giả định một hàng không đầy đủ có thể dựng thành aggregate hoàn chỉnh.

### 2.1. Luôn đóng stream

Stream từ database có thể giữ tài nguyên JDBC. Phải đóng nó kể cả khi xử lý gặp exception:

~~~java
try (Stream<PurchaseOrder> orders =
         repository.streamByStatus("SUBMITTED")) {
    orders.forEach(this::process);
}
~~~

Không dựa vào garbage collector để đóng ResultSet hoặc connection. Terminal operation như `forEach`, `count` hay `collect` không tự động thay thế việc gọi `close()` trên stream.

Try-with-resources gọi `close()` khi block kết thúc, kể cả khi xử lý ném exception.

### 2.2. Không trả stream ra ngoài transaction boundary

Một lỗi phổ biến là mở stream trong method repository hoặc service rồi trả stream cho caller xử lý sau khi method kết thúc. Nếu transaction đã kết thúc hoặc connection đã được giải phóng trước khi caller đọc phần tử, stream có thể thất bại.

Đặt transaction boundary bao quanh cả thời gian mở và tiêu thụ stream:

~~~java
@Service
public class OrderExportService {

    private final PurchaseOrderRepository orders;

    public OrderExportService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public long processSubmittedOrders() {
        try (Stream<PurchaseOrder> stream =
                 orders.streamByStatus("SUBMITTED")) {
            return stream
                .peek(this::process)
                .count();
        }
    }

    private void process(PurchaseOrder order) {
        // Xử lý nhanh dữ liệu của một aggregate.
    }
}
~~~

Trong ví dụ, transaction của service còn hoạt động trong lúc stream được tiêu thụ. Khi method kết thúc, try-with-resources đóng stream trước khi transaction kết thúc.

Nếu ứng dụng có nhiều transaction manager, chỉ rõ transaction manager gắn với repository/DataSource đó trong `@Transactional`.

### 2.3. Đừng mặc định mọi query method đều tự có transaction phù hợp

Các method CRUD kế thừa từ repository có quy tắc transaction mặc định của Spring Data. Query method khai báo riêng có thể cần cấu hình transaction tường minh. Ngay cả khi query method có transaction riêng, transaction đó có thể kết thúc khi method trả về stream, trước khi caller tiêu thụ hết kết quả.

Một service-level transaction bao quanh cả việc đọc và xử lý thường làm rõ vòng đời tài nguyên hơn. Hãy xác nhận semantics của phiên bản Spring Data JDBC đang dùng và kiểm thử với driver thực tế.

## 3. Connection được giữ trong bao lâu?

Với stream dựa trên JDBC cursor/result set, connection cần còn mở khi ứng dụng tiếp tục lấy hàng. Vòng đời thường là:

~~~mermaid
sequenceDiagram
    participant Service
    participant Repository
    participant JDBC as JDBC Driver
    participant DB as Database
    Service->>Repository: mở query stream
    Repository->>JDBC: tạo Statement và execute query
    JDBC->>DB: gửi SELECT
    DB-->>JDBC: trả ResultSet/cursor
    JDBC-->>Repository: Stream<T>
    Repository-->>Service: Stream<T>
    loop Tiêu thụ từng hàng
        Service->>JDBC: yêu cầu hàng tiếp theo
        JDBC->>DB: fetch batch nếu cần
        DB-->>JDBC: dữ liệu tiếp theo
        JDBC-->>Service: object đã map
    end
    Service->>Repository: close stream
    Repository->>JDBC: đóng ResultSet/Statement
    JDBC->>DB: giải phóng cursor/connection
~~~

Chi tiết fetch có thể khác theo driver, nhưng nguyên tắc quản lý tài nguyên vẫn quan trọng: không đóng stream thì connection có thể tiếp tục bị giữ.

### 3.1. Streaming giảm heap nhưng tăng connection occupancy

Giả sử một truy vấn trả về 500.000 hàng. Materialize thành `List` có thể cần giữ hàng trăm nghìn object cùng lúc. Stream cho phép xử lý từng hàng và bỏ tham chiếu sau khi xử lý.

Tuy nhiên, nếu quá trình xử lý mất 15 phút, connection có thể bị giữ trong 15 phút. Trong thời gian đó, connection không sẵn sàng cho request khác.

Hãy cân nhắc hai tài nguyên riêng biệt:

- **Heap:** số object và dữ liệu được giữ đồng thời trong ứng dụng.
- **Connection pool:** số connection bị chiếm và thời gian mỗi connection không thể phục vụ công việc khác.

Streaming tối ưu một mặt nhưng có thể làm mặt còn lại trở thành nút thắt.

### 3.2. Không gọi dịch vụ chậm trong lúc giữ stream nếu có thể tránh

Ví dụ sau có thể giữ connection rất lâu:

~~~java
try (Stream<PurchaseOrder> orders = repository.streamAll()) {
    orders.forEach(order -> {
        remoteClient.send(order); // Có thể chờ network lâu.
    });
}
~~~

Nếu mỗi lần gọi HTTP mất vài trăm mili giây hoặc bị retry, thời gian giữ connection tăng theo số hàng. Một luồng export chậm có thể chiếm connection pool và làm các request thông thường bị chờ.

Các lựa chọn tốt hơn tùy yêu cầu:

- Đọc theo batch nhỏ, đóng query rồi mới gọi dịch vụ bên ngoài.
- Đưa dữ liệu cần xử lý vào queue hoặc staging table.
- Dùng worker chuyên trách và giới hạn concurrency.
- Tách bước đọc dữ liệu khỏi bước gọi dịch vụ bên ngoài.

Không giữ một cursor database mở trong khi chờ người dùng, network hoặc một hệ thống bên ngoài phản hồi.

## 4. Fetch size là gì?

Fetch size là một hint mà ứng dụng có thể đặt trên JDBC `Statement` thông qua:

~~~java
statement.setFetchSize(500);
~~~

Nó gợi ý cho JDBC driver số hàng nên lấy trong mỗi lần fetch từ database. Với driver hỗ trợ cursor hoặc incremental fetch, fetch size có thể giúp giới hạn lượng dữ liệu được đưa về trong một lượt.

Fetch size **không phải**:

- Giới hạn tổng số hàng của câu SELECT.
- Tương đương `LIMIT` hoặc `TOP`.
- Kích thước page mà repository trả về.
- Cam kết tuyệt đối về số object tối đa trong heap.
- Cam kết mọi driver đều dùng server-side cursor.

Driver có thể coi fetch size là hint, diễn giải theo cách riêng hoặc bỏ qua nó. Hành vi còn phụ thuộc autocommit, transaction, URL properties và phiên bản driver.

### 4.1. Fetch size khác page size

| Khái niệm | Tác dụng |
|---|---|
| Fetch size | Số hàng driver được gợi ý lấy mỗi lượt từ result set |
| Page size | Số hàng ứng dụng yêu cầu trong một page |
| SQL limit | Giới hạn số hàng database trả về cho một câu query |
| Batch size | Số bản ghi ứng dụng gom vào một nhóm xử lý/ghi |

Ví dụ, query có `LIMIT 10000` và fetch size 500 vẫn chỉ trả tối đa 10.000 hàng, có thể được driver lấy thành nhiều lượt. Ngược lại, query không có LIMIT với fetch size 500 vẫn có thể trả về hàng triệu hàng qua nhiều lượt fetch.

### 4.2. Fetch size không bảo đảm bộ nhớ cố định

Ngay cả khi fetch size là 500:

- Driver có thể buffer nhiều hơn hoặc toàn bộ kết quả.
- Mapper có thể tạo object lớn.
- Code có thể giữ object đã xử lý trong một collection.
- Persistence context/cache của ứng dụng có thể giữ thêm dữ liệu.
- Một aggregate có thể kéo theo nhiều object con hoặc dữ liệu liên quan.

Đo heap và quan sát driver/database trong môi trường mục tiêu. Đừng dùng con số fetch size như một lời cam kết về memory ceiling.

## 5. Đặt fetch size với JdbcTemplate

Spring JDBC cho phép cấu hình fetch size mặc định trên `JdbcTemplate`. Nếu `NamedParameterJdbcTemplate` được tạo từ `JdbcTemplate` đó, nó sử dụng cùng JDBC operations bên dưới.

Ví dụ cấu hình:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class JdbcReadConfiguration {

    @Bean
    NamedParameterJdbcOperations namedParameterJdbcOperations(
            DataSource dataSource) {
        JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
        jdbcTemplate.setFetchSize(500);

        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }
}
~~~

Đây là fetch size mặc định cho các statement được tạo qua template đó. Cấu hình toàn cục có thể ảnh hưởng nhiều query, không chỉ query streaming. Hãy kiểm tra các query khác và driver trước khi áp dụng rộng.

Với Spring Data JDBC, repository infrastructure thường dùng `NamedParameterJdbcOperations`. Nếu tự cấu hình bean này để điều chỉnh fetch size, bảo đảm repository group thực sự được gắn với đúng bean operations đó.

Không giả định annotation `@Query` của mọi phiên bản Spring Data JDBC có thuộc tính `fetchSize`. Hãy kiểm tra chữ ký API của phiên bản dự án. Nếu annotation không cung cấp tùy chọn này, có thể cấu hình JDBC operations nền hoặc dùng một đường query chuyên biệt có kiểm soát statement.

## 6. Đặt fetch size cho từng truy vấn bằng queryForStream

Khi cần kiểm soát fetch size riêng cho một truy vấn, Spring JDBC cung cấp `JdbcTemplate.queryForStream` ở các phiên bản Spring Framework có API này.

Ví dụ:

~~~java
public record OrderExportRow(
        Long id,
        String orderNumber,
        String status
) {
}
~~~

~~~java
public class OrderExportReader {

    private static final String SQL = """
        SELECT id, order_number, status
        FROM purchase_orders
        WHERE status = ?
        ORDER BY id
        """;

    private final JdbcTemplate jdbcTemplate;

    public OrderExportReader(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Stream<OrderExportRow> streamSubmittedOrders() {
        return jdbcTemplate.queryForStream(
            connection -> {
                PreparedStatement statement =
                    connection.prepareStatement(SQL);
                statement.setString(1, "SUBMITTED");
                statement.setFetchSize(500);
                statement.setFetchDirection(ResultSet.FETCH_FORWARD);
                return statement;
            },
            (resultSet, rowNumber) -> new OrderExportRow(
                resultSet.getLong("id"),
                resultSet.getString("order_number"),
                resultSet.getString("status")
            )
        );
    }
}
~~~

Caller phải đóng stream:

~~~java
try (Stream<OrderExportRow> rows = reader.streamSubmittedOrders()) {
    rows.forEach(exportWriter::write);
}
~~~

Đoạn code này minh họa cách đặt fetch size trên `PreparedStatement` cho một query cụ thể. `queryForStream` trả stream gắn với tài nguyên JDBC; phải đóng stream để giải phóng ResultSet, Statement và connection. Xác nhận API có trong Spring Framework version của dự án trước khi dùng.

Nếu query cần transaction dài để driver dùng cursor, hãy bao quanh cả lúc mở và tiêu thụ stream bằng transaction manager của DataSource đó:

~~~java
@Transactional(readOnly = true)
public void exportSubmittedOrders() {
    try (Stream<OrderExportRow> rows = reader.streamSubmittedOrders()) {
        rows.forEach(exportWriter::write);
    }
}
~~~

Nếu `exportWriter` thực hiện I/O chậm, hãy cân nhắc đọc theo batch để không giữ connection suốt thời gian ghi file hoặc gọi hệ thống ngoài.

## 7. Driver và database quyết định cách fetch

JDBC chuẩn cung cấp `Statement.setFetchSize`, nhưng driver có quyền quyết định cách thực thi. Cùng một fetch size có thể tạo ra hành vi khác nhau giữa các database.

### 7.1. PostgreSQL

Với PostgreSQL JDBC driver, cursor-based fetching thường cần:

- Một transaction đang mở, tức connection không ở autocommit mode.
- Fetch size dương được đặt trên statement.
- ResultSet được tiêu thụ trong thời gian transaction còn hoạt động.

Nếu query chạy ở autocommit mode, driver có thể lấy toàn bộ kết quả thay vì dùng cursor theo batch. Một service-level `@Transactional(readOnly = true)` có thể giúp tạo transaction phù hợp, nhưng phải xác nhận cấu hình thực tế và phiên bản driver.

### 7.2. MySQL Connector/J

Với MySQL Connector/J, cursor-based fetching có thể cần bật property `useCursorFetch=true` và đặt fetch size dương. Nếu không, driver có thể buffer kết quả theo cách khác.

Kiểm tra tài liệu đúng phiên bản Connector/J đang chạy; đừng sao chép URL property từ một phiên bản khác mà không xác nhận.

### 7.3. Các driver khác

Oracle, SQL Server và các JDBC driver khác có mặc định, giới hạn và cơ chế prefetch riêng. Có driver dùng fetch size để điều chỉnh số hàng prefetch; có driver yêu cầu transaction hoặc cấu hình bổ sung để đọc theo cursor.

Khi tài liệu không nêu cụ thể một driver, hãy viết rằng fetch size là hint JDBC và yêu cầu kiểm chứng theo driver. Không khẳng định một con số fetch size tối ưu cho mọi hệ quản trị.

## 8. Chọn fetch size như thế nào?

Fetch size quá nhỏ có thể làm tăng số lượt trao đổi giữa ứng dụng và database. Fetch size quá lớn có thể tăng buffer memory và giảm lợi ích của streaming.

Một cách chọn thực tế:

1. Bắt đầu bằng giá trị vừa phải, chẳng hạn 200 hoặc 500.
2. Dùng cùng query và tập dữ liệu đại diện.
3. Đo thời gian hoàn thành, heap, số lần fetch và connection hold time.
4. Thử tăng hoặc giảm fetch size.
5. Kiểm tra nhiều kích thước hàng và độ trễ network.
6. Chọn giá trị phù hợp với driver, workload và pool connection.

Không dùng benchmark trên máy local với vài trăm hàng để kết luận cho batch hàng triệu bản ghi ở production.

### 8.1. Ước lượng bộ nhớ buffer

Giả sử driver giữ gần đúng một batch có `F` hàng và kích thước dữ liệu trung bình mỗi hàng sau khi biểu diễn trong buffer là `R` byte. Phần buffer có thể có quy mô gần:

`F × R`

Đây chỉ là ước lượng khái niệm. Heap thực tế còn gồm object Java, String, collection, mapper, driver buffers và dữ liệu mà code giữ lại. Không thể suy ra memory limit chính xác chỉ từ fetch size.

### 8.2. Chú ý kích thước hàng

500 hàng nhỏ chỉ chứa vài cột số có thể nhẹ hơn 500 hàng chứa nhiều CLOB, JSON lớn hoặc binary. Khi query phục vụ export, chỉ SELECT những cột cần thiết thay vì lấy toàn bộ aggregate nếu use case không cần.

Projection/DTO phẳng thường phù hợp cho streaming báo cáo hơn việc dựng aggregate đầy đủ với nhiều object con.

## 9. Connection pool và thời gian giữ connection

Connection pool có số lượng connection hữu hạn. Khi một stream mở và chưa đóng, connection dùng cho stream đó không thể được cấp cho request khác.

Ví dụ pool có 20 connection:

- 5 request export cùng mở stream.
- 4 batch job cũng giữ stream.
- 11 connection còn lại phục vụ các request thông thường.

Nếu mỗi stream giữ connection trong thời gian dài, các request khác có thể chờ lấy connection dù query của chúng rất nhanh.

### 9.1. Thời gian giữ connection quan trọng hơn số hàng đơn thuần

Một query trả về 1 triệu hàng nhưng được tiêu thụ nhanh có thể giữ connection ít thời gian hơn một query trả về 5.000 hàng mà mỗi hàng phải gọi API ngoài trong vài giây.

Theo dõi ít nhất:

- Thời gian mở query đến khi đóng stream.
- Số connection active và idle.
- Số request chờ connection.
- Connection acquisition timeout.
- Thời gian query và thời gian xử lý từng hàng.
- Số hàng và kích thước payload.

Phân biệt query execution time với total connection hold time. Query có thể hoàn tất phần lớn ở database sớm, nhưng connection vẫn bị giữ trong khi ứng dụng xử lý phần còn lại của stream.

### 9.2. Đừng mở nhiều stream đồng thời không giới hạn

Mỗi stream có thể chiếm một connection. Nếu mở một stream cho mỗi task trong executor không giới hạn, pool có thể cạn và các task chờ lẫn nhau.

Giới hạn concurrency của batch/export theo:

- Kích thước connection pool.
- Số connection cần dành cho request trực tuyến.
- Tải database.
- Thời gian giữ connection.
- Bộ nhớ dành cho mỗi worker.

Không đặt concurrency bằng số luồng CPU rồi giả định database có thể phục vụ từng ấy stream cùng lúc.

## 10. Transaction và khóa trong lúc streaming

Một stream chạy bên trong transaction có thể giữ transaction mở trong toàn bộ quá trình tiêu thụ. Điều này ảnh hưởng đến:

- Connection được giữ lâu.
- Snapshot hoặc MVCC state tồn tại lâu tùy database/isolation.
- Lock nếu query hoặc transaction có thao tác ghi.
- Vacuum/cleanup hoặc version retention ở một số database.
- Khả năng rollback và thời gian phục hồi khi task lỗi.

Đọc streaming nên dùng transaction read-only khi phù hợp với semantics của ứng dụng. Tuy nhiên, `readOnly = true` là hint cho transaction manager/database, không phải cam kết rằng mọi câu ghi đều bị chặn.

Tránh thực hiện cập nhật nhiều bảng trong cùng transaction dài chỉ vì dữ liệu được đọc qua stream. Nếu cần ghi kết quả, hãy xem xét chia công việc thành các batch transaction ngắn.

## 11. Không chạy query lồng nhau trên cùng stream một cách tùy tiện

Khi ResultSet đang mở, gọi thêm repository query trên cùng connection có thể gây vấn đề tùy driver:

- Driver không hỗ trợ nhiều ResultSet/Statement đồng thời trên một connection.
- Query mới làm ResultSet cũ bị đóng hoặc thay đổi trạng thái.
- Transaction và lock kéo dài hơn dự kiến.
- N+1 query làm tăng round trip và connection occupancy.

Ví dụ nên tránh:

~~~java
try (Stream<PurchaseOrder> orders = repository.streamAll()) {
    orders.forEach(order -> {
        Customer customer = customerRepository.findById(
            order.getCustomerId()
        ).orElseThrow();
        process(order, customer);
    });
}
~~~

Thay vào đó, dùng JOIN/projection nếu phù hợp hoặc đọc customer theo batch bằng danh sách ID. Với danh sách lớn, có thể dùng keyset pagination để kiểm soát từng nhóm dữ liệu.

## 12. Khi nào nên dùng keyset pagination thay cho streaming?

Streaming phù hợp khi:

- Cần đọc tuần tự một kết quả lớn.
- Có thể xử lý mỗi hàng nhanh.
- Driver hỗ trợ fetch theo batch.
- Có thể chấp nhận giữ một connection trong thời gian tiêu thụ.

Keyset pagination thường phù hợp hơn khi:

- Công việc kéo dài hoặc có gọi hệ thống ngoài.
- Muốn giải phóng connection giữa các batch.
- Có thể tiếp tục từ khóa cuối cùng đã xử lý.
- Muốn retry một batch hoặc tiếp tục sau khi worker dừng.

Ví dụ query theo ID:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
WHERE id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
~~~

Ứng dụng xử lý một batch, ghi nhận ID cuối cùng rồi truy vấn batch tiếp:

~~~java
long lastSeenId = 0L;
int batchSize = 500;

while (true) {
    List<OrderExportRow> batch =
        reader.findNextBatch(lastSeenId, batchSize);

    if (batch.isEmpty()) {
        break;
    }

    processBatch(batch);
    lastSeenId = batch.get(batch.size() - 1).id();
}
~~~

Mỗi query materialize tối đa một batch nhỏ. Nếu transaction boundary nằm trong method xử lý từng batch và kết thúc sau khi batch hoàn tất, connection có thể được trả về pool giữa các batch.

### 12.1. Điều kiện để keyset pagination an toàn

- Cột cursor phải có thứ tự ổn định, thường là khóa chính hoặc khóa sắp xếp duy nhất.
- Điều kiện WHERE phải dùng cùng thứ tự với ORDER BY.
- Cần xử lý hàng được thêm hoặc sửa trong khi batch đang chạy.
- Nếu sort theo nhiều cột, cursor phải chứa đủ các cột để tạo thứ tự duy nhất.
- Cần xác định snapshot consistency hay chấp nhận dữ liệu thay đổi trong lúc export.

Keyset pagination không tự tạo snapshot nhất quán cho toàn bộ job. Nếu nghiệp vụ cần snapshot, phải thiết kế isolation hoặc chiến lược dữ liệu riêng.

## 13. Xử lý lỗi và đóng tài nguyên

Luôn dùng try-with-resources cho stream:

~~~java
try (Stream<OrderExportRow> rows = reader.streamSubmittedOrders()) {
    rows.forEach(this::process);
} catch (DataAccessException ex) {
    // Ghi log và xử lý lỗi theo hợp đồng của job.
}
~~~

Nếu xử lý ném exception:

1. Try-with-resources gọi close trên stream.
2. JDBC ResultSet và Statement được giải phóng.
3. Connection được trả về transaction manager hoặc pool theo transaction lifecycle.
4. Transaction interceptor quyết định commit/rollback dựa trên exception và rollback rules.

Không bắt exception rồi tiếp tục dùng stream có thể đã ở trạng thái lỗi. Nếu cần retry, thường phải mở query/transaction mới và tiếp tục từ checkpoint đã lưu.

### 13.1. Không gọi close quá sớm

Không làm như sau:

~~~java
Stream<OrderExportRow> stream = reader.streamSubmittedOrders();
stream.close();
stream.forEach(this::process);
~~~

Stream đã đóng không thể tiếp tục tiêu thụ. Hãy giữ nó trong try-with-resources và xử lý bên trong block.

### 13.2. Không chuyển stream sang thread khác

JDBC connection và ResultSet không được thiết kế để chia sẻ tùy tiện giữa nhiều thread. Tránh:

~~~java
stream.parallel().forEach(this::process);
~~~

Việc chạy song song trên một stream JDBC có thể truy cập cursor và connection không an toàn, đồng thời làm khó xác định transaction boundary.

Nếu cần parallel processing, hãy chia dữ liệu thành batch độc lập, đóng query của batch rồi gửi dữ liệu đã materialize sang worker có giới hạn concurrency. Mỗi worker mở transaction/connection riêng nếu cần truy cập database.

## 14. Kiểm tra streaming trong môi trường thực tế

Một unit test xác nhận code xử lý từng object không chứng minh driver đang fetch theo batch. Cần kiểm tra với database và driver thực tế.

Các điểm nên đo:

| Chỉ số | Điều cần quan sát |
|---|---|
| Heap usage | Có tăng theo tổng số hàng hay ổn định theo batch? |
| GC activity | Có nhiều allocation hoặc pause lớn không? |
| Fetch size | Statement có nhận giá trị đã cấu hình không? |
| Driver behavior | Có cursor/incremental fetch thật không? |
| Connection hold time | Từ lúc mở query đến khi stream đóng mất bao lâu? |
| Pool pending threads | Có request phải chờ connection không? |
| Database session | Cursor/transaction có được đóng sau khi xử lý không? |
| Throughput | Số hàng xử lý mỗi giây thay đổi thế nào? |

### 14.1. Test stream được đóng khi thành công và thất bại

Có thể dùng integration test với query đủ lớn để kiểm tra luồng tiêu thụ. Ngoài ra, dùng metric connection pool hoặc JDBC instrumentation để xác nhận connection được trả về sau khi block try-with-resources kết thúc.

Kiểm tra cả:

- Tiêu thụ hết stream.
- Dừng sớm sau một số hàng.
- Mapper hoặc processor ném exception.
- Caller không có transaction ngoài.
- Caller có service-level transaction.
- Hủy tác vụ export giữa chừng.

### 14.2. Đo trên database/driver mục tiêu

Hãy chạy test với đúng driver version và cấu hình connection string dự kiến triển khai. Một bài test H2 có thể xác nhận mapping cơ bản nhưng không chứng minh PostgreSQL hoặc MySQL dùng cursor theo cùng cách.

Ghi lại database version, driver version, fetch size, autocommit/transaction mode và số hàng thử. Không đưa ra một khuyến nghị fetch size phổ quát nếu chưa có benchmark phù hợp.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Heap vẫn tăng dù dùng Stream | Driver buffer nhiều dữ liệu hoặc code giữ object đã xử lý | Kiểm tra driver, fetch size và references trong ứng dụng |
| Connection pool cạn | Stream không được đóng hoặc bị giữ quá lâu | Dùng try-with-resources và rút ngắn thời gian xử lý |
| Stream lỗi sau khi service trả về | Transaction/connection kết thúc trước khi caller tiêu thụ | Tiêu thụ stream bên trong transaction boundary |
| Fetch size không tạo khác biệt | Driver bỏ qua hoặc cần cấu hình khác | Đọc tài liệu đúng driver và đo thực tế |
| Query trả nhiều hàng hơn mong đợi | Nhầm fetch size với LIMIT/page size | Dùng SQL limit hoặc pagination để giới hạn tổng kết quả |
| Export chậm khi gọi API ngoài | Connection bị giữ trong khi chờ network | Đọc theo batch rồi xử lý ngoài transaction |
| Query lồng nhau làm stream hỏng | Driver không hỗ trợ nhiều statement trên cùng connection | Dùng JOIN hoặc batch lookup |
| Dùng parallel stream gây lỗi | ResultSet/connection không an toàn khi chia sẻ | Xử lý tuần tự hoặc chia batch độc lập |
| Cursor không hoạt động trên PostgreSQL | Autocommit hoặc transaction/fetch size không phù hợp | Kiểm tra transaction và cấu hình driver |
| MySQL vẫn buffer kết quả | Chưa bật cursor fetch hoặc driver config phù hợp | Kiểm tra useCursorFetch và fetch size |
| Query method không biên dịch với Stream | Phiên bản Spring Data JDBC không hỗ trợ chữ ký đó | Kiểm tra return types của đúng phiên bản |
| Batch bỏ sót hoặc lặp hàng | Keyset không có thứ tự duy nhất hoặc dữ liệu thay đổi | Dùng cursor ổn định và xác định consistency model |

## 16. Quy trình chọn cách đọc dữ liệu lớn

Khi xử lý tập kết quả lớn, có thể đi theo trình tự:

1. **Ước lượng quy mô:** số hàng, kích thước mỗi hàng và tổng payload.
2. **Chọn kiểu kết quả:** DTO/projection cho báo cáo; aggregate khi cần domain mapping đầy đủ.
3. **Xác nhận Stream support:** kiểm tra phiên bản Spring Data JDBC đã resolve.
4. **Thiết kế transaction:** transaction phải bao quanh thời gian tiêu thụ stream nếu driver cần cursor.
5. **Cấu hình fetch size:** đặt trên JDBC Statement hoặc template phù hợp.
6. **Kiểm tra driver:** xác nhận cursor/incremental fetch và điều kiện autocommit.
7. **Đóng tài nguyên:** dùng try-with-resources, kể cả khi dừng sớm hoặc có lỗi.
8. **Đo connection occupancy:** theo dõi thời gian giữ connection và pool pressure.
9. **Giới hạn công việc chậm:** tránh gọi network hoặc chờ người dùng trong khi giữ stream.
10. **Cân nhắc keyset pagination:** nếu cần batch transaction ngắn, retry và checkpoint.
11. **Kiểm thử tải:** dùng database/driver và số lượng hàng gần môi trường triển khai.

## 17. Bài tập thực hành

### Bài 1 — So sánh List và Stream

1. Viết một query trả về `List<PurchaseOrder>`.
2. Viết query tương đương trả về `Stream<PurchaseOrder>` nếu version hỗ trợ.
3. Đọc một tập dữ liệu đủ lớn.
4. Quan sát heap và thời gian hoàn tất.
5. Xác nhận stream được đóng sau khi xử lý.

### Bài 2 — Fetch size

1. Dùng `JdbcTemplate` và `PreparedStatement.setFetchSize`.
2. Thử các giá trị 100, 500 và 1.000.
3. Giữ nguyên query và tập dữ liệu.
4. Đo heap, throughput và connection hold time.
5. So sánh kết quả trên driver mục tiêu.

### Bài 3 — Transaction boundary

1. Mở stream trong một service method.
2. Tiêu thụ stream trong transaction read-only.
3. Thử trả stream ra ngoài method.
4. Quan sát lỗi hoặc hành vi khi transaction kết thúc sớm.
5. Đưa việc tiêu thụ trở lại bên trong transaction.

### Bài 4 — Connection pool

1. Mở nhiều stream đồng thời.
2. Cố ý làm chậm processor.
3. Theo dõi active, idle và pending connection.
4. Giới hạn số worker.
5. So sánh với batch processing.

### Bài 5 — Keyset pagination

1. Viết query `id > :lastSeenId ORDER BY id LIMIT :batchSize`.
2. Xử lý một batch rồi đóng query.
3. Lưu checkpoint ID cuối cùng.
4. Tiếp tục từ checkpoint sau khi khởi động lại job.
5. Kiểm tra trường hợp dữ liệu mới được thêm trong lúc export.

## 18. Kết luận

Streaming giúp xử lý tập kết quả lớn mà không cần luôn materialize toàn bộ thành một `List`, nhưng hiệu quả bộ nhớ phụ thuộc cách Spring Data JDBC, JDBC driver và code tiêu thụ kết quả. `fetch size` là hint cho driver về số hàng lấy mỗi lượt; nó không giới hạn tổng kết quả và không bảo đảm một mức heap cố định.

Một stream JDBC có thể giữ ResultSet, Statement, connection và transaction trong suốt thời gian tiêu thụ. Hãy dùng try-with-resources, đặt transaction boundary bao quanh việc đọc, xử lý nhanh từng hàng và theo dõi connection pool. Tránh gọi API chậm hoặc chạy song song trên cùng JDBC stream.

Nếu công việc kéo dài, cần retry hoặc cần trả connection giữa các nhóm xử lý, keyset pagination theo batch thường dễ kiểm soát hơn. Dù chọn streaming hay batch, hãy đo trên đúng database và driver mục tiêu, ghi rõ fetch size cùng cấu hình đã thử, và không khái quát kết quả của một driver thành bảo đảm cho mọi hệ quản trị.
