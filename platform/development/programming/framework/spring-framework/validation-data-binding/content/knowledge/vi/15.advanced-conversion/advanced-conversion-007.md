# Kiểu phần tử không xác định và thông tin generic bị mất

Khi chuyển đổi một collection trong Java, biết rằng giá trị có kiểu `List` là chưa đủ. Ứng dụng có thể cần biết đó là `List<String>`, `List<ProductCode>` hay `List<LocalDate>` để chuyển từng phần tử đúng cách. Tuy nhiên, do **type erasure** của Java generics, object collection ở runtime thường chỉ cho biết class là `ArrayList`/`List`; kiểu phần tử khai báo có thể không lấy được từ object instance.

Spring cung cấp `TypeDescriptor` và `ResolvableType` để giữ hoặc giải quyết metadata generic khi framework có một điểm khai báo kiểu như field, JavaBean property, method parameter, hoặc khi caller cung cấp target descriptor tường minh. Nếu thông tin không có hoặc không thể giải quyết, framework phải coi element type là **unknown**; không nên đoán từ một phần tử ngẫu nhiên rồi xem đó là contract của toàn collection.

Bài này giải thích type erasure, nguồn metadata generic, cách Spring conversion xử lý collection có kiểu và collection mất kiểu, cách truyền target descriptor, và giới hạn khi kiểu là raw, wildcard hoặc type variable không thể resolve. Ví dụ dùng Java 17+ và Spring Framework 6.2.x.

## 1. Vì sao biết List chưa đủ?

Giả sử form có property:

```java
private List<ProductCode> productCodes;
```

Nếu input là danh sách chuỗi `["ab-123", "cd-456"]`, ứng dụng muốn chuyển từng phần tử thành `ProductCode`. Để làm vậy, conversion system cần biết container đích là `List`, element type đích là `ProductCode` và converter `String -> ProductCode` nào được đăng ký.

Chỉ truyền `List.class` không cung cấp thông tin phần tử. Java reflection nhìn từ `List.class` không thể kết luận list đó chứa `ProductCode` hay `String`.

| Khai báo | Container type | Element type |
| --- | --- | --- |
| `List<String>` | `List` | `String` |
| `List<ProductCode>` | `List` | `ProductCode` |
| `List<?>` | `List` | wildcard, không có class cụ thể |
| `List<T>` | `List` | type variable, phụ thuộc context |
| raw `List` | `List` | không khai báo |
| `List<? extends Number>` | `List` | giới hạn trên `Number`, không phải subtype cụ thể |

Đối với `List<ProductCode>`, compiler kiểm tra kiểu khi viết source code. Nhưng generic argument không được lưu trên từng instance `ArrayList`. Muốn xử lý đúng, framework cần **metadata tại điểm khai báo** hoặc caller cung cấp metadata đích.

## 2. Type erasure: điều gì còn và điều gì mất?

Java compiler dùng generic để kiểm tra kiểu và áp dụng type erasure khi tạo bytecode. Ví dụ:

```java
List<String> names = new ArrayList<>();
List<ProductCode> codes = new ArrayList<>();

System.out.println(names.getClass() == codes.getClass());
```

Hai biến có thể trỏ tới object cùng class runtime `ArrayList`. Runtime class không lưu “object này sinh từ `List<String>`” hay “object kia sinh từ `List<ProductCode>`”.

Điều đó không có nghĩa mọi generic metadata biến mất khỏi chương trình. Signature của field, method và class có thể giữ generic declaration trong class file để reflection đọc. Field khai báo `List<ProductCode> productCodes` vẫn có generic type signature để Spring introspect.

Phân biệt ba trường hợp:

1. **Object runtime:** `new ArrayList<ProductCode>()` không tự mang element type generic trên instance.
2. **Khai báo reflective:** field `List<ProductCode> productCodes` có metadata generic; framework có thể đọc từ declaration.
3. **API chỉ nhận Class:** truyền `List.class` làm mất generic argument ở đối số đó; `Class<?>` không biểu diễn đầy đủ `List<ProductCode>`.

