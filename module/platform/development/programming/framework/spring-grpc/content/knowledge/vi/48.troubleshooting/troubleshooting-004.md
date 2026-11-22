# UNIMPLEMENTED do service chưa đăng ký

Trong **SPRING_GRPC**, client gọi một RPC bằng full method path gồm protobuf package, service name và method name. Nếu gRPC server không đăng ký service tương ứng, endpoint có thể trả `UNIMPLEMENTED`. Status này cũng xuất hiện khi service đã đăng ký nhưng method chưa được triển khai, client dùng contract cũ/sai hoặc một lớp trung gian trả status đó.

Cần xác định server thực sự nhận request nào và service definition nào đã được bind. `UNIMPLEMENTED` khác `UNAVAILABLE`: trường hợp đầu thường có một gRPC endpoint trả lời rằng method không được hỗ trợ; trường hợp sau thường cho biết client không kết nối được hoặc dependency tạm thời không sẵn sàng. Bài này hướng dẫn truy vết từ RPC path, generated code, Spring bean registration đến kiểm thử service registration.

## 1. Hiểu full method path mà client gọi

gRPC định danh một method bằng đường dẫn dạng:

```text
/package.Service/Method
```

Ví dụ contract:

```proto
syntax = "proto3";

package inventory.v1;

option java_package = "com.acme.inventory.grpc.v1";
option java_multiple_files = true;

service InventoryService {
  rpc GetStock(GetStockRequest) returns (GetStockReply);
}

message GetStockRequest {
  string sku = 1;
}

message GetStockReply {
  string sku = 1;
  int32 available = 2;
}
```

Full method path là:

```text
/inventory.v1.InventoryService/GetStock
```

Phân biệt hai loại package:

- `package inventory.v1` thuộc protobuf và tham gia tạo full method path trên wire.
- `option java_package = "com.acme.inventory.grpc.v1"` quyết định package Java của generated class; nó không đổi RPC path.

Vì vậy, đổi `java_package` không làm client gọi một service path mới. Đổi protobuf `package`, service name hoặc method name có thể làm thay đổi path và khiến client/server không còn khớp.

## 2. `UNIMPLEMENTED` có thể đến từ đâu?

Có một số trường hợp cần phân biệt:

| Tình huống | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| Service chưa đăng ký | Server không có service descriptor tương ứng | Spring bean discovery, `@GrpcService`, server registration |
| Service có đăng ký nhưng method chưa được override/triển khai | Service tồn tại nhưng một method trả `UNIMPLEMENTED` | Generated `ImplBase`, method override và implementation |
| Client gọi sai package/service/method | Full method path không trùng contract server | Proto source và generated stub ở hai phía |
| Client dùng contract/version cũ | Method path hoặc message contract khác bản server | Dependency artifact và bước generate code |
| Server chủ động trả `UNIMPLEMENTED` | Application code hoặc interceptor trả status này | Tìm `Status.UNIMPLEMENTED` trong code |
| Proxy/gateway trả status | Request không đến đúng backend service | Route, upstream cluster và proxy log |

Không kết luận service chưa đăng ký chỉ từ status code. Hãy đối chiếu full method path, log server và registry/service definition của đúng process đang nhận traffic.

## 3. Kiểm tra generated service implementation

Spring gRPC adapter thường kế thừa generated `ImplBase`:

```java
@GrpcService
public class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    private final GetStockUseCase getStock;
    private final InventoryProtoMapper mapper;

    public InventoryGrpcService(
            GetStockUseCase getStock,
            InventoryProtoMapper mapper) {
        this.getStock = getStock;
        this.mapper = mapper;
    }

    @Override
    public void getStock(
            GetStockRequest request,
            StreamObserver<GetStockReply> observer) {
        try {
            StockView result = getStock.execute(
                    new GetStockQuery(request.getSku()));

            observer.onNext(mapper.toProto(result));
            observer.onCompleted();
        } catch (RuntimeException error) {
            observer.onError(Status.INTERNAL
                    .withDescription("Internal server error")
                    .asRuntimeException());
        }
    }
}
```

Kiểm tra các điểm sau:

- Class kế thừa đúng generated base class của contract server dự định cung cấp.
- Method cần gọi có `@Override` và đúng signature được generate.
- Class được Spring quản lý và có annotation đăng ký service phù hợp với phiên bản Spring gRPC đang dùng.
- Không có điều kiện profile/configuration khiến bean bị loại khỏi application context.
- Implementation không chủ động trả `Status.UNIMPLEMENTED` cho method đó.

