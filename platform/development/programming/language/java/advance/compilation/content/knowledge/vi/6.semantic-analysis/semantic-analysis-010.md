# Kiểu đích của lambda, method reference và biểu thức điều kiện

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu **target typing** (kiểu đích) và **poly expression** (biểu thức phụ thuộc ngữ cảnh) trong bước kiểm tra ngữ nghĩa của trình biên dịch Java.
- Giải thích cách `javac` tìm **functional interface** phù hợp để kiểm tra lambda expression và method reference; phân biệt cú pháp, kiểu đích, chữ ký của **SAM** và kiểu của biểu thức.
- Phân tích các ngữ cảnh như gán biến, truyền đối số, trả về từ phương thức, ép kiểu và suy luận generic.
- Giải thích vì sao biểu thức điều kiện `condition ? a : b` đôi khi truyền kiểu đích cho hai nhánh và đôi khi tự xác định kiểu riêng, đặc biệt khi nhánh chứa lambda hoặc method reference.
- Nhận diện và xử lý lỗi biên dịch do overload không xác định được lời gọi, không có functional-interface target, kiểu tham số hoặc kiểu trả về không tương thích.
- Tự biên dịch và kiểm tra những chương trình Java 17+ minh họa bằng `javac` và `java`.

Trong Java, **không phải mọi biểu thức đều có kiểu hoàn toàn xác định từ chính phần chữ được viết**. Một số biểu thức cần thông tin ở *vị trí sử dụng*. Đó là trọng tâm của bài học này.

## 1. Target typing: ngữ cảnh quyết định kiểu cần có

Xét hai dòng sau:

~~~java
IntUnaryOperator twice = value -> value * 2;
Predicate<Integer> positive = value -> value > 0;
~~~

Hai lambda đều dùng tham số tên `value`, nhưng trình biên dịch hiểu nó theo những **kiểu đích khác nhau**:

| Biểu thức | Kiểu đích | Phương thức trừu tượng duy nhất (SAM) | Kiểu tham số suy ra | Kiểu kết quả |
| --- | --- | --- | --- | --- |
| `value -> value * 2` | `IntUnaryOperator` | `int applyAsInt(int operand)` | `int` | `int` |
| `value -> value > 0` | `Predicate<Integer>` | `boolean test(Integer t)` | `Integer` | `boolean` |

Trong ví dụ này, `IntUnaryOperator` thuộc `java.util.function` và dùng primitive `int`. `Predicate<Integer>` có tham số kiểu tham chiếu `Integer`; ở biểu thức so sánh, Java có thể unbox thành `int`.

### Poly expression và standalone expression

- **Poly expression**: kiểu hoặc tính hợp lệ của biểu thức phụ thuộc kiểu đích do ngữ cảnh cung cấp. Lambda và method reference là các trường hợp điển hình: chúng cần một functional-interface target.
- **Standalone expression**: kiểu được xác định từ chính biểu thức theo quy tắc ngôn ngữ, rồi mới xem nó có chuyển được sang kiểu cần ở ngoài hay không. Ví dụ literal `42` có kiểu `int`. Nhiều biểu thức điều kiện thuộc nhóm này.

Sự khác biệt này xuất hiện ngay trong lỗi compiler:

~~~java
// Các dòng dưới đây chỉ để minh họa lỗi, không thuộc một chương trình chạy.
var operation = x -> x + 1;    // Lỗi: lambda không có kiểu đích.
Object anything = x -> x + 1; // Lỗi: Object không phải functional interface.
~~~

`var` yêu cầu compiler suy ra kiểu biến local từ initializer, nhưng lambda **không tự mang một kiểu functional interface cụ thể** để compiler suy ra. Tương tự, một lambda không thể được gán trực tiếp vào `Object` vì kiểu đích này không có SAM. Cách hợp lệ là xác định functional interface:

~~~java
IntUnaryOperator operation = x -> x + 1;
Object anything = (IntUnaryOperator) (x -> x + 1);
var inferred = (IntUnaryOperator) (x -> x + 1);
~~~

Ở dòng thứ hai và thứ ba, cast sang `IntUnaryOperator` cung cấp target type; kết quả biểu thức đã ép kiểu có thể tiếp tục được gán cho `Object` hoặc dùng làm initializer để `var` suy ra `IntUnaryOperator`.

### Ngữ cảnh thường cung cấp kiểu đích

| Ngữ cảnh | Ví dụ | Kiểu đích lấy từ đâu? |
| --- | --- | --- |
| Gán/khởi tạo biến | `Runnable r = () -> run();` | Kiểu biến `Runnable` |
| Truyền đối số | `execute(() -> run());` | Kiểu formal parameter của `execute` sau khi xét overload |
| `return` | `return x -> x + 1;` | Kiểu trả về của phương thức chứa nó |
| Ép kiểu | `(Runnable) () -> run()` | Kiểu trong cast |
| Khởi tạo mảng | `new Runnable[] { () -> run() }` | Kiểu phần tử `Runnable` |
| Nhánh của reference conditional poly | `Runnable r = flag ? () -> run() : () -> stop();` | Kiểu đích truyền vào các nhánh |

Các dòng có `run()`/`stop()` ở bảng chỉ **minh họa cú pháp trong một lớp có các phương thức tương ứng**, không phải file Java độc lập.

Không nên suy luận rằng bất kỳ dấu bằng hay lời gọi nào cũng cung cấp một functional interface duy nhất: nếu có overload, generic chưa được suy ra hoặc kiểu đích không phải functional interface, compiler phải giải quyết thêm các ràng buộc trước khi chấp nhận lambda.

## 2. Functional interface và SAM là nền tảng của target typing

Lambda và method reference được gán vào một **functional interface**, tức interface có đúng một *abstract method* được tính theo quy tắc của Java. Các phương thức `default`, `static` và một số phương thức tương đương phương thức public của `Object` không làm tăng số lượng abstract methods cần thực hiện.

