# Thứ tự trường trong chỉ mục và dạng điều kiện truy vấn

Trong một ứng dụng Java, hai câu SQL cùng dùng các trường của một bảng có thể có thời gian thực thi rất khác nhau. Một nguyên nhân thường gặp là **thứ tự cột trong chỉ mục ghép** không phù hợp với điều kiện lọc và thứ tự sắp xếp của truy vấn. Hiểu cách cơ sở dữ liệu đi qua các khóa trong chỉ mục giúp thiết kế truy vấn có thể mở rộng khi số bản ghi tăng lên, đồng thời tránh tạo chỉ mục thừa.

Bài này thuộc phần **Chỉ mục** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Kiến thức được đặt trong bối cảnh thiết kế ranh giới persistence cho Java: lựa chọn mô hình dữ liệu và truy vấn, tối ưu truy cập, giữ tính đúng đắn của phân trang và kiểm tra hiệu năng trên dữ liệu thực tế. Ví dụ dùng cú pháp **PostgreSQL và B-tree** để giải thích cụ thể; các nguyên lý tổ chức khóa có ích với nhiều hệ quản trị quan hệ, nhưng quy tắc tối ưu hóa, hỗ trợ chỉ mục và kế hoạch thực thi có thể khác nhau giữa các hệ.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Giải thích vì sao chỉ mục ghép **(a, b, c)** thường hữu ích nhất khi truy vấn ràng buộc các cột bên trái trước.
- Phân biệt điều kiện bằng, danh sách giá trị, khoảng, tiền tố chuỗi, phủ định và biểu thức trên cột; dự đoán khả năng tận dụng chỉ mục.
- Chọn thứ tự cột theo **tập truy vấn thực tế**, bao gồm điều kiện lọc, **ORDER BY** và **LIMIT**.
- Tạo một truy vấn có tham số từ Java, sử dụng phân trang ổn định và đánh giá kế hoạch thực thi trước khi quyết định giữ một chỉ mục.

## 2. Cách một chỉ mục nhiều cột sắp xếp dữ liệu

Giả sử bảng có chỉ mục B-tree trên **(tenant_id, status, created_at)**. Có thể hình dung các mục chỉ mục được sắp xếp theo bộ khóa:

1. So sánh **tenant_id** trước.
2. Khi **tenant_id** bằng nhau, so sánh **status**.
3. Khi hai cột đầu bằng nhau, so sánh **created_at**.

Ví dụ các khóa được sắp xếp tăng dần:

~~~text
(10, 'CANCELLED', 2026-01-03)
(10, 'PAID',      2026-01-01)
(10, 'PAID',      2026-01-04)
(20, 'CANCELLED', 2026-01-02)
(20, 'PAID',      2026-01-05)
~~~

Với **tenant_id = 10 AND status = 'PAID'**, cơ sở dữ liệu có thể tìm đến một vùng khóa liên tiếp tương ứng, rồi đọc các bản ghi theo thời gian. Nếu chỉ có **status = 'PAID'**, những khóa phù hợp nằm rải rác giữa các tenant; chỉ mục này khó cung cấp một khoảng tìm kiếm liên tục nhỏ. Tùy hệ quản trị và thống kê, trình tối ưu vẫn có thể quét chỉ mục, sử dụng kỹ thuật như skip scan hoặc chọn cách truy cập khác. Vì vậy, **quy tắc tiền tố trái là nguyên tắc thiết kế, không phải lời khẳng định rằng mọi truy vấn thiếu cột đầu đều không thể dùng chỉ mục**.

Phải phân biệt ba khả năng của một cột trong chỉ mục:

| Khả năng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Giới hạn vùng tìm kiếm** | Giúp xác định vị trí bắt đầu/kết thúc cần đọc trong B-tree | tenant_id = 10, status = 'PAID' |
| **Lọc trong khi đọc** | Có thể loại bớt mục sau khi đã tới một vùng rộng hơn, không nhất thiết thu hẹp vùng ban đầu | tenant_id = 10 AND created_at >= mốc, khi status nằm giữa hai cột |
| **Cung cấp thứ tự hoặc dữ liệu** | Có thể tránh sắp xếp lại hoặc hỗ trợ đọc cột có sẵn trong chỉ mục | ORDER BY created_at, id; truy vấn chỉ lấy các cột có trong chỉ mục |

