# Giữ giao dịch mở trong lúc gọi dịch vụ ngoài

Một dịch vụ Java nhận yêu cầu thanh toán đơn hàng. Nó bắt đầu transaction, cập nhật trạng thái đơn sang **PROCESSING**, gọi cổng thanh toán qua HTTP và chỉ **COMMIT** sau khi cổng thanh toán trả lời. Ở môi trường thử nghiệm, lời gọi HTTP mất 100 ms nên mọi thứ có vẻ ổn. Khi dịch vụ thanh toán chậm 15 giây, connection pool cạn, các request khác chờ khóa, transaction timeout, và hệ thống bắt đầu retry hàng loạt. Nguy hiểm hơn: nếu cổng thanh toán đã trừ tiền nhưng PostgreSQL rollback, trạng thái giữa hai hệ thống có thể không còn khớp nhau.

Đây là lỗi thiết kế thường gặp: **giữ một database transaction mở trong khi đợi một thao tác bên ngoài database không thuộc cùng cơ chế commit**. Việc gọi HTTP, RPC, message broker, object storage, hệ thống email hoặc bên thứ ba trong một transaction không khiến thao tác bên ngoài tự động tham gia tính nguyên tử của database. Nó thường chỉ kéo dài thời gian giữ tài nguyên, làm tăng xác suất lỗi và khiến việc khôi phục khó hơn.

Bài thuộc chương **Lỗi thiết kế** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module hướng dẫn nguyên lý lưu trữ dữ liệu bền vững trong Java: từ mô hình dữ liệu, schema, truy vấn và chỉ mục đến giao dịch, cô lập, kiểm soát đồng thời, lỗi kết nối, tiến hóa dữ liệu, bảo mật, sao lưu và hiệu năng. Các ví dụ sử dụng **PostgreSQL, JDBC, Spring @Transactional, TransactionTemplate, HTTP client và transactional outbox**; chúng minh họa cách thiết kế ranh giới persistence và phải được điều chỉnh, kiểm thử theo hệ thống thật trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **transaction boundary** và vì sao thời gian chờ dịch vụ ngoài làm tăng thời gian giữ connection, row locks hoặc snapshot.
- Phân biệt **database atomicity** với tính nhất quán giữa database và dịch vụ ngoài; hiểu vì sao rollback local không hoàn tác một tác động HTTP đã thành công.
- Chẩn đoán **pool exhaustion, lock contention, idle in transaction, transaction timeout, retry storm và kết quả commit không chắc chắn**.
- Phân tích những sai lầm trong cách dùng **Spring @Transactional**, propagation, proxy, JPA flush và lời gọi bất đồng bộ.
- Thiết kế luồng **transaction ngắn → thao tác ngoài transaction → transaction ngắn**, có state machine, idempotency và reconciliation.
- Biết khi nào cần **transactional outbox, durable command, inbox, Saga hoặc cơ chế bù trừ**, cùng những giới hạn của chúng.
- Viết kiểm thử lỗi mạng, kết quả ngoài không chắc chắn, crash giữa các bước, cạnh tranh cập nhật và timeout bằng database thật.
- Xây dựng checklist phát hiện và sửa thiết kế giao dịch kéo dài trong ứng dụng Java.

## 2. Nhận diện anti-pattern trong mã nguồn

Ví dụ Spring đơn giản nhưng nguy hiểm:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final PaymentGateway gateway;

    public CheckoutService(
            OrderRepository orders, PaymentGateway gateway) {
        this.orders = orders;
        this.gateway = gateway;
    }

    @Transactional
    public void pay(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.markProcessing();

        // Lời gọi HTTP nằm TRONG phạm vi transaction của phương thức.
        PaymentResult result = gateway.charge(
                order.getCustomerId(), order.getAmount());

        order.markPaid(result.providerReference());
        // Spring/JPA flush và COMMIT thường xảy ra sau method body.
    }
}
~~~

Đây là **mã minh họa anti-pattern**, không phải implementation có thể dùng trong hệ thống thanh toán. Các type **OrderRepository, Order, PaymentGateway, PaymentResult** là abstraction giả định; những bước xác thực, idempotency, kiểm soát version và bảo mật chưa được mô tả.

Vấn đề:

1. **@Transactional** mở một transaction logic bao quanh quá trình thực thi phương thức, gồm cả thời gian đợi HTTP.
2. Sau khi đọc/cập nhật order, JPA hoặc JDBC có thể đã giữ connection, database locks hoặc phiên bản hàng liên quan.
3. Khi **gateway.charge** chậm, transaction vẫn chưa commit.
4. Nếu gateway đã trừ tiền rồi JVM hoặc COMMIT thất bại, **rollback DB không làm gateway hoàn tiền**.
5. Nếu client retry cùng thao tác mà không có khóa idempotency ổn định, cổng thanh toán có thể bị gọi thêm lần nữa.

Điểm tinh tế: **thời điểm physical connection được cấp có thể là lazy**, phụ thuộc Spring, Hibernate, DataSource và lúc câu SQL đầu tiên thực thi. Không được kết luận mọi method đánh dấu @Transactional đều ngay lập tức chiếm một connection từ đầu. Tuy nhiên, **sau khi đã thực hiện SQL** trong một transaction, việc kéo dài transaction bằng lời gọi ngoài là rủi ro rõ ràng và cần quan sát thực tế.

## 3. Dòng thời gian cho thấy vì sao thiết kế bị chậm

~~~text
Client      Spring service       PostgreSQL           Payment API
   |              |                  |                    |
   |-- pay() ---->|                  |                    |
   |              |-- BEGIN / SELECT>|                    |
   |              |<-- order --------|                    |
   |              |-- UPDATE ------->|                    |
   |              |                  | giữ một số tài nguyên
   |              |-- POST /charge ----------------------->|
   |              |                  |        mạng hoặc API chậm...
   |              |                  |                    |
   |              |<----------------------- charge result |
   |              |-- UPDATE ------->|                    |
   |              |-- COMMIT ------->|                    |
   |<-- 200 ------|                  |                    |
~~~

Trong khoảng đợi dịch vụ ngoài, transaction có thể tồn tại nhưng không gửi SQL mới đến database. Nếu đã giữ row lock, một transaction khác vẫn có thể phải đợi. Nếu dùng connection pool, connection đó có thể chưa được trả lại cho request khác.

Một request duy nhất bị chậm chưa chắc gây sự cố hệ thống. Vấn đề xuất hiện khi **rất nhiều request đồng thời đều giữ tài nguyên trong lúc chờ**.

## 4. Các loại tài nguyên có thể bị giữ quá lâu

| Tài nguyên | Hệ quả khi transaction kéo dài | Lưu ý |
| --- | --- | --- |
| **JDBC connection** | Ít connection rảnh cho request khác; pool pending tăng | Phụ thuộc lúc connection thực sự được mượn |
| **Row locks** | UPDATE/DELETE của transaction khác đợi, gây contention | Không phải mọi SELECT đều giữ row lock |
| **Transaction/snapshot** | Có thể giữ phiên bản dữ liệu cũ, ảnh hưởng VACUUM/MVCC | Tác động phụ thuộc isolation, truy vấn và DB |
| **ORM persistence context** | Entity managed và dirty-checking state tồn tại lâu hơn | Heap/GC có thể tăng khi nhiều entity được giữ |
| **Timeout budget** | Transaction, request và lời gọi ngoài cùng tiêu thụ deadline | Các timeout có ý nghĩa khác nhau |
| **Transaction log/WAL pressure** | Ghi và commit có thể bị ảnh hưởng khi đồng thời tải cao | Transaction kéo dài không luôn tạo nhiều WAL hơn, nhưng làm vòng đời phức tạp |
| **Connection pool capacity** | Request không liên quan cũng có thể lỗi xin connection | Cần đo active, idle, pending và usage |
| **Operational recovery** | Khó quyết định retry nếu local/remote đã lệch trạng thái | Cần state machine và đối soát |

**Một transaction vẫn có thể gây vấn đề dù không có nhiều locks.** Ví dụ đọc dữ liệu rồi chờ dịch vụ ngoài có thể giữ connection, snapshot hoặc tạo áp lực pool. Ngược lại, một lời gọi HTTP rất nhanh bên ngoài transaction không tự gây contention; nguyên nhân cần được đo, không suy đoán từ tên API.

## 5. Ước lượng áp lực lên connection pool

