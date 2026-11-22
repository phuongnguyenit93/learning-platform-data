# Versioning package và service

Khi một API gRPC đã có client đang chạy, thay đổi hợp đồng không chỉ ảnh hưởng file Protocol Buffers và mã Java được sinh. Tên package protobuf và tên service còn tạo nên **định danh RPC trên đường truyền**. Đổi chúng có thể khiến client cũ gọi vào một đường dẫn mà server mới không còn đăng ký, dù nội dung xử lý gần như giống nhau.

Trong **Spring gRPC**, versioning package và service giúp nhiều thế hệ API cùng tồn tại trong thời gian chuyển đổi. Bài này tập trung vào cách phân biệt `package` của protobuf với `java_package`, xác định khi nào cần v1/v2, cách đặt tên service và triển khai hai phiên bản song song.

## 1. Ba tên khác nhau, ba tác động khác nhau

Xét file `catalog/v1/catalog.proto`:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
}
```

Các khai báo có vai trò riêng:

| Khai báo | Dùng để làm gì? | Thay đổi sẽ ảnh hưởng |
| --- | --- | --- |
| `package shop.catalog.v1;` | Namespace của message, enum và service trong descriptor protobuf | Tên đầy đủ của kiểu; tên đầy đủ của service và đường dẫn RPC |
| `option java_package = "...";` | Package Java chứa các lớp sinh ra | Import, tên lớp được sinh và mã Java phụ thuộc |
| `service CatalogService` | Tên service trong hợp đồng gRPC | Đường dẫn RPC của mọi method trong service |
| Đường dẫn file `catalog/v1/catalog.proto` | Vị trí file nguồn và tên được dùng trong `import` | Build/import path; không tự quyết định protobuf package |

Với khai báo trên, tên service đầy đủ là `shop.catalog.v1.CatalogService`; đường dẫn phương thức là:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

Đường dẫn này được tạo từ **protobuf package + service name + method name**. `java_package` không tham gia tạo đường dẫn đó.

Ví dụ nếu chỉ đổi:

```proto
option java_package = "com.myshop.generated.catalog";
```

thì lớp Java được sinh sẽ chuyển package, nhưng service vẫn được gọi qua `/shop.catalog.v1.CatalogService/GetProduct`. Ngược lại, đổi `package shop.catalog.v1` thành `shop.catalog.v2` sẽ đổi định danh service và message trong protobuf, kể cả khi giữ nguyên `java_package`.

## 2. Khi nào giữ v1, khi nào tạo v2?

Không cần tạo package mới cho mọi lần thêm field. Hãy phân biệt thay đổi **mở rộng tương thích** với thay đổi làm client hiểu sai hoặc không thể tiếp tục sử dụng hợp đồng.

| Thay đổi | Hướng xử lý thường phù hợp |
| --- | --- |
| Thêm field mới với field number chưa dùng và fallback an toàn | Giữ `shop.catalog.v1` |
| Thêm một RPC mới mà không đổi hành vi các RPC hiện tại | Có thể bổ sung vào service v1; triển khai server trước khi client gọi method mới |
| Thêm enum value mà mọi consumer có nhánh xử lý unknown an toàn | Có thể giữ v1, nhưng phải rollout có kiểm soát |
| Đổi ý nghĩa một field đang được client sử dụng | Tạo API mới hoặc v2; không âm thầm thay ngữ nghĩa v1 |
| Đổi kiểu/field number theo cách không tương thích | Thiết kế message/API v2 |
| Đổi tên service hoặc method đã phát hành | Đường dẫn RPC thay đổi; giữ endpoint cũ song song hoặc công bố API mới |
| Bỏ một hành vi mà client cũ vẫn phụ thuộc | Giữ v1 trong thời gian chuyển; v2 định nghĩa hành vi mới |

Một nguyên tắc thực tế: **v1 tiếp tục giữ hợp đồng và hành vi đã công bố; v2 dành cho thay đổi không thể tương thích một cách an toàn**. Version mới không phải cách thay thế cho việc đánh giá tương thích. Nếu chỉ thêm một trường tùy chọn có default an toàn, tạo v2 có thể làm tăng chi phí client, tài liệu và vận hành mà không đem lại lợi ích.

### Thay đổi cấu trúc và thay đổi hành vi

Có thay đổi vẫn parse được bằng protobuf binary nhưng vẫn phá hợp đồng. Ví dụ, đổi ý nghĩa `price_minor_units` từ “đồng” sang “xu” không nhất thiết làm wire format thay đổi, nhưng client sẽ tính sai giá. Tương tự, server có thể bắt đầu yêu cầu một field mới và trả `INVALID_ARGUMENT` cho client v1 dù schema mới vẫn parse được request cũ.

Khi quyết định versioning, hãy xem xét cả:

- **Wire compatibility:** các field cũ còn giải mã đúng không?
- **Behavior compatibility:** client cũ có nhận kết quả và lỗi như trước không?
- **Source compatibility:** mã Java sinh ra còn các lớp, accessor và method mà ứng dụng đang dùng không?
- **Routing compatibility:** client cũ còn gọi đúng full method path không?

## 3. Đặt phiên bản trong protobuf package

Với thay đổi lớn ảnh hưởng nhiều message hoặc nhiều service trong cùng miền, đưa phiên bản vào protobuf package là cách rõ ràng:

```proto
// catalog/v1/catalog.proto
package shop.catalog.v1;
option java_package = "com.myshop.grpc.catalog.v1";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
}
```

Khi cần thay đổi không tương thích:

```proto
// catalog/v2/catalog.proto
package shop.catalog.v2;
option java_package = "com.myshop.grpc.catalog.v2";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
  string locale = 2;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
  string localized_description = 3;
}
```

Hai service có cùng tên ngắn `CatalogService`, nhưng khác protobuf package nên có tên đầy đủ và đường dẫn RPC khác nhau:

| Phiên bản | Full service name | Method path |
| --- | --- | --- |
| v1 | `shop.catalog.v1.CatalogService` | `/shop.catalog.v1.CatalogService/GetProduct` |
| v2 | `shop.catalog.v2.CatalogService` | `/shop.catalog.v2.CatalogService/GetProduct` |

Client v1 tiếp tục gọi v1; client đã nâng cấp gọi v2. Cả hai có thể chạy trên cùng server/port nếu server đăng ký cả hai service. Việc cùng dùng method name `GetProduct` không gây xung đột vì full service name khác nhau.

### Không nhầm package với thư mục

Đường dẫn file `catalog/v2/catalog.proto` là quy ước tổ chức source. Compiler không tự suy ra `package shop.catalog.v2` từ thư mục. Cũng không nên nghĩ rằng chuyển file từ `catalog/v1` sang `catalog/v2` sẽ tự đổi tên RPC; cần sửa khai báo `package` và các import liên quan nếu muốn thay đổi namespace.

## 4. Khi nào version service name thay vì package?

Đôi khi chỉ một nhóm method cần thay đổi, còn message dùng chung vẫn giữ nguyên ngữ nghĩa. Khi đó có thể giữ package và thêm service mới:

```proto
package shop.catalog.v1;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

