# Phân biệt declaration annotation với type-use annotation trong Java Reflection

## 1. Vì sao cần phân biệt hai nơi gắn annotation?

Trong Java, annotation có thể mô tả **một khai báo** (*declaration*) hoặc **một vị trí sử dụng kiểu** (*type use*). Nhìn qua source, hai annotation đều bắt đầu bằng ký hiệu `@`, nhưng ý nghĩa và đường truy cập qua Reflection khác nhau.

Ví dụ:

```java
@Decl("field")
private @Use("type") List<@Use("element") String> names;
```

Đây là đoạn mã minh họa **nằm trong một class**, giả định `Decl` được phép đặt trên khai báo field, `Use` được phép đặt trên type use, và các annotation có retention phù hợp.

- `@Decl("field")` mô tả **khai báo field `names`**.
- `@Use("type")` mô tả **kiểu `List<...>` mà field sử dụng**.
- `@Use("element")` mô tả **kiểu đối số generic `String`** bên trong `List`.

Nếu chỉ gọi `field.getDeclaredAnnotations()`, chương trình có thể thấy declaration annotation mà **không** thấy annotation trên type-use. Muốn tìm type-use annotation, phải lấy cấu trúc `AnnotatedType` qua `field.getAnnotatedType()` và, khi cần, đi sâu vào type argument.

Bài học hướng tới ba năng lực:

1. Phân biệt vị trí và ngữ nghĩa của *declaration annotation* với *type-use annotation*.
2. Chọn đúng `@Target`, `@Retention` và API Reflection để đọc annotation ở Java 17+.
3. Không hiểu nhầm metadata runtime thành cơ chế kiểm tra kiểu tự động hoặc coi các loại annotation là hoàn toàn loại trừ nhau.

## 2. Declaration annotation là gì?

*Declaration annotation* gắn với **một khai báo chương trình**: class, interface, method, constructor, field, formal parameter, type parameter, v.v. Nó thường cung cấp metadata cho compiler, công cụ build hoặc framework.

Một số ví dụ quen thuộc:

- `@Override` trên khai báo method: compiler kiểm tra method có override/satisfy đúng hợp đồng hay không.
- `@Deprecated` trên khai báo class/member: mô tả API không còn khuyến nghị sử dụng.
- `@Entity` (trong thư viện ORM) trên class: một ví dụ về annotation mô tả declaration.
- Một annotation `@Route` tùy chỉnh trên method: metadata về điểm cuối.
- `@Qualifier` hoặc annotation tùy chỉnh trên parameter declaration: mô tả cách injection.

Annotation được phép đặt ở vị trí nào do meta-annotation `@Target` quy định.

| `ElementType` | Phạm vi khai báo điển hình |
| --- | --- |
| `TYPE` | Khai báo class, interface, enum, record và những kiểu tương ứng |
| `FIELD` | Khai báo field |
| `METHOD` | Khai báo method |
| `CONSTRUCTOR` | Khai báo constructor |
| `PARAMETER` | Khai báo formal parameter |
| `TYPE_PARAMETER` | Khai báo tham số kiểu generic như `T` |
| `LOCAL_VARIABLE` | Khai báo biến cục bộ |
| `ANNOTATION_TYPE` | Khai báo một annotation type |
| `PACKAGE` | Khai báo package |
| `MODULE` | Khai báo module |

Các mục trong bảng là một số `ElementType` liên quan đến đề bài; Java còn có `TYPE_USE` dành cho những vị trí sử dụng kiểu. Đừng hiểu `TYPE` và `TYPE_USE` là hai cách viết đồng nghĩa.

Định nghĩa annotation dành riêng cho khai báo field:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ColumnInfo {
    String value();
}
```

Dùng trên field:

```java
class Book {
    @ColumnInfo("book_title")
    private String title;
}
```

Sau khi compile, Reflection có thể tìm:

```java
java.lang.reflect.Field f = Book.class.getDeclaredField("title");
ColumnInfo info = f.getDeclaredAnnotation(ColumnInfo.class);
System.out.println(info.value()); // book_title
```

Đoạn truy vấn Reflection là **mã minh họa trong một phương thức** đã xử lý/khai báo `NoSuchFieldException`. Vì `ColumnInfo` có retention `RUNTIME` và gắn trên *field declaration*, đọc annotation trực tiếp từ `Field` là hợp lý.

## 3. Type-use annotation là gì?

*Type-use annotation* gắn với **một lần dùng kiểu** (*use of a type*): kiểu của field, kiểu trả về, kiểu parameter, kiểu đối số generic, thành phần mảng, kiểu superclass/interface, wildcard bound, cast, `new` expression và những ngữ cảnh type use khác theo luật Java.

Định nghĩa:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface MarkType {
    String value();
}
```

