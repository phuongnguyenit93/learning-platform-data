# Đánh giá phần mở rộng mức thấp như bộ sửa serializer và deserializer

Jackson cung cấp nhiều mức tùy biến khi chuyển đổi giữa Java object và JSON. Ở mức đơn giản, có thể dùng annotation trên class/property, converter hoặc một custom serializer/deserializer cho kiểu cụ thể. Ở mức rộng hơn, **serializer modifier** và **deserializer modifier** cho phép can thiệp vào quá trình Jackson xây dựng bộ chuyển đổi mặc định: thay đổi danh sách property, điều chỉnh builder hoặc bọc serializer/deserializer đã được tạo.

Các extension point mức thấp này hữu ích khi một quy tắc cần áp dụng có hệ thống cho nhiều model, hoặc khi cần thay đổi cách databinding mặc định được lắp ráp mà annotation đơn lẻ không diễn đạt đủ. Tuy nhiên, chúng cũng làm cấu hình phụ thuộc sâu hơn vào pipeline nội bộ của databind, tăng phạm vi ảnh hưởng và khó dự đoán khi nhiều module cùng can thiệp.

Bài này đánh giá vai trò của `BeanSerializerModifier` và `BeanDeserializerModifier`, cách đăng ký qua module, so sánh với mix-in và custom serializer/deserializer, cùng các tiêu chí để chọn mức mở rộng vừa đủ.

## 1. Các tầng mở rộng của Jackson

Có thể hình dung Jackson có nhiều tầng từ khai báo đơn giản đến can thiệp thấp:

```text
JSON <-> Java object
       |
       +-- Annotation trên class/property
       |     @JsonProperty, @JsonIgnore, @JsonFormat, @JsonCreator
       |
       +-- Mix-in
       |     Gắn annotation cho class không thể sửa
       |
       +-- Converter / custom serializer / deserializer
       |     Chuyển đổi một kiểu hoặc một property cụ thể
       |
       +-- Module và provider
       |     Đăng ký serializer, deserializer, key handler, subtype...
       |
       +-- BeanSerializerModifier / BeanDeserializerModifier
             Can thiệp vào quá trình dựng bộ chuyển đổi mặc định
```

Các tầng không loại trừ nhau. Một module có thể đăng ký serializer cho kiểu đặc biệt và đồng thời cung cấp modifier để điều chỉnh bean serializer mặc định cho một nhóm model.

Điểm khác biệt quan trọng là **custom serializer/deserializer** thường thay thế cách xử lý một kiểu hoặc property bằng logic do ứng dụng viết. Trong khi đó, **modifier** nhận bộ chuyển đổi mặc định mà Jackson đã xây dựng rồi có thể điều chỉnh hoặc bọc nó.

## 2. Serializer modifier và deserializer modifier là gì?

Jackson 2.x cung cấp hai extension point chính trong package databind:

- `com.fasterxml.jackson.databind.ser.BeanSerializerModifier`
- `com.fasterxml.jackson.databind.deser.BeanDeserializerModifier`

Chúng được thiết kế để thay đổi quá trình tạo serializer/deserializer cho bean.

### 2.1. BeanSerializerModifier

`BeanSerializerModifier` cho phép can thiệp vào các giai đoạn Jackson xây dựng serializer cho bean. Những hook thường gặp:

| Hook | Vai trò |
|---|---|
| `changeProperties(...)` | Thêm, bỏ hoặc thay đổi danh sách property writer trước khi tạo serializer |
| `orderProperties(...)` | Thay đổi thứ tự property |
| `updateBuilder(...)` | Điều chỉnh `BeanSerializerBuilder` sau khi các property writer đã được chuẩn bị |
| `modifySerializer(...)` | Thay thế hoặc bọc bean serializer cuối cùng |
| `modifyArraySerializer(...)` | Điều chỉnh serializer cho array |
| `modifyCollectionSerializer(...)` | Điều chỉnh serializer cho collection |
| `modifyCollectionLikeSerializer(...)` | Điều chỉnh serializer cho collection-like type |
| `modifyMapSerializer(...)` | Điều chỉnh serializer cho map |
| `modifyMapLikeSerializer(...)` | Điều chỉnh serializer cho map-like type |
| `modifyEnumSerializer(...)` | Điều chỉnh serializer cho enum |
| `modifyKeySerializer(...)` | Điều chỉnh serializer cho map key |

Không phải mọi hook đều áp dụng cho mọi kiểu Java. Ví dụ, `changeProperties` và `modifySerializer` tập trung vào bean serializer; collection, map, enum và key serializer có hook riêng.

### 2.2. BeanDeserializerModifier

`BeanDeserializerModifier` cung cấp các hook tương ứng ở chiều đọc:

| Hook | Vai trò |
|---|---|
| `updateProperties(...)` | Điều chỉnh danh sách property definition trước khi dựng bean deserializer |
| `updateBuilder(...)` | Thay đổi `BeanDeserializerBuilder`, ví dụ property, ignorable property hoặc cấu hình builder |
| `modifyDeserializer(...)` | Thay thế hoặc bọc bean deserializer mặc định |
| `modifyEnumDeserializer(...)` | Điều chỉnh enum deserializer |
| `modifyReferenceDeserializer(...)` | Điều chỉnh deserializer cho reference type |
| `modifyArrayDeserializer(...)` | Điều chỉnh array deserializer |
| `modifyCollectionDeserializer(...)` | Điều chỉnh collection deserializer |
| `modifyCollectionLikeDeserializer(...)` | Điều chỉnh collection-like deserializer |
| `modifyMapDeserializer(...)` | Điều chỉnh map deserializer |
| `modifyMapLikeDeserializer(...)` | Điều chỉnh map-like deserializer |
| `modifyKeyDeserializer(...)` | Điều chỉnh key deserializer của map |

Các hook cụ thể và chữ ký có thể khác theo major version. Khi triển khai, hãy đối chiếu Javadoc đúng phiên bản Jackson của dự án.

## 3. Modifier tham gia vào pipeline như thế nào?

Ở chiều serialize, Jackson phân tích kiểu bean, phát hiện property, tạo `BeanPropertyWriter`, dựng `BeanSerializerBuilder`, rồi tạo serializer. Modifier có thể can thiệp vào các bước này.

Ở chiều deserialize, Jackson phân tích property definition, tạo builder và settable property, dựng bean deserializer rồi dùng nó để đọc object. Modifier có thể thay đổi property model hoặc serializer cuối cùng.

```text
Serialization
  Java type
     |
     v
  Introspect bean properties
     |
     v
  BeanSerializerModifier.changeProperties()
     |
     v
  BeanSerializerModifier.orderProperties()
     |
     v
  BeanSerializerModifier.updateBuilder()
     |
     v
  Create default bean serializer
     |
     v
  BeanSerializerModifier.modifySerializer()
     |
     v
  Serialize JSON


Deserialization
  Java type
     |
     v
  Introspect property definitions
     |
     v
  BeanDeserializerModifier.updateProperties()
     |
     v
  Build settable properties
     |
     v
  BeanDeserializerModifier.updateBuilder()
     |
     v
  Create default bean deserializer
     |
     v
  BeanDeserializerModifier.modifyDeserializer()
     |
     v
  Deserialize Java object
```

Sơ đồ là mô hình khái quát cho bean pipeline. Collection, map, enum, key và reference type có các đường tạo serializer/deserializer riêng. Vì vậy, nếu cần can thiệp vào một loại container, hãy chọn đúng hook chuyên biệt thay vì giả định `modifySerializer()` hoặc `modifyDeserializer()` sẽ bắt mọi kiểu.

## 4. Đăng ký modifier thông qua SimpleModule

Trong Jackson 2.x, `SimpleModule` là cách thuận tiện để đăng ký serializer, deserializer và modifier:

```java
SimpleModule module = new SimpleModule("api-model-policy");

module.setSerializerModifier(new PublicApiSerializerModifier());
module.setDeserializerModifier(new ImportModelDeserializerModifier());

ObjectMapper mapper = JsonMapper.builder()
        .addModule(module)
        .build();
```

Sau khi module được thêm, mapper sử dụng modifier khi tạo serializer/deserializer phù hợp với phạm vi hook của chúng.

Một module có thể đăng ký nhiều loại extension:

```java
SimpleModule module = new SimpleModule("custom-json");

module.addSerializer(Money.class, new MoneySerializer());
module.addDeserializer(Money.class, new MoneyDeserializer());

module.setSerializerModifier(new PublicApiSerializerModifier());
module.setDeserializerModifier(new ImportModelDeserializerModifier());
```

Điều này giúp gom các quy tắc JSON của một integration boundary vào một đơn vị cấu hình. Tuy nhiên, không nên tạo một module khổng lồ chứa mọi chính sách không liên quan. Tách module theo domain hoặc theo hợp đồng tích hợp giúp dễ hiểu phạm vi ảnh hưởng hơn.

### 4.1. Cấu hình mapper trước khi dùng

Hãy đăng ký module và hoàn tất cấu hình trước khi chia sẻ mapper cho nhiều thread:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(module)
        .build();