```text
Field declaration                         Runtime object
List<ProductCode> productCodes            ArrayList instance
        |                                         |
        | reflection/signature                    | getClass()
        v                                         v
TypeDescriptor / ResolvableType             ArrayList.class
(element = ProductCode)                     (element unknown)
        |                                         |
        +------------------+----------------------+
                           |
                  ConversionService
```

**Hệ quả:** không nên đoán rằng nếu phần tử đầu tiên là `ProductCode` thì toàn list luôn có contract `List<ProductCode>`. Collection có thể rỗng, có null, hoặc chứa kiểu không đồng nhất do raw type/unchecked cast.

## 3. Spring TypeDescriptor: mô tả kiểu tại điểm truy cập

`org.springframework.core.convert.TypeDescriptor` là metadata mô tả kiểu mà Spring cần chuyển đổi. Ngoài `Class<?>`, nó có thể giữ generic của array/collection/map, annotation tại điểm khai báo, và nguồn metadata như field, property hoặc method parameter.

| API | Mục đích |
| --- | --- |
| `TypeDescriptor.valueOf(Class<?>)` | Descriptor từ class; không bổ sung generic |
| `TypeDescriptor.forObject(Object)` | Descriptor từ object nguồn |
| `new TypeDescriptor(Field)` | Đọc generic/annotation tại field |
| `new TypeDescriptor(Property)` | Mô tả JavaBean property |
| `new TypeDescriptor(MethodParameter)` | Mô tả method parameter/return |
| `getElementTypeDescriptor()` | Lấy kiểu phần tử nếu giải được |
| `getMapKeyTypeDescriptor()` / `getMapValueTypeDescriptor()` | Kiểu key/value của Map |
| `TypeDescriptor.collection(Class, TypeDescriptor)` | Tạo descriptor collection có element type |
| `TypeDescriptor.map(Class, TypeDescriptor, TypeDescriptor)` | Tạo descriptor Map có key/value type |
| `getResolvableType()` | Truy cập `ResolvableType` nền |

Ví dụ JavaBean:

```java
public class CatalogForm {
    private List<ProductCode> codes;

    public List<ProductCode> getCodes() { return codes; }
    public void setCodes(List<ProductCode> codes) { this.codes = codes; }
}
```

Khi Spring introspect property `codes`, nó có thể lấy `List<ProductCode>` từ khai báo và tạo descriptor có element type là `ProductCode`. Nhờ đó, binder có ngữ cảnh để chuyển từng phần tử.

### 3.1. Raw descriptor và typed descriptor

```java
TypeDescriptor raw = TypeDescriptor.valueOf(List.class);

TypeDescriptor typed = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(ProductCode.class));
```

- `raw.getElementTypeDescriptor()` là `null` vì chỉ biết class `List`.
- `typed.getElementTypeDescriptor()` mô tả `ProductCode` vì caller đã cung cấp type.

`TypeDescriptor.collection` không đọc nội dung list và không chuyển đổi collection tại thời điểm tạo descriptor. Nó mô tả **kiểu đích được yêu cầu**; chuyển đổi chỉ diễn ra khi gọi `ConversionService.convert`.

## 4. ResolvableType: giải quyết generic qua hierarchy và context

`org.springframework.core.ResolvableType` introspect và resolve generic type. Nó hữu ích với field, superclass/interface parameterized, method parameter/return và type variable có thể thay thế từ concrete subclass.

Ví dụ:

```java
class BaseForm<T> {
    private List<T> values;
}

class ProductForm extends BaseForm<ProductCode> {}
```

Field ở base class khai báo `List<T>`. Trong context của `ProductForm`, `T` có thể được giải thành `ProductCode`. Đọc raw field type riêng lẻ chỉ cho thấy `List.class`; cần generic signature cùng context để resolve.

