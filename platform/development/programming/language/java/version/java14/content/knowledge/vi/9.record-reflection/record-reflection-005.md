# Annotation có mặt trực tiếp trên thành phần record qua Reflection (Java 16+)

> Bài học giải thích annotation **trực tiếp trên `RecordComponent`**, cách dùng `getDeclaredAnnotation()`/`getDeclaredAnnotations()`, sự khác biệt với annotation trên field, accessor, tham số canonical constructor và annotation của kiểu (`TYPE_USE`). Record là tính năng Java **chính thức từ Java 16**; ví dụ sử dụng JDK 17+ và không cần cờ preview của Java 14/15.

## 1. Record component là một phần tử Reflection riêng

Với khai báo:

```java
record Customer(String id, String name) {}
```

`id` và `name` là **record components** được khai báo ở header. Java tạo field `private final`, accessor `id()`/`name()` và canonical constructor tương ứng. Tuy nhiên record component **không đồng nhất** với field, method hay parameter: Java cung cấp `java.lang.reflect.RecordComponent` để biểu diễn riêng từng component.

Ví dụ đọc tên và kiểu của các component (đoạn minh họa đặt bên cạnh khai báo `Customer`, các câu lệnh chạy trong một phương thức):

```java
Class<?> type = Customer.class;
if (type.isRecord()) {
    for (java.lang.reflect.RecordComponent c : type.getRecordComponents()) {
        System.out.println(c.getName() + ":" + c.getType().getSimpleName());
    }
}
```

Đầu ra là `id:String` rồi `name:String` theo thứ tự component được khai báo. `getRecordComponents()` trả mảng rỗng nếu record không có component, và trả `null` nếu `Class` không đại diện record; nên kiểm tra `type.isRecord()` trước khi lặp.

Thông tin annotation của component được đọc **trên chính `RecordComponent`**. Nếu lấy `getDeclaredField("id")` hoặc `getAccessor()`, bạn đang đọc annotation của **hai declaration khác** và có thể nhận kết quả khác.

## 2. Định nghĩa một annotation trực tiếp cho record component

Để một annotation ở record header được Reflection nhận dạng **trực tiếp trên component**, kiểu annotation cần có mục tiêu `ElementType.RECORD_COMPONENT`. Để truy vấn được lúc chạy, annotation cần `@Retention(RetentionPolicy.RUNTIME)`.

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ColumnName {
    String value();
}

record Person(@ColumnName("person_id") String id, String displayName) {}
```

Ở đây `@ColumnName("person_id")` áp dụng trực tiếp cho component `id`, không áp dụng cho `displayName`. Vì target chỉ là `RECORD_COMPONENT`, annotation này **không tự được gắn** vào field `id`, accessor `id()` hoặc tham số `id` của canonical constructor.

Đọc annotation trực tiếp (đặt câu lệnh trong một phương thức nơi đã định nghĩa `Person` và `ColumnName`):

```java
java.lang.reflect.RecordComponent id = Person.class.getRecordComponents()[0];
ColumnName annotation = id.getDeclaredAnnotation(ColumnName.class);
System.out.println(id.getName());                    // id
System.out.println(annotation.value());              // person_id
System.out.println(id.isAnnotationPresent(ColumnName.class)); // true
```

`getDeclaredAnnotation()` trả đối tượng annotation đúng kiểu hoặc `null` nếu không tồn tại, nên mã xử lý tổng quát cần kiểm tra `null` trước khi gọi `value()`. Đọc metadata không cần tạo instance `new Person(...)`.

### `@Target` và `@Retention` là hai điều kiện độc lập

| Annotation đặt tại header component | Đọc trực tiếp bằng `RecordComponent.getDeclaredAnnotation(...)`? |
|---|---|
| `@Target(RECORD_COMPONENT)` và `@Retention(RUNTIME)` | **Có** nếu annotation được khai báo trên component |
| `@Target(RECORD_COMPONENT)` và `@Retention(CLASS)` | Không, Reflection runtime không trả về |
| `@Target(RECORD_COMPONENT)` và `@Retention(SOURCE)` | Không, chỉ tồn tại lúc biên dịch nguồn |
| `@Target(FIELD)` và `@Retention(RUNTIME)` | Không trên `RecordComponent`; annotation có thể được truyền sang field ngầm định |
| `@Target(METHOD)` và `@Retention(RUNTIME)` | Không trên `RecordComponent`; có thể xuất hiện trên accessor ngầm định |
| `@Target(PARAMETER)` và `@Retention(RUNTIME)` | Không trên `RecordComponent`; có thể xuất hiện trên tham số canonical constructor được sinh |
| `@Target(TYPE_USE)` và `@Retention(RUNTIME)` | Không như declaration annotation của component; đọc qua `getAnnotatedType()` |
| `@Target({RECORD_COMPONENT, FIELD, METHOD, PARAMETER})` và `@Retention(RUNTIME)` | Có trực tiếp trên component **và** có thể được truyền đến các declaration thích hợp |

Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`, nên dù code chứa annotation, `RecordComponent.getAnnotation()` vẫn không tìm thấy tại runtime. Khi thiết kế thư viện xử lý metadata qua Reflection, cần xác định rõ annotation có `RUNTIME` và target nào.