```

Sau khi cấu hình xong, có thể tái sử dụng mapper. Không nên bật/tắt modifier hoặc đăng ký module theo từng request trên mapper đang được nhiều luồng dùng chung. Nếu cần các contract khác nhau, tạo mapper/reader/writer đã cấu hình riêng cho từng boundary.

## 5. Ví dụ BeanSerializerModifier: bỏ property nội bộ khỏi JSON public

Một ứng dụng có nhiều DTO public nhưng muốn loại bỏ các property nội bộ theo một quy ước chung. Nếu từng class đều phải lặp `@JsonIgnore`, việc quản lý có thể khó khi model đến từ thư viện hoặc được chia sẻ với nhiều boundary.

Có thể tạo marker annotation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface PublicApiModel {
}
```

Modifier:

```java
import com.fasterxml.jackson.databind.BeanDescription;
import com.fasterxml.jackson.databind.SerializationConfig;
import com.fasterxml.jackson.databind.ser.BeanPropertyWriter;
import com.fasterxml.jackson.databind.ser.BeanSerializerModifier;

import java.util.ArrayList;
import java.util.List;

public final class PublicApiSerializerModifier
        extends BeanSerializerModifier {

    @Override
    public List<BeanPropertyWriter> changeProperties(
            SerializationConfig config,
            BeanDescription beanDesc,
            List<BeanPropertyWriter> beanProperties
    ) {
        if (!beanDesc.getBeanClass().isAnnotationPresent(PublicApiModel.class)) {
            return beanProperties;
        }

        List<BeanPropertyWriter> result =
                new ArrayList<>(beanProperties);

        result.removeIf(writer ->
                writer.getName().startsWith("internal")
        );

        return result;
    }
}
```

DTO:

```java
@PublicApiModel
public class UserResponse {
    private String id;
    private String name;
    private String internalRiskScore;
    private String internalNote;

    // Getter và setter
}
```

Khi serialize, modifier loại bỏ các property có tên bắt đầu bằng `internal` khỏi danh sách writer. JSON chỉ còn các field public.

Ví dụ:

```json
{
  "id": "U-100",
  "name": "An"
}
```

Ví dụ minh họa chính sách serialization theo marker type. Trong ứng dụng thực tế, nên dùng allowlist property hoặc annotation chuyên biệt nếu quy tắc bảo mật quan trọng. Quy tắc dựa trên prefix tên field dễ bị phá vỡ khi đổi tên property và không thay thế kiểm soát dữ liệu nhạy cảm ở API boundary.

### 5.1. Modifier serialization không thay đổi deserialization

Bỏ property trong `BeanSerializerModifier` chỉ ảnh hưởng chiều ghi. Nó không tự động ngăn consumer gửi property đó khi deserialize.

Nếu cần kiểm soát cả hai chiều, phải định nghĩa chính sách riêng cho deserializer, hoặc dùng annotation/DTO phù hợp. Không giả định một modifier tự động đồng bộ serialize và deserialize.

## 6. Ví dụ BeanDeserializerModifier: điều chỉnh property model

Ở chiều đọc, modifier có thể điều chỉnh danh sách property trước khi builder tạo bean deserializer. Ví dụ, một DTO import cần bỏ qua một property legacy đã bị ngừng hỗ trợ.

```java
public final class ImportModelDeserializerModifier
        extends BeanDeserializerModifier {

    @Override
    public BeanDeserializerBuilder updateBuilder(
            DeserializationConfig config,
            BeanDescription beanDesc,
            BeanDeserializerBuilder builder
    ) {
        if (LegacyImportRequest.class.isAssignableFrom(
                beanDesc.getBeanClass()
        )) {
            builder.addIgnorable("obsoleteFlag");
        }

        return builder;
    }
}
```

Với cấu hình này, property `obsoleteFlag` được đánh dấu ignorable trong bean deserializer cho loại model mục tiêu. Đây là cách can thiệp sâu vào builder, vì vậy cần kiểm tra chữ ký API và hành vi trên đúng Jackson version.

Một cách khác là dùng `updateProperties(...)` để lọc hoặc thay đổi `BeanPropertyDefinition` trước khi property writer/reader được tạo. Hook này tác động vào metadata property, không phải giá trị runtime của từng object.

### 6.1. Khi nào không nên dùng modifier cho một property đơn lẻ?

Nếu chỉ một field cần bỏ qua hoặc đổi tên, annotation thường rõ hơn:

```java
@JsonIgnore
private String obsoleteFlag;
```

Hoặc:

```java
@JsonProperty("legacy_name")
private String currentName;
```

Dùng modifier khi chính sách cần áp dụng cho nhiều model, khi class không thể sửa, hoặc khi cần thao tác với metadata/builder mà annotation không biểu diễn được.

## 7. Bọc default serializer bằng modifySerializer

