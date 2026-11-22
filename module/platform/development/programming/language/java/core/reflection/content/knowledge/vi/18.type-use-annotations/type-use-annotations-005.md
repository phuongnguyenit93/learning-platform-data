# AnnotatedWildcardType và annotation trên bound trong Java Reflection

## 1. Bối cảnh: annotation có thể nằm ngay trên dấu `?` hoặc trên bound

Trong Java, wildcard là đối số kiểu dùng trong generic, chẳng hạn `List<?>`, `List<? extends Number>` và `List<? super Integer>`. Từ Java 8, annotation có `@Target(ElementType.TYPE_USE)` có thể xuất hiện **tại những vị trí sử dụng kiểu** (type use), bao gồm wildcard và kiểu của bound.

Hai vị trí khác nhau:

```java
List<@Mark("wildcard") ? extends @Mark("bound") Number> values;
```

- `@Mark("wildcard")` nằm **trên chính wildcard `?`**.
- `@Mark("bound")` nằm **trên kiểu `Number`** sau từ khóa `extends`.

Hai annotation này không thay thế nhau, dù cùng xuất hiện trong một khai báo generic. Khi dùng Reflection:

- `AnnotatedWildcardType.getAnnotation(Mark.class)` đọc annotation gắn với `?`.
- `AnnotatedWildcardType.getAnnotatedUpperBounds()[0].getAnnotation(Mark.class)` đọc annotation gắn với upper bound `Number`.

Nếu chỉ lấy `WildcardType` qua `Field.getGenericType()` rồi gọi `getUpperBounds()`, bạn quan sát được **kiểu của bound**, nhưng **không đọc được annotation type-use của bound** bằng API `Type` thuần. Muốn giữ thông tin annotation theo vị trí, cần nhánh `AnnotatedType` và các interface con.

**Mục tiêu:** hiểu `AnnotatedWildcardType`, truy cập annotation ở wildcard/upper bound/lower bound, trường hợp bound ngầm định, duyệt generic lồng nhau và các giới hạn của metadata runtime trong Java 17+.

## 2. Wildcard và bound theo ngôn ngữ Java

Ba hình thức thường gặp:

| Viết trong Java | Upper bound | Lower bound | Ý nghĩa kiểu |
| --- | --- | --- | --- |
| `?` | `Object` ngầm định | Không có lower bound tường minh | Wildcard không giới hạn tường minh |
| `? extends Number` | `Number` tường minh | Không có lower bound tường minh | Đối số kiểu chưa biết, bị chặn trên bởi `Number` |
| `? super Integer` | `Object` ngầm định | `Integer` tường minh | Đối số kiểu chưa biết, bị chặn dưới bởi `Integer` |

Ví dụ về annotation tại từng vị trí:

```java
List<@Mark("any") ?> any;
List<@Mark("wild") ? extends @Mark("upper") Number> upper;
List<@Mark("wild") ? super @Mark("lower") Integer> lower;
List<? extends @Mark("onlyUpper") Number> onlyUpper;
```

Các ví dụ là **khai báo field minh họa**; `Mark` cần được định nghĩa với `TYPE_USE` và `RUNTIME` như trong ví dụ đầy đủ ở mục 5.

Hãy chú ý cú pháp:

- `@Mark("wild") ?`: annotation ở **wildcard node**.
- `? extends @Mark("upper") Number`: annotation ở **upper-bound type node**.
- `? super @Mark("lower") Integer`: annotation ở **lower-bound type node**.
- `?` không có bound tường minh nhưng theo Reflection vẫn có upper bound là `Object` không được annotate.

Với cú pháp wildcard Java hiện nay, một wildcard không vừa có `extends` vừa có `super`, và không viết được một intersection bound dạng `? extends A & B` trong Java source. Tuy nhiên, các phương thức Reflection trả về **mảng** các bound; mã xử lý nên duyệt mảng thay vì tự giả định mọi runtime chỉ có phần tử [0].

