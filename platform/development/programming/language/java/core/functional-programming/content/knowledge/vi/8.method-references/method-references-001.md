# Method reference và quan hệ tương đương với lambda trong Java

## 1. Method reference là gì?

**Method reference** (tham chiếu phương thức) là biểu thức dạng `::` dùng để chỉ một phương thức hoặc constructor đã tồn tại và chuyển nó thành cách triển khai cho **functional interface**. Thay vì viết một lambda chỉ để gọi một phương thức khác, ta có thể tham chiếu trực tiếp đến phương thức đó.

Ví dụ, hai biểu thức dưới đây có cùng ý nghĩa đối với tham số `String`:

~~~java
Function<String, String> a = s -> s.trim();
Function<String, String> b = String::trim;
~~~

Cả `a.apply("  Java  ")` và `b.apply("  Java  ")` đều trả về `"Java"`. Tuy nhiên, `String::trim` không tự gọi `trim()` ngay tại chỗ khai báo: nó tạo một giá trị có kiểu là functional interface, để phương thức được gọi khi phương thức trừu tượng duy nhất (SAM) của interface được thực thi.

Phạm vi bài này là **mối quan hệ giữa method reference và lambda**: cách chuyển đổi, cách compiler gắn tham số, những trường hợp tương đương và những khác biệt quan trọng. Lambda, functional interface và Stream API được dùng làm ngữ cảnh minh họa.

## 2. Kiểu đích quyết định method reference có hợp lệ hay không

Java không có một kiểu “method reference” độc lập để lưu trữ. Giống lambda, method reference là **poly expression**: compiler phải biết *target type* là functional interface, chẳng hạn `Function<T,R>`, `Consumer<T>`, `Supplier<T>`, `Predicate<T>`, `Comparator<T>` hay interface do ta định nghĩa.

- `Function<String, Integer>` có SAM `Integer apply(String s)`: nhận một `String`, trả `Integer`.
- `ToIntFunction<String>` có SAM `int applyAsInt(String s)`: nhận một `String`, trả `int`.
- `Consumer<String>` có SAM `void accept(String s)`: nhận một `String`, không cần nhận giá trị trả về.
- `Supplier<List<String>>` có SAM `List<String> get()`: không nhận tham số, trả một danh sách.

Ví dụ:

~~~java
Function<String, Integer> parse = Integer::parseInt;
ToIntFunction<String> length = String::length;
Consumer<String> print = System.out::println;
Supplier<List<String>> createList = ArrayList::new;
~~~

`Integer::parseInt` chọn overload tương thích với `String -> Integer` (giá trị `int` được boxing thành `Integer`). `String::length` nhận một đối tượng `String` làm receiver và trả `int`. `System.out::println` đã gắn receiver là luồng in cụ thể. `ArrayList::new` gọi constructor khi `get()` được gọi.

Lưu ý: các đoạn ví dụ này giả định có `import java.util.*;` và `import java.util.function.*;`; chương trình hoàn chỉnh ở phần 5 có thể biên dịch độc lập.

## 3. Bốn dạng method reference và lambda tương ứng

### 3.1. Phương thức `static`: `TypeName::staticMethod`

~~~java
Function<String, Integer> ref = Integer::parseInt;
Function<String, Integer> lambda = s -> Integer.parseInt(s);
~~~

Ở đây tham số SAM `s` được truyền thành đối số đầu tiên cho phương thức static. Nếu phương thức có nhiều tham số, chúng được chuyển theo thứ tự tương ứng:

~~~java
BinaryOperator<Integer> maxRef = Math::max;
BinaryOperator<Integer> maxLambda = (a, b) -> Math.max(a, b);
~~~

Kiểu đích giúp compiler chọn overload; không thể hiểu một tham chiếu overload chỉ bằng cách nhìn tên phương thức mà bỏ qua chữ ký SAM.

### 3.2. Phương thức của một đối tượng đã biết: `expression::instanceMethod`

