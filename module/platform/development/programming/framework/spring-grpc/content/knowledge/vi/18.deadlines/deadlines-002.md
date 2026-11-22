# Deadline truyền từ client đến server

Một lời gọi gRPC không nên chờ vô hạn để nhận kết quả. **Deadline** xác định thời điểm muộn nhất mà client chấp nhận lời gọi hoàn tất. Khi client gửi RPC, gRPC truyền ngân sách thời gian cùng lời gọi để server biết còn bao lâu, có nên tiếp tục xử lý hay dừng công việc. Nếu server gọi thêm service downstream, deadline và tín hiệu hủy cũng cần tiếp tục chi phối các lời gọi đó.

Trong **Spring gRPC**, ứng dụng Java thường đọc deadline của RPC hiện tại qua **io.grpc.Context**. gRPC Java dùng context của lời gọi khi tạo outbound RPC, giúp deadline và cancellation đi tiếp theo chuỗi xử lý. Hiểu cơ chế này giúp tránh việc service con tiếp tục làm việc lâu hơn thời gian client đã cho phép.

## 1. Luồng deadline từ client đến server

Client đặt deadline trên stub. Khi gRPC gửi lời gọi qua HTTP/2, deadline được truyền trong metadata giao thức bằng header **grpc-timeout** dưới dạng thời lượng còn lại. Server nhận lời gọi, diễn giải thời lượng này thành deadline trong context của RPC.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as gRPC transport
    participant S as Spring gRPC server
    C->>C: Đặt deadline 800 ms
    C->>T: Gửi RPC + grpc-timeout
    T->>S: Chuyển request và timeout còn lại
    S->>S: Tạo Context có deadline
    S->>S: Xử lý trong ngân sách còn lại
    alt Hoàn tất kịp hạn
        S-->>C: Response + grpc-status OK
    else Deadline hết
        T-->>C: DEADLINE_EXCEEDED
        T-->>S: Hủy RPC / Context cancelled
    end
~~~

Ví dụ, client cấp 800 ms. Nếu request mất 100 ms để truyền và server nhận được sau khoảng 100 ms, server chỉ còn xấp xỉ 700 ms, chưa tính thời gian xử lý và trả response. **Server không nhận một ngân sách mới 800 ms** khi request đến nơi.

gRPC truyền thời lượng còn lại thay vì phụ thuộc vào đồng hồ tuyệt đối của hai máy. Điều này giảm vấn đề lệch giờ giữa client và server. Header grpc-timeout là chi tiết giao thức do gRPC quản lý; ứng dụng không nên tự tạo hoặc sao chép header này như metadata nghiệp vụ.

## 2. Đặt deadline ở client

Với gRPC Java, dùng **withDeadlineAfter** để tạo stub có giới hạn thời gian:

~~~java
import java.util.concurrent.TimeUnit;

GetOrderRequest request = GetOrderRequest.newBuilder()
    .setOrderId("order-2048")
    .build();

GetOrderResponse response = orderStub
    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
    .getOrder(request);
~~~

Deadline được tính cho **toàn bộ RPC**: thời gian chờ tài nguyên, truyền request, xử lý server và chờ response. Nó không phải thời gian xử lý riêng ở server. Mỗi lần gọi cần ngân sách phù hợp với yêu cầu nghiệp vụ; không nên đặt một timeout quá dài cho mọi method.

Nếu client không đặt deadline, lời gọi có thể chờ lâu hơn dự kiến khi server hoặc network gặp sự cố. Nên đặt deadline rõ ràng cho các lời gọi phụ thuộc vào trải nghiệm người dùng hoặc SLA.

## 3. Server nhận deadline qua Context

Khi gRPC Java dispatch một RPC vào service, context của lời gọi được gắn với luồng thực thi callback. Server có thể đọc deadline và thời gian còn lại:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (deadline != null) {
    long remainingMs =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);

    if (remainingMs <= 0 || rpcContext.isCancelled()) {
        // Không bắt đầu thêm công việc.
        return;
    }
}
~~~

