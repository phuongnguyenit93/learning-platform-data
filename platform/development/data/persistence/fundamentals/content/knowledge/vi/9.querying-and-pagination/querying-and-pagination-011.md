# Đọc theo luồng và vòng đời tài nguyên truy vấn

Khi một ứng dụng Java phải đọc hàng trăm nghìn hoặc hàng triệu bản ghi để xuất CSV, lập báo cáo hay xử lý dữ liệu theo lô, cách `SELECT` rồi đưa toàn bộ kết quả vào một `List` có thể làm bộ nhớ tăng mạnh, kích hoạt nhiều lần thu gom rác và gây `OutOfMemoryError`. **Đọc theo luồng (streaming read)** giải quyết một phần vấn đề bằng cách tiêu thụ dần từng hàng hoặc từng nhóm hàng, thay vì giữ tất cả trong RAM.

Nhưng streaming không chỉ là một vòng lặp `ResultSet.next()`. Kết quả truy vấn còn phụ thuộc vào `Connection`, `PreparedStatement`, `ResultSet`, JDBC driver, transaction/snapshot, khả năng tiếp nhận của consumer và cách đóng tài nguyên. Nếu quản lý sai, chương trình có thể tiết kiệm bộ nhớ nhưng giữ kết nối hàng chục phút, làm cạn connection pool hoặc để lại giao dịch không kết thúc.

Bài học thuộc chương **Truy vấn và phân trang** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Các kỹ thuật sau liên hệ với thiết kế truy vấn/chỉ mục, giao dịch, cô lập và kiểm soát đồng thời, ranh giới persistence trong Java, xử lý lỗi kết nối, bảo mật, sao lưu và tối ưu hiệu năng.

## 1. Mục tiêu của streaming read

Giả sử hệ thống phải xuất **2 triệu đơn hàng**. Nếu mỗi đối tượng Java sau khi ánh xạ chiếm trung bình 1 KiB, riêng dữ liệu giữ trong `List` có thể tốn xấp xỉ:

`2.000.000 × 1 KiB ≈ 1,91 GiB`

Chưa kể `ArrayList`, driver buffer, chuỗi, đối tượng trung gian và phần đệm của định dạng xuất.

~~~java
// Cách dễ làm nhưng có nguy cơ giữ toàn bộ dữ liệu trong RAM:
List<Order> all = repository.findAllForTenant(tenantId);
for (Order order : all) {
    csvWriter.write(order);
}
~~~

Một pipeline đọc dần có dạng:

~~~mermaid
flowchart LR
    A[("Database")] --> B["JDBC fetch / cursor"]
    B --> C["ResultSet.next()"]
    C --> D["Ánh xạ hàng"]
    D --> E["Ghi output theo lô nhỏ"]
    E --> F["File / object storage / HTTP"]
    G["Connection + statement + transaction"] -.-> B
    H["Backpressure / timeout / cancellation"] -.-> E
~~~

Mục tiêu là bộ nhớ tiêu thụ tại tầng xử lý **không tăng tuyến tính với tổng số hàng**. Mục tiêu đó chưa đủ để kết luận toàn hệ thống tốn ít tài nguyên: database vẫn có thể phải sort, join hoặc materialize dữ liệu, driver có thể buffer và consumer có thể tích lũy dữ liệu ở nơi khác.

## 2. Streaming không đồng nghĩa phân trang hay xử lý bất đồng bộ

| Kỹ thuật | Cách hoạt động | Đặc điểm |
| --- | --- | --- |
| **Streaming read** | Tiêu thụ hàng khi nguồn truy vấn còn mở | Thường giữ tài nguyên JDBC suốt thời gian tiêu thụ |
| **Pagination** | Mỗi request lấy một trang có giới hạn | Có thể mở transaction ngắn cho từng trang |
| **Batch processing** | Xử lý các nhóm hàng theo kích thước xác định | Nguồn có thể là streaming hoặc phân trang |
| **Asynchronous/reactive** | Điều phối không đồng bộ và yêu cầu dữ liệu theo nhu cầu | Không tự làm JDBC truyền thống thành I/O không chặn |

Ví dụ:

~~~sql
-- Một trang có tối đa 100 hàng:
SELECT id FROM orders ORDER BY id LIMIT 100 OFFSET 500;

-- Một truy vấn có khả năng trả hàng triệu kết quả:
SELECT id FROM orders ORDER BY id;
~~~

Ở ví dụ thứ hai, chương trình có thể gọi `ResultSet.next()` để tiêu thụ dần. Cách driver thực sự vận chuyển kết quả từ database còn phụ thuộc cấu hình và phiên bản driver.