Hook `modifySerializer()` nhận serializer bean mà Jackson đã xây dựng. Có thể trả lại serializer gốc, một serializer thay thế hoặc một wrapper delegate.

Ví dụ ý tưởng: bọc serializer để ghi metric khi một loại model được serialize:

```java
@Override
public JsonSerializer<?> modifySerializer(
        SerializationConfig config,
        BeanDescription beanDesc,
        JsonSerializer<?> serializer
) {
    if (!AuditedResponse.class.isAssignableFrom(beanDesc.getBeanClass())) {
        return serializer;
    }

    return new AuditingSerializer(serializer);
}
```

Wrapper cần delegate thao tác ghi cho serializer gốc:

```java
public final class AuditingSerializer extends JsonSerializer<Object> {
    private final JsonSerializer<Object> delegate;

    @SuppressWarnings("unchecked")
    public AuditingSerializer(JsonSerializer<?> delegate) {
        this.delegate = (JsonSerializer<Object>) delegate;
    }

    @Override
    public void serialize(
            Object value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        recordSerialization(value.getClass());
        delegate.serialize(value, generator, provider);
    }
}
```

Đây là skeleton minh họa. Wrapper production cần cân nhắc và delegate các capability khác của serializer gốc như `serializeWithType()`, `isEmpty()`, `isUnwrappingSerializer()`, `getDelegatee()`, `replaceDelegatee()` và contextualization nếu serializer gốc có triển khai `ContextualSerializer`. Nếu bỏ qua các hành vi này, wrapper có thể làm hỏng polymorphic type handling, property-level configuration hoặc serializer được contextualize theo property.

Nếu mục tiêu chỉ là metric ở tầng HTTP, filter/interceptor của framework có thể phù hợp hơn vì nó quan sát request/response ở đúng boundary. Không nên dùng serializer modifier cho logging chung nếu có thể đo ở tầng cao hơn mà không ảnh hưởng pipeline JSON.

## 8. Bọc default deserializer bằng modifyDeserializer

Tương tự, `modifyDeserializer()` nhận bean deserializer đã được tạo. Có thể dùng nó để thêm hành vi trước hoặc sau khi delegate deserialize.

Ví dụ về mặt thiết kế:

```java
@Override
public JsonDeserializer<?> modifyDeserializer(
        DeserializationConfig config,
        BeanDescription beanDesc,
        JsonDeserializer<?> deserializer
) {
    if (!AuditedInput.class.isAssignableFrom(beanDesc.getBeanClass())) {
        return deserializer;
    }

    return new AuditingDeserializer(deserializer);
}
```

Một wrapper như `AuditingDeserializer` cần gọi delegate để thực hiện binding mặc định, sau đó có thể ghi metric hoặc kiểm tra hậu điều kiện nhẹ.

Không nên triển khai wrapper chỉ bằng cách override mỗi `deserialize()` rồi bỏ qua các phương thức khác. Deserializer có thể hỗ trợ contextualization, resolution, update-in-place, null value, empty value và polymorphic type. Nếu wrapper không chuyển tiếp đúng những hành vi đó, nó có thể làm thay đổi ngữ nghĩa databinding.

Khi cần một deserializer hoàn toàn mới cho kiểu cụ thể, đăng ký `JsonDeserializer<T>` trực tiếp thường đơn giản và dễ kiểm soát hơn. Modifier phù hợp khi cần can thiệp có chọn lọc vào deserializer mặc định đã được tạo.

## 9. Modifier khác gì custom serializer/deserializer?

| Tiêu chí | Custom serializer/deserializer | Bean modifier |
|---|---|---|
| Mục tiêu | Tự định nghĩa cách đọc/ghi một kiểu hoặc property | Điều chỉnh hoặc bọc bộ chuyển đổi mặc định |
| Phạm vi | Kiểu/property đã đăng ký | Có thể chọn nhiều bean theo metadata/type |
| Độ phức tạp | Tự xử lý token hoặc output cho kiểu đích | Phải hiểu lifecycle và hook của serializer/deserializer factory |
| Tái sử dụng default behavior | Thường không, trừ khi delegate rõ ràng | Đây là một mục tiêu phổ biến |
| Use case | Value object có wire format riêng | Chính sách cross-cutting trên nhiều bean |
| Rủi ro | Logic parse/format sai | Thay đổi pipeline rộng, tương tác với module khác |
| Khả năng đọc code | Dễ hiểu khi logic tập trung một kiểu | Khó truy vết nếu nhiều modifier cùng can thiệp |

Ví dụ:

- `MoneyDeserializer` đọc string hoặc object thành `Money`: custom deserializer.
- Một modifier bọc mọi bean serializer của nhóm response để áp dụng chính sách chung: modifier.
- Một serializer ghi `Money` thành chuỗi ISO riêng: custom serializer.
- Một modifier loại bỏ property nội bộ trên mọi DTO có marker annotation: modifier.