Theo phép xấp xỉ từ Little's Law:

~~~text
Số thao tác đang đồng thời xử lý ≈ throughput × thời gian mỗi thao tác

Ví dụ:
  40 yêu cầu/giây × 2 giây mỗi transaction = khoảng 80 transaction đồng thời
~~~

Nếu mỗi transaction giữ một DB connection gần trọn thời gian, nhu cầu connection có thể lớn hơn rất nhiều so với pool 20 connection. Yêu cầu sẽ xếp hàng chờ pool, làm latency tăng thêm và có thể kích hoạt timeout/retry. Đây là **ước lượng công suất trong trạng thái tương đối ổn định**, không phải công thức chính xác cho mọi tải burst.

So sánh hai thiết kế giả định:

| Thiết kế | Thời gian giữ connection mỗi request | Nhu cầu trung bình ở 40 request/giây |
| --- | ---: | ---: |
| Giữ transaction qua HTTP chậm | 2 giây | Khoảng 80 connection đồng thời |
| Chỉ giữ connection khi làm DB trong hai đoạn ngắn | Tổng 40 ms | Khoảng 1,6 connection bận trung bình |

Giá trị thứ hai **không có nghĩa pool size 2 là đủ**: tải burst, commit latency, DB capacity và số worker khác vẫn quan trọng. Điều nó minh họa là **đưa thời gian chờ network ra ngoài transaction có thể thay đổi rất lớn nhu cầu tài nguyên**.

Đừng chữa mọi trường hợp bằng cách tăng pool size. PostgreSQL còn có giới hạn session, CPU, I/O và lock contention; tăng số connection có thể chuyển điểm nghẽn từ JVM sang DB.

## 6. Atomicity của database không kéo dài tới HTTP

Một PostgreSQL transaction chỉ bảo đảm các thay đổi nằm **trong phạm vi transaction của database** được commit/rollback theo cơ chế của nó. Nó không tự biết:

- Cổng thanh toán đã chuyển tiền hay chưa.
- Dịch vụ gửi email đã phát thư hay chưa.
- Một đối tượng đã được upload lên object storage chưa.
- Message broker đã nhận và phát message chưa.
- Một HTTP API của đối tác đã áp dụng cập nhật hay chưa.

Ví dụ:

~~~text
BEGIN DB
  UPDATE orders SET status='PROCESSING'
  HTTP POST /charge  --> Provider thực hiện thanh toán THÀNH CÔNG
  UPDATE orders SET status='PAID'
  COMMIT DB          --> thất bại, DB ROLLBACK

Kết quả:
  Provider: đã thu tiền.
  PostgreSQL: đơn chưa được đánh dấu PAID.
~~~

Thay vị trí câu HTTP sang trước COMMIT **không biến nó thành thành viên của transaction**. Một database ROLLBACK không có thẩm quyền hoàn tác thao tác ngoài, trừ khi hệ thống đã xây dựng một giao thức phối hợp/compensation riêng.

**Chỉ dùng @Transactional không tạo distributed transaction.** Muốn điều phối nhiều resource thật sự cần cơ chế khác và giới hạn riêng; với phần lớn HTTP APIs, một giao thức two-phase commit (2PC) chuẩn không được cung cấp.

## 7. Bảng lỗi: hệ thống có thể dừng ở đâu?

| Thời điểm lỗi | Database cục bộ | Dịch vụ ngoài | Rủi ro |
| --- | --- | --- | --- |
| Trước khi gọi HTTP | Có thể rollback | Chưa gọi | Dễ khôi phục local |
| HTTP chưa tới nơi, timeout | Chưa hoàn tất | Có thể chưa nhận | Client khó kết luận chắc chắn từ timeout |
| Provider đã xử lý, phản hồi mất | Chưa biết kết quả local | **Có thể đã thành công** | Retry có thể tạo tác động trùng |
| Provider thành công, DB COMMIT lỗi | DB rollback hoặc chưa rõ | Đã có hiệu lực ngoài | Lệch trạng thái |
| DB COMMIT thành công, HTTP response trả client mất | DB đã commit | Có thể đã xử lý | Client retry dù nghiệp vụ đã hoàn tất |
| JVM crash giữa hai bước | Tùy mốc commit | Tùy mốc gọi API | Cần dữ liệu bền vững để resume/đối soát |
| Provider từ chối rõ ràng | Có thể ghi trạng thái FAILED | Không thực hiện | Được xử lý nếu lỗi phân loại chính xác |

Một timeout không chứng minh hệ thống ngoài đã **thất bại**. Khi HTTP client bị mất kết nối sau khi gửi request, remote server vẫn có thể xử lý và commit tác động. Tương tự, JDBC timeout đúng lúc COMMIT có thể để lại **kết quả local không chắc chắn**.

Trong thiết kế đúng, phải có trạng thái **UNKNOWN/PENDING_RECONCILIATION** hoặc cơ chế truy vấn trạng thái theo khóa đã biết, thay vì luôn gán **FAILED** và gửi request mới.

## 8. Đặt timeout không sửa được ranh giới giao dịch sai

Thêm timeout cho HTTP client là cần thiết:

~~~text
connect timeout: thời gian thiết lập kết nối
read/response timeout: thời gian chờ dữ liệu hoặc phản hồi
request deadline: giới hạn tổng thời gian của thao tác từ góc nhìn caller
DB statement timeout: giới hạn câu SQL trên database
transaction timeout: giới hạn thao tác transaction theo framework/DB
pool acquisition timeout: giới hạn thời gian chờ mượn connection
~~~

Nhưng timeout chỉ **chặn thời gian chờ**, không làm remote rollback, không rút ngắn transaction tới mức tối ưu nếu vẫn đặt HTTP trong đó, và không bảo đảm câu lệnh chưa hoàn tất.

Một thiết kế không an toàn thường có cấu hình:

~~~text
HTTP timeout = 30 s
Transaction timeout = 10 s
Connection pool timeout = 2 s
~~~

Khi HTTP chậm 20 giây, transaction có thể bị đánh dấu rollback-only hoặc bị DB hủy trước khi remote trả kết quả; remote vẫn có thể hoàn thành. **Chỉnh mọi timeout thành 30 giây không giải quyết sự lệch trạng thái**. Phải thay đổi transaction boundary và quy tắc đối soát.

Không dựa vào **Thread.interrupt**, cancel request hoặc socket close như một cơ chế hoàn tác remote operation đã được xử lý.

## 9. Giải pháp nền tảng: giao dịch ngắn, thao tác ngoài transaction

Đối với nhiều luồng nghiệp vụ, có thể tách:

~~~text
PHASE A - transaction ngắn
  kiểm tra yêu cầu
  ghi trạng thái PENDING + request_id ổn định
  COMMIT

PHASE B - ngoài transaction DB
  gọi HTTP tới provider với idempotency key
  nhận kết quả hoặc ghi nhận trạng thái chưa chắc chắn

PHASE C - transaction ngắn
  kiểm tra trạng thái/version hiện tại
  cập nhật SUCCEEDED/FAILED/UNKNOWN một cách có điều kiện
  ghi outbox event nếu cần
  COMMIT
~~~

Điểm lợi:

- Không giữ row lock hoặc DB connection chỉ để chờ remote.
- Mỗi bước local có transaction nhỏ, dễ quan sát và retry đúng phạm vi.
- Có một **dấu vết bền vững** để resume khi JVM crash.
- Có thể áp deadline/backpressure và giới hạn số lời gọi provider đang chạy.

Nhưng có một giới hạn quan trọng: giữa **PHASE A** và **PHASE C**, dữ liệu trong DB ở trạng thái **chưa hoàn tất**. Ứng dụng và UI phải **chấp nhận eventual consistency** hoặc trạng thái trung gian rõ ràng; không tự trả thành công cuối cùng khi chưa có kết quả.

Nếu process có thể chết sau PHASE A trước khi bắt đầu PHASE B, một mô hình chỉ gọi HTTP ngay trong luồng request **không bảo đảm tác vụ sẽ được thực hiện**. Cần cơ chế **durable work/outbox + worker** hoặc job recovery quét lại PENDING.

## 10. Đừng chuyển HTTP ra ngoài rồi quên vấn đề cạnh tranh

Một giải pháp sơ sài:

~~~java
// T1: đọc đơn hàng, commit.
OrderSnapshot snapshot = orderService.load(orderId);

