# Deadline propagation qua nested call

Một request thường đi qua nhiều service trước khi có kết quả: client gọi OrderService, service này gọi InventoryService, rồi có thể gọi tiếp PricingService hoặc cơ sở dữ liệu. Nếu mỗi tầng tự đặt timeout mới mà không quan tâm thời gian đã trôi qua, tổng thời gian xử lý có thể vượt xa giới hạn mà client chấp nhận.

**Deadline propagation** là việc giữ ngân sách thời gian của lời gọi cha khi tạo các lời gọi gRPC lồng bên trong. Trong **Spring gRPC** với gRPC Java, deadline và trạng thái cancellation được gắn với **io.grpc.Context** của RPC hiện tại. Khi service tạo outbound RPC trong context đó, gRPC có thể truyền deadline còn lại sang service con. Nhờ vậy, các tầng cùng tuân theo một giới hạn cuối thay vì mỗi tầng bắt đầu một đồng hồ độc lập.

## 1. Vì sao nested call cần propagation?

Giả sử client cho phép toàn bộ thao tác đặt hàng hoàn tất trong 900 ms. OrderService cần kiểm tra tồn kho, tính giá và lưu đơn. Nếu mỗi service con đều được cấp timeout 900 ms mới, các bước tuần tự có thể tiêu thụ gần 2,7 giây hoặc hơn.

~~~mermaid
flowchart TD
    C["Client<br/>deadline tổng: 900 ms"] --> O["OrderService"]
    O --> I["InventoryService"]
    O --> P["PricingService"]
    O --> D["Order database"]
    I --> R["Kết quả về OrderService"]
    P --> R
    D --> R
    R --> C
~~~

Ví dụ ngân sách tuần tự:

| Bước | Thời gian đã dùng | Ngân sách còn lại xấp xỉ |
| --- | ---: | ---: |
| Client bắt đầu | 0 ms | 900 ms |
| Truyền request và vào OrderService | 80 ms | 820 ms |
| Kiểm tra tồn kho | 220 ms | 600 ms |
| Tính giá | 140 ms | 460 ms |
| Ghi đơn và trả response | 300 ms | 160 ms |

Các con số chỉ minh họa cách phân bổ. Điểm cốt lõi: **service con dùng phần thời gian còn lại của request cha**, không được tự khởi động lại toàn bộ ngân sách.

## 2. Deadline nằm trong Context của RPC

Ở client, đặt deadline trên stub:

~~~java
GetOrderResponse response = orderStub
    .withDeadlineAfter(900, TimeUnit.MILLISECONDS)
    .getOrder(request);
~~~

Khi request đến server, gRPC Java tạo context cho lời gọi. Trong handler, có thể đọc deadline và thời gian còn lại:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (deadline != null) {
    long remainingMs =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);
    if (remainingMs <= 0 || rpcContext.isCancelled()) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("request budget exhausted")
            .asRuntimeException();
    }
}
~~~

Context.current() là context đang gắn với callback hiện tại. getDeadline() có thể trả về null nếu lời gọi không có deadline. Với các API cần giới hạn thời gian, client hoặc gateway nên đặt deadline rõ ràng; server cũng có thể áp dụng chính sách mặc định phù hợp nếu hệ thống yêu cầu.

Context còn mang trạng thái cancellation. Khi deadline hết hoặc client chủ động hủy RPC, context được đánh dấu cancelled. Các bước xử lý tiếp theo nên dừng nếu không còn giá trị cho request ban đầu.

## 3. gRPC Java tự truyền deadline khi gọi service con

Khi một outbound gRPC call được tạo trong context của RPC server hiện tại, gRPC Java hỗ trợ **deadline propagation**: deadline cha được áp dụng cho lời gọi con. Vì vậy, nếu OrderService gọi InventoryService ngay trong handler đang chạy với context của request, không cần tự đọc header grpc-timeout rồi gắn lại vào metadata.

Ví dụ:

~~~java
@Service
public class OrderServiceImpl
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub;

    public OrderServiceImpl(
            InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub) {
        this.inventoryStub = inventoryStub;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        try {
            InventoryResponse inventory =
                inventoryStub.checkAvailability(
                    CheckAvailabilityRequest.newBuilder()
                        .setProductId(request.getProductId())
                        .setQuantity(request.getQuantity())
                        .build());

            // Tiếp tục nghiệp vụ với ngân sách còn lại của RPC cha.
            GetOrderResponse response = buildOrderResponse(request, inventory);
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (StatusRuntimeException ex) {
            responseObserver.onError(ex);
        }
    }
}
~~~

Các hàm buildOrderResponse(...) và cấu hình constructor được lược giản theo ứng dụng. Điều quan trọng là lời gọi inventoryStub.checkAvailability(...) được tạo trong context của RPC cha; deadline và cancellation của context đó tiếp tục chi phối lời gọi con.

Không phải tạo một ManagedChannel mới cho mỗi nested call. Channel nên được quản lý và tái sử dụng; stub có thể được tạo/cấu hình từ channel đó. Deadline là thuộc tính của **lời gọi**, không phải tuổi thọ của channel.

## 4. Đặt deadline riêng ngắn hơn cho một bước downstream

Propagation giữ giới hạn cha, nhưng một bước con có thể cần ngân sách **ngắn hơn**. Ví dụ, OrderService dành tối đa 200 ms cho kiểm tra tồn kho để còn thời gian tính giá và ghi đơn.

~~~java
var boundedInventoryStub = inventoryStub
    .withDeadlineAfter(200, TimeUnit.MILLISECONDS);

InventoryResponse inventory =
    boundedInventoryStub.checkAvailability(request);
~~~

Deadline hiệu lực của outbound call không được vượt deadline đang có trong context cha. Trong gRPC Java, giới hạn từ CallOptions và deadline context được kết hợp theo giới hạn sớm hơn. Vì vậy deadline riêng ngắn hơn có thể siết chặt bước con; một deadline mới dài hơn không nên được dùng để kéo dài request cha.

Nếu cần chủ động phân bổ ngân sách, hãy đọc thời gian còn lại và dành phần dự phòng cho xử lý sau downstream:

~~~java
Deadline parent = Context.current().getDeadline();
long childLimit = TimeUnit.MILLISECONDS.toNanos(200);
long responseReserve = TimeUnit.MILLISECONDS.toNanos(40);

if (parent != null) {
    long remaining = parent.timeRemaining(TimeUnit.NANOSECONDS);
    childLimit = Math.min(childLimit, remaining - responseReserve);
}

if (childLimit <= 0) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("insufficient budget for inventory")
        .asRuntimeException();
}

var childStub = inventoryStub.withDeadlineAfter(
    childLimit, TimeUnit.NANOSECONDS);
InventoryResponse inventory = childStub.checkAvailability(request);
~~~

Phần dự phòng 40 ms là ví dụ; cần hiệu chỉnh theo latency của service cha, serialization và thời gian trả response. Nếu không có deadline cha, hệ thống vẫn có thể áp dụng giới hạn cục bộ 200 ms.

## 5. Nested call tuần tự và gọi song song

### Gọi tuần tự

Nếu service cha gọi lần lượt InventoryService rồi PricingService, mỗi bước tiêu thụ một phần ngân sách. Lời gọi sau tự nhận thời gian còn lại trong context; không cấp lại thời gian ban đầu.

~~~java
InventoryResponse inventory =
    inventoryStub.checkAvailability(inventoryRequest);

PriceResponse price =
    pricingStub.calculatePrice(priceRequest);
~~~

Nếu kiểm tra tồn kho mất 300 ms trong ngân sách 900 ms, bước tính giá chỉ còn tối đa khoảng 600 ms, chưa kể phần dự phòng cho response cuối.

### Gọi song song

Nếu hai bước độc lập, service cha có thể gọi chúng đồng thời. Mỗi lời gọi con vẫn bị ràng buộc bởi deadline cha, nhưng thời gian tổng thường gần bằng bước chậm nhất thay vì tổng thời gian hai bước.

