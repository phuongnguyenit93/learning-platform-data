# Tránh giữ kết nối trong khi chờ tác vụ ngoài không liên quan

Một kết nối cơ sở dữ liệu là tài nguyên có giới hạn. Trong ứng dụng Java, việc lấy `Connection` từ pool rồi giữ nó trong lúc gọi HTTP, chờ dịch vụ thanh toán, gửi email hoặc xử lý tác vụ dài có thể làm nghẽn toàn bộ hệ thống ngay cả khi câu SQL chạy rất nhanh. Kết nối vẫn được tính là **đang được mượn** từ pool, còn nếu giao dịch đang mở, cơ sở dữ liệu có thể tiếp tục giữ khóa, snapshot và những tài nguyên khác.

Nguyên tắc thực hành là **chỉ mượn kết nối cho phần công việc thực sự cần cơ sở dữ liệu, rồi trả lại sớm nhất khi có thể**. Các thao tác bên ngoài nên được thực hiện ở ngoài phạm vi sở hữu kết nối và giao dịch khi nghiệp vụ cho phép. Tuy nhiên, tách một quy trình thành nhiều lần truy cập DB cũng tạo khoảng thời gian mà dữ liệu có thể thay đổi; cần kết hợp kiểm tra phiên bản, thao tác SQL có điều kiện hoặc cơ chế phối hợp đáng tin cậy.

Trong chương **Kết nối và tài nguyên** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này nối kiến thức về ranh giới persistence Java, giao dịch, đồng thời, xử lý lỗi kết nối và hiệu năng để trả lời ba câu hỏi: *khi nào thực sự cần giữ kết nối, làm sao trả nó đúng lúc, và làm sao duy trì tính đúng đắn khi có tác vụ bên ngoài?*

## 1. Một kết nối đang được mượn có chi phí gì?

Phần lớn ứng dụng server Java sử dụng connection pool. Khi gọi `dataSource.getConnection()`, ứng dụng thường **mượn** một kết nối logic từ pool; khi gọi `close()` trên đối tượng này, nó thường được **trả về pool** theo cơ chế của nhà cung cấp, thay vì đóng ngay một socket vật lý. Điều quan trọng là thời gian kết nối ở trạng thái *borrowed/active*.

Giả sử pool có 10 kết nối. Nếu 10 yêu cầu cùng lấy connection, thực hiện một câu `SELECT` rồi giữ connection thêm vài giây để chờ API vận chuyển, những yêu cầu thứ 11 trở đi có thể phải chờ kết nối rảnh dù DB hầu như không làm gì.

```text
Cách dễ gây nghẽn:
  request ── [mượn connection ─ SQL ─ chờ HTTP ─ xử lý khác ─ trả connection]
                              ^^^^^^^^^^^^
                              giữ tài nguyên DB dù không dùng DB

Cách tổ chức có ranh giới rõ:
  request ── [mượn ─ SQL ─ trả] ─ chờ HTTP ─ [mượn ─ SQL ─ trả]
                         ^                      ^
                  pool có thể phục vụ      kết nối chỉ được giữ
                  request khác            khi thật sự cần DB
```

Nếu connection đang có transaction mở, tác hại có thể lớn hơn sự cạn pool:

- **Khóa giữ lâu hơn:** hàng đang bị khóa có thể chặn cập nhật từ các giao dịch khác và tăng nguy cơ deadlock.
- **Snapshot tồn tại lâu:** với DB dùng MVCC, giao dịch kéo dài có thể ảnh hưởng đến cơ chế dọn phiên bản cũ; quy tắc chi tiết tùy hệ quản trị và mức cô lập.
- **Giữ tài nguyên session:** cursor, prepared statement, temporary state và bộ nhớ phía DB có thể còn gắn với phiên kết nối.
- **Độ trễ lan truyền:** người gọi chờ lấy connection; ứng dụng có thể tăng thread đang đợi, timeout hoặc retry, làm tải tăng thêm.
- **Khó quan sát nguyên nhân:** log SQL có thể cho thấy câu lệnh chỉ mất vài mili giây, trong khi thời gian *connection checkout* kéo dài nhiều giây.

