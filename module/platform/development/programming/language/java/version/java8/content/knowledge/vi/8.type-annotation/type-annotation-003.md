# Type annotation trong generic argument, array và cast (Java 8 → Java hiện đại)

## 1. Mục tiêu và tư duy cốt lõi

Kể từ Java 8, Java hỗ trợ **type-use annotations**: đặt annotation lên **một lần sử dụng kiểu dữ liệu** thay vì chỉ gắn annotation vào khai báo class, method hoặc field. Ba vị trí rất dễ nhầm nhưng có giá trị thực tế là:

1. **Generic type argument:** `List<@Label String>`, `Map<String, List<@Label Integer>>` hoặc bound trong wildcard.
2. **Array và từng chiều mảng:** `String @Label []`; với mảng nhiều chiều, annotation trước từng cặp `[]` có thể mô tả một **tầng kiểu mảng khác nhau**.
3. **Cast expression:** `(@Label String) value`, annotation áp dụng cho kiểu đích của phép ép kiểu.

Các quy tắc này vẫn nằm trong Java Language Specification hiện hành, không phải cú pháp legacy. Nhưng điểm quan trọng nhất là: **Java compiler/JVM mặc định không suy ra chính sách nullness, bảo mật hoặc validation từ một type annotation tùy ý**. Annotation là metadata để công cụ kiểm tra tĩnh, annotation processor, thư viện/framework hoặc code reflection có thể diễn giải theo **hợp đồng riêng**.

Sau bài học, bạn sẽ biết khai báo `@Target(ElementType.TYPE_USE)`, đặt annotation đúng cấp độ kiểu, so sánh `TYPE_USE` và `TYPE_PARAMETER`, dùng reflection đọc metadata còn giữ ở runtime, hiểu hạn chế của type erasure/cast và viết test cho các vị trí này.

Các ví dụ chỉ dùng tính năng **còn áp dụng trên JDK hiện đại được nhà cung cấp duy trì**. Mã ví dụ là cú pháp Java 8 gốc và tương thích mức ngôn ngữ đó; có thể biên dịch trên JDK mới với `javac --release 8` nếu compiler hỗ trợ. Không yêu cầu chạy JDK 8 cũ.

## 2. Khai báo annotation hợp lệ cho vị trí kiểu

Annotation dùng ở vị trí type use phải có target phù hợp:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}
~~~

- `@Target(ElementType.TYPE_USE)` cho phép annotation trên những **lần dùng kiểu**, bao gồm generic argument, array component/dimension và cast type.
- `@Retention(RetentionPolicy.RUNTIME)` giữ annotation để các API reflection hỗ trợ có thể đọc metadata ở runtime **tại vị trí được reflection biểu diễn**. Không có nghĩa mọi vị trí như cast/local expression đều được core reflection duyệt trực tiếp.
- Nếu chỉ cần công cụ build phân tích bytecode mà không cần Java reflection, `RetentionPolicy.CLASS` có thể đủ; nếu chỉ cần công cụ xử lý source, `SOURCE` có thể phù hợp.
- `String value();` là thành phần của annotation: `@Label("name")` là dạng viết gọn tương ứng `@Label(value = "name")`.
- Một annotation với `@Target(ElementType.METHOD)` chỉ cho khai báo method sẽ **không** hợp lệ khi dùng như `List<@Marker String>`.

**`TYPE_USE` khác `TYPE_PARAMETER` như thế nào?** `TYPE_PARAMETER` hướng đến chỗ **khai báo type parameter**, ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@interface TypeVariableNote {
}

class Holder<@TypeVariableNote T> {
}
~~~

Còn `List<@Label String>` không khai báo một biến kiểu `T` nào cả: nó dùng `String` làm **type argument** trong một parameterized type. Để viết annotation tại đây, `TYPE_USE` là mục tiêu đúng. `TYPE_USE` có phạm vi rộng và có thể áp dụng ở vị trí khai báo type parameter theo quy tắc Java; nhưng `TYPE_PARAMETER` riêng **không đủ** cho mọi vị trí sử dụng kiểu.

