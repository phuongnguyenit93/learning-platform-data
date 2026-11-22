# Giải quyết xung đột giữa module, annotation và cấu hình

Trong Jackson, cùng một kiểu Java có thể chịu ảnh hưởng từ nhiều nguồn cấu hình: annotation đặt trực tiếp trên class hoặc property, annotation bổ sung qua Mix-in, serializer/deserializer được đăng ký trong `Module`, và các feature ở cấp `ObjectMapper`. Khi những nguồn này cùng định nghĩa cách đọc hoặc ghi một giá trị, kết quả có thể khác với điều mà người viết cấu hình mong đợi.

Để giải quyết xung đột, trước hết cần phân biệt vai trò của từng nguồn:

- **Annotation trên mô hình** mô tả cách một class hoặc property tham gia vào JSON.
- **Mix-in** bổ sung hoặc ghi đè metadata annotation cho một kiểu mà không sửa source class.
- **Module** đăng ký serializer, deserializer, key serializer, subtype, modifier và các thành phần mở rộng khác.
- **Mapper configuration** đặt chính sách chung như visibility, naming, inclusion, coercion và các feature serialize/deserialize.
- **ObjectReader/ObjectWriter** tạo cấu hình bất biến cho một lần đọc hoặc ghi cụ thể.

Không có một quy tắc “nguồn A luôn thắng nguồn B” áp dụng cho mọi extension point. Jackson có những điểm ưu tiên phổ biến trong quá trình tìm serializer/deserializer, nhưng modifier, contextual serializer, loại property và phiên bản thư viện có thể làm thay đổi kết quả. Cách an toàn là hiểu từng tầng, tránh khai báo cạnh tranh không cần thiết và kiểm tra bằng đúng `ObjectMapper` mà ứng dụng đang dùng.

## 1. Các nguồn cấu hình của Jackson

Hãy xem một property `Money total` cần được ghi thành JSON. Cách ghi có thể được chỉ định ở nhiều nơi:

```java
@JsonSerialize(using = MoneyAnnotationSerializer.class)
public class Money {
    private BigDecimal amount;
    private String currency;
}
```

Một module cũng có thể đăng ký serializer cho `Money`:

```java
SimpleModule module = new SimpleModule("money-module");
module.addSerializer(Money.class, new MoneyModuleSerializer());
```

Mix-in có thể gắn một annotation serializer khác vào `Money`:

```java
@JsonSerialize(using = MoneyMixinSerializer.class)
abstract class MoneyMixin {
}
```

Mapper còn có thể tắt annotation hoặc thay đổi chính sách serialize:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(MapperFeature.USE_ANNOTATIONS);
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
```

Nếu tất cả cấu hình trên cùng xuất hiện, không nên suy luận kết quả chỉ bằng cách nhìn thứ tự các dòng code. Cần biết Jackson đang chọn serializer từ annotation hay module, Mix-in được ghép vào annotation metadata ra sao, và có modifier nào can thiệp sau đó hay không.

## 2. Vai trò và phạm vi của annotation

Annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonInclude`, `@JsonSerialize` và `@JsonDeserialize` được Jackson đọc thông qua cơ chế annotation introspection.

Một số annotation tác động đến tên và khả năng xuất hiện của property; một số chọn serializer/deserializer; một số thay đổi null handling hoặc type metadata. Annotation có thể nằm trên:

- Class hoặc record.
- Field.
- Getter hoặc setter.
- Constructor/creator parameter.
- Property cụ thể trong một DTO.

Phạm vi càng cụ thể thì cấu hình càng gắn với một vị trí dữ liệu cụ thể. Ví dụ, serializer đặt trên một property thường chỉ điều khiển property đó, trong khi serializer đặt trên class có thể ảnh hưởng mọi nơi kiểu đó được sử dụng.

### 2.1. Property-level và type-level

Giả sử `Money` có serializer ở cấp class:

```java
@JsonSerialize(using = MoneyObjectSerializer.class)
public class Money {
    private BigDecimal amount;
    private String currency;
}
```

Một DTO có thể cần ghi riêng property `total` thành chuỗi:

```java
public class Invoice {
    private Money subtotal;

    @JsonSerialize(using = MoneyAsTextSerializer.class)
    private Money total;
}
```

