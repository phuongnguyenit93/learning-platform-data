# Kiểm tra hỗ trợ mô hình sealed theo phiên bản

Java sealed class và sealed interface cho phép khai báo một hệ phân cấp kiểu có tập lớp con trực tiếp được kiểm soát tại thời điểm biên dịch. Đặc điểm này rất phù hợp với mô hình đa hình: một thuộc tính có thể mang nhiều kiểu cụ thể, nhưng chỉ những kiểu được cho phép trong hierarchy mới có thể kế thừa hoặc triển khai kiểu gốc.

Jackson có thể serialize và deserialize các hierarchy đa hình bằng `@JsonTypeInfo`, `@JsonSubTypes` hoặc đăng ký subtype qua mapper. Tuy nhiên, khả năng **tự phát hiện các lớp con từ danh sách `permits` của Java sealed type** phụ thuộc phiên bản Jackson:

- Jackson Databind 2.x không tự động dùng `getPermittedSubclasses()` để đăng ký các subtype của sealed hierarchy. Cần khai báo `@JsonSubTypes`, gọi `registerSubtypes()` hoặc dùng giải pháp mở rộng tương thích với phiên bản 2.x.
- Jackson 3.0 bổ sung tự động phát hiện các subtype của sealed class/interface Java 17. Khi kiểu gốc có `@JsonTypeInfo`, có thể bỏ danh sách `@JsonSubTypes` trùng lặp; Jackson lấy các subtype từ sealed declaration.

Vì vậy, khi dùng sealed model, cần kiểm tra cả phiên bản Java, phiên bản Jackson Databind, cách khai báo type id và cấu hình mapper. Chỉ riêng từ khóa `sealed` trong mã Java không bảo đảm mọi phiên bản Jackson đều biết cách deserialize subtype.

## 1. Sealed class và sealed interface trong Java

Sealed classes được hoàn thiện trong Java 17. Một sealed type khai báo các subtype trực tiếp được phép bằng `permits`:

```java
public sealed interface Payment
        permits CardPayment, BankTransfer {
}

public final class CardPayment implements Payment {
}

public final class BankTransfer implements Payment {
}
```

Mỗi subtype trực tiếp phải khai báo một trong các trạng thái phù hợp:

- `final`: không cho phép có lớp con tiếp theo.
- `sealed`: tiếp tục giới hạn các subtype được phép.
- `non-sealed`: mở lại nhánh kế thừa, cho phép các lớp khác kế thừa tự do.

Ví dụ một nhánh sealed nhiều cấp:

```java
public sealed interface Payment
        permits CardPayment, BankPayment {
}

public final class CardPayment implements Payment {
}

public sealed abstract class BankPayment implements Payment
        permits DomesticTransfer, InternationalTransfer {
}

public final class DomesticTransfer extends BankPayment {
}

public final class InternationalTransfer extends BankPayment {
}
```

`Payment` cho phép `CardPayment` và `BankPayment`; riêng `BankPayment` tiếp tục giới hạn các subtype trực tiếp của nó. Mỗi sealed type có danh sách permitted subtype riêng.

### 1.1. Java sealed type không tự tạo JSON discriminator

Từ khóa `sealed` là quy tắc của hệ thống kiểu Java. Nó không tự quy định JSON sẽ chứa field nào để phân biệt subtype.

Ví dụ, nếu một API nhận:

```json
{
  "kind": "card",
  "last4": "4242"
}
```

Jackson vẫn cần biết `kind` là type id và giá trị `card` ánh xạ tới lớp Java nào. Đây là trách nhiệm của cơ chế polymorphic typing như `@JsonTypeInfo` và cách đăng ký/khám phá subtype.

### 1.2. Vì sao sealed hierarchy hữu ích cho Jackson?

Với hierarchy thông thường, tập subtype có thể mở rộng ở nhiều module hoặc package. Jackson cần được cung cấp danh sách các subtype được phép bằng annotation hoặc API đăng ký.

