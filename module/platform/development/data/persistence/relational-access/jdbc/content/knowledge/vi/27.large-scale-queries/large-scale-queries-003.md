# Thiết kế `ORDER BY` ổn định với khóa phân trang duy nhất trong JDBC

Trong chương **Truy vấn quy mô lớn**, một ứng dụng Java dùng JDBC thường phải trả danh sách đơn hàng, sự kiện hoặc giao dịch thành từng trang. Phân trang giúp giới hạn số hàng mà `PreparedStatement` và `ResultSet` cần chuyển về ứng dụng, nhưng **giới hạn số hàng không đủ để bảo đảm nội dung các trang chính xác**. Nếu câu SQL không có thứ tự xác định cho mọi hàng, người dùng có thể thấy một bản ghi xuất hiện ở hai trang hoặc không xuất hiện ở trang nào, ngay cả khi dữ liệu chưa thay đổi.

Ví dụ, màn hình nhật ký hoạt động sắp xếp theo `created_at DESC`. Nhiều sự kiện có thể cùng thời điểm tạo. DB được phép trả các sự kiện có cùng `created_at` theo thứ tự khác nhau giữa hai lần thực thi. Khi ghép thêm **khóa duy nhất `id`** vào `ORDER BY created_at DESC, id DESC`, ứng dụng xác lập một thứ tự toàn phần (*total order*) trong phạm vi kết quả. Đây là nền tảng để xây dựng cả phân trang `LIMIT/OFFSET` lẫn phân trang theo khóa (*keyset/cursor pagination*).

Bài học tập trung vào cách chọn khóa phân trang, tạo biểu thức `ORDER BY` và điều kiện trang kế tiếp tương ứng, viết SQL tham số hóa bằng JDBC, kiểm tra index và phân biệt **thứ tự ổn định** với **ảnh chụp dữ liệu nhất quán** giữa các request. Các ví dụ dùng `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`; cú pháp `LIMIT` được ghi rõ theo họ DB hỗ trợ, không coi là một cú pháp có thể dùng nguyên xi trên mọi hệ quản trị.

## 1. Vì sao phân trang cần một thứ tự toàn phần?

Giả sử bảng sự kiện có dữ liệu:

| `id` | `created_at` | `summary` |
| ---: | --- | --- |
| 101 | 2026-11-17 08:00:00 | Đăng nhập |
| 102 | 2026-11-17 08:00:00 | Cập nhật hồ sơ |
| 103 | 2026-11-17 08:00:00 | Đổi mật khẩu |
| 104 | 2026-11-17 07:59:00 | Đăng xuất |
| 105 | 2026-11-17 07:58:00 | Đăng nhập |

Câu truy vấn:

```sql
SELECT id, created_at, summary
FROM app_event
ORDER BY created_at DESC
LIMIT 2 OFFSET 0;
```

Chỉ quy định rằng các hàng ở `08:00:00` phải đứng trước các hàng cũ hơn. **Nó không quy định thứ tự giữa `101`, `102` và `103`.** Một lượt truy vấn có thể trả `101, 103`; lần khác, khi lấy trang thứ hai, DB có thể xếp ba hàng cùng timestamp thành `103, 102, 101`, khiến `103` xuất hiện lần nữa hoặc `102` bị bỏ lỡ.

Không có bảo đảm ngầm nào rằng DB phải dùng thứ tự chèn, thứ tự khóa chính, thứ tự trên ổ đĩa hoặc kế hoạch thực thi giống nhau để giải quyết các giá trị hòa nhau. Thêm một index cũng **không** biến `ORDER BY created_at DESC` thành hợp đồng xác định thứ tự giữa các bản ghi có cùng thời gian.

Câu truy vấn chặt chẽ hơn:

```sql
SELECT id, created_at, summary
FROM app_event
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 0;
```

Nếu `id` là khóa chính duy nhất và không `NULL`, các hàng sẽ có thứ tự:

```text
Trang 1: (08:00:00, 103), (08:00:00, 102)
Trang 2: (08:00:00, 101), (07:59:00, 104)
Trang 3: (07:58:00, 105)
```

**Định nghĩa thực hành:** Một `ORDER BY` đủ cho phân trang ổn định khi bộ biểu thức sắp xếp xác định **thứ tự không hòa nhau giữa mọi cặp hàng khác nhau trong kết quả**. Thường chỉ cần thêm khóa chính vào cuối danh sách sắp xếp; với kết quả được nhân hàng bởi `JOIN`, cần một khóa thật sự duy nhất cho **hàng kết quả**, không chỉ khóa của một bảng ở bên trái.

## 2. Chọn khóa phân trang duy nhất và bất biến

