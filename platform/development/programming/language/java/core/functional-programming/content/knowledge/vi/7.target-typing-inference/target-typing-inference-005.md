# Suy luận generic khi truyền lambda vào phương thức Java

## 1. Vấn đề: tại sao có thể bỏ kiểu tham số lambda?

Khi gọi phương thức tổng quát (*generic method*), Java thường tự suy luận các tham số kiểu như `T`, `R`, thay vì bắt người gọi viết rõ `<String, Integer>`. Nếu đối số là biểu thức lambda, trình biên dịch còn phải xác định **kiểu của các tham số lambda** và **kiểu trả về của phần thân lambda**. Hai việc này hỗ trợ lẫn nhau.

Xét phương thức:

```java
static <T, R> R convert(T input, Function<T, R> converter) {
    return converter.apply(input);
}
```

Đây là phương thức minh họa cần đặt trong một lớp và import `java.util.function.Function`. Tại lời gọi:

```java
int length = convert("Java", text -> text.length());
```

Trình biên dịch suy luận `T` từ đối số `"Java"` (kiểu `String`). Do đó lambda có kiểu đích (*target type*) phù hợp với `Function<String, R>`, khiến `text` được hiểu là `String`. Thân `text.length()` cho kết quả `int`, tương thích với kiểu tham chiếu `Integer` qua boxing; kết quả có thể gán vào `int length` qua unboxing. Ở ví dụ này, `R` được suy luận phù hợp với `Integer`, và kết quả là `4`.

Điều quan trọng: **lambda không được biên dịch như một hàm độc lập rồi mới gắn kiểu vào sau**. Nó là một *poly expression*: tính hợp lệ và cách suy luận tham số phụ thuộc vào kiểu đích của ngữ cảnh.

Mục tiêu bài học: hiểu luồng suy luận kiểu khi truyền lambda vào generic method; viết đúng kiểu ràng buộc `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`; nắm vai trò của kết quả mong đợi, wildcard, tham chiếu phương thức và cách xử lý lỗi trình biên dịch.

## 2. Ba nguồn ràng buộc khi suy luận kiểu

Với chữ ký `<T, R> R convert(T input, Function<T, R> converter)`, trình biên dịch không đoán tùy ý. Nó giải các ràng buộc tương thích từ nhiều vị trí.

| Nguồn ràng buộc | Ví dụ | Tác dụng |
| --- | --- | --- |
| Đối số thông thường | `convert("Java", ...)` | Giới hạn `T` theo kiểu của `"Java"` |
| Tham số phương thức chức năng | `Function<T,R>` | Cung cấp kiểu đích để kiểm tra tham số lambda |
| Phần thân lambda | `text -> text.length()` | Kiểm tra `length()` hợp lệ trên `String`, ràng buộc `R` từ kết quả |
| Ngữ cảnh kết quả | `Integer n = convert(...)` | Đặt yêu cầu tương thích lên kiểu trả về của lời gọi |
| Các đối số khác | `combine(3, 4, (a,b) -> a+b)` | Ràng buộc cùng một `T` ở hai đối số và lambda |

Không phải lúc nào một ràng buộc cũng dẫn đến một kiểu duy nhất ngay lập tức. Java xử lý các ràng buộc theo quy tắc *type inference* (JLS §18), xét boxing/unboxing, subtype và tính tương thích của biểu thức. Kiểu kết quả được quyết định bởi toàn bộ lời gọi, không nhất thiết chỉ theo một đối số hay theo kiểu của phép tính trong lambda.

Cách hiểu thực hành: **đọc chữ ký phương thức → xem các đối số rõ kiểu → xác định kiểu đích lambda → kiểm tra phần thân → đối chiếu kiểu kết quả**.

## 3. Kiểu đích của lambda đến từ tham số generic

Một lambda như `s -> s.length()` không tự nói `s` có kiểu gì. Khi nó được truyền vào tham số `Function<T,R>` của `convert`, ngữ cảnh tạo ra kiểu đích thích hợp.

```java
static <T, R> R convert(T input, Function<T, R> fn) {
    return fn.apply(input);
}

// Trong main:
Integer size = convert("Hello", s -> s.length());
```

