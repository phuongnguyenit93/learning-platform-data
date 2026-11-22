# Lambda không tham số, một tham số và nhiều tham số trong Java

Lambda expression là cú pháp ngắn gọn để cung cấp phần triển khai cho **một phương thức trừu tượng duy nhất** của một functional interface. Dấu `->` phân tách **danh sách tham số** và **thân lambda**:

```java
(parameters) -> expression
(parameters) -> { statements; }
```

Đây là hai **mẫu cú pháp tổng quát**, không phải hai chương trình Java độc lập để biên dịch. Một lambda cần ngữ cảnh **kiểu đích (target type)**; compiler dựa vào functional method của interface đó để kiểm tra số tham số, kiểu tham số và kiểu kết quả.

Các dạng thường gặp gồm:
- **Không tham số:** `() -> ...` dùng khi công việc không nhận dữ liệu đầu vào.
- **Một tham số:** `x -> ...` hoặc `(x) -> ...` khi compiler suy luận kiểu.
- **Nhiều tham số:** `(a, b) -> ...`, `(a, b, c) -> ...`, bắt buộc có ngoặc tròn.

Sau bài này, bạn có thể viết cả ba dạng, hiểu cách dùng ngoặc/kiểu tường minh/`var`, sử dụng thân biểu thức và thân khối, và kiểm tra lambda có phù hợp functional interface hay không.

## 1. Bảng quy tắc cú pháp theo số tham số

| Số tham số | Dạng suy luận kiểu | Dạng kiểu tường minh | Functional interface ví dụ |
| --- | --- | --- | --- |
| 0 | `() -> 42` | Không có tham số để ghi kiểu | `Supplier<Integer>` |
| 1 | `x -> x * 2` hoặc `(x) -> x * 2` | `(Integer x) -> x * 2` | `Function<Integer,Integer>` |
| 2 | `(a, b) -> a + b` | `(int a, int b) -> a + b` | `IntBinaryOperator` |
| 3 | `(a, b, c) -> a + b + c` | `(int a, int b, int c) -> a + b + c` | Interface tự định nghĩa |

**Quy tắc bắt buộc:**

1. Danh sách **0 tham số phải viết `()`**. Dạng `-> 42` thiếu phần tham số và không hợp lệ.
2. Với **đúng 1 tham số**, có thể bỏ ngoặc chỉ khi tên tham số không ghi kiểu tường minh và không dùng `var`. `x -> x * 2` và `(x) -> x * 2` cùng hợp lệ.
3. Với **từ 2 tham số**, luôn bao toàn bộ danh sách trong ngoặc: `(a, b) -> ...`. Dạng `a, b -> ...` sai cú pháp.
4. Khi khai báo kiểu tường minh, phải khai báo kiểu cho **mọi tham số**: `(String left, String right)`, không viết `(String left, right)`.
5. Có thể dùng `var` trong danh sách tham số lambda từ Java 11, nhưng nếu dùng thì **tất cả tham số đều dùng `var`**. Dạng `(var a, b)` hoặc `(var a, int b)` không hợp lệ.
6. Một lambda có thể có một thân **biểu thức** hoặc một thân **khối**. Các quy tắc trả kết quả phải khớp với functional method.

Số tham số của lambda khác với số *generic type parameters* của interface. Chẳng hạn `Function<T,R>` có hai tham số kiểu `T`, `R` nhưng functional method `R apply(T value)` chỉ nhận **một đối số**.

## 2. Lambda không tham số: `() -> ...`

Dạng không tham số được dùng khi một thao tác không cần đầu vào. Hai interface điển hình là:

- `Runnable` trong `java.lang`: functional method `void run()` không nhận đối số và không trả kết quả.
- `Supplier<T>` trong `java.util.function`: functional method `T get()` không nhận đối số nhưng trả kết quả kiểu `T`.

Ví dụ minh họa (đặt trong phương thức, với `import java.util.function.Supplier;`):

```java
Runnable printHello = () -> System.out.println("Xin chào");
Supplier<Integer> answer = () -> 42;

printHello.run();
int value = answer.get();  // 42
```

**Việc tạo lambda không chạy ngay thân lambda.** `printHello` chỉ thực hiện khi `run()` được gọi; `answer` tạo giá trị khi `get()` được gọi. Tùy cách triển khai, mỗi lần gọi lại có thể lặp công việc, vì `Supplier` không tự động ghi nhớ kết quả.

Khi thân gồm nhiều câu lệnh, dùng khối:

```java
Supplier<String> code = () -> {
    String prefix = "ID-";
    return prefix + 100;
};
```

Ở đây `get()` trả `"ID-100"`. Đối với `Runnable`, thân rỗng `() -> { }` cũng là một lambda hợp lệ vì `run()` trả `void`.

## 3. Lambda một tham số: `x -> ...`

Dạng một tham số phổ biến trong xử lý Stream, kiểm tra điều kiện, chuyển đổi dữ liệu và callback:

```java
Function<String, Integer> length = text -> text.length();
Predicate<Integer> positive = n -> n > 0;
Consumer<String> printer = text -> System.out.println(text);
```

Đây là mảnh mã minh họa cần các import tương ứng trong `java.util.function`.

- `Function<String,Integer>` có functional method `Integer apply(String input)`, nên compiler suy luận `text` là `String`.
- `Predicate<Integer>` có `boolean test(Integer input)`, nên `n > 0` tạo kết quả `boolean`.
- `Consumer<String>` có `void accept(String input)`, nên lambda được dùng để thực hiện hành động không trả kết quả.

Các cách viết hợp lệ và tương đương cho **một tham số**:

```java
Function<String, Integer> a = text -> text.length();
Function<String, Integer> b = (text) -> text.length();
Function<String, Integer> c = (String text) -> text.length();
Function<String, Integer> d = (var text) -> text.length();
```

Đoạn minh họa này yêu cầu Java 11+ (vì `var` trong lambda), và chạy được trong thân phương thức khi có `import java.util.function.Function;`. Với kiểu tường minh `String` hoặc `var`, dấu ngoặc là bắt buộc. `var` ở đây là suy luận kiểu **tĩnh**, không phải kiểu động; compiler vẫn suy luận `text` thành `String`.

Ví dụ với primitive:

```java
java.util.function.IntUnaryOperator doubling = n -> n * 2;
int result = doubling.applyAsInt(7); // 14
```

`IntUnaryOperator` nhận và trả `int` nguyên thủy nên tránh boxing/unboxing của `Function<Integer,Integer>`.

## 4. Lambda nhiều tham số: `(a, b, ...) -> ...`

Với hai tham số, Java có nhiều interface chuẩn:

```java
BiFunction<Integer, Integer, Integer> sum = (a, b) -> a + b;
BiPredicate<String, String> sameLength =
        (left, right) -> left.length() == right.length();
Comparator<String> byLength =
        (left, right) -> Integer.compare(left.length(), right.length());
```

Đoạn minh họa cần `java.util.function.BiFunction`, `java.util.function.BiPredicate` và `java.util.Comparator`.

- `BiFunction<T,U,R>` nhận hai giá trị và trả `R`.
- `BiPredicate<T,U>` nhận hai giá trị và trả `boolean`.
- `Comparator<T>` nhận hai giá trị cùng kiểu, trả `int` âm/0/dương để mô tả thứ tự.

Các ví dụ với kiểu tường minh:

```java
BiFunction<String, String, String> join =
        (String first, String second) -> first + " " + second;

java.util.function.IntBinaryOperator max =
        (int x, int y) -> x >= y ? x : y;
```

Một interface được phép có functional method với **ba tham số hoặc nhiều hơn**. JDK không cung cấp `TriFunction` tổng quát trong gói `java.util.function`, vì vậy nếu bài toán cần hợp đồng kiểu này, có thể tự định nghĩa:

```java
@FunctionalInterface
interface TriFunction<A, B, C, R> {
    R apply(A first, B second, C third);
}
```

Sau đó trong một phương thức:

```java
TriFunction<Integer, Integer, Integer, Integer> sumThree =
        (a, b, c) -> a + b + c;
int total = sumThree.apply(1, 2, 3); // 6
```

Hai đoạn trên là **mảnh mã liên quan**: interface được khai báo ở cấp top-level, phép gán đặt trong phương thức. Functional interface vẫn chỉ có **một abstract method**, dù method đó nhận ba đối số.

## 5. Chương trình hoàn chỉnh cho 0, 1 và 2 tham số

Lưu thành tệp **`LambdaArityDemo.java`**:

```java
import java.util.Comparator;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

@FunctionalInterface
interface NameTag {
    String apply(String name, String topic);
}

public class LambdaArityDemo {
    public static void main(String[] args) {
        // 0 tham số: ngoặc () bắt buộc.
        Runnable greeting = () -> System.out.println("Không tham số: xin chào");
        Supplier<Integer> answer = () -> 42;
        greeting.run();
        System.out.println("Giá trị: " + answer.get());

        // 1 tham số: có thể bỏ ngoặc nếu kiểu được suy luận.
        Predicate<String> hasText = text -> text != null && !text.isBlank();
        Function<String, Integer> length = (String text) -> text.length();
        System.out.println("Một tham số: " + hasText.test("Java"));
        System.out.println("Độ dài Lambda: " + length.apply("Lambda"));

        // 2 tham số: ngoặc quanh danh sách bắt buộc.
        BiFunction<Integer, Integer, Integer> sum = (a, b) -> a + b;
        Comparator<String> byLength =
                (left, right) -> Integer.compare(left.length(), right.length());
        NameTag tag = (String name, String topic) -> name + " học " + topic;
        System.out.println("Tổng: " + sum.apply(3, 4));
        System.out.println("So sánh: " + byLength.compare("go", "hello"));
        System.out.println("Nhãn: " + tag.apply("Lan", "Java"));
    }
}
```

Dùng JDK 17 trở lên, trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 LambdaArityDemo.java
java LambdaArityDemo
```

**Stdout chính xác:**

```text
Không tham số: xin chào
Giá trị: 42
Một tham số: true
Độ dài Lambda: 6
Tổng: 7
So sánh: -1
Nhãn: Lan học Java
```

`Runnable` đã được tự động import từ `java.lang`; không cần import riêng. `NameTag` là một interface cùng tệp, không có `public`, nên có thể được biên dịch cùng `public class LambdaArityDemo`. Toàn bộ ví dụ minh họa số tham số phải khớp functional method của target type, bất kể dùng suy luận kiểu hay viết tường minh.

## 6. Thân biểu thức và thân khối

Cú pháp tham số và cú pháp thân là hai lựa chọn độc lập.

### 6.1. Thân biểu thức

```java
Function<Integer, Integer> square = n -> n * n;
Predicate<String> hasJ = text -> text.contains("J");
Consumer<String> print = text -> System.out.println(text);
```

Ba dòng là mảnh mã minh họa với các import `Function`, `Predicate`, `Consumer`. Ở hai dòng đầu, giá trị của biểu thức trở thành kết quả functional method. Dòng cuối dùng lời gọi `println` tương thích với method trả `void`. Không dùng từ khóa `return` trong thân biểu thức, ví dụ `n -> return n * n` là cú pháp sai.

### 6.2. Thân khối

```java
Function<Integer, String> sign = n -> {
    if (n < 0) {
        return "âm";
    }
    if (n == 0) {
        return "không";
    }
    return "dương";
};

Consumer<String> log = value -> {
    System.out.println("Bắt đầu");
    System.out.println(value);
};
```

Thân khối cần dấu `{ ... }`; khi trả giá trị, dùng `return expression;` và đảm bảo các đường đi hoàn tất bình thường đều trả kết quả. Với method trả `void`, không được dùng `return value;`; có thể dùng `return;` để kết thúc lambda sớm.

| Target type | Ví dụ hợp lệ | Ví dụ sai |
| --- | --- | --- |
| `Supplier<Integer>` | `() -> 42` hoặc `() -> { return 42; }` | `() -> { System.out.println("x"); }` |
| `Runnable` | `() -> System.out.println("x")` hoặc `() -> { }` | `() -> { return 42; }` |
| `Predicate<String>` | `s -> s.isBlank()` hoặc `s -> { return s.isBlank(); }` | `s -> { System.out.println(s); }` |

Một **statement expression** như lời gọi phương thức có thể phù hợp thân biểu thức của lambda trả `void`; nhưng biểu thức chỉ là literal số `42` thì không. Do đó `Runnable r = () -> 42;` **không hợp lệ**, ngay cả khi Java cho phép bỏ qua giá trị trả về của một số phương thức được gọi dưới dạng câu lệnh.

## 7. Kiểu tham số tường minh và var từ Java 11

Suy luận kiểu dựa vào functional interface:

```java
java.util.function.BiFunction<Integer, Integer, Integer> multiply =
        (x, y) -> x * y;
```

Có thể thay phần tham số bằng `(Integer x, Integer y)` hoặc `(var x, var y)`. Các dạng có cùng kiểu đích, cùng logic nhưng không nên viết đồng thời vào cùng phạm vi với tên biến `multiply` trùng nhau.

**Các dạng sai (cố ý không biên dịch):**

```java
// SAI: trộn var với tham số suy luận kiểu
(var x, y) -> x + y

