# Tạo deserializer theo ngữ cảnh thuộc tính hoặc kiểu tổng quát

Trong Jackson, một custom deserializer đôi khi cần biết **nó đang được dùng ở property nào** hoặc **kiểu generic cụ thể của dữ liệu cần đọc là gì**. Ví dụ, cùng một kiểu `LocalDate` có thể được đọc theo hai quy tắc khác nhau tùy field; hoặc một wrapper `Box<T>` cần biết `T` là `User`, `Order` hay `List<Product>` để deserialize đúng giá trị bên trong.

Nếu viết deserializer chỉ dựa trên kiểu Java thô, nó không có đủ thông tin để phân biệt những ngữ cảnh đó. Jackson cung cấp `ContextualDeserializer` để tạo một phiên bản deserializer phù hợp với từng property hoặc kiểu đang được xử lý. Interface này cho phép nhận `DeserializationContext` và `BeanProperty`, đọc annotation/metadata của property, lấy `JavaType` đã được tham số hóa và tìm deserializer cho kiểu con.

Thiết kế quan trọng là deserializer contextual nên giữ cấu hình riêng trong instance bất biến được tạo ra từ `createContextual()`. Không sửa trạng thái dùng chung của một deserializer sau khi Jackson đã cache nó, vì cùng một deserializer có thể được tái sử dụng ở nhiều property và nhiều lần đọc.

Các ví dụ dưới đây dùng Jackson 2.x với package `com.fasterxml.jackson`. Những đoạn code minh họa cách triển khai; hãy dùng đúng version Jackson mà dự án đang quản lý.

## 1. Vì sao deserializer cần biết ngữ cảnh?

Một deserializer thông thường được gắn với kiểu Java. Ví dụ, một `LocalDateDeserializer` đọc chuỗi thành `LocalDate`. Nhưng cùng kiểu `LocalDate` có thể xuất hiện trong nhiều property:

```java
public class BookingRequest {
    private LocalDate bookingDate;
    private LocalDate birthDate;
}
```

Hai field có thể có quy tắc khác nhau:

- `bookingDate` chỉ nhận định dạng ISO `yyyy-MM-dd`.
- `birthDate` có thể nhận chuỗi rỗng như một giá trị không được cung cấp.

Nếu deserializer chỉ nhìn vào `LocalDate.class`, nó không biết đang xử lý `bookingDate` hay `birthDate`. Ngữ cảnh property cung cấp tên property, kiểu đầy đủ, member Java và annotation liên quan.

Tình huống thứ hai là generic type:

```java
public class Box<T> {
    private T value;
}
```

Khi Jackson gặp `Box<User>`, deserializer cần đọc `value` thành `User`. Khi gặp `Box<List<Order>>`, nó cần đọc thành `List<Order>`. Ở runtime, `Box.class` không giữ được `T` do Java type erasure; deserializer cần `JavaType` mà Jackson tạo từ khai báo generic ở property hoặc target type.

## 2. `ContextualDeserializer` là gì?

`ContextualDeserializer` là interface của Jackson Databind dành cho deserializer cần được cấu hình theo ngữ cảnh sử dụng.

```java
public interface ContextualDeserializer {
    JsonDeserializer<?> createContextual(
            DeserializationContext ctxt,
            BeanProperty property) throws JsonMappingException;
}
```

Hai tham số chính:

- `DeserializationContext ctxt`: cung cấp cấu hình và trạng thái của lần deserialize hiện tại, khả năng tìm deserializer khác, kiểu hiện tại và các cơ chế báo lỗi.
- `BeanProperty property`: mô tả property đang được deserialize, bao gồm tên, `JavaType`, annotation và metadata của member. Tham số này có thể là `null` khi deserializer được dùng ở root hoặc không gắn với một bean property cụ thể.

Jackson gọi `createContextual()` để lấy deserializer đã được điều chỉnh cho ngữ cảnh đó. Phương thức thường trả về một instance mới chứa cấu hình riêng, hoặc trả lại `this` nếu không cần thay đổi.

Sơ đồ khái quát:

