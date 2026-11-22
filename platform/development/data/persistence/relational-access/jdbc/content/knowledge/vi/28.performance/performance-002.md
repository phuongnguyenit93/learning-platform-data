# Phân biệt nút thắt SQL, mạng, driver và mã Java trong JDBC

Trong chương **Hiệu năng**, tối ưu một chức năng truy cập cơ sở dữ liệu bằng JDBC không nên bắt đầu bằng việc tăng kích thước connection pool hoặc thêm `setFetchSize(1000)` theo cảm tính. Một API có thời gian phản hồi 800 ms có thể chậm vì SQL quét hàng triệu dòng, vì chờ khóa, vì mạng có độ trễ cao, vì driver trao đổi dữ liệu theo nhiều lượt, hoặc vì Java tốn thời gian giải mã và biến đổi hàng trả về. Những nguyên nhân đó cần **bằng chứng khác nhau** và cách sửa cũng khác nhau.

Ví dụ, cùng một truy vấn `SELECT` có thể chạy 20 ms theo bộ đo trên database nhưng phương thức Java mất 600 ms. Không thể kết luận ngay driver chậm: ứng dụng có thể chờ lấy connection từ pool, tải nhiều megabyte dữ liệu qua mạng, gọi `ResultSet.next()` làm phát sinh thêm nhiều lần fetch, hoặc parse JSON trên từng hàng. Ngược lại, một câu `executeQuery()` nhanh cũng không chứng minh query nhanh: một số driver bắt đầu trả kết quả trước khi mọi hàng được đọc.

Bài học hướng dẫn chia thời gian thành từng giai đoạn của `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`, liên hệ với số liệu từ cơ sở dữ liệu và hệ thống mạng, rồi thiết kế phép thử có thể phân biệt **nút thắt SQL – mạng – driver – mã Java**. Những ví dụ dùng SQL tham số hóa và JDBC chuẩn; hành vi fetch, cursor, timeout và cache cụ thể vẫn phụ thuộc driver/DB.

## 1. Một request JDBC thực sự trải qua những gì?

Sơ đồ giản lược:

```text
HTTP / Job
    |
    | Java: kiểm tra input, xử lý nghiệp vụ
    v
DataSource.getConnection()    <--- chờ pool, tạo/kiểm tra kết nối nếu cần
    |
    v
Connection.prepareStatement() <--- đối tượng Java / thao tác driver
    |
    v
bind tham số + executeQuery()
    |
    +----> Driver: mã hóa tham số, giao thức, TLS, gửi SQL
    |          |
    |          +----> Mạng: độ trễ, băng thông, retransmit
    |                         |
    |                         +----> DB: parse/plan/execute, đọc dữ liệu,
    |                                   lọc/sort/join, chờ khóa, tạo kết quả
    |                         |
    |          <--------------+
    v
ResultSet.next()/getXxx()     <--- có thể fetch thêm qua mạng, giải mã kiểu
    |
    v
Java: ánh xạ DTO, parse JSON, tính toán, tạo response
    |
    v
ResultSet/Statement/Connection.close()
    |
    v
Pool nhận lại kết nối, response được gửi về client
```

Đường thực tế không nhất thiết tuần tự hoàn toàn: driver có thể chuẩn bị statement trên server sớm hoặc muộn, tải một phần kết quả ở `executeQuery()`, đệm toàn bộ hoặc fetch khi gọi `next()`. Vì vậy, mỗi thời gian đo ở phía Java thường là **hỗn hợp** của nhiều thành phần.

Có thể phân rã gần đúng:

\[
T_{\mathrm{JDBC}} \approx T_{\mathrm{borrow}} + T_{\mathrm{prepare/bind}} +
T_{\mathrm{execute\_return}} + T_{\mathrm{consume}} + T_{\mathrm{cleanup}}
\]

Đây là cách **chia thời gian đo**, không phải công thức tách được thời gian thuần SQL, mạng và driver. Chẳng hạn, cả `T_execute_return` lẫn `T_consume` đều có thể bao gồm việc DB thực thi, trao đổi qua mạng và chuyển đổi dữ liệu trong driver.

## 2. Ma trận dấu hiệu: nghi ngờ lớp nào?