Ở vị trí `total`, annotation gắn trực tiếp vào property là chỉ dẫn cụ thể cho property đó. `subtotal` vẫn dùng cách serialize thông thường của `Money`. Đây là cách hợp lý khi cùng kiểu Java cần nhiều wire format theo ngữ cảnh.

Đừng đặt serializer ở cấp class chỉ để xử lý một trường hợp đơn lẻ trong một DTO; điều đó có thể ảnh hưởng các API khác sử dụng cùng kiểu.

## 3. Mix-in là lớp annotation bổ sung

Mix-in cho phép Jackson nhìn thấy annotation từ một class khác như metadata gắn với target type hoặc member tương ứng. Nó không phải một serializer và không tự biến đổi dữ liệu. Mix-in chỉ cung cấp annotation metadata; chính annotation đó mới yêu cầu Jackson thực hiện hành vi cụ thể.

Ví dụ, `ExternalMoney` thuộc thư viện bên thứ ba nên không thể sửa source:

```java
public class ExternalMoney {
    public BigDecimal amount() { /* ... */ return null; }
    public String currency() { /* ... */ return null; }
}
```

Tạo Mix-in:

```java
@JsonSerialize(using = ExternalMoneySerializer.class)
abstract class ExternalMoneyMixin {
}
```

Đăng ký:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalMoney.class, ExternalMoneyMixin.class);
```

Sau khi đăng ký, Jackson sử dụng annotation từ `ExternalMoneyMixin` khi introspect `ExternalMoney`. Điều này giúp thêm serializer mà không sửa class gốc.

### 3.1. Mix-in có thể ghi đè annotation trên target

Mix-in được ghép vào annotation view của target. Khi cùng một annotation được khai báo trên cùng class/member, metadata từ Mix-in thường được ưu tiên cho mục đích tương ứng; Mix-in cũng có thể bổ sung annotation mà target chưa khai báo.

Tuy nhiên, không nên hiểu đây là phép thay thế văn bản đơn giản cho mọi annotation. Một số annotation có quy tắc hợp nhất hoặc tích lũy metadata riêng; kết quả phụ thuộc cách `AnnotationIntrospector` diễn giải annotation đó. Ví dụ, các khai báo subtype, property và creator có thể được xử lý theo quy tắc chuyên biệt.

Nếu Mix-in được dùng để thay một cấu hình cũ, hãy kiểm tra đúng member và đúng annotation cần thay. Mix-in áp dụng theo target class đã đăng ký, không phải theo một request riêng.

### 3.2. Một target class chỉ có một Mix-in đang áp dụng

`addMixIn(Target.class, Mixin.class)` gắn Mix-in cho target trong mapper. Nếu gọi lại cho cùng target bằng một Mix-in khác, mapping hiện tại được thay bằng mapping mới theo cấu hình mapper; không nên giả định nhiều Mix-in độc lập sẽ tự động cộng dồn.

Nếu hai API cần hai cách Mix-in khác nhau cho cùng class, hãy cân nhắc hai `ObjectMapper` được cấu hình riêng, hoặc thiết kế DTO/wire model riêng. Không nên thay Mix-in trên mapper dùng chung trong lúc request đang chạy.

## 4. Module chịu trách nhiệm đăng ký thành phần mở rộng

Module là cơ chế mở rộng cấp mapper/factory. `SimpleModule` thường được dùng để đăng ký serializer, deserializer, key serializer, key deserializer, abstract type mapping, subtype và serializer/deserializer modifier.

Ví dụ đăng ký serializer:

```java
SimpleModule module = new SimpleModule("money-module");
module.addSerializer(Money.class, new MoneyModuleSerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Ví dụ đăng ký deserializer:

```java
SimpleModule module = new SimpleModule("money-module");
module.addDeserializer(Money.class, new MoneyDeserializer());
mapper.registerModule(module);
```

Module phù hợp khi muốn cấu hình tập trung, tích hợp kiểu bên thứ ba hoặc giữ domain model không phụ thuộc Jackson annotation.

### 4.1. Các điểm mở rộng thường gặp trong Module

| Thành phần | Vai trò |
| --- | --- |
| `addSerializer()` | Đăng ký serializer cho kiểu Java |
| `addDeserializer()` | Đăng ký deserializer cho kiểu Java |
| `addKeySerializer()` | Đăng ký cách ghi key của Map |
| `addKeyDeserializer()` | Đăng ký cách đọc key của Map |
| `registerSubtypes()` | Đăng ký subtype cho polymorphic handling |
| `addAbstractTypeMapping()` | Ánh xạ abstract type sang kiểu triển khai |
| `setSerializerModifier()` | Can thiệp vào quá trình xây dựng/chỉnh serializer |
| `setDeserializerModifier()` | Can thiệp vào quá trình xây dựng/chỉnh deserializer |
| `setMixInAnnotation()` | Đăng ký Mix-in qua module |

Không phải mọi module đều dùng tất cả điểm mở rộng. Module có thể đóng gói một nhóm cấu hình liên quan, ví dụ Java Time module đăng ký hỗ trợ các kiểu ngày giờ.

## 5. Annotation serializer và serializer đăng ký qua Module

Đây là một xung đột thường gặp. Một class có `@JsonSerialize(using = ...)`, đồng thời module cũng đăng ký serializer cho cùng kiểu.

Trong luồng Databind thông dụng, Jackson tìm serializer được chỉ định bằng annotation trước khi tìm custom serializer đăng ký qua factory/module. Vì vậy, serializer annotation thường được chọn thay cho serializer đăng ký bằng `SimpleModule` cho cùng kiểu.

Ví dụ:

```java
@JsonSerialize(using = MoneyAnnotationSerializer.class)
public class Money {
    // ...
}
```

```java
SimpleModule module = new SimpleModule();
module.addSerializer(Money.class, new MoneyModuleSerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Nếu annotation vẫn được bật và được nhận diện, hãy kỳ vọng `MoneyAnnotationSerializer` là serializer được chọn trong đường xử lý thông thường. Đăng ký module không đồng nghĩa với việc tự động thay thế serializer đã được chỉ định rõ bằng annotation.

Điều tương tự cần được xem xét ở chiều deserialize với `@JsonDeserialize(using = ...)` và deserializer đăng ký trong module. Hãy kiểm tra bằng test trên đúng phiên bản Jackson thay vì giả định serializer và deserializer có mọi chi tiết ưu tiên giống nhau trong tất cả extension path.

### 5.1. Muốn module trở thành nguồn cấu hình chính

Nếu module phải kiểm soát cách biểu diễn kiểu, cách rõ ràng nhất là bỏ annotation serializer cạnh tranh khỏi class/property do ứng dụng sở hữu. Nếu không thể sửa class bên thứ ba, hãy cân nhắc Mix-in để quản lý annotation view có chủ đích, hoặc dùng mapper riêng với chính sách annotation phù hợp.

Tắt `MapperFeature.USE_ANNOTATIONS` sẽ vô hiệu hóa annotation introspection nói chung, bao gồm cả annotation trên target và Mix-in. Đây là thay đổi rộng, có thể làm mất `@JsonProperty`, `@JsonIgnore`, `@JsonCreator`, `@JsonTypeInfo` và nhiều metadata khác. Không nên tắt chỉ để sửa một serializer nếu ứng dụng còn phụ thuộc vào các annotation đó.

Một `BeanSerializerModifier` hoặc `BeanDeserializerModifier` có thể can thiệp vào serializer/deserializer ở giai đoạn factory xây dựng chúng. Tuy nhiên, modifier không phải công tắc universal để ghi đè mọi serializer đã được chọn từ annotation; phạm vi modifier được áp dụng phụ thuộc đường tạo serializer/deserializer. Hãy xác định loại serializer cụ thể và kiểm thử trước khi dùng modifier làm cơ chế override.

## 6. Thứ tự đăng ký Module và xung đột giữa nhiều Module

Một mapper có thể đăng ký nhiều module:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.registerModule(applicationModule);
mapper.registerModule(integrationModule);
```

Module được setup vào mapper/factory theo thứ tự đăng ký. Bên trong một `SimpleModule`, việc thêm nhiều handler trùng kiểu vào cùng registry có thể thay entry trước đó. Nhưng giữa nhiều module khác nhau, kết quả lookup còn phụ thuộc cách factory thu thập và duyệt extension objects, loại registry và phiên bản Jackson. Không nên suy ra rằng module đăng ký sau luôn thay module trước.

Lý do là các module có thể đóng góp những loại thành phần khác nhau:

- Custom serializer/deserializer lookup.
- Serializer/deserializer modifiers được áp dụng theo chuỗi.
- Abstract type resolver.
- Subtype resolver.
- Annotation introspector hoặc Mix-in.
- Các feature/configuration được module thay đổi trong quá trình setup.

Mỗi loại có quy tắc kết hợp riêng. Với modifier, nhiều modifier có thể lần lượt nhận serializer/deserializer đã được tạo hoặc đã được modifier trước đó xử lý. Với subtype, mapping có thể được tích lũy. Với Mix-in, mapping cho cùng target có thể bị thay thế. Vì vậy, thứ tự module có ý nghĩa nhưng kết quả phụ thuộc loại cấu hình mà module đăng ký.

### 6.1. Cách quản lý module có trật tự

Nên có một điểm bootstrap tạo mapper và đăng ký module theo thứ tự được tài liệu hóa:

```java
public final class JsonMapperFactory {
    public static ObjectMapper create() {
        ObjectMapper mapper = new ObjectMapper();

        mapper.registerModule(new JavaTimeModule());
        mapper.registerModule(createDomainModule());
        mapper.registerModule(createIntegrationModule());

        return mapper;
    }
}
```

Đặt module nền tảng trước, sau đó đến module domain và module tích hợp của ứng dụng nếu thứ tự đó phù hợp với cách các extension được đăng ký. Quan trọng nhất là không để nhiều module cùng tranh quyền định nghĩa một kiểu mà không có quy ước rõ ràng.

Đặt tên module có ý nghĩa và dùng `getRegisteredModuleIds()` để quan sát các module đã đăng ký:

```java
System.out.println(mapper.getRegisteredModuleIds());
```

Danh sách này hữu ích để kiểm tra module nào đã được đăng ký, nhưng không cho biết đầy đủ serializer nào cuối cùng được chọn cho từng property. Muốn xác nhận hành vi, cần serialize/deserialize một input đại diện.

## 7. Mapper-wide configuration và annotation

Mapper có các feature mặc định áp dụng rộng cho quá trình serialize/deserialize. Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.enable(SerializationFeature.INDENT_OUTPUT);
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
```

Các cấu hình này tạo chính sách mặc định của mapper. Annotation trên class/property có thể cung cấp chỉ dẫn cụ thể hơn cho một kiểu hoặc property. Ví dụ, mapper đặt inclusion mặc định là `NON_NULL`, nhưng một property có thể dùng `@JsonInclude(ALWAYS)` để yêu cầu ghi cả null theo cấu hình annotation mà Jackson hỗ trợ.

Tương tự, naming strategy ở cấp mapper có thể chuyển `firstName` thành `first_name`, trong khi `@JsonProperty("displayName")` đặt tên wire rõ ràng cho property đó. Khi có xung đột, cần hiểu annotation nào có ý nghĩa explicit và cấu hình mapper nào là mặc định.

Không nên xem mọi `MapperFeature`, `SerializationFeature` và `DeserializationFeature` là cùng một loại ưu tiên. Mỗi feature điều khiển một phần khác nhau của pipeline; có feature chỉ ảnh hưởng hành vi mặc định, có feature thay đổi cách Jackson introspect mô hình, có feature tác động parser/generator.

## 8. ObjectReader và ObjectWriter cho cấu hình theo lần gọi

Nếu một endpoint cần hành vi khác mapper chung, không nhất thiết phải thay đổi cấu hình toàn cục. `ObjectReader` và `ObjectWriter` là các đối tượng cấu hình bất biến, có thể tạo từ mapper và thêm/bớt feature cho một lần đọc/ghi.

Ví dụ reader riêng chấp nhận unknown property:

```java
ObjectReader tolerantReader = mapper.readerFor(PartnerPayload.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

PartnerPayload payload = tolerantReader.readValue(json);
```

Reader khác vẫn strict theo mapper mặc định:

```java
ObjectReader strictReader = mapper.readerFor(InternalCommand.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Writer riêng bật pretty print:

```java
ObjectWriter prettyWriter = mapper.writer()
        .with(SerializationFeature.INDENT_OUTPUT);

String json = prettyWriter.writeValueAsString(value);
```

Cách này giảm nguy cơ thay đổi mapper dùng chung ảnh hưởng các request khác. Tuy nhiên, ObjectReader/ObjectWriter không phải nơi đăng ký tùy ý mọi module hoặc thay Mix-in cho từng lần gọi; nếu cần một annotation/module registry khác, hãy dùng mapper riêng được cấu hình trước.

## 9. Không thay đổi ObjectMapper dùng chung sau khi bắt đầu sử dụng

`ObjectMapper` được thiết kế để cấu hình rồi tái sử dụng. Sau khi mapper đã được dùng để đọc/ghi, thay đổi cấu hình hoặc đăng ký module trong lúc nhiều request đang chạy có thể gây hành vi khó dự đoán, đặc biệt nếu serializer/deserializer đã được cache.

Quy tắc thực tế:

1. Tạo mapper ở giai đoạn khởi tạo ứng dụng.
2. Đăng ký module, Mix-in và feature cần thiết.
3. Hoàn tất cấu hình trước khi chia sẻ mapper cho nhiều thread.
4. Sau đó dùng mapper như cấu hình ổn định.
5. Tạo `ObjectReader`/`ObjectWriter` cho khác biệt theo lần gọi.
6. Nếu cần một bộ annotation/module hoàn toàn khác, tạo mapper riêng thay vì mutate mapper dùng chung.

Nếu cần bản sao để tạo cấu hình độc lập, `ObjectMapper.copy()` có thể tạo mapper mới với cấu hình được sao chép. Việc copy có chi phí và nên thực hiện lúc khởi tạo, không tạo mapper mới cho mỗi request.

## 10. Một số xung đột thường gặp

### 10.1. @JsonSerialize trên class và serializer trong Module

**Triệu chứng:** module đã đăng ký serializer nhưng output vẫn theo serializer annotation.

**Nguyên nhân:** trong đường Databind thông thường, serializer được chỉ định trực tiếp bằng annotation thường được phát hiện trước custom serializer đăng ký qua module.

**Cách xử lý:** bỏ annotation nếu module phải quản lý kiểu đó, hoặc chấp nhận annotation là quy ước của kiểu. Nếu class bên ngoài, dùng Mix-in một cách có chủ đích. Viết test xác nhận serializer thực tế được gọi.

### 10.2. Annotation trên property và annotation trên class

**Triệu chứng:** một field không dùng serializer chung của kiểu.

**Nguyên nhân:** property có cấu hình cụ thể riêng, ví dụ `@JsonSerialize(using = ...)`.

**Cách xử lý:** xác định đây có phải ngoại lệ chủ ý không. Nếu không, bỏ annotation property; nếu có, ghi rõ hợp đồng cho field đó.

### 10.3. Annotation trên target và Mix-in

**Triệu chứng:** annotation Mix-in không tạo hành vi như mong muốn.

**Nguyên nhân:** Mix-in gắn vào sai class/member, mapper khác đang được dùng, annotation bị tắt, hoặc annotation có quy tắc hợp nhất riêng.

**Cách xử lý:** kiểm tra target class, member signature, `MapperFeature.USE_ANNOTATIONS`, mapper thực tế và output bằng test. Đừng giả định Mix-in tự thay thế mọi metadata ở mọi cấp.

### 10.4. Hai Module đăng ký serializer cho cùng kiểu

**Triệu chứng:** serializer khác nhau được gọi tùy cấu hình bootstrap.

**Nguyên nhân:** nhiều module cùng đăng ký handler cho một kiểu hoặc cùng tác động qua modifier.

**Cách xử lý:** chỉ định một module sở hữu kiểu đó, gom đăng ký vào một nơi hoặc dùng mapper riêng cho từng hợp đồng. Nếu dựa vào thứ tự đăng ký, ghi rõ thứ tự và khóa hành vi bằng test trên phiên bản Jackson đang dùng.

### 10.5. Cấu hình mapper khác với cấu hình của framework

**Triệu chứng:** unit test dùng `new ObjectMapper()` cho kết quả khác endpoint HTTP.

**Nguyên nhân:** Spring Boot hoặc framework đã đăng ký module, customizer, Mix-in và feature trên mapper mà HTTP converter thực sự dùng.

**Cách xử lý:** kiểm tra bean mapper và converter thực tế. Test qua đúng cấu hình ứng dụng hoặc inject mapper được cấu hình thay vì tạo mapper mới trong test.

## 11. Ví dụ tổng hợp: annotation, Mix-in và Module cùng xuất hiện

Giả sử class thuộc thư viện bên ngoài:

```java
public class ExternalCode {
    private String value;

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
```

Ứng dụng có serializer đăng ký qua module:

```java
public class CodeModuleSerializer extends StdSerializer<ExternalCode> {
    public CodeModuleSerializer() {
        super(ExternalCode.class);
    }

    @Override
    public void serialize(
            ExternalCode value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeString("module:" + value.getValue());
    }
}
```

Module:

```java
SimpleModule codeModule = new SimpleModule("code-module");
codeModule.addSerializer(ExternalCode.class, new CodeModuleSerializer());
```

Sau đó một Mix-in gắn serializer annotation khác:

```java
@JsonSerialize(using = CodeMixinSerializer.class)
abstract class ExternalCodeMixin {
}
```

Đăng ký cả hai:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(codeModule);
mapper.addMixIn(ExternalCode.class, ExternalCodeMixin.class);
```

Trong đường xử lý annotation thông thường, Mix-in làm annotation serializer hiện diện trong annotation view của `ExternalCode`; serializer được chỉ định bằng annotation thường được chọn trước serializer custom đăng ký từ module. Do đó, chỉ nhìn thấy `codeModule` đã đăng ký không đủ để kết luận `CodeModuleSerializer` sẽ chạy.

Nếu muốn module là nguồn duy nhất, hãy bỏ cấu hình Mix-in serializer hoặc dùng mapper khác không có Mix-in cạnh tranh. Nếu muốn Mix-in là nguồn duy nhất, không đăng ký serializer module cho cùng kiểu. Một kiểu chỉ nên có một chủ sở hữu rõ ràng cho wire format trong một mapper.

## 12. Cấu hình cho serialize và deserialize có thể khác nhau

Đừng giả định rằng một lựa chọn serializer sẽ tự quyết định cách deserialize ngược lại. Jackson có hai pipeline:

| Chiều | Annotation | Module API |
| --- | --- | --- |
| Java → JSON | `@JsonSerialize` | `addSerializer()` |
| JSON → Java | `@JsonDeserialize` | `addDeserializer()` |
| Map key → JSON field name | `@JsonSerialize(keyUsing = ...)` | `addKeySerializer()` |
| JSON field name → Map key | `@JsonDeserialize(keyUsing = ...)` | `addKeyDeserializer()` |

Ví dụ một kiểu được ghi thành string nhưng khi đọc lại cần parse theo format riêng. Phải đăng ký cả serializer lẫn deserializer hoặc dùng module có cả hai. Nếu chỉ có serializer, JSON output có thể hợp lệ nhưng quá trình đọc ngược vẫn theo deserializer mặc định và có thể thất bại.

## 13. Kiểm soát annotation toàn cục bằng USE_ANNOTATIONS

`MapperFeature.USE_ANNOTATIONS` điều khiển việc Jackson có sử dụng annotation introspection hay không.

```java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(MapperFeature.USE_ANNOTATIONS);
```

Khi tắt, Jackson bỏ qua annotation trên mô hình và Mix-in trong quá trình introspection. Điều này có thể hữu ích khi muốn mapper hoạt động dựa trên module và cấu hình lập trình, nhưng ảnh hưởng rất rộng:

- `@JsonProperty` có thể không còn đổi tên field.
- `@JsonIgnore` có thể không còn loại property.
- `@JsonCreator` có thể không còn định nghĩa creator.
- `@JsonSerialize` và `@JsonDeserialize` không còn chỉ định handler.
- `@JsonTypeInfo` và metadata liên quan có thể không còn được áp dụng.

Vì vậy, chỉ tắt annotation khi mapper được thiết kế để bỏ qua toàn bộ annotation. Nếu mục tiêu chỉ là thay serializer cho một kiểu, giải quyết xung đột tại kiểu/property/module tương ứng sẽ an toàn và dễ hiểu hơn.

## 14. Naming strategy, property name và Mix-in

Mapper có thể dùng naming strategy:

```java
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
```

Khi đó `firstName` thường được chuyển thành `first_name`. Một annotation explicit như `@JsonProperty("displayName")` cung cấp tên wire cụ thể cho property đó. Mix-in cũng có thể bổ sung `@JsonProperty` cho class bên ngoài.

Nếu JSON output có tên field không như mong đợi, hãy kiểm tra theo thứ tự:

1. Có `@JsonProperty` hoặc `@JsonAlias` trên target không?
2. Có Mix-in gắn annotation tên khác không?
3. Mapper có naming strategy nào?
4. Mapper có bật annotation introspection không?
5. Có custom serializer ghi tên field thủ công không?

Custom serializer tự ghi `writeFieldName()` không nhất thiết tuân theo naming strategy của bean property, vì serializer đang tự tạo cấu trúc JSON. Đây là một lý do nên dùng `provider.defaultSerializeValue()` cho các giá trị con hoặc dùng bean serializer mặc định khi không cần thay đổi cấu trúc.

## 15. Cấu hình null và inclusion từ nhiều nguồn

Một property có thể chịu ảnh hưởng từ inclusion mặc định của mapper và annotation trên class/property:

```java
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
```

```java
@JsonInclude(JsonInclude.Include.ALWAYS)
private String note;
```

Mapper cung cấp chính sách chung; annotation có thể chỉ định hành vi riêng. Ngoài `NON_NULL`, Jackson có các lựa chọn như `NON_EMPTY`, `NON_DEFAULT` và `CUSTOM`, mỗi lựa chọn có ý nghĩa riêng đối với kiểu dữ liệu và serializer.

Nếu một field vẫn xuất hiện dù mapper đặt `NON_NULL`, hãy kiểm tra annotation và custom serializer. Serializer tự ghi property không nhất thiết đi qua cùng cơ chế inclusion của bean property. Đừng giả định cấu hình inclusion toàn cục có thể loại bỏ một token mà custom serializer đã chủ động ghi.

## 16. Cách kiểm tra serializer/deserializer thực sự được chọn

Đừng chỉ kiểm tra mapper có đăng ký module hay Mix-in. Hãy tạo một test nhỏ với input/output thể hiện rõ handler được gọi:

```java
public class MarkerSerializer extends StdSerializer<Money> {
    public MarkerSerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeString("MARKER-ANNOTATION");
    }
}
```

Serializer module có marker khác:

```java
generator.writeString("MARKER-MODULE");
```

Serialize cùng một object bằng mapper production và kiểm tra marker. Với deserialize, mỗi deserializer có thể trả về một marker field hoặc ném lỗi riêng trong test. Cách này cho biết handler thực tế được chọn thay vì dựa vào suy đoán về thứ tự cấu hình.

Nên kiểm tra các trường hợp:

- Kiểu được serialize trực tiếp ở root.
- Kiểu xuất hiện trong property của DTO.
- Kiểu nằm trong collection/map.
- Property-level annotation có khác type-level không.
- Mix-in được đăng ký và khi không đăng ký.
- Module được đăng ký theo thứ tự thực tế của ứng dụng.
- Annotation bị bật/tắt.
- ObjectReader/ObjectWriter có feature override.

## 17. Quy tắc thiết kế để tránh xung đột

1. **Chọn một nơi sở hữu wire format của mỗi kiểu.** Nếu class annotation đã quy định serializer, đừng đăng ký một serializer module khác cho cùng kiểu trừ khi có chủ đích rõ ràng.
2. **Dùng property-level cho ngoại lệ cục bộ.** Không thay serializer toàn kiểu chỉ để đổi một field.
3. **Dùng Mix-in cho class không thể sửa.** Xem Mix-in là lớp annotation overlay, không phải nơi đăng ký handler độc lập.
4. **Dùng Module cho cấu hình tập trung.** Gom serializer, deserializer và subtype liên quan vào module có tên rõ ràng.
5. **Quản lý thứ tự module.** Ghi rõ thứ tự bootstrap, nhưng không dựa vào một quy tắc “last wins” chung cho mọi extension point.
6. **Giữ mapper ổn định sau bootstrap.** Tạo reader/writer cho khác biệt theo lần gọi; dùng mapper riêng nếu cần registry khác.
7. **Test trên mapper production.** Mapper tự tạo trong unit test có thể thiếu module, Mix-in hoặc customizer của framework.
8. **Không tắt annotation toàn cục vì một xung đột đơn lẻ.** `USE_ANNOTATIONS` ảnh hưởng nhiều metadata quan trọng.
9. **Tách serializer và deserializer.** Hai chiều có cấu hình và handler riêng.
10. **Ghi nhận phiên bản Jackson.** Quy tắc chi tiết của factory, module và modifier cần được xác nhận với dependency thực tế.

## 18. Bảng xử lý nhanh theo triệu chứng

| Triệu chứng | Nguồn cần kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Module serializer không chạy | `@JsonSerialize` trên class/property hoặc Mix-in | Xác định serializer annotation có đang được chọn trước module không |
| Serializer chung bị một field thay thế | `@JsonSerialize` ở property-level | Giữ nếu là ngoại lệ có chủ đích; nếu không thì bỏ annotation cục bộ |
| Mix-in không có tác dụng | `USE_ANNOTATIONS`, target mapping, mapper thực tế | Kiểm tra mapper, class/member signature và annotation introspection |
| Module A và B ghi khác nhau | Cùng đăng ký handler hoặc modifier | Chỉ định một module sở hữu kiểu; khóa thứ tự bằng test |
| Tên JSON không đúng | `@JsonProperty`, Mix-in, naming strategy, custom serializer | Xác định tên được tạo từ introspection hay viết thủ công |
| Null vẫn xuất hiện | Property inclusion, class annotation, custom serializer | Kiểm tra inclusion cụ thể và đường ghi property |
| Test khác endpoint | Mapper production có module/customizer khác | Inject mapper thật hoặc test qua application context |
| Đọc được nhưng ghi không được (hoặc ngược lại) | Serializer/deserializer được đăng ký không đối xứng | Cấu hình và kiểm tra riêng hai chiều |

## 19. Ghi nhớ

- Annotation trên class/property mô tả metadata của mô hình; property-level thường là chỉ dẫn cụ thể cho một property.
- Mix-in bổ sung hoặc ghi đè annotation metadata trên target mà không sửa class gốc; nó không phải serializer riêng.
- `Module` đăng ký serializer, deserializer, key handler, subtype, abstract mapping và modifier.
- Trong đường Databind thông thường, serializer/deserializer được chỉ định trực tiếp bằng annotation thường được tìm trước custom handler đăng ký qua module.
- Module đăng ký sau thường thay mapping trùng trong một số registry đơn giản, nhưng không có quy tắc “module cuối luôn thắng” cho mọi extension point.
- Modifier có pipeline riêng; không nên xem nó là cách override universal cho handler annotation.
- Mapper-wide features đặt chính sách chung; annotation có thể cung cấp hành vi cụ thể hơn cho kiểu/property.
- `ObjectReader` và `ObjectWriter` cho phép override một số feature theo lần gọi mà không mutate mapper dùng chung.
- `MapperFeature.USE_ANNOTATIONS` tắt annotation introspection rộng, bao gồm cả Mix-in; chỉ dùng khi mapper được thiết kế để bỏ qua annotation.
- Đăng ký module/Mix-in trước khi mapper được chia sẻ; dùng mapper riêng nếu cần registry khác.
- Kiểm tra hành vi bằng đúng mapper production và test thể hiện rõ serializer/deserializer thực tế được chọn.

Khi nhiều nguồn cấu hình cùng tác động một kiểu, hãy xác định nguồn nào chịu trách nhiệm cho wire format đó. Dùng annotation cho quy ước gần mô hình, Mix-in cho metadata của class không thể sửa, Module cho đăng ký tập trung và reader/writer cho khác biệt theo lần gọi. Tránh khai báo cạnh tranh và xác nhận kết quả trên đúng phiên bản Jackson sẽ giúp cấu hình dễ dự đoán, dễ kiểm thử và ít bị thay đổi ngoài ý muốn.
