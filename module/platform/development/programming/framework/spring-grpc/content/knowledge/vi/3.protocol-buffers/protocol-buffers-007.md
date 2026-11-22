# Repeated field và map field

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn **repeated** khi cần danh sách có thứ tự và **map** khi cần tra cứu theo khóa.
- Khai báo repeated field và map field trong proto3, hiểu giới hạn kiểu dữ liệu và giá trị mặc định.
- Dùng API Java được sinh như **addXxx()**, **getXxxList()**, **putXxx()**, **getXxxMap()**.
- Giải thích cách hai loại field được mã hóa trong Protobuf nhị phân và biểu diễn trong ProtoJSON.
- Thiết kế cập nhật danh sách/map qua request gRPC mà không nhầm tập hợp rỗng với yêu cầu không thay đổi.

## 1. Chọn danh sách hay tập hợp khóa–giá trị?

Trong hợp đồng **SPRING_GRPC**, message Protobuf mô tả dữ liệu request/response của RPC. Khi một message cần chứa nhiều giá trị, proto3 cung cấp hai cấu trúc thường dùng:

- **repeated** biểu diễn một danh sách gồm 0 hoặc nhiều phần tử. Thứ tự và phần tử trùng lặp đều có thể có ý nghĩa.
- **map** biểu diễn các cặp khóa–giá trị. Mỗi khóa chỉ có một giá trị sau khi parse; thứ tự duyệt không phải một phần của hợp đồng.

Ví dụ, một sản phẩm có thể có nhiều nhãn phân loại và một tập thuộc tính tra cứu theo tên:

~~~proto
syntax = "proto3";

message Product {
  string sku = 1;
  string name = 2;
  repeated string tags = 3;
  map<string, string> attributes = 4;
}
~~~

**tags** phù hợp với danh sách như **["sale", "featured", "sale"]**: có thứ tự và cho phép lặp. **attributes** phù hợp với dữ liệu như **{"color":"blue","size":"M"}**: truy cập bằng khóa và không dựa vào thứ tự.

| Nhu cầu | Chọn | Lý do |
| --- | --- | --- |
| Danh sách bước theo thứ tự thực hiện | **repeated** | Thứ tự phần tử được giữ. |
| Nhiều mã lỗi, có thể trùng | **repeated** | Danh sách giữ được phần tử trùng. |
| Tra cứu thuộc tính theo tên | **map** | Mỗi khóa ánh xạ tới một giá trị. |
| Danh sách bản ghi cần sắp xếp hoặc phân trang | **repeated** | Thứ tự là dữ liệu cần giữ. |
| Tập cấu hình theo mã định danh duy nhất | **map** | Truy cập theo khóa thuận tiện. |

Không chọn map chỉ vì dữ liệu hiện tại trông giống một đối tượng JSON. Nếu thứ tự hoặc khóa trùng có ý nghĩa, hãy dùng repeated message để mô tả đúng mô hình.

## 2. Khai báo repeated field

Đặt từ khóa **repeated** trước kiểu dữ liệu:

~~~proto
message SearchResponse {
  repeated string suggestions = 1;
  repeated Product products = 2;
}

message Product {
  string sku = 1;
  string name = 2;
}
~~~

Repeated hỗ trợ scalar, enum và message. Một field repeated có thể chứa:

- **0 phần tử**: danh sách rỗng, là giá trị mặc định.
- **1 phần tử**: danh sách có một phần tử.
- **Nhiều phần tử**: giữ thứ tự tuần tự hóa/đọc vào.
- **Phần tử trùng nhau**: được phép; Protobuf không tự loại bỏ trùng lặp.

Ví dụ danh sách kỹ năng **["Java", "gRPC", "Java"]** vẫn có ba phần tử theo đúng thứ tự. Nếu nghiệp vụ cần loại bỏ trùng, sắp xếp hoặc chuẩn hóa, ứng dụng phải thực hiện điều đó.

Repeated field không có **presence** riêng như optional scalar. Khi không có phần tử, getter trả danh sách rỗng; API Java không sinh **hasSuggestions()**. Vì vậy, chỉ nhìn danh sách rỗng không thể biết client không gửi field hay gửi danh sách rỗng với ý định xóa toàn bộ.

## 3. Khai báo map field và giới hạn kiểu khóa

Cú pháp map:

~~~proto
message Product {
  string sku = 1;
  map<string, string> attributes = 2;
  map<string, int32> stock_by_warehouse = 3;
}
~~~

Map có một kiểu khóa và một kiểu giá trị. Kiểu khóa chỉ được là:

- Các kiểu số nguyên được Protobuf cho phép, như **int32**, **int64**, **uint32**, **sint32**, **fixed32**, **sfixed64** và các biến thể số nguyên tương ứng.
- **bool**.
- **string**.

Không dùng **float**, **double**, **bytes**, **enum** hoặc **message** làm khóa. Giá trị map có thể là scalar, enum hoặc message; không thể khai báo trực tiếp một map lồng trong map hoặc một repeated field làm kiểu value.

Ví dụ map có giá trị là message:

~~~proto
message WarehouseStock {
  int32 available = 1;
  int32 reserved = 2;
}

message Inventory {
  map<string, WarehouseStock> stock_by_warehouse = 1;
}
~~~

Map phù hợp khi khóa là duy nhất theo mô hình dữ liệu, chẳng hạn mã kho, mã ngôn ngữ hoặc tên thuộc tính. Nếu cần giữ nhiều giá trị cho cùng một khóa, hoặc cần thứ tự các cặp, hãy dùng **repeated message** chứa key và value.

## 4. API Java được sinh cho repeated

Với:

~~~proto
message SearchResponse {
  repeated string suggestions = 1;
}
~~~

Java message cung cấp các phương thức đọc phổ biến:

| Phương thức | Ý nghĩa |
| --- | --- |
| **getSuggestionsList()** | Lấy danh sách các phần tử. |
| **getSuggestionsCount()** | Lấy số phần tử. |
| **getSuggestions(index)** | Lấy phần tử tại vị trí. |

Builder cung cấp các phương thức chỉnh sửa:

| Phương thức | Ý nghĩa |
| --- | --- |
| **addSuggestions(value)** | Thêm một phần tử vào cuối. |
| **addAllSuggestions(values)** | Thêm nhiều phần tử vào cuối. |
| **setSuggestions(index, value)** | Thay phần tử tại vị trí. |
| **clearSuggestions()** | Xóa toàn bộ phần tử khỏi builder. |

Ví dụ:

~~~java
import com.example.catalog.v1.SearchResponse;
import java.util.List;

SearchResponse response = SearchResponse.newBuilder()
    .addSuggestions("Java")
    .addSuggestions("gRPC")
    .addAllSuggestions(List.of("Spring", "Protocol Buffers"))
    .build();

System.out.println(response.getSuggestionsCount()); // 4
System.out.println(response.getSuggestions(0));     // Java
System.out.println(response.getSuggestionsList());
~~~

Message sau **build()** là bất biến. Danh sách trả về từ message không phải nơi để chỉnh sửa trực tiếp; muốn thay đổi, dùng **toBuilder()** hoặc tạo builder mới:

~~~java
SearchResponse revised = response.toBuilder()
    .setSuggestions(0, "Java 21")
    .addSuggestions("HTTP/2")
    .build();
~~~

Với repeated message, builder còn có các phương thức như **addProducts(product)**, **addAllProducts(...)** và **getProductsBuilder(index)**. Mỗi phần tử vẫn là một message Protobuf riêng.

## 5. API Java được sinh cho map

Với:

~~~proto
message Product {
  map<string, string> attributes = 1;
}
~~~

Message Java thường cung cấp:

- **getAttributesMap()**: lấy map.
- **getAttributesCount()**: số cặp khóa–giá trị.
- **getAttributesOrDefault(key, defaultValue)**: lấy giá trị hoặc trả default do ứng dụng cung cấp.
- **getAttributesOrThrow(key)**: lấy giá trị và báo lỗi nếu khóa không tồn tại.
- **containsAttributes(key)**: kiểm tra khóa.

Builder cung cấp:

- **putAttributes(key, value)**: thêm hoặc thay giá trị của một khóa.
- **putAllAttributes(map)**: thêm nhiều cặp.
- **removeAttributes(key)**: xóa một khóa.
- **clearAttributes()**: xóa toàn bộ map.

Ví dụ:

~~~java
import com.example.catalog.v1.Product;
import java.util.Map;

