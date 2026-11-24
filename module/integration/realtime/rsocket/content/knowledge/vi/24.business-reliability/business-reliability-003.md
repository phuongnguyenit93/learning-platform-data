# Thiết kế khóa chống xử lý lặp (idempotency key) cho lệnh có tác dụng phụ

Trong hệ thống RSocket, client có thể gửi lệnh tạo đơn hàng, trừ tiền, đặt chỗ hoặc điều khiển thiết bị. Kết nối có thể bị ngắt sau khi server đã nhận lệnh nhưng trước khi client nhận được kết quả. Khi retry, client không biết chắc lần gửi đầu đã được xử lý hay chưa. Nếu server thực hiện lại tác dụng phụ, một thao tác nghiệp vụ có thể xảy ra hai lần.

**Idempotency key** là mã định danh ổn định cho một lần thực hiện nghiệp vụ logic. Client tạo key một lần và gửi lại chính key đó trong mọi lần retry. Server lưu key cùng trạng thái và kết quả xử lý để nhận ra request trùng, ngăn thực hiện tác dụng phụ lần nữa và trả lại kết quả đã có khi phù hợp.

Idempotency không làm cho mạng trở thành exactly-once. Nó tạo ra hành vi xử lý lặp an toàn trong một phạm vi, một kho lưu trữ và một khoảng thời gian được thiết kế rõ ràng. Độ tin cậy đến từ việc kết hợp key ổn định, ghi nhận nguyên tử, kiểm tra nội dung request, lưu kết quả và quy tắc retry.

## 1. Vì sao lệnh RSocket cần idempotency key?

RSocket cung cấp giao tiếp hai chiều và các interaction model như request-response, fire-and-forget, request-stream và request-channel. Những cơ chế này không tự đảm bảo một lệnh nghiệp vụ chỉ được thực hiện một lần.

Xét tình huống client yêu cầu thanh toán:

```text
Client                                      Server
  |                                           |
  | REQUEST_RESPONSE: capture payment        |
  |------------------------------------------>|
  |                                           | trừ tiền thành công
  |                                           |
  X kết nối bị ngắt trước khi nhận response   |
  |                                           |
  | không biết server đã xử lý hay chưa       |
  |                                           |
  | retry request                             |
  |------------------------------------------>|
  |                                           | có thể trừ tiền lần hai
```

Timeout ở client chỉ nói rằng client chưa nhận được kết quả trong thời hạn. Nó không chứng minh server chưa nhận hoặc chưa hoàn tất lệnh. Connection resumption có thể khôi phục một phiên RSocket còn đủ trạng thái, nhưng nếu client mở request mới hoặc tạo connection mới thì server vẫn cần nhận diện lệnh nghiệp vụ đã được gửi trước đó.

Idempotency key giải quyết vấn đề bằng cách gắn mọi lần gửi lại với cùng một định danh:

```text
Lệnh logic: capture payment #P-42
Idempotency-Key: 7b7f...a91c

Attempt 1  ---- key=7b7f...a91c ----> server xử lý
Attempt 2  ---- key=7b7f...a91c ----> server trả kết quả đã lưu
Attempt 3  ---- key=7b7f...a91c ----> server trả kết quả đã lưu
```

Server chỉ tạo tác dụng phụ cho lần claim key đầu tiên. Những lần sau được xử lý theo trạng thái đã lưu.

## 2. Idempotency key đại diện cho một lệnh logic

Key phải được tạo cho **một ý định nghiệp vụ**, không phải cho từng lần gửi qua mạng.

Ví dụ client muốn tạo một lệnh chuyển tiền:

```java
UUID key = UUID.randomUUID();

TransferCommand command = new TransferCommand(
    key,
    sourceAccountId,
    destinationAccountId,
    new BigDecimal("125.00"),
    "USD");
```

Nếu request timeout và cần retry, client gửi lại cùng `TransferCommand` và cùng key. Không tạo UUID mới trong mỗi lần retry:

```java
Mono<TransferReceipt> sendTransfer(TransferCommand command) {
    return requester
        .route("accounts.transfer")
        .data(command)
        .retrieveMono(TransferReceipt.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));
}
```

Trong ví dụ, `command.idempotencyKey()` không thay đổi giữa các lần subscribe/retry. Nếu client tạo key bên trong `defer` hoặc mapper retry, mỗi attempt có thể nhận key mới và server sẽ coi đó là lệnh khác.

Nếu retry có thể diễn ra sau khi ứng dụng client khởi động lại, client nên lưu key và command trong outbox hoặc local durable store trước lần gửi đầu. Chỉ giữ key trong biến RAM không đủ để retry an toàn sau process restart.

