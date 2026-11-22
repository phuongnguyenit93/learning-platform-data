# Thay đổi package hoặc service name

## 1. Vì sao đổi package hoặc service name có thể phá tương thích?

Trong **SPRING_GRPC**, Protobuf schema định nghĩa message và service mà client/server dùng để giao tiếp. Đổi protobuf package hoặc tên service không đơn thuần là đổi namespace source: chúng tham gia tạo **full gRPC method name**. Client gọi RPC bằng tên đầy đủ này trong HTTP/2 path; server đăng ký handler theo cùng định danh.

Vì vậy, server mới có thể vẫn chạy và parse được message bytes, nhưng client cũ gọi một RPC path mà server không còn đăng ký. Package Protobuf còn tạo fully-qualified message names, ảnh hưởng descriptor, reflection và google.protobuf.Any.

Cần phân biệt:

- package trong tệp proto: namespace của message, enum và service; tham gia full gRPC service/method name.
- Tên service và rpc: tham gia RPC path.
- option java_package: namespace của Java generated classes; ảnh hưởng compile-time API nhưng không quyết định RPC path.

Bài tập trung vào tác động của từng loại tên, cách giữ service cũ trong giai đoạn chuyển tiếp, dual registration, cập nhật tích hợp phụ thuộc tên và kiểm thử mixed-version rollout.

## 2. Full gRPC method name

Ví dụ:

```proto
syntax = "proto3";

package catalog.v1;

service ProductService {
  rpc GetProduct(GetProductRequest) returns (ProductReply);
}
```

Tên đầy đủ của service là catalog.v1.ProductService; full method name là:

```text
/catalog.v1.ProductService/GetProduct
```

Đây là tên được dùng làm HTTP/2 :path khi client gọi RPC. Generated Java stub lưu method descriptor tương ứng; client không chỉ gửi một tên class Java tới server.

| Thành phần | Ví dụ cũ | Nếu đổi | Tác động |
| --- | --- | --- | --- |
| Protobuf package | catalog.v1 | catalog.v2 | Đổi service full name và RPC path |
| Service name | ProductService | CatalogProductService | Đổi RPC path |
| RPC method name | GetProduct | FetchProduct | Đổi RPC path |

Nếu server mới chỉ đăng ký /catalog.v2.ProductService/GetProduct, client cũ gọi /catalog.v1.ProductService/GetProduct sẽ không khớp handler. Khi server reachable nhưng không có method path tương ứng, client thường nhận UNIMPLEMENTED. Đây là lỗi định tuyến contract, khác với lỗi kết nối như UNAVAILABLE.

## 3. Phân biệt protobuf package với java_package

Ví dụ:

```proto
syntax = "proto3";

package catalog.v1;

option java_package = "com.example.generated.catalog";
option java_multiple_files = true;

message ProductReply {
  string sku = 1;
}
```

Hai namespace có mục đích khác nhau:

| Khai báo | Tác động |
| --- | --- |
| package catalog.v1 | Protobuf fully-qualified names; service full name; descriptor; type URL của Any |
| option java_package | Package Java của generated classes |
| option java_multiple_files | Cách chia message/enum thành Java files |
| option java_outer_classname | Tên outer wrapper class khi dùng kiểu sinh code tương ứng |

Nếu chỉ đổi java_package, binary message field tags và gRPC method path vẫn giữ nguyên, miễn là protobuf package, service và RPC names không đổi. Tuy nhiên, Java consumers có thể không compile vì generated class chuyển package.

Ngược lại, đổi package catalog.v1 thành package catalog.v2 có thể giữ nguyên java_package nhưng vẫn đổi gRPC method path và Protobuf type names. Giữ Java package không khôi phục wire service identity.

Đường dẫn file proto trong import cũng khác protobuf package. Import dùng đường dẫn file trong proto source tree; package là namespace khai báo bên trong file. Đổi một bên không tự động đổi bên kia.

## 4. Đổi protobuf package ảnh hưởng message type identity

Field number và wire type quyết định cách parse binary message. Tên fully-qualified message không được thêm vào mọi payload message thông thường. Vì vậy, đổi protobuf package mà giữ nguyên cấu trúc message có thể không làm thay đổi bytes của message đơn lẻ.

Nhưng type identity vẫn được dùng ở các cơ chế khác:

- Descriptor và reflection tra cứu message bằng fully-qualified name.
- google.protobuf.Any đóng gói type URL chứa tên type, thường có dạng type.googleapis.com/catalog.v1.ProductReply.
- Protobuf JSON cho Any cần type registry để resolve đúng message type.
- Schema registry, gateway, validation và tooling có thể tham chiếu fully-qualified name.
- Service method descriptor dùng package/service/method name để định danh RPC.

