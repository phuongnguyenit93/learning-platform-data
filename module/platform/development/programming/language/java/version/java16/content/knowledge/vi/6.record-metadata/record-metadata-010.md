# Kiểm thử metadata, annotation và record không có component

Khi viết thư viện hoặc công cụ dùng Java Reflection để xử lý record, chỉ kiểm tra một record có vài component là chưa đủ. Bộ kiểm thử cần xác nhận thứ tự component, kiểu dữ liệu, accessor, canonical constructor, annotation ở đúng vị trí và các trường hợp biên như record không có component.

Một điểm dễ nhầm là **record rỗng vẫn là record**. Với `record EmptyRecord() {}`, `Class.isRecord()` trả về `true` và `getRecordComponents()` trả về mảng rỗng. Với một lớp thông thường, `isRecord()` trả về `false` và `getRecordComponents()` trả về `null`. Hai kết quả này mang ý nghĩa khác nhau và cần được kiểm thử riêng.

Bài học thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**. Các API record và reflection được giới thiệu chính thức từ Java 16 và vẫn dùng trong Java hiện đại. Ví dụ kiểm thử dùng JUnit Jupiter API, một lựa chọn phổ biến để kiểm tra mã Java; các bài kiểm tra không phụ thuộc vào thứ tự entry trong collection hoặc tên tham số constructor được lưu trong bytecode.

## 1. Những hành vi metadata cần kiểm thử

Với một record:

```java
record Person(String name, int age) {}
```

Có thể kiểm tra các hành vi sau:

| Hành vi | API | Điều cần xác nhận |
| --- | --- | --- |
| Nhận diện record | `Class.isRecord()` | Trả về `true` với record |
| Đọc component | `Class.getRecordComponents()` | Trả về mảng theo thứ tự record header |
| Đọc tên component | `RecordComponent.getName()` | Tên khớp với khai báo |
| Đọc kiểu component | `RecordComponent.getType()` | Kiểu `Class<?>` khớp, kể cả kiểu nguyên thủy |
| Đọc accessor | `RecordComponent.getAccessor()` | Accessor đúng tên, không có tham số và có kiểu trả về tương ứng |
| Tìm canonical constructor | `Class.getDeclaredConstructor(...)` | Chữ ký có kiểu và thứ tự tương ứng với component |
| Đọc annotation | `getAnnotation(...)` | Annotation xuất hiện ở đúng declaration context |
| Đọc annotation trên kiểu | `getAnnotatedType()` | Annotation type-use được đọc từ đúng tầng kiểu |
| Record không component | `getRecordComponents()` | Trả về mảng không null có độ dài bằng 0 |

Một bộ kiểm thử tốt nên xác nhận cả kết quả đúng lẫn các trường hợp không được phép nhầm lẫn.

## 2. Phân biệt record rỗng và kiểu không phải record

Hai khai báo sau khác nhau:

```java
record EmptyRecord() {}

class PlainClass {}
```

Kết quả reflection:

| Kiểu | `isRecord()` | `getRecordComponents()` |
| --- | :---: | --- |
| `EmptyRecord.class` | `true` | Mảng rỗng, không phải `null` |
| `PlainClass.class` | `false` | `null` |

Record rỗng vẫn có canonical constructor không tham số. Nó không có accessor component vì không có component nào.

Ví dụ kiểm tra:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;

record EmptyRecord() {}

RecordComponent[] components =
        EmptyRecord.class.getRecordComponents();
Constructor<?> constructor =
        EmptyRecord.class.getDeclaredConstructor();

System.out.println(EmptyRecord.class.isRecord()); // true
System.out.println(components != null);           // true
System.out.println(components.length);            // 0
System.out.println(constructor.getParameterCount()); // 0
```

Không viết logic như sau:

```java
if (type.getRecordComponents().length > 0) {
    // Kết luận đây là record
}
```

Với lớp thường, `getRecordComponents()` trả về `null`, nên truy cập `length` có thể gây `NullPointerException`. Với record rỗng, độ dài bằng `0` nhưng kiểu vẫn là record. Hãy dùng `isRecord()` để nhận diện, rồi mới đọc component:

```java
if (type == null || !type.isRecord()) {
    throw new IllegalArgumentException("Expected a record class");
}