Với sealed hierarchy, Java lưu thông tin các subtype trực tiếp được phép. Từ Java 17, reflection có thể truy vấn danh sách này. Jackson 3.0 tận dụng metadata đó để tự động phát hiện subtype, giảm việc phải khai báo lặp lại cùng một danh sách trong `@JsonSubTypes`.

Tuy nhiên, sealed hierarchy chỉ giới hạn các nhánh được khai báo. Nếu một permitted subtype là `non-sealed`, nhánh đó vẫn có thể mở rộng thêm. Nếu ứng dụng yêu cầu một tập implementation thực sự đóng, hãy cân nhắc dùng `final` hoặc tiếp tục sealed các cấp con.

## 2. Ma trận hỗ trợ theo phiên bản

Điểm khác biệt cần nhớ là khả năng tự động phát hiện subtype, không phải khả năng Java có thể biên dịch sealed type.

| Nền tảng / Jackson | Sealed type trong Java | Jackson tự phát hiện permitted subtype? | Cách cấu hình đa hình |
|---|---|---|---|
| Java 15/16 preview | Có dưới dạng preview language feature | Phụ thuộc Jackson và không nên dùng làm baseline ổn định | Cần cấu hình subtype tường minh |
| Java 17 + Jackson Databind 2.x | Sealed type là tính năng Java ổn định | Không có hỗ trợ tự động trong core Databind 2.x | `@JsonTypeInfo` cùng `@JsonSubTypes` hoặc `registerSubtypes()` |
| Java 17+ + Jackson 3.0 | Sealed type được hỗ trợ trực tiếp | Có, từ nhánh 3.0; implementation được đưa vào 3.0.0-rc2 và có trong bản 3.0 GA | `@JsonTypeInfo`; subtype được lấy từ sealed declaration, có thể dùng `@JsonTypeName` để đặt id rõ ràng |

Jackson 3.0 được phát hành chính thức ngày 03/10/2025 và yêu cầu Java 17 trở lên cho các thành phần 3.x. Tính năng tự động phát hiện subtype sealed được đưa vào nhánh 3.0 trong 3.0.0-rc2. Vì đây là tính năng của major version 3, không nên suy luận rằng một bản 2.x mới hơn sẽ tự động có cùng hành vi.

### 2.1. Điều gì có và không có trong Jackson 2.x?

Jackson 2.x vẫn có hệ thống polymorphic typing từ lâu. Có thể dùng sealed interface làm kiểu gốc và deserialize thành subtype nếu đã khai báo chúng:

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
public sealed interface Payment
        permits CardPayment, BankTransfer {
}
```

Ở đây Java compiler kiểm soát hierarchy bằng `permits`, còn Jackson 2.x lấy danh sách subtype từ `@JsonSubTypes`. Hai danh sách cần nhất quán với nhau. Jackson 2.x không tự đọc `permits` chỉ vì kiểu gốc được khai báo `sealed`.

Nếu không muốn đặt annotation trên kiểu gốc, có thể đăng ký subtype trên mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(BankTransfer.class, "bank")
);
```

Với cách này, kiểu gốc vẫn cần `@JsonTypeInfo` hoặc một cấu hình polymorphic typing phù hợp để Jackson biết phải đọc type id ở đâu và theo cơ chế nào.

### 2.2. Điều gì thay đổi trong Jackson 3.0?

Trong Jackson 3.0, sealed subtype discovery được tích hợp vào `JacksonAnnotationIntrospector`. Với sealed type có `@JsonTypeInfo`, Jackson có thể lấy các subtype từ danh sách permitted của Java:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
public sealed interface Payment
        permits CardPayment, BankTransfer {
}
```

Không cần lặp lại danh sách `@JsonSubTypes` trong trường hợp thông thường. `@JsonTypeName` trên từng implementation có thể xác định type id ổn định:

```java
@JsonTypeName("card")
public final class CardPayment implements Payment {
    private String last4;

    public CardPayment() {
    }

    public CardPayment(String last4) {
        this.last4 = last4;
    }

    public String getLast4() {
        return last4;
    }

    public void setLast4(String last4) {
        this.last4 = last4;
    }
}

