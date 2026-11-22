# So sánh phân trang offset với phân trang theo khóa

Một ứng dụng Java cho phép khách hàng xem lịch sử đơn hàng, sắp xếp từ mới đến cũ. Khi dữ liệu mới chỉ có 500 đơn, hai cách lấy trang đầu đều nhanh. Sau một năm, bảng có hàng chục triệu bản ghi, người dùng kéo đến cuối danh sách thì truy vấn dùng `OFFSET 500000` bắt đầu chậm. Trong lúc khách đang duyệt, một đơn mới được tạo ở đầu danh sách; lần tải trang kế tiếp đột nhiên hiển thị lại đơn đã thấy. Nhóm phát triển thay `OFFSET` bằng một “con trỏ” chỉ chứa ID cuối cùng, nhưng kết quả vẫn sai vì danh sách thực tế sắp xếp theo thời gian và nhiều đơn có thể cùng timestamp.

**Phân trang offset** (*offset pagination*) chia kết quả thành trang bằng cách bỏ qua một số dòng sau khi sắp xếp, thường dùng `LIMIT ... OFFSET ...`. **Phân trang theo khóa** (*keyset/seek pagination*) lấy các dòng nằm **sau một khóa sắp xếp đã quan sát**, sử dụng điều kiện so sánh trực tiếp với khóa đó. Hai cách đều hợp lệ nhưng có đặc tính rất khác về chi phí, điều hướng và ảnh hưởng khi dữ liệu thay đổi.

Bài thuộc chương **Thực hành tổng hợp** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ vận dụng tư duy thiết kế persistence Java — mô hình dữ liệu, SQL/index, giao dịch, isolation, bảo mật nhiều tenant, tài nguyên JDBC, kiểm thử và đo hiệu năng — để xây dựng hai API phân trang trên **cùng một tập dữ liệu PostgreSQL**, kiểm chứng bằng test và lựa chọn theo yêu cầu nghiệp vụ.

**Kết quả mong đợi:** không chỉ biết viết hai câu SQL, mà còn giải thích được *vì sao* một chiến lược có độ trễ tốt/xấu theo trang sâu, *khi nào* có thể bị lặp hoặc bỏ sót bản ghi, *khi nào* cần tổng số trang và *cần bảo vệ con trỏ* như thế nào.

## 1. Mô hình bài thực hành và yêu cầu sản phẩm

Giả sử API lịch sử đơn hàng có các yêu cầu:

1. Người dùng chỉ được xem đơn thuộc **tenant đã xác thực** và phạm vi quyền tương ứng.
2. Lọc theo `status` và sắp xếp **mới nhất trước**, không để các đơn có cùng thời điểm xuất hiện theo thứ tự không xác định.
3. Mỗi lần trả tối đa 50 bản ghi; UI có thể nhấn **Trang 1, 2, 3** hoặc cuộn **Tải thêm**.
4. Trong lúc duyệt có thể có đơn mới, đơn bị hủy hoặc đơn thay đổi trạng thái.
5. Hệ thống phải hoạt động trên dữ liệu lớn, không gửi payload chứa bí mật hoặc thông tin khách hàng trong URL con trỏ.
6. Kết quả cần có cách kiểm thử bằng JDBC/PostgreSQL thật và một phép benchmark có số đo chứ không phán đoán.

Chúng ta xét hai UX khác nhau:

| Trải nghiệm | Phù hợp tự nhiên hơn | Vì sao |
| --- | --- | --- |
| “Trang 1 / 2 / 3 / … / 100” | Offset | Đi đến trang N bằng phép tính vị trí |
| “Tải thêm đơn cũ hơn” | Keyset | Tiếp tục ngay sau hàng cuối của trang trước |
| “Lấy 50 bản ghi tiếp sau khóa X” | Keyset | Xác định điểm tiếp tục bằng khóa dữ liệu |
| “Xuất toàn bộ báo cáo đúng một snapshot” | Không cách nào tự đủ | Cần hợp đồng snapshot/consistency và job export riêng |
| “Xem tổng cộng có bao nhiêu đơn/trang?” | Offset thường được ghép với COUNT | COUNT là câu truy vấn riêng; không miễn phí |

Không có một “cách hiện đại” thay thế mọi phân trang. Phải chọn từ **hợp đồng sản phẩm, tính ổn định, chi phí truy vấn và cấu trúc khóa**.

## 2. Schema PostgreSQL làm nền cho cả hai cách

Bảng minh họa:

~~~sql
CREATE TABLE orders (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status      TEXT NOT NULL
                CHECK (status IN (
                    'PENDING', 'PAID', 'SHIPPED', 'CANCELLED'
                )),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(18, 2) NOT NULL
                 CHECK (total_amount >= 0)
);

-- Dành cho truy vấn minh họa: tenant + status + thứ tự mới đến cũ.
CREATE INDEX orders_tenant_status_created_id_idx
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Index tổng hợp bắt đầu bằng các điều kiện **equality** `tenant_id` và `status`, sau đó là hai cột `ORDER BY`. PostgreSQL có thể sử dụng index này để đi theo một thứ tự gần với kết quả mong muốn và tránh/giảm thao tác sort tùy kích thước dữ liệu, selectivity, statistics và query plan thực tế.

Các quyết định có chủ ý:

- `id` là khóa duy nhất, không phụ thuộc việc hai đơn có cùng `created_at`.
- `created_at` không NULL; so sánh keyset tuple với NULL không hoạt động như phép so sánh tổng thứ tự thông thường.
- `tenant_id` xuất phát từ principal đã xác thực, **không lấy tùy ý** từ query parameter của người dùng.
- `status` là bộ lọc chính của bài. Nếu sản phẩm có chế độ “mọi trạng thái”, cần benchmark một query/index khác; không mặc định index có `status` ở giữa vẫn tối ưu cho mọi truy vấn.
- `id` có thể không tăng đúng theo **thứ tự commit** của transaction. Vì vậy không dùng mỗi ID để thay cho `created_at` khi hợp đồng là sắp xếp theo thời gian tạo.

### Dữ liệu nhỏ để kiểm tra bằng mắt

Giả sử cùng tenant `501`, trạng thái `PAID`:

| id | created_at (UTC) |
| ---: | --- |
| 108 | 2026-11-22 09:00:02 |
| 107 | 2026-11-22 09:00:01 |
| 106 | 2026-11-22 09:00:01 |
| 105 | 2026-11-22 09:00:00 |
| 104 | 2026-11-22 08:59:59 |
| 103 | 2026-11-22 08:59:58 |

Với `ORDER BY created_at DESC, id DESC`, thứ tự là **108, 107, 106, 105, 104, 103**. Nếu chỉ sắp xếp theo `created_at DESC`, thứ tự giữa 107 và 106 **không được xác định đầy đủ**, có thể thay đổi theo plan, index hoặc truy vấn.

## 3. Thứ tự toàn phần: điều kiện bắt buộc trước khi phân trang

Phân trang không chỉ cần `LIMIT`; nó cần một **thứ tự ổn định và có thể so sánh được**.

~~~sql
-- KHÔNG đủ khi nhiều hàng cùng created_at.
SELECT id, created_at
FROM orders
WHERE tenant_id = 501 AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 3;

-- Có tie-breaker duy nhất.
SELECT id, created_at
FROM orders
WHERE tenant_id = 501 AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Một thứ tự **toàn phần** trong phạm vi kết quả làm rõ mỗi cặp hàng đứng trước/sau nhau thế nào. Bổ sung `id` duy nhất vào `ORDER BY` tránh việc các hàng cùng timestamp được trả theo thứ tự không xác định. Tuy vậy:

1. Thứ tự được xác định **tại thời điểm truy vấn**, không đóng băng dữ liệu qua nhiều request.
2. Nếu trường sắp xếp bị cập nhật, vị trí của một hàng có thể thay đổi giữa các trang.
3. Nếu lọc theo trạng thái có thể đổi, một hàng có thể rời khỏi/từ bên ngoài đi vào tập kết quả.
4. Collation của chuỗi, quy tắc `NULLS FIRST/LAST` và tie-breaker phải được hiểu rõ nếu dùng những khóa khác.

Với bài này, ta coi `created_at` là **bất biến** sau khi ghi. Nếu ứng dụng cho phép chỉnh sửa thời gian tạo, phải điều chỉnh cam kết về phân trang và kiểm thử riêng các trường hợp di chuyển hàng.

## 4. Offset pagination: bỏ qua bao nhiêu hàng?

SQL:

~~~sql
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
OFFSET :offset;
~~~

Với kích thước trang `3`, trang đánh số từ `1`:

\[
\text{offset}=(\text{pageNumber}-1)\times\text{pageSize}
\]

Ví dụ bảng sáu hàng ở trên:

~~~text
Trang 1: LIMIT 3 OFFSET 0  -> 108, 107, 106
Trang 2: LIMIT 3 OFFSET 3  -> 105, 104, 103
Trang 3: LIMIT 3 OFFSET 6  -> không còn hàng
~~~

### Ưu điểm

- Cú pháp đơn giản, dễ hiểu, tương thích nhiều database và ORM.
- Đi tới trang N mà không cần tải từng trang trước đó.
- Phù hợp UI bảng quản trị yêu cầu số trang và chọn trang bất kỳ.
- Có thể ghép với `COUNT(*)` để tính tổng số dòng/trang, với chi phí đo được.

### Nhược điểm

