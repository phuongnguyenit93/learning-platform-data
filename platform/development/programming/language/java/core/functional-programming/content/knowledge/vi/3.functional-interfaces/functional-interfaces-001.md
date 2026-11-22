# Functional interface và phương thức trừu tượng duy nhất trong Java

## 1. Functional interface là gì?

**Functional interface** là một `interface` có đúng **một phương thức trừu tượng cần được triển khai** (*single abstract method*, thường viết tắt là **SAM**) theo quy tắc đếm phương thức của Java. Chính phương thức này xác định chữ ký mà biểu thức lambda hoặc method reference phải thực hiện.

Một functional interface có thể có nhiều phương thức `default`, `static` và `private` có phần thân, cũng như các khai báo phù hợp với những phương thức `public` của `Object`. Những phương thức đó không làm phát sinh thêm SAM. Tên `@FunctionalInterface` là một annotation yêu cầu trình biên dịch kiểm tra hợp đồng; nó **không phải điều kiện bắt buộc** để interface đủ điều kiện nhận lambda.

Ví dụ ngắn:

~~~java
@FunctionalInterface
interface TextMapper {
    String map(String text);  // Phương thức trừu tượng duy nhất (SAM).

    default String mapInBrackets(String text) {
        return "[" + map(text) + "]";
    }
}
~~~

`map(String)` là SAM. Phương thức `mapInBrackets` có phần thân nên không được tính là phương thức trừu tượng thứ hai. Do đó, `TextMapper mapper = s -> s.toUpperCase();` là hợp lệ trong ngữ cảnh kiểu đích `TextMapper`.

**Ý nghĩa:** functional interface cung cấp một hợp đồng kiểu tường minh cho hành vi có thể truyền vào phương thức, lưu trong biến, trả về từ phương thức và kết hợp với các API như Stream. Lambda là một **cách triển khai** hợp đồng ấy, không phải chính định nghĩa functional interface.

## 2. Thế nào là “một phương thức trừu tượng duy nhất”?

Xét những dạng khai báo thường gặp:

| Thành phần trong interface | Có được tính là SAM không? | Lý do |
|---|---|---|
| `String convert(String s);` | **Có** | Phương thức không có thân, cần một triển khai |
| `default String label() { return "x"; }` | Không | Đã có triển khai mặc định |
| `static int version() { return 1; }` | Không | Thuộc chính interface, không phải thao tác instance phải triển khai |
| `private String helper() { return "x"; }` | Không | Phương thức trợ giúp có thân, được phép từ Java 9 |
| `boolean equals(Object other);` | Không, khi tương đương khai báo `public Object.equals` | Phương thức `Object` được loại khỏi phép đếm SAM theo quy tắc Java |
| Hai khai báo trừu tượng có chữ ký khác nhau | Thường không hợp lệ | Không còn một hành vi trừu tượng duy nhất |

**Điểm tinh tế về kế thừa:** Java xét tập phương thức trừu tượng sau khi tính đến kế thừa, ghi đè và tính tương thích chữ ký. Có thể có nhiều *khai báo* trừu tượng nhưng vẫn chỉ biểu diễn một hợp đồng chức năng nếu các khai báo đó tương thích và cùng được thực hiện bởi một phương thức. Vì thế, “một SAM” không có nghĩa là file source nhất thiết chỉ xuất hiện đúng một dấu chấm phẩy sau khai báo phương thức.

Một interface chỉ chứa `default` và `static` nhưng **không có SAM** thì không phải functional interface. Tương tự, interface chỉ khai báo lại `equals(Object)` mà không có phương thức trừu tượng khác cũng không trở thành functional interface.

### 2.1. Vì sao `Object.equals`, `hashCode` và `toString` được xử lý đặc biệt?

Mọi đối tượng Java đều liên quan đến hợp đồng `Object`. Những khai báo trừu tượng trong interface có chữ ký tương ứng với các phương thức `public` của `Object`, chẳng hạn `equals(Object)`, `hashCode()` và `toString()`, **không được đếm** khi xác định SAM.

Ví dụ:

~~~java
@FunctionalInterface
interface IdentifiedAction {
    void perform();
    boolean equals(Object other);
    int hashCode();
    String toString();
}
~~~