| Quan sát | Giả thuyết nên kiểm tra | Bằng chứng cần thêm |
| --- | --- | --- |
| Database báo truy vấn chậm, nhiều hàng scan/sort | SQL, index hoặc thống kê/kế hoạch truy vấn | `EXPLAIN`, actual rows, buffer/I/O, thời gian DB |
| SQL đợi lock dù CPU DB thấp | Tranh chấp khóa/transaction | Wait event, blocking session, tuổi transaction |
| `getConnection()` chậm, pool có nhiều waiter | Pool cạn, kết nối giữ lâu hoặc DB kết nối chậm | Active/idle/pending, acquisition time, hold time |
| DB query nhanh nhưng ứng dụng xa DB chậm | Mạng hoặc số lượt round-trip | RTT, số request/fetch, số byte, so sánh cùng vùng mạng |
| `executeQuery()` nhanh, vòng `rs.next()` chậm | Fetch nhiều đợt, hàng lớn, driver hoặc mapping | Thời gian `next/getXxx`, số hàng, bytes, CPU/allocations |
| Chậm khi đọc `getObject()`/`getString()` loại SQL đặc biệt | Chuyển kiểu ở driver, mã hóa ký tự, dữ liệu lớn | Kiểu cột, profiler, thử getter tương ứng |
| CPU Java/GC cao trong lúc DB rảnh | Ánh xạ DTO, parse JSON, logic hoặc tạo quá nhiều object | CPU profiler, allocation profile, GC logs |
| Một request phát rất nhiều SQL nhỏ | Mẫu N+1 hoặc vòng lặp gọi DB | SQL count/request, trace, số lượt qua mạng |
| Lần đầu chậm, lần sau nhanh | Khởi động kết nối, cache, JIT, page cache, server prepare | Phép đo lạnh/ấm có kiểm soát |

**Một dấu hiệu không đủ kết luận.** Ví dụ `ResultSet.next()` chậm không chứng minh Java chậm: driver có thể đang chờ một lượt tải dữ liệu mới từ DB. Tương tự, tăng `fetchSize` giúp nhanh hơn không chứng minh DB engine chậm; nó có thể chỉ làm giảm số lượt truyền mạng.

## 3. Đo đúng các mốc của một thao tác JDBC

Tối thiểu nên ghi:

1. **Thời gian mượn kết nối**: trước/sau `DataSource.getConnection()`; bao gồm chờ pool và đôi khi kiểm tra hoặc tạo kết nối vật lý.
2. **Thời gian chuẩn bị và bind**: `prepareStatement`, `setLong`, `setString`, cấu hình statement; không mặc nhiên tương đương thời gian parse SQL trên server.
3. **Thời gian tới khi `executeQuery()` trả về**: có thể mới chứa một phần thực thi và một phần dữ liệu.
4. **Thời gian duyệt và đọc kết quả**: `next()`, `getXxx()`, mọi lần fetch bổ sung, ánh xạ/transform Java.
5. **Thời gian đóng tài nguyên**: đóng cursor, statement, kết nối logic và trả về pool; có thể có I/O tùy driver.
6. **Thời gian xử lý ngoài JDBC**: serialize HTTP response, gọi service khác, làm việc CPU/I/O; không cộng nhầm vào “SQL time”.

Dùng `System.nanoTime()` cho **khoảng thời gian**. `System.currentTimeMillis()` thích hợp để ghi timestamp lịch, không phải lựa chọn tốt nhất để lấy hiệu đo độ trễ vì đồng hồ hệ thống có thể được điều chỉnh.

### Ví dụ Java: đo 5 giai đoạn, không giữ toàn bộ kết quả trong heap

Giả sử bảng `product(id, tenant_id, title)` và DB hỗ trợ cú pháp `LIMIT ?` (ví dụ PostgreSQL/MySQL/SQLite với driver tương ứng). Phương thức sau đo một truy vấn theo trang, chỉ đếm và đọc cột thay vì đưa mọi hàng vào một danh sách lớn:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

public final class JdbcQueryProbe {
    private final DataSource dataSource;