### Declaration annotation và type annotation không đồng nhất

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface ColumnInfo {
}

@Target(ElementType.TYPE_USE)
@interface TypeNote {
}

// Trong một class:
@ColumnInfo
@TypeNote
String value;
~~~

`@ColumnInfo` gắn vào **declaration của field**; `@TypeNote` mô tả **type use `String`** trong khai báo field. Vì vị trí cú pháp có thể chồng lên nhau, phải nhìn **`@Target`** để hiểu annotation đang áp dụng vào đâu. `Field.getDeclaredAnnotations()` và `Field.getAnnotatedType()` không phải hai API tương đương.

Không nên đặt tên annotation như `@NonNull` rồi kỳ vọng javac tự cấm null. Muốn kiểm soát nullness tại compile-time, cần chọn một công cụ/library có hợp đồng annotation và cấu hình phân tích cụ thể; muốn kiểm runtime, dùng validation/các precondition rõ ràng.

## 3. Type annotation trong generic type argument

### 3.1. Chỗ đặt annotation quan trọng

~~~java
import java.util.List;
import java.util.Map;

// Với @Label đã khai báo:
List<@Label("element") String> names;

Map<@Label("key") String,
    @Label("value-list") List<@Label("item") Integer>> catalog;
~~~

Giải thích theo cấu trúc:

- `@Label("element")` áp dụng cho lần sử dụng `String` làm type argument của `List`.
- `@Label("key")` áp dụng cho `String` làm key type của `Map`.
- `@Label("value-list")` áp dụng cho toàn bộ kiểu `List<Integer>` ở vị trí value type của `Map`, còn `@Label("item")` áp dụng riêng lên `Integer` ở **type argument bên trong**.
- Thứ tự và vị trí annotation có ý nghĩa: nhãn trên `List<Integer>` khác nhãn trên `Integer`.

Có thể hình dung cây kiểu:

~~~text
Map
├── String                        @Label("key")
└── List<Integer>                 @Label("value-list")
    └── Integer                   @Label("item")
~~~

Type annotation mô tả **vị trí trong cây kiểu**, không phải chú thích trực tiếp vào từng object phần tử đang nằm trong collection. Một `List<@Label String>` không làm JVM đi qua list và kiểm tra nội dung string ở runtime.

### 3.2. Wildcard bound và generic method

Một annotation TYPE_USE cũng có thể áp dụng trên kiểu bound:

~~~java
import java.util.List;

List<? extends @Label("bound") Number> measurements;
~~~

Ở đây annotation gắn lên `Number` là **upper bound của wildcard**. Nó không biến wildcard thành một concrete type mới, không đổi quy tắc variance, và không nới giới hạn generic type checking.

Ví dụ với generic method:

~~~java
import java.util.List;

static <T> List<@Label("result-item") T> echo(List<T> input) {
    return input;
}
~~~

Đây là **một method declaration minh họa**, không phải file Java độc lập. Annotation ở `List<@Label T>` gắn lên **type use của T** trong giá trị trả về, không gắn lên chỗ khai báo `<T>`. Để gắn trực tiếp khai báo type parameter, viết `<@TypeVariableNote T>` với annotation có target thích hợp.

### 3.3. Erasure: type annotation không đổi phép kiểm runtime mặc định

~~~java
List<@Label("a") String> a;
List<@Label("b") String> b;
~~~

Hai type argument ở trên đều là `String` trong hệ generic thông thường. Label khác nhau **không biến chúng thành hai kiểu Java khác nhau** dưới compiler chuẩn; các annotation này dành cho tooling. Java generic **type erasure** vẫn áp dụng; bạn không nhận được runtime kiểm tra từng phần tử chỉ vì viết `@Label`.

Không thể dùng `instanceof List<@Label String>` như một phép kiểm sâu cho generic argument; kiểu generic parameterized non-reifiable như `List<String>` không thể được kiểm theo cách đó. Nếu cần đảm bảo phần tử thỏa một ràng buộc nghiệp vụ, sử dụng validation hoặc công cụ type-checking được cấu hình.

