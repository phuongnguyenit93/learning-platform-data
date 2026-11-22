# Kiểm thử annotation trên generic, mảng và record trong Java

## 1. Mục tiêu và phạm vi

Annotation trong Java không chỉ gắn lên class, method hoặc field. Từ Java 8, `ElementType.TYPE_USE` cho phép gắn annotation vào **vị trí sử dụng kiểu** (*type use*): kiểu đối số của generic, kiểu bound, kiểu thành phần mảng, từng chiều của mảng, kiểu trả về và nhiều vị trí khác. Java 8 cũng hỗ trợ `ElementType.TYPE_PARAMETER` cho **khai báo tham số kiểu**. Từ Java 16, record là tính năng chính thức, kèm `ElementType.RECORD_COMPONENT` và API phản chiếu `RecordComponent`.

Khi kiểm thử, một dòng nguồn “có annotation” không đủ chứng minh mọi API reflection sẽ trả về annotation ấy. Phải hỏi đúng ba câu:

1. Annotation được đặt ở **đích nào**: `TYPE_USE`, `TYPE_PARAMETER`, `FIELD` hay `RECORD_COMPONENT`?
2. Annotation có được giữ tới **runtime** không, và test dùng Java reflection hay một annotation processor?
3. Test đang truy vấn **đúng lớp metadata** chưa: declaration qua `Field.getAnnotation(...)`, generic argument qua `AnnotatedParameterizedType`, array dimension qua `AnnotatedArrayType`, hoặc record component qua `RecordComponent`?

Đây là bài hướng dẫn thiết kế test cho các trường hợp dễ nhầm nhất ở **Java 17+**: annotation trên khai báo generic và bound, annotation trên generic type arguments, chú thích mảng một chiều/nhiều chiều, record component và việc phân biệt metadata gốc với metadata được compiler truyền tới các thành phần record liên quan.

## 2. Hai nhóm đích: declaration annotation và type-use annotation

`@Target` thuộc `java.lang.annotation`, xác định nơi annotation được phép sử dụng. Các đích liên quan trực tiếp:

| Đích | Ý nghĩa | Ví dụ |
|---|---|---|
| `ElementType.TYPE_PARAMETER` | Khai báo một tham số kiểu | `class Box<@TypeParamMark T> {}` |
| `ElementType.TYPE_USE` | Vị trí sử dụng một kiểu | `List<@TypeMark String>` |
| `ElementType.FIELD` | Khai báo field | `@FieldMark String name;` |
| `ElementType.METHOD` | Khai báo method | `@MethodMark String read()` |
| `ElementType.PARAMETER` | Khai báo tham số method/constructor | `void f(@ParamMark String x)` |
| `ElementType.RECORD_COMPONENT` | Khai báo record component | `record User(@ComponentMark String id) {}` |

Hai ví dụ khai báo annotation type:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParamMark {
    String value();
}
```

`TypeParamMark` mô tả **khai báo** `T` trong `class Box<T>`. `TypeMark` mô tả **vị trí sử dụng kiểu**, ví dụ `String` trong `List<String>` hoặc `Number` ở bound `T extends Number`. Đây là hai tầng metadata có thể độc lập với nhau.

**Lưu ý về chồng lấn target:** `TYPE_USE` còn áp dụng tại một số ngữ cảnh khai báo kiểu/tham số kiểu theo đặc tả Java. Để làm test dễ giải thích, các ví dụ bên dưới dùng annotation type **chỉ dành cho từng đích**. Không suy luận rằng một annotation xuất hiện ngay trước từ khóa `String` thì chắc chắn phải lấy bằng `Field.getAnnotation`; nó có thể là type-use annotation.

## 3. Điều kiện nhìn thấy annotation qua runtime reflection

Để test qua Java reflection, annotation type phải có `@Retention(RetentionPolicy.RUNTIME)`. Nếu chỉ dùng `SOURCE`, metadata không tồn tại trong class file sau biên dịch; `CLASS` vẫn được ghi trong class file nhưng không hiện qua API reflection chuẩn.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface RuntimeTypeMark {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE_USE)
@interface BytecodeTypeMark {
    String value();
}
```

Hai khai báo là ví dụ rời, cần import `Retention`, `RetentionPolicy`, `Target` và `ElementType`.

Test runtime:

- `getAnnotatedType()` / `getAnnotatedReturnType()` / `getAnnotatedBounds()` cùng những API phụ liên quan chỉ nhìn thấy các annotation phù hợp retention `RUNTIME`.
- `RetentionPolicy.CLASS` có thể kiểm bằng công cụ đọc class file, ví dụ `javap -v` hoặc một bytecode parser.
- Không thấy annotation qua reflection **không** chứng minh source sai; hãy kiểm tra retention, target và đối tượng đang được tra cứu trước.

Các attribute trong class file thường có dạng `RuntimeVisibleTypeAnnotations` và `RuntimeInvisibleTypeAnnotations` cho type-use annotations. Điều này khác `RuntimeVisibleAnnotations`/`RuntimeInvisibleAnnotations` dùng cho nhiều declaration annotations. Khi phân tích bytecode, cần tìm đúng loại attribute theo vị trí được chú thích.

## 4. Kiểm thử khai báo generic type parameter

Ví dụ:

```java
class Repository<@TypeParamMark("entity-parameter") T> {
}
```

Annotation ở đây mô tả chính **tham số kiểu `T` của lớp `Repository`**, không phải một đối tượng kiểu `T` khi chạy. Ta đọc nó qua:

```java
import java.lang.reflect.TypeVariable;

TypeVariable<?> variable =
        Repository.class.getTypeParameters()[0];

TypeParamMark annotation =
        variable.getAnnotation(TypeParamMark.class);
```

