# Xử lý trùng yêu cầu bằng khóa lũy đẳng

Một người dùng bấm **Đặt hàng**, máy chủ đã lưu đơn và commit thành công nhưng kết nối mạng bị ngắt trước khi trình duyệt nhận phản hồi. Người dùng bấm lại hoặc ứng dụng tự thử lại vì thấy timeout. Nếu mỗi lần nhận HTTP request đều tạo một đơn hàng mới, hệ thống có thể tạo **hai đơn cho một ý định mua hàng**. Tương tự, việc gọi lại API thanh toán có thể gây thu tiền trùng nếu không có cơ chế chống xử lý lặp.

**Khóa lũy đẳng** (*idempotency key*) là một mã nhận diện **một ý định thực hiện thao tác** do bên gửi tạo hoặc được hệ thống cấp theo hợp đồng. Khi cùng một ý định được gửi lại với **cùng khóa và cùng dữ liệu**, dịch vụ nhận có thể trả lại kết quả đã ghi nhận hoặc thông báo rằng yêu cầu đang được xử lý, thay vì thực hiện tác động nghiệp vụ thêm một lần.

Bài học nằm trong chương **Lỗi và thử lại** thuộc module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là hiểu tại sao retry xảy ra, thiết kế ranh giới persistence cho Java, dùng ràng buộc database và transaction để chống trùng, nhận diện trạng thái commit không rõ, và phối hợp an toàn khi một nghiệp vụ liên quan nhiều dịch vụ.

## 1. Lũy đẳng là gì, và khóa lũy đẳng giải quyết vấn đề nào?

Một thao tác **lũy đẳng** (*idempotent*) có nghĩa thực hiện nó nhiều lần có **cùng tác động lên trạng thái** như thực hiện một lần, trong phạm vi ngữ nghĩa đã xác định. Ví dụ đặt trạng thái đơn hàng thành `CANCELLED` có thể là phép lũy đẳng nếu gọi lặp lại không gây thêm tác động mới; còn “tạo một đơn hàng mới” thường không tự lũy đẳng.

Đối với thao tác tạo mới, client có thể gửi một mã như:

~~~http
POST /orders
Idempotency-Key: 7b6a9b9e-a182-4e1d-9958-a793ea2b16b4
Content-Type: application/json

{"productId":42,"quantity":2}
~~~

Nếu cùng client phải retry **cùng ý định đặt hàng**, client dùng lại **chính mã này** cùng dữ liệu tương đương về ngữ nghĩa. Nếu người dùng thực sự muốn tạo một đơn hàng khác, dù chọn cùng sản phẩm và số lượng, họ phải dùng **khóa mới**.

Khóa lũy đẳng không phải một mã bất kỳ đổi sau mỗi lần gửi request. Nó là mã ổn định trong suốt **vòng đời retry của một thao tác**.

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Request ID / trace ID** | Truy vết một lần gọi qua hệ thống | Mỗi lần gửi lại có thể có một trace ID khác |
| **Idempotency key** | Liên kết các lần gửi lại của cùng ý định nghiệp vụ | Một khóa được giữ nguyên giữa các lần retry |
| **Business ID** | Định danh thực thể nghiệp vụ đã tạo | `order_id = 12345` |
| **Unique business constraint** | Chặn các tổ hợp dữ liệu trái quy tắc nghiệp vụ | Một mã hóa đơn không được xuất hiện hai lần |
| **Deduplication event ID** | Chặn xử lý trùng một sự kiện bất đồng bộ | Consumer ghi nhận `event_id` đã xử lý |

Các loại mã này có thể liên quan nhưng **không mặc nhiên thay thế nhau**. Một idempotency key có thể được ánh xạ tới một `order_id` và vẫn có trace ID khác ở mỗi lần retry.

## 2. Vì sao retry có thể gây trùng dù server không hề lỗi nghiệp vụ?

Một phản hồi thất bại **không chứng minh** thao tác ghi ở server thất bại. Mạng có thể mất phản hồi ở nhiều điểm:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Java API
    participant DB as Database
    C->>S: POST /orders, key = K
    S->>DB: INSERT order + record key K
    DB-->>S: COMMIT thành công
    S--xC: Mất phản hồi HTTP 201
    Note over C: Timeout; chưa biết server đã ghi hay chưa
    C->>S: Retry POST /orders, vẫn key K
    S->>DB: Tra cứu kết quả đã commit theo K
    DB-->>S: Order 12345
    S-->>C: Trả lại kết quả của order 12345
~~~

Không có khóa lũy đẳng, lần retry ở sơ đồ có thể tạo order thứ hai. Có khóa được lưu **bền vững**, server có thể nhận diện hai lần gọi là cùng một ý định.

Những nguồn tạo request trùng thường gặp:

- Client chủ động retry sau timeout, lỗi kết nối hoặc HTTP 5xx.
- Người dùng bấm nút nhiều lần, tải lại trang hoặc mạng di động tự gửi lại.
- Load balancer, gateway, job scheduler hoặc message consumer gửi lại khi chưa nhận xác nhận.
- Một tiến trình crash sau khi commit nhưng trước khi lưu trạng thái giao việc hoặc trả lời bên gọi.

Ẩn nút “Gửi” sau lần bấm đầu giúp trải nghiệm người dùng, nhưng **không thể** thay thế cơ chế chống trùng ở server. Máy khách, proxy và hệ thống mạng không cung cấp một lời hứa “chỉ giao yêu cầu đúng một lần” cho toàn bộ nghiệp vụ.

## 3. Phạm vi của khóa và dấu vân tay của yêu cầu

Một thiết kế cần trả lời bốn câu hỏi:

1. **Ai sở hữu khóa?** Client tạo UUID đủ khó đoán, hoặc server tạo mã thao tác và đưa cho client theo hợp đồng. Client phải lưu mã để dùng lại khi retry.
2. **Khóa duy nhất trong phạm vi nào?** Thường là tổ hợp tenant hoặc principal đã xác thực, **loại thao tác/endpoint**, và giá trị idempotency key.
3. **Cùng khóa nhưng payload thay đổi thì sao?** Server phải từ chối, không im lặng thực hiện lại hoặc trả kết quả của dữ liệu khác.
4. **Khóa còn hiệu lực bao lâu?** Định nghĩa retention window, thời gian hết hạn và hành vi khi retry sau khi bản ghi chống trùng bị xóa.

Ví dụ phạm vi khóa:

~~~text
scope = tenant:501:POST:/orders
key   = 7b6a9b9e-a182-4e1d-9958-a793ea2b16b4

Một tenant khác có thể dùng cùng chuỗi key.
Một thao tác khác có thể định nghĩa phạm vi riêng.
Trong cùng scope, cùng key phải luôn tham chiếu cùng một ý định.
~~~

**Scope phải lấy từ danh tính đã xác thực và định nghĩa thao tác phía server.** Không tin một trường `tenantId` tự khai trong payload để phân quyền truy xuất kết quả của tenant khác. Khóa lũy đẳng **không phải access token** và không thay thế xác thực, ủy quyền hay rate limit.

### Dấu vân tay yêu cầu (request fingerprint)

Ngoài khóa, nên lưu một giá trị đại diện cho nội dung có ý nghĩa nghiệp vụ, chẳng hạn hash SHA-256 của một biểu diễn **chuẩn hóa**:

~~~text
operation = POST /orders
productId = 42
quantity  = 2
currency  = VND
pricePlan = A
~~~

Nếu client dùng key cũ nhưng đổi `quantity` từ `2` thành `5`, server thấy fingerprint khác và trả lỗi có ý nghĩa, ví dụ `409 Conflict` hoặc `422 Unprocessable Content` theo hợp đồng API.

Không nên hash chuỗi JSON tùy ý nếu hệ thống coi hai JSON khác thứ tự trường, khác whitespace hoặc cách biểu diễn số là **cùng một yêu cầu**. Hãy chuẩn hóa và kiểm tra các trường nghiệp vụ quan trọng trước khi hash; dùng cách mã hóa không mơ hồ, có phiên bản schema nếu payload thay đổi theo thời gian. Đừng coi hash là công cụ bảo mật: quyền truy cập và xác thực vẫn phải được kiểm tra trước khi trả dữ liệu.

### Cùng payload nhưng khóa khác

Hai lần đặt hàng cùng `productId=42`, `quantity=2` có thể là **hai đơn hợp lệ** nếu người dùng thực sự mua hai lần. Vì vậy, chỉ dựa trên hash payload để chặn mọi request giống nhau có thể xóa mất nghiệp vụ hợp lệ. **Ý định** được biểu đạt bởi khóa cùng phạm vi, còn fingerprint dùng để bảo đảm khóa đó không bị tái sử dụng cho ý định khác.

## 4. Lưu trạng thái chống trùng bền vững trong database

Với hệ thống Java dùng PostgreSQL, có thể tạo một bảng lưu kết quả xử lý theo khóa. SQL dưới đây là **một thiết kế minh họa**, cần điều chỉnh cho lược đồ thật:

~~~sql
CREATE TABLE idempotency_requests (
    scope           VARCHAR(200) NOT NULL,
    idem_key        VARCHAR(128) NOT NULL,
    request_hash    CHAR(64) NOT NULL,
    status          VARCHAR(20) NOT NULL
                    CHECK (status IN ('PROCESSING', 'COMPLETED')),
    order_id        BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMPTZ,
    PRIMARY KEY (scope, idem_key),
    CHECK (
        status <> 'COMPLETED'
        OR (order_id IS NOT NULL AND completed_at IS NOT NULL)
    )
);

