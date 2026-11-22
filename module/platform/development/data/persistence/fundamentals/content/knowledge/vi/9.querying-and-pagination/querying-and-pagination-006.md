# Giới hạn kết quả để kiểm soát bộ nhớ và thời gian xử lý

Trong chương **Truy vấn và phân trang** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một câu lệnh đọc dữ liệu không chỉ cần trả về **đúng hàng** mà còn phải trả về **đúng lượng dữ liệu, trong thời gian và ngân sách tài nguyên đã xác định**. Một endpoint Java truy vấn vài chục bản ghi thường ổn, nhưng nếu vô tình đọc vài triệu hàng, nó có thể làm đầy heap, tăng thời gian GC, giữ kết nối database quá lâu, chiếm băng thông và khiến các giao dịch khác chậm đi.

**Giới hạn kết quả** không đơn thuần là thêm `LIMIT 100`. Nó gồm phạm vi dữ liệu được phép truy vấn, số hàng mỗi lần trả, kích thước từng hàng, cơ chế phân trang, chỉ mục, timeout, bộ đệm JDBC, mức đồng thời và cách xử lý các thao tác cần xuất toàn bộ dữ liệu. Thiết kế phải phù hợp với ranh giới persistence Java, truy vấn/chỉ mục, giao dịch, cô lập, tính nhất quán, bảo mật, sao lưu và khả năng vận hành của mô-đun.

**Mục tiêu học tập**

- Phân biệt số hàng **được trả**, số hàng **database phải xử lý** và số byte **ứng dụng phải giữ trong bộ nhớ**.
- Giới hạn phạm vi và kích thước trang với `LIMIT`, `ORDER BY`, keyset pagination và tham số được xác thực.
- Nhận diện đánh đổi giữa `OFFSET` và cursor/keyset khi dữ liệu lớn hoặc có ghi đồng thời.
- Dùng JDBC để tải dữ liệu theo trang hoặc theo luồng mà không vô tình materialize toàn bộ kết quả.
- Thiết kế timeout, giới hạn tổng byte, quyền truy cập và cơ chế xuất dữ liệu lớn an toàn.
- Kiểm thử độ trễ p95/p99, memory/GC, truy vấn quét sâu, tính nhất quán giữa các trang và lỗi kết nối.

## 1. Vấn đề: trả một danh sách không có điểm kết thúc

Giả sử một nền tảng bán hàng cho phép khách xem các đơn của họ:

~~~java
// Ví dụ phản diện: không giới hạn số hàng, có thể tiêu thụ nhiều heap.
List<Order> orders = orderRepository.findAllByCustomerId(customerId);
return orders;
~~~

Nếu một khách chỉ có 10 đơn, vấn đề khó nhận ra. Nhưng nếu một tài khoản doanh nghiệp có 2 triệu đơn và mỗi đối tượng Java (gồm các trường, cấu trúc và overhead) chiếm trung bình 1 KiB, riêng phần dữ liệu đã vào khoảng **2 GiB** trước khi cộng serialization, response buffer, ORM tracking và các bản sao tạm.

Những ước lượng này chỉ để hình dung: kích thước object thực tế phụ thuộc JVM, mô hình object, các tham chiếu, thư viện ORM và dữ liệu. Quan trọng là **bộ nhớ ứng dụng tăng theo tổng số hàng được materialize**, còn thời gian query, JSON serialization và truyền mạng tăng theo dữ liệu thực phải xử lý.

Một luồng truy vấn không giới hạn có thể gây chuỗi hậu quả:

1. Database phải đọc/sắp xếp hoặc JOIN một tập rất lớn.
2. Kết nối trong pool bị giữ trong thời gian dài; request khác phải chờ.
3. Driver/ORM có thể đệm hàng hoặc xây toàn bộ object graph.
4. Java heap, GC và response buffer chịu áp lực; server chậm, timeout hoặc `OutOfMemoryError`.
5. Truyền hàng trăm MB đến client ngay cả khi giao diện chỉ hiển thị 20 mục.
6. Giao dịch đọc dài có thể giữ snapshot và cản trở dọn phiên bản cũ trong các DBMS dùng MVCC.

**Không nên chờ tới khi có OOM mới đặt giới hạn.** Số hàng được phép trả và cách đọc kết quả là một phần hợp đồng API.

## 2. Ba lớp giới hạn phải phân biệt

| Lớp | Câu hỏi cần kiểm soát | Công cụ thường dùng |
| --- | --- | --- |
| **Phạm vi nghiệp vụ** | Ai được xem dữ liệu nào, trong khoảng thời gian và trạng thái nào? | `tenant_id`, `customer_id`, quyền, khoảng ngày, bộ lọc có giới hạn |
| **Khối lượng truy vấn** | Database tìm, lọc, JOIN và sắp xếp bao nhiêu hàng/byte? | Chỉ mục, phân vùng, điều kiện chọn lọc, query plan, `LIMIT` |
| **Khối lượng đưa lên ứng dụng** | Bao nhiêu hàng/byte được chuyển, đệm và serialize? | Projection, page size, fetch size, streaming, timeout, byte cap |

Ví dụ, một `SELECT *` với `LIMIT 100` có thể chỉ trả 100 hàng nhưng mỗi hàng chứa một BLOB 10 MB: response vẫn có thể gần 1 GB. Ngược lại, một query `GROUP BY` trên 200 triệu hàng có thể chỉ trả 20 nhóm nhưng vẫn phải quét nhiều dữ liệu trước khi trả kết quả.

