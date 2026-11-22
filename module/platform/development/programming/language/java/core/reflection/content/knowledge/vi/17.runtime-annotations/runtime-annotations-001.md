# AnnotatedElement và các đối tượng hỗ trợ annotation trong Java Reflection

Trong Java, annotation là metadata gắn với khai báo hoặc với vị trí sử dụng một kiểu. Reflection có thể đọc các annotation được giữ ở runtime thông qua giao diện **`java.lang.reflect.AnnotatedElement`**. Thay vì mỗi loại đối tượng Reflection có một cách đọc hoàn toàn khác nhau, giao diện này thống nhất các thao tác như `getAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()` và `getAnnotationsByType(...)`.

Bài học trả lời ba câu hỏi: **đối tượng nào triển khai `AnnotatedElement`**, **cách tra cứu annotation chính xác ở runtime**, và **vì sao kết quả thay đổi theo retention, inheritance, repeatable annotation và vị trí annotation**.

## 1. AnnotatedElement là gì?

`AnnotatedElement` là interface thuộc package `java.lang.reflect`. Nó mô tả một phần tử có thể mang annotation và cung cấp API đọc metadata annotation bằng Reflection.

Một số phương thức quan trọng:

```java
<T extends Annotation> T getAnnotation(Class<T> annotationType);
Annotation[] getAnnotations();
<T extends Annotation> T getDeclaredAnnotation(Class<T> annotationType);
Annotation[] getDeclaredAnnotations();
<T extends Annotation> T[] getAnnotationsByType(Class<T> annotationType);
<T extends Annotation> T[] getDeclaredAnnotationsByType(Class<T> annotationType);
boolean isAnnotationPresent(Class<? extends Annotation> annotationType);
```

Đây là các chữ ký **minh họa rút gọn** để học API, không phải đoạn source độc lập để biên dịch. `Annotation` là interface `java.lang.annotation.Annotation`.

Điểm quan trọng:

- Mọi phương thức đọc annotation trả về dữ liệu **có thể quan sát ở runtime**; `@Retention(RetentionPolicy.SOURCE)` và `CLASS` không bảo đảm có thể đọc bằng Reflection runtime.
- `getAnnotation(T.class)` trả **một annotation** thuộc kiểu `T` hoặc `null` nếu kiểu đó không “present” theo định nghĩa API.
- `isAnnotationPresent(T.class)` tương đương về mặt kết quả với `getAnnotation(T.class) != null`.
- `getAnnotations()` trả mảng các annotation “present”. `getDeclaredAnnotations()` chỉ lấy annotation **trực tiếp hiện diện** trên chính phần tử.
- `getAnnotationsByType(T.class)` và `getDeclaredAnnotationsByType(T.class)` hỗ trợ đặc biệt cho **repeatable annotation**: chúng có thể mở container annotation để lấy nhiều phần tử `T`.
- Các mảng annotation trả về có thể được người gọi sửa mà không thay đổi kết quả trả về từ những lần tra cứu khác; đối tượng annotation là immutable và serializable theo hợp đồng API.

Khái niệm “present”, “directly present”, “indirectly present” và “associated” có ý nghĩa kỹ thuật, đặc biệt khi annotation được phép kế thừa hoặc lặp lại. Vì vậy không được coi tất cả các phương thức trên là từ đồng nghĩa.

## 2. Những đối tượng Reflection nào hỗ trợ AnnotatedElement?

Không chỉ `Class<?>`, nhiều đối tượng metadata khác cũng triển khai `AnnotatedElement`:

| Loại đối tượng | Cách lấy ví dụ | Annotation đọc được ở đâu? |
| --- | --- | --- |
| `Class<?>` | `Book.class` | Khai báo class, interface, enum, annotation type hoặc record |
| `Method` | `Book.class.getDeclaredMethod("read")` | Khai báo method |
| `Constructor<?>` | `Book.class.getDeclaredConstructor()` | Khai báo constructor |
| `Field` | `Book.class.getDeclaredField("title")` | Khai báo field |
| `Parameter` | `method.getParameters()[0]` | Khai báo formal parameter |
| `Package` | `Book.class.getPackage()` | Annotation đặt trên package, thường trong `package-info.java` |
| `Module` | `Book.class.getModule()` | Annotation áp dụng cho module declaration |
| `RecordComponent` | `Person.class.getRecordComponents()[0]` | Annotation của record component (Java 16+) |
| `AnnotatedType` và các subtype | `method.getAnnotatedReturnType()` | Annotation ở **vị trí sử dụng kiểu** (type-use) |