## 4. Annotation trên mảng: phân biệt phần tử và từng chiều

Mảng là nơi cú pháp `TYPE_USE` dễ gây nhầm nhất. Theo JLS `9.7.4` và `10.1`, annotation có thể đứng **trước kiểu phần tử** hoặc **trước cặp ngoặc vuông** của một chiều mảng:

~~~java
@Label("element") String[] words;
String @Label("array") [] words2;
~~~

Hai khai báo **không mang cùng vị trí metadata**:

- `@Label("element") String[]`: annotation ở `String`, tức **kiểu phần tử**.
- `String @Label("array") []`: annotation ở **kiểu mảng** mà cặp `[]` đó biểu thị.

### 4.1. Mảng hai chiều và đường đi từ ngoài vào trong

~~~java
@Label("leaf") String @Label("outer") [] @Label("inner") [] matrix;
~~~

Cấu trúc:

~~~text
String[][]                            @Label("outer")  (mảng ngoài)
└── String[]                         @Label("inner")  (mảng thành phần)
    └── String                       @Label("leaf")   (kiểu phần tử)
~~~

Hãy nhớ quy tắc: với hai cặp `[]`, annotation nằm trước **cặp thứ nhất** ở mức outermost array; annotation nằm trước **cặp thứ hai** ở mức component array. Annotation viết trước `String` mô tả element type. Dấu cách giữa kiểu và `[]` cũng giúp biểu đạt vị trí rõ ràng.

Tại sao phải quan tâm? Một công cụ kiểm tra nullness hoặc ownership có thể muốn phân biệt **mảng ngoài có thể null**, **mảng con có thể null**, và **phần tử có thể null**. Các ý nghĩa cụ thể này **do công cụ quyết định**, không có sẵn chỉ từ tên annotation.

### 4.2. Generic argument chứa array type

~~~java
import java.util.List;

List<String @Label("array-argument") []> rows;
List<@Label("element") String[]> items;
~~~

Vế đầu đánh dấu **array type `String[]`** dùng làm generic argument, vế sau đánh dấu **String element type** của array trong type argument. Khi đọc code, đừng gom chúng thành cùng một annotation “trên List”; chúng ở hai vị trí khác nhau trong cây kiểu.

### 4.3. Dùng array annotation không phân bổ dữ liệu

~~~java
String @Label("array") [] values; // Mới khai báo biến, chưa tạo mảng.
values = new String[] {"A", "B"};
~~~

Annotation không tự cấp phát mảng, không đặt giá trị mặc định mới và không làm thay đổi thời gian sống hay khả năng mutate. Ngôn ngữ Java vẫn áp dụng các quy tắc bình thường về `null`, chỉ số, covariance và `ArrayStoreException`.

## 5. Annotation trên kiểu đích của cast

Type annotation có thể nằm **bên trong dấu ngoặc của cast**:

~~~java
Object raw = "Java";
String name = (@Label("cast-target") String) raw;
System.out.println(name);  // Java
~~~

`@Label("cast-target")` mô tả **type use `String` của biểu thức cast**. Về phép ép kiểu Java thông thường:

- Cast vẫn được compiler/JVM kiểm theo **quan hệ kiểu Java**, không theo chuỗi `"cast-target"`.
- Nếu `raw` chứa một `Integer`, cast sang `String` vẫn ném `ClassCastException`.
- Nếu `raw == null`, cast sang reference type `String` cho kết quả `null`; annotation có tên gợi nullness **không tự biến cast thành null check**.
- Type annotation tại cast có thể được ghi ở metadata classfile khi retention phù hợp, để tool phân tích bytecode sử dụng. Tuy nhiên core reflection `java.lang.reflect` **không có API liệt kê mọi cast expression trong method body** như `Field.getAnnotatedType()` cho khai báo field.

Đây là khác biệt lớn giữa type annotation **ở chỗ khai báo dễ phản chiếu** (field, method return/parameter...) và **ở vị trí biểu thức** (cast).

