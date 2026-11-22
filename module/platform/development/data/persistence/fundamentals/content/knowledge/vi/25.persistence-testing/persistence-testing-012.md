# Mô phỏng gián đoạn kết nối, ghi dở dang và kết quả commit chưa rõ

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Chỉ ra các điểm sự cố trên đường **mượn connection → thực thi SQL → COMMIT → gửi phản hồi** và phân biệt kết quả đã biết với kết quả chưa xác định.
2. Giải thích vì sao mất kết nối **trước khi gửi COMMIT** khác với mất phản hồi **sau khi COMMIT có thể đã tới database**, và vì sao gọi `rollback()` không chứng minh dữ liệu chưa được commit.
3. Thiết kế fault injection ở mức JDBC, mạng, tiến trình và API để tái hiện lỗi một cách **có kiểm soát, xác định và có thể lặp lại**.
4. Kiểm thử tính nguyên tử của transaction khi một phần SQL đã chạy, connection bị đóng và database rollback các thay đổi chưa commit.
5. Xây dựng nghiệp vụ ghi idempotent bằng khóa yêu cầu duy nhất, conditional UPDATE, transaction và quy trình đối soát trên kết nối mới.
6. Viết integration test Java 17/PostgreSQL với JUnit 5 và Testcontainers, phân biệt lỗi tổng hợp trong test với sự cố thực ở giao thức mạng.
7. Kiểm tra bất biến dữ liệu, side effect ngoài DB, retry budget, tài nguyên JDBC, metrics và các giới hạn mà một bài test không thể chứng minh.

Bài thuộc chương **Kiểm thử lưu trữ** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module tập trung vào dữ liệu bền vững trong Java: từ mô hình, schema, truy vấn và chỉ mục đến transaction, isolation, concurrency, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Đích của bài không phải “làm cho test ném exception”, mà là chứng minh **hệ thống xử lý chính xác khi người gọi không thể quan sát chắc kết quả ghi**.

## 1. Bốn kết quả cần phân biệt

Giả sử API Java nhận yêu cầu đặt trước một sản phẩm. Nó cần trừ số lượng tồn kho và ghi nhận một yêu cầu duy nhất.

| Tình huống | Bên Java quan sát | Có thể kết luận điều gì? |
| --- | --- | --- |
| SQL được DB từ chối rõ ràng; chưa COMMIT | SQLSTATE ràng buộc, serialization hoặc deadlock | Transaction cần rollback; nguyên nhân lỗi phải được phân loại |
| Connection bị đóng khi transaction còn các UPDATE nhưng **chưa gửi COMMIT** | Lỗi kết nối/đóng session | Những thay đổi chưa commit không được trở thành dữ liệu đã commit; cần kiểm tra DB thực |
| Client đã gửi COMMIT nhưng không nhận được kết quả | Timeout, socket reset, SQL exception | **Không biết chắc** commit thành công hay thất bại |
| DB commit thành công nhưng HTTP response không đến caller | Client HTTP timeout | DB có thể đã có dữ liệu; request tiếp theo phải dùng idempotency |

Hai mục cuối là bẫy phổ biến: **một lỗi giao tiếp không đồng nghĩa với một thao tác nghiệp vụ đã thất bại**.

### 1.1. Không phải mọi ngoại lệ giống nhau

Với JDBC, `SQLException` có thể xuất hiện ở nhiều bước:

~~~text
HTTP client
    |
    v
Java service
    |
    +-- A: DataSource.getConnection()
    |
    +-- B: BEGIN / setAutoCommit(false)
    |
    +-- C: SELECT / UPDATE / INSERT
    |
    +-- D: COMMIT
    |
    +-- E: dựng kết quả, trả HTTP response
    |
    v
Client nhận xác nhận
~~~

Vị trí lỗi ảnh hưởng trực tiếp đến quyết định có retry hay không.

- **A:** chưa lấy được connection ở nhánh này, nên chưa gửi SQL qua connection đó. Có thể chờ rồi thử lại nếu còn deadline.
- **B/C trước COMMIT:** nếu dùng một transaction thực sự, có thể rollback; cần biết SQL bị từ chối, socket đứt hay transaction đang chờ khóa.
- **D:** nếu COMMIT được gửi mà kết quả trả về bị mất, không thể suy ra rollback chỉ từ exception.
- **E:** kết quả DB có thể đã chắc chắn commit ở server, nhưng caller không nhận được xác nhận và có thể gọi lại.

Ngoài ra, với chế độ **autocommit**, một statement ghi có thể tự kết thúc transaction. Nếu socket đứt sau khi gửi statement, trạng thái commit cũng có thể **chưa rõ** dù Java không gọi `connection.commit()` riêng.

## 2. Ba timeline cần thuộc

### 2.1. Ghi dở dang rồi session thật sự kết thúc

~~~text
Java                         PostgreSQL
  |                              |
  |---------- BEGIN ------------>|
  |---------- UPDATE ----------->|  thay đổi trong transaction
  |---------- INSERT ----------->|  vẫn chưa commit
  |                              |
  X  session bị đóng / rollback   |
  |                              |  hủy transaction chưa commit
  |                              |
  |-- kết nối mới: SELECT ------->|  thấy trạng thái cũ
~~~

Với PostgreSQL và transaction thông thường, các thay đổi chưa commit sẽ không hiển thị như dữ liệu đã commit sau khi session bị kết thúc và transaction rollback. Test phải **đọc bằng connection mới**, chứ không kết luận chỉ vì test gọi `close()`.

Nếu connection chỉ bị mất liên lạc nhưng DB chưa phát hiện session chết, session hoặc transaction có thể còn tồn tại tạm thời. Test phải xác định được điều kiện kết thúc thật, không coi “client bị timeout” là bằng chứng rollback tức thì.

### 2.2. COMMIT đã xảy ra, phản hồi bị mất

~~~text
Java                         PostgreSQL
  |                              |
  |---------- UPDATE ----------->|
  |---------- COMMIT ----------->|
  |                              |  commit thành công
  |                  phản hồi X   |
  X  SQLException / timeout      |
  |                              |
  |-- connection mới: SELECT --->|  dữ liệu đã tồn tại
~~~

Không có cách suy ra từ lỗi socket rằng lịch thực thi này **chắc chắn không xảy ra**. Nếu Java catch lỗi rồi gọi `rollback()` trên một connection không còn tin cậy, rollback đó **không đảo ngược một commit đã hoàn tất**.

### 2.3. Mất kết quả HTTP sau commit

~~~text
Client A                  Java service                 DB
   |                           |                       |
   |---- POST /reserve ------->|                       |
   |                           |---- transaction ----->|
   |                           |<--- COMMIT OK --------|
   |                  HTTP 201 X                       |
   |<------------------------- X                       |
   |                                                   |
   |---- POST lại với cùng request_key --------------->|
   |                   Service đối soát, không ghi trùng |
~~~

Ở timeline này, chính service **biết** COMMIT đã thành công; chỉ HTTP caller không biết. Test ở tầng API phải bảo đảm request lặp **không tạo thêm side effect**.

Ba timeline có thể tạo ra triệu chứng gần giống nhau ở người dùng (“timeout”), nhưng assertion và cách phục hồi khác nhau.

## 3. Ma trận fault injection theo giai đoạn

