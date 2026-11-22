# Xử lý lớp lồng và yêu cầu có đối tượng bao ngoài

Khi thiết kế model Java để Jackson đọc JSON, cần phân biệt **lớp lồng tĩnh** (static nested class) với **lớp thành viên không tĩnh** (non-static member inner class). Hai kiểu khai báo có thể trông gần giống nhau trong mã nguồn, nhưng chúng có cách tạo object khác nhau. Lớp lồng tĩnh có thể được khởi tạo độc lập; lớp inner không tĩnh luôn gắn với một instance cụ thể của lớp bao ngoài.

Sự khác biệt này trở nên quan trọng khi deserialize. Jackson databind thường tạo object đích thông qua constructor hoặc creator mà nó có thể gọi. Với một inner class không tĩnh, constructor ở bytecode cần có tham chiếu đến instance bao ngoài. JSON lồng nhau chỉ mô tả cấu trúc dữ liệu; nó không tự cung cấp tham chiếu Java đó. Vì vậy, Jackson không thể mặc nhiên tạo inner object như một POJO độc lập trong mọi trường hợp.

Trong DTO dùng cho JSON, lựa chọn đơn giản và dễ bảo trì nhất thường là lớp top-level hoặc `static` nested class. Nếu phải làm việc với một inner class legacy có yêu cầu enclosing instance, ứng dụng cần tạo instance bao ngoài trước và cung cấp cách khởi tạo inner object rõ ràng, chẳng hạn cập nhật một instance có sẵn hoặc viết deserializer tùy chỉnh.

## 1. Phân biệt các loại lớp lồng trong Java

Java cho phép khai báo một lớp bên trong lớp khác. Tuy nhiên, không phải mọi lớp được viết bên trong một lớp khác đều có cùng ngữ nghĩa.

| Loại | Đặc điểm | Có cần instance bao ngoài để tạo object? |
|---|---|---|
| Top-level class | Được khai báo trực tiếp trong package. | Không. |
| Static nested class | Được khai báo bên trong lớp khác với từ khóa `static`. | Không. |
| Non-static member inner class | Được khai báo bên trong lớp khác mà không có `static`. | Có. |
| Local class | Được khai báo bên trong method hoặc block. | Có thể giữ tham chiếu đến biến/local context được capture; không phù hợp làm DTO công khai. |
| Anonymous class | Lớp không có tên, thường được tạo tại biểu thức. | Phụ thuộc ngữ cảnh tạo; không phù hợp làm kiểu dữ liệu trao đổi JSON. |

Ví dụ:

```java
public class Order {
    private String orderId;

    // Static nested class: không cần một Order instance để tạo.
    public static class LineItem {
        private String sku;
        private int quantity;
    }

    // Non-static inner class: cần một Order instance cụ thể.
    public class AuditInfo {
        private String createdBy;
    }
}
```

Hai cách tạo object khác nhau:

```java
Order.LineItem line = new Order.LineItem();

Order order = new Order();
Order.AuditInfo audit = order.new AuditInfo();
```

Với `LineItem`, tên lớp bao ngoài chỉ là một phần của tên kiểu. Object `LineItem` không cần một object `Order` cụ thể. Với `AuditInfo`, cú pháp `order.new AuditInfo()` thể hiện rõ instance bao ngoài mà inner object sẽ gắn vào.

### 1.1. Static nested class gần giống top-level class

Một static nested class không có tham chiếu `this` ngầm định đến instance của lớp bao ngoài. Nó có thể truy cập thành viên static của lớp bao ngoài, nhưng muốn dùng trạng thái instance thì phải nhận một tham chiếu tường minh.

```java
public class Customer {
    private String customerCode;

    public static class Address {
        private String city;
        private String country;
    }
}
```

Jackson có thể tạo `Customer.Address` theo các quy tắc POJO thông thường, miễn là constructor, visibility và thuộc tính được cấu hình phù hợp. Không cần một `Customer` instance chỉ để tạo `Address`.

### 1.2. Non-static inner class giữ enclosing instance

Inner class không tĩnh có thể truy cập trực tiếp thành viên instance của lớp bao ngoài:

```java
public class Order {
    private final String orderId;

    public Order(String orderId) {
        this.orderId = orderId;
    }

    public class AuditInfo {
        public String orderReference() {
            return orderId;
        }
    }
}
```