Một khóa phân trang tốt thường có ba đặc tính:

1. **Duy nhất trong tập kết quả:** không còn hai hàng hòa nhau sau khi so toàn bộ các cột trong `ORDER BY`.
2. **Có thứ tự so sánh rõ ràng:** các biểu thức có quy tắc `ASC`/`DESC`, `NULL` và collation được xác định.
3. **Ít hoặc không thay đổi khi phân trang:** nếu khóa sắp xếp bị cập nhật giữa hai request, hàng có thể di chuyển qua ranh giới trang.

Ví dụ:

| Nhu cầu hiển thị | `ORDER BY` nên cân nhắc | Lý do |
| --- | --- | --- |
| Sự kiện mới nhất trước | `created_at DESC, id DESC` | `id` phá hòa timestamp trùng |
| Đơn hàng theo tổng tiền tăng | `total_amount ASC, id ASC` | Nhiều đơn có cùng tổng tiền |
| Khách hàng theo tên | `last_name ASC, first_name ASC, id ASC` | Tên không duy nhất; cần quy tắc collation |
| Nhật ký theo chuỗi tự tăng | `sequence_id DESC` | Đã đủ nếu `sequence_id` duy nhất và dùng làm trật tự mong muốn |
| `GROUP BY tenant_id, status` | `COUNT(*) DESC, tenant_id ASC, status ASC` | Khóa duy nhất là **nhóm kết quả**, không phải ID hàng nguồn |

Trường hợp đa tenant: nếu điều kiện `WHERE tenant_id = ?` đã giới hạn đúng một tenant và `id` chỉ duy nhất **bên trong tenant**, `created_at, id` vẫn có thể tạo thứ tự toàn phần trong phạm vi ấy. Nếu truy vấn bỏ điều kiện tenant, cần thêm phần định danh tenant hoặc một khóa duy nhất toàn hệ thống.

**Lưu ý về tính bất biến:** `created_at` nên được coi là thời điểm tạo, không bị sửa trong các thao tác cập nhật thông thường. `updated_at` thuận tiện cho feed “mới thay đổi” nhưng dễ khiến hàng nhảy vị trí giữa các lần lật trang; nếu dùng, ứng dụng phải chấp nhận hoặc xử lý sự dịch chuyển ấy.

## 3. Vì sao chỉ thêm `ORDER BY id` không phải lúc nào cũng đủ?

`ORDER BY id DESC` là ổn định nếu `id` duy nhất, nhưng có thể **không đáp ứng đúng yêu cầu nghiệp vụ**. Người dùng muốn “mới nhất theo `created_at`” chứ không nhất thiết “ID lớn nhất”. Sequence, import dữ liệu, ghi đồng thời và cơ chế cấp ID có thể khiến thứ tự ID không phản ánh hoàn toàn thời gian tạo.

Cách làm đúng là ưu tiên tiêu chí nghiệp vụ **trước**, rồi thêm khóa phá hòa **cuối cùng**:

```sql
-- Mục tiêu: hiển thị sự kiện mới nhất.
ORDER BY created_at DESC, id DESC

-- Mục tiêu khác: hiển thị theo số tiền từ thấp tới cao.
ORDER BY total_amount ASC, id ASC
```

Đừng mặc định “khóa chính duy nhất” luôn là một cột đơn. Bảng có khóa chính ghép `(tenant_id, order_no)` phải dùng tổ hợp bảo đảm duy nhất trong **phạm vi truy vấn thực tế**. Nếu một câu `JOIN` với bảng con tạo nhiều hàng cho cùng `orders.id`, việc thêm `orders.id` vẫn có thể để lại tie: cần thêm khóa dòng con hoặc tổng hợp/loại trùng theo định nghĩa kết quả.

Với `DISTINCT` hoặc `GROUP BY`, khóa phân trang phải là giá trị hiện diện và phân biệt được **các hàng kết quả đã xử lý**, không nhất thiết là khóa chính của bảng gốc. Các DB cũng có quy tắc khác nhau về biểu thức được phép xuất hiện trong `ORDER BY` khi dùng `DISTINCT`.

## 4. `LIMIT/OFFSET`: thứ tự ổn định nhưng trang vẫn có thể trôi

Phân trang dựa vào vị trí thường dùng:

```sql
-- PostgreSQL/MySQL/SQLite và các DB hỗ trợ cú pháp tương ứng.
SELECT id, created_at, summary
FROM app_event
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;
```