## 3. Các API đọc annotation trực tiếp

`RecordComponent` triển khai `java.lang.reflect.AnnotatedElement`. Những API quan trọng:

| API | Ý nghĩa |
|---|---|
| `getDeclaredAnnotation(A.class)` | Lấy annotation `A` khai báo **trực tiếp** trên component; trả `null` nếu vắng mặt |
| `getDeclaredAnnotations()` | Trả mảng annotation khai báo trực tiếp; mảng rỗng nếu không có |
| `getAnnotation(A.class)` | Lấy annotation `A` có mặt trên phần tử; đối với record component, không có kế thừa annotation từ component của superclass |
| `getAnnotations()` | Lấy các annotation có mặt; trong trường hợp record component thông thường, tập này tương ứng với các annotation trực tiếp |
| `isAnnotationPresent(A.class)` | Kiểm tra có annotation `A` hay không, hữu ích với marker annotation |
| `getDeclaredAnnotationsByType(A.class)` | Lấy các annotation cùng kiểu `A` (kể cả annotation được chứa gián tiếp khi `A` là `@Repeatable`) |
| `getAnnotationsByType(A.class)` | Biến thể cho các annotation có mặt của cùng kiểu, tiện khi xử lý annotation lặp |

Những API metadata khác thường dùng cùng lúc là `getName()`, `getType()`, `getGenericType()`, `getAnnotatedType()`, `getAccessor()` và `getDeclaringRecord()`. `getGenericType()` hữu ích khi component có `List<String>`; `getType()` sẽ chỉ cho biết raw class `List.class`. `getAnnotatedType()` dùng cho annotation tại **type-use**, có ý nghĩa khác với annotation khai báo component.

Không nên tìm annotation bằng cách so chuỗi `toString()` của `RecordComponent`; hãy dùng API theo kiểu `getDeclaredAnnotation(MyTag.class)` để có kiểu trả về chính xác. Nếu cần liệt kê mọi loại annotation, dùng `for (Annotation a : c.getDeclaredAnnotations())` và `a.annotationType()`.

**Không dựa vào `@Inherited` cho record component:** cơ chế `@Inherited` của Java chủ yếu nói về annotation trên class. Một record class không thể mở rộng record khác để kế thừa component; annotation trên class, field hoặc accessor không trở thành annotation trực tiếp trên component chỉ vì cùng tên.

## 4. Vì sao annotation ở header có thể xuất hiện ở field, method và parameter?

JLS quy định annotation viết ở record header có thể được **truyền tiếp** (*propagated*) sang những thành viên liên quan khi kiểu annotation có target phù hợp. Đây là quá trình độc lập với việc annotation có trực tiếp trên `RecordComponent` hay không.

| Target trong `@Target(...)` | Đối tượng Reflection có thể nhận annotation | Điều kiện đặc biệt |
|---|---|---|
| `RECORD_COMPONENT` | `RecordComponent` | Có `RUNTIME` để đọc ở runtime |
| `FIELD` | `Class.getDeclaredField(componentName)` | Component field do Java sinh |
| `METHOD` | `RecordComponent.getAccessor()` | Chỉ tự truyền đến **accessor ngầm định**, không tự truyền đến accessor viết tay |
| `PARAMETER` | `Constructor.getParameters()[index]` | Tham số của canonical constructor ngầm định hoặc compact constructor; không tự truyền vào tham số normal canonical constructor viết tường minh |
| `TYPE_USE` | `RecordComponent.getAnnotatedType()` | Chú thích vào kiểu được sử dụng; không phải declaration annotation |

