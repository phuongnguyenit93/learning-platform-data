# Mô phỏng timeout khi ghi và thiết kế cơ chế thử lại lũy đẳng

Một API Java nhận yêu cầu đặt hàng, trừ tồn kho và tạo đơn trong PostgreSQL. Ở cuối thao tác, ứng dụng gửi `COMMIT` nhưng kết nối bị ngắt trước khi nhận được phản hồi. Client thấy thông báo *timeout* và gửi lại yêu cầu. **Lần đầu có thể đã commit hoặc chưa**. Nếu server tạo một đơn mới và trừ kho lần nữa, dữ liệu sẽ sai; nếu server luôn bỏ qua yêu cầu lặp, đơn có thể bị mất khi lần đầu thật sự rollback.

Đây là lý do **timeout khi ghi** không chỉ là vấn đề cấu hình thời gian chờ. Nó là bài toán kết hợp **transaction, trạng thái không chắc chắn, idempotency, concurrency, xử lý lỗi kết nối và quan sát được kết quả nghiệp vụ**.

Bài thuộc chương **Thực hành tổng hợp** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ thiết kế một lab Java + JDBC + PostgreSQL có thể chuyển ý tưởng thành mã kiểm thử: tạo schema với ràng buộc, gửi request cùng khóa lũy đẳng, chủ động gây lỗi ở các thời điểm khác nhau, xác minh trạng thái sau retry và rút ra quy tắc phục hồi. Những nguyên lý này cũng áp dụng khi dùng Spring Data JPA/Hibernate, dù ví dụ SQL/JDBC được ưu tiên để nhìn rõ ranh giới giao dịch.

**Phạm vi:** đây là môi trường lab trên database dùng để thử nghiệm, không phải kịch bản phá kết nối hoặc inject timeout vào production. Các đoạn mã Java/SQL minh họa các thành phần thực tế và cần ghép vào dự án có dependencies/cấu hình tương ứng. Mọi bài kiểm thử gây lỗi chỉ chạy trên tài nguyên bạn được phép điều khiển.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt timeout **khi mượn connection**, **khi kết nối**, **khi thực thi SQL**, **khi chờ khóa**, **khi đọc response** và **quanh COMMIT**.
2. Giải thích tại sao một `SQLException` hoặc HTTP 504 **không đủ chứng minh thao tác ghi đã rollback**.
3. Phát biểu invariant nghiệp vụ và chính sách trả kết quả khi request được gửi nhiều lần.
4. Thiết kế `request_id`/idempotency key ổn định, fingerprint của payload và unique constraint.
5. Thực hiện claim khóa và cập nhật nghiệp vụ **trong một transaction**, lưu outcome thành công hoặc bị từ chối có chủ đích.
6. Xử lý hai request cùng khóa chạy đồng thời mà không trừ tồn kho hai lần.
7. Phân biệt retry an toàn với cách “retry mọi SQLException”.
8. Mô phỏng lỗi *trước commit*, *sau commit nhưng mất xác nhận*, và đồng thời nhiều request.
9. Dùng Testcontainers/JUnit để kiểm tra dữ liệu thật sau lỗi, thay vì chỉ mock repository.
10. Mở rộng thiết kế sang HTTP, Spring `@Transactional`, outbox, connection pool, logging và runbook vận hành.

## 2. Tình huống thực hành và hợp đồng nghiệp vụ

Giả sử dịch vụ `checkout` có đầu vào:

~~~json
{
  "requestId": "c6a7b947-68d1-4824-98b9-50b13b296951",
  "customerId": 42,
  "sku": "BOOK-01",
  "quantity": 2
}
~~~

`requestId` là **một UUID v4 ngẫu nhiên đủ khó đoán, được giữ nguyên cho mọi lần thử cùng một ý định đặt hàng**. Nó không phải ID mới cho mỗi HTTP retry. Người gọi cần gửi request ID đã tạo ban đầu, kể cả sau khi kết nối đứt hoặc app restart.

Trong ví dụ lab:

- `inventory(sku, available)` lưu tồn kho.
- `checkout_requests` ghi nhận một ý định và kết quả cuối cùng của nó.
- `orders` lưu đơn hàng.
- `outbox_events` lưu thông điệp sẽ được phát sau khi DB commit.
- Tất cả ghi trong cùng **một PostgreSQL transaction**.

### 2.1. Các bất biến phải giữ

1. **Không trừ tồn kho hai lần cho một `requestId`.**
2. **Một `requestId` chỉ có một kết quả nghiệp vụ cuối cùng**: `SUCCEEDED` hoặc `REJECTED`.
3. **Không tái sử dụng khóa cho payload khác**: nếu cùng request ID nhưng customer/SKU/số lượng khác, trả conflict.
4. Với `SUCCEEDED`, một đơn và một outbox event tương ứng đã được lưu trong cùng transaction.
5. Tồn kho không âm và số lượng đặt phải dương.
6. Nếu một transaction rollback, không được để lại hàng ghi “đã xử lý” khiến retry bị bỏ mất.
7. Nếu database đã commit nhưng phản hồi tới caller bị mất, retry cùng khóa phải trả lại kết quả đã ghi chứ không tạo tác dụng phụ mới.

Ta đang thiết kế **at-most-once business effect cho mỗi khóa lũy đẳng còn được giữ**, trên một database và một đường ghi được kiểm soát. Điều đó **không** chứng minh “exactly-once” cho mọi hệ ngoài, mọi client hay vô thời hạn.

### 2.2. Hai khái niệm lũy đẳng

**Lũy đẳng về trạng thái:** thực hiện lại thao tác với cùng mã ý định không làm thay đổi kết quả cuối thêm lần nữa.

**Lũy đẳng về phản hồi:** caller lặp lại cùng khóa/payload nhận cùng outcome đã được lưu, chẳng hạn order ID hoặc mã từ chối. Điều này hữu ích vì client cần biết lần đầu có thành công không, không chỉ biết “hệ thống chưa bị trừ kho hai lần”.

Ví dụ:

~~~text
Lần 1:
  requestId = R1, sku = BOOK-01, qty = 2
  -> SUCCEEDED(orderId=R1)
  -> COMMIT

Lần 2:
  requestId = R1, cùng payload
  -> SUCCEEDED(orderId=R1) từ ledger
  -> không UPDATE inventory nữa

Lần 3:
  requestId = R1, qty = 5
  -> CONFLICT: idempotency key reused with different payload
  -> không UPDATE inventory
~~~

Ở đây `orderId=R1` là lựa chọn đơn giản cho lab. Hệ thật có thể dùng order ID riêng và lưu mapping `request_id → order_id`; điều quan trọng là mapping phải được lưu nguyên tử với hiệu ứng.

## 3. Hiểu thời điểm timeout trước khi chọn retry

### 3.1. Không phải timeout nào cũng có cùng kết luận

| Điểm timeout | Điều đã biết | Điều **không** thể tự kết luận |
|---|---|---|
| Chờ pool cấp connection | Không lấy được connection trong lượt gọi đó | Không có công việc khác với cùng request ID đang xử lý |
| Thiết lập TCP/TLS tới DB | Kết nối mới có thể chưa hình thành | Trạng thái của một request cũ đã gửi trước đó |
| Chờ row lock | SQL có thể chưa cập nhật được hàng mục tiêu | Toàn bộ transaction có rollback chưa |
| `statement_timeout` tại PostgreSQL | Statement bị DB hủy; transaction có thể ở trạng thái lỗi | Mọi side effect ngoài DB cũng bị đảo |
| Driver socket/read timeout | Client không nhận response đúng hạn | DB đã hoặc chưa thực thi/commit |
| Đứt mạng quanh `COMMIT` | Caller không nhận được ACK đáng tin | COMMIT chắc chắn thất bại |
| HTTP gateway timeout | Gateway không có phản hồi kịp | Server/backend đã hay chưa hoàn thành nghiệp vụ |

Một HTTP 504 có thể xảy ra sau khi DB commit thành công vì web server chưa gửi response. Ngược lại, một timeout SQL trước commit có thể làm transaction rollback. **HTTP status và exception class là bằng chứng về đường truyền/phản hồi, không phải oracle về dữ liệu đã commit.**

### 3.2. Timeline của kết quả không chắc chắn

~~~text
Ứng dụng Java             PostgreSQL
      |                       |
      | BEGIN                 |
      |---------------------->|
      | INSERT ledger         |
      | UPDATE stock          |
      | INSERT order/outbox   |
      |---------------------->|
      |                       | các lệnh thành công trong transaction
      | COMMIT                |
      |---------------------->|
      X mất connection         | COMMIT có thể đã hoàn tất
      |                       |
      | SQLException/timeout  |
      |                       |
      v
Caller KHÔNG BIẾT kết quả cuối

Retry cùng request ID trên connection mới
     -> DB unique key + ledger
     -> hoặc thấy outcome đã commit,
        hoặc thực thi một lần mới nếu trước đó rollback.
~~~

Khoảng mơ hồ được gọi là **ambiguous commit**. Kể cả khi Java bắt exception tại `commit()`, cũng không thể dựa vào catch block để suy ra DB chưa commit. Một lần `rollback()` sau đó có thể không đến được server, hoặc không thể đảo transaction đã commit.

### 3.3. Timeout, cancellation và retry khác nhau

- **Timeout** chỉ ra một giới hạn thời gian đã bị vượt qua tại một tầng.
- **Cancellation** có thể yêu cầu DB hủy statement còn đang chạy, nhưng thời điểm áp dụng và trạng thái transaction phụ thuộc driver/DBMS.
- **Retry** là gửi lại một yêu cầu; nếu yêu cầu có tác dụng ghi, nó cần chính sách lũy đẳng.
- **Reconciliation** là đọc lại từ nguồn có thẩm quyền để xác nhận kết quả khi phản hồi bị thiếu.

Không gộp bốn hoạt động thành một vòng lặp `catch(Exception) { executeAgain(); }`.

## 4. Phân loại lỗi PostgreSQL/JDBC khi thử lại

JDBC phơi bày `SQLException.getSQLState()`, `getErrorCode()`, chain `getNextException()` và cause. Đây là đầu vào để phân loại, nhưng cần kết hợp với **thời điểm xảy ra lỗi và tính lũy đẳng của use case**.