`Method` và `Constructor<?>` cùng kế thừa `Executable`; các đối tượng thuộc nhóm này còn có `getParameters()`, `getParameterAnnotations()`, `getAnnotatedParameterTypes()`, `getAnnotatedExceptionTypes()` và API metadata chữ ký khác. `Field` có `getAnnotatedType()` để lấy type-use annotation trên kiểu của field.

Một điểm phân biệt quan trọng: **annotation trên khai báo method** không đồng nhất với **annotation trên kiểu trả về của method**. Cả `Method` lẫn `AnnotatedType` đều là `AnnotatedElement`, nhưng mỗi đối tượng đại diện cho **một vị trí khác nhau** trong source/class file.

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonBlank {}

public @NonBlank String getName() {
    return "Ada";
}
```

Đây là đoạn minh họa cần import `java.lang.annotation.*` và đặt trong một class hợp lệ. `@NonBlank` gắn với **việc dùng kiểu trả về `String`**. Muốn đọc, truy cập:

```java
Method m = SomeClass.class.getDeclaredMethod("getName");
boolean found =
        m.getAnnotatedReturnType().isAnnotationPresent(NonBlank.class);
```

Đây là đoạn minh họa; `SomeClass` phải được thay bằng class chứa `getName`, xử lý checked exception và import `Method`. Nếu chỉ gọi `m.isAnnotationPresent(NonBlank.class)`, bạn đang hỏi về **method declaration**, không phải return type-use annotation.

## 3. Retention và Target quyết định annotation có thể được đọc ở đâu

Một annotation type thường được khai báo với các **meta-annotation**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audit {
    String value();
}
```

Đây là khai báo annotation có thể đặt trong source hợp lệ. `@Target` xác định vị trí cú pháp được phép gắn; `@Retention` xác định mức giữ lại metadata.

| RetentionPolicy | Có trong source | Có trong class file | Reflection runtime tiêu chuẩn đọc được? |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không cần được lưu | Không |
| `CLASS` | Có | Được lưu trong class file | Không phải runtime-visible qua API chuẩn |
| `RUNTIME` | Có | Được lưu | Có, trên đối tượng/phần tử tương ứng |

Nếu **không khai báo `@Retention`**, retention mặc định của annotation type là `CLASS`, không phải `RUNTIME`.

Một số `ElementType` thường gặp: `TYPE`, `METHOD`, `FIELD`, `CONSTRUCTOR`, `PARAMETER`, `PACKAGE`, `MODULE`, `RECORD_COMPONENT`, `TYPE_USE`, `TYPE_PARAMETER` và `ANNOTATION_TYPE`.

Phân biệt `TYPE` (annotation của khai báo kiểu), `TYPE_USE` (annotation của vị trí sử dụng kiểu) và `TYPE_PARAMETER` (annotation của khai báo type parameter như `<@X T>`). Một annotation type có thể khai báo nhiều target. Trong nhiều ngữ cảnh, một annotation `TYPE_USE` xuất hiện cạnh khai báo có thể còn được trình biên dịch xử lý theo quy tắc target liên quan; do đó khi cần quan sát chuẩn xác, hãy kiểm tra đúng đối tượng `AnnotatedElement`, không suy luận chỉ dựa vào chỗ chữ `@` xuất hiện trên dòng.

## 4. Chương trình Java 17+ hoàn chỉnh: Class, Method, Field, Parameter và AnnotatedType

