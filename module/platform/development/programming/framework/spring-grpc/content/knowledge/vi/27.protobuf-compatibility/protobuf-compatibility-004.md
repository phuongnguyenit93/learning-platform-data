# Đổi tên field và wire compatibility

## 1. Đổi tên field có làm thay đổi dữ liệu trên wire không?

Trong **SPRING_GRPC**, Protobuf schema được dùng để sinh Java message, client stub và các API phục vụ giao tiếp giữa service. Khi cần đổi tên một field cho dễ hiểu hơn, câu hỏi quan trọng là thay đổi đó có làm client/server đang chạy các phiên bản khác nhau không thể trao đổi binary message hay không.

Với **binary Protobuf**, tên field không được ghi vào tag trên wire. Tag được tạo từ field number và wire type. Vì vậy, nếu chỉ đổi tên field nhưng giữ nguyên field number, kiểu dữ liệu và semantics mã hóa, payload binary vẫn có thể được đọc bởi client/server dùng schema trước đó.

Tuy nhiên, đổi tên vẫn có thể phá vỡ những bề mặt khác:

- Generated Java API đổi tên getter, setter, builder method và constant.
- Protobuf JSON mặc định dùng tên field được chuyển sang lowerCamelCase.
- Descriptor/reflection và các công cụ dựa trên tên field thấy identifier mới.
- FieldMask path, TextFormat, mapping, validation rule và tài liệu API có thể tham chiếu tên cũ.

Do đó cần phân biệt **binary wire compatibility** với **source/API compatibility và JSON compatibility**. Bài này tập trung vào cách đổi tên có kiểm soát, giữ wire format và nhận diện các hợp đồng phụ thuộc vào tên.

## 2. Vì sao binary Protobuf không phụ thuộc tên field?

Trong binary encoding, mỗi field được ghi bằng tag:

```text
tag = (field_number << 3) | wire_type
```

Ví dụ schema cũ:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message Product {
  string sku = 1;
  string display_name = 2;
  int64 price_cents = 3;
}
```

Schema mới đổi `display_name` thành `label`, nhưng giữ nguyên number và kiểu:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message Product {
  string sku = 1;
  string label = 2;
  int64 price_cents = 3;
}
```

Trong cả hai schema, field number 2 có wire type length-delimited vì là `string`. Payload của field 2 vẫn có cùng tag và cách mã hóa. Client v1 có thể parse payload do server v2 tạo và đọc giá trị bằng `getDisplayName()`; client v2 có thể parse payload do server v1 tạo và đọc cùng bytes bằng `getLabel()`.

Điều kiện để kết luận này đúng:

- Giữ nguyên field number.
- Giữ nguyên kiểu và quy tắc mã hóa của field.
- Giữ nguyên cardinality, presence semantics và ý nghĩa dữ liệu.
- Không thay đổi message/package/service wire identity theo cách khác.
- Không thay đổi các field khác trong cùng đợt mà ảnh hưởng tương thích.

Đổi tên field đơn thuần không đổi tag. Nếu đồng thời đổi `string` thành kiểu khác, đổi repeated/optional, thay đổi `oneof` hoặc đổi semantics, cần đánh giá từng thay đổi riêng. Không dùng kết luận “rename không đổi wire” để hợp thức hóa một thay đổi schema lớn hơn.

## 3. Ví dụ client cũ và server mới

Giả sử client v1 được sinh từ schema có field `display_name`. Code Java cũ:

```java
Product product = catalogStub.getProduct(
    GetProductRequest.newBuilder()
        .setSku("SKU-100")
        .build()
);

String displayName = product.getDisplayName();
```

Server v2 được sinh từ schema có field `label`:

```java
Product product = Product.newBuilder()
    .setSku("SKU-100")
    .setLabel("Wireless keyboard")
    .setPriceCents(4900)
    .build();

responseObserver.onNext(product);
responseObserver.onCompleted();
```

Vì field 2 vẫn là `string`, client v1 parse được response và `getDisplayName()` nhận `"Wireless keyboard"`. Tương tự, server v2 có thể parse request/message do client v1 tạo nếu những field liên quan giữ nguyên wire contract.

Đây là tương thích ở **binary serialization layer**. Client v1 không cần sinh lại code chỉ để parse message có field được đổi tên, nhưng source code của client v1 cũng không thể gọi `getLabel()` vì generated API cũ không có method đó.

