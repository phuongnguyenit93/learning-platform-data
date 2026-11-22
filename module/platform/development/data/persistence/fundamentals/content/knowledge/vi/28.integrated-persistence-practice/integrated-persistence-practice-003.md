# Lưu và đọc cùng dữ liệu qua tệp và cơ sở dữ liệu để đối chiếu

Một bản ghi đơn hàng có thể được lưu trong tệp trên ổ đĩa hoặc trong một bảng quan hệ. Cả hai cách đều có thể cho phép **ghi dữ liệu, đóng ứng dụng rồi đọc lại**. Tuy nhiên, khả năng lưu được một vài giá trị không có nghĩa hai cách cung cấp cùng bảo đảm về transaction, truy vấn, đồng thời, tính toàn vẹn và phục hồi sau lỗi.

Trong chương **Thực hành tổng hợp** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài này xây một bài thực hành có thể kiểm chứng: **tạo một tập dữ liệu chuẩn, lưu tập đó vào tệp UTF-8 và PostgreSQL, đọc dữ liệu từ hai nơi, chuẩn hóa và so sánh từng trường**, rồi thử các tình huống dữ liệu thay đổi, tệp hỏng, giao dịch rollback và cập nhật đồng thời. Bài thực hành gắn các quyết định persistence trong Java với mô hình dữ liệu, schema, SQL, ranh giới transaction, độ bền và kiểm thử.

**Mục tiêu:** sau bài học, người học không chỉ thấy hai phương thức “đọc ra giống nhau”, mà còn giải thích được **vì sao giống, khi nào lệch, cách phát hiện lệch, và những bảo đảm mà phép đối chiếu chưa chứng minh**.

## 1. Xác định cùng một dữ liệu và tiêu chí đúng

Giả sử một ứng dụng quản lý đơn hàng cần lưu các trường:

| Trường | Kiểu logic | Ví dụ | Quy tắc |
| --- | --- | --- | --- |
| `orderId` | Số nguyên 64-bit | `101` | Khóa định danh duy nhất, lớn hơn 0 |
| `customerId` | Số nguyên 64-bit | `501` | Lớn hơn 0 |
| `status` | Trạng thái | `PENDING`, `PAID`, `CANCELLED` | Chỉ nằm trong tập giá trị hợp lệ |
| `totalAmount` | Số thập phân | `125.50` | Không âm, đúng hai chữ số thập phân |
| `createdAt` | Thời điểm UTC | `2026-11-01T09:30:00Z` | Độ chính xác đến microsecond cho ví dụ PostgreSQL |
| `version` | Số nguyên 64-bit | `0`, `1` | Không âm, tăng khi thay đổi trạng thái nếu dùng optimistic locking |

Ba bản ghi mẫu là:

```text
orderId customerId status     totalAmount createdAt               version
101     501       PENDING    125.50      2026-11-01T09:30:00Z      0
102     502       PAID        42.00      2026-11-01T09:31:00Z      1
103     501       CANCELLED    0.00      2026-11-01T09:32:00Z      2
```

Ta gọi đây là **tập dữ liệu chuẩn** (*canonical fixture*). Trong lúc thử nghiệm, nó được đưa vào hai kho lưu trữ độc lập; không suy dữ liệu chuẩn từ một kho rồi mặc nhiên coi kho ấy luôn đúng. Đối chiếu cần trả lời:

1. Hai nơi có cùng **tập khóa `orderId`** không, kể cả bản ghi thiếu hoặc thừa?
2. Với mỗi khóa chung, **từng trường** có cùng ý nghĩa không?
3. Định dạng số tiền, múi giờ và thứ tự bản ghi có tạo ra khác biệt bề ngoài không?
4. Nếu một nơi ghi thất bại, có bị coi nhầm là một lần đồng bộ thành công không?
5. Khi nhiều request Java cùng thay đổi dữ liệu, nơi nào bảo vệ transaction và version?

**Không chỉ so số hàng:** hai nguồn đều có ba hàng nhưng một nguồn có IDs `101,102,103` còn nguồn kia có `101,102,999` vẫn lệch. **Không chỉ so chuỗi JSON/TSV nguyên văn:** thứ tự hàng, cách viết số thập phân hoặc biểu diễn thời gian có thể khác dù dữ liệu nghiệp vụ tương đương.

## 2. Kiến trúc bài thực hành và ranh giới của hai nơi lưu

```text
                     Canonical List<PracticeOrder>
                                   |
                    +--------------+---------------+
                    |                              |
                    v                              v
          FileSnapshotStore                JdbcOrderRepository
          ghi snapshot UTF-8               INSERT/UPDATE transaction
                    |                              |
                    v                              v
            orders.snapshot                 PostgreSQL
         (tệp trên file system)           practice_orders
                    |                              |
                    v                              v
             readSnapshot()                    readAll()
                    |                              |
                    +---------------+--------------+
                                    |
                                    v
                              OrderComparator
                              theo orderId/field
                                    |
                                    v
                        PASS hoặc báo thiếu/thừa/lệch
```

Tệp và database **không nằm trong cùng một transaction**. Bài thực hành cố tình ghi hai nơi để **quan sát và đối chiếu**. Trong ứng dụng production, nếu cần một nghiệp vụ được commit nguyên tử, không thể chỉ gọi lần lượt `writeFile()` rồi `commitDatabase()` và mong cả hai cùng thành công hoặc cùng rollback.

### Chọn hình thức tệp phù hợp mục tiêu học

Ta dùng **một tệp snapshot dạng văn bản UTF-8**, gồm phần đầu định danh phiên bản, số bản ghi và sáu trường cách nhau bằng ký tự tab. Định dạng này **chỉ dùng cho bộ dữ liệu có trường được kiểm soát**: số, trạng thái thuộc enum và timestamp chuẩn ISO; không có chuỗi người dùng chứa tab hoặc xuống dòng.

Nếu cần lưu tên khách hàng, ghi chú tự do, ảnh hoặc payload JSON bất kỳ, phải dùng **serialization có escaping và schema/version đúng** (chẳng hạn thư viện JSON/CSV đã kiểm thử) hoặc thiết kế format nhị phân có length-prefix. Không mở rộng ví dụ bằng cách ghép chuỗi tùy ý rồi coi đó là parser an toàn cho mọi dữ liệu.

```text
orders-snapshot-v1
count=3
101	501	PENDING	125.50	2026-11-01T09:30:00Z	0
102	502	PAID	42.00	2026-11-01T09:31:00Z	1
103	501	CANCELLED	0.00	2026-11-01T09:32:00Z	2
```

Các dòng dữ liệu được viết theo **thứ tự `orderId` tăng dần**, vì file system không cung cấp quan hệ thứ tự theo khóa cho các record. Định dạng v1 này là **snapshot đầy đủ**, không phải append-only log. Nếu muốn cập nhật liên tục bằng cách ghi nối cuối file, cần thiết kế event log, checksum, record framing và khả năng phục hồi khi bản ghi cuối bị ghi dở dang — đó là bài toán khác.

## 3. Chuẩn bị PostgreSQL và môi trường thực hành

Dùng **database test riêng** có thể tạo lại. Ví dụ SQL:

```sql
CREATE TABLE practice_orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(18, 2) NOT NULL
                 CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0
                 CHECK (version >= 0),
    CHECK (order_id > 0),
    CHECK (customer_id > 0)
);

CREATE INDEX practice_orders_customer_recent
ON practice_orders (customer_id, created_at DESC, order_id DESC);
```

Trong môi trường thực tế, schema thay đổi cần được quản lý bởi migration có version (Flyway, Liquibase hoặc quy trình tương ứng). Đoạn `CREATE TABLE` được trình bày để làm **lab có thể tạo lại**, không phải chỉ thị ứng dụng tự tạo bảng production lúc khởi động.

| Điều kiện | Yêu cầu |
| --- | --- |
| Java | Java 17+ để sử dụng `record` và text block |
| JDBC | PostgreSQL JDBC driver tương thích môi trường |
| Connection pool (ví dụ) | HikariCP, dùng `DataSource` và đóng pool lúc kết thúc chương trình |
| Database | PostgreSQL trong container hoặc database lab độc lập |
| File system | Thư mục riêng để lưu `orders.snapshot`, đủ quyền và dung lượng |
| Cấu hình | JDBC URL, tên role và credential của **lab** cấp ngoài mã nguồn |
| An toàn | Không dùng bảng/tài khoản production, không đưa secret vào log hoặc commit |

Khi chạy ví dụ ngoài đời, cần xác định datasource chỉ kết nối tới lab. Đặc biệt vì phần ghi SQL dưới đây có một thao tác **xóa toàn bộ bảng chuyên dùng cho thực hành trong transaction**, không được trỏ nó tới một bảng nghiệp vụ có dữ liệu thật.

### Tính nhất quán kiểu dữ liệu giữa hai thế giới

PostgreSQL dùng `NUMERIC(18,2)` cho tiền, nên Java nên dùng `BigDecimal` thay vì `double`. Với thời gian, PostgreSQL `TIMESTAMPTZ` lưu một **thời điểm tuyệt đối** (không bảo tồn tên múi giờ gốc). JDBC có thể đọc nó thành `OffsetDateTime` rồi chuyển về `Instant`. Thực hành này giới hạn timestamp ở **độ chính xác microsecond** để tránh khác biệt khi nguồn Java dùng nanosecond mà PostgreSQL lưu độ chính xác thấp hơn.

Một phép so sánh đáng tin **không được tùy tiện cắt phần thập phân hoặc làm tròn thời gian để che lỗi**. Chọn chuẩn ngay từ đầu và từ chối dữ liệu không tuân thủ, hoặc ghi rõ chính sách chuẩn hóa được chấp nhận.

## 4. Mô hình Java chung với kiểm tra bất biến

Đặt các class minh họa dưới cùng một package tùy project; các đoạn code dưới đây bỏ dòng `package` để tập trung vào cơ chế persistence. File `PracticeOrder.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.Set;

public record PracticeOrder(
        long orderId,
        long customerId,
        String status,
        BigDecimal totalAmount,
        Instant createdAt,
        long version) {

    private static final Set<String> STATUSES =
            Set.of("PENDING", "PAID", "CANCELLED");

    public PracticeOrder {
        if (orderId <= 0 || customerId <= 0 || version < 0) {
            throw new IllegalArgumentException("ID/version không hợp lệ");
        }
        if (!STATUSES.contains(Objects.requireNonNull(status))) {
            throw new IllegalArgumentException("Trạng thái không hợp lệ");
        }
        totalAmount = Objects.requireNonNull(totalAmount)
                .setScale(2, RoundingMode.UNNECESSARY);
        if (totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Số tiền phải >= 0");
        }
        Objects.requireNonNull(createdAt);
        if (!createdAt.equals(
                createdAt.truncatedTo(ChronoUnit.MICROS))) {
            throw new IllegalArgumentException(
                    "Timestamp phải có độ chính xác microsecond");
        }
    }
}
```

Compact constructor của `record` chuẩn hóa `totalAmount` về **scale 2**, vì `new BigDecimal("42.0").equals(new BigDecimal("42.00"))` trả `false` (scale khác nhau) dù `compareTo()` bằng 0. Chính sách này phù hợp với `NUMERIC(18,2)` của lab nhưng không phải quy tắc chung cho tỷ giá, lượng đo hoặc tiền cần nhiều chữ số.

Record là immutable về các trường của nó và thuận tiện làm DTO đối chiếu. Nó không tự bảo vệ dữ liệu khi đối tượng khác giữ mutable reference; trong ví dụ, `BigDecimal` và `Instant` là immutable. Các kiểm tra trong Java **bổ sung**, không thay thế `CHECK`/`PRIMARY KEY` trong PostgreSQL.

## 5. Lưu snapshot ra tệp bằng Java NIO

Với một tệp chứa toàn bộ dữ liệu, không nên ghi trực tiếp từ đầu vào `orders.snapshot`: nếu JVM chết giữa chừng, tệp cũ có thể bị cắt cụt còn tệp mới chưa ghi đủ. Một mẫu an toàn hơn là:

1. Chuẩn bị nội dung snapshot trong bộ nhớ.
2. Ghi nội dung ra **tệp tạm cùng thư mục/volume** với tệp đích.
3. Yêu cầu đồng bộ dữ liệu và metadata cần thiết của tệp tạm bằng `FileChannel.force(true)`.
4. Đổi tên tệp tạm thành tệp đích bằng **atomic move** nếu file system hỗ trợ.
5. Nếu thao tác thất bại, báo lỗi thay vì đánh dấu đã lưu thành công.

File `FileSnapshotStore.java`:

```java
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.DateTimeException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class FileSnapshotStore {
    private static final String HEADER = "orders-snapshot-v1";

    public void save(Path destination, List<PracticeOrder> source)
            throws IOException {
        Path target = destination.toAbsolutePath().normalize();
        Path parent = target.getParent();
        Files.createDirectories(parent);

        List<PracticeOrder> rows = new ArrayList<>(source);
        rows.sort(Comparator.comparingLong(PracticeOrder::orderId));

        Set<Long> ids = new HashSet<>();
        StringBuilder text = new StringBuilder();
        text.append(HEADER).append('\n');
        text.append("count=").append(rows.size()).append('\n');

        for (PracticeOrder row : rows) {
            if (!ids.add(row.orderId())) {
                throw new IllegalArgumentException(
                        "Trùng orderId: " + row.orderId());
            }
            text.append(row.orderId()).append('\t')
                .append(row.customerId()).append('\t')
                .append(row.status()).append('\t')
                .append(row.totalAmount().toPlainString()).append('\t')
                .append(row.createdAt()).append('\t')
                .append(row.version()).append('\n');
        }

        Path temporary =
                Files.createTempFile(parent, "orders-", ".tmp");
        try {
            Files.writeString(
                    temporary, text.toString(), StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            try (FileChannel channel = FileChannel.open(
                    temporary, StandardOpenOption.WRITE)) {
                channel.force(true);
            }

            // Thử atomic replacement; nếu FS không hỗ trợ, fail.
            Files.move(
                    temporary, target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    public List<PracticeOrder> read(Path source) throws IOException {
        List<String> lines =
                Files.readAllLines(source, StandardCharsets.UTF_8);
        if (lines.size() < 2 || !HEADER.equals(lines.get(0))
                || !lines.get(1).startsWith("count=")) {
            throw new IOException("Sai header hoặc phiên bản snapshot");
        }

        try {
            int expected = Integer.parseInt(lines.get(1).substring(6));
            if (expected < 0 || expected != lines.size() - 2) {
                throw new IOException("Số hàng thực tế khác count header");
            }
            List<PracticeOrder> result = new ArrayList<>();
            Set<Long> ids = new HashSet<>();

            for (int lineNo = 2; lineNo < lines.size(); lineNo++) {
                String[] field = lines.get(lineNo).split("\t", -1);
                if (field.length != 6) {
                    throw new IOException(
                            "Thiếu/thừa cột ở dòng " + (lineNo + 1));
                }
                PracticeOrder row = new PracticeOrder(
                        Long.parseLong(field[0]),
                        Long.parseLong(field[1]),
                        field[2],
                        new BigDecimal(field[3]),
                        Instant.parse(field[4]),
                        Long.parseLong(field[5]));
                if (!ids.add(row.orderId())) {
                    throw new IOException(
                            "Trùng orderId ở dòng " + (lineNo + 1));
                }
                result.add(row);
            }
            return List.copyOf(result);
        } catch (IllegalArgumentException | DateTimeException ex) {
            throw new IOException("Snapshot chứa dữ liệu không hợp lệ", ex);
        }
    }
}
```

### Điều được và chưa được bảo đảm khi ghi tệp

**Tốt hơn việc ghi đè trực tiếp:** khi atomic move hoạt động đúng, một reader mở tệp đích trước hoặc sau rename thường thấy một phiên bản đầy đủ thay vì một tệp đang ghi dở. Cách dùng file tạm cùng thư mục giảm nguy cơ move xuyên file system.

**Chưa tương đương transaction database:**

- `ATOMIC_MOVE` là tính năng tùy file system/provider; nếu không hỗ trợ, ví dụ **báo lỗi**. Không âm thầm fallback sang move không nguyên tử rồi tuyên bố đã đạt cùng bảo đảm.
- `force(true)` đồng bộ tệp tạm theo ngữ nghĩa của môi trường, nhưng **không tự bảo đảm directory entry sau rename đã được flush** trong mọi OS/file system. Hệ thống cần bảo đảm durability sau mất điện phải có thêm quy trình đồng bộ directory/khôi phục phù hợp nền tảng và thử bằng fault injection.
- Tệp snapshot này không có khóa writer. Hai JVM cùng gọi `save()` có thể ghi đè lần lượt; **last writer wins** mà không kiểm tra version. Atomic rename không giải quyết mất cập nhật.
- Một tệp đơn giản không cung cấp chỉ mục theo customer, foreign key, SQL JOIN hay transaction trên nhiều tệp.
- `readAllLines()` và xây nội dung với `StringBuilder` thích hợp dữ liệu nhỏ của lab; với hàng triệu hàng cần streaming, quản lý memory, snapshot protocol và validation khác.
- Header count giúp phát hiện một số tình huống bị cắt/nghẽn, **không phải checksum mã hóa hay bằng chứng không bị sửa nội dung**. Có thể thêm digest, manifest, signature và backup độc lập theo mục tiêu an toàn.

**Quan trọng:** không bao giờ đồng nhất “`Files.move()` đã trả về” với “đã chống được mọi tình huống mất điện/phần cứng”. Phải định nghĩa failure model và kiểm thử trên hệ thống lưu trữ thực tế.

## 6. Lưu cùng dữ liệu vào PostgreSQL bằng JDBC transaction

Ở phía database, ứng dụng dùng `PreparedStatement` để bind từng trường đúng kiểu. Đối với bài thực hành, ta **thay toàn bộ dữ liệu của riêng bảng `practice_orders`** trong một transaction PostgreSQL, rồi đọc lại bằng query có `ORDER BY order_id`.

File `JdbcOrderRepository.java`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class JdbcOrderRepository {
    private final DataSource dataSource;

    public JdbcOrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    // CHỈ dùng trên database lab và bảng practice_orders riêng!
    public void replaceLabSnapshot(List<PracticeOrder> orders)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (Statement statement = connection.createStatement()) {
                    statement.executeUpdate("DELETE FROM practice_orders");
                }

                String sql = """
                    INSERT INTO practice_orders
                        (order_id, customer_id, status,
                         total_amount, created_at, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """;
                try (PreparedStatement ps =
                             connection.prepareStatement(sql)) {
                    for (PracticeOrder row : orders) {
                        ps.setLong(1, row.orderId());
                        ps.setLong(2, row.customerId());
                        ps.setString(3, row.status());
                        ps.setBigDecimal(4, row.totalAmount());
                        ps.setObject(5, OffsetDateTime.ofInstant(
                                row.createdAt(), ZoneOffset.UTC));
                        ps.setLong(6, row.version());
                        ps.addBatch();
                    }
                    ps.executeBatch();
                }
                connection.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }

    public List<PracticeOrder> readAll() throws SQLException {
        String sql = """
            SELECT order_id, customer_id, status,
                   total_amount, created_at, version
            FROM practice_orders
            ORDER BY order_id
            """;
        List<PracticeOrder> result = new ArrayList<>();
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setQueryTimeout(10);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new PracticeOrder(
                            rs.getLong("order_id"),
                            rs.getLong("customer_id"),
                            rs.getString("status"),
                            rs.getBigDecimal("total_amount"),
                            rs.getObject(
                                    "created_at", OffsetDateTime.class)
                              .toInstant(),
                            rs.getLong("version")));
                }
            }
        }
        return List.copyOf(result);
    }
}
```

Ở đây `DELETE` và các câu `INSERT` nằm **cùng transaction trên một connection**. Nếu một câu insert lỗi và transaction rollback thành công, dữ liệu cũ của bảng vẫn còn; các reader khác theo mô hình isolation phù hợp không nhìn thấy dữ liệu mới chưa commit. Đây là khác biệt lớn so với việc xóa tệp rồi ghi từng dòng.

**Không áp dụng `replaceLabSnapshot()` cho dữ liệu production.** Trên production, thường cần `INSERT ... ON CONFLICT ...` có quy tắc nghiệp vụ, `UPDATE ... WHERE version = ?`, batch hợp lý, chỉ sửa các row đã được xác thực và transaction boundary phù hợp. Xóa rồi chèn toàn bộ một bảng có thể phá khóa ngoại/trigger, tốn WAL và tạo tranh chấp lớn.

Các điểm tích hợp Java:

- `DataSource` nên được tạo một lần cho vòng đời service, thường bởi pool; mọi `Connection` mượn từ pool phải được đóng/trả lại kịp thời.
- Không tự nối SQL từ giá trị người dùng; bind bằng `PreparedStatement`.
- Khi dùng JPA/Hibernate hoặc framework có `@Transactional`, **chỉ một tầng sở hữu transaction**; không lồng các câu `commit()` thủ công vào transaction manager.
- Trong PostgreSQL, `TIMESTAMPTZ` lưu thời điểm; khi lấy bằng `OffsetDateTime` và đổi sang `Instant`, nên so cùng thời điểm UTC chứ không so chuỗi múi giờ.
- Không đọc từ asynchronous replica ngay sau khi ghi rồi coi kết quả cũ là mất dữ liệu; bước đối chiếu này đọc từ DB lab primary để tránh replication lag.

## 7. So sánh theo khóa và từng trường, không theo vị trí hàng

Phép đối chiếu đúng nên phân biệt ba loại khác biệt:

1. **Chỉ có trong file:** ID tồn tại trong snapshot, không có trong DB.
2. **Chỉ có trong DB:** ID không tồn tại trong snapshot, nhưng có ở DB.
3. **Cùng ID nhưng khác trường:** status, số tiền, thời gian, version hoặc customer khác nhau.

Mỗi nguồn được biến thành `Map<orderId, PracticeOrder>`; nếu một nguồn có ID trùng, báo lỗi thay vì cho `Map.put()` âm thầm ghi đè. File `OrderComparator.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeSet;

public final class OrderComparator {
    private OrderComparator() {}

    public record Difference(
            long orderId, String field, String fileValue, String dbValue) {}

    public static List<Difference> compare(
            List<PracticeOrder> fromFile,
            List<PracticeOrder> fromDb) {
        Map<Long, PracticeOrder> file = byId(fromFile);
        Map<Long, PracticeOrder> db = byId(fromDb);
        TreeSet<Long> allIds = new TreeSet<>(file.keySet());
        allIds.addAll(db.keySet());

        List<Difference> diff = new ArrayList<>();
        for (long id : allIds) {
            PracticeOrder left = file.get(id);
            PracticeOrder right = db.get(id);
            if (left == null) {
                diff.add(new Difference(id, "missing-in-file",
                        "<absent>", "present"));
                continue;
            }
            if (right == null) {
                diff.add(new Difference(id, "missing-in-db",
                        "present", "<absent>"));
                continue;
            }

            addIfDifferent(diff, id, "customerId",
                    left.customerId(), right.customerId());
            addIfDifferent(diff, id, "status",
                    left.status(), right.status());
            addIfDifferent(diff, id, "totalAmount",
                    left.totalAmount(), right.totalAmount());
            addIfDifferent(diff, id, "createdAt",
                    left.createdAt(), right.createdAt());
            addIfDifferent(diff, id, "version",
                    left.version(), right.version());
        }
        return List.copyOf(diff);
    }

    private static Map<Long, PracticeOrder> byId(
            List<PracticeOrder> rows) {
        Map<Long, PracticeOrder> index = new HashMap<>();
        for (PracticeOrder row : rows) {
            if (index.putIfAbsent(row.orderId(), row) != null) {
                throw new IllegalArgumentException(
                        "Trùng orderId: " + row.orderId());
            }
        }
        return index;
    }

    private static void addIfDifferent(
            List<Difference> diff, long id, String field,
            Object fileValue, Object dbValue) {
        if (!Objects.equals(fileValue, dbValue)) {
            diff.add(new Difference(id, field,
                    String.valueOf(fileValue),
                    String.valueOf(dbValue)));
        }
    }
}
```

**Vì sao không so theo vị trí?** PostgreSQL không bảo đảm thứ tự hàng nếu câu `SELECT` không có `ORDER BY`; ngay cả khi SQL có `ORDER BY`, file vẫn có thể được export với thứ tự khác. So khóa giúp phân biệt **đảo thứ tự** với **mất bản ghi**.

**Vì sao cần chuẩn hóa trước khi so?** Một chuỗi thời gian `2026-11-01T09:30:00Z` và `2026-11-01T16:30:00+07:00` cùng biểu diễn một `Instant`. Tiền `42.0` và `42.00` có cùng giá trị số nhưng không cùng biểu diễn chuỗi. Mô hình `PracticeOrder` chuẩn hóa scale và timestamp, nên `Objects.equals` ở comparator có ý nghĩa nhất quán trong phạm vi lab.

**Lưu ý:** nếu normalization làm mất một thông tin nghiệp vụ quan trọng (ví dụ chữ ký số phải khớp byte-for-byte), phải dùng phép so riêng cho trường đó; không được bỏ qua khác biệt tùy tiện.

## 8. Ghép các bước thành một lần chạy thực tế

File `PracticeRunner.java` dùng HikariCP tạo pool cho database lab, ghi fixture vào cả hai nơi rồi đọc lại. Credential được cấp từ môi trường **chỉ cho lab**, không hardcode trong repository:

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

public final class PracticeRunner {
    public static void main(String[] args) throws Exception {
        List<PracticeOrder> fixture = List.of(
            new PracticeOrder(101, 501, "PENDING",
                    new BigDecimal("125.50"),
                    Instant.parse("2026-11-01T09:30:00Z"), 0),
            new PracticeOrder(102, 502, "PAID",
                    new BigDecimal("42.00"),
                    Instant.parse("2026-11-01T09:31:00Z"), 1),
            new PracticeOrder(103, 501, "CANCELLED",
                    new BigDecimal("0.00"),
                    Instant.parse("2026-11-01T09:32:00Z"), 2)
        );

        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl(required("LAB_DB_JDBC_URL"));
        cfg.setUsername(required("LAB_DB_USER"));
        cfg.setPassword(required("LAB_DB_PASSWORD"));
        cfg.setMaximumPoolSize(3);
        cfg.setConnectionTimeout(5_000);

        Path filePath = Path.of("lab-data", "orders.snapshot");
        FileSnapshotStore fileStore = new FileSnapshotStore();

        try (HikariDataSource dataSource = new HikariDataSource(cfg)) {
            JdbcOrderRepository dbStore =
                    new JdbcOrderRepository(dataSource);

            fileStore.save(filePath, fixture);
            dbStore.replaceLabSnapshot(fixture);

            List<PracticeOrder> fromFile = fileStore.read(filePath);
            List<PracticeOrder> fromDb = dbStore.readAll();
            List<OrderComparator.Difference> differences =
                    OrderComparator.compare(fromFile, fromDb);

            if (!differences.isEmpty()) {
                differences.forEach(System.err::println);
                throw new IllegalStateException(
                        "Đối chiếu KHÔNG ĐẠT: " + differences.size()
                                + " khác biệt");
            }
            System.out.println(
                    "PASS: hai nơi có cùng " + fromFile.size()
                            + " đơn hàng theo khóa và giá trị");
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu cấu hình: " + key);
        }
        return value;
    }
}
```

Trước khi chạy, cần tạo database lab, cấp quyền cần thiết cho role test, chạy schema ở mục 3, thêm PostgreSQL JDBC và HikariCP vào dependencies theo build tool của project, rồi cấp `LAB_DB_JDBC_URL`, `LAB_DB_USER` và `LAB_DB_PASSWORD` **qua cơ chế secret của môi trường**. Biến môi trường chỉ là cách minh họa cấu hình ngoài mã; credential vẫn có thể lộ qua log/process diagnostic, nên không log toàn bộ env hoặc giữ credential production trong lab.

**Kết quả kỳ vọng** khi có ba bản ghi và không có lỗi:

```text
PASS: hai nơi có cùng 3 đơn hàng theo khóa và giá trị
```

Đây là **kết quả dự kiến**, không phải kết quả đã chạy trong bài học. Mẫu code chưa bao gồm xác thực tenant, phân quyền nghiệp vụ, migration runner, metric hoặc lịch trình backup; nó chỉ minh họa một vòng đối chiếu có giới hạn.

### Trình tự thực hiện quan trọng thế nào?

Nếu `fileStore.save()` thành công rồi `dbStore.replaceLabSnapshot()` thất bại, file đã chứa fixture mới còn DB vẫn có dữ liệu cũ. Bài tập sẽ báo **không đạt** ở lần so tiếp theo. Nhưng đó không có nghĩa cả hai nơi bị hỏng: nó chứng minh **hai hệ thống không commit nguyên tử cùng nhau**.

Trong một hệ thống thật, cần chọn **nguồn sự thật** rõ ràng (ví dụ database), rồi tạo file export/snapshot **sau commit** từ một snapshot đọc nhất quán. Nếu bắt buộc phân phối trạng thái giữa DB và object storage, cần version/manifest, idempotency và quy trình đối soát hoặc giao thức phối hợp phù hợp, không dựa vào thứ tự gọi hàm như một transaction phân tán.

## 9. Tạo khác biệt có chủ đích để chứng minh comparator hoạt động

Sau một lần chạy thành công, trong **database lab** có thể sửa một hàng và chạy riêng đoạn đọc/đối chiếu (không chạy lại phần `replaceLabSnapshot` vì nó sẽ reset dữ liệu):

```sql
-- Chỉ chạy trên practice_orders của DB LAB.
UPDATE practice_orders
SET total_amount = 126.50,
    version = version + 1
WHERE order_id = 101;
```

Comparator cần phát hiện ít nhất:

```text
Difference[orderId=101, field=totalAmount,
           fileValue=125.50, dbValue=126.50]
Difference[orderId=101, field=version,
           fileValue=0, dbValue=1]
```

Tương tự, thêm `order_id=999` vào DB lab sẽ tạo `missing-in-file`; xóa một bản ghi ở DB sẽ tạo `missing-in-db`. **Nếu thay đổi file** để thử parser, chỉ sửa bản sao snapshot **trong lab**: làm hỏng header, sai số cột hoặc trùng ID phải trả lỗi đọc, không được âm thầm bỏ qua.

Để tránh nhầm lẫn trong test, nên lưu **bản fixture đầu vào bất biến** và không reset nó trước mỗi phép so âm tính. Một test không thể phát hiện dữ liệu sai nếu nó luôn ghi đè cả hai nguồn bằng cùng dữ liệu ngay trước lúc kiểm tra.

## 10. So sánh ranh giới consistency, atomicity và durability

| Khía cạnh | Snapshot tệp của ví dụ | PostgreSQL của ví dụ |
| --- | --- | --- |
| Đơn vị ghi | Toàn bộ tệp snapshot | Nhiều hàng trong một DB transaction |
| Khả năng rollback | Trước atomic rename thường giữ bản đích cũ; sau rename không có cơ chế `ROLLBACK` SQL | `ROLLBACK` toàn transaction nếu chưa commit |
| Kiểm soát đồng thời | Không có lock/version writer trong code mẫu | DB hỗ trợ row locking, isolation và version/constraint |
| Ghi bền vững | Phụ thuộc file system, `force`, rename, directory sync và thiết bị | Phụ thuộc WAL, commit durability và cấu hình engine |
| Đọc nhất quán | Một tệp đơn có atomic replacement theo hỗ trợ FS; nhiều tệp không cùng snapshot | MVCC snapshot và transaction theo isolation |
| Chỉ mục/truy vấn | Phải đọc/parse hoặc tự xây index | SQL, index, planner, aggregate, join |
| Ràng buộc | Constructor/parser và logic của người viết | PK, CHECK, FK, UNIQUE và transaction |
| Tiến hóa schema | Header `v1` + code reader/migration format | DDL migration/compatibility giữa app versions |
| Backup/khôi phục | Tự thiết kế lịch backup, retention và verify | Logical/physical backup, WAL/PITR theo khả năng DB |
| Quyền truy cập | Quyền file/volume/OS | DB role, table privilege, TLS và network policy |

**Cả file lẫn database đều có thể mất dữ liệu** nếu ứng dụng xác nhận trước khi ghi bền vững, ổ đĩa lỗi hoặc không có backup. PostgreSQL cung cấp công cụ tốt hơn để quản lý những bảo đảm phức tạp, nhưng không có nghĩa chỉ gọi `commit()` là hoàn thành toàn bộ chiến lược khôi phục. Cần biết mức cấu hình WAL, backup, HA và recovery thực tế.

### Nếu hai snapshot đọc không cùng thời điểm thì sao?

Giả sử file được export lúc 10:00; PostgreSQL được đọc để đối chiếu lúc 10:10, sau khi một đơn đã được thanh toán. Comparator báo `status` và `version` lệch là **đúng**. Nó không thể tự phân biệt:

- File ghi sai dữ liệu.
- DB ghi sai dữ liệu.
- Hai nơi phản ánh **hai thời điểm hợp lệ khác nhau**.

Do đó bản export dùng cho đối chiếu production cần ghi **mốc version/watermark, thời gian snapshot hoặc commit position phù hợp**, kèm giao thức đọc DB tương ứng. Đừng cố làm cho mọi diff biến mất bằng cách liên tục “lấy mới nhất” giữa lúc giao dịch đang diễn ra.

## 11. Cập nhật đồng thời: file và DB sẽ khác nhau ra sao?

Với cùng đơn hàng, hai worker cùng đọc `version=0`, `status=PENDING` rồi cùng quyết định đổi trạng thái:

```text
T1 đọc version 0 ----+
                     +---- T1 muốn ghi PAID
T2 đọc version 0 ----+
                     +---- T2 muốn ghi CANCELLED
```

**Tệp snapshot hiện tại:** nếu mỗi worker xây một file đầy đủ rồi cùng atomic rename, một file sẽ thắng cuối cùng; thay đổi của worker kia có thể bị ghi đè mà không phát hiện. Atomic rename **không phải optimistic locking**.

**Trong PostgreSQL:** có thể bảo vệ chuyển trạng thái bằng điều kiện:

```sql
UPDATE practice_orders
SET status = 'PAID', version = version + 1
WHERE order_id = 101
  AND status = 'PENDING'
  AND version = 0;
```

Ứng dụng kiểm tra affected rows. Nếu T1 đã đổi version trước, T2 dùng version cũ sẽ cập nhật **0 hàng**; khi ấy T2 phải xử lý conflict hoặc bắt đầu transaction mới đọc lại dữ liệu, không ghi đè mù. Nếu có nhiều bảng phải thay đổi atomically, thực hiện mọi lệnh trong cùng transaction và rollback khi một bất biến bị từ chối.

Để có version concurrency trên file, phải thiết kế riêng: lock liên tiến trình đáng tin cậy, kiểm tra expected version, atomic update cả file và cơ chế khôi phục. `synchronized` trên một object Java chỉ bảo vệ các thread dùng **cùng lock trong một JVM**, không bảo vệ hai JVM hay nhiều máy.

## 12. Kiểm thử lỗi: chỉ đối chiếu sau khi các bước đã xác định kết quả

Nên kiểm thử ít nhất những tình huống sau:

| Tình huống | Cách gây lỗi an toàn trong lab | Kỳ vọng |
| --- | --- | --- |
| File path không ghi được | Dùng thư mục test có quyền hạn chế hoặc injected I/O error | Lỗi được trả về, không báo snapshot mới đã lưu |
| File tạm ghi xong nhưng chưa rename | Tiêm lỗi trước `Files.move()` | Tệp đích cũ còn; tệp tạm được dọn theo policy |
| File header/version sai | Sửa bản sao snapshot test | Reader từ chối, không trả dữ liệu thiếu mà coi thành công |
| File thiếu một dòng | Cắt dòng sau khi tạo snapshot test | Kiểm tra `count` báo sai số hàng |
| File sai giá trị vẫn đủ dòng | Sửa `totalAmount` của một đơn | Reader có thể đọc được nhưng comparator chỉ ra diff |
| SQL insert lỗi giữa batch | Trùng PK/vi phạm CHECK trong fixture lab | Transaction rollback, không có trạng thái nửa chừng |
| JDBC mất kết nối trước commit | Proxy test/ngắt session có kiểm soát | Không tự đánh dấu command thành công; đọc lại để phân loại |
| JDBC mất ACK khi commit | Fault injection tại ranh giới network phù hợp | Kết quả commit có thể chưa rõ; đối soát bằng request ID |
| Hai writer cập nhật cùng order | Barrier trong test trên DB/container | DB guard ngăn lost update; file cần lock/version riêng |
| DB backup/restore | Restore tại môi trường cô lập, không dùng dữ liệu thật | Khả năng đọc, schema, role và dữ liệu nghiệp vụ phù hợp |

Không dùng những lệnh như `kill -9` trên PostgreSQL production hoặc xóa nhầm data directory để “thử độ bền”. Nếu muốn kiểm tra crash durability, dùng DB lab có volume riêng, chuẩn bị dữ liệu và có rollback runbook; phân biệt **kill client session**, **server crash** và **mất điện** vì chúng không tương đương.

**Khi `commit()` ném exception**, đừng giả định transaction đã rollback: có thể database đã commit nhưng phản hồi bị mất. Một ứng dụng cần request ID/idempotency receipt hoặc cách đối soát đủ nhất quán để không thực thi lại command hai lần.

## 13. Kiểm thử tự động JUnit 5: điều gì nên assert?

Tách test thành hai nhóm: **test serializer/comparator không cần database** và **integration test với PostgreSQL thật**.

Test đơn vị có thể xác minh mọi khác biệt quan trọng mà không cần container:

```java
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FileAndCompareTest {
    private static PracticeOrder order(long id, String amount) {
        return new PracticeOrder(id, 501, "PENDING",
                new BigDecimal(amount),
                Instant.parse("2026-11-01T09:30:00Z"), 0);
    }

    @Test
    void roundTripFileAndCompareSemantics() throws Exception {
        Path directory = Files.createTempDirectory("orders-lab-");
        Path file = directory.resolve("orders.snapshot");
        try {
            FileSnapshotStore store = new FileSnapshotStore();
            List<PracticeOrder> initial =
                    List.of(order(102, "42.0"), order(101, "125.50"));

            store.save(file, initial);
            List<PracticeOrder> restored = store.read(file);
            assertTrue(OrderComparator.compare(initial, restored).isEmpty());
            assertEquals(101, restored.get(0).orderId()); // đã sắp xếp

            List<PracticeOrder> changed =
                    List.of(order(101, "126.50"), order(102, "42.00"));
            var differences =
                    OrderComparator.compare(restored, changed);
            assertEquals(1, differences.size());
            assertEquals("totalAmount", differences.get(0).field());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Đoạn test trên dùng file temp và xóa sạch sau khi hoàn tất; nếu file system thử nghiệm không hỗ trợ `ATOMIC_MOVE`, nó sẽ **báo lỗi**, giúp phát hiện giới hạn nền tảng thay vì âm thầm đánh giá pass. Với bộ test lớn, dùng `@TempDir` của JUnit 5 để quản lý đường dẫn thử nghiệm nhất quán hơn.

**Integration test** nên dựng PostgreSQL phiên bản phù hợp bằng Testcontainers hoặc database test độc lập, chạy DDL/fixture rồi:

1. Ghi ba `PracticeOrder` giống nhau vào file và bảng.
2. Đọc lại cả hai, assert `OrderComparator.compare(...).isEmpty()`.
3. Sửa một trường DB trong transaction, assert comparator báo đúng ID và trường đó.
4. Thêm fixture vi phạm `CHECK/PRIMARY KEY` vào transaction DB và xác minh rollback giữ dữ liệu cũ.
5. Với cập nhật đồng thời, chạy hai worker có barrier, assert chỉ một ghi `WHERE version = ?` thành công ở version ban đầu.

Những test này là **mục tiêu cần triển khai**, không phải bằng chứng đã chạy. Không thay PostgreSQL bằng một DB nhúng khác rồi suy ra khóa, isolation và SQLSTATE chắc chắn giống PostgreSQL.

## 14. Tiến hóa định dạng và schema: bài thực hành nâng cao

Sau một thời gian, nghiệp vụ cần thêm `currency` hoặc `updatedAt`. Hai nơi lưu phải tiến hóa theo cơ chế khác nhau:

| Vấn đề | Tệp snapshot | PostgreSQL |
| --- | --- | --- |
| Thêm trường | Tạo `orders-snapshot-v2`, quy định default/upgrade từ v1 | DDL migration `ADD COLUMN`/backfill/constraint |
| Reader cũ | Chỉ hiểu v1; phải từ chối v2 hoặc có khả năng backward compatibility được thiết kế | Query/ORM cũ cần tương thích giai đoạn rolling deploy |
| Dữ liệu đang ghi | Chuyển format cần atomic replacement và chống concurrent writer | DDL lock, backfill, index build, migration plan |
| Đối chiếu | Định nghĩa schema canonical chung và mapping v1/v2 | Mapping SQL row sang phiên bản canonical |

Đừng thêm cột rồi im lặng cho reader cũ bỏ qua, hoặc mặc định `currency='USD'` với mọi đơn cũ khi chưa có quy tắc nghiệp vụ. Trong migration, cần chỉ rõ **nguồn dữ liệu cho trường mới** và làm thế nào khôi phục một bản snapshot cũ đúng format.

Khi có nhiều nguồn và nhiều phiên bản, comparator nên nêu `snapshot_format_version`, `schema_migration_version` và thời điểm chụp dữ liệu trong report; không chỉ in “PASS” hoặc “FAIL”.

## 15. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: cùng số lượng nhưng khác khóa

File có IDs `101,102,103`; PostgreSQL có `101,102,999`. Cả hai nguồn đều ba hàng. Nếu so `COUNT(*)`, kết luận sẽ sai ở đâu?

**Đáp án:** số lượng bằng nhau không chứng minh hai tập dữ liệu bằng nhau. Comparator phải báo `orderId=103` thiếu trong DB và `orderId=999` thiếu trong file.

### Bài tập 2: khác biểu diễn, cùng ý nghĩa

File chứa số tiền `42.0` và thời gian `2026-11-01T09:31:00Z`; DB đọc được `42.00` và `2026-11-01T16:31:00+07:00`. Có nên đánh dấu dữ liệu khác nhau?

**Đáp án:** không, nếu hợp đồng dữ liệu xem hai số tiền tương đương và hai thời gian cùng một thời điểm. Chuẩn hóa `BigDecimal` theo scale được phê duyệt, chuyển thời gian về `Instant` trước khi so. Không làm tròn hoặc bỏ qua khác biệt ngoài hợp đồng.

### Bài tập 3: JVM chết trong lúc ghi tệp

Một chương trình gọi `Files.writeString(destination, veryLargeContent)` trực tiếp rồi chết khi mới ghi nửa tệp. Cách thiết kế tốt hơn là gì?

**Đáp án:** ghi vào tệp tạm cùng file system, sync nội dung, atomic move nếu hỗ trợ, có kế hoạch directory sync/recovery theo nền tảng. Với nhiều writer, cần thêm đồng bộ/version. Đây chưa tự trở thành transaction nhiều tệp.

### Bài tập 4: batch database lỗi giữa chừng

Một fixture ba hàng hợp lệ được chèn vào PostgreSQL sau `DELETE FROM practice_orders` trong cùng transaction. Hàng thứ ba vi phạm constraint nên `executeBatch()` ném lỗi. Dữ liệu cũ còn không?

**Đáp án:** nếu toàn bộ thao tác thực sự dùng cùng transaction và ứng dụng rollback khi lỗi, dữ liệu cũ vẫn còn theo atomicity. Nếu code dùng auto-commit, có thể đã commit một phần; cần kiểm tra ranh giới transaction thay vì chỉ dựa vào số lần gọi JDBC.

### Bài tập 5: đối chiếu giữa hai thời điểm

File export lúc 10:00. DB cập nhật version đơn lúc 10:05. Comparator chạy lúc 10:10 và phát hiện khác version. Có thể kết luận database ghi sai không?

**Đáp án:** chưa. Hai nguồn được chụp ở những thời điểm khác nhau. Cần mốc snapshot/watermark, đọc nhất quán và tiêu chí thời điểm trước khi quy lỗi cho hệ thống lưu trữ.

### Bài tập 6: hai JVM ghi snapshot

Hai JVM cùng đọc snapshot version 0, cùng cập nhật đơn 101 theo hai hướng, rồi mỗi JVM `ATOMIC_MOVE` tệp riêng vào cùng tên. Có bảo đảm phát hiện conflict không?

**Đáp án:** không. Atomic move bảo vệ tính nguyên vẹn của từng lần thay tên, không ngăn last-writer-wins. Cần version check dưới một lock liên tiến trình đáng tin hoặc dùng DB với điều kiện `WHERE version = ?` và transaction.

### Bài tập 7: mất kết nối ở COMMIT

JDBC `commit()` ném lỗi network. Chương trình tự tạo orderId mới rồi retry ghi đơn từ đầu. Rủi ro là gì?

**Đáp án:** commit cũ có thể đã thành công dù client mất ACK; retry bằng ID mới có thể tạo hai đơn hoặc hai tác động. Cần request/idempotency key ổn định và đối soát trên DB đủ nhất quán.

### Bài tập 8: có file snapshot thì không cần backup?

Team mỗi đêm ghi file `orders.snapshot` mới vào cùng thư mục, lần nào cũng thay thế file cũ. Khi phát hiện lỗi xóa dữ liệu từ hai ngày trước, tệp hiện tại có giúp phục hồi đúng mốc không?

**Đáp án:** không bảo đảm. Nếu mọi file cũ đã bị ghi đè và không có retention, snapshot mới cũng chứa lỗi. Cần backup lịch sử độc lập, chính sách giữ phiên bản, checksum/restore drill và WAL/PITR nếu yêu cầu.

### Checklist hoàn thành bài thực hành

- Có **một mô hình canonical** cho cả file và DB, quy tắc kiểu dữ liệu/scale/múi giờ rõ ràng chưa?
- File có header phiên bản, record count, validation, deterministic ordering và cơ chế ghi tạm/atomic replacement phù hợp chưa?
- PostgreSQL có PK/CHECK, transaction boundary, JDBC parameter binding và readback trên nguồn đúng chưa?
- Comparator có phát hiện **thiếu/thừa ID, trùng ID và lệch từng field**, không chỉ so số hàng hoặc thứ tự chưa?
- Đã thử dữ liệu cố tình lệch, file hỏng, transaction rollback và writer đồng thời chưa?
- Kết quả đối chiếu có ghi **mốc snapshot, schema version, nguồn sự thật và phạm vi dữ liệu** chưa?
- Có xử lý lỗi khi file commit thành công nhưng DB thất bại, không tuyên bố hai hệ thống cùng commit atomically chưa?
- Có tách database lab khỏi production, bảo vệ credential, không in PII/secret và trả connection về pool chưa?
- Có kế hoạch backup/restore cho cả dữ liệu thật và định dạng tệp, thay vì dựa vào bản snapshot cuối cùng chưa?

**Kết luận:** Lưu và đọc cùng một tập dữ liệu qua tệp và cơ sở dữ liệu là cách thực hành trực tiếp để hiểu **persistence không chỉ là serialization**. File snapshot giúp nhìn thấy byte/format/atomic replacement; PostgreSQL cung cấp transaction, constraint, SQL và kiểm soát đồng thời theo cấu hình. Phép đối chiếu theo khóa và giá trị chuẩn hóa giúp phát hiện sai lệch, nhưng chỉ có ý nghĩa khi biết dữ liệu thuộc **cùng một thời điểm và phạm vi**. Từ bài thực hành này, người học có cơ sở lựa chọn nơi lưu nguồn sự thật, thiết kế xuất dữ liệu, đặt ranh giới transaction và xây kiểm thử phục hồi đáng tin cậy cho ứng dụng Java.
