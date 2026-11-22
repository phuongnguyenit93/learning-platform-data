# Thiết kế request và response rõ nghĩa trong Spring gRPC

Trong **Spring gRPC**, file Protocol Buffers (`.proto`) là hợp đồng mà client và server cùng biên dịch thành mã nguồn. Tên phương thức có thể diễn đạt đúng nghiệp vụ, nhưng API vẫn khó sử dụng nếu request không nói rõ cần truyền gì, response không có ý nghĩa ổn định, hoặc trạng thái lỗi bị trộn vào dữ liệu thành công. Thiết kế request/response tốt giúp client gọi unary hoặc streaming RPC đúng cách, server kiểm tra đầu vào nhất quán và hai bên phát triển schema mà không phá vỡ hợp đồng đã công bố.

Bài này thuộc chương **Schema design** của module **SPRING_GRPC**. Ta sẽ thiết kế hợp đồng cho dịch vụ danh mục sản phẩm, đọc ví dụ Java trong Spring gRPC, đồng thời xem cách request/response liên quan đến metadata, deadline, gRPC status, kiểm thử tích hợp và tính tương thích.

Sau khi học, bạn có thể:

- Xác định dữ liệu bắt buộc, dữ liệu tùy chọn, giá trị mặc định và điều kiện hợp lệ của một request.
- Quyết định trả về một đối tượng, một tập kết quả, thông tin phân trang hay một luồng sự kiện.
- Sử dụng `optional`, `oneof` và `google.protobuf.FieldMask` đúng ngữ nghĩa.
- Phân biệt dữ liệu nghiệp vụ trong response với lỗi của lời gọi gRPC.
- Thiết kế hợp đồng có thể kiểm thử và mở rộng mà vẫn bảo vệ client hiện có.

## 1. Bắt đầu từ hành vi của RPC

Trước khi định nghĩa các trường, hãy viết ra bốn câu trả lời cho mỗi RPC:

1. **Client muốn làm gì?** Lấy một sản phẩm, liệt kê theo bộ lọc, thay đổi thông tin hay theo dõi sự kiện?
2. **Client phải cung cấp gì?** Định danh nào xác định đối tượng, điều kiện lọc nào có thể bỏ trống, có cần token phân trang hoặc khóa chống xử lý trùng?
3. **Kết quả thành công có ý nghĩa gì?** Một bản ghi hiện tại, danh sách có thể rỗng, dữ liệu sau cập nhật, hay nhiều sự kiện theo thời gian?
4. **Lỗi được biểu diễn ở đâu?** Thiếu định danh, không tìm thấy tài nguyên, hết quyền hay hết deadline cần gRPC status phù hợp; một thao tác xử lý lô có thể cần kết quả riêng cho từng phần tử.

Ví dụ về hợp đồng của dịch vụ `CatalogService`:

| RPC | Request trả lời câu hỏi | Response khi thành công | Trường hợp lỗi điển hình |
| --- | --- | --- | --- |
| `GetProduct` | “Sản phẩm nào?” | Chi tiết đúng một sản phẩm | Thiếu mã: `INVALID_ARGUMENT`; không tồn tại: `NOT_FOUND` |
| `ListProducts` | “Lọc và lấy trang nào?” | Danh sách (có thể rỗng) và token trang tiếp theo | Token sai/ngữ nghĩa bộ lọc không hợp lệ: `INVALID_ARGUMENT` |
| `UpdateProduct` | “Sửa sản phẩm nào, những trường nào?” | Trạng thái sản phẩm sau khi cập nhật | Không tồn tại: `NOT_FOUND`; dữ liệu không hợp lệ: `INVALID_ARGUMENT` |
| `WatchProductEvents` | “Theo dõi nhóm sản phẩm nào?” | Nhiều sự kiện theo thời gian | Không có quyền: `PERMISSION_DENIED`; sự cố dịch vụ: `UNAVAILABLE` |

Thiết kế thông điệp theo **ngữ nghĩa quan sát được**. Không nên yêu cầu client truyền một `database_table_name` khi server có thể tự quyết định nơi lưu, hoặc trả về một `success = true` trong mọi response dù gRPC đã phân biệt trạng thái thành công và thất bại.

## 2. Một hợp đồng .proto hoàn chỉnh

Giả sử file `src/main/proto/catalog/v1/catalog.proto` chứa:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";

import "google/protobuf/field_mask.proto";
import "google/protobuf/timestamp.proto";