## 10. Modifier khác gì mix-in?

Mix-in là cơ chế gắn annotation vào class mà ứng dụng không thể hoặc không muốn sửa source. Ví dụ, một class bên thứ ba có field cần bỏ qua:

```java
public abstract class ExternalUserMixIn {
    @JsonIgnore
    abstract String getInternalToken();
}
```

Đăng ký:

```java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.addMixIn(
        ExternalUser.class,
        ExternalUserMixIn.class
);
```

Jackson đọc annotation trên mix-in như metadata bổ sung cho target class khi introspect.

| Tiêu chí | Mix-in | Serializer/deserializer modifier |
|---|---|---|
| Cơ chế | Bổ sung annotation metadata | Can thiệp vào quá trình tạo serializer/deserializer |
| Phù hợp | Đổi tên, ignore, creator, format, type info | Sửa property writer/definition, builder hoặc bọc delegate |
| Cần code xử lý token? | Không | Có thể cần |
| Phạm vi | Target class được đăng ký trên mapper | Có thể áp dụng theo nhiều bean/type |
| Tác động đến class gốc | Không sửa source | Không sửa source, nhưng thay pipeline runtime |
| Độ phức tạp | Thường thấp | Thường cao hơn |
| Tùy biến logic động | Hạn chế theo annotation | Linh hoạt hơn |

Nếu chỉ cần thêm `@JsonIgnore`, `@JsonProperty`, `@JsonCreator` hoặc `@JsonFormat` cho class bên thứ ba, mix-in thường là lựa chọn phù hợp. Modifier dành cho trường hợp cần thay đổi cấu trúc hoặc hành vi của serializer/deserializer ở mức thấp.

## 11. Modifier và Module: hai khái niệm liên quan nhưng không giống nhau

`Module` là đơn vị đăng ký các extension với Jackson. Modifier là một trong những extension có thể được module đăng ký.

Với `SimpleModule`:

```java
SimpleModule module = new SimpleModule("integration-json");

module.setSerializerModifier(new IntegrationSerializerModifier());
module.setDeserializerModifier(new IntegrationDeserializerModifier());

mapper.registerModule(module);
```

Với module tùy chỉnh, có thể override `setupModule()` và đăng ký modifier qua `SetupContext`:

```java
public final class IntegrationModule extends Module {
    @Override
    public String getModuleName() {
        return "integration-json";
    }

    @Override
    public Version version() {
        return Version.unknownVersion();
    }

    @Override
    public void setupModule(SetupContext context) {
        context.addBeanSerializerModifier(
                new IntegrationSerializerModifier()
        );

        context.addBeanDeserializerModifier(
                new IntegrationDeserializerModifier()
        );
    }
}
```

Module tùy chỉnh phù hợp khi cần gom nhiều extension, có cấu hình riêng hoặc cần đăng ký theo composition root. Nếu chỉ có một modifier nhỏ, `SimpleModule` thường ít code hơn.

### 11.1. Module order và nhiều modifier

Một mapper có thể nhận nhiều module. Nếu nhiều module cùng thêm modifier, thứ tự đăng ký và thứ tự áp dụng trong factory pipeline có thể ảnh hưởng kết quả. Ví dụ modifier đầu tiên đổi property name, modifier sau lọc theo tên; thứ tự có thể làm thay đổi property nào bị loại.

Không nên dựa vào thứ tự tình cờ. Hãy:

- Gom các quy tắc liên quan vào cùng một module khi có thể.
- Tránh hai modifier cùng sửa một property theo cách xung đột.
- Đăng ký module theo thứ tự rõ ràng tại nơi tạo mapper.
- Viết test integration kiểm tra output/input cuối cùng của mapper đã cấu hình đầy đủ.
- Ghi rõ modifier nào sở hữu một chính sách để tránh trùng trách nhiệm.

## 12. Khi nào low-level modifier thực sự đáng dùng?

Modifier thường đáng cân nhắc khi có một trong các tình huống:

### 12.1. Chính sách xuyên suốt nhiều bean

Ví dụ một nhóm response model có marker annotation và mọi property nội bộ phải được loại bỏ khi serialize. Modifier có thể áp dụng một quy tắc ở một nơi thay vì lặp logic trong từng DTO.

### 12.2. Class không thể sửa và mix-in không đủ

Nếu cần thay đổi danh sách property writer, sắp xếp property theo metadata động hoặc bọc serializer mặc định, annotation mix-in có thể không đủ. Modifier cung cấp điểm can thiệp sâu hơn.

### 12.3. Cần giữ phần lớn databinding mặc định