Nếu người dùng bấm các trang trong vài phút, giữ một cursor/transaction mở xuyên các HTTP request thường không phải lựa chọn tốt. Còn một job export được kiểm soát thời lượng có thể phù hợp với streaming liên tục.

## 3. Vì sao ResultSet.next() chưa chắc tiết kiệm bộ nhớ?

Giao diện JDBC cho phép duyệt từng hàng:

~~~java
try (ResultSet rows = statement.executeQuery()) {
    while (rows.next()) {
        process(rows);
    }
}
~~~

Nhưng JDBC API không hứa mọi driver chỉ tải một số ít hàng từ server. Một driver có thể buffer toàn bộ kết quả trước khi ứng dụng bắt đầu gọi `next()`. Một driver khác có thể dùng **server-side cursor** hoặc fetch theo lô nếu cấu hình phù hợp.

Phân biệt ba lớp:

1. **Tiêu thụ tăng dần ở Java:** không tạo `List` khổng lồ.
2. **Nhận tăng dần từ driver/database:** driver chỉ đưa các nhóm hàng về khi cần.
3. **Thực thi tăng dần ở database:** query plan có thể trả hàng đầu mà không phải xây dựng toàn bộ kết quả trước.

Một câu `ORDER BY` không có index phù hợp có thể cần sort lớn trước khi trả hàng đầu. `GROUP BY` hoặc hash join cũng có thể dùng nhiều bộ nhớ/tệp tạm. Vì vậy, cần đo cả **time to first row**, **thời gian đọc hết**, **query plan**, **heap**, **bộ nhớ DB** và **chi phí I/O**.

## 4. Vòng đời của Connection, Statement và ResultSet

Thứ tự phụ thuộc tài nguyên:

~~~mermaid
flowchart TD
    P["DataSource / connection pool"] --> C["Connection"]
    C --> S["PreparedStatement"]
    S --> R["ResultSet"]
    R --> U["Row consumer"]
    R -.->|"close"| S
    S -.->|"close"| C
    C -.->|"close / return to pool"| P
~~~

Thông thường:

1. Lấy `Connection` từ `DataSource`.
2. Thiết lập transaction, read-only/isolation theo yêu cầu.
3. Tạo và cấu hình `PreparedStatement`, bind tham số.
4. Gọi `executeQuery()` và tiêu thụ `ResultSet` khi statement/connection còn mở.
5. Đóng `ResultSet` rồi statement.
6. Kết thúc transaction khi có quản lý transaction tường minh.
7. Đóng connection, thường là trả về pool.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, tenantId);

    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            process(rows);
        }
    }
} // Tự đóng resources kể cả khi ném exception.
~~~

Trong `try-with-resources`, các tài nguyên được đóng theo thứ tự ngược với lúc được khai báo. Trường hợp transaction có `autoCommit=false` phải kết thúc bằng `commit()` hoặc `rollback()` trước khi trả connection, theo hợp đồng của pool/framework. Không dựa vào việc đóng kết nối là một cơ chế commit.

### Sai lầm: trả ResultSet ra khỏi scope

~~~java
ResultSet find(long tenantId) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
             "SELECT id FROM orders WHERE tenant_id = ?")) {

        statement.setLong(1, tenantId);
        return statement.executeQuery(); // Sai vòng đời.
    }
}
~~~

Khi hàm trả kết quả, `statement` và `connection` đã đóng. `ResultSet` còn lại không được phép xem như một nguồn đọc hợp lệ. Quy tắc tương tự áp dụng với `Stream<Entity>` hoặc `InputStream` được tạo từ kết quả truy vấn: **consumer phải chạy khi tài nguyên nguồn còn sống**, hoặc dữ liệu phải được copy sang cấu trúc độc lập trước khi đóng.

## 5. Fetch size là gì?

`setFetchSize(n)` là một gợi ý dành cho JDBC driver về số hàng muốn lấy trong một lần fetch. Nó **không phải** mệnh đề giới hạn tổng số hàng.