Khai báo trên hợp lệ: `perform()` là hành vi cần được lambda cung cấp. Lambda không nhận trách nhiệm riêng về ba phương thức `Object`. Cơ chế này cũng giải thích vì sao `Comparator<T>` vẫn là functional interface dù nó khai báo `equals(Object)`: SAM của `Comparator` là `compare(T, T)`.

Cẩn thận: không thể dùng `default` trong interface để ghi đè phương thức `public` của `Object` như `default String toString()`; trình biên dịch bác bỏ cách khai báo đó.

### 2.2. Kế thừa không nhất thiết tạo thêm SAM

Ví dụ minh họa hợp lệ:

~~~java
interface BaseAction {
    void run();
}

@FunctionalInterface
interface NamedAction extends BaseAction {
    @Override
    void run();

    default String name() {
        return "action";
    }
}
~~~

`NamedAction` khai báo lại chính hợp đồng `run()` đã kế thừa; không tạo một chức năng trừu tượng khác. Ngược lại, thêm `void stop();` vào `NamedAction` sẽ khiến interface này không còn là functional interface. Trình biên dịch sẽ chỉ ra lỗi vì `@FunctionalInterface` yêu cầu một SAM.

## 3. Chương trình hoàn chỉnh: một SAM, nhiều loại phương thức

Lưu mã sau thành file `FunctionalInterfaceDemo.java`:

~~~java
import java.util.Locale;

@FunctionalInterface
interface TextAction {
    String apply(String input); // SAM duy nhất.

    // Tương đương phương thức public của Object: không được đếm thành SAM.
    boolean equals(Object other);

    default String surround(String input) {
        return "[" + apply(input) + "]";
    }

    default String normalized(String input) {
        return apply(clean(input));
    }

    static TextAction identity() {
        return input -> input;
    }

    private static String clean(String input) {
        return input.trim();
    }
}

public class FunctionalInterfaceDemo {
    public static void main(String[] args) {
        TextAction upper = text -> text.toUpperCase(Locale.ROOT);
        TextAction trim = String::trim;

        System.out.println(upper.apply("java"));
        System.out.println(upper.surround("lambda"));
        System.out.println(upper.normalized("  hello  "));
        System.out.println(trim.apply("  JDK  "));
        System.out.println(TextAction.identity().apply("same"));
    }
}
~~~

Với JDK 17 trở lên, chạy:

~~~bash
javac FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
~~~

Kết quả:

~~~text
JAVA
[LAMBDA]
HELLO
JDK
same
~~~

Giải thích từng thành phần:

1. `TextAction.apply(String)` là phương thức trừu tượng mà lambda và method reference phải triển khai; kiểu trả về là `String`.
2. `upper` sử dụng lambda để biến chuỗi thành chữ hoa. `Locale.ROOT` khiến thao tác minh họa không phụ thuộc locale mặc định của máy.
3. `trim` sử dụng method reference `String::trim`; Java đối chiếu nó với SAM `String apply(String)`. Với một đối số `String`, thao tác tương ứng là gọi `trim()` trên đối số đó.
4. `surround` và `normalized` là các phương thức `default` gọi lại SAM `apply`. Cùng một interface có thể có nhiều phương thức mặc định để cung cấp hành vi tái sử dụng.
5. `identity` là phương thức `static` tạo và trả về một `TextAction` mới; phương thức này không được triển khai bởi lambda ở phía caller.
6. `clean` là phương thức `private static` dùng bên trong interface; nó có thân và không phải SAM.
7. `equals(Object)` là một khai báo phù hợp với `Object` nên không làm SAM tăng lên hai.

`@FunctionalInterface` ở đây giúp phát hiện sớm các thay đổi làm mất hợp đồng SAM. Nếu thêm `String reverse(String text);` mà không cung cấp thân `default`, `TextAction` không còn hợp lệ và mã bị lỗi khi biên dịch.

## 4. Lambda cần kiểu đích (*target type*)

Lambda trong Java **không tự có một kiểu độc lập**; nó cần ngữ cảnh xác định một functional interface. Một biểu thức lambda có thể xuất hiện ở các vị trí như phép gán, truyền đối số, trả về từ phương thức hoặc chuyển kiểu rõ ràng.

~~~java
java.util.function.Function<String, Integer> length = s -> s.length();