`AuditInfo` có thể đọc `orderId` mà không cần nhận tham số trong method, vì Java gắn nó với `Order` đã tạo ra nó. Điều này tiện cho một số mô hình domain, nhưng khiến `AuditInfo` không còn là một object độc lập có thể được tạo chỉ từ các field JSON.

## 2. Vì sao Jackson cần đối tượng bao ngoài?

Khi biên dịch một inner class không tĩnh, compiler Java biểu diễn tham chiếu enclosing instance trong cấu trúc class. Ở mức bytecode, constructor của inner class có thêm tham số ngầm định mang kiểu lớp bao ngoài.

Ví dụ mã nguồn:

```java
public class Envelope {
    public class Payload {
        private String value;

        public Payload() {
        }
    }
}
```

Về mặt khái niệm, constructor được biên dịch có hình dạng tương tự:

```text
Envelope$Payload(Envelope enclosingInstance)
```

Đây là tham số do compiler quản lý, không phải tham số mà lập trình viên khai báo như một thuộc tính JSON. Muốn tạo `Payload`, JVM phải có một `Envelope` instance để gắn vào.

Trong khi đó, lời gọi databinding thông thường:

```java
Envelope.Payload payload = mapper.readValue(
    json,
    Envelope.Payload.class
);
```

chỉ cung cấp kiểu đích `Envelope.Payload`. JSON không cho Jackson biết phải dùng `Envelope` instance nào, và `ObjectMapper` cũng không thể tự suy ra một instance bao ngoài có đúng trạng thái nghiệp vụ. Vì thế, cơ chế tạo POJO mặc định không có đủ thông tin để khởi tạo inner object.

Thông báo lỗi cụ thể phụ thuộc phiên bản Jackson và đường mapping, nhưng thường là một lỗi định nghĩa/khởi tạo kiểu, chẳng hạn `InvalidDefinitionException` với nội dung nói rằng non-static inner class không thể được tạo theo cách thông thường. Không nên dựa vào chính xác câu chữ exception; hãy nhận diện nguyên nhân từ cấu trúc lớp và constructor.

### 2.1. JSON lồng nhau không đồng nghĩa Java inner class

JSON có thể biểu diễn object lồng nhau:

```json
{
  "orderId": "O-100",
  "audit": {
    "createdBy": "system"
  }
}
```

Đây chỉ là quan hệ dữ liệu: object ngoài có thuộc tính `audit`, giá trị của thuộc tính đó là một object JSON. JSON không chứa khái niệm enclosing instance, `this$0`, hay tham chiếu đến một object Java đã tồn tại.

Do đó, một JSON object lồng nhau có thể ánh xạ tự nhiên vào static nested class hoặc top-level class. Nó không tự giải quyết yêu cầu tạo một non-static inner class.

### 2.2. Có constructor không tham số trong mã nguồn vẫn chưa đủ

Trong ví dụ trên, `Payload()` nhìn như constructor không tham số. Nhưng ở mức bytecode, nó vẫn nhận enclosing instance. Jackson không thể gọi nó như constructor không tham số của một POJO độc lập.

Thêm setter, đổi visibility field, thêm `@JsonProperty` hoặc bật field visibility không loại bỏ tham số enclosing instance. Các annotation điều chỉnh mapping thuộc tính; chúng không tạo ra object bao ngoài cần thiết.

### 2.3. `@JsonCreator` không tự cung cấp enclosing instance

`@JsonCreator` giúp Jackson chọn constructor hoặc factory method để tạo object và liên kết tham số với dữ liệu JSON. Nó hữu ích cho immutable class, nhưng không tự tìm hoặc tạo một instance lớp bao ngoài cho inner class không tĩnh.

Nếu model thực sự cần enclosing instance, phải cung cấp instance đó qua một cơ chế khởi tạo rõ ràng. Trong đa số DTO, chuyển sang static nested class hoặc top-level class đơn giản và ít phụ thuộc phiên bản hơn.

## 3. Lựa chọn ưu tiên: chuyển DTO thành static nested class

Nếu lớp lồng chỉ nhằm nhóm các kiểu request/response liên quan đến lớp ngoài, hãy khai báo nó là `static`.

```java
public class OrderDto {
    private String orderId;
    private List<LineDto> lines;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public List<LineDto> getLines() {
        return lines;
    }

    public void setLines(List<LineDto> lines) {
        this.lines = lines;
    }

    public static class LineDto {
        private String sku;
        private int quantity;

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }
}
```

