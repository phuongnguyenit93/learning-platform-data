# Idempotency khi client retry command

## 1. Vì sao command cần idempotency?

Trong **SPRING_GRPC**, nhiều unary RPC thực hiện side effect như tạo đơn hàng, ghi nhận thanh toán, chuyển tiền hoặc cập nhật trạng thái. Client có thể gửi request nhưng không nhận được response vì mạng bị ngắt, deadline hết hoặc process client khởi động lại. Trong khi đó, server có thể đã commit database thành công.

Client không thể luôn biết request đã được thực hiện hay chưa. Nếu gửi lại command như một request mới, server có thể tạo side effect lần hai. Đây là tình huống **ambiguous outcome**: kết quả phía server đã có thể commit, nhưng caller không nhận được xác nhận.

**Idempotency** cho phép nhiều lần gửi cùng một ý định nghiệp vụ tạo ra một kết quả hiệu lực duy nhất. Client gắn một idempotency key ổn định với command; server lưu key, nhận diện request trùng và trả lại kết quả đã ghi nhận thay vì thực hiện side effect lần nữa.

Idempotency không làm mạng trở thành exactly-once và không loại bỏ retry. Nó tạo ra cơ chế để xử lý at-least-once delivery an toàn ở tầng nghiệp vụ.

Bài tập trung vào thiết kế key và request fingerprint, lưu key bằng unique constraint, transaction nguyên tử với business update, xử lý request trùng đồng thời, replay kết quả, retry theo deadline, retention và kiểm thử tình huống commit thành công nhưng response bị mất.

## 2. Retry không chứng minh request trước đã thất bại

Giả sử client gọi RPC CreateOrder:

1. Client gửi request.
2. Server validate và ghi đơn hàng.
3. Database commit thành công.
4. Kết nối bị ngắt trước khi response tới client.
5. Client nhận UNAVAILABLE hoặc DEADLINE_EXCEEDED.
6. Client retry.

Ở bước 5, client chỉ biết không nhận được response. Nó không biết server đã commit ở bước 3 hay chưa. Nếu server tạo đơn mới cho lần retry, một ý định mua hàng có thể sinh hai đơn.

Cũng có thể server chưa commit và transaction rollback. Khi client retry, lần gửi mới cần được thực thi bình thường.

Vì vậy, server cần phân biệt hai trường hợp bằng một định danh ổn định cho ý định command. Không dùng connection ID, request timestamp hoặc ID mới sinh ở mỗi lần retry làm idempotency key.

## 3. Idempotent operation và idempotency key

Một operation vốn đã idempotent nếu thực hiện lặp lại cùng input không làm thay đổi kết quả cuối ngoài lần đầu. Ví dụ đặt trạng thái tài nguyên thành ACTIVE thường có thể idempotent; lệnh tăng balance thêm 10 hoặc tạo order mới thì không tự idempotent.

Với command không tự idempotent, client tạo một key cho **một ý định nghiệp vụ**:

```text
idempotency_key = "8f2c...-stable-command-id"
```

Quy tắc phía client:

- Sinh key trước lần gửi đầu tiên.
- Giữ nguyên key qua mọi retry của cùng command.
- Dùng key mới khi người dùng thực sự tạo một ý định command mới.
- Lưu key đủ lâu nếu retry có thể tiếp tục sau khi process restart.
- Không dùng chung key cho hai command khác nhau.

Key thường là UUID ngẫu nhiên đủ mạnh hoặc định danh operation được tạo bởi client. Phạm vi key nên bao gồm tenant/client identity và operation/RPC name để tránh hai API hoặc hai tenant vô tình dùng chung namespace.

Ví dụ scope:

```text
(tenant_id, client_application, full_method_name, idempotency_key)
```

Không coi key là cơ chế xác thực. Server vẫn phải kiểm tra authentication và authorization trên từng lần gọi, kể cả khi chỉ replay kết quả cũ.

## 4. Request fingerprint phát hiện key bị tái sử dụng sai

Chỉ lưu key là chưa đủ. Client có thể gửi cùng key nhưng payload khác do bug hoặc do dùng nhầm key cho một command mới.

Server nên tạo **request fingerprint** từ nội dung nghiệp vụ đã chuẩn hóa:

- Xác định các field ảnh hưởng tới side effect.
- Chuẩn hóa representation trước khi hash nếu thứ tự/map/default có thể tạo byte khác nhau cho cùng semantics.
- Không đưa idempotency key, trace ID hoặc metadata thay đổi theo từng lần retry vào fingerprint.
- Dùng hash như SHA-256 trên canonical representation hoặc một encoding nội bộ ổn định.
- Lưu thuật toán/version fingerprint nếu cách canonicalize có thể thay đổi.

Khi key đã tồn tại:

- Fingerprint giống nhau: đây là retry của cùng command; trả kết quả đã lưu hoặc trạng thái đang xử lý.
- Fingerprint khác nhau: từ chối vì key đã được dùng cho một ý định khác.

Không chỉ hash raw bytes một cách máy móc nếu cùng một message có thể serialize thành byte khác nhau nhưng mang cùng semantics do field order, unknown fields hoặc representation. Chọn canonical form phù hợp với contract.

## 5. Lưu idempotency record trong database

Một bảng idempotency record có thể gồm:

| Cột | Mục đích |
| --- | --- |
| tenant_id | Phạm vi tenant |
| client_id | Phạm vi ứng dụng gọi |
| method_name | RPC/full method identity |
| idempotency_key | Key do client tạo |
| request_hash | Fingerprint của command |
| state | Trạng thái xử lý |
| result_payload | Kết quả cần replay hoặc operation reference |
| grpc_status | Status cuối nếu API lưu cả kết quả lỗi |
| created_at | Thời điểm nhận lần đầu |
| expires_at | Thời điểm hết thời hạn lưu key |

Tạo unique constraint trên scope đã chọn, ví dụ:

```sql
CREATE UNIQUE INDEX uq_idempotency_scope
ON idempotency_record (
    tenant_id,
    client_id,
    method_name,
    idempotency_key
);
```

Unique constraint là hàng rào cuối cùng chống hai request cùng key cùng vượt qua kiểm tra đồng thời. Một câu SELECT kiểm tra key rồi mới INSERT mà không có unique constraint vẫn có race condition.

Nếu lưu response Protobuf bytes, phải quản lý schema/type version và giữ khả năng đọc kết quả trong suốt thời gian record còn hiệu lực. Một lựa chọn khác là lưu operation ID hoặc kết quả domain ổn định rồi dựng response theo contract hiện tại. Chọn cách replay nhất quán với API version và yêu cầu giữ nguyên kết quả.

## 6. Claim key, business update và kết quả trong cùng transaction

Với command xử lý ngắn, thiết kế đơn giản và mạnh là đặt việc nhận key, thay đổi nghiệp vụ và lưu kết quả trong **cùng một database transaction**:

1. Atomically thử tạo idempotency record trong scope.
2. Nếu tạo thành công, request này sở hữu việc thực thi.
3. Thực hiện business operation.
4. Lưu kết quả/operation ID vào idempotency record.
5. Commit cả business data và idempotency record cùng nhau.
6. Chỉ sau khi transaction commit, adapter mới gửi gRPC response.

Ví dụ service minh họa:

```java
@Service
@RequiredArgsConstructor
public class CreateOrderService {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final RequestFingerprint fingerprints;

    @Transactional
    public CreateOrderResult execute(
            String tenantId,
            String clientId,
            CreateOrderCommand command) {

        String hash = fingerprints.hash(command);

        boolean claimed = idempotency.insertIfAbsent(
            tenantId,
            clientId,
            "commerce.v1.OrderService/CreateOrder",
            command.idempotencyKey(),
            hash
        );

        if (!claimed) {
            IdempotencyRecord existing = idempotency.findRequired(
                tenantId,
                clientId,
                "commerce.v1.OrderService/CreateOrder",
                command.idempotencyKey()
            );

            if (!existing.requestHash().equals(hash)) {
                throw new IdempotencyKeyReuseException();
            }

            return existing.toCreateOrderResult();
        }

        Order order = orders.save(Order.create(command));
        CreateOrderResult result = CreateOrderResult.from(order);

        idempotency.complete(
            tenantId,
            clientId,
            command.idempotencyKey(),
            result
        );

        return result;
    }
}
```