`TypeVariable` triển khai `AnnotatedElement` nên hỗ trợ các API đọc annotation. `getTypeParameters()` trả các `TypeVariable`, khác `getGenericInterfaces()` hay `Field.getAnnotatedType()`.

Một trường hợp khác:

```java
class Pair<
    @TypeParamMark("key") K,
    @TypeParamMark("value") V
> {
}
```

Test nên bảo đảm:

- Có đúng **hai** type variables.
- Thứ tự tên của chúng là `K` rồi `V`.
- Mỗi `TypeVariable` có annotation đúng giá trị tương ứng.
- Nếu annotation target-only là `TYPE_PARAMETER`, không giả định annotation sẽ xuất hiện trên mọi nơi người dùng sau đó viết `K` hoặc `V`.

Một annotation trên declaration `T` **không tự được truyền** tới type argument `String` trong `Repository<String>`. Đây là hai bối cảnh khác nhau; nếu yêu cầu giá trị type argument có annotation, phải ghi annotation ở chính vị trí đó.

## 5. Kiểm thử annotation trên generic bound

Khai báo:

```java
class NumericBox<T extends @TypeMark("upper-bound") Number> {
}
```

`@TypeMark` ở đây gắn lên **kiểu `Number` được dùng làm upper bound**, không gắn lên `T` như một `TYPE_PARAMETER` declaration annotation.

Đọc đúng vị trí:

```java
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.TypeVariable;

TypeVariable<?> t =
        NumericBox.class.getTypeParameters()[0];

AnnotatedType bound = t.getAnnotatedBounds()[0];
TypeMark mark = bound.getAnnotation(TypeMark.class);
```

Điểm cần kiểm tra:

1. `NumericBox.class.getTypeParameters()[0]` là `TypeVariable` cho `T`.
2. `getAnnotatedBounds()` trả các annotated bounds.
3. `bound.getAnnotation(TypeMark.class)` đọc annotation **gắn vào bound `Number`**.

Không gọi `t.getAnnotation(TypeMark.class)` rồi kết luận bound không được chú thích; đó là truy vấn nhầm **declaration** của `T` thay vì **bound type**.

Với nhiều interface bounds:

```java
class ComparableBox<
    T extends @TypeMark("number") Number
        & @TypeMark("comparable") Comparable<T>
> {
}
```

`getAnnotatedBounds()` có nhiều mục theo các bounds được khai báo. Test nên xác minh đúng số phần tử và giá trị trên từng bound theo thứ tự, không chỉ kiểm tra xem “có một annotation” hay không.

## 6. Kiểm thử generic type arguments bằng `AnnotatedParameterizedType`

Đây là trường hợp thường bị bỏ sót:

```java
import java.util.List;

class Messages {
    List<@TypeMark("message") String> values;
}
```

Annotation không gắn trực tiếp trên declaration field `values`. Nó nằm trên **kiểu đối số `String` bên trong `List<String>`**.

API phù hợp:

```java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;

Field field = Messages.class.getDeclaredField("values");

AnnotatedParameterizedType parameterized =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType argument =
        parameterized.getAnnotatedActualTypeArguments()[0];

TypeMark mark = argument.getAnnotation(TypeMark.class);
```

Đây là đoạn minh họa, giả định `TypeMark` đã được khai báo và ngoại lệ `NoSuchFieldException` được xử lý.

**Phân biệt ba API:**

| API | Trả về | Thông tin chính |
|---|---|---|
| `field.getType()` | `Class<?>` | Kiểu đã xóa generic ở mức field (ở đây `List.class`) |
| `field.getGenericType()` | `Type` | Cấu trúc generic, ví dụ `List<String>` |
| `field.getAnnotatedType()` | `AnnotatedType` | Cấu trúc kiểu **kèm type-use annotation** |

`field.getAnnotation(TypeMark.class)` không truy vấn vào type argument bên trong `List<...>`. Một test phải đọc đúng `AnnotatedParameterizedType` rồi đi xuống `getAnnotatedActualTypeArguments()`.

### Generic lồng nhau

Ví dụ:

```java
import java.util.Map;
import java.util.List;

class NestedMap {
    Map<@TypeMark("key") String,
        List<@TypeMark("item") Integer>> value;
}
```

Cấu trúc reflection là một cây:

```text
AnnotatedParameterizedType: Map
  ├── AnnotatedType: String
  │     └── @TypeMark("key")
  └── AnnotatedParameterizedType: List
        └── AnnotatedType: Integer
              └── @TypeMark("item")
```

Nếu test chỉ kiểm tra annotation trên `Map` hoặc `List` ngoài cùng, sẽ bỏ sót annotation nằm sâu trong các type arguments. Cách test đúng là đi theo cây annotated types.

Trong ứng dụng tổng quát, nên kiểm tra `instanceof AnnotatedParameterizedType` trước khi ép kiểu, vì field có thể thay đổi từ `List<String>` sang kiểu đơn, kiểu mảng hoặc type variable trong lần refactor sau.

## 7. Kiểm thử từng chiều mảng: `AnnotatedArrayType`

Annotation trên mảng có thể thuộc **chiều mảng** hoặc **kiểu phần tử cuối**.

Ví dụ:

```java
class MatrixHolder {
    String @TypeMark("outer") []
           @TypeMark("inner") [] matrix;
}
```

`matrix` có kiểu `String[][]`, nhưng annotation `outer` gắn lên **chiều ngoài** và `inner` lên **chiều trong**. Đọc qua:

```java
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.Field;

Field field = MatrixHolder.class.getDeclaredField("matrix");

AnnotatedArrayType outer =
        (AnnotatedArrayType) field.getAnnotatedType();

AnnotatedArrayType inner =
        (AnnotatedArrayType) outer.getAnnotatedGenericComponentType();

TypeMark outerMark = outer.getAnnotation(TypeMark.class);
TypeMark innerMark = inner.getAnnotation(TypeMark.class);
```

