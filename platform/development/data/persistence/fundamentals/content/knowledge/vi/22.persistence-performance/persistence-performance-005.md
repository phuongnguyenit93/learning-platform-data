# Giảm dữ liệu truyền bằng lựa chọn trường và giới hạn kết quả

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao **chọn đúng cột** và **giới hạn đúng số hàng** làm giảm dữ liệu truyền giữa database, ứng dụng Java và client.
2. Phân biệt `SELECT *`, projection, DTO, truy vấn aggregate và việc tải toàn bộ entity qua ORM.
3. Thiết kế truy vấn có `WHERE`, `ORDER BY`, `LIMIT`, `OFFSET` hoặc **keyset pagination** đúng với yêu cầu nghiệp vụ.
4. Phân biệt `LIMIT` ở database với `Statement.setMaxRows()`, `setFetchSize()`, streaming và giới hạn sau khi dữ liệu đã vào heap Java.
5. Viết repository JDBC/JPA chỉ trả các trường cần thiết, kiểm soát page size, vòng đời `Connection` và các ranh giới bảo mật.
6. Đo số hàng, số byte, số truy vấn, độ trễ và kế hoạch thực thi để chứng minh tối ưu có ích mà không làm thay đổi kết quả nghiệp vụ.

Bài thuộc chương **Hiệu năng** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module học nguyên lý lưu trữ bền vững trong Java: mô hình dữ liệu, lược đồ, truy vấn và chỉ mục, giao dịch và cô lập, kiểm soát đồng thời, lỗi kết nối, bảo mật, backup và tối ưu hiệu năng. Trong bối cảnh đó, giảm payload không chỉ là giảm băng thông: nó còn giúp giảm thời gian giữ kết nối, chi phí dựng object, áp lực bộ nhớ và nguy cơ trả thừa dữ liệu nhạy cảm.

## 1. Một API chỉ cần 20 dòng dữ liệu, vì sao tải cả bảng?

Giả sử API hiển thị **20 đơn hàng mới nhất** của một tenant. Giao diện chỉ cần:

- Mã đơn hàng.
- Thời điểm tạo.
- Tổng tiền.
- Trạng thái.

Nhưng entity `Order` trong DB còn có ghi chú nội bộ, địa chỉ, thông tin giao hàng, payload JSON, audit metadata và nhiều quan hệ. Một cách viết dễ gặp:

~~~java
// Mã minh họa cách làm thiếu hiệu quả.
List<OrderEntity> all = orderRepository.findAll();

return all.stream()
        .filter(o -> o.getTenantId().equals(tenantId))
        .sorted(Comparator.comparing(OrderEntity::getCreatedAt)
                .reversed())
        .limit(20)
        .map(this::toSummary)
        .toList();
~~~

Với các repository mà `findAll()` thực sự tải toàn bộ hàng, những vấn đề có thể xuất hiện:

- Tất cả đơn hàng, kể cả đơn của tenant khác, được đọc từ DB trước khi Java lọc.
- Những trường không phục vụ màn hình vẫn có thể được đọc và chuyển qua mạng.
- Ứng dụng cấp phát entity và các object phụ, rồi bỏ phần lớn đi.
- Lọc và phân trang trong Java khiến số hàng DB trả về tăng cùng kích thước bảng.
- Chuyển entity thành DTO có thể kích hoạt thêm SQL qua quan hệ lazy (*N+1*).
- Nếu kết quả được serialize trực tiếp, API có nguy cơ gửi thừa thông tin hoặc lộ field nhạy cảm.

**Cốt lõi của tối ưu:** Đưa việc lọc, chọn cột, sắp xếp và giới hạn kết quả xuống nơi xử lý phù hợp — thông thường là database — rồi chỉ tạo DTO cho dữ liệu thật sự cần trả.

## 2. Đường đi của dữ liệu và các loại chi phí

Một lượt truy vấn đi qua nhiều tầng:

~~~text
PostgreSQL
  ├── Tìm và xử lý các hàng phù hợp
  ├── Đọc trang/index, lọc, join, sort
  └── Mã hóa các cột được SELECT
            |
            | TCP/TLS + giao thức database
            v
       JDBC driver
            |
            | chuyển dữ liệu thành Java values/objects
            v
       Repository / Service
            |
            | tạo DTO, map và serialize
            v
       HTTP response / JSON
            |
            v
       Web/mobile client
~~~

Giảm số cột và hàng truyền đi có thể giúp ở cả đường DB → Java và Java → HTTP, nhưng không nên coi chi phí của chúng là một. Một repository đọc ít dữ liệu rồi service gọi các truy vấn bổ sung có thể vẫn đắt; ngược lại, một SQL trả ít byte nhưng cần quét/sort hàng triệu bản ghi có thể chậm vì CPU hoặc I/O DB.

| Loại chi phí | Cơ chế tác động | Cách đo |
| --- | --- | --- |
| Byte DB → Java | Số hàng × dữ liệu thực tế của cột đã chọn, cộng overhead giao thức | Network bytes, row count, độ lớn giá trị; đo tại driver/host nếu có |
| Thời gian DB | Scan, join, sort, aggregate, index lookup, chờ lock hoặc I/O | `EXPLAIN (ANALYZE, BUFFERS)`, DB metrics |
| Heap và GC Java | Object entity, string, byte array, collection, graph quan hệ | Allocation profiling, heap/GC metrics |
| Độ trễ request | Chờ pool, truy vấn, chuyển dữ liệu, serialize, network | Tracing p50/p95/p99 end-to-end |
| Byte HTTP | JSON của các DTO, metadata phân trang, nén response | Response body size và wire bytes |
| Bảo mật | Trường không nên trả vẫn được đọc hoặc serialize | Review DTO/authorization, test payload |

### 2.1. Một phép tính minh họa

