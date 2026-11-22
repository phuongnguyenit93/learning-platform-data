# Phối hợp serializer riêng với thông tin kiểu đa hình

Khi một property Java có kiểu khai báo là interface hoặc lớp cha nhưng có thể chứa nhiều lớp con, Jackson cần một cách nhận diện subtype để deserialize JSON về đúng kiểu thực tế. Cơ chế này thường được khai báo bằng @JsonTypeInfo và @JsonSubTypes, hoặc bằng một type resolver tương đương.

Nếu ứng dụng đồng thời dùng serializer riêng, serializer phải phối hợp với cơ chế ghi type metadata. Serializer thông thường chỉ biết cách ghi các field của object; type serializer chịu trách nhiệm ghi discriminator như kind = "card". Nếu serializer tự ghi toàn bộ object mà không xử lý type metadata, JSON có thể mất discriminator, có discriminator trùng hoặc không còn đúng cấu trúc mà Jackson mong đợi khi đọc lại.

Bài học này tập trung vào ranh giới giữa hai trách nhiệm:

- **Custom serializer**: quyết định cách ghi dữ liệu của một subtype.
- **Polymorphic type handling**: quyết định cách nhận diện subtype trong JSON để có thể khôi phục kiểu thực tế khi deserialize.

Khi kết hợp đúng hai phần, Jackson có thể vừa dùng định dạng JSON tùy chỉnh vừa giữ được thông tin kiểu đa hình.

## 1. Vì sao cần phối hợp serializer với type metadata?

Giả sử ứng dụng xử lý nhiều phương thức thanh toán:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;
    private String network;

    public CardPayment() {
    }

    // Getter và setter.
}

public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;
    private String accountNumber;

    public BankTransfer() {
    }

    // Getter và setter.
}
~~~

Một lớp chứa payment method:

~~~java
public class PaymentRequest {
    private String requestId;
    private PaymentMethod method;

    public PaymentRequest() {
    }

    // Getter và setter.
}
~~~

Property method có kiểu khai báo PaymentMethod, nhưng object thực tế có thể là CardPayment hoặc BankTransfer.

Nếu chỉ serialize dữ liệu theo field của subtype, JSON có thể chứa các property như lastFourDigits hoặc bankCode. Tuy nhiên, khi deserialize về PaymentMethod, Jackson cần biết class concrete nào phải tạo.

Có thể dùng một property discriminator:

~~~json
{
  "requestId": "REQ-100",
  "method": {
    "kind": "card",
    "reference": "PAY-001",
    "lastFourDigits": "4242",
    "network": "VISA"
  }
}
~~~

Giá trị kind cho biết object method là CardPayment. Nếu method là BankTransfer, kind có thể là bank-transfer.

Serializer riêng cần giữ đúng cấu trúc này. Phần ghi các field thanh toán do serializer thực hiện; phần ghi discriminator do TypeSerializer của Jackson thực hiện.

## 2. Khai báo subtype và discriminator

### 2.1. Dùng @JsonTypeInfo trên kiểu cha

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface PaymentMethod {
    String getReference();
}
~~~

Các thuộc tính chính:

| Thành phần | Vai trò |
|---|---|
| use = Id.NAME | Dùng tên subtype logic thay cho tên class Java |
| include = As.PROPERTY | Ghi discriminator thành property trong JSON object |
| property = "kind" | Tên khóa chứa type id |
| @JsonSubTypes | Đăng ký các subtype và tên logic tương ứng |

Tên card và bank-transfer là một phần của hợp đồng JSON. Chúng không phụ thuộc vào package hoặc tên class Java. Có thể refactor CardPayment thành class khác mà vẫn giữ kind = "card" nếu mapping tiếp tục được duy trì.

### 2.2. Dùng @JsonTypeName trên subtype

Thay vì đặt toàn bộ tên ở @JsonSubTypes, có thể khai báo tên logic trên subtype:

~~~java
@JsonTypeName("card")
public class CardPayment implements PaymentMethod {
    // Các field và method.
}
~~~

