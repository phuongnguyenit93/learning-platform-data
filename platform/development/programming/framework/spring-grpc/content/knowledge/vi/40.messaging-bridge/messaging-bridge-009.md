# Idempotency của command

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao command gửi qua gRPC hoặc messaging có thể được xử lý nhiều lần.
- Phân biệt idempotency với retry, deduplication của message và exactly-once delivery.
- Thiết kế command ID/idempotency key có scope rõ ràng theo tenant và operation.
- Tạo request fingerprint để phát hiện trường hợp dùng lại key với payload khác.
- Dùng unique constraint và transaction để chỉ áp dụng một lần business effect trong database.
- Kết hợp command record, business mutation và transactional outbox trong cùng transaction.
- Xử lý request trùng đồng thời, command đang xử lý, lỗi tạm thời và lỗi nghiệp vụ cuối cùng.
- Thiết kế inbox/deduplication ở consumer khi broker có at-least-once delivery.
- Bảo vệ external side effect bằng downstream idempotency key hoặc saga.
- Chọn retention, quan sát và kiểm thử concurrency cho idempotency contract.

## 1. Vì sao command cần idempotency?

Trong **SPRING_GRPC**, client gửi command qua unary RPC hoặc streaming RPC để yêu cầu một hành động có side effect, ví dụ tạo đơn hàng, ghi nhận thanh toán, đặt chỗ hoặc cập nhật trạng thái. Service có thể commit transaction thành công nhưng response bị mất do network timeout, client cancel hoặc connection đóng trước khi nhận kết quả.

Client không thể biết chắc command chưa chạy hay đã chạy thành công. Nếu gửi lại command như một request mới, service có thể tạo đơn hàng thứ hai, trừ tiền hai lần hoặc phát hai sự kiện giống nhau.

**Idempotency của command** bảo đảm nhiều lần gửi cùng một command logic tạo ra tối đa một business effect, đồng thời các lần gửi lại có thể nhận lại kết quả đã được ghi nhận. Một command có thể được truyền qua gRPC, ghi vào database, phát qua outbox tới broker và được consumer xử lý. Mỗi ranh giới cần một định danh ổn định và một cơ chế deduplication phù hợp.

Ví dụ: client gửi PlaceOrder với command ID C-123. Server tạo order O-900 và commit, nhưng response bị timeout. Client gửi lại C-123 với cùng nội dung. Server nhận ra command đã hoàn tất và trả lại kết quả của O-900; không tạo order mới.

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant G as gRPC Service
    participant DB as Database
    participant O as Outbox Relay
    participant B as Broker
    C->>G: Command ID C-123
    G->>DB: Insert command key + update order + outbox
    DB-->>G: Commit
    G--xC: Response bị mất
    C->>G: Retry C-123 cùng payload
    G->>DB: Lookup command key
    DB-->>G: Completed + stored result
    G-->>C: Replay kết quả cũ
    O->>B: Publish event có event ID ổn định
~~~

Idempotency đặc biệt quan trọng khi hệ thống dùng retry, load balancer, broker redelivery hoặc client reconnect. Nó là một phần của contract command, không chỉ là một mẹo xử lý exception.

## 2. Idempotency không đồng nghĩa exactly-once delivery

Cần phân biệt các khái niệm:

| Khái niệm | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| Retry | Gửi lại khi chưa nhận được kết quả hoặc gặp lỗi có thể phục hồi | Có thể tạo request trùng |
| Idempotency | Lặp lại cùng operation không tạo thêm business effect | Cần key, storage và quy tắc replay |
| Message deduplication | Nhận diện message đã được consumer xử lý | Scope thường là consumer/subscription |
| At-least-once delivery | Message được giao ít nhất một lần, có thể nhiều lần | Consumer phải chịu được duplicate |
| Exactly-once delivery | Hệ thống bảo đảm một lần giao theo phạm vi cụ thể | Không tự bảo đảm side effect end-to-end qua nhiều hệ thống |

Trong messaging bridge, broker thường ưu tiên at-least-once delivery để không mất message. Producer có thể publish thành công nhưng chết trước khi ghi nhận trạng thái published; relay sẽ publish lại. Consumer cũng có thể commit business transaction rồi mất acknowledgement, khiến broker redeliver.