CREATE TABLE orders (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Trong một triển khai đầy đủ, có thể thêm khóa ngoại `idempotency_requests.order_id` tới `orders.id` và lưu response status/body hoặc một snapshot kết quả cần phát lại. Bảng ví dụ lưu `order_id` để dựng lại phản hồi ổn định `{"orderId":...}`.

**Ràng buộc duy nhất `PRIMARY KEY (scope, idem_key)` là hàng rào chống tranh chấp quan trọng nhất.** Một thao tác kiểu “`SELECT` xem khóa tồn tại chưa rồi `INSERT`” không có unique constraint vẫn gặp race condition khi hai transaction cùng thấy chưa có khóa.

| Cột | Vai trò |
| --- | --- |
| `scope + idem_key` | Định danh duy nhất cho một ý định trong phạm vi cho phép |
| `request_hash` | Phát hiện cùng khóa nhưng thay đổi payload |
| `status` | Cho biết thao tác đang xử lý hay đã hoàn thành theo thiết kế |
| `order_id` hoặc kết quả lưu | Liên kết kết quả để trả lại khi bị gửi lặp |
| `created_at`, `completed_at` | Quan sát vòng đời, retention và dọn dữ liệu |

Trong **mô hình transaction nguyên tử của bài này**, record `PROCESSING` sẽ được chèn và hoàn tất thành `COMPLETED` **trong cùng một transaction**, rồi mới commit. Các transaction khác không đọc thấy trạng thái `PROCESSING` chưa commit ở các mức cô lập thông dụng. Trạng thái này hữu ích để biểu diễn tiến trình nội bộ hoặc phát triển sang một thiết kế nhiều giai đoạn; nếu hệ thống chọn **commit PROCESSING trước** để giữ chỗ qua tác vụ dài, nó cần thêm lease, expiration và cơ chế phục hồi riêng (xem phần 8).

## 5. Ranh giới nguyên tử: ghi idempotency record cùng tác động nghiệp vụ

Với tác động chỉ nằm trong **cùng một database**, cách đơn giản và đáng tin cậy là:

1. Mở một transaction DB.
2. Thử chiếm khóa bằng **INSERT có unique constraint**.
3. Nếu chiếm khóa thành công, thực hiện tác động nghiệp vụ và ghi kết quả vào bản ghi idempotency.
4. Commit **cùng lúc** thay đổi nghiệp vụ và kết quả idempotency.
5. Nếu khóa đã tồn tại, kiểm tra fingerprint và lấy kết quả đã ghi mà không tạo tác động mới.
6. Rollback toàn bộ khi lỗi trước commit; request sau có thể thử lại với cùng khóa.

~~~mermaid
flowchart TD
    A[Nhận request với key và payload] --> B[Xác thực, kiểm tra key, fingerprint]
    B --> C[Bắt đầu transaction DB]
    C --> D[INSERT key với unique constraint]
    D --> E{Chiếm key thành công?}
    E -- Có --> F[Thực hiện thay đổi nghiệp vụ]
    F --> G[Ghi kết quả COMPLETED vào idempotency]
    G --> H[COMMIT cả hai]
    H --> I[Trả kết quả]
    E -- Không --> J[Đọc bản ghi đã tồn tại]
    J --> K{Fingerprint có khớp?}
    K -- Không --> L[ROLLBACK / trả lỗi key tái sử dụng sai]
    K -- Có --> M{Đã có kết quả?}
    M -- Có --> N[Hoàn tất transaction và trả lại kết quả]
    M -- Chưa --> O[Trả đang xử lý / thử lại sau]
~~~

Thiết kế tránh hai lỗ hổng nguy hiểm:

- **Chỉ ghi nghiệp vụ, chưa ghi idempotency record rồi crash:** request sau không biết tác động đã xảy ra.
- **Chỉ commit idempotency record “đã xong”, chưa commit nghiệp vụ:** request sau bị từ chối tạo lại trong khi kết quả nghiệp vụ chưa tồn tại.

Ghi cả hai trong cùng transaction làm một kết quả commit có thể được truy vấn như một đơn vị. Ràng buộc và dữ liệu vẫn phải nằm trong **cùng transaction manager và cùng phạm vi nguyên tử**; không thể tự suy rộng bảo đảm này sang hai database hoặc API ngoài.

## 6. Hai yêu cầu đồng thời cùng khóa

Một triển khai nguy hiểm:

~~~text
Request A: SELECT key K -> chưa có
Request B: SELECT key K -> chưa có
Request A: tạo order 101
Request B: tạo order 102
Request A: INSERT key K
Request B: INSERT key K (lỗi trùng, nhưng order 102 có thể đã commit riêng)
~~~

Không nên chỉ “kiểm tra rồi tạo” bên ngoài transaction. Unique constraint phải tham gia vào **điểm chiếm quyền thực thi tác động**, và tất cả bước ghi liên quan phải được commit/rollback chung.

Với PostgreSQL, câu lệnh chiếm khóa có thể dùng:

~~~sql
INSERT INTO idempotency_requests
    (scope, idem_key, request_hash, status)
VALUES
    (:scope, :idemKey, :requestHash, 'PROCESSING')
ON CONFLICT (scope, idem_key) DO NOTHING;
~~~

Nếu affected row = `1`, transaction đang nắm quyền xử lý ý định đó. Nếu affected row = `0`, đã có một record cạnh tranh và transaction cần đọc kết quả sau khi cơ chế kiểm tra unique hoàn tất. Trong PostgreSQL `READ COMMITTED`, một lần `INSERT ... ON CONFLICT DO NOTHING` có thể chờ transaction khác đang chèn cùng khóa; câu `SELECT` **tiếp theo** thường có snapshot mới để quan sát record đã commit. Ở isolation khác, có thể nhận serialization failure hoặc cần retry một transaction mới.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as PostgreSQL
    participant B as Request B
    A->>DB: BEGIN; INSERT key K
    DB-->>A: 1 dòng
    B->>DB: BEGIN; INSERT key K
    Note over B,DB: Chờ unique conflict chưa phân giải
    A->>DB: INSERT order + UPDATE key thành COMPLETED
    A->>DB: COMMIT
    DB-->>B: 0 dòng vì K đã tồn tại
    B->>DB: SELECT request_hash, order_id theo K
    DB-->>B: Kết quả của A
    B->>DB: COMMIT; trả lại cùng order ID
~~~

Nếu A rollback trước commit, B có thể trở thành request chiếm khóa hợp lệ và thực hiện thao tác **một lần**. Nếu B timeout vì chờ khóa, client nên retry có giới hạn với cùng key sau thời gian ngắn. Không được đổi key để “vượt” cạnh tranh.

## 7. Ví dụ Java/JDBC: tạo đơn hàng chống trùng

Ví dụ dưới đây giả định:

- Cơ sở dữ liệu là **PostgreSQL**, transaction dùng `READ COMMITTED`, và có schema `orders` / `idempotency_requests` như phần 4.
- `tenantId` được lấy từ thông tin xác thực của request; scope xác định cùng tenant và endpoint tạo đơn.
- Payload trong ví dụ chỉ có `productId` và `quantity` là số nguyên dương. Hash được tính trên dạng chuẩn hóa `productId:quantity`; với payload phức tạp cần canonicalization nghiêm ngặt hơn.
- Kết quả ổn định của API là `orderId`. Mô hình sản xuất có thể cần lưu đầy đủ HTTP status/body và nhiều ràng buộc nghiệp vụ khác.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HexFormat;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    // Java 17+: record và HexFormat.
    public record OrderResult(long orderId, boolean replayed) {}
    private record Saved(String requestHash, String status, Long orderId) {}

    public OrderResult createOrder(
            long tenantId, String key, long productId, int quantity)
            throws SQLException {
        if (tenantId <= 0 || productId <= 0 || quantity <= 0
                || key == null || !key.matches("[A-Za-z0-9_-]{16,128}")) {
            throw new IllegalArgumentException("Yêu cầu không hợp lệ");
        }

        String scope = "tenant:" + tenantId + ":POST:/orders";
        String requestHash = sha256(productId + ":" + quantity);

        try (Connection connection = dataSource.getConnection()) {
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
            connection.setAutoCommit(false);
            try {
                boolean claimed = claim(connection, scope, key, requestHash);
                if (claimed) {
                    long orderId = insertOrder(
                            connection, tenantId, productId, quantity);
                    complete(connection, scope, key, orderId);
                    connection.commit();
                    return new OrderResult(orderId, false);
                }

                // Cùng key: kiểm tra payload và dùng lại kết quả.
                Saved saved = load(connection, scope, key);
                if (saved == null) {
                    throw new SQLException(
                            "Chưa quan sát được kết quả; thử lại sau");
                }
                if (!requestHash.equals(saved.requestHash())) {
                    throw new IllegalStateException(
                            "Idempotency key đã dùng cho payload khác");
                }
                if (!"COMPLETED".equals(saved.status())
                        || saved.orderId() == null) {
                    throw new IllegalStateException(
                            "Yêu cầu trước đang xử lý; thử lại sau");
                }

                connection.commit();
                return new OrderResult(saved.orderId(), true);
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

    private boolean claim(Connection c, String scope, String key,
                          String hash) throws SQLException {
        String sql = "INSERT INTO idempotency_requests " +
                "(scope, idem_key, request_hash, status) " +
                "VALUES (?, ?, ?, 'PROCESSING') " +
                "ON CONFLICT (scope, idem_key) DO NOTHING";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, scope);
            ps.setString(2, key);
            ps.setString(3, hash);
            return ps.executeUpdate() == 1;
        }
    }

    private long insertOrder(Connection c, long tenantId,
                             long productId, int quantity) throws SQLException {
        String sql = "INSERT INTO orders (tenant_id, product_id, quantity) " +
                "VALUES (?, ?, ?) RETURNING id";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, tenantId);
            ps.setLong(2, productId);
            ps.setInt(3, quantity);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("INSERT không trả order ID");
                }
                return rs.getLong(1);
            }
        }
    }

    private void complete(Connection c, String scope, String key,
                          long orderId) throws SQLException {
        String sql = "UPDATE idempotency_requests " +
                "SET status = 'COMPLETED', order_id = ?, " +
                "completed_at = CURRENT_TIMESTAMP " +
                "WHERE scope = ? AND idem_key = ? AND status = 'PROCESSING'";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setString(2, scope);
            ps.setString(3, key);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Không ghi được kết quả idempotency");
            }
        }
    }

    private Saved load(Connection c, String scope, String key)
            throws SQLException {
        String sql = "SELECT request_hash, status, order_id " +
                "FROM idempotency_requests WHERE scope = ? AND idem_key = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, scope);
            ps.setString(2, key);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                Long orderId = (Long) rs.getObject("order_id");
                return new Saved(rs.getString("request_hash"),
                        rs.getString("status"), orderId);
            }
        }
    }

    private static String sha256(String canonical) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossibleOnNormalJdk) {
            throw new IllegalStateException(
                    "Không có SHA-256 trong JDK", impossibleOnNormalJdk);
        }
    }
}
~~~