Đây là đoạn minh họa, cần khai báo `TypeMark` và xử lý `NoSuchFieldException` khi đặt vào chương trình.

**Test quan trọng nhất:** hai giá trị phải nằm ở **hai tầng `AnnotatedArrayType` khác nhau**, không phải cả hai tại `field.getAnnotation(...)` hoặc chỉ một tầng mảng.

Với một mảng một chiều:

```java
class OneDimension {
    String @TypeMark("array-dimension") [] names;
}
```

`field.getAnnotatedType()` là một `AnnotatedArrayType` có annotation `array-dimension`, còn `getAnnotatedGenericComponentType()` dẫn tới annotated type của `String`.

### Annotation trên kiểu phần tử thay vì chiều mảng

```java
class AnnotatedComponent {
    @TypeMark("element") String[] names;
}
```

Trong một annotation chỉ có `@Target(TYPE_USE)`, vị trí này nhắm vào **kiểu phần tử `String`**, không phải bản thân `FIELD` declaration. Để đọc trong mảng một chiều:

```java
AnnotatedArrayType array =
        (AnnotatedArrayType) AnnotatedComponent.class
                .getDeclaredField("names")
                .getAnnotatedType();

TypeMark componentMark =
        array.getAnnotatedGenericComponentType()
             .getAnnotation(TypeMark.class);
```

Vì cú pháp gần giống field declaration annotation, test nên chủ động tách annotation type chỉ target `TYPE_USE` khỏi annotation type chỉ target `FIELD` để quan sát đúng metadata.

### Mảng của generic

```java
class GenericArrayHolder {
    List<@TypeMark("item") String>
            @TypeMark("array") [] names;
}
```

Cây reflection:

```text
AnnotatedArrayType: array
  └── @TypeMark("array")
  └── AnnotatedParameterizedType: List
        └── AnnotatedType: String
              └── @TypeMark("item")
```

Test phải đi từ `AnnotatedArrayType` đến component `AnnotatedParameterizedType`, rồi vào actual type argument `String`.

## 8. Record component là một vị trí metadata riêng

Từ Java 16, Java có **record** như một cách khai báo kiểu dữ liệu chứa các component:

```java
record User(String id, int age) {}
```

Record thường có thành phần tương ứng với:

- Một **record component** trong record header.
- Field riêng tương ứng do compiler khai báo.
- Accessor method như `id()`.
- Tham số của canonical constructor.

Tuy nhiên, đây là các **phần tử khác nhau trong ngôn ngữ và reflection**. Không nên gọi `Field.getAnnotation(...)` rồi giả định nó phản ánh đầy đủ annotation chỉ nhắm `RECORD_COMPONENT`.

Định nghĩa annotation declaration riêng cho component:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMark {
    String value();
}
```

Ví dụ:

```java
record User(
    @ComponentMark("identifier") String id,
    String displayName
) {}
```

Truy vấn:

```java
import java.lang.reflect.RecordComponent;

RecordComponent[] components =
        User.class.getRecordComponents();

ComponentMark mark =
        components[0].getAnnotation(ComponentMark.class);
```

Kiểm tra chắc chắn hơn nên tìm component theo `getName()` thay vì luôn chọn index `0` khi mục đích test không phụ thuộc thứ tự; trên bản khai báo record cố định, `getRecordComponents()` trả theo thứ tự record header.

Hai API quan trọng khác:

- `User.class.isRecord()` cho biết đó có phải record class hay không.
- `component.getAnnotatedType()` cung cấp metadata annotation trên **kiểu của component**, khác `component.getAnnotation(...)` vốn hỏi annotation trên **declaration record component**.
- `component.getAccessor()` cho phép truy vấn accessor tương ứng nếu test cũng cần kiểm tra metadata ở method.
- `component.getGenericType()` cung cấp thông tin generic của kiểu component.

Nếu chỉ dùng `@Target(RECORD_COMPONENT)`, không kỳ vọng annotation ấy tự xuất hiện trên field/accessor/constructor parameter vì những đích khác không được cho phép.

## 9. Record component với type-use annotation và generic

Hai annotation có thể cùng xuất hiện ở record header mà mang ý nghĩa khác:

```java
record Entry(
    @ComponentMark("key")
    @TypeMark("text-type")
    String key
) {}
```

Ở đây:

- `@ComponentMark("key")` là **record component declaration annotation**.
- `@TypeMark("text-type")` là **annotation trên kiểu `String` của component** vì `TypeMark` chỉ có `@Target(TYPE_USE)`.

Test đúng:

```java
RecordComponent component =
        Entry.class.getRecordComponents()[0];

ComponentMark declaration =
        component.getAnnotation(ComponentMark.class);

TypeMark typeUse =
        component.getAnnotatedType()
                 .getAnnotation(TypeMark.class);
```

Cả hai có thể được đọc nếu retention là `RUNTIME`. Không đổi hai vị trí này cho nhau.

### Record generic

```java
import java.util.List;

record Inbox(
    List<@TypeMark("record-argument") String> messages
) {}
```

Đọc:

```java
RecordComponent component =
        Inbox.class.getRecordComponents()[0];

AnnotatedParameterizedType type =
        (AnnotatedParameterizedType) component.getAnnotatedType();

TypeMark argMark =
        type.getAnnotatedActualTypeArguments()[0]
            .getAnnotation(TypeMark.class);