Ví dụ annotation `@Target(FIELD)` có thể được đặt ở header record để field ngầm định nhận nó, nhưng `RecordComponent.getDeclaredAnnotations()` sẽ không thấy annotation đó. Annotation `@Target(METHOD)` có thể được truyền đến accessor `code()` ngầm định; nếu chính bạn viết accessor, việc truyền này không tự xảy ra.

### Trường hợp accessor tường minh

Giả sử annotation `@Tracked` có `@Target({RECORD_COMPONENT, METHOD})` và `@Retention(RUNTIME)`:

```java
record ExplicitAccessor(@Tracked String code) {
    public String code() { return code; }
}
```

`RecordComponent.getDeclaredAnnotation(Tracked.class)` vẫn tìm thấy `@Tracked`, nhưng `getAccessor().getDeclaredAnnotation(Tracked.class)` trả `null` do accessor đã được khai báo tường minh. Muốn annotation có trên accessor, hãy ghi trực tiếp nếu annotation cho phép target `METHOD`:

```java
record ExplicitAccessor(@Tracked String code) {
    @Tracked
    public String code() { return code; }
}
```

Hai snippet ở trên là **hai phiên bản thay thế** của cùng record, không được đặt cả hai cạnh nhau trong cùng một chương trình.

### Trường hợp canonical constructor tường minh

Với `@Tracked` có cả target `RECORD_COMPONENT` và `PARAMETER`:

```java
record ExplicitCanonical(@Tracked String code) {
    ExplicitCanonical(String code) { this.code = code; }
}
```

Tham số `String code` do người viết khai báo **không tự nhận** `@Tracked` từ header; để parameter có annotation, đặt `ExplicitCanonical(@Tracked String code)` nếu mục tiêu `PARAMETER` được phép. Với **compact canonical constructor** `ExplicitCanonical { ... }`, danh sách tham số được tạo ngầm, nên annotation trên component với target `PARAMETER` được truyền đến parameter đó. Không nhầm hai trường hợp này.

## 5. Annotation tại kiểu `TYPE_USE` cần `getAnnotatedType()`

Một annotation có `@Target(ElementType.TYPE_USE)` mô tả **kiểu của component**, không nhất thiết mô tả chính declaration của component. Nếu chỉ đọc `getDeclaredAnnotations()`, bạn có thể bỏ sót thông tin type-use.

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeFlag {}