JSON tương ứng:

```json
{
  "orderId": "O-100",
  "lines": [
    { "sku": "BOOK-01", "quantity": 2 },
    { "sku": "PEN-02", "quantity": 5 }
  ]
}
```

Deserialize:

```java
ObjectMapper mapper = new ObjectMapper();
OrderDto order = mapper.readValue(json, OrderDto.class);

OrderDto.LineDto firstLine = order.getLines().get(0);
System.out.println(firstLine.getSku());
```

Jackson có thể tạo `OrderDto` và từng `LineDto` bằng cơ chế databinding thông thường. Quan hệ lồng nhau được thể hiện bằng thuộc tính `lines`, không cần một instance bao ngoài ẩn trong từng `LineDto`.

### 3.1. Khi nào nên dùng top-level DTO?

Static nested class phù hợp khi kiểu chỉ có ý nghĩa trong phạm vi một nhóm DTO. Top-level class phù hợp khi kiểu được dùng rộng rãi bởi nhiều service, module hoặc API. Cả hai đều tránh enclosing instance ngầm định.

| Tiêu chí | Static nested DTO | Top-level DTO |
|---|---|---|
| Phạm vi sử dụng | Chủ yếu gắn với một nhóm request/response. | Được dùng ở nhiều khu vực. |
| Tổ chức source | Nhóm các kiểu liên quan trong một file/lớp. | Mỗi kiểu có tên và file riêng. |
| Khởi tạo bởi Jackson | Không cần instance bao ngoài. | Không cần instance bao ngoài. |
| Tái sử dụng | Có thể tái sử dụng, nhưng tên kiểu gắn với lớp chứa. | Dễ import và tái sử dụng độc lập. |

### 3.2. Nested record

Record thành viên trong một class được Java xem là implicitly static. Vì vậy, nested record không giữ enclosing instance như member inner class thông thường.

```java
public class OrderDtos {
    public record Line(String sku, int quantity) {
    }

    public record Order(String orderId, List<Line> lines) {
    }
}
```

Jackson phiên bản phù hợp có thể hỗ trợ record thông qua cơ chế creator tương ứng. Cần bảo đảm JDK và Jackson version của dự án hỗ trợ record; việc record là static không tự giải quyết mọi yêu cầu constructor hoặc module khác.

## 4. Dùng `@JsonCreator` cho static nested class bất biến

Không phải DTO nào cũng cần constructor không tham số và setter. Một static nested class có thể bất biến, dùng `final` field và `@JsonCreator`:

```java
public class ApiModels {
    public static class Address {
        private final String city;
        private final String country;

        @JsonCreator
        public Address(
            @JsonProperty("city") String city,
            @JsonProperty("country") String country
        ) {
            this.city = city;
            this.country = country;
        }

        public String getCity() {
            return city;
        }

        public String getCountry() {
            return country;
        }
    }
}
```

Jackson có thể đọc tên field JSON, gọi creator và tạo `ApiModels.Address` mà không cần `ApiModels` instance. Đây là cách thích hợp khi muốn nhóm kiểu theo namespace nhưng vẫn giữ khả năng tạo object độc lập.

`@JsonCreator` cần được dùng với tham số có thể liên kết rõ ràng tới tên property. Với Jackson 2.x, `@JsonProperty` trên tham số là cách tường minh và dễ đọc. Cấu hình parameter names module hoặc compiler metadata cũng có thể tham gia trong các dự án phù hợp, nhưng không nên dựa vào metadata ngầm nếu hợp đồng cần ổn định.

## 5. Nếu phải giữ non-static inner class

Có những model legacy hoặc domain object cố ý dùng inner class vì inner object phải truy cập trạng thái của outer object. Trong trường hợp đó, cần phân biệt hai tình huống:

1. Ứng dụng đã có outer instance và chỉ cần nạp dữ liệu vào inner instance được tạo từ outer đó.
2. Jackson phải tạo inner instance trong lúc deserialize một property lồng nhau; khi ấy cần cung cấp enclosing instance bằng cơ chế tùy chỉnh.

Không nên mong đợi `ObjectMapper` tự đoán outer instance dựa vào cấu trúc JSON.

### 5.1. Tạo inner instance trước rồi cập nhật bằng `readerForUpdating`