Không phải mọi connection được giữ đều đang có transaction. Một connection ở chế độ `autoCommit=true` có thể không giữ khóa transaction sau mỗi câu SQL, nhưng nó vẫn chiếm một slot trong pool cho đến khi được trả. Cần phân biệt **thời gian mượn connection**, **thời gian transaction mở** và **thời gian câu SQL thực thi**.

## 2. Dấu hiệu của một ranh giới sai

Ví dụ dưới đây minh họa **mẫu nên tránh**. Dù việc kiểm tra địa chỉ bằng API ngoài mất nhiều thời gian, connection đã được mượn trước và tiếp tục tồn tại trong lúc chờ mạng:

```java
// Minh họa anti-pattern: giữ connection trong lúc chờ HTTP.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    Order order = loadOrder(connection, orderId);

    // Có thể chờ DNS, TLS, timeout, retry hoặc dịch vụ đối tác.
    AddressCheck check = addressClient.verify(order.address());

    updateAddressStatus(connection, orderId, check);
    connection.commit();
}
```

Tình huống còn bất lợi hơn nếu trước lời gọi mạng chương trình đã `SELECT ... FOR UPDATE` hoặc thực hiện `UPDATE`, vì khóa giao dịch có thể bị giữ suốt thời gian chờ. Nếu API ngoài không phản hồi, câu SQL của những giao dịch khác có thể bị chặn dù hệ thống DB vẫn khỏe.

Một mẫu tương tự dễ bị bỏ sót:

```java
@Transactional
public void placeOrder(Command command) {
    orderRepository.save(command.toOrder());
    paymentClient.charge(command.paymentDetails()); // I/O ngoài DB
    orderRepository.markPaid(command.orderId());
}
```

Với transaction manager thông dụng, giao dịch có thể được mở và connection được mượn trước hoặc tại lệnh DB đầu tiên. Sau `save`, transaction vẫn còn hiệu lực khi gọi cổng thanh toán. Bỏ `@Transactional` một cách máy móc cũng **không** giải quyết yêu cầu nhất quán giữa DB và khoản thanh toán đã thực hiện. Cần thiết kế quy trình nghiệp vụ rõ ràng: giữ transaction ngắn, xử lý side effect bằng idempotency, outbox hoặc một state machine phù hợp.

## 3. Tách tác vụ đọc bên ngoài khỏi hai đoạn truy cập DB

Một trường hợp dễ tách là lấy **báo giá tham khảo từ dịch vụ vận chuyển**. Quy trình có thể:

1. Mượn connection, đọc thông tin cần thiết và **phiên bản** của đơn, sau đó đóng các tài nguyên DB.
2. Gọi dịch vụ báo giá **ngoài** thời gian mượn connection.
3. Mượn connection mới, lưu báo giá **nếu đơn vẫn giữ phiên bản/trạng thái đã đọc**; trả connection ngay khi xong.

```text
DB:   [ SELECT order + version ]                      [ UPDATE ... WHERE version = ? ]
                 |                                                ^
                 v                                                |
Pool:         trả kết nối                                   mượn kết nối mới
                 |                                                ^
                 +-----> [ HTTP lấy báo giá vận chuyển ] ---------+
                                       |
                              Không chiếm slot DB
```

Ở giữa bước 1 và bước 3, người dùng có thể sửa địa chỉ hoặc khối lượng kiện hàng. Nếu cứ ghi báo giá cũ mà không kiểm tra, hệ thống lưu kết quả không còn tương ứng với đơn hiện tại. **Optimistic concurrency control** qua cột `version` giúp phát hiện tình huống ấy.

### Ví dụ Java/JDBC hoàn chỉnh

