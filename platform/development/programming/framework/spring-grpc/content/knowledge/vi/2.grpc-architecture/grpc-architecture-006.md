# Deadline, cancellation và status

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **deadline**, **timeout**, **cancellation** và **Status.Code** trong một lời gọi gRPC.
- Đặt deadline theo từng RPC từ client Spring, hiểu **grpc-timeout** và việc truyền hạn thời gian sang server.
- Hủy các RPC đang chạy, quan sát **io.grpc.Context** và dừng công việc ở phía server.
- Chọn mã lỗi gRPC phù hợp; phân biệt status với HTTP/2 status và nội dung protobuf response.
- Xử lý deadline/cancellation an toàn trong unary và streaming, đặc biệt khi một thao tác ghi có thể đã hoàn tất trước khi caller timeout.
- Kiểm thử và quan sát hiệu năng/độ tin cậy qua trạng thái RPC, metrics và tracing.

## 1. Ba khái niệm ở ba vai trò

Trong **SPRING_GRPC**, client gọi server bằng stub Java được sinh từ hợp đồng Protocol Buffers. Runtime truyền lời gọi qua Channel và HTTP/2 stream. Một RPC có thể hoàn thành, bị hủy, hết thời gian hoặc thất bại vì lỗi ứng dụng.

| Khái niệm | Ý nghĩa | Kết quả thường gặp |
| --- | --- | --- |
| **Deadline** | Caller chờ kết quả **đến thời điểm nào**? | Khi hết hạn, client thường thấy **DEADLINE_EXCEEDED** |
| **Cancellation** | Lời gọi **còn cần thực hiện** nữa không? | Khi hủy chủ động, caller thường thấy **CANCELLED** |
| **Status** | Kết quả cuối cùng của RPC là gì? | **OK**, **NOT_FOUND**, **UNAVAILABLE**, **INTERNAL**... |

**Deadline** là hạn cuối của một RPC. **Timeout** là khoảng thời gian tương đối dùng để xác định deadline, ví dụ "RPC tối đa 800 ms từ bây giờ". Trong khi đó, cancellation có thể xảy ra *trước* deadline nếu người dùng không còn muốn chờ.

**Status** là cơ chế báo kết quả theo mã chuẩn gRPC. Một số status được server trả theo logic nghiệp vụ; số khác do runtime sinh ra, chẳng hạn khi client hết deadline hoặc transport mất kết nối.

~~~mermaid
flowchart TD
    A["Client gọi stub"] --> B["ManagedChannel mở RPC/HTTP2 stream"]
    B --> C{"RPC kết thúc trước deadline?"}
    C -->|"Có"| D{"Kết quả?"}
    D -->|"Thành công"| E["OK + response"]
    D -->|"Lỗi"| F["Status khác OK"]
    C -->|"Chưa"| G{"Caller hủy trước?"}
    G -->|"Có"| H["Thường CANCELLED"]
    G -->|"Không; deadline hết"| I["Thường DEADLINE_EXCEEDED"]
    H --> J["Server nhận tín hiệu hủy nếu transport chuyển được"]
    I --> J
    J --> K["Ngừng công việc và dọn tài nguyên"]
~~~

Sơ đồ cho biết các nhánh phổ biến; không đảm bảo hai phía luôn nhìn thấy cùng một status. Đặc biệt, khi deadline hết, server có thể đã hoàn thành thao tác ghi.

## 2. Hợp đồng Protocol Buffers dùng trong ví dụ

Ta khai báo một unary RPC lấy đơn hàng và một server-streaming RPC theo dõi thay đổi:

~~~proto
syntax = "proto3";

package demo.orders.v1;

option java_package = "dev.example.orders.v1";
option java_multiple_files = true;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderUpdate);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string state = 2;
}

message WatchOrderRequest {
  string order_id = 1;
}

message OrderUpdate {
  string order_id = 1;
  string state = 2;
  int64 sequence = 3;
}
~~~

**protoc** và **protoc-gen-grpc-java** sinh message class, client stub và **OrderServiceGrpc.OrderServiceImplBase**. Lập trình viên viết business logic trong server implementation.

Không cần thêm field deadline/status vào mọi message: deadline là call option/context, status là kết quả RPC. Nếu nghiệp vụ có hạn thanh toán riêng, đó là field dữ liệu cần mô tả rõ, khác với deadline mạng.

## 3. Deadline giới hạn toàn bộ thời gian một RPC

Một RPC có thể tiêu tốn thời gian ở nhiều giai đoạn:

~~~text
Caller bắt đầu RPC
  -> Chọn backend, chờ connection sẵn sàng
  -> Gửi headers, metadata, protobuf request
  -> Chờ server queue/executor
  -> Server truy cập database hoặc gọi downstream
  -> Nhận response, trailers, giải mã
  -> Caller có kết quả
~~~

**Deadline bao gồm tất cả giai đoạn**, không chỉ thời gian thực thi handler. Nếu một lời gọi có ngân sách 800 ms và đã chờ connection 500 ms, server chỉ còn khoảng 300 ms để hoàn thành và trả kết quả.

Đặt deadline trong grpc-java:

~~~java
GetOrderResponse response = blockingStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());
~~~

Ở đây **blockingStub** có kiểu **OrderServiceGrpc.OrderServiceBlockingStub**, **TimeUnit** thuộc **java.util.concurrent.TimeUnit**. **withDeadlineAfter(...)** trả stub mới với call options mới; nó không sửa stub gốc.

