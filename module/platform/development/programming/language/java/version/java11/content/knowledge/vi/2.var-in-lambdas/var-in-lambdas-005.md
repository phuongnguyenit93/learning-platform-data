# final, annotation và var trong tham số lambda (Java 11+)

## 1. Bối cảnh và mục tiêu

Từ Java 11 (JEP 323), tham số của **biểu thức lambda** có thể dùng `var` để compiler suy luận kiểu từ *functional interface* đích. Cách viết này đặc biệt hữu ích khi cần gắn `final` hoặc annotation lên tham số mà vẫn không phải lặp lại tên kiểu dài. Đây là cú pháp Java chuẩn và tiếp tục dùng được trên các JDK hiện đại.

Sau bài này, bạn cần phân biệt được ba khái niệm:
- **`var`:** yêu cầu compiler suy luận **kiểu tĩnh** của tham số lambda; không tạo kiểu động.
- **`final`:** cấm gán lại **biến tham số** sau khi nhận đối số; không biến đối tượng được tham chiếu thành bất biến.
- **Annotation:** gắn metadata/ý nghĩa theo định nghĩa annotation và công cụ xử lý; tự nó không bảo đảm kiểm tra dữ liệu lúc chạy.

## 2. Ba cách khai báo tham số lambda vẫn hợp lệ

Giả sử đích là `Function<String, Integer>`, tức phương thức trừu tượng nhận `String` và trả về `Integer`:

```java
Function<String, Integer> length1 = text -> text.length();
Function<String, Integer> length2 = (String text) -> text.length();
Function<String, Integer> length3 = (var text) -> text.length(); // Java 11+
```

Cả ba có cùng ý nghĩa về kiểu: `text` là `String`; kết quả `text.length()` là `int` và được boxing thành `Integer` theo kiểu trả về đích. `var` không suy luận từ giá trị truyền vào ở từng lần gọi, mà từ *target type* khi compiler kiểm tra lambda.

Đối với nhiều tham số, ba hình thức tương ứng là:

```java
BinaryOperator<Integer> add1 = (left, right) -> left + right;
BinaryOperator<Integer> add2 = (Integer left, Integer right) -> left + right;
BinaryOperator<Integer> add3 = (var left, var right) -> left + right;
```

Các ví dụ là **mảnh mã minh họa**; muốn biên dịch riêng, cần đặt chúng trong phương thức/lớp và import `java.util.function.*`. `BinaryOperator<Integer>` xác định cả hai đối số và kết quả là `Integer`.

**Quy tắc đồng nhất bắt buộc:** trong một danh sách tham số lambda, hoặc tất cả đều ghi kiểu cụ thể, hoặc tất cả dùng `var`, hoặc tất cả chỉ dùng tên. Hai cách biểu diễn kiểu suy luận (`var` và tên trần) cũng không được trộn. Khi có `var`, dù chỉ một tham số, phải có cặp ngoặc: `(var text) -> ...`.

## 3. `final` trên tham số lambda

`final` áp dụng như với tham số phương thức: compiler không cho phép gán lại biến đã khai báo `final`. Java 11 cho phép đặt nó trước `var`:

```java
Function<String, String> normalize =
    (final var text) -> text.trim().toUpperCase();
```

Cách khai báo trên tương đương về tính chất `final` với `(final String text) -> ...` nhưng vẫn suy luận kiểu tham số. Nếu bỏ `final`, một tham số lambda thông thường **có thể** được gán lại trong body (dù thường nên tránh để mã dễ hiểu).

```java
// LỖI BIÊN DỊCH: không được gán lại tham số final.
Function<String, String> invalid = (final var text) -> {
    text = text.trim();
    return text;
};
```

`final` chỉ cố định *biến tham chiếu*, không đóng băng trạng thái của đối tượng:

```java
Function<StringBuilder, Integer> append =
    (final var builder) -> {
        builder.append("!");
        return builder.length();
    }; // HỢP LỆ: gọi phương thức thay đổi đối tượng, không gán lại builder.
```

Cần phân biệt `final` **của tham số** với quy tắc **effectively final** của biến bên ngoài được lambda bắt giữ (*capture*):

```java
String prefix = "ID-";
Function<Integer, String> label = (var id) -> prefix + id; // HỢP LỆ
// prefix = "NEW-"; // Nếu bỏ comment, compiler báo lỗi vì prefix bị capture
```

Ở đây `prefix` phải là `final` hoặc *effectively final* (không bị gán lại trên đường thực thi sau khi đã khởi tạo), mặc dù bạn không viết từ khóa `final`. Quy tắc capture tồn tại độc lập với việc tham số `id` có `final` hay có dùng `var`. Tương tự, một tham số lambda bị lambda lồng bên trong capture cũng phải là effectively final.

