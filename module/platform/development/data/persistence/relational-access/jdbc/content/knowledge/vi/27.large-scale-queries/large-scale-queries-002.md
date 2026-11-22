# Phân trang theo offset và theo khóa trong JDBC

## 1. Vì sao cần phân trang khi truy vấn quy mô lớn?

Trong ứng dụng **JDBC**, một câu `SELECT` có thể trả hàng triệu bản ghi. Nếu đọc tất cả vào `List`, bộ nhớ Java tăng theo lượng dữ liệu, thời gian phản hồi kéo dài và người dùng thường chỉ xem được một phần nhỏ. **Phân trang** giới hạn số hàng được yêu cầu ở mỗi lượt, giúp giao diện hoặc API xử lý dữ liệu từng phần. Hai cách phổ biến:

- **Phân trang theo offset** (*offset pagination*): yêu cầu “bỏ qua N hàng đầu rồi lấy K hàng tiếp theo”, thường dùng `LIMIT ... OFFSET ...`.
- **Phân trang theo khóa** (*keyset/seek pagination*): yêu cầu “lấy K hàng đứng sau bản ghi có khóa sắp xếp X”, thường dùng điều kiện so sánh các cột trong `WHERE`.

Cả hai dùng `Connection`, `PreparedStatement` và `ResultSet` như một câu truy vấn JDBC bình thường. Sự khác nhau nằm ở **hợp đồng thứ tự, cách định vị trang và chi phí SQL** — không nằm ở API Java dùng để đọc hàng.

| Tiêu chí | Offset | Keyset (theo khóa) |
| --- | --- | --- |
| Vị trí trang | Chỉ số trang hoặc số hàng bỏ qua. | Giá trị khóa sắp xếp của hàng cuối trang trước. |
| SQL minh họa | `ORDER BY ... LIMIT ? OFFSET ?`. | `WHERE sort_key < ? ORDER BY ... LIMIT ?`. |
| Nhảy thẳng tới trang 100 | Thuận tiện khi biết kích thước trang. | Không tự nhiên; thường phải đi qua các cursor liên tiếp. |
| Đọc trang rất sâu | DBMS có thể phải duyệt/bỏ qua rất nhiều hàng. | Có thể tìm từ vị trí khóa bằng index phù hợp. |
| Khi hàng mới được thêm/xóa | Dễ bị lặp hoặc bỏ sót giữa hai request. | Thường ổn định hơn với khóa sắp xếp bất biến, nhưng **không phải snapshot tuyệt đối**. |
| UI phù hợp | Bảng quản trị có số trang, nhảy đến trang cụ thể. | News feed, lịch sử giao dịch, API đồng bộ, infinite scroll. |

**Không phải cứ dữ liệu lớn là phải bỏ offset.** Nếu kết quả ít, người dùng cần chọn trang bất kỳ hoặc đang ở một tập dữ liệu gần như bất biến, offset vẫn đơn giản và hiệu quả. Keyset nổi trội khi thường xuyên đọc **các trang kế tiếp** trên tập dữ liệu lớn có index và trật tự xác định.

## 2. Thiết lập ví dụ: danh sách đơn hàng theo thời gian

Giả sử một ứng dụng có bảng PostgreSQL cho nhiều khách hàng doanh nghiệp (`tenant`). Danh sách đơn hàng được lọc theo `tenant_id` và `order_status`, sau đó sắp theo thời điểm tạo mới nhất:

```sql
CREATE TABLE sales_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(12, 2) NOT NULL
);

CREATE INDEX idx_orders_tenant_status_created_id
    ON sales_orders (
        tenant_id, order_status, created_at DESC, order_id DESC
    );
```

Đây là **schema minh họa**; dữ liệu nhạy cảm và xác thực tenant vẫn phải được kiểm soát ở tầng ứng dụng. `created_at` nên được coi là **bất biến** sau khi tạo. `order_id` là khóa chính duy nhất toàn bảng, có tác dụng phá hòa (*tie-breaker*) khi nhiều đơn có cùng `created_at`.

Mọi trang trong bài dùng một thứ tự xác định:

```sql
ORDER BY created_at DESC, order_id DESC
```

Nếu chỉ `ORDER BY created_at DESC`, hai đơn có cùng thời điểm tạo có thể xuất hiện theo thứ tự khác giữa các lần thực thi. Điều đó gây thiếu/trùng hàng ngay cả khi không có ghi dữ liệu mới. **Thêm một khóa duy nhất vào cuối tiêu chí sắp xếp** là điều kiện quan trọng cho cả offset lẫn keyset.

Index `(tenant_id, order_status, created_at DESC, order_id DESC)` phù hợp với bộ lọc bằng và thứ tự này, giúp DBMS có cơ hội đọc dữ liệu theo index mà không phải sắp xếp toàn tập. Nhưng quyết định thực tế vẫn thuộc query planner; cần kiểm chứng bằng kế hoạch thực thi khi dữ liệu đủ lớn.

### Ví dụ thứ tự kết quả

