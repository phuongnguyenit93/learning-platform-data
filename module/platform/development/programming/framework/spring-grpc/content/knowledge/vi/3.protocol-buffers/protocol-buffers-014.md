# Import proto và package namespace

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Tổ chức nhiều tệp **.proto** và import kiểu dữ liệu từ tệp khác.
- Phân biệt đường dẫn import, **package** của Protobuf và **java_package** của Java.
- Tham chiếu message/enum bằng tên trong cùng package hoặc tên đầy đủ.
- Hiểu ảnh hưởng của **java_multiple_files** và **java_outer_classname** đến mã Java được sinh.
- Cấu hình include path để **protoc** tìm đúng dependency.
- Đánh giá rủi ro khi đổi package, di chuyển tệp hoặc thay đổi tên service trong hệ thống Spring gRPC.

## 1. Vì sao cần import và namespace?

Khi hợp đồng **SPRING_GRPC** phát triển, một message có thể được dùng trong nhiều request, response hoặc service. Nếu khai báo mọi kiểu trong một tệp **.proto**, tệp đó nhanh chóng khó đọc và các nhóm khó tái sử dụng kiểu dữ liệu.

Protocol Buffers hỗ trợ chia schema thành nhiều tệp. Một tệp có thể **import** tệp khác để sử dụng các message, enum hoặc service đã khai báo. Từ khóa **package** tạo namespace cho các symbol Protobuf, tránh xung đột tên giữa những phần hợp đồng khác nhau.

Ba khái niệm cần phân biệt:

| Khái niệm | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| Đường dẫn import | **protoc** tìm tệp .proto nào | **common/address.proto** |
| **package** | Tên đầy đủ của symbol trong Protobuf | **acme.common.v1.Address** |
| **java_package** | Package Java của lớp được sinh | **com.acme.common.v1** |

Ba giá trị này có thể được tổ chức theo cùng một quy ước, nhưng chúng không phải một khái niệm và không tự động thay thế cho nhau.

## 2. Tổ chức schema thành nhiều tệp

Giả sử nhiều service cần dùng chung địa chỉ. Có thể đặt kiểu này trong một tệp riêng:

~~~proto
// common/address.proto
syntax = "proto3";

package acme.common.v1;

option java_package = "com.acme.common.v1";
option java_multiple_files = true;

message Address {
  string street = 1;
  string city = 2;
  string country_code = 3;
}
~~~

Tệp định nghĩa Customer import và sử dụng Address:

~~~proto
// customer/customer.proto
syntax = "proto3";

package acme.customer.v1;

option java_package = "com.acme.customer.v1";
option java_multiple_files = true;

import "common/address.proto";

message GetCustomerRequest {
  string customer_id = 1;
}

message Customer {
  string customer_id = 1;
  string display_name = 2;
  acme.common.v1.Address address = 3;
}

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (Customer);
}
~~~

Tệp **customer/customer.proto** có thể dùng **Address** vì đã import tệp định nghĩa kiểu đó. Import dùng **đường dẫn logic của tệp .proto**, còn **acme.common.v1.Address** là tên symbol trong namespace Protobuf.

Một quy ước thư mục thường dùng:

~~~text
src/main/proto/
  common/
    address.proto
  customer/
    customer.proto
  order/
    order.proto
~~~

Tên thư mục và package có thể được tổ chức tương ứng để dễ tìm kiếm, nhưng compiler không tự suy ra package từ thư mục. Nội dung khai báo **package** mới quyết định namespace của symbol.

## 3. Đường dẫn import và include path của protoc

Trong câu lệnh:

~~~proto
import "common/address.proto";
~~~

Đường dẫn được phân giải tương đối với một trong các **proto include root** đã truyền cho compiler. Ví dụ, nếu tệp nằm tại **src/main/proto/common/address.proto**, include root có thể là **src/main/proto**.

Lệnh minh họa:

~~~bash
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/sources/proto/main/java \
  customer/customer.proto
~~~

Chạy lệnh từ thư mục gốc dự án. Compiler lấy đường dẫn đầu vào và import tương đối với include root để tìm **customer/customer.proto** và **common/address.proto**. Nếu include root sai, tệp không được tìm thấy dù file thực tế tồn tại.

Các lưu ý:

- Đường dẫn import dùng dấu **/**, không dùng package Java.
- Import không cần và không nên dùng đường dẫn tuyệt đối gắn với một máy phát triển.
- Viết đúng chữ hoa/chữ thường của tên tệp; môi trường Linux thường phân biệt hoa thường.
- Tất cả include root cần thiết, bao gồm thư mục chứa các WKT như **google/protobuf/timestamp.proto**, phải có trong cấu hình build.
- Đường dẫn import là định danh tệp trong môi trường biên dịch; đổi vị trí tệp có thể làm hỏng import dù nội dung message không đổi.

Với Gradle hoặc Maven, plugin Protobuf thường quản lý include path và thư viện proto phụ thuộc. Điều quan trọng là cấu hình build phải cung cấp cùng một cây schema và dependency cho mọi môi trường build.

## 4. Package namespace của Protobuf

Khai báo:

~~~proto
package acme.customer.v1;
~~~

tạo namespace cho các symbol được khai báo ở cấp tệp. Tên đầy đủ của message **Customer** là:

~~~text
acme.customer.v1.Customer
~~~

Tên đầy đủ này còn được gọi là **fully qualified name**. Khi tham chiếu kiểu từ package khác, có thể dùng tên đầy đủ:

~~~proto
package acme.order.v1;

import "customer/customer.proto";

message Order {
  string order_id = 1;
  acme.customer.v1.Customer buyer = 2;
}
~~~

Có thể dùng dấu chấm đầu để chỉ rõ việc phân giải bắt đầu từ namespace gốc:

~~~proto
message Order {
  .acme.customer.v1.Customer buyer = 1;
}
~~~

Dạng có dấu chấm đầu hữu ích khi tên tương đối có thể bị hiểu nhầm do một package hoặc message lồng nhau cùng tên. Trong schema lớn, dùng tên đầy đủ tại ranh giới package giúp người đọc nhận biết dependency ngay tại field.

Nếu bỏ khai báo **package**, symbol nằm trong namespace gốc. Điều này có thể hoạt động trong schema nhỏ, nhưng dễ gây trùng tên khi nhiều tệp cùng định nghĩa **Address**, **Status** hoặc **Request**. Với API được chia sẻ, nên khai báo package có quy ước rõ ràng, thường có tên miền logic và phiên bản như **acme.customer.v1**.

## 5. Package Protobuf khác java_package

Ví dụ:

~~~proto
package acme.customer.v1;

option java_package = "com.acme.api.customer";
~~~

Hai namespace phục vụ hai mục đích khác nhau:

- **package** thuộc descriptor Protobuf, xác định tên đầy đủ của message, enum và service.
- **java_package** chỉ định nơi đặt các lớp Java được sinh.

Với cấu hình trên:

| Thành phần | Tên |
| --- | --- |
| Protobuf full name | **acme.customer.v1.Customer** |
| Java package | **com.acme.api.customer** |
| Java class với **java_multiple_files = true** | **com.acme.api.customer.Customer** |

Một message có thể giữ nguyên Protobuf package nhưng chuyển Java package để phù hợp cách tổ chức source code. Việc đó làm thay đổi import và binary API ở phía Java, nhưng không tự thay đổi tên symbol Protobuf hoặc wire format.

Ngược lại, đổi **package** Protobuf có thể tác động tới descriptor, tên kiểu đầy đủ và tên service gRPC. Không coi việc đổi package Protobuf là thao tác sắp xếp lại thư mục Java.

## 6. java_multiple_files và java_outer_classname

Java generator có các tùy chọn ảnh hưởng cách tổ chức lớp được sinh:

~~~proto
option java_package = "com.acme.customer.v1";
option java_multiple_files = true;
option java_outer_classname = "CustomerSchema";
~~~

### java_multiple_files

- Khi **false** (mặc định), các kiểu top-level thường được đặt bên trong lớp wrapper ngoài được sinh từ tên tệp .proto.
- Khi **true**, các message và enum top-level được sinh thành các lớp Java riêng trong **java_package**.
- Nested message/enum vẫn được truy cập thông qua lớp message bao ngoài, ví dụ **Customer.Address**.

Với **java_multiple_files = true**, mã Java có thể import trực tiếp:

~~~java
import com.acme.common.v1.Address;
import com.acme.customer.v1.Customer;
~~~

Nếu không bật tùy chọn này, kiểu top-level thường được tham chiếu qua wrapper class, chẳng hạn **CustomerSchema.Customer**, tùy tên lớp ngoài do generator xác định.

### java_outer_classname

Tùy chọn **java_outer_classname** đặt tên rõ ràng cho lớp wrapper ngoài của tệp. Nó hữu ích khi tên mặc định được suy ra từ tên file không phù hợp hoặc có nguy cơ xung đột với một message/enum cùng tên.

Đặt tên ổn định cho wrapper giúp tránh việc đổi tên file vô tình làm thay đổi tên lớp Java được sinh. Khi thay đổi tùy chọn này, cần xem xét các source Java đang import wrapper.

Các tùy chọn Java không đổi **package** Protobuf. Đừng dùng **java_outer_classname** để thay đổi fully qualified name của message trong descriptor.

## 7. Import dependency trực tiếp và public import

Một tệp nên import trực tiếp mọi tệp định nghĩa kiểu mà nó sử dụng. Không dựa vào việc một dependency tình cờ được import bởi tệp khác.

Ví dụ:

~~~proto
// customer/customer.proto
import "common/address.proto";

message Customer {
  acme.common.v1.Address address = 1;
}
~~~

Nếu **order.proto** dùng **Address**, **order.proto** cũng nên import **common/address.proto** trực tiếp:

~~~proto
// order/order.proto
import "common/address.proto";

message OrderDestination {
  acme.common.v1.Address address = 1;
}
~~~

### import public

**import public** cho phép một tệp tái xuất dependency để các tệp import nó có thể nhìn thấy symbol được tái xuất. Cơ chế này thường hữu ích trong một giai đoạn di chuyển schema:

~~~proto
// common/location.proto
import public "common/address.proto";

message Location {
  string code = 1;
}
~~~

Một tệp cũ chỉ import **common/location.proto** vẫn có thể tiếp tục truy cập symbol từ **address.proto** trong giai đoạn chuyển tiếp. Cách dùng này cần được tài liệu hóa và có kế hoạch loại bỏ nếu mục tiêu cuối cùng là import dependency trực tiếp.

Không dùng public import để tạo chuỗi phụ thuộc khó hiểu hoặc che giấu dependency thực. Khi một tệp dùng một kiểu, import trực tiếp thường làm hợp đồng dễ đọc và dễ bảo trì hơn.

## 8. Import WKT và thư viện schema dùng chung

Well-known types cũng được import bằng đường dẫn chuẩn:

~~~proto
syntax = "proto3";

package acme.audit.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/field_mask.proto";

message AuditRecord {
  string record_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
}

message UpdateAuditRequest {
  string record_id = 1;
  AuditRecord record = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

Các file WKT phải có trong include path của compiler. Khi build qua Gradle/Maven, dependency Protobuf thường cung cấp các file này; cần bảo đảm plugin code generation nhìn thấy đúng phiên bản.

Với schema dùng chung giữa nhiều module, nên có một nguồn định nghĩa rõ ràng cho các kiểu như **Address**, **Money** hoặc **ErrorDetail**. Tránh sao chép cùng một message vào nhiều package khác nhau: dù field trông giống nhau, chúng vẫn là hai kiểu Protobuf khác tên đầy đủ và có thể không tương thích với Any, reflection hoặc API Java.

## 9. Package và tên service ảnh hưởng đến gRPC như thế nào?

Tên package không chỉ dùng để tránh trùng message. Với service:

~~~proto
package acme.customer.v1;

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (Customer);
}
~~~

Tên đầy đủ của service là **acme.customer.v1.CustomerService**. Tên phương thức gRPC trên HTTP/2 dựa trên dạng:

~~~text
/acme.customer.v1.CustomerService/GetCustomer
~~~

Vì vậy, đổi Protobuf package có thể đổi **full service name** và đường dẫn phương thức mà client gọi. Server cũ và client mới có thể không tìm thấy cùng endpoint nếu package/service name thay đổi mà không có kế hoạch tương thích.

Tên package Java do **java_package** quy định không thay thế tên service trên wire. Đổi **java_package** chủ yếu ảnh hưởng lớp Java và source code; đổi Protobuf **package** ảnh hưởng namespace descriptor và tên service gRPC.

Khi version API, việc dùng package như **acme.customer.v1** rồi phát hành **acme.customer.v2** tạo ranh giới rõ ràng. Hai version có thể cùng tồn tại trong thời gian client di chuyển; cần quyết định cách chia sẻ message dùng chung và cách chuyển đổi dữ liệu giữa chúng.

## 10. Tiến hóa package và import an toàn

Khi schema đã được phát hành:

- Không đổi package Protobuf chỉ để đổi tên thư mục.
- Không đổi đường dẫn import mà không cập nhật mọi consumer và cấu hình include root.
- Không di chuyển message sang package mới mà giả định descriptor, Any type URL hoặc service route vẫn giữ nguyên.
- Không sao chép một message dùng chung sang package khác rồi coi hai kiểu là cùng một symbol.
- Giữ field number và wire type ổn định khi thay đổi cấu trúc message; package không thay thế các quy tắc tương thích field.

Đổi package Protobuf của message thường không làm thay byte của các field bên trong một message đơn giản nếu cấu trúc field giữ nguyên. Tuy nhiên, tên đầy đủ của kiểu thay đổi; dữ liệu đóng gói trong **google.protobuf.Any**, descriptor, reflection và các hệ thống dựa vào tên kiểu có thể bị ảnh hưởng.

Đối với service, thay package làm thay full method name như mục 9. Vì vậy, đổi package của một service đang hoạt động là thay đổi hợp đồng API cần triển khai song song hoặc có migration rõ ràng.

## 11. Ví dụ Java từ hai tệp proto

Với **common/address.proto** và **customer/customer.proto** ở mục 2, khi **java_multiple_files = true**, Java code có thể dùng trực tiếp các lớp:

~~~java
import com.acme.common.v1.Address;
import com.acme.customer.v1.Customer;

Address address = Address.newBuilder()
    .setStreet("12 Nguyen Hue")
    .setCity("Ho Chi Minh City")
    .setCountryCode("VN")
    .build();

Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setDisplayName("An")
    .setAddress(address)
    .build();
~~~

Nếu một service nhận message **Customer**, stub gRPC được sinh từ plugin gRPC Java sẽ sử dụng lớp Java tương ứng trong package được cấu hình. Cần bảo đảm cả Java message generator và gRPC plugin cùng dùng một bộ schema, include path và phiên bản Protobuf tương thích.

Khi IDE báo không tìm thấy **com.acme.common.v1.Address**, hãy kiểm tra theo thứ tự:

1. Tệp import có đúng đường dẫn và tên file không?
2. Compiler có include root chứa **common/address.proto** không?
3. **address.proto** có khai báo **java_package** như dự kiến không?
4. Code generation đã chạy và output directory có nằm trong source set chưa?
5. **java_multiple_files** có đang bật hay kiểu nằm trong wrapper class?

Đây là những nguyên nhân phổ biến hơn việc sửa package bằng cách đoán tên.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng **java_package** trong câu import | Compiler không tìm thấy file proto | Import bằng đường dẫn tương đối với include root. |
| Nghĩ thư mục quyết định package | Fully qualified name khác dự kiến | Khai báo **package** tường minh trong từng file. |
| Nhầm package Protobuf với package Java | Tham chiếu sai type hoặc đổi nhầm namespace | Kiểm tra riêng **package** và **java_package**. |
| Không import trực tiếp kiểu đang dùng | Build phụ thuộc vào import gián tiếp | Import file định nghĩa kiểu trực tiếp. |
| Đổi tên file mà không kiểm tra outer class | Java wrapper class có thể đổi tên | Đặt **java_outer_classname** ổn định nếu cần. |
| Đổi Protobuf package của service đang chạy | Client gọi sai full method name | Version/migrate service có kế hoạch. |
| Tạo bản sao message dùng chung trong package khác | Hai kiểu có tên đầy đủ khác nhau | Import và tái sử dụng một định nghĩa chuẩn. |
| Include path khác nhau giữa local và CI | Build chỉ lỗi ở một môi trường | Chuẩn hóa cấu hình proto path trong build. |

## 13. Bài tập thực hành

Tạo ba tệp:

~~~text
src/main/proto/
  common/address.proto
  customer/customer.proto
  order/order.proto
~~~

Yêu cầu:

1. Khai báo **Address** trong package **acme.common.v1**, Java package **com.acme.common.v1**.
2. Khai báo **Customer** trong package **acme.customer.v1**, import **common/address.proto** và dùng field **acme.common.v1.Address**.
3. Khai báo **Order** trong package **acme.order.v1**, import trực tiếp cả **common/address.proto** và **customer/customer.proto**.
4. Bật **java_multiple_files = true**; xác định tên Java class và import tương ứng.
5. Thử đổi **java_package** nhưng giữ nguyên Protobuf **package**; mô tả điều gì đổi trong Java và điều gì không đổi trong descriptor Protobuf.
6. Thử đổi Protobuf package của **CustomerService**; xác định full method name gRPC trước và sau thay đổi.
7. Chạy **protoc** với include root là **src/main/proto**, sau đó cố ý thay include root để quan sát lỗi không tìm thấy import.

**Tiêu chí hoàn thành:** phân biệt chính xác import path, Protobuf package và Java package; tham chiếu được kiểu dùng chung; giải thích được tác động của namespace đến Java API, descriptor và gRPC service route.

## 14. Ghi nhớ

- **Import path** xác định tệp .proto; nó được phân giải tương đối với include root của compiler.
- **package** xác định namespace Protobuf và tên đầy đủ của message, enum, service.
- **java_package** chỉ định package Java được sinh; không thay đổi Protobuf package.
- **java_multiple_files** và **java_outer_classname** điều khiển cách tổ chức mã Java, không đổi wire schema.
- Import trực tiếp dependency mà tệp đang sử dụng; chỉ dùng **import public** khi cần tái xuất có chủ đích.
- Đổi Protobuf package có thể ảnh hưởng descriptor, Any type URL và full method name gRPC; đổi Java package ảnh hưởng source/API Java.

Tổ chức import proto và package namespace rõ ràng giúp hợp đồng Protobuf có thể tái sử dụng giữa nhiều service, giúp code Java được sinh nhất quán và giảm rủi ro khi Spring gRPC phát triển qua nhiều phiên bản.
