# Quy tắc dùng `var` cho toàn bộ tham số của cùng một lambda (Java 11+)

## 1. Quy tắc cốt lõi

Từ Java 11 (JEP 323), Java cho phép viết `var` ở **tham số của biểu thức lambda**. Khi một lambda có nhiều tham số, **nếu đã dùng `var` cho một tham số thì phải dùng `var` cho tất cả tham số còn lại trong chính lambda đó**. Không được trộn `var` với tham số không ghi kiểu hoặc với tham số ghi kiểu tường minh.

Ví dụ, với một functional interface phù hợp:

~~~java
(a, b) -> a + b                    // HỢP LỆ: cả hai đều suy luận kiểu, không viết var
(var a, var b) -> a + b            // HỢP LỆ: cả hai đều viết var
(int a, int b) -> a + b            // HỢP LỆ: cả hai đều khai báo kiểu int

(var a, b) -> a + b                // SAI: var trộn với tên tham số không ghi kiểu
(a, var b) -> a + b                // SAI: ngược lại cũng không hợp lệ
(var a, int b) -> a + b            // SAI: var trộn với kiểu tường minh
(int a, var b) -> a + b            // SAI: ngược lại cũng không hợp lệ
(int a, b) -> a + b                // SAI: kiểu tường minh trộn với tham số không ghi kiểu
~~~

Các dòng được đánh dấu **SAI** là ví dụ minh họa lỗi biên dịch, không phải mã được phép đưa vào chương trình chạy. Dù số lượng tham số là hai, ba hay nhiều hơn, quy tắc nhất quán áp dụng cho **toàn bộ danh sách tham số của một lambda**.

**Phạm vi quy tắc:** “cùng một lambda” chỉ danh sách tham số ở bên trái dấu `->` của lambda đó. Lambda khác, kể cả lambda lồng bên trong, có danh sách tham số và cách viết riêng; không có quy tắc buộc mọi lambda trong cùng một phương thức phải dùng `var` đồng loạt.

## 2. Vì sao Java yêu cầu đồng nhất?

Lambda trong Java được gán một **kiểu đích** (target type), thường là một functional interface có đúng một phương thức trừu tượng (SAM). Từ chữ ký của phương thức đó, trình biên dịch biết kiểu tham số của lambda.

Có ba cách viết nhất quán:

| Cách khai báo | Ví dụ | Kiểu tham số đến từ đâu? |
| --- | --- | --- |
| Suy luận, không viết `var` | `(a, b) -> a + b` | Từ kiểu đích của lambda |
| Suy luận, có viết `var` | `(var a, var b) -> a + b` | Vẫn từ kiểu đích của lambda |
| Ghi kiểu tường minh | `(int a, int b) -> a + b` | Các kiểu `int` được viết trong danh sách tham số và phải phù hợp kiểu đích |

`var` không phải một kiểu dữ liệu mới, không có nghĩa tham số mang kiểu động và cũng không làm tham số trở thành `Object`. Trong lambda, `var` chỉ yêu cầu trình biên dịch **suy luận kiểu tĩnh** từ ngữ cảnh. Vì vậy, cùng một kiểu đích, hai cách viết `(a, b)` và `(var a, var b)` cho cùng kiểu tham số và cùng ý nghĩa thực thi.

Về quy tắc ngôn ngữ, Java không cho phép pha trộn danh sách tên tham số suy luận kiểu với danh sách khai báo tham số; đồng thời cũng cấm pha trộn tham số có kiểu khai báo với tham số có kiểu suy luận. Việc dùng `var` cho tất cả tham số giữ cho cú pháp nhất quán và giúp trình biên dịch phân tích danh sách tham số rõ ràng.

## 3. Ví dụ Java 11 chạy độc lập: ba cách hợp lệ

Tạo tệp **LambdaVarRule.java**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;