## 4. Annotation trên tham số: lợi ích chính của `var`

Annotation trên tham số lambda có thể phục vụ kiểm tra tĩnh, hợp đồng API, phân tích mã hoặc tooling khác tùy loại annotation. Trước Java 11, nếu cần annotation trên tham số lambda, thường phải ghi kiểu cụ thể; Java 11 cho phép dùng `(@Marker var value)` để giữ suy luận kiểu.

Ví dụ khai báo một annotation đơn giản:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.SOURCE)
@interface Reviewed {}
```

Sử dụng nó trên tham số lambda có thể theo các dạng:

```java
Function<String, String> a = (@Reviewed var text) -> text.trim();
Function<String, String> b = (@Reviewed final var text) -> text.trim();
Function<String, String> c = (@Reviewed String text) -> text.trim();
```

`@Reviewed` ở đây chỉ là marker mẫu với `RetentionPolicy.SOURCE`: compiler chấp nhận cú pháp và annotation không được lưu để đọc qua reflection lúc chạy. Nó **không** tự kiểm tra `null`, độ dài chuỗi hay điều kiện nghiệp vụ. Muốn có kiểm tra thực sự, phải dùng annotation và bộ xử lý/tooling có hợp đồng rõ ràng, hoặc kiểm tra bằng mã Java.

Phải khai báo `@Target` phù hợp với vị trí gắn annotation: `ElementType.PARAMETER` cho annotation khai báo tham số; `ElementType.TYPE_USE` cho annotation trên vị trí sử dụng kiểu. Không phải mọi annotation đều hợp lệ ở đây. Các tên quen thuộc như `@NotNull`/`@Nullable` không mặc nhiên có trong Java SE với một ngữ nghĩa kiểm tra thống nhất; thư viện và công cụ cụ thể quyết định ý nghĩa của chúng.

Khi một lambda có nhiều tham số, **tất cả vẫn phải dùng `var` nếu chọn dạng này**, nhưng annotation và `final` có thể khác nhau giữa các tham số:

```java
BiFunction<String, String, String> combine =
    (@Reviewed final var left, var right) -> left + "-" + right;
```

Đoạn trên dùng `BiFunction` của `java.util.function` và annotation `Reviewed` đã khai báo ở trên. `left` không thể bị gán lại; `right` không mang `final` tường minh.

## 5. Ví dụ hoàn chỉnh: annotation + `final` + `var`

Lưu đoạn sau thành **`LambdaParametersDemo.java`**. Chương trình không phụ thuộc thư viện bên ngoài, dùng cú pháp Java 11 trở lên.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaParametersDemo {
    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.SOURCE)
    @interface Reviewed {}

    public static void main(String[] args) {
        Function<String, String> normalize =
            (final var text) -> text.trim().toUpperCase();

        Predicate<String> isLong =
            (@Reviewed var text) -> text.length() >= 4;

        BinaryOperator<Integer> sum =
            (@Reviewed final var left, @Reviewed final var right) -> left + right;

        String prefix = "ID-";
        Function<Integer, String> format = (var id) -> prefix + id;

        System.out.println(normalize.apply("  Java  "));
        System.out.println(isLong.test("Java"));
        System.out.println(sum.apply(3, 7));
        System.out.println(format.apply(42));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 11 LambdaParametersDemo.java
java LambdaParametersDemo
```

Nếu đang dùng đúng JDK 11, có thể chạy `javac LambdaParametersDemo.java` rồi `java LambdaParametersDemo`. Kết quả chuẩn:

```text
JAVA
true
10
ID-42
```

Giải thích theo từng lambda:
1. `normalize`: `Function<String, String>` khiến `text` được suy luận là `String`; `final` cấm gán lại `text` nhưng cho phép gọi `trim()`, `toUpperCase()`.
2. `isLong`: `Predicate<String>` yêu cầu kết quả `boolean`; annotation `@Reviewed` chỉ minh họa vị trí cú pháp, không thay đổi phép so sánh `length() >= 4`.
3. `sum`: hai tham số đều được suy luận là `Integer` từ `BinaryOperator<Integer>`; phép `+` thực hiện unboxing/boxing cần thiết; cả hai tham số có `final`.
4. `format`: `id` suy luận là `Integer`, còn `prefix` là biến cục bộ bên ngoài được capture và phải effectively final.

## 6. Các lỗi cú pháp và hiểu nhầm thường gặp

Những mẫu sau **cố ý sai và không biên dịch**; dấu `...` là phần body minh họa, không phải chương trình độc lập.