Generated base class thường cung cấp default implementation cho RPC chưa override; default này kết thúc call bằng `UNIMPLEMENTED`. Do đó service có thể đã được đăng ký, nhưng một method cụ thể vẫn chưa được triển khai.

## 4. Xác minh Spring bean được tạo

Với Spring gRPC, service implementation thường được đăng ký qua bean có annotation `@GrpcService`. Nếu class không được component scan hoặc configuration loại bean, server sẽ không có service đó.

Ví dụ cấu trúc package:

```text
com.acme.inventory
├── InventoryApplication.java
└── adapter
    └── grpc
        └── InventoryGrpcService.java
```

Application class nên scan được package chứa adapter. Nếu application class nằm ở package không phải parent của adapter, cấu hình component scan/import tương ứng.

Các nguyên nhân phổ biến:

- Adapter nằm ngoài package scan.
- Class thiếu annotation đăng ký gRPC service.
- Bean bị loại bởi `@Profile`, `@ConditionalOnProperty` hoặc condition khác.
- Constructor dependency lỗi khiến bean không khởi tạo được.
- Adapter nằm trong module chưa được đưa vào runtime classpath.
- Có nhiều server/port và service được đăng ký vào server khác với endpoint client đang gọi.

Đừng chỉ kiểm tra class có annotation hay không. Xem startup log để biết bean có được tạo, server có khởi động và service có được bind hay không. Nếu application startup đã thất bại vì bean dependency hoặc duplicate registration, đó là lỗi cấu hình khởi động cần xử lý trước.

## 5. Kiểm tra cách đăng ký service

Có hai kiểu wiring thường gặp:

**Spring-managed registration**

```java
@GrpcService
public class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {
    // RPC implementations
}
```

Spring gRPC phát hiện bean service và đăng ký nó với server theo cơ chế của phiên bản thư viện.

**Manual server registration**

```java
Server server = ServerBuilder
        .forPort(port)
        .addService(inventoryGrpcService)
        .build()
        .start();
```

Trong kiểu manual, việc tạo object Spring bean chưa đồng nghĩa service đã được add vào server. Phải xác nhận đúng instance được truyền vào `addService`.

Tránh đăng ký cùng một full service name đồng thời qua nhiều đường wiring. Duplicate registration thường gây lỗi lúc khởi tạo server thay vì âm thầm sửa lỗi `UNIMPLEMENTED`; tuy vậy cấu hình nhiều server có thể khiến service được bind ở endpoint khác với endpoint client đang dùng.

## 6. Đối chiếu client stub và server contract

Generated client stub mang full method path được tạo từ contract tại thời điểm generate. Nếu client dùng artifact cũ, nó có thể gọi package/service/method không còn được server cung cấp.

Kiểm tra:

1. Tìm `.proto` mà client thực sự compile.
2. Xác nhận protobuf `package`, `service` và `rpc` name.
3. Xác nhận server compile contract tương thích.
4. Kiểm tra dependency version hoặc generated source đang được đóng gói.
5. Regenerate code sau khi thay đổi `.proto`.
6. Kiểm tra endpoint mà channel target đang trỏ tới.

Có thể in full method name từ generated method descriptor:

```java
String methodName =
        InventoryServiceGrpc.getGetStockMethod()
                .getFullMethodName();

log.info("Calling gRPC method {}", methodName);
```

Giá trị mong đợi:

```text
inventory.v1.InventoryService/GetStock
```

Nếu client và server log ra tên khác nhau, tìm nguyên nhân trong proto source, version artifact hoặc build pipeline. Đừng sửa bằng cách đổi Java package nếu phần protobuf package/service/method mới là thành phần không khớp.

## 7. Xác minh đúng endpoint và đúng process

Trong môi trường có nhiều instance, local profile, container hoặc nhiều gRPC port, client có thể kết nối thành công tới một server khác chưa triển khai service.

Kiểm tra:

- `forTarget(...)`, DNS name và port của channel.
- Service discovery/load balancer trả về backend nào.
- Port publish/container mapping và ingress route.
- Profile/configuration của instance đang chạy.
- Image/tag hoặc deployment revision thực tế.
- Log có instance ID, RPC method và thời điểm request.

