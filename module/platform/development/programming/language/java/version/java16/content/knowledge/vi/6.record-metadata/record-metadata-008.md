# Phân biệt annotation trên component với annotation trên kiểu dữ liệu

Trong record header, annotation có thể mô tả **chính record component** hoặc mô tả **kiểu dữ liệu của component**. Hai annotation này đôi khi được viết ở cùng một vị trí cú pháp, nhưng Java phân biệt chúng dựa trên `@Target` của annotation type.

Sự khác nhau ảnh hưởng trực tiếp đến cách đọc metadata:

- Annotation áp dụng cho record component declaration được đọc bằng `RecordComponent.getAnnotation(...)`.
- Annotation áp dụng cho kiểu dữ liệu được đọc qua `RecordComponent.getAnnotatedType()` và các API `AnnotatedType` tương ứng.

Nếu một annotation có cả target `RECORD_COMPONENT` và `TYPE_USE`, annotation ở vị trí đó có thể đồng thời áp dụng cho declaration và kiểu gần nhất. Vì vậy, cần kiểm tra đúng cả hai bề mặt metadata khi thiết kế thư viện hoặc công cụ phân tích record.

Bài học thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**, tập trung vào các API annotation và reflection chính thức từ Java 16, vẫn áp dụng trong Java hiện đại.

## 1. Hai khái niệm: declaration annotation và type-use annotation

Xét khai báo:

```java
record Customer(String name) {}
```

Record component `name` có hai khía cạnh:

1. **Declaration:** đây là component có tên `name` trong record header.
2. **Type:** kiểu khai báo của component là `String`.

Annotation gắn tại vị trí trước kiểu có thể áp dụng cho một trong hai khía cạnh, tùy theo target:

| Loại annotation | Target | Nó mô tả | Reflection API |
| --- | --- | --- | --- |
| Declaration annotation | `ElementType.RECORD_COMPONENT` | Component declaration | `RecordComponent.getAnnotation(...)` |
| Type-use annotation | `ElementType.TYPE_USE` | Kiểu dữ liệu của component | `RecordComponent.getAnnotatedType()` |
| Cả hai | `RECORD_COMPONENT` và `TYPE_USE` | Declaration và kiểu gần nhất | Đọc qua cả hai API |

Đây là quy tắc của Java Language Specification về vị trí annotation. Cú pháp đặt annotation trước kiểu không tự quyết định annotation thuộc declaration hay type; khả năng áp dụng của annotation type mới là yếu tố quyết định.

## 2. Annotation chỉ dành cho record component

Nếu muốn mô tả component như một trường dữ liệu trong schema, khai báo annotation với target `RECORD_COMPONENT`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DisplayLabel {
    String value();
}
```

Áp dụng:

```java
record Customer(
        @DisplayLabel("Mã khách hàng") String code,
        @DisplayLabel("Tên khách hàng") String name
) {}
```

Đọc metadata:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component : Customer.class.getRecordComponents()) {
    DisplayLabel label = component.getAnnotation(DisplayLabel.class);
    System.out.println(component.getName() + " -> " + label.value());
}
```

Kết quả:

```text
code -> Mã khách hàng
name -> Tên khách hàng
```

`DisplayLabel` mô tả ý nghĩa của component. Nó không phải annotation của kiểu `String`, vì target không bao gồm `TYPE_USE`. Do đó, không tìm annotation này bằng `component.getAnnotatedType().getAnnotation(DisplayLabel.class)`.

## 3. Annotation chỉ dành cho kiểu dữ liệu

Khi cần đánh dấu kiểu, khai báo `@Target(ElementType.TYPE_USE)`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Sensitive {}
```

Áp dụng lên kiểu component:

```java
record Account(@Sensitive String secret) {}
```

Ở đây, `@Sensitive` áp dụng cho kiểu `String` của component. Nó không phải annotation declaration của record component. Vì vậy:

- `component.getAnnotation(Sensitive.class)` trả về `null`.
- `component.getAnnotatedType().getAnnotation(Sensitive.class)` trả về annotation `Sensitive`.

Ví dụ đọc đúng vị trí:

```java
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

public class TypeUseReadDemo {
    public static void main(String[] args) {
        RecordComponent component =
                Account.class.getRecordComponents()[0];

        AnnotatedType annotatedType = component.getAnnotatedType();
        Sensitive annotation =
                annotatedType.getAnnotation(Sensitive.class);

        System.out.println(component.getAnnotation(Sensitive.class));
        System.out.println(annotation != null);
    }
}
```

Kết quả:

```text
null
true
```

`RecordComponent.getAnnotatedType()` trả về đối tượng `AnnotatedType` mô tả kiểu cùng các annotation gắn lên kiểu đó. Nếu chỉ dùng `getType()`, ta nhận được `Class<?>` và không có API để đọc type-use annotation từ đối tượng `Class` này.

## 4. Một annotation có thể áp dụng đồng thời cho declaration và type

Theo JLS `9.7.4, nếu annotation type áp dụng được cả trong record component declaration context và type context, annotation tại vị trí cú pháp đó được xem là áp dụng cho **cả hai**.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;