public class LambdaVarRule {
    public static void main(String[] args) {
        // Mỗi tham số đều dùng var.
        IntBinaryOperator sum =
                (var left, var right) -> left + right;

        // Tất cả tham số đều bỏ kiểu và bỏ var.
        IntBinaryOperator product =
                (left, right) -> left * right;

        // Tất cả tham số đều viết kiểu tường minh.
        IntBinaryOperator difference =
                (int left, int right) -> left - right;

        // Lambda một tham số: có var thì cần dấu ngoặc tròn.
        Function<String, Integer> length =
                (var text) -> text.length();

        // BiFunction quy định cả hai tham số đều có kiểu String.
        BiFunction<String, String, String> join =
                (var first, var second) -> first + " " + second;

        System.out.println("sum=" + sum.applyAsInt(2, 3));
        System.out.println("product=" + product.applyAsInt(2, 3));
        System.out.println("difference=" + difference.applyAsInt(7, 3));
        System.out.println("length=" + length.apply("Java"));
        System.out.println("join=" + join.apply("Java", "11"));
    }
}
~~~

Biên dịch và chạy bằng JDK 11 trở lên (nếu dùng JDK mới hơn, tham số `--release 11` kiểm tra mức ngôn ngữ/API Java 11):

~~~bash
javac --release 11 LambdaVarRule.java
java LambdaVarRule
~~~

Kết quả chính xác:

~~~text
sum=5
product=6
difference=4
length=4
join=Java 11
~~~

**Phân tích:**

- `IntBinaryOperator` có phương thức trừu tượng `int applyAsInt(int, int)`; do đó `left` và `right` của lambda `sum` đều là `int`, mặc dù viết `var`.
- `product` dùng hai tên tham số không ghi kiểu. `difference` khai báo `int` cho cả hai. Đây là hai lựa chọn hợp lệ khác với `sum`.
- `Function<String, Integer>` khiến `text` trong `length` có kiểu `String`; gọi `text.length()` được kiểm tra kiểu ngay khi biên dịch.
- `BiFunction<String, String, String>` khiến `first` và `second` đều là `String`. `var` không đoán kiểu từ chuỗi `"Java"` truyền vào lúc chạy.

Các lambda trên cùng tồn tại trong một phương thức nhưng **không cần sử dụng cùng một cách khai báo**, vì quy tắc đồng nhất chỉ xét *từng lambda riêng lẻ*.

## 4. Chẩn đoán và sửa lỗi khi trộn kiểu

Giả sử đã có:

~~~java
IntBinaryOperator operation;
~~~

Các cách gán sau đều **không biên dịch**:

~~~java
operation = (var x, y) -> x + y;
operation = (x, var y) -> x + y;
operation = (var x, int y) -> x + y;
operation = (int x, var y) -> x + y;
operation = (int x, y) -> x + y;
~~~

Khi gặp lỗi, chọn **một** trong ba cách cho *cả hai* tham số:

~~~java
operation = (var x, var y) -> x + y;
// hoặc:
operation = (x, y) -> x + y;
// hoặc:
operation = (int x, int y) -> x + y;
~~~

Cả ba đều hợp lệ với `IntBinaryOperator`. Không có yêu cầu thay đổi phần thân `x + y`; lỗi nằm ở cách khai báo danh sách tham số.

Với lambda ba tham số, chỉ một tham số viết khác cũng đủ khiến cả biểu thức sai:

~~~java
// SAI: tham số thứ ba không viết var.
(a, b, c) -> a + b + c             // HỢP LỆ nếu có kiểu đích phù hợp
(var a, var b, c) -> a + b + c     // SAI
(var a, var b, var c) -> a + b + c // HỢP LỆ nếu có kiểu đích phù hợp
~~~

Các ví dụ ba tham số trên là **đoạn lambda minh họa**, không phải chương trình độc lập. Chúng cần một functional interface nhận ba đối số có phép cộng hợp lệ.

## 5. Trường hợp một tham số và không có tham số

Lambda có **một tham số** không có tham số khác để trộn, nhưng vị trí dấu ngoặc vẫn quan trọng:

~~~java
Function<String, Integer> count1 = text -> text.length();       // ĐÚNG
Function<String, Integer> count2 = (text) -> text.length();     // ĐÚNG
Function<String, Integer> count3 = (var text) -> text.length(); // ĐÚNG
Function<String, Integer> count4 = (String text) -> text.length(); // ĐÚNG