## 3. `AnnotatedWildcardType` nằm ở đâu trong Reflection?

`java.lang.reflect.AnnotatedWildcardType` là interface mở rộng `AnnotatedType` (từ Java 8), đại diện cho wildcard type argument có thể được annotate; các upper/lower bounds cũng có thể mang annotation.

Các API chính:

| API | Trả về | Điều cần nhớ |
| --- | --- | --- |
| `AnnotatedWildcardType.getType()` | `Type` (thường là `WildcardType`) | Cho hình dạng generic, không phải nơi đọc annotation trên bound |
| `getAnnotations()` | `Annotation[]` | Annotation ở chính node wildcard |
| `getAnnotation(Mark.class)` | `Mark` hoặc `null` | Trực tiếp hỏi marker tại wildcard |
| `getAnnotatedUpperBounds()` | `AnnotatedType[]` | Bound phía trên **có thể có annotation riêng** |
| `getAnnotatedLowerBounds()` | `AnnotatedType[]` | Bound phía dưới **có thể có annotation riêng** |
| `getAnnotatedOwnerType()` | `null` với wildcard | Không phải API để truy cập upper/lower bound |

`AnnotatedWildcardType` thuộc nhánh **annotated**. Nó khác `java.lang.reflect.WildcardType`:

```java
WildcardType wildcard = (WildcardType) annotatedWildcard.getType();
Type[] upperTypes = wildcard.getUpperBounds();
Type[] lowerTypes = wildcard.getLowerBounds();

AnnotatedType[] annotatedUpper =
        annotatedWildcard.getAnnotatedUpperBounds();
AnnotatedType[] annotatedLower =
        annotatedWildcard.getAnnotatedLowerBounds();
```

Đây là **đoạn minh họa**: cần import `java.lang.reflect.*` và có biến `annotatedWildcard` đã được xác định.

- `WildcardType.getUpperBounds()` và `getLowerBounds()` trả kiểu generic thuần (`Type`), ví dụ `Number.class` hoặc `Integer.class`.
- `AnnotatedWildcardType.getAnnotatedUpperBounds()` và `getAnnotatedLowerBounds()` trả `AnnotatedType`, vừa chứa kiểu, vừa cho phép đọc annotation tại vị trí type-use của bound.
- `AnnotatedType.getType()` của bound cho kiểu liên quan; `AnnotatedType.getAnnotation(...)` cho annotation gắn **đúng bound đó**.

Nếu cần annotation ở wildcard **lẫn** annotation ở bound, không được chọn một trong hai loại metadata rồi bỏ loại kia.

## 4. Đi tới wildcard đúng cách từ Field, Method, Parameter

Giả sử có field:

```java
List<@Mark("wildcard") ? extends @Mark("bound") Number> numbers;
```

Đường đi từ field tới type annotation:

```text
Field numbers
  └── getAnnotatedType(): AnnotatedParameterizedType [List<...>]
       └── getAnnotatedActualTypeArguments()[0]
            └── AnnotatedWildcardType [? extends Number]
                 ├── getAnnotation(Mark.class)       -> "wildcard"
                 ├── getAnnotatedUpperBounds()
                 │     └── AnnotatedType [Number]
                 │           └── getAnnotation(Mark.class) -> "bound"
                 └── getAnnotatedLowerBounds()       -> empty
```

Dưới đây là các bước Reflection đúng cấu trúc:

```java
Field field = Sample.class.getDeclaredField("numbers");

// Không phải (AnnotatedWildcardType) field.getAnnotatedType():
// field là List<...>, lớp ngoài cùng là parameterized type.
AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType argument = listType.getAnnotatedActualTypeArguments()[0];
AnnotatedWildcardType wildcard = (AnnotatedWildcardType) argument;

Mark wildcardMark = wildcard.getAnnotation(Mark.class);
AnnotatedType bound = wildcard.getAnnotatedUpperBounds()[0];
Mark boundMark = bound.getAnnotation(Mark.class);
```