```text
Jackson tìm deserializer cho một kiểu
              |
              v
       createContextual(ctxt, property)
              |
       +------+------+
       |             |
       v             v
  Đọc metadata    Đọc JavaType
  / annotation    và generic argument
       |             |
       +------+------+
              |
              v
   Tạo deserializer đã cấu hình
              |
              v
   deserialize(parser, context)
```

`ContextualDeserializer` không phải là nơi đọc token JSON. Nó chuẩn bị deserializer trước; phần đọc token vẫn nằm trong `deserialize()`.

## 3. Ví dụ property-specific: đọc `LocalDate` theo annotation

Giả sử ứng dụng có quy tắc cho phép chuỗi rỗng thành `null` ở một số field ngày, trong khi những field khác phải từ chối chuỗi rỗng.

Trước hết, tạo annotation đánh dấu property được phép coi chuỗi rỗng là không có giá trị:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
public @interface BlankAsNull {
}
```

Deserializer:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.BeanProperty;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.ContextualDeserializer;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public final class FlexibleLocalDateDeserializer
        extends StdDeserializer<LocalDate>
        implements ContextualDeserializer {

    private final boolean blankAsNull;

    public FlexibleLocalDateDeserializer() {
        this(false);
    }

    private FlexibleLocalDateDeserializer(boolean blankAsNull) {
        super(LocalDate.class);
        this.blankAsNull = blankAsNull;
    }

    @Override
    public JsonDeserializer<?> createContextual(
            DeserializationContext ctxt,
            BeanProperty property) throws JsonMappingException {

        boolean allowBlank = property != null
                && property.getAnnotation(BlankAsNull.class) != null;

        return new FlexibleLocalDateDeserializer(allowBlank);
    }

    @Override
    public LocalDate deserialize(JsonParser parser,
                                 DeserializationContext ctxt) throws IOException {
        if (parser.currentToken() != JsonToken.VALUE_STRING) {
            return (LocalDate) ctxt.handleUnexpectedToken(LocalDate.class, parser);
        }

        String text = parser.getText().trim();
        if (text.isEmpty()) {
            if (blankAsNull) {
                return null;
            }
            return ctxt.handleWeirdStringValue(
                    LocalDate.class,
                    text,
                    "Expected an ISO date in yyyy-MM-dd format"
            );
        }

        try {
            return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
        } catch (DateTimeParseException ex) {
            return ctxt.handleWeirdStringValue(
                    LocalDate.class,
                    text,
                    "Expected an ISO date in yyyy-MM-dd format"
            );
        }
    }
}
```

`createContextual()` kiểm tra annotation trên property rồi tạo một instance mới có cờ `blankAsNull` tương ứng. Instance mặc định không cho phép chuỗi rỗng; instance gắn với property có `@BlankAsNull` cho phép chuỗi rỗng thành `null`.

Gắn deserializer và annotation:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.time.LocalDate;

public class PersonRequest {
    @JsonDeserialize(using = FlexibleLocalDateDeserializer.class)
    private LocalDate bookingDate;

    @BlankAsNull
    @JsonDeserialize(using = FlexibleLocalDateDeserializer.class)
    private LocalDate birthDate;

    // getters và setters
}
```

Input:

```json
{
  "bookingDate": "2026-11-12",
  "birthDate": ""
}
```

`bookingDate` được parse thành ngày bình thường; `birthDate` được đọc thành `null`. Nếu `bookingDate` là chuỗi rỗng, deserializer báo lỗi theo chính sách của field đó.

Ví dụ này thể hiện lợi ích chính của contextualization: cùng một Java type và cùng một class deserializer nhưng mỗi property có thể nhận một cấu hình riêng.

## 4. `BeanProperty` cung cấp những thông tin nào?

Trong `createContextual()`, `BeanProperty` thường là nơi đầu tiên cần kiểm tra:

```java
String propertyName = property.getName();
JavaType propertyType = property.getType();
Class<?> rawType = propertyType.getRawClass();
BlankAsNull marker = property.getAnnotation(BlankAsNull.class);
```

Các API hữu ích:

| API | Ý nghĩa |
|---|---|
| `getName()` | Tên property theo Jackson |
| `getType()` | `JavaType` đầy đủ của property, có thể chứa generic argument |
| `getRawType()` | Lớp Java thô của property |
| `getMember()` | Member Java tương ứng nếu có |
| `getAnnotation(A.class)` | Lấy annotation trên property/member theo metadata Jackson |
| `getContextAnnotation(A.class)` | Lấy annotation từ ngữ cảnh chứa property, ví dụ lớp cha |
| `getWrapperName()` | Tên wrapper property nếu cấu hình có sử dụng |

`property` có thể là `null`; vì vậy luôn kiểm tra trước khi gọi method. Nếu deserializer được dùng ở root, không có một field như `bookingDate` để truy vấn annotation.

`getAnnotation()` và `getContextAnnotation()` phục vụ hai phạm vi khác nhau. Ví dụ, annotation đặt trên field có thể được lấy qua `getAnnotation()`, trong khi annotation đặt trên lớp chứa field có thể được đọc qua `getContextAnnotation()`.

## 5. Lấy kiểu tổng quát từ `JavaType`

Jackson dùng `JavaType` để giữ thông tin kiểu đầy đủ hơn `Class<?>`. Với property khai báo `Box<User>`, `property.getType()` mô tả cả raw class `Box` và tham số `User`.

Ví dụ:

```java
JavaType type = property.getType();