~~~java
PreparedStatement statement = connection.prepareStatement(
    "SELECT id, total_amount FROM orders WHERE tenant_id = ?",
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
statement.setFetchSize(500);
~~~

| Thuộc tính | Mục đích |
| --- | --- |
| `setFetchSize(500)` | Driver có thể lấy khoảng 500 hàng mỗi lần từ server |
| `LIMIT 500` | SQL chỉ trả tối đa 500 hàng trong kết quả |
| `setMaxRows(500)` | Giới hạn số hàng JDBC được phép cung cấp theo hỗ trợ driver |
| `OFFSET / keyset` | Xác định trang hoặc vị trí tiếp tục trong tập kết quả |
| `setQueryTimeout(60)` | Đặt timeout của statement theo semantics driver, không phải toàn bộ thời gian export |

Với PostgreSQL JDBC, cấu hình cursor thường yêu cầu:

- `ResultSet.TYPE_FORWARD_ONLY`.
- `fetchSize` dương.
- `autoCommit=false` để cursor tồn tại trong transaction.
- Câu SQL và cấu hình driver tương thích với cursor-based fetching.

~~~java
connection.setAutoCommit(false);
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT id FROM orders WHERE tenant_id = ? ORDER BY id",
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    statement.setLong(1, tenantId);
    statement.setFetchSize(500);

    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            // Xử lý hàng hiện tại.
        }
    }
}
connection.commit();
~~~

Đây là ví dụ theo **PostgreSQL JDBC**, không phải cấu hình có thể sao chép nguyên cho mọi driver. MySQL, Oracle, SQL Server và các driver/phiên bản khác có hành vi cursor/buffering khác nhau. Cần kiểm tra bằng tài liệu driver và phép đo thực tế.

**Fetch size không bảo đảm mức sử dụng bộ nhớ chính xác.** Driver còn có buffer, metadata và đối tượng ánh xạ. Nếu một hàng chứa BLOB nhiều megabyte thì 500 hàng có thể là lô rất lớn.

## 6. Ví dụ schema và truy vấn phục vụ export

Để minh họa, sử dụng PostgreSQL với một tập dữ liệu đơn hàng:

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(19, 2) NOT NULL CHECK (total_amount >= 0)
);

CREATE INDEX idx_orders_tenant_id ON orders (tenant_id, id);
~~~

Truy vấn:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY id;
~~~

`:tenant_id` là tham số minh họa; với JDBC thuần dùng dấu `?` và `PreparedStatement`. Lọc ở database giúp giảm lượng dữ liệu chuyển về và bảo vệ phạm vi tenant. Kiểm tra quyền tenant vẫn phải thực hiện theo thông tin xác thực, không tin một tham số HTTP tùy ý.

Chỉ chọn các cột cần thiết, tránh `SELECT *` nếu bảng có cột lớn hoặc nhiều trường nhạy cảm. Index `(tenant_id, id)` là ứng viên hỗ trợ lọc tenant và duyệt theo ID; hiệu quả còn phụ thuộc kích thước dữ liệu, độ chọn lọc và kế hoạch thực thi.

`ORDER BY id` tạo thứ tự xác định nhưng **không mặc nhiên là thứ tự thời gian nghiệp vụ**. Muốn xuất theo thời gian cần thứ tự `created_at, id` và index tương ứng.

## 7. Java 17+: xuất CSV theo từng hàng, quản lý tài nguyên đúng scope

Ví dụ sau dùng JDBC và một `Writer` do tầng gọi sở hữu. Nó không tạo `List` tất cả các đơn:

~~~java
import java.io.IOException;
import java.io.Writer;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import javax.sql.DataSource;

public final class OrderCsvExporter {
    private final DataSource dataSource;

