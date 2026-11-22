# Vì sao timeout không đồng nghĩa thao tác ghi chưa xảy ra

Ứng dụng Java gửi yêu cầu tạo đơn hàng, cập nhật số dư hoặc phát sự kiện. Sau vài giây, JDBC ném ngoại lệ timeout hoặc HTTP client nhận 504 Gateway Timeout. Người dùng hỏi: “Thao tác có thành công không?”. Một câu trả lời vội như “timeout nghĩa là chưa ghi” có thể khiến hệ thống thực hiện cùng nghiệp vụ **hai lần** khi thử lại.

**Timeout chỉ cho biết một bên đã ngừng chờ trước khi nhận được kết quả mong đợi. Nó không tự cho biết bên xử lý đã thực hiện, commit hay hoàn tất tác động hay chưa.** Yêu cầu có thể chưa tới máy chủ, đang chờ, đang xử lý, đã commit nhưng chưa gửi phản hồi, hoặc đã gửi phản hồi nhưng phản hồi bị mất.

Bài học thuộc chương **Lỗi và thử lại** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là hiểu tính bền vững và ranh giới giao dịch của persistence trong Java, xử lý lỗi kết nối, quyết định khi nào retry được và ngăn lặp các tác động nghiệp vụ quan trọng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt lỗi timeout với một kết quả xác định là đã thành công hoặc đã rollback.
- Chỉ ra các cửa sổ lỗi từ khi Java gửi lệnh SQL đến khi database commit và client nhận phản hồi.
- Giải thích vì sao mất ACK sau commit khiến **kết quả chưa rõ** dù server đã ghi dữ liệu.
- Phân biệt pool acquisition timeout, connection timeout, query timeout, lock timeout, transaction timeout và HTTP timeout.
- Nhận diện các thao tác có thể thử lại an toàn và những thao tác cần idempotency key hoặc kiểm tra trạng thái.
- Thiết kế ghi dữ liệu cùng bản ghi idempotency trong **một transaction DB**, có UNIQUE constraint để bảo vệ request gửi trùng.
- Phối hợp transaction, retry và reconciliation trong JDBC/Spring mà không làm lặp thanh toán, đơn hàng hay thông điệp.
- Kiểm chứng bằng fault injection tại các điểm lỗi thay vì dựa vào một lần thử may mắn.

## 2. Một lịch thực thi: server đã commit, client vẫn timeout

Giả sử client gửi POST /orders với nội dung mua một sản phẩm. API ghi vào PostgreSQL rồi trả mã đơn:

~~~text
Thời gian        Client Java                   Server / Database
    |
    |             POST /orders --------------> Nhận request
    |                                         BEGIN
    |                                         INSERT orders
    |                                         COMMIT thành công
    |                                         Chuẩn bị HTTP 201
    |             <---- phản hồi bị mất ---X--- gửi response
    |
    |             HTTP read timeout
    v
~~~

Client chỉ nhìn thấy exception. Nhưng **đơn hàng đã tồn tại**. Nếu client kết luận đơn chưa được tạo, sinh mã mới rồi gửi lại, người dùng có thể bị tạo hai đơn.

Tình huống tương tự xảy ra trực tiếp với JDBC:

~~~text
JDBC client                    PostgreSQL
     |                              |
     |--- INSERT/UPDATE ----------->|
     |<-- statement success --------|
     |--- COMMIT ------------------>|
     |                         commit được ghi nhận
     |<-- ACK COMMIT mất ---------X |
     |
SQLException / socket timeout
Kết quả commit: chưa rõ từ góc nhìn client
~~~

Một lời gọi commit() ném lỗi **không phải bằng chứng chắc chắn rằng rollback đã xảy ra**. Nếu database đã chốt COMMIT, việc gọi rollback() sau đó qua connection bị ngắt không thể đảo ngược quyết định đã commit.

### 2.1. Timeout là sự kiện của bên đợi

Một thao tác timeout thường được quyết định bởi **đồng hồ của bên gọi hoặc một tầng trung gian**:

- HTTP client ngừng chờ sau 3 giây.
- API gateway trả 504 vì upstream chưa phản hồi trong deadline.
- Pool ngừng đợi một connection rảnh.
- JDBC driver ngừng chờ đọc dữ liệu từ socket.
- Database hủy câu lệnh theo statement_timeout, nếu lệnh hủy được xử lý và kết quả được xác nhận.

Những sự kiện này có ý nghĩa khác nhau. Câu hỏi đúng là: **timeout xảy ra ở tầng nào, trước hay sau khi gửi gì, và server đã xác nhận mốc nào?**

## 3. Các mốc cần phân biệt khi ghi dữ liệu

| Mốc | Sự kiện | Có thể kết luận gì? |
|---|---|---|
| A | Java bắt đầu mượn Connection từ pool | Chưa nhất thiết có SQL nào được gửi |
| B | Java có Connection và gửi lệnh SQL | Yêu cầu có thể đang trên mạng hoặc đã đến DB |
| C | DB thực thi UPDATE/INSERT và trả kết quả statement | Câu lệnh thành công trong ngữ cảnh transaction hiện tại; nếu chưa commit, vẫn có thể rollback |
| D | Java gửi COMMIT | Không biết kết quả cho đến khi nhận xác nhận hoặc tra cứu trạng thái |
| E | DB ghi nhận COMMIT theo cấu hình | Thay đổi đã được commit theo bảo đảm DB hiện hành |
| F | DB gửi ACK COMMIT | ACK có thể chưa tới client |
| G | Client nhận ACK và trả kết quả HTTP | Client biết kết quả trong phạm vi hợp đồng API; dịch vụ khác chưa chắc đã hoàn tất |
| H | Replica, broker, hệ thanh toán hoặc backup có dữ liệu | Phải kiểm tra cam kết riêng của từng tài nguyên |

Một transaction có thể chứa nhiều statement. Kết quả executeUpdate() bằng 1 không bảo đảm transaction đã commit; EntityManager.flush() cũng không tự commit. Ngay cả khi COMMIT được xác nhận, bảo đảm tồn tại sau crash, failover hay mất cả vùng còn phụ thuộc WAL, fsync, synchronous replication, storage và chính sách khôi phục.

**Hai trường hợp khác nhau:**

