# Đặt package cho proto trong Spring gRPC

Khi phát triển dịch vụ gRPC với Spring, file Protocol Buffers (thường có đuôi `.proto`) là hợp đồng dùng chung giữa client và server. Một quyết định tưởng nhỏ như đặt `package` sẽ ảnh hưởng đến tên dịch vụ trên mạng, cách các thông điệp được tham chiếu, vị trí các lớp Java sinh ra và khả năng phát triển API sau này. Vì vậy, nên thống nhất quy ước package **trước khi** sinh mã và công bố hợp đồng cho các bên sử dụng.

Sau bài này, bạn có thể:

- Phân biệt `package` của Protocol Buffers với `option java_package` và đường dẫn thư mục chứa file `.proto`.
- Thiết kế namespace rõ miền nghiệp vụ và phiên bản, tránh trùng tên khi tách nhiều dịch vụ Spring gRPC.
- Đọc được tên service trên đường truyền và tên lớp Java được sinh từ cùng một schema.
- Đánh giá tác động của việc đổi package và kiểm tra lỗi thường gặp khi các proto import lẫn nhau.

## 1. Ba khái niệm dễ nhầm lẫn

Giả sử chúng ta có dịch vụ tra cứu sản phẩm của hệ thống bán hàng. Trong file `catalog/v1/catalog.proto`:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";
```

Các tên trên có ba vai trò khác nhau:

| Thành phần | Vai trò | Trong ví dụ |
| --- | --- | --- |
| `package shop.catalog.v1;` | Namespace **logic của Protocol Buffers**: phân biệt message, enum và service; tham gia tạo tên RPC đầy đủ. | `shop.catalog.v1.CatalogService` |
| `option java_package = "...";` | Package của các **lớp Java được sinh ra** từ file proto. | `com.myshop.grpc.catalog.v1` |
| Đường dẫn `catalog/v1/catalog.proto` | Vị trí file nguồn và tên dùng trong lệnh `import` (tính từ một proto import root). | `import "catalog/v1/catalog.proto";` |

**Điểm quan trọng:** `java_package` không đổi tên service trên mạng. Ngược lại, `package` của proto không buộc các lớp Java phải nằm trong một package cùng tên khi đã khai báo `java_package`. Đường dẫn file cũng không tự thiết lập hai namespace này.

Nếu không khai báo `java_package`, trình sinh mã Java thường sử dụng namespace từ `package` của proto. Tuy nhiên, khai báo tường minh giúp hợp đồng dễ hiểu và tránh phải phụ thuộc vào quy tắc mặc định của từng ngôn ngữ.

### Các option Java liên quan

- `java_multiple_files = true`: sinh các lớp Java cấp cao riêng cho message, enum và service code do plugin gRPC tạo. Đây là cách tổ chức thường dễ dùng trong dự án Spring. Phần mô tả file vẫn có thể nằm trong lớp outer.
- `java_outer_classname = "CatalogProto"`: đặt tên lớp Java chứa thông tin mô tả file; đặc biệt hữu ích để tránh tên mặc định trùng với message. Option này **không** đổi tên RPC.
- `java_package` là option dành riêng cho Java. Client viết bằng Go, C# hoặc ngôn ngữ khác có quy tắc và option sinh mã riêng nhưng vẫn dùng cùng `package` của proto.

## 2. Chọn một quy ước namespace nhất quán

Một quy ước dễ mở rộng là:

```text
<tổ-chức>.<miền-nghiệp-vụ>.<phiên-bản>
```

Ví dụ:

| Nhu cầu | Proto package | Java package |
| --- | --- | --- |
| Tra cứu sản phẩm phiên bản 1 | `shop.catalog.v1` | `com.myshop.grpc.catalog.v1` |
| Đặt hàng phiên bản 1 | `shop.order.v1` | `com.myshop.grpc.order.v1` |
| Kiểu dữ liệu chia sẻ phiên bản 1 | `shop.common.v1` | `com.myshop.grpc.common.v1` |
| API sản phẩm có thay đổi phá vỡ tương thích | `shop.catalog.v2` | `com.myshop.grpc.catalog.v2` |

Tên tổ chức và miền nghiệp vụ trong bảng chỉ là ví dụ; dự án nên chọn một tiền tố thuộc quyền quản lý của mình. Dùng chữ thường và các thành phần ngắn, rõ nghĩa; đặt tên message theo `UpperCamelCase` và field theo `snake_case`. Không dùng chung một namespace quá rộng như `shop.v1` cho mọi miền: hai nhóm rất dễ tạo trùng `CreateRequest`, `Status` hoặc `Result`.

**Khi nào thêm `v1`?** Nên đưa phiên bản lớn vào namespace ngay từ hợp đồng công khai đầu tiên. Các bổ sung tương thích có thể tiếp tục ở `v1`; khi cần thay đổi phá vỡ hợp đồng, tạo `v2` và cho phép hai phiên bản cùng tồn tại trong giai đoạn chuyển đổi. Không cần thay package mỗi lần thêm một field tương thích.

## 3. Ví dụ hoàn chỉnh: hai proto và một dịch vụ

Tổ chức file nguồn:

```text
src/main/proto/
├── common/
│   └── v1/
│       └── money.proto
└── catalog/
    └── v1/
        └── catalog.proto