Nếu inner class có setter hoặc field có thể cập nhật, ứng dụng có thể tạo instance bằng cú pháp Java rồi yêu cầu Jackson cập nhật instance đó:

```java
public class Invoice {
    private final String invoiceId;

    public Invoice(String invoiceId) {
        this.invoiceId = invoiceId;
    }

    public class Note {
        private String text;

        public void setText(String text) {
            this.text = text;
        }

        public String getText() {
            return text;
        }

        public String invoiceReference() {
            return invoiceId;
        }
    }
}
```

Tạo instance theo đúng enclosing object:

```java
Invoice invoice = new Invoice("INV-2026-001");
Invoice.Note note = invoice.new Note();

ObjectReader updater = mapper.readerForUpdating(note);
updater.readValue("""
    { "text": "Payment received" }
    """);

System.out.println(note.invoiceReference());
System.out.println(note.getText());
```

`readerForUpdating(note)` nhận object đã tồn tại làm giá trị đích, vì vậy Jackson không phải tự gọi constructor inner class để tạo root object mới. Đây là cách hữu ích khi ứng dụng kiểm soát được vòng đời outer và inner instance.

Giới hạn cần hiểu:

- Inner object phải có thể được cập nhật bằng cơ chế property access mà Jackson nhận diện.
- Đây là cập nhật một root object đã có. Nó không tự động làm cho mọi property inner class lồng sâu bên trong một object khác có thể được tạo mới.
- Không chia sẻ object đích mutable giữa nhiều request đồng thời.
- `readerForUpdating` có thể giữ lại thuộc tính không xuất hiện trong JSON vì mục tiêu là cập nhật object hiện tại; hãy kiểm thử semantics này nếu dữ liệu thiếu có ý nghĩa.

### 5.2. Tạo inner object trong code nghiệp vụ rồi gắn vào outer object

Nếu JSON là dữ liệu đầu vào cho một domain object, thường dễ kiểm soát hơn khi deserialize vào DTO độc lập rồi chuyển sang domain model:

```java
public class InvoiceRequest {
    private String invoiceId;
    private NoteRequest note;

    public static class NoteRequest {
        private String text;
        // getter/setter
    }
}
```

Sau khi Jackson tạo DTO, service tạo domain object và inner object bằng đúng outer instance:

```java
InvoiceRequest request = mapper.readValue(json, InvoiceRequest.class);

Invoice invoice = new Invoice(request.getInvoiceId());
Invoice.Note note = invoice.new Note();
note.setText(request.getNote().getText());
invoice.setNote(note);
```

Cách này tách hai trách nhiệm: Jackson ánh xạ định dạng bên ngoài vào DTO, còn domain layer kiểm soát invariant và quan hệ object. Nó cũng tránh việc custom deserializer phải biết cách tạo một domain object có trạng thái phức tạp.

## 6. Custom deserializer khi cần cung cấp outer instance

Nếu hợp đồng yêu cầu Jackson deserialize trực tiếp một kiểu inner class không tĩnh, có thể viết custom deserializer. Deserializer phải biết outer instance nào sẽ sở hữu inner object.

Một cách truyền thông tin theo từng thao tác là dùng `InjectableValues` của Jackson 2.x. Deserializer lấy owner từ `DeserializationContext`, tạo inner object qua cú pháp `owner.new Detail()` rồi gán dữ liệu JSON.

### 6.1. Khai báo domain class

```java
public class Order {
    private final String orderId;
    private Detail detail;

    public Order(String orderId) {
        this.orderId = orderId;
    }

    public Detail newDetail() {
        return new Detail();
    }

    public void setDetail(Detail detail) {
        this.detail = detail;
    }

    public Detail getDetail() {
        return detail;
    }

    public class Detail {
        private String note;

        public void setNote(String note) {
            this.note = note;
        }

        public String getNote() {
            return note;
        }

        public String getOrderId() {
            return orderId;
        }
    }
}
```

### 6.2. Viết deserializer

```java
public final class DetailDeserializer
        extends StdDeserializer<Order.Detail> {

    public DetailDeserializer() {
        super(Order.Detail.class);
    }

    @Override
    public Order.Detail deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        Order owner = (Order) context.findInjectableValue(
            "orderOwner", null, null);

        JsonNode node = parser.getCodec().readTree(parser);

        Order.Detail detail = owner.newDetail();
        detail.setNote(node.path("note").asText(null));
        return detail;
    }
}
```

