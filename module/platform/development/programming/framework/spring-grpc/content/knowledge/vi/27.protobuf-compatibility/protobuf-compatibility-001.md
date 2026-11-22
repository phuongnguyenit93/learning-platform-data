# Thêm field mới mà client cũ vẫn đọc được

## 1. Bài toán tương thích khi mở rộng Protobuf

Trong hệ **SPRING_GRPC**, client và server có thể được build, triển khai và nâng cấp ở những thời điểm khác nhau. Một server mới có thể chạy cùng client cũ trong một khoảng thời gian; nhiều replica cũng có thể chưa đồng thời chuyển sang cùng phiên bản. Vì vậy, mở rộng hợp đồng Protocol Buffers phải giữ cho message mới vẫn được client cũ phân tích đúng.

Một thay đổi phổ biến là **thêm field mới vào message**. Nếu field mới dùng một field number chưa từng được sử dụng, client cũ có thể đọc các field mà nó biết và bỏ qua field chưa biết. Đây là nền tảng của khả năng tương thích nhị phân khi tiến hóa schema Protobuf.

Bài này tập trung vào:

- Vì sao field number và wire type quyết định cách Protobuf đọc message.
- Cách thêm field vào response để client cũ tiếp tục đọc field hiện có.
- Giá trị mặc định và field presence của client mới khi gặp server cũ.
- Khác biệt khi thêm field vào request và response.
- Những thay đổi tưởng như tương thích nhưng có thể làm sai ý nghĩa dữ liệu.
- Thứ tự rollout, kiểm thử với generated client cũ và các giới hạn khi đi qua JSON/API gateway.

## 2. Field number là định danh trên wire

Protobuf không gửi tên field trong binary message. Mỗi field được mã hóa bằng một tag chứa **field number** và **wire type**. Tên như `product_name` chủ yếu phục vụ source code, descriptor và JSON mapping; field number mới là định danh dùng để giải mã binary payload.

Ví dụ schema ban đầu:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message ProductReply {
  string sku = 1;
  string name = 2;
}
```

Giả sử phiên bản mới cần bổ sung loại sản phẩm:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message ProductReply {
  string sku = 1;
  string name = 2;
  string category = 3;
}
```

Field `category = 3` có field number mới. Client cũ được sinh từ schema đầu tiên chỉ biết field 1 và 2. Khi parse binary payload của server mới:

1. Client nhận tag của field 1 và đọc `sku`.
2. Client nhận tag của field 2 và đọc `name`.
3. Client gặp tag field 3 mà generated code cũ không định nghĩa.
4. Protobuf runtime nhận diện đây là unknown field và bỏ qua giá trị đó khi tạo object theo schema cũ.

Kết quả: client cũ vẫn đọc được `sku` và `name`; nó không thể truy cập `category` bằng API generated cũ, nhưng field mới không làm sai vị trí của các field hiện có.

**Không thêm field bằng cách tái sử dụng một number đã dùng trước đây.** Field number là một phần của wire contract và phải được quản lý lâu dài.

## 3. Unknown fields được xử lý như thế nào?

Một message được parse bởi schema cũ có thể chứa field mà schema đó chưa biết. Protobuf gọi chúng là **unknown fields**.

Với binary Protobuf, generated runtime thường có khả năng bỏ qua unknown field để tiếp tục đọc các field đã biết. Trong Java Protobuf, unknown fields thường được giữ trong phần dữ liệu unknown của message và có thể được serialize lại. Tuy nhiên, ứng dụng không nên mặc định rằng unknown field luôn sống sót qua mọi bước xử lý.

Unknown field có thể bị mất nếu ứng dụng:

- Chuyển message Protobuf thành DTO khác rồi tạo lại message mới chỉ từ các field đã biết.
- Chuyển qua JSON hoặc một định dạng trung gian không giữ unknown field.
- Dùng mapper thủ công chỉ copy những property hiện diện trong model cũ.
- Tạo message mới từ builder thay vì serialize lại message đã parse.

Vì vậy, nếu một thành phần đóng vai trò proxy và phải forward nguyên vẹn các field mà nó chưa hiểu, hãy kiểm tra hành vi parse/serialize của đúng Protobuf runtime và toàn bộ đường đi. **Khả năng client cũ đọc được field cũ không đồng nghĩa mọi intermediary đều bảo toàn field mới.**

## 4. Client cũ đọc response từ server mới

Đây là trường hợp trực tiếp nhất của đề bài. Server mới trả thêm một field trong response; client cũ chỉ đọc các field có trong schema mà nó đã biên dịch.

Giả sử server v2 trả:

```json
{
  "sku": "SKU-100",
  "name": "Wireless keyboard",
  "category": "ACCESSORY"
}
```