**Diễn giải đúng về ví dụ:**

1. `claim()` dựa vào unique constraint; chỉ request chiếm được khóa mới tạo order.
2. `insertOrder()` và `complete()` chạy **trong chính transaction đang giữ claim**. Nếu một bước thất bại, rollback xóa cả record claim chưa commit lẫn order vừa tạo.
3. Request lặp sau khi transaction ban đầu commit sẽ gặp `claimed=false`, so sánh fingerprint rồi lấy lại `orderId`. Với response chỉ gồm ID ổn định, kết quả nghiệp vụ không bị nhân đôi.
4. Nếu cùng key nhưng payload đổi, ví dụ ném `IllegalStateException`; tầng API cần ánh xạ lỗi này thành HTTP 409/422 phù hợp, không tự động biến mọi `IllegalStateException` thành một mã duy nhất.
5. Nếu mất kết nối lúc `commit()`, JDBC có thể ném ngoại lệ mà không biết kết quả cuối. Client hoặc tầng điều phối **giữ nguyên key** và truy vấn/retry có kiểm soát, không tạo key mới.
6. `setTransactionIsolation` và `setAutoCommit(false)` được gọi trước thao tác ghi. Pool phải quản lý trạng thái connection khi trả về; phần minh họa này không thay thế chuẩn quản lý transaction của framework.

Đây là ví dụ thực hành về chống trùng **trong một database**. Nó chưa xử lý thanh toán, chính sách lưu response nhạy cảm, chống trùng sau thời hạn retention, retry backoff, SQL timeout hoặc các quy tắc tồn kho. Trong hệ thống sản xuất nên bổ sung các ràng buộc nghiệp vụ, quan sát lỗi, kiểm thử cạnh tranh và mô hình trả lỗi cụ thể.

## 8. Trạng thái PROCESSING, COMPLETED và yêu cầu đang chạy

Có hai kiểu thiết kế cần phân biệt:

| Mô hình | Khi nào record PROCESSING được commit? | Cơ chế xử lý request trùng |
| --- | --- | --- |
| **Một transaction nguyên tử** như ví dụ | Không commit riêng PROCESSING; record được commit ở trạng thái COMPLETED cùng nghiệp vụ | Unique constraint làm request thứ hai chờ/được từ chối theo DB; sau commit thì đọc kết quả |
| **Reservation/lease qua nhiều transaction** | Commit PROCESSING **trước** khi làm việc dài hoặc gọi hệ thống khác | Request trùng thấy đang xử lý và phải chờ, poll hoặc nhận phản hồi retry; cần lease, owner token và phục hồi |

Thiết kế thứ hai có ích cho công việc kéo dài nhiều giây/phút, nhưng phức tạp hơn:

- Lưu `owner` hoặc fencing token, `lease_expires_at` và thời điểm cập nhật trạng thái.
- Phân biệt worker còn sống với worker đã crash; sau timeout phải có quy trình **tiếp quản an toàn**.
- Không chỉ thấy lease hết hạn rồi chạy lại tác động bên ngoài: worker cũ có thể vẫn đang thực hiện, hoặc tác động đã thành công nhưng phản hồi bị mất.
- Mọi thay đổi trạng thái phải có điều kiện phiên bản/owner để worker cũ không ghi đè kết quả của worker mới.
- Nếu chạy song song trên nhiều máy, cần dùng cơ chế đồng bộ bền vững và kiểm thử race condition, không dựa vào mutex trong bộ nhớ một JVM.

Với trường hợp nhiều hệ thống tham gia, tiến trình thường cần mô hình trạng thái như `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`; idempotency key là một thành phần của quy trình, **không thay thế hệ thống điều phối hoặc bù trừ**.

### Trả gì cho request trùng khi yêu cầu trước chưa xong?

Đây là lựa chọn hợp đồng API, không có một quy tắc duy nhất:

- **Chờ** kết quả trong một khoảng ngắn rồi replay nếu hoàn thành.
- Trả `202 Accepted` với mã công việc để client poll, nếu thao tác thực sự được đưa vào hàng đợi.
- Trả `409 Conflict` hoặc một response thể hiện “in progress” và hướng dẫn retry có giới hạn, có thể kèm `Retry-After` khi phù hợp.
- Nếu hệ thống quá tải, trả lỗi tạm thời có backoff, nhưng **không cấp khóa mới** để vượt qua giới hạn.

Khi gặp lock timeout trong database, đừng suy ngay thao tác ban đầu thất bại. Cần phân biệt “đang tranh chấp” với “đã hoàn thành”, và cho phép client thử lại cùng key.

## 9. Nên lưu và phát lại phản hồi như thế nào?

Một API có thể trả `201 Created` khi tạo đơn. Nếu retry trùng khóa, response nên nhất quán về **kết quả nghiệp vụ**: cùng order ID, cùng trạng thái xử lý đã cam kết và không tạo thêm đơn. Hai chiến lược phổ biến:

1. **Lưu snapshot response:** status code, body đã phát, một số header cần thiết; replay lại dữ liệu đã lưu. Cẩn trọng với nội dung nhạy cảm, kích thước response và thời hạn retention.
2. **Lưu tham chiếu tới thực thể:** như `order_id`; dựng lại một response xác định. Cần hiểu trạng thái thực thể có thể thay đổi sau khi tạo, nên phản hồi dựng lại có thể khác snapshot ban đầu nếu chứa trường động.

Ví dụ một hợp đồng HTTP:

~~~http
POST /orders
Idempotency-Key: 7b6a9b9e-a182-4e1d-9958-a793ea2b16b4
Content-Type: application/json

{"productId":42,"quantity":2}

HTTP/1.1 201 Created
Content-Type: application/json
Location: /orders/12345

{"orderId":12345}
~~~

Nếu request cùng key/payload được gửi lại, server có thể trả lại `201 Created` và cùng `orderId` theo hợp đồng. Một số API dùng `200 OK` cho replay hoặc thêm header riêng báo “replayed”; client **không nên tự suy trạng thái dựa trên mã phản hồi** nếu hợp đồng API chưa mô tả rõ.

### Có lưu cả response lỗi không?

Không có chính sách chung cho mọi lỗi:

- **Lỗi kiểm tra input trước khi bắt đầu nghiệp vụ:** thường có thể trả ngay mà không giữ khóa; có thể cho phép gửi lại dữ liệu hợp lệ theo hợp đồng, hoặc yêu cầu key mới khi payload thay đổi.
- **Lỗi nghiệp vụ xác định đã được ghi nhận:** có thể lưu kết quả thất bại nếu muốn replay ổn định, nhất là khi thất bại là trạng thái nghiệp vụ cuối.
- **Lỗi tạm thời trước commit và rollback thành công:** thường không nên ghi “COMPLETED” giả; request sau có thể thử lại.
- **Lỗi mạng lúc commit hoặc tác động ngoài DB chưa rõ:** phải tra cứu trạng thái, tránh ghi thất bại chắc chắn khi chưa có bằng chứng.

Hãy tài liệu hóa loại lỗi nào được cache/replay. Việc “lưu mọi 5xx rồi replay mãi” có thể khóa vĩnh viễn một tác vụ dù sự cố hạ tầng đã được khắc phục.

## 10. Khóa lũy đẳng không tạo ra exactly-once cho hệ thống phân tán

Nếu một transaction tạo đơn hàng trong database rồi gọi API thanh toán bên ngoài, hai hệ thống **không tự tham gia cùng một giao dịch**:

~~~text
BEGIN DB TRANSACTION
  INSERT order
  Gọi paymentProvider.charge(...)
  INSERT idempotency COMPLETED