    public OrderCsvExporter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long export(long tenantId, Writer output)
            throws SQLException, IOException {
        if (tenantId <= 0 || output == null) {
            throw new IllegalArgumentException("Đầu vào không hợp lệ");
        }

        String sql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE tenant_id = ?
            ORDER BY id
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setReadOnly(true);
            connection.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            connection.setAutoCommit(false);

            try {
                long count = 0;

                try (PreparedStatement statement =
                         connection.prepareStatement(
                             sql,
                             ResultSet.TYPE_FORWARD_ONLY,
                             ResultSet.CONCUR_READ_ONLY)) {
                    statement.setLong(1, tenantId);
                    statement.setFetchSize(500);
                    statement.setQueryTimeout(120);

                    output.write("order_id,created_at,total_amount\n");

                    try (ResultSet rows = statement.executeQuery()) {
                        while (rows.next()) {
                            long id = rows.getLong("id");
                            OffsetDateTime createdAt = rows.getObject(
                                "created_at", OffsetDateTime.class
                            );
                            BigDecimal total =
                                rows.getBigDecimal("total_amount");

                            output.write(Long.toString(id));
                            output.write(",");
                            output.write(createdAt.toString());
                            output.write(",");
                            output.write(total.toPlainString());
                            output.write("\n");
                            count++;
                        }
                    }
                }

                connection.commit();
                return count;
            } catch (SQLException | IOException | RuntimeException failure) {
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

Điều cần chú ý:

1. `ResultSet` được duyệt **trong khi statement và connection còn mở**; tài nguyên đóng khi kết thúc hoặc gặp lỗi.
2. `connection.commit()` kết thúc transaction đọc, giúp giải phóng snapshot/cursor theo semantics database.
3. Khi `IOException` hoặc `SQLException` xuất hiện, code cố rollback và đóng các tài nguyên.
4. `Writer` thuộc sở hữu của tầng gọi, vì thế hàm **không đóng Writer**. Tầng gọi phải flush/close và xử lý lỗi thích hợp.
5. Ví dụ dùng cột số/thời gian do database kiểm soát nên cách nối CSV đơn giản. Khi thêm trường văn bản do người dùng nhập, cần escaping CSV chuẩn và xử lý **CSV formula injection** trong các ứng dụng bảng tính.
6. `setQueryTimeout(120)` áp dụng theo cơ chế statement/driver; không phải thời gian tối đa đảm bảo của toàn bộ thao tác ghi file.
7. Transaction `REPEATABLE READ` được dùng để minh họa snapshot ổn định; với **một câu SELECT** ở PostgreSQL, `READ COMMITTED` cũng cung cấp snapshot ở mức statement. Một transaction đọc dài vẫn có chi phí dù chỉ đọc.
8. Nếu Writer đã ghi được 10.000 dòng rồi lỗi, rollback database **không thu hồi được byte đã ghi ra file hoặc gửi qua HTTP**. Cần quản lý tính hoàn chỉnh của output riêng.

Đây là ví dụ giáo dục; chưa có quota số dòng, timeout toàn job, job status, metric, retry, xử lý cancel hoặc cơ chế xuất file hoàn chỉnh. Trong ứng dụng thật, chúng là những yêu cầu thiết kế độc lập.

## 8. Đọc BLOB dưới dạng InputStream cũng cần scope

Một kết quả truy vấn có thể cung cấp luồng nhị phân:

~~~java
InputStream open(long id) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
             "SELECT content FROM documents WHERE id = ?")) {
        statement.setLong(1, id);

        try (ResultSet rows = statement.executeQuery()) {
            if (!rows.next()) {
                return InputStream.nullInputStream();
            }
            return rows.getBinaryStream("content"); // Sai vòng đời.
        }
    }
}
~~~

Khi hàm trả về, `ResultSet`, statement và connection đã đóng. Luồng nhị phân có thể không còn hợp lệ.

Giải pháp là **copy byte khi cả nguồn và đích còn mở**:

~~~java
try (ResultSet rows = statement.executeQuery()) {
    if (rows.next()) {
        try (InputStream input = rows.getBinaryStream("content")) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (n > 0) {
                    output.write(buffer, 0, n);
                }
            }
        }
    }
}
~~~

`statement`, `connection` và `output` trong đoạn rút gọn được quản lý ở tầng bao ngoài. `getBinaryStream()` cũng không tự đảm bảo driver sẽ stream trực tiếp, không buffer toàn bộ BLOB; phải kiểm tra driver và kích thước thật.

## 9. Chọn fetch size theo kích thước hàng và round trip

Một ước lượng sơ bộ:

`bytes_in_batch ≈ fetch_size × average_row_bytes`

Nếu mỗi hàng trung bình có 2 KiB dữ liệu truyền về:

| Fetch size | Dữ liệu một lô (ước tính) |
| ---: | ---: |
| 50 | 100 KiB |
| 500 | 1.000 KiB ≈ 0,98 MiB |
| 5.000 | 10.000 KiB ≈ 9,77 MiB |

Đây là dung lượng **payload tương đối**, chưa tính buffer driver, metadata, object Java và các công đoạn phía sau.

- Fetch size quá nhỏ có thể tăng số lượt fetch/round trip.
- Fetch size quá lớn có thể tăng đỉnh bộ nhớ và áp lực network.
- Truy vấn có hàng rộng, JSON/BLOB lớn hoặc nhiều cột cần lô nhỏ hơn.
- Kích thước tối ưu phụ thuộc độ trễ mạng, loại truy vấn và cách driver triển khai.

Nên đo nhiều giá trị trên dữ liệu tương đương sản xuất, theo dõi **time to first row, tổng thời gian, throughput, heap/GC, DB CPU/I/O, connection duration và tỷ lệ lỗi**. Không lấy một con số mặc định làm quy tắc cho toàn bộ module Java.

## 10. Transaction dài ảnh hưởng database thế nào?