```java
ResolvableType type = ResolvableType.forClass(ProductForm.class)
        .as(BaseForm.class)
        .getGeneric(0);

Class<?> resolved = type.resolve();
```

Đoạn này lấy generic argument của `BaseForm` đã được giải trong context `ProductForm`. Khi `resolve()` trả `null`, metadata hiện tại không đủ để khẳng định một class cụ thể.

**Không đồng nhất unknown với Object có chủ đích.** `List<Object>` có element type khai báo là `Object`; raw `List` không có generic declaration. Hai trường hợp có thể dẫn tới lựa chọn converter khác nhau.

## 5. Chuyển đổi collection: target element type rất quan trọng

Spring có converter mặc định cho collection/array và có thể tái sử dụng converter của kiểu phần tử. Nếu đã đăng ký `Converter<String, ProductCode>`, thông thường không cần viết thêm converter đặc biệt `List<String> -> List<ProductCode>`.

```java
DefaultConversionService service =
        new DefaultConversionService();
service.addConverter(new ProductCodeConverter());

List<String> source = List.of("ab-123", "cd-456");

TypeDescriptor sourceType = TypeDescriptor.forObject(source);
TypeDescriptor targetType = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(ProductCode.class));

@SuppressWarnings("unchecked")
List<ProductCode> result =
        (List<ProductCode>) service.convert(
                source, sourceType, targetType);
```

Ở đây:

1. `sourceType` mô tả object nguồn; kiểu của từng phần tử có thể được narrow theo runtime value.
2. `targetType` chỉ rõ container `List` và element type `ProductCode`.
3. Spring chọn collection conversion, rồi chuyển từng phần tử qua converter scalar.
4. Kết quả chứa các object `ProductCode` đã tạo, không phải list chuỗi được cast.

Overload `ConversionService.convert(Object, Class<T>)` chỉ nhận target `Class<T>`, không đủ biểu diễn collection parameterized. Khi cần target generic, dùng overload nhận source/target `TypeDescriptor`.

### 5.1. Khi target element type unknown

Nếu chỉ có:

```java
Class<?> targetClass = List.class;
```

thì Spring không thể biết caller muốn `List<ProductCode>` hay `List<UUID>`. Hãy lấy descriptor từ field/property/method parameter nếu đang binding vào khai báo typed; tạo descriptor tường minh nếu code đang chuyển đổi programmatically; hoặc quy định contract riêng nếu API thực sự nhận raw/unknown collection.

Không nên đoán type từ sample đầu tiên trong collection. Với list rỗng, cách đoán đó không có dữ liệu; với raw/unsafe input, phần tử đầu có thể không đại diện các phần tử còn lại.

## 6. Ví dụ Java 17+ chạy được: metadata có và không có

Ví dụ dùng Spring Framework 6.2.12 để minh họa:

- Runtime class của hai list generic khác nhau vẫn giống nhau.
- BeanWrapper đọc descriptor từ property `List<ProductCode>`.
- Raw `List` không có element descriptor khai báo.
- ConversionService chuyển từng `String` sang `ProductCode` khi target descriptor nêu rõ kiểu.

### 6.1. Cấu trúc project