- **Thất bại đã biết:** database xác nhận transaction bị rollback hoặc trả lỗi serialization và transaction đã được abort. Có thể cân nhắc retry toàn bộ transaction theo chính sách.
- **Kết quả chưa rõ (ambiguous outcome):** kết nối/ACK mất đúng thời điểm có thể đã commit. Không biết chắc thao tác xảy ra hay chưa; cần xác minh hoặc gửi lại một yêu cầu **có idempotency**.

Việc phân loại phải dựa trên tín hiệu thật từ DB/driver; không được suy “bất kỳ SQLException nào cũng là rollback” hoặc “bất kỳ timeout nào cũng là commit”.

## 4. Cửa sổ lỗi chi tiết

Giả sử một transaction tạo đơn và ghi audit:

~~~sql
BEGIN;

INSERT INTO orders(id, customer_id, status)
VALUES ('af22e912-ecaf-42ce-9b0f-58246073ec31', 101, 'PENDING');

INSERT INTO order_audit(order_id, action)
VALUES ('af22e912-ecaf-42ce-9b0f-58246073ec31', 'CREATED');

COMMIT;
~~~

Các thời điểm mất kết nối có ý nghĩa khác nhau:

| Điểm xảy ra lỗi | Trạng thái có thể có | Hướng xử lý |
|---|---|---|
| Chưa mượn được connection | Chưa có lệnh SQL của operation này đi qua handle đó | Có thể thử mượn lại, nhưng vẫn xét request/attempt khác cùng nghiệp vụ |
| Mạng lỗi trước khi DB nhận SQL | DB có thể chưa làm gì; client thường không chứng minh được chính xác điểm thất bại nếu dữ liệu đã rời tiến trình | Không lặp một thao tác không có định danh an toàn |
| INSERT đã thành công, transaction vẫn mở | DB có thay đổi chưa commit; nếu transaction bị hủy thì rollback | Không trả lời “đã tạo đơn” chỉ từ số hàng UPDATE |
| DB báo lỗi SQL và transaction bị abort | Thường chưa có commit của transaction này; phải kết thúc transaction đúng cách | Chỉ retry khi lỗi thuộc nhóm có thể retry |
| Mất kết nối khi gửi COMMIT | Commit có thể đã xảy ra hoặc chưa | Tra cứu qua business key; retry với cùng idempotency key |
| DB commit xong nhưng ACK mất | Dữ liệu đã commit mà client không biết | Trả kết quả đã có khi yêu cầu được gửi lại |
| ACK tới API nhưng HTTP response tới người dùng bị mất | API biết thành công, người dùng chưa biết | GET trạng thái hoặc retry cùng key, không tạo thao tác khác |
| Primary mất sau ACK, replica bất đồng bộ chưa nhận | Bản ghi có thể không tồn tại trên primary mới | Đánh giá cam kết failover/RPO; không nhầm với chỉ lỗi timeout |

Với lệnh ghi có tác động bên ngoài như thanh toán hoặc gửi email, phạm vi trở nên rộng hơn: rollback database không hoàn tác được giao dịch đã được hệ thống ngoài chấp nhận.

### 4.1. Retry câu lệnh khác retry toàn bộ transaction

Nếu một lệnh UPDATE chưa commit trong transaction đã thất bại, có thể phải rollback toàn transaction rồi tạo transaction mới. Đừng gửi lại riêng câu UPDATE trên connection đang ở trạng thái lỗi, vì dữ liệu dùng để ra quyết định trước đó có thể đã cũ.

Nếu **COMMIT outcome chưa rõ**, tự động bắt exception rồi tạo transaction mới làm lại toàn bộ nghiệp vụ với ID mới càng nguy hiểm: lần đầu có thể đã commit. Phải có lớp bảo vệ trùng lặp.

## 5. Cùng một từ “timeout” nhưng khác tầng kỹ thuật

| Timeout | Đang chờ điều gì? | Có chứng minh thao tác ghi chưa xảy ra không? |
|---|---|---|
| **Pool acquisition timeout** | Chờ một connection rảnh | Nếu chưa mượn được connection và chưa gửi thao tác nào qua nó thì operation đó chưa chạy SQL trên handle đó; không nói gì về attempt khác |
| **Connection establishment timeout** | Kết nối TCP, TLS, authentication hoặc handshake | Có thể chưa mở phiên DB hữu dụng; vẫn cần xác định chính xác thành phần nào bị timeout |
| **JDBC socket/read timeout** | Chờ dữ liệu từ DB trên connection | **Không.** DB có thể đã xử lý hoặc commit rồi phản hồi bị mất |
| **Statement/query timeout** | Giới hạn thời gian chạy statement theo driver/server | Nếu server xác nhận hủy thì có bằng chứng về statement đó; không suy kết quả của các hành động khác |
| **Lock timeout** | Chờ row/table lock quá lâu | Phải xem transaction bị abort hay chỉ statement lỗi theo DBMS; không đồng nghĩa toàn workflow được rollback |
| **Transaction timeout** | Transaction vượt deadline của framework/DB | Cần xác nhận framework thực sự đã rollback và thời điểm commit; external side effect không tự được hoàn tác |
| **HTTP connect timeout** | Kết nối tới API khác | Không đủ để kết luận về một lần gọi khác hoặc retry trước đó |
| **HTTP read timeout / 504** | Chờ upstream trả response | **Không.** Upstream có thể đã commit và chỉ chậm hoặc mất response |
| **Message broker send timeout** | Chờ ACK publish | **Không.** Broker có thể đã nhận message nhưng producer chưa thấy xác nhận |

### 5.1. PostgreSQL statement_timeout không giống mất ACK COMMIT

Ví dụ:

~~~sql
SET LOCAL statement_timeout = '2s';
UPDATE inventory
SET available = available - 1
WHERE sku = 'A' AND available > 0;
~~~

SET LOCAL có ý nghĩa khi dùng bên trong transaction thích hợp; ngưỡng cụ thể chỉ để minh họa. Nếu PostgreSQL trả lỗi hủy statement với SQLSTATE 57014 và transaction bị đưa vào trạng thái aborted, ứng dụng cần rollback transaction đó trước khi dùng lại.

Tuy nhiên, **một lần socket timeout trước khi nhận được lỗi từ PostgreSQL không chứng minh lệnh đã bị hủy**. Client có thể timeout trong lúc server đang chạy, sau khi lệnh đã hoàn tất, hoặc đúng lúc commit. Cần phân loại dựa trên phản hồi đã xác nhận, không chỉ tên class của exception.

### 5.2. HTTP client timeout không hủy transaction DB từ xa

