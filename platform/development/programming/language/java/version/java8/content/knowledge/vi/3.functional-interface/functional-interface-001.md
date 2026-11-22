# Single Abstract Method (SAM) và Functional Descriptor trong Java

## 1. Hai khái niệm quyết định lambda có hợp lệ hay không

**Functional interface** là interface mang đúng **một hợp đồng phương thức trừu tượng độc lập** để một lambda hoặc method reference có thể triển khai. Hợp đồng ấy thường được gọi là **Single Abstract Method (SAM)**. Trong Java Language Specification, **function type** của functional interface mô tả chữ ký mà lambda phải đáp ứng; trong tài liệu học và cách nói thông dụng, tập thông tin đó thường được gọi là **functional descriptor**.

Có thể hình dung hai khái niệm như sau:

- **SAM** trả lời: *Phương thức trừu tượng nào đóng vai trò hành vi chính của interface?*
- **Functional descriptor** trả lời: *Một giá trị lambda phải nhận những tham số gì, trả kiểu nào và được phép khai báo checked exception nào để khớp hợp đồng?*

Ví dụ:

~~~java
@FunctionalInterface
interface NameChecker {
    boolean check(String name);
}
~~~

`NameChecker` có một SAM là `check`; descriptor tương ứng là:

~~~text
(String) -> boolean
~~~

Một lambda phù hợp:

~~~java
NameChecker nonBlank = name -> name != null && !name.isBlank();
~~~

Trong ví dụ này, `name` nhận một `String` và thân lambda tạo một `boolean`. Phương thức `String.isBlank()` có từ Java 11; đây là API hiện đại, không có trong JDK 8. Nếu dự án phải biên dịch bằng đúng JDK 8, có thể dùng `name -> name != null && !name.trim().isEmpty()` (đồng thời hiểu rằng hai cách xác định khoảng trắng không hoàn toàn đồng nhất). Phần còn lại của bài sử dụng ví dụ tương thích Java 8 khi có thể, nhưng các nguyên tắc SAM vẫn áp dụng trên JDK hiện tại.

> Lưu ý thuật ngữ: **descriptor là mô tả hợp đồng kiểu**, không phải một chuỗi khai báo độc lập của Java và cũng không phải tên một lớp được tạo ra ở runtime. `(String) -> boolean` ở trên là cách ghi dễ đọc, không phải một dòng mã Java có thể biên dịch riêng.

## 2. Quy tắc xác định SAM: không chỉ đếm dòng khai báo

Một interface được coi là functional interface khi tập các phương thức trừu tượng hợp lệ của nó quy về **một phương thức chức năng** theo quy tắc chữ ký, kế thừa và kiểu trả về của Java.

### 2.1. Interface có một abstract method

~~~java
@FunctionalInterface
interface Formatter {
    String format(String input);
}
~~~

Đây là ví dụ đơn giản nhất. `Formatter` có SAM `format(String)` và descriptor `(String) -> String`.

Annotation `@FunctionalInterface` **không bắt buộc** để dùng lambda. Nó có tác dụng yêu cầu trình biên dịch kiểm tra interface có đúng một hợp đồng chức năng. Khi interface bị sửa thành không còn functional, lỗi được phát hiện ngay ở chỗ khai báo interface.

### 2.2. `default` và `static` không tạo thêm SAM

~~~java
@FunctionalInterface
interface TextAction {
    void perform(String value); // SAM duy nhất

    default void performTwice(String value) {
        perform(value);
        perform(value);
    }

    static String normalize(String input) {
        return input == null ? "" : input.trim();
    }
}
~~~

`perform` là abstract method cần triển khai. `performTwice` đã có thân `default`; `normalize` là phương thức `static` thuộc interface. Chúng **không** làm thay đổi số lượng abstract method. Trong Java hiện đại, interface còn có thể có phương thức private để chia sẻ logic nội bộ (từ Java 9); các phương thức có thân này cũng không thêm SAM.

**Không nhầm** một phương thức `default` có thể *gọi* SAM với việc nó là SAM mới: chỉ hợp đồng abstract cần được lambda cung cấp phần cài đặt.