// SAI: trộn kiểu tường minh và suy luận kiểu
(Integer x, y) -> x + y

// SAI: trộn var với kiểu tường minh
(var x, Integer y) -> x + y

// SAI: có kiểu nhưng thiếu ngoặc cho một tham số
String s -> s.length()

// SAI: hai tham số nhưng thiếu ngoặc
x, y -> x + y
```

Một lambda với kiểu suy luận có thể dùng tên biến ngắn khi ngữ cảnh rõ ràng; với logic nghiệp vụ dài, đặt tên giàu ý nghĩa như `candidate`, `left`, `right`. Việc khai báo kiểu tường minh hữu ích khi cần làm rõ kiểu hoặc hỗ trợ annotation trên tham số.

## 8. Chương trình Java 17: var, thân khối và biến capture

Lưu thành **`LambdaBodyDemo.java`**:

```java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;

public class LambdaBodyDemo {
    public static void main(String[] args) {
        Function<Integer, Integer> square = n -> n * n;
        System.out.println("Bình phương: " + square.apply(5));

        Function<Integer, String> classify = n -> {
            if (n < 0) {
                return "âm";
            }
            if (n == 0) {
                return "không";
            }
            return "dương";
        };
        System.out.println("Phân loại: " + classify.apply(-1));

        Predicate<String> notNull = (var text) -> text != null;
        System.out.println("Không null: " + notNull.test("Java"));

        IntBinaryOperator max = (var x, var y) -> x >= y ? x : y;
        System.out.println("Lớn nhất: " + max.applyAsInt(5, 8));

        int bonus = 5; // effectively final
        IntUnaryOperator addBonus = n -> n + bonus;
        System.out.println("Cộng thêm: " + addBonus.applyAsInt(7));

        Consumer<String> print = text -> System.out.println("Nhận: " + text);
        print.accept("Lambda");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 LambdaBodyDemo.java
java LambdaBodyDemo
```

**Stdout chính xác:**

```text
Bình phương: 25
Phân loại: âm
Không null: true
Lớn nhất: 8
Cộng thêm: 12
Nhận: Lambda
```

`IntBinaryOperator` có functional method `int applyAsInt(int left, int right)`; compiler suy luận `var x` và `var y` thành `int`. Biến local `bonus` được lambda tham chiếu phải là `final` hoặc **effectively final**, nghĩa là không bị gán lại sau khi khởi tạo. Lambda có thể capture đối tượng mutable, nhưng không vì vậy mà đối tượng đó trở nên immutable.

## 9. Kiểu đích và lời gọi phương thức

Lambda không có kiểu độc lập ngoài ngữ cảnh. Nó cần một functional interface phù hợp trong phép gán, truyền đối số hoặc ép kiểu:

```java
java.util.function.Supplier<Integer> makeAnswer = () -> 42;
Runnable print = () -> System.out.println("OK");
```

Hai dòng là minh họa hợp lệ đặt trong phương thức. Dạng `Runnable wrong = () -> 42;` là **sai**, vì `run()` không nhận kết quả và literal `42` không phải statement expression hợp lệ.

Khi truyền lambda làm đối số, compiler suy luận target type từ phương thức nhận đối số:

```java
static void execute(Runnable action) {
    action.run();
}

// Trong phương thức:
execute(() -> System.out.println("Đang chạy"));
```

Đây là hai mảnh mã: khai báo `execute` trong class, rồi gọi nó ở phương thức khác. Nếu nhiều overload nhận các functional interface cùng phù hợp, trình biên dịch có thể báo **ambiguous method call**; hãy dùng kiểu đích rõ ràng hoặc ép kiểu có chủ đích thay vì phỏng đoán compiler luôn chọn đúng overload mong muốn.

Nếu functional method không khai báo checked exception, lambda cũng không thể để checked exception tương ứng thoát ra mà không xử lý. Ví dụ `Runnable.run()` không khai báo `IOException`, nên khi gọi API file có checked exception bên trong lambda, cần xử lý hoặc chọn hợp đồng thích hợp.

## 10. Phạm vi, return và các lỗi thường gặp

1. **Tham số trùng tên:** `(x, x) -> x` sai cú pháp.
2. **Che khuất biến local bao quanh:** nếu phương thức đã có biến local `count`, không thể đặt tên tham số lambda là `count` trong cùng phạm vi.
3. **Biến capture bị gán lại:** lambda không thể tham chiếu biến local không effectively final; hãy tính giá trị mới ở biến khác hoặc thay đổi thiết kế.
4. **Hiểu sai `return`:** `return` trong thân khối lambda kết thúc lời gọi lambda, không thoát luôn khỏi phương thức chứa nó.
5. **Nhầm `this`:** trong lambda thuộc instance method, `this` tham chiếu instance bao quanh; nó không tạo `this` riêng như anonymous class.
6. **Quên gọi functional method:** `Function<String,Integer> f = s -> s.length();` dùng `f.apply("abc")`, không gọi `f("abc")`.
7. **Sai ngoặc:** với hai tham số viết `(a,b)`, với một tham số có kiểu phải viết `(String s)`, với 0 tham số viết `()`.
8. **Trộn kiểu khai báo:** `(var a, b)`, `(int a, b)`, `(var a, int b)` đều sai.
9. **Nhầm kiểu và số tham số:** `BiFunction<T,U,R>` có ba generic arguments nhưng lambda nhận hai đối số.
10. **Chọn sai thân:** `n -> n + 1` là thân biểu thức; `n -> { return n + 1; }` là thân khối. Không viết `n -> { n + 1; }` cho `Function<Integer,Integer>`.
11. **Đặt return không tương thích:** method trả `void` không chấp nhận `return 5;`; method trả giá trị cần nhánh kết quả phù hợp.
12. **Đổi thứ tự tham số:** compiler kiểm tra kiểu theo thứ tự của functional method; hai tham số cùng kiểu có thể lọt qua biên dịch nhưng gây lỗi nghiệp vụ nếu đảo vai trò.

## 11. Lựa chọn nhanh theo bài toán

| Bài toán | Dạng lambda | Kiểu đích điển hình |
| --- | --- | --- |
| Chạy một hành động | `() -> doWork()` | `Runnable` |
| Trì hoãn việc tạo kết quả | `() -> createValue()` | `Supplier<T>` |
| Chuyển đổi một đầu vào | `value -> transform(value)` | `Function<T,R>` |
| Kiểm tra điều kiện | `item -> item.isValid()` | `Predicate<T>` |
| Xử lý giá trị mà không trả kết quả | `item -> print(item)` | `Consumer<T>` |
| Kết hợp hai đầu vào | `(a, b) -> combine(a,b)` | `BiFunction<T,U,R>` |
| So sánh hai giá trị | `(a, b) -> compare(a,b)` | `Comparator<T>` |
| Nhận ba đầu vào | `(a,b,c) -> calculate(a,b,c)` | Functional interface tự định nghĩa |

Các tên `doWork`, `createValue`, `transform` và tương tự trong bảng là **tên ví dụ**; cần được định nghĩa ở code thực tế. Khi lambda chỉ chuyển tiếp đến một phương thức đã có, đôi khi **method reference** như `String::length` rõ hơn. Dù chọn cú pháp nào, target type và functional method vẫn quyết định hợp đồng.

## 12. Tự kiểm tra

**Câu 1.** Viết một lambda không tham số trả chuỗi `"ready"`:

```java
java.util.function.Supplier<String> ready = () -> "ready";
```

**Câu 2.** Vì sao `Predicate<String> longName = name -> name.length() > 5;` có thể bỏ ngoặc?

Vì chỉ có **một tham số suy luận kiểu**. Nếu ghi kiểu tường minh, phải viết `(String name)`.

**Câu 3.** Sửa `a, b -> a + b` như thế nào?

Viết `(a, b) -> a + b` và đặt trong ngữ cảnh target type có hai tham số phù hợp.

**Câu 4.** Hai lambda `n -> n * 2` và `n -> { return n * 2; }` khác nhau gì?

Với target type phù hợp như `Function<Integer,Integer>`, chúng cho cùng kết quả; một dạng dùng thân biểu thức, một dạng dùng thân khối với `return`.

**Câu 5.** `(var x, int y) -> x + y` có hợp lệ với target type nhận hai `int`?

**Không.** Không được trộn `var` và kiểu tường minh. Chọn `(var x, var y)` hoặc `(int x, int y)`.

**Câu 6.** Functional interface có một method nhận ba tham số có dùng lambda được không?

**Có.** “Functional” nghĩa là có **một functional method**, còn method đó có thể nhận ba hoặc nhiều đối số.

**Ghi nhớ:** Khi đọc hoặc viết lambda Java, hãy xác định **số lượng tham số**, **cách dùng dấu ngoặc/kiểu**, **thân biểu thức hay thân khối**, và **chữ ký của functional method trong target type**. Đáp ứng cả bốn giúp lambda biên dịch và thực thi đúng ý định.