// SAI: không thể bỏ ngoặc quanh khai báo dùng var.
// Function<String, Integer> count5 = var text -> text.length();
~~~

Chỉ khi tham số duy nhất được viết như **một tên đơn thuần** (`text -> ...`) mới có thể bỏ cặp ngoặc. Khi dùng `var`, kiểu tường minh, annotation hoặc modifier, cần dạng `(var text) -> ...` có ngoặc.

Lambda **không có tham số** dùng `() -> ...`; không có tham số nào để áp dụng `var`:

~~~java
Runnable task = () -> System.out.println("done");
~~~

## 6. Khi nào nên dùng `var`? Annotation và modifier

Trong nhiều trường hợp, `(x, y)` ngắn và dễ đọc hơn `(var x, var y)`. Giá trị nổi bật của cú pháp `var` trong lambda là cho phép **annotation** và **modifier** như `final` trên tham số mà vẫn để trình biên dịch suy luận kiểu.

Ví dụ tự chạy, không cần thư viện annotation bên ngoài. Tạo tệp **LambdaVarAnnotation.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.function.BiFunction;

@Target(ElementType.PARAMETER)
@interface Traced {}

public class LambdaVarAnnotation {
    public static void main(String[] args) {
        BiFunction<String, String, String> combine =
                (@Traced var first, final var second) ->
                        first.trim() + "-" + second.trim();

        System.out.println(combine.apply(" core ", " java "));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 11 LambdaVarAnnotation.java
java LambdaVarAnnotation
~~~

Kết quả:

~~~text
core-java
~~~

Ở đây:

- `@Traced` là annotation do ví dụ định nghĩa, có `@Target(ElementType.PARAMETER)`, gắn vào tham số `first`. Bản thân annotation mẫu này **không tự ghi log, kiểm tra null hoặc thay đổi hành vi** của lambda.
- `final var second` hợp lệ: `final` ngăn gán lại tham số `second` trong thân lambda; không yêu cầu tham số `first` cũng phải `final`.
- **Cả hai tham số vẫn dùng `var`**. Có annotation ở một tham số hoặc `final` ở tham số khác không làm mất quy tắc đồng nhất.
- Nếu không cần annotation/modifier, cách `(first, second) -> ...` thường gọn hơn. Nếu muốn ghi kiểu tường minh, dùng kiểu thực cho **tất cả** tham số, chẳng hạn `(String first, String second) -> ...`.

Lưu ý: chỉ đặt một annotation lên tham số không đồng nghĩa annotation đó được xử lý lúc chạy; cách một thư viện dùng annotation phụ thuộc vào chính annotation và công cụ/thư viện tương ứng.

## 7. `var` vẫn cần kiểu đích, không tự xác định kiểu lambda

Lambda không có kiểu độc lập để gán trực tiếp vào một biến cục bộ cũng khai báo bằng `var`. Trình biên dịch phải biết functional interface đích:

~~~java
// SAI: không có functional interface đích để xác định kiểu của lambda.
// var add = (var x, var y) -> x + y;

// ĐÚNG: kiểu đích quy định hai tham số int và kiểu trả về int.
IntBinaryOperator add = (var x, var y) -> x + y;
~~~

Sự khác biệt:

- `var` **bên trái** dấu `=` của một khai báo biến cục bộ yêu cầu suy luận *kiểu biến* từ biểu thức khởi tạo.
- `var` **trong danh sách tham số lambda** yêu cầu suy luận *kiểu tham số* từ functional interface đã có.
- Viết `var` trong lambda không thay đổi kiểu đích, overload resolution, tính an toàn kiểu hay quy tắc chuyển đổi kiểu của Java.

Không nên hiểu `var` là cách né lỗi không khớp kiểu. Nếu thân lambda gọi phương thức không tồn tại trên kiểu tham số được suy luận, lỗi biên dịch vẫn xảy ra.

## 8. Bảng đối chiếu và lỗi phổ biến

| Trường hợp | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `(x, y) -> ...` | Có | Hai tham số cùng dạng suy luận, không viết `var` |
| `(var x, var y) -> ...` | Có | Mọi tham số đều dùng `var` |
| `(String x, String y) -> ...` | Có, nếu hợp kiểu đích | Tất cả tham số ghi kiểu tường minh |
| `(var x, y) -> ...` | Không | Trộn `var` và tham số không ghi kiểu |
| `(x, var y) -> ...` | Không | Vẫn là trộn hai cách suy luận |
| `(var x, String y) -> ...` | Không | Trộn `var` và kiểu tường minh |
| `(String x, var y) -> ...` | Không | Trộn kiểu tường minh và `var` |
| `x -> ...` | Có | Một tham số dạng tên đơn, có thể bỏ ngoặc |
| `(var x) -> ...` | Có | Một tham số có `var`, phải có ngoặc |
| `var x -> ...` | Không | Thiếu ngoặc của khai báo tham số `var` |
| `() -> ...` | Có | Lambda không có tham số, không liên quan `var` |
| `(@Traced var x, var y) -> ...` | Có, nếu annotation hợp lệ | Tất cả tham số vẫn có `var` |
| `(final var x, var y) -> ...` | Có | Modifier có thể khác nhau; cú pháp `var` vẫn đồng nhất |

**Lỗi thường gặp và cách xử lý:**

1. **Thêm `var` vào một tham số rồi quên tham số khác.** Sửa cả danh sách thành `var`, hoặc bỏ `var` khỏi tất cả tham số.
2. **Muốn thể hiện kiểu rõ cho một tham số nhưng giữ `var` cho phần còn lại.** Không được; nếu cần kiểu tường minh thì ghi kiểu cho toàn bộ tham số của lambda.
3. **Bỏ ngoặc khi lambda có một tham số `var`.** Thêm `(` và `)` quanh `var tênThamSố`.
4. **Cho rằng `var` lấy kiểu từ đối số truyền vào khi chạy.** Kiểu được suy luận **khi biên dịch**, từ functional interface đích.
5. **Cho rằng mỗi lambda trong cùng file phải dùng cùng cú pháp.** Chỉ yêu cầu thống nhất *bên trong từng danh sách tham số*.
6. **Dùng annotation nhưng nghĩ annotation sẽ tự thực hiện nghiệp vụ.** Annotation là metadata; hiệu quả cụ thể phụ thuộc vào nơi khai báo và công cụ xử lý nó.

## 9. Checklist áp dụng khi viết và review mã

Khi nhìn thấy một lambda có `var`, hãy kiểm tra lần lượt:

1. Functional interface đích có xác định rõ và có chữ ký phù hợp không?
2. **Mỗi tham số của chính lambda này** đều có `var` chưa?
3. Có vô tình trộn với tên tham số thuần hoặc kiểu tường minh không?
4. Nếu lambda chỉ có một tham số, có đủ ngoặc tròn không?
5. Nếu có annotation/`final`, chúng có hợp lệ cho tham số tương ứng không?
6. Các thao tác trên tham số có hợp với kiểu **được suy luận từ kiểu đích** không?

Ghi nhớ ngắn gọn: **Một lambda, một kiểu khai báo danh sách tham số: tất cả không ghi kiểu; hoặc tất cả `var`; hoặc tất cả ghi kiểu tường minh.** Nếu đã chọn `var`, dùng `var` cho **mọi tham số của lambda đó**.

## Tài liệu chuẩn

- [JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): tính năng được đưa vào Java 11.
- [Java Language Specification, Java SE 27, §15.27.1 Lambda Parameters](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27.1): quy định hiện hành về tham số lambda, kiểu suy luận và việc không được trộn các dạng khai báo.
- [Oracle — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): ví dụ chính thức về `var` trong tham số lambda.

Bài học tập trung vào **quy tắc cú pháp và suy luận kiểu vẫn có hiệu lực trên các Java hiện hành**; không yêu cầu bất kỳ API cũ, thư viện legacy hay tính năng thử nghiệm nào.