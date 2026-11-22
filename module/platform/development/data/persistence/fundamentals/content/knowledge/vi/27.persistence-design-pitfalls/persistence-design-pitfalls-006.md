# Thử lại thao tác ghi không lũy đẳng sau mọi timeout

Trong chương **Lỗi thiết kế** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một lỗi đặc biệt nguy hiểm là **cứ gặp timeout thì thực hiện lại thao tác ghi như một yêu cầu mới**. Với Java/JDBC, HTTP client, message consumer hoặc một dịch vụ thanh toán, timeout thường chỉ chứng minh rằng **bên gọi không nhận được kết quả trong thời gian cho phép**; nó không chứng minh database hoặc dịch vụ phía nhận chưa thực thi tác vụ.

Nếu thao tác có tác dụng cộng dồn hoặc tạo thực thể mới — trừ tiền, đặt hàng, tăng tồn kho, phát hành hóa đơn, gửi yêu cầu hoàn tiền — lần thử thứ hai có thể tạo **tác dụng phụ thứ hai**. Một transaction ACID trong database bảo vệ việc commit cục bộ, nhưng **không bảo đảm caller biết commit đã xảy ra** khi mạng hoặc tiến trình bị lỗi vào đúng thời điểm trả phản hồi.

Bài này phân biệt **retry**, **idempotency (lũy đẳng)**, **kết quả ghi chưa rõ** và **đối soát**; đồng thời hướng dẫn đặt ranh giới persistence an toàn trong Java bằng PostgreSQL, JDBC/Spring, ràng buộc `UNIQUE`, thao tác có điều kiện và transactional outbox. Mục tiêu không phải “không retry”, mà là **chỉ retry theo một giao thức không làm nghiệp vụ xảy ra hai lần**.

## 1. Một timeout có thể che giấu một lần ghi đã thành công

Giả sử khách hàng yêu cầu chuyển 500.000 đồng. Ứng dụng gửi lệnh ghi tới dịch vụ tài khoản:

```text
Thời gian       Java / Client                Database / Service
-----------------------------------------------------------------------
T0              send transfer(X, 500000) --> nhận lệnh X
T1                                              kiểm tra điều kiện
T2                                              ghi debit/credit
T3                                              COMMIT thành công
T4              <----- phản hồi bị mất ----X     gửi response
T5              timeout sau 3 giây
T6              retry transfer(Y, 500000) --> nhận lệnh mới Y
T7                                              ghi debit/credit lần 2
T8                                              COMMIT lần 2
-----------------------------------------------------------------------
Kết quả: caller chỉ muốn chuyển một lần, DB đã có hai lần chuyển.
```

Nếu ứng dụng cấp một ID mới `Y` cho lần retry, database có thể coi đó là **một giao dịch nghiệp vụ hoàn toàn mới**. Dù cả hai lần ghi riêng lẻ đều đúng ACID, kết quả tổng thể vẫn sai ý định khách hàng.

**Câu hỏi cốt lõi:** Sau timeout, hệ thống có bằng chứng *chưa thực hiện* hay chỉ có sự thật *chưa nhận được xác nhận*? Nếu chỉ chưa nhận ACK, trạng thái phải được coi là **chưa xác định (unknown/indeterminate)** cho đến khi có cách đối soát đáng tin.

## 2. Phân biệt bốn loại kết quả mà caller quan sát

| Caller quan sát | Có thể kết luận? | Cách xử lý cần xem xét |
| --- | --- | --- |
| Phản hồi thành công có hợp đồng rõ | Bên nhận đã xác nhận kết quả theo hợp đồng API/DB. | Lưu kết quả và tiếp tục, không phát lại ý định. |
| Từ chối nghiệp vụ xác định (ví dụ không đủ số dư) | Thao tác không được chấp nhận theo kết quả authoritative, nếu hợp đồng bảo đảm. | Trả kết quả từ chối; không tự đổi thành thành công. |
| Timeout, mất kết nối, không nhận phản hồi | **Không biết chắc** thao tác đã xảy ra hay chưa. | Đối soát bằng operation ID; nếu retry thì giữ cùng ID và có cơ chế lũy đẳng. |
| Lỗi validation trước khi gửi yêu cầu | Có thể khẳng định chưa gửi **nếu đường gọi thật sự dừng trước khi có side effect**. | Sửa yêu cầu; không coi đây là lỗi hạ tầng cần retry. |

Tương tự, HTTP 500 có thể phát sinh **sau** khi database đã commit (ví dụ serialize response lỗi). HTTP 502/504 tại gateway có thể do gateway mất kết nối với service upstream đã xử lý xong. Một mã trạng thái HTTP **không tự chứng minh** hệ thống phía sau chưa có side effect.

Với JDBC, `SQLException` do connection mất trong lúc `commit()` có thể có trạng thái không rõ. Không được suy từ mọi exception rằng Spring hoặc PostgreSQL chắc chắn đã rollback.

## 3. Lũy đẳng là thuộc tính của tác dụng nghiệp vụ, không phải của việc gọi lại API

Một thao tác **lũy đẳng** khi thực hiện nó một hoặc nhiều lần theo cùng ý định cho ra **tác dụng được bảo vệ** như chỉ thực hiện một lần, trong phạm vi hợp đồng đã định. Viết khái quát:

\[
f(f(s, x), x) = f(s, x)
\]

Trong đó `s` là trạng thái ban đầu và `x` là **cùng một ý định đã được định danh**. Biểu thức này nói về tác dụng chính yếu; metadata như số lần truy cập, timestamp quan sát hoặc log kỹ thuật có thể vẫn tăng và cần chính sách riêng.

| Ví dụ | Lũy đẳng theo mặc định? | Điều kiện để retry an toàn |
| --- | --- | --- |
| `SET status = 'CANCELLED'` | Có thể lũy đẳng về giá trị cột, nhưng không chắc mọi side effect. | State guard, không phát email/hoàn tiền mỗi lần. |
| `UPDATE balance = balance - 100` | **Không**. | Operation ID duy nhất và ledger/transaction chống trùng. |
| `UPDATE inventory SET available = available - 1` | **Không**. | Idempotency key + reservation và điều kiện tồn kho. |
| `INSERT INTO orders ...` với ID tự sinh mỗi lần | **Không**. | Stable request ID hoặc order ID với unique constraint. |
| `INSERT ... ON CONFLICT DO NOTHING` | Có thể tránh trùng **theo khóa conflict được chọn**. | Khóa phải đại diện cho ý định nghiệp vụ và phải so payload. |
| `DELETE WHERE id = ?` | Có thể lũy đẳng về sự vắng mặt của hàng. | Xét trigger, audit, event, cascade và điều kiện authorization. |
| Gửi email “Đã đặt hàng” | Không thể thu hồi email đã nhận. | Hạn chế lặp theo message ID và chọn semantics giao hàng rõ. |
| HTTP `PUT` | Theo semantics thường hướng tới tính lũy đẳng. | Implementation vẫn phải kiểm soát side effect và concurrency. |
| HTTP `POST` | Không mặc nhiên lũy đẳng. | Hợp đồng `Idempotency-Key` hoặc định danh nghiệp vụ ổn định. |

Không nên phân loại “câu SQL này lũy đẳng” chỉ bằng cách nhìn động từ HTTP hoặc cú pháp `UPSERT`. Cần xét **tác dụng nghiệp vụ trọn vẹn**: ghi hàng, phát event, lập hóa đơn, gọi payment provider, cập nhật audit và phản hồi người dùng.

## 4. Những cửa sổ lỗi giữa request, transaction và response

Một lệnh ghi thường đi qua nhiều chặng:

```text
[A] Caller tạo operation ID
         |
[B] Gửi request qua mạng
         |
[C] Service xác thực/validate
         |
[D] DB BEGIN / ghi dữ liệu
         |
[E] DB COMMIT
         |
[F] Service tạo HTTP/message response
         |
[G] Caller nhận ACK
```

| Chặng gặp lỗi | Điều caller có thể biết | Nguy cơ nếu tự tạo lệnh mới |
| --- | --- | --- |
| Trước B, chắc chắn chưa gửi | Chưa có yêu cầu phía nhận. | Chủ yếu lỗi input/local; có thể gửi lần đầu sau sửa. |
| B–C, mạng mất | Không biết bên nhận đã nhận chưa. | Tác vụ có thể đã bắt đầu. |
| D, DB rollback xác định | Chưa có commit của transaction đó. | Các tác dụng phụ **ngoài DB** có thể vẫn xảy ra nếu thiết kế sai. |
| E, ACK commit bị mất | DB **có thể đã commit**. | Ghi hai lần nếu retry thành ý định mới. |
| F–G, response bị mất | DB và service có thể đã hoàn tất. | Lặp nghiệp vụ dù chính giao dịch đầu tiên thành công. |

Trong distributed systems, trạng thái **không xác định** không phải ngoại lệ hiếm có thể bỏ qua; nó là hậu quả tự nhiên của việc hai tiến trình không thể luôn phân biệt một node đã xử lý xong với node chưa xử lý nhưng chậm trả lời.

Một service không nên biến mọi timeout thành `FAILED`. Cần có `PENDING/UNKNOWN` và đường đối soát với nguồn dữ liệu có thẩm quyền (*source of truth*).

