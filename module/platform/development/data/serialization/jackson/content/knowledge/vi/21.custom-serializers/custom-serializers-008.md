# Tạo serializer theo ngữ cảnh thuộc tính

Một kiểu Java có thể xuất hiện ở nhiều thuộc tính nhưng cần được biểu diễn khác nhau trong từng ngữ cảnh. Ví dụ, một giá trị Money có thể được ghi thành object gồm amount và currency trong response chi tiết, nhưng chỉ ghi thành number trong một báo cáo mà currency đã được xác định ở cấp cha. Một ngày có thể cần format khác nhau ở hai field; một giá trị nhạy cảm có thể cần được che ở DTO công khai nhưng giữ nguyên ở bản ghi nội bộ.

Nếu viết một serializer chỉ dựa vào kiểu Java, mọi thuộc tính cùng kiểu thường nhận chung một cách biểu diễn. Để thay đổi hành vi theo thuộc tính đang được serialize, Jackson cung cấp interface **ContextualSerializer**. Serializer triển khai interface này có thể đọc metadata của property thông qua BeanProperty trong phương thức createContextual(), sau đó trả về một serializer đã được cấu hình riêng cho property đó.

Cơ chế này giúp tái sử dụng logic serialize theo kiểu dữ liệu trong khi vẫn giữ được khác biệt giữa các field. Điểm quan trọng là cấu hình theo ngữ cảnh phải được tạo thành instance serializer bất biến; không sửa trạng thái dùng chung của serializer trong lúc xử lý từng property.

## 1. Vì sao serializer cần biết ngữ cảnh thuộc tính?

Giả sử ứng dụng có kiểu Money:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

Cùng một kiểu Money được dùng ở nhiều nơi:

~~~java
public class InvoiceResponse {
    private Money subtotal;
    private Money tax;
    private Money total;
}
~~~

Một API có thể cần:

- subtotal được ghi thành object để consumer biết cả số tiền và đơn vị tiền tệ.
- tax được ghi thành number vì currency đã được quy định ở cấp invoice.
- total được ghi thành string theo format dành cho màn hình hiển thị.

Nếu serializer chỉ nhận Money, nó không biết giá trị hiện tại thuộc property subtotal, tax hay total. Nó chỉ nhìn thấy amount và currency.

Có thể viết ba kiểu wrapper riêng, nhưng điều đó làm domain model phình to và lặp logic. Contextual serializer giải quyết vấn đề bằng cách nhận metadata của property trước khi serialize giá trị.

~~~text
                 Kiểu Java: Money
                       |
             Serializer dùng chung
                       |
            createContextual(...)
                       |
          +------------+------------+
          |            |            |
       subtotal       tax          total
          |            |            |
       cấu hình A   cấu hình B   cấu hình C
          |            |            |
        object       number       string
~~~

Context ở đây là metadata của property trong mô hình Jackson, không phải toàn bộ HTTP request, user session hay trạng thái nghiệp vụ đang chạy. Nếu cần serialize khác nhau theo người dùng hoặc request context, cần một thiết kế rõ ràng khác; không nên lưu trạng thái request vào serializer dùng chung.

## 2. ContextualSerializer là gì?

ContextualSerializer thuộc package com.fasterxml.jackson.databind.ser. Interface này định nghĩa phương thức createContextual():

~~~java
public interface ContextualSerializer {
    JsonSerializer<?> createContextual(
        SerializerProvider provider,
        BeanProperty property
    ) throws JsonMappingException;
}
~~~

Jackson gọi phương thức này khi chuẩn bị serializer cho một vị trí cụ thể trong object graph. Serializer có thể:

- Đọc tên và kiểu của property.
- Đọc annotation trên field hoặc getter.
- Đọc metadata liên quan đến property.
- Chọn format hoặc quy tắc ghi phù hợp.
- Trả về chính instance hiện tại nếu không cần thay đổi.
- Trả về một instance serializer mới đã chứa cấu hình riêng.

Hai tham số quan trọng:

| Tham số | Vai trò |
|---|---|
| SerializerProvider | Cung cấp context serialization, cấu hình và các tiện ích của Jackson |
| BeanProperty | Mô tả property mà serializer đang phục vụ, có thể là field hoặc getter trong bean |

BeanProperty cung cấp một số thông tin hữu ích:

| Phương thức | Thông tin |
|---|---|
| getName() | Tên property theo mô hình Jackson |
| getType() | JavaType của property |
| getMember() | Thành viên Java đại diện cho property nếu có |
| getAnnotation(Class) | Annotation trực tiếp liên quan đến property |
| getContextAnnotation(Class) | Annotation từ context bao quanh, nếu có |

Không phải mọi lần contextualization đều có một BeanProperty cụ thể. Khi serializer được dùng cho root value, property có thể là null. Code phải xử lý trường hợp này bằng cấu hình mặc định.

### 2.1. createContextual() cấu hình serializer trước khi ghi value

Luồng xử lý có thể hình dung:

1. Jackson xác định kiểu của property.
2. Jackson tìm serializer cho kiểu đó.
3. Nếu serializer triển khai ContextualSerializer, Jackson gọi createContextual() với BeanProperty phù hợp.
4. Serializer trả về instance đã cấu hình.
5. Jackson gọi serialize(value, generator, provider) trên instance đó.

createContextual() không phải nơi ghi token JSON. Việc ghi JSON vẫn nằm trong serialize(). Hãy dùng createContextual() để đọc metadata và chuẩn bị cấu hình; dùng serialize() để ghi giá trị.

### 2.2. Contextualization không phải tạo serializer cho từng object

Jackson có thể cache và tái sử dụng serializer. Contextualization nhằm tạo cấu hình cho vị trí property, không có nghĩa mỗi lần serialize một object đều phải tạo một serializer mới.

Không nên dựa vào số lần createContextual() được gọi. Hãy viết phương thức sao cho an toàn nếu Jackson gọi nhiều lần và serializer được tái sử dụng.

## 3. Phân biệt serializer thông thường và contextual serializer

Serializer thông thường chỉ cần triển khai serialize():

~~~java
public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {
        generator.writeNumber(value.amount());
    }
}
~~~

Serializer này ghi mọi Money thành number. Nó không biết property đang được xử lý và không có chỗ nhận cấu hình riêng theo field.

Contextual serializer bổ sung createContextual():

~~~java
public class MoneySerializer
        extends JsonSerializer<Money>
        implements ContextualSerializer {

    @Override
    public JsonSerializer<?> createContextual(
        SerializerProvider provider,
        BeanProperty property
    ) throws JsonMappingException {
        // Đọc cấu hình của property và trả serializer phù hợp.
        return this;
    }

    @Override
    public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {
        // Ghi value theo cấu hình đã nhận.
    }
}
~~~

Trong ví dụ khung trên, trả this chỉ đúng nếu serializer không cần cấu hình khác nhau. Nếu cần scale, shape hoặc policy riêng cho từng property, hãy trả về instance mới chứa cấu hình đó.

## 4. Tạo annotation để khai báo format theo property

Một cách rõ ràng là tạo annotation riêng cho quy tắc serialize Money.

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import java.math.RoundingMode;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target({FIELD, METHOD})
@Retention(RUNTIME)
public @interface MoneyOutput {

    Shape shape() default Shape.OBJECT;

    int scale() default 2;

    RoundingMode rounding() default RoundingMode.HALF_UP;

    enum Shape {
        OBJECT,
        NUMBER
    }
}
~~~

Annotation cho phép mỗi property khai báo:

- OBJECT: ghi cả amount và currency.
- NUMBER: chỉ ghi amount dưới dạng JSON number.
- scale: số chữ số thập phân.
- rounding: quy tắc làm tròn BigDecimal.

Ví dụ DTO:

~~~java
public class InvoiceResponse {

    @MoneyOutput(shape = MoneyOutput.Shape.OBJECT, scale = 2)
    private Money subtotal;

    @MoneyOutput(
        shape = MoneyOutput.Shape.NUMBER,
        scale = 0,
        rounding = RoundingMode.HALF_UP
    )
    private Money tax;

    public Money getSubtotal() {
        return subtotal;
    }

    public Money getTax() {
        return tax;
    }
}
~~~

Annotation nằm trên field. Nếu mô hình Jackson lấy property từ getter, hãy đặt annotation trên accessor được dùng hoặc kiểm tra quy tắc hợp nhất annotation của class. Điều quan trọng là BeanProperty mà serializer nhận phải nhìn thấy annotation cần đọc.

Không cần đưa các tùy chọn serialize này vào chính class Money. Money vẫn là một value object biểu diễn số tiền và currency; cách xuất JSON thuộc hợp đồng của từng DTO/property.

## 5. Triển khai contextual serializer cho Money

