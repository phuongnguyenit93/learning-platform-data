# Thiết kế chống gửi yêu cầu lặp và thông báo sau giao dịch

*Chương: Thực hành hệ thống đơn hàng*

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, có mục tiêu **Học tổ chức phần mềm theo kiến trúc phân tầng**. Trong một hệ thống đơn hàng, client có thể gửi lại yêu cầu vì timeout, mất kết nối, người dùng nhấn nút nhiều lần hoặc proxy tự retry. Nếu mỗi lần nhận request đều tạo đơn hàng mới và gửi thông báo mới, một ý định mua hàng có thể tạo ra nhiều tác dụng phụ.

Thiết kế cần giải quyết hai vấn đề liên quan nhưng khác nhau:

- **Chống xử lý lặp:** cùng một ý định nghiệp vụ được gửi lại nhiều lần nhưng chỉ tạo ra một kết quả nghiệp vụ.
- **Thông báo sau giao dịch:** email, webhook hoặc message chỉ được phát sau khi thay đổi dữ liệu đã commit, đồng thời có cơ chế phục hồi nếu ứng dụng dừng giữa chừng.

Trong kiến trúc phân tầng, controller nhận hợp đồng HTTP; application service điều phối ca sử dụng; mô hình nghiệp vụ bảo vệ quy tắc đơn hàng; repository và outbox adapter lưu trạng thái. Việc chống lặp và phát thông báo cần được thiết kế xuyên các ranh giới này, với database làm nơi bảo vệ tính duy nhất và transaction làm ranh giới nhất quán cục bộ.

## 1. Vì sao request có thể được gửi nhiều lần?

HTTP request và response đi qua mạng không tạo thành một giao dịch nguyên tử giữa client và server. Server có thể đã xử lý và commit đơn hàng, nhưng response bị mất trên đường về. Client chỉ thấy timeout nên không biết đơn hàng đã được tạo hay chưa.

Các tình huống phổ biến:

- Người dùng nhấn nút “Đặt hàng” hai lần vì giao diện phản hồi chậm.
- Ứng dụng di động gửi lại request khi chuyển từ Wi-Fi sang mạng di động.
- API gateway hoặc HTTP client retry khi gặp lỗi kết nối tạm thời.
- Server commit thành công nhưng kết nối bị đóng trước khi client nhận response.
- Worker xử lý message lại vì broker giao message ít nhất một lần hoặc consumer không kịp xác nhận.

Không phải mọi request giống nhau đều là request trùng. Hai lần đặt cùng một sản phẩm có thể là hai ý định mua hàng khác nhau. Hệ thống cần một định danh cho **ý định cụ thể** để phân biệt retry của cùng thao tác với một thao tác mới.

## 2. Idempotency là gì?

Một thao tác có tính idempotent khi thực hiện lặp lại với cùng ý định và cùng dữ liệu không làm thay đổi kết quả nghiệp vụ sau lần đầu. Ví dụ, yêu cầu “đặt đơn với khóa K” khi được gửi lại nhiều lần chỉ nên tạo một đơn hàng và trả lại kết quả của lần xử lý đầu tiên.

Idempotency không có nghĩa mọi request có payload giống nhau đều phải gộp thành một. Hai đơn hàng giống hệt nhau có thể là hai giao dịch hợp lệ. Vì vậy, API ghi dữ liệu thường dùng **Idempotency-Key** do client tạo cho một ý định cụ thể.

Ví dụ:

~~~http
POST /api/orders
Idempotency-Key: 8d1b2f4c-...
Content-Type: application/json
~~~

Client phải giữ nguyên key khi retry cùng thao tác. Khi người dùng bắt đầu một ý định đặt hàng mới, client tạo key mới. Nếu client tạo key mới cho mỗi lần retry, server không thể nhận ra các request đó thuộc cùng một ý định.

Idempotency key nên có phạm vi rõ, thường gắn với:

- Người dùng hoặc tenant đã xác thực.
- Tên thao tác/API hoặc loại nghiệp vụ.
- Giá trị key do client cung cấp.

Không nên dùng key toàn cục mà không có phạm vi, vì hai client khác nhau có thể vô tình chọn cùng giá trị.

## 3. Phân biệt idempotency key với kiểm tra trùng dữ liệu