Khi dùng trong một lớp đã import `java.util.function.Function`, `s` ở lambda được hiểu là `String`. Java biết `String` có `length()`. Kiểu kết quả `Integer` tương thích với giá trị `int` được boxing.

Phân biệt với lời gọi sau:

```text
String wrong = convert("Java", s -> s.length());
```

Đây là **ví dụ cố ý không biên dịch** với chữ ký `convert` đã nêu: kết quả lambda là độ dài `int`/boxed `Integer`, trong khi kết quả được yêu cầu là `String`. Trình biên dịch có thể báo `inference variable R has incompatible bounds` (các ràng buộc `R` không tương thích).

Không nên “sửa” bằng cách ép `String` một cách tùy tiện. Hãy chọn kiểu mong đợi đúng (`Integer`, `int`) hoặc đổi phép biến đổi trả `String`.

## 4. Lambda không có kiểu đích độc lập

Những câu lệnh sau phải được đặt trong ngữ cảnh có kiểu đích:

```java
Function<String, Integer> count = s -> s.length();
IntUnaryOperator increment = n -> n + 1;
```

Nếu muốn dùng trực tiếp các lệnh này trong phương thức, import `Function` và `IntUnaryOperator` từ `java.util.function`.

Tương phản:

```text
var count = s -> s.length(); // Sai: không có target type cho lambda
```

`var` dùng để suy luận kiểu biến cục bộ, nhưng không thể tự tạo kiểu giao diện hàm từ một lambda đứng độc lập. Tuy nhiên, **`var` có thể nhận kết quả của lời gọi generic method** nếu phương thức và các đối số cung cấp đủ ràng buộc:

```java
var size = convert("Java", s -> s.length());
```

Trong trường hợp này, lời gọi `convert` có chữ ký giúp xác định lambda và kết quả; `var` chỉ nhận kiểu đã suy luận của biểu thức gọi phương thức.

Cần phân biệt thêm `(var s) -> s.length()` (dùng `var` trong danh sách tham số lambda, Java 11+) với `var f = s -> ...` (suy luận kiểu biến nhận lambda). Dạng thứ nhất vẫn cần kiểu đích `Function<String,Integer>` hoặc tương tự.

## 5. Ví dụ đầy đủ Java 17: nhiều loại generic method

Lưu toàn bộ nội dung vào tệp `GenericLambdaInferenceDemo.java`:

```java
import java.util.*;
import java.util.function.*;

public class GenericLambdaInferenceDemo {
    static <T, R> R convert(T input, Function<T, R> fn) {
        return fn.apply(input);
    }

    static <T, R> List<R> map(
            List<T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    static <T> List<T> filter(
            List<T> source,
            Predicate<? super T> test) {
        List<T> result = new ArrayList<>();
        for (T item : source) {
            if (test.test(item)) {
                result.add(item);
            }
        }
        return result;
    }

    static <T> T supply(Supplier<T> fn) {
        return fn.get();
    }

    static <T> T combine(T a, T b, BinaryOperator<T> fn) {
        return fn.apply(a, b);
    }

    static <T> void consume(T input, Consumer<? super T> fn) {
        fn.accept(input);
    }

    static <T, R> List<R> streamMap(
            List<T> source,
            Function<? super T, ? extends R> mapper) {
        return source.stream().<R>map(mapper).toList();
    }

    static <T> Function<T, String> describe(String prefix) {
        return item -> prefix + item;
    }

    static <T, U> Function<T, U> chain(Function<T, U> f) {
        return f;
    }

    public static void main(String[] args) {
        int len = convert("Java", s -> s.length());
        System.out.println(len);

        List<Integer> lengths =
                map(List.of("An", "Binh", "Chi"), s -> s.length());
        System.out.println(lengths);

        System.out.println(
                filter(List.of(2, 3, 4, 5), n -> n % 2 == 0));

        String label = supply(() -> "ready");
        System.out.println(label);

        int total = combine(3, 4, (x, y) -> x + y);
        System.out.println(total);

        consume("java",
                s -> System.out.println(s.toUpperCase(Locale.ROOT)));

        System.out.println(
                GenericLambdaInferenceDemo.<String, Integer>convert(
                        "Hello", s -> s.length()));

        List<Number> values = map(
                List.of(1, 2, 3), n -> n.doubleValue() + 0.5);
        System.out.println(values);

        System.out.println(
                streamMap(List.of("A", "BB"), String::length));

        Function<Integer, String> printer =
                GenericLambdaInferenceDemo.<Integer>describe("num=");
        System.out.println(printer.apply(5));

        System.out.println(
                chain((String s) -> s + "!").apply("Hi"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 GenericLambdaInferenceDemo.java
java GenericLambdaInferenceDemo
```