~~~java
@JsonTypeName("bank-transfer")
public class BankTransfer implements PaymentMethod {
    // Các field và method.
}
~~~

Jackson vẫn cần biết các subtype hợp lệ thông qua metadata, đăng ký module hoặc cơ chế subtype resolver. @JsonTypeName đặt tên cho subtype; nó không phải lúc nào cũng tự động phát hiện mọi class con trong ứng dụng.

### 2.3. JSON sau khi có type metadata

Khi ghi một CardPayment qua kiểu PaymentMethod, JSON mong muốn có dạng:

~~~json
{
  "kind": "card",
  "reference": "PAY-001",
  "lastFourDigits": "4242",
  "network": "VISA"
}
~~~

Khi đọc, Jackson dùng kind = card để chọn CardPayment. Nếu discriminator không có hoặc không được nhận diện, quá trình deserialize có thể thất bại tùy cấu hình và default implementation.

## 3. Serializer riêng thường ghi gì?

Một serializer riêng thường kế thừa StdSerializer hoặc JsonSerializer. Ví dụ serializer cho CardPayment:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;

public class CardPaymentSerializer extends StdSerializer<CardPayment> {

    public CardPaymentSerializer() {
        super(CardPayment.class);
    }

    @Override
    public void serialize(
            CardPayment value,
            JsonGenerator gen,
            SerializerProvider provider
    ) throws IOException {

        gen.writeStartObject();
        writeFields(value, gen);
        gen.writeEndObject();
    }

    private void writeFields(CardPayment value, JsonGenerator gen)
            throws IOException {

        gen.writeStringField("reference", value.getReference());
        gen.writeStringField("lastFourDigits", value.getLastFourDigits());
        gen.writeStringField("network", value.getNetwork());
    }
}
~~~

Method serialize() tự tạo JSON object và ghi các field nghiệp vụ. Nếu không có polymorphic type handling, output chỉ chứa reference, lastFourDigits và network.

Nhưng khi serializer được dùng cho một kiểu có @JsonTypeInfo, Jackson có thể gọi serializeWithType() để serializer ghi dữ liệu cùng type metadata. Đây là điểm cần xử lý.

## 4. Vai trò của serializeWithType()

Trong Jackson, serializer có hai trách nhiệm khác nhau:

- serialize(): ghi representation của value khi không cần type metadata đa hình ở vị trí đó.
- serializeWithType(): ghi representation của value trong ngữ cảnh cần type metadata.

Nếu serializer riêng chỉ override serialize() mà không hỗ trợ serializeWithType(), nó có thể không hoạt động đúng khi Jackson yêu cầu ghi type information. Tùy phiên bản và serializer base class, lời gọi mặc định có thể ném exception báo serializer không hỗ trợ polymorphic type handling.

Với Jackson hiện đại, cách triển khai thường dùng WritableTypeId cùng TypeSerializer:

~~~java
@Override
public void serializeWithType(
        CardPayment value,
        JsonGenerator gen,
        SerializerProvider provider,
        TypeSerializer typeSer
) throws IOException {

    WritableTypeId typeId = typeSer.writeTypePrefix(
            gen,
            typeSer.typeId(value, JsonToken.START_OBJECT)
    );

    writeFields(value, gen);

    typeSer.writeTypeSuffix(gen, typeId);
}
~~~

Các import bổ sung:

~~~java
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.type.WritableTypeId;
import com.fasterxml.jackson.databind.jsontype.TypeSerializer;
~~~

TypeSerializer thực hiện phần mở đầu và kết thúc cấu trúc có chứa type metadata. Với As.PROPERTY, prefix có thể ghi discriminator kind vào object. Serializer riêng chỉ ghi các field của CardPayment ở giữa prefix và suffix.

### 4.1. Vì sao không tự ghi kind trong writeFields()?

Không nên viết:

~~~java
private void writeFields(CardPayment value, JsonGenerator gen)
        throws IOException {

    gen.writeStringField("kind", "card");
    gen.writeStringField("reference", value.getReference());
}
~~~