@JsonTypeName("bank")
public final class BankTransfer implements Payment {
    private String iban;

    public BankTransfer() {
    }

    public BankTransfer(String iban) {
        this.iban = iban;
    }

    public String getIban() {
        return iban;
    }

    public void setIban(String iban) {
        this.iban = iban;
    }
}
```

Với `JsonTypeInfo.Id.NAME`, `@JsonTypeName("card")` và `@JsonTypeName("bank")` làm cho JSON dùng các tên ngắn, có chủ đích thay vì phụ thuộc tên class Java.

**Lưu ý:** `@JsonTypeInfo` vẫn cần thiết để bật polymorphic handling và xác định cơ chế type id. Jackson 3.0 tự phát hiện subtype; nó không tự quyết định rằng mọi sealed class đều phải serialize đa hình hoặc tự thêm discriminator nếu kiểu gốc không yêu cầu điều đó.

## 3. Khai báo type id bằng JsonTypeInfo

`@JsonTypeInfo` mô tả cách Jackson ghi và đọc thông tin subtype. Ví dụ:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
public sealed interface Payment
        permits CardPayment, BankTransfer {
}
```

Các thành phần quan trọng:

- `use`: chiến lược xác định type id, ví dụ `NAME`, `CLASS` hoặc `MINIMAL_CLASS`.
- `include`: vị trí hoặc hình thức đưa type id vào JSON.
- `property`: tên field chứa type id khi dùng dạng `As.PROPERTY`.

Với cấu hình trên, JSON có dạng:

```json
{
  "kind": "card",
  "last4": "4242"
}
```

Khi deserialize thành `Payment`, Jackson đọc `kind`, tìm subtype có tên `card` rồi tạo `CardPayment`.

### 3.1. Ưu tiên tên type ổn định

Với API công khai hoặc dữ liệu được lưu lâu dài, nên dùng `JsonTypeInfo.Id.NAME` cùng tên tường minh:

```java
@JsonTypeName("card")
public final class CardPayment implements Payment {
    // fields và accessors
}
```

Type id `card` là một phần của hợp đồng JSON. Nó không đổi chỉ vì lớp Java được đổi tên từ `CardPayment` thành `CardPaymentDetails`.

Các chiến lược dựa trên tên class như `Id.CLASS` hoặc `Id.MINIMAL_CLASS` gắn chặt dữ liệu JSON với tên package/class. Việc đổi package hoặc refactor có thể làm dữ liệu cũ không còn deserialize được. Với dữ liệu không đáng tin cậy, không nên dùng class name làm type id mà không có chính sách kiểm soát subtype phù hợp.

### 3.2. Các hình thức đặt type id

Một số `JsonTypeInfo.As` thường gặp:

| Hình thức | Ý nghĩa | JSON minh họa |
|---|---|---|
| `PROPERTY` | Type id là một property trong object | `{"kind":"card","last4":"4242"}` |
| `WRAPPER_OBJECT` | Type id là key bọc object | `{"card":{"last4":"4242"}}` |
| `WRAPPER_ARRAY` | Type id và payload nằm trong array | `["card",{"last4":"4242"}]` |
| `EXISTING_PROPERTY` | Dùng property có sẵn trong model làm type id | `{"kind":"card","last4":"4242"}` |

`PROPERTY` thường dễ đọc và tương thích với REST API. `EXISTING_PROPERTY` phù hợp khi discriminator là một field thực sự của model và serializer không cần tự tạo một field type id riêng. Hãy chọn một hình thức và giữ nhất quán giữa các producer/consumer.

## 4. Ví dụ cho Jackson 2.x: khai báo subtype tường minh

Ví dụ sau dùng cùng Java sealed interface nhưng khai báo subtype bằng annotation để tương thích với Jackson Databind 2.x.

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.annotation.JsonTypeName;
import com.fasterxml.jackson.databind.ObjectMapper;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank")
})
public sealed interface Payment
        permits CardPayment, BankTransfer {
}

@JsonTypeName("card")
public final class CardPayment implements Payment {
    private String last4;