Tạo tệp **`AnnotatedElementDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class AnnotatedElementDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD,
            ElementType.FIELD, ElementType.PARAMETER})
    @interface Label {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Tags.class)
    @interface Tag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Tags {
        Tag[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface NonBlank {
    }

    @Label("base")
    @Role("reader")
    @Tag("red")
    @Tag("blue")
    static class Base {
        @Label("field")
        public String id;

        @Label("method")
        public @NonBlank String read(@Label("argument") String input) {
            return input;
        }
    }

    static class Child extends Base {
    }

    public static void main(String[] args) throws NoSuchMethodException,
            NoSuchFieldException {
        AnnotatedElement element = Base.class;
        System.out.println("base label: "
                + element.getAnnotation(Label.class).value());

        System.out.println("child role: "
                + Child.class.getAnnotation(Role.class).value());
        System.out.println("child declared role: "
                + (Child.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("child label: "
                + (Child.class.getAnnotation(Label.class) != null));

        Tag[] tags = Base.class.getAnnotationsByType(Tag.class);
        System.out.println("expanded tags: " + tags.length);
        System.out.println("single tag lookup: "
                + (Base.class.getAnnotation(Tag.class) != null));
        System.out.println("container present: "
                + (Base.class.getDeclaredAnnotation(Tags.class) != null));

        Method method = Base.class.getDeclaredMethod("read", String.class);
        Field field = Base.class.getDeclaredField("id");
        Parameter parameter = method.getParameters()[0];

        System.out.println("method label: "
                + method.getAnnotation(Label.class).value());
        System.out.println("field label: "
                + field.getAnnotation(Label.class).value());
        System.out.println("parameter label: "
                + parameter.getAnnotation(Label.class).value());

        System.out.println("return type-use annotation: "
                + method.getAnnotatedReturnType()
                        .isAnnotationPresent(NonBlank.class));
        System.out.println("method declaration has NonBlank: "
                + method.isAnnotationPresent(NonBlank.class));

        System.out.println("label retention: "
                + Label.class.getAnnotation(Retention.class).value());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AnnotatedElementDemo.java
java AnnotatedElementDemo
```

Stdout dự kiến:

```text
base label: base
child role: reader
child declared role: false
child label: false
expanded tags: 2
single tag lookup: false
container present: true
method label: method
field label: field
parameter label: argument
return type-use annotation: true
method declaration has NonBlank: false
label retention: RUNTIME
```

Giải thích:

1. `Base.class` có `@Label("base")` nên có thể được gán cho biến kiểu `AnnotatedElement` và gọi `getAnnotation(Label.class)`.
2. `Role` có `@Inherited` và được gắn trên `Base`. `Child.class.getAnnotation(Role.class)` nhận metadata role từ superclass; `Child.class.getDeclaredAnnotation(Role.class)` trả `null` vì `Child` không trực tiếp khai báo nó.
3. `Label` không có `@Inherited`. Vì vậy `Child.class.getAnnotation(Label.class)` là `null` dù `Base` mang nhãn đó.
4. Hai annotation `@Tag` có thể lặp. Compiler lưu chúng qua container `@Tags`; `getAnnotationsByType(Tag.class)` mở container được hai phần tử, trong khi `getAnnotation(Tag.class)` không tự mở container theo cùng cách.
5. `Method`, `Field` và `Parameter` đều là `AnnotatedElement`. Mỗi đối tượng cho annotation trên đúng khai báo mà nó đại diện.
6. `getAnnotatedReturnType()` trả đối tượng `AnnotatedType` có thể mang `@NonBlank`, còn chính khai báo `Method` không mang annotation declaration `NonBlank`.
7. Annotation type `Label.class` cũng là một `Class`, nên Reflection có thể hỏi meta-annotation `@Retention` của chính annotation type; kết quả là enum `RUNTIME`.

Chương trình dùng `getParameters()` để lấy đối tượng `Parameter`. **Không cần tùy chọn `javac -parameters` chỉ để đọc annotation parameter**; tùy chọn đó chủ yếu giúp lưu tên parameter nguồn để `Parameter.getName()` có thể hiển thị đúng tên khai báo thay vì tên tổng hợp.

## 5. Phân biệt getAnnotation và getDeclaredAnnotation