| Nhóm lỗi | Ví dụ PostgreSQL/JDBC | Chính sách |
|---|---|---|
| Serialization failure | SQLSTATE `40001` | Rollback và chạy lại **toàn transaction** khi idempotent |
| Deadlock detected | `40P01` | Rollback; retry có giới hạn và backoff/jitter |
| Statement canceled | `57014`, có thể do `statement_timeout` | Xác minh trạng thái transaction; không retry mù side effects |
| Unique violation | `23505` | Thường là conflict nghiệp vụ; phân biệt idempotency key trùng hợp lệ |
| Foreign key/check violation | `23503`/`23514` | Lỗi dữ liệu/logic; không retry nguyên dữ liệu vô hạn |
| Connection exception | SQLSTATE class `08` | Có thể không biết công việc đã tới đâu; thử lại **cùng khóa** |
| Lock not available/timeout | Ví dụ `55P03` trong PostgreSQL | Rollback/retry theo budget, quan sát contention |
| SQL syntax/schema mismatch | Ví dụ `42xxx` | Sửa code/migration; không retry liên tục |
| Pool timeout | Exception của pool | Xem tải/pool và deadline; không suy ra request ID chưa được xử lý |

Không dùng danh sách trên như bảng tra tuyệt đối cho mọi JDBC driver. Một lỗi mạng có thể được wrap trong exception của Spring/Hibernate hoặc xảy ra khi đóng connection, và không phải mọi trạng thái cho phép retry. Cần giữ nguyên cause, SQLSTATE và metadata an toàn để hỗ trợ điều tra.

### 4.1. Ngân sách retry

Một retry policy thực tế cần giới hạn:

- Tổng deadline end-to-end của request.
- Số lần retry tối đa.
- Backoff tăng dần và jitter để tránh retry storm.
- Giới hạn concurrency và connection pool.
- Điều kiện retry riêng theo exception + operation type.
- Thống kê lần đầu/đã replay/tranh chấp/đã từ chối.

Không sleep lâu khi đang giữ transaction, connection hoặc row lock. Retry nên bắt đầu bằng transaction/connection mới sau khi lần trước đã được kết thúc hoặc kết quả không chắc chắn được xử lý qua khóa lũy đẳng.

## 5. Thiết kế bảng dữ liệu cho lab

Các lệnh PostgreSQL sau được chạy trên **database lab sạch**. Chúng không phải migration production và không nên áp dụng trực tiếp lên bảng thật.

### 5.1. Tồn kho

