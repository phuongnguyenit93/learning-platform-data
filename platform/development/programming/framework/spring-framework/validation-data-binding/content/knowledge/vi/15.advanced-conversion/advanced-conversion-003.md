# TypeDescriptor với kiểu phần tử, generic và annotation trong Spring

## 1. Vì sao cần TypeDescriptor?

Java cung cấp Class<?> để mô tả kiểu runtime, nhưng generic bị type erasure. Vì thế List<String> và List<Integer> đều có cùng raw class là List.class. Nếu chỉ dựa vào class nguồn/đích, conversion service không thể biết phần tử collection cần chuyển từ kiểu nào sang kiểu nào.

Spring Core có org.springframework.core.convert.TypeDescriptor để mang thêm metadata cho conversion: raw type, generic element/key/value types và annotation khai báo trên field hoặc method parameter. Nhờ đó, converter có thể chuyển List<String> thành List<Integer>, chuyển cả key lẫn value của map, hoặc chỉ hoạt động khi target có annotation nhất định.

Sau bài này, bạn có thể tạo descriptor từ class/field/collection/map, đọc generic lồng nhau, truy cập annotation metadata và hiểu khi nào cần GenericConverter hoặc ConditionalGenericConverter.

## 2. Class<?> và TypeDescriptor

Class<?> là lựa chọn đủ dùng khi quy tắc chỉ phụ thuộc kiểu runtime như String.class hoặc Integer.class. TypeDescriptor mở rộng thông tin đó.

| Nhu cầu | Class<?> | TypeDescriptor |
| --- | --- | --- |
| Raw Java class | Có | Có qua getType() |
| Generic element của List | Không giữ trong List.class | getElementTypeDescriptor() |
| Generic key/value của Map | Không giữ trong Map.class | getMapKeyTypeDescriptor() / getMapValueTypeDescriptor() |
| Annotation trên field | Không mô tả | getAnnotation() / hasAnnotation() |
| Cấu trúc generic sâu | Không | Metadata qua getResolvableType() và descriptor con |

TypeDescriptor không khôi phục generic đã mất ở mọi object runtime. TypeDescriptor.forObject(value) biết runtime class, nhưng không suy ra chắc chắn một ArrayList được dùng như List<String> hay List<Integer>. Muốn giữ generic metadata, tạo descriptor từ field/parameter có khai báo kiểu hoặc cung cấp element descriptor tường minh.

## 3. API thường dùng

TypeDescriptor thuộc package org.springframework.core.convert.

| API | Ý nghĩa |
| --- | --- |
| valueOf(Class<?>) | Descriptor từ class |
| new TypeDescriptor(Field) | Giữ generic và annotation của field |
| getType() | Raw class |
| getResolvableType() | Generic type resolution |
| getElementTypeDescriptor() | Kiểu phần tử collection/array |
| getMapKeyTypeDescriptor() | Kiểu key map |
| getMapValueTypeDescriptor() | Kiểu value map |
| hasAnnotation(Class<?>) / getAnnotation(Class<A>) | Kiểm tra/đọc annotation |
| getAnnotations() | Metadata annotation |
| getSource() | Phần tử khai báo nguồn nếu có |
| isCollection() / isArray() / isMap() | Kiểm tra dạng cấu trúc |
| isAssignableTo(TypeDescriptor) | Kiểm tra khả năng gán |
| collection(Class, TypeDescriptor) | Tạo descriptor collection |
| array(TypeDescriptor) | Tạo descriptor array |
| map(Class, TypeDescriptor, TypeDescriptor) | Tạo descriptor map |

Descriptor chỉ tạo từ raw class thường không có element/key/value type. Kiểm tra null trước khi truy cập descriptor con vì generic có thể không khai báo hoặc không resolve được.

### 3.1. Collection và array

~~~java
TypeDescriptor strings = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor integers = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));
TypeDescriptor stringArray =
        TypeDescriptor.array(TypeDescriptor.valueOf(String.class));
~~~

strings mô tả List<String>, integers mô tả List<Integer>. Caller chủ động cung cấp metadata generic để conversion service biết phải chuyển đổi từng phần tử.

### 3.2. Map

~~~java
TypeDescriptor stringToInteger = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(String.class),
        TypeDescriptor.valueOf(Integer.class));
~~~

Descriptor trên biểu diễn Map<String, Integer>. Với map conversion, key và value là hai nhánh kiểu độc lập. Nếu hai key nguồn khác nhau cùng thành một key đích sau conversion, dữ liệu có thể va chạm; TypeDescriptor không tự quyết định chính sách xử lý collision.

## 4. Đọc generic metadata từ Field

Tạo model có collection, map và generic lồng nhau:

~~~java
import java.util.List;
import java.util.Map;

