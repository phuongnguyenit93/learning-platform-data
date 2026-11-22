# Đọc vị trí và đường dẫn thuộc tính trong thông tin lỗi

Khi Jackson deserialize JSON thành object Java, lỗi có thể xảy ra sâu bên trong cấu trúc lồng nhau. Một request có thể chứa danh sách đơn hàng, mỗi đơn có địa chỉ và nhiều dòng hàng; một giá trị ở property cuối cùng lại không thể chuyển thành kiểu Java đích. Thông báo “Cannot deserialize value” cho biết phép chuyển đổi thất bại, nhưng chưa đủ để tìm đúng record và field trong payload.

Jackson lưu đường dẫn đi qua object graph trong các exception thuộc databind. Với JsonMappingException, có thể đọc đường dẫn bằng getPath() hoặc getPathReference(), đồng thời lấy thông báo gốc bằng getOriginalMessage(). Đường dẫn thuộc tính khác với vị trí cú pháp trong input: JsonLocation cho biết dòng, cột hoặc offset byte/ký tự; property path cho biết field và index trong cấu trúc đang được ánh xạ.

Bài này trình bày cách đọc hai loại thông tin đó, diễn giải path của nested DTO, list và map, xử lý lỗi unknown property và custom deserializer, rồi chuẩn hóa chúng thành thông báo hữu ích cho log hoặc API.

## 1. Vì sao cần đọc property path?

Xét các DTO:

~~~java
public class OrderRequest {
    private String orderId;
    private Customer customer;
    private List<OrderLine> lines;

    // Getter và setter
}

public class Customer {
    private String name;
    private Address address;

    // Getter và setter
}

public class Address {
    private String city;
    private Integer postalCode;

    // Getter và setter
}

public class OrderLine {
    private String sku;
    private Integer quantity;

    // Getter và setter
}
~~~

Payload có thể chứa lỗi ở nhiều cấp:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "name": "An",
    "address": {
      "city": "Ho Chi Minh City",
      "postalCode": "not-a-number"
    }
  },
  "lines": [
    {
      "sku": "SKU-1",
      "quantity": 2
    },
    {
      "sku": "SKU-2",
      "quantity": "many"
    }
  ]
}
~~~

Hai giá trị không hợp lệ nằm ở:

- customer.address.postalCode
- lines[1].quantity

Nếu chỉ nhìn class đích hoặc dòng JSON, người xử lý phải tự tìm trong payload. Property path cho phép Jackson mô tả nhánh đang deserialize khi exception phát sinh.

Thông tin path hữu ích cho log và điều tra payload lỗi, trả lỗi binding cho API client, xác định index của phần tử lỗi trong batch, theo dõi lỗi từ custom deserializer và phân biệt nhiều field cùng kiểu dữ liệu.

## 2. JsonMappingException lưu những thông tin nào?

JsonMappingException là exception nền quan trọng trong Jackson Databind. Nhiều lỗi ánh xạ như sai kiểu dữ liệu, property không biết hoặc không thể tạo object được biểu diễn bằng lớp này hoặc lớp con của nó.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| getMessage() | Thông báo đầy đủ; thường bao gồm path nếu Jackson đã gắn path |
| getOriginalMessage() | Thông báo gốc trước phần path được nối thêm |
| getPath() | Danh sách các segment của đường dẫn |
| getPathReference() | Đường dẫn ở dạng chuỗi để log hoặc hiển thị |
| getLocation() | Vị trí parser trong input, nếu có |
| getProcessor() | Parser hoặc generator liên quan đến lỗi, nếu có |

Ví dụ:

~~~java
try {
    OrderRequest request = mapper.readValue(json, OrderRequest.class);
} catch (JsonMappingException ex) {
    System.err.println(ex.getOriginalMessage());
    System.err.println(ex.getPathReference());
}
~~~

Thông báo gốc trả lời “Jackson không thể làm gì?”. Path trả lời “lỗi xảy ra khi đang đi qua nhánh nào?”. Nên giữ cả hai thông tin thay vì chỉ log một chuỗi message đã ghép.

### 2.1. getMessage() và getOriginalMessage()

getMessage() có thể chứa phần path do Jackson thêm vào, thường có dạng “through reference chain”. Ví dụ minh họa:

~~~text
Cannot deserialize value of type java.lang.Integer from String "many":
not a valid Integer value
 at [Source: ...; line: 15, column: 19]
 (through reference chain:
 com.example.OrderRequest["lines"]->java.util.ArrayList[1]->
 com.example.OrderLine["quantity"])
~~~

Định dạng cụ thể phụ thuộc phiên bản Jackson, parser và kiểu container. Không nên viết code parse chuỗi getMessage() để trích path vì message là văn bản dành cho chẩn đoán và có thể thay đổi.