Vì vậy, mục tiêu thực tế là **effectively-once business processing trong một phạm vi transaction được kiểm soát**: dùng stable command/event ID, unique constraint và transaction để side effect chỉ được commit một lần. Không tuyên bố toàn bộ chuỗi gRPC → database → broker → consumer có exactly-once semantics nếu các hệ thống không cùng một transaction coordinator.

## 3. Command ID và idempotency key

Mỗi command cần một định danh ổn định xuyên suốt các lần retry. Có thể dùng command ID trong protobuf contract hoặc metadata key theo API convention. Với command nghiệp vụ, field rõ ràng trong request thường dễ kiểm tra, versioning và log hơn.

Ví dụ contract:

~~~proto
message PlaceOrderCommand {
  string command_id = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
  string currency = 4;
}

message PlaceOrderResult {
  string command_id = 1;
  string order_id = 2;
  string outcome = 3;
}

service OrderCommandService {
  rpc PlaceOrder(PlaceOrderCommand) returns (PlaceOrderResult);
}
~~~

Client tạo command ID trước lần gửi đầu tiên và giữ nguyên ID qua mọi retry của cùng operation. Không sinh UUID mới trong mỗi lần gọi retry, vì server sẽ coi mỗi UUID là một command mới.

Command ID không phải identity của caller. Server phải lấy tenant/client identity từ authentication context đã xác thực; không tin tenant ID tùy ý trong request để xác định scope deduplication.

Một key nên được scope theo ít nhất:

- Tenant hoặc owner đã xác thực.
- Operation hoặc command type.
- Command ID/idempotency key.

Ví dụ unique key là (tenant_id, command_type, command_id). Điều này tránh collision giữa hai tenant và tránh vô tình dùng một key của operation PlaceOrder cho operation CancelOrder.

Không dùng access token làm idempotency key. Token có thể rotate, chứa thông tin nhạy cảm và không biểu diễn một business operation ổn định.

## 4. Cùng key phải đi cùng cùng một request

Một lỗi nguy hiểm là client gửi command A với key K, sau đó tái sử dụng K cho command B. Nếu server chỉ kiểm tra key tồn tại rồi replay kết quả cũ, caller có thể nhận response sai hoặc che giấu lỗi tích hợp.

Khi nhận command, server nên tính **request fingerprint** từ biểu diễn canonical của các field nghiệp vụ. Lưu fingerprint cùng idempotency record. Khi key đã tồn tại:

- Cùng fingerprint: đây là retry của cùng command; replay kết quả hoặc trả trạng thái đang xử lý.
- Khác fingerprint: key bị tái sử dụng sai; từ chối rõ ràng.
- Không xác định được fingerprint: không xử lý theo kiểu đoán; báo lỗi contract.

Fingerprint nên dùng SHA-256 trên canonical payload đã chuẩn hóa. Chọn rõ field nào tham gia fingerprint: command type, resource ID, amount, currency, line items và các option làm thay đổi side effect. Không đưa transport metadata như trace ID, deadline hoặc retry count vào fingerprint.

Không nên mặc định hash trực tiếp protobuf bytes nếu serialization có thể thay đổi do schema evolution, field presence hoặc canonicalization. Với cùng logical command, fingerprint phải ổn định qua phiên bản client được hỗ trợ. Có thể tạo canonical DTO/encoding có version và hash biểu diễn đó.

Ví dụ:

~~~java
byte[] fingerprint = sha256(
        canonicalCommandEncoder.encode(command));
~~~

Không lưu payload nhạy cảm trong log chỉ để debug fingerprint. Có thể lưu hash và các field audit đã redacted.

## 5. Lưu idempotency record bằng unique constraint

Idempotency cần storage bền vững. In-memory map chỉ có hiệu lực trong một process; restart hoặc request được route sang replica khác sẽ quên lịch sử.

Một bảng tối thiểu có thể là:

~~~sql
CREATE TABLE command_deduplication (
    tenant_id       VARCHAR(100) NOT NULL,
    command_type    VARCHAR(120) NOT NULL,
    command_id      VARCHAR(120) NOT NULL,
    request_hash    CHAR(64) NOT NULL,
    state           VARCHAR(24) NOT NULL,
    result_payload  BYTEA,
    result_version  INTEGER,
    created_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    expires_at      TIMESTAMP,
    PRIMARY KEY (tenant_id, command_type, command_id)
);
~~~

Unique constraint là hàng rào cuối cùng trước race condition. Không dùng pattern “SELECT trước, nếu không có thì INSERT” như cơ chế duy nhất: hai transaction đồng thời có thể cùng SELECT không thấy record rồi cùng thực thi side effect. Unique key buộc chỉ một transaction thắng quyền tạo record.

Các cột quan trọng:

- request_hash: phát hiện key bị tái sử dụng với payload khác.
- state: trạng thái command theo contract.
- result_payload/result_version: kết quả có thể replay.
- created_at/completed_at: audit và vận hành.
- expires_at: thời điểm record có thể được dọn theo retention policy.

Nếu result lớn, không nhất thiết lưu toàn bộ protobuf response. Có thể lưu resource ID, operation ID hoặc kết quả tối thiểu đủ để dựng response ổn định. Tuy nhiên, replay phải có semantics rõ: cùng command trả cùng outcome, không đọc trạng thái mới rồi vô tình trả một kết quả khác với lần đầu nếu contract yêu cầu response bất biến.

## 6. Xử lý command đồng bộ trong một database transaction

Với command mà business effect nằm trong cùng database, cách đơn giản và mạnh là thực hiện các bước trong một transaction:

1. Tạo idempotency record với unique key và request fingerprint.
2. Nếu key đã tồn tại, xác minh fingerprint và đọc kết quả cũ.
3. Áp dụng business mutation.
4. Tạo outbox event nếu cần phát message.
5. Lưu response/result vào idempotency record và chuyển state thành COMPLETED.
6. Commit tất cả cùng nhau.

Nếu transaction rollback, record idempotency và business mutation cũng rollback. Client có thể retry cùng key; lần retry sau có thể trở thành transaction thắng.

Với PostgreSQL, có thể dùng INSERT ... ON CONFLICT DO NOTHING để tranh quyền tạo record mà không làm transaction hiện tại rơi vào trạng thái lỗi constraint:

~~~sql
INSERT INTO command_deduplication (
    tenant_id, command_type, command_id, request_hash,
    state, created_at
)
VALUES (
    :tenantId, :commandType, :commandId, :requestHash,
    'PROCESSING', CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, command_type, command_id)
DO NOTHING
RETURNING command_id;
~~~

Nếu câu lệnh trả về một dòng, transaction hiện tại đã tạo record và có quyền thực hiện command. Nếu không trả dòng nào, đọc record hiện có, so sánh request_hash và xử lý theo state. Với isolation level và database khác, cần kiểm tra semantics của unique conflict và visibility; không dựa vào hành vi PostgreSQL cho mọi hệ quản trị.

Ví dụ service Spring:

~~~java
@Transactional
public PlaceOrderResult execute(
        String authenticatedTenantId,
        PlaceOrderCommand command) {

    String commandId = requireCommandId(command);
    byte[] requestHash = fingerprint(command);

    boolean claimed = dedupRepository.insertIfAbsent(
            authenticatedTenantId,
            "PlaceOrder",
            commandId,
            requestHash);

    if (!claimed) {
        CommandRecord existing = dedupRepository.findRequired(
                authenticatedTenantId,
                "PlaceOrder",
                commandId);

        if (!MessageDigest.isEqual(
                existing.requestHash(), requestHash)) {
            throw new IdempotencyKeyConflictException();
        }

        if (existing.isCompleted()) {
            return resultCodec.decode(existing.resultPayload());
        }

        throw new CommandInProgressException(commandId);
    }

    PlaceOrderResult result = orderDomainService.place(command);

    outboxRepository.append(
            eventFactory.orderPlaced(commandId, result));

    dedupRepository.markCompleted(
            authenticatedTenantId,
            "PlaceOrder",
            commandId,
            resultCodec.encode(result),
            resultCodec.version());

    return result;
}
~~~