## 3. Phạm vi duy nhất của key (scope)

Key cần có một phạm vi duy nhất rõ ràng. Không nên giả định UUID tự nó giải quyết mọi vấn đề về phạm vi, tenant hoặc loại thao tác.

Một khóa lưu trữ thường được xác định bởi tổ hợp:

```text
scope = tenant + authenticated actor (nếu cần) + operation + idempotency key
```

Ví dụ:

| Thành phần | Giá trị ví dụ | Mục đích |
|---|---|---|
| Tenant | `tenant-17` | Cô lập dữ liệu giữa các khách hàng. |
| Actor | `user-42` hoặc service identity | Phân biệt người/ứng dụng tạo lệnh nếu nghiệp vụ yêu cầu. |
| Operation | `accounts.transfer:v1` | Không dùng chung key giữa các loại lệnh khác nhau. |
| Key | `7b7f...a91c` | Nhận diện lần thực hiện logic. |

Scope cụ thể phụ thuộc hợp đồng API. Nếu key chỉ cần duy nhất trong tenant và operation, không cần thêm actor. Nếu một tenant có nhiều người dùng và mỗi người có quyền tạo lệnh độc lập, thêm actor có thể là cần thiết. Dù chọn scope nào, mọi node xử lý cùng một nghiệp vụ phải tính scope theo cùng quy tắc.

Không tin `tenantId` hoặc `actorId` do client tự gửi trong payload để quyết định scope. Tenant và danh tính nên lấy từ principal/security context đã được xác thực; server dùng thông tin đó cùng operation và key để tạo khóa lưu trữ.

## 4. Tách idempotency key khỏi request fingerprint

Key trả lời câu hỏi: “Đây có phải cùng một lệnh logic không?”. Request fingerprint trả lời câu hỏi: “Nội dung của lệnh có giống lần đầu không?”. Hai khái niệm này phải được kiểm tra cùng nhau.

Server tính fingerprint từ biểu diễn chuẩn hóa của các trường có ý nghĩa nghiệp vụ, ví dụ:

```text
fingerprint = SHA-256(
    canonical(operation, sourceAccount, destinationAccount, amount, currency)
)
```

Không đưa những trường thay đổi theo lần gửi vào fingerprint nếu chúng không làm thay đổi ý nghĩa lệnh, chẳng hạn trace ID, timestamp gửi lại, transport metadata hoặc access token. Ngược lại, không được bỏ qua một trường nghiệp vụ có thể làm thay đổi tác dụng phụ.

Khi server nhận một key đã tồn tại:

| Key | Fingerprint | Hành vi |
|---|---|---|
| Chưa tồn tại | Bất kỳ fingerprint hợp lệ | Claim key và bắt đầu xử lý. |
| Đã tồn tại | Giống fingerprint cũ | Không chạy lại tác dụng phụ; trả hoặc báo trạng thái của lần xử lý cũ. |
| Đã tồn tại | Khác fingerprint cũ | Từ chối vì cùng key đang bị dùng cho hai lệnh khác nhau. |

Không âm thầm trả kết quả cũ cho một request có payload khác. Ví dụ client gửi key `K1` để chuyển 100 USD, sau đó dùng lại `K1` để chuyển 900 USD; server phải báo xung đột key/payload thay vì trả receipt của lệnh 100 USD và khiến caller tưởng lệnh 900 USD đã được xử lý.

## 5. Sinh key ở phía client

Key nên khó trùng, không đoán được dễ dàng và có định dạng ổn định giữa các lần gửi. UUID ngẫu nhiên là lựa chọn phổ biến; ULID hoặc một ID do hệ thống cấp cũng có thể dùng nếu bảo đảm uniqueness theo phạm vi đã chọn.

Các nguyên tắc:

1. Sinh key khi người dùng hoặc hệ thống tạo một ý định nghiệp vụ mới.
2. Lưu key cùng command trước khi gửi nếu cần phục hồi sau restart.
3. Giữ nguyên key khi retry, reconnect hoặc gửi lại sau timeout.
4. Tạo key mới khi người dùng thực sự tạo một lệnh nghiệp vụ mới, kể cả payload giống hệt lệnh cũ.
5. Không dùng timestamp đơn lẻ, số thứ tự cục bộ dễ trùng hoặc hash payload làm key mặc định.
6. Không dùng idempotency key như credential hoặc bằng chứng xác thực.

Hai lệnh chuyển tiền giống hệt nhau có thể là hai ý định hợp lệ khác nhau. Nếu dùng hash payload làm key, server có thể nhầm lệnh thứ hai là retry của lệnh đầu và bỏ qua giao dịch hợp lệ. Vì vậy key và fingerprint cần độc lập.