COMMIT
~~~

Nếu payment provider đã thu tiền nhưng database rollback, record idempotency và order có thể mất, trong khi tiền đã bị thu. Nếu ứng dụng retry mà chỉ chống trùng ở database, lần gọi thanh toán sau vẫn có thể thu tiền lần nữa.

Hướng thiết kế đáng tin cậy hơn:

1. **Transaction DB ngắn:** tạo order ở trạng thái `PENDING`, lưu idempotency record và một sự kiện **transactional outbox** để yêu cầu thanh toán; commit cùng nhau.
2. **Worker xử lý outbox:** gửi yêu cầu đến payment provider sau commit, dùng một **khóa ổn định** ở provider nếu provider hỗ trợ idempotency.
3. **Ghi nhận kết quả:** cập nhật trạng thái payment/order bằng transaction DB khác; lưu provider transaction ID và trạng thái để đối soát.
4. **Xử lý phản hồi mất hoặc callback trùng:** tra cứu provider theo mã giao dịch hoặc khóa của provider và deduplicate webhook/event ID ở consumer.
5. **Tác vụ bù:** nếu nhiều bước thuộc các hệ thống khác nhau thất bại một phần, áp dụng chiến lược bù/đối soát phù hợp nghiệp vụ; không coi rollback DB là cách hủy tác động của provider.

~~~mermaid
flowchart TD
    A[Client gửi key K] --> B[DB transaction: order PENDING + idempotency + outbox]
    B --> C[Commit]
    C --> D[Worker đọc outbox]
    D --> E[Payment API với provider key ổn định]
    E --> F{Provider xác nhận kết quả?}
    F -- Có --> G[DB transaction cập nhật payment + order]
    F -- Chưa rõ --> H[Tra cứu và đối soát theo provider ID/key]
    H --> G
    G --> I[Consumer xử lý sự kiện idempotent]
~~~

**Exactly-once end-to-end** là bảo đảm khó hơn nhiều so với “mỗi key tạo tối đa một order trong một database”. Dedupe, outbox, idempotency ở bên nhận và reconciliation phối hợp để giảm tác động lặp; mỗi mắt xích vẫn phải được phân tích theo hợp đồng của hệ thống thực tế.

## 11. Retry đúng cách: giữ khóa, giới hạn và phân loại lỗi

Một client hoặc worker muốn retry cần **quy tắc rõ ràng**:

| Tình huống | Cách xử lý gợi ý |
| --- | --- |
| Timeout hoặc mất phản hồi sau khi gửi request | Giữ **cùng key/payload**, retry hoặc tra cứu kết quả |
| Lỗi HTTP 5xx có thể tạm thời | Retry hữu hạn với backoff/jitter nếu hợp đồng API cho phép |
| Xung đột key và payload khác nhau | Ngừng retry; đây là lỗi dùng khóa sai |
| Request đang xử lý | Tôn trọng `Retry-After`/trạng thái công việc, không gửi dồn dập |
| Payload không hợp lệ hoặc không được phép | Sửa lỗi đầu vào/quyền; không retry mù |
| DB báo deadlock/serialization failure và transaction đã rollback | Có thể retry **cả transaction mới**, giữ nguyên ý định và key |
| Mất kết nối đúng lúc commit | Kết quả **chưa rõ**; tra cứu/retry bằng cùng key, không suy chắc đã rollback |

Ví dụ lịch backoff mang tính minh họa cho các lần retry có điều kiện:

~~~text
Lần 1: ngay khi người dùng gửi
Lần 2: sau 200-400 ms
Lần 3: sau 400-800 ms
Lần 4: sau 800-1600 ms
Sau đó: dừng và cho phép tra cứu trạng thái
~~~

Giới hạn số lần, ngân sách thời gian, jitter và loại lỗi phải phù hợp với SLO/tải của hệ thống. Đừng retry vô hạn; nhiều client cùng retry quá nhanh có thể biến sự cố ngắn thành quá tải kéo dài.

**Không tạo idempotency key bên trong vòng retry.** Tạo một lần cho ý định ban đầu, lưu và truyền lại ở mọi lần thử. Nếu ứng dụng khởi động lại mà mất key, cơ chế chống trùng có thể không nhận diện lần retry với request cũ.

## 12. Thời gian lưu khóa, dọn dữ liệu và giới hạn thiết kế

Bản ghi chống trùng không nhất thiết giữ vĩnh viễn, nhưng **xóa quá sớm có thể tạo lại tác động nghiệp vụ**.

Giả sử server giữ key trong 24 giờ:

~~~text
T0: Client gửi K, order 12345 được tạo.
T0 + 2 giờ: Client retry K -> nhận order 12345.
T0 + 25 giờ: Record K đã bị xóa.
              Retry K có thể bị hiểu là ý định mới -> tạo order khác.
~~~

**24 giờ chỉ là một ví dụ về chính sách**, không phải ngưỡng chung. Retention cần dựa trên thời gian retry tối đa của client, scheduler, hệ thống queue, thời gian mất mạng, yêu cầu đối soát, pháp lý và tác động nếu xử lý trùng.

Các lưu ý quan trọng:

- Chỉ dọn những record đã ở trạng thái cuối và đã qua thời hạn bảo vệ; **không xóa vô điều kiện** record đang xử lý.
- Việc dọn record khi request cũ vẫn có thể retry phải có hợp đồng rõ ràng: trả “key expired”, buộc tra cứu theo business ID, hoặc có **unique business key** dài hạn để ngăn tác động lặp.
- Nếu cần chặn trùng vĩnh viễn một loại nghiệp vụ, retention của idempotency cache không thay thế ràng buộc nghiệp vụ tồn tại lâu dài.
- Tránh áp dụng một TTL ngắn cho thanh toán quan trọng khi hệ thống có thể nhận đối soát/webhook muộn.
- Cẩn trọng với tác vụ cleanup chạy đồng thời với request mới; cần transaction và điều kiện xóa phù hợp.
- Lưu response chứa thông tin nhạy cảm phải được giới hạn truy cập, mã hóa và tuân theo chính sách lưu trữ dữ liệu.