`getAnnotation(T.class)` và `getDeclaredAnnotation(T.class)` khác nhau khi có **annotation được kế thừa trên class**:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("base")
class BaseType {
}

class DerivedType extends BaseType {
}
```

Đây là ví dụ khai báo cần import `java.lang.annotation.*`, không chứa `main`.

Kết quả:

```java
Category inherited = DerivedType.class.getAnnotation(Category.class);
Category direct = DerivedType.class.getDeclaredAnnotation(Category.class);

System.out.println(inherited.value()); // base
System.out.println(direct == null);      // true
```

Mã này chỉ chạy khi đặt trong phương thức có thể truy cập các type đã khai báo. `@Inherited` **không** có nghĩa method, field hoặc interface luôn truyền annotation cho phần tử tương ứng ở class con:

- `@Inherited` chỉ ảnh hưởng cơ chế inheritance annotation **khi phần tử được kiểm tra là class**, theo superclass chain.
- Annotation trên interface không được class implementing “thừa kế” theo `@Inherited`.
- Một method override không tự nhận annotation của method bị override. Nếu công cụ cần fallback lên method lớp cha, phải tự thiết kế bước tra cứu theo chữ ký.
- Field che khuất field khác cũng không được tự gán annotation của field lớp cha.

Nếu một class con có annotation cùng kiểu được khai báo trực tiếp, annotation đó thắng đường inheritance đối với kiểu annotation đó; không cộng gộp tùy ý các khai báo trực tiếp và inherited trong API tra cứu một annotation.

## 6. getAnnotations / getDeclaredAnnotations: tập nào được trả?

`getAnnotations()` trả các annotation “present”; `getDeclaredAnnotations()` chỉ trả những annotation “directly present”. Hai mảng có thể khác nhau khi một class kế thừa annotation được đánh dấu `@Inherited`.

Trong chương trình ở mục 4, `Child.class.getAnnotations()` nhìn thấy `Role` được kế thừa; `Child.class.getDeclaredAnnotations()` không chứa `Role`.

Nếu một annotation type là repeatable, các bản xuất hiện lặp nhiều lần có thể được mã hóa bằng một **container annotation**; khi đó `getAnnotations()` hoặc `getDeclaredAnnotations()` có thể cho bạn **container** chứ không phải từng annotation thành phần. Vì thế khi muốn đọc tất cả `@Tag`, dùng `getAnnotationsByType(Tag.class)` thay vì tự ép mảng `getAnnotations()` sang `Tag[]`.

Không dựa vào thứ tự mảng `getAnnotations()` làm phần cốt lõi của logic chung. Nếu xuất báo cáo hoặc tạo UI, hãy sắp xếp/định danh theo annotation type và thuộc tính có ý nghĩa thay vì phụ thuộc thứ tự tình cờ.

## 7. Repeatable annotation và hai biến thể ByType

Một annotation được lặp lại khi khai báo `@Repeatable(Container.class)` và có container hợp lệ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Flags {
    Flag[] value();
}
```

Đây là snippet độc lập về khai báo annotation type, cần import `java.lang.annotation.*`. Ví dụ sử dụng:

```java
@Flag("fast")
@Flag("verified")
class Task {
}
```

Phân biệt:

| API | Ý nghĩa |
| --- | --- |
| `getAnnotation(Flag.class)` | Tìm một `Flag` “present”; không tự mở container để trả hai `Flag` |
| `getDeclaredAnnotation(Flag.class)` | Tìm một `Flag` trực tiếp hiện diện; không tự mở container |
| `getAnnotationsByType(Flag.class)` | Lấy các `Flag` “associated”, có mở container và có áp dụng inheritance nếu điều kiện thỏa |
| `getDeclaredAnnotationsByType(Flag.class)` | Lấy `Flag` trực tiếp hoặc gián tiếp qua container **trên chính phần tử**, không tìm superclass |

`Task.class.getAnnotationsByType(Flag.class)` và `Task.class.getDeclaredAnnotationsByType(Flag.class)` đều cho hai phần tử trong ví dụ vì cả hai được khai báo trên chính `Task`.