## 6. Truyền key qua RSocket

Có hai vị trí phổ biến để truyền key:

- **Data payload:** key là một trường trong command DTO. Cách này rõ ràng, dễ version hóa và không cần custom metadata extractor.
- **Custom metadata:** key là metadata cross-cutting, có MIME type riêng và được trích xuất thành header ở server.

Với lệnh có tác dụng phụ, đưa key vào command DTO thường làm hợp đồng dễ kiểm tra hơn:

```java
public record CapturePaymentCommand(
    UUID idempotencyKey,
    UUID orderId,
    BigDecimal amount,
    String currency
) {}
```

Client gửi request-response:

```java
Mono<PaymentReceipt> capture(CapturePaymentCommand command) {
    return requester
        .route("payments.capture")
        .data(command)
        .retrieveMono(PaymentReceipt.class);
}
```

Nếu dùng metadata, client có thể gắn key như custom metadata:

```java
Mono<PaymentReceipt> capture(
        CapturePaymentCommand command, UUID key) {
    return requester
        .route("payments.capture")
        .metadata(key.toString(), IDEMPOTENCY_KEY_MIME_TYPE)
        .data(command)
        .retrieveMono(PaymentReceipt.class);
}
```

Khi đó server cần cấu hình `MetadataExtractor`/`metadataToExtract(...)` để đưa key vào message header. Phải quy định rõ key nằm ở payload hay metadata; tránh cho phép hai giá trị khác nhau cùng xuất hiện mà không có quy tắc ưu tiên.

Routing metadata chỉ dùng để chọn handler. Không nhầm route hoặc stream ID với idempotency key. Stream ID thay đổi theo từng tương tác trên kết nối, còn idempotency key phải ổn định qua các lần gửi lại cùng một lệnh nghiệp vụ.

## 7. Lưu trữ key với ràng buộc duy nhất

Để chống hai request đồng thời cùng claim một key, server cần một cơ chế atomic tại nơi lưu trữ dùng chung. Một bảng idempotency có thể có cấu trúc:

```sql
CREATE TABLE idempotency_record (
    tenant_id       UUID         NOT NULL,
    operation       VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash    CHAR(64)     NOT NULL,
    state           VARCHAR(20)  NOT NULL,
    response_json   JSONB,
    created_at      TIMESTAMPTZ  NOT NULL,
    updated_at      TIMESTAMPTZ  NOT NULL,
    expires_at      TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
```

Đây là ví dụ schema PostgreSQL; kiểu JSON, UUID và cú pháp thời gian có thể thay đổi theo database. Nếu scope cần actor, thêm actor vào unique key. Ràng buộc `PRIMARY KEY` hoặc `UNIQUE` là phần quan trọng: hai node nhận cùng key đồng thời không thể cùng tạo hai record claim thành công.

Không dùng `Map` trong bộ nhớ của một instance làm kho idempotency chính trong hệ thống nhiều node. Hai instance có thể cùng nhận request và mỗi instance đều thấy key chưa tồn tại. Khi restart, dữ liệu trong RAM cũng mất. Dùng database hoặc kho phân tán có atomic conditional write và retention phù hợp.

## 8. Claim key một cách nguyên tử

Luồng xử lý phải có một bước claim duy nhất. Ý tưởng là thử insert record theo unique key; chỉ request insert thành công mới được quyền thực hiện tác dụng phụ.

```text
Request A, key=K ----\
                      +--> atomic INSERT/claim(K)
Request B, key=K ----/             |
                                   +--> A thắng: được xử lý
                                   +--> B thua: đọc trạng thái của A
```

Pseudocode ở tầng repository:

```java
Mono<Boolean> tryClaim(IdempotencyScope scope,
                       String key,
                       String requestHash);
```

Repository cần thực hiện thao tác insert-if-absent dựa trên unique constraint hoặc conditional write của datastore. Không triển khai bằng hai bước không nguyên tử kiểu “SELECT xem có chưa, nếu chưa thì INSERT”; hai request có thể cùng SELECT trước khi request nào INSERT.

Kết quả `true` nghĩa là request này tạo claim thành công. `false` nghĩa là key đã tồn tại và caller phải đọc record hiện có để quyết định replay, chờ hoặc báo conflict. Lỗi database không được diễn giải thành “key mới”; nếu không thể xác minh claim, phải dừng xử lý để tránh thực hiện side effect không có bảo vệ.

## 9. Trạng thái xử lý của idempotency record

Một mô hình trạng thái đơn giản:

```text
                  claim thành công
        NEW ----------------------------> IN_PROGRESS
                                            |
                      xử lý thành công     |     lỗi cuối cùng
                          +----------------+----------------+
                          v                                 v
                     COMPLETED                           FAILED
```

| Trạng thái | Ý nghĩa | Request trùng nên làm gì? |
|---|---|---|
| `IN_PROGRESS` | Một request đã claim key và đang thực hiện. | Chờ kết quả trong giới hạn, trả trạng thái đang xử lý hoặc yêu cầu caller truy vấn sau. Không chạy side effect lần nữa. |
| `COMPLETED` | Tác dụng phụ đã hoàn tất và kết quả được lưu. | Trả lại kết quả đã lưu nếu fingerprint khớp. |
| `FAILED_FINAL` | Lệnh thất bại theo kết quả cuối cùng đã được ghi nhận. | Trả lại lỗi/kết quả cuối cùng theo contract. |
| `RETRYABLE` | Lần xử lý trước thất bại theo cách được phép thử lại. | Claim lại theo quy tắc lease/owner/version có kiểm soát. |

Không phải hệ thống nào cũng cần mọi trạng thái. Điều quan trọng là phân biệt “đang xử lý”, “đã có kết quả cuối cùng” và “có thể thử lại”. Tránh xóa record ngay khi một request lỗi vì retry sau đó có thể thực hiện side effect lần nữa trong khi trạng thái thật chưa được xác định.

## 10. Xử lý request mới, request trùng và key conflict

Một service có thể dùng quy tắc sau:

```java
Mono<PaymentReceipt> handle(
        IdempotencyScope scope,
        CapturePaymentCommand command) {

    String hash = fingerprint(command);

    return repository.tryClaim(scope, command.idempotencyKey(), hash)
        .flatMap(claimed -> {
            if (claimed) {
                return executeAndStore(scope, command, hash);
            }
            return repository.find(scope, command.idempotencyKey())
                .flatMap(record -> replayOrReject(record, hash));
        });
}
```

Hàm `replayOrReject(...)` phải kiểm tra fingerprint và state:

```java
Mono<PaymentReceipt> replayOrReject(
        IdempotencyRecord record, String incomingHash) {

    if (!record.requestHash().equals(incomingHash)) {
        return Mono.error(new IdempotencyKeyConflictException());
    }

    return switch (record.state()) {
        case COMPLETED -> Mono.just(record.receipt());
        case IN_PROGRESS -> Mono.error(new CommandInProgressException());
        case FAILED_FINAL -> Mono.error(record.failure());
        case RETRYABLE -> retryClaimAccordingToPolicy(record);
    };
}
```

Đây là skeleton minh họa; kiểu trả về cho `FAILED_FINAL` và cách chờ `IN_PROGRESS` cần được thiết kế theo API cụ thể. Một số hệ thống trả DTO trạng thái thay vì phát lỗi giao thức để caller có thể phân biệt `COMPLETED`, `IN_PROGRESS` và `CONFLICT`.

Không để request trùng `IN_PROGRESS` tự động chạy cùng service method lần nữa. Nếu cần chờ, dùng notification, polling có backoff hoặc một cơ chế future/result store gắn với key.

## 11. Ghi claim, tác dụng phụ và kết quả trong cùng transaction

Nếu tác dụng phụ nằm trong cùng database, cách mạnh nhất thường là thực hiện claim, cập nhật dữ liệu nghiệp vụ và lưu kết quả idempotency trong cùng một transaction.

```text
BEGIN
  INSERT idempotency_record (scope, key, hash, state=IN_PROGRESS)
  -- insert chỉ thành công nếu key chưa tồn tại

  UPDATE account / INSERT payment / ...

  UPDATE idempotency_record
     SET state=COMPLETED, response_json=<receipt>
COMMIT
```

Nếu transaction commit, cả tác dụng phụ và kết quả idempotency cùng tồn tại. Nếu transaction rollback, claim và thay đổi nghiệp vụ cùng rollback; lần retry có thể claim lại. Unique constraint vẫn bảo vệ trước hai transaction đồng thời.

Ví dụ ở tầng service với `TransactionalOperator`:

```java
Mono<PaymentReceipt> capture(CapturePaymentCommand command,
                             IdempotencyScope scope) {
    String hash = fingerprint(command);

    Mono<PaymentReceipt> work = repository.tryInsert(scope, command, hash)
        .flatMap(inserted -> {
            if (!inserted) {
                return repository.find(scope, command.idempotencyKey())
                    .flatMap(record -> replayOrReject(record, hash));
            }

            return paymentRepository.capture(command)
                .flatMap(receipt -> repository.markCompleted(
                    scope, command.idempotencyKey(), receipt)
                    .thenReturn(receipt));
        });

    return transactionalOperator.transactional(work);
}
```