| Mẫu sai | Lý do | Cách sửa |
| --- | --- | --- |
| `(var x, y) -> ...` | Trộn `var` và tham số chỉ ghi tên. | `(var x, var y) -> ...` hoặc `(x, y) -> ...`. |
| `(var x, String y) -> ...` | Trộn kiểu suy luận và kiểu khai báo tường minh. | `(var x, var y) -> ...` hoặc `(String x, String y) -> ...` (khi phù hợp kiểu đích). |
| `var x -> ...` | Dùng `var` bắt buộc có ngoặc quanh danh sách tham số. | `(var x) -> ...`. |
| `(final x) -> ...` | Không thể dùng modifier trên tham số chỉ ghi tên. | `(final var x) -> ...` hoặc ghi kiểu tường minh. |
| `(@Reviewed x) -> ...` | Annotation cần dạng khai báo tham số có kiểu hoặc `var`. | `(@Reviewed var x) -> ...`. |
| `(var x[]) -> ...` | Không cho phép dấu ngoặc vuông hậu tố trên tham số `var`. | Suy luận dạng `(var x)` từ target type mảng hoặc khai báo `(String[] x)` phù hợp. |
| `(var... items) -> ...` | Không dùng `var` làm loại tham số varargs. | Dùng kiểu tường minh tương ứng, chẳng hạn `(String... items) -> ...`, nếu functional interface phù hợp. |
| `var fn = (var x) -> x;` | Lambda cần một kiểu đích (functional interface); riêng `var` cục bộ không cung cấp kiểu đích cho lambda. | `Function<String, String> fn = (var x) -> x;`. |

Mẫu `(final var x) -> { x = ...; ... }` có thể đúng về **cú pháp khai báo**, nhưng vẫn lỗi biên dịch vì gán lại tham số `final`. Cần tách biệt lỗi khai báo tham số với lỗi trong body.

## 7. Khi nào nên dùng cách nào?

- **Chỉ ghi tên** như `text -> text.trim()`: phù hợp nhất khi lambda ngắn và không cần annotation hay `final`.
- **Ghi kiểu tường minh** như `(String text) -> ...`: hữu ích khi tên kiểu giúp người đọc hiểu hơn hoặc cần trình bày rõ một signature.
- **Dùng `var`** như `(var text) -> ...`: hợp lý nhất khi cần annotation/`final` nhưng muốn compiler suy luận kiểu, nhất là với generic phức tạp.
- **Dùng `final var`**: khi muốn compiler bắt lỗi gán lại biến tham số. Không dùng nó như lời hứa rằng đối tượng sẽ bất biến.
- **Dùng annotation**: khi dự án có ý nghĩa và công cụ xử lý rõ ràng cho annotation ấy; đừng xem marker tùy ý là cơ chế xác thực dữ liệu.

Với lambda nhiều tham số, hãy chọn **một** phong cách khai báo cho toàn bộ danh sách. Với codebase dùng formatter hoặc static analyzer, tuân thủ quy ước của dự án để tránh đổi hình thức liên tục mà không tăng độ rõ ràng.

## 8. Tự kiểm tra

**Câu 1.** `BiFunction<String, String, String> f = (final var a, var b) -> a + b;` có hợp lệ không? **Có.** Cả hai tham số đều dùng `var`; `final` chỉ áp dụng riêng cho `a`.

**Câu 2.** Với `Function<String, Integer> length = (var s) -> s.length();`, khi truyền vào `"abc"` thì compiler có mới quyết định kiểu của `s` không? **Không.** Kiểu `String` đã được xác định lúc biên dịch từ `Function<String, Integer>`.

**Câu 3.** Gắn `@Reviewed` trên tham số có tự làm dữ liệu qua kiểm tra chất lượng không? **Không.** Marker trong ví dụ chỉ có retention `SOURCE`; hành vi kiểm tra chỉ tồn tại khi có công cụ hoặc mã cụ thể thực hiện.

**Câu 4.** Lambda dùng biến `prefix` bên ngoài và không ghi `final` cho biến đó có hợp lệ không? **Có**, nếu `prefix` effectively final. Việc gán lại `prefix` ở cùng phạm vi sẽ làm mã không biên dịch.

## 9. Ghi nhớ và tài liệu chuẩn

`var` cho tham số lambda là tính năng Java 11, **vẫn được hỗ trợ**; nó giữ nguyên kiểm tra kiểu tĩnh. Annotation và `final` là lý do thực tế để chọn cách viết này. Mọi tham số trong cùng lambda phải tuân thủ quy tắc đồng nhất về cách ghi kiểu. `final` và quy tắc effectively final là hai khái niệm liên quan nhưng tác động lên các biến khác nhau trong ví dụ capture.

Tham khảo đặc tả: [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323) và [Java Language Specification `15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27).