Ví dụ giả định repository thực thi insert-if-absent theo unique constraint và mọi thao tác cùng tham gia một transaction. Không gọi broker, HTTP service hoặc payment provider trực tiếp bên trong transaction này; network call có thể kéo dài lock và không rollback được side effect bên ngoài.

## 7. Xử lý duplicate đồng thời

Hai request cùng key có thể tới hai replica gần như cùng lúc. Cả hai đều tính cùng fingerprint và cùng cố insert. Unique constraint chỉ cho một transaction tạo record.

Với thiết kế một transaction đồng bộ:

- Transaction thắng insert thực hiện business mutation, outbox và lưu result.
- Transaction còn lại chờ unique conflict được giải quyết.
- Sau khi transaction thắng commit, transaction còn lại đọc record COMPLETED và replay result.
- Nếu transaction thắng rollback, transaction còn lại có thể insert thành công và thực hiện command.

Cách xử lý duplicate phụ thuộc database isolation và transaction timeout. Không giữ transaction mở trong lúc chờ một external service. Nếu command có thời gian xử lý dài, chuyển sang mô hình asynchronous accepted command thay vì giữ lock lâu.

Nếu duplicate nhận trạng thái PROCESSING trong một thiết kế claim được commit riêng, cần quy định rõ response: trả operation ID để client poll, trả status retryable, hoặc chờ trong giới hạn ngắn. Không tạo một side effect thứ hai chỉ vì command đang xử lý lâu.

## 8. Command bất đồng bộ: ACCEPTED, lease và recovery

Một số command tạo report, import dữ liệu hoặc điều phối workflow không nên xử lý hết trong gRPC request. Server có thể commit một command record ở trạng thái ACCEPTED và outbox job trong một transaction, sau đó trả operation ID.

Luồng:

1. Ghi idempotency record với key, fingerprint và state ACCEPTED.
2. Ghi command/job message vào outbox cùng transaction.
3. Commit và trả cùng operation ID cho mọi retry cùng key.
4. Worker nhận job, claim bằng lease hoặc trạng thái có version.
5. Worker thực hiện business work và cập nhật COMPLETED/FAILED.
6. Client dùng operation ID để truy vấn trạng thái hoặc nhận event completion.

Lease cần owner, lease_until và fencing/version token để worker cũ không thể commit sau khi lease đã được worker khác lấy lại. Khi worker crash, lease hết hạn cho phép recovery. Mọi bước business vẫn cần idempotency vì worker có thể chạy lại sau crash.

Không giữ trạng thái PROCESSING vĩnh viễn. Cần timeout, lease expiry, retry limit và dead-letter/reconciliation policy. Nếu command thất bại tạm thời, có thể retry cùng operation; nếu thất bại nghiệp vụ cuối cùng, lưu FAILED/REJECTED theo contract để lần gửi lại cùng key không tự biến thành operation mới.

## 9. Kết hợp idempotency với Transactional Outbox

Một command thường cập nhật database rồi phát event sang broker. Nếu commit database xong nhưng publish thất bại, hệ thống có trạng thái nghiệp vụ mới nhưng downstream không biết. Nếu publish trước rồi transaction database rollback, downstream nhận event cho thay đổi chưa tồn tại.

Transactional Outbox giải quyết dual-write bằng cách ghi business mutation và event vào cùng database transaction:

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(120) PRIMARY KEY,
    aggregate_id    VARCHAR(120) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         BYTEA NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    published_at    TIMESTAMP
);
~~~

Trong transaction xử lý command, insert outbox event với event ID ổn định, ví dụ derived từ command ID và event type hoặc một ID được tạo và lưu cùng transaction. Relay đọc event chưa publish và gửi tới broker.

Relay có thể publish event thành công rồi crash trước khi đánh dấu published_at. Khi restart, nó publish lại. Đây là hành vi at-least-once có chủ đích; event ID phải giữ nguyên để consumer deduplicate.

Không đánh dấu outbox published trước khi broker xác nhận publish. Dù broker confirm, vẫn có cửa sổ crash giữa publish và cập nhật database; consumer vẫn cần inbox deduplication.