    public JdbcQueryProbe(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public record ProbeResult(
            long acquireMs,
            long prepareAndBindMs,
            long executeReturnMs,
            long consumeMs,
            long closeMs,
            int rows,
            long titleCharacters) {}

    private static long millis(long nanos) {
        return TimeUnit.NANOSECONDS.toMillis(nanos);
    }

    public ProbeResult measure(long tenantId, long afterId, int pageSize)
            throws SQLException {
        if (pageSize < 1 || pageSize > 1000) {
            throw new IllegalArgumentException("pageSize phải trong [1,1000]");
        }

        String sql = """
                SELECT id, title
                FROM product
                WHERE tenant_id = ? AND id > ?
                ORDER BY id
                LIMIT ?
                """;

        long t0 = System.nanoTime();
        long acquiredAt;
        long preparedAt;
        long executeReturnedAt;
        long consumedAt;
        int count = 0;
        long characters = 0L;

        try (Connection connection = dataSource.getConnection()) {
            acquiredAt = System.nanoTime();

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setLong(1, tenantId);
                ps.setLong(2, afterId);
                ps.setInt(3, pageSize);

                ps.setFetchSize(200);   // Gợi ý, không bảo đảm 200 hàng/fetch.
                ps.setQueryTimeout(15); // Giây, hỗ trợ phụ thuộc driver.
                preparedAt = System.nanoTime();

                try (ResultSet rs = ps.executeQuery()) {
                    executeReturnedAt = System.nanoTime();

                    while (rs.next()) {
                        rs.getLong("id");
                        String title = rs.getString("title");
                        if (title != null) {
                            characters += title.length();
                        }
                        count++;
                    }
                    consumedAt = System.nanoTime();
                }
            }
        }

        long closedAt = System.nanoTime();
        return new ProbeResult(
                millis(acquiredAt - t0),
                millis(preparedAt - acquiredAt),
                millis(executeReturnedAt - preparedAt),
                millis(consumedAt - executeReturnedAt),
                millis(closedAt - consumedAt),
                count,
                characters);
    }
}
```

`try-with-resources` bảo đảm các tài nguyên được đóng khi thành công **và khi ném lỗi**. Nếu thao tác ném `SQLException`, ví dụ này truyền lỗi cho tầng gọi; hệ thống quan sát nên có nhánh ghi metric **thất bại theo giai đoạn**, thay vì chỉ đo request thành công. Hàm nhận `afterId` để dùng keyset, tránh phép thử ở offset quá sâu che lấp phân tích về driver/mạng.

**Cách đọc kết quả:** `executeReturnMs` là từ sau khi bind/cấu hình đến lúc `executeQuery()` trả về; `consumeMs` gồm cả đọc cursor, chuyển đổi kiểu, có thể nhiều round-trip mạng và xử lý Java. `closeMs` bao gồm đóng `ResultSet`, `PreparedStatement` và `Connection`. Do dùng mili giây nguyên, các giai đoạn rất ngắn có thể được hiển thị là `0`; khi cần độ phân giải tốt hơn hãy lưu nano/micro giây trong metrics.

Nếu DB khác không hỗ trợ `LIMIT ?`, thay bằng cú pháp phân trang phù hợp và xác minh query plan. `setFetchSize(200)` và `setQueryTimeout(15)` đều có thể được driver xử lý như gợi ý/khả năng tùy môi trường; chúng **không** bảo đảm truy vấn luôn dừng sau đúng 15 giây hoặc chỉ tải 200 hàng mỗi lần.

## 4. Nút thắt SQL: kế hoạch truy vấn, I/O và chờ khóa

Nếu phép đo trên DB cho thấy phần thực thi máy chủ tốn nhiều thời gian, hãy xem SQL trước khi tối ưu Java.

### Quan sát chính xác ở phía cơ sở dữ liệu

- **Kế hoạch thực thi:** `EXPLAIN` hoặc công cụ tương đương cho biết DB có quét bảng, sử dụng index, sort, join hoặc materialize trung gian không.
- **Kế hoạch có số liệu thực thi:** một số DB cung cấp `EXPLAIN ANALYZE`, số hàng thực tế, số lần lặp, thời gian từng node và thống kê buffer. **Cẩn thận:** `EXPLAIN ANALYZE` có thể thật sự chạy câu lệnh; không chạy bừa với `UPDATE`/`DELETE` trên dữ liệu production.
- **Thống kê:** cardinality, độ chọn lọc, histogram và thời điểm cập nhật thống kê có thể ảnh hưởng việc chọn plan.
- **Khóa và transaction:** truy vấn có thể “chậm” vì đợi một transaction khác, không phải vì tính toán SQL nặng.
- **Tài nguyên DB:** CPU, disk I/O, buffer-cache hit/miss, memory cho sort/hash và áp lực log/transaction.

Ví dụ một query lọc theo tenant và sắp xếp theo khóa:

```sql
SELECT id, title
FROM product
WHERE tenant_id = ?
  AND id > ?
ORDER BY id
LIMIT ?;

-- Chỉ mục tham khảo cho hệ quản trị hỗ trợ cú pháp này:
CREATE INDEX idx_product_tenant_id
    ON product (tenant_id, id);