RecordComponent[] components = type.getRecordComponents();
// Với record hợp lệ, components không null; có thể có length == 0.
```

## 3. Kiểm thử thứ tự component, kiểu và accessor

Khai báo một record mẫu:

```java
record Person(String name, int age) {}
```

Kiểm thử cần xác nhận:

- Có đúng hai component.
- Component đầu tiên là `name`, kiểu `String.class`.
- Component thứ hai là `age`, kiểu `int.class`.
- Accessor tương ứng là `name()` và `age()`.
- Accessor không nhận tham số và trả về đúng kiểu component.

Ví dụ:

```java
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

RecordComponent[] components = Person.class.getRecordComponents();

assert components.length == 2;
assert components[0].getName().equals("name");
assert components[0].getType() == String.class;
assert components[1].getName().equals("age");
assert components[1].getType() == int.class;

Method nameAccessor = components[0].getAccessor();
Method ageAccessor = components[1].getAccessor();

assert nameAccessor.getName().equals("name");
assert nameAccessor.getParameterCount() == 0;
assert nameAccessor.getReturnType() == String.class;
assert ageAccessor.getName().equals("age");
assert ageAccessor.getReturnType() == int.class;
```

Các lệnh `assert` của Java chỉ có hiệu lực khi JVM được chạy với tùy chọn `-ea`. Trong bộ kiểm thử tự động, nên dùng assertion của framework kiểm thử để tránh phụ thuộc vào tùy chọn chạy.

## 4. Kiểm thử canonical constructor

Canonical constructor nhận các component theo đúng thứ tự record header. Với `Person`, chữ ký runtime là:

```java
Person(String.class, int.class)
```

Có thể dựng chữ ký từ metadata thay vì ghi cứng:

```java
RecordComponent[] components = Person.class.getRecordComponents();
Class<?>[] parameterTypes = new Class<?>[components.length];

for (int i = 0; i < components.length; i++) {
    parameterTypes[i] = components[i].getType();
}

Constructor<?> constructor =
        Person.class.getDeclaredConstructor(parameterTypes);

assert constructor.getParameterCount() == 2;
assert constructor.getParameterTypes()[0] == String.class;
assert constructor.getParameterTypes()[1] == int.class;
```

Sau khi tìm được constructor, có thể tạo một instance và kiểm tra accessor:

```java
Person person = (Person) constructor.newInstance("Mai", 28);

assert person.name().equals("Mai");
assert person.age() == 28;
```

Kiểm thử này cũng xác nhận rằng kiểu nguyên thủy `int` phải được giữ nguyên trong chữ ký constructor. Không thay `int.class` bằng `Integer.class`.

Không chọn constructor bằng cách lấy phần tử đầu tiên của `getDeclaredConstructors()`: record có thể khai báo overloaded constructor và thứ tự mảng constructor không phải quy tắc nhận diện canonical constructor.

## 5. Kiểm thử annotation ở đúng vị trí

Annotation dùng cho reflection runtime cần có retention `RetentionPolicy.RUNTIME`. Target phải khớp với vị trí mà bài kiểm thử muốn xác nhận.

Ví dụ annotation có thể xuất hiện ở component, field, accessor và tham số canonical constructor:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER
})
@interface Trace {
    String value();
}

record TracedPerson(@Trace("person-name") String name) {}
```

Vì record không tự khai báo accessor hay canonical constructor, các thành phần tương ứng được compiler ngầm khai báo. Annotation có target phù hợp được áp dụng ở các vị trí đó.

Ví dụ đọc từng vị trí:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;

RecordComponent component =
        TracedPerson.class.getRecordComponents()[0];
Field field = TracedPerson.class.getDeclaredField("name");
Method accessor = component.getAccessor();
Constructor<?> constructor =
        TracedPerson.class.getDeclaredConstructor(String.class);
Parameter parameter = constructor.getParameters()[0];

assert component.getAnnotation(Trace.class) != null;
assert field.getAnnotation(Trace.class) != null;
assert accessor.getAnnotation(Trace.class) != null;
assert parameter.getAnnotation(Trace.class) != null;
```

Nếu mục tiêu chỉ là kiểm tra annotation trên component, chỉ cần `RecordComponent.getAnnotation(...)`. Các vị trí field, method và parameter nên được kiểm tra riêng vì chúng là những metadata context khác nhau.

## 6. Kiểm thử declaration annotation và type-use annotation

Một annotation chỉ có target `TYPE_USE` mô tả kiểu dữ liệu, không phải record component declaration:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Sensitive {}

record Account(@Sensitive String secret) {}
```

Kiểm thử đúng:

```java
RecordComponent component =
        Account.class.getRecordComponents()[0];

assert component.getAnnotation(Sensitive.class) == null;
assert component.getAnnotatedType()
        .isAnnotationPresent(Sensitive.class);
```

Nếu annotation có cả hai target `RECORD_COMPONENT` và `TYPE_USE`, annotation đặt ở vị trí component có thể áp dụng đồng thời cho declaration và kiểu:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.TYPE_USE
})
@interface DualTag {}

record TaggedAccount(@DualTag String secret) {}
```

Khi đó, cả hai phép kiểm tra đều phải tìm thấy annotation:

```java
RecordComponent component =
        TaggedAccount.class.getRecordComponents()[0];

assert component.getAnnotation(DualTag.class) != null;
assert component.getAnnotatedType()
        .isAnnotationPresent(DualTag.class);
```

Đây là trường hợp cần kiểm thử cả hai API. Không suy luận vị trí annotation chỉ từ cách viết annotation trước kiểu.

## 7. Kiểm thử annotation trong kiểu generic

Annotation có thể nằm ở tham số kiểu chứ không nằm trên kiểu ngoài cùng. Ví dụ:

```java
import java.util.List;
import java.util.Map;

record SearchIndex(
        List<Map<String, @Sensitive Integer>> entries
) {}
```

Muốn kiểm tra annotation trên `Integer`, cần đi qua cấu trúc `AnnotatedType`:

```java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

RecordComponent component =
        SearchIndex.class.getRecordComponents()[0];

AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) component.getAnnotatedType();
AnnotatedParameterizedType mapType =
        (AnnotatedParameterizedType)
                listType.getAnnotatedActualTypeArguments()[0];
AnnotatedType valueType =
        mapType.getAnnotatedActualTypeArguments()[1];

assert valueType.isAnnotationPresent(Sensitive.class);
```

Chỉ gọi `component.getAnnotatedType().getAnnotation(Sensitive.class)` sẽ không tìm thấy annotation ở tầng generic lồng bên trong. Kiểm thử cần đi đúng đường dẫn tham số kiểu.

Với kiểu generic không có annotation, `getGenericType()` vẫn hữu ích để xác nhận cấu trúc khai báo như `List<Map<String, Integer>>`; còn `getAnnotatedType()` được dùng khi cần kiểm tra annotation trên từng tầng kiểu.

## 8. Kiểm thử retention

Nếu không khai báo `@Retention`, retention mặc định của annotation là `CLASS`. Annotation có thể được lưu trong class file nhưng không đọc được qua runtime Reflection.

Có thể tạo annotation để xác nhận hành vi này:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.RECORD_COMPONENT)
@interface ClassRetentionTag {
    String value();
}

record RetentionSample(@ClassRetentionTag("internal") String name) {}
```

Kiểm thử:

```java
RecordComponent component =
        RetentionSample.class.getRecordComponents()[0];

assert component.getAnnotation(ClassRetentionTag.class) == null;
```

Khi cần đọc annotation lúc runtime, khai báo rõ:

```java
@Retention(RetentionPolicy.RUNTIME)
```

Trong bài kiểm thử, nên phân biệt trường hợp annotation không tồn tại với trường hợp annotation có target đúng nhưng retention không cho phép runtime Reflection đọc nó.

## 9. Bộ kiểm thử tổng hợp bằng JUnit Jupiter

JUnit Jupiter cung cấp assertion và vòng đời test phù hợp cho kiểm thử tự động. Để chạy ví dụ, dự án cần có dependency JUnit Jupiter trong cấu hình test và test runner tương ứng. Mã dưới đây gom các tình huống quan trọng vào một test class.

