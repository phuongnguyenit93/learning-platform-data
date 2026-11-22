# Gắn annotation vào tham số được suy luận trong lambda (`var`, Java 11+)

## 1. Vấn đề cần giải quyết

Lambda Java thường để trình biên dịch suy luận kiểu tham số từ **functional interface** đích:

```java
Function<String, Integer> length = text -> text.length();
```

Ở đây `text` có kiểu `String`, dù không viết `String` bên cạnh tên biến. Nhưng cú pháp tham số rút gọn `text -> ...` hoặc `(text) -> ...` **không cho phép gắn annotation trực tiếp lên khai báo tham số**. Nếu cần annotation, trước Java 11 phải ghi kiểu tường minh, chẳng hạn `(@InputHint String text) -> ...`.

Từ **Java 11**, JEP 323 cho phép dùng `var` trong danh sách tham số lambda để **vẫn suy luận kiểu** mà có chỗ viết annotation hoặc modifier `final`:

```java
Function<String, Integer> length = (@InputHint var text) -> text.length();
```

`@InputHint` là annotation ví dụ được định nghĩa ở phần chương trình hoàn chỉnh bên dưới. Cú pháp `var` này tiếp tục được hỗ trợ trên các phiên bản Java hiện đại.

## 2. `var` suy luận kiểu như thế nào?

Trong `Function<String, Integer>`, phương thức trừu tượng có dạng `Integer apply(String value)`. Vì vậy, với `(@InputHint var text) -> text.length()`, trình biên dịch suy ra tham số `text` có kiểu **`String`** từ functional interface đích. Annotation không tham gia chọn kiểu, không biến tham số thành kiểu động và không làm mất kiểm tra kiểu khi biên dịch.

Ba dạng sau có cùng kiểu tham số khi đích là `Function<String, Integer>`:

```java
Function<String, Integer> a = text -> text.length();
Function<String, Integer> b = (String text) -> text.length();
Function<String, Integer> c = (var text) -> text.length();
```

- `a`: tham số rút gọn, kiểu được suy luận.
- `b`: khai báo kiểu `String` tường minh.
- `c`: kiểu vẫn được suy luận, nhưng dùng dạng khai báo đầy đủ để có thể gắn annotation hoặc `final`.

**Điểm mấu chốt:** `var` ở tham số lambda **không** lấy kiểu từ biểu thức khởi tạo của biến như `var` trong khai báo biến cục bộ thông thường. Nó dựa vào kiểu đích của lambda: `Function`, `Predicate`, `BiFunction`, một functional interface tự định nghĩa, v.v. Vì lambda cần kiểu đích, `var fn = (var x) -> x;` không hợp lệ.

## 3. Ví dụ Java 11+ chạy độc lập

Tạo tệp **`LambdaVarAnnotationDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.function.BiFunction;
import java.util.function.Function;

public class LambdaVarAnnotationDemo {

    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.SOURCE)
    @interface InputHint {}

    public static void main(String[] args) {
        Function<String, String> clean =
                (@InputHint var text) -> text.strip().toUpperCase();

        BiFunction<Integer, Integer, Integer> plus =
                (@InputHint var left, @InputHint var right) -> left + right;

        Function<String, Integer> count =
                (final var text) -> text.length();

        System.out.println(clean.apply("  java 11  "));
        System.out.println(plus.apply(7, 5));
        System.out.println(count.apply("lambda"));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 11 trở lên (ví dụ JDK 17/21):

```bash
javac LambdaVarAnnotationDemo.java
java LambdaVarAnnotationDemo
```

Kết quả chuẩn:

```text
JAVA 11
12
6
```

Giải thích:

1. `@Target(ElementType.PARAMETER)` khai báo `@InputHint` được phép gắn vào **khai báo tham số**; `@Retention(RetentionPolicy.SOURCE)` xác định annotation dùng ở mức mã nguồn.
2. `clean` nhận `String` nên `text.strip()` hợp lệ; `strip()` có từ Java 11, bỏ khoảng trắng hai đầu chuỗi.
3. `plus` dùng hai tham số `var`: `left` và `right` đều được suy luận là `Integer` từ `BiFunction<Integer, Integer, Integer>`. Biểu thức cộng áp dụng unboxing, cho kết quả `12`.
4. `count` minh họa modifier `final` với kiểu suy luận: `text` vẫn là `String` và không được gán lại trong thân lambda.

Annotation `@InputHint` trong ví dụ **chỉ là nhãn minh họa**, không tự kiểm tra dữ liệu đầu vào, không tự loại `null` và không thay đổi kết quả chương trình.

## 4. Cách gắn annotation đúng

Cấu trúc thường dùng:

```java
(@SomeAnnotation var parameter) -> expression
```

Khi có nhiều tham số:

```java
(@SomeAnnotation var first, var second) -> expression
```

Có thể gắn các annotation khác nhau lên từng tham số nếu các annotation đó có `@Target` phù hợp. Một khi đã dùng `var` cho một tham số trong cùng lambda, **tất cả tham số còn lại cũng phải dùng `var`**; không bắt buộc phải gắn annotation cho tất cả.

Khi cần vừa annotation vừa ngăn gán lại tham số, có thể kết hợp với `final`:

```java
Function<String, Integer> length =
        (@InputHint final var text) -> text.length();