**Quy tắc:** giới hạn số hàng, giới hạn kích thước hàng và giới hạn *công việc truy vấn* là ba bài toán khác nhau. Một `LIMIT` chỉ giải quyết trực tiếp phần đầu, và đôi khi giúp database ngừng đọc sớm nếu có kế hoạch truy vấn phù hợp.

## 3. Mô hình dữ liệu minh họa và truy vấn có thứ tự ổn định

Các ví dụ SQL dùng PostgreSQL, dựa trên bảng đơn hàng:

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('CREATED', 'PAID', 'SHIPPED', 'CANCELLED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_minor BIGINT NOT NULL CHECK (total_minor >= 0),
    currency CHAR(3) NOT NULL
);

-- Hỗ trợ liệt kê đơn của một tenant theo thời gian và khóa phụ.
CREATE INDEX idx_order_tenant_created_id
ON sales_order (tenant_id, created_at DESC, order_id DESC);
~~~

Trong ví dụ, `created_at` được coi là **bất biến sau khi tạo** và `order_id` là khóa duy nhất. Các lệnh lọc theo tenant phải nhận tenant từ danh tính đã xác thực, **không** tin một tenant ID tùy ý do client gửi.

Truy vấn danh sách đơn mới nhất:

~~~sql
SELECT order_id, created_at, status, total_minor, currency
FROM sales_order
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size;
~~~

Ký hiệu `:parameter` chỉ để giải thích; với JDBC cơ bản hãy dùng dấu `?` và bind tham số. Index ở trên có thể giúp DB tìm các hàng theo tenant đúng thứ tự mà không cần sắp xếp toàn bộ tập kết quả, **tùy kế hoạch thực thi và thống kê dữ liệu**.

### 3.1. Vì sao ORDER BY cần khóa phụ duy nhất?

Giả sử ba đơn có cùng `created_at` tới độ phân giải microsecond. Nếu chỉ `ORDER BY created_at DESC`, thứ tự giữa ba hàng này **không được xác định**. Khi phân trang, chúng có thể đổi vị trí giữa các lần query và gây trùng/bỏ sót.

Thêm `order_id DESC` giúp tạo **thứ tự toàn phần** trong tập được lọc:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Không nên dựa vào thứ tự “tự nhiên” của index, insertion order hoặc khóa chính nếu truy vấn không có `ORDER BY`. Database được quyền trả các hàng theo thứ tự khác khi đổi execution plan hoặc tình trạng dữ liệu.

### 3.2. Bắt buộc có phạm vi và page size hợp lệ

Một chính sách API minh họa:

| Thuộc tính | Giá trị minh họa | Vì sao |
| --- | --- | --- |
| Trang mặc định | 20 hàng | Phù hợp giao diện danh sách |
| Trang tối đa | 100 hàng | Chặn request `size=10000000` |
| Trang tối thiểu | 1 hàng | Tránh giá trị âm, 0 và phép tính không mong muốn |
| Khoảng lịch sử báo cáo | Ví dụ tối đa 90 ngày cho API đồng bộ | Giảm truy vấn quá rộng; nhu cầu dài hơn dùng export |
| Số byte mỗi response | Giới hạn theo API/gateway | Tránh hàng quá lớn dù số hàng nhỏ |
| Timeout | Mức phù hợp SLO đã đo | Ngăn một request chiếm tài nguyên vô hạn |

Đây là **thông số giả định**, không phải chuẩn bắt buộc cho mọi hệ thống. Chọn ngưỡng dựa trên độ rộng bản ghi, SLO, hành vi khách hàng và kết quả đo tải.

Kiểm tra giá trị trước khi chuyển vào JDBC, không ghép `LIMIT` từ chuỗi request chưa xác thực. Ví dụ Java:

~~~java
static int validatePageSize(Integer requested) {
    int size = requested == null ? 20 : requested;
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("page size must be from 1 to 100");
    }
    return size;
}
~~~

Có thể chọn chính sách *clamp* (giảm về max) hoặc *reject* (trả lỗi); hãy công bố và thực thi nhất quán. Giới hạn tổng số request, concurrency và rate limit vẫn cần thiết: 1.000 request hợp lệ mỗi request 100 hàng cũng có thể tạo tải lớn.

## 4. Phân trang OFFSET/LIMIT: đơn giản nhưng có giới hạn

Trang 1, 2, 3 tương ứng với offset 0, 20, 40:

~~~sql
SELECT order_id, created_at, status, total_minor, currency
FROM sales_order
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size OFFSET :offset;
~~~

Với page size `S` và trang đánh số bắt đầu từ 1, offset là `(pageNumber - 1) * S`. Khi tính bằng Java, cần dùng số nguyên đủ rộng, kiểm tra overflow, và đặt giới hạn page number/offset cho endpoint đồng bộ.

**Ưu điểm:**

- Dễ hiểu: client yêu cầu trang số 5.
- Hữu ích khi tập dữ liệu nhỏ, ít thay đổi hoặc giao diện cần nhảy trực tiếp tới một trang.
- Phù hợp nhiều bảng quản trị nội bộ có giới hạn lượng dữ liệu.

**Hạn chế:**

- Với offset sâu, database thường vẫn cần duyệt/loại những hàng phía trước. `LIMIT 20 OFFSET 1000000` không đồng nghĩa chỉ xử lý 20 hàng.
- Mỗi trang là một truy vấn riêng, nên khi có thêm/xóa dữ liệu giữa các lần đọc, vị trí các hàng thay đổi.
- `COUNT(*)` để tính tổng số trang có thể trở thành truy vấn đắt, nhất là cùng bộ lọc lớn.