// Gọi hệ thống ngoài, có thể mất nhiều giây.
PaymentResult result = gateway.charge(snapshot.amount());

// T2: ghi lại trạng thái.
orderService.markPaid(orderId, result.reference());
~~~

Nếu trong khoảng giữa có người **hủy đơn**, thay đổi số tiền hoặc một worker khác đã thanh toán, T2 có thể ghi **PAID** lên trạng thái không còn hợp lệ.

Vì vậy phải xác định:

1. **Dữ liệu nào được đóng băng** trước khi gọi ngoài: amount, currency, merchant, order version?
2. Ai được quyền thay đổi đơn trong trạng thái PROCESSING?
3. Có **request ID và payment attempt** duy nhất để bảo vệ khỏi hai caller?
4. Việc cập nhật cuối có **WHERE state = expected_state** hoặc **WHERE version = expected_version**?
5. Nếu state đã thay đổi, kết quả remote sẽ được **đối soát hoặc bù trừ** như thế nào?
6. Nếu response bị mất, ai được quyền gọi provider query API để xác định kết quả?

**Transaction ngắn là điều kiện cần về tài nguyên, không đủ cho tính đúng xuyên hệ thống.**

## 11. State machine làm hợp đồng giữa hai hệ thống

Ví dụ một payment attempt:

~~~text
                  +---------+
                  | PENDING |
                  +----+----+
                       |
                       v
                 +-----------+
                 | IN_FLIGHT |
                 +-----+-----+
                       |
            +----------+-----------+
            |          |           |
            v          v           v
       +---------+ +--------+ +----------+
       |SUCCEEDED| | FAILED | | UNKNOWN  |
       +---------+ +--------+ +-----+----+
                                     |
                              reconciliation
                                     |
                              +------+-------+
                              |              |
                              v              v
                         SUCCEEDED         FAILED
~~~

Trạng thái **UNKNOWN** có nghĩa **chưa có bằng chứng đủ để kết luận**, không phải chắc chắn provider chưa thực hiện. Nếu provider đã xác nhận **nhận yêu cầu nhưng chưa xử lý xong** (ví dụ HTTP 202), có thể dùng nhánh riêng **PENDING_PROVIDER** từ IN_FLIGHT, sau đó đợi callback/tra cứu để chuyển sang trạng thái cuối. Những tên trạng thái có thể khác trong hệ thống thật; quan trọng là **định nghĩa chuyển trạng thái**, tác động được phép và cách phục hồi.

Một số bất biến:

- Mỗi **(tenant_id, request_id)** chỉ đại diện một ý định thanh toán với payload được kiểm soát.
- Một lần charge chỉ dùng **provider idempotency key ổn định** đã gắn với payment attempt.
- **SUCCEEDED** chỉ được ghi khi có bằng chứng provider xác nhận thành công tương ứng.
- **FAILED** chỉ dùng cho kết quả thất bại xác định theo hợp đồng provider; timeout mơ hồ không đủ.
- Một payment attempt đã SUCCEEDED không được quay lại PENDING/FAILED chỉ vì một retry đến muộn.
- Việc phát sự kiện **PaymentSucceeded** và ghi trạng thái local diễn ra nguyên tử trong DB qua outbox nếu nghiệp vụ yêu cầu.

Thiết kế cũng phải bao gồm chính sách **timeout, expiry, cancellation và hoàn/bù giao dịch**. Việc có một trạng thái PROCESSING không được biến thành tình trạng treo vô hạn không ai theo dõi.

## 12. Ví dụ PostgreSQL: lưu ý định và trạng thái bền vững

Một lược đồ minh họa:

~~~sql
CREATE TABLE payment_attempts (
    attempt_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    request_id TEXT NOT NULL,
    provider_idempotency_key TEXT NOT NULL UNIQUE,
    payload_fingerprint TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'PENDING', 'IN_FLIGHT', 'PENDING_PROVIDER',
            'SUCCEEDED', 'FAILED', 'UNKNOWN'
        )
    ),
    provider_reference TEXT,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, request_id)
);

CREATE INDEX idx_payment_attempts_recovery
ON payment_attempts(state, updated_at);
~~~

Lược đồ chưa chứa đầy đủ foreign keys, ownership, partial indexes, outbox, dữ liệu nhạy cảm hoặc policy giữ dữ liệu. Giả định **amount_minor** dùng đơn vị nhỏ nhất của tiền tệ phù hợp (ví dụ cents); không dùng kiểu số thực dấu phẩy động để đại diện số tiền nếu nghiệp vụ cần tính chính xác.

Ở transaction khởi tạo:

~~~sql
INSERT INTO payment_attempts (
    attempt_id, tenant_id, order_id, request_id,
    provider_idempotency_key, payload_fingerprint,
    amount_minor, currency, state
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
ON CONFLICT (tenant_id, request_id) DO NOTHING;
~~~

Nếu INSERT bị bỏ qua do request ID trùng, service phải **đọc bản ghi đã có và so payload_fingerprint, tenant và kết quả**, không mặc định trả thành công cho một payload khác. Khóa **provider_idempotency_key** cần được tạo ổn định theo attempt và đáp ứng giới hạn API của provider.

## 13. Claim công việc với transaction ngắn

Nếu nhiều worker cùng xử lý PENDING, phải tránh tất cả gọi provider cùng lúc vì cùng đọc một hàng. Một cách là **claim** bằng cập nhật có điều kiện:

~~~sql
UPDATE payment_attempts
SET state = 'IN_FLIGHT',
    version = version + 1,
    updated_at = now()
WHERE attempt_id = ?
  AND state = 'PENDING'
RETURNING attempt_id, tenant_id, order_id,
          provider_idempotency_key, amount_minor, currency, version;
~~~

Nếu trả một hàng, worker đã claim thành công; nếu không trả hàng, attempt đã ở trạng thái khác hoặc không tồn tại. Câu UPDATE được **COMMIT trước khi HTTP call**.

Nhưng claim một lần **không tự giải quyết crash sau claim**. Hệ thống cần có cơ chế **lease hoặc recovery**:

- Ghi **owner/lease_until/claim_token** nếu có nhiều worker hoặc xử lý lâu.
- Job quét lại attempt IN_FLIGHT quá hạn và chuyển sang UNKNOWN để đối soát, hoặc claim lại theo quy tắc.
- Dùng **fencing token/version** khi ghi kết quả về DB để một worker cũ không ghi đè state mới.
- Provider phải hỗ trợ **idempotency hoặc query by request key** nếu muốn retry an toàn khi attempt cũ có thể đã được xử lý.

**Lease hết hạn không có nghĩa remote call đã dừng**. Worker cũ có thể vẫn đang ở trên mạng hoặc provider đang xử lý; vì vậy local claim giúp kiểm soát concurrency, còn remote idempotency mới hỗ trợ tránh tác động trùng ở phía ngoài.

## 14. Ghi kết quả có điều kiện để tránh stale completion

Một worker đã gọi provider thành công cần ghi kết quả theo **attempt_id, state và version/claim token** phù hợp:

~~~sql
UPDATE payment_attempts
SET state = 'SUCCEEDED',
    provider_reference = ?,
    version = version + 1,
    updated_at = now()
WHERE attempt_id = ?
  AND state IN ('IN_FLIGHT', 'PENDING_PROVIDER', 'UNKNOWN')
  AND version = ?;
~~~

Nếu **rows_updated = 0**, không được âm thầm coi là thành công. Cần đọc trạng thái mới nhất và kiểm tra:

- Attempt đã được worker khác xử lý thành công với **cùng provider reference**?
- Attempt đã bị hủy/đổi phiên bản nhưng provider thực sự đã thu tiền?
- Có cần phát thao tác refund/compensation hoặc xử lý thủ công?

Lưu ý: ví dụ trên dùng version để ngăn stale update, nhưng một implementation production có lease/fencing token cần xác định chính xác **token nào phải được chấp nhận khi state=UNKNOWN**. Không đơn giản chỉ cho mọi callback đến từ provider sửa mọi version.

Đặc biệt, một response HTTP **200** chưa chắc có nghĩa thanh toán đã hoàn tất nếu provider chỉ xác nhận **accepted/processing**. Phải đọc đúng **semantics của API bên ngoài** và cập nhật state tương ứng.

## 15. Java Spring: tách orchestration khỏi transaction cục bộ

Một cấu trúc dễ kiểm soát:

~~~text
CheckoutOrchestrator (không @Transactional)
  |
  +-- PaymentAttemptService.createOrLoad(...)   @Transactional
  |       -> lưu PENDING, COMMIT
  |
  +-- PaymentGateway.charge(...)                ngoài DB transaction
  |
  +-- PaymentAttemptService.complete(...)       @Transactional
          -> update state + outbox, COMMIT
~~~

Ví dụ Java dạng khung:

~~~java
import org.springframework.stereotype.Service;

@Service
public final class CheckoutOrchestrator {
    private final PaymentAttemptService attempts;
    private final PaymentGateway gateway;

    public CheckoutOrchestrator(
            PaymentAttemptService attempts, PaymentGateway gateway) {
        this.attempts = attempts;
        this.gateway = gateway;
    }

    // Không đánh dấu @Transactional ở orchestration.
    public CheckoutResult charge(CheckoutCommand command) {
        AttemptView attempt = attempts.createOrLoad(command);

        // Chỉ caller nắm quyền claim attempt mới được đi tiếp.
        if (!attempt.claimedByThisExecution()) {
            return CheckoutResult.pending(attempt.attemptId());
        }

        try {
            ProviderOutcome outcome = gateway.charge(
                    attempt.providerIdempotencyKey(),
                    attempt.amountMinor(),
                    attempt.currency());
            return attempts.complete(attempt, outcome);
        } catch (ProviderDefinitiveRejection ex) {
            return attempts.recordDefinitiveFailure(attempt, ex.code());
        } catch (ProviderAmbiguousFailure ex) {
            return attempts.markUnknown(attempt);
        }
    }
}
~~~

**Đây là pseudocode kiến trúc**, chưa phải lớp biên dịch độc lập. **CheckoutCommand, AttemptView, ProviderOutcome, CheckoutResult, PaymentAttemptService** và các exception do ứng dụng định nghĩa; class này chưa xử lý mọi lỗi phát sinh từ DB, timeout hoặc concurrent callbacks. Cần kiểm tra **ngoại lệ được phân loại theo tài liệu provider**, không bắt mọi IOException thành thất bại cuối.

Điểm thiết kế chính:

- Orchestrator **không mở transaction bao quanh lời gọi gateway**.
- Mỗi method cục bộ phải **commit trước khi trả về** hoặc trước khi orchestration tiếp tục (với Spring proxy/TransactionTemplate đúng cách).
- **Provider idempotency key** lấy từ attempt đã được lưu, không tạo mới mỗi lần retry.
- Nếu **attempts.complete** thất bại sau khi provider thành công, phải có **reconciliation** để hoàn tất local state sau này.
- Bắt ngoại lệ ở vùng remote call riêng; không vô tình biến lỗi DB ở bước complete thành FAILED của provider.

## 16. Spring proxy và self-invocation có thể phá việc tách transaction

Ví dụ không đúng:

~~~java
@Service
public class CheckoutService {
    @Transactional
    public void createPending(...) {
        // ghi PENDING
    }

    public void charge(...) {
        this.createPending(...);
        gateway.call(...);
    }
}
~~~

Với **Spring proxy-based transaction management**, lời gọi **this.createPending(...)** từ chính instance có thể bỏ qua transaction advice của proxy. Việc method được chú thích **@Transactional** không đủ để bảo đảm một transaction mới đã được tạo.

Ngược lại, đặt **@Transactional** ở public method charge() rồi gọi một method private không transaction bên trong cũng không làm HTTP call thoát khỏi transaction đã mở ở phía ngoài.

Thực hành:

1. Đặt những phương thức transaction ngắn trên **bean/service riêng**, gọi qua Spring proxy đúng cách.
2. Hoặc dùng **TransactionTemplate** để định nghĩa ranh giới transaction tường minh.
3. Kiểm tra transaction manager và DataSource tương ứng; nhiều database có thể cần transaction manager khác.
4. Tạo integration test chứng minh **PENDING đã commit trước khi HTTP call bắt đầu**.
5. Không tự giả định **@Transactional(propagation=NOT_SUPPORTED)** ở một inner method sẽ luôn hoạt động nếu self-invocation bỏ qua proxy.

## 17. Ví dụ TransactionTemplate với hai transaction rõ ràng

Nếu khó suy ranh giới proxy, một tầng điều phối có thể tách:

~~~java
import org.springframework.transaction.support.TransactionTemplate;

public final class OrderPaymentFlow {
    private final TransactionTemplate tx;
    private final PaymentStore store;
    private final PaymentGateway gateway;

    public OrderPaymentFlow(
            TransactionTemplate tx,
            PaymentStore store,
            PaymentGateway gateway) {
        this.tx = tx;
        this.store = store;
        this.gateway = gateway;
    }

    public PaymentOutcome execute(PaymentRequest request) {
        // Transaction A commit trước khi gọi provider.
        PaymentAttempt attempt = tx.execute(status ->
                store.createOrClaim(request));

        if (attempt == null || !attempt.claimed()) {
            return PaymentOutcome.pending();
        }

        ProviderResult remote;
        try {
            // Không có transaction DB từ TransactionTemplate ở dòng này
            // nếu caller không giữ outer transaction khác.
            remote = gateway.charge(
                    attempt.providerKey(), attempt.amountMinor());
        } catch (ProviderOutcomeUnknownException ex) {
            tx.executeWithoutResult(status ->
                    store.markUnknownIfOwned(attempt));
            return PaymentOutcome.pending();
        }

        // Transaction B: cập nhật kết quả có version/claim check.
        return tx.execute(status ->
                store.completeIfOwned(attempt, remote));
    }
}
~~~

**Pseudocode minh họa:** Các type và PaymentStore cần triển khai theo schema/state machine; không phải API Spring có sẵn. Trong code thật, transaction manager, propagation và rollback rules phải được xác nhận; **nếu caller đã mở outer transaction, TransactionTemplate mặc định REQUIRED có thể tham gia transaction đó**, khiến HTTP vẫn nằm trong transaction lớn của caller.

Để ranh giới A và B thực sự độc lập, cần **hợp đồng rõ không có outer transaction** hoặc propagation/kiến trúc được chọn có chủ đích. Dùng **REQUIRES_NEW** có thể tách một transaction mới nhưng có đánh đổi về connection, và không phải thuốc chữa khi outer transaction vẫn bị giữ mở trong lúc chờ.

## 18. Vì sao REQUIRES_NEW không tự sửa anti-pattern?

Giả sử:

~~~java
@Transactional
public void checkout(...) {
    orderService.savePendingInNewTransaction(...); // REQUIRES_NEW
    gateway.charge(...);                            // vẫn trong outer tx
}
~~~

**REQUIRES_NEW** tạo transaction độc lập cho lời gọi inner nếu interceptor thực sự được kích hoạt, nhưng **outer transaction vẫn tồn tại** quanh cả phương thức checkout. Trong một số cấu hình, outer transaction đã giữ connection/resources; khi inner transaction chạy, outer bị suspend và inner có thể cần thêm connection. Nếu nhiều request làm vậy, **pool contention có thể còn tệ hơn**.

Không nên chèn REQUIRES_NEW khắp nơi để ép commit sớm. Cần xem kiến trúc:

- Method orchestration có bắt buộc mở transaction hay không?
- Trước khi gọi ngoài, transaction nào đã commit?
- Tài nguyên transaction ngoài có còn giữ không?
- Các thay đổi local có bắt buộc commit nguyên tử với nhau không?
- Nếu inner commit rồi outer rollback, hệ thống còn nhất quán không?

**Propagation là công cụ triển khai ranh giới**, không thay thế quyết định nghiệp vụ về consistency.

## 19. Transactional outbox: ghi ý định và giao việc bền vững

Với những thao tác ngoài có thể thực hiện **bất đồng bộ**, transactional outbox giúp giải quyết khoảng trống **đã commit dữ liệu local nhưng process chết trước khi gửi message**.

~~~text
API Java
   |
   +-- BEGIN DB
   |     INSERT payment_attempts(..., PENDING)
   |     INSERT outbox_events(type='PAYMENT_REQUESTED', ...)
   |   COMMIT
   |
   +-- HTTP 202 Accepted / trạng thái PENDING

Outbox dispatcher (sau commit)
   |
   +-- claim một event trong transaction ngắn
   +-- COMMIT claim
   +-- gửi message / gọi provider ngoài transaction
   +-- ghi trạng thái dispatch/attempt có điều kiện

Consumer / worker
   |
   +-- gọi provider với idempotency key
   +-- lưu kết quả + outbox PaymentSucceeded trong transaction ngắn
~~~

Lợi ích:

- **Intent và outbox event được commit nguyên tử trong cùng một database transaction**.
- Crash ngay sau COMMIT không làm mất ý định vì dispatcher có thể đọc lại.
- API request không phải giữ connection trong thời gian provider chậm.
- Có thể điều tiết concurrency, retry, dead-letter và quan sát backlog.

**Outbox không bảo đảm exactly-once delivery chỉ bằng nó.** Một event có thể được gửi rồi dispatcher crash trước khi đánh dấu đã gửi; khi chạy lại, event được gửi lần nữa. Consumer/provider phải xử lý duplicate bằng **event ID, request key, inbox/unique constraint hoặc idempotency**.

### 19.1. Lược đồ outbox tối giản

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    state TEXT NOT NULL DEFAULT 'READY',
    claim_token UUID,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT outbox_state_check CHECK (
        state IN ('READY', 'CLAIMED', 'SENT')
    )
);

CREATE INDEX idx_outbox_ready
ON outbox_events(state, available_at);
~~~

Đây là schema ví dụ, chưa đủ để vận hành: cần trạng thái xử lý lỗi, số lần thử, lease expiration, retention, chính sách cleanup, version/sequence và bảo mật payload. **event_id** phải được giữ ổn định qua retry; payload không nên chứa thông tin nhạy cảm nhiều hơn mức cần thiết.

Ghi payment attempt và outbox event trong cùng transaction:

~~~sql
BEGIN;

-- INSERT payment_attempts(...) VALUES (...);
-- INSERT outbox_events(event_id, aggregate_id, event_type, payload)
-- VALUES (?, ?, 'PAYMENT_REQUESTED', CAST(? AS jsonb));

COMMIT;
~~~

Đoạn minh họa dùng comment cho các câu INSERT vì danh sách tham số phụ thuộc schema và implementation thực tế; không coi đó là script có thể chạy độc lập.

## 20. Tránh giữ transaction khi publisher gọi broker/provider

Một lỗi triển khai outbox:

~~~text
BEGIN DB
SELECT ... FROM outbox_events FOR UPDATE SKIP LOCKED
HTTP POST /provider            <-- vẫn giữ row lock và transaction
UPDATE outbox_events SET sent=true
COMMIT
~~~

Điều này chỉ chuyển anti-pattern sang worker. Dù sử dụng **SKIP LOCKED**, worker vẫn giữ transaction qua HTTP, và những worker khác không thể xử lý/đối chiếu hàng bị khóa cho tới khi nó kết thúc.

Một cách phù hợp hơn:

~~~text
Transaction ngắn A:
  SELECT/UPDATE event sang CLAIMED với owner, lease_until, token
  COMMIT

Ngoài transaction:
  Publish/call provider

Transaction ngắn B:
  Đánh dấu SENT hoặc UNKNOWN bằng claim_token/version
  COMMIT
~~~

Đây là mô hình **at-least-once**. Nếu crash sau publish và trước transaction B, worker có thể publish lại. Vì vậy, downstream idempotency là yêu cầu thiết kế, không phải tùy chọn để tối ưu.

Với PostgreSQL, **FOR UPDATE SKIP LOCKED** hữu ích để nhiều worker claim các hàng outbox trong một transaction ngắn, nhưng không giải quyết vấn đề claim hết hạn, worker cũ vẫn chạy, sự cố mạng hoặc bảo đảm thứ tự event. Cần version/fencing và logic xử lý duplicate.

## 21. Transactional event listener AFTER_COMMIT có thay outbox không?

Spring hỗ trợ xử lý event sau commit, chẳng hạn:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaymentRequested(PaymentRequested event) {
    gateway.send(event);
}
~~~

Giải pháp này giúp tránh gọi dịch vụ ngoài **trước khi transaction cục bộ commit**, nhưng có giới hạn:

- **Nếu JVM chết sau khi DB commit nhưng trước khi callback chạy**, event có thể không được phát.
- Nếu callback lỗi, không có một record bền vững tự động để retry.
- Nếu callback chạy đồng bộ, request vẫn có thể đợi network sau commit và chịu timeout ở tầng HTTP, dù connection/transaction DB đã kết thúc hoặc đang trong giai đoạn cleanup.
- Nếu callback cần ghi tiếp dữ liệu, phải hiểu rõ tài nguyên transaction đang ở thời điểm nào và chọn transaction mới phù hợp; không giả định mọi lệnh SQL trong callback sẽ tự commit đúng.

**AFTER_COMMIT không đồng nghĩa durable delivery.** Với yêu cầu phải giao việc chắc chắn sau commit, transactional outbox hoặc một cơ chế durable work tương đương phù hợp hơn.

## 22. Saga: nhiều bước ngoài database và hành động bù trừ

Một use case có thể gồm nhiều hành động:

~~~text
1. Reserve inventory
2. Authorize payment
3. Create shipment
4. Capture payment
5. Mark order completed
~~~

Không thể bao toàn bộ bằng một PostgreSQL transaction nếu mỗi bước gọi một dịch vụ khác. **Saga** chia use case thành **local transactions** và những bước bên ngoài được điều phối, có **compensating actions** khi không thể tiếp tục.

Ví dụ:

| Bước đã hoàn tất | Bước sau thất bại | Hành động bù có thể cần |
| --- | --- | --- |
| Đã giữ tồn kho | Payment bị từ chối | Giải phóng giữ chỗ |
| Đã authorize thanh toán | Không tạo được shipment | Void authorization nếu provider hỗ trợ |
| Đã capture thanh toán | Không thể giao hàng | Refund theo chính sách, có thể cần xử lý thủ công |
| Đã phát yêu cầu email | Đơn bị hủy sau đó | Gửi thông báo điều chỉnh, không thể thu hồi email đã đọc |

**Compensation không phải ROLLBACK nguyên tử**. Hoàn tiền có thể mất phí, thất bại hoặc hoàn sau nhiều giờ; email đã gửi có thể không thu hồi được. Vì thế Saga cần:

- State machine với trạng thái trung gian rõ ràng.
- Idempotency cho mỗi bước và mỗi compensation.
- Durable record về tiến độ/attempt/retry.
- Deadline, backoff, manual escalation và audit.
- Quy tắc tránh tiến hành một bước khi điều kiện nghiệp vụ đã thay đổi.

Thiết kế tốt thường cố **giảm tác động không thể đảo ngược** trước khi có đủ điều kiện, ví dụ authorize trước capture khi provider và nghiệp vụ cho phép.

## 23. Vì sao không mặc định dùng distributed transaction/2PC?

**Two-phase commit (2PC)** có thể phối hợp một số tài nguyên tham gia giao thức commit, nhưng không phải mọi dịch vụ ngoài hỗ trợ XA hoặc prepare/commit/rollback theo nghĩa transaction coordinator.

Ngay cả khi có:

- Coordinator, participant và logging cần vận hành phức tạp.
- Transaction phân tán có thể giữ khóa/tài nguyên lâu.
- Khi coordinator hoặc mạng lỗi, quá trình giải quyết trạng thái có thể chậm.
- Sự cố kéo dài có thể gây blocking và giảm availability.
- Một tác động như **gửi email** hoặc **chuyển tiền qua HTTP API không hỗ trợ XA** không thể được biến thành participant 2PC chỉ bằng annotation.

Không nên kết luận 2PC luôn sai; nó có thể phù hợp trong một số môi trường và tài nguyên được hỗ trợ. Nhưng với **HTTP API bên thứ ba**, giải pháp thực tế thường là **idempotency, durable workflow, outbox/inbox, Saga và reconciliation**.

## 24. PostgreSQL: dấu hiệu transaction bị giữ mở

Quan sát trạng thái các session:

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       clock_timestamp() - xact_start AS transaction_age,
       clock_timestamp() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Nếu thấy **state = 'idle in transaction'** và transaction_age lớn, một connection đã mở transaction nhưng hiện không thực thi SQL. Đây là một dấu hiệu cần điều tra; nó có thể xuất hiện khi ứng dụng đang đợi HTTP, tính toán lâu, treo hoặc quản lý transaction không đúng.

Tuy nhiên:

- **Không phải mọi session idle in transaction đều do HTTP**. Cần kết hợp trace/log và trạng thái Java.
- Với connection chưa bắt đầu transaction vật lý hoặc chưa mượn connection, không nhất thiết có session tương ứng trong DB để xem.
- Quyền xem hoạt động của session khác phụ thuộc role và chính sách DB.
- Trạng thái là **snapshot tại thời điểm truy vấn**, không phải lịch sử đầy đủ.
- Một transaction ở **active** và chờ **Lock** cũng có thể phản ánh contention do transaction khác giữ khóa quá lâu.

Quan sát blocker:

~~~sql
SELECT a.pid AS waiting_pid,
       pg_blocking_pids(a.pid) AS blocking_pids,
       a.wait_event_type,
       a.wait_event,
       clock_timestamp() - a.query_start AS waiting_age
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
~~~

Không tự động terminate một PID chỉ vì transaction_age cao; cần xác định tác động, quyền thao tác và quy trình xử lý sự cố.

## 25. Metrics và tracing để xác nhận nguyên nhân

Một dashboard hữu ích kết hợp:

| Thành phần | Chỉ số hoặc tín hiệu | Câu hỏi |
| --- | --- | --- |
| **HTTP/API** | p95/p99 latency, timeout, 5xx, in-flight requests | Tải chậm có tăng cùng thời điểm? |
| **Remote provider** | latency, success/decline/unknown, rate limit | Phần thời gian chờ ngoài lớn đến đâu? |
| **HikariCP** | active, idle, pending, acquisition latency, usage | Pool bị giữ bởi request nào và bao lâu? |
| **PostgreSQL** | transaction age, idle in transaction, blockers, waits | Có khóa/snapshot bị giữ lâu không? |
| **Transactions** | commit/rollback counts, duration, timeout | Transaction có kéo dài qua HTTP không? |
| **Outbox/workers** | backlog, age, claims, retries, unknown states | Có công việc PENDING bị bỏ quên không? |
| **Idempotency** | duplicates detected, fingerprint mismatch | Retry có gây tác động trùng hoặc lỗi nghiệp vụ? |
| **JVM** | active threads, queue depth, GC, memory | Thread chờ network có làm nghẽn tài nguyên không? |

Một trace lý tưởng:

~~~text
POST /checkout                          1800 ms
  |
  +-- transaction createPending          35 ms
  +-- HTTP payment-provider            1610 ms
  +-- transaction complete               55 ms
  +-- other                              ...
~~~

Thiết kế cũ có thể là:

~~~text
POST /checkout                          1800 ms
  |
  +-- transaction checkout             1770 ms
       +-- UPDATE order                 20 ms
       +-- HTTP payment-provider      1610 ms
       +-- COMMIT                       55 ms
~~~

Trên cùng mức latency HTTP, thiết kế mới có thể giữ connection/locks ngắn hơn rất nhiều. **Không phải cứ thấy HTTP span nằm trong transaction span là chắc đã giữ row lock**; cần xem SQL và transaction thực tế.

## 26. Timeout, retry và circuit breaker phải gắn với state machine

Khi provider chậm hoặc không khả dụng, ứng dụng có thể dùng:

- **Connect/read/overall deadline** phù hợp với SLA của provider.
- **Circuit breaker** để hạn chế tiếp tục gửi request mới khi provider đang lỗi.
- **Rate limiting/bulkhead** để một dependency ngoài không làm kiệt toàn bộ worker threads.
- **Retry có giới hạn + exponential backoff + jitter** cho lỗi được phép retry.
- **Idempotency key cố định** và chính sách query-status trước khi lặp thao tác có tác động.
- **UNKNOWN/PENDING** cùng job reconciliation khi không chắc remote đã thực hiện.

Một bảng ra quyết định:

| Kết quả provider | Có thể kết luận gì? | Hành động thường phù hợp |
| --- | --- | --- |
| Xác nhận thành công dứt khoát | Provider đã chấp nhận tác động theo hợp đồng | Ghi SUCCEEDED bằng transaction ngắn |
| Từ chối cuối cùng dứt khoát | Không thực hiện theo hợp đồng đã xác thực | Ghi FAILED, có thể thông báo khách |
| Timeout/mất kết nối sau gửi | **Không rõ** đã thực hiện hay chưa | Ghi UNKNOWN, query/reconcile theo key |
| HTTP 202/đang xử lý | Đã nhận, chưa chắc hoàn tất | Ghi PENDING_PROVIDER, theo dõi callback/query |
| Rate limit/503 | Có thể tạm thời | Backoff theo retry-after/chính sách provider |
| Local DB không cập nhật được sau remote success | Provider có thể đã thành công | Recovery job đối soát và ghi local state |

**Circuit breaker không hủy giao dịch từ xa đã bắt đầu**. Tương tự, timeout phía Java không dừng chắc một lệnh đang được provider xử lý. Mọi retry cần tôn trọng state machine và hợp đồng API thực.

## 27. Trường hợp ngoại lệ: cần gọi ngoài để quyết định dữ liệu ghi

Đôi khi ứng dụng phải lấy dữ liệu từ dịch vụ ngoài để quyết định cách ghi database, ví dụ:

- Tra cứu tỷ giá/thuế suất hợp lệ.
- Kiểm tra chính sách chống gian lận.
- Xác nhận địa chỉ giao hàng.
- Lấy thông tin kho ở hệ thống khác.

Không vì vậy mà mặc định phải giữ transaction DB trong lúc gọi ngoài. Một lộ trình thường hợp lý:

~~~text
1. Đọc đầu vào cần thiết hoặc chụp snapshot/version ngắn.
2. Gọi hệ thống ngoài ngoài transaction.
3. Bắt đầu transaction DB mới.
4. Kiểm tra lại dữ liệu có thay đổi không (version/state/precondition).
5. Ghi kết quả có điều kiện rồi COMMIT.
~~~

Nếu kết quả dịch vụ ngoài có thời hạn, phải **lưu version/time/fingerprint** và xác nhận khi sử dụng. Đây là vấn đề **time-of-check vs time-of-use**: dữ liệu có thể thay đổi giữa lúc được kiểm tra bên ngoài và lúc ghi local. Khi sự nhất quán mạnh là bắt buộc, cần điều chỉnh mô hình nghiệp vụ (reservation/lease/điều phối) chứ không dựa vào việc giữ một DB transaction lâu để khóa cả thế giới.

## 28. Một số trường hợp thường bị bỏ sót trong Java

### 28.1. Gửi email bên trong @Transactional

~~~java
@Transactional
public void register(...) {
    users.save(...);
    emailSender.sendWelcome(...); // sai ranh giới
}
~~~

Nếu email đã gửi nhưng transaction user bị rollback, người dùng nhận thư cho tài khoản chưa tồn tại. Giải pháp: ghi **user + outbox email event** trong cùng transaction, sau commit worker gửi email, xử lý duplicate theo event ID và provider capability.

### 28.2. Upload file/object storage

~~~text
BEGIN DB -> INSERT metadata -> upload file lên object storage -> COMMIT
~~~

Nếu upload thành công nhưng COMMIT lỗi, có thể còn **orphan object**. Nếu DB COMMIT trước upload, metadata có thể trỏ tới file chưa tồn tại. Cần state **UPLOADING/READY**, temporary object key, finalize và cleanup/reconciliation; object storage không tự rollback theo PostgreSQL.

### 28.3. Gọi broker trực tiếp

~~~text
BEGIN -> INSERT order -> publish Kafka/RabbitMQ -> COMMIT
~~~

Message có thể đến consumer trong khi order vẫn chưa commit, hoặc DB rollback sau khi publish. Dùng outbox khi cần bảo đảm message chỉ biểu diễn dữ liệu đã commit và có cơ chế retry bền vững.

### 28.4. Open Session in View và lazy loading

Một số cấu hình JPA **Open Session/EntityManager in View** giữ persistence context trong suốt HTTP request. Điều này **không đồng nghĩa có một transaction DB duy nhất xuyên toàn request**, nhưng lazy loading ngoài service boundary có thể kéo thêm truy vấn, giữ/đòi connection hoặc che ranh giới dữ liệu. Cần phân biệt session scope với transaction scope; tắt/bật cơ chế này không tự sửa lỗi gọi provider trong @Transactional.

### 28.5. Streaming và export rất lớn

Một truy vấn streaming có thể cần transaction/cursor mở để đọc theo lô. Nếu trong vòng lặp còn gọi HTTP tới từng record, connection/transaction có thể tồn tại hàng giờ. Cân nhắc **keyset pagination, checkpoint, batch enrichment ngoài transaction** và đảm bảo tính nhất quán của dữ liệu qua nhiều trang.

### 28.6. Reactive hoặc async code

Với reactive transaction, ranh giới có thể gắn với **reactive context** thay vì thread-local giống JDBC truyền thống. Không suy rằng @Transactional trong code reactive chạy giống hệt imperative JDBC hoặc rằng tạo **CompletableFuture** trong method @Transactional sẽ tự mang transaction sang worker. Cần kiểm tra framework, transaction manager và pipeline thực tế.

## 29. Phân biệt read-only transaction và transaction ghi

Không phải cứ không ghi là giữ transaction qua HTTP trở nên vô hại:

~~~text
BEGIN READ ONLY
SELECT một tập dữ liệu
HTTP call chậm
COMMIT
~~~

Ngay cả khi không giữ row lock ghi, transaction read-only còn có thể giữ **connection, snapshot hoặc transaction state**; tùy isolation và query, có thể góp phần vào long-running MVCC snapshots. Đặc biệt nếu mở cursor hoặc dùng REPEATABLE READ, cần xem chi phí.

Tuy nhiên cũng không nên khẳng định mọi read-only transaction giữ snapshot đến khi kết thúc ở mọi DB/driver. Hãy kiểm tra **transaction isolation, thời điểm snapshot được thiết lập, connection acquisition và PostgreSQL wait/transaction state**.

Giải pháp thường là đọc vừa đủ dữ liệu rồi kết thúc transaction, gọi dịch vụ ngoài, sau đó **kiểm tra lại preconditions** nếu kết quả sau gọi ngoài cần được ghi dựa trên dữ liệu trước đó.

## 30. Kiểm thử concurrency và failure injection

Đừng chỉ viết happy-path test nơi provider trả lời trong 10 ms. Một ma trận:

| Kịch bản | Cách mô phỏng trong test | Bất biến cần xác nhận |
| --- | --- | --- |
| Provider phản hồi nhanh | Fake server trả success | Local SUCCEEDED, một payment attempt |
| Provider chậm 10 giây | Fake server chặn response bằng latch | Không giữ transaction/row lock trong lúc chờ |
| Timeout sau provider đã nhận request | Fake server ghi nhận request rồi ngắt kết nối | Attempt UNKNOWN; retry không tạo charge trùng |
| JVM crash sau PENDING commit | Dừng worker trước khi publish/gọi ngoài | Durable work có thể resume |
| JVM crash sau provider success trước local update | Bỏ bước complete | Reconciliation cập nhật đúng từ provider |
| Hai worker claim cùng attempt | Start cùng lúc bằng barrier | Chỉ một claim hợp lệ mỗi thời điểm |
| Lease hết hạn, worker cũ quay lại | Worker A chậm, B reclaim | Stale completion bị version/fencing từ chối |
| Provider trả 202 processing | Trả async outcome | Không đánh dấu SUCCEEDED trước confirm |
| DB COMMIT response mất | Fault injection kết nối | Không lặp thao tác với key mới |
| Outbox publish rồi crash | Không đánh dấu delivered | Có thể phát lại; consumer idempotent |
| Provider từ chối dứt khoát | Fake trả rejection hợp lệ | FAILED và không tự retry vô hạn |
| Connection pool nhỏ dưới tải | Giới hạn pool trong integration test | Thiết kế mới giảm pending và giữ giao dịch ngắn |

Với bài test cạnh tranh, dùng **hai connection/transaction độc lập**, **CountDownLatch/CyclicBarrier có timeout** và PostgreSQL thật hoặc Testcontainers tương thích. Tránh **Thread.sleep()** để đoán lịch thực thi; nó dễ gây flaky tests.

Không chạy fault injection làm phá dữ liệu trên production. Các test phải dùng dữ liệu giả, cổng thanh toán sandbox/fake và môi trường đã cô lập.

## 31. Ví dụ kiểm thử chứng minh không giữ transaction qua HTTP

Một test có thể thiết kế:

~~~text
Worker A:
  gọi checkout()
  phase A: ghi PENDING và COMMIT
  HTTP fake provider: dừng ở latch, chưa trả phản hồi

Thread kiểm thử B:
  bắt đầu transaction riêng
  SELECT/UPDATE hàng kiểm thử theo quy tắc phù hợp
  xác minh có thể lấy connection và tiến hành thao tác
  quan sát DB không còn transaction của A giữ khóa từ phase A

Coordinator:
  thả latch provider
  chờ worker A hoàn tất
  xác nhận state và idempotency
~~~

Trước khi kết luận, cần tách hai điều:

1. **Không còn DB transaction của request A đang mở khi provider bị chặn**.
2. **Một tác vụ B độc lập vẫn tiến hành được**.

Điều (2) riêng lẻ chưa đủ chứng minh (1): với READ COMMITTED, một SELECT khác có thể đọc được dù transaction A đang giữ lock ghi; hoặc B có thể dùng connection khác. Nên kết hợp **instrumentation transaction boundaries, pg_stat_activity** và bài test cố gắng cập nhật đúng một hàng dễ bị chặn nếu A giữ row lock.

Đặt deadline cho mọi latch/Future, cleanup worker trong finally và kiểm tra không còn connection bị mượn sau test.

## 32. Những sai lầm thường gặp

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Đặt toàn bộ flow gọi HTTP trong @Transactional | Giữ connection/locks lâu, không có atomicity xuyên HTTP | Transaction ngắn bao quanh SQL, HTTP ở ngoài |
| Nghĩ rollback DB hoàn tác payment/email | Hai hệ thống có thể lệch trạng thái | Idempotency, state machine, reconciliation/Saga |
| Chỉ tăng connection pool khi chậm | Có thể đẩy tải/locks sang PostgreSQL | Đo usage/acquire, rút ngắn transaction |
| Chỉ thêm timeout HTTP | Kết quả remote vẫn có thể không chắc chắn | UNKNOWN state + query/reconcile |
| Retry payment với key mới sau timeout | Charge trùng | Giữ provider idempotency key ổn định |
| Gọi gateway sau transaction A nhưng không lưu việc cần làm | Crash trước HTTP làm mất công việc | Durable command/outbox + recovery |
| Dùng AFTER_COMMIT listener như hàng đợi bền vững | Crash sau commit có thể mất event | Transactional outbox |
| Worker giữ FOR UPDATE trong lúc publish | Lock kéo dài, throughput thấp | Claim/commit, publish, finalize/commit |
| Chỉ dùng lease, bỏ idempotency provider | Worker cũ vẫn có thể gọi khi lease hết | Fencing local + remote idempotency |
| Dùng REQUIRES_NEW ở inner method nhưng outer tx vẫn mở | Outer giữ tài nguyên; có thể cần thêm connection | Bỏ outer transaction hoặc thiết kế lại orchestration |
| @Transactional self-invocation | Advice có thể bị bỏ qua | Bean riêng/proxy hoặc TransactionTemplate |
| Coi HTTP 202 là đã thanh toán | Trạng thái nghiệp vụ sai | Chờ confirm hoặc dùng trạng thái pending |
| Ghi FAILED cho mọi timeout | Provider có thể đã thành công | Phân biệt definitive failure và unknown |
| Ghi kết quả provider mà không kiểm tra version | Stale worker ghi đè cancellation/attempt mới | CAS/version/claim token |
| Gửi message trong transaction và tin rằng sẽ rollback cùng DB | Consumer có thể thấy event cho dữ liệu chưa commit | Outbox |
| Test bằng fake provider luôn trả ngay | Không lộ pool saturation/failure windows | Test chậm, timeout, crash và concurrency |
| Không có job xử lý UNKNOWN | Giao dịch treo vô hạn | Reconciliation với deadline/escalation |

## 33. Bài tập thực hành

### Bài 1. Nhận diện ranh giới sai

Method **@Transactional** thực hiện UPDATE inventory, gọi HTTP shipping trong 8 giây rồi COMMIT. Những tài nguyên nào có thể bị giữ? Vì sao rollback không hủy yêu cầu shipping đã nhận?

**Gợi ý:** Connection, row locks, transaction/snapshot có thể tồn tại; HTTP shipping không phải participant trong PostgreSQL transaction.

### Bài 2. Connection pool

Hệ thống nhận 40 request/giây, mỗi request giữ connection qua HTTP khoảng 2 giây. Ước lượng số connection bận trung bình trong trạng thái ổn định. Một pool 20 connection có nguy cơ gì?

**Gợi ý:** Khoảng **80** connection đồng thời theo ước lượng. Pool 20 dễ pending/timeout nếu không có bottleneck khác làm giảm throughput trước đó.

### Bài 3. Remote thành công, DB rollback

Payment provider đã charge nhưng COMMIT PostgreSQL lỗi. Có được retry charge với idempotency key mới không?

**Gợi ý:** Không. Phải đối soát payment theo key ổn định, hoàn tất state local hoặc thực hiện compensation có kiểm soát.

### Bài 4. Timeout

HTTP client timeout sau 5 giây và ghi FAILED. Vì sao kết luận này có thể sai?

**Gợi ý:** Provider có thể đã nhận và thực hiện. Ghi UNKNOWN/PENDING, tra cứu trạng thái hoặc đợi callback theo hợp đồng.

### Bài 5. Tách transaction

Vẽ ba giai đoạn A/B/C để xử lý một payment attempt mà không giữ DB connection trong thời gian provider chậm.

**Gợi ý:** A lưu PENDING/claim rồi commit; B gọi provider ngoài transaction; C ghi kết quả có version check và commit.

### Bài 6. Lost work

Ứng dụng ghi PENDING và commit, sau đó JVM crash trước khi gửi HTTP. Thiết kế chỉ dựa trên request thread có tiếp tục được không?

**Gợi ý:** Không chắc. Dùng outbox/durable job hoặc recovery scanner để tiếp tục ý định chưa được xử lý.

### Bài 7. Outbox và duplicate

Dispatcher publish event thành công nhưng crash trước khi đánh dấu SENT. Có thể publish trùng không?

**Gợi ý:** Có. Outbox thường bảo đảm at-least-once; consumer/provider cần idempotency theo event/request ID.

### Bài 8. REQUIRES_NEW

Method checkout() có @Transactional gọi savePending() REQUIRES_NEW, rồi đợi HTTP 20 giây. Ranh giới này đã sửa vấn đề chưa?

**Gợi ý:** Chưa chắc; outer transaction vẫn mở, có thể giữ tài nguyên và inner còn cần connection khác.

### Bài 9. Stale callback

Worker A gọi provider chậm, lease hết hạn và worker B nhận việc. A trở lại cập nhật SUCCEEDED mà không kiểm tra claim token. Điều gì có thể xảy ra?

**Gợi ý:** Stale write có thể ghi đè state mới. Cần version/fencing token, idempotency từ provider và quy tắc đối soát.

### Bài 10. Email trong transaction

Method đăng ký user INSERT vào DB rồi gửi email trước COMMIT. Email đi thành công nhưng DB rollback. Nên đổi kiến trúc thế nào?

**Gợi ý:** Commit user và email outbox event nguyên tử trong DB, sau đó worker gửi có retry/idempotency phù hợp.

### Bài 11. Long-running read

Một job export mở cursor PostgreSQL rồi gọi API bên ngoài cho từng hàng. Vì sao heap có thể ổn nhưng vận hành vẫn lỗi?

**Gợi ý:** Connection/transaction/snapshot mở lâu, pool thiếu connection và khó resume. Dùng keyset/chunk/enrichment ngoài transaction với checkpoint.

### Bài 12. Tiêu chí test

Test xác minh một SELECT từ thread B chạy được khi thread A đang đợi provider. Có đủ chứng minh A không giữ row lock không?

**Gợi ý:** Chưa. READ COMMITTED vẫn có thể đọc được phiên bản committed cũ. Cần kiểm tra transaction boundaries, DB wait/locks hoặc một UPDATE có tranh chấp thực sự.

### Bài 13. HTTP 202

Provider trả **202 Accepted** cho lệnh charge, chưa báo transaction thành công. Ứng dụng có nên đánh dấu đơn PAID ngay không?

**Gợi ý:** Không. Dùng PENDING_PROVIDER và xác nhận bằng callback/query API trước khi chuyển SUCCEEDED.

### Bài 14. Tính nhất quán xuyên hai hệ

Đơn hàng đã bị hủy trong lúc provider đang xử lý payment. Worker nhận kết quả thành công rồi cập nhật PAID không có WHERE state/version. Nêu rủi ro và cách ngăn.

**Gợi ý:** Ghi đè quyết định hủy. Dùng state machine, cập nhật có điều kiện và compensation/refund khi kết quả remote không còn phù hợp với trạng thái local.

## 34. Checklist trước khi triển khai use case có lời gọi ngoài

1. **Inventory:** liệt kê mọi HTTP/RPC/email/broker/storage call trong hoặc gần một method @Transactional.
2. **Transaction boundary:** lời gọi ngoài có xảy ra khi DB transaction hoặc row lock vẫn mở không?
3. **Connection:** đã đo pool active/usage/pending và transaction age dưới tải thật chưa?
4. **Atomicity:** thao tác nào chỉ được commit ở DB, thao tác nào thuộc provider? Có chỗ nào đang giả định rollback xuyên hệ không?
5. **State machine:** có PENDING/IN_FLIGHT/SUCCEEDED/FAILED/UNKNOWN với quy tắc chuyển trạng thái rõ không?
6. **Idempotency:** request ID và provider key ổn định qua retry; có unique constraint và kiểm tra fingerprint không?
7. **Concurrent writers:** có claim/version/fencing token và xử lý stale completion không?
8. **Durability:** có outbox/durable command hoặc recovery job cho crash sau local commit không?
9. **Delivery:** biết event/provider call có thể được lặp; consumer có idempotent không?
10. **Timeout:** phân biệt kết quả definitive failure và ambiguous outcome, có deadline/reconciliation không?
11. **Retry:** giới hạn attempts, backoff, jitter, không retry thao tác không lũy đẳng bằng key mới?
12. **Spring:** có tự gọi @Transactional qua this, REQUIRES_NEW lồng nhau hoặc outer transaction không mong muốn không?
13. **JPA:** có biết flush khác commit, persistence context giữ bao lâu và commit exception xuất hiện tại tầng nào không?
14. **Saga:** có bước nào không thể đảo ngược, compensation và escalation đã định nghĩa không?
15. **PostgreSQL:** có quan sát idle in transaction, blockers, transaction age, WAL/replication lag liên quan không?
16. **Observability:** traces tách được DB phases với network call, metrics đo pool và trạng thái UNKNOWN không?
17. **Failure tests:** đã thử provider chậm, timeout sau xử lý, DB COMMIT lỗi, crash trước/sau remote và claim lease expiry chưa?
18. **Security:** credential provider/DB được bảo vệ; log không chứa token, payment payload hoặc PII?
19. **Business contract:** API trả 200/202/409 thế nào khi thao tác còn pending hoặc chưa thể kết luận?
20. **Operations:** có runbook đối soát và xử lý giao dịch treo lâu, người chịu trách nhiệm và cảnh báo backlog không?

## 35. Tổng kết

**Giữ giao dịch mở trong lúc gọi dịch vụ ngoài** là một lỗi thiết kế dễ bị che khuất bởi annotation **@Transactional**: lời gọi bên ngoài không trở thành một phần của database atomicity, nhưng có thể kéo dài thời gian giữ **connection, row locks, snapshot và transaction state**. Khi provider chậm hoặc mất mạng, hệ thống dễ gặp pool exhaustion, lock contention, timeout và retry storm; khi remote đã thành công nhưng DB rollback, hai hệ thống có thể lệch nhau.

Giải pháp là đặt **transaction boundaries ngắn quanh thao tác database**, gọi dịch vụ ngoài **sau commit và ngoài transaction local**, rồi hoàn tất trạng thái trong một transaction ngắn khác. Để bảo đảm việc vẫn tiếp tục sau crash và xử lý retry đúng, cần bổ sung **state machine, idempotency key, optimistic checks/fencing, durable outbox/workflow, reconciliation và compensation/Saga khi phù hợp**. Trong Java, hãy kiểm tra thật ranh giới **Spring proxy, TransactionTemplate, propagation, JPA flush/commit**, đồng thời đo **connection pool, PostgreSQL waits, trace và failure scenarios**. Thiết kế tốt không chỉ nhanh hơn mà quan trọng nhất là **phục hồi được và đúng dữ liệu khi các hệ thống không cùng thành công hoặc thất bại**.
