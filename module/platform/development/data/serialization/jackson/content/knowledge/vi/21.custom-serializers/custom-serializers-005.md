# Tái sử dụng serializer chuẩn cho các thành phần bên trong

Khi viết custom serializer cho một lớp Java, ứng dụng thường chỉ cần thay đổi cách biểu diễn một vài phần của object. Những thành phần còn lại vẫn nên được serialize theo quy tắc Jackson đã biết: getter, annotation, naming strategy, module, custom serializer đã đăng ký và xử lý kiểu generic.

Jackson cung cấp `SerializerProvider` để custom serializer ủy quyền việc serialize các giá trị con cho serializer phù hợp. Thay vì tự viết lại logic cho mọi field, ta có thể dùng `defaultSerializeValue()` hoặc `defaultSerializeField()` để tái sử dụng serializer chuẩn trong cùng cấu hình `ObjectMapper`.

Kỹ thuật này giúp custom serializer tập trung vào phần định dạng đặc biệt, đồng thời giữ hành vi nhất quán cho các object lồng nhau, collection, map, kiểu ngày giờ và các kiểu đã có serializer riêng.

## 1. Custom serializer không cần tự serialize mọi field

Giả sử một hóa đơn có các thành phần:

```java
public class Invoice {
    private String number;
    private Customer customer;
    private List<InvoiceLine> lines;
    private Money total;

    // Constructor, getter và setter
}
```

Jackson đã biết cách serialize `Customer`, `InvoiceLine`, `List` và `Money` thông qua serializer mặc định hoặc serializer do ứng dụng đăng ký. Nếu custom serializer của `Invoice` chỉ muốn đổi tên field, thêm metadata hoặc thay đổi cấu trúc ngoài, không cần tự viết lại cách serialize từng object con.

Một custom serializer thường mở object, ghi các field cần điều khiển, rồi ủy quyền các giá trị lồng nhau cho `SerializerProvider`:

```java
public class InvoiceSerializer extends StdSerializer<Invoice> {
    public InvoiceSerializer() {
        super(Invoice.class);
    }

    @Override
    public void serialize(
            Invoice value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("invoice_number", value.getNumber());

        provider.defaultSerializeField("customer", value.getCustomer(), generator);
        provider.defaultSerializeField("items", value.getLines(), generator);
        provider.defaultSerializeField("total", value.getTotal(), generator);

        generator.writeEndObject();
    }
}
```

Ở đây serializer tự quyết định tên field `invoice_number`, còn các giá trị `customer`, `items` và `total` được serialize bằng cơ chế Jackson hiện tại. Nếu `Money` có custom serializer, serializer đó vẫn được dùng khi ghi `total`.

## 2. Vai trò của SerializerProvider

`SerializerProvider` là ngữ cảnh serialize mà Jackson truyền vào custom serializer. Nó cung cấp dịch vụ tìm serializer, xử lý null, contextualization và các cấu hình liên quan đến lần serialize hiện tại.

Những trách nhiệm thường gặp:

- Tìm serializer cho kiểu Java của giá trị cần ghi.
- Dùng serializer đã đăng ký trong module hoặc được Jackson tạo từ introspection.
- Áp dụng serializer dành cho kiểu con trong collection, map hoặc object lồng nhau.
- Ghi giá trị null bằng null serializer phù hợp.
- Cung cấp các API để custom serializer không phải tự quản lý một `ObjectMapper` khác.

Jackson truyền provider vào phương thức `serialize()`:

```java
@Override
public void serialize(
        Invoice value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {
    // Dùng generator và provider tại đây
}
```

Hãy dùng chính provider được truyền vào. Nó thuộc serialization context hiện tại và biết các serializer, module, mix-in cùng cấu hình mà mapper đã thiết lập.

## 3. Hai API ủy quyền thường dùng

### 3.1. defaultSerializeValue()

`defaultSerializeValue(value, generator)` serialize một giá trị vào vị trí hiện tại của generator. Phương thức không ghi tên field; caller phải bảo đảm generator đang ở trạng thái chờ một JSON value.

```java
generator.writeFieldName("customer");
provider.defaultSerializeValue(value.getCustomer(), generator);
```

Nếu `customer` là POJO, Jackson tìm serializer phù hợp cho kiểu runtime của nó. Nếu là collection, Jackson dùng collection serializer và serializer của từng phần tử. Nếu là kiểu có custom serializer đã đăng ký, custom serializer đó được gọi.