Với PostgreSQL và MVCC, transaction đọc lâu có thể giữ một snapshot cũ và làm chậm quá trình dọn những phiên bản dữ liệu không còn cần thiết. Trong khi đó, connection của job export cũng không thể phục vụ request khác nếu đang được giữ bởi cursor.

Các tác động có thể thấy:

- Connection pool hết chỗ khi nhiều export chạy cùng lúc.
- Session nằm ở trạng thái `idle in transaction` nếu consumer tạm dừng và query không tiến triển.
- Vacuum bị hạn chế khả năng dọn phiên bản cũ bởi snapshot sống lâu.
- Query hoặc các tác vụ quản trị/DDL có thể phải chờ tài nguyên tùy transaction và lock.
- Memory buffer, temp files, network và CPU bị chiếm bởi export lớn.
- Lỗi mạng tới client có thể xảy ra sau khi transaction giữ tài nguyên lâu.

**Read-only không có nghĩa là miễn phí.** Một transaction không sửa dữ liệu vẫn có thể gây áp lực lên tài nguyên và tính sẵn sàng của hệ thống.

### Có nên stream trực tiếp từ DB đến HTTP client?

Nếu client tải CSV rất chậm, vòng lặp vừa gọi `rows.next()` vừa ghi vào response có thể bị chặn bởi tốc độ mạng của client, kéo dài transaction và thời gian giữ connection.

Với export lớn, kiến trúc thường an toàn hơn là:

1. Tạo job export có quyền, quota và định danh riêng.
2. Worker đọc DB, ghi kết quả vào file tạm hoặc object staging.
3. Flush/close, kiểm tra số hàng/hash, cập nhật trạng thái `READY` khi đủ điều kiện.
4. Đóng tài nguyên DB **trước khi client tải xuống**.
5. Client tải file hoàn chỉnh qua endpoint riêng hoặc URL có thời hạn.
6. Dọn file hết hạn và file lỗi theo chính sách.

Đổi lại, cần quản lý nơi lưu file, backup/retention, quyền truy cập, trạng thái job và phục hồi lỗi.

## 11. Phân trang ngắn/keyset thay cho một cursor sống lâu

Một lựa chọn khác là xử lý các lô có giới hạn bằng **keyset pagination**:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND id > :last_id
ORDER BY id
LIMIT 1000;
~~~

Sau mỗi lô:

1. Xử lý thành công dữ liệu lô.
2. Lưu checkpoint của hàng cuối **đã xử lý thành công**.
3. Kết thúc transaction/connection của lô.
4. Tiếp tục bằng checkpoint trong transaction mới.

~~~mermaid
flowchart LR
    A["Đọc checkpoint"] --> B["SELECT ... id > last_id LIMIT N"]
    B --> C["Xử lý một lô"]
    C --> D["Lưu checkpoint sau khi xác nhận kết quả"]
    D --> E{"Còn hàng?"}
    E -->|"Có"| B
    E -->|"Không"| F["Kết thúc"]
~~~

**Ưu điểm:** transaction ngắn, dễ dừng hoặc tiếp tục, không cần giữ một cursor cho toàn bộ job.

**Giới hạn:** các lô có thể nhìn những snapshot khác nhau. ID có thể được cấp trước thời điểm commit; bản ghi có ID nhỏ hơn checkpoint có thể commit muộn và bị bỏ qua. Bản ghi cũ cũng có thể được cập nhật để đi vào/ra khỏi filter. Do đó, **keyset không mặc nhiên là point-in-time snapshot**.

Nếu báo cáo đòi hỏi dữ liệu nhất quán tại một thời điểm, hãy thiết kế snapshot transaction có giới hạn, materialized snapshot hoặc dữ liệu có version. Nếu mục tiêu là pipeline live, cần hợp đồng về late-arriving records, checkpoint và xử lý lặp.

## 12. Backpressure: consumer chậm có thể phá lợi ích streaming

Giả sử DB có thể trả 20.000 hàng/giây, nhưng hệ thống nhận chỉ xử lý 2.000 hàng/giây. Nếu producer liên tục đẩy dữ liệu vào một queue không giới hạn, heap vẫn tăng cho đến khi hết bộ nhớ.

Các cách thiết kế:

- **Tiêu thụ đồng bộ:** chỉ gọi `next()` tiếp khi hàng hiện tại đã xử lý xong; tiết kiệm bộ nhớ nhưng connection sống theo consumer.
- **Queue có giới hạn:** khi đầy thì producer dừng; phải có timeout/cancellation và lan truyền lỗi.
- **Batch có checkpoint:** kết thúc truy vấn sau từng lô, chuyển dữ liệu sang bước sau có giới hạn; cần kiểm soát idempotency.
- **Export sang file trung gian:** tách tốc độ DB khỏi tốc độ client, đổi lại phải quản lý file và trạng thái.

