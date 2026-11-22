# Ghi cấu trúc đầu ra thông qua JsonGenerator

Khi Jackson serialize một object, serializer phải chuyển dữ liệu Java thành các token JSON theo đúng cấu trúc: bắt đầu object hoặc array, ghi tên property, ghi giá trị và đóng cấu trúc. JsonGenerator là API mức thấp của Jackson Core dùng để thực hiện các thao tác đó trực tiếp.

Trong một custom serializer, JsonGenerator cho phép kiểm soát chính xác JSON được phát ra. Thay vì để Jackson tự suy ra tên và cấu trúc từ getter của POJO, serializer có thể đổi tên field, flatten object lồng, tạo mảng, ghi giá trị tính toán hoặc bỏ các thuộc tính không thuộc representation public. API này cũng hữu ích khi cần streaming output mà không tạo một Map hoặc JsonNode trung gian.

Một custom serializer đúng phải tuân thủ cấu trúc token JSON, để Jackson quản lý việc escape chuỗi và định dạng số, đồng thời không tự đóng generator do framework truyền vào. Bài này trình bày cách ghi object, array và giá trị lồng nhau, cách tích hợp với ObjectMapper, cách xử lý null và các lưu ý khi triển khai serializer trong ứng dụng thực tế.

## 1. JsonGenerator nằm ở đâu trong kiến trúc Jackson?

Jackson thường được chia thành ba lớp:

| Thành phần | Vai trò |
|---|---|
| Jackson Core | Đọc token bằng JsonParser và ghi token bằng JsonGenerator. |
| Jackson Databind | Ánh xạ giữa JSON và POJO/record/tree thông qua ObjectMapper, serializer và deserializer. |
| Jackson Annotations | Cung cấp metadata như JsonProperty, JsonSerialize, JsonInclude và JsonTypeInfo. |

Khi gọi:

```java
String json = mapper.writeValueAsString(product);
```

Jackson Databind tìm serializer phù hợp với kiểu Product. Serializer đó có thể là serializer mặc định được tạo từ bean metadata hoặc custom serializer do ứng dụng đăng ký. Serializer nhận một JsonGenerator và ghi token đầu ra qua generator.

Luồng tổng quát:

```text
Java object
    |
    v
ObjectMapper / SerializerProvider
    |
    v
JsonSerializer<T>
    |
    v
JsonGenerator
    |
    v
JSON bytes or characters
```

JsonGenerator không tự hiểu model Java. Nó cung cấp các thao tác ghi token. Serializer chịu trách nhiệm quyết định token nào cần được ghi và theo thứ tự nào.

## 2. Cấu trúc token của JSON

JSON có hai cấu trúc tổng hợp là object và array. Object chứa các cặp tên property/giá trị; array chứa một dãy giá trị.

Ví dụ:

```json
{
  "id": "p-10",
  "name": "Keyboard",
  "price": {
    "amount": 49.90,
    "currency": "USD"
  },
  "tags": ["office", "wireless"]
}
```

Các token quan trọng tương ứng:

```text
START_OBJECT
  FIELD_NAME("id")
  VALUE_STRING("p-10")
  FIELD_NAME("name")
  VALUE_STRING("Keyboard")
  FIELD_NAME("price")
  START_OBJECT
    FIELD_NAME("amount")
    VALUE_NUMBER_FLOAT(49.90)
    FIELD_NAME("currency")
    VALUE_STRING("USD")
  END_OBJECT
  FIELD_NAME("tags")
  START_ARRAY
    VALUE_STRING("office")
    VALUE_STRING("wireless")
  END_ARRAY
END_OBJECT
```

Generator theo dõi context hiện tại. Trong object, phải ghi field name trước value tương ứng. Trong array, ghi trực tiếp từng value mà không có field name. Khi đã mở object hoặc array, phải đóng đúng cấu trúc đó.

## 3. Các phương thức JsonGenerator thường dùng

