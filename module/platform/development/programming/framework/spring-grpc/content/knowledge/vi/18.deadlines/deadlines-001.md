# Deadline là giới hạn thời gian của RPC

Một lời gọi gRPC không nên chờ vô hạn để nhận kết quả. **Deadline** xác định thời điểm muộn nhất mà client chấp nhận lời gọi hoàn tất. Khi thời điểm đó đến, gRPC kết thúc lời gọi và thông báo timeout; server cũng nhận tín hiệu hủy để có thể dừng công việc không còn cần thiết.

Trong **Spring gRPC**, deadline được cấu hình trên client stub của gRPC Java và đi theo toàn bộ vòng đời RPC. Nó bao gồm thời gian chờ tài nguyên, truyền request, xử lý ở server và chờ response. Deadline giúp giới hạn độ trễ, ngăn request treo chiếm tài nguyên và tạo ngân sách thời gian rõ ràng cho các lời gọi giữa nhiều service.

## 1. Deadline và timeout khác nhau thế nào?

Hai khái niệm liên quan nhưng không giống nhau:

- **Timeout** thường được diễn đạt như một khoảng thời gian chờ tối đa, ví dụ 800 mili giây.
- **Deadline** là mốc thời gian cuối cùng mà lời gọi phải hoàn tất.

Nếu một RPC bắt đầu lúc 10:00:00 và có timeout 800 ms, deadline của nó xấp xỉ 10:00:00.800. Nếu công việc đã mất 500 ms ở hàng đợi trước khi gửi request, thời gian còn lại chỉ khoảng 300 ms.

gRPC biểu diễn deadline như một mốc thời gian và theo dõi thời gian còn lại. Khi deadline được truyền qua các lời gọi service, gRPC có thể truyền **thời gian còn lại** thay vì chỉ truyền một mốc đồng hồ tuyệt đối, giúp tránh sai lệch đồng hồ giữa các máy.

Điều quan trọng là deadline thuộc về **toàn bộ RPC**, không phải một bộ đếm riêng được khởi động lại cho từng giai đoạn. Gửi thêm một message trong streaming RPC cũng không tự làm deadline dài thêm.

## 2. Đặt deadline trên Java client

Với gRPC Java, có thể đặt thời lượng tối đa bằng **withDeadlineAfter**:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;

GetProductRequest request = GetProductRequest.newBuilder()
    .setProductId("keyboard-01")
    .build();

try {
    GetProductResponse response = blockingStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getProduct(request);

    System.out.println(response.getName());
} catch (StatusRuntimeException ex) {
    if (ex.getStatus().getCode() == Status.Code.DEADLINE_EXCEEDED) {
        // Lời gọi đã vượt quá thời gian cho phép.
        // Kiểm tra trạng thái nghiệp vụ trước khi gửi lại lệnh có tác dụng phụ.
    } else {
        throw ex;
    }
}
~~~

**withDeadlineAfter(800, TimeUnit.MILLISECONDS)** tạo một stub mới với deadline cho lời gọi được thực hiện qua stub đó. Stub gốc không bị thay đổi; có thể cấu hình các stub khác nhau cho các nhóm thao tác có ngân sách thời gian khác nhau.

Với async stub, cách đặt deadline tương tự:

~~~java
var timedStub = InventoryServiceGrpc.newStub(channel)
    .withDeadlineAfter(2, TimeUnit.SECONDS);

timedStub.watchStock(request, responseObserver);
~~~

Trong ứng dụng Spring, channel và stub thường được quản lý bằng bean hoặc cơ chế tích hợp của phiên bản Spring gRPC đang sử dụng. Deadline nên được đặt **theo từng lời gọi hoặc nhóm nghiệp vụ**, thay vì gắn một con số tùy tiện cho toàn bộ client.

## 3. Deadline bao gồm những khoảng thời gian nào?

Ngân sách của một RPC có thể được tiêu thụ ở nhiều nơi:

~~~mermaid
flowchart LR
    A["Bắt đầu RPC"] --> B["Chờ tài nguyên / kết nối"]
    B --> C["Truyền request"]
    C --> D["Server xử lý"]
    D --> E["Truyền response"]
    E --> F["Hoàn tất trước deadline"]
~~~

Thời gian chờ ở client, network, hàng đợi và xử lý server đều tiêu thụ cùng ngân sách. Nếu một RPC có deadline 1 giây nhưng phải chờ 700 ms ở hàng đợi, server chỉ còn khoảng 300 ms để xử lý và trả kết quả.