### Lưu ý “annotated cast” không phải “validated cast”

~~~java
Object source = Integer.valueOf(42);

// Java vẫn ném ClassCastException khi thực thi câu lệnh:
// String text = (@Label("must-be-string") String) source;
~~~

Một checker có thể dùng annotation để báo lỗi hoặc cảnh báo trước khi chạy nếu được tích hợp đúng. Nếu không có checker, `@Label` chỉ là metadata, không can thiệp vào hoạt động của cast.

## 6. Chương trình hoàn chỉnh: generic argument, array và cast + reflection

Tạo file **`TypeUseLocationsDemo.java`** dưới encoding UTF-8. Ví dụ không dùng thư viện ngoài và có output xác định; sử dụng một annotation `Tag` có `RUNTIME` retention để đọc metadata trên field. Phép cast vẫn được thực thi theo luật Java thông thường.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.util.List;
import java.util.Locale;

public class TypeUseLocationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface Tag {
        String value();
    }

    static final class Sample {
        List<@Tag("argument") String> labels;

        @Tag("leaf") String @Tag("outer") [] @Tag("inner") [] grid;
    }

    static String tagOf(AnnotatedType type) {
        Tag tag = type.getAnnotation(Tag.class);
        return tag == null ? "-" : tag.value();
    }

    public static void main(String[] args) throws Exception {
        Field labels = Sample.class.getDeclaredField("labels");
        AnnotatedParameterizedType listType =
            (AnnotatedParameterizedType) labels.getAnnotatedType();

        AnnotatedType argument =
            listType.getAnnotatedActualTypeArguments()[0];
        System.out.println("generic: " + tagOf(argument));

        Field grid = Sample.class.getDeclaredField("grid");
        AnnotatedArrayType outer =
            (AnnotatedArrayType) grid.getAnnotatedType();
        AnnotatedArrayType inner =
            (AnnotatedArrayType) outer.getAnnotatedGenericComponentType();
        AnnotatedType leaf = inner.getAnnotatedGenericComponentType();

        System.out.println("array: "
            + tagOf(outer) + "/" + tagOf(inner) + "/" + tagOf(leaf));

        Object source = "Java";
        String castValue = (@Tag("cast") String) source;
        System.out.println("cast: " + castValue.toUpperCase(Locale.ROOT));

        try {
            Object wrong = Integer.valueOf(42);
            String invalid = (@Tag("cast") String) wrong;
            System.out.println(invalid);
        } catch (ClassCastException expected) {
            System.out.println("cast error: ClassCastException");
        }
    }
}
~~~

Biên dịch bằng JDK hiện đại hỗ trợ `--release 8`:

~~~text
javac --release 8 -encoding UTF-8 TypeUseLocationsDemo.java
java TypeUseLocationsDemo
~~~

Nếu dự án chỉ hỗ trợ một mức JDK mới cụ thể, dùng `--release <phiên_bản_được_hỗ_trợ>` hoặc cấu hình build chính thức của dự án; không ép mọi dự án mới giữ bytecode Java 8.

**Stdout chính xác, bốn dòng:**

~~~text
generic: argument
array: outer/inner/leaf
cast: JAVA
cast error: ClassCastException
~~~

**Phân tích kết quả:**

1. Field `labels` có type `List<@Tag("argument") String>`. `Field.getAnnotatedType()` trả một `AnnotatedParameterizedType`; `getAnnotatedActualTypeArguments()[0]` trỏ tới annotated use của `String` và đọc được `Tag("argument")`.
2. Field `grid` có mảng hai chiều. `AnnotatedArrayType` ngoài chứa annotation `outer`; đi một bước `getAnnotatedGenericComponentType()` nhận mảng bên trong có `inner`; bước tiếp theo nhận `String` có `leaf`.
3. Cast `(@Tag("cast") String) source` thành công vì object thực tế là `String`. `toUpperCase(Locale.ROOT)` tạo kết quả `"JAVA"` ổn định, không phụ thuộc locale người chạy.
4. `wrong` là `Integer` nên phép cast sang `String` ném `ClassCastException`. Annotation `@Tag("cast")` không tạo exemption hay runtime validation đặc biệt.