record Note(@TypeFlag String text) {}
```

Trong phương thức truy vấn Reflection:

```java
java.lang.reflect.RecordComponent c = Note.class.getRecordComponents()[0];
System.out.println(c.isAnnotationPresent(TypeFlag.class)); // false
System.out.println(c.getAnnotatedType().isAnnotationPresent(TypeFlag.class)); // true
```

Với các kiểu generic như `List<@TypeFlag String>`, chú thích nằm ở đối số kiểu bên trong `AnnotatedParameterizedType`. `RecordComponent.getGenericType()` cho biết kiểu tổng quát, còn `getAnnotatedType()` mở đường tới cấu trúc annotation trên kiểu. Không suy ra rằng `TYPE_USE` luôn là annotation khai báo trực tiếp.

## 6. Ví dụ Java 17+ đầy đủ: so sánh vị trí annotation

Tạo tệp **`RecordAnnotationCheck.java`** dưới đây. Chương trình hiển thị annotation trực tiếp trên component, annotation truyền sang field, accessor, parameter, và type-use; đồng thời so sánh các thành viên sinh ngầm với thành viên khai báo tường minh.

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

public class RecordAnnotationCheck {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface Label { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.RECORD_COMPONENT, ElementType.FIELD,
             ElementType.METHOD, ElementType.PARAMETER})
    public @interface Tracked {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface FieldOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeFlag {}

    public record User(
        @Label("identifier") @Tracked @FieldOnly @TypeFlag String id,
        String role
    ) {}

    public record Custom(@Tracked String code) {
        @Override public String code() { return code; }
    }

    public record Explicit(@Tracked String code) {
        public Explicit(String code) { this.code = code; }
    }

    public record Compact(@Tracked String code) {
        public Compact { code = code.strip(); }
    }

    public static void main(String[] args) throws Exception {
        RecordComponent c = User.class.getRecordComponents()[0];
        System.out.println("record=" + User.class.isRecord());
        System.out.println("name=" + c.getName());
        System.out.println("label=" + c.getAnnotation(Label.class).value());
        System.out.println("componentTracked=" +
            c.isAnnotationPresent(Tracked.class));
        System.out.println("componentFieldOnly=" +
            c.isAnnotationPresent(FieldOnly.class));
        System.out.println("fieldOnlyOnField=" +
            User.class.getDeclaredField("id").isAnnotationPresent(FieldOnly.class));
        System.out.println("trackedOnAccessor=" +
            c.getAccessor().isAnnotationPresent(Tracked.class));
        System.out.println("trackedOnParameter=" +
            User.class.getDeclaredConstructor(String.class, String.class)
                .getParameters()[0].isAnnotationPresent(Tracked.class));
        System.out.println("typeFlagOnType=" +
            c.getAnnotatedType().isAnnotationPresent(TypeFlag.class));
        System.out.println("typeFlagOnComponent=" +
            c.isAnnotationPresent(TypeFlag.class));

        RecordComponent custom = Custom.class.getRecordComponents()[0];
        System.out.println("customComponent=" +
            custom.isAnnotationPresent(Tracked.class));
        System.out.println("customAccessor=" +
            custom.getAccessor().isAnnotationPresent(Tracked.class));
        System.out.println("explicitParameter=" +
            Explicit.class.getDeclaredConstructor(String.class)
                .getParameters()[0].isAnnotationPresent(Tracked.class));
        System.out.println("compactParameter=" +
            Compact.class.getDeclaredConstructor(String.class)
                .getParameters()[0].isAnnotationPresent(Tracked.class));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 RecordAnnotationCheck.java
java RecordAnnotationCheck
```

**Stdout chính xác** (đã xác nhận bằng mã tương đương trên OpenJDK 24):

```text
record=true
name=id
label=identifier
componentTracked=true
componentFieldOnly=false
fieldOnlyOnField=true
trackedOnAccessor=true
trackedOnParameter=true
typeFlagOnType=true
typeFlagOnComponent=false
customComponent=true
customAccessor=false
explicitParameter=false
compactParameter=true
```

Giải thích:

- `Label` có duy nhất target `RECORD_COMPONENT`, nên tìm thấy trên component và lấy được giá trị `identifier`.
- `Tracked` có nhiều target, nên có trên component và còn được gắn lên accessor/parameter **được sinh ngầm**.
- `FieldOnly` chỉ được truyền sang field `id`, không phải annotation trực tiếp của `RecordComponent`.
- `TypeFlag` chỉ thuộc `TYPE_USE`, phải đọc qua `getAnnotatedType()`.
- `Custom` có accessor tự viết nên accessor không tự nhận `Tracked`, dù component vẫn có.
- `Explicit` có normal canonical constructor tự viết nên parameter không tự nhận `Tracked`.
- `Compact` có parameter do trình biên dịch tạo ngầm nên annotation có target `PARAMETER` được truyền vào.

## 7. Annotation lặp: dùng `getDeclaredAnnotationsByType()`

