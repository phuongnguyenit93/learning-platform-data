# Cấu trúc cú pháp lambda trong Java: tham số, dấu `->` và phần thân

## 1. Lambda là gì và đọc cú pháp như thế nào?

Biểu thức lambda (*lambda expression*) là cách cung cấp phần triển khai của **phương thức trừu tượng duy nhất** trong một giao diện hàm (*functional interface*), thường ngắn gọn hơn lớp ẩn danh. Một lambda có ba thành phần:

```text
(danh_sách_tham_số) -> biểu_thức
(danh_sách_tham_số) -> { các_câu_lệnh }
```

- **Bên trái `->`** mô tả số lượng và tên tham số; có thể khai báo kiểu tường minh, để trình biên dịch suy luận kiểu, hoặc dùng `var` (Java 11+).
- **Dấu `->`** tách danh sách tham số khỏi phần thân. Đây không phải toán tử so sánh hay lệnh `return`.
- **Bên phải `->`** là một biểu thức duy nhất (*expression body*) hoặc một khối lệnh (*block body*) được bao bằng `{ ... }`.

Chẳng hạn `(left, right) -> left + right` cho biết hành vi cộng hai đối số nhưng chưa xác định hoàn toàn kiểu của chúng. Java cần **kiểu đích** (*target type*) như `BinaryOperator<Integer>` hoặc `IntBinaryOperator` để kiểm tra kiểu tham số và kiểu kết quả. Lambda không tự có một kiểu độc lập có thể được gán vô điều kiện.

Mục tiêu học tập: viết được lambda với 0, 1, nhiều tham số; biết khi nào cần dấu ngoặc; hiểu suy luận kiểu và `var`; phân biệt thân biểu thức với thân khối, cú pháp `return`, cách dùng kiểu đích và sửa lỗi biên dịch thường gặp.

## 2. Cú pháp danh sách tham số

| Trường hợp | Cú pháp | Kiểu đích minh họa | Ý nghĩa |
| --- | --- | --- | --- |
| Không có tham số | `() -> 42` | `Supplier<Integer>` | Cần cặp ngoặc tròn rỗng |
| Một tham số suy luận kiểu | `s -> s.length()` | `Function<String, Integer>` | Có thể bỏ ngoặc tròn |
| Một tham số suy luận kiểu, có ngoặc | `(s) -> s.length()` | `Function<String, Integer>` | Tương đương dạng trên |
| Một tham số ghi kiểu | `(String s) -> s.length()` | `Function<String, Integer>` | Bắt buộc có ngoặc |
| Một tham số ghi `var` | `(var s) -> s.length()` | `Function<String, Integer>` | Java 11+, bắt buộc có ngoặc |
| Hai tham số suy luận kiểu | `(a, b) -> a + b` | `BinaryOperator<Integer>` | Hai tên cách nhau bởi dấu phẩy |
| Hai tham số ghi kiểu | `(int a, int b) -> a + b` | `IntBinaryOperator` | Mỗi tham số ghi kiểu |
| Hai tham số dùng `var` | `(var a, var b) -> a + b` | `BinaryOperator<Integer>` | Mỗi tham số ghi `var` |

Các quy tắc cần nhớ:

1. **Không có tham số:** luôn viết `()`; không thể viết `-> 42`.
2. **Một tham số có kiểu suy luận và chỉ có tên:** có thể viết `x -> x + 1` hoặc `(x) -> x + 1`.
3. **Một tham số đã ghi kiểu tường minh, `var`, `final`, hay annotation:** phải viết ngoặc `(...)`.
4. **Hai tham số trở lên:** luôn phải đặt trong `(...)`, cách nhau bằng dấu phẩy.
5. **Trong một danh sách tham số, giữ hình thức khai báo nhất quán:** hoặc đều suy luận kiểu, hoặc đều ghi kiểu, hoặc đều dùng `var`.

Ví dụ khi đã import `java.util.function.Function`:

```java
Function<String, Integer> a = s -> s.length();
Function<String, Integer> b = (s) -> s.length();
Function<String, Integer> c = (String s) -> s.length();
Function<String, Integer> d = (var s) -> s.length();
```