| Vị trí hiển thị | `created_at` (UTC) | `order_id` |
| --- | --- | --- |
| 1 | `2026-10-01T10:00:00Z` | `108` |
| 2 | `2026-10-01T10:00:00Z` | `107` |
| 3 | `2026-10-01T09:00:00Z` | `106` |
| 4 | `2026-10-01T08:00:00Z` | `105` |
| 5 | `2026-10-01T08:00:00Z` | `104` |
| 6 | `2026-10-01T07:00:00Z` | `103` |

Giả sử kích thước trang là 3. Trang đầu chứa `108, 107, 106`; trang tiếp theo chứa `105, 104, 103`. Giá trị `order_id` không nhất thiết liên tục trong dữ liệu thật: điều quyết định vị trí là **cặp** `(created_at, order_id)`, không chỉ ID.

## 3. Phân trang theo offset: `LIMIT` và `OFFSET`

Trong PostgreSQL, một câu SQL với tham số JDBC có thể viết:

```sql
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = ? AND order_status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ? OFFSET ?;
```

Hai tham số cuối:

- `LIMIT`: số hàng tối đa cần lấy.
- `OFFSET`: số hàng đứng trước vị trí bắt đầu mà DBMS phải bỏ qua.

Với `pageIndex` **bắt đầu từ 0** và `pageSize > 0`:

```text
offset = pageIndex × pageSize
pageIndex = 0, pageSize = 3 -> OFFSET 0
pageIndex = 1, pageSize = 3 -> OFFSET 3
pageIndex = 2, pageSize = 3 -> OFFSET 6
```

Nếu giao diện bắt đầu số trang từ **1**, cần chuyển `pageIndex = displayedPage - 1` khi xây query. Không trộn hai quy ước: lỗi off-by-one thường làm mất trang đầu hoặc bỏ sót hàng.

**Ưu điểm:** mã dễ hiểu, dễ dùng trong bảng quản trị, cho phép nhảy trực tiếp tới một số trang. Nếu cần hiển thị “Trang 2/120”, có thể kết hợp truy vấn đếm:

```sql
SELECT COUNT(*)
FROM sales_orders
WHERE tenant_id = ? AND order_status = ?;
```

Nhưng `COUNT(*)` là **truy vấn riêng** với chi phí riêng; không nên mặc định đếm toàn tập dữ liệu sau mỗi request khi số hàng lớn. Kết quả `COUNT(*)` và trang dữ liệu đọc ở hai thời điểm khác nhau cũng có thể không hoàn toàn khớp nếu có ghi đồng thời.

### Vì sao offset lớn có thể chậm?

Với `LIMIT 20 OFFSET 100000`, DBMS thường vẫn cần duyệt hoặc định vị **rất nhiều kết quả đứng trước** để biết nên bỏ qua bao nhiêu hàng. Ngay cả khi dùng index, engine có thể phải quét hơn 100.000 index entries trước khi trả 20 hàng. Chi phí phụ thuộc optimizer, bộ lọc, dữ liệu, index và cache; không thể hứa một công thức thời gian cố định, nhưng về nguyên lý lượng hàng cần bỏ qua thường tăng theo offset.

```text
Index theo (created_at DESC, order_id DESC):
  [hàng 1] [hàng 2] ... [hàng 100000] [hàng 100001] ... [hàng 100020]
  <-------- phần phải bỏ qua -----------> <--- phần cần trả --->
```

Không nên giải quyết vấn đề này bằng việc tăng `pageSize` không giới hạn: nó làm tăng bộ nhớ, số hàng gửi qua mạng và thời gian giữ tài nguyên JDBC.

## 4. Offset khi dữ liệu thay đổi: lặp và bỏ sót hàng

Giả sử trang đầu trả `108, 107, 106`. Trước khi người dùng yêu cầu trang thứ hai, hệ thống thêm một đơn mới có khóa sắp xếp đứng **trước** `108`. Trật tự lúc này có thể thành:

```text
Lần 1: 108, 107, 106 | 105, 104, 103
Thêm:  109, 108, 107, 106 | 105, 104, 103
Lần 2 với OFFSET 3: 106, 105, 104
```

**Đơn 106 bị lặp** vì offset chỉ đếm vị trí hiện tại, không biết người dùng đã xem hàng nào. Nếu một hàng ở đầu danh sách bị xóa trước lần 2, một hàng đáng lẽ nằm ở trang tiếp theo có thể bị **bỏ sót**.

Đây không phải lỗi JDBC, mà là hệ quả của việc phân trang theo **vị trí trên một tập dữ liệu thay đổi**. `ORDER BY` xác định rõ thứ tự tại mỗi lần đọc nhưng không biến các request rời rạc thành một snapshot chung.

Nếu hệ thống yêu cầu bản xuất dữ liệu **không được lặp/thiếu** trong quá trình nhiều trang, cần thiết kế riêng: snapshot/transaction phù hợp, version hoặc một tác vụ xuất dữ liệu có trạng thái. Chỉ đổi offset sang keyset sẽ giải quyết được một số dịch chuyển vị trí, **không giải quyết mọi kiểu cập nhật đồng thời**.

## 5. Keyset pagination: dùng khóa cuối trang làm cursor

Thay vì hỏi “bỏ qua ba hàng”, keyset hỏi “lấy ba hàng **nhỏ hơn cặp khóa** của hàng cuối đã xem trong thứ tự giảm dần”. Với dữ liệu ví dụ, cursor sau trang đầu là:

```text
created_at = 2026-10-01T09:00:00Z
order_id   = 106
```

Câu SQL trang **đầu** chưa cần cursor:

```sql
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = ? AND order_status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Từ trang **tiếp theo**, PostgreSQL hỗ trợ so sánh một hàng gồm nhiều giá trị:

```sql
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = ? AND order_status = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Điều kiện `(created_at, order_id) < (cursorCreatedAt, cursorId)` là so sánh **từ điển**:

1. Những hàng có `created_at` **nhỏ hơn** thời điểm cursor được lấy.
2. Hoặc cùng `created_at` nhưng `order_id` **nhỏ hơn** ID của cursor.

Vì cả hai cột đều sắp xếp **DESC**, các hàng với cặp khóa nhỏ hơn nằm **sau** cursor. Có thể viết điều kiện tương đương, dễ điều chỉnh khi DBMS không hỗ trợ row-value comparison:

```sql
AND (
    created_at < ?
    OR (created_at = ? AND order_id < ?)
)
```

Với biểu thức mở rộng này, JDBC phải bind thời điểm cursor ở **hai** vị trí khác nhau. Không thể bind một tham số rồi mong nó được tái sử dụng tự động cho dấu `?` thứ hai.

**Điều kiện để ví dụ đúng:** hai cột khóa sắp xếp là `NOT NULL`, tuple cuối là duy nhất nhờ `order_id`, cả hai tiêu chí đều DESC. Với sắp xếp trộn ASC/DESC hoặc `NULLS FIRST/LAST`, không được áp dụng máy móc phép so sánh tuple `<`; cần suy ra điều kiện riêng cho từng chiều và quy tắc `NULL`.

### Tránh lỗi “cursor của hàng nhìn trước”

Để biết còn trang tiếp theo, ứng dụng thường truy vấn **`pageSize + 1` hàng**, nhưng chỉ trả `pageSize` hàng cho caller. Cursor phải lấy từ **hàng cuối thực sự trả cho caller**, không phải hàng nhìn trước thứ `pageSize + 1`. Nếu dùng hàng nhìn trước làm cursor, hàng đó sẽ bị bỏ qua vĩnh viễn ở lượt kế tiếp.

Ví dụ: truy vấn lấy `108, 107, 106, 105` với `pageSize=3`. Trả `108,107,106`, đặt cursor tại `106`; hàng `105` chỉ chứng minh `hasNext=true`.

## 6. Offset và keyset đều cần lọc, sắp xếp và giới hạn an toàn

| Yêu cầu | Cách triển khai |
| --- | --- |
| Không lọt dữ liệu tenant khác | Luôn đặt `WHERE tenant_id = ?` lấy từ ngữ cảnh phân quyền đã xác thực; không tin một tenant ID tùy ý từ client. |
| Giữ nguyên bộ lọc qua nhiều trang | Cursor phải gắn với `order_status` và mọi filter khác; đổi filter thì bắt đầu lại từ trang đầu. |
| Không bỏ hòa thứ tự | `ORDER BY created_at DESC, order_id DESC`, cùng cặp khóa trong `WHERE` keyset. |
| Không nhận page size vô hạn | Giới hạn `pageSize` tại API, ví dụ 1–100 theo mục tiêu vận hành. |
| Không nối chuỗi SQL từ đầu vào | Dùng `PreparedStatement` bind giá trị; tên cột/chiều sort phải chọn từ danh sách cho phép. |
| Không gây tràn số khi tính offset | Dùng `long` và `Math.multiplyExact()`, không tính bằng `int` thiếu kiểm tra. |
| Không đưa cursor sai schema vào query | Kiểm tra phiên bản cursor, kiểu dữ liệu, filter, chiều sort và thời hạn sử dụng. |
| Không giữ một kết nối qua nhiều request | Mỗi request mượn/đóng `Connection` đúng phạm vi từ `DataSource`; không dựa vào locator `ResultSet` của request trước. |

Điểm khác biệt quan trọng: **keyset không thể làm việc tốt nếu thiếu index** phù hợp và giá trị cursor đáng tin. Ngược lại, offset cũng cần `ORDER BY` xác định, các filter có index và giới hạn page size để tránh truy vấn nặng.

## 7. Ví dụ Java đầy đủ: repository hỗ trợ cả hai cách phân trang

Ví dụ sau sử dụng **Java 17+**, `DataSource` và PostgreSQL. Giả định schema ở mục 2 đã tồn tại, driver hỗ trợ ánh xạ JDBC 4.2 giữa `TIMESTAMPTZ` và `OffsetDateTime`. Mỗi phương thức mượn connection riêng, dùng `PreparedStatement` để bind tham số, đọc `ResultSet` và đóng tài nguyên qua `try-with-resources`.

