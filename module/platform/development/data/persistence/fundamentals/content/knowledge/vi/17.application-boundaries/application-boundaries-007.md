# Tách truy vấn phục vụ đọc khỏi thao tác thay đổi trạng thái khi cần

Một màn hình danh sách đơn hàng cần đọc nhanh một vài trường để hiển thị. Trong khi đó, thao tác hủy đơn phải kiểm tra quyền, trạng thái hiện tại, phiên bản dữ liệu và bảo đảm mọi thay đổi liên quan được commit cùng nhau. Hai nhu cầu này đều truy cập cơ sở dữ liệu, nhưng có **mục tiêu, giao diện và ranh giới giao dịch khác nhau**.

Việc tách **truy vấn phục vụ đọc** (*query*) khỏi **thao tác thay đổi trạng thái** (*command*) giúp mã nguồn thể hiện rõ ý định: phía đọc trả dữ liệu cần hiển thị; phía ghi chịu trách nhiệm bảo vệ bất biến nghiệp vụ. Đây là cách áp dụng thực dụng của nguyên tắc *Command Query Separation* và có thể tiến dần đến *CQRS* (*Command Query Responsibility Segregation*) nếu nhu cầu phức tạp hơn.

Trong chương **Ranh giới ứng dụng** thuộc **DATA_PERSISTENCE_FUNDAMENTALS**, mục tiêu không phải đưa thêm tầng kiến trúc bằng mọi giá. Người học cần biết **khi nào tách là có ích**, cách tổ chức Java/JDBC để giữ transaction ngắn và đúng phạm vi, khi nào đọc và ghi có thể dùng chung database, và cách bảo đảm tính nhất quán khi tối ưu đường đọc.

## 1. Đọc và ghi khác nhau ở điểm nào?

Một **query** trả về dữ liệu và về nguyên tắc **không thay đổi trạng thái nghiệp vụ**. Một **command** thể hiện yêu cầu thay đổi trạng thái, chẳng hạn hủy đơn, giữ chỗ hoặc chuyển tiền. Command có thể trả về mã định danh, kết quả thành công/thất bại hoặc phiên bản mới; điều cốt lõi là bên ghi sở hữu các quy tắc thay đổi, thay vì để controller tự ghép một chuỗi cập nhật.

| Khía cạnh | Đường đọc (query) | Đường ghi (command) |
| --- | --- | --- |
| Mục đích | Tra cứu, lọc, sắp xếp, tổng hợp, hiển thị | Thực hiện một thay đổi nghiệp vụ hợp lệ |
| Dữ liệu trả về | DTO, projection, danh sách, báo cáo theo nhu cầu màn hình | Kết quả lệnh, ID, phiên bản, lý do từ chối |
| Quy tắc chính | Phân quyền xem, giới hạn dữ liệu, tối ưu truy vấn | Phân quyền thao tác, bất biến, kiểm soát đồng thời |
| Giao dịch | Một câu đọc ngắn; có thể cần snapshot nếu gồm nhiều câu | Transaction bao trùm các thay đổi phải commit cùng nhau |
| Hiệu năng | Giảm số trường trả về, tối ưu index, phân trang, cache | Giảm thời gian giữ khóa; thực hiện ghi có điều kiện |
| Khi thất bại | Có thể đọc lại nếu phù hợp yêu cầu nhất quán | Phải biết giao dịch đã abort, còn hợp lệ hay kết quả commit chưa rõ |

Chẳng hạn, một API có hai hành vi:

```text
GET  /orders                     -> Danh sách OrderSummary
POST /orders/{orderId}/cancel    -> CancelOrder(command)
```

GET cần chọn đúng các cột và bảo đảm khách hàng chỉ thấy đơn của mình. POST cần xác nhận đơn đang ở trạng thái được hủy, tránh cập nhật đè thay đổi của yêu cầu khác, và ghi sự kiện nếu hệ thống yêu cầu. Một phương thức chung kiểu `saveOrFindOrder(...)` khó biểu đạt rõ hai trách nhiệm ấy.