getOriginalMessage() giúp lấy phần mô tả lỗi mà không cần tự loại bỏ đoạn path ở cuối:

~~~java
String message = ex.getOriginalMessage();
String path = ex.getPathReference();
~~~

### 2.2. getPath() trả về dữ liệu có cấu trúc

Nếu cần xử lý từng segment, dùng getPath():

~~~java
List<JsonMappingException.Reference> path = ex.getPath();

for (JsonMappingException.Reference reference : path) {
    System.out.println(reference.getDescription());
}
~~~

Mỗi Reference mô tả một bước trong đường dẫn, chẳng hạn property name hoặc array/list index. Cách này tốt hơn việc phân tích chuỗi path vì code có thể phân biệt field và index bằng API.

## 3. JsonMappingException.Reference: từng segment của đường dẫn

Một path thường đi qua nhiều loại thành phần:

- Một property của bean.
- Một phần tử ở index cụ thể trong array hoặc collection.
- Một entry trong map.
- Một object lồng nhau khác.

Jackson biểu diễn từng bước bằng JsonMappingException.Reference.

Các phương thức hữu ích:

| Phương thức | Ý nghĩa |
|---|---|
| getFrom() | Object hoặc class làm điểm xuất phát của segment |
| getFieldName() | Tên property nếu segment là field; có thể null nếu là index |
| getIndex() | Index nếu segment là phần tử; thường là -1 nếu không phải index |
| getDescription() | Mô tả segment dưới dạng chuỗi |
| toString() | Biểu diễn văn bản của reference |

Ví dụ đọc từng segment:

~~~java
for (JsonMappingException.Reference ref : ex.getPath()) {
    String fieldName = ref.getFieldName();
    int index = ref.getIndex();
    Object from = ref.getFrom();

    if (fieldName != null) {
        System.out.println("Field: " + fieldName);
    } else if (index >= 0) {
        System.out.println("Index: " + index);
    }

    if (from != null) {
        System.out.println("From: " + from.getClass().getName());
    }
}
~~~

Không phải segment nào cũng có cả field name và index. Với property, thường có field name; với phần tử collection, thường có index. Hãy kiểm tra null và giá trị âm trước khi sử dụng.

### 3.1. getFrom() là object nguồn của segment

getFrom() giúp xác định segment thuộc object hoặc kiểu nào. Tùy thời điểm Jackson ghi nhận path, giá trị này có thể là instance bean, class hoặc container liên quan. Không nên giả định nó luôn là instance đầy đủ đã được tạo xong.

Nếu chỉ cần log, class name thường đủ:

~~~java
Object from = ref.getFrom();

String sourceType;
if (from == null) {
    sourceType = "<unknown>";
} else if (from instanceof Class<?> type) {
    sourceType = type.getName();
} else {
    sourceType = from.getClass().getName();
}
~~~

Không nên gọi toString() trên toàn bộ object nguồn để ghi log; object có thể chứa dữ liệu nhạy cảm hoặc tạo chuỗi rất lớn.

## 4. Đọc path của object lồng nhau

Với payload có nhánh:

~~~json
{
  "customer": {
    "address": {
      "postalCode": "not-a-number"
    }
  }
}
~~~

Nếu postalCode là Integer, Jackson có thể phát sinh lỗi chuyển đổi. Path logic đi qua:

~~~text
OrderRequest
  -> customer
  -> address
  -> postalCode
~~~

Một path reference hiển thị có thể gần giống:

~~~text
com.example.OrderRequest["customer"]->
com.example.Customer["address"]->
com.example.Address["postalCode"]
~~~

Đây là ví dụ minh họa; không nên phụ thuộc chính xác dấu phân cách hoặc tên class trong chuỗi hiển thị. Để xử lý máy móc, đọc getPath().

### 4.1. Chuyển path thành danh sách field

Có thể viết helper chỉ lấy tên field:

~~~java
static List<String> fieldNames(JsonMappingException exception) {
    List<String> names = new ArrayList<>();

    for (JsonMappingException.Reference ref : exception.getPath()) {
        if (ref.getFieldName() != null) {
            names.add(ref.getFieldName());
        }
    }

    return names;
}
~~~

Với path của ví dụ trên, danh sách có thể là:

~~~text
["customer", "address", "postalCode"]
~~~

Helper này bỏ qua index. Nếu payload có collection, nên giữ cả field và index thay vì chỉ nối tên property.

### 4.2. Không phải lỗi nào cũng có path đầy đủ

Path chỉ có những segment Jackson có thể xác định trong quá trình databinding. Lỗi parser xảy ra trước khi Jackson biết object/property đích có thể chỉ có location mà không có property path. Lỗi cấu hình kiểu hoặc lỗi khởi tạo serializer/deserializer cũng có thể không có path giống lỗi binding của một field.

