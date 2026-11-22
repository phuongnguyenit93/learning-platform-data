# Service definition trong Protocol Buffers

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **service definition** trong hợp đồng gRPC và cách nó kết nối client, server với runtime HTTP/2.
- Viết được một file **.proto** theo cú pháp **proto3**, gồm **package**, **message**, **enum**, **service** và phương thức **rpc**.
- Phân biệt kiểu request/response với bốn dạng lời gọi **unary**, **server streaming**, **client streaming** và **bidirectional streaming**.
- Hiểu cách **protoc** và plugin gRPC Java tạo **message class**, **method descriptor**, **client stub** và lớp cơ sở cho server.
- Thiết kế tên dịch vụ, số hiệu trường dữ liệu và phiên bản hợp đồng để client/server thay đổi an toàn.
- Liên hệ hợp đồng Protocol Buffers với cách đăng ký implementation, gọi stub, xử lý status/deadline, kiểm thử và vận hành trong Spring.

## 1. Service definition nằm ở đâu trong kiến trúc gRPC?

Trong **SPRING_GRPC**, điểm xuất phát là **hợp đồng Protocol Buffers**. Hợp đồng này mô tả những RPC một service cung cấp, loại thông điệp đi vào và đi ra, cùng việc mỗi phía gửi **một hay nhiều message**. Từ đó, công cụ sinh mã tạo API Java để client gọi và server triển khai; thư viện gRPC vận chuyển message qua HTTP/2.

Ví dụ một hệ thống đơn hàng có service **OrderService**, trong đó client gọi **GetOrder** với mã đơn hàng và nhận dữ liệu đơn hàng.

~~~mermaid
flowchart LR
    P["order_service.proto<br/>service + rpc + message"] --> G["protoc + gRPC Java plugin"]
    G --> C["Generated client stubs"]
    G --> S["Generated server base + descriptors"]
    C --> H["ManagedChannel / HTTP/2"]
    H --> R["gRPC server transport"]
    R --> I["Spring service implementation"]
    S --> I
~~~

Các khối trong sơ đồ có trách nhiệm riêng:

| Thành phần | Quy định hoặc thực hiện điều gì? |
| --- | --- |
| **File .proto** | Tên service, tên method, kiểu request/response, streaming cardinality, cấu trúc dữ liệu |
| **Mã được sinh** | API Java, bộ tuần tự/giải mã protobuf và mô tả phương thức RPC |
| **Client stub** | Đóng gói lời gọi Java thành RPC thông qua Channel |
| **Server runtime** | Nhận HTTP/2, giải mã request và định tuyến tới handler đã đăng ký |
| **Server implementation** | Thực hiện nghiệp vụ, trả response hoặc mã lỗi gRPC |
| **Cấu hình môi trường** | Địa chỉ server, TLS, deadline, authentication, retry, cân bằng tải, metrics |

**Service definition là hợp đồng API**, không phải implementation, bản khai địa chỉ kết nối hoặc cấu hình bảo mật. File **.proto** không tự mở server: sau khi sinh mã, ứng dụng vẫn phải tạo/đăng ký service implementation để nhận RPC.

Một request HTTP/2 thường mang đường dẫn dạng:

~~~text
/<protobuf-package>.<ServiceName>/<MethodName>
~~~

Với package **orders.v1**, service **OrderService** và method **GetOrder**, đường dẫn đầy đủ là:

~~~text
/orders.v1.OrderService/GetOrder
~~~

Đường dẫn này là một phần danh tính RPC trên mạng. Nó khác với tên package Java và URL host/cổng mà client cấu hình trong Channel.

## 2. Cấu trúc của một file .proto

Hãy tạo file **order_service.proto** với ví dụ hoàn chỉnh sau:

~~~proto
syntax = "proto3";

package orders.v1;

option java_package = "com.example.orders.grpc.v1";
option java_multiple_files = true;
option java_outer_classname = "OrderProto";

service OrderService {
  // Một yêu cầu, một phản hồi.
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);

  // Một yêu cầu, một chuỗi phản hồi.
  rpc ListOrders(ListOrdersRequest) returns (stream Order);

  // Một chuỗi yêu cầu, một phản hồi tổng hợp.
  rpc UploadEvents(stream OrderEvent) returns (UploadSummary);

  // Hai chiều có thể trao đổi thông điệp xen kẽ.
  rpc Synchronize(stream SyncRequest) returns (stream SyncResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  Order order = 1;
}

message ListOrdersRequest {
  string customer_id = 1;
}

message Order {
  string id = 1;
  string customer_id = 2;
  OrderState state = 3;
  int64 created_at_epoch_ms = 4;
}

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_COMPLETED = 2;
}

message OrderEvent {
  string order_id = 1;
  string event_type = 2;
}

message UploadSummary {
  int32 accepted_count = 1;
}

message SyncRequest {
  string cursor = 1;
}

message SyncResponse {
  string cursor = 1;
  Order order = 2;
}
~~~

Đây là một hợp đồng ví dụ dùng để học. Các trường như **cursor**, **event_type** và **created_at_epoch_ms** cần được định nghĩa rõ ý nghĩa ở tài liệu API của sản phẩm thật; cú pháp proto chỉ xác định kiểu và danh tính trường.