| Điểm chèn lỗi | Cách mô phỏng phù hợp | Bất biến cần kiểm |
| --- | --- | --- |
| Trước khi lấy connection | Datasource/proxy từ chối kết nối, pool timeout | Không có write mới do request này |
| Ngay sau `BEGIN` | Đóng connection vật lý hoặc rollback | Không có thay đổi commit |
| Sau UPDATE thứ nhất, trước INSERT thứ hai | Transaction hook + đóng connection/rollback | Hai bảng không bị commit một nửa |
| Statement đang chờ khóa | Một connection khác giữ khóa; đặt timeout | Lỗi được phân loại, transaction được rollback |
| SQL bị DB từ chối | Vi phạm CHECK/UNIQUE/FK có chủ đích | Không ghi dữ liệu không hợp lệ; SQLSTATE đúng |
| Ngay trước gửi COMMIT | Hook dừng/đóng kết nối trước COMMIT | Không được công bố “thành công” |
| COMMIT gửi rồi mất ACK | Proxy/hook kiểm soát phản hồi | Client báo **unknown**, DB có thể đã commit |
| Sau khi service nhận COMMIT OK | Chặn phản hồi HTTP | Retry cùng key trả cùng kết quả nghiệp vụ |
| Sau DB commit, trước phát event | Dừng tiến trình; dùng transactional outbox | Event không mất âm thầm hoặc có reconciliation |
| Khi replica chưa nhận WAL | Failover lab có kiểm soát | Mục tiêu RPO và lịch sử commit được kiểm chứng |

Các phép mô phỏng ở bảng không tương đương nhau. Ví dụ **ném exception sau khi hàm `commit()` đã trả thành công** mô phỏng *sự quan sát của caller mất kết quả*, nhưng không chứng minh driver xử lý packet loss và commit protocol như thế nào. Cần ghi rõ phạm vi mỗi test.

### 3.1. Test seam, proxy mạng và fault thực tế

Có ba mức thử nghiệm:

1. **Mức application:** tiêm hook tại vị trí cụ thể, ví dụ “đã COMMIT thật nhưng báo lỗi cho phía gọi”. Nhanh, ổn định và dễ assert, nhưng không chứng minh hành vi socket/driver.
2. **Mức connection/network:** đặt proxy giữa JDBC driver và PostgreSQL (ví dụ môi trường có Toxiproxy), cắt kết nối hoặc làm chậm truyền/nhận đúng giai đoạn. Kiểm tra đường đi của exception, timeout và reconnect.
3. **Mức database/process/failover:** crash hoặc cô lập PostgreSQL trong lab, promote standby, đo WAL và đối soát dữ liệu. Kiểm tra khả năng phục hồi thực và failure domain.

Nên có test ở cả ba mức nếu đây là luồng nghiệp vụ quan trọng. Không chạy fault injection phá hoại trên production khi chưa có quy trình được phê duyệt.

## 4. Chuẩn bị bất biến nghiệp vụ trước khi “phá” kết nối

Không nên chỉ assert “exception đã ném”. Với nghiệp vụ giữ hàng:

- Stock không được âm.
- Một `(tenant_id, request_key)` chỉ được tạo **một** kết quả nghiệp vụ.
- Nếu outcome `RESERVED`, đúng một lượng hàng tương ứng đã bị giữ.
- Nếu outcome `REJECTED` vì hết hàng, stock không bị giảm.
- Đơn/yêu cầu và thay đổi stock phải **commit hoặc rollback cùng nhau**.
- Hai request khác payload nhưng cùng key không được coi là cùng một yêu cầu.
- Một lời gọi HTTP lặp không được nhân đôi thanh toán, gửi hàng hoặc event ngoài DB.
- Sau sự cố, hệ thống có thể đối soát với nguồn có thẩm quyền mà không tin vào cache/replica trễ.

### 4.1. Schema PostgreSQL cho phòng lab

Lược đồ sau giữ tập trung vào **một transaction ghi**:

~~~sql
CREATE TABLE inventory (
    tenant_id    BIGINT NOT NULL,
    product_id   BIGINT NOT NULL,
    available    INTEGER NOT NULL CHECK (available >= 0),
    PRIMARY KEY (tenant_id, product_id)
);

CREATE TABLE reservation_requests (
    tenant_id    BIGINT NOT NULL,
    request_key  VARCHAR(120) NOT NULL,
    product_id   BIGINT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    status       TEXT NOT NULL
                 CHECK (status IN ('PENDING', 'RESERVED', 'REJECTED')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, request_key),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES inventory (tenant_id, product_id)
);
~~~

Lưu ý:

- `PRIMARY KEY (tenant_id, request_key)` là rào chắn idempotency quan trọng nhất.
- `CHECK (available >= 0)` là lớp phòng thủ cuối; SQL cập nhật có điều kiện vẫn phải kiểm soát số hàng bị ảnh hưởng.
- `PENDING` được dùng **bên trong transaction đang xử lý**; đường ghi mẫu sẽ cập nhật thành `RESERVED` hoặc `REJECTED` trước khi commit. Nếu đọc được hàng `PENDING` đã commit, phải điều tra hoặc có một giao thức xử lý trạng thái riêng; không tự động trừ hàng lần nữa.
- Foreign key mang tenant để một request không trỏ tới sản phẩm thuộc tenant khác.
- Lược đồ là ví dụ thử nghiệm; production còn cần phân quyền, RLS khi phù hợp, retention, event outbox và audit.

Fixture:

~~~sql
INSERT INTO inventory (tenant_id, product_id, available)
VALUES (42, 101, 5), (77, 101, 10);
~~~

Tenant 42 và 77 cùng có product ID 101, nhưng stock phải độc lập.

## 5. Ghi nguyên tử: một transaction bao gồm tất cả thay đổi

Quy trình tạo yêu cầu lần đầu:

~~~text
BEGIN
   |
   +-- INSERT reservation_requests(key, payload, PENDING)
   |       ON CONFLICT DO NOTHING
   |
   +-- Nếu key mới:
   |      UPDATE inventory
   |      SET available = available - quantity
   |      WHERE available >= quantity
   |
   |      UPDATE reservation_requests
   |      SET status = RESERVED hoặc REJECTED
   |
   +-- Nếu key đã có:
   |      SELECT trạng thái cũ và so khớp payload
   |
COMMIT
   |
   +-- Chỉ sau COMMIT OK mới trả kết quả chắc chắn
~~~

Mọi thay đổi dùng **cùng connection và cùng transaction**. Không viết:

~~~text
Connection A: trừ stock, autocommit
Connection B: tạo reservation, autocommit
~~~

vì nếu bước thứ hai lỗi, stock đã bị trừ nhưng không có yêu cầu tương ứng.

### 5.1. SQL atomic conditional UPDATE

~~~sql
UPDATE inventory
SET available = available - ?
WHERE tenant_id = ?
  AND product_id = ?
  AND available >= ?;
~~~

Nếu số hàng được cập nhật là 1, DB đã thực hiện bước giữ hàng **trong transaction đang chạy**. Nếu 0, stock không đủ hoặc sản phẩm không tồn tại; cần business rule phân biệt hai lý do nếu API yêu cầu. Không được chỉ dựa vào một SELECT stock trước đó rồi tính giảm trong Java mà không có bảo vệ concurrency.