nếu TypeSerializer cũng đang quản lý discriminator kind.

Nếu cả serializer và TypeSerializer cùng ghi kind, output có thể chứa property trùng hoặc type metadata không còn nhất quán với subtype resolver. Nếu type id đổi trong cấu hình, chuỗi hard-code "card" cũng có thể lệch với mapping thực tế.

Hãy để TypeSerializer ghi type id. Serializer riêng chỉ ghi dữ liệu thuộc subtype.

### 4.2. Không mở object hai lần trong serializeWithType()

Trong serialize() thông thường, serializer tự gọi writeStartObject() và writeEndObject().

Trong serializeWithType(), TypeSerializer đã quản lý prefix/suffix cho object. Vì vậy, hàm writeFields() chỉ ghi các field bên trong, không được gọi thêm writeStartObject() hoặc writeEndObject().

Sai cấu trúc có thể xảy ra nếu:
- TypeSerializer mở object.
- Serializer lại mở object lần nữa.
- Serializer đóng object trước khi TypeSerializer ghi suffix.

Hãy tách phần ghi field dùng chung thành một method không quản lý dấu ngoặc object.

## 5. Ví dụ serializer hoàn chỉnh có hỗ trợ đa hình

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.type.WritableTypeId;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.jsontype.TypeSerializer;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;

public class CardPaymentSerializer extends StdSerializer<CardPayment> {

    public CardPaymentSerializer() {
        super(CardPayment.class);
    }

    @Override
    public void serialize(
            CardPayment value,
            JsonGenerator gen,
            SerializerProvider provider
    ) throws IOException {

        gen.writeStartObject();
        writeFields(value, gen);
        gen.writeEndObject();
    }

    @Override
    public void serializeWithType(
            CardPayment value,
            JsonGenerator gen,
            SerializerProvider provider,
            TypeSerializer typeSer
    ) throws IOException {

        WritableTypeId typeId = typeSer.writeTypePrefix(
                gen,
                typeSer.typeId(value, JsonToken.START_OBJECT)
        );

        writeFields(value, gen);

        typeSer.writeTypeSuffix(gen, typeId);
    }

    private void writeFields(CardPayment value, JsonGenerator gen)
            throws IOException {

        gen.writeStringField("reference", value.getReference());
        gen.writeStringField("lastFourDigits", value.getLastFourDigits());
        gen.writeStringField("network", value.getNetwork());
    }
}
~~~

Với mapping subtype card đã khai báo, output qua PaymentMethod có thể là:

~~~json
{
  "kind": "card",
  "reference": "PAY-001",
  "lastFourDigits": "4242",
  "network": "VISA"
}
~~~

Nếu dùng custom serializer cho BankTransfer, serializer đó cũng cần triển khai serializeWithType() theo cùng nguyên tắc: TypeSerializer ghi discriminator, serializer ghi các field riêng của subtype.

### 5.1. Serializer không nên tự chịu trách nhiệm chọn subtype

CardPaymentSerializer chỉ biết cách ghi CardPayment. Nó không nên tự kiểm tra một object PaymentMethod rồi đoán object đó là CardPayment hay BankTransfer.

Việc chọn serializer cho runtime subtype thuộc serializer lookup của Jackson. Việc ghi discriminator thuộc TypeSerializer và polymorphic type configuration. Tách trách nhiệm này giúp mỗi serializer đơn giản và tránh logic lựa chọn kiểu bị lặp lại ở nhiều nơi.

## 6. Đăng ký custom serializer

Có thể đăng ký serializer bằng annotation trên subtype:

~~~java
@JsonSerialize(using = CardPaymentSerializer.class)
public class CardPayment implements PaymentMethod {
    // Các field và method.
}
~~~

Hoặc đăng ký bằng module:

~~~java
SimpleModule module = new SimpleModule();

module.addSerializer(
        CardPayment.class,
        new CardPaymentSerializer()
);

ObjectMapper mapper = JsonMapper.builder()
        .addModule(module)
        .build();
~~~

Các import thường dùng:

~~~java
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;
~~~