| Mục đích | Phương thức |
|---|---|
| Bắt đầu object | writeStartObject() |
| Kết thúc object | writeEndObject() |
| Bắt đầu array | writeStartArray() |
| Kết thúc array | writeEndArray() |
| Ghi tên property | writeFieldName(String) |
| Ghi chuỗi | writeString(String) |
| Ghi số nguyên | writeNumber(int), writeNumber(long), writeNumber(BigInteger) |
| Ghi số thập phân | writeNumber(double), writeNumber(float), writeNumber(BigDecimal) |
| Ghi boolean | writeBoolean(boolean) |
| Ghi null | writeNull() |
| Ghi binary dạng Base64 | writeBinary(...) |
| Ghi object thông qua codec | writeObject(Object) |
| Ghi cây JSON | writeTree(TreeNode) |

Ngoài các phương thức cơ bản, generator có các helper như writeStringField, writeNumberField, writeBooleanField, writeNullField, writeObjectField và writeArrayFieldStart. Các helper này thuận tiện khi ghi object có cấu trúc đơn giản.

Ví dụ:

```java
gen.writeStartObject();
gen.writeStringField("id", "p-10");
gen.writeNumberField("quantity", 3);
gen.writeBooleanField("available", true);
gen.writeEndObject();
```

Đầu ra:

```json
{
  "id": "p-10",
  "quantity": 3,
  "available": true
}
```

Tên phương thức và overload có thể khác theo Jackson Core version. Hãy tham chiếu Javadoc đúng version trong dự án, đặc biệt với các overload nhận metadata object hoặc độ dài array.

## 4. Viết custom JsonSerializer

Custom serializer thường kế thừa JsonSerializer<T> và override phương thức serialize.

Ví dụ model:

```java
public class Product {
    private String id;
    private String name;
    private BigDecimal price;
    private boolean available;

    // Constructor, getters and setters
}
```

Serializer:

```java
public class ProductSerializer extends JsonSerializer<Product> {
    @Override
    public void serialize(
            Product product,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeStartObject();
        gen.writeStringField("productId", product.getId());
        gen.writeStringField("title", product.getName());

        gen.writeFieldName("price");
        if (product.getPrice() == null) {
            gen.writeNull();
        } else {
            gen.writeNumber(product.getPrice());
        }

        gen.writeBooleanField("inStock", product.isAvailable());
        gen.writeEndObject();
    }
}
```

Serializer này tạo representation có tên productId, title và inStock, khác tên thuộc tính Java. Giá trị BigDecimal được ghi bằng overload số thập phân để giữ semantics số, không chuyển thành chuỗi.

Output ví dụ:

```json
{
  "productId": "p-10",
  "title": "Keyboard",
  "price": 49.90,
  "inStock": true
}
```

Custom serializer cần tự quyết định:

- Property nào xuất hiện và theo thứ tự nào.
- Tên JSON của từng property.
- Giá trị Java nào được đổi thành kiểu JSON nào.
- Null được ghi thành null, bị bỏ hay được thay bằng giá trị khác.
- Cấu trúc object/array lồng nhau được biểu diễn ra sao.

Không nên gọi getter hoặc ghi dữ liệu có thể nhạy cảm nếu representation hiện tại không được phép chứa chúng.

## 5. Đăng ký serializer với ObjectMapper

Có hai cách phổ biến để gắn custom serializer.

### 5.1. Dùng annotation JsonSerialize

Nếu serializer luôn áp dụng cho một kiểu hoặc property cụ thể, có thể dùng annotation:

```java
@JsonSerialize(using = ProductSerializer.class)
public class Product {
    // ...
}
```

Hoặc đặt trên một property:

```java
public class OrderResponse {
    @JsonSerialize(using = ProductSerializer.class)
    private Product featuredProduct;
}
```

Annotation trên type phù hợp khi mọi lần serialize kiểu đó cần cùng representation. Annotation trên property giới hạn hành vi vào một vị trí cụ thể, hữu ích khi cùng kiểu Java xuất hiện ở nhiều nơi nhưng mỗi nơi cần output khác nhau.

### 5.2. Dùng SimpleModule

Nếu không muốn model phụ thuộc annotation Jackson hoặc muốn cấu hình từ composition root, đăng ký serializer qua module:

```java
SimpleModule module = new SimpleModule("product-serialization");
module.addSerializer(Product.class, new ProductSerializer());

ObjectMapper mapper = new ObjectMapper()
    .registerModule(module);
```

Sau khi module được đăng ký, mapper có thể serialize mọi Product bằng serializer đã cung cấp, trừ khi có cấu hình/property-specific serializer có độ ưu tiên phù hợp khác.