Trong JDBC, ba giá trị của `tenant_id`, `LIMIT` và `OFFSET` có thể được bind bằng `PreparedStatement` khi driver/DB hỗ trợ tham số tại các vị trí đó. **Tên cột và hướng `ASC/DESC` không phải giá trị `?`**; nếu cho phép người dùng chọn cách sắp xếp, phải chọn từ danh sách biểu thức đã được ứng dụng cho phép.

Với trang kích thước 20, `OFFSET 200000` thường buộc DB duyệt/bỏ qua nhiều hàng trước khi trả 20 hàng, dù có index hỗ trợ. Mức chi phí phụ thuộc kế hoạch thực thi và DB; index tốt không làm offset sâu luôn rẻ.

Quan trọng hơn, **thứ tự toàn phần không tạo snapshot giữa nhiều request**. Ví dụ:

```text
T0: Dữ liệu theo ORDER BY id DESC: 9, 8, 7, 6, 5, 4
T1: Client lấy LIMIT 2 OFFSET 0  -> 9, 8
T2: Transaction khác INSERT id=10
T3: Client lấy LIMIT 2 OFFSET 2  -> 8, 7
                                          ^
                                      id=8 bị lặp
```

Không có tie ở `ORDER BY`, nhưng chèn hàng mới **dịch mọi vị trí phía sau**. Xóa hàng hoặc thay đổi khóa sắp xếp cũng có thể làm client bỏ lỡ/lặp dữ liệu. Vì vậy, cần tách hai câu hỏi:

- **Deterministic ordering:** trong một trạng thái dữ liệu cụ thể, mọi hàng có vị trí rõ ràng không?
- **Cross-request consistency:** các trang liên tiếp có cùng một snapshot dữ liệu hay không?

Thêm khóa duy nhất giải quyết câu hỏi thứ nhất; câu hỏi thứ hai cần chiến lược phân trang và mức nhất quán phù hợp.

## 5. Keyset/cursor pagination: lấy trang sau bằng bộ khóa cuối

Thay vì “bỏ qua N hàng”, **keyset pagination** lấy các hàng đứng **sau khóa sắp xếp của hàng cuối trang trước**.

Với thứ tự:

```sql
ORDER BY created_at DESC, id DESC
```

Giả sử hàng cuối trang hiện tại là `(created_at = '2026-11-17 08:00:00', id = 102)`. Trang tiếp theo cần thỏa:

```sql
WHERE created_at < ?
   OR (created_at = ? AND id < ?)
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

Điều kiện `<` được dùng vì trang sau nằm ở phía **nhỏ hơn** theo thứ tự giảm dần. Dấu `=` ở nhánh thứ hai cho phép tiến đến các hàng **cùng timestamp nhưng có ID thấp hơn**. Nếu chỉ dùng `created_at < ?`, tất cả hàng cùng thời gian nhưng chưa trả sẽ bị bỏ sót.

Với PostgreSQL và một số DB hỗ trợ so sánh tuple, có thể viết gọn:

```sql
WHERE (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

**Không coi cú pháp tuple là khả chuyển tuyệt đối.** So sánh row-value, quy tắc `NULL` và khả năng dùng index khác nhau giữa DB. Dạng điều kiện mở rộng `OR` phía trên dễ giải thích và kiểm tra hơn; có thể cần tối ưu để đạt kế hoạch thực thi tốt.

### Hình dung ranh giới

```text
Sắp xếp DESC theo (created_at, id)

(08:00, 103)   -> trang 1
(08:00, 102)   -> trang 1, cursor=(08:00,102)
--------------------------------------------- ranh giới
(08:00, 101)   -> trang 2
(07:59, 104)   -> trang 2, cursor=(07:59,104)
--------------------------------------------- ranh giới
(07:58, 105)   -> trang 3
```

Keyset thường hiệu quả hơn offset sâu nếu có index phù hợp và ít cột sắp xếp. Một hàng được chèn **phía trước cursor** sau khi trang 1 đã trả thường không làm lặp một hàng ở trang 2. Tuy nhiên, keyset **không tự tạo snapshot**; hàng bị xóa, bị sửa khóa hoặc được chèn với giá trị khóa cũ vẫn có thể khiến tập kết quả giữa các trang khác đi.

## 6. Ví dụ JDBC hoàn chỉnh: trang sự kiện bằng khóa kép

Giả sử bảng (DDL minh họa theo PostgreSQL):

```sql
CREATE TABLE app_event (
    id         BIGINT PRIMARY KEY,
    tenant_id  BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    summary    VARCHAR(255) NOT NULL
);

CREATE INDEX idx_app_event_page
ON app_event (tenant_id, created_at DESC, id DESC);
```

Ví dụ cố ý dùng `TIMESTAMP` **không có timezone** và `java.time.LocalDateTime` để minh họa tuple cursor; hệ thống lưu thời điểm tuyệt đối nên cân nhắc `TIMESTAMP WITH TIME ZONE`/`OffsetDateTime` theo DB và xác định quy tắc UTC. Khóa `id` duy nhất, `created_at` và `tenant_id` không `NULL`.

Repository Java sau dùng `DataSource`, giới hạn trang từ 1 đến 100 và lấy **thêm một hàng** để biết còn trang tiếp hay không. Các chuỗi SQL được định nghĩa sẵn, không nối input vào câu lệnh:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class EventPager {
    private static final String FIRST_PAGE = """
            SELECT id, created_at, summary
            FROM app_event
            WHERE tenant_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

    private static final String NEXT_PAGE = """
            SELECT id, created_at, summary
            FROM app_event
            WHERE tenant_id = ?
              AND (created_at < ?
                   OR (created_at = ? AND id < ?))
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

    public record EventRow(
            long id, LocalDateTime createdAt, String summary) {}

    // Cursor chỉ là khóa kỹ thuật; token HTTP cần thêm bảo vệ ở tầng API.
    public record Cursor(LocalDateTime createdAt, long id) {}

    public record Page(
            List<EventRow> items, Optional<Cursor> nextCursor) {}

    private final DataSource dataSource;

    public EventPager(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Page fetch(long tenantId, int pageSize, Cursor after)
            throws SQLException {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize phải từ 1 đến 100");
        }
        if (after != null && after.createdAt() == null) {
            throw new IllegalArgumentException("Cursor thiếu createdAt");
        }

        String sql = after == null ? FIRST_PAGE : NEXT_PAGE;
        List<EventRow> items = new ArrayList<>(pageSize);
        boolean hasMore = false;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, tenantId);

            if (after == null) {
                ps.setInt(2, pageSize + 1);
            } else {
                ps.setObject(2, after.createdAt());
                ps.setObject(3, after.createdAt());
                ps.setLong(4, after.id());
                ps.setInt(5, pageSize + 1);
            }

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    if (items.size() == pageSize) {
                        hasMore = true; // Hàng look-ahead, chưa trả cho client.
                        break;
                    }
                    LocalDateTime createdAt =
                            rs.getObject("created_at", LocalDateTime.class);
                    if (createdAt == null) {
                        throw new SQLException("created_at không được NULL");
                    }
                    items.add(new EventRow(
                            rs.getLong("id"),
                            createdAt,
                            rs.getString("summary")));
                }
            }
        }

        Optional<Cursor> next = Optional.empty();
        if (hasMore) {
            EventRow last = items.get(items.size() - 1);
            next = Optional.of(new Cursor(last.createdAt(), last.id()));
        }
        return new Page(List.copyOf(items), next);
    }
}
```

Ví dụ dùng **Java 16+** (`record` và text block); `setObject(LocalDateTime)` và `getObject(..., LocalDateTime.class)` yêu cầu ánh xạ JDBC 4.2 được driver hỗ trợ. SQL `LIMIT ?` chạy với PostgreSQL cùng các driver hỗ trợ cú pháp đó; không dùng nguyên xi cho mọi DB. Một DB khác có thể yêu cầu `FETCH NEXT`, `OFFSET … FETCH` hoặc biến thể riêng.

Điểm cốt lõi:

1. **Giữ nguyên bộ sắp xếp** giữa trang đầu và trang kế: `created_at DESC, id DESC`.
2. **Điều kiện trang kế khớp thứ tự:** `created_at < ? OR (created_at = ? AND id < ?)`.
3. **Bind tất cả giá trị:** tenant, giá trị cursor và page size được truyền qua `PreparedStatement`.
4. **Lấy thêm một hàng:** `LIMIT pageSize + 1` giúp kiểm tra sự tồn tại của trang kế mà không cần `COUNT(*)` cho toàn bảng.
5. **Cursor lấy từ hàng cuối đã trả**, không lấy từ hàng look-ahead; nếu lấy từ hàng look-ahead sẽ vô tình bỏ qua hàng đó ở trang sau.
6. **Đóng kết nối đúng lúc:** `ResultSet` và `PreparedStatement` được đóng trước `Connection`, hạn chế thời gian mượn connection từ pool.

Trong triển khai thật, nên đo thời gian query và kiểm tra `SQLException`/SQLState. Nếu DB/driver không hỗ trợ typed conversion của `LocalDateTime`, cần thiết kế một cách bind/read timestamp tương thích đã kiểm chứng, không tự ghép chuỗi ngày giờ vào SQL.

## 7. Lựa chọn chiều sắp xếp và diễn đạt điều kiện cursor

Nguyên tắc: **một phần tử đứng sau cursor nếu nó nhỏ hơn theo so sánh `DESC` hoặc lớn hơn theo so sánh `ASC`**. Với nhiều cột, điều kiện keyset là so sánh từ trái sang phải (*lexicographic*):

| `ORDER BY` | Điều kiện các hàng sau cursor, với cột không `NULL` |
| --- | --- |
| `id ASC` | `id > :lastId` |
| `id DESC` | `id < :lastId` |
| `created_at DESC, id DESC` | `created_at < :lastTime OR (created_at = :lastTime AND id < :lastId)` |
| `score ASC, id ASC` | `score > :lastScore OR (score = :lastScore AND id > :lastId)` |
| `priority ASC, created_at DESC, id ASC` | `priority > :p OR (priority = :p AND (created_at < :t OR (created_at = :t AND id > :id)))` |

`:lastId` và các tên có dấu hai chấm trong bảng là **ký hiệu giải thích**, không phải named parameter của `java.sql.PreparedStatement` chuẩn. Khi viết JDBC, sử dụng dấu `?` với đúng thứ tự bind; một số framework có named parameter riêng.

Ví dụ trộn chiều `ASC` và `DESC`:

```sql
SELECT id, priority, created_at
FROM task
WHERE priority > ?
   OR (priority = ? AND created_at < ?)
   OR (priority = ? AND created_at = ? AND id > ?)