`UNIMPLEMENTED` cho biết một endpoint trả status, nhưng endpoint đó có thể là proxy, sidecar hoặc server cũ. So sánh request với log của từng backend để xác định request dừng ở lớp nào.

Nếu client không kết nối được, thường sẽ thấy `UNAVAILABLE`, connection refused, DNS failure hoặc timeout. Đừng xử lý `UNIMPLEMENTED` bằng retry liên tục như lỗi kết nối tạm thời; trước tiên phải sửa service/method registration hoặc contract mismatch.

## 8. Dùng reflection và grpcurl để kiểm tra service

Nếu server bật gRPC Server Reflection, có thể dùng `grpcurl` để liệt kê service:

```bash
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe inventory.v1.InventoryService
```

Kết quả `list` nên có `inventory.v1.InventoryService`; `describe` hiển thị các RPC của service. Với TLS, dùng cấu hình CA/client certificate tương ứng thay cho `-plaintext`.

Reflection là công cụ chẩn đoán, không phải điều kiện để service hoạt động. Nếu reflection bị tắt, `grpcurl list` không thể khám phá service dù service vẫn được đăng ký. Khi đó, gọi method đã biết bằng proto descriptor/file hoặc kiểm tra server logs và registration trong ứng dụng.

Không bật reflection công khai trong production chỉ để tiện debug nếu policy bảo mật không cho phép. Có thể bật trong môi trường nội bộ hoặc test, có kiểm soát network access.

## 9. Kiểm tra service registry khi khởi động

Đảm bảo đúng server instance đã nhận service definition. Với Spring-managed registration, kiểm tra log startup của Spring gRPC và bean condition report khi cần. Với manual registration, kiểm tra danh sách `ServerServiceDefinition` được add vào server builder trước khi start.

Có thể ghi log một allowlist service name khi khởi động:

```java
server.getServices().forEach(definition ->
        log.info(
                "Registered gRPC service: {}",
                definition.getServiceDescriptor().getName()));
```

Đoạn code này chỉ áp dụng nếu API server/runtime đang dùng cung cấp danh sách service definitions ở thời điểm kiểm tra. Nếu không, ghi nhận service name tại nơi application gọi `addService` hoặc dùng startup diagnostics của framework; không thêm reflection hoặc API nội bộ chỉ để lấy registry.

Tên service cần khớp protobuf package cộng service name, ví dụ `inventory.v1.InventoryService`. Một Java class có tên `InventoryGrpcService` không chứng minh wire service đã được đăng ký đúng.

## 10. Kiểm thử service registration bằng in-process gRPC

In-process test xác minh một service implementation được add vào server và generated client gọi được RPC. Test không cần TCP port:

```java
String serverName = InProcessServerBuilder.generateName();

InventoryGrpcService service =
        new InventoryGrpcService(getStockUseCase, mapper);

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(service)
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    InventoryServiceGrpc.InventoryServiceBlockingStub client =
            InventoryServiceGrpc.newBlockingStub(channel);

    GetStockReply reply = client.getStock(
            GetStockRequest.newBuilder()
                    .setSku("SKU-42")
                    .build());

    assertEquals("SKU-42", reply.getSku());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(2, TimeUnit.SECONDS);
    server.awaitTermination(2, TimeUnit.SECONDS);
}
```

Test này chứng minh service definition và method implementation hoạt động qua gRPC runtime. Nó chưa xác minh Spring component scanning hoặc annotation-based registration, vì test đã add service trực tiếp.

Để kiểm tra Spring registration, thêm integration test khởi động Spring application context với gRPC server auto-configuration đang dùng, rồi gọi generated stub tới server test. Không tự add service trong test đó; mục tiêu là chứng minh framework phát hiện bean và đăng ký đúng service.

## 11. Kiểm thử trường hợp service chưa đăng ký

Một negative test có thể khởi động in-process server mà không add service, sau đó gọi stub:

```java
@Test
void unknownServiceReturnsUnimplemented() throws Exception {
    String serverName = InProcessServerBuilder.generateName();

    Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .build()
            .start();

    ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

    try {
        InventoryServiceGrpc.InventoryServiceBlockingStub client =
                InventoryServiceGrpc.newBlockingStub(channel);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> client.getStock(
                        GetStockRequest.newBuilder()
                                .setSku("SKU-42")
                                .build()));

        assertEquals(
                Status.Code.UNIMPLEMENTED,
                Status.fromThrowable(error).getCode());
    } finally {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(2, TimeUnit.SECONDS);
        server.awaitTermination(2, TimeUnit.SECONDS);
    }
}
```