Điều này đặc biệt quan trọng khi service gọi service khác. Không nên để mỗi tầng tự cấp một timeout mới bằng toàn bộ ngân sách ban đầu, vì tổng thời gian chuỗi có thể vượt xa điều client đã chấp nhận.

## 4. Chọn deadline theo ngân sách nghiệp vụ

Deadline quá dài khiến request chậm giữ tài nguyên lâu; deadline quá ngắn khiến thao tác hợp lệ thường xuyên thất bại. Hãy chọn dựa trên đặc tính của thao tác và số liệu đo:

| Loại thao tác | Cách xác định ngân sách |
| --- | --- |
| Đọc dữ liệu nhỏ trong nội bộ | Dựa vào latency p95/p99 và thời gian network thông thường |
| Ghi dữ liệu hoặc tạo đơn | Tính cả kiểm tra, transaction, ghi bền và phản hồi |
| Gọi nhiều service downstream | Chia ngân sách cho từng bước và giữ phần dự phòng cho tầng gọi |
| Upload dữ liệu theo stream | Tính tổng thời gian truyền, xử lý và kích thước tối đa |
| Subscription hoặc stream dài | Dùng chính sách vòng đời/kết nối lại phù hợp, không áp dụng timeout ngắn của unary |

Một cách tiếp cận là đặt deadline cao hơn p99 của thao tác trong điều kiện tải hợp lệ, sau đó kiểm tra tỷ lệ timeout và tài nguyên bị giữ. Không lấy một con số từ một môi trường thử nghiệm rồi áp dụng cho mọi method.

Deadline cũng phải phù hợp với trải nghiệm người dùng hoặc SLA. Nếu giao diện chỉ chờ tối đa 2 giây, service không nên tiếp tục xử lý đồng bộ trong 30 giây mà không có cơ chế job bất đồng bộ.

## 5. Truyền deadline qua các service

Giả sử API gateway gọi OrderService, rồi OrderService gọi InventoryService. Nếu client ban đầu chỉ còn 500 ms, lời gọi downstream không nên được phép dùng thêm 2 giây.

Nguyên tắc là **ngân sách thời gian chỉ giảm dần theo chuỗi lời gọi**:

~~~mermaid
flowchart TD
    A["Client<br/>deadline còn 1.000 ms"] --> B["OrderService<br/>xử lý 150 ms"]
    B --> C["InventoryService<br/>ngân sách còn tối đa 850 ms"]
    C --> D["Database / downstream<br/>ngân sách còn lại tiếp tục giảm"]
~~~

Trong gRPC Java, deadline và cancellation được gắn với **io.grpc.Context** của lời gọi. Các lời gọi downstream được tạo trong context hiện hành có thể kế thừa giới hạn deadline/cancellation; deadline tường minh ngắn hơn vẫn có thể siết chặt ngân sách. Cần tránh ghi đè bằng một deadline dài hơn ngân sách còn lại của request cha.

Ví dụ tính một ngân sách cục bộ không vượt deadline cha:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Deadline parentDeadline = Context.current().getDeadline();
long localBudgetNanos = TimeUnit.MILLISECONDS.toNanos(250);

if (parentDeadline != null) {
    long remaining = parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);
    long reserveForResponse = TimeUnit.MILLISECONDS.toNanos(20);
    localBudgetNanos = Math.min(
        localBudgetNanos,
        remaining - reserveForResponse);
}

if (localBudgetNanos <= 0) {
    // Không còn đủ ngân sách để bắt đầu downstream call.
    throw Status.DEADLINE_EXCEEDED
        .withDescription("insufficient time for inventory lookup")
        .asRuntimeException();
}

var inventoryStub = InventoryServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(localBudgetNanos, TimeUnit.NANOSECONDS);

InventoryResponse response = inventoryStub.checkAvailability(request);
~~~

Đoạn code minh họa việc dành 20 ms để tầng gọi xử lý response và trả kết quả. Con số dự phòng cần được chọn theo latency thực tế. Trong trường hợp không có deadline cha, ví dụ dùng ngân sách cục bộ 250 ms.

## 6. Server phản ứng khi deadline hết hạn

Khi client hết deadline, gRPC hủy lời gọi. Ở server, context của RPC được đánh dấu cancelled; server nên ngừng công việc tiếp theo và giải phóng tài nguyên. Có thể kiểm tra trạng thái trong logic xử lý:

~~~java
import io.grpc.Context;

Context context = Context.current();

if (context.isCancelled()) {
    // Dừng xử lý tiếp theo nếu có thể.
    return;
}

// Chỉ thực hiện bước nghiệp vụ tiếp theo khi RPC còn hiệu lực.
~~~

Với tác vụ kéo dài, có thể đăng ký cancellation listener để hủy tài nguyên hoặc tác vụ downstream:

~~~java
Context context = Context.current();
context.addListener(cancelledContext -> {
    uploadTask.cancel(true);
    releaseTemporaryResources();
}, Runnable::run);
~~~

Ví dụ giả định **uploadTask** và **releaseTemporaryResources()** thuộc logic ứng dụng. Không nên gọi các thao tác giải phóng không an toàn từ callback; cần bảo đảm cleanup idempotent và tránh tranh chấp với luồng đang hoàn tất bình thường.

**Cancellation không phải rollback.** Nếu server đã commit transaction trước khi nhận tín hiệu hủy, dữ liệu vẫn có thể đã được ghi. Deadline chỉ giới hạn thời gian chờ của RPC và phát tín hiệu hủy; nó không tự hoàn tác tác dụng phụ đã xảy ra.

## 7. Phân biệt DEADLINE_EXCEEDED, CANCELLED và các lỗi khác

| Status | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| **DEADLINE_EXCEEDED** | Deadline của lời gọi đã hết | Client không nhận kết quả trong ngân sách |
| **CANCELLED** | Lời gọi bị hủy | Có thể do client, context cha hoặc tác nhân khác hủy |
| **UNAVAILABLE** | Dịch vụ/kết nối tạm thời không sẵn sàng | Có thể thử lại nếu thao tác an toàn |
| **RESOURCE_EXHAUSTED** | Vượt giới hạn tài nguyên/quota | Giảm tải hoặc điều chỉnh quota |
| **INVALID_ARGUMENT** | Dữ liệu đầu vào không hợp lệ | Sửa request, không retry nguyên trạng |
| **INTERNAL** | Lỗi nội bộ server | Điều tra bằng log/trace an toàn |

Client có thể kiểm tra status từ **StatusRuntimeException**:

~~~java
catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();
    if (code == Status.Code.DEADLINE_EXCEEDED) {
        // Xử lý timeout.
    } else if (code == Status.Code.CANCELLED) {
        // Lời gọi đã bị hủy.
    } else {
        // Ánh xạ status còn lại theo nghiệp vụ.
    }
}
~~~

Không nên chuyển mọi lỗi thành **DEADLINE_EXCEEDED** chỉ vì client chờ lâu ở tầng giao diện. Hãy giữ đúng status gRPC để telemetry, retry policy và người vận hành phân biệt được nguyên nhân.

## 8. Deadline với streaming RPC

Deadline áp dụng cho **toàn bộ streaming RPC**, không phải từng message:

- **Server streaming:** một request mở stream; deadline giới hạn thời gian sống của lời gọi nhận nhiều response.
- **Client streaming:** toàn bộ thời gian gửi request và chờ response cuối cùng dùng chung deadline.
- **Bidirectional streaming:** cả hai chiều gửi/nhận nằm trong một RPC có deadline chung.

Một stream subscription có thể được thiết kế để tồn tại lâu. Khi đó, deadline ngắn có thể làm stream kết thúc trước khi người dùng cần. Các lựa chọn thường gặp:

1. Đặt thời gian sống tối đa cho một phiên và client tự kết nối lại.
2. Dùng sequence/cursor để client tiếp tục từ vị trí đã nhận.
3. Phân biệt kết thúc bình thường, lỗi và hết deadline trong logic reconnect.
4. Giải phóng subscription, queue và tài nguyên server khi stream bị hủy.

Không tự gia hạn deadline mỗi khi có message mới. Nếu cần phiên dài, hãy thiết kế vòng đời và resume rõ ràng thay vì xem stream là kết nối vô hạn.

## 9. Retry khi deadline hết: phải xét tác dụng phụ

Khi client nhận **DEADLINE_EXCEEDED**, có hai khả năng:

- Server chưa hoàn tất thao tác.
- Server đã hoàn tất hoặc commit thao tác, nhưng response không đến client kịp thời.