service CatalogService {
  // Một request -> một response.
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
  rpc ListProducts(ListProductsRequest) returns (ListProductsResponse);
  rpc UpdateProduct(UpdateProductRequest) returns (UpdateProductResponse);

  // Một request -> một luồng response.
  rpc WatchProductEvents(WatchProductEventsRequest)
      returns (stream ProductEvent);
}

message Product {
  string product_id = 1;
  string display_name = 2;
  string category_id = 3;

  // Giá trong đơn vị nhỏ nhất của tiền tệ, ví dụ 125000 VND.
  int64 price_minor_units = 4;
  string currency_code = 5;
  bool active = 6;
  google.protobuf.Timestamp updated_at = 7;
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  Product product = 1;
}

message ListProductsRequest {
  // Chuỗi rỗng nghĩa là không lọc theo danh mục.
  string category_id = 1;
  // 0 dùng kích thước trang mặc định; giá trị âm bị từ chối.
  int32 page_size = 2;
  // Rỗng nghĩa là trang đầu.
  string page_token = 3;
}

message ListProductsResponse {
  repeated Product products = 1;
  // Rỗng nghĩa là không còn trang tiếp theo.
  string next_page_token = 2;
}

message UpdateProductRequest {
  // product_id xác định đối tượng; các trường khác chứa giá trị muốn đặt.
  Product product = 1;
  // Chỉ các đường dẫn trong mask mới được cập nhật.
  google.protobuf.FieldMask update_mask = 2;
  // Dùng để nhận diện các lần thử lại cùng một yêu cầu, nếu server hỗ trợ.
  string request_id = 3;
}

message UpdateProductResponse {
  // Trạng thái mới nhất sau khi cập nhật thành công.
  Product product = 1;
}

enum ProductEventType {
  PRODUCT_EVENT_TYPE_UNSPECIFIED = 0;
  PRODUCT_EVENT_TYPE_CREATED = 1;
  PRODUCT_EVENT_TYPE_UPDATED = 2;
  PRODUCT_EVENT_TYPE_DELETED = 3;
}

message WatchProductEventsRequest {
  // Rỗng nghĩa là theo dõi tất cả danh mục mà client được phép xem.
  string category_id = 1;
}

