# Mapping not found thành NOT_FOUND

## 1. Vì sao cần ánh xạ not found rõ ràng?

Trong **SPRING_GRPC**, client gọi các RPC để đọc, cập nhật hoặc xóa tài nguyên như account, order, customer hay device. Khi định danh hợp lệ nhưng bản ghi không tồn tại, server cần trả một kết quả nhất quán để client biết tài nguyên được yêu cầu không có.

Ở tầng persistence, tình huống này thường xuất hiện dưới dạng Optional rỗng, query không trả hàng hoặc một exception cụ thể của repository/ORM. Ở tầng gRPC, cách biểu diễn phù hợp thường là status **NOT_FOUND**. Client có thể dựa vào status để hiển thị “không tìm thấy”, bỏ qua tài nguyên đã bị xóa hoặc xử lý quan hệ cha/con không còn tồn tại.

Không nên ánh xạ mọi exception thành NOT_FOUND. Lỗi database, lỗi kết nối, lỗi mapping, quyền truy cập và trạng thái nghiệp vụ không hợp lệ có ý nghĩa khác nhau. Nếu phân loại sai, client sẽ đưa ra hành động sai và hệ thống che giấu lỗi thật.

Bài tập trung vào:

- Nhận diện tài nguyên không tồn tại ở repository và application service.
- Dùng exception nghiệp vụ có kiểu rõ ràng.
- Ánh xạ exception sang gRPC NOT_FOUND tại biên transport.
- Phân biệt NOT_FOUND với PERMISSION_DENIED, FAILED_PRECONDITION và INVALID_ARGUMENT.
- Xử lý tài nguyên lồng nhau, update/delete và race condition.
- Tránh rò rỉ thông tin về tài nguyên hoặc dữ liệu nội bộ.
- Kiểm thử status qua gRPC integration test.

## 2. NOT_FOUND biểu đạt điều gì?

NOT_FOUND có nghĩa tài nguyên được định danh trong request không tồn tại theo contract của API tại thời điểm xử lý.

Ví dụ:

- GetOrder nhận order_id hợp lệ nhưng không có order tương ứng.
- GetDevice nhận device_id không tồn tại.
- GetOrderLine nhận line_id không thuộc order_id được chỉ định.
- Parent resource không tồn tại trong một đường dẫn lồng nhau.
- Một API tra cứu theo external reference không tìm thấy bản ghi tương ứng.

Ví dụ response lỗi:

```text
gRPC status: NOT_FOUND
description: Order not found
```

NOT_FOUND không có nghĩa request sai cú pháp. Nếu order_id rỗng hoặc sai định dạng, đó thường là INVALID_ARGUMENT. Nếu order tồn tại nhưng không thể hủy vì đã SHIPPED, đó thường là FAILED_PRECONDITION.

Hãy xác định tài nguyên và điều kiện tồn tại theo contract. “Không có kết quả” từ một truy vấn phụ không phải lúc nào cũng có nghĩa resource chính không tồn tại; có thể đó là danh sách rỗng hợp lệ.

## 3. Phân biệt lỗi persistence với domain not found

Repository nên biểu diễn việc không có dữ liệu bằng kiểu trả về rõ ràng nếu đó là kết quả bình thường có thể xảy ra.

Ví dụ Spring Data JPA:

```java
public interface OrderRepository
        extends JpaRepository<Order, String> {
}
```

Application service chuyển kết quả repository thành kết quả domain:

```java
@Service
@RequiredArgsConstructor
public class OrderApplicationService {
    private final OrderRepository orders;

    @Transactional(readOnly = true)
    public OrderResult getOrder(String orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() ->
                new ResourceNotFoundException(
                    "Order", orderId
                )
            );

        return OrderResult.from(order);
    }
}
```

findById trả Optional. Khi Optional rỗng, application service ném exception nghiệp vụ ResourceNotFoundException. Exception này diễn đạt một điều kiện domain mà transport layer có thể ánh xạ, đồng thời không buộc application service phụ thuộc gRPC Status.

Không dùng Optional.get() rồi để NoSuchElementException rơi ra ngoài. NoSuchElementException không mô tả loại resource, không cung cấp context hữu ích và dễ bị ánh xạ nhầm với lỗi lập trình.

## 4. Định nghĩa exception nghiệp vụ có kiểu rõ ràng

Một exception có thể mang resource type và identifier nội bộ để log:

```java
public class ResourceNotFoundException
        extends RuntimeException {

    private final String resourceType;
    private final String resourceId;

    public ResourceNotFoundException(
            String resourceType,
            String resourceId) {
        super(resourceType + " not found");
        this.resourceType = resourceType;
        this.resourceId = resourceId;
    }

    public String getResourceType() {
        return resourceType;
    }

    public String getResourceId() {
        return resourceId;
    }
}
```