insertIfAbsent cần được triển khai bằng thao tác atomic phù hợp database, được bảo vệ bởi unique constraint; không phải SELECT-then-INSERT thông thường. Với database/isolation cụ thể, request cạnh tranh có thể phải chờ transaction sở hữu key commit rồi mới đọc record. Nếu transaction snapshot không nhìn thấy record vừa commit, rollback và đọc lại bằng transaction mới.

Nếu business operation thất bại theo cách phải rollback, idempotency record cũng rollback. Lần retry sau có thể trở thành request thực thi. Với kết quả nghiệp vụ từ chối có tính terminal và cần replay ổn định, có thể lưu outcome từ chối như một kết quả đã hoàn tất trong transaction rồi để adapter ánh xạ thành gRPC status sau commit.

## 7. Vì sao unique constraint và transaction phải đi cùng nhau?

Một cách sai thường gặp:

1. SELECT để kiểm tra key chưa tồn tại.
2. Thực hiện tạo order.
3. INSERT idempotency record.
4. Commit.

Hai request cùng key có thể cùng SELECT thấy chưa tồn tại rồi cùng tạo order. Unique constraint có thể chặn một insert record, nhưng nếu order và record không cùng transaction thì side effect của request thua cuộc có thể đã commit.

Thiết kế đúng phải bảo đảm:

- Claim key có atomic uniqueness.
- Business update và kết quả idempotency commit cùng transaction.
- Nếu claim thất bại, không chạy business side effect.
- Nếu business update rollback, claim cũng rollback.
- Nếu commit thành công nhưng response mất, retry đọc được record hoàn tất.

Với ORM, unique violation có thể đánh dấu transaction rollback-only hoặc làm transaction hiện tại không thể tiếp tục, tùy database/provider. Không bắt duplicate-key exception rồi mặc nhiên query record trong cùng transaction. Có thể dùng primitive insert-if-absent/upsert phù hợp hoặc để transaction rollback rồi thực hiện lookup trong transaction mới.

## 8. Request trùng đồng thời và trạng thái PROCESSING

Hai request cùng key có thể đến gần như đồng thời. Hệ thống cần policy xác định.

### Xử lý trong một transaction ngắn

Khi claim, business update và kết quả cùng nằm trong một transaction, unique index điều phối hai request. Request thứ hai thường phải chờ kết quả transaction đầu:

- Nếu request đầu commit, request thứ hai nhận diện key đã tồn tại và replay kết quả.
- Nếu request đầu rollback, request thứ hai có thể claim key và thực hiện operation.
- Nếu chờ quá lâu, caller có thể hết deadline; retry cùng key vẫn an toàn.

Đây thường là lựa chọn phù hợp cho command ngắn.

### Reservation riêng cho tác vụ dài

Với tác vụ dài cần trả ACK sớm, có thể commit record PROCESSING trước khi thực hiện công việc bất đồng bộ. Khi đó cần thêm:

- Owner/worker token.
- Lease expiry và heartbeat.
- Quy tắc takeover khi worker chết.
- Cách phân biệt PROCESSING, COMPLETED và FAILED.
- Worker phải idempotent vì lease hết hạn có thể làm cùng task được giao lại.
- API để client query operation status hoặc retry cùng key.

Không tạo PROCESSING record vĩnh viễn mà không có lease/recovery. Một worker crash không được khiến key bị khóa mãi.

## 9. Replay kết quả và bảo vệ thông tin

Khi request trùng có fingerprint khớp và operation đã hoàn tất, server trả lại kết quả đã lưu mà không thực hiện business logic lần nữa.

Cần quyết định rõ điều gì được replay:

- Response payload hoặc operation ID.
- Kết quả nghiệp vụ cuối.
- gRPC status cuối nếu contract yêu cầu giữ nguyên cả kết quả lỗi.
- Một số metadata/trailer có ý nghĩa contract nếu cần.

Không replay các giá trị chỉ có ý nghĩa cho lần transport trước như trace ID, server timing hoặc debug metadata. Những thông tin này cần được tạo mới cho từng lần gọi.

Authentication và authorization vẫn phải chạy trên mỗi retry. Nếu user/tenant không còn quyền xem kết quả, server không được trả payload đã lưu chỉ vì key khớp. Scope key cũng phải ngăn tenant này dò kết quả của tenant khác.