Deserializer không giữ owner trong field. Nó lấy owner từ context của lần đọc hiện tại, vì vậy có thể dùng cùng định nghĩa deserializer cho nhiều `Order` instance mà không gắn nhầm inner object vào một outer object dùng chung.

### 6.3. Đăng ký module và tạo reader theo owner

```java
ObjectMapper mapper = new ObjectMapper();

SimpleModule module = new SimpleModule();
module.addDeserializer(Order.Detail.class, new DetailDeserializer());
mapper.registerModule(module);

Order order = new Order("O-100");

InjectableValues injectables = new InjectableValues.Std()
    .addValue("orderOwner", order);

ObjectReader detailReader = mapper
    .readerFor(Order.Detail.class)
    .with(injectables);

Order.Detail detail = detailReader.readValue("""
    { "note": "Handle with care" }
    """);

order.setDetail(detail);
```

`ObjectReader.with(InjectableValues)` tạo một reader mang tập giá trị inject cho lần đọc. Trong ví dụ, `orderOwner` được cung cấp cho custom deserializer để tạo đúng `Order.Detail` thuộc về `order`.

Đây là ví dụ minh họa cơ chế. Khi dùng trong ứng dụng, cần xử lý rõ trường hợp injectable value bị thiếu hoặc sai kiểu, kiểm tra JSON shape và validation nội dung. Reader chứa owner cụ thể chỉ nên dùng cho thao tác hoặc owner tương ứng; không giữ reader đó thành singleton toàn ứng dụng nếu mỗi request có một outer instance khác nhau.

### 6.4. Vì sao không lưu outer instance trong deserializer singleton?

Một deserializer đăng ký trong mapper thường được tái sử dụng. Nếu constructor deserializer nhận một outer object rồi lưu vào field, tất cả lần deserialize sau có thể tạo inner object gắn với cùng một outer instance. Điều này gây sai liên kết, rò rỉ dữ liệu giữa request và race condition.

Nếu dùng owner-specific deserializer, phải tạo phạm vi mapper/module riêng cho owner đó và không chia sẻ ngoài phạm vi. Cách inject theo reader/context thường thể hiện rõ hơn rằng owner thuộc về một lần xử lý. Tuy nhiên, DTO độc lập vẫn là thiết kế dễ hiểu và ít rủi ro hơn.

## 7. Xử lý property inner class nằm bên trong outer object

Một trường hợp khó hơn là muốn deserialize cả object ngoài và property inner class trong một lần gọi:

```json
{
  "orderId": "O-100",
  "detail": {
    "note": "Handle with care"
  }
}
```

Model:

```java
public class Order {
    private String orderId;
    private Detail detail;

    public class Detail {
        private String note;
    }
}
```

Khi Jackson deserialize property `detail`, deserializer của `Detail` cần owner là instance `Order` vừa được tạo. Cơ chế bean property thông thường không tự động chuyển parent bean đang được deserialize thành tham số enclosing instance của constructor inner class. Việc có property JSON lồng bên trong không làm phát sinh liên kết Java đó.

Các hướng thiết kế có thể cân nhắc:

1. **Đổi `Detail` thành static nested class** nếu nó chỉ là dữ liệu con.
2. **Dùng DTO riêng** rồi map sang domain object sau khi deserialize.
3. **Viết custom deserializer cho `Order`** để đọc object JSON, tạo `Order` trước, rồi gọi `order.new Detail()` và gán các field.
4. **Dùng một custom setter/factory ở domain layer** nếu ứng dụng kiểm soát quá trình tạo và gắn detail.

Nếu chọn custom deserializer cho toàn bộ `Order`, logic phải kiểm soát cả thứ tự đọc, field thiếu/null, field lạ và các thuộc tính còn lại. Ví dụ đơn giản:

```java
public final class OrderDeserializer extends StdDeserializer<Order> {
    public OrderDeserializer() {
        super(Order.class);
    }

    @Override
    public Order deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonNode root = parser.getCodec().readTree(parser);
        String orderId = root.path("orderId").asText();

        Order order = new Order(orderId);
        JsonNode detailNode = root.path("detail");

        if (!detailNode.isMissingNode() && !detailNode.isNull()) {
            Order.Detail detail = order.newDetail();
            detail.setNote(detailNode.path("note").asText(null));
            order.setDetail(detail);
        }

        return order;
    }
}
```

