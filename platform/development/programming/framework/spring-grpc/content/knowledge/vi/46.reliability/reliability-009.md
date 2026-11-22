# Redelivery và duplicate response

Redelivery xảy ra khi cùng một yêu cầu logic được gửi lại sau lỗi tạm thời, timeout, mất kết nối hoặc cơ chế retry ở client/proxy. Duplicate response là kết quả của cùng một thao tác logic được trả về hoặc xử lý nhiều lần do nhiều attempt được thực hiện. Trong gRPC, một RPC có thể đã được server xử lý và commit dữ liệu nhưng client vẫn không nhận được response. Client nhìn thấy lỗi transport hoặc deadline rồi gửi lại request; nếu server thực thi lại thao tác, side effect có thể bị nhân đôi.

Trong Spring gRPC, độ tin cậy cần được thiết kế xuyên suốt client retry, gRPC status/deadline, server handler, transaction và hệ thống downstream. Retry chỉ cải thiện khả năng hoàn tất khi lỗi có thể phục hồi; nó không tự bảo đảm một thao tác nghiệp vụ chỉ xảy ra một lần. Muốn xử lý redelivery an toàn, cần định danh ổn định cho thao tác, lưu kết quả idempotency nguyên tử với side effect và xác định cách client xử lý response lặp.

## 1. Vì sao một request có thể được gửi lại?

Một tình huống phổ biến:

```text
Client                    gRPC Server                 Database
  |                            |                          |
  |---- CreateOrder(key=K) --->|                          |
  |                            |---- INSERT order ------->|
  |                            |<--- COMMIT --------------|
  |          X response lost   |                          |
  |<---- UNAVAILABLE/timeout --|                          |
  |                            |                          |
  |---- retry same request --->|                          |
  |                            |---- INSERT order ------->|
  |                            |       duplicate order!    |
```

Server có thể đã commit trước khi connection bị reset hoặc response bị mất. Client không thể suy ra từ lỗi transport rằng server chưa thực hiện thao tác. Đây là ambiguous outcome: caller không biết operation chưa bắt đầu, đang chạy, đã commit hay đã commit nhưng response không tới nơi.

Redelivery có thể đến từ:

- Retry do application code tự thực hiện.
- Retry policy của gRPC channel khi nhận retryable status.
- Proxy, service mesh hoặc gateway có chính sách retry riêng.
- Message broker/job scheduler giao lại message khi worker không ACK đúng hạn.
- Người vận hành replay một request sau sự cố.
- Client reconnect và khôi phục stream bằng cách gửi lại command chưa xác nhận.

Nhiều tầng retry có thể nhân số attempt. Ví dụ client retry 3 lần và gateway retry 2 lần có thể tạo nhiều hơn một lần thực thi ở server. Cần lập bản đồ retry ownership và giới hạn tổng attempt trên toàn request path.

Không có bảo đảm exactly-once chỉ nhờ transport retry. Một client library có thể che các attempt nội bộ, nhưng không thể xóa sự mơ hồ khi server đã commit side effect mà response bị mất. Mục tiêu thực tế là effectively-once business effect: mọi lần gửi lại cùng logical operation đều hội tụ về một kết quả nghiệp vụ nhờ idempotency và deduplication bền vững.

## 2. Phân biệt RPC attempt và logical operation

Một logical operation có thể có nhiều RPC attempt. Mỗi attempt có thể có call ID/trace span riêng, nhưng tất cả phải dùng cùng idempotency key nếu chúng đại diện cho cùng một hành động:

| Khái niệm | Ý nghĩa | Vòng đời |
| --- | --- | --- |
| Logical operation ID | Định danh thao tác nghiệp vụ | Ổn định qua mọi retry/redelivery |
| Idempotency key | Khóa để server nhận ra request lặp | Ổn định cho cùng ý định thực hiện |
| RPC attempt ID | Định danh một lần gọi cụ thể | Mới cho mỗi attempt |
| Request/trace ID | Tương quan log và trace | Có thể mới mỗi attempt hoặc được truyền theo trace policy |

Không dùng một request ID ngẫu nhiên mới làm idempotency key ở mỗi retry. Khi đó server không nhận ra hai lần gọi là cùng một thao tác. Ngược lại, không dùng idempotency key làm trace ID; một logical operation có thể có nhiều attempt và nhiều span.