Product product = Product.newBuilder()
    .setSku("KB-42")
    .putAttributes("color", "black")
    .putAttributes("layout", "US")
    .putAllAttributes(Map.of("switch", "linear", "wireless", "true"))
    .build();

System.out.println(product.getAttributesCount());            // 4
System.out.println(product.getAttributesMap().get("color")); // black
System.out.println(product.containsAttributes("layout"));    // true

Product updated = product.toBuilder()
    .putAttributes("color", "white")
    .removeAttributes("wireless")
    .build();
~~~

**putAttributes("color", "white")** thay giá trị hiện có của khóa color; nó không tạo thêm một cặp color thứ hai trong map. Muốn lưu nhiều giá trị cho một khóa, dùng repeated message thay vì map.

## 6. Cách Protobuf mã hóa repeated và map

### Repeated scalar

Trong proto3, các repeated scalar **có thể packed** như số nguyên, boolean, enum và float/double mặc định dùng **packed encoding**. Các giá trị được gom vào một payload length-delimited của cùng field.

Ví dụ:

~~~proto
message Quantities {
  repeated int32 values = 1;
}
~~~

Với danh sách **[1, 2]**, một biểu diễn packed là:

~~~text
0A 02 01 02
|  |  |  |
|  |  +--+-- Hai giá trị varint: 1 và 2
|  +-------- Độ dài payload: 2 byte
+----------- Tag field 1, wire type 2 (length-delimited)
~~~

Các kiểu **string**, **bytes** và **message** không được packed; mỗi phần tử được mã hóa như một lần xuất hiện của field. Parser Protobuf chấp nhận dạng packed và unpacked cho repeated field thuộc nhóm kiểu packable, giúp tương thích giữa các cách phát sinh mã.

### Map entry

Map được biểu diễn trên wire như một repeated field của message entry tổng hợp. Về ý tưởng, khai báo:

~~~proto
map<string, int32> stock = 1;
~~~

tương đương cấu trúc wire của các entry có hai field:

~~~proto
message StockEntry {
  string key = 1;
  int32 value = 2;
}
~~~

Mỗi entry được mã hóa thành một message length-delimited tại số field của map bên ngoài. Số 1 bên trong entry dành cho key, số 2 dành cho value. Đây là mô tả cách mã hóa; trong schema thực, không tự khai báo message entry này thay cho cú pháp map nếu không có lý do thiết kế cụ thể.

Do map dùng entry message trên wire, dữ liệu nhị phân có thể chứa nhiều entry cùng khóa. Khi parse thành map, khóa trùng được xử lý theo quy tắc **giá trị xuất hiện sau cùng thắng**. Ứng dụng không nên dựa vào thứ tự entry hoặc dùng map để biểu diễn lịch sử thay đổi theo thời gian.

## 7. Thứ tự, phần tử trùng và khóa trùng

Hai cấu trúc có hành vi khác nhau:

| Thuộc tính | Repeated | Map |
| --- | --- | --- |
| Thứ tự phần tử | Được giữ | Không được bảo đảm |
| Phần tử/khóa trùng | Phần tử trùng được giữ | Một giá trị hiệu lực cho mỗi khóa |
| Truy cập | Theo chỉ số | Theo khóa |
| Ý nghĩa mặc định | Danh sách rỗng | Map rỗng |
| API Java | List và builder add | Map và builder put/remove |

Ví dụ:

~~~proto
message Example {
  repeated string codes = 1;
  map<string, string> labels = 2;
}
~~~

Với **codes = ["A", "B", "A"]**, số phần tử là 3 và thứ tự A-B-A có ý nghĩa. Với **labels = {"region":"north"}**, không có khái niệm vị trí phần tử. Nếu dữ liệu đầu vào map có nhiều entry cùng khóa region, giá trị sau cùng được giữ sau parse.

Map Java là một cấu trúc tra cứu; không dựa vào thứ tự vòng lặp để quyết định thứ tự hiển thị, xử lý hay gửi sự kiện. Nếu cần thứ tự ổn định, hãy sắp xếp khóa ở tầng ứng dụng hoặc dùng repeated message.

## 8. ProtoJSON: repeated thành mảng, map thành object

ProtoJSON biểu diễn:

- **repeated** bằng JSON array.
- **map** bằng JSON object; khóa map trở thành tên thuộc tính JSON (dạng chuỗi), kể cả khi khóa trong .proto là số nguyên hoặc bool.