### 4.1. OFFSET gây trùng hoặc bỏ sót khi dữ liệu thay đổi

Giả sử danh sách theo thứ tự mới nhất là:

~~~text
Trước khi có bản ghi mới: [A, B, C, D, E, F]
Trang 1, size=3:         [A, B, C]

Có đơn X mới đứng đầu:  [X, A, B, C, D, E, F]
Trang 2 với OFFSET 3:   [C, D, E]
~~~

`C` đã xuất hiện ở cả hai trang. Nếu một hàng phía trước bị xóa, một hàng ở trang sau có thể bị bỏ qua. `ORDER BY` ổn định **không khắc phục việc vị trí thay đổi giữa hai truy vấn**.

Khi cần tải tiếp dòng dữ liệu cập nhật liên tục (news feed, lịch sử thanh toán, đơn hàng mới), **keyset/cursor pagination** thường thích hợp hơn.

## 5. Keyset pagination: tiếp tục sau hàng cuối cùng

Thay vì bảo database “bỏ qua 10.000 hàng đầu”, client gửi khóa sắp xếp của **hàng cuối đã hiển thị**:

~~~sql
-- Trang đầu tiên
SELECT order_id, created_at, status, total_minor, currency
FROM sales_order
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT :size_plus_one;
~~~

Trang kế tiếp dùng **tuple comparison** của PostgreSQL:

~~~sql
SELECT order_id, created_at, status, total_minor, currency
FROM sales_order
WHERE tenant_id = :tenant_id
  AND (created_at, order_id) < (:last_created_at, :last_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT :size_plus_one;
~~~

Vì cả hai khóa đều sắp xếp **giảm dần** và không null, phép so sánh tuple `<` đúng theo thứ tự seek này. Nếu sắp xếp hỗn hợp chiều, có giá trị `NULL` hoặc collation đặc biệt, predicate phải viết lại cho đúng. Đừng sao chép tuple predicate cho mọi kiểu sort.

**Ví dụ:** danh sách đã sắp theo `(created_at DESC, order_id DESC)` gồm các khóa `(12:00, 109)`, `(12:00, 108)`, `(11:59, 110)`, `(11:58, 120)`. Nếu trang đầu trả hai hàng đầu, cursor là `(12:00, 108)`; truy vấn sau tiếp tục ở `(11:59, 110)`, không lặp hàng thứ hai.

### 5.1. Tại sao lấy size + 1?

Nếu trang có kích thước `S = 20`, truy vấn lấy tối đa **21** hàng:

- Có 21 hàng → trả 20 hàng đầu, `hasNext = true`; tạo cursor từ **hàng cuối được trả**, không phải hàng thứ 21.
- Có 20 hàng hoặc ít hơn → trả tất cả và `hasNext = false` cho trạng thái truy vấn hiện tại.

Phương án này tránh một câu `COUNT(*)` chỉ để biết có trang tiếp hay không. Tuy nhiên, `hasNext` không bảo đảm trang sau vẫn có dữ liệu nếu các hàng bị xóa hoặc quyền/bộ lọc thay đổi trước lúc client truy vấn tiếp.

### 5.2. Điều kiện để keyset hoạt động đúng

1. Dùng **thứ tự ổn định, có khóa phụ duy nhất**: `created_at DESC, order_id DESC`.
2. Các trường dùng trong cursor phải thuộc các hàng có thể đọc; cursor không được nhảy qua tenant hay bộ lọc khác.
3. Trường sắp xếp nên **bất biến** khi phân trang. Nếu `status`, điểm xếp hạng hay `updated_at` có thể đổi, hàng có thể di chuyển qua ranh giới và gây trùng/bỏ sót.
4. Mọi trang phải dùng cùng filter, sort và chính sách phân quyền.
5. Chỉ mục phải phù hợp với tiền tố filter và sort; đo plan thực thay vì kết luận chỉ từ câu SQL.

**Giới hạn:** keyset giảm chi phí offset sâu và các lỗi dịch chuyển vị trí do insert ở đầu danh sách, **không tự cung cấp snapshot nhất quán qua nhiều request**. Với cập nhật/xóa, phân trang trên dữ liệu đang thay đổi vẫn có thể không biểu diễn một tập dữ liệu cố định tại một thời điểm.

## 6. Cursor trong API: ký hiệu tiếp tục, không phải quyền truy cập

Một API có thể trả:

~~~json
{
  "items": [
    {"orderId": 103, "status": "PAID"},
    {"orderId": 102, "status": "SHIPPED"}
  ],
  "hasNext": true,
  "nextCursor": "opaque-token-from-server"
}
~~~

**Cursor public nên là token opaque**, không phải một câu SQL hay đoạn filter tùy ý. Nội dung logic của token có thể gồm:

~~~json
{
  "v": 1,
  "sort": "created_at_desc_order_id_desc",
  "lastCreatedAt": "2026-11-20T09:30:00Z",
  "lastOrderId": 102,
  "filterFingerprint": "hash-of-canonical-filters",
  "scope": "tenant-scoped",
  "issuedAt": "2026-11-20T09:30:10Z"
}
~~~

Đây là **mô tả logic**, không phải token thực cần gửi nguyên JSON cho client. Server nên ký/MAC token hoặc dùng một opaque ID tra metadata phía server; mã hóa nếu cần giấu nội dung. Khi nhận cursor, xác minh chữ ký, hạn sử dụng, phiên bản token, bộ lọc, tenant và quyền hiện tại. Không tin `lastOrderId` do client tự sửa thành giá trị tùy ý nếu điều đó có thể rò rỉ dữ liệu hoặc làm tăng chi phí truy vấn.

Một cursor **không cấp quyền**: API vẫn kiểm tra tenant/actor ở mọi request. Cần xử lý token hỏng, hết hạn hoặc không tương thích sau khi thay đổi schema bằng phản hồi rõ và hướng dẫn client tải lại từ đầu.

## 7. Java/JDBC: trả một trang hữu hạn

Ví dụ Java 17+ sau dùng JDBC với schema `sales_order` ở trên. Chương trình giả định tầng API đã xác thực tenant, xác minh token cursor và kiểm tra page size; repository nhận một `OrderCursor` nội bộ đã tin cậy.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;

record OrderRow(long orderId, Instant createdAt,
                String status, long totalMinor, String currency) {}

record OrderCursor(Instant createdAt, long orderId) {}

record OrderPage(List<OrderRow> items, boolean hasNext,
                 OrderCursor nextCursor) {}

public final class OrderPageRepository {
    private final DataSource dataSource;

    public OrderPageRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public OrderPage fetch(UUID tenantId, int pageSize, OrderCursor cursor)
            throws SQLException {
        if (tenantId == null || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("invalid tenant or page size");
        }

        boolean nextPage = cursor != null;
        String seek = nextPage
                ? "AND (created_at, order_id) < (?, ?) "
                : "";
        // Chỉ nối mảnh SQL cố định do server chọn; không nối input client.
        String sql = """
                SELECT order_id, created_at, status, total_minor, currency
                FROM sales_order
                WHERE tenant_id = ?
                """ + seek + """
                ORDER BY created_at DESC, order_id DESC
                LIMIT ?
                """;

        List<OrderRow> rows = new ArrayList<>(pageSize + 1);
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setQueryTimeout(10);  // Giới hạn phụ thuộc driver
            int pos = 1;
            statement.setObject(pos++, tenantId);
            if (nextPage) {
                statement.setObject(pos++,
                        OffsetDateTime.ofInstant(
                                cursor.createdAt(), ZoneOffset.UTC));
                statement.setLong(pos++, cursor.orderId());
            }
            statement.setInt(pos, pageSize + 1);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    rows.add(new OrderRow(
                            result.getLong("order_id"),
                            result.getTimestamp("created_at").toInstant(),
                            result.getString("status"),
                            result.getLong("total_minor"),
                            result.getString("currency")
                    ));
                }
            }
        }

        boolean hasNext = rows.size() > pageSize;
        if (hasNext) {
            rows.remove(rows.size() - 1); // Hàng thăm dò, không trả về.
        }
        OrderCursor nextCursor = null;
        if (hasNext && !rows.isEmpty()) {
            OrderRow last = rows.get(rows.size() - 1);
            nextCursor = new OrderCursor(last.createdAt(), last.orderId());
        }
        return new OrderPage(List.copyOf(rows), hasNext, nextCursor);
    }
}
~~~

