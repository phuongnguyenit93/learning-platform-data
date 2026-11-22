# Bảo toàn bất biến và giới hạn dữ liệu khi tạo đối tượng

Một deserializer không chỉ chuyển JSON thành object Java. Nó còn là ranh giới nơi dữ liệu bên ngoài đi vào mô hình của ứng dụng. Nếu deserializer tạo ra object thiếu trường bắt buộc, chứa số âm ở nơi chỉ cho phép số dương, có collection quá lớn hoặc phá vỡ quan hệ giữa các thuộc tính, lỗi có thể lan sâu vào service và database trước khi được phát hiện.

Với Jackson, có thể dùng custom JsonDeserializer để kiểm soát quá trình đọc token, kiểm tra dữ liệu và chỉ tạo object sau khi đã xác nhận các điều kiện cần thiết. Tuy nhiên, bất biến quan trọng vẫn nên được bảo vệ ở constructor hoặc factory của domain model. Cách này bảo đảm object hợp lệ dù nó được tạo từ JSON, từ code Java khác hay từ một nguồn dữ liệu khác.

Một thiết kế tốt kết hợp nhiều lớp bảo vệ: giới hạn kích thước request ở HTTP boundary, giới hạn độ sâu và độ dài token ở Jackson Core, giới hạn số phần tử và quan hệ dữ liệu trong custom deserializer, rồi xác nhận bất biến cuối cùng ở constructor/domain layer. Không nên chỉ dựa vào một lớp duy nhất để ngăn payload lớn hoặc dữ liệu sai.

## 1. Bất biến của object là gì?

Bất biến (invariant) là điều kiện phải luôn đúng đối với một object ở trạng thái hợp lệ. Nó có thể là điều kiện trên một thuộc tính hoặc quan hệ giữa nhiều thuộc tính.

Ví dụ với một đơn hàng:

- Mã đơn hàng phải có giá trị và không vượt quá độ dài cho phép.
- Danh sách mặt hàng không được null hoặc rỗng.
- Mỗi mặt hàng phải có mã SKU hợp lệ.
- Số lượng của mỗi mặt hàng phải lớn hơn 0 và không vượt quá giới hạn nghiệp vụ.
- Tổng số đơn vị hàng không được vượt ngưỡng cho phép.
- Không được có hai mặt hàng trùng khóa nếu contract yêu cầu SKU duy nhất.

Các điều kiện này khác với việc JSON có cú pháp hợp lệ. Payload sau là JSON hợp lệ:

```json
{
  "orderId": "",
  "items": [
    { "sku": "A-1", "quantity": -4 }
  ]
}
```

Nhưng nó không thể tạo thành một đơn hàng hợp lệ. JSON parser chỉ xác nhận cấu trúc và token; domain model mới biết các điều kiện nghiệp vụ.

### 1.1. Phân loại điều kiện cần bảo vệ

| Nhóm | Ví dụ | Nơi kiểm tra phù hợp |
|---|---|---|
| Cấu trúc | Root phải là object; items phải là array | Deserializer/parser |
| Presence | orderId và items phải xuất hiện | Deserializer hoặc creator validation |
| Kiểu dữ liệu | quantity phải là integer | Deserializer/databinding |
| Giới hạn | SKU tối đa 32 ký tự; tối đa 100 item | Parser/deserializer và domain constructor |
| Quan hệ | Tổng quantity không vượt 10.000 | Domain constructor/factory |
| Nghiệp vụ | Trạng thái đơn chỉ được chuyển theo quy tắc cho phép | Service/domain method |
| Tài nguyên | Request body tối đa một số byte; nesting không quá sâu | HTTP server và Jackson Core |

Đặt validation đúng tầng giúp thông báo lỗi rõ ràng và tránh để dữ liệu sai đi vào phần còn lại của hệ thống.

## 2. Bảo vệ bất biến ở constructor hoặc factory

Custom deserializer có thể kiểm tra trước khi tạo object, nhưng không nên là nơi duy nhất bảo vệ domain invariant. Một service khác có thể gọi constructor trực tiếp mà không đi qua Jackson.

Ví dụ dùng Java record:

```java
public record OrderItem(String sku, int quantity) {
    public OrderItem {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }

        sku = sku.trim();
        if (sku.length() > 32) {
            throw new IllegalArgumentException("sku is too long");
        }

        if (quantity < 1 || quantity > 1_000) {
            throw new IllegalArgumentException("quantity is outside the allowed range");
        }
    }
}
```

Constructor compact của record xác nhận điều kiện trước khi object được tạo. Việc chuẩn hóa sku bằng trim() được thực hiện có chủ đích; nếu contract yêu cầu giữ nguyên khoảng trắng thì không nên tự chuẩn hóa.

Đơn hàng:

```java
public record OrderCommand(String orderId, List<OrderItem> items) {
    public static final int MAX_ITEMS = 100;
    public static final long MAX_TOTAL_UNITS = 10_000;

    public OrderCommand {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        orderId = orderId.trim();
        if (orderId.length() > 64) {
            throw new IllegalArgumentException("orderId is too long");
        }

        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }
        if (items.size() > MAX_ITEMS) {
            throw new IllegalArgumentException("too many items");
        }

        items = List.copyOf(items);

        long totalUnits = 0;
        Set<String> seenSkus = new HashSet<>();
        for (OrderItem item : items) {
            if (!seenSkus.add(item.sku())) {
                throw new IllegalArgumentException("duplicate sku");
            }
            totalUnits = Math.addExact(totalUnits, item.quantity());
            if (totalUnits > MAX_TOTAL_UNITS) {
                throw new IllegalArgumentException("total quantity is too large");
            }
        }
    }
}
```

List.copyOf tạo snapshot không thể sửa qua reference được trả ra và từ chối phần tử null. Vì thế object không bị thay đổi bất ngờ nếu caller sửa list ban đầu sau khi tạo đơn hàng.

Với Java class thông thường, áp dụng nguyên tắc tương tự trong constructor hoặc static factory. Không để object ở trạng thái nửa hợp lệ rồi yêu cầu mọi caller nhớ gọi một phương thức validate() sau đó.

## 3. Vì sao cần custom deserializer?

Jackson có thể deserialize nhiều model qua constructor, record creator hoặc setter mà không cần custom code. Nên ưu tiên databinding thông thường khi mapping đơn giản và các annotation/validation hiện có đủ diễn tả contract.

Custom JsonDeserializer hữu ích khi cần:

- Đọc dữ liệu theo luồng và giới hạn số phần tử trước khi tạo collection lớn.
- Phân biệt field bị thiếu, explicit null và giá trị rỗng.
- Kiểm tra duplicate property.
- Kiểm tra kiểu token chính xác, không chấp nhận coercion ngoài ý muốn.
- Kiểm tra quan hệ giữa nhiều field trước khi gọi constructor.
- Chuyển đổi một schema JSON đặc biệt thành domain object bất biến.
- Trả lỗi mapping tại ranh giới JSON với thông tin field phù hợp.

Không nên viết custom deserializer chỉ để thay thế một mapping đơn giản mà JsonCreator, record constructor hoặc Bean Validation đã xử lý rõ ràng. Custom code có nhiều trách nhiệm hơn: theo dõi token, xử lý null, field lạ, lỗi cú pháp, giới hạn và trạng thái parser.

## 4. Mẫu custom deserializer đọc object theo token

Giả sử request có dạng:

```json
{
  "orderId": "ord-2026-17",
  "items": [
    { "sku": "KEY-01", "quantity": 2 },
    { "sku": "MOUSE-02", "quantity": 1 }
  ]
}
```

Deserializer cần:

1. Xác nhận root là object.
2. Đọc property theo tên, không phụ thuộc thứ tự.
3. Từ chối field bắt buộc bị thiếu hoặc null.
4. Giới hạn số phần tử trước khi thêm vào list.
5. Kiểm tra token type và range trước khi chuyển thành kiểu Java.
6. Chỉ tạo OrderCommand sau khi object đã đọc xong.
7. Để constructor domain kiểm tra lại bất biến tổng thể.

### 4.1. Custom deserializer

Ví dụ dưới đây xử lý cả OrderCommand và OrderItem trong cùng một class để có thể kiểm soát số phần tử trước khi tạo từng item:

```java
public final class OrderCommandDeserializer
        extends JsonDeserializer<OrderCommand> {

    private static final int MAX_ORDER_ID_LENGTH = 64;
    private static final int MAX_SKU_LENGTH = 32;
    private static final int MAX_ITEMS = 100;
    private static final int MAX_QUANTITY = 1_000;
    private static final long MAX_TOTAL_UNITS = 10_000;

    @Override
    public OrderCommand deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(parser, "order must be an object");
        }

        String orderId = null;
        List<OrderItem> items = null;
        boolean orderIdSeen = false;
        boolean itemsSeen = false;

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            JsonToken token = parser.currentToken();
            if (token == null) {
                throw JsonMappingException.from(parser, "unexpected end of order");
            }
            if (token != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(parser, "expected an order field name");
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            if (valueToken == null) {
                throw JsonMappingException.from(parser, "missing order field value");
            }

            switch (fieldName) {
                case "orderId" -> {
                    if (orderIdSeen) {
                        throw JsonMappingException.from(parser, "duplicate orderId field");
                    }
                    orderIdSeen = true;
                    orderId = readRequiredString(
                        parser, valueToken, "orderId", MAX_ORDER_ID_LENGTH
                    );
                }
                case "items" -> {
                    if (itemsSeen) {
                        throw JsonMappingException.from(parser, "duplicate items field");
                    }
                    itemsSeen = true;
                    items = readItems(parser, valueToken);
                }
                default -> throw JsonMappingException.from(
                    parser, "unknown order property: " + fieldName
                );
            }
        }

        if (!orderIdSeen) {
            throw JsonMappingException.from(parser, "missing required field: orderId");
        }
        if (!itemsSeen) {
            throw JsonMappingException.from(parser, "missing required field: items");
        }

        try {
            return new OrderCommand(orderId, items);
        } catch (IllegalArgumentException | ArithmeticException exception) {
            throw JsonMappingException.from(
                parser, "invalid order: " + exception.getMessage()
            );
        }
    }

    private List<OrderItem> readItems(
            JsonParser parser,
            JsonToken token) throws IOException {

        if (token == JsonToken.VALUE_NULL) {
            throw JsonMappingException.from(parser, "items must not be null");
        }
        if (token != JsonToken.START_ARRAY) {
            throw JsonMappingException.from(parser, "items must be an array");
        }

        List<OrderItem> result = new ArrayList<>();
        long totalUnits = 0;
        Set<String> seenSkus = new HashSet<>();

        JsonToken itemToken;
        while ((itemToken = parser.nextToken()) != JsonToken.END_ARRAY) {
            if (itemToken == null) {
                throw JsonMappingException.from(parser, "unexpected end of items array");
            }
            if (result.size() >= MAX_ITEMS) {
                throw JsonMappingException.from(parser, "too many items");
            }

            OrderItem item = readItem(parser);
            if (!seenSkus.add(item.sku())) {
                throw JsonMappingException.from(parser, "duplicate sku");
            }

            totalUnits = Math.addExact(totalUnits, item.quantity());
            if (totalUnits > MAX_TOTAL_UNITS) {
                throw JsonMappingException.from(parser, "total quantity is too large");
            }
            result.add(item);
        }

        if (result.isEmpty()) {
            throw JsonMappingException.from(parser, "items must not be empty");
        }
        return result;
    }

    private OrderItem readItem(JsonParser parser) throws IOException {
        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(parser, "each item must be an object");
        }

        String sku = null;
        Integer quantity = null;
        boolean skuSeen = false;
        boolean quantitySeen = false;

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            JsonToken token = parser.currentToken();
            if (token == null) {
                throw JsonMappingException.from(parser, "unexpected end of item");
            }
            if (token != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(parser, "expected an item field name");
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            if (valueToken == null) {
                throw JsonMappingException.from(parser, "missing item field value");
            }

            switch (fieldName) {
                case "sku" -> {
                    if (skuSeen) {
                        throw JsonMappingException.from(parser, "duplicate sku field");
                    }
                    skuSeen = true;
                    sku = readRequiredString(
                        parser, valueToken, "sku", MAX_SKU_LENGTH
                    );
                }
                case "quantity" -> {
                    if (quantitySeen) {
                        throw JsonMappingException.from(parser, "duplicate quantity field");
                    }
                    quantitySeen = true;
                    quantity = readQuantity(parser, valueToken);
                }
                default -> throw JsonMappingException.from(
                    parser, "unknown item property: " + fieldName
                );
            }
        }

        if (!skuSeen) {
            throw JsonMappingException.from(parser, "missing required field: sku");
        }
        if (!quantitySeen) {
            throw JsonMappingException.from(parser, "missing required field: quantity");
        }

        try {
            return new OrderItem(sku, quantity);
        } catch (IllegalArgumentException exception) {
            throw JsonMappingException.from(
                parser, "invalid item: " + exception.getMessage()
            );
        }
    }

    private static String readRequiredString(
            JsonParser parser,
            JsonToken token,
            String fieldName,
            int maxLength) throws IOException {

        if (token == JsonToken.VALUE_NULL) {
            throw JsonMappingException.from(parser, fieldName + " must not be null");
        }
        if (token != JsonToken.VALUE_STRING) {
            throw JsonMappingException.from(parser, fieldName + " must be a string");
        }
        if (parser.getTextLength() > maxLength) {
            throw JsonMappingException.from(parser, fieldName + " is too long");
        }

        String value = parser.getText();
        if (value.isBlank()) {
            throw JsonMappingException.from(parser, fieldName + " must not be blank");
        }
        return value;
    }

    private static int readQuantity(
            JsonParser parser,
            JsonToken token) throws IOException {

        if (token != JsonToken.VALUE_NUMBER_INT) {
            throw JsonMappingException.from(parser, "quantity must be an integer");
        }

        long value = parser.getLongValue();
        if (value < 1 || value > MAX_QUANTITY) {
            throw JsonMappingException.from(parser, "quantity is outside the allowed range");
        }
        return (int) value;
    }
}
```