## 5. Chỉ retry khi biết lớp lỗi và thao tác có thể chịu lặp

Không phải mọi lỗi persistence đều là lỗi tạm thời. Một số ví dụ:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Validation/domain | Quantity âm, không được phép mua, dữ liệu thiếu. | Từ chối xác định, không retry y nguyên. |
| Unique violation | Trùng request ID hoặc khóa nghiệp vụ. | Tìm operation cũ và so payload; không tự kết luận retry an toàn cho mọi unique error. |
| Deadlock/serialization | PostgreSQL SQLSTATE `40P01` / `40001`. | Có thể retry **toàn bộ transaction** với giới hạn nếu operation an toàn/idempotent. |
| Network timeout khi request đã gửi | ACK không về. | Kết quả chưa rõ; đối soát, giữ nguyên operation ID. |
| Connection acquisition timeout | Pool không cho mượn connection. | Nếu chắc chưa gửi SQL thì chưa ghi ở DB trên đường này; điều tiết tải và retry có giới hạn. |
| Statement timeout/cancel | Câu SQL bị ngắt theo engine/config. | Xem trạng thái transaction và tác dụng ngoài DB; không suy rộng sang mọi lệnh cùng workflow. |
| Check constraint/foreign key violation | Dữ liệu vi phạm ràng buộc. | Thường là lỗi xác định cho payload hiện tại; sửa nghiệp vụ. |
| Mất ACK từ payment provider | Provider có thể đã thu tiền. | Tra cứu trạng thái bằng provider operation key, không thu tiền lại bằng ID mới. |
| Mất kết nối lúc commit | Không biết commit local đã được xác nhận ở caller chưa. | Reconnect và đối soát trên primary bằng idempotency/operation ID. |

Các lỗi SQLSTATE cụ thể là tín hiệu hữu ích nhưng **không tự quyết định ngữ nghĩa nghiệp vụ**. Với PostgreSQL, `40001` thường yêu cầu chạy lại cả transaction vì snapshot trước không còn hợp lệ; retry riêng statement cuối có thể dùng dữ liệu đã đọc từ một snapshot cũ và gây sai. Với unique violation `23505`, cần xét constraint nào bị vi phạm và nó đại diện cho điều kiện gì.

**Một chính sách “catch mọi `SQLException` rồi retry ba lần” là sai thiết kế** nếu chưa phân biệt đường gửi, trạng thái commit và tính lũy đẳng.

## 6. Ví dụ chống mẫu: retry tạo hai đơn hàng

Một API đơn giản:

```java
// Ví dụ SAI: cố ý minh họa anti-pattern.
public UUID submitOrder(OrderRequest request) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            // Mỗi lần lại cấp orderId mới.
            UUID orderId = UUID.randomUUID();
            return orderRepository.create(orderId, request);
        } catch (DatabaseTimeoutException timeout) {
            // Không biết lần vừa rồi đã commit hay chưa.
            // Lại thử với orderId mới.
        }
    }
    throw new IllegalStateException("Could not create order");
}
```

Nếu lần đầu đã commit nhưng ACK mất, lần hai dùng ID mới sẽ tạo một đơn khác. Ngay cả khi dùng Hibernate và `@Transactional`, transaction chỉ ràng buộc ghi cục bộ; nó không đảm bảo câu lệnh trả thành công tới HTTP client.

Một biến thể nguy hiểm:

```sql
-- Caller retry vô điều kiện:
UPDATE accounts
SET balance_cents = balance_cents - 50000
WHERE account_id = :account_id;
```

Câu `UPDATE` có thể hoàn toàn nguyên tử **mỗi lần** nhưng không lũy đẳng **khi lặp**. Nếu caller không có ID đại diện cùng ý định chuyển tiền, database không biết hai lần trừ thực chất là một yêu cầu.

Thay vì cố tìm cách “chặn timeout”, cần thiết kế **một định danh ổn định cho ý định nghiệp vụ**, kiểm soát tác dụng phụ một lần và cung cấp đường tra cứu kết quả.

## 7. Định danh ý định nghiệp vụ khác attempt ID và message ID

Để retry an toàn, hãy tách bốn loại ID:

| Định danh | Đại diện cho | Khi retry |
| --- | --- | --- |
| `requestId` / `idempotencyKey` | **Một ý định nghiệp vụ**: tạo đơn cụ thể, chuyển tiền cụ thể. | **Giữ nguyên** qua mọi lần gửi lại cùng ý định. |
| `operationId` | Một hiệu ứng cụ thể trong workflow, như charge lần đầu hoặc refund. | **Giữ nguyên** nếu thực sự là cùng hiệu ứng. |
| `attemptId` | Một lượt mạng/DB execution để debug. | Có thể **thay đổi** mỗi lượt. |
| `eventId` | Một bản tin được phát/truyền. | Có thể cùng hoặc khác ID tùy nguồn; không thay thế khóa nghiệp vụ. |
| `traceId` | Theo dõi đường đi request. | Có thể thay đổi theo lượt; không dùng làm bảo đảm chống trùng. |

Ví dụ:

```text
HTTP requestId = ORDER-REQUEST-123
        |
        +-- attempt 1 (HTTP timeout)
        +-- attempt 2 (retry)
        +-- attempt 3 (poll status)

Cùng requestId phải dẫn tới cùng ý định và cùng kết quả đã chốt.
Không tạo một orderId/paymentOperationId mới chỉ vì attempt tăng.
```

**Khóa lũy đẳng cần có phạm vi:** service nào, tenant nào, loại thao tác nào, đôi khi tài khoản hoặc resource nào. Ví dụ `UNIQUE(tenant_id, operation_type, idempotency_key)`. Không tái sử dụng cùng một key cho **hai ý định hợp lệ khác nhau**.

### Không tin vào UUID nếu không có ràng buộc

UUID ngẫu nhiên đủ khó trùng trong thực hành phù hợp, nhưng **bản thân UUID không ngăn tác dụng lặp** nếu code luôn tạo UUID mới trong mỗi retry hoặc database không cưỡng chế unique. Tính đúng đắn cần đến từ **giao thức và constraint tại nguồn có thẩm quyền**, không chỉ từ định dạng chuỗi.

## 8. Cùng key nhưng payload khác: phải phát hiện xung đột

Giả sử client gửi:

```text
Idempotency-Key: 7a1f...
Body: { "sku": "BOOK-1", "quantity": 2 }

Retry sai:
Idempotency-Key: 7a1f...
Body: { "sku": "BOOK-1", "quantity": 5 }
```

Nếu chỉ dùng key để trả kết quả cũ, client có thể tưởng đơn 5 sản phẩm đã được chấp nhận trong khi database chỉ giữ 2. Nếu cho phép key cũ điều khiển payload mới, lại phá hợp đồng lũy đẳng.

**Chính sách phổ biến:** với cùng phạm vi key, ghi một **fingerprint/canonical hash** của những tham số có ý nghĩa nghiệp vụ. Khi trùng key:

- **Fingerprint khớp:** trả trạng thái/kết quả đã ghi; không áp dụng lại side effect.
- **Fingerprint khác:** trả lỗi xung đột rõ ràng, ví dụ HTTP 409 theo hợp đồng.
- **Ý định còn đang xử lý:** trả `PENDING`/HTTP 202 hoặc 409 theo API đã định; cung cấp đường theo dõi.

Fingerprint không nên chỉ hash raw JSON nếu hai JSON khác thứ tự key hoặc biểu diễn số nhưng mang cùng ý nghĩa. Cần định nghĩa **chuẩn hóa có version**: identity/tenant, SKU, số lượng, đơn vị tiền, currency, phương thức thanh toán, đối tượng nhận và chính sách làm tròn. Tránh bỏ sót tham số làm thay đổi tác dụng nghiệp vụ. Với dữ liệu nhạy cảm, không lưu plaintext token/thông tin thẻ trong bảng idempotency.

## 9. Nguồn có thẩm quyền: không suy kết quả từ cache miss hoặc replica lag

Khi gặp timeout, ứng dụng có thể cố tra cứu:

```text
GET /operations/ORDER-REQUEST-123
  |
  +-- Database primary: có kết quả SUCCEEDED
  +-- Read replica: chưa bắt kịp WAL, không thấy bản ghi
  +-- Redis: key đã bị evict, không thấy giá trị
```

**Không thấy bản ghi ở cache/replica không chứng minh giao dịch chưa commit** ở primary. Nếu dùng replica lag để quyết định tạo lệnh mới, có thể tạo trùng tác dụng.

Một đường đối soát an toàn cần được thiết kế với **nguồn có thẩm quyền** cho operation ID: bảng kết quả giao dịch trên primary, ledger thanh toán, hoặc API trạng thái của provider có hợp đồng rõ ràng. Khi nguồn đó không sẵn sàng, có thể phải **giữ trạng thái UNKNOWN** và tránh một lệnh mới có tác dụng không lũy đẳng.

Trong hệ thống có failover, “primary mới” vẫn cần xét bảo đảm durability/replication. Dữ liệu đã được ACK bởi primary cũ nhưng chưa đồng bộ sang node lên thay có thể là tình huống cần giao thức đối soát theo RPO và kiến trúc; không thể xử lý đơn giản chỉ bằng việc đọc lại một replica.