API trả tối đa `pageSize` bản ghi; nó đọc thêm **một** hàng để xác định `hasNext` mà không cần `COUNT(*)`.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class OrderPager {
    private static final int MAX_PAGE_SIZE = 100;
    private final DataSource source;

    public OrderPager(DataSource source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    public record OrderRow(
        long orderId, OffsetDateTime createdAt, BigDecimal totalAmount
    ) {}

    public record SeekCursor(OffsetDateTime createdAt, long orderId) {
        public SeekCursor {
            Objects.requireNonNull(createdAt, "createdAt");
            if (orderId <= 0) {
                throw new IllegalArgumentException("orderId phải > 0");
            }
        }
    }

    // nextPageIndex chỉ có giá trị nếu hasNext=true.
    public record OffsetPage(
        List<OrderRow> rows, boolean hasNext, Long nextPageIndex
    ) {}

    // nextCursor chỉ có giá trị nếu hasNext=true.
    public record SeekPage(
        List<OrderRow> rows, boolean hasNext, SeekCursor nextCursor
    ) {}

    public OffsetPage byOffset(
            long tenantId, String status, long pageIndex, int pageSize)
            throws SQLException {
        validateInput(tenantId, status, pageSize);
        if (pageIndex < 0) {
            throw new IllegalArgumentException("pageIndex phải >= 0");
        }

        // Ném ArithmeticException nếu phép nhân vượt giới hạn long.
        long offset = Math.multiplyExact(pageIndex, (long) pageSize);

        String sql = """
            SELECT order_id, created_at, total_amount
            FROM sales_orders
            WHERE tenant_id = ? AND order_status = ?
            ORDER BY created_at DESC, order_id DESC
            LIMIT ? OFFSET ?
            """;

        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setString(2, status);
            statement.setInt(3, pageSize + 1);
            statement.setLong(4, offset);

            try (ResultSet rows = statement.executeQuery()) {
                List<OrderRow> fetched = readRows(rows);
                boolean hasNext = fetched.size() > pageSize;
                List<OrderRow> visible = firstPageSize(fetched, pageSize);
                Long next = hasNext ? Math.addExact(pageIndex, 1L) : null;
                return new OffsetPage(visible, hasNext, next);
            }
        }
    }

    public SeekPage byKeyset(
            long tenantId, String status, SeekCursor cursor, int pageSize)
            throws SQLException {
        validateInput(tenantId, status, pageSize);

        String sql = cursor == null
            ? """
              SELECT order_id, created_at, total_amount
              FROM sales_orders
              WHERE tenant_id = ? AND order_status = ?
              ORDER BY created_at DESC, order_id DESC
              LIMIT ?
              """
            : """
              SELECT order_id, created_at, total_amount
              FROM sales_orders
              WHERE tenant_id = ? AND order_status = ?
                AND (created_at, order_id) < (?, ?)
              ORDER BY created_at DESC, order_id DESC
              LIMIT ?
              """;

        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setString(2, status);

            if (cursor == null) {
                statement.setInt(3, pageSize + 1);
            } else {
                statement.setObject(3, cursor.createdAt());
                statement.setLong(4, cursor.orderId());
                statement.setInt(5, pageSize + 1);
            }

            try (ResultSet rows = statement.executeQuery()) {
                List<OrderRow> fetched = readRows(rows);
                boolean hasNext = fetched.size() > pageSize;
                List<OrderRow> visible = firstPageSize(fetched, pageSize);

                SeekCursor nextCursor = null;
                if (hasNext) {
                    // Cursor của hàng cuối ĐÃ TRẢ, không phải hàng lookahead.
                    OrderRow last = visible.get(visible.size() - 1);
                    nextCursor = new SeekCursor(
                        last.createdAt(), last.orderId());
                }
                return new SeekPage(visible, hasNext, nextCursor);
            }
        }
    }

    private static void validateInput(
            long tenantId, String status, int pageSize) {
        if (tenantId <= 0) {
            throw new IllegalArgumentException("tenantId phải > 0");
        }
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("status không hợp lệ");
        }
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "pageSize phải nằm trong khoảng 1..100");
        }
    }

    private static List<OrderRow> readRows(ResultSet rows)
            throws SQLException {
        List<OrderRow> result = new ArrayList<>();
        while (rows.next()) {
            result.add(new OrderRow(
                rows.getLong("order_id"),
                rows.getObject("created_at", OffsetDateTime.class),
                rows.getBigDecimal("total_amount")
            ));
        }
        return result;
    }

    private static List<OrderRow> firstPageSize(
            List<OrderRow> fetched, int pageSize) {
        int end = Math.min(pageSize, fetched.size());
        return List.copyOf(fetched.subList(0, end));
    }
}
```

### Cách gọi

```java
OrderPager pager = new OrderPager(dataSource);

// Trang offset đầu tiên (pageIndex bắt đầu từ 0):
OrderPager.OffsetPage byNumber =
    pager.byOffset(42L, "PAID", 0L, 20);
System.out.println(byNumber.rows());
System.out.println("Trang tiếp: " + byNumber.nextPageIndex());

// Trang keyset đầu tiên (cursor = null):
OrderPager.SeekPage first = pager.byKeyset(42L, "PAID", null, 20);
System.out.println(first.rows());