Đoạn code giả định `tryInsert`, thao tác payment và `markCompleted` dùng cùng transaction manager/database. Cách triển khai `tryInsert` nên dùng atomic insert-if-absent thay vì SELECT rồi INSERT. Nếu database đánh dấu transaction rollback-only khi gặp unique violation, hãy dùng câu lệnh conflict-safe như `INSERT ... ON CONFLICT DO NOTHING` để xử lý duplicate mà không tiếp tục trong transaction lỗi.

Không giữ một transaction database mở trong thời gian dài để gọi dịch vụ bên ngoài hoặc chờ thiết bị phản hồi. Với side effect ở hệ thống khác, cần mô hình xử lý riêng.

## 12. Side effect bên ngoài: dùng outbox và idempotency ở downstream

Một transaction local không thể tự atomically commit database và một API thanh toán bên ngoài nếu không có distributed transaction phù hợp. Tình huống nguy hiểm:

1. Server ghi `IN_PROGRESS`.
2. Server gọi cổng thanh toán; cổng đã trừ tiền.
3. Kết nối hoặc process bị lỗi trước khi server lưu `COMPLETED`.
4. Retry đến và server không biết cổng đã thực hiện hay chưa.

Để xử lý, có thể dùng transactional outbox:

```text
Database transaction:
  - claim idempotency key
  - ghi business command / pending payment
  - ghi outbox event có eventId ổn định
  - commit

Outbox publisher:
  - gửi event đến downstream với cùng idempotency key
  - retry khi chưa xác định kết quả

Downstream:
  - deduplicate theo key
  - trả lại kết quả đã lưu khi nhận lại cùng key

Consumer:
  - lưu kết quả và cập nhật state COMPLETED
```

Nếu downstream hỗ trợ idempotency key, truyền cùng key qua ranh giới service. Nếu downstream không hỗ trợ deduplication và side effect không thể đối soát, không thể đảm bảo không có xử lý lặp chỉ bằng một bảng local; cần thiết kế reconciliation, query trạng thái hoặc quy trình bù trừ.

Với event consumer, inbox pattern cũng hữu ích: lưu event ID đã xử lý cùng thay đổi nghiệp vụ trong một transaction để cùng event được giao lại không tạo side effect lần nữa.

## 13. Fire-and-forget và giới hạn của acknowledgement

`RSocketRequester.send()` thực hiện fire-and-forget và trả `Mono<Void>`. Khi publisher complete, đó là tín hiệu hoàn tất thao tác gửi ở phía client theo runtime, không phải xác nhận server đã xử lý command.

Nếu dùng FNF cho lệnh có tác dụng phụ:

- Gửi idempotency key cùng command để server deduplicate.
- Server ghi nhận command bền vững trước khi coi đã tiếp nhận.
- Client không suy luận trạng thái nghiệp vụ từ `send()` complete.
- Nếu cần biết kết quả, dùng request-response hoặc một route/status stream riêng để tra cứu bằng key.

Ví dụ API tách lệnh gửi và truy vấn trạng thái:

```java
Mono<Void> submit(CapturePaymentCommand command) {
    return requester.route("payments.submit")
        .data(command)
        .send();
}

Mono<PaymentStatus> status(UUID idempotencyKey) {
    return requester.route("payments.status")
        .data(new PaymentStatusQuery(idempotencyKey))
        .retrieveMono(PaymentStatus.class);
}
```

Client có thể gửi lệnh, sau đó truy vấn trạng thái theo cùng key. Server cần kiểm tra quyền truy cập trước khi trả trạng thái; idempotency key không phải secret hoặc authorization token.

## 14. Request-response timeout và retry cùng key

Với request-response, client thường có response hoặc lỗi. Nhưng nếu timeout xảy ra sau khi server đã commit side effect và response bị mất, client vẫn không biết kết quả. Cách retry an toàn là giữ nguyên key:

```java
Mono<PaymentReceipt> captureWithRetry(CapturePaymentCommand command) {
    return requester
        .route("payments.capture")
        .data(command) // command giữ nguyên idempotencyKey
        .retrieveMono(PaymentReceipt.class)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(300)));
}
```

Không tạo command/key mới bên trong retry function. Nếu retry tạo key mới, server coi mỗi attempt là một lệnh khác và có thể trừ tiền nhiều lần.

Chính sách retry cần giới hạn số lần, backoff và jitter. Không retry lỗi validation hoặc authorization như thể đó là lỗi mạng. Nếu lỗi trả về là `IN_PROGRESS`, client có thể chờ và truy vấn trạng thái theo cùng key thay vì gửi một command mới.

