# Đối soát dữ liệu khi trích xuất nhiều phần trong JDBC

Trong chương **Truy vấn quy mô lớn**, việc trích xuất một bảng có hàng triệu bản ghi thường không nên thực hiện bằng cách gọi `ResultSet` một lần rồi giữ tất cả trong một `List`. Ứng dụng thường chia dữ liệu thành nhiều **phần (partition/chunk/page)**, ghi ra các tệp hoặc đẩy sang hệ thống khác, sau đó ghép lại.

Vấn đề khó là: **làm thế nào biết không mất hàng, không trùng hàng, không sai nội dung và các phần có cùng trạng thái dữ liệu?** Một chương trình chỉ chạy đủ số lần `executeQuery()` hoặc thấy mọi tệp đều tồn tại chưa thể chứng minh dữ liệu cuối cùng chính xác.

Với **JDBC**, ta sử dụng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và transaction để truy vấn SQL tham số hóa, xử lý dữ liệu theo luồng, đặt ranh giới nhất quán và ghi nhận bằng chứng đối soát. Bài học tập trung vào **quy trình đối soát đầu–cuối**: thiết kế phân vùng, tạo mốc dữ liệu, kiểm tra số hàng và checksum, quản lý manifest, khôi phục sau lỗi và kiểm chứng lại ở đích.

## 1. “Đối soát” cần chứng minh những điều gì?

Một lượt xuất dữ liệu thường phải đáp ứng nhiều thuộc tính độc lập:

| Thuộc tính | Câu hỏi cần trả lời | Cách kiểm chứng tiêu biểu |
| --- | --- | --- |
| **Đầy đủ (completeness)** | Có xuất thiếu hàng thuộc phạm vi yêu cầu không? | Đếm hàng nguồn trong cùng snapshot, so tổng số hàng phần xuất |
| **Không trùng (uniqueness)** | Một hàng có bị xuất hai lần không? | Khóa định danh ổn định, biên phân vùng không chồng lấn, kiểm tra khóa trùng |
| **Nhất quán (consistency)** | Các phần có phản ánh cùng một trạng thái CSDL không? | Snapshot/transaction nhất quán hoặc cơ chế đóng băng/version dữ liệu |
| **Toàn vẹn nội dung (integrity)** | Byte của tệp có thay đổi, cắt cụt hoặc sai encoding không? | Checksum trên byte thực tế của tệp, so sánh với manifest |
| **Khôi phục được (recoverability)** | Chết tiến trình ở phần thứ 8 có tiếp tục an toàn không? | Tệp tạm, checkpoint bền vững, định danh run/part, kiểm tra trước retry |
| **Truy vết được (auditability)** | Có biết đã lấy dữ liệu nào, từ đâu và theo quy tắc gì không? | Manifest chứa query/version, tham số, mốc, phạm vi, số hàng, hash |
| **Đúng nghiệp vụ** | Giá trị xuất có đáp ứng quy tắc, schema, timezone không? | Kiểm tra tổng tiền, tổng trạng thái, ràng buộc hoặc đối soát định danh |

**Không có một phép kiểm tra duy nhất thay thế tất cả.** Ví dụ, tổng số hàng xuất bằng tổng số hàng nguồn nhưng vẫn có thể bị **thiếu một hàng và trùng một hàng khác**. Hash tệp đúng chứng minh byte tệp khớp manifest, nhưng nếu manifest được tạo từ dữ liệu đã thiếu thì hash vẫn đúng.

### Ví dụ thiếu–trùng nhưng số hàng bằng nhau

~~~text
Nguồn:  [10, 20, 30, 40, 50]
Đích:   [10, 20, 20, 40, 50]

COUNT nguồn = 5
COUNT đích  = 5  ← bằng nhau
Nhưng id=30 bị thiếu, id=20 bị lặp.
~~~

Do đó cần phối hợp **COUNT + khóa duy nhất + biên phần không chồng lấn + kiểm tra nội dung**.

## 2. Chọn khóa và ranh giới phân phần

Giả sử bảng nguồn (ví dụ PostgreSQL hoặc MySQL):

~~~sql
CREATE TABLE source_orders (
    id BIGINT PRIMARY KEY CHECK (id > 0),
    status VARCHAR(30) NOT NULL,
    total_cents BIGINT NOT NULL
);
~~~

`id` là khóa chính **duy nhất, ổn định và có thứ tự**. Đây là ứng viên tốt cho keyset pagination.

### Hai kiểu chia phần thường dùng

**A. Chia theo khoảng khóa cố định**

~~~text
Phần 1:  1 <= id < 1001
Phần 2:  1001 <= id < 2001
Phần 3:  2001 <= id < 3001
...
~~~

SQL:

~~~sql
SELECT id, status, total_cents
FROM source_orders
WHERE id >= ? AND id < ?
ORDER BY id;
~~~

Các khoảng **nửa mở** `[low, high)` giúp định nghĩa biên rõ ràng; giá trị đúng bằng `high` thuộc phần tiếp theo. Điều kiện cần: phân chia toàn bộ miền khóa cần xuất mà không chồng lấn, không bỏ khoảng nào.

**B. Keyset pagination theo khóa đã xuất cuối cùng**

~~~sql
SELECT id, status, total_cents
FROM source_orders
WHERE id > ? AND id <= ?
ORDER BY id
LIMIT ?;
~~~

Với ví dụ này, `LIMIT ?` là cú pháp quen thuộc của **PostgreSQL/MySQL**, không phải cú pháp portable của mọi DBMS. Ở các hệ khác có thể dùng `FETCH FIRST ... ROWS ONLY` hoặc cơ chế tương đương. Luôn tham số hóa giá trị và xác minh cú pháp driver/DBMS.

Các tham số là:

1. `lastId` — ID cuối đã xuất ở phần trước; ban đầu là 0 khi khóa luôn dương.
2. `upperId` — cận trên của lượt xuất, được chọn ở đầu quy trình.
3. `pageSize` — số hàng tối đa mỗi phần.

Sau mỗi phần, chỉ di chuyển `lastId` tới **ID lớn nhất đã xuất thành công**. Không tăng theo công thức `lastId + pageSize` vì ID có thể không liên tục.

### Vì sao `OFFSET` dễ gây sai khi nguồn thay đổi?

Ví dụ:

~~~sql
SELECT id, status
FROM source_orders
ORDER BY id
LIMIT 100 OFFSET 200;
~~~

