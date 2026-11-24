# Polymorphic deserialization và tập subtype cần được biết trước

## 1. Bài toán polymorphic deserialization

Một JSON API có thể nhận nhiều loại đối tượng cùng tuân theo một hợp đồng. Ví dụ, hệ thống nhận sự kiện OrderCreated, PaymentRejected và OrderCancelled; tất cả đều là DomainEvent, nhưng mỗi loại có các trường riêng. Khi deserialize JSON thành DomainEvent, thư viện phải biết **kiểu cụ thể nào được phép tạo** dựa trên thông tin type discriminator trong payload.

Đó là **polymorphic deserialization**: chuyển JSON thành một trong nhiều subtype của một kiểu gốc (base class hoặc interface). Jackson thường giải quyết bằng type metadata như @JsonTypeInfo, @JsonSubTypes, @JsonTypeName hoặc bằng một Jackson Module đăng ký các subtype.

Với Spring Boot Native Image, GraalVM phân tích khả năng truy cập tại build time. Những subtype được chọn từ chuỗi JSON ở runtime không nhất thiết được suy ra từ call graph tĩnh. Vì vậy, ứng dụng cần một **tập subtype hữu hạn, được xác định trước khi build**, và cần bảo đảm metadata reflection/binding cho các kiểu đó có trong native executable.

Bài này thuộc chương **Binding và JSON** của module **SPRING_BOOT_NATIVE_IMAGE**. Nội dung tập trung vào:

- Cách Jackson xác định subtype từ type discriminator.
- Khai báo subtype bằng annotation hoặc module đăng ký.
- Vì sao tập subtype cần được biết trước khi tạo Native Image.
- Cách Spring AOT đóng góp reflection hints cho kiểu gốc, subtype và DTO lồng nhau.
- Kiểm thử deserialize trên JVM và native executable.
- Kiểm soát type id không tin cậy để tránh mở rộng bề mặt tấn công.

## 2. Base type, subtype và type discriminator

Giả sử API nhận một sự kiện nghiệp vụ. Ta có kiểu gốc:

```java
package com.example.events;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = OrderCreated.class,
        name = "order-created"
    ),
    @JsonSubTypes.Type(
        value = PaymentRejected.class,
        name = "payment-rejected"
    )
})
public abstract class DomainEvent {

    private String eventId;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }
}
```

Subtype thứ nhất:

```java
package com.example.events;

import java.math.BigDecimal;

public class OrderCreated extends DomainEvent {

    private String orderNumber;
    private BigDecimal total;

    public OrderCreated() {
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
```

Subtype thứ hai:

```java
package com.example.events;

public class PaymentRejected extends DomainEvent {

    private String paymentReference;
    private String reasonCode;

    public PaymentRejected() {
    }

    public String getPaymentReference() {
        return paymentReference;
    }

    public void setPaymentReference(String paymentReference) {
        this.paymentReference = paymentReference;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public void setReasonCode(String reasonCode) {
        this.reasonCode = reasonCode;
    }
}
```

Payload JSON tương ứng:

```json
{
  "eventType": "order-created",
  "eventId": "evt-1001",
  "orderNumber": "ORD-2026-001",
  "total": 125000.00
}
```

Và:

```json
{
  "eventType": "payment-rejected",
  "eventId": "evt-1002",
  "paymentReference": "PAY-88",
  "reasonCode": "INSUFFICIENT_FUNDS"
}
```

eventType là **type discriminator**. Jackson dùng giá trị của nó để chọn lớp concrete đã đăng ký. Ứng dụng deserialize qua kiểu gốc:

```java
DomainEvent event = objectMapper.readValue(json, DomainEvent.class);
```

Kết quả có thể là OrderCreated hoặc PaymentRejected, tùy discriminator. Kiểu gốc phải có thông tin subtype mà Jackson có thể tra cứu; nếu không, Jackson không thể tự suy ra mọi implementation chỉ từ tên trường JSON.

## 3. Các cách khai báo tập subtype trong Jackson

### 3.1. Dùng @JsonSubTypes và @JsonTypeInfo

Cách trực tiếp là khai báo subtype ngay trên base type, như ví dụ ở phần 2. Ưu điểm:

- Danh sách subtype nằm cạnh hợp đồng JSON.
- Type id có tên logic ổn định, không phụ thuộc package/class name Java.
- Người đọc có thể thấy ngay những loại payload được hỗ trợ.
- Tập subtype có thể được AOT xử lý cùng kiểu gốc.

Khi muốn khai báo tên logic ở chính subtype, có thể dùng @JsonTypeName:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("order-created")
public class OrderCreated extends DomainEvent {
    // Các trường và accessor của subtype.
}
```

Nếu đã khai báo tên rõ trong @JsonSubTypes.Type(name = "..."), @JsonTypeName thường không bắt buộc cho cùng mapping; nó hữu ích khi muốn subtype tự mang logical name trong các tình huống Jackson cần tra cứu tên kiểu.

### 3.2. Đăng ký subtype bằng Jackson Module

Khi không muốn gắn annotation lên base type, có thể đăng ký subtype bằng NamedType trong module:

```java
import com.example.events.DomainEvent;
import com.example.events.OrderCreated;
import com.example.events.PaymentRejected;
import com.fasterxml.jackson.databind.jsontype.NamedType;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule eventModule = new SimpleModule("event-subtypes");
eventModule.registerSubtypes(
    new NamedType(OrderCreated.class, "order-created"),
    new NamedType(PaymentRejected.class, "payment-rejected")
);
```

Trong Spring Boot, có thể cung cấp module như một bean để Jackson auto-configuration tích hợp vào ObjectMapper do ứng dụng quản lý:

```java
@Configuration(proxyBeanMethods = false)
class EventJacksonConfiguration {

    @Bean
    SimpleModule eventSubtypeModule() {
        SimpleModule module = new SimpleModule("event-subtypes");
        module.registerSubtypes(
            new NamedType(OrderCreated.class, "order-created"),
            new NamedType(PaymentRejected.class, "payment-rejected")
        );
        return module;
    }
}
```

Ví dụ module chỉ minh họa đăng ký subtype. Cách resolve type id còn phụ thuộc cấu hình @JsonTypeInfo/type resolver của base type và phiên bản Jackson. Hãy kiểm thử serialize và deserialize trên ObjectMapper thực tế do Spring Boot cấu hình. Đừng tạo new ObjectMapper() riêng trong production nếu ứng dụng cần các module, naming strategy, date/time configuration hoặc custom serializer do Spring Boot quản lý.

### 3.3. Sealed class và danh sách subtype tường minh

Java sealed classes có thể giới hạn các lớp được phép kế thừa:

```java
public sealed abstract class DomainEvent
    permits OrderCreated, PaymentRejected {
}

public final class OrderCreated extends DomainEvent {
}