Một Any đã lưu với type URL type.googleapis.com/catalog.v1.ProductReply không tự trở thành catalog.v2.ProductReply chỉ vì schema mới đổi package. Consumer mới cần giữ khả năng resolve type cũ hoặc có bước chuyển đổi dữ liệu rõ ràng.

Do đó, đánh giá package rename phải bao gồm cả RPC path lẫn type identity của message, nhất là khi hệ thống lưu Any, descriptor hoặc dữ liệu Protobuf lâu dài.

## 5. Đổi service name hoặc RPC method name

Đổi service name nhưng giữ package:

```proto
package catalog.v1;

service CatalogProductService {
  rpc GetProduct(GetProductRequest) returns (ProductReply);
}
```

RPC path đổi từ:

```text
/catalog.v1.ProductService/GetProduct
```

sang:

```text
/catalog.v1.CatalogProductService/GetProduct
```

Đổi tên method GetProduct thành FetchProduct cũng thay đổi path, dù request/response message giữ nguyên.

Các nơi thường phụ thuộc service/method name:

- Generated Java stub và service base class.
- Server registration và gRPC reflection.
- gRPC Health Checking Protocol, trong đó health status có thể được đăng ký theo service name.
- Authorization/interceptor rules so khớp full method name.
- Service config, retry policy và load-balancing method config.
- Metrics, tracing span name, dashboard và alert.
- Gateway, transcoding config, OpenAPI hoặc client SDK.
- Integration test, command-line tool và script vận hành.

Nếu đổi tên service nhưng quên cập nhật health status hoặc authorization rule, RPC có thể chạy nhưng health probe báo sai hoặc request bị từ chối. Cần cập nhật mọi thành phần dùng full service/method name.

## 6. Vì sao reserved không giải quyết việc đổi service name?

Protobuf reserved dùng trong message và enum để khóa field number/tên hoặc enum number/tên đã xóa. Nó không phải cơ chế alias cho package, service hoặc RPC method name.

Khi ngừng một service cũ, cách bảo vệ client đang hoạt động là **tiếp tục đăng ký service/method cũ trong giai đoạn chuyển tiếp**. Không có khai báo reserved ở cấp service để server tự động ánh xạ tên cũ sang tên mới.

Với field/message, reservation và schema compatibility rules có thể ngăn một số tái sử dụng. Với service identity, cần quản lý bằng versioned API, giữ handler cũ, contract registry và kiểm thử RPC path.

## 7. Version hóa và giữ service v1/v2 cùng tồn tại

Một cách phổ biến là giữ package/service v1 và thêm API v2. Message dùng chung có thể vẫn ở package v1, còn service mới đặt trong package v2:

```proto
syntax = "proto3";

package catalog.v2;

import "catalog/v1/product_messages.proto";

service ProductService {
  rpc GetProduct(catalog.v1.GetProductRequest)
      returns (catalog.v1.ProductReply);
}
```

Trong giai đoạn chuyển tiếp, server đăng ký cả service v1 và v2. Cả hai adapter có thể gọi cùng application/domain service:

```java
Server server = ServerBuilder.forPort(port)
    .addService(new ProductServiceV1Adapter(applicationService))
    .addService(new ProductServiceV2Adapter(applicationService))
    .build();
```

Tên class adapter là minh họa. Mỗi adapter được sinh từ service definition tương ứng; adapter chuyển đổi request/response nếu contract v2 có message khác.

Cách này cho phép client cũ tiếp tục gọi full method name v1, client mới gọi v2, và business logic dùng chung. Nếu cần đổi cả message package, tạo message v2 và viết mapping giữa message v1/v2 với domain model. Nếu chỉ cần đổi service namespace, có thể import và tái sử dụng message types hiện có.

## 8. Trình tự rollout an toàn

Đổi package/service name cần triển khai theo thứ tự server/reader trước client:

1. **Kiểm kê consumers:** xác định client version, service path, gateway, health probe, auth policy, service config, reflection và dữ liệu Any.
2. **Định nghĩa API mới:** tạo package/service v2; giữ method cũ trong schema v1 trong giai đoạn chuyển tiếp.
3. **Triển khai server dual registration:** server mới đăng ký cả v1 và v2, cùng xử lý qua application service hoặc adapter.
4. **Cập nhật hạ tầng:** health service, authorization/interceptor, routing, metrics, tracing và gateway nhận diện cả hai tên.
5. **Kiểm thử server mới:** gọi cả full method name v1 và v2; xác nhận cả hai hoạt động.
6. **Phát hành client v2:** chuyển dần consumer sang endpoint/method mới; giữ khả năng rollback.
7. **Theo dõi traffic v1:** đo request count, lỗi và consumer còn gọi service cũ.
8. **Ngừng v1 có điều kiện:** chỉ sau khi xác nhận không còn consumer, dữ liệu hoặc job cần v1 và đã qua thời gian rollback.
9. **Gỡ đăng ký cũ:** xóa service v1 trong release riêng, thông báo deprecation và cập nhật contract baseline.