Vì vậy, code chẩn đoán nên chấp nhận path rỗng. Không coi path rỗng là lỗi của helper.

## 5. Đọc index của array và collection

Với JSON array:

~~~json
{
  "lines": [
    {"sku": "SKU-1", "quantity": 2},
    {"sku": "SKU-2", "quantity": "many"}
  ]
}
~~~

Path logic của giá trị lỗi:

~~~text
OrderRequest
  -> lines
  -> element at index 1
  -> quantity
~~~

Đường dẫn chuỗi có thể hiển thị:

~~~text
OrderRequest["lines"]->ArrayList[1]->OrderLine["quantity"]
~~~

Đọc index bằng getIndex():

~~~java
for (JsonMappingException.Reference ref : ex.getPath()) {
    if (ref.getIndex() >= 0) {
        System.out.println("Invalid element index: " + ref.getIndex());
    }
}
~~~

Index thường bắt đầu từ 0. Nếu API hiển thị cho người dùng cuối theo thứ tự đếm từ 1, chỉ đổi ở tầng trình bày; giữ index gốc trong log để dễ đối chiếu với JSON và code.

### 5.1. Mảng lồng nhau

Với cấu trúc:

~~~json
{
  "batches": [
    {
      "items": [
        {"code": "A"},
        {"code": 123}
      ]
    }
  ]
}
~~~

Path có thể đi qua nhiều segment:

~~~text
batches -> index 0 -> items -> index 1 -> code
~~~

Không nên chỉ lấy index đầu tiên hoặc cuối cùng. Một đường dẫn có thể chứa nhiều index ở các cấp collection khác nhau.

## 6. Đọc path của Map

Map có key động nên path có thể chứa key thay vì tên property được khai báo trong class.

Ví dụ:

~~~json
{
  "prices": {
    "SKU-1": 100,
    "SKU-2": "invalid"
  }
}
~~~

Nếu kiểu đích là Map<String, Integer>, lỗi có thể nằm tại value của key SKU-2. Đường dẫn hiển thị tùy Jackson version có thể mô tả map cùng key hoặc phần tử liên quan.

Map key khác list index:

- Index là vị trí số trong array/collection.
- Key là giá trị định danh entry trong map.
- Tên property là một field được khai báo trong object bean.

Không nên ép mọi segment thành fieldName. Với map, API path có thể dùng mô tả container/key mà không có một field name JavaBean tương ứng. Hãy giữ getDescription() cho chẩn đoán hoặc dùng getPathReference() khi cần chuỗi tổng hợp.

## 7. Path của lỗi unknown property

Một trường hợp phổ biến là JSON có field mà DTO không khai báo:

~~~json
{
  "id": "U-100",
  "displayName": "An",
  "adress": {
    "city": "HCMC"
  }
}
~~~

Ở đây, adress có thể là lỗi đánh máy của address. Nếu FAIL_ON_UNKNOWN_PROPERTIES bật, Jackson có thể ném UnrecognizedPropertyException.

Ví dụ:

~~~java
try {
    User user = mapper.readValue(json, User.class);
} catch (UnrecognizedPropertyException ex) {
    System.out.println("Unknown property: " + ex.getPropertyName());
    System.out.println("Path: " + ex.getPathReference());
    System.out.println("Known properties: " + ex.getKnownPropertyIds());
}
~~~

UnrecognizedPropertyException cung cấp thêm:

- getPropertyName(): tên property không được nhận diện.
- getKnownPropertyIds(): tập các property mà Jackson biết tại object đó.
- Path kế thừa từ JsonMappingException: nhánh dẫn tới object có field lạ.

Với object lồng nhau, path giúp xác định field lạ nằm trong object nào. Ví dụ customer.adress khác với shippingAddress.adress, dù cả hai đều có key sai chính tả.

### 7.1. Unknown property và FAIL_ON_UNKNOWN_PROPERTIES

Nếu tắt:

~~~java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Jackson thường bỏ qua property không biết thay vì ném UnrecognizedPropertyException. Khi đó sẽ không có lỗi path cho field đó vì lỗi đã không được xem là lỗi.

Nếu cần giữ field mở rộng, có thể dùng @JsonAnySetter hoặc JsonNode. Chọn policy dựa trên hợp đồng: strict để phát hiện producer sai schema, tolerant để tương thích field mới, preserve để chuyển tiếp dữ liệu chưa biết.

## 8. Path khác với JsonLocation

Đây là hai loại thông tin dễ bị nhầm.

| Thông tin | Trả lời câu hỏi | API |
|---|---|---|
| Property path | Lỗi xảy ra trong property/index nào của object graph? | JsonMappingException.getPath(), getPathReference() |
| Parser location | Parser đang ở dòng, cột hoặc offset nào trong input? | JsonProcessingException.getLocation() / JsonLocation |