service CatalogAdminService {
  rpc ReindexCatalog(ReindexCatalogRequest)
      returns (ReindexCatalogResponse);
}
```

Nếu cần một hành vi mới không tương thích ở đúng một service, cũng có thể công bố service tên mới, chẳng hạn `CatalogQueryV2Service`, trong khi các message vẫn thuộc package hiện tại. Tuy nhiên, cách này cần quy ước tên nhất quán và có thể khiến package chứa nhiều thế hệ hợp đồng.

Nên chọn theo phạm vi thay đổi:

- **Version package** khi message, enum và nhiều service của một API cùng cần một thế hệ hợp đồng mới. Cách này cô lập namespace v1/v2 rõ ràng.
- **Version service** khi chỉ một ranh giới service thay đổi, các message liên quan vẫn tương thích và nhóm muốn duy trì các service khác trong cùng package.
- **Thêm method vào service hiện tại** khi đó là chức năng mới có thể bổ sung mà không thay đổi semantics của method cũ.

Nếu chỉ version service nhưng request/response mới cũng không tương thích, hãy khai báo message mới với tên riêng, chẳng hạn `GetProductV2Request` và `GetProductV2Response`; không thay đổi định nghĩa message cũ mà client v1 vẫn sử dụng. Nếu nhiều message cùng cần thay đổi, version package thường tạo ranh giới sạch hơn.

Tránh đặt phiên bản ở cả package lẫn service một cách dư thừa như `shop.catalog.v2.CatalogServiceV2`, trừ khi có quy ước cụ thể giải thích hai số phiên bản đại diện cho hai vòng đời độc lập. Thông thường chọn một nơi làm ranh giới version là dễ đọc hơn.

## 5. Đổi protobuf package ảnh hưởng những gì?

Đổi `package` không đổi field number của message, do đó payload binary của một message có thể vẫn mang cùng các tag. Tuy nhiên, **định danh kiểu** trong protobuf thay đổi:

1. **RPC routing:** full service name thay đổi; client stub cũ vẫn gọi đường dẫn cũ. Nếu server chỉ đăng ký service dưới package mới, client cũ thường nhận `UNIMPLEMENTED`.
2. **Descriptor và reflection:** tên đầy đủ của message/service khác; công cụ reflection, schema registry hoặc hệ thống dựa trên descriptor phải cập nhật.
3. **`google.protobuf.Any`:** type URL mặc định chứa full message name, ví dụ `type.googleapis.com/shop.catalog.v1.Product`. Đổi package làm type URL đổi, nên consumer cần xử lý cả hai định danh trong thời gian chuyển đổi nếu dữ liệu Any được lưu hoặc trao đổi.
4. **Generated Java:** nếu `java_package` cũng đổi, import và binary/source API Java thay đổi. Nếu chỉ đổi protobuf package, các lớp Java có thể vẫn nằm trong package Java cũ nhưng descriptor protobuf vẫn mang tên mới.
5. **Các file import:** tham chiếu kiểu đầy đủ và import source có thể cần điều chỉnh. Đường dẫn file và protobuf package là hai khái niệm riêng.

Do đó, không xem đổi protobuf package là refactor tên thư mục. Nó tạo ra một API identity mới ở tầng protobuf/gRPC.

## 6. Đổi java_package có phải version API không?

Không. `java_package` chỉ điều khiển namespace Java sinh ra. Ví dụ:

```proto
package shop.catalog.v1;
option java_package = "com.myshop.grpc.catalog.generated";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
```

Full service name vẫn là `shop.catalog.v1.CatalogService`; method path vẫn là `/shop.catalog.v1.CatalogService/GetProduct`. Nhưng code Java sẽ import các lớp từ `com.myshop.grpc.catalog.generated`.

Đổi `java_package` có thể làm dự án Java không biên dịch cho đến khi cập nhật import, dependency và artifact sinh mã. Nếu có nhiều module Java tiêu thụ generated classes, hãy xem đây là thay đổi API ở tầng source/binary Java và lên kế hoạch nâng cấp. Nó không tạo endpoint gRPC v2 và không cho phép server v1/v2 tự động cùng tồn tại.

Khi biên dịch v1 và v2 trong cùng một Java artifact, nên đặt `java_package` khác nhau (thường cũng có hậu tố phiên bản) để các lớp message trùng tên đơn giản không va chạm. Đây là quyết định namespace của mã Java; đường dẫn RPC vẫn do protobuf package và service name quyết định.

## 7. Triển khai v1 và v2 cùng lúc trong Spring gRPC

Khi hai package khác nhau, mã sinh ra tạo hai lớp service base riêng. Server có thể đăng ký hai implementation:

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogV1Endpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    // Giữ hành vi và contract v1 đã công bố.
}

@GrpcService
public class CatalogV2Endpoint
        extends com.myshop.grpc.catalog.v2.CatalogServiceGrpc.CatalogServiceImplBase {
    // Ánh xạ request/response v2 vào domain service nếu phù hợp.
}
```