```

Dù `Inbox` là record, generic type argument vẫn được tra theo cùng cây `AnnotatedParameterizedType` như field thông thường.

### Mảng trong record

```java
record Batch(String @TypeMark("record-array") [] values) {}
```

`Batch.class.getRecordComponents()[0].getAnnotatedType()` có thể được ép thành `AnnotatedArrayType` để đọc `record-array` ở chiều mảng, như với field.

**Điểm học tập:** Record không tạo một “cơ chế type-use annotation khác”. Nó cung cấp thêm **đối tượng `RecordComponent`**, từ đó dùng lại các loại `AnnotatedType` theo đúng cấu trúc kiểu của component.

## 10. Khi nào annotation trong record được truyền tới field, accessor, constructor?

Theo quy tắc của Java record, một số annotation viết trên record component có thể được **truyền** đến field tương ứng, accessor được khai báo ngầm, hoặc formal parameter của canonical constructor, **nếu annotation type có target phù hợp**.

Ví dụ annotation nhiều đích:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Labelled {
    String value();
}

record Task(@Labelled("task-id") String id) {}
```

Vì `Labelled` cho phép nhiều đích, compiler có thể ghi metadata tương ứng ở những phần tử do record khai báo ngầm theo các quy tắc đặc tả.

Nhưng phải phân biệt:

1. **Record component**: truy vấn `Task.class.getRecordComponents()`.
2. **Field**: `Task.class.getDeclaredField("id")`.
3. **Accessor**: `Task.class.getDeclaredMethod("id")`.
4. **Canonical constructor parameter**: lấy `Constructor<?>` có chữ ký tương ứng rồi `getParameters()` hoặc `getParameterAnnotations()`.

**Không khái quát rằng mọi annotation trên record component đều xuất hiện trên cả bốn nơi.** Việc truyền phụ thuộc vào `@Target` và loại thành phần cụ thể.

Một lưu ý nâng cao: nếu **tự khai báo accessor** hoặc **canonical constructor**, quy tắc lan truyền tới các khai báo tường minh có những điều kiện khác với thành phần được compiler tạo ngầm. Khi cần đảm bảo contract ở những nơi ấy, hãy viết test riêng cho dạng record thực tế của dự án; không chỉ kiểm thử một record “rút gọn” rồi suy rộng.

Để tránh nhầm trong các test đơn vị của bài này, ví dụ chạy ở mục tiếp theo dùng một annotation **chỉ target `RECORD_COMPONENT`** và một annotation **chỉ target `TYPE_USE`**, nên mỗi truy vấn phản ánh một chủ đích rõ ràng.

## 11. Chương trình Java 17+ hoàn chỉnh: generic, mảng và record

Tạo **một file duy nhất** tên `AnnotationShapeDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParamMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMark {
    String value();
}

class Samples<@ParamMark("T") T extends @TypeMark("bound") Number> {
    List<@TypeMark("argument") String> texts;

    String @TypeMark("outer") []
           @TypeMark("inner") [] matrix;
}

record Entry(
    @ComponentMark("name")
    @TypeMark("type")
    String name
) {}

public class AnnotationShapeDemo {
    private static String getValue(TypeMark mark) {
        if (mark == null) {
            throw new AssertionError("Missing TypeMark");
        }
        return mark.value();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        TypeVariable<?> parameter =
                Samples.class.getTypeParameters()[0];

        System.out.println("type parameter="
                + parameter.getAnnotation(ParamMark.class).value());

        AnnotatedType bound =
                parameter.getAnnotatedBounds()[0];

        System.out.println("bound="
                + getValue(bound.getAnnotation(TypeMark.class)));

        Field texts =
                Samples.class.getDeclaredField("texts");

        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) texts.getAnnotatedType();

        AnnotatedType typeArgument =
                listType.getAnnotatedActualTypeArguments()[0];

        System.out.println("type argument="
                + getValue(typeArgument.getAnnotation(TypeMark.class)));

        Field matrix =
                Samples.class.getDeclaredField("matrix");

        AnnotatedArrayType outer =
                (AnnotatedArrayType) matrix.getAnnotatedType();

        AnnotatedArrayType inner =
                (AnnotatedArrayType) outer.getAnnotatedGenericComponentType();

        System.out.println("array outer="
                + getValue(outer.getAnnotation(TypeMark.class)));

        System.out.println("array inner="
                + getValue(inner.getAnnotation(TypeMark.class)));

        RecordComponent component =
                Entry.class.getRecordComponents()[0];

        System.out.println("record declaration="
                + component.getAnnotation(ComponentMark.class).value());

        System.out.println("record type="
                + getValue(component.getAnnotatedType()
                        .getAnnotation(TypeMark.class)));
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 hoặc mới hơn:

```bash
javac AnnotationShapeDemo.java
java AnnotationShapeDemo
```

**Stdout dự kiến chính xác:**

```text
type parameter=T
bound=bound
type argument=argument
array outer=outer
array inner=inner
record declaration=name
record type=type
```

### Phân tích từng kết quả

1. `ParamMark` đặt trên **declaration của `T`**: lấy bằng `TypeVariable.getAnnotation(ParamMark.class)`.
2. `TypeMark("bound")` đặt trên kiểu `Number` ở bound: phải truy vấn `TypeVariable.getAnnotatedBounds()[0]`.
3. `TypeMark("argument")` đặt trên `String` trong `List<String>`: đi qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.
4. Hai `TypeMark` trên `matrix` thuộc **hai mức mảng**; từ outer `AnnotatedArrayType` phải đi xuống thêm một `AnnotatedArrayType` mới thấy `inner`.
5. `ComponentMark` là annotation declaration trên record component `name`.
6. `TypeMark("type")` mô tả kiểu của record component; lấy qua `RecordComponent.getAnnotatedType()`.

`getValue(...)` báo `AssertionError` nếu metadata type-use mong đợi vắng mặt, giúp bài học không âm thầm in `null` trong các trường hợp sai target hoặc retention.

Không có annotation processor hoặc thư viện ngoài trong ví dụ này. Đây là bài test **runtime reflection**; các annotation đều có retention `RUNTIME`. Chỉ `AnnotationShapeDemo` là public top-level class và tên trùng file, nên các kiểu còn lại có thể khai báo cùng compilation unit.

## 12. Viết assertions thay vì chỉ nhìn stdout

Trong code kiểm thử, nên kiểm tra **giá trị chính xác** và vị trí phản chiếu, không chỉ in ra console.

Một helper đơn giản không phụ thuộc JUnit:

```java
static void expect(String expected, String actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                "Expected " + expected + " but got " + actual);
    }
}
```

Đây là một method minh họa để thêm **bên trong một class test**.

Thay vì:

```java
System.out.println(typeArgument.getAnnotation(TypeMark.class));
```

nên viết:

```java
TypeMark mark =
        typeArgument.getAnnotation(TypeMark.class);