if (first.hasNext()) {
    OrderPager.SeekPage second =
        pager.byKeyset(42L, "PAID", first.nextCursor(), 20);
    System.out.println(second.rows());
}
```

Trong ví dụ, `tenantId=42` chỉ minh họa; ứng dụng nhiều tenant phải lấy nó từ **ngữ cảnh đã xác thực** thay vì tin một tham số tùy ý của client. `status` cũng cần được kiểm tra theo enum hoặc tập giá trị nghiệp vụ được phép. SQL vẫn dùng placeholder nên nội dung `status` không được ghép vào câu lệnh.

### Giải thích các lựa chọn cài đặt

- `Math.multiplyExact()` tránh **tràn số âm thầm** khi tính offset lớn. Tầng API nên chuyển `ArithmeticException` thành lỗi đầu vào phù hợp.
- `pageSize` bị chặn ở 100 để giới hạn bộ nhớ và chi phí đọc ở mỗi lần gọi; đây là con số minh họa, không phải mức tối ưu chung.
- `LIMIT pageSize + 1` giúp xác định còn dữ liệu để đọc tiếp mà không cần `COUNT(*)`. Phần tử nhìn trước không được trả và không được dùng làm cursor.
- `SeekCursor` giữ **hai** thành phần khóa sắp xếp. Chỉ sử dụng `order_id` làm cursor là sai khi `ORDER BY` ưu tiên `created_at`.
- Các lớp kết quả chứa danh sách bất biến tạo bằng `List.copyOf()`; không giữ `ResultSet` hoặc `Connection` sống sau khi phương thức hoàn tất.
- `OffsetDateTime` dựa vào mapping JDBC 4.2 cho `TIMESTAMPTZ`. Với driver khác, cần kiểm chứng `getObject(..., OffsetDateTime.class)` và `setObject(...)`; quy tắc thời gian không được phép làm mất độ chính xác cần thiết của cursor.
- Cả hai truy vấn dùng **cùng filter và ORDER BY**. Khi thay đổi status hay thứ tự, phải bắt đầu một chuỗi keyset mới.

### Điểm giới hạn của ví dụ

`SeekCursor` ở đây là **giá trị Java nội bộ**, chưa phải token cursor an toàn để gửi trực tiếp tới client. Với API công khai cần thiết kế mã hóa, xác thực và kiểm tra cursor như mục 9. Ví dụ cũng giả định `created_at` và `order_id` **không bị cập nhật** sau khi tạo, các cột không `NULL`, và mỗi request tự có connection. Nó không hứa các request ở những thời điểm khác nhau nhìn cùng snapshot dữ liệu.

## 8. Thiết kế API: tổng số trang hay `nextCursor`?

Với offset, request/response có thể có dạng:

```json
{
  "request": {"page": 1, "size": 20, "status": "PAID"},
  "response": {
    "items": ["... tối đa 20 bản ghi ..."],
    "hasNext": true,
    "nextPage": 2
  }
}
```

Đây là **minh họa cấu trúc**, không phải dữ liệu thật. Ví dụ API dùng số trang **1-based** nên tầng controller phải đổi thành `pageIndex=page-1` trước khi gọi `OrderPager.byOffset()`.

Với keyset, API công khai nên cung cấp một cursor gắn với kết quả của lượt trước:

```json
{
  "request": {"size": 20, "status": "PAID", "cursor": null},
  "response": {
    "items": ["... tối đa 20 bản ghi ..."],
    "hasNext": true,
    "nextCursor": "<opaque-token>"
  }
}
```

Cursor không phải số trang, và không thể mặc định tạo cursor cho trang thứ 500 nếu chưa biết khóa bắt đầu của trang đó. Với màn hình vô hạn cuộn xuống, điều này thường phù hợp; với bảng quản trị cần nhảy tới trang bất kỳ, offset có thể trực quan hơn.

**Tổng số trang** thường đòi hỏi `COUNT(*)` hoặc một bộ đếm riêng được cập nhật. Với keyset, phần lớn API chỉ cần `hasNext` và `nextCursor`; số trang tổng không phải một khái niệm tự nhiên. Nếu sản phẩm bắt buộc hiển thị tổng số, phải chấp nhận chi phí đếm, độ trễ cập nhật hoặc quy tắc nhất quán được mô tả riêng.

## 9. Cursor công khai: không chỉ là Base64 của khóa

Trong nội bộ, cursor có thể là record `(createdAt, orderId)`. Nhưng khi gửi ra HTTP, client có thể sửa, dùng lại hoặc ghép cursor của một bộ lọc khác. Một token có thể mang:

| Trường | Mục đích |
| --- | --- |
| `version` | Xác định định dạng cursor để nâng cấp có kiểm soát. |
| `createdAt` và `orderId` | Vị trí hàng cuối đã trả theo `ORDER BY`. |
| `sort`/`direction` | Bảo đảm phép so sánh cursor khớp thứ tự hiện hành. |
| `status` và các filter được chuẩn hóa | Chặn việc dùng cursor của một tập kết quả cho tập khác. |
| `tenant` hoặc định danh phạm vi dữ liệu | Ràng buộc cursor với phạm vi đã được phép, **không thay kiểm tra phân quyền**. |
| `issuedAt`/`expiresAt` | Giới hạn thời hạn dùng cursor khi chính sách yêu cầu. |

Không chỉ gọi `Base64.getUrlEncoder()` lên JSON rồi coi đó là bảo mật: Base64 là **mã hóa biểu diễn**, không chống sửa nội dung. Nếu cần tin rằng cursor chưa bị thay đổi, hãy ký bằng **HMAC** với khóa bí mật do server giữ, hoặc dùng token được xác thực tương đương. Khi nhận lại, cần xác minh chữ ký, phiên bản, hạn sử dụng, kiểu dữ liệu, chiều sort và các filter **trước khi bind vào `PreparedStatement`**.

Với dữ liệu nhạy cảm, **ký token không che nội dung**: có thể cần mã hóa hoặc không đưa thông tin nhạy cảm vào cursor. Luôn giới hạn độ dài token, xử lý trường hợp parse hỏng và trả lỗi đầu vào rõ ràng thay vì ném tràn stack trace. **Không cho cursor tự quyết định tenant được truy cập**: tenant phải tiếp tục được lấy từ danh tính đã xác thực và đối chiếu với token.

Cursor theo thời điểm cần được serialize đủ độ chính xác. Ví dụ, nếu DB lưu microsecond nhưng API làm tròn `created_at` về giây, nhiều hàng có thể rơi vào một mốc thời gian khác so với điều kiện SQL. Hãy dùng định dạng ISO-8601 có đủ phần thập phân hoặc encode kiểu dữ liệu thời gian được chuẩn hóa; thử nghiệm khứ hồi trên **driver thật**. `orderId` cũng cần bảo toàn đủ phạm vi của `BIGINT` — tránh làm tròn số nguyên 64-bit khi client dùng JavaScript Number.

## 10. Dữ liệu thay đổi đồng thời: keyset giải quyết được gì?

Keyset giúp tránh hiện tượng **dịch vị trí offset** khi có hàng mới chen vào **trước cursor**. Ví dụ, sau khi trang đầu kết thúc ở `106`, nếu đơn `109` được thêm ở đầu danh sách, câu SQL với điều kiện `(created_at, order_id) < (createdAt106, 106)` vẫn lấy các đơn **đứng sau 106**, không lặp lại 106.

Tuy nhiên, một số tình huống vẫn thay đổi kết quả:

- **Xóa hàng chưa xem:** hàng bị xóa sẽ không xuất hiện ở trang sau. Keyset không giữ snapshot của các hàng đã biến mất.
- **Thay đổi `order_status`:** một đơn vừa chuyển từ `PENDING` sang `PAID` có thể gia nhập tập lọc giữa hai lần đọc; đơn chuyển ngược lại có thể biến mất.
- **Thay đổi `created_at`:** nếu cột sắp xếp bị sửa, hàng có thể di chuyển qua ranh giới cursor, dẫn tới lặp hoặc bỏ sót. Nên dùng khóa sắp xếp **bất biến** khi thiết kế feed.
- **Thêm hàng với thời điểm cũ:** nếu backfill dữ liệu có `created_at` nhỏ hơn cursor hiện tại, hàng mới có thể xuất hiện ở các trang tiếp theo. Keyset không mặc định “đóng băng” tập kết quả.
- **Đồng thời nhiều cập nhật:** nếu sản phẩm cần bản xuất dữ liệu chính xác tại một thời điểm, **nhiều request độc lập ở READ COMMITTED không tạo thành một snapshot chung**.

### Có thể giới hạn phạm vi bằng một mốc trên cùng

Một giải pháp thường dùng cho feed là thêm một **high-water mark** (ví dụ khóa của hàng đầu tại lúc bắt đầu) và áp dụng ràng buộc:

```sql
WHERE tenant_id = ? AND order_status = ?
  AND (created_at, order_id) <= (?, ?)   -- mốc trên cùng
  AND (created_at, order_id) <  (?, ?)   -- cursor vị trí hiện tại
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Mốc trên cùng giúp loại những đơn mới có khóa sắp xếp **cao hơn** mốc đã chốt. Nhưng **không** ngăn hàng mới có khóa thấp hơn hoặc các thay đổi `status`/xóa/sửa dữ liệu. Vì thế, high-water mark chỉ là một **giới hạn của phạm vi duyệt**, không phải snapshot transaction hoàn chỉnh.