Nếu deadline là null, client hoặc tầng gọi phía trước không cung cấp deadline tường minh. Với API cần thời gian phản hồi có giới hạn, server có thể áp dụng chính sách mặc định ở tầng client hoặc gateway. Không nên tự suy ra rằng một lời gọi không có deadline sẽ tự kết thúc sau một khoảng thời gian cụ thể.

Context còn mang trạng thái cancellation. Khi deadline hết hoặc client chủ động hủy RPC, context được đánh dấu cancelled. Server nên kiểm tra trạng thái trước khi bắt đầu bước xử lý tốn kém và truyền tín hiệu dừng đến các tác vụ có thể hủy.

## 4. Deadline tiếp tục chi phối lời gọi downstream

Giả sử client gọi OrderService, rồi OrderService gọi InventoryService. Nếu deadline ban đầu là 800 ms và OrderService đã dùng 250 ms, lời gọi kiểm tra tồn kho chỉ còn tối đa khoảng 550 ms, đồng thời cần giữ một phần ngân sách để OrderService hoàn tất và trả response.

~~~mermaid
flowchart LR
    A["Client<br/>800 ms"] --> B["OrderService<br/>dùng 250 ms"]
    B --> C["InventoryService<br/>ngân sách còn lại"]
    C --> D["Database<br/>dùng phần còn lại"]
    D --> E["Response trước deadline"]
~~~

Trong gRPC Java, outbound call được tạo trong context hiện hành có thể kế thừa deadline và cancellation của RPC cha. Nếu code đang chạy trong context của request, không cần tự đọc rồi sao chép grpc-timeout vào metadata. Có thể đặt deadline tường minh ngắn hơn cho một bước downstream; ngân sách hiệu lực không nên vượt deadline cha.

Ví dụ giới hạn lời gọi tồn kho tối đa 200 ms:

~~~java
var inventoryCall = inventoryStub
    .withDeadlineAfter(200, TimeUnit.MILLISECONDS);

InventoryResponse inventory =
    inventoryCall.checkAvailability(inventoryRequest);
~~~

Giới hạn 200 ms là ngân sách riêng của bước downstream. Nếu deadline còn lại của request cha ngắn hơn, context cha vẫn phải chi phối lời gọi; việc đặt timeout dài hơn không được dùng để kéo dài toàn bộ request ban đầu.

Trong code thực tế, nên dành phần dự phòng cho bước xử lý còn lại:

~~~java
Deadline parentDeadline = Context.current().getDeadline();
long childBudgetNanos = TimeUnit.MILLISECONDS.toNanos(200);
long responseReserveNanos = TimeUnit.MILLISECONDS.toNanos(30);

if (parentDeadline != null) {
    long remaining = parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);
    childBudgetNanos = Math.min(
        childBudgetNanos,
        remaining - responseReserveNanos);
}

if (childBudgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("not enough time for inventory lookup")
        .asRuntimeException();
}

var boundedStub = inventoryStub.withDeadlineAfter(
    childBudgetNanos, TimeUnit.NANOSECONDS);
InventoryResponse result =
    boundedStub.checkAvailability(inventoryRequest);
~~~

Phần dự phòng 30 ms chỉ là ví dụ. Cần chọn dựa trên latency thực tế của OrderService và chi phí serialize/response. Nếu không có deadline cha, ví dụ dùng ngân sách cục bộ 200 ms.

## 5. Context có thể mất khi chuyển thread

Deadline propagation dựa vào **Context.current()**. Khi xử lý đồng bộ trong callback gRPC, context của RPC hiện tại được gắn vào thread. Nhưng nếu ứng dụng chuyển công việc sang executor hoặc thread pool, context không tự xuất hiện trong mọi thread tùy ý.

Nếu outbound RPC được tạo trong thread không có context cha, lời gọi đó có thể không kế thừa deadline/cancellation như mong đợi. Hãy capture context hiện tại và truyền nó qua ranh giới bất đồng bộ:

~~~java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    // Context.current() bên trong task là context đã capture.
    inventoryStub.checkAvailability(
        inventoryRequest,
        inventoryResponseObserver);
}));
~~~