if (mark == null) {
    throw new AssertionError("Missing annotation on type argument");
}

expect("argument", mark.value());
```

Cách này phát hiện cả hai lỗi:

- Metadata **vắng mặt**, thường do sai `@Target`, retention hoặc đường reflection.
- Metadata **có mặt nhưng sai giá trị**, chẳng hạn lỡ gắn annotation vào type argument khác.

Nếu dùng JUnit 5, nguyên lý không đổi: dùng `assertNotNull`, `assertEquals`, `assertArrayEquals` và `assertThrows` phù hợp. Bài này không yêu cầu dependency JUnit vì test cơ sở có thể viết bằng Java thuần.

### Một test tốt gồm cả kiểm tra “không có”

Ví dụ với `ComponentMark` chỉ target `RECORD_COMPONENT`, có thể kiểm tra không xuất hiện dưới dạng field annotation:

```java
Field field = Entry.class.getDeclaredField("name");
if (field.isAnnotationPresent(ComponentMark.class)) {
    throw new AssertionError("Unexpected field annotation");
}
```

Đoạn được thực thi trong ngữ cảnh xử lý `NoSuchFieldException` và dùng các kiểu đã định nghĩa ở mục 11.

Test âm tính này chứng minh code không đọc nhầm record component metadata thành field declaration metadata. Khi annotation type được mở rộng target thêm `FIELD`, kết quả mong đợi cần đánh giá lại theo quy tắc truyền annotation của record.

## 13. Những trường hợp test âm tính về `@Target` và cú pháp

### 13.1. Dùng annotation chỉ target `TYPE_PARAMETER` trên type argument

```java
import java.util.List;

// CỐ Ý SAI: ParamMark chỉ cho phép TYPE_PARAMETER.
class WrongGeneric {
    List<@ParamMark("bad") String> values;
}
```

`String` trong `List<String>` là một **type argument use**, không phải khai báo một type parameter. Hãy dùng annotation có `@Target(TYPE_USE)`, ví dụ `@TypeMark("ok")`.

### 13.2. Dùng annotation chỉ target `RECORD_COMPONENT` trên field thông thường

```java
// CỐ Ý SAI: ComponentMark chỉ cho phép RECORD_COMPONENT.
class WrongField {
    @ComponentMark("bad")
    String name;
}
```

`name` ở đây là field trong class, không phải record component. Khi mục đích là đánh dấu declaration field, dùng annotation có `@Target(FIELD)`.

### 13.3. Dùng `List<String>` làm kiểu element của annotation

```java
import java.util.List;

// CỐ Ý SAI: annotation element không nhận List<String>.
@interface InvalidMetadata {
    List<String> values();
}
```

Đây là vấn đề khác với việc **đặt annotation trên một generic type argument**. Java cho phép `List<@TypeMark String>` ở nơi sử dụng kiểu, nhưng **không** cho phép annotation element trả về `List<String>`.

Annotation element chỉ được trả về primitive, `String`, `Class` thích hợp, enum, annotation hoặc mảng một chiều của các kiểu ấy. Đừng nhầm “generic type có thể mang type-use annotation” với “annotation element hỗ trợ mọi generic type”.

### 13.4. Thiếu `@Retention(RUNTIME)` rồi kiểm bằng reflection

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface CompileOnlyMark {
}
```

Không khai báo `@Retention` nghĩa là mặc định `CLASS`. Test bằng `getAnnotatedType().getAnnotation(CompileOnlyMark.class)` sẽ không nhìn thấy annotation, dù bytecode còn có thể chứa metadata class-file.

### 13.5. Kiểm thử mảng bằng `field.getAnnotation`

```java
Field matrix = Samples.class.getDeclaredField("matrix");
TypeMark mark = matrix.getAnnotation(TypeMark.class);
```

`mark` không phải giá trị `outer` hoặc `inner` vì chúng là annotation **trên các chiều của kiểu mảng**, không phải annotation declaration trên `Field`. Phải bắt đầu bằng `matrix.getAnnotatedType()` và truy vấn theo cây `AnnotatedArrayType`.

## 14. Kiểm thử sâu cho generic lồng nhau và mảng lồng nhau

Với một thư viện xử lý annotation type-use tổng quát, không nên chỉ test một tầng `List<String>`. Hãy thêm các mẫu dữ liệu:

```java
import java.util.List;
import java.util.Map;

class ComplexTypes {
    Map<@TypeMark("map-key") String,
        List<@TypeMark("list-item") Integer>> nested;

    List<@TypeMark("element") String>
            @TypeMark("array") [] genericArray;

    @TypeMark("base") String @TypeMark("dimension") [] simpleArray;
}
```

Các kiểu test tương ứng:

| Vị trí | Đường đi qua reflection |
|---|---|
| `"map-key"` | `AnnotatedParameterizedType(Map)` → arg thứ 0 |
| `"list-item"` | `AnnotatedParameterizedType(Map)` → arg thứ 1 (`List`) → arg thứ 0 |
| `"array"` | `AnnotatedArrayType` ngoài cùng |
| `"element"` | `AnnotatedArrayType` → component là `AnnotatedParameterizedType(List)` → arg thứ 0 |
| `"dimension"` | `AnnotatedArrayType` ngoài cùng |
| `"base"` | `AnnotatedArrayType` → component `String` |