message ProductEvent {
  // Định danh sự kiện để client có thể nhận biết bản tin trùng.
  string event_id = 1;
  ProductEventType event_type = 2;
  // Luôn có với các sự kiện hợp lệ.
  string product_id = 3;
  // Có thể không có khi sự kiện biểu thị việc xóa sản phẩm.
  Product product = 4;
  google.protobuf.Timestamp occurred_at = 5;
}
```

Đây là một thiết kế minh họa, không phải hợp đồng bắt buộc cho mọi hệ thống. Quy ước cần chốt cùng nhóm sử dụng API là: `product_id` không rỗng với thao tác trên một sản phẩm; `ListProducts` trả danh sách rỗng khi không có kết quả; các giá trị tiền luôn gắn với `currency_code`; `UpdateProduct` chỉ sửa các đường dẫn trong `update_mask`; `ProductEvent` là một phần tử của server stream.

**Vì sao tách `Product` và các request/response?** `Product` mô tả đối tượng nghiệp vụ có thể tái sử dụng. `GetProductRequest` chứa tiêu chí tìm; `ListProductsRequest` chứa tiêu chí lọc/phân trang; `UpdateProductRequest` chứa cả đối tượng cần sửa và phạm vi cập nhật. Tách chúng tránh một kiểu `Product` bị dùng làm input cho mọi thao tác với ý nghĩa bất đồng.

## 3. Thiết kế request: đúng dữ liệu đầu vào, đúng tính bắt buộc

### 3.1. Lấy một tài nguyên: request ngắn nhưng đủ điều kiện

```proto
message GetProductRequest {
  string product_id = 1;
}
```

Request không cần chứa `display_name`, `category_id` hoặc giá của sản phẩm: đó không phải dữ liệu cần thiết để tìm theo mã. Hợp đồng nên công bố rõ các điều kiện:

- `product_id` bắt buộc **theo nghiệp vụ**; chuỗi rỗng bị từ chối bằng `INVALID_ARGUMENT`.
- Nếu mã đúng định dạng nhưng tài nguyên không tồn tại, trả `NOT_FOUND`.
- Nếu định danh là tài nguyên cần được kiểm tra quyền, server còn phải áp dụng quy tắc xác thực/phân quyền trước khi cung cấp dữ liệu.

Trong proto3, `string product_id = 1;` có giá trị mặc định `""` nếu không được gửi. Cú pháp không tự biến field thành bắt buộc; server cần validate. Nếu cần phân biệt “không gửi” và “cố ý gửi chuỗi rỗng”, hãy cân nhắc `optional string product_id = 1;` rồi kiểm tra cả sự hiện diện lẫn giá trị; với API chỉ cho phép mã khác rỗng, kiểm tra `isBlank()` có thể đã đủ.

### 3.2. Liệt kê: đặt quy tắc mặc định và phân trang rõ ràng

`ListProductsRequest` dùng `category_id` để lọc, `page_size` giới hạn số bản ghi, và `page_token` tiếp tục từ trang trước:

```json
{
  "categoryId": "CAT-10",
  "pageSize": 20,
  "pageToken": ""
}
```

Trong ví dụ này, thống nhất quy tắc phía server:

| Trường | Giá trị | Cách hiểu |
| --- | --- | --- |
| `category_id` | `""` | Không áp dụng bộ lọc danh mục |
| `page_size` | `0` | Dùng mặc định 20 sản phẩm/trang |
| `page_size` | `1..100` | Tối đa giá trị yêu cầu, trừ khi ít bản ghi hơn |
| `page_size` | Số âm hoặc lớn hơn 100 | `INVALID_ARGUMENT` (theo quy ước của API ví dụ) |
| `page_token` | `""` | Trang đầu tiên |
| `page_token` | Token do server phát hành | Truy xuất trang tiếp theo theo điều kiện đã thống nhất |

Không nên trả “tất cả sản phẩm” một cách không giới hạn chỉ vì client quên cung cấp `page_size`. Server nên áp dụng giới hạn số lượng và kích thước response để bảo vệ hiệu năng và độ tin cậy.

`page_token` nên là **opaque token**: client lưu và gửi lại nguyên vẹn, không tự phân tích hoặc sửa. Khi thiết kế server, cần quyết định token có ràng buộc với bộ lọc, thứ tự sắp xếp, quyền truy cập và thời hạn hay không. Nếu yêu cầu snapshot nhất quán qua nhiều trang, cần cơ chế riêng; thứ tự ổn định một mình không ngăn bản ghi thay đổi khi client duyệt trang.

### 3.3. Khi nào cần `optional` hoặc `oneof`?

Một field scalar bình thường trong proto3 không cho biết chắc client đã gửi giá trị hay chưa. Điều này quan trọng với API cập nhật hoặc yêu cầu phân biệt “không truyền” và “truyền giá trị mặc định”:

```proto
message SetProductVisibilityRequest {
  string product_id = 1;
  optional bool active = 2;
}
```

Với Java code sinh phù hợp, `hasActive()` cho biết client có truyền trường `active` hay không; `getActive()` trả Boolean. Khi `active` không hiện diện thì không nên tự suy ra lệnh “đặt thành `false`”.

Nếu có hai cách định danh loại trừ nhau, `oneof` diễn đạt ý nghĩa tốt hơn hai string tùy ý:

```proto
message LookupProductRequest {
  oneof selector {
    string product_id = 1;
    string sku = 2;
  }
}
```

`oneof` bảo đảm tại một thời điểm message được xây dựng chứa tối đa một lựa chọn trong nhóm. Server vẫn phải kiểm tra yêu cầu **có ít nhất một lựa chọn hợp lệ** nếu nghiệp vụ cần đúng một.

## 4. Thiết kế response: thành công phải có ý nghĩa xác định

### 4.1. Trả về một đối tượng

```proto
message GetProductResponse {
  Product product = 1;
}
```

Hợp đồng quy định rằng khi `GetProduct` thành công, `product` phải có mặt và có `product_id` hợp lệ. Trong proto3, message field có thể vắng mặt; vì vậy server phải tự bảo đảm điều này bằng kiểm thử và logic ứng dụng. Một response thành công với `product` trống sẽ khiến client phải suy đoán “không tìm thấy” hay “server quên điền dữ liệu”.

Ta cũng có thể dùng `returns (Product)` trực tiếp nếu hợp đồng đơn giản. Chọn `GetProductResponse` khi cần một ranh giới rõ ràng cho từng phương thức và dự kiến thêm metadata **nghiệp vụ** của kết quả; đừng tạo wrapper nhiều tầng không mang ý nghĩa.

Ví dụ ProtoJSON response khi trả về sản phẩm (giá trị `int64` được ánh xạ thành chuỗi JSON theo ProtoJSON):

```json
{
  "product": {
    "productId": "P-100",
    "displayName": "Bàn phím cơ",
    "categoryId": "CAT-10",
    "priceMinorUnits": "125000",
    "currencyCode": "VND",
    "active": true,
    "updatedAt": "2026-11-19T08:00:00Z"
  }
}
```

Lưu ý: định dạng JSON ở đây là **ProtoJSON**, không phải byte protobuf nhị phân trên HTTP/2 của gRPC thông thường. Những công cụ như `grpcurl` có thể nhận/xuất JSON theo mapping đó.

### 4.2. Trả về danh sách rỗng là thành công hợp lệ

```proto
message ListProductsResponse {
  repeated Product products = 1;
  string next_page_token = 2;
}
```

Không tìm thấy sản phẩm phù hợp bộ lọc là một kết quả `OK` với `products` rỗng. Không nên dùng `NOT_FOUND` chỉ vì một danh sách không có phần tử. `next_page_token` rỗng biểu thị kết thúc phân trang; một response chỉ có dữ liệu nhưng thiếu cách chuyển trang sẽ buộc client tự đoán.

```json
{
  "products": [],
  "nextPageToken": ""
}
```

Với ProtoJSON, các trường giá trị mặc định có thể bị lược bỏ theo tùy chọn serializer; ví dụ trên thể hiện ý nghĩa logic của response chứ không buộc mọi thư viện luôn xuất cả hai khóa. Client nên dựa vào kiểu và giá trị mặc định theo protobuf.

### 4.3. Trả về đối tượng sau cập nhật

`UpdateProductResponse.product` chứa trạng thái cuối cùng sau khi server áp dụng quy tắc nghiệp vụ, chẳng hạn chuẩn hóa tên hoặc điều chỉnh `updated_at`. Điều này hữu ích hơn chỉ trả một cờ `success` vì client có thể đồng bộ trạng thái ngay sau thao tác.

Nếu thực sự không cần dữ liệu trả về, có thể dùng `google.protobuf.Empty`, nhưng phải cân nhắc việc client cần đọc lại tài nguyên. Không nhất thiết gắn thêm `bool success`: trong gRPC, kết thúc bình thường là thành công và các trường hợp thất bại phải dùng status hoặc một mô hình kết quả được xác định rõ.

## 5. Cập nhật từng phần: phân biệt “không đổi” với “đặt về mặc định”

Đây là một trong những quyết định dễ gây lỗi nhất. Giả sử sản phẩm hiện tại có `active = true`. Client muốn đặt `active = false` mà không đổi giá. Nếu server tự cập nhật tất cả field trong `Product`, các field không gửi sẽ nhận giá trị mặc định và có thể vô tình bị xóa.

Trong thiết kế ở mục 2, ta dùng `google.protobuf.FieldMask`:

```proto
message UpdateProductRequest {
  Product product = 1;
  google.protobuf.FieldMask update_mask = 2;
  string request_id = 3;
}
```

Request logic:

```text
product.product_id = "P-100"
product.active = false
update_mask.paths = ["active"]
request_id = "change-20261119-001"
```

Server chỉ thay `active` vì mask có đúng đường dẫn đó; các field không được liệt kê sẽ giữ nguyên. Đây là cách xử lý trường Boolean `false` hoặc chuỗi rỗng được **chủ ý** dùng để xóa giá trị.

Quy tắc cần ghi rõ trong tài liệu API:

1. `product` và `update_mask` phải có mặt; `product.product_id` không rỗng.
2. `update_mask.paths` phải không rỗng. Dự án này không coi mask rỗng là “cập nhật tất cả”.
3. Chỉ cho phép các đường dẫn `display_name`, `category_id`, `price_minor_units`, `currency_code`, `active`; từ chối `product_id` và `updated_at` vì chúng do server quản lý.
4. Với các field có liên hệ nghiệp vụ, ví dụ giá và mã tiền tệ, validate tổ hợp cuối cùng để tránh dữ liệu không nhất quán.
5. `request_id` chỉ có tác dụng chống xử lý trùng **nếu server triển khai lưu/kiểm tra idempotency key** với phạm vi và thời gian hiệu lực rõ ràng; việc thêm field không tự tạo ra tính idempotent.

Đường dẫn trong `FieldMask` được định nghĩa theo **tên field proto**, ví dụ `display_name`, `active`. Khi biểu diễn FieldMask bằng ProtoJSON, cách mã hóa chuỗi mask tuân theo quy tắc JSON riêng (ví dụ `"updateMask": "displayName,active"`). Không được nhầm giữa đường dẫn bên trong `FieldMask` và tên phương thức accessor Java.

Một biến thể khác là request riêng với các scalar `optional`. Cách đó phù hợp cập nhật ít field, nhưng với nhiều thuộc tính và dữ liệu lồng nhau, `FieldMask` cho phép mô tả rõ tập trường được sửa. Dù chọn cách nào, phải ghi chép hành vi của “không truyền”, “truyền mặc định” và “xóa giá trị”.

## 6. Streaming RPC: response không còn là một kết quả duy nhất

Không phải lúc nào một lời gọi gRPC cũng chỉ có một request và một response:

| Kiểu RPC | Chữ ký proto | Thiết kế request/response |
| --- | --- | --- |
| Unary | `rpc GetProduct(GetProductRequest) returns (GetProductResponse);` | Một request xác định mục tiêu; một response xác định kết quả |
| Server streaming | `rpc WatchProductEvents(WatchProductEventsRequest) returns (stream ProductEvent);` | Request chọn phạm vi theo dõi; mỗi response là một sự kiện |
| Client streaming | `rpc UploadMeasurements(stream Measurement) returns (UploadMeasurementsResponse);` | Client gửi nhiều bản ghi; server trả tổng kết sau khi đọc xong luồng |
| Bidirectional streaming | `rpc SyncProducts(stream SyncProductsRequest) returns (stream SyncProductsResponse);` | Hai phía gửi nhiều thông điệp độc lập; cần làm rõ tương quan và thứ tự |

Hai ví dụ cuối chỉ minh họa dạng chữ ký; muốn biên dịch cần khai báo các message `Measurement`, `UploadMeasurementsResponse`, `SyncProductsRequest` và `SyncProductsResponse` tương ứng.

### 6.1. Server streaming: mỗi response phải tự giải thích được

Trong `WatchProductEvents`, mỗi `ProductEvent` chứa:

- `event_id` để phát hiện hoặc xử lý bản tin trùng theo chính sách hệ thống.
- `event_type` để client biết đó là tạo, cập nhật hay xóa.
- `product_id` để nhận diện sản phẩm ngay cả khi bản tin xóa không còn payload `product`.
- `occurred_at` để ghi nhận thời điểm sự kiện, không mặc định là thời điểm client nhận.

Hợp đồng còn cần nêu rõ thứ tự sự kiện, khả năng mất kết nối, replay và điểm bắt đầu theo dõi nếu hệ thống hỗ trợ. Chỉ thêm `event_id` không bảo đảm truyền đúng một lần. Nếu cần tiếp tục stream sau khi ngắt kết nối, hãy thiết kế thêm cursor/resume token và cơ chế lưu sự kiện phù hợp.

Server có thể phát ra **không bản tin nào** trong một khoảng thời gian mà luồng vẫn hoạt động; đó không phải kết quả lỗi hoặc “không tìm thấy”. Client phải hỗ trợ hủy stream và deadline khi phù hợp. Nếu nghiệp vụ cần thông báo heartbeat, hãy định nghĩa rõ một kiểu sự kiện hoặc cơ chế kiểm tra liveness; đừng tạo một `ProductEvent` rỗng mơ hồ.

### 6.2. Client streaming và bidirectional: xác định quan hệ giữa các message

Với client streaming upload, response tổng kết nên cho biết số bản ghi hợp lệ, số bản ghi từ chối và thông tin nhận diện lỗi theo từng bản ghi nếu chấp nhận xử lý một phần. `accepted_count` và `rejected_count` chỉ có ích khi hợp đồng định nghĩa điều gì được tính là đã chấp nhận.

Với bidirectional streaming, không nên ngầm giả định request thứ `n` luôn tạo ra response thứ `n`. Nếu hệ thống xử lý song song hoặc gửi sự kiện chủ động, hãy thêm một `correlation_id` vào từng message liên quan và mô tả cách ghép cặp, thứ tự và chính sách retry. Deadline, backpressure, kết thúc từng chiều của stream và lỗi giữa chừng cũng cần được xác định khi triển khai.

## 7. Phân biệt dữ liệu nghiệp vụ và trạng thái lỗi gRPC

**gRPC status** là kết quả ở mức lời gọi, tách khỏi nội dung message trả về khi thành công. Những mã thường gặp:

| Tình huống | Status phù hợp | Diễn giải |
| --- | --- | --- |
| Thiếu `product_id`, `page_size` âm, mask không hợp lệ | `INVALID_ARGUMENT` | Request sai độc lập với trạng thái hiện tại của hệ thống |
| `GetProduct` không có tài nguyên được hỏi | `NOT_FOUND` | Mục tiêu hợp lệ nhưng không tồn tại |
| Chưa xác thực | `UNAUTHENTICATED` | Thiếu hoặc sai danh tính xác thực |
| Đã xác thực nhưng không được phép | `PERMISSION_DENIED` | Quyền không đủ cho thao tác |
| Cập nhật mâu thuẫn với trạng thái hiện tại | `FAILED_PRECONDITION` hoặc `ABORTED` tùy bản chất | Điều kiện không còn phù hợp hoặc giao dịch bị hủy do xung đột |
| Dịch vụ tạm thời không thể phục vụ | `UNAVAILABLE` | Có thể thích hợp để retry theo chính sách |
| Hết thời hạn đã cấu hình | `DEADLINE_EXCEEDED` | Lời gọi không hoàn tất trước deadline |

Không nên nhét `status_code`/`error_message` vào mọi response rồi trả gRPC `OK` ngay cả khi request thất bại. Cách đó khiến interceptor, metric, retry và quan sát lỗi ở tầng gRPC hiểu sai kết quả. Khi client cần chi tiết lỗi có cấu trúc, hệ thống có thể thống nhất sử dụng cơ chế rich error model (ví dụ `google.rpc.Status` và các chi tiết lỗi); phải kiểm tra hỗ trợ thư viện và kích thước metadata trước khi triển khai.

**Metadata và deadline** cũng có vai trò riêng. Auth token, trace context và các header điều khiển phù hợp với metadata, không cần lặp thành field trong mọi request. Client đặt deadline cho lời gọi; server phải tôn trọng việc hủy/timeout. TLS bảo vệ đường truyền; không phải một trường `encrypted = true` trong request. Ngược lại, `product_id`, `page_token` và `update_mask` thuộc dữ liệu nghiệp vụ nên nên nằm trong message.

## 8. Minh họa triển khai unary trong Spring gRPC

Khi biên dịch proto bằng `protoc` và plugin gRPC Java, các lớp như `GetProductRequest`, `GetProductResponse`, `Product` và `CatalogServiceGrpc` được sinh theo `java_package`. Một service triển khai bằng Spring gRPC có thể xử lý các trường hợp thành công/lỗi như sau:

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import com.myshop.grpc.catalog.v1.Product;
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

        String id = request.getProductId();
        if (id.isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id must not be blank")
                    .asRuntimeException());
            return;
        }

        // Dữ liệu cố định để minh họa hành vi; hệ thống thực sẽ đọc repository.
        if (!id.equals("P-100")) {
            observer.onError(Status.NOT_FOUND
                    .withDescription("product not found")
                    .asRuntimeException());
            return;
        }

        Product product = Product.newBuilder()
                .setProductId("P-100")
                .setDisplayName("Bàn phím cơ")
                .setCategoryId("CAT-10")
                .setPriceMinorUnits(125000L)
                .setCurrencyCode("VND")
                .setActive(true)
                .build();

        GetProductResponse response = GetProductResponse.newBuilder()
                .setProduct(product)
                .build();
        observer.onNext(response);
        observer.onCompleted();
    }
}
```