Lưu ý: **khác trách nhiệm không bắt buộc khác database hoặc khác bảng**. Trong giai đoạn đầu, cả hai đường vẫn có thể dùng cùng một `DataSource`, cùng schema và các repository đơn giản. Sự tách biệt đầu tiên có thể chỉ là tên method, kiểu dữ liệu và ranh giới giao dịch rõ ràng.

## 2. Khi nào nên tách, khi nào chưa cần?

Tách đọc/ghi thường có lợi khi:

- **Đường đọc cần hình dạng dữ liệu khác mô hình ghi:** một trang danh sách cần mã đơn, trạng thái, số tiền, thời điểm; phần ghi cần nhiều quy tắc và trạng thái trung gian.
- **Nhu cầu hiệu năng khác nhau:** truy vấn danh sách cần index, phân trang hoặc cache riêng; cập nhật cần khóa, ràng buộc và các transaction ngắn.
- **Nhiều nơi cùng thay đổi một đối tượng:** API, job nền và consumer cùng phải tuân thủ một bộ quy tắc; đặt quy tắc ở command service tránh mỗi nơi tự ghép SQL khác nhau.
- **Có bất biến đồng thời:** hai yêu cầu hủy/xác nhận cùng lúc cần kiểm tra trạng thái và version ngay trong câu ghi, thay vì chỉ tin bản ghi vừa được đọc.
- **Cần tích hợp hệ thống ngoài:** sau khi ghi phải phát sự kiện hoặc thông báo; command boundary thuận tiện cho transactional outbox.

Không nhất thiết áp dụng một kiến trúc CQRS lớn cho CRUD đơn giản. Nếu form chỉ sửa tên hiển thị, một repository rõ ràng với phương thức đọc và phương thức cập nhật có kiểm tra quyền có thể đủ. Tách thành hai service, hai schema, hai database, message broker và read model đồng bộ bất đồng bộ khi chưa có nhu cầu thực tế sẽ làm tăng số trạng thái cần quản lý và độ khó kiểm thử.

Có thể tiến hóa theo các mức:

1. **Một repository:** tách tên hàm đọc và ghi, dùng DTO đầu ra thay vì lộ toàn bộ entity.
2. **Hai đường ứng dụng rõ ràng:** `OrderQueryService` và `OrderCommandService` cùng dùng database chính; transaction và quyền tách riêng.
3. **Projection/read model chuyên biệt:** dùng truy vấn tổng hợp, view hoặc bảng projection cùng DB nếu đường đọc phức tạp.
4. **Read model bất đồng bộ hoặc replica:** chỉ dùng khi lợi ích tải/độ trễ vượt chi phí đồng bộ, quan sát độ trễ dữ liệu và xử lý sai lệch.

Các mức trên là lựa chọn thiết kế, không phải một chuỗi bắt buộc. Một ứng dụng có thể dừng ở mức 1 hoặc 2 trong thời gian dài mà vẫn có ranh giới rõ và hiệu năng tốt.

## 3. Ví dụ xuyên suốt: đọc danh sách và hủy đơn

Giả sử ứng dụng Java quản lý các đơn hàng trong PostgreSQL. Đơn có trạng thái `PENDING`, `CONFIRMED` hoặc `CANCELLED`. Quy tắc minh họa: **chỉ đơn PENDING được hủy**, khách hàng chỉ được hủy đơn của mình, và thao tác hủy phải ghi một bản tin vào outbox trong **cùng transaction** để worker phát sự kiện sau commit.

Schema đơn giản:

```sql
CREATE TABLE customer_orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    total_amount NUMERIC(18, 2) NOT NULL CHECK (total_amount >= 0),
    version      BIGINT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id   UUID PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES customer_orders(order_id),
    event_type VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_customer_orders_recent
ON customer_orders (customer_id, updated_at DESC, order_id DESC)
INCLUDE (status, total_amount, version);
```

