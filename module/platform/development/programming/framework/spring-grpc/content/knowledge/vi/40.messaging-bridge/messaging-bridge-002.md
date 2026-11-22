# Chuyển RPC request thành command message

## 1. Mapping tạo ranh giới giữa API và message flow

Trong **SPRING_GRPC**, client gửi request theo hợp đồng Protocol Buffers đến service Spring. Khi RPC là ingress cho message flow, server cần chuyển request transport thành **command message** biểu đạt ý định nghiệp vụ mà consumer có thể xử lý độc lập.

Mapping tạo ranh giới giữa ba mô hình:

- **Protobuf request:** cấu trúc wire contract mà client gửi.
- **Application command:** dữ liệu có kiểu, biểu đạt một ý định nghiệp vụ.
- **Command message/envelope:** nội dung được serialize và gửi qua broker, kèm metadata phục vụ định tuyến, truy vết, tương thích và xử lý lặp.

~~~mermaid
flowchart LR
    A["Protobuf RPC request"] --> B["Validate presence / shape"]
    B --> C["Read trusted caller context"]
    C --> D["Map to application command"]
    D --> E["Wrap in message envelope"]
    E --> F["Serialize with schema"]
    F --> G["Publish to broker"]
    G --> H["Consumer maps to use case"]
~~~

Mỗi bước có một trách nhiệm. Mapper không xác thực credential, không quyết định quyền truy cập và không thực hiện side effect nghiệp vụ. Nó nhận dữ liệu đã được xác thực ở ranh giới phù hợp, chuẩn hóa field transport và tạo command có cấu trúc ổn định.

## 2. Protobuf request không phải command message

Hai loại message có thể chứa các field tương tự nhưng phục vụ mục đích khác nhau:

| Protobuf RPC request | Command message |
|---|---|
| Được thiết kế cho client gọi một RPC | Được thiết kế cho consumer thực thi một ý định |
| Chứa field theo API công khai | Chứa dữ liệu tối thiểu cần cho use case |
| Có thể chứa field phục vụ tương thích client | Có schema và version riêng cho message flow |
| Gắn với method/service gRPC | Có command ID, tenant, correlation và routing key |
| Có thể chứa giá trị mặc định do protobuf tạo | Phải biểu đạt rõ field nào thực sự được cung cấp |

Ví dụ `SubmitOrderRequest` có thể mang `customer_id`, danh sách line và `idempotency_key`. Command nội bộ có thể bổ sung `tenantId`, `actorId`, `commandId` và `correlationId` lấy từ context đã xác thực. Những thông tin này không nên được caller tự quyết định bằng cách gửi thêm field giả mạo.

Nếu serialize nguyên generated request vào topic, consumer bị ràng buộc vào package, schema và lifecycle của API gRPC. Thay đổi API có thể vô tình thay đổi message flow dù hợp đồng giữa producer và consumer không hề được thiết kế lại.

## 3. Bắt đầu từ hợp đồng RPC rõ ràng

Ví dụ API nhận yêu cầu tạo đơn:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.rpc";

service OrdersIngress {
  rpc SubmitOrder(SubmitOrderRequest) returns (SubmitOrderReply);
}