Class<?> rawClass = type.getRawClass();
JavaType firstArgument = type.containedType(0);
```

Với các kiểu container, API chuyên biệt dễ đọc hơn:

```java
JavaType listType = property.getType();
JavaType elementType = listType.getContentType();

JavaType mapType = property.getType();
JavaType keyType = mapType.getKeyType();
JavaType valueType = mapType.getContentType();
```

Các ví dụ cho thấy:

| Kiểu khai báo | `JavaType` cần lấy |
|---|---|
| `Box<User>` | `containedType(0)` là `User` |
| `List<User>` | `getContentType()` là `User` |
| `Map<String, Order>` | `getKeyType()` là `String`, `getContentType()` là `Order` |
| `Map<String, List<Order>>` | `getContentType()` là `List<Order>`, bên trong list có content type `Order` |

Không dùng `property.getType().getRawClass()` để suy ra generic argument. `getRawClass()` chỉ trả `Box.class` hoặc `List.class`; nó không cho biết `T` là gì.

## 6. Custom deserializer cho wrapper generic `Box<T>`

Giả sử JSON có dạng:

```json
{
  "value": {
    "id": 10,
    "name": "An"
  }
}
```

Lớp Java generic:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

@JsonDeserialize(using = BoxDeserializer.class)
public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }
}
```

Deserializer cần biết kiểu `T` để đọc property `value`. Nó lấy generic argument từ `JavaType` của wrapper và tìm deserializer tương ứng qua `DeserializationContext`.

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.BeanProperty;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.ContextualDeserializer;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;