    public CardPayment() {
    }

    public CardPayment(String last4) {
        this.last4 = last4;
    }

    public String getLast4() {
        return last4;
    }

    public void setLast4(String last4) {
        this.last4 = last4;
    }
}

@JsonTypeName("bank")
public final class BankTransfer implements Payment {
    private String iban;

    public BankTransfer() {
    }

    public BankTransfer(String iban) {
        this.iban = iban;
    }

    public String getIban() {
        return iban;
    }

    public void setIban(String iban) {
        this.iban = iban;
    }
}
```

Deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

Payment payment = mapper.readValue(
    "{\"kind\":\"card\",\"last4\":\"4242\"}",
    Payment.class
);

if (payment instanceof CardPayment card) {
    System.out.println(card.getLast4());
}
```

Serialize:

```java
String json = mapper.writeValueAsString(new CardPayment("4242"));
```

Kết quả có discriminator `kind` theo cấu hình. `@JsonSubTypes` giúp Jackson 2.x biết `card` và `bank` là các subtype hợp lệ của `Payment`.

### 4.1. Dùng registerSubtypes() thay cho JsonSubTypes

Nếu không muốn đặt subtype list trong annotation, có thể đăng ký trên mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(BankTransfer.class, "bank")
);
```

`registerSubtypes()` là cách cấu hình runtime. Nó phù hợp khi danh sách implementation được quyết định bởi composition root hoặc module wiring. Cần bảo đảm mapper dùng để đọc JSON đã đăng ký đủ subtype trước khi deserialize.

Nếu annotation và mapper đăng ký cùng một lớp nhưng dùng type id khác nhau, cần xác định rõ quy tắc đặt tên và tránh cấu hình chồng chéo gây khó hiểu.

## 5. Ví dụ cho Jackson 3.0: tự phát hiện permitted subclasses

Với Jackson 3.0, có thể giữ `@JsonTypeInfo` ở kiểu gốc và bỏ `@JsonSubTypes` trong sealed hierarchy:

```java
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.annotation.JsonTypeName;
import tools.jackson.databind.json.JsonMapper;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
public sealed interface Payment
        permits CardPayment, BankTransfer {
}

@JsonTypeName("card")
public final class CardPayment implements Payment {
    private String last4;

    public CardPayment() {
    }

    public CardPayment(String last4) {
        this.last4 = last4;
    }

    public String getLast4() {
        return last4;
    }

    public void setLast4(String last4) {
        this.last4 = last4;
    }
}

@JsonTypeName("bank")
public final class BankTransfer implements Payment {
    private String iban;

    public BankTransfer() {
    }

    public BankTransfer(String iban) {
        this.iban = iban;
    }

    public String getIban() {
        return iban;
    }

    public void setIban(String iban) {
        this.iban = iban;
    }
}

JsonMapper mapper = JsonMapper.builder().build();

Payment payment = mapper.readValue(
    "{\"kind\":\"card\",\"last4\":\"4242\"}",
    Payment.class
);
```

Trong Jackson 3.0, introspector có thể lấy `CardPayment` và `BankTransfer` từ permitted subclasses của `Payment`. `@JsonTypeName` cung cấp các id `card` và `bank` để JSON không phụ thuộc tên class.

### 5.1. Package name thay đổi trong Jackson 3

Jackson 3 là major version không tương thích API hoàn toàn với 2.x. Các package của Core/Databind chuyển từ `com.fasterxml.jackson...` sang `tools.jackson...`.

Ví dụ:

| Thành phần | Jackson 2.x | Jackson 3.x |
|---|---|---|
| `ObjectMapper` | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.ObjectMapper` |
| `JsonMapper` | `com.fasterxml.jackson.databind.json.JsonMapper` | `tools.jackson.databind.json.JsonMapper` |
| `JsonParser` | `com.fasterxml.jackson.core.JsonParser` | `tools.jackson.core.JsonParser` |
| `JsonTypeInfo` | `com.fasterxml.jackson.annotation.JsonTypeInfo` | Vẫn dùng `com.fasterxml.jackson.annotation.JsonTypeInfo` |