Nếu kết quả chứa dữ liệu nhạy cảm, áp dụng chính sách mã hóa, quyền truy cập và retention như dữ liệu nghiệp vụ tương ứng.

## 10. Chọn policy cho lỗi và kết quả không thành công

Không phải mọi lỗi đều nên được lưu như kết quả idempotent vĩnh viễn.

| Kết quả lần đầu | Policy thường phù hợp |
| --- | --- |
| Thành công và commit | Lưu kết quả; retry cùng key replay |
| Validation/business rejection terminal | Có thể lưu outcome để retry không đổi kết quả |
| Optimistic conflict ABORTED | Transaction rollback; retry có thể đọc lại và chạy lại nếu contract cho phép |
| Lỗi database/transient trước commit | Rollback claim và business changes; retry cùng key có thể thực thi lại |
| Lỗi sau commit nhưng trước response | Record đã hoàn tất; retry replay kết quả |
| Key trùng nhưng fingerprint khác | Từ chối; không chạy side effect |

Nếu lưu business rejection, không ném exception khiến toàn bộ transaction rollback rồi kỳ vọng record vẫn tồn tại. Thay vào đó, biểu diễn rejection như một outcome được commit mà không thực hiện side effect; adapter chuyển outcome thành status sau khi transaction kết thúc.

Với ABORTED, cần định nghĩa rõ key đại diện cho ý định cố định hay một attempt có thể tính lại theo trạng thái mới. Một thiết kế phổ biến rollback record cùng transaction conflict, cho phép client retry cùng key sau khi đọc lại; nhưng nếu request semantics thay đổi thì fingerprint phải được tính theo input command ổn định và policy phải được công bố.

## 11. Client retry: giữ key, tôn trọng deadline

Client tạo idempotency key một lần cho command, sau đó giữ nguyên key trong mọi lần retry:

```java
String key = commandId; // Được tạo một lần cho ý định nghiệp vụ.

CreateOrderRequest request = CreateOrderRequest.newBuilder()
    .setCustomerId(customerId)
    .setIdempotencyKey(key)
    .addAllItems(items)
    .build();

for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
        return blockingStub
            .withDeadlineAfter(remainingMillis(), TimeUnit.MILLISECONDS)
            .createOrder(request);
    } catch (StatusRuntimeException ex) {
        if (!isRetryable(ex.getStatus().getCode())
                || attempt == MAX_ATTEMPTS) {
            throw ex;
        }
        sleepWithExponentialBackoffAndJitter(attempt);
    }
}
```

Đây là pseudocode minh họa; implementation cần quản lý deadline tổng, cancellation và interrupt đúng cách. Không cấp một deadline mới vô hạn cho mỗi attempt; tổng thời gian retry phải nằm trong ngân sách caller cho phép.

Các nguyên tắc:

- Retry cùng command phải dùng cùng key và cùng payload semantics.
- Không retry lỗi INVALID_ARGUMENT hoặc business rejection không thể tự phục hồi.
- UNAVAILABLE hoặc timeout có thể có outcome chưa rõ; retry cùng key.
- ABORTED yêu cầu đọc lại và retry toàn bộ workflow theo contract.
- Backoff có jitter và số lần thử giới hạn.
- Nếu caller không còn thời gian chờ, có thể trả timeout nhưng giữ key để query/retry sau.

gRPC retry policy ở tầng transport không tự tạo idempotency. Server vẫn phải bảo vệ side effect; không giả định bật retry config là đủ.

## 12. Outbox và side effects bên ngoài

Nếu command vừa cập nhật database vừa cần phát event, ghi business data, idempotency result và outbox record trong cùng transaction:

1. Claim idempotency key.
2. Thực hiện business update.
3. Ghi outbox event với event ID ổn định.
4. Lưu kết quả command vào idempotency record.
5. Commit.
6. Worker publish outbox event.
7. Consumer xử lý idempotent vì publish có thể lặp lại.

Không gửi email, publish broker hoặc gọi RPC ngoài trước commit rồi kỳ vọng database rollback được side effect đó.

Nếu worker publish event nhưng crash trước khi đánh dấu sent, event có thể được publish lại. Consumer cần deduplicate theo event ID hoặc operation ID. Idempotency của command không tự động làm mọi downstream consumer exactly-once.

## 13. Retention, expiration và key scope