public final class BoxDeserializer
        extends StdDeserializer<Box<?>>
        implements ContextualDeserializer {

    private final JavaType valueType;
    private final JsonDeserializer<Object> valueDeserializer;

    public BoxDeserializer() {
        this(null, null);
    }

    @SuppressWarnings("unchecked")
    private BoxDeserializer(JavaType valueType,
                            JsonDeserializer<?> valueDeserializer) {
        super(Box.class);
        this.valueType = valueType;
        this.valueDeserializer = (JsonDeserializer<Object>) valueDeserializer;
    }

    @Override
    public JsonDeserializer<?> createContextual(
            DeserializationContext ctxt,
            BeanProperty property) throws JsonMappingException {

        JavaType wrapperType = property != null
                ? property.getType()
                : ctxt.getContextualType();

        JavaType contentType = wrapperType == null
                ? null
                : wrapperType.containedType(0);

        if (contentType == null) {
            // Raw Box không cung cấp generic argument; Object là fallback.
            contentType = ctxt.constructType(Object.class);
        }

        JsonDeserializer<?> contentDeserializer =
                ctxt.findContextualValueDeserializer(contentType, property);

        return new BoxDeserializer(contentType, contentDeserializer);
    }

    @Override
    public Box<?> deserialize(JsonParser parser,
                              DeserializationContext ctxt) throws IOException {
        if (parser.currentToken() != JsonToken.START_OBJECT) {
            return (Box<?>) ctxt.handleUnexpectedToken(Box.class, parser);
        }

        Object value = null;
        boolean valueWasPresent = false;

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            if (parser.currentToken() == null) {
                return (Box<?>) ctxt.handleUnexpectedToken(Box.class, parser);
            }

            if (parser.currentToken() != JsonToken.FIELD_NAME) {
                return (Box<?>) ctxt.handleUnexpectedToken(Box.class, parser);
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            if ("value".equals(fieldName)) {
                valueWasPresent = true;
                value = valueToken == JsonToken.VALUE_NULL
                        ? valueDeserializer.getNullValue(ctxt)
                        : valueDeserializer.deserialize(parser, ctxt);
            } else {
                parser.skipChildren();
            }
        }

        // Ví dụ này quy định field thiếu và field null đều tạo Box(null).
        // Nếu hợp đồng cần phân biệt hai trường hợp, hãy kiểm tra valueWasPresent.
        return new Box<>(value);
    }
}
```

Trong code này:

1. `createContextual()` lấy kiểu wrapper từ property hoặc contextual type hiện tại.
2. `containedType(0)` lấy tham số `T`.
3. `findContextualValueDeserializer()` tìm deserializer phù hợp với kiểu `T`, đồng thời cho phép Jackson áp dụng contextualization cho kiểu con.
4. `deserialize()` đọc object wrapper, tìm field `value` rồi ủy quyền việc đọc nội dung cho deserializer của `T`.
5. Các field không biết được bỏ qua cùng nội dung lồng nhau bằng `skipChildren()`.

Trường `valueWasPresent` cho thấy cách phân biệt field không xuất hiện với field xuất hiện nhưng null. Ví dụ đang chọn cùng kết quả `Box(null)` cho cả hai; nếu nghiệp vụ cần phân biệt, có thể ném lỗi khi field thiếu hoặc lưu thêm trạng thái trong wrapper.

### 6.1. Đọc wrapper với generic type cụ thể

Khi property khai báo:

```java
private Box<User> userBox;
```

Jackson cung cấp `Box<User>` cho `createContextual()`. Deserializer lấy `User` làm content type và tạo value deserializer cho `User`.

Với root value, hãy cung cấp đầy đủ generic type bằng `TypeReference`:

```java
Box<User> box = mapper.readValue(
        json,
        new TypeReference<Box<User>>() {}
);
```

Nếu chỉ truyền `Box.class`, Java không còn thông tin `User` ở runtime. Deserializer sẽ chỉ thấy raw `Box` và có thể phải dùng `Object` làm fallback; object lồng bên trong khi đó thường trở thành cấu trúc map/list tự nhiên của Jackson.

### 6.2. Generic lồng nhau

Với:

```java
Box<List<User>> usersBox;
```

`containedType(0)` là `List<User>`, không phải `User`. Khi deserializer được tìm qua `findContextualValueDeserializer()`, Jackson tiếp tục xử lý generic argument của `List<User>`.

Có thể đọc root:

```java
Box<List<User>> usersBox = mapper.readValue(
        json,
        new TypeReference<Box<List<User>>>() {}
);
```

Nguyên tắc là giữ toàn bộ `JavaType` của `T` và giao cho Jackson xử lý đệ quy. Không tự lấy raw class rồi cast các phần tử bằng tay nếu không có yêu cầu đặc biệt.

## 7. Sử dụng contextual value deserializer đúng cách

Trong `createContextual()`, nên tìm deserializer thông qua `DeserializationContext`:

```java
JsonDeserializer<?> valueDeserializer =
        ctxt.findContextualValueDeserializer(valueType, property);