**Điều ví dụ bảo đảm:** câu SQL có `LIMIT pageSize + 1`; Java không tải toàn bộ tập đơn vào một `List`; thứ tự có khóa phụ; tenant được bind; điều kiện cursor do server tạo; connection/statement/result set được đóng bằng try-with-resources. Với 100 hàng mỗi trang, danh sách tạm giữ tối đa 101 đối tượng DTO.

**Điều chưa được minh họa:** xác thực và giải mã token cursor từ HTTP, phân quyền cấp đơn, response HTTP/JSON, rate limit, giới hạn byte mỗi hàng, metrics và phân loại lỗi. Kết quả không phải snapshot nhiều trang. Cách bind `TIMESTAMPTZ` cần kiểm tra với driver JDBC đang dùng và cấu hình múi giờ. `setQueryTimeout(10)` là giới hạn cấp statement phụ thuộc khả năng driver, không phải bảo đảm tuyệt đối mọi tác vụ kết thúc đúng ở giây thứ 10.

### 7.1. Projection: đừng SELECT *

Ví dụ trên chỉ chọn năm cột cần hiển thị. Nếu bảng có JSON chi tiết đơn hoặc tài liệu nhúng lớn, `SELECT *` có thể khiến mỗi page ngốn nhiều bộ nhớ và băng thông dù `LIMIT 20`.

Dùng DTO nhỏ cho danh sách; chỉ tải chi tiết nặng khi người dùng mở một đơn cụ thể. Với quan hệ một-nhiều, hạn chế fetch join vô điều kiện vì có thể nhân số hàng trả; **phân trang trên parent ID trước, rồi tải child cho đúng tập parent** hoặc dùng chiến lược truy vấn khác đã kiểm chứng.

## 8. Fetch size và streaming: khác với page size

Ba con số không đồng nghĩa:

| Thuộc tính | Mục đích | Có ngăn query trả quá nhiều hàng không? |
| --- | --- | --- |
| `LIMIT` / keyset page size | Giới hạn số hàng trong **một page kết quả** | Có, ở mức hàng trả từ query (không nhất thiết giới hạn công việc nội bộ) |
| `setFetchSize(n)` | Gợi ý driver lấy số hàng từng đợt | **Không**; toàn bộ truy vấn vẫn có thể có hàng triệu hàng |
| `setMaxRows(n)` | Yêu cầu JDBC giới hạn số hàng trong `ResultSet` theo khả năng driver | Không thay thế `LIMIT` trong SQL, plan hay phân quyền |