**Không nên gắn deadline ngay khi tạo singleton stub**:

~~~java
@Bean
OrderServiceGrpc.OrderServiceBlockingStub riskyStub(ManagedChannel channel) {
    return OrderServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
}
~~~

Deadline của stub này được tính khi bean được tạo. Nếu dùng sau nhiều giây, các RPC mới có thể hết hạn ngay. Nên giữ stub gốc và gọi **withDeadlineAfter** ở mỗi use case, sát lúc gọi.

### 3.1. grpc-timeout trong request headers

gRPC có thể diễn đạt khoảng thời gian còn lại bằng metadata giao thức **grpc-timeout**:

~~~text
Client -> Server
  HEADERS
    :method: POST
    :path: /demo.orders.v1.OrderService/GetOrder
    content-type: application/grpc
    te: trailers
    grpc-timeout: 800m
  DATA
    [gRPC message prefix][serialized GetOrderRequest]
~~~

**800m** là 800 mili giây và **2S** là 2 giây. Các đơn vị: **H** giờ, **M** phút, **S** giây, **m** mili giây, **u** micro giây, **n** nano giây. Đây là giá trị tương đối trên wire; runtime có thể điều chỉnh theo thời gian đã trôi qua.

Ứng dụng nên đặt deadline bằng API stub/Context. **Không tự đặt grpc-timeout bằng Metadata** vì đây là header được gRPC runtime quản lý.

### 3.2. Deadline khác keepalive và timeout proxy

- **Deadline RPC**: ngân sách của một lời gọi.
- **Keepalive PING**: hỗ trợ kiểm tra tình trạng connection theo policy, không bảo đảm RPC xong kịp thời.
- **Idle timeout của proxy**: có thể cắt một stream chờ lâu dù deadline chưa hết.
- **Timeout database/HTTP client khác**: là giới hạn riêng của dependency, cần phối hợp với deadline RPC.

Một unary đọc cache và một server-streaming tồn tại nhiều phút có yêu cầu thời gian khác nhau. Chọn deadline theo mục tiêu sản phẩm, đo latency thực tế và độ biến động tải.

## 4. Khi deadline hết: những điều không được bảo đảm

Nếu deadline hết trước khi RPC kết thúc, client thường nhận **Status.Code.DEADLINE_EXCEEDED**. Runtime ngừng chờ và cố hủy RPC còn đang hoạt động.

Tuy nhiên, điều đó **không bảo đảm**:

1. Server chưa nhận request.
2. Handler chưa thực hiện nghiệp vụ.
3. Database chưa commit.
4. Một hàm chặn trong Java bị ngắt ngay lập tức.
5. Job chạy ở thread khác hoặc trong hệ thống ngoài gRPC tự dừng.
6. Client và server quan sát chính xác cùng một mã status.

Ví dụ client gọi **CreateOrder** với deadline 1 giây. Server ghi đơn hàng ở giây 0,9 nhưng response chỉ đến lúc 1,1 giây. Client thấy **DEADLINE_EXCEEDED**, trong khi đơn đã tồn tại. Nếu caller gửi lại không có **idempotency key**, có nguy cơ tạo đơn trùng.

Deadline là giới hạn **khả năng chờ của caller**, không phải cam kết rollback. Với thao tác có tác dụng phụ, cần thiết kế khử trùng lặp hoặc tra cứu trạng thái sau timeout.

### 4.1. Truyền deadline qua nhiều service

~~~text
HTTP request budget: 1500 ms
  Gateway
    -> OrderService
         -> InventoryService
         -> PricingService
              -> Database
~~~

Nếu Gateway đã dùng 500 ms, những tầng sau chỉ còn khoảng 1.000 ms. Không nên cấp lại 1.500 ms cho từng hop rồi cộng dồn.

Trong grpc-java, **io.grpc.Context** có thể mang deadline/cancellation qua các RPC downstream được tạo trong context hiện tại. Khi dùng **@Async**, **CompletableFuture**, scheduler hoặc executor riêng, context có thể bị mất nếu không chủ động truyền sang thread thực thi.

Một service có thể đặt deadline ngắn hơn cho dependency nhằm chừa thời gian fallback và gửi response. Mọi retry phải nằm trong ngân sách thời gian còn lại.

## 5. Cancellation là hành động ngừng một RPC

Các tình huống hủy thường gặp: người dùng đóng trang, caller không cần một stream nữa, một job cha hủy, deadline hết, hoặc mất kết nối. Hủy một RPC không đồng nghĩa đóng **ManagedChannel**. Channel thường được chia sẻ giữa nhiều lời gọi; đóng Channel để hủy một stream có thể làm hỏng các RPC khác.

### 5.1. Half-close khác cancellation

Trong client-streaming hoặc bidirectional streaming:

~~~java
requestObserver.onNext(firstRequest);
requestObserver.onNext(secondRequest);
requestObserver.onCompleted();
~~~

**onCompleted()** trên *request observer* chỉ có nghĩa **client đã gửi xong** (half-close chiều gửi). Server vẫn có thể tiếp tục gửi response và hoàn tất RPC. Đó không phải cancellation.

Khi một RPC thực sự bị hủy, runtime có thể kết thúc HTTP/2 stream bằng tín hiệu như **RST_STREAM** và phía client nhận **onError**. Không dùng **onCompleted()** để thay cho thao tác hủy.

### 5.2. Hủy một lời gọi async bằng CancellableContext