Đây là cách tiếp cận có kiểm soát: custom deserializer tạo outer object trước rồi mới tạo inner object thông qua outer đó. Khi triển khai thực tế, phải đăng ký deserializer và bổ sung mapping cho mọi field cần thiết. Với model phức tạp, nên dùng DTO độc lập để không biến deserializer thành nơi lặp lại toàn bộ logic mapping và validation của domain.

## 8. Serialization và deserialization không đối xứng

Một inner object đã tồn tại có thể được serialize vì Jackson đang nhận một instance cụ thể. Serializer có thể đọc các thuộc tính hiển thị của instance đó. Khi deserialize, Jackson phải tạo một instance mới và cần enclosing object tương ứng.

Do đó, một lớp inner có thể serialize thành JSON nhưng deserialize ngược lại thất bại. Đây là lý do một bài test chỉ gọi `writeValueAsString` không chứng minh model có thể round-trip.

Ngoài ra, inner class có tham chiếu ngầm tới outer object. Theo cấu hình visibility mặc định, tham chiếu tổng hợp do compiler tạo thường không phải property JSON công khai mà ứng dụng muốn trao đổi. Nhưng nếu bật field visibility rộng, dùng mix-in hoặc custom introspection, cần cẩn thận để không vô tình đưa tham chiếu enclosing vào output, gây vòng lặp hoặc lộ cấu trúc nội bộ.

Nếu JSON phải đại diện ổn định cho domain object, nên định nghĩa rõ DTO và các field được phép xuất. Không dựa vào việc Jackson tình cờ bỏ qua synthetic field trong một cấu hình cụ thể.

## 9. Những annotation không giải quyết được enclosing instance

Một số cách sửa thường được thử nhưng không giải quyết nguyên nhân gốc:

| Cách thử | Vì sao chưa đủ |
|---|---|
| Thêm constructor không tham số trong inner class | Bytecode constructor vẫn cần enclosing instance. |
| Thêm setter cho tất cả field | Setter chỉ gán giá trị sau khi object được tạo. |
| Thêm `@JsonProperty` | Annotation xác định mapping tên field, không tạo outer object. |
| Thêm `@JsonCreator` | Creator vẫn cần đủ tham số để tạo inner instance; outer reference không tự xuất hiện từ JSON. |
| Bật field visibility `ANY` | Cho phép truy cập field không đồng nghĩa có thể gọi constructor với outer instance. |
| Tắt `FAIL_ON_UNKNOWN_PROPERTIES` | Feature này xử lý field JSON lạ, không liên quan đến constructor inner class. |
| Thêm `@JsonIgnoreProperties` | Có thể bỏ qua property, nhưng không cung cấp enclosing instance để tạo inner object. |

Nếu stack trace cho biết lỗi tạo instance của non-static inner class, hãy kiểm tra khai báo lớp và cách tạo object trước khi thay đổi các feature mapping không liên quan.

## 10. Kiểm thử cách tạo lớp lồng

Nên có test riêng cho static nested DTO và cho trường hợp legacy inner class nếu ứng dụng bắt buộc sử dụng kiểu đó.

### 10.1. Test static nested class

```java
class OrderDtoTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsStaticNestedLine() throws Exception {
        String json = """
            {
              "orderId": "O-100",
              "line": { "sku": "BOOK-01", "quantity": 2 }
            }
            """;

        OrderWithLine order = mapper.readValue(json, OrderWithLine.class);

        assertEquals("O-100", order.getOrderId());
        assertEquals("BOOK-01", order.getLine().getSku());
        assertEquals(2, order.getLine().getQuantity());
    }

    public static class OrderWithLine {
        private String orderId;
        private Line line;

        public String getOrderId() { return orderId; }
        public void setOrderId(String value) { orderId = value; }
        public Line getLine() { return line; }
        public void setLine(Line value) { line = value; }

        public static class Line {
            private String sku;
            private int quantity;

            public String getSku() { return sku; }
            public void setSku(String value) { sku = value; }
            public int getQuantity() { return quantity; }
            public void setQuantity(int value) { quantity = value; }
        }
    }
}
```

Test xác nhận Jackson tạo được cả object ngoài và object con bằng cơ chế POJO thông thường.

### 10.2. Test cập nhật inner instance có sẵn