Idempotency key phải được tạo ở ranh giới bắt đầu thao tác và được giữ lại khi retry. Có thể đặt trong field Protobuf hoặc metadata. Với thao tác ghi dữ liệu, field trong request thường dễ gắn với contract nghiệp vụ và dễ lưu cùng command. Metadata phù hợp khi key là concern xuyên suốt nhiều method, nhưng server vẫn phải xác minh và lưu nó.

## 3. Retry của gRPC và giới hạn của nó

grpc-java có thể áp dụng retry policy từ service config khi channel/provider hỗ trợ. Một policy thường quy định:

- `maxAttempts`: tổng số attempt tối đa, bao gồm attempt đầu.
- `initialBackoff` và `maxBackoff`: khoảng chờ ban đầu và giới hạn backoff.
- `backoffMultiplier`: hệ số tăng khoảng chờ.
- `retryableStatusCodes`: các status cho phép thử lại.

Ví dụ service config minh họa:

```json
{
  "methodConfig": [{
    "name": [{
      "service": "acme.orders.v1.OrderService",
      "method": "GetOrder"
    }],
    "retryPolicy": {
      "maxAttempts": 4,
      "initialBackoff": "0.2s",
      "maxBackoff": "2s",
      "backoffMultiplier": 2,
      "retryableStatusCodes": ["UNAVAILABLE"]
    }
  }]
}
```

Đây là cấu hình minh họa; cách nạp service config phụ thuộc ManagedChannelBuilder, resolver và phiên bản grpc-java. Spring gRPC starter có thể cung cấp channel customizer hoặc cấu hình riêng. Xác minh cấu hình thực tế được channel sử dụng, không chỉ kiểm tra JSON đã tồn tại trong file.

Retry policy nên chỉ áp dụng cho method có semantics phù hợp. GetOrder thường có thể retry khi UNAVAILABLE. CreateOrder hoặc ChargeCard chỉ nên retry khi server hỗ trợ idempotency. Không đưa mọi status vào retryableStatusCodes: INVALID_ARGUMENT, UNAUTHENTICATED và PERMISSION_DENIED thường không tự hết sau một lần thử lại.

UNAVAILABLE thường chỉ ra lỗi tạm thời nhưng không chứng minh server chưa tạo side effect. Nếu server commit rồi connection hỏng trước response, retry UNAVAILABLE vẫn có thể chạy lại command. Status code quyết định có thử lại hay không; idempotency quyết định thử lại có an toàn hay không.

## 4. Retry, commitment và deadline

gRPC retry runtime có thể giữ request để thử lại trước khi call được commit theo quy tắc của implementation. Khi response headers đã được nhận hoặc dữ liệu vượt giới hạn retry buffer, call có thể được xem là committed và retry nội bộ không còn khả dụng. Chi tiết commitment/buffering phụ thuộc gRPC runtime và kiểu RPC; không dùng nó thay thế idempotency nghiệp vụ.

Deadline áp dụng cho toàn bộ logical RPC, không nên được đặt lại thành một ngân sách đầy đủ cho mỗi attempt. Backoff và các attempt trước tiêu thụ thời gian còn lại. Nếu mỗi tầng tự tạo deadline mới dài hơn, tổng thời gian end-to-end có thể vượt giới hạn caller.

Ví dụ client đặt deadline:

```java
OrderReply reply = orderStub
    .withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Deadline phải đủ cho số attempt và backoff dự kiến, nhưng vẫn nằm trong latency budget của API. Khi hết deadline, caller có thể nhận DEADLINE_EXCEEDED dù server đã commit thao tác. Vì vậy DEADLINE_EXCEEDED cũng là một ambiguous outcome đối với command có side effect.

Không retry vô hạn. Dùng maxAttempts hữu hạn, backoff có giới hạn, deadline end-to-end và retry budget để tránh retry storm khi dependency đang quá tải.

## 5. Chọn status và chính sách retry

Status phản ánh loại lỗi, nhưng không phải tất cả lỗi đều có semantics retry giống nhau:

| Status | Hướng xử lý thường gặp | Lưu ý |
| --- | --- | --- |
| UNAVAILABLE | Có thể retry với backoff | Kết quả attempt trước vẫn có thể chưa rõ |
| RESOURCE_EXHAUSTED | Chỉ retry nếu có tín hiệu phục hồi/thời gian chờ | Retry ngay có thể làm quá tải nặng hơn |
| ABORTED | Có thể chạy lại transaction ở cấp cao hơn | Thường cần khởi động lại toàn bộ transaction |
| DEADLINE_EXCEEDED | Chỉ retry khi còn ngân sách và operation idempotent | Server có thể đã hoàn tất |
| CANCELLED | Thường không tự retry khi caller chủ động hủy | Phân biệt cancellation do shutdown/transport |
| INVALID_ARGUMENT | Không retry | Request phải được sửa |
| UNAUTHENTICATED | Làm mới credential theo policy rồi mới thử | Không retry mù với credential cũ |
| PERMISSION_DENIED | Không retry | Cần thay đổi quyền hoặc request |
| FAILED_PRECONDITION | Thường không retry nguyên trạng | Cần sửa trạng thái hệ thống trước |

ABORTED có thể dùng khi transaction conflict và caller cần chạy lại một chuỗi thao tác. UNAVAILABLE có thể phù hợp cho lỗi tạm thời của dependency. Status mapping phải nhất quán giữa service và client; không dùng UNAVAILABLE để che mọi exception vì sẽ kích hoạt retry không cần thiết.

## 6. Idempotency key ở contract Protobuf

Với command tạo hoặc thay đổi dữ liệu, có thể đưa idempotency key vào request:

```proto
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}