Đoạn trên chỉ minh họa và cần khai báo `Sample.numbers`, định nghĩa `Mark`, các import `java.lang.reflect.*` và xử lý checked exceptions. Mã hoàn chỉnh chạy được nằm ở mục 5.

**Vì sao phải qua `AnnotatedParameterizedType` trước?** Bởi vì kiểu ngoài cùng là `List<...>`. Một đối số kiểu của `List` mới là wildcard `?`. Ép trực tiếp `field.getAnnotatedType()` thành `AnnotatedWildcardType` sẽ gây `ClassCastException`.

Các điểm xuất phát khác, tùy wildcard xuất hiện ở đâu:

- **Field:** `Field.getAnnotatedType()`.
- **Tham số method/constructor:** `Parameter.getAnnotatedType()` hoặc `Executable.getAnnotatedParameterTypes()`.
- **Kiểu trả về method:** `Method.getAnnotatedReturnType()`.
- **Superclass/interface generic có annotation:** `Class.getAnnotatedSuperclass()` và `Class.getAnnotatedInterfaces()`.
- **Ngoại lệ ở throws clause:** `Executable.getAnnotatedExceptionTypes()` khi cần.

Ở mỗi nhánh, tiếp tục dựa vào kiểu interface **thực** của `AnnotatedType`: `AnnotatedParameterizedType`, `AnnotatedWildcardType`, `AnnotatedArrayType` hoặc `AnnotatedTypeVariable`. Không giả định cấu trúc mọi khai báo giống nhau.

## 5. Ví dụ Java 17+ hoàn chỉnh: wildcard, extends, super và generic lồng nhau

Lưu tệp **`AnnotatedWildcardDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

public class AnnotatedWildcardDemo {
    List<@Mark("question") ? extends @Mark("upper") Number> producers;

    List<@Mark("question") ? super @Mark("lower") Integer> consumers;

    List<@Mark("any") ?> unknown;

    List<? extends @Mark("onlyUpper") Number> onlyBound;

    Map<String, List<@Mark("nestedW") ?
            extends @Mark("nestedUpper") Number>> nested;

    static String mark(AnnotatedType type) {
        Mark annotation = type.getAnnotation(Mark.class);
        return annotation == null ? "-" : annotation.value();
    }

    static void show(String fieldName) throws NoSuchFieldException {
        Field field = AnnotatedWildcardDemo.class
                .getDeclaredField(fieldName);

        AnnotatedParameterizedType list =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedWildcardType wildcard = (AnnotatedWildcardType)
                list.getAnnotatedActualTypeArguments()[0];

        System.out.println(fieldName + " wildcard=" + mark(wildcard));

        for (AnnotatedType upper : wildcard.getAnnotatedUpperBounds()) {
            System.out.println("  upper=" + upper.getType().getTypeName()
                    + " mark=" + mark(upper));
        }

        for (AnnotatedType lower : wildcard.getAnnotatedLowerBounds()) {
            System.out.println("  lower=" + lower.getType().getTypeName()
                    + " mark=" + mark(lower));
        }

        System.out.println("  lower count="
                + wildcard.getAnnotatedLowerBounds().length);
    }

    public static void main(String[] args) throws Exception {
        show("producers");
        show("consumers");
        show("unknown");
        show("onlyBound");

        Field field = AnnotatedWildcardDemo.class
                .getDeclaredField("nested");

        AnnotatedParameterizedType mapType =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType)
                mapType.getAnnotatedActualTypeArguments()[1];

        AnnotatedWildcardType nestedWildcard =
                (AnnotatedWildcardType)
                listType.getAnnotatedActualTypeArguments()[0];

        System.out.println("nested wildcard=" + mark(nestedWildcard));
        AnnotatedType nestedUpper =
                nestedWildcard.getAnnotatedUpperBounds()[0];

        System.out.println("nested upper="
                + nestedUpper.getType().getTypeName()
                + " mark=" + mark(nestedUpper));
    }
}
```