### 5.2. Xử lý trùng request key an toàn

~~~sql
INSERT INTO reservation_requests (
    tenant_id, request_key, product_id, quantity, status
)
VALUES (?, ?, ?, ?, 'PENDING')
ON CONFLICT (tenant_id, request_key) DO NOTHING
RETURNING request_key;
~~~

Khi `RETURNING` có hàng, transaction hiện tại vừa tạo bản ghi mới **chưa commit**. Khi không có hàng, khóa đã tồn tại; service phải đọc hàng đó, kiểm tra `product_id` và `quantity` rồi trả outcome cũ nếu đúng nội dung.

Trong PostgreSQL READ COMMITTED, một INSERT cạnh tranh cùng unique key có thể phải **chờ transaction đang giữ key kết thúc**. Sau `ON CONFLICT DO NOTHING`, một SELECT **ở statement kế tiếp** có thể thấy hàng vừa được transaction khác commit. Tuy vậy, timeout, xóa cùng key, thay đổi isolation hoặc sự cố kết nối vẫn cần được xử lý như những nhánh lỗi riêng.

Nếu key trùng nhưng payload khác, trả lỗi conflict **không thực hiện trừ stock**. Unique key không tự bảo đảm hai request có cùng ý nghĩa nghiệp vụ nếu không đối chiếu payload.

## 6. Java 17/JDBC: service có điểm tiêm sự cố tại COMMIT

Ví dụ sau sử dụng `ConnectionFactory` để test có thể dùng kết nối thật từ Testcontainers mà không cần khởi tạo toàn bộ framework. Ứng dụng thực có thể truyền `dataSource::getConnection`.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ReservationService {

    @FunctionalInterface
    public interface ConnectionFactory {
        Connection open() throws SQLException;
    }

    @FunctionalInterface
    public interface CommitAction {
        void commit(Connection connection) throws SQLException;
    }

    public record Request(
            long tenantId,
            String requestKey,
            long productId,
            int quantity) {}

    public record Result(String requestKey, String status) {}

    public static final class CommitOutcomeUnknownException
            extends SQLException {
        public CommitOutcomeUnknownException(
                String requestKey, SQLException cause) {
            super("Cannot determine commit outcome for request key "
                    + requestKey, cause);
        }
    }

    private final ConnectionFactory connections;
    private final CommitAction commitAction;

    public ReservationService(ConnectionFactory connections) {
        this(connections, Connection::commit);
    }

    // Hook này chỉ nhằm tạo test có thể tái hiện điểm lỗi.
    public ReservationService(
            ConnectionFactory connections,
            CommitAction commitAction) {
        this.connections = connections;
        this.commitAction = commitAction;
    }

    public Result reserve(Request request) throws SQLException {
        if (request == null
                || request.tenantId() <= 0
                || request.productId() <= 0
                || request.quantity() <= 0
                || request.requestKey() == null
                || request.requestKey().isBlank()) {
            throw new IllegalArgumentException("Invalid request");
        }

        try (Connection connection = connections.open()) {
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
            connection.setAutoCommit(false);

            boolean commitAttempted = false;
            try {
                Result result;

                if (insertRequestIfAbsent(connection, request)) {
                    boolean reserved =
                            reserveStock(connection, request);
                    String status = reserved
                            ? "RESERVED" : "REJECTED";
                    completeRequest(connection, request, status);
                    result = new Result(request.requestKey(), status);
                } else {
                    result = findExisting(connection, request);
                }

                // Từ đây, lỗi JDBC có thể để lại outcome chưa rõ.
                commitAttempted = true;
                commitAction.commit(connection);
                return result;
            } catch (SQLException | RuntimeException failure) {
                // Rollback chỉ là cố gắng dọn transaction/connection.
                // Nó KHÔNG chứng minh COMMIT trước đó chưa thành công.
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }

                if (commitAttempted
                        && failure instanceof SQLException sqlError) {
                    throw new CommitOutcomeUnknownException(
                            request.requestKey(), sqlError);
                }
                throw failure;
            }
        }
    }

    private static boolean insertRequestIfAbsent(
            Connection connection, Request request)
            throws SQLException {
        String sql = """
            INSERT INTO reservation_requests (
                tenant_id, request_key, product_id, quantity, status
            )
            VALUES (?, ?, ?, ?, 'PENDING')
            ON CONFLICT (tenant_id, request_key) DO NOTHING
            RETURNING request_key
            """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setLong(1, request.tenantId());
            statement.setString(2, request.requestKey());
            statement.setLong(3, request.productId());
            statement.setInt(4, request.quantity());

            try (ResultSet rows = statement.executeQuery()) {
                return rows.next();
            }
        }
    }

    private static boolean reserveStock(
            Connection connection, Request request)
            throws SQLException {
        String sql = """
            UPDATE inventory
            SET available = available - ?
            WHERE tenant_id = ?
              AND product_id = ?
              AND available >= ?
            """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setInt(1, request.quantity());
            statement.setLong(2, request.tenantId());
            statement.setLong(3, request.productId());
            statement.setInt(4, request.quantity());
            return statement.executeUpdate() == 1;
        }
    }

    private static void completeRequest(
            Connection connection, Request request, String status)
            throws SQLException {
        String sql = """
            UPDATE reservation_requests
            SET status = ?
            WHERE tenant_id = ?
              AND request_key = ?
            """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, status);
            statement.setLong(2, request.tenantId());
            statement.setString(3, request.requestKey());

            if (statement.executeUpdate() != 1) {
                throw new SQLException(
                        "Request status update affected unexpected rows");
            }
        }
    }

    private static Result findExisting(
            Connection connection, Request request)
            throws SQLException {
        String sql = """
            SELECT product_id, quantity, status
            FROM reservation_requests
            WHERE tenant_id = ? AND request_key = ?
            """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setLong(1, request.tenantId());
            statement.setString(2, request.requestKey());

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new SQLException(
                            "Request disappeared during reconciliation");
                }

                if (rows.getLong("product_id") != request.productId()
                        || rows.getInt("quantity") != request.quantity()) {
                    throw new IllegalArgumentException(
                            "Request key reused with different payload");
                }

                String status = rows.getString("status");
                if ("PENDING".equals(status)) {
                    throw new SQLException(
                            "Committed request still pending reconciliation");
                }
                return new Result(request.requestKey(), status);
            }
        }
    }
}
~~~

### 6.1. Những điều ví dụ cố ý không tự hứa

- Service giả định `tenantId` đã được xác thực và người gọi được phép đặt hàng trong tenant đó. Trong production cần kiểm tra authorization và/hoặc RLS.
- `CommitAction` là test seam; production dùng `Connection::commit`. Không làm mất ACK trong production bằng một hook test.
- `CommitOutcomeUnknownException` là **phân loại phía ứng dụng**, không phải mã SQLSTATE do PostgreSQL trả.
- Sau khi đã gửi hoặc định gửi COMMIT, nếu gặp SQLException thì xử lý thận trọng là **unknown** cho tới khi đối soát; mọi lỗi không nhất thiết có nghĩa COMMIT thành công.
- Nếu `connection.rollback()` được gọi sau khi COMMIT đã hoàn tất, nó không đảo ngược commit cũ.
- Trong READ COMMITTED, request trùng key thường có thể tra cứu hàng vừa commit sau statement phát hiện conflict. Trường hợp timeout/trạng thái không ổn định vẫn phải theo quy trình retry có deadline.
- Code chỉ bảo vệ hai bảng trong một PostgreSQL transaction. HTTP gọi cổng thanh toán, gửi email hoặc phát event ra ngoài không tự rollback.
- Khi failover làm **mất một commit đã được ACK** vì replica/backup thiếu WAL, chỉ unique constraint trên primary mới không đủ để phục hồi lịch sử đã mất; cần cơ chế đối soát độc lập theo RPO.

