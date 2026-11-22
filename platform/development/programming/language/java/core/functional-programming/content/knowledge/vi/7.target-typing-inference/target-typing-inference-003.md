# Kiểm tra tương thích tham số và kiểu kết quả của lambda trong Java

## 1. Mục tiêu: lambda có khớp hợp đồng mà nơi sử dụng yêu cầu không?

Trong Java, biểu thức lambda như `x -> x * 2` **không mang sẵn một kiểu hàm độc lập**. Nó được kiểm tra trong *ngữ cảnh kiểu đích* (*target type*): kiểu của biến được gán, tham số phương thức đang gọi, kiểu trả về hoặc kiểu của phép ép kiểu. Kiểu đích phải là một **functional interface** hợp lệ.

Functional interface có một phương thức trừu tượng chức năng (*single abstract method*, SAM). Chữ ký chức năng (*function descriptor*) cho biết số tham số, kiểu từng tham số, kiểu kết quả và những checked exception có thể ném. Java đối chiếu biểu thức lambda với descriptor ấy để xác định lambda có **tương thích** hay không.

Ví dụ:

~~~java
java.util.function.IntUnaryOperator square = x -> x * x;
java.util.function.Predicate<String> nonEmpty = text -> !text.isEmpty();
java.util.function.Consumer<String> print = text -> System.out.println(text);
~~~

Ba câu lệnh trên hợp lệ khi được đặt trong một phương thức. Nhưng cùng một cách viết lambda không thể gán tùy ý cho mọi interface: `square` yêu cầu `int → int`, `nonEmpty` yêu cầu `String → boolean`, còn `print` yêu cầu `String → void`.

**Quy trình kiểm tra cốt lõi:** (1) tìm kiểu đích; (2) tìm SAM; (3) đối chiếu **số lượng và kiểu tham số**; (4) đối chiếu **dạng thân và kết quả**; (5) đối chiếu **checked exception**, khả năng truy cập và các ràng buộc liên quan.

## 2. Xác định kiểu đích và chữ ký SAM trước

Một số interface quen thuộc trong `java.util.function`:

| Functional interface | SAM | Kiểu tham số | Kiểu kết quả |
|---|---|---|---|
| `Runnable` | `void run()` | 0 tham số | `void` |
| `Supplier<T>` | `T get()` | 0 tham số | `T` |
| `Consumer<T>` | `void accept(T value)` | 1 tham số `T` | `void` |
| `Predicate<T>` | `boolean test(T value)` | 1 tham số `T` | `boolean` |
| `Function<T,R>` | `R apply(T value)` | 1 tham số `T` | `R` |
| `BiFunction<T,U,R>` | `R apply(T t,U u)` | 2 tham số | `R` |
| `IntUnaryOperator` | `int applyAsInt(int x)` | 1 `int` | `int` |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | 1 `T` | `int` |

Ví dụ `Function<String,Integer> f = text -> text.length();` có kiểu đích `Function<String,Integer>`. Descriptor là `Integer apply(String)`. Trình biên dịch suy ra `text` có kiểu `String`; phương thức `length()` trả `int`, được **boxing** thành `Integer` để tương thích kiểu kết quả.

Ngược lại, `ToIntFunction<String> f = text -> text.length();` có descriptor `int applyAsInt(String)` và nhận `int` trực tiếp, không cần boxing ở kết quả.

Một interface có nhiều phương thức `default` hoặc `static` vẫn có thể là functional interface nếu hợp đồng trừu tượng tính theo quy tắc ngôn ngữ chỉ còn một SAM. Không nên chọn SAM bằng cách đếm tất cả phương thức xuất hiện trong source.

## 3. Điều kiện thứ nhất: số lượng tham số phải khớp

**Số tham số lambda phải đúng bằng số tham số của descriptor.** Không có cơ chế tự động bỏ bớt hay tạo thêm tham số.

~~~java
Runnable ready = () -> System.out.println("ready");
java.util.function.Function<String, Integer> length =
        text -> text.length();
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (a, b) -> a + b;
~~~

Các ví dụ trên hợp lệ vì lần lượt có **0, 1 và 2** tham số, đúng với SAM.