Biên dịch và chạy:

```bash
javac AnnotatedWildcardDemo.java
java AnnotatedWildcardDemo
```

**Stdout mong đợi:**

```text
producers wildcard=question
  upper=java.lang.Number mark=upper
  lower count=0
consumers wildcard=question
  upper=java.lang.Object mark=-
  lower=java.lang.Integer mark=lower
  lower count=1
unknown wildcard=any
  upper=java.lang.Object mark=-
  lower count=0
onlyBound wildcard=-
  upper=java.lang.Number mark=onlyUpper
  lower count=0
nested wildcard=nestedW
nested upper=java.lang.Number mark=nestedUpper
```

### Giải thích kết quả

1. Với `producers`, annotation `question` nằm trên wildcard; `upper` nằm trên `Number`. `getAnnotatedUpperBounds()` có `Number`, không có lower bound tường minh.
2. Với `consumers`, lower bound `Integer` mang `lower`. Upper bound mặc định là `Object` không annotate, mặc dù khai báo dùng `super`.
3. Với `unknown`, wildcard vẫn có upper bound mặc định `Object`; `getAnnotatedLowerBounds()` trả mảng rỗng.
4. Với `onlyBound`, wildcard không có annotation riêng, nên helper `mark(wildcard)` in `-`. Nhưng bound `Number` có annotation `onlyUpper`, chứng tỏ vị trí annotation phải được đọc độc lập.
5. Với `nested`, kiểu ngoài cùng là `Map`. Đối số thứ hai là `List<...>`, và đối số đầu của `List` mới là wildcard. Cần **hai lần** qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` để tìm đến wildcard và bound cần đọc.

Các field được khai báo để phục vụ phân tích kiểu; chúng không cần được khởi tạo thành `List` hay `Map` thực. Reflection ở đây đọc metadata của *declaration*, không đọc phần tử của một collection runtime.

### Nếu chỉ có `WildcardType` thì sao?

Một đoạn như:

```java
Field f = AnnotatedWildcardDemo.class
        .getDeclaredField("producers");

java.lang.reflect.ParameterizedType p =
        (java.lang.reflect.ParameterizedType) f.getGenericType();

java.lang.reflect.WildcardType w =
        (java.lang.reflect.WildcardType)
        p.getActualTypeArguments()[0];

System.out.println(w.getUpperBounds()[0].getTypeName());
```

sẽ cho `java.lang.Number` nhưng **không giữ annotation `@Mark("upper")` ngay trên `Type` này**. Để đọc annotation ở upper bound, đi theo `Field.getAnnotatedType()` như ví dụ chạy được ở trên.

Đoạn mã này chỉ minh họa Reflection generic thuần, giả định tên class và field đã được định nghĩa theo ví dụ trước; cần chạy trong method có xử lý `NoSuchFieldException`.

## 6. Quy tắc upper/lower bound ngầm định

### `?` không có giới hạn tường minh

```java
List<?> values;
```

Đối với wildcard này:

- `getAnnotatedUpperBounds()` trả upper bound `Object` **không mang annotation**, do Java không viết upper bound tường minh.
- `getAnnotatedLowerBounds()` trả mảng độ dài `0`.

Đừng hiểu mảng lower rỗng là “không tồn tại quan hệ kiểu”; nó chỉ nói **không có lower bound được khai báo tường minh**. Tương tự, sự xuất hiện của `Object` **không chứng minh mã nguồn đã viết `extends Object`**.

### `? extends Number`

```java
List<? extends @Mark("limit") Number> values;
```

- Upper bound là `Number`, với annotation `limit`.
- Lower bounds rỗng.
- Wildcard bản thân có thể không có annotation nào.

### `? super Integer`

```java
List<? super @Mark("floor") Integer> values;
```

- Lower bound là `Integer`, với annotation `floor`.
- Upper bound phản ánh mặc định là `Object` (không annotate).
- `getAnnotatedUpperBounds().length` không nên bị hiểu là `0` chỉ vì khai báo sử dụng `super`.

### Tránh khẳng định mọi array đều chỉ có một phần tử

Theo tài liệu Java, hiện tại wildcard source có tối đa một upper bound hoặc một lower bound tường minh, nhưng API vẫn sử dụng `AnnotatedType[]` và lưu ý caller nên sẵn sàng tiếp nhận nhiều bound ở tương lai. Duyệt với vòng `for` sẽ rõ ràng và bền hơn so với ép luôn `[0]`. Chỉ dùng `[0]` khi bạn vừa kiểm tra độ dài hoặc chủ động làm ví dụ cho cú pháp Java cụ thể.

## 7. Annotation trên wildcard không phải annotation trên field

Xét một trường hợp có hai `@Target`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ColumnInfo {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeInfo {
    String value();
}

class Record {
    @ColumnInfo("scores")
    List<@TypeInfo("wild") ? extends
            @TypeInfo("bound") Number> scores;
}
```