Giả sử bảng PostgreSQL đã có đơn ở trạng thái `DRAFT` và mỗi lần cập nhật địa chỉ/khối lượng hoặc trường liên quan đều tăng `version`:

```sql
CREATE TABLE shipping_orders (
    order_id     BIGINT PRIMARY KEY,
    postal_code  VARCHAR(20) NOT NULL,
    weight_grams INTEGER NOT NULL CHECK (weight_grams > 0),
    status       VARCHAR(20) NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0,
    quote_amount NUMERIC(18, 2)
);
```

Trong ví dụ sau, endpoint báo giá là dịch vụ bên ngoài **chỉ tính giá và trả chuỗi số tiền thập phân trong body**, không tạo đơn vận chuyển hay thu tiền. Tên endpoint và cách gửi/nhận dữ liệu chỉ mang tính minh họa; trong ứng dụng thực, phải tuân thủ hợp đồng API, xác thực và kiểm tra nội dung phản hồi của nhà cung cấp.

```java
import javax.sql.DataSource;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;

public final class ShippingQuoteService {
    public enum SaveOutcome { SAVED, STALE_ORDER }

    private record OrderSnapshot(long orderId, String postalCode,
                                 int weightGrams, long version) {}

    private final DataSource dataSource;
    private final HttpClient httpClient;
    private final URI quoteEndpoint;

    public ShippingQuoteService(DataSource dataSource, HttpClient httpClient,
                                URI quoteEndpoint) {
        this.dataSource = dataSource;
        this.httpClient = httpClient;
        this.quoteEndpoint = quoteEndpoint;
    }

    public SaveOutcome refreshQuote(long orderId)
            throws SQLException, IOException, InterruptedException {
        // Connection đầu tiên chỉ tồn tại trong lời gọi đọc.
        OrderSnapshot snapshot = loadSnapshot(orderId);

        // Không có JDBC Connection nào được giữ khi chờ HTTP.
        BigDecimal quote = fetchQuote(snapshot);

        // Connection thứ hai chỉ dùng cho lệnh cập nhật có điều kiện.
        return saveIfUnchanged(snapshot, quote)
                ? SaveOutcome.SAVED : SaveOutcome.STALE_ORDER;
    }

    private OrderSnapshot loadSnapshot(long orderId) throws SQLException {
        String sql = """
            SELECT postal_code, weight_grams, version
            FROM shipping_orders
            WHERE order_id = ? AND status = 'DRAFT'
            """;
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            try (ResultSet rows = ps.executeQuery()) {
                if (!rows.next()) {
                    throw new IllegalArgumentException(
                            "Không tìm thấy đơn DRAFT: " + orderId);
                }
                return new OrderSnapshot(
                        orderId,
                        rows.getString("postal_code"),
                        rows.getInt("weight_grams"),
                        rows.getLong("version"));
            }
        }
    }

    private BigDecimal fetchQuote(OrderSnapshot snapshot)
            throws IOException, InterruptedException {
        // Định dạng payload ví dụ được thỏa thuận với API giả định.
        String body = snapshot.postalCode() + "\n" + snapshot.weightGrams();
        HttpRequest request = HttpRequest.newBuilder(quoteEndpoint)
                .timeout(Duration.ofSeconds(3))
                .header("Content-Type", "text/plain; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        body, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
        if (response.statusCode() != 200) {
            throw new IOException(
                    "Dịch vụ báo giá trả HTTP " + response.statusCode());
        }

        try {
            BigDecimal amount = new BigDecimal(response.body().trim());
            if (amount.signum() < 0) {
                throw new NumberFormatException("Số tiền âm");
            }
            return amount;
        } catch (NumberFormatException invalidAmount) {
            throw new IOException("Phản hồi báo giá không hợp lệ", invalidAmount);
        }
    }

    private boolean saveIfUnchanged(OrderSnapshot snapshot, BigDecimal quote)
            throws SQLException {
        String sql = """
            UPDATE shipping_orders
            SET quote_amount = ?, version = version + 1
            WHERE order_id = ?
              AND status = 'DRAFT'
              AND version = ?
            """;
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setBigDecimal(1, quote);
            ps.setLong(2, snapshot.orderId());
            ps.setLong(3, snapshot.version());
            return ps.executeUpdate() == 1;
        }
    }
}
```