## 10. Thiết kế operation ledger chống trùng tại PostgreSQL

Để một thao tác ghi trong **một database** có kết quả ổn định, có thể dùng bảng lưu **ý định + kết quả** trong cùng transaction với dữ liệu nghiệp vụ.

Ví dụ:

```sql
CREATE TABLE operation_results (
    tenant_id        UUID NOT NULL,
    idempotency_key  UUID NOT NULL,
    operation_type   TEXT NOT NULL,
    payload_hash     TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (
        status IN ('SUCCEEDED', 'REJECTED')
    ),
    result_payload   JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);

CREATE TABLE inventory (
    tenant_id UUID NOT NULL,
    sku       TEXT NOT NULL,
    available INTEGER NOT NULL CHECK (available >= 0),
    active    BOOLEAN NOT NULL DEFAULT TRUE,
    version   BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, sku)
);

CREATE TABLE reservations (
    reservation_id UUID PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    idempotency_key UUID NOT NULL,
    sku            TEXT NOT NULL,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    FOREIGN KEY (tenant_id, sku)
        REFERENCES inventory(tenant_id, sku),
    UNIQUE (tenant_id, idempotency_key)
);
```

Trong thiết kế này, `operation_results` chỉ lưu **kết quả cuối của thao tác cục bộ**. Hàng được chèn với trạng thái placeholder trong **transaction chưa commit** và phải được cập nhật thành `SUCCEEDED` hoặc `REJECTED` **trước khi commit**; không công bố trạng thái chưa hoàn tất. Nếu lỗi bất ngờ khiến transaction rollback, không có hàng kết quả được lưu.

**Không nên dùng riêng `UNIQUE(idempotency_key)` trên toàn cluster** nếu hai tenant có thể tạo key trùng hợp lệ. Mặt khác, đừng để chính client tự chọn `tenant_id` mà không qua authentication/authorization. Constraint là hàng rào chống trùng **theo phạm vi đã chọn**, còn quyền truy cập cần được bảo vệ độc lập.

### Tại sao lưu kết quả từ chối?

Ví dụ request giữ 4 sản phẩm nhưng tồn kho chỉ còn 3. Nếu hệ thống **không lưu kết quả từ chối** và client retry cùng key khi có đợt nhập hàng mới, lần retry có thể đột ngột thành công. Điều đó có thể trái hợp đồng “một request chỉ được quyết định một lần”.

Một lựa chọn là lưu `REJECTED` như kết quả cuối với lý do nghiệp vụ. Khi client muốn thử lại sau khi tình hình thay đổi, client phát **một ý định mới với key mới**. Chính sách khác cũng có thể hợp lệ, nhưng phải được định nghĩa rõ thay vì để việc TTL/khả năng retry quyết định ngẫu nhiên.

## 11. Ghi ý định, điều kiện nghiệp vụ và kết quả trong một local transaction

Một luồng PostgreSQL an toàn về mặt **atomicity và deduplication local**:

```text
BEGIN transaction
  1. INSERT operation_results với khóa duy nhất
     ON CONFLICT DO NOTHING RETURNING ...
  2. Nếu không tạo được:
        SELECT kết quả đã commit của cùng khóa
        kiểm tra payload_hash và trạng thái
        KHÔNG cập nhật inventory lần nữa
  3. Nếu là request mới:
        UPDATE inventory với điều kiện available >= quantity
        nếu UPDATE 1 row:
            INSERT reservation
            UPDATE operation_results thành SUCCEEDED
        nếu UPDATE 0 row:
            UPDATE operation_results thành REJECTED
  4. COMMIT cả dữ liệu nghiệp vụ và kết quả idempotency
```

Các câu SQL minh họa dưới đây dùng placeholder named parameter; với JDBC thuần phải dùng `?` hoặc thư viện bind tương ứng:

```sql
BEGIN;

-- Bước 1: một transaction tranh quyền thực hiện operation mới.
-- Hàng chưa commit của transaction khác sẽ được xử lý theo
-- ràng buộc unique/khả năng chờ của PostgreSQL.
INSERT INTO operation_results (
    tenant_id, idempotency_key, operation_type,
    payload_hash, status, result_payload
)
VALUES (
    :tenant_id, :idempotency_key, 'RESERVE_STOCK',
    :payload_hash, 'REJECTED', '{}'::jsonb
)
ON CONFLICT (tenant_id, operation_type, idempotency_key)
DO NOTHING
RETURNING idempotency_key;

-- Nếu câu INSERT trả 0 hàng, KHÔNG chạy UPDATE sau đây.
-- Đọc hàng cũ bằng một statement mới, so payload và trả kết quả.

-- Chỉ với INSERT mới trả đúng 1 hàng:
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND sku = :sku
  AND active = TRUE
  AND available >= :quantity;

-- Ứng dụng kiểm tra số hàng thay đổi:
--   1: INSERT reservations rồi lưu kết quả SUCCEEDED.
--   0: lưu kết quả REJECTED, không tạo reservation.

COMMIT;
```

Giá trị `REJECTED` ban đầu chỉ là **placeholder chưa commit** để đáp ứng constraint cột status. Nó **không được coi là kết quả cuối** cho tới khi transaction thật sự chạy hết nhánh xử lý và commit. Mọi exception ở giữa phải rollback.

Ở PostgreSQL `READ COMMITTED`, khi hai transaction đồng thời `INSERT ... ON CONFLICT DO NOTHING` cùng khóa, câu INSERT ở transaction sau có thể **chờ** kết quả unique conflict; nếu trả 0 do transaction trước đã commit, **một câu SELECT riêng sau đó** có thể lấy bản ghi đã commit. Không gom INSERT và SELECT đối soát vào cùng một statement/CTE rồi giả định luôn nhìn thấy hàng thắng cuộc trong snapshot của statement đó. Với isolation khác hoặc failover, phải kiểm thử và thiết kế đọc lại/retry riêng.

**Cảnh báo:** câu SQL trên là skeleton có nhánh điều kiện do code điều phối; **không chạy vô điều kiện UPDATE sau khi INSERT trả 0**. Phần dưới đưa ví dụ Java hoàn chỉnh hơn.

## 12. Ví dụ Java/Spring JDBC: retry cùng ID chỉ tạo một reservation

Một service dùng Spring `@Transactional` và `JdbcTemplate` có thể giữ toàn bộ hiệu ứng **trong một PostgreSQL transaction**. Các class sau là ví dụ minh họa cần tích hợp đúng schema, transaction manager và cấu hình Spring ở dự án.

```java
import java.util.UUID;

public record ReserveCommand(
        UUID tenantId,
        UUID requestId,
        String sku,
        int quantity,
        String payloadHash
) {}

public record ReserveResult(
        String status,
        UUID reservationId,
        String reason
) {}
```

Service:

```java
import java.util.Objects;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {
    private final JdbcTemplate jdbc;

    public ReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public ReserveResult reserve(ReserveCommand cmd) {
        validate(cmd); // Tenant/request/sku/quantity/hash.

        Integer claimed = jdbc.query("""
            INSERT INTO operation_results (
                tenant_id, idempotency_key, operation_type,
                payload_hash, status, result_payload
            )
            VALUES (?, ?, 'RESERVE_STOCK', ?, 'REJECTED', '{}'::jsonb)
            ON CONFLICT (tenant_id, operation_type, idempotency_key)
            DO NOTHING
            RETURNING 1
            """,
            ps -> {
                ps.setObject(1, cmd.tenantId());
                ps.setObject(2, cmd.requestId());
                ps.setString(3, cmd.payloadHash());
            },
            rs -> rs.next() ? 1 : 0
        );

        if (claimed == null || claimed == 0) {
            return previouslyCommitted(cmd);
        }

        int updated = jdbc.update("""
            UPDATE inventory
               SET available = available - ?,
                   version = version + 1
             WHERE tenant_id = ?
               AND sku = ?
               AND active = TRUE
               AND available >= ?
            """,
            cmd.quantity(), cmd.tenantId(), cmd.sku(), cmd.quantity()
        );

        final ReserveResult result;
        if (updated == 1) {
            UUID reservationId = UUID.randomUUID();
            jdbc.update("""
                INSERT INTO reservations(
                    reservation_id, tenant_id, idempotency_key,
                    sku, quantity
                ) VALUES (?, ?, ?, ?, ?)
                """,
                reservationId, cmd.tenantId(), cmd.requestId(),
                cmd.sku(), cmd.quantity()
            );
            result = new ReserveResult(
                    "SUCCEEDED", reservationId, "");
        } else if (updated == 0) {
            // Lý do cụ thể có thể cần truy vấn nghiệp vụ riêng.
            result = new ReserveResult(
                    "REJECTED", null, "CONDITION_NOT_MET");
        } else {
            throw new IllegalStateException("Unexpected row count");
        }

        int saved = jdbc.update("""
            UPDATE operation_results
               SET status = ?,
                   result_payload = jsonb_build_object(
                       'status', CAST(? AS text),
                       'reservationId', CAST(? AS text),
                       'reason', CAST(? AS text)
                   )
             WHERE tenant_id = ?
               AND operation_type = 'RESERVE_STOCK'
               AND idempotency_key = ?
            """,
            result.status(), result.status(),
            result.reservationId() == null
                    ? "" : result.reservationId().toString(),
            result.reason(), cmd.tenantId(), cmd.requestId()
        );
        if (saved != 1) {
            throw new IllegalStateException("Operation result not persisted");
        }
        return result;
    }

    private ReserveResult previouslyCommitted(ReserveCommand cmd) {
        return jdbc.queryForObject("""
            SELECT payload_hash, status, result_payload
              FROM operation_results
             WHERE tenant_id = ?
               AND operation_type = 'RESERVE_STOCK'
               AND idempotency_key = ?
            """,
            (rs, rowNum) -> {
                if (!Objects.equals(rs.getString("payload_hash"),
                                    cmd.payloadHash())) {
                    throw new IdempotencyConflictException();
                }
                String status = rs.getString("status");
                String json = rs.getString("result_payload");
                // Để mã độc lập thư viện JSON, chỉ dùng JSON có cấu trúc
                // được ánh xạ qua mapper tin cậy của dự án.
                return ResultJsonMapper.parse(status, json);
            },
            cmd.tenantId(), cmd.requestId()
        );
    }

    private void validate(ReserveCommand cmd) {
        if (cmd == null || cmd.tenantId() == null ||
            cmd.requestId() == null || cmd.sku() == null ||
            cmd.sku().isBlank() || cmd.quantity() <= 0 ||
            cmd.payloadHash() == null || cmd.payloadHash().isBlank()) {
            throw new IllegalArgumentException("Invalid command");
        }
    }
}
```