Nên cấu hình mapper và đăng ký module trước khi đưa mapper vào sử dụng đồng thời. ObjectMapper được thiết kế để tái sử dụng sau khi cấu hình hoàn tất; thay đổi cấu hình giữa các request có thể gây hành vi khó dự đoán.

### 5.3. Khi nào chọn annotation, khi nào chọn module?

| Nhu cầu | Lựa chọn |
|---|---|
| Serializer là đặc tính cố định của model | JsonSerialize(using = ...) trên type |
| Chỉ một property cần representation riêng | Annotation trên property |
| Model thuộc thư viện ngoài hoặc không muốn thêm annotation | SimpleModule hoặc mix-in |
| Cần nhiều cấu hình mapper độc lập | Module riêng cho từng mapper |
| Serializer được dùng xuyên suốt ứng dụng | Module được đăng ký ở cấu hình mapper chung |

Không đăng ký cùng một kiểu serializer ở nhiều nơi mà không hiểu thứ tự ưu tiên. Nếu output không như mong đợi, kiểm tra annotation, mix-in, module và property-level configuration của mapper đang thực sự dùng.

## 6. Ghi object lồng nhau

Một custom serializer có thể tự ghi object con bằng generator:

```java
public class Address {
    private String city;
    private String country;
    // Getters and setters
}

public class Customer {
    private String id;
    private String name;
    private Address address;
    // Getters and setters
}
```

Serializer có thể điều khiển cấu trúc lồng:

```java
public class CustomerSerializer extends JsonSerializer<Customer> {
    @Override
    public void serialize(
            Customer customer,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeStartObject();
        gen.writeStringField("customerId", customer.getId());
        gen.writeStringField("fullName", customer.getName());

        gen.writeFieldName("address");
        Address address = customer.getAddress();
        if (address == null) {
            gen.writeNull();
        } else {
            gen.writeStartObject();
            gen.writeStringField("city", address.getCity());
            gen.writeStringField("country", address.getCountry());
            gen.writeEndObject();
        }

        gen.writeEndObject();
    }
}
```

Output:

```json
{
  "customerId": "c-21",
  "fullName": "An Nguyen",
  "address": {
    "city": "Da Nang",
    "country": "VN"
  }
}
```

Tự ghi object con giúp kiểm soát hoàn toàn representation, nhưng đồng nghĩa serializer cha phải tự duy trì quy tắc của object con. Nếu Address có serializer riêng và muốn tái sử dụng nó, hãy ủy quyền cho SerializerProvider thay vì tự lặp lại logic.

## 7. Ủy quyền cho serializer mặc định qua SerializerProvider

Trong custom serializer, không phải mọi giá trị đều cần được ghi thủ công. SerializerProvider có thể tìm serializer phù hợp và ghi giá trị lồng:

```java
gen.writeFieldName("address");
serializers.defaultSerializeValue(customer.getAddress(), gen);
```

defaultSerializeValue sử dụng serializer phù hợp với kiểu runtime của giá trị và xử lý null theo null serializer của provider. Cách này tái sử dụng cấu hình mapper, annotation, module, naming và serializer của kiểu con.

Có thể dùng tương tự với collection:

```java
gen.writeFieldName("items");
serializers.defaultSerializeValue(order.getItems(), gen);
```

Hoặc với một property có serializer cụ thể:

```java
JsonSerializer<Object> serializer =
    serializers.findValueSerializer(value.getClass());
serializer.serialize(value, gen, serializers);
```

Trong phần lớn trường hợp, defaultSerializeValue gọn và ít lỗi hơn việc tự tìm serializer. Dùng findValueSerializer khi cần giữ một serializer để tái sử dụng hoặc cần gọi nó trực tiếp theo logic riêng.

Không nên gọi lại serializer của chính object đang serialize bằng defaultSerializeValue(thisValue, gen) trong custom serializer của kiểu đó; điều này có thể tạo đệ quy vô hạn. Hãy chỉ ủy quyền cho giá trị con hoặc dùng serializer mặc định có chủ đích.

## 8. Ghi array và collection

Array JSON bắt đầu bằng writeStartArray() và kết thúc bằng writeEndArray(). Mỗi phần tử được ghi trực tiếp:

```java
gen.writeStartArray();
gen.writeString("red");
gen.writeString("green");
gen.writeString("blue");
gen.writeEndArray();
```

Output:

```json
["red", "green", "blue"]
```

Trong custom serializer:

```java
gen.writeFieldName("tags");
gen.writeStartArray();
for (String tag : product.getTags()) {
    if (tag == null) {
        gen.writeNull();
    } else {
        gen.writeString(tag);
    }
}
gen.writeEndArray();
```

Nếu không cần logic riêng cho từng phần tử, có thể ủy quyền:

```java
gen.writeFieldName("tags");
serializers.defaultSerializeValue(product.getTags(), gen);
```

Cách thứ hai giữ lại serializer và inclusion policy được cấu hình cho collection/element type. Cách thứ nhất cho phép lọc, chuyển đổi hoặc thay thế từng phần tử theo quy tắc custom.

### 8.1. Array rỗng và null collection

Phải quyết định rõ null collection được biểu diễn thế nào:

```json
{ "tags": null }
```

khác với:

```json
{ "tags": [] }
```

Nếu field null là null trong contract, ghi writeNull(). Nếu API muốn coi null như collection rỗng, ghi writeStartArray() rồi writeEndArray(). Đừng tự chuyển null thành empty chỉ vì cách đó tiện hơn; client có thể dựa vào khác biệt này.

### 8.2. Mảng có độ dài biết trước

Một số overload writeStartArray nhận object và kích thước dự kiến. Khi biết số phần tử, có thể cung cấp size để generator hoặc backend tối ưu. Đây là gợi ý kích thước, không thay thế việc ghi đủ phần tử và đóng array đúng cách.

## 9. Ghi giá trị scalar và giữ đúng kiểu JSON

JSON có string, number, boolean và null. Serializer nên dùng đúng phương thức tương ứng:

```java
gen.writeString("42");          // JSON string
gen.writeNumber(42);            // JSON number
gen.writeBoolean(false);        // JSON boolean
gen.writeNull();                // JSON null
```

Các giá trị sau không tương đương:

```json
{
  "count": 42,
  "countText": "42",
  "enabled": false,
  "description": null
}
```

Nếu một số được ghi bằng writeString, client sẽ nhận string thay vì number. Nếu cần độ chính xác thập phân cho tiền tệ, dùng BigDecimal và writeNumber(BigDecimal) thay vì chuyển qua double.

Ví dụ:

```java
BigDecimal total = new BigDecimal("1234567890.123456789");
gen.writeNumber(total);
```

Tránh dùng double cho tiền hoặc số cần decimal precision chính xác vì binary floating-point không biểu diễn chính xác mọi số thập phân.

## 10. String escaping và Unicode

Khi ghi chuỗi, hãy dùng writeString hoặc helper tương ứng. Generator tự escape các ký tự đặc biệt cần thiết trong JSON như dấu nháy kép, dấu gạch chéo ngược và ký tự điều khiển.

```java
gen.writeStringField("message", "He said: \"Hello\"\nNext line");
```

Output JSON hợp lệ có thể hiển thị:

```json
{
  "message": "He said: \"Hello\"\nNext line"
}
```

Không tự nối chuỗi JSON:

```java
// Không nên:
String json = "{\"message\":\"" + message + "\"}";
```

Nếu message có dấu nháy, newline hoặc ký tự điều khiển, cách nối chuỗi có thể tạo JSON không hợp lệ hoặc làm thay đổi nội dung. writeString xử lý escaping theo chuẩn generator.

Unicode được ghi theo encoding của output target. Generator có thể phát ký tự Unicode trực tiếp hoặc escape tùy cấu hình/encoding; client JSON phải giải mã đúng UTF-8 theo contract. Không cần tự chuyển tiếng Việt thành chuỗi \\uXXXX nếu không có yêu cầu cụ thể.

## 11. Ghi null và xử lý null serializer

Trong custom serializer của một object không null, property con vẫn có thể null. Có ba lựa chọn phổ biến:

```java
// Ghi explicit JSON null.
gen.writeFieldName("description");
gen.writeNull();

// Dùng null serializer mặc định của provider.
gen.writeFieldName("comment");
serializers.defaultSerializeNull(gen);

// Bỏ hẳn property.
if (product.getInternalNote() != null) {
    gen.writeStringField("internalNote", product.getInternalNote());
}
```