~~~java
Context parentContext = Context.current();
Executor contextExecutor =
    parentContext.fixedContextExecutor(applicationExecutor);

CompletableFuture<InventoryResponse> inventoryFuture =
    CompletableFuture.supplyAsync(
        () -> inventoryStub.checkAvailability(inventoryRequest),
        contextExecutor);

CompletableFuture<PriceResponse> priceFuture =
    CompletableFuture.supplyAsync(
        () -> pricingStub.calculatePrice(priceRequest),
        contextExecutor);

InventoryResponse inventory = inventoryFuture.join();
PriceResponse price = priceFuture.join();
~~~

Ví dụ dùng cùng context cho hai tác vụ và một executor do ứng dụng quản lý. Cần xử lý CompletionException, timeout và cancellation; khi một nhánh thất bại hoặc request cha bị hủy, nên hủy nhánh còn lại nếu không còn cần thiết. Không dùng một executor không giới hạn cho fan-out lớn.

## 6. Giữ Context khi chuyển thread

Một lỗi phổ biến là nhận RPC trong thread có context, sau đó đẩy công việc sang executor hoặc CompletableFuture mà không truyền context. Thread mới có thể không có deadline cha; outbound RPC được tạo ở đó không còn nhận đúng ngân sách và cancellation như mong đợi.

Hãy capture context khi còn ở trong callback gRPC:

~~~java
Context captured = Context.current();

applicationExecutor.execute(captured.wrap(() -> {
    // Context.current() trong task là context của RPC cha.
    inventoryStub.checkAvailability(
        inventoryRequest,
        inventoryResponseObserver);
}));
~~~

Hoặc dùng executor gắn context đã capture:

~~~java
Context rpcContext = Context.current();
Executor contextExecutor =
    rpcContext.fixedContextExecutor(applicationExecutor);

contextExecutor.execute(() -> {
    pricingStub.calculatePrice(
        priceRequest,
        priceResponseObserver);
});
~~~

Context.currentContextExecutor(delegate) cũng có thể dùng khi muốn tạo executor gắn với context hiện tại tại thời điểm gọi API. Dùng fixedContextExecutor trên context đã capture giúp thể hiện rõ context nào được truyền qua ranh giới bất đồng bộ.

Context nên sống trong phạm vi công việc của RPC. Không lưu context của request vào singleton hoặc queue dài hạn để chạy công việc sau khi RPC kết thúc. Tác vụ nền độc lập cần có vòng đời và deadline riêng, không phụ thuộc vào context đã hết hạn của request cũ.

## 7. Cancellation cũng phải lan xuống downstream

Deadline hết là một nguyên nhân dẫn tới cancellation; client cũng có thể hủy RPC chủ động. Khi context cha bị hủy, các lời gọi con gắn với context đó có thể bị hủy theo. Tuy nhiên, tác vụ Java tự viết, truy vấn database hoặc công việc trong executor chỉ dừng nếu API của chúng hỗ trợ cancellation hoặc ứng dụng chủ động kiểm tra tín hiệu.

Có thể đăng ký listener:

~~~java
Context rpcContext = Context.current();
rpcContext.addListener(cancelled -> {
    downstreamFuture.cancel(true);
    releaseTemporaryResources();
}, Runnable::run);
~~~

Tên downstreamFuture và releaseTemporaryResources() đại diện cho tài nguyên của ứng dụng. Cleanup phải idempotent, an toàn khi xảy ra đồng thời với đường hoàn tất bình thường và không chặn callback quá lâu.

**Cancellation không phải rollback.** Nếu service con đã commit dữ liệu trước khi nhận tín hiệu hủy, tác dụng phụ vẫn có thể tồn tại. Với command có thể được retry, cần idempotency key hoặc operation ID để tránh tạo tác động trùng.

## 8. Không tự truyền grpc-timeout bằng metadata

grpc-timeout là header thuộc giao thức gRPC. Client library tạo header từ deadline; server library diễn giải nó thành deadline trong context. Khi tạo nested call trong context đúng, gRPC Java xử lý propagation.