public class ImportForm {
    private List<String> codes;
    private Map<String, Integer> quantities;
    private List<List<String>> matrix;

    public List<String> getCodes() { return codes; }
    public void setCodes(List<String> codes) { this.codes = codes; }

    public Map<String, Integer> getQuantities() { return quantities; }
    public void setQuantities(Map<String, Integer> quantities) {
        this.quantities = quantities;
    }

    public List<List<String>> getMatrix() { return matrix; }
    public void setMatrix(List<List<String>> matrix) {
        this.matrix = matrix;
    }
}
~~~

Đọc element type từ reflection field:

~~~java
Field codesField = ImportForm.class.getDeclaredField("codes");
TypeDescriptor codes = new TypeDescriptor(codesField);

System.out.println(codes.getType().getSimpleName());
System.out.println(
        codes.getElementTypeDescriptor().getType().getSimpleName());
~~~

Kết quả:

~~~text
List
String
~~~

getType() trả raw type List; getElementTypeDescriptor() trả descriptor phần tử String. Không cần tạo instance ImportForm để đọc generic signature trên field.

### 4.1. Generic lồng nhau

Với List<List<String>> matrix:

~~~java
Field field = ImportForm.class.getDeclaredField("matrix");
TypeDescriptor matrix = new TypeDescriptor(field);
TypeDescriptor row = matrix.getElementTypeDescriptor();
TypeDescriptor cell = row.getElementTypeDescriptor();

System.out.println(matrix.getType().getSimpleName());
System.out.println(row.getType().getSimpleName());
System.out.println(cell.getType().getSimpleName());
~~~

Kết quả:

~~~text
List
List
String
~~~

Mỗi lần đi xuống một tầng, lấy element descriptor của tầng hiện tại. Với raw collection, wildcard hoặc type variable chưa resolve, descriptor con có thể không có hoặc không đủ cụ thể. Không đoán kiểu từ phần tử đầu tiên của collection runtime.

### 4.2. Generic metadata của Map

~~~java
Field field = ImportForm.class.getDeclaredField("quantities");
TypeDescriptor quantities = new TypeDescriptor(field);

System.out.println(
        quantities.getMapKeyTypeDescriptor().getType().getSimpleName());
System.out.println(
        quantities.getMapValueTypeDescriptor().getType().getSimpleName());
~~~

Kết quả:

~~~text
String
Integer
~~~

Spring có metadata để chuyển key và value theo kiểu đích riêng. Nếu một generic branch không được khai báo, hãy kiểm tra descriptor con trước khi truy cập.

## 5. Annotation metadata trên TypeDescriptor

Annotation có thể mô tả quy ước của một field. Ví dụ ứng dụng định nghĩa @UppercaseCode để yêu cầu chuẩn hóa mã thành chữ hoa.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
public @interface UppercaseCode {
}
~~~

Gắn vào field:

~~~java
public class ProductForm {
    @UppercaseCode
    private String productCode;

    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) {
        this.productCode = productCode;
    }
}
~~~

Đọc annotation qua descriptor:

~~~java
Field field = ProductForm.class.getDeclaredField("productCode");
TypeDescriptor descriptor = new TypeDescriptor(field);

boolean enabled = descriptor.hasAnnotation(UppercaseCode.class);
UppercaseCode annotation =
        descriptor.getAnnotation(UppercaseCode.class);

System.out.println(enabled);
System.out.println(annotation != null);
~~~

Kết quả là true và true. Cần RetentionPolicy.RUNTIME nếu converter đọc annotation qua reflection lúc chạy.

### 5.1. Annotation trên field và trên type argument

Annotation @UppercaseCode với target FIELD trên List<String> mô tả thuộc tính collection; nó không tự động trở thành annotation trên từng phần tử String. Nếu muốn annotation gắn trực tiếp vào type argument, cần khai báo @Target(ElementType.TYPE_USE) và dùng cú pháp List<@UppercaseCode String>. Sau đó kiểm tra descriptor/ResolvableType tương ứng trên phiên bản Spring cụ thể để xác nhận metadata ở đúng cấp.

## 6. GenericConverter và ConditionalGenericConverter

Converter<S,T> đủ dùng khi quy tắc chỉ cần kiểu nguồn và kiểu đích cố định. Khi cần generic metadata hoặc annotation, Spring cung cấp GenericConverter:

~~~java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

getConvertibleTypes() khai báo các cặp raw source/target hỗ trợ. convert(...) nhận descriptor của lần gọi cụ thể để biết generic và annotation khi metadata có sẵn.

ConditionalGenericConverter bổ sung matches(sourceType, targetType) để converter chỉ được chọn khi điều kiện metadata phù hợp.

Ví dụ converter chuẩn hóa String ở target có annotation @UppercaseCode:

~~~java
import java.util.Locale;
import java.util.Set;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;