```java
@Test
void updatesExistingInnerInstance() throws Exception {
    Invoice invoice = new Invoice("INV-1");
    Invoice.Note note = invoice.new Note();

    mapper.readerForUpdating(note).readValue("""
        { "text": "Paid" }
        """);

    assertEquals("INV-1", note.invoiceReference());
    assertEquals("Paid", note.getText());
}
```

Test này kiểm tra đúng tình huống application đã có enclosing instance và inner object được tạo trước khi Jackson cập nhật. Nó không chứng minh Jackson có thể tự deserialize một property inner mới bên trong JSON object cha.

### 10.3. Test lỗi khởi tạo inner class mặc định

Nếu muốn ghi nhận giới hạn của một phiên bản Jackson đang dùng, có thể viết test xác nhận đường deserialize POJO mặc định không được dùng cho inner class không tĩnh. Không nên assert toàn bộ thông báo exception vì nội dung và wrapper exception có thể thay đổi theo phiên bản.

```java
@Test
void documentsDefaultConstructionLimitation() {
    String json = "{\"value\":\"x\"}";

    assertThrows(JsonProcessingException.class, () ->
        mapper.readValue(json, Envelope.Payload.class)
    );
}
```

Test cụ thể cần căn chỉnh với phiên bản Jackson và cấu trúc class của dự án. Nếu một phiên bản có hỗ trợ đặc biệt cho một hình thức inner class nhất định, hãy kiểm tra hành vi đó bằng test thực tế và không mở rộng kết luận sang mọi inner class.

## 11. Quyết định thiết kế theo tình huống

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Kiểu con chỉ nhóm dữ liệu của DTO cha | Dùng `static` nested class. |
| Kiểu con được nhiều module sử dụng | Dùng top-level DTO. |
| Model bất biến, có constructor rõ ràng | Static nested class hoặc top-level class với `@JsonCreator`/record. |
| Domain inner class cần truy cập outer state | Deserialize vào DTO độc lập rồi tạo domain inner object trong service. |
| Đã có outer và inner instance, chỉ cần nạp field | `readerForUpdating(existingInner)` nếu object có thể cập nhật. |
| Bắt buộc deserialize trực tiếp inner class | Custom deserializer nhận enclosing instance qua context/injection hoặc mapper chuyên biệt có phạm vi rõ. |
| Muốn deserialize cả outer chứa inner property mới | DTO/static nested hoặc custom deserializer cho outer để tạo inner sau khi outer tồn tại. |

Trước khi chọn custom deserializer, hãy hỏi liệu lớp inner có thực sự cần truy cập outer state hay chỉ được khai báo bên trong để tiện tổ chức source. Nếu chỉ là cách nhóm file, đổi thành static nested class thường loại bỏ đáng kể độ phức tạp.

## 12. Những điểm cần ghi nhớ

- Static nested class không cần enclosing instance; non-static member inner class luôn gắn với một outer object cụ thể.
- Compiler thêm tham chiếu enclosing instance vào cấu trúc inner class; constructor không tham số trong source vẫn không phải constructor độc lập.
- JSON object lồng nhau biểu diễn cấu trúc dữ liệu, không biểu diễn tham chiếu `this` tới outer object của Java.
- Jackson databind thông thường không thể tự suy ra outer instance để tạo inner object mới.
- `@JsonProperty`, `@JsonCreator`, setter và field visibility không tự cung cấp enclosing instance.
- Ưu tiên top-level DTO, static nested DTO hoặc nested record cho dữ liệu JSON.
- Với inner class legacy, có thể tạo instance bằng `outer.new Inner()` rồi dùng `readerForUpdating`, hoặc cung cấp outer qua custom deserializer/injectable value.
- Nếu cần deserialize cả outer và inner property, custom deserializer phải tạo outer trước rồi mới tạo inner; DTO riêng thường dễ bảo trì hơn.
- Serialization thành công không đảm bảo deserialization thành công; cần test hai chiều theo đúng hợp đồng.
- Reader/deserializer chứa owner cụ thể không được chia sẻ tùy tiện giữa các outer instance hoặc request đồng thời.

Khi model Java phản ánh đúng cách Jackson tạo object, quá trình mapping sẽ dễ dự đoán hơn. Hãy dùng lớp lồng tĩnh cho cấu trúc JSON lồng nhau thông thường; chỉ giữ inner class không tĩnh khi mối quan hệ với object bao ngoài là một yêu cầu domain thực sự và ứng dụng có cơ chế cung cấp instance đó một cách tường minh.