**Tại sao chương trình có thể đọc annotation trên field?** Vì `@Retention(RUNTIME)` và reflection cung cấp các interface `AnnotatedType`, `AnnotatedParameterizedType`, `AnnotatedArrayType`. Điều này **không** có nghĩa có thể dùng các method đó để tra annotation của mọi cast expression đã chạy.

## 7. Đọc metadata chính xác bằng reflection

### 7.1. Đừng dùng nhầm API bỏ mất cấu trúc type

~~~java
// Khi đã có Field labels như ví dụ hoàn chỉnh:
java.lang.reflect.Type generic = labels.getGenericType();
java.lang.reflect.AnnotatedType annotated = labels.getAnnotatedType();
~~~

- `getGenericType()` trả mô tả kiểu `Type`, hữu ích để phân tích parameterized type, nhưng **không phải API trả trực tiếp annotation của từng type use**.
- `getAnnotatedType()` trả `AnnotatedType`, điểm bắt đầu để đọc annotation và đi sâu xuống các thành phần của kiểu.
- Với kiểu `List<String>`, cast phù hợp sang `AnnotatedParameterizedType` và dùng `getAnnotatedActualTypeArguments()`.
- Với mảng, đi xuống từng tầng `AnnotatedArrayType.getAnnotatedGenericComponentType()`; annotation của dimension ngoài **không tự thay thế** annotation của element type.

Với code introspection tổng quát, không cast tất cả `AnnotatedType` thành `AnnotatedParameterizedType`; trước tiên kiểm `instanceof` và xử lý `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable` khi phù hợp.

### 7.2. Wildcard và type variable cần nhánh riêng

Nếu gặp `List<? extends @Tag Number>`, đường đi reflection đi qua `AnnotatedWildcardType`, sau đó tới các annotated upper bounds. Nếu annotation nằm trên declaration của generic type parameter, `TypeVariable.getAnnotations()`/`getAnnotatedBounds()` có vai trò khác so với đọc actual type argument tại một field hoặc return type.

Không tự viết parser bằng cách split chuỗi từ `Type.getTypeName()`: chuỗi hiển thị không thay thế được cây metadata và các vị trí `type_path` trong bytecode.

### 7.3. Retention và khả năng truy xuất

| Retention | Còn ở đâu? | Đọc bằng core reflection khi type use được hỗ trợ? |
| --- | --- | --- |
| `SOURCE` | Trong quá trình xử lý source | Không |
| `CLASS` | Metadata trong classfile | Không, thông thường không được reflection expose |
| `RUNTIME` | Metadata runtime tương ứng | Có với các vị trí có API reflection thích hợp như annotated field/return/parameter types |

Các chú thích trên biểu thức như **cast** có thể được mã hóa trong cấu trúc annotation của classfile, nhưng **không có nghĩa** một call `Class.getAnnotations()` hoặc `Field.getAnnotations()` sẽ liệt kê chúng. Để phân tích expression-level metadata, chọn công cụ compiler/bytecode phù hợp (annotation processing, AST tools, class-file API hoặc bytecode libraries đang được duy trì) với kiểm thử trên JDK mục tiêu.

## 8. Annotation và việc thực thi quy tắc nghiệp vụ

Một type-use annotation được đặt tên `@NonNull`, `@ReadOnly` hoặc `@Sensitive` có thể có **ý nghĩa do công cụ định nghĩa**, nhưng Java SE không mặc nhiên gắn các tên này với cơ chế chặn null hoặc phân quyền. Phải phân biệt ba mức:

1. **Cú pháp hợp lệ:** compiler chấp nhận vị trí annotation vì `@Target(TYPE_USE)` và các rule ngôn ngữ.
2. **Metadata tồn tại:** retention quyết định annotation còn lại trong source/classfile/runtime ở mức tương ứng.
3. **Quy tắc được thực thi:** chỉ xảy ra nếu bạn đã cấu hình checker/framework hoặc viết code validation sử dụng annotation theo hợp đồng.