Dùng annotation phù hợp khi class thuộc quyền kiểm soát của ứng dụng và serializer là quy tắc gắn trực tiếp với model. Dùng module khi class thuộc thư viện bên ngoài, không thể sửa source hoặc muốn tập trung cấu hình mapping ở một nơi.

Chọn một cách đăng ký rõ ràng. Tránh đồng thời khai báo nhiều serializer cạnh tranh cho cùng một subtype nếu chưa hiểu rõ thứ tự ưu tiên giữa annotation, module và serializer factory trong phiên bản Jackson đang dùng.

## 7. Deserialization: discriminator chọn subtype trước, deserializer xử lý dữ liệu sau

Serializer riêng quyết định cách ghi JSON. Khi đọc, Jackson cần giải quyết hai việc:

1. Dựa vào discriminator để chọn class concrete.
2. Dùng deserializer phù hợp để tạo và điền dữ liệu cho class đó.

Nếu các subtype là POJO thông thường, Jackson có thể dùng BeanDeserializer mặc định để đọc field. Không nhất thiết phải viết custom deserializer chỉ vì đã có custom serializer.

Ví dụ:

~~~java
PaymentMethod method = mapper.readValue(
        """
        {
          "kind": "card",
          "reference": "PAY-001",
          "lastFourDigits": "4242",
          "network": "VISA"
        }
        """,
        PaymentMethod.class
);
~~~

Với @JsonTypeInfo và subtype mapping đúng, kết quả là CardPayment.

~~~java
assert method instanceof CardPayment;
~~~

Serializer tùy chỉnh có thể rút gọn, đổi tên hoặc biến đổi output. Nhưng JSON ghi ra vẫn phải tuân theo schema mà deserializer có thể hiểu. Nếu serializer ghi lastFourDigits thành field maskedPan, subtype POJO cần annotation hoặc custom deserializer để đọc maskedPan tương ứng.

## 8. Khi subtype cần custom deserializer

Nếu JSON của subtype có cấu trúc đặc biệt, có thể viết deserializer cho chính subtype concrete.

Ví dụ JSON card dùng object lồng nhau:

~~~json
{
  "kind": "card",
  "reference": "PAY-001",
  "card": {
    "last4": "4242",
    "brand": "VISA"
  }
}
~~~

Custom deserializer cho CardPayment:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;

public class CardPaymentDeserializer
        extends StdDeserializer<CardPayment> {

    public CardPaymentDeserializer() {
        super(CardPayment.class);
    }

    @Override
    public CardPayment deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {

        JsonNode root = parser.getCodec().readTree(parser);
        JsonNode card = root.path("card");

        CardPayment result = new CardPayment();
        result.setReference(root.path("reference").asText());
        result.setLastFourDigits(card.path("last4").asText());
        result.setNetwork(card.path("brand").asText());

        return result;
    }
}
~~~

Đăng ký trên subtype:

~~~java
@JsonDeserialize(using = CardPaymentDeserializer.class)
public class CardPayment implements PaymentMethod {
    // Field và getter/setter.
}
~~~

Hoặc dùng SimpleModule:

~~~java
SimpleModule module = new SimpleModule();

module.addDeserializer(
        CardPayment.class,
        new CardPaymentDeserializer()
);
~~~

Jackson vẫn cần type metadata ở kiểu cha để biết phải chuyển sang CardPayment. Sau khi subtype được chọn, deserializer của CardPayment xử lý cấu trúc riêng của nó.

Trong custom deserializer, cần kiểm tra node bắt buộc, null và kiểu dữ liệu theo hợp đồng. Không nên dùng asText() một cách mù quáng nếu thiếu field hoặc kiểu sai phải được báo lỗi.

### 8.1. Vì sao nên gắn custom deserializer ở subtype?

Nếu custom deserializer được gắn trực tiếp lên base type PaymentMethod và tự đọc toàn bộ JSON, nó có thể vô tình thay thế hoặc bỏ qua cơ chế polymorphic type resolution mà Jackson vốn dùng cho base type đó.