Kết quả:

```text
4
[2, 4, 3]
[2, 4]
ready
7
JAVA
5
[1.5, 2.5, 3.5]
[1, 2]
num=5
Hi!
```

Các cơ chế đáng chú ý trong chương trình:

1. `convert("Java", s -> s.length())`: đối số `String` hướng suy luận `T`, lambda xác định chuyển đổi sang `Integer`.
2. `map(List.of(...), s -> s.length())`: các phần tử nguồn hướng suy luận `T=String`; `List<Integer>` đích và kết quả lambda hướng suy luận `R=Integer`.
3. `filter(List.of(...), n -> n % 2 == 0)`: `Predicate<? super T>` phải trả `boolean`; nguồn là `Integer`, danh sách kết quả vẫn chứa `Integer`.
4. `String label = supply(() -> "ready")`: lambda không nhận tham số; kiểu trả về `String` góp phần suy luận `T`.
5. `combine(3,4,(x,y)->x+y)`: hai giá trị và `BinaryOperator<T>` cùng ràng buộc kiểu `T`, kết quả in ra `7`.
6. `consume("java", s -> ...)`: `Consumer<? super T>` nhận dữ liệu và trả `void`; `T` được suy luận từ đối số chuỗi.
7. `GenericLambdaInferenceDemo.<String, Integer>convert(...)`: **type witness** (*chỉ định tham số kiểu tường minh*) cho phép kiểm chứng hoặc làm rõ hai tham số kiểu. Bình thường Java có thể tự suy luận.
8. `List<Number> values = map(List.of(1,2,3), n -> n.doubleValue()+0.5)`: đầu ra là `Double`, vẫn tương thích với `Number` vì `Double` là kiểu con của `Number`.
9. `streamMap(..., String::length)`: tham chiếu phương thức là một biểu thức có kiểu đích tương tự lambda, và phương thức generic của `Stream` cần truyền kiểu đầu ra rõ ràng trong cách triển khai này.
10. `GenericLambdaInferenceDemo.<Integer>describe("num=")`: ở đây kiểu `T` **không xuất hiện trong đối số** `String prefix`; chỉ định `<Integer>` giúp tạo `Function<Integer,String>`.
11. `chain((String s) -> s + "!")`: kiểu tham số lambda được viết rõ `String` khi truyền vào phương thức generic, cho phép suy luận `T=String`, `U=String`.

## 6. Khi kiểu T chỉ xuất hiện trong lambda

Xét phương thức:

```java
static <T> Function<T, String> describe(String prefix) {
    return item -> prefix + item;
}
```

Đoạn này minh họa định nghĩa phương thức trong một lớp có import `Function`. `T` xuất hiện **chỉ ở kiểu trả về** `Function<T,String>`, không xuất hiện trong tham số thường `String prefix`. Khi dùng:

```java
Function<Integer, String> printer = describe("num=");
System.out.println(printer.apply(5)); // num=5
```

Ngữ cảnh gán giúp suy luận `T=Integer`. Nếu muốn tránh phụ thuộc nhiều vào ngữ cảnh, có thể viết:

```java
Function<Integer, String> printer = MyClass.<Integer>describe("num=");
```

Đây là minh họa; đổi `MyClass` thành tên lớp thực chứa phương thức (ví dụ `GenericLambdaInferenceDemo` ở chương trình hoàn chỉnh). **Không nên đoán `T` từ chuỗi `"num="`**: nó là dữ liệu cấu hình, không ràng buộc kiểu đầu vào hàm được trả về.