java.util.function.Predicate<String> nonBlank =
        s -> s != null && !s.isBlank();

java.util.function.Consumer<String> print =
        text -> System.out.println(text);
~~~

Ba ví dụ trên là những **đoạn mã minh họa đặt trong phương thức**. Các kiểu đích quyết định số tham số, kiểu tham số và kiểu kết quả:

- `Function<String, Integer>` có SAM `Integer apply(String value)`. Lambda nhận một `String` và trả một `Integer` (ở ví dụ, `int` được boxing).
- `Predicate<String>` có SAM `boolean test(String value)`; kết quả phải tương thích với kiểu `boolean`.
- `Consumer<String>` có SAM `void accept(String value)`; nó chỉ thực hiện tác vụ, không yêu cầu kết quả trả về.

Một lambda như `s -> s.length()` **không thể đứng một mình** trong câu lệnh `var f = s -> s.length();`, vì `var` cần suy ra kiểu từ biểu thức khởi tạo và lambda không cung cấp đủ kiểu đích trong trường hợp này.

Khi gọi một phương thức overloaded nhận nhiều loại functional interface, kiểu đích cũng có thể trở nên mơ hồ:

~~~java
// Đoạn minh họa hai overload.
static void use(java.util.function.Supplier<String> supplier) {}
static void use(java.util.concurrent.Callable<String> callable) {}

// use(() -> "ok");  // Lỗi: không chọn được overload chỉ từ lambda.
use((java.util.function.Supplier<String>) () -> "ok");
~~~

Câu lệnh cuối dùng cast để chỉ rõ functional interface. Mỗi interface riêng lẻ đều là hợp lệ; lỗi ở đây đến từ **lựa chọn overload**, không phải từ việc thiếu SAM. Các đoạn mã trong mục này cần đặt trong đúng khai báo lớp/phương thức và không phải file chạy độc lập.

## 5. Các functional interface chuẩn cần nhận ra

Thay vì tạo interface mới cho mọi lambda, Java đã cung cấp nhiều hợp đồng thường dùng.

| Kiểu chuẩn | SAM | Dùng khi |
|---|---|---|
| `Runnable` | `void run()` | Thực hiện công việc không trả kết quả |
| `Callable<V>` | `V call() throws Exception` | Công việc trả kết quả và có thể ném checked exception |
| `Supplier<T>` | `T get()` | Cung cấp hoặc tạo ra một giá trị |
| `Consumer<T>` | `void accept(T value)` | Tiếp nhận giá trị và thực hiện hành động |
| `Function<T, R>` | `R apply(T value)` | Biến đổi giá trị kiểu `T` sang `R` |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi một giá trị nhưng giữ nguyên kiểu |
| `BinaryOperator<T>` | `T apply(T a, T b)` | Kết hợp hai giá trị cùng kiểu thành một giá trị |
| `BiFunction<T, U, R>` | `R apply(T a, U b)` | Biến đổi từ hai đầu vào |
| `Comparator<T>` | `int compare(T a, T b)` | Quy định thứ tự của hai giá trị |

Một số tên phương thức như `Function.apply`, `Predicate.test`, `Consumer.accept` dễ nhầm vì có thể cùng nhận một tham số. Hãy phân biệt chúng bằng **hợp đồng đầu vào/đầu ra** và chức năng thực tế.

Các biến thể chuyên biệt như `IntPredicate`, `IntConsumer`, `IntUnaryOperator`, `ToIntFunction<T>`, `LongSupplier` giúp làm việc với kiểu nguyên thủy và tránh boxing/unboxing không cần thiết trong nhiều tình huống. Sự tối ưu này có ý nghĩa khi xử lý nhiều phần tử hoặc đường mã nóng; không cần chọn kiểu primitive chỉ vì thấy một biểu thức lambda.

### Ví dụ đầy đủ sử dụng nhiều kiểu chuẩn

Lưu file `StandardSamDemo.java`:

~~~java
import java.util.List;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Function;