## 7. Java integration test: rollback khi connection đóng trước COMMIT

Để chứng minh “ghi dở dang không bền”, cần transaction với **ít nhất một UPDATE** đã thực thi, sau đó đóng session mà không commit và kiểm tra bằng connection khác.

Một lớp JUnit 5/Testcontainers mẫu:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLTransientConnectionException;
import java.sql.Statement;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PersistenceFailureIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static Connection open() throws SQLException {
        return DriverManager.getConnection(
                POSTGRES.getJdbcUrl(),
                POSTGRES.getUsername(),
                POSTGRES.getPassword());
    }

    static ReservationService service() {
        return new ReservationService(
                PersistenceFailureIntegrationTest::open);
    }

    @BeforeAll
    static void createSchema() throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement()) {
            s.executeUpdate("""
                CREATE TABLE inventory (
                    tenant_id BIGINT NOT NULL,
                    product_id BIGINT NOT NULL,
                    available INTEGER NOT NULL CHECK (available >= 0),
                    PRIMARY KEY (tenant_id, product_id)
                )
                """);
            s.executeUpdate("""
                CREATE TABLE reservation_requests (
                    tenant_id BIGINT NOT NULL,
                    request_key VARCHAR(120) NOT NULL,
                    product_id BIGINT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    status TEXT NOT NULL CHECK (
                        status IN ('PENDING', 'RESERVED', 'REJECTED')
                    ),
                    PRIMARY KEY (tenant_id, request_key),
                    FOREIGN KEY (tenant_id, product_id)
                        REFERENCES inventory(tenant_id, product_id)
                )
                """);
        }
    }

    @BeforeEach
    void reset() throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement()) {
            s.executeUpdate("""
                TRUNCATE TABLE reservation_requests, inventory
                """);
            s.executeUpdate("""
                INSERT INTO inventory (tenant_id, product_id, available)
                VALUES (42, 101, 5), (77, 101, 10)
                """);
        }
    }

    static int stock(long tenantId) throws SQLException {
        try (Connection c = open();
             PreparedStatement p = c.prepareStatement("""
                 SELECT available FROM inventory
                 WHERE tenant_id = ? AND product_id = 101
                 """)) {
            p.setLong(1, tenantId);
            try (ResultSet rows = p.executeQuery()) {
                assertTrue(rows.next());
                return rows.getInt(1);
            }
        }
    }

    static long countRequests(long tenantId) throws SQLException {
        try (Connection c = open();
             PreparedStatement p = c.prepareStatement("""
                 SELECT count(*) FROM reservation_requests
                 WHERE tenant_id = ?
                 """)) {
            p.setLong(1, tenantId);
            try (ResultSet rows = p.executeQuery()) {
                assertTrue(rows.next());
                return rows.getLong(1);
            }
        }
    }

    @Test
    void uncommittedUpdateIsRolledBackWhenSessionCloses()
            throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try (PreparedStatement p = c.prepareStatement("""
                    UPDATE inventory
                    SET available = available - 2
                    WHERE tenant_id = 42 AND product_id = 101
                    """)) {
                assertEquals(1, p.executeUpdate());
            }

            // Không gọi commit(): đóng physical JDBC connection.
            // Với PostgreSQL, transaction chưa commit bị rollback.
        }

        assertEquals(5, stock(42));
        assertEquals(10, stock(77));
    }

    @Test
    void errorBeforeCommitDoesNotLeavePartialBusinessState()
            throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);

            try (Statement s = c.createStatement()) {
                assertEquals(1, s.executeUpdate("""
                    UPDATE inventory
                    SET available = available - 2
                    WHERE tenant_id = 42 AND product_id = 101
                    """));
            }

            // Mô phỏng statement tiếp theo bị DB từ chối.
            try (Statement s = c.createStatement()) {
                SQLException error = assertThrows(
                    SQLException.class,
                    () -> s.executeUpdate("""
                        INSERT INTO reservation_requests
                            (tenant_id, request_key, product_id,
                             quantity, status)
                        VALUES (42, 'bad', 101, -1, 'PENDING')
                        """));
                assertEquals("23514", error.getSQLState());
            }

            c.rollback();
        }

        assertEquals(5, stock(42));
        assertEquals(0, countRequests(42));
    }

    @Test
    void lostCommitResponseMayHideSuccessfulCommit()
            throws SQLException {
        ReservationService.ConnectionFactory connections =
                PersistenceFailureIntegrationTest::open;

        // Chỉ trong test: COMMIT thật, sau đó tạo cảm giác ACK bị mất.
        ReservationService withLostAck =
                new ReservationService(connections, connection -> {
                    connection.commit();
                    throw new SQLTransientConnectionException(
                            "Synthetic lost COMMIT response", "08006");
                });

        var request = new ReservationService.Request(
                42, "checkout-001", 101, 2);

        assertThrows(
                ReservationService.CommitOutcomeUnknownException.class,
                () -> withLostAck.reserve(request));

        // COMMIT đã thật sự thành công: không được coi lỗi là rollback.
        assertEquals(3, stock(42));
        assertEquals(1, countRequests(42));

        // Client gửi lại CÙNG key: phải trả kết quả cũ, không trừ nữa.
        var recovered = service().reserve(request);
        assertEquals("RESERVED", recovered.status());
        assertEquals(3, stock(42));
        assertEquals(1, countRequests(42));
    }

    @Test
    void sameKeyDifferentPayloadMustNotReserveAgain()
            throws SQLException {
        service().reserve(new ReservationService.Request(
                42, "checkout-002", 101, 2));

        assertThrows(IllegalArgumentException.class,
                () -> service().reserve(new ReservationService.Request(
                        42, "checkout-002", 101, 3)));

        assertEquals(3, stock(42));
        assertEquals(1, countRequests(42));
    }

    @Test
    void otherTenantHasIndependentStockAndRequestKey()
            throws SQLException {
        var a = service().reserve(new ReservationService.Request(
                42, "same-key", 101, 2));
        var b = service().reserve(new ReservationService.Request(
                77, "same-key", 101, 3));

        assertEquals("RESERVED", a.status());
        assertEquals("RESERVED", b.status());
        assertEquals(3, stock(42));
        assertEquals(7, stock(77));
        assertEquals(1, countRequests(42));
        assertEquals(1, countRequests(77));
    }
}
~~~

**Yêu cầu triển khai:** project phải có JUnit Jupiter, Testcontainers PostgreSQL/JUnit integration và PostgreSQL JDBC driver tương thích. Ví dụ dành cho PostgreSQL Testcontainers chuyên dụng, không chạy với datasource production. Tránh test chạy song song trên cùng fixture dùng `TRUNCATE` nếu chưa thiết kế isolation giữa test.