Cách dễ kiểm soát thường là:
- Đặt @JsonTypeInfo ở base type.
- Đăng ký các subtype hợp lệ.
- Đặt custom deserializer trên từng subtype cần xử lý đặc biệt.
- Để type resolver chọn subtype trước khi deserializer cụ thể đọc nội dung.

Nếu thật sự cần custom deserializer ở base type, implementation phải phối hợp rõ với TypeDeserializer và cơ chế deserializeWithType. Không nên tự đọc discriminator bằng một logic riêng rồi đồng thời để Jackson chạy một type resolver khác.

## 9. Chọn type metadata phù hợp

Jackson hỗ trợ nhiều cách đưa type id vào JSON:

| Kiểu include | Cách biểu diễn | Ví dụ ý tưởng |
|---|---|---|
| As.PROPERTY | Discriminator nằm trong object | {"kind":"card","reference":"..."} |
| As.EXISTING_PROPERTY | Dùng property đã có trong model | {"kind":"card","reference":"..."} |
| As.WRAPPER_OBJECT | Tên subtype bọc object | {"card":{"reference":"..."}} |
| As.WRAPPER_ARRAY | Type id và value nằm trong array | ["card",{"reference":"..."}] |
| As.EXTERNAL_PROPERTY | Discriminator nằm cạnh property được đa hình | {"method":{...},"methodType":"card"} |

As.PROPERTY thường dễ đọc và phù hợp với API. As.EXISTING_PROPERTY có thể hữu ích khi model đã có field kind và ứng dụng muốn field đó cũng là dữ liệu thông thường. Khi dùng custom serializer, cần hiểu TypeSerializer sẽ ghi prefix/suffix theo kiểu include đã chọn.

Một serializer viết cứng giả định object JSON luôn bắt đầu bằng dấu ngoặc nhọn có thể không tương thích với WRAPPER_ARRAY hoặc WRAPPER_OBJECT. Hãy để TypeSerializer quản lý cấu trúc bao ngoài thay vì tự hard-code discriminator.

## 10. Không ghi discriminator hai lần

Một lỗi phổ biến là vừa cấu hình @JsonTypeInfo vừa tự ghi field kind trong custom serializer.

Ví dụ serializer ghi:

~~~java
gen.writeStringField("kind", "card");
~~~

Trong khi TypeSerializer cũng ghi kind từ subtype resolver.

Điều này có thể tạo output có property trùng hoặc hành vi parser không như mong đợi. JSON object có key trùng không phải một hợp đồng tốt vì các parser khác nhau có thể xử lý key trùng khác nhau.

Quy tắc:
- TypeSerializer quản lý discriminator khi Jackson gọi serializeWithType().
- Custom serializer ghi các property nghiệp vụ.
- Nếu muốn type id lấy từ field hiện có, cấu hình @JsonTypeInfo phù hợp, chẳng hạn As.EXISTING_PROPERTY, và bảo đảm model/serializer ghi field đó đúng một lần.
- Không hard-code type id ở nhiều nơi.

## 11. Kiểu khai báo ảnh hưởng đến việc Jackson có yêu cầu type metadata hay không

Xét hai lời gọi:

~~~java
CardPayment card = new CardPayment();
PaymentMethod method = card;
~~~

Serialize qua kiểu cha:

~~~java
String polymorphicJson = mapper
        .writerFor(PaymentMethod.class)
        .writeValueAsString(method);
~~~

Kiểu writer là PaymentMethod, nên polymorphic type handling của base type được áp dụng theo cấu hình.

Serialize qua kiểu concrete:

~~~java
String concreteJson = mapper
        .writerFor(CardPayment.class)
        .writeValueAsString(card);
~~~

Ngữ cảnh kiểu khai báo khác nhau có thể ảnh hưởng cách Jackson chọn serializer và áp dụng type metadata. Nếu JSON là hợp đồng đa hình, hãy kiểm thử đúng cách gọi thực tế của ứng dụng: root value, property trong wrapper, collection hoặc map.