public class StandardSamDemo {
    public static void main(String[] args) {
        IntUnaryOperator doubleIt = x -> x * 2;
        IntUnaryOperator plusThree = x -> x + 3;
        System.out.println(doubleIt.andThen(plusThree).applyAsInt(4));

        Predicate<String> hasText = s -> s != null && !s.isBlank();
        System.out.println(hasText.test(" "));

        Function<String, Integer> length = String::length;
        System.out.println(length.apply("Java"));

        List<String> words = List.of("aaa", "b", "cc");
        System.out.println(words.stream()
                .sorted((a, b) -> Integer.compare(a.length(), b.length()))
                .toList());
    }
}
~~~

Chạy:

~~~bash
javac StandardSamDemo.java
java StandardSamDemo
~~~

Kết quả:

~~~text
11
false
4
[b, cc, aaa]
~~~

- `IntUnaryOperator.andThen` là phương thức `default` cung cấp cách ghép hai phép biến đổi mà không tạo thêm SAM; với `4`: nhân đôi thành `8` rồi cộng `3` thành `11`.
- `Predicate.test` đánh giá chuỗi chỉ có dấu cách là `false`.
- `String::length` được gán cho `Function<String, Integer>`; phương thức `length()` trả `int`, kết quả được boxing thành `Integer` theo hợp đồng.
- Phương thức `sorted` nhận `Comparator<? super String>`; lambda có hai tham số và trả số âm/0/dương để biểu thị thứ tự theo độ dài.

## 6. Vì sao annotation `@FunctionalInterface` nên được dùng?

Nếu một interface có đúng một SAM, Java cho phép gán lambda **dù không có annotation**. Tuy vậy, nên đánh dấu `@FunctionalInterface` khi tác giả **chủ ý công khai một hợp đồng chức năng**:

~~~java
@FunctionalInterface
interface PriceRule {
    long calculate(long base);
}
~~~

Annotation là một ràng buộc kiểm tra lúc biên dịch. Ví dụ, khi sửa interface trên để thêm `long tax(long base);` dưới dạng trừu tượng, trình biên dịch thông báo rằng `PriceRule` không còn là functional interface. Điều này hữu ích vì những đoạn code đã sử dụng `PriceRule` làm kiểu đích của lambda phụ thuộc vào tính chất SAM đó.

Annotation **không** làm cho code chạy nhanh hơn, không tự sinh phương thức, không áp dụng tính thuần khiết và không cấm phương thức `default`/`static`. Một interface là functional interface dựa trên định nghĩa ngôn ngữ; annotation chỉ xác nhận ý định và yêu cầu trình biên dịch kiểm chứng ý định.

### Trường hợp có lỗi biên dịch

~~~java
// Minh họa lỗi: đừng đặt vào cùng file ví dụ chạy.
@FunctionalInterface
interface InvalidService {
    void start();
    void stop();
}
~~~

Vì `start()` và `stop()` là hai hành vi trừu tượng khác chữ ký, không có một SAM duy nhất. Bỏ `@FunctionalInterface` sẽ cho phép định nghĩa một interface thông thường, nhưng **không** biến nó thành kiểu đích nhận lambda.

Một trường hợp khác cũng sai:

~~~java
// Minh họa lỗi: interface này không có SAM.
@FunctionalInterface
interface DefaultsOnly {
    default void execute() {}
    static void version() {}
}
~~~

Đừng đếm số phương thức viết trong file hoặc số dấu `;`. Hãy xác định chính xác phương thức nào còn là **hợp đồng trừu tượng** cần người triển khai cung cấp.

## 7. Những chi tiết giúp hiểu đúng hợp đồng SAM

### 7.1. Lambda phải khớp tham số và kiểu trả về

SAM quyết định số lượng tham số; lambda có thể viết `(a, b) -> ...` hoặc `a -> ...` tùy số lượng. Với SAM trả `void`, thân lambda phải tương thích với ngữ cảnh `void`; với SAM trả giá trị, biểu thức hoặc các nhánh trả về phải phù hợp kiểu kết quả.

~~~java
Runnable task = () -> System.out.println("done");
java.util.function.BinaryOperator<Integer> sum = (a, b) -> a + b;
java.util.function.Predicate<Integer> even = x -> x % 2 == 0;
~~~

`Runnable` không có tham số; `BinaryOperator<Integer>` có hai tham số và trả `Integer`; `Predicate<Integer>` có một tham số và trả `boolean`. Các ví dụ là đoạn mã để đặt trong phương thức.

### 7.2. Checked exception thuộc hợp đồng của SAM