```

Chỉ mục `(tenant_id, id)` có thể giúp tìm hàng trong một tenant theo thứ tự id, nhưng không phải bảo đảm DB sẽ dùng nó ở mọi kích thước và phân phối dữ liệu. Trước/sau khi tạo hoặc thay index, kiểm tra plan thực tế và chi phí ghi dữ liệu do index mang lại.

### Những mẫu SQL gây chậm thường gặp

| Mẫu | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| `SELECT *` trong danh sách chỉ cần 2–3 cột | Kích thước hàng lớn, truyền nhiều byte | Chỉ lấy cột cần thiết |
| Lọc trên cột thiếu index thích hợp | Quét nhiều hàng, I/O cao | Đánh giá index dựa trên predicate và thứ tự |
| `ORDER BY`/`GROUP BY` lớn | Sort/hash tốn CPU và bộ nhớ DB | Giảm số hàng, tối ưu index/truy vấn |
| `LIKE '%keyword%'` hoặc biểu thức bọc cột | Khó dùng index B-tree thông thường | Xem cơ chế tìm kiếm/chỉ mục phù hợp DB |
| Join tăng số hàng trung gian | ResultSet lớn hơn dự kiến | Xem cardinality, khóa join, chọn cột và predicate |
| Nhiều cập nhật cùng hàng | Chờ khóa, deadlock/serialization | Rút ngắn transaction, thứ tự khóa thống nhất |
| Paginate bằng `OFFSET` rất sâu | Phải bỏ qua số lượng lớn hàng | Cân nhắc keyset pagination |

**Đo thời gian server không đồng nghĩa đo toàn bộ thời gian response.** Một query chạy nhanh trên DB nhưng trả 500 MB dữ liệu vẫn có thể mất nhiều giây để truyền và ánh xạ ở Java.

## 5. Nút thắt mạng: round-trip, băng thông và payload

Mạng có hai thành phần cần quan sát riêng:

1. **Độ trễ mỗi lượt trao đổi** (*round-trip time*, RTT): khi ứng dụng hỏi DB nhiều lần, mỗi lượt có thể chờ một phần độ trễ mạng.
2. **Khối lượng dữ liệu**: hàng lớn, nhiều cột hoặc hàng triệu bản ghi có thể mất thời gian truyền ngay cả khi RTT thấp.

Giả sử một thao tác phát 100 câu `SELECT` riêng và RTT giữa ứng dụng với DB là 10 ms. Chỉ riêng các lượt trao đổi tuần tự có thể đóng góp thời gian đáng kể; nhưng **không thể lấy `100 × 10 ms` làm thời gian thực tế chắc chắn**, vì driver/giao thức có thể kết hợp hoặc pipeline một số lượt và SQL/server cũng làm việc song song. Phải quan sát số request thực và thời gian mạng của môi trường.

### Dấu hiệu nghiêng về mạng

- Cùng SQL và dữ liệu, ứng dụng đặt gần DB nhanh hơn đáng kể ứng dụng chạy ở vùng địa lý khác.
- DB báo thời gian thực thi thấp nhưng phía Java đọc hết `ResultSet` chậm, trong khi CPU Java và DB không bão hòa.
- Giảm số cột hoặc số hàng trả về cải thiện đáng kể thời gian dù plan SQL gần như không đổi.
- Thay đổi fetch size hoặc cơ chế cursor làm thay đổi số round-trip và tổng độ trễ.
- Có packet loss/retransmit, băng thông bị giới hạn, hoặc TLS/connection handshake tốn nhiều thời gian khi tạo kết nối mới.

**Cẩn trọng:** Đọc chậm ở Java có thể kéo dài thời gian DB gửi kết quả (*backpressure*), nên chỉ nhìn biểu đồ DB cũng dễ nhầm. Kết hợp network metrics, thời gian DB, row count và profiling driver/app.

### Giảm số lượt đi lại trước khi tăng pool

Ví dụ N+1: lấy danh sách 100 đơn hàng, sau đó mỗi đơn gọi một câu `SELECT customer_name FROM customer WHERE id = ?`. Đây có thể là 101 lần gọi DB. Trong một số nghiệp vụ, một query `JOIN` hoặc một truy vấn theo tập ID giúp giảm round-trip:

```sql
-- Một query có thể thay thế nhiều lookup tuần tự:
SELECT o.id, o.total_amount, c.name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.tenant_id = ? AND o.id > ?
ORDER BY o.id
LIMIT ?;
```

Vẫn phải xem cardinality của join: một join một-nhiều có thể nhân số hàng và tạo payload lớn. Cần đo kết quả thực, không coi “ít câu SQL hơn” là luôn tốt hơn.

## 6. Nút thắt driver JDBC: fetch, mã hóa kiểu và buffering

Driver là lớp chuyển `PreparedStatement`, tham số Java và kết quả SQL sang giao thức của DB. Khi nghi ngờ driver, điều tra **hành vi cụ thể** thay vì mặc định mọi driver xử lý giống nhau.

### `setFetchSize(...)` không phải `LIMIT`

`Statement.setFetchSize(int rows)` là một **gợi ý** về số hàng driver nên lấy trong một lượt giao tiếp khi cần thêm dữ liệu. Nó không bảo đảm:

- Driver luôn lấy đúng `rows` hàng từ server.
- Driver không đệm toàn bộ kết quả.
- SQL chỉ chạy trên `rows` hàng hoặc tổng số hàng bị giới hạn.
- Mọi DB đều dùng server-side cursor khi cài fetch size lớn hơn 0.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, title FROM product WHERE tenant_id = ? ORDER BY id")) {
    ps.setLong(1, tenantId);
    ps.setFetchSize(200); // Gợi ý driver, không phải giới hạn tổng số hàng.

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            consumeRow(rs.getLong("id"), rs.getString("title"));
        }
    }
}
```