Ví dụ một interface tự định nghĩa:

~~~java
@FunctionalInterface
interface IntTransformer {
    int transform(int input);
}
~~~

`@FunctionalInterface` yêu cầu compiler kiểm tra điều kiện functional interface. Annotation này giúp phát hiện thay đổi làm mất tính “functional”; một interface thỏa quy tắc vẫn có thể là functional interface kể cả không có annotation.

Gán lambda:

~~~java
IntTransformer triple = input -> input * 3;
~~~

Compiler dùng SAM `int transform(int input)` để suy ra:

1. Lambda phải có **một tham số** phù hợp.
2. Tham số suy ra có kiểu `int`.
3. Body `input * 3` tạo kết quả `int`, phù hợp kiểu trả về SAM.
4. Khi chạy, `triple.transform(4)` nhận kết quả `12`.

Đây là kiểm tra **tương thích khi biên dịch**. Lambda không phải lớp `IntTransformer` được định nghĩa bằng source ngay tại vị trí đó, và bạn không cần viết một anonymous class thủ công.

### 2.1 Lambda không đồng nghĩa tên hay hình dạng một method bất kỳ

Một lambda có thể tương thích với **nhiều functional interface** có SAM phù hợp. Ví dụ:

~~~java
Runnable a = () -> System.out.println("x");
java.util.concurrent.Callable<String> b = () -> "x";
java.util.function.Supplier<String> c = () -> "x";
~~~

Các lambda ở trên được kiểm tra theo target riêng. Nhưng điều này không cho phép dùng một biểu thức lambda đã viết **không có kiểu đích** rồi xem nó mặc nhiên thuộc một interface “tự nhiên”.

Một số functional interface quen thuộc trong `java.util.function`:

| Interface | SAM | Tình huống |
| --- | --- | --- |
| `Runnable` (ở `java.lang`) | `void run()` | Không tham số, không trả giá trị |
| `Supplier<T>` | `T get()` | Không tham số, có trả giá trị |
| `Consumer<T>` | `void accept(T value)` | Nhận một giá trị, không trả giá trị |
| `Function<T,R>` | `R apply(T value)` | Chuyển một giá trị sang một giá trị khác |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra một điều kiện |
| `IntUnaryOperator` | `int applyAsInt(int value)` | Chuyển đổi primitive `int` |
| `Comparator<T>` | `int compare(T a, T b)` | So sánh hai giá trị |

**Kiểu trả về của SAM cũng quan trọng.** `Runnable r = () -> 42;` là lỗi: literal `42` không phải *statement expression* thích hợp cho lambda trả `void`. Ngược lại, `Supplier<Integer> s = () -> 42;` hợp lệ vì SAM yêu cầu giá trị `Integer` (có thể box từ `int`).

### 2.2 Kiểu lambda phụ thuộc vào SAM, không phải tên tham số

Hai lambda sau có cùng hiệu ứng dưới `IntUnaryOperator`:

~~~java
IntUnaryOperator first = n -> n + 1;
IntUnaryOperator second = number -> number + 1;
~~~

Đổi tên `n` thành `number` không làm đổi kiểu tham số hoặc giá trị trả về. Tên tham số lambda chỉ phục vụ scope trong source; compiler kiểm tra hình dạng, kiểu và body theo functional target.

## 3. Ví dụ tổng hợp: cùng biểu thức, nhiều kiểu đích

Tạo file **`TargetTypingDemo.java`** với JDK 17+:

~~~java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class TargetTypingDemo {
    public static void main(String[] args) {
        IntUnaryOperator twice = n -> n * 2;
        Predicate<String> longName = s -> s.length() > 3;
        Function<String, Integer> size = String::length;
        Supplier<String> message = () -> "Xin chao Java";

        System.out.println("twice(4) = " + twice.applyAsInt(4));
        System.out.println("longName(Java) = " + longName.test("Java"));
        System.out.println("size(code) = " + size.apply("code"));
        System.out.println(message.get());
    }
}
~~~

Biên dịch và chạy tại thư mục có file:

~~~bash
javac -encoding UTF-8 -d out TargetTypingDemo.java
java -cp out TargetTypingDemo
~~~

Stdout chính xác:

~~~text
twice(4) = 8
longName(Java) = true
size(code) = 4
Xin chao Java
~~~

Giải thích cách compiler đi từ ngữ cảnh vào expression:

- Với `twice`, kiểu đích cung cấp chữ ký `int -> int`. `n` được hiểu là `int`; `n * 2` hợp lệ và trả `int`.
- Với `longName`, kiểu đích `Predicate<String>` yêu cầu `String -> boolean`; vì vậy `s.length() > 3` là biểu thức boolean hợp lệ.
- Với `size`, target `Function<String,Integer>` cần một phép chuyển `String -> Integer`. Method reference `String::length` dùng `String` làm receiver và trả `int`, được box thành `Integer`.
- Với `message`, SAM `Supplier<String>.get()` không có đối số và trả `String`.

**Lỗi thường gặp:** nếu thay `Function<String,Integer> size` thành `Function<Integer,String> size` nhưng vẫn giữ `String::length`, compiler không thể ghép tham số kiểu `Integer` của target với receiver `String` mà method reference yêu cầu. Tên method có tồn tại không đủ; cả **receiver, số tham số, kiểu tham số và kiểu trả về** phải tương thích.

## 4. Lambda: compiler kiểm tra tham số và body như thế nào?

### 4.1 Tham số suy ra so với tham số khai báo tường minh

Khi target đã rõ:

~~~java
IntUnaryOperator implicit = x -> x + 1;
IntUnaryOperator explicit = (int x) -> x + 1;
~~~

