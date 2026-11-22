# Idempotency của unary RPC

## 1. Vì sao retry unary RPC cần idempotency?

Giả sử client gọi `CreateOrder`. Server đã ghi đơn hàng vào database, nhưng kết nối bị ngắt trước khi response tới client. Client chỉ thấy `UNAVAILABLE` hoặc `DEADLINE_EXCEEDED`; nó không biết server đã tạo đơn hàng hay chưa. Nếu gửi lại request như một thao tác mới, server có thể tạo **hai đơn hàng** cho cùng một ý định của người dùng.

**Idempotency** cho phép server nhận diện nhiều lần gửi của cùng một thao tác logic và bảo đảm chúng không tạo tác dụng phụ lặp lại. Với unary RPC, cách phổ biến là client gửi một **idempotency key** ổn định; server lưu key cùng dấu vân tay request và kết quả đã tạo.

Mục tiêu không phải làm cho mạng chỉ gửi đúng một lần. Mạng có thể gửi lại, response có thể mất và client có thể không biết kết quả. Mục tiêu là khiến các lần gọi lặp cùng key có **một kết quả nghiệp vụ nhất quán** trong phạm vi thời gian lưu key.

Sau bài học, người học có thể thiết kế idempotency key cho unary RPC, lưu key và kết quả một cách nguyên tử trong Spring, xử lý request trùng đồng thời, phân biệt key trùng với payload khác và kiểm thử retry mà không tạo tác dụng phụ lặp.

## 2. Idempotency không đồng nghĩa exactly-once delivery

Có ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| At-most-once effect theo key | Một thao tác logic chỉ tạo tối đa một tác dụng phụ được bảo vệ trong phạm vi key/retention |
| At-least-once delivery | Client hoặc hạ tầng có thể gửi lại request cho tới khi nhận được kết quả |
| Exactly-once delivery | Mạng bảo đảm request chỉ được chuyển đúng một lần; đây không phải bảo đảm của gRPC |

gRPC retry có thể tạo nhiều attempt cho cùng logical RPC. Idempotency ở tầng ứng dụng giúp các attempt đó không thực hiện lại tác dụng phụ. Nhưng nếu một tác dụng phụ nằm ngoài transaction database, ví dụ gọi cổng thanh toán hoặc gửi email, chỉ lưu key trong database của service chưa đủ để bảo đảm tác dụng phụ bên ngoài xảy ra đúng một lần.

Vì vậy, hãy mô tả guarantee chính xác: **cùng scope, cùng key và cùng request fingerprint sẽ trả lại cùng kết quả đã lưu; key không được tái sử dụng cho request khác**. Guarantee chỉ tồn tại trong thời gian record còn được lưu và trong các hệ thống side effect đã được bảo vệ.

## 3. Thiết kế idempotency key

Một key tốt cần đáp ứng:

- **Ổn định qua retry:** client tạo key một lần cho một ý định nghiệp vụ và giữ nguyên key qua mọi attempt.
- **Đủ duy nhất:** UUID/ULID ngẫu nhiên hoặc định danh được tạo từ hệ thống có uniqueness phù hợp.
- **Có scope:** kết hợp tenant/principal, tên method và key để tránh va chạm giữa khách hàng hoặc API khác nhau.
- **Không chứa bí mật:** key có thể xuất hiện trong log và trace; không nhúng access token, số thẻ hoặc dữ liệu nhạy cảm.
- **Có thời hạn lưu:** server công bố thời gian giữ record và hành vi khi key hết hạn.

Ví dụ:

```text
scope = tenant-17
method = orders.v1.OrderService/CreateOrder
idempotency_key = 01JQ7M9K2Y...
```

Khóa duy nhất trong storage có thể là bộ ba `(tenant_id, method_name, idempotency_key)`. Không nên chỉ dùng key toàn cục nếu hệ thống có nhiều tenant hoặc nhiều method.