Ở đây `IdempotencyConflictException` và `ResultJsonMapper` là **thành phần ví dụ do ứng dụng cần định nghĩa**, không phải class có sẵn trong JDK. Hai `public record` trong ví dụ trước cũng cần được đặt ở các tệp Java tương ứng. Mapper phải đọc lại chính xác kiểu dữ liệu và trạng thái đã lưu; không dựa trên việc parse chuỗi bằng cách nối/cắt thô. Hash phải được backend tính từ payload tin cậy/canonical, không nhận giá trị hash tự khai từ client rồi mặc nhiên tin.

**Giới hạn và điều kiện quan trọng:**

1. Tất cả bảng `operation_results`, `inventory` và `reservations` phải nằm trong **cùng database và transaction manager** cho lời hứa local atomicity này.
2. Method phải được gọi qua Spring transactional proxy hoặc cơ chế transaction tương đương, không tự gọi nội bộ khiến annotation bị bỏ qua.
3. `JdbcTemplate` phải dùng cùng `DataSource` mà transaction manager quản lý.
4. Kết quả trả ra từ method trước khi commit được caller xác nhận **chỉ sau khi Spring hoàn tất commit**; nếu commit thất bại hoặc mất ACK, tầng API không được trả “SUCCEEDED” như kết quả bền vững chắc chắn.
5. Với kết quả `REJECTED` do điều kiện nghiệp vụ, hệ thống **chủ động ghi nhận từ chối cuối**. Nếu nghiệp vụ muốn cho phép thử lại sau restock, đó phải là **ý định mới với request ID mới**.
6. Không gọi provider thanh toán, broker hay dịch vụ ngoài **bên trong transaction này** rồi suy rằng transaction cục bộ có thể rollback tác dụng ngoài.

Mã là **một khung triển khai để học giao thức**, cần hoàn thiện authorization, mapping, test concurrency, logging, exception translation và rollback semantics trước khi dùng trong production.

## 13. Khi trả kết quả cũ, phải giữ ngữ nghĩa phản hồi

Với một key đã có kết quả:

- Nếu kết quả trước là `SUCCEEDED`, retry nên trả **cùng định danh reservation/order**, không tạo ID khác.
- Nếu trước là `REJECTED`, trả cùng lý do/quyết định đã được chốt theo hợp đồng.
- Nếu payload hash khác, trả **conflict**, không giả vờ cùng yêu cầu.
- Nếu operation đang chạy ở hệ thống bất đồng bộ, trả `PENDING` và thông tin poll/status, không phát tiếp một tác dụng giống hệt.
- Nếu dữ liệu bị xóa do retention, API phải có chính sách cho request quá cũ; không tự tuyên bố mọi key đều có thể retry vô hạn.

Idempotency có thể được nhìn ở hai mức: **hiệu ứng** (không nhân đôi ghi) và **phản hồi** (caller có được một kết quả ổn định khi retry). Một hệ thống chặn ghi trùng nhưng mỗi lần trả lỗi khác nhau hoặc không có endpoint tra cứu vẫn có thể gây retry storm, timeout kéo dài và khó hỗ trợ khách hàng.

## 14. Không dùng `ON CONFLICT DO NOTHING` để che lỗi khác nghiệp vụ

Một câu `INSERT ... ON CONFLICT DO NOTHING` có thể rất hữu ích, nhưng có hai bẫy:

1. Nếu không chỉ rõ conflict target, lệnh có thể bỏ qua **những unique conflict không phải khóa idempotency** theo hành vi PostgreSQL. Khi đó lỗi dữ liệu khác có thể bị nuốt mất.
2. Ngay cả khi chặn được duplicate, chỉ dùng `DO NOTHING` mà **không đọc/so kết quả trước** có thể khiến API trả thành công cho một request có payload khác.

Với bảng `operation_results`, nên giới hạn conflict target tường minh:

```sql
INSERT INTO operation_results (
    tenant_id, idempotency_key, operation_type,
    payload_hash, status, result_payload
)
VALUES (
    :tenant_id, :idempotency_key, 'RESERVE_STOCK',
    :payload_hash, 'REJECTED', '{}'::jsonb
)
ON CONFLICT (tenant_id, operation_type, idempotency_key)
DO NOTHING
RETURNING idempotency_key;
```

Nếu hệ thống có thêm unique constraint trên một số cột khác, lỗi vi phạm constraint đó nên được **đánh giá riêng**, không xem mọi `23505` là “đã xử lý thành công”. Các chiến lược `UPSERT DO UPDATE` cũng cần kiểm tra side effect: một `DO UPDATE SET counter = counter + 1` **không trở nên lũy đẳng** chỉ vì có chữ `UPSERT`.

## 15. Ranh giới quan trọng: giao dịch DB không bao trùm API ngoài

Ví dụ đặt hàng cần thu tiền qua một provider:

```text
Order Service                         Payment Provider
    |
    +-- BEGIN PostgreSQL
    +-- INSERT order
    +-- call charge(orderId) ------------------------>
    |                                             Charge thành công
    |<----- timeout / lost ACK ----------------------X
    +-- exception, ROLLBACK PostgreSQL
    |
    +-- retry tạo order mới, gọi charge lần nữa --->
                                                  Charge lần hai?
```

**Sai lầm:** đặt lời gọi thanh toán bên trong `@Transactional` rồi suy rằng rollback PostgreSQL cũng hoàn tiền/hoàn tác provider. Một transaction của PostgreSQL chỉ rollback những thay đổi nó quản lý; provider ngoài không tự là participant của nó.

Ngoài ra, giữ transaction trong khi chờ HTTP gây những hậu quả khác:

- Khóa và connection có thể được giữ suốt nhiều giây timeout.
- Connection pool cạn khi nhiều yêu cầu cùng chờ mạng.
- Retry của caller và của client library có thể cộng dồn với retry phía provider.
- Thông tin trạng thái DB và tác dụng phía provider bị phân kỳ.

Một phương án thiết kế tốt hơn cho workflow dài là tách:

1. Ghi đơn ở trạng thái `PAYMENT_PENDING` và lệnh thanh toán vào **transactional outbox** trong cùng local transaction.
2. Relay/worker gửi `ChargePayment` với **payment operation ID ổn định**.
3. Payment Service/provider áp dụng idempotency cho ID đó, ghi nhận kết quả vào nguồn có thẩm quyền.
4. Orchestrator nhận/truy vấn kết quả, cập nhật order bằng state guard.
5. Nếu không thể hoàn tất, chạy **compensation** (ví dụ refund) có ID riêng, lịch sử riêng và trạng thái cần đối soát.

Mẫu này **không tạo global ACID**. Nó tạo một chuỗi hành động có thể phục hồi, chấp nhận trạng thái trung gian và đặt rõ hợp đồng khi không nhận được ACK.

## 16. Outbox đóng lỗ hổng “commit xong nhưng chưa gửi command”

Nếu Order Service thực hiện:

```text
COMMIT order(PAYMENT_PENDING)
process crashes
publish ChargePayment(...)
```

thì có thể **không bao giờ gửi lệnh** sau khi database đã commit. Nếu đổi thứ tự `publish` trước `COMMIT`, provider có thể thu tiền rồi transaction order rollback.

**Transactional outbox** lưu một event/command cần phát trong cùng transaction của dữ liệu nguồn:

```sql
CREATE TABLE outbox_commands (
    event_id       UUID PRIMARY KEY,
    operation_id   UUID NOT NULL UNIQUE,
    aggregate_id   UUID NOT NULL,
    command_type   TEXT NOT NULL,
    payload        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at   TIMESTAMPTZ
);

-- Cùng local transaction với ghi order:
BEGIN;

INSERT INTO orders(order_id, state, ...)
VALUES (:order_id, 'PAYMENT_PENDING', ...);

INSERT INTO outbox_commands(
    event_id, operation_id, aggregate_id, command_type, payload
) VALUES (
    :event_id, :payment_operation_id,
    :order_id, 'CHARGE_PAYMENT', :payload::jsonb
);

COMMIT;
```