Trong test, hai phiên bản generated class thường có cùng fully qualified Java class name nếu cùng `java_package` và message name. Để chạy đồng thời trong một test suite, có thể đặt fixture cũ và mới ở hai module/package Java riêng hoặc dùng artifact/classloader riêng; giữ nguyên Protobuf `package` và field number để wire identity được kiểm tra đúng.

## 4. Generated Java API vẫn là source breaking change

Protobuf compiler sinh Java method dựa trên tên field. Đổi:

```proto
string display_name = 2;
```

thành:

```proto
string label = 2;
```

sẽ làm generated API đổi từ các method như:

- `getDisplayName()`
- `setDisplayName(...)`
- `clearDisplayName()`
- `hasDisplayName()` nếu field có presence

sang các method tương ứng với `Label`.

Các module compile trực tiếp với generated source mới phải cập nhật import usage và method calls. Vì vậy, thay đổi có thể **wire-compatible nhưng không source-compatible**.

Điều này quan trọng khi phát hành một contract JAR dùng chung:

- Ứng dụng chưa nâng version JAR vẫn compile với API cũ.
- Ứng dụng nâng JAR phải đổi code gọi getter/setter.
- Không nên phát hành contract artifact mới mà không thông báo generated API đã đổi.
- Nếu nhiều team dùng contract, cần versioning và migration guide cho source code.

Tên Java generated có thể thay đổi dù binary payload vẫn tương thích. Hai khái niệm này cần được đánh giá độc lập trong review.

## 5. Protobuf JSON có thể bị breaking khi đổi tên

Binary tag không chứa tên field, nhưng Protobuf JSON sử dụng tên field. Theo mapping mặc định, tên snake_case trong `.proto` được chuyển thành lowerCamelCase khi serialize JSON.

Ví dụ field cũ:

```proto
message Product {
  string display_name = 2;
}
```

JSON thường được serialize:

```json
{
  "displayName": "Wireless keyboard"
}
```

Sau khi đổi tên thành `label`, JSON mặc định có thể trở thành:

```json
{
  "label": "Wireless keyboard"
}
```

Một REST consumer, gateway, frontend hoặc JSON fixture đang chờ `displayName` có thể bị ảnh hưởng, dù binary gRPC client vẫn parse được.

### Giữ JSON key cũ bằng json_name

Nếu cần đổi tên field trong `.proto` nhưng vẫn giữ tên JSON được phát hành, có thể khai báo `json_name` tường minh:

```proto
message Product {
  string label = 2 [json_name = "displayName"];
}
```

Khi dùng Protobuf JSON printer chuẩn, field vẫn được xuất với key `displayName`. JSON parser cũng nhận tên JSON được cấu hình theo quy tắc của Protobuf JSON mapping. Cần test với parser/gateway thực tế, đặc biệt nếu hệ thống dùng custom transcoding hoặc serializer không phải Protobuf JSON chuẩn.

`json_name` chỉ điều khiển tên JSON; nó không khôi phục generated Java method `getDisplayName()` và không đổi tên field trong descriptor. Nó cũng không làm cho một REST consumer tùy chỉnh tự động hỗ trợ mọi alias cũ/mới.

Nếu API trước đây bật chế độ giữ nguyên proto field name thay vì lowerCamelCase, hãy kiểm tra chính xác JSON key đã phát hành và giữ key đó bằng cấu hình phù hợp. Không giả định key JSON cũ luôn là lowerCamelCase.

## 6. Reserve tên cũ sau khi đổi tên

Sau khi đổi field identifier, nên reserve tên cũ để ngăn một field khác vô tình dùng lại tên đó trong tương lai. Field mới vẫn giữ number 2, còn tên cũ được reserve:

```proto
message Product {
  string sku = 1;
  string label = 2;
  int64 price_cents = 3;

  reserved "display_name";
}
```

Đây là trường hợp hợp lệ: `label` đang dùng number 2; tên `display_name` được giữ lại để không thể gán cho một field khác sau này.

Không reserve number 2 trong ví dụ này, vì number 2 vẫn thuộc field `label`. Chỉ reserve number khi field number đó đã bị loại bỏ hoàn toàn khỏi message. Quy tắc cần nhớ:

| Thay đổi | Reservation phù hợp |
| --- | --- |
| Đổi tên field, giữ number | Reserve tên cũ |
| Xóa field, không thay thế | Reserve number và tên cũ |
| Xóa enum value | Reserve enum number và tên |
| Xóa member `oneof` | Reserve number và tên ở cấp message |

Reservation tên cũ bảo vệ schema source. Nó không giữ lại generated API cũ và cũng không tự giữ JSON key cũ; muốn giữ JSON contract, dùng `json_name` và test riêng.

## 7. Những hợp đồng khác dựa vào field name

Ngoài binary và generated Java API, field name có thể được dùng ở nhiều nơi:

| Thành phần | Tác động của rename | Việc cần làm |
| --- | --- | --- |
| Protobuf descriptor/reflection | `FieldDescriptor.getName()` trả tên mới | Cập nhật code tra cứu theo tên |
| Protobuf JSON | Default JSON key có thể đổi | Dùng `json_name` nếu cần giữ key |
| FieldMask | Path tham chiếu field name | Cập nhật path và kiểm thử mapping |
| TextFormat/TextProto | Tên field trong text representation đổi | Cập nhật fixture/config text |
| Gateway/OpenAPI | Tên property có thể đổi | Regenerate spec và kiểm tra consumer |
| Validation/mapping rule | Rule có thể tham chiếu tên field | Cập nhật annotation/config theo codegen |
| Log, metric, audit mapping | Label/tag có thể dựa trên descriptor name | Đánh giá dashboard và truy vấn |

### FieldMask cần chú ý

FieldMask biểu diễn danh sách đường dẫn field cần đọc/cập nhật. Nếu client gửi path `display_name` nhưng server mới chỉ nhận diện `label`, logic xử lý FieldMask dựa trên tên có thể không còn khớp.

Nếu API có FieldMask public, phải có kế hoạch chuyển đổi path cũ sang path mới trong giai đoạn tương thích, hoặc giữ một adapter chấp nhận cả hai cách gọi. Không nên giả định binary message chứa FieldMask sẽ tự ánh xạ tên cũ sang tên mới.

## 8. Đổi tên field trong oneof

Đổi tên một member trong `oneof` cũng không thay đổi binary tag nếu giữ nguyên number và kiểu. Tuy nhiên, generated Java API của oneof sẽ đổi tên method và case enum tương ứng.

Ví dụ:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }
}
```

Nếu đổi `card_token` thành `card_credential` nhưng giữ number 1:

```proto
message PaymentMethod {
  oneof method {
    string card_credential = 1;
    string bank_account = 2;
  }

  reserved "card_token";
}
```

Binary client cũ và mới vẫn có thể đọc tag 1 theo cùng wire encoding. Tuy nhiên, Java API cũ có `getCardToken()` và `METHOD` case cũ; generated API mới có tên tương ứng `CardCredential`. Code reflection, JSON mapping và validation cũng cần cập nhật.

Nếu field trong oneof bị xóa hoàn toàn thay vì đổi tên, reserve cả number và tên tại cấp message. Nếu chỉ đổi tên và giữ field number, reserve tên cũ nhưng không reserve number đang tiếp tục được dùng.

## 9. Quy trình đổi tên an toàn

Trước khi đổi tên field trong contract đã phát hành:

1. **Xác định tất cả consumer:** client Java, service khác ngôn ngữ, gateway, JSON/REST, FieldMask, reflection và dữ liệu text.
2. **Giữ nguyên wire identity:** không đổi field number, type, cardinality, presence hoặc semantics.
3. **Đổi identifier trong `.proto`:** cập nhật tên mới và reserve tên cũ.
4. **Giữ JSON key nếu cần:** đặt `json_name` bằng key JSON đã công bố trước đó.
5. **Sinh lại generated code:** compile các module sử dụng contract mới và cập nhật getter/setter.
6. **Kiểm tra consumer không nâng cấp:** dùng generated client cũ để parse binary message từ server mới và ngược lại.
7. **Kiểm thử JSON/FieldMask:** xác nhận key và path được xử lý theo chính sách tương thích.
8. **Phát hành có kiểm soát:** thông báo source API change, nâng contract artifact và cập nhật consumer theo kế hoạch.
9. **Quan sát sau rollout:** theo dõi parse errors, JSON mapping errors và lỗi do path/name không còn khớp.

Nếu mục tiêu chỉ là cải thiện tên trong code nội bộ, cân nhắc giữ nguyên field name trong `.proto` và tạo adapter/domain property có tên mong muốn. Cách đó tránh thay đổi generated API và JSON contract công khai.

## 10. Kiểm thử wire compatibility giữa schema cũ và mới

Không chỉ compile schema mới. Cần giữ generated type từ hai phiên bản và kiểm tra bytes thực tế:

- Tạo message bằng generated class v1, serialize rồi parse bằng generated class v2.
- Tạo message bằng generated class v2, serialize rồi parse bằng generated class v1.
- Assert field number tương ứng vẫn mang cùng dữ liệu.
- Kiểm tra JSON printer/parser với key đã phát hành.
- Kiểm tra FieldMask và descriptor-based mapping nếu ứng dụng sử dụng.
- Chạy integration test qua gRPC server/client để xác nhận service path và serialization end-to-end.

Ví dụ ở cấp binary message:

```java
// ProductV1 có getDisplayName(); ProductV2 có getLabel().
// Hai generated type được build trong fixture/module riêng.