Không chia sẻ `ResultSet` giữa nhiều thread hoặc gọi `parallelStream()` trên một iterator JDBC rồi mặc định thread-safe. Nếu cần xử lý song song, hãy copy dữ liệu sang các đối tượng độc lập, dùng queue bounded và xác định khi nào kết quả được coi là hoàn tất.

### Reactive có bảo đảm nonblocking không?

Không. `Flux` hay `Publisher` chỉ là abstraction. Nếu tầng dưới vẫn dùng JDBC blocking hoặc đã buffer toàn bộ kết quả, API reactive không tự làm I/O nonblocking hay giảm bộ nhớ. Có thể đánh giá R2DBC hoặc driver bất đồng bộ khác khi yêu cầu thực sự cần, nhưng vẫn phải quản lý transaction, cancellation và backpressure.

## 13. Cancellation, timeout và thất bại giữa luồng

Một luồng truy vấn có thể dừng vì:

- HTTP client hủy tải.
- `Writer` ném `IOException`.
- Mạng tới database đứt.
- SQL query timeout.
- Job hết hạn, hết quota hoặc bị người dùng hủy.
- Worker bị tắt giữa quá trình xuất file.

Cần quản lý cả **tài nguyên truy vấn** lẫn **tính hoàn chỉnh của kết quả đầu ra**.

Các cơ chế nên xem xét:

| Cơ chế | Mục đích và giới hạn |
| --- | --- |
| `try-with-resources` | Đóng result set/statement/connection khi luồng code kết thúc; không tự giới hạn thời gian query |
| `Statement.setQueryTimeout` | Yêu cầu timeout cho statement tùy driver, không thay end-to-end deadline |
| `Statement.cancel()` | Đề nghị hủy statement đang chạy; semantics phụ thuộc driver/database |
| Deadline/job cancellation | Buộc workflow dừng đúng chính sách, đóng tài nguyên và cập nhật trạng thái |
| Queue bounded/backpressure | Tránh tích lũy vô hạn khi consumer chậm |
| File staging/atomic publish | Không công bố file dở dang như output hoàn chỉnh |

**Không tự đóng connection đang được một thread khác sử dụng** mà không có cơ chế điều phối phù hợp. Có thể cần cancellation API, interrupt được hỗ trợ và worker lifecycle rõ ràng.

Nếu đã ghi 100.000 dòng CSV rồi mất kết nối DB, transaction rollback không làm các byte CSV biến mất. Một luồng hoàn chỉnh phải:

1. Ghi output vào file/object staging.
2. Khi nguồn kết thúc, flush/close output và kiểm tra dữ liệu.
3. Chỉ sau đó publish file và đánh dấu job `READY`.
4. Khi thất bại, đánh dấu `FAILED`/`RETRYABLE` và dọn dữ liệu tạm theo chính sách.

## 14. ORM và framework có API Stream vẫn phải quản lý vòng đời

### JPA/Hibernate

Một số API cung cấp `Stream<Entity>` hoặc `ScrollableResults`. Nhưng cần lưu ý:

- Stream có thể giữ JDBC cursor và session mở.
- Persistence context có thể tích lũy nhiều entity managed, làm heap tăng dù driver fetch theo lô.
- Lazy loading trong vòng lặp có thể tạo N+1 queries.
- Bulk query/stream cần fetch size, read-only/projection và chính sách clear/detach phù hợp.
- Đóng stream/cursor trước khi transaction/session kết thúc.

Ví dụ cấu trúc service với stream trong một transaction được framework quản lý:

~~~java
@Transactional(readOnly = true)
public void export() {
    try (Stream<OrderProjection> stream = repository.streamForExport()) {
        stream.forEach(this::writeOneRow);
    }
}
~~~

Đây là ví dụ về **scope**, không phải đoạn mã đầy đủ để chạy độc lập: cần định nghĩa repository, projection, xử lý ngoại lệ từ writer và xem xét semantics proxy/interceptor của `@Transactional`.

### Spring JDBC

`JdbcTemplate` có `RowCallbackHandler` cho phép xử lý từng hàng:

~~~java
jdbcTemplate.query(
    "SELECT id, total_amount FROM orders WHERE tenant_id = ? ORDER BY id",
    rs -> {
        long id = rs.getLong("id");
        BigDecimal total = rs.getBigDecimal("total_amount");
        consume(id, total);
    },
    tenantId
);
~~~