Vì client không thể suy ra trạng thái nghiệp vụ chỉ từ timeout, retry command có thể gây tạo đơn, thanh toán hoặc giữ hàng hai lần.

Với thao tác có tác dụng phụ, dùng **idempotency key** hoặc operation ID ổn định. Server lưu kết quả theo khóa và trả lại kết quả trước đó nếu nhận request lặp. Nếu thao tác chạy lâu, có thể chuyển thành mô hình tạo job: unary trả operation ID nhanh, client dùng method khác để truy vấn trạng thái hoặc theo dõi tiến trình.

Retry cũng phải nằm trong ngân sách deadline tổng thể. Không cấu hình mỗi lần retry một timeout dài mới khiến tổng thời gian chờ vượt quá điều client chấp nhận.

## 10. Kiểm thử deadline

Kiểm thử nên xác nhận cả status client nhận và hành vi cleanup ở server:

1. **Thành công trước deadline:** server trả response trong ngân sách, client nhận **OK**.
2. **Server xử lý chậm:** đặt deadline ngắn, client nhận **DEADLINE_EXCEEDED**.
3. **Cancellation:** server nhận biết context đã cancelled và dừng tác vụ có thể dừng.
4. **Downstream:** lời gọi service con không vượt deadline còn lại của request cha.
5. **Side effect:** timeout xảy ra sau commit không khiến retry tạo dữ liệu trùng.
6. **Streaming:** deadline hết giữa stream làm dừng producer và giải phóng subscription/queue.

Ví dụ test có thể dùng một service cố ý trì hoãn:

~~~java
@Override
public void getProduct(
        GetProductRequest request,
        StreamObserver<GetProductResponse> responseObserver) {
    try {
        Thread.sleep(500);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }

    responseObserver.onNext(
        GetProductResponse.newBuilder()
            .setProductId(request.getProductId())
            .setName("Demo")
            .build());
    responseObserver.onCompleted();
}
~~~

Client gọi method này với deadline ngắn hơn 500 ms để kiểm tra timeout. Đây là fixture đơn giản cho test; trong production không nên dùng **Thread.sleep** để điều khiển thời gian xử lý. Test tích hợp cần xác minh server không tiếp tục ghi response sau khi RPC đã bị hủy và không để lại tác vụ nền.

## 11. Quan sát deadline trong production

Theo dõi các chỉ số sau theo method và service:

- Tỷ lệ RPC kết thúc bằng **DEADLINE_EXCEEDED**.
- Latency p50, p95, p99 so với deadline cấu hình.
- Thời gian chờ hàng đợi, thời gian xử lý server và thời gian downstream.
- Số lời gọi bị cancel và thời gian cleanup sau cancellation.
- Tỷ lệ retry, số lần thử trung bình và tác động trùng được ngăn bởi idempotency.
- Với streaming: thời gian sống stream, số stream bị deadline và tài nguyên được giải phóng.

Nếu timeout tăng, không nên chỉ tăng deadline ngay. Hãy xác định phần thời gian bị tiêu thụ ở client queue, network, server, database hay service downstream. Deadline dài hơn có thể che giấu quá tải và làm request giữ tài nguyên lâu hơn.

## 12. Ghi nhớ và tự kiểm tra

**Deadline là mốc kết thúc của toàn bộ RPC**. Client có thể đặt giới hạn bằng **withDeadlineAfter**; server nhận deadline/cancellation trong **Context.current()**. Deadline cần được truyền xuyên suốt chuỗi service theo ngân sách còn lại, và server nên dừng công việc khi RPC bị hủy.

Tự kiểm tra:

1. Vì sao deadline 1 giây không có nghĩa server luôn có đủ 1 giây xử lý nghiệp vụ?
2. Khi một service gọi service khác, vì sao không nên cấp lại toàn bộ timeout ban đầu?
3. Client nhận **DEADLINE_EXCEEDED** có chứng minh transaction chưa commit không?
4. Vì sao deadline của streaming RPC không tự khởi động lại sau mỗi message?
5. Cần quan sát những chỉ số nào để biết timeout xuất phát từ hàng đợi, server hay downstream?

Đặt deadline đúng giúp Spring gRPC kiểm soát độ trễ và tài nguyên xuyên suốt hệ thống. Kết hợp deadline với cancellation, idempotency, status rõ ràng và quan sát phù hợp giúp ứng dụng xử lý timeout an toàn thay vì chỉ tăng thời gian chờ.