Ví dụ path:

~~~text
OrderRequest["lines"]->ArrayList[1]->OrderLine["quantity"]
~~~

Ví dụ location:

~~~text
line: 14, column: 22
byte offset: 318
~~~

Path giúp tìm property trong mô hình dữ liệu. Location giúp tìm vùng ký tự trong file hoặc request body.

### 8.1. Đọc JsonLocation

~~~java
JsonLocation location = ex.getLocation();

if (location != null) {
    System.out.println("Line: " + location.getLineNr());
    System.out.println("Column: " + location.getColumnNr());
    System.out.println("Byte offset: " + location.getByteOffset());
    System.out.println("Char offset: " + location.getCharOffset());
}
~~~

Một số nguồn input không cung cấp đầy đủ mọi offset. Giá trị offset có thể không xác định tùy parser/source. Vì vậy, đừng giả định byte offset luôn có sẵn hoặc luôn trùng với character offset.

### 8.2. Vì sao path và location không thay thế nhau?

Một property có thể trải qua nhiều token và parser location chỉ trỏ đến token nơi lỗi được phát hiện. Ngược lại, lỗi do constructor hoặc custom validation có thể có path nhưng không có một vị trí token chính xác.

Trong log tốt, thường lưu cả loại exception, original message, property path, line/column hoặc byte offset nếu có, và correlation ID của request hoặc record.

## 9. Phân biệt các loại exception khi chẩn đoán

Không phải mọi lỗi Jackson đều có cùng ý nghĩa.

| Exception | Ý nghĩa thường gặp | Thông tin nên xem |
|---|---|---|
| JsonParseException | JSON sai cú pháp/token không hợp lệ | getLocation(), message |
| MismatchedInputException | Input shape/token không phù hợp kiểu đích | Path, location, target type |
| InvalidFormatException | Giá trị có format không chuyển được sang kiểu đích | Path, value, target type |
| UnrecognizedPropertyException | JSON có property không được nhận diện | Property name, known IDs, path |
| InvalidDefinitionException | Cấu hình/model không thể được Jackson xử lý | Message, target type; path có thể không có |
| JsonMappingException | Lỗi databinding tổng quát | Original message, path, location |

### 9.1. MismatchedInputException

Ví dụ field cần object nhưng input là string:

~~~json
{
  "customer": "An"
}
~~~

Nếu property customer có kiểu Customer, Jackson có thể ném MismatchedInputException. Path chỉ ra property đang được binding.

### 9.2. InvalidFormatException

Ví dụ:

~~~json
{
  "age": "twenty"
}
~~~

Nếu age là integer, Jackson có thể ném InvalidFormatException. Có thể lấy giá trị lỗi và kiểu đích:

~~~java
catch (InvalidFormatException ex) {
    Object rejectedValue = ex.getValue();
    Class<?> targetType = ex.getTargetType();

    log.error(
            "Invalid value at {} for target {}",
            ex.getPathReference(),
            targetType.getName()
    );
}
~~~

Tránh log rejectedValue nếu có khả năng chứa token, mật khẩu hoặc dữ liệu cá nhân. Giá trị lỗi hữu ích cho debug nhưng cần tuân thủ chính sách bảo vệ dữ liệu.

### 9.3. JsonParseException

JSON sai cú pháp, ví dụ thiếu dấu nháy hoặc dấu ngoặc, thường phát sinh ở parser layer:

~~~json
{
  "name": "An,
  "age": 20
}
~~~

Ở giai đoạn này, Jackson có thể chưa xác định được một bean property cụ thể để tạo path. Hãy đọc location và thông báo parser trước. Không nên kết luận path rỗng nghĩa là JSON sai ở root; parser có thể dừng trước khi databinding bắt đầu.

### 9.4. InvalidDefinitionException

Ví dụ class đích không có constructor phù hợp hoặc cấu hình serializer/deserializer không hợp lệ. Đây thường là lỗi model/configuration của ứng dụng hơn là dữ liệu JSON do client gửi sai.

Không nên trả mọi JsonMappingException thành HTTP 400 mà không phân loại. Một lỗi cấu hình server có thể cần xử lý như lỗi nội bộ thay vì báo client sửa payload.

## 10. Xây dựng helper trích path có cấu trúc

Một helper có thể trả về danh sách segment mà không phụ thuộc định dạng chuỗi hiển thị:

~~~java
public record PathSegment(
        String fieldName,
        Integer index,
        String description,
        String sourceType
) {
}