Ví dụ, với một annotation riêng `@Label("non-null")`, câu lệnh bên dưới vẫn có thể được compiler Java thông thường chấp nhận:

~~~java
@Label("non-null") String name = null;
~~~

Điều này **không** chứng minh annotation “không hữu ích”; nó có thể là một phần của static-analysis system. Nhưng không được bảo đảm an toàn null chỉ nhờ tên annotation.

Nếu bạn cần check runtime bằng API hiện có:

~~~java
String safeName = java.util.Objects.requireNonNull(name, "name");
~~~

`Objects.requireNonNull` thực sự ném `NullPointerException` khi `name` null. Nó độc lập với một type-use annotation tùy ý và dễ được kiểm thử. Với thư viện checker bên ngoài, phải theo đúng version, scope, build plugin và rule set đang được bảo trì; không trình bày tên annotation không có chuẩn chung như thể chúng là một phần built-in của Java.

## 9. Những lỗi phổ biến trong generic, array và cast

### Lỗi 1 — Dùng sai `@Target`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface MethodOnly {
}

// Không biên dịch:
// java.util.List<@MethodOnly String> wrong;
~~~

`MethodOnly` được giới hạn cho method declaration, không được gắn lên generic argument. Thêm `ElementType.TYPE_USE` nếu annotation thật sự được thiết kế để dùng ở vị trí kiểu và điều đó phù hợp với hợp đồng.

### Lỗi 2 — Hiểu nhầm `@Label String[]` với `String @Label []`

~~~java
@Label("element") String[] a;
String @Label("array") [] b;
~~~

Cả hai có thể compile, nhưng annotation nhắm vào **hai vị trí type use khác nhau**. Nếu một thư viện/checker kỳ vọng annotation ở cấp độ array reference, viết trước `String` thay vì trước `[]` có thể khiến checker diễn giải khác. Test vị trí bằng reflection như mục 6, không chỉ kiểm có annotation nào đó tồn tại.

### Lỗi 3 — Dùng `getDeclaredAnnotations()` của Field để đọc nested type-use

~~~java
// Đối với field List<@Tag String>:
java.lang.annotation.Annotation[] declared =
    Sample.class.getDeclaredField("labels").getDeclaredAnnotations();
~~~

Method này trả **declaration annotations trên field**, không phải tất cả annotation nested trên `String` bên trong `List`. Dùng `getAnnotatedType()` rồi duyệt `AnnotatedParameterizedType`.

### Lỗi 4 — Cho rằng cast annotation ngăn ClassCastException

~~~java
Object value = Integer.valueOf(10);
// String s = (@Label("string") String) value; // Runtime ClassCastException.
~~~

Annotation không chuyển object sang kiểu `String` và cũng không làm mất quy tắc cast của JVM. Nếu cần chuyển dữ liệu, dùng API chuyển đổi hoặc validate kiểu đúng cách.

### Lỗi 5 — Cho rằng type-use annotation sửa type erasure

Hai biểu thức `List<@Label("one") String>` và `List<@Label("two") String>` không tạo hai class runtime khác nhau. Metadata annotation và kiểu generic là hai khía cạnh tách biệt. Runtime kiểm kiểu phần tử trong collection phải được thiết kế rõ nếu thực sự cần.

### Lỗi 6 — Mong nhìn thấy cast/local annotation qua Field reflection

Chỉ những loại khai báo và đường đi được reflection API biểu diễn mới có thể được đọc trực tiếp theo cách đó. Cast thuộc expression trong method body: cần công cụ phân tích compiler/bytecode, không phải `Field.getAnnotatedType()`.

### Lỗi 7 — Đọc sai từng cấp array

Với `String @A [] @B []`, `@A` gắn ở mảng ngoài, `@B` gắn ở mảng thành phần. Nếu code reflection chỉ gọi `getAnnotation(A.class)` ở leaf component type, kết quả có thể null dù annotation đã được lưu đúng ở outer dimension.