Ví dụ dùng connection ở chế độ auto-commit mặc định của pool cho mỗi câu SQL độc lập. Mỗi lệnh là một transaction nhỏ; câu `UPDATE ... WHERE version = ?` thực hiện phép kiểm tra và ghi trong **cùng một câu SQL nguyên tử**. Nếu không còn khớp phiên bản, số hàng cập nhật bằng 0 và service trả `STALE_ORDER`; ứng dụng có thể báo người dùng tính lại báo giá. Nó không âm thầm lưu báo giá dựa trên địa chỉ cũ.

**Điều kiện quan trọng:** mọi đường cập nhật trường ảnh hưởng đến báo giá phải tăng `version` hoặc có cơ chế nhận diện thay đổi tương đương. Nếu một luồng sửa `postal_code` nhưng quên tăng phiên bản, optimistic locking trong ví dụ không phát hiện được. Nếu thời hạn hiệu lực của báo giá có giới hạn, hệ thống còn cần lưu thời điểm hết hạn và kiểm tra lại khi chốt đơn.

Sự tách biệt trên phù hợp với dịch vụ báo giá **không tạo side effect**. Nếu lời gọi bên ngoài thực sự thu tiền, đặt chỗ hoặc gửi thông báo, chỉ tách connection chưa đủ để bảo đảm tính nhất quán giữa hai hệ thống.

## 4. Với tác vụ ngoài có side effect: dùng quy trình và outbox

Giả sử sau khi xác nhận đơn hàng, ứng dụng cần phát sự kiện `ORDER_CONFIRMED` sang broker. Không nên giữ transaction DB mở trong lúc chờ broker xác nhận; đồng thời không thể tự bảo đảm hai thao tác "commit DB" và "publish broker" cùng thành công chỉ bằng một khối `try/catch`.

Hai thứ tự ngây thơ đều có cửa sổ sai lệch:

```text
Publish trước -> DB commit thất bại:
    Bên nhận đã xử lý sự kiện về một đơn chưa được xác nhận.

DB commit trước -> Publish thất bại:
    Đơn đã xác nhận nhưng sự kiện chưa đến bên nhận.
```

**Transactional outbox** giải quyết vấn đề này bằng cách lưu thay đổi nghiệp vụ và một bản ghi cần phát đi **trong cùng transaction DB**. Một worker sau đó đọc outbox và gọi hệ thống ngoài khi **không giữ transaction DB của lần ghi nghiệp vụ**.

```text
Request xác nhận đơn
    |
    v
[DB transaction ngắn]
    UPDATE orders
    INSERT outbox(event_id, payload, status='PENDING')
    COMMIT
    |
    v
Response: trạng thái đơn đã được commit

Outbox worker (lần chạy khác)
    |
    +-- [transaction ngắn: claim sự kiện, ghi lease] -- trả connection
    |
    +-- Gọi broker / API ngoài -- không giữ connection
    |
    +-- [transaction ngắn: đánh dấu đã gửi] -- trả connection
```

Ví dụ câu lệnh được thực hiện trong transaction của request:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 1001 AND status = 'DRAFT';
-- Tầng ứng dụng kiểm tra đã cập nhật đúng 1 hàng.

INSERT INTO outbox (event_id, aggregate_id, event_type, status)
VALUES ('event-1001-confirmed', 1001, 'ORDER_CONFIRMED', 'PENDING');

