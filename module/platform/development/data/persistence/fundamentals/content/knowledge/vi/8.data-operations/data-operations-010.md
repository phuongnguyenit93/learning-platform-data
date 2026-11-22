# Lựa chọn cập nhật tại kho dữ liệu thay vì đọc rồi ghi lại

Trong ứng dụng Java, một cách cập nhật rất dễ viết là **đọc bản ghi về bộ nhớ, thay đổi giá trị rồi lưu lại**. Cách này trực quan nhưng có thể tạo thêm lượt truy cập cơ sở dữ liệu, mở rộng khoảng thời gian xảy ra tranh chấp và đặc biệt dễ dẫn đến **mất cập nhật (lost update)** nếu nhiều yêu cầu xử lý đồng thời.

Với những thay đổi có thể diễn đạt trực tiếp từ **giá trị hiện đang lưu trong cơ sở dữ liệu**, một lựa chọn thường tốt hơn là **thực hiện cập nhật ngay tại kho dữ liệu**, chẳng hạn `UPDATE ... SET available_qty = available_qty - ? WHERE ...`. Tuy nhiên, cập nhật trực tiếp chỉ an toàn khi câu lệnh phản ánh đúng điều kiện nghiệp vụ, ứng dụng kiểm tra kết quả và ranh giới transaction được xác định rõ.

Bài thuộc chương **Thao tác dữ liệu** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Các nguyên tắc ở đây liên hệ trực tiếp với thiết kế lược đồ và ràng buộc, truy vấn và chỉ mục, giao dịch, mức cô lập và kiểm soát đồng thời, ranh giới persistence trong Java, xử lý lỗi kết nối và retry, bảo mật và hiệu năng.

## 1. Bài toán mở đầu: bán sản phẩm còn ít tồn kho

Giả sử ứng dụng quản lý kho đang lưu:

~~~text
product_id = 101
available_qty = 10
~~~

Hai yêu cầu đến gần như đồng thời:

- Yêu cầu A đặt **3** sản phẩm.
- Yêu cầu B đặt **4** sản phẩm.

Sau khi cả hai yêu cầu thành công, tồn kho phải còn:

`10 - 3 - 4 = 3` sản phẩm.

Nhưng nếu cả hai yêu cầu cùng đọc 10, rồi tự tính trong Java:

~~~text
A: SELECT available_qty   -> 10
B: SELECT available_qty   -> 10
A: 10 - 3 = 7
B: 10 - 4 = 6
A: UPDATE ... SET available_qty = 7
B: UPDATE ... SET available_qty = 6

Kết quả cuối: 6 (sai, đáng lẽ 3).
~~~

Cả hai yêu cầu có thể báo thành công nhưng dữ liệu chỉ phản ánh một phần thay đổi. Một cập nhật đã bị **ghi đè bởi kết quả tính từ bản đọc cũ**.

Cách khác là gửi phép trừ tới database:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 3
WHERE product_id = 101
  AND available_qty >= 3;
~~~

Và cho yêu cầu B:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 4
WHERE product_id = 101
  AND available_qty >= 4;
~~~

Trong PostgreSQL, đối với **cùng một hàng**, các lệnh `UPDATE` tranh chấp khóa ghi hàng; ở mức `READ COMMITTED`, lệnh đến sau có thể chờ và điều kiện cập nhật sẽ được kiểm tra lại trên phiên bản hàng mới phù hợp. Nhờ đó, nếu hai yêu cầu hoàn tất thành công, giá trị cuối là **3**. Nếu không đủ số lượng, lệnh cập nhật có điều kiện sẽ tác động **0 hàng**.

**Chốt ý:** câu lệnh cập nhật tại kho dữ liệu kết hợp **đọc giá trị hiện tại, kiểm tra điều kiện và áp dụng phép thay đổi trên một hàng** trong một thao tác SQL. Điều này thu hẹp khoảng cách giữa việc đọc và sửa so với cách đọc về Java rồi ghi một con số đã tính sẵn.

## 2. Hai cách thực hiện một thay đổi

| Tiêu chí | Đọc về Java rồi ghi lại | Cập nhật trực tiếp tại kho dữ liệu |
| --- | --- | --- |
| Ví dụ | `SELECT qty` → `qty - 3` → `UPDATE SET qty = 7` | `UPDATE SET qty = qty - 3` |
| Số lượt trao đổi thường gặp | Ít nhất một lượt đọc và một lượt ghi | Có thể chỉ một lượt ghi |
| Giá trị dùng để tính | Bản đọc ở một thời điểm trước đó | Giá trị được database dùng tại thời điểm cập nhật |
| Rủi ro đồng thời | Dễ lost update nếu thiếu khóa/version | Giảm lost update kiểu cộng/trừ trên cùng hàng; vẫn phải xét xung đột khác |
| Kiểm tra điều kiện | Có thể bị lỗi TOCTOU nếu kiểm tra trước rồi sửa sau | Có thể đặt điều kiện trong chính `WHERE` |
| Lấy kết quả mới | Đọc lại hoặc dùng cơ chế provider | Có thể dùng `RETURNING` ở PostgreSQL hoặc API tương ứng |
| Phức tạp nghiệp vụ | Dễ biểu diễn logic trong Java | Phù hợp khi logic diễn đạt tốt bằng SQL, biểu thức, điều kiện |
| Ràng buộc transaction | Vẫn cần nếu nghiệp vụ nhiều bước | Vẫn cần nếu nghiệp vụ nhiều bước |

**Cập nhật trực tiếp không có nghĩa bỏ Java hay bỏ repository.** Tầng Java vẫn có trách nhiệm xác thực người dùng, kiểm tra đầu vào, tham số hóa SQL, xác nhận số hàng cập nhật, diễn giải lỗi và quản lý transaction.

