# Annotation tại ép kiểu, tạo đối tượng và các vị trí kiểu khác trong Java

## 1. Annotation có thể mô tả một lần *sử dụng kiểu*

Trong Java, annotation không chỉ gắn vào khai báo class, method hay field. Một annotation có `@Target(ElementType.TYPE_USE)` còn được đặt **tại những chỗ mã nguồn sử dụng kiểu**: ở khai báo biến, kiểu tham số, generic argument, type cast, biểu thức `new`, phép thử `instanceof`, kiểu phần tử mảng, `extends`, `implements`, `throws` và những vị trí khác được Java Language Specification (JLS) quy định.

Ví dụ:

```java
@TypeTag("cast")
String result = (@TypeTag("checked") String) source;
```

Ở đây `@TypeTag("checked")` gắn vào **kiểu `String` dùng trong phép ép kiểu**, còn annotation đứng trước kiểu ở khai báo biến có thể mô tả **kiểu của biến**. Chúng không phải hai lần gọi annotation như gọi một function: annotation là metadata, không có hiệu ứng tự động chuyển đổi giá trị hay kiểm tra tính hợp lệ của phép cast.

Để tự khai báo annotation cho các ngữ cảnh sử dụng kiểu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}
```

- **`TYPE_USE`** cho phép annotation nằm trên một vị trí sử dụng kiểu.
- **`RUNTIME`** giữ thông tin annotation phù hợp trong class file để những API runtime có hỗ trợ truy cập metadata có thể đọc được. Không phải **mọi** vị trí trong thân method đều được Java Reflection cung cấp API trực tiếp để truy vấn.
- `value()` là phần tử `String`, nên ta có thể viết dạng ngắn `@TypeTag("cast")`.
- Không có `@Target(TYPE_USE)` thì annotation chỉ dành cho khai báo (theo `@Target` cụ thể hoặc mặc định), **không tự được phép dùng trong cast hay `new`**.

Annotation tại vị trí dùng kiểu là nền tảng để các static analysis/type checker mở rộng hệ thống kiểu, chẳng hạn mô tả nullable/non-null, tainted data hoặc dữ liệu đã được xác thực. **Chỉ định nghĩa `@TypeTag` không làm compiler Java mặc định tự hiểu ý nghĩa “đã kiểm tra” hoặc “không null”.** Muốn có quy tắc kiểm tra bổ sung, cần công cụ xử lý annotation hiểu đúng ngữ nghĩa annotation type.

## 2. Phân biệt declaration annotation và type-use annotation

Hai vị trí trông giống nhau nhưng biểu thị khác nhau:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldInfo {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNullType {}

class Example {
    @FieldInfo
    @NonNullType String text;
}
```

- `@FieldInfo` thuộc **field declaration**: metadata trên field `text`.
- `@NonNullType` thuộc **kiểu `String`** của field.
- `Field.getAnnotation(FieldInfo.class)` truy vấn annotation trên declaration.
- `Field.getAnnotatedType().getAnnotation(NonNullType.class)` truy vấn annotation trên kiểu được dùng.

Một annotation type có thể khai báo cả `FIELD` và `TYPE_USE`; nếu đặt ở vị trí chung trước kiểu của field, cùng cú pháp có thể áp dụng ở **cả hai ngữ cảnh**. Do đó, hãy đọc `@Target` và chọn đúng API reflection trước khi kết luận annotation “bị mất”.

Tương tự, `TYPE_PARAMETER` dùng để đánh dấu **khai báo tham số kiểu** như `class Box<@Marker T>`, còn `TYPE_USE` mô tả **các kiểu được sử dụng** như `Box<@Marker String>`. Hai mục tiêu có thể cùng xuất hiện trong `@Target({TYPE_PARAMETER, TYPE_USE})` nếu annotation được thiết kế cho cả hai.

## 3. Annotation tại phép ép kiểu (cast)

Java cho phép đặt type-use annotation bên trong cặp ngoặc của **cast expression**, ngay trước kiểu:

```java
Object input = "hello";
String text = (@TypeTag("cast") String) input;
```

Thứ tự thực thi vẫn là Java thông thường:

1. JVM thực hiện cast từ `Object` sang `String` theo quy tắc runtime của Java.
2. Nếu giá trị có kiểu không phù hợp, cast ném `ClassCastException` giống như không có annotation.
3. Nếu giá trị phù hợp (hoặc là `null` với reference cast), cast thành công.
4. `@TypeTag("cast")` là metadata gắn với **kiểu được viết trong cast**. Bản thân nó không thay logic kiểm tra kiểu.

Ví dụ, code sau **vẫn thất bại lúc chạy**:

```java
Object number = 42;
String invalid = (@TypeTag("cast") String) number; // ClassCastException
```

Type-use annotation có thể diễn đạt ý định của developer hoặc contract của checker, nhưng không “cứu” một phép cast vốn sai.

### Cast kiểu generic

Annotation có thể xuất hiện trên type argument:

```java
Object unknown = java.util.List.of("a", "b");

@SuppressWarnings("unchecked")
java.util.List<@TypeTag("element") String> strings =
        (java.util.List<@TypeTag("cast-element") String>) unknown;
```

Phép cast sang `List<String>` là **unchecked** vì runtime chỉ kiểm tra được `List`, không kiểm tra được từng phần tử có phải `String` hay không. `@TypeTag` không thay type erasure. Việc cần `@SuppressWarnings("unchecked")` (nếu có) là vấn đề cảnh báo cast riêng, không được `TYPE_USE` tự giải quyết.

## 4. Annotation tại biểu thức tạo đối tượng bằng `new`

Trong **unqualified class instance creation expression**, ta có thể đánh dấu kiểu class ngay sau `new`:

```java
String value = new @TypeTag("created-type") String("hello");
```

Ở đây `@TypeTag` mô tả **kiểu của class đang được tạo**. Constructor vẫn chạy bình thường; `TYPE_USE` không tác động vào constructor invocation, thời điểm cấp phát bộ nhớ hay khả năng ném exception của constructor.

Ví dụ với generic class:

```java
java.util.List<@TypeTag("element") String> names =
        new @TypeTag("list-type")
            java.util.ArrayList<@TypeTag("new-element") String>();
```

Tuy nhiên, với **tên kiểu có package qualifier** (như `java.util.ArrayList`), vị trí đặt annotation phải tuân thủ chính xác quy tắc cú pháp của tên kiểu; cách đặt annotation ở phần trước `java` trong ví dụ minh họa trên không phải cú pháp Java hợp lệ. Dạng chắc chắn hợp lệ và dễ đọc là import class rồi viết:

```java
import java.util.ArrayList;
import java.util.List;

List<@TypeTag("element") String> names =
        new @TypeTag("list-type")
            ArrayList<@TypeTag("new-element") String>();
```

*Hai khối trên nhằm so sánh vị trí đặt; khối sử dụng tên đầy đủ là ví dụ cú pháp cố ý không dùng để biên dịch. Dùng khối sau trong ứng dụng hoặc ví dụ chạy được.*

Điều quan trọng: `@TypeTag` đặt trước `ArrayList` áp dụng cho **kiểu được khởi tạo trong biểu thức**, còn annotation đặt bên trong dấu `<...>` áp dụng cho **generic type argument**.

### Anonymous class

Với một anonymous class, kiểu được dùng sau `new` vẫn là vị trí sử dụng kiểu. Ví dụ:

```java
Runnable task = new @TypeTag("anonymous-base") Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
```

Annotation ở đây mô tả kiểu interface `Runnable` tại vị trí tạo anonymous class, **không tự trở thành annotation trên phương thức `run()`**, và không tự tạo ra hành vi runtime bổ sung.

## 5. Annotation tại `instanceof` và pattern matching

Một phép thử kiểu có thể mang type-use annotation:

```java
Object input = "Java";
boolean stringValue = input instanceof @TypeTag("tested-type") String;
```

`instanceof` vẫn trả về kết quả theo quy tắc Java: giá trị không null và có kiểu phù hợp thì `true`. Annotation ở kiểu được thử không ảnh hưởng kết quả.

Java 17 cũng hỗ trợ type pattern trong `instanceof`:

```java
Object input = "Java";
if (input instanceof @TypeTag("pattern-type") String text) {
    System.out.println(text.toUpperCase());
}
```

Ví dụ này kiểm tra giá trị và khai báo pattern variable `text`; annotation nhắm vào **kiểu `String` của pattern**, không khiến `text` được tạo ra theo cơ chế khác.