### 7.1. Test mất ACK trên là mô phỏng gì?

Ở `lostCommitResponseMayHideSuccessfulCommit`, `connection.commit()` **đã trả thành công trong JVM**, rồi hook mới ném lỗi tổng hợp. Nó chứng minh quy tắc ứng dụng:

> Nếu caller quan sát một lỗi được phân loại là commit outcome chưa rõ, ứng dụng không được mặc định rollback và retry bằng một request key khác.

Nó **không** chứng minh driver gửi/nhận packet như thế nào khi cắt TCP thật giữa các byte của COMMIT. Muốn kiểm chứng driver/network, cần thêm thử nghiệm ở proxy và/hoặc PostgreSQL process thật với điều kiện sự cố được ghi nhận rõ.

## 8. Tái hiện bằng network proxy: phải chọn đúng điểm lỗi

Nếu cần thử stack JDBC thực, có thể đặt **một proxy TCP có điều khiển** giữa PostgreSQL JDBC driver và database trong môi trường lab. Các công cụ fault injection có thể tạo:

- Mất kết nối trước khi gửi SQL.
- Latency hoặc timeout khi đang đọc dữ liệu trả về.
- Kết nối bị reset trong lúc chờ COMMIT.
- Cắt toàn bộ traffic giữa service instance và DB.
- Mạng phục hồi rồi client phải tạo connection mới.

Tuy nhiên, **chỉ thao tác “cắt proxy sau 500 ms” không xác định chắc COMMIT đã xảy ra hay chưa**. Do đó phải thiết kế đồng bộ sự kiện:

1. Gắn request key duy nhất cho mỗi kịch bản.
2. Dùng query/marker/hook để xác định request đã tới bước cần thử.
3. Điều khiển proxy theo mốc càng sát giao thức càng tốt; lưu timeline và log.
4. Cho Java nhận lỗi, nhưng **không suy diễn kết quả DB**.
5. Khôi phục đường kết nối hoặc dùng đường quản trị riêng đã được cho phép.
6. Mở connection mới, đọc authoritative DB theo request key.
7. Thử lại cùng key và xác minh bất biến cuối.
8. Lặp nhiều lần để ghi nhận cả nhánh “commit có” và “commit không”, nếu fault thật có thể tạo cả hai.

Để phân biệt **DB xử lý xong COMMIT nhưng ACK mất** khỏi **COMMIT không tới DB**, một proxy có khả năng quan sát/chặn phản hồi có thể hữu ích; song PostgreSQL wire protocol, TLS và driver làm việc đặt fault đúng byte khó hơn so với một test seam. Đừng khẳng định đã mô phỏng “ACK sau COMMIT bị mất” chỉ dựa vào một lỗi `08006`.

### 8.1. Timeout không phải một nút tắt transaction

Các timeout khác nhau có ý nghĩa khác nhau:

| Giới hạn | Vị trí | Có thể quan sát |
| --- | --- | --- |
| Pool acquisition timeout | Chờ connection ở Java | SQL chưa được gửi qua connection chưa mượn |
| TCP connect timeout | Thiết lập kết nối | Chưa có session JDBC dùng được |
| Socket read timeout | Chờ dữ liệu từ DB | DB có thể đang xử lý hoặc đã xử lý xong |
| JDBC statement timeout | Chờ một statement | DB/driver có thể hủy statement; cần xem trạng thái transaction |
| PostgreSQL `statement_timeout` | Phía DB | Thường hủy statement, có thể dẫn tới transaction aborted |
| PostgreSQL `lock_timeout` | Chờ khóa trong DB | Không lấy được khóa đúng hạn; cần rollback hoặc xử lý theo nghiệp vụ |
| HTTP request timeout | Client/gateway | Service có thể vẫn đang xử lý hoặc đã commit |
| Transaction timeout | Transaction manager | Có thể đánh dấu rollback-only hoặc hủy, tùy framework |

Một client HTTP ngắt kết nối không nhất thiết khiến PostgreSQL dừng công việc ngay. Khi tổ chức các timeout cần xác định **deadline tổng** thay vì cho phép mỗi lớp thử lại nhiều lượt không phối hợp.

## 9. Gián đoạn kết nối trong transaction và vòng đời JDBC

### 9.1. Connection đóng không đồng nghĩa SQL chưa chạy

Một UPDATE có thể đã được server thực thi và giữ khóa/hàng đã đổi trong transaction. Nhưng trước COMMIT, thay đổi đó vẫn chưa trở thành **committed state**. Khi session thật sự kết thúc và transaction được rollback, thay đổi không còn.

Nếu test chỉ gọi `connection.close()` trên connection được lấy từ một **pool**, cần kiểm tra pool xử lý thế nào: `close()` thường trả handle về pool, không hẳn cắt TCP vật lý ngay. Trong ví dụ JUnit phía trên, `DriverManager.getConnection()` tạo connection trực tiếp nên việc đóng dễ chứng minh nhánh kết thúc session hơn.

Trong lab dùng pool, có thể thử:

- Transaction bị exception và rollback rõ ràng.
- Handle được trả pool, kiểm tra pool có rollback/reset transaction state không.
- Physical connection bị cắt từ proxy hoặc network.
- Kết nối mới từ pool không thừa hưởng uncommitted transaction hay tenant session state.
- Pool loại bỏ connection hỏng, không tiếp tục giao nó cho request khác.

### 9.2. PostgreSQL transaction aborted

Nếu statement trong transaction gây lỗi SQL, PostgreSQL thường chuyển transaction sang trạng thái **aborted**. Những statement tiếp theo có thể báo SQLSTATE `25P02` cho đến khi rollback hoặc rollback tới savepoint thích hợp.

Vì vậy, retry một statement trên cùng transaction sau lỗi `23505`, `40001` hoặc `40P01` thường không phải giải pháp. Nếu lỗi retryable, ứng dụng nên tạo **transaction mới** và tính lại quyết định nghiệp vụ.

### 9.3. Lỗi SQLSTATE tham khảo

| SQLSTATE | Ý nghĩa | Hướng test |
| --- | --- | --- |
| `08xxx` | Connection exception | Xác định lỗi ở giai đoạn nào; với ghi phải xét unknown outcome |
| `08006` | Connection failure | Mất kết nối, không suy ra commit thất bại |
| `08007` | Transaction resolution unknown | Nếu driver/DB trả, cần đối soát; không giả định tất cả driver dùng mã này |
| `40001` | Serialization failure | Có thể retry **toàn transaction** khi idempotent |
| `40P01` | Deadlock detected | Rollback và thử lại toàn transaction có budget |
| `55P03` | Lock not available | Kiểm tra chính sách khóa, lock timeout và retry phù hợp |
| `57014` | Query canceled | Không tự retry nếu request đã bị hủy có chủ ý |
| `25P02` | In failed SQL transaction | Rollback và xử lý nguyên nhân trước đó |
| `23505` | Unique violation | Kiểm tra request key/payload hoặc báo conflict |
| `23514` | Check violation | Dữ liệu không hợp lệ, sửa đầu vào thay vì retry |

Không assert thông báo tiếng Anh của driver làm tiêu chí duy nhất. Thông báo và exception wrapper có thể thay đổi; giữ SQLSTATE và **giai đoạn thao tác** trong log kiểm thử.