Giả sử bảng có 10.000 đơn. Nếu đường đọc vô tình lấy trung bình **2 KiB/hàng**, tổng payload dữ liệu hàng đã vào ứng dụng có thể ở mức khoảng **20 MiB** trước overhead giao thức và object Java.

Nếu màn hình chỉ cần 20 dòng, mỗi DTO có khoảng **100 byte dữ liệu trường**, payload dữ liệu trường của một trang chỉ khoảng **2.000 byte**. Đây là **ước lượng để thấy bậc độ lớn**, không phải benchmark: độ dài string, encoding, kiểu dữ liệu, null, protocol framing, row alignment, nén và serializer có thể làm số thực tế khác đáng kể.

Tiết kiệm byte thường giảm áp lực CPU/GC/network; nhưng **không tự chứng minh độ trễ DB đã giảm theo cùng tỷ lệ**. DB có thể vẫn scan hoặc sort rất nhiều hàng nếu thiếu chỉ mục phù hợp.

## 3. Chọn trường cần dùng: projection thay cho `SELECT *`

Lược đồ PostgreSQL minh họa:

~~~sql
CREATE TABLE orders (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         BIGINT NOT NULL,
    customer_id       BIGINT NOT NULL,
    status            VARCHAR(24) NOT NULL,
    total_amount      NUMERIC(14, 2) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shipping_address  TEXT,
    internal_note     TEXT,
    provider_payload  JSONB
);
~~~

Cách lấy dư dữ liệu:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Tốt hơn với mục tiêu trang danh sách:

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Trong truy vấn thứ hai, DB không cần truyền `shipping_address`, `internal_note`, `provider_payload` và những cột không phục vụ màn hình. Với dữ liệu có giá trị lớn được lưu ngoài trang chính (ví dụ cơ chế TOAST của PostgreSQL), projection có thể tránh một phần công việc đọc/giải nén giá trị lớn; mức lợi ích thực tế vẫn tùy plan và cách DB thực thi.

### 3.1. Lợi ích của projection

- **Ít byte hơn:** tránh gửi text, JSON hoặc trường ít dùng.
- **Ít object hơn:** Java không cần dựng entity đầy đủ khi chỉ cần bản tóm tắt.
- **Hợp đồng API rõ hơn:** DTO nói rõ những gì màn hình được nhận.
- **Giảm rủi ro dữ liệu nhạy cảm:** nếu trường không được SELECT thì đường đọc này không vô tình serialize nó.
- **Có thể mở đường cho index-only scan:** nếu những cột truy vấn cần nằm trong index và các điều kiện của DB phù hợp.

Chọn trường cần dùng **không thay thế kiểm tra quyền**. Nếu một tenant không được phép xem đơn hàng của tenant khác, query vẫn phải lọc đúng tenant và tầng service phải xác thực/quyết định quyền truy cập.

### 3.2. Những điều projection không tự giải quyết

Một query chỉ chọn bốn trường vẫn có thể chậm nếu:

- `WHERE` không chọn lọc và thiếu chỉ mục.
- `ORDER BY` phải sort nhiều hàng.
- Query `JOIN` nhân hàng lên ngoài dự đoán.
- Mỗi DTO lại kích hoạt một query bổ sung.
- Màn hình thực sự cần dữ liệu từ nhiều nguồn phải gọi nhiều lần theo kiểu N+1.
- Client yêu cầu lấy toàn bộ các trang trong một request mà không có giới hạn tổng.

**Giảm cột là một đòn bẩy, không phải thay thế phân tích kế hoạch thực thi.**

## 4. Giới hạn số hàng ở database, không phải sau khi materialize

Hai đoạn code dưới đây có ý nghĩa chi phí khác nhau.

**Phân trang sau khi tải toàn bộ:**

~~~java
// Ví dụ sai cho tập dữ liệu lớn.
List<OrderEntity> allOrders = repository.findAll();
List<OrderEntity> page = allOrders.stream()
        .skip(1000)
        .limit(20)
        .toList();
~~~

**Phân trang tại DB:**

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 1000;
~~~

Ở ví dụ thứ hai, DB trả tối đa 20 hàng cho query. Nhưng cần hiểu chính xác: `LIMIT 20` **giới hạn kết quả trả ra**, không bảo đảm DB chỉ phải đọc 20 hàng. Với `OFFSET 1000`, DB có thể cần xác định và bỏ qua 1000 hàng trước đó. Nếu thiếu index phù hợp, DB vẫn có thể đọc/sort tập lớn.

### 4.1. Không dùng `LIMIT` mà thiếu thứ tự

~~~sql
-- Không nên dùng làm phân trang có ngữ nghĩa ổn định.
SELECT id, total_amount
FROM orders
WHERE tenant_id = ?
LIMIT 20;
~~~

Không có `ORDER BY`, DB không cam kết 20 hàng nào được chọn, kể cả khi lần chạy trước “có vẻ trả theo ID”. Thứ tự vật lý, chỉ mục hoặc query plan có thể thay đổi.

Nếu định nghĩa “mới nhất” theo `created_at`, nên có **tie-breaker** quyết định khi nhiều hàng cùng thời điểm:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Ở ví dụ này `id` là duy nhất, nên cặp `(created_at, id)` xác định thứ tự ổn định cho một tập dữ liệu không đổi. Nó **không tạo snapshot cố định xuyên các request** khi có insert/update/delete đồng thời.

### 4.2. Luôn giới hạn page size ở server

Không nên tin hoàn toàn giá trị `limit` từ URL:

~~~text
GET /orders?limit=1000000000
~~~

Ngay cả khi có `LIMIT ?`, giá trị quá lớn vẫn có thể tạo response khổng lồ. Phải đặt max page size theo loại API và dùng validation.

Ví dụ:

~~~java
int pageSize = Math.max(1, Math.min(requestedPageSize, 100));
~~~