public class DualTargetAnnotationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.TYPE_USE
    })
    @interface Metadata {
        String value();
    }

    record User(@Metadata("user-name") String name) {}

    public static void main(String[] args) {
        RecordComponent component =
                User.class.getRecordComponents()[0];

        Metadata declarationAnnotation =
                component.getAnnotation(Metadata.class);
        Metadata typeAnnotation =
                component.getAnnotatedType().getAnnotation(Metadata.class);

        System.out.println(declarationAnnotation.value());
        System.out.println(typeAnnotation.value());
    }
}
```

Kết quả:

```text
user-name
user-name
```

Hai lời gọi đọc cùng một annotation type nhưng ở hai context khác nhau:

- `getAnnotation(Metadata.class)` đọc annotation của record component declaration.
- `getAnnotatedType().getAnnotation(Metadata.class)` đọc annotation của kiểu component.

Điều này không có nghĩa Reflection tự động hợp nhất hai metadata. Mỗi API vẫn phản ánh đúng vị trí mà nó đại diện. Nếu annotation chỉ có một target, chỉ context tương ứng mới nhận annotation.

## 5. `getType()`, `getGenericType()` và `getAnnotatedType()`

Ba API này liên quan đến kiểu component nhưng cung cấp các lớp thông tin khác nhau:

| API | Kiểu trả về | Thông tin |
| --- | --- | --- |
| `RecordComponent.getType()` | `Class<?>` | Kiểu runtime sau type erasure |
| `RecordComponent.getGenericType()` | `Type` | Kiểu khai báo, bao gồm cấu trúc generic nếu có |
| `RecordComponent.getAnnotatedType()` | `AnnotatedType` | Cấu trúc kiểu khai báo cùng annotation trên các vị trí kiểu |

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.util.List;

public class AnnotatedGenericTypeDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Sensitive {}

    record Document(List<@Sensitive String> labels) {}

    public static void main(String[] args) {
        RecordComponent component =
                Document.class.getRecordComponents()[0];

        System.out.println(component.getType().getTypeName());

        Type genericType = component.getGenericType();
        System.out.println(genericType.getTypeName());

        AnnotatedParameterizedType annotatedType =
                (AnnotatedParameterizedType) component.getAnnotatedType();
        Type argumentType =
                annotatedType.getAnnotatedActualTypeArguments()[0].getType();
        boolean sensitive = annotatedType
                .getAnnotatedActualTypeArguments()[0]
                .isAnnotationPresent(Sensitive.class);

        System.out.println(argumentType.getTypeName());
        System.out.println(sensitive);
    }
}
```

Kết quả:

```text
java.util.List
java.util.List<java.lang.String>
java.lang.String
true
```

Ta có thể đọc được:

- `getType()` chỉ cho biết raw type là `List`.
- `getGenericType()` giữ cấu trúc `List<String>` nhưng không cung cấp API đọc annotation.
- `getAnnotatedType()` cho phép duyệt vào tham số `String` và đọc `@Sensitive` trên kiểu đó.

Khi làm schema hoặc framework validation, đây là điểm rất quan trọng: biết kiểu generic và biết annotation trên từng vị trí generic là hai yêu cầu khác nhau.

## 6. Đọc annotation trong generic lồng nhau

Với kiểu generic lồng nhau:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;
import java.util.List;
import java.util.Map;