Đây là **mảnh mã minh họa**; để biên dịch độc lập cần các import từ `java.lang.annotation` và `java.util.List`.

Các vị trí đọc khác nhau:

| Vị trí annotation | API chính |
| --- | --- |
| `@ColumnInfo` trên declaration của field `scores` | `Field.getAnnotation(ColumnInfo.class)` |
| `@TypeInfo("wild")` trên dấu `?` | `AnnotatedWildcardType.getAnnotation(TypeInfo.class)` |
| `@TypeInfo("bound")` trên `Number` | `getAnnotatedUpperBounds()[0].getAnnotation(TypeInfo.class)` |

Không dùng `field.getAnnotations()` rồi kỳ vọng nó trả annotation type-use ở wildcard hoặc bound. Những annotation đó thuộc **các vị trí con trong cây kiểu đã annotate**, không phải cùng node với declaration của field.

Tương tự, `AnnotatedParameterizedType.getAnnotations()` trên node `List<...>` không tự “thu gom” mọi annotation nằm sâu ở `?` hay bound. Muốn lấy toàn bộ, phải duyệt cây kiểu.

## 8. Bound là kiểu parameterized, array hoặc type variable

`AnnotatedType` của bound không nhất thiết chỉ đại diện cho `Class<?>` đơn giản.

### Bound chứa generic lồng nhau

```java
List<? extends @Mark("boundList")
        List<@Mark("element") String>> nestedBound;
```

Đây là khai báo field minh họa có ý nghĩa type-use. Trong Reflection, upper bound của wildcard là một `AnnotatedParameterizedType` đại diện `List<String>`:

1. `AnnotatedWildcardType.getAnnotatedUpperBounds()[0]` lấy node bound.
2. `bound.getAnnotation(Mark.class)` có thể cho `boundList`.
3. Ép bound thành `AnnotatedParameterizedType` rồi gọi `getAnnotatedActualTypeArguments()[0]` để lấy node `String`.
4. `getAnnotation(Mark.class)` trên node `String` cho `element`.

Chỉ hỏi `bound.getAnnotations()` mà bỏ qua các actual type arguments sẽ bỏ sót annotation sâu hơn.

### Bound là kiểu mảng

```java
List<? extends @Mark("element") Number[]> arrayBound;
```

Đọc kiểu array cần xem đúng vị trí annotation trên component và dimension; `AnnotatedArrayType.getAnnotatedGenericComponentType()` giúp đi vào kiểu phần tử hoặc dimension bên trong theo cấu trúc Reflection. Ví dụ annotation trên `Number` và annotation trên dấu ngoặc mảng `Number @Mark("dimension") []` là **hai vị trí type-use khác nhau**. Không nên kết luận vị trí chỉ bằng `toString()` của `Type`.