Tương tự, nếu một generic method nhận `Function<T,R>` nhưng không có đối số thông thường nào liên hệ với `T`, trình biên dịch có thể phải dựa vào **kiểu tham số lambda được viết tường minh**, ngữ cảnh kết quả hoặc các ràng buộc khác. Nếu ràng buộc chưa đủ, kiểu suy luận có thể quá rộng (như `Object`) hoặc dẫn tới lỗi khi gọi phương thức mong đợi một kiểu cụ thể.

## 7. Wildcard và tính linh hoạt của API nhận lambda

Trong ví dụ `map`, chữ ký:

```java
static <T, R> List<R> map(
        List<T> source,
        Function<? super T, ? extends R> mapper) {
    // Phần thân xử lý các phần tử, trả về List<R>.
}
```

Đây là **chữ ký minh họa**, không phải mã nguồn độc lập (phần thân ở đây được rút gọn). Vì sao dùng wildcard thay vì luôn `Function<T,R>`?

- `? super T` ở đầu vào cho phép hàm xử lý `T` **hoặc một kiểu cha của `T`**. Hàm nhận `Object` có thể xử lý phần tử `String`.
- `? extends R` ở đầu ra cho phép hàm tạo `R` **hoặc kiểu con của `R`**. Ví dụ hàm trả `Double` có thể dùng ở nơi muốn các kết quả `Number`.
- Cách khai báo này là ứng dụng của nguyên tắc **producer extends, consumer super (PECS)** tại vị trí chức năng nhận và sinh dữ liệu.

Tuy nhiên wildcard làm quá trình suy luận và kiểu bắt giữ (*wildcard capture*) phức tạp hơn. Ví dụ trong chương trình chính:

```java
static <T, R> List<R> streamMap(
        List<T> source,
        Function<? super T, ? extends R> mapper) {
    return source.stream().<R>map(mapper).toList();
}
```

Dạng `.<R>map(mapper)` **chỉ định tham số kiểu của phương thức `Stream.map`**, buộc kiểu kết quả của stream là `R`. Trong trường hợp này, nếu chỉ viết `source.stream().map(mapper).toList()`, trình biên dịch có thể suy luận ra `List<capture of ? extends R>`, không gán trực tiếp được cho `List<R>`. Đoạn mã có `.<R>map(...)` đã được biên dịch với Java 17.

Một cách đơn giản khác là dùng vòng lặp và `result.add(mapper.apply(item))` như phương thức `map` của chương trình chính. Tránh dùng ép kiểu không an toàn chỉ để qua trình biên dịch. Khi một API không cần wildcard, `Function<T,R>` đơn giản hơn; khi cần tính linh hoạt, nên kiểm tra kỹ compiler.

## 8. Suy luận trong phương thức nhận Predicate, Consumer, Supplier và BinaryOperator

**`Predicate<T>`** thường dùng khi giữ nguyên kiểu phần tử nhưng thay đổi tiêu chí:

```java
static <T> List<T> filter(List<T> input, Predicate<? super T> predicate) {
    List<T> result = new ArrayList<>();
    for (T item : input) {
        if (predicate.test(item)) result.add(item);
    }
    return result;
}
```

Đoạn định nghĩa có thể đặt trong lớp, với import `java.util.List`, `java.util.ArrayList`, `java.util.function.Predicate`. Khi gọi `filter(List.of("An","Binh"), s -> s.length()>2)`, `T` đến từ `List<String>` và lambda cần trả `boolean`; kết quả chứa `"Binh"`.

**`Consumer<T>`** trả `void`, nên thân lambda có thể là hành động: `consume("java", s -> System.out.println(s))`. Ở đây `T` gắn với kiểu `String`; `s` là `String`.

**`Supplier<T>`** không có tham số, nên kiểu `T` có thể đến từ kết quả biểu thức lambda và ngữ cảnh nhận kết quả: `String ready = supply(() -> "ready");`.

**`BinaryOperator<T>`** đồng thời ràng buộc hai tham số và kết quả cùng kiểu `T`: `combine(3,4,(a,b)->a+b)` có `T=Integer`. Đây không phải lúc nào cũng là giao diện thích hợp cho hai đầu vào khác kiểu; khi cần `A`, `B` và kết quả `R` khác nhau, dùng `BiFunction<A,B,R>`.

