# Dùng `var` trong tham số lambda và yêu cầu nhất quán trong Java

## 1. `var` trong lambda dùng để làm gì?

Từ **Java 11**, Java cho phép khai báo tham số của biểu thức lambda bằng `var`. Đây là tính năng **Local-Variable Syntax for Lambda Parameters (JEP 323)**, mở rộng kiểu cú pháp `var` vốn được bổ sung cho biến cục bộ từ Java 10.

Ví dụ, ba biểu thức sau đều hợp lệ và cùng thực hiện phép cộng hai số nguyên nếu kiểu đích là `BinaryOperator<Integer>`:

~~~java
java.util.function.BinaryOperator<Integer> a = (x, y) -> x + y;
java.util.function.BinaryOperator<Integer> b = (Integer x, Integer y) -> x + y;
java.util.function.BinaryOperator<Integer> c = (var x, var y) -> x + y;
~~~

Đây là các câu lệnh minh họa đặt trong một phương thức hoặc khối khởi tạo. Với `a` và `c`, kiểu tham số được suy ra từ functional interface. Với `b`, kiểu được viết tường minh là `Integer` và phải tương thích với kiểu đích.

**Ý nghĩa quan trọng nhất:** `var` trong tham số lambda **không tự tạo ra kiểu đích** và **không chuyển Java thành ngôn ngữ dynamic typing**. Trình biên dịch vẫn cần biết *functional interface* đang được triển khai; từ phương thức trừu tượng duy nhất (*single abstract method*, SAM), nó mới biết kiểu của từng tham số.

`var` hữu ích đặc biệt khi cần khai báo **annotation** hoặc modifier như `final` trên tham số lambda mà vẫn để trình biên dịch suy ra kiểu. Nó không bắt buộc và không đương nhiên làm lambda chạy nhanh hơn.

## 2. Ba cách viết tham số lambda

Với một functional interface nhận hai `String`:

~~~java
java.util.function.BiFunction<String, String, String> join1 =
        (left, right) -> left + ":" + right;

java.util.function.BiFunction<String, String, String> join2 =
        (String left, String right) -> left + ":" + right;

java.util.function.BiFunction<String, String, String> join3 =
        (var left, var right) -> left + ":" + right;
~~~

Ba cách đều hợp lệ; `join1.apply("a", "b")`, `join2.apply("a", "b")` và `join3.apply("a", "b")` đều trả `"a:b"`.

| Cách viết | Ví dụ | Kiểu tham số được xác định như thế nào? |
|---|---|---|
| Không ghi kiểu (*implicitly typed*) | `(left, right) -> ...` | Suy ra từ SAM của kiểu đích |
| Ghi kiểu tường minh (*explicitly typed*) | `(String left, String right) -> ...` | Ghi trực tiếp, phải phù hợp SAM |
| Dùng `var` (*inferred with var*) | `(var left, var right) -> ...` | Vẫn suy ra từ SAM; có chỗ để ghi annotation/modifier |

Cách thứ ba là lambda có tham số **được suy ra kiểu** như cách thứ nhất, mặc dù về hình thức có chữ `var`. `var` không có nghĩa một tham số có thể tùy ý đổi từ `String` sang `Integer` ở mỗi lần gọi.

Nếu SAM có hai kiểu khác nhau, các tham số viết `var` **không nhất thiết cùng một kiểu**:

~~~java
java.util.function.BiFunction<String, Integer, String> repeat =
        (var text, var times) -> text.repeat(times);
~~~

Trong trường hợp này, `text` được suy ra là `String` và `times` là `Integer`. Phương thức `String.repeat(int)` nhận `int`, nên `times` được unboxing thành `int` khi gọi. `repeat.apply("ha", 3)` trả `"hahaha"`.

## 3. Quy tắc nhất quán: hoặc tất cả dùng `var`, hoặc tất cả không dùng

Khi lambda có từ hai tham số trở lên, Java **không cho phép trộn các kiểu khai báo tham số** trong cùng danh sách. Nếu đã dùng `var` cho một tham số, **mọi tham số khác cũng phải dùng `var`**.