Đoạn này minh họa cách **clamp** vào khoảng 1..100. Trong API thực, có thể chọn trả HTTP 400 cho giá trị không hợp lệ, thay vì âm thầm chỉnh số; điều quan trọng là có hợp đồng rõ, không cho caller vô hạn hóa khối lượng dữ liệu.

## 5. OFFSET pagination: đơn giản nhưng có giá khi dữ liệu lớn

Với phân trang theo số thứ tự, ví dụ trang 51 kích thước 20:

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 1000;
~~~

**Ưu điểm:** dễ hiểu, dễ đi tới trang số bất kỳ, hợp với tập nhỏ hoặc báo cáo tương đối ổn định.

**Hạn chế:**

1. OFFSET càng lớn, DB có thể phải đi qua nhiều hàng trước khi trả trang.
2. Nếu có đơn mới chèn vào đầu danh sách giữa hai lần gọi, các trang dùng OFFSET có thể **trùng/bỏ sót bản ghi**.
3. Khi filter/sort phức tạp, truy vấn thường tốn thêm CPU và memory cho sort.
4. Nếu API trả cả `totalElements`, một câu `COUNT(*)` bổ sung có thể đắt với tập lớn.

Ví dụ hai lần phân trang:

~~~text
T0: Danh sách theo ID giảm dần: 10,9,8,7,6,5
    Trang 1 (LIMIT 3 OFFSET 0): 10,9,8

T1: Có ID 11 mới chèn vào đầu.
    Danh sách mới: 11,10,9,8,7,6,5
    Trang 2 (LIMIT 3 OFFSET 3): 8,7,6

Kết quả: ID 8 xuất hiện hai lần.
~~~

OFFSET không sai; nó chỉ có đánh đổi cần công khai. Nếu người dùng yêu cầu trang “mới nhất” theo dòng thời gian và thường duyệt tiếp, **keyset pagination** thường phù hợp hơn.

## 6. Keyset pagination: giới hạn trang theo khóa cuối

Keyset (cursor-based) pagination giữ vị trí của hàng cuối đã hiển thị, rồi yêu cầu các hàng **đứng sau** nó trong cùng thứ tự.

Trang đầu:

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT ?;
~~~

Giả sử hàng cuối trang đầu có `created_at = 2026-11-22T10:00:00Z` và `id = 501`. Trang tiếp theo:

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = ?
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT ?;
~~~

Ở PostgreSQL, phép so sánh tuple `(created_at, id) < (?, ?)` tương ứng với việc lấy các hàng phía sau cursor trong thứ tự **cả hai khóa giảm dần**, giả sử các khóa không NULL và không bị sửa sau khi phát cursor. Cursor phải chứa **đúng giá trị `created_at` và `id` của hàng cuối** trên trang vừa trả.

### 6.1. Vì sao keyset thường nhanh hơn OFFSET lớn?

Với chỉ mục có tiền tố phù hợp cho `tenant_id` và thứ tự `created_at DESC, id DESC`, DB có thể định vị vị trí sau cursor thay vì phải bỏ qua hàng nghìn/millions hàng ở các trang sâu. Mức lợi ích thực vẫn phụ thuộc selectivity, plan, index, kích thước trang và số lần truy cập bảng.

Keyset phù hợp khi giao diện di chuyển “tiếp tục/tải thêm”. Nó không giải quyết trực tiếp yêu cầu “đi tới trang số 500” mà không có cursor trung gian.

### 6.2. Những điều keyset không tự bảo đảm

- **Không tạo snapshot xuyên nhiều HTTP request.** Khi dữ liệu bị xóa, thay đổi sort key hoặc có thay đổi đồng thời, client vẫn phải định nghĩa hành vi phù hợp.
- Nếu `created_at` có thể thay đổi, một hàng có thể chuyển vị trí. Với danh sách đơn, thường coi `created_at` là immutable.
- Với sort key có NULL, so sánh tuple và quy tắc `NULLS FIRST/LAST` cần thiết kế riêng.
- Với filter động, cursor cần gắn với **filter và sort order** để không bị dùng nhầm.
- Cursor không được dùng để vượt qua authorization của tenant. Server xác thực tenant và áp dụng filter ở mọi trang.
- Nếu đưa cursor thô ra client, cần xem xét dữ liệu có nhạy cảm hay không; có thể encode hoặc ký token (opaque cursor) theo hợp đồng API.

### 6.3. `LIMIT pageSize + 1` để biết còn trang sau

Một kỹ thuật phổ biến:

1. Nhận `pageSize` do server giới hạn.
2. Query tối đa `pageSize + 1` hàng.
3. Nếu nhận **nhiều hơn `pageSize`**, còn ít nhất một hàng sau trang được trả trong snapshot của truy vấn đó.
4. Chỉ trả `pageSize` hàng đầu tiên và tạo cursor từ **hàng cuối đã trả**, không lấy cursor từ hàng dư.
5. Không cần chạy thêm `COUNT(*)` cho câu hỏi đơn giản “còn trang tiếp không?”.

Lưu ý: dữ liệu có thể thay đổi trước request kế tiếp; `hasNext` phản ánh kết quả ở thời điểm truy vấn hiện tại, không bảo đảm trang sau sẽ luôn còn dữ liệu.

## 7. Java 17 + JDBC: chỉ lấy ba cột và một trang