public final class PaymentRejected extends DomainEvent {
}
```

Đây là biến thể sealed của hierarchy dùng abstract class ở phần 2; các direct subtype phải được khai báo final, sealed hoặc non-sealed theo quy tắc Java. Sealed hierarchy giúp compiler kiểm tra tập subtype, nhưng **không tự thay thế cấu hình polymorphic của Jackson**. Jackson vẫn cần biết cách ánh xạ JSON type id tới subtype, chẳng hạn qua @JsonTypeInfo kết hợp @JsonSubTypes hoặc module đăng ký. Đồng thời, native image vẫn cần các kiểu được giữ lại và có metadata phù hợp.

Dù dùng annotation, module hay sealed hierarchy, nguyên tắc là: **tập subtype được phép phải rõ ràng và ổn định tại build time**.

## 4. Type id là hợp đồng dữ liệu, không phải tên class tùy ý

Với JsonTypeInfo.Id.NAME, JSON dùng logical name như order-created, payment-rejected. Đây thường là lựa chọn phù hợp cho API vì tên type id không đổi khi refactor package Java.

Tránh dùng JsonTypeInfo.Id.CLASS hoặc bật default typing rộng cho JSON đến từ client không tin cậy. Khi type id biểu diễn tên class, payload có thể yêu cầu Jackson tìm kiểu theo tên class; nếu cấu hình cho phép quá rộng, nguy cơ khởi tạo kiểu ngoài dự kiến và gadget chain tăng lên.

Nguyên tắc an toàn:

- Dùng logical type id có allowlist.
- Chỉ đăng ký subtype mà API thực sự chấp nhận.
- Không lấy class name từ request rồi gọi Class.forName để deserialize.
- Không bật default typing toàn cục cho dữ liệu bên ngoài nếu chưa có chính sách validator chặt chẽ.
- Kiểm soát subtype lồng nhau và các trường có kiểu Object, interface hoặc base class.
- Trả lỗi rõ ràng khi type id không hợp lệ; không âm thầm chuyển sang một subtype mặc định không phù hợp.

Ví dụ JSON có type id không được phép:

```json
{
  "eventType": "admin-command",
  "eventId": "evt-1003",
  "command": "..."
}
```

Nếu admin-command không nằm trong danh sách subtype đã đăng ký, ứng dụng nên từ chối payload theo chính sách API. Không tự động tìm và nạp lớp có tên tương ứng.

### 4.1. Xử lý type id không biết

Có thể chọn một trong các hành vi tùy hợp đồng:

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Fail closed | Từ chối type id không biết | API nghiệp vụ cần schema rõ ràng |
| Default subtype | Chuyển sang kiểu mặc định đã định nghĩa | Chỉ khi kiểu fallback thực sự an toàn và có ý nghĩa |
| Ignore/forward unknown | Giữ payload như dữ liệu chưa phân loại | Hệ thống event gateway cần chuyển tiếp, không thực thi subtype |
| Versioned contract | Đưa version/type mới qua version API hoặc schema | Khi subtype được mở rộng theo phiên bản sản phẩm |

defaultImpl của Jackson có thể được dùng cho một hợp đồng fallback cụ thể, nhưng không nên dùng nó để che lỗi type id sai hoặc biến mọi payload không hợp lệ thành một object chung. Nếu cần forward dữ liệu chưa biết, cân nhắc mô hình envelope chứa type và raw JSON riêng thay vì deserialize trực tiếp vào một subtype tùy ý.

## 5. Vì sao Native Image cần biết trước subtype?

Trong JVM truyền thống, Jackson có thể dùng reflection để khám phá constructor, getter/setter, field, annotation và tạo object theo metadata runtime. Native Image sử dụng reachability analysis khi build; các kiểu chỉ được nhắc đến qua chuỗi JSON có thể không xuất hiện trong call graph tĩnh.

Ví dụ, code chỉ khai báo:

```java
DomainEvent event = objectMapper.readValue(payload, DomainEvent.class);
```

nhưng payload có thể chọn OrderCreated hoặc PaymentRejected. Nếu GraalVM không nhận diện các subtype này và các member Jackson cần truy cập, binary có thể build thành công nhưng deserialize lỗi khi request tới.

Những metadata thường cần xem xét:

- Kiểu gốc và các concrete subtype.
- Constructor được Jackson sử dụng.
- Getter/setter hoặc field được binding.
- Record canonical constructor, @JsonCreator và constructor parameter.
- Các DTO lồng nhau, collection element, map value và kiểu generic được giải quyết tại runtime.
- Custom serializer/deserializer, type resolver hoặc module nếu chúng được tạo/nạp động.

Spring AOT cung cấp cơ chế reflection hints cho binding. @RegisterReflectionForBinding là một cách khai báo các kiểu được dùng trong quá trình serialize/deserialize để Spring đóng góp metadata cần thiết cho native build.

## 6. Đăng ký reflection hints cho base type và từng subtype

Với Spring Boot, có thể khai báo trên một configuration class:

```java
import com.example.events.DomainEvent;
import com.example.events.OrderCreated;
import com.example.events.PaymentRejected;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    DomainEvent.class,
    OrderCreated.class,
    PaymentRejected.class
})
class EventBindingConfiguration {
}
```

Điểm quan trọng:

1. Đăng ký kiểu gốc mà controller/service dùng để deserialize.
2. Đăng ký từng concrete subtype có thể xuất hiện trong payload.
3. Đăng ký thêm các DTO tùy biến được dùng trong property của subtype nếu chúng không được cơ chế binding hiện có nhận diện.
4. Nếu một subtype có property là interface/base type khác, xác định và đăng ký tập subtype của hierarchy lồng nhau.
5. Đảm bảo configuration class được Spring phát hiện qua component scan hoặc import từ cấu hình khác.

Không nên chỉ đăng ký DomainEvent.class rồi mặc định mọi subtype sẽ được giữ lại. Danh sách subtype có thể chỉ xuất hiện trong annotation hoặc trong module registry; hãy xác minh Spring/Jackson AOT integration của phiên bản đang dùng và khai báo rõ các kiểu nếu cần.

### 6.1. Khi nào dùng RuntimeHintsRegistrar?

Nếu danh sách kiểu được quản lý ở một nơi riêng hoặc cần điều kiện đăng ký phức tạp, có thể dùng RuntimeHintsRegistrar. Tuy nhiên, đối với JSON binding thông thường, ưu tiên @RegisterReflectionForBinding vì annotation này diễn tả đúng mục đích binding và để Spring xử lý metadata liên quan.

Ví dụ minh họa một registrar tường minh:

```java
import com.example.events.OrderCreated;
import com.example.events.PaymentRejected;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class EventReflectionHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.reflection().registerType(
            OrderCreated.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.reflection().registerType(
            PaymentRejected.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Liên kết với Spring AOT bằng @ImportRuntimeHints trên một cấu hình được phát hiện:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(EventReflectionHints.class)
class NativeEventHintsConfiguration {
}
```

Đoạn registrar trên là ví dụ khi ứng dụng biết chính xác Jackson cần gọi public constructor và public accessor. Nếu DTO dùng private field, private constructor, @JsonCreator hoặc custom access pattern, cần đăng ký đúng member category tương ứng hoặc dùng @RegisterReflectionForBinding để Spring phân tích binding. Không sao chép danh sách member category mà chưa kiểm tra model thực tế.

## 7. DTO lồng nhau, collection và immutable model

Một subtype thường chứa DTO khác:

```java
public class OrderCreated extends DomainEvent {

    private CustomerSnapshot customer;
    private List<OrderLine> lines;

    public OrderCreated() {
    }

    public CustomerSnapshot getCustomer() {
        return customer;
    }

    public void setCustomer(CustomerSnapshot customer) {
        this.customer = customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void setLines(List<OrderLine> lines) {
        this.lines = lines;
    }
}
```

Khi deserialize, Jackson cần tạo OrderCreated, sau đó binding CustomerSnapshot và từng phần tử OrderLine. Nếu các kiểu này được dùng qua reflection hoặc đường binding động, hãy bảo đảm chúng được nhận diện trong AOT hints. @RegisterReflectionForBinding có thể đăng ký các kiểu gốc và các model binding cụ thể:

```java
@RegisterReflectionForBinding({
    DomainEvent.class,
    OrderCreated.class,
    PaymentRejected.class,
    CustomerSnapshot.class,
    OrderLine.class
})
```

### 7.1. Records và @JsonCreator

Nếu thiết kế base type là interface thay vì abstract class, một subtype có thể là Java record:

```java
public interface DomainEvent {
}

public record PaymentRejected(
    String paymentReference,
    String reasonCode
) implements DomainEvent {
}
```

Record không thể extends abstract class vì mọi record đều kế thừa java.lang.Record; do đó ví dụ này dùng biến thể interface của hierarchy. Jackson cần sử dụng canonical constructor và tên component để binding. Hãy test record subtype trên đúng phiên bản Jackson, đồng thời đăng ký record type trong binding hints khi cần.

Với immutable class không phải record, có thể dùng @JsonCreator và @JsonProperty:

```java
public final class PaymentRejected {

    private final String paymentReference;
    private final String reasonCode;

    @JsonCreator
    public PaymentRejected(
            @JsonProperty("paymentReference") String paymentReference,
            @JsonProperty("reasonCode") String reasonCode) {
        this.paymentReference = paymentReference;
        this.reasonCode = reasonCode;
    }

    public String getPaymentReference() {
        return paymentReference;
    }

    public String getReasonCode() {
        return reasonCode;
    }
}
```

Constructor và parameter metadata phải phù hợp với Jackson configuration. Nếu binding dựa trên constructor được gọi qua reflection trong native, hãy xác minh hints có quyền truy cập cần thiết. Không giả định chỉ có getter là đủ cho mọi immutable model.

## 8. Polymorphism lồng nhau và tập subtype nhiều tầng

Một subtype có thể chứa property polymorphic khác. Ví dụ OrderCreated có List<PaymentMethod> và mỗi phần tử có thể là CardPayment hoặc BankTransfer. Khi đó có hai hierarchy độc lập:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "methodType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface PaymentMethod {
}
```

Đăng ký subtype của PaymentMethod riêng với hierarchy DomainEvent. Ví dụ payload:

```json
{
  "eventType": "order-created",
  "eventId": "evt-2001",
  "paymentMethods": [
    {
      "methodType": "card",
      "lastFour": "4242"
    },
    {
      "methodType": "bank-transfer",
      "bankCode": "VCB"
    }
  ]
}
```

Bảng quản lý subtype giúp tránh bỏ sót:

| Base type | Logical type id | Concrete subtype | Đã có binding hint? |
| --- | --- | --- | --- |
| DomainEvent | order-created | OrderCreated | Có/Chưa xác minh |
| DomainEvent | payment-rejected | PaymentRejected | Có/Chưa xác minh |
| PaymentMethod | card | CardPayment | Có/Chưa xác minh |
| PaymentMethod | bank-transfer | BankTransfer | Có/Chưa xác minh |

Mỗi hierarchy phải có mapping type id riêng, và các subtype cần được giữ lại trong native image. Một subtype được đăng ký cho hierarchy này không tự động trở thành subtype hợp lệ của hierarchy khác.

## 9. Custom deserializer và module đăng ký subtype

Một số hệ thống dùng custom JsonDeserializer hoặc TypeIdResolver để ánh xạ type id. Khi đó cần kiểm tra cả hai phần:

- **Registry:** type id nào được ánh xạ tới class nào? Danh sách này phải hữu hạn và biết trước nếu các class được đưa vào native executable.
- **Deserializer/resolver:** class nào được Jackson tạo và gọi? Nếu nó được tạo qua Spring bean hoặc Jackson module, ưu tiên cơ chế đăng ký được framework hỗ trợ; nếu khởi tạo phản chiếu, bổ sung hints phù hợp.

Ví dụ registry tĩnh:

```java
Map<String, Class<? extends DomainEvent>> allowedTypes = Map.of(
    "order-created", OrderCreated.class,
    "payment-rejected", PaymentRejected.class
);
```

Một resolver có thể tra cứu map này, nhưng không nên thay bằng logic ghép chuỗi type id thành class name rồi gọi Class.forName. Khi custom deserializer có dependency Spring, không tự tạo new CustomDeserializer() bên trong ObjectMapper nếu nó cần bean hoặc configuration từ ApplicationContext.

Đối với các module Jackson đăng ký subtype bằng NamedType, bảo đảm module được Spring Boot quản lý và thực sự được áp dụng vào mapper dùng bởi HTTP message converter. Unit test với một ObjectMapper tự tạo có thể không phản ánh mapper thực tế của ứng dụng.

## 10. Kiểm thử polymorphic binding trên JVM và native

### 10.1. Unit test từng subtype

Test payload cho từng logical type id:

```java
@Test
void deserializesOrderCreated() throws Exception {
    String json = """
        {
          "eventType": "order-created",
          "eventId": "evt-1001",
          "orderNumber": "ORD-2026-001",
          "total": 125000.00
        }
        """;

    DomainEvent event =
        objectMapper.readValue(json, DomainEvent.class);

    assertInstanceOf(OrderCreated.class, event);
    assertEquals("evt-1001", event.getEventId());
}
```

```java
@Test
void deserializesPaymentRejected() throws Exception {
    String json = """
        {
          "eventType": "payment-rejected",
          "eventId": "evt-1002",
          "paymentReference": "PAY-88",
          "reasonCode": "INSUFFICIENT_FUNDS"
        }
        """;

    DomainEvent event =
        objectMapper.readValue(json, DomainEvent.class);

    assertInstanceOf(PaymentRejected.class, event);
    assertEquals("INSUFFICIENT_FUNDS",
        ((PaymentRejected) event).getReasonCode());
}
```

Các test này cần dùng cùng mapper configuration với ứng dụng. Nếu Spring Boot cung cấp module/subtype registry qua bean, hãy lấy mapper từ Spring test context hoặc dùng @JsonTest với các cấu hình được import phù hợp.

### 10.2. Test unknown type id

Kiểm tra chính sách với type id không nằm trong allowlist:

```java
@Test
void rejectsUnknownEventType() {
    String json = """
        {
          "eventType": "admin-command",
          "eventId": "evt-unknown"
        }
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> objectMapper.readValue(json, DomainEvent.class)
    );
}
```

Kiểu exception cụ thể có thể được bọc bởi Spring MVC hoặc ứng dụng. Điều quan trọng là payload không hợp lệ phải bị từ chối theo hợp đồng, không được biến thành một subtype không mong muốn.

### 10.3. Kiểm tra qua HTTP message converter

Nếu API nhận @RequestBody DomainEvent, kiểm tra cả endpoint để xác minh Jackson mapper được Spring Boot cấu hình đúng:

```java
@RestController
@RequestMapping("/events")
class EventController {

    @PostMapping
    ResponseEntity<String> accept(@RequestBody DomainEvent event) {
        return ResponseEntity.ok(event.getClass().getSimpleName());
    }
}
```

Test hai payload qua HTTP và xác nhận subtype được chọn đúng. Test này phát hiện khác biệt giữa mapper trong unit test và mapper được MVC sử dụng.

### 10.4. Chạy trên native executable

Quy trình:

1. Chạy toàn bộ unit/integration test trên JVM.
2. Bật Spring AOT và kiểm tra registrar/annotation binding hints đã được phát hiện.
3. Build GraalVM Native Image bằng Maven hoặc Gradle theo cấu hình dự án.
4. Khởi động native executable và gọi endpoint với payload cho **từng subtype**.
5. Gọi payload có nested polymorphism và DTO immutable/record nếu ứng dụng dùng.
6. Gửi type id không biết để xác nhận chính sách fail closed.
7. So sánh subtype class, field values, HTTP status và response giữa JVM/native.

Build thành công không chứng minh mọi subtype đã được đăng ký. Một subtype chỉ lỗi khi payload cụ thể được gửi tới; do đó test phải bao phủ từng type id mà API cam kết hỗ trợ.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| InvalidTypeIdException | Type id không có mapping hoặc sai chính tả | Kiểm tra @JsonSubTypes, @JsonTypeName hoặc NamedType |
| JVM deserialize được nhưng native lỗi | Subtype/constructor/accessor thiếu binding metadata | Đăng ký root type và concrete subtypes bằng binding hints |
| Base type được giữ nhưng subtype không được tạo | Subtype chỉ xuất hiện trong JSON hoặc registry động | Khai báo tập subtype tường minh và bảo đảm chúng có mặt lúc build |
| Field trong subtype bị null/mất dữ liệu | Getter/setter, field visibility, creator hoặc JSON property không khớp | Kiểm tra Jackson model và member access hints |
| Record subtype lỗi trên native | Canonical constructor hoặc metadata binding chưa được hỗ trợ đầy đủ | Kiểm tra phiên bản Jackson/Spring, thêm binding hint và native test |
| Nested subtype lỗi | Hierarchy lồng nhau chưa có mapping/hints | Lập danh sách subtype cho từng base type và test payload lồng |
| Custom deserializer không được gọi | Module không được đăng ký vào mapper của Spring | Đăng ký module qua cấu hình Spring và test HTTP converter |
| Type id mới chỉ lỗi sau deploy | Native binary được build trước khi subtype mới có mặt | Build lại binary với subtype và metadata mới |
| Unknown type id tạo object mặc định không mong muốn | defaultImpl hoặc custom fallback quá rộng | Chọn chính sách unknown type rõ ràng, fail closed khi phù hợp |
| Lỗi reflection constructor | Constructor được gọi động chưa có hint | Đăng ký constructor cần thiết hoặc dùng binding hints |
| Lỗi chỉ xảy ra ở endpoint MVC | Test dùng mapper khác với mapper production | Kiểm tra qua Spring context/HTTP integration test |

## 12. Quy trình quản lý tập subtype khi phát triển API

Khi thêm subtype mới, thực hiện theo thứ tự:

1. Xác định base type và logical type id.
2. Thêm concrete subtype và kiểm tra schema/validation.
3. Cập nhật @JsonSubTypes hoặc Jackson module registry.
4. Cập nhật binding hints cho subtype và DTO lồng nhau nếu cần.
5. Thêm test serialize/deserialize cho type id mới.
6. Thêm test unknown type id và kiểm tra backward compatibility.
7. Chạy Spring AOT, build native và kiểm tra endpoint trên binary.
8. Phát hành API schema/documentation cùng thay đổi subtype.

Tập subtype phải là **allowlist có quản lý phiên bản**. Khi subtype mới được thêm, cần build lại native executable và phát hành artifact tương ứng. Nếu yêu cầu cài plugin mới sau deploy mà không build lại, kiến trúc closed-world của Native Image không phù hợp với kiểu nạp class tùy ý đó; cân nhắc tách plugin thành service/process riêng hoặc dùng một cơ chế mở rộng được xác định trước.

## 13. Bài thực hành: xây dựng API nhận nhiều loại event

**Bối cảnh:** API POST /events nhận DomainEvent. Có hai loại event OrderCreated và PaymentRejected; mỗi subtype có trường riêng.

**Các bước:**

1. Tạo base type DomainEvent và khai báo @JsonTypeInfo(use = Id.NAME, property = "eventType").
2. Đăng ký OrderCreated với id order-created, PaymentRejected với id payment-rejected.
3. Tạo payload JSON tương ứng và test deserialize qua base type.
4. Thêm @RegisterReflectionForBinding cho base type và tất cả subtype; bổ sung DTO lồng nhau nếu có.
5. Nếu dùng Jackson Module thay cho @JsonSubTypes, cung cấp module qua Spring configuration và kiểm tra mapper thực tế.
6. Viết test type id không hợp lệ để xác nhận payload bị từ chối.
7. Chạy test qua HTTP endpoint để xác minh Spring MVC message converter.
8. Build Native Image, gửi từng payload tới executable và so sánh subtype/field values với JVM.
9. Thêm một subtype mới, cập nhật registry/hints/test rồi build lại native image.
10. Ghi lại danh sách type id được hỗ trợ và quy trình phát hành khi subtype thay đổi.

**Tiêu chí đạt:**

- Type discriminator được xác định rõ và không phụ thuộc tên class Java.
- Chỉ các subtype nằm trong allowlist mới được deserialize.
- Base type, concrete subtypes và DTO lồng nhau có binding metadata phù hợp.
- Unit test và HTTP integration test chạy đúng trên JVM.
- Native executable deserialize được mọi subtype được hỗ trợ.
- Unknown type id bị xử lý theo chính sách API.
- Việc thêm subtype mới kéo theo cập nhật registry, hints, test và native artifact.

## 14. Tổng kết

Polymorphic deserialization cho phép một JSON base type được chuyển thành nhiều concrete subtype thông qua type discriminator. Với Jackson, tập subtype có thể được khai báo bằng @JsonTypeInfo/@JsonSubTypes, @JsonTypeName hoặc đăng ký trong Module. Với Spring Boot Native Image, các subtype và kiểu binding liên quan phải được biết trước khi build; dùng @RegisterReflectionForBinding hoặc RuntimeHintsRegistrar khi cơ chế AOT hiện có chưa cung cấp đủ metadata.

Hãy dùng logical type id có allowlist, tránh class name động từ payload không tin cậy, và kiểm thử mọi subtype trên native executable thực tế. Khi subtype thay đổi, cập nhật registry, binding hints và test rồi build lại binary. Cách quản lý tập subtype tường minh giúp JSON contract ổn định và giúp GraalVM phân tích đúng các kiểu mà ứng dụng có thể tạo ở runtime.