Khi thực sự cần cùng snapshot qua nhiều trang, có thể xem xét một transaction có mức cô lập phù hợp (chẳng hạn cơ chế snapshot/REPEATABLE READ của DBMS) hoặc một tác vụ export/materialized result lưu trạng thái. **Giữ một transaction mở qua nhiều request HTTP** thường có rủi ro giữ tài nguyên, làm MVCC khó thu gom phiên bản cũ và gây timeout. Hãy cân nhắc quy trình xuất nền hoặc chụp tập khóa ở tầng database thay vì mặc định giữ connection lâu.

## 11. Index và phép đo hiệu năng

Trong schema ví dụ, cả hai kiểu truy vấn dùng filter bằng:

```sql
WHERE tenant_id = ? AND order_status = ?
```

và thứ tự:

```sql
ORDER BY created_at DESC, order_id DESC
```

Vì vậy một B-tree index bắt đầu bằng `(tenant_id, order_status)` rồi tới `(created_at DESC, order_id DESC)` có thể phục vụ **lọc + thứ tự + seek**. Với keyset, nếu DBMS sử dụng index phù hợp, nó có thể bắt đầu gần vị trí cursor thay vì bỏ qua hàng chục nghìn kết quả trước đó.

Đối với PostgreSQL, có thể khảo sát kế hoạch với dữ liệu thử nghiệm:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = 42 AND order_status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Đối chiếu với keyset, thay các giá trị cursor bằng một mốc thật:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = 42 AND order_status = 'PAID'
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-10-01 09:00:00+00', 106)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