Một modifier có thể delegate về serializer/deserializer gốc và chỉ thêm một hành vi hẹp. Điều này có thể tốt hơn viết lại toàn bộ token handling của một bean phức tạp.

### 12.4. Framework hoặc thư viện đang xây dựng chính sách JSON

Một thư viện dùng Jackson có thể cung cấp module để người dùng đăng ký một lần và áp dụng chính sách lên các kiểu được đánh dấu. Đây là trường hợp modifier phát huy giá trị vì cần tích hợp sâu với factory pipeline.

### 12.5. Cần điều chỉnh bean metadata trước khi tạo handler

Một số quy tắc cần thay đổi property model trước khi serializer/deserializer được tạo. Đây là lý do dùng `changeProperties`, `updateProperties` hoặc builder hook thay vì post-process object sau khi đọc.

## 13. Khi nào modifier là lựa chọn không phù hợp?

Không nên dùng modifier chỉ vì nó có nhiều hook hoặc có vẻ mạnh hơn annotation.

| Nhu cầu | Lựa chọn thường đơn giản hơn |
|---|---|
| Bỏ một field | `@JsonIgnore` hoặc mix-in |
| Đổi tên property | `@JsonProperty`, naming strategy hoặc mix-in |
| Đọc format scalar riêng | Converter hoặc custom deserializer |
| Ghi một value object thành scalar | Custom serializer |
| Null policy | `@JsonSetter`, `Nulls` |
| Chọn subtype | `@JsonTypeInfo`, subtype registry |
| Thay đổi response theo user/request | DTO mapping ở service/controller |
| Kiểm tra nghiệp vụ | Bean Validation/domain service |
| Ghi log request/response | Framework filter/interceptor hoặc observability layer |

Một dấu hiệu modifier đang bị dùng quá mức là nó cần kiểm tra nhiều tên class cụ thể, nhiều property name đặc biệt và nhiều cờ runtime để quyết định hành vi. Khi đó, có thể nên tách DTO hoặc module theo contract thay vì xây một bộ quy tắc toàn cục khó theo dõi.

## 14. Phạm vi ảnh hưởng và khả năng bảo trì

Modifier được đăng ký ở mapper/module và có thể tác động tới mọi type thỏa điều kiện hook. Điều này làm thay đổi hành vi của những class mà người viết modifier không trực tiếp sở hữu.

Các rủi ro thường gặp:

- Một DTO mới vô tình khớp điều kiện và bị thay đổi output.
- Một property rename khiến chính sách lọc không còn áp dụng.
- Module khác thêm serializer/deserializer riêng, khiến modifier không được gọi theo cách dự kiến.
- Wrapper không delegate đủ capability của serializer/deserializer gốc.
- Nâng Jackson version làm thay đổi API SPI hoặc thứ tự pipeline.
- Cấu hình toàn cục ảnh hưởng API khác dùng cùng mapper.

Để giảm rủi ro:

1. Giới hạn theo marker annotation, base class hoặc package có chủ đích.
2. Tránh điều kiện dựa vào substring tên class nếu có thể dùng metadata rõ ràng.
3. Không thay đổi global mapper theo request.
4. Viết test cho mapper hoàn chỉnh sau khi tất cả module đã đăng ký.
5. Tài liệu hóa chính sách và các type chịu ảnh hưởng.
6. Kiểm tra release note/Javadoc khi nâng major version.
7. Ưu tiên extension API công khai thay vì truy cập field hoặc class nội bộ của databind.

## 15. Thread safety và vòng đời modifier

Jackson thường cache serializer/deserializer đã tạo để tái sử dụng. Vì vậy, modifier và các handler mà nó tạo nên được thiết kế theo hướng stateless hoặc chỉ chứa cấu hình bất biến.

Không nên:

- Lưu user hiện tại hoặc request context vào field của modifier.
- Thay đổi danh sách property dùng chung sau khi serializer đã được cache.
- Giữ parser/generator của một request để dùng ở request khác.
- Tạo mapper mới bên trong mỗi hook.
- Đăng ký lại module liên tục trên mapper đang được chia sẻ.

Nếu chính sách cần dữ liệu theo request, hãy dùng API contextual/provider phù hợp hoặc chuyển quyết định đó lên tầng application. Serializer/deserializer là thành phần hạ tầng có thể được dùng đồng thời từ nhiều thread.

## 16. Modifier và các kiểu không phải bean

Tên `BeanSerializerModifier`/ `BeanDeserializerModifier` có chữ “Bean” vì chúng chủ yếu can thiệp vào pipeline bean. Jackson có hook riêng cho array, collection, map, enum, reference type và map key.