```

Ví dụ trên dùng `@InputHint` đã khai báo ở chương trình trước. `final` ngăn phép gán lại biến `text` trong thân lambda; nó không tự làm đối tượng mà `text` trỏ tới trở thành bất biến.

Với chỉ một tham số dùng `var`, **phải có cặp ngoặc**: `(var text) -> ...` hoặc `(@InputHint var text) -> ...`. Cú pháp không ngoặc chỉ dành cho dạng tham số rút gọn, chẳng hạn `text -> ...`.

## 5. Hiểu đúng vai trò của annotation

Annotation là metadata có phạm vi áp dụng do `@Target` quy định và cách lưu giữ do `@Retention` quy định; **bản thân annotation không thực thi kiểm tra hay xử lý nghiệp vụ**. Nếu thư viện có annotation kiểu `@NotNull`/`@NonNull`, ý nghĩa kiểm tra phụ thuộc vào công cụ hoặc framework thực sự hỗ trợ nó. Java không tự chèn lệnh kiểm tra `null` chỉ vì tham số lambda có annotation đó.

Cần phân biệt hai trường hợp:

- **Annotation trên khai báo tham số** (`ElementType.PARAMETER`): công cụ phân tích mã nguồn có thể sử dụng. Theo Java Language Specification, annotation nằm trên *khai báo tham số lambda* **không được lưu vào tệp `.class`**, kể cả khi annotation khai báo retention `CLASS` hoặc `RUNTIME`. Vì vậy, không thiết kế chức năng dựa trên giả định có thể tìm lại annotation khai báo này bằng reflection ở runtime.
- **Annotation trên vị trí sử dụng kiểu** (`ElementType.TYPE_USE`): là loại annotation khác, có quy tắc lưu giữ riêng theo retention; không đánh đồng nó với annotation khai báo tham số. Việc framework/kiểm tra tĩnh đọc và diễn giải annotation nào cần đối chiếu với tài liệu của chính công cụ đó.

Nếu yêu cầu là validation chạy thật khi nhận dữ liệu, hãy viết logic kiểm tra rõ ràng (ví dụ `Objects.requireNonNull(text)`) hoặc dùng cơ chế validation được framework hỗ trợ và kiểm chứng trên đúng điểm tích hợp. Việc thêm `@InputHint` vào lambda không đủ để tạo validation.

## 6. Các quy tắc cú pháp dễ nhầm

### Quy tắc 1 — Không trộn các kiểu khai báo tham số trong cùng lambda

Các đoạn sau **cố ý sai, không dùng trong chương trình chạy**:

```java
// Sai: trộn var với tham số rút gọn
BiFunction<Integer, Integer, Integer> a = (var x, y) -> x + y;

// Sai: trộn kiểu suy luận với kiểu khai báo tường minh
BiFunction<Integer, Integer, Integer> b = (var x, Integer y) -> x + y;