public final class UppercaseCodeConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(String.class, String.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType, TypeDescriptor targetType) {
        return targetType.hasAnnotation(UppercaseCode.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        if (source == null) {
            return null;
        }
        return source.toString().trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là class tích hợp cần đăng ký vào registry phù hợp; annotation và ProductForm phải nằm trong dự án. Cặp String -> String rất rộng nên điều kiện matches là thiết yếu. Test cả target có annotation lẫn target thông thường để bảo đảm converter không chiếm đường conversion không liên quan.

| SPI | Khi dùng |
| --- | --- |
| Converter<S,T> | Cặp kiểu cố định, không cần generic/annotation |
| ConverterFactory<S,R> | Một nguồn chuyển thành nhiều kiểu đích cùng họ |
| GenericConverter | Cần TypeDescriptor hoặc nhiều cặp kiểu |
| ConditionalGenericConverter | Cần điều kiện dựa trên annotation/metadata |
| Formatter<T> | Cần parse/print theo Locale |

Chọn SPI ít phức tạp nhất diễn đạt đúng yêu cầu. Không cần GenericConverter nếu Converter đơn giản đã đủ.

## 7. Chuyển collection bằng source/target descriptors

ConversionService có overload nhận source và target descriptor:

~~~java
Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Ví dụ chuyển List<String> sang List<Integer>:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

TypeDescriptor source = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor target = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(
        List.of("12", "34"), source, target);

System.out.println(converted);
~~~

Kết quả với conversion service mặc định:

~~~text
[12, 34]
~~~

Nếu collection có phần tử như abc không parse được thành Integer, phép chuyển đổi có thể thất bại; đừng giả định Spring âm thầm bỏ qua phần tử lỗi.

### 7.1. Chuyển Map key và value

~~~java
TypeDescriptor sourceMap = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(String.class),
        TypeDescriptor.valueOf(String.class));
TypeDescriptor targetMap = TypeDescriptor.map(
        Map.class,
        TypeDescriptor.valueOf(Long.class),
        TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(
        Map.of("100", "7"), sourceMap, targetMap);
~~~

Spring có đủ metadata để chuyển key String -> Long và value String -> Integer. Trong thực tế, xác định kiểu map đích và xử lý khả năng key collision.

## 8. TypeDescriptor trong data binding

Spring MVC dùng conversion service khi bind request values vào model attribute. Khi target property là List<Integer>, descriptor của property có thể cung cấp element type để Spring chuyển từng phần tử.

~~~java
public class OrderForm {
    private List<Integer> quantities;

    public List<Integer> getQuantities() { return quantities; }
    public void setQuantities(List<Integer> quantities) {
        this.quantities = quantities;
    }
}
~~~

TypeDescriptor là metadata cho chuyển đổi, không phải validator. Nó không thay @Valid, không kiểm tra business rules, không quyết định authorization và không định nghĩa đầy đủ schema request.

@RequestBody JSON đi qua HTTP message converter/JSON mapper. Đừng mặc định custom converter phục vụ form binding cũng điều khiển JSON deserialization.

## 9. Khi metadata thiếu hoặc generic không resolve

Raw collection:

~~~java
List rawValues;
~~~

Không có generic element được khai báo. Với wildcard:

~~~java
List<? extends Number> values;
~~~

Kiểu phần tử không phải một class concrete đơn giản. ResolvableType hỗ trợ phân tích generic structure, nhưng converter vẫn cần quyết định cách xử lý wildcard/type variable chưa resolve.

Nguyên tắc:

1. Null-check element/key/value descriptor trước khi sử dụng.
2. Không đoán element type từ phần tử đầu tiên của collection.
3. Nếu caller cần generic type mà source không có metadata, yêu cầu cung cấp descriptor tường minh.
4. Dùng getResolvableType() để khảo sát cấu trúc generic.
5. Không coi annotation vắng mặt là annotation mặc định.
6. Với generic lồng nhau, kiểm tra từng cấp.
7. Collection rỗng không tiết lộ element type; metadata phải đến từ field/parameter hoặc caller.

TypeDescriptor.forObject(value) phù hợp khi chỉ cần runtime type. Nó không thay thế descriptor từ khai báo khi cần generic/annotation.

## 10. Ví dụ Java 17+ chạy độc lập

Ví dụ dùng Java 17+ và Spring Core 6.2.12. Chương trình đọc generic/annotation từ field rồi chuyển List<String> thành List<Integer>.

settings.gradle:

~~~groovy
rootProject.name = 'type-descriptor-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.12'
}

application {
    mainClass = 'TypeDescriptorDemo'
}
~~~

src/main/java/TypeDescriptorDemo.java:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.util.List;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public class TypeDescriptorDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface NormalizeCode {
    }