### Các kiểu cập nhật trực tiếp thường dùng

~~~sql
-- Tăng bộ đếm theo giá trị hiện tại:
UPDATE counters
SET hits = hits + 1
WHERE id = 5;

-- Chuyển trạng thái chỉ khi đang PENDING:
UPDATE orders
SET status = 'CONFIRMED'
WHERE id = 42 AND status = 'PENDING';

-- Ghi thời điểm cập nhật bằng đồng hồ database:
UPDATE jobs
SET updated_at = CURRENT_TIMESTAMP
WHERE id = 7;

-- Cập nhật có điều kiện theo phiên bản:
UPDATE documents
SET title = 'Bản mới', version = version + 1
WHERE id = 9 AND version = 3;
~~~

Đây là các ví dụ **riêng rẽ**, giả định các bảng/cột tồn tại. Chúng đều yêu cầu ứng dụng xem xét số hàng được cập nhật: `0` có thể là bản ghi không tồn tại, không đúng trạng thái, sai phiên bản hoặc điều kiện không thỏa.

## 3. Schema làm hàng rào cho cập nhật dữ liệu

Trước khi viết lệnh cập nhật, hãy định nghĩa các bất biến có thể được kiểm tra bằng cơ sở dữ liệu.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE inventory (
    product_id    BIGINT PRIMARY KEY,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0),
    version       BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO inventory (product_id, available_qty)
VALUES (101, 10);
~~~

Ba điểm quan trọng:

1. `PRIMARY KEY` bảo đảm mỗi `product_id` có đúng tối đa một hàng trong bảng.
2. `NOT NULL` và `CHECK (available_qty >= 0)` chặn nhiều trường hợp cập nhật sai ở mọi đường ghi đi qua database.
3. Cột `version` dành cho trường hợp cần phát hiện xung đột khi cập nhật theo dữ liệu người dùng đã đọc.

Ràng buộc `CHECK` hữu ích nhưng **không thay thế hoàn toàn điều kiện nghiệp vụ**. Ví dụ:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 20
WHERE product_id = 101;
~~~

Lệnh này sẽ vi phạm `CHECK` nếu số lượng hiện tại chỉ có 10. Database từ chối thay đổi, nhưng lỗi ràng buộc chưa phải phản hồi nghiệp vụ thân thiện như “không đủ hàng”. Câu lệnh có điều kiện `available_qty >= ?` cho phép ứng dụng nhận biết việc đặt hàng thất bại mà không phải cố ý gây lỗi constraint.

Với số lượng lớn hoặc giá trị có thể vượt miền số nguyên, cần chọn kiểu `BIGINT`, thêm kiểm soát giới hạn và quy tắc overflow phù hợp. Không nên dùng các phép cộng/trừ vượt phạm vi mà không có chính sách rõ ràng.

## 4. Dùng điều kiện ngay trong UPDATE để bảo vệ bất biến

Một lệnh cập nhật tồn kho phải trả lời **đổi bao nhiêu** và **khi nào được phép đổi**:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :quantity,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = :product_id
  AND available_qty >= :quantity
RETURNING product_id, available_qty, version;
~~~

Trong ví dụ này:

- `:quantity` là số lượng cần giữ, đã được Java xác minh là **số nguyên dương**.
- `:product_id` là định danh sản phẩm.
- `WHERE` vừa định vị đúng hàng vừa xác minh còn đủ tồn kho.
- `SET available_qty = available_qty - :quantity` sử dụng giá trị database đang quản lý.
- `version = version + 1` báo hiệu hàng đã thay đổi.
- PostgreSQL `RETURNING` trả lại hàng đã cập nhật và giá trị mới.

Nếu `RETURNING` không trả hàng, không được diễn giải rằng cập nhật thành công. Cũng không nên tự kết luận ngay nguyên nhân là “hết hàng”: sản phẩm có thể không tồn tại hoặc người gọi không đủ điều kiện truy cập nếu điều kiện quyền được đặt trong truy vấn. Nếu nghiệp vụ cần thông điệp chính xác hơn, có thể thực hiện truy vấn đọc bổ sung **sau khi cập nhật thất bại** theo chính sách phù hợp, đồng thời tránh rò rỉ thông tin không được phép.

### Vì sao không chỉ kiểm tra trước bằng SELECT?

Cách làm sau có lỗ hổng thời gian:

~~~sql
SELECT available_qty
FROM inventory
WHERE product_id = 101;
-- Java xác minh số lượng đủ.
-- Trong lúc này một giao dịch khác có thể bán hàng.

UPDATE inventory
SET available_qty = :new_qty
WHERE product_id = 101;
~~~

Đây là dạng lỗi **time of check to time of use (TOCTOU)**: điều kiện từng đúng ở lúc đọc nhưng không còn đúng lúc ghi. Kiểm tra trong `WHERE` của lệnh `UPDATE` tránh khoảng cách đó cho **bất biến trên cùng hàng**.

Nếu câu lệnh trả 0 hàng, đây có thể là một kết quả nghiệp vụ hợp lệ, không nhất thiết là exception của JDBC.

## 5. JDBC: cập nhật có điều kiện và kiểm tra số hàng

Đoạn Java sau sử dụng JDBC thuần, không cần ORM. Mục tiêu là **giảm tồn kho một lần** và lấy số lượng sau cập nhật. Giả định `DataSource` đã được cấu hình và bảng `inventory` giống phần trước.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.OptionalInt;
import javax.sql.DataSource;

public final class InventoryRepository {
    private final DataSource dataSource;

