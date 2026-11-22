# Kiểm soát bộ nhớ khi đọc hoặc ghi tập dữ liệu lớn

Một câu **SELECT** trả hai triệu hàng có thể hoàn thành tương đối nhanh trên database nhưng làm ứng dụng Java hết heap vì code gọi **getResultList()**, đưa toàn bộ hàng vào **List**, rồi tiếp tục chuyển danh sách đó thành JSON. Ở chiều ngược lại, một job nhập dữ liệu có thể đọc từng dòng từ tệp nhưng vẫn bị **OutOfMemoryError** nếu tích lũy hàng trăm nghìn **PreparedStatement.addBatch()** hoặc entity JPA trong persistence context mà không giải phóng.

Giải pháp không phải đơn giản là tăng **-Xmx**. Cần thiết kế **luồng dữ liệu có giới hạn dung lượng giữ trong bộ nhớ** từ database, driver, ORM đến logic ứng dụng và điểm xuất kết quả. Bài thuộc chương **Hiệu năng** của module **DATA_PERSISTENCE_FUNDAMENTALS**, trong đó người học thiết kế persistence cho Java từ mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch và cô lập đến quản lý kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Các ví dụ sử dụng **PostgreSQL, JDBC, Spring và JPA/Hibernate**, đồng thời chỉ rõ những nơi hành vi phụ thuộc phiên bản, driver hoặc ORM.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao **số hàng trả về**, **số object được giữ**, **kích thước hàng** và **số request chạy đồng thời** quyết định áp lực heap.
- Phân biệt **cursor/streaming**, **fetch size**, **keyset pagination**, **offset pagination** và **batch processing**; biết chọn cách phù hợp.
- Dùng PostgreSQL JDBC với **autoCommit=false**, **fetchSize dương**, vòng đọc **ResultSet** và tài nguyên được đóng rõ ràng để hạn chế việc tải toàn bộ kết quả vào Java.
- Tổ chức ghi theo **lô có kích thước hữu hạn**, dùng **PreparedStatement.addBatch/executeBatch/clearBatch**, giao dịch ngắn và idempotency khi retry.
- Kiểm soát **persistence context** của JPA/Hibernate qua **flush/clear**, projection và giới hạn số entity managed.
- Phân biệt bộ nhớ Java với bộ nhớ dùng ở **database, driver, connection pool, hàng đợi, bộ đệm xuất dữ liệu và cache**.
- Thiết kế **backpressure**, quan sát heap/GC, WAL, I/O, transaction duration và kiểm thử dữ liệu lớn trước khi chọn thông số.

## 2. Vì sao dữ liệu lớn dễ gây lỗi bộ nhớ?

Giả sử một báo cáo có hai triệu hàng. Nếu mỗi hàng sau khi biến thành object Java, chuỗi, collection và metadata chiếm trung bình **800 byte**, riêng phần object tương ứng đã gần **1,6 GB**. Trong thực tế còn có:

- Mảng hoặc node để giữ tham chiếu trong **ArrayList/HashMap**.
- Bộ đệm của JDBC driver hoặc ORM.
- Dữ liệu tạm khi ánh xạ entity sang DTO, serialize JSON/CSV, sort hoặc group.
- Hàng đợi giữa các worker, kết quả bị giữ trong cache, log/tracing.
- Những request khác đang chạy cùng JVM.

Một câu lệnh trông gọn:

~~~java
List<Order> all = repository.findAll();
return all.stream()
        .map(this::toDto)
        .toList();
~~~

có thể giữ đồng thời **entities** và **DTOs**, chưa kể JPA persistence context đang theo dõi các entity. Nếu sau đó HTTP framework còn buffer toàn bộ JSON, áp lực nhớ có thể tăng tiếp.

Vấn đề cốt lõi là **độ phức tạp bộ nhớ theo số bản ghi**:

~~~text
Tải toàn bộ N hàng:        bộ nhớ ứng dụng có thể tăng O(N)
Xử lý tối đa B hàng/lần:    bộ nhớ theo dữ liệu gần O(B), nếu không giữ lại

N = tổng số hàng (có thể hàng triệu)
B = số hàng/bộ đệm được giữ đồng thời (ví dụ vài trăm)
~~~

**O(B) không có nghĩa toàn bộ JVM chắc chắn chỉ dùng đúng B hàng.** Driver, thư viện, bộ đệm mạng, heap overhead, thread, cache và xử lý ứng dụng vẫn dùng bộ nhớ. Đây là cách diễn đạt mục tiêu: **không tích lũy mọi hàng trong bộ nhớ theo N**.

## 3. Xác định bộ nhớ tăng ở tầng nào

Một luồng đọc điển hình:

~~~text
PostgreSQL: query executor, sort/hash/temp files
                |
                v
Network / PostgreSQL JDBC driver: result buffers
                |
                v
JPA persistence context hoặc JDBC RowMapper
                |
                v
Ứng dụng Java: List, Map, DTO, queue, aggregation
                |
                v
Serialization / HTTP response / file writer / message broker
~~~

Một luồng ghi:

~~~text
File/API/message source
         |
         v
Parser và validation
         |
         v
Danh sách/buffer chứa bản ghi chờ ghi
         |
         v
JDBC batch hoặc JPA persistence context
         |
         v
Database: index, lock, WAL, dirty pages, checkpoint
~~~

Không thể chẩn đoán chính xác chỉ từ câu “database xử lý hai triệu hàng”. Cần xác định **nơi tích lũy dữ liệu**:

| Hiện tượng | Nguồn áp lực có thể xảy ra | Biện pháp đầu tiên |
| --- | --- | --- |
| Heap Java tăng theo số hàng đọc | **List**, ORM managed entities, DTO hoặc serializer | Cursor/streaming, projection, keyset, không gom toàn bộ |
| Heap tăng theo số hàng đã insert | **addBatch** chưa execute/clear, JPA context chưa flush/clear | Batch hữu hạn, flush/clear, xử lý từng chunk |
| Java heap ổn nhưng process RSS lớn | Direct/native buffers, thread stacks, JVM khác/OS | Quan sát native memory, thread, container limits |
| Database chậm khi ORDER BY/GROUP BY lớn | Sort/hash aggregate hoặc temporary file trên DB | EXPLAIN, index, giảm dữ liệu, tuning theo workload |
| Pool bị cạn khi streaming lâu | Connection/transaction giữ quá lâu | Chia công việc, giới hạn đồng thời, keyset |
| HTTP gateway timeout khi xuất dữ liệu | Kết quả rất lớn và client đọc chậm | Streaming có backpressure hoặc export job bất đồng bộ |
| WAL và replica lag tăng khi import | Nhiều hàng/index/transaction gây tải ghi | Batch có kiểm soát, staging/COPY, đo commit và replication |

## 4. Chọn đúng chiến lược: streaming, phân trang hay batch

| Tình huống | Lựa chọn thường phù hợp | Điều phải kiểm soát |
| --- | --- | --- |
| Đọc một tập lớn **một lần** để xuất CSV | JDBC cursor/streaming | Fetch size, transaction mở, tốc độ consumer |
| Job cần **checkpoint và chạy lại** sau lỗi | Keyset pagination theo khóa ổn định | Trạng thái cursor, dữ liệu thay đổi khi quét |
| Giao diện web hiển thị từng màn | Phân trang có LIMIT | Tránh tải tất cả; cân nhắc keyset |
| Xử lý nhiều bản ghi và ghi vào DB | Bounded batch + transaction từng chunk | Số bản ghi/chunk, idempotency, retry |
| Nhập hàng triệu hàng vào PostgreSQL | JDBC batch hoặc **COPY** | Streaming input, schema/constraint, WAL và khả năng phục hồi |
| Xử lý entity với JPA/Hibernate | Projection hoặc batch persist + flush/clear | Persistence context, cascade, ID strategy |
| Tính tổng nhóm nhỏ từ dữ liệu rất lớn | SQL aggregation ngay trong DB | Index, group cardinality, query plan |
| Chuyển đổi dữ liệu qua nhiều worker | Hàng đợi có dung lượng hữu hạn | Backpressure, memory per item, concurrency |