Đoạn ngắn giả định `jdbcTemplate`, `consume` và `BigDecimal` đã có. Callback giữ việc xử lý trong phạm vi truy vấn, nhưng **không tự chứng minh driver đã bật server-side cursor**. Fetch size, transaction và buffering vẫn cần kiểm tra.

**Quy tắc chung:** bất kể dùng JDBC thuần, Spring hay JPA, luôn biết **ai sở hữu và đóng stream, transaction sống đến khi nào, và dữ liệu được tải từ DB theo cách nào**.

## 15. Tính nhất quán khi có ghi đồng thời

Khi stream đang đọc, giao dịch khác có thể thêm, sửa hoặc xóa dữ liệu. Các mức đảm bảo khác nhau:

- Trong PostgreSQL `READ COMMITTED`, một câu `SELECT` nhìn snapshot theo statement. Hai query khác nhau có thể đọc hai trạng thái khác nhau.
- PostgreSQL `REPEATABLE READ` cung cấp snapshot ổn định cho các query trong cùng transaction theo semantics của engine.
- Nếu job dùng keyset theo từng transaction ngắn, các lô có snapshot khác nhau.
- Nếu khóa checkpoint hoặc bộ lọc có thể thay đổi, kết quả có thể lặp hoặc bỏ sót.
- Read replica có thể trễ so với primary và không thấy các ghi vừa commit.

Có hai hợp đồng điển hình:

**Export theo thời điểm:** mọi hàng và giá trị phải phản ánh cùng một snapshot xác định. Có thể chọn snapshot transaction ngắn được kiểm soát hoặc materialize dữ liệu.

**Xử lý luồng live:** chấp nhận trạng thái thay đổi, dùng checkpoint, idempotency và đối soát, công bố rõ mức nhất quán. Không được gọi đây là snapshot chính xác nếu chưa có cơ chế bảo đảm.

Đặc biệt với dữ liệu tài chính, tồn kho hoặc kiểm toán, cần quy định rõ thời điểm của dữ liệu xuất, cách xử lý ghi đồng thời và độ hoàn chỉnh yêu cầu.

## 16. Bảo mật, quyền truy cập và kiểm soát tải

Export hàng triệu bản ghi có thể làm lộ lượng dữ liệu lớn nếu truy vấn hoặc API thiếu ràng buộc quyền.

Các kiểm soát nên có:

1. Xác thực người gọi và kiểm quyền export.
2. Xác định `tenant_id` từ ngữ cảnh tin cậy; lọc theo tenant/quyền **ngay trong SQL**.
3. Chọn chỉ các cột cần thiết, tránh kéo dữ liệu nhạy cảm không sử dụng.
4. Dùng bind parameters để chống SQL injection.
5. Giới hạn kích thước, thời lượng, số job đồng thời, số bản ghi và dung lượng output theo chính sách.
6. Đặt timeout và cancellation thích hợp, tránh một người dùng giữ hết connection pool.
7. Quản lý file tạm, URL tải xuống có thời hạn, cleanup và audit.
8. Nếu xuất CSV có trường do người dùng nhập, dùng escaping đúng chuẩn và xử lý nguy cơ CSV formula injection.
9. Không ghi tên file nhạy cảm, token, nội dung export hoặc dữ liệu cá nhân vào nhãn metric/log công khai.

Streaming tiết kiệm RAM không đồng nghĩa có thể bỏ qua quota, phân quyền và giới hạn kết nối.

## 17. Giám sát để biết tài nguyên được giải phóng thật

| Nhóm metrics | Tín hiệu |
| --- | --- |
| Query | Time to first row, tổng thời gian, hàng/giây, rows scanned/returned |
| Driver | Fetch size thực tế, fetch errors, query timeout, cancel |
| Connection pool | Active/idle/pending, wait time, timeouts |
| Transaction | Transaction duration, snapshot age, idle in transaction |
| Memory | Heap, GC, buffered rows, queue depth |
| Database | CPU, I/O, sort spill, temp files, vacuum lag |
| Output | Bytes written, consumer throughput, client disconnect |
| Job | READY/FAILED, tổng dòng hoàn tất, checksum và cleanup |

Những dấu hiệu cần điều tra:

- Active connections không giảm sau khi export hoàn tất.
- Có nhiều session `idle in transaction`.
- Heap tăng theo số hàng đã quét dù không giữ `List`.
- Job đã hủy nhưng SQL vẫn thực thi.
- File staging không được dọn sau lỗi.
- ORM persistence context giữ hàng trăm nghìn managed entity.
- p99 của API thông thường xấu đi khi job export chạy.