### 2.1. Giải thích từng cấu phần

| Thành phần | Tác dụng |
| --- | --- |
| **syntax = "proto3"** | Chọn cú pháp Protocol Buffers phiên bản proto3 |
| **package orders.v1** | Định danh namespace protobuf; góp phần tạo tên service đầy đủ trên giao thức |
| **java_package** | Đặt package cho các lớp Java được sinh |
| **java_multiple_files = true** | Sinh nhiều lớp Java cấp cao nhất cho message, enum và service-related classes, thay vì chỉ lồng chúng vào một outer class |
| **java_outer_classname** | Định tên lớp outer dùng cho những thành phần mã Java cần được gom vào lớp này, chẳng hạn file descriptor |
| **service OrderService** | Khai báo nhóm các phương thức RPC |
| **rpc GetOrder(...) returns (...)** | Khai báo tên method và kiểu thông điệp request/response |
| **stream** | Chỉ ra hướng có thể truyền nhiều message trong một RPC |
| **message** | Khai báo kiểu dữ liệu trao đổi |
| **enum** | Khai báo tập giá trị mã hóa bằng số nguyên |
| **= 1, = 2, ...** | Số hiệu trường dữ liệu (*field number*) dùng trong định dạng nhị phân protobuf |

Đừng nhầm **package** protobuf với **java_package**:

- **package orders.v1** xác định tên service đầy đủ **orders.v1.OrderService** và các tên protobuf trong descriptor.
- **java_package com.example.orders.grpc.v1** quyết định vị trí các lớp Java được sinh.
- Thay đổi **java_package** có thể làm mã Java cần cập nhật import ngay cả khi tên RPC ở tầng mạng không đổi.
- Thay đổi **package** protobuf làm đổi tên service đầy đủ và đường dẫn RPC, do đó có thể làm client cũ không gọi được method nếu server không còn đăng ký tên cũ.

Tên file **order_service.proto** giúp tổ chức mã nguồn, nhưng đường dẫn RPC không lấy từ tên file. Đối với gRPC, định danh phương thức đến từ **package + service + method**.

### 2.2. Khai báo message và field number

Trong **message**, mỗi field gồm **kiểu**, **tên** và **số hiệu duy nhất**:

~~~proto
message GetOrderRequest {
  string order_id = 1;
}
~~~

Ở wire format của Protocol Buffers, **field number** là một phần của khóa mã hóa. Bên nhận dựa vào số hiệu và kiểu wire để giải mã; tên trường chủ yếu phục vụ source code, công cụ và định dạng như ProtoJSON.

Một số kiểu thường gặp:

| Kiểu proto | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **string** | Chuỗi UTF-8 | Proto3 thường trả chuỗi rỗng nếu không hiện diện |
| **int32 / int64** | Số nguyên có dấu | Xem xét kích thước/range và chuyển đổi với Java |
| **bool** | Giá trị đúng/sai | Giá trị mặc định là false |
| **bytes** | Dữ liệu nhị phân | Thích hợp cho payload nhị phân cần định dạng rõ |
| **enum** | Mã trạng thái được định nghĩa trước | Nên khai báo giá trị 0 có nghĩa "UNSPECIFIED"/"UNKNOWN" |
| **MessageType** | Một thông điệp lồng nhau | Có đặc tính hiện diện riêng của message field |
| **repeated T** | Danh sách nhiều phần tử | Danh sách rỗng nếu không có phần tử |
| **map<K, V>** | Bảng khóa-giá trị | Khóa có loại cho phép theo protobuf; không dùng làm thứ tự nghiệp vụ |

Trong proto3, **scalar field thông thường** như string, int32 và bool không phân biệt trực tiếp "không được gửi" với "được gửi bằng giá trị mặc định" qua accessor cơ bản. Khi cần nhận biết việc một scalar có được gán hay chưa, cân nhắc **optional**:

~~~proto
message UpdateOrderRequest {
  string order_id = 1;
  optional string note = 2;
}
~~~

Trong Java sinh mã từ proto3 hỗ trợ optional, ứng dụng có thể kiểm tra **hasNote()** để phân biệt "không cập nhật note" và "cập nhật note thành chuỗi rỗng". Không nên tự suy ra giá trị 0 hoặc chuỗi rỗng luôn có nghĩa "chưa truyền".

Khi dữ liệu chỉ có thể thuộc **một trong nhiều kiểu loại trừ nhau**, dùng **oneof**:

~~~proto
message LookupOrderRequest {
  oneof key {
    string order_id = 1;
    string external_reference = 2;
  }
}
~~~

**oneof** mô tả tính loại trừ ở tầng dữ liệu. Nó không thay thế việc kiểm tra hợp lệ, phân quyền hoặc ràng buộc nghiệp vụ ở implementation.

## 3. Từ cú pháp rpc đến bốn kiểu giao tiếp

Dạng tổng quát của một method trong service là:

~~~proto
rpc MethodName(RequestType) returns (ResponseType);
~~~

Thêm **stream** ở phía request hoặc response để xác định chiều truyền nhiều message:

| Kiểu RPC | Khai báo .proto | Số request/response logic | Ví dụ |
| --- | --- | --- | --- |
| **Unary** | **rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);** | 1 request, 1 response | Lấy một đơn hàng theo ID |
| **Server streaming** | **rpc ListOrders(ListOrdersRequest) returns (stream Order);** | 1 request, 0..n response | Phát danh sách đơn hàng theo từng message |
| **Client streaming** | **rpc UploadEvents(stream OrderEvent) returns (UploadSummary);** | 0..n request, 1 response | Client gửi các sự kiện, server trả thống kê |
| **Bidirectional streaming** | **rpc Synchronize(stream SyncRequest) returns (stream SyncResponse);** | 0..n request, 0..n response | Đồng bộ tiến độ giữa hai hệ thống |

**stream** là từ khóa trong hợp đồng, không phải tên một HTTP/2 connection. Mỗi lời gọi gRPC sử dụng **một HTTP/2 stream**, và bên trong có thể chứa nhiều gRPC message. Nếu một method gửi 200 bản ghi từ server, nó vẫn là **một RPC** với **một HTTP/2 stream**, không phải 200 RPC độc lập.

### 3.1. Chọn kiểu RPC theo nhu cầu

**Unary** phù hợp cho yêu cầu ngắn, kết quả hữu hạn: đọc thông tin, ghi một thay đổi, xác thực một hành động. Dễ kiểm thử và dễ thể hiện trong luồng xử lý đồng bộ.

**Server streaming** phù hợp khi một request dẫn tới kết quả được phát dần, như dữ liệu lớn, cập nhật liên tục hoặc tiến trình dài. Client phải xử lý **onNext** nhiều lần, backpressure và cancellation.

**Client streaming** phù hợp cho upload theo từng phần hoặc gom nhiều bản ghi; client đóng **chiều gửi** sau message cuối, rồi chờ phản hồi tổng hợp. Server cần giới hạn số bản ghi, kích thước và thời gian xử lý.

**Bidirectional streaming** phù hợp với tương tác hai chiều liên tục. Hai phía có thể phát message độc lập và xen kẽ; không nên giả định cứ gửi một request thì lập tức có đúng một response.

**Lưu ý về kiểu trả về:** gRPC yêu cầu mọi method có một kiểu request và một kiểu response được khai báo rõ. Nếu không cần payload, có thể dùng **google.protobuf.Empty**:

~~~proto
import "google/protobuf/empty.proto";

service HealthControl {
  rpc ResetCache(google.protobuf.Empty) returns (google.protobuf.Empty);
}
~~~

Cần dùng Empty theo ngữ nghĩa API; với thao tác quan trọng, một response có trạng thái nghiệp vụ và phiên bản rõ ràng thường hữu ích hơn.

### 3.2. Định nghĩa không nói lên toàn bộ giao thức ứng dụng

Với **Synchronize**, proto chỉ cho biết có nhiều **SyncRequest** và **SyncResponse**. Nó chưa xác định:

- Mỗi response có tương ứng một request hay không.
- Thông điệp có phải theo thứ tự nhất định, có checkpoint hay retry hay không.
- **cursor** dùng làm dấu mốc chính xác như thế nào.
- Điều kiện kết thúc, giới hạn message và cách xử lý khi client hủy.

Các quy tắc này cần được tài liệu hóa và triển khai nhất quán. Đối với streaming dài, thiết kế protocol cấp ứng dụng thường cần message loại **start/data/ack/end**, hoặc **oneof** kèm enum để thể hiện trạng thái, thay vì chỉ dựa vào stream ở chữ ký rpc.

## 4. Code generation tạo ra những gì?

Sau khi định nghĩa hợp đồng, pipeline sinh mã thường có hai phần:

1. **protoc + bộ sinh Java protobuf** tạo lớp **message/enum**, builder, parser và file descriptor.
2. **protoc-gen-grpc-java** tạo lớp hỗ trợ gRPC, method descriptor, stub và lớp cơ sở server.

Ví dụ với **java_multiple_files = true** ở mục 2, các lớp Java đáng chú ý thường là:

| Thành phần được sinh | Vai trò |
| --- | --- |
| **GetOrderRequest**, **GetOrderResponse**, **Order** | Dữ liệu protobuf và API builder/accessor |
| **OrderState** | Kiểu enum Java tương ứng enum protobuf |
| **OrderProto** | File-level descriptor và thành phần metadata hỗ trợ |
| **OrderServiceGrpc** | Service descriptor, method descriptor, factory tạo stub |
| **OrderServiceGrpc.OrderServiceImplBase** | Lớp cơ sở để server override phương thức |
| **OrderServiceGrpc.OrderServiceBlockingStub** | API blocking, thường dùng cho unary/server streaming |
| **OrderServiceGrpc.OrderServiceStub** | API async, dùng được cho mọi dạng RPC |
| **OrderServiceGrpc.OrderServiceFutureStub** | API future, chủ yếu cho unary |

**Không sửa code được sinh trực tiếp.** Khi thay đổi service definition, sửa file **.proto** và chạy lại code generation, sau đó cập nhật các implementation/caller bị ảnh hưởng.

### 4.1. Các chữ ký Java thường thấy

Ví dụ các method phía server khi dùng base API gRPC Java truyền thống:

~~~java
@Override
public void getOrder(
        GetOrderRequest request,
        StreamObserver<GetOrderResponse> responseObserver) {
    // unary
}

