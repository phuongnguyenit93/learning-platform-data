# `var` trong lambda: Suy luận kiểu không làm biến trở thành kiểu động

## 1. Ý nghĩa của `var` trong tham số lambda

Từ Java 11, có thể khai báo tham số lambda bằng `var`, chẳng hạn `(var text) -> text.length()`. Đây là **suy luận kiểu tĩnh (static type inference)**: trình biên dịch xác định kiểu của `text` ngay lúc biên dịch, rồi kiểm tra các phép gán, phép toán và lời gọi phương thức dựa trên kiểu đó.

`var` **không** có nghĩa là “kiểu bất kỳ”, không đồng nghĩa với `Object` và không khiến tham số đổi kiểu theo từng lần gọi. Mỗi biểu thức lambda phải có một **kiểu đích (target type)** là một functional interface; chính phương thức trừu tượng duy nhất của interface này cung cấp kiểu tham số cho lambda.

Cú pháp `var` cho biến cục bộ đã có từ Java 10; riêng cú pháp `var` **trong danh sách tham số lambda** được bổ sung từ Java 11. Cả hai vẫn được hỗ trợ trên các phiên bản Java hiện đại.

## 2. Kiểu được suy luận từ đâu?

Xét ba cách viết tương đương:

```java
Function<String, Integer> a = (String text) -> text.length();
Function<String, Integer> b = text -> text.length();
Function<String, Integer> c = (var text) -> text.length();
```

Trong cả ba trường hợp, `Function<String, Integer>` cung cấp hợp đồng `Integer apply(String text)`. Vì vậy, `text` có **kiểu tĩnh `String`**, còn kết quả `text.length()` là `int` được boxing thành `Integer`. Viết `var` chỉ thay đổi cách thể hiện cú pháp, không thay đổi hợp đồng kiểu.

Trình biên dịch thực hiện các bước về mặt khái niệm:

1. Xác định functional interface đích từ phép gán, tham số của phương thức hoặc ngữ cảnh yêu cầu lambda.
2. Lấy kiểu tham số của phương thức trừu tượng tương ứng (sau khi xét các đối số kiểu generic).
3. Gán các kiểu **cố định khi biên dịch** ấy cho tham số được viết bằng `var`.
4. Kiểm tra thân lambda và kiểu giá trị trả về theo hợp đồng của functional interface.

Ví dụ, trong `BiFunction<Integer, Integer, Integer>`, biểu thức `(var left, var right) -> left + right` có `left` và `right` mang kiểu tĩnh `Integer`; phép `+` thực hiện unboxing và kết quả được boxing phù hợp với kiểu trả về. Không có bước nào biến `left` hoặc `right` thành biến có kiểu động.

## 3. Ví dụ Java chạy được

Lưu chương trình dưới tên **`VarLambdaStaticType.java`**:

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