    public InventoryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public OptionalInt reserve(long productId, int quantity)
            throws SQLException {
        if (productId <= 0 || quantity <= 0) {
            throw new IllegalArgumentException("ID và số lượng phải dương");
        }

        String sql = """
            UPDATE inventory
            SET available_qty = available_qty - ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
              AND available_qty >= ?
            RETURNING available_qty
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement stmt = connection.prepareStatement(sql)) {
            stmt.setInt(1, quantity);
            stmt.setLong(2, productId);
            stmt.setInt(3, quantity);

            try (ResultSet rows = stmt.executeQuery()) {
                if (!rows.next()) {
                    return OptionalInt.empty();
                }
                return OptionalInt.of(rows.getInt("available_qty"));
            }
        }
    }
}
~~~

Trong ví dụ:

- `PreparedStatement` truyền tham số riêng, không ghép giá trị người dùng vào SQL.
- `OptionalInt.empty()` nghĩa là **không có hàng đáp ứng điều kiện cập nhật**, không phải chắc chắn “sản phẩm đã hết”.
- Phương thức chỉ thao tác **một bảng, một câu lệnh**. Với kết nối JDBC ở chế độ `autoCommit = true` (thường là mặc định khi tạo kết nối), lệnh được xác nhận theo cơ chế tự động; trong ứng dụng thật phải tuân theo cấu hình transaction của pool/framework.
- Nếu còn phải tạo đơn hàng, ghi lịch sử giữ hàng hoặc phát sự kiện, không thể gọi phương thức tự commit này rồi coi cả nghiệp vụ nhiều bước là nguyên tử. Cần đổi ranh giới thành **transaction ở tầng service**.

Với database không hỗ trợ `UPDATE ... RETURNING`, có thể dùng `executeUpdate()`, kiểm tra số hàng bị ảnh hưởng và truy vấn thêm nếu thực sự cần giá trị mới. Cú pháp `RETURNING` trong bài dùng PostgreSQL, không phải SQL chuẩn có thể bê nguyên sang mọi engine.

### Kiểm tra số hàng với executeUpdate()

~~~java
String sql = """
    UPDATE inventory
    SET available_qty = available_qty - ?
    WHERE product_id = ? AND available_qty >= ?
    """;

try (PreparedStatement stmt = connection.prepareStatement(sql)) {
    stmt.setInt(1, quantity);
    stmt.setLong(2, productId);
    stmt.setInt(3, quantity);

    int affected = stmt.executeUpdate();
    if (affected != 1) {
        // Dừng các bước nghiệp vụ tiếp theo; xử lý xung đột/không đủ hàng.
    }
}
~~~

`connection` trong đoạn ngắn này được quản lý bởi tầng gọi. Khi một kỳ vọng là “đúng một hàng được cập nhật”, cần xử lý cả trường hợp 0 và trường hợp ngoài dự kiến; không chỉ gọi `executeUpdate()` rồi bỏ qua kết quả.

## 6. Transaction: cập nhật trực tiếp không thay thế tính nguyên tử nhiều bước

Đặt hàng thường cần nhiều thao tác:

1. Trừ tồn kho.
2. Tạo đơn hàng.
3. Tạo dòng đơn hoặc ghi lịch sử dịch chuyển kho.
4. Xác nhận **cả nhóm** công việc.

Nếu bước trừ kho đã commit nhưng bước tạo đơn thất bại, hệ thống có thể giữ thiếu hàng mà không có đơn tương ứng. Vì vậy, cần **cùng một transaction** khi tất cả dữ liệu nằm trong một database hỗ trợ giao dịch.

Ví dụ SQL minh họa:

~~~sql
BEGIN;

UPDATE inventory
SET available_qty = available_qty - 3,
    version = version + 1
WHERE product_id = 101
  AND available_qty >= 3;
-- Ứng dụng bắt buộc kiểm tra đúng 1 hàng được cập nhật.

INSERT INTO reservations (reservation_id, product_id, quantity)
VALUES ('reserve-2026-001', 101, 3);
-- Giả sử bảng reservations và ràng buộc của nó đã được khai báo.

COMMIT;
~~~

**Không chạy script minh họa mà bỏ qua kiểm tra:** nếu `UPDATE` ảnh hưởng 0 hàng, phải dừng và `ROLLBACK`, không chèn bản ghi reservation và không `COMMIT`. Nếu `INSERT` thất bại, phải rollback cả thao tác trừ tồn kho. Khóa duy nhất cho `reservation_id` và xử lý retry còn cần được thiết kế riêng.

### Quy tắc transaction trong JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // 1. UPDATE inventory ... WHERE available_qty >= ?.
        // 2. Kiểm tra số hàng được cập nhật == 1.
        // 3. INSERT reservation và kiểm tra kết quả.
        // 4. Kiểm tra các bất biến khác trong transaction.
        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
~~~

Đây là **khung transaction**, không phải hàm đặt hàng hoàn chỉnh. Cần triển khai và kiểm tra từng bước. Khi dùng Spring `@Transactional`, Jakarta `@Transactional` hoặc connection pool, để framework quản lý transaction theo hợp đồng của nó; tránh tự tắt `autoCommit` bên trong một transaction đã được quản lý mà không hiểu hệ quả.

**Một câu SQL có tính nguyên tử không có nghĩa cả nghiệp vụ xuyên database hoặc HTTP là nguyên tử.** Nếu cập nhật DB rồi gửi thông điệp đến dịch vụ khác, có thể cần outbox, idempotency hoặc cơ chế xử lý lỗi phân tán tương ứng.

## 7. Khi cần thay một giá trị dựa trên dữ liệu đã đọc: optimistic locking

Không phải thao tác nào cũng chỉ là cộng/trừ. Ví dụ người dùng mở tài liệu, chỉnh sửa tiêu đề và nội dung trong 10 phút, sau đó nhấn Lưu. Nếu người khác đã sửa tài liệu trong khoảng đó, việc ghi đè trực tiếp không kiểm tra sẽ làm mất thay đổi của người kia.

Giải pháp phổ biến là **so sánh và đổi trạng thái nếu phiên bản vẫn đúng (compare-and-set / optimistic locking)**.

Schema minh họa:

~~~sql
CREATE TABLE documents (
    id         BIGINT PRIMARY KEY,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    version    BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0)
);
~~~

Khi API đọc, trả về nội dung và `version = 7`. Khi lưu:

~~~sql
UPDATE documents
SET title = :new_title,
    body = :new_body,
    version = version + 1
WHERE id = :id
  AND version = :expected_version
RETURNING version;
~~~

Nếu có người đã sửa và version tăng từ 7 lên 8, yêu cầu lưu với `expected_version = 7` ảnh hưởng 0 hàng. Ứng dụng trả thông báo xung đột, cho người dùng xem lại/ghép thay đổi hoặc quyết định cập nhật lại theo hợp đồng.

| Nhu cầu | Câu SQL điển hình | Bảo vệ chính |
| --- | --- | --- |
| Tăng bộ đếm từ giá trị hiện tại | `SET hits = hits + 1` | Không tính trên bản đọc cũ |
| Trừ hàng nếu còn đủ | `SET qty = qty - ? WHERE qty >= ?` | Điều kiện nghiệp vụ trên cùng hàng |
| Chuyển trạng thái | `SET state = 'DONE' WHERE state = 'PENDING'` | Không áp lại thay đổi khi trạng thái đã chuyển |
| Lưu chỉnh sửa của người dùng | `SET ..., version = version + 1 WHERE version = ?` | Phát hiện cập nhật xen vào |
| Thay dữ liệu theo điều kiện phức tạp | `UPDATE ... FROM ...` hoặc transaction | Cần phân tích nhiều bảng, khóa và isolation |

**Không nhầm optimistic locking với tự động hợp nhất nội dung.** Nó phát hiện xung đột; ứng dụng vẫn phải quyết định báo lỗi, cho chỉnh sửa lại hay hợp nhất dữ liệu.

### Với JPA/Hibernate

JPA có thể quản lý entity đã tải về và dùng `@Version` để phát hiện xung đột khi flush/commit theo quy tắc provider:

~~~java
@Entity
public class DocumentEntity {
    @Id
    private Long id;

    @Version
    private Long version;

    private String title;
}
~~~

Ví dụ chỉ minh họa thuộc tính ánh xạ; entity hoàn chỉnh còn cần constructor, getter/setter và cấu hình persistence phù hợp. `@Version` là công cụ hữu ích cho **read-modify-write có kiểm soát**, nhưng không đồng nghĩa mọi đường cập nhật dữ liệu đều tự có version check.

Đặc biệt, **bulk update JPQL/SQL** có thể bỏ qua dirty checking và đồng bộ trạng thái của entity đang managed; có thể cần `flush`, `clear` hoặc refresh persistence context theo API/framework. Nếu dùng câu lệnh bulk mà muốn version thay đổi, phải thiết kế cập nhật và kiểm tra version tường minh.

## 8. Cập nhật theo tập hợp thay vì lặp SELECT rồi UPDATE

Đọc một danh sách hàng về Java rồi gọi `UPDATE` riêng cho từng hàng có thể làm tăng lượt mạng và làm transaction dài hơn. SQL có thể áp dụng một phép biến đổi cho **cả tập hợp**.

Ví dụ khóa hết hạn cho các phiếu đặt chỗ:

~~~sql
UPDATE reservations
SET state = 'EXPIRED',
    updated_at = CURRENT_TIMESTAMP
WHERE state = 'HELD'
  AND expires_at < CURRENT_TIMESTAMP;
~~~

Ví dụ tăng phụ cấp cho một tập nhân viên được phép cập nhật:

~~~sql
UPDATE employee_allowances
SET monthly_allowance = monthly_allowance + 100000
WHERE department_id = :department_id
  AND monthly_allowance < :upper_bound;
~~~

Lệnh thứ hai chỉ mang tính minh họa kỹ thuật, chưa thể hiện đầy đủ quy tắc nhân sự hoặc quyền truy cập. Trong nghiệp vụ thật cần chính sách giới hạn và đối soát.

**Ưu điểm** của cập nhật theo tập hợp là database có thể lập kế hoạch, lọc và cập nhật các hàng một cách tập trung, giảm số lượt khứ hồi. Tuy nhiên, bulk update có thể:

- Khóa nhiều hàng trong một transaction.
- Sinh nhiều WAL/redo và I/O.
- Kích hoạt trigger, ràng buộc và tác vụ liên quan.
- Gây tranh chấp hoặc làm tăng độ trễ những truy vấn khác.
- Bỏ qua callback/logic entity của ORM nếu thực hiện trực tiếp ở database.

Với dữ liệu lớn, có thể cần xử lý theo lô đã thiết kế, có chỉ số dừng và cơ chế tiếp tục, chứ không mặc định một `UPDATE` hàng triệu bản ghi luôn là lựa chọn tốt nhất.

## 9. Upsert và cập nhật khi có xung đột khóa

Một trường hợp gần với chủ đề là thao tác “chưa có thì tạo, đã có thì tăng”:

~~~sql
CREATE TABLE daily_metrics (
    tenant_id BIGINT NOT NULL,
    metric_day DATE NOT NULL,
    event_count BIGINT NOT NULL DEFAULT 0 CHECK (event_count >= 0),
    PRIMARY KEY (tenant_id, metric_day)
);
~~~

Nếu cần tăng bộ đếm cho một ngày, PostgreSQL hỗ trợ `INSERT ... ON CONFLICT DO UPDATE`:

~~~sql
INSERT INTO daily_metrics (tenant_id, metric_day, event_count)
VALUES (:tenant_id, :metric_day, 1)
ON CONFLICT (tenant_id, metric_day)
DO UPDATE
SET event_count = daily_metrics.event_count + EXCLUDED.event_count;
~~~

Cơ sở dữ liệu xử lý chèn hoặc cập nhật theo ràng buộc khóa chính. Cách này tránh chuỗi “kiểm tra tồn tại trước → chèn/cập nhật sau” có race condition.

Tuy vậy:

- **Upsert không tự chống gửi yêu cầu trùng.** Nếu event bị gửi lại, bộ đếm có thể tăng lần thứ hai.
- Với quy tắc “một event chỉ đếm một lần”, cần định danh event và ràng buộc duy nhất/idempotency tương ứng.
- Khi cập nhật tổng hợp, sự kiện bị xóa/điều chỉnh cũng cần có đường cập nhật bù hoặc tính lại.
- Cú pháp xung đột khác nhau giữa PostgreSQL, MySQL, SQL Server và các hệ khác; phải kiểm tra semantics của engine.

## 10. Phạm vi áp dụng của cập nhật nguyên tử

Tính nguyên tử của **một lệnh trên một hàng** rất hữu ích, nhưng **không đủ cho mọi ràng buộc xuyên hàng hoặc xuyên bảng**.

### Ví dụ giữ chỗ theo tổng nhiều hàng

Giả sử người dùng chỉ được giữ tối đa 3 chỗ, nhưng hệ thống lưu mỗi lần giữ chỗ bằng một hàng riêng trong `reservations`. Hai transaction có thể cùng đếm 2 chỗ đã giữ, rồi mỗi transaction chèn thêm một hàng. Kết quả có 4 chỗ, dù mỗi thao tác `INSERT` riêng đều hợp lệ.

Đây không còn là trường hợp đơn giản “`SET count = count + 1` trên cùng một hàng”. Có thể cần:

- Một hàng counter có ràng buộc và cập nhật có điều kiện được quản lý nhất quán.
- Khóa hàng đại diện cho người dùng hoặc tài nguyên.
- Isolation phù hợp, ví dụ SERIALIZABLE với cơ chế retry khi có xung đột.
- Ràng buộc unique/exclusion hoặc thiết kế lược đồ diễn đạt bất biến theo cách database có thể áp dụng.

**Không được coi một điều kiện đọc trước ở mức READ COMMITTED là bằng chứng bất biến xuyên nhiều hàng sẽ luôn đúng.** Lựa chọn phụ thuộc engine, mô hình dữ liệu và các đường ghi.

### Ví dụ chuyển tiền giữa hai tài khoản

Một lệnh trừ có điều kiện bảo vệ số dư nguồn:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :from_id
  AND balance >= :amount;
~~~

Nhưng chuyển tiền còn phải **cộng** tài khoản đích và **ghi lịch sử**. Cần transaction bao trùm các thay đổi và kiểm tra đúng một hàng cho từng cập nhật. Nếu chỉ trừ nguồn rồi commit, nghiệp vụ vẫn sai dù lệnh trừ tự nó nguyên tử.

## 11. Retry, idempotency và kết quả không chắc chắn khi commit

Giả sử API giữ 3 sản phẩm bằng `SET qty = qty - 3`. Database đã commit nhưng kết nối ngắt trước khi client nhận phản hồi. Client không biết thao tác đã thành công hay thất bại.

Nếu client thử lại nguyên câu lệnh:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 3
WHERE product_id = 101 AND available_qty >= 3;
~~~

và vẫn còn đủ tồn kho, số lượng có thể bị trừ **lần thứ hai**. Vì vậy, **cập nhật tại kho dữ liệu có thể nguyên tử nhưng không tự idempotent**.

Một phương án là đưa **mã yêu cầu nghiệp vụ ổn định** vào database:

~~~sql
CREATE TABLE inventory_reservations (
    request_id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES inventory(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nguyên tắc luồng xử lý:

1. Client cung cấp hoặc server phát hành `request_id` được dùng lại khi retry.
2. Trong cùng một transaction, kiểm tra/ghi dấu request một cách chống trùng, sau đó trừ tồn kho có điều kiện và tạo kết quả reservation.
3. Nếu request đã được xử lý, đọc lại kết quả cũ; **không trừ hàng thêm lần nữa**.
4. Nếu request ID đã tồn tại nhưng payload khác, xử lý thành lỗi xung đột theo hợp đồng.
5. Khi transaction không xác định được kết quả vì mất kết nối, tra cứu bằng `request_id` trước khi quyết định tiếp tục.

**Cần thiết kế đường đồng thời rõ ràng:** hai transaction cùng nhận một request ID phải được điều phối bằng unique constraint, upsert/lock hoặc cơ chế khác bảo đảm chỉ một transaction thực hiện hiệu ứng nghiệp vụ. Chỉ gọi `SELECT` xem request tồn tại trước khi cập nhật chưa đủ để chống race.

### Retry cho lỗi transaction

Một số lỗi như deadlock hoặc serialization failure có thể được phép thử lại **toàn bộ transaction** theo chính sách giới hạn số lần, backoff và jitter. Với PostgreSQL, SQLSTATE `40001` là serialization failure và `40P01` là deadlock detected. Nhưng không nên tự động retry tất cả lỗi SQL, đặc biệt là lỗi ràng buộc dữ liệu, lỗi phân quyền hoặc lỗi nghiệp vụ không đủ tồn kho.

Với trạng thái commit không rõ, retry phải đi kèm **idempotency**. Tự động chạy lại câu `SET balance = balance - ?` vì “lỗi mạng” có thể tạo hậu quả khó khôi phục.

## 12. Cập nhật tại kho dữ liệu không đồng nghĩa bỏ các quy tắc nghiệp vụ

Đưa một phép cộng/trừ hoặc đổi trạng thái vào SQL là hợp lý khi database có đủ dữ liệu và có thể kiểm tra điều kiện. Nhưng nhiều tác vụ yêu cầu quyết định ở tầng domain.

Ví dụ giá bán có thể phụ thuộc vào chương trình khuyến mại, quy định thuế hoặc quyền của người dùng; không nên nhét toàn bộ nghiệp vụ thay đổi liên tục vào một câu SQL khó hiểu chỉ để giảm một lượt mạng.

Một cách phân chia trách nhiệm:

| Trách nhiệm | Tầng phù hợp |
| --- | --- |
| Xác thực token, kiểm quyền sử dụng API | API/service; có thể tăng cường ở DB bằng chính sách quyền/row security |
| Kiểm tra input (số lượng dương, định dạng) | Service và ràng buộc database tương ứng |
| Thay đổi dựa trên giá trị hiện tại cùng hàng | `UPDATE ... SET x = x + ?` |
| Kiểm tra điều kiện trạng thái cùng hàng | Điều kiện `WHERE` |
| Ràng buộc miền giá trị, khóa, quan hệ | `CHECK`, `NOT NULL`, `PRIMARY KEY`, `FOREIGN KEY` |
| Điều phối nhiều bảng cùng database | Transaction/service với các lệnh SQL có kiểm tra |
| Phát hiện sửa đồng thời trên bản người dùng đã đọc | Version/optimistic locking |
| Quy trình nghiệp vụ phức tạp hoặc xuyên dịch vụ | Domain/service, transaction và cơ chế phối hợp thích hợp |

Một câu SQL đọc được và kiểm chứng được thường tốt hơn hàng trăm dòng Java tải dữ liệu chỉ để thực hiện phép cộng. Ngược lại, một câu SQL quá phức tạp, giấu nhiều side effect hoặc phụ thuộc sâu vào một engine có thể khó kiểm thử và nâng cấp. Cân nhắc theo độ đúng đắn, hiệu năng và khả năng bảo trì.

## 13. Bảo mật và quyền truy cập khi cập nhật trực tiếp

Cập nhật dữ liệu qua câu lệnh SQL không được bỏ qua kiểm tra tenant hoặc quyền sở hữu.

Ví dụ ứng dụng đa tenant:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :quantity
WHERE tenant_id = :tenant_id
  AND product_id = :product_id
  AND available_qty >= :quantity;
~~~

Nếu schema có `PRIMARY KEY (tenant_id, product_id)` hoặc ràng buộc duy nhất theo tenant, truy vấn phải nhất quán với phạm vi định danh. `tenant_id` nên lấy từ danh tính được xác thực hoặc được kiểm tra theo chính sách, **không chỉ tin một tham số HTTP do client tự chọn**.

Những lưu ý:

- Sử dụng `PreparedStatement` hoặc API có parameter binding; không ghép giá trị người dùng thành SQL.
- Cấp quyền database tối thiểu cho tài khoản ứng dụng.
- Nếu hỗ trợ row-level security, kiểm tra chính sách tương tác với quyền của kết nối/service như thế nào.
- Không báo rõ “bản ghi có tồn tại nhưng không thuộc tenant này” cho người không có quyền nếu làm lộ thông tin.
- Ghi audit phù hợp cho thay đổi quan trọng và tránh lưu giá trị nhạy cảm không cần thiết vào log.
- Bulk update theo điều kiện rộng phải có bảo vệ để không vô tình sửa dữ liệu của khách hàng khác.

Tối ưu một lượt database không có giá trị nếu thay đổi có thể vượt phạm vi quyền hoặc làm mất dấu vết cần kiểm toán.

## 14. Đo hiệu năng và ảnh hưởng tới đồng thời

Giảm từ “`SELECT` rồi `UPDATE`” thành một câu lệnh có thể giảm **round trip**, giảm thời gian giữ trạng thái cũ và đơn giản hóa đường code. Nhưng hiệu năng không tự động tốt hơn trong mọi trường hợp.

### Các chỉ số cần đo

| Chỉ số | Điều cần quan sát |
| --- | --- |
| p50/p95/p99 của API ghi | Người dùng mất bao lâu để biết thao tác thành công? |
| Số câu SQL/request | Cập nhật có thực sự loại bỏ truy vấn không cần thiết? |
| Thời gian chờ lock | Nhiều request có tranh chấp một hàng nóng không? |
| Throughput giao dịch thành công | Có xử lý được tải mong muốn ở tỷ lệ lỗi chấp nhận? |
| Deadlock/serialization failure | Có tăng lỗi đồng thời ở tải đỉnh không? |
| CPU/I/O/WAL của database | Ghi theo tập hợp có tăng tải lưu trữ/replication không? |
| Pool wait và transaction duration | Kết nối có bị giữ lâu bởi khóa hay logic ứng dụng? |
| Số request retry và duplicate | Có phát sinh hiệu ứng lặp vì lỗi kết nối không? |

Ví dụ khi mọi lượt xem trang đều tăng một cột `view_count` trên cùng hàng, cập nhật nguyên tử `SET view_count = view_count + 1` giải quyết lost update nhưng có thể biến hàng đó thành **điểm nóng**. Nếu chỉ tiêu đo không cần chính xác tuyệt đối ngay lập tức, có thể xem xét bộ đếm phân mảnh, batch aggregation hoặc event pipeline. Những giải pháp đó thêm độ trễ đồng bộ và nghĩa vụ đối soát; quyết định theo yêu cầu dữ liệu, không chỉ theo RPS.

**Đừng đánh đổi nhất quán để lấy tốc độ** nếu dữ liệu được dùng cho tiền, hàng tồn hoặc giới hạn nghiệp vụ bắt buộc. Phải đo cả tốc độ lẫn tính đúng đắn.

## 15. Thiết kế thử nghiệm đồng thời có ý nghĩa

Để chứng minh một thay đổi chống lost update, thử với nhiều phiên giao dịch độc lập trên **một bản ghi giống nhau**.

### Kịch bản A — đọc rồi ghi lại

Khởi tạo `available_qty = 100`. Cho hai client cùng đọc 100, sau đó mỗi client chuẩn bị cập nhật số lượng giảm 10. Nếu cả hai ghi giá trị 90 mà không có version/lock, kết quả cuối có thể là 90 thay vì 80.

Mục đích của test là tạo đúng interleaving xấu; nếu chỉ chạy một client tuần tự thì sẽ không bộc lộ lỗi.

### Kịch bản B — cập nhật tại kho dữ liệu

Khởi tạo `available_qty = 100`. Cho hai transaction thực hiện:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 10
WHERE product_id = 101 AND available_qty >= 10;
~~~

Sau khi cả hai transaction **commit** và đều cập nhật đúng một hàng, tồn kho kỳ vọng là **80**. Nếu lượng hàng không đủ cho tất cả các yêu cầu, số yêu cầu thành công phải phù hợp với điều kiện và không làm số lượng âm.

### Kịch bản C — đối đầu với retry

Khởi tạo 10 sản phẩm. Gửi hai lần **cùng một request ID** để giữ 3 sản phẩm và giả lập mất kết nối sau commit. Kết quả nghiệp vụ kỳ vọng chỉ có một reservation và tồn kho còn 7, nếu hệ thống đã triển khai idempotency chính xác.

### Kịch bản D — transaction nhiều bước thất bại

Trong một transaction trừ tồn kho rồi chèn reservation, cố ý làm `INSERT` thất bại. Sau rollback, tồn kho phải trở về giá trị ban đầu và không có reservation mới.

### Kịch bản E — sửa tài liệu có version

Hai người cùng mở `version = 7`. Một người lưu thành công lên version 8; người thứ hai gửi update với expected version 7 phải nhận xung đột, không ghi đè nội dung version 8.

Những test có giá trị nhất là **kiểm tra dữ liệu cuối, số hàng cập nhật, trạng thái commit, retry và ràng buộc**; không chỉ khẳng định lệnh SQL trả về mà không ném exception.

## 16. Checklist quyết định khi chọn cách cập nhật

Trước khi đưa một phép sửa dữ liệu vào repository, hãy trả lời:

1. **Giá trị mới có thể tính từ giá trị đang lưu và input hay không?** Nếu có, ưu tiên đánh giá `SET column = column ± ?` thay vì tính trên bản đọc cũ.
2. **Điều kiện hợp lệ có thể đặt ngay trong `WHERE` không?** Ví dụ đủ số lượng, trạng thái đang PENDING, version đúng.
3. **Có ràng buộc database nào bảo vệ bất biến?** `CHECK`, `NOT NULL`, khóa duy nhất, khóa ngoại.
4. **Một hàng hay nhiều hàng/bảng phải đổi cùng nhau?** Xác định transaction và thứ tự cập nhật.
5. **Nếu 0 hàng được cập nhật thì kết quả nghiệp vụ là gì?** Không tồn tại, không đủ điều kiện, xung đột hay chưa được phép?
6. **Nếu hai request đồng thời thì sao?** Kiểm tra isolation, row lock, optimistic version và các bất biến xuyên hàng.
7. **Nếu mạng lỗi đúng lúc commit thì sao?** Có idempotency key và khả năng tra cứu kết quả đã thực hiện chưa?
8. **Có nhiều đường ghi không?** API, batch, ORM dirty checking, script quản trị có cùng tuân thủ bất biến không?
9. **Ranh giới quyền truy cập đã được đưa vào truy vấn chưa?** Tenant, sở hữu bản ghi và chính sách hàng.
10. **Đã đo được tác động thực tế chưa?** Lượt SQL, độ trễ, thông lượng, lock wait và tính đúng đắn dưới tải.

Không phải mọi thao tác đọc-trước-ghi đều sai. Khi cần **đối thoại với người dùng, quyết định domain phức tạp hoặc cập nhật dựa trên một phiên bản nội dung đã xem**, ứng dụng vẫn có thể đọc, xử lý và ghi, miễn là có **version check, lock hoặc transaction** tương ứng.

## 17. Những nhầm lẫn phổ biến

**“Một câu UPDATE luôn đủ bảo đảm cả quy trình nghiệp vụ.”** Không. Một lệnh cập nhật một hàng có thể nguyên tử, nhưng nếu còn tạo đơn, ghi lịch sử hoặc gọi dịch vụ ngoài, cần thiết kế ranh giới khác.

**“Đọc rồi ghi luôn gây lost update.”** Không hẳn. Đọc rồi ghi có thể đúng nếu sử dụng khóa hoặc optimistic version đúng cách và xử lý xung đột. Vấn đề là đọc rồi ghi **không có cơ chế kiểm soát đồng thời**.

**“Cập nhật `SET x = x + 1` có thể retry tùy ý.”** Không. Phép tăng có tác dụng lặp; retry sau trạng thái commit không chắc chắn có thể tăng hai lần.

**“WHERE qty >= ? bảo đảm mọi bất biến của kho.”** Không. Điều kiện bảo vệ phần dữ liệu diễn đạt được trên hàng đó; quy tắc liên quan nhiều hàng, reservations hoặc kho khác cần thiết kế bổ sung.

**“0 hàng cập nhật luôn có nghĩa hết hàng.”** Không. Có thể thiếu ID, sai tenant, không đúng trạng thái hoặc version đã thay đổi.

**“Có CHECK constraint thì không cần WHERE.”** Không. Constraint giúp từ chối trạng thái sai nhưng điều kiện `WHERE` có thể cung cấp hành vi nghiệp vụ có kiểm soát, không phụ thuộc vào cố tình gây exception.

**“Dùng ORM không thể cập nhật trực tiếp.”** Không. ORM/JPA có bulk update hoặc native SQL; cần quản lý persistence context và versioning đúng cách.

**“UPDATE hàng loạt luôn nhanh hơn lặp theo lô.”** Không. Một lệnh cập nhật quá rộng có thể gây khóa lâu, I/O lớn và tăng áp lực WAL. Cần đo và chia lô nếu phù hợp.

## 18. Câu hỏi tự kiểm tra và bài tập áp dụng

**Câu 1.** Tài khoản có số điểm 100; hai yêu cầu cùng cộng 10. Nếu cả hai đọc 100 rồi ghi 110, cuối cùng có thể là bao nhiêu? Làm thế nào để đúng?

**Đáp án:** Có thể là 110 thay vì 120 do lost update. Có thể dùng `UPDATE accounts SET points = points + 10 WHERE id = ?` trên cùng hàng hoặc cơ chế version/lock có xử lý xung đột thích hợp.

**Câu 2.** Một lệnh `UPDATE inventory SET available_qty = available_qty - 5 WHERE product_id = 101 AND available_qty >= 5` ảnh hưởng 0 hàng. Có thể trả “đặt hàng thành công” không?

**Đáp án:** Không. Không có hàng nào thỏa điều kiện; cần dừng thao tác nghiệp vụ và xử lý nguyên nhân theo hợp đồng, không chèn reservation như đã giữ được hàng.

**Câu 3.** Vì sao `@Version` hữu ích khi người dùng chỉnh sửa một trang tài liệu trong vài phút nhưng có thể không cần cho một phép tăng đếm nguyên tử đơn giản?

**Đáp án:** Với tài liệu, ứng dụng cần phát hiện bản người dùng chỉnh sửa đã cũ. Với `SET count = count + 1` trên cùng hàng, database áp phép tăng từ giá trị hiện tại theo cơ chế kiểm soát cập nhật của nó. Dù vậy, vẫn cần version hoặc cơ chế khác nếu còn bất biến phụ thuộc vào nhiều trường hay tác vụ.

**Câu 4.** Tại sao đổi `SELECT ...; INSERT ...` thành upsert vẫn chưa bảo đảm event được xử lý đúng một lần?

**Đáp án:** Upsert tránh xung đột chèn một hàng cùng khóa, nhưng cùng sự kiện được gửi lại vẫn có thể làm bộ đếm tăng lần nữa. Cần event/request ID, ràng buộc duy nhất và giao dịch/idempotency phù hợp.

**Câu 5.** Nếu một request cần trừ hàng rồi tạo reservation, nên commit ngay sau `UPDATE` không?

**Đáp án:** Không nếu hai thao tác cần thành công hoặc hủy cùng nhau. Phải đặt trong cùng transaction, kiểm tra số hàng cập nhật và chỉ commit sau khi đã tạo reservation thành công.

**Câu 6.** Một bulk update JPA chạy thành công nhưng entity đã được load trước đó vẫn giữ giá trị cũ. Nguyên nhân có thể là gì?

**Đáp án:** Bulk update có thể bỏ qua việc đồng bộ state của entity trong persistence context. Cần xem xét flush/clear/refresh theo framework và quản lý versioning để tránh ghi lại giá trị cũ về sau.

**Bài tập A — kho hàng:** Viết repository JDBC giữ `quantity` sản phẩm bằng một `UPDATE ... WHERE qty >= ? RETURNING`, trả về số lượng còn lại hoặc kết quả thất bại. Thử song song 10 request cùng giữ 3 sản phẩm khi kho chỉ có 20; kiểm tra số request thành công và số lượng cuối.

**Bài tập B — chuyển trạng thái:** Đơn hàng được chuyển từ `PENDING` sang `CONFIRMED` chỉ một lần. Thiết kế `UPDATE` có điều kiện, kiểm tra số hàng, cơ chế lưu dấu request để retry và luồng xử lý khi đơn đã bị hủy.

**Bài tập C — đồng bộ transaction:** Tạo bảng reservation có `request_id` duy nhất. Thiết kế thao tác giữ hàng và tạo reservation trong cùng transaction. Giả lập timeout lúc commit rồi gửi lại request cũ; chứng minh không trừ hàng hai lần.

**Bài tập D — tối ưu dưới tải:** So sánh hai cách cập nhật bộ đếm: `SELECT`/`UPDATE` từ Java và `UPDATE SET counter = counter + 1`. Đo p95/p99, số truy vấn, contention và tính đúng đắn. Nếu hàng counter trở thành hot row, đề xuất cách mở rộng và nêu đánh đổi về tính nhất quán.

Khi một thay đổi chỉ cần **biến đổi giá trị hiện tại hoặc chuyển trạng thái theo điều kiện**, hãy cân nhắc đặt phép biến đổi và điều kiện **ngay trong câu SQL**. Điều đó thường giảm lượt đọc và tránh lost update kiểu ghi đè từ bản đọc cũ. Với nghiệp vụ nhiều bước, chỉnh sửa trên bản dữ liệu đã đọc lâu hoặc hệ thống có retry, hãy bổ sung **transaction, version/lock, idempotency và kiểm tra kết quả** để bảo đảm dữ liệu bền vững và đúng đắn.