Serializer dưới đây nhận cấu hình từ MoneyOutput trong createContextual(), sau đó giữ cấu hình đó trong các field final.

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.BeanProperty;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.ContextualSerializer;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MoneySerializer
        extends StdSerializer<Money>
        implements ContextualSerializer {

    private final MoneyOutput.Shape shape;
    private final int scale;
    private final RoundingMode rounding;

    public MoneySerializer() {
        this(
            MoneyOutput.Shape.OBJECT,
            2,
            RoundingMode.HALF_UP
        );
    }

    private MoneySerializer(
        MoneyOutput.Shape shape,
        int scale,
        RoundingMode rounding
    ) {
        super(Money.class);
        this.shape = shape;
        this.scale = scale;
        this.rounding = rounding;
    }

    @Override
    public JsonSerializer<?> createContextual(
        SerializerProvider provider,
        BeanProperty property
    ) throws JsonMappingException {

        if (property == null) {
            return this;
        }

        MoneyOutput config = property.getAnnotation(MoneyOutput.class);

        if (config == null) {
            return this;
        }

        if (config.scale() < 0) {
            throw JsonMappingException.from(
                provider,
                "Money scale cannot be negative for property: "
                    + property.getName()
            );
        }

        return new MoneySerializer(
            config.shape(),
            config.scale(),
            config.rounding()
        );
    }

    @Override
    public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {

        BigDecimal amount = value.amount().setScale(scale, rounding);

        if (shape == MoneyOutput.Shape.NUMBER) {
            generator.writeNumber(amount);
            return;
        }

        generator.writeStartObject();
        generator.writeNumberField("amount", amount);
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Có ba điểm quan trọng trong implementation:

1. Constructor không tham số cung cấp cấu hình mặc định để Jackson có thể khởi tạo serializer.
2. createContextual() đọc MoneyOutput từ BeanProperty và tạo instance mới chứa shape, scale, rounding.
3. serialize() chỉ đọc cấu hình bất biến và ghi token bằng JsonGenerator.

Serializer không sửa các field cấu hình sau khi được tạo. Nhờ vậy, serializer cho subtotal không thể vô tình thay đổi cấu hình của serializer cho tax.

Ví dụ trên giả định Money đã bảo đảm amount và currency không null bằng constructor hoặc validation domain. Nếu kiểu cho phép null, hãy định nghĩa rõ chính sách null trước khi serialize; không để NullPointerException trở thành cách xử lý hợp đồng.

## 6. Đăng ký serializer với ObjectMapper

Có hai cách phổ biến để Jackson sử dụng serializer.

### 6.1. Đăng ký serializer qua module

Nếu muốn mọi property kiểu Money đều đi qua serializer này, đăng ký serializer với SimpleModule:

~~~java
SimpleModule moneyModule = new SimpleModule("money-module");
moneyModule.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = JsonMapper.builder()
    .addModule(moneyModule)
    .build();
~~~

Jackson tìm MoneySerializer cho kiểu Money. Khi serializer được dùng tại một property, cơ chế contextualization cho phép nó đọc annotation MoneyOutput của property đó.

Cách này phù hợp khi muốn có một serializer chung cho kiểu Money và để từng DTO quyết định cách xuất.

### 6.2. Chỉ định serializer trên property

Nếu không muốn đăng ký toàn cục, có thể chỉ định serializer trực tiếp:

~~~java
public class InvoiceResponse {

    @JsonSerialize(using = MoneySerializer.class)
    @MoneyOutput(shape = MoneyOutput.Shape.OBJECT, scale = 2)
    private Money subtotal;

    @JsonSerialize(using = MoneySerializer.class)
    @MoneyOutput(shape = MoneyOutput.Shape.NUMBER, scale = 0)
    private Money tax;
}
~~~

Jackson tạo serializer được chỉ định cho property và contextualize nó với metadata tương ứng.

Cách này thích hợp khi chỉ một số property cần logic đặc biệt. Nếu dùng cả module registration và @JsonSerialize(using = ...), hãy xác định rõ serializer nào được chọn theo annotation và cấu hình thực tế; thông thường không cần khai báo cả hai cho cùng một property.

### 6.3. So sánh hai cách đăng ký

| Cách | Phạm vi | Điểm phù hợp |
|---|---|---|
| SimpleModule.addSerializer() | Kiểu Money trong mapper | Có một implementation chung, nhiều property cấu hình khác nhau |
| @JsonSerialize(using = ...) | Property được đánh dấu | Chỉ một số field cần serializer tùy biến |
| Serializer mặc định của Jackson | Các kiểu còn lại | Không cần logic đặc biệt |

Có thể kết hợp module và annotation cấu hình riêng như MoneyOutput. Module quyết định serializer dùng cho kiểu; annotation cung cấp tham số theo property.

## 7. Kết quả serialize khác nhau theo từng property

Với InvoiceResponse có subtotal và tax như ví dụ, giả sử:

~~~java
InvoiceResponse invoice = new InvoiceResponse(
    new Money(new BigDecimal("125.5"), "VND"),
    new Money(new BigDecimal("10.4"), "VND")
);
~~~

Serializer cho subtotal dùng OBJECT và scale 2. Serializer cho tax dùng NUMBER và scale 0.

JSON kết quả:

~~~json
{
  "subtotal": {
    "amount": 125.50,
    "currency": "VND"
  },
  "tax": 10
}
~~~

Cùng một class Money nhưng mỗi property có representation riêng.

Lưu ý rằng tax chỉ xuất number nên currency không còn nằm trong chính giá trị đó. Cách biểu diễn này chỉ hợp lý khi currency đã được xác định rõ ở cấp invoice hoặc trong hợp đồng bao quanh. Nếu consumer cần biết currency độc lập, hãy dùng OBJECT hoặc một cấu trúc khác có đủ thông tin.

## 8. Dùng BeanProperty để đọc nhiều loại metadata

Contextual serializer không bắt buộc chỉ đọc annotation tự tạo. Nó có thể đọc thông tin property để chọn hành vi.

Ví dụ:

~~~java
@Override
public JsonSerializer<?> createContextual(
    SerializerProvider provider,
    BeanProperty property
) throws JsonMappingException {

    if (property == null) {
        return this;
    }

    String propertyName = property.getName();
    JavaType propertyType = property.getType();

    // Có thể đọc annotation hoặc dựa trên metadata đã được công bố.
    // Trả về serializer phù hợp với property này.
    return this;
}
~~~

Các ứng dụng thường gặp:

- Đọc annotation format tùy biến.
- Chọn cách biểu diễn dựa trên kiểu generic của property.
- Kiểm tra property có thuộc một nhóm DTO nhất định không.
- Đọc tên property để đưa vào thông báo lỗi.
- Kết hợp metadata của field/getter với cấu hình serializer.

Không nên dùng tên property làm quy tắc ngầm nếu có thể khai báo annotation rõ ràng. Ví dụ, logic "nếu tên field là total thì ghi số" rất dễ hỏng khi property được đổi tên. Annotation mô tả ý định trực tiếp và dễ review hơn.

## 9. @JsonFormat và các annotation có sẵn

Trước khi viết annotation riêng, hãy xem Jackson đã có annotation đáp ứng nhu cầu chưa.

@JsonFormat thường được các serializer chuẩn hỗ trợ để điều chỉnh hình dạng hoặc định dạng, chẳng hạn date/time, number hoặc một số kiểu container.

Ví dụ:

~~~java
public class Report {
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    private LocalDate reportDate;
}
~~~

Nếu chỉ cần đổi định dạng ngày, không cần viết ContextualSerializer mới. Serializer của kiểu LocalDate trong module Java Time có thể đọc cấu hình format theo property.

Dùng ContextualSerializer khi:

- Quy tắc không được annotation chuẩn hỗ trợ.
- Cần đọc annotation nghiệp vụ riêng.
- Cần chọn cấu trúc JSON khác nhau cho cùng một kiểu Java.
- Cần kết hợp nhiều metadata để tạo serializer đã cấu hình.

Không nên sao chép lại các tính năng format mà Jackson đã cung cấp, vì custom code làm tăng số trường hợp phải kiểm thử và bảo trì.

## 10. Annotation trên field, getter và MixIn

BeanProperty đại diện cho property theo cách Jackson introspect class, không nhất thiết tương ứng duy nhất với một field Java.

Một property có thể được mô tả bởi:

- Field.
- Getter.
- Setter.
- Constructor parameter.
- Record component trong các phiên bản Java/Jackson hỗ trợ.

Nếu annotation nằm ở field nhưng Jackson đang dùng getter, khả năng nhìn thấy annotation phụ thuộc quy tắc hợp nhất annotation và visibility configuration.

Ví dụ:

~~~java
public class InvoiceResponse {

    private Money total;

    @MoneyOutput(shape = MoneyOutput.Shape.NUMBER, scale = 0)
    public Money getTotal() {
        return total;
    }
}
~~~

Có thể đặt annotation trực tiếp trên getter được Jackson dùng để serialize.

Nếu không thể sửa class nguồn, Jackson MixIn có thể bổ sung annotation cho property hoặc kiểu:

~~~java
abstract class InvoiceResponseMixIn {

    @JsonSerialize(using = MoneySerializer.class)
    @MoneyOutput(shape = MoneyOutput.Shape.NUMBER, scale = 0)
    abstract Money getTotal();
}
~~~

Đăng ký MixIn:

~~~java
mapper.addMixIn(InvoiceResponse.class, InvoiceResponseMixIn.class);
~~~

MixIn hữu ích khi tích hợp thư viện bên ngoài hoặc giữ domain model độc lập với Jackson annotation. Hãy kiểm tra rằng BeanProperty nhận được đúng annotation từ MixIn trong cấu hình mapper thực tế.

## 11. Serializer contextual cho collection và Map

Một property có thể chứa nhiều giá trị cùng kiểu:

~~~java
public class InvoiceResponse {
    private List<Money> lineAmounts;
}
~~~

Nếu cần serializer riêng cho phần tử collection, có thể dùng contentUsing:

~~~java
public class InvoiceResponse {

    @JsonSerialize(contentUsing = MoneySerializer.class)
    @MoneyOutput(shape = MoneyOutput.Shape.NUMBER, scale = 2)
    private List<Money> lineAmounts;
}
~~~

Contextual serializer của phần tử có thể nhận metadata property chứa collection. Vì vậy, annotation trên property collection có thể được dùng như cấu hình chung cho các phần tử, tùy cách serializer được contextualize trong cấu trúc đó. Hãy kiểm tra chính xác hành vi bằng test với phiên bản Jackson của dự án.

Các annotation liên quan:

| Thuộc tính của @JsonSerialize | Mục đích |
|---|---|
| using | Serializer cho chính property |
| contentUsing | Serializer cho phần tử collection hoặc value của Map |
| keyUsing | Serializer cho key của Map |
| nullsUsing | Serializer cho giá trị null của property |

Nếu key của Map cần ngữ cảnh riêng, Jackson có interface contextual dành cho key serializer, thường được triển khai bằng ContextualKeySerializer. Đây là cơ chế riêng cho key serialization; không giả định rằng serializer value có thể xử lý key của Map.

### 11.1. Context của container và context của phần tử

Một property List<Money> là một property có kiểu List<Money>. Serializer của Money được dùng cho từng phần tử, nhưng BeanProperty có thể đại diện cho property chứa danh sách chứ không phải một field riêng cho từng phần tử.

Vì vậy, nếu annotation mô tả cách serialize toàn bộ danh sách, đừng vô tình áp dụng cùng quy tắc cho từng Money. Hãy phân biệt:

- using: serialize chính giá trị của property.
- contentUsing: serialize từng phần tử hoặc value.
- keyUsing: serialize key của Map.

Khi cần metadata riêng cho từng phần tử, cân nhắc kiểu wrapper, serializer cho container hoặc DTO có cấu trúc rõ ràng.

## 12. Serializer contextual và serializer cho null

Jackson thường xử lý null bằng null serializer của SerializerProvider; method serialize() của serializer cho kiểu Money thông thường không được gọi với một giá trị null như một object bình thường.

Do đó, nếu property Money là null, không nên kỳ vọng code kiểm tra null trong MoneySerializer.serialize() sẽ quyết định output.

Nếu cần null policy riêng cho property, có thể dùng nullsUsing trong @JsonSerialize hoặc các cơ chế null serialization tương ứng. Hãy tách hai câu hỏi:

- Property có giá trị Money: MoneySerializer quyết định cách ghi.
- Property có giá trị null: null serializer/policy quyết định cách ghi.

Ví dụ annotation:

~~~java
@JsonSerialize(
    using = MoneySerializer.class,
    nullsUsing = CustomNullSerializer.class
)
private Money optionalAmount;
~~~

CustomNullSerializer phải triển khai serializer cho kiểu phù hợp và ghi JSON token theo hợp đồng, ví dụ null, chuỗi placeholder hoặc một cấu trúc đặc biệt. Tránh dùng placeholder nếu nó khiến consumer nhầm null với một giá trị tiền thật.

## 13. Không sửa serializer dùng chung trong createContextual()

Đây là nguyên tắc quan trọng nhất khi viết contextual serializer.

Không nên:

~~~java
public JsonSerializer<?> createContextual(
    SerializerProvider provider,
    BeanProperty property
) {
    this.scale = readScale(property);
    return this;
}
~~~

Nếu Jackson dùng chung instance serializer cho nhiều property, cấu hình của property cuối cùng có thể ghi đè cấu hình trước đó. Trong môi trường nhiều request hoặc nhiều thread, hành vi có thể trở nên không xác định.

Cách đúng là dùng field final và trả instance mới:

~~~java
public JsonSerializer<?> createContextual(
    SerializerProvider provider,
    BeanProperty property
) {
    int propertyScale = readScale(property);

    return new MoneySerializer(
        MoneyOutput.Shape.NUMBER,
        propertyScale,
        RoundingMode.HALF_UP
    );
}
~~~

Serializer contextual đã tạo chỉ chứa cấu hình bất biến. Không lưu BeanProperty, request, user hoặc dữ liệu của object đang serialize vào field mutable.

### 13.1. Khi nào trả về this?

Nếu property không có annotation hoặc cấu hình giống hệt instance hiện tại, có thể trả về this:

~~~java
if (config == null) {
    return this;
}
~~~

Nếu annotation có cùng giá trị với cấu hình hiện tại, có thể kiểm tra và trả this để giảm instance không cần thiết. Đây là tối ưu nhỏ; ưu tiên code rõ và đúng trước.

### 13.2. Không lưu trạng thái giữa các lần serialize

Không đặt các thông tin sau vào field mutable của serializer:

- Giá trị đang serialize.
- Tên property vừa xử lý.
- User hiện tại.
- Request ID.
- Locale thay đổi theo request.
- JsonGenerator đang sử dụng.
- SerializerProvider của một lần gọi.

Serializer có thể được tái sử dụng và chạy đồng thời. Cấu hình bất biến theo property là phù hợp; trạng thái theo từng lần gọi phải nằm trong biến cục bộ hoặc được truyền qua cơ chế context có lifecycle rõ.

## 14. ContextualSerializer và ContextualDeserializer

Hai interface giải quyết hai chiều khác nhau:

| Interface | Chiều | Mục đích |
|---|---|---|
| ContextualSerializer | Java object → JSON | Chọn cách ghi theo property |
| ContextualDeserializer | JSON → Java object | Chọn cách đọc theo property |

Ví dụ, Money được serialize thành number ở field tax và object ở field subtotal. Nếu muốn deserialize hai hình dạng này trở lại cùng kiểu Money, custom deserializer cũng cần biết property đang được đọc để diễn giải number hoặc object theo hợp đồng tương ứng.

ContextualDeserializer có phương thức createContextual() nhận DeserializationContext và BeanProperty. Nó có thể đọc cùng annotation MoneyOutput hoặc một annotation input riêng, rồi trả về deserializer đã cấu hình.

Không nên giả định @JsonValue hoặc ContextualSerializer tự tạo ra chiều deserialize. Hai chiều cần được thiết kế và kiểm thử riêng, nhất là khi một kiểu Java có nhiều JSON representation.

## 15. Dùng serializer theo context cho che dữ liệu

Một ứng dụng có thể cần cùng kiểu dữ liệu nhưng mức hiển thị khác nhau. Ví dụ EmailAddress đầy đủ trong event nội bộ, nhưng che một phần trong response công khai.

Có thể tạo annotation:

~~~java
@Target({FIELD, METHOD})
@Retention(RUNTIME)
public @interface EmailView {
    boolean masked() default true;
}
~~~

Serializer contextual đọc annotation và trả instance có cấu hình masked:

~~~java
public final class EmailSerializer
        extends StdSerializer<EmailAddress>
        implements ContextualSerializer {

    private final boolean masked;

    public EmailSerializer() {
        this(false);
    }

    private EmailSerializer(boolean masked) {
        super(EmailAddress.class);
        this.masked = masked;
    }

    @Override
    public JsonSerializer<?> createContextual(
        SerializerProvider provider,
        BeanProperty property
    ) {
        EmailView view = property == null
            ? null
            : property.getAnnotation(EmailView.class);

        return view == null
            ? this
            : new EmailSerializer(view.masked());
    }

    @Override
    public void serialize(
        EmailAddress value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {
        String output = masked
            ? mask(value.value())
            : value.value();

        generator.writeString(output);
    }

    private String mask(String email) {
        int at = email.indexOf('@');

        if (at <= 1) {
            return "***" + email.substring(Math.max(at, 0));
        }

        return email.charAt(0)
            + "***"
            + email.substring(at);
    }
}
~~~

DTO:

~~~java
public class UserResponse {

    @EmailView(masked = true)
    private EmailAddress publicEmail;

    @EmailView(masked = false)
    private EmailAddress internalEmail;
}
~~~

Ví dụ này chỉ minh họa cơ chế theo property. Không dùng annotation serialize làm cơ chế authorization hoặc bảo vệ dữ liệu duy nhất. DTO công khai nên chỉ chứa dữ liệu được phép công bố; việc che dữ liệu cần được kiểm thử và kiểm soát ở tầng API phù hợp.

## 16. Khi cần thông tin runtime thay đổi theo request

ContextualSerializer phù hợp với metadata ổn định của property như annotation, kiểu dữ liệu và cấu hình mapper. Nó không phải cơ chế mặc định để đọc user hiện tại hoặc quyền của request.

Ví dụ, cùng một property có thể cần che email tùy quyền của người gọi. Không nên tạo serializer mutable rồi cập nhật field masked theo từng request. Serializer có thể được cache và dùng đồng thời.

Các lựa chọn phù hợp hơn:

- Tạo DTO khác nhau cho response công khai và nội bộ.
- Chuẩn bị giá trị đã che trước khi serialize.
- Dùng một cơ chế provider/context có lifecycle rõ ràng nếu kiến trúc thực sự cần serialization theo request.
- Dùng custom serializer có truy cập context được thiết kế và kiểm soát, đồng thời bảo đảm không lưu trạng thái request vào instance dùng chung.

Nếu chỉ khác nhau giữa hai API, hai response DTO thường dễ hiểu và an toàn hơn một serializer phụ thuộc quyền người dùng.

## 17. Xử lý lỗi trong contextualization và serialize()

createContextual() có thể ném JsonMappingException nếu metadata không hợp lệ. Ví dụ scale âm hoặc annotation xung đột.

serialize() có thể ném IOException/JsonMappingException nếu giá trị không thể biểu diễn hoặc generator gặp lỗi.

Nên tạo thông báo lỗi có tên property khi có thể:

~~~java
if (config.scale() < 0) {
    throw JsonMappingException.from(
        provider,
        "Invalid scale for property " + property.getName()
    );
}
~~~

Không nên âm thầm fallback sang format khác nếu cấu hình sai. Fallback có thể tạo JSON hợp lệ về cú pháp nhưng sai hợp đồng.

Một số lỗi thường gặp:

- Annotation không được BeanProperty nhìn thấy.
- Serializer không có constructor phù hợp để Jackson khởi tạo.
- createContextual() sửa instance dùng chung.
- Serializer được gán cho kiểu không tương thích.
- Property root không có BeanProperty nhưng code giả định luôn khác null.
- Null serializer bị nhầm với serializer cho value.
- Annotation trên collection bị hiểu nhầm là annotation của từng phần tử.
- Serializer gọi lại ObjectMapper trên chính value hiện tại gây đệ quy.

## 18. Kiểm thử contextual serializer

Cần kiểm tra cùng một kiểu Java nhưng các property khác nhau thực sự tạo JSON khác nhau theo annotation.

Ví dụ cấu hình mapper qua module:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(
        new SimpleModule()
            .addSerializer(Money.class, new MoneySerializer())
    )
    .build();
~~~

Test:

~~~java
@Test
void serializesSameTypeDifferentlyByProperty() throws Exception {
    InvoiceResponse invoice = new InvoiceResponse(
        new Money(new BigDecimal("125.5"), "VND"),
        new Money(new BigDecimal("10.4"), "VND")
    );

    JsonNode json = mapper.readTree(
        mapper.writeValueAsString(invoice)
    );

    assertTrue(json.path("subtotal").isObject());
    assertEquals(
        new BigDecimal("125.50"),
        json.path("subtotal").path("amount").decimalValue()
    );
    assertEquals("VND", json.path("subtotal").path("currency").asText());

    assertTrue(json.path("tax").isNumber());
    assertEquals(10, json.path("tax").intValue());
}
~~~

Test này chứng minh annotation của từng property ảnh hưởng đến serializer.

### 18.1. Test property không có annotation

Nếu property không có MoneyOutput, serializer phải dùng default đã định nghĩa:

~~~java
@Test
void usesDefaultConfigurationWithoutPropertyAnnotation() throws Exception {
    Money value = new Money(new BigDecimal("12.3"), "VND");

    JsonNode json = mapper.readTree(
        mapper.writeValueAsString(value)
    );

    assertTrue(json.isObject());
    assertEquals(
        new BigDecimal("12.30"),
        json.path("amount").decimalValue()
    );
}
~~~

Root value không có BeanProperty nên serializer dùng cấu hình mặc định. Nếu root cần format khác, hãy cung cấp writer/serializer riêng hoặc bọc giá trị trong DTO có annotation.

### 18.2. Test serializer không rò cấu hình giữa các property

Serialize một DTO có hai property cùng kiểu nhưng cấu hình khác nhau nhiều lần:

~~~java
@Test
void contextualConfigurationDoesNotLeakBetweenProperties()
        throws Exception {

    InvoiceResponse invoice = sampleInvoice();

    String first = mapper.writeValueAsString(invoice);
    String second = mapper.writeValueAsString(invoice);

    assertEquals(first, second);

    JsonNode json = mapper.readTree(first);
    assertTrue(json.path("subtotal").isObject());
    assertTrue(json.path("tax").isNumber());
}
~~~

Test này giúp phát hiện lỗi serializer mutable làm cấu hình property này ghi đè property khác.

### 18.3. Các trường hợp cần test thêm

- Annotation trên field và getter.
- MixIn bổ sung annotation.
- Property root với property null context.
- Giá trị null và nullsUsing.
- Money nằm trong List hoặc Map.
- contentUsing và keyUsing.
- BigDecimal rounding, scale và giá trị âm.
- Property không có annotation.
- Hai property cùng kiểu nhưng format khác nhau.
- Nhiều request serialize đồng thời.
- JSON output đúng schema và không mất currency ngoài ý muốn.

Không chỉ kiểm tra serializer được gọi. Hãy assert cấu trúc JSON và giá trị cuối cùng mà consumer nhận được.

## 19. Quy trình triển khai contextual serializer

1. Xác định cùng một kiểu Java có cần nhiều representation theo property hay không.
2. Kiểm tra @JsonFormat hoặc serializer chuẩn có đáp ứng được không.
3. Thiết kế annotation riêng chỉ chứa các tùy chọn thực sự cần thiết.
4. Triển khai JsonSerializer<T> và ContextualSerializer.
5. Đọc annotation qua BeanProperty trong createContextual().
6. Trả instance mới với các field cấu hình final; không sửa serializer dùng chung.
7. Xử lý property null context bằng cấu hình mặc định.
8. Ghi token trong serialize() bằng JsonGenerator.
9. Đăng ký qua SimpleModule hoặc @JsonSerialize(using = ...).
10. Phân biệt serializer cho property, content serializer, key serializer và null serializer.
11. Test cùng một kiểu ở nhiều property, root value, collection và trường hợp null.
12. Kiểm tra JSON output là hợp đồng ổn định mà consumer mong đợi.

## 20. Nguyên tắc nên giữ

- Dùng ContextualSerializer khi cách ghi phụ thuộc metadata của property.
- Đọc annotation và kiểu property trong createContextual(), ghi JSON trong serialize().
- Xử lý trường hợp BeanProperty là null khi serialize root value.
- Dùng field final và instance serializer mới cho mỗi cấu hình khác nhau.
- Không sửa trạng thái serializer dùng chung.
- Không lưu request, user hoặc object đang serialize vào field mutable.
- Dùng @JsonFormat nếu annotation chuẩn đã đáp ứng yêu cầu.
- Dùng @JsonSerialize(using), contentUsing, keyUsing đúng vị trí.
- Tách null serialization khỏi value serialization.
- Không nhầm metadata của container với metadata riêng của từng phần tử.
- Dùng DTO riêng nếu format phụ thuộc authorization hoặc mục đích API.
- Test JSON thực tế, nhiều property cùng kiểu và việc cấu hình không rò rỉ.

Contextual serializer cho phép Jackson điều chỉnh cách serialize một kiểu Java dựa trên property đang chứa nó. BeanProperty cung cấp annotation và metadata; createContextual() tạo serializer đã cấu hình; serialize() ghi giá trị theo cấu hình đó. Khi giữ serializer bất biến, phân biệt rõ property với container content và kiểm thử các representation khác nhau, ứng dụng có thể tái sử dụng logic serialize mà vẫn giữ được hợp đồng JSON riêng cho từng thuộc tính.