Deserializer xác nhận các field bắt buộc xuất hiện đúng một lần. Nó không chấp nhận quantity là chuỗi "2" hoặc số thập phân 2.0, dù một số cấu hình databinding có thể hỗ trợ coercion. Với command API, kiểm tra token type nghiêm ngặt giúp tránh client gửi sai schema mà vẫn được chấp nhận.

getTextLength() cho phép kiểm tra độ dài token string trước getText(). Tuy nhiên, parser vẫn phải đọc token từ input; giới hạn cấp Jackson Core và giới hạn byte của request vẫn cần thiết để ngăn dữ liệu quá lớn trước khi custom code được gọi.

### 4.2. Đăng ký custom deserializer

Đăng ký qua SimpleModule:

```java
SimpleModule module = new SimpleModule("order-input");
module.addDeserializer(OrderCommand.class, new OrderCommandDeserializer());

ObjectMapper mapper = new ObjectMapper()
    .registerModule(module);
```

Sau đó:

```java
OrderCommand command = mapper.readValue(json, OrderCommand.class);
```

Custom deserializer cấp trên tự đọc từng item, vì vậy không cần đăng ký deserializer riêng cho OrderItem trong ví dụ này. Nếu chuyển sang context.readValue(parser, OrderItem.class), hãy đăng ký deserializer của OrderItem để Jackson chọn đúng implementation.

## 5. Giới hạn dữ liệu ở Jackson Core

Kiểm tra trong custom deserializer chỉ chạy sau khi parser đã đọc tới token tương ứng. Vì vậy, cần giới hạn token ở lớp parser để tránh chuỗi, số hoặc cấu trúc lồng quá lớn.

Từ Jackson Core 2.15, có thể dùng StreamReadConstraints để giới hạn một số thuộc tính của input:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(32)
    .maxStringLength(4_096)
    .maxNumberLength(64)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Ý nghĩa:

| Giới hạn | Tác dụng |
|---|---|
| maxNestingDepth | Giới hạn độ sâu object/array lồng nhau. |
| maxStringLength | Giới hạn độ dài string token. |
| maxNumberLength | Giới hạn độ dài biểu diễn số. |
| STRICT_DUPLICATE_DETECTION | Báo lỗi khi cùng tên field xuất hiện lặp trong một object. |

Các giới hạn này giúp parser từ chối input vượt ngưỡng trước khi databinding tạo object tương ứng. Tên API và khả năng cấu hình phụ thuộc Jackson Core version; hãy dùng cùng dòng version tương thích giữa jackson-core, jackson-databind và module liên quan.

StreamReadConstraints không thay thế giới hạn số phần tử của array, số entry trong map, số object trong batch hoặc kích thước request body. Các giới hạn nghiệp vụ đó cần được kiểm tra ở deserializer/service và HTTP boundary.

## 6. Giới hạn request body ở HTTP boundary

Giới hạn parser không đồng nghĩa giới hạn tổng số byte mà client có thể gửi. Một request có thể chứa nhiều token nhỏ nhưng tổng payload vẫn rất lớn.

Nên có giới hạn tại HTTP server hoặc API gateway:

- Maximum request body bytes.
- Read timeout hoặc request timeout.
- Giới hạn số request đồng thời theo năng lực hệ thống.
- Giới hạn upload riêng cho endpoint nhận file/binary.
- Rate limit hoặc quota phù hợp với client.

Ví dụ cấu hình giới hạn request trong Spring Boot phụ thuộc loại endpoint, servlet container và phiên bản framework. Không nên giả định StreamReadConstraints.maxStringLength giới hạn toàn bộ request body. Hãy cấu hình body size ở server/container/gateway theo cơ chế mà ứng dụng đang dùng.

Đối với InputStream, không đọc toàn bộ body vào byte[] chỉ để kiểm tra size nếu payload có thể lớn. Dùng giới hạn ở tầng server hoặc một bounded stream để từ chối khi vượt số byte cho phép.

## 7. Giới hạn collection trước khi cấp phát bộ nhớ

Một lỗi thường gặp là đọc toàn bộ array thành list rồi mới kiểm tra:

```java
List<Item> items = mapper.readValue(
    parser,
    new TypeReference<List<Item>>() {}
);

if (items.size() > MAX_ITEMS) {
    throw new IllegalArgumentException("too many items");
}
```

Kiểm tra này quá muộn: Jackson đã tạo toàn bộ list và từng item trước khi phát hiện giới hạn. Với payload lớn, chi phí bộ nhớ đã phát sinh.

Thay vào đó, đọc từng phần tử và kiểm tra trước khi thêm:

```java
List<Item> items = new ArrayList<>();

while (parser.nextToken() != JsonToken.END_ARRAY) {
    if (items.size() >= MAX_ITEMS) {
        throw JsonMappingException.from(parser, "too many items");
    }

    Item item = context.readValue(parser, Item.class);
    items.add(item);
}
```