Đây là các lệnh minh họa để đặt trong thân một phương thức. Cả bốn tham số `s` đều có kiểu `String` do kiểu đích quyết định. Với `var`, Java vẫn kiểm tra kiểu tĩnh và dựa vào kiểu đích; `var` không biến lambda thành hàm nhận kiểu động.

Đoạn sau **cố ý sai cú pháp**, không đưa vào chương trình chạy:

```text
(int a, b) -> a + b        // Trộn khai báo kiểu với tham số suy luận
(var a, b) -> a + b        // Trộn var với tham số suy luận
(var a, int b) -> a + b    // Trộn var với kiểu tường minh
int x -> x * x            // Kiểu tường minh nhưng thiếu ngoặc
```

Viết lại tương ứng bằng `(a, b)`, `(int a, int b)`, `(var a, var b)` hoặc `(int x)` theo đúng kiểu đích.

## 3. Dấu `->` và vai trò của kiểu đích

Đọc `parameters -> body` là “nhận các tham số này rồi thực hiện phần thân kia”. Dấu `->` **không gọi hàm ngay**. Với ví dụ:

```java
Runnable task = () -> System.out.println("Chạy");
task.run();
```

Lệnh gán tạo một giá trị thực thi giao diện `Runnable`. Chỉ khi gọi `task.run()`, phần thân mới được chạy. Đoạn này được đặt trong thân một phương thức Java.

Một lambda cần kiểu đích là functional interface, ví dụ:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();
```

Ở đây, phương thức chức năng `apply(String)` trả `Integer`; trình biên dịch suy ra `text` là `String` và tự boxing kết quả `int` của `length()`. Kiểu đích cũng có thể đến từ tham số của một phương thức, từ giá trị trả về hoặc từ biểu thức ép kiểu.

```java
static void execute(Runnable task) {
    task.run();
}

// Ở trong thân một phương thức khác:
execute(() -> System.out.println("done"));
```

Lời gọi cuối hợp lệ vì `execute` nhận `Runnable`. Còn đoạn sau cố ý sai:

```text
var f = x -> x + 1;   // Không có kiểu đích để suy ra kiểu chức năng
```

Dù `var` dùng được khi khai báo biến cục bộ, nó không thể tự suy ra functional interface từ một lambda độc lập. Cách đúng, khi cần xử lý số nguyên:

```java
java.util.function.IntUnaryOperator f = x -> x + 1;
```

Cẩn thận với **overload**: hai phương thức trùng tên nhận các functional interface khác nhau có thể khiến lời gọi lambda mơ hồ. Có thể khai báo biến lambda với kiểu đích rõ ràng hoặc ép kiểu theo đúng hợp đồng mong muốn.

## 4. Phần thân biểu thức (expression body)

Bên phải dấu `->` có thể là **một biểu thức**:

```java
Function<Integer, Integer> square = x -> x * x;
Predicate<String> nonEmpty = s -> !s.isEmpty();
Runnable greet = () -> System.out.println("Hi");
```

Các ví dụ cần `import java.util.function.Function;` và `import java.util.function.Predicate;`, đặt trong thân phương thức. Dấu `;` ở cuối mỗi khai báo biến kết thúc **câu lệnh Java bên ngoài**; nó không thuộc bản thân biểu thức lambda.

Khi phương thức chức năng có giá trị trả về, kết quả của biểu thức được dùng làm kết quả lambda. Vì vậy:

```text
x -> x * x            // Đúng với kiểu đích nhận số và trả số
x -> return x * x;    // Sai: return là câu lệnh, không phải biểu thức
```

Với phương thức chức năng trả `void` (ví dụ `Runnable.run` hoặc `Consumer.accept`), một thân biểu thức phải là **biểu thức có thể dùng làm câu lệnh** (*statement expression*), như lời gọi phương thức, phép gán, phép tăng/giảm hoặc tạo đối tượng. `() -> System.out.println("Hi")` phù hợp với `Runnable`. Nhưng `() -> 1 + 2` không phù hợp với `Runnable`: phép cộng thuần túy không phải statement expression.

Đừng nhầm **giá trị trả về của biểu thức** với câu lệnh `return`. Biểu thức `n -> n * 2` không cần viết `return` vì phần thân chỉ có biểu thức.

## 5. Phần thân khối lệnh (block body)

Khi cần nhiều câu lệnh, khai báo biến cục bộ, phân nhánh hoặc ghi log, đặt phần thân trong `{ ... }`:

```java
Function<Integer, Integer> square = x -> {
    int result = x * x;
    return result;
};