Đừng nhầm `@Target(TYPE_USE)` với `@Target(LOCAL_VARIABLE)`. Một annotation trên declaration của biến và một annotation trên kiểu được viết trong pattern/biểu thức có thể chịu các quy tắc khác nhau. Muốn biết vị trí thực sự được annotation, phải nhìn cả cú pháp lẫn `@Target`.

## 6. Generic: type argument, wildcard bound, type parameter bound

Trong Java Generics, ta có thể đánh dấu **kiểu cụ thể** ở bên trong dấu `<...>`:

```java
List<@TypeTag("element") String> names = List.of("A", "B");
```

Annotation ở đây gắn lên type argument `String`, **không** gắn lên declaration `List` và **không** tự annotate mọi đối tượng `String` đang nằm trong list.

Wildcard bound cũng là một ngữ cảnh sử dụng kiểu:

```java
List<? extends @TypeTag("upper-bound") Number> values = List.of(1, 2);
List<? super @TypeTag("lower-bound") Integer> sink =
        new ArrayList<Number>();
```

- `@TypeTag("upper-bound") Number` là phần **upper bound** của wildcard.
- `@TypeTag("lower-bound") Integer` là phần **lower bound** của wildcard.
- `List<@TypeTag("wildcard") ?>` minh họa annotation đặt lên chính wildcard nếu checker của bạn có contract cho trường hợp đó.
- Generic assignment, variance, capture và erasure vẫn tuân theo quy tắc Java; annotation type-use không tự đổi quan hệ `extends`/`super`.

Bound của tham số kiểu cũng có thể mang annotation:

```java
class NumericBox<T extends @TypeTag("bound") Number> {
    private final T value;
    NumericBox(T value) { this.value = value; }
    T get() { return value; }
}
```

Trong ví dụ này, `@TypeTag` gắn lên **`Number` được dùng làm bound**. Khai báo `T` là type parameter, nên nếu muốn annotate **chính declaration `T`** thì cần xem xét `ElementType.TYPE_PARAMETER`; không nhầm nó với annotation trên bound.

Một số biểu thức có **explicit type arguments** cũng cho phép type annotation:

```java
// Giả định List, Collections và TypeTag được import:
List<String> empty = java.util.Collections.<@TypeTag("call-arg") String>emptyList();
```

Annotation nhắm vào kiểu `String` trong **type argument list của lời gọi method**. Nó không biến method `emptyList` thành annotated method declaration.

## 7. Mảng: kiểu phần tử khác annotation trên từng chiều

Java cho phép annotate **kiểu phần tử** và **từng tầng của kiểu mảng**. Ví dụ:

```java
@TypeTag("element") String @TypeTag("outer-array") [] values;
```

- `@TypeTag("element")` trước `String` áp dụng cho **kiểu phần tử String**.
- `@TypeTag("outer-array")` trước `[]` áp dụng cho **kiểu mảng String[]**.
- Với mảng nhiều chiều, từng cặp `[]` có thể nhận annotation riêng.

```java
String @TypeTag("two-dimensional") []
       @TypeTag("inner-array") [] grid;
```

Vị trí annotation rất quan trọng. Annotate kiểu phần tử `String` không giống annotate `String[]`. Khi phản ánh qua `AnnotatedType`, API `AnnotatedArrayType` cho phép đi sâu từng tầng bằng `getAnnotatedGenericComponentType()`.

### Mảng trong biểu thức `new`

Kiểu phần tử và chiều mảng có thể được annotate tại array creation expression:

```java
int @TypeTag("array-dimension") [] numbers =
        new int @TypeTag("new-dimension") [2];
```

Ví dụ này vẫn tạo mảng `int[]` độ dài 2. Annotation **không thay đổi kích thước mảng, kiểm tra biên hay giá trị mặc định** của các phần tử.

Không được đặt annotation tùy ý ở bất kỳ vị trí nào của `[]` hoặc giữa các token tùy ý; phải đặt theo grammar của Java type annotation (đặc biệt là bên trái dấu `[` ở chiều cần đánh dấu).

## 8. Những vị trí TYPE_USE khác: extends, implements, throws, receiver, method reference

### 8.1. Superclass và superinterface

```java
class Base {}

class Worker extends @TypeTag("base") Base
        implements @TypeTag("interface") Runnable {
    @Override
    public void run() {}
}
```