Với endpoint danh sách, ưu tiên **page hữu hạn**. Khi thật sự cần xử lý tất cả hàng (export, migration được cấp quyền, tính toán batch), có thể đọc theo luồng hoặc nhiều page có checkpoint.

### 8.1. Ví dụ đọc theo luồng PostgreSQL JDBC

Trong PostgreSQL JDBC, để driver sử dụng cursor/fetch theo đợt cho truy vấn thích hợp, thông thường cần **tắt auto-commit** và đặt fetch size dương. Ví dụ chỉ minh họa một tập kết quả được xử lý tuần tự, không tự ý dồn vào `List`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class OrderExportReader {
    private final DataSource dataSource;

    public OrderExportReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void forEachOrder(UUID tenantId, java.util.function.Consumer<String> sink)
            throws SQLException {
        String sql = """
                SELECT order_id, status
                FROM sales_order
                WHERE tenant_id = ?
                ORDER BY created_at DESC, order_id DESC
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setReadOnly(true);
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        sql, ResultSet.TYPE_FORWARD_ONLY,
                        ResultSet.CONCUR_READ_ONLY)) {
                    statement.setObject(1, tenantId);
                    statement.setFetchSize(200);
                    statement.setQueryTimeout(60);

                    try (ResultSet result = statement.executeQuery()) {
                        while (result.next()) {
                            String line = result.getLong("order_id")
                                    + "," + result.getString("status");
                            sink.accept(line); // Xử lý từng dòng; không gom tất cả.
                        }
                    }
                }
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
    }
}
~~~

Ví dụ không xử lý escape CSV đầy đủ, lỗi I/O của đích xuất, audit hoặc giới hạn số hàng; nó chỉ cho thấy **vòng đọc không tích lũy kết quả**. Nếu ghi CSV thực, hãy dùng encoder CSV chuẩn, xử lý dấu phẩy/dấu nháy/newline và chú ý formula injection khi file sẽ được mở trong bảng tính.

**Rủi ro vận hành:** một cursor đọc hàng triệu hàng vẫn giữ connection/transaction và có thể giữ snapshot lâu, gây áp lực MVCC/VACUUM trong PostgreSQL. `fetchSize=200` giảm kích thước batch truyền/đệm nhưng **không biến một export dài nhiều giờ thành truy vấn không tốn tài nguyên**. Với export lớn, nên cân nhắc background job, chia page/keyset, checkpoint, giới hạn thời gian, lưu file kết quả ở object storage và trả trạng thái job cho client.

### 8.2. ORM có thể materialize vượt quá dự kiến

Các cơ chế ORM như JPA/Hibernate có thể giữ entity trong persistence context, tạo bản sao hoặc tải quan hệ lười khi serialize JSON. `Page<Entity>`, `List<Entity>` hoặc streaming repository không tự chứng minh bộ nhớ được giới hạn.

Một số cách giảm rủi ro:

- Dùng projection/DTO chỉ chứa trường cần thiết.
- Đặt page size ở truy vấn, không `findAll()` rồi mới `subList()` trong Java.
- Với batch dài, flush/clear persistence context theo lô khi phù hợp; xem hành vi transaction.
- Tránh N+1: 20 đơn nhưng mỗi đơn tải 10 lần query child vẫn có thể tạo hơn 200 round trip.
- Kiểm tra SQL thực ORM phát ra: fetch join collection với pagination có thể bị xử lý trong bộ nhớ hoặc cần kế hoạch truy vấn khác tùy phiên bản/cấu hình.

## 9. LIMIT không luôn giảm công việc trong database

Câu truy vấn có `LIMIT 20` vẫn có thể rất chậm nếu database phải xử lý tập lớn trước khi xác định 20 hàng đầu:

~~~sql
SELECT customer_id, SUM(total_minor) AS gross_minor
FROM sales_order
WHERE tenant_id = :tenant_id
GROUP BY customer_id
ORDER BY gross_minor DESC
LIMIT 20;
~~~

Để tìm **20 khách có tổng tiền lớn nhất**, database thường cần đọc và tổng hợp dữ liệu của nhiều khách trước khi chọn top 20. Index `(tenant_id, created_at DESC, order_id DESC)` dành cho danh sách theo thời gian không tự tối ưu truy vấn này.

Một ví dụ khác:

~~~sql
SELECT order_id, created_at
FROM sales_order
WHERE tenant_id = :tenant_id
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Nếu rất ít đơn có `status = 'PAID'` và số lượng hàng lớn, index chỉ theo tenant/thời gian có thể phải quét nhiều hàng trước khi tìm đủ 50. Có thể **cân nhắc** index:

~~~sql
CREATE INDEX idx_order_tenant_status_created_id
ON sales_order (tenant_id, status, created_at DESC, order_id DESC);
~~~

Đây là quyết định dựa trên workload, không phải yêu cầu phải tạo mọi index minh họa trong cùng môi trường. Index tăng dung lượng và chi phí ghi; cần xem `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường kiểm thử có dữ liệu đại diện, quan sát scan/rows removed, sort, buffer và thời gian. `EXPLAIN ANALYZE` **thực thi truy vấn**, nên phải thận trọng với câu lệnh thay đổi dữ liệu và tải hệ thống.

### 9.1. LIMIT sau JOIN có thể cắt sai đối tượng

Ví dụ một đơn hàng có 10 dòng. Nếu JOIN `sales_order` với `order_line` rồi `LIMIT 20`, 20 **hàng kết quả JOIN** không nhất thiết tương đương với **20 đơn hàng**. Thậm chí các dòng của đơn cuối có thể bị cắt.

Cách an toàn hơn khi cần trả 20 parent kèm child:

1. Truy vấn trước 20 `order_id` theo filter và thứ tự ổn định.
2. Truy vấn child bằng `WHERE order_id IN (...)` hoặc JOIN với tập parent đã giới hạn.
3. Ghép dữ liệu theo parent ID, bảo toàn thứ tự và giới hạn số lượng child khi cần.
4. Kiểm tra tổng số hàng và byte ở cả parent lẫn child, tránh một parent có vô số child.

Nếu cần một snapshot nhất quán giữa hai câu lệnh, phải chọn transaction/isolation hoặc phương án query phù hợp; hai truy vấn độc lập ở `READ COMMITTED` có thể nhìn các thời điểm khác nhau.

## 10. COUNT(*), totalPages và bài toán “trang cuối”

Nhiều endpoint trả:

~~~json
{
  "items": [],
  "page": 42,
  "size": 20,
  "totalElements": 12345678,
  "totalPages": 617284
}
~~~

Để trả `totalElements` chính xác, server thường phải chạy `COUNT(*)` trên toàn bộ tập đủ điều kiện, có thể đắt hơn truy vấn lấy một page. Khi dữ liệu đang thay đổi, con số count cũng có thể lệch với danh sách trả trong cùng response nếu hai query không cùng snapshot.

**Các lựa chọn:**

- **Không trả total count:** với infinite scroll, chỉ có `items`, `hasNext` và `nextCursor`.
- **Tính count khi được yêu cầu:** ví dụ nhấn “Xem tổng số kết quả” hoặc báo cáo riêng, có timeout và cache phù hợp.
- **Dùng số ước lượng:** ghi rõ đây là estimate, không hiển thị như số chính xác.
- **Dùng bảng tổng hợp/counter:** phải thiết kế cách cập nhật, sửa sai và đối soát.

Tránh chạy một `COUNT(*)` mới ở **mọi page** chỉ vì thư viện trả kiểu `Page` có sẵn. Đối với các use case chỉ cần biết có phần tiếp, mô hình `Slice` hoặc `size+1` thường tiết kiệm hơn.

## 11. Tính nhất quán qua nhiều trang và dữ liệu thay đổi

Mỗi request phân trang thường là một transaction riêng. Khi dữ liệu đang được tạo, sửa, xóa, **không có bảo đảm tất cả trang cùng mô tả một ảnh chụp duy nhất** nếu không có cơ chế bổ sung.

| Yêu cầu | Phương án thường phù hợp | Đánh đổi |
| --- | --- | --- |
| Danh sách UI chấp nhận cập nhật liên tục | Keyset + thứ tự bất biến | Có thể bỏ qua thay đổi nằm ngoài cursor; không phải snapshot cố định |
| Báo cáo cần đúng tập tại một thời điểm | Snapshot giao dịch/chiến lược `as_of`, hoặc xuất từ bản dữ liệu bất biến | Giữ snapshot lâu tốn tài nguyên; cần quản lý phiên và thời gian |
| Export hàng triệu bản ghi | Background job + chunk/keyset + checkpoint hoặc snapshot nhất quán | Pipeline phức tạp hơn, cần lưu trạng thái tiến độ |
| Báo cáo số liệu chính thức | Mốc dữ liệu chốt, định nghĩa business và đối soát | Chấp nhận độ trễ hoặc chi phí lưu tập dữ liệu chốt |

Có thể đưa một **mốc giới hạn** từ trang đầu vào các trang sau, ví dụ `created_at <= :as_of`, để tránh nhiều bản ghi mới nhất chen vào phía trước. Tuy vậy, điều kiện đó **không đủ** tạo snapshot cố định nếu có backdated insert, update hoặc delete. Muốn đảm bảo toàn bộ tập kết quả không thay đổi, phải dùng cơ chế snapshot/phiên bản dữ liệu phù hợp, và hiểu chi phí giữ nó.

Thời gian của client không phải mốc chốt đáng tin cậy. Nếu có SLA về dữ liệu mới, phải định nghĩa nguồn thời gian, timezone và mức lệch cho phép.

## 12. Timeout, hủy truy vấn và bảo vệ tài nguyên

Giới hạn kết quả cần kết hợp với giới hạn **thời gian** và **mức đồng thời**:

- **Timeout ở API:** chặn request chờ quá SLO; xử lý hủy an toàn khi client ngắt kết nối.
- **Statement timeout ở JDBC/DBMS:** giới hạn truy vấn quá dài; hành vi hủy phụ thuộc driver/database, không phải timer chính xác tuyệt đối.
- **Connection-pool timeout và pool size:** tránh hàng nghìn request cùng chiếm connection; theo dõi pool wait.
- **Rate limit và concurrency cap:** một người dùng không được chạy hàng trăm truy vấn báo cáo nặng cùng lúc.
- **Giới hạn độ rộng filter:** từ chối khoảng ngày quá dài hoặc sort không được hỗ trợ cho API đồng bộ.
- **Giới hạn hàng và byte:** hạn chế trường lớn, số entity liên quan, lượng JSON sinh ra và kích thước response.
- **Export bất đồng bộ:** chạy job trong pool riêng, quản lý quota, cung cấp trạng thái và file kết quả có thời hạn.

Không nên retry vô hạn khi truy vấn timeout. Nếu timeout do query plan xấu hoặc tài nguyên bão hòa, retry ngay lập tức với nhiều client có thể tạo *retry storm*. Hãy dùng backoff có giới hạn, phân loại lỗi tạm thời, tối ưu query, index và admission control.

### 12.1. API truy vấn cần chống lạm dụng

Người dùng có thể gửi `size=999999999`, `offset=-1`, sort theo trường rất đắt hoặc cursor đã bị sửa. API nên:

1. Đặt **allowlist** các trường và chiều sắp xếp; tên cột/`ORDER BY` không thể được bind như dữ liệu nên không nối raw client input vào SQL.
2. Bind mọi giá trị lọc bằng prepared statement để tránh SQL injection.
3. Giới hạn `pageSize`, độ sâu offset, thời gian truy vấn và tổng byte.
4. Kiểm tra tenant/owner và cả quyền đọc từng trường nhạy cảm.
5. Xác thực token cursor (scope, filter fingerprint, TTL, integrity).
6. Ghi metrics và audit phù hợp, không đưa dữ liệu cá nhân hoặc cursor nhạy cảm vào log.

Giới hạn kết quả vừa là yêu cầu hiệu năng vừa là **biện pháp chống resource exhaustion**. Nhưng nó không thay thế authorization: trả 20 hàng của tenant khác vẫn là vi phạm nghiêm trọng.

## 13. Xử lý lỗi kết nối, retry và trạng thái phân trang

Một trang truy vấn thuần đọc có thể retry khi mất kết nối tạm thời, nhưng cần phân biệt:

| Tình huống | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Timeout trước khi có bất kỳ kết quả nào | Không biết database đã thực thi bao lâu | Giới hạn retry, backoff, xem lại plan và tải |
| Response bị ngắt sau khi gửi một phần JSON | Client có dữ liệu không hoàn chỉnh | Không coi page đã hợp lệ; tải lại bằng cursor cũ hoặc yêu cầu mới |
| Dữ liệu thay đổi giữa retry | Trang có thể khác lần đầu | Chấp nhận theo hợp đồng UI hoặc dùng snapshot/`as_of` |
| Cursor hết hạn hoặc sai filter | Tiếp tục sai phạm vi | Trả lỗi rõ, yêu cầu khởi động phân trang mới |
| Export đã xử lý một số chunk trước khi lỗi | Nguy cơ ghi lặp hoặc thiếu chunk | Lưu checkpoint theo khóa cuối và version/snapshot; ghi kết quả idempotent |

Với một **HTTP response đã được gửi dở**, server không thể “đổi thành mã lỗi mới” sau khi client đã nhận header. Vì thế endpoint đồng bộ nên giữ page nhỏ để có thể xây response hữu hạn trước khi gửi; còn export lớn dùng một giao thức streaming có xử lý lỗi riêng hoặc job bất đồng bộ với file đã hoàn tất rồi mới công bố.

Nếu cần chỉ đọc dữ liệu **đã commit** trong một transaction, dùng mức isolation và read source phù hợp. Đọc từ replica có lag có thể khiến dữ liệu mới chưa xuất hiện, dù page size đã đúng. Khi vừa ghi xong rồi mở danh sách, lựa chọn read-your-writes cần được giải quyết riêng.

## 14. Tối ưu truy vấn và giám sát thực tế

Các số đo quan trọng:

| Số đo | Tín hiệu |
| --- | --- |
| `rows_returned`, `bytes_returned` | Dung lượng thật trả về cho client |
| `rows_scanned` / `rows_removed_by_filter` | Query đang đọc nhiều hơn trả về bao nhiêu |
| `sort_spill`, temp bytes, I/O wait | Sort/JOIN vượt bộ nhớ và phải dùng đĩa |
| p50/p95/p99 query và API | Độ trễ thường gặp và phần đuôi khi tải cao |
| JDBC pool wait, active connection | Request đang chờ kết nối hoặc chiếm connection lâu |
| JVM heap, GC pause, allocation rate | Có materialize quá nhiều đối tượng/JSON không |
| Page size/offset/cursor depth | Truy vấn nào gây quét sâu |
| Timeout, cancellation, retry rate | Dấu hiệu quá tải hoặc kế hoạch truy vấn không phù hợp |
| Export duration, backlog, bytes per job | Job lớn ảnh hưởng nguồn giao dịch ra sao |

Thử nghiệm cần có dữ liệu **cùng phân bố** với production: nhiều đơn cũ, một số tenant rất lớn, số lượng trạng thái không đều, nhiều bản ghi có timestamp trùng và truy vấn ở giờ cao điểm. Benchmark chỉ trên 10.000 hàng với cache ấm không chứng minh được hiệu năng khi dữ liệu tăng lên hàng trăm triệu hàng.

### 14.1. Khi nào LIMIT làm API nhanh hơn rõ rệt?

Ví dụ `WHERE tenant_id = ? ORDER BY created_at DESC, order_id DESC LIMIT 20` thường có khả năng ngừng sớm khi có index phù hợp và dữ liệu chọn lọc. Ngược lại, `ORDER BY SUM(...) DESC LIMIT 20` phải tổng hợp trước, khó được cứu chỉ bằng `LIMIT`.

Do đó cần nhìn **kế hoạch thực thi**: index scan hay full scan, sort có thể tránh không, số hàng thực đọc, số hàng bị lọc, bộ nhớ tạm và tổng thời gian. Nếu kết quả rất rộng, có thể cần đổi yêu cầu sang báo cáo tổng hợp hoặc workflow export, không chỉ tăng timeout.

## 15. Bài tập tình huống: API lịch sử đơn hàng bị quá tải

Một dịch vụ Java chạy với PostgreSQL và có các triệu chứng sau (dữ liệu giả định):

- Bảng `sales_order` chứa **85 triệu** hàng; một tenant lớn có **4 triệu** đơn.
- API `GET /orders` dùng `SELECT *`, trả tất cả đơn của tenant trong một `List<Entity>`.
- Sau khi khách mở trang, p99 tăng từ 300 ms lên 8 giây; Java heap tăng mạnh và connection pool cạn.
- Nhóm phát triển thêm `LIMIT 100` nhưng một số truy vấn sắp xếp theo tổng tiền vẫn rất chậm.
- Sản phẩm yêu cầu UI tải thêm 30 đơn/lần; bộ phận kế toán cần export toàn bộ dữ liệu trong một khoảng ngày có thể lên tới 24 tháng.
- Các đơn mới có thể tiếp tục được tạo trong lúc người dùng đang kéo danh sách.

**Hãy thiết kế lại:**

1. Xác định ít nhất năm nguyên nhân có thể gây độ trễ/heap tăng từ SQL, JDBC, ORM và response JSON.
2. Viết truy vấn cho trang đầu và trang kế tiếp theo `created_at DESC, order_id DESC` với `LIMIT 31`.
3. Đề xuất API có `items`, `hasNext` và `nextCursor`; nêu thông tin cursor phải được xác thực.
4. Giải thích vì sao `OFFSET 3000000` tốn tài nguyên và có thể trùng/bỏ sót dưới tải ghi.
5. Trình bày vì sao truy vấn `SUM(total_minor) GROUP BY customer_id ORDER BY SUM(...) DESC LIMIT 100` vẫn chậm.
6. Tách export 24 tháng thành job có quota, checkpoint, kiểm tra quyền và file kết quả; nêu đánh đổi về snapshot nhất quán.
7. Đề xuất ít nhất tám phép đo và sáu ca kiểm thử.

**Hướng giải tham khảo:** dùng DTO nhỏ, index phù hợp với tenant và thứ tự, keyset pagination với khóa phụ duy nhất và lấy `pageSize+1`. UI lấy từng trang hữu hạn và không gọi `COUNT(*)` mỗi lần. Truy vấn tổng hợp có thể chuyển sang bảng/warehouse phân tích nếu workload cần; không coi `LIMIT` là cách giảm mọi phép GROUP BY. Export nên có job chạy riêng, giới hạn tài nguyên, ghi file theo stream/chunk và công bố chỉ khi hoàn tất. Kiểm thử insert/delete giữa các trang, timestamp trùng, cursor bị sửa, tenant khác, timeout, big row, export retry và đối soát tập dữ liệu đã xuất.

## 16. Checklist áp dụng

- [ ] Mọi API danh sách có **page size mặc định và tối đa** được kiểm tra tại server.
- [ ] Có phạm vi tenant/quyền, điều kiện lọc và giới hạn thời gian/byte phù hợp.
- [ ] Query phân trang luôn có `ORDER BY` xác định với khóa phụ duy nhất.
- [ ] Chọn `OFFSET` hay keyset dựa trên độ sâu, mẫu sử dụng và thay đổi dữ liệu.
- [ ] Cursor được xác minh scope, sort/filter, hạn dùng và tính toàn vẹn.
- [ ] Thường dùng `LIMIT size+1` để biết còn trang kế mà không bắt buộc `COUNT(*)`.
- [ ] Chỉ chọn các cột cần thiết, tránh BLOB và JOIN làm nhân số hàng ngoài dự kiến.
- [ ] Đã xác minh index và execution plan, không mặc định có `LIMIT` thì công việc DB ít.
- [ ] Java/JDBC không gom toàn bộ tập kết quả; hiểu rõ sự khác biệt giữa `LIMIT`, fetch size và streaming.
- [ ] Export lớn có cơ chế riêng, quota, checkpoint, phục hồi và nguồn dữ liệu nhất quán theo yêu cầu.
- [ ] Có timeout, rate limit, giới hạn concurrency và phân loại retry đúng.
- [ ] Có kiểm thử snapshot/cập nhật đồng thời, khóa phụ trùng, lỗi kết nối và phân quyền đa tenant.
- [ ] Có metrics về rows/bytes/heap/GC/p95/p99/connection pool và kế hoạch tối ưu khi tăng trưởng.

**Ghi nhớ:** Giới hạn kết quả là **hợp đồng tài nguyên** của một thao tác đọc. `LIMIT` quyết định số hàng trả về trong một câu truy vấn, nhưng hiệu năng và bộ nhớ còn phụ thuộc vào phạm vi dữ liệu, chỉ mục, phép JOIN/sort/group, độ rộng từng hàng, cách JDBC/ORM đệm kết quả và số request đồng thời. Với ứng dụng Java bền vững, hãy dùng **thứ tự ổn định, phân trang đúng, projection gọn, giới hạn nhiều lớp và cơ chế export riêng**, rồi chứng minh bằng đo đạc và kiểm thử khi dữ liệu thay đổi.