### 2.3. Phương thức tương ứng với public method của `Object` được loại khỏi phép đếm

~~~java
@FunctionalInterface
interface EventListener {
    void onEvent(String event); // SAM

    boolean equals(Object other); // Tương ứng Object.equals
}
~~~

`equals(Object)` đã là public instance method của `java.lang.Object`, nên khai báo abstract có chữ ký tương ứng **không được tính thành hành vi chức năng thứ hai**. Tương tự, có thể xét các chữ ký tương ứng `hashCode()` và `toString()`.

Điều này **không** có nghĩa mọi phương thức có tên giống `Object` đều được bỏ qua. Ví dụ một phương thức tùy biến `boolean equals(String other)` có tham số khác `Object.equals(Object)` sẽ là một hợp đồng riêng.

Interface chỉ khai báo `equals(Object)` mà không có thêm SAM độc lập sẽ **không** phải functional interface. Không có hành vi mới nào để lambda triển khai.

### 2.4. Các abstract method kế thừa có thể cùng một hợp đồng

Hai interface cha có thể cùng khai báo một chữ ký:

~~~java
interface Starts {
    void execute();
}

interface Runs {
    void execute();
}

@FunctionalInterface
interface CombinedAction extends Starts, Runs {
}
~~~

`CombinedAction` vẫn là functional interface: hai khai báo `execute()` là các phương thức **override-equivalent**, quy về cùng hợp đồng `void execute()`.

Vì vậy quy tắc “đúng một abstract method” là cách nhớ ngắn gọn; khi có kế thừa, cần nhìn vào **các chữ ký trừu tượng độc lập** sau khi áp dụng quy tắc override, chứ không đơn thuần đếm các dòng `abstract` trên mọi interface cha. Những trường hợp nhiều khai báo cùng tên nhưng chữ ký không tương thích hoặc kiểu trả về không tương thích có thể làm interface không hợp lệ hay không còn functional.

### 2.5. Nhiều hợp đồng độc lập thì không thể là functional interface

~~~java
interface InvalidAction {
    void start();
    void stop();
}
~~~

`InvalidAction` có hai hành vi độc lập. Không thể viết một lambda để cung cấp đồng thời cả `start` và `stop`. Nếu thêm `@FunctionalInterface` vào interface trên, trình biên dịch báo lỗi ở khai báo annotation. Để dùng lambda, hãy thiết kế lại thành một SAM phản ánh đúng hành vi, hoặc giữ interface nhiều phương thức và triển khai bằng lớp thông thường.

## 3. Functional descriptor gồm những gì?

Với functional interface, function type/descriptor mô tả các thành phần sau:

1. **Số lượng và kiểu tham số** mà lambda nhận.
2. **Kiểu kết quả**: `void`, primitive hoặc reference type; thân lambda phải tương thích.
3. **Danh sách checked exception cho phép** từ phương thức chức năng (theo quy tắc `throws` và kế thừa). Lambda không được tự ý ném checked exception rộng hơn hợp đồng.
4. **Thông tin generic/type parameter** khi kiểu đích hoặc chữ ký SAM có tham số kiểu. Việc thay `T`, `R` bằng kiểu cụ thể có thể làm descriptor tại nơi sử dụng cụ thể hơn.

Bảng đối chiếu những interface vẫn dùng rộng rãi:

| Kiểu đích | SAM | Descriptor dễ đọc | Ý nghĩa |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `() -> void` | Hành động không nhận tham số |
| `Supplier<String>` | `String get()` | `() -> String` | Tạo/cung cấp chuỗi |
| `Consumer<String>` | `void accept(String)` | `(String) -> void` | Tiêu thụ chuỗi |
| `Predicate<String>` | `boolean test(String)` | `(String) -> boolean` | Điều kiện |
| `Function<String,Integer>` | `Integer apply(String)` | `(String) -> Integer` | Ánh xạ |
| `BiFunction<Integer,Integer,Integer>` | `Integer apply(Integer,Integer)` | `(Integer,Integer) -> Integer` | Kết hợp hai giá trị |
| `Comparator<String>` | `int compare(String,String)` | `(String,String) -> int` | Quy tắc thứ tự |
| `IntUnaryOperator` | `int applyAsInt(int)` | `(int) -> int` | Biến đổi `int` không boxing |
| `Callable<String>` | `String call() throws Exception` | `() -> String`, cho phép `Exception` | Tác vụ trả kết quả |