Trong ví dụ này:

- Với `product_id = ""`, server gọi `onError(INVALID_ARGUMENT)` và **không** gửi response thành công.
- Với mã khác `P-100`, server gọi `onError(NOT_FOUND)`.
- Với `P-100`, server phát đúng một `GetProductResponse` có `Product` rồi kết thúc bằng `onCompleted()`.

Mã ví dụ cố tình giản lược repository, xác thực và quan sát vận hành để làm rõ hợp đồng. Khi tích hợp thật, nên kiểm tra quyền truy cập và quy tắc dữ liệu trước khi trả sản phẩm, không làm lộ thông tin nhạy cảm trong thông báo lỗi, và có kiểm thử cho từng trạng thái. Đường dẫn import annotation `@GrpcService` và cách cấu hình starter cần phù hợp phiên bản Spring gRPC mà dự án đang dùng.

Một client gRPC Java có stub đã được tạo có thể đọc kết quả và phân biệt lỗi theo `StatusRuntimeException`:

```java
import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import io.grpc.Channel;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;

public class CatalogClientExample {
    public static GetProductResponse fetch(Channel channel, String productId) {
        var stub = CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);

        try {
            return stub.getProduct(GetProductRequest.newBuilder()
                    .setProductId(productId)
                    .build());
        } catch (StatusRuntimeException ex) {
            if (ex.getStatus().getCode() == Status.Code.NOT_FOUND) {
                // Ứng dụng tự chọn cách xử lý tài nguyên không tồn tại.
                return null;
            }
            throw ex;
        }
    }
}
```