### Bound là type variable

```java
class Catalog<T extends Number> {
    List<? extends T> values;
}
```

Upper bound của wildcard này là kiểu biến `T`. Nếu cần xem *ràng buộc khai báo của T* (ví dụ `T extends Number`), tiếp tục khảo sát `AnnotatedTypeVariable.getAnnotatedBounds()` khi có thông tin liên quan.

Phân biệt:

- **Bound của wildcard:** `? extends T` — dùng `AnnotatedWildcardType.getAnnotatedUpperBounds()`.
- **Bound khai báo của type variable:** `T extends Number` — dùng `TypeVariable.getAnnotatedBounds()` hoặc `AnnotatedTypeVariable.getAnnotatedBounds()` từ góc nhìn annotated type variable.

Hai cấp bound không phải cùng một node. Với loại recursive bounds (ví dụ `T extends Comparable<T>`), khi viết thuật toán duyệt đệ quy tổng quát phải tránh vòng lặp vô hạn bằng cách theo dõi node/type đã thăm.

## 9. Ví dụ đọc wildcard tại method parameter và return type

Các API không bị giới hạn ở field. Ví dụ:

```java
class Service {
    java.util.List<@Mark("returnWild") ?
            extends @Mark("returnBound") Number> find() {
        return java.util.List.of();
    }

    void accept(java.util.List<@Mark("paramWild") ?
            super @Mark("paramBound") Integer> values) {
    }
}
```

Đây là đoạn minh họa bổ sung, dùng annotation `Mark` ở mục 5.

Với method `find`:

```java
Method method = Service.class.getDeclaredMethod("find");
AnnotatedParameterizedType returned =
        (AnnotatedParameterizedType) method.getAnnotatedReturnType();
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
        returned.getAnnotatedActualTypeArguments()[0];
AnnotatedType bound = wildcard.getAnnotatedUpperBounds()[0];
```

Với method `accept`:

```java
Method method = Service.class
        .getDeclaredMethod("accept", java.util.List.class);
AnnotatedParameterizedType parameterized =
        (AnnotatedParameterizedType)
        method.getParameters()[0].getAnnotatedType();
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
        parameterized.getAnnotatedActualTypeArguments()[0];
AnnotatedType bound = wildcard.getAnnotatedLowerBounds()[0];
```

Cần `import java.lang.reflect.*;` và xử lý `NoSuchMethodException`. Ví dụ đầy đủ runnable ở mục 5 đã trình bày các bước tương tự trên field.

Điều này minh họa rằng `getAnnotatedReturnType()` và `Parameter.getAnnotatedType()` là **cổng vào cấu trúc annotated type**, còn `getAnnotatedUpperBounds()/getAnnotatedLowerBounds()` chỉ xuất hiện sau khi tìm được node wildcard.

## 10. Giới hạn metadata: không phải annotation nào cũng đọc được bằng Reflection

Muốn type-use annotation có thể đọc ở runtime, khai báo thông thường cần:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}
```

Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`: annotation có thể được compiler lưu trong class file nhưng **không được API core Reflection trả về như annotation runtime**. Với `RetentionPolicy.SOURCE`, annotation thường bị loại bỏ trước khi tạo class file. Nếu một thư viện sửa hoặc làm mờ bytecode, thông tin có thể bị thay đổi.

Không được hiểu việc `getAnnotation(Mark.class) == null` là chắc chắn trong source không từng có annotation: có thể do retention, metadata bị bỏ, vị trí tra cứu sai, loại `@Target` không phù hợp, hoặc annotation class không khả dụng.

### Type erasure và việc đọc generic annotations

`List<? extends Number>` và `List<? super Integer>` khi chạy đều là đối tượng thuộc kiểu thô `List` ở JVM. Reflection đọc cấu trúc generic từ metadata khai báo như `Signature` và các type annotation attributes liên quan. Các annotation này mô tả **kiểu được khai báo**, không phải annotation runtime của từng phần tử thực tế bên trong một danh sách.