**Đây chỉ là câu SQL để đo trên dữ liệu kiểm thử, không phải benchmark có kết quả được bảo đảm.** `EXPLAIN ANALYZE` thực thi câu SELECT để đo thời gian; hãy dùng môi trường, quyền và tải phù hợp. Quan sát các điểm như Index Scan/Bitmap Scan/Seq Scan, Sort, số hàng thực sự được đọc, buffer hits/reads và thời gian thực tế. Đừng kết luận keyset nhanh hơn chỉ vì câu SQL ngắn hơn; nếu filter không có index hoặc truy vấn không chọn lọc, DBMS vẫn có thể quét nhiều dữ liệu.

Các phép đo có ích:

| Phép đo | Cần so sánh |
| --- | --- |
| Độ trễ trang 1, trang 100, trang 10.000 | Offset tăng có làm thời gian xấu đi? Keyset giữ ổn định hơn khi có index? |
| `rows examined` và `BUFFERS` | DBMS phải đọc/bỏ qua bao nhiêu dữ liệu trước khi trả một trang? |
| CPU, bộ nhớ, I/O phía DB | Query nào gây áp lực tài nguyên khi nhiều request chạy đồng thời? |
| Độ trễ từ HTTP đến JDBC | Bao gồm chờ mượn connection, query, mapping `ResultSet` và serialize. |
| Tỷ lệ trang rỗng/`hasNext` không chính xác khi dữ liệu đổi | Hành vi UX trong điều kiện concurrency thực tế. |

### `setFetchSize()` không thay thế phân trang SQL

`Statement.setFetchSize(int)` là **gợi ý cho driver** về số hàng cần lấy mỗi lượt khi xử lý `ResultSet`, không phải tương đương `LIMIT`. Một `SELECT` không có `LIMIT` vẫn có thể trả về hàng triệu hàng, dù driver truyền chúng theo từng đợt. Để API trả một trang có kích thước giới hạn, hãy **giới hạn tại SQL**.

Với PostgreSQL, cơ chế server-side cursor/streaming theo fetch size có thể yêu cầu điều kiện về `autoCommit` và kiểu `ResultSet`; đây là một bài toán **streaming** khác với API lấy từng trang rồi đóng connection. Không trộn fetch size, page size, batch size và pool size thành một tham số chung.

## 12. Kiểm thử tính đúng đắn và các trường hợp ranh giới

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Dữ liệu ít hơn `pageSize` | Trả tất cả hàng, `hasNext=false`, không có cursor tiếp. |
| Dữ liệu đúng bằng `pageSize` | `hasNext=false`; không nhầm số hàng đúng giới hạn thành còn trang tiếp. |
| Dữ liệu bằng `pageSize + 1` | Trả `pageSize` hàng, `hasNext=true` và cursor trỏ tới **hàng cuối đã trả**. |
| Nhiều hàng có cùng `created_at` | Không lặp/thiếu hàng khi chuyển trang keyset nhờ `order_id` phá hòa. |
| Keyset từ cursor cuối cùng | Kết quả rỗng nếu không có hàng đứng sau. |
| `pageIndex=0` | Offset = 0, trả trang đầu. |
| `pageIndex < 0`, `pageSize=0` hoặc quá giới hạn | Từ chối đầu vào trước khi chạy SQL. |
| Tích `pageIndex × pageSize` tràn `long` | Phát hiện bằng `Math.multiplyExact()`, không truyền offset âm. |
| Thêm hàng ở đầu trước trang 2 | Offset có thể lặp; keyset với cursor cũ không lặp các hàng phía trước. |
| Xóa hàng trước cursor/trang offset | Giải thích được khác biệt hai cơ chế, không giả định snapshot. |
| Sửa `created_at` hoặc đổi `status` | Kiểm tra chính sách nghiệp vụ; keyset không tự bảo đảm bất biến. |
| Cursor bị sửa/tái sử dụng cho filter khác | API từ chối token không hợp lệ hoặc không khớp filter/tenant. |
| Thời gian có phần microsecond và ID lớn | Cursor encode/decode không mất độ chính xác. |
| Truy vấn có nhiều tenant | Không trả hàng ngoài phạm vi tenant đã xác thực. |
| Driver/DBMS khác PostgreSQL | Kiểm tra cú pháp pagination, row-value comparator, kiểu thời gian và kế hoạch index. |