public static List<PathSegment> extractPath(
        JsonMappingException exception
) {
    List<PathSegment> result = new ArrayList<>();

    for (JsonMappingException.Reference ref : exception.getPath()) {
        Object from = ref.getFrom();

        String sourceType = null;
        if (from instanceof Class<?> type) {
            sourceType = type.getName();
        } else if (from != null) {
            sourceType = from.getClass().getName();
        }

        Integer index = ref.getIndex() >= 0
                ? ref.getIndex()
                : null;

        result.add(new PathSegment(
                ref.getFieldName(),
                index,
                ref.getDescription(),
                sourceType
        ));
    }

    return result;
}
~~~

Ví dụ các segment logic:

| Thứ tự | Field | Index | Source type minh họa |
|---:|---|---:|---|
| 1 | lines | — | com.example.OrderRequest |
| 2 | — | 1 | java.util.ArrayList |
| 3 | quantity | — | com.example.OrderLine |

Đây là dạng minh họa. Nội dung description và sourceType phụ thuộc kiểu thực tế và phiên bản Jackson. Nếu cần schema ổn định cho API, nên tự định nghĩa cấu trúc segment của ứng dụng từ fieldName và index, không trả nguyên toString() của Jackson như một contract lâu dài.

### 10.1. Tạo path dạng dot/bracket notation

Một chuỗi dễ đọc có thể dùng quy ước:

~~~text
lines[1].quantity
~~~

Helper:

~~~java
public static String toSimplePath(JsonMappingException exception) {
    StringBuilder path = new StringBuilder();

    for (JsonMappingException.Reference ref : exception.getPath()) {
        if (ref.getFieldName() != null) {
            if (path.length() > 0) {
                path.append('.');
            }
            path.append(ref.getFieldName());
        } else if (ref.getIndex() >= 0) {
            path.append('[').append(ref.getIndex()).append(']');
        } else {
            if (path.length() > 0) {
                path.append('.');
            }
            path.append(ref.getDescription());
        }
    }

    return path.toString();
}
~~~

Helper trên là định dạng phục vụ log/UI. Nó không phải cú pháp JSON Pointer hay JSONPath. Nếu tên field chứa dấu chấm hoặc dấu ngoặc vuông, dot notation có thể mơ hồ. Với tên field tùy ý, nên trả segment array có cấu trúc hoặc dùng JSON Pointer với quy tắc escape phù hợp.

## 11. Gắn path khi viết custom deserializer

Khi viết custom deserializer, hãy tạo lỗi mapping có liên hệ với parser:

~~~java
if (parser.currentToken() != JsonToken.VALUE_STRING) {
    throw JsonMappingException.from(
            parser,
            "code phải là JSON string"
    );
}
~~~

Khi lỗi đi qua bean deserializer, Jackson thường bổ sung path của property đang gọi custom deserializer. Nếu custom deserializer được dùng ở order.customer.code, path bên ngoài có thể được thêm khi exception truyền ngược qua các lớp binding.

### 11.1. Dùng handleUnexpectedToken khi token sai

~~~java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
    return (Integer) context.handleUnexpectedToken(
            Integer.class,
            parser
    );
}
~~~

API này cho phép Jackson tạo lỗi mismatch theo ngữ cảnh target type. Nếu cần message nghiệp vụ cụ thể, có thể tạo JsonMappingException từ parser.

### 11.2. Giữ nguyên cause và path khi wrap exception

Nếu bắt exception từ thư viện parse bên ngoài, có thể wrap thành mapping exception:

~~~java
try {
    return parseDomainValue(parser.getText());
} catch (IllegalArgumentException ex) {
    throw JsonMappingException.from(
            parser,
            "Giá trị không hợp lệ cho DomainValue",
            ex
    );
}
~~~

Không nên tạo một exception mới chỉ từ ex.getMessage() rồi bỏ cause. Giữ cause giúp log và điều tra nguyên nhân sâu hơn. Cũng không nên bắt JsonMappingException rồi thay bằng exception mới không giữ path đã có.

### 11.3. Không tự gắn path trùng lặp

Trong đa số custom deserializer được gọi thông qua property databinding, Jackson sẽ gắn context path khi exception được truyền ra ngoài. Không nên tự gọi wrapWithPath() cho cùng property nếu framework đã gắn segment đó; kết quả có thể lặp field trong đường dẫn.

Nếu tự parse một cấu trúc ngoài bean binding hoặc tự gọi deserializer lồng nhau, cần hiểu rõ exception path hiện tại trước khi thêm segment. JsonMappingException.wrapWithPath(...) và prependPath(...) là API thấp hơn, chỉ nên dùng khi ứng dụng thực sự chịu trách nhiệm quản lý path.

## 12. Path của lỗi trong nested collection và map

Ví dụ một request có nhiều cấp:

~~~json
{
  "warehouse": {
    "bins": [
      {
        "products": {
          "SKU-1": {
            "quantity": 4
          },
          "SKU-2": {
            "quantity": "unknown"
          }
        }
      }
    ]
  }
}
~~~