Annotation gắn lên **kiểu superclass `Base`** và **kiểu interface `Runnable`** trong quan hệ kế thừa. Chúng không tự annotate chính declaration của class `Worker`, cũng không tự gắn vào các phương thức được kế thừa.

Reflection trên class có thể truy vấn một số type-use annotation tại đây bằng:

```java
Worker.class.getAnnotatedSuperclass();
Worker.class.getAnnotatedInterfaces();
```

### 8.2. Return type, parameter type, receiver type và throws

```java
import java.io.IOException;

class Service {
    public @TypeTag("return") String read(
            @TypeTag("parameter") String key)
            throws @TypeTag("exception") IOException {
        return key;
    }

    void inspect(@TypeTag("receiver") Service this) {
        // Receiver type annotation, không phải một đối số truyền khi gọi method.
    }
}
```

- Annotation trên `String` trước tên method là **return type**.
- Annotation trên `String key` là **parameter type**; chỉ `TYPE_USE` có thể không tạo declaration annotation trên `java.lang.reflect.Parameter`.
- Annotation trên `IOException` mô tả kiểu exception trong `throws`.
- `Service this` là **receiver parameter**: một vị trí cú pháp đặc biệt cho type annotation, không thêm tham số truyền khi gọi `inspect()`.

Các API reflection tương ứng gồm `Method.getAnnotatedReturnType()`, `Executable.getAnnotatedParameterTypes()`, `Executable.getAnnotatedExceptionTypes()` và `Executable.getAnnotatedReceiverType()`, tùy declaration có receiver tương ứng.

### 8.3. Kiểu trong method reference

Trong biểu thức method reference, reference type cũng có thể được annotate:

```java
java.util.function.Function<String, Integer> length =
        @TypeTag("reference-type") String::length;
```

Đây là một type-use annotation trên kiểu tham chiếu `String`. Kết quả method reference vẫn là lambda/function object theo semantics của Java. Annotation không tự động gắn vào method `String.length()`.

Một method reference với explicit type arguments (khi cú pháp API phù hợp) cũng có thể annotate các type arguments đó.

## 9. Ví dụ Java 17+ chạy được: nhiều vị trí trong một chương trình

Tạo file **Main.java** đúng như sau. Chương trình cho thấy annotation tại expression và declaration type context đều hợp lệ; những metadata có API reflection được đọc để đối chiếu rõ ràng.

```java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.ArrayList;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Tag {
    String value();
}

class Base {}

class Sample extends @Tag("super") Base
        implements @Tag("interface") Runnable {

    public @Tag("return") String message(
            @Tag("parameter") String text)
            throws @Tag("throws") IOException {

        Object value = text;
        String casted = (@Tag("cast") String) value;
        String created = new @Tag("new") String(casted);

        List<@Tag("argument") String> names =
                new @Tag("generic-new")
                    ArrayList<@Tag("constructor-argument") String>();
        names.add(created);

        List<? extends @Tag("bound") Number> numbers = List.of(1, 2);
        int @Tag("array") [] values =
                new int @Tag("new-dimension") [2];

        if (casted instanceof @Tag("instanceof") String) {
            values[0] = numbers.size();
        }
        return names.get(0) + values[0];
    }

    @Override
    public void run() {}

    public void receiver(@Tag("receiver") Sample this) {}
}

public class Main {
    public static void main(String[] args) throws Exception {
        Sample sample = new Sample();

        System.out.println(sample.message("ok"));

        System.out.println(Sample.class.getAnnotatedSuperclass()
                .getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getAnnotatedInterfaces()[0]
                .getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getMethod("message", String.class)
                .getAnnotatedReturnType().getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getMethod("message", String.class)
                .getAnnotatedParameterTypes()[0]
                .getAnnotation(Tag.class).value());
        System.out.println(Sample.class.getMethod("message", String.class)
                .getAnnotatedExceptionTypes()[0]
                .getAnnotation(Tag.class).value());
    }
}
```

Biên dịch và chạy trong thư mục chứa `Main.java`:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Kết quả:

```text
ok2
super
interface
return
parameter
throws
```

Giải thích kết quả:

1. `message("ok")` ép `"ok"` từ `Object` sang `String`, tạo một `String` mới, thêm vào `List`, đặt `values[0] = 2` vì danh sách `numbers` có hai phần tử, rồi nối chuỗi ra `"ok2"`.
2. `getAnnotatedSuperclass()` và `getAnnotatedInterfaces()` đọc type-use annotation của những kiểu được ghi ở `extends`/`implements`.
3. `getAnnotatedReturnType()`, `getAnnotatedParameterTypes()` và `getAnnotatedExceptionTypes()` đọc type-use annotation ở chữ ký method.
4. Annotation `cast`, `new`, `generic-new`, `instanceof` nằm trong **thân method**. Chúng không được liệt kê trong output reflection trên chữ ký method. Điều đó **không có nghĩa compiler bỏ qua annotation khi sinh class file**; có thể dùng công cụ đọc class file để quan sát metadata tại những vị trí biểu thức.

Chương trình chỉ biểu diễn và đọc metadata; nó không có checker riêng triển khai logic cho các nhãn `cast`, `new`, `bound`, `throws`.

## 10. Đọc type-use annotation: Reflection và class file

Java reflection có các đối tượng **`AnnotatedType`** mô tả kiểu trong nhiều vị trí khai báo:

| Vị trí | Reflection API thường dùng |
|---|---|
| Kiểu của field | `Field.getAnnotatedType()` |
| Kiểu trả về method | `Method.getAnnotatedReturnType()` |
| Kiểu tham số | `Executable.getAnnotatedParameterTypes()` |
| Kiểu exception trong `throws` | `Executable.getAnnotatedExceptionTypes()` |
| Kiểu receiver | `Executable.getAnnotatedReceiverType()` |
| Superclass / interface | `Class.getAnnotatedSuperclass()`, `Class.getAnnotatedInterfaces()` |
| Generic argument | Chuyển thành `AnnotatedParameterizedType`, rồi `getAnnotatedActualTypeArguments()` |
| Chiều mảng | `AnnotatedArrayType.getAnnotatedGenericComponentType()` |

Nhưng `AnnotatedType` **không phải một hệ thống duyệt mọi expression trong body**. Java reflection chuẩn không có method trực tiếp kiểu `getAnnotationsOnAllCasts()` hay `getAnnotationsOnAllNewExpressions()`.

Đối với annotation retained ở class file tại cast/new/instanceof, công cụ phân tích bytecode có thể đọc các thuộc tính `RuntimeVisibleTypeAnnotations` hoặc `RuntimeInvisibleTypeAnnotations` tương ứng. Ví dụ sau dùng `javap` sau khi biên dịch:

```bash
javap -v Sample
```

Tra các phần `RuntimeVisibleTypeAnnotations` để xem type annotation được ghi trong class file, bao gồm các mục tiêu liên quan đến expression, nếu compiler và retention tạo ra thuộc tính đó. `javap` hiển thị thông tin chi tiết không giống hệt API reflection; kết quả chỉ dùng để minh họa cấu trúc class file, không cần bịa ra một output `javap` cố định.

**Retention không đồng nghĩa với runtime enforcement.** Dù annotation `RUNTIME` và bytecode chứa metadata, Java vẫn không tự thực thi ràng buộc người viết annotation dự tính.

## 11. Các lỗi phổ biến và cách sửa

### 11.1. Dùng `@Target` sai

Ví dụ sai:

```java
@Target(ElementType.METHOD)
@interface MethodInfo {}

Object source = "text";
String result = (@MethodInfo String) source; // SAI: cast là TYPE_USE
```

Muốn đánh dấu kiểu trong cast, annotation type phải có `TYPE_USE`. `METHOD` chỉ cho phép sử dụng trên khai báo method, không tạo quyền annotate kiểu được dùng trong biểu thức.

### 11.2. Viết annotation sai phía của tên kiểu

Type annotation gắn với **simple name của kiểu**. Khi dùng qualified type như `java.util.List`, không nên chèn annotation tùy ý giữa các token package. Ưu tiên import rồi viết `new @Tag ArrayList<String>()`, hoặc đặt đúng trước simple type name trong qualified type khi đáp ứng quy tắc JLS.

### 11.3. Tưởng annotation tự chặn `null`

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}