Khóa nên có kích thước, định dạng và độ dài giới hạn để tránh dùng tài nguyên vô hạn. Chọn giá trị đủ phân tán và khó đoán (chẳng hạn UUID ngẫu nhiên do client tạo) giúp giảm khả năng trùng ngoài ý muốn; việc biết khóa **không được** cấp quyền xem kết quả thuộc tenant khác.

## 13. Kiểm thử chống trùng và tranh chấp đồng thời

Kiểm thử với một request duy nhất rồi kiểm tra bảng idempotency tồn tại là chưa đủ. Cần kiểm tra trường hợp **hai transaction thật**, đường lỗi, phản hồi mất và tác động ngoài database.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Gửi key `K` một lần | Tạo đúng một order, lưu kết quả cùng key |
| Gửi lại `K` với cùng payload sau commit | Không tạo order thứ hai; trả cùng order ID |
| Gửi lại `K` với payload khác | Từ chối rõ ràng, không sửa order cũ |
| Hai request cùng `K` chạy đồng thời | Chỉ một tác động nghiệp vụ được commit; request kia chờ, replay hoặc nhận trạng thái đang xử lý |
| Request thứ nhất rollback trước commit | Không để lại record COMPLETED giả; request sau có thể thực thi |
| Commit thành công nhưng mất HTTP response | Retry `K` tìm lại kết quả đã commit |
| Lỗi kết nối tại commit, chưa rõ kết quả | Không kết luận thất bại; tra cứu/retry cùng key theo cơ chế đã thiết kế |
| Hai tenant dùng cùng chuỗi `K` | Không truy cập nhầm hoặc replay chéo dữ liệu |
| Hết hạn record theo retention | Hành vi sau TTL đúng hợp đồng và có hàng rào nghiệp vụ khi cần |
| Duplicate webhook / outbox message | Consumer không thực thi tác động nghiệp vụ lặp |

### Thử nghiệm hai kết nối JDBC độc lập

1. Khởi tạo hai kết nối hoặc hai transaction trên database test hỗ trợ unique constraint.
2. Cho cả hai cùng cố `INSERT` một cặp `(scope, idem_key)`. Có thể dùng `CountDownLatch` để đồng bộ điểm bắt đầu.
3. Giao dịch A tạo order và commit sau khi ghi kết quả idempotency. Quan sát B chờ theo engine hoặc nhận kết quả xử lý cạnh tranh, rồi kiểm tra B không tạo order khác.
4. Lặp lại khi A rollback: B có thể trở thành owner, và cuối cùng vẫn chỉ một order được commit.
5. So sánh số order, bản ghi idempotency, kết quả HTTP và metric thay vì chỉ kiểm tra một exception.

Nếu framework tự bọc test trong một transaction lớn và rollback cuối test, hai request có thể không có transaction độc lập đúng nghĩa. Nên dùng integration test trên cơ sở dữ liệu cùng loại với môi trường chạy hoặc Testcontainers, có chủ đích về isolation và các lần commit thật.

### Mô phỏng phản hồi thất lạc

Sau khi transaction đầu đã commit, giả lập đường HTTP không trả kết quả cho client. Gửi lại cùng key/payload, xác minh rằng database vẫn chỉ có **một** order và response liên kết tới đúng order ban đầu. Đây là một trong những bài kiểm thử quan trọng nhất vì nó chứng minh giá trị của idempotency trước trạng thái kết quả **không chắc chắn ở client**.

## 14. Quan sát, bảo mật và vận hành

Các số liệu nên thu thập theo loại nghiệp vụ, tenant tier hoặc endpoint, **không dùng raw key làm nhãn metric** vì số lượng khóa rất lớn:

| Chỉ số | Mục đích |
| --- | --- |
| Số request mới chiếm được khóa | Lưu lượng ý định nghiệp vụ mới |
| Số replay trùng key và cùng payload | Mức độ retry hoặc gửi lặp |
| Số reuse key với payload khác | Phát hiện lỗi client hoặc hành vi bất thường |
| Số request đang xử lý và tuổi PROCESSING | Phát hiện worker treo trong thiết kế nhiều giai đoạn |
| Thời gian chờ unique lock / xung đột DB | Đo cạnh tranh khi hai yêu cầu cùng key |
| Số commit result unknown và lần đối soát | Hiểu lỗi mạng/hạ tầng quanh commit |
| Số duplicate event/webhook đã bị chặn | Đánh giá chống trùng ở downstream |
| Số khóa hết hạn và tỷ lệ retry sau TTL | Kiểm tra retention có phù hợp không |

Log chỉ nên chứa định danh cần thiết như request/trace ID, scope đã hạn chế quyền, hash/rút gọn key, loại thao tác và mã trạng thái; tránh lưu raw header nhạy cảm, token và response body có dữ liệu cá nhân. Ràng buộc xác thực và phân quyền phải được áp dụng **trước** khi tiết lộ kết quả của một key.