## 10. Đối soát commit chưa rõ bằng key duy nhất

Một protocol tối thiểu:

~~~text
Client gọi reserve với requestKey = "checkout-001"
                   |
                   v
          DB transaction bắt đầu
                   |
              ... ghi ...
                   |
                   v
            COMMIT thử gửi
              /          \
          Có ACK       Mất ACK/lỗi
             |              |
             v              v
       Trả kết quả     Đánh dấu UNKNOWN
                            |
                            v
                 Mở kết nối mới tới nguồn
                 có thẩm quyền (thường primary)
                            |
               +------------+-------------+
               |            |             |
          Có row cùng    Có row key    Chưa thấy row
          key/payload    khác payload       |
               |            |             |
          Trả outcome   Báo conflict   Không kết luận
          đã lưu                       chắc là rollback
                                            |
                                            v
                             Retry đúng CÙNG key với
                             UNIQUE + transaction,
                             deadline và đối soát
~~~

**Không thay request key khi retry.** Nếu dùng key mới, database không còn khả năng nhận diện đây là cùng một yêu cầu, nên có thể trừ tồn kho hoặc thu tiền lần nữa.

### 10.1. Vì sao “chưa thấy row” chưa chắc là chưa commit?

Một số khả năng:

- Transaction cũ vẫn đang chạy và chưa commit/rollback.
- Reader đang dùng replica trễ nên chưa thấy commit trên primary.
- Một lỗi connection/failover khiến nguồn đang đọc chưa phản ánh lịch sử vừa được ACK.
- Quy tắc phân vùng tenant, RLS hoặc read path sai khiến row bị che đi.
- Transaction thực sự rollback và row chưa từng tồn tại.

Vì thế phải chọn **nguồn đọc authoritative** và có giao thức giải quyết xung đột. Nếu một writer cũ vẫn có thể commit, việc chạy lại cùng key kèm UNIQUE trên **cùng authority** giúp ngăn hai request cùng commit. Nếu đã failover mà lịch sử commit trước đó bị mất, cần đối soát với hệ ngoài theo RPO; một constraint trên primary mới không thể tái tạo bằng chứng đã biến mất.

### 10.2. Outbox cho side effect ngoài DB

Nếu sau khi giữ hàng phải phát sự kiện, nên lưu outbox trong cùng transaction với request/stock:

~~~sql
CREATE TABLE reservation_outbox (
    event_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    request_key VARCHAR(120) NOT NULL,
    event_type  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, request_key, event_type)
);
~~~

Trong nhánh đặt thành công:

~~~sql
INSERT INTO reservation_outbox (
    tenant_id, request_key, event_type
)
VALUES (?, ?, 'StockReserved')
ON CONFLICT (tenant_id, request_key, event_type) DO NOTHING;
~~~

Điều kiện: lệnh tạo outbox phải chạy **trong cùng transaction** với đổi stock và trạng thái request. Nếu transaction rollback, không có event đã commit từ transaction đó. Nếu worker phát event rồi chết trước khi đánh dấu hoàn tất, nó có thể phát lại; consumer cần idempotency theo event ID hoặc business key.

Không gọi cổng thanh toán hoặc gửi email trực tiếp giữa hai UPDATE trong một transaction rồi giả định rollback DB sẽ thu hồi tác dụng phụ đã xảy ra.

## 11. Bài test đồng thời: lỗi kết nối kết hợp retry

Một lỗi kết nối hiếm gặp thường xuất hiện **khi nhiều request cùng tranh chấp**, vì vậy cần test có barrier và nhiều connection độc lập.

### 11.1. Hai caller dùng cùng key

~~~text
A: BEGIN -> INSERT key=K -> UPDATE stock -> chưa COMMIT
B: BEGIN -> INSERT key=K (có thể chờ UNIQUE)
A: COMMIT nhưng A không nhận ACK
B: ON CONFLICT xử lý key đã có
B: SELECT kết quả đã commit của K -> trả lại
~~~

Assertion:

- Có **chính xác một hàng** `reservation_requests` cho `(tenant_id, K)`.
- Stock chỉ giảm một lần.
- Nếu payload khác, request B nhận conflict, không được trả kết quả của A.
- Không có outbox/event/thanh toán trùng.
- Không có connection hoặc transaction bị bỏ quên.
- Có giới hạn thời gian chờ; test không treo mãi ở unique lock.

### 11.2. Một caller khác dùng key khác

Nếu hai request khác key nhưng cùng tranh chấp tồn kho, SQL conditional UPDATE phải bảo vệ `available >= 0`. Ví dụ còn một sản phẩm, hai request khác key cùng mua một đơn vị: chỉ một outcome `RESERVED`, outcome còn lại `REJECTED`.

Đây là bài toán concurrency khác với idempotency. **Khóa yêu cầu bảo vệ việc lặp một yêu cầu; conditional UPDATE bảo vệ bất biến tồn kho giữa những yêu cầu khác nhau.** Cần kiểm thử cả hai.

### 11.3. Lịch kiểm thử xác định

Dùng `CountDownLatch` hoặc một điểm chặn trong repository/proxy:

1. A ghi hàng `PENDING` và chuẩn bị COMMIT.
2. Giữ A tại điểm đã biết bằng hook hoặc cơ chế điều phối phù hợp.
3. B bắt đầu với cùng key.
4. Thả A để nó COMMIT; làm mất tín hiệu xác nhận với A.
5. Cho B hoàn thành sau khi DB xử lý xung đột.
6. Đọc trạng thái nguồn và kiểm tra số hàng/stock.
7. Lặp lại với nhánh A rollback trước COMMIT.
8. Bảo đảm cả hai nhánh đều có kết quả hợp lệ và không có ghi trùng.

Không chỉ dùng `Thread.sleep(20)` và hy vọng scheduler tạo lịch mong muốn. **Một test concurrency không ép được các bước quan trọng thì chưa chứng minh tình huống race**.

## 12. Lỗi phía database: crash, WAL và failover

### 12.1. Crash một PostgreSQL process khác với mất cả storage

Giả sử transaction đã COMMIT và WAL được flush theo chính sách durability cục bộ. Nếu PostgreSQL process crash rồi restart trên storage còn nguyên, cơ chế WAL recovery hướng tới việc giữ commit đã được bảo vệ.

Nhưng nếu client không nhận ACK do crash đúng giai đoạn commit, client không thể kết luận status chỉ từ `SQLException`. Test phải đọc lại sau khi DB phục hồi.

### 12.2. Failover sang standby có thể mất lịch sử đã ACK

Với asynchronous replication:

~~~text
Primary: COMMIT OK được gửi cho client
         |
         +-- WAL chưa tới standby
         |
         X primary hoặc cả vùng bị mất

Standby được promote có thể không chứa commit đã ACK
~~~

Đây là rủi ro **RPO/failover**, không phải lỗi idempotency riêng lẻ. Nếu primary mới không chứa request key cũ, retry trên primary mới có thể tạo một nghiệp vụ mới trong khi hệ ngoài đã xử lý side effect của giao dịch cũ.

Để kiểm thử:

- Xác định chính sách `synchronous_commit` và standby acknowledgement.
- Tạo probe/key có ACK độc lập.
- Tái hiện failover trong phòng lab với nguồn WAL/replica đã định.
- So sánh các request được ACK với trạng thái sau promotion.
- Kiểm tra outbox và đối tác ngoài.
- Không tự hứa “zero data loss” chỉ vì có standby.