Một cách hủy server-streaming RPC trong grpc-java là tạo **Context.CancellableContext** trước khi bắt đầu call. Ví dụ **asyncStub** là **OrderServiceGrpc.OrderServiceStub**, được tạo từ Channel dùng chung:

~~~java
import dev.example.orders.v1.OrderUpdate;
import dev.example.orders.v1.WatchOrderRequest;
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

Context.CancellableContext callContext =
        Context.current().withCancellation();

Context previous = callContext.attach();
try {
    asyncStub.watchOrder(
            WatchOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build(),
            new StreamObserver<OrderUpdate>() {
                @Override
                public void onNext(OrderUpdate value) {
                    System.out.println(value.getState());
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println(
                            "WatchOrder kết thúc: "
                            + Status.fromThrowable(error).getCode());
                }

                @Override
                public void onCompleted() {
                    System.out.println("WatchOrder hoàn tất");
                }
            });
} finally {
    callContext.detach(previous);
}

// Khi người dùng thực sự yêu cầu dừng theo dõi:
callContext.cancel(
        new java.util.concurrent.CancellationException(
                "User stopped watching"));
~~~

**attach()/detach()** cho phép RPC được tạo trong context đã có khả năng hủy rồi phục hồi context gốc cho thread. Dòng **cancel()** được đặt ngay sau để minh họa API; trong ứng dụng thật chỉ gọi khi có sự kiện hủy hoặc cleanup phù hợp. Nên lưu handle hủy trong một đối tượng gắn với lifecycle của phiên làm việc/luồng sự kiện.

Tùy kiểu RPC, các lựa chọn khác gồm **ClientCall.cancel(...)**, **ClientCallStreamObserver.cancel(...)** hoặc cancel future do API cung cấp. Chỉ bỏ tham chiếu Java đến observer không khiến runtime tự biết cần hủy RPC.

### 5.3. Caller và server có thể quan sát status khác nhau

Caller chủ động hủy thường thấy **CANCELLED**; caller hết deadline thường thấy **DEADLINE_EXCEEDED**; mất kết nối có thể dẫn tới **UNAVAILABLE**. Ở server, tín hiệu tương ứng thường thể hiện qua **Context.isCancelled()** hoặc cancel handler, nhưng không nhất thiết còn đầy đủ thông tin về status cuối mà client quan sát. Vì vậy nên theo dõi lý do hủy, thời điểm và nguồn metrics của mỗi phía.

## 6. Server nhận biết cancellation và thời gian còn lại

Trong handler grpc-java, **io.grpc.Context** của lời gọi chứa thông tin deadline và cancellation. Ví dụ:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Deadline deadline = Context.current().getDeadline();

if (deadline != null) {
    long remainingMs = deadline.timeRemaining(TimeUnit.MILLISECONDS);
    System.out.println("Deadline còn khoảng " + remainingMs + " ms");
}

if (Context.current().isCancelled()) {
    // Caller đã ngừng chờ, không mở thêm công việc tốn tài nguyên.
    return;
}
~~~

**getDeadline()** có thể trả **null** nếu không có hạn được đặt. **timeRemaining(...)** có thể bằng 0 hoặc âm nếu deadline đã hết; đây không phải thời điểm tuyệt đối để lưu vào trường dữ liệu nghiệp vụ.

Server nên kiểm tra cancellation trước khi bắt đầu việc lớn, giữa các bước xử lý dài hoặc bằng listener/hook để đóng subscription. Một hàm blocking trong database driver hoặc thư viện không hỗ trợ cancel sẽ không tự dừng ngay chỉ vì Context gRPC đổi trạng thái. Cần áp timeout/cancel vào dependency khi hạ tầng hỗ trợ.

### 6.1. ServerCallStreamObserver và cancel handler

Với server-streaming, **ServerCallStreamObserver** cung cấp **isCancelled()** và **setOnCancelHandler(...)**. Ví dụ bên dưới phát ba message để minh họa cách kiểm tra, không mô phỏng một stream sự kiện dài hạn:

~~~java
package dev.example.orders.server;

import dev.example.orders.v1.OrderServiceGrpc;
import dev.example.orders.v1.OrderUpdate;
import dev.example.orders.v1.WatchOrderRequest;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;

public class OrderWatchEndpoint
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void watchOrder(
            WatchOrderRequest request,
            StreamObserver<OrderUpdate> responseObserver) {

        ServerCallStreamObserver<OrderUpdate> out =
                (ServerCallStreamObserver<OrderUpdate>) responseObserver;

        AtomicBoolean stopped = new AtomicBoolean(false);

        out.setOnCancelHandler(() -> {
            stopped.set(true);
            // Bỏ đăng ký sự kiện, dừng polling/timer và cleanup.
        });

        for (int i = 1; i <= 3; i++) {
            if (stopped.get() || out.isCancelled()) {
                return;
            }

            out.onNext(
                    OrderUpdate.newBuilder()
                            .setOrderId(request.getOrderId())
                            .setState("UPDATE_" + i)
                            .setSequence(i)
                            .build());
        }

        if (!out.isCancelled()) {
            out.onCompleted();
        }
    }
}
~~~

Với stream thật có nguồn dữ liệu lớn, cần kết hợp **isReady()/setOnReadyHandler(...)**, flow control, giới hạn buffer và sự điều phối producer để tránh nhiều thread cùng phát trên một observer. **StreamObserver không tự bảo đảm thread-safe khi ghi đồng thời**. Cancellation cũng có thể đến ngay sau lúc kiểm tra isCancelled(); đó là race condition bình thường cần xử lý an toàn.