Các vị trí minh họa:

```java
class Basket {
    private @MarkType("field-type") String title;

    private java.util.List<@MarkType("element") String> labels;

    public @MarkType("return-type") String find(
            @MarkType("parameter-type") String key) {
        return key;
    }
}
```

Trong ví dụ, các dấu `@MarkType` áp dụng vào **vị trí kiểu** chứ không đơn giản là annotation của `Field` hoặc `Method`. Nếu muốn đọc `@MarkType("element")` trên `String` trong `List<String>`, phải đi vào cấu trúc `AnnotatedParameterizedType`.

Điểm quan trọng:

- `@Target(TYPE_USE)` cho phép annotation xuất hiện ở các **ngữ cảnh type use**; nó không biến annotation thành modifier `public`, `private` hay một kiểu mới tại runtime.
- `String` và `@MarkType String` vẫn dùng cùng kiểu Java `String` về mặt runtime class identity. Annotation chỉ thêm metadata.
- Compiler hoặc công cụ phân tích static có thể dùng type-use annotations để kiểm tra nullness, ownership, thread-safety, v.v., **nếu** có bộ kiểm tra hỗ trợ. Java/JVM không tự biết `@NonNull` tùy chỉnh phải chặn null ra sao.
- Một annotation có `@Retention(RUNTIME)` có thể được Reflection đọc tại **những vị trí type use mà API Reflection biểu diễn được**. Không phải mọi annotation trong mọi biểu thức source đều có API Reflection mức cao để truy vấn.

## 4. Một bảng đối chiếu vị trí và API

| Điều muốn quan sát | Đối tượng Reflection | API chính |
| --- | --- | --- |
| Annotation trên khai báo class | `Class<?>` | `getDeclaredAnnotations()`, `getDeclaredAnnotation(T.class)` |
| Annotation trên khai báo field | `Field` | `getDeclaredAnnotations()`, `getDeclaredAnnotation(T.class)` |
| Annotation trên **kiểu của field** | `Field` → `AnnotatedType` | `field.getAnnotatedType().getAnnotations()` |
| Annotation trên khai báo method | `Method` | `method.getDeclaredAnnotations()` |
| Annotation trên **kiểu trả về method** | `Method` → `AnnotatedType` | `method.getAnnotatedReturnType().getAnnotations()` |
| Annotation trên khai báo parameter | `Parameter` | `parameter.getAnnotations()` hoặc `getDeclaredAnnotations()` |
| Annotation trên **kiểu của parameter** | `Parameter` → `AnnotatedType` | `parameter.getAnnotatedType().getAnnotations()` |
| Annotation trên kiểu exception trong `throws` | `Executable`/`Method` | `getAnnotatedExceptionTypes()` |
| Annotation trên kiểu superclass | `Class<?>` | `getAnnotatedSuperclass()` |
| Annotation trên kiểu implemented interfaces | `Class<?>` | `getAnnotatedInterfaces()` |
| Annotation trên đối số generic như `List<@T String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| Annotation trên thành phần kiểu mảng | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| Annotation trên bound của wildcard | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`/`getAnnotatedLowerBounds()` |
| Annotation trên bound của type variable | `TypeVariable<?>` | `getAnnotatedBounds()` |
| Annotation trên khai báo type parameter `T` | `TypeVariable<?>` | `getAnnotations()`/`getDeclaredAnnotations()` |

**Không nhầm:** `Field.getGenericType()` trả về `Type` có thông tin về generic signature nhưng **không đủ** để lấy toàn bộ annotation nằm trên từng phần của kiểu. Khi cần annotation, dùng họ `getAnnotated...` và các subtype của `AnnotatedType`.

## 5. Ví dụ hoàn chỉnh Java 17+: một annotation gắn declaration, một annotation gắn type use