**Chú ý**: `Comparator<T>` có thêm các phương thức mặc định/static và công khai `equals(Object)` nhưng SAM vẫn là `compare(T,T)`. `Callable<V>` có chữ ký `throws Exception`; không nên suy diễn rằng mọi `Supplier<V>` hay `Runnable` cũng cho phép ném checked exception.

### Generic thay đổi kiểu descriptor tại nơi dùng

~~~java
java.util.function.Function<String, Integer> length = String::length;
java.util.function.Function<Integer, String> stringify = Object::toString;
~~~

Với `Function<T,R>`, SAM được khai báo ở mức tổng quát là `R apply(T value)`. Khi chọn `Function<String,Integer>`, đầu vào là `String` và kết quả là `Integer`. Method reference `String::length` trả primitive `int`, được **boxing** thành `Integer` theo ngữ cảnh. Tương tự, `Object::toString` ở đây có thể được áp dụng trên đối số `Integer` rồi trả `String`.

Generic là cơ chế kiểm tra kiểu ở thời điểm biên dịch; lambda không đòi bạn viết một phiên bản riêng cho từng kiểu khi API được tham số hóa thích hợp.

## 4. Ví dụ Java chạy được: nhận diện SAM, `default`, `static` và `Object`

Tạo tệp **SamDescriptorDemo.java**:

~~~java
public class SamDescriptorDemo {

    @FunctionalInterface
    interface StringRule {
        boolean check(String text); // SAM

        boolean equals(Object other); // Không tính thêm SAM

        default String label() {
            return "rule";
        }

        static String kind() {
            return "SAM";
        }
    }