ORDER BY priority ASC, created_at DESC, id ASC
LIMIT ?;
```

Ở đây phải bind `priority` nhiều lần và `created_at` nhiều lần đúng vị trí dấu `?`. Mỗi hàng mới được xét theo cột ưu tiên trước, sau đó timestamp và cuối cùng ID duy nhất. **Không** dùng điều kiện đơn giản `id > ?` khi thứ tự thực tế còn có `priority` và `created_at`.

### Phân trang lùi

Để tìm trang **trước cursor đầu trang hiện tại** trong thứ tự giảm dần, có thể đảo hướng so sánh và truy vấn theo thứ tự ngược:

```sql
-- Cột không NULL, cursor là khóa của hàng ĐẦU trang hiện tại.
SELECT id, created_at, summary
FROM app_event
WHERE (created_at > ? OR (created_at = ? AND id > ?))
ORDER BY created_at ASC, id ASC
LIMIT ?;
```

Sau khi nhận kết quả, **đảo thứ tự danh sách trong Java** trước khi hiển thị theo `DESC` gốc. Cần thử các trang rìa, trường hợp ít hàng và thêm/xóa đồng thời; không được dùng một cursor cuối trang cho cả hai chiều mà không định nghĩa rõ ý nghĩa.

## 8. `NULL`, collation và kiểu dữ liệu: nguồn bất ổn tinh vi

### Cột sắp xếp cho phép `NULL`

Các phép so sánh `col > ?`, `col < ?` hoặc `col = ?` thường cho kết quả SQL **UNKNOWN** khi một toán hạng là `NULL`. Vì vậy, nếu `created_at` có thể `NULL`, mẫu cursor phần trước sẽ không bao phủ đúng những hàng có giá trị `NULL`.

Các hướng xử lý:

- **Ưu tiên thiết kế cột phân trang `NOT NULL`** nếu phù hợp nghiệp vụ.
- Nếu bắt buộc có `NULL`, quy định rõ **`NULLS FIRST`/`NULLS LAST`** (cú pháp tùy DB), đồng thời xây cả điều kiện cursor bao gồm nhóm `NULL`.
- Có thể chuẩn hóa khóa sắp xếp thành biểu thức như `CASE WHEN col IS NULL THEN ... ELSE ... END` hoặc cột phát sinh có định nghĩa chặt chẽ; phải đảm bảo `ORDER BY`, điều kiện cursor và index dùng cùng ngữ nghĩa.

Không tự ý thay `NULL` bằng một giá trị ngày giờ “rất cũ” nếu giá trị sentinel đó có thể là dữ liệu thật, hoặc nếu DB/index không xử lý biểu thức như dự kiến.

### Chữ và quy tắc so sánh

`ORDER BY last_name ASC, id ASC` chỉ ổn định về tie nếu `id` duy nhất, nhưng **thứ tự chữ có thể khác nhau** giữa DB, locale, collation, quy tắc không phân biệt hoa/thường hoặc phiên bản collation. Nếu cursor chứa giá trị chữ, bảo đảm so sánh cursor dùng **cùng quy tắc collation** như `ORDER BY`. Việc thay collation trong khi còn cursor cũ có thể đổi ranh giới các trang.

### Số dấu phẩy động và thời gian

- Tránh dùng biểu thức số thực dễ sai khác phép so sánh khi có `NaN`, phép làm tròn hoặc chuyển kiểu giữa Java và DB; nếu là tiền, thường chọn `DECIMAL` và Java `BigDecimal`.
- Với timestamp, thống nhất độ chính xác lưu trữ (giây, mili giây, micro giây) và kiểu Java. Nếu chuyển timestamp qua chuỗi cursor, việc cắt bớt phần nano giây có thể khiến điều kiện trang kế sai.
- Không dùng `LocalDateTime` để đại diện cho một thời điểm tuyệt đối mà chưa định nghĩa timezone. Với ứng dụng đa vùng, cần chọn mapping `Instant`/`OffsetDateTime` và kiểu SQL phù hợp DB.

## 9. Concurrent writes: ổn định thứ tự khác snapshot nhất quán

Ngay cả khi `ORDER BY` có khóa duy nhất và dùng keyset, các request HTTP gọi JDBC vào **những thời điểm khác nhau** thường không đọc cùng snapshot của DB.

| Thay đổi trong lúc phân trang | `OFFSET` | Keyset với khóa sắp xếp bất biến |
| --- | --- | --- |
| Chèn bản ghi mới đứng **trước** trang hiện tại | Có thể dịch offset gây trùng/bỏ lỡ | Thường không lặp các hàng đã trả, nhưng hàng mới ở đầu có thể không xuất hiện trong lượt duyệt hiện tại |
| Xóa hàng trước ranh giới | Offset thay đổi nên có thể bỏ sót | Ranh giới giá trị vẫn dùng được cho hàng còn lại |
| Chèn hàng mới đứng **sau** cursor | Có thể làm đổi thứ tự/vị trí | Hàng mới có thể xuất hiện ở trang kế; **không** phải snapshot cố định |
| Sửa `created_at` hoặc khóa sắp xếp | Có thể lặp/bỏ lỡ | **Vẫn có thể** lặp/bỏ lỡ vì hàng di chuyển qua cursor |
| Sửa `summary` nhưng không sửa khóa | Vị trí ổn định, nội dung có thể thay đổi | Vị trí ổn định, nội dung có thể thay đổi |

**Mức cô lập giao dịch** cũng cần hiểu đúng. Với một transaction dài sử dụng snapshot do DB cung cấp, một số mức cô lập/cơ chế MVCC có thể làm các câu SELECT thấy dữ liệu nhất quán. Nhưng **không nên giữ transaction và connection mở xuyên nhiều request HTTP** chỉ để duy trì các trang: cách này giữ tài nguyên của pool, có thể gây áp lực lên DB và dễ lỗi khi người dùng ngừng thao tác.

Nếu bài toán thực sự yêu cầu *một danh sách cố định* cho cả phiên xuất báo cáo, hãy cân nhắc snapshot/materialized result hoặc cơ chế snapshot DB được thiết kế riêng và có thời hạn sử dụng. Một bộ lọc “chỉ lấy `created_at <= thời điểm bắt đầu`” có thể chặn các hàng mới có timestamp lớn hơn, nhưng **không đủ** để cấm chèn bản ghi bị ghi lùi ngày (*backdated*) hay sửa/xóa bản ghi cũ.

Trong feed liên tục không đòi snapshot tuyệt đối, keyset với **khóa sắp xếp bất biến** thường là sự đánh đổi tốt giữa hiệu năng và tính nhất quán vừa đủ.

## 10. Index và hiệu năng: sắp xếp đúng nhưng vẫn phải chạy nhanh

Với truy vấn trong phần 6:

```sql
SELECT id, created_at, summary
FROM app_event
WHERE tenant_id = ?
  AND (created_at < ?
       OR (created_at = ? AND id < ?))
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