message CreateOrderReply {
  string order_id = 1;
  string state = 2;
}
```

Client tạo key một lần cho ý định tạo đơn hàng và giữ nguyên key qua retry. Server cần xác định scope của key, ví dụ tenant + principal + service/method + key. Không dùng key toàn cục không scope vì hai caller khác nhau có thể vô tình va chạm hoặc dò kết quả của nhau.

Một idempotency record thường lưu:

| Field | Mục đích |
| --- | --- |
| scope | Tenant/principal/service-method |
| key | Idempotency key |
| request_hash | Phát hiện cùng key nhưng payload khác |
| state | IN_PROGRESS hoặc COMPLETED |
| response | Kết quả đã lưu để replay |
| created_at/expires_at | Quản lý retention |

Nếu cùng key nhưng payload khác, trả lỗi rõ ràng như INVALID_ARGUMENT hoặc FAILED_PRECONDITION theo contract. Không trả response cũ cho một request có nội dung khác; điều đó có thể khiến caller hiểu sai thao tác đã thực hiện.

## 7. Lưu deduplication record nguyên tử với side effect

Idempotency chỉ hiệu quả nếu server ghi nhận key và thực hiện side effect theo một cơ chế nhất quán. Với database quan hệ, có thể dùng unique constraint trên scope + key và lưu kết quả trong cùng transaction:

```sql
CREATE TABLE grpc_idempotency (
    tenant_id       VARCHAR(100) NOT NULL,
    principal_id    VARCHAR(200) NOT NULL,
    method_name     VARCHAR(300) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    state           VARCHAR(20) NOT NULL,
    response_bytes  BYTEA,
    created_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    PRIMARY KEY (
        tenant_id,
        principal_id,
        method_name,
        idempotency_key
    )
);
```

Ví dụ dùng kiểu BYTEA của PostgreSQL cho response bytes; với database khác, chọn kiểu binary tương ứng. Cần có index/constraint theo đúng scope và kế hoạch partition/retention khi bảng tăng lớn.

Transaction cần thực hiện theo nguyên tắc:

1. Claim key bằng insert có unique constraint.
2. Nếu key đã tồn tại, đọc record theo cùng scope.
3. So sánh request_hash; khác payload thì từ chối.
4. Nếu COMPLETED, trả lại response đã lưu.
5. Nếu key mới, thực hiện business mutation.
6. Lưu response và chuyển state thành COMPLETED.
7. Commit record và business mutation cùng transaction.

Unique constraint là hàng rào cuối cùng chống hai request đồng thời cùng claim một key. Cần xử lý unique-key conflict theo đúng isolation/transaction semantics của database. Không chỉ thực hiện SELECT rồi mới INSERT mà không có constraint, vì hai request có thể cùng thấy "chưa tồn tại" và cùng tạo side effect.

Ví dụ PostgreSQL: unique violation có thể làm transaction hiện tại ở trạng thái failed; không tiếp tục SELECT record trong chính transaction đó. Rollback transaction bị lỗi, sau đó đọc record đã commit bằng transaction mới và so sánh request fingerprint trước khi replay response.

## 8. Mẫu service xử lý idempotency trong Spring

Service có thể ủy quyền claim/replay cho một IdempotencyExecutor. Executor phải bảo đảm claim key, business mutation và response record cùng transaction:

```java
@GrpcService
final class OrderGrpcService extends OrderServiceGrpc.OrderServiceImplBase {
    private final IdempotencyExecutor idempotency;
    private final OrderApplicationService orders;

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderReply> observer) {
        try {
            RequestScope scope = RequestScope.from(
                AuthContext.currentPrincipal(),
                "acme.orders.v1.OrderService/CreateOrder");

            CreateOrderReply reply = idempotency.execute(
                scope,
                request.getIdempotencyKey(),
                RequestFingerprint.sha256(request),
                CreateOrderReply.parser(),
                () -> {
                    Order order = orders.create(
                        request.getCustomerId(),
                        request.getLinesList());
                    return CreateOrderReply.newBuilder()
                        .setOrderId(order.id())
                        .setState(order.state())
                        .build();
                });

            observer.onNext(reply);
            observer.onCompleted();
        } catch (IdempotencyKeyConflictException conflict) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("idempotency key reused with different request")
                .asRuntimeException());
        } catch (RuntimeException failure) {
            observer.onError(Status.INTERNAL
                .withDescription("create order failed")
                .asRuntimeException());
        }
    }
}
```

Đây là skeleton để minh họa điểm tích hợp; IdempotencyExecutor phải được triển khai với transaction, unique constraint, xử lý concurrent claim và lưu/replay response như mô tả. Không bắt mọi RuntimeException rồi luôn trả INTERNAL trong production: ánh xạ lỗi nghiệp vụ, database unavailable và transaction conflict sang status đúng contract.

Fingerprint nên được tạo từ biểu diễn request canonical, không dựa vào toString() không ổn định. Cân nhắc bỏ qua trường không ảnh hưởng semantics như trace metadata; không đưa credential vào hash. Scope phải lấy từ principal/tenant đã xác minh, không lấy tenant header tùy ý.

## 9. Xử lý request trùng đang IN_PROGRESS

Hai attempt có cùng idempotency key có thể đến gần như đồng thời. Request thứ hai thấy record IN_PROGRESS. Có một số chiến lược:

- Chờ request đầu hoàn tất rồi đọc/replay response.
- Trả status retryable có hướng dẫn backoff để client thử lại cùng key.
- Trả lỗi conflict nếu contract không cho phép chờ hoặc request không tương thích.

Chọn một chiến lược nhất quán. Nếu trả UNAVAILABLE/ABORTED cho request đang chạy, client có thể retry liên tục và tạo tải thêm; dùng backoff, deadline và giới hạn concurrency. Nếu chờ, giới hạn thời gian chờ và không giữ database lock lâu hơn cần thiết.

Record IN_PROGRESS cần xử lý crash. Nếu claim được commit riêng trước business transaction, server có thể chết và để record treo. Cần lease/owner token, timeout recovery hoặc transaction design bảo đảm record không tồn tại vĩnh viễn mà không có operation tương ứng.

Với database transaction ngắn, cách đơn giản là claim record và business mutation trong cùng transaction; request cạnh tranh sẽ bị unique constraint/lock chặn cho tới khi transaction đầu commit hoặc rollback. Với công việc dài, dùng state machine bền vững, lease và worker recovery thay vì giữ transaction mở trong thời gian xử lý dài.

## 10. External side effect và transactional outbox

Database transaction không thể nguyên tử bao trùm một HTTP call tới payment provider, gửi email hoặc publish message tới broker. Nếu server gọi external system rồi crash trước khi lưu idempotency response, retry có thể gọi external system lần nữa.

Mẫu phù hợp:

1. Trong một database transaction, claim idempotency key, ghi business state và tạo outbox event.
2. Commit transaction.
3. Worker đọc outbox và gửi event tới downstream.
4. Downstream nhận stable operation/event ID và deduplicate.
5. Worker đánh dấu event đã gửi; retry khi kết quả gửi chưa rõ.

Outbox bảo đảm business state và ý định gửi event được lưu nguyên tử. Nó không tự bảo đảm broker hoặc downstream chỉ nhận một lần; consumer/downstream vẫn cần dedupe theo event ID hoặc idempotency key.

Với payment provider, truyền idempotency key của logical payment operation nếu provider hỗ trợ. Không tạo key mới cho mỗi retry HTTP/gRPC. Lưu provider reference và trạng thái kết quả để đối soát trường hợp timeout nhưng payment đã được chấp nhận.

## 11. Duplicate response và cách client xử lý

gRPC retry nội bộ thường che các attempt bên dưới một logical call và chỉ đưa kết quả cuối của call tới application observer. Nhưng nếu application tự gọi lại RPC sau timeout, mỗi lần gọi là một RPC riêng; nhiều attempt có thể trả cùng response đã được server lưu. Nếu client xử lý mỗi response như một lệnh mới, UI, event handler hoặc downstream action có thể bị thực hiện hai lần.

Client cần phân biệt:

- Response replay của cùng logical operation: cùng operation/idempotency key, cùng kết quả.
- Response của operation khác: key khác, dù payload tương tự.
- RPC attempt: một lần truyền tải, không phải một business operation mới.

Khi nhận response lặp, client có thể cập nhật trạng thái theo operation ID một cách idempotent. Ví dụ, nếu UI đã đánh dấu order ord-123 là CREATED, response replay tiếp theo chỉ refresh trạng thái hiện có thay vì thêm một order card mới hoặc phát lại email.

Với consumer xử lý message/response event, dùng inbox/deduplication table keyed by event ID hoặc operation ID. Ghi nhận event đã xử lý cùng business side effect trong một transaction. Không dựa vào in-memory Set vì restart sẽ xóa dấu dedupe.

## 12. Streaming RPC và redelivery

Không áp dụng máy móc retry unary cho streaming. Một stream có thể đã gửi/nhận một phần message trước khi connection mất; mở stream mới và gửi lại toàn bộ có thể tạo duplicate hoặc bỏ sót message.

Muốn khôi phục stream, thiết kế application protocol có:

- Stable stream/session ID.
- Sequence number hoặc offset cho mỗi message.
- Acknowledgement/checkpoint xác nhận message đã được xử lý.
- Resume token/last acknowledged sequence để client tiếp tục từ vị trí an toàn.
- Idempotent processing ở server/consumer để xử lý message được gửi lại.

Ví dụ client gửi event có stream_id và sequence; server lưu unique key (stream_id, sequence) cùng kết quả xử lý. Khi reconnect, client gửi resume token để server biết điểm tiếp tục. Nếu response cuối bị mất, client có thể hỏi trạng thái sequence trước khi gửi lại.

Với bidi-streaming, request và response tiến triển độc lập. Cần quy định acknowledgement áp dụng cho request message nào, response message nào và khi nào server được phép xóa checkpoint. Không coi onNext phía client là xác nhận server đã commit message.

## 13. Retention và bảo mật idempotency record

Idempotency record phải tồn tại ít nhất trong khoảng thời gian client, proxy, broker hoặc operator có thể redeliver request. Nếu xóa record quá sớm, request cũ có thể tạo side effect lần nữa. Nếu giữ vô hạn, bảng dedupe tăng không giới hạn.

Định nghĩa:

- Retention theo loại operation và SLA retry/replay.
- TTL đủ dài hơn retry window tối đa và thời gian vận hành replay.
- Quy trình archive/partition/cleanup không xóa record IN_PROGRESS còn hiệu lực.
- Scope key theo tenant/principal/method để tránh replay chéo danh tính.
- Quyền đọc response cache; response có thể chứa dữ liệu nhạy cảm.
- Audit cho key conflict, replay hit và cleanup.

Không lưu raw idempotency key vào log nếu key có thể bị dùng để truy vấn response. Có thể log hash/fingerprint đã rút gọn, nhưng không dùng hash làm cơ chế xác thực. Khi cùng key nhưng request hash khác, phát cảnh báo hoặc audit event vì có thể là bug client hoặc hành vi lạm dụng.

## 14. Observability cho retry và deduplication

Metrics và logs nên phân biệt logical operation với RPC attempt:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| rpc_attempt_count | Số attempt truyền tải |
| retry_count | Số lần retry theo method/status |
| idempotency_replay_count | Số request được trả lại response đã lưu |
| idempotency_conflict_count | Cùng key nhưng request fingerprint khác |
| in_progress_duplicate_count | Request trùng khi operation còn chạy |
| deadline_exceeded_count | Call hết ngân sách thời gian |
| dedupe_store_latency | Thời gian claim/lookup record |
| outbox_lag | Độ trễ xử lý side effect downstream |

Gắn method, status, attempt number, operation ID đã che/hash và trace ID theo cardinality policy. Không dùng idempotency key hoặc user ID làm label metric không giới hạn vì tạo high cardinality. Không ghi request payload, token hoặc dữ liệu thanh toán vào log.

Retry tăng đột biến cùng UNAVAILABLE có thể là dấu hiệu dependency outage hoặc retry storm. Replay hit tăng có thể là bình thường sau network instability; conflict tăng thường chỉ ra client tái sử dụng key sai hoặc có lỗi integration.

## 15. Ma trận kiểm thử và bài tập vận dụng

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Request mới với key K | Side effect chạy một lần, response được lưu |
| Retry cùng key và cùng payload | Trả response đã lưu, không lặp side effect |
| Cùng key nhưng payload khác | Từ chối rõ ràng, không chạy side effect |
| Hai request cùng key đồng thời | Chỉ một request claim và thực hiện |
| Request đầu commit nhưng response bị mất | Retry nhận kết quả cũ, không tạo bản ghi thứ hai |
| Request đầu rollback | Retry có thể thực hiện operation theo transaction policy |
| Deadline hết sau commit | Client retry cùng key và nhận kết quả đã lưu |
| Audit/outbox publish lỗi | Business state và outbox vẫn nhất quán |
| Downstream nhận event lặp | Consumer dedupe theo event ID |
| Stream reconnect | Resume từ checkpoint, không xử lý lặp ngoài policy |
| Idempotency record hết TTL | Hành vi replay sau retention được định nghĩa |
| Nhiều tenant dùng cùng key | Scope ngăn replay chéo tenant |

**Bài tập:** OrderService.CreateOrder tạo order và phát OrderCreated event. Client đôi lúc nhận DEADLINE_EXCEEDED sau khi database commit. Gateway có retry UNAVAILABLE; worker broker cũng có thể redeliver outbox event.

1. Thêm idempotency key vào CreateOrderRequest và giữ key qua mọi retry.
2. Tạo unique constraint theo tenant, principal, method và key.
3. Lưu request fingerprint, state và response trong cùng transaction với order.
4. Kiểm thử hai request cùng key đến đồng thời và xác minh chỉ có một order.
5. Mô phỏng response bị mất sau commit; retry phải nhận lại order ID cũ.
6. Tạo outbox event cùng transaction và dùng event ID ổn định.
7. Dedupe event ở consumer để email/notification không phát hai lần.
8. Đặt retry policy chỉ cho status phù hợp, với maxAttempts/backoff/deadline hữu hạn.
9. Kiểm tra metrics replay/conflict/retry mà không log raw key hoặc payload.

**Câu hỏi tự kiểm tra:**

- Vì sao UNAVAILABLE không chứng minh server chưa commit?
- Logical operation ID khác RPC attempt ID thế nào?
- Retry policy của gRPC kiểm soát điều gì và không bảo đảm điều gì?
- Vì sao deadline áp dụng cho toàn logical call?
- Idempotency key cần scope theo những yếu tố nào?
- Vì sao unique constraint cần thiết khi hai request cùng key chạy đồng thời?
- Làm thế nào lưu business mutation và response replay nguyên tử?
- Vì sao external side effect cần outbox và downstream dedupe?
- Duplicate response từ application retry khác retry nội bộ của gRPC ra sao?
- Streaming cần sequence/checkpoint nào để resume an toàn?

**Ghi nhớ:** Redelivery là hệ quả bình thường của hệ thống phân tán; client không thể luôn biết server đã commit hay chưa khi response bị mất. Dùng retry có giới hạn và deadline end-to-end, giữ idempotency key ổn định qua attempt, deduplicate nguyên tử với side effect và replay cùng response. Với external event/stream, dùng outbox, event ID, sequence và checkpoint; thiết kế client để xử lý response lặp một cách idempotent.