- Để lấy một trang sâu, engine thường phải duyệt hoặc loại bỏ **nhiều hàng đứng trước**. `OFFSET 500000 LIMIT 50` không có nghĩa chỉ xử lý 50 hàng.
- Khi dữ liệu chèn/xóa trước vị trí hiện tại, **offset cố định không còn chỉ tới cùng vị trí logic**.
- Query COUNT trên tập dữ liệu lớn/điều kiện phức tạp có thể là một thành phần chi phí riêng đáng kể.
- Nếu trang N vượt giá trị integer/offset cho phép, phép tính từ API có thể overflow nếu không kiểm tra.

Độ phức tạp thường được mô tả xấp xỉ `O(offset + limit)` với index scan theo thứ tự, nhưng không phải một định lý cho mọi execution plan. Tùy selectivity, sort, heap fetch, index-only scan, parallelism và bộ nhớ cache, PostgreSQL có thể có kế hoạch khác. **Phải xem EXPLAIN thực tế**.

## 5. Thực hành offset: hai trang và phép COUNT

Một cặp query trong API dạng “Trang N”:

~~~sql
-- Page 2, page size 3.
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = 501 AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;

-- Tổng số dòng cùng điều kiện lọc.
SELECT COUNT(*) AS total_rows
FROM orders
WHERE tenant_id = 501 AND status = 'PAID';
~~~

Với 6 hàng, `total_rows=6` và số trang là `CEIL(6 / 3.0) = 2`. Nếu sản phẩm cần tổng chính xác, cần chấp nhận rằng SELECT danh sách và COUNT là **hai câu truy vấn** có thể thấy **hai snapshot khác nhau** dưới `READ COMMITTED` nếu có ghi đồng thời.

Đừng tính “totalPages” bằng một con số giả lấy từ `pg_class.reltuples` rồi trình bày như tổng chính xác đã được chứng thực. Thống kê ước lượng có ích cho UI hoặc lập kế hoạch khi chấp nhận sai số, nhưng phải ghi rõ rằng đó là ước lượng.

### Kiểm tra input trước khi đưa vào JDBC

~~~java
static long calculateOffset(int pageNumber, int pageSize) {
    if (pageNumber < 1 || pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Trang/kích thước không hợp lệ");
    }
    // Dùng long để tránh overflow từ nhân hai int.
    return (long) (pageNumber - 1) * pageSize;
}
~~~

Nếu driver/database sử dụng giới hạn kiểu cho offset, cần giới hạn thêm theo phạm vi được hỗ trợ. Đừng lấy một `int pageNumber` âm hoặc vô cùng lớn rồi dựng SQL/alloc list trước khi validate.

## 6. Offset pagination dưới INSERT và DELETE đồng thời

Đây là một vấn đề độc lập với việc truy vấn nhanh hay chậm.

Ban đầu:

~~~text
Theo thứ tự DESC:
108 107 106 | 105 104 103
Trang 1 = 108 107 106
~~~

Trước khi request trang 2, có đơn mới `109` được chèn **ở đầu**:

~~~text
109 108 107 | 106 105 104 | 103
Trang 2 với OFFSET 3 = 106 105 104
                       ^^^
106 đã xuất hiện ở trang 1 -> trùng bản ghi.
~~~

Nếu thay vì INSERT, đơn `108` ở đầu bị xóa:

~~~text
107 106 105 | 104 103
Trang 2 với OFFSET 3 = 104 103
Đơn 105 chưa xuất hiện ở trang 1 nhưng bị bỏ qua.
~~~

Một `ORDER BY` có khóa phụ duy nhất **không giải quyết sự dịch chuyển vị trí** do dữ liệu thêm/xóa. Nó chỉ giải quyết tính bất định khi hai hàng có khóa sắp xếp trùng nhau.

### “Cố định một snapshot” có giúp không?

Có thể đạt một mức kết quả nhất quán hơn khi đọc nhiều trang **trong cùng một transaction snapshot** với isolation phù hợp, chẳng hạn PostgreSQL `REPEATABLE READ`. Nhưng một UI gửi hàng chục HTTP request trong nhiều phút **không nên giữ một transaction database mở suốt lúc người dùng cuộn**, vì có thể giữ connection, snapshot cũ và làm tăng chi phí vacuum/resource. Đồng thời load balancer/request sau có thể vào worker khác.

Nếu yêu cầu là xuất báo cáo có dữ liệu chính xác tại một mốc, thiết kế **export job với snapshot/anchor hoặc tập ID đã được chốt** có thể phù hợp hơn việc tự kéo các trang offset qua HTTP.

## 7. Keyset pagination: bắt đầu từ khóa cuối của trang trước

Thay vì “bỏ qua 3 dòng”, keyset nói: “cho tôi những hàng có khóa sắp xếp **đứng sau** hàng cuối cùng đã thấy”.

Trang đầu:

~~~sql
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Trang tiếp theo dùng khóa cuối trang trước, ví dụ trang 1 có hàng cuối `(2026-11-22 09:00:01+00, 106)`:

~~~sql
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) < (:cursorCreatedAt, :cursorId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Với thứ tự `created_at DESC, id DESC`, các hàng **đứng sau** có tuple nhỏ hơn theo so sánh từ trái sang phải. PostgreSQL hỗ trợ row-value comparison cho các kiểu có phép so sánh B-tree phù hợp; điều kiện trên tương đương logic:

~~~sql
AND (
    created_at < :cursorCreatedAt
    OR (
        created_at = :cursorCreatedAt
        AND id < :cursorId
    )
)
~~~

Trong SQL với named placeholder lặp lại, framework cần bind đúng mọi vị trí; JDBC thuần dùng dấu `?` theo thứ tự. Row-value syntax ở ví dụ đầu phù hợp PostgreSQL và không phải một cú pháp chung cho mọi công nghệ SQL/NoSQL.

## 8. Thực hành keyset bằng chính dữ liệu mẫu

Trang 1 với size 3:

~~~text
Rows:
  (09:00:02, 108)
  (09:00:01, 107)
  (09:00:01, 106)  <- khóa cuối

nextCursor = (created_at=09:00:01, id=106)
~~~

Trang 2:

~~~sql
-- Đây là bản literal để đọc dễ; production dùng bind parameters.
SELECT id, created_at
FROM orders
WHERE tenant_id = 501
  AND status = 'PAID'
  AND (created_at, id) <
      (TIMESTAMPTZ '2026-11-22 09:00:01+00', 106)
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Kết quả: `105, 104, 103`. Nếu có đơn 109 mới chèn lên đầu trong thời gian đó, điều kiện “nhỏ hơn khóa 106” vẫn đi tiếp từ đúng vị trí logic trong danh sách **tại thời điểm truy vấn**; nó không trả lại 106 chỉ vì một hàng khác mới xuất hiện phía trên.

~~~mermaid
flowchart TD
    A[Trang đầu: 108, 107, 106] --> B[Giữ last key: time của 106, id 106]
    B --> C[Trang sau: WHERE tuple < lastKey]
    C --> D[105, 104, 103]
    E[Chèn 109 vào đầu] -. Không làm dịch khóa 106 .-> C
~~~

**Điều kiện quan trọng:** khóa sắp xếp và bộ lọc phải tiếp tục có nghĩa như lúc tạo cursor. Nếu `status` hoặc `created_at` thay đổi, keyset không tự bảo đảm duyệt mỗi bản ghi đúng một lần trong toàn bộ phiên người dùng.

## 9. Keyset, tie-breaker và hướng sắp xếp

Quy tắc:

| `ORDER BY` | Điều kiện “trang kế tiếp sau cursor” |
| --- | --- |
| `created_at DESC, id DESC` | `(created_at, id) < (cursorTime, cursorId)` |
| `created_at ASC, id ASC` | `(created_at, id) > (cursorTime, cursorId)` |
| `score DESC, id DESC` | `(score, id) < (cursorScore, cursorId)` |
| `name ASC, id ASC` | Cần theo collation, NULL semantics và index tương ứng |
| `priority DESC, created_at ASC, id ASC` | Điều kiện hỗn hợp **không** đơn giản là so tuple một chiều |

Với thứ tự hỗn hợp, ví dụ `priority DESC, created_at ASC, id ASC`, phải viết điều kiện theo **thứ tự từ điển với từng hướng**:

~~~sql
AND (
    priority < :priority
    OR (
        priority = :priority
        AND created_at > :createdAt
    )
    OR (
        priority = :priority
        AND created_at = :createdAt
        AND id > :id
    )
)
~~~

Việc bổ sung `id` duy nhất là thiết yếu khi `created_at` hoặc `priority` có thể trùng. **Không chỉ dùng `WHERE id < lastId`** khi `ORDER BY created_at DESC, id DESC`, vì ID có thể không đi cùng thứ tự thời gian và có thể thay đổi nếu dùng nguồn ID khác.

### NULL trong khóa sắp xếp

Row comparison chứa NULL có thể cho kết quả `UNKNOWN`, khiến hàng không được duyệt như mong muốn. Các lựa chọn:

1. Thiết kế khóa seek **NOT NULL**.
2. Định nghĩa `NULLS FIRST/LAST`, biểu thức sắp xếp chuẩn hóa và điều kiện seek tương ứng.
3. Dùng trường computed/sort key rõ ràng, có index phù hợp; kiểm thử cả NULL và non-NULL.

Không dùng `COALESCE(created_at, '1970-01-01')` một cách tùy tiện: mốc sentinel có thể trùng dữ liệu thật hoặc đổi semantics nghiệp vụ.

## 10. Java/JDBC: API offset với giới hạn page size

Ví dụ một adapter JDBC thuần dùng `DataSource`. Đoạn mã giả định bảng `orders` như phần 2 và `tenantId` đã được xác thực ở tầng use case:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

record OrderRow(
        long id, Instant createdAt, String status, BigDecimal totalAmount) {}

public final class OffsetOrderReader {
    private final DataSource dataSource;

    public OffsetOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderRow> findPage(
            long authenticatedTenantId,
            String allowedStatus,
            int pageNumber,
            int pageSize) throws SQLException {
        if (authenticatedTenantId <= 0 ||
                pageNumber < 1 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Input không hợp lệ");
        }
        if (!List.of("PENDING", "PAID", "SHIPPED", "CANCELLED")
                .contains(allowedStatus)) {
            throw new IllegalArgumentException("Status không hợp lệ");
        }
        long offset = (long) (pageNumber - 1) * pageSize;

        String sql = """
            SELECT id, created_at, status, total_amount
            FROM orders
            WHERE tenant_id = ? AND status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """;

        List<OrderRow> rows = new ArrayList<>(pageSize);
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, authenticatedTenantId);
            ps.setString(2, allowedStatus);
            ps.setInt(3, pageSize);
            ps.setLong(4, offset);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    rows.add(new OrderRow(
                            rs.getLong("id"),
                            rs.getObject(
                                    "created_at", OffsetDateTime.class)
                                    .toInstant(),
                            rs.getString("status"),
                            rs.getBigDecimal("total_amount")));
                }
            }
        }
        return List.copyOf(rows);
    }
}
~~~