Chỉ mục cuối phục vụ đường đọc theo khách hàng và thời gian gần nhất. `INCLUDE` là cú pháp PostgreSQL cho cột bổ sung dùng để bao phủ truy vấn; nó có chi phí lưu trữ/ghi và **không bảo đảm** cơ sở dữ liệu sẽ chọn `Index Only Scan`. Cần đánh giá bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện trước khi tạo chỉ mục rộng trong production.

### 3.1. Phía đọc: trả DTO đúng nhu cầu

API danh sách có thể dùng câu SQL chỉ lấy các cột cần hiển thị:

```sql
SELECT order_id, status, total_amount, updated_at, version
FROM customer_orders
WHERE customer_id = ?
ORDER BY updated_at DESC, order_id DESC
LIMIT ?;
```

Phần triển khai JDBC sau dùng Java 17+ và PostgreSQL JDBC driver hỗ trợ ánh xạ `TIMESTAMPTZ` sang `OffsetDateTime`:

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

public final class OrderQueryRepository {
    public record OrderSummary(
            long orderId, String status, BigDecimal totalAmount,
            OffsetDateTime updatedAt, long version) {}

    private final DataSource dataSource;

    public OrderQueryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderSummary> listRecent(long customerId, int pageSize)
            throws SQLException {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize phải trong 1..100");
        }

        String sql = """
            SELECT order_id, status, total_amount, updated_at, version
            FROM customer_orders
            WHERE customer_id = ?
            ORDER BY updated_at DESC, order_id DESC
            LIMIT ?
            """;
        List<OrderSummary> result = new ArrayList<>();

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setInt(2, pageSize);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new OrderSummary(
                            rs.getLong("order_id"),
                            rs.getString("status"),
                            rs.getBigDecimal("total_amount"),
                            rs.getObject("updated_at", OffsetDateTime.class),
                            rs.getLong("version")));
                }
            }
        } // Đóng ResultSet/statement và trả connection trước khi trả DTO.

        return result;
    }
}
```

Đường đọc trả về `OrderSummary` độc lập với `Connection`/`ResultSet`. Nó không cần tải một aggregate đầy đủ chỉ để dựng danh sách. `customerId` phải lấy từ ngữ cảnh xác thực/phân quyền đáng tin cậy ở tầng ứng dụng, không tự động tin một ID do người gọi bất kỳ gửi lên.

Ở ví dụ này, một `SELECT` có thể chạy trong transaction ngắn theo chế độ auto-commit của pool. Nếu một báo cáo cần **nhiều câu SQL phải cùng nhìn một snapshot**, có thể mở transaction đọc với isolation thích hợp, nhưng vẫn phải đóng sớm; hai câu lệnh tự động commit riêng biệt không bảo đảm cùng snapshot.

### 3.2. Phía ghi: kiểm tra điều kiện trong chính câu UPDATE

Ngược lại, thao tác hủy dùng một lệnh cập nhật có điều kiện:

```sql
UPDATE customer_orders
SET status = 'CANCELLED',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = ?
  AND customer_id = ?
  AND status = 'PENDING'
  AND version = ?;