Không nên chỉ kiểm thử serialize object qua kiểu concrete rồi kết luận property khai báo base type trong API cũng có output giống hệt.

## 12. Polymorphic type handling trong collection

Một collection có thể chứa nhiều subtype:

~~~java
public class Checkout {
    private List<PaymentMethod> methods;

    public Checkout() {
    }

    public List<PaymentMethod> getMethods() {
        return methods;
    }

    public void setMethods(List<PaymentMethod> methods) {
        this.methods = methods;
    }
}
~~~

Ví dụ dữ liệu:

~~~java
Checkout checkout = new Checkout();
checkout.setMethods(List.of(
        new CardPayment("PAY-001", "4242", "VISA"),
        new BankTransfer("PAY-002", "VCB", "123456")
));
~~~

JSON có discriminator trên từng phần tử:

~~~json
{
  "methods": [
    {
      "kind": "card",
      "reference": "PAY-001",
      "lastFourDigits": "4242",
      "network": "VISA"
    },
    {
      "kind": "bank-transfer",
      "reference": "PAY-002",
      "bankCode": "VCB",
      "accountNumber": "123456"
    }
  ]
}
~~~

Mỗi subtype có thể dùng serializer riêng, nhưng mỗi serializer phải hỗ trợ serializeWithType() nếu Jackson yêu cầu type metadata ở vị trí phần tử.

Khi deserialize, generic type List<PaymentMethod> cho Jackson biết kiểu khai báo của phần tử là PaymentMethod; discriminator của từng phần tử chọn CardPayment hoặc BankTransfer.

## 13. Dùng SimpleModule cho cả serializer và deserializer

Có thể đăng ký các serializer/deserializer subtype trong cùng module:

~~~java
SimpleModule paymentModule = new SimpleModule("payment-module");

paymentModule.addSerializer(
        CardPayment.class,
        new CardPaymentSerializer()
);

paymentModule.addSerializer(
        BankTransfer.class,
        new BankTransferSerializer()
);

paymentModule.addDeserializer(
        CardPayment.class,
        new CardPaymentDeserializer()
);

paymentModule.addDeserializer(
        BankTransfer.class,
        new BankTransferDeserializer()
);

ObjectMapper mapper = JsonMapper.builder()
        .addModule(paymentModule)
        .build();
~~~

Subtype mapping vẫn cần được khai báo trên base type hoặc đăng ký qua cơ chế subtype phù hợp. Module cung cấp serializer/deserializer; nó không tự thay thế toàn bộ thông tin subtype trừ khi ứng dụng cũng cấu hình type resolver.

Đối với class không thuộc quyền kiểm soát của ứng dụng, module là cách mở rộng hữu ích vì không cần sửa annotation trên source model.

## 14. An toàn khi deserialize type đa hình

Discriminator là dữ liệu đầu vào có thể ảnh hưởng class được khởi tạo. Với JSON đến từ client hoặc hệ thống bên ngoài, hãy giới hạn subtype được phép.

Nên ưu tiên:
- JsonTypeInfo.Id.NAME với tên subtype logic.
- Danh sách subtype đăng ký rõ ràng.
- Type id ổn định và được kiểm soát.
- Từ chối unknown type id nếu không có fallback an toàn.
- Custom deserializer chỉ tạo đúng subtype mà ứng dụng cho phép.

Tránh bật default typing không giới hạn cho dữ liệu không đáng tin cậy. Đặc biệt, không nên cho payload tùy ý chỉ định tên class Java đầy đủ rồi yêu cầu Jackson khởi tạo class đó.

Custom serializer không giải quyết vấn đề bảo mật ở chiều đọc. Deserialization vẫn phải kiểm tra type id, schema và dữ liệu đầu vào.