```

Trong `src/main/proto/common/v1/money.proto`:

```proto
syntax = "proto3";

package shop.common.v1;

option java_package = "com.myshop.grpc.common.v1";
option java_multiple_files = true;
option java_outer_classname = "MoneyProto";

message Money {
  string currency_code = 1;
  int64 units = 2;
  int32 nanos = 3;
}
```

Trong `src/main/proto/catalog/v1/catalog.proto`:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";

import "common/v1/money.proto";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
  .shop.common.v1.Money unit_price = 3;
}
```

Trong ví dụ này:

1. `import "common/v1/money.proto"` cho trình biên dịch biết file nào định nghĩa `Money`. Đường dẫn import được giải từ thư mục gốc được cấu hình cho trình biên dịch proto, ở đây là `src/main/proto`.
2. `.shop.common.v1.Money` là **tên kiểu protobuf đầy đủ**. Dấu chấm ở đầu biểu thị việc tra cứu từ namespace gốc, tránh nhầm với kiểu có tên gần giống ở package hiện tại.
3. `shop.catalog.v1` là namespace của `CatalogService`, `GetProductRequest` và `GetProductResponse`, còn `shop.common.v1` là namespace của `Money`. Import **không** đưa các kiểu của package khác vào cùng namespace.
4. Việc các thư mục `common/v1` và `catalog/v1` trùng với phần cuối của package là quy ước hỗ trợ tra cứu; đó không phải yêu cầu cú pháp của Protocol Buffers.

### Kết quả sinh mã Java

Với trình biên dịch Protocol Buffers và plugin gRPC Java được cấu hình trong dự án, các lớp thường được sinh ra tương tự:

```text
com.myshop.grpc.common.v1
  ├── Money
  └── MoneyProto

com.myshop.grpc.catalog.v1
  ├── CatalogProto
  ├── GetProductRequest
  ├── GetProductResponse
  └── CatalogServiceGrpc
```

`CatalogServiceGrpc` chứa mã gRPC Java sinh từ `service CatalogService`, trong khi `GetProductRequest` và `GetProductResponse` là các lớp thông điệp. Cách bố trí này giúp code Spring import trực tiếp lớp cần dùng:

```java
import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import com.myshop.grpc.common.v1.Money;
```