Không cấp phát trước theo kích thước do client gửi nếu chưa xác thực. Ví dụ new ArrayList<>(clientProvidedCount) có thể yêu cầu một lượng bộ nhớ lớn ngay lập tức. Nếu cần tối ưu, dùng capacity nhỏ có giới hạn hoặc cấu trúc tăng dần.

### 7.1. Giới hạn tổng số phần tử trong cấu trúc lồng

Giới hạn 100 phần tử ở mỗi array có thể vẫn cho phép số object rất lớn nếu payload có nhiều array lồng hoặc nhiều record. Có thể cần thêm ngân sách tổng:

```java
final class ReadBudget {
    private int remainingItems;

    ReadBudget(int maxItems) {
        this.remainingItems = maxItems;
    }

    void consumeItem(JsonParser parser) throws JsonMappingException {
        if (remainingItems <= 0) {
            throw JsonMappingException.from(parser, "item budget exceeded");
        }
        remainingItems--;
    }
}
```

Trước khi tạo mỗi phần tử, gọi budget.consumeItem(parser). Với object graph lớn, có thể quản lý thêm ngân sách tổng cho số node, map entry hoặc nested object. Budget nên có phạm vi một lần deserialize/request, không dùng biến static hoặc mutable singleton vì các request có thể chạy đồng thời.

## 8. Giới hạn string và number

Độ dài string có thể ảnh hưởng bộ nhớ, thời gian xử lý, index database và log. Giới hạn cần dựa trên semantics của từng field:

| Field | Ví dụ giới hạn | Lý do |
|---|---:|---|
| Order ID | 64 ký tự | Khóa định danh |
| SKU | 32 ký tự | Mã hàng |
| Display name | 120 ký tự | Nội dung hiển thị |
| Free-text note | 2.000 ký tự | Trường văn bản dài |

Không nên áp một giới hạn duy nhất cho mọi string. Tên người dùng, mã định danh, nội dung mô tả và token có quy tắc khác nhau.

### 8.1. Kiểm tra trước khi tạo chuỗi lớn hơn

Trong custom deserializer, khi parser đang ở VALUE_STRING, có thể kiểm tra getTextLength() trước getText():

```java
if (parser.currentToken() != JsonToken.VALUE_STRING) {
    throw JsonMappingException.from(parser, "name must be a string");
}
if (parser.getTextLength() > MAX_NAME_LENGTH) {
    throw JsonMappingException.from(parser, "name is too long");
}

String name = parser.getText();
```

Đây là kiểm tra bổ sung ở tầng field. Giới hạn maxStringLength ở StreamReadConstraints vẫn cần thiết để parser từ chối token quá lớn trước khi logic field chạy.

### 8.2. Kiểm tra số nguyên và overflow

Không chuyển số tùy ý sang int mà không kiểm tra range:

```java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
    throw JsonMappingException.from(parser, "quantity must be an integer");
}

long value = parser.getLongValue();
if (value < 1 || value > 1_000) {
    throw JsonMappingException.from(parser, "quantity is out of range");
}

int quantity = Math.toIntExact(value);
```

getLongValue() có thể ném lỗi input/coercion nếu số vượt phạm vi long. Không nên bắt lỗi rồi thay bằng 0 hoặc một giá trị mặc định vì điều đó che giấu dữ liệu sai.

Với tiền hoặc decimal chính xác, dùng BigDecimal, giới hạn precision/scale theo contract và không chuyển qua double. Với phép cộng tổng số lượng hoặc tổng tiền, dùng Math.addExact hoặc kiểm tra overflow trước khi cộng.

## 9. Giới hạn độ sâu và tránh đệ quy không kiểm soát

Payload có thể chứa object/array lồng rất sâu:

```json
{
  "a": {
    "b": {
      "c": {
        "d": {
          "value": 1
        }
      }
    }
  }
}
```

Với cấu trúc do client kiểm soát, độ sâu lớn có thể tiêu tốn stack, CPU và bộ nhớ. StreamReadConstraints.maxNestingDepth giúp parser giới hạn độ sâu cấu trúc JSON.

Nếu custom deserializer tự gọi đệ quy để đọc node lồng, cần có giới hạn riêng hoặc dựa vào parser constraint. Không xây dựng recursion từ một số depth client gửi mà không kiểm tra.

Khi schema có cấu trúc lồng không giới hạn theo nghiệp vụ, cân nhắc:

- Giới hạn depth.
- Giới hạn tổng node.
- Giới hạn tổng string/number token.
- Giới hạn số phần tử mỗi collection.
- Giới hạn tổng phần tử toàn document.

Một giới hạn riêng lẻ không đủ nếu các chiều còn lại vẫn không bị giới hạn.

## 10. Duplicate property và tính nhất quán