Khi tối ưu, đo hiệu quả đối với **cả workload khác dùng chung database**, không chỉ tốc độ của job export.

## 18. Quy trình kiểm thử và tự kiểm tra

### Kiểm thử thực hành

**Kịch bản A — memory bounded.** So sánh `findAll()` và JDBC streaming khi dữ liệu tăng từ 100.000 lên 1.000.000 hàng. Ghi nhận đỉnh heap, GC, thời gian, số kết nối đang dùng.

**Kịch bản B — fetch size.** Thử các giá trị 0, 100, 500, 5.000 với driver đang dùng. Đo time to first row, tổng thời gian và mức buffer. Xác minh liệu driver có server-side cursor hay không.

**Kịch bản C — consumer chậm.** Giả lập nơi nhận chỉ ghi được lượng nhỏ mỗi giây. Kiểm tra transaction duration, pool wait, queue size và cancellation.

**Kịch bản D — lỗi giữa luồng.** Làm Writer ném `IOException` sau 10.000 hàng; kiểm tra connection trả về pool, transaction kết thúc, file không được công bố.

**Kịch bản E — ghi đồng thời.** Trong lúc một export đang chạy, cho transaction khác thêm/sửa/xóa. So sánh một snapshot transaction với job keyset nhiều transaction.

**Kịch bản F — tải hỗn hợp.** Cho vài export cùng chạy với API tạo đơn. Đo p95/p99 của cả hai, hạn mức connection và mức tài nguyên DB.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao duyệt một `List` hai triệu đối tượng từng cái một không phải streaming từ DB?

**Đáp án:** Vì dữ liệu đã được tập hợp và giữ trong RAM trước khi vòng lặp bắt đầu. Muốn tiết kiệm bộ nhớ, cần giảm buffering từ JDBC/ORM và xử lý trong scope của truy vấn hoặc đọc các lô có giới hạn.

**Câu 2.** `setFetchSize(500)` có nghĩa query chỉ trả 500 hàng không?

**Đáp án:** Không. Đây là hint về kích thước mỗi lần driver fetch, không thay thế `LIMIT`.

**Câu 3.** Tại sao không thể trả `ResultSet` sau khi đóng `Connection`?

**Đáp án:** ResultSet thường phụ thuộc connection/statement nguồn để tiếp tục lấy dữ liệu. Khi nguồn đóng, nó không còn hợp lệ để đọc.

**Câu 4.** Một export đang ghi ra HTTP client rất chậm. Rủi ro đối với database là gì?

**Đáp án:** Connection, cursor và transaction có thể bị giữ theo tốc độ client, gây cạn pool và áp lực MVCC. Có thể tách job tạo file khỏi việc client tải file.

**Câu 5.** Vì sao keyset theo `id > last_id` trong transaction riêng không bảo đảm một snapshot theo thời điểm?

**Đáp án:** Mỗi trang có thể thấy trạng thái khác; dữ liệu có thể commit muộn hoặc được cập nhật/xóa. Muốn point-in-time consistency phải có cơ chế snapshot/versioned data.

**Câu 6.** Khi Writer lỗi sau 100.000 dòng, database rollback có xóa CSV đã ghi không?

**Đáp án:** Không. Cần quản lý file staging/HTTP response và trạng thái job riêng. Transaction database không bao trùm tác dụng phụ ở nơi nhận.

### Bài tập mở rộng

- Viết export CSV JDBC dùng `setFetchSize` và `try-with-resources`, tự đưa vào lỗi Writer để thử cơ chế cleanup.
- Thiết kế job keyset 1.000 hàng/lô có checkpoint, giới hạn số request đồng thời và idempotent consumer.
- So sánh export theo snapshot với export live; viết hợp đồng dữ liệu rõ cho từng loại.
- Kiểm thử một ORM stream lớn và quan sát số entity managed, N+1 query, heap và thời gian giữ transaction.
- Thiết kế API export theo tenant có audit, quota, file TTL và kiểm soát truy cập.

**Kết luận:** Đọc theo luồng không chỉ là “đọc từng hàng”. Thiết kế đúng phải thống nhất **đường truy vấn và chỉ mục, driver fetch, vòng đời ResultSet/Statement/Connection, transaction/snapshot, tốc độ consumer, backpressure, cancellation và tính hoàn chỉnh của output**. Streaming chỉ thực sự hữu ích khi tiết kiệm bộ nhớ mà không làm suy giảm tính đúng đắn, bảo mật và khả năng phục vụ những truy vấn khác của hệ thống.