Một chỉ mục phù hợp để bắt đầu đánh giá:

```sql
CREATE INDEX idx_app_event_page
ON app_event (tenant_id, created_at DESC, id DESC);
```

`tenant_id` đứng trước vì được lọc bằng đẳng thức, sau đó là các khóa sắp xếp và ranh giới. Đây không phải phép bảo đảm optimizer sẽ chọn index: kích thước bảng, số hàng mỗi tenant, phân phối timestamp, selectivity, cột được SELECT và phiên bản DB vẫn ảnh hưởng kế hoạch.

So sánh hai chiến lược:

| Tiêu chí | Offset pagination | Keyset pagination |
| --- | --- | --- |
| Đi tới trang số N bất kỳ | Dễ diễn đạt `OFFSET (N-1)*pageSize` | Khó nhảy ngẫu nhiên, thường cần đi qua cursor |
| Trang rất sâu | Có thể phải bỏ qua lượng lớn hàng | Có thể tìm tiếp từ ranh giới khóa bằng index |
| Chèn/xóa phía trước trong lúc duyệt | Dễ làm dịch vị trí | Giảm một số lỗi dịch trang nhưng không tạo snapshot |
| Điều kiện SQL | Đơn giản | Phức tạp với nhiều cột, `NULL` và chiều trộn |
| Khả năng phù hợp UI | Danh sách có số trang tuyệt đối | Feed, “Load more”, cuộn vô hạn |