`Channel` được truyền vào để ví dụ tập trung vào request/response; ứng dụng Spring nên quản lý và tái sử dụng channel theo cấu hình dự án. Trả `null` ở nhánh `NOT_FOUND` chỉ là lựa chọn của hàm minh họa phía client, không phải response gRPC được server gửi khi lỗi.

## 9. Thiết kế để thay đổi mà không gây bất ngờ

Trong Protobuf, **số field và kiểu wire** quan trọng đối với dữ liệu nhị phân; đồng thời tên field ảnh hưởng mã sinh và ProtoJSON, còn tên `service`/`rpc` ảnh hưởng đường dẫn gRPC. Khi chỉnh một request hoặc response đã công bố, cần đánh giá từng lớp tương thích:

| Thay đổi | Tác động thường gặp | Khuyến nghị |
| --- | --- | --- |
| Thêm field mới với số mới | Client cũ thường bỏ qua field chưa biết khi xử lý binary protobuf | Đặt mặc định hợp lý; đừng khiến field mới trở thành bắt buộc với client cũ mà không có chuyển đổi |
| Đổi tên field, giữ số/kiểu | Có thể tương thích trên binary wire nhưng đổi accessor Java, khóa ProtoJSON và descriptor | Hạn chế sau phát hành; đánh giá mọi client, đặc biệt client JSON |
| Đổi số field đã phát hành | Có nguy cơ đọc nhầm/đánh mất dữ liệu | Không đổi; nếu bỏ field, đặt `reserved` cho số và tên đã xóa |
| Đổi kiểu field | Có thể làm thay đổi wire type hoặc ngữ nghĩa, kể cả khi đọc được byte | Xem là thay đổi hợp đồng; cân nhắc field mới hoặc version API |
| Đổi `service` hoặc `rpc` | Đổi đường dẫn RPC trên mạng | Giữ endpoint cũ trong giai đoạn chuyển hoặc cung cấp phiên bản mới |
| Thay `ListProducts` từ trả toàn bộ sang bắt buộc phân trang | Client cũ có thể chỉ lấy trang đầu mà không biết | Công bố quy tắc phân trang từ đầu; có migration rõ ràng khi đổi hành vi |
| Đổi nghĩa `page_token` hoặc `update_mask` | Không nhất thiết đổi cấu trúc proto nhưng có thể phá vỡ logic client | Duy trì ngữ nghĩa được tài liệu hóa; phiên bản hóa khi không thể tương thích |