```text
generic-conversion-demo/
├── pom.xml
└── src/main/java/GenericConversionDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>generic-conversion-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/GenericConversionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.PropertyAccessorFactory;
import org.springframework.core.ResolvableType;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public class GenericConversionDemo {

    public record ProductCode(String value) {
        public ProductCode {
            if (value == null || !value.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid product code");
            }
        }
    }

    public static final class ProductCodeConverter
            implements Converter<String, ProductCode> {
        @Override
        public ProductCode convert(String source) {
            if (source == null) {
                return null;
            }
            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new ProductCode(normalized);
        }
    }

    public static class CatalogForm {
        private List<ProductCode> codes = new ArrayList<>();

        @SuppressWarnings("rawtypes")
        private List rawCodes = new ArrayList();

        public List<ProductCode> getCodes() { return codes; }
        public void setCodes(List<ProductCode> codes) { this.codes = codes; }

        @SuppressWarnings("rawtypes")
        public List getRawCodes() { return rawCodes; }

        @SuppressWarnings("rawtypes")
        public void setRawCodes(List rawCodes) { this.rawCodes = rawCodes; }
    }

    public static void main(String[] args) {
        List<String> strings = new ArrayList<>();
        List<ProductCode> codes = new ArrayList<>();

        System.out.println("same.runtime.class=" +
                (strings.getClass() == codes.getClass()));

        CatalogForm form = new CatalogForm();
        BeanWrapper wrapper =
                PropertyAccessorFactory.forBeanPropertyAccess(form);

        TypeDescriptor codesDescriptor =
                wrapper.getPropertyTypeDescriptor("codes");
        TypeDescriptor rawDescriptor =
                wrapper.getPropertyTypeDescriptor("rawCodes");

        System.out.println("declared.codes.element=" +
                codesDescriptor.getElementTypeDescriptor().getType()
                        .getSimpleName());
        System.out.println("declared.rawCodes.element=" +
                (rawDescriptor.getElementTypeDescriptor() == null
                        ? "unknown"
                        : rawDescriptor.getElementTypeDescriptor()
                                .getType().getSimpleName()));

        ResolvableType resolved =
                ResolvableType.forField(getCodesField());
        System.out.println("resolvable.codes.element=" +
                resolved.getGeneric(0).resolve().getSimpleName());

        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new ProductCodeConverter());

        List<String> input = List.of("ab-123", "cd-456");
        TypeDescriptor sourceType = TypeDescriptor.forObject(input);
        TypeDescriptor targetType = TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(ProductCode.class));

        @SuppressWarnings("unchecked")
        List<ProductCode> converted =
                (List<ProductCode>) service.convert(
                        input, sourceType, targetType);

        System.out.println("target.element=" +
                targetType.getElementTypeDescriptor().getType()
                        .getSimpleName());
        System.out.println("converted=" +
                converted.stream().map(ProductCode::value).toList());
        System.out.println("converted.element=" +
                converted.get(0).getClass().getSimpleName());
    }

    private static java.lang.reflect.Field getCodesField() {
        try {
            return CatalogForm.class.getDeclaredField("codes");
        } catch (NoSuchFieldException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
```

Chạy từ thư mục `generic-conversion-demo` bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=GenericConversionDemo
```

Stdout:

```text
same.runtime.class=true
declared.codes.element=ProductCode
declared.rawCodes.element=unknown
resolvable.codes.element=ProductCode
target.element=ProductCode
converted=[AB-123, CD-456]
converted.element=ProductCode
```

### 6.2. Giải thích kết quả

- Hai object `ArrayList` có cùng class runtime dù biến được khai báo `List<String>` hoặc `List<ProductCode>`.
- `BeanWrapper.getPropertyTypeDescriptor("codes")` đọc metadata property JavaBean. Field/setter khai báo `List<ProductCode>` giúp Spring biết element type.
- `rawCodes` chỉ dùng raw `List`, nên descriptor không xác định element type từ declaration; code in `unknown`.
- `ResolvableType.forField(...)` đọc generic signature trực tiếp từ field và resolve thành `ProductCode`.
- Target descriptor được tạo bằng `TypeDescriptor.collection(...)`, vì vậy conversion system biết phải chuyển từng phần tử sang `ProductCode`.
- Converter scalar chuẩn hóa từng chuỗi. Nó không cần converter riêng cho toàn list.

Ví dụ không đọc generic từ object instance. Metadata đến từ class/property/field declaration hoặc descriptor caller cung cấp.

## 7. Generic metadata trong BeanWrapper và DataBinder

Khi binding vào JavaBean có khai báo:

```java
class ImportForm {
    private List<LocalDate> dates;