Thử nghiệm bằng `EXPLAIN`/`EXPLAIN ANALYZE` hoặc công cụ kế hoạch thực thi tương ứng với DB, đo **thời gian thực tế**, số hàng scan, sort, bộ nhớ, truy cập đĩa và độ trễ p95/p99 ở offset nông/sâu. Không chỉ đo một câu truy vấn trên bảng vài chục dòng.

`PreparedStatement.setFetchSize(...)` là **gợi ý fetch/transport của driver**, không thay thế `LIMIT` hay điều kiện cursor. `Statement.setMaxRows(...)` có thể giới hạn số hàng trả về ở tầng JDBC nhưng không có cùng ý nghĩa/kế hoạch tối ưu với phân trang giới hạn ngay trong SQL. Cả hai không sửa được `ORDER BY` thiếu khóa duy nhất.

## 11. Thiết kế cursor an toàn cho API thực tế

Trong Java, cursor ở phần 6 chứa `(createdAt, id)`. Khi đưa ra HTTP API, không nên chỉ ghép tùy tiện `created_at|id` rồi tin rằng client luôn gửi lại giá trị hợp lệ.

Một token cursor thường cần chứa:

- Các giá trị khóa của **hàng cuối đã trả** với đủ độ chính xác.
- Phiên bản định dạng cursor để tương thích khi nâng cấp API.
- Thông tin ràng buộc như tenant, filter, kiểu sort và chiều duyệt; hoặc dấu kiểm để xác nhận cursor được dùng đúng với các tham số đang có.
- Thời điểm hết hạn hay phiên bản snapshot nếu chính sách sản phẩm cần.

**Bảo vệ token:** Một chuỗi Base64 không tự bảo đảm tính toàn vẹn hay bảo mật. Nếu cursor được client gửi lại, hãy xác thực trường và kiểu dữ liệu, kiểm tra quyền truy cập tenant ở phía server và cân nhắc ký HMAC/AEAD (hoặc lưu state ở server) để phát hiện token bị sửa. Không dùng cursor làm bằng chứng phân quyền. Không deserialize đối tượng Java tùy ý lấy từ client.

Ví dụ giao thức API ở mức khái niệm:

```text
GET /events?tenant=42&size=20
-> items: [...]
-> nextCursor: "opaque-signed-token"

GET /events?tenant=42&size=20&cursor=opaque-signed-token
-> server kiểm tra token:
   - token hợp lệ và chưa hết hạn?
   - tenant / filter / sort có khớp?
   - created_at / id có đúng kiểu và độ chính xác?
-> bind các giá trị bằng PreparedStatement, không ghép vào SQL.
```

Khi cho phép nhiều lựa chọn sort, dùng **allowlist** để chọn nguyên câu `ORDER BY` và điều kiện keyset tương ứng:

```java
String sql = switch (sortMode) {
    case NEWEST -> SQL_NEWEST;   // ORDER BY created_at DESC, id DESC
    case OLDEST -> SQL_OLDEST;   // ORDER BY created_at ASC, id ASC
};
// Cả SQL_NEWEST và SQL_OLDEST là hằng SQL của ứng dụng.
// Các giá trị của cursor và điều kiện WHERE vẫn bind qua dấu ?.
```

Đây là đoạn minh họa với enum `sortMode` và các hằng SQL đã khai báo ở nơi khác; không đưa chuỗi raw từ request trực tiếp vào `ORDER BY`. Các giá trị kiểu `ASC`/`DESC` và tên cột **không thể bind bằng dấu `?`** của JDBC chuẩn.

## 12. Kiểm thử hồi quy và các lỗi thường gặp

### Ma trận kiểm thử