Cả hai hợp lệ. Với `implicit`, `x` có kiểu `int` nhờ target. Với `explicit`, compiler kiểm tra kiểu `int` khai báo có khớp SAM không.

Một ví dụ sai về kiểu:

~~~java
// Chỉ minh họa lỗi biên dịch:
IntUnaryOperator wrong = (String x) -> x.length();
~~~

`IntUnaryOperator` cần tham số `int`, nhưng lambda khai báo `String` nên không tương thích. Chỉ sửa body hoặc đổi tên biến sẽ không giải quyết mâu thuẫn này.

### 4.2 `var` trong danh sách tham số lambda khác `var` ở initializer

Từ Java 11, có thể dùng `var` để khai báo tham số lambda khi target đã biết:

~~~java
java.util.function.BinaryOperator<Integer> add = (var a, var b) -> a + b;
~~~

Ở đây compiler vẫn cần target `BinaryOperator<Integer>` để xác định kiểu hai tham số. Việc dùng `var` trong danh sách tham số **không khiến một lambda độc lập tự suy ra functional interface**.

Trong cùng một danh sách tham số lambda, không được trộn kiểu khai báo tường minh với kiểu suy ra hoặc `var` tùy tiện, ví dụ `(var a, Integer b) -> a + b` không hợp lệ.

### 4.3 Tương thích body với SAM trả `void` hoặc giá trị

Các ví dụ:

~~~java
Runnable print = () -> System.out.println("Hello");
Supplier<Integer> answer = () -> 42;
java.util.function.Consumer<String> consume = s -> System.out.println(s);
java.util.function.Function<String, Integer> measure = s -> s.length();
~~~

- Lambda nhắm tới SAM trả `void` phải có body **void-compatible**.
- Lambda nhắm tới SAM có kết quả phải có body **value-compatible**, có kết quả có thể chuyển đổi sang return type yêu cầu.
- Với block lambda, mọi `return` hợp lệ cần tuân theo kiểu trả về: ví dụ `return 42;` cho SAM trả giá trị và `return;` cho SAM trả void. Compiler cũng kiểm tra các đường đi của control flow.

Đây là hai block lambda hợp lệ, là đoạn code minh họa trong lớp/method:

~~~java
Runnable task = () -> {
    System.out.println("begin");
    System.out.println("end");
};

Supplier<Integer> makeNumber = () -> {
    int a = 20;
    int b = 22;
    return a + b;
};
~~~

Một expression lambda như `s -> s.length()` sử dụng lời gọi method, vốn là *statement expression*; nên tùy target và ngữ cảnh overload, body có thể được xem là void-compatible (bỏ kết quả) hoặc value-compatible (lấy kết quả). Chính đặc điểm này tạo ra những lời gọi overloaded dễ mơ hồ.

### 4.4 Checked exception vẫn phải tương thích với SAM

Một lambda có thể ném checked exception chỉ khi chữ ký SAM/điều kiện kiểm tra ngoại lệ cho phép.

Ví dụ minh họa trong một method có thể ném exception:

~~~java
java.util.concurrent.Callable<String> read = () -> {
    throw new java.io.IOException("No data");
};
~~~

`Callable.call()` khai báo `throws Exception`, nên lambda có thể ném `IOException`. Trong khi đó:

~~~java
// Lỗi: Supplier.get() không khai báo checked IOException.
java.util.function.Supplier<String> read = () -> {
    throw new java.io.IOException("No data");
};
~~~

Cờ compiler hoặc việc dùng method reference không tự làm checked exception biến mất. Bạn cần xử lý exception, dùng interface phù hợp hoặc cung cấp adapter có quy tắc rõ ràng.

## 5. Target type xuất hiện ở những ngữ cảnh nào?

### 5.1 Assignment context

~~~java
Predicate<String> nonEmpty = text -> !text.isEmpty();
~~~

Target có ngay bên trái dấu `=`. Nếu đổi sang `Predicate<Integer>`, body `text.isEmpty()` sẽ không hợp lệ vì `Integer` không có method `isEmpty()`.

### 5.2 Invocation context

Khi lời gọi có một overload phù hợp, formal parameter của method cung cấp target:

~~~java
import java.util.function.IntUnaryOperator;

public class InvocationTargetDemo {
    static int evaluate(IntUnaryOperator transform) {
        return transform.applyAsInt(5);
    }

    public static void main(String[] args) {
        System.out.println(evaluate(x -> x * 3));
    }
}
~~~

Chạy:

~~~bash
javac -d out InvocationTargetDemo.java
java -cp out InvocationTargetDemo
~~~

Stdout:

~~~text
15
~~~

Compiler biết `evaluate` nhận `IntUnaryOperator`, nên `x` là `int`. Nếu có nhiều overload, compiler cần xét tính tương thích của biểu thức với từng candidate và quy tắc chọn method cụ thể; đôi khi không có một target duy nhất.

### 5.3 Return context

Trong một method trả về functional interface, expression được dùng ở `return` nhận target từ return type:

~~~java
import java.util.function.IntUnaryOperator;

public class ReturnTargetDemo {
    static IntUnaryOperator transform(boolean negate) {
        return negate ? x -> -x : x -> x + 1;
    }