Nếu annotation hỗ trợ nhiều vị trí, một declaration có thể mang cả **annotation trên phần tử** và **annotation trên chiều mảng**. Test phải phân biệt hai địa chỉ ấy.

Một thuật toán duyệt cây annotated types thường cần phân nhánh:

```java
if (type instanceof AnnotatedArrayType arrayType) {
    // Xử lý annotation trên chiều mảng.
    // Duyệt arrayType.getAnnotatedGenericComponentType().
} else if (type instanceof AnnotatedParameterizedType parameterized) {
    // Xử lý annotation trên generic type.
    // Duyệt parameterized.getAnnotatedActualTypeArguments().
} else {
    // Kiểm tra annotation ở lá hoặc trên dạng AnnotatedType khác.
}
```

Đây là mảnh code minh họa trong một hàm có biến `AnnotatedType type` và các import tương ứng. Một bộ duyệt **đầy đủ** còn phải cân nhắc `AnnotatedTypeVariable`, `AnnotatedWildcardType`, bounds và owner types theo cấu trúc generic. Không nên cho rằng hai nhánh trên đã phủ mọi dạng kiểu Java.

## 15. Kiểm thử wildcard và type variable trong generic

Mô hình Java generic không chỉ có `List<String>`. Ví dụ:

```java
import java.util.List;

class Variance {
    List<? extends @TypeMark("upper") Number> upper;
    List<? super @TypeMark("lower") Integer> lower;
}
```

`? extends ...` và `? super ...` tạo **annotated wildcard type**. Truy vấn theo cấu trúc:

1. `Field.getAnnotatedType()` → `AnnotatedParameterizedType` cho `List`.
2. `getAnnotatedActualTypeArguments()[0]` → `AnnotatedWildcardType` cho wildcard.
3. `getAnnotatedUpperBounds()` hoặc `getAnnotatedLowerBounds()` → annotated type của bound.
4. `getAnnotation(TypeMark.class)` trên bound tương ứng.

Phân biệt annotation **trên dấu wildcard**:

```java
List<@TypeMark("wildcard") ? extends Number> example;
```

với annotation **trên kiểu bound**:

```java
List<? extends @TypeMark("bound") Number> example;
```

Để so sánh chính xác, test cả hai và chứng minh annotation nằm trên đối tượng `AnnotatedWildcardType` hay trên một `AnnotatedType` trả từ `getAnnotatedUpperBounds()`.

Đối với type variable sử dụng trong kiểu field:

```java
class Holder<@ParamMark("parameter") T> {
    @TypeMark("use") T item;
}
```

Annotation `ParamMark("parameter")` gắn vào **khai báo type parameter `T`**; `TypeMark("use")` gắn vào **vị trí sử dụng `T` trên field**. Test hai nơi bằng hai đường đọc riêng: `Holder.class.getTypeParameters()[0].getAnnotation(ParamMark.class)` và `Holder.class.getDeclaredField("item").getAnnotatedType().getAnnotation(TypeMark.class)`.

## 16. Record annotation và các bài test về propagation

Khi sử dụng annotation có nhiều targets, record header có thể ảnh hưởng metadata tại **nhiều phần tử sinh ra**.

Ví dụ:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface VisibleAt {
    String value();
}