Nếu muốn repeatable annotation **cũng kế thừa** từ superclass, phải thiết kế tương thích `@Inherited` cho annotation thành phần và container theo yêu cầu Java, rồi xét quy tắc “associated”. Đừng giả định đơn giản rằng khi class con có thêm annotation cùng type thì kết quả ByType tự ghép toàn bộ các annotation của superclass: annotation trực tiếp hoặc gián tiếp tại lớp con có thể **che kết quả từ superclass** đối với cùng kiểu annotation.

## 8. Annotation trên declaration khác annotation trên type use

Đây là điểm dễ nhầm nhất vì cả hai được truy cập qua `AnnotatedElement`.

### Annotation khai báo

Một annotation có target `METHOD`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Logged {
}
```

gắn với khai báo method:

```java
@Logged
public String find() {
    return "found";
}
```

Đây là các snippet minh họa cần đặt trong ngữ cảnh class thích hợp. Để đọc, lấy `Method` rồi gọi `method.isAnnotationPresent(Logged.class)`.

### Annotation ở vị trí sử dụng kiểu

Một annotation có target `TYPE_USE`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ImportantType {
}
```

có thể gắn với kiểu trả về, kiểu field, kiểu của parameter, type argument trong generic, array component, wildcard, superclass/interface use tùy cú pháp hợp lệ.