    public List<LocalDate> getDates() { return dates; }
    public void setDates(List<LocalDate> dates) { this.dates = dates; }
}
```

Spring introspection có thể thu được element type từ property. Khi đăng ký converter/formatter cho kiểu ngày, binder có ngữ cảnh để chuyển từng phần tử. Với path indexed như `dates[0]`, nested metadata của property cũng có vai trò.

```java
BeanWrapper wrapper =
        PropertyAccessorFactory.forBeanPropertyAccess(form);

TypeDescriptor property =
        wrapper.getPropertyTypeDescriptor("dates");
TypeDescriptor element =
        property.getElementTypeDescriptor();
```

Đây là đoạn minh họa dùng `form` có property `dates`. Nếu element descriptor khác null, xem `element.getType()` để biết kiểu resolve được.

`DataBinder` sử dụng property access và conversion tương ứng khi bind `PropertyValues`. Khi element type được khai báo, framework có thể chuyển từng item; nếu input sai, binder có thể ghi lỗi gắn với path như `dates[1]` vào `BindingResult`. Hãy kiểm tra FieldError thực tế thay vì giả định mọi trường hợp collection conversion tạo cùng mã lỗi/path.

**Raw collection làm giảm thông tin.** Nếu property khai báo raw `List`, Spring không thể lấy declared element class từ signature. Runtime value đôi khi cho phép narrow descriptor cho một phần tử cụ thể, nhưng không khôi phục contract bị thiếu cho collection rỗng hoặc các phần tử khác.

## 8. GenericConverter: khi source/target descriptor thực sự cần thiết

`Converter<S,T>` thuận tiện cho cặp kiểu đơn giản. Nếu cần inspect generic/annotation của source và target, Spring có `GenericConverter`:

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
```

Đây là hình dạng rút gọn của SPI. `getConvertibleTypes()` khai báo các cặp kiểu; `convert(...)` nhận descriptor để đọc generic declaration, annotation hoặc điểm khai báo property/parameter.

Ví dụ, một converter array-to-collection có thể cần biết target là `List<ProductCode>` để chuyển từng phần tử. Spring đã có converter collection mặc định cho nhiều trường hợp; chỉ viết `GenericConverter` riêng khi logic cần metadata đặc biệt.

**Không dùng GenericConverter để đoán ý định của caller.** Nếu target type thực sự unknown, descriptor cũng không thể tự phát hiện business schema. Caller phải cung cấp type hoặc API phải có schema rõ.

`ConditionalGenericConverter` có thể chỉ chạy khi descriptor thỏa điều kiện, ví dụ annotation hay generic type cụ thể. Nó tăng độ phức tạp; với nhu cầu `String -> ProductCode` thông thường, `Converter<String, ProductCode>` đơn giản hơn.

## 9. Generic type: resolve được, chưa resolve được hoặc chỉ resolve một phần

| Khai báo/context | Khả năng resolve | Hướng xử lý |
| --- | --- | --- |
| `List<ProductCode>` | Element `ProductCode` rõ | Lấy từ field/property |
| `List<T>` trong `Base<T>`, target là `Base<ProductCode>` | Có thể resolve nếu context được cung cấp | Dùng `ResolvableType`/`TypeDescriptor` theo subclass |
| `List<T>` với raw `Base` | `T` unknown | Yêu cầu caller cung cấp schema |
| `List<?>` | Wildcard không chỉ định class cụ thể | Không tự đoán target element |
| `List<? extends Number>` | Có upper bound `Number`, không chỉ rõ subtype | Không tự giả định Integer/BigDecimal |
| raw `List` | Không khai báo element type | Sửa API thành typed collection nếu có thể |
| `List<Object>` | Element type khai báo là `Object` | Metadata có nhưng rất rộng |
| `List<List<ProductCode>>` | Có nested generic nếu declaration đầy đủ | Đi qua descriptor từng cấp |

`List<? extends Number>` và `List<Number>` không đồng nghĩa. Wildcard mô tả giới hạn kiểu; việc ghi phần tử cũng bị ràng buộc bởi variance của Java. DTO dùng cho binding thường dễ dự đoán hơn khi khai báo kiểu phần tử cụ thể và collection mutable phù hợp.