## 9. Generic method và tham chiếu phương thức

Tham chiếu phương thức như `String::length` cũng cần kiểu đích, giống `s -> s.length()`:

```java
List<Integer> sizes = map(List.of("A", "BB"), String::length);
```

Câu lệnh minh họa nằm trong một phương thức có `map` như mục 5 và import `List`. Kiểu nguồn là `String`; `String::length` nhận đối tượng `String` và cho `int` được boxing thành `Integer`, nên kết quả là `[1, 2]`.

Với tham chiếu đến **phương thức overloaded** (nhiều phương thức cùng tên khác danh sách tham số), kiểu đích cũng ảnh hưởng trình biên dịch chọn overload phù hợp. Một số tham chiếu/lambda chỉ có thể được kiểm tra đầy đủ sau khi các tham số kiểu generic được suy luận. Hãy khai báo rõ chữ ký chức năng khi trình biên dịch không chọn được phương thức bạn muốn.

## 10. Các lỗi thường gặp và cách đọc thông báo

### 10.1. Ràng buộc kiểu trả về không tương thích

```text
String wrong = convert("Java", s -> s.length());
```

Với `convert(T,Function<T,R>)`, `R` phải đồng thời phù hợp với giá trị độ dài (`Integer`) và ngữ cảnh `String`. Java 17 từ chối cách dùng này, có thể báo `inference variable R has incompatible bounds`. Sửa thành:

```java
Integer correct = convert("Java", s -> s.length());
```

### 10.2. Lambda trả sai kiểu so với List đích

```text
List<Integer> bad = map(
        List.of("a"), s -> s.toUpperCase());
```

Lambda tạo `String` trong khi danh sách kết quả yêu cầu `Integer`. Đây là ví dụ cố ý không biên dịch. Sửa thành `List<String> upper = map(List.of("a"), s -> s.toUpperCase());`, hoặc giữ `List<Integer>` và dùng `s -> s.length()`.

### 10.3. Overload mơ hồ

Nếu một lớp có hai overload:

```java
static void use(Function<String, Integer> f) { }
static void use(ToIntFunction<String> f) { }
```

Hai khai báo phương thức này hợp lệ trong một lớp đã import `Function`, `ToIntFunction`; nhưng lời gọi sau **cố ý mơ hồ**:

```text
use(s -> s.length());
```

Cả hai kiểu đích đều có thể nhận lambda trên. Để chọn rõ ràng, dùng:

```java
use((ToIntFunction<String>) s -> s.length());
```

Đoạn này nằm trong thân phương thức và cần hai overload ở trên. Đừng lầm rằng suy luận generic luôn giải quyết được **mọi** overload; khi có nhiều kiểu chức năng phù hợp, Java có thể yêu cầu kiểu đích cụ thể.

### 10.4. Gọi sai phương thức trên tham số lambda

```text
consume(10, x -> x.nonexistent());
```

Đây là đoạn cố ý không biên dịch vì tham số `x` không có phương thức `nonexistent()`. Kiểu `T` suy luận từ số `10` là `Integer`, không cho phép gọi một phương thức không tồn tại. Hãy kiểm tra kiểu đích và API của kiểu đó trước khi chỉnh generic declaration.

### 10.5. Kiểu đích quá chung

Khi lambda không cung cấp thông tin đủ cụ thể và generic method không có đối số/kiểu kết quả ràng buộc `T`, `T` có thể được suy luận về một kiểu chung như `Object`. Việc `Object` có `toString()` không chứng tỏ `T` là `String`. Để tránh ngộ nhận, hãy đặt kiểu cụ thể vào chữ ký, gán cho biến có kiểu đích cụ thể, viết kiểu tham số lambda tường minh hoặc chỉ định type witness khi cần.

## 11. Những lưu ý nâng cao

**Suy luận kiểu không phải thực thi lambda:** compiler phân tích **kiểu tĩnh**, không chạy phần thân để xem giá trị thật. Nếu thân lambda có điều kiện hoặc nhiều nhánh `return`, tất cả đường đi cần tương thích với kiểu đích.