## 15. Lỗi thường gặp khi kết hợp serializer riêng và đa hình

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Thiếu discriminator | Serializer chỉ triển khai serialize() | Triển khai serializeWithType() |
| Lỗi serializer không hỗ trợ type id | Serializer không xử lý polymorphic call | Dùng TypeSerializer prefix/suffix |
| JSON có kind lặp | Serializer tự ghi kind và TypeSerializer cũng ghi | Để một cơ chế duy nhất quản lý discriminator |
| JSON lồng object sai cấu trúc | Gọi writeStartObject()/writeEndObject() cả trong prefix/suffix | Tách hàm ghi field |
| Không tìm thấy subtype khi đọc | Type id chưa đăng ký hoặc sai tên | Kiểm tra @JsonSubTypes/@JsonTypeName/module |
| Đọc vào base type thất bại | Base là interface/abstract nhưng thiếu type metadata | Cấu hình type resolver hoặc truyền concrete type |
| Custom deserializer không được gọi như mong đợi | Gắn ở base type và xung đột type resolution | Gắn trên concrete subtype hoặc phối hợp TypeDeserializer |
| Output root khác output property | Kiểu writer/static type khác nhau | Kiểm thử root và property theo kiểu khai báo thực tế |
| Unknown kind gây lỗi | Discriminator không nằm trong subtype allowlist | Quy định fallback hoặc từ chối có chủ đích |

## 16. Kiểm thử serializer và type metadata cùng nhau

Không chỉ kiểm tra JSON có field đúng. Cần kiểm tra discriminator và kiểu thực tế sau khi đọc lại.

### 16.1. Kiểm thử serialization

~~~java
@Test
void writesSubtypeFieldsAndTypeId() throws Exception {
    PaymentMethod method =
            new CardPayment("PAY-001", "4242", "VISA");

    String json = mapper
            .writerFor(PaymentMethod.class)
            .writeValueAsString(method);

    JsonNode root = mapper.readTree(json);

    assertEquals("card", root.path("kind").asText());
    assertEquals("PAY-001", root.path("reference").asText());
    assertEquals("4242", root.path("lastFourDigits").asText());
    assertEquals("VISA", root.path("network").asText());
}
~~~

Test xác nhận:
- Type id có mặt.
- Field do custom serializer ghi có mặt.
- Type id không bị ghi trùng.
- Output có cấu trúc object hợp lệ.

### 16.2. Kiểm thử deserialization

~~~java
@Test
void readsCardSubtypeFromTypeId() throws Exception {
    String json = """
            {
              "kind": "card",
              "reference": "PAY-001",
              "lastFourDigits": "4242",
              "network": "VISA"
            }
            """;

    PaymentMethod method =
            mapper.readValue(json, PaymentMethod.class);

    assertInstanceOf(CardPayment.class, method);
    assertEquals("PAY-001", method.getReference());

    CardPayment card = (CardPayment) method;
    assertEquals("4242", card.getLastFourDigits());
}
~~~

Test xác nhận discriminator chọn đúng subtype và deserializer có thể khôi phục dữ liệu.

### 16.3. Kiểm thử round trip

~~~java
@Test
void roundTripsCustomPolymorphicSerializer() throws Exception {
    PaymentMethod original =
            new CardPayment("PAY-001", "4242", "VISA");

    String json = mapper
            .writerFor(PaymentMethod.class)
            .writeValueAsString(original);

    PaymentMethod restored =
            mapper.readValue(json, PaymentMethod.class);

    assertInstanceOf(CardPayment.class, restored);
    assertEquals(original.getReference(), restored.getReference());

    CardPayment restoredCard = (CardPayment) restored;
    assertEquals("4242", restoredCard.getLastFourDigits());
    assertEquals("VISA", restoredCard.getNetwork());
}
~~~

Round-trip test hữu ích vì serializer và deserializer phải đồng ý về tên property, kiểu dữ liệu và discriminator. Một chiều chạy thành công không bảo đảm chiều ngược lại cũng đúng.

### 16.4. Kiểm thử unknown type id

~~~java
@Test
void rejectsUnknownPaymentType() {
    String json = """
            {
              "kind": "crypto-wallet",
              "reference": "PAY-999"
            }
            """;

    assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(json, PaymentMethod.class)
    );
}
~~~