COMMIT;
```

Ví dụ giả định bảng `outbox` có khóa duy nhất trên `event_id` và giao dịch này chỉ phát sự kiện nếu câu `UPDATE` thực sự chuyển trạng thái. Khi xử lý outbox, worker cần có cơ chế claim an toàn giữa nhiều worker (chẳng hạn cập nhật trạng thái có điều kiện và lease có hạn trong transaction ngắn), trả connection, gửi sự kiện, rồi mở transaction mới để ghi kết quả. Để xử lý worker chết giữa chừng cần khôi phục lease đã hết hạn và thử gửi lại có kiểm soát.

Outbox thường đem lại **at-least-once delivery**: nếu broker đã nhận nhưng worker chết trước khi đánh dấu `SENT`, sự kiện có thể được gửi lần nữa. Bên nhận phải hỗ trợ **idempotency/deduplication** theo `event_id`. Không quảng cáo outbox đơn giản là "exactly once" xuyên mọi hệ thống.

Một lời gọi ngoài cần kết quả ngay, như thu tiền qua cổng thanh toán, đòi hỏi thiết kế state machine rõ ràng (ví dụ `PENDING_PAYMENT → PAID/FAILED`), mã yêu cầu idempotency, bước đối soát và có thể bù trừ. Khi nhận lỗi mạng ngay sau khi gọi thanh toán, không thể suy ra bên đối tác chưa xử lý lệnh.

## 5. Quản lý tài nguyên JDBC bằng phạm vi nhỏ nhất

Tối thiểu, mỗi đoạn truy cập DB nên quản lý đầy đủ `Connection`, `PreparedStatement` và `ResultSet`:

```java
public CustomerDto findCustomer(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT customer_id, display_name FROM customers " +
                 "WHERE customer_id = ?";
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(sql)) {
        ps.setLong(1, id);
        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return null;
            }
            return new CustomerDto(
                    rs.getLong("customer_id"),
                    rs.getString("display_name"));
        }
    }
}
```

Ví dụ này giả định `CustomerDto` là một record/class bất biến đã được định nghĩa. Đoạn mã trả về **giá trị tách khỏi JDBC**, không trả lại `ResultSet` hoặc stream phụ thuộc connection còn mở. Khi thoát khối `try-with-resources`, tài nguyên được đóng ngay cả khi có ngoại lệ.

Các điểm dễ bị bỏ sót:

- **Không truyền `Connection` ra luồng xử lý dài:** đừng đặt connection vào HTTP session, cache, singleton hay `CompletableFuture` rồi chờ tác vụ khác dùng nó sau này. JDBC connection thông thường không nên được chia sẻ tùy ý giữa nhiều thread.
- **Tránh lazy loading ngoài transaction:** ORM có thể cần connection khi truy cập thuộc tính chưa được tải. Trả DTO/projection đã có đủ trường trước khi rời persistence boundary, hoặc thiết kế truy vấn phù hợp.
- **Transaction dài cần `rollback` rõ ràng:** nếu đã gọi `setAutoCommit(false)`, sau lỗi phải rollback theo quyền sở hữu transaction trước khi trả connection. Không dựa vào pool để sửa một transaction đang lỗi thay cho ứng dụng.
- **Không nhầm `close()` với commit:** khi dùng pool, `close()` thường trả connection; nó không phải thao tác xác nhận transaction. Chỉ commit khi tất cả bất biến nghiệp vụ trong giao dịch đã được bảo đảm.
- **Tách timeout:** acquisition timeout của pool, JDBC statement/query timeout, lock timeout và HTTP connect/request timeout phục vụ các mục đích khác nhau. Timeout API ngoài không nên kéo theo việc giữ connection đang rảnh.

## 6. Spring: phạm vi @Transactional phải bao quanh phần DB

Một sai sót thường gặp là gắn `@Transactional` lên phương thức điều phối toàn bộ quy trình, khiến cả thời gian chờ API ngoài nằm trong phạm vi transaction:

```java
// Ví dụ nên xem lại:
@Transactional
public void handle(long orderId) {
    OrderSnapshot snapshot = repository.load(orderId);
    ExternalResult result = externalClient.fetch(snapshot);
    repository.update(orderId, result);
}
```

Với Spring, thời điểm kết nối vật lý được lấy có thể phụ thuộc transaction manager, ORM và cấu hình. Nhưng ngay cả khi connection được lấy lười, sau câu DB đầu tiên transaction đã có thể chiếm tài nguyên trong lúc chờ `externalClient.fetch`. `readOnly=true` cũng không tự động bảo đảm trả connection ngay giữa phương thức.

Một cấu trúc rõ hơn là **orchestrator không mở transaction**, gọi hai service/repository boundary quản lý transaction riêng:

```java
@Service
public class QuoteOrchestrator {
    private final QuotePersistence persistence;
    private final ExternalQuoteClient client;