```

API này giúp Jackson chọn deserializer theo `JavaType` và property hiện tại, đồng thời áp dụng contextualization cho kiểu con. Đây là cách phù hợp khi custom deserializer bao một kiểu khác và muốn tái sử dụng toàn bộ khả năng Databind của Jackson.

Tránh tự tạo deserializer bằng `new SomeDeserializer()` cho kiểu con. Làm vậy có thể bỏ qua module, annotation, naming strategy, converter, mix-in hoặc custom deserializer mà ứng dụng đã đăng ký.

Nếu kiểu con có polymorphic type metadata, custom deserializer cần giữ và áp dụng `TypeDeserializer` phù hợp để gọi `deserializeWithType()`. Không giả định một lời gọi `deserialize()` trực tiếp sẽ xử lý mọi type discriminator. Với generic wrapper có subtype đa hình, hãy kiểm tra riêng đường đi đó bằng test.

## 8. Dùng annotation trên property để chọn custom deserializer

`@JsonDeserialize` cho phép chọn deserializer ở các cấp khác nhau:

| Thuộc tính annotation | Phạm vi |
|---|---|
| `using` | Deserializer của chính property/type |
| `contentUsing` | Deserializer của phần tử trong collection/array hoặc value trong container phù hợp |
| `keyUsing` | Deserializer của key trong map |
| `as` | Kiểu Java cụ thể để ánh xạ thay cho kiểu khai báo trong một số trường hợp |
| `contentAs` | Kiểu cụ thể cho nội dung container |
| `keyAs` | Kiểu cụ thể cho key map |

Ví dụ, một property là `List<LocalDate>` nhưng chỉ muốn custom deserializer áp dụng cho từng ngày:

```java
public class ScheduleRequest {
    @JsonDeserialize(contentUsing = FlexibleLocalDateDeserializer.class)
    private List<LocalDate> holidays;

    // getter và setter
}
```

Ở đây, `FlexibleLocalDateDeserializer` được dùng cho mỗi phần tử của `holidays`; nó không thay thế deserializer của toàn bộ `List`.

Ví dụ với map value:

```java
public class CalendarRequest {
    @JsonDeserialize(contentUsing = FlexibleLocalDateDeserializer.class)
    private Map<String, LocalDate> datesByName;
}
```

Nếu cần custom map key, dùng `keyUsing` với `KeyDeserializer` phù hợp. `ContextualDeserializer` xử lý value deserializer; cơ chế contextual cho key có extension point riêng theo API Jackson version đang dùng.

## 9. Property context có thể lấy annotation của lớp chứa

Có những chính sách được đặt ở lớp chứa thay vì từng field, ví dụ một DTO quy định mọi ngày trong payload dùng một timezone hoặc một format cụ thể. `BeanProperty.getContextAnnotation()` có thể truy xuất annotation từ context class:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ApiDatePolicy {
    String pattern();
}
```

Lớp DTO:

```java
@ApiDatePolicy(pattern = "dd/MM/uuuu")
public class LegacyDateRequest {
    @JsonDeserialize(using = ContextualDateDeserializer.class)
    private LocalDate createdDate;
}
```

Trong `createContextual()`:

```java
ApiDatePolicy policy = property == null
        ? null
        : property.getContextAnnotation(ApiDatePolicy.class);

String pattern = policy == null
        ? "uuuu-MM-dd"
        : policy.pattern();
```

Deserializer có thể tạo formatter từ `pattern` và lưu formatter đó trong instance riêng. `DateTimeFormatter` là immutable và thread-safe, nên phù hợp để tái sử dụng.

Nếu policy đặt ở nhiều cấp (field, getter, class, mix-in), hãy quy định thứ tự ưu tiên rõ ràng. Đừng để cùng một property nhận hai pattern mâu thuẫn mà không có quy tắc.

## 10. Root deserializer và trường hợp `property == null`

Một custom deserializer có thể được dùng trực tiếp ở root:

```java
LocalDate date = mapper.readValue("\"2026-11-12\"", LocalDate.class);
```

Khi không có bean property cụ thể, `BeanProperty` truyền vào `createContextual()` có thể là `null`. Vì vậy:

- Không gọi `property.getName()` trước khi kiểm tra null.
- Không giả định có annotation trên field.
- Có thể dùng `ctxt.getContextualType()` nếu cần kiểu hiện tại trong quá trình contextualization.
- Nếu không có metadata property, áp dụng cấu hình mặc định an toàn.

Với generic root, caller cần truyền `TypeReference<T>` hoặc `JavaType` để giữ generic metadata. `Class<T>` chỉ đủ cho kiểu không cần generic argument.

## 11. Không sửa trạng thái của deserializer dùng chung

Jackson có thể cache deserializer để tái sử dụng. Nếu một instance được dùng cho nhiều property, việc thay đổi field cấu hình bên trong `createContextual()` có thể gây rò rỉ cấu hình giữa các property hoặc giữa các request.