JSON có thể chứa tên property lặp:

```json
{
  "role": "user",
  "role": "admin"
}
```

Nếu parser hoặc databinding chấp nhận duplicate theo kiểu giá trị sau ghi đè giá trị trước, các lớp hệ thống khác có thể diễn giải khác nhau. Điều này đặc biệt nguy hiểm khi một proxy, chữ ký request, validator và service không thống nhất cách chọn giá trị.

Bật strict duplicate detection:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();
```

Trong custom deserializer, vẫn có thể giữ cờ seen cho field bắt buộc để thông báo lỗi domain cụ thể. Strict duplicate detection áp dụng ở parser và phát hiện duplicate ở object; cờ seen giúp code deserializer nêu rõ property nào không được xuất hiện nhiều lần.

Không dùng duplicate field như một cách ghi đè giá trị cũ trong command. Nếu contract cần patch hoặc merge, thiết kế field/operation riêng thay vì dựa vào thứ tự xuất hiện của cùng một tên property.

## 11. Missing, null và default không được nhập làm một

Khi tạo object, ba trường hợp sau khác nhau:

```json
{}
```

```json
{ "note": null }
```

```json
{ "note": "" }
```

- Missing: client không gửi property.
- Explicit null: client gửi property nhưng không có giá trị.
- Empty: client gửi giá trị rỗng.

Trong custom deserializer, dùng cờ seen riêng:

```java
boolean noteSeen = false;
String note = null;

// Khi đọc field note:
noteSeen = true;
if (valueToken == JsonToken.VALUE_NULL) {
    note = null;
} else if (valueToken == JsonToken.VALUE_STRING) {
    note = parser.getText();
} else {
    throw JsonMappingException.from(parser, "note must be a string or null");
}
```

Sau khi đọc xong:

- Nếu noteSeen là false, giữ default hoặc báo lỗi theo contract.
- Nếu noteSeen là true và note là null, xử lý explicit null.
- Nếu note là chuỗi rỗng, xử lý empty theo quy tắc riêng.

Đối với lệnh PATCH, missing thường có nghĩa không thay đổi; explicit null có thể có nghĩa xóa giá trị; empty string là một giá trị được gửi. Nếu gộp cả ba thành null, ứng dụng có thể vô tình xóa dữ liệu.

## 12. Unknown field: strict hay bỏ qua?

Custom deserializer phải quyết định điều gì xảy ra khi gặp property không có trong contract.

### 12.1. Từ chối unknown field

Với command thay đổi dữ liệu, từ chối field lạ thường giúp phát hiện sai tên hoặc sai version sớm:

```java
default -> throw JsonMappingException.from(
    parser, "unknown property: " + fieldName
);
```

Không đưa giá trị field lạ vào domain object nếu ứng dụng không có semantics cho nó.

### 12.2. Bỏ qua unknown field

Với consumer đọc response hoặc event cần forward compatibility, có thể bỏ qua value:

```java
default -> parser.skipChildren();
```

skipChildren() tiêu thụ toàn bộ object/array lồng của value hiện tại, giúp parser quay lại đúng ranh giới object cha. Chỉ gọi nextToken() một lần không đủ nếu value là cấu trúc lồng.

Nếu cần giữ field lạ, có thể đọc value thành JsonNode và lưu vào extension map. Tuy nhiên, điều này tạo object tree và tăng bộ nhớ; hãy áp giới hạn kích thước, số field và số node nếu payload không đáng tin cậy.

### 12.3. Không bỏ qua field bắt buộc bị đổi tên

Ignore unknown không có nghĩa payload luôn hợp lệ. Nếu producer đổi orderId thành id, deserializer cũ có thể bỏ qua id rồi báo thiếu orderId. Đây là hành vi tốt hơn việc tự đoán hai field có cùng semantics. Dùng alias hoặc version mapping có chủ đích nếu contract hỗ trợ tên cũ và mới.

## 13. Bean Validation bổ sung sau deserialize

Bean Validation có thể kiểm tra constraint trên object sau khi Jackson tạo nó:

```java
public record CreateUserRequest(
    @NotBlank
    @Size(max = 80)
    String username,

    @Email
    @Size(max = 254)
    String email,

    @Min(1)
    @Max(150)
    int age
) {}
```

Trong Spring MVC, @Valid hoặc @Validated có thể kích hoạt validation cho request DTO tùy method signature và cấu hình framework.

Bean Validation hữu ích cho constraint trên thuộc tính và một số class-level constraint. Nhưng validation chạy sau khi object đã được tạo; nó không thay thế giới hạn request bytes, parser string length hoặc giới hạn collection trước khi cấp phát. Với collection cực lớn, việc deserialize toàn bộ rồi mới chạy @Size(max = ...) có thể đã tiêu tốn bộ nhớ.

Có thể kết hợp:

1. Jackson Core constraints để giới hạn token và nesting.
2. Custom deserializer để giới hạn collection trong lúc đọc.
3. Constructor/domain factory để bảo vệ invariant mọi đường tạo object.
4. Bean Validation để diễn tả constraint và trả lỗi có cấu trúc ở API layer.

Không nhân đôi mọi quy tắc ở tất cả các tầng nếu không cần thiết. Chọn một nơi làm nguồn chuẩn cho từng invariant, còn các tầng khác chỉ đặt guard cần thiết để bảo vệ tài nguyên hoặc chuyển lỗi phù hợp.

## 14. Không để validation làm lộ dữ liệu hoặc gây log quá lớn

Khi dữ liệu sai, lỗi nên chỉ rõ field và điều kiện bị vi phạm, nhưng không cần ghi toàn bộ giá trị đầu vào.

Thông báo phù hợp:

```text
items: too many elements (maximum 100)
orderId: value is too long (maximum 64 characters)
quantity: must be between 1 and 1000
```

Tránh thông báo chứa toàn bộ token hoặc raw request. Log toàn bộ payload có thể làm lộ token, thông tin cá nhân hoặc dữ liệu thanh toán; đồng thời một payload rất lớn có thể làm log system bị quá tải. Ghi tên field, loại lỗi, request correlation ID và kích thước/metadata cần thiết. Nếu cần lưu payload để điều tra, áp chính sách bảo vệ dữ liệu, retention và access control riêng.

## 15. Kiểm soát số lượng object trong batch hoặc stream

Một endpoint có thể nhận một array gồm nhiều đơn hàng:

```json
[
  { "orderId": "o-1", "items": [ ... ] },
  { "orderId": "o-2", "items": [ ... ] }
]
```

Giới hạn item bên trong từng đơn hàng chưa đủ. Cần giới hạn số đơn hàng trong batch và tổng item trên toàn batch.

Ví dụ đọc array root theo streaming:

```java
List<OrderCommand> batch = new ArrayList<>();
long totalItems = 0;
final int maxOrders = 50;
final long maxBatchItems = 2_000;