Ví dụ, `List<@Mark ? extends Number>` không có nghĩa mọi `Number` trong list là một đối tượng được gắn `@Mark`; annotation ở đây là thông tin trong **type use của đối số generic**.

Một `java.lang.reflect.Type` thuần có thể nêu đúng generic bound nhưng không thể giữ vị trí annotation; dùng `AnnotatedType` khi câu hỏi là annotation trên kiểu và bound.

### Khi class file metadata không đủ

Các tình huống có thể gặp:

- Generic `Signature` bị loại bỏ hoặc hỏng, khiến việc phân tích type argument không còn đáng tin.
- Type-use annotation có `CLASS` hoặc `SOURCE` retention, nên API runtime không thấy.
- Obfuscation hoặc bytecode transformation làm thay đổi metadata.
- Kiểu tham chiếu trong generic signature không còn tồn tại, có thể phát sinh `TypeNotPresentException` hay ngoại lệ phản ánh phù hợp.
- Parser cố ép kiểu node sai, ví dụ ép một `AnnotatedArrayType` thành `AnnotatedWildcardType`.

Trường hợp metadata không tồn tại thì hãy coi dữ liệu là **không xác định** thay vì tự suy ra annotation đã/không đã viết trong source. Cần thông tin trước runtime thì dùng công cụ biên dịch/source AST hoặc class-file reader với mục đích phù hợp.

## 11. Kiểm tra class file bằng `javap`

Sau khi biên dịch chương trình `AnnotatedWildcardDemo.java` ở mục 5:

```bash
javap -v -p AnnotatedWildcardDemo
```

Tìm các phần liên quan:

- `Signature` lưu biểu diễn generic, chẳng hạn wildcard upper/lower type arguments.
- `RuntimeVisibleTypeAnnotations` lưu type-use annotations có runtime retention và thông tin **type path/target** để chỉ ra vị trí annotation: wildcard, bound, node generic sâu hơn.
- Một số annotation không có runtime retention có thể được lưu trong `RuntimeInvisibleTypeAnnotations` tùy retention; core Reflection không hiển thị chúng theo cách giống runtime-visible annotations.

`javap` hữu ích để đối chiếu vị trí với dữ liệu class file, nhưng không thay thế API `AnnotatedWildcardType` khi bạn viết logic Reflection ở runtime.

Nếu `getAnnotation(...)` không thấy annotation, hãy xác định thật rõ **đang hỏi node nào** trước khi kết luận annotation thiếu: field declaration, `List`, wildcard `?`, upper bound hay lower bound.

## 12. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Cast `field.getAnnotatedType()` trực tiếp thành `AnnotatedWildcardType` | Field là `List<...>`, không phải wildcard | Đi qua `AnnotatedParameterizedType` và lấy type argument |
| Dùng `Field.getGenericType()` để đọc annotation bound | `Type` thuần không mang annotation type-use theo node | Dùng `getAnnotatedType()` |
| Gọi `wildcard.getAnnotation(Mark.class)` để tìm annotation trên `Number` | Annotation ở bound, không ở dấu `?` | Hỏi `getAnnotatedUpperBounds()[0].getAnnotation(...)` |
| Với `? super Integer`, giả định upper bounds rỗng | Upper bound ngầm định là `Object` | Kiểm tra upper và lower độc lập |
| Với `?`, giả định không có bound nào | Upper bound ngầm định vẫn là `Object` | Đọc `getAnnotatedUpperBounds()` |
| Mọi wildcard đều là đối số số 0 | Map/nested generics có thể có nhiều type arguments | Duyệt đúng cây annotated types |
| Chỉ duyệt bound một cấp | Bound có thể là `List<@Mark String>` hay array/type variable | Duyệt `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedTypeVariable` khi cần |
| Mong `getAnnotations()` của `Field` chứa annotation trên `?` | Declaration annotation khác type-use annotation | Dùng annotated type APIs |
| Thiếu `@Retention(RUNTIME)` nhưng đòi Reflection thấy marker | Retention mặc định `CLASS` | Dùng `RUNTIME` khi cần đọc runtime |
| Coi annotation generic là annotation của object runtime | Thông tin thuộc type use khai báo | Tách metadata khai báo khỏi giá trị runtime |
| Phụ thuộc `getAnnotatedUpperBounds()[0]` cho mọi hoàn cảnh | API trả mảng; kiểu thực tế có thể khác | Kiểm tra độ dài và duyệt vòng `for` |
| Coi mọi `AnnotatedType` là `AnnotatedWildcardType` | Hệ phân loại Reflection có nhiều nhánh | Dùng `instanceof` / kiểm tra class trước khi cast |