Nếu giữa hai lần lấy trang có bản ghi mới được thêm hoặc bản ghi cũ bị xóa, **vị trí hàng có thể dịch chuyển**. Điều đó có thể gây trùng hoặc bỏ sót giữa các trang. Với offset lớn, DBMS cũng có thể phải bỏ qua nhiều hàng, làm tăng chi phí.

Keyset theo khóa duy nhất thường ổn định và hiệu quả hơn, **nhưng không tự giải quyết mọi vấn đề nhất quán**. Nếu hàng cũ bị sửa/xóa hoặc ID mới được chèn vào khoảng đã duyệt, vẫn cần cơ chế snapshot hoặc chiến lược dữ liệu phù hợp.

### Nếu thứ tự theo thời gian thì sao?

`ORDER BY created_at` có thể có nhiều hàng cùng thời điểm. Một cursor chỉ lưu timestamp sẽ không đủ:

~~~sql
-- Thứ tự ổn định khi created_at có thể trùng nhau:
SELECT id, created_at, status
FROM source_orders
WHERE created_at > ?
   OR (created_at = ? AND id > ?)
ORDER BY created_at, id
LIMIT ?;
~~~

Lưu **cặp cursor `(created_at, id)`** và dùng khóa phụ duy nhất. Nếu `created_at` có thể cập nhật, bản ghi có thể đổi vị trí giữa các phần; muốn tránh thiếu/trùng cần snapshot hoặc chiến lược theo phiên bản.

## 3. Mốc `MAX(id)` giúp gì và không giúp gì?

Một cách đặt giới hạn lượt xuất là lấy ID lớn nhất ở đầu:

~~~sql
SELECT COALESCE(MAX(id), 0) AS upper_id
FROM source_orders;
~~~

Rồi luôn truy vấn `id <= upper_id`. Điều này chặn **phần lớn bản ghi mới có ID tăng vượt cận trên** khỏi lọt vào lượt xuất hiện tại.

Tuy nhiên, mốc ID **không phải snapshot**:

- Một giao dịch khác có thể `UPDATE` hàng `id=100` sau khi phần đầu xuất xong; phần sau có thể thấy trạng thái mới của hàng khác.
- Một hàng `id=200` chưa được xuất có thể bị `DELETE` trước khi lượt xuất tới nó.
- Bản ghi mới có thể được chèn với ID **nhỏ hơn hoặc bằng `upper_id`**, ví dụ import lại hoặc ID được cấp nhưng commit muộn.
- Một transaction chưa commit lúc lấy `MAX(id)` có thể commit sau đó, tạo biến động mà mốc ID không loại trừ.
- Nếu khóa được tái sử dụng hoặc cập nhật, logic cursor có thể bỏ qua/trùng dữ liệu.

**Kết luận:** `MAX(id)` là một *fence* theo giá trị khóa, **không phải bằng chứng tất cả các phần nhìn thấy cùng một trạng thái nguồn**.

## 4. Giữ một snapshot nhất quán cho nhiều phần

Trong nhiều DBMS hỗ trợ MVCC, có thể đặt mức transaction phù hợp để nhiều câu `SELECT` trên **cùng một `Connection`, trong cùng một transaction** quan sát một snapshot nhất quán.

Ví dụ ý tưởng với **PostgreSQL**:

~~~java
try (Connection conn = dataSource.getConnection()) {
    // Thiết lập trước câu SQL đầu tiên của transaction.
    conn.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    conn.setReadOnly(true);
    conn.setAutoCommit(false);

    try {
        long upperId = readUpperId(conn);
        long expectedCount = countRowsWithinFence(conn, upperId);

        exportPagesOnSameConnection(conn, upperId);

        // Chỉ đọc: rollback để kết thúc transaction/snapshot.
        conn.rollback();
    } catch (SQLException | RuntimeException failure) {
        try {
            conn.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
~~~

Đây là **phác thảo điều khiển transaction**. Trong mã production cần khôi phục trạng thái `autoCommit`/`readOnly`/isolation trước khi trả connection cho pool, sau khi transaction đã kết thúc an toàn, và xử lý lỗi phát sinh khi đọc/ghi tệp.

Với PostgreSQL, `REPEATABLE READ` sử dụng snapshot nhất quán cho các câu đọc trong cùng transaction theo ngữ nghĩa MVCC của PostgreSQL. `Connection.setReadOnly(true)` thể hiện ý định chỉ đọc; không nên coi lời gọi này là thay thế kiểm soát quyền SQL.

**Không suy rộng thành quy tắc cho mọi DBMS:** JDBC định nghĩa các mức isolation nhưng hành vi snapshot và khả năng giữ nó qua nhiều câu SQL/transaction khác nhau giữa DBMS, storage engine và driver. Nếu sự nhất quán là điều kiện bắt buộc, hãy kiểm chứng chính xác trên hệ thống nguồn.

### Đánh đổi của transaction snapshot dài

Một transaction đọc hàng triệu bản ghi trong nhiều phút hoặc nhiều giờ có thể:

- Giữ phiên bản dữ liệu cũ hoặc cản trở việc dọn MVCC/vacuum tùy DBMS.
- Tiêu tốn tài nguyên kết nối, cursor, bộ nhớ phía server và thời gian quản trị.
- Gặp timeout, network failure, restart server hoặc giới hạn transaction.
- Khó mở rộng song song vì **không thể mặc định chia sẻ một snapshot giữa nhiều connection độc lập**.

Nếu nhiều worker/connection cần xuất song song mà vẫn cùng một snapshot, cần cơ chế **được DBMS hỗ trợ** để chia sẻ/export snapshot, hoặc làm việc trên tập dữ liệu đóng băng/đã phiên bản hóa. JDBC chuẩn **không có API phổ quát** để “ghim cùng snapshot cho mọi connection”.

### Khi không thể giữ transaction dài

Có thể cân nhắc:

1. **Bảng snapshot/staging**: materialize danh sách khóa và phiên bản dữ liệu thuộc lượt xuất, sau đó chia phần từ tập đã đóng băng.
2. **Version/snapshot ID nghiệp vụ**: truy vấn theo một phiên bản dữ liệu bất biến được thiết kế sẵn.
3. **Bulk export/backup nhất quán** theo khả năng DBMS, rồi chia phần ở tầng lưu trữ.
4. **Initial snapshot + CDC** (change data capture) để bắt thay đổi phát sinh và đồng bộ tới mốc log nhất định.

Một cột `updated_at <= watermark` đơn lẻ thường **không đủ** để bắt delete, cập nhật commit muộn hoặc lệch đồng hồ. Nếu cần biến tập xuất thành trạng thái chính xác ở một thời điểm, phải giải thích rõ cơ chế đối phó với các trường hợp ấy.

## 5. Thiết kế manifest đối soát cho mỗi lượt xuất

**Manifest** là bản mô tả bền vững về lượt trích xuất. Mỗi phần xuất nên có đủ thông tin để kiểm tra và phục hồi độc lập.

Ví dụ minh họa:

~~~json
{
  "run_id": "orders-2026-11-17-001",
  "source": "source_orders",
  "query_version": "v3",
  "schema_version": "2026-11",
  "isolation": "PostgreSQL REPEATABLE READ, one connection",
  "upper_id": 80250,
  "source_row_count": 78542,
  "parts": [
    {
      "part": 1,
      "file": "part-00001.csv",
      "first_id": 1,
      "last_id": 500,
      "rows": 500,
      "bytes": 18320,
      "sha256": "..."
    },
    {
      "part": 2,
      "file": "part-00002.csv",
      "first_id": 501,
      "last_id": 1002,
      "rows": 500,
      "bytes": 18604,
      "sha256": "..."
    }
  ],
  "status": "IN_PROGRESS"
}
~~~

Các giá trị và tên tệp trên **chỉ minh họa**; mục `parts` chưa đầy đủ, nên `status` là `IN_PROGRESS`, không được xem là manifest kết thúc. Manifest cuối cùng phải ghi đầy đủ các phần và kết quả kiểm chứng trước khi công bố `COMPLETE`.

### Các trường nên lưu

| Nhóm | Trường quan trọng | Lý do |
| --- | --- | --- |
| Định danh | `run_id`, `part_id`, phiên bản query/schema | Phân biệt lần xuất và định dạng |
| Phạm vi nguồn | Bảng, tham số lọc, tenant, mốc dữ liệu, isolation/snapshot | Biết xuất chính xác đối tượng nào |
| Phân vùng | `first_id`, `last_id`, `low/high` hoặc cursor bắt đầu/kết thúc | Phát hiện trùng/thiếu và cho phép tiếp tục |
| Số lượng | `rows` từng phần, tổng, `source_row_count` | Đối soát độ đầy đủ |
| Nội dung | `sha256` và kích thước byte mỗi tệp | Phát hiện tệp hỏng/cắt cụt/sai byte |
| Vận hành | `STARTED`/`STAGED`/`VERIFIED`/`COMPLETE`, thời điểm, lỗi | Phục hồi sau tiến trình chết |
| Định dạng | Charset UTF-8, CSV quoting, timezone, decimal format, null policy | Đọc và so sánh đúng dữ liệu |

Đừng ghi mật khẩu database, token hoặc dữ liệu nhạy cảm vào manifest. Nếu manifest có ID nghiệp vụ hoặc đường dẫn riêng tư, phân quyền truy cập và mã hóa theo mức độ nhạy cảm.

### Hai loại checksum khác nhau

- **Checksum tệp**: tính SHA-256 trên **byte thực tế đã ghi** ra phần CSV/Parquet/...; giúp phát hiện file bị sửa, hỏng hoặc truyền thiếu.
- **Checksum logic của hàng**: chuẩn hóa từng giá trị theo schema, sắp thứ tự theo khóa rồi hash theo một quy tắc cố định; phù hợp để so nguồn và đích dù định dạng file khác nhau.

Không trộn chúng. Hai file CSV có cùng dữ liệu nhưng khác cách escape, xuống dòng hoặc thứ tự hàng có thể có SHA-256 khác nhau. Ngược lại, checksum tệp đúng **không chứng minh dữ liệu có đầy đủ các hàng của nguồn**.

### Chuẩn hóa hash logic phải được định nghĩa trước

Nếu cần hash logic từ JDBC sang một hệ đích khác, cần quy tắc chính xác:

- Sắp theo khóa duy nhất; cùng một tập hàng nhưng thứ tự khác có thể cho hash khác.
- Phân biệt `NULL` với chuỗi rỗng, số 0 và chuỗi ký tự `"null"`.
- Với từng trường, ghi **type tag + null marker + độ dài byte + byte dữ liệu**, tránh ghép chuỗi mơ hồ (ví dụ `"ab"+"c"` và `"a"+"bc"`).
- Chốt charset như UTF-8, chuẩn hóa Unicode nếu nghiệp vụ yêu cầu.
- Với `BigDecimal`, thống nhất precision/scale và biểu diễn, tránh sai do `1.0` khác chuỗi `1.00` dù giá trị số tương đương.
- Với timestamp, thống nhất timezone, độ chính xác phần giây và ý nghĩa `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE`.
- Với binary/LOB, hash **byte thật** qua stream; không chuyển mù sang `String`.
- Version hóa thuật toán hash để các lần xuất sau vẫn có thể so sánh.

## 6. Đối soát số hàng và biên phần

Giả sử mỗi phần có số hàng `n_i` và phạm vi cursor theo khóa `id`. Các kiểm tra cơ bản:

\[
N_{\text{export}} = \sum_{i=1}^{k} n_i
\]

Mục tiêu là:

\[
N_{\text{export}} = N_{\text{source snapshot}}
\]

Nhưng còn cần:

1. Mỗi phần có hàng theo **ID tăng nghiêm ngặt**, không có ID trùng bên trong phần.
2. `last_id(part_i) < first_id(part_{i+1})` khi dùng keyset có thứ tự tăng và không cho ID trùng.
3. Không bỏ qua một **trang trả kết quả** do checkpoint sai; cursor của phần tiếp theo phải bắt đầu từ đúng last ID đã xuất bền vững.
4. Mọi hàng đáp ứng predicate nguồn, chẳng hạn `id <= upper_id` và điều kiện tenant/status.
5. Nếu nguồn có các ID không liên tục, **không được coi khoảng trống ID là hàng bị mất**. Đối soát thiếu thực sự phải dựa vào tập khóa/snapshot nguồn.
6. Nếu xuất song song theo các khoảng, chứng minh các khoảng là **rời nhau và bao phủ toàn bộ miền lọc**, kể cả biên.

### Đối soát số hàng từ nguồn **trong cùng snapshot**

~~~sql
SELECT COUNT(*)
FROM source_orders
WHERE id <= ?;
~~~

Với cùng `upper_id`, câu này phải chạy trong **cùng snapshot** với các câu lấy trang nếu muốn dùng làm chứng cứ nhất quán. Chạy `COUNT(*)` sau khi tất cả phần đã xuất, trên một transaction mới, có thể thấy dữ liệu đã đổi nên không còn so sánh cùng tập.

Câu `COUNT(*)` trên bảng rất lớn có thể đắt. Khi cần tiết kiệm chi phí, có thể dùng kiểm tra bằng khóa/manifest, thống kê nguồn có kiểm chứng, hoặc count theo partition, nhưng phải nêu rõ mức bảo đảm thấp hơn nếu không có count chính xác.

### Kiểm tra tổng giá trị nghiệp vụ

Ngoài đếm, với bảng `source_orders` có thể lưu:

~~~sql
SELECT COUNT(*) AS row_count,
       COALESCE(SUM(total_cents), 0) AS total_cents_sum
FROM source_orders
WHERE id <= ?;
~~~

Đối soát tổng `total_cents` giúp phát hiện một số sai lệch giá trị mà count không thấy. Tuy nhiên, **COUNT + SUM vẫn không chứng minh hai tập dữ liệu giống hệt**, vì các thay đổi có thể bù trừ nhau. Nếu yêu cầu độ tin cậy cao, dùng hash logic theo hàng/partition và khóa định danh.

Khi tính tổng trong Java, chọn kiểu tránh tràn số (ví dụ `BigInteger`/`BigDecimal` hoặc kiểm tra `Math.addExact`) phù hợp miền giá trị, không cộng `long` vô điều kiện cho lượng dữ liệu cực lớn.

## 7. Mẫu Java/JDBC: xuất nhiều phần theo một snapshot

Ví dụ dưới đây dùng **Java 17+**, `DataSource`, `PreparedStatement` và `ResultSet`. Nó:

- Lấy một connection từ pool.
- Dùng mức `TRANSACTION_REPEATABLE_READ`, chế độ read-only và manual transaction.
- Lấy cận trên `MAX(id)` và số hàng nguồn `COUNT(*)` **trong cùng snapshot**.
- Lấy từng trang bằng keyset `id > lastId AND id <= upperId ORDER BY id LIMIT ?`.
- Ghi từng tệp CSV UTF-8 tạm; tính SHA-256 trên **byte tệp đầu ra**.
- Chuyển tệp tạm thành tệp phần khi đã ghi thành công.
- Đối soát tổng số hàng; kết thúc transaction đọc và trả metadata các phần cho lớp ghi manifest.

**Phạm vi:** SQL `LIMIT ?` trong ví dụ dành cho **PostgreSQL** (và có thể áp dụng cho nhiều driver MySQL nếu xác minh). Cam kết snapshot ở đây dựa trên cách PostgreSQL triển khai `REPEATABLE READ`, **không chỉ dựa vào tên mức cô lập trong JDBC**.

### Mã triển khai minh họa

~~~java
import javax.sql.DataSource;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;

public final class OrderPartitionExporter {
    public record Part(
        String filename, long firstId, long lastId,
        long rows, long bytes, String sha256
    ) {}

    public record Summary(
        long upperId, long sourceRowCount,
        long exportedRows, List<Part> parts
    ) {}

    private final DataSource source;

    public OrderPartitionExporter(DataSource source) {
        this.source = Objects.requireNonNull(source);
    }

    public Summary exportToRunDirectory(Path directory, int pageSize)
            throws Exception {
        if (pageSize < 1 || pageSize > 10_000) {
            throw new IllegalArgumentException(
                "pageSize phải thuộc khoảng 1..10000"
            );
        }
        // Yêu cầu một thư mục run riêng, chưa có file part cũ.
        // Chỉ một tiến trình ghi vào thư mục này.
        Files.createDirectories(directory);

        try (Connection conn = source.getConnection()) {
            boolean oldAutoCommit = conn.getAutoCommit();
            boolean oldReadOnly = conn.isReadOnly();
            int oldIsolation = conn.getTransactionIsolation();

            // Thiết lập trước câu SQL đầu tiên.
            conn.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            conn.setReadOnly(true);
            conn.setAutoCommit(false);

            boolean transactionEnded = false;
            Throwable failure = null;

            try {
                long upperId = queryLong(
                    conn, "SELECT COALESCE(MAX(id), 0) FROM source_orders"
                );
                long expected = countWithinFence(conn, upperId);

                List<Part> parts = new ArrayList<>();
                long lastId = 0L;
                long total = 0L;
                int partIndex = 1;

                while (true) {
                    Path temp = Files.createTempFile(
                        directory, "part-", ".tmp");
                    MessageDigest sha256 =
                        MessageDigest.getInstance("SHA-256");

                    long rows = 0L;
                    long firstId = -1L;
                    long newLastId = lastId;

                    try {
                        String sql = """
                            SELECT id, status, total_cents
                            FROM source_orders
                            WHERE id > ? AND id <= ?
                            ORDER BY id
                            LIMIT ?
                            """;

                        try (OutputStream raw = Files.newOutputStream(temp);
                             DigestOutputStream hashed =
                                 new DigestOutputStream(raw, sha256);
                             BufferedWriter out = new BufferedWriter(
                                 new OutputStreamWriter(
                                     hashed, StandardCharsets.UTF_8));
                             PreparedStatement ps =
                                 conn.prepareStatement(sql)) {

                            ps.setLong(1, lastId);
                            ps.setLong(2, upperId);
                            ps.setInt(3, pageSize);
                            ps.setFetchSize(pageSize);

                            try (ResultSet rs = ps.executeQuery()) {
                                while (rs.next()) {
                                    long id = rs.getLong("id");
                                    String status = rs.getString("status");
                                    long cents = rs.getLong("total_cents");

                                    if (id <= newLastId || id > upperId) {
                                        throw new SQLException(
                                            "ID không tăng hoặc vượt fence"
                                        );
                                    }
                                    if (rows == 0) {
                                        firstId = id;
                                    }

                                    // CSV: quote mọi giá trị văn bản;
                                    // escape dấu nháy kép thành hai dấu.
                                    out.write(Long.toString(id));
                                    out.write(',');
                                    out.write(quoteCsv(status));
                                    out.write(',');
                                    out.write(Long.toString(cents));
                                    out.write('\n');

                                    newLastId = id;
                                    rows++;
                                }
                            }
                        }

                        if (rows == 0) {
                            Files.deleteIfExists(temp);
                            break;
                        }

                        String digest =
                            HexFormat.of().formatHex(sha256.digest());
                        String filename =
                            String.format("part-%05d.csv", partIndex);
                        Path finalPart = directory.resolve(filename);

                        // Yêu cầu filesystem hỗ trợ atomic rename.
                        // Một run có thư mục riêng tránh overwrite file cũ.
                        Files.move(temp, finalPart,
                            StandardCopyOption.ATOMIC_MOVE);

                        parts.add(new Part(
                            filename, firstId, newLastId, rows,
                            Files.size(finalPart), digest));

                        total = Math.addExact(total, rows);
                        lastId = newLastId;
                        partIndex++;

                        if (rows < pageSize) {
                            break;
                        }
                    } catch (Exception problem) {
                        try {
                            Files.deleteIfExists(temp);
                        } catch (IOException cleanup) {
                            problem.addSuppressed(cleanup);
                        }
                        throw problem;
                    }
                }

                if (total != expected) {
                    throw new IOException(
                        "Lệch số hàng: source=" + expected
                        + ", export=" + total
                    );
                }

                // Chỉ đọc dữ liệu: rollback để đóng snapshot.
                conn.rollback();
                transactionEnded = true;

                // Chưa công bố COMPLETE ở đây: lớp gọi phải
                // lưu/kiểm tra manifest và checksum trên disk.
                return new Summary(
                    upperId, expected, total, List.copyOf(parts));

            } catch (Exception problem) {
                failure = problem;
                try {
                    conn.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackProblem) {
                    problem.addSuppressed(rollbackProblem);
                }
                throw problem;

            } finally {
                if (transactionEnded) {
                    // Chỉ đổi autoCommit khi transaction kết thúc.
                    try {
                        conn.setAutoCommit(oldAutoCommit);
                        conn.setReadOnly(oldReadOnly);
                        conn.setTransactionIsolation(oldIsolation);
                    } catch (SQLException restoreProblem) {
                        if (failure != null) {
                            failure.addSuppressed(restoreProblem);
                        } else {
                            throw restoreProblem;
                        }
                    }
                }
            }
        }
    }

    private static long queryLong(Connection conn, String sql)
            throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Query không trả kết quả");
            }
            return rs.getLong(1);
        }
    }

    private static long countWithinFence(
            Connection conn, long upperId
    ) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT COUNT(*) FROM source_orders WHERE id <= ?")) {
            ps.setLong(1, upperId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("COUNT không trả kết quả");
                }
                return rs.getLong(1);
            }
        }
    }

    private static String quoteCsv(String value) {
        if (value == null) {
            throw new IllegalArgumentException(
                "status của bảng phải NOT NULL");
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
~~~

### Diễn giải mã

1. `DataSource` cung cấp connection; tất cả câu `MAX(id)`, `COUNT(*)` và các trang dùng **cùng connection trong một transaction**.
2. `ORDER BY id` cộng điều kiện `id > lastId` bảo đảm không lấy lại hàng trước trong thứ tự khóa; khóa `id` phải là khóa chính duy nhất và ổn định.
3. `pageSize` giới hạn số hàng của mỗi phần. `setFetchSize(pageSize)` chỉ là **gợi ý cho driver**, không phải bảo đảm về bộ nhớ hoặc số lần đọc tại server.
4. Tệp được ghi qua `DigestOutputStream`; SHA-256 được tính trên **byte đã qua UTF-8/CSV encoding**, không phải hash logic của tuple SQL.
5. Writer đóng và flush trước khi gọi `sha256.digest()`, nên hash bao phủ các byte đã được gửi xuống output stream.
6. Nếu ghi tệp lỗi, đoạn mã cố xóa tệp tạm và rethrow; các tệp phần đã hoàn chỉnh vẫn có thể còn tồn tại để chẩn đoán, **chưa được coi là một bản xuất hoàn tất**.
7. Nếu filesystem **không hỗ trợ `ATOMIC_MOVE`**, thao tác sẽ thất bại; mã không tự thay thế bằng move không nguyên tử vì cần chính sách nhất quán được thiết kế riêng.
8. Mã dùng `rollback()` để kết thúc **transaction chỉ đọc**, không phải để hủy tệp đã ghi. File I/O bên ngoài DBMS **không tham gia transaction JDBC**.
9. `Summary` mới chứa thông tin trong RAM; phải ghi manifest bền vững và kiểm tra lại các file trước khi đánh dấu `COMPLETE`.
10. Nếu rollback/khôi phục trạng thái connection thất bại, không tự coi connection an toàn; việc đóng/trả connection cho pool cần chính sách kiểm soát connection lỗi.

### Những giả định và giới hạn cần nêu rõ

- `source_orders.id` **luôn dương**, không thay đổi và là khóa chính. Vì thế `lastId = 0` hợp lệ để bắt đầu. Nếu khóa có thể âm hoặc là UUID, phải sửa quy tắc cursor.
- Mã không tự xử lý xung đột nhiều tiến trình ghi **cùng thư mục run**. Trong sản phẩm thực tế cần thư mục/namespace duy nhất cho run và kiểm soát quyền ghi.
- `Files.move(..., ATOMIC_MOVE)` yêu cầu hỗ trợ filesystem và cùng ngữ cảnh lưu trữ phù hợp. Atomic rename **không đồng nghĩa đã fsync bền vững xuống đĩa**; với yêu cầu durability cao cần quy trình sync và publication riêng.
- Mã chưa ghi final manifest hoặc phục hồi sau crash; đó là bước cần thiết trước khi công bố dữ liệu cho downstream.
- CSV có thể chứa nội dung cần **chống công thức độc hại** nếu file được mở bằng bảng tính. CSV escaping thông thường chỉ bảo vệ cú pháp phân cách, không tự chống spreadsheet formula injection. Cần chính sách dành cho người nhận tệp.
- Nếu sản phẩm cần khẳng định text UTF-8 được giữ nguyên ngữ nghĩa Unicode, có thể cần kiểm tra encoding/normalization nghiêm ngặt và round-trip; SHA-256 trên file chỉ chứng minh byte file hiện tại khớp digest đã tạo.
- `getLong()` phù hợp với schema `BIGINT NOT NULL`. Nếu các cột cho phép `NULL`, phải dùng `wasNull()` hoặc `getObject()` để không đánh đồng SQL NULL với số 0.

## 8. Làm thế nào công bố tệp và checkpoint an toàn?

Một lượt export thường có ít nhất hai loại trạng thái: **nội dung tệp** và **checkpoint/manifest**. Chúng không cùng transaction với database nguồn.

### Chu kỳ sống của một phần

~~~mermaid
flowchart TD
    A["Chọn run_id và snapshot"] --> B["Tạo tệp part tạm"]
    B --> C["Đọc JDBC và ghi bytes + checksum"]
    C --> D{"Đọc và ghi hoàn tất?"}
    D -- "Không" --> E["Giữ trạng thái FAILED; dọn tệp tạm"]
    D -- "Có" --> F["Đóng và flush tệp"]
    F --> G["Publish part bằng cơ chế an toàn"]
    G --> H["Ghi metadata part + checkpoint bền vững"]
    H --> I{"Còn phần?"}
    I -- "Có" --> B
    I -- "Không" --> J["Đối soát count/range/hash"]
    J --> K{"Tất cả PASS?"}
    K -- "Không" --> E
    K -- "Có" --> L["Publish manifest COMPLETE"]
~~~

Nếu tiến trình chết:

| Thời điểm chết | Tình trạng | Hướng phục hồi |
| --- | --- | --- |
| Trong khi ghi `.tmp` | Tệp có thể chỉ có một phần byte | Không sử dụng tệp tạm; xóa/ghi lại |
| Sau khi đóng tệp, trước rename | Nội dung đã ghi nhưng chưa publish | Kiểm tra rồi publish/ghi lại theo run ID |
| Sau rename, trước cập nhật manifest | Tệp hoàn chỉnh có thể tồn tại nhưng chưa được ghi nhận | Đối soát tên/size/hash và quyết định ghi nhận hoặc tạo lại |
| Sau checkpoint, trước phần kế tiếp | Phần trước đã có trạng thái bền vững | Resume từ đúng cursor/biên đã xác nhận |
| Sau tất cả part, trước manifest `COMPLETE` | Có thể đủ file nhưng chưa công bố | Verify toàn bộ, sau đó mới đánh dấu complete |
| Sau manifest `COMPLETE` | Downstream có thể bắt đầu đọc | Không sửa các part đã publish; tạo run mới nếu cần hiệu chỉnh |

Đừng coi “ghi được `lastId` vào RAM” là checkpoint. Một checkpoint phải **bền vững**, và phải mô tả rõ tệp nào đã xác minh. Nếu dùng database để lưu checkpoint, cập nhật trạng thái phần và điều kiện idempotent phải nằm trong transaction thích hợp.

### Đừng resume bừa vào snapshot đã mất

Nếu lượt xuất ban đầu dùng một transaction snapshot duy nhất mà tiến trình đã chết, **snapshot thường không thể khôi phục chỉ bằng `upperId` và `lastId`**. Resume bằng một connection/transaction mới có thể nhìn dữ liệu đã thay đổi, làm toàn bộ các phần không còn nhất quán.

Có ba lựa chọn tùy mức cam kết:

1. **Chạy lại toàn bộ run** từ snapshot mới; đơn giản và an toàn khi chi phí chấp nhận được.
2. **Xuất từ dữ liệu đã đóng băng/phiên bản hóa**, để mọi lần resume vẫn tham chiếu đúng nguồn bất biến.
3. **Dùng cơ chế snapshot/CDC chuyên biệt** do DBMS hoặc nền tảng dữ liệu cung cấp, có checkpoint được thiết kế cho việc khôi phục.

Việc chỉ dùng `id <= upperId` giúp ràng buộc miền khóa, nhưng **không giữ nguyên giá trị của các bản ghi hoặc bảo vệ khỏi delete** sau khi transaction gốc biến mất.

## 9. Đối soát khi nạp vào hệ thống đích

Sau khi tạo các tệp xuất, công việc chưa kết thúc nếu mục tiêu là chuyển dữ liệu sang CSDL/kho dữ liệu khác. Cần kiểm chứng **tệp được nhận, parse đúng và ghi đủ vào đích**.

Một quy trình thông dụng:

1. Kiểm tra tên tệp, kích thước byte và SHA-256 của từng phần với manifest.
2. Đọc/parse định dạng theo **đúng phiên bản schema**: charset, phân cách CSV, escape, NULL, decimal, timezone, thứ tự cột.
3. Kiểm tra số dòng parse của từng phần; cẩn thận vì một trường CSV có thể chứa dấu xuống dòng bên trong dấu nháy. **Không đếm newline thô thay cho số bản ghi CSV hợp lệ.**
4. Kiểm tra khóa định danh không trùng giữa các phần; dùng `UNIQUE` ở đích nếu phù hợp.
5. Đếm hàng đã load và so với manifest, theo phạm vi run; nếu là upsert, **số hàng bị ảnh hưởng** không nhất thiết bằng số hàng mới.
6. Đối soát tổng hoặc hash logic theo các nhóm khóa/partition để phát hiện lệch giá trị.
7. Chỉ công bố bảng đích cho người dùng khi tất cả kiểm tra cần thiết đã PASS; có thể nạp vào bảng staging rồi chuyển trạng thái/publish atomically khi DBMS hỗ trợ.

### Ví dụ các lớp kiểm tra

~~~text
Nguồn trong snapshot:
  source_count  = 2.400.000
  source_sum    = 18.350.000.000 cents

Manifest cuối:
  part_count    = 120
  sum(part.rows)= 2.400.000
  part hashes   = SHA-256 từng tệp

Hệ thống đích:
  files_verified= 120/120
  parsed_rows   = 2.400.000
  distinct_ids  = 2.400.000
  loaded_rows   = 2.400.000
  target_sum    = 18.350.000.000 cents
~~~

Đây là số liệu minh họa. Nếu còn phát sinh phép biến đổi (lọc, làm tròn, chuẩn hóa dữ liệu), phải ghi rõ **quy tắc transform** và kiểm tra một cách có chủ đích, thay vì mong hai tổng luôn giống nhau.

Ngay cả khi mọi count/sum khớp, bài toán kiểm toán độ chính xác cao có thể yêu cầu hash logic theo hàng/khóa, kiểm tra mẫu và xác nhận toàn vẹn ở tầng lưu trữ.

## 10. Trích xuất song song: tăng throughput nhưng khó đối soát hơn

Nhiều worker có thể xử lý các khoảng khóa riêng:

~~~text
Worker A: [1, 1_000_001)
Worker B: [1_000_001, 2_000_001)
Worker C: [2_000_001, 3_000_001)
~~~

Với SQL:

~~~sql
SELECT id, status, total_cents
FROM source_orders
WHERE id >= ? AND id < ?
ORDER BY id;
~~~

Phân vùng song song có thể giảm thời gian xuất, nhưng cần kiểm chứng:

- Không có phần trùng hoặc bỏ khoảng; biên `[low, high)` rõ ràng.
- Mỗi worker xuất toàn bộ hàng thuộc khoảng của mình, ghi count/hash.
- **Các worker có cùng snapshot hay không?** Mỗi connection thông thường có transaction riêng và có thể thấy nguồn ở những thời điểm khác nhau.
- Connection pool và DBMS chịu được số truy vấn đồng thời; song song quá nhiều có thể tăng lock, I/O contention và timeout.
- Checkpoint/manifest chống hai worker cùng nhận một part gây ghi đè.
- Khi một worker phải retry, nó có thể tái dùng **đúng snapshot/dữ liệu bất biến** hay phải chạy lại cả lượt xuất?

Nếu đòi hỏi tất cả phần nhất quán tại một thời điểm, đừng chỉ chia khoảng rồi mở nhiều connection `REPEATABLE_READ` độc lập. Hãy dùng cơ chế snapshot chung đúng DBMS hoặc một tập nguồn đã version/frozen.

## 11. Truy vấn quy mô lớn: JDBC fetch, timeout và tài nguyên

### `setFetchSize()` là gợi ý

~~~java
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT id, status, total_cents "
        + "FROM source_orders WHERE id > ? AND id <= ? "
        + "ORDER BY id LIMIT ?")) {

    ps.setFetchSize(1_000);
    // Thiết lập tham số, executeQuery rồi đọc rs.next().
}
~~~