Ví dụ thiết kế không an toàn:

```java
public class BadDeserializer extends StdDeserializer<LocalDate>
        implements ContextualDeserializer {

    private boolean blankAsNull;

    @Override
    public JsonDeserializer<?> createContextual(
            DeserializationContext ctxt,
            BeanProperty property) {
        this.blankAsNull = property != null
                && property.getAnnotation(BlankAsNull.class) != null;
        return this;
    }

    // deserialize() dùng blankAsNull
}
```

Nếu instance này được dùng cho hai field có policy khác nhau, lần contextualization sau có thể ghi đè cờ của lần trước.

Thiết kế an toàn:

```java
@Override
public JsonDeserializer<?> createContextual(
        DeserializationContext ctxt,
        BeanProperty property) {
    boolean allowBlank = property != null
            && property.getAnnotation(BlankAsNull.class) != null;
    return new FlexibleLocalDateDeserializer(allowBlank);
}
```

Instance được tạo có trạng thái final và không thay đổi sau đó. Constructor mặc định có thể giữ cấu hình chung; `createContextual()` trả instance riêng theo property.

Không lưu `JsonParser`, `DeserializationContext`, `BeanProperty` hoặc dữ liệu request vào field của deserializer để dùng cho lần đọc sau. Các đối tượng đó thuộc một lần xử lý cụ thể.

## 12. Phân biệt contextualization với dependency resolution

Jackson có thêm `ResolvableDeserializer`, dùng cho deserializer cần được liên kết hoặc hoàn thiện dependency sau khi instance được tạo, ví dụ một deserializer phụ thuộc vào deserializer khác trong cấu trúc đệ quy.

Hai cơ chế có mục tiêu khác nhau:

| Interface | Mục đích |
|---|---|
| `ContextualDeserializer` | Điều chỉnh deserializer theo property/type context: annotation, format, generic type, property metadata |
| `ResolvableDeserializer` | Hoàn tất việc resolve dependency của deserializer sau khi được tạo |

Một class có thể cần cả hai interface trong trường hợp phức tạp. Tuy nhiên, với phần lớn custom deserializer theo property hoặc generic argument, `ContextualDeserializer` là extension point cần dùng.

Không dùng `ResolvableDeserializer` chỉ để lấy tên property hoặc annotation; các thông tin đó thuộc contextualization.

## 13. Kết hợp contextual deserializer với module đăng ký

Ngoài `@JsonDeserialize(using = ...)`, có thể đăng ký deserializer theo kiểu qua `SimpleModule`:

```java
SimpleModule module = new SimpleModule("custom-dates");
module.addDeserializer(LocalDate.class, new FlexibleLocalDateDeserializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Khi đăng ký toàn cục theo kiểu, deserializer vẫn có thể triển khai `ContextualDeserializer` để nhận property metadata. Tuy nhiên, policy mặc định phải phù hợp với mọi property không có annotation. Nếu chỉ một số field cần custom behavior, gắn `@JsonDeserialize` tại property thường làm phạm vi ảnh hưởng rõ hơn.

Nếu một module đã đăng ký deserializer toàn cục và property lại khai báo `using`, cần kiểm tra ưu tiên cấu hình trong ứng dụng thực tế. Không nên tạo nhiều nguồn cấu hình cạnh tranh mà không có quy tắc.

## 14. Xử lý generic type lồng nhau và container

Khi `JavaType` mô tả một cấu trúc lồng nhau, hãy truyền nguyên `JavaType` cho Jackson thay vì tự tháo rời quá nhiều tầng.

Ví dụ:

```java
JavaType userListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);

JavaType boxOfUsersType = mapper.getTypeFactory()
        .constructParametricType(Box.class, userListType);

Box<List<User>> result = mapper.readValue(json, boxOfUsersType);
```

Trong custom `BoxDeserializer`, `containedType(0)` nhận được `List<User>`. `findContextualValueDeserializer()` sau đó lấy deserializer của cả list cùng element type `User`.

Với map:

```java
JavaType mapType = mapper.getTypeFactory().constructMapType(
        Map.class,
        String.class,
        userListType
);