Một repository hoàn chỉnh ở mức minh họa trả DTO thay vì entity graph. Để làm rõ cơ chế, response gồm `id`, `createdAt`, `totalAmount`; nếu API cần `status`, thêm đúng cột và field đó, không quay về `SELECT *`.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderPageRepository {
    public record OrderSummary(
            long id, Instant createdAt, BigDecimal totalAmount) {}

    public record Cursor(Instant createdAt, long id) {}

    public record Page(
            List<OrderSummary> items, Cursor nextCursor) {}

    private final DataSource dataSource;

    public OrderPageRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Page listRecent(long tenantId, Cursor cursor, int requestedSize)
            throws SQLException {

        // Một page tối đa 100 hàng, thêm 1 hàng để biết còn dữ liệu.
        int size = Math.max(1, Math.min(requestedSize, 100));

        String firstPageSql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE tenant_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        String nextPageSql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE tenant_id = ?
              AND (created_at, id) < (?, ?)
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        String sql = cursor == null ? firstPageSql : nextPageSql;
        List<OrderSummary> fetched = new ArrayList<>(size + 1);

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, tenantId);

            if (cursor == null) {
                statement.setInt(2, size + 1);
            } else {
                statement.setTimestamp(
                        2, Timestamp.from(cursor.createdAt()));
                statement.setLong(3, cursor.id());
                statement.setInt(4, size + 1);
            }

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    fetched.add(new OrderSummary(
                            rs.getLong("id"),
                            rs.getTimestamp("created_at").toInstant(),
                            rs.getBigDecimal("total_amount")));
                }
            }
        }

        boolean hasNext = fetched.size() > size;
        List<OrderSummary> items = List.copyOf(
                fetched.subList(0, Math.min(fetched.size(), size)));

        if (!hasNext) {
            return new Page(items, null);
        }

        OrderSummary last = items.get(items.size() - 1);
        return new Page(
                items, new Cursor(last.createdAt(), last.id()));
    }
}
~~~

Điều kiện ví dụ:

- PostgreSQL có bảng `orders` như trên, `created_at` là `NOT NULL` và không bị cập nhật khi duyệt.
- `DataSource` là thành phần được ứng dụng cấu hình sẵn; mỗi lời gọi mượn và trả `Connection` đúng cách.
- Không cần giữ toàn bộ result set hay connection sống sau khi trả `Page`.
- `tenantId` phải đến từ context đã được xác thực hoặc được kiểm tra quyền; không dùng một ID tenant bất kỳ do client cung cấp mà không kiểm tra.
- Query có **thứ tự ổn định và giới hạn cứng**, tránh một request tải hàng triệu bản ghi.
- `Cursor` được minh họa bằng record; API thật có thể dùng token đã xác thực chữ ký, kiểm tra phiên bản định dạng và bộ lọc.
- `TIMESTAMPTZ` và cách driver ánh xạ timestamp phải được kiểm thử về múi giờ/độ chính xác với provider đang dùng.

Nếu yêu cầu nghiệp vụ cần snapshot nhất quán qua nhiều request, cần thiết kế snapshot hoặc cơ chế materialized result riêng; repository đơn giản này chỉ đáp ứng phân trang theo thứ tự tại thời điểm mỗi SELECT.

### 7.1. Vì sao không trả `ResultSet` ra controller?

`ResultSet` gắn với `PreparedStatement` và `Connection`. Nếu trả nó ra tầng HTTP, controller/serializer có thể giữ connection trong lúc client đọc chậm, hết connection pool hoặc dùng tài nguyên sau khi đã đóng.

Chuyển hàng cần dùng thành DTO nhỏ **trong phạm vi repository**, đóng `ResultSet` và `Connection` trước khi trả là cách dễ kiểm soát. Streaming rất nhiều hàng có thể phù hợp cho batch export, nhưng cần một giao thức vòng đời riêng về cancellation, backpressure, transaction và tài nguyên.

## 8. JDBC `fetchSize`, `setMaxRows` và SQL `LIMIT` không giống nhau

Đây là nguồn nhầm lẫn thường gặp.

| Công cụ | Phạm vi tác động | Điều không nên suy ra |
| --- | --- | --- |
| `LIMIT` trong SQL | Giới hạn số hàng kết quả của query theo semantics DBMS | Không đảm bảo DB chỉ scan đúng số hàng đó |
| `OFFSET` | Bỏ qua một số hàng trong kết quả có thứ tự | Không miễn chi phí duyệt các hàng bị bỏ qua |
| `Statement.setMaxRows(n)` | Yêu cầu JDBC giới hạn tối đa số hàng mà `ResultSet` cung cấp, theo hợp đồng driver | Không thay thế tối ưu truy vấn hoặc bảo đảm engine giảm việc scan |
| `Statement.setFetchSize(n)` | Gợi ý số hàng driver nên lấy trong một đợt fetch | Không quyết định tổng số hàng của query |
| ORM `setMaxResults(n)` | Giới hạn số kết quả theo API ORM, thường được chuyển xuống SQL | Không chứng minh SQL thật hay collection-fetch pagination là tối ưu |
| `stream().limit(n)` sau `findAll()` | Giới hạn object ở Java sau khi nguồn đã được đọc | Không làm số hàng đã tải từ DB nhỏ đi |

Với PostgreSQL JDBC, server-side cursor/fetch theo đợt thường có các điều kiện như **connection không ở autocommit** và cấu hình fetch size dương, cùng những giới hạn của driver. Cần xem tài liệu và kiểm chứng trên phiên bản driver thực tế. `setFetchSize(100)` **không tự biến SELECT một triệu hàng thành SELECT tối đa 100 hàng**.

Ví dụ dùng fetch size cho tác vụ xử lý dữ liệu theo dòng:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try (PreparedStatement statement =
                 connection.prepareStatement(
                         "SELECT id, total_amount FROM orders " +
                         "WHERE tenant_id = ? ORDER BY id")) {
        statement.setLong(1, tenantId);
        statement.setFetchSize(200);

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                // Xử lý từng hàng và không tích lũy toàn bộ vào heap.
                consumeRow(rs.getLong(1), rs.getBigDecimal(2));
            }
        }
        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
~~~