Hoặc tạo executor tự động gắn context tại thời điểm submit:

~~~java
Executor contextAwareExecutor =
    Context.currentContextExecutor(applicationExecutor);

contextAwareExecutor.execute(() -> {
    inventoryStub.checkAvailability(
        inventoryRequest,
        inventoryResponseObserver);
});
~~~

Context có thể được capture để truyền qua callback, nhưng không nên giữ nó lâu hơn vòng đời RPC. Khi request cha bị hủy, task con cần quan sát cancellation và dừng; không đưa công việc của request đã hết hạn vào một queue nền để xử lý như thể nó vẫn còn hiệu lực.

Với Spring, các executor do ứng dụng quản lý vẫn cần được cấu hình rõ ràng. Không giả định mọi tác vụ bất đồng bộ hoặc callback của thư viện đều tự động truyền gRPC Context nếu chưa xác minh cơ chế tích hợp.

## 6. Cancellation đi cùng deadline

Deadline hết là một nguyên nhân dẫn tới cancellation, nhưng client cũng có thể chủ động hủy RPC. Khi context bị cancelled, server nên:

- Ngừng bắt đầu các bước downstream mới.
- Hủy future, task hoặc subscription nếu API hỗ trợ.
- Dừng producer đang phát dữ liệu cho streaming RPC.
- Giải phóng queue, file tạm và tài nguyên đang giữ.
- Không gửi thêm response sau khi RPC đã kết thúc.

Có thể đăng ký listener để phản ứng với cancellation:

~~~java
Context rpcContext = Context.current();
rpcContext.addListener(cancelled -> {
    downstreamFuture.cancel(true);
    releaseTemporaryResources();
}, Runnable::run);
~~~

Tên downstreamFuture và releaseTemporaryResources() đại diện cho tài nguyên của ứng dụng. Cleanup phải an toàn khi được gọi đồng thời với đường hoàn tất bình thường; cần tránh giải phóng hai lần hoặc để callback cleanup gây chặn lâu.

**Cancellation không phải rollback.** Nếu một transaction đã commit trước khi deadline hết, dữ liệu đã ghi vẫn tồn tại. Deadline chỉ giới hạn thời gian chờ và phát tín hiệu dừng; tính nguyên tử và phục hồi tác dụng phụ phải được xử lý ở tầng nghiệp vụ.

## 7. grpc-timeout không phải metadata nghiệp vụ

Header **grpc-timeout** thuộc giao thức gRPC. gRPC client tạo giá trị này từ deadline; server đọc và chuyển thành deadline của RPC. Ứng dụng thường không cần tự thêm header này bằng Metadata hoặc interceptor.

Metadata nghiệp vụ như authorization, tenant ID, request ID và trace context là các thông tin khác. Chúng có thể được truyền qua metadata/interceptor theo chính sách của hệ thống, nhưng không thay thế deadline. Cũng không nên copy một giá trị timeout cũ sang request downstream, vì thời gian đã trôi qua; gRPC cần truyền ngân sách còn lại.

Khi quan sát network trace, có thể thấy grpc-timeout trong request headers. Giá trị có thể dùng đơn vị thời gian khác nhau theo quy tắc giao thức. Không nên giả định luôn là milliseconds hoặc so sánh trực tiếp một chuỗi header với đồng hồ máy chủ.

## 8. Deadline propagation với streaming RPC

Với server streaming, client streaming và bidirectional streaming, deadline vẫn thuộc **toàn bộ RPC**:

- **Server streaming:** giới hạn toàn bộ thời gian subscription và nhận response.
- **Client streaming:** giới hạn thời gian gửi request cùng lúc chờ kết quả cuối.
- **Bidirectional streaming:** giới hạn cả phiên trao đổi hai chiều.

Gửi thêm message không làm deadline tự gia hạn. Nếu một subscription cần tồn tại lâu, hãy thiết kế thời gian sống từng phiên, cơ chế reconnect và cursor/sequence để tiếp tục. Khi deadline hết, server phải dừng producer và giải phóng subscription.