// Sai: trộn tham số khai báo tường minh và var
BiFunction<Integer, Integer, Integer> c = (Integer x, var y) -> x + y;
```

Hai dạng hợp lệ tương ứng:

```java
BiFunction<Integer, Integer, Integer> a = (x, y) -> x + y;
BiFunction<Integer, Integer, Integer> b = (var x, var y) -> x + y;
```

### Quy tắc 2 — Không bỏ kiểu/`var` khi muốn viết annotation

```java
// Sai: @InputHint không biến "text" thành khai báo tham số hợp lệ
Function<String, Integer> bad = (@InputHint text) -> text.length();

// Đúng: có var để trình biên dịch suy luận kiểu
Function<String, Integer> good = (@InputHint var text) -> text.length();

// Cũng đúng: viết kiểu tường minh
Function<String, Integer> explicit = (@InputHint String text) -> text.length();
```

### Quy tắc 3 — Lambda phải có kiểu đích

```java
// Sai: lambda không có kiểu đích đủ để suy luận tham số
var bad = (@InputHint var text) -> text.length();

// Đúng
Function<String, Integer> good = (@InputHint var text) -> text.length();
```

### Quy tắc 4 — Kiểm tra `@Target` của annotation

Nếu annotation chỉ cho phép `ElementType.METHOD`, bạn không thể gắn nó vào tham số lambda. Nếu muốn minh họa annotation trên khai báo tham số, hãy khai báo `@Target(ElementType.PARAMETER)` như ví dụ hoàn chỉnh. Với annotation của thư viện, đọc `@Target`/tài liệu chính thức trước khi sử dụng; không thay annotation tùy tiện để làm code biên dịch.

### Quy tắc 5 — `var` không làm lỏng hệ thống kiểu

Khi đích là `Function<String, Integer>`, tham số vẫn là `String`. Viết lời gọi phương thức không tồn tại trên `String` sẽ báo lỗi biên dịch dù tham số được ghi `var`. Đối với kiểu generic, kiểu suy luận phải thỏa hợp đồng của functional interface; `var` không bỏ qua quy tắc generic.

## 7. Chọn kiểu viết nào trong thực tế?

- **Không cần annotation hoặc modifier:** ưu tiên dạng ngắn, dễ đọc, như `text -> text.strip()` hoặc `(x, y) -> x + y`.
- **Cần gắn annotation khi vẫn muốn suy luận kiểu:** dùng `(@Annotation var x) -> ...`, bảo đảm `@Target` phù hợp và cả danh sách tham số tuân thủ quy tắc `var`.
- **Cần chủ động thể hiện kiểu trong mã nguồn:** dùng kiểu tường minh `(@Annotation String x) -> ...` khi phù hợp ngữ cảnh; Java 11 không bắt buộc dùng `var`.
- **Cần hành vi runtime thực sự:** kiểm tra logic hoặc framework hỗ trợ; không suy diễn việc thực thi từ annotation gắn trên tham số lambda.

Một bài tập tự kiểm tra: nếu `BiFunction<String, String, String> combine` cần gắn `@InputHint` cho tham số đầu, dạng hợp lệ là:

```java
BiFunction<String, String, String> combine =
        (@InputHint var left, var right) -> left + " / " + right;
```

`left` và `right` đều suy luận là `String`. Không cần gắn `@InputHint` cho `right`, nhưng vẫn phải viết `var right`.

## 8. Ghi nhớ

`var` trong tham số lambda là cú pháp được bổ sung từ Java 11 để giữ **suy luận kiểu tĩnh** đồng thời cho phép **annotation/`final`** trên tham số. Kiểu vẫn đến từ functional interface đích; mọi tham số trong cùng lambda phải dùng một phong cách nhất quán. Annotation phải hợp lệ theo `@Target` và không tự sinh validation; đặc biệt, annotation **trên khai báo** tham số lambda không được bảo toàn trong `.class`.

### Tài liệu chính thức

- [JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323)
- [Java Language Specification, `15.27.1 — Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.1)
- [Java Language Specification, `9.6.4.2 — Retention và `9.7.4 — Vị trí annotation](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2)