Một cột không còn giúp thu hẹp khoảng tìm kiếm vẫn có thể hữu ích cho hai khả năng còn lại. Kế hoạch thực thi cụ thể phụ thuộc vào bộ tối ưu.

## 3. Tiền tố trái, điều kiện bằng và điều kiện khoảng

Xét chỉ mục **(a, b, c)** trong B-tree:

| Điều kiện WHERE | Cách tận dụng điển hình |
| --- | --- |
| a = ? | Có tiền tố **a**, tìm được nhóm khóa theo a |
| a = ? AND b = ? | Tìm được nhóm khóa theo **(a, b)** |
| a = ? AND b = ? AND c = ? | Có thể giới hạn theo cả ba cột |
| a = ? AND b BETWEEN ? AND ? | Dùng a bằng và một khoảng trên b; c phía sau thường không tiếp tục thu hẹp một khoảng tìm kiếm đơn giản |
| a = ? AND c = ? | a giới hạn vùng tìm; c có thể được kiểm tra trong vùng đó nhưng b chưa được ràng buộc |
| b = ? AND c = ? | Không có tiền tố a; có thể phải quét rộng hoặc dùng kế hoạch khác |
| a IN (?, ?) AND b = ? | Có thể xử lý thành nhiều nhánh tìm kiếm; không đồng nghĩa với một giá trị bằng duy nhất của a |

Một quy tắc thực dụng cho truy vấn tìm kiếm theo khoảng là **các điều kiện bằng trên tiền tố trước, rồi đến cột khoảng**. Chẳng hạn, với **(tenant_id, status, created_at)**:

~~~sql
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
~~~

Cơ sở dữ liệu có thể giới hạn vùng quét theo tenant, trạng thái, rồi theo thời điểm. Ngược lại:

~~~sql
WHERE tenant_id = 10
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
~~~

với cùng chỉ mục sẽ thiếu điều kiện trên **status**, khiến các bản ghi của nhiều trạng thái trong tenant xen kẽ nhau trước khi xét **created_at**. Khi truy vấn này phổ biến, một chỉ mục **(tenant_id, created_at)** thường phù hợp hơn.

**Lưu ý về cột sau điều kiện khoảng:** Câu nói “gặp khoảng là các cột sau vô dụng” là sai. Ví dụ chỉ mục **(tenant_id, status, created_at DESC, id DESC)** vẫn có thể trả dữ liệu đúng thứ tự **created_at DESC, id DESC** sau khi lọc bằng tenant và status, kể cả khi có điều kiện khoảng trên **created_at**. Điều thường bị hạn chế là khả năng dùng cột sau khoảng để **thu hẹp thêm vùng tìm kiếm**, không phải mọi công dụng của cột đó.

## 4. Bài toán đơn hàng: chọn chỉ mục theo câu truy vấn

Giả sử hệ thống nhiều khách hàng tổ chức (multi-tenant) có bảng:

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
);
~~~

Màn hình vận hành cần hiển thị **50 đơn PAID mới nhất của một tenant**, trong khoảng thời gian nhất định:

~~~sql
SELECT id, status, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Một ứng viên hợp lý:

~~~sql
CREATE INDEX idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Cấu trúc này có chủ đích:

- **tenant_id** và **status** là hai điều kiện bằng giúp đi đến nhóm khóa cần tìm.
- **created_at DESC** hỗ trợ quét các đơn mới trước, đồng thời phục vụ khoảng thời gian.
- **id DESC** tạo thứ tự duy nhất khi nhiều đơn có cùng **created_at**; điều này quan trọng cho phân trang.
- **LIMIT 50** cho phép dừng sớm nếu tìm đủ bản ghi phù hợp; mức tiết kiệm phụ thuộc kế hoạch, điều kiện và phân bố dữ liệu.

Hình dung đường đi của truy vấn:

~~~text
Index (tenant_id, status, created_at DESC, id DESC)
          |           |           |              |
        bằng        bằng       khoảng +        khóa phụ
                               sắp xếp        sắp xếp
~~~

Không có nghĩa đây là chỉ mục tốt cho mọi truy vấn trên bảng **orders**. Nếu màn hình khác liệt kê tất cả đơn mới nhất **không phân biệt status**:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 10
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