Đoạn này giả định `consumeRow(...)` là hàm xử lý hàng của ứng dụng. Một số driver (ví dụ cấu hình PostgreSQL JDBC dùng cursor) cần điều kiện transaction và loại ResultSet thích hợp mới thực sự fetch theo lô; một số driver khác có thuộc tính connection/statement riêng để bật streaming. **Không tự áp dụng cấu hình của driver này cho driver khác.**

Muốn lấy 20 hàng, ưu tiên **`LIMIT` hoặc cú pháp phân trang SQL phù hợp DB**; muốn đọc nhiều hàng với giới hạn bộ nhớ và ít round-trip hơn, hãy đánh giá fetch size và streaming theo driver.

### Chuẩn bị statement và cache

- `Connection.prepareStatement(sql)` có thể chỉ tạo đối tượng phía Java hoặc có thể liên quan tới chuẩn bị trên server, tùy driver/cấu hình.
- Driver/pool có thể cache prepared statement hoặc server plan; đây không phải hành vi đồng nhất của JDBC chuẩn.
- Thử thay cách bind, `setObject`, `getObject`, cột JSON/UUID, thời gian/LOB cần phân biệt chuyển đổi của driver và chi phí parse/serialize của code Java.
- Việc bật rewrite batch có thể thay đổi số lượt gửi SQL và semantics trả generated keys/update counts; phải kiểm tra trên DB/driver thật.
- Phiên bản driver mới có thể sửa hiệu năng, nhưng cũng có thay đổi giao thức, fetch, timeout hoặc bộ nhớ; cần kiểm thử hồi quy trước/sau nâng cấp.

Không suy ra “driver chậm” chỉ vì một phương thức `getObject()` tốn thời gian. Nếu lần gọi đó bắt đầu fetch thêm dữ liệu, phần chờ mạng/DB có thể chiếm đa số. CPU profiler và trace giao thức ở mức phù hợp sẽ giúp phân tách.

### Cảnh báo khi đo `executeQuery()`

Nếu `executeQuery()` trả `ResultSet` sau 15 ms nhưng vòng `while (rs.next())` tốn thêm 500 ms, thời gian thực thi DB có thể vẫn kéo dài khi các trang kết quả được fetch. Để kết luận, so đồng thời số liệu server, thời gian `execute`, thời gian tiêu thụ và tổng số hàng/byte đã đọc.

## 7. Nút thắt mã Java: mapping, cấp phát và GC

Sau khi nhận dữ liệu từ driver, một ứng dụng thường biến mỗi hàng thành DTO, parse JSON, chuyển timestamp, kiểm tra quyền, tính toán nghiệp vụ rồi đưa vào collection hoặc response. Khi số hàng lớn, phần này có thể chiếm đáng kể thời gian và bộ nhớ.

Ví dụ một vòng xử lý hàng:

```java
while (rs.next()) {
    long id = rs.getLong("id");
    String title = rs.getString("title");

    // Không nhất thiết cần tạo object nếu chỉ đếm hay tổng hợp.
    ProductDto dto = new ProductDto(id, title);
    results.add(dto);
}
```

`ProductDto` và `results` là class/collection giả định. Nếu chỉ cần xuất tổng hợp, không phải lúc nào cũng nên tạo DTO cho từng hàng. Nếu cần trả một trang cho HTTP client, giới hạn trang từ SQL để không xây danh sách hàng triệu phần tử.

### Dấu hiệu thuộc Java