`Statement.setFetchSize(int)` hướng dẫn driver số hàng nên lấy theo đợt. Nó **không** đặt giới hạn số hàng trả về, không bảo đảm streaming không dùng nhiều RAM và không thay thế phân trang SQL. Ví dụ pgJDBC có yêu cầu cấu hình và transaction nhất định để dùng cursor-based fetching; driver khác có thể buffer toàn bộ kết quả.

### Kích thước part không chỉ là số hàng

Một phần 1.000 hàng có thể rất nhỏ nếu chỉ có ba cột số, nhưng cực lớn nếu có BLOB/CLOB vài MB mỗi hàng. Cần:

- Tránh `SELECT *`; chỉ lấy cột thực sự cần.
- Xử lý LOB bằng `getBinaryStream()`/`getCharacterStream()` khi phù hợp và driver hỗ trợ.
- Đặt giới hạn số hàng **và** số byte/tệp/tổng tài nguyên.
- Áp dụng backpressure thay vì nạp nhiều phần vào `List` hoặc hàng đợi vô hạn.
- Giới hạn số kết nối và số phần chạy song song.
- Đóng `ResultSet`, `PreparedStatement` và `Connection` bằng `try-with-resources`.

### Timeout và cancellation

`setQueryTimeout(seconds)` giúp yêu cầu giới hạn thời gian thực thi câu SQL; `Statement.cancel()` có thể gửi yêu cầu hủy đang chạy. Tuy nhiên, cancellation và timeout **không bảo đảm rollback hoặc bảo đảm SQL chưa kịp chạy**. Khi lỗi xảy ra, dừng việc công bố phần lỗi, đóng/dọn tài nguyên và xác định transaction còn khả dụng hay không.