### 12.3. Tránh đưa fault test thành test phá dữ liệu

- Không kill production database hoặc chặn production network chỉ để kiểm thử.
- Test failover trong môi trường cô lập, có backup và quyền phê duyệt.
- Không dùng credential production trong test.
- Không coi container stop là tương đương mọi kiểu power loss hoặc hỏng thiết bị lưu trữ.
- Giữ log timeline, DB version, replication mode, image và cấu hình cho mỗi kịch bản.
- Sau test, cleanup proxy/container/temp data; xác nhận không có service/queue thật nhận side effect.

## 13. Retry policy không được che mất nguyên nhân

Một cơ chế retry nên có:

| Thành phần | Quy tắc gợi ý |
| --- | --- |
| Phân loại lỗi | SQLSTATE, giai đoạn COMMIT và tính an toàn của operation |
| Phạm vi | Retry toàn transaction nếu `40001`/`40P01`, không chỉ UPDATE cuối |
| Số lượt | Giới hạn tổng attempts, bao gồm lần đầu |
| Deadline | Dừng nếu không còn thời gian cho retry + đối soát |
| Backoff | Exponential backoff kèm jitter để tránh retry storm |
| Cancellation | Tôn trọng thread interrupt, HTTP cancellation và job shutdown |
| Idempotency | Giữ nguyên tenant, request key và payload |
| Quan sát | Ghi số attempts và trạng thái `UNKNOWN`/`RESOLVED` |
| Khi không chắc | Trả trạng thái có thể tra cứu, không bịa thành công/thất bại |

Ví dụ retry ngay ba lần khi database thiếu connection có thể làm tải nặng hơn. Với connection pool, cần đo pool pending/active, thời gian chờ, transaction đang mở và số lần cấp lại connection.

### 13.1. Không tự retry mọi `SQLException`

- `23514` hoặc `23502`: dữ liệu sai, lặp lại không sửa được.
- `23505`: có thể là idempotency conflict; cần so khớp payload.
- `40001` hoặc `40P01`: thường retry **toàn transaction** sau rollback, nếu nghiệp vụ an toàn.
- `08xxx`: có thể phục hồi kết nối, nhưng ghi có thể chưa rõ trạng thái.
- `57014`: query bị hủy có thể do client chủ động cancel; không tự bật retry.
- Mất phản hồi COMMIT: **đối soát trước**, retry chỉ khi dùng cùng key và giao thức chống trùng.

Một test retry tốt khẳng định **số lần thực thi DB** và **số kết quả nghiệp vụ đã commit**, không chỉ tỷ lệ HTTP thành công.

## 14. Giám sát và bằng chứng sau sự cố

Khi điều tra một lỗi ghi, cần tái dựng timeline từ nhiều nguồn:

| Trường/thông tin | Mục đích |
| --- | --- |
| `request_key` / correlation ID | Ghép các lần thử cùng nghiệp vụ |
| Tenant và operation | Chặn đối soát nhầm dữ liệu |
| Giai đoạn lỗi: acquire/execute/commit/respond | Phân loại kết quả đã biết và unknown |
| SQLSTATE, exception chain | Tìm nguyên nhân kỹ thuật |
| Connection pool stats | Phát hiện hết slot, leak hoặc connection hỏng |
| Transaction start/commit attempt | Biết vị trí lỗi trong vòng đời |
| Database request row/status | Đối soát kết quả được commit |
| Inventory/ledger state | Xác nhận bất biến |
| Outbox/event delivery ID | Phát hiện side effect trùng hoặc mất |
| Replication lag/WAL position | Đánh giá rủi ro ở failover |
| Retry count, deadline, backoff | Phát hiện retry storm và bỏ qua deadline |
| Thời gian xử lý unknown | Đo chất lượng phục hồi nghiệp vụ |

**Không dùng log “executed SQL UPDATE” làm bằng chứng transaction đã commit.** Statement có thể chạy thành công rồi transaction rollback. Ngược lại, log “SQLException khi commit” không chứng minh commit chưa xảy ra.

Hạn chế log tham số nhạy cảm, mật khẩu, token, dữ liệu thanh toán hoặc dữ liệu tenant khác. Request key cần có quy tắc xử lý/retention phù hợp, không mặc nhiên coi mọi key có thể công khai.

### 14.1. Các trạng thái hữu ích cho API

Một API ghi có thể phân biệt:

- `CONFIRMED`: trạng thái nghiệp vụ đã được xác nhận theo hợp đồng.
- `REJECTED`: nghiệp vụ được xử lý, kết quả từ chối đã commit.
- `PENDING`: yêu cầu đã được tiếp nhận nhưng chưa có kết quả cuối.
- `UNKNOWN`: chưa đủ bằng chứng kết luận transaction đã commit hay chưa.
- `CONFLICT`: cùng key nhưng payload khác.

`HTTP 202 Accepted` thường phù hợp với “đã nhận để xử lý” hơn là “đã commit thành công”. Nếu trả lỗi kỹ thuật cho `UNKNOWN`, có thể kèm đường tra cứu kết quả; không bắt client tự tạo request key mới vì timeout.

## 15. Ma trận kiểm thử tổng hợp

| Kịch bản | Chèn lỗi | Kỳ vọng quan sát | Bất biến sau đối soát |
| --- | --- | --- | --- |
| Không lỗi | Không chèn | `RESERVED` hoặc `REJECTED` | Một request key, stock đúng |
| Connection acquisition lỗi | Datasource từ chối | Không mở transaction | Không có row mới |
| Lỗi sau UPDATE trước COMMIT | DB báo constraint error | Rollback | Stock và request không bị commit một nửa |
| Physical session đóng trước COMMIT | Đóng/cắt kết nối có xác nhận session kết thúc | SQL exception/rollback | Không có committed write mới |
| COMMIT thành công nhưng ACK bị giả lập mất | Hook commit thật rồi throw | `UNKNOWN` ở Java | Có row đã commit; retry cùng key không trừ nữa |
| HTTP response mất | Proxy HTTP chặn reply | Client timeout | DB có đúng một kết quả |
| Trùng key cùng payload | Retry sau timeout | Trả kết quả cũ | Không tăng số hàng/số lần trừ |
| Trùng key khác payload | Request bất hợp lệ | Conflict | Không sửa stock thêm |
| Hai key khác nhau tranh chấp một item | Hai transaction chạy song song | Một RESERVED, một REJECTED | Stock không âm |
| Cache/replica trễ | Đối soát trên replica chưa bắt kịp | Có thể không thấy row | Không kết luận sai là rollback |
| Deadlock/serialization | Hai transaction cùng tranh chấp | SQLSTATE phù hợp | Retry toàn transaction an toàn |
| Pool trả lại connection lỗi | Mất TCP và mượn lại | Pool thay/loại connection hỏng | Tenant/transaction state không rò |
| Post-commit crash trước event | Dừng sau COMMIT | Event worker có thể chưa phát | Outbox còn bản ghi hoặc có reconciliation |
| Async failover thiếu commit | Promote standby trễ trong lab | Có thể thiếu ACKed row | Đối soát RPO, external side effect |
| Retry storm | Nhiều caller mất kết nối | Backoff/deadline được áp | DB không bị tăng tải vô hạn |