Một thao tác đôi khi kết hợp nhiều kỹ thuật: **keyset đọc 500 hàng → kiểm tra → batch ghi 500 hàng → commit → ghi checkpoint → tiếp tục**. Không cần dùng một câu SELECT giữ transaction nhiều giờ nếu công việc có thể chia thành các đơn vị an toàn.

## 5. JDBC mặc định có chắc đọc từng hàng từ server không?

Không. Dù code gọi **ResultSet.next()** từng lần, JDBC driver vẫn có thể **nạp/buffer phần lớn hoặc toàn bộ kết quả** ở client tùy driver, cấu hình và kiểu statement. Việc dùng vòng lặp không tự bảo đảm server gửi kết quả theo những lô nhỏ.

~~~java
try (ResultSet rs = statement.executeQuery()) {
    while (rs.next()) {
        process(rs);
    }
}
~~~

Đoạn code trên chỉ nói **cách ứng dụng tiêu thụ ResultSet**; nó chưa cho biết driver đã giữ bao nhiêu hàng trong bộ nhớ. Muốn giới hạn bộ nhớ, cần **đường truyền dữ liệu và vòng đời ResultSet** phù hợp với DBMS.

Với **PostgreSQL JDBC (pgJDBC)**, một cách thông dụng để driver lấy kết quả theo cursor là:

- Dùng **connection trong transaction**: **autoCommit=false**.
- Dùng **Statement/PreparedStatement forward-only**.
- Đặt **fetchSize là số dương** (ví dụ 500), không để mặc định 0 cho bài toán cần cursor streaming.
- Đảm bảo câu lệnh và kết nối đáp ứng các điều kiện của driver và giao thức; một số lựa chọn cấu hình có thể làm driver không áp dụng cursor.
- Tiêu thụ ResultSet rồi **đóng nó và commit/rollback đúng phạm vi**.

**Các điều kiện này là hướng dẫn cho pgJDBC, không phải quy tắc phổ quát của mọi JDBC driver.** Ví dụ, driver của hệ quản trị khác có cách diễn giải fetch size hoặc streaming riêng.

## 6. Ví dụ đọc PostgreSQL theo cursor và xử lý từng hàng