thì chỉ mục **(tenant_id, status, created_at DESC, id DESC)** sắp xếp các đơn theo **status trước created_at**. Nó không đảm bảo toàn bộ các trạng thái đã được đan xen theo thời gian như yêu cầu. Một ứng viên đúng hướng là:

~~~sql
CREATE INDEX idx_orders_tenant_recent
ON orders (tenant_id, created_at DESC, id DESC);
~~~

Hai chỉ mục phục vụ hai nhu cầu khác nhau. Chỉ nên giữ cả hai nếu khối lượng truy vấn, hiệu năng đo được và chi phí ghi dữ liệu biện minh cho điều đó.

### Khi nào cần đổi thứ tự hai cột đều dùng dấu bằng?

Ví dụ **(tenant_id, status, created_at)** và **(status, tenant_id, created_at)** đều có thể giới hạn tốt truy vấn luôn truyền **tenant_id = ? AND status = ?**. Việc đặt cột “có độ chọn lọc cao nhất” trước **không phải luật bất biến**. Hãy xem những truy vấn khác có dùng riêng tiền tố **tenant_id** hay **status**; trong hệ thống nhiều tenant, điều kiện tenant thường là đường truy cập phổ biến và còn là ranh giới dữ liệu cần duy trì nhất quán.

## 5. Dạng điều kiện WHERE thay đổi khả năng sử dụng B-tree

| Dạng điều kiện | Đặc điểm và gợi ý |
| --- | --- |
| **=** | Thường thích hợp nhất để cố định từng cột đầu trong khóa ghép |
| **IN (...)** | Có thể mở thành nhiều giá trị/nhánh; hiệu quả phụ thuộc số phần tử, thống kê và truy vấn đi kèm |
| **>, >=, <, <=, BETWEEN** | Tạo điều kiện khoảng; hay đặt sau các cột bằng. **BETWEEN** lấy cả hai đầu, nên với thời gian thường ưu tiên **>= đầu AND < cuối** |
| **IS NULL** | Nhiều hệ B-tree, trong đó có PostgreSQL, lưu khóa NULL và có thể tìm theo NULL; vẫn cần kiểm tra thống kê và kế hoạch |
| **<> / != / NOT IN** | Thường khó thu hẹp một vùng nhỏ nếu phần lớn bảng thỏa mãn; không mặc định rằng index scan sẽ nhanh |
| **LIKE 'abc%'** | Tìm tiền tố có thể dùng B-tree với cấu hình collation/operator class thích hợp; cần kiểm tra theo hệ quản trị |
| **LIKE '%abc' hoặc '%abc%'** | B-tree thông thường không đi thẳng đến phần bắt đầu chuỗi; cân nhắc full-text hoặc trigram khi cần tìm đoạn con |
| **OR** giữa nhiều cột | Bộ tối ưu có thể kết hợp nhiều chỉ mục, dùng bitmap hoặc quét bảng; không bảo đảm một chỉ mục ghép xử lý tối ưu |
| **Hàm/cast trên cột** | Có thể làm điều kiện không còn sử dụng trực tiếp thứ tự khóa gốc; cân nhắc viết lại điều kiện hoặc chỉ mục biểu thức |

### 5.1. Ví dụ với thời điểm

Điều kiện sau chuyển đổi trực tiếp cột **created_at**:

~~~sql
-- Ví dụ PostgreSQL: cột được chuyển thành DATE.
WHERE created_at::date = DATE '2026-01-15'
~~~

Chỉ mục B-tree thường trên **created_at** không lưu sẵn kết quả biểu thức **created_at::date**. Nếu nghiệp vụ tính ngày theo **UTC**, hãy chuyển ngày thành khoảng nửa mở trên cột gốc:

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-01-15 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-01-16 00:00:00+00'
~~~

Khoảng **[đầu ngày, đầu ngày kế tiếp)** tránh bỏ sót các mốc có phần giây nhỏ và không cần đoán “thời điểm cuối ngày”. Nếu nghiệp vụ dùng múi giờ khác UTC, phải chuyển đúng **hai ranh giới ngày địa phương** sang thời điểm tuyệt đối; ngày có đổi giờ mùa hè có thể không dài đúng 24 giờ.