@NonNull String value = null;
```

Nếu không có checker hay công cụ bổ sung, đoạn khai báo trên **không tự bị `javac` bác bỏ chỉ vì `@NonNull`**. Annotation tên `NonNull` chưa chứa bất kỳ quy tắc kiểm tra nào; tên annotation chỉ là metadata.

### 11.4. Tưởng `@Tag` thay đổi cast hoặc constructor

`(@Tag String) object` vẫn cast theo quy tắc JVM. `new @Tag Service()` vẫn gọi constructor như thông thường. Annotation không tạo thêm constructor, không bọc object và không thêm runtime check mặc định.

### 11.5. Đọc nhầm declaration thay vì annotated type

Nếu `@Tag` chỉ có `TYPE_USE`, `field.getAnnotation(Tag.class)` có thể không thấy annotation trên **kiểu field**. Phải dùng `field.getAnnotatedType().getAnnotation(Tag.class)`. Với generic nhiều tầng, phải duyệt `AnnotatedParameterizedType` hoặc `AnnotatedArrayType` tại đúng cấp.

### 11.6. Cứ nhìn Reflection rồi kết luận compiler làm mất annotation cast

`Method.getAnnotations()` đọc metadata của **method declaration**, không trả về type-use annotations nằm trên những cast và biểu thức `new` trong thân method. Muốn kiểm tra các vị trí đó ở class file, dùng `javap -v` hoặc công cụ đọc bytecode phù hợp.

### 11.7. Đặt annotation tại vị trí không được grammar chấp nhận

`TYPE_USE` mở rộng những nơi được phép dùng annotation nhưng **không cho chèn @Annotation vào bất kỳ khoảng trắng nào**. Vị trí trong cast, `new`, `instanceof`, generic, `[]`, wildcard bound hoặc method reference đều có grammar cụ thể. Nếu gặp lỗi parser, đối chiếu JLS §4.11 và §9.7.4 trước khi đổ lỗi cho `@Target`.

## 12. Checklist khi làm việc với TYPE_USE

1. **Đọc `@Target`**: annotation type có `TYPE_USE` hay không? Nếu muốn annotate declaration type parameter, xét thêm `TYPE_PARAMETER`.
2. **Chỉ rõ vị trí**: đang annotate class declaration, field declaration, kiểu field, kiểu cast, kiểu sau `new`, generic argument, array dimension hay return type?
3. **Chọn đúng cú pháp**: ví dụ `(@Tag String) value`, `new @Tag String("x")`, `List<@Tag String>`, `String @Tag []`.
4. **Phân biệt metadata và logic**: chương trình có annotation processor/type checker nào giải thích `@Tag` không? Nếu không, JVM xử lý biểu thức như bình thường.
5. **Xác định công cụ đọc metadata**: `AnnotatedType` dùng cho nhiều vị trí signature/declaration; `javap -v` hay bytecode scanner phù hợp cho annotation trong method body.
6. **Kiểm tra retention**: `SOURCE`, `CLASS`, `RUNTIME` phục vụ các mục đích khác nhau; reflection chỉ thấy những dữ liệu có thể truy cập qua API và còn retention phù hợp.
7. **Thử compile ở JDK mục tiêu**: type annotation syntax yêu cầu Java 8+, còn những cú pháp khác như `instanceof` pattern cần phiên bản Java phù hợp (ví dụ Java 17).

## 13. Tài liệu chuẩn để tra cứu

- [Java SE 17 JLS §4.11 — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11): danh sách type contexts, bao gồm cast, new, array creation, instanceof và method reference.
- [Java SE 17 JLS §9.6.4.1 — @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): ý nghĩa `ElementType.TYPE_USE`, `TYPE_PARAMETER` và declaration target.
- [Java SE 17 JLS §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): ngữ cảnh annotation trên kiểu và cách phân biệt declaration/type.
- [Java SE 17 API — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): truy cập annotated type qua reflection.
- [Java SE 17 JVM Specification §4.7.20–4.7.21](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.20): định dạng `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` trong class file.

**Ghi nhớ:** `@Target(TYPE_USE)` cho phép annotation mô tả **một kiểu tại nơi nó được sử dụng**: cast, `new`, `instanceof`, generics, mảng, method reference, `throws` và nhiều type context khác. Type-use annotation không tự đổi runtime semantics. Muốn quan sát annotation, phải biết nó nằm trên declaration/signature hay expression và chọn Reflection hoặc phân tích class file cho phù hợp.