Consumer<String> print = text -> {
    System.out.println("Nhận: " + text);
};
```

Đây là các câu lệnh minh họa trong phương thức có import `Function` và `Consumer`.

- Với SAM **có kiểu trả về**, thân khối phải `return` giá trị phù hợp khi kết thúc bình thường. Trong một `if/else`, các đường đi tương ứng cần đáp ứng yêu cầu trả về.
- Với SAM trả **`void`**, thân khối chỉ thực hiện công việc; có thể dùng `return;` để kết thúc sớm, nhưng không dùng `return value;`.
- `x -> { x * 2; }` không hợp lệ vì phép nhân `x * 2` không phải statement expression, đồng thời thiếu kết quả nếu kiểu đích là `Function<Integer, Integer>`.
- `x -> { x.toString(); }` có câu lệnh hợp lệ, nhưng nếu kiểu đích trả `String` thì vẫn sai vì **thiếu `return`**.

Ví dụ so sánh hai dạng tương đương:

```java
java.util.function.IntUnaryOperator one = n -> n * 2;
java.util.function.IntUnaryOperator two = n -> {
    return n * 2;
};
```

Với `IntUnaryOperator`, cả hai nhận `int`, trả `int` và cho cùng kết quả ở cùng đầu vào. Dạng khối dùng `return` tường minh; dạng biểu thức không cần.

## 6. Ví dụ Java 17 hoàn chỉnh: nhiều kiểu tham số và phần thân

Lưu toàn bộ chương trình vào tệp `LambdaStructureDemo.java`:

```java
import java.util.Locale;
import java.util.function.BinaryOperator;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaStructureDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String left, String right);
    }

    public static void main(String[] args) {
        Runnable sayHello = () -> System.out.println("hello");

        Function<String, Integer> length = s -> s.length();
        Function<String, String> normalize =
                (String s) -> s.strip().toUpperCase(Locale.ROOT);

        BinaryOperator<Integer> add = (left, right) -> left + right;
        Predicate<String> longName = (var name) -> name.length() >= 4;

        Function<Integer, Integer> squared = n -> {
            int result = n * n;
            return result;
        };

        Consumer<String> printUpper = word -> {
            System.out.println(word.toUpperCase(Locale.ROOT));
        };

        Formatter join = (left, right) -> left + ":" + right;

        sayHello.run();
        System.out.println(length.apply("Java"));
        System.out.println(normalize.apply("  java "));
        System.out.println(add.apply(3, 4));
        System.out.println(longName.test("Lambda"));
        System.out.println(squared.apply(5));
        printUpper.accept("syntax");
        System.out.println(join.format("A", "B"));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 LambdaStructureDemo.java
java LambdaStructureDemo
```

Đầu ra chính xác:

```text
hello
4
JAVA
7
true
25
SYNTAX
A:B
```

**Giải thích:**

1. `()->...` của `Runnable` không nhận tham số; `sayHello.run()` kích hoạt lambda.
2. `s -> s.length()` suy luận tham số `String`, bỏ ngoặc tròn, kết quả `int` được boxing thành `Integer` cho `Function`.
3. `(String s) -> ...` khai báo kiểu tường minh, bắt buộc ngoặc; `strip()` xóa khoảng trắng đầu và cuối, `toUpperCase(Locale.ROOT)` chuyển thành chữ hoa.
4. `(left, right) -> ...` nhận hai tham số `Integer`, cho phép phép cộng nhờ unboxing/boxing.
5. `(var name) -> ...` dùng cú pháp `var` cho tham số (Java 11+), nhận `String` từ `Predicate<String>` và tạo kết quả `boolean`.
6. `n -> { ... return result; }` có thân khối, biến cục bộ và `return` tường minh.
7. `word -> { System.out.println(...); }` là thân khối trả `void` của `Consumer`.
8. `Formatter` cho thấy lambda cũng dùng được với giao diện hàm tự khai báo; `format(String, String)` là SAM của giao diện.

Dấu `->` chỉ tạo hành vi phù hợp kiểu đích. Các phép biến đổi xuất hiện trong phần thân chưa thực thi tại thời điểm khai báo biến `sayHello`, `length` hoặc `normalize`.

## 7. Kiểu tường minh, `var`, `final` và tham số nguyên thủy

Cú pháp ghi tường minh kiểu rất hữu ích khi muốn cho người đọc thấy chính xác kiểu dữ liệu:

```java
java.util.function.IntBinaryOperator add =
        (int a, int b) -> a + b;
java.util.function.Function<String, Integer> count =
        (final String text) -> text.length();
```

Đây là các lệnh minh họa cần đặt trong một phương thức. `IntBinaryOperator` có hai tham số `int` và kết quả `int`, không phát sinh boxing của `Integer`; `final String text` không cho gán lại tham số `text` trong phần thân, nhưng không có nghĩa mọi đối tượng được tham chiếu đều bất biến.

Nếu dùng `var`, hãy ghi **tất cả** tham số là `var`, ví dụ `(var left, var right) -> left + right`. Trong lambda, `var` vẫn dựa trên kiểu đích nên không nhận các giá trị tùy ý ngoài hợp đồng.

Một giao diện như `Function<String, Integer>` chỉ nhận **một** đối số, nên không thể dùng cho lambda `(a, b) -> a + b`. Nếu cần hai đối số, dùng `BiFunction<A, B, R>`, `BinaryOperator<T>`, hoặc giao diện hàm tự khai báo.

## 8. Phạm vi tên và biến được lambda ghi nhớ

Tham số lambda là biến cục bộ trong thân lambda. Không được khai báo trùng tên hai tham số trong một lambda. Không nên cố gắng khai báo lại một biến cục bộ đang tồn tại trong phạm vi phương thức bao quanh; lambda không mở ra phạm vi độc lập cho việc che khuất tên theo cách một số lớp lồng nhau có thể làm.

Lambda có thể tham chiếu biến cục bộ bên ngoài nếu biến đó là `final` hoặc **effectively final** (sau khởi tạo không bị gán lại). Ví dụ độc lập dưới đây:

```java
import java.util.function.IntUnaryOperator;

public class LambdaCaptureDemo {
    public static void main(String[] args) {
        int increment = 3;
        IntUnaryOperator add = n -> n + increment;

        System.out.println(add.applyAsInt(4));
        System.out.println(add.applyAsInt(10));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LambdaCaptureDemo.java
java LambdaCaptureDemo
```

Kết quả:

```text
7
13
```

Nếu thêm `increment = 4;` sau khi khai báo biến trong phương thức, trình biên dịch không chấp nhận lambda bắt giữ `increment` vì biến không còn effectively final. Quy tắc này không tự biến các đối tượng có trạng thái thành bất biến hoặc an toàn trong môi trường đa luồng.

## 9. Lambda lồng nhau

Phần thân biểu thức của lambda có thể chính là một lambda khác nếu kiểu đích yêu cầu trả về giao diện hàm:

```java
java.util.function.Function<Integer, java.util.function.IntUnaryOperator>
        makeAdder = amount -> number -> amount + number;
```

Đây là lệnh minh họa đặt trong thân một phương thức. `makeAdder.apply(3)` tạo một `IntUnaryOperator`, sau đó `applyAsInt(4)` trả `7`. Lambda ngoài nhận `amount`, phần thân của nó là lambda trong nhận `number`; cú pháp `->` được dùng hai lần vì có hai hàm. Đừng nhầm việc tạo hàm mới với việc thực hiện phép cộng.

## 10. Lỗi cú pháp hoặc sai kiểu thường gặp

| Đoạn mã/nhận định sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| `() -> 42` gán cho `Runnable` | Phép đọc số không phải statement expression cho SAM `void` | Dùng `Supplier<Integer>` hoặc thân thực hiện thao tác `void` |
| `x -> return x * x;` | `return` không thể là expression body | `x -> x * x` hoặc `x -> { return x * x; }` |
| `x -> { x * 2; }` gán cho `Function<Integer, Integer>` | Phép nhân không là câu lệnh; thiếu kết quả | `x -> x * 2` |
| `x -> { x.toString(); }` gán cho `Function<Integer, String>` | Có lời gọi nhưng chưa trả kết quả | `x -> { return x.toString(); }` |
| `() -> { return 1; }` gán cho `Runnable` | SAM trả `void`, không thể `return` giá trị | Chọn `Supplier<Integer>` nếu cần kết quả |
| `(a, b) -> a + b` gán cho `Function<Integer, Integer>` | `Function` chỉ nhận một đối số | Dùng `BiFunction<Integer, Integer, Integer>` hoặc `BinaryOperator<Integer>` |
| `var inc = x -> x + 1;` | Không có kiểu đích cho lambda | `IntUnaryOperator inc = x -> x + 1;` |
| `(var a, int b) -> a + b` | Trộn kiểu khai báo tham số | Dùng `(var a, var b)` hoặc `(int a, int b)` |
| Thân khối có `if` nhưng thiếu `return` ở một nhánh | Không đáp ứng kết quả SAM yêu cầu | Xem mọi đường đi có thể hoàn tất và trả giá trị thích hợp |
| Tưởng lambda chạy ngay khi gán | Gán chỉ tạo hành vi | Gọi `run`, `apply`, `test`, `accept` hoặc API khác sẽ thực thi |

## 11. Tự luyện tập

**Bài 1:** Tách ba phần của `Predicate<String> p = s -> s.length() >= 3;`. Đáp án: tham số `s` được suy ra là `String`, dấu `->` chia hai phía, phần thân `s.length() >= 3` trả `boolean`.

**Bài 2:** Viết lại `IntUnaryOperator doubleValue = n -> n * 2;` sang thân khối. Đáp án:

```java
IntUnaryOperator doubleValue = n -> {
    return n * 2;
};
```

Câu lệnh ở trong phương thức đã import `java.util.function.IntUnaryOperator`.

**Bài 3:** Chọn kiểu đích cho `(a, b) -> a.concat(b)` khi hai đối số đều là `String`. Đáp án: `BinaryOperator<String>` (hai đầu vào cùng kiểu, trả về cùng kiểu). `Function<String, String>` không phù hợp vì có một tham số.

**Bài 4:** Sửa `Function<String, Integer> size = (String s) -> { s.length(); };`. Đáp án: đổi thành `(String s) -> { return s.length(); }` hoặc `s -> s.length()`.

**Bài 5:** `(var a, var b) -> a + b` hợp lệ khi nào? Đáp án: trong Java 11+ khi có kiểu đích tương thích, ví dụ `BinaryOperator<Integer>`; mọi tham số đều sử dụng `var` và kiểu được suy luận tĩnh.

## 12. Ghi nhớ

- Một lambda có cấu trúc **tham số → dấu `->` → phần thân**.
- Với **0 tham số**, viết `()`; với **1 tham số suy luận kiểu** có thể bỏ ngoặc; với **nhiều tham số** cần `(...)`.
- Có kiểu tường minh, `final`, `var` thì giữ ngoặc; không trộn các hình thức khai báo tham số trong cùng lambda.
- **Expression body** là một biểu thức, không viết `return`; **block body** có dấu `{ ... }` và dùng `return` theo kiểu trả về của SAM.
- `var` trong tham số lambda không có nghĩa động; lambda cần **kiểu đích** là functional interface.
- Lambda chỉ được thực thi khi phương thức chức năng được gọi; tránh nhầm lẫn thời điểm tạo hành vi với thời điểm chạy.

Tài liệu đối chiếu: [Java Language Specification, §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27) và [§9.8 Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).