Jackson 3.0 sử dụng dòng `jackson-annotations` 2.x, vì vậy annotation import vẫn thuộc package `com.fasterxml.jackson.annotation`. Khi nâng cấp, không đổi máy móc mọi import theo cùng một quy tắc; kiểm tra từng module và artifact.

## 6. Java và Jackson phải cùng đáp ứng yêu cầu runtime

Để dùng sealed class/interface ổn định, project nên compile và chạy với Java 17 trở lên:

```java
public sealed interface Result
        permits Success, Failure {
}
```

Nếu build dùng Java toolchain, hãy đặt toolchain tương ứng. Ví dụ Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Nếu compile bằng Maven compiler plugin, đặt release:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đây là cấu hình ví dụ cho Java 17. Jackson 3.x cũng yêu cầu JDK 17+, trong khi Jackson 2.x có thể chạy trên các baseline Java cũ hơn tùy phiên bản. Dù ứng dụng chạy Java 17, việc dùng Jackson 2.x vẫn không tự có sealed subtype discovery.

## 7. Hỗ trợ sealed hierarchy nhiều cấp

Một sealed type có thể cho phép subtype trực tiếp tiếp tục là sealed. Ví dụ:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
public sealed interface Payment
        permits CardPayment, BankPayment {
}

@JsonTypeName("card")
public final class CardPayment implements Payment {
}

@JsonTypeName("bank")
public sealed abstract class BankPayment implements Payment
        permits DomesticTransfer, InternationalTransfer {
}

@JsonTypeName("domestic")
public final class DomesticTransfer extends BankPayment {
}

@JsonTypeName("international")
public final class InternationalTransfer extends BankPayment {
}
```

Ở mỗi cấp, sealed declaration xác định permitted subtype trực tiếp. Nếu dữ liệu JSON được deserialize vào `Payment`, type id cần trỏ đến một subtype hợp lệ của `Payment`, ví dụ `card` hoặc `bank`. Nếu deserialize vào `BankPayment`, các subtype phù hợp là `domestic` và `international`.

Không nên giả định rằng mọi lớp con ở mọi cấp đều có thể được dùng thay thế cho nhau trong mọi vị trí. Type id phải xác định subtype phù hợp với base type đang được deserialize.

### 7.1. Nhánh non-sealed mở rộng hierarchy

Ví dụ:

```java
public sealed interface Payment
        permits CardPayment, PluginPayment {
}

public final class CardPayment implements Payment {
}

public non-sealed class PluginPayment implements Payment {
}
```

`PluginPayment` là permitted subtype trực tiếp, nhưng vì được khai báo `non-sealed`, các lớp khác có thể kế thừa nó. Sealed root không còn mô tả toàn bộ concrete class có thể xuất hiện trong nhánh này.

Với plugin hoặc extension point, cần đăng ký và kiểm soát các implementation cụ thể theo cách phù hợp. Không nên xem sealed root là allowlist đầy đủ nếu một nhánh được mở lại bằng `non-sealed`.

## 8. Type id và tên subtype

Khi dùng `JsonTypeInfo.Id.NAME`, Jackson cần một tên để liên kết JSON với lớp Java. Có thể khai báo bằng:

- `@JsonTypeName("card")` trên subtype.
- `@JsonSubTypes.Type(value = CardPayment.class, name = "card")` trên base type trong Jackson 2.x.
- `NamedType` qua `registerSubtypes()`.
- Quy tắc tên mặc định của Jackson nếu không khai báo tên riêng.

Đối với API bền vững, nên dùng tên tường minh. Ví dụ:

```java
@JsonTypeName("card")
public final class CardPayment implements Payment {
}
```

Type id `card` là contract; tên class có thể được refactor độc lập.

### 8.1. Tránh phụ thuộc tên class trong JSON

`Id.CLASS` đưa tên lớp đầy đủ vào JSON, ví dụ tên package và class. Cách này làm schema phụ thuộc cấu trúc source code và không thuận tiện khi refactor hoặc trao đổi với hệ thống khác.

Với JSON đến từ nguồn không đáng tin cậy, không nên bật polymorphic deserialization quá rộng. Dùng `Id.NAME` với subtype được xác định rõ và kiểm soát danh sách subtype hợp lệ. Sealed hierarchy giúp thu hẹp danh sách subtype, nhưng không thay thế việc thiết kế type id an toàn.

### 8.2. Xử lý type id không biết

Nếu JSON có:

```json
{
  "kind": "crypto-wallet",
  "address": "..."
}
```

nhưng hierarchy không có subtype với id `crypto-wallet`, Jackson thường báo lỗi không tìm được subtype. Đây là hành vi hữu ích để phát hiện producer và consumer không đồng bộ.

Nếu muốn hỗ trợ fallback, có thể cân nhắc `defaultImpl` trong `@JsonTypeInfo` hoặc custom type resolver, nhưng cần xác định rõ dữ liệu không nhận diện sẽ được xử lý thế nào. Fallback không nên che giấu một type id sai hoặc cho phép tạo kiểu ngoài dự kiến.

## 9. Kiểm thử hỗ trợ sealed type theo phiên bản

Không nên chỉ dựa vào việc code compile thành công. Hãy kiểm tra cả serialize, deserialize, type id và runtime version.

### 9.1. Test deserialize subtype

Với mapper và model tương ứng phiên bản:

```java
String json = """
    {
      "kind": "card",
      "last4": "4242"
    }
    """;