if (parser.nextToken() != JsonToken.START_ARRAY) {
    throw JsonMappingException.from(parser, "expected an array of orders");
}

while (parser.nextToken() != JsonToken.END_ARRAY) {
    if (batch.size() >= maxOrders) {
        throw JsonMappingException.from(parser, "too many orders in batch");
    }

    OrderCommand order = context.readValue(parser, OrderCommand.class);
    totalItems += order.items().size();
    if (totalItems > maxBatchItems) {
        throw JsonMappingException.from(parser, "batch contains too many items");
    }

    batch.add(order);
}
```

Ví dụ này giới hạn số order trước khi deserialize từng order. Tổng item được kiểm tra sau khi mỗi order được tạo; nếu cần dừng sớm hơn, hãy truyền một ReadBudget theo phạm vi lần đọc vào deserializer để tiêu thụ ngân sách cho từng item ngay khi token được đọc.

Không dùng biến static để đếm quota giữa các request. Mỗi request hoặc batch phải có budget riêng để không tạo race condition hoặc làm request này ảnh hưởng request khác.

## 16. Kiểm thử invariant và giới hạn

Test nên kiểm tra cả payload hợp lệ, payload biên và payload vượt giới hạn.

### 16.1. Payload hợp lệ tạo object bất biến

```java
@Test
void readsValidOrder() throws Exception {
    String json = """
        {
          "orderId": "ord-2026-17",
          "items": [
            {"sku": "KEY-01", "quantity": 2},
            {"sku": "MOUSE-02", "quantity": 1}
          ]
        }
        """;

    OrderCommand order = mapper.readValue(json, OrderCommand.class);

    assertEquals("ord-2026-17", order.orderId());
    assertEquals(2, order.items().size());
    assertThrows(
        UnsupportedOperationException.class,
        () -> order.items().add(new OrderItem("PAD-01", 1))
    );
}
```

### 16.2. Field bắt buộc bị thiếu hoặc null

Kiểm tra riêng:

- Không có orderId.
- orderId là null.
- orderId là chuỗi rỗng hoặc chỉ có whitespace.
- Không có items.
- items là null.
- items là array rỗng.

Mỗi trường hợp nên trả lỗi tương ứng với contract; không để tất cả trở thành object với giá trị Java mặc định.

### 16.3. Kiểm tra số lượng phần tử tại ranh giới

Test với:

- Đúng 100 item: được chấp nhận nếu các điều kiện khác hợp lệ.
- 101 item: bị từ chối trước khi thêm item thứ 101.
- Array rất lớn: parser dừng sớm khi vượt quota.
- Batch có số order tối đa và vượt tối đa.

### 16.4. Kiểm tra độ dài string và range số

Test:

- SKU đúng 32 ký tự.
- SKU dài 33 ký tự.
- Order ID đúng 64 và dài 65 ký tự.
- Quantity bằng 1 và 1.000.
- Quantity bằng 0, âm hoặc 1.001.
- Number vượt phạm vi long.
- Decimal được gửi cho field yêu cầu integer.

### 16.5. Kiểm tra parser constraints

Tạo JsonFactory với giới hạn test nhỏ, rồi xác nhận:

- String token vượt maxStringLength bị từ chối.
- Number token vượt maxNumberLength bị từ chối.
- Object/array vượt maxNestingDepth bị từ chối.
- Duplicate property bị từ chối khi bật strict duplicate detection.

Các test này nên dùng đúng Jackson Core version được quản lý trong dự án.

### 16.6. Kiểm tra invariant khi tạo object trực tiếp

Gọi constructor/factory từ Java với dữ liệu sai để bảo đảm domain model tự bảo vệ:

```java
assertThrows(
    IllegalArgumentException.class,
    () -> new OrderItem("SKU-1", 0)
);