~~~java
Consumer<String> ref = System.out::println;
Consumer<String> lambda = value -> System.out.println(value);
~~~

Đây là **bound receiver**: biểu thức bên trái `::` được đánh giá khi *tạo* method reference, và đối tượng nhận được được giữ làm receiver cho các lần gọi sau. Với `System.out::println`, không cần thêm tham số receiver trong SAM; `accept(value)` chuyển `value` cho `println(value)` trên luồng in đã bắt.

Một ví dụ khác:

~~~java
String prefix = "Hello ";
Function<String, String> ref = prefix::concat;
Function<String, String> lambda = suffix -> prefix.concat(suffix);
~~~

Trong ví dụ này, `apply("Java")` của cả hai cho `"Hello Java"`. Các biến cục bộ được lambda bắt phải final hoặc *effectively final*; hãy xem thêm khác biệt về **thời điểm đánh giá receiver** ở phần 6.

### 3.3. Phương thức instance chưa gắn đối tượng: `ReferenceType::instanceMethod`

~~~java
ToIntFunction<String> ref = String::length;
ToIntFunction<String> lambda = s -> s.length();
~~~

Đây là **unbound receiver**: chính tham số đầu tiên của SAM cung cấp đối tượng receiver. Các tham số còn lại của SAM lần lượt là đối số thực của phương thức.

~~~java
Comparator<String> ref = String::compareToIgnoreCase;
Comparator<String> lambda = (left, right) -> left.compareToIgnoreCase(right);
~~~

`Comparator.compare(left, right)` có hai tham số: `left` làm receiver của `compareToIgnoreCase`, `right` được truyền vào phương thức. Vì vậy, **không** thể suy luận nhầm thành cách gọi static `String.compareToIgnoreCase(left, right)`.

### 3.4. Constructor và array constructor: `TypeName::new`

~~~java
Supplier<ArrayList<String>> listRef = ArrayList::new;
Supplier<ArrayList<String>> listLambda = () -> new ArrayList<>();

Function<char[], String> textRef = String::new;
Function<char[], String> textLambda = chars -> new String(chars);

IntFunction<String[]> arrayRef = String[]::new;
IntFunction<String[]> arrayLambda = n -> new String[n];
~~~

Constructor reference không tạo đối tượng tại thời điểm khai báo biến `listRef`, `textRef` hoặc `arrayRef`; đối tượng/mảng được tạo khi gọi SAM. Constructor overload nào được chọn phụ thuộc kiểu tham số và giá trị trả về của SAM. Với `String[]::new`, `n` là chiều dài mảng.

## 4. “Tương đương với lambda” phải hiểu đến mức nào?

Về mặt **ánh xạ tham số tới một lời gọi phương thức**, mỗi dạng trên có biểu thức lambda diễn tả cùng thao tác. Chẳng hạn:

| Method reference | Lambda diễn đạt lời gọi | Cách ghép tham số |
| --- | --- | --- |
| `Integer::parseInt` | `s -> Integer.parseInt(s)` | Tất cả tham số vào phương thức static |
| `printer::println` | `s -> printer.println(s)` | Receiver đã được gắn, `s` là đối số |
| `String::length` | `s -> s.length()` | `s` làm receiver |
| `String::compareToIgnoreCase` | `(a, b) -> a.compareToIgnoreCase(b)` | `a` làm receiver, `b` làm đối số |
| `ArrayList::new` | `() -> new ArrayList<>()` | Gọi constructor không tham số |
| `String[]::new` | `n -> new String[n]` | `n` là độ dài mảng |

**Không có nghĩa** rằng thay thế cú pháp giữa hai dạng lúc nào cũng giữ nguyên toàn bộ hành vi chương trình. Cần xét thời điểm đánh giá receiver, tình trạng `null`, overload, target type, exception và những thao tác bổ sung trong thân lambda. Method reference chỉ là cách gọn để ủy quyền cho một phương thức/constructor; nó không thay thế mọi lambda.