Ví dụ giả định phiên bản Spring gRPC của dự án dùng `@GrpcService` để phát hiện implementation. Điều cần kiểm tra khi tích hợp là server đăng ký được **hai full service name khác nhau**. Không đăng ký hai implementation cùng một full service name trên cùng server, vì chúng cạnh tranh cùng một endpoint.

Hai endpoint có thể gọi chung domain/application service:

```text
CatalogV1Endpoint ──┐
                    ├── CatalogApplicationService ── Repository
CatalogV2Endpoint ──┘
```

Điều này giúp giữ logic nghiệp vụ nhất quán trong khi adapter v1/v2 chuyển đổi các message khác nhau. Không nên để implementation v2 gọi qua RPC v1 của chính server nếu có thể gọi trực tiếp application service; việc gọi vòng qua mạng tạo thêm timeout, serialization và phụ thuộc vận hành.

## 8. Kế hoạch chuyển client từ v1 sang v2

Versioning chỉ hữu ích khi có đường di chuyển rõ ràng:

1. **Công bố v2:** định nghĩa package, message và semantics mới; ghi rõ khác biệt với v1.
2. **Triển khai server hỗ trợ song song:** đăng ký cả `shop.catalog.v1.CatalogService` và `shop.catalog.v2.CatalogService`.
3. **Kiểm thử hai hợp đồng:** xác nhận client v1 vẫn có hành vi cũ; client v2 có thể gọi endpoint mới và xử lý status đúng.
4. **Phát hành client v2 theo đợt:** chuyển một nhóm traffic trước, theo dõi lỗi `UNIMPLEMENTED`, `INVALID_ARGUMENT`, latency và tỷ lệ sử dụng từng service.
5. **Thông báo ngừng v1:** xác định thời hạn, nhóm consumer còn lại và phương án hỗ trợ đối tác.
6. **Gỡ v1 sau khi xác nhận không còn consumer:** chỉ xóa service cũ khi có bằng chứng traffic đã chuyển, không chỉ dựa vào việc code client mới đã phát hành.