Nếu server tạo một stream downstream trong lúc xử lý stream cha, context của RPC cha cần được truyền sang tác vụ đó. Nếu stream con sống lâu hơn deadline cha do bị tách khỏi context, nó có thể tiếp tục tiêu tốn tài nguyên sau khi client đã bỏ cuộc.

## 9. Kiểm thử deadline truyền xuyên service

Một bài kiểm thử cần xác nhận cả deadline ở client, context ở server và lời gọi downstream:

1. Client đặt deadline ngắn; server đọc được deadline trong Context.
2. Server gọi downstream; lời gọi con không vượt ngân sách còn lại của lời gọi cha.
3. Server chuyển tác vụ sang executor; context được capture nên deadline/cancellation vẫn hiện diện.
4. Deadline hết trong khi downstream đang chạy; tác vụ con được hủy nếu hỗ trợ.
5. RPC bị hủy sau khi commit; retry không tạo tác dụng phụ trùng.
6. Streaming bị deadline; producer và subscription được dọn.

Ví dụ kiểm thử client nhận status khi server xử lý lâu hơn ngân sách:

~~~java
var stub = OrderServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(100, TimeUnit.MILLISECONDS);

StatusRuntimeException failure = assertThrows(
    StatusRuntimeException.class,
    () -> stub.getOrder(request));

assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    failure.getStatus().getCode());
~~~

Test này chỉ chứng minh client nhận status hết deadline. Để chứng minh propagation, cần instrument service cha và service con, ghi lại deadline còn lại tại từng điểm, rồi xác nhận context bị cancelled sau khi client hết hạn. Nên dùng latch hoặc controllable future thay vì Thread.sleep dài để giảm test flaky.

## 10. Quan sát và xử lý lỗi

Theo dõi các chỉ số sau theo RPC method và service:

- Deadline còn lại khi request tới server.
- Thời gian xử lý ở từng tầng và thời gian chờ downstream.
- Tỷ lệ **DEADLINE_EXCEEDED** và **CANCELLED**.
- Số tác vụ downstream còn chạy sau khi RPC cha bị hủy.
- Thời gian cleanup sau cancellation.
- Tỷ lệ retry và số tác dụng phụ trùng được ngăn bởi idempotency.

Nếu server thường nhận request với deadline còn rất ít, có thể độ trễ đã phát sinh trước khi đến service. Nếu deadline cha còn nhiều nhưng downstream timeout thường xuyên, cần điều tra service con hoặc timeout riêng. Đừng chỉ tăng timeout; hãy tìm tầng đang tiêu thụ ngân sách.

Client nhận **DEADLINE_EXCEEDED** không chứng minh server chưa thực hiện thao tác. Với command có tác dụng phụ, sử dụng idempotency key hoặc operation ID để kiểm tra/trả lại kết quả cũ khi client gửi lại cùng yêu cầu.

## 11. Ghi nhớ và tự kiểm tra

**Deadline truyền từ client đến server** qua cơ chế giao thức gRPC, thường được biểu diễn bằng header **grpc-timeout**. Server nhận deadline trong **Context.current()**; outbound RPC được tạo trong context đó có thể kế thừa deadline và cancellation. Khi chuyển thread, cần truyền context một cách tường minh để không làm mất ngân sách thời gian của request.

Tự kiểm tra:

1. Vì sao server không nhận một ngân sách deadline mới đầy đủ khi request đến nơi?
2. grpc-timeout khác metadata như authorization hoặc tenant ID ở điểm nào?
3. Điều gì có thể xảy ra nếu server chuyển xử lý sang executor nhưng không truyền Context?
4. Vì sao deadline cha phải chi phối lời gọi downstream dù stub con đặt timeout riêng?
5. Client nhận **DEADLINE_EXCEEDED** có chứng minh transaction chưa commit không?

Truyền deadline đúng xuyên suốt chuỗi lời gọi giúp Spring gRPC tránh xử lý công việc đã hết giá trị, giới hạn tài nguyên và giữ thời gian phản hồi trong ngân sách mà client yêu cầu.