Khi thực sự cần truy vấn theo một biểu thức cố định, PostgreSQL còn hỗ trợ **expression index**, nhưng biểu thức trong truy vấn phải tương thích với chỉ mục và quy tắc của hệ quản trị. Không nên thêm chỉ mục biểu thức chỉ để sửa một truy vấn có thể viết bằng điều kiện khoảng đơn giản.

### 5.2. Điều kiện IN và thứ tự sắp xếp

Với chỉ mục **(tenant_id, status, created_at DESC)**, câu lệnh:

~~~sql
WHERE tenant_id = 10
  AND status IN ('NEW', 'PAID')
ORDER BY created_at DESC
~~~

có thể lấy dữ liệu từ nhiều nhóm **status**. Mỗi nhóm được sắp theo thời gian, nhưng ghép hai nhóm lại **chưa chắc** đã theo thời gian toàn cục. Bộ tối ưu có thể phải sắp xếp/ghép kết quả. Đừng coi **IN** nhiều giá trị tương đương một dấu **=** khi đánh giá khả năng phục vụ **ORDER BY**.

## 6. Kết hợp WHERE, ORDER BY và LIMIT

Để một chỉ mục phục vụ đồng thời việc lọc và thứ tự trả về, cần xem **cả thứ tự khóa và điều kiện cố định phía trước**.

Với chỉ mục **(tenant_id, status, created_at DESC, id DESC)**:

| Truy vấn | Nhận xét |
| --- | --- |
| tenant_id = ? AND status = ?; ORDER BY created_at DESC, id DESC | Phù hợp để đọc theo đúng thứ tự từ nhóm khóa đã giới hạn |
| tenant_id = ?; ORDER BY created_at DESC, id DESC | status không cố định nên thứ tự thời gian toàn tenant không được bảo đảm từ chỉ mục này |
| tenant_id = ? AND status = ?; ORDER BY created_at ASC, id ASC | PostgreSQL có thể quét ngược B-tree để phục vụ hai chiều đảo đồng thời |
| tenant_id = ? AND status = ?; ORDER BY created_at DESC, id ASC | Hai chiều trộn khác cấu hình khóa; có thể cần chỉ mục theo chiều trộn hoặc một bước sort |
| tenant_id = ? AND status = ?; ORDER BY total_amount DESC | total_amount không thuộc thứ tự khóa; thường cần sort hoặc chỉ mục khác |

Hệ quản trị có thể hỗ trợ **backward scan**, **incremental sort** hay lựa chọn kế hoạch tương đương. Khi có **NULL**, collation hoặc biểu thức trong ORDER BY, cần kiểm tra chính xác quy tắc thứ tự tương ứng.

### Phân trang ổn định bằng keyset

Phân trang kiểu **OFFSET 100000 LIMIT 50** vẫn phải xử lý số lượng lớn mục trước trang cần lấy, kể cả khi có chỉ mục phù hợp. Với dữ liệu tăng liên tục, cách **keyset/cursor** thường tốt hơn nếu người dùng chủ yếu bấm “xem tiếp”.

Trang đầu:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Giả sử bản ghi cuối trang đầu có **created_at = :lastCreatedAt** và **id = :lastId**. Trong PostgreSQL, trang tiếp theo có thể dùng so sánh bộ:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Đây là cú pháp tham số đặt tên thường dùng trong JPA/Spring Data; với JDBC thuần cần thay bằng dấu **?**. Vì **created_at** và **id** đều **NOT NULL** và được sắp giảm dần, so sánh bộ **<** có ý nghĩa “đứng sau con trỏ” trong thứ tự này. Các hệ quản trị khác có thể cần diễn đạt lại điều kiện hoặc có cách tối ưu khác.

Luôn truyền đủ **tenant_id** và các điều kiện lọc của trang trước; lưu cả hai thành phần của con trỏ. Chỉ dùng **created_at** sẽ có nguy cơ bỏ sót/trùng bản ghi cùng thời điểm. Keyset vẫn cần một quy tắc nhất quán để xử lý bản ghi mới hoặc bản ghi bị sửa giữa hai lần tải; khi cần một ảnh chụp dữ liệu cố định, phải kết hợp cơ chế snapshot/transaction phù hợp với nghiệp vụ.

## 7. Đưa truy vấn vào Java an toàn và đúng kiểu