Khi peer đã hủy, không cố gửi thêm response "đã hủy" qua đường truyền có thể đã đóng. Cleanup nguồn dữ liệu là trách nhiệm quan trọng hơn.

### 6.2. Context trong công việc bất đồng bộ

Nếu server dùng executor riêng, cần truyền Context sang thread thực thi. **Context.wrap(...)** là cách dùng điển hình:

~~~java
import io.grpc.Context;
import java.util.concurrent.Executor;

void submitRpcWork(Executor executor) {
    Context captured = Context.current();

    executor.execute(captured.wrap(() -> {
        if (Context.current().isCancelled()) {
            return;
        }

        // Xử lý nghiệp vụ và kiểm tra cancellation khi cần.
    }));
}
~~~

Đoạn code minh họa việc truyền context, không phải handler đầy đủ. Executor phải được quản lý lifecycle/shutdown trong Spring. Nếu dùng **Context.attach()** thủ công, phải **detach()** trong finally.

Khi server gọi tiếp một service gRPC khác, runtime có thể truyền deadline/cancellation nếu outgoing RPC được khởi tạo trong context hiện tại. Nếu **CompletableFuture**, scheduler hoặc **@Async** làm mất context, deadline của request cha có thể không còn được downstream nhận như mong đợi.

## 7. gRPC status khác HTTP status

HTTP/2 trao đổi frame và status ở tầng vận chuyển; gRPC có **grpc-status** để mô tả kết quả RPC. Một response thành công có thể trông như sau:

~~~text
Server -> Client:
  HEADERS
    :status: 200
    content-type: application/grpc
  DATA
    [serialized GetOrderResponse]
  HEADERS (trailers)
    grpc-status: 0
  END_STREAM
~~~

**grpc-status: 0** là **OK**. Nếu server trả **NOT_FOUND**, HTTP status có thể vẫn là **200**, nhưng **grpc-status** trong trailers khác 0. Khi lỗi xảy ra sớm, server có thể trả **trailers-only**, không có response DATA:

~~~text
Server -> Client:
  HEADERS (trailers-only)
    :status: 200
    content-type: application/grpc
    grpc-status: 5
    grpc-message: Order%20not%20found
  END_STREAM
~~~

Đây là biểu diễn logic cho dễ đọc, không phải dump frame nhị phân. **grpc-message** có quy tắc mã hóa riêng và chỉ nên dùng để mô tả lỗi an toàn, không phải contract máy đọc. Client phải phân nhánh theo **Status.Code**, không parse description text.

### 7.1. Các mã Status.Code phổ biến

| Status.Code | Ý nghĩa điển hình | Hướng xử lý |
| --- | --- | --- |
| **OK** | RPC thành công | Đọc response message |
| **CANCELLED** | Lời gọi bị hủy | Dừng chờ, cleanup |
| **UNKNOWN** | Lỗi chưa được phân loại rõ | Điều tra nguồn lỗi |
| **INVALID_ARGUMENT** | Request tự nó không hợp lệ | Caller sửa dữ liệu |
| **DEADLINE_EXCEEDED** | RPC không hoàn thành trước hạn | Kiểm tra latency và kết quả thực nếu có side effect |
| **NOT_FOUND** | Tài nguyên nghiệp vụ không tồn tại | Xử lý trường hợp vắng mặt |
| **ALREADY_EXISTS** | Tài nguyên đã tồn tại | Xử lý trùng định danh |
| **UNAUTHENTICATED** | Thiếu hoặc không hợp lệ danh tính/token | Kiểm tra credentials |
| **PERMISSION_DENIED** | Caller không được phép thao tác | Kiểm tra quyền |
| **RESOURCE_EXHAUSTED** | Quá quota/tài nguyên/giới hạn | Giảm tải, retry có điều kiện |
| **FAILED_PRECONDITION** | Trạng thái hiện tại chưa cho phép thao tác | Sửa điều kiện trước khi gọi lại |
| **ABORTED** | Xung đột giao dịch hoặc tương tranh | Xét thử lại toàn bộ đơn vị transaction |
| **OUT_OF_RANGE** | Vượt phạm vi phụ thuộc trạng thái | Điều chỉnh cursor/range |
| **UNIMPLEMENTED** | Service/method không được hỗ trợ/đăng ký | Kiểm tra descriptor và phiên bản |
| **INTERNAL** | Lỗi nội bộ nghiêm trọng | Điều tra server; không lộ stack trace |
| **UNAVAILABLE** | Service/transport tạm không sẵn sàng | Retry có backoff nếu an toàn |
| **DATA_LOSS** | Mất/hỏng dữ liệu không thể phục hồi | Xử lý sự cố dữ liệu |

Một số cặp thường nhầm:

- **INVALID_ARGUMENT**: request không hợp lệ bất kể trạng thái; **FAILED_PRECONDITION**: trạng thái hiện tại không cho phép; **ABORTED**: xung đột làm hủy thao tác.
- **UNAUTHENTICATED**: không xác minh được danh tính; **PERMISSION_DENIED**: yêu cầu không được cấp quyền.
- **NOT_FOUND**: tài nguyên nghiệp vụ không tồn tại; **UNIMPLEMENTED**: service hoặc method gRPC chưa được triển khai.
- **DEADLINE_EXCEEDED**: caller không nhận được kết quả trước hạn; **UNAVAILABLE**: đường truyền/backend tạm không phục vụ được.