Không nên:

- Đọc chuỗi grpc-timeout từ metadata rồi copy nguyên văn sang lời gọi con.
- Tự đặt lại timeout bằng toàn bộ giá trị ban đầu ở mỗi service.
- Truyền deadline qua custom metadata như một field nghiệp vụ.
- Bỏ context khi chuyển thread rồi kỳ vọng gRPC tự biết request cha.

Metadata nghiệp vụ như authorization, tenant ID, request ID và trace context là vấn đề riêng. Chúng có thể được truyền bằng metadata/interceptor, còn deadline nên được quản lý bằng API deadline và context của gRPC.

## 9. Kiểm thử deadline propagation

Một test chỉ xác minh client nhận DEADLINE_EXCEEDED chưa chứng minh deadline đã truyền đúng qua nested call. Cần kiểm tra cả service cha, service con và ranh giới executor:

1. Client đặt deadline tổng ngắn và gọi service cha.
2. Service cha đọc Context.current().getDeadline() và ghi nhận thời gian còn lại.
3. Service cha gọi service con; service con xác nhận có deadline và ngân sách nhỏ hơn hoặc bằng ngân sách cha tại thời điểm nhận.
4. Thử chuyển lời gọi con sang executor có context và executor không có context để phát hiện mất propagation.
5. Cho service con xử lý chậm hơn deadline; xác minh client nhận status timeout và tác vụ downstream được hủy nếu hỗ trợ.
6. Kiểm tra cleanup và bảo đảm timeout sau commit không tạo dữ liệu trùng khi retry.

Có thể dùng gRPC in-process cho test service-to-service và một executor điều khiển được. Dùng latch hoặc controllable future để tạo tình huống chậm có thể lặp lại; tránh phụ thuộc vào Thread.sleep dài. Integration test Spring cần khởi động context để xác nhận bean, interceptor và channel thực tế được cấu hình đúng.

## 10. Quan sát ngân sách qua chuỗi service

Theo dõi các chỉ số theo trace ID và RPC method:

- Deadline còn lại khi request đến từng service.
- Thời gian xử lý nội bộ và thời gian chờ từng downstream.
- Số nested call bắt đầu khi ngân sách còn quá ít.
- Tỷ lệ DEADLINE_EXCEEDED và CANCELLED ở từng tầng.
- Số tác vụ downstream còn chạy sau khi request cha kết thúc.
- Thời gian cleanup và tỷ lệ retry.

Nếu service cha còn nhiều thời gian nhưng service con thường xuyên timeout, điều tra latency hoặc giới hạn riêng của service con. Nếu request đến service cha đã gần hết deadline, vấn đề có thể nằm ở gateway, queue hoặc tầng trước đó. Trace phân tách từng span giúp xác định chính xác nơi tiêu thụ ngân sách.

## 11. Ghi nhớ và tự kiểm tra

**Deadline propagation qua nested call** giữ một giới hạn thời gian chung từ client qua service cha đến các service con. gRPC Java gắn deadline/cancellation vào Context; outbound RPC được tạo trong context đó có thể kế thừa giới hạn. Khi đặt deadline con, chỉ nên siết chặt ngân sách; khi chuyển thread, cần truyền context tường minh.

Tự kiểm tra:

1. Vì sao mỗi service con không nên nhận lại toàn bộ timeout ban đầu?
2. gRPC Java sử dụng Context như thế nào để truyền deadline và cancellation?
3. Vì sao outbound call tạo từ thread pool không có context có thể mất deadline cha?
4. Khi hai downstream call chạy song song, ngân sách deadline được tính như thế nào?
5. Vì sao cancellation của RPC không đảm bảo rollback transaction đã commit?

Giữ deadline nhất quán qua nested call giúp Spring gRPC giới hạn thời gian xử lý xuyên suốt, tránh công việc downstream tiếp tục sau khi client đã bỏ cuộc và làm cho hành vi timeout có thể quan sát, kiểm thử và vận hành được.