Tầng persistence nên truyền điều kiện dưới dạng **tham số**, không nối trực tiếp chuỗi SQL từ dữ liệu người dùng. Ví dụ JDBC sau tương ứng với chỉ mục của màn hình tìm đơn theo status và thời gian:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record OrderSummary(
            long id,
            String status,
            OffsetDateTime createdAt,
            BigDecimal totalAmount
    ) {}

    public List<OrderSummary> findRecent(
            long tenantId,
            String status,
            OffsetDateTime fromInclusive,
            OffsetDateTime toExclusive,
            int pageSize
    ) throws SQLException {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize phải trong [1, 100]");
        }

        String sql = """
            SELECT id, status, created_at, total_amount
            FROM orders
            WHERE tenant_id = ?
              AND status = ?
              AND created_at >= ?
              AND created_at < ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        List<OrderSummary> result = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setString(2, status);
            statement.setObject(3, fromInclusive);
            statement.setObject(4, toExclusive);
            statement.setInt(5, pageSize);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    result.add(new OrderSummary(
                            rows.getLong("id"),
                            rows.getString("status"),
                            rows.getObject("created_at", OffsetDateTime.class),
                            rows.getBigDecimal("total_amount")
                    ));
                }
            }
        }
        return result;
    }
}
~~~

Mẫu này giả định Java hỗ trợ **text block/record** và PostgreSQL JDBC hỗ trợ ánh xạ **TIMESTAMPTZ ↔ OffsetDateTime**. Ứng dụng thực tế còn cần xác thực quyền truy cập tenant trước khi gọi repository, kiểm tra khoảng ngày hợp lệ, giới hạn kích thước trang và phân loại lỗi kết nối/truy vấn theo chính sách của tầng persistence. **Chỉ mục giúp tăng tốc; chỉ mục không thay thế kiểm soát quyền truy cập hoặc xử lý lỗi.**

Nếu dùng ORM như JPA, vẫn cần xem SQL cuối cùng ORM tạo ra, đặc biệt khi có truy vấn động, eager loading, JOIN, phân trang và chuyển đổi kiểu dữ liệu. Tên method trong repository không nói lên việc truy vấn có tận dụng được chỉ mục hay không.

## 8. Khi một chỉ mục chưa đủ: cân bằng đọc, ghi và kích thước

### 8.1. Các mẫu truy vấn khác nhau có thể cần khóa khác nhau

| Nhu cầu thường xuyên | Chỉ mục ứng viên |
| --- | --- |
| Đơn của một tenant theo một status, mới nhất trước | **(tenant_id, status, created_at DESC, id DESC)** |
| Tất cả đơn của một tenant, mới nhất trước | **(tenant_id, created_at DESC, id DESC)** |
| Lịch sử đơn của một khách hàng trong tenant | **(tenant_id, customer_id, created_at DESC, id DESC)** |
| Tìm theo khoảng giá trong một danh mục | **(category_id, price, id)** trên bảng sản phẩm phù hợp |

Không tạo cả bốn chỉ mục chỉ dựa trên bảng gợi ý. Hãy đo tần suất, số bản ghi trả về, thời gian đích, phân bố giá trị và chi phí ghi. Mỗi lần **INSERT**, **UPDATE** cột thuộc chỉ mục hoặc **DELETE** đều có thể tạo thêm công việc bảo trì chỉ mục, tăng dung lượng và ảnh hưởng cache.

### 8.2. Covering index và cột INCLUDE

PostgreSQL cho phép lưu cột chỉ dùng để trả kết quả mà không biến nó thành thành phần sắp xếp của khóa:

~~~sql
CREATE INDEX idx_orders_tenant_status_recent_cover
ON orders (tenant_id, status, created_at DESC, id DESC)
INCLUDE (total_amount);
~~~

Nếu truy vấn chỉ cần các cột này, hệ quản trị **có thể** chọn index-only scan. Trong PostgreSQL, việc có thật sự tránh đọc heap còn phụ thuộc trạng thái visibility map của MVCC; INCLUDE cũng làm chỉ mục lớn hơn. Đây là ứng viên **thay thế** cho chỉ mục tương đương thiếu INCLUDE khi đo đạc chứng minh lợi ích, không phải mặc định giữ cả hai.

### 8.3. Partial index và truy vấn có tham số

Nếu phần lớn lưu lượng chỉ đọc đơn đã thanh toán và nhóm này chiếm tỷ lệ nhỏ, PostgreSQL hỗ trợ chỉ mục có điều kiện:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON orders (tenant_id, created_at DESC, id DESC)
WHERE status = 'PAID';
~~~

Chỉ mục này chỉ chứa hàng có **status = 'PAID'**. Bộ tối ưu cần chứng minh truy vấn thỏa điều kiện của partial index; khi status được truyền qua tham số và PostgreSQL chọn **generic plan**, không phải lúc nào điều đó cũng chứng minh được. Vì thế, phải kiểm tra với cách ứng dụng thật sự gửi truy vấn và với giá trị tham số điển hình.

## 9. Kiểm tra bằng kế hoạch thực thi

Thiết kế chỉ mục là một **giả thuyết cần đo**, không phải bằng chứng rằng truy vấn sẽ nhanh. Trên cơ sở dữ liệu thử nghiệm có lượng dữ liệu và phân bố đủ giống thực tế:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

**EXPLAIN ANALYZE thực sự chạy câu lệnh**, vì vậy nên thực hiện trên môi trường phù hợp, có kiểm soát tải. Khi đọc kết quả, tập trung vào:

- **Index Scan / Index Only Scan / Bitmap Heap Scan / Seq Scan:** PostgreSQL chọn cách truy cập nào; quét tuần tự đôi khi tốt hơn khi bảng nhỏ hoặc truy vấn lấy tỷ lệ lớn bản ghi.
- **Index Cond** so với **Filter:** điều kiện nào đã giúp giới hạn/lọc trong đường truy cập chỉ mục, điều kiện nào còn được lọc sau.
- **Sort:** có phát sinh bước sắp xếp vì thứ tự khóa không phù hợp không; số dòng và bộ nhớ/đĩa dùng cho sort.
- **actual rows, loops, actual time, Buffers:** lượng việc thật và lượng dữ liệu đọc; so với ước lượng để nhận biết thống kê sai lệch hoặc phân bố không đồng đều.
- **Giá trị tham số và dữ liệu lệch (skew):** tenant rất lớn, status phổ biến và tenant nhỏ có thể nhận kế hoạch khác nhau. Đo cả trường hợp điển hình lẫn trường hợp xấu.

Quy trình đánh giá có thể thực hiện như sau:

1. Ghi nhận truy vấn chậm thật, SQL thực tế, kích thước dữ liệu, số lần gọi và mục tiêu độ trễ.
2. Kiểm tra kế hoạch hiện tại; ghi nhận sort, số bản ghi quét, số bản ghi trả về và I/O.
3. Đề xuất thứ tự cột theo **WHERE + ORDER BY + LIMIT**; tạo một chỉ mục ứng viên trong môi trường thử nghiệm.
4. Đo lại với cùng tập dữ liệu và tham số, cả lúc dữ liệu thường xuyên được cập nhật; xem tác động đến truy vấn khác và tốc độ ghi.
5. Chỉ triển khai chỉ mục khi lợi ích được đo có ý nghĩa; theo dõi hiệu năng và dung lượng sau khi triển khai.

Nếu **Index Scan** không xuất hiện, điều đó chưa tự động chứng minh chỉ mục sai: bảng nhỏ, truy vấn thiếu tính chọn lọc, thống kê cũ, truy vấn dùng biểu thức không tương thích, kiểu tham số, hoặc chi phí đọc ngẫu nhiên đều có thể khiến bộ tối ưu chọn kế hoạch khác.

## 10. Những lỗi thiết kế thường gặp

1. **Đặt cột lọc theo khoảng trước các điều kiện bằng thường xuyên dùng.** Ví dụ ưu tiên **(created_at, tenant_id)** cho màn hình luôn lọc tenant và khoảng ngày có thể khiến phạm vi đọc lớn hơn **(tenant_id, created_at)**.
2. **Chỉ xét WHERE, bỏ qua ORDER BY.** Chỉ mục có status nằm trước created_at chưa chắc sắp được toàn bộ đơn của tenant theo thời gian.
3. **Áp dụng máy móc “cột chọn lọc nhất đứng đầu”.** Với nhiều dấu bằng, hiệu quả thực tế còn phụ thuộc các truy vấn sử dụng từng tiền tố và nhu cầu sắp xếp.
4. **Xem điều kiện khoảng là điểm kết thúc mọi lợi ích.** Cột phía sau vẫn có thể phục vụ sắp xếp, lọc bổ sung hay cung cấp dữ liệu.
5. **Dùng hàm trực tiếp trên cột khóa dù có thể viết điều kiện khoảng.** Ví dụ ép created_at sang ngày có thể làm mất khả năng tìm theo B-tree thông thường.
6. **Phân trang chỉ theo một cột không duy nhất.** Khi nhiều bản ghi cùng created_at, thứ tự thiếu id sẽ không ổn định.
7. **Thêm hàng loạt chỉ mục chồng lắp mà không đo.** Chỉ mục tiêu tốn lưu trữ, cache và chi phí ghi; một thiết kế tối ưu cho đọc chưa chắc tối ưu tổng thể.
8. **Dựa vào giả định an toàn từ chỉ mục hoặc bộ lọc tại giao diện.** Ứng dụng phải kiểm tra quyền tenant ở tầng nghiệp vụ/truy cập dữ liệu và tham số hóa SQL.

## 11. Tự kiểm tra

**Tình huống A.** Có chỉ mục **(department_id, salary, employee_id)**. Truy vấn lọc **department_id = ? AND salary BETWEEN ? AND ?**, rồi sắp theo **salary ASC, employee_id ASC**. Chỉ mục có thể hỗ trợ điều gì?

**Gợi ý đáp án:** Điều kiện bằng cố định phòng ban; salary giới hạn khoảng; thứ tự salary rồi employee_id có thể được đọc theo chỉ mục, tránh sort tùy kế hoạch. **employee_id** không nhất thiết tiếp tục thu hẹp khoảng salary, nhưng vẫn giúp sắp xếp ổn định.

**Tình huống B.** Có chỉ mục **(tenant_id, status, created_at DESC)**. Truy vấn lọc **tenant_id = ?** và lấy 20 đơn mới nhất **bất kể status**. Có thể giả định chỉ mục cung cấp ORDER BY created_at DESC không?

**Gợi ý đáp án:** Không. Các khóa được nhóm theo status trước, nên không tạo một dãy thời gian duy nhất của tenant. Cân nhắc **(tenant_id, created_at DESC, id DESC)** nếu mẫu truy vấn này quan trọng.

**Tình huống C.** Truy vấn **WHERE tenant_id = ? AND status IN ('NEW', 'PAID') ORDER BY created_at DESC LIMIT 30** được đề xuất chạy trên chỉ mục **(tenant_id, status, created_at DESC)**. Cần kiểm tra điều gì?

**Gợi ý đáp án:** Hai nhóm status có thể phải hợp nhất và sắp lại theo created_at; kiểm tra bước Sort/Merge, lượng dòng đọc, tỷ lệ lọc và chi phí so với phương án khác.

**Tình huống D.** Người dùng yêu cầu thêm chỉ mục **(tenant_id, status, created_at)** và **(status, tenant_id, created_at)** vì “hai cột đầu đều rất chọn lọc”. Bạn nên phản hồi thế nào?

**Gợi ý đáp án:** Phân tích truy vấn sử dụng tiền tố nào, tần suất, ORDER BY và kế hoạch thực thi. Nếu hầu hết truy vấn luôn ràng buộc cả hai cột, hai chỉ mục có thể trùng công dụng đáng kể; thêm cả hai mà chưa đo sẽ tăng chi phí ghi.

## 12. Ghi nhớ khi thiết kế persistence

Với B-tree ghép, hãy bắt đầu bằng **hình dạng câu truy vấn thực tế**: cột nào được cố định bằng, cột nào tạo khoảng, kết quả phải sắp theo gì, có LIMIT hay phân trang không, và dữ liệu phân bố ra sao. Từ đó đề xuất thứ tự khóa, viết SQL để tận dụng chỉ mục, rồi **xác minh bằng kế hoạch và số đo**. Thứ tự cột quyết định những vùng khóa có thể đi tới hiệu quả; sự phù hợp giữa **WHERE, ORDER BY và cách truy cập của ứng dụng Java** mới quyết định lợi ích trong hệ thống chạy thật.