Khi các part là **đọc thuần**, retry truy vấn sau lỗi tương đối dễ hơn so với ghi, nhưng chỉ an toàn về tính nhất quán nếu nguồn/snapshot vẫn đúng. Với kết quả commit không rõ ràng ở công đoạn **ghi checkpoint/đích**, phải dùng idempotency và đối soát trước khi chạy lại.

## 12. Tình huống lỗi và cách phản ứng

| Sự cố | Sai lầm thường gặp | Cách xử lý |
| --- | --- | --- |
| Nguồn thêm hàng trong lúc xuất | Cứ coi `MAX(id)` là snapshot | Dùng snapshot hoặc tập nguồn bất biến |
| Nguồn sửa/xóa hàng cũ | Chỉ so count cuối và tưởng nhất quán | Dùng cùng snapshot, hash logic/CDC phù hợp |
| ID thưa, không liên tục | Tăng cursor đúng bằng pageSize | Lấy ID cuối **thực sự đọc** |
| Truy vấn `ORDER BY created_at` có giá trị trùng | Cursor chỉ lưu timestamp | Dùng cursor tổng thứ tự `(created_at, id)` |
| Dùng `LIMIT/OFFSET` với nguồn biến động | Trang bị lệch vị trí | Keyset + snapshot khi cần |
| Tệp ghi được một nửa | Đặt tên cuối ngay từ đầu | Ghi tệp tạm, kiểm tra rồi publish |
| Tệp hoàn tất nhưng manifest chưa ghi | Xóa hoặc ghi đè mù | Đối soát tệp orphan với run/checkpoint |
| Snapshot chết khi xuất dở | Tiếp tục từ `lastId` trên connection mới | Chạy lại hoặc dùng snapshot/frozen data có thể resume |
| Tổng hàng khớp nhưng có trùng ID | Chỉ kiểm COUNT | Kiểm khóa duy nhất và các biên |
| Hash tệp đúng nhưng dữ liệu thiếu | Hash được tính từ chính dữ liệu thiếu | Đối soát với nguồn trong cùng snapshot |
| CSV có dấu xuống dòng trong text | Dùng `wc -l` làm số hàng | Parse đúng theo quy tắc CSV |
| Tên/giá trị Unicode khác chuẩn hóa | Hash logic không nhất quán | Chuẩn hóa charset/Unicode có version |
| Worker song song dùng transaction riêng | Tưởng mỗi `REPEATABLE_READ` là cùng snapshot | Kiểm soát snapshot chung theo DBMS |
| Retry load tạo bản ghi trùng | Không có khóa run/part/row | Khóa `UNIQUE`, upsert/idempotency |
| Xuất nhiều LOB gây tràn heap | Đếm hàng mà không đếm byte | Stream, giới hạn byte và concurrency |