~~~sql
CREATE TABLE inventory (
    sku       TEXT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

INSERT INTO inventory (sku, available)
VALUES ('BOOK-01', 10), ('PEN-02', 3);
~~~

Tồn kho không âm được bảo vệ bởi `CHECK` ngay cả khi một đường ghi khác đi qua raw SQL. Tuy nhiên, constraint không thay điều kiện concurrency trên phép trừ; ứng dụng vẫn cần cập nhật có điều kiện.

### 5.2. Ledger cho idempotency

~~~sql
CREATE TABLE checkout_requests (
    request_id   UUID PRIMARY KEY,
    payload_hash CHAR(64) NOT NULL,
    outcome      TEXT NOT NULL
                 CHECK (outcome IN ('STARTED', 'SUCCEEDED', 'REJECTED')),
    order_id     UUID,
    reject_code  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at  TIMESTAMPTZ,
    CONSTRAINT checkout_outcome_shape CHECK (
        (outcome = 'STARTED'
            AND order_id IS NULL
            AND reject_code IS NULL
            AND finished_at IS NULL)
        OR
        (outcome = 'SUCCEEDED'
            AND order_id IS NOT NULL
            AND reject_code IS NULL
            AND finished_at IS NOT NULL)
        OR
        (outcome = 'REJECTED'
            AND order_id IS NULL
            AND reject_code IS NOT NULL
            AND finished_at IS NOT NULL)
    )
);
~~~

**Các trạng thái trong lab:**

- `STARTED`: hàng ledger mới được insert bên trong transaction, **chưa được commit**.
- `SUCCEEDED`: nghiệp vụ đã hoàn tất, order/outbox tồn tại trong cùng transaction.
- `REJECTED`: từ chối nghiệp vụ có chủ đích, ví dụ thiếu tồn kho, đã được commit để retry giữ cùng kết quả.

Ứng dụng chỉ cho phép `COMMIT` sau khi outcome đã chuyển từ `STARTED` sang trạng thái cuối. Vì vậy, trong đường chuẩn, transaction khác **không bao giờ nhìn thấy `STARTED` đã commit**. Nếu nó xuất hiện trong dữ liệu đã commit, đó là trạng thái bất thường cần cảnh báo/điều tra, không nên mặc định “đang xử lý, cứ trừ kho lại”.

### 5.3. Đơn hàng và outbox

~~~sql
CREATE TABLE orders (
    order_id    UUID PRIMARY KEY,
    request_id  UUID NOT NULL UNIQUE
                REFERENCES checkout_requests(request_id),
    customer_id BIGINT NOT NULL CHECK (customer_id > 0),
    sku         TEXT NOT NULL REFERENCES inventory(sku),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    state       TEXT NOT NULL DEFAULT 'PENDING_PAYMENT'
                CHECK (state IN ('PENDING_PAYMENT', 'PAID', 'CANCELED')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id    UUID PRIMARY KEY,
    request_id  UUID NOT NULL UNIQUE
                REFERENCES checkout_requests(request_id),
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
~~~

Đây là một checkout chỉ chứa **một SKU** và phát một event cho mỗi request. Hệ thực cần thêm tenant/authorization, giá tiền được chốt, reservation, inventory movement ledger, payment state, audit và nhiều dòng order tùy yêu cầu.

Bảo đảm ở mức database:

- `request_id` unique trong ledger.
- Một request chỉ có tối đa một order.
- Một request chỉ có tối đa một outbox event (theo mô hình lab).
- Các foreign key liên kết kết quả với request.
- State và số lượng theo miền đã xác định.

### 5.4. Không đồng nhất request ID với nguồn xác thực

Một UUID khó đoán **không phải quyền truy cập**. API vẫn phải xác thực và kiểm tra customer/tenant. Khóa lũy đẳng nên được gắn với principal/tenant đã xác thực. Trong demo, request UUID là global unique; ở hệ nhiều tenant, có thể dùng `PRIMARY KEY (tenant_id, request_id)` và scope tất cả truy vấn theo tenant.

Nếu hai khách cùng dùng một ID nhưng payload khác, không được trả kết quả của người kia như thể họ có quyền xem đơn. Fingerprint giúp nhận ra payload conflict; **authorization vẫn phải được kiểm tra riêng**.

## 6. Chọn transaction boundary trước khi viết vòng retry

Với một yêu cầu đặt hàng, các bước phải nằm trong cùng transaction:

~~~mermaid
flowchart TD
    A["Nhận requestId + payload"] --> B["BEGIN transaction"]
    B --> C{"Claim idempotency key bằng unique INSERT"}
    C -->|"Đã tồn tại"| D["Đọc outcome + so fingerprint"]
    D --> E["COMMIT / đóng transaction; trả kết quả cũ"]
    C -->|"Mới"| F["UPDATE tồn kho có điều kiện"]
    F --> G{"Đủ hàng?"}
    G -->|"Không"| H["Ghi REJECTED vào ledger"]
    G -->|"Có"| I["INSERT order + outbox"]
    I --> J["Ghi SUCCEEDED vào ledger"]
    H --> K["COMMIT"]
    J --> K
    K --> L["Trả outcome"]
~~~

**Điểm then chốt:** cả claim, trừ kho, tạo order, ghi outbox và lưu outcome thuộc **một DB transaction**. Không được commit `STARTED` ở một transaction rồi mới thực hiện nghiệp vụ trong transaction khác mà không có lease/recovery protocol rõ ràng.

Nếu transaction rollback, ledger mới của request cũng rollback. Nếu commit thành công, ledger và tác dụng nghiệp vụ cùng xuất hiện. Đây là nền tảng để retry an toàn khi client không nhận được phản hồi.

### 6.1. Tại sao `INSERT ... ON CONFLICT DO NOTHING` giúp điều phối cùng khóa?

PostgreSQL:

~~~sql
INSERT INTO checkout_requests (
    request_id, payload_hash, outcome
)
VALUES (?, ?, 'STARTED')
ON CONFLICT (request_id) DO NOTHING;
~~~

Ứng dụng kiểm tra `executeUpdate()`:

- `1`: request ID chưa có hàng committed cạnh tranh thành công; transaction này có quyền xử lý ý định mới.
- `0`: hàng cùng request ID đã tồn tại/được transaction khác commit, cần **đọc ledger và so fingerprint**.

Nếu hai transaction cố insert cùng request ID đồng thời, unique constraint có thể khiến một transaction **chờ** transaction còn lại commit hoặc rollback. Nếu bên đầu commit, bên thứ hai không insert và đọc kết quả đã có; nếu bên đầu rollback, bên sau có thể insert và xử lý ý định.

Tính chất này cần được kiểm thử trên PostgreSQL với mức isolation được thiết kế, ví dụ `READ COMMITTED`. Trong PostgreSQL `READ COMMITTED`, câu SELECT tiếp theo nhận snapshot mới và có thể thấy hàng đã commit sau khi lệnh INSERT chờ xung đột kết thúc. Không giả định kỹ thuật này giống hệt ở mọi DBMS hoặc mọi mức isolation.

### 6.2. Không lấy `SELECT exists` làm cơ chế khóa chính

Cách dễ sai:

~~~text
T1: SELECT request_id -> không có
T2: SELECT request_id -> không có
T1: tạo order
T2: tạo order
T1: insert ledger
T2: insert ledger -> lỗi trùng, nhưng side effect khác có thể đã commit
~~~

Kiểm tra tồn tại trước có thể hữu ích cho UX, nhưng không thay thế **unique constraint và atomic claim**. Đặc biệt nếu các thao tác ở những transaction khác nhau, side effect có thể đã phát ra trước khi phát hiện trùng.

### 6.3. Trừ tồn kho bằng điều kiện ngay tại DB

~~~sql
UPDATE inventory
SET available = available - ?
WHERE sku = ?
  AND available >= ?;
~~~

Ứng dụng bind số lượng hai lần và SKU một lần. Nếu affected-row count = 1, lượng tồn đã được trừ trong transaction. Nếu count = 0, SKU có thể không tồn tại hoặc không đủ hàng; ví dụ đơn giản trả `REJECTED/OUT_OF_STOCK` và commit outcome này vào ledger.

Hai request có ID **khác nhau** vẫn cạnh tranh đúng theo điều kiện tồn kho; việc lũy đẳng theo request ID không thay thế kiểm soát oversell giữa các khách khác nhau.

### 6.4. Ghi từ chối có chủ đích khác rollback do lỗi hạ tầng

Với thiếu hàng, hệ có thể muốn retry cùng key tiếp tục nhận `REJECTED` ngay cả sau khi cửa hàng nhập thêm. Khi đó phải **commit outcome REJECTED**.

Với lỗi kết nối/DB timeout, **không ghi kết quả REJECTED giả**; không biết nghiệp vụ đã commit hay chưa. Hãy để transaction rollback nếu có thể, hoặc coi kết quả không chắc chắn và retry cùng key/đối soát từ database mới.

Nếu sản phẩm muốn “thử lại khi hàng về”, client phải tạo **ý định mới với request ID mới**. Chính sách có lưu kết quả từ chối lâu dài hay không là quyết định API cần được công bố rõ.

## 7. Implement lab với JDBC: một lần thực thi có lũy đẳng

Trong lab, ứng dụng dùng JDBC trực tiếp để phân biệt rõ transaction của database với lời gọi Java. Ví dụ Java 17+ dùng `record` và `HexFormat`, PostgreSQL JDBC driver, và một `DataSource` cấp kết nối.

### 7.1. Payload fingerprint phải ổn định

Chỉ so `requestId` là chưa đủ. Một client có thể vô tình gửi cùng khóa nhưng thay `sku`, `quantity` hoặc `customerId`. Nếu server trả lại outcome cũ mà không kiểm tra payload, kết quả có thể bị hiểu sai hoặc bị lạm dụng.

Fingerprint cần dựa trên **các trường ảnh hưởng ý nghĩa nghiệp vụ**, có encoding xác định. Đừng dùng `Object.toString()`, thứ tự thuộc tính JSON không ổn định hoặc nối chuỗi có dấu phân tách dễ va chạm.

Trong lab:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class CheckoutFingerprint {
    private CheckoutFingerprint() {}

    public static String of(long customerId, String sku, int quantity) {
        byte[] skuBytes = sku.getBytes(StandardCharsets.UTF_8);
        ByteBuffer encoded = ByteBuffer.allocate(
            Long.BYTES + Integer.BYTES + skuBytes.length + Integer.BYTES
        );
        encoded.putLong(customerId);
        encoded.putInt(skuBytes.length);
        encoded.put(skuBytes);
        encoded.putInt(quantity);

        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            sha256.update("checkout:v1:".getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(
                sha256.digest(encoded.array())
            );
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(
                "JVM does not provide SHA-256", error
            );
        }
    }
}
~~~

Hàm này có tiền điều kiện `sku != null` và số lượng hợp lệ, do tầng request validation kiểm tra trước. Trong hệ nhiều tenant, cần đưa principal/tenant, currency, giá đã cam kết và những thuộc tính mang nghĩa nghiệp vụ vào phép so theo quy tắc được công bố.

**Hash không phải là authorization hay phương tiện ẩn danh hóa.** Một fingerprint ổn định có thể giúp đối chiếu payload, nhưng không cho phép ai có request ID đều được đọc đơn hàng; cần kiểm tra quyền. Nếu một số trường có số giá trị khả dĩ nhỏ, hash có thể bị dò bằng từ điển; tránh log hash/payload như thể chúng luôn không nhạy cảm.

### 7.2. API của service và điểm inject lỗi

Ta dùng một interface `CommitAction` chỉ để **tiêm hành vi mô phỏng** ở thời điểm commit trong unit/integration test. Production truyền `Connection::commit`.

~~~java
import java.sql.Connection;
import java.sql.SQLException;

@FunctionalInterface
public interface CommitAction {
    void commit(Connection connection) throws SQLException;
}
~~~

Trong file Java thật, interface có thể là kiểu top-level hoặc nested của service. Một implementation giả lập sẽ **thực sự commit rồi ném exception** để mô phỏng trường hợp server đã commit nhưng ACK bị mất.

Điều này không mô phỏng toàn bộ network protocol; nó kiểm tra **business-level recovery path** trước trạng thái commit mơ hồ. Muốn kiểm tra driver/pool khi socket đứt thật cần proxy mạng hoặc fault harness riêng.

### 7.3. Service thực thi với một transaction

Ví dụ cấu trúc hoàn chỉnh ở cấp lab. Để tập trung vào logic, các helper cho SQL đặt trong phần kế tiếp:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class CheckoutJdbcService {
    public record Request(
        UUID requestId, long customerId, String sku, int quantity
    ) {}

    public record Outcome(
        String status, UUID orderId, String rejectCode
    ) {}

    @FunctionalInterface
    public interface CommitAction {
        void commit(Connection connection) throws SQLException;
    }

    private final DataSource source;
    private final CommitAction commitAction;

    public CheckoutJdbcService(DataSource source) {
        this(source, Connection::commit);
    }

    public CheckoutJdbcService(
        DataSource source,
        CommitAction commitAction
    ) {
        this.source = source;
        this.commitAction = commitAction;
    }

    public Outcome place(Request req) throws SQLException {
        validate(req);
        String hash = CheckoutFingerprint.of(
            req.customerId(), req.sku(), req.quantity()
        );

        try (Connection connection = source.getConnection()) {
            // Lab dùng snapshot READ COMMITTED cho đường claim.
            if (connection.getTransactionIsolation()
                    != Connection.TRANSACTION_READ_COMMITTED) {
                throw new SQLException(
                    "This lab requires READ COMMITTED"
                );
            }

            connection.setAutoCommit(false);
            try {
                Outcome result;
                int claimed = claim(connection, req.requestId(), hash);

                if (claimed == 0) {
                    result = readPrevious(
                        connection, req.requestId(), hash
                    );
                } else if (claimed == 1) {
                    int changed = decrementStock(
                        connection, req.sku(), req.quantity()
                    );

                    if (changed == 0) {
                        finishRejected(connection, req.requestId());
                        result = new Outcome(
                            "REJECTED", null, "OUT_OF_STOCK"
                        );
                    } else if (changed == 1) {
                        UUID orderId = req.requestId();
                        createOrder(connection, req, orderId);
                        createOutbox(connection, req, orderId);
                        finishSucceeded(
                            connection, req.requestId(), orderId
                        );
                        result = new Outcome(
                            "SUCCEEDED", orderId, null
                        );
                    } else {
                        throw new SQLException(
                            "Inventory UPDATE affected " + changed + " rows"
                        );
                    }
                } else {
                    throw new SQLException(
                        "Unexpected idempotency claim count: " + claimed
                    );
                }

                // Có thể commit thành công rồi mất phản hồi.
                commitAction.commit(connection);
                return result;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                // Rollback sau lỗi COMMIT không chứng minh
                // lần COMMIT trước đó chưa hoàn tất.
                throw failure;
            }
        }
        // try-with-resources đóng connection/hoàn trả pool.
        // DataSource/pool phải reset connection state đúng.
    }

    private static void validate(Request req) {
        if (req == null
                || req.requestId() == null
                || req.customerId() <= 0
                || req.sku() == null
                || req.sku().isBlank()
                || req.sku().length() > 128
                || req.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid checkout request"
            );
        }
    }

    // Các hàm claim/readPrevious/decrementStock/createOrder/
    // createOutbox/finishRejected/finishSucceeded bên dưới
    // nằm trong cùng class khi triển khai thực tế.
}
~~~

**Điểm cần chú ý:**

- Trong JDBC, `setAutoCommit(false)` mở chế độ giao dịch tường minh khi các statement được thực hiện; không cần gửi thêm chuỗi SQL `BEGIN` khi driver quản lý transaction như ví dụ.
- Mọi helper nhận **cùng một `Connection`**. Không được tự mở connection mới trong mỗi repository helper vì như vậy sẽ phá atomicity.
- Code kiểm tra `READ COMMITTED` để điều kiện đọc ledger sau conflict có hành vi được kỳ vọng. Ở hệ thật, điều phối isolation qua cấu hình DataSource/transaction manager và xác minh trên DBMS thực.
- Sau lỗi có thể thử `rollback()` để dọn transaction chưa commit, nhưng **không được lấy kết quả rollback làm bằng chứng COMMIT trước đó chưa diễn ra**.
- Nếu đóng connection/pool trả lỗi sau commit thành công, caller vẫn có thể nhận exception; retry bằng cùng khóa vẫn phải an toàn.
- Chúng ta không tự đặt transaction mới bên trong vòng retry bằng cách reuse entity manager/session đã lỗi.
- Interface `CommitAction` chỉ là seam kiểm thử, không yêu cầu application production expose một endpoint “làm mất ACK”.

### 7.4. Helper claim và đọc kết quả đã có

Các method sau thuộc `CheckoutJdbcService` trong ví dụ.

~~~java
private static int claim(
        Connection c, UUID requestId, String hash
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        INSERT INTO checkout_requests (
            request_id, payload_hash, outcome
        )
        VALUES (?, ?, 'STARTED')
        ON CONFLICT (request_id) DO NOTHING
        """)) {
        ps.setObject(1, requestId);
        ps.setString(2, hash);
        return ps.executeUpdate();
    }
}

private static Outcome readPrevious(
        Connection c, UUID requestId, String expectedHash
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        SELECT payload_hash, outcome, order_id, reject_code
        FROM checkout_requests
        WHERE request_id = ?
        """)) {
        ps.setObject(1, requestId);
        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                // Có thể gặp ở trường hợp snapshot/isolation không
                // được thiết kế đúng hoặc DB/driver bất thường.
                throw new SQLException(
                    "Conflict observed without visible ledger row"
                );
            }
            String storedHash = rs.getString("payload_hash");
            if (!expectedHash.equals(storedHash)) {
                throw new IllegalArgumentException(
                    "IDEMPOTENCY_KEY_PAYLOAD_CONFLICT"
                );
            }

            String status = rs.getString("outcome");
            UUID orderId =
                (UUID) rs.getObject("order_id");
            String reason = rs.getString("reject_code");

            if (!status.equals("SUCCEEDED")
                    && !status.equals("REJECTED")) {
                throw new IllegalStateException(
                    "Committed non-terminal checkout request"
                );
            }
            return new Outcome(status, orderId, reason);
        }
    }
}
~~~

Trong file Java đầy đủ phải import `java.sql.PreparedStatement` và `java.sql.ResultSet` cùng các kiểu đã dùng.

Nếu `readPrevious` nhận `IDEMPOTENCY_KEY_PAYLOAD_CONFLICT`, caller nên map sang HTTP `409 Conflict` hoặc mã lỗi hợp đồng tương ứng, không tự tạo request mới. Nếu thấy ledger `STARTED` đã commit, đó là lỗi invariant: cần dừng xử lý và điều tra, không tiếp tục trừ kho như lần đầu.

Ở PostgreSQL, unique conflict có thể làm câu insert chờ transaction khác hoàn tất. Nếu bị `lock_timeout` hoặc deadline trước khi hoàn tất, service **chưa có outcome đáng tin**, cần đóng/rollback transaction hiện tại rồi thử lại với cùng khóa và budget.

### 7.5. Helper trừ kho và ghi đơn