public class VarLambdaStaticType {
    public static void main(String[] args) {
        Function<String, Integer> length =
                (var text) -> text.length();

        BiFunction<Integer, Integer, Integer> sum =
                (var left, var right) -> left + right;

        Predicate<String> hasVisibleText =
                (var text) -> !text.isBlank();

        System.out.println(length.apply("Java 11"));
        System.out.println(sum.apply(4, 6));
        System.out.println(hasVisibleText.test("   "));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (mã chỉ sử dụng tính năng từ Java 11):

```bash
javac VarLambdaStaticType.java
java VarLambdaStaticType
```

Kết quả chính xác:

```text
7
10
false
```

Giải thích: `length` nhận `String`, nên `text.length()` hợp lệ và chuỗi `"Java 11"` dài 7 ký tự. `sum` nhận hai `Integer` và tính `4 + 6 = 10`. `hasVisibleText` nhận `String`; chuỗi chỉ chứa khoảng trắng có `isBlank() == true`, nên biểu thức phủ định trả về `false`. Dù cùng viết `var`, kiểu mỗi tham số đã được xác định từ functional interface của chính lambda đó.

## 4. Những trường hợp vẫn bị từ chối khi biên dịch

Các đoạn sau **cố ý sai**, minh họa lỗi kiểu; không đưa chúng vào chương trình chạy ở trên.

**Không thể gán giá trị khác kiểu cho tham số lambda:**

```java
Function<String, Integer> wrong = (var text) -> {
    text = 123; // Lỗi biên dịch: text có kiểu String, không nhận int.
    return text.length();
};
```

Dù dùng `var`, biến `text` vẫn là `String`. Có thể gán cho nó *một `String` khác* nếu không khai báo `final`; điều đó cũng không làm kiểu thay đổi.

**Kiểu đích khác thì tập phương thức hợp lệ cũng khác:**

```java
Function<Object, Integer> wrong = (var value) -> value.length();
// Lỗi biên dịch: Object không khai báo phương thức length().
```

Một đối tượng thực tế có thể là `String`, nhưng compiler kiểm tra `value` theo kiểu khai báo/suy luận là `Object`, không đoán kiểu dựa trên giá trị sẽ đi vào lúc chạy. Nếu thật sự cần thao tác dành riêng cho `String` trên một `Object`, chương trình phải kiểm tra kiểu hoặc dùng giao diện/API phù hợp.

**Lambda cần một kiểu đích:**

```java
var fn = (var text) -> text.length();
// Lỗi biên dịch: chỉ riêng biểu thức lambda không cung cấp
// functional interface đích để suy luận kiểu cho fn và text.
```

Viết `Function<String, Integer> fn = (var text) -> text.length();` để cung cấp kiểu đích. Quy tắc này cũng áp dụng khi không viết `var` ở tham số.

## 5. Quy tắc cú pháp cần nhớ

- Khi **một** tham số lambda dùng `var`, **tất cả** tham số trong cùng danh sách phải dùng `var`: `(var x, var y) -> x + y` hợp lệ; `(var x, y)` và `(var x, Integer y)` không hợp lệ.
- Với `var`, phải có dấu ngoặc quanh danh sách tham số, kể cả khi chỉ có một tham số: `(var text) -> text.length()`.
- Có thể dùng modifier `final` với tham số viết bằng `var`, chẳng hạn `(final var text) -> text.length()`; lúc đó không thể gán lại giá trị cho tham số. Cú pháp `var` cũng cho phép đặt annotation phù hợp lên tham số khi cần.
- `var` không thay thế cho kiểu trả về, kiểu của field hay các nơi Java yêu cầu kiểu tường minh. Trong ngữ cảnh lambda, suy luận kiểu dựa vào functional interface; nó không tạo ra một loại tham số “dynamic”.

## 6. Cách áp dụng và lỗi tư duy thường gặp

Đọc `Function<String, Integer> formatter = (var s) -> s.length();` như thể đã viết `(String s)`. Khi kiểm tra lỗi, hãy **nhìn kiểu đích trước**, rồi đối chiếu API và kiểu trả về của thân lambda. Nếu kiểu đích là `Function<Object, Integer>`, không thể gọi `s.length()` mà chỉ dựa vào hy vọng đối tượng lúc chạy là `String`.

Có thể dùng `var` để giữ nhất quán kiểu khai báo tham số và bổ sung annotation/modifier khi cần. Nếu chỉ muốn giảm chữ, cú pháp lambda suy luận ngầm như `s -> s.length()` đã đủ. Khi độ rõ ràng quan trọng hơn việc viết gọn, ghi tường minh `(String s)` cũng hoàn toàn hợp lệ.

**Ghi nhớ:** `var` trong lambda là cách yêu cầu compiler **suy luận kiểu tại thời điểm biên dịch** từ functional interface. Java vẫn là ngôn ngữ kiểm tra kiểu tĩnh; một tham số không trở thành biến kiểu động chỉ vì không ghi tên kiểu trong cú pháp.