Ở đây dấu `...` là vị trí lược bỏ **các cột/giá trị minh họa**, không phải SQL hoàn chỉnh để chạy nguyên văn. Bài học chính: việc tạo order và ghi ý định phát command phải cùng commit. Schema production cần quyền, tenant, trạng thái retry và quy trình dọn dẹp phù hợp.

Nếu relay gửi message rồi sập trước khi đánh dấu `published_at`, message **có thể được phát lại**. Outbox xử lý nguy cơ **mất message**, nhưng không mặc nhiên đảm bảo **exactly once** ở end-to-end. Consumer/provider vẫn cần chống tác dụng phụ lặp theo `operation_id`.

### Không đổi operation ID ở mỗi lần relay

Một relay đúng có thể có nhiều attempt:

```text
event_id = E1, payment_operation_id = P1
   attempt #1: broker ACK bị mất
   attempt #2: publish lại E1 hoặc message tương đương
   attempt #3: consumer nhận duplicate

Tất cả phải giữ payment_operation_id = P1.
```

Nếu relay sinh `P2`, `P3` cho mỗi lần gửi, cơ chế dedup ở Payment Service không nhận ra đó là **cùng một ý định thu tiền**.

## 17. Payment Service cần idempotency ở điểm tạo hiệu ứng thật

Một Order Service đã có outbox và request ID chưa đủ nếu Payment Service vẫn chạy:

```sql
INSERT INTO payment_charges(charge_id, amount_cents)
VALUES (gen_random_uuid(), :amount_cents);
```

cho mỗi message nhận được. Event lặp vẫn có thể tạo hai charge.

Cần một **ràng buộc duy nhất tại nơi thực thi tác dụng**:

```sql
CREATE TABLE payment_operations (
    payment_operation_id UUID PRIMARY KEY,
    order_id             UUID NOT NULL,
    amount_cents         BIGINT NOT NULL CHECK (amount_cents > 0),
    currency             TEXT NOT NULL,
    state                TEXT NOT NULL CHECK (
        state IN ('PENDING', 'CHARGED', 'DECLINED', 'UNKNOWN')
    ),
    provider_reference   TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Một thao tác ở database phải sử dụng
-- payment_operation_id để phát hiện xử lý lại.
```

**Nhưng còn một ranh giới ngoài:** nếu Payment Service gọi một nhà cung cấp thanh toán qua mạng, ghi `payment_operations` và gọi provider **không cùng một transaction**. Payment Service cũng phải dùng **provider idempotency key**, nếu provider hỗ trợ, hoặc API tra cứu/reference đáng tin để đối soát.

| Ranh giới | Khóa chống trùng nên là gì? | Nguồn kết quả có thẩm quyền |
| --- | --- | --- |
| HTTP client → Order API | Order request ID theo tenant/người dùng. | Order operation ledger ở Order DB. |
| Order outbox → Payment consumer | Event ID + payment operation ID. | Payment operation ledger/inbox. |
| Payment Service → provider | Provider idempotency key theo hợp đồng. | Provider/payment ledger authoritative. |
| Payment → refund | **Refund operation ID riêng**, ổn định khi retry refund. | Kết quả refund được xác nhận. |

Không tái sử dụng payment operation ID cho **một lần charge mới hợp lệ** sau khi người dùng thay đổi phương thức thanh toán hoặc số tiền. Mỗi ý định được định nghĩa độc lập; retry của **cùng** ý định giữ nguyên key.

## 18. Đối soát sau timeout với provider: “không thấy” vẫn có thể chưa đủ

Giả sử provider API có khả năng:

```text
POST /charges      với Idempotency-Key = P1
GET /charges/by-operation/P1
```

Đây là **hợp đồng API minh họa**, không phải endpoint của một nhà cung cấp cụ thể. Khi timeout:

1. Giữ trạng thái local `UNKNOWN` hoặc `PENDING`.
2. Tra cứu kết quả theo `P1` qua API có thẩm quyền.
3. Nếu chắc chắn `CHARGED`, ghi nhận charge đã hoàn tất và không gọi tác dụng mới.
4. Nếu chắc chắn `DECLINED` theo hợp đồng, ghi nhận từ chối.
5. Nếu tra cứu chưa có kết quả hoặc provider tạm không sẵn sàng, **không tùy tiện sinh `P2`**. Chỉ gửi lại `P1` khi hợp đồng provider đảm bảo điều đó an toàn trong phạm vi thời hạn key.
6. Nếu không thể xác định an toàn, đưa workflow sang trạng thái cần đối soát/kiểm tra thủ công.

Một API trả “not found” không luôn chứng minh chưa thu tiền, đặc biệt khi trạng thái xử lý bất đồng bộ, hệ thống tra cứu có replication lag hoặc provider chỉ index kết quả sau một khoảng thời gian.

**Phải đọc hợp đồng thực của provider:** phạm vi key, thời gian giữ key, cách xử lý retry cùng key khác payload, phản hồi khi request đang xử lý, khả năng tra cứu và nghĩa của trạng thái không tồn tại. Không xây chính sách “cứ GET 404 là charge lại bằng ID mới” nếu chưa có bảo đảm.

### Refund là một tác dụng mới, không phải rollback

Khi quyết định hủy một order đã charge:

```text
Charge operation = P1, state = CHARGED
Refund operation = R1, state = REFUND_PENDING

Retry refund sau timeout: vẫn dùng R1.
Không tạo R2 chỉ vì không nhận được ACK refund.
```

Hoàn tiền có thể xử lý bất đồng bộ, mất phí hoặc cần can thiệp. Do đó `REFUND_REQUESTED` khác `REFUNDED` và bù trừ không xóa dấu vết charge khỏi audit ledger.

## 19. Inbox và message delivery: đừng nhầm at-least-once với exactly-once

Trong hệ thống broker, message có thể được giao lại vì consumer xử lý xong DB rồi mất ACK trước khi broker nhận được.

```text
Broker phát Event E1
     |
     v
Consumer:
  BEGIN
  UPDATE trạng thái nghiệp vụ
  COMMIT
  --- network lost before ACK ---
     |
Broker giao Event E1 lần nữa
```

Mẫu **transactional inbox** xử lý duplicate theo event:

```sql
CREATE TABLE inbox_events (
    consumer_name TEXT NOT NULL,
    event_id      UUID NOT NULL,
    handled_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong **cùng local transaction**:

1. Thử ghi event ID bằng `INSERT ... ON CONFLICT DO NOTHING RETURNING ...`.
2. Nếu đã xử lý, không áp dụng lại business update.
3. Nếu chưa, kiểm tra trạng thái workflow và thực hiện cập nhật có điều kiện.
4. Ghi outbox cho bước kế tiếp nếu cần.
5. Commit inbox + business state + outbox.
6. ACK broker sau khi commit thành công.

Nếu transaction lỗi trước commit, inbox phải rollback. **Không commit inbox trước khi xử lý business**, vì lần giao lại sẽ bị bỏ qua dù nghiệp vụ chưa thực hiện.

Một vấn đề khác: upstream có thể gửi **hai event ID khác nhau** cho cùng một payment operation. Vì vậy, inbox theo event ID chỉ chống **giao trùng một event**; unique theo **business operation ID** ở điểm tạo charge/đổi state mới chống tác dụng phụ trùng về mặt nghiệp vụ.

## 20. Retry policy: backoff, jitter, budget và khả năng phân loại kết quả

Sau khi có idempotency, không nên gửi request vô hạn. Retry là một nguồn tải có thể khuếch đại sự cố:

```text
Client retry × Gateway retry × Service retry × DB retry
    3 lần         3 lần          3 lần          3 lần
           → Có thể khuếch đại thành 81 attempts
             cho một yêu cầu gốc ở một số đường gọi.
```

Một chính sách tốt cần:

- **Retry budget:** số lần thử hoặc tổng thời gian tối đa cho một ý định.
- **Exponential backoff + jitter:** tránh hàng nghìn client thử lại cùng lúc.
- **Deadline:** không giữ một request đồng bộ mở vượt cam kết; có thể chuyển sang 202/poll.
- **Error classification:** phân biệt lỗi tạm thời xác định, lỗi nghiệp vụ và kết quả chưa rõ.
- **Circuit breaker/bulkhead:** hạn chế retry khi dependency đang quá tải.
- **End-to-end idempotency:** mọi attempt sử dụng cùng business operation ID.
- **Observability:** đếm attempts, duplicates, reconcile lag, pending age, tỷ lệ outcome UNKNOWN.

Ví dụ dãy delay **minh họa**, không phải cấu hình mặc định nên dùng:

```text
attempt 1: gửi ngay
attempt 2: chờ random khoảng 100–250 ms
attempt 3: chờ random khoảng 300–700 ms
attempt 4: dừng, trả PENDING hoặc chuyển đối soát nền
```

Khi dependency đã trở lại, không nhất thiết gửi lại đồng loạt mọi pending operation. Cần giới hạn concurrency và tôn trọng rate limit. **Retry an toàn về dữ liệu chưa chắc an toàn về tải**.

### Retry toàn transaction sau lỗi serialization

Nếu PostgreSQL trả `40001`, transaction hiện tại thường cần rollback. Một lần thử mới phải bắt đầu **transaction mới** và chạy lại toàn bộ **đọc → quyết định → ghi** theo logic nghiệp vụ. Không giữ lại dữ liệu đã đọc trong snapshot trước rồi chỉ thử `UPDATE` cuối.

Trong Spring, cần chú ý thứ tự interceptor `@Retryable` và `@Transactional`, self-invocation và cách tạo transaction mỗi attempt. Một phương án rõ ràng là:

```text
Retry coordinator (không giữ transaction mở)
     |
     +-- attempt 1 -> transactional service -> rollback nếu 40001
     |
     +-- backoff
     |
     +-- attempt 2 -> transaction MỚI -> đọc/ghi toàn bộ use case