### Lỗi 8 — Đồng nhất annotation type-use với validation “đã bật”

Một project có thể chứa hàng trăm `@NonNull` mà static checker chưa được chạy ở CI. Lúc đó các annotation chỉ mang metadata/tài liệu, không hình thành bằng chứng an toàn. Định nghĩa và kiểm thử cả *tooling*, không chỉ kiểm cú pháp.

## 10. Kiểm thử annotation ở từng vị trí trong CI

Một bộ test tối thiểu cho thư viện tự định nghĩa type-use annotations nên gồm:

| Kiểm tra | Bằng chứng |
| --- | --- |
| Biên dịch type argument | `List<@Tag String>`, nested generic argument và wildcard bound đều compile |
| Biên dịch array levels | `@Tag String @Tag [] @Tag [][]` được phân tích đúng từng cấp |
| Biên dịch cast | `(@Tag String) raw` compile và giữ luật `ClassCastException` |
| Negative compile test | Annotation thiếu `TYPE_USE` bị compiler từ chối tại type-use |
| Runtime reflection test | `getAnnotatedActualTypeArguments()` và `getAnnotatedGenericComponentType()` trả đúng tag |
| Retention test | `RUNTIME` đọc được; `SOURCE`/`CLASS` không được dùng sai qua core reflection |
| Tooling test | Checker được bật thật sự, nhận đúng đường đi kiểu và làm build fail khi vi phạm |
| Runtime behavior test | Null/cast/array vẫn theo luật Java khi annotation không có checker bổ sung |

**Thực hành tốt:** Với compiler thử nghiệm hoặc các version checker khác nhau, test **cả thành công lẫn thất bại mong đợi**. Đừng phụ thuộc chính xác câu chữ thông báo lỗi (có thể đổi theo locale/JDK), chỉ cần xác minh exit code và diagnostics trọng tâm.

Nếu ứng dụng dùng code generation, serialization hoặc bytecode transformation, bổ sung integration test để xác nhận những công cụ đó **có giữ hoặc diễn giải annotation trên generic arguments và array dimensions** đúng cách hay không. Đừng ngầm giả định mọi thư viện serialize `AnnotatedType` như nhau.

### Checklist review code

- [ ] Annotation được khai báo với đúng `@Target`, retention và ý nghĩa semantically documented.
- [ ] Type argument ở đúng vị trí, kể cả nested generic/wildcard khi liên quan.
- [ ] Annotation trước `String` hay trước `[]` là lựa chọn **có chủ đích**, không phải lệch chỗ do style formatter.
- [ ] Cast annotation không bị hiểu thành runtime validation.
- [ ] Code reflection dùng `AnnotatedType` đúng loại và không bỏ sót array levels.
- [ ] Hành vi ngăn null/kiểm bảo mật có test và công cụ thực thi rõ, không chỉ là tên annotation.
- [ ] Runtime/toolchain được bảo trì; phiên bản Java target được kiểm bằng build và test thực.
- [ ] Negative tests được tách rõ khỏi chương trình runnable để không làm hỏng build chính.

## 11. Bài tập thực hành và đáp án định hướng

**Bài 1 — Generic argument:** Định nghĩa `@Tag` như mục 6, khai báo `List<@Tag("name") String> names;`. Dùng reflection lấy annotated actual type argument và in `name`. Giải thích tại sao `Field.getDeclaredAnnotations()` không trả đúng nested annotation đó.

**Bài 2 — Nested generic:** Khai báo `Map<String, List<@Tag("count") Integer>> data;`. Vẽ cây kiểu và chỉ đường đi reflection đến `Integer`. Đáp án: đi qua outer `AnnotatedParameterizedType` của `Map`, lấy argument 1 là `List<Integer>`, rồi `getAnnotatedActualTypeArguments()[0]` ở nested parameterized type để lấy `Tag("count")`.

**Bài 3 — Array một chiều:** So sánh `@Tag("element") String[]` và `String @Tag("array") []`. Dùng `AnnotatedArrayType` kiểm annotation ở root và component. Đáp án: label `array` ở root array; `element` ở component `String`.