### 9.1. Type variable trong class generic

```java
class BaseForm<T> {
    private List<T> items;
}

class ProductForm extends BaseForm<ProductCode> {}
```

Nếu chỉ introspect declaration `BaseForm.items` mà thiếu context, `T` chưa chắc resolve. Nếu Spring biết đang xử lý `ProductForm`, nó có thể thay `T` bằng `ProductCode` thông qua generic hierarchy.

Đó là lý do Spring có `ResolvableType` thay vì chỉ dùng `Field.getType()`. `getType()` trả raw `List.class`; `getGenericType()` hoặc Spring `ResolvableType` giữ cấu trúc generic signature để resolve theo context.

## 10. Map cũng có hai generic argument

Một Map có key type và value type:

```java
Map<CustomerId, ProductCode> assignments;
```

`TypeDescriptor` cung cấp `getMapKeyTypeDescriptor()` và `getMapValueTypeDescriptor()`; khi tạo descriptor thủ công, dùng `TypeDescriptor.map(...)`:

```java
TypeDescriptor mapType = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(CustomerId.class),
        TypeDescriptor.valueOf(ProductCode.class));
```

Đây là descriptor cho `Map<CustomerId, ProductCode>`. Nó không đọc dữ liệu và không query database xác nhận customer/product. Nó chỉ nêu kiểu đích của key/value cho conversion.

Nếu Map khai báo raw hoặc `Map<?, ?>`, key/value descriptor có thể unknown. Không suy luận type cho toàn Map dựa trên key/value đầu tiên.

## 11. TypeDescriptor lồng nhau và annotation metadata

Một property có nhiều tầng:

```java
List<Map<String, ProductCode>> groupedCodes;
```

Metadata gồm container `List`, phần tử `Map<String, ProductCode>`, key `String` và value `ProductCode`. `TypeDescriptor` có thể biểu diễn các tầng collection/map; `nested(int)` và API liên quan giúp đi tới nested type. Nếu generic không resolve được, descriptor sâu hơn có thể không có sẵn.

Descriptor còn mang annotation trên field/property/parameter. `GenericConverter` có thể đọc annotation qua `targetType.getAnnotation(...)` để chọn rule conversion phù hợp. Tuy vậy, annotation metadata không biến converter thành nơi kiểm tra quyền hoặc query nghiệp vụ.

**Metadata không phải dữ liệu runtime.** TypeDescriptor mô tả điểm nhận giá trị; nó không giữ toàn bộ nội dung collection, không đảm bảo các phần tử hiện có đúng kiểu và không kiểm tra domain constraints.

## 12. Vì sao không dùng instanceof để suy luận generic cho cả collection?

Một pattern không an toàn:

```java
if (value instanceof List<?> list && !list.isEmpty()) {
    Class<?> elementClass = list.get(0).getClass();
    // Không thể kết luận mọi phần tử dùng cùng type.
}
```

Vấn đề:

- Collection rỗng không có phần tử đầu tiên.
- Collection có thể chứa null.
- Raw collection/unchecked cast có thể chứa nhiều kiểu.
- Phần tử đầu có thể là subtype chứ không phải contract khai báo.
- Runtime element không thay thế annotation/generic context của target property.

`elementTypeDescriptor(Object element)` có thể narrow descriptor cho **một phần tử cụ thể**. Điều đó không chứng minh toàn collection có contract element type ấy. Muốn chuyển cả collection sang typed target, lấy element type từ property hoặc truyền descriptor tường minh.

## 13. Lỗi thường gặp khi generic metadata bị mất