### 3.1. Các dạng hợp lệ

~~~java
// Các câu lệnh minh họa, đều hợp lệ:
java.util.function.BiFunction<Integer, Integer, Integer> add1 =
        (a, b) -> a + b;

java.util.function.BiFunction<Integer, Integer, Integer> add2 =
        (Integer a, Integer b) -> a + b;

java.util.function.BiFunction<Integer, Integer, Integer> add3 =
        (var a, var b) -> a + b;
~~~

Tất cả tham số trong một lambda đều có cùng *cách khai báo*: không ghi kiểu, ghi tường minh hoặc cùng dùng `var`.

### 3.2. Trộn `var` với tham số không ghi kiểu: lỗi

~~~java
// CỐ Ý SAI — không biên dịch:
java.util.function.BiFunction<Integer, Integer, Integer> wrong =
        (var a, b) -> a + b;
~~~

Ở đây `a` được khai báo bằng `var`, còn `b` chỉ có tên. Hai cách viết không thể trộn trong cùng một danh sách. Để sửa, dùng `(var a, var b)` hoặc `(a, b)`.

### 3.3. Trộn `var` với kiểu tường minh: lỗi

~~~java
// CỐ Ý SAI — không biên dịch:
java.util.function.BiFunction<Integer, Integer, Integer> wrong =
        (var a, Integer b) -> a + b;
~~~

Tương tự, `(Integer a, var b)` không hợp lệ. Dùng `(Integer a, Integer b)` hoặc `(var a, var b)`. Việc hai kiểu cuối cùng đều được hiểu là `Integer` **không** làm cú pháp trộn trở nên hợp lệ.

### 3.4. Không được trộn cả kiểu tường minh và tham số bỏ kiểu

Ngay cả trước khi `var` được hỗ trợ, biểu thức `(String a, b) -> ...` cũng không hợp lệ: nó trộn tham số khai báo kiểu tường minh với tham số chỉ ghi tên.

Ghi nhớ quy tắc này theo **cú pháp của cả danh sách**, không phải theo việc các tham số có kiểu dữ liệu giống nhau hay không.

## 4. Dùng `var` với một tham số: phải có dấu ngoặc

Với lambda có đúng một tham số, Java cho phép **bỏ dấu ngoặc** nếu chỉ viết một tên tham số:

~~~java
java.util.function.Function<String, Integer> length1 = text -> text.length();
java.util.function.Function<String, Integer> length2 = (text) -> text.length();
java.util.function.Function<String, Integer> length3 = (var text) -> text.length();
java.util.function.Function<String, Integer> length4 = (String text) -> text.length();
~~~

**Không hợp lệ:**

~~~java
// CỐ Ý SAI — khi dùng var không được bỏ dấu ngoặc:
java.util.function.Function<String, Integer> wrong = var text -> text.length();
~~~

Dạng `text -> ...` không có ngoặc chỉ được dùng khi tham số là **một identifier đơn lẻ**, không kèm `var`, kiểu tường minh, annotation hoặc modifier. Nếu cần `var`, phải dùng `(var text) -> ...`.

Đối với lambda **không có tham số**, luôn dùng cặp ngoặc rỗng `() -> ...` và không có `var`:

~~~java
java.util.function.Supplier<String> message = () -> "ready";
~~~

Không tồn tại kiểu cú pháp `(var) -> ...`, vì `var` phải đi cùng tên của một tham số thực tế.

## 5. Chương trình Java 17 hoàn chỉnh: cùng kiểu đích, ba cách dùng `var`

Lưu mã sau trong file **`LambdaVarDemo.java`**:

~~~java
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaVarDemo {
    public static void main(String[] args) {
        Function<String, Integer> length = (var text) -> text.length();
        BiFunction<Integer, Integer, Integer> sum = (var a, var b) -> a + b;
        Predicate<String> nonBlank =
                (var text) -> text != null && !text.isBlank();

        List<String> words = List.of("Java", "FP", "lambda");
        words.forEach((var word) ->
                System.out.println(word + ":" + length.apply(word)));

        System.out.println("sum=" + sum.apply(2, 3));
        System.out.println("nonBlank=" + nonBlank.test("  "));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac LambdaVarDemo.java
java LambdaVarDemo
~~~

Kết quả stdout chính xác:

~~~text
Java:4
FP:2
lambda:6
sum=5
nonBlank=false
~~~

**Phân tích:**

1. `Function<String, Integer>` có SAM `Integer apply(String)`, nên trong `(var text) -> text.length()`, `text` có kiểu `String`.
2. `BiFunction<Integer, Integer, Integer>` có SAM `Integer apply(Integer, Integer)`, nên `a` và `b` được suy ra là `Integer`. Toán tử `+` kích hoạt unboxing khi tính tổng, rồi kết quả được boxing theo hợp đồng trả về.
3. `Predicate<String>` có SAM `boolean test(String)`, vì vậy biểu thức `nonBlank` kiểm tra `null` và chuỗi rỗng/trắng; với chuỗi hai dấu cách nó trả `false`.
4. `List<String>.forEach` nhận `Consumer<? super String>`; vì thế `word` được suy ra là `String`. Cú pháp `(var word)` không thay đổi thứ tự duyệt danh sách.
5. Dùng `var` ở tham số không làm thay đổi cách gọi `apply`, `test` hoặc `accept`. Lambda vẫn tuân theo hợp đồng của functional interface tương ứng.

Trong ví dụ này, bỏ `var` và viết `text -> ...`, `(a, b) -> ...`, `word -> ...` vẫn cho hành vi tương đương.

## 6. Vì sao `var` có ích khi muốn gắn annotation?

Một lý do thực tế để JEP 323 cho phép `var` trong lambda là **giữ khả năng suy luận kiểu nhưng vẫn có cú pháp khai báo tham số đầy đủ để thêm annotation**.

Ví dụ, có thể muốn đánh dấu tham số trong source code nhằm phục vụ công cụ phân tích tĩnh hoặc annotation processor:

~~~java
@Marker var input
~~~

Đây là phần khai báo tham số, phải nằm trong ngoặc của lambda, như `(@Marker var input) -> ...`. Annotation cần được định nghĩa và có `@Target` phù hợp; `@Marker` trong ví dụ chỉ là tên minh họa.

Nếu chỉ viết lambda kiểu rút gọn `input -> ...`, không có vị trí khai báo tham số theo dạng đủ để gắn `@Marker`. Chúng ta có thể viết kiểu tường minh `(@Marker String input) -> ...`, nhưng đôi khi muốn compiler suy ra kiểu vì nó dài, generic hoặc đã rõ từ kiểu đích. Khi đó `(@Marker var input) -> ...` phù hợp.

### Chương trình chạy được: annotation và `final` với `var`

Lưu thành file **`LambdaAnnotationDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.SOURCE)
@interface NonEmptyContract {}

public class LambdaAnnotationDemo {
    public static void main(String[] args) {
        Function<String, String> normalized =
                (@NonEmptyContract var text) -> text.trim();

        BiFunction<String, String, String> join =
                (@NonEmptyContract final var left, var right) ->
                        left + "-" + right;

        Predicate<String> check =
                (@NonEmptyContract var text) -> !text.isEmpty();

        System.out.println(normalized.apply("  Java  "));
        System.out.println(join.apply("type", "safe"));
        System.out.println(check.test(""));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LambdaAnnotationDemo.java
java LambdaAnnotationDemo
~~~

Stdout:

~~~text
Java
type-safe
false
~~~

**Giải thích:**

- `@Target(ElementType.PARAMETER)` cho phép `@NonEmptyContract` áp dụng lên khai báo tham số; `RetentionPolicy.SOURCE` nghĩa là annotation được dành cho source/compile-time, không được giữ lại để truy vấn tại runtime.
- `(@NonEmptyContract var text)` để Java suy ra kiểu `String` từ `Function<String, String>`, đồng thời cho phép annotation trên tham số.
- `(@NonEmptyContract final var left, var right)` hợp lệ: **cả hai tham số đều dùng `var`**. `final` và annotation là modifier; chúng không biến `left` thành kiểu được ghi tường minh. `final` ngăn gán lại biến tham số `left` trong thân lambda.
- `@NonEmptyContract` trong ví dụ **chỉ là dấu đánh dấu**, không tự động kiểm tra chuỗi rỗng hoặc từ chối `null`. Tên annotation không phải cơ chế validation; nếu cần kiểm tra thực sự phải có logic hoặc công cụ xử lý annotation tương ứng.
- `check.test("")` vẫn trả `false` dù tham số có annotation. Điều đó minh họa rõ việc annotation không tự thay đổi hành vi của lambda.

Đừng suy ra rằng mọi annotation trên tham số lambda sẽ luôn có mặt khi dùng reflection: điều đó phụ thuộc vào target, retention, cách biên dịch và vị trí metadata. Trong ví dụ này, retention là `SOURCE` nên ta **không trông đợi truy vấn runtime**.

## 7. `var` và `final`: nhất quán về **kiểu**, không bắt buộc giống hệt modifier

Quy tắc “tất cả dùng `var`” áp dụng cho **hình thức khai báo kiểu tham số**, không bắt buộc mọi tham số đều có cùng annotation hoặc modifier.

Các dạng minh họa:

~~~java
java.util.function.BiFunction<String, String, String> combine1 =
        (var left, var right) -> left + right;

java.util.function.BiFunction<String, String, String> combine2 =
        (final var left, var right) -> left + right;

java.util.function.BiFunction<String, String, String> combine3 =
        (final var left, final var right) -> left + right;
~~~

Cả ba hợp lệ trong Java 17+. `final` trong khai báo tham số ngăn việc gán lại chính tham số đó, nhưng **không khiến đối tượng tham chiếu trở thành immutable**. Ví dụ nếu kiểu suy ra là `List<String>`, `final var list` vẫn có thể cho phép `list.add(...)` nếu danh sách có thể sửa.

Không được hiểu `final` là cách “sửa” một danh sách tham số trộn kiểu: `(final var left, String right)` vẫn vi phạm yêu cầu nhất quán.

## 8. `var` được suy ra **từ kiểu đích**, không suy ra ngược chỉ từ thân lambda

Lambda không có một kiểu hoạt động độc lập với ngữ cảnh. Ví dụ sau **sai**:

~~~java
// CỐ Ý SAI: không thể suy ra kiểu đích cho biểu thức lambda.
var fn = (var value) -> value.length();
~~~

`var` ở **biến cục bộ bên trái** cần suy ra một kiểu cụ thể từ biểu thức khởi tạo. Tuy nhiên bản thân lambda ở bên phải lại cần một *target type* là functional interface để biết `value` có kiểu gì. Hai phía không đủ thông tin để suy ra hợp đồng phù hợp.

**Cách sửa** là cung cấp kiểu đích:

~~~java
java.util.function.ToIntFunction<String> fn =
        (var value) -> value.length();
~~~

Ở đây `ToIntFunction<String>` xác định SAM `int applyAsInt(String)`; tham số `value` có kiểu `String` và biểu thức `length()` trả `int`.

Đừng nhầm `var` ở **biến cục bộ** với `var` ở **tham số lambda**:

| Vị trí | Ví dụ | Vai trò |
|---|---|---|
| Biến cục bộ | `var count = 10;` | Suy kiểu biến dựa trên initializer, ở đây là `int` |
| Tham số lambda | `(var s) -> s.length()` | Suy kiểu `s` từ SAM của functional interface kiểu đích |
| Biến cục bộ khởi tạo bằng lambda | `var f = (var s) -> ...;` | **Không hợp lệ** nếu không có ngữ cảnh kiểu đích cho lambda |

Có thể dùng `var` để lưu **một đối tượng đã có kiểu functional interface**, chẳng hạn `var f = (java.util.function.Function<String, Integer>) (var s) -> s.length();` vì phép cast cung cấp kiểu đích cho lambda, nhưng cách viết này thường khó đọc hơn khai báo kiểu rõ ràng.

### Generic và suy luận kiểu

Với `Function<List<String>, Integer>`, tham số `(var values)` được hiểu là `List<String>`; phần tử vẫn là `String`. `var` không xóa thông tin generic đã có trong kiểu đích. Tuy nhiên các giới hạn thông thường của Java generics (type erasure, wildcard, bounds) vẫn áp dụng.

### Overload không tự được giải quyết bởi `var`

Nếu một phương thức có nhiều overload nhận các functional interface với chữ ký có thể cùng khớp một lambda, việc thêm `var` vào tham số không bảo đảm chọn được overload. Có thể phải cung cấp biến kiểu rõ ràng hoặc cast sang functional interface cụ thể.

## 9. Các tình huống không nên dùng `var` một cách máy móc

**Không cần `var` chỉ để rút ngắn code.** `(var x) -> x * 2` dài hơn `x -> x * 2`. Khi không có annotation hoặc modifier, cách viết không ghi kiểu thường ngắn và dễ đọc.

**Nên cân nhắc `var` khi có annotation hoặc `final`.** `(@NonNull var input) -> ...` tránh lặp lại kiểu phức tạp nếu đã có annotation thích hợp trong dự án; nhưng một tên annotation chưa có validation không khiến dữ liệu an toàn hơn.

**Đừng dùng `var` để che giấu một API khó hiểu.** Nếu kiểu đích không rõ, hãy đặt tên functional interface, khai báo biến có kiểu tường minh, hoặc dùng method reference phù hợp. `var` không cải thiện một API có quá nhiều overload khó suy đoán.

**Không kỳ vọng tính năng ở Java 8 hoặc Java 10.** Java 10 hỗ trợ `var` cho biến cục bộ trong phạm vi nhất định, nhưng `var` ở **tham số lambda** chỉ được chuẩn hóa từ **Java 11**. Với ứng dụng nhắm Java 17+, ví dụ trong bài hợp lệ.

## 10. Lỗi phổ biến cần tránh

| Sai lầm | Ví dụ sai | Cách sửa |
|---|---|---|
| Trộn `var` và tham số không ghi kiểu | `(var x, y) -> ...` | `(var x, var y) -> ...` hoặc `(x, y) -> ...` |
| Trộn `var` và kiểu tường minh | `(var x, String y) -> ...` | Cả hai `var` hoặc cả hai `String` nếu đúng SAM |
| Bỏ ngoặc quanh `var` ở lambda một tham số | `var x -> ...` | `(var x) -> ...` |
| Dùng `var` thay cho kiểu đích | `var f = (var x) -> ...` | Gán lambda cho `Function<...>`, `Predicate<...>`, v.v. |
| Gắn annotation chưa khai báo hoặc sai target | `(@Missing var x) -> ...` | Định nghĩa/import annotation và kiểm tra `@Target` |
| Cho rằng `var` là `Object` | `(var x)` luôn là `Object` | Kiểu thực sự theo tham số của SAM, có thể là primitive hoặc reference |
| Cho rằng `final var` làm object bất biến | `(final var list) -> ...` | `final` chỉ ngăn gán lại biến tham số |
| Dùng `var` để khắc phục thiếu functional interface | Một interface có hai SAM độc lập | Sửa thiết kế interface/kiểu đích; `var` không thay đổi số SAM |

Đối với lỗi cú pháp, trình biên dịch có thể báo nhiều lỗi nối tiếp. Hãy kiểm tra dòng khai báo lambda và **kiểu đích** trước khi thay đổi logic trong thân lambda.

## 11. Một quy trình đọc và kiểm tra lambda có `var`

Khi gặp biểu thức `(var a, var b) -> a + b` trong codebase, có thể kiểm tra theo thứ tự:

1. **Tìm kiểu đích:** biến được khai báo là `BiFunction`, `BinaryOperator`, functional interface riêng, hay tham số của một phương thức?
2. **Tìm SAM:** phương thức trừu tượng duy nhất nhận bao nhiêu tham số và kiểu gì; trả về kiểu gì?
3. **Suy kiểu từng tham số:** `var a` và `var b` lấy kiểu theo đúng vị trí trong SAM, không phải vì `a + b` “muốn” kiểu gì.
4. **Kiểm tra cú pháp nhất quán:** nếu một tham số dùng `var`, tất cả tham số khác cũng phải dùng `var`.
5. **Kiểm tra annotation/modifier:** annotation có hợp lệ ở parameter không; `final` có bị gán lại trong thân không?
6. **Kiểm tra thân lambda:** biểu thức/kết quả và checked exception có tương thích với SAM và ngữ cảnh sử dụng không?
7. **Chạy biên dịch:** ví dụ sử dụng `javac --release 17` để đảm bảo cú pháp thuộc đúng phiên bản Java dự kiến.

Cách kiểm tra này tách biệt ba vấn đề dễ lẫn: **cú pháp tham số**, **suy luận kiểu** và **hành vi của lambda**. Việc sử dụng `var` chỉ thay đổi cách khai báo tham số; nó không tự giải quyết bất kỳ vấn đề logic nào bên trong thân lambda.

## 12. Câu hỏi tự kiểm tra

1. `(var a, var b) -> a + b` hợp lệ trong Java 11+ khi có kiểu đích `BiFunction<Integer,Integer,Integer>` không? `a` và `b` có kiểu gì?
2. Vì sao `(var a, b) -> ...` không hợp lệ dù trình biên dịch có thể biết cả hai tham số từ SAM?
3. Nếu muốn annotation trên tham số lambda nhưng vẫn để compiler suy ra kiểu, cú pháp nên dùng là gì?
4. `(final var a, var b) -> ...` có vi phạm yêu cầu “cả hai dùng `var`” không?
5. Vì sao `var fn = (var s) -> s.length();` không có đủ thông tin kiểu?
6. Với `BiFunction<String,Integer,String>`, hai tham số `(var text, var count)` có nhất thiết cùng kiểu không?
7. Java 10 có hỗ trợ `var` trong tham số lambda không?
8. Annotation tên `@NonEmptyContract` trong ví dụ có tự từ chối chuỗi rỗng không?

**Đáp án:** (1) Có, cả hai là `Integer`. (2) Java cấm trộn các dạng khai báo tham số lambda. (3) `(@MyAnnotation var parameter) -> ...`, với annotation hợp lệ. (4) Không: kiểu của cả hai vẫn khai báo bằng `var`. (5) Lambda chưa có functional interface kiểu đích. (6) Không: `text` là `String`, `count` là `Integer`. (7) Không, tính năng đó có từ Java 11. (8) Không, annotation minh họa không có logic validation.

## 13. Nguồn đối chiếu chính thức

- [JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): mục tiêu đưa cú pháp `var` vào tham số lambda và giữ quy tắc nhất quán, cho phép annotation.
- [Oracle Java 11 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/11/language/local-variable-type-inference.html): các trường hợp dùng `var` trong lambda và ví dụ không được trộn kiểu.
- [Java Language Specification Java SE 17, `15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): ngữ pháp và suy kiểu của tham số lambda.

**Ghi nhớ:** `var` trong lambda là **cú pháp suy kiểu tham số từ SAM**, không phải một loại kiểu dữ liệu mới. **Trong cùng danh sách tham số lambda, đã dùng `var` thì phải dùng `var` cho tất cả tham số**. Dạng có `var` cần ngoặc, và tính năng này được hỗ trợ từ Java 11; lợi ích nổi bật là có thể ghi annotation hoặc `final` mà vẫn giữ suy kiểu.