    public static void main(String[] args) {
        System.out.println(transform(true).applyAsInt(5));
        System.out.println(transform(false).applyAsInt(5));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -d out ReturnTargetDemo.java
java -cp out ReturnTargetDemo
~~~

Stdout:

~~~text
-5
6
~~~

Return type của `transform` là `IntUnaryOperator`, nên hai lambda trong biểu thức điều kiện được kiểm tra theo target này. Nếu đổi return type thành `Object` mà vẫn trả trực tiếp các lambda, compiler không tự chọn functional interface từ chúng.

### 5.4 Cast context

~~~java
var operation = (IntUnaryOperator) (x -> x * 2);
System.out.println(operation.applyAsInt(5));
~~~

Đây là đoạn minh họa cần đặt trong method và import `IntUnaryOperator`. Cast cung cấp target và kết quả có kiểu `IntUnaryOperator`, do đó `var` có thể suy ra kiểu biến. Với một lambda được cast đến functional interface khác, các tham số/body sẽ được kiểm tra lại theo SAM của target mới.

### 5.5 Array initializer context

~~~java
Runnable[] tasks = {
        () -> System.out.println("one"),
        () -> System.out.println("two")
};
~~~

Mỗi phần tử cần tương thích `Runnable`. Không có quy tắc chung “mọi literal hoặc collection tự suy ra interface” — trong mảng trên chính thành phần `Runnable[]` cung cấp target.

### 5.6 Generic invocation và target inference

Xem ví dụ độc lập **`GenericTargetDemo.java`**:

~~~java
import java.util.function.Function;

public class GenericTargetDemo {
    static <T, R> R mapOne(T source, Function<T, R> mapper) {
        return mapper.apply(source);
    }

    public static void main(String[] args) {
        String result = mapOne(21, n -> "value=" + n);
        System.out.println(result);
    }
}
~~~

~~~bash
javac -d out GenericTargetDemo.java
java -cp out GenericTargetDemo
~~~

Stdout:

~~~text
value=21
~~~

Compiler dùng cả giá trị `21`, kiểu `Function<T,R>` của đối số thứ hai, body lambda và ngữ cảnh gán `String` để giải các ràng buộc suy luận kiểu. Đây là quá trình **kiểm tra ngữ nghĩa kết hợp**; không nên mô tả đơn giản là “compiler tự đoán kiểu từ tên `n`”.

Các lời gọi API như `stream().map(String::length)` hoạt động theo cùng nguyên tắc: generic method cung cấp formal functional interface, rồi compiler kiểm tra method reference dựa trên kiểu phần tử stream và kiểu kết quả cần suy ra.

## 6. Method reference cũng cần kiểu đích

Method reference có cú pháp `::`. Nó không phải lời gọi thực thi ngay tại vị trí viết; nó diễn tả một phép thực hiện có thể được gán cho functional interface. Compiler cần target SAM để xác định cách ghép receiver, tham số và return type của method được tham chiếu.

Có bốn dạng thường gặp:

| Dạng | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Tham chiếu static method | `Integer::parseInt` | Target cung cấp tham số cần truyền cho static method |
| Tham chiếu instance method với receiver đã có (*bound*) | `word::toUpperCase` | Receiver `word` đã được xác định; target nhận các tham số còn lại |
| Tham chiếu instance method qua kiểu (*unbound*) | `String::length` hoặc `String::concat` | Tham số đầu ở SAM có thể đóng vai receiver |
| Tham chiếu constructor | `StringBuilder::new`, `String[]::new` | Target cung cấp số/kiểu tham số cần cho constructor hoặc tạo mảng |

### 6.1 Chương trình minh họa bốn dạng

Tạo file **`MethodReferenceTargetDemo.java`**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

public class MethodReferenceTargetDemo {
    static String greet(String name) {
        return "Hello " + name;
    }

    public static void main(String[] args) {
        Function<String, String> staticMethod =
                MethodReferenceTargetDemo::greet;

        String word = "java";
        Supplier<String> bound = word::toUpperCase;

        ToIntFunction<String> unbound = String::length;
        BiFunction<String, String, String> concat = String::concat;

        Supplier<StringBuilder> constructor = StringBuilder::new;
        IntFunction<String[]> arrayConstructor = String[]::new;

        System.out.println(staticMethod.apply("An"));
        System.out.println(bound.get());
        System.out.println(unbound.applyAsInt("code"));
        System.out.println(concat.apply("Ja", "va"));
        System.out.println(constructor.get().append("ok"));
        System.out.println(arrayConstructor.apply(3).length);
    }
}
~~~

~~~bash
javac -d out MethodReferenceTargetDemo.java
java -cp out MethodReferenceTargetDemo
~~~

Stdout chính xác:

~~~text
Hello An
JAVA
4
Java
ok
3
~~~

Phân tích:

- `MethodReferenceTargetDemo::greet` trỏ đến static method nhận `String` và trả `String`; khớp `Function<String,String>`.
- `word::toUpperCase` là **bound reference**, đã biết receiver `word`; khớp `Supplier<String>` vì `toUpperCase()` không cần thêm đối số và trả `String`.
- `String::length` với `ToIntFunction<String>` dùng **chuỗi đầu vào làm receiver**, nên khớp `String -> int`.
- `String::concat` với `BiFunction<String,String,String>` dùng `String` thứ nhất làm receiver và `String` thứ hai làm tham số của `concat`.
- `StringBuilder::new` khớp no-arg constructor theo `Supplier<StringBuilder>`.
- `String[]::new` dùng độ dài `int` để tạo array; khớp `IntFunction<String[]>`.

Điểm dễ nhầm là sự khác nhau giữa:

~~~java
String word = "java";
Supplier<String> bound = word::toUpperCase;
Function<String, String> unbound = String::toUpperCase;
~~~

`bound.get()` không nhận đối số vì receiver đã gắn vào biểu thức `word::...`. `unbound.apply("hello")` cần một đối số chuỗi làm receiver. Cùng tên method nhưng target SAM khác nhau là đúng.

### 6.2 Overloaded method reference được giải theo target

Ví dụ `Integer::parseInt` có nhiều overload trong Java API. Khi gán:

~~~java
java.util.function.ToIntFunction<String> parser = Integer::parseInt;
~~~

target yêu cầu một `String`, trả `int`. Compiler tìm overload `parseInt` tương thích về arity, kiểu tham số và kiểu kết quả. Bạn không cần ghi overload bằng cú pháp riêng trong method reference.

Ngược lại, nếu target yêu cầu kiểu tham số hoặc kiểu trả về không thể thích ứng, compiler báo không tìm được method phù hợp dù `Integer.parseInt` chắc chắn tồn tại. **“Có method cùng tên” chưa đủ**.

Method reference có thể được phân loại là *exact* hoặc *inexact* đối với một số bước giải overload; tham chiếu tới method quá tải có thể cần target để chọn. Do đó, khi một lời gọi bên ngoài cũng bị overload, hai tầng lựa chọn có thể tương tác và dẫn tới lỗi mơ hồ.

### 6.3 Method reference và lambda có thể diễn đạt thao tác tương đương

Hai biểu thức:

~~~java
ToIntFunction<String> lengthByLambda = s -> s.length();
ToIntFunction<String> lengthByReference = String::length;
~~~

đều có thể trả độ dài chuỗi. Nhưng không phải mọi lambda có thể thay bằng method reference mà không xét lại target, overload, receiver, exception và kiểu generic. Không nên xem việc thay cú pháp là phép biến đổi chắc chắn đúng ở mọi hoàn cảnh.

### 6.4 Generic API sử dụng target typing cho method reference

Ví dụ độc lập **`StreamReferenceDemo.java`**:

~~~java
import java.util.List;

public class StreamReferenceDemo {
    public static void main(String[] args) {
        List<Integer> lengths =
                List.of("A", "Java", "lambda")
                        .stream()
                        .map(String::length)
                        .toList();
        System.out.println(lengths);
    }
}
~~~

~~~bash
javac -d out StreamReferenceDemo.java
java -cp out StreamReferenceDemo
~~~

Stdout:

~~~text
[1, 4, 6]
~~~

`Stream.map` nhận một `Function<? super T, ? extends R>`. Khi stream chứa `String`, reference `String::length` được kiểm tra như phép đổi từ `String` sang giá trị có kiểu tương thích với `R`. Kiểu `int` được box thành `Integer`; ngữ cảnh và generic inference dẫn tới kết quả danh sách `Integer`. `Stream.toList()` có từ Java 16, nên ví dụ này hợp lệ với Java 17+.

## 7. Overload resolution: vì sao target đôi khi mơ hồ?

Khi nhiều phương thức có cùng tên nhưng formal parameters khác nhau, `javac` phải quyết định overload nào được gọi. Lambda/method reference lúc đó có thể cần target từ overload — đồng thời compiler cần xét biểu thức để chọn overload. Java có các quy tắc riêng để kiểm tra **potential compatibility**, **applicability** và **most specific method**; không phải cứ nhìn return type của lambda rồi chọn tùy ý.

### 7.1 Lambda tương thích hai functional interfaces

Ví dụ sau **cố ý không biên dịch**:

~~~java
import java.util.function.Supplier;
import java.util.concurrent.Callable;

class AmbiguousCall {
    static void use(Supplier<String> source) {}
    static void use(Callable<String> source) {}

    static void example() {
        use(() -> "done"); // Lỗi: không xác định được overload duy nhất.
    }
}
~~~

`Supplier<String>.get()` và `Callable<String>.call()` đều có dạng không tham số, trả `String`. Lambda `() -> "done"` có thể phù hợp cả hai; không có lý do đủ để compiler tự chọn một cái.

Giải quyết bằng **cast tới interface có chủ đích** hoặc biến có kiểu rõ:

~~~java
use((Supplier<String>) () -> "done");

// Trong một method có kiểu ở import:
Supplier<String> supplier = () -> "done";
use(supplier);
~~~

Hai đoạn sửa trên minh họa lời gọi hợp lệ bên trong lớp `AmbiguousCall`, nhưng muốn chạy phải thêm `main` hoặc dùng trong chương trình khác. Cast không “chọn kiểu của lambda sau khi lambda đã có kiểu”; nó cung cấp kiểu đích ngay khi compiler kiểm tra lambda.

### 7.2 Hai overload có SAM cùng tham số nhưng khác return type

Một trường hợp khác:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

class BodyCompatibilityExample {
    static void choose(Consumer<String> consumer) {}
    static void choose(Function<String, Integer> function) {}

    static void example() {
        // Có thể mơ hồ: s.length() là method invocation,
        // có thể được dùng như statement expression
        // hoặc như value expression.
        choose(s -> s.length());
    }
}
~~~

Đây là **đoạn minh họa lỗi**, không phải file dự định chạy. Lambda dạng expression với body là lời gọi method `s.length()` có thể thỏa yêu cầu `void` bằng cách bỏ kết quả hoặc thỏa yêu cầu nhận giá trị `Integer` sau boxing. Với hai overload cùng được xét, lời gọi như vậy có thể không chọn được duy nhất một method.

Để diễn đạt ý định, viết:

~~~java
choose((Function<String, Integer>) String::length);

choose((Consumer<String>) s -> {
    System.out.println(s);
});
~~~

Hoặc gán lambda/method reference vào biến có kiểu rõ trước khi truyền vào method overloaded. Việc thêm cast đúng chỗ thường ít mơ hồ hơn chỉnh sửa body một cách tình cờ.

### 7.3 Target typing khác với chọn overload theo kiểu trả về bên ngoài

Java không có quy tắc chung “nhìn kiểu biến nhận kết quả rồi luôn chọn overload theo return type”. Chọn overload chủ yếu dựa trên tên, tập tham số, khả năng áp dụng và các quy tắc most-specific. Khi generic inference hoặc poly arguments tham gia, ngữ cảnh có thể đóng góp ràng buộc; nhưng bạn không được giả định chỉ vì muốn kết quả `String` thì compiler chọn method overload trả `String`.

Một cách xử lý dễ kiểm soát: đưa ra một interface target tường minh cho lambda/method reference hoặc thay đổi API để overload không có những SAM tương đương khó phân biệt.

## 8. Biểu thức điều kiện `?:` và kiểu đích

Cú pháp:

~~~java
condition ? whenTrue : whenFalse
~~~

Java phân loại các biểu thức điều kiện thành các nhóm khác nhau theo quy tắc ngôn ngữ. Điểm then chốt ở đây: **reference conditional expression** có thể là **poly expression** khi xuất hiện trong *assignment context* hoặc *invocation context*. Khi đó, kiểu đích từ bên ngoài được truyền vào hai nhánh.

Không phải mọi `?:` đều là poly expression. Các biểu thức điều kiện **boolean** hoặc **numeric** được phân loại và xác định kiểu theo quy tắc riêng, thường là standalone expressions; không thể suy ra rằng hễ có `?:` thì kiểu đích sẽ điều khiển mọi nhánh theo cách giống lambda.

### 8.1 Hai lambda trong một reference conditional

File **`ConditionalTargetDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class ConditionalTargetDemo {
    static int evaluate(IntUnaryOperator operation, int value) {
        return operation.applyAsInt(value);
    }

    public static void main(String[] args) {
        boolean increase = args.length > 0;

        IntUnaryOperator direct =
                increase ? x -> x + 1 : x -> x * 2;

        System.out.println("direct = " + direct.applyAsInt(4));

        int viaArgument = evaluate(
                increase ? x -> x + 1 : x -> x * 2,
                4
        );
        System.out.println("argument = " + viaArgument);
    }
}
~~~

Biên dịch/chạy **không có đối số**:

~~~bash
javac -d out ConditionalTargetDemo.java
java -cp out ConditionalTargetDemo
~~~

Stdout:

~~~text
direct = 8
argument = 8
~~~

Chạy **có một đối số bất kỳ**:

~~~bash
java -cp out ConditionalTargetDemo yes
~~~

Stdout:

~~~text
direct = 5
argument = 5
~~~

Giải thích:

- Trong initializer `IntUnaryOperator direct = ...`, kiểu đích là `IntUnaryOperator`. Hai nhánh lambda đều được kiểm tra với SAM `int -> int`.
- Ở lời gọi `evaluate(...)`, tham số thứ nhất có kiểu `IntUnaryOperator`. Kiểu này được dùng để kiểm tra biểu thức điều kiện poly và các nhánh.
- Cả hai nhánh hợp lệ, nhưng chỉ **nhánh được chọn tại runtime** mới được đánh giá theo ngữ nghĩa `?:`.
- Compiler kiểm tra kiểu của **cả hai nhánh khi biên dịch**; điều kiện runtime không làm một nhánh sai kiểu trở nên hợp lệ.

### 8.2 Khi không có target, compiler không thể suy ra functional interface

Đoạn sau **cố ý sai**:

~~~java
// Đoạn minh họa lỗi compile-time:
boolean increase = true;
var operation = increase ? x -> x + 1 : x -> x * 2;
~~~

`var` không cung cấp một functional interface cụ thể cho hai lambda. Một lambda không có standalone type để compiler tạo một kiểu đích chung từ hư không.

Có thể sửa bằng kiểu bên trái:

~~~java
IntUnaryOperator operation =
        increase ? x -> x + 1 : x -> x * 2;
~~~

Hoặc cung cấp target qua cast trước khi dùng `var`:

~~~java
var operation = increase
        ? (IntUnaryOperator) (x -> x + 1)
        : (IntUnaryOperator) (x -> x * 2);
~~~

Hai nhánh sau cast là những biểu thức có kiểu đã xác định. Ở dạng initializer với `var`, compiler có đủ thông tin để tính kiểu của biểu thức điều kiện và suy ra kiểu biến. Không cần ép cả hai nhánh nếu một thiết kế khác cung cấp target phù hợp, nhưng cast tường minh giúp ví dụ rõ hơn.

### 8.3 Cùng `?:` nhưng nhánh có kiểu độc lập

Với các toán hạng số primitive:

~~~java
Number number = true ? 1 : 2L;
System.out.println(number.getClass().getSimpleName());
~~~

Đoạn này, đặt trong một method, in:

~~~text
Long
~~~

Vì đây là **numeric conditional expression**, quy tắc numeric promotion cho `int` và `long` tạo giá trị kiểu `long`, sau đó boxing thành `Long` để gán vào `Number`. Kiểu `Number` bên ngoài không khiến compiler tùy ý chọn `Integer` ở nhánh `1`. Không nên nhầm cơ chế này với truyền target vào lambda.

Một reference conditional với hai biểu thức đã có kiểu có thể nhận target khi ở assignment/invocation context:

~~~java
CharSequence text = true ? "Java" : new StringBuilder("JVM");
~~~

Cả hai nhánh đều có thể chuyển sang `CharSequence`; biểu thức phù hợp với target này. Nhưng nếu viết `var text = ...`, compiler phải suy ra kiểu từ chính điều kiện và các nhánh theo quy tắc riêng; đừng mặc định biến có kiểu `CharSequence` chính xác như ví dụ khai báo tường minh.

### 8.4 Lambda/method reference trong nhánh `?:`

Biểu thức điều kiện có thể chọn giữa:

- Hai lambda.
- Một lambda và một method reference.
- Hai method references.
- Một lambda và `null`, với target reference thích hợp.

Ví dụ trong method có import `IntUnaryOperator`:

~~~java
IntUnaryOperator choose = flag
        ? x -> x + 1
        : Math::abs;
~~~

Khi `flag` là `false`, compiler có thể chọn method reference `Math::abs` phù hợp với kiểu `int -> int`. Khi `flag` là `true`, nhánh lambda có cùng target. Đoạn này không phải chương trình độc lập vì biến `flag` cần được khai báo.

### 8.5 Precedence và cú pháp

Không nên dựa vào việc đọc “bằng mắt” những biểu thức nhiều toán tử để suy ra target. Đặc biệt, lồng `?:`, method invocation, cast và lambda dễ gây nhầm phạm vi. Hãy thêm dấu ngoặc khi một biểu thức phức tạp:

~~~java
IntUnaryOperator strategy = flag
        ? (x -> x + 1)
        : (x -> x * 2);
~~~

Dấu ngoặc ở đây giúp nhìn rõ nhánh mà không thay functional target. Với cast, dấu ngoặc quyết định rõ cast áp dụng lên toàn bộ lambda hay phần nào của biểu thức. Giữ ví dụ đơn giản và đặt biến trung gian có kiểu rõ là cách tốt để chẩn đoán lỗi compiler.

## 9. Tương tác giữa generic inference, conditional và overload

Một expression có thể chịu nhiều nguồn ràng buộc:

1. Compiler xác định những overload ứng viên có thể áp dụng.
2. Với generic method, compiler tạo các biến suy luận kiểu và thu thập ràng buộc.
3. Lambda/method reference cần một kiểu đích đủ cụ thể để kiểm tra số lượng tham số, body, result và exception.
4. Reference conditional poly truyền target xuống các nhánh khi thỏa điều kiện ngữ cảnh.
5. Compiler hoàn thiện lựa chọn phương thức và kiểu theo quy tắc ngôn ngữ; nếu không có nghiệm duy nhất/hợp lệ, báo lỗi compile-time.

Đây là mô hình giải thích, không phải cam kết compiler luôn thực thi thuật toán theo đúng năm bước tuyến tính. Đặc tả Java quy định nhiều bước xác định applicability, inference và most-specific có quan hệ tương tác.

### Ví dụ: generic transform với biểu thức điều kiện

Tạo file **`GenericConditionalDemo.java`**:

~~~java
import java.util.function.Function;

public class GenericConditionalDemo {
    static <T, R> R apply(T input, Function<T, R> operation) {
        return operation.apply(input);
    }

    public static void main(String[] args) {
        boolean upper = args.length > 0;

        String result = apply(
                "java",
                upper ? String::toUpperCase : String::toLowerCase
        );

        System.out.println(result);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -d out GenericConditionalDemo.java
java -cp out GenericConditionalDemo
~~~

Stdout:

~~~text
java
~~~

Khi chạy `java -cp out GenericConditionalDemo yes`:

~~~text
JAVA
~~~

Tại lời gọi `apply`, compiler suy luận kiểu của `T` và `R` từ input `String`, từ phép chuyển trong `Function<T,R>` và từ assignment vào `String`. Reference conditional poly được kiểm tra trong ngữ cảnh tham số `Function<T,R>`; mỗi method reference cần phù hợp kiểu function đó. Với kết quả ở đây, hai method references đều nhận `String` làm receiver và trả `String`.

### Ví dụ: overload thay đổi tính rõ ràng của target

Nếu một API có hai overload cùng nhận functional interface gần tương đương, target không còn hiển nhiên. Với code kiểu:

~~~java
// Pseudocode dạng Java, minh họa một trường hợp overload:
static void execute(java.util.function.Supplier<String> action) {}
static void execute(java.util.concurrent.Callable<String> action) {}

static void example() {
    // execute(() -> "OK"); // Mơ hồ giữa hai overload.
    execute((java.util.function.Supplier<String>) () -> "OK");
}
~~~

Cùng một lambda có thể được check theo nhiều SAM. Cast trước lời gọi giải thích rõ method nào được chọn. Nếu bạn sở hữu API, có thể thiết kế tên phương thức rõ hơn để không buộc người dùng cast nhiều lần.

## 10. Các lỗi compiler thường gặp

| Hiện tượng | Nguyên nhân ngữ nghĩa | Cách sửa |
| --- | --- | --- |
| “lambda expression needs an explicit target type” hoặc “lambda expression not expected here” | Không có functional-interface target hợp lệ | Khai báo biến/return/parameter kiểu functional interface hoặc cast đúng |
| `var f = x -> x + 1` báo không suy ra được kiểu | `var` không tạo SAM từ initializer là lambda | `IntUnaryOperator f = x -> x + 1` |
| `Object o = () -> 1` bị lỗi | `Object` không phải functional interface | `Object o = (Supplier<Integer>) () -> 1` |
| “incompatible parameter types in lambda expression” | Lambda khai báo tham số khác chữ ký SAM | Kiểm tra arity, kiểu và explicit/implicit parameter |
| “bad return type in lambda expression” | Body không trả kiểu tương thích SAM | Chọn interface phù hợp hoặc sửa body/return |
| “incompatible thrown types” | Body/method reference ném checked exception không được SAM cho phép | Xử lý exception hoặc dùng interface khai báo throws thích hợp |
| “invalid method reference” | Receiver, overload, arity hoặc return type không khớp SAM | Kiểm tra method được tham chiếu, target và loại bound/unbound |
| “reference to ... is ambiguous” | Nhiều overload có khả năng áp dụng mà không có lựa chọn duy nhất | Cast sang interface mong muốn hoặc dùng biến trung gian |
| `var f = flag ? lambda1 : lambda2` lỗi | Conditional không có kiểu đích functional interface cho các lambda | Đặt functional type bên trái hoặc cast các nhánh |
| Conditional với `int` và `long` ra kiểu bất ngờ | Đây là numeric conditional, dùng quy tắc numeric promotion | Phân biệt numeric/boolean/reference conditional, kiểm tra boxing |
| Method reference đúng tên nhưng sai compile | Target kiểm tra cả số/kiểu tham số, receiver, result, throws | Viết lambda tương đương có kiểu tường minh để nhìn thấy chỗ sai |

### Cách xử lý khi thông báo compiler khó hiểu

1. **Tìm vị trí expression.** Lambda/method reference đang ở assignment, return, argument, cast hay nhánh `?:`?
2. **Xác định target.** Viết ra kiểu functional interface và chữ ký SAM cụ thể, gồm generic type arguments.
3. **So khớp arity và kiểu.** Đếm tham số; với `Type::instanceMethod`, nhớ tham số đầu tiên có thể đóng vai receiver.
4. **Kiểm tra body.** Có trả về giá trị, thuộc kiểu nào, có checked exception hay không?
5. **Xét overload.** Nếu có hai ứng viên, đưa lambda vào một biến đã có functional type hoặc thêm cast để kiểm tra riêng từng ứng viên.
6. **Xét `?:`.** Đây là numeric, boolean hay reference conditional? Nó đang ở assignment/invocation context có truyền target vào nhánh không?
7. **Kiểm tra giới hạn Java version.** Ví dụ `var` trong tham số lambda yêu cầu Java 11+, `Stream.toList()` cần Java 16+.

Đọc diagnostic theo toàn bộ dòng báo lỗi và vị trí caret; câu chữ cụ thể có thể khác theo phiên bản `javac`. Không suy ra lỗi runtime/JVM từ lỗi kiểu mà compiler đã phát hiện trước khi chạy.

## 11. Bài tập thực hành

### Bài 1 — Xác định target của từng biểu thức

Cho đoạn code minh họa trong một method có import tương ứng:

~~~java
Runnable a = () -> System.out.println("A");
Supplier<Integer> b = () -> 10;
Predicate<String> c = s -> s.isBlank();
Function<String, Integer> d = String::length;
~~~

**Đáp án:**

- `a` có SAM `void run()`, lambda không nhận đối số và trả void.
- `b` có SAM `Integer get()`, literal `10` được box.
- `c` có SAM `boolean test(String s)`.
- `d` có SAM `Integer apply(String s)`, dùng `String` làm receiver rồi box `int`.

### Bài 2 — Vì sao `var` không chấp nhận lambda?

~~~java
// Minh họa lỗi:
var f = x -> x + 1;
~~~

**Đáp án:** Lambda là poly expression, cần target là một functional interface. Chỉ `var` ở vế trái không cung cấp functional type. Sửa:

~~~java
IntUnaryOperator f = x -> x + 1;
~~~

### Bài 3 — Tìm lỗi ở method reference

~~~java
// Minh họa lỗi:
Function<Integer, String> wrong = String::toUpperCase;
~~~

**Đáp án:** Với unbound instance method `String::toUpperCase`, tham số target phải cấp receiver kiểu `String`, không phải `Integer`. Cách hợp lệ:

~~~java
Function<String, String> upper = String::toUpperCase;
~~~

### Bài 4 — Dự đoán hai nhánh

Với `ConditionalTargetDemo` ở mục 8, hãy dự đoán stdout không có đối số và có một đối số.

**Đáp án:** Không có đối số: `direct = 8` và `argument = 8`. Có đối số: `direct = 5` và `argument = 5`. Target type của hai nhánh không đổi, chỉ có lựa chọn nhánh thay đổi.

### Bài 5 — Giải quyết overload

Hai overload nhận `Supplier<String>` và `Callable<String>`. Vì sao `use(() -> "done")` bị mơ hồ? Có thể giải quyết bằng cách nào?

**Đáp án:** Cùng một lambda tương thích với cả hai target. Cast tường minh tới một trong hai interface hoặc gán vào biến có kiểu đó trước khi gọi `use`.

### Bài 6 — Numeric conditional khác poly conditional

Xét:

~~~java
Number value = true ? 1 : 2L;
~~~

**Đáp án:** Hai nhánh là numeric operands `int`/`long`; expression có kiểu `long` theo numeric promotion, rồi box thành `Long` khi gán cho `Number`. Ngữ cảnh bên trái không truyền `Number` vào từng nhánh theo kiểu reference conditional poly.

## 12. Checklist trước khi kết luận một lambda/method reference hợp lệ

- [ ] Vị trí biểu thức có **functional-interface target** thực sự, hoặc đã có cast phù hợp.
- [ ] Interface thỏa định nghĩa functional interface với SAM cần thiết.
- [ ] Số và kiểu tham số lambda/method reference tương thích SAM.
- [ ] Body có kiểu trả về, dạng `void`/value và checked exceptions tương thích.
- [ ] Với method reference, đã xác định đúng dạng static, bound instance, unbound instance hay constructor.
- [ ] Nếu có overload, đã xét tất cả ứng viên và biết vì sao lời gọi có lựa chọn duy nhất.
- [ ] Nếu có `?:`, đã phân biệt reference poly conditional với numeric/boolean conditional.
- [ ] Nếu có generic, đã xác nhận ràng buộc suy luận kiểu và boxing/unboxing cần thiết.
- [ ] Đã biên dịch thử trên JDK mục tiêu, không chỉ đoán từ cú pháp.

## 13. Tổng kết kiến thức

**Target typing là mối liên hệ giữa ngữ cảnh và biểu thức.** Lambda và method reference cần functional-interface target để compiler kiểm tra SAM; chúng không có một kiểu standalone tùy ý chỉ dựa trên hình dạng chữ viết. Reference conditional `?:` có thể truyền target xuống hai nhánh trong assignment/invocation context, vì vậy ta có thể chọn giữa hai lambda hoặc method references. Nhưng numeric/boolean conditionals vận hành theo quy tắc kiểu riêng, và các overload hoặc generic constraints có thể khiến lựa chọn target trở nên mơ hồ.

Khi gặp lỗi, hãy lần ngược từ **vị trí sử dụng → kiểu đích → chữ ký SAM → tham số/body/return/throws → overload/conditional/generic**. Cách phân tích này giải thích nguyên nhân compile-time tốt hơn việc thay ngẫu nhiên dấu ngoặc hoặc cast cho đến khi hết lỗi.