Đối với một cụm nhiều instance Java, không thể chỉ dùng `ConcurrentHashMap` hoặc `synchronized` trong một JVM: request gửi lại có thể đi đến instance khác hoặc xảy ra sau khi máy chủ khởi động lại. Lưu dữ liệu chống trùng ở hệ lưu trữ chung có tính bền vững và ràng buộc nguyên tử phù hợp.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo key mới ở mỗi lần retry | Mỗi lần gửi lại bị xem là nghiệp vụ mới | Tạo key **một lần cho mỗi ý định**, lưu và tái sử dụng |
| Chỉ kiểm tra `SELECT` xem key đã có chưa | Hai request đồng thời đều thấy “chưa có” | Dùng unique constraint và transaction để chiếm key |
| Lưu key và order ở hai transaction không phối hợp | Crash tạo ra trạng thái chỉ có một trong hai | Commit nghiệp vụ và record idempotency **cùng nhau** khi cùng DB |
| Cùng key nhưng payload thay đổi vẫn được thực thi | Có thể xử lý nghiệp vụ khác dưới cùng khóa | So khớp fingerprint và từ chối khác biệt |
| Chỉ dựa vào hash payload, không có key | Hai ý định hợp lệ cùng dữ liệu bị chặn | Tách định danh ý định khỏi so sánh nội dung |
| Coi timeout là rollback chắc chắn | Retry có thể tạo tác động lặp | Giữ key và tra cứu khi kết quả commit chưa rõ |
| Cache chống trùng chỉ trong bộ nhớ JVM | Mất sau restart hoặc không chia sẻ giữa instance | Lưu bền vững với ràng buộc/đồng bộ DB |
| Để record PROCESSING tồn tại vô hạn | Request sau bị kẹt mãi | Lease, owner/fencing token, timeout và phục hồi |
| Xóa key quá sớm | Retry muộn tạo nghiệp vụ lần hai | Retention dựa vào thực tế, kết hợp ràng buộc nghiệp vụ |
| Nghĩ idempotency trong DB cũng bảo vệ thanh toán ngoài DB | Vẫn có thể thu tiền trùng sau rollback | Outbox, provider key, webhook dedupe và đối soát |
| Retry liên tục không backoff | Tăng tải và kéo dài sự cố | Retry hữu hạn với jitter, phân loại lỗi |
| Trả kết quả chỉ dựa trên key không kiểm tra quyền | Rò rỉ dữ liệu liên tenant | Scope theo danh tính đã xác thực, phân quyền mọi lần replay |

## 16. Bài tập vận dụng: tạo phiếu thanh toán

Giả sử dịch vụ có endpoint `POST /invoices` và người dùng gửi:

~~~http
POST /invoices
Idempotency-Key: c7c611c9-27ee-49a5-8f1a-05f8d3c32955
Content-Type: application/json

{"customerId":18,"amount":"150000.00","currency":"VND"}
~~~

Máy chủ commit invoice `id=9001` nhưng phản hồi HTTP mất. Sau đó:

1. Client retry cùng key, cùng dữ liệu. API nên trả kết quả gì?
2. Client dùng cùng key nhưng sửa `amount` thành `250000.00`. API nên làm gì?
3. Hai request cùng key đến đồng thời trước khi bảng idempotency có record. Cơ chế nào quyết định bên thực hiện?
4. Sau khi lưu invoice, hệ thống còn gọi API thanh toán ngoài database. Vì sao transaction chống trùng nội bộ vẫn chưa đủ?
5. Nếu record idempotency đã bị xóa sau TTL và request cũ đến lại, điều gì có thể xảy ra?

**Gợi ý lời giải:** Request lặp phải nhận lại invoice `9001` mà không tạo thêm invoice. Payload mới dùng key cũ bị từ chối theo hợp đồng API. Unique constraint `(scope, key)` cùng transaction cho một yêu cầu chiếm quyền thực thi; phía còn lại chờ hoặc lấy kết quả. Thanh toán ngoài DB cần idempotency của provider, outbox/trạng thái và đối soát. Khi key hết hạn, request cũ có thể được xem là thao tác mới; cần chọn retention đủ dài hoặc bổ sung unique business ID để ngăn trùng theo quy tắc nghiệp vụ.

## 17. Ghi nhớ khi thiết kế persistence cho Java

- **Một ý định nghiệp vụ tương ứng một idempotency key**, và key phải được giữ nguyên qua mọi lần retry của ý định đó.
- **Scope key theo danh tính đã xác thực và loại thao tác**; kiểm tra fingerprint để từ chối cùng key nhưng payload khác.
- **Dùng unique constraint và transaction bền vững**. Một lần `SELECT` kiểm tra trước rồi mới ghi không đủ để chống đua đồng thời.
- **Ghi nghiệp vụ và kết quả chống trùng trong cùng transaction khi cùng một DB**; nếu rollback, cả hai phải rollback.
- **Commit thành công nhưng response mất vẫn là thành công ở database**. Client retry bằng cùng key có thể lấy lại kết quả; lỗi mạng tại commit phải được xem là trạng thái chưa rõ cho đến khi đối soát.
- **Phân biệt dữ liệu nghiệp vụ nội bộ với tác động ngoài DB**. Outbox, idempotency của provider và deduplication phía consumer bổ sung bảo vệ cho quy trình nhiều hệ thống.
- **Xác định retention, retry/backoff, lỗi có thể lưu lại, và hành vi in progress** trong hợp đồng API.
- **Kiểm thử race, rollback, replay và timeout** trên database thực, sử dụng nhiều transaction độc lập và quan sát trạng thái đã commit.

Khóa lũy đẳng giúp một hệ thống chịu được việc thông điệp hoặc HTTP request được gửi lại. Nó không khiến mạng trở nên đáng tin tuyệt đối và cũng không làm toàn bộ hệ thống phân tán có giao dịch nguyên tử. Thiết kế hiệu quả là xác định **một ý định**, ghi nhận nó **một cách nguyên tử**, và cho phép bên gửi **thử lại an toàn** mà không vô tình thực hiện thêm tác động nghiệp vụ.