## 13. Bài tập tình huống

**Tình huống A.** Lần xuất gồm hai phần. Part 1 chứa ID `1..100`. Trước khi lấy part 2, một hàng mới được chèn với ID `50`. Dùng `WHERE id > 100` có lấy hàng mới đó không? Có bảo đảm đủ dữ liệu ở thời điểm cuối không?

**Đáp án:** Không lấy hàng mới `id=50`. Keyset tránh lấy lại ID đã đi qua nhưng không đảm bảo tính đầy đủ theo trạng thái cuối nếu nguồn cho phép chèn ID nhỏ hơn cursor. Cần xác định snapshot/mốc nghiệp vụ.

**Tình huống B.** Đếm nguồn và đích đều là 50.000, nhưng đích thiếu `id=700` và chứa hai dòng `id=701`. Tổng count có phát hiện không?

**Đáp án:** Không. Cần kiểm tra khóa duy nhất và đối soát tập ID, cùng các điều kiện phân vùng.

**Tình huống C.** Bạn lấy `MAX(id)` ở đầu export, đặt `upperId`, rồi nguồn cập nhật `status` của hàng có ID nhỏ hơn mốc. `upperId` có ngăn thay đổi đó xuất hiện trong phần sau không?

**Đáp án:** Không. `MAX(id)` chỉ ràng buộc miền ID, không đóng băng giá trị của hàng. Cần snapshot hoặc dữ liệu version/frozen.