~~~java
private static int decrementStock(
        Connection c, String sku, int quantity
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        UPDATE inventory
        SET available = available - ?
        WHERE sku = ?
          AND available >= ?
        """)) {
        ps.setInt(1, quantity);
        ps.setString(2, sku);
        ps.setInt(3, quantity);
        return ps.executeUpdate();
    }
}

private static void createOrder(
        Connection c, Request req, UUID orderId
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        INSERT INTO orders (
            order_id, request_id, customer_id,
            sku, quantity, state
        ) VALUES (?, ?, ?, ?, ?, 'PENDING_PAYMENT')
        """)) {
        ps.setObject(1, orderId);
        ps.setObject(2, req.requestId());
        ps.setLong(3, req.customerId());
        ps.setString(4, req.sku());
        ps.setInt(5, req.quantity());
        requireOne(ps.executeUpdate(), "create order");
    }
}

private static void createOutbox(
        Connection c, Request req, UUID orderId
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        INSERT INTO outbox_events (
            event_id, request_id, event_type, payload
        )
        VALUES (
            ?, ?, 'OrderPlaced',
            jsonb_build_object(
                'orderId', CAST(? AS TEXT),
                'sku', CAST(? AS TEXT),
                'quantity', CAST(? AS INTEGER)
            )
        )
        """)) {
        // Lab: một event duy nhất mỗi checkout request.
        ps.setObject(1, req.requestId());
        ps.setObject(2, req.requestId());
        ps.setString(3, orderId.toString());
        ps.setString(4, req.sku());
        ps.setInt(5, req.quantity());
        requireOne(ps.executeUpdate(), "create outbox event");
    }
}

private static void requireOne(
        int affected, String action
) throws SQLException {
    if (affected != 1) {
        throw new SQLException(
            action + " affected " + affected + " rows"
        );
    }
}
~~~

Dữ liệu outbox cố tình **không chứa email, token thanh toán hoặc dữ liệu cá nhân**. Nếu business event cần trường nhạy cảm, thiết kế field-level security và retention riêng. Việc outbox đã commit không có nghĩa event đã publish; relay còn phải xử lý send-at-least-once/deduplication.

### 7.6. Helper hoàn tất outcome

~~~java
private static void finishSucceeded(
        Connection c, UUID requestId, UUID orderId
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        UPDATE checkout_requests
        SET outcome = 'SUCCEEDED',
            order_id = ?,
            finished_at = CURRENT_TIMESTAMP
        WHERE request_id = ?
          AND outcome = 'STARTED'
        """)) {
        ps.setObject(1, orderId);
        ps.setObject(2, requestId);
        requireOne(ps.executeUpdate(), "finish success");
    }
}

private static void finishRejected(
        Connection c, UUID requestId
) throws SQLException {
    try (PreparedStatement ps = c.prepareStatement(
        """
        UPDATE checkout_requests
        SET outcome = 'REJECTED',
            reject_code = 'OUT_OF_STOCK',
            finished_at = CURRENT_TIMESTAMP
        WHERE request_id = ?
          AND outcome = 'STARTED'
        """)) {
        ps.setObject(1, requestId);
        requireOne(ps.executeUpdate(), "finish rejection");
    }
}
~~~

Khi `finishSucceeded`/`finishRejected` trả count bất thường, service ném lỗi và rollback transaction đang chạy. Không nên cố commit dù trạng thái ledger chưa ở trạng thái cuối.

### 7.7. Quy trình thực tế khi kết nối bị mất

Ví dụ gọi:

~~~java
CheckoutJdbcService store = new CheckoutJdbcService(dataSource);

CheckoutJdbcService.Request request =
    new CheckoutJdbcService.Request(
        UUID.fromString(
            "c6a7b947-68d1-4824-98b9-50b13b296951"
        ),
        42L,
        "BOOK-01",
        2
    );

CheckoutJdbcService.Outcome result = store.place(request);
~~~

Nếu `store.place` ném lỗi kết nối tại thời điểm commit hoặc một thời điểm chưa rõ, đừng tạo `new UUID()` cho retry. Hãy giữ `request.requestId()` và các trường payload cố định để gọi lại trên một lượt mới. Lượt tiếp theo dựa trên unique ledger và trạng thái DB để xác định đã thực hiện hay chưa.

## 8. Ví dụ phản chứng: thiết kế retry không lũy đẳng

### 8.1. Mỗi lần retry tạo order ID mới

~~~java
public UUID wrongPlaceOrder(String sku, int quantity) {
    UUID orderId = UUID.randomUUID();

    // Giả định UPDATE và INSERT dưới đây được gửi tới DB.
    inventoryDao.decrement(sku, quantity);
    orderDao.insert(orderId, sku, quantity);

    return orderId;
}
~~~

Nếu lần đầu commit nhưng response bị mất, lần thử thứ hai tạo `orderId` khác và có thể trừ kho hai lần.

Một vòng lặp retry bên ngoài:

~~~java
for (int attempt = 0; attempt < 3; attempt++) {
    try {
        return wrongPlaceOrder(sku, quantity);
    } catch (SQLException timeout) {
        // Sai: tạo order ID mới ở lần sau.
    }
}
~~~

Ngoài việc ví dụ là pseudo-code (chưa biên dịch nguyên trạng vì cách khai báo exception), nguyên tắc sai ở đây là **mỗi attempt trở thành một ý định mới**. Chỉ thêm backoff không sửa được.

### 8.2. Ghi ledger bằng transaction khác

~~~text
TX1: INSERT checkout_requests(R1, STARTED); COMMIT
TX2: trừ kho + tạo order; chưa kịp COMMIT thì process crash
Retry R1: thấy STARTED, không biết nên làm lại hay trả gì
~~~

Thiết kế này không sai trong mọi hệ thống; một hàng `PROCESSING` được commit có thể là một **job lease/workflow** hợp lệ. Nhưng để dùng nó, phải có owner/lease expiry, fencing token, recovery state machine và đối soát side effects. Với lab transactional checkout đơn giản, gộp ledger và hiệu ứng trong cùng transaction tránh sự phức tạp đó.

### 8.3. Chỉ unique order mà quên trừ kho

Nếu `orders.request_id` unique nhưng Java trừ kho ở transaction khác trước khi chèn order, retry có thể trừ kho lần hai rồi gặp unique violation ở lệnh INSERT. Unique constraint chỉ bảo vệ những thao tác thực sự nằm trong **transaction và thứ tự được thiết kế đúng**.

Tương tự, ghi outbox ở một connection auto-commit riêng có thể tạo event cho một đơn đã rollback, hoặc làm mất event khi order đã commit. “Có unique ở một bảng” không thay thế atomic boundary.

## 9. Không coi tất cả retry là giống nhau

### 9.1. Retry trong cùng transaction là sai

Khi một transaction PostgreSQL gặp lỗi statement, nó có thể ở trạng thái aborted; nhiều câu SQL sau sẽ thất bại cho tới khi rollback (hoặc xử lý savepoint phù hợp). Không thực hiện:

~~~text
BEGIN
  statement timeout / deadlock
  catch exception
  tiếp tục UPDATE/INSERT trong chính transaction lỗi
  COMMIT như không có gì xảy ra
~~~

Sau deadlock/serialization failure, DB đã chọn rollback/hủy một transaction. Cần tạo **transaction mới** để thực hiện lại toàn thao tác nghiệp vụ nếu được phép.

### 9.2. Retry theo SQLSTATE nhưng không xem SQLSTATE là toàn bộ câu trả lời

Một policy khái niệm:

~~~text
40001 / 40P01:
  rollback, retry transaction mới (idempotent), có backoff.

08xxx / mất connection quanh commit:
  kết quả không chắc chắn, retry cùng requestId
  trên connection mới hoặc đối soát ledger.

23505:
  xem unique constraint nào, có phải idempotency key trùng
  hay là conflict data không hợp lệ; không retry mù.

57014 / statement cancel:
  xem statement nào bị cancel và transaction state;
  rollback và chỉ retry nếu deadline/budget cho phép.

Lỗi schema/validation:
  báo lỗi hoặc xử lý dữ liệu; không retry vô hạn.
~~~

Một exception có thể chứa nhiều nguyên nhân ở `getCause()` và `getNextException()`. Không phân loại bằng cách tìm chuỗi `"timeout"` trong message do driver trả; đó là một tín hiệu yếu và có thể thay đổi theo ngôn ngữ/version.

### 9.3. Đừng retry cả HTTP request lẫn DB thao tác vô hạn

Nếu API gateway, HTTP client và repository layer đều có retry, số lần thực thi có thể nhân lên. Ví dụ gateway thử 3 lần, client thử 3 lần và tầng DB thử 3 lần có thể tạo tới 27 lượt attempt trong các điều kiện lỗi.

Nên phân quyền retry rõ:

- Client retry cùng `requestId` theo deadline của user.
- Server retry một số lỗi transaction trong budget hẹp.
- Gateway biết giới hạn và không đổi payload/idempotency key.
- Các tầng ghi lại attempt count và tránh retry storm.
- Kết quả `REJECTED` cuối cùng được trả ổn định, không tự đổi thành success trên retry cùng khóa.

### 9.4. Backoff có jitter

Một ví dụ số học để **mô tả** backoff, không phải cấu hình production được khuyến nghị:

~~~text
Attempt 1: ngay
Attempt 2: sau ~100-250 ms
Attempt 3: sau ~200-500 ms
Attempt 4: sau ~400-1000 ms
Dừng khi vượt max attempts hoặc deadline.
~~~

Jitter làm phân tán các client đang cùng gặp sự cố. Nhưng việc tăng delay không làm phép ghi vốn không lũy đẳng trở nên an toàn. **Lũy đẳng là điều kiện tiên quyết, backoff là kiểm soát tải**.

## 10. Ma trận kiểm thử bắt buộc: kiểm tra dữ liệu sau timeout

Giả sử database lab vừa được reset, tồn kho `BOOK-01 = 10`. Các kịch bản dưới đây nên được chạy độc lập để không phụ thuộc trạng thái test trước.

| Test | Lần thử đầu | Lần thử tiếp theo | Kết quả mong đợi |
|---|---|---|---|
| T1 – bình thường | R1 đặt 2, commit | Không | Tồn 8, 1 order, 1 event, ledger SUCCEEDED |
| T2 – replay | R1 đặt 2, commit | R1 đặt 2 | Tồn vẫn 8, không thêm row |
| T3 – payload conflict | R1 đặt 2 | R1 đặt 3 | Conflict, không có tác dụng mới |
| T4 – thiếu hàng | R2 đặt 99 | R2 đặt 99 | REJECTED ổn định, tồn 10 |
| T5 – lỗi trước COMMIT | R3 đặt 2 rồi rollback | R3 đặt 2 | Lần đầu không còn row; lần hai thành công một lần |
| T6 – mất ACK sau COMMIT | R4 đã commit nhưng caller nhận exception | R4 đặt 2 | Trả SUCCEEDED cũ, không trừ kho thêm |
| T7 – đồng thời cùng khóa | Hai thread cùng R5 | Chạy song song | Một hiệu ứng, một outcome chung |
| T8 – hai khóa khác nhau | R6 và R7 cùng đặt 4, tồn chỉ 5 | Chạy song song | Một thành công, một bị từ chối, tồn 1 |
| T9 – SQL statement timeout | Server hủy statement | Transaction mới nếu được phép | Không tiếp tục transaction bị lỗi |
| T10 – lock timeout | Session B chờ khóa session A | Retry budget | Không giữ lock/pool vô hạn |