Không phải mọi mã do server handler chọn. Runtime/client cũng sinh DEADLINE_EXCEEDED, CANCELLED, UNAVAILABLE hoặc một số lỗi RESOURCE_EXHAUSTED. Metrics nên phân biệt nơi quan sát lỗi ở client và server.

## 8. Server Spring trả status rõ ràng

Phương thức unary **GetOrder** dưới đây kiểm tra input, mô phỏng một bản ghi và dùng status phù hợp:

~~~java
package dev.example.orders.server;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderEndpoint
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {

        String orderId = request.getOrderId().trim();

        if (orderId.isEmpty()) {
            observer.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id không được rỗng")
                            .asRuntimeException());
            return;
        }

        if (!"order-42".equals(orderId)) {
            observer.onError(
                    Status.NOT_FOUND
                            .withDescription("Không tìm thấy đơn hàng")
                            .asRuntimeException());
            return;
        }

        if (Context.current().isCancelled()) {
            // Không phát response khi caller đã bỏ cuộc.
            return;
        }

        observer.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(orderId)
                        .setState("PENDING")
                        .build());
        observer.onCompleted();
    }
}
~~~

Đối với response observer, **onCompleted()** và **onError()** là các nhánh terminal loại trừ nhau. Khi đã kết thúc, không gọi thêm **onNext()**. Unary thành công phải có một response message. Với lỗi, có thể chỉ gửi status mà không có message thành công.

Trong dịch vụ thật, handler nên gọi service nghiệp vụ/repository, kiểm tra authorization và ánh xạ exception. Không trả stack trace, SQL hoặc token trong **Status.description**. Nếu code bắt tất cả exception và gói thành INTERNAL, client sẽ mất khả năng phân biệt lỗi dữ liệu với sự cố hạ tầng.

### 8.1. Đăng ký endpoint qua Spring