Các kết quả khác nhau:

- Explicit null: client biết property có mặt nhưng không có giá trị.
- Omitted: client không nhận được property.
- Empty string/empty array: property có mặt với giá trị rỗng.

Nếu dùng JsonInclude trong bean serializer mặc định, Jackson có thể tự áp dụng inclusion policy. Khi custom serializer tự ghi toàn bộ object, logic lọc property do serializer viết ra quyết định; không nên mặc định rằng mọi annotation inclusion trên từng field sẽ tự động được thực thi cho những lời gọi gen.write... thủ công.

Nếu muốn tái sử dụng null serializer hoặc cấu hình null toàn mapper, dùng SerializerProvider và các API phù hợp. Nếu cần null serializer riêng cho property, xem xét JsonSerialize(nullsUsing = ...) hoặc cấu hình property writer trong kiến trúc serializer tương ứng.

## 12. Ghi ngày giờ và kiểu dữ liệu đặc biệt

Với java.time, nên để serializer đã đăng ký qua JavaTimeModule xử lý khi không cần format riêng:

```java
gen.writeFieldName("createdAt");
serializers.defaultSerializeValue(order.getCreatedAt(), gen);
```

Nếu tự chuyển thành string, phải định nghĩa rõ format, offset/timezone và precision:

```java
gen.writeStringField(
    "createdAt",
    order.getCreatedAt().toString()
);
```

Cách thứ hai dùng toString() của kiểu Java. Đây có thể là ISO representation phù hợp cho một số kiểu, nhưng không thay thế contract format cụ thể của API. Nếu cần UTC hoặc precision cố định, chuẩn hóa giá trị trước khi ghi và kiểm thử chuỗi output.

Với byte[], có thể ghi Base64:

```java
gen.writeFieldName("document");
gen.writeBinary(binaryData);
```

JSON không có kiểu binary riêng; writeBinary mã hóa dữ liệu thành representation Base64 theo variant được cấu hình. Nếu payload lớn, cân nhắc giới hạn kích thước và streaming binary thay vì giữ toàn bộ dữ liệu trong bộ nhớ.

## 13. Ghi object thông qua codec và writeObject

JsonGenerator có thể ghi một object thông qua codec gắn với generator:

```java
gen.writeObject(address);
```

Hoặc:

```java
gen.writeTree(node);
```

Các thao tác này yêu cầu generator có codec phù hợp. Trong luồng serialize do ObjectMapper quản lý, codec thường đã được gắn. Nếu tạo generator trực tiếp từ JsonFactory, có thể gắn mapper:

```java
JsonGenerator gen = factory.createGenerator(outputStream);
gen.setCodec(mapper);
```

Trong custom serializer, thường nên dùng serializers.defaultSerializeValue(value, gen) vì nó dùng SerializerProvider hiện tại và giữ các cấu hình databind của lần serialize. gen.writeObject hữu ích khi thao tác ở tầng generator có codec, nhưng cần chắc chắn codec đã được cấu hình.

Không dùng writeObject cho chính object đang được serializer xử lý vì có thể gọi lại cùng serializer và tạo recursion. Chỉ ghi object con hoặc giá trị độc lập.

## 14. Phân biệt writeRaw, writeRawValue và các phương thức write

writeString ghi một JSON string hợp lệ và tự escape nội dung. writeNumber, writeBoolean, writeNull ghi các token có kiểu tương ứng. Đây là lựa chọn mặc định nên dùng.

writeRaw ghi ký tự thô vào output mà không áp dụng đầy đủ semantics của token JSON. writeRawValue ghi một đoạn nội dung thô như một JSON value. Chúng có thể hữu ích khi tích hợp một fragment JSON đã được xác thực, nhưng rất dễ tạo output không hợp lệ nếu input không phải JSON hợp lệ.

Ví dụ nguy hiểm:

```java
// Không dùng dữ liệu bên ngoài theo cách này:
gen.writeRawValue(userSuppliedText);
```

Nếu userSuppliedText là hello, output không phải JSON value hợp lệ. Nếu nội dung được tạo từ dữ liệu không đáng tin cậy, có thể phát sinh injection hoặc phá cấu trúc document.