| Vị trí | API phù hợp |
| --- | --- |
| Kiểu trả về method | `Method.getAnnotatedReturnType()` |
| Kiểu của field | `Field.getAnnotatedType()` |
| Kiểu formal parameter | `Executable.getAnnotatedParameterTypes()` |
| Kiểu throws được khai báo | `Executable.getAnnotatedExceptionTypes()` |
| Kiểu superclass | `Class.getAnnotatedSuperclass()` |
| Các kiểu interface | `Class.getAnnotatedInterfaces()` |
| Kiểu parameterized và type arguments | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` |
| Kiểu array có annotation | `AnnotatedArrayType.getAnnotatedGenericComponentType()` |
| Wildcard bounds mang annotation | `AnnotatedWildcardType.getAnnotatedLowerBounds()` / `getAnnotatedUpperBounds()` |

Ví dụ `List<@ImportantType String>` không có nghĩa toàn bộ khai báo `Field` được đánh dấu `@ImportantType`. Để tìm annotation trên **type argument `String`**, cần đi từ `field.getAnnotatedType()`, kiểm tra `AnnotatedParameterizedType`, rồi đọc phần tử `getAnnotatedActualTypeArguments()[0]`. Truy cập đơn thuần `field.getAnnotation(ImportantType.class)` là đang hỏi sai vị trí.

Sự khác biệt còn xuất hiện ở type parameter declaration như `class Box<@Tag T>` nếu `Tag` cho phép `TYPE_PARAMETER`. Khi đó có thể đọc annotation từ `TypeVariable<?>` hoặc vị trí type-use phù hợp theo metadata; không lấy bằng `Box.class.getAnnotation(Tag.class)` và mong đó là annotation của class.

## 9. Package, Module, RecordComponent và annotations ở các vị trí khác

### Package

Package annotation thường được khai báo trong tệp `package-info.java`:

```java
@com.example.annotations.PublicPackage
package com.example.domain;
```

Đây là ví dụ **mô tả cấu trúc**; annotation type phải tồn tại, có `@Target(PACKAGE)` và `@Retention(RUNTIME)` để quan sát runtime qua `Package`. Trong chương trình có class thuộc package:

```java
Package p = SomeDomainClass.class.getPackage();
boolean present = p.isAnnotationPresent(PublicPackage.class);
```

Đây là snippet, không phải chương trình độc lập. `getPackage()` có thể cần xử lý null/điều kiện class loader khi viết công cụ chung, và không nên tìm annotation package bằng cách lấy annotation trên một class bất kỳ trong package.

### Module

`java.lang.Module` triển khai `AnnotatedElement`. Các annotation với target `MODULE` có thể đặt trên module declaration trong `module-info.java` (tuân theo cú pháp). Ví dụ `SomeClass.class.getModule().getAnnotations()` đọc annotation của module, **không phải** của class.

### Record component

`RecordComponent` (Java 16+) là đối tượng Reflection từ `Class.getRecordComponents()`. Nó đại diện cho một **thành phần record**, khác với backing field, accessor method hoặc constructor parameter dù compiler tạo các thành phần liên quan. Nếu muốn xem annotation trên record component, hãy chọn đúng `RecordComponent` và xác định `@Target(RECORD_COMPONENT)`. Java cũng có các quy tắc lan truyền annotation hợp lệ trên các phần tử được suy ra từ record component; công cụ không nên mặc định rằng kết quả khi đọc field, accessor, constructor parameter và record component sẽ luôn giống nhau.

## 10. Các đối tượng annotation và thuộc tính bên trong

Khi có được một annotation:

```java
Label label = Base.class.getAnnotation(Label.class);
String value = label.value();
Class<? extends Annotation> annotationType = label.annotationType();
```

Đây là snippet dùng `Label`/`Base` trong ví dụ mục 4 và import `java.lang.annotation.Annotation`. Annotation instance hiện thực giao diện annotation tương ứng, vì vậy các phần tử như `value()` được gọi như method đọc thuộc tính.

API `Annotation` còn có `annotationType()`, `equals(...)`, `hashCode()` và `toString()`. Không nên dựa vào tên runtime class thực thi annotation; implementation có thể dùng proxy hoặc chi tiết nội bộ JDK. Hãy dựa vào annotation interface và các giá trị attribute được tài liệu hóa.

Một annotation attribute có thể là primitive, String, Class, enum, annotation hoặc mảng của các kiểu hợp lệ. Nếu dùng class file hoặc thư viện thay đổi không đồng bộ, đọc attribute có thể gặp lỗi metadata như `TypeNotPresentException`, `EnumConstantNotPresentException`, `AnnotationTypeMismatchException`, `IncompleteAnnotationException` hoặc `AnnotationFormatError` tùy nguyên nhân. Công cụ xử lý plugin/class file do bên khác cung cấp nên có đường chẩn đoán thích hợp, không coi mọi annotation luôn có cấu trúc hoàn hảo.

## 11. Quy trình khám phá annotation đúng mục tiêu

Khi phát triển framework/validator/documentation generator:

1. **Chọn phần tử:** class, method, constructor, field, parameter, package, module, record component hoặc type-use. Đây là bước quan trọng nhất.
2. **Xác minh retention:** annotation type bạn muốn đọc phải có `@Retention(RUNTIME)`; nếu metadata không runtime-visible, Reflection sẽ không thấy như mong đợi.
3. **Chọn phạm vi:** `getDeclaredAnnotation(s)` nếu chỉ xét trực tiếp; `getAnnotation(s)` nếu muốn semantics “present” và chấp nhận inheritance trên class khi áp dụng.
4. **Chọn số lượng:** với annotation repeatable, dùng `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType` để đọc được các phần tử trong container.
5. **Kiểm tra khai báo hay type-use:** method annotation nằm ở `Method`, còn return type annotation ở `Method.getAnnotatedReturnType()`.
6. **Xét cấu trúc kế thừa:** override method không tự kế thừa annotation method của cha; hãy viết chính sách quét hierarchy nếu framework yêu cầu.
7. **Phân biệt metadata với quyền thực thi:** đọc annotation không tự cấp quyền gọi private method, thay đổi field, hay vượt quyền JPMS.
8. **Đọc attribute an toàn:** chú ý annotation có thể thiếu ở runtime, chỉ có mặt ở vị trí khác hoặc cấu trúc class file không tương thích.
9. **Kiểm thử với nhiều kiểu phần tử:** ít nhất thử annotation trực tiếp, annotation không kế thừa, repeatable container, method/parameter và type-use.

## 12. Những lỗi phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Mọi annotation ở source đều đọc được bằng Reflection | Chỉ annotation được giữ ở runtime và tại vị trí phù hợp mới nhìn thấy qua API |
| `@Retention` mặc định là RUNTIME | Mặc định là CLASS |
| `Class<?>` là kiểu duy nhất hỗ trợ `AnnotatedElement` | `Method`, `Field`, `Constructor`, `Parameter`, `Package`, `Module`, `RecordComponent`, `AnnotatedType`… cũng hỗ trợ |
| `getAnnotations()` và `getDeclaredAnnotations()` luôn giống nhau | Class có thể kế thừa annotation `@Inherited` mà không khai báo trực tiếp |
| `@Inherited` có hiệu lực cho method override | Chỉ áp dụng cho quy tắc inheritance annotation trên class qua superclass |
| `getAnnotation(Tag.class)` trả hết repeatable tags | Dùng `getAnnotationsByType(Tag.class)` để mở container |
| Lớp con tự động gộp repeatable annotations của cha | Quy tắc “associated” không đơn giản là nối mọi cấp; annotation tại class con có thể che kết quả cha |
| Annotation của kiểu trả về nằm trên Method declaration | Phải đọc `method.getAnnotatedReturnType()` |
| Annotation của parameter cần `javac -parameters` | Tùy chọn đó chủ yếu cho tên parameter; annotation runtime của parameter có API riêng |
| Annotation trên superclass method tự xuất hiện khi class con override | Method override là khai báo mới; cần chính sách tìm qua hierarchy nếu nghiệp vụ yêu cầu |
| Đọc được private method annotation tức có quyền invoke method | Khả năng đọc metadata và khả năng truy cập gọi method là hai câu hỏi riêng |
| Có thể ép mọi object `AnnotatedElement` thành `Class<?>` | Các loại metadata khác nhau cùng implement interface; cần `instanceof` hoặc contract chung |

## 13. Tự kiểm tra

1. **Vì sao `Child.class.getAnnotation(Role.class)` thấy `Role` nhưng `getDeclaredAnnotation(Role.class)` không thấy?** Vì `Role` có `@Inherited` trên `Base` và `Child` không tự khai báo nó.
2. **Nếu annotation type dùng `@Retention(CLASS)`, có dùng `getAnnotation(...)` trên class đang chạy để đọc ổn định không?** Không. Metadata đó không phải runtime-visible qua Reflection chuẩn.
3. **Hai `@Tag` trên cùng class có phải trả một phần tử từ `getAnnotation(Tag.class)` không?** Không; repeatable annotations thường được lưu qua container và phải đọc bằng `getAnnotationsByType(Tag.class)`.
4. **`Field` và `Method` có thể được lưu trong cùng biến interface `AnnotatedElement` không?** Có. Cả hai triển khai interface.
5. **Annotation `@NonBlank` gắn vào return type `String` phải đọc ở đâu?** `method.getAnnotatedReturnType()`, không phải trực tiếp annotation declaration của `Method`.
6. **Muốn tìm annotation trên kiểu `String` trong `List<@X String>` phải làm gì?** Đi qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` từ annotated type của phần tử chứa kiểu đó.
7. **Một method override không mang `@Label` của method lớp cha, phải làm gì nếu framework muốn fallback?** Duyệt method hierarchy theo chữ ký và chính sách rõ ràng; đừng giả định `@Inherited` áp dụng cho method.
8. **Tại sao đọc `Parameter.getAnnotation(...)` không cần tên parameter trong class file?** Vì annotation metadata của parameter được lưu và đọc tách khỏi việc lưu tên nguồn bằng `-parameters`.
9. **Có được phép dùng `getAnnotation(...)` làm cách vượt quyền gọi method không public không?** Không. Metadata annotation không sửa quyền truy cập Reflection hoặc module.

**Ghi nhớ:** `AnnotatedElement` là giao diện thống nhất để **đọc annotation của đúng phần tử**. Chọn đúng đối tượng (declaration hay type-use), xác nhận runtime retention, phân biệt trực tiếp/kế thừa và dùng API `ByType` cho repeatable annotation để tránh bỏ sót metadata.

### Tài liệu chính thức

- [Java SE 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [Java SE 17 — RecordComponent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Java Language Specification — Annotation interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6)