Ví dụ cách bảo vệ field đã xóa:

```proto
message Product {
  reserved 8;
  reserved "legacy_price";

  string product_id = 1;
  string display_name = 2;
}
```

Đây là ví dụ rút gọn để minh họa `reserved`. Trong schema thực, phải giữ các field còn được sử dụng; không được thay toàn bộ message bằng đoạn rút gọn này. Số 8 và tên `legacy_price` không còn được phép tái sử dụng trong chính message `Product`.

## 10. Kiểm thử hợp đồng request/response

Một bộ kiểm thử tích hợp nên kiểm tra hành vi mà client thực sự nhìn thấy, thay vì chỉ kiểm tra builder có thể tạo message. Với `CatalogService`, ít nhất cần các trường hợp:

| Ca thử | Input | Kỳ vọng |
| --- | --- | --- |
| Lấy sản phẩm hợp lệ | `GetProductRequest{product_id="P-100"}` | `OK`, `response.hasProduct()` đúng, `product_id` khớp |
| Thiếu định danh | `GetProductRequest{}` | `INVALID_ARGUMENT`, không có response thành công |
| Không tìm thấy | Mã hợp lệ nhưng chưa tồn tại | `NOT_FOUND` |
| Danh sách trống | Bộ lọc không có kết quả | `OK`, số phần tử `products` bằng 0, không có trang kế |
| Phân trang | Nhiều dữ liệu hơn `page_size` | Kích thước trang và `next_page_token` đúng; không bỏ sót/trùng trong điều kiện kiểm thử |
| Cập nhật Boolean về `false` | `update_mask.paths=["active"]` | `active` thành `false`; field ngoài mask giữ nguyên |
| Mask chứa field cấm sửa | `update_mask.paths=["product_id"]` | `INVALID_ARGUMENT` |
| Stream bị hủy | Client hủy `WatchProductEvents` | Server ngừng công việc liên quan và giải phóng tài nguyên |
| Deadline hết | Client đặt deadline ngắn hơn thời gian xử lý | Client nhận `DEADLINE_EXCEEDED` hoặc trạng thái phù hợp với cuộc đua hoàn tất/hủy; server xử lý cancellation |

