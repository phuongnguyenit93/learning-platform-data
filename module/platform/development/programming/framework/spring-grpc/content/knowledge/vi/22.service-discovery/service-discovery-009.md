# Tên service khác với package proto

Trong gRPC, tên service trên wire được hình thành từ `package` trong file `.proto` và tên khai báo sau từ khóa `service`. Tên đó quyết định RPC path mà client gọi tới. Nó **khác** với Java package dùng để sinh mã, và cũng khác với tên logic mà service discovery dùng để tìm địa chỉ server.

Phân biệt ba khái niệm này rất quan trọng trong Spring gRPC. Một client có thể phân giải đúng DNS và kết nối được tới server nhưng vẫn nhận `UNIMPLEMENTED` nếu service path không khớp. Ngược lại, đổi Java package có thể làm mã nguồn phải sửa import nhưng không nhất thiết thay đổi RPC path.

## 1. Ba loại tên có mục đích khác nhau

Xét ví dụ:

```proto
syntax = "proto3";

package acme.orders.v1;

option java_package = "com.acme.platform.orders.grpc";
option java_multiple_files = true;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string status = 2;
}
```

Từ định nghĩa này có ba tên cần tách biệt:

| Khái niệm | Giá trị ví dụ | Dùng ở đâu |
| --- | --- | --- |
| Proto package | `acme.orders.v1` | Namespace của service và message trong Protobuf descriptor |
| Fully qualified gRPC service name | `acme.orders.v1.OrderService` | Nhận diện service trên gRPC protocol, health checking, reflection và RPC routing |
| Java package | `com.acme.platform.orders.grpc` | Package của các lớp Java được protoc sinh ra |

Tên RPC đầy đủ là `acme.orders.v1.OrderService/GetOrder`. HTTP/2 `:path` của call có dạng:

```text
/acme.orders.v1.OrderService/GetOrder
```

`java_package` chỉ điều khiển package Java được sinh. Nó không thay `package acme.orders.v1` trong descriptor và không đổi tên service trên wire.

## 2. Proto package tạo ra tên service đầy đủ như thế nào?

Quy tắc tổng quát:

```text
fully-qualified-service-name = proto-package + "." + service-name
rpc-method-name              = fully-qualified-service-name + "/" + method-name
HTTP/2 :path                 = "/" + rpc-method-name
```

Với ví dụ trên:

- Proto package: `acme.orders.v1`
- Service declaration: `OrderService`
- Fully qualified service name: `acme.orders.v1.OrderService`
- Method declaration: `GetOrder`
- RPC path: `/acme.orders.v1.OrderService/GetOrder`

Nếu file `.proto` không khai báo `package`, tên service không có prefix package. Ví dụ service `OrderService` với method `GetOrder` sẽ có path `/OrderService/GetOrder`. Vì vậy nên khai báo package rõ ràng để tránh tên service chung chung và giảm nguy cơ trùng tên giữa các API.

Tên package và identifier phân biệt chữ hoa/chữ thường. `acme.orders.v1.OrderService` khác `acme.orders.v1.orderservice`; client và server phải dùng cùng tên đầy đủ.

## 3. Java package không quyết định RPC path

Protoc sinh lớp Java dựa trên các option Java:

- `java_package`: package Java của mã sinh.
- `java_multiple_files`: quyết định các message/enum có được sinh thành các lớp riêng hay lồng trong outer class.
- `java_outer_classname`: tên outer class chứa descriptor hoặc các kiểu lồng trong chế độ tương ứng.

Các option này ảnh hưởng cấu trúc mã nguồn, import và tên lớp Java. Chúng không thay `package` Protobuf và không đổi fully qualified gRPC service name.

Với ví dụ, lớp generated service thường có tên `OrderServiceGrpc` trong package Java `com.acme.platform.orders.grpc`. Có thể kiểm tra service name do mã sinh cung cấp:

```java
import com.acme.platform.orders.grpc.OrderServiceGrpc;

class GeneratedNameCheck {
    void inspect() {
        String serviceName = OrderServiceGrpc.SERVICE_NAME;
        // acme.orders.v1.OrderService
        System.out.println(serviceName);
    }
}
```

Tên lớp generated là chi tiết của Java code generation; `OrderServiceGrpc.SERVICE_NAME` mới là giá trị cần đối chiếu với service name trong descriptor và các cấu hình gRPC liên quan.

Do đó:

- Đổi `java_package` từ `com.acme.platform.orders.grpc` sang `com.acme.orders.api` thường yêu cầu cập nhật import và build artifact.
- Nếu vẫn giữ `package acme.orders.v1` và `service OrderService`, RPC path vẫn là `/acme.orders.v1.OrderService/GetOrder`.
- Đổi `package` trong `.proto` thành `acme.sales.v1` sẽ đổi RPC path, dù `java_package` không đổi.

## 4. Service name khác target dùng cho service discovery

Đây là một nhầm lẫn phổ biến khác. Target của channel cho biết **kết nối tới dịch vụ ở đâu**; fully qualified service name cho biết **RPC nào được gọi trên kết nối đó**.

Ví dụ:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .useTransportSecurity()
    .build();

OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub.getOrder(
    GetOrderRequest.newBuilder()
        .setOrderId("ORD-1042")
        .build());
```

Trong ví dụ:

- `dns:///orders.default.svc.cluster.local:8443` là target URI cho resolver tìm endpoint.
- `acme.orders.v1.OrderService` là service name trong gRPC descriptor.
- `GetOrder` là method trong service.
- `OrderServiceGrpc` là lớp Java generated dùng để tạo stub.

Resolver có thể tìm một Pod, một ClusterIP hoặc một nhóm endpoint từ registry. Nó không đổi tên service hoặc method trong RPC path. Vì vậy kết nối TCP/TLS thành công chưa chứng minh server có triển khai đúng service path.

Tên registry như `orders`, DNS name `orders.default.svc.cluster.local` và proto service name `acme.orders.v1.OrderService` có thể khác nhau. Hãy đặt quy ước rõ ràng và không dùng một chuỗi thay thế cho cả ba chỉ vì chúng cùng chứa từ `orders`.

## 5. Server đăng ký service bằng descriptor nào?

Server cần đăng ký implementation được sinh từ đúng định nghĩa `.proto`. grpc-java dùng service descriptor của implementation để nhận diện service:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;

final class OrderServiceImpl
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {
        GetOrderResponse response = GetOrderResponse.newBuilder()
            .setOrderId(request.getOrderId())
            .setStatus("CONFIRMED")
            .build();
        observer.onNext(response);
        observer.onCompleted();
    }
}

Server server = ServerBuilder.forPort(8443)
    .addService(new OrderServiceImpl())
    .build()
    .start();
```

Implementation trên được đăng ký với tên service từ descriptor Protobuf, không phải tên class Java hay tên Spring bean. Đặt bean là `ordersGrpcService` không làm service name trên wire đổi thành `ordersGrpcService`.

Trong Spring gRPC, có thể dùng cơ chế đăng ký service của starter đang cài đặt, chẳng hạn bean/annotation được starter hỗ trợ. Dù dùng cơ chế nào, implementation vẫn phải dựa trên generated service tương ứng và descriptor phải khớp với client.

Nếu client gọi `/acme.orders.v1.OrderService/GetOrder` nhưng server chỉ đăng ký `acme.orders.v2.OrderService`, kết nối vẫn có thể thành công nhưng server không tìm thấy method path được yêu cầu và thường trả `UNIMPLEMENTED`.

## 6. Tên service trong health checking, reflection và interceptor

Fully qualified service name còn xuất hiện ở những cơ chế gRPC khác:

**Health checking.** Khi đặt trạng thái cho một service trong `HealthStatusManager`, dùng service name đầy đủ từ proto package và service declaration:

```java
healthStatusManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.SERVING);
```

Nếu client-side health checking cấu hình `serviceName`, giá trị đó cũng phải khớp tên service mà health server công bố. Dùng `orders.default.svc.cluster.local` ở đây là sai mục đích vì đó là DNS target, không phải gRPC service name.

**Server reflection.** Reflection công bố descriptor và service để công cụ như grpcurl khám phá API. Tên hiển thị là tên service Protobuf đầy đủ, không phải Java package hoặc tên registry.

**Interceptor và authorization.** Method descriptor cung cấp full method name để áp dụng policy theo service/method:

```java
String fullMethod =
    call.getMethodDescriptor().getFullMethodName();