Nếu v2 dùng cùng endpoint host/port, client chọn phiên bản bằng generated stub tương ứng. gRPC không tự thương lượng package version hoặc tự chuyển từ v1 sang v2. Một lời gọi tới full method path không tồn tại sẽ không tự động được route sang service gần giống tên.

### Theo dõi traffic theo full method name

Metrics/interceptor nên phân biệt các method như:

```text
shop.catalog.v1.CatalogService/GetProduct
shop.catalog.v2.CatalogService/GetProduct
```

Nhờ đó nhóm vận hành biết client nào còn dùng v1, v2 có phát sinh lỗi gì và khi nào có thể ngừng v1. Tránh gắn nhãn metric bằng ID người dùng hoặc dữ liệu nhạy cảm; full method name thường đủ để phân tích mức sử dụng API.

## 9. Checklist chọn ranh giới version

- [ ] Đã xác định thay đổi là additive hay phá vỡ wire, behavior, source hoặc routing compatibility.
- [ ] Đã phân biệt `package`, `java_package`, service name và file path.
- [ ] Nếu tạo package v2, các message/service mới có full name riêng và không vô tình trùng descriptor.
- [ ] Nếu chỉ version service, phạm vi message dùng chung vẫn có semantics tương thích.
- [ ] Không version cả package lẫn service dư thừa nếu không có lý do độc lập.
- [ ] Đã kiểm tra `Any` type URL, reflection và schema registry nếu hệ thống sử dụng.
- [ ] Server có thể đăng ký song song hai full service name và giữ v1 hoạt động.
- [ ] Client chọn đúng generated stub; không trông chờ gRPC tự fallback giữa phiên bản.
- [ ] Có metrics theo full method name, kế hoạch migration và tiêu chí ngừng v1.

**Tự kiểm tra**

**Câu 1.** Đổi `option java_package` từ `com.myshop.grpc.catalog.v1` sang `com.myshop.generated.catalog` có làm đổi đường dẫn `/shop.catalog.v1.CatalogService/GetProduct` không?

*Đáp án:* Không. Đường dẫn dựa trên protobuf package, service name và method name. Java package chỉ đổi vị trí lớp sinh ra.

**Câu 2.** Đổi `package shop.catalog.v1` thành `shop.catalog.v2` nhưng giữ nguyên service name có tác động gì?

*Đáp án:* Full service name và method path thay đổi; message full names/descriptor cũng đổi. Field wire có thể vẫn giải mã nếu tag/type giữ nguyên, nhưng đây là một API identity mới.

**Câu 3.** Khi nào nên thêm method vào service v1 thay vì tạo package v2?

*Đáp án:* Khi chức năng mới là mở rộng không phá semantics hiện tại, message cũ vẫn dùng đúng và client v1 không bị thay đổi hành vi. Server phải được triển khai method trước khi client gọi.

**Câu 4.** Có thể đăng ký v1 và v2 cùng một server không?

*Đáp án:* Có, nếu chúng có full service name khác nhau, thường nhờ protobuf package version khác nhau. Hai implementation cùng full service name sẽ xung đột.

Versioning package và service là cách quản lý **định danh API**, không chỉ là đặt tên thư mục. Giữ v1 cho thay đổi tương thích, tạo v2 khi semantics hoặc định danh không thể giữ nguyên, và chạy song song hai service trong thời gian chuyển đổi giúp client Spring gRPC nâng cấp có kiểm soát.