Các trường hợp sau **cố ý không hợp lệ** (không đặt chúng vào file chạy):

~~~java
// SAI: Runnable.run() không có tham số.
// Runnable wrong = x -> System.out.println(x);

// SAI: Function.apply(T) chỉ có một tham số.
// Function<String,Integer> wrong = (a,b) -> a.length() + b.length();

// SAI: BiFunction.apply(T,U) có hai tham số.
// BiFunction<Integer,Integer,Integer> wrong = x -> x + 1;
~~~

Dấu ngoặc là cú pháp, không làm thay đổi số tham số: `x -> ...` và `(x) -> ...` cùng có đúng một tham số; `() -> ...` có không tham số; `(a,b) -> ...` có hai tham số.

## 4. Điều kiện thứ hai: kiểu tham số phải phù hợp descriptor

### 4.1. Tham số không ghi kiểu: Java suy ra từ kiểu đích

~~~java
java.util.function.Function<String, Integer> size =
        text -> text.length();
java.util.function.BiFunction<String, Integer, String> repeat =
        (text, count) -> text.repeat(count);
~~~

Trong `size`, `text` là `String`. Trong `repeat`, `text` là `String` còn `count` là `Integer`; khi gọi `String.repeat(int)`, `count` được unboxing thành `int`.

Java **không** suy kiểu theo giả định “tên biến là text thì phải là chuỗi”; chính SAM quyết định điều đó. Nếu kiểu đích là `Function<Integer,Integer>`, biểu thức `text -> text.length()` không hợp lệ vì `text` có kiểu `Integer` và không có phương thức `length()`.

### 4.2. Tham số khai báo kiểu tường minh: phải đúng kiểu descriptor

~~~java
java.util.function.Function<String, Integer> good =
        (String text) -> text.length();

java.util.function.IntUnaryOperator twice =
        (int n) -> n * 2;
~~~

Đây là cách viết hợp lệ. Khi khai báo kiểu tham số lambda tường minh, kiểu ấy phải **trùng** kiểu tham số tương ứng của descriptor sau khi xác định kiểu đích; không thể thay bằng một kiểu con, kiểu cha hay wrapper chỉ vì có phép chuyển đổi khi gọi hàm bình thường.

~~~java
// SAI: descriptor yêu cầu Number, không phải Integer.
// Function<Number,String> wrong = (Integer n) -> n.toString();

// SAI: descriptor IntUnaryOperator yêu cầu int, không phải Integer.
// IntUnaryOperator wrong = (Integer n) -> n + 1;
~~~

Nếu cần xử lý một `Number` được truyền vào, hãy dùng `(Number n) -> ...` hoặc `n -> ...` với `Function<Number,...>`. Nếu muốn `Integer` thì khai báo kiểu đích là `Function<Integer,...>` cho đúng. Trong Java, độ linh hoạt kiểu con của object **không cho phép tự ý đổi kiểu tham số được khai báo tường minh trong lambda**.

### 4.3. Tham số `var` vẫn lấy kiểu từ descriptor

Từ Java 11, có thể viết:

~~~java
java.util.function.BiFunction<String, Integer, String> repeat =
        (var text, var times) -> text.repeat(times);
~~~

`text` là `String` và `times` là `Integer` theo SAM; `var` không có nghĩa cả hai cùng một kiểu. Nếu một tham số khai báo bằng `var`, **tất cả** tham số trong cùng danh sách phải dùng `var`; `(var text, times)` và `(var text, Integer times)` không hợp lệ. Với một tham số, phải có ngoặc: `(var text) -> ...`, không được viết `var text -> ...`.

`var` trong lambda cũng không tự tạo ra kiểu đích: `var f = x -> x;` không hợp lệ vì biểu thức lambda chưa được gắn với functional interface cụ thể.

## 5. Điều kiện thứ ba: thân lambda có tương thích kiểu kết quả không?

Cần phân biệt **`void`** và **kiểu kết quả có giá trị**. Java kiểm tra cả dạng thân (*expression body* hay *block body*) và kiểu của các biểu thức trả về.