- CPU profiler cho thấy nhiều thời gian ở JSON parser, mapper, formatter hoặc logic nghiệp vụ, không ở socket read.
- Allocation profiler cho thấy tạo nhiều object tạm, `byte[]`, `String` hoặc một cấu trúc trung gian trên mỗi hàng.
- GC pause hoặc tần suất GC tăng rõ khi trả kết quả lớn.
- Đổi từ mapping toàn bộ sang streaming/tiêu thụ tăng dần giúp giảm peak heap, trong khi thời gian DB gần như không đổi.
- Cùng một `ResultSet`, thao tác chỉ đếm hàng nhanh hơn đáng kể thao tác parse/transform đầy đủ. **Phép thử này vẫn phải đọc cùng lượng dữ liệu**, tránh so sánh hai query có payload khác nhau mà kết luận sai.

### Chọn đúng kiểu và giới hạn dữ liệu

Với tiền tệ, `BigDecimal` cho độ chính xác nhưng việc parse và tính toán có chi phí; không đổi sang `double` chỉ vì muốn nhanh nếu làm sai nghiệp vụ. Với BLOB/CLOB, dùng `getBinaryStream`/`getCharacterStream` khi cần truyền/đọc nội dung lớn và giữ connection mở trong suốt quá trình tiêu thụ. Đừng gọi `getBytes` cho tệp hàng trăm MB khi không cần toàn bộ dữ liệu trong heap.

Nếu CPU Java tốn nhiều thời gian để serialize response, đây có thể là **nút thắt ngoài JDBC**, dù kết quả SQL đã trả nhanh. Đo riêng serialize HTTP và thời gian gửi dữ liệu tới client để tránh quy chậm vào database.

## 8. Pool, transaction và khóa: nút thắt trước khi SQL bắt đầu

Một request mất 700 ms ở `getConnection()` và chỉ 20 ms ở `executeQuery()` không nên được “sửa” bằng một index mới. Hãy kiểm tra:

| Tình huống | Cần đo/xem |
| --- | --- |
| Chờ connection rảnh | Pool active/idle/pending, acquisition time, connection timeout |
| Connection bị giữ quá lâu | Checkout/hold duration, stack mượn/trả, tài nguyên ResultSet/LOB |
| SQL hoặc transaction chờ khóa | Wait events, blocking sessions, tuổi transaction, deadlock |
| Pool tạo kết nối mới chậm | Handshake, xác thực DB, kiểm tra kết nối, DNS/TLS/mạng |
| Pool quá nhỏ hoặc DB quá tải | Throughput, concurrency, CPU/I/O và connection capacity |
| Connection không được `close()` | Rò rỉ tài nguyên ở nhánh exception hoặc callback |

`DataSource.getConnection()` nhanh không chứng minh database đủ công suất; truy vấn có thể xếp hàng ở DB sau đó. Ngược lại, active sát kích thước tối đa không đủ kết luận leak: một đợt transaction hợp lệ nhưng dài cũng có thể mượn toàn bộ pool.

**Quy tắc vòng đời:** mượn connection càng sát thời điểm cần truy vấn càng tốt; đóng bằng `try-with-resources` sau khi đọc xong. Đừng giữ connection trong khi gọi HTTP ngoài, đợi người dùng, dựng PDF lớn hoặc thực hiện công việc CPU không cần DB.

Khi một nghiệp vụ có nhiều thao tác ghi, dùng transaction rõ ràng với `setAutoCommit(false)`, `commit()` và `rollback()`, hoặc để transaction manager sở hữu. Không giảm thời gian giữ connection bằng cách bỏ transaction cần thiết: tối ưu phải bảo toàn tính đúng đắn. Cần kiểm tra cả thời gian chờ khóa và khả năng rollback khi phát sinh lỗi.

## 9. Phương pháp chẩn đoán: đo – giả thuyết – thay đổi một biến

Một quy trình có thể tái hiện:

1. **Chọn một thao tác cụ thể.** Ví dụ “lấy trang 50 sản phẩm theo tenant” thay vì chỉ đo thời gian trung bình của toàn API.
2. **Ghi đường cơ sở.** Lưu số hàng trả, kích thước payload, cấu hình pool, phiên bản driver/DB, số request đồng thời, plan SQL và phân phối latency.
3. **Cắm mốc đo.** `getConnection`, `prepare/bind`, `execute`, `next/getXxx`, xử lý Java, `close` và serialization.
4. **Thu thập bằng chứng ở DB.** Truy vấn chậm, plan, actual rows, wait/lock, CPU, memory, I/O và trạng thái transaction.
5. **Xây giả thuyết có thể bác bỏ.** Ví dụ “chi phí cao do `OFFSET 100000`”: dự đoán keyset giảm số hàng scan; nếu plan và thời gian không đổi, giả thuyết cần xem lại.
6. **Chỉ thay một biến chính.** Đổi index, query, fetch size, vị trí app/DB, số cột hoặc logic mapping; giữ dữ liệu và tải tương đương.
7. **Đo nhiều lần.** Có warm-up, phân biệt cache nóng/lạnh, xem median/p95/p99, throughput, lỗi, GC và pool waiters.
8. **Kiểm tra tính đúng đắn.** So số hàng, nội dung và thứ tự kết quả; tối ưu làm thiếu hàng hoặc đổi transaction semantics là không chấp nhận.
9. **Theo dõi sau triển khai.** Giữ metric và cảnh báo để phát hiện hồi quy khi dữ liệu tăng hoặc driver/DB thay đổi.