message SubmitOrderRequest {
  optional string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
  string note = 4;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

message SubmitOrderReply {
  string command_id = 1;
  string state = 2;
}
~~~

`customer_id` dùng `optional` để phân biệt field vắng mặt với field được gửi nhưng có giá trị rỗng. `lines` là repeated field nên không có presence theo cách của scalar optional; danh sách rỗng được kiểm tra qua `getLinesCount()`. `note` là scalar không có presence trong ví dụ này, vì vậy getter trả giá trị mặc định khi client không gửi field.

Quyết định presence phải xuất phát từ ý nghĩa API. Nếu `note` cần phân biệt “không cung cấp” với “xóa ghi chú”, hãy dùng `optional` hoặc `oneof` thay vì suy luận từ chuỗi rỗng.

## 4. Application command có kiểu riêng

Command nên phản ánh ý định nghiệp vụ và không phụ thuộc generated protobuf class:

~~~java
import java.util.List;

public record CreateOrderCommand(
        String commandId,
        String tenantId,
        String actorId,
        String customerId,
        List<Line> lines,
        String note,
        String idempotencyKey,
        String correlationId) {

    public CreateOrderCommand {
        lines = List.copyOf(lines);
    }

    public record Line(String sku, int quantity) {}
}
~~~

Command này không chứa `SubmitOrderRequest`, `StreamObserver`, `Metadata` hoặc `ServerCall`. Vì vậy, consumer có thể dùng command mà không cần phụ thuộc gRPC runtime.

Một command có thể được tạo từ nhiều adapter: gRPC, REST, scheduler hoặc message consumer khác. Các adapter khác nhau có thể map vào cùng một application command nếu chúng biểu đạt cùng một ý định nghiệp vụ.

Không thêm mọi field của request vào command theo thói quen. Chỉ giữ field mà use case cần để thực hiện hoặc audit ý định. Field chỉ phục vụ hiển thị ở client có thể không cần đi vào message.

## 5. Phân biệt validation cấu trúc và validation nghiệp vụ

Trước khi map, cần kiểm tra request có đủ dữ liệu để tạo command hợp lệ về mặt cấu trúc:

- Field bắt buộc có presence hoặc không rỗng theo hợp đồng.
- Danh sách line không rỗng và không vượt giới hạn kích thước.
- Chuỗi được chuẩn hóa theo quy ước, ví dụ trim khoảng trắng ở mã định danh.
- Số lượng nằm trong miền biểu diễn cho phép.
- Idempotency key có định dạng và độ dài hợp lệ.

Các quy tắc như SKU có đang bán, khách hàng có quyền đặt hàng, tồn kho còn đủ hoặc đơn có vượt hạn mức không thuộc mapper. Đó là validation nghiệp vụ trong use case/consumer và phải được kiểm tra lại tại thời điểm thực thi vì trạng thái có thể thay đổi sau khi command được publish.

Ví dụ:

~~~java
private void validateShape(SubmitOrderRequest request) {
    if (!request.hasCustomerId()
            || request.getCustomerId().isBlank()) {
        throw new InvalidCommandRequest("customer_id is required");
    }
    if (request.getLinesCount() == 0) {
        throw new InvalidCommandRequest("at least one line is required");
    }
    if (request.getLinesCount() > 100) {
        throw new InvalidCommandRequest("too many order lines");
    }
    if (request.getIdempotencyKey().isBlank()) {
        throw new InvalidCommandRequest("idempotency_key is required");
    }
}
~~~

Giới hạn 100 line chỉ là ví dụ. Hãy đặt giới hạn theo hợp đồng, kích thước message, thời gian xử lý và năng lực broker/consumer. Đừng dựa vào validation ở ingress để bỏ validation trong consumer: message có thể đến từ producer khác hoặc được phát lại sau thời gian dài.

## 6. Lấy tenant và actor từ nguồn đáng tin cậy

Các field nhận diện caller phải lấy từ principal đã xác thực, thường được thiết lập bởi authentication interceptor hoặc security integration:

~~~java
public record TrustedCaller(
        String tenantId,
        String actorId,
        String correlationId) {}
~~~

Mapper nhận caller context riêng:

~~~java
private CreateOrderCommand toCommand(
        SubmitOrderRequest request,
        TrustedCaller caller,
        String commandId) {

    var lines = request.getLinesList().stream()
            .map(line -> new CreateOrderCommand.Line(
                    line.getSku().trim(),
                    line.getQuantity()))
            .toList();

    return new CreateOrderCommand(
            commandId,
            caller.tenantId(),
            caller.actorId(),
            request.getCustomerId().trim(),
            lines,
            request.getNote(),
            request.getIdempotencyKey(),
            caller.correlationId());
}
~~~

Không dùng `tenant_id` hoặc `actor_id` do client gửi làm danh tính đã xác minh. Nếu API cần caller chỉ định một đối tượng trong tenant, use case phải kiểm tra đối tượng đó có thuộc tenant của principal và caller có quyền thao tác hay không.

Correlation ID có thể được lấy từ metadata sau khi kiểm tra định dạng, hoặc được tạo tại ingress nếu chưa có. Không đưa toàn bộ gRPC metadata vào command; chỉ truyền các giá trị đã được cho phép và có ý nghĩa xuyên qua message flow.

## 7. Message envelope tách metadata khỏi payload

Một command message nên có envelope nhất quán để consumer biết loại message, nguồn gốc và cách xử lý:

~~~java
import java.time.Instant;

public record CommandEnvelope<T>(
        String messageId,
        String messageType,
        int schemaVersion,
        String aggregateKey,
        String tenantId,
        String actorId,
        String correlationId,
        String causationId,
        Instant createdAt,
        T payload) {}
~~~

Ý nghĩa các field:

| Field | Vai trò |
|---|---|
| `messageId` | Định danh duy nhất của message |
| `messageType` | Tên ổn định của loại command, ví dụ `orders.create` |
| `schemaVersion` | Phiên bản schema của payload |
| `aggregateKey` | Khóa phân vùng/định tuyến theo aggregate nếu broker hỗ trợ |
| `tenantId`, `actorId` | Ngữ cảnh tenant và actor đã được xác minh |
| `correlationId` | Liên kết các bước của cùng request/workflow |
| `causationId` | Message hoặc action gây ra command hiện tại |
| `createdAt` | Thời điểm ingress tạo envelope |
| `payload` | Dữ liệu command có schema riêng |

Không đưa access token, refresh token, mật khẩu hoặc toàn bộ metadata transport vào envelope. Message broker là một ranh giới bảo mật riêng; topic ACL, encryption, retention và quyền consumer phải được cấu hình theo độ nhạy của payload.

## 8. Xây dựng envelope và publish message

Sau khi mapper tạo command, ingress tạo envelope và publish với key phù hợp:

~~~java
CreateOrderCommand command =
        mapper.toCommand(request, caller, commandId);

CommandEnvelope<CreateOrderCommand> envelope =
        new CommandEnvelope<>(
                command.commandId(),
                "orders.create",
                1,
                command.customerId(),
                command.tenantId(),
                command.actorId(),
                command.correlationId(),
                rpcRequestId,
                clock.instant(),
                command);

kafkaTemplate.send(
        "orders.commands",
        command.customerId(),
        envelope);
~~~

Ví dụ dùng customer ID làm key chỉ phù hợp nếu thứ tự cần giữ theo khách hàng. Nếu các thay đổi cần được tuần tự hóa theo từng đơn hàng, dùng `orderId` hoặc aggregate key tương ứng. Với command tạo đơn chưa có `orderId`, có thể dùng command ID hoặc một business key ổn định được thiết kế cho mục tiêu ordering.

Đừng chọn key chỉ vì field đó có sẵn. Key quyết định phân phối partition và khả năng giữ thứ tự; chọn sai có thể gom tải vào một partition hoặc làm các command liên quan bị xử lý song song.

## 9. Idempotency key và command ID phải ổn định

Client có thể retry cùng RPC khi response bị mất. Ingress có thể đã publish message nhưng chưa nhận được acknowledgement. Nếu retry tạo `commandId` mới, cùng một ý định có thể được xử lý nhiều lần.

Quy tắc mapping:

1. Client tạo idempotency key cho một ý định nghiệp vụ.
2. Retry của cùng ý định gửi lại key đó.
3. Ingress xác định phạm vi key bằng tenant/principal đã xác thực.
4. Store có unique constraint cho `(tenantId, idempotencyKey)`.
5. Lần đầu tạo command ID và lưu fingerprint của payload; lần sau trả lại command ID đã có nếu payload tương đương.
6. Cùng key nhưng payload khác phải trả conflict theo API contract.

Không chỉ băm idempotency key thành command ID rồi bỏ qua việc lưu trạng thái. Hệ thống vẫn cần xử lý cạnh tranh giữa hai request cùng key, lưu kết quả mapping bền vững và xác định trạng thái publish.

Consumer cũng cần deduplicate theo command ID hoặc business key trước side effect. Idempotency ở ingress bảo vệ việc tạo command; idempotency ở consumer bảo vệ việc thực thi message lặp.

## 10. Schema evolution cho command message

Message có thể tồn tại lâu hơn một phiên bản triển khai của producer hoặc consumer. Vì vậy, schema command cần được quản lý độc lập với API gRPC:

- Thêm field mới theo cách tương thích; xác định giá trị mặc định khi consumer cũ không biết field đó.
- Không tái sử dụng field number đã xóa nếu payload dùng Protobuf.
- Giữ ý nghĩa field hiện tại; không đổi `customerId` từ customer sang account chỉ vì tên field còn phù hợp.
- Dùng `messageType` và `schemaVersion` ổn định.
- Consumer phải có chiến lược xử lý phiên bản chưa hỗ trợ: reject có kiểm soát, quarantine hoặc dead-letter.
- Triển khai consumer hiểu schema mới trước khi producer bắt đầu phát field bắt buộc mới.

Nếu payload dùng Protobuf, generated command message nên là message riêng như `CreateOrderCommandMessage`, không dùng lại `SubmitOrderRequest`. Nếu payload dùng JSON/Avro, dùng schema registry hoặc quy trình review/versioning tương ứng.

Không giả định mapper sẽ tự giữ mọi field chưa biết. Khi map generated request sang application record, field không được ánh xạ sẽ bị loại khỏi command. Đó thường là điều mong muốn vì command chỉ chứa dữ liệu được use case chấp nhận; nếu cần forward-compatible pass-through, phải thiết kế rõ ràng và kiểm soát field được phép truyền.

## 11. Enum, optional, oneof và kiểu dữ liệu đặc biệt

Mapping cần xử lý các đặc tính của protobuf thay vì chỉ gọi getter:

| Protobuf | Rủi ro khi map | Cách xử lý |
|---|---|---|
| Scalar không có presence | Getter trả default khi field vắng mặt | Dùng `optional`/`oneof` nếu cần phân biệt |
| `repeated` | Danh sách rỗng có thể hợp lệ hoặc không | Kiểm tra theo hợp đồng |
| Enum | Client mới có thể gửi giá trị mà server cũ không nhận diện | Xử lý `UNRECOGNIZED` rõ ràng |
| `oneof` | Chỉ một nhánh được chọn | Kiểm tra `getChoiceCase()` trước khi map |
| `google.protobuf.Timestamp` | Có thể chứa giá trị ngoài miền hợp lệ | Chuyển sang `Instant` qua helper có kiểm tra |
| `int32`/`int64` | Có thể không khớp miền kiểu domain | Kiểm tra range trước khi ép kiểu |

Ví dụ enum:

~~~java
PaymentMethod method = switch (request.getPaymentMethod()) {
    case CARD -> PaymentMethod.CARD;
    case BANK_TRANSFER -> PaymentMethod.BANK_TRANSFER;
    case PAYMENT_METHOD_UNSPECIFIED ->
            throw new InvalidCommandRequest("payment method is required");
    case UNRECOGNIZED ->
            throw new InvalidCommandRequest("unsupported payment method");
};
~~~

Không dùng ordinal của enum để lưu vào message hoặc database. Thứ tự enum có thể thay đổi; dùng tên/giá trị contract ổn định và mapping tường minh.

## 12. Consumer chỉ nhận command contract

Consumer không nên phụ thuộc vào gRPC request hoặc transport context:

~~~java
@KafkaListener(topics = "orders.commands")
public void handle(CommandEnvelope<CreateOrderCommand> envelope) {
    deduplication.executeOnce(
            envelope.messageId(),
            () -> createOrderUseCase.execute(envelope.payload()));
}
~~~

Đây là skeleton; consumer thực tế phải xử lý deserialization, retry, acknowledgement/offset commit, dead-letter và transaction. `executeOnce` cần lưu marker và side effect theo transaction hoặc cơ chế idempotency phù hợp; chỉ kiểm tra marker trong bộ nhớ không bảo đảm an toàn khi restart.

Consumer nên xác minh message type/version, tenant và schema trước khi gọi use case. Không coi envelope là đáng tin cậy chỉ vì message đến từ broker; broker ACL và quyền producer cần được kiểm soát, đồng thời consumer vẫn phải áp dụng authorization nghiệp vụ cần thiết.

## 13. Mapping và publish có thể cần transactional outbox

Nếu ingress phải lưu command receipt hoặc idempotency mapping trong database đồng thời publish message, hai thao tác riêng rẽ tạo dual-write:

~~~text
DB commit thành công
    |
    +--> process crash
             |
             v
       message chưa publish
~~~

Transactional outbox ghi command receipt, idempotency mapping và outbox record trong cùng một database transaction. Relay publish outbox record sau đó. Khi broker xác nhận, relay đánh dấu record đã gửi. Relay có thể publish lại sau crash, nên consumer vẫn phải deduplicate.

Với outbox, API có thể định nghĩa `ACCEPTED` tại thời điểm transaction commit vì command đã được ghi nhận bền vững để dispatch. Nếu hợp đồng hứa broker đã nhận message, chỉ trả response sau acknowledgement của relay/broker. Hai mốc này khác nhau và phải được mô tả rõ trong API.

## 14. Kiểm thử mapping request thành command

Mapper nên có unit test độc lập với broker. Integration test kiểm tra đường đi đầy đủ:

| Kịch bản | Điều cần xác minh |
|---|---|
| Request hợp lệ | Command có đúng field và giá trị đã chuẩn hóa |
| Scalar optional vắng mặt | Mapping từ chối hoặc áp dụng default đúng hợp đồng |
| Repeated field rỗng/quá lớn | Validation xử lý đúng |
| Enum `UNRECOGNIZED` | Không âm thầm map sang giá trị hợp lệ khác |
| `oneof` không có nhánh | Trả lỗi validation phù hợp |
| Tenant/principal khác nhau | Command lấy identity từ context đáng tin cậy |
| Metadata thiếu correlation ID | Tạo ID theo quy ước và giữ xuyên message flow |
| Cùng idempotency key, cùng payload | Command ID ổn định, không tạo operation thứ hai |
| Cùng key, payload khác | Trả conflict theo hợp đồng |
| Schema version mới | Consumer cũ xử lý theo chính sách tương thích |
| Publish lỗi sau khi DB commit | Outbox relay tiếp tục dispatch |
| Consumer nhận lại message | Side effect không lặp |

Test mapper không cần chạy broker. Test producer/consumer cần broker thật hoặc containerized broker để xác minh serializer, partition key, acknowledgement và redelivery. Mock `KafkaTemplate` chỉ chứng minh lời gọi publish được thực hiện, không chứng minh message có thể được consumer đọc.

## 15. Metrics và chẩn đoán

Theo dõi các giai đoạn riêng:

- Số request bị từ chối ở validation và nguyên nhân.
- Thời gian mapping và tạo envelope.
- Số idempotency hit, conflict và race condition.
- Số command theo `messageType`/`schemaVersion`.
- Publish success/failure, acknowledgement latency và pending send.
- Partition distribution, consumer lag và processing latency.
- Số message không hỗ trợ schema, deserialize failure và dead-letter.
- Correlation ID xuyên suốt RPC → command → consumer.

Không dùng `commandId`, `customerId` hoặc correlation ID làm metric label có cardinality cao. Dùng log/trace để truy vết từng operation; metric label nên là service, method, message type, version hoặc status có tập giá trị giới hạn.

## 16. Những lỗi mapping thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Publish nguyên protobuf RPC request | Consumer phụ thuộc transport contract | Map sang command schema riêng |
| Tin tenant/actor do client gửi | Có nguy cơ giả mạo danh tính | Lấy từ principal đã xác thực |
| Không kiểm tra presence của scalar | Field vắng mặt bị hiểu thành default hợp lệ | Dùng `optional`/`oneof` và kiểm tra presence |
| Đưa business validation vào mapper | Quy tắc bị lặp và không được kiểm tra lại ở consumer | Giữ mapper ở structural validation; use case kiểm tra nghiệp vụ |
| Tạo command ID mới mỗi retry | Một ý định tạo nhiều command | Idempotency mapping bền vững |
| Dùng request ID làm aggregate key | Ordering không theo aggregate nghiệp vụ | Chọn key theo entity cần giữ thứ tự |
| Đổi schema message cùng lúc với API mà không version | Consumer cũ không đọc được message mới | Quản lý schema/version độc lập |
| Đưa toàn bộ metadata vào envelope | Rò rỉ token và dữ liệu transport không cần thiết | Allowlist field được truyền |
| Chỉ test mapper bằng mock producer | Bỏ sót serializer, ack và redelivery | Bổ sung broker integration test |

**Ghi nhớ:** Chuyển RPC request thành command message là bước mapping có chủ đích giữa protobuf contract, application command và broker envelope. Kiểm tra presence/shape ở ingress, lấy tenant/actor từ danh tính tin cậy, giữ command schema độc lập với request, dùng message ID và idempotency key ổn định, chọn aggregate key theo yêu cầu ordering và version schema riêng. Consumer nhận command, xác minh và thực thi idempotently; transactional outbox bảo vệ việc ghi nhận cùng publish khi hai thao tác phải nhất quán.