### 5.1. SAM trả giá trị: biểu thức phải tương thích kiểu trả về

~~~java
java.util.function.Function<String, Integer> length =
        text -> text.length();

java.util.function.Predicate<String> longerThanThree =
        text -> text.length() > 3;

java.util.function.Function<Integer, String> tag =
        number -> "N-" + number;
~~~

- `length` trả `int` rồi boxing thành `Integer` theo yêu cầu của `Function<String,Integer>`.
- `longerThanThree` trả `boolean` theo descriptor của `Predicate<String>`.
- `tag` trả `String` theo `Function<Integer,String>`.

Các ví dụ không hợp lệ:

~~~java
// SAI: Predicate<String>.test phải trả boolean.
// Predicate<String> wrong = text -> text.length();

// SAI: Function<String,String>.apply phải trả String.
// Function<String,String> wrong = text -> System.out.println(text);

// SAI: Function<String,Integer> cần Integer, không nhận String.
// Function<String,Integer> wrong = text -> "length=" + text.length();
~~~

Với `Predicate`, con số khác `0` không được tự hiểu là `true` như ở một số ngôn ngữ khác. Với `Function<String,String>`, `System.out.println` trả `void` nên không thể tạo ra giá trị `String` bắt buộc.

### 5.2. Khối `{ ... }` trả giá trị: các nhánh phải có `return` phù hợp

~~~java
java.util.function.Function<Integer, String> grade = score -> {
    if (score >= 80) {
        return "high";
    }
    return "normal";
};
~~~

Khối lambda có kiểu kết quả `String` phải trả giá trị tương thích khi hoàn tất theo đường thực thi bình thường. Nếu có nhánh đi tới cuối khối mà không trả giá trị hoặc ném ngoại lệ, trình biên dịch từ chối.

~~~java
// SAI: có đường đi không trả String.
// Function<Integer,String> wrong = score -> {
//     if (score >= 80) return "high";
// };
~~~

Khi dùng *block body*, dấu `;` sau `return` thuộc Java statement; dấu `;` sau `}` kết thúc câu lệnh gán lambda. Đừng nhầm việc viết `{ System.out.println(x); }` với việc tạo ra một kết quả trả về.

### 5.3. SAM trả `void`: biểu thức statement hoặc khối tương thích `void`

~~~java
java.util.function.Consumer<String> show =
        text -> System.out.println(text);

java.util.function.Consumer<String> showAgain = text -> {
    System.out.println(text);
    return;
};
~~~

`Consumer<String>` có `void accept(String)`, vì thế hai lambda trên hợp lệ. Trong khối `void`, `return;` được phép, còn `return text.length();` không phù hợp vì cố trả một giá trị.

Ngược lại, với `Function<String,Integer>`, `return;` trống không đáp ứng kiểu kết quả `Integer`.

### 5.4. Phân biệt *statement expression* và giá trị biểu thức

Đây là chi tiết thường gây bất ngờ. Một **expression body** là *statement expression* (chẳng hạn lời gọi phương thức, phép gán, tăng/giảm, khởi tạo đối tượng) có thể tương thích với SAM trả `void` **dù biểu thức đó tự tạo ra một giá trị**. Giá trị được bỏ qua.

~~~java
java.util.List<String> items = new java.util.ArrayList<>();

// List.add trả boolean; Consumer chấp nhận vì đây là method invocation.
java.util.function.Consumer<String> addOnly = text -> items.add(text);

// Predicate nhận chính giá trị boolean của List.add.
java.util.function.Predicate<String> addAndReport = text -> items.add(text);
~~~

Hai ví dụ này là đoạn minh họa, không phải chương trình chạy độc lập. Thân `items.add(text)` là lời gọi phương thức, một statement expression. Với `Consumer`, boolean trả về bị bỏ qua; với `Predicate`, boolean trở thành kết quả. Cả hai có tác dụng phụ là thay đổi danh sách, vì vậy không nên dùng chúng như một ví dụ hàm thuần khiết.

Tuy nhiên, **không phải mọi biểu thức trả giá trị đều tương thích `void`**:

~~~java
// SAI: biểu thức số học thông thường không là statement expression.
// Consumer<Integer> wrong = number -> number + 1;

// SAI: literal số không là statement expression.
// Runnable wrong = () -> 42;
~~~

Muốn thực hiện công việc mà bỏ qua kết quả, dùng lời gọi hoặc khối lệnh hợp lệ. Muốn nhận kết quả, chọn functional interface có SAM trả giá trị tương ứng.

### 5.5. Các thuật ngữ trong JLS: *void-compatible* và *value-compatible*

Với **block lambda**:

- Khối **void-compatible** nếu mọi câu `return` trong khối (nếu có) chỉ có dạng `return;`.
- Khối **value-compatible** nếu nó không thể hoàn tất bình thường (*cannot complete normally*) và mọi câu `return` (nếu có) đều là `return expression;`.

Một khối chỉ chứa `throw new IllegalStateException();` có thể đáp ứng cả hai tiêu chí. Không nên chỉ dựa vào việc nhìn thấy từ khóa `return`; cần xét cả khả năng luồng điều khiển đi hết khối.

Đối với **expression lambda**: nó tương thích mục tiêu trả `void` khi thân là statement expression; tương thích mục tiêu trả giá trị khi thân là biểu thức có kiểu kết quả phù hợp trong ngữ cảnh gán.

## 6. Chương trình hoàn chỉnh: kiểm tra tham số và kết quả

Lưu thành **`LambdaCompatibilityDemo.java`**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;

public class LambdaCompatibilityDemo {
    @FunctionalInterface
    interface Formatter {
        String format(int value);
    }

    static <T, R> R transform(T value, Function<? super T, ? extends R> rule) {
        return rule.apply(value);
    }