Những điều cần nhớ:

- `OFFSET`/`LIMIT` là **giá trị số** được bind, không ghép chuỗi từ request. `ORDER BY` cũng phải cố định hoặc chọn từ **allowlist**; SQL parameter không thể biểu diễn tùy ý tên cột.
- `getObject(..., OffsetDateTime.class)` yêu cầu JDBC driver hỗ trợ ánh xạ PostgreSQL `TIMESTAMPTZ` phù hợp. Kiểm thử theo phiên bản driver thật.
- `DataSource` quản lý connection pool; adapter đóng `ResultSet`/statement/connection bằng `try-with-resources`. Không giữ connection trong lúc client cuộn giữa các trang.
- `pageSize` có giới hạn nhỏ để tránh vô tình lấy hàng triệu row và làm đầy JVM heap.
- Quyền tenant không đến từ một tham số URL do người dùng có thể tùy ý đổi. Với truy vấn customer-level, cần **bổ sung `customer_id`** hoặc policy được phê duyệt, không coi chỉ có tenant đủ cho mọi user.

**Giới hạn:** `List<OrderRow>` trả rows, chưa có `totalPages`. Nếu UI cần total, thực hiện `COUNT(*)` riêng và kiểm tra chi phí; không suy ra total từ việc danh sách có đủ `pageSize` hàng.

## 11. Java/JDBC: một API keyset hoàn chỉnh cho “Tải thêm”

Một response keyset thường trả `items` và `nextCursor`. Chúng ta tách:

- `SeekKey`: cặp khóa sắp xếp cuối cùng đã được phục vụ.
- `SeekPage`: danh sách dữ liệu và thông tin có trang tiếp hay không.
- `CursorCodec`: lớp mã hóa/ký và xác minh cursor ở ranh giới HTTP (đề cập ở phần tiếp).

Adapter sau giữ cursor dạng **typed object đã được xác minh**; nó không giải mã trực tiếp string không đáng tin:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

record SeekKey(Instant createdAt, long id) {}
record OrderItem(
        long id, Instant createdAt, String status, BigDecimal totalAmount) {}
record SeekPage(List<OrderItem> items, SeekKey nextKey) {}

public final class KeysetOrderReader {
    private final DataSource dataSource;

    public KeysetOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public SeekPage readAfter(
            long tenantId, String status, SeekKey after, int size)
            throws SQLException {
        if (tenantId <= 0 || size < 1 || size > 100 ||
                !List.of("PENDING", "PAID", "SHIPPED", "CANCELLED")
                        .contains(status)) {
            throw new IllegalArgumentException("Invalid scope/size");
        }
        if (after != null &&
                (after.createdAt() == null || after.id() <= 0)) {
            throw new IllegalArgumentException("Invalid cursor key");
        }

        // Hai SQL cố định giúp optimizer nhìn rõ hai trường hợp;
        // không dùng OR (? IS NULL) làm điều kiện chung.
        final String firstSql = """
            SELECT id, created_at, status, total_amount
            FROM orders
            WHERE tenant_id = ? AND status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;
        final String nextSql = """
            SELECT id, created_at, status, total_amount
            FROM orders
            WHERE tenant_id = ? AND status = ?
              AND (created_at, id) < (?, ?)
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        List<OrderItem> fetched = new ArrayList<>(size + 1);
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     after == null ? firstSql : nextSql)) {
            ps.setLong(1, tenantId);
            ps.setString(2, status);
            if (after == null) {
                ps.setInt(3, size + 1);
            } else {
                ps.setObject(3, OffsetDateTime.ofInstant(
                        after.createdAt(), ZoneOffset.UTC));
                ps.setLong(4, after.id());
                ps.setInt(5, size + 1);
            }

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    fetched.add(new OrderItem(
                            rs.getLong("id"),
                            rs.getObject(
                                    "created_at", OffsetDateTime.class)
                                    .toInstant(),
                            rs.getString("status"),
                            rs.getBigDecimal("total_amount")));
                }
            }
        }

        boolean hasMore = fetched.size() > size;
        List<OrderItem> visible = List.copyOf(
                fetched.subList(0, Math.min(size, fetched.size())));
        SeekKey next = null;
        if (hasMore) {
            OrderItem lastVisible = visible.get(visible.size() - 1);
            next = new SeekKey(lastVisible.createdAt(), lastVisible.id());
        }
        return new SeekPage(visible, next);
    }
}
~~~

### Vì sao lấy `size + 1`?

Nếu chỉ lấy `size` hàng, không chắc còn hàng tiếp theo. Trả thêm **một hàng thăm dò** giúp xác định `hasMore` mà không cần chạy COUNT. Ví dụ size 3, truy vấn trả 4 hàng; API chỉ trả 3 hàng và `nextCursor` trỏ tới **hàng thứ ba đã hiển thị**, không phải hàng thứ tư thăm dò. Nếu lấy key của hàng thứ tư làm cursor, request sau sẽ **bỏ qua hàng thứ tư**.

Ở trang cuối, nếu truy vấn trả không quá size hàng, `nextKey=null`. Điều đó chỉ có nghĩa **tại thời điểm query, không tìm thấy hàng tiếp trong cùng điều kiện**; nếu dữ liệu đổi sau đó, trạng thái có thể khác.

### Một đặc điểm cần đo

Query trả tối đa `size + 1` hàng, nhưng không có nghĩa DB luôn đọc đúng số hàng này; index visibility, heap fetch, filter và plan vẫn ảnh hưởng. Nếu cursor được chọn rất sâu trong tập dữ liệu, index có thể cho phép **seek tới gần vị trí bắt đầu** thay vì đi qua toàn bộ hàng ở các trang trước.

## 12. Thiết kế API: page number và opaque cursor

Hai hợp đồng HTTP minh họa:

~~~http
GET /api/orders?status=PAID&page=12&size=25

GET /api/orders?status=PAID&size=25&after=eyJ2IjoxLC4uLn0.signature
~~~

Ví dụ response offset:

~~~json
{
  "items": [{"id": 1001}, {"id": 1000}],
  "page": 12,
  "size": 25,
  "totalItems": 1000000,
  "totalPages": 40000
}
~~~

Ví dụ response keyset:

~~~json
{
  "items": [{"id": 1001}, {"id": 1000}],
  "nextCursor": "opaque-signed-token",
  "hasMore": true
}
~~~

JSON là hợp đồng minh họa; `totalItems` và `totalPages` trong offset chỉ nên xuất hiện khi API **đã thực sự tính hoặc lấy nguồn ước lượng được ghi nhãn rõ**. Những số `1000000` và `40000` không liên quan tới tập dữ liệu nhỏ ở phần 2.

Ở keyset, không nên trả trực tiếp raw `id=1000` rồi coi đó là một cursor đủ khi sort theo cả `created_at` và `id`. Cursor phải chứa **đủ khóa sắp xếp**, phiên bản hợp đồng và phạm vi filter.

### Nên mã hóa gì trong cursor?

~~~json
{
  "v": 1,
  "sort": "created_at_desc_id_desc",
  "tenantId": 501,
  "status": "PAID",
  "limit": 25,
  "lastCreatedAt": "2026-11-22T09:00:01Z",
  "lastId": 106,
  "expiresAtEpochSeconds": 1795400000
}
~~~

Giá trị timestamp và expiry ở đây chỉ để hình dung cấu trúc, **không phải token đã ký hợp lệ**. Trong production, các field phải được mã hóa canonical và **ký toàn vẹn**; không dùng JSON thô từ client như dữ liệu đã tin cậy.

## 13. Bảo mật cursor: ràng buộc scope và kiểm soát sửa đổi

Một cursor là **dữ liệu client có thể gửi lại**, ngay cả khi server sinh ra nó. Vì vậy cần thiết kế như một capability/continuation token có giới hạn, chứ không phải mảnh SQL ghép tự do.

Các rủi ro:

| Rủi ro | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Client đổi tenant | Sửa `tenantId=501` thành `502` | So scope cursor với principal đã xác thực, luôn bind WHERE tenant |
| Client đổi filter | Trang 1 status PAID, trang 2 status SHIPPED | Ký và đối chiếu filter/sort |
| Client nâng pageSize | Size 25 thành 100000 | Giới hạn và ký size |
| Cursor bị giả mạo | Đặt timestamp/ID tùy ý | HMAC/AEAD và input validation |
| Token sống quá lâu | Dùng sau đổi schema/sort | Version, expiry, key rotation |
| Thông tin nhạy cảm trong token | Đưa customer name, raw SQL, JWT vào JSON | Chỉ chứa metadata tối thiểu; mã hóa nếu cần bảo mật nội dung |
| Token bị leak trong log URL | Query param bị log ở proxy | Redact query, không gắn PII, cân nhắc transport phù hợp |

**Base64URL chỉ là encoding, không phải encryption hoặc chữ ký**. Một token base64 có thể đọc/sửa nếu không có xác thực toàn vẹn. HMAC-SHA256 với khóa lưu ở secret manager là một cơ chế phổ biến để ký payload; AEAD hữu ích nếu nội dung token cần **bí mật**, không chỉ chống giả mạo.

Khi nhận token:

1. Parse theo format đã định, kiểm tra kích thước tối đa để tránh payload quá lớn.
2. Xác minh chữ ký bằng kiểm tra constant-time trước khi tin field trong payload.
3. Kiểm tra phiên bản, expiry, sort/filter/page size và phạm vi tenant so với **principal server đã xác thực**.
4. Kiểm tra định dạng thời gian/ID và giá trị hợp lệ trước khi truyền vào JDBC.
5. Dù cursor đã hợp lệ, vẫn áp dụng kiểm tra quyền ở use case và điều kiện `WHERE tenant_id=?`.
6. Trả lỗi cursor không hợp lệ/hết hạn theo API contract, không đưa ra stack trace hay khóa ký.

Một cursor bị sửa không được làm hệ thống phát ra SQL tùy ý. **Không dùng `ORDER BY` lấy từ chuỗi token và nối trực tiếp vào câu SQL**; server chọn từ các lựa chọn được allowlist.

## 14. Quay lại trang trước bằng keyset

Offset đi ngược bằng `pageNumber - 1`. Với keyset, muốn lấy trang **đứng trước** trang hiện tại, cần giữ **khóa đầu** của trang hiện tại và đảo chiều điều kiện/query để lấy các hàng liền trước:

~~~sql
-- Danh sách chính sắp DESC, nhưng query lấy trang liền trước
-- bằng cách đi ASC từ first key của trang hiện tại.
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) > (:firstCreatedAt, :firstId)
ORDER BY created_at ASC, id ASC
LIMIT :pageSize;
~~~

Các hàng trong kết quả truy vấn này được trả theo **ASC**, vì vậy phía ứng dụng phải **đảo ngược thứ tự của những hàng đã lấy** trước khi hiển thị trong danh sách chính `DESC`.

Ví dụ trang hiện tại có 105, 104, 103 (đứng cuối là 103), `firstKey=(time105,105)`. Query “greater-than firstKey” sắp ASC trả 106, 107, 108; đảo lại thành **108,107,106**, đúng trang phía trước.

### Những chi tiết không nên bỏ sót

- Muốn biết có trang trước nữa hay không, có thể lấy `size + 1` trong query ngược và bỏ đúng hàng thăm dò theo thứ tự, giống logic forward nhưng phải chú ý chiều.
- `prevCursor` phải dựa vào **khóa đầu của trang được trả về**, không dùng nhầm `lastKey` của trang hiện tại.
- Nếu dữ liệu bị thêm/xóa trong thời gian duyệt, “quay lại” vẫn chỉ là một phép đọc mới, không bảo đảm kết quả trùng byte-for-byte với lần trước.
- Nếu UI cần quay lại chính xác các trang đã xem, có thể giữ **history of cursors** ở client hoặc lưu một result-set snapshot có TTL ở server. Đó là một hợp đồng khác với keyset stateless.
- Không coi keyset hỗ trợ “nhảy đến trang 10.000” một cách tự nhiên; muốn nhảy xa phải có một điểm seek tương ứng hoặc cấu trúc index/anchor bổ trợ.

## 15. Index cho offset và keyset: không chỉ có cú pháp SQL

Với query:

~~~sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
~~~

Index gợi ý:

~~~sql
CREATE INDEX orders_tenant_status_created_id_idx
ON orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
~~~

### Vì sao thứ tự cột quan trọng?

- `tenant_id` và `status` được lọc bằng equality, giúp thu hẹp vùng khóa theo tenant/trạng thái khi planner chọn index.
- `created_at DESC, id DESC` phù hợp chính xác thứ tự mà trang yêu cầu; hai cột này cũng phục vụ điều kiện seek.
- Nếu đảo cột thứ tự hoặc dùng một index riêng chỉ trên `created_at`, planner có thể phải sort hoặc quét rộng hơn tùy thống kê.
- B-tree hỗ trợ scan theo thứ tự ngược trong các trường hợp phù hợp; không phải lúc nào cần tạo hai index riêng cho chiều ASC và DESC khi toàn bộ hướng đảo đồng nhất.

### Chú ý bộ lọc tùy chọn

Nếu product cho phép không truyền `status`, query:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

có thể **không** nhận được thứ tự lý tưởng từ index `(tenant_id,status,created_at DESC,id DESC)`, vì các hàng được nhóm theo status trước khi được sắp theo created_at. Có thể cần một index khác:

~~~sql
CREATE INDEX orders_tenant_created_id_idx
ON orders (tenant_id, created_at DESC, id DESC);
~~~

**Không tạo index vô hạn cho mọi bộ lọc.** Mỗi index làm tăng dung lượng, I/O ghi và chi phí vacuum/maintenance. Cần đo truy vấn thật, lưu lượng read/write và business-critical paths trước khi chọn số index.

### Covering index có luôn nhanh?

Một index có `INCLUDE(status,total_amount)` hoặc những cột projection khác có thể giúp một số index-only scan khi điều kiện MVCC visibility cho phép, nhưng thêm quá nhiều cột làm index phình to, tăng write amplification. `Index Only Scan` vẫn có thể phải truy cập heap nếu visibility map chưa đủ; cần đọc `Heap Fetches` và `BUFFERS` trong `EXPLAIN`.

## 16. Đọc `EXPLAIN` để giải thích vì sao trang sâu chậm

Hai query benchmark minh họa:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = 501 AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50 OFFSET 500000;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = 501 AND status = 'PAID'
  AND (created_at, id) <
      (TIMESTAMPTZ '2026-11-22 09:00:01+00', 106)
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

**Không so sánh hai giá trị cursor tùy tiện**: query keyset phải bắt đầu gần đúng vị trí của offset sâu để benchmark cùng trang logic. Trong dữ liệu sản phẩm lớn, trước hết lấy khóa hàng tại vị trí deep offset **ở môi trường test**, rồi dùng đúng khóa đó làm starting point cho keyset; không tính chi phí “tìm cursor” vào mỗi lần keyset next page nếu API thông thường đã có cursor từ trang trước.

Các trường cần đọc trong plan:

| Tín hiệu | Cần quan sát |
| --- | --- |
| `Index Scan`/`Index Only Scan`/`Seq Scan` | Planner đang chọn đường đọc nào? |
| `actual rows` và `loops` | Bao nhiêu hàng thật được xử lý ở mỗi node? |
| `Buffers: shared hit/read` | Bao nhiêu truy cập buffer/cache, không đồng nhất với physical disk I/O |
| `Heap Fetches` | Index-only scan có phải đọc heap nhiều không? |
| `Sort Method` và temp I/O | Có sort đắt hoặc spill ra disk không? |
| `Execution Time` | Thời gian ở phía server, không chứa toàn bộ network/JDBC/JSON |
| `rows removed by filter` | Index có lọc đúng phạm vi không? |

Với một index phù hợp và dữ liệu lớn, offset sâu có thể phải **đi qua nhiều entry trước trang cần lấy**, trong khi keyset có thể bắt đầu từ một vùng khóa sát điểm seek. Nhưng kết quả còn phụ thuộc cache, data distribution, query plan, lọc, phiên bản database và indexing. Một benchmark chỉ có 100 bản ghi thường không cho thấy khác biệt có ý nghĩa.

**`EXPLAIN ANALYZE` thực thi câu SQL thật.** Ví dụ trên là `SELECT`, nhưng `EXPLAIN ANALYZE UPDATE/DELETE` có thể gây thay đổi dữ liệu, lock và side effect. Không chạy DML analyze trên production ngoài quy trình được kiểm soát.

## 17. Benchmark công bằng: đo latency, throughput và độ ổn định

Một phép đo đáng tin cậy nên có ít nhất ba nhóm dữ liệu:

1. **Hiệu năng:** latency p50/p95/p99, server execution time, số buffer, rows read, CPU/I/O, pool wait.
2. **Tính đúng:** có lặp/mất row giữa trang trong một timeline được kiểm soát không; mọi row được phép có xuất hiện đúng kỳ vọng không?
3. **Trải nghiệm:** có thể nhảy trang, có total pages, cursor quá hạn ra sao, khả năng quay lại khi dữ liệu đổi.

Một thiết kế benchmark:

| Thí nghiệm | Offset | Keyset | Điều cần so |
| --- | --- | --- | --- |
| Trang đầu, size 50 | `OFFSET 0` | Không cursor | Có thể tương đương khi index tốt |
| Trang giữa, size 50 | `OFFSET 5000` | Seek từ khóa hàng trước trang | Buffers, runtime |
| Trang sâu, size 50 | `OFFSET 500000` | Seek từ khóa hàng trước trang | Chi phí bỏ qua vs tìm khóa |
| Thêm bản ghi ở đầu sau trang 1 | Trang 2 với offset cố định | Trang 2 với key cuối | Duplicate/skip |
| Xóa bản ghi ở đầu sau trang 1 | Trang 2 với offset cố định | Trang 2 với key cuối | Duplicate/skip |
| Cập nhật sort key/filter | Trang mới | Trang seek | Cả hai có thể có thay đổi |

Chạy dữ liệu thật hoặc data generator có phân phối gần production: kích thước tenant lớn/nhỏ, mật độ timestamp trùng nhau, tỷ lệ trạng thái, hàng vừa tạo và hàng cũ, index statistics, tỷ lệ write/read, network hop. Thử cả cold/warm cache khi có ý nghĩa. Đo sau warmup phù hợp và lặp lại nhiều lần, không lấy một lần `EXPLAIN` nhanh nhất làm kết luận.

Không benchmark bằng cách thực hiện 500.000 lần “next cursor” rồi so với một query offset deep nếu mục tiêu của bạn là chi phí **một request next page**. Ngược lại, nếu UX thật cần nhảy ngay đến trang 10.000 từ trang đầu, phải tính cả **chi phí tìm điểm seek**; keyset không được gán khả năng nhảy ngẫu nhiên miễn phí.

## 18. Keyset không tự cung cấp snapshot nhất quán xuyên request

Keyset giải quyết tốt việc “tiếp tục sau khóa cuối” khi tập kết quả thay đổi bằng **chèn/xóa ở phía trước cursor**, nhưng không đóng băng toàn bộ danh sách.

Các trường hợp cần phân biệt:

| Thay đổi sau khi xem trang 1 | Offset có thể ra sao? | Keyset có thể ra sao? |
| --- | --- | --- |
| INSERT có khóa mới hơn tất cả hàng trang 1 | Trang 2 dễ lặp hàng cuối trang 1 | Trang sau thường không lặp do seek từ khóa cuối đã xem |
| DELETE hàng trước vị trí hiện tại | Trang 2 có thể bỏ sót hàng chưa thấy | Điều kiện seek tiếp tục theo khóa còn lại |
| INSERT có khóa **cũ hơn** last key | Có thể xuất hiện ở trang sau | **Cũng có thể** xuất hiện ở trang sau |
| UPDATE khóa sắp xếp của hàng đã xem xuống phía sau cursor | Có thể lặp ở trang sau | **Cũng có thể lặp** ở trang sau |
| UPDATE khóa sắp xếp của hàng chưa xem lên phía trước cursor | Có thể bỏ sót hoặc xuất hiện khác trang | **Có thể bỏ sót** |
| UPDATE `status` làm hàng rời/tới tập lọc | Thay đổi tập kết quả | **Cũng thay đổi tập kết quả** |
| DELETE một hàng phía sau cursor | Hàng không còn xuất hiện | Hàng không còn xuất hiện |

Ví dụ một row `id=99` đã hiển thị ở trang đầu với `created_at=09:00:10`, rồi người quản trị sửa created_at thành `08:50:00` (nhỏ hơn cursor đang dùng). Request sau với `WHERE created_at < cursorTime` có thể trả lại row 99. Đây là lý do thường chọn **sort key bất biến** cho một luồng keyset.

### Snapshot nhất quán là một yêu cầu riêng

Nếu nghiệp vụ cần **chính xác toàn bộ tập dữ liệu tại một thời điểm**, hãy cân nhắc:

- **Export job** chạy trong một transaction snapshot phù hợp và stream ra file với quản lý tài nguyên/timeout.
- **Materialized snapshot of IDs** có TTL, trạng thái job và quyền truy cập rõ ràng.
- **Snapshot/version fence** theo nghiệp vụ, ví dụ chỉ lấy record thuộc một version/cutoff đã chốt nếu mọi writer hỗ trợ ngữ nghĩa đó.
- Cơ chế snapshot database/CDC chuyên biệt khi thật sự cần tái dựng trạng thái nhất quán ở quy mô lớn.

Giữ một transaction PostgreSQL `REPEATABLE READ` qua hàng chục HTTP request là rủi ro vận hành: snapshot lâu làm tăng retention của MVCC row versions, connection bị giữ và cleanup/vacuum có thể chịu ảnh hưởng. Không chọn giải pháp này chỉ để thanh cuộn UI “đỡ trùng”.

## 19. High-water mark/anchor: giới hạn dữ liệu mới, nhưng không giải mọi thay đổi

Một kỹ thuật bổ sung cho feed keyset là lưu **khóa đầu lớn nhất** khi bắt đầu và gắn nó vào các trang tiếp:

~~~sql
-- Ví dụ anchor=(anchorCreatedAt, anchorId)
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) <= (:anchorCreatedAt, :anchorId)
  AND (created_at, id) <  (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Ý nghĩa: các hàng được tạo **sau thời điểm bắt đầu** với khóa lớn hơn anchor sẽ không xen vào các trang tiếp. Cursor cần lưu cả `anchorKey` và `lastKey`, không nhầm hai khái niệm.

**Giới hạn rõ ràng:**

1. Nếu ứng dụng cho phép INSERT với `created_at` trong quá khứ, một hàng mới **vẫn có thể nằm dưới anchor** và xuất hiện trong những trang sau.
2. `DEFAULT CURRENT_TIMESTAMP` của PostgreSQL dùng thời điểm bắt đầu transaction cho một số semantics; một transaction bắt đầu trước anchor nhưng commit sau có thể sinh row với timestamp nhỏ hơn anchor. Tăng theo thời gian tạo **không đồng nghĩa** tăng theo thứ tự commit.
3. Anchor không ngăn hàng bị UPDATE/DELETE, không giữ nguyên filter `status` và không phục hồi record đã xóa.
4. Anchor dùng ID tăng không tự chốt thứ tự commit. Sequence/identity có thể cấp ID trước khi transaction commit và transaction có thể rollback.
5. Nếu API cho phép tùy ý đổi filter, anchor của filter trước không còn là anchor hợp lệ.

Vì vậy nên mô tả đây là **giới hạn một số chèn mới vào đầu danh sách**, không gọi là snapshot bền vững hoặc “exactly-once traversal”. Nếu hợp đồng cần đúng mọi row ở mốc cụ thể, phải dùng cơ chế snapshot thật.

## 20. Phân trang trên replica, cache và hệ phân tán

Giả sử trang 1 đọc từ primary, trang 2 lại đọc từ read replica chậm hơn 5 giây:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Primary PostgreSQL
    participant R as Read replica
    C->>P: Trang 1, lấy lastKey K
    P-->>C: Items + cursor K
    C->>R: Trang 2 với cursor K
    Note over R: Replica có thể chưa có một số commit
    R-->>C: Dữ liệu ở một trạng thái cũ hơn
~~~

Đọc từ các phiên bản dữ liệu khác nhau gây thêm vấn đề consistency:

- Replica chưa nhận những INSERT/UPDATE đã có trên primary.
- Một hàng hiện ở trang 1 có thể chưa có/đã khác trạng thái trên replica.
- Với bộ lọc `status` thay đổi, cả trang đầu và tiếp theo có thể không phản ánh cùng tiến độ replication.
- Không nên suy từ `cursor K` rằng replica đã replay tới vị trí/transaction tạo nên K.

Một số lựa chọn:

| Hợp đồng đọc | Cách tiếp cận |
| --- | --- |
| Feed chấp nhận eventual consistency | Cho phép thay đổi hiển thị, thông báo semantics rõ |
| Read-your-writes bắt buộc | Route về primary hoặc đợi replica đạt vị trí replay cần thiết theo cơ chế hỗ trợ |
| Cần read snapshot cố định | Materialized snapshot/job hoặc cơ chế snapshot chuyên biệt |
| Có cache cho từng trang | Cache key phải gồm principal/tenant, filter, sort, cursor/version và chính sách invalidation |

Không lưu cache key chỉ theo `page=2`, vì sẽ trộn kết quả giữa tenant, filter, quyền và các mốc dữ liệu khác nhau. Nếu cache nhận kết quả đã được RLS lọc trong PostgreSQL, **cache hit không đi qua RLS**; cần kiểm tra quyền ở tầng ứng dụng trước khi trả dữ liệu đã cache.

### Sharding và nhiều database

Nếu đơn hàng được phân theo shard, một truy vấn có thứ tự toàn cục cần **merge các luồng đã sắp xếp** hoặc một sort key/toàn cục có thể so sánh đúng. Một cursor chỉ có `id` của shard A không đủ biểu diễn trạng thái đã đọc ở shard B. Có thể cần cursor chứa vị trí từng shard, watermark và policy merge, hoặc chuyển bài toán thành search/index read model riêng.

Phân trang theo khóa **không tự tạo giao dịch/snapshot toàn cụm** khi nhiều database độc lập tham gia.

## 21. Kiểm thử tích hợp: offset trùng/bỏ sót, keyset đi tiếp đúng khóa

Một test tốt không dựa vào timing ngẫu nhiên. Ta chủ động thực hiện các bước INSERT/DELETE **giữa hai lần gọi API**, với dữ liệu kiểm soát.

Ví dụ dưới đây dùng **JUnit 5, Testcontainers PostgreSQL và JDBC**. Để ví dụ tự chạy, test tạo một bảng có đủ các cột phục vụ bài. Trong dự án thực, **không thay migration production bằng DDL viết riêng trong test**; chạy migration đúng phiên bản trước khi kiểm tra repository thật.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class OrderPaginationIT {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    Connection connect() throws SQLException {
        return DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
    }

    @BeforeEach
    void seed() throws SQLException {
        try (Connection c = connect();
             Statement s = c.createStatement()) {
            s.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    tenant_id BIGINT NOT NULL,
                    customer_id BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    total_amount NUMERIC(18,2) NOT NULL
                )
                """);
            s.execute("""
                CREATE INDEX IF NOT EXISTS
                orders_tenant_status_created_id_idx
                ON orders (tenant_id, status, created_at DESC, id DESC)
                """);
            s.execute("DELETE FROM orders");
            s.execute("""
                INSERT INTO orders
                  (id, tenant_id, customer_id, status, created_at, total_amount)
                  OVERRIDING SYSTEM VALUE VALUES
                  (108,501,1,'PAID','2026-11-22 09:00:02+00',10.00),
                  (107,501,1,'PAID','2026-11-22 09:00:01+00',10.00),
                  (106,501,1,'PAID','2026-11-22 09:00:01+00',10.00),
                  (105,501,1,'PAID','2026-11-22 09:00:00+00',10.00),
                  (104,501,1,'PAID','2026-11-22 08:59:59+00',10.00),
                  (103,501,1,'PAID','2026-11-22 08:59:58+00',10.00)
                """);
        }
    }

    List<Long> offset(int skip, int limit) throws SQLException {
        try (Connection c = connect();
             PreparedStatement ps = c.prepareStatement("""
                SELECT id FROM orders
                WHERE tenant_id=501 AND status='PAID'
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """)) {
            ps.setInt(1, limit);
            ps.setInt(2, skip);
            List<Long> found = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) found.add(rs.getLong(1));
            }
            return found;
        }
    }

    List<Long> after(
            OffsetDateTime createdAt, long id, int limit)
            throws SQLException {
        try (Connection c = connect();
             PreparedStatement ps = c.prepareStatement("""
                SELECT id FROM orders
                WHERE tenant_id=501 AND status='PAID'
                  AND (created_at, id) < (?, ?)
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """)) {
            ps.setObject(1, createdAt);
            ps.setLong(2, id);
            ps.setInt(3, limit);
            List<Long> found = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) found.add(rs.getLong(1));
            }
            return found;
        }
    }

    @Test
    void insertAtFrontShiftsOffsetButNotSeekPosition()
            throws SQLException {
        assertEquals(List.of(108L, 107L, 106L), offset(0, 3));

        try (Connection c = connect();
             Statement s = c.createStatement()) {
            s.execute("""
                INSERT INTO orders
                  (id,tenant_id,customer_id,status,created_at,total_amount)
                  OVERRIDING SYSTEM VALUE
                VALUES (109,501,1,'PAID',
                        '2026-11-22 09:00:03+00',10.00)
                """);
        }

        // Đơn 106 đã có ở trang 1, nay lặp ở trang 2 kiểu offset.
        assertEquals(List.of(106L,105L,104L), offset(3, 3));
        // Keyset tiếp tục sau khóa của đơn 106.
        assertEquals(List.of(105L,104L,103L),
                after(OffsetDateTime.parse(
                        "2026-11-22T09:00:01Z"),106L,3));
    }

    @Test
    void deleteAtFrontShiftsOffsetAndSkipsUnseenOrder()
            throws SQLException {
        assertEquals(List.of(108L,107L,106L), offset(0,3));
        try (Connection c = connect();
             Statement s = c.createStatement()) {
            s.executeUpdate("DELETE FROM orders WHERE id=108");
        }
        // Đơn 105 chưa xem nhưng bị bỏ qua bởi OFFSET 3.
        assertEquals(List.of(104L,103L), offset(3,3));
        assertEquals(List.of(105L,104L,103L),
                after(OffsetDateTime.parse(
                        "2026-11-22T09:00:01Z"),106L,3));
    }

    @Test
    void sameTimestampNeedsUniqueTieBreaker() throws SQLException {
        assertEquals(List.of(106L,105L,104L),
                after(OffsetDateTime.parse(
                        "2026-11-22T09:00:01Z"),107L,3));
    }
}
~~~

### Kết quả kỳ vọng

| Tình huống | Offset trang 2 | Keyset trang 2 | Kết luận |
| --- | --- | --- | --- |
| Không có ghi đồng thời | 105, 104, 103 | 105, 104, 103 | Cùng tập |
| INSERT 109 trước trang 2 | **106, 105, 104** | 105, 104, 103 | Offset lặp 106 |
| DELETE 108 trước trang 2 | **104, 103** | 105, 104, 103 | Offset bỏ sót 105 |
| Hai hàng 107/106 cùng timestamp | Phải có ORDER BY id | Seek sau 107 trả 106 trước | Khóa phụ duy nhất là bắt buộc |

**Giới hạn test:** Các test trên chọn một lịch tuần tự có INSERT/DELETE giữa hai request để tạo ra hiệu ứng của ghi đồng thời. Chúng **không** chứng minh keyset đúng trong mọi lịch transaction, mọi isolation, mọi biến động sort key. Cần bổ sung kiểm thử concurrent writes, filter thay đổi, NULL, reverse pagination và điều kiện bảo mật như phần tiếp.

## 22. Test performance và contract cùng tồn tại

Một adapter có thể **đúng nhưng chậm**, hoặc **nhanh nhưng sai**. Vì vậy không nên trộn mọi yêu cầu trong một assert:

| Tầng test | Mục tiêu |
| --- | --- |
| Unit test cursor/filter | Encode/decode, expiry, tenant binding, sort version, validation |
| Repository integration test | SQL và tie-breaker, NULL semantics, đúng thứ tự, row limit |
| Concurrent mutation test | INSERT/DELETE giữa các trang, cập nhật filter/sort key |
| Security test | Cursor tenant A không truy cập tenant B; tamper bị từ chối |
| Snapshot/consistency test | Kiểm chứng chính xác mức consistency API cam kết |
| Performance test | EXPLAIN/Buffers, latency theo offset depth, DB CPU/I/O |
| API contract test | `hasMore`/`nextCursor`, 400/403 cho invalid cursor, 404/empty |
| Migration regression | Index và sort fields còn tương thích với cursor cũ |

Không assert cố định rằng PostgreSQL **phải** dùng `Index Scan` trong mọi bộ dữ liệu CI: với bảng rất nhỏ, planner có thể chọn `Seq Scan` hợp lý hơn. Performance regression cần dữ liệu/tải đại diện, một ngưỡng phù hợp và số đo ổn định; functional tests nên assert **kết quả nghiệp vụ**, không assert một execution plan cụ thể.

### Kết quả `hasMore` và race

Giả sử query fetch `size+1` trả đúng size, API phát `hasMore=false`. Ngay sau khi SELECT hoàn tất, một hàng mới xuất hiện với khóa nhỏ hơn lastKey. Nếu client tiếp tục được phép duyệt, hàng đó có thể thuộc trang tiếp; nhưng response cũ đã đúng **theo snapshot của truy vấn vừa chạy**. Nếu hợp đồng đòi push realtime, cần cơ chế cập nhật feed, không thể ép một response cũ dự đoán mọi INSERT tương lai.

Không dùng `COUNT(*) > offset+size` để khẳng định tồn tại trang kế tiếp trong một thời điểm khác nếu query COUNT và query danh sách không cùng snapshot.

## 23. Mã hóa và xác minh cursor bằng chữ ký HMAC

Một cursor HTTP có thể được tạo dưới dạng **opaque Base64URL token** chứa payload đã ký. Dưới đây là ví dụ tối thiểu Java 17, dùng HMAC-SHA256 để bảo vệ **tính toàn vẹn**, không dùng encryption:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

record CursorPayload(
        long tenantId,
        String status,
        int pageSize,
        Instant lastCreatedAt,
        long lastId,
        long expiresAtEpochSeconds) {}

public final class SignedCursorCodec {
    private static final String SORT = "created_at_desc_id_desc";
    private final byte[] hmacKey;
    private final Clock clock;

    // HMAC key lấy từ secret manager; không hardcode trong source code.
    public SignedCursorCodec(byte[] hmacKey, Clock clock) {
        if (hmacKey == null || hmacKey.length < 32) {
            throw new IllegalArgumentException("Signing key quá ngắn");
        }
        this.hmacKey = hmacKey.clone();
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    public String encode(CursorPayload p) {
        validateValues(p);
        String raw = String.join("|",
                "1",
                Long.toString(p.tenantId()),
                p.status(),
                Integer.toString(p.pageSize()),
                SORT,
                p.lastCreatedAt().toString(),
                Long.toString(p.lastId()),
                Long.toString(p.expiresAtEpochSeconds()));
        String body = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
        String signature = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(sign(body));
        return body + "." + signature;
    }

    public CursorPayload decodeAndValidate(
            String token, long authenticatedTenantId,
            String requestedStatus, int requestedPageSize) {
        if (token == null || token.length() > 2048) {
            throw new IllegalArgumentException("Cursor không hợp lệ");
        }
        try {
            String[] tokenParts = token.split("\\.", -1);
            if (tokenParts.length != 2) {
                throw new IllegalArgumentException("Token format");
            }
            byte[] supplied = Base64.getUrlDecoder()
                    .decode(tokenParts[1]);
            if (!MessageDigest.isEqual(
                    sign(tokenParts[0]), supplied)) {
                throw new IllegalArgumentException("Signature mismatch");
            }

            String raw = new String(Base64.getUrlDecoder()
                    .decode(tokenParts[0]), StandardCharsets.UTF_8);
            String[] p = raw.split("\\|", -1);
            if (p.length != 8 ||
                    !"1".equals(p[0]) || !SORT.equals(p[4])) {
                throw new IllegalArgumentException("Version/sort mismatch");
            }
            CursorPayload cursor = new CursorPayload(
                    Long.parseLong(p[1]),
                    p[2],
                    Integer.parseInt(p[3]),
                    Instant.parse(p[5]),
                    Long.parseLong(p[6]),
                    Long.parseLong(p[7]));
            validateValues(cursor);
            if (cursor.expiresAtEpochSeconds()
                    <= clock.instant().getEpochSecond()) {
                throw new IllegalArgumentException("Cursor expired");
            }
            if (cursor.tenantId() != authenticatedTenantId ||
                    !cursor.status().equals(requestedStatus) ||
                    cursor.pageSize() != requestedPageSize) {
                throw new IllegalArgumentException("Scope mismatch");
            }
            return cursor;
        } catch (IllegalArgumentException e) {
            // API có thể map sang 400 hoặc mã lỗi token đã định nghĩa.
            throw new IllegalArgumentException(
                    "Cursor không hợp lệ hoặc hết hạn", e);
        }
    }

    private static void validateValues(CursorPayload p) {
        if (p == null || p.status() == null || p.tenantId() <= 0 ||
                p.lastId() <= 0 || p.pageSize() < 1 ||
                p.pageSize() > 100 || p.lastCreatedAt() == null ||
                p.expiresAtEpochSeconds() <= 0 ||
                !java.util.List.of(
                        "PENDING", "PAID", "SHIPPED", "CANCELLED")
                        .contains(p.status())) {
            throw new IllegalArgumentException("Cursor values invalid");
        }
    }

    private byte[] sign(String encodedBody) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
            return mac.doFinal(
                    encodedBody.getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC unavailable", e);
        }
    }
}
~~~

**Giải thích và giới hạn:**

- Ví dụ trên đủ để minh họa integrity + validation, nhưng **không mã hóa nội dung**. Người có token vẫn có thể giải mã Base64URL và đọc tenant/status/timestamp. Không đưa PII, secret hoặc SQL text vào payload.
- Cùng secret phải có trên các Java instance có nhiệm vụ xác minh; cần quản lý qua secret manager, phân tách môi trường, **key rotation** và chính sách token cũ khi thay key.
- Với cursor có nhiều loại sort/filter, payload phải lưu toàn bộ các yếu tố ảnh hưởng thứ tự, ví dụ customer scope, category, search term/fingerprint, anchor, version; ví dụ chỉ có `status` vì bài thực hành chỉ lọc hai field.
- Ví dụ này xác thực HMAC trên chuỗi Base64URL đã mã hóa. Khi làm đa ngôn ngữ/cross-service, cần quy ước canonical encoding và loại dữ liệu rõ, kiểm thử chữ ký cả ở nơi tạo lẫn nơi đọc.
- Không thực hiện phép đổi sort/filter trong query nếu cursor không cùng phạm vi. Nếu người dùng muốn chuyển filter, **bắt đầu phân trang từ đầu**.
- Không tin tenant trong payload là nguồn quyền: luôn so với principal đáng tin và bind `WHERE tenant_id=?`. HMAC ngăn sửa token nhưng không thay application authorization.
- Khi security yêu cầu ẩn tenant ID/timestamp, có thể dùng AEAD với kiểm tra toàn vẹn và quản lý nonce/key phù hợp, hoặc lưu opaque cursor state phía server thay vì nhồi dữ liệu vào token.

Trong production, nên cân nhắc **schema version, key ID**, giới hạn độ dài và các ký tự lạ, log redaction, expiry, bộ mã hóa dữ liệu ổn định và negative tests; không xem một ví dụ lớp duy nhất là một thư viện token đã được audit.

## 24. Test cursor: giả mạo, tenant khác, hết hạn, đổi sort/filter

Một bộ test cần ít nhất:

| Kịch bản | Kết quả |
| --- | --- |
| Token hợp lệ, đúng tenant/status/pageSize | Parse đúng SeekKey |
| Đổi một ký tự payload | HMAC verification không đạt |
| Đổi hoặc xóa chữ ký | Từ chối |
| Đổi tenant trong request hoặc principal khác | Từ chối dù chữ ký hợp lệ |
| Đổi `status` từ PAID sang CANCELLED | Từ chối |
| Đổi `pageSize` từ 25 sang 100 | Từ chối hoặc yêu cầu bắt đầu lại |
| Token đã hết hạn | Từ chối |
| Payload của phiên bản cũ không còn hỗ trợ | Từ chối an toàn hoặc migration theo chính sách |
| Timestamp không parse được, ID âm hoặc zero | Từ chối |
| Token dài vượt giới hạn | Từ chối trước khi decode nặng |
| Raw cursor có key thuộc tenant khác | Luôn còn điều kiện `WHERE tenant_id=?` |
| Thay sort order nhưng tái dùng cursor cũ | Không được diễn giải với comparator mới |

Một test chữ ký tối thiểu:

~~~java
byte[] testKey = new byte[32];
java.util.Arrays.fill(testKey, (byte) 0x5A);
SignedCursorCodec codec = new SignedCursorCodec(
        testKey,
        java.time.Clock.fixed(
                java.time.Instant.parse("2026-11-22T08:00:00Z"),
                java.time.ZoneOffset.UTC));

CursorPayload payload = new CursorPayload(
        501L, "PAID", 25,
        java.time.Instant.parse("2026-11-22T07:59:00Z"),
        106L,
        java.time.Instant.parse("2026-11-22T09:00:00Z")
                .getEpochSecond());

String token = codec.encode(payload);
assertEquals(payload,
        codec.decodeAndValidate(token, 501L, "PAID", 25));
assertThrows(IllegalArgumentException.class, () ->
        codec.decodeAndValidate(token, 502L, "PAID", 25));
assertThrows(IllegalArgumentException.class, () ->
        codec.decodeAndValidate(token, 501L, "CANCELLED", 25));
~~~

Trong test có thể dùng khóa giả cố định; trong production không đặt key đó trong source. Negative tests không nên chỉ tìm cách đổi HMAC; chúng phải kiểm tra **phân quyền thực** ở repository và service khi token đã được ký đúng nhưng người dùng không còn quyền truy cập resource.

## 25. Vòng đời transaction, connection pool và timeout

Một API phân trang nên trả connection về pool sau khi tải xong trang:

~~~text
HTTP request N
  -> authenticate principal
  -> validate filter/cursor
  -> acquire JDBC connection
  -> SELECT ... LIMIT size+1
  -> consume ResultSet; map DTO
  -> close ResultSet / PreparedStatement / Connection
  -> serialize HTTP response

HTTP request N+1
  -> xác thực lại principal và cursor
  -> acquire một connection (có thể là connection khác)
  -> SELECT trang tiếp, trong transaction/snapshot mới
~~~

Các điểm thực tế:

- **Không giữ `ResultSet` hoặc JDBC connection trong HTTP session** chỉ để chờ client nhấn “Next”.
- Không dùng một transaction dài qua nhiều request nếu không có yêu cầu snapshot rõ, vì giữ tài nguyên, snapshot và lock lâu.
- Với ORM, tránh trả trực tiếp managed entity rồi để serializer lazy-load association ngoài transaction; sử dụng projection/DTO và fetch có kiểm soát.
- Đặt statement/query timeout, network timeout và giới hạn page size phù hợp với SLO; xem riêng pool acquisition time và SQL execute/fetch.
- Khi query timeout, không tự động tăng `OFFSET` hay đổi cursor sang một hàng khác; chỉ retry một request đọc **với cùng filter/cursor** nếu hợp đồng, deadline và consistency cho phép.
- Nếu JDBC driver mất kết nối giữa lúc fetch, response có thể chưa trả đủ kết quả; thường phải từ chối/khởi động lại trang chứ không tự ghép hai partial result với snapshot khác nhau.

**Góc nhìn transaction isolation:** Mỗi lần SELECT ở `READ COMMITTED` thường đọc một snapshot của statement tại thời điểm truy vấn trên PostgreSQL. Giữa request N và N+1 có thay đổi là điều bình thường. `REPEATABLE READ` bên trong **một request** không tự kéo dài snapshot sang request sau nếu transaction đã kết thúc.

## 26. Tình huống thực tế: khi nào OFFSET là lựa chọn tốt?

Một bảng quản trị có khoảng 2.000 kết quả sau khi filter, người vận hành cần:

- Đến ngay trang 7 hoặc trang 19.
- Nhìn số trang/tổng kết quả chính xác ở thời điểm truy vấn.
- Sắp xếp theo vài cột khác nhau, có cả ASC/DESC và có thể NULL.
- Thường làm việc trong một khoảng thời gian ngắn, dữ liệu ít biến động.

Trong trường hợp này, **offset hoàn toàn có thể hợp lý**. Một số tối ưu:

1. Dùng điều kiện lọc đủ chọn lọc để giới hạn tập kết quả.
2. Sắp xếp bằng cột có tie-breaker duy nhất.
3. Index theo workload thực tế, không tự động thêm index cho mọi sort.
4. Giới hạn `pageSize` và **độ sâu tối đa cho phép**; với deep pages, đề xuất filter hẹp hơn hoặc export.
5. Đo chi phí `COUNT(*)`, tránh gửi COUNT chính xác trong mọi request nếu không cần.
6. Khi dữ liệu biến động nhanh, giải thích rằng trang 2 là **trang của một kết quả mới**, không bảo đảm đúng tập snapshot từ trang 1.

Offset không phải anti-pattern mọi nơi; **dùng offset vô hạn trên bảng khổng lồ rồi hứa kết quả ổn định khi chèn/xóa đồng thời** mới là thiết kế cần xem lại.

## 27. Tình huống thực tế: khi nào KEYSET có lợi thế rõ?

Một API sự kiện hoặc đơn hàng cần cuộn mới → cũ:

- Tập kết quả có hàng chục triệu bản ghi trong nhiều năm.
- Người dùng hiếm khi nhảy tới “trang N”, mà chỉ liên tục nhấn “Tải thêm”.
- Sắp xếp bằng trường thời gian/ID ổn định, có index tương ứng.
- Dữ liệu mới thường xuất hiện ở đầu danh sách.
- Không cần tính tổng số hàng mỗi lần cuộn.

**Keyset** có lợi vì:

- Tập điều kiện seek cho phép DB bắt đầu gần khóa tiếp tục.
- Độ trễ trang sâu có thể tăng ít hơn so với offset khi query/index phù hợp.
- INSERT mới phía trước cursor thường không làm trang sau lặp hàng đã thấy.
- Có thể phát `nextCursor` chỉ bằng khóa hàng cuối và một bản ghi thăm dò.

Nhưng cần chấp nhận:

- Không nhảy ngẫu nhiên đến trang 10.000 nếu không có anchor.
- Cursor chứa trạng thái sort/filter/version và phải được xác minh.
- Đảo chiều phân trang phức tạp hơn.
- Sort key mutable, filter mutable và replica lag có thể làm kết quả thay đổi.
- “Đã cuộn hết” có nghĩa trong điều kiện ở thời điểm query, không phải đóng băng tập dữ liệu vĩnh viễn.

## 28. Bài tập tổng hợp: lựa chọn và chứng minh

Thiết kế hai endpoint:

~~~text
GET /api/orders?status=PAID&page=5&size=20
GET /api/orders?status=PAID&size=20&after=<signed-cursor>
~~~

Dataset thử nghiệm:

- Tenant 501: 1.000.000 đơn, nhiều đơn có timestamp trùng đến microsecond.
- Tenant 502: 20.000 đơn, dùng chung bảng vật lý.
- Các trạng thái `PENDING`, `PAID`, `SHIPPED` và `CANCELLED` thay đổi theo vòng đời.
- Có job nhập dữ liệu lịch sử tạo đơn với `created_at` trong quá khứ.
- Có read replica chậm hơn primary trong những đợt ghi lớn.

**Nhiệm vụ:**

1. Viết `CREATE INDEX` phù hợp với query lọc tenant + status và thứ tự DESC.
2. Tại sao chỉ dùng `ORDER BY created_at DESC` là chưa đủ?
3. Viết SQL offset cho trang 5 size 20 và tính offset cụ thể.
4. Viết SQL keyset khi cursor chứa `created_at = 2026-11-22T09:00:01Z`, `id = 106`.
5. Sau khi trang 1 trả 20 hàng, một đơn mới xuất hiện ở đầu; hai cách có thể khác nhau như thế nào ở trang 2?
6. Nếu các đơn có timestamp trùng nhau, điều kiện `created_at < cursorTime` **một mình** gây lỗi gì?
7. Vì sao không trả `totalPages` “miễn phí” ở keyset?
8. Với dữ liệu nhập lịch sử tạo timestamp cũ, anchor trên timestamp có còn ngăn mọi INSERT mới không?
9. Nếu cursor của tenant 501 được gửi bởi người thuộc tenant 502, điều gì phải xảy ra?
10. Khi người dùng đổi `status=PAID` sang `status=SHIPPED`, có được tái dùng cursor cũ không?
11. Làm thế nào kiểm chứng query keyset sâu nhanh hơn mà không benchmark sai vị trí?
12. Nếu sản phẩm yêu cầu export chính xác tập dữ liệu tại một thời điểm, dùng một vòng nextCursor qua HTTP có đủ không?

### Gợi ý lời giải

1. `(tenant_id, status, created_at DESC, id DESC)` là một index phù hợp với workload chính; đo EXPLAIN để xác nhận planner.
2. Timestamp trùng dẫn đến thứ tự không đầy đủ; cần `id DESC` làm tie-breaker.
3. `(5 - 1) × 20 = 80`, dùng `LIMIT 20 OFFSET 80`.
4. Dùng `(created_at,id) < (cursorTime,106)` cùng tenant/status, `ORDER BY created_at DESC,id DESC` và `LIMIT size+1`.
5. Offset có thể lặp hàng do vị trí dịch, keyset thường tiếp tục sau khóa cuối đã thấy khi sort key bất biến.
6. Bỏ sót những hàng có timestamp bằng cursor nhưng ID nhỏ hơn; phải dùng tuple comparison.
7. Keyset không đếm toàn bộ tập kết quả; muốn total chính xác vẫn cần query riêng/cơ chế thống kê.
8. Không. Backdated insert dưới anchor có thể vẫn xuất hiện trong các trang sau; anchor không thay snapshot.
9. Từ chối token sai scope và luôn bind tenant từ principal đáng tin; không tiết lộ dữ liệu qua cursor.
10. Không; filter là một phần hợp đồng cursor, phải bắt đầu từ đầu.
11. Lấy khóa ở vị trí tương ứng trong môi trường test, so hai query với cùng filters/index/data; đo buffers, execution time và end-to-end latency nhiều lần.
12. Không. Cần snapshot/job export và quy tắc consistency/timeout riêng; cursor qua request độc lập không đóng băng dữ liệu.

## 29. Checklist trước khi triển khai hai cách phân trang

1. **Hợp đồng UI:** cần nhảy trang bất kỳ, số trang hay chỉ cuộn tiếp?
2. **Sort:** `ORDER BY` có tất cả khóa cần thiết và tie-breaker duy nhất?
3. **Nullable:** sort key có NULL không; nếu có, đã quy định `NULLS FIRST/LAST` và seek predicate đúng?
4. **Filter:** mọi request dùng đúng tenant/customer scope từ principal đáng tin, không từ payload cursor tùy ý?
5. **Index:** điều kiện equality, sort direction và projection đã được benchmark trên workload đại diện?
6. **Offset:** giới hạn page size/page number/offset, không overflow; deep pages có plan được đo?
7. **Keyset:** comparator khớp thứ tự, tuple đầy đủ, dùng key của hàng **cuối đã hiển thị**, không phải hàng thăm dò?
8. **Cursor:** ký integrity hoặc dùng server-side state, version/expiry, filter/sort/tenant binding, không chứa bí mật?
9. **Ngược trang:** dùng first key, đảo comparator và đảo thứ tự kết quả đúng?
10. **COUNT:** total là số chính xác hay ước lượng; thời điểm/snapshot nào?
11. **Concurrency:** đã thử INSERT/DELETE/UPDATE ở đầu, giữa và sau cursor?
12. **Snapshot:** đã nêu rõ consistency contract; keyset không hứa exactly-once traversal trên dữ liệu thay đổi?
13. **Replica/cache:** có chiến lược read-your-writes, lag, cache scoping và invalidation?
14. **JDBC/ORM:** dùng bound parameters, resource closing, fetch/page limit, tránh N+1/lazy load ngoài dự kiến?
15. **Timeout:** có query/connection timeout, phương án trả lỗi và khả năng retry đọc mà không đổi cursor?
16. **Test:** có integration tests với PostgreSQL thật, timestamp trùng, cursor invalid, tenant cross-access?
17. **Benchmark:** đo p50/p95, EXPLAIN BUFFERS, số hàng phải bỏ qua, CPU/I/O và chi phí COUNT?
18. **Vận hành:** theo dõi query chậm, index bloat, page-size abuse, error rate và thay đổi plan sau migration?

**Kết luận:** Offset và keyset là hai giao thức **duyệt kết quả đã sắp xếp**, không chỉ là hai cú pháp SQL. `LIMIT/OFFSET` đơn giản, hỗ trợ nhảy trang và đếm tổng dễ diễn đạt, nhưng trang sâu có thể tốn chi phí bỏ qua hàng và dễ dịch vị trí khi chèn/xóa đồng thời. Keyset dùng **khóa sắp xếp toàn phần** và một cursor được bảo vệ để tiếp tục từ đúng vị trí logic; nó thường phù hợp với luồng “Tải thêm” dài và có index tốt, nhưng không tự tạo snapshot, không miễn phí khi nhảy trang tùy ý và phải xử lý sort/filter thay đổi. Thiết kế đúng là chọn cách phân trang theo UX và tính đúng đắn cần cam kết, **kiểm chứng bằng PostgreSQL/JDBC thật**, kiểm soát tenant/cursor và đo hiệu năng trên dữ liệu đại diện trước khi tối ưu.