Lưu nguyên nội dung sau vào tệp **`AnnotationLocationDemo.java`**. Chương trình dùng hai annotation độc lập:

- `@Decl`: chỉ áp dụng trên các **declaration** như class, field, method và parameter.
- `@Use`: chỉ khai báo `@Target(TYPE_USE)` để đánh dấu những **vị trí sử dụng kiểu**.

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD,
         ElementType.METHOD, ElementType.PARAMETER})
@interface Decl {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Use {
    String value();
}

class Base {}

@Decl("class")
class Example extends @Use("base") Base
              implements @Use("interface") Runnable {

    @Decl("field")
    private @Use("field-type") List<@Use("element") String> names;

    @Decl("method")
    public @Use("return") List<@Use("return-element") String> process(
            @Decl("parameter") @Use("param-type") String input) {
        return List.of(input);
    }

    @Override
    public void run() {}
}

public class AnnotationLocationDemo {
    private static String declared(AnnotatedElement element) {
        Decl annotation = element.getDeclaredAnnotation(Decl.class);
        return annotation == null ? "-" : annotation.value();
    }

    private static String typeUse(AnnotatedType type) {
        Use annotation = type.getAnnotation(Use.class);
        return annotation == null ? "-" : annotation.value();
    }

    public static void main(String[] args) throws Exception {
        Class<Example> type = Example.class;
        Field field = type.getDeclaredField("names");
        Method method = type.getDeclaredMethod("process", String.class);
        Parameter parameter = method.getParameters()[0];

        AnnotatedParameterizedType fieldType =
                (AnnotatedParameterizedType) field.getAnnotatedType();
        AnnotatedParameterizedType returnType =
                (AnnotatedParameterizedType) method.getAnnotatedReturnType();

        System.out.println("class declaration: " + declared(type));
        System.out.println("field declaration: " + declared(field));
        System.out.println("field type: " + typeUse(fieldType));
        System.out.println("generic argument: "
                + typeUse(fieldType.getAnnotatedActualTypeArguments()[0]));
        System.out.println("method declaration: " + declared(method));
        System.out.println("method return type: " + typeUse(returnType));
        System.out.println("return argument: "
                + typeUse(returnType.getAnnotatedActualTypeArguments()[0]));
        System.out.println("parameter declaration: "
                + declared(parameter));
        System.out.println("parameter type: "
                + typeUse(parameter.getAnnotatedType()));
        System.out.println("superclass type: "
                + typeUse(type.getAnnotatedSuperclass()));
        System.out.println("interface type: "
                + typeUse(type.getAnnotatedInterfaces()[0]));

        System.out.println("field use on declaration: "
                + (field.getDeclaredAnnotation(Use.class) != null));
        System.out.println("field decl on type: "
                + (field.getAnnotatedType().getAnnotation(Decl.class) != null));
    }
}
```

Biên dịch theo chuẩn Java 17 và chạy:

```bash
javac --release 17 AnnotationLocationDemo.java
java AnnotationLocationDemo
```

Output từ chương trình:

```text
class declaration: class
field declaration: field
field type: field-type
generic argument: element
method declaration: method
method return type: return
return argument: return-element
parameter declaration: parameter
parameter type: param-type
superclass type: base
interface type: interface
field use on declaration: false
field decl on type: false
```

Ví dụ cố tình không tạo instance `Example`; chỉ dùng metadata ở runtime. Tất cả class/annotation phụ được đặt trong cùng một file Java để `javac` biên dịch được mà không cần thêm thư viện.

## 6. Giải thích cách đọc kết quả

### 6.1. Class declaration

`@Decl("class")` được gắn trên khai báo `class Example` vì `Decl` cho phép `ElementType.TYPE`.

```java
Decl d = Example.class.getDeclaredAnnotation(Decl.class);
```

Đây là truy vấn trực tiếp annotation của **Class**. Nó khác annotation ở `extends @Use Base` hoặc `implements @Use Runnable`: hai chỗ đó là **type use** của superclass/interface và phải tìm qua `getAnnotatedSuperclass()`, `getAnnotatedInterfaces()`.

### 6.2. Field declaration và field type

Ví dụ:

```java
@Decl("field")
private @Use("field-type") List<@Use("element") String> names;
```

Ba mục metadata khác nhau:

1. `field.getDeclaredAnnotation(Decl.class)` trả `@Decl("field")`.
2. `field.getAnnotatedType().getAnnotation(Use.class)` trả `@Use("field-type")`.
3. `((AnnotatedParameterizedType) field.getAnnotatedType()).getAnnotatedActualTypeArguments()[0].getAnnotation(Use.class)` trả `@Use("element")` trên đối số generic `String`.

**Vì sao không thể chỉ gọi `field.getDeclaredAnnotations()`?** Vì API đó hỏi annotation gắn trực tiếp vào **khai báo field**. Annotation dùng để mô tả **kiểu field** và **kiểu phần tử generic** nằm trong một nhánh metadata khác, được biểu diễn qua `AnnotatedType`.

### 6.3. Method declaration và return type

`@Decl("method")` đánh dấu method declaration `process`. `@Use("return")` đánh dấu **kiểu trả về `List<...>`**; `@Use("return-element")` đánh dấu **generic type argument String** của return type.

Do đó:

```java
method.getDeclaredAnnotation(Decl.class); // @Decl("method")
method.getAnnotatedReturnType()
      .getAnnotation(Use.class);           // @Use("return")
```

Muốn thấy `return-element`, lấy `AnnotatedParameterizedType` và duyệt `getAnnotatedActualTypeArguments()`. API `method.getReturnType()` chỉ trả `List.class` và không chứa vị trí annotation trên `String`.

### 6.4. Parameter declaration và parameter type

Trong khai báo:

```java
@Decl("parameter") @Use("param-type") String input
```

Hai annotation ở hai ngữ nghĩa khác nhau:

- `parameter.getDeclaredAnnotation(Decl.class)`: annotation của **parameter declaration**.
- `parameter.getAnnotatedType().getAnnotation(Use.class)`: annotation của **kiểu String** được parameter sử dụng.

Không nên suy luận rằng `method.getParameterAnnotations()` đủ để đọc mọi type-use annotation. API đó cung cấp annotation trên các parameter declaration; để lấy annotation của kiểu tham số, dùng `getAnnotatedParameterTypes()` hoặc `Parameter.getAnnotatedType()`.

### 6.5. Annotated superclass và interfaces

`Example extends @Use("base") Base implements @Use("interface") Runnable` chứa hai type-use annotation ở **vị trí dùng kiểu**. Lấy:

```java
AnnotatedType parent = Example.class.getAnnotatedSuperclass();
AnnotatedType[] interfaces = Example.class.getAnnotatedInterfaces();
```

Sau đó kiểm tra `getAnnotation(Use.class)` trên từng `AnnotatedType`.

Điểm khác biệt: `Example.class.getDeclaredAnnotations()` mô tả annotation của **declaration class Example**, không thay thế các API annotated superclass/interface.

### 6.6. Hai dòng false là bằng chứng gì?

- `field.getDeclaredAnnotation(Use.class) == null`: trong ví dụ này, `@Use("field-type")` không xuất hiện như annotation của **field declaration**.
- `field.getAnnotatedType().getAnnotation(Decl.class) == null`: `@Decl("field")` không mô tả **kiểu field**.

Hai dòng cuối in `false`. Chúng minh họa sự phân tách metadata rõ ràng vì ví dụ sử dụng hai annotation có `@Target` riêng biệt.

**Không tổng quát hóa thành “một annotation không thể vừa là declaration annotation vừa là type-use annotation”.** Trong các ngữ cảnh và `@Target` khác, cùng loại annotation có thể được phép đặt ở cả declaration và type use. Phần tiếp theo giải thích giới hạn này.

## 7. @Target quyết định vị trí hợp lệ, không chỉ là tên annotation

Một annotation có thể được khai báo:

```java
@Target(ElementType.FIELD)
@interface FieldOnly {}

@Target(ElementType.TYPE_USE)
@interface TypeOnly {}

@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface EitherLocation {}
```

Đây là đoạn minh họa về `@Target` (giả định đã `import java.lang.annotation.*;`). Khi thiếu `@Retention(RUNTIME)`, chúng không phải ví dụ phù hợp để truy vấn runtime bằng Reflection; chỉ dùng để so sánh target.

| Target | Ý định |
| --- | --- |
| `FIELD` | Gắn annotation trên field declaration |
| `TYPE_USE` | Gắn annotation ở nơi kiểu được dùng, ví dụ kiểu field/generic argument |
| `FIELD, TYPE_USE` | Annotation có thể được sử dụng ở cả hai dạng vị trí theo quy tắc Java |
| `PARAMETER` | Mô tả parameter declaration |
| `TYPE_PARAMETER` | Mô tả khai báo type parameter generic |
| `TYPE` | Mô tả khai báo class/interface/những kiểu phù hợp |

### Một nuance quan trọng: TYPE_USE không hoàn toàn tách rời declaration

Theo luật Java, `TYPE_USE` còn áp dụng được tại **một số vị trí khai báo kiểu**, bao gồm khai báo class/interface và type parameter. Do đó, từ dòng source có vẻ “đặt annotation trước tên class” không thể khẳng định annotation đó chỉ là một declaration annotation và không thể là type-use annotation.

Hơn nữa, một annotation khai báo target gồm **cả `FIELD` và `TYPE_USE`** có thể khiến annotation ở vị trí phù hợp được compiler ghi nhận cho cả declaration và type use. Khi soạn công cụ phân tích, hãy xác định rõ **metadata bạn muốn đọc** (declaration hay type position), dùng API tương ứng, và kiểm tra output của compiler nếu ngữ cảnh có nhiều `@Target`.

Hai loại metadata là hai **chiều mô tả**, không phải hai nhóm Java type loại trừ nhau bằng nhãn tuyệt đối.

## 8. @Retention ảnh hưởng trực tiếp đến Reflection

`@Target` xác định **nơi đặt annotation hợp lệ**; `@Retention` xác định **thông tin được giữ đến giai đoạn nào**.

| Retention policy | Annotation được giữ đến đâu? | Runtime Reflection |
| --- | --- | --- |
| `SOURCE` | Dành cho source/processor, thường không lưu trong class file | Không đọc được tại runtime |
| `CLASS` | Có thể lưu trong class file nhưng không phải runtime-visible | Không được API Reflection chuẩn trả lại |
| `RUNTIME` | Lưu trong class file dưới metadata runtime-visible phù hợp | Có thể đọc được qua Reflection **nếu API hỗ trợ vị trí đó** |

Ví dụ runnable dùng:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Use { String value(); }
```

Nếu bỏ `RetentionPolicy.RUNTIME`, annotation mặc định retention `CLASS` và các lời gọi `getAnnotation(Use.class)` trong chương trình thường không thấy type-use metadata. Vì vậy, khi nhận kết quả `null`, cần kiểm tra **retention**, **target**, **đúng phần tử/type position**, và **metadata sau biên dịch** trước khi nghĩ Reflection gặp lỗi.

Không nên mặc định “có trong source” = “có trong runtime Reflection”.

## 9. Định tuyến theo hình dạng `AnnotatedType`

Khi một kiểu phức hợp chứa nhiều vị trí annotation, trước hết lấy `AnnotatedType` từ nơi khai báo (`Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()`, v.v.). `getType()` trả **kiểu nền** dạng `Type`; `getAnnotations()` chỉ trả annotation của **vị trí hiện tại**, không tự gom các nhánh con.

| Nếu nút là | Cách truy cập annotation nằm sâu hơn |
| --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` cho từng đối số generic; `getAnnotatedOwnerType()` khi có owner |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` để xuống từng chiều rồi tới phần tử |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` cho `? extends` / `? super` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` cho ràng buộc của biến kiểu |
| `AnnotatedType` đơn giản | Đọc annotation của nút; có thể không có nhánh con |

Ví dụ, `List<@Use("item") String>` có annotation ở **đối số String**, nên phải đi qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`, không hỏi `List.class` hay `Field.getDeclaredAnnotations()`. Tương tự, `? extends @Use("bound") Number` có marker ở upper bound, còn `String @Use("dimension") []` đánh dấu chiều mảng.

Một type parameter như `<@ParameterMark T extends @Use("bound") Number>` có **annotation khai báo trên T** (đọc qua `TypeVariable.getAnnotations()`) và **annotation type-use trên bound** (đọc qua `TypeVariable.getAnnotatedBounds()`): đây là hai nơi riêng biệt. Các bài sau xây ví dụ sâu cho từng dạng nút, receiver/exception/return type và hierarchy.

Khi viết trình duyệt đệ quy tổng quát, cần giữ **đường dẫn của từng vị trí**, khám phá owner khi có, và chống vòng lặp bound kiểu `T extends Comparable<T>`. Chương “Xây dựng trình duyệt cây kiểu mà vẫn giữ vị trí annotation” cung cấp visitor có bảo vệ chu trình; không dùng đệ quy bounds vô điều kiện trong production.

## 10. Declaration và type-use ở parameter khác nhau như thế nào?

Giả sử một framework injection dùng annotation `@FromHeader` trên parameter declaration và một static checker dùng `@NonNull` dạng type use.

```java
void send(
    @FromHeader("X-Request") @NonNull String requestId) {
}
```

Đoạn là **minh họa**: hai loại annotation chưa được định nghĩa trong bài, vì vậy không phải chương trình độc lập. `@FromHeader` mô tả **nguồn dữ liệu của parameter**; `@NonNull` mô tả **hợp đồng của kiểu String tại vị trí sử dụng**.

Một framework có thể đọc:

```java
Parameter parameter = method.getParameters()[0];
Annotation[] declaration = parameter.getDeclaredAnnotations();
Annotation[] typeUse = parameter.getAnnotatedType().getAnnotations();
```

Nếu mỗi annotation được định nghĩa đúng `@Target`/`@Retention`, hai mảng có thể phản ánh metadata khác nhau. Không dùng `getParameterAnnotations()` làm đường duy nhất để thu thập contract type-use, và không dùng `getAnnotatedParameterTypes()` để thay thế thông tin injection gắn với parameter declaration.

## 11. Declaration annotation khác type-use annotation ở method

Xem ý nghĩa của hai annotation:

```java
@Transaction
public @NonNull String findUser() {
    return "Ada";
}
```

Đây là đoạn minh họa, chưa định nghĩa `Transaction`/`NonNull`.

- `@Transaction` mô tả **method declaration**: yêu cầu giao dịch (nếu framework hỗ trợ).
- `@NonNull` mô tả **kiểu trả về String**: thông tin giúp công cụ static-checker hoặc framework kiểm tra kết quả (nếu framework áp dụng).

API:

```java
method.getDeclaredAnnotation(Transaction.class);
method.getAnnotatedReturnType().getAnnotation(NonNull.class);
```

Lựa chọn API xuất phát từ câu hỏi: “Thông tin này mô tả **lời khai báo một method** hay **kiểu của giá trị trả về**?”

Với generic return `List<@NonNull String>`, `@NonNull` còn có thể gắn vào **type argument**, phải duyệt `AnnotatedParameterizedType`.

## 12. Type-use annotation không mặc nhiên thay đổi hành vi Java

Giả sử một annotation có tên `@NonNull`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}
```

Nếu không có checker/framework chuyên biệt, Java/JVM **không tự ném lỗi** chỉ vì một biến `@NonNull String` nhận giá trị null. Annotation là metadata, không phải cơ chế tự động thêm câu lệnh `if (value == null) throw ...`.

Với các annotation kiểu @Nullable/@NonNull, hiệu lực còn tùy **bộ công cụ**: static analysis, annotation processor, compiler plugin, library runtime validation, v.v. Đừng đánh đồng việc Reflection **đọc thấy metadata** với việc JVM tự thi hành hợp đồng đó.

Tương tự, type-use annotation không tạo ra một `Class<?>` mới: `String.class` vẫn là `String.class` dù những chỗ dùng kiểu `String` được gắn các annotation khác nhau.

## 13. Ranh giới của Reflection: không đọc được mọi type use trong body

Các vị trí type use xuất hiện ở:

- Kiểu của field, kiểu trả về và tham số method.
- Generic arguments và các bound.
- Superclass/interface được khai báo.
- Kiểu trong `throws`.
- Kiểu tại `new`, cast, `instanceof`, local variable, lambda và nhiều expression khác.

Java Reflection cung cấp API khá phong phú cho **declaration signatures** và các annotated types liên quan, nhưng **không phải trình phân tích toàn bộ method body**. Annotation trên local variable, cast hay expression trong bytecode thường cần công cụ đọc class file/bytecode như ASM nếu muốn phân tích đúng type annotation attributes và vị trí target.

Do đó một scanner chỉ chạy `Class.getDeclaredFields()` rồi `Field.getAnnotatedType()` **không thể chứng minh** rằng trong thân mọi method không có type-use annotation khác. Phạm vi công cụ là metadata API thực sự cung cấp.

Với runtime annotation trong class file, sự phân tách thường tương ứng với các attribute liên quan đến declaration annotations và **runtime-visible type annotations**; chúng không được xem là cùng một danh sách phẳng.

## 14. Những lỗi phổ biến khi dùng Reflection với annotation

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `Field.getAnnotations()` để tìm type annotation của `List<@X String>` | Field declaration khác type argument | Dùng `getAnnotatedType()` rồi duyệt `AnnotatedParameterizedType` |
| Dùng `Method.getAnnotations()` để tìm `@X` trên return type | Method declaration khác return type | Dùng `getAnnotatedReturnType()` |
| Dùng `Parameter.getAnnotations()` để tìm mọi type-use annotation | Parameter declaration không bao quát annotation trên kiểu | Dùng `Parameter.getAnnotatedType()` |
| Quên `Retention(RUNTIME)` | Metadata không runtime-visible | Định nghĩa retention đúng khi cần runtime Reflection |
| Chỉ xem `getReturnType()` hoặc `getGenericReturnType()` | Không lấy annotation từng vị trí type use | Sử dụng `getAnnotatedReturnType()` và subtype liên quan |
| Coi `TYPE` tương đương `TYPE_USE` | Hai ngữ nghĩa và target không đồng nhất | Phân biệt khai báo class với các vị trí sử dụng kiểu |
| Coi annotation type-use là JVM validation | Metadata không tự bắt lỗi | Tích hợp checker hoặc runtime validation nếu cần |
| Nghĩ `TYPE_USE` không bao giờ xuất hiện ở declaration | Một số type declaration/type parameter declaration cũng hợp lệ | Hiểu quy tắc `@Target` và kiểm tra metadata đúng API |
| Chỉ quan sát outermost generic type | Bỏ sót annotation trên nested type arguments | Duyệt đệ quy `AnnotatedParameterizedType`, array/wildcard/bounds |
| Giả định Reflection hiểu annotation trong method body | API mức cao không biểu diễn mọi vị trí expression/local | Dùng bytecode scanner khi yêu cầu bao phủ body |
| Dựa vào vị trí hiển thị của dấu `@` để đoán storage | Có context áp dụng kép hoặc annotation nhiều target | Xác định ý nghĩa annotation và kiểm tra class file nếu cần |

## 15. Mẫu xử lý thông tin theo đúng vai trò

### 15.1. Xây dựng field scanner

Khi quét field, tách hai luồng:

```java
static void inspectField(java.lang.reflect.Field field) {
    // Metadata thuộc chính khai báo field:
    java.lang.annotation.Annotation[] fieldAnnotations =
            field.getDeclaredAnnotations();

    // Metadata trên type use của field:
    java.lang.reflect.AnnotatedType type = field.getAnnotatedType();
    java.lang.annotation.Annotation[] typeAnnotations =
            type.getAnnotations();

    System.out.println("Declaration: " + fieldAnnotations.length);
    System.out.println("Type use: " + typeAnnotations.length);
}
```

Đây là method Java hoàn chỉnh khi đặt trong một class, không bao gồm việc duyệt các generic arguments: nếu `field.getAnnotatedType()` là `AnnotatedParameterizedType`, cần đọc các type argument riêng theo mục 9.

### 15.2. Đọc type-use annotation trong generic

Nếu scanner cần biết annotation trên từng đối số trực tiếp của `List` hoặc `Map`, hãy đọc theo từng nút:

```java
static void inspectArguments(java.lang.reflect.Field field) {
    if (field.getAnnotatedType()
            instanceof java.lang.reflect.AnnotatedParameterizedType p) {
        for (java.lang.reflect.AnnotatedType arg
                : p.getAnnotatedActualTypeArguments()) {
            System.out.println(arg.getType().getTypeName()
                    + ": " + java.util.Arrays.toString(arg.getAnnotations()));
        }
    }
}
```

Đoạn này xử lý **một cấp đối số generic** và không tự gom annotation sâu hơn. Nếu cần duyệt mảng, wildcard, nested generic, owner và type-variable bounds, sử dụng visitor có đường dẫn/cycle guard ở bài cuối chương. Cách giới hạn phạm vi giữ ví dụ an toàn trước recursive bounds và không làm mất trọng tâm declaration vs type use.

### 15.3. Khi chỉ cần declaration metadata

Nếu annotation thiết kế rõ `@Target(FIELD)`, hãy đọc trực tiếp từ `Field`:

```java
ColumnInfo column = field.getDeclaredAnnotation(ColumnInfo.class);
```

Không cần duyệt `AnnotatedType` chỉ để tìm declaration annotation. Hai hệ API nên được sử dụng bổ trợ đúng mục tiêu.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt giữa `@Decl` trên field declaration và `@Use` trên kiểu của field là gì?

**Đáp án:** `@Decl` mô tả member được khai báo, còn `@Use` mô tả một vị trí sử dụng kiểu. Với runtime Reflection, `Field.getDeclaredAnnotation` và `Field.getAnnotatedType().getAnnotation` đọc hai vị trí tương ứng.

**Câu 2.** Muốn đọc `@X` từ `List<@X String>`, có đủ chỉ gọi `field.getDeclaredAnnotations()` không?

**Đáp án:** Không. Cần lấy `field.getAnnotatedType()`, cast đúng loại `AnnotatedParameterizedType`, duyệt `getAnnotatedActualTypeArguments()` rồi đọc annotation trên type argument `String`.

**Câu 3.** Method có `@Audit` trên declaration và `@NonNull` trên return type. Nên dùng API nào?

**Đáp án:** `method.getDeclaredAnnotation(Audit.class)` cho declaration; `method.getAnnotatedReturnType().getAnnotation(NonNull.class)` cho return type.

**Câu 4.** `@Target(TYPE_USE)` có tự bảo đảm JVM cấm gán null cho biến được annotate `@NonNull` không?

**Đáp án:** Không. Annotation là metadata; phải có checker/framework thực thi quy tắc.

**Câu 5.** `@Target(TYPE)` và `@Target(TYPE_USE)` có đồng nghĩa không?

**Đáp án:** Không. `TYPE` chủ yếu dành cho type declarations, còn `TYPE_USE` dành cho vị trí sử dụng kiểu và cũng được phép ở một số khai báo kiểu/type parameter theo luật Java.

**Câu 6.** Vì sao `@Retention(RUNTIME)` quan trọng?

**Đáp án:** Nếu annotation không được giữ đến runtime, Reflection chuẩn không thể đọc nó ở thời điểm chương trình chạy, dù annotation xuất hiện trong source.

**Câu 7.** Có thể dùng `getAnnotatedSuperclass()` để đọc annotation trên `extends @X Base` không?

**Đáp án:** Có. Đây là metadata tại vị trí **type use** của superclass, khác annotation trên declaration của subclass.

**Câu 8.** Java Reflection có thể liệt kê mọi type-use annotation trên cast và local variable trong body method không?

**Đáp án:** Không qua các API mức cao về signature thông thường. Muốn đọc metadata loại này đầy đủ cần công cụ phân tích bytecode/class file phù hợp.

**Câu 9.** Một annotation có `@Target({FIELD, TYPE_USE})` có thể xuất hiện liên quan đến cả declaration và type-use metadata không?

**Đáp án:** Có những ngữ cảnh mà annotation áp dụng được cho cả hai dạng. Vì vậy cần xem `@Target`, ngữ cảnh cú pháp và metadata thực của class file; không khẳng định hai miền hoàn toàn loại trừ nhau.

**Ghi nhớ:** *Declaration annotation* trả lời “thành phần chương trình nào được khai báo và mô tả ra sao?”, còn *type-use annotation* trả lời “kiểu đang được sử dụng tại vị trí nào và mang metadata gì?”. Trong Reflection, API trên `Class`/`Field`/`Method`/`Parameter` đọc declaration metadata; họ API `getAnnotated...` và `AnnotatedType` đọc metadata của những **type positions**. Chọn API theo vị trí, bảo đảm `@Target`/`@Retention` phù hợp và đừng đồng nhất metadata với cơ chế validation tự động.