## 10. Consumer Inbox: chống xử lý event trùng

Idempotency của command ở gRPC ingress không tự bảo vệ consumer. Consumer cần deduplicate theo event ID hoặc message ID ổn định.

Mẫu Inbox:

~~~sql
CREATE TABLE processed_message (
    consumer_name   VARCHAR(120) NOT NULL,
    event_id        VARCHAR(120) NOT NULL,
    processed_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction của consumer:

1. Insert (consumer_name, event_id).
2. Nếu unique conflict, message đã được xử lý; không chạy business effect lần nữa.
3. Nếu insert thành công, áp dụng business mutation.
4. Commit inbox record và business mutation cùng nhau.
5. Chỉ acknowledge broker sau khi transaction commit.

Nếu consumer commit database rồi crash trước acknowledgement, broker redeliver; inbox record làm lần sau nhận diện duplicate. Nếu business mutation và inbox insert không cùng transaction, vẫn có cửa sổ tạo duplicate hoặc bỏ sót effect.

Nếu consumer gọi external service, inbox transaction không thể atomically bao trùm external side effect. Dùng downstream idempotency key, outbox tiếp theo hoặc saga/compensation.

## 11. Idempotency qua nhiều service và external side effect

Một command có thể đi qua nhiều bước: gRPC service → order database → payment provider → inventory service → broker. Idempotency ở service đầu không tự động làm mọi downstream step idempotent.

Propagate một operation/command ID ổn định tới downstream khi contract cho phép. Mỗi service cần scope và lưu idempotency state của riêng nó. Không dùng một global key tùy tiện cho mọi operation nếu các service có semantics khác nhau.

Với payment provider, dùng idempotency key mà provider hỗ trợ và giữ key ổn định qua retry. Nếu provider không hỗ trợ, cần lưu attempt, reconcile trạng thái giao dịch và thiết kế saga để xử lý kết quả không xác định.

Không giữ database transaction mở trong khi gọi payment/HTTP. Một quy trình an toàn thường là:

- Transaction A: tạo command/order ở trạng thái PENDING và ghi outbox.
- Worker: gọi payment với idempotency key.
- Transaction B: ghi kết quả payment và chuyển trạng thái.
- Nếu thất bại hoặc timeout không rõ kết quả, query/reconcile provider trước khi gửi một charge mới.
- Phát event trạng thái mới qua outbox.

Đây là workflow nhiều transaction, không phải một transaction phân tán. Saga xác định các bước, retry, timeout và compensation; idempotency bảo vệ mỗi bước khỏi chạy lặp.

## 12. Kết quả duplicate và status gRPC

Contract phải định nghĩa server trả gì khi nhận lại cùng command:

| Tình huống | Hành vi gợi ý |
| --- | --- |
| Key mới, payload hợp lệ | Thực hiện command và lưu kết quả |
| Key cũ, fingerprint giống, COMPLETED | Replay kết quả đã lưu |
| Key cũ, fingerprint khác | Từ chối key conflict |
| Key cũ, command đang xử lý | Trả operation ID/in-progress hoặc status retryable |
| Key cũ, FAILED nghiệp vụ cuối cùng | Replay outcome thất bại đã lưu |
| Lỗi hạ tầng tạm thời trước commit | Rollback để retry cùng key có thể thực hiện lại |

Có thể ánh xạ key conflict thành ALREADY_EXISTS hoặc INVALID_ARGUMENT theo API contract. ALREADY_EXISTS diễn đạt xung đột với command đã được tạo; INVALID_ARGUMENT diễn đạt request dùng key sai. Chọn một status nhất quán và có reason code ổn định.

Với command đang xử lý, ABORTED hoặc UNAVAILABLE có thể phù hợp nếu client được phép retry sau delay; nhưng nếu API có operation resource, trả operation ID thường rõ ràng hơn. Không trả RESOURCE_EXHAUSTED chỉ vì command đang xử lý nếu quota chưa bị vượt.

Không expose trạng thái nội bộ, SQL error hoặc fingerprint trong status description. Dùng status detail có schema rõ nếu client cần retry delay hoặc operation reference.

## 13. Retention và bảo vệ idempotency store

Idempotency record cần tồn tại lâu hơn cửa sổ retry/replay có thể xảy ra. Nếu xóa record quá sớm, một retry muộn có thể thực thi command lần nữa.

Retention phụ thuộc loại operation:

- Payment/financial command có thể cần retention dài theo quy định và reconciliation.
- Tạo order hoặc booking cần retention ít nhất qua thời gian client có thể retry và xử lý dispute.
- Telemetry/ephemeral command có thể dùng retention ngắn hơn nếu contract cho phép.
- Async command cần giữ operation state đến khi hoàn tất và hết thời hạn tra cứu.

Cần index theo expires_at và dọn theo batch nhỏ để tránh lock lớn. Không xóa command còn PROCESSING hoặc operation chưa hoàn tất. Nếu cần archive, giữ tombstone key đủ lâu để ngăn command cũ được chạy lại.

Idempotency key có thể bị lạm dụng để tạo record vô hạn. Xác thực client trước khi tạo record, giới hạn chiều dài key, giới hạn số command mới theo client/tenant và áp retention. Không cho caller dùng key tùy ý làm database index dài hoặc cardinality không giới hạn.

## 14. Observability và audit

Theo dõi:

- Số command mới, duplicate replay và key conflict.
- Tỷ lệ command COMPLETED, FAILED, ACCEPTED và PROCESSING.
- Thời gian xử lý và thời gian chờ duplicate.
- Unique conflict theo command type.
- Outbox backlog, publish retry và age của event cũ nhất.
- Inbox duplicate count và consumer lag.
- Lease expiry, worker recovery và command stuck.
- Downstream idempotency conflict/reconciliation.

Dùng command ID trong trace/log theo chính sách bảo mật, nhưng không đưa mọi command ID thành metric label vì cardinality cao. Log tenant/client đã pseudonymize, command type, outcome và correlation ID; không log token hoặc toàn bộ payload nhạy cảm.

Alert khi command PROCESSING vượt maximum age, outbox backlog tăng, duplicate conflict bất thường hoặc consumer inbox rejection tăng. Duplicate replay tăng có thể là bình thường khi client retry; key conflict tăng thường chỉ ra bug client hoặc lạm dụng.

## 15. Kiểm thử idempotency và race condition

Test phải kiểm tra side effect, không chỉ status trả về:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Gửi command lần đầu | Một business effect và một result record |
| Gửi lại cùng key, cùng payload | Replay result; không tạo effect thứ hai |
| Cùng key, payload khác | Từ chối key conflict |
| Hai request cùng key đến đồng thời | Chỉ một transaction thực hiện side effect |
| Transaction rollback trước commit | Retry cùng key có thể thực hiện command |
| Commit thành công nhưng response bị mất | Retry trả kết quả đã lưu |
| Relay publish rồi crash trước mark published | Event có thể publish lại, consumer deduplicate |
| Consumer commit rồi crash trước ack | Redelivery không tạo business effect thứ hai |
| Worker async crash khi PROCESSING | Lease expiry và recovery an toàn |
| Downstream timeout không rõ kết quả | Reconcile bằng operation/idempotency key |
| Record hết retention | Behavior đúng với contract và replay window |

Dùng barrier/latch để gửi nhiều request đồng thời qua hai channel hoặc hai replica. Assert số row business, command record và outbox event đúng bằng một. Không dùng Thread.sleep để tạo race một cách ngẫu nhiên.

Kiểm thử rollback và crash window bằng cách chủ động ném exception ở các điểm trước/sau commit, trước/sau publish và trước/sau broker acknowledgement. Với consumer, xác minh inbox record và business mutation nằm trong cùng transaction.

Trong Spring integration test, gọi service qua gRPC generated stub thực tế, kiểm tra @Transactional proxy hoạt động, unique constraint được database thực thi và response replay có cùng business result. In-memory repository không thay thế được test concurrency của database thật.

## 16. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Sinh command ID mới mỗi lần retry | Server coi retry là command mới | Giữ nguyên key cho cùng logical operation |
| Dùng client-supplied tenant chưa xác thực | Có thể né quota hoặc truy cập record tenant khác | Scope bằng authenticated principal |
| Chỉ SELECT trước INSERT | Race tạo duplicate side effect | Unique constraint và atomic insert |
| Chỉ lưu key, không lưu fingerprint | Cùng key khác payload bị replay sai | So sánh canonical request hash |
| Lưu dedup record ngoài transaction business | Record và side effect lệch nhau | Commit cùng transaction |
| Publish broker trong DB transaction | Dual-write và transaction kéo dài | Transactional outbox |
| Không deduplicate consumer | Broker redelivery chạy business effect nhiều lần | Inbox unique key trong cùng transaction |
| Xóa record quá sớm | Retry muộn tạo side effect mới | Retention theo operation/replay window |
| Giữ DB transaction khi gọi external API | Lock lâu, không rollback side effect bên ngoài | Outbox/worker/saga |
| Coi timeout là chắc chắn thất bại | Retry có thể charge/create trùng | Reconcile và downstream idempotency |
| Bucket/map in-memory là nguồn sự thật | Restart hoặc replica khác xử lý duplicate | Durable database/shared store |

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Thêm command_id vào protobuf command và bảo đảm client giữ nguyên ID qua retry.
2. Lấy tenant/client scope từ authentication Context, không tin tenant field tự khai báo.
3. Tạo bảng command_deduplication với unique key và request fingerprint.
4. Viết transactional service: insert-if-absent, business mutation, outbox insert và lưu result trong cùng transaction.
5. Gửi hai request đồng thời cùng key; xác minh chỉ một order được tạo.
6. Gửi lại cùng key với payload khác; xác minh server từ chối key conflict.
7. Tạo outbox relay có thể publish lại và consumer inbox dedup trong cùng transaction với business effect.
8. Thử crash window sau commit, sau publish và trước acknowledgement; xác minh retry/redelivery không tạo effect trùng.
9. Với async command, triển khai ACCEPTED state, operation ID, lease expiry và worker recovery.
10. Viết Spring gRPC integration test qua generated stub và database thật.

### Câu hỏi tự kiểm tra

**1. Vì sao command cần idempotency?**  
Vì client có thể retry sau timeout dù server đã commit; cùng logical command không được tạo side effect lần thứ hai.

**2. Command ID phải được tạo khi nào?**  
Trước lần gửi đầu tiên và được giữ nguyên qua mọi retry của cùng operation.

**3. Vì sao cần request fingerprint?**  
Để phát hiện caller tái sử dụng key cho payload khác và tránh replay một kết quả không liên quan.

**4. Vì sao SELECT rồi INSERT không đủ?**  
Hai transaction có thể cùng không thấy record; unique constraint và atomic insert mới bảo vệ race.

**5. Vì sao command record và business mutation phải cùng transaction?**  
Để không có trạng thái dedup đã lưu nhưng business effect chưa commit, hoặc effect commit mà không có record ngăn retry.

**6. Outbox có bảo đảm broker chỉ nhận event một lần không?**  
Không. Relay có thể publish lại; event ID ổn định và consumer inbox giúp business effect không bị lặp.

**7. Consumer inbox phải commit cùng gì?**  
Cùng transaction với business mutation của consumer; chỉ acknowledge broker sau commit.

**8. Exactly-once delivery có đồng nghĩa exactly-once business effect end-to-end không?**  
Không. Các boundary database, broker và external API cần idempotency/transaction riêng; mục tiêu thực tế là effectively-once effect trong từng phạm vi được kiểm soát.

## Tổng kết

Idempotency của command bảo đảm retry hoặc duplicate delivery không tạo thêm business effect. Client giữ command ID ổn định; server scope key theo authenticated tenant/client và command type, lưu request fingerprint, dùng unique constraint và transaction để kết hợp dedup record, business mutation, stored result và outbox. Duplicate cùng payload được replay; cùng key khác payload bị từ chối; command dài có thể dùng ACCEPTED state, lease và operation status. Outbox relay vẫn có thể publish lặp, nên consumer cần inbox dedup cùng transaction với business effect. External side effect cần downstream idempotency key hoặc saga. Retention, concurrency tests và crash-window tests là phần bắt buộc của contract vận hành.