record Order(@VisibleAt("id") String id) {}
```

Bộ test tích hợp có thể đặt bốn phép kiểm tra độc lập:

- `Order.class.getRecordComponents()[0].getAnnotation(VisibleAt.class)`.
- `Order.class.getDeclaredField("id").getAnnotation(VisibleAt.class)`.
- `Order.class.getDeclaredMethod("id").getAnnotation(VisibleAt.class)`.
- `Order.class.getDeclaredConstructor(String.class).getParameters()[0].getAnnotation(VisibleAt.class)`.

Với record **không tự định nghĩa lại accessor/canonical constructor**, các quy tắc record của Java sẽ quyết định sự lan truyền annotation tùy target. Nếu có accessor hoặc constructor **tường minh**, hãy viết test riêng vì propagation không nên được suy đoán là giống nhau cho mọi kiểu khai báo.

Để tránh regression khó phát hiện:

1. Kiểm thử **record declaration** và **type-use** riêng biệt.
2. Kiểm thử các thành phần ngầm sinh tương ứng với target.
3. Nếu người lập trình tự viết accessor/canonical constructor, kiểm thử **phiên bản tường minh**.
4. Không dùng `getDeclaredFields()` rồi cho rằng mọi field đều là “nguồn sự thật” của record component metadata.
5. Không xóa bỏ thông tin gắn trên `RecordComponent` chỉ vì một thư viện serializer chỉ quét field.

## 17. Kiểm thử compile-time và bytecode bên cạnh runtime

Reflection tốt cho annotation có retention `RUNTIME`, nhưng không đại diện toàn bộ hành vi của Java compiler.

### Test compile-time với annotation processor

Nếu annotation chỉ có retention `SOURCE`, có thể dùng một annotation processor (JSR 269) để xem `TypeElement`, `Element`, `AnnotationMirror` hoặc kiểu được biểu diễn bằng `TypeMirror` trong lúc biên dịch. Điều này phù hợp khi dự án cần kiểm tra metadata nguồn, sinh mã hay validate cấu trúc generic/record sớm.

Cần lưu ý:

- `RoundEnvironment.getElementsAnnotatedWith(...)` chủ yếu truy vấn annotation trên các **element** theo quy tắc processor; nó không tự thay thế việc duyệt mọi **type-use annotation** nằm sâu trong generic arguments và mảng.
- Để kiểm thử annotation trên type use, kiểm tra `TypeMirror.getAnnotationMirrors()` của **đúng TypeMirror** và sử dụng `Types`/`Elements` để đi qua cấu trúc kiểu.
- Một processor muốn nhận việc phải được đăng ký/khởi chạy; chỉ có `@Retention(SOURCE)` không tự tạo test.
- `Filer` sinh file mới và `Messager` báo diagnostic; không phải API reflection runtime.

### Test class-file

Khi annotation có retention `CLASS`, `javap -v` giúp xác nhận compiler đã ghi annotation vào classfile:

```bash
javap -v Samples
javap -v Entry
```

Trong output, tìm `RuntimeInvisibleTypeAnnotations` cho `TYPE_USE` có retention `CLASS` và `RuntimeVisibleTypeAnnotations` khi `RUNTIME`. Các declaration annotations có thể nằm trong thuộc tính khác, ví dụ `RuntimeVisibleAnnotations`. Với record, classfile còn có cấu trúc liên quan `Record` attribute.

**Cẩn thận:** `javap -v` hiển thị chi tiết classfile và constant pool, không phải giao diện ổn định để test bằng cách khớp nguyên văn toàn bộ stdout qua mọi phiên bản JDK. Hãy kiểm nội dung/target metadata cần thiết thay vì phụ thuộc số thứ tự constant-pool hoặc vị trí dòng in.

## 18. Bảng lỗi phổ biến và hướng sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `Field.getAnnotation` trả `null` cho `List<@Mark String>` | Annotation nằm ở type argument, không phải field declaration | `Field.getAnnotatedType()` → `AnnotatedParameterizedType` → arg |
| Annotation trên mảng “mất một chiều” | Chỉ đọc outer `AnnotatedArrayType` | Duyệt tiếp `getAnnotatedGenericComponentType()` |
| Annotation generic bound không xuất hiện trên `TypeVariable` | Đọc declaration thay vì bound | Dùng `getAnnotatedBounds()` |
| `TYPE_PARAMETER` annotation không thấy trên `List<String>` | Nhầm khai báo `T` với use `String` | Đọc `Class.getTypeParameters()` |
| Record component annotation không thấy trên field | Annotation chỉ target `RECORD_COMPONENT` | Đọc `RecordComponent.getAnnotation` |
| Record type-use annotation không thấy qua `RecordComponent.getAnnotation` | Metadata nằm trên kiểu component | Dùng `RecordComponent.getAnnotatedType()` |
| Test Java 17 compile lỗi với record | Cú pháp record không được hỗ trợ bởi JDK cũ/source level thấp | Kiểm `java -version`, `javac -version`, `--release` |
| Annotation visible trong source nhưng reflection không thấy | Retention `SOURCE`/`CLASS` hoặc sai target | Xem `@Retention`, `@Target`, bytecode |
| `ClassCastException` khi ép `AnnotatedType` | Giả định mọi field đều là parameterized/array | Dùng `instanceof` trước khi cast |
| Test phụ thuộc thứ tự method reflection | `getDeclaredMethods()` không cam kết thứ tự phù hợp test | Sắp xếp hoặc chọn method theo tên |
| Annotation ở generic type argument bị bỏ qua trong processor | Chỉ quét elements, không duyệt TypeMirror | Duyệt cây kiểu phù hợp |
| Record accessor do người dùng viết có metadata khác dự kiến | Lẫn implicit/explicit member propagation | Viết test riêng cho accessor/constructor tường minh |

Một số lỗi khác có thể xuất hiện khi generic signature hoặc annotation type không tải được lúc phản chiếu. Khi đó cần kiểm tra classpath, class loader, phiên bản dependency và output compiler thay vì cho rằng API luôn trả mảng rỗng.

## 19. Quy trình kiểm thử đề xuất cho dự án thực tế

Một bộ test bền vững có thể tổ chức theo ba lớp:

**Lớp 1 — Test biên dịch:** kiểm `@Target` hợp lệ/sai, tên class, generic signature, record syntax; nếu có processor, kiểm diagnostic phù hợp. Những đoạn cố ý không hợp lệ phải nằm trong **file test âm tính riêng**, không đặt vào bộ demo chạy bình thường.

**Lớp 2 — Test reflection:** với retention `RUNTIME`, tạo các fixture nhỏ chứa từng trường hợp và đọc đúng cây `AnnotatedType`/`RecordComponent`. Assertion nên kiểm tra cả annotation value, số lượng, vị trí và trường hợp không có.

**Lớp 3 — Test tích hợp:** nếu framework mapper, serializer hoặc DI đọc metadata, kiểm tra thật đường tiêu thụ ấy. Một annotation tồn tại qua reflection chưa chứng minh framework tự áp dụng hành vi mong muốn.

Gợi ý danh sách fixture tối thiểu:

1. Một generic type parameter có `@Target(TYPE_PARAMETER)`.
2. Một generic bound có `@Target(TYPE_USE)`.
3. Một `List<@Mark String>` và một `Map<K, List<V>>` lồng nhau.
4. Một mảng một chiều với annotation trên chiều mảng.
5. Một mảng hai chiều với annotation trên từng chiều.
6. Một annotation trên kiểu phần tử của mảng, không phải chiều.
7. Một record component có `@Target(RECORD_COMPONENT)`.
8. Một record component có type-use annotation ở kiểu.
9. Một record generic/mảng có annotation ở type argument/dimension.
10. Một record có accessor/canonical constructor tường minh nếu dự án dùng.
11. Một annotation `CLASS` chỉ kiểm bằng bytecode, không kiểm bằng runtime reflection.
12. Một fixture sai `@Target` dùng làm negative compilation test.

Với mỗi fixture, đặt tên rõ ràng như `GenericArgumentCase`, `ArrayDimensionsCase` hoặc `RecordComponentCase` và ghi lại **đường reflection mà test dự định đi qua**. Cách này giúp bài test phản ánh chủ đích nguồn thay vì vô tình pass do một annotation xuất hiện ở vị trí khác.

## 20. Bài tập tự kiểm tra

Xét các khai báo:

```java
import java.util.List;