    public static class Sample {
        @NormalizeCode
        private List<String> codes;

        private List<List<String>> matrix;
    }

    public static void main(String[] args) throws Exception {
        Field codesField = Sample.class.getDeclaredField("codes");
        TypeDescriptor codes = new TypeDescriptor(codesField);

        Field matrixField = Sample.class.getDeclaredField("matrix");
        TypeDescriptor matrix = new TypeDescriptor(matrixField);
        TypeDescriptor row = matrix.getElementTypeDescriptor();

        System.out.println("raw=" + codes.getType().getSimpleName());
        System.out.println("element="
                + codes.getElementTypeDescriptor().getType().getSimpleName());
        System.out.println("annotation="
                + codes.hasAnnotation(NormalizeCode.class));
        System.out.println("nested="
                + row.getElementTypeDescriptor().getType().getSimpleName());

        DefaultConversionService service =
                new DefaultConversionService();
        TypeDescriptor target = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Integer.class));

        Object converted = service.convert(
                List.of("12", "34"), codes, target);

        System.out.println("converted=" + converted);
    }
}
~~~

Chạy với JDK 17+ và Gradle:

~~~bash
gradle -q run
~~~

Có Gradle Wrapper thì dùng ./gradlew -q run trên Linux/macOS hoặc gradlew.bat -q run trên Windows. Khi dependency chưa có cache, môi trường cần truy cập Maven Central.

Stdout mong đợi:

~~~text
raw=List
element=String
annotation=true
nested=String
converted=[12, 34]
~~~

codes descriptor lấy từ field nên chứa element type và annotation. Target descriptor được tạo tường minh là List<Integer>. Annotation NormalizeCode chỉ minh họa metadata; conversion demo không tự áp dụng quy tắc uppercase. Khả năng đọc metadata và việc converter thực sự sử dụng metadata là hai việc riêng.

## 11. Lỗi thường gặp

**Chỉ dùng List.class rồi mong Spring biết element type.** Raw class không giữ generic argument. Tạo descriptor từ field/parameter hoặc dùng TypeDescriptor.collection.

**Dùng forObject để khôi phục generic.** Runtime object không tự lưu generic signature sau type erasure. Giữ descriptor từ khai báo hoặc truyền tường minh.

**Annotation không có runtime retention.** Muốn đọc bằng reflection, chọn RetentionPolicy.RUNTIME.

**Nhầm annotation container với annotation element.** List<@A String> khác @A List<String>. Khai báo target annotation đúng và test descriptor ở đúng cấp.

**GenericConverter match quá rộng.** Cặp String -> String phổ biến; dùng matches để giới hạn target descriptor, rồi test negative path.

**Không null-check descriptor con.** Raw/wildcard generic có thể không có element descriptor cụ thể.

**Dùng TypeDescriptor thay validation.** Metadata giúp chọn conversion; constraint và nghiệp vụ cần validator riêng.

**Giả định phần tử lỗi luôn bị bỏ qua.** Conversion collection có thể thất bại toàn phép chuyển đổi. Partial success cần logic tường minh.

**Không xét map key collision.** Hai key text có thể cùng thành một key sau conversion. Xác định chính sách trước khi ghi dữ liệu.

**Bỏ qua nguồn metadata.** Descriptor từ Field giữ generic/annotation; descriptor từ raw class thì không có cùng thông tin.

## 12. Checklist áp dụng

1. Quy tắc chỉ cần class hay cần generic/annotation?
2. Source descriptor đến từ Field/parameter hay runtime object?
3. Target descriptor có element/key/value type đầy đủ?
4. Descriptor con có thể null không?
5. Raw type, wildcard và generic lồng nhau được xử lý ra sao?
6. Annotation đặt ở FIELD, PARAMETER hay TYPE_USE? Retention có phải RUNTIME?
7. matches có giới hạn đủ hẹp?
8. Collection/map conversion có xử lý lỗi và key collision rõ?
9. Conversion có bị nhầm với validation hoặc JSON deserialization?
10. Có test collection, map, nested generic, empty collection và phần tử sai?
11. Có test target có và không có annotation?
12. Đã kiểm tra Javadoc đúng phiên bản Spring của ứng dụng?

## 13. Tài liệu chính thức

- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [TypeDescriptor Javadoc (Spring 6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [GenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [ConditionalGenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/ResolvableType.html)
- [Java Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)
- [Java Reflection Field API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6)

**Điều cốt lõi:** TypeDescriptor cho Spring biết nhiều hơn raw Class: generic element/key/value và annotation metadata khi nguồn khai báo cung cấp chúng. Hãy giữ metadata từ field/parameter hoặc tạo descriptor tường minh; dùng GenericConverter khi quy tắc thực sự phụ thuộc metadata, và luôn kiểm tra trường hợp generic chưa resolve.