// Ví dụ: acme.orders.v1.OrderService/GetOrder
if (fullMethod.equals(
        "acme.orders.v1.OrderService/GetOrder")) {
    // Áp dụng policy cho RPC cụ thể.
}
```

Trong grpc-java, `getFullMethodName()` thường trả chuỗi `service/method` không có dấu `/` đầu tiên; HTTP/2 path có thêm dấu `/` ở đầu. Khi viết test hoặc so khớp interceptor, dùng đúng định dạng API trả về.

## 7. Đổi proto package là thay đổi contract

Đổi Java package và đổi Protobuf package có mức ảnh hưởng khác nhau:

| Thay đổi | Ảnh hưởng mã Java | Ảnh hưởng gRPC wire/service identity |
| --- | --- | --- |
| Đổi `java_package` | Import, package và build output thay đổi | Không đổi RPC path nếu proto package/service giữ nguyên |
| Đổi `java_outer_classname` | Tên outer class/descriptor holder thay đổi | Không đổi RPC path |
| Đổi `java_multiple_files` | Cấu trúc lớp generated thay đổi | Không đổi RPC path |
| Đổi proto `package` | Descriptor và tên đầy đủ của kiểu/service thay đổi; có thể phải cập nhật mã tham chiếu | Đổi service/method path; client cũ không còn gọi đúng service path |
| Đổi tên `service` | Generated service class và API server/client thay đổi | Đổi service identity và RPC path |
| Đổi tên `rpc` method | Stub method thay đổi | Đổi method path |

Đổi proto package không tương đương refactor Java package. Nó là thay đổi contract ở cấp Protobuf/gRPC và có thể ảnh hưởng:

- Client generated từ `.proto` cũ.
- Server đang đăng ký descriptor cũ.
- Health checking service name.
- Reflection và công cụ vận hành.
- Authorization/interceptor rule dựa trên full method name.
- Metrics, tracing và dashboard nhóm theo service/method.
- `Any` type URL hoặc dữ liệu descriptor được lưu/phát ra ngoài nếu các message liên quan được đóng gói theo tên đầy đủ.

Nếu cần chuyển từ `acme.orders.v1` sang `acme.fulfillment.v1`, cân nhắc tạo service/version mới hoặc duy trì song song service cũ trong giai đoạn chuyển đổi. Rollout cần bảo đảm server có thể phục vụ cả path cũ và mới trong thời gian client được nâng cấp. Chỉ xóa service cũ khi đã xác nhận không còn client gọi path đó.

## 8. Kiểm tra và chẩn đoán tên service

Khi gặp `UNIMPLEMENTED`, đừng vội thay DNS target. Kiểm tra lần lượt:

1. Đọc `package` và `service` trong `.proto` mà client đã dùng để sinh stub.
2. Xác định `OrderServiceGrpc.SERVICE_NAME` hoặc full method name do generated code cung cấp.
3. Xác nhận server đăng ký implementation được sinh từ đúng proto contract.
4. Kiểm tra HTTP/2 path có dạng `/<proto-package>.<Service>/<Method>`.
5. Kiểm tra health config, reflection và interceptor có dùng cùng service name không.
6. Sau cùng mới kiểm tra resolver target, DNS, port, TLS và network path nếu kết nối chưa tới server.

Ví dụ với grpcurl, service reflection có thể liệt kê `acme.orders.v1.OrderService`; gọi method bằng tên đầy đủ:

```bash
grpcurl -plaintext localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Lệnh chỉ phù hợp với server local plaintext và đã bật reflection. Trong production, dùng TLS flags/trust material phù hợp và không bật plaintext để né lỗi chứng thư.

## 9. Kiểm thử contract name

Nên có kiểm thử tự động để tránh thay đổi tên ngoài ý muốn:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Proto descriptor full service name | `acme.orders.v1.OrderService` |
| Generated `SERVICE_NAME` | Trùng với fully qualified service name |
| Generated full method name | `acme.orders.v1.OrderService/GetOrder` |
| HTTP/2 path | `/acme.orders.v1.OrderService/GetOrder` |
| Java package | `com.acme.platform.orders.grpc` |
| Server registration | Có service descriptor đúng tên |
| Health status key | Dùng `acme.orders.v1.OrderService` |
| Health client config | Dùng cùng service name |
| Resolver target | Dùng DNS/registry target độc lập với proto service name |
| Interceptor rule | So khớp đúng định dạng `getFullMethodName()` |

Một test nhỏ có thể khóa service name:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class OrderServiceDescriptorTest {
    @Test
    void serviceIdentityMatchesProtoContract() {
        assertEquals(
            "acme.orders.v1.OrderService",
            OrderServiceGrpc.SERVICE_NAME);
    }
}
```

Thêm integration test gọi method qua channel tới server thật để xác minh cả routing path lẫn registration. Unit test constant không chứng minh server đã đăng ký implementation hoặc resolver đang trỏ đúng endpoint.

## 10. Bài tập vận dụng

Client hiện dùng generated stub từ proto có `package acme.orders.v1`, `java_package = "com.acme.legacy.orders"` và `service OrderService`. Nhóm muốn chuyển mã Java sang `com.acme.platform.orders.grpc` và đổi DNS target sang `orders.prod.svc.cluster.local`.

**Yêu cầu:**

1. Xác định fully qualified service name và RPC path hiện tại.
2. Giải thích việc đổi `java_package` ảnh hưởng điều gì và điều gì không đổi.
3. Giải thích việc đổi DNS target ảnh hưởng resolver/endpoint ra sao và vì sao không đổi RPC path.
4. Xác định những cấu hình cần kiểm tra: health service name, health check config, reflection và interceptor.
5. Đề xuất quy trình nếu sau này cần đổi proto package sang `acme.orders.v2`.
6. Viết test khóa `SERVICE_NAME`, full method name và server registration để phát hiện contract drift.

**Câu hỏi tự kiểm tra:**

- Thành phần nào tạo fully qualified gRPC service name?
- `java_package` có thay đổi HTTP/2 `:path` không?
- Vì sao server bean name không quyết định RPC service name?
- DNS target và proto service name trả lời hai câu hỏi nào?
- `UNIMPLEMENTED` có thể xảy ra thế nào khi client và server dùng proto package khác nhau?
- Health checking phải dùng tên service nào?
- Đổi proto package có thể ảnh hưởng những thành phần vận hành nào ngoài stub?

**Ghi nhớ:** Proto `package` kết hợp với tên `service` tạo fully qualified gRPC service name; tên đó xuất hiện trong RPC path. `java_package` chỉ tổ chức mã Java được sinh, còn DNS/registry target chỉ giúp tìm endpoint. Trong Spring gRPC, giữ ba loại tên tách biệt, kiểm tra health/reflection/interceptor theo service name đầy đủ và xem việc đổi proto package là thay đổi contract cần rollout có tương thích.