| Trường hợp | Kết quả cần kiểm tra |
| --- | --- |
| Nhiều hàng cùng `created_at` | Không trùng/bỏ sót hàng chỉ vì tie khi dữ liệu không thay đổi |
| Chỉ một hàng; đúng bằng page size; nhiều hơn page size một hàng | `nextCursor` chỉ xuất hiện khi còn hàng thật |
| Không có hàng; cursor cuối trang | Trả danh sách rỗng hoặc trang cuối đúng; không gọi `last` trên danh sách rỗng |
| Dữ liệu nhiều tenant | Cursor của tenant này không được làm lộ dữ liệu tenant khác |
| Chèn hàng mới ở đầu giữa hai request | So sánh offset và keyset; ghi nhận khác biệt, không đòi snapshot giả |
| Xóa/sửa hàng sau trang đầu | Xác định chính sách hiển thị và trường hợp hàng di chuyển |
| `created_at` có `NULL` (nếu schema cho phép) | Cả `ORDER BY` và điều kiện cursor xử lý thống nhất nhóm `NULL` |
| Dữ liệu ngày giờ có độ chính xác cao | Encode/decode cursor không cắt nano/micro giây ngoài ý muốn |
| Trùng tên khách hàng, collation khác | Thứ tự và điều kiện cursor dùng cùng collation |
| Đổi phiên bản driver/DB | `LIMIT/FETCH`, typed `getObject`, row comparison và kế hoạch index còn hoạt động |
| Bảng hàng triệu dòng, trang 1 và trang rất sâu | Đo scan, sort, thời gian truy vấn và áp lực pool |

### Những lỗi nên phát hiện qua code review

1. **`ORDER BY created_at DESC` không có khóa phá hòa:** thứ tự giữa những hàng trùng thời gian không xác định.
2. **`ORDER BY created_at DESC, id DESC` nhưng cursor chỉ lưu `created_at`:** bỏ sót những hàng cùng thời gian ở trang sau.
3. **Dùng dấu `>` cho trang sau của thứ tự `DESC`:** dễ đọc lại hàng cũ hoặc đi sai hướng.
4. **Dùng `LIMIT/OFFSET` sâu và cho rằng index luôn khắc phục độ trễ:** vẫn có thể tốn chi phí bỏ qua nhiều hàng.
5. **Mặc định offset + khóa duy nhất cho snapshot cố định:** ghi đồng thời vẫn gây dịch trang.
6. **Dùng cột sắp xếp có thể đổi thường xuyên nhưng không xử lý chuyển vị trí:** cả keyset cũng có thể lặp/bỏ lỡ.
7. **Đưa nguyên tên cột hoặc `ASC/DESC` của request vào SQL:** mở đường cho lỗi SQL và injection.
8. **Nhầm số hàng look-ahead với hàng cuối đã trả:** cursor có thể nhảy qua một bản ghi.
9. **Không giới hạn `pageSize`:** request có thể giữ connection lâu, tải nhiều dữ liệu và tăng áp lực heap.
10. **Giữ transaction/connection xuyên nhiều lần click “Trang tiếp”:** làm cạn connection pool và tạo gánh nặng snapshot/khóa.

### Bài tập áp dụng

Cho bảng `orders(id, customer_id, total_amount, created_at)`, hãy thiết kế:

1. Một query hiển thị đơn mới nhất theo `created_at DESC`, dùng `id` làm khóa phá hòa; xây trang đầu và điều kiện keyset của trang tiếp.
2. Một query xếp theo `total_amount ASC`. Nếu hai đơn có cùng số tiền, dùng `id ASC` và viết biểu thức cursor tương ứng.
3. Một index phục vụ `WHERE customer_id = ? ORDER BY created_at DESC, id DESC`. Dùng công cụ `EXPLAIN` để xác minh kế hoạch.
4. Một bài test tạo 100 đơn có **cùng timestamp**, phân trang size 7 và xác nhận khi dữ liệu đứng yên mọi ID xuất hiện **đúng một lần** trong toàn bộ lượt duyệt.
5. Thử chèn/xóa đơn ở giữa hai request. Ghi nhận thứ tự toàn phần giúp điều gì và điều gì vẫn cần chính sách snapshot riêng.

**Ghi nhớ:** Phân trang JDBC đúng cần bắt đầu từ **`ORDER BY` xác định thứ tự toàn phần**: dùng tiêu chí nghiệp vụ trước và thêm một khóa **duy nhất, tốt nhất là bất biến**, để phá hòa. Với dữ liệu lớn, **keyset pagination** sử dụng đầy đủ bộ khóa của hàng cuối đã trả thường phù hợp hơn `OFFSET` sâu và giảm lỗi dịch vị trí khi có thêm dữ liệu. Tuy nhiên, **thứ tự ổn định không đồng nghĩa snapshot nhất quán giữa nhiều request**; phải kiểm soát concurrency, kiểu dữ liệu, bảo vệ cursor, index, khả năng driver và thời gian giữ connection theo yêu cầu thực tế.