`consumeRow(...)` là hàm ứng dụng chưa được định nghĩa ở đây; đoạn code minh họa cấu trúc resource/transaction, không phải một lớp có thể biên dịch độc lập. Một transaction đọc dài có thể giữ snapshot, ảnh hưởng vacuum/connection pool và tiêu thụ thời gian xử lý, nên cần chia lô hoặc thiết kế export chuyên biệt khi khối lượng lớn.

**Bài học:** Dùng `LIMIT` khi mục tiêu nghiệp vụ chỉ cần một trang nhỏ. Dùng fetch-by-batch/streaming khi **nghiệp vụ thật sự cần duyệt nhiều hàng**, đồng thời chủ động quản lý giới hạn tài nguyên.

## 9. Projection trong JPA, Hibernate và Spring Data JPA

Dùng ORM có thể làm việc với DTO mà không cần tải đầy đủ entity.

Giả sử `OrderEntity` là entity JPA đã map đúng các thuộc tính `id`, `tenantId`, `createdAt`, `totalAmount`.

Định nghĩa record:

~~~java
package com.example.dto;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(
        Long id, Instant createdAt, BigDecimal totalAmount) {}
~~~

Truy vấn JPQL constructor projection:

~~~java
var query = entityManager.createQuery(
        """
        SELECT new com.example.dto.OrderSummary(
            o.id, o.createdAt, o.totalAmount)
        FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderSummary.class);

var summaries = query
        .setParameter("tenantId", tenantId)
        .setMaxResults(20)
        .getResultList();
~~~

Đây là **projection DTO**, không yêu cầu `SELECT o` để materialize mọi trường của entity và không giữ một graph managed entities chỉ nhằm trả API. Cần kiểm chứng constructor signature, mapping `Instant`, SQL sinh ra và số byte trả về theo provider đang dùng.

### 9.1. Khi Spring Data JPA trả `Page` hoặc `Slice`

Spring Data JPA hỗ trợ phân trang thông qua `Pageable` và các kiểu kết quả như `Page<T>` hoặc `Slice<T>`, theo repository method và cách cấu hình.

- `Page<T>` thường nhằm cung cấp tổng số phần tử/trang. Nó **có thể phát thêm count query**, tùy truy vấn và framework.
- `Slice<T>` có thể phù hợp nếu UI chỉ cần biết có trang kế tiếp mà không cần tổng số kết quả.
- Query derivation/projection interface/class giúp giảm boilerplate, nhưng phải kiểm tra **SQL phát sinh thực tế**, số cột và fetch behavior.
- Collection `JOIN FETCH` kết hợp phân trang có thể sinh kết quả nhân hàng hoặc khiến ORM xử lý paging trong bộ nhớ tùy provider; không mặc định tin rằng `setMaxResults(20)` luôn giới hạn đúng số hàng DB đọc.

Nếu API chỉ hiển thị nút “Xem thêm”, việc chạy một `COUNT(*)` nặng chỉ để hiện tổng số trang có thể không cần thiết.

### 9.2. Không dùng DTO thiếu trường để ghi đè entity

Projection phục vụ **đường đọc**. Không nên lấy một DTO chỉ chứa `id` và `status` rồi gán vào entity detached và gọi `merge()` mà không xác định rõ các trường thiếu; quá trình merge có thể gây cập nhật không mong muốn tùy mapping.

Đường ghi cần thiết kế riêng với optimistic version, conditional update, transaction và các bất biến ở DB. Giảm payload của SELECT không làm mất đi yêu cầu về dữ liệu cần cho quyết định nghiệp vụ.

## 10. Join và N+1: ít cột vẫn có thể nhiều hàng hoặc nhiều query

Giả sử hệ thống còn lưu từng dòng hàng trong bảng sau:

~~~sql
CREATE TABLE order_items (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Chỉ mục trên `order_items(order_id)` là một ứng viên cần đo khi thường xuyên lấy hoặc đếm các dòng hàng theo đơn; PostgreSQL không mặc nhiên tạo chỉ mục phía bảng tham chiếu chỉ vì có foreign key.

Xét trang danh sách đơn cần thêm **số dòng hàng** trong mỗi đơn. Một cách làm thiếu hiệu quả:

~~~text
SELECT 20 orders
for each order:
    SELECT COUNT(*) FROM order_items WHERE order_id = ?
=> 1 + 20 lượt SQL nếu mỗi order gây một query riêng
~~~

Một truy vấn aggregate có thể giảm round trip:

~~~sql
SELECT o.id,
       o.created_at,
       o.total_amount,
       COUNT(i.id) AS item_count
FROM (
    SELECT id, created_at, total_amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY created_at DESC, id DESC
    LIMIT ?
) AS o
LEFT JOIN order_items AS i ON i.order_id = o.id
GROUP BY o.id, o.created_at, o.total_amount
ORDER BY o.created_at DESC, o.id DESC;
~~~

Truy vấn giới hạn **đơn hàng cha trước khi join**, chỉ trả bốn trường mỗi order, không tải toàn bộ items vào Java. Kết quả `COUNT(i.id)` là 0 cho order không có item nhờ `LEFT JOIN`.

Tuy nhiên, một SQL vẫn có thể phải đọc rất nhiều `order_items` nếu mỗi đơn chứa nhiều item. So sánh các phương án qua plan và workload. Có thể dùng batch `IN (...)`, aggregate đã lưu sẵn hoặc read model cho trường hợp phù hợp.

### 10.1. Join fan-out và `SELECT DISTINCT`

Một truy vấn kiểu:

~~~sql
SELECT o.id, o.created_at, i.id, i.quantity
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC
LIMIT 20;
~~~

sẽ trả **20 hàng JOIN**, không mặc nhiên là 20 order. Một order có 10 item chiếm 10 hàng; UI có thể chỉ nhận được vài order khác nhau. Thêm `DISTINCT` một cách mù quáng không luôn giải quyết đúng bài toán và có thể tăng chi phí sort/hash.

Nếu cần 20 order kèm toàn bộ items, hãy phân trang **order ID trước**, rồi fetch items của những ID đó, hoặc dùng chiến lược tải được kiểm chứng. Phải định nghĩa semantics khi có thay đổi đồng thời giữa hai query, nhất là ở `READ COMMITTED`.

## 11. Chỉ mục hỗ trợ lọc, sắp xếp và projection

Để hỗ trợ truy vấn gần nhất theo tenant:

~~~sql
CREATE INDEX idx_orders_tenant_recent
ON orders (tenant_id, created_at DESC, id DESC);
~~~

Chỉ mục này là ứng viên cho filter `tenant_id = ?` và thứ tự `created_at DESC, id DESC`. PostgreSQL có thể dùng index scan để tìm các hàng theo thứ tự mà không cần sort toàn tập; **planner vẫn có quyền chọn plan khác** dựa trên thống kê, kích thước bảng và chi phí.

Nếu truy vấn thường xuyên chỉ đọc `total_amount` cùng các khóa đã có trong index, có thể cân nhắc covering index:

~~~sql
CREATE INDEX idx_orders_tenant_recent_cover
ON orders (tenant_id, created_at DESC, id DESC)
INCLUDE (total_amount);
~~~

**Hai lệnh CREATE INDEX trên là các phương án để so sánh**, không nhất thiết tạo cả hai trên production. Chỉ mục rộng hơn tăng dung lượng, WAL và chi phí INSERT/UPDATE.

PostgreSQL có thể dùng **index-only scan** khi query cần những cột nằm trong index và điều kiện về visibility map/MVCC phù hợp. Việc thêm `INCLUDE` **không đảm bảo** tránh mọi lần đọc heap. Cột `status` nếu còn được SELECT mà không nằm trong index vẫn có thể cần đọc heap; hãy xem plan thực.

### 11.1. Quan sát truy vấn bằng EXPLAIN

Trong môi trường thử nghiệm phù hợp:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Quan sát:

- `actual rows` của các node và tổng hàng output.
- Có `Index Scan`, `Index Only Scan`, `Seq Scan` hay `Sort` không.
- `Buffers: shared hit/read`, thời gian thực thi và ước lượng row có sát thực tế không.
- Với index-only scan, `Heap Fetches` có lớn không.
- Khác biệt giữa query có và không có `provider_payload`/cột rộng trong SELECT.
- Sự thay đổi theo tenant ít dữ liệu và tenant có nhiều đơn.

`EXPLAIN ANALYZE` **thực thi câu lệnh thật**; với SELECT ở đây chỉ đọc dữ liệu nhưng vẫn tiêu thụ tài nguyên. Với lệnh ghi, cần thận trọng hơn nữa vì phân tích có thể gây thay đổi dữ liệu. Không suy ra “index scan chắc chắn tốt hơn seq scan”: với bảng nhỏ hoặc truy vấn trả phần lớn hàng, sequential scan có thể hợp lý.

### 11.2. Đếm hàng khác với đếm byte

`EXPLAIN` cho biết nhiều thông tin về xử lý bên trong database, nhưng không trực tiếp cung cấp con số chính xác “bao nhiêu byte TCP đã truyền về ứng dụng” trong mọi trường hợp. Muốn đánh giá payload end-to-end, cần kết hợp:

1. Số hàng trả ra và các cột được chọn.
2. Phép đo ứng dụng/driver hoặc network ở môi trường test.
3. Thời gian decode/DTO allocation.
4. HTTP response bytes và JSON serialization time.
5. Độ trễ tổng khi tải đồng thời.

PostgreSQL có thể báo ước lượng `width` trong plan; **ước lượng width không phải số byte on-the-wire đã đo**. Kích thước thực phụ thuộc kiểu dữ liệu, protocol và cách mã hóa.

## 12. Giảm payload nhưng giữ đúng tính nhất quán

Projection/pagination phải giữ semantics nghiệp vụ.

### 12.1. Phân trang trong hệ có ghi đồng thời

Một danh sách “đơn mới nhất” không cần thiết mang một snapshot bất biến qua vài phút thao tác của người dùng. Keyset giúp hạn chế trùng do chèn ở đầu danh sách, nhưng nếu status, timestamp hoặc thứ tự bị thay đổi, vẫn có thể bỏ sót/di chuyển hàng.

Nếu báo cáo kế toán yêu cầu snapshot tại một mốc, dùng một DB transaction/snapshot phù hợp hoặc materialized export, chứ không giả định mọi trang gọi HTTP độc lập đều thấy cùng dữ liệu. Với PostgreSQL `READ COMMITTED`, hai SELECT thông thường trong cùng transaction có thể thấy snapshot khác nhau nếu các transaction khác commit giữa chúng.

### 12.2. Projection phải đủ dữ liệu cho phép quyết định

Trong UI, chỉ cần ID và trạng thái có thể là đủ. Nhưng trong bước **đặt hàng**, quyết định trừ tồn kho cần điều kiện ở DB:

~~~sql
UPDATE products
SET stock = stock - ?
WHERE tenant_id = ?
  AND id = ?
  AND stock >= ?;
~~~

Không được dựa vào một DTO stock đã cache hoặc đã đọc từ trước rồi tự tính trong Java mà bỏ cơ chế kiểm soát đồng thời. Giảm trường trong query đọc không phải lý do bỏ mất version/constraint/condition của transaction ghi.

### 12.3. Multi-tenant và dữ liệu nhạy cảm

Tầng server phải:

- Xác minh tenant từ thông tin xác thực và quyền truy cập.
- Gắn `tenant_id` vào query tại DB khi dữ liệu dùng chung bảng.
- Không cho request tự chọn field nhạy cảm chỉ vì endpoint hỗ trợ projection động.
- Dùng **allowlist** cho danh sách field/sort được phép; bind parameter không thay thế việc kiểm tra identifier SQL nếu phải dựng `ORDER BY` động.
- Tránh log payload lớn chứa PII/secret; giới hạn telemetry ở metadata cần thiết.
- Kiểm tra API serializer để DTO không vô tình đưa field nội bộ ra ngoài.

Ví dụ chuỗi `ORDER BY ?` với `PreparedStatement` **không có nghĩa bind được tên cột SQL** như giá trị: dấu `?` là value parameter, không phải identifier. Muốn sort động, map từ lựa chọn đã duyệt (ví dụ `createdAt`, `totalAmount`) sang biểu thức SQL tin cậy do server định nghĩa.

## 13. API response cũng cần giới hạn

Dù repository chỉ đọc 20 hàng, một response có thể phình to nếu service lại đưa thêm các quan hệ, lịch sử sự kiện hoặc metadata lớn.

Ví dụ thiết kế response:

~~~json
{
  "items": [
    {
      "id": 501,
      "createdAt": "2026-11-22T10:00:00Z",
      "totalAmount": "250000.00"
    }
  ],
  "nextCursor": "opaque-signed-page-token"
}
~~~

Hợp đồng nên nêu rõ:

- `items` tối đa bao nhiêu phần tử.
- Những field được trả và kiểu dữ liệu/định dạng JSON.
- `nextCursor` có thể `null` khi không còn trang.
- Cursor được ràng buộc với tenant, filter, sort và nếu cần là thời hạn sử dụng.
- Thứ tự ổn định và chính sách khi có hàng mới/xóa giữa các request.
- Giới hạn tổng số trang hoặc thời gian export cho client dùng API hàng loạt.

HTTP compression như gzip/br có thể giảm số byte qua mạng đối với JSON, nhưng **không xóa chi phí DB truyền thừa các cột về Java** và không thay việc giới hạn dữ liệu. Nén còn tiêu tốn CPU; đo theo workload và cấu hình thực.

## 14. Khi nào không nên cố giảm payload hơn nữa?

Tối ưu sai có thể làm hệ thống chậm hoặc kết quả sai:

- Chỉ chọn `id` nhưng sau đó gọi `SELECT` từng ID để lấy thêm thông tin → N+1.
- Đọc cùng một hàng nhiều lần thay vì lấy một projection vừa đủ cho use case.
- Ép `LIMIT 20` vào tác vụ xuất dữ liệu cần đầy đủ kết quả → thiếu dữ liệu nghiệp vụ.
- Dùng keyset cho sort key thay đổi liên tục mà không định nghĩa hành vi → bỏ sót.
- Tách một query nhất quán thành nhiều query không có snapshot phù hợp → dữ liệu không khớp.
- Giảm trường xác nhận xung đột/phiên bản khỏi câu ghi → lost update.
- Gửi mọi trường trong query nhưng chỉ ẩn JSON field ở serializer → DB → Java vẫn bị thừa.
- Thêm covering index cho mọi trường chỉ để có index-only scan → write amplification, WAL và dung lượng tăng mạnh.

**Câu hỏi trước khi tối ưu:** Người gọi cần thông tin gì để hoàn thành một hành động **đúng**, không chỉ để hiển thị màn hình? Chỉ cắt dữ liệu thừa sau khi xác định phần dữ liệu bắt buộc.

## 15. Một quy trình đo có thể tái hiện

Một thử nghiệm nên so sánh ít nhất ba phiên bản:

- **A — baseline:** `SELECT *`/tải mọi entity rồi phân trang trong Java.
- **B — SQL projection + LIMIT:** chỉ lấy trường cần thiết của trang.
- **C — projection + keyset/index phù hợp:** kiểm tra khi đi sâu qua nhiều trang.

Để so sánh công bằng:

1. Chuẩn bị dữ liệu thử nghiệm tương tự production: tenant nhỏ, tenant lớn, cột text/JSON có độ dài biến thiên và phân bố `created_at` thực tế.
2. Ghi rõ kích thước page, filter, sort, số request đồng thời, trạng thái cache nóng/lạnh.
3. Dùng cùng query semantics để kiểm tra tính đúng đắn: số hàng, thứ tự, không lộ tenant khác, field DTO chính xác.
4. Đo DB plan bằng `EXPLAIN (ANALYZE, BUFFERS)` cho SQL tương ứng.
5. Đo SQL count, bytes DB → ứng dụng nếu có công cụ, allocation/GC, connection hold time và HTTP response bytes.
6. Đo p50/p95/p99 ở nhiều mức concurrency thay vì chỉ chạy một query đơn lẻ.
7. Kiểm tra phân trang khi có insert/delete đồng thời; xác định chấp nhận trùng/bỏ sót hay yêu cầu snapshot.
8. Đo tác động đến INSERT/UPDATE và dung lượng nếu đã thêm index phục vụ projection.
9. Ghi kết quả trước/sau cùng giả định, không kết luận từ một lần đo quá ngắn.

Bảng báo cáo có thể dùng:

| Metric | A: baseline | B: projection + LIMIT | C: keyset + index |
| --- | --- | --- | --- |
| SQL statements/request | Đo thực tế | Đo thực tế | Đo thực tế |
| Rows DB → Java | Đo | Đo | Đo |
| DB transfer bytes | Đo nếu có telemetry | Đo | Đo |
| Heap allocation/request | Đo | Đo | Đo |
| HTTP response bytes | Đo | Đo | Đo |
| DB execution p95 | Đo | Đo | Đo |
| API p95/p99 | Đo | Đo | Đo |
| Write throughput sau thêm index | Baseline | So sánh | So sánh |

Không điền số liệu “tăng gấp 10 lần” nếu chưa thực sự benchmark. Mục tiêu là có một giả thuyết đo được và kiểm chứng bằng dữ liệu.

## 16. Các sai lầm thường gặp

**“`SELECT *` tiện hơn, trả về 20 hàng thôi nên không sao.”** Nếu mỗi hàng có JSON/text lớn hoặc PII, payload vẫn có thể lớn; projection giúp hạn chế.

**“Dùng `stream().limit(20)` ở Java là DB chỉ gửi 20 hàng.”** Nếu upstream đã materialize cả bảng, giới hạn ở Java xảy ra quá muộn.

**“`setFetchSize(50)` tương đương `LIMIT 50`.”** Fetch size là gợi ý batch fetch, không phải số hàng tối đa.

**“`setMaxRows(50)` luôn tối ưu DB tốt như SQL LIMIT.”** Driver có thể giới hạn hàng ở JDBC nhưng không bảo đảm engine tránh scan/sort thừa.

**“Có LIMIT thì không cần ORDER BY.”** Phân trang thiếu thứ tự không có tính ổn định.

**“OFFSET càng cao vẫn tốn chi phí bằng trang đầu.”** DB có thể phải duyệt/bỏ qua nhiều hàng trước khi tới trang sâu.

**“Keyset bảo đảm snapshot không đổi.”** Keyset giữ vị trí theo sort key nhưng không cố định toàn bộ tập qua nhiều request.

**“Chỉ cần lấy cột ít hơn là index-only scan.”** Còn phụ thuộc index, MVCC/visibility map và kế hoạch thực thi.

**“Ít SQL luôn nhanh hơn.”** Một query JOIN quá lớn có thể tốn nhiều hơn vài query nhỏ hợp lý; xem cả fan-out và bytes.

**“Chuyển entity sang DTO ở controller là đã giảm dữ liệu DB truyền.”** Nếu entity được SELECT đầy đủ trước khi map DTO, DB → Java chưa được giảm.

**“Để client chọn bất kỳ field nào giúp API linh hoạt.”** Không có allowlist/authorization có thể làm lộ dữ liệu hoặc tạo query quá nặng.

**“Tối ưu độ lớn response không cần kiểm tra transaction.”** Việc tách query hoặc bỏ trường dùng để kiểm tra xung đột có thể phá tính nhất quán nghiệp vụ.

## 17. Bài tập thực hành

**Bài 1 — sửa `SELECT *`.** Một API cần 30 đơn mới nhất với `id`, `status`, `total_amount`, nhưng repository gọi `SELECT * FROM orders` rồi lọc tenant ở Java. Hãy viết SQL có `WHERE`, `ORDER BY`, `LIMIT` và giải thích lợi ích về network, heap và bảo mật.

**Bài 2 — so sánh payload.** Cho 5.000 hàng, mỗi hàng khoảng 1,5 KiB dữ liệu, trong khi một trang chỉ cần 25 hàng × 80 byte dữ liệu trường. Hãy ước lượng payload logic baseline và projection; nêu những overhead khiến wire bytes thực tế khác ước lượng.

**Bài 3 — OFFSET và keyset.** Giao diện sắp xếp `created_at DESC, id DESC`, trang kích thước 20. Viết truy vấn OFFSET cho trang 51 và truy vấn keyset dựa trên cursor của hàng cuối trang 50. Đánh giá hiệu năng, khả năng nhảy trang và hành vi khi có insert mới.

**Bài 4 — JDBC.** Giải thích `LIMIT`, `setMaxRows`, `setFetchSize` và `ResultSet.next()`. Nếu một export phải đọc 10 triệu hàng, cách xử lý tài nguyên khác API danh sách 20 hàng như thế nào?

**Bài 5 — JPA/Hibernate.** Một method trả `List<OrderEntity>` rồi serializer duyệt quan hệ items. Hãy xây JPQL constructor projection trả `OrderSummary`; xác định dữ liệu cần cho UI và cách đo N+1/query count khi cache lạnh.

**Bài 6 — covering index.** Với filter tenant và sort theo `created_at`, đề xuất index trên `(tenant_id, created_at DESC, id DESC)`. Đo `EXPLAIN (ANALYZE, BUFFERS)` trước/sau. Thêm `INCLUDE(total_amount)` có làm mọi query index-only không? Vì sao?

**Bài 7 — security boundary.** Một endpoint cho client truyền `fields=id,totalAmount,internalNote` và `sort=...`. Thiết kế danh sách field/sort được phép, tenant authorization, giới hạn page size và response validation để không lộ dữ liệu.

**Bài 8 — quyết định tối ưu.** API A cần hiển thị 20 sản phẩm, API B cần xuất toàn bộ dữ liệu theo lô, API C kiểm tra tồn kho trước khi thanh toán. Với mỗi API, hãy lựa chọn projection, LIMIT, keyset, streaming và transaction/conditional UPDATE phù hợp. Giải thích vì sao không dùng một cơ chế cho tất cả.

## Ghi nhớ

**Muốn giảm dữ liệu truyền, hãy chọn đúng trường và đúng số hàng từ database**: dùng projection/DTO thay cho `SELECT *` khi chỉ cần vài field, filter theo tenant tại DB, thêm `ORDER BY` có tie-breaker và áp dụng `LIMIT` có giới hạn do server kiểm soát. Khi đi sâu qua nhiều trang, cân nhắc keyset thay OFFSET lớn; khi chỉ cần biết có trang kế tiếp, `LIMIT pageSize + 1` có thể tránh count query không cần thiết.

Trong Java persistence, cần phân biệt giới hạn SQL với fetch size, tránh materialize toàn bộ entity rồi mới lọc, quan sát SQL do ORM phát sinh, và đo cả database plan lẫn bytes/latency end-to-end. **Giảm payload là tối ưu có ích khi không làm sai semantics, ranh giới transaction hoặc quyền truy cập dữ liệu.**