| Triệu chứng | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| `List.class` không cho biết element | Chỉ truyền raw class | Dùng `TypeDescriptor.collection(...)` |
| BeanWrapper không lấy element type | Property khai báo raw `List` | Sửa thành `List<T>` cụ thể |
| Base class trả `T` unresolved | Thiếu concrete context | Resolve qua subclass bằng `ResolvableType` |
| Collection target giữ String | Target element descriptor unknown/Object | Cung cấp typed target descriptor |
| Conversion lỗi ở phần tử N | Một element không thỏa converter | Kiểm tra input và field error path |
| Collection rỗng không suy được type | Không có runtime element để narrow | Dùng declaration/contract |
| Generic lồng nhau không resolve | Raw/wildcard/type variable ở một cấp | Kiểm tra từng nested descriptor |
| `ClassCastException` sau conversion | Cast list mà không convert từng phần tử | Dùng ConversionService |
| MVC và convert thủ công khác nhau | MVC có property metadata; code thủ công chỉ truyền Class | Dùng TypeDescriptor trong code thủ công |
| Map key/value bị chuyển sai | Chỉ mô tả raw Map | Dùng property descriptor hoặc `TypeDescriptor.map` |

Một lỗi nguy hiểm là unchecked cast:

```java
@SuppressWarnings("unchecked")
List<ProductCode> codes = (List<ProductCode>) rawList;
```

Đoạn này không chuyển đổi phần tử. Nó chỉ yêu cầu compiler không cảnh báo; lỗi thật có thể xuất hiện khi đọc/cast từng item. Muốn chuyển đổi, tạo collection target mới và convert từng phần tử theo contract.

## 14. Chọn API theo tình huống

| Tình huống | API phù hợp | Vì sao |
| --- | --- | --- |
| Chuyển một kiểu cụ thể | `Converter<S,T>` + ConversionService | Đơn giản, strongly typed |
| Chuyển collection theo khai báo property | Bean property metadata + TypeDescriptor | Đọc generic declaration |
| Code thủ công chuyển `List<S>` sang `List<T>` | ConversionService với source/target TypeDescriptor | Truyền descriptor generic |
| Type variable qua superclass/interface | `ResolvableType` | Resolve theo hierarchy/context |
| Converter cần annotation/generic đích | `GenericConverter` | Có source/target descriptor |
| Conversion có điều kiện metadata | `ConditionalGenericConverter` | Matching có điều kiện |
| UI text phụ thuộc Locale | `Formatter<T>` | Parse/print nhận Locale |
| Data binding JavaBean | `DataBinder`/`BeanWrapper` | Framework có property metadata |

Không mặc định dùng `GenericConverter` cho mọi collection. Spring đã có collection/array conversion phổ biến; converter scalar cho element thường đủ. Chỉ chuyển sang generic SPI khi logic thật sự cần descriptor hoặc nhiều cặp source/target.

## 15. Kiểm thử generic conversion

Các ca tối thiểu:

1. **Typed property:** `List<ProductCode>` cho element descriptor `ProductCode`.
2. **Raw property:** raw `List` có element descriptor unknown/null.
3. **Parameterized target:** descriptor collection với `ProductCode` chuyển từng phần tử.
4. **List rỗng:** target descriptor vẫn biết element type dù không có phần tử nguồn.
5. **Input lỗi:** một chuỗi sai mẫu gây conversion error.
6. **Nested types:** `List<Map<String, ProductCode>>` cho key/value descriptor tương ứng nếu declaration đầy đủ.
7. **Generic inheritance:** `BaseForm<T>` resolve T trong concrete subclass khi có context.
8. **Raw input không an toàn:** dữ liệu lẫn kiểu được phát hiện rõ, không dựa vào cast.
9. **Null element:** policy null được xác định.
10. **MVC và code thủ công:** test cả hai nếu ứng dụng dùng cả hai đường conversion.

Assertion JUnit minh họa:

```java
assertEquals(ProductCode.class,
        wrapper.getPropertyTypeDescriptor("codes")
                .getElementTypeDescriptor().getType());

assertNull(wrapper.getPropertyTypeDescriptor("rawCodes")
        .getElementTypeDescriptor());
```