Phương thức này hữu ích khi code cần kiểm soát chính xác thời điểm ghi tên field hoặc đang ghi một phần tử trong array.

### 3.2. defaultSerializeField()

`defaultSerializeField(fieldName, value, generator)` ghi tên field rồi serialize giá trị tương ứng:

```java
provider.defaultSerializeField("customer", value.getCustomer(), generator);
```

Đoạn này tương đương về ý tưởng với:

```java
generator.writeFieldName("customer");
provider.defaultSerializeValue(value.getCustomer(), generator);
```

API này ngắn gọn khi custom serializer đang ghi một object và muốn ủy quyền cả tên field lẫn giá trị.

### 3.3. So sánh nhanh

| API | Ghi tên field? | Ghi value? | Trường hợp dùng |
|---|---|---|---|
| `defaultSerializeValue(value, gen)` | Không | Có | Ghi value tại vị trí hiện tại, ví dụ trong array hoặc sau `writeFieldName()` |
| `defaultSerializeField(name, value, gen)` | Có | Có | Ghi một property hoàn chỉnh trong object |
| `defaultSerializeNull(gen)` | Không | Ghi JSON `null` | Ghi null tường minh ở vị trí value |

Không gọi `defaultSerializeField()` khi generator đang ở trong array và không chờ tên field. Trong array, mỗi phần tử là một JSON value; hãy dùng `defaultSerializeValue()`.

## 4. Ví dụ đầy đủ: custom serializer chỉ thay đổi cấu trúc ngoài

Giả sử các kiểu con đã có getter/setter thông thường:

```java
public class Customer {
    private long id;
    private String name;

    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

public class InvoiceLine {
    private String sku;
    private int quantity;

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }
}

public class Invoice {
    private String number;
    private Customer customer;
    private List<InvoiceLine> lines;

    // Getter và setter
}
```

Custom serializer:

```java
public class InvoiceSerializer extends StdSerializer<Invoice> {
    public InvoiceSerializer() {
        super(Invoice.class);
    }

    @Override
    public void serialize(
            Invoice value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("type", "invoice");
        generator.writeStringField("number", value.getNumber());

        provider.defaultSerializeField("bill_to", value.getCustomer(), generator);
        provider.defaultSerializeField("line_items", value.getLines(), generator);

        generator.writeEndObject();
    }
}
```

Đăng ký serializer:

```java
SimpleModule module = new SimpleModule("invoice-module");
module.addSerializer(Invoice.class, new InvoiceSerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Khi serialize `Invoice`, custom serializer điều khiển tên `type`, `number`, `bill_to` và `line_items`. Các field bên trong `Customer` và từng `InvoiceLine` vẫn được xử lý bằng serializer tương ứng của chúng.

JSON có dạng:

```json
{
  "type": "invoice",
  "number": "INV-2026-001",
  "bill_to": {
    "id": 25,
    "name": "An"
  },
  "line_items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
```

Nếu sau này `Customer` đổi naming strategy hoặc có thêm annotation, serializer của `Invoice` không cần biết chi tiết đó. Nó chỉ ủy quyền giá trị con cho provider.

## 5. Tái sử dụng custom serializer đã đăng ký cho kiểu con

“Serializer chuẩn” ở đây không nhất thiết là serializer mặc định do Jackson tự sinh. Nó có thể là custom serializer của ứng dụng đã đăng ký trong cùng mapper.

Ví dụ `Money` có định dạng JSON riêng:

```java
public class Money {
    private BigDecimal amount;
    private String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }
}
```

Custom serializer của `Money`:

```java
public class MoneySerializer extends StdSerializer<Money> {
    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeNumberField("amount", value.getAmount());
        generator.writeStringField("currency", value.getCurrency());
        generator.writeEndObject();
    }
}
```

Đăng ký cả hai serializer:

```java
SimpleModule module = new SimpleModule("billing-module");
module.addSerializer(Money.class, new MoneySerializer());
module.addSerializer(Invoice.class, new InvoiceSerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Khi `InvoiceSerializer` gọi:

```java
provider.defaultSerializeField("total", value.getTotal(), generator);
```

provider tìm `MoneySerializer` đã đăng ký và dùng nó cho property `total`. Output có thể là:

```json
{
  "total": {
    "amount": 125.50,
    "currency": "USD"
  }
}
```

Như vậy, custom serializer cấp ngoài có thể phối hợp với nhiều serializer cấp trong theo đúng cấu hình của mapper.

## 6. Tái sử dụng serializer cho collection, array và Map

Khi một property là collection hoặc map, thường chỉ cần ủy quyền cả container:

```java
provider.defaultSerializeField("items", value.getItems(), generator);
provider.defaultSerializeField("attributes", value.getAttributes(), generator);
```

Jackson chọn serializer cho kiểu container và tiếp tục chọn serializer phù hợp cho từng phần tử hoặc value.

### 6.1. Collection chứa POJO

```java
List<InvoiceLine> lines = value.getLines();
provider.defaultSerializeField("items", lines, generator);
```

Jackson ghi JSON array và serialize từng `InvoiceLine`. Nếu `InvoiceLine` có custom serializer, serializer đó được gọi cho mỗi phần tử.

Nếu cần kiểm soát từng phần tử, có thể tự ghi array nhưng vẫn ủy quyền từng value:

```java
generator.writeArrayFieldStart("items");
for (InvoiceLine line : value.getLines()) {
    provider.defaultSerializeValue(line, generator);
}
generator.writeEndArray();
```

Cách này hữu ích khi muốn bỏ một số phần tử theo quy tắc nghiệp vụ hoặc chèn giá trị bổ sung vào array. Nếu không có yêu cầu như vậy, serialize cả collection bằng `defaultSerializeField()` ngắn gọn hơn.

### 6.2. Map chứa object

Có thể ủy quyền cả map:

```java
provider.defaultSerializeField("metadata", value.getMetadata(), generator);
```

Jackson dùng map serializer và serializer cho từng value. Nếu muốn ghi map theo thứ tự hoặc cấu trúc tùy chỉnh, có thể duyệt entry:

```java
generator.writeObjectFieldStart("metadata");
for (Map.Entry<String, Object> entry : value.getMetadata().entrySet()) {
    generator.writeFieldName(entry.getKey());
    provider.defaultSerializeValue(entry.getValue(), generator);
}
generator.writeEndObject();
```

Hãy bảo đảm key map hợp lệ cho JSON object. JSON object dùng tên property dạng chuỗi; Jackson có key serializer riêng cho map key nếu dùng cách serialize cả map.

### 6.3. Mảng Java

Mảng cũng có thể được ủy quyền trực tiếp:

```java
provider.defaultSerializeField("scores", value.getScores(), generator);
```

Jackson ghi array và serialize từng phần tử theo kiểu tương ứng. Không cần tự lặp qua mảng trừ khi muốn thay đổi cấu trúc hoặc chính sách lọc.

## 7. Null và chính sách bỏ qua thành phần bên trong

`defaultSerializeValue()` và `defaultSerializeField()` xử lý null thông qua null serializer của provider. Khi value null, kết quả thông thường là JSON `null`.

```java
provider.defaultSerializeField("customer", value.getCustomer(), generator);
```

Nếu `getCustomer()` trả null, output có field `"customer": null` trong trường hợp thông thường.

Nếu hợp đồng yêu cầu bỏ hẳn field khi null, custom serializer phải quyết định trước khi ghi:

```java
if (value.getCustomer() != null) {
    provider.defaultSerializeField("customer", value.getCustomer(), generator);
}
```

Tương tự, có thể bỏ collection rỗng:

```java
if (value.getLines() != null && !value.getLines().isEmpty()) {
    provider.defaultSerializeField("items", value.getLines(), generator);
}
```

### 7.1. Không tự động giả định @JsonInclude trên field cha được áp dụng

Khi custom serializer ghi field bằng tay, nó đang tự quyết định field nào được ghi. `@JsonInclude` đặt trên property của bean cha thường được áp dụng bởi bean serializer chuẩn khi serializer đó xử lý property. Nếu custom serializer bỏ qua bean serializer và gọi `defaultSerializeField()` trực tiếp, không nên giả định annotation property-level của field cha sẽ tự động được áp dụng như trong bean serializer.

Ví dụ:

```java
public class Invoice {
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Customer customer;
}
```

Nếu `InvoiceSerializer` luôn gọi:

```java
provider.defaultSerializeField("customer", value.getCustomer(), generator);
```

thì code custom serializer đang chủ động ghi field. Để bỏ field null một cách chắc chắn trong custom serializer, hãy kiểm tra null và chỉ ghi khi phù hợp.

Các annotation trên object con, chẳng hạn `@JsonInclude` đặt trên property bên trong `Customer`, vẫn được xử lý khi provider gọi serializer chuẩn của `Customer`.

## 8. Giữ serializer của kiểu con có polymorphic type information

Một object con có thể được serialize đa hình. Ví dụ:

```java
public abstract class PaymentMethod {
}

public class CardPayment extends PaymentMethod {
    private String last4;
    // Getter và setter
}

public class BankTransfer extends PaymentMethod {
    private String iban;
    // Getter và setter
}
```

Base type có cấu hình type information:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank")
})
public abstract class PaymentMethod {
}
```

Custom serializer của invoice chỉ cần ủy quyền:

```java
provider.defaultSerializeField("payment", value.getPaymentMethod(), generator);
```

Provider dùng cơ chế serializer phù hợp cho runtime value và type information đã cấu hình. Nếu cần kiểm soát trực tiếp typed serializer, provider có API `findTypedValueSerializer()`; tuy nhiên, với phần lớn custom serializer, `defaultSerializeValue()` hoặc `defaultSerializeField()` là lựa chọn ít lỗi hơn.

Không tự gọi serializer thuần của subtype rồi giả định type id sẽ được ghi. Khi tự tìm serializer và gọi `serialize()` trực tiếp, có thể bỏ qua typed serializer/type serializer mà Jackson dùng để thêm discriminator. Hãy ưu tiên API ủy quyền mặc định nếu muốn giữ polymorphic behavior.

## 9. Contextual serializer và metadata riêng của property

Serializer có thể phụ thuộc property mà nó đang serialize. Ví dụ, cùng kiểu `Money` nhưng một property cần hiển thị số tiền theo đơn vị nhỏ, property khác cần định dạng đã làm tròn. Jackson hỗ trợ contextual serializer để serializer nhận metadata của property.

Khi custom serializer cha gọi `provider.defaultSerializeField("total", value.getTotal(), generator)`, provider tìm serializer theo kiểu runtime của giá trị và serialization context hiện tại. Tuy nhiên, code đang ghi field thủ công không tự mang theo toàn bộ metadata của `BeanProperty` mà bean serializer chuẩn có thể dùng, chẳng hạn annotation `@JsonSerialize(using = ...)` chỉ đặt trên property của lớp cha.

Nếu cần tôn trọng serializer hoặc converter riêng của một property cụ thể, có thể:

- Để bean serializer chuẩn xử lý property đó thay vì tự ghi field.
- Thiết kế custom serializer để nhận metadata property và contextualize serializer phù hợp.
- Dùng `SerializerProvider.findValueSerializer(type, property)` hoặc `findTypedValueSerializer(...)` khi thực sự cần lấy serializer gắn với `BeanProperty`.

Việc gọi serializer trực tiếp đòi hỏi hiểu rõ typed serialization và null handling. Không nên dùng API tìm serializer thủ công chỉ để thay thế một lời gọi `defaultSerializeField()` đơn giản.

## 10. Tìm serializer thủ công khi cần kiểm soát nâng cao

`SerializerProvider` cung cấp API tìm serializer. Ví dụ:

```java
JsonSerializer<Object> serializer = provider.findValueSerializer(
    value.getCustomer().getClass()
);