Path logic của lỗi:

~~~text
warehouse -> bins -> index 0 -> products -> key SKU-2 -> quantity
~~~

Đây là lý do nên giữ path dạng danh sách segment thay vì chỉ một field cuối. Nếu chỉ log quantity, sẽ không biết nó thuộc sản phẩm nào và kho nào.

Khi xử lý map, tên key có thể do người dùng hoặc hệ thống ngoài cung cấp. Trước khi đưa key vào log/UI, hãy giới hạn độ dài và escape ký tự điều khiển để tránh log injection. Không nên giả định key luôn là một tên field Java hợp lệ.

## 13. Root collection và batch record

Nếu JSON root là array:

~~~json
[
  {"id": "A-1", "amount": 100},
  {"id": "A-2", "amount": "bad"},
  {"id": "A-3", "amount": 300}
]
~~~

Đọc vào:

~~~java
List<Payment> payments = mapper.readValue(
        json,
        new TypeReference<List<Payment>>() {}
);
~~~

Lỗi ở phần tử thứ hai có thể có path chứa index 1. Path giúp xác định vị trí phần tử trong batch.

Nếu đọc JSON Lines và parse từng dòng riêng, index trong root list không còn là số dòng của file. Khi đó cần lưu thêm line number ở tầng framing:

~~~java
long lineNumber = 0;

while ((line = reader.readLine()) != null) {
    lineNumber++;

    try {
        Event event = objectReader.readValue(line);
        process(event);
    } catch (JsonMappingException ex) {
        log.error(
                "Invalid record at line {}, path {}",
                lineNumber,
                ex.getPathReference()
        );
    }
}
~~~

Property path và record number bổ sung cho nhau: line number định vị record trong stream; path định vị field trong record.

## 14. Path trong lỗi constructor và creator property

Khi Jackson dùng @JsonCreator hoặc constructor để tạo immutable object, lỗi có thể xảy ra khi binding một tham số constructor.

Ví dụ:

~~~java
public final class Customer {
    private final String id;
    private final Integer age;

    @JsonCreator
    public Customer(
            @JsonProperty("id") String id,
            @JsonProperty("age") Integer age
    ) {
        this.id = id;
        this.age = age;
    }
}
~~~

Nếu age không thể chuyển đổi, path có thể tham chiếu property/creator parameter age. Nếu constructor tự ném exception do invariant, Jackson có thể biểu diễn lỗi thông qua exception mapping của creator và path có thể chỉ đến object hoặc parameter liên quan tùy điểm phát sinh.

Đừng giả định mọi lỗi trong constructor sẽ có cùng path chi tiết như setter-based binding. Với lỗi do invariant domain, có thể tốt hơn khi validate riêng sau deserialize hoặc tạo exception domain có field path của ứng dụng.

## 15. Property path của Jackson khác path của Bean Validation

Jackson path mô tả nơi lỗi xảy ra trong quá trình parse/bind JSON. Bean Validation mô tả constraint vi phạm sau khi object đã được tạo hoặc trong quá trình validate.

Ví dụ:

~~~java
public class UserRequest {
    @NotBlank
    private String email;

    @Min(18)
    private int age;
}
~~~

JSON:

~~~json
{
  "email": "",
  "age": 15
}
~~~

Jackson có thể deserialize thành công vì cả hai giá trị đều đúng kiểu. Sau đó Bean Validation mới báo email vi phạm @NotBlank và age vi phạm @Min(18).

Với Bean Validation, đọc path từ ConstraintViolation.getPropertyPath(), không phải JsonMappingException.getPath().

| Tình huống | Nguồn path |
|---|---|
| String không chuyển được sang Integer | Jackson JsonMappingException |
| Unknown JSON property | Jackson UnrecognizedPropertyException |
| JSON sai cú pháp | Parser location; có thể không có bean path |
| Email rỗng vi phạm @NotBlank | Bean Validation ConstraintViolation.getPropertyPath() |
| Quy tắc nghiệp vụ trong service không hợp lệ | Domain/application error path do ứng dụng định nghĩa |

Một API có thể chuẩn hóa các lỗi này về cùng một response schema, nhưng nên giữ nguồn và loại lỗi bên trong để không nhầm lỗi dữ liệu đầu vào với lỗi cấu hình hoặc nghiệp vụ.

## 16. Xử lý path khi tạo response lỗi API

Không nên trả nguyên stack trace hoặc toàn bộ exception message cho client. Thay vào đó, có thể chuẩn hóa lỗi thành cấu trúc:

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "Dữ liệu gửi lên không hợp lệ",
  "errors": [
    {
      "path": "lines[1].quantity",
      "message": "Giá trị phải là số nguyên"
    }
  ]
}
~~~