```

Điều kiện `status = 'PENDING'` ngăn hủy đơn đã xác nhận; `version = ?` giúp phát hiện yêu cầu đã dựa trên trạng thái cũ. Việc kiểm tra và cập nhật ở **cùng một câu SQL** quan trọng hơn cách controller đọc trạng thái trước đó. Nếu có hai lệnh cạnh tranh, cơ sở dữ liệu xử lý xung đột ghi theo cơ chế khóa/cô lập và chỉ lệnh đáp ứng điều kiện tại thời điểm thực thi thích hợp mới cập nhật thành công.

Nếu số hàng ảnh hưởng bằng `0`, có thể là không tồn tại đơn, sai khách hàng, trạng thái không cho phép hoặc version đã thay đổi. Tầng API cần phân loại khi cần thiết nhưng không được làm lộ sự tồn tại của đơn thuộc khách hàng khác. Việc đọc lại để quyết định lỗi trả về cũng phải tôn trọng quyền truy cập.

Để bảo đảm cập nhật trạng thái và ghi event cùng commit, đặt cả hai trong một transaction. Ví dụ Java/JDBC:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public final class OrderCommandService {
    private final DataSource dataSource;

    public OrderCommandService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    // eventId được cấp ổn định cho một yêu cầu ở tầng gọi.
    public boolean cancel(long customerId, long orderId,
                          long expectedVersion, UUID eventId)
            throws SQLException {
        if (eventId == null) {
            throw new IllegalArgumentException("eventId không được null");
        }

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String update = """
                    UPDATE customer_orders
                    SET status = 'CANCELLED',
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ? AND customer_id = ?
                      AND status = 'PENDING' AND version = ?
                    """;
                try (PreparedStatement ps = c.prepareStatement(update)) {
                    ps.setLong(1, orderId);
                    ps.setLong(2, customerId);
                    ps.setLong(3, expectedVersion);
                    if (ps.executeUpdate() != 1) {
                        c.rollback();
                        return false;
                    }
                }

                String outbox = """
                    INSERT INTO outbox_events (event_id, order_id, event_type)
                    VALUES (?, ?, 'ORDER_CANCELLED')
                    """;
                try (PreparedStatement ps = c.prepareStatement(outbox)) {
                    ps.setObject(1, eventId);
                    ps.setLong(2, orderId);
                    ps.executeUpdate();
                }

                c.commit();
                return true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

Service sở hữu transaction trong ví dụ nên có thể `commit`/`rollback`. Pool JDBC cần khôi phục trạng thái `autoCommit` khi connection được trả. Nếu ứng dụng dùng Spring/JPA hoặc một tầng gọi đã sở hữu transaction, repository cần **tham gia giao dịch đang có**; không tự mở/commit một transaction riêng theo mẫu trên.

Ghi outbox trong cùng transaction bảo đảm: nếu câu `INSERT outbox_events` thất bại, cập nhật `CANCELLED` cũng rollback. Worker khác có thể đọc outbox **sau commit** và gửi thông điệp mà không giữ khóa của transaction hủy đơn. Việc gửi có thể lặp nếu worker chết sau khi broker đã nhận; consumer cần xử lý idempotent theo `event_id`.

Đoạn code tập trung vào ranh giới đọc/ghi, **chưa phải API hoàn chỉnh bảo đảm idempotency**. Nếu `COMMIT` báo lỗi do mất kết nối, kết quả có thể chưa rõ. Một yêu cầu được gửi lại với cùng `eventId` cần tra cứu, đối soát kết quả tương ứng và kiểm tra tham số trước khi quyết định chạy lại; trả `false` chỉ vì version đã đổi chưa đủ phân biệt “đã hủy thành công ở lần trước” với “bị yêu cầu khác sửa”. Cũng không retry tự động mọi `SQLException`.

## 4. Phân chia lớp theo ý định, không theo số bảng

Một cách tổ chức ứng dụng đơn giản:

```text
HTTP / gRPC / Job / Consumer
           |
        Application
       /           \
  QueryService   CommandService
       |              |
  QueryRepository  CommandRepository / Unit of Work
       |              |
       +------ Database chính ------+
                          |
                    Outbox dispatcher
                          |
                        Broker