Một API gateway trả 504 không tự gửi lệnh ROLLBACK tới database của upstream. Upstream có thể tiếp tục chạy sau khi client đóng kết nối, tùy framework, cơ chế cancellation và trạng thái request. Ngay cả khi upstream nhận tín hiệu hủy, việc xử lý hủy cũng có thể xảy ra sau một side effect đã commit.

Vì vậy, endpoint ghi cần **giao thức nhận diện yêu cầu lặp lại** chứ không chỉ điều chỉnh timeout lên cao hơn.

## 6. Những thao tác nào an toàn để thử lại?

| Loại thao tác | Ví dụ | Retry đơn giản có an toàn không? |
|---|---|---|
| Truy vấn chỉ đọc không có side effect | SELECT dữ liệu thông thường | Thường an toàn về tác động ghi, nhưng cần đánh giá tính nhất quán và chi phí |
| Ghi với business key UNIQUE | Tạo đơn với order_request_id cố định | Có thể retry cùng key nếu thiết kế trả lại kết quả cũ và kiểm tra payload |
| Cập nhật đặt trạng thái cố định | SET status='CANCELLED' | Có thể idempotent về giá trị cuối nhưng cần kiểm tra chuyển trạng thái, version và side effect kèm theo |
| Tăng bộ đếm | SET counter=counter+1 | **Không**, nếu gửi lại sẽ tăng thêm |
| Trừ tiền / chuyển tiền | UPDATE balance=balance-amount | **Không**, phải có định danh yêu cầu bền vững và kiểm tra trùng |
| Tạo bản ghi với ID ngẫu nhiên mới mỗi lần | INSERT order mới | **Không**, có thể sinh hai order |
| Gửi email | sendEmail | Có thể gửi trùng; rollback DB không thu hồi email |
| Publish event | broker.publish(OrderCreated) | Broker có thể nhận rồi mất ACK; cần message ID/consumer idempotent |

**Idempotent** nghĩa là xử lý lại *cùng một yêu cầu nghiệp vụ* không tạo thêm tác động không mong muốn. Nó không chỉ là “SQL viết giống nhau”. Một câu SET status có thể idempotent ở một cột, nhưng nếu mỗi lần chạy lại phát email hoặc tính phí, toàn bộ workflow không idempotent.

### 6.1. Retry được phép ≠ retry ngay lập tức

Ngay cả với thao tác idempotent, vẫn phải có giới hạn số lần thử, backoff có jitter, deadline, giới hạn đồng thời và quan sát. Retry hàng loạt khi DB đang quá tải có thể làm lỗi lan rộng. Không retry lỗi dữ liệu sai, thiếu quyền, vi phạm bất biến nghiệp vụ hay xung đột payload của cùng key.

## 7. Idempotency key: định danh một ý định nghiệp vụ

Khi người dùng nhấn “Tạo đơn” một lần, ứng dụng tạo **một idempotency key ổn định**. Nếu request timeout và được gửi lại, **giữ nguyên key đó**. Chỉ tạo key mới cho một ý định kinh doanh mới.

Ví dụ:

~~~text
POST /orders
Idempotency-Key: 4837d91b-635b-4114-a281-c68a76eb2b27

body = { customerId: 101, sku: "A", quantity: 2 }
~~~

Server cần bảo đảm:

1. Key có phạm vi rõ, chẳng hạn tenant_id cùng request_key, không dùng chung mù quáng giữa khách hàng.
2. Key và kết quả nghiệp vụ được lưu **bền vững**, không chỉ trong RAM của một instance.
3. Có ràng buộc UNIQUE/PRIMARY KEY để hai request đồng thời cùng key không cùng tạo tác động.
4. Lưu dấu vết payload hoặc hash của dữ liệu chuẩn hóa; **cùng key nhưng khác nội dung phải bị từ chối**.
5. Bản ghi nhận diện yêu cầu phải được commit **cùng transaction** với thay đổi DB mà nó bảo vệ, nếu dùng cùng một database.
6. Một lần replay trả về kết quả đã ghi, hoặc trạng thái đang xử lý/chưa rõ theo hợp đồng API.
7. Có chính sách retention key phù hợp thời gian client có thể retry và mức rủi ro; không dọn key quá sớm rồi cho phép tạo lại tác động cũ.

Chỉ đặt key ở HTTP header mà không có UNIQUE constraint hoặc transaction bền vững ở database **không tạo ra idempotency**.

### 7.1. Dùng business identifier thay vì UUID mới cho mỗi lần thử

Một lỗi điển hình:

~~~java
// Sai: mỗi lần retry sinh một ID mới.
for (int attempt = 0; attempt < 3; attempt++) {
    UUID orderId = UUID.randomUUID();
    tryCreateOrder(orderId);
}
~~~

Nếu attempt đầu đã commit nhưng mất ACK, attempt kế tiếp tạo thêm một đơn.

Đúng hơn là tạo requestKey một lần cho ý định nghiệp vụ và **tái sử dụng**:

~~~java
UUID requestKey = command.requestKey(); // Ổn định qua retry.
for (int attempt = 0; attempt < maxAttempts; attempt++) {
    try {
        return orderClient.create(command, requestKey);
    } catch (RetryableTransportException ex) {
        // Backoff có jitter, giữ nguyên requestKey và cùng payload.
        // Server phải hỗ trợ idempotency bằng dữ liệu bền vững.
    }
}
throw new RetryExhaustedException("Result needs reconciliation");
~~~

Code chỉ mô tả phương pháp. Không phải mọi RetryableTransportException đều bảo đảm một lần gửi có thể replay tùy ý; chính **hợp đồng idempotency ở phía xử lý** mới khiến việc gửi lại an toàn.

## 8. Thiết kế idempotent ở PostgreSQL: ghi key và tác động trong cùng transaction

Ví dụ một nghiệp vụ chuyển tiền nội bộ giữa hai tài khoản trong cùng PostgreSQL. Đây là tình huống cần bảo vệ đặc biệt vì retry không có idempotency có thể trừ tiền nhiều lần.

Bảng tối giản:

~~~sql
CREATE TABLE accounts (
    tenant_id bigint NOT NULL,
    id bigint NOT NULL,
    balance numeric(18, 2) NOT NULL CHECK (balance >= 0),
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE transfer_requests (
    tenant_id bigint NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    transfer_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, request_key),
    UNIQUE (tenant_id, transfer_id)
);