Đoạn test cần `wrapper` của `CatalogForm` ở phần 6 và JUnit. Nó chứng minh generic metadata đến từ property declaration, không phải list instance.

Khi test conversion programmatically, assert mọi phần tử kết quả có class và value đúng. Chỉ assert result là `List` chưa chứng minh element type đúng.

## 16. Lưu ý thiết kế API

- Tránh raw collection trong DTO/public API; khai báo generic cụ thể nếu biết element type.
- Không dùng wildcard khi binder cần tạo/ghi phần tử cụ thể mà không có contract.
- Với cấu trúc động, dùng schema/discriminator rõ rồi resolve an toàn ở layer phù hợp.
- Không nhận class name tùy ý từ client rồi gọi `Class.forName` để chọn type; đó không phải cơ chế generic binding an toàn.
- Không dùng class runtime phần tử đầu để quyết định kiểu cả collection.
- Với collection lớn, giới hạn body size/số phần tử ở tầng input; generic metadata không giới hạn tài nguyên.
- Validation từng phần tử là bước riêng; descriptor không chứng minh nghiệp vụ hợp lệ.
- Nếu generic không resolve được, xử lý như unknown và yêu cầu contract bổ sung; không âm thầm chọn Object rồi cast.

## 17. Tự kiểm tra kiến thức

**1. Vì sao `new ArrayList<String>()` và `new ArrayList<ProductCode>()` có cùng runtime class?**  
Do Java type erasure. Generic argument phục vụ compile-time checking và có thể còn trong declaration signature, nhưng không được giữ trên từng instance.

**2. `TypeDescriptor.valueOf(List.class)` có biết element type không?**  
Không. Nó chỉ mô tả raw class; `getElementTypeDescriptor()` có thể trả null.

**3. Khi nào BeanWrapper biết property là `List<ProductCode>`?**  
Khi generic được khai báo cụ thể trong field/getter/setter signature và Spring introspection đọc được metadata.

**4. Vì sao `ConversionService.convert(source, List.class)` không đủ để yêu cầu `List<ProductCode>`?**  
Target `Class` không biểu diễn generic argument. Dùng overload nhận `TypeDescriptor`.

**5. `TypeDescriptor.collection(...)` có convert list ngay không?**  
Không. Nó tạo metadata mô tả target; conversion xảy ra khi gọi ConversionService.

**6. `List<?>` có thể resolve thành ProductCode từ phần tử đầu không?**  
Không nên coi phần tử đầu là contract. Wildcard không cung cấp target type cụ thể; caller phải nêu rõ `List<ProductCode>` khi đó là yêu cầu.

**7. `ResolvableType` giúp gì với `Base<T>`?**  
Có thể resolve type variable trong context subclass/interface cụ thể nếu generic hierarchy đủ thông tin.

**8. Có cần converter riêng `List<String> -> List<ProductCode>` không?**  
Thông thường không. Đăng ký converter scalar và cung cấp target element descriptor; Spring có thể tái sử dụng collection converter mặc định.

**9. Descriptor có chứng minh mọi phần tử hiện tại đúng kiểu không?**  
Không. Nó mô tả declaration/target, không kiểm tra toàn bộ collection runtime.

**10. Nếu element type unknown thì làm gì?**  
Giữ trạng thái unknown, yêu cầu schema/descriptor rõ ràng hoặc sửa API thành typed collection. Không đoán và unchecked cast.

**Ghi nhớ:** generic metadata không nằm trên từng collection instance sau type erasure; nó đến từ **declaration/context** hoặc **target descriptor do caller cung cấp**. `TypeDescriptor` mô tả kiểu tại điểm chuyển đổi, `ResolvableType` resolve generic qua hierarchy, và `ConversionService` dùng metadata đó để chuyển từng phần tử đúng kiểu. Khi metadata không có, hãy thừa nhận **unknown** và làm rõ contract thay vì đoán.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework 6.2 — ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableType.html)
- [Spring Framework 6.2 — GenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework 6.2 — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Java Language Specification — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6)