assertThrows(
    IllegalArgumentException.class,
    () -> new OrderCommand("order-1", List.of())
);
```

Test này chứng minh invariant không phụ thuộc vào việc object được tạo qua Jackson.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Object không hợp lệ lọt vào service | Chỉ kiểm tra cú pháp JSON | Xác nhận required field và domain invariant trước khi trả object. |
| List quá lớn làm tăng memory | Deserialize toàn bộ rồi mới kiểm tra size | Đếm và từ chối trước khi thêm phần tử vượt giới hạn. |
| Chuỗi khổng lồ gây áp lực bộ nhớ | Chỉ kiểm tra độ dài sau khi gọi getText() | Dùng parser constraints và kiểm tra getTextLength() trước. |
| Số bị tràn hoặc bị ép kiểu | Dùng getIntValue()/coercion không kiểm tra | Kiểm tra token type, đọc kiểu rộng hơn và xác nhận range. |
| Null và missing bị gộp | Chỉ kiểm tra giá trị Java cuối cùng | Theo dõi cờ seen riêng cho từng field cần phân biệt. |
| Duplicate field ghi đè dữ liệu | Parser không bật duplicate detection | Bật strict duplicate detection và/hoặc theo dõi field đã đọc. |
| Constructor có thể tạo object nửa hợp lệ | Validation nằm ngoài domain constructor | Bảo vệ invariant trong constructor/factory. |
| Request body vẫn quá lớn dù token constraints có giới hạn | Nhầm giới hạn token với giới hạn toàn request | Đặt body size/time limit tại HTTP server hoặc gateway. |
| Request này tiêu thụ quota của request khác | Dùng counter/budget static | Tạo budget riêng theo lần deserialize/request. |
| Log chứa dữ liệu nhạy cảm | Ghi toàn bộ payload khi mapping lỗi | Log metadata và lỗi field, không log raw body mặc định. |

## 18. Quy trình triển khai

1. Liệt kê invariant của object: required field, range, quan hệ giữa field và trạng thái hợp lệ.
2. Đặt invariant cốt lõi trong constructor hoặc factory để mọi đường tạo object đều được bảo vệ.
3. Chỉ viết custom deserializer khi cần kiểm soát token, presence, collection hoặc schema phức tạp.
4. Kiểm tra root token, field name, token type, missing, explicit null và duplicate.
5. Giới hạn string, number, collection, batch và tổng số node trước khi cấp phát vượt ngưỡng.
6. Cấu hình StreamReadConstraints cho nesting, string length và number length ở Jackson Core.
7. Đặt giới hạn request body và timeout ở HTTP server/gateway.
8. Chọn rõ chính sách unknown field: reject, skip hoặc capture.
9. Chỉ tạo domain object sau khi các điều kiện đầu vào cần thiết đã được xác nhận.
10. Kết hợp Bean Validation ở API boundary khi phù hợp, nhưng không dùng nó thay cho giới hạn tài nguyên trước deserialize.
11. Trả lỗi có field/constraint rõ ràng nhưng không ghi raw payload nhạy cảm vào log.
12. Test giá trị biên, payload vượt giới hạn, duplicate, null/missing và tạo object trực tiếp.

Bảo toàn bất biến khi deserialize cần nhiều lớp bảo vệ phối hợp. Jackson Core giới hạn hình dạng và kích thước token; custom deserializer kiểm soát cách đọc field và collection; constructor/factory bảo đảm domain object luôn hợp lệ; HTTP boundary giới hạn tổng request. Khi đặt mỗi quy tắc ở đúng tầng và từ chối dữ liệu vượt ngưỡng trước khi tạo object lớn, ứng dụng vừa giữ được tính đúng đắn của domain model vừa giảm rủi ro tiêu thụ tài nguyên quá mức.