class Example<
    @ParamMark("P") T extends @TypeMark("B") Number
> {
    List<@TypeMark("A") String> items;
    String @TypeMark("D1") [] @TypeMark("D2") [] matrix;
}

record RecordExample(
    @ComponentMark("RC")
    List<@TypeMark("G") String> values
) {}
```

Giả sử `ParamMark` target `TYPE_PARAMETER`; `TypeMark` target `TYPE_USE`; `ComponentMark` target `RECORD_COMPONENT`; cả ba đều retention `RUNTIME`.

Hãy xác định:

1. Muốn đọc `"P"`, cần bắt đầu ở API nào?
2. Muốn đọc `"B"`, nên hỏi annotation trên `T` trực tiếp hay trên annotated bound?
3. Muốn đọc `"A"` trong `items`, vì sao `Field.getAnnotation(TypeMark.class)` chưa đủ?
4. `"D1"` và `"D2"` nằm ở một hay hai đối tượng `AnnotatedArrayType`?
5. `RecordExample.class.getRecordComponents()[0].getAnnotation(ComponentMark.class)` cho giá trị gì?
6. Muốn đọc `"G"` ở `RecordExample.values`, phải dùng `RecordComponent.getAnnotatedType()` và tiếp theo API nào?
7. Nếu `TypeMark` đổi retention thành `CLASS`, `Field.getAnnotatedType().getAnnotation(TypeMark.class)` có còn đọc `"A"` khi chạy không?
8. Có thể khai báo annotation element `List<String> tags();` chỉ vì Java generic support `List` không?
9. Nếu `matrix` trở thành mảng một chiều, việc ép cấp thứ hai thành `AnnotatedArrayType` có còn hợp lệ không?
10. Khi annotation chỉ target `RECORD_COMPONENT`, có nên luôn kỳ vọng tìm nó trên accessor `values()` không?

**Đáp án:**

1. `Example.class.getTypeParameters()[0].getAnnotation(ParamMark.class)`.
2. `TypeVariable.getAnnotatedBounds()[0].getAnnotation(TypeMark.class)`.
3. Vì `"A"` nằm trên **type argument `String`**, cần `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.
4. **Hai tầng `AnnotatedArrayType`**: outer và inner.
5. Giá trị `"RC"`.
6. `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` để vào `String`.
7. **Không.** Retention `CLASS` không hiện qua runtime reflection chuẩn.
8. **Không.** Annotation element types có tập kiểu giới hạn, không có `List`.
9. **Không.** Phải kiểm tra cấu trúc annotated type trước khi cast.
10. **Không.** Annotation chỉ target `RECORD_COMPONENT` không được hiểu là method declaration annotation trên accessor.

## 21. Checklist cuối bài

- [ ] Biết annotation đang nhắm declaration hay type use.
- [ ] Chọn đúng `@Target(TYPE_PARAMETER)` cho khai báo tham số kiểu và `TYPE_USE` cho generic argument/bound/array dimension.
- [ ] Đặt `@Retention(RUNTIME)` nếu kiểm qua reflection; dùng bytecode tool khi cần kiểm metadata `CLASS`.
- [ ] Đọc annotation type parameter qua `TypeVariable`.
- [ ] Đọc generic bound qua `TypeVariable.getAnnotatedBounds()`.
- [ ] Đọc type argument qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.
- [ ] Đọc wildcard bound bằng `AnnotatedWildcardType` nếu có wildcard.
- [ ] Với mảng nhiều chiều, duyệt từng `AnnotatedArrayType` qua `getAnnotatedGenericComponentType()`.
- [ ] Phân biệt annotation trên **array dimension** với annotation trên **element type**.
- [ ] Với record, dùng `Class.getRecordComponents()` và `RecordComponent.getAnnotation(...)` khi annotation nhắm declaration.
- [ ] Đọc record component type-use annotation qua `RecordComponent.getAnnotatedType()`.
- [ ] Nếu test propagation, xem đúng target và phân biệt implicit/explicit accessor/constructor.
- [ ] Viết assertions cho giá trị, số lượng, vị trí và trường hợp không có.
- [ ] Đặt các ví dụ cố ý sai vào negative compilation tests riêng, không trộn với fixture chạy được.
- [ ] Không suy luận rằng framework sẽ hiểu annotation chỉ vì reflection có thể đọc nó.
- [ ] Tránh test dựa vào thứ tự không được API cam kết; lấy field/method/component có tên phù hợp.
- [ ] Chạy với source level/JDK hỗ trợ record (Java 17 là lựa chọn ổn định).
- [ ] Kiểm tra cả compile-time, class-file và runtime theo đúng mục đích của annotation.

## 22. Tài liệu đối chiếu

- [Java SE 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): giao diện chung cho annotation ở vị trí sử dụng kiểu.
- [`AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): các annotated type arguments của generic.
- [`AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html): annotation ở chiều mảng và việc đi tới component type.
- [`RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): metadata record component, annotated type và accessor.
- [JLS Java 17 — Chương 9](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): annotation types, `@Target` và nơi annotation có thể xuất hiện.
- [JLS Java 17 — Mục 8.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record classes và các thành phần liên quan.

**Tóm lại:** Kiểm thử annotation trên generic, mảng và record cần kiểm **vị trí metadata**, không chỉ kiểm “đã gắn annotation”. `TYPE_PARAMETER` và `TYPE_USE` ở hai tầng khác nhau; mảng có từng chiều riêng; record có declaration component riêng với type-use annotation. Khi dùng đúng `AnnotatedType`, `AnnotatedParameterizedType`, `AnnotatedArrayType` và `RecordComponent`, các phép thử trở nên minh bạch, chặt chẽ và chống regression tốt hơn.