**Bằng chứng đúng:** đọc trạng thái database từ **connection mới**; không chỉ kiểm tra một exception được ném hoặc mock method được gọi đúng một lần. Với các test khác khóa, cần kiểm tra cả invariant tồn kho, ledger, số lượng đơn và sự kiện.

### 10.1. Các truy vấn đối soát

~~~sql
SELECT sku, available
FROM inventory WHERE sku = 'BOOK-01';

SELECT request_id, outcome, order_id, reject_code
FROM checkout_requests
WHERE request_id = 'c6a7b947-68d1-4824-98b9-50b13b296951';

SELECT COUNT(*) AS orders_for_request
FROM orders
WHERE request_id = 'c6a7b947-68d1-4824-98b9-50b13b296951';

SELECT COUNT(*) AS events_for_request
FROM outbox_events
WHERE request_id = 'c6a7b947-68d1-4824-98b9-50b13b296951';
~~~

Sau một request đặt 2 trên tồn 10 rồi retry cùng key: `available=8`, ledger `SUCCEEDED`, số đơn và event đều bằng 1. Nếu muốn kiểm tra toàn tính đúng đắn, còn đối chiếu `orders.quantity=2` và nội dung outbox theo `order_id` đã lưu.

### 10.2. Chuẩn bị database test sạch

Trong database lab được phép reset:

~~~sql
TRUNCATE TABLE outbox_events, orders, checkout_requests;

UPDATE inventory
SET available = 10
WHERE sku = 'BOOK-01';
~~~

Không đưa những lệnh reset vào môi trường production hoặc chạy với account có quyền trên bảng thật. Với CI, mỗi test nên có container, database hoặc schema độc lập; khi chia sẻ test database phải khóa lịch chạy/cleanup rõ ràng.

## 11. Fault injection A: thất bại trước COMMIT

### 11.1. Tạo lỗi tại seam commit

Dùng interface `CommitAction` ở mục 7, injection ném exception **trước** khi gọi `Connection.commit()`:

~~~java
CheckoutJdbcService.CommitAction failBeforeCommit =
    connection -> {
        throw new java.sql.SQLTransientConnectionException(
            "LAB: failed before COMMIT",
            "08006"
        );
    };

CheckoutJdbcService service =
    new CheckoutJdbcService(dataSource, failBeforeCommit);
~~~

Vì transaction chưa được commit, service sẽ bắt exception và cố rollback. Với connection PostgreSQL khỏe trong lab, rollback hoàn tất.

Kiểm tra sau lời gọi lỗi bằng một connection **khác**:

- Không có ledger R3.
- Không có order R3.
- Không có outbox event R3.
- Tồn kho vẫn là 10.

Sau đó dùng service bình thường và **cùng R3** gọi lại. Kỳ vọng chỉ tạo một đơn, một event và tồn còn 8. Đây là bài kiểm tra rằng **ledger chưa commit cũng bị rollback**, không tạo trạng thái “đã xử lý” giả.

### 11.2. PostgreSQL `statement_timeout`

Để nhìn thấy timeout thực sự ở DB:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '150ms';
SELECT pg_sleep(1);
-- Kỳ vọng statement bị hủy do timeout.
ROLLBACK;
~~~

`SET LOCAL` chỉ áp dụng trong transaction hiện tại. Sau lỗi statement ở PostgreSQL, transaction thông thường rơi vào trạng thái failed; cần rollback. Đoạn `pg_sleep` chỉ mô phỏng một statement chậm **không đổi dữ liệu**, không phải ambiguous commit.

Ví dụ Java:

~~~java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);

    try (Statement st = c.createStatement()) {
        st.execute("SET LOCAL statement_timeout = '150ms'");
        st.executeQuery("SELECT pg_sleep(1)");

        throw new AssertionError("Expected statement timeout");
    } catch (SQLException error) {
        if (!"57014".equals(error.getSQLState())) {
            throw error;
        }
        c.rollback();
    }
}
~~~

Các import `java.sql.Connection`, `Statement`, `SQLException` và biến `dataSource` cần được cung cấp trong harness. Chỉ cần một kiểu statement timeout đã chứng minh DB hủy câu lệnh và rollback path được thực thi; **nó không chứng minh** driver/HTTP xử lý mất xác nhận COMMIT an toàn.

### 11.3. Hai connection và `lock_timeout`

Mở hai session:

~~~sql
-- Session A:
BEGIN;
UPDATE inventory SET available = available
WHERE sku = 'BOOK-01';
-- Giữ transaction để chiếm row lock.

-- Session B:
BEGIN;
SET LOCAL lock_timeout = '200ms';
UPDATE inventory
SET available = available - 1
WHERE sku = 'BOOK-01' AND available >= 1;
-- Kỳ vọng lock timeout khi Session A còn giữ khóa.
ROLLBACK;

-- Session A:
ROLLBACK;
~~~

Đây là hai kết nối tách biệt, không được thực thi nối tiếp toàn bộ trên một connection. Khi inject lỗi thật, harness phải dọn khóa trong `finally` và có test timeout để tránh treo suite.

`lock_timeout` và `statement_timeout` không đồng nghĩa: timeout chờ khóa khác giới hạn thời gian thực thi toàn câu SQL. Trong cả hai trường hợp, việc thử lại ghi cần đi qua idempotency key và transaction mới theo policy.

## 12. Fault injection B: COMMIT đã thành công nhưng caller thấy lỗi

Đây là bài kiểm thử quan trọng nhất để chứng minh **lũy đẳng khi kết quả commit không chắc chắn**.

### 12.1. Cách mô phỏng chính xác tính chất nghiệp vụ

~~~java
CheckoutJdbcService.CommitAction commitThenLoseAck =
    connection -> {
        connection.commit();  // Server đã commit.

        throw new java.sql.SQLTransientConnectionException(
            "LAB: COMMIT succeeded but ACK was lost",
            "08006"
        );
    };

CheckoutJdbcService firstAttempt =
    new CheckoutJdbcService(dataSource, commitThenLoseAck);
~~~

Trong lab, `Connection.commit()` thực sự thành công trước khi exception được ném. Service sẽ đi qua catch/rollback cleanup nhưng **rollback này không thể xóa transaction đã commit**.

Đây là *application-level fault injection*: không mô phỏng byte-level TCP packet hay driver socket behavior. Để thử network thực có thể dùng proxy điều khiển lỗi như Toxiproxy, nhưng test socket có thể không cho phép chủ động chọn đúng thời điểm ACK; vì vậy seam sau-commit là cách **tái hiện được** nhánh nghiệp vụ quan trọng.

### 12.2. Lịch chạy và expected DB state

~~~text
Attempt 1, requestId=R4:
  BEGIN
  claim R4
  inventory 10 -> 8
  INSERT order(R4)
  INSERT outbox(R4)
  ledger R4 -> SUCCEEDED
  COMMIT thực sự thành công
  Tiêm SQLException trước khi trả response

Caller thấy lỗi, không biết kết quả thực.

Attempt 2, cùng requestId=R4 và payload:
  BEGIN
  INSERT ledger ON CONFLICT DO NOTHING -> 0
  SELECT existing R4 -> SUCCEEDED
  So fingerprint -> khớp
  COMMIT read-only/replay transaction
  Trả orderId=R4

Cuối cùng:
  inventory=8
  checkout_requests R4 = SUCCEEDED
  COUNT(orders WHERE request_id=R4)=1
  COUNT(outbox WHERE request_id=R4)=1
~~~

Nếu retry dùng `UUID.randomUUID()` mới thay vì giữ R4, test sẽ phát hiện trừ tồn kho và tạo đơn trùng. Nếu ledger ghi ở transaction riêng, test có thể phát hiện outcome sai/thiếu.

### 12.3. JUnit test seam giả lập mất ACK

Giả sử `dataSource` trỏ đến PostgreSQL test với schema và seed ở mục 5, cùng helper kiểm tra database:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.SQLTransientConnectionException;
import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void retryAfterLostCommitAckWritesOnlyOnce()
        throws Exception {
    UUID id = UUID.randomUUID();
    var request = new CheckoutJdbcService.Request(
        id, 42L, "BOOK-01", 2
    );

    var first = new CheckoutJdbcService(
        dataSource,
        c -> {
            c.commit();
            throw new SQLTransientConnectionException(
                "Simulated lost ACK", "08006"
            );
        }
    );

    assertThrows(
        SQLTransientConnectionException.class,
        () -> first.place(request)
    );

    // Caller không có thông tin chắc chắn về COMMIT lần đầu.
    var replay = new CheckoutJdbcService(dataSource);
    var result = replay.place(request);

    assertEquals("SUCCEEDED", result.status());
    assertEquals(id, result.orderId());
    assertNull(result.rejectCode());

    // assertDbState do test harness cài đặt bằng JDBC
    // đọc từ một connection khác, không đọc entity cache.
    assertDbState(dataSource, "BOOK-01", 8, id, 1, 1);
}
~~~

Đây là **method JUnit minh họa**, cần thêm `@BeforeEach`, `dataSource` và `assertDbState` từ dự án thực. Quan trọng là test **không đọc DB giữa hai lần gọi** để quyết định có retry hay không; hệ thống phải an toàn khi caller không thể biết kết quả.

### 12.4. Helper kiểm tra count theo request ID

~~~java
private static long countByRequest(
        Connection c, String table, UUID id
) throws SQLException {
    String sql = switch (table) {
        case "checkout_requests" ->
            "SELECT COUNT(*) FROM checkout_requests WHERE request_id = ?";
        case "orders" ->
            "SELECT COUNT(*) FROM orders WHERE request_id = ?";
        case "outbox_events" ->
            "SELECT COUNT(*) FROM outbox_events WHERE request_id = ?";
        default ->
            throw new IllegalArgumentException("Unknown test table");
    };

    try (PreparedStatement ps = c.prepareStatement(sql)) {
        ps.setObject(1, id);
        try (ResultSet rows = ps.executeQuery()) {
            rows.next();
            return rows.getLong(1);
        }
    }
}
~~~