Lưu thành `RecordMetadataTest.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RecordMetadataTest {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.FIELD,
            ElementType.METHOD,
            ElementType.PARAMETER
    })
    @interface Trace {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.TYPE_USE
    })
    @interface DualTag {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Sensitive {}

    @Target(ElementType.RECORD_COMPONENT)
    @interface ClassRetentionTag {}

    record Person(String name, int age) {}
    record EmptyRecord() {}
    record TracedPerson(@Trace("person-name") String name) {}
    record TaggedAccount(@DualTag String secret) {}
    record Account(@Sensitive String secret) {}
    record SearchIndex(
            List<Map<String, @Sensitive Integer>> entries
    ) {}
    record RetentionSample(
            @ClassRetentionTag String name
    ) {}

    static class PlainClass {}

    @Test
    void identifiesRecordAndOrdinaryClass() {
        assertTrue(Person.class.isRecord());
        assertFalse(PlainClass.class.isRecord());
        assertNull(PlainClass.class.getRecordComponents());
    }

    @Test
    void readsComponentsInDeclarationOrder()
            throws ReflectiveOperationException {
        RecordComponent[] components =
                Person.class.getRecordComponents();

        assertEquals(2, components.length);
        assertEquals("name", components[0].getName());
        assertEquals(String.class, components[0].getType());
        assertEquals("age", components[1].getName());
        assertEquals(int.class, components[1].getType());

        Method nameAccessor = components[0].getAccessor();
        Method ageAccessor = components[1].getAccessor();

        assertEquals("name", nameAccessor.getName());
        assertEquals(0, nameAccessor.getParameterCount());
        assertEquals(String.class, nameAccessor.getReturnType());
        assertEquals("age", ageAccessor.getName());
        assertEquals(int.class, ageAccessor.getReturnType());

        Constructor<?> constructor =
                Person.class.getDeclaredConstructor(
                        String.class, int.class);
        assertEquals(String.class, constructor.getParameterTypes()[0]);
        assertEquals(int.class, constructor.getParameterTypes()[1]);

        Person person = (Person) constructor.newInstance("Mai", 28);
        assertEquals("Mai", nameAccessor.invoke(person));
        assertEquals(28, ageAccessor.invoke(person));
    }

    @Test
    void treatsEmptyRecordAsRecordWithEmptyComponentArray()
            throws ReflectiveOperationException {
        assertTrue(EmptyRecord.class.isRecord());

        RecordComponent[] components =
                EmptyRecord.class.getRecordComponents();
        assertNotNull(components);
        assertEquals(0, components.length);

        Constructor<?> constructor =
                EmptyRecord.class.getDeclaredConstructor();
        assertEquals(0, constructor.getParameterCount());
        assertNotNull(constructor.newInstance());
    }

    @Test
    void readsRuntimeAnnotationAtEachApplicableDeclaration()
            throws ReflectiveOperationException {
        RecordComponent component =
                TracedPerson.class.getRecordComponents()[0];
        Field field = TracedPerson.class.getDeclaredField("name");
        Method accessor = component.getAccessor();
        Constructor<?> constructor =
                TracedPerson.class.getDeclaredConstructor(String.class);
        Parameter parameter = constructor.getParameters()[0];

        assertEquals(
                "person-name",
                component.getAnnotation(Trace.class).value());
        assertEquals(
                "person-name",
                field.getAnnotation(Trace.class).value());
        assertEquals(
                "person-name",
                accessor.getAnnotation(Trace.class).value());
        assertEquals(
                "person-name",
                parameter.getAnnotation(Trace.class).value());
    }

    @Test
    void distinguishesDeclarationAndTypeUseAnnotations() {
        RecordComponent typeUseComponent =
                Account.class.getRecordComponents()[0];
        assertNull(typeUseComponent.getAnnotation(Sensitive.class));
        assertTrue(typeUseComponent.getAnnotatedType()
                .isAnnotationPresent(Sensitive.class));

        RecordComponent dualComponent =
                TaggedAccount.class.getRecordComponents()[0];
        assertNotNull(dualComponent.getAnnotation(DualTag.class));
        assertTrue(dualComponent.getAnnotatedType()
                .isAnnotationPresent(DualTag.class));
    }

    @Test
    void findsAnnotationOnNestedGenericTypeArgument() {
        RecordComponent component =
                SearchIndex.class.getRecordComponents()[0];

        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) component.getAnnotatedType();
        AnnotatedParameterizedType mapType =
                (AnnotatedParameterizedType)
                        listType.getAnnotatedActualTypeArguments()[0];
        AnnotatedType valueType =
                mapType.getAnnotatedActualTypeArguments()[1];

        assertTrue(valueType.isAnnotationPresent(Sensitive.class));
    }

    @Test
    void doesNotExposeClassRetentionAnnotationAtRuntime() {
        RecordComponent component =
                RetentionSample.class.getRecordComponents()[0];
        assertNull(component.getAnnotation(ClassRetentionTag.class));
    }
}
```

Các test trên kiểm tra từng hợp đồng metadata độc lập. Khi thêm record mới vào ứng dụng, có thể bổ sung test tương ứng thay vì chỉ kiểm tra `isRecord()` một lần.

## 10. Ma trận tình huống kiểm thử