```

| Thành phần | Trách nhiệm |
| --- | --- |
| Controller/transport | Xác thực, ánh xạ input, chọn use case, ánh xạ kết quả ra HTTP/gRPC |
| Query service/repository | Áp dụng quyền đọc, chọn dữ liệu cần hiển thị, thực hiện phân trang và truy vấn |
| Command service | Kiểm tra quyền thay đổi, điều kiện nghiệp vụ, điều phối transaction và kết quả cập nhật |
| Domain policy | Quy tắc bất biến như “đơn CONFIRMED không được hủy” hoặc “số dư không âm” |
| Persistence adapter | SQL, ánh xạ kiểu, khóa, isolation, lỗi DB, quản lý tài nguyên |
| Outbox dispatcher | Truyền thông điệp sau commit, retry/lease và xử lý giao hàng có thể lặp |

Trong hệ thống nhỏ, QueryService có thể được gộp với QueryRepository; CommandService có thể trực tiếp dùng JDBC như ví dụ. Điểm chính là **bên đọc không vô tình thay đổi trạng thái** và **bên ghi không dựa trên phép đọc không được bảo vệ để quyết định cập nhật**.

Không nên để controller gọi `repository.findOrder()`, tự kiểm tra một điều kiện, sau đó gọi `repository.save()` mà thiếu ranh giới transaction hoặc điều kiện đồng thời; giữa hai lời gọi, người khác có thể đã thay đổi đơn. Một command nên thể hiện được **toàn bộ quyết định và thay đổi mà nó chịu trách nhiệm**.

## 5. Đọc không tạo tác động nghiệp vụ

Đường đọc nên dễ cache, có thể gọi lại và không khiến trạng thái nghiệp vụ thay đổi. Một ví dụ cần tránh là:

```java
// Mẫu cần xem lại:
public OrderDetail getOrder(long id) {
    Order order = repository.findById(id);
    order.setStatus("VIEWED");     // thay đổi nghiệp vụ khi chỉ muốn đọc
    repository.save(order);
    return mapToDetail(order);
}
```

Nếu tác vụ cập nhật đánh dấu đã xem là yêu cầu nghiệp vụ thực sự, hãy biểu diễn nó bằng một **command rõ ràng** hoặc một sự kiện độc lập có ranh giới thích hợp. Không dùng HTTP GET để thực hiện chuyển trạng thái có hậu quả đáng kể: browser, crawler, proxy, prefetch, cache hoặc client có thể gửi lại GET mà người dùng không chủ ý thao tác.

Việc đường đọc ghi **log truy cập hoặc metric** phục vụ vận hành không đồng nghĩa với command thay đổi trạng thái nghiệp vụ. Nhưng một câu `SELECT` không mặc nhiên “không tác động”: nó có thể gọi hàm có side effect, lấy khóa `FOR UPDATE`, hoặc khiến ORM tự động flush những thay đổi đang chờ trong một session. Với Spring, `@Transactional(readOnly = true)` là tín hiệu tối ưu/chế độ được framework và driver xử lý tùy cấu hình, **không phải biện pháp phân quyền hoặc bảo đảm tuyệt đối rằng không thể ghi**.

Ranh giới query cần đáp ứng cả **bảo mật và hiệu năng**: chỉ lấy dữ liệu mà caller được phép xem, hạn chế `SELECT *`, tránh N+1 khi truy cập quan hệ lười, và trả DTO đã được materialize trước khi đóng connection/session.

## 6. Đường đọc tối ưu khác đường ghi

Một danh sách thường không cần tải toàn bộ object graph và các trường phục vụ cập nhật. Với ví dụ đơn hàng, truy vấn đã có `ORDER BY updated_at DESC, order_id DESC` giúp thứ tự ổn định khi nhiều đơn cùng thời điểm.

Một số lựa chọn phổ biến:

- **Projection:** chọn đúng cột cho danh sách; đối với dashboard có thể dùng phép tổng hợp `GROUP BY`, view hoặc bảng chỉ đọc chuyên dụng.
- **Phân trang:** `LIMIT/OFFSET` dễ dùng nhưng trang sâu có thể đắt; keyset pagination theo `(updated_at, order_id)` có thể tốt hơn với danh sách lớn và thứ tự ổn định.
- **Chỉ mục:** chọn khóa phù hợp với `WHERE` và `ORDER BY` dựa trên query plan thực tế; tránh nhân bản nhiều index gần giống nhau nếu chi phí ghi tăng cao.
- **Cache:** đặt TTL, key, phân quyền, cơ chế invalidation/refresh và quy tắc chấp nhận dữ liệu cũ. Không dùng cache làm nguồn quyết định cuối cho bất biến ghi.
- **Snapshot đọc:** khi một báo cáo cần nhất quán qua nhiều câu SQL, cần xác định mức cô lập và vòng đời transaction đọc. `READ COMMITTED` của một số DB không bảo đảm hai câu thấy cùng snapshot.

Ví dụ keyset pagination trong PostgreSQL, với cursor được lấy từ hàng cuối của trang trước:

```sql
SELECT order_id, status, total_amount, updated_at, version
FROM customer_orders
WHERE customer_id = ?
  AND (updated_at, order_id) < (?, ?)