Payment payment = mapper.readValue(json, Payment.class);

assertInstanceOf(CardPayment.class, payment);
assertEquals("4242", ((CardPayment) payment).getLast4());
```

Test này xác nhận mapper có thể giải quyết type id `card` thành implementation mong muốn.

### 9.2. Test serialize subtype

```java
Payment payment = new CardPayment("4242");
String json = mapper.writerFor(Payment.class).writeValueAsString(payment);

JsonNode tree = mapper.readTree(json);
assertEquals("card", tree.get("kind").asText());
assertEquals("4242", tree.get("last4").asText());
```

Dùng writer với kiểu base `Payment` giúp kiểm tra polymorphic type id theo base contract. Nếu serialize trực tiếp kiểu concrete, cần xác nhận type metadata vẫn được áp dụng theo cấu hình mong muốn.

### 9.3. Test round-trip

```java
Payment original = new CardPayment("4242");
String json = mapper.writerFor(Payment.class).writeValueAsString(original);
Payment restored = mapper.readValue(json, Payment.class);

assertInstanceOf(CardPayment.class, restored);
assertEquals("4242", ((CardPayment) restored).getLast4());
```

Round-trip giúp xác nhận cả serializer lẫn deserializer dùng cùng type id. Đây là test cần thiết khi đổi từ Jackson 2.x sang 3.x hoặc thay đổi subtype registration.

### 9.4. Test subtype không được phép

Thử một type id không nằm trong hierarchy hoặc chưa đăng ký:

```java
String unknownType = """
    {
      "kind": "unknown-payment",
      "reference": "X-1"
    }
    """;

assertThrows(JsonProcessingException.class,
    () -> mapper.readValue(unknownType, Payment.class));