**Bài 4 — Array hai chiều:** Tạo `@Tag("leaf") String @Tag("first") [] @Tag("second") [] matrix;`. Truy xuất từ outer xuống leaf; dự kiến `first/second/leaf`. Nêu vì sao đây không phải ba field annotations khác nhau.

**Bài 5 — Cast:** Với `Object source = "ok"`, thực hiện `(@Tag("cast") String) source`; sau đó đổi source thành `Integer.valueOf(1)`. Dự đoán trường hợp sau vẫn ném `ClassCastException`.

**Bài 6 — Target sai:** Định nghĩa annotation chỉ có `@Target(METHOD)` và đặt vào `List<@YourAnnotation String>`. Dự đoán compiler từ chối; sửa bằng `TYPE_USE` khi phù hợp.

**Bài 7 — Retention:** Đổi `@Tag` từ `RUNTIME` sang `CLASS` và chạy lại reflection test. Thấy metadata không còn được trả qua `AnnotatedType.getAnnotation(Tag.class)`; giải thích tại sao classfile vẫn có thể chứa metadata cho tool khác.

**Bài 8 — Contract nullness:** Tạo `@Tag("nonnull") String value = null;` và quan sát compiler chuẩn không báo lỗi chỉ vì nhãn đó. Thêm `Objects.requireNonNull` hoặc một checker đã cấu hình; mô tả bằng chứng mới có giá trị.

**Bài 9 — Reflection tool:** Viết helper `String show(AnnotatedType type)` đọc `@Tag` khi có, rồi viết visitor xử lý `AnnotatedArrayType` và `AnnotatedParameterizedType`. Dùng dữ liệu chương trình mục 6 và kiểm chuỗi output ổn định.

**Bài 10 — Review thư viện:** Bạn định public một annotation dùng trên generic arguments trong một API. Lập ma trận target/retention/tooling/backward compatibility và xác định ai chịu trách nhiệm enforce semantics, source hay runtime.

**Tiêu chí đạt:** Bạn tự viết đúng syntax cho ba vị trí; phân biệt annotation element type với array dimension, type argument với type parameter declaration; giải thích được annotation không tự thực thi validation; đọc metadata đúng bằng reflection và chạy `TypeUseLocationsDemo.java` với bốn dòng stdout.

## 12. Tài liệu chính thức, còn áp dụng trên JDK hiện đại

- **JLS Java SE 27, `9.7.4 — Where Annotations May Appear:** https://docs.oracle.com/javase/specs/jls/se27/html/jls-9.html#jls-9.7.4
- **JLS Java SE 27, `4.11 — Where Types Are Used:** https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.11
- **JLS Java SE 27, `10.1 — Array Types:** https://docs.oracle.com/javase/specs/jls/se27/html/jls-10.html#jls-10.1
- **JLS Java SE 27, `15.16 — Cast Expressions:** https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.16
- **Java SE 27, java.lang.reflect AnnotatedType/AnnotatedArrayType/AnnotatedParameterizedType:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/package-summary.html
- **Java SE specifications index:** https://docs.oracle.com/javase/specs/

Tài liệu Java SE 27 được dùng để đối chiếu luật ngôn ngữ và APIs hiện hành; ví dụ cú pháp `TYPE_USE` và `AnnotatedType` đã được hỗ trợ từ Java 8. Dù code được kiểm ở mức tương thích Java 8, khi xây ứng dụng mới hãy dùng bản JDK và công cụ phân tích **còn nhận cập nhật bảo mật** theo yêu cầu dự án.

**Ghi nhớ:** `List<@Tag String>`, `String @Tag []` và `(@Tag String) source` đều gắn annotation vào **lần dùng kiểu**, nhưng ở ba cấu trúc rất khác nhau. Đặt annotation đúng vị trí, cấu hình công cụ diễn giải nó, và kiểm tra runtime/compile-time bằng test thay vì giả định annotation tự thay đổi hành vi Java.