Đối với mọi test, cần ghi cả **đường thành công** và **đường thất bại**, vì một service luôn từ chối tất cả yêu cầu có thể “không ghi sai dữ liệu” nhưng không đạt chức năng.

## 16. Bài tập thực hành

**Bài 1 — phân loại lỗi theo thời điểm.** Với A–E trong sơ đồ phần 1, hãy nêu mỗi lỗi có thể khiến Java biết transaction thất bại, biết thành công hay **chưa thể kết luận**. Trình bày vì sao timeout tại `COMMIT` khác pool acquisition timeout.

**Bài 2 — ghi dở dang.** Với bảng `inventory`, mở transaction, trừ stock rồi đóng physical connection trước commit. Dùng connection mới kiểm tra giá trị cũ. Lặp lại bằng một pooled connection và đánh giá sự khác nhau giữa đóng handle và cắt TCP.

**Bài 3 — lost COMMIT ACK.** Dùng `CommitAction` tiêm lỗi: COMMIT thật, sau đó ném `SQLTransientConnectionException`. Kiểm tra service báo `UNKNOWN`, database có hàng và retry cùng key không trừ stock lần hai.

**Bài 4 — phân biệt HTTP response loss.** Để service commit thành công nhưng chặn HTTP reply trước client. Client gọi lại cùng key. Vì sao service không nên chờ biết “client đã nhận response” rồi mới commit?

**Bài 5 — trùng key khác payload.** Lần đầu dùng `quantity=2`, lần sau cùng key dùng `quantity=3`. Chứng minh UNIQUE không đủ nếu không so khớp payload, và xác định response conflict hợp lệ.

**Bài 6 — cạnh tranh tồn kho.** Stock ban đầu bằng 1, hai request key khác nhau cùng đặt 1. Dùng latch và hai connection; kiểm tra chỉ một `RESERVED` và stock cuối bằng 0.

**Bài 7 — lỗi ở COMMIT do deferred constraint.** Tạo foreign key `DEFERRABLE INITIALLY DEFERRED`, cho INSERT tạm thời hợp lệ trong transaction nhưng thiếu parent tới COMMIT. Phân biệt lỗi DB từ chối COMMIT với lỗi không nhận được phản hồi COMMIT.

**Bài 8 — proxy mạng.** Thiết kế một thí nghiệm đặt proxy giữa JDBC và PostgreSQL, cắt traffic trước statement, trong lúc statement và khi chờ commit. Nêu bằng chứng cần thu để không nhầm mất ACK với transaction rollback.

**Bài 9 — outbox và thanh toán.** Trong transaction tạo order và outbox, sau COMMIT worker gọi cổng thanh toán rồi chết trước khi đánh dấu event đã xử lý. Thiết kế idempotency tại consumer/cổng thanh toán; kiểm tra phát lại không thu tiền hai lần.

**Bài 10 — failover và RPO.** Primary đã ACK một request nhưng standby async chưa nhận WAL. Khi standby được promote, request row có thể không tồn tại. Vì sao retry cùng key trên primary mới chưa đủ để chứng minh không có side effect cũ? Đề xuất kế hoạch đối soát với bản ghi độc lập.

**Bài 11 — deadlock và transaction state.** Tạo hai transaction khóa hai hàng theo thứ tự ngược nhau; quan sát `40P01`. Vì sao phải rollback và retry từ đầu? Test rằng một transaction không bị commit một nửa.

**Bài 12 — runbook kiểm thử.** Lập bảng gồm điểm chèn lỗi, công cụ, DB version, cấu hình timeout, evidence, assertion, cleanup và quyền môi trường. Định nghĩa tiêu chí pass cho safety, liveness và dữ liệu được phục hồi.

## 17. Những ngộ nhận cần tránh

**“Nếu Java thấy `SQLException` thì transaction chắc chắn rollback.”** Không đúng khi COMMIT có thể đã tới DB và phản hồi bị mất.

**“Gọi `rollback()` sau lỗi COMMIT sẽ thu hồi commit.”** Một commit đã hoàn tất không bị undo bởi rollback sau đó.

**“Mất socket sau UPDATE chứng minh UPDATE chưa chạy.”** UPDATE có thể đã thực thi trong transaction; cần phân biệt chạy SQL và commit.

**“Đóng pooled connection luôn giống cắt kết nối vật lý.”** Pool thường chỉ thu hồi handle; phải kiểm chứng semantics và cleanup của pool.

**“Tăng retry là đủ để khắc phục gián đoạn.”** Với ghi không idempotent, retry có thể nhân đôi tác dụng và gây thêm tải.

**“Unique request key là đủ cho mọi tình huống.”** Cần so khớp payload, transaction, authority, external side effect và chính sách failover.

**“Không thấy row trên replica nghĩa là commit thất bại.”** Replica có thể trễ, không phải nguồn đối soát mạnh nhất.

**“Test ném exception sau COMMIT chứng minh packet TCP bị mất.”** Nó chứng minh hành vi ở ranh giới ứng dụng; cần network proxy test riêng.

**“Test rollback là đủ cho lỗi COMMIT.”** Một test đóng trước COMMIT không tạo nhánh “DB commit thành công nhưng ACK mất”.

**“Synchronous replication tự giải quyết mọi lỗi RPO.”** Còn phụ thuộc mode ACK, failure domain, promotion và fencing.

**“Ghi outbox nghĩa là event phát đúng một lần.”** Worker/consumer có thể chạy lại; cần idempotent delivery.

**“Một SQL cập nhật stock có điều kiện thay thế idempotency.”** SQL bảo vệ stock không âm trước tranh chấp giữa các yêu cầu, nhưng không loại trừ cùng yêu cầu bị trừ hai lần ở hai thời điểm khác nhau nếu không có key.

**“Kiểm thử bằng một luồng là đủ.”** Race giữa request, backoff, pool và transaction cần kiểm thử song song có điều phối.

**“HTTP timeout là chứng minh server đã dừng.”** Service có thể vẫn xử lý sau khi client hết hạn.

## Ghi nhớ

**Trong persistence, lỗi kết nối là một vấn đề quan sát, không phải luôn là một kết luận về dữ liệu.** Một transaction chưa commit phải rollback khi session kết thúc; nhưng mất phản hồi ở giai đoạn COMMIT khiến client có thể không biết database đã commit hay chưa. Mất HTTP response lại là một trường hợp khác: DB có thể đã hoàn tất dù người dùng không thấy xác nhận.

Để kiểm thử đáng tin, cần **chèn lỗi theo từng giai đoạn**, đo SQLSTATE và timeline, xác minh dữ liệu cuối trên kết nối mới, giữ bất biến bằng transaction và conditional UPDATE, sử dụng `(tenant_id, request_key)` duy nhất cùng payload-check, và đối soát mọi kết quả `UNKNOWN`. Kết hợp test hook ổn định, PostgreSQL Testcontainers, proxy mạng và failover lab ở mức rủi ro phù hợp. Với ứng dụng Java, câu hỏi quan trọng không chỉ là “có retry được không?” mà là **“lặp yêu cầu này có giữ nguyên đúng một kết quả nghiệp vụ trong mọi lịch thực thi đã xét không?”**