### Vì sao benchmark một lần dễ sai?

Thời gian phụ thuộc JIT warm-up, cache DB và OS, connection pool vừa khởi động, chuẩn bị statement, background load và trạng thái bộ nhớ. Truy vấn đầu tiên sau deploy có thể khác nhiều lần sau. Không lựa chọn phương án chỉ từ một lần chạy `System.nanoTime()` trên laptop với database trống.

Đối với các yêu cầu có SLA, xem **p95/p99** và tỉ lệ timeout/SQL errors, không chỉ thời gian trung bình. Đếm cả request thất bại hoặc chờ connection timeout; nếu loại các mẫu lỗi khỏi dữ liệu, metric có thể trông tốt hơn thực tế.

## 10. Ma trận thử nghiệm để cô lập từng giả thuyết

| Thay đổi có kiểm soát | Nếu nhanh hơn, có thể gợi ý | Cần tránh kết luận vội |
| --- | --- | --- |
| Chạy cùng SQL trực tiếp trên DB | Phân biệt sơ bộ server với toàn đường JDBC | Công cụ DB có thể không tải hết kết quả như ứng dụng |
| Giữ SQL, giảm số cột và hàng trả | Chi phí truyền/driver/Java phụ thuộc payload | Query plan cũng có thể đổi |
| Giữ SQL và dữ liệu, đặt app gần DB hơn | Độ trễ mạng đáng kể | Tải, cấu hình hạ tầng và cache phải tương đồng |
| Tăng/giảm `fetchSize` có kiểm soát | Số lần fetch hoặc buffering có ảnh hưởng | Driver có thể bỏ qua hint, heap có thể tăng |
| Chuyển 100 lookup thành join/batch query | Round-trip/N+1 đang tốn thời gian | Join có thể nhân hàng hoặc tạo plan tệ hơn |
| Thay `OFFSET` sâu bằng keyset | DB bớt scan/bỏ qua hàng | Keyset thay semantics điều hướng trang |
| Thay mapping nặng bằng logic chỉ đọc/đếm | Chi phí mapping/parse đáng kể | Phải đảm bảo cùng dữ liệu được tải và getters tương đương |
| Xem profiler và giảm cấp phát Java | CPU/GC là yếu tố đáng kể | Tổng latency có thể vẫn bị DB/mạng chi phối |
| Tăng pool size một mức hợp lý | Có thể giảm chờ pool ở tải cụ thể | Có thể che leak hoặc đẩy DB quá tải |
| Chỉ cập nhật driver sau benchmark đối chứng | Hành vi/cải tiến driver có thể ảnh hưởng | Phải kiểm tra regression, plan, kiểu và giao thức |

Mỗi thí nghiệm nên có tiêu chí thành công rõ: chẳng hạn giảm p95 từ 500 ms xuống dưới 300 ms **mà vẫn trả đúng 20 hàng và không tăng lỗi**. Các giá trị là ví dụ minh họa, không phải mức mục tiêu áp dụng cho mọi hệ thống.

## 11. Ba tình huống phân tích từ đầu đến cuối

### Tình huống A: API báo cáo mất 3 giây dù DB báo 40 ms

**Bằng chứng ban đầu:** một truy vấn trả 200.000 hàng; `executeQuery()` trả sớm, nhưng vòng `rs.next()` kéo dài; response JSON rất lớn. **Giả thuyết cần kiểm tra:** nhiều lượt fetch, tải dữ liệu qua mạng và Java serialize lớn, không nhất thiết do SQL engine.

**Cách điều tra:** đo row count/byte, thời gian `next/getXxx`, serialization, CPU/GC, số lượt fetch và RTT. Thử chỉ lấy cột cần thiết, giới hạn/phân trang kết quả và fetch size phù hợp driver. Đừng dùng `SELECT *` hoặc đẩy cả 200.000 hàng ra màn hình chỉ vì SQL nhanh.