### 3.1. Tạo key ở client, không tạo lại trong mỗi attempt

Client tạo key trước khi gọi RPC và giữ nó trong đối tượng command:

```java
String key = UUID.randomUUID().toString();
CreateOrderRequest request = CreateOrderRequest.newBuilder()
        .setIdempotencyKey(key)
        .setCustomerId("customer-42")
        .setProductCode("BOOK-17")
        .setQuantity(2)
        .build();

CreateOrderResponse response = stub
        .withDeadlineAfter(3, TimeUnit.SECONDS)
        .createOrder(request);
```

Nếu caller quyết định thử lại sau khi call kết thúc, phải dùng **cùng request và cùng key**. Tạo UUID mới cho lần thử sau sẽ khiến server coi đó là một thao tác mới. Nếu người dùng chủ động tạo đơn hàng mới, lúc đó mới tạo key mới.

Trong ứng dụng cần phục hồi sau khi process client khởi động lại, key và payload của thao tác đang chờ có thể phải được lưu bền vững phía client trước khi gửi.

## 4. Đặt key trong Protobuf hay metadata?

Với một thao tác unary, đặt key trong request message là cách rõ ràng, dễ kiểm thử và dễ lưu cùng dữ liệu nghiệp vụ:

```proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.v1";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
}

message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  string product_code = 3;
  int32 quantity = 4;
}

message CreateOrderResponse {
  string order_id = 1;
  string status = 2;
}
```

Có thể truyền key qua gRPC metadata nếu đó là quy ước chung của nền tảng, nhưng cần thống nhất tên header, validation, interceptor và cách lưu. Không truyền cùng một key ở cả metadata lẫn body mà không định nghĩa nguồn nào có thẩm quyền khi hai giá trị khác nhau.

Trong bài này, key nằm trong Protobuf để mối liên hệ với thao tác nghiệp vụ được thể hiện trực tiếp.

## 5. Fingerprint để phát hiện dùng lại key sai

Chỉ kiểm tra key là chưa đủ. Client có thể vô tình gửi cùng key với payload khác:

```text
Lần đầu: key=K, product=BOOK-17, quantity=2
Lần sau: key=K, product=BOOK-17, quantity=5
```

Nếu server chỉ nhìn thấy key, nó có thể trả kết quả của request đầu cho request thứ hai dù ý định đã thay đổi. Vì vậy server cần tính **request fingerprint** từ các trường có ý nghĩa nghiệp vụ, ví dụ:

[
fingerprint = SHA256(canonical(customer, product, quantity))
]

Quy tắc:

- Chuẩn hóa dữ liệu trước khi hash: thứ tự field, encoding, giá trị mặc định và cách biểu diễn số phải nhất quán.
- Không đưa chính idempotency key vào fingerprint.
- Chỉ hash các trường ảnh hưởng kết quả nghiệp vụ; không đưa trace ID, deadline hoặc metadata vận chuyển vào.
- Nếu cùng key nhưng fingerprint khác, trả lỗi xung đột, thường dùng `ALREADY_EXISTS` hoặc status được contract quy định.

Không dùng hash không có kiểm soát trên chuỗi JSON tùy ý nếu thứ tự field hoặc định dạng có thể thay đổi. Dùng canonical representation ổn định, chẳng hạn serializer có quy tắc rõ ràng hoặc chuỗi trường đã chuẩn hóa.

## 6. Lưu idempotency record nguyên tử

Một bảng tối thiểu có thể như sau:

```sql
CREATE TABLE grpc_idempotency (
    tenant_id          VARCHAR(100) NOT NULL,
    method_name        VARCHAR(200) NOT NULL,
    idempotency_key    VARCHAR(160) NOT NULL,
    request_hash       VARCHAR(64) NOT NULL,
    response_type      VARCHAR(200),
    response_payload   BYTEA,
    created_at         TIMESTAMP NOT NULL,
    expires_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, method_name, idempotency_key)
);
```