CREATE TABLE transfers (
    tenant_id bigint NOT NULL,
    id uuid NOT NULL,
    from_account_id bigint NOT NULL,
    to_account_id bigint NOT NULL,
    amount numeric(18, 2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
~~~

Trong ví dụ này, request_hash là dấu vết của **nội dung nghiệp vụ đã chuẩn hóa** (tenant, tài khoản gửi/nhận, số tiền, đơn vị tiền, loại thao tác). Để tránh cùng key được dùng cho yêu cầu khác, hệ thống phải đối chiếu nội dung một cách đáng tin cậy; có thể lưu cả dữ liệu chuẩn hóa hoặc một hash mật mã phù hợp. Các cột, loại tiền và ràng buộc trong schema thật cần được thiết kế đầy đủ hơn.

### 8.1. Thuật toán một transaction

~~~text
Nhận tenantId, requestKey, nội dung chuyển tiền đã được xác thực
        |
        v
BEGIN
        |
        v
INSERT transfer_requests(tenantId, requestKey, hash, transferId)
ON CONFLICT (tenant_id, request_key) DO NOTHING
        |
        +-- Đã tồn tại key?
        |       |
        |       +-- Có: đọc bản ghi, so sánh nội dung request
        |                    |
        |                    +-- Khác nội dung: báo xung đột
        |                    +-- Giống: trả transferId gốc
        |
        +-- Chưa tồn tại:
                |
                +-- UPDATE trừ tiền có điều kiện đủ số dư
                +-- UPDATE cộng tiền người nhận
                +-- INSERT transfers
                |
                v
             COMMIT
                |
                v
             Trả kết quả
~~~

**Điểm mấu chốt:** bản ghi transfer_requests và tất cả thay đổi số dư được commit **trong cùng transaction của cùng database**. Nếu trừ tiền thất bại, rollback cũng xóa bản ghi idempotency chưa commit; một attempt khác cùng key vẫn có thể xử lý. Nếu commit thành công rồi phản hồi mất, bản ghi idempotency và các thay đổi tiền cùng tồn tại để retry lần sau tìm lại.

### 8.2. Ví dụ Java với Spring JdbcTemplate

Giả sử sử dụng PostgreSQL, Spring transaction manager của cùng DataSource và một command đã được validate: số tiền lớn hơn 0, tài khoản nguồn khác tài khoản đích, thông tin tenant hợp lệ và requestHash ổn định qua mọi lần thử.

~~~java
public record TransferCommand(
        long tenantId,
        UUID requestKey,
        String requestHash,
        long fromAccountId,
        long toAccountId,
        BigDecimal amount
) {}

public record StoredTransferRequest(String requestHash, UUID transferId) {}

@Service
public class TransferTransactionService {
    private final JdbcTemplate jdbc;

    public TransferTransactionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public UUID transfer(TransferCommand command) {
        UUID proposedTransferId = UUID.randomUUID();

        int inserted = jdbc.update(
            """
            INSERT INTO transfer_requests
                (tenant_id, request_key, request_hash, transfer_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tenant_id, request_key) DO NOTHING
            """,
            command.tenantId(),
            command.requestKey(),
            command.requestHash(),
            proposedTransferId
        );

        if (inserted == 0) {
            StoredTransferRequest previous = jdbc.queryForObject(
                """
                SELECT request_hash, transfer_id
                FROM transfer_requests
                WHERE tenant_id = ? AND request_key = ?
                """,
                (rs, rowNumber) -> new StoredTransferRequest(
                    rs.getString("request_hash"),
                    rs.getObject("transfer_id", UUID.class)
                ),
                command.tenantId(),
                command.requestKey()
            );

            if (previous == null ||
                    !previous.requestHash().equals(command.requestHash())) {
                throw new IllegalArgumentException(
                    "Idempotency key belongs to a different request"
                );
            }
            return previous.transferId();
        }

        int debited = jdbc.update(
            """
            UPDATE accounts
            SET balance = balance - ?
            WHERE tenant_id = ? AND id = ? AND balance >= ?
            """,
            command.amount(), command.tenantId(),
            command.fromAccountId(), command.amount()
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source account missing or insufficient funds"
            );
        }

        int credited = jdbc.update(
            """
            UPDATE accounts
            SET balance = balance + ?
            WHERE tenant_id = ? AND id = ?
            """,
            command.amount(), command.tenantId(), command.toAccountId()
        );
        if (credited != 1) {
            throw new IllegalStateException("Target account missing");
        }

        jdbc.update(
            """
            INSERT INTO transfers
                (tenant_id, id, from_account_id, to_account_id, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            command.tenantId(), proposedTransferId,
            command.fromAccountId(), command.toAccountId(), command.amount()
        );

        return proposedTransferId;
    }
}
~~~

Mã minh họa cơ chế chính, chưa phải một dịch vụ chuyển tiền hoàn chỉnh: cần xử lý quản trị tài khoản, đồng thời khác chiều chuyển tiền, quota, audit, chống gian lận, deadline và các ràng buộc kế toán thích hợp. Ví dụ sử dụng PostgreSQL với READ COMMITTED và requestHash đã chuẩn hóa. Các transaction có thể chờ nhau ở UNIQUE constraint hoặc row lock; phát sinh deadlock/serialization failure thì cần retry có giới hạn theo loại lỗi.

**Vì sao không chỉ làm SELECT kiểm tra key trước rồi INSERT?** Hai request cùng đến có thể đều thấy chưa có key. UNIQUE constraint mới là điểm chặn việc hai transaction cùng commit một key. Với PostgreSQL, một INSERT ON CONFLICT có thể phải chờ giao dịch đang ghi key trùng; sau khi conflict đã commit, truy vấn SELECT sau đó trong READ COMMITTED có thể thấy bản ghi đã commit.

Đối với request dùng cùng key nhưng payload khác, API nên trả lỗi xung đột rõ ràng, thường là HTTP 409 theo hợp đồng. Không tiếp tục thực thi lệnh với thông số mới.

### 8.3. Vẫn có thể timeout ở bước COMMIT

Với method @Transactional tạo transaction mới qua Spring proxy, phần thân method có thể return transferId cho proxy **trước khi** proxy thực hiện commit. Nếu commit bị mất kết nối, caller có thể nhận exception thay vì giá trị trả về dù dữ liệu đã được commit.

Không nên bắt exception bên trong transaction rồi gọi lại các UPDATE. Để transaction manager kết thúc/giải phóng connection, sau đó một tầng điều phối bên ngoài quyết định tra cứu hoặc retry bằng **cùng requestKey**.

Ví dụ chính sách ở tầng API:

~~~text
Gửi transfer(R, payload P)
    |
    +-- Xác nhận thành công: trả transferId
    |
    +-- Xác nhận business error: trả lỗi nghiệp vụ, không retry vô điều kiện
    |
    +-- Kết quả chưa rõ (network/commit timeout):
          |
          +-- Mượn connection mới khi DB sẵn sàng
          +-- Tìm transfer_requests theo (tenantId, R) trên primary
          |      |
          |      +-- Tồn tại, hash khớp: trả transferId đã lưu
          |      +-- Tồn tại, hash khác: từ chối xung đột
          |      +-- Chưa tồn tại: có thể attempt cũ chưa kết thúc
          |
          +-- Retry transfer(R, P) theo backoff và deadline
                 UNIQUE + transaction chung bảo vệ khỏi commit trùng
~~~

Một lần đọc “chưa tìm thấy” **không chứng minh chắc chắn** transaction cũ đã rollback: nó có thể còn đang xử lý hoặc chưa commit. Vì vậy retry phải giữ **cùng key** và được bảo vệ ở database; không chỉ dựa vào việc SELECT trả về rỗng.

### 8.4. Giới hạn của bảo đảm

Mẫu trên chặn việc nhiều attempt **cùng key** cùng commit nhiều transfer trong một database với các ràng buộc phù hợp. Nhưng:

- Không ngăn hai idempotency key khác nhau cho cùng ý định kinh doanh nếu client sinh key mới.
- Không tự đảm bảo an toàn cho API thanh toán bên ngoài nếu service đó không hỗ trợ idempotency.
- Không giúp phát hiện một client gian lận cố ý gửi thao tác khác; cần xác thực/ủy quyền.
- Không duy trì chứng cứ retry nếu bản ghi idempotency bị xóa sớm hoặc mất do khôi phục từ replica/backup chưa có commit đó.
- Không bảo đảm exactly-once delivery của email/message broker; cần cơ chế riêng.

## 9. Phân biệt lỗi có thể retry từ kết quả commit chưa rõ

Không nên có một catch SQLException rồi retry tất cả mọi lỗi. Trong PostgreSQL, có những mã lỗi giúp phân loại, nhưng phải kiểm tra câu lệnh, trạng thái transaction và tầng chuyển đổi exception thực tế.

| Tín hiệu | Ý nghĩa thường gặp | Chính sách phù hợp |
|---|---|---|
| **40001** serialization_failure | Một transaction bị từ chối vì xung đột tuần tự hóa | Retry **toàn bộ transaction** trên snapshot/trạng thái mới, có backoff |
| **40P01** deadlock_detected | DB chọn một transaction làm nạn nhân deadlock | Retry toàn transaction nếu thao tác an toàn và còn budget |
| **23505** unique_violation | Vi phạm ràng buộc UNIQUE | Thường là kết quả nghiệp vụ hoặc dấu hiệu duplicate; đọc lại/so sánh key, không retry mù |
| **23514** check_violation | Vi phạm CHECK | Thường là dữ liệu/luật nghiệp vụ sai, không retry |
| **57014** query_canceled | Statement bị hủy theo tín hiệu server (có thể do statement_timeout) | Đánh giá transaction đã aborted, rollback khi cần; không suy toàn workflow chưa có tác động |
| **08xxx** connection_exception | Vấn đề đường kết nối/giao thức | Có thể kết quả chưa rõ, đặc biệt ở commit; xác minh bằng business key |
| HTTP 502/503/504 hoặc read timeout | Gateway/upstream không trả kết quả bình thường | Không suy remote rollback; retry theo contract idempotency |
| Broker publish timeout | Producer không nhận ACK đúng hạn | Broker có thể đã nhận; retry cùng message ID, consumer idempotent |

Bảng áp dụng theo ví dụ PostgreSQL và cách driver/framework báo lỗi. Một exception class Java không phải lúc nào cũng ánh xạ một-một với SQLSTATE; trong Spring có thể cần đi theo cause chain và xác minh log/trace để phân loại.

**Lưu ý trọng yếu:** trường hợp transaction bị PostgreSQL abort với 40001 khác với mất phản hồi khi COMMIT. Với 40001 đã xác nhận, transaction không commit; với lỗi mạng ở COMMIT, trạng thái có thể chưa rõ. Logic retry không được coi hai loại này như nhau.

## 10. Backoff, retry budget và tránh bão thử lại

Nếu 1.000 request cùng gặp timeout rồi lập tức retry ba lần, hệ thống có thể nhận 3.000 request bổ sung khi database đang yếu. Retry phải được điều tiết:

- **Giới hạn attempt:** ví dụ vài lần thử có kiểm soát thay vì vòng lặp vô hạn.
- **Exponential backoff có jitter:** phân tán thời điểm retry giữa nhiều client.
- **Deadline toàn nghiệp vụ:** không kéo dài retry quá thời gian còn hữu ích.
- **Giới hạn concurrency:** không để retry chiếm hết connection pool hoặc thread.
- **Retry theo loại lỗi:** 40001, deadlock hoặc lỗi mạng tạm thời có thể phù hợp; lỗi quyền truy cập, dữ liệu không hợp lệ và business conflict thường không.
- **Giữ nguyên key/payload:** không đổi idempotency key khi thử lại cùng ý định.
- **Reconciliation:** khi hết budget nhưng vẫn chưa biết kết quả, lưu trạng thái cần đối soát thay vì tự tuyên bố thất bại.

Một lần retry thành công không nhất thiết nghĩa attempt trước thất bại. Nó có thể chỉ là replay tìm lại kết quả đã commit của attempt trước.

## 11. Timeout khi gọi tài nguyên bên ngoài

Một local transaction bảo vệ các câu SQL trong một database, nhưng không tự bao phủ HTTP, message broker, email hay object storage. Nếu ứng dụng gọi những tài nguyên ấy, trạng thái chưa rõ có thể xuất hiện ở **mỗi ranh giới**.

### 11.1. API thanh toán: timeout sau khi bị trừ tiền

~~~text
Order Service                 Payment Provider
      |                              |
      |---- Charge(paymentKey=P) --->|
      |                         Ghi nhận/capture tiền
      |<----- phản hồi mất ------X----|
      |
   Timeout
      |
      +-- Nếu gọi charge bằng P2: có thể bị trừ lần nữa
      +-- Nếu tra cứu theo P và retry cùng P theo contract:
          có thể trả kết quả cũ mà không charge trùng
~~~

Đối với nhà cung cấp thanh toán:

1. Sử dụng định danh yêu cầu thanh toán ổn định trong phạm vi nhà cung cấp hỗ trợ.
2. Lưu paymentKey và trạng thái nghiệp vụ vào database của mình.
3. Nếu timeout, chuyển sang trạng thái **UNKNOWN / RECONCILING** theo hợp đồng hệ thống; không tự coi là FAILED.
4. Gọi API truy vấn trạng thái, xử lý webhook đã xác thực hoặc đối soát dữ liệu để xác định kết quả.
5. Nếu cần gửi lại charge, kiểm tra chính sách idempotency, thời hạn giữ key và semantics của nhà cung cấp.
6. Chỉ chuyển order sang PAID hoặc FAILED khi có bằng chứng phù hợp.

Ngay cả khi HTTP request có idempotency key, không thể tự suy nhà cung cấp giữ key mãi mãi hoặc ngăn mọi tác dụng phụ; phải đọc và kiểm thử **contract của API đó**.

### 11.2. Broker đã nhận message nhưng ACK bị mất

~~~text
Producer                 Message broker                  Consumer
   |                           |                             |
   |--- publish(eventId=E) --->| lưu message                  |
   |<------ ACK mất -------X---|                             |
   |        timeout            |--- giao E ----------------->|
   |--- publish(E) lần nữa --->|--- giao E lần nữa ---------->|
~~~

Nếu producer không nhận ACK, nó có thể gửi lại E. Nếu consumer thực hiện cập nhật DB rồi chết trước khi ACK đã xử lý, E cũng có thể được giao lại. Vì vậy, đối với hệ thống truyền thông điệp ít nhất một lần (**at-least-once**), consumer phải idempotent theo eventId và business key.

Ví dụ bảng đánh dấu event đã xử lý:

~~~sql
CREATE TABLE processed_messages (
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer nên ghi processed_messages và thay đổi nghiệp vụ của nó trong **cùng local transaction**. Nếu transaction thất bại, cả hai rollback để lần giao lại có thể thử xử lý. Nếu transaction đã commit rồi ACK mất, lần giao lại gặp bản ghi xử lý trùng và không lặp tác động.

Đây là bảo vệ ở **tài nguyên của consumer**, không có nghĩa broker hay database thực thi exactly-once trên toàn hệ thống.

### 11.3. Database đã commit nhưng publish chưa xảy ra

Một ứng dụng tạo order rồi gọi broker.publish có thể gặp:

~~~text
DB COMMIT thành công
      |
process crash trước publish
      |
Consumer không biết có order mới
~~~

Ngược lại, publish trước DB COMMIT có thể phát event về order chưa commit hoặc sẽ rollback. **Transactional outbox** giúp ghi order và intent phát event trong cùng DB transaction. Một dispatcher phát sau commit và retry khi mất ACK; consumer vẫn cần chống trùng.

Timeout không chỉ là câu chuyện retry trên một SQL; đôi khi cần tái thiết kế **ranh giới nhất quán** để đảm bảo các bước nghiệp vụ không bị mất.

## 12. Trạng thái nghiệp vụ cần thể hiện “chưa rõ”

Một API ghi an toàn nên có trạng thái trung gian khi không thể trả kết quả dứt khoát.

~~~mermaid
flowchart TD
    A["Client gửi requestKey R"] --> B["Đang xử lý"]
    B -->|Commit đã được xác nhận| C["COMPLETED"]
    B -->|Lỗi nghiệp vụ đã biết| D["REJECTED"]
    B -->|Mất kết nối / mất ACK| E["UNKNOWN / RECONCILING"]
    E --> F["Tra cứu theo R trên nguồn authoritative"]
    F -->|Có kết quả hợp lệ| C
    F -->|Đã xác nhận thất bại| D
    F -->|Vẫn chưa rõ| G["Retry cùng R / theo dõi tiếp"]
    G --> F
~~~

**UNKNOWN không tương đương FAILED.** Khi kết quả còn chưa rõ, cách diễn đạt “yêu cầu đang được kiểm tra” đúng hơn “không có thay đổi nào được ghi”.

Một hợp đồng API bất đồng bộ có thể dùng:

~~~text
POST /transfers
Idempotency-Key: R

202 Accepted
{
  "requestId": "R",
  "status": "PROCESSING",
  "statusUrl": "/transfers/requests/R"
}

GET /transfers/requests/R

200 OK
{
  "requestId": "R",
  "status": "COMPLETED",
  "transferId": "T"
}
~~~

Đây là ví dụ contract minh họa; chỉ trả HTTP 202 nếu workflow thực sự được nhận để xử lý bất đồng bộ và có nơi tra cứu được. Một API đồng bộ có thể trả 201/200 sau commit thành công và vẫn hỗ trợ idempotent replay. Khi API thực sự chưa thể xác định trạng thái, không nên trả “đã thất bại chắc chắn” chỉ vì HTTP response quá hạn.

**Lưu ý khi tra cứu:** đọc từ replica bất đồng bộ có thể trả dữ liệu cũ dù primary đã commit. Với nghiệp vụ cần xác minh một ambiguous commit, ưu tiên nguồn authoritative/primary hoặc một cơ chế đọc có consistency phù hợp. Nếu đang chuyển đổi primary sau failover, phải đánh giá replication và RPO, vì bản ghi idempotency cũng có thể mất nếu commit chưa nằm trên replica được promote.

## 13. JDBC và Spring: đặt retry ở đúng tầng

### 13.1. Một transaction tự quản lý bằng JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        performAllDatabaseWrites(connection, command);
        connection.commit();
        // Commit đã được DB xác nhận theo cấu hình hiện hành.
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        // Nếu lỗi xảy ra tại COMMIT do mất kết nối:
        // rollback ở đây KHÔNG chứng minh commit chưa xảy ra.
        throw ex;
    }
}
~~~

Khi code bắt exception, cần ghi lại **giai đoạn xảy ra lỗi**: lúc mượn connection, lúc chạy SELECT/UPDATE, lúc COMMIT, hoặc sau COMMIT trong quá trình trả response. Nếu không ghi nhận giai đoạn, rất khó quyết định retry.

Với transaction tự quản lý, một nỗ lực retry phải mượn connection mới nếu kết nối cũ bị lỗi, làm lại toàn bộ kiểm tra và ghi. Trước khi chạy lại nghiệp vụ có khả năng đã commit, đảm bảo nó idempotent bằng dữ liệu DB bền vững.

### 13.2. Spring proxy có thể commit sau khi method return

~~~java
@Service
public class OrderTransactionService {
    private final OrderRepository repository;

    public OrderTransactionService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public UUID createOrder(UUID requestKey, CreateOrderCommand command) {
        // Repository ghi idempotency key và order trong cùng DB transaction.
        return repository.insertOrFindOrder(requestKey, command);
    }
}
~~~

Khi proxy mở transaction mới, thân method trả về giá trị rồi transaction manager mới COMMIT. Nếu COMMIT thất bại hoặc ACK bị mất, caller có thể nhận exception dù method đã tạo được order trong database.

Do đó:

- Retry ở tầng **ngoài** method @Transactional, sau khi Spring đã kết thúc attempt hiện tại.
- Mỗi attempt mới phải đi qua proxy để tạo transaction mới; self-invocation bằng this.method() thường không kích hoạt proxy theo cách mong đợi.
- Nếu method chỉ tham gia transaction bên ngoài (propagation REQUIRED), nó chưa commit khi method return; cần đặt retry ở ranh giới thực sự sở hữu commit.
- Với serialization failure được xác nhận, rollback rồi retry **toàn bộ transaction**, bao gồm các bước đọc và quyết định.
- Với lỗi mạng ở COMMIT, dùng requestKey ổn định để **tìm kết quả cũ hoặc replay idempotent**, không kết luận lần đầu đã rollback.

Nếu cần một lớp retry dựa trên annotation hoặc thư viện, phải đảm bảo thứ tự proxy của retry và transaction: **mỗi lần retry có transaction riêng**, không vô tình chạy nhiều attempt trong một transaction đã thất bại.

### 13.3. Exception translation không thay cho phân tích trạng thái

Spring có thể chuyển SQLException thành các lớp DataAccessException. Việc phân loại lỗi retryable bằng class là hữu ích, nhưng cần xác nhận cách driver PostgreSQL, transaction manager và Spring version ánh xạ từng SQLSTATE.

Không dùng một catch (Exception ex) rộng rồi retry ba lần bất kể lỗi. Nó có thể lặp vô ích với password sai, quyền thiếu, CHECK violation, payload xung đột, hoặc trường hợp commit đã thành công.

## 14. Quan sát và ghi log để phân biệt timeout với kết quả nghiệp vụ

Khi phân tích sự cố, nên lưu những trường đủ để truy vết mà không phơi lộ dữ liệu nhạy cảm:

| Dữ liệu quan sát | Mục đích |
|---|---|
| requestId/idempotencyKey, tenantId | Nối nhiều attempt của cùng ý định nghiệp vụ |
| operation/transferId/orderId | Tìm kết quả đã được commit |
| attempt_number | Biết có bao nhiêu lần thử |
| stage (acquire, execute, commit, respond) | Xác định timeout tại bước nào |
| SQLSTATE hoặc error category | Phân biệt serialization, constraint, connection và cancellation |
| request_deadline, query_timeout, pool_timeout | Đối chiếu deadline giữa các tầng |
| transaction_duration, commit_latency | Tìm transaction dài và nghẽn |
| outcome (confirmed, rejected, unknown, reconciled) | Tránh đánh đồng mất ACK với rollback |
| retry_count, reconciliation_backlog | Theo dõi mức tải bổ sung và công việc chưa rõ |
| pool_active/pending, DB lock waits | Phát hiện timeout do cạn tài nguyên hoặc chờ khóa |

Không log số thẻ, mật khẩu, token, toàn bộ payload chứa dữ liệu cá nhân hoặc connection string có secret. Hash và business key cũng phải được quản lý theo yêu cầu bảo mật tương ứng.

Một metric “timeout_count” đơn lẻ rất khó điều tra. Cần tách timeout khi mượn connection, timeout câu lệnh, HTTP read timeout và mất phản hồi tại commit. Tỷ lệ **UNKNOWN kéo dài** hay số request cần đối soát cũng quan trọng không kém độ trễ p95/p99.

## 15. Thực hành: fault injection ở các cửa sổ lỗi

Kiểm thử chức năng đơn luồng chỉ kiểm tra đường thành công sẽ bỏ sót phần lớn lỗi do mất phản hồi. Trên môi trường thử nghiệm độc lập có database và dữ liệu đại diện, chủ động tạo các kịch bản sau:

| Kịch bản | Cách kiểm chứng | Kết quả mong muốn |
|---|---|---|
| Timeout trước khi mượn connection | Giới hạn pool và giữ các handle đang bận | Không tạo tác động mới ở attempt đó; API báo đúng tầng lỗi |
| Lỗi statement trước COMMIT | Cố ý vi phạm constraint trong transaction | Transaction rollback, không lưu bản ghi nghiệp vụ dở dang |
| Lỗi serialization 40001 | Ép hai transaction có xung đột phù hợp | Attempt bị abort được retry toàn bộ, vẫn giữ bất biến |
| Mất ACK ngay sau DB COMMIT | Fault injection tại proxy mạng sau khi DB xác nhận commit | Client nhận lỗi, nhưng retry cùng key trả lại kết quả cũ |
| Client timeout nhưng server còn chạy | Ngắt HTTP response trong lúc DB tiếp tục thực thi | Server không tạo hai nghiệp vụ khi client replay |
| Hai request cùng key chạy đồng thời | Dùng barrier trước phần chèn idempotency | UNIQUE/transaction chỉ cho một tác động được commit |
| Cùng key, payload khác | Gửi R với P1 rồi R với P2 | Request thứ hai bị từ chối, dữ liệu cũ giữ nguyên |
| Broker nhận message nhưng mất ACK | Ngắt ACK sau khi broker lưu message | Producer retry cùng event ID; consumer không lặp side effect |
| Primary failover với replica trễ | Thử trong cụm staging được kiểm soát | Báo cáo rõ RPO, rủi ro dữ liệu chưa nằm trên primary mới |
| Reconciliation tạm thời không truy cập DB | Tạm ngắt kết nối tra cứu | Giữ trạng thái UNKNOWN, tiếp tục kiểm tra có giới hạn |

Khi thử mất ACK ngay sau COMMIT, cần công cụ cho phép chặn response tại điểm kiểm soát; không phải cứ ngắt socket ngẫu nhiên là chứng minh đã rơi vào đúng cửa sổ lỗi. Xác minh trực tiếp database authoritative để biết effect đã commit trong bài test.

**Các assertion quan trọng:** cùng một requestKey chỉ có tối đa một tác động nghiệp vụ đã commit; payload khác bị từ chối; kết quả replay nhất quán; tài nguyên JDBC được hoàn trả; không có lệnh gửi bên ngoài bị lặp ngoài mức hợp đồng chấp nhận.

## 16. Bài tập tự kiểm tra

### Bài A — Timeout ở HTTP 504

Người dùng nhấn “Đặt hàng”. API gateway trả 504, nhưng database đã commit order. Ứng dụng di động tự tạo orderId mới rồi gửi lại.

**Câu hỏi:** Rủi ro gì xảy ra và cần sửa client/server thế nào?

**Gợi ý:** Hai đơn có thể được tạo. Client giữ cùng requestKey qua retry; server lưu key và order trong một DB transaction có UNIQUE constraint, trả kết quả đã lưu khi replay.

### Bài B — executeUpdate trả 1

Trong transaction autoCommit=false, executeUpdate() trả về 1. Sau đó COMMIT thất bại vì kết nối bị ngắt.

**Câu hỏi:** Có thể nói “bản ghi chắc chắn chưa commit” không?

**Gợi ý:** Không. Thành công statement chưa chứng minh commit, còn lỗi mạng ở commit tạo kết quả chưa rõ. Dùng business key và đối soát; không gọi lại với ID mới.

### Bài C — SQLSTATE 40001 và socket timeout

Một transaction bị PostgreSQL báo serialization_failure 40001. Một transaction khác bị mất socket đúng lúc COMMIT.

**Câu hỏi:** Hai lỗi có cùng chính sách retry không?

**Gợi ý:** 40001 đã xác nhận transaction bị abort; retry toàn transaction có kiểm soát. Mất ACK ở COMMIT có thể đã thành công; cần idempotency/reconciliation trước hoặc trong quá trình replay cùng key.

### Bài D — Mượn connection bị timeout

Pool có 10 connection, tất cả đang bận. getConnection() của request mới timeout, chưa nhận Connection.

**Câu hỏi:** Có thể nói thao tác ghi của request mới chưa được gửi qua handle đó không? Có thể suy các attempt trước chưa ghi không?

**Gợi ý:** Request mới chưa mượn được handle để chạy SQL qua nó; nhưng không nói gì về attempt khác cùng ý định có thể đã commit. Cần nhìn idempotency key và timeline nhiều attempt.

### Bài E — Publish event nhận timeout

Producer gửi OrderCreated với eventId E; broker nhận E nhưng ACK mất. Producer retry và consumer nhận E hai lần.

**Câu hỏi:** Chặn lặp ở đâu?

**Gợi ý:** Giữ eventId qua retry và dùng processed_messages có PRIMARY KEY theo consumer/eventId trong cùng transaction với thay đổi nghiệp vụ. Nếu cần phát event từ DB, dùng transactional outbox để chống mất intent sau commit.

### Bài F — Cùng key nhưng khác payload

Client gửi requestKey R chuyển 100.000, sau timeout gửi lại R nhưng đổi số tiền thành 200.000.

**Câu hỏi:** Server phải làm gì?

**Gợi ý:** Từ chối xung đột key/payload; không coi là retry hợp lệ. Lưu bản ghi đã chuẩn hóa hoặc hash xác thực để đối chiếu.

### Bài G — Kiểm tra trên replica

Primary đã commit transaction và ACK mất. API tra cứu trên replica bất đồng bộ và không thấy order, rồi kết luận rollback.

**Câu hỏi:** Kết luận sai ở đâu?

**Gợi ý:** Replica có thể đang trễ; cần đọc primary hoặc cơ chế consistency có bảo đảm. Nếu primary đã mất và failover sang replica trễ, còn phải xét mục tiêu RPO và durability policy.

## 17. Checklist thiết kế xử lý timeout và retry

- [ ] Phân biệt timeout ở pool, connect, statement, lock, transaction, HTTP và broker.
- [ ] Không suy timeout hoặc SQLException đồng nghĩa thao tác ghi chắc chắn chưa xảy ra.
- [ ] Biết lệnh đang ở trước, trong hay sau transaction COMMIT.
- [ ] Không suy executeUpdate/flush thành công đồng nghĩa COMMIT đã thành công.
- [ ] Dùng idempotency key ổn định cho một ý định nghiệp vụ qua mọi lần thử.
- [ ] Key có phạm vi tenant/actor phù hợp và đi kèm so khớp payload.
- [ ] Có UNIQUE/PRIMARY KEY cưỡng chế, không chỉ SELECT trước INSERT.
- [ ] Bản ghi idempotency và tác động DB commit nguyên tử khi nằm cùng database.
- [ ] Khi kết quả commit chưa rõ, tra cứu trạng thái từ nguồn authoritative; replay vẫn cùng key.
- [ ] Retry toàn transaction sau serialization/deadlock được xác nhận; không retry lỗi nghiệp vụ mù quáng.
- [ ] Có backoff, jitter, budget, deadline và giới hạn đồng thời.
- [ ] Không lặp side effect ngoài DB khi retry transaction; dùng key của hệ ngoài, outbox hoặc compensation phù hợp.
- [ ] Client/API có trạng thái UNKNOWN/PROCESSING và cơ chế reconciliation.
- [ ] Đã tính đến lag của replica, failover và phạm vi độ bền dữ liệu.
- [ ] Có log/metric theo requestId, stage, attempt và outcome, tránh lộ dữ liệu nhạy cảm.
- [ ] Đã kiểm thử mất ACK sau commit, replay đồng thời, xung đột key và xử lý trùng thông điệp.

**Ghi nhớ:** timeout là **giới hạn thời gian chờ của một thành phần**, còn việc dữ liệu đã được ghi và commit hay chưa là **trạng thái của hệ thống xử lý**. Hai sự kiện có thể không trùng nhau. Một thiết kế persistence đáng tin cậy trong Java phải xử lý khả năng đã commit nhưng mất xác nhận bằng **idempotency bền vững, truy vấn đối soát và retry đúng ranh giới giao dịch**.