Negative test xác nhận behavior của gRPC runtime khi service không được bind. Trong test thực tế, nên có positive test song song để chứng minh service đúng được đăng ký và method hoạt động.

## 12. Trình tự troubleshooting có hệ thống

Khi nhận `UNIMPLEMENTED`, đi theo thứ tự:

1. Ghi nhận full method path từ generated descriptor hoặc server log.
2. Xác nhận host/port/backend mà client thực sự gọi.
3. Kiểm tra protobuf package, service name và method name giữa hai phía.
4. Xác nhận server generated base class đúng contract và method đã override.
5. Xác nhận Spring bean được tạo, không bị profile/condition loại bỏ.
6. Xác nhận service được bind vào đúng gRPC server.
7. Dùng reflection/grpcurl nếu môi trường cho phép.
8. Viết hoặc chạy in-process registration test.
9. Kiểm tra proxy/gateway nếu request không tới process mong đợi.
10. Sau khi sửa, restart/deploy đúng artifact và xác nhận call thành công.

Không bắt đầu bằng cách retry RPC hoặc đổi status ở client. `UNIMPLEMENTED` thường cần sửa server registration, method implementation hoặc contract path.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao gây `UNIMPLEMENTED` | Cách xử lý |
| --- | --- | --- |
| Quên `@GrpcService` hoặc registration | Service bean không được bind | Đăng ký service bằng cơ chế Spring gRPC đang dùng |
| Adapter ngoài component scan | Spring không tạo bean | Sửa package scan/import |
| Profile loại adapter | Service không tồn tại ở runtime đó | Kiểm tra active profile/conditions |
| Kế thừa generated `ImplBase` nhưng không override RPC | Default method trả `UNIMPLEMENTED` | Implement method hoặc bỏ method khỏi contract nếu không hỗ trợ |
| Client dùng proto cũ | Full method path không khớp | Cập nhật contract artifact và regenerate |
| Nhầm protobuf package với `java_package` | Kiểm tra sai wire path | Dùng protobuf package/service/method |
| Gọi nhầm port/backend | Request tới server không có service | Kiểm tra target, discovery và deployment |
| Reflection tắt | Không list được service bằng grpcurl | Dùng known proto hoặc startup diagnostics |
| Server trả `UNIMPLEMENTED` có chủ đích | Status không liên quan registration | Tìm nơi tạo status trong code/interceptor |

## 14. Bài tập thực hành

1. Tạo `inventory.v1.InventoryService` với RPC `GetStock`.
2. Sinh generated Java code và in full method name từ generated descriptor.
3. Viết `InventoryGrpcService` kế thừa generated `ImplBase` và override `getStock`.
4. Đăng ký adapter qua Spring gRPC bean mechanism; xác nhận bean được tạo khi application start.
5. Tạm bỏ annotation/registration và quan sát lỗi từ generated client.
6. Khôi phục registration, gọi lại RPC và xác nhận response thành công.
7. Tạo in-process positive test cho service đã đăng ký.
8. Tạo negative test cho unknown service và assert `Status.Code.UNIMPLEMENTED`.
9. Dùng grpcurl/reflection nếu được bật để kiểm tra service name và method list.
10. Thay protobuf package hoặc dùng client artifact cũ trong môi trường test; xác nhận full method path thay đổi và ghi lại cách khắc phục.

### Ghi nhớ

**`UNIMPLEMENTED` thường có nghĩa endpoint gRPC đã trả lời rằng service hoặc method path được gọi không được hỗ trợ.** Hãy xác minh full method path, generated contract, method override, Spring bean discovery và service registration trên đúng server instance. Phân biệt service chưa đăng ký với method chưa triển khai hoặc client dùng contract cũ; kiểm chứng bằng in-process test và startup diagnostics trước khi thay đổi client hoặc thêm retry.

## Tài liệu tham khảo

- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC — Reflection](https://grpc.io/docs/guides/reflection/)
- [gRPC Java — ServerServiceDefinition](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerServiceDefinition.html)
- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html)
- [Spring gRPC — Server Services](https://docs.spring.io/spring-grpc/reference/server.html)
- [grpcurl](https://github.com/fullstorydev/grpcurl)