## 13. Bài tập tự kiểm tra

**Câu 1.** Trong `List<@Mark("A") ? extends @Mark("B") Number>`, nơi nào đọc được `A` và `B`?

**Đáp án:** `A` ở `AnnotatedWildcardType.getAnnotation(Mark.class)`; `B` ở `getAnnotatedUpperBounds()[0].getAnnotation(Mark.class)`.

**Câu 2.** `List<? super @Mark("LOW") Integer>` có upper bound nào ở runtime?

**Đáp án:** Có upper bound `Object` không annotate, và lower bound `Integer` mang `LOW`.

**Câu 3.** Tại sao `Field.getAnnotation(Mark.class)` không phải API phù hợp để đọc `@Mark` đặt ngay trên dấu `?`?

**Đáp án:** Vì đó là annotation **type-use** trên wildcard node trong generic signature; nó không trực tiếp annotate declaration của `Field`.

**Câu 4.** `getAnnotatedLowerBounds().length == 0` cho biết điều gì?

**Đáp án:** Không có lower bound **tường minh** trong cách phản ánh wildcard đó. Đừng suy ra wildcard không có upper bound.

**Câu 5.** Nếu field là `Map<String, List<? extends Number>>`, có thể cast ngay kết quả `field.getAnnotatedType()` thành `AnnotatedWildcardType` không?

**Đáp án:** Không. Đầu tiên là `AnnotatedParameterizedType` của `Map`; type argument thứ hai là `List` cũng là `AnnotatedParameterizedType`; wildcard nằm ở type argument của `List`.

**Câu 6.** Với `@Retention(CLASS)`, core Reflection có bảo đảm trả annotation ở bound không?

**Đáp án:** Không. Class file có thể giữ metadata nhưng annotation không có runtime retention để Reflection hiển thị như runtime annotation.

**Câu 7.** Phải chọn `getAnnotatedUpperBounds()` hay `getAnnotatedLowerBounds()` cho `? extends @Mark Number` và `? super @Mark Integer`?

**Đáp án:** `extends` → upper; `super` → lower.

## 14. Ghi nhớ

**`AnnotatedWildcardType` mô tả wildcard `?` có thể được annotate, và mỗi bound là một `AnnotatedType` có thể được annotate độc lập.** Để đọc đầy đủ metadata, đi theo đường từ field/method/parameter tới `AnnotatedParameterizedType`, lấy node `AnnotatedWildcardType`, hỏi annotation trên wildcard, rồi duyệt upper/lower bounds. Wildcard không có bound tường minh vẫn có upper bound `Object`; `? super T` cũng có upper bound `Object` và lower bound `T`.

Khi gặp generic lồng nhau, hãy duyệt cây `AnnotatedType` chứ không cố bóc mọi annotation bằng `Type` thuần hay ép kiểu mù quáng. Metadata chỉ đáng tin ở mức runtime nếu retention và class file thực sự giữ các thông tin cần thiết.

**Tài liệu tham khảo chuẩn:**

- [Java SE 17 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [Java SE 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java Language Specification `4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html)