### Tình huống B: `getConnection()` chiếm 900 ms

**Bằng chứng ban đầu:** `executeQuery()` trung bình 15 ms; pool có active sát maximum và nhiều thread chờ; DB có một số transaction cũ. **Giả thuyết:** ứng dụng giữ kết nối lâu hoặc có rò rỉ, không phải truy vấn vừa đo thiếu index.

**Cách điều tra:** xem acquisition/hold duration, stack checkout và transaction đang mở; kiểm tra code có giữ `Connection` khi gọi API khác hoặc đọc BLOB chậm không. Sửa quyền sở hữu và thời gian giữ kết nối trước khi cân nhắc thay pool size.

### Tình huống C: Một request có 150 câu SQL nhanh

**Bằng chứng ban đầu:** mỗi `SELECT` mất khoảng vài ms trên DB nhưng request tốn trên một giây, nhất là khi app xa DB. **Giả thuyết:** mẫu N+1 và round-trip tuần tự. **Cách điều tra:** đếm SQL/request, xem trace, đo thời gian mạng; thử gom các truy vấn theo `JOIN` hoặc `IN` với số placeholder có kiểm soát. So kết quả và plan để đảm bảo không thay lỗi latency bằng explosion dữ liệu.

## 12. Thực hành và checklist vận hành

### Bài thực hành

Với bảng `product(id, tenant_id, title)` và `orders(id, customer_id, total_amount)`:

1. Viết một API JDBC truy vấn 100 sản phẩm trong tenant, đo 5 giai đoạn như `JdbcQueryProbe` và tính số hàng/độ dài chuỗi đã đọc.
2. Tạo dữ liệu thử nghiệm đủ lớn; dùng công cụ `EXPLAIN` của DB so sánh query trước/sau index `(tenant_id, id)`. Ghi cả actual rows và thời gian DB.
3. Đo với `fetchSize` thấp, trung bình và cao; theo dõi thời gian đọc toàn bộ kết quả, peak heap và số lượt fetch nếu driver cung cấp.
4. Dùng query chỉ lấy `id`/`title` rồi thêm một cột văn bản lớn. So thời gian DB, row bytes, network và Java; xác định nguồn chậm có thay đổi không.
5. Tạo mô hình N+1 bằng cách truy vấn từng đơn hàng rồi truy vấn tên khách hàng; thử một query `JOIN` tương đương và đối chiếu dữ liệu.
6. Giới hạn pool nhỏ trong môi trường test, dùng hai tác vụ giữ connection lâu. Quan sát acquisition time và waiter, sau đó thu hẹp phạm vi giữ để đo tác động.
7. Thay logic Java ánh xạ thành DTO nặng bằng xử lý chỉ đọc/đếm; dùng profiler/GC để kiểm chứng khác biệt. Không kết luận chỉ từ wall-clock một lần.
8. Viết báo cáo nêu **triệu chứng → phép đo → giả thuyết → thay đổi → kết quả → xác minh dữ liệu** cho từng nút thắt.

### Checklist chẩn đoán nhanh

| Câu hỏi | Nguồn bằng chứng |
| --- | --- |
| Chậm khi mượn connection hay sau khi mượn? | Acquisition metric và pool active/waiters |
| DB mất thời gian thực thi hay đợi khóa? | Query plan, slow-query log, DB wait events |
| Có quá nhiều lượt trao đổi DB không? | SQL count/request, fetch/trace, RTT |
| Payload trả về có lớn hơn nhu cầu không? | Rows, columns, bytes, response size |
| Driver có fetch/buffer toàn bộ dữ liệu không? | Driver docs, fetch metrics, heap và thử `fetchSize` |
| Java có tốn CPU/GC ở mapper hoặc serializer không? | CPU/allocation profiler, GC logs |
| Connection bị giữ vì transaction/streaming quá lâu không? | Hold duration, transaction age, stack |
| Tối ưu có đổi kết quả hoặc giao dịch không? | Regression test, row count, dữ liệu, isolation |

**Ghi nhớ:** Trong JDBC, **thời gian một lời gọi Java không phải thời gian thuần SQL**. Hãy đo riêng mượn connection, prepare/bind, `executeQuery()`, duyệt `ResultSet`, xử lý Java và đóng tài nguyên; ghép số liệu này với plan, lock/wait trên DB, RTT/payload mạng, hành vi fetch của driver và CPU/GC ứng dụng. Chỉ tối ưu sau khi có giả thuyết được phép thử kiểm chứng, và luôn giữ đúng kết quả truy vấn, transaction và vòng đời kết nối.