`table` chỉ chọn từ allowlist của test, không nhận chuỗi tên bảng tùy ý của người dùng. Import JDBC `Connection`, `PreparedStatement`, `ResultSet` và `SQLException` cần có khi ghép thành test class.

Đừng chỉ so count một lần: với những bài test quan trọng, kiểm tra cả amount/quantity/state, fingerprint, stock và payload outbox để không bỏ sót trường hợp cùng số row nhưng giá trị bị sai.

## 13. Hai request cạnh tranh cùng khóa hoặc cùng tồn kho

### 13.1. Cùng một khóa, hai thread

Một trường hợp thực tế: client retry ngay khi request đầu còn chạy, hai HTTP request đến hai node khác nhau. Không thể giải quyết bằng `synchronized` trên một JVM.

Lịch chạy dự kiến ở PostgreSQL:

~~~text
T1: BEGIN; INSERT ledger R5 -> 1
T2: BEGIN; INSERT ledger R5 -> chờ unique conflict
T1: UPDATE inventory, INSERT order/outbox, SUCCEEDED, COMMIT
T2: INSERT ... DO NOTHING -> 0
T2: SELECT ledger R5 -> SUCCEEDED
T2: COMMIT; trả kết quả của T1
~~~

Nếu T1 rollback, T2 có thể claim và xử lý R5 thay thế. Nếu T2 hết lock timeout trước khi T1 kết thúc, cần retry cùng R5 với budget. **Không tự tạo request ID khác** chỉ để né chờ unique key.

Một bài test JUnit có thể dùng barrier:

~~~java
@Test
void concurrentSameKeyDoesNotDoubleApply() throws Exception {
    UUID id = UUID.randomUUID();
    var request = new CheckoutJdbcService.Request(
        id, 42L, "BOOK-01", 2
    );
    var service = new CheckoutJdbcService(dataSource);

    var workers = Executors.newFixedThreadPool(2);
    var start = new CountDownLatch(1);

    Callable<CheckoutJdbcService.Outcome> call = () -> {
        start.await();
        return service.place(request);
    };

    try {
        Future<CheckoutJdbcService.Outcome> first =
            workers.submit(call);
        Future<CheckoutJdbcService.Outcome> second =
            workers.submit(call);

        start.countDown();

        var a = first.get(15, TimeUnit.SECONDS);
        var b = second.get(15, TimeUnit.SECONDS);

        assertEquals("SUCCEEDED", a.status());
        assertEquals(a, b);
        assertDbState(dataSource, "BOOK-01", 8, id, 1, 1);
    } finally {
        workers.shutdownNow();
    }
}
~~~

Các import `java.util.UUID` và `java.util.concurrent.*` cần có; test chạy trên database sạch và có ít nhất hai connection độc lập. `CountDownLatch` khởi động gần đồng thời nhưng không bắt buộc interleaving đến từng statement; có thể dùng barrier test-only sau claim hoặc row lock để ép lịch chạy.

### 13.2. Hai khóa khác nhau vẫn cần điều kiện tồn kho

Giả sử tồn kho chỉ có 5, hai **ý định khác nhau** R6 và R7 đồng thời mua 4:

~~~text
R6: requestId=R6, qty=4
R7: requestId=R7, qty=4
~~~

Cả hai request đều hợp lệ và không trùng idempotency key. Một cơ chế trừ kho kiểu `SELECT available` rồi `SET available = old-qty` có thể bị lost update/oversell. Với:

~~~sql
UPDATE inventory
SET available = available - 4
WHERE sku = 'BOOK-01'
  AND available >= 4;
~~~

và transaction đúng, kết quả phù hợp cho lab là **một SUCCEEDED, một REJECTED**, tồn 1. Đây là **concurrency control cho hai ý định khác nhau**, không thể được bảo vệ chỉ bằng unique ledger.

### 13.3. Điều gì nếu request bị từ chối rồi hàng về?

R8 bị từ chối do kho chỉ còn 1 trong khi đặt 4. Sau đó có nhập hàng. Nếu R8 retry, thiết kế lab trả **REJECTED đã lưu**, chứ không tự đổi kết quả thành SUCCEEDED.

Nếu khách muốn thử mua lại sau khi hàng về, đó là **ý định mới, request ID mới**. Chính sách này nên được ghi rõ trong hợp đồng API, vì có hệ thống chọn không cache một số loại lỗi tạm thời; khi đó cần thiết kế riêng để vẫn bảo vệ không phát sinh side effect trùng.

## 14. Setup kiểm thử Java và PostgreSQL an toàn

### 14.1. Testcontainers

Có thể dùng Java 17+, JUnit Jupiter, Testcontainers PostgreSQL, PostgreSQL JDBC driver và các class service ở trên. Ví dụ tạo database lab:

~~~java
import org.postgresql.ds.PGSimpleDataSource;
import org.testcontainers.containers.PostgreSQLContainer;

PostgreSQLContainer<?> pg =
    new PostgreSQLContainer<>("postgres:16-alpine");
pg.start();

PGSimpleDataSource source = new PGSimpleDataSource();
source.setURL(pg.getJdbcUrl());
source.setUser(pg.getUsername());
source.setPassword(pg.getPassword());

// Tạo schema mục 5 trong container mới.
// Đóng container sau khi suite/test hoàn tất.
~~~

`postgres:16-alpine` là phiên bản minh họa cho lab, không mặc định khớp phiên bản production. Dependencies và runtime container phải được cấu hình tại dự án. Bài này không yêu cầu tự động chạy Gradle/Maven hay can thiệp hạ tầng ngoài phạm vi được giao.

### 14.2. Test không được bị bọc bởi transaction chưa commit

Một số Spring test tự tạo `@Transactional` trên test method rồi rollback cuối test. Khi service vô tình tham gia cùng transaction test đó, test có thể **không bao giờ quan sát một COMMIT thật**, từ đó che đi lỗi ambiguous commit.

Trong lab JDBC, mỗi `place()` lấy connection riêng và commit tự nó. Assertion dùng connection khác. Với Spring JPA test thực tế, cần chọn test transaction scope không che transaction boundary cần kiểm chứng.

### 14.3. Fault proxy và network failure thật

Seam sau-COMMIT chứng minh tính lũy đẳng nghiệp vụ. Một mạng thử nghiệm có thể dùng Toxiproxy hoặc fault proxy tương đương để:

- Cắt đường network trước khi gửi SQL.
- Tăng latency hoặc dừng response.
- Hủy kết nối trong lúc query đang chạy.
- Buộc pool loại connection lỗi.
- Đánh giá retry budget và connection cleanup.

Nhưng **không thể khẳng định mọi lần proxy cắt TCP đều xảy ra đúng sau khi DB commit**. Muốn kết quả deterministic, cần seam test có điểm inject đã xác định; network test bổ sung độ tin cậy của driver/pool chứ không thay thế bài test trạng thái DB.

## 15. Tiêu chí PASS cho lần thực hành

| Tiêu chí | Bằng chứng yêu cầu |
|---|---|
| Chống double-write | Cùng key gửi 2+ lần: stock trừ một lần, một order, một event |
| Ngăn payload conflict | Cùng key nhưng payload khác: conflict, không sửa DB |
| REJECTED ổn định | Retry cùng key trả cùng từ chối, không “tự thành công” |
| Rollback trước commit | Không còn ledger/order/outbox, stock giữ nguyên |
| Commit ACK bị mất | Caller thấy exception, replay trả outcome cũ đúng |
| Concurrency cùng key | Một hiệu ứng nghiệp vụ, hai caller cùng kết quả cuối |
| Concurrency khác key | Không oversell, `available >= 0` |
| Statement/lock timeout | Transaction lỗi được rollback/đóng đúng, không treo khóa |
| Connection cleanup | Số connection/pool pending trở lại baseline |
| Outbox | Event ghi cùng order; relay xử lý trùng bằng event ID |
| Độc lập test | Có reset/schema riêng, chạy lại không phụ thuộc thứ tự |
| Không lộ dữ liệu | Chỉ sử dụng dữ liệu giả, không ghi secret/PII vào log |

**Không đánh dấu bài thử ACK loss đạt nếu chỉ mock `repository.save()` ném exception.** Điều cần chứng minh là nhánh *database đã commit, caller không nhận confirmation*, và retry vẫn có đúng một hiệu ứng.

## 16. Hợp đồng HTTP cho request có thể thử lại

Cơ chế ở database chỉ hữu ích nếu API caller biết **tạo, giữ và gửi lại cùng request ID**. Hợp đồng nên được công bố rõ để client không vô tình biến retry thành một đơn mới.

### 16.1. API minh họa

~~~http
POST /api/checkouts
Idempotency-Key: c6a7b947-68d1-4824-98b9-50b13b296951
Content-Type: application/json

{
  "customerId": 42,
  "sku": "BOOK-01",
  "quantity": 2
}
~~~

Các mã kết quả **minh họa**:

| Tình huống | Phản hồi có thể dùng |
|---|---|
| Yêu cầu mới thành công | `201 Created` cùng order ID và outcome |
| Replay cùng key/payload đã thành công | `200 OK` hoặc kết quả tương đương đã lưu |
| Yêu cầu mới bị từ chối do thiếu hàng | `409 Conflict` hoặc mã domain phù hợp, kèm outcome ổn định |
| Replay request bị từ chối | Cùng outcome từ chối đã được lưu |
| Cùng key nhưng payload khác | `409 Conflict`, không tạo đơn |
| Không biết chắc kết quả do timeout | `503` hoặc `202` với hướng dẫn retry/poll **cùng key**, tùy thiết kế API |
| Request không hợp lệ về cấu trúc | `400/422` theo hợp đồng; không mặc định đây là bản ghi nghiệp vụ đã xử lý |

Không có một mapping HTTP duy nhất bắt buộc cho mọi sản phẩm; cần thống nhất giữa gateway, client và service. Điều quan trọng là một response không có/`504 Gateway Timeout` **không được khiến client tự tạo một key mới** để “thử lần nữa”.

### 16.2. Poll trạng thái với quyền truy cập

Có thể cung cấp:

~~~http
GET /api/checkouts/requests/c6a7b947-68d1-4824-98b9-50b13b296951
Authorization: Bearer ...
~~~

Endpoint phải xác thực và scope theo customer/tenant; một người biết UUID của người khác không được xem đơn của họ.

Một chú ý khó: nếu transaction đầu **chưa commit**, ledger row `STARTED` cũng chưa visible, nên một SELECT thường có thể trả “không tìm thấy” dù transaction khác đang làm. Vì vậy “chưa thấy row” **không chứng minh** việc chưa từng xử lý hoặc chắc chắn có thể tạo key mới. Client vẫn phải retry **cùng key** theo deadline/contract.

Nếu cần trạng thái `PROCESSING` hiển thị được qua polling, thường phải bổ sung hàng điều phối đã commit, lease và cơ chế recovery riêng, phức tạp hơn mẫu một transaction của lab.

### 16.3. Thời gian sống và phạm vi khóa

Khóa lũy đẳng cần chính sách retention:

- Giữ đủ lâu cho toàn bộ cửa sổ retry hợp lệ của client/gateway/mobile offline.
- Không xóa ledger rồi cho phép một request cũ quay lại và tạo hiệu ứng lần hai.
- Nếu cần purge, có thể duy trì tombstone/unique business reference hoặc cơ chế lưu kết quả dài hạn phù hợp.
- Đảm bảo cleanup không tách ledger khỏi những order/event còn phải đối soát.
- Thiết kế archive và truy vết theo nghĩa vụ dữ liệu/retention thực, không giữ PII vô hạn.

Một ứng dụng tuyên bố idempotent **chỉ trong 24 giờ** phải ghi rõ phạm vi đó; ngoài hạn, gửi lại request cũ có thể là yêu cầu mới hoặc bị từ chối theo hợp đồng. Không gọi đó là exactly-once vĩnh viễn.

## 17. Chuyển thiết kế sang Spring/JPA mà không làm mất ranh giới

Lab dùng JDBC để quan sát rõ SQL. Nếu chuyển sang Spring Boot/JPA, ranh giới vẫn phải được đặt ở **use case**, và tất cả đường ghi phải tham gia cùng transaction DB.

### 17.1. Application service giữ nguyên atomic boundary

Một kiến trúc hợp lý:

~~~text
HTTP handler (auth + stable Idempotency-Key)
    |
    v
Retry orchestrator (deadline/attempt budget)
    |
    v
Transactional checkout executor
    |
    +-> Idempotency repository (claim + fingerprint)
    +-> Inventory repository (conditional UPDATE)
    +-> Order repository
    +-> Outbox repository
    |
    v
COMMIT bởi Spring transaction manager
    |
    v
Trả outcome / xử lý ACK loss
~~~

Không đặt một `@Transactional` quanh cả vòng lặp retry rồi giữ lại transaction đã lỗi giữa các attempts. Mỗi attempt cần **transaction mới** theo cơ chế framework. Một cách là orchestration bên ngoài gọi bean transactional qua proxy; một cách khác là dùng `TransactionTemplate` cho từng attempt.

### 17.2. Proxy và exception rollback

Ví dụ sai trong mô hình Spring proxy:

~~~java
@Service
class RetryAndWriteService {
    public void retry() {
        this.executeOnce();
    }

    @Transactional
    public void executeOnce() {
        // Self-invocation có thể bỏ qua transaction advice.
    }
}
~~~

Ở cấu hình Spring proxy thông dụng, lời gọi `this.executeOnce()` không đi qua proxy nên annotation ở method con có thể không áp dụng như người viết tưởng. Tách bean hoặc dùng `TransactionTemplate` để chủ động xác định transaction scope.

Với Spring transaction mặc định phổ biến, `RuntimeException`/`Error` rollback, còn checked exception có thể không rollback nếu không cấu hình. Nếu tầng persistence ném checked exception hoặc bị catch-and-ignore, cần chắc chắn transaction không bị commit ngoài ý định. Các repository phải dùng đúng DataSource/transaction manager; tự mở một `DriverManager.getConnection` khác có thể commit độc lập.

### 17.3. Lỗi xảy ra sau method body

Một phương thức `@Transactional` có thể hoàn tất phần code và return outcome, **sau đó interceptor mới gọi commit**. Nếu commit ném exception, caller của proxy nhận lỗi dù method đã tính xong kết quả. Vì vậy tầng ở ngoài transaction vẫn phải có cách retry cùng idempotency key.

Không ghi “đã gửi HTTP 201 thành công” hay phát email thật trước khi database commit được xác nhận; outbox/event relay nên chạy sau commit và có cơ chế gửi lại an toàn.

### 17.4. JPA persistence context sau lỗi

Nếu transaction gặp deadlock/serialization failure, đừng reuse `EntityManager`/managed entities đã mang state cũ cho retry. Đọc lại dữ liệu trong context/transaction mới; tránh một phép `merge` ghi đè state cập nhật của concurrent request. Native SQL/bulk JPQL cũng có thể bypass `@Version`/cache synchronization; kiểm tra trên PostgreSQL thật.

### 17.5. Unique constraint là điểm đồng bộ thật

Một method repository như `existsByRequestId` chỉ là phép đọc, không chặn hai transaction cùng xử lý. Cần unique key tại database, thao tác claim atomic và tình huống concurrent insert được test. Nếu ORM không cho biểu đạt `INSERT ... ON CONFLICT DO NOTHING` thuận tiện, có thể dùng JDBC/`JdbcTemplate` cho phần claim mà vẫn giữ transaction Spring quản lý.

Đừng ngại kết hợp JPA và SQL trực tiếp khi một thao tác cần ngữ nghĩa của DBMS. Điều kiện là **cùng transaction, cùng policy lỗi và cùng hợp đồng dữ liệu**, không phải tất cả phải đi qua một annotation repository.

## 18. Outbox, xử lý lặp bên ngoài và giới hạn “exactly-once”

### 18.1. Order và outbox nằm trong DB transaction

Trong lab, thành công ghi một hàng `orders` và một hàng `outbox_events` cùng transaction. Nếu commit thành công, cả hai hiện diện. Nếu rollback, cả hai không có.

Tuy nhiên, một outbox relay có thể:

~~~text
Đọc event E1 -> publish tới broker -> broker nhận
Relay mất kết nối trước khi cập nhật published_at
Relay restart -> publish E1 lần nữa
~~~

Đây là **at-least-once delivery** có thể phát lặp. Consumer cần dùng `event_id`/operation ID và một cơ chế processed-message ledger hoặc version check phù hợp để không áp tác dụng hai lần.

### 18.2. Payment provider không tham gia transaction PostgreSQL

Không nên viết:

~~~java
@Transactional
public void checkout(...) {
    orderRepository.save(order);
    paymentGateway.charge(card, amount);
    outboxRepository.save(event);
}
~~~

rồi nghĩ rằng rollback DB sẽ hoàn lại charge đã thành công. Payment API, email, SMS, object store và broker là hệ thống bên ngoài. Khi timeout từ payment provider, kết quả có thể cũng **không chắc chắn**.

Cần workflow trạng thái, idempotency key khi gọi provider (nếu provider hỗ trợ), truy vấn đối soát, retry có giới hạn và cơ chế compensation khi cần. Outbox giúp lưu bền vững ý định cần publish; nó không tự tạo transaction phân tán exactly-once.

### 18.3. Không lấy “một event trong DB” làm bằng chứng “một email đã gửi”

Một unique outbox row ngăn lặp bản ghi trong DB, nhưng relay/consumer có thể phát tác dụng phụ nhiều lần. Nếu email có thể gửi hai lần khi worker crash, cơ chế dedup của consumer hoặc nghiệp vụ phải định nghĩa mức bảo đảm mong muốn. Với charge payment, kiểm tra trạng thái phía provider trước mọi lần gửi lại là quan trọng hơn chỉ đếm event DB.

## 19. Observability và xử lý sự cố timeout

Một hệ thống có retry lũy đẳng vẫn có thể quá tải nếu timeout làm phát sinh nhiều attempts, giữ transaction quá lâu hoặc chiếm connection pool.

### 19.1. Metrics nên có

| Metric | Vì sao theo dõi |
|---|---|
| `checkout_attempts_total` | Tổng attempts, phân biệt new/replay |
| `checkout_idempotency_replays_total` | Tần suất request được trả từ ledger |
| `checkout_key_conflicts_total` | Payload khác cùng key, nghi bug hoặc lạm dụng |
| `checkout_unknown_commit_total` | Caller mất xác nhận ở commit/network |
| `checkout_rejected_total` | Số từ chối nghiệp vụ, phân loại rõ |
| `checkout_retry_attempts_total` | Retry storm và budget |
| Transaction duration p95/p99 | Transaction quá lâu hoặc giữ lock |
| DB lock wait/deadlocks | Contention do cùng SKU/key |
| JDBC pool active/pending | Hết connection khi retry hoặc giữ transaction |
| Outbox pending/oldest age | Relay đang chậm hoặc stuck |
| Business invariant checks | Order/ledger/outbox nhất quán không |

Không gắn `request_id` vào label metrics vì cardinality có thể rất lớn. Request ID có thể đặt ở trace/log có retention và quyền truy cập phù hợp. Log cần giữ operation type, SQLSTATE và attempt count nhưng không in payment token, mật khẩu hay dữ liệu cá nhân.

### 19.2. Chuỗi sự kiện log hữu ích

~~~text
traceId=T1 requestId=R4 attempt=1 checkout.begin
traceId=T1 requestId=R4 attempt=1 claim=new
traceId=T1 requestId=R4 attempt=1 database.commit.unknown
traceId=T2 requestId=R4 attempt=2 checkout.begin
traceId=T2 requestId=R4 attempt=2 claim=replay
traceId=T2 requestId=R4 attempt=2 checkout.outcome=SUCCEEDED
~~~

Đây là log mẫu; **không suy diễn** rằng commit đầu chắc chắn thành công chỉ từ log `commit.unknown`. Nếu cần biết, đối chiếu ledger trên kết nối DB tin cậy và kiểm tra tác dụng nghiệp vụ.

### 19.3. Runbook khi tỷ lệ timeout tăng

1. Xác định lỗi xuất hiện ở pool, connect, SQL, lock wait, COMMIT hay gateway; không gộp tất cả thành `database timeout`.
2. Ghi nhận SQLSTATE, vendor code, statement ID và transaction duration bằng metadata an toàn.
3. Giới hạn retry, giảm concurrency và kiểm tra database load trước khi khuếch đại sự cố.
4. Với một request không rõ outcome, **không tạo request ID mới**; thử lại hoặc truy vấn ledger cùng ID theo hợp đồng.
5. Nếu ledger đã SUCCEEDED, đối chiếu order/outbox và trả kết quả cũ sau authorization.
6. Nếu ledger REJECTED, trả cùng từ chối đã lưu.
7. Nếu chưa thấy ledger, xem có transaction đang chờ/khóa không; thử lại với cùng ID, không kết luận chắc chắn chưa thực hiện chỉ từ một SELECT.
8. Nếu thấy `STARTED` đã commit hoặc có order mà không có ledger terminal, báo vi phạm invariant, dừng auto-retry cho trường hợp đó và điều tra.
9. Nếu outbox bị backlog, xử lý relay/reconciliation riêng, tránh tái tạo order chỉ để phát event.
10. Sau xử lý, thực hiện fault-injection regression và rà soát timeout/retry budgets toàn tuyến.

### 19.4. Thứ tự deadline cần thống nhất

Một thiết kế cần nhìn end-to-end:

~~~text
Client request deadline
  ├─ connection pool acquisition timeout
  ├─ connect/TLS timeout
  ├─ PostgreSQL statement_timeout
  ├─ lock_timeout
  ├─ JDBC socket/read timeout
  └─ HTTP gateway/server timeout
~~~

Nếu gateway timeout sớm hơn thời gian service thực sự hoàn tất, client có thể retry khi transaction đầu vẫn đang chạy. Điều đó không sai nếu idempotency đúng, nhưng tăng contention và chi phí. Chọn timeout có cơ sở theo SLA, transaction duration, dự phòng mạng và đặc tính retry; không copy một con số chung cho mọi môi trường.

## 20. Sai lầm thường gặp

| Sai lầm | Hậu quả | Sửa như thế nào |
|---|---|---|
| Gọi timeout là rollback | Retry có thể tạo đơn/trừ kho hai lần | Coi COMMIT result có thể mơ hồ, dùng ledger |
| Mỗi lần retry tạo UUID mới | Mỗi attempt thành một ý định mới | Giữ nguyên idempotency key |
| Chỉ `SELECT exists` trước INSERT | Race giữa hai transaction | Unique constraint + atomic claim |
| Claim ledger rồi commit riêng | Crash làm ledger và hiệu ứng lệch | Commit cùng transaction hoặc có lease/recovery protocol |
| Đặt `STARTED` đã commit nhưng không có lease | Request có thể treo vô hạn | State machine/lease/fencing hoặc tránh commit STARTED |
| Không so payload fingerprint | Reuse key cho payload khác trả kết quả sai | Canonical fingerprint và conflict |
| Chỉ unique order, trừ kho ở transaction khác | Tồn kho bị trừ hai lần trước khi unique violation | Một transaction cho toàn hiệu ứng |
| Retry trong transaction PostgreSQL đã aborted | SQL tiếp tục thất bại | Rollback rồi transaction mới |
| Retry mọi lỗi DB | Bão tải, lặp lỗi constraint cố định | Phân loại SQLSTATE và deadline |
| Retry cùng key nhưng trước đó đã ghi REJECTED rồi xóa | Đổi kết quả sau thời hạn | Retention/tombstone/hợp đồng rõ |
| Trả HTTP 201 trước COMMIT | Client tin đơn đã thành công khi DB rollback | Trả sau commit và dùng replay |
| Gọi payment/email trong DB transaction | Side effect ngoài DB không rollback | Outbox/workflow và idempotent consumer |
| Tin outbox là exactly-once toàn hệ | Relay có thể publish lặp | Event ID + consumer dedup/reconciliation |
| Dùng `pg_sleep` để “mô phỏng mất ACK COMMIT” | Chỉ hủy statement trước commit | Injection sau commit hoặc fault proxy có quan sát |
| Test mock repository là đủ | Không thấy trạng thái commit/locks thực | PostgreSQL integration tests |
| Test method tự rollback bao ngoài | Che lỗi commit boundary | Kiểm tra commit thực từ connection khác |
| Log nguyên payload/hash nhạy cảm | Rò dữ liệu khi debug | Log metadata an toàn, quyền hẹp |
| Tăng retry vô hạn để “tăng độ tin cậy” | DB/pool nghẽn hơn | Bounded retries, jitter, backpressure |

## 21. Bài tập thực hành và tự kiểm tra

### Bài 1. Phân biệt timeout

Một JDBC query ném exception vì socket read timeout. Điều gì có thể kết luận về COMMIT, và điều gì không?

**Gợi ý:** Chỉ biết caller không nhận phản hồi đúng hạn. Có thể DB đã hoặc chưa thực thi/commit; cần phân tích thời điểm và ledger.

### Bài 2. Khóa mới khi retry

Client gửi R1, bị HTTP 504, rồi gửi R2 với payload y hệt. Vì sao thiết kế có thể sai?

**Gợi ý:** Hệ không biết R2 là retry của R1; nếu R1 commit có thể double effect. Phải giữ R1.

### Bài 3. Payload conflict

R3 đặt 2 sản phẩm rồi client gửi lại R3 đặt 5. Có nên trả kết quả cũ mà không kiểm tra gì?

**Gợi ý:** Không. So fingerprint cùng scope tenant/principal; từ chối dùng key cho payload khác.

### Bài 4. Unique key và transaction

Tại sao `checkout_requests.request_id PRIMARY KEY` chỉ đủ khi claim, trừ stock, order và outbox cùng transaction?

**Gợi ý:** Trừ tồn hoặc gửi event ở transaction khác có thể đã commit trước khi phát hiện key trùng.

### Bài 5. Sau khi rollback trước COMMIT

Trong lab, lỗi xảy ra trước commit, rollback thành công. Ledger và order của request mới phải ở trạng thái nào?

**Gợi ý:** Không có hàng đã commit; retry cùng key có thể claim mới và thực hiện một lần.

### Bài 6. ACK loss sau COMMIT

Tiêm `connection.commit(); throw new SQLException(...)`. Caller thấy lỗi. Vì sao retry vẫn phải thành công theo hợp đồng?

**Gợi ý:** Lần đầu đã commit; replay same-key đọc terminal outcome, không trừ kho/insert order lại.

### Bài 7. Từ chối thiếu hàng

R4 bị REJECTED do hết hàng. Sau đó inventory được bổ sung. Retry R4 nên cho kết quả gì theo thiết kế lab?

**Gợi ý:** REJECTED như lần đầu. Muốn mua tiếp là ý định mới, key mới.

### Bài 8. Same-key concurrency

Hai transaction cùng insert `request_id=R5`. Tại sao một SELECT `exists` trước không đủ?

**Gợi ý:** Hai transaction cùng đọc không có row; unique conflict/atomic insert mới điều phối cạnh tranh.

### Bài 9. Different-key concurrency

Tồn kho 5, R6 và R7 mỗi request mua 4. Unique request ID có ngăn oversell không?

**Gợi ý:** Không. Cần conditional UPDATE/locking/isolation cho cùng SKU.

### Bài 10. `statement_timeout`

Một `SELECT pg_sleep(1)` bị hủy do `statement_timeout=150ms`. Có thể xem đó là bằng chứng server đã commit nhưng ACK mất không?

**Gợi ý:** Không. Đây là statement cancellation trước commit; transaction lỗi cần rollback.

### Bài 11. Commit error và rollback

Sau khi `Connection.commit()` đã thành công, catch block gọi `rollback()` không ném lỗi. Có thể kết luận dữ liệu đã rollback không?

**Gợi ý:** Không. Một COMMIT đã hoàn tất không được đảo bằng rollback của transaction sau đó.

### Bài 12. Spring transaction

Service gọi `this.executeOnce()` có `@Transactional` rồi loop retry trong cùng bean. Nguy cơ gì?

**Gợi ý:** Self-invocation có thể bỏ qua proxy; retry có thể dùng sai transaction scope. Tách bean hoặc dùng `TransactionTemplate`.

### Bài 13. Data retention

Tại sao xóa ledger sau 1 giờ mà client vẫn có thể retry sau 24 giờ gây rủi ro?

**Gợi ý:** Khóa đã mất; request cũ có thể được xử lý lần hai. Chính sách TTL phải gắn với retry window/tombstone.

### Bài 14. Outbox

Tại sao chỉ có một outbox event row không đủ để khẳng định consumer không gửi email hai lần?

**Gợi ý:** Relay có thể publish lặp khi ACK broker mất; consumer cần dedup/idempotency.

### Bài 15. Error classification

So sánh SQLSTATE `40P01`, `23505` và class `08` khi xử lý retry.

**Gợi ý:** Deadlock: rollback và retry transaction; unique: xử lý conflict theo nghiệp vụ; connection failure: có thể mơ hồ, retry cùng idempotency key.

### Bài 16. Bằng chứng kiểm thử

Một test chỉ `verify(orderRepository, times(1)).save(...)` rồi kết luận không double order sau timeout. Test này thiếu gì?

**Gợi ý:** Commit thật, DB unique, race và đọc trạng thái từ connection mới; cần Testcontainers/fault injection.

## 22. Ghi nhớ

- **Timeout khi ghi không đồng nghĩa rollback.** Khi phản hồi bị mất, caller có thể không biết transaction đã commit hay chưa.
- **Giữ một khóa lũy đẳng ổn định cho cùng ý định.** Không tạo request ID mới chỉ vì HTTP hoặc JDBC timeout.
- **Khóa phải gắn với payload.** So fingerprint và scope tenant/principal; cùng key với payload khác là conflict.
- **Unique constraint và transaction là nền tảng.** Claim ledger, cập nhật kho, tạo đơn, ghi outbox và terminal outcome phải commit/rollback cùng nhau.
- **Không commit `STARTED` vô tình.** Muốn có trạng thái processing tồn tại độc lập phải thiết kế thêm lease, fencing và recovery.
- **Retry phải dùng transaction mới khi lần trước lỗi.** Phân loại SQLSTATE, bounded attempts, backoff và deadline, không tái sử dụng session PostgreSQL đã aborted.
- **Kết quả từ chối cũng có thể cần lưu.** Replay cùng key phải có kết quả ổn định theo hợp đồng.
- **Mô phỏng đúng từng điểm lỗi.** `statement_timeout` kiểm tra cancellation; seam sau `commit()` kiểm tra ambiguous ACK; proxy mạng kiểm tra driver/network.
- **Kiểm tra concurrency và bất biến thật.** Same-key tránh duplicate; different-key vẫn cần conditional inventory update để tránh oversell.
- **Đừng nhầm DB với toàn hệ phân tán.** Outbox có thể được publish lặp; payment/email cần idempotency và reconciliation riêng.
- **Quan sát từ DB sau commit.** Một test đạt khi tồn kho, ledger, order, outbox và kết quả retry đúng, không phải vì mock không ném exception.

Điểm cốt lõi của bài thực hành là thay câu hỏi *“Khi timeout có nên retry không?”* bằng hai câu hỏi chính xác hơn: **“Lần trước có thể đã tạo tác dụng nghiệp vụ nào?”** và **“Nếu thử lại cùng ý định, database và các hệ liên quan có bảo đảm không tạo thêm tác dụng ngoài mong muốn không?”**. Khi giao dịch được thiết kế cùng khóa lũy đẳng, unique constraint, outcome ledger và phép kiểm thử lỗi ở đúng thời điểm, ứng dụng Java có thể xử lý tình huống phản hồi bị mất mà vẫn bảo toàn dữ liệu bền vững.