ORDER BY updated_at DESC, order_id DESC
LIMIT ?;
```

Điều kiện tuple dùng hai cột giảm dần, không nên hoán đổi vị trí hoặc dấu so sánh khi thay chiều sắp xếp. Cursor nên gắn với bộ lọc, thứ tự và người dùng tương ứng; nếu danh sách có các cập nhật làm đổi `updated_at` giữa hai lần đọc thì pagination vẫn có thể thấy dữ liệu thay đổi, vì nó không tạo snapshot xuyên nhiều HTTP requests.

Đường ghi ưu tiên **tính đúng đắn, bất biến và khả năng phục hồi**. Không nên bỏ điều kiện `version` khỏi command chỉ vì một màn hình đang cache danh sách cũ; thay vào đó, nếu cập nhật bị từ chối, giao diện cần tải lại và trình bày xung đột thích hợp.

## 7. Khi tách thành read model riêng: chấp nhận mức nhất quán nào?

Đường đọc và ghi có thể dùng cùng một DB. Nếu khối lượng đọc rất lớn, một lựa chọn khác là phục vụ query từ **read replica** hoặc **projection** được cập nhật sau giao dịch ghi. Khi ấy, dữ liệu phía đọc có thể chậm hơn phía ghi.

```text
Command ── UPDATE DB chính ── COMMIT ───> response thành công
                    |
                    +── change/outbox event
                                |
                                v
                       Projection consumer
                                |
                                v
                        Read model / replica
                                |
                                v
                           Query API