Application layer có thể dùng exception này trong nhiều adapter như gRPC, REST hoặc message consumer. Không nhúng gRPC StatusRuntimeException vào domain model vì như vậy nghiệp vụ sẽ phụ thuộc transport.

Resource ID trong exception chỉ phục vụ log/diagnostic nội bộ. Không mặc định đưa identifier nhạy cảm hoặc thông tin tenant vào status description trả về client.

Nếu codebase có nhiều loại not-found khác nhau, có thể tạo các exception chuyên biệt như OrderNotFoundException hoặc AccountNotFoundException. Chọn một cách nhất quán để exception mapper không phải phân tích chuỗi message.

## 5. Ánh xạ exception tại biên gRPC

gRPC Java biểu diễn lỗi bằng Status và RuntimeException. Adapter có thể bắt domain exception rồi gọi observer.onError:

```java
@Override
public void getOrder(
        GetOrderRequest request,
        StreamObserver<GetOrderReply> observer) {
    try {
        OrderResult result =
            orderApplicationService.getOrder(
                request.getOrderId()
            );

        GetOrderReply reply = GetOrderReply.newBuilder()
            .setOrderId(result.orderId())
            .setStatus(result.status())
            .build();

        observer.onNext(reply);
        observer.onCompleted();

    } catch (ResourceNotFoundException ex) {
        observer.onError(
            Status.NOT_FOUND
                .withDescription("Order not found")
                .asRuntimeException()
        );
    }
}
```

Chỉ phát response thành công khi application service trả kết quả bình thường. Nếu resource không tồn tại, adapter phát một terminal error bằng onError và không gọi onNext/onCompleted sau đó.

Không lặp cùng một try/catch ở hàng chục service implementation. Trong hệ thống có nhiều RPC, tạo exception mapper hoặc base adapter dùng chung để mọi service ánh xạ domain exception nhất quán. Cơ chế đăng ký mapper phụ thuộc Spring gRPC starter và cách tích hợp gRPC Java của dự án; dù dùng interceptor hay helper, mapping phải nằm ở biên transport.

## 6. Centralized exception mapping

Một mapper tập trung giúp tránh các service trả status khác nhau cho cùng một lỗi:

```java
@Component
public class GrpcExceptionMapper {

    public StatusRuntimeException toStatus(Throwable error) {
        if (error instanceof ResourceNotFoundException) {
            return Status.NOT_FOUND
                .withDescription("Resource not found")
                .asRuntimeException();
        }

        if (error instanceof InvalidCommandException) {
            return Status.INVALID_ARGUMENT
                .withDescription("Invalid request")
                .asRuntimeException();
        }

        if (error instanceof BusinessPreconditionException) {
            return Status.FAILED_PRECONDITION
                .withDescription("Operation is not allowed")
                .asRuntimeException();
        }

        return Status.INTERNAL
            .withDescription("Unexpected server error")
            .asRuntimeException();
    }
}
```

Mapper thực tế có thể nhận cause chain để nhận diện exception đã được Spring dịch, nhưng không nên tìm một từ khóa như “not found” trong message. Phân loại theo type exception đáng tin cậy hơn.

Không ánh xạ mọi DataAccessException, SQLException hoặc RuntimeException thành NOT_FOUND. Database unavailable, timeout, connection pool exhaustion và SQL syntax error không phải là resource missing; lỗi không dự kiến nên được log và ánh xạ theo policy server, thường là INTERNAL hoặc UNAVAILABLE tùy nguyên nhân.

## 7. Phân biệt NOT_FOUND với các status gần nghĩa

| Tình huống | Status thường dùng | Lý do |
| --- | --- | --- |
| ID hợp lệ nhưng resource không tồn tại | NOT_FOUND | Tài nguyên không được tìm thấy |
| ID thiếu, rỗng hoặc sai định dạng | INVALID_ARGUMENT | Request không hợp lệ |
| Resource tồn tại nhưng user không có quyền | PERMISSION_DENIED | Tài nguyên có nhưng caller không được phép |
| Resource tồn tại nhưng trạng thái không cho phép thao tác | FAILED_PRECONDITION | Cần thay đổi trạng thái trước |
| Concurrent update làm version stale | ABORTED | Cần đọc lại và retry workflow |
| Database/service tạm thời không sẵn sàng | UNAVAILABLE | Lỗi hạ tầng có thể phục hồi |
| Query vượt deadline | DEADLINE_EXCEEDED | Hết ngân sách thời gian |

Không chọn NOT_FOUND chỉ vì muốn client ngừng retry. Status phải phản ánh nguyên nhân thật và contract đã công bố.