Trên wire, payload là binary Protobuf chứ không phải JSON ở trên. JSON chỉ giúp hình dung nội dung. Client v1 được sinh từ schema không có `category` sẽ parse hai field quen thuộc và bỏ qua field số 3.

Ví dụ code client cũ:

```java
ProductReply reply = catalogStub.getProduct(
    ProductRequest.newBuilder()
        .setSku("SKU-100")
        .build()
);

String sku = reply.getSku();
String name = reply.getName();

// Generated client v1 không có getCategory().
System.out.println(sku + " - " + name);
```

Client cũ không cần thay đổi source hoặc sinh lại code để tiếp tục đọc hai field hiện có, miễn là server giữ nguyên semantics và field number của chúng.

Điều này cũng có nghĩa client cũ **không thể sử dụng tính năng mới** dựa trên `category`. Nếu ứng dụng yêu cầu category để quyết định nghiệp vụ, cần có fallback tương thích hoặc triển khai client mới trước khi bắt buộc dữ liệu đó.

## 5. Thêm field vào request và response có chiều tương thích khác nhau

Thêm field vào cả request và response đều có thể tương thích ở mức binary nếu dùng field number mới, nhưng hành vi giữa phiên bản cũ và mới khác nhau:

| Kết hợp phiên bản | Điều xảy ra với field mới |
| --- | --- |
| Client cũ → server mới, field mới nằm trong request | Client không gửi field; server mới nhận giá trị mặc định/không có presence |
| Client mới → server cũ, field mới nằm trong request | Server cũ không biết field và bỏ qua nó |
| Server mới → client cũ, field mới nằm trong response | Client cũ bỏ qua unknown field và đọc các field cũ |
| Server cũ → client mới, field mới nằm trong response | Client mới không nhận field; getter trả giá trị mặc định hoặc báo absent tùy loại field |

Do đó, “wire-compatible” không đồng nghĩa “tính năng mới hoạt động với mọi tổ hợp phiên bản”.

Ví dụ, client mới gửi `include_stock=true` trong request nhưng server cũ bỏ qua field đó. RPC vẫn có thể parse thành công, nhưng server cũ không thực hiện yêu cầu include stock. Nếu client phụ thuộc vào hành vi đó, cần kiểm tra khả năng server hỗ trợ trước khi bật tính năng.

Khi thêm field vào response, server cũ chưa biết field mới nên không thể trả nó. Client mới phải xử lý trường hợp field absent/default cho đến khi mọi server cần thiết đã được nâng cấp.

## 6. Giá trị mặc định và field presence trong proto3

Khi client mới nhận message từ server cũ, field mới không xuất hiện trên wire. Cách client quan sát trường đó phụ thuộc kiểu field và quy tắc presence.

### 6.1. Scalar không khai báo optional

Với proto3 implicit presence, scalar field như `string`, `bool`, `int32` có giá trị mặc định khi không xuất hiện:

| Kiểu | Giá trị getter mặc định |
| --- | --- |
| `string` | Chuỗi rỗng |
| `bool` | `false` |
| `int32`, `int64` | `0` |
| `float`, `double` | `0.0` |
| enum | Giá trị enum đầu tiên có number 0 |

Ví dụ:

```proto
message ProductReply {
  string sku = 1;
  string category = 3;
  bool discontinued = 4;
}
```

Nếu server cũ chỉ gửi `sku`, client mới nhận `getCategory()` là chuỗi rỗng và `getDiscontinued()` là `false`. Ứng dụng cần xem các giá trị đó là fallback hợp lệ, không diễn giải chúng thành dữ liệu mà server cũ đã chủ động gửi.

### 6.2. Dùng optional khi cần phân biệt absent với default

Nếu cần phân biệt “server không cung cấp field” với “server chủ động cung cấp chuỗi rỗng”, khai báo `optional`:

```proto
message ProductReply {
  string sku = 1;
  optional string category = 3;
}
```

Generated Java API hỗ trợ kiểm tra presence, ví dụ:

```java
if (reply.hasCategory()) {
    useCategory(reply.getCategory());
} else {
    useLegacyCategoryFallback();
}
```

Với scalar proto3 implicit presence, không thể phân biệt rõ field vắng mặt với field được gửi bằng giá trị mặc định chỉ qua getter. `optional` bổ sung presence tracking. Với message fields, repeated fields và map fields, quy tắc presence/default có khác biệt; cần đọc API generated tương ứng thay vì giả định tất cả đều có `hasX()`.

Nếu field mới ảnh hưởng tới quyết định nghiệp vụ, hãy thiết kế rõ semantics của absent, empty và default trước khi phát hành.

## 7. Quy tắc để field mới thực sự tương thích

Khi thêm field, cần giữ các nguyên tắc sau:

1. **Chọn field number chưa từng sử dụng.** Không lấy number của field đã xóa hoặc đổi tên.
2. **Giữ nguyên field number và ý nghĩa của field cũ.** Không đổi nghĩa dữ liệu trong khi giữ nguyên tag.
3. **Chọn kiểu dữ liệu phù hợp.** Một số kiểu có cùng wire type nhưng khác cách diễn giải; không đổi kiểu chỉ vì parser có thể đọc được byte.
4. **Để giá trị mặc định có ý nghĩa an toàn.** Client/server cũ không gửi field mới; phiên bản mới phải xử lý tình huống đó.
5. **Không thêm proto2 `required` field.** Sender cũ không gửi field mới và message có thể không hợp lệ theo yêu cầu initialization.
6. **Đảm bảo client cũ bỏ qua field mà vẫn xử lý đúng các field cũ.** Không thay đổi semantics hiện có phụ thuộc vào field mới.
7. **Kiểm thử đường đi qua intermediary.** Proxy hoặc adapter có thể parse rồi dựng lại message và làm mất unknown field.

Field number 1 đến 15 thường có encoding tag ngắn hơn, nên phù hợp cho field có tần suất xuất hiện cao khi thiết kế schema ban đầu. Khi thêm field vào schema đã phát hành, ưu tiên quan trọng hơn là dùng một number mới, hợp lệ và chưa từng được sử dụng; không thay đổi number cũ chỉ để tối ưu kích thước.

## 8. Xóa field cũ và reserved number

Khi một field không còn được dùng, không xóa rồi dùng lại number đó cho field mới. Một binary payload cũ vẫn có thể chứa tag đó; client/server phiên bản khác có thể hiểu tag theo nghĩa cũ và diễn giải dữ liệu sai.

Ví dụ, nếu field number 2 và tên `legacy_name` đã bị loại bỏ:

```proto
message ProductReply {
  string sku = 1;

  reserved 2;
  reserved "legacy_name";

  string category = 3;
}
```

`reserved` giúp compiler phát hiện nếu ai đó vô tình tái sử dụng number hoặc tên đã loại bỏ. Nên reserve cả number và tên khi xóa field khỏi schema dùng chung.

Đổi tên field nhưng giữ nguyên number thường tương thích với binary wire format, vì tên không được gửi trong binary tag. Tuy nhiên, đổi tên có thể phá JSON field name, generated API của Java, client dùng reflection hoặc tài liệu hợp đồng. Vì vậy, không nên xem đổi tên là thay đổi không ảnh hưởng.

## 9. Những trường hợp thêm field có thể gây vấn đề

### 9.1. Đổi kiểu nhưng giữ number

Không đổi kiểu field hiện có chỉ vì hai kiểu có cùng wire type. Ví dụ `int32` và `sint32` đều dùng varint nhưng `sint32` áp dụng zig-zag encoding; dữ liệu có thể được parse thành số khác. `string` và `bytes` đều length-delimited nhưng ý nghĩa và validation khác nhau.

Đổi `int32` thành `int64` có thể giữ wire type nhưng client cũ không biểu diễn được toàn bộ miền giá trị mới. Wire parser chấp nhận byte không có nghĩa dữ liệu giữ nguyên semantics.

### 9.2. Thêm member vào oneof

Client cũ không biết một member mới của `oneof` có thể coi tag đó là unknown và không thấy lựa chọn nào được set qua API oneof cũ. Điều này có thể làm client xử lý như trường hợp “không có lựa chọn”, dù server mới thực tế đã gửi một lựa chọn mới.

Nếu client cũ phải hiểu mọi lựa chọn, không thêm member mới rồi kỳ vọng chúng tự động có fallback đúng. Cần thiết kế hành vi unknown/default rõ ràng.

### 9.3. Thêm enum value

Với proto3, thêm enum value có thể tương thích ở mức wire, nhưng client cũ có thể nhận numeric value chưa biết. Trong Java generated enum, trường hợp này có thể biểu diễn qua `UNRECOGNIZED`; code cần tránh gọi `getNumber()` trên sentinel đó và có thể dùng getter số nguyên tương ứng để xử lý giá trị chưa biết.

Nếu code cũ có `switch` hoặc logic mặc định giả định enum chỉ có các giá trị đã biết, thêm enum value có thể gây lỗi nghiệp vụ dù message vẫn parse được.

### 9.4. JSON transcoding và API bên ngoài

Binary Protobuf và JSON mapping không có cùng hành vi unknown-field trong mọi parser/gateway. Một JSON consumer strict, schema validator hoặc API gateway có thể từ chối field mới dù gRPC binary client cũ vẫn đọc được response. Khi gRPC được chuyển thành JSON/REST, phải kiểm tra cấu hình parser và hợp đồng công khai riêng.

## 10. Thứ tự rollout an toàn

Giả sử muốn thêm `category` vào response của `Catalog.GetProduct`:

1. **Phát hành schema mới:** thêm field number mới, giữ nguyên các field cũ và generated package/service.
2. **Nâng server:** server mới có thể trả `category`; server vẫn phải trả đầy đủ các field cũ với semantics cũ.
3. **Kiểm thử client cũ:** dùng generated client v1 gọi server v2 và xác nhận `sku`, `name` vẫn đọc đúng.
4. **Nâng client mới:** client mới có thể đọc `category`, nhưng phải xử lý absent/default khi gặp server cũ.
5. **Bật logic phụ thuộc field mới:** chỉ bật khi backend đã cung cấp dữ liệu hoặc có cơ chế capability/rollout phù hợp.
6. **Quan sát:** theo dõi lỗi parse, status RPC, tỷ lệ field absent và khác biệt giữa các replica trong thời gian chuyển phiên bản.

Nếu client mới bắt buộc cần giá trị `category`, hãy triển khai server hỗ trợ trước và xác minh toàn bộ endpoint phía sau load balancer đã nâng cấp. Trong rolling deployment, một channel có thể gặp server v1 và v2 trong cùng thời gian; client phải hoạt động đúng với cả hai.

Không dùng version string của ứng dụng làm bằng chứng duy nhất rằng field đã có. Nếu tính năng phụ thuộc khả năng server, có thể dùng capability RPC, metadata có phiên bản hoặc một feature flag được kiểm soát.

## 11. Kiểm thử tương thích bằng generated client cũ

Kiểm thử quan trọng nhất cho yêu cầu này là **dùng code được sinh từ schema cũ để parse response do server mới tạo**. Chỉ compile client mới với schema mới không kiểm tra được khả năng tương thích của client cũ.

Có thể tổ chức test theo các bước:

- Giữ fixture hoặc test module chứa generated Java từ schema v1.
- Dùng schema v2 để tạo response có thêm field.
- Serialize response v2 thành binary bytes.
- Parse bytes bằng generated class v1.
- Assert những field cũ vẫn có đúng giá trị.
- Nếu cần kiểm tra proxy, parse rồi serialize lại bằng client v1 và xác minh unknown field có được giữ theo runtime/đường đi mong muốn hay không.

Ví dụ minh họa kiểm tra ở cấp message:

```java
// ProductReplyV2 là generated type từ schema mới.
ProductReplyV2 replyV2 = ProductReplyV2.newBuilder()
    .setSku("SKU-100")
    .setName("Wireless keyboard")
    .setCategory("ACCESSORY")
    .build();

byte[] payload = replyV2.toByteArray();

// ProductReplyV1 là generated type được giữ từ schema cũ.
ProductReplyV1 replyV1 = ProductReplyV1.parseFrom(payload);

assertEquals("SKU-100", replyV1.getSku());
assertEquals("Wireless keyboard", replyV1.getName());
// Schema v1 không có getCategory(); field 3 là unknown với client v1.
```

Tên class `ProductReplyV1` và `ProductReplyV2` ở đây là tên minh họa. Trong thực tế, để tránh hai schema sinh cùng fully qualified class name, đặt generated code vào hai test module/package khác nhau hoặc dùng artifact fixture riêng. Không sửa package wire `catalog.v1` chỉ để giải quyết trùng class trong test mà không đánh giá tác động hợp đồng.

Ngoài message-level test, nên có integration test gọi RPC thật bằng client v1 tới server v2. Test đó xác minh cả serialization, transport, service registration và behavior của generated stub.

## 12. Checklist trước khi phát hành schema mới

- Field mới dùng number chưa từng được dùng và không nằm trong vùng reserved.
- Các field hiện có giữ nguyên number, type và semantics.
- Field mới có default/presence behavior rõ ràng khi server hoặc client chưa nâng cấp.
- Client cũ đọc response mới mà không lỗi và vẫn xử lý đúng field cũ.
- Server cũ bỏ qua field mới trong request mà không làm sai nghiệp vụ hiện có.
- Client mới có fallback khi server cũ chưa trả field mới.
- Không dựa vào unknown-field preservation nếu message đi qua JSON hoặc được map sang DTO khác.
- Enum/oneof và JSON transcoding đã được xem xét nếu schema có các cấu trúc đó.
- CI có test với generated code từ schema cũ.
- Rolling deployment đã được kiểm thử với nhiều phiên bản server cùng tồn tại.

Với **SPRING_GRPC**, thêm field mới là thay đổi schema có thể triển khai an toàn khi field number mới được quản lý đúng, client cũ có thể bỏ qua unknown field và mọi bên vẫn giữ nguyên semantics của dữ liệu cũ. Tương thích wire cần được kiểm tra bằng generated code từ phiên bản schema đã phát hành, không chỉ bằng việc biên dịch thành công schema mới.