Không chỉ dựa vào việc client v2 đã được phát hành để xóa service v1. Batch jobs, mobile clients, integration bên ngoài hoặc queue consumers có thể nâng cấp chậm hơn.

## 9. Kiểm thử tương thích và định tuyến

CI nên kiểm tra cả schema và RPC path thực tế:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| Descriptor test | ServiceDescriptor có full service name mong đợi |
| Method descriptor test | Full method name giữ đúng package/service/method |
| Old client → new server | Server dual-register vẫn nhận RPC v1 |
| New client → new server | RPC v2 hoạt động |
| New client → old server | Xác định rõ có hỗ trợ rollback hay không |
| Health check | Health service trả trạng thái cho cả service name v1/v2 |
| Reflection | Client/tooling thấy service version cần thiết |
| Auth/interceptor | Policy khớp full method name của cả hai phiên bản |
| Any payload | Type URL cũ được resolve hoặc migrate theo kế hoạch |
| Gateway/JSON | Route và mapping không bị mất khi đổi namespace |

Ví dụ test descriptor ở Java:

```java
assertEquals(
    "catalog.v2.ProductService",
    ProductServiceGrpc.getServiceDescriptor().getName()
);

assertEquals(
    "catalog.v2.ProductService/GetProduct",
    ProductServiceGrpc.getGetProductMethod().getFullMethodName()
);
```

Tên generated class phụ thuộc java_package và các option sinh code; dùng đúng class từ contract đang kiểm tra. Test descriptor xác nhận định danh mà generated code sẽ gọi, còn integration test xác nhận server thực sự đăng ký handler tương ứng.

Ngoài test path, chạy schema breaking check so với baseline đã phát hành. Công cụ schema và test descriptor không thay thế kiểm tra gateway, health, authorization và traffic production.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client cũ nhận UNIMPLEMENTED | Server không còn đăng ký full method name cũ | Dual-register v1/v2 trong giai đoạn chuyển tiếp |
| Java client không compile sau khi đổi java_package | Generated class chuyển namespace | Cập nhật imports hoặc version hóa contract artifact |
| RPC path đổi dù Java package giữ nguyên | Protobuf package hoặc service name đã đổi | Kiểm tra full method name từ descriptor |
| Health probe báo NOT_SERVING/unknown | Health registry chỉ đăng ký service name mới hoặc cũ | Đăng ký health status cho từng service name cần hỗ trợ |
| Authorization từ chối RPC mới | Interceptor rule vẫn match path cũ | Cập nhật policy cho full method name mới |
| Reflection/tool không thấy service cũ | Server không còn đăng ký service cũ hoặc reflection chưa cập nhật | Kiểm tra registered services và reflection |
| Any.unpack() thất bại | Type URL dùng protobuf message FQN cũ | Giữ type cũ hoặc chuyển đổi type URL/dữ liệu có kiểm soát |
| Metrics bị chia thành series mới | Full method name/label thay đổi | Cập nhật dashboard và theo dõi song song hai tên |

Khi chẩn đoán, lấy full method name từ client descriptor hoặc trace. Đừng suy luận RPC path từ package Java; hai namespace có vai trò khác nhau.

## 11. Checklist review thay đổi package/service

- Đã xác định đây là đổi protobuf package, service name, RPC method name hay chỉ java_package.
- Đã ghi lại full gRPC method name cũ và mới.
- Đã rà soát message fully-qualified names, descriptor/reflection và Any type URLs nếu đổi protobuf package.
- Đã đánh giá generated Java API nếu đổi java_package, java_outer_classname hoặc codegen options.
- Service v1 vẫn được đăng ký khi còn client cũ.
- Server v2 đã sẵn sàng trước khi chuyển client.
- Health checking, auth/interceptor, service config, gateway và observability đã cập nhật.
- Có descriptor tests và integration tests cho cả path v1/v2.
- Có kế hoạch đo traffic cũ, deprecate và thời điểm gỡ v1.
- CI breaking check dùng baseline đã phát hành và ghi nhận contract version mới.

Với **SPRING_GRPC**, protobuf package và service name là một phần của RPC identity, còn java_package chủ yếu quyết định namespace của code Java sinh ra. Đổi nhầm hoặc thay đổi không có dual registration có thể làm client cũ gọi vào một method path không còn tồn tại. Giữ service cũ trong giai đoạn chuyển tiếp, triển khai server hỗ trợ v2 trước client và kiểm thử full method name cùng các tích hợp phụ thuộc sẽ giúp nâng cấp có kiểm soát.