**Tình huống D.** Ba worker dùng ba connection riêng, mỗi worker đặt `TRANSACTION_REPEATABLE_READ`. Có chắc cả ba nhìn cùng snapshot không?

**Đáp án:** Không. Mỗi transaction có thể bắt đầu snapshot ở thời điểm khác. Cần cơ chế snapshot chung của DBMS hoặc nguồn đã đóng băng.

**Tình huống E.** Tệp phần có SHA-256 khớp manifest nhưng khi đọc sang hệ đích có ít bản ghi hơn. Những nguyên nhân nào cần kiểm tra?

**Đáp án:** Kiểm tra trình parse CSV/encoding, schema, lỗi nạp/upsert, bản ghi bị lọc/trùng khóa, và đối soát count nguồn cùng snapshot. Hash file không chứng minh parser/load giữ đủ hàng.

**Tình huống F.** Chương trình chết sau khi đã rename `part-00008.csv` nhưng trước khi ghi checkpoint. Có cần ghi lại ngay tệp này không?

**Đáp án:** Không tự động. Kiểm tra run ID, sự tồn tại, kích thước và checksum của part. Nếu nguồn snapshot cũ không còn truy cập được, phải cân nhắc chạy lại toàn run thay vì ghép với dữ liệu mới.

**Tình huống G.** Trong một lần xuất, `id` là `5, 7, 11, 20`. Với pageSize=2, sau phần đầu cursor tiếp theo phải là bao nhiêu?