## 15. Idempotency trong request-stream và request-channel

Nếu stream hoặc channel mang nhiều command có tác dụng phụ, mỗi command logic cần một key riêng. Stream ID chỉ định danh interaction; nó không thay thế key cho từng phần tử nghiệp vụ.

Ví dụ channel gửi nhiều lệnh:

```java
Flux<CommandResult> results = requester
    .route("devices.{deviceId}.control", deviceId)
    .data(commands.map(command -> new DeviceCommand(
        command.idempotencyKey(),
        command.action(),
        command.parameters())))
    .retrieveFlux(CommandResult.class);
```

Mỗi `DeviceCommand` có key ổn định. Nếu channel bị reconnect hoặc caller gửi lại một phần lệnh, server có thể deduplicate từng command độc lập.

Với stream command cần giữ thứ tự, có thể dùng `concatMap` phía xử lý để tuần tự hóa các inner publisher. Idempotency giải quyết việc gửi trùng; `concatMap` giải quyết thứ tự xử lý trong pipeline. Hai cơ chế bổ sung cho nhau và không thay thế nhau.

## 16. Xử lý request trùng đang IN_PROGRESS

Hai request cùng key có thể đến gần như đồng thời. Request thắng claim bắt đầu xử lý; request còn lại thấy record `IN_PROGRESS`. Có một số chính sách:

| Chính sách | Khi phù hợp | Đánh đổi |
|---|---|---|
| Chờ kết quả đầu tiên | Tác vụ ngắn và server có cơ chế thông báo kết quả. | Request trùng giữ tài nguyên lâu hơn. |
| Trả trạng thái `IN_PROGRESS` | Caller có thể poll hoặc subscribe trạng thái. | Caller cần thêm bước truy vấn. |
| Trả lỗi retryable | Client có thể retry sau `Retry-After` hoặc backoff. | Phải phân biệt lỗi tạm thời với lỗi cuối cùng. |
| Từ chối conflict | API không cho phép hai request cùng key chạy đồng thời. | Caller cần hiểu semantics của lỗi. |

Không trả một receipt giả định thành công khi record vẫn `IN_PROGRESS`. Cũng không xóa record chỉ vì request thứ hai không muốn chờ; request đầu vẫn có thể đang thực hiện side effect.

Nếu dùng lease/lock cho worker xử lý, cần có owner token hoặc fencing/version để worker cũ không ghi đè kết quả của worker mới sau khi lease hết hạn. Lease hết hạn không chứng minh worker cũ đã dừng thực thi.

## 17. Xử lý lỗi và quyết định có cho retry hay không

Không phải lỗi nào cũng có cùng semantics:

- **Validation failure:** request không hợp lệ; có thể lưu kết quả thất bại cuối cùng cho key hoặc từ chối trước khi claim, theo contract.
- **Authorization failure:** không được phép thực hiện; không cho retry cùng credential như thể lỗi tạm thời.
- **Business rejection:** ví dụ tài khoản không đủ số dư; quyết định có lưu kết quả cuối cùng hay cho phép thử lại sau khi trạng thái thay đổi.
- **Transient infrastructure failure:** database timeout hoặc downstream unavailable; cần xác định side effect đã xảy ra chưa trước khi đánh dấu retryable.
- **Unknown outcome:** timeout sau khi gọi external provider; không tự xóa key và chạy lại từ đầu. Đối soát với provider hoặc retry cùng key tại provider.

Việc có lưu failure hay không là một phần của hợp đồng API. Nếu một key đã nhận kết quả cuối cùng `INSUFFICIENT_FUNDS`, gửi lại cùng key sau khi nạp thêm tiền có thể vẫn trả kết quả cũ. Nếu người dùng muốn tạo một ý định thanh toán mới sau thay đổi nghiệp vụ, cần một key mới.

## 18. Thời hạn lưu key (retention window)

Idempotency record không nhất thiết phải lưu vĩnh viễn, nhưng không được xóa trước khi mọi retry hợp lệ có thể xảy ra đã kết thúc.

Retention nên dài hơn hoặc bằng:

- Khoảng thời gian client có thể retry tự động.
- Thời gian client offline rồi gửi lại command từ durable outbox.
- Cửa sổ replay/re-delivery của broker hoặc hệ thống event liên quan.
- Khoảng thời gian vận hành cho phép người dùng retry thủ công.

Ví dụ, nếu client có thể retry trong 24 giờ và offline queue giữ lệnh tối đa 7 ngày, retention của server phải bao phủ ít nhất cửa sổ 7 ngày cộng khoảng đệm phù hợp. Con số cụ thể cần theo SLA và chính sách dữ liệu của hệ thống.