Một số hệ thống cố ý trả NOT_FOUND khi caller không được phép biết resource có tồn tại hay không. Đây là chính sách che giấu sự tồn tại; cần áp dụng nhất quán và được quyết định ở authorization boundary, không phải do repository tùy tiện đổi lỗi.

## 8. Validate identifier trước khi truy vấn

Phân biệt identifier không hợp lệ với identifier hợp lệ nhưng không có bản ghi:

```java
public OrderResult getOrder(String orderId) {
    if (orderId == null || orderId.isBlank()) {
        throw new InvalidCommandException(
            "order_id is required"
        );
    }

    if (!orderId.matches("[A-Za-z0-9-]{1,64}")) {
        throw new InvalidCommandException(
            "order_id has invalid format"
        );
    }

    Order order = orders.findById(orderId)
        .orElseThrow(() ->
            new ResourceNotFoundException("Order", orderId)
        );

    return OrderResult.from(order);
}
```

Định dạng regex chỉ là ví dụ; validation thực tế phải theo kiểu identifier trong contract. Nếu dùng UUID, parse thành UUID trước khi query. Không query database với input sai định dạng rồi trả NOT_FOUND vì điều đó làm client khó phân biệt lỗi đầu vào với resource không tồn tại.

Validation ở Proto3 cần lưu ý scalar string mặc định là chuỗi rỗng; việc field có mặt hay không có thể không được biểu diễn nếu dùng implicit presence. Application layer vẫn cần kiểm tra giá trị và semantics.

## 9. Resource lồng nhau và quan hệ cha/con

Một RPC có thể nhận cả parent ID và child ID, ví dụ GetOrderLine(order_id, line_id). Có nhiều trường hợp:

- Order không tồn tại.
- Order tồn tại nhưng line không tồn tại.
- Line tồn tại nhưng thuộc order khác.
- Caller không được phép truy cập order hoặc line.

Nếu contract coi line là tài nguyên con của order, cả “line không tồn tại” và “line không thuộc order này” thường có thể trả NOT_FOUND để không tiết lộ quan hệ giữa các resource.

Ví dụ truy vấn scoped:

```java
Optional<OrderLine> line =
    orderLines.findByOrderIdAndId(orderId, lineId);

OrderLine found = line.orElseThrow(() ->
    new ResourceNotFoundException("OrderLine", lineId)
);
```

Truy vấn scoped tránh lấy line theo ID rồi vô tình trả dữ liệu của một order khác. Tuy nhiên, nếu cần phân biệt parent không tồn tại với child không tồn tại, hãy làm theo contract và policy bảo mật.

Với resource nhiều tenant, mọi query cần scope theo tenant/owner. Không chỉ tìm theo ID toàn cục rồi kiểm tra quyền sau khi đã lộ dữ liệu vào log hoặc response mapping.

## 10. Mapping cho get, update và delete

### Get

Dùng findById/Optional. Nếu không có resource, ném domain not-found exception và trả NOT_FOUND. Nếu có, mapping sang response.

### Update

Nếu API là update resource hiện hữu, không tìm thấy resource thì thường trả NOT_FOUND. Nếu API là upsert, việc không có resource có thể là nhánh tạo mới và không phải lỗi. Contract phải nói rõ semantics.

Trong transaction, đọc entity, kiểm tra quyền và precondition, cập nhật rồi commit. Nếu row biến mất do concurrent delete giữa lúc đọc và ghi, persistence layer có thể báo stale state/optimistic lock. Không tự động coi mọi optimistic lock exception là NOT_FOUND; đó có thể là concurrent update và cần ABORTED. Chỉ phân loại resource disappearance thành NOT_FOUND khi có đủ bằng chứng và policy rõ ràng.

### Delete

Delete có hai contract phổ biến:

- **Strict delete:** resource không tồn tại thì trả NOT_FOUND.
- **Idempotent delete:** resource không tồn tại vẫn coi thao tác hoàn tất, trả success hoặc empty response.

Chọn một semantics và giữ nhất quán. Không dựa vào hành vi mặc định của deleteById mà chưa kiểm tra Spring Data version/repository contract; một số API xóa có thể im lặng khi ID không tồn tại.

Nếu cần strict delete, có thể tìm resource trong transaction rồi xóa; hoặc dùng câu DELETE có điều kiện và kiểm tra affected row count. Với cạnh tranh delete, xử lý race theo semantics đã công bố.

## 11. Không biến database outage thành NOT_FOUND

Một số code sai bắt exception rộng rồi trả NOT_FOUND:

```java
try {
    return repository.findById(id)
        .orElseThrow(() -> new ResourceNotFoundException("Order", id));
} catch (RuntimeException ex) {
    throw new ResourceNotFoundException("Order", id);
}
```