Nếu phương thức trừu tượng khai báo `throws IOException` thì lambda có thể ném `IOException` tương ứng; nếu SAM không khai báo checked exception tương thích, không thể tùy ý ném nó ra ngoài lambda mà không xử lý.

~~~java
@FunctionalInterface
interface ReaderAction {
    String read(String path) throws java.io.IOException;
}
~~~

`ReaderAction loader = path -> java.nio.file.Files.readString(java.nio.file.Path.of(path));` có thể hợp lệ vì `read` khai báo `throws IOException`. Ngược lại, không thể gán trực tiếp lambda trên cho `Function<String, String>` nếu lambda để checked exception `IOException` thoát ra mà chưa xử lý. Đây là khác biệt ở **hợp đồng phương thức**, không phải ở cú pháp viết lambda.

### 7.3. Biến được capture phải final hoặc effectively final

Lambda được phép sử dụng biến cục bộ của scope bao quanh khi biến đó là `final` hoặc **effectively final** (không bị gán lại sau khi khởi tạo).

~~~java
int factor = 3;
java.util.function.IntUnaryOperator multiply = x -> x * factor;
~~~

Nếu sau đó gán lại `factor = 4;` trong cùng phương thức, lambda sẽ không còn hợp lệ vì `factor` không effectively final. Nhưng điều đó **không có nghĩa** đối tượng được capture luôn bất biến:

~~~java
java.util.List<String> captured = new java.util.ArrayList<>();
java.util.function.Consumer<String> addItem = item -> captured.add(item);
~~~

Biến `captured` không bị gán lại; lambda vẫn sửa nội dung danh sách. Khả năng gán lambda cho functional interface không tự bảo đảm tính thuần khiết, thread-safety hoặc không có tác dụng phụ.

### 7.4. Cách hiểu kế thừa, generic và interface giao nhau

- Functional interface có thể khai báo bằng generic, ví dụ `interface Mapper<T, R> { R map(T value); }`. Kiểu `Mapper<String, Integer>` xác định SAM nhận `String` và trả `Integer`.
- Interface con kế thừa đúng một hợp đồng abstract có thể tiếp tục là functional interface; phương thức `default` bổ sung vẫn được phép.
- Nếu kế thừa nhiều phương thức trừu tượng có chữ ký tương ứng và kết quả tương thích, Java có thể xem chúng cùng biểu diễn một hợp đồng. Trường hợp chữ ký hoặc kiểu kết quả không tương thích có thể làm interface không hợp lệ hoặc không còn functional interface.
- Không nên dự đoán tính hợp lệ chỉ bằng số dòng `interface`; để `@FunctionalInterface` và trình biên dịch kiểm tra các trường hợp kế thừa phức tạp.

### 7.5. Lambda khác anonymous class ở ngữ cảnh `this`

Lambda không tạo một phạm vi `this` riêng như anonymous class. Bên trong lambda, `this` (nếu hợp lệ) tham chiếu đối tượng bao ngoài; trong anonymous class, `this` tham chiếu instance của anonymous class. Lambda cũng không tạo một subclass riêng cho interface như cách viết `new SomeInterface() { ... }`. Khi code cần trạng thái instance riêng cho từng hành vi, một lớp triển khai hoặc anonymous class có thể diễn đạt ý định rõ hơn.

## 8. Khi nào tự định nghĩa functional interface?

**Ưu tiên kiểu chuẩn** khi hợp đồng đơn giản đúng với `Function`, `Predicate`, `Consumer`, `Supplier`, v.v. Chẳng hạn, một thao tác chuyển chuỗi thành số có thể dùng `Function<String, Integer>`; việc tạo `interface StringToNumber { int convert(String s); }` chỉ vì muốn truyền lambda thường không cần thiết.

**Tự định nghĩa interface có SAM** khi tên miền nghiệp vụ, checked exception, chữ ký đặc biệt hoặc phương thức `default` bổ trợ giúp hợp đồng dễ hiểu:

~~~java
@FunctionalInterface
interface RetryDecision {
    boolean shouldRetry(int attempt, Throwable failure);
}
~~~