Với annotation được đánh dấu `@Repeatable`, muốn đọc tất cả giá trị cùng kiểu trên một component, dùng API `getDeclaredAnnotationsByType()` thay vì chỉ gọi `getDeclaredAnnotation()`.

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@Repeatable(Tags.class)
@interface Tag { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface Tags { Tag[] value(); }

record Asset(@Tag("index") @Tag("public") String code) {}

// Những câu lệnh sau đặt trong một phương thức:
Tag[] tags = Asset.class.getRecordComponents()[0]
    .getDeclaredAnnotationsByType(Tag.class);
System.out.println(tags.length); // 2
```

Snippet ở trên minh họa cú pháp khai báo lặp có container phù hợp. `@Tag` và container `@Tags` cùng có target `RECORD_COMPONENT` và `RUNTIME` retention. Khi xử lý một kiểu annotation không lặp, `getDeclaredAnnotation()` vẫn là lựa chọn trực tiếp nhất.

## 8. Áp dụng metadata và những lỗi hay gặp

**Ứng dụng:** một thư viện mapping có thể đặt `@ColumnName("person_id")` trên record component, duyệt `clazz.getRecordComponents()`, lấy tên, kiểu và annotation rồi tạo cấu hình ánh xạ. Cách làm này chỉ phù hợp nếu hợp đồng của thư viện thật sự đọc annotation từ `RecordComponent`; một thư viện khác có thể đọc field hoặc accessor, dẫn tới kết quả khác.

**Annotation không tự thi hành validation.** Viết `@NotBlank` hoặc `@Required` lên component chỉ lưu metadata theo target/retention. Phải có framework chạy validator, hoặc kiểm tra bất biến dữ liệu ngay trong canonical constructor. Không dùng một marker annotation để thay thế phân quyền hay kiểm tra dữ liệu đầu vào.

| Sai lầm | Nguyên nhân | Cách sửa |
|---|---|---|
| Có annotation ở header nhưng `getDeclaredAnnotation` là `null` | Target không có `RECORD_COMPONENT` hoặc retention không phải `RUNTIME` | Kiểm tra định nghĩa annotation; đọc đúng đối tượng Reflection nếu target là FIELD/METHOD/PARAMETER/TYPE_USE |
| `@Target(FIELD)` không xuất hiện trong `RecordComponent.getAnnotations()` | Annotation được truyền sang field ngầm định | Dùng `getDeclaredField(name)` hoặc bổ sung target RECORD_COMPONENT nếu được phép sửa annotation |
| `@Target(METHOD)` không xuất hiện ở accessor viết tay | Propagation chỉ áp dụng tới accessor ngầm định | Ghi annotation trên accessor tường minh |
| `@Target(PARAMETER)` thiếu ở normal canonical constructor tường minh | Tham số được tự khai báo có annotation riêng | Ghi annotation trên tham số đó hoặc dùng canonical constructor ngầm định/compact nếu phù hợp |
| `TYPE_USE` bị coi là annotation component | Hai loại metadata khác nhau | Dùng `getAnnotatedType()` |
| Gọi `getRecordComponents()` của class thường rồi lặp | API trả `null` cho non-record class | Kiểm tra `isRecord()` trước khi duyệt |
| Dùng `getDeclaredAnnotation(A.class)` để lấy mọi annotation lặp | Annotation có thể nằm trong repeatable container | Dùng `getDeclaredAnnotationsByType(A.class)` |
| Trông đợi validation tự chạy vì có annotation | Annotation chỉ là metadata | Tích hợp validator hoặc kiểm tra constructor |

## 9. Checklist hoàn thiện

1. Dùng `Class.isRecord()` để kiểm tra đúng đối tượng và `Class.getRecordComponents()` để lấy các component.
2. Muốn annotation **trực tiếp** trên component? Kiểm tra `@Target(ElementType.RECORD_COMPONENT)`.
3. Muốn đọc annotation bằng Reflection khi chạy? Kiểm tra `@Retention(RetentionPolicy.RUNTIME)`.
4. Biết khi nào dùng `getDeclaredAnnotation`, `getDeclaredAnnotations`, `isAnnotationPresent` và `getDeclaredAnnotationsByType`.
5. Phân biệt `RecordComponent`, `Field`, `Method`, `Parameter` và `AnnotatedType`; đừng suy ra kết quả ở đối tượng này từ đối tượng khác.
6. Kiểm tra accessor và canonical constructor được sinh ngầm, compact hay tự khai báo; điều này ảnh hưởng propagation.
7. Nếu component generic hoặc type-use, đọc `getGenericType()`/`getAnnotatedType()` phù hợp.
8. Có test cả annotation hiện diện và vắng mặt, annotation lặp, nhánh class không phải record.
9. Dùng Java 16+ chính thức, ưu tiên JDK 17+ cho ví dụ học tập; không cần bất kỳ cờ preview Java 14/15 nào.

## Nguồn tham khảo chính thức

- Java Language Specification, §8.10.1 *Record Components*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.1
- Java Language Specification, §8.10.3 *Record Members*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3
- Java Language Specification, §8.10.4 *Record Constructor Declarations*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4
- Java SE 25 API, `RecordComponent`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html
- Java SE 17 API, `ElementType.RECORD_COMPONENT`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html#RECORD_COMPONENT
- Java SE 17 API, `AnnotatedElement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