Với:

~~~proto
message Product {
  repeated string tags = 1;
  map<string, string> attributes = 2;
}
~~~

Một biểu diễn JSON:

~~~json
{
  "tags": ["sale", "featured"],
  "attributes": {
    "color": "black",
    "layout": "US"
  }
}
~~~

Danh sách giữ thứ tự phần tử. JSON object không mang cam kết thứ tự cho các cặp map. Với map có khóa số, ví dụ **map<int32, string> names = 1**, khóa JSON vẫn được viết dưới dạng chuỗi như **"10"**; parser ProtoJSON chuyển khóa về kiểu số tương ứng.

Field repeated/map rỗng thường không xuất hiện trong JSON theo printer mặc định, nhưng vẫn có giá trị rỗng khi đọc message. Đừng dùng sự xuất hiện/vắng mặt của thuộc tính JSON để suy luận rằng repeated/map có explicit presence như optional scalar.

Khi cần ProtoJSON chính thức trong Java, dùng **JsonFormat** từ **protobuf-java-util** tương thích với runtime:

~~~java
import com.google.protobuf.util.JsonFormat;

String json = JsonFormat.printer().print(product);

Product.Builder parsed = Product.newBuilder();
JsonFormat.parser().merge(json, parsed);
Product restored = parsed.build();

System.out.println(restored.getTagsList());
System.out.println(restored.getAttributesMap());
~~~

Không đồng nhất ProtoJSON với JSON do một thư viện tổng quát tự chuyển đổi object Java. Các quy tắc về tên field, enum, số nguyên 64-bit, bytes và well-known types có thể khác nhau.

## 9. Merge semantics: repeated nối thêm, map gộp theo khóa

Khi dùng **mergeFrom()**, repeated field thường **nối các phần tử** từ message nguồn vào message đích. Map được gộp theo khóa: khóa mới được thêm, khóa đã tồn tại nhận giá trị từ message nguồn.

~~~java
Product current = Product.newBuilder()
    .addTags("sale")
    .putAttributes("color", "black")
    .putAttributes("layout", "US")
    .build();

Product incoming = Product.newBuilder()
    .addTags("featured")
    .putAttributes("color", "white")
    .putAttributes("material", "aluminum")
    .build();

Product merged = current.toBuilder()
    .mergeFrom(incoming)
    .build();

System.out.println(merged.getTagsList());
// [sale, featured]

System.out.println(merged.getAttributesMap());
// Có color=white, layout=US, material=aluminum.
~~~

Điều này có ý nghĩa quan trọng khi thiết kế API cập nhật:

- Nếu muốn **thêm** tag, append/merge có thể phù hợp.
- Nếu muốn **thay toàn bộ** danh sách tag, phải clear trước hoặc áp dụng quy tắc replace rõ ràng.
- Nếu muốn **xóa một khóa** map, merge một map không có khóa ấy không tự xóa giá trị cũ.
- Nếu muốn xóa map, phải gọi thao tác xóa rõ ràng trong logic builder/domain.

Đừng giả định merge message đồng nghĩa với PATCH theo nghĩa nghiệp vụ. Protobuf định nghĩa cách gộp cấu trúc; ứng dụng định nghĩa thao tác cập nhật dữ liệu.

## 10. Cập nhật repeated/map qua request gRPC

Repeated và map không có **hasXxx()** cho tập hợp. Một request chứa danh sách rỗng có thể có cùng trạng thái quan sát được như request không gửi phần tử nào. Nếu server cần phân biệt **không thay đổi** với **thay toàn bộ thành rỗng**, phải thêm ngữ nghĩa cập nhật vào hợp đồng.

### Cách 1: FieldMask và quy tắc thay thế

~~~proto
syntax = "proto3";

import "google/protobuf/field_mask.proto";

message ProductSettings {
  repeated string tags = 1;
  map<string, string> attributes = 2;
}