@Override
public void listOrders(
        ListOrdersRequest request,
        StreamObserver<Order> responseObserver) {
    // server streaming
}

@Override
public StreamObserver<OrderEvent> uploadEvents(
        StreamObserver<UploadSummary> responseObserver) {
    // client streaming
    // Trả về observer nhận từng OrderEvent.
}

@Override
public StreamObserver<SyncRequest> synchronize(
        StreamObserver<SyncResponse> responseObserver) {
    // bidirectional streaming
}
~~~

Đây là **minh họa chữ ký** để hiểu sự khác biệt; các method chưa có phần xử lý sẽ cần triển khai đầy đủ trong lớp server thật. Các kiểu được import từ package Java sinh mã đã chọn, và **StreamObserver** thuộc **io.grpc.stub.StreamObserver**.

Ở phía client:

- **BlockingStub.getOrder(request)** trả về **GetOrderResponse** hoặc ném **StatusRuntimeException**.
- **BlockingStub.listOrders(request)** thường trả về **Iterator<Order>**.
- **AsyncStub.uploadEvents(responseObserver)** trả về **StreamObserver<OrderEvent>** để client gửi nhiều request.
- **AsyncStub.synchronize(responseObserver)** trả về **StreamObserver<SyncRequest>** cho trao đổi hai chiều.

Cách gọi API phản ánh trực tiếp từ khóa **stream** của mỗi phía trong file .proto. Một số phiên bản/cấu hình generator có thể cung cấp thêm API khác, nhưng nguyên lý mapping không đổi.

### 4.2. Service descriptor và định tuyến RPC

Một gRPC service không được định tuyến bằng tên phương thức Java bất kỳ. Runtime dựa vào descriptor của service và method, ví dụ:

~~~java
String fullServiceName =
        OrderServiceGrpc.getServiceDescriptor().getName();
// "orders.v1.OrderService"

String fullMethodName =
        OrderServiceGrpc.getGetOrderMethod().getFullMethodName();
// "orders.v1.OrderService/GetOrder"
~~~

Khi nhận request, server định tuyến **/orders.v1.OrderService/GetOrder** tới handler được đăng ký cho method đó. Descriptor cung cấp tên, kiểu request/response, loại RPC và marshaller cần thiết; việc gắn logic xử lý là trách nhiệm của implementation.

Với hệ sinh thái công cụ, descriptor còn được dùng cho kiểm thử hợp đồng, server reflection nếu được bật và các client động. **Reflection** không tự bật chỉ vì đã sinh descriptor; server phải đăng ký/dùng cơ chế hỗ trợ reflection phù hợp.

## 5. Tích hợp hợp đồng với Spring server

Giả sử server cần hỗ trợ unary **GetOrder**. Một lớp Spring bean có thể kế thừa API gRPC sinh mã:

~~~java
package com.example.orders.server;

import com.example.orders.grpc.v1.GetOrderRequest;
import com.example.orders.grpc.v1.GetOrderResponse;
import com.example.orders.grpc.v1.Order;
import com.example.orders.grpc.v1.OrderServiceGrpc;
import com.example.orders.grpc.v1.OrderState;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderGrpcEndpoint extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        String id = request.getOrderId().trim();
        if (id.isEmpty()) {
            responseObserver.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id không được rỗng")
                            .asRuntimeException());
            return;
        }

        // Dữ liệu minh họa; triển khai thật lấy từ tầng nghiệp vụ/repository.
        Order order = Order.newBuilder()
                .setId(id)
                .setCustomerId("customer-100")
                .setState(OrderState.ORDER_STATE_PENDING)
                .setCreatedAtEpochMs(1_700_000_000_000L)
                .build();

        responseObserver.onNext(
                GetOrderResponse.newBuilder().setOrder(order).build());
        responseObserver.onCompleted();
    }
}
~~~

Chữ ký **getOrder** phải khớp method đã sinh: **GetOrderRequest** vào, **StreamObserver<GetOrderResponse>** ra. Gọi **onNext** để phát response, sau đó **onCompleted** để kết thúc thành công. Nếu request không hợp lệ, gọi **onError** với mã gRPC thích hợp và dừng xử lý. Không gọi **onCompleted** sau **onError** hay phát thêm message sau terminal event.

Một service definition có thể chứa bốn method, nhưng không có nghĩa implementation minh họa ở trên đã hoàn chỉnh tất cả: các phương thức chưa override sẽ dùng hành vi mặc định của lớp cơ sở, thường trả **UNIMPLEMENTED** khi được gọi. Vì thế, phải kiểm tra các RPC thực sự được yêu cầu trước khi công bố service.

### 5.1. Đăng ký service với runtime

Nếu dùng API grpc-java cơ bản trong Spring:

~~~java
package com.example.orders.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfiguration {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderGrpcServer(OrderGrpcEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

Đây là ví dụ **grpc-java do Spring quản lý bean**, tách biệt với cơ chế tự cấu hình của một starter Spring gRPC. Nếu framework đang dùng tự đăng ký service bean và quản lý server, hãy theo cơ chế đó thay vì tạo thêm server cùng cổng.

**@Component** giúp Spring quản lý instance implementation, còn **addService(endpoint)** giúp gRPC server biết method nào đang được cung cấp. Hai việc này phục vụ hai tầng khác nhau.

## 6. Client dùng stub theo hợp đồng đã sinh

Ứng dụng client có thể tạo **ManagedChannel** dùng chung và tạo blocking stub từ Channel:

~~~java
package com.example.orders.client;

import com.example.orders.grpc.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        // Chỉ dành cho thử nghiệm local.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderBlockingStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

Service Spring gọi **GetOrder** như sau:

~~~java
package com.example.orders.client;

import com.example.orders.grpc.v1.GetOrderRequest;
import com.example.orders.grpc.v1.GetOrderResponse;
import com.example.orders.grpc.v1.OrderServiceGrpc;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderLookupClient(
            OrderServiceGrpc.OrderServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse getOrder(String id) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(id)
                .build();

        try {
            return stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException error) {
            // Tầng ứng dụng ánh xạ status theo use case và chính sách retry.
            throw new IllegalStateException(
                    "GetOrder lỗi: " + error.getStatus().getCode(),
                    error);
        }
    }
}
~~~

Những gì file .proto quyết định ở đây là: method **getOrder**, kiểu **GetOrderRequest** và kiểu **GetOrderResponse**. Địa chỉ **localhost:9090**, deadline **2 giây**, TLS và xử lý exception là quyết định ở tầng client/runtime. Hàm **withDeadlineAfter** tạo stub với call options mới; nên cấu hình deadline gần thời điểm gọi.

Ví dụ sử dụng **usePlaintext()** để đơn giản hóa chạy local. Khi triển khai thật, cần cấu hình TLS, certificate/trust và cơ chế xác thực phù hợp. Tái sử dụng Channel thay vì tạo Channel mới trong mỗi lần gọi để tránh phát sinh kết nối không cần thiết.

## 7. Thiết kế service definition có thể phát triển lâu dài

Một service definition ổn định cần được xem như **API công khai đối với các client đang dùng**. Khi nhiều team triển khai client/server độc lập, thay đổi schema thiếu kiểm soát có thể gây lỗi biên dịch hoặc lỗi lúc chạy.

### 7.1. Quy tắc đặt tên

- Dùng tên service thể hiện một năng lực nghiệp vụ, ví dụ **OrderService** thay vì **GlobalService**.
- Dùng tên RPC bắt đầu bằng động từ rõ hành động, ví dụ **GetOrder**, **ListOrders**, **CreateOrder**; giữ nhất quán trong một API.
- Dùng **snake_case** cho tên field, **PascalCase** cho message/service và **UPPER_SNAKE_CASE** cho giá trị enum.
- Dùng package có phiên bản như **orders.v1** khi cần quản lý thay đổi lớn. Không thay đổi tên package tùy tiện khi đã có client.
- Tránh đặt tên message chỉ là **Request**, **Result** vì dễ trùng/khó đọc; **GetOrderRequest** mang ngữ cảnh rõ hơn.
- Chú thích các trường có quy tắc nghiệp vụ, định dạng hoặc giới hạn đặc biệt: đơn vị thời gian, phạm vi cursor, idempotency, ý nghĩa empty/null.

Các nguyên tắc đặt tên là quy ước thiết kế API để dễ bảo trì; chúng cần được thống nhất trong dự án. Chúng không phải điều kiện bắt buộc của trình biên dịch protobuf.

### 7.2. Tương thích khi chỉnh message

Xét trường **Order** ban đầu:

~~~proto
message Order {
  string id = 1;
  string customer_id = 2;
  OrderState state = 3;
  int64 created_at_epoch_ms = 4;
}
~~~

Muốn thêm thông tin mô tả, cách thường tương thích hơn là **thêm field mới với số hiệu mới**:

~~~proto
message Order {
  string id = 1;
  string customer_id = 2;
  OrderState state = 3;
  int64 created_at_epoch_ms = 4;
  optional string description = 5;
}
~~~

Client cũ thường bỏ qua field **5** mà chưa biết; client mới vẫn đọc được message từ server cũ, lúc đó **description** chưa hiện diện. Tuy nhiên, **wire compatibility không tự đảm bảo semantic compatibility**: nếu nghiệp vụ bắt buộc description luôn có giá trị thì client/server cũ có thể không đáp ứng yêu cầu mới.

**Không tái sử dụng field number** đã phát hành cho ý nghĩa khác. Khi xóa field, dùng **reserved** để ngăn vô tình tái sử dụng:

~~~proto
message OrderPatch {
  reserved 2, 5;
  reserved "legacy_note", "old_status";

  string order_id = 1;
  optional string description = 3;
  optional int64 expected_version = 4;
}
~~~

**reserved** không loại bỏ dữ liệu cũ khỏi message đã lưu hoặc hỗ trợ migration; nó giúp compiler từ chối việc định nghĩa lại số hiệu/tên đã dành riêng.

Bảng quyết định khi thay schema:

| Thay đổi | Đánh giá thông thường | Lý do |
| --- | --- | --- |
| Thêm field với số hiệu chưa dùng | Thường tương thích ở wire format | Client cũ có thể bỏ qua field chưa biết |
| Xóa field và đánh dấu reserved | Có thể giữ wire compatibility, cần xét logic | Client cũ có thể vẫn gửi/đọc field cũ với giá trị mặc định hoặc bị bỏ qua |
| Đổi số hiệu của field đang dùng | **Breaking** | Bên nhận giải mã thành trường khác hoặc bỏ qua |
| Tái sử dụng số hiệu cũ cho ý nghĩa mới | **Nguy hiểm/breaking** | Dữ liệu cũ có thể bị hiểu sai |
| Đổi kiểu field | Phải kiểm tra quy tắc tương thích cụ thể; mặc định coi là rủi ro | Wire type, range, presence hoặc ý nghĩa dữ liệu có thể thay đổi |
| Đổi tên protobuf package/service/method | **Breaking đối với đường dẫn RPC cũ** | Tên method đầy đủ dùng để định tuyến |
| Đổi unary thành streaming hoặc ngược lại | **Breaking** | Chữ ký API và protocol tương tác thay đổi |
| Thêm một RPC mới | Thường không phá RPC cũ | Client cũ không bắt buộc gọi method mới |
| Bổ sung enum value | Thường tương thích ở wire format, phải xử lý unknown value | Client cũ có thể chưa biết giá trị mới |

Với enum proto3, giữ một giá trị **UNSPECIFIED = 0**. Consumer nên có nhánh xử lý giá trị không biết, thay vì giả định mọi server chỉ phát các enum value đang có trong bản client hiện tại.

### 7.3. Khi nào nên tạo v2?

Nếu cần thay đổi mang tính phá vỡ — chẳng hạn định nghĩa lại ý nghĩa **Order**, đổi kiểu RPC hoặc tổ chức lại toàn bộ service — có thể thiết kế **orders.v2.OrderService** và duy trì API v1 trong giai đoạn chuyển đổi.

~~~proto
syntax = "proto3";

package orders.v2;

service OrderService {
  rpc FetchOrder(FetchOrderRequest) returns (FetchOrderResponse);
}

message FetchOrderRequest {
  string id = 1;
}

message FetchOrderResponse {
  string id = 1;
  string display_name = 2;
}
~~~

Đây là ví dụ một **hợp đồng khác**, không phải cách đổi tên trực tiếp v1. Client dùng v1 sẽ vẫn gọi đường dẫn **/orders.v1.OrderService/GetOrder**; nếu còn hỗ trợ, server phải tiếp tục đăng ký service v1 hoặc triển khai adapter phù hợp. Đừng chỉ đổi package rồi kỳ vọng client cũ tự tìm thấy method mới.

## 8. Những gì service definition không tự giải quyết

File .proto là nguồn hợp đồng về API và dữ liệu. Nhưng để vận hành tin cậy, ứng dụng cần nhiều quyết định khác:

| Nhu cầu | Được khai báo trực tiếp trong service definition? | Giải pháp triển khai thường gặp |
| --- | --- | --- |
| **Metadata/correlation ID** | Không phải thành phần bắt buộc trong chữ ký rpc | Gửi metadata qua header, dùng client/server interceptor |
| **Authentication/authorization** | Không tự được thực thi bởi proto | TLS/mTLS, credentials, interceptor và policy ở server |
| **Deadline** | Không được cố định bởi chữ ký method | Client đặt deadline; server quan sát cancellation/deadline |
| **gRPC status** | Không phải response message khai báo riêng | Handler trả lỗi bằng **Status** và runtime gửi **grpc-status** |
| **Retry và idempotency** | Không được bảo đảm bởi hợp đồng syntax | Chính sách client và thiết kế operation/idempotency key |
| **Load balancing/discovery** | Không nằm trong file .proto | ManagedChannel, name resolver và load-balancer |
| **Flow control/backpressure** | Từ khóa stream chỉ định hướng dữ liệu | HTTP/2 transport cùng logic streaming kiểm soát tốc độ |
| **Giám sát/tracing** | Không được cấu hình trong message definition | Metrics, tracing và interceptor |
| **Đăng ký endpoint thực tế** | Không | gRPC server cần đăng ký BindableService/implementation |

Có thể thêm custom **protobuf options** để mô tả chính sách API, nhưng chỉ thêm annotation/option trong schema **không tự kích hoạt** authentication, routing hay retry. Phải có tooling và runtime hiểu, thực thi option đó.

### 8.1. Thiết kế lỗi và deadline theo ngữ nghĩa method

Ví dụ **GetOrder** có thể có các kết quả:

- Thành công: trả **GetOrderResponse** với **order**.
- Sai input: trả **INVALID_ARGUMENT**.
- Không tìm thấy đơn: trả **NOT_FOUND**.
- Client thiếu quyền: trả **PERMISSION_DENIED**.
- Backend tạm không khả dụng: trả **UNAVAILABLE**.
- Hết thời hạn: caller có thể nhận **DEADLINE_EXCEEDED**.

Status gRPC thường ở **trailers**, trong khi HTTP status có thể vẫn là **200**. Client phải xử lý **StatusRuntimeException** hoặc callback **onError**, không chỉ đọc payload protobuf.

Nếu RPC tạo hoặc cập nhật dữ liệu, việc retry sau **DEADLINE_EXCEEDED** có thể làm thực thi lặp vì server có thể đã xử lý thành công nhưng response chưa đến client. Khi thiết kế service, cần ghi rõ tính **idempotent** hoặc cung cấp request identifier/idempotency key nếu nghiệp vụ cần.

## 9. Quy trình làm việc và kiểm chứng hợp đồng

Một quy trình thực hành hợp lý:

1. **Thiết kế .proto.** Thống nhất package có version, method name, request/response message và hướng streaming. Xác định những trường cần presence/oneof.
2. **Review hợp đồng.** Kiểm tra field number, kiểu dữ liệu, meaning của field, tương thích ngược và những hành vi mà syntax chưa thể hiện.
3. **Chạy code generation.** Dùng **protoc** và plugin sinh mã gRPC Java trong build để tạo message class, descriptor và stub; giữ version công cụ tương thích.
4. **Triển khai server.** Override các method cần hỗ trợ, gắn logic nghiệp vụ và mã Status; đăng ký service với gRPC runtime.
5. **Triển khai client.** Tạo/reuse ManagedChannel, chọn stub phù hợp, cấu hình deadline/TLS và xử lý lỗi.
6. **Kiểm thử.** Kiểm tra serialization, request/response, trạng thái lỗi, các kiểu streaming và tương thích giữa bản client/server khác nhau.
7. **Quan sát khi chạy.** Theo dõi tên method, latency, status code, RPC đang chạy, deadline và tỉ lệ lỗi; truy vết xuyên client/server để nhận diện tầng phát sinh chậm.

### 9.1. Minh họa bước sinh mã Java

Giả sử đã cài **protoc**, Java plugin chuẩn và plugin **protoc-gen-grpc-java**, một cách gọi ở mức ý tưởng là:

~~~text
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  --grpc-java_out=build/generated/source/proto/main/grpc \
  src/main/proto/order_service.proto
~~~

Đường dẫn output phụ thuộc cấu hình build, và plugin **protoc-gen-grpc-java** cần nằm trong PATH hoặc được khai báo rõ. Trong dự án Java/Spring, thông thường cấu hình Maven/Gradle plugin để tự sinh mã khi build; **không sao chép thủ công code sinh** vào source do lập trình viên bảo trì.

Một hợp đồng chỉ thực sự được dùng sau khi cả client và server đều build với API sinh mã tương thích; việc có file .proto trên đĩa không tự khiến runtime nhận ra service.

### 9.2. Kiểm thử qua in-process transport

Có thể kiểm chứng registration và một unary RPC mà không mở cổng mạng, bằng **grpc-inprocess**. Đoạn mã minh họa JUnit 5 sử dụng **OrderGrpcEndpoint** ở mục 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.orders.grpc.v1.GetOrderRequest;
import com.example.orders.grpc.v1.GetOrderResponse;
import com.example.orders.grpc.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class OrderContractTest {

    @Test
    void generatedStubCallsRegisteredMethod() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderGrpcEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(channel);

            GetOrderResponse result = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-123")
                            .build());

            assertEquals("order-123", result.getOrder().getId());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Kiểm thử in-process cần **grpc-inprocess** và thư viện test tương thích với grpc-java đang dùng. Nó giúp xác minh API sinh mã, việc đăng ký method, serialization và status qua runtime gRPC. Nó **không** thay thế kiểm thử TLS, ALPN, HTTP/2 proxy, DNS hoặc cân bằng tải qua mạng thật. **directExecutor()** chỉ nên dùng cho test nhỏ, không mô phỏng đầy đủ hệ thống có callback chặn/tương tranh.

### 9.3. Kiểm tra service discovery với reflection

Khi server có bật **gRPC Server Reflection** và môi trường cho phép, có thể dùng công cụ như **grpcurl** để liệt kê service/method hoặc gọi thử mà không cần xây client Java đầy đủ:

~~~text
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe orders.v1.OrderService
grpcurl -plaintext -d '{"orderId":"order-123"}' \
  localhost:9090 orders.v1.OrderService/GetOrder
~~~

Các lệnh này **chỉ có tác dụng nếu reflection được đăng ký trên server**; ví dụ server đơn giản ở mục 5 chưa tự bật reflection. Các lệnh dùng **-plaintext** cho môi trường local, không phải mặc định cho production. JSON đưa vào grpcurl thường dùng tên field theo ProtoJSON (**orderId**) thay vì tên **order_id** trong source proto, dù parser có thể chấp nhận cả hai tùy công cụ.

Nếu không bật reflection, vẫn có thể kiểm thử bằng descriptor/proto file cục bộ hoặc client sinh mã, theo khả năng công cụ đang sử dụng.

## 10. Lỗi thường gặp khi viết service definition

| Dấu hiệu | Nguyên nhân dễ gặp | Cách xác minh/khắc phục |
| --- | --- | --- |
| Client báo **UNIMPLEMENTED** | Server chưa đăng ký service/method, implementation chưa override hoặc client/server khác hợp đồng | Kiểm tra method descriptor, package, service name, đăng ký handler và đường dẫn RPC |
| Import Java không tìm thấy lớp sinh mã | Code generation chưa chạy, output chưa được đưa vào source set, sai **java_package** | Kiểm tra cấu hình generator và package sinh ra |
| Client cũ không còn gọi được sau lần đổi tên | Đổi protobuf package/service/method làm đổi full RPC path | Duy trì API cũ hoặc phát hành phiên bản v2 có lộ trình migration |
| Dữ liệu đọc sai sau khi sửa schema | Đổi/tái sử dụng field number, thay đổi type thiếu đánh giá | Khôi phục số field ổn định, dùng reserved khi xóa |
| Không biết field scalar có được truyền không | Dựa vào giá trị mặc định của proto3 | Dùng **optional** hoặc kiểu message/oneof phù hợp |
| Streaming trả thiếu message | Handler gọi terminal callback sớm hoặc không quản lý backpressure | Xem logic onNext/onCompleted, cancellation, giới hạn và flow control |
| Client timeout dù method có trong proto | Deadline quá ngắn, backend chậm hoặc network lỗi | Theo dõi latency từng method, deadline, logs/traces và status |
| Nâng schema xong vẫn lỗi runtime | Chỉ generate một phía hoặc không kiểm tra tương thích bản triển khai | Build/test nhiều version client-server và triển khai theo lộ trình |
| Metadata xác thực không có trong request message | Metadata là khái niệm RPC headers, không phải field bắt buộc | Cấu hình credentials/interceptor và server authorization |

Một compiler protobuf chạy thành công chỉ xác nhận **cú pháp và một số ràng buộc schema**. Nó không chứng minh service có được đăng ký, caller được cấp quyền, hợp đồng tương thích ngược về ngữ nghĩa hay toàn bộ hệ thống hoạt động qua HTTP/2/TLS.

## 11. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành: mở rộng OrderService an toàn

Bắt đầu từ file **order_service.proto** trong mục 2 và thử các bước:

1. Thêm trường **optional string note = 5;** vào **Order**. Sinh lại Java và xác định phương thức kiểm tra presence tương ứng. Giải thích client cũ sẽ làm gì khi server mới trả field này.
2. Bổ sung một unary RPC **CancelOrder(CancelOrderRequest) returns (CancelOrderResponse)**. Thiết kế request có **order_id** và **expected_version**; nêu các status có thể trả khi không tìm thấy đơn hoặc đơn đã hoàn tất.
3. Thêm một method **WatchOrder** trả về **stream Order**. Phân biệt semantics của nó với **GetOrder**: nhiều message, điểm kết thúc, cancellation và các giới hạn kết nối.
4. Tạo implementation Spring cho một method mới, đăng ký lên gRPC server và kiểm thử bằng stub sinh mã. Nếu kiểm tra bằng grpcurl, bật reflection rõ ràng hoặc cung cấp schema cục bộ.
5. Giả lập client cũ và server mới. Đánh giá khả năng đọc message khi thêm field, sau đó thử thay đổi **package** protobuf trên một nhánh tách biệt để quan sát sự thay đổi đường dẫn RPC.

### Câu hỏi tự kiểm tra

**1. Tại sao service definition không cần ghi địa chỉ server hoặc cổng?**

Vì hợp đồng mô tả **API logic**, còn nơi kết nối và cách vận chuyển do **ManagedChannel/runtime/configuration** quyết định. Một hợp đồng có thể được triển khai trên nhiều địa chỉ và môi trường.

**2. Trong proto, từ khóa stream xuất hiện trước ResponseType có ý nghĩa gì?**

Server có thể gửi nhiều response message trong **một RPC**. Nó không có nghĩa tạo một HTTP/2 connection mới cho mỗi response.

**3. Package protobuf và java_package khác nhau thế nào?**

**package** góp phần định danh service/method trong gRPC wire protocol; **java_package** xác định package của mã Java được sinh. Thay đổi protobuf package có thể thay đổi đường dẫn RPC.

**4. Có được đổi số field 3 thành số 7 chỉ để sắp xếp lại schema không?**

Không nên. **Field number** là danh tính của trường trong protobuf wire format. Đổi số field là thay đổi có nguy cơ phá vỡ tương thích; khi cần xóa field cũ, nên dùng **reserved**.

**5. Vì sao server trả HTTP 200 nhưng client vẫn nhận StatusRuntimeException?**

gRPC truyền trạng thái RPC riêng, thường trong **grpc-status** ở trailers. HTTP 200 không đảm bảo nghiệp vụ RPC thành công.

**6. Khi file .proto đã khai báo GetOrder, tại sao client vẫn có thể nhận UNIMPLEMENTED?**

Vì runtime server có thể chưa đăng ký đúng service hoặc method chưa được implementation hỗ trợ. **Khai báo API** và **triển khai/đăng ký handler** là hai bước khác nhau.

## Tổng kết

**Service definition trong Protocol Buffers** là nguồn hợp đồng cho gRPC trong Spring: nó quy định **tên service, tên RPC, request/response message và hướng streaming**. Từ hợp đồng này, **protoc** và plugin gRPC Java sinh lớp dữ liệu, descriptor, stub và API cơ sở để server triển khai. Thiết kế tốt cần giữ ổn định field number và tên RPC đã phát hành, quản lý phiên bản rõ ràng, phân biệt schema với cấu hình runtime, đồng thời kiểm thử tương thích giữa client/server. Đây là nền tảng để phát triển các RPC unary và streaming có khả năng bảo trì, vận hành và mở rộng an toàn.