    public QuoteOrchestrator(QuotePersistence persistence,
                             ExternalQuoteClient client) {
        this.persistence = persistence;
        this.client = client;
    }

    public SaveResult refresh(long orderId) {
        QuoteSnapshot snapshot = persistence.loadForQuote(orderId);
        QuoteAmount amount = client.fetch(snapshot); // không có DB transaction
        return persistence.saveIfVersionMatches(snapshot, amount);
    }
}

@Service
public class QuotePersistence {
    @Transactional(readOnly = true)
    public QuoteSnapshot loadForQuote(long orderId) { /* truy vấn DB */ }

    @Transactional
    public SaveResult saveIfVersionMatches(
            QuoteSnapshot snapshot, QuoteAmount amount) {
        /* UPDATE có điều kiện theo version */
    }
}
```

Đây là **minh họa cấu trúc**, với các kiểu `SaveResult`, `QuoteSnapshot`, `QuoteAmount`, `ExternalQuoteClient` do ứng dụng định nghĩa. Cần bảo đảm các phương thức `@Transactional` được gọi qua bean/proxy hoặc cơ chế transaction management đang dùng. Việc một phương thức gọi trực tiếp phương thức `@Transactional` khác trong **cùng đối tượng** có thể không kích hoạt interception theo cấu hình Spring AOP phổ biến. Nếu orchestrator đã tham gia transaction được mở ở tầng gọi, tách thành hai method như trên cũng chưa bảo đảm đoạn HTTP nằm ngoài transaction; phải kiểm soát ranh giới từ tầng trên.

Trong những hệ thống cần điều khiển phạm vi rõ ràng bằng code, có thể dùng `TransactionTemplate` để bọc đúng từng khối thao tác DB. Đối với xử lý bất đồng bộ, cần nắm rõ transaction context và thread đang sở hữu nó; không giả định transaction trên một thread tự truyền qua mọi callback.

## 7. Nếu dữ liệu thay đổi trong lúc chờ tác vụ ngoài?

Việc trả connection trước khi gọi HTTP làm giảm contention nhưng tạo **khoảng trống thời gian** giữa đọc và ghi. Thiết kế cần xác định rõ điều kiện nào phải được xác minh lại.

| Tình huống | Nguy cơ | Cách bảo vệ |
| --- | --- | --- |
| Đọc địa chỉ rồi gọi báo giá; người dùng đổi địa chỉ | Báo giá tương ứng dữ liệu cũ | Cột `version` hoặc điều kiện so sánh trường quan trọng trong `UPDATE`; trả `STALE` và tính lại |
| Đọc tồn kho rồi gọi dịch vụ gợi ý; người khác mua hết | Quyết định dựa trên tồn kho đã cũ | Trừ tồn kho bằng SQL có điều kiện trong transaction chốt đơn, kiểm tra số hàng cập nhật |
| Đánh dấu đơn `PAID` rồi gửi email | Email thất bại sau khi DB đã commit | Outbox và retry có kiểm soát; consumer idempotent |
| Gọi cổng thanh toán rồi connection mới ghi DB thất bại | Tiền đã thu nhưng DB chưa phản ánh | Idempotency key, trạng thái chờ và quy trình đối soát/bù trừ |
| Nhận timeout từ API ngoài | Không rõ đối tác đã xử lý chưa | Truy vấn trạng thái theo request ID nếu API hỗ trợ; tránh retry mù thao tác không idempotent |
| Câu DB sau HTTP báo timeout | Không rõ lệnh có commit hay chưa | Kiểm tra giao dịch/khóa nghiệp vụ trên DB trước khi lặp thao tác có tác dụng nghiệp vụ |

Với những bất biến buộc phải được bảo vệ **trên nhiều hàng DB**, có thể cần transaction ngắn với khóa hoặc mức cô lập phù hợp vào thời điểm chốt quyết định. Cách giảm thời gian giữ kết nối không thay thế atomicity; nó buộc ta đặt đúng **mốc kiểm tra và mốc commit**.

## 8. Quan sát pool và đo vấn đề thực tế

Đừng chỉ tìm SQL chậm. Khi thấy request chờ lâu, cần đo thời gian ở từng pha:

```text
HTTP request đến
   |
   +-- Chờ mượn connection (pool acquire / pending)
   +-- Thời gian chạy SQL
   +-- Thời gian giữ connection sau SQL
   +-- Thời gian gọi dịch vụ ngoài
   +-- Thời gian commit / rollback
   +-- HTTP response