Tên `RetryDecision` và tham số `attempt`, `failure` mô tả ý nghĩa rõ hơn một `BiPredicate<Integer, Throwable>` chung chung. Có thể truyền lambda `(attempt, failure) -> attempt < 3`, nhưng logic quyết định retry còn phải phù hợp với chính sách nghiệp vụ, giới hạn và loại lỗi thực tế. Interface này là một **hợp đồng hành vi**; phần quyết định có thuần hay không tùy triển khai.

Trong API công khai, một interface chuyên biệt cũng giúp bổ sung các phương thức `default` liên quan mà vẫn giữ SAM. Tuy nhiên, thay đổi chữ ký SAM có thể phá vỡ những lambda và method reference đang dùng API đó; hãy cân nhắc tương thích khi phát hành thư viện.

## 9. Lỗi phổ biến khi học functional interface

1. **Cho rằng có `@FunctionalInterface` mới dùng được lambda.** Thực tế interface chỉ cần thỏa điều kiện SAM. Annotation giúp bảo vệ ý định.
2. **Cho rằng đúng một phương thức tổng cộng.** `default`, `static`, `private` có thân không được đếm; một số phương thức tương đương `Object` cũng không được đếm.
3. **Cho rằng hai khai báo trừu tượng luôn có hai SAM.** Nếu chúng cùng là một hợp đồng sau quy tắc override, có thể vẫn là functional interface. Trường hợp kế thừa phức tạp hãy dựa vào biên dịch.
4. **Thêm phương thức trừu tượng mới vào API đã có lambda.** Làm mất tính chất SAM, gây lỗi compile ở nơi sử dụng.
5. **Nhầm kiểu hàm với lambda.** Kiểu đích là functional interface; lambda cung cấp cách thực hiện SAM.
6. **Nhầm method reference với một API khác.** `String::trim` không phải functional interface, chỉ là biểu thức tham chiếu đến phương thức được gán dựa trên một kiểu đích tương thích.
7. **Không xét checked exception của SAM.** Lambda dùng I/O có thể cần interface khai báo `throws` hoặc phải tự xử lý lỗi.
8. **Đoán kiểu lambda trong mọi biểu thức.** Overload có nhiều kiểu đích khả dĩ có thể mơ hồ; dùng biến đã định kiểu hoặc cast rõ ràng.
9. **Cho rằng lambda đương nhiên thuần và an toàn khi chạy song song.** Lambda vẫn có thể sửa dữ liệu capture hoặc thực hiện I/O; đây là vấn đề hành vi, không phải tiêu chí xác định SAM.

## 10. Checklist và câu hỏi tự kiểm tra

Khi thấy một interface định dùng với lambda, hãy tự hỏi:

- Sau khi xét kế thừa và bỏ qua các phương thức không được đếm, **SAM nào** là hợp đồng thực sự?
- Số lượng/kiểu tham số, kiểu trả về và `throws` của SAM là gì?
- Phương thức `default` nào có thể hỗ trợ thao tác thường dùng mà vẫn giữ một SAM?
- Có nên thêm `@FunctionalInterface` để bảo đảm hợp đồng khi bảo trì?
- Kiểu chuẩn đã đủ diễn đạt chưa, hay cần một tên miền nghiệp vụ riêng?
- Lambda hoặc method reference tại vị trí sử dụng có khớp kiểu đích, và có tác dụng phụ nào cần lưu ý?

**Bài tập nhỏ:** Cho biết các interface sau có thể nhận lambda hay không, và giải thích:

~~~java
interface A {
    void execute();
}

interface B {
    void execute();
    default void reset() {}
}

interface C {
    void execute();
    int status();
}

interface D {
    String toString();
    int hashCode();
    void execute();
}
~~~

**Đáp án:** `A` có SAM `execute()`; `B` cũng có SAM `execute()` vì `reset()` là `default`; `C` có hai phương thức trừu tượng khác nhau nên không nhận lambda; `D` có SAM `execute()` vì `toString()` và `hashCode()` tương đương các phương thức `public` của `Object` nên không được tính.

**Ghi nhớ:** Một functional interface được nhận diện bởi **hợp đồng trừu tượng duy nhất sau khi áp dụng quy tắc ngôn ngữ**, không phải bởi số phương thức trông thấy trong source. `@FunctionalInterface` xác nhận ý định, còn lambda/method reference cung cấp hành vi cho SAM trong ngữ cảnh kiểu đích.