message UpdateProductSettingsRequest {
  string product_id = 1;
  ProductSettings settings = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

Client đặt đường dẫn **tags** trong **update_mask** để nói rằng server phải xử lý field tags. Nếu **settings.tags** rỗng và mask chứa tags, ứng dụng có thể định nghĩa là **thay danh sách hiện tại bằng danh sách rỗng**. Nếu mask không chứa tags, server giữ nguyên danh sách hiện tại.

FieldMask chỉ xác định **field nào nằm trong phạm vi cập nhật**. Server vẫn phải quy định replace hay merge cho repeated/map, xác thực đường dẫn, và xử lý trường hợp mask vắng mặt hoặc rỗng.

### Cách 2: Message lệnh với oneof

Nếu API cần phân biệt rõ replace, append và clear, có thể biểu diễn từng thao tác:

~~~proto
syntax = "proto3";

import "google/protobuf/empty.proto";

message StringList {
  repeated string values = 1;
}

message TagsMutation {
  oneof operation {
    StringList replace = 1;
    StringList append = 2;
    google.protobuf.Empty clear = 3;
  }
}

message UpdateTagsRequest {
  string product_id = 1;
  TagsMutation tags = 2;
}
~~~

Ý nghĩa:

- Không chọn nhánh operation: không có thao tác tag được yêu cầu.
- Chọn replace với values rỗng: thay danh sách bằng danh sách rỗng.
- Chọn append: thêm các phần tử vào cuối theo thứ tự.
- Chọn clear: xóa toàn bộ tag.

Vì **TagsMutation** là message field, nó có presence; **oneof** bên trong cho biết hành động được chọn. Đây là cách diễn đạt rõ ràng khi API có nhiều thao tác. Với map, có thể xây dựng message lệnh tương tự cho replace, upsert, remove keys và clear.

Không thêm **optional** trực tiếp vào repeated/map; dùng message wrapper, oneof hoặc FieldMask theo ngữ nghĩa cần biểu đạt.

## 11. Chọn repeated message thay cho map khi cần cặp dữ liệu có thứ tự

Một map không phù hợp nếu hệ thống cần lưu lịch sử thay đổi, giữ khóa trùng hoặc sắp xếp theo thứ tự do người dùng chọn.

Ví dụ cần danh sách header theo thứ tự:

~~~proto
message HeaderEntry {
  string name = 1;
  string value = 2;
}

message RequestMetadata {
  repeated HeaderEntry headers = 1;
}
~~~

Có thể có hai entry cùng name nhưng value khác nhau; thứ tự entry được giữ. Đây là điều map không biểu diễn được vì map chỉ có một giá trị hiệu lực cho mỗi khóa.

Ngược lại, nếu cấu hình có một giá trị duy nhất cho mỗi tên thuộc tính và không phụ thuộc thứ tự, **map<string, string>** đơn giản hơn và thể hiện đúng mục đích tra cứu.

Quyết định nên dựa vào **ngữ nghĩa dữ liệu**, không chỉ vào việc cấu trúc nào ngắn hơn trong file .proto.

## 12. Tương thích schema và lưu ý hiệu năng

Khi thêm repeated hoặc map field vào message đã phát hành, chọn số hiệu chưa dùng và giữ nguyên các field cũ. Client cũ thường bỏ qua field mới trên binary wire; server mới phải xử lý trường hợp collection rỗng khi nhận request từ client cũ.

Khi xóa field repeated/map đã dùng, reserve số và tên cũ để tránh tái sử dụng. Không chuyển một repeated field thành map chỉ vì muốn tra cứu thuận tiện: map có quy tắc khóa duy nhất và không bảo đảm thứ tự, nên dữ liệu cũ có phần tử trùng hoặc thứ tự có thể bị mất ý nghĩa.

Một số điểm hiệu năng:

- Repeated scalar packable trong proto3 mặc định dùng **packed encoding**, giảm số tag lặp lại cho danh sách số.
- Repeated message/string/bytes vẫn có chi phí tag và length cho từng phần tử.
- Map cần một entry message cho mỗi cặp khóa–giá trị; map lớn có chi phí cấp phát và tra cứu riêng.
- Không gửi một collection rất lớn trong một message nếu kích thước có thể vượt giới hạn message, tăng độ trễ hoặc tạo áp lực bộ nhớ. Cân nhắc phân trang hoặc streaming RPC.
- Không tối ưu số byte bằng cách dùng map/repeated sai ngữ nghĩa; dữ liệu đọc sai gây chi phí vận hành lớn hơn phần tiết kiệm.

Trong streaming gRPC, repeated field có thể gom một nhóm phần tử trong một message; server-streaming có thể gửi từng phần tử ở nhiều message riêng. Lựa chọn phụ thuộc vào kích thước, độ trễ mong muốn và khả năng xử lý dần của client.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng map khi thứ tự có ý nghĩa | Mất bảo đảm thứ tự khi serialize/parse | Dùng repeated message. |
| Dùng repeated khi khóa phải duy nhất | Ứng dụng phải tự tìm và xử lý trùng | Dùng map nếu không cần thứ tự hoặc khóa trùng. |
| Nghĩ repeated/map có **hasXxx()** | Code không biên dịch hoặc thiết kế presence sai | Kiểm tra nội dung/count; dùng wrapper/FieldMask nếu cần phân biệt thao tác. |
| Cho rằng merge repeated sẽ thay danh sách | Danh sách cũ và mới bị nối | Clear rồi add hoặc áp dụng replace semantics. |
| Cho rằng merge map sẽ xóa khóa không có trong nguồn | Khóa cũ vẫn tồn tại | Xóa khóa tường minh hoặc thay toàn bộ map. |
| Dùng map cho khóa trùng | Một giá trị ghi đè giá trị khác | Dùng repeated entry message. |
| Dựa vào thứ tự lặp qua map | Kết quả không ổn định | Sắp xếp khóa ở tầng ứng dụng nếu cần trình bày ổn định. |
| Khai báo kiểu khóa map không hợp lệ | protoc từ chối schema | Chọn kiểu số nguyên, bool hoặc string. |
| Xem collection rỗng là lệnh xóa | Có thể xóa dữ liệu ngoài ý muốn hoặc bỏ qua thao tác | Dùng FieldMask hoặc message lệnh oneof. |

## 14. Bài tập thực hành

Một dịch vụ quản lý kho cần lưu các vị trí chứa sản phẩm và thuộc tính sản phẩm:

~~~proto
message WarehouseItem {
  string sku = 1;
  repeated string warehouse_codes = 2;
  map<string, int32> quantity_by_warehouse = 3;
}
~~~

Hãy thực hiện:

1. Tạo message với **warehouse_codes = ["HN", "HCM", "HN"]**; kiểm tra số phần tử, thứ tự và phần tử trùng.
2. Tạo map với **HN = 10**, **HCM = 5**; cập nhật **HN = 12** và xác nhận map vẫn chỉ có một giá trị cho khóa HN.
3. Serialize/parse message rồi kiểm tra danh sách và map sau round-trip.
4. Dùng JsonFormat để quan sát repeated thành array và map thành object.
5. Thực hiện **mergeFrom()** với message có thêm warehouse code và map cập nhật HN; giải thích vì sao danh sách nối thêm nhưng map thay giá trị theo khóa.
6. Thiết kế request cập nhật phân biệt **không thay đổi warehouse_codes**, **thay danh sách bằng rỗng**, và **thêm một mã kho**.
7. Giải thích vì sao **map<string, int32>** không thể lưu hai giá trị độc lập cho cùng khóa HN và khi nào nên thay bằng repeated message.

**Tiêu chí hoàn thành:** chọn đúng cấu trúc theo thứ tự/khóa, sử dụng đúng builder Java, dự đoán được merge semantics và thiết kế được lệnh cập nhật collection rõ ràng.

## 15. Ghi nhớ

- **repeated** là danh sách có thứ tự, cho phép phần tử trùng; **map** là tập hợp khóa–giá trị, không bảo đảm thứ tự và mỗi khóa có một giá trị hiệu lực.
- Repeated/map mặc định là rỗng và **không có explicit presence** cho cả collection.
- Java dùng **add/addAll/getList** cho repeated và **put/putAll/remove/getMap** cho map.
- ProtoJSON biểu diễn repeated thành **array**, map thành **object**; không dựa vào thứ tự của object.
- **mergeFrom()** thường nối repeated và gộp map theo khóa; không mặc nhiên thực hiện thao tác replace/clear nghiệp vụ.
- Khi cần phân biệt không đổi với thay collection thành rỗng, dùng **FieldMask**, message wrapper hoặc **oneof** diễn đạt hành động.

Chọn đúng repeated và map giúp hợp đồng Protocol Buffers phản ánh chính xác cấu trúc dữ liệu, giữ được thứ tự khi cần, tránh mất khóa và hỗ trợ ứng dụng Spring gRPC xử lý collection hiệu quả trong cả unary lẫn streaming RPC.