JavaType boxOfMapType = mapper.getTypeFactory()
        .constructParametricType(Box.class, mapType);
```

`T` lúc này là `Map<String, List<User>>`. Custom wrapper không cần biết từng tầng cấu trúc; nó chỉ cần chuyển đúng `JavaType` của `T` cho Jackson.

## 15. Xử lý polymorphic generic content

Nếu `T` là kiểu cơ sở có các subtype được cấu hình bằng `@JsonTypeInfo`, custom wrapper cần bảo đảm type metadata của `T` cũng được áp dụng. Trong những custom deserializer tự gọi content deserializer trực tiếp, có thể cần lấy `TypeDeserializer` từ cấu hình và gọi `deserializeWithType()` cho value.

Ví dụ khái quát trong `createContextual()`:

```java
TypeDeserializer typeDeserializer =
        ctxt.getConfig().findTypeDeserializer(contentType);

if (typeDeserializer != null) {
    typeDeserializer = typeDeserializer.forProperty(property);
}
```

Trong `deserialize()`:

```java
Object value = typeDeserializer == null
        ? valueDeserializer.deserialize(parser, ctxt)
        : valueDeserializer.deserializeWithType(parser, ctxt, typeDeserializer);
```

Đoạn này chỉ cần khi content type có polymorphic metadata. Với kiểu cụ thể như `User` không có type discriminator, lời gọi `deserialize()` thông thường là đủ. Cần kiểm tra API cụ thể của Jackson version và test cả subtype ID hợp lệ lẫn không hợp lệ.

## 16. Xử lý lỗi theo property context

Contextual deserializer biết property đang được đọc, nhưng nên để Jackson xây dựng lỗi mapping có path thay vì tự ném một exception không có ngữ cảnh.

Các helper thường dùng:

- `ctxt.handleUnexpectedToken(...)`: báo token không đúng kiểu mong đợi.
- `ctxt.handleWeirdStringValue(...)`: báo chuỗi không thể chuyển thành kiểu đích.
- `ctxt.reportInputMismatch(...)`: báo dữ liệu không khớp hợp đồng với thông tin format.
- `JsonMappingException.from(parser, message)`: tạo lỗi mapping gắn với parser hiện tại khi cần.

Ví dụ:

```java
return ctxt.handleWeirdStringValue(
        LocalDate.class,
        text,
        "Property '%s' must use yyyy-MM-dd",
        property == null ? "<root>" : property.getName()
);
```

Không đưa secret hoặc toàn bộ payload nhạy cảm vào thông điệp lỗi. Jackson thường bổ sung đường dẫn property/array index khi lỗi đi qua quá trình mapping, giúp chẩn đoán vị trí dữ liệu sai.

## 17. Kiểm thử property-specific behavior

Với ví dụ `BlankAsNull`, cần xác nhận hai property cùng kiểu nhưng cho kết quả khác nhau:

```java
@Test
void appliesDifferentPolicyPerDateProperty() throws Exception {
    String json = """
            {
              "bookingDate": "2026-11-12",
              "birthDate": ""
            }
            """;

    PersonRequest request = mapper.readValue(json, PersonRequest.class);

    assertEquals(LocalDate.of(2026, 11, 12), request.getBookingDate());
    assertNull(request.getBirthDate());
}
```

Test lỗi:

```java
@Test
void rejectsBlankBookingDate() {
    String json = """
            {
              "bookingDate": "",
              "birthDate": ""
            }
            """;

    assertThrows(JsonMappingException.class,
            () -> mapper.readValue(json, PersonRequest.class));
}
```

Test cần dùng đúng mapper đã đăng ký custom deserializer nếu annotation không đủ để khởi tạo. Ngoài ra, kiểm tra property có annotation trên field, getter hoặc constructor parameter theo cách model đang sử dụng.

## 18. Kiểm thử generic type preservation

Với `Box<User>`, test cần xác nhận object bên trong thực sự là `User`:

```java
@Test
void readsBoxWithConcreteGenericType() throws Exception {
    String json = """
            {
              "value": {
                "id": 10,
                "name": "An"
              }
            }
            """;

    Box<User> box = mapper.readValue(
            json,
            new TypeReference<Box<User>>() {}
    );

    assertInstanceOf(User.class, box.getValue());
    assertEquals(10L, box.getValue().getId());
}
```

Test generic lồng nhau:

```java
Box<List<User>> box = mapper.readValue(
        json,
        new TypeReference<Box<List<User>>>() {}
);