Một kiểm thử tích hợp hữu ích: chèn nhiều đơn cùng `created_at` với ID khác nhau, duyệt liên tiếp tất cả các trang keyset, thu toàn bộ ID vào một tập, rồi đối chiếu với kết quả từ một truy vấn kiểm chứng **trong môi trường không có ghi đồng thời**. Khi có ghi đồng thời, thay tiêu chí kiểm thử thành những bất biến có thể bảo đảm, không so sánh với một snapshot tự tạo không tương ứng.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không có `ORDER BY`. | Thứ tự trang tùy kế hoạch query, dễ trùng hoặc thiếu. | Dùng thứ tự tường minh và duy nhất. |
| Chỉ sort theo `created_at` khi có nhiều giá trị trùng. | Thứ tự không xác định, cursor sai. | Thêm `order_id` làm tie-breaker. |
| Cursor chỉ chứa ID trong khi sort theo thời gian. | So sánh không phản ánh thứ tự thực. | Cursor chứa toàn bộ cặp khóa sắp xếp. |
| Dùng `<=` cho cursor kế tiếp. | Hàng cuối của trang trước có thể lặp ở trang sau. | Dùng phép so sánh **strict** `<` với chiều DESC. |
| Dùng cursor là hàng lookahead. | Bỏ sót hàng nhìn trước. | Cursor lấy từ hàng cuối **đã trả**. |
| Dùng phép `<` với sort ASC hoặc nhiều chiều trộn lẫn. | Duyệt sai thứ tự. | Thiết kế predicate theo chính xác `ORDER BY`. |
| Trộn cursor giữa hai filter/tenant. | Sai dữ liệu hoặc rủi ro vượt phạm vi. | Gắn filter/tenant vào token và xác minh phân quyền. |
| Base64 cursor rồi coi là chống sửa. | Client tự thay khóa để truy cập vị trí tùy ý. | Ký/kiểm tra token, đồng thời phân quyền ở query. |
| OFFSET rất sâu nhưng không đo query plan. | Độ trễ tăng theo số hàng phải bỏ qua. | Xem xét keyset và index khi pattern truy cập phù hợp. |
| Tính offset bằng `int` không kiểm tra. | Tràn số, trả sai trang hoặc lỗi SQL. | `long` + `Math.multiplyExact()` + giới hạn đầu vào. |
| Xem keyset như snapshot bất biến. | Không xử lý được xóa, update sort key hoặc backfill. | Định nghĩa yêu cầu consistency rõ ràng. |
| Dùng `setFetchSize()` để thay `LIMIT`. | Query vẫn có thể trả rất nhiều hàng. | Giới hạn hàng bằng SQL, fetch size chỉ là gợi ý truyền dữ liệu. |
| Đếm toàn bảng sau mọi trang. | Tăng tải không cần thiết. | Dùng `hasNext` khi UX không bắt buộc tổng số. |

## 14. Quy trình chọn phương án phù hợp

1. **Xác định hành vi UX/API.** Người dùng cần nhảy tới số trang bất kỳ hay chỉ bấm “xem thêm”?
2. **Chốt filter và thứ tự.** Bảo đảm `ORDER BY` xác định; thêm khóa duy nhất để phá hòa.
3. **Lựa chọn cơ chế.** Offset cho bảng nhỏ/nhảy trang; keyset cho duyệt tiếp theo trên dữ liệu lớn và có index.
4. **Thiết kế SQL tham số hóa.** Bind tất cả filter, cursor, `LIMIT` và `OFFSET` bằng `PreparedStatement`; chỉ chọn tên cột/sort từ whitelist của server.
5. **Giới hạn đầu vào.** Xác định `pageSize` tối đa, quy ước page 0/1, phát hiện overflow và giới hạn token.
6. **Đảm bảo cursor đúng.** Chứa toàn bộ khóa sắp xếp, lấy từ hàng cuối đã trả, bảo toàn kiểu và độ chính xác thời gian.
7. **Thiết kế nhất quán.** Quyết định hành vi khi thêm/xóa/sửa dữ liệu; nếu cần snapshot tuyệt đối, không dựa riêng vào keyset.
8. **Thiết kế index và đo.** Dùng query plan và dữ liệu gần thực tế; đo trang sâu, số hàng đọc và áp lực DBMS.
9. **Kiểm thử đa driver.** Xác minh `TIMESTAMPTZ`/`OffsetDateTime`, row comparison, offset binding và các trường hợp ranh giới.

## 15. Ghi nhớ

Trong **JDBC**, **phân trang theo offset** lấy hàng theo vị trí qua `LIMIT/OFFSET`, dễ đánh số và nhảy trang nhưng có thể chậm khi offset lớn và dễ bị dịch vị trí bởi dữ liệu thay đổi. **Phân trang theo khóa (keyset)** lấy hàng dựa trên **khóa sắp xếp của bản ghi cuối trang trước**, thường thích hợp cho feed, lịch sử giao dịch và API duyệt nhiều trang. Cả hai phải có `ORDER BY` xác định, truy vấn tham số hóa, giới hạn page size và index phù hợp. Keyset cần cursor chứa đủ khóa, dùng phép so sánh đúng chiều, không lấy cursor từ hàng lookahead và không được coi là một snapshot bất biến. Hãy chọn cách phù hợp với sản phẩm, kiểm chứng tính đúng đắn khi có ghi đồng thời và đo kế hoạch thực thi trên driver/DBMS thực tế.