public class NestedGenericTypeUseDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Sensitive {}

    record SearchIndex(
            Map<String, List<@Sensitive String>> tagsByLanguage
    ) {}

    public static void main(String[] args) {
        RecordComponent component =
                SearchIndex.class.getRecordComponents()[0];

        AnnotatedParameterizedType mapType =
                (AnnotatedParameterizedType) component.getAnnotatedType();

        // Map có hai tham số: key String và value List<@Sensitive String>.
        AnnotatedType valueType =
                mapType.getAnnotatedActualTypeArguments()[1];

        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) valueType;

        AnnotatedType elementType =
                listType.getAnnotatedActualTypeArguments()[0];

        boolean sensitive =
                elementType.isAnnotationPresent(Sensitive.class);

        System.out.println(sensitive); // true
    }
}
```

Không nên chỉ kiểm tra annotation ở lớp ngoài cùng. `SearchIndex` có component kiểu `Map`, nên `component.getAnnotatedType().getAnnotation(Sensitive.class)` trả về `null` trong ví dụ này; annotation nằm trên kiểu phần tử của danh sách lồng bên trong.

### Các dạng cấu trúc kiểu khác

Tùy khai báo component, `AnnotatedType` có thể là một trong các dạng:

| Kiểu | Dùng để phân tích |
| --- | --- |
| `AnnotatedType` | Kiểu đơn giản hoặc kiểu tổng quát |
| `AnnotatedParameterizedType` | Kiểu generic có tham số, ví dụ `List<String>` |
| `AnnotatedArrayType` | Kiểu mảng và kiểu component của mảng |
| `AnnotatedWildcardType` | Wildcard, ví dụ `? extends Number` |
| `AnnotatedTypeVariable` | Biến kiểu, ví dụ `T extends CharSequence` |

Với mảng, `AnnotatedArrayType.getAnnotatedGenericComponentType()` giúp đọc annotation trên kiểu phần tử. Với wildcard và biến kiểu, dùng các phương thức lấy annotated bound tương ứng. Mỗi tầng có thể mang annotation riêng, vì vậy cần duyệt đến đúng vị trí cần kiểm tra.

## 7. Annotation trên kiểu mảng: vị trí cũng quan trọng

Type-use annotation có thể đánh dấu kiểu mảng, từng chiều mảng hoặc kiểu phần tử. Ví dụ:

Hai vị trí không hoàn toàn giống nhau:

- `@Sensitive String[]` đặt annotation trên kiểu phần tử `String`.
- `String @Sensitive []` đặt annotation trên kiểu mảng.

Có thể đọc cấu trúc bằng `AnnotatedArrayType`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

public class AnnotatedArrayTypeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Sensitive {}

    record Asset(
            @Sensitive String[] secretNames,
            String @Sensitive [] protectedArray
    ) {}

    public static void main(String[] args) {
        RecordComponent[] components = Asset.class.getRecordComponents();

        AnnotatedArrayType first =
                (AnnotatedArrayType) components[0].getAnnotatedType();
        AnnotatedArrayType second =
                (AnnotatedArrayType) components[1].getAnnotatedType();

        AnnotatedType firstElement =
                first.getAnnotatedGenericComponentType();

        System.out.println(
                firstElement.isAnnotationPresent(Sensitive.class));
        System.out.println(
                second.isAnnotationPresent(Sensitive.class));
    }
}
```

Kết quả lần lượt là `true` và `true`, nhưng annotation nằm ở hai tầng khác nhau. Nếu cần xác định chính xác annotation đánh dấu phần tử hay mảng, hãy kiểm tra cả `AnnotatedArrayType` và `getAnnotatedGenericComponentType()`.

## 8. Annotation type không khai báo target

Trong Java hiện đại, nếu annotation interface không có `@Target`, annotation có thể được dùng trong các declaration context, nhưng không được xem là áp dụng trong type contexts. Vì vậy, không dựa vào việc bỏ `@Target` để đánh dấu kiểu dữ liệu.

Muốn annotation được áp dụng cho kiểu dữ liệu, hãy khai báo `ElementType.TYPE_USE` rõ ràng. Muốn đọc annotation ở component declaration, khai báo `ElementType.RECORD_COMPONENT`. Nếu cần cả hai, liệt kê cả hai:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.TYPE_USE
})
@interface ComponentAndType {}
```

Khi đọc metadata, đừng suy luận target từ tên annotation hoặc vị trí đặt trong mã nguồn. Hãy xem định nghĩa annotation type và gọi đúng API Reflection.

## 9. Annotation propagation và API đọc metadata

Annotation trên component có thể được áp dụng cho các thành phần liên quan nếu target của annotation phù hợp với context đích. Điều này có thể xảy ra với field component, accessor ngầm định và formal parameter của canonical constructor ngầm định hoặc compact constructor.

Đối với declaration annotation:

| Vị trí | API đọc declaration annotation |
| --- | --- |
| Component | `RecordComponent.getAnnotation(...)` |
| Field | `Field.getAnnotation(...)` |
| Accessor | `Method.getAnnotation(...)` |
| Constructor parameter | `Parameter.getAnnotation(...)` |

Đối với type-use annotation:

| Vị trí | API đọc type annotation |
| --- | --- |
| Kiểu component | `RecordComponent.getAnnotatedType()` |
| Kiểu field | `Field.getAnnotatedType()` |
| Kiểu trả về accessor | `Method.getAnnotatedReturnType()` |
| Kiểu tham số constructor | `Parameter.getAnnotatedType()` |

Accessor tường minh và normal canonical constructor tường minh có quy tắc riêng: annotation component không tự động lan truyền sang các khai báo tường minh đó. Nếu cần annotation ở những vị trí ấy, hãy khai báo trực tiếp trên method hoặc formal parameter. Với type-use annotation, cũng cần đọc đúng annotated type của khai báo tương ứng.

## 10. Retention: điều kiện để Reflection đọc annotation

Target xác định vị trí annotation được áp dụng. Retention xác định annotation có được giữ lại để đọc ở runtime hay không.

| Retention | Hành vi |
| --- | --- |
| `SOURCE` | Chỉ có trong mã nguồn; không có trong class file |
| `CLASS` | Có trong class file nhưng không đọc được qua runtime Reflection |
| `RUNTIME` | Có thể đọc bằng Reflection khi chương trình chạy |

Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`. Vì vậy, annotation dùng cho reflection metadata cần khai báo:

```java
@Retention(RetentionPolicy.RUNTIME)
```

Khi `getAnnotation(...)` hoặc `getAnnotatedType().getAnnotation(...)` trả về `null`, hãy kiểm tra cả target và retention trước khi kết luận annotation không tồn tại.

## 11. Các lỗi thường gặp

**Dùng `RecordComponent.getAnnotation()` để đọc type-use annotation**

API này đọc annotation của component declaration. Với annotation trên kiểu, dùng `getAnnotatedType()`.

**Dùng `getAnnotatedType().getAnnotation()` để đọc declaration annotation**

Annotation declaration nằm trên `RecordComponent`. Hãy dùng `component.getAnnotation(...)`.

**Cho rằng annotation đặt trước tên component luôn là annotation của component**

Vị trí cú pháp có thể tương ứng với declaration, type hoặc cả hai. `@Target` xác định annotation áp dụng ở context nào.

**Cho rằng `getType()` giữ annotation**

`getType()` trả về `Class<?>` sau type erasure. Dùng `AnnotatedType` để đọc annotation trên kiểu.

**Chỉ kiểm tra kiểu generic ngoài cùng**

Annotation có thể nằm ở tham số generic hoặc kiểu lồng sâu hơn. Duyệt `AnnotatedParameterizedType` đến đúng tầng.

**Quên retention runtime**

Annotation có target phù hợp nhưng retention `CLASS` hoặc `SOURCE` vẫn không đọc được bằng Reflection lúc chạy.

## 12. Bài tập tự kiểm tra

Cho annotation và record:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Confidential {}

@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.TYPE_USE
})
@interface Both {
    String value();
}

record Employee(
        @Label("Mã nhân viên") String id,
        @Confidential String secret,
        @Both("Tên hiển thị") String displayName,
        List<@Confidential String> aliases
) {}
```

Hãy xác định:

1. Annotation `Label` của component `id` được đọc bằng API nào?
2. Annotation `Confidential` trên kiểu `String` của `secret` được đọc bằng API nào?
3. `component.getAnnotation(Confidential.class)` có tìm thấy annotation của `secret` không?
4. Annotation `Both` của `displayName` có thể đọc ở những vị trí nào?
5. Làm thế nào để kiểm tra annotation `Confidential` trên phần tử `String` của `aliases`?
6. Vì sao `getType()` không đủ để kiểm tra câu 5?

**Đáp án:**

1. `RecordComponent.getAnnotation(Label.class)`.
2. `RecordComponent.getAnnotatedType().getAnnotation(Confidential.class)`.
3. Không. `Confidential` chỉ có target `TYPE_USE`, không áp dụng cho record component declaration.
4. Cả `component.getAnnotation(Both.class)` và `component.getAnnotatedType().getAnnotation(Both.class)` đều đọc được vì annotation có cả hai target.
5. Lấy `AnnotatedParameterizedType` từ `component.getAnnotatedType()` rồi gọi `getAnnotatedActualTypeArguments()[0].isAnnotationPresent(Confidential.class)`.
6. `getType()` chỉ trả về `Class<?>` của raw type `List`, không giữ annotation trên tham số kiểu `String`.

## Ghi nhớ

**Annotation trên component mô tả declaration; annotation trên kiểu mô tả type use.** Dùng `RecordComponent.getAnnotation(...)` để đọc declaration annotation và `RecordComponent.getAnnotatedType()` để đọc annotation trên kiểu. Nếu annotation có cả target `RECORD_COMPONENT` và `TYPE_USE`, nó có thể áp dụng đồng thời cho cả hai. Với generic hoặc mảng, hãy duyệt cấu trúc `AnnotatedType` đến đúng vị trí; `getType()` và `getGenericType()` không thay thế việc đọc annotated type.

## Tài liệu tham khảo

- [Java Language Specification — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4)
- [Java Language Specification — Record Components](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.1)
- [Oracle Java SE API — RecordComponent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE API — AnnotatedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Oracle Java SE API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Oracle Java SE API — AnnotatedArrayType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [Oracle Java SE API — ElementType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)