Nếu cần ghi một fragment JSON có sẵn, hãy parse/validate nó thành JsonNode rồi dùng writeTree, hoặc dùng parser/generator để copy token. Chỉ dùng raw output khi đã kiểm soát nguồn và xác minh fragment đúng cú pháp, đúng vị trí, đúng semantics.

## 15. Ghi cấu trúc có điều kiện

Custom serializer có thể quyết định property nào được ghi dựa trên trạng thái object:

```java
public class InvoiceSerializer extends JsonSerializer<Invoice> {
    @Override
    public void serialize(
            Invoice invoice,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeStartObject();
        gen.writeStringField("invoiceId", invoice.getId());
        gen.writeNumberField("total", invoice.getTotal());

        if (invoice.isPaid()) {
            gen.writeStringField("paymentStatus", "paid");
            gen.writeStringField("paidAt", invoice.getPaidAt().toString());
        } else {
            gen.writeStringField("paymentStatus", "pending");
        }

        gen.writeEndObject();
    }
}
```

Khi paid là false, property paidAt không được ghi. Khi paid là true, serializer ghi thêm paidAt. Cách này phù hợp với representation có cấu trúc phụ thuộc trạng thái.

Tuy nhiên, nếu property có semantics riêng, validation hoặc được tái sử dụng ở nhiều endpoint, DTO response tường minh có thể dễ bảo trì hơn một serializer lớn với nhiều nhánh.

## 16. Serializer theo ngữ cảnh property

Một kiểu Java có thể cần format khác nhau tùy property chứa nó. Ví dụ Money ở trang hiển thị có thể là object {amount, currency}, còn trong một payload khác có thể là string. Khi đó serializer có thể cần biết metadata của property.

Jackson cung cấp ContextualSerializer để tạo serializer theo BeanProperty:

```java
public class MoneySerializer
        extends JsonSerializer<Money>
        implements ContextualSerializer {

    private final boolean compact;

    public MoneySerializer() {
        this(false);
    }

    private MoneySerializer(boolean compact) {
        this.compact = compact;
    }

    @Override
    public JsonSerializer<?> createContextual(
            SerializerProvider provider,
            BeanProperty property) {
        if (property == null) {
            return this;
        }

        // Có thể đọc annotation trên property và tạo serializer phù hợp.
        return new MoneySerializer(compact);
    }

    @Override
    public void serialize(
            Money money,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {
        if (compact) {
            gen.writeString(money.toString());
            return;
        }

        gen.writeStartObject();
        gen.writeNumberField("amount", money.amount());
        gen.writeStringField("currency", money.currency());
        gen.writeEndObject();
    }
}
```

Ví dụ trên minh họa vòng đời contextualization; biến compact chưa được chọn theo annotation vì phần đọc annotation phụ thuộc thiết kế của ứng dụng. Trong triển khai thật, tạo annotation riêng hoặc dùng metadata của BeanProperty, sau đó trả về một serializer mới bất biến cho property đó.

Không lưu BeanProperty hoặc request mutable vào một serializer dùng chung theo cách làm trạng thái thay đổi giữa các lần serialize. Serializer được cache và tái sử dụng; mọi cấu hình contextual nên bất biến.

## 17. Custom serializer và polymorphic type information

Nếu kiểu được serialize có JsonTypeInfo hoặc dùng polymorphic typing, serializer phải tương thích với cơ chế ghi type metadata. Một custom serializer chỉ ghi object bằng writeStartObject()/writeEndObject() có thể không tự phát type ID mà Jackson cần.

Với serializer cần hỗ trợ polymorphic type metadata, hãy triển khai đường serializeWithType và sử dụng TypeSerializer để ghi type prefix/suffix phù hợp với shape của JSON. API hiện đại dùng WritableTypeId:

```java
WritableTypeId typeId =
    typeSer.typeId(value, JsonToken.START_OBJECT);

typeSer.writeTypePrefix(gen, typeId);
// Ghi các field của object ở đây.
typeSer.writeTypeSuffix(gen, typeId);
```

Đây là phác thảo vị trí gọi type prefix/suffix; phần field writing phải dùng cùng generator và không tự ghi một discriminator thứ hai nếu TypeSerializer đã chịu trách nhiệm. Cần đối chiếu API với Jackson version đang dùng và test JSON polymorphic thực tế.