Giả định bảng **orders** có khóa **(tenant_id, id)** và những cột cần đọc. Service sẽ đọc tuần tự các đơn trong một tenant, gửi từng bản ghi tới một thành phần tiêu thụ **không tích lũy kết quả**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderScanner {
    private final DataSource dataSource;

    public OrderScanner(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @FunctionalInterface
    public interface RowSink {
        void accept(long orderId, long productId, long quantity)
                throws Exception;
    }

    public void scan(long tenantId, RowSink sink) throws Exception {
        String sql = """
            SELECT id, product_id, quantity
            FROM orders
            WHERE tenant_id = ?
            ORDER BY id
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setReadOnly(true);
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        sql,
                        ResultSet.TYPE_FORWARD_ONLY,
                        ResultSet.CONCUR_READ_ONLY)) {
                    statement.setLong(1, tenantId);
                    statement.setFetchSize(500);
                    statement.setQueryTimeout(120);

                    try (ResultSet rows = statement.executeQuery()) {
                        while (rows.next()) {
                            sink.accept(
                                    rows.getLong("id"),
                                    rows.getLong("product_id"),
                                    rows.getLong("quantity"));
                        }
                    }
                }
                connection.commit();
            } catch (Exception failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Ví dụ minh họa **cơ chế tiêu thụ từng hàng**. **RowSink** là một callback có thể ghi ra file hoặc aggregate hữu hạn; nếu implement sink bằng **list.add(...)**, bộ nhớ vẫn tăng theo toàn bộ dữ liệu. Từ khóa **readOnly** được đặt trước khi transaction thực sự bắt đầu. Đoạn code sử dụng Java có text block, giả định đã cấu hình đúng DataSource và PostgreSQL JDBC.

Các điểm quan trọng:

1. **setFetchSize(500)** định hướng driver lấy dữ liệu theo từng đợt, không có nghĩa toàn chương trình chỉ dùng đủ bộ nhớ cho 500 object.
2. **setAutoCommit(false)** cần thiết với cursor-based fetching thông thường của pgJDBC; nếu bật auto-commit, PostgreSQL có thể đóng cursor cùng transaction và driver có thể buffer kết quả theo cách khác.
3. **TYPE_FORWARD_ONLY** là dạng đọc tiến, phù hợp việc xử lý tuần tự thay vì di chuyển ngẫu nhiên trong ResultSet.
4. **ORDER BY id** cung cấp thứ tự ổn định theo khóa đã chọn; nó không tự bảo đảm hiệu quả nếu thiếu index phù hợp hoặc server phải sort lớn.
5. **PreparedStatement, ResultSet và Connection** được đóng ngay cả khi sink ném lỗi. Không giữ ResultSet sau khi transaction kết thúc.
6. **setQueryTimeout(120)** là timeout ở tầng statement theo JDBC, không thay thế deadline của job/HTTP hoặc giới hạn thời gian giữ connection; hành vi khi cursor lấy nhiều lượt dữ liệu phụ thuộc driver.
7. Một read transaction mở suốt quá trình scan có thể ảnh hưởng VACUUM, thời gian giữ snapshot, pool và recovery conflicts. Với job dài, cân nhắc **keyset pagination**.

**Không nên cho sink gọi lại thao tác ghi hoặc truy vấn phức tạp trên chính connection đang phục vụ cursor** mà không hiểu trạng thái transaction/cursor và tính nhất quán. Nếu cần read-transform-write, có thể chia chunk và sử dụng transaction/connection riêng theo quy tắc được thiết kế trước.

## 7. Streaming vẫn có giá vận hành: transaction kéo dài

Cursor streaming thường giải quyết áp lực heap bằng cách **không tải toàn bộ kết quả vào Java ngay**. Nhưng nếu xử lý mỗi hàng mất 20 ms cho một triệu hàng, cursor có thể giữ connection và transaction trong thời gian rất dài.

Chi phí có thể bao gồm:

- Connection bị mượn khỏi pool trong toàn thời gian scan.
- Transaction hoặc snapshot có thể giữ các phiên bản MVCC, ảnh hưởng dọn dẹp dữ liệu cũ.
- Server phải giữ tài nguyên liên quan tới cursor, truy vấn và trạng thái transaction.
- Kết nối mạng có thể bị lỗi giữa chừng; nếu chưa có checkpoint, job phải bắt đầu lại.
- Client chậm có thể khiến luồng xuất dữ liệu đợi, kéo dài thời gian mở transaction.
- Một số môi trường standby có thể hủy truy vấn dài do xung đột với WAL recovery.

**Streaming là chiến lược giới hạn bộ nhớ, không mặc nhiên là chiến lược tốt nhất cho khả năng phục hồi job hoặc thời gian giữ transaction.** Nếu cần chạy hàng giờ và được phép xử lý dữ liệu theo nhiều transaction, keyset pagination thường dễ kiểm soát hơn.

## 8. Keyset pagination để đọc lớn theo từng chunk độc lập

Thay vì mở một ResultSet khổng lồ, dùng khóa có thứ tự:

~~~sql
SELECT id, product_id, quantity
FROM orders
WHERE tenant_id = :tenantId
  AND id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
~~~

Ví dụ keyset:

~~~text
Lần 1: lastSeenId=0   -> id 1..500
Lần 2: lastSeenId=500 -> id 501..1000
Lần 3: lastSeenId=1000 -> id 1001..1500
...
~~~

Ưu điểm khi có index phù hợp:

- Mỗi câu SQL trả **tối đa B hàng**, nên ứng dụng có thể xử lý rồi giải phóng chunk.
- Không cần giữ một transaction/cursor từ đầu đến cuối toàn công việc.
- Có thể lưu **lastSeenId** làm checkpoint để job tiếp tục sau sự cố.
- Với index theo **(tenant_id, id)**, DB có thể tìm vị trí tiếp theo hiệu quả hơn phân trang OFFSET rất sâu.

### 8.1. Code JDBC với bộ nhớ hữu hạn

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderPageReader {
    private final DataSource dataSource;

    public OrderPageReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record OrderRow(long id, long productId, long quantity) {}

    public List<OrderRow> fetch(
            long tenantId, long afterId, int limit) throws SQLException {
        if (limit < 1 || limit > 1000) {
            throw new IllegalArgumentException("limit phải từ 1 đến 1000");
        }
        String sql = """
            SELECT id, product_id, quantity
            FROM orders
            WHERE tenant_id = ? AND id > ?
            ORDER BY id
            LIMIT ?
            """;

        List<OrderRow> result = new ArrayList<>(limit);
        try (Connection connection = dataSource.getConnection();
             PreparedStatement st = connection.prepareStatement(sql)) {
            st.setLong(1, tenantId);
            st.setLong(2, afterId);
            st.setInt(3, limit);
            try (ResultSet rs = st.executeQuery()) {
                while (rs.next()) {
                    result.add(new OrderRow(
                            rs.getLong("id"),
                            rs.getLong("product_id"),
                            rs.getLong("quantity")));
                }
            }
        }
        return result;
    }
}
~~~

Ở ví dụ này, việc trả **List** là có chủ đích vì **List được chặn tối đa 1.000 phần tử**. Lớp điều phối bên ngoài phải xử lý xong từng chunk rồi bỏ tham chiếu tới nó, không đưa tất cả List vào một danh sách chung.

### 8.2. Vì sao OFFSET lớn thường không phù hợp?

~~~sql
SELECT id, product_id, quantity
FROM orders
WHERE tenant_id = ?
ORDER BY id
LIMIT 500 OFFSET 1000000;
~~~

Đối với nhiều kế hoạch truy vấn, DB vẫn phải xử lý/bỏ qua lượng lớn hàng trước khi lấy trang cần thiết. OFFSET cũng có thể tạo ra **thiếu hoặc lặp hàng** khi dữ liệu bị insert/delete trong lúc quét nhiều trang. **Keyset** giúp giảm chi phí seek và có semantics tiến qua mốc rõ hơn, nhưng vẫn cần kế hoạch cho dữ liệu biến đổi đồng thời.

## 9. Tính nhất quán khi quét nhiều chunk

Nếu mỗi trang chạy trong một transaction READ COMMITTED riêng, **mỗi lần đọc có thể thấy một trạng thái dữ liệu khác nhau**. Ví dụ:

- Một hàng mới được insert với ID lớn hơn **lastSeenId** có thể xuất hiện ở trang sau.
- Một hàng mới có khóa thấp hơn mốc đã quét sẽ bị bỏ qua.
- Một hàng vừa được cập nhật có thể thay đổi điều kiện WHERE và ra/vào tập kết quả trong lúc job chạy.
- Nếu phân trang theo cột có thể thay đổi như **updated_at**, cùng một hàng có thể xuất hiện ở nhiều trang.

Do vậy, cần định nghĩa job muốn xử lý **snapshot tại một mốc** hay **mọi hàng đang xuất hiện trong thời gian chạy**.

### 9.1. High-water mark cho tập khóa tăng

Nếu ID được cấp theo thứ tự và job chỉ cần xử lý những hàng nằm trong biên đã chốt, có thể ghi nhận một giới hạn:

~~~sql
SELECT max(id) AS upper_id
FROM orders
WHERE tenant_id = ?;
~~~

Sau đó quét:

~~~sql
SELECT id, product_id, quantity
FROM orders
WHERE tenant_id = ?
  AND id > :lastSeenId
  AND id <= :upperId
ORDER BY id
LIMIT :batchSize;
~~~

**Giới hạn ID không tạo ra một snapshot bất biến**: ID có thể được cấp trước khi transaction commit, một hàng có thể được cập nhật/xóa sau khi tính max, và cột lọc có thể thay đổi. Chỉ dùng thiết kế này khi nghiệp vụ chấp nhận semantics đó hoặc có **snapshot/export manifest** khác làm nguồn chuẩn.

Nếu cần tập hàng đúng tại một thời điểm, cân nhắc snapshot transaction, bảng staging chứa danh sách ID, version/created_at có định nghĩa rõ, hoặc API xuất snapshot của DB. Đánh đổi giữa tính nhất quán và thời gian giữ snapshot phải được đánh giá.

### 9.2. Khóa ghép khi phân trang

Nếu cần sort theo **created_at, id**, hãy dùng khóa ghép để có thứ tự toàn phần:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND (created_at, id) > (:lastCreatedAt, :lastId)
ORDER BY created_at, id
LIMIT :batchSize;
~~~

Cần index thích hợp và một mốc gồm **cả timestamp lẫn ID**. Nếu chỉ lưu timestamp khi nhiều hàng có cùng thời điểm, job có thể bỏ sót hàng. Nếu **created_at** bị sửa hoặc được ghi lùi thời gian, phải xét lại tính đúng của cursor.

## 10. Chỉ đọc những cột và hàng thật sự cần

Giảm số hàng là một nửa bài toán; **giảm kích thước mỗi hàng** cũng quan trọng. Ví dụ bảng orders còn có cột **notes JSONB**, **receipt_blob BYTEA**, **audit_payload** rất lớn. Nếu chỉ cần tổng tiền và ngày, đừng dùng:

~~~sql
SELECT * FROM orders WHERE tenant_id = ?;
~~~

Thay bằng:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND created_at >= ?
ORDER BY created_at, id;
~~~

Một số nguyên tắc:

- Đẩy **WHERE**, **JOIN**, **GROUP BY** và phép tổng hợp xuống DB khi query plan phù hợp.
- Dùng **projection DTO** thay vì nạp toàn entity/quan hệ nếu không cần.
- Tránh **SELECT *** và kéo large objects để sau đó bỏ đi.
- Tránh **N+1 queries** khi ORM truy cập lazy associations trong vòng lặp.
- Kiểm tra **index** cho điều kiện lọc và thứ tự, không giả định thêm LIMIT sẽ làm query nhanh nếu DB phải sort rất nhiều dữ liệu.
- Với dữ liệu nhạy cảm, chỉ đọc cột cần thiết còn giúp giảm phạm vi lộ dữ liệu ở memory, log và file trung gian.

Ví dụ đếm tổng tại DB:

~~~sql
SELECT customer_id, sum(total_amount) AS total
FROM orders
WHERE tenant_id = ?
  AND created_at >= ?
GROUP BY customer_id;
~~~

Vẫn cần xem số lượng nhóm: nếu mỗi khách hàng tạo một nhóm và có hàng triệu khách, kết quả aggregate cũng có thể rất lớn. **Aggregate ở DB không bảo đảm đầu ra luôn nhỏ**.

## 11. Xuất CSV/JSON mà không dựng một List lớn

Với export CSV, một cách tiếp cận là ghép **cursor read** với **BufferedWriter** ghi trực tiếp tới file/output stream:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;

public final class CsvRows {
    private CsvRows() {}

    public static void writeCell(Writer out, String value)
            throws IOException {
        String safe = value == null ? "" : value;
        out.write('"');
        for (int i = 0; i < safe.length(); i++) {
            char c = safe.charAt(i);
            if (c == '"') {
                out.write('"');
                out.write('"');
            } else {
                out.write(c);
            }
        }
        out.write('"');
    }
}
~~~

Ví dụ tạo một dòng:

~~~java
try (BufferedWriter writer = /* Writer cho một file được quản lý */) {
    scanner.scan(tenantId, (orderId, productId, quantity) -> {
        writer.write(Long.toString(orderId));
        writer.write(',');
        writer.write(Long.toString(productId));
        writer.write(',');
        writer.write(Long.toString(quantity));
        writer.newLine();
    });
    writer.flush();
}
~~~

Đây là **phác thảo luồng xuất**, không phải một chương trình có thể biên dịch độc lập: biến **scanner**, **tenantId** và cách tạo Writer phải được cung cấp ở ứng dụng. Hàm **writeCell** minh họa escape CSV khi có text; đoạn xuất ba cột số không gọi hàm này vì chúng đã được chuẩn hóa thành số. Với CSV chứa text do người dùng nhập, cần thêm chính sách chống **CSV formula injection** khi mở bằng spreadsheet nếu đó là yêu cầu bảo mật của sản phẩm.

Những điều cần chú ý:

- **BufferedWriter** chỉ giữ một buffer hữu hạn, không tự chứa toàn bộ file trong heap.
- **writer.flush()** là đồng bộ buffer Java tới tầng stream, **không** tự bảo đảm file đã bền vững sau mất điện; nếu cần phải có chính sách fsync/upload/atomic rename phù hợp.
- Nếu **OutputStream** là HTTP response và client nhận dữ liệu chậm, callback scan cũng chậm, làm **connection/transaction giữ mở**; nên dùng export job bất đồng bộ và lưu file tạm ở nơi có vòng đời quản lý.
- Khi client ngắt kết nối, phải hủy/đóng ResultSet và connection để không giữ tài nguyên vô thời hạn.

## 12. Ghi dữ liệu lớn: batch thay vì một INSERT mỗi hàng

Ghi từng hàng với một round-trip và một COMMIT riêng thường có chi phí lớn. JDBC **PreparedStatement.addBatch()** cho phép gom nhiều bộ tham số và **executeBatch()** để gửi theo đợt, giảm overhead.

~~~text
Nhận một chunk B hàng
    |
    +-- bind và addBatch từng hàng
    +-- executeBatch
    +-- clearBatch
    +-- COMMIT chunk
    +-- giải phóng chunk
    v
Nhận chunk kế tiếp
~~~

Nếu cứ **addBatch** hàng triệu lần rồi mới **executeBatch**, bộ nhớ vẫn có thể tăng theo hàng triệu bộ tham số. Giới hạn batch là phần bắt buộc của thiết kế.

### 12.1. Ví dụ JDBC ghi một chunk có giới hạn

Giả sử bảng **imported_events(job_id, source_id, payload)** có ràng buộc duy nhất **(job_id, source_id)**. Mỗi chunk chứa tối đa 500 bản ghi, được nạp từ nguồn dữ liệu bên ngoài theo cách đã giới hạn memory:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import javax.sql.DataSource;

public final class EventBatchWriter {
    private final DataSource dataSource;

    public EventBatchWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record ImportRow(long sourceId, String payload) {}

    public void writeChunk(long jobId, List<ImportRow> chunk)
            throws SQLException {
        if (chunk.isEmpty()) {
            return;
        }
        if (chunk.size() > 500) {
            throw new IllegalArgumentException("Chunk vượt 500 hàng");
        }

        String sql = """
            INSERT INTO imported_events(job_id, source_id, payload)
            VALUES (?, ?, ?)
            ON CONFLICT (job_id, source_id) DO NOTHING
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    for (ImportRow row : chunk) {
                        statement.setLong(1, jobId);
                        statement.setLong(2, row.sourceId());
                        statement.setString(3, row.payload());
                        statement.addBatch();
                    }
                    statement.executeBatch();
                    statement.clearBatch();
                }
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Ý nghĩa:

- **chunk.size() <= 500** bảo đảm chỉ có tối đa 500 bộ tham số được add trong lần gọi này.
- **executeBatch()** thực hiện các thao tác trong **một transaction**. Nếu lỗi, rollback transaction của chunk.
- **clearBatch()** loại các tham số batch đã thêm; việc đóng statement sau đó cũng giải phóng tài nguyên theo driver.
- **ON CONFLICT DO NOTHING** giúp việc chạy lại cùng cặp key không insert lần hai. Nó chỉ an toàn khi **cùng key thật sự biểu diễn cùng event và payload**; hệ thống thật cần phát hiện xung đột payload, không âm thầm bỏ qua dữ liệu khác.
- Chunk trước đã commit sẽ **không rollback** khi chunk sau thất bại. Job phải có idempotency, checkpoint và chính sách xử lý partial progress.
- **executeBatch()** có thể trả mã **SUCCESS_NO_INFO** tùy driver; không suy rằng mọi phần tử update count luôn bằng 1.

### 12.2. Nên chọn batch size bao nhiêu?

Không có con số tối ưu cố định. Bắt đầu từ một giá trị có kiểm chứng, ví dụ **100–1.000 hàng**, rồi đo:

- Kích thước payload trung bình và lớn nhất, không chỉ số lượng hàng.
- Heap và allocated bytes của JVM.
- Round-trips, throughput, latency executeBatch và commit.
- Mức độ khóa, WAL, index maintenance và replica lag.
- Khả năng retry khi một chunk lỗi và thời gian xử lý lại.

Một batch **500 hàng × 1 KB** khác hoàn toàn **500 hàng × 10 MB**. Với dữ liệu biến thiên mạnh, nên giới hạn **cả số hàng và tổng số byte ước tính** trong chunk.

## 13. Giới hạn bộ nhớ trong pipeline đọc – chuyển đổi – ghi

Giả sử một job đọc file CSV, kiểm tra dữ liệu và ghi database. Nếu parser và validator nhanh hơn writer, hàng đợi trung gian có thể phình tới khi hết heap:

~~~text
CSV reader -> unbounded queue -> validator -> unbounded queue -> DB writer
                       |
                 OOM nếu DB chậm
~~~

Thiết kế tốt hơn:

~~~text
CSV reader -> bounded queue -> validator -> bounded queue -> batch writer
                   |                        |
          Đầy thì reader chờ       Đầy thì validator chờ
~~~

Đây là **backpressure**: phía tiêu thụ chậm làm phía tạo dữ liệu giảm tốc độ, thay vì tiếp tục tích lũy vô hạn.

Các nguyên tắc:

1. Dùng **BlockingQueue có capacity**, channel có giới hạn, hoặc cơ chế reactive với backpressure được thực thi thật.
2. Giới hạn số lượng writer và tổng số batch đang chờ, không chỉ kích thước mỗi batch.
3. Có cơ chế **cancellation, shutdown và truyền lỗi**; producer không được treo mãi khi consumer đã thất bại.
4. Tính cả các object trung gian và dữ liệu lớn bất thường; một phần tử queue có thể rất nặng.
5. Không đọc toàn file vào byte[] hoặc String trước khi tách dòng nếu mục tiêu là streaming.
6. Khi ghi theo thứ tự có ý nghĩa nghiệp vụ, phải xác định chính sách ordering/retry giữa các worker; chạy song song không luôn an toàn.

Một ví dụ kích thước nhớ sơ bộ:

~~~text
2 writer threads × tối đa 500 hàng mỗi batch
+ queue capacity 4 batch × 500 hàng
= tối đa 3.000 hàng ở những vị trí này
~~~

Đó chỉ là tính toán cho **những buffer được nêu**, không tính dữ liệu parser đang xử lý, buffer driver, connection, hoặc các request khác. Nếu mỗi hàng trung bình 20 KB, riêng payload của 3.000 hàng đã có thể đáng kể.

## 14. JPA/Hibernate: persistence context có thể giữ rất nhiều entity

JPA giúp đơn giản hóa logic entity, nhưng một **persistence context** thường giữ các entity managed và trạng thái cần cho dirty checking. Khi import nhiều hàng:

~~~java
@Transactional
public void importAll(List<RawRecord> records) {
    for (RawRecord raw : records) {
        entityManager.persist(toEntity(raw));
    }
}
~~~

Mã trên có hai rủi ro:

1. **records** đã chứa toàn bộ dữ liệu trong memory.
2. Persistence context có thể giữ các entity mới cùng trạng thái theo dõi cho đến khi flush/clear hoặc transaction kết thúc.

Thay vào đó, xử lý từng chunk và chủ động quản lý context:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class JpaImportService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importChunk(List<RawRecord> chunk) {
        if (chunk.size() > 500) {
            throw new IllegalArgumentException("Chunk quá lớn");
        }
        int count = 0;
        for (RawRecord raw : chunk) {
            entityManager.persist(toEntity(raw));
            count++;
            if (count % 100 == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }
        entityManager.flush();
        entityManager.clear();
    }
}
~~~

**Đây là khung code minh họa**: **RawRecord** và **toEntity** do ứng dụng định nghĩa; transaction manager phải được cấu hình, và lời gọi **@Transactional** phải đi qua cơ chế Spring thích hợp. Trong một hệ thống thật, đơn vị chunk và transaction nên do tầng điều phối quyết định; tránh đọc toàn bộ nguồn thành một List rồi mới cắt khúc.

Tại sao phải **flush rồi mới clear**?

- **flush()** đẩy các thao tác pending xuống DB trong transaction, **chưa phải COMMIT**.
- **clear()** tách entity khỏi persistence context và giải phóng bớt bộ nhớ theo dõi; thay đổi **chưa được flush** có thể mất khỏi kế hoạch đồng bộ.
- Nếu sau **clear()** vẫn giữ tham chiếu entity ở một List lớn, object Java **vẫn không được GC**; clear không thay thế việc bỏ tham chiếu ở ứng dụng.
- Entity bị **detached** sau clear, nên không tiếp tục sửa nó và mong dirty checking ghi lại.
- Với quan hệ, cascade và entity graph phức tạp, cần kiểm tra điểm flush/clear có ảnh hưởng bất biến và thứ tự insert hay không.

### 14.1. Batch ORM còn phụ thuộc chiến lược ID

Hibernate có các thuộc tính như **hibernate.jdbc.batch_size** và khả năng sắp xếp insert/update theo cấu hình. Tuy nhiên, chiến lược lấy khóa **IDENTITY** và các lựa chọn khác có thể khiến ORM cần INSERT sớm, ảnh hưởng khả năng JDBC batching. Không suy rằng đặt một property batch_size đồng nghĩa database nhận đúng những batch như dự kiến.

Để đo hiệu quả:

- Bật SQL/driver metrics có kiểm soát thay vì in toàn bộ payload.
- Đếm số round-trip/batch execute thực tế.
- Kiểm tra generated keys, cascade và thứ tự flush.
- So sánh throughput, heap và thời gian commit với JDBC batch hoặc COPY nếu khối lượng lớn.

### 14.2. Đọc JPA bằng stream chưa chắc tự giới hạn memory

Một method repository trả **Stream<Entity>** có thể sử dụng cursor/ResultSet phía dưới tùy provider và truy vấn; cần giữ **transaction mở trong lúc tiêu thụ stream**, đóng stream và kiểm tra fetch size. Nếu trong vòng lặp vẫn giữ entity managed trong context, bộ nhớ vẫn tăng.

Đối với báo cáo chỉ đọc, ưu tiên **projection DTO**, phân trang hoặc JDBC streaming khi cần kiểm soát bộ nhớ rõ hơn. Không dùng **findAll().stream()** rồi cho rằng JVM sẽ đọc từ database từng hàng: **findAll() đã vật chất hóa danh sách** trước đó.

## 15. PostgreSQL COPY cho nhập dữ liệu khối lượng rất lớn

Với nhiều hàng có cấu trúc phù hợp, PostgreSQL **COPY FROM STDIN** là một phương án nhập dữ liệu tốc độ cao. Với driver PostgreSQL JDBC, có thể dùng API **CopyManager** để truyền dữ liệu từ InputStream:

~~~java
import java.io.InputStream;
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public final class CopyImporter {
    private final DataSource dataSource;

    public CopyImporter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long importCsv(InputStream source) throws Exception {
        String sql = """
            COPY staging_events(source_id, payload)
            FROM STDIN WITH (FORMAT csv, HEADER true)
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                PGConnection pg = connection.unwrap(PGConnection.class);
                CopyManager copy = pg.getCopyAPI();
                long imported = copy.copyIn(sql, source);
                connection.commit();
                return imported;
            } catch (Exception failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Ví dụ giả định:

- Đã thêm **pgJDBC** vào dependencies và pool hỗ trợ **unwrap(PGConnection.class)**.
- **staging_events** tồn tại với schema thích hợp; CSV từ InputStream đã được kiểm tra encoding, dấu phân cách, escaping và quyền truy cập.
- **source** được caller sở hữu và đóng đúng cách, ví dụ tại tầng đọc file. Đừng xây dựng InputStream từ **một byte[] chứa toàn bộ tệp khổng lồ** rồi tuyên bố hệ thống streaming.
- Lệnh COPY cố định/đáng tin cậy, không ghép tên bảng/cột từ input không được kiểm tra.

**COPY giúp giảm overhead của nhiều INSERT riêng lẻ**, nhưng không bỏ qua chi phí WAL, index, constraint, disk, transaction hoặc các quy tắc bảo mật. Với data validation phức tạp và retry nhiều phần, có thể **COPY vào staging table**, rồi chuyển sang bảng đích qua những transaction có điều kiện và idempotency.

Nếu COPY nhiều triệu dòng trong một transaction, rollback/retry vẫn tốn kém. Cần thử nghiệm chia file, staging, checkpoint và hành vi khi job bị hủy.

## 16. Đọc/ghi BLOB hoặc nội dung lớn bằng stream

Một hàng có thể chỉ có một bản ghi nhưng chứa **hàng trăm MB** dữ liệu nhị phân. Việc gọi **getBytes()** hoặc dựng một byte[] chứa cả file có thể gây áp lực heap lớn.

JDBC có các API dạng stream, ví dụ:

~~~java
try (InputStream input = resultSet.getBinaryStream("attachment_bytes")) {
    // Copy từng block nhỏ sang OutputStream được quản lý.
}
~~~

Ở chiều ghi:

~~~java
try (InputStream input = /* stream từ nguồn được quản lý */) {
    statement.setBinaryStream(1, input);
    statement.executeUpdate();
}
~~~

Những đoạn mã trên là **minh họa API**, không phải chương trình độc lập: ResultSet/PreparedStatement và transaction phải còn sống trong lúc stream được tiêu thụ, và driver/DBMS có thể quyết định cách buffer nội dung. Không phải mọi cột/driver sẽ thực hiện truyền streaming tuyệt đối chỉ vì Java gọi **getBinaryStream/setBinaryStream**.

Với file rất lớn, cũng cần cân nhắc **object storage** và chỉ lưu metadata/đường dẫn/kiểm tra tính toàn vẹn trong database, tùy yêu cầu transaction, bảo mật, backup và vòng đời nội dung. Điều đó chuyển bài toán ra một hệ thống khác, cần giải quyết atomicity và cleanup giữa DB và object storage.

## 17. Transaction boundary khi xử lý hàng triệu bản ghi

Một giao dịch chứa tất cả các bước nhập dữ liệu có vẻ hấp dẫn vì tính nguyên tử, nhưng với khối lượng quá lớn nó có thể:

- Giữ lock/row versions lâu, tăng áp lực MVCC/VACUUM.
- Tạo lượng WAL lớn, kéo dài replication lag hoặc recovery.
- Giữ connection/pool và kéo dài thời gian COMMIT hoặc rollback.
- Làm mỗi lần thử lại sau lỗi tốn công lớn.
- Dễ gặp timeout, chiếm nhiều tài nguyên ở cả DB và ứng dụng.

Chia thành transaction từng **chunk** giảm rủi ro vận hành nhưng **thay đổi hợp đồng atomicity**:

~~~text
Chunk 1 --> COMMIT
Chunk 2 --> COMMIT
Chunk 3 --> lỗi/ROLLBACK

Kết quả: chunk 1, 2 vẫn tồn tại; không phải toàn job rollback.
~~~

Ứng dụng phải quyết định ý nghĩa của tiến độ từng phần:

1. **Import có thể tiếp tục:** mỗi hàng có ID nguồn duy nhất, ghi idempotent, checkpoint phản ánh chunk đã commit.
2. **Import phải xuất hiện đồng loạt:** nạp vào staging, kiểm tra toàn bộ, sau đó chuyển trạng thái job hoặc công bố phiên bản dữ liệu qua một bước atomic phù hợp.
3. **Import có quan hệ xuyên chunk:** kiểm tra ràng buộc, thứ tự phụ thuộc, khóa ngoại và chính sách khi một chunk thất bại.
4. **Job cần nhất quán snapshot:** xác định phương án giữ snapshot, manifest hoặc watermark; không đánh đồng đọc nhiều chunk với ảnh chụp tại một thời điểm.

### 17.1. Checkpoint phải phản ánh tác động đã commit

Một lỗi thiết kế:

~~~text
Ghi checkpoint "đã xử lý đến dòng 10.000"
           |
           v
Ghi batch 9.501..10.000
           |
       DB rollback
           |
       Job khởi động lại từ dòng 10.001 -> bỏ sót dữ liệu
~~~

An toàn hơn là **ghi tác động và checkpoint trong cùng DB transaction**, hoặc thiết kế ghi idempotent cho phép đọc lại và áp dụng lại chunk mà không tạo tác động trùng. Nếu checkpoint nằm ở nơi lưu trữ khác, phải có kế hoạch đối soát vì không thể giả định hai nơi commit nguyên tử.

Ví dụ:

~~~sql
BEGIN;

-- Ứng dụng thực hiện batch ghi dữ liệu.
-- Sau đó, cùng transaction cập nhật tiến độ:
UPDATE import_jobs
SET last_committed_source_id = :newCheckpoint
WHERE job_id = :jobId;

COMMIT;
~~~

Đây là phác thảo, chưa bao gồm điều kiện version/owner để chống hai worker cùng cập nhật checkpoint. Với pipeline nhiều worker, cần **partition, lease/fencing token** hoặc cơ chế phối hợp thích hợp.

## 18. Retry sau lỗi và chống ghi trùng

Khi batch lỗi vì deadlock, serialization failure hoặc mất connection, job có thể phải retry. Nhưng sau khi client mất kết nối đúng lúc COMMIT, server **có thể đã xác nhận transaction** dù caller nhận SQLException.

Nếu retry cùng batch không có khóa nghiệp vụ, dữ liệu có thể bị chèn hoặc cộng/trừ nhiều lần.

Một số cơ chế:

- Dùng **(job_id, source_id)** làm unique business key cho mỗi record được nhập.
- Dùng **INSERT ... ON CONFLICT** phù hợp để xử lý trùng, nhưng đối chiếu payload khi cùng key có thể mang dữ liệu khác.
- Với thao tác cộng tiền hoặc cộng điểm, dùng **ledger/event ID** duy nhất chứ không chỉ thử lại câu UPDATE tăng số dư.
- Retry **toàn bộ transaction** trong một transaction mới khi DB báo lỗi xung đột có thể retry, không thử tiếp trên transaction PostgreSQL đã abort.
- Kết hợp **bounded attempts, exponential backoff, jitter, deadline** và backpressure, không tạo cơn bão retry khi DB đã quá tải.
- Với staging/import có nhiều pha, dùng trạng thái **NEW/PROCESSING/VALIDATED/PUBLISHED/FAILED** được định nghĩa rõ; consumer không đọc dữ liệu chưa được công bố nếu hợp đồng yêu cầu nguyên tử.

Giới hạn bộ nhớ chỉ giải quyết một loại rủi ro. **Một pipeline dùng O(B) memory nhưng retry tạo bản ghi hai lần vẫn là pipeline sai.**

## 19. Connection pool và số job chạy song song

Giả sử ứng dụng có **8 import workers**, mỗi worker mượn một connection để ghi chunk; cùng lúc có 200 API request. Nếu pool chỉ có 10 connection, những worker giữ transaction lâu có thể khiến API request phải đợi.

Các điểm cần thiết kế:

- Dùng **semaphore/worker limit** để giới hạn số job DB đồng thời.
- Có thể dùng pool riêng cho batch và API để tách ngân sách kết nối, nhưng **tổng connection trên DB vẫn phải được tính chung**.
- Khi cursor export giữ connection lâu, giới hạn số export chạy đồng thời; có thể chuyển export thành job bất đồng bộ.
- Không tăng pool size chỉ vì JVM đã dùng virtual threads; số connection DB vẫn là tài nguyên hữu hạn.
- Quan sát **active/idle/pending, acquisition latency, transaction duration** và trạng thái **idle in transaction**.
- Không giữ connection trong lúc backoff, xử lý CPU lâu, chờ HTTP API hoặc đợi consumer không được giới hạn.

Nếu nguồn dữ liệu có thể đọc theo keyset, mỗi chunk có thể mượn connection ngắn hơn, giúp pool phục vụ request khác giữa các chunk.

## 20. Hiệu năng của database cũng ảnh hưởng bộ nhớ tổng thể

Giảm heap Java không nhất thiết cải thiện thông lượng nếu PostgreSQL phải sort hàng triệu hàng, tạo index tạm hoặc ghi WAL quá lớn.

Ví dụ chẩn đoán:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
ORDER BY created_at, id
LIMIT 500;
~~~

**EXPLAIN ANALYZE thực sự chạy truy vấn**, nên cẩn thận với UPDATE/DELETE và dữ liệu production; với ví dụ SELECT này cũng cần xét độ tốn kém, quyền truy cập và tài nguyên. Quan sát:

- Index scan hay sequential scan, có Sort/Hash không.
- Số hàng ước lượng và thực tế khác nhau bao nhiêu.
- Shared buffer hits/reads, thời gian thực thi và số hàng trả.
- Truy vấn có tạo **temp files** do sort/hash không, nếu có đo từ PostgreSQL phù hợp.

PostgreSQL có các thống kê như **pg_stat_database.temp_bytes** để theo dõi tổng byte temp file đã ghi theo khoảng đo. Nếu dùng **pg_stat_statements**, có thể quan sát các truy vấn tiêu tốn thời gian, số lần chạy và các chỉ số I/O tùy phiên bản/cấu hình.

**work_mem** không phải “bộ nhớ tối đa cho toàn database”: nhiều toán tử sort/hash và nhiều truy vấn đồng thời có thể cùng dùng bộ nhớ. Tăng nó thiếu kiểm chứng có thể làm database hết RAM dù heap Java đã ổn định.

Với ghi lớn, còn phải theo dõi:

- Index maintenance, constraint và trigger.
- WAL bytes, full-page images, checkpoint và fsync latency.
- Replication lag, slot giữ WAL và dung lượng lưu trữ.
- Lock wait và các transaction chạy lâu.
- Autovacuum/vacuum khi cập nhật hoặc xóa rất nhiều hàng.

Không tắt **fsync**, WAL hoặc ràng buộc dữ liệu chỉ để đạt benchmark nhập nhanh mà không đánh giá lại bảo đảm độ bền và phục hồi.

## 21. Đo Java heap, GC và bộ nhớ ngoài heap

Một thiết kế streaming tốt cần có số liệu. Những chỉ số nên thu thập:

| Nhóm | Chỉ số | Vì sao quan trọng |
| --- | --- | --- |
| **Heap** | Used heap sau GC, peak heap, object allocation rate | Phát hiện object tích lũy và tốc độ tạo rác |
| **GC** | Số lần GC, pause p95/p99, thời gian GC theo phút | Xem GC có lấy quá nhiều CPU/độ trễ không |
| **Process/container** | RSS, memory limit, OOM kills | Java có thể dùng memory ngoài heap |
| **Threads/queues** | Số worker, queue depth, batch in flight | Tìm buffer tăng khi DB chậm |
| **JDBC** | Fetch size, số hàng/chunk, batch size, execute latency | Xác định hiệu ứng từ cấu hình đọc/ghi |
| **Pool** | Active, idle, pending, connection wait | Kiểm soát đồng thời và tình trạng cạn pool |
| **DB** | Query plan, lock wait, temp bytes, WAL bytes, replica lag | Không đổ mọi vấn đề cho heap Java |
| **Job** | Rows processed/sec, bytes/sec, checkpoint lag, retries | Đo throughput cùng correctness |

Công cụ Java có thể dùng **Java Flight Recorder (JFR)**, Java Mission Control, heap dump và profiler được phép trong môi trường thử nghiệm. Một số thao tác profiling/heap dump trên production có thể tạo chi phí đáng kể hoặc chứa dữ liệu nhạy cảm, nên phải có quy trình bảo mật và vận hành.

Khi test:

1. Dùng **cùng giới hạn heap/container dự kiến** của production.
2. Thử dữ liệu có **phân phối kích thước thực**, gồm hàng rất lớn, NULL, Unicode, JSON/BLOB và trường hợp lỗi.
3. Đo sau khi hệ thống chạy qua **nhiều chunk**; một chunk nhỏ có thể chưa lộ leak.
4. Tăng số job đồng thời theo kịch bản thật, không chỉ một job đơn độc.
5. Theo dõi **used heap sau GC**; nếu tăng đều theo số hàng đã xử lý, có thể còn tham chiếu giữ dữ liệu.
6. Chạy test khi DB bị chậm và consumer bị nghẽn để xác minh **backpressure**, không chỉ lúc mọi thứ nhanh.

## 22. Mẫu kiến trúc cho job import hàng triệu hàng

Một giải pháp có khả năng tiếp tục và giới hạn bộ nhớ:

~~~text
Nguồn CSV/object storage
          |
          v
Streaming parser
          |
          v
Validator/mapper (chỉ giữ một chunk)
          |
          v
Bounded chunk buffer (số hàng + tổng byte giới hạn)
          |
          v
JDBC batch hoặc COPY vào staging
          |
          v
COMMIT dữ liệu chunk + checkpoint
          |
          v
Đối soát / công bố dữ liệu sau khi toàn job đạt điều kiện
~~~

Một kế hoạch thực thi:

1. Tạo **job_id** và thông tin nguồn dữ liệu (hash/version) để bảo đảm resume không vô tình đọc một file đã thay đổi.
2. Đọc streaming từng dòng; validate sớm và chỉ giữ những bản ghi hợp lệ trong một chunk giới hạn.
3. Ghi chunk trong transaction riêng, sử dụng unique key nguồn, kiểm tra lỗi và đồng bộ checkpoint an toàn.
4. Sau COMMIT thành công, giải phóng chunk, lấy phần tiếp theo.
5. Nếu lỗi tạm thời, rollback, backoff và retry đúng chunk trong transaction mới; nếu lỗi payload vĩnh viễn, ghi nhận theo chính sách lỗi.
6. Khi hoàn tất, đối chiếu tổng số hàng, checksum/aggregate thích hợp và điều kiện nghiệp vụ.
7. Công bố dữ liệu bằng một mốc/version hoặc chuyển trạng thái job nếu người đọc không được thấy tập dữ liệu đang nhập dở.
8. Theo dõi heap/GC, tốc độ, WAL/replication lag, connection pool và hàng đợi.

**Điểm then chốt là không giữ hai triệu hàng cùng lúc**. Mọi bước trong pipeline đều có giới hạn dung lượng hoặc cơ chế chờ phía trước khi nơi nhận chậm.

## 23. Mẫu kiến trúc cho export dữ liệu lớn

Một công việc export có thể chọn:

- **Cursor JDBC** khi tập dữ liệu không quá lâu để duyệt, có thể giữ transaction/connection và cần một thứ tự nhất quán.
- **Keyset pagination** khi job kéo dài, cần checkpoint và chấp nhận hoặc đã xử lý rõ biến động dữ liệu giữa các trang.
- **Server-side export/COPY TO STDOUT** trong PostgreSQL khi cấu trúc và yêu cầu dữ liệu phù hợp; phải quản lý định dạng, quyền và kết nối.
- **Snapshot manifest** nếu cần đúng tập dữ liệu tại một thời điểm mà không muốn giữ một transaction cực dài.

Không dùng HTTP request đồng bộ kéo dài hàng giờ nếu gateway/client có thể ngắt và job không có checkpoint. Có thể trả **202 Accepted + export job ID**, tạo file trong hệ thống lưu trữ, rồi cho client tải khi đã hoàn tất và được ủy quyền.

Đối với export chứa thông tin cá nhân, cần giới hạn quyền, mã hóa/retention của file, thời hạn link tải và cleanup khi job thất bại. Một file tạm chưa xóa cũng là tài nguyên phải quản lý, dù heap Java đã được kiểm soát.

## 24. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “ResultSet.next() đọc từng hàng nên driver không bao giờ buffer lớn.” | Driver có thể buffer nhiều hoặc mọi hàng; pgJDBC cần điều kiện cursor/fetch size phù hợp |
| “setFetchSize(500) luôn hoạt động giống nhau ở mọi driver.” | Đây là một hint/hợp đồng phụ thuộc driver, DBMS và transaction |
| “Tăng -Xmx là giải pháp tổng quát.” | Có thể trì hoãn OOM nhưng không sửa tích lũy O(N) |
| “Stream<Entity> luôn giữ bộ nhớ O(1).” | Persistence context vẫn có thể giữ entity; stream phải được đóng/tiêu thụ đúng scope |
| “clear() là đủ để giải phóng mọi entity.” | List khác có thể còn giữ tham chiếu; clear còn có thể làm mất thay đổi chưa flush |
| “persist() một triệu lần rồi commit một lần là batch tốt nhất.” | Context, WAL và transaction có thể quá lớn |
| “addBatch() hàng triệu lần là tiết kiệm memory.” | Batch parameters có thể tích lũy; cần execute/clear theo ngưỡng |
| “OFFSET sâu tốt ngang keyset.” | OFFSET có thể bỏ qua lượng lớn hàng và gặp thiếu/lặp khi dữ liệu đổi |
| “Keyset chia chunk cho ảnh chụp nhất quán tuyệt đối.” | Mỗi trang có thể thấy dữ liệu khác; cần snapshot/manifest nếu hợp đồng yêu cầu |
| “COPY bỏ qua WAL và constraint.” | COPY vẫn chịu cơ chế DB theo cấu hình, và có thể tạo tải rất lớn |
| “Một triệu hàng/chunk cũng được vì chỉ có một List.” | Kích thước chunk phải chặn theo hàng và byte, xét payload lớn nhất |
| “Đóng ResultSet sau export không quan trọng.” | Cursor/connection/transaction có thể bị giữ, làm cạn pool |
| “Batch commit từng lô vẫn có tính nguyên tử cho toàn job.” | Chunk trước đã commit vẫn còn khi chunk sau rollback |
| “Rollback rồi retry luôn an toàn sau lỗi COMMIT.” | Kết quả commit có thể không rõ; cần idempotency/đối soát |
| “Java heap thấp thì DB cũng ít dùng RAM.” | DB có sort/hash/temp, work_mem và nhiều phiên truy vấn đồng thời |

## 25. Bài tập tự kiểm tra

### Bài 1. List và streaming

Một repository gọi **findAll()** lấy 1,5 triệu entity rồi dùng **.stream().forEach(...)**. Thao tác này đã tránh tích lũy toàn bộ dữ liệu chưa?

**Gợi ý:** **Chưa**. findAll() đã materialize toàn bộ List. Dùng cursor/streaming thực sự hoặc phân trang theo chunk, và kiểm tra JPA persistence context.

### Bài 2. PostgreSQL fetchSize

Một chương trình đặt **setFetchSize(500)** nhưng để **autoCommit=true** rồi gọi SELECT lớn trên pgJDBC. Có chắc driver dùng cursor để fetch từng 500 hàng không?

**Gợi ý:** **Không**. Cursor-based fetching của pgJDBC thông thường cần một transaction với autoCommit=false, forward-only ResultSet và những điều kiện driver khác. Phải đo và xác minh trong môi trường thật.

### Bài 3. Keyset và OFFSET

Job đang đọc trang thứ 10.000 của bảng bằng **OFFSET 5.000.000 LIMIT 500**. Có những vấn đề gì?

**Gợi ý:** DB có thể phải xử lý nhiều hàng để bỏ qua offset; insert/delete trong lúc quét có thể làm trùng hoặc thiếu. Dùng keyset theo khóa ổn định, index thích hợp và hợp đồng rõ về snapshot.

### Bài 4. Persistence context

Trong một transaction, code gọi **persist()** 300.000 lần rồi cuối cùng mới gọi **flush/commit**. Heap tăng liên tục. Thay đổi nào có tác dụng?

**Gợi ý:** Chia dữ liệu nguồn thành chunk, flush rồi clear context theo ngưỡng, bỏ tham chiếu đến entity, cân nhắc transaction từng chunk và kiểm tra Hibernate JDBC batching/ID strategy.

### Bài 5. Flush có phải commit không?

Job JPA gọi **flush()** sau 100 entity rồi gặp lỗi ở entity thứ 150 và rollback. Một trăm entity đầu đã được commit chưa?

**Gợi ý:** **Chưa** nếu vẫn trong cùng transaction. Flush chỉ đồng bộ SQL; rollback hủy các thay đổi chưa commit. Nếu dùng transaction từng chunk, các chunk đã commit trước đó vẫn tồn tại.

### Bài 6. Batch đang phình bộ nhớ

Writer dùng PreparedStatement.addBatch() cho 900.000 hàng trước executeBatch(). Vì sao đây không phải cách dùng batch có memory bound?

**Gợi ý:** Driver có thể giữ gần 900.000 bộ tham số. Execute/clear batch theo ngưỡng số hàng/byte và commit theo chính sách job.

### Bài 7. Checkpoint trước commit

Job lưu “đã xử lý đến ID 50.000” vào nơi khác trước khi transaction ghi ID 49.501..50.000 commit. Database rollback. Khi job tiếp tục từ 50.001 sẽ có gì xảy ra?

**Gợi ý:** Bỏ sót phần dữ liệu rollback. Lưu checkpoint cùng transaction với tác động hoặc xử lý lại chunk an toàn nhờ unique business key/idempotency.

### Bài 8. Consumer chậm

Reader tạo 20.000 object/s, writer chỉ lưu 5.000 object/s, queue không có giới hạn. Điều gì xảy ra sau thời gian dài?

**Gợi ý:** Hàng đợi tăng liên tục và có nguy cơ OOM. Cần bounded queue/backpressure, điều tiết concurrency và giám sát queue depth.

### Bài 9. Cursor dài

Một export dùng cursor PostgreSQL và giữ transaction mở 90 phút vì client tải chậm. Dù heap không tăng, vì sao hệ thống vẫn có vấn đề?

**Gợi ý:** Giữ connection, snapshot/MVCC resources, ảnh hưởng vacuum và pool; client ngắt có thể để lại tài nguyên. Chuyển thành job bất đồng bộ, keyset/chunk hoặc lưu file có vòng đời quản lý khi phù hợp.

### Bài 10. Một hàng cực lớn

Chương trình import batch 200 hàng nhưng mỗi hàng có thể chứa 15 MB JSON. Số hàng/chunk đã đủ bảo vệ heap chưa?

**Gợi ý:** **Chưa**. Cần giới hạn tổng byte, xem có cần stream/COPY/staging hoặc chuyển lưu trữ nội dung lớn, và kiểm soát bộ đệm từng tầng.

### Bài 11. Retry sau commit timeout

Client gửi batch import, COMMIT đã có thể thành công nhưng kết nối bị cắt trước phản hồi. Có nên tạo job_id mới rồi chạy lại batch không?

**Gợi ý:** Không mặc định. Giữ job/source identifiers ổn định, đối soát trạng thái trên DB và sử dụng unique key để ngăn trùng.

### Bài 12. Đo đúng

Sau đổi sang keyset, heap Java giảm nhưng PostgreSQL tăng temp_bytes, thời gian query vẫn cao. Nên làm gì tiếp?

**Gợi ý:** Xem EXPLAIN/BUFFERS, kế hoạch sort/hash, điều kiện WHERE/ORDER BY/index, thống kê và các truy vấn đồng thời; streaming chỉ xử lý một phần bài toán hiệu năng.

## 26. Checklist trước khi xử lý tập dữ liệu lớn

1. **Kích thước:** có bao nhiêu hàng, độ lớn trung bình/p99/max mỗi hàng, số job/request đồng thời?
2. **Dòng đọc:** JDBC driver có buffer toàn kết quả không; fetchSize và transaction scope đã kiểm chứng chưa?
3. **Phân trang:** có khóa tăng/thứ tự toàn phần, index và checkpoint an toàn không; tập dữ liệu thay đổi trong lúc quét thế nào?
4. **Projection:** SELECT có lấy đúng cột cần thiết, tránh LOB/N+1 và chuyển đổi dư thừa không?
5. **Dòng ghi:** batch và chunk được giới hạn theo cả số hàng lẫn byte, có execute/clear đúng lúc không?
6. **ORM:** entity managed có được flush/clear, có giữ trong List/cache, batch SQL thực có được gom không?
7. **Pipeline:** mọi queue/buffer đều bounded, có backpressure và cancellation khi downstream chậm không?
8. **Giao dịch:** mỗi chunk commit ở đâu, job có yêu cầu atomicity toàn bộ hay chỉ từng chunk?
9. **Idempotency:** retry/commit không rõ kết quả có tạo bản ghi hoặc tác động nghiệp vụ lặp không?
10. **Tài nguyên:** ResultSet, PreparedStatement, Connection, stream và file tạm được đóng/giải phóng đúng vòng đời không?
11. **Database:** query plan, WAL, index, lock wait, temp files, vacuum và replica lag có nằm trong ngân sách không?
12. **Pool:** số export/import workers có làm cạn connection dành cho API không?
13. **Quan sát:** heap sau GC, allocation rate, RSS, queue depth, rows/sec, retry và checkpoint lag có dashboard không?
14. **Kiểm thử:** đã thử payload lớn bất thường, DB chậm, consumer bị nghẽn, crash giữa batch và nhiều job đồng thời chưa?
15. **Bảo mật:** dữ liệu xuất tạm, heap dump, log và đường tải có chính sách quyền, mã hóa và thời hạn lưu không?

## 27. Tổng kết

**Kiểm soát bộ nhớ với tập dữ liệu lớn** là việc đặt giới hạn rõ ràng cho **bao nhiêu hàng và bao nhiêu byte được giữ ở mỗi tầng**, không chỉ tăng heap của JVM. Khi đọc, sử dụng **PostgreSQL JDBC cursor/fetch size** hoặc **keyset pagination**, đọc đúng cột cần và tiêu thụ kết quả mà không tích lũy mọi object. Khi ghi, dùng **bounded batch/COPY**, quản lý **JPA persistence context** bằng flush/clear đúng thứ tự và đặt transaction boundary theo chunk phù hợp.

Để giải pháp thực sự an toàn, phải xét thêm **backpressure, thời gian giữ connection, MVCC, WAL, idempotency, checkpoint và rollback sau lỗi**. Cuối cùng, hãy đo bằng dữ liệu thực: **heap/GC của Java, queue, connection pool, query plan và tài nguyên DB**. Một pipeline tốt không chỉ tránh OutOfMemoryError mà còn xử lý đúng dữ liệu, tiếp tục được sau sự cố và không làm các dịch vụ khác cạn tài nguyên.