ProductV1 oldMessage = ProductV1.newBuilder()
    .setSku("SKU-100")
    .setDisplayName("Wireless keyboard")
    .build();

byte[] bytes = oldMessage.toByteArray();

ProductV2 newMessage = ProductV2.parseFrom(bytes);

assertEquals("SKU-100", newMessage.getSku());
assertEquals("Wireless keyboard", newMessage.getLabel());
```

Test chiều ngược lại cũng cần có: tạo `ProductV2` với `label`, serialize, rồi parse bằng `ProductV1` và assert `getDisplayName()` nhận đúng giá trị. Hai schema phải giữ cùng Protobuf package, message name, field number và wire type để kiểm tra đúng wire identity; có thể tách Java package/module fixture để tránh trùng class trong test.

Nếu dùng schema compatibility tool, chọn rule set phù hợp. Một rename có thể không bị xem là binary wire breaking nhưng vẫn bị phát hiện ở nhóm source/JSON compatibility. Hãy đọc loại breaking change mà công cụ báo, không chỉ dựa vào một kết quả pass/fail tổng quát.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client Java không compile sau khi nâng contract JAR | Getter/setter đã đổi theo tên field mới | Cập nhật source hoặc giữ contract version cũ trong giai đoạn chuyển tiếp |
| gRPC binary vẫn chạy nhưng REST client lỗi | JSON key mặc định đổi | Giữ `json_name` hoặc version hóa JSON API |
| Reflection lookup không tìm thấy field | Descriptor name đã đổi | Cập nhật lookup và rule dựa trên descriptor |
| FieldMask không cập nhật field | Path vẫn dùng tên cũ | Adapter path cũ/mới và test |
| Schema checker báo breaking change | Rule set kiểm tra source/JSON name | Xác định compatibility target và ghi nhận chủ đích |
| Payload cũ parse sai | Field number/type đã bị thay đổi cùng lúc rename | Khôi phục wire identity và tách thay đổi |
| Người khác tạo field trùng tên cũ | Tên cũ chưa được reserve | Thêm `reserved "old_name";` |
| Oneof generated API đổi case | Member name đã đổi | Cập nhật code và test oneof case |

## 12. Checklist review

- Field number được giữ nguyên.
- Kiểu dữ liệu và wire encoding không đổi.
- Cardinality, presence và semantics không đổi.
- Tên cũ được reserve nếu field identifier đã đổi.
- Không reserve number đang tiếp tục được dùng bởi field mới.
- JSON key đã được giữ bằng `json_name` nếu API yêu cầu.
- Generated Java consumers đã được cập nhật hoặc có kế hoạch versioning.
- FieldMask, reflection, TextFormat, gateway và validation rules đã được rà soát.
- Có test hai chiều giữa generated schema cũ và mới.
- Schema compatibility checker được chạy với rule set phù hợp.

Với **SPRING_GRPC**, đổi tên field có thể giữ nguyên binary wire compatibility khi field number, kiểu và semantics được giữ nguyên. Nhưng generated Java API, JSON mapping và các hợp đồng dựa trên tên vẫn có thể thay đổi. Review phải đánh giá riêng từng bề mặt, dùng `reserved` cho identifier cũ và kiểm thử bằng generated code của phiên bản đã phát hành.