Ở tầng API:

1. Bắt các exception Jackson thuộc nhóm input mapping.
2. Lấy getOriginalMessage() hoặc map exception subtype sang thông báo an toàn.
3. Lấy path có cấu trúc từ getPath().
4. Chuyển sang định dạng path của API.
5. Không trả class name nội bộ, stack trace hoặc raw value nhạy cảm.
6. Giữ correlation ID để liên kết với log server.

Ví dụ minh họa:

~~~java
@ExceptionHandler(JsonMappingException.class)
public ResponseEntity<ApiError> handleJsonMapping(
        JsonMappingException exception
) {
    String path = toSimplePath(exception);

    ApiError body = new ApiError(
            "INVALID_REQUEST",
            "Dữ liệu tại " + path + " không hợp lệ"
    );

    return ResponseEntity.badRequest().body(body);
}
~~~

Đây là ví dụ Spring MVC ở mức ý tưởng. Trong ứng dụng thực tế, cần phân loại exception trước khi trả 400: InvalidDefinitionException có thể là lỗi cấu hình server; một số lỗi parser cũng có thể đến từ request bị truncate; và lỗi validation không thuộc JsonMappingException.

### 16.1. Tránh trả thông tin nội bộ

Không trả trực tiếp tên package/class nội bộ nếu không cần, stack trace, raw JSON có token hoặc thông tin cá nhân, giá trị bị từ chối nếu chứa bí mật, đường dẫn file hoặc thông tin source parser nội bộ.

Path dạng customer.address.postalCode thường đủ hữu ích cho client. Log nội bộ có thể giữ thêm exception type, location, source type và correlation ID.

## 17. Ghi log chẩn đoán có cấu trúc

Thay vì ghi toàn bộ getMessage() vào một chuỗi, có thể log các field riêng:

~~~java
catch (JsonMappingException ex) {
    JsonLocation location = ex.getLocation();

    log.warn(
            "JSON mapping failed: exceptionType={}, message={}, path={}, line={}, column={}",
            ex.getClass().getSimpleName(),
            ex.getOriginalMessage(),
            ex.getPathReference(),
            location == null ? null : location.getLineNr(),
            location == null ? null : location.getColumnNr()
    );

    throw ex;
}
~~~

Lợi ích:

- Có thể tìm kiếm theo exception type.
- Có thể gom metric theo path hoặc field.
- Dễ phân biệt lỗi ở property với lỗi cú pháp.
- Có thể ẩn hoặc mask một số giá trị riêng biệt.
- Tránh parse message text trong hệ thống log analytics.

Nếu path chứa tên key do người dùng kiểm soát, cần giới hạn độ dài và escape newline/control character trước khi log. Điều này giảm nguy cơ log injection và log quá lớn.

## 18. Path và vị trí trong streaming parser

Khi dùng JsonParser trực tiếp, ứng dụng có thể không có đầy đủ bean path vì không có databinding context tạo property reference tự động.

Ví dụ:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    while (parser.nextToken() != null) {
        // Ứng dụng tự điều khiển token
    }
}
~~~

Parser vẫn cung cấp vị trí hiện tại qua currentLocation() hoặc getCurrentLocation() tùy API/version, nhưng đó là vị trí trong input. Nếu tự viết logic duyệt token, ứng dụng phải tự theo dõi field name, array index và path nếu muốn thông báo lỗi theo cấu trúc.

Trong databinding, Jackson biết property đang được gán và có thể bổ sung path. Trong streaming thuần, parser chỉ biết token và vị trí; path nghiệp vụ là trách nhiệm của code xử lý.

Một chiến lược trung gian là đọc một nhánh thành JsonNode, rồi chuyển nhánh đó thành DTO bằng treeToValue(). Khi lỗi xảy ra trong conversion, Jackson có thể cung cấp path tương ứng với phần tree được chuyển, nhưng ứng dụng vẫn nên giữ path ngoài của nhánh đó nếu đã tách payload từ root.

## 19. Các giới hạn khi diễn giải property path

Một vài lưu ý giúp tránh kết luận sai:

- Path không phải JSONPath chuẩn. getPathReference() là định dạng hiển thị của Jackson; không coi nó là cú pháp query ổn định cho hệ thống khác.
- Path có thể rỗng hoặc chưa đầy đủ. Parser error, lỗi cấu hình và lỗi xảy ra trước khi binding property có thể không có path.
- Tên class/container có thể xuất hiện. Chuỗi path có thể chứa class name hoặc loại collection, không chỉ tên field.
- Map key không giống bean property. Path của map có thể mô tả key/container theo cách riêng.
- Path không phải line number. Dùng JsonLocation để biết dòng/cột.
- Path không phải validation path. Bean Validation có API path riêng.
- Không parse chuỗi message để lấy field. Dùng getPath() và Reference.
- Không phụ thuộc chính xác format path text. Có thể thay đổi theo phiên bản hoặc kiểu nguồn.
- Path không chứng minh payload sai nghiệp vụ. Nó chỉ chỉ ra vị trí Jackson gặp lỗi mapping.