## 5. Ví dụ Java 17+ chạy hoàn chỉnh

Lưu tệp thành `MethodReferenceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

public class MethodReferenceDemo {
    public static void main(String[] args) {
        // Unbound instance method: s -> s.trim()
        Function<String, String> withLambda = s -> s.trim();
        Function<String, String> withReference = String::trim;
        System.out.println("lambda=" + withLambda.apply("  Java  "));
        System.out.println("ref=" + withReference.apply("  Java  "));

        List<String> words = List.of("  Java  ", "  Lambda  ", "  API  ");
        System.out.println(words.stream().map(String::trim).toList());

        ToIntFunction<String> lengthLambda = s -> s.length();
        ToIntFunction<String> lengthReference = String::length;
        System.out.println(
                lengthLambda.applyAsInt("Java")
                        == lengthReference.applyAsInt("Java"));

        // Receiver đầu tiên của Comparator trở thành receiver của phương thức.
        List<String> names = new ArrayList<>(List.of("zoe", "Ana", "bob"));
        Comparator<String> ignoreCase = String::compareToIgnoreCase;
        names.sort(ignoreCase);
        System.out.println(names);

        // Constructor reference: () -> new ArrayList<String>()
        Supplier<List<String>> create = ArrayList::new;
        List<String> result = create.get();
        result.add("ok");
        System.out.println(result);

        IntFunction<String[]> createArray = String[]::new;
        System.out.println(createArray.apply(3).length);

        // Bound instance method: s -> System.out.println(s)
        Consumer<String> printer = System.out::println;
        printer.accept("done");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MethodReferenceDemo.java
java MethodReferenceDemo
~~~

Kết quả chuẩn (stdout):

~~~text
lambda=Java
ref=Java
[Java, Lambda, API]
true
[Ana, bob, zoe]
[ok]
3
done
~~~

Giải thích: `map(String::trim)` tương đương với `map(s -> s.trim())` cho từng phần tử nguồn, rồi `toList()` tạo danh sách kết quả. `String::compareToIgnoreCase` thể hiện cách gán receiver từ tham số thứ nhất của `Comparator`. `ArrayList::new` tạo danh sách mới khi gọi `get()`; `String[]::new` tạo mảng khi gọi `apply(3)`. `System.out::println` là phương thức instance đã gắn receiver.

## 6. Các khác biệt ngữ nghĩa cần nhớ

### 6.1. Đánh giá receiver ngay khi tạo bound reference

Xét chương trình độc lập `CaptureTimingDemo.java`:

~~~java
import java.util.function.Supplier;

public class CaptureTimingDemo {
    private static int calls;

    private static Greeter makeGreeter() {
        calls++;
        return new Greeter("Hi");
    }

    private record Greeter(String message) {
        String say() {
            return message;
        }
    }

    public static void main(String[] args) {
        Supplier<String> ref = makeGreeter()::say;
        Supplier<String> lambda = () -> makeGreeter().say();

        System.out.println("after creation=" + calls);
        System.out.println(ref.get());
        System.out.println("after reference=" + calls);
        System.out.println(lambda.get());
        System.out.println("after lambda=" + calls);
    }
}
~~~

~~~bash
javac CaptureTimingDemo.java
java CaptureTimingDemo
~~~

~~~text
after creation=1
Hi
after reference=1
Hi
after lambda=2
~~~

`makeGreeter()::say` gọi `makeGreeter()` **một lần lúc tạo reference**; `ref.get()` chỉ gọi `say()` trên receiver đã lưu. `() -> makeGreeter().say()` gọi `makeGreeter()` **mỗi lần gọi lambda**. Vì vậy, khi expression bên trái `::` có side effect hoặc trả các đối tượng khác nhau, hai biểu thức không tương đương hoàn toàn.

Nếu receiver tham chiếu đến **cùng một đối tượng mutable**, cả method reference và lambda vẫn quan sát trạng thái mới của chính đối tượng đó khi method chạy; “gắn receiver” không có nghĩa là chụp bản sao trạng thái đối tượng.

### 6.2. `null` và thời điểm phát sinh lỗi

~~~java
String s = null;
Supplier<String> delayed = () -> s.toString(); // Tạo lambda thành công.
// delayed.get();                            // NullPointerException khi gọi SAM.
// Supplier<String> immediate = s::toString; // NullPointerException ngay ở dòng này.
~~~

Với bound reference `s::toString`, receiver `s` phải khác `null` ngay khi đánh giá biểu thức tham chiếu. Với lambda `() -> s.toString()`, thân lambda chỉ được chạy khi `get()` được gọi. Còn unbound reference `String::toString` có thể được tạo mà không cần receiver hiện hữu; lỗi xảy ra nếu sau đó gọi `apply` với `null` theo cách dẫn đến lời gọi instance.

### 6.3. Lambda có thể chứa nhiều thao tác; reference chỉ trỏ tới lời gọi tương thích

~~~java
Function<String, String> normalize = s -> s.trim().toUpperCase();
Predicate<String> valid = s -> s != null && !s.isBlank();
~~~

Không có một method reference đơn lẻ tương đương trực tiếp với toàn bộ phép biến đổi `trim` rồi `toUpperCase` hoặc phép kiểm tra hai điều kiện như trên, trừ khi ta định nghĩa một phương thức chứa logic đó rồi tham chiếu đến nó. Lambda cũng dễ đặt breakpoint, viết nhiều câu lệnh, bắt lỗi cục bộ hoặc xử lý đặc biệt.

### 6.4. Overload, generics và kiểu đích

~~~java
Function<String, Integer> parse = Integer::parseInt;
ToIntFunction<String> parsePrimitive = Integer::parseInt;
~~~

Cùng tên phương thức nhưng hai kiểu đích mang kiểu kết quả khác nhau (boxing cần thiết cho `Function`). Khi overload phức tạp, compiler sử dụng chữ ký SAM và quy tắc chọn overload để xác định method tương thích; đôi khi cần khai báo kiểu cụ thể hoặc dùng lambda để làm rõ.

Một method reference không tự động hợp lệ với mọi functional interface. Ví dụ, `String::length` hợp lệ với `ToIntFunction<String>`, nhưng **không** phù hợp với `Supplier<Integer>` vì `Supplier.get()` không cung cấp `String` làm receiver.

### 6.5. Checked exception, return và kiểu `void`

Cả lambda lẫn method reference đều phải tuân thủ kiểu tham số, kết quả và tập checked exception cho phép bởi SAM. Một method reference trỏ đến phương thức khai báo `throws IOException` không thể dùng trực tiếp cho `Function<String, String>` nếu lời gọi cần xử lý `IOException`, bởi `Function.apply` không khai báo checked exception đó. Hãy dùng interface phù hợp hoặc lambda có `try/catch` khi cần.

Java có thể bỏ qua giá trị trả về của một lời gọi trong ngữ cảnh SAM trả `void` nếu lời gọi thích hợp làm statement expression; tuy vậy không được tự suy rằng mọi chữ ký trả về đều thích hợp. Compiler là nguồn quyết định tính tương thích.

## 7. Khi nào nên chọn method reference, khi nào chọn lambda?

Nên chọn **method reference** khi toàn bộ thân lambda chỉ chuyển tiếp tham số tới một phương thức hoặc constructor có tên rõ nghĩa, ví dụ `map(String::trim)`, `forEach(System.out::println)`, `sort(String::compareToIgnoreCase)` hay `Supplier<List<String>> factory = ArrayList::new`. Cú pháp này thể hiện trực tiếp ý định sử dụng thao tác đã có.

Nên chọn **lambda** khi cần nối nhiều bước, kiểm tra `null`, đổi thứ tự hoặc chuyển đổi tham số, diễn đạt điều kiện phức tạp, xử lý ngoại lệ, hoặc khi reference khiến người đọc khó xác định receiver/overload. Ví dụ `stream.map(s -> s == null ? "" : s.trim())` biểu đạt chính sách riêng mà `String::trim` không tự cung cấp.

Một cách chuyển đổi an toàn:

1. Xác định functional interface và chữ ký SAM thực tế.
2. Viết lời gọi lambda rõ tham số, receiver, kiểu trả về và checked exception.
3. Đối chiếu một trong bốn dạng `::`, chú ý với instance method *unbound* thì tham số SAM đầu tiên là receiver.
4. Xem có thay đổi thời điểm đánh giá receiver, hành vi khi `null` hay side effect hay không.
5. Chỉ rút gọn thành method reference nếu bản mới vẫn đúng ý định và dễ đọc.

## 8. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai hoặc dễ gây nhầm | Cách sửa |
| --- | --- | --- |
| Viết `String::trim()` | `::` tham chiếu tên phương thức, không gọi phương thức ngay | Dùng `String::trim` |
| Gán `String::length` cho `Supplier<Integer>` | SAM không nhận receiver `String` | Dùng `ToIntFunction<String>` hoặc `Function<String,Integer>` |
| Cho rằng `String::compareToIgnoreCase` là static | Đây là unbound instance method | Hiểu `(a,b) -> a.compareToIgnoreCase(b)` |
| Nghĩ `obj::method` đánh giá `obj` lúc gọi SAM | Bound receiver được đánh giá lúc tạo reference | Kiểm tra side effect và `null` trước khi thay thế lambda |
| Giả định có thể đổi mọi lambda thành `::` | Lambda có thể làm nhiều thao tác | Giữ lambda hoặc tách logic thành method đặt tên rõ ràng |
| Bỏ qua overload hoặc exception | Target type quyết định method được chọn và tính hợp lệ | Khai báo rõ kiểu SAM; xử lý exception đúng chữ ký |

## 9. Tự kiểm tra

**Câu 1.** `Function<String, String> f = String::toUpperCase;` tương ứng lambda nào?

Đáp án: `s -> s.toUpperCase()`. Đây là unbound instance method; `s` là receiver.

**Câu 2.** `BiFunction<String, String, Boolean> f = String::startsWith;` có hợp lệ không?

Đáp án: có. Tham số thứ nhất là receiver `String`; tham số thứ hai là tiền tố. Lambda tương ứng là `(s, prefix) -> s.startsWith(prefix)`; giá trị `boolean` được boxing thành `Boolean` cho `BiFunction`.

**Câu 3.** Với `Supplier<String> a = makeGreeter()::say;` và `Supplier<String> b = () -> makeGreeter().say();`, phương án nào gọi `makeGreeter()` ngay lúc khai báo?

Đáp án: `a`. `b` chỉ gọi `makeGreeter()` khi `get()` chạy.

**Câu 4.** Vì sao `String::trim` không tương đương trực tiếp với `s -> s == null ? "" : s.trim()`?

Đáp án: lambda có nhánh xử lý `null`, còn lời gọi `trim()` trên receiver `null` sẽ ném `NullPointerException`.

## Ghi nhớ

Method reference là **cú pháp cô đọng của một lời gọi có thể thích ứng với functional interface**, trong khi lambda diễn đạt một hàm bằng danh sách tham số và thân thực thi. Quan hệ tương đương chỉ đúng khi kiểu đích, ánh xạ tham số, receiver, thời điểm đánh giá, ngoại lệ và các hiệu ứng quan sát được đều phù hợp. Hiểu rõ bốn dạng `Type::staticMethod`, `object::instanceMethod`, `Type::instanceMethod` và `Type::new` giúp đọc và viết Java functional code chính xác.