| Trường hợp | Kết quả mong đợi | Lỗi cần phát hiện |
| --- | --- | --- |
| Record có nhiều component | Mảng metadata theo thứ tự header | Sắp xếp nhầm theo tên hoặc kiểu |
| Component có kiểu nguyên thủy | `getType()` trả về `int.class`, `long.class`, v.v. | Nhầm primitive với wrapper |
| Record rỗng | `isRecord() == true`, mảng component rỗng | Coi mảng rỗng là không phải record |
| Lớp thường | `isRecord() == false`, component array là `null` | Gọi `.length` trên `null` |
| Annotation declaration runtime | Đọc được bằng `RecordComponent.getAnnotation()` | Sai target hoặc retention |
| Annotation type-use runtime | Đọc được bằng `getAnnotatedType()` | Đọc nhầm qua `getAnnotation()` |
| Annotation có cả hai target | Đọc được ở cả hai context | Chỉ kiểm tra một API |
| Annotation retention mặc định | Không đọc được bằng runtime Reflection | Giả định mặc định là `RUNTIME` |
| Generic lồng nhau | Duyệt đúng các tầng `AnnotatedType` | Chỉ kiểm tra kiểu ngoài cùng |
| Record có overload constructor | Tìm canonical bằng danh sách kiểu component | Chọn constructor theo vị trí trong mảng |

## 11. Các nguyên tắc để bộ kiểm thử bền vững

- **Kiểm tra hợp đồng, không kiểm tra chi tiết compiler không cam kết.** Ví dụ, kiểm tra tên và thứ tự component, không phụ thuộc vào cách compiler sắp xếp các method khác trong lớp.
- **Không dựa vào thứ tự constructor được liệt kê.** Tìm constructor bằng `getDeclaredConstructor(parameterTypes)`.
- **Không dựa vào tên tham số reflection.** Test này không cần tùy chọn biên dịch `-parameters`; chỉ số và kiểu tham số đủ để xác minh chữ ký canonical.
- **Phân biệt null với mảng rỗng.** Lớp thường và record rỗng có kết quả `getRecordComponents()` khác nhau.
- **Đọc annotation ở đúng context.** Dùng `RecordComponent`, `Field`, `Method`, `Parameter` hoặc `AnnotatedType` theo target.
- **Giữ retention runtime cho test Reflection.** Annotation có retention `CLASS` hoặc `SOURCE` không thể được xác minh bằng runtime Reflection như annotation `RUNTIME`.
- **Chạy test bằng JDK 16 trở lên.** Record metadata API không có trong các JDK trước Java 16.

## 12. Bài tập tự kiểm tra

Cho các kiểu:

```java
record Empty() {}
record Pair(String left, String right) {}
class Ordinary {}
```

Hãy trả lời:

1. `Empty.class.isRecord()` trả về gì?
2. `Empty.class.getRecordComponents()` là `null` hay mảng rỗng?
3. `Ordinary.class.getRecordComponents()` trả về gì?
4. `Pair.class.getRecordComponents()[1].getName()` trả về gì?
5. Canonical constructor của `Pair` có thứ tự kiểu tham số nào?
6. Vì sao không nên dùng `getDeclaredConstructors()[0]` để tìm canonical constructor?

**Đáp án:**

1. `true`.
2. Mảng rỗng có độ dài bằng `0`.
3. `null`, vì `Ordinary` không phải record.
4. `"right"`.
5. `String.class`, `String.class`, theo thứ tự `left`, `right`.
6. Vì record có thể có overloaded constructor và thứ tự constructor trong mảng không phải quy tắc nhận diện canonical constructor.

## Ghi nhớ

**Bộ kiểm thử metadata record cần phân biệt record rỗng với lớp thường, xác nhận thứ tự component và constructor, đồng thời đọc annotation ở đúng context.** Record rỗng có `isRecord() == true` và `getRecordComponents()` trả về mảng rỗng; lớp thường có `false` và `null`. Với annotation, kiểm tra target, retention và lựa chọn giữa `RecordComponent.getAnnotation()` với `getAnnotatedType()`. JUnit Jupiter giúp đóng gói các hợp đồng này thành test tự động, dễ chạy lại khi thư viện reflection hoặc mapper thay đổi.

## Tài liệu tham khảo

- [Oracle Java SE API — `Class.isRecord()` và `Class.getRecordComponents()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)
- [Oracle Java SE API — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE API — `AnnotatedType` và `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Oracle Java SE API — `Constructor`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html)
- [Oracle Java SE API — `ElementType` và `RetentionPolicy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)
- [JUnit 5 User Guide — JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/)
- [Java Language Specification — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10)