**Đáp án:** `lastId=7` (ID cuối thực sự xuất), không phải `0+2` hoặc `5+2` theo phép cộng pageSize. Phần hai dùng `WHERE id > 7`.

**Tình huống H.** Một cột có văn bản chứa ký tự xuống dòng bên trong dấu nháy CSV. Đếm ký tự newline có cho số bản ghi chính xác không?

**Đáp án:** Không. Phải parse CSV theo quy tắc escape/quoting. Nên lưu `rows` từ quá trình tạo phần và kiểm tra lại bằng parser ở đích.

**Tình huống I.** Nguồn có 10 triệu hàng, `COUNT(*)` mỗi lần chạy rất tốn tài nguyên. Có thể bỏ hoàn toàn đối soát rồi vẫn tuyên bố “exactly once” không?

**Đáp án:** Không. Có thể thay chiến lược kiểm tra bằng phân vùng bất biến, manifest, kiểm khóa, hash logic, hoặc thống kê/kiểm tra theo nguồn phù hợp, nhưng phải mô tả rõ bằng chứng và mức bảo đảm; thiếu phép chứng minh thì không nên tuyên bố tuyệt đối.

**Tình huống J.** Sau khi xuất 100 phần, cần tải lại phần 40 sang đích nhưng không muốn tạo trùng. Cần dữ liệu gì?

**Đáp án:** Định danh `run_id + part_id`, checksum, khóa dòng duy nhất, trạng thái phần đã load và thao tác idempotent/transaction phù hợp ở đích. Chỉ retry khi biết phần nào đã hoàn tất.

## Ghi nhớ

- **Đối soát trích xuất nhiều phần phải kiểm tra đầy đủ, không trùng, nhất quán và toàn vẹn nội dung**, không chỉ kiểm tra mọi file đã tồn tại.
- **Keyset pagination + khóa duy nhất ổn định** giảm nguy cơ trùng/thiếu do vị trí, nhưng **không tự tạo snapshot**. `MAX(id)` là fence theo ID, không ngăn sửa/xóa/chèn ID cũ.
- **Nếu cần cùng một trạng thái nguồn**, giữ nhiều câu `SELECT` trong snapshot có ngữ nghĩa đã kiểm chứng của DBMS, hoặc xuất từ nguồn bất biến/versioned; các connection độc lập không mặc định chia sẻ snapshot.
- **Manifest là bằng chứng đối soát và khôi phục:** mỗi phần cần biên khóa, số hàng, kích thước, checksum, trạng thái và thông tin phiên bản/snapshot.
- **So sánh số hàng, kiểm khóa không trùng và hash nội dung** bổ trợ cho nhau. Hash file chứng minh byte tệp, còn hash logic và quy tắc canonicalization mới giúp so dữ liệu xuyên định dạng.
- **File I/O và checkpoint không tham gia transaction JDBC của nguồn**. Ghi tệp tạm, publish có kiểm soát, lưu checkpoint bền vững rồi chỉ công bố manifest `COMPLETE` sau khi verify.
- **Đừng resume bằng connection mới như thể snapshot cũ vẫn tồn tại.** Khi lỗi giữa lượt xuất, cần chạy lại hoặc dùng dữ liệu/snapshot có thể phục hồi một cách xác minh được.