```

Những chỉ số hữu ích (tên metric tùy pool/framework):

| Chỉ số | Giải thích |
| --- | --- |
| Kết nối `active / idle / total` | Pool có đang thường xuyên cạn kết nối khả dụng không |
| Thread/request `pending` đợi connection | Có hàng chờ ở tầng ứng dụng khi pool bận không |
| `connection acquire time` | Mất bao lâu để mượn được kết nối |
| `connection usage time` | Kết nối được giữ bao lâu từ lúc mượn đến lúc trả |
| Transaction duration / idle-in-transaction | Có giao dịch mở nhưng không chạy SQL trong lúc chờ I/O khác không |
| Lock wait, deadlock, query latency | Có tranh chấp tài nguyên DB thật hay chỉ đang chờ pool |
| External HTTP p95/p99, timeout, retry | Thời gian chờ đối tác có trùng với thời gian connection bị giữ không |

Ví dụ nhận diện: biểu đồ cho thấy `connection usage time` tăng lên vài giây cùng lúc với độ trễ API vận chuyển, trong khi phần lớn câu SQL chỉ mất vài mili giây. Đây là dấu hiệu cần kiểm tra phạm vi `Connection`/`@Transactional` trong code. **Tăng kích thước pool ngay** có thể chỉ dời điểm nghẽn sang DB và làm quá tải nhiều kết nối hơn.

Cần phân biệt **pool exhaustion** với **connection leak**:

- *Giữ lâu nhưng cuối cùng trả:* mỗi request vẫn `close()`, nhưng phạm vi mượn quá rộng. Cần rút ngắn phần công việc bên trong `try` hoặc transaction.
- *Leak thật:* có luồng lỗi không đóng connection hoặc giữ tham chiếu mãi. Cần sửa vòng đời tài nguyên, dùng `try-with-resources` và cấu hình leak detection có chọn lọc để hỗ trợ tìm đường đi.

Một connection bị mượn lâu còn có thể do câu SQL thật sự chậm, khóa đang chờ hoặc đọc result set theo kiểu streaming có chủ đích. Không nên tự động kết luận mọi checkout dài đều do chờ HTTP; hãy dùng trace và log để xác nhận.

## 9. Thực hành: tìm và sửa phạm vi giữ tài nguyên

### Bài tập 1: xác định sai lầm

```java
try (Connection connection = dataSource.getConnection()) {
    Customer customer = loadCustomer(connection, customerId);
    Thread.sleep(1500); // mô phỏng chờ việc không liên quan đến DB
    sendMarketingMessage(customer);
}
```

**Câu hỏi:** kết nối được trả vào thời điểm nào? Nếu nhiều request làm vậy, pool gặp vấn đề gì?

**Đáp án:** kết nối chỉ trả khi thoát khối `try`, sau cả thời gian chờ và gửi thông điệp. Các request khác có thể thiếu connection. Cần đóng DB resources ngay sau `loadCustomer`, sau đó mới thực hiện tác vụ ngoài. Nếu đang giữ transaction, phải hoàn tất hoặc rollback trước khi rời đoạn DB.

### Bài tập 2: phát hiện dữ liệu cũ

Luồng A đọc `postal_code='700000', version=3` rồi trả connection. A đi gọi API báo giá. Trong lúc đó, luồng B đổi `postal_code='720000'` và tăng `version=4`. A quay lại với báo giá cho mã `700000`.

**Câu hỏi:** lệnh `UPDATE shipping_orders SET quote_amount = ? WHERE order_id = ?` có an toàn không? Nên sửa điều kiện nào?

**Đáp án:** không, vì báo giá đã cũ. Dùng `WHERE order_id=? AND status='DRAFT' AND version=3`; khi cập nhật 0 hàng, yêu cầu tính lại trên phiên bản mới. Quy tắc tăng version phải áp dụng thống nhất.

### Bài tập 3: xử lý thông báo sau commit

Một ứng dụng cập nhật đơn sang `CONFIRMED` trong DB, rồi gọi broker; broker timeout. Lần retry tiếp theo có thể gửi hai lần.

**Câu hỏi:** làm sao không giữ connection khi gọi broker, nhưng vẫn bảo đảm cuối cùng có cơ hội phát thông báo?

**Đáp án:** ghi outbox event trong **cùng transaction DB** với thay đổi đơn; worker claim event trong transaction ngắn, trả connection rồi gửi; ghi trạng thái sau đó. Xử lý retry/lease và deduplication theo `event_id` vì giao hàng có thể lặp.

### Bài tập 4: đọc metric

Pool có 8 kết nối. 8 request đang giữ connection trong lúc chờ HTTP khoảng 2 giây; SQL của mỗi request mất chưa tới 10 mili giây. Request mới báo timeout khi mượn connection.

**Câu hỏi:** nên tìm phần code nào trước? Tăng pool có giải quyết tận gốc không?

**Đáp án:** xem đoạn `try (Connection...)`, phạm vi `@Transactional` và lời gọi HTTP/callback đang diễn ra giữa hai mốc mượn–trả connection. Rút ngắn phạm vi sở hữu và đo lại; tăng pool riêng lẻ không sửa việc giữ connection khi không dùng.

### Checklist trước khi hoàn tất một luồng persistence Java

- Mỗi lần `getConnection()` có phạm vi kết thúc rõ và luôn trả về pool qua `close()`/`try-with-resources` không?
- Có giữ connection hoặc transaction trong lúc chờ HTTP, broker, file I/O, retry, sleep, người dùng hoặc tác vụ CPU dài không?
- Mọi dữ liệu cần sau khi đóng connection đã được ánh xạ thành DTO độc lập, không phụ thuộc `ResultSet`/lazy session chưa?
- Nếu tách lần đọc và lần ghi, có kiểm tra lại `version`, điều kiện trạng thái hoặc bất biến nghiệp vụ tại thời điểm commit không?
- Nếu tác vụ ngoài có side effect, có idempotency, outbox hoặc quy trình đối soát phù hợp không?
- Timeout cho pool, SQL, lock và external API đã được tách và đo riêng chưa? Có theo dõi active/pending/usage time của pool không?

**Kết luận:** Kết nối DB nên được mượn trong **thời gian thực sự cần thao tác dữ liệu**, rồi trả ngay để phục vụ yêu cầu khác. Với tác vụ ngoài không liên quan, tách thành các ranh giới DB ngắn giúp giảm cạn pool, thời gian giữ khóa và độ trễ lan truyền. Khi tách giao dịch, phải đồng thời bảo vệ tính đúng đắn bằng kiểm tra phiên bản, thao tác có điều kiện và cơ chế phối hợp phù hợp với side effect.