Hai cơ chế này bảo vệ hai ý nghĩa khác nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Idempotency key | Đây có phải retry của cùng một ý định đã gửi trước đó không? | Client gửi lại request tạo đơn với cùng key |
| Ràng buộc nghiệp vụ duy nhất | Dữ liệu này có được phép tồn tại nhiều lần không? | Một mã đơn hàng hoặc mã tham chiếu thanh toán chỉ được dùng một lần |
| Debounce ở giao diện | Có thể hạn chế thao tác nhấn lặp trong một khoảng thời gian không? | Vô hiệu hóa nút trong lúc gửi request |

Debounce giúp cải thiện trải nghiệm, nhưng không bảo vệ server trước retry từ mạng hoặc request đồng thời. Kiểm tra “đã có đơn giống payload chưa” cũng không thay thế idempotency key vì hai ý định khác nhau có thể có dữ liệu giống nhau.

Nên kết hợp các lớp bảo vệ phù hợp: giao diện tránh thao tác vô ý, API nhận idempotency key, database đặt unique constraint cho key trong phạm vi của nó, và nghiệp vụ có constraint riêng cho các định danh phải duy nhất.

## 4. Lưu idempotency record một cách bền vững

Một bảng idempotency có thể lưu:

| Trường | Mục đích |
|---|---|
| `caller_id` hoặc `tenant_id` | Phạm vi của caller đã xác thực |
| `operation` | Phân biệt thao tác, ví dụ `CREATE_ORDER` |
| `idempotency_key` | Khóa do client gửi |
| `request_hash` | Dấu vân tay của dữ liệu yêu cầu đã chuẩn hóa |
| `state` | `IN_PROGRESS`, `COMPLETED` hoặc trạng thái xử lý cần thiết |
| `response_status` | HTTP status của kết quả đã hoàn tất |
| `response_body` | Kết quả có thể phát lại cho retry |
| `created_at`, `expires_at` | Thời điểm tạo và thời hạn lưu |

Database cần bảo vệ tính duy nhất bằng ràng buộc:

~~~sql
create table idempotency_record (
    id                uuid primary key,
    caller_id         varchar(120) not null,
    operation         varchar(80) not null,
    idempotency_key   varchar(200) not null,
    request_hash      varchar(128) not null,
    state             varchar(24) not null,
    response_status   integer,
    response_body     text,
    created_at        timestamp not null,
    expires_at        timestamp not null,
    constraint uk_idempotency_scope_key
        unique (caller_id, operation, idempotency_key)
);
~~~

Ràng buộc unique ở database là lớp bảo vệ cuối cùng trước hai request đến đồng thời. Một đoạn code kiểu “đọc xem key đã tồn tại chưa, nếu chưa thì insert” mà không có unique constraint vẫn có race condition: cả hai request có thể cùng đọc thấy chưa tồn tại rồi cùng tạo đơn.

`request_hash` giúp phát hiện việc dùng lại một key cho payload khác. Hash nên được tính từ command đã chuẩn hóa theo quy tắc API, không nên hash trực tiếp chuỗi JSON thô nếu thứ tự field, khoảng trắng hoặc cách biểu diễn tương đương có thể khác nhau. Có thể dùng SHA-256 trên biểu diễn canonical của dữ liệu có ý nghĩa đối với thao tác.

## 5. Luồng xử lý request có idempotency

Một luồng đồng bộ điển hình:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Controller
    participant A as Application Service
    participant DB as Database

    C->>API: POST + Idempotency-Key K
    API->>A: command + caller + K
    A->>DB: INSERT idempotency record (unique)
    A->>DB: Tạo Order + ghi Outbox
    A->>DB: Lưu response vào idempotency record
    A->>DB: COMMIT
    DB-->>A: Commit thành công
    A-->>API: Kết quả đã lưu
    API-->>C: Response

    C->>API: Retry cùng key K
    API->>A: command + caller + K
    A->>DB: Đọc record theo phạm vi và key
    DB-->>A: COMPLETED + response đã lưu
    A-->>API: Phát lại kết quả
    API-->>C: Cùng kết quả nghiệp vụ
~~~

Các bước quan trọng:

1. Xác thực caller và kiểm tra request ở tầng trình bày.
2. Xác định phạm vi key từ caller, operation và header.
3. Tính fingerprint từ command đã chuẩn hóa.
4. Thử tạo idempotency record với unique constraint.
5. Trong cùng transaction, thực hiện thay đổi nghiệp vụ, ghi outbox và lưu kết quả phản hồi.
6. Commit tất cả thay đổi local cùng nhau.
7. Nếu request lặp đến sau, đọc record và phát lại kết quả đã lưu thay vì thực hiện lại ca sử dụng.

Với luồng đồng bộ ngắn, có thể tạo record, xử lý nghiệp vụ và đánh dấu `COMPLETED` trong cùng transaction. Record chưa commit không hiển thị cho transaction khác. Request đồng thời dùng cùng key có thể phải chờ unique index hoặc nhận lỗi xung đột sau khi transaction đầu commit. Nếu transaction đầu rollback, request còn lại có thể trở thành request thực hiện thao tác.

Vì record và đơn hàng được commit cùng nhau, không tồn tại trạng thái “đã đánh dấu hoàn tất nhưng đơn hàng chưa được tạo” trong cùng database transaction, miễn là mọi thao tác đó thực sự dùng chung transaction manager và database.

## 6. Xử lý cùng key nhưng payload khác

Cùng một key phải đại diện cho cùng một ý định và cùng dữ liệu có ý nghĩa. Nếu key K đã được dùng để đặt đơn với 2 sản phẩm, một request khác dùng lại K nhưng gửi 5 sản phẩm cần bị từ chối.

Quy tắc xử lý thường là:

| Trạng thái record | Fingerprint | Hành vi |
|---|---|---|
| Chưa có | Bất kỳ hợp lệ | Tiếp nhận xử lý mới |
| `COMPLETED` | Trùng | Phát lại status/body đã lưu |
| `COMPLETED` | Khác | Từ chối, thường dùng `409 Conflict` |
| `IN_PROGRESS` | Trùng | Trả trạng thái đang xử lý, hoặc hướng dẫn polling/retry |
| `IN_PROGRESS` | Khác | Từ chối vì key đang gắn với request khác |

Không nên chỉ trả lại response cũ khi payload mới khác fingerprint. Điều đó có thể khiến client tưởng yêu cầu mới đã được xử lý trong khi server thực chất đang trả kết quả của một thao tác khác.

Nếu API lưu response để phát lại, cần xác định những phần nào thuộc hợp đồng ổn định: HTTP status, body và các header quan trọng như `Location`. Không nhất thiết lưu mọi header truyền tải. Không lưu token, thông tin xác thực hoặc dữ liệu nhạy cảm vào response record nếu không cần thiết; áp dụng chính sách mã hóa, quyền truy cập và thời hạn lưu phù hợp.

## 7. Java/Spring: đặt ranh giới transaction đúng

Controller chỉ nhận key và chuyển request thành command:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final PlaceOrderFacade facade;

    public OrderController(PlaceOrderFacade facade) {
        this.facade = facade;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> place(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateOrderRequest request,
            Principal principal) {

        PlaceOrderResponse response = facade.execute(
                principal.getName(),
                key,
                request
        );

        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Facade không mở transaction. Nó gọi một bean khác có phương thức transaction để exception từ commit có thể được xử lý sau khi proxy kết thúc transaction:

~~~java
@Service
public class PlaceOrderFacade {
    private final PlaceOrderTransaction transaction;
    private final IdempotencyReader reader;
    private final RequestFingerprint fingerprint;

    public PlaceOrderFacade(
            PlaceOrderTransaction transaction,
            IdempotencyReader reader,
            RequestFingerprint fingerprint) {
        this.transaction = transaction;
        this.reader = reader;
        this.fingerprint = fingerprint;
    }

    public PlaceOrderResponse execute(
            String callerId,
            String key,
            CreateOrderRequest request) {

        String hash = fingerprint.of(request);

        try {
            return transaction.execute(callerId, key, hash, request);
        } catch (DataIntegrityViolationException exception) {
            if (!isIdempotencyKeyConstraint(exception)) {
                throw exception;
            }

            return reader.replayOrReject(callerId, key, hash);
        }
    }

    private boolean isIdempotencyKeyConstraint(
            DataIntegrityViolationException exception) {
        // Kiểm tra đúng tên unique constraint của database/driver.
        return ConstraintErrors.isNamed(
                exception,
                "uk_idempotency_scope_key"
        );
    }
}
~~~

`ConstraintErrors` là helper minh họa, cần triển khai theo database và driver của dự án. Chỉ chuyển lỗi của đúng unique constraint idempotency thành luồng replay; không được coi mọi `DataIntegrityViolationException` là request trùng vì lỗi đó có thể là vi phạm constraint nghiệp vụ khác.

Bean thực hiện transaction:

~~~java
@Service
public class PlaceOrderTransaction {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderTransaction(
            IdempotencyRepository idempotency,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.idempotency = idempotency;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PlaceOrderResponse execute(
            String callerId,
            String key,
            String requestHash,
            CreateOrderRequest request) {

        IdempotencyRecord record = idempotency.insertNew(
                callerId,
                "CREATE_ORDER",
                key,
                requestHash
        );

        Order order = Order.create(
                request.customerId(),
                request.items()
        );
        orders.save(order);

        OrderPlaced event = OrderPlaced.from(order);
        outbox.save(OutboxMessage.from(event));

        PlaceOrderResponse response =
                PlaceOrderResponse.from(order);

        record.complete(
                HttpStatus.CREATED.value(),
                response
        );

        return response;
    }
}
~~~

Đây là cấu trúc minh họa; repository cần thực hiện insert idempotency record và lưu response đúng cách. Với JPA, lỗi unique constraint có thể chỉ xuất hiện khi flush hoặc commit. Vì vậy facade phải bao quanh lời gọi qua Spring proxy và xử lý lỗi sau khi transaction bean kết thúc. Không nên bắt lỗi unique rồi tiếp tục sử dụng transaction đã bị đánh dấu rollback-only.

`IdempotencyReader.replayOrReject` đọc record trong một transaction/read operation mới, so sánh fingerprint và trả kết quả đã lưu hoặc lỗi xung đột. Nếu request đồng thời đang chờ transaction đầu commit, reader có thể chưa thấy record ngay; cần retry đọc có giới hạn hoặc trả trạng thái đang xử lý tùy thiết kế. Với hệ quản trị và isolation level cụ thể, cần kiểm tra hành vi khi unique conflict và commit cạnh tranh bằng integration test.

## 8. Khi xử lý kéo dài: trạng thái IN_PROGRESS và lease

Với thao tác chỉ gồm database local và hoàn tất nhanh, một transaction duy nhất có thể tạo record và hoàn tất record cùng lúc. Nhưng nếu quy trình kéo dài qua nhiều bước hoặc gọi hệ thống ngoài, không nên giữ transaction mở trong suốt quy trình.

Khi đó có thể dùng hai giai đoạn:

1. Transaction ngắn tạo record `IN_PROGRESS`, lưu fingerprint và thông tin công việc cần xử lý; commit.
2. Worker nhận việc, thực hiện từng bước bằng transaction ngắn và cập nhật record thành `COMPLETED` khi đã có kết quả.

Request lặp với cùng key và fingerprint trong lúc xử lý có thể nhận `202 Accepted` cùng URL tra cứu trạng thái, hoặc `409 Conflict`/`Retry-After` theo hợp đồng API. Key cùng fingerprint không được khởi chạy một công việc thứ hai.

Nếu worker chết giữa chừng, cần lease hoặc cơ chế claim có thời hạn để worker khác có thể tiếp tục sau khi lease hết hạn. Lease nên có owner/token và thời điểm hết hạn; worker cũ cần kiểm tra quyền sở hữu trước khi ghi kết quả để tránh một worker cũ thức dậy và ghi đè tiến trình mới. Việc xử lý phải idempotent ở từng bước có tác dụng phụ.

Không nên để record `IN_PROGRESS` tồn tại vô hạn. Cần có timeout, số lần thử, trạng thái thất bại có thể phục hồi, và công cụ vận hành để tra cứu hoặc xử lý thủ công.

## 9. Vì sao thông báo phải gắn với kết quả commit?

Giả sử ứng dụng tạo đơn hàng rồi gửi email xác nhận trước khi transaction database commit. Email có thể đến khách hàng dù transaction sau đó rollback vì lỗi lưu trữ. Người nhận được thông báo về một đơn hàng không tồn tại.

Nếu gửi email sau commit bằng một lời gọi trực tiếp, một rủi ro khác xuất hiện: database commit thành công, nhưng dịch vụ email không phản hồi hoặc process dừng trước khi gửi. Đơn hàng tồn tại nhưng thông báo chưa được gửi.

Có thể phân biệt:

~~~mermaid
flowchart TD
    A["Application Service"] --> B["Transaction database"]
    B --> C["Lưu Order"]
    B --> D["Lưu ý định phát sự kiện"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Xử lý sau commit"]
    F --> G["Email / Webhook / Message Broker"]
~~~

Điểm quan trọng là dữ liệu nghiệp vụ và ý định phát thông báo cần được ghi nhận nhất quán. Cách thực hiện phụ thuộc mức độ tin cậy cần có.

## 10. AFTER_COMMIT event: phù hợp cho việc best-effort

Spring hỗ trợ `@TransactionalEventListener` để lắng nghe event ở giai đoạn transaction cụ thể:

~~~java
@Component
public class OrderNotificationListener {
    private final EmailClient emailClient;

    public OrderNotificationListener(EmailClient emailClient) {
        this.emailClient = emailClient;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        emailClient.sendOrderConfirmation(
                event.orderId(),
                event.customerEmail()
        );
    }
}
~~~

Listener `AFTER_COMMIT` chỉ được gọi sau khi transaction đã commit. Nếu transaction rollback, listener không được thực hiện theo luồng thông thường. Điều này tránh gửi thông báo trước khi dữ liệu nghiệp vụ được xác nhận.

Tuy nhiên, event in-process không phải hàng đợi bền vững. Nếu process dừng sau commit nhưng trước khi listener chạy, event có thể mất. Nếu lời gọi email thất bại, transaction đã commit nên không thể rollback đơn hàng chỉ bằng cách ném exception từ listener. Nếu listener chạy đồng bộ, lỗi có thể làm request trả lỗi dù đơn hàng đã được commit; client retry khi đó cần idempotency key để không tạo đơn thứ hai.

Có thể dùng `@Async` cho listener để không chặn request, nhưng việc chạy bất đồng bộ trong bộ nhớ vẫn không bảo đảm phục hồi sau khi process dừng. `AFTER_COMMIT` phù hợp với công việc best-effort hoặc có thể tái tạo, chẳng hạn làm mới cache không quan trọng. Với thông báo bắt buộc phải được gửi hoặc cần retry bền vững, nên cân nhắc Outbox.

## 11. Transactional Outbox cho thông báo bền vững

Transactional Outbox ghi thay đổi nghiệp vụ và bản ghi sự kiện vào cùng database transaction. Một worker riêng đọc outbox và gửi thông báo sau commit.

Ví dụ, transaction tạo đơn lưu cả đơn hàng và event:

~~~java
@Transactional
public PlaceOrderResponse createOrder(CreateOrderCommand command) {
    Order order = Order.create(command);
    orders.save(order);

    OrderPlaced event = OrderPlaced.from(order);
    outbox.save(OutboxMessage.pending(
            event.eventId(),
            "OrderPlaced",
            order.id(),
            event
    ));

    return PlaceOrderResponse.from(order);
}
~~~

Nếu transaction rollback, cả đơn hàng và outbox record đều rollback. Nếu commit, cả hai cùng tồn tại. Worker có thể gửi thông báo sau đó, kể cả khi ứng dụng web đã kết thúc request.

Một bản ghi outbox thường có:

- `event_id`: định danh duy nhất, ổn định.
- `event_type`: loại sự kiện nghiệp vụ.
- `aggregate_id`: định danh đơn hàng hoặc đối tượng liên quan.
- `payload`: dữ liệu cần cho consumer.
- `created_at`: thời điểm ghi sự kiện.
- `status`, `attempt_count`, `next_attempt_at`: trạng thái và lịch retry.
- `locked_until` hoặc thông tin claim: hỗ trợ nhiều worker xử lý song song.

Luồng publisher:

~~~mermaid
sequenceDiagram
    participant W as Outbox Worker
    participant DB as Database
    participant N as Notification Provider

    W->>DB: Claim batch trong transaction ngắn
    DB-->>W: Danh sách event + lease
    Note over W,DB: Commit transaction claim
    W->>N: Gửi thông báo (ngoài transaction)
    N-->>W: Thành công
    W->>DB: Đánh dấu SENT trong transaction mới
    DB-->>W: Commit
~~~

Không nên giữ transaction database mở trong lúc chờ email provider hoặc message broker. Worker nên claim một lô bằng transaction ngắn, commit, gọi mạng bên ngoài transaction, rồi cập nhật kết quả bằng transaction mới. Với nhiều worker, có thể dùng row locking như `FOR UPDATE SKIP LOCKED` nếu database hỗ trợ, hoặc cơ chế claim/lease tương đương.

## 12. Outbox không tạo ra exactly-once delivery

Có một cửa sổ lỗi không thể loại bỏ chỉ bằng outbox:

1. Worker gửi email thành công.
2. Email provider đã nhận yêu cầu.
3. Worker bị dừng trước khi đánh dấu outbox là `SENT`.
4. Lease hết hạn, worker khác gửi lại cùng event.

Kết quả là provider có thể nhận hai lần. Vì vậy, outbox thường cung cấp **at-least-once delivery**: event đã lưu sẽ được thử gửi cho đến khi hoàn tất theo chính sách, nhưng một event có thể được gửi nhiều lần.

Cần thiết kế consumer và provider theo hướng idempotent:

- Dùng `event_id` làm khóa idempotency nếu provider hỗ trợ.
- Consumer lưu các event đã xử lý với unique constraint trên `event_id`.
- Ghi nhận kết quả xử lý và thay đổi dữ liệu consumer trong cùng transaction local.
- Với email provider không hỗ trợ idempotency, lưu notification ledger và đối soát trạng thái gửi; vẫn phải thừa nhận có cửa sổ không chắc chắn nếu provider đã gửi nhưng response bị mất.
- Có retry với exponential backoff, giới hạn số lần thử và dead-letter/manual review cho lỗi kéo dài.

Không nên tuyên bố hệ thống gửi email “đúng một lần” chỉ vì có outbox hoặc consumer deduplication. Có thể đạt xử lý hiệu quả một lần ở phạm vi database consumer, nhưng tác dụng phụ ở hệ thống bên ngoài vẫn phụ thuộc hợp đồng và khả năng idempotency của provider.

## 13. Kết hợp idempotency và outbox để chống gửi trùng

Idempotency bảo vệ thao tác tạo đơn khỏi request lặp. Outbox bảo vệ ý định thông báo khỏi bị mất giữa commit và gửi. Hai cơ chế nên được nối trong cùng transaction tạo đơn:

~~~mermaid
flowchart TD
    A["POST /orders + Idempotency-Key"] --> B["Application Service"]
    B --> C["Transaction"]
    C --> D["Insert idempotency record"]
    C --> E["Create Order"]
    C --> F["Insert Outbox event"]
    C --> G["Store response in idempotency record"]
    D --> H["COMMIT"]
    E --> H
    F --> H
    G --> H
    H --> I["Return response"]
    H --> J["Outbox publisher"]
    J --> K["Notification provider"]
~~~

Nếu client retry cùng key, server phát lại response và không tạo order hoặc outbox event mới. Nếu publisher retry event vì không chắc lần gửi trước đã thành công, `event_id` giúp consumer hoặc provider nhận diện cùng một thông báo.

Cần bảo đảm idempotency record, order và outbox nằm trong cùng transaction manager/database. Nếu lưu idempotency record ở một database khác, hoặc phát event trước commit mà không có cơ chế bền vững, tính nguyên tử cục bộ này không còn được bảo đảm.

## 14. Xử lý lỗi và retry có chủ đích

Không phải mọi lỗi đều nên retry theo cùng cách:

| Tình huống | Cách xử lý gợi ý |
|---|---|
| Request sai dữ liệu | Trả lỗi validation; không tạo tác dụng phụ |
| Cùng key, cùng fingerprint, đã hoàn tất | Phát lại kết quả đã lưu |
| Cùng key, payload khác | Trả lỗi xung đột theo hợp đồng |
| Cùng key đang xử lý | Trả trạng thái đang xử lý hoặc hướng dẫn retry/poll |
| Database rollback trước commit | Không có kết quả thành công; client có thể retry cùng key |
| Timeout khi gọi provider | Kết quả có thể chưa xác định; tra cứu/retry cùng idempotency key |
| Provider tạm thời không khả dụng | Retry có backoff và giới hạn |
| Lỗi vĩnh viễn hoặc payload không hợp lệ | Đánh dấu cần xử lý, không retry vô hạn |

Retry cần có giới hạn, backoff và jitter để tránh nhiều worker cùng tạo tải đột biến lên một dịch vụ đang gặp sự cố. Các lỗi không thể tự phục hồi cần dead-letter hoặc hàng đợi xử lý thủ công. Log và metric nên có `orderId`, idempotency key đã được che/mã hóa phù hợp, `eventId`, số lần thử và correlation ID để truy vết toàn luồng.

## 15. Kiểm thử các tình huống cạnh tranh và lỗi giữa chừng

Unit test có thể kiểm tra quy tắc fingerprint và xử lý trạng thái, nhưng cần integration test với database thật hoặc môi trường tương đương để xác minh unique constraint và transaction.

Các tình huống nên có:

| Tình huống | Điều cần xác minh |
|---|---|
| Gửi cùng key hai lần tuần tự | Chỉ một order và một outbox event; response được phát lại |
| Gửi cùng key đồng thời | Unique constraint ngăn hai transaction tạo hai đơn |
| Cùng key nhưng payload khác | Request thứ hai bị từ chối |
| Transaction tạo đơn rollback | Không có order, idempotency completion hoặc outbox event đã commit |
| Commit thành công nhưng client timeout | Retry cùng key nhận lại kết quả đã lưu |
| Publisher gửi thành công rồi dừng trước khi đánh dấu SENT | Event có thể được gửi lại; consumer/provider xử lý idempotent |
| Provider tạm ngừng | Outbox còn lại và được retry theo lịch |
| Key hết hạn | Hành vi tái sử dụng key tuân theo chính sách retention đã công bố |

Khi kiểm thử cạnh tranh, dùng hai transaction hoặc hai request thực sự chạy song song. Một test tuần tự không chứng minh được unique constraint hoạt động đúng trong race condition. Cần xác minh đúng tên constraint được nhận diện để không nhầm lỗi dữ liệu khác thành idempotency conflict.

Cũng cần kiểm tra các tình huống rollback và commit thực tế. Test chỉ mock repository có thể xác nhận facade gọi một phương thức, nhưng không xác nhận transaction boundary, unique index hoặc outbox cùng commit.

## 16. Checklist thiết kế cho API đặt hàng

Trước khi phát hành API có tác dụng phụ, hãy rà soát:

- [ ] Client tạo key ổn định cho một ý định và giữ nguyên key khi retry.
- [ ] Key được giới hạn theo caller/tenant và operation.
- [ ] Server chuẩn hóa request và so sánh fingerprint khi key đã tồn tại.
- [ ] Database có unique constraint cho phạm vi key.
- [ ] Record idempotency, dữ liệu nghiệp vụ và outbox được commit cùng nhau khi dùng chung database.
- [ ] Response đã hoàn tất có thể được phát lại nhất quán.
- [ ] Request đang xử lý có trạng thái, timeout và chính sách polling/retry rõ.
- [ ] Key có thời hạn lưu phù hợp với thời gian retry và đối soát.
- [ ] Không gọi email/webhook/message broker trong transaction database.
- [ ] Thông báo quan trọng dùng outbox hoặc cơ chế durable tương đương.
- [ ] Publisher có claim/lease, retry, backoff và quan sát lỗi.
- [ ] Consumer/provider có cơ chế idempotency hoặc deduplication phù hợp.
- [ ] Không tuyên bố exactly-once cho tác dụng phụ bên ngoài khi chưa có bảo đảm từ provider.
- [ ] Integration test bao phủ request đồng thời, rollback, timeout và publisher crash.

Một thiết kế tốt phân biệt rõ ba điều: client có thể gửi lại cùng ý định; database transaction chỉ bảo đảm tính nguyên tử trong phạm vi resource được quản lý; và thông báo qua mạng cần cơ chế giao nhận, retry, deduplication riêng. Khi idempotency record, đơn hàng và outbox được ghi cùng transaction, ứng dụng có thể trả kết quả ổn định cho request lặp và tiếp tục gửi thông báo sau commit mà không giữ transaction mở trong lúc chờ mạng.