Ví dụ, nếu cần thay cách serialize mọi `Map`, hãy xem `modifyMapSerializer()`; nếu cần thay cách đọc map key, xem `modifyKeyDeserializer()`. Không nên cố xử lý map như một POJO bằng `changeProperties()`.

Một số kiểu có serializer/deserializer được đăng ký trực tiếp bởi module hoặc xử lý đặc biệt. Modifier bean không phải bộ lọc universal bắt mọi token và mọi kiểu. Trước khi viết, xác định kiểu đích thực tế, serializer/deserializer factory đang chọn và hook tương ứng.

## 17. Ví dụ tổ chức module cho một API boundary

Có thể gom chính sách public API vào một module:

```java
public final class PublicApiJacksonModule extends SimpleModule {
    public PublicApiJacksonModule() {
        super("public-api-json");

        setSerializerModifier(new PublicApiSerializerModifier());
        setDeserializerModifier(new PublicApiDeserializerModifier());

        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
```

Tạo mapper:

```java
ObjectMapper publicApiMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .addModule(new PublicApiJacksonModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();
```

Mapper này đại diện cho một boundary cụ thể. Nếu persistence layer hoặc message consumer có contract khác, có thể dùng mapper khác với module tương ứng.

Không nhất thiết phải tạo một mapper cho mọi endpoint. Chỉ tách khi chính sách JSON thực sự khác nhau và dùng chung mapper sẽ gây xung đột.

## 18. Kiểm thử modifier

Vì modifier tác động vào quá trình tạo handler, test nên dùng mapper đã đăng ký module như ứng dụng thật.

### 18.1. Test serializer modifier

```java
@Test
void shouldRemoveInternalPropertiesFromPublicModel() throws Exception {
    SimpleModule module = new SimpleModule();
    module.setSerializerModifier(new PublicApiSerializerModifier());

    ObjectMapper mapper = JsonMapper.builder()
            .addModule(module)
            .build();

    UserResponse response = new UserResponse();
    response.setId("U-100");
    response.setName("An");
    response.setInternalNote("private");

    JsonNode json = mapper.readTree(
            mapper.writeValueAsString(response)
    );

    assertEquals("U-100", json.path("id").asText());
    assertFalse(json.has("internalNote"));
}
```

Test này xác nhận output wire format. Nên thêm test cho class không có marker annotation để bảo đảm modifier không tác động ngoài phạm vi.

### 18.2. Test deserializer modifier

Nếu modifier đánh dấu property là ignorable hoặc thay đổi builder, test cả trường hợp property xuất hiện và không xuất hiện:

```java
@Test
void shouldIgnoreLegacyPropertyForImportRequest() throws Exception {
    SimpleModule module = new SimpleModule();
    module.setDeserializerModifier(
            new ImportModelDeserializerModifier()
    );

    ObjectMapper mapper = JsonMapper.builder()
            .addModule(module)
            .build();

    LegacyImportRequest request = mapper.readValue(
            """
            {
              "name": "batch-1",
              "obsoleteFlag": true
            }
            """,
            LegacyImportRequest.class
    );

    assertEquals("batch-1", request.getName());
}
```

Test này giả định builder modifier đã đánh dấu `obsoleteFlag` là ignorable và class có property `name`. Nếu chính sách unknown-property của mapper khác nhau, hãy xác nhận hành vi theo cấu hình thực tế.

### 18.3. Test tương tác module

Khi nhiều module cùng được đăng ký, test mapper cuối cùng với:

- Thứ tự module như production.
- Serializer/deserializer custom đã đăng ký trực tiếp.
- Mix-in được thêm vào mapper.
- Property-level annotation.
- Root/generic type nếu có.
- Các class nằm ngoài phạm vi modifier.

Đây là test contract, không chỉ test từng modifier độc lập.

## 19. Tiêu chí lựa chọn mức mở rộng

Có thể dùng bảng sau khi quyết định giải pháp:

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Chỉ cần đổi metadata annotation? | Dùng annotation hoặc mix-in |
| Chỉ một kiểu cần wire format riêng? | Dùng custom serializer/deserializer |
| Chỉ chuyển đổi một kiểu nguồn sang một kiểu đích? | Cân nhắc converter |
| Cần áp dụng quy tắc cho nhiều bean mặc định? | Cân nhắc modifier |
| Cần thay property writer/definition hoặc builder? | Modifier là extension point phù hợp |
| Cần xử lý mọi collection/map/enum? | Chọn hook chuyên biệt cho loại đó |
| Cần thay đổi theo request/user? | Đưa logic lên application layer hoặc contextual API có kiểm soát |
| Logic phụ thuộc nhiều chi tiết private của databind? | Cân nhắc thiết kế lại vì chi phí nâng cấp cao |