Nếu không cần polymorphic serialization, có thể tránh tùy biến serializeWithType. Nhưng khi base type được dùng qua nhiều subtype và contract yêu cầu discriminator, không được bỏ qua type metadata chỉ vì custom serializer tạo được JSON hợp lệ về cú pháp.

## 18. Pretty printing và định dạng output

Generator có thể dùng PrettyPrinter để định dạng JSON dễ đọc:

```java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
String json = prettyWriter.writeValueAsString(product);
```

Pretty printing chỉ thay đổi whitespace và cách trình bày, không thay đổi cấu trúc dữ liệu. Với API response production, compact JSON thường giảm kích thước truyền tải; với log/debug/export, pretty output có thể dễ đọc hơn.

Nếu tạo generator trực tiếp, có thể cấu hình pretty printer trên generator hoặc writer. Không tự chèn newline/indent bằng writeRaw trong custom serializer; để generator quản lý format nhất quán.

## 19. Streaming trực tiếp với JsonFactory

Có thể dùng JsonFactory để tạo generator ghi trực tiếp ra OutputStream hoặc Writer, không cần tạo toàn bộ chuỗi JSON trong bộ nhớ:

```java
JsonFactory factory = new JsonFactory();

try (JsonGenerator gen = factory.createGenerator(outputStream)) {
    gen.writeStartObject();
    gen.writeStringField("id", "batch-1");
    gen.writeFieldName("items");
    gen.writeStartArray();

    for (Item item : items) {
        gen.writeStartObject();
        gen.writeStringField("code", item.getCode());
        gen.writeNumberField("quantity", item.getQuantity());
        gen.writeEndObject();
    }

    gen.writeEndArray();
    gen.writeEndObject();
}
```

Đây là streaming output: generator phát dữ liệu dần vào output target. Nó có thể giảm peak memory khi ghi tập dữ liệu lớn vì không cần tạo một JSON string hoàn chỉnh trước khi ghi.

Trong ứng dụng dùng ObjectMapper, custom serializer thường không tự tạo generator mới. Mapper đã tạo generator và truyền vào serializer. Chỉ tự tạo generator khi ứng dụng thực sự sở hữu luồng ghi ở tầng ngoài.

Nếu generator được truyền vào từ framework, không tự gọi close() hoặc flush() trong custom serializer. Framework hoặc caller quản lý lifecycle. Nếu chính code của bạn tạo generator, dùng try-with-resources để đóng đúng cách và giải phóng target theo cấu hình.

## 20. Trạng thái generator và lỗi cấu trúc

Generator kiểm tra một số quy tắc cấu trúc. Ví dụ:

- Ghi field name khi đang ở root hoặc trong array là sai context.
- Ghi value trong object mà chưa có field name là sai.
- Ghi writeEndObject() khi không có object mở là sai.
- Kết thúc output khi object/array chưa đóng có thể tạo JSON không hoàn chỉnh hoặc gây lỗi khi đóng generator.

Ví dụ sai:

```java
gen.writeStartObject();
gen.writeString("p-10"); // Sai: object cần field name trước value.
gen.writeEndObject();
```

Ví dụ đúng:

```java
gen.writeStartObject();
gen.writeStringField("id", "p-10");
gen.writeEndObject();
```

Khi phát hiện JsonGenerationException, kiểm tra thứ tự token và trạng thái cấu trúc trước. Không nên bắt exception rồi tiếp tục ghi như thể generator vẫn ở trạng thái hợp lệ; output có thể đã không còn sử dụng được.

## 21. Kiểm thử custom serializer

Nên test output ở cấp JSON tree thay vì so sánh chuỗi nguyên văn nếu whitespace và thứ tự field không phải contract.

### 21.1. Test cấu trúc và kiểu value

```java
@Test
void writesProductRepresentation() throws Exception {
    Product product = new Product();
    product.setId("p-10");
    product.setName("Keyboard");
    product.setPrice(new BigDecimal("49.90"));
    product.setAvailable(true);

    String json = mapper.writeValueAsString(product);
    JsonNode root = mapper.readTree(json);

    assertEquals("p-10", root.path("productId").asText());
    assertEquals("Keyboard", root.path("title").asText());
    assertTrue(root.path("price").isNumber());
    assertEquals(new BigDecimal("49.90"), root.path("price").decimalValue());
    assertTrue(root.path("inStock").asBoolean());
}
```