```

Đừng đặt network call không lũy đẳng bên trong transaction rồi dùng `@Retryable` cho cả method nếu như các side effect đó không được bảo vệ bằng operation ID phía nhận.

## 21. Java: ví dụ coordinator phân biệt timeout và trạng thái chưa rõ

Ví dụ một interface gateway cho thanh toán **minh họa hợp đồng**, không giả định endpoint cụ thể:

```java
import java.util.UUID;

public interface PaymentGateway {
    enum State { CHARGED, DECLINED, PENDING, UNKNOWN }

    record Result(State state, String providerReference) {}

    Result charge(UUID operationId, long amountCents)
            throws GatewayTimeoutException;

    Result lookup(UUID operationId)
            throws GatewayUnavailableException;
}

class GatewayTimeoutException extends Exception {}
class GatewayUnavailableException extends Exception {}
```

Điều phối một lần sau timeout:

```java
import java.util.UUID;

public final class PaymentCoordinator {
    private final PaymentGateway gateway;

    public PaymentCoordinator(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentGateway.Result submitOrReconcile(
            UUID paymentOperationId, long amountCents
    ) throws GatewayUnavailableException {
        try {
            return gateway.charge(paymentOperationId, amountCents);
        } catch (GatewayTimeoutException unknownOutcome) {
            try {
                PaymentGateway.Result observed =
                        gateway.lookup(paymentOperationId);
                if (observed.state() == PaymentGateway.State.CHARGED
                        || observed.state() == PaymentGateway.State.DECLINED) {
                    return observed;
                }
            } catch (GatewayUnavailableException temporarilyUnavailable) {
                // Giữ UNKNOWN; không tạo một ID/charge mới.
            }
            return new PaymentGateway.Result(
                    PaymentGateway.State.UNKNOWN, null);
        }
    }
}
```

Đoạn code chỉ minh họa **một lần gửi và một lần đối soát**. Implementation hoàn chỉnh còn phải:

1. Ghi trạng thái operation bền vững trước và sau call, để phục hồi khi JVM sập.
2. Quy định retry hoặc poll nền với backoff và giới hạn thời gian.
3. Xác định response `DECLINED` có thực sự là kết quả cuối theo hợp đồng provider.
4. Kiểm tra provider có đảm bảo **lũy đẳng cho cùng paymentOperationId** không trước khi phát lại `charge()`.
5. Xác thực số tiền, currency, tenant, reference và độ tin cậy của trạng thái trả về.
6. Không hiểu `UNKNOWN` là “chưa thu tiền” hay “thất bại chắc chắn”.

Trong hệ thống nhiều service, trạng thái `UNKNOWN` được ghi vào workflow và có **owner cùng thời hạn đối soát**, thay vì để caller chờ HTTP vô hạn hoặc tự gửi yêu cầu mới.

## 22. Thiết kế API cho caller được phép retry nhưng không nhân đôi side effect

Một hợp đồng HTTP có thể yêu cầu `Idempotency-Key` khi tạo order:

```http
POST /orders
Idempotency-Key: 8cbe3e02-a5e8-4b90-b0a2-cc30eae68c29
Content-Type: application/json

{"sku":"BOOK-1","quantity":2}
```

Những phản hồi hợp lý tùy trạng thái:

| Trạng thái backend | Phản hồi API có thể chọn | Hợp đồng cần công bố |
| --- | --- | --- |
| Đơn vừa hoàn thành | `201 Created`, order ID. | Key gắn với order mới. |
| Retry cùng key và payload đã hoàn thành | `200`/`201` với cùng kết quả đã lưu. | Status và body/headers được replay theo quy ước. |
| Đang xử lý bất đồng bộ | `202 Accepted` cùng operation/status URL. | Client poll bằng ID, không gửi key mới. |
| Cùng key nhưng payload khác | `409 Conflict`. | Cho biết xung đột mà không lộ payload cũ. |
| Kết quả cuối từ chối nghiệp vụ | 4xx phù hợp hoặc result `REJECTED`. | Có thể trả lại cùng quyết định khi retry. |
| Nguồn đối soát chưa sẵn sàng | `202`/`503` theo API với operation ID. | Caller biết chưa rõ, phải giữ key và không tạo ý định mới. |

Mã HTTP cụ thể phụ thuộc hợp đồng; **không có một mã duy nhất đảm bảo lũy đẳng**. Quan trọng là caller biết **có nên gửi lại cùng key**, **tra cứu ở đâu**, và **khi nào phải mở ý định mới**.

Với giao diện web, việc người dùng bấm nút hai lần, tải lại trang hoặc mạng mobile tự gửi lại đều có thể tạo duplicate. Client nên tạo key cho **một lần người dùng xác nhận ý định**, giữ nó qua retry/reload phù hợp và tạo key khác khi người dùng chủ động bắt đầu hành động mới. Không dùng một key duy nhất vĩnh viễn cho mọi đơn.

## 23. Thời hạn lưu khóa: TTL là quyết định nghiệp vụ

Giữ mọi idempotency record mãi mãi có chi phí dung lượng; xóa quá sớm lại tạo cửa sổ replay:

```text
Ngày 1: Order request K đã commit; kết quả lưu trong ledger.
Ngày 2: Client offline, chưa nhận được phản hồi.
Ngày 3: Retention job xóa record K.
Ngày 4: Client retry K; hệ thống nghĩ đây là request mới.
       → Có thể tạo thêm order/charge.
```

Chính sách retention phải xét:

- **Retry window** của client, gateway và broker.
- Thời gian mất mạng/offline dài nhất cần hỗ trợ theo hợp đồng.
- Thời hạn idempotency key của provider (nếu có).
- Thời gian đối soát thanh toán, chargeback/refund và hỗ trợ khách hàng.
- Dữ liệu audit/ledger phải giữ vì yêu cầu pháp lý/kế toán.
- Khả năng tồn tại event trễ, DLQ replay và khôi phục backup cũ.

Có thể thiết kế khóa duy nhất tồn tại lâu trong bảng nghiệp vụ chính, còn bản sao response chi tiết có TTL ngắn hơn; hoặc lưu một **tombstone** đủ để từ chối/đối soát key cũ. Nhưng cách này phải phân biệt “đã tồn tại nhưng body cũ hết hạn” với “chưa từng tồn tại”.

Không xóa idempotency ledger dựa thuần vào “bảng đã quá lớn” nếu chưa chứng minh rằng mọi retry cũ sẽ bị từ chối an toàn.

## 24. Bảo mật khóa idempotency và đường đối soát

Một idempotency key không nên biến thành một khả năng đọc kết quả của người khác. Các điểm cần bảo vệ:

- **Scope theo tenant/tài khoản đã xác thực**; đừng cho người dùng A đoán key của B rồi đọc order B.
- Xác thực và phân quyền endpoint `GET /operations/{id}` giống việc đọc chính tài nguyên nghiệp vụ.
- Không coi key ngẫu nhiên là **authentication token** thay cho session/JWT/quyền.
- Không để cùng key được phép đổi amount, currency, payee hoặc owner.
- Giới hạn kích thước/định dạng key để ngăn storage abuse và key injection.
- Không log raw token thanh toán, dữ liệu thẻ hoặc payload nhạy cảm trong operation ledger.
- Rate-limit endpoint tạo và tra cứu operation để chống spam/replay.

Đối với fingerprint, nên hash **dữ liệu đã chuẩn hóa từ tham số được xác thực**, có version của thuật toán canonicalization. Nếu dữ liệu đầu vào nhạy cảm hoặc tập giá trị nhỏ dễ đoán, cần cân nhắc HMAC hoặc cách bảo vệ phù hợp thay vì đưa raw hash có thể suy diễn ra các trường bí mật.

**Phân quyền business không được bỏ qua vì request là retry.** Trả kết quả đã lưu của một đơn có thể tiết lộ thông tin riêng nếu người gửi key hiện tại không còn quyền đọc.

## 25. Quan sát vận hành: phát hiện retry storm và duplicate bị chặn

Một hệ thống có idempotency đúng vẫn có thể khó vận hành nếu không biết bao nhiêu tác vụ đang kẹt ở trạng thái không rõ.

| Metric / log | Ý nghĩa |
| --- | --- |
| `operation.started` theo loại | Số ý định mới, tách khỏi số attempts. |
| `operation.duplicate_detected` | Bao nhiêu lần replay cùng key bị chặn. |
| `operation.payload_conflict` | Cùng key nhưng khác payload; có bug client hoặc tấn công? |
| `operation.unknown_outcome` | Bao nhiêu thao tác chưa kết luận sau timeout. |
| `operation.reconcile_age_seconds` | Thời gian pending/unknown; phát hiện backlog. |
| `operation.reconcile_resolved` | Bao nhiêu unknown xác nhận thành công/từ chối sau đó. |
| `retry.attempts_per_operation` | Mức khuếch đại từ client/gateway/worker. |
| `outbox.oldest_unpublished_age` | Command đã commit nhưng chưa gửi lâu bao nhiêu. |
| `inbox.duplicate_event` | Broker giao lại event, khả năng idempotency consumer. |
| `payment.duplicate_provider_response` | Provider trả cùng operation hoặc có sai lệch reference. |
| `database.serialization_failures` | Retry transaction do concurrency, cần đo giới hạn. |
| `db_pool.pending_acquire` | Retry storm có đang làm nghẽn connection pool? |

Log có thể mang `operationId`, `attemptId`, `traceId`, phase, trạng thái workflow, loại kết quả và SQLSTATE đã lọc. Tránh đặt `operationId` đầy đủ làm **metric label có cardinality cực cao**; sử dụng log/trace theo ID, còn metric aggregate theo service, operation type và result code.

### Khi cảnh báo UNKNOWN tăng

Không chỉ tăng số lần retry. Quy trình điều tra:

1. Xem dependency có timeout/overload, failover hay lỗi mạng không.
2. Đối chiếu ledger ở nguồn có thẩm quyền và số event chưa xác nhận.
3. Giảm mức đồng thời; bật backoff/circuit breaker phù hợp.
4. Kiểm tra có charge/refund đã xảy ra mà workflow vẫn pending không.
5. Xác định các operation quá hạn cần can thiệp thủ công.
6. Ghi nhận trạng thái cuối và nguyên nhân, không sinh thêm tác dụng không lũy đẳng chỉ để “cho xong”.

## 26. Kiểm thử concurrency và fault injection để chứng minh idempotency

Một unit test mock repository chỉ kiểm tra code gọi `findByRequestId` trước khi ghi; nó **không chứng minh** race an toàn nếu hai request cùng đi qua:

```text
Thread A: SELECT request K → not found
Thread B: SELECT request K → not found
Thread A: INSERT order K
Thread B: INSERT order K
```

Phải có **constraint tại DB** (và transaction/claim protocol) để chặn cả khi hai connection cạnh tranh. Với PostgreSQL Testcontainers và Java integration tests, kiểm tra:

| Kịch bản | Bằng chứng mong muốn |
| --- | --- |
| Hai request cùng key/payload tới đồng thời | Chỉ một operation được commit; cả hai thấy cùng kết quả. |
| Hai request cùng key, payload khác | Một operation thắng; cái còn lại nhận conflict, không đổi hiệu ứng đã chốt. |
| Timeout sau DB commit nhưng trước HTTP ACK | Retry cùng key đọc lại kết quả; không tạo đơn hoặc trừ hàng lần hai. |
| Transaction rollback trước commit | Không có side effect đã commit; retry có thể xử lý lại cùng key. |
| Unique conflict từ constraint khác | Không bị nuốt thành duplicate hợp lệ. |
| Payment provider commit rồi mất ACK | Lệnh charge lại cùng provider operation ID hoặc đối soát; không phát charge mới. |
| Broker giao lại cùng event ID | Inbox và local transaction ngăn side effect lặp. |
| Hai event ID khác nhưng một payment operation | Constraint theo business operation vẫn chặn double-charge. |
| Refund commit rồi mất ACK | Không hoàn tiền lần nữa với ID mới. |
| Bảng key được cleanup giữa hai lần retry | Cơ chế tombstone/expired-key policy ngăn replay sai. |
| Read replica chậm chưa thấy operation | Không xem cache/replica miss là chứng cứ chưa commit. |
| Worker cũ hoạt động sau khi mất lease | State/version guard ngăn stale worker chuyển trạng thái sai. |

**Phải chủ động đặt lỗi đúng thời điểm.** Ném một exception **trước** khi gọi `commit()` chỉ thử rollback, không thử trường hợp **commit đã bền nhưng ACK bị mất**. Muốn kiểm thử trường hợp khó này, cần môi trường cô lập có thể chặn/mất phản hồi tại proxy/đường mạng và đọc kết quả qua một kết nối mới.

### Phép thử hai request đồng thời

Một khung kiểm thử:

```java
// Pseudocode JUnit logic; triển khai bằng database thật.
UUID requestId = UUID.randomUUID();
ReserveCommand cmd = command(tenantId, requestId, "BOOK-1", 3);

// Fixture: tồn kho 10 và cùng hash của một ý định.
// Hai thread có transaction/connection riêng; barrier cho bắt đầu.
ReserveResult resultA = invokeConcurrently(() -> service.reserve(cmd));
ReserveResult resultB = invokeConcurrently(() -> service.reserve(cmd));

assertEquals(resultA.status(), resultB.status());
assertEquals(resultA.reservationId(), resultB.reservationId());

// Truy vấn database sau commit từ connection khác:
// available = 7, reservations có đúng 1 hàng cho requestId,
// operation_results có đúng 1 kết quả cho key.
```

Đây **không phải mã JUnit chạy độc lập**: `invokeConcurrently`/`command` là hàm giả lập để diễn đạt kịch bản, cần hiện thực bằng `CountDownLatch`/`ExecutorService` và fixture của dự án. Test phải có timeout, cleanup và không vô tình chạy cả hai invocation trong **cùng một transaction**. Một số race cần barrier tại từng bước, không chỉ khởi chạy hai thread cùng lúc.

## 27. Test theo ma trận trạng thái thay vì chỉ theo mã lỗi

Để không xử lý nhầm `UNKNOWN` thành `FAILED`, hãy kiểm tra toàn bộ những chuyển trạng thái quan trọng:

```text
NEW
  |
  v
PROCESSING  ------> SUCCEEDED
  |                    |
  |                    +-- duplicate: trả cùng kết quả
  |
  +---------------> REJECTED
  |                    |
  |                    +-- duplicate: trả cùng quyết định
  |
  +-- timeout ------> UNKNOWN / RECONCILING
                            |
                            +--> SUCCEEDED khi xác minh thành công
                            +--> REJECTED khi xác minh từ chối
                            +--> NEEDS_REVIEW khi không thể kết luận
```

Không phải mọi workflow cần lưu đủ tất cả trạng thái. **Local transaction đơn** có thể chỉ công bố `SUCCEEDED`/`REJECTED` theo ledger mẫu; **distributed payment** cần trạng thái pending/unknown bền vững. Quan trọng là state machine phản ánh thực tế của các ranh giới đã commit.

State guard ngăn worker cũ chuyển kết quả cuối trở lại pending:

```sql
UPDATE payment_operations
SET state = 'CHARGED',
    updated_at = CURRENT_TIMESTAMP
WHERE payment_operation_id = :operation_id
  AND state IN ('PENDING', 'UNKNOWN');
```

Cần kiểm tra số hàng cập nhật và sự phù hợp của provider reference/số tiền. Nếu state đã `DECLINED` hoặc `CHARGED` do xử lý khác, event đến trễ không được tự động ghi đè: phải đối soát/đánh giá conflict. Với nhiều sự kiện cạnh tranh, thêm version hoặc transition guard đủ mạnh; ví dụ này mới bảo vệ một phần.

## 28. Những quyết định thiết kế cần ghi rõ trước khi bật retry

| Quyết định | Câu hỏi cụ thể |
| --- | --- |
| **Phạm vi idempotency** | Key unique theo tenant, người dùng, service hay operation type? |
| **Thời điểm chốt kết quả** | Sau local DB commit, provider ACK, hay workflow hoàn tất? |
| **Nguồn đối soát** | Bảng ledger primary, payment provider, event log hay hệ khác? |
| **Trùng payload** | Fingerprint thế nào, version schema và quy tắc so sánh ra sao? |
| **Trạng thái pending** | Client nhận gì khi thao tác đang xử lý hoặc chưa rõ? |
| **Chiến lược timeout** | Deadline, retry budget, backoff, rate limit, circuit breaker? |
| **Cơ chế chống trùng** | Unique constraint, inbox, provider key, conditional state transition? |
| **Retention** | Giữ key và kết quả bao lâu so với cửa sổ retry/replay? |
| **Lỗi commit không rõ** | Ai đối soát, trong bao lâu, khi nào chuyển NEEDS_REVIEW? |
| **Tác dụng phụ không bù được** | Email, chuyển tiền, shipment cần trì hoãn hoặc xử lý bằng quy tắc gì? |
| **Bảo mật** | Ai được tạo/tra cứu key và kết quả? Có lộ dữ liệu qua replay không? |
| **Quan sát** | Có phân biệt số ý định mới, số attempt và số tác dụng đã commit không? |

Nếu một hệ thống không trả lời được “cùng request ID được gửi lại thì chuyện gì xảy ra?”, việc thêm `retry(3)` chỉ làm lỗi khó nhận biết hơn.

## 29. Các anti-pattern cần nhận diện khi review code Java

| Anti-pattern | Vì sao sai | Thay bằng |
| --- | --- | --- |
| `catch (TimeoutException) { createOrder(new UUID); }` | Timeout có thể sau commit; sinh đơn trùng. | Giữ request ID, tra ledger và trả kết quả cũ. |
| `catch (SQLException) { retrySameSQL(); }` | Không phân biệt lỗi và transaction boundary. | Phân loại SQLSTATE, retry toàn transaction nếu phù hợp. |
| `@Retryable` bao toàn method chứa charge HTTP | Side effect ngoài DB có thể lặp sau local rollback. | Outbox, provider idempotency, reconciliation. |
| Kiểm tra `existsByKey` rồi mới `INSERT` | Hai request đồng thời đều thấy “chưa có”. | Unique constraint + atomic claim + transaction. |
| Dùng cache để đánh dấu “đã xử lý” | Cache có thể mất/expire trước retry hợp lệ. | Durable idempotency ledger ở nguồn authoritative. |
| Dùng request hash nhưng không unique key | Hai connection vẫn có thể cùng ghi. | Constraint theo scope + so fingerprint. |
| `ON CONFLICT DO NOTHING` rồi trả 200 luôn | Có thể payload khác hoặc conflict khác. | Chỉ rõ target, đọc kết quả cũ và phân loại. |
| Ghi inbox trước, commit business sau | Event retry bị bỏ qua khi business chưa hoàn tất. | Inbox + business state + outbox cùng local transaction. |
| Mỗi retry của broker sinh operation ID mới | Dedup theo ID không chặn duplicate. | Operation ID ổn định qua mọi attempt. |
| Timeout payment → đánh dấu thất bại ngay | Provider có thể đã charge. | UNKNOWN, tra provider/ledger và đối soát. |
| Thấy “not found” ở read replica rồi tạo mới | Replica có thể lag sau commit. | Kiểm tra nguồn authoritative với consistency phù hợp. |
| Xóa idempotency records quá sớm | Replay cũ lại tạo tác dụng. | TTL/retention theo hợp đồng, tombstone hoặc reject key hết hạn. |
| Retry không giới hạn khi dependency lỗi | Tăng tải và kéo dài sự cố. | Backoff, jitter, retry budget, bulkhead. |
| Dùng key làm quyền đọc kết quả | Người đoán key có thể xem dữ liệu người khác. | Authentication/authorization độc lập. |

## 30. Checklist sửa lỗi “retry mọi timeout” theo từng bước

1. **Liệt kê tác dụng không lũy đẳng:** tạo đơn, giữ hàng, trừ/cộng số dư, charge, refund, gửi email, phát command.
2. **Xác định ranh giới commit thật:** database nào commit, broker/provider nào có thể đã xử lý, có external side effect nào xảy ra trước commit.
3. **Định nghĩa một operation ID ổn định** cho mỗi ý định nghiệp vụ, giữ qua retry, phân biệt ID attempt/event.
4. **Đặt unique constraint tại nơi tác dụng được tạo** và đảm bảo atomic claim + business update + result trong một local transaction.
5. **Lưu fingerprint/canonical payload**, từ chối cùng key khác payload.
6. **Định nghĩa kết quả cuối và pending/unknown**; cung cấp endpoint/status để client tra cứu.
7. **Không xem timeout là rollback**; đối soát bằng nguồn có thẩm quyền.
8. **Với external API**, yêu cầu hợp đồng idempotency key và lookup; nếu không có bảo đảm, thêm manual review hoặc thiết kế workflow khác.
9. **Với message broker**, dùng inbox/outbox và chống trùng theo business operation.
10. **Phân loại lỗi transient**, retry toàn transaction khi cần, không phát lại non-idempotent side effect tùy tiện.
11. **Giới hạn retry**, backoff và concurrency; ngăn retry storm.
12. **Chính sách retention đủ dài**, không xóa idempotency evidence trước khi hết cửa sổ replay.
13. **Bảo vệ tenant, phân quyền và secrets** trên key/ledger/status endpoint.
14. **Viết integration test với DB thật** cho hai request đồng thời, rollback và lỗi commit không rõ; fault injection tại provider/broker.
15. **Quan sát số tác dụng nghiệp vụ thực**, không chỉ số HTTP 200 hoặc số attempt.
16. **Có runbook đối soát** UNKNOWN/NEEDS_REVIEW và hậu kiểm nếu đã phát sinh duplicate.

## 31. Câu hỏi tự kiểm tra

**Câu 1.** Một câu `UPDATE balance = balance - 100` chạy trong transaction PostgreSQL. Có thể retry vô điều kiện khi JDBC `commit()` timeout không?

**Không.** Transaction cục bộ có thể đã commit nhưng ACK mất. Retry y nguyên có thể trừ thêm 100. Cần operation ID, constraint/ledger và đối soát trên nguồn authoritative.

**Câu 2.** Tại sao cùng client request lại phải giữ nguyên idempotency key qua retry?

Vì key xác định **một ý định**, cho server biết kết quả đã commit cần được trả lại thay vì tạo tác dụng mới. Attempt ID có thể thay đổi nhưng operation ID không.

**Câu 3.** Hai lần `POST` cùng key nhưng amount khác nhau thì sao?

Hệ thống phải phát hiện payload conflict dựa trên fingerprint của tham số có nghĩa nghiệp vụ, không ghi lần hai hay âm thầm trả kết quả như thể amount mới đã được xử lý.

**Câu 4.** `SELECT existsByRequestId` trước `INSERT` đã đủ ngăn ghi trùng chưa?

**Chưa.** Hai transaction có thể cùng thấy chưa tồn tại. Phải có unique constraint/atomic claim ở database, kèm transaction bảo vệ tác dụng.

**Câu 5.** Vì sao `ON CONFLICT DO NOTHING` chưa đủ để API hoàn chỉnh?

Vì cần chỉ rõ conflict target, so payload và trả trạng thái/kết quả đã lưu. Không phải mọi unique conflict đều là duplicate hợp lệ của cùng request.

**Câu 6.** Payment provider đã charge nhưng gateway timeout. Có nên gửi lại với payment ID mới để chắc chắn thu được tiền không?

**Không.** Phải tra cứu bằng operation ID cũ; chỉ retry cùng key khi provider có hợp đồng lũy đẳng phù hợp. Nếu kết quả không rõ, giữ pending/unknown và đối soát.

**Câu 7.** Một event broker có ID E được giao lại sau khi consumer commit. Cần làm gì?

Dùng inbox để phát hiện E đã xử lý, trong cùng local transaction với business update và outbox. Ngoài ra cần business operation ID để chặn hai event khác ID nhưng cùng ý định.

**Câu 8.** Vì sao không nên xóa idempotency key sau 24 giờ nếu client có thể retry sau bảy ngày?

Vì lần retry cũ sau khi record bị xóa có thể bị hiểu là ý định mới. Retention phải bao phủ phạm vi replay hoặc có tombstone/expired-key policy an toàn.

**Câu 9.** Khi PostgreSQL trả `40001`, retry câu `UPDATE` cuối cùng với dữ liệu đã đọc từ transaction cũ có đúng không?

**Không.** Cần rollback và retry cả transaction gồm các bước đọc/kiểm tra/ghi theo giao thức an toàn, với số lần thử có giới hạn.

**Câu 10.** Vì sao đọc “không có operation P” trên Redis hoặc read replica không chứng minh P chưa commit?

Vì cache có thể mất entry và replica có thể lag. Cần nguồn có thẩm quyền và bảo đảm freshness thích hợp; nếu không thể xác định, giữ trạng thái unknown.

**Câu 11.** Một gateway đã có idempotency key, có cần test concurrency với hai request cùng key nữa không?

**Có.** Cần chứng minh constraint và transaction thật ngăn hai worker đồng thời cùng tạo side effect, kiểm tra cả cùng payload, khác payload và mất ACK sau commit.

**Câu 12.** Một API luôn trả HTTP 200 khi retry thành công. Đã chứng minh nghiệp vụ lũy đẳng chưa?

**Chưa.** Phải kiểm tra dữ liệu cuối: một order/charge/reservation, cùng kết quả cũ, không có external side effect lặp. Mã HTTP không phải bằng chứng chống trùng.

## Kết luận

**“Timeout thì thử ghi lại” là một quyết định nguy hiểm khi thao tác không lũy đẳng.** Timeout phản ánh việc không nhận được kết quả đúng hạn, trong khi transaction hoặc provider **có thể đã hoàn tất và commit**. Một hệ thống đúng không biến sự bất định thành giả định rollback, và không sinh operation ID mới chỉ để việc retry có vẻ dễ thực hiện.

Trong nền tảng Java persistence, hãy định danh **ý định nghiệp vụ**, bảo vệ tác dụng ở điểm ghi bằng **unique constraint + transaction + state guard**, lưu kết quả để replay an toàn và đối soát từ nguồn có thẩm quyền sau lỗi mạng. Với nhiều dịch vụ, thêm **outbox/inbox, idempotency phía provider, workflow trạng thái UNKNOWN và cơ chế compensation có ID riêng**. Retry vẫn hữu ích khi có backoff và giới hạn, nhưng chỉ an toàn khi mọi ranh giới có thể nhận lại cùng yêu cầu **mà không nhân đôi tác dụng nghiệp vụ**.