**Trước khi suy luận, compiler cần xác định tính thích hợp của lời gọi:** không phải mọi chi tiết phần thân đều được xem như nguồn để chọn overload ngay lập tức; khả năng phụ thuộc ràng buộc và dạng lambda. Bởi vậy các lời gọi overloaded có lambda suy luận kiểu có thể cần kiểu đích tường minh.

**Kiểu generic không nhận primitive trực tiếp:** `Function<int,int>` là sai vì kiểu tham số generic phải là kiểu tham chiếu. Dùng `Function<Integer,Integer>` có boxing/unboxing, hoặc `IntUnaryOperator` cho `int → int`.

**Hành vi khi chạy vẫn tách biệt:** lambda gắn vào `Function` chỉ thực thi khi gọi `apply` hoặc khi generic method chủ động gọi nó. Suy luận `T` và `R` diễn ra trong quá trình biên dịch.

**Không lạm dụng ép kiểu:** ép kiểu thô/raw `Function` có thể che lỗi và dẫn tới `ClassCastException`. Ưu tiên sửa chữ ký, xác định kiểu đích và giữ tính an toàn kiểu.

## 12. Bài tập có đáp án

**Bài 1.** Với `static <T,R> R convert(T x, Function<T,R> f)`, lời gọi `Integer n = convert("hello", s -> s.length());` suy luận `T` và `R` như thế nào?

Đáp án: `T` tương ứng `String` từ `"hello"`; `s` là `String`; `length()` trả `int` tương thích `Integer`, `R` là `Integer`. `n=5` nếu phương thức gọi `f.apply(x)`.

**Bài 2.** `String s = supply(() -> "ok");` dùng nguồn ràng buộc nào khi `supply` có chữ ký `<T> T supply(Supplier<T> f)`?

Đáp án: giá trị trả từ lambda là `String` và ngữ cảnh gán `String s` góp phần ràng buộc `T`; không có tham số thường.

**Bài 3.** `map(List.of(1,2), n -> n.doubleValue())` có thể gán cho `List<Number>` nếu `map` dùng `Function<? super T,? extends R>` không?

Đáp án: **Có**. Đầu vào là `Integer`, lambda trả `double` được boxing thành `Double`, là kiểu con `Number`. Chữ ký với `? extends R` hỗ trợ điều này (và kết quả đã được kiểm chứng trong chương trình chính).

**Bài 4.** Tại sao `List<Integer> x = map(List.of("a"), s -> s.toUpperCase());` không đúng?

Đáp án: lambda tạo `String`, trong khi kết quả được yêu cầu là `Integer`. Cần thay kiểu kết quả sang `List<String>` hoặc dùng lambda tính độ dài.

**Bài 5.** Khi phương thức trả `Function<T,String>` nhưng tham số thường không nhắc đến `T`, làm sao chủ động yêu cầu `T=Integer`?

Đáp án: gán kết quả vào `Function<Integer,String>` hoặc gọi `ClassName.<Integer>method(...)` với tên lớp thật, như `GenericLambdaInferenceDemo.<Integer>describe("num=")`.

## 13. Tóm lược

- Suy luận generic khi truyền lambda là **quá trình giải ràng buộc kiểu của toàn bộ lời gọi**, kết hợp đối số thường, kiểu đích functional interface, thân lambda và ngữ cảnh kết quả.
- Lambda cần **target type**; tham số không ghi kiểu nhận kiểu từ giao diện hàm đã được chuyên biệt hóa bởi suy luận.
- `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>` và `BinaryOperator<T>` cho compiler các hợp đồng đầu vào/đầu ra khác nhau.
- Wildcard `? super T` và `? extends R` tăng khả năng tái sử dụng nhưng đôi khi cần hướng dẫn suy luận rõ hơn, ví dụ `stream().<R>map(mapper)`.
- Nếu compiler báo `incompatible bounds`, `cannot infer type-variable`, `incompatible types` hoặc `reference is ambiguous`, hãy truy ngược các ràng buộc từ chữ ký phương thức, không ép kiểu thô để giấu lỗi.
- Chỉ dùng type witness `ClassName.<T,R>method(...)` hay tham số lambda có kiểu tường minh khi thực sự cần giúp compiler hoặc người đọc.

Tài liệu chính thống: [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html), [§15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27), [§15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).