    public static void main(String[] args) {
        Formatter formatter = (int value) -> "id-" + value;
        BiFunction<String, Integer, String> repeat =
                (text, count) -> text.repeat(count);
        IntUnaryOperator square = (int n) -> n * n;
        Predicate<String> longText = (String s) -> s.length() >= 4;
        Function<String, Integer> length = text -> text.length();
        Consumer<String> report =
                text -> System.out.println("report:" + text);

        Function<Integer, String> band = score -> {
            if (score >= 80) {
                return "high";
            }
            return "normal";
        };

        System.out.println("formatter=" + formatter.format(7));
        System.out.println("repeat=" + repeat.apply("ha", 2));
        System.out.println("square=" + square.applyAsInt(3));
        System.out.println("longText=" + longText.test("Java"));
        System.out.println("length=" + length.apply("hello"));
        report.accept("ok");
        System.out.println("band=" + band.apply(85));
        System.out.println("generic=" + transform("abc", String::toUpperCase));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac LambdaCompatibilityDemo.java
java LambdaCompatibilityDemo
~~~

Stdout mong đợi:

~~~text
formatter=id-7
repeat=haha
square=9
longText=true
length=5
report:ok
band=high
generic=ABC
~~~

**Đối chiếu từng hợp đồng:**

1. `Formatter.format(int)` nhận một `int` và trả `String`; `(int value) -> "id-" + value` khớp một tham số và một kết quả `String`.
2. `BiFunction<String,Integer,String>` yêu cầu hai tham số kiểu `String`, `Integer`; `repeat` dùng `String.repeat(int)` nên unboxing tham số thứ hai khi gọi.
3. `IntUnaryOperator` nhận/trả `int`; `(int n) -> n * n` có kiểu tham số đúng hoàn toàn.
4. `Predicate<String>` trả `boolean`; điều kiện `s.length() >= 4` đáp ứng.
5. `Function<String,Integer>` cho phép boxing kết quả `s.length()` từ `int` thành `Integer`.
6. `Consumer<String>` trả `void`; lời gọi `println` là statement expression phù hợp.
7. `band` có khối trả `String` ở cả đường đi đạt và không đạt ngưỡng.
8. `transform` là phương thức generic nhận một `Function<? super T,? extends R>`. Với `"abc"` và `String::toUpperCase`, kiểu đầu vào/kết quả đều là `String`. Generic type inference và kiểm tra lambda/method reference cùng tham gia tại vị trí gọi.

Các kết quả trên do code cụ thể quy định; phần hướng dẫn không cần một framework hay thư viện bên ngoài Java SE.

## 7. Chương trình hoàn chỉnh: một method invocation phù hợp hai kiểu kết quả

Ví dụ sau giúp phân biệt “body có trả giá trị” với “SAM yêu cầu trả giá trị”.

Lưu thành **`LambdaBodyDemo.java`**:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaBodyDemo {
    static boolean persist(String value) {
        System.out.println("saved:" + value);
        return value.length() > 1;
    }

    public static void main(String[] args) {
        Consumer<String> action = value -> persist(value);
        Function<String, Boolean> check = value -> persist(value);

        Predicate<Integer> even = number -> {
            if (number == null) {
                return false;
            }
            return number % 2 == 0;
        };

        action.accept("A");
        System.out.println("accepted=" + check.apply("AB"));
        System.out.println("even=" + even.test(4));
    }
}
~~~

Chạy:

~~~bash
javac LambdaBodyDemo.java
java LambdaBodyDemo
~~~

Stdout:

~~~text
saved:A
saved:AB
accepted=true
even=true
~~~

Giải thích:

- `persist` trả `boolean`, nhưng `Consumer<String>` có SAM trả `void`. Lời gọi phương thức `persist(value)` là statement expression, vì vậy kết quả boolean bị **bỏ qua** khi gọi `action.accept("A")`.
- `Function<String,Boolean>` có SAM trả `Boolean`, nên với `check`, kết quả `boolean` của `persist` được boxing và trở thành kết quả của `check.apply("AB")`.
- `Predicate<Integer>` yêu cầu trả `boolean`. Khối `even` có cả hai nhánh trả `boolean`, vì thế tương thích.
- `persist` in ra stdout, là tác dụng phụ. Việc lambda tương thích kiểu đích **không có nghĩa** nó thuần khiết hoặc không làm thay đổi trạng thái quan sát được.

Lưu ý `Consumer<String> action = value -> value.length();` cũng có thể được chấp nhận vì `value.length()` là method invocation (statement expression), dù giá trị `int` bị bỏ qua. Ngược lại `value -> value.length() + 1` không phải statement expression nên không hợp lệ cho `Consumer`.

## 8. Boxing, unboxing, kiểu primitive và `null`

Khi kiểm tra kết quả của lambda, Java cho phép các phép chuyển đổi phù hợp với **ngữ cảnh gán** (*assignment context*), bao gồm boxing/unboxing và một số phép chuyển đổi kiểu số.

~~~java
java.util.function.Function<String, Integer> boxed =
        text -> text.length();                 // int → Integer

java.util.function.ToIntFunction<String> primitive =
        text -> text.length();                 // int → int

java.util.function.Function<String, Long> widenedAndBoxed =
        text -> (long) text.length();          // long → Long
~~~

Điểm quan trọng là **khả năng tương thích kết quả** không có nghĩa các kiểu wrapper có thể thay thế nhau tùy ý. Ví dụ một `int` không tự boxing thành `Long`. Ở ví dụ thứ ba, cast `(long)` bảo đảm biểu thức có kiểu `long`, sau đó boxing thành `Long`.

Với tham số khai báo tường minh, nguyên tắc chặt hơn: `(Integer n) -> ...` **không** thay cho `(int n) -> ...` khi descriptor yêu cầu `int`. Ngược lại, khi gọi `Function<Integer,...>.apply(3)`, lời gọi phương thức có thể boxing literal `3` thành `Integer` theo quy tắc invocation thông thường. Hai giai đoạn này không nên lẫn vào nhau.

**`null` cũng cần được chú ý:**

- `Function<String,String> f = s -> null;` có thể hợp lệ vì `String` là reference type.
- `Function<String,Integer> f = s -> null;` cũng có thể biên dịch; kết quả tham chiếu là `null` và caller phải xử lý.
- `ToIntFunction<String> f = s -> null;` **không hợp lệ**: `null` literal không thể trực tiếp là kết quả primitive `int`.
- Nếu lambda trả về một biến kiểu `Integer` đang bằng `null` và SAM yêu cầu `int`, phép unboxing lúc chạy có thể ném `NullPointerException`. Việc biên dịch thành công chưa bảo đảm an toàn runtime.

## 9. Checked exception là một phần của kiểm tra tương thích

Một lambda không thể tùy ý để checked exception thoát ra nếu SAM của kiểu đích không cho phép.

~~~java
@FunctionalInterface
interface FileLoader {
    String load(String path) throws java.io.IOException;
}

FileLoader loader = path ->
        java.nio.file.Files.readString(java.nio.file.Path.of(path));
~~~

Đây là **đoạn minh họa khai báo**, không có `main`. Nó hợp lệ vì `FileLoader.load` khai báo `throws IOException`.

Nhưng ví dụ sau **cố ý sai**:

~~~java
// Function.apply không khai báo throws IOException.
// java.util.function.Function<String,String> invalid = path ->
//         java.nio.file.Files.readString(java.nio.file.Path.of(path));
~~~

Trình biên dịch yêu cầu xử lý hoặc khai báo ngoại lệ theo hợp đồng của SAM. Việc thêm `try/catch` trong lambda, dùng functional interface riêng cho phép checked exception, hoặc đưa I/O sang lớp xử lý khác là những cách sửa tùy bài toán. Đừng diễn giải lỗi này là “tham số hoặc kiểu kết quả không tương thích”: đó là **điều kiện checked exception bổ sung** trong kiểm tra tính phù hợp lambda.

## 10. Tương thích với ngữ cảnh gọi phương thức và overload

Lambda có thể xuất hiện làm đối số của phương thức, ví dụ `list.sort((a,b) -> a.compareTo(b))` hoặc `stream.map(x -> x.toString())`. Trong các trường hợp này, khai báo tham số của API cung cấp kiểu đích cho lambda.

Nếu một phương thức có **nhiều overload** nhận các functional interface khác nhau, một lambda có thể phù hợp với nhiều ứng viên; trình biên dịch phải áp dụng thêm quy tắc chọn overload. Có khi không chọn được một overload duy nhất.

Ví dụ hai overload đều nhận một SAM không tham số trả `String`:

~~~java
// Minh họa cố ý mơ hồ nếu hai overload cùng tồn tại.
static void execute(java.util.function.Supplier<String> task) {}
static void execute(java.util.concurrent.Callable<String> task) {}

// execute(() -> "ok"); // SAI: không phân biệt được overload.
~~~

`Supplier<String>` và `Callable<String>` đều có SAM 0 tham số trả `String`; khác biệt về khả năng ném checked exception không tự giúp `() -> "ok"` chọn duy nhất một overload trong ví dụ trên.

Cách sửa đơn giản là xác định **kiểu đích rõ ràng**:

~~~java
// Trong cùng lớp chứa các overload ở trên:
execute((java.util.function.Supplier<String>) () -> "ok");
~~~

Hoặc gán lambda cho biến `Supplier<String>` đã khai báo kiểu rồi truyền biến đó. Ép kiểu sang functional interface làm rõ ý định và cho phép trình biên dịch kiểm tra lại tham số/kết quả theo interface được chọn.

**Lưu ý:** Không phải tất cả overload với lambda đều mơ hồ. Số tham số, kiểu kết quả, kiểu tham số, generic bounds và quy tắc *most specific* có thể giúp chọn một overload. Hãy đọc chữ ký API và thông báo biên dịch thay vì đoán từ cách viết lambda.

## 11. Đối chiếu lambda với generic và wildcard

Xét phương thức:

~~~java
static <T, R> java.util.List<R> convert(
        java.util.List<T> items,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return items.stream().map(mapper).toList();
}
~~~

Đây là **đoạn phương thức minh họa**, có thể đặt trong lớp cùng imports `java.util.List` hoặc dùng tên đã ghi đầy đủ ở trên. Khi gọi `convert(List.of("a", "bbb"), String::length)`, Java suy `T` từ nguồn dữ liệu `String` và suy kiểu kết quả `R` phù hợp với `Integer` do boxing kết quả `length()`.

Các wildcard có vai trò:

- `? super T` ở kiểu đầu vào cho phép một mapper nhận `T` hoặc supertype của `T`.
- `? extends R` ở kiểu đầu ra cho phép một mapper tạo giá trị phù hợp với `R`, kể cả subtype của `R`.

Điều này không làm cho một lambda khai báo tường minh `(Object x) -> ...` tự động tương thích với **mọi** kiểu đích: tính phù hợp cuối cùng phụ thuộc descriptor cụ thể sau suy luận và ngữ cảnh sử dụng.

Với lambda có tham số không ghi kiểu, compiler thường dựa vào kiểu đích để suy ra kiểu rồi mới kiểm tra phần thân. Với overload/generic phức tạp, lỗi biên dịch đôi khi phản ánh nhiều ràng buộc cùng lúc: số lượng tham số, bounds, kiểu kết quả và khả năng truy cập.

## 12. Khi nào method reference phù hợp?

Method reference như `String::length`, `Integer::parseInt` hoặc `System.out::println` cũng cần kiểu đích là functional interface. Hợp đồng SAM quyết định cách ánh xạ lời gọi, dù quy tắc suy luận và lựa chọn method reference có các chi tiết riêng.

~~~java
java.util.function.ToIntFunction<String> length = String::length;
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.Consumer<String> print = System.out::println;
~~~

- `String::length` tương thích với `String → int`.
- `Integer::parseInt` nhận `String` và trả `int`, được boxing khi gán cho `Function<String,Integer>`.
- `System.out::println` được chọn overload phù hợp với tham số `String` và kết quả `void`.

Nếu chữ ký method reference không phù hợp descriptor, đổi từ lambda sang method reference không tự sửa lỗi. Lúc cần debug, hãy thử viết lambda tường minh tương đương và kiểm tra cụ thể tham số/kết quả được yêu cầu.

## 13. Bảng lỗi nhanh: đúng ở đâu, sai ở đâu?

| Kiểu đích | Lambda | Kết luận |
|---|---|---|
| `Runnable` | `() -> System.out.println("go")` | Đúng: 0 tham số, statement expression |
| `Runnable` | `x -> System.out.println(x)` | Sai: thừa tham số |
| `Function<String,Integer>` | `s -> s.length()` | Đúng: `String → Integer` qua boxing |
| `Function<String,Integer>` | `s -> "x"` | Sai: kết quả `String` không phù hợp `Integer` |
| `Predicate<String>` | `s -> s.isEmpty()` | Đúng: kết quả `boolean` |
| `Predicate<String>` | `s -> s.length()` | Sai: kết quả `int`, không phải `boolean` |
| `Consumer<String>` | `s -> System.out.println(s)` | Đúng: statement expression trả `void` |
| `Consumer<String>` | `s -> s.length() + 1` | Sai: biểu thức số học không void-compatible |
| `IntUnaryOperator` | `(int n) -> n + 1` | Đúng: `int → int` |
| `IntUnaryOperator` | `(Integer n) -> n + 1` | Sai: kiểu tham số tường minh không trùng `int` |
| `Supplier<String>` | `() -> "ok"` | Đúng: 0 tham số, trả `String` |
| `Supplier<String>` | `() -> { System.out.println("ok"); }` | Sai: không trả `String` |
| `Function<String,String>` | `s -> null` | Đúng về kiểu, nhưng cần chính sách `null` ở runtime |

Khi thấy một lỗi tại `->`, nguyên nhân có thể nằm ở **kiểu đích** được suy ra từ nhiều tầng API. Không nên lập tức sửa mọi lambda: tìm descriptor và đối chiếu có hệ thống thường xác định nguyên nhân nhanh hơn.

## 14. Quy trình tự kiểm tra trước khi biên dịch

Một quy trình ngắn nhưng đáng tin khi review code:

1. **Xác định ngữ cảnh target typing:** gán biến, trả về, gọi API hay cast?
2. **Xác định functional interface:** có SAM hợp lệ không, có generic/wildcard cần suy ra không?
3. **Đếm tham số:** 0, 1, 2 hay nhiều hơn? Có đúng số tham số SAM không?
4. **Kiểm tra kiểu từng tham số:** implicit/`var` thì suy từ SAM; explicit thì phải đúng kiểu descriptor.
5. **Kiểm tra kiểu trả về:** SAM trả `void` hay một giá trị? Expression body có phù hợp không?
6. **Nếu dùng block:** có nhánh thiếu `return` hay trả sai kiểu không? Có trộn `return;` với `return expression;` trái quy tắc không?
7. **Xét chuyển đổi kiểu hợp lệ:** widening, boxing/unboxing và `null` có thực sự tương thích không?
8. **Xét checked exception:** lambda có ném checked exception vượt khỏi hợp đồng SAM không?
9. **Nếu overload/generic:** compiler có nhiều target type cạnh tranh nhau không? Có cần khai báo biến hoặc cast làm rõ không?
10. **Chạy compiler và test:** thông báo compiler là bằng chứng cuối cùng; sau khi biên dịch, kiểm thử thêm giá trị biên, `null`, ngoại lệ và side effects.

Việc kiểm tra phù hợp với SAM là **kiểm tra kiểu và cấu trúc thân lambda tại compile time**. Nó không chứng minh nghiệp vụ đúng, không tự kiểm tra overflow, thread safety, hiệu ứng ngoài hay trường hợp `null` dẫn tới exception ở runtime.

## 15. Câu hỏi tự kiểm tra

1. `Function<String,Integer> f = s -> s.length();` hợp lệ nhờ phép chuyển đổi nào?
2. Vì sao `IntUnaryOperator op = (Integer n) -> n + 1;` sai, dù `Integer` có thể unboxing thành `int`?
3. `Consumer<String> c = s -> list.add(s);` có thể hợp lệ không khi `List.add` trả `boolean`? Giải thích theo *statement expression*.
4. `Consumer<Integer> c = n -> n + 1;` có hợp lệ không?
5. Một khối lambda trả `String` có nhánh `if` trả `String` nhưng nhánh còn lại rơi tới cuối khối. Trình biên dịch xử lý thế nào?
6. Vì sao `var f = s -> s.length();` không tự xác định kiểu của lambda?
7. Nếu `Supplier<String>` và `Callable<String>` đều là overload, `() -> "ok"` có chắc chọn được đúng một overload không?
8. Khi method reference `Integer::parseInt` được gán cho `Function<String,Integer>`, kiểu tham số/kết quả là gì?

**Đáp án:** (1) boxing `int → Integer`. (2) Vì kiểu khai báo tường minh trong lambda phải trùng descriptor `int`, quy tắc này khác chuyển đổi đối số khi gọi. (3) Có, `add` là method invocation/statement expression và giá trị boolean bị bỏ qua. (4) Không, `n + 1` không phải statement expression để dùng với SAM trả `void`. (5) Không hợp lệ nếu còn đường hoàn tất bình thường mà không trả kết quả cần thiết. (6) Lambda cần functional interface kiểu đích. (7) Không, hai overload có thể gây mơ hồ; cung cấp biến có kiểu hoặc cast. (8) `String → int` rồi boxing kết quả thành `Integer`.

## 16. Nguồn đặc tả chính thức

- [Java Language Specification SE 17, `15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): cú pháp, body và các quy tắc kiểm tra lambda theo ngữ cảnh kiểu đích.
- [JLS SE 17, `15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): congruence về số/kiểu tham số, void/value-compatible bodies, kiểu kết quả và các chuyển đổi.
- [JLS SE 17, `9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): xác định kiểu giao diện chức năng và descriptor.

**Ghi nhớ:** Khi xem một lambda, đừng suy đoán kiểu dựa vào `->` hoặc tên biến. Hãy bắt đầu từ **functional interface và SAM**; sau đó so sánh **số tham số → kiểu tham số → dạng thân → kiểu kết quả → checked exception**. Lambda hợp lệ khi nó khớp hợp đồng của **kiểu đích cụ thể** trong ngữ cảnh Java đang biên dịch.