Nếu xóa record quá sớm, một retry muộn sẽ bị coi là command mới và side effect có thể lặp. Với giao dịch tài chính hoặc thao tác không thể đảo ngược, có thể cần lưu tombstone/key hash lâu hơn response đầy đủ để ngăn key cũ được tái sử dụng.

Cleanup phải an toàn khi có request đang xử lý. Không xóa `IN_PROGRESS` chỉ dựa trên tuổi record mà không có lease, owner/fencing và quy trình recovery.

## 19. Nhiều instance và tính nhất quán

Trong production, cùng một key có thể đến các instance khác nhau do load balancer, reconnect hoặc retry. Vì vậy, việc deduplicate phải dựa trên kho lưu trữ dùng chung và atomic uniqueness:

```text
RSocket connection A -> Instance 1 --\
                                      +--> shared idempotency store
RSocket connection B -> Instance 2 --/       unique(scope, operation, key)
```

Không dùng cache local làm nguồn sự thật duy nhất. Cache có thể hỗ trợ đọc nhanh, nhưng quyết định claim phải được bảo vệ bởi database/coordination store có atomic write.

Nếu dùng Redis, cần chọn primitive atomic phù hợp, thiết lập TTL có chủ đích và hiểu failover/persistence. Nếu dùng database quan hệ, unique constraint cùng transaction thường là nền tảng dễ kiểm tra. Dù dùng công nghệ nào, mọi instance phải thống nhất canonical scope và fingerprint algorithm.

## 20. Bảo mật và quyền riêng tư

Idempotency key là mã định danh, không phải credential. Người biết key không nên tự động có quyền xem receipt hoặc truy vấn trạng thái command.

Các nguyên tắc:

1. Xác thực caller độc lập với idempotency key.
2. Kiểm tra caller có quyền trên tenant/resource của record trước khi replay response.
3. Scope key theo tenant và operation để giảm va chạm giữa các miền dữ liệu.
4. Không đưa dữ liệu cá nhân hoặc bí mật vào key; dùng giá trị opaque.
5. Hạn chế lưu toàn bộ request/response nếu chứa dữ liệu nhạy cảm; có thể lưu response tối thiểu hoặc reference tới kết quả.
6. Bảo vệ kho idempotency bằng access control, encryption và retention policy phù hợp.
7. Log key ở dạng đã che hoặc hash nếu cần correlation; tránh ghi payload thanh toán/secret.

## 21. Quan sát và vận hành

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `idempotency.claim.created` | Số key mới được claim thành công. |
| `idempotency.replay.hit` | Số request trùng được trả kết quả cũ. |
| `idempotency.in_progress` | Số request trùng gặp command đang xử lý. |
| `idempotency.payload_conflict` | Số lần cùng key nhưng fingerprint khác. |
| `idempotency.processing.failure` | Số command kết thúc bằng lỗi. |
| `idempotency.record.expired` | Số record/tombstone hết retention. |

Theo dõi thêm thời gian xử lý, số record `IN_PROGRESS` quá lâu, tuổi record cũ nhất, tỷ lệ retry và lỗi downstream. Nếu conflict tăng đột biến, có thể client đang tạo key sai hoặc vô tình tái sử dụng key giữa các lệnh.

Log nên có operation, scope đã được phép ghi, correlation ID và trạng thái xử lý. Không log raw authentication metadata, dữ liệu thanh toán hoặc toàn bộ request chỉ để điều tra retry.

## 22. Kiểm thử idempotency và race condition

Một kiểm thử tốt cần xác minh cả kết quả trả về và số lần tác dụng phụ thực sự xảy ra.

Các kịch bản quan trọng:

1. Gửi một command với key mới; xác minh side effect xảy ra đúng một lần và record chuyển `COMPLETED`.
2. Gửi lại cùng key, cùng payload; xác minh trả cùng receipt và side effect không chạy lại.
3. Gửi cùng key nhưng payload khác; xác minh nhận conflict và không có side effect thứ hai.
4. Gửi hai request cùng key đồng thời đến hai connection; xác minh chỉ một request claim thành công.
5. Gửi request trùng khi record `IN_PROGRESS`; xác minh đúng chính sách wait/status/retry.
6. Mô phỏng timeout sau khi server commit nhưng trước khi client nhận response; retry cùng key và xác minh receipt cũ được trả lại.
7. Mô phỏng process crash trước/sau commit để xác minh transaction và recovery.
8. Kiểm tra retention: retry trong cửa sổ được bảo vệ, key hết hạn được xử lý theo policy đã công bố.
9. Chạy nhiều instance để xác minh shared store và unique constraint thực sự phối hợp.
10. Kiểm tra caller khác tenant hoặc không có quyền không thể dùng key để đọc kết quả của người khác.

Ví dụ kiểm tra ở tầng service:

```java
StepVerifier.create(paymentService.capture(scope, command))
    .expectNextMatches(receipt -> receipt.paymentId() != null)
    .verifyComplete();

StepVerifier.create(paymentService.capture(scope, command))
    .expectNextMatches(receipt -> receipt.paymentId() != null)
    .verifyComplete();

verify(paymentGateway, times(1)).capture(any());
```

Test gọi service hai lần với cùng scope, key và fingerprint; gateway chỉ được gọi một lần. Cần bổ sung test song song dùng `Mono.when(...)` hoặc nhiều client connection để kiểm tra race condition ở tầng repository/database, không chỉ mock repository.

## 23. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Sinh key mới trong mỗi lần retry | Server coi retry là lệnh mới và lặp side effect. | Tạo key một lần cho logical command và giữ nguyên. |
| Dùng stream ID làm idempotency key | Stream ID chỉ có ý nghĩa trong một connection và interaction. | Dùng key nghiệp vụ độc lập, ổn định qua connection. |
| Dùng hash payload làm key | Hai ý định hợp lệ có payload giống nhau bị gộp. | Tách key do client tạo khỏi request fingerprint. |
| Chỉ SELECT rồi mới INSERT | Hai request đồng thời có thể cùng thấy key chưa tồn tại. | Dùng unique constraint/atomic insert-if-absent. |
| Chỉ lưu key trong RAM của một node | Request tới node khác hoặc process restart không được deduplicate. | Dùng shared durable store. |
| Trả kết quả cũ dù fingerprint khác | Caller có thể hiểu nhầm command mới đã được xử lý. | Từ chối key conflict. |
| Xóa record ngay sau khi xử lý | Retry muộn có thể lặp tác dụng phụ. | Chọn retention theo retry/replay window. |
| Đánh dấu COMPLETED trước khi side effect commit | Client nhận kết quả thành công dù tác dụng phụ chưa bền vững. | Ghi kết quả và side effect trong cùng transaction hoặc dùng workflow/outbox. |
| Giữ IN_PROGRESS vô thời hạn | Request trùng không thể tiến triển sau crash. | Có lease, timeout, owner/fencing và recovery rõ ràng. |
| Nghĩ FNF `send()` complete là server đã xử lý | Không có business acknowledgement trong fire-and-forget. | Dùng request-response hoặc status query/event riêng. |
| Dùng key như token truy cập | Người biết key có thể bị cấp quyền ngoài ý muốn. | Authorization độc lập trước khi replay hoặc trả trạng thái. |
| Gọi external side effect rồi không đối soát khi timeout | Không biết provider đã thực hiện hay chưa. | Truyền key xuống provider, query trạng thái hoặc reconciliation. |

## 24. Quy trình thiết kế idempotency cho một command

Trước khi triển khai, hãy xác định rõ:

1. Command nào có tác dụng phụ và cần idempotency?
2. Ai tạo key, ở thời điểm nào và key có được lưu bền vững phía client không?
3. Scope uniqueness gồm tenant, actor và operation nào?
4. Trường nào tham gia request fingerprint?
5. Kho dữ liệu nào thực hiện atomic claim và lưu kết quả?
6. Tác dụng phụ có nằm trong cùng transaction không? Nếu không, downstream/outbox/inbox xử lý dedup thế nào?
7. Request trùng `IN_PROGRESS`, `COMPLETED`, `FAILED` và payload conflict nhận hành vi gì?
8. Retention bao phủ retry, offline queue và replay window trong bao lâu?
9. Client nhận receipt qua request-response hay truy vấn trạng thái sau fire-and-forget?
10. Có kiểm thử concurrent duplicate, timeout-after-commit và multi-instance chưa?

## Kết luận

Idempotency key giúp một lệnh có tác dụng phụ được nhận diện xuyên suốt các lần gửi lại. Client tạo key một lần cho logical command và giữ nguyên khi retry; server dùng scope, unique constraint và request fingerprint để claim nguyên tử, phát hiện payload conflict và trả lại kết quả đã lưu. Với tác dụng phụ cùng database, claim, thay đổi nghiệp vụ và receipt nên nằm trong một transaction. Với hệ thống bên ngoài, cần outbox/inbox, idempotency ở downstream hoặc reconciliation. Trong RSocket, timeout, reconnect và fire-and-forget đều có thể tạo trạng thái không chắc chắn; key ổn định cùng trạng thái bền vững giúp retry an toàn trong phạm vi retention đã định nghĩa.