serializer.serialize(value.getCustomer(), generator, provider);
```

Đây là ví dụ tối giản cho một giá trị khác null. Nó hữu ích khi custom serializer cần giữ một tham chiếu serializer để gọi nhiều lần hoặc cần thực hiện logic trước/sau khi gọi serializer.

Tuy nhiên, cách gọi trực tiếp `JsonSerializer.serialize()` không tự xử lý mọi trường hợp như API ủy quyền mặc định. Cần tự xử lý null, và nếu kiểu cần polymorphic type id, phải dùng typed serializer thích hợp. Khi cần serializer có type information:

```java
JsonSerializer<Object> serializer = provider.findTypedValueSerializer(
    value.getCustomer().getClass(),
    true,
    null
);

serializer.serialize(value.getCustomer(), generator, provider);
```

Các overload có thể nhận `JavaType` và `BeanProperty` để mô tả kiểu generic hoặc ngữ cảnh property. Hãy dùng chúng khi yêu cầu thực sự cần thiết; nếu chỉ muốn serialize object con theo mapper hiện tại, `defaultSerializeValue()` dễ hiểu và an toàn hơn.

## 11. Tránh tạo ObjectMapper mới bên trong custom serializer

Một lỗi thường gặp là tạo mapper mới trong mỗi lần serialize object con:

```java
@Override
public void serialize(
        Invoice value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {

    ObjectMapper mapper = new ObjectMapper();
    mapper.writeValue(generator, value.getCustomer());
}
```

Cách này có nhiều vấn đề:

- Mapper mới có thể không có module đã đăng ký trong ứng dụng.
- Naming strategy, mix-in, serializer tùy chỉnh và inclusion config có thể khác.
- Khởi tạo mapper lặp lại gây chi phí không cần thiết.
- Dễ tạo recursion nếu mapper mới lại dùng serializer của kiểu đang xử lý.
- Có thể làm việc kiểm soát output và exception phức tạp hơn.

Hãy dùng:

```java
provider.defaultSerializeValue(value.getCustomer(), generator);
```

Provider thuộc đúng mapper đang serialize `Invoice`, nên object con được xử lý trong cùng cấu hình.

## 12. Tránh recursion khi serialize chính kiểu hiện tại

Giả sử custom serializer đang xử lý `Invoice`. Đoạn sau là sai:

```java
provider.defaultSerializeValue(value, generator);
```

Giá trị `value` vẫn là `Invoice`, vì vậy provider tìm lại `InvoiceSerializer`. Serializer lại gọi `defaultSerializeValue(value, generator)`, tạo vòng lặp đệ quy cho đến khi lỗi stack overflow hoặc lỗi liên quan.

Trong custom serializer, hãy ủy quyền cho **các thành phần bên trong** như `Customer`, `List<InvoiceLine>` hoặc `Money`, không gọi lại chính object đang được serialize.

Nếu mục tiêu là giữ serializer bean mặc định của cùng một lớp nhưng chỉ sửa một vài property, hãy cân nhắc `BeanSerializerModifier`, `BeanPropertyWriter` hoặc custom serializer dạng delegate được xây dựng có chủ đích. Không dùng provider để gọi lại serializer hiện tại một cách trực tiếp.

## 13. Kết hợp custom serializer với module và mapper

Đăng ký serializer trong `SimpleModule` trước khi mapper được sử dụng:

```java
SimpleModule module = new SimpleModule("invoice-module");
module.addSerializer(Invoice.class, new InvoiceSerializer());
module.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = JsonMapper.builder()
    .addModule(module)
    .build();
```

Sau khi mapper được cấu hình, mọi lần serialize `Invoice` qua mapper này sẽ dùng `InvoiceSerializer`; các object `Money` lồng bên trong sẽ dùng `MoneySerializer` khi được provider ủy quyền.

Trong ứng dụng có dependency injection, hãy cấu hình mapper/module ở composition root hoặc dùng mapper do framework cung cấp. Không tạo mapper riêng trong từng service nếu mục tiêu là chia sẻ cùng hợp đồng JSON.

### 13.1. Không đăng ký module sau khi mapper đã hoạt động

Mapper và serializer provider có cache serializer. Hãy đăng ký module, mix-in và các cấu hình cần thiết trước khi mapper được chia sẻ cho nhiều thread. Việc thay đổi cấu hình muộn có thể gây hành vi khó đoán hoặc không nhất quán giữa các lần serialize.

### 13.2. Tái sử dụng ObjectWriter khi cần cấu hình đầu ra riêng

Nếu cùng một mapper cần nhiều cấu hình serialize, có thể tạo `ObjectWriter` bất biến:

```java
ObjectWriter invoiceWriter = mapper.writerFor(Invoice.class);
String json = invoiceWriter.writeValueAsString(invoice);
```

`ObjectWriter` không thay thế `SerializerProvider` bên trong custom serializer. Nó là API ở tầng gọi để giữ kiểu gốc và cấu hình writer; provider vẫn là cơ chế để custom serializer ủy quyền object con.

## 14. Ví dụ JUnit kiểm tra việc tái sử dụng serializer con

Có thể xác nhận serializer con được gọi bằng cách kiểm tra cấu trúc JSON mà nó tạo ra.

```java
class InvoiceSerializerTest {
    private final ObjectMapper mapper;

    InvoiceSerializerTest() {
        SimpleModule module = new SimpleModule();
        module.addSerializer(Money.class, new MoneySerializer());
        module.addSerializer(Invoice.class, new InvoiceSerializer());

        mapper = new ObjectMapper();
        mapper.registerModule(module);
    }

    @Test
    void delegatesNestedMoneyToRegisteredSerializer() throws Exception {
        Invoice invoice = sampleInvoiceWithTotal(
            new Money(new BigDecimal("125.50"), "USD")
        );

        JsonNode json = mapper.readTree(mapper.writeValueAsString(invoice));

        assertEquals("125.50", json.get("total").get("amount").decimalValue().toPlainString());
        assertEquals("USD", json.get("total").get("currency").asText());
    }
}
```

Test này xác nhận field `total` được serialize bằng định dạng do `MoneySerializer` định nghĩa. Nếu `InvoiceSerializer` tự ghi `Money` thành chuỗi hoặc map thủ công, test sẽ phát hiện cấu trúc khác mong muốn.

Một test khác có thể xác nhận null policy của custom serializer:

```java
@Test
void omitsCustomerWhenCustomSerializerChoosesToSkipNull() throws Exception {
    Invoice invoice = sampleInvoiceWithCustomer(null);

    JsonNode json = mapper.readTree(mapper.writeValueAsString(invoice));

    assertFalse(json.has("customer"));
}
```

Test này chỉ đúng nếu `InvoiceSerializer` có điều kiện bỏ field null. Nếu serializer luôn gọi `defaultSerializeField()`, JSON có thể chứa `"customer": null`.

## 15. Những lỗi thường gặp

**Tự viết lại serializer cho mọi object con.** Việc này lặp logic Jackson, dễ bỏ sót module, annotation hoặc custom serializer. Dùng `SerializerProvider` để ủy quyền.

**Gọi `writeString()` với JSON đã serialize thành chuỗi.** Nếu muốn object lồng nhau, hãy ghi field name rồi gọi `defaultSerializeValue()` hoặc `defaultSerializeField()`. Ghi JSON dưới dạng string sẽ tạo một JSON string, không phải object.

**Tạo `ObjectMapper` mới trong custom serializer.** Mapper mới có thể mất cấu hình và gây recursion. Dùng provider được truyền vào.

**Gọi provider với chính object đang serialize.** Điều này có thể gọi lại custom serializer vô hạn. Chỉ ủy quyền cho các thành phần con hoặc dùng một delegate được thiết kế riêng.

**Dùng `defaultSerializeField()` trong array.** Array không có tên field; dùng `defaultSerializeValue()` cho từng phần tử.

**Quên xử lý null theo hợp đồng output.** Provider thường ghi JSON null. Nếu muốn bỏ property, kiểm tra null trước khi ghi.

**Cho rằng annotation trên field cha tự động chạy khi custom serializer ghi field bằng tay.** Custom serializer phải tự áp dụng chính sách inclusion hoặc ủy quyền bean property theo cách phù hợp.

**Tự tìm serializer rồi gọi `serialize()` mà quên type information.** Với polymorphic value, ưu tiên `defaultSerializeValue()`/`defaultSerializeField()` hoặc typed serializer.

**Đăng ký module sau khi mapper đã dùng.** Cấu hình mapper và serializer trước khi chia sẻ mapper.

## 16. Quy trình viết custom serializer có ủy quyền

1. Xác định phần JSON thực sự cần định dạng đặc biệt.
2. Liệt kê các thành phần con đã có serializer chuẩn hoặc custom serializer được đăng ký.
3. Dùng `JsonGenerator` để ghi cấu trúc ngoài và scalar cần kiểm soát.
4. Dùng `defaultSerializeField()` cho property trong object; dùng `defaultSerializeValue()` cho value ở vị trí hiện tại hoặc phần tử array.
5. Để provider chọn serializer cho POJO, collection, map, kiểu Java Time và các kiểu con.
6. Quyết định rõ cách ghi null, bỏ field và xử lý collection rỗng trong custom serializer.
7. Tránh gọi lại serializer của chính object hiện tại.
8. Chỉ tìm serializer thủ công khi cần property context, typed serializer hoặc tối ưu có chủ đích.
9. Đăng ký module trên mapper dùng trong ứng dụng trước khi mapper được chia sẻ.
10. Viết test xác nhận serializer con đã đăng ký được sử dụng và JSON có đúng cấu trúc mong đợi.

## Kết luận

Custom serializer có thể kiểm soát phần JSON đặc biệt mà vẫn tái sử dụng toàn bộ serializer của Jackson cho các thành phần bên trong. `SerializerProvider.defaultSerializeValue()` ghi một giá trị tại vị trí hiện tại; `defaultSerializeField()` ghi tên field và giá trị. Provider tìm serializer phù hợp trong cùng serialization context, bao gồm serializer mặc định, serializer đã đăng ký cho kiểu con và serializer của collection/map. Hãy dùng provider thay vì tạo mapper mới, xử lý null và inclusion có chủ đích khi ghi field thủ công, đồng thời tránh gọi lại serializer của chính object đang xử lý để không tạo recursion.