Ràng buộc primary key là phần quan trọng: nó bảo đảm hai transaction đồng thời không thể cùng tạo hai record cho một scope/key. Kiểm tra kiểu `SELECT` rồi sau đó `INSERT` mà không có unique constraint là không an toàn vì hai request có thể cùng thấy “chưa tồn tại”.

Với side effect nằm trong cùng database, một cách triển khai mạnh là:

1. Bắt đầu transaction.
2. Thử insert idempotency record bằng thao tác atomic như `INSERT ... ON CONFLICT DO NOTHING`.
3. Nếu insert thành công, transaction hiện tại là owner: thực hiện thay đổi nghiệp vụ và lưu response vào record.
4. Commit thay đổi nghiệp vụ và response cùng một transaction.
5. Nếu insert không thành công, đọc record đã tồn tại, so sánh fingerprint và trả lại response đã lưu.

Khi hai request đồng thời dùng cùng key, unique constraint khiến transaction đến sau phải chờ kết quả của transaction đầu hoặc nhận conflict. Sau khi transaction đầu commit, request sau đọc được response đã lưu; nếu transaction đầu rollback, request sau có thể giành quyền tạo record và thực hiện thao tác.

### 6.1. Vì sao phải lưu response cùng transaction?

Giả sử service tạo đơn hàng rồi mới lưu response idempotency ở một transaction khác. Nếu service crash giữa hai bước, đơn hàng đã tồn tại nhưng record idempotency chưa có; retry có thể tạo đơn hàng thứ hai.

Đưa **thay đổi nghiệp vụ và response idempotency vào cùng transaction** giúp hai phần cùng commit hoặc cùng rollback, miễn là chúng nằm trong cùng transactional database.

Không commit một record `IN_PROGRESS` riêng rồi xử lý side effect ở transaction khác mà không có lease/recovery. Nếu process chết sau khi claim key, record có thể kẹt vĩnh viễn. Mô hình claim tách transaction cần thêm owner token, lease expiry, heartbeat hoặc cơ chế phục hồi rõ ràng.

## 7. Luồng xử lý trong Spring service

Service nên phân biệt ba kết quả từ tầng idempotency store:

| Kết quả claim | Hành vi |
| --- | --- |
| `OWNER` | Request hiện tại sở hữu key và được thực thi |
| `REPLAY` | Key và fingerprint khớp record đã hoàn tất; trả response đã lưu |
| `KEY_CONFLICT` | Key đã dùng cho fingerprint khác; từ chối |

Một abstraction giúp nhìn rõ luồng nghiệp vụ:

```java
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final IdempotentOrderHandler handler;

    public OrderGrpcService(IdempotentOrderHandler handler) {
        this.handler = handler;
    }

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderResponse> observer) {
        try {
            CreateOrderResponse response = handler.execute(request);
            observer.onNext(response);
            observer.onCompleted();
        } catch (StatusRuntimeException error) {
            observer.onError(error);
        } catch (RuntimeException error) {
            observer.onError(Status.INTERNAL
                    .withDescription("Không thể tạo đơn hàng")
                    .asRuntimeException());
        }
    }
}
```

Phần idempotency nằm trong application handler, không nằm trong callback transport:

```java
import com.google.protobuf.InvalidProtocolBufferException;
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderHandler {
    private final IdempotencyStore idempotencyStore;
    private final OrderRepository orderRepository;
    private final RequestFingerprint fingerprint;

    public IdempotentOrderHandler(
            IdempotencyStore idempotencyStore,
            OrderRepository orderRepository,
            RequestFingerprint fingerprint) {
        this.idempotencyStore = idempotencyStore;
        this.orderRepository = orderRepository;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public CreateOrderResponse execute(CreateOrderRequest request) {
        if (request.getIdempotencyKey().isBlank()) {
            throw Status.INVALID_ARGUMENT
                    .withDescription("idempotency_key bắt buộc")
                    .asRuntimeException();
        }
        if (request.getQuantity() <= 0) {
            throw Status.INVALID_ARGUMENT
                    .withDescription("quantity phải lớn hơn 0")
                    .asRuntimeException();
        }

        String tenantId = currentTenantId();
        String method = "orders.v1.OrderService/CreateOrder";
        String hash = fingerprint.forCreateOrder(request);

        IdempotencyStore.Claim claim = idempotencyStore.claimOrLoad(
                tenantId, method, request.getIdempotencyKey(), hash);

        return switch (claim.kind()) {
            case REPLAY -> decodeStoredResponse(claim.responsePayload());
            case KEY_CONFLICT -> throw Status.ALREADY_EXISTS
                    .withDescription(
                            "idempotency_key đã dùng với request khác")
                    .asRuntimeException();
            case OWNER -> {
                Order order = orderRepository.save(
                        new Order(request.getCustomerId(),
                                request.getProductCode(),
                                request.getQuantity()));
                CreateOrderResponse response = CreateOrderResponse
                        .newBuilder()
                        .setOrderId(order.getId().toString())
                        .setStatus("CREATED")
                        .build();
                idempotencyStore.complete(claim.recordId(),
                        response.toByteArray(),
                        "orders.v1.CreateOrderResponse");
                yield response;
            }
        };
    }

    private String currentTenantId() {
        // Lấy tenant từ security context đã được xác thực.
        return "tenant-from-auth-context";
    }

    private CreateOrderResponse decodeStoredResponse(byte[] payload) {
        try {
            return CreateOrderResponse.parseFrom(payload);
        } catch (InvalidProtocolBufferException error) {
            throw Status.DATA_LOSS
                    .withDescription("Response idempotency bị hỏng")
                    .withCause(error)
                    .asRuntimeException();
        }
    }
}
```

`IdempotencyStore.claimOrLoad()` phải được triển khai bằng unique constraint và thao tác database atomic như mô tả ở phần trước; không phải một `findByKey()` rồi `save()` thông thường. `complete()` lưu serialized response vào **cùng transaction** với `OrderRepository.save()`. Các kiểu `Claim`, `RequestFingerprint` và repository là abstraction của ứng dụng, cần được hiện thực theo database đang dùng.

Ví dụ dùng `switch` expression của Java hiện đại. Nếu dự án dùng Java cũ hơn, thay bằng switch statement. `currentTenantId()` là điểm tích hợp với security context; không lấy tenant từ request mà chưa xác thực.

## 8. Tác dụng phụ ngoài database

Transaction database không thể rollback một lời gọi HTTP tới payment provider, email service hoặc message broker đã thực hiện thành công. Ví dụ:

1. Service tạo order trong database.
2. Service gọi payment provider và thanh toán thành công.
3. Service crash trước khi lưu idempotency response.
4. Client retry; service có thể gọi payment provider lần nữa.

Để bảo vệ chuỗi side effect:

- Dùng cùng idempotency key khi gọi downstream provider nếu provider hỗ trợ.
- Ghi **transactional outbox** trong cùng transaction với order và idempotency response.
- Worker đọc outbox và phát event; consumer cũng deduplicate theo event ID.
- Lưu trạng thái xử lý và kết quả downstream để có thể tiếp tục sau crash.

Idempotency phải được triển khai xuyên qua ranh giới nơi tác dụng phụ xảy ra. Chỉ lưu request/response trong service đầu tiên không tạo exactly-once cho toàn hệ thống phân tán.

## 9. TTL và chính sách hết hạn

Idempotency record cần retention đủ dài để bao phủ thời gian client có thể retry hoặc người dùng gửi lại thao tác do không nhận được kết quả. Khi hết hạn:

- Client gửi lại key cũ có thể bị coi như thao tác mới nếu record đã bị xóa.
- Không nên xóa record ngay sau khi trả response đầu tiên.
- TTL phải được công bố theo contract và phù hợp với thời gian retry, offline queue và phục hồi client.
- Cleanup nên xóa theo batch, tránh một job xóa lớn gây lock hoặc tải database.