~~~java
package dev.example.orders.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server grpcServer(OrderEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

**@Component** đăng ký implementation trong Spring; **addService(endpoint)** đăng ký handler với gRPC runtime. Đây là ví dụ **grpc-java do Spring quản lý**, không phải tên cấu hình bắt buộc cho mọi bản Spring gRPC starter. Nếu framework tự tạo/đăng ký server, nên dùng đúng cơ chế đó để tránh mở hai server trên cùng cổng.

Khi ứng dụng dừng, **shutdown()** yêu cầu ngừng nhận công việc mới; không có nghĩa server đã chờ xong toàn bộ RPC. Production nên có quy trình **graceful shutdown**, thời gian drain hợp lý và cleanup job còn chạy.

## 9. Client Spring đặt deadline và phân loại status

Một **ManagedChannel** có thể được tái sử dụng cho nhiều RPC. Stub gốc cũng nhẹ và có thể dùng chung; từng lời gọi tự quyết định deadline theo use case.

~~~java
package dev.example.orders.client;

import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        // Demo local; production cần TLS và xác thực phù hợp.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel ordersChannel) {
        return OrderServiceGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Spring service dùng deadline mới cho mỗi lời gọi và phân loại status:

~~~java
package dev.example.orders.client;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.NoSuchElementException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {

    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderLookupClient(
            OrderServiceGrpc.OrderServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse findOrder(String id) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(id)
                .build();

        try {
            return stub.withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException error) {
            Status.Code code = error.getStatus().getCode();

            switch (code) {
                case INVALID_ARGUMENT:
                    throw new IllegalArgumentException(
                            "ID đơn hàng không hợp lệ", error);
                case NOT_FOUND:
                    throw new NoSuchElementException(
                            "Không tìm thấy đơn hàng: " + id);
                case DEADLINE_EXCEEDED:
                    throw new IllegalStateException(
                            "GetOrder vượt deadline", error);
                case UNAVAILABLE:
                    throw new IllegalStateException(
                            "OrderService tạm không sẵn sàng", error);
                default:
                    throw error;
            }
        }
    }
}
~~~

Đây là ví dụ ánh xạ gRPC status sang lỗi tầng ứng dụng; sản phẩm thật có thể dùng exception domain riêng. **Không tự retry mọi mã lỗi**. INVALID_ARGUMENT cần sửa dữ liệu; NOT_FOUND là một nhánh kết quả nghiệp vụ; UNAVAILABLE có thể tạm thời; DEADLINE_EXCEEDED cần kiểm tra thời gian và trạng thái đã xử lý.

**usePlaintext()** chỉ phù hợp demo local hoặc đường truyền được kiểm soát theo chính sách. Khi triển khai thực tế cần cấu hình TLS/mTLS, trust chain, credentials và kiểm thử proxy HTTP/2. TLS bảo vệ đường truyền nhưng không thay deadline/cancellation.

### 9.1. Async RPC nhận status trong onError()

Lời gọi async trả về trước khi có kết quả. Những lỗi RPC xảy ra sau đó sẽ đi vào **onError(...)**, không chỉ được bắt bởi try/catch bên ngoài lúc gọi stub:

~~~java
asyncStub.withDeadlineAfter(5, TimeUnit.SECONDS)
        .watchOrder(
                WatchOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build(),
                new StreamObserver<OrderUpdate>() {
                    @Override
                    public void onNext(OrderUpdate update) {
                        // Xử lý event tiếp theo.
                    }

                    @Override
                    public void onError(Throwable error) {
                        Status.Code code =
                                Status.fromThrowable(error).getCode();
                        System.err.println("WatchOrder status: " + code);
                    }

                    @Override
                    public void onCompleted() {
                        // Luồng đã hoàn tất thành công.
                    }
                });
~~~

Ở đây **asyncStub** là **OrderServiceGrpc.OrderServiceStub**. Các lớp **WatchOrderRequest**, **OrderUpdate** được sinh từ proto ở mục 2; cần import **TimeUnit**, **Status** và **StreamObserver** khi đưa snippet vào source thật.

Đối với streaming, một observer gắn với một RPC cụ thể. Không dùng lại observer của RPC đã kết thúc, và phải kiểm soát bộ đệm khi server phát nhanh hơn tốc độ client tiêu thụ.

## 10. Retry, idempotency và giới hạn thời gian

Retry có thể cải thiện độ tin cậy trước lỗi tạm thời, nhưng cũng có thể nhân tải lên hoặc thực thi một thao tác ghi hai lần. Trước khi retry, cần xem:

1. **Status**: UNAVAILABLE có thể tạm thời, INVALID_ARGUMENT không tự hết khi gửi lại cùng request.
2. **Tính idempotent**: đọc đơn hàng theo ID thường có thể retry; tạo đơn hàng/thu tiền cần cơ chế khử trùng lặp.
3. **Deadline còn lại**: retry và backoff phải nằm trong ngân sách tổng.
4. **Backoff/jitter**: tránh nhiều client retry cùng lúc gây retry storm.
5. **Trạng thái thực của server**: DEADLINE_EXCEEDED không chứng minh thao tác đã thất bại.

Một request tạo đơn có thể mang idempotency key:

~~~proto
message CreateOrderRequest {
  string customer_id = 1;
  string idempotency_key = 2;
}

message CreateOrderResponse {
  string order_id = 1;
}
~~~

Chỉ thêm field không tự bảo đảm idempotency. Implementation phải lưu, kiểm tra và đồng bộ hóa key để nhiều request cùng key không tạo nhiều đơn. Khi caller không biết kết quả ghi sau timeout, nên tra cứu trạng thái theo key hoặc đối soát, thay vì gửi lại mù quáng.

| Trường hợp | Retry ngay? | Hướng xử lý |
| --- | --- | --- |
| GetOrder trả **INVALID_ARGUMENT** | Không | Sửa request |
| GetOrder trả **NOT_FOUND** | Thường không | Xử lý tài nguyên không có |
| GetOrder trả **UNAVAILABLE** | Có thể | Backoff/jitter, giới hạn số lần |
| RPC trả **RESOURCE_EXHAUSTED** | Theo quota/policy | Giảm tốc độ, không gây thêm quá tải |
| GetOrder vượt **DEADLINE_EXCEEDED** | Tùy use case | Chỉ retry nếu còn thời gian và thao tác an toàn |
| CreateOrder vượt deadline | Không retry mù | Tra cứu bằng idempotency key/đối soát |
| Người dùng chủ động **CANCELLED** | Không | Dừng công việc và cleanup |
| RPC trả **PERMISSION_DENIED** | Không | Kiểm tra phân quyền |

gRPC Java có thể hỗ trợ retry theo service config/chính sách, nhưng **retry transport không thay thế tính an toàn nghiệp vụ**.

## 11. Rich error details, trailers và bảo mật

Server trả lỗi bằng **io.grpc.Status**:

~~~java
responseObserver.onError(
        Status.FAILED_PRECONDITION
                .withDescription("Đơn hàng đã chốt, không thể chỉnh sửa")
                .asRuntimeException());
~~~

Runtime ghi status vào gRPC trailers. **Không tự đặt grpc-status** dưới dạng custom metadata. Với lỗi có cấu trúc phức tạp, hệ sinh thái gRPC có thể dùng **google.rpc.Status** và các error details, nếu cả client và server đã thống nhất hỗ trợ.

Client blocking stub đọc status:

~~~java
try {
    blockingStub.getOrder(request);
} catch (StatusRuntimeException error) {
    Status.Code code = error.getStatus().getCode();
    String description = error.getStatus().getDescription();

    // Phân nhánh theo code; description chỉ để chẩn đoán.
    // error.getTrailers() có thể trả null.
}
~~~

**StatusRuntimeException.getTrailers()** có thể là **null** khi lỗi xảy ra trước khi nhận phản hồi. Không viết logic dựa trên giả định mọi lời gọi lỗi đều có trailers. Không đưa token, stack trace, SQL hoặc thông tin hạ tầng nhạy cảm vào **description** hay metadata gửi cho client.

## 12. Kiểm thử status qua grpc-inprocess

Kiểm thử bằng cách gọi trực tiếp Java method của handler không đi qua generated stub và gRPC runtime. **InProcessServerBuilder** và **InProcessChannelBuilder** cho phép kiểm chứng RPC/status qua runtime mà không chiếm cổng TCP.

### 12.1. Kiểm thử unary thành công và lỗi

Ví dụ JUnit 5 với **OrderEndpoint** ở mục 8, yêu cầu thư viện **grpc-inprocess** tương thích grpc-java:

~~~java
package dev.example.orders.server;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class OrderEndpointTest {

    @Test
    void shouldReturnResponseAndExpectedErrors() throws Exception {
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new OrderEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(channel);

            GetOrderResponse found = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-42")
                            .build());
            assertEquals("PENDING", found.getState());

            StatusRuntimeException invalid = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.getOrder(
                            GetOrderRequest.newBuilder().build()));
            assertEquals(Status.Code.INVALID_ARGUMENT,
                    invalid.getStatus().getCode());

            StatusRuntimeException missing = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.getOrder(
                            GetOrderRequest.newBuilder()
                                    .setOrderId("missing")
                                    .build()));
            assertEquals(Status.Code.NOT_FOUND,
                    missing.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**directExecutor()** tiện cho test nhỏ, nhưng không mô phỏng hệ thống xử lý chặn hoặc tương tranh phức tạp. Khi thử deadline/cancellation, nên dùng executor phù hợp và đồng bộ bằng latch/tín hiệu thay vì dựa vào các khoảng **Thread.sleep** không ổn định.

### 12.2. Kiểm thử DEADLINE_EXCEEDED

Trong một test riêng, có thể đăng ký handler cố ý **không hoàn tất RPC**, chỉ để runtime client tự hết deadline:

~~~java
OrderServiceGrpc.OrderServiceImplBase neverResponds =
        new OrderServiceGrpc.OrderServiceImplBase() {
            @Override
            public void getOrder(
                    GetOrderRequest request,
                    StreamObserver<GetOrderResponse> observer) {
                // Chỉ trong test: chưa gọi terminal callback.
            }
        };
~~~

Đăng ký **neverResponds** trên một server in-process riêng; với blocking stub kết nối vào server đó:

~~~java
StatusRuntimeException expired = assertThrows(
        StatusRuntimeException.class,
        () -> stub.withDeadlineAfter(200, TimeUnit.MILLISECONDS)
                .getOrder(
                        GetOrderRequest.newBuilder()
                                .setOrderId("order-42").build()));

assertEquals(Status.Code.DEADLINE_EXCEEDED,
        expired.getStatus().getCode());
~~~

Hai snippet bổ sung vào khung test, cần import **StreamObserver** và **TimeUnit**. Handler treo chỉ dùng để test, không phải thiết kế production. Với CI, chọn deadline đủ rộng để hạn chế test bị flaky khi máy bận.

### 12.3. Kiểm thử cancellation

Với streaming async, mở RPC từ **CancellableContext**, ghi nhận **onError** ở client và **setOnCancelHandler** ở server, rồi gọi **cancel()**. Kiểm tra:

- Client kết thúc với status tương ứng, thường là **CANCELLED** khi hủy chủ động.
- Server nhận cancellation và đóng nguồn event/job nền.
- Không còn message được phát sau terminal event.
- Channel vẫn dùng được cho một RPC khác.
- Không có rò rỉ tài nguyên nếu hủy và response hoàn tất gần đồng thời.

Cancellation là sự kiện bất đồng bộ; dùng **CountDownLatch** hoặc tín hiệu tương tự để chờ và xác minh, đừng đọc ngay biến trạng thái server trong cùng dòng sau cancel rồi cho rằng callback đã chạy.

### 12.4. Giới hạn kiểm thử in-process

In-process test giúp kiểm tra API, status, context và registration, nhưng **không chứng minh** TLS, HTTP/2 proxy, DNS, load balancing, reconnect hoặc lỗi TCP đã được xử lý đúng. Với môi trường triển khai thật, cần kiểm thử thêm transport TLS/mTLS, graceful shutdown và những trường hợp backend ngắt kết nối.

## 13. Giám sát deadline, cancellation và độ tin cậy

Trong ứng dụng Spring gRPC, nên đo ở cả client và server:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Latency p50/p95/p99 theo full method name** | RPC nào chậm và chậm ở tầng nào? |
| **Status.Code theo method** | Tỉ lệ lỗi INVALID_ARGUMENT, UNAVAILABLE, DEADLINE_EXCEEDED... |
| **Deadline exceeded rate** | Có bao nhiêu caller không nhận được kết quả đúng hạn? |
| **Cancellation count** | Bao nhiêu stream bị hủy; do user hay hệ thống? |
| **In-flight RPC / active streams** | Tải đang tồn đọng và số luồng dài đang mở |
| **Retry attempts / final outcome** | Retry giúp hồi phục hay nhân tải? |
| **Work after cancellation** | Có job nào vẫn chạy khi caller không còn chờ? |
| **Downstream latency** | Dependency nào tiêu thụ phần lớn ngân sách deadline? |

Tracing có thể liên kết client RPC với server handler và các lời gọi downstream. Tránh nhét token, order ID hoặc request ID có cardinality cao vào metric label; thông tin trace/correlation cần có chính sách bảo mật rõ ràng.

Nếu p99 của **GetOrder** là 1.500 ms nhưng deadline 800 ms, chỉ tăng deadline có thể làm giảm lỗi timeout trên giấy tờ mà tăng thời gian user phải chờ và số RPC tồn đọng. Trước hết cần phân tích connection time, server queue, handler, database và retry storm.

## 14. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| RPC vừa bắt đầu đã **DEADLINE_EXCEEDED** | Stub singleton được gắn deadline từ lúc tạo bean | Gắn deadline cho từng RPC |
| Hủy một stream làm hỏng nhiều RPC khác | Đóng ManagedChannel dùng chung | Chỉ hủy RPC liên quan |
| Server tiếp tục chạy job sau khi client hủy | Không kiểm tra Context hoặc thiếu cancel handler | Cleanup subscription và tác vụ nền |
| Client-streaming không có response | Client chưa half-close request observer | Gọi onCompleted phía gửi, chờ response |
| HTTP 200 nhưng RPC lỗi | Chỉ đọc HTTP status | Đọc grpc-status/StatusRuntimeException |
| Server trả UNKNOWN/INTERNAL cho mọi lỗi | Không ánh xạ exception nghiệp vụ | Chọn Status.Code phù hợp |
| Retry gây tạo đơn trùng | RPC ghi không idempotent; timeout không rõ kết quả | Idempotency key và đối soát |
| RPC downstream chạy quá hạn caller | Context bị mất ở executor riêng | Propagate Context và ngân sách còn lại |
| Stream vẫn phát sau khi đã hủy | Producer không dừng, race với terminal state | Điều phối producer và cleanup |
| Proxy ngắt streaming dù deadline còn | Idle timeout hoặc cấu hình HTTP/2/TLS | Test proxy và điều chỉnh policy |
| Timeout tăng khi tải cao | Queue dài, backend chậm, retry storm | Phân tích latency, giới hạn in-flight |
| Status description lộ bí mật | Trả nguyên exception nội bộ | Sanitize status, log lỗi chi tiết ở server |

Khi chẩn đoán, hãy theo dõi tuần tự **client deadline → Channel/transport → server queue → handler → downstream → status/trailers**. Điều này giúp phân biệt nguyên nhân thời gian, lỗi nghiệp vụ và hạ tầng.

## 15. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành: OrderService có giới hạn thời gian và hỗ trợ hủy

1. Sinh mã Java từ hợp đồng **OrderService** ở mục 2; tạo Spring client/server và dùng chung Channel.
2. Triển khai **GetOrder** trả **INVALID_ARGUMENT** khi ID rỗng, **NOT_FOUND** khi không có đơn và **OK** khi tồn tại.
3. Gọi GetOrder với deadline dài, sau đó mô phỏng xử lý vượt deadline để quan sát **DEADLINE_EXCEEDED**.
4. Đọc **Context.current().getDeadline()** và **isCancelled()** tại server. Thử chuyển công việc sang executor riêng và truyền Context đúng cách.
5. Gọi **WatchOrder** bằng async stub, chủ động hủy bằng **CancellableContext**, kiểm tra cancel handler của server và cleanup.
6. Mô phỏng thao tác tạo đơn đã commit trước khi caller timeout; thiết kế cơ chế idempotency/đối soát để tránh trùng.
7. Viết JUnit in-process test cho status, deadline và cancellation, rồi kiểm thử transport TLS/HTTP2 thật khi hệ thống có proxy.
8. Theo dõi latency, các mã status và số RPC bị hủy, so sánh metrics client/server.

### Câu hỏi tự kiểm tra

**1. Deadline khác timeout ra sao?**  
Deadline là hạn cuối cho RPC; timeout là khoảng thời gian dùng để tính hạn đó. **withDeadlineAfter** đặt deadline từ thời lượng tương đối.

**2. Khi client thấy DEADLINE_EXCEEDED, server có chắc chưa ghi dữ liệu?**  
**Không.** Server có thể đã commit. Phải dùng idempotency hoặc đối soát với thao tác có tác dụng phụ.

**3. onCompleted() của request observer có phải cancellation không?**  
**Không.** Đó là half-close chiều gửi trong client/bidirectional streaming.

**4. Vì sao không đóng Channel để hủy một RPC?**  
Channel dùng chung cho nhiều lời gọi. Đóng Channel có thể làm ảnh hưởng những RPC khác.

**5. NOT_FOUND khác UNIMPLEMENTED thế nào?**  
**NOT_FOUND** là tài nguyên nghiệp vụ không có; **UNIMPLEMENTED** là service/method RPC không được runtime hỗ trợ.

**6. Server phát hiện cancellation bằng API nào?**  
Có thể kiểm tra **Context.current().isCancelled()**, **ServerCallStreamObserver.isCancelled()** và sử dụng **setOnCancelHandler(...)**.

**7. HTTP 200 có đảm bảo gRPC OK không?**  
**Không.** Kết quả RPC nằm ở **grpc-status** trong trailers.

**8. Có nên retry mọi UNAVAILABLE/DEADLINE_EXCEEDED không?**  
Không. Cần xét tính an toàn của thao tác, deadline còn lại, backoff và trạng thái server có thể đã thực thi.

**9. Deadline tự lan sang mọi CompletableFuture không?**  
Không nên giả định vậy. Cần truyền **io.grpc.Context** cho executor/thread tùy chỉnh.

## Tổng kết

**Deadline** giới hạn thời gian caller chờ một RPC; **cancellation** cho phép ngừng công việc không còn cần; **gRPC status** mô tả kết quả bằng mã chuẩn và độc lập với HTTP status. Trong Spring gRPC, hãy đặt deadline **theo từng lời gọi**, truyền **Context** cho downstream/async work, quản lý **StreamObserver** và cancel handler đúng vòng đời, đồng thời ánh xạ lỗi sang **Status.Code** phù hợp. Với RPC có tác dụng phụ, cần retry có kiểm soát và **idempotency**, vì timeout không bảo đảm server chưa commit. Kiểm thử in-process, kiểm thử transport thật và metrics/tracing theo method giúp dịch vụ unary/streaming ổn định và dễ chẩn đoán.