### 21.2. Test null và empty

Kiểm tra riêng:

- Property null được ghi thành JSON null hay bị bỏ.
- Collection null được ghi thành null hay array rỗng.
- Collection rỗng có output [].
- Phần tử null trong collection được giữ hay loại theo contract.

Không chỉ kiểm tra asText() vì cách đọc tree có thể che khác biệt giữa null, missing và string rỗng. Dùng has, hasNonNull, isNull, isArray và các method type-specific.

### 21.3. Test escaping

Ghi chuỗi có dấu nháy kép, dấu gạch chéo ngược, newline, tab và tiếng Việt. Parse output lại bằng ObjectMapper.readTree để xác nhận JSON hợp lệ và nội dung sau parse giống input.

### 21.4. Test nested object và serializer delegation

Nếu serializer gọi defaultSerializeValue cho object con, đăng ký serializer của kiểu con và xác nhận representation con được tái sử dụng. Test cả giá trị con null.

### 21.5. Test polymorphic output

Nếu serializer hỗ trợ type metadata, xác nhận discriminator xuất hiện đúng một lần, subtype đúng và deserialize ngược lại được kiểu mong đợi.

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| JSON thiếu dấu ngoặc hoặc sai cấu trúc | Không đóng object/array hoặc ghi token sai context | Ghép cặp start/end và theo dõi trạng thái token. |
| Field bị ghi mà không có tên | Gọi writeString/writeNumber trực tiếp trong object | Ghi writeFieldName trước hoặc dùng helper field. |
| Chuỗi làm JSON lỗi | Tự nối JSON hoặc dùng raw output | Dùng writeString để generator escape. |
| Số tiền mất precision | Chuyển BigDecimal sang double | Ghi bằng writeNumber(BigDecimal). |
| Object con có format không đồng nhất | Tự ghi lại logic của serializer con | Dùng SerializerProvider.defaultSerializeValue. |
| Null bị biến thành empty ngoài ý muốn | Serializer không phân biệt null và collection rỗng | Chọn và test rõ semantics của từng trạng thái. |
| Generator bị đóng giữa request | Custom serializer tự close generator được truyền vào | Để caller/framework quản lý lifecycle. |
| Type discriminator biến mất | Custom serializer không tích hợp TypeSerializer | Hỗ trợ serializeWithType nếu polymorphic contract yêu cầu. |
| JSON fragment bị chèn sai | Dùng writeRaw/writeRawValue với input không được xác thực | Parse/validate fragment hoặc ghi token bình thường. |

## 23. Quy trình triển khai

1. Xác định JSON contract cần tạo và kiểu dữ liệu cho từng property.
2. Chọn custom serializer chỉ khi cấu trúc output cần kiểm soát riêng.
3. Kế thừa JsonSerializer<T> và override serialize.
4. Ghi object/array theo đúng thứ tự token: start, field/value, nested structure và end.
5. Dùng các phương thức typed như writeString, writeNumber, writeBoolean, writeNull để giữ đúng kiểu JSON.
6. Dùng SerializerProvider.defaultSerializeValue để tái sử dụng serializer của object con khi phù hợp.
7. Đăng ký serializer qua JsonSerialize hoặc SimpleModule trước khi mapper được sử dụng.
8. Không tự đóng generator do Jackson/framework truyền vào.
9. Nếu cần polymorphic type metadata, tích hợp TypeSerializer thay vì tự ghi discriminator trùng lặp.
10. Kiểm thử JSON tree, null, empty, escaping, precision, nested object và output thực tế.

JsonGenerator cho phép custom serializer xây dựng JSON ở mức token với quyền kiểm soát cao. Khi ghi đúng cấu trúc và dùng đúng phương thức cho từng kiểu value, output sẽ hợp lệ, giữ được semantics dữ liệu và có thể tận dụng streaming để giảm bộ nhớ. Hãy để generator xử lý escaping/formatting, dùng provider để ủy quyền serializer con và giữ lifecycle generator ở đúng tầng sở hữu nó.