## 20. Kiểm thử property path

Nên test path ở mức API công khai mà ứng dụng dựa vào, thay vì so sánh toàn bộ message string vốn dễ thay đổi theo phiên bản.

Ví dụ:

~~~java
@Test
void shouldExposeNestedPropertyPath() {
    String json = """
            {
              "lines": [
                {"sku": "SKU-1", "quantity": 2},
                {"sku": "SKU-2", "quantity": "many"}
              ]
            }
            """;

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, OrderRequest.class)
    );

    assertFalse(exception.getPath().isEmpty());

    List<String> fields = exception.getPath().stream()
            .map(JsonMappingException.Reference::getFieldName)
            .filter(Objects::nonNull)
            .toList();

    assertTrue(fields.contains("lines"));
    assertTrue(fields.contains("quantity"));

    assertTrue(
            exception.getPath().stream()
                    .anyMatch(ref -> ref.getIndex() == 1)
    );
}
~~~

Test kiểm tra các segment quan trọng mà không phụ thuộc toàn bộ chuỗi class name hoặc dấu phân cách.

### 20.1. Kiểm thử location riêng

Nếu parser source là String hoặc byte array, location có thể cung cấp line/column. Test location nên kiểm tra giá trị trong đúng parser/version và không nên dùng byte offset như character offset.

### 20.2. Kiểm thử unknown property

~~~java
@Test
void shouldExposeUnknownPropertyNameAndPath() {
    UnrecognizedPropertyException exception = assertThrows(
            UnrecognizedPropertyException.class,
            () -> mapper.readValue(
                    """
                    {
                      "customer": {
                        "adress": {}
                      }
                    }
                    """,
                    OrderRequest.class
            )
    );

    assertEquals("adress", exception.getPropertyName());
    assertFalse(exception.getPath().isEmpty());
}
~~~

Test này giả định mapper bật FAIL_ON_UNKNOWN_PROPERTIES. Nếu cấu hình ứng dụng bỏ qua field lạ, exception sẽ không được phát sinh.

## 21. Quy trình chẩn đoán một lỗi Jackson

Khi nhận exception từ readValue(), có thể theo trình tự:

1. Xác định loại exception: parser, mapping, format, unknown property hay definition/configuration.
2. Lấy original message: dùng getOriginalMessage() để biết lỗi gốc.
3. Đọc property path: dùng getPath() hoặc getPathReference().
4. Đọc segment: field name, index, source type và description.
5. Đọc parser location: line, column, byte/char offset nếu có.
6. Xác định tầng lỗi: JSON syntax, coercion, bean construction, custom deserializer hay validation.
7. Đối chiếu payload và DTO: kiểm tra token thực tế ở path đó so với kiểu đích.
8. Chuẩn hóa thông báo: tạo lỗi API an toàn, giữ log nội bộ có cấu trúc.
9. Kiểm thử regression: tạo test cho payload sai và xác nhận path hữu ích vẫn được giữ.

## 22. Kết luận

Property path của Jackson cho biết đường đi trong object graph dẫn tới lỗi mapping. JsonMappingException.getPath() cung cấp các segment có cấu trúc qua Reference; getPathReference() tạo chuỗi dễ đọc; getOriginalMessage() lấy thông báo lỗi gốc. Với từng segment, getFieldName(), getIndex(), getFrom() và getDescription() giúp xác định field, vị trí collection và kiểu nguồn.

Path khác với JsonLocation: path xác định property/index trong mô hình Java, còn location xác định dòng/cột/offset trong input. Unknown property, sai kiểu và lỗi custom deserializer thường có thể mang path; lỗi cú pháp parser hoặc lỗi cấu hình có thể không có. Hãy đọc exception theo API có cấu trúc, không parse chuỗi message, đồng thời phân biệt lỗi Jackson với Bean Validation. Khi log và trả lỗi API, chỉ phát thông tin cần thiết, tránh raw payload nhạy cảm và giữ correlation ID để truy vết.

## Tài liệu tham khảo

- [Jackson Databind — JsonMappingException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonMappingException.html)
- [Jackson Databind — JsonMappingException.Reference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonMappingException.Reference.html)
- [Jackson Core — JsonProcessingException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonProcessingException.html)
- [Jackson Core — JsonLocation API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonLocation.html)
- [Jackson Databind — UnrecognizedPropertyException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/exc/UnrecognizedPropertyException.html)
- [Jackson Databind — MismatchedInputException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/exc/MismatchedInputException.html)