Nếu nghiệp vụ không cho phép tạo trùng trong thời gian dài, có thể cần unique business constraint bổ sung, ví dụ mã đơn hàng ngoài idempotency key. Idempotency retention không thay thế invariant nghiệp vụ lâu dài.

## 10. Kiểm thử idempotency

Các test quan trọng:

| Kịch bản | Assertion |
| --- | --- |
| Cùng key, cùng payload, gọi hai lần tuần tự | Hai response có cùng order ID; chỉ một order được tạo |
| Cùng key, cùng payload, hai request đồng thời | Unique constraint bảo đảm một owner; request còn lại replay kết quả |
| Cùng key, payload khác | Trả lỗi conflict; không tạo side effect thứ hai |
| Khác tenant, cùng key | Hai scope độc lập theo contract |
| Server commit nhưng response bị mất | Retry cùng key trả response đã lưu |
| Transaction đầu rollback | Request sau có thể giành key và thực hiện thao tác |
| Response đã lưu không parse được | Báo lỗi dữ liệu/record; không tạo tác dụng phụ mới |
| Record hết TTL | Hành vi phù hợp retention contract được xác minh |
| Downstream side effect | Outbox/provider idempotency ngăn tác dụng phụ trùng |

Đặc biệt cần test **concurrency** bằng hai request đồng thời và xác minh số bản ghi nghiệp vụ bằng một. Test tuần tự không phát hiện được race condition giữa `SELECT` và `INSERT`.

## 11. Sai lầm thường gặp

1. **Tạo key mới ở mỗi lần retry.** Server sẽ coi mỗi attempt là thao tác mới.
2. **Chỉ lưu key mà không lưu fingerprint.** Cùng key có thể bị dùng cho payload khác và nhận nhầm kết quả.
3. **Dùng SELECT rồi INSERT không có unique constraint.** Hai request đồng thời có thể cùng trở thành owner.
4. **Lưu idempotency record sau khi commit nghiệp vụ ở transaction khác.** Crash ở giữa có thể tạo tác dụng phụ trùng.
5. **Trả `Accepted` trước khi dành được quyền xử lý.** Client tưởng request đã được nhận dù server chưa bảo vệ key.
6. **Không giới hạn TTL hoặc cleanup.** Bảng idempotency có thể tăng vô hạn.
7. **Cho rằng transaction DB bảo vệ được payment/email bên ngoài.** Cần downstream idempotency hoặc outbox.
8. **Gọi idempotency là exactly-once delivery.** Đây là guarantee ở tầng nghiệp vụ trong một scope/retention cụ thể.

## 12. Bài tập vận dụng

Với `orders.v1.OrderService/CreateOrder`:

1. Thêm `idempotency_key` vào request Protobuf và tạo bảng có unique key theo tenant, method và key.
2. Tạo fingerprint từ customer, product và quantity; loại key khỏi fingerprint.
3. Thực hiện insert/claim nguyên tử, tạo order và lưu response trong cùng transaction.
4. Gửi hai request đồng thời cùng key/payload; xác minh chỉ có một order và hai caller nhận cùng order ID.
5. Gửi cùng key với quantity khác; xác minh server trả conflict và không tạo order thứ hai.
6. Mô phỏng response bị mất sau commit; retry cùng key và xác minh response được replay.
7. Thêm transactional outbox cho event `OrderCreated`, kiểm thử consumer không xử lý trùng.

**Tiêu chí hoàn thành:** cùng key và cùng payload trả lại cùng kết quả; cùng key với payload khác bị từ chối; request đồng thời không tạo tác dụng phụ trùng; side effect ngoài database có cơ chế idempotency riêng.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy và giới hạn replay của RPC.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): status kết thúc lời gọi.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction trong ứng dụng Spring.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