Đối với cập nhật, thử lại cùng `request_id` chỉ có ý nghĩa kiểm thử idempotency nếu hợp đồng **đã cam kết** cơ chế này và server thực sự lưu trạng thái chống xử lý lặp. Với sự kiện streaming, kiểm tra thêm cách xử lý trùng, mất kết nối, thứ tự và bắt đầu lại luồng theo các cam kết cụ thể.

Khi server thử nghiệm chạy trên `localhost:9090` ở chế độ plaintext và proto nằm dưới `src/main/proto`, có thể gửi request unary:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto catalog/v1/catalog.proto \
  -d '{"productId":"P-100"}' \
  localhost:9090 shop.catalog.v1.CatalogService/GetProduct
```

Đường dẫn phương thức là `/shop.catalog.v1.CatalogService/GetProduct`; `productId` là dạng JSON theo mapping ProtoJSON của `product_id`. Lệnh `grpcurl` dùng các tham số phù hợp với cổng và cấu hình TLS thực tế, không thể giả định mọi môi trường đều là plaintext.

## 11. Bài tập tự kiểm tra

**Bài tập 1 — Request thiếu ý nghĩa.** Một RPC khai báo:

```proto
rpc FindProduct(Product) returns (Product);
```

Client chỉ cần tìm theo mã sản phẩm. Thiết kế lại request/response thế nào để dễ hiểu và tránh client gửi dữ liệu không liên quan?

*Gợi ý:* `GetProduct(GetProductRequest) returns (GetProductResponse)`; request chỉ có `product_id`, response có `Product product`. Ghi rõ mã rỗng là `INVALID_ARGUMENT`, không tìm thấy là `NOT_FOUND` và response thành công phải có `product`.

**Bài tập 2 — Không có dữ liệu.** `ListProducts` không tìm được sản phẩm nào trong danh mục `CAT-99`. Nên trả `NOT_FOUND` hay `OK` với danh sách rỗng?

*Gợi ý:* `OK` với `products` rỗng và `next_page_token` rỗng. Danh sách có thể không có phần tử dù bộ lọc hoàn toàn hợp lệ.

**Bài tập 3 — Cập nhật giá trị mặc định.** Sản phẩm có `active = true`, client muốn đổi thành `false`. Vì sao gửi một `Product` với `active = false` nhưng không nói rõ phạm vi cập nhật có thể gây lỗi?

*Gợi ý:* Các scalar proto3 không được gửi có thể được đọc thành giá trị mặc định. Nếu server cập nhật mọi field, các field khác có thể bị ghi đè. Dùng `update_mask.paths = ["active"]` hoặc mô hình `optional`/presence phù hợp để phân biệt “không sửa” với “đặt thành false”.

**Bài tập 4 — Lỗi và response.** Nếu `GetProduct` không tìm thấy mã `P-404`, nên trả `GetProductResponse{product: default}` kèm `success = false` hay gRPC status `NOT_FOUND`?

*Gợi ý:* Dùng `NOT_FOUND` theo hợp đồng; không gửi response thành công giả. Client có thể xử lý theo mã status, còn trường hợp tìm kiếm danh sách rỗng vẫn là thành công.

**Bài tập 5 — Stream có thể bị gián đoạn.** Với `WatchProductEvents`, client nhận hai sự kiện có cùng `event_id` sau khi kết nối lại. Có thể kết luận server vi phạm hợp đồng không?

*Gợi ý:* Chưa thể kết luận. Cần xem API cam kết at-most-once, at-least-once hay cơ chế replay nào. `event_id` giúp client nhận biết trùng nhưng không tự bảo đảm không phát trùng; hợp đồng cần nêu rõ cách resume và deduplicate.

Một request/response rõ nghĩa luôn trả lời được: **client phải gửi gì, trường hợp nào hợp lệ, server cam kết trả điều gì và lỗi thể hiện thế nào**. Khi các quyết định đó đã được ghi thành hợp đồng Protocol Buffers, mã Java Spring gRPC, kiểm thử tích hợp và cơ chế quan sát dịch vụ sẽ cùng dựa trên một cách hiểu thống nhất.