Cách này che giấu connection failure, timeout, SQL error, mapping bug và cả lỗi lập trình. Client sẽ nghĩ tài nguyên không tồn tại và có thể xóa cache hoặc bỏ qua dữ liệu.

Chỉ tạo ResourceNotFoundException khi truy vấn hoàn tất bình thường và kết quả thật sự không có. Nếu database không trả lời, giữ nguyên lỗi persistence để exception mapper phân loại thành lỗi hạ tầng. Log phải giữ cause chain đầy đủ.

## 12. Bảo mật và information disclosure

NOT_FOUND có thể tiết lộ rằng một ID không tồn tại. Với API đa tenant hoặc tài nguyên nhạy cảm, chính sách cần xác định:

- Caller đã authenticated chưa?
- Caller có quyền đọc loại resource này không?
- Có được phép phân biệt “không tồn tại” và “tồn tại nhưng không thuộc tenant” không?
- Có cần trả NOT_FOUND cho cả resource ngoài phạm vi để tránh enumeration không?

Nếu policy yêu cầu che giấu existence, authorization layer có thể trả cùng một response NOT_FOUND cho resource không tồn tại và resource ngoài phạm vi. Nhưng log nội bộ vẫn cần phân loại nguyên nhân thật, có kiểm soát quyền truy cập.

Không đưa resource ID nhạy cảm, tenant ID, SQL hoặc stack trace vào status description. Dùng correlation ID để liên kết log với RPC. Authentication/authorization phải được thực hiện trước khi replay cached result hoặc trả dữ liệu.

## 13. Kiểm thử mapping NOT_FOUND

Cần kiểm tra cả application behavior và gRPC wire status:

| Test | Điều cần xác nhận |
| --- | --- |
| Get resource tồn tại | Trả response bình thường |
| Get ID hợp lệ nhưng không có row | Client nhận NOT_FOUND |
| ID rỗng/sai format | Client nhận INVALID_ARGUMENT |
| Resource tồn tại nhưng không có quyền | PERMISSION_DENIED hoặc policy hide-existence đã định |
| Parent/child không khớp | NOT_FOUND theo nested-resource contract |
| Update resource không tồn tại | NOT_FOUND nếu update strict |
| Delete resource không tồn tại | Đúng strict/idempotent delete semantics |
| Database connection failure | Không bị ánh xạ thành NOT_FOUND |
| Optimistic lock conflict | ABORTED, không phải NOT_FOUND mặc định |
| Status description | Không chứa SQL/stack trace/secret |

Ví dụ integration test với blocking stub:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> blockingStub.getOrder(
        GetOrderRequest.newBuilder()
            .setOrderId("missing-order")
            .build()
    )
);

assertEquals(
    Status.Code.NOT_FOUND,
    Status.fromThrowable(error).getCode()
);
```

Test qua gRPC server thật giúp xác nhận exception mapper, adapter và transport cùng tạo ra status code mong đợi. Unit test chỉ gọi mapper không đủ chứng minh server thực sự gửi đúng status.

## 14. Checklist review

- Repository biểu diễn absence bằng Optional hoặc kết quả rõ ràng.
- Application service ném typed domain exception khi resource thực sự không tồn tại.
- Không dùng Optional.get()/NoSuchElementException làm contract.
- Exception mapper ở biên gRPC ánh xạ đúng NOT_FOUND.
- Không map mọi DataAccessException/RuntimeException thành NOT_FOUND.
- INVALID_ARGUMENT dùng cho identifier/request sai định dạng.
- PERMISSION_DENIED và hide-existence policy được xác định rõ.
- FAILED_PRECONDITION dùng cho resource tồn tại nhưng trạng thái không phù hợp.
- ABORTED dùng cho concurrency conflict theo contract.
- Nested resource query được scope theo parent và tenant.
- Get/update/delete có semantics not-found rõ ràng; strict và idempotent delete không bị trộn lẫn.
- Không phát response thành công trước khi application service hoàn tất.
- Status description không làm lộ dữ liệu nội bộ.
- Có gRPC integration tests cho resource missing và các lỗi dễ nhầm.

Trong **SPRING_GRPC**, NOT_FOUND là cách biểu diễn một tài nguyên không tồn tại theo contract của RPC. Hãy phát hiện absence ở repository, chuyển thành typed domain exception trong application service và ánh xạ tập trung tại biên gRPC. Phân biệt rõ request sai, thiếu quyền, trạng thái nghiệp vụ không hợp lệ, concurrency conflict và database outage để client có thể xử lý đúng, đồng thời tránh làm lộ thông tin tài nguyên.