assertInstanceOf(List.class, box.getValue());
assertInstanceOf(User.class, box.getValue().get(0));
```

Nếu chỉ đọc bằng `Box.class`, test có thể cho thấy `value` trở thành `LinkedHashMap`. Đây là dấu hiệu generic type đã bị mất trước khi custom deserializer nhận được context.

## 19. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cùng một kiểu nhưng hai field không thể có policy khác nhau | Deserializer chỉ dựa vào raw class | Implement `ContextualDeserializer`, đọc metadata từ `BeanProperty` |
| Annotation không được nhìn thấy | `property` null hoặc annotation đặt ở phạm vi khác | Kiểm tra null; dùng `getAnnotation()`/`getContextAnnotation()` đúng phạm vi |
| `Box<T>` đọc thành `LinkedHashMap` | Dùng raw `Box.class` hoặc generic argument không được giữ | Dùng `TypeReference<Box<User>>` hoặc `JavaType` |
| Deserializer của kiểu con không dùng module đã đăng ký | Tự tạo deserializer bằng `new` | Dùng `ctxt.findContextualValueDeserializer()` |
| Cấu hình property này ảnh hưởng property khác | Sửa field mutable trên deserializer dùng chung | Trả instance mới, bất biến từ `createContextual()` |
| Root deserialize bị lỗi null pointer | Giả định `BeanProperty` luôn có giá trị | Có nhánh xử lý `property == null` |
| Generic lồng nhau bị mất type | Chỉ dùng `getRawClass()` | Giữ và truyền `JavaType` đầy đủ |
| Subtype generic không được nhận diện | Custom deserializer gọi `deserialize()` mà bỏ qua type metadata | Lấy `TypeDeserializer` và gọi `deserializeWithType()` khi cần |
| Field thiếu và field null bị coi giống nhau ngoài ý muốn | Không theo dõi field có xuất hiện hay không | Dùng cờ `seen`, validation hoặc kiểu biểu diễn ba trạng thái |

## 20. Quy trình triển khai contextual deserializer

Khi cần custom deserializer phụ thuộc property hoặc generic type, có thể thực hiện theo trình tự:

1. Tạo deserializer cơ sở có constructor mặc định để Jackson có thể khởi tạo.
2. Implement `ContextualDeserializer`.
3. Trong `createContextual()`, xử lý trường hợp `property == null`.
4. Lấy annotation/property metadata bằng `BeanProperty`.
5. Lấy `JavaType` đầy đủ từ `property.getType()` hoặc contextual type hiện tại.
6. Với wrapper generic, lấy `containedType(index)`, `getContentType()` hoặc `getKeyType()` phù hợp.
7. Tìm deserializer của kiểu con bằng `ctxt.findContextualValueDeserializer()`.
8. Tạo và trả instance mới chứa cấu hình final, không sửa trạng thái dùng chung.
9. Trong `deserialize()`, đọc token và ủy quyền phần giá trị con cho deserializer đã contextualize.
10. Kiểm thử nhiều property, generic lồng nhau, root value, null, field thiếu và lỗi kiểu.

## 21. Ghi nhớ

`ContextualDeserializer` cho phép Jackson điều chỉnh một custom deserializer theo property hoặc generic type đang được xử lý. `BeanProperty` cung cấp tên, kiểu đầy đủ và annotation; `JavaType` giữ generic argument; `DeserializationContext.findContextualValueDeserializer()` giúp tìm deserializer của kiểu con theo đúng cấu hình ứng dụng.

Hãy tạo instance contextual bất biến thay vì sửa trạng thái của deserializer dùng chung. Xử lý `property == null`, giữ đầy đủ generic metadata và áp dụng type metadata khi kiểu con có polymorphism. Cách làm này giúp một deserializer có thể tái sử dụng an toàn ở nhiều property và nhiều cấu trúc generic mà vẫn tôn trọng chính sách riêng của từng ngữ cảnh.