Nếu hệ thống có default subtype hoặc custom unknown handler, hãy kiểm thử đúng fallback đã công bố thay vì kỳ vọng exception.

## 17. Khác biệt API giữa các phiên bản Jackson

API type serializer đã có thay đổi qua các phiên bản Jackson. Các phiên bản hiện đại dùng WritableTypeId và cặp method writeTypePrefix()/writeTypeSuffix(). Code cũ có thể gặp các method dạng writeTypePrefixForObject() hoặc writeTypeSuffixForObject(), vốn đã được thay thế/deprecate trong các phiên bản mới.

Trước khi sao chép ví dụ:
- Kiểm tra phiên bản jackson-databind và jackson-core đang được dependency management chọn.
- Giữ các module Jackson cùng một dòng phiên bản tương thích.
- Xem chữ ký TypeSerializer trong đúng version.
- Chạy test root serialization và collection serialization.
- Không trộn code ví dụ API cũ với dependency mới mà không kiểm tra compile.

Nếu project dùng Jackson 2.x hiện đại, WritableTypeId là cách thể hiện type prefix/suffix rõ ràng. Với Jackson 3.x, hãy kiểm tra thay đổi package/API theo tài liệu phiên bản cụ thể.

## 18. Quy trình thiết kế thực tế

Khi cần serializer riêng cho một hierarchy đa hình, có thể thực hiện theo trình tự:

1. Xác định base type mà property hoặc API công bố.
2. Liệt kê các subtype được phép xuất hiện.
3. Chọn type id ổn định, ví dụ card hoặc bank-transfer.
4. Khai báo @JsonTypeInfo và subtype mapping.
5. Viết serializer cho từng subtype cần representation đặc biệt.
6. Triển khai cả serialize() và serializeWithType().
7. Để TypeSerializer quản lý discriminator; serializer riêng chỉ ghi field dữ liệu.
8. Nếu cần custom deserializer, gắn theo subtype concrete và giữ type resolution ở base type.
9. Đăng ký serializer/deserializer bằng annotation hoặc module theo một cách rõ ràng.
10. Kiểm thử root value, property base type, collection, unknown type id và round trip.
11. Kiểm tra JSON thực tế để chắc chắn discriminator chỉ xuất hiện một lần.
12. Giới hạn subtype được phép deserialize từ nguồn không đáng tin cậy.

## 19. Những điểm cần nhớ

- Kiểu khai báo là base class/interface không cho biết subtype cụ thể cần tạo khi đọc JSON.
- @JsonTypeInfo và subtype mapping cung cấp discriminator để Jackson chọn kiểu thực tế.
- Custom serializer ghi representation của subtype.
- Khi cần polymorphic type metadata, serializer phải hỗ trợ serializeWithType().
- TypeSerializer.writeTypePrefix()/writeTypeSuffix() quản lý cấu trúc bao ngoài và discriminator.
- Không ghi discriminator thủ công lần nữa nếu TypeSerializer đã quản lý nó.
- Hàm ghi field dùng chung không nên tự mở/đóng object trong serializeWithType().
- Custom deserializer trên subtype có thể xử lý schema đặc biệt sau khi type resolver đã chọn concrete type.
- TypeReference giữ kiểu generic của collection nhưng không thay thế discriminator cho từng subtype.
- Ưu tiên logical type name và subtype allowlist khi đọc dữ liệu không đáng tin cậy.
- Kiểm thử cả serialization, deserialization và round trip theo đúng kiểu khai báo mà ứng dụng sử dụng.

Phối hợp serializer riêng với thông tin kiểu đa hình đòi hỏi hai phần cùng tuân theo một hợp đồng JSON. Type resolver xác định object thuộc subtype nào; TypeSerializer ghi discriminator; custom serializer ghi các field riêng của subtype. Ở chiều đọc, discriminator chọn concrete class rồi deserializer tương ứng khôi phục dữ liệu. Khi phân chia đúng trách nhiệm và kiểm thử cả hai chiều, ứng dụng có thể tùy biến JSON mà vẫn giữ được khả năng khôi phục kiểu thực tế.