Idempotency record cần được giữ ít nhất trong khoảng thời gian client có thể retry hoặc phục hồi sau sự cố. Nếu xóa record quá sớm, một retry muộn có thể tạo side effect mới.

Chọn retention dựa trên deadline tối đa và retry window của client; thời gian client có thể offline rồi gửi lại; thời gian xử lý batch/reconciliation; quy định lưu giữ dữ liệu và audit; thời gian downstream có thể phát lại command/event.

Khi record hết hạn, cần quyết định key có được tái sử dụng hay không. Thường client vẫn phải tạo key mới cho ý định mới; không dùng lại key cũ chỉ vì record đã bị cleanup.

Scope key cần đủ chặt: tenant/client/method/key. Cleanup job nên xóa theo batch có giới hạn, tránh khóa bảng lâu. Với operation dài, giữ operation ID/tombstone lâu hơn response payload nếu cần ngăn duplicate sau khi kết quả chi tiết đã hết retention.

## 14. Kiểm thử idempotency

Unit test một lần gọi thành công chưa chứng minh idempotency. Cần kiểm thử retry và cạnh tranh thật trên database:

| Test | Điều cần xác nhận |
| --- | --- |
| Cùng key, cùng payload sau commit | Trả lại cùng kết quả; business side effect chỉ một lần |
| Cùng key, payload khác | Từ chối; không thực hiện side effect lần hai |
| Hai request cùng key đồng thời | Unique constraint chỉ cho một execution |
| Request đầu rollback | Request retry có thể thực hiện theo policy |
| Commit xong nhưng response bị mất | Retry replay kết quả đã lưu |
| Hai tenant dùng cùng key | Scope không làm lộ hoặc trộn kết quả |
| Worker PROCESSING bị crash | Lease/recovery cho phép tiếp tục mà không duplicate |
| Outbox publish lặp | Consumer deduplicate event |
| Record hết hạn | Hành vi retry muộn đúng retention contract |
| Authorization thay đổi | Replay vẫn kiểm tra quyền hiện tại |

Dùng hai transaction/thread độc lập để tạo race condition. Testcontainers hoặc database cùng loại production giúp xác minh unique constraint, isolation và insert-if-absent behavior. Một test chỉ gọi repository tuần tự sẽ không phát hiện race giữa SELECT và INSERT.

Để mô phỏng response bị mất, cho server commit thành công rồi ngắt transport trước khi client nhận response; gọi lại cùng request/key và xác nhận kết quả cũ được trả mà không tạo record nghiệp vụ thứ hai.

## 15. Checklist review

- Client sinh key một lần cho một ý định nghiệp vụ và giữ nguyên qua retry.
- Key có scope tenant/client/method rõ ràng; không dùng làm authentication.
- Request fingerprint bao gồm field ảnh hưởng side effect và loại bỏ metadata biến động.
- Key reuse với payload khác bị từ chối.
- Database có unique constraint trên idempotency scope.
- Claim key, business update và stored result commit cùng transaction cho command ngắn.
- Không dựa vào SELECT-then-INSERT làm concurrency guard.
- Request trùng đồng thời được chờ/replay hoặc xử lý bằng PROCESSING lease có recovery.
- Adapter chỉ trả response sau commit.
- Kết quả replay không thực hiện side effect lần nữa và vẫn kiểm tra authorization.
- Policy cho success, terminal rejection, ABORTED và transient error được định nghĩa.
- Client retry có deadline tổng, backoff/jitter và số lần thử giới hạn.
- Outbox event có ID ổn định; downstream consumer có deduplication.
- Retention dài hơn retry/recovery window đã cam kết.
- Có integration tests cho race, rollback, lost response và key mismatch.

Trong **SPRING_GRPC**, idempotency key biến retry của một command thành việc hỏi lại kết quả của cùng ý định nghiệp vụ. Server cần phối hợp unique constraint, request fingerprint và transaction để lưu side effect cùng kết quả một cách nguyên tử. Khi response bị mất sau commit, lần retry cùng key sẽ replay kết quả; khi request đầu chưa commit, transaction rollback cho phép một attempt hợp lệ khác thực thi. Cùng với deadline, backoff, authorization và outbox, cơ chế này giúp command an toàn trước retry và lỗi mạng.