```

**Ví dụ:** người dùng hủy đơn thành công nhưng danh sách lấy từ replica vẫn hiển thị `PENDING` trong một khoảng thời gian. Đây là vấn đề *read-after-write consistency*. Nếu giao diện yêu cầu thấy trạng thái vừa ghi ngay, có thể:

1. Trả trạng thái/phiên bản mới từ command và cập nhật giao diện tức thời, trong khi vẫn phân biệt với dữ liệu được tải lại.
2. Đọc lại từ database chính trong khoảng thời gian cần **read-your-writes**.
3. Dùng version/offset/LSN hoặc cơ chế watermark thích hợp, chỉ phục vụ khi read model đã bắt kịp mốc commit.

Mỗi phương án có chi phí. Trả dữ liệu mới từ command giúp UI phản hồi nhanh, nhưng nếu màn hình phải hiển thị một báo cáo tổng hợp phức tạp, có thể vẫn phải chờ projection cập nhật hoặc hiển thị trạng thái đang đồng bộ.

Khi có consumer cập nhật projection, cần đảm bảo:

- **Idempotency:** sự kiện có thể bị giao lại; xử lý trùng theo `event_id` hoặc phiên bản sự kiện.
- **Thứ tự:** sự kiện cho cùng một đơn có thể đến lệch thứ tự; chỉ áp dụng phiên bản mới hơn khi quy tắc projection yêu cầu.
- **Khôi phục:** định nghĩa cách tái dựng projection từ nguồn sự thật, mốc checkpoint và cách xử lý sự kiện lỗi.
- **Quan sát:** đo độ trễ giữa thời điểm DB commit và thời điểm read model cập nhật; có ngưỡng cảnh báo khi dữ liệu quá cũ.
- **Phân quyền:** read model có thể chứa dữ liệu đã được tổng hợp/denormalize; không được để tối ưu đọc làm lộ dữ liệu giữa khách hàng hoặc tenant.

**CQRS không đồng nghĩa với event sourcing.** Có thể tách query và command ngay trên một database quan hệ thông thường mà không lưu mọi thay đổi dưới dạng sự kiện. Event sourcing là một lựa chọn mô hình lưu trữ khác, thường có thêm yêu cầu về replay, schema event và tiến hóa dữ liệu.

## 8. Giao dịch, quyền và lỗi phải được giữ ở phía command

Đường đọc có thể hiển thị nút “Hủy đơn” khi trạng thái hiện tại là `PENDING`, nhưng điều đó chỉ hỗ trợ **trải nghiệm người dùng**, không phải quyết định nghiệp vụ cuối cùng. Giữa lúc tải trang và nhấn nút, đơn có thể đã được xác nhận bởi job hoặc yêu cầu khác.

Phía command cần xác minh lại những điều kiện quan trọng **trong ranh giới giao dịch phù hợp**:

| Rủi ro | Cách xử lý |
| --- | --- |
| Người dùng thay đổi đơn của khách hàng khác | Ràng buộc `customer_id` đáng tin cậy trong query và command; kiểm tra quyền ở application boundary |
| Hai người cùng sửa một đơn | Version hoặc điều kiện trạng thái trong `UPDATE`; xem số hàng ảnh hưởng và trả xung đột thích hợp |
| Ghi nhiều bảng, lỗi ở bước sau | Một transaction cho toàn bộ thay đổi bắt buộc; rollback khi một bước thất bại |
| Giao dịch bị deadlock/serialization failure | Phân loại theo DB, retry **toàn transaction** khi phù hợp, với giới hạn và side effect an toàn |
| Mất kết nối lúc commit | Kết quả commit có thể chưa rõ; đối soát qua khóa yêu cầu/idempotency trước khi tạo thay đổi lần nữa |
| Phát sự kiện ra broker | Transactional outbox; worker gửi ngoài transaction nghiệp vụ, consumer deduplicate |
| Query từ replica trả dữ liệu cũ | Áp dụng read-your-writes hoặc chấp nhận eventual consistency theo từng use case |

Các SQL ở ví dụ dùng PostgreSQL để minh họa. MySQL/InnoDB, SQL Server, Oracle và SQLite có khác biệt về kiểu dữ liệu, SQL syntax, transaction behavior, isolation và khả năng index-only/covering; không tự áp dụng nguyên xi khi thay DB. Dù dùng ORM, nguyên tắc quan trọng vẫn là kiểm tra xem mã tạo **bao nhiêu câu SQL**, transaction bắt đầu/kết thúc ở đâu và có phát sinh flush/lock ngầm hay không.

## 9. Đo hiệu quả của việc tách đọc/ghi

Thay đổi kiến trúc nên giải quyết một vấn đề có thể quan sát. Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| p95/p99 của API danh sách | Đường đọc đã nhanh hơn và ổn định hơn chưa |
| Số hàng quét, thời gian SQL, buffer/I/O | Projection/index có thực sự giúp query hay chỉ tăng độ rộng dữ liệu |
| Thời lượng transaction ghi, lock wait/deadlock | Command boundary có giữ transaction ngắn và tránh tranh chấp không |
| Tỷ lệ optimistic conflict | Người dùng hay job có thường gặp dữ liệu thay đổi giữa đọc và ghi không |
| Độ trễ replica/projection | Read model chậm hơn nguồn dữ liệu bao nhiêu, có vi phạm yêu cầu freshness không |
| Lag của outbox, số sự kiện lặp, lỗi consumer | Tích hợp phía sau command có xử lý đầy đủ trường hợp gửi trùng/chậm không |
| Số đường cập nhật bỏ qua quy tắc | Có writer nào cập nhật trạng thái mà không đi qua command boundary đã thống nhất không |

Nếu mục tiêu ban đầu chỉ là giảm truy vấn `SELECT *` và tránh N+1, việc tách DTO/query có thể đã đủ. Nếu vấn đề nằm ở deadlock, điều cần sửa có thể là khóa và transaction phía command. Chỉ đầu tư thêm projection, replica hoặc broker khi kết quả đo và yêu cầu nhất quán cho thấy lợi ích tương xứng với độ phức tạp.

## 10. Bài tập thực hành

### Bài tập 1: phân loại đọc và ghi

Phân loại các thao tác: (a) xem danh sách 20 đơn gần nhất, (b) xác nhận thanh toán, (c) tính tổng doanh thu tháng, (d) đánh dấu một tin nhắn là đã đọc, (e) hủy đơn.

**Gợi ý đáp án:** (a) và (c) là query; (b), (d) và (e) là command nếu chúng thay đổi trạng thái nghiệp vụ. Trường hợp (d) cần làm rõ yêu cầu: nếu chỉ ghi log lượt xem phục vụ vận hành thì đó là một loại ghi telemetry riêng; nếu thay đổi trạng thái “đã đọc” mà người dùng thấy thì nên là command rõ ràng.

### Bài tập 2: tìm lỗi race condition

```java
Order order = orderRepository.find(orderId);
if (order.status().equals("PENDING")) {
    orderRepository.updateStatus(orderId, "CANCELLED");
}
```

**Câu hỏi:** điều gì có thể xảy ra nếu có một request xác nhận đơn giữa hai lời gọi? **Cách sửa:** đặt điều kiện `status = 'PENDING'` và phiên bản kỳ vọng (nếu có) trong chính câu `UPDATE`; kiểm tra số hàng cập nhật. Có thể cần transaction cho những thay đổi liên quan, như ghi outbox.

### Bài tập 3: đọc ngay sau ghi

Sau khi command hủy đơn commit, màn hình tải lại danh sách từ replica và vẫn thấy `PENDING`. Có phải command thất bại không? **Đáp án:** chưa thể kết luận; replica/projection có thể đang trễ. Xác định yêu cầu freshness, kiểm tra trạng thái DB chính, rồi chọn cách cung cấp read-your-writes hoặc hiển thị trạng thái đang đồng bộ.

### Bài tập 4: lựa chọn kiến trúc

Một ứng dụng có một bảng khách hàng, hai API đọc và một API đổi tên. Mỗi ngày chỉ có ít yêu cầu, không có vấn đề hiệu năng hay bất biến phức tạp. Có cần hai database, message bus và projection không? **Đáp án:** chưa có lý do. Nên bắt đầu với các phương thức đọc/ghi rõ ràng, DTO đầu ra và cập nhật có điều kiện nếu có rủi ro đồng thời; chỉ tăng độ phức tạp khi có nhu cầu đo được.

### Checklist thiết kế ranh giới ứng dụng

- Đã xác định rõ thao tác nào **chỉ đọc**, thao tác nào **thay đổi trạng thái** và command nào sở hữu bất biến nghiệp vụ chưa?
- Query có trả DTO/projection đủ dùng, lọc theo quyền truy cập, phân trang và đóng tài nguyên DB sớm không?
- Command có kiểm tra quyền, trạng thái và version **tại điểm ghi**; có transaction chung cho thay đổi bắt buộc không?
- Có đường cập nhật nào bỏ qua command service và làm sai quy tắc tăng version hoặc phát sự kiện không?
- Đường đọc có cần thấy thay đổi ngay sau commit, hay chấp nhận dữ liệu cũ trong một giới hạn đo được?
- Nếu dùng replica/outbox/projection, đã xử lý lag, sự kiện trùng, sai thứ tự, retry và khôi phục chưa?
- Đã đo query plan, latency, lock waits và chi phí đồng bộ trước khi mở rộng kiến trúc chưa?

**Kết luận:** Tách truy vấn phục vụ đọc khỏi thao tác thay đổi trạng thái là một cách làm rõ **ý định, trách nhiệm và ranh giới giao dịch**. Có thể bắt đầu chỉ bằng các API và repository khác nhau trên cùng database; phía đọc tập trung trả dữ liệu phù hợp, phía ghi chịu trách nhiệm bảo vệ bất biến và xử lý đồng thời. Chỉ dùng read model riêng hoặc CQRS phức tạp hơn khi cần và đã xác định rõ cách đáp ứng tính nhất quán.