Một modifier tốt thường có phạm vi hẹp, điều kiện áp dụng rõ, giữ nguyên hành vi mặc định ngoài phần thay đổi và có test cho cả trường hợp được áp dụng lẫn không được áp dụng.

## 20. Các lỗi thường gặp

**Dùng modifier để đổi tên một property đơn lẻ.** Annotation hoặc mix-in dễ đọc hơn.

**Giả định BeanSerializerModifier áp dụng cho mọi kiểu.** Array, collection, map, enum và key có hook riêng; custom serializer đã đăng ký có thể đi theo đường khác.

**Bọc serializer nhưng không delegate serializeWithType.** Polymorphic type metadata có thể bị mất hoặc ghi sai.

**Bọc deserializer nhưng bỏ qua contextualization/null/update methods.** Property annotation, null handling hoặc update-in-place có thể thay đổi.

**Sửa trực tiếp danh sách metadata dùng chung.** Hãy hiểu lifecycle và tránh giữ mutable state sau khi handler được cache.

**Dùng modifier global cho một API duy nhất.** Mapper dùng chung có thể làm thay đổi output của boundary khác. Dùng mapper/module có phạm vi rõ.

**Đăng ký nhiều modifier cùng sửa một property.** Kết quả phụ thuộc thứ tự và khó dự đoán. Gom chính sách hoặc định nghĩa thứ tự rõ ràng.

**Lưu request-specific state trong modifier.** Modifier có thể được dùng đồng thời. Chỉ giữ cấu hình bất biến.

**Dùng low-level hook thay cho validation.** Modifier không phải nơi phù hợp để chứa toàn bộ quy tắc nghiệp vụ.

**Không test mapper sau khi đăng ký đủ module.** Test một modifier riêng không phát hiện xung đột khi chạy cùng mix-in hoặc custom serializer khác.

## 21. Quy trình triển khai modifier có kiểm soát

1. **Mô tả hành vi cần thay đổi:** property nào, chiều đọc hay ghi, nhóm type nào?
2. **Kiểm tra giải pháp cấp cao:** annotation, mix-in, converter hoặc serializer/deserializer riêng đã đủ chưa?
3. **Xác định hook phù hợp:** property list, builder, bean serializer/deserializer hay collection/map/enum hook?
4. **Giới hạn phạm vi:** marker annotation, base type hoặc điều kiện metadata rõ ràng.
5. **Giữ default behavior:** delegate handler gốc nếu chỉ cần bổ sung một hành vi.
6. **Thiết kế stateless:** không lưu trạng thái request; cấu hình handler bất biến.
7. **Đăng ký qua module:** tạo mapper hoàn chỉnh tại composition root.
8. **Kiểm tra module order:** tránh hai extension cùng sửa một phần metadata.
9. **Viết contract test:** xác nhận output/input, type ngoài phạm vi và tương tác module.
10. **Đánh giá nâng cấp:** kiểm tra Javadoc/release note của Jackson version khi thay đổi major.

## 22. Kết luận

`BeanSerializerModifier` và `BeanDeserializerModifier` là các extension point mức thấp cho phép Jackson điều chỉnh quá trình tạo serializer/deserializer mặc định. Chúng có thể thay đổi property metadata, thứ tự property, builder hoặc bọc handler cuối cùng; các loại array, collection, map, enum và key có hook riêng. Đăng ký modifier qua `SimpleModule` hoặc module tùy chỉnh giúp gom chính sách vào một boundary cấu hình.

Modifier đáng dùng khi cần một quy tắc xuyên suốt nhiều bean hoặc cần can thiệp vào lifecycle mà annotation không đủ diễn đạt. Nếu chỉ cần bổ sung annotation cho class ngoài quyền sở hữu, mix-in thường đơn giản hơn; nếu một kiểu có format riêng, custom serializer/deserializer thường rõ hơn. Giới hạn phạm vi modifier, giữ handler stateless, delegate đầy đủ capability và kiểm thử mapper sau khi mọi module được đăng ký sẽ giảm rủi ro khi ứng dụng phát triển hoặc nâng Jackson version.

## Tài liệu tham khảo

- [Jackson Databind — BeanSerializerModifier API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ser/BeanSerializerModifier.html)
- [Jackson Databind — BeanDeserializerModifier API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/BeanDeserializerModifier.html)
- [Jackson Databind — BeanSerializerBuilder API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ser/BeanSerializerBuilder.html)
- [Jackson Databind — BeanDeserializerBuilder API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/BeanDeserializerBuilder.html)
- [Jackson Databind — SimpleModule API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/module/SimpleModule.html)
- [Jackson Databind — Module API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/Module.html)
- [Jackson Annotations — JsonIgnore API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)