    public static void main(String[] args) {
        String suffix = ".java";

        StringRule hasJavaSuffix =
                text -> text != null && text.endsWith(suffix);
        StringRule longEnough =
                text -> text != null && text.length() >= 8;

        System.out.println(hasJavaSuffix.check("Main.java"));
        System.out.println(hasJavaSuffix.check("notes.txt"));
        System.out.println(longEnough.check("Example"));
        System.out.println(hasJavaSuffix.label());
        System.out.println(StringRule.kind());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ (toàn bộ cấu trúc trong ví dụ tương thích Java 8):

~~~bash
javac SamDescriptorDemo.java
java SamDescriptorDemo
~~~

**Stdout chính xác:**

~~~text
true
false
false
rule
SAM
~~~

Giải thích:

- `StringRule` có SAM `boolean check(String)`; `equals(Object)` tương ứng với `Object.equals` không tạo thêm hợp đồng chức năng.
- `label()` đã được cài bằng `default`, còn `kind()` là `static`, vì thế cả hai không ngăn việc dùng lambda.
- Hai lambda có cùng descriptor `(String) -> boolean` nhưng cài **hai quy tắc khác nhau**: kiểm tra hậu tố và kiểm tra độ dài.
- `suffix` là biến local được capture. Nó effectively final vì không bị gán lại. Capture không đổi descriptor: `StringRule.check` vẫn chỉ nhận đúng một tham số `String`.
- `"Example"` có 7 ký tự, nhỏ hơn 8, nên dòng thứ ba là `false`.

## 5. Descriptor quyết định lambda hợp lệ ra sao?

Java kiểm tra lambda dựa trên **target type** là một functional interface, không dựa vào hình dạng văn bản của lambda một cách độc lập.

~~~java
java.util.function.Predicate<String> nonEmpty =
        text -> text != null && !text.isEmpty();

java.util.function.Consumer<String> printer =
        text -> System.out.println(text);

java.util.function.IntUnaryOperator doubleIt =
        value -> value * 2;
~~~

Trong ba phép gán:

- `Predicate<String>` yêu cầu một `String` và trả `boolean`.
- `Consumer<String>` yêu cầu một `String` và trả `void`; phần thân là một lời gọi phương thức, phù hợp lambda thân biểu thức dạng *statement expression*.
- `IntUnaryOperator` yêu cầu một `int` và trả `int`.

### 5.1. Suy luận kiểu tham số

Vì kiểu đích đã rõ, có thể viết `s -> s.length()` thay vì `(String s) -> s.length()` trong ngữ cảnh đích `ToIntFunction<String>`.

~~~java
java.util.function.ToIntFunction<String> size = s -> s.length();
~~~

Dù không ghi `String` trong lambda, Java vẫn biết `s` là `String` từ descriptor. Khi cần, có thể khai báo kiểu tham số tường minh:

~~~java
java.util.function.ToIntFunction<String> size =
        (String s) -> s.length();
~~~

Trong một danh sách tham số lambda, không trộn tùy tiện tham số có kiểu khai báo tường minh với tham số suy luận kiểu; dùng một cách nhất quán và để trình biên dịch kiểm tra.

### 5.2. Kiểu kết quả và `void`

Những đoạn sau **cố ý không biên dịch** (đặt độc lập trong phương thức để minh họa lỗi):

~~~java
java.util.function.Predicate<String> p = s -> s.length();
// Sai: int không chuyển thành boolean

java.util.function.Supplier<Integer> number = () -> "one";
// Sai: String không thể là Integer

Runnable task = () -> 42;
// Sai: literal 42 không phải thân lambda phù hợp void
~~~

Với SAM trả `void`, lambda có thể có thân khối không `return` giá trị hoặc biểu thức là statement expression (như lời gọi phương thức). Với SAM trả kết quả, mỗi đường đi hoàn tất bình thường qua thân khối phải cung cấp kết quả đúng kiểu theo quy tắc Java; với thân biểu thức, giá trị biểu thức phải tương thích kiểu trả về.

### 5.3. Khi không có kiểu đích

~~~java
var operation = x -> x + 1; // Cố ý không biên dịch
~~~

Lambda không có kiểu độc lập để Java tự suy ra chỉ từ `x -> x + 1`. Cần chỉ rõ functional interface:

~~~java
java.util.function.IntUnaryOperator operation = x -> x + 1;
~~~

Tương tự, không thể gán trực tiếp một lambda “trần” vào `Object`. Có thể truyền lambda vào lời gọi phương thức có tham số kiểu functional interface, gán cho biến có kiểu functional interface hoặc ép kiểu lambda sang functional interface để cung cấp target type. Đây là một trong những vai trò thực tế quan trọng nhất của descriptor.

## 6. Ví dụ Java chạy được: cùng cú pháp, descriptor khác nhau

Tạo tệp **DescriptorTargetDemo.java**:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;

public class DescriptorTargetDemo {

    @FunctionalInterface
    interface Converter<T, R> {
        R convert(T input);
    }

    static <T, R> R convert(T value, Converter<T, R> converter) {
        return converter.convert(value);
    }

    public static void main(String[] args) {
        Converter<String, Integer> length = String::length;
        Converter<String, String> trimmed = String::trim;

        System.out.println(convert("lambda", length));
        System.out.println(convert("  Java  ", trimmed));

        Function<String, Integer> parse = Integer::parseInt;
        System.out.println(parse.apply("21") + 1);

        IntUnaryOperator doubled = value -> value * 2;
        System.out.println(doubled.applyAsInt(5));

        Supplier<String> greeting = () -> "hello";
        Consumer<String> show = System.out::println;
        show.accept(greeting.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DescriptorTargetDemo.java
java DescriptorTargetDemo
~~~

Stdout:

~~~text
6
Java
22
10
hello
~~~

Phân tích:

1. `Converter<T,R>` tự định nghĩa có SAM `R convert(T)`. Đối với `Converter<String,Integer>`, descriptor áp dụng tại đây là `(String) -> Integer`. Method reference `String::length` tương thích nhờ boxing `int` thành `Integer`.
2. Với `Converter<String,String>`, method reference `String::trim` phù hợp descriptor `(String) -> String`.
3. `Function<String,Integer>` tiếp nhận `Integer::parseInt`. Phương thức `parseInt` trả `int`, được boxing; trong `parse.apply("21") + 1`, `Integer` lại được unboxing để thực hiện phép cộng.
4. `IntUnaryOperator` dùng `int` ở cả đầu vào/đầu ra nên tránh boxing cho thao tác số học này.
5. `Supplier<String>` có descriptor `() -> String`; `Consumer<String>` có descriptor `(String) -> void`. Hai hành vi được kết hợp ở nơi gọi bằng `show.accept(greeting.get())`.

**Lưu ý:** cú pháp `String::length`, `String::trim` và `Integer::parseInt` không quyết định kiểu đích một cách độc lập; compiler so khớp method reference với descriptor ở vị trí sử dụng. Một method reference có thể không phù hợp với một SAM khác dù tên phương thức giống nhau.

## 7. Checked exception là một phần của hợp đồng

Giả sử muốn truyền hành vi đọc dữ liệu có thể ném `IOException`.

~~~java
@FunctionalInterface
interface TextLoader {
    String load() throws java.io.IOException;
}
~~~

Descriptor của `TextLoader` không chỉ nói `() -> String`; nó còn **cho phép `IOException`** khi hành vi được gọi.

~~~java
TextLoader loader = () -> {
    throw new java.io.IOException("offline");
};
~~~

Hai đoạn trên là **mảnh mã minh họa**, cần đặt trong lớp/phương thức thích hợp để chạy. Chúng hợp lệ vì SAM khai báo `throws IOException`. Ở phía gọi, phương thức `loader.load()` vẫn phải được xử lý bằng `try/catch` hoặc khai báo `throws`.

Ngược lại, các SAM chuẩn như `Supplier.get()`, `Function.apply()`, `Predicate.test()`, `Runnable.run()` **không khai báo checked exception**. Không thể đưa trực tiếp lambda ném `IOException` chưa xử lý vào chúng. Cần xử lý lỗi trong callback hoặc định nghĩa interface có hợp đồng `throws` phù hợp. `Callable<V>.call()` cho phép `throws Exception` nhưng là hợp đồng tác vụ trả kết quả; không nên dùng `Callable` chỉ để né thiết kế lỗi của một API hoàn toàn khác.

**Phân biệt:** unchecked exception (`RuntimeException` và các lớp con) không bị áp cùng hạn chế khai báo `throws` như checked exception. Tuy vậy, API vẫn phải làm rõ cách xử lý/thông báo lỗi callback.

## 8. Kế thừa, override-equivalent và các trường hợp cần thận trọng

Ở những trường hợp kế thừa phức tạp, Java xem xét tập abstract method sau khi loại những chữ ký tương ứng với public instance method của `Object`. Một phương thức có thể đóng vai trò đại diện cho toàn bộ hợp đồng nếu chữ ký của nó **subsignature** với các phương thức còn lại và kiểu trả về **return-type-substitutable** theo quy tắc ngôn ngữ.

Không cần thuộc lòng các quy tắc này để sử dụng `Predicate` hoặc `Function` hàng ngày, nhưng cần biết chúng để hiểu vì sao **hai khai báo** không nhất thiết có nghĩa là hai SAM, và vì sao một số cách kết hợp interface không hợp lệ.

Ví dụ thêm về kiểu trả về hiệp biến (*covariant return*):

~~~java
interface HasValue {
    Number value();
}

interface HasIntegerValue {
    Integer value();
}

@FunctionalInterface
interface IntegerValueSource extends HasValue, HasIntegerValue {
}
~~~

`Integer` là kiểu con của `Number`; hai hợp đồng có cùng tên/danh sách tham số và kiểu trả về tương thích, nên có thể được thỏa bằng một cài đặt trả `Integer`. Đối với một API public, nên giữ hợp đồng rõ ràng: nếu cấu trúc kế thừa quá phức tạp, việc khai báo lại SAM rõ kiểu trả về hoặc đơn giản hóa interface thường giúp mã dễ đọc hơn.

Nếu thêm vào interface một abstract method hoàn toàn mới, chẳng hạn `void reset()`, annotation `@FunctionalInterface` sẽ báo lỗi. Không nên loại bỏ annotation để “sửa” lỗi; vấn đề thực tế là giao diện đã không còn biểu diễn một hành vi đơn lẻ thích hợp cho lambda.

## 9. Descriptor gắn với target typing và overload

Phương thức nhận lambda thường khai báo tham số bằng functional interface:

~~~java
static void process(java.util.function.Predicate<String> rule) {
    System.out.println(rule.test("java"));
}
~~~

Lời gọi (minh họa đặt trong lớp/phương thức thích hợp):

~~~java
process(text -> text.length() == 4); // true
~~~

Kiểu tham số của `process` định hướng Java rằng `text` là `String` và kết quả phải là `boolean`.

Tuy nhiên, overload có thể gây mơ hồ. Ví dụ giả sử có hai overload:

~~~java
static void fetch(java.util.function.Supplier<String> source) {}
static void fetch(java.util.concurrent.Callable<String> source) {}
~~~

Lời gọi sau (minh họa lỗi) không đủ thông tin để chọn một overload:

~~~java
fetch(() -> "data"); // Có thể mơ hồ giữa Supplier và Callable
~~~

Cách giải quyết là dùng tên API có nghĩa rõ ràng hoặc cung cấp target type trước:

~~~java
java.util.function.Supplier<String> source = () -> "data";
fetch(source);
~~~

Trong các mảnh mã trên, chỉ tiêu đề overload ở ví dụ tương ứng mới cần được định nghĩa để biên dịch; chúng không phải chương trình hoàn chỉnh. Bài học thiết kế là **không nên overload cùng tên nhiều lần chỉ khác những functional interface có descriptor tương tự** nếu người gọi sẽ thường truyền lambda trần.

## 10. Method reference cũng phải khớp descriptor

Method reference là cách viết ngắn cho việc chuyển lời gọi tới phương thức hoặc constructor đã có. Nó cũng cần target type là một functional interface:

| Dạng | Ví dụ | Kiểu đích thường gặp |
| --- | --- | --- |
| Phương thức static | `Integer::parseInt` | `Function<String,Integer>` |
| Phương thức instance của một đối tượng cụ thể | `System.out::println` | `Consumer<String>` |
| Phương thức instance của đối tượng sẽ nhận lúc gọi | `String::length` | `ToIntFunction<String>` |
| Constructor | `java.util.ArrayList<String>::new` | `Supplier<java.util.List<String>>` |

Lưu ý hai trường hợp instance khác nhau:

- `object::method` sử dụng đối tượng receiver đã có khi tạo method reference.
- `Type::instanceMethod` sử dụng một tham số của descriptor làm receiver. Ví dụ `String::length` phù hợp `ToIntFunction<String>` vì nó có thể hiểu là `s -> s.length()`.

Không phải mọi method reference đều đơn giản hơn lambda. Khi cần biến đổi thêm dữ liệu trước khi gọi hoặc khi dạng tham chiếu làm người đọc khó suy luận về receiver, lambda có tên tham số tường minh có thể rõ hơn.

## 11. Những nhầm lẫn và lỗi thường gặp

1. **“SAM bằng một dòng abstract khai báo trong interface.”** Cần tính cả kế thừa, chữ ký override-equivalent và loại các public method tương ứng của `Object`. `default`/`static` không thêm abstract contract.
2. **“Không có `@FunctionalInterface` thì không thể dùng lambda.”** Annotation chỉ thêm kiểm tra compile-time; interface thực sự hợp lệ vẫn dùng được dù không ghi annotation.
3. **“Descriptor là tên method hoặc tên interface.”** Descriptor mô tả tham số, kiểu trả về, checked exception và generic trong function type; tên method hỗ trợ khai báo SAM, nhưng kiểu lambda phải được suy ra từ target interface.
4. **“Cứ cùng số tham số là lambda hợp lệ.”** Kiểu tham số, kiểu trả về và kiểm tra exception đều phải khớp.
5. **“Lambda tạo ra là chạy ngay.”** SAM cho biết hình dạng lời gọi, không quy định callback chạy lúc nào, mấy lần, có bất đồng bộ hay không.
6. **“Lambda có thể được suy ra kiểu chỉ từ cú pháp.”** Không thể viết `var f = x -> x + 1` nếu không có target type.
7. **“Function trả `Integer` thì không dùng được method trả `int`.”** Boxing/unboxing có thể làm tương thích, nhưng cũng có chi phí cần cân nhắc nếu xử lý dữ liệu số quy mô lớn.
8. **“Có `throws` ở thân lambda là có thể ném checked exception ra ngoài.”** Phải xem descriptor có cho phép checked exception đó hay không và caller phải xử lý theo hợp đồng SAM.
9. **“Nhiều overload nhận lambda luôn tốt.”** Các descriptor gần nhau có thể gây lời gọi mơ hồ; API thường rõ hơn nếu dùng tên khác hoặc mục đích hành vi khác nhau.

## 12. Bài tập tự luyện

**Bài 1 — Xác định SAM.** Với interface sau, hãy ghi SAM và descriptor, giải thích vì sao `reset` không thêm abstract method:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String value);

    default String reset() {
        return "";
    }

    static String identity(String input) {
        return input;
    }

    boolean equals(Object other);
}
~~~

Đáp án đối chiếu: SAM là `format(String)`, descriptor `(String) -> String`. `reset` có thân `default`, `identity` là `static`, `equals(Object)` tương ứng public instance method của `Object`.

**Bài 2 — Chọn interface chuẩn.** Với từng hành vi, chọn một functional interface có sẵn và viết lambda phù hợp: (a) kiểm tra `Integer` dương; (b) chuyển `String` thành độ dài `int`; (c) in một `String`; (d) tạo một `String` không nhận tham số. So sánh `ToIntFunction<String>` với `Function<String,Integer>` về boxing.

**Bài 3 — Phát hiện lỗi biên dịch.** Giải thích vì sao ba lời gán này không hợp lệ:

~~~java
java.util.function.Predicate<String> a = s -> s.length();
java.util.function.Supplier<Integer> b = () -> "abc";
java.util.function.Consumer<String> c = s -> { return s; };
~~~

Đối chiếu: `a` trả `int` thay vì `boolean`; `b` trả `String` thay vì `Integer`; `c` cố trả một `String` trong SAM `void`.

**Bài 4 — Thiết kế interface có checked exception.** Tạo `@FunctionalInterface interface FileLoader { String load() throws IOException; }`, cài một lambda đọc nội dung từ tệp bằng API `Files.readString(Path)` trên JDK 17+ và bắt `IOException` tại chỗ gọi. Giải thích vì sao đổi kiểu đích thành `Supplier<String>` buộc bạn xử lý exception trong lambda hoặc đổi thiết kế API. `Files.readString` là API từ Java 11, còn quy tắc descriptor là nền tảng Java 8 đến nay.

## 13. Ghi nhớ

- **SAM** là hợp đồng abstract duy nhất của functional interface sau khi xét đúng quy tắc kế thừa, chữ ký và các phương thức `Object`. Annotation `@FunctionalInterface` giúp kiểm tra hợp đồng này khi biên dịch.
- **Functional descriptor/function type** diễn tả số lượng/kiểu tham số, kết quả, checked exception và generic của SAM tại target type. Nó quyết định lambda và method reference có tương thích hay không.
- `default` và `static` không làm phát sinh thêm SAM; hai khai báo kế thừa có thể cùng biểu diễn một hợp đồng khi override-equivalent và tương thích.
- Java sử dụng **target typing**: lambda không phải một hàm độc lập tự suy ra mọi kiểu; interface đích cung cấp thông tin để trình biên dịch kiểm tra và suy luận.
- Kiểu descriptor quy định **hình dạng lời gọi**, còn việc gọi lúc nào, bao nhiêu lần và trên luồng nào thuộc về API nhận callback. Những nguyên tắc này vẫn thiết yếu trong Java hiện đại và các API Stream, collection, callback, executor.
