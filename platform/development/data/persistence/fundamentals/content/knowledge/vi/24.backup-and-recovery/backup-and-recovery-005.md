# Tính nhất quán của dữ liệu trong thời gian sao lưu

Một dịch vụ Java đang nhận đơn hàng liên tục. Lúc 10:00, hệ thống bắt đầu sao lưu bảng `orders`; vài phút sau, nó mới sao lưu `order_items` và `payments`. Trong khoảng thời gian ấy, các giao dịch vẫn thêm sản phẩm, chốt thanh toán và cập nhật trạng thái đơn. Nếu sao chép từng bảng một cách tùy tiện, bản sao có thể chứa **đơn hàng ở trạng thái cũ nhưng các dòng chi tiết ở trạng thái mới** — tổ hợp dữ liệu chưa từng tồn tại như một trạng thái giao dịch hợp lệ.

Do đó, câu hỏi quan trọng không chỉ là “backup có chạy hết không?”, mà là: **Khi khôi phục, dữ liệu có tương ứng với một điểm nhất quán hợp lệ hay không, các giao dịch đã commit nào có mặt, và những phần nào nằm ngoài ranh giới ấy?**

Trong chương **Sao lưu và khôi phục** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này liên hệ trực tiếp đến transaction, isolation, WAL, độ bền dữ liệu, connection và ranh giới persistence Java. Ta sẽ phân biệt tính nhất quán của *logical backup*, *physical backup* và bản chụp hạ tầng, xem PostgreSQL duy trì dữ liệu đúng khi ứng dụng vẫn ghi, rồi xây một quy trình sao lưu–khôi phục có thể kiểm chứng.

## 1. Bản sao “đầy đủ” chưa chắc “nhất quán”

Xét hai bảng minh họa:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL
);

CREATE TABLE order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Tại thời điểm A, đơn số 42 có `total_amount = 100` và tổng dòng chi tiết bằng 100. Một transaction khác thay đổi đơn thành 150 **cùng lúc** thêm dòng hàng 50:

```sql
BEGIN;
INSERT INTO order_items(item_id, order_id, quantity, unit_price)
VALUES (1003, 42, 1, 50);
UPDATE orders SET total_amount = 150 WHERE order_id = 42;
COMMIT;
```

Nếu một công cụ tự chế đọc `orders` **trước khi transaction này commit** nhưng đọc `order_items` **sau commit**, bản sao có thể lưu `total_amount = 100` và các dòng chi tiết có tổng 150. Mỗi truy vấn đơn lẻ có thể đọc dữ liệu đã commit, nhưng **hai truy vấn không cùng một thời điểm quan sát**.

```text
Thời gian                  T0          T1               T2
                            |           |                |
Transaction ghi             |       COMMIT 100 -> 150     |
                            |           |                |
Sao lưu không phối hợp   đọc orders                     đọc items
                         total=100                       sum=150

Kết quả: bản sao trộn hai trạng thái giao dịch.
```

Một backup hữu ích cần bảo vệ tối thiểu hai thuộc tính:

- **Tính nhất quán giao dịch:** không khôi phục “nửa transaction” đã được commit nguyên tử; hoặc có trạng thái tương đương một snapshot hợp lệ theo cơ chế DB, hoặc có đủ log để phục hồi về trạng thái hợp lệ.
- **Khả năng phục hồi:** các tệp, bản ghi log, metadata và phiên bản phần mềm cần thiết thực sự có thể được dùng để đưa DB lên trạng thái phục vụ.

Ngoài ra, hệ thống còn cần **tính nhất quán nghiệp vụ**: đơn đã thanh toán, sổ cái, tồn kho, outbox và hệ thống ngoài có còn đáp ứng các quy tắc được công bố không? Một backup nhất quán về transaction **không thể tự sửa dữ liệu nghiệp vụ đã sai từ trước**.

## 2. Những tầng nhất quán cần phân biệt

| Tầng | Câu hỏi đúng | Ví dụ sai lệch |
| --- | --- | --- |
| **Tệp/trang lưu trữ** | Các page và metadata đủ để DB mở lên và recovery không? | Sao chép data directory khi DB đang chạy, file được copy ở nhiều thời điểm nhưng thiếu WAL |
| **Transaction** | Các cập nhật của một transaction có được khôi phục nguyên tử không? | Có `orders` mới nhưng thiếu `order_items` tương ứng |
| **Snapshot nhiều bảng** | Các hàng trong các bảng có cùng ranh giới quan sát không? | Dump bảng A rồi bảng B ở hai snapshot độc lập |
| **Toàn cluster/database** | Backup có gồm đầy đủ database, role, extension, tablespace, sequence và cấu hình cần thiết không? | Data restore được nhưng role/extension thiếu hoặc version schema không tương thích |
| **Nhiều database/dịch vụ** | Những hệ thống khác nhau có được khôi phục về trạng thái phối hợp được không? | DB đơn hàng hồi về T0, dịch vụ thanh toán vẫn ở T2 |
| **Side effect ngoài DB** | Email, broker, file, cổng thanh toán đã xảy ra có cần đối soát không? | Restore outbox về trước khi sự kiện đã được phát, sau đó phát lại |

Không nên dùng một từ “consistent” mà không nói **phạm vi**. PostgreSQL `pg_dump` có snapshot nhất quán trong một database, nhưng điều đó không tự tạo snapshot đồng thời cho mọi database, hệ thống broker hoặc API thanh toán. Một bản chụp volume đồng bộ về block cũng không nhất thiết làm nội dung được restore có ý nghĩa nghiệp vụ nếu thiếu transaction recovery.

## 3. Vai trò của MVCC khi sao lưu logic

Với PostgreSQL, **MVCC** (*multi-version concurrency control*) cho phép transaction đọc một snapshot phù hợp mà không cần chặn toàn bộ giao dịch ghi. Mỗi phiên bản hàng có thông tin phục vụ xác định nó hiển thị với snapshot nào. Một transaction ghi đang dở dang không được nhìn như đã commit chỉ vì một trang dữ liệu đã được ghi ra disk.

Ở isolation `READ COMMITTED` của PostgreSQL, mỗi statement thông thường nhìn snapshot riêng tại lúc câu lệnh bắt đầu. Nếu chạy hai câu `SELECT` liên tiếp khi writer commit giữa chúng, kết quả có thể phản ánh hai thời điểm khác nhau.

```sql
-- Ví dụ chỉ đọc, với isolation mặc định READ COMMITTED:
BEGIN;
SELECT total_amount FROM orders WHERE order_id = 42;  -- có thể là 100

-- Transaction khác COMMIT cập nhật đơn và chi tiết tại đây.

SELECT COALESCE(SUM(quantity * unit_price), 0)
FROM order_items WHERE order_id = 42;                 -- có thể là 150
COMMIT;
```

Nếu cần hai phép đọc quan sát **cùng snapshot** trong PostgreSQL, hãy đặt chúng trong một transaction `REPEATABLE READ`:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT total_amount FROM orders WHERE order_id = 42;

SELECT COALESCE(SUM(quantity * unit_price), 0)
FROM order_items WHERE order_id = 42;

COMMIT;
```

Trong ví dụ này, các câu đọc bên trong transaction dùng cùng snapshot, kể cả khi writer commit trong lúc đọc. Snapshot là **ảnh logic tại một điểm quan sát**, không phải cam kết rằng DB ngừng thay đổi. Một snapshot cũ có thể hợp lệ nhưng không phải dữ liệu mới nhất tại thời điểm backup hoàn tất.

**Lưu ý về isolation:** `REPEATABLE READ` không tự kiểm chứng mọi invariant nghiệp vụ và không nhất thiết có hành vi giống nhau ở mọi hệ quản trị. Nó giải quyết sự trộn thời điểm của các lần đọc trong mô hình này, chứ không thay thế transaction đúng ở phía ghi, constraint hoặc kiểm tra bất biến nhiều hàng.

## 4. Sao lưu logic: một snapshot để đọc nhiều bảng

**Logical backup** xuất schema và dữ liệu dưới dạng câu SQL hoặc định dạng lưu trữ logic. Với PostgreSQL, `pg_dump` sử dụng một snapshot MVCC nhất quán cho dữ liệu của **một database**, để các hàng được dump phản ánh một điểm quan sát nhất quán dù những transaction khác vẫn ghi.

Ví dụ lệnh do một job backup được cấp quyền tối thiểu chạy:

```bash
# Minh họa. File đầu ra phải ở vùng lưu trữ backup được bảo vệ.
# Cung cấp thông tin xác thực qua cơ chế bảo mật của môi trường,
# tuyệt đối không đặt password vào tham số command.
pg_dump \
  --host=db-primary.internal.example \
  --username=backup_reader \
  --dbname=orders_db \
  --format=custom \
  --file=/secure/backups/orders_001.dump
```

Một bản dump logic tốt cần xét cả *schema* và *data*. Công cụ thực tế có thể gồm table definitions, indexes, constraints, sequence metadata, function và những đối tượng khác tùy quyền/phạm vi được chọn. Nếu backup được giới hạn bằng tùy chọn chọn bảng/schema, không được mặc định mọi phụ thuộc đều có mặt.

**Những giới hạn cần nhớ:**

1. **Phạm vi một database:** nhiều lần gọi `pg_dump` cho các database khác nhau không mặc định chia sẻ một snapshot toàn hệ thống. Các global object như role/tablespace definitions có quy trình backup riêng; phải kiểm chứng khả năng restore cùng chúng.
2. **DDL đồng thời:** snapshot dữ liệu không có nghĩa mọi thay đổi schema tùy ý đều an toàn trong lúc dump. Các câu `ALTER/DROP` có thể xung đột lock với dump hoặc làm backup thất bại; nên có cửa sổ kiểm soát migration.
3. **Sequence:** thao tác cấp số qua sequence có semantics không giao dịch giống bảng thông thường. Trạng thái sequence được dump/restore cần kiểm tra; không suy ra nó phản ánh chính xác cùng snapshot như mọi row.
4. **Dữ liệu ngoài DB:** file upload, object storage, broker và dịch vụ khác không nằm trong `pg_dump`; phải phối hợp backup và điểm khôi phục riêng.
5. **Rủi ro dữ liệu cũ:** snapshot thường bắt đầu trước khi dump kết thúc; những giao dịch commit sau snapshot sẽ không xuất hiện trong dump, dù ứng dụng đã trả thành công trước khi file backup hoàn tất.

### 4.1. Parallel dump và snapshot đồng bộ

Khi dùng nhiều worker để dump các bảng song song, mỗi worker có thể có connection riêng. Nếu mỗi worker nhìn snapshot khác nhau, backup có thể không nhất quán giữa bảng. PostgreSQL hỗ trợ **synchronized snapshots** cho `pg_dump --jobs` trên các phiên bản/điều kiện tương thích; đây là lý do không nên tự viết parallel exporter chỉ bằng cách chia bảng cho nhiều JVM mà không phối hợp snapshot.

Ví dụ minh họa công cụ chính thức:

```bash
# Directory format được pg_dump dùng cho parallel jobs.
pg_dump \
  --host=db-primary.internal.example \
  --username=backup_reader \
  --dbname=orders_db \
  --format=directory \
  --jobs=4 \
  --file=/secure/backups/orders_dir_001
```

Chạy nhiều job có thể giảm thời gian dump khi CPU/disk/network còn dư, nhưng nó **tăng số connection và mức cạnh tranh I/O**. Ngoài ra, backup tool vẫn có thể gặp xung đột DDL; không coi parallel dump là phương án không tác động tới production.

### 4.2. Export/import snapshot khi tự xây nhiều reader

Nếu buộc phải tự viết công cụ xuất dữ liệu nhiều connection, PostgreSQL cung cấp cơ chế `pg_export_snapshot()` và `SET TRANSACTION SNAPSHOT`. Ví dụ mô tả điều kiện sử dụng, **không phải hướng dẫn thay thế `pg_dump`**:

```sql
-- Session A: mở transaction, xuất snapshot và GIỮ MỞ
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
-- Ví dụ kết quả: 00000003-0000001B-1

-- Session B: mở transaction riêng, trước mọi query dữ liệu:
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET TRANSACTION SNAPSHOT '00000003-0000001B-1';
SELECT COUNT(*) FROM orders;
COMMIT;

-- Session A: chỉ COMMIT sau khi các reader đã import snapshot.
COMMIT;
```

Đoạn trên trình bày hai session trong một code block cho dễ nhìn; trong thực tế **không gửi toàn bộ như một script của một session**. Snapshot được xuất phải còn hợp lệ khi reader nhập nó, isolation và điều kiện phiên bản PostgreSQL phải đáp ứng quy tắc import. Không giữ transaction export mở vô thời hạn, vì snapshot lâu có thể kéo dài tuổi các phiên bản hàng mà hệ thống cần giữ.

## 5. Sao lưu vật lý: tệp được copy ở nhiều thời điểm nhưng recovery phải nhất quán

**Physical backup** giữ các trang/tệp lưu trữ của DB để khôi phục ở mức engine. Khi DB vẫn ghi, các file được sao chép có thể phản ánh **những thời điểm vật lý khác nhau**. Điều quan trọng không phải “mọi file byte-for-byte giống lúc 10:00”, mà là **DB có đủ metadata và WAL để phục hồi về trạng thái giao dịch hợp lệ**.

PostgreSQL dùng **Write-Ahead Log (WAL)** để ghi lại thay đổi phục vụ crash recovery và backup/recovery. Trong một quy trình physical backup đúng cách, DB xác định ranh giới backup, backup tool copy data files, đồng thời phải có **đầy đủ WAL cần thiết** để hệ thống replay tới điểm nhất quán khi restore.

```text
                   Database vẫn nhận ghi
                           |
                           v
                     Data files + WAL
                      /           \
            Copy base files       Thu thập WAL
            (qua nhiều pha)       (bao phủ đúng ranh giới)
                      \           /
                       v         v
                         Base backup
                             |
                      Restore + WAL replay
                             |
                             v
                  Trạng thái DB nhất quán
```

Một ví dụ PostgreSQL dùng công cụ `pg_basebackup`, được chạy bằng danh tính backup và vị trí đích được bảo vệ:

```bash
# Minh họa tạo physical base backup dạng plain.
# Đích phải chưa chứa dữ liệu có thể bị ghi đè nguy hiểm.
pg_basebackup \
  --host=db-primary.internal.example \
  --username=backup_operator \
  --pgdata=/secure/backups/base_001 \
  --format=plain \
  --wal-method=stream \
  --progress

# Kiểm tra manifest và các thành phần mà công cụ hỗ trợ xác minh.
pg_verifybackup /secure/backups/base_001
```

Ở chế độ `--wal-method=stream`, `pg_basebackup` lấy WAL cần thiết qua luồng để base backup có thể phục hồi nhất quán theo cam kết của công cụ. **Điều này không có nghĩa backup tự chứa mọi WAL để khôi phục đến bất kỳ phút nào về sau**: để làm *point-in-time recovery* (PITR) vượt thời điểm mà base backup bao phủ, phải có quy trình lưu giữ/archiving WAL liên tục và đủ chuỗi log.

`pg_verifybackup` giúp phát hiện lỗi manifest, thiếu/sai file và kiểm tra WAL theo khả năng/phiên bản công cụ, nhưng **không chứng minh ứng dụng sẽ chạy đúng sau restore**. Phải thử khôi phục DB thật ở môi trường cô lập và chạy các phép kiểm tra dữ liệu, schema, quyền, extension và use case Java.

**Tuyệt đối không dùng `cp -r`/copy file data directory đang mở rồi xem đó là physical backup hợp lệ.** Việc chép các file mà không phối hợp với cơ chế backup/WAL có thể làm mất dữ liệu hoặc tạo trạng thái không thể recovery. Với disk/volume snapshot, phải hiểu cơ chế làm “đóng băng” đồng thời các volume chứa data, tablespace và WAL, bảo đảm đủ log để crash recovery; một snapshot của riêng volume dữ liệu khi WAL nằm ở volume khác có thể không an toàn.

## 6. Tính nhất quán của snapshot storage và backup trên replica

Nhiều nền tảng lưu trữ hỗ trợ **storage snapshot** hoặc backup managed service. Một ảnh chụp block tại một thời điểm có thể là **crash-consistent**: tương tự hệ thống đột ngột mất điện, DB có thể sử dụng WAL để recovery. Nhưng mức bảo đảm này phụ thuộc:

- Snapshot có **nguyên tử trên tất cả volume liên quan** hay mỗi volume bị chụp tại thời điểm khác nhau?
- WAL, tablespace, transaction status và metadata có đầy đủ, cùng một miền snapshot hợp lệ không?
- Có cần hooks/quy trình của DB để bảo đảm khả năng khôi phục hay không?
- Mốc phục hồi và retention của snapshot được mô tả, kiểm thử cụ thể ra sao?

**Crash-consistent** không đồng nghĩa với **application-consistent trên nhiều dịch vụ**. Một DB có thể recovery sạch ở T0 trong khi một dịch vụ khác giữ trạng thái T1. Các hệ thống nhiều DB cần kế hoạch phối hợp mốc, log offset, ID nghiệp vụ hoặc công cụ backup phân tán có hợp đồng nhất quán rõ.

Backup từ **read replica/standby** có thể giảm phần tải đọc/backup trên primary tùy DB và cấu hình, nhưng replica có thể đang trễ, bị ngắt replay hoặc thiếu khả năng thực hiện một số thao tác backup tùy phiên bản. Không tự kết luận rằng “backup trên replica = backup mới nhất trên primary”. Cần xác định **mốc log/replay thực tế**, quyền, tiến trình recovery và mức RPO của bản sao đó.

## 7. Snapshot nhất quán trong Java/JDBC: đọc nhiều bảng cùng một transaction

Ứng dụng Java có thể cần **xuất dữ liệu nghiệp vụ** hoặc kiểm tra thống kê trên nhiều bảng. Khi đó, cần một ranh giới đọc nhất quán, ngay cả khi không dùng `pg_dump`. Ví dụ sau dùng **PostgreSQL** và Java 17+, trả về một DTO có hai tổng đọc tại cùng snapshot.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ConsistentOrderReader {
    public record Totals(
            BigDecimal orderTotal, BigDecimal lineItemsTotal) {
        public boolean sameAmount() {
            return orderTotal.compareTo(lineItemsTotal) == 0;
        }
    }

    private final DataSource dataSource;

    public ConsistentOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Totals readAtOneSnapshot(long orderId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Cấu hình trước khi transaction bắt đầu thực hiện SQL.
            connection.setReadOnly(true);
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_REPEATABLE_READ);
            connection.setAutoCommit(false);

            try {
                BigDecimal header = readOrderTotal(connection, orderId);
                BigDecimal details = readItemsTotal(connection, orderId);
                connection.commit();
                return new Totals(header, details);
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private static BigDecimal readOrderTotal(
            Connection c, long orderId) throws SQLException {
        String sql = """
            SELECT total_amount
            FROM orders WHERE order_id = ?
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException(
                            "Không tồn tại orderId");
                }
                return rs.getBigDecimal(1);
            }
        }
    }

    private static BigDecimal readItemsTotal(
            Connection c, long orderId) throws SQLException {
        String sql = """
            SELECT COALESCE(SUM(quantity * unit_price), 0)
            FROM order_items WHERE order_id = ?
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next(); // Aggregate không có GROUP BY trả một hàng.
                return rs.getBigDecimal(1);
            }
        }
    }
}
```

**Những giới hạn của ví dụ:**

1. Hai câu SELECT dùng **cùng `Connection` và cùng transaction `REPEATABLE READ`**, nên không trộn một snapshot cũ với một snapshot mới. `setReadOnly(true)` là một cấu hình/hint JDBC theo driver, **không phải cơ chế phân quyền**; database role và câu SQL vẫn phải được kiểm soát.
2. `sameAmount()` chỉ là một phép kiểm tra nghiệp vụ. Nếu dữ liệu tại snapshot đã vi phạm invariant thì kết quả vẫn sai, dù snapshot nhất quán. Ứng dụng cần bảo đảm tổng đơn/chi tiết được ghi trong cùng transaction hoặc có mô hình tính tổng đúng.
3. Connection được trả về pool sau `try-with-resources`. Pool/driver phải khôi phục thuộc tính `readOnly`, isolation và `autoCommit` trước khi cho request khác mượn.
4. Không dùng một transaction đọc kéo dài hàng giờ qua request HTTP chỉ để “giữ snapshot”. Transaction lâu có thể giữ các phiên bản hàng cũ, làm tăng bloat và cản công tác VACUUM/cleanup.
5. Đây là minh họa **đọc nhất quán**, không phải thuật toán xuất backup logic toàn database. Việc tự chạy hàng loạt SELECT và ghi ra nhiều tệp còn cần protocol snapshot, xử lý DDL, định dạng, ghi file nguyên tử và khôi phục thử; với PostgreSQL thường nên chọn `pg_dump` chính thức.

## 8. Lưu WAL và chọn điểm khôi phục (PITR)

Một bản base backup có một **ranh giới thời gian/LSN**. Nếu có chuỗi WAL liên tục và khả dụng sau base backup, hệ thống PostgreSQL có thể replay những thay đổi đã commit đến **một recovery target phù hợp** (*point-in-time recovery*). Điều này giúp giảm khoảng dữ liệu phải mất khi lỗi do thao tác nhầm hoặc sự cố vật lý.

```text
T0: base backup bắt đầu -------- T1: base backup hoàn tất
             WAL cần cho backup có sẵn
                                 |
                                 +----- WAL archive liên tục ---- T3
                                                      |
                                        T2: lỗi DELETE nhầm
                                                      |
                      Restore base backup + replay đến trước T2
```

Không thể coi mọi timestamp là điểm chính xác tuyệt đối cho mọi sự kiện; cần xác định transaction commit, timeline/LSN và chính sách phục hồi. Nếu target nằm trước một sự kiện sai, các transaction hợp lệ **commit sau target** cũng có thể không được khôi phục; cần chọn điểm dựa trên mục tiêu nghiệp vụ và kế hoạch đối soát.

**PITR không thay thế backup ổn định.** Nếu WAL bị thất lạc giữa base backup và target, quá trình recovery có thể không tiến xa được như kỳ vọng. Việc bật `archive_mode` nhưng archive command liên tục lỗi không phải là kế hoạch PITR thành công.

### RPO và RTO không được suy từ lịch chạy backup

| Khái niệm | Ý nghĩa | Điều cần đo |
| --- | --- | --- |
| **RPO** (*Recovery Point Objective*) | Tối đa bao nhiêu dữ liệu đã commit được phép mất trong tình huống sự cố | Khoảng cách giữa lần commit cuối có thể phục hồi và thời điểm lỗi; lưu WAL/replica, tính liên tục của archive |
| **RTO** (*Recovery Time Objective*) | Thời gian mục tiêu để phục hồi dịch vụ | Tải backup, verify, replay WAL, kiểm tra DB, đổi endpoint và đưa Java service trở lại |
| **Backup freshness** | Đã bao lâu kể từ bản backup thành công và mốc log tương ứng | Thời gian tạo, version, phạm vi, điểm kết thúc và archive health |
| **Recovery confidence** | Có bằng chứng backup thật sự khôi phục được không | Restore drill, kiểm tra toàn vẹn, dữ liệu nghiệp vụ và thời gian thực tế |

Ví dụ một tổ chức làm full backup mỗi đêm nhưng không lưu WAL liên tục: dù có hai bản backup tồn tại, sự cố sát cuối ngày có thể làm mất gần một ngày giao dịch. Nếu yêu cầu RPO chỉ vài phút, phải thiết kế và thử cơ chế lưu log/replication phù hợp, không chỉ tăng số file backup.

## 9. Nhiều database, outbox và tác động ngoài DB: điểm nhất quán nghiệp vụ

Giả sử dịch vụ A có database đơn hàng, dịch vụ B có database thanh toán. Một giao dịch ở A ghi `orders.status='PAID'` và `outbox_events` để phát event; worker gửi message tới broker, B cập nhật sổ cái của mình. Khi khôi phục:

- Backup của A được chụp ở T0.
- Backup của B ở T1, muộn hơn T0.
- Broker hoặc dịch vụ gửi email đã xử lý event giữa T0 và T1.

Hai database riêng có thể **mỗi cái hoàn toàn nhất quán** nhưng khi ghép lại lại tạo một trạng thái nghiệp vụ khó giải thích: B ghi nhận một thanh toán mà A chưa có đơn tương ứng tại mốc restore.

```text
Database A: [Order + Outbox] ------- backup A tại T0
                  |
                  v
               Broker ----------- đã giao E1
                  |
                  v
Database B: [Payment ledger] ------ backup B tại T1

Khôi phục A về T0 và B về T1 không tạo một snapshot toàn hệ thống.
```

Các chiến lược có thể cân nhắc tùy yêu cầu:

1. **Chỉ định một mốc phục hồi phối hợp:** ghi nhận mốc LSN/timestamp/offset tương ứng giữa các thành phần nếu sản phẩm và quy trình hỗ trợ, rồi restore theo kế hoạch.
2. **Đối soát sau restore:** so sánh transaction ID, order ID, payment operation ID và trạng thái sổ cái; sửa bằng nghiệp vụ bù trừ có audit, không chỉnh tay một phía rồi bỏ qua phía kia.
3. **Thiết kế idempotency end-to-end:** event/command có ID ổn định; sau restore, worker có thể phát lại từ outbox hoặc broker có thể giao lại. Consumer phải chống xử lý trùng theo ID đã được lưu trong cơ sở dữ liệu đủ bền.
4. **Quy trình saga/reconciliation:** những bước không có transaction chung được kiểm tra và bù trừ qua state machine; bù trừ là thao tác nghiệp vụ mới, không phải DB rollback.
5. **Chặn side effect trong môi trường restore:** không cho bản sao dựng thử tự động gửi email, thu tiền, phát outbox hoặc gọi API production khi chưa có cách ly và xác nhận rõ.

**Transactional outbox** giúp atomic giữa trạng thái đơn hàng và *ý định phát event* trong **cùng database nguồn**. Nó không biến broker và database khác thành một transaction chung. Ngoài ra, nếu restore DB nguồn về trước thời điểm đã phát event, outbox có thể bị phát lại; vì vậy cần giao thức idempotent và chiến lược đối soát.

## 10. Sao lưu nhất quán không có nghĩa không ảnh hưởng hiệu năng

Một logical dump dài cần giữ snapshot trong thời gian đọc. Trong PostgreSQL, snapshot kéo dài có thể **giữ lại các phiên bản hàng đã chết mà VACUUM chưa được phép thu hồi**, gây bloat hoặc tăng áp lực storage trong workload ghi lớn. Dump còn đọc nhiều trang và cạnh tranh CPU/disk/cache với API đang phục vụ.

Physical backup cũng tiêu thụ I/O, network, WAL bandwidth và dung lượng; nếu stream WAL hoặc archive không theo kịp, bộ phận backup có thể tăng độ trễ và gây thiếu dung lượng ở nguồn hoặc đích.

| Dấu hiệu khi backup chạy | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| API p95/p99 tăng | Backup tranh I/O hoặc tạo cache eviction | Disk throughput, IOPS, buffer hit, SQL latency |
| Kích thước bảng/index tăng bất thường | Snapshot cũ, churn, VACUUM không thu hồi được | Long transactions, vacuum status, dead tuples |
| WAL/archive backlog tăng | Tốc độ tạo WAL vượt khả năng lưu/chuyển | Archive errors, disk, replication slots, lag |
| Connection pool pending tăng | Query chậm, transaction đọc kéo dài, query bị DDL chặn | Acquire time, usage time, active transactions |
| Dump treo hoặc lỗi | DDL đang chờ/giữ lock hoặc hết tài nguyên | Wait events, blocker PIDs, backup logs |
| Replica trễ khi backup | CPU/I/O/network bị phân chia hoặc replay bị chậm | Replay lag, throughput và recovery point |

Một cách giảm tác động là **lập lịch tải**, giới hạn số job song song, điều tiết I/O nếu nền tảng cho phép, cấu hình timeout và tránh trùng thời điểm migration DDL nặng. Không kéo dài transaction ứng dụng để đợi backup; ngược lại, cũng không chủ động khóa toàn bảng trong hàng giờ nếu công cụ backup đã có cơ chế nhất quán phù hợp.

## 11. Khôi phục thử: cách kiểm chứng backup nhất quán

Một công việc backup chỉ nên được xem là **đáng tin cậy** sau khi có thử nghiệm restore. Kiểm tra tệp tồn tại hoặc checksum đúng là cần thiết, nhưng chưa chứng minh schema, quyền và ứng dụng khởi động được.

### 11.1. Restore logic vào môi trường cách ly

Giả sử đã tạo database thử nghiệm `restore_lab` rỗng trong môi trường không nối ra các hệ thống sản xuất. Có thể dùng:

```bash
# Chỉ áp dụng cho một database restore_lab cách ly đã chuẩn bị.
# --no-owner/--no-acl có thể hữu ích ở lab không có role của nguồn.
pg_restore \
  --host=restore-db.internal.example \
  --username=restore_operator \
  --dbname=restore_lab \
  --no-owner \
  --no-acl \
  --exit-on-error \
  /secure/backups/orders_001.dump
```

Mục tiêu của tùy chọn `--no-owner --no-acl` ở lab là kiểm tra dữ liệu/schema mà không đòi hỏi toàn bộ role/ACL nguồn. **Đây không thay thế phép thử khôi phục quyền đầy đủ cho production**: trong diễn tập chính thức, phải kiểm tra role, grant, extension, timezone/collation, sequence, tablespace và cấu hình đúng yêu cầu.

### 11.2. Kiểm tra các bất biến dữ liệu

Các truy vấn kiểm chứng cần bám vào quy tắc nghiệp vụ và phạm vi backup, không chỉ `SELECT COUNT(*)`:

```sql
-- Đếm số đơn theo trạng thái, so với manifest hoặc thống kê nguồn
-- tại mốc backup phù hợp (không so tùy tiện với DB nguồn hiện tại).
SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status;

-- Nếu tổng đơn phải bằng tổng các dòng chi tiết theo quy tắc nghiệp vụ:
SELECT o.order_id, o.total_amount,
       COALESCE(SUM(i.quantity * i.unit_price), 0) AS items_total
FROM orders o
LEFT JOIN order_items i ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount IS DISTINCT FROM
       COALESCE(SUM(i.quantity * i.unit_price), 0)
LIMIT 20;
```

Nếu query cuối trả dữ liệu, cần phân biệt: **backup sai**, **quy tắc tính tổng chưa phản ánh chiết khấu/thuế**, hay **dữ liệu đã sai ngay trước backup**. Không vội tuyên bố backup hỏng chỉ từ một kiểm tra nghiệp vụ không đầy đủ.

### 11.3. Kiểm tra ứng dụng Java thực sự dùng được dữ liệu

Sau restore ở môi trường cô lập, kiểm tra:

- Schema version/migration phù hợp với bản ứng dụng được dùng để phục hồi; nếu cần migration sau restore thì có kế hoạch và khả năng rollback/forward-fix.
- Role và cấu hình kết nối có quyền phù hợp; secrets, TLS và endpoint **chỉ** tới database thử nghiệm, không vô tình tới production.
- Query quan trọng, index, khóa ngoại, unique constraint, sequence và identity hoạt động sau restore; thử ghi một giao dịch vào DB thử và rollback/đối soát.
- Những bản ghi outbox ở trạng thái chờ, inbox dedupe, job nền và các lịch tích hợp được xử lý theo kế hoạch — **không tự động tái phát side effect tới thế giới thật**.
- Có thể theo dõi RTO thực tế: thời gian lấy backup, decrypt, restore, replay WAL, validate dữ liệu và mở lại dịch vụ.

**Không chỉ mở được DB là đủ.** Một DB restore thành công nhưng thiếu key giải mã trường nhạy cảm, thiếu object storage gắn với record hoặc không tương thích schema của Java service vẫn có thể không phục vụ được nghiệp vụ.

## 12. Runbook trước, trong và sau sao lưu

| Giai đoạn | Việc cần làm | Dấu hiệu hoàn tất |
| --- | --- | --- |
| **Thiết kế** | Xác định phạm vi database, RPO/RTO, backup logic/physical, dependency ngoài DB và nơi giữ WAL | Có manifest và chính sách recovery bằng văn bản |
| **Chuẩn bị** | Kiểm tra quyền backup, phiên bản DB/tool, dung lượng, encryption, lịch tránh DDL và monitoring | Không có dependency chưa rõ hoặc thiếu dung lượng |
| **Bắt đầu** | Tạo snapshot logic nhất quán hoặc thực hiện protocol physical backup đúng engine | Mốc snapshot/backup và job ID được ghi nhận |
| **Trong lúc chạy** | Theo dõi latency, lock, long transaction, I/O, WAL/archive lag, trạng thái job | Không vi phạm ngưỡng vận hành; lỗi được phát hiện |
| **Kết thúc** | Xác minh code thoát thành công, file/manifest/checksum, WAL cần thiết và catalog backup | Bản backup hoàn tất, không thiếu dữ liệu phụ thuộc |
| **Lưu trữ** | Encryption, retention, offsite/immutable copies, phân quyền và tách miền lỗi | Backup còn đọc được; khóa giải mã còn có thể truy xuất |
| **Diễn tập restore** | Dựng DB cách ly, replay, kiểm tra schema/constraint/query/ứng dụng, đo RPO/RTO | Có bằng chứng restore và kết quả kiểm chứng |
| **Hậu kiểm** | Điều chỉnh tần suất, thời điểm, số worker và kế hoạch phục hồi sau sự cố | Chênh lệch so với mục tiêu đã được xử lý |

Một job báo “backup complete” chỉ khẳng định **quá trình ghi bản sao kết thúc theo logic của công cụ**. Một báo cáo backup tốt phải nêu thêm **phạm vi, consistency model, mốc log/snapshot, phiên bản, khả năng đọc/giải mã, trạng thái WAL và lần restore thử gần nhất**.

## 13. Các lỗi suy luận thường gặp

| Nhận định sai | Thực tế cần nhớ |
| --- | --- |
| “Copy mọi bảng thành công là backup nhất quán” | Các bảng có thể bị đọc ở snapshot khác nhau, tạo tổ hợp trạng thái không hợp lệ |
| “Backup khi đang ghi chắc chắn gây hỏng dữ liệu” | Công cụ DB chính thức có MVCC hoặc protocol physical + WAL để xử lý ghi đồng thời |
| “`REPEATABLE READ` làm database ngừng thay đổi” | Nó cung cấp snapshot phù hợp cho transaction đọc, không khóa toàn bộ writer |
| “Có base backup là PITR được mọi thời điểm” | Cần WAL đầy đủ và lưu trữ liên tục đến recovery target |
| “Replica có cùng mọi giao dịch đã ACK với primary” | Replica bất đồng bộ có thể trễ, kể cả lúc backup |
| “Snapshot volume nào cũng recovery được” | Snapshot đa volume, data directory, tablespace và WAL phải nhất quán về khả năng khôi phục |
| “Checksum file hợp lệ nghĩa là app chạy được” | Cần restore thử, schema/role/secret/extension và kiểm tra nghiệp vụ |
| “Backup PostgreSQL là backup cả broker và thanh toán” | Mỗi hệ thống có ranh giới riêng, cần mốc phối hợp và đối soát |
| “Restore outbox cũ không gây tác dụng phụ” | Worker có thể phát lại event; consumer/side effect phải lũy đẳng |
| “Backup một lần là xong” | Cần retention, lịch kiểm thử restore, monitoring và diễn tập theo RPO/RTO |

## 14. Bài tập thực hành

### Bài tập 1 — Hai bảng, hai thời điểm

Một exporter Java đọc `orders` lúc 10:00 và `order_items` lúc 10:05 bằng hai connection auto-commit riêng. Trong lúc đó có transaction chốt đơn.

**Câu hỏi:** có thể xuất hiện mâu thuẫn gì và cách sửa phù hợp là gì?

**Đáp án:** bản sao có thể trộn trạng thái trước và sau commit, như order total 100 và items sum 150. Ưu tiên `pg_dump` hoặc công cụ có synchronized snapshot; nếu tự xây, cần transaction snapshot nhất quán có phối hợp giữa các connection, không chỉ thêm `ORDER BY` hay chạy nhanh hơn.

### Bài tập 2 — READ COMMITTED và REPEATABLE READ

Một transaction Java chạy hai câu `SELECT` dưới `READ COMMITTED` trong PostgreSQL; writer commit giữa chúng. Có bảo đảm hai câu thấy cùng snapshot không?

**Đáp án:** không. Trong PostgreSQL, `READ COMMITTED` thường lấy snapshot tại từng statement. Để cùng quan sát một snapshot cho hai phép đọc, có thể dùng một transaction `REPEATABLE READ READ ONLY` và giữ cùng connection tới khi đọc xong.

### Bài tập 3 — Backup dữ liệu nhưng thiếu WAL

Một operator tự copy data directory PostgreSQL đang hoạt động, sau đó mất những WAL segment thuộc thời gian copy. Có thể coi bản sao là physical backup an toàn không?

**Đáp án:** không. File được copy có thể chứa các trang từ những thời điểm khác nhau; WAL và protocol backup hợp lệ là điều kiện để replay nhất quán. Dùng `pg_basebackup` hoặc cơ chế snapshot được DB hỗ trợ, giữ đúng WAL và kiểm thử restore.

### Bài tập 4 — Backup mỗi đêm và RPO

Một đội làm `pg_dump` lúc 00:00 hằng ngày, không lưu WAL để PITR. DB hỏng lúc 23:55, dịch vụ cần RPO 5 phút. Lịch sao lưu này có đạt yêu cầu không?

**Đáp án:** không. Bản dump gần nhất có thể thiếu gần một ngày giao dịch. Phải thiết kế giải pháp giảm RPO (chẳng hạn physical backup + WAL archiving/replication phù hợp) và đo khả năng phục hồi thực tế; chỉ tăng tần suất dump mà không kiểm chứng vẫn có rủi ro.

### Bài tập 5 — Restore giữa các dịch vụ

DB đơn hàng restore về 10:00 nhưng DB thanh toán và broker vẫn ở 10:10. Một `ORDER_PAID` từng được phát lại xuất hiện trong outbox sau restore. Có thể bật ngay worker và để nó gửi mọi event không?

**Đáp án:** chưa nên nếu chưa kiểm tra tác động ngoài DB. Cần cô lập môi trường diễn tập hoặc có kế hoạch đối soát, dedupe event ID, kiểm tra payment operation ID và lựa chọn replay/saga/bù trừ phù hợp, tránh thu tiền hoặc gửi thông báo lần hai.

### Bài tập 6 — Kiểm chứng sau restore

Job backup báo thành công, `pg_verifybackup` không báo lỗi, nhưng dịch vụ Java không khởi động do thiếu extension và một số role. Backup đã đáp ứng toàn bộ yêu cầu recovery chưa?

**Đáp án:** chưa. Kiểm tra manifest/tệp không thay thế restore drill đầy đủ; cần bao gồm các dependency như extension, roles, permissions, schema version, encryption key, kết nối và các use case ứng dụng.

### Checklist trước khi tuyên bố sao lưu an toàn

- Đã mô tả **phạm vi nhất quán**: một transaction, một database, cả cluster hay nhiều dịch vụ chưa?
- Logical dump có dùng snapshot đồng bộ cho các bảng/worker, và có chính sách DDL concurrent chưa?
- Physical backup có cơ chế engine hỗ trợ cùng đủ WAL/metadata, không sao chép file nóng tùy tiện chưa?
- Với PITR, có chuỗi WAL liên tục, retention, điểm khôi phục và kiểm chứng archive health chưa?
- Có đo tác động I/O, long snapshot, vacuum/bloat, replication lag và latency ứng dụng trong lúc backup không?
- Có bảo vệ backup bằng encryption, quyền tối thiểu, lưu trữ tách miền lỗi và kiểm soát khóa giải mã không?
- Đã restore thật ở môi trường cách ly, kiểm tra schema, role, sequence, constraint, data invariant và Java service chưa?
- Outbox, inbox, broker, thanh toán và side effect ngoài DB có kế hoạch đối soát/khôi phục riêng chưa?
- RPO/RTO có được xác minh bằng số liệu diễn tập, không chỉ được suy từ lịch backup hoặc log báo thành công chưa?

**Kết luận:** **Tính nhất quán trong thời gian sao lưu** là khả năng dựng lại một trạng thái dữ liệu có ranh giới giao dịch rõ ràng dù hệ thống tiếp tục hoạt động. Với sao lưu logic, trọng tâm là **snapshot MVCC nhất quán**; với sao lưu vật lý, trọng tâm là **protocol backup, tệp và WAL đầy đủ để replay về điểm hợp lệ**. Muốn recovery thực sự dùng được, còn phải xác định phạm vi giữa nhiều hệ thống, bảo vệ backup, diễn tập restore và đối soát những tác động nghiệp vụ ngoài database.