Chẳng hạn, một triển khai server sử dụng Spring gRPC có thể viết như sau (giả sử dự án đã cấu hình runtime và công cụ sinh mã tương ứng):

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import com.myshop.grpc.common.v1.Money;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {

        if (request.getProductId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id is required")
                    .asRuntimeException());
            return;
        }

        GetProductResponse response = GetProductResponse.newBuilder()
                .setProductId(request.getProductId())
                .setDisplayName("Sản phẩm mẫu")
                .setUnitPrice(Money.newBuilder()
                        .setCurrencyCode("VND")
                        .setUnits(125000)
                        .build())
                .build();

        observer.onNext(response);
        observer.onCompleted();
    }
}
```

Package `com.myshop.server.catalog` là package của **mã nguồn tự viết** và không cần trùng với package của code sinh ra. Annotation `@GrpcService` hỗ trợ Spring gRPC phát hiện và đăng ký implementation; vị trí lớp `CatalogServiceGrpc` vẫn do `java_package` quyết định. Tên annotation và cấu hình đăng ký cụ thể cần phù hợp với phiên bản thư viện Spring gRPC dự án sử dụng.

### Tên nào xuất hiện trên mạng?

Từ khai báo service trong proto:

```proto
package shop.catalog.v1;
service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
```

gRPC dùng:

- Tên service đầy đủ: `shop.catalog.v1.CatalogService`.
- Tên phương thức đầy đủ: `shop.catalog.v1.CatalogService/GetProduct`.
- Đường dẫn HTTP/2 của lời gọi: `/shop.catalog.v1.CatalogService/GetProduct`.

Việc đổi `java_package` sang một tên Java khác **không làm đổi** ba giá trị này; việc đổi `package shop.catalog.v1` thì có. Client có stub cũ thường không gọi được server chỉ đăng ký service dưới tên package mới, kể cả khi mã xử lý giống hệt.

## 4. Điều gì xảy ra khi thay đổi package?

| Thay đổi | Ảnh hưởng quan trọng | Cách xử lý |
| --- | --- | --- |
| Đổi `package shop.catalog.v1` thành `shop.catalog.v2` | Đổi tên đầy đủ của service và message trong descriptor; đổi đường dẫn RPC, ảnh hưởng client, reflection và các tham chiếu kiểu. | Xem như thay đổi hợp đồng; tạo và triển khai API `v2` song song trong thời gian di chuyển client. |
| Đổi `java_package` nhưng giữ nguyên proto package | Lớp Java chuyển namespace, làm hỏng import hoặc tham chiếu nhị phân ở mã Java cũ; tên RPC trên mạng giữ nguyên. | Cập nhật các dự án Java và sinh lại stub cùng hợp đồng. |
| Đổi `java_multiple_files` | Cách tổ chức các lớp Java được sinh thay đổi; có thể cần sửa import và tham chiếu kiểu. | Quyết định sớm, giữ ổn định khi các dự án đã phụ thuộc mã sinh. |
| Đổi `java_outer_classname` | Tên lớp Java chứa descriptor hoặc lớp bọc có thể thay đổi. | Kiểm tra nơi sử dụng outer class rồi sinh lại mã. |
| Chuyển/đổi tên file `.proto` | Đường dẫn `import` và cấu hình build ở các dự án khác có thể hỏng; tên RPC không tự đổi chỉ vì chuyển file. | Cập nhật import path và cấu hình biên dịch cho toàn bộ bên tiêu thụ. |

Proto3 mã hóa trường dữ liệu theo **số field và wire type**, vì vậy việc đổi proto package riêng lẻ không nhất thiết thay đổi byte của một message thông thường. Tuy nhiên, sự tương thích trên đường truyền của riêng message **không đồng nghĩa** tương thích API gRPC: tên service dùng để định tuyến sẽ khác. Kiểu `google.protobuf.Any`, hệ thống reflection hoặc mã xử lý descriptor còn có thể phụ thuộc trực tiếp vào tên message đầy đủ.

Ngoài package, khi phát triển schema cần giữ ổn định số field đã phát hành; nếu xóa field, nên dùng `reserved` cho số và tên cũ để ngăn tái sử dụng nhầm. Đó là quy tắc tương thích độc lập với việc đặt namespace.

## 5. Quy trình quyết định package cho một API mới

1. **Xác định chủ sở hữu API:** chọn tiền tố do tổ chức quản lý, ví dụ `shop`, thay vì tên tùy hứng dễ trùng với hệ thống khác.
2. **Xác định miền nghiệp vụ:** `catalog`, `order` hoặc `identity`. Nếu hai loại message có vòng đời và chủ sở hữu khác nhau, cân nhắc tách package.
3. **Xác định phiên bản hợp đồng:** bắt đầu với `v1`; chuẩn bị chiến lược chạy đồng thời `v1` và `v2` nếu cần thay đổi phá vỡ tương thích.
4. **Chọn Java package tường minh:** dùng namespace phù hợp với quy ước công ty, ví dụ `com.myshop.grpc.catalog.v1`, và giữ nhất quán giữa các file cùng miền.
5. **Đặt tên file và import root:** bố trí `src/main/proto/catalog/v1/` theo cấu trúc có thể dự đoán, cấu hình một hoặc nhiều import root rõ ràng khi biên dịch.
6. **Sinh mã và xem tên thực tế:** kiểm tra import của `GetProductRequest`/`CatalogServiceGrpc` và tên service đầy đủ; thử một lời gọi end-to-end khi server đã chạy.
7. **Công bố hợp đồng cùng quy ước:** client và server sinh mã từ cùng phiên bản proto; quản lý thay đổi bằng version control và quy trình review API.

Ví dụ kiểm tra phương thức đã đăng ký bằng `grpcurl` khi server thử nghiệm đang lắng nghe tại `localhost:9090`, hỗ trợ kết nối plaintext và file proto khả dụng ở vị trí nói trên:

```bash
grpcurl -plaintext -import-path src/main/proto -proto catalog/v1/catalog.proto -d '{"productId":"P-100"}' localhost:9090 shop.catalog.v1.CatalogService/GetProduct
```

Phần cuối lệnh là tên service/phương thức của **proto package**, không phải `com.myshop.grpc.catalog.v1.CatalogServiceGrpc`. Cổng, TLS và địa chỉ server là cấu hình triển khai riêng; đổi namespace không thay thế việc cấu hình bảo mật hay endpoint.

## 6. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| Java báo `package ... does not exist` khi import stub | Dùng proto `package` để import Java trong khi `java_package` khác; hoặc chưa sinh/thêm mã vào classpath. | Mở cấu hình `java_package`, kiểm tra lớp đã sinh và thiết lập build. |
| Compiler báo không tìm được `common/v1/money.proto` | Import root chưa bao phủ `src/main/proto`, hoặc đường dẫn `import` không khớp. | Sửa proto include path hoặc cấu trúc thư mục, rồi biên dịch lại. |
| Compiler không nhận `Money` hoặc bị mơ hồ tên | File đã import nhưng dùng sai namespace, hoặc hai package có kiểu trùng tên. | Tham chiếu `.shop.common.v1.Money` và kiểm tra `package` trong file định nghĩa. |
| Client nhận `UNIMPLEMENTED` dù server đã chạy | Client gọi tên service/method cũ; server đăng ký package mới, hoặc chưa đăng ký implementation. | Đối chiếu tên service đầy đủ với các service server thực tế cung cấp và cấu hình đăng ký Spring gRPC. |
| Code Java bị xung đột lớp cùng tên | Nhiều proto dùng cùng `java_package` và các tên message/outer class trùng nhau. | Tách package theo miền/phiên bản, chỉnh tên lớp và sinh lại mã. |
| Client nhiều ngôn ngữ thấy tên khác kỳ vọng | Nhầm tên Java với tên protobuf, hoặc dựa vào option dành riêng cho một ngôn ngữ. | Thống nhất schema và proto `package`; xác minh option sinh mã cho từng ngôn ngữ. |

## 7. Tự kiểm tra kiến thức

**Tình huống A:** File `catalog.proto` có `package shop.catalog.v1;` và `option java_package = "com.myshop.api.catalog";`. Client gọi `/shop.catalog.v1.CatalogService/GetProduct`. Nếu đổi `java_package` thành `com.myshop.grpc.catalog.v1` nhưng không sửa proto package, đường dẫn gRPC có đổi không?

**Đáp án:** Không. Đường dẫn gRPC dựa trên proto `package`, tên `service` và tên `rpc`. Các dự án Java có thể cần sửa import, biên dịch và phân phối lại thư viện mã sinh.

**Tình huống B:** Hai file ở `catalog/v1/` và `order/v1/` đều khai báo `message CreateRequest`. Có thể tránh trùng tên bằng cách nào?

**Đáp án:** Đặt `package shop.catalog.v1;` và `package shop.order.v1;` tương ứng; khi tham chiếu chéo, dùng tên protobuf đủ namespace. Đồng thời đặt `java_package` khác nhau để mã Java sinh ra không va chạm.

**Tình huống C:** Một nhóm định chuyển từ `shop.catalog.v1` sang `shop.catalog.v2` mà không sửa các client đang chạy. Rủi ro chính là gì?

**Đáp án:** Tên service đầy đủ và đường dẫn RPC thay đổi, nên client gọi tên cũ có thể gặp `UNIMPLEMENTED`. Cần giữ server `v1` hoạt động hoặc có lớp tương thích trong giai đoạn chuyển client sang `v2`.

Ghi nhớ: **proto `package` xác định danh tính hợp đồng gRPC; `java_package` xác định nơi đặt code Java sinh ra; đường dẫn file xác định cách tìm và import schema.** Thiết kế cả ba nhất quán từ đầu giúp hệ thống Spring gRPC nhiều dịch vụ và nhiều ngôn ngữ phát triển ổn định hơn.