```

Tên exception cụ thể và API exception có thể khác giữa Jackson 2.x và 3.x; điều quan trọng là test xác nhận subtype không được nhận diện bị từ chối theo chính sách của ứng dụng.

## 10. Kiểm tra phiên bản Jackson thực tế trong ứng dụng

Trong dự án có nhiều module hoặc framework, version Jackson runtime có thể khác version mà developer nghĩ rằng mình đã khai báo. Ví dụ, dependency management của framework có thể chọn một bản `jackson-databind` khác với bản ghi trong một module con.

Hãy kiểm tra dependency tree của build tool:

**Maven:**

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

**Gradle:**

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Với Jackson 3, group/package namespace thay đổi; điều chỉnh filter dependency theo tọa độ thực tế của project. Không trộn `jackson-core`/`jackson-databind` 2.x với 3.x trong cùng một cấu hình ứng dụng.

Có thể in version từ class package hoặc đọc metadata artifact khi cần điều tra runtime. Tuy nhiên, dependency tree của runtime classpath thường cho biết rõ dependency nào kéo phiên bản đó vào.

### 10.1. Kiểm tra cả module và framework

Ứng dụng có thể dùng:

- Spring Boot hoặc framework khác quản lý version Jackson.
- Module Jackson bổ sung cho Kotlin, Scala, Java Time hoặc datatype khác.
- Một thư viện bên thứ ba đóng gói dependency Jackson.

Khi nâng major version, cần kiểm tra tương thích của toàn bộ module và framework. Tính năng sealed discovery nằm trong Databind; chỉ nâng `jackson-annotations` mà không nâng `jackson-databind` không cung cấp tính năng này.

## 11. Nếu dự án vẫn dùng Jackson 2.x

Không nhất thiết phải nâng lên Jackson 3 chỉ để dùng Java sealed type. Có các lựa chọn:

1. Khai báo `@JsonTypeInfo` và `@JsonSubTypes` trên kiểu gốc.
2. Gọi `registerSubtypes()` khi cấu hình mapper.
3. Dùng module ngoài tương thích với Jackson 2.x nếu dự án chấp nhận dependency đó; cần xác minh phiên bản module, Databind và Java đang dùng.
4. Viết subtype resolver hoặc custom type handling nếu có hợp đồng đặc biệt.

Một module bên ngoài từng được phát triển để bổ sung khả năng sealed subtype cho Jackson 2.x; implementation tương ứng sau đó được tích hợp vào Jackson Databind 3.0. Nếu chọn module ngoài, hãy kiểm tra trạng thái bảo trì và compatibility matrix của chính module thay vì giả định mọi version 2.x đều tương thích.

Đối với đa số dự án, `@JsonSubTypes` hoặc `registerSubtypes()` là lựa chọn dễ hiểu, ít phụ thuộc hơn. Danh sách subtype nên được quản lý cùng sealed declaration để tránh một subtype được phép trong Java nhưng bị thiếu trong cấu hình Jackson.

## 12. Checklist nâng cấp từ Jackson 2.x lên 3.x

Khi muốn chuyển sang auto-discovery của Jackson 3.0, hãy kiểm tra:

1. Project compile và chạy với JDK 17 trở lên.
2. Tất cả artifact Core/Databind và module liên quan đã chuyển sang major version phù hợp.
3. Package import của Core/Databind đã chuyển sang `tools.jackson...`.
4. Annotation import vẫn dùng `com.fasterxml.jackson.annotation...` theo dòng annotations mà Jackson 3 sử dụng.
5. Base sealed type có `@JsonTypeInfo` với type id strategy và property phù hợp.
6. Các subtype được khai báo trong `permits` và có thể được truy cập/khởi tạo theo cách model yêu cầu.
7. `@JsonTypeName` cung cấp id ổn định cho các subtype khi dùng `Id.NAME`.
8. Những `@JsonSubTypes` trước đây có thể bỏ nếu chỉ lặp lại permitted subtype và không cung cấp metadata bổ sung cần thiết.
9. Các subtype được đăng ký thủ công hoặc đến từ module ngoài đã được rà soát để tránh cấu hình thừa/xung đột.
10. Test serialize, deserialize, round-trip, unknown type id và mọi hierarchy nhiều cấp.
11. Dependency tree runtime xác nhận ứng dụng thực sự chạy Jackson 3.0+.
12. Kiểm tra các thay đổi API/behavior khác của Jackson 3; nâng major version không chỉ thay đổi sealed subtype discovery.

## 13. Những hiểu lầm thường gặp

**Java 17 có sealed class nên Jackson 2.x tự tìm được subtype.** Không đúng. Java cung cấp metadata permitted subclass; core Databind 2.x không tự động dùng metadata đó. Cần khai báo subtype hoặc dùng giải pháp mở rộng phù hợp.

**Jackson 3.0 bỏ luôn `@JsonTypeInfo`.** Không đúng. Sealed discovery giúp bỏ danh sách `@JsonSubTypes` trùng lặp; `@JsonTypeInfo` vẫn cần để bật và định nghĩa polymorphic type handling.

**`@JsonSubTypes` và `permits` là cùng một cơ chế.** `permits` là quy tắc compiler/runtime của Java; `@JsonSubTypes` là metadata subtype của Jackson. Trong Jackson 2.x, thường cần cả hai nếu hierarchy là sealed và JSON cần polymorphism.

**Sealed type bảo đảm mọi nhánh đều đóng hoàn toàn.** Không nếu có permitted subtype `non-sealed`. Nhánh đó vẫn có thể có implementation mới.

**Có thể dùng tên class làm type id mà không ảnh hưởng schema.** Tên package/class có thể đổi khi refactor. Dùng `Id.NAME` và `@JsonTypeName` để ổn định contract.

**Nâng jackson-core hoặc annotations là đủ.** Sealed subtype auto-detection là tính năng của Databind 3.0. Cần kiểm tra đúng dependency `jackson-databind` và toàn bộ version alignment.

**Code compile được nghĩa là deserialize đa hình đã hoạt động.** Compile chỉ xác nhận Java hierarchy. Cần chạy test với mapper thực tế để xác nhận type id, subtype discovery và constructor/creator.

## 14. Quy trình kiểm tra hỗ trợ theo phiên bản

Khi nhận một sealed model từ ứng dụng, có thể kiểm tra theo thứ tự:

1. Xác định JDK đang dùng để compile và chạy; sealed type ổn định cần Java 17+.
2. Xác định phiên bản `jackson-databind` thực tế trong runtime dependency tree.
3. Nếu là Jackson 2.x, kiểm tra `@JsonSubTypes`, `registerSubtypes()` hoặc module bổ sung có cung cấp subtype list không.
4. Nếu là Jackson 3.0+, kiểm tra base sealed type có `@JsonTypeInfo` không.
5. Kiểm tra các subtype trực tiếp có trong `permits` và type id được đặt ổn định bằng `@JsonTypeName` khi cần.
6. Xác định `non-sealed` branch có mở rộng tập subtype ngoài dự kiến không.
7. Kiểm tra import/package namespace tương ứng với Jackson major version.
8. Deserialize JSON cho từng subtype và xác nhận class cụ thể được tạo.
9. Serialize bằng kiểu base để xác nhận discriminator xuất hiện đúng.
10. Thử unknown type id và kiểm tra hành vi từ chối/fallback theo hợp đồng.

## Kết luận

Sealed class/interface là tính năng Java được hoàn thiện trong Java 17, nhưng khả năng tự động phát hiện permitted subtype là khác biệt theo phiên bản Jackson. Core Databind 2.x vẫn cần subtype được khai báo bằng `@JsonSubTypes`, `registerSubtypes()` hoặc giải pháp bổ sung tương thích. Jackson 3.0, bắt đầu từ 3.0.0-rc2 và có trong bản GA, tự phát hiện các subtype của Java 17 sealed type khi base type được đánh dấu `@JsonTypeInfo`; `@JsonTypeName` giúp đặt type id ổn định. Khi kiểm tra hoặc nâng cấp, hãy xác minh JDK, Databind runtime, package namespace, cấu hình type id và test cả serialize lẫn deserialize.

## Tài liệu tham khảo

- [Jackson 3.0 Release Notes](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0) — yêu cầu JDK 17, ngày phát hành và mục tự động phát hiện Java 17 sealed classes.
- [Jackson Databind PR #5025](https://github.com/FasterXML/jackson-databind/pull/5025) — implementation và ví dụ subtype discovery từ permitted subclasses.
- [Jackson 3.0.0-rc2 notes](https://cowtowncoder.medium.com/jackson-3-0-0-rc2-minor-update-593306f89e2c) — lý do có thể bỏ `@JsonSubTypes` nhưng vẫn dùng `@JsonTypeInfo`.
- [Java Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6) — quy tắc khai báo sealed class và permitted direct subclasses.
