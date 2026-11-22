# Hàm bậc cao trong Java: nhận hàm hoặc trả về hàm

## 1. Mục tiêu và ý tưởng cốt lõi

**Hàm bậc cao** (*higher-order function*) là hàm có ít nhất một trong hai đặc điểm: **nhận một hàm làm đối số** hoặc **trả về một hàm**. Nhờ vậy, ta có thể tách phần xử lý cố định khỏi phần hành vi thay đổi theo tình huống.

Trong Java, phương thức không có kiểu “hàm tự do” riêng như một số ngôn ngữ khác. Thay vào đó, ta truyền hoặc trả về đối tượng có kiểu **giao diện hàm** (*functional interface*): giao diện có đúng một phương thức trừu tượng, chẳng hạn `Function<T, R>` hay `Predicate<T>`. Biểu thức lambda (`x -> ...`) và tham chiếu phương thức (`String::length`) giúp tạo giá trị phù hợp với giao diện đó.

Sau bài này, bạn có thể:
- Nhận biết phương thức bậc cao và phân biệt nó với lời gọi phương thức thông thường.
- Viết phương thức nhận `Function`, `Predicate` hoặc các giao diện hàm thích hợp.
- Viết phương thức trả về lambda, hiểu biến được lambda ghi nhớ và thời điểm hàm được thực thi.
- Kết hợp các hàm bằng `compose`, `andThen`, sử dụng đúng kiểu tổng quát và tránh lỗi thường gặp.

## 2. Vì sao cần hàm bậc cao?

Giả sử một chương trình cần xử lý nhiều danh sách: đôi khi đổi chuỗi thành độ dài, đôi khi chuẩn hóa chữ, đôi khi chọn phần tử theo điều kiện. Nếu mỗi biến thể đều có một vòng lặp gần giống nhau, mã sẽ lặp lại cấu trúc duyệt và khó mở rộng.

Hàm bậc cao cho phép **giữ nguyên cơ chế duyệt và chuyển phần quy tắc thành tham số**:

- Phần ổn định: lấy từng phần tử và tập hợp kết quả.
- Phần thay đổi: biến đổi phần tử bằng `Function` hoặc kiểm tra điều kiện bằng `Predicate`.
- Nơi gọi quyết định quy tắc bằng lambda, tham chiếu phương thức hoặc một đối tượng thực thi giao diện hàm.

Đây là nền tảng của `Stream.map`, `Stream.filter`, `Optional.map`, `Comparator.comparing` và nhiều API Java hiện đại. Các API đó **nhận hành vi** để thực hiện vào thời điểm được thiết kế.

## 3. Java biểu diễn “hàm như giá trị” như thế nào?

| Giao diện trong `java.util.function` | Phương thức chính | Ý nghĩa |
| --- | --- | --- |
| `Function<T, R>` | `R apply(T value)` | Một đầu vào, tạo một kết quả |
| `UnaryOperator<T>` | `T apply(T value)` | Trường hợp `Function<T, T>` |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra một điều kiện |
| `Consumer<T>` | `void accept(T value)` | Nhận giá trị và thực hiện hành động |
| `Supplier<T>` | `T get()` | Cung cấp giá trị, không nhận đối số |
| `BiFunction<T, U, R>` | `R apply(T first, U second)` | Hai đầu vào, một kết quả |
| `IntUnaryOperator` | `int applyAsInt(int value)` | Biến thể chuyên biệt cho `int`, tránh boxing |

Một lambda phải có **kiểu đích** (*target type*) là giao diện hàm:

```java
Function<String, Integer> length = text -> text.length();
Predicate<String> nonBlank = text -> !text.isBlank();

int size = length.apply("Java");       // 4
boolean ok = nonBlank.test(" Java ");  // true
```

Đoạn trên minh họa các biểu thức đặt trong thân một phương thức có sẵn; có thể thêm `import java.util.function.Function;` và `import java.util.function.Predicate;` để sử dụng. Việc **tạo** `length` chưa gọi `text.length()`: hành vi thực thi khi `apply` được gọi. Lambda không tự động là hàm thuần; nó vẫn có thể đọc/ghi trạng thái hoặc gây tác dụng phụ.

Bạn cũng có thể khai báo giao diện của mình bằng `@FunctionalInterface` khi cần hợp đồng chuyên biệt. Tuy nhiên, hãy ưu tiên các giao diện chuẩn nếu chúng đã diễn đạt chính xác đầu vào và đầu ra.

## 4. Nhận hàm làm tham số: một chương trình chạy được

Ví dụ dưới đây có hai phương thức bậc cao:

- `map` **nhận** quy tắc biến đổi `Function` và áp dụng nó lên mọi phần tử.
- `filter` **nhận** điều kiện `Predicate` và giữ lại phần tử thỏa điều kiện.

Lưu vào tệp `HigherOrderDemo.java`:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class HigherOrderDemo {
    static <T, R> List<R> map(
            List<T> items,
            Function<? super T, ? extends R> rule) {
        return items.stream().<R>map(rule).toList();
    }

    static <T> List<T> filter(
            List<T> items,
            Predicate<? super T> condition) {
        return items.stream().filter(condition).toList();
    }

    static Function<String, String> prefixWith(String prefix) {
        return value -> prefix + value;
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        System.out.println(map(names, String::length));
        System.out.println(filter(names, name -> name.length() >= 4));

        Function<String, String> label = prefixWith("Bạn: ");
        System.out.println(label.apply("Lan"));

        Function<String, String> trim = String::trim;
        Function<String, Integer> length = String::length;
        System.out.println(trim.andThen(length).apply("  Java  "));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac HigherOrderDemo.java
java HigherOrderDemo
```

Kết quả chuẩn:

```text
[2, 4, 3]
[Binh]
Bạn: Lan
4
```

**Phân tích luồng xử lý:**

1. `map(names, String::length)` truyền hành vi “đo độ dài” vào phương thức duyệt. `String::length` là tham chiếu đến phương thức của đối tượng `String` nhận được, tương đương `name -> name.length()`.
2. `filter(names, name -> name.length() >= 4)` cung cấp quy tắc lọc tại nơi gọi. Chỉ `"Binh"` dài ít nhất bốn ký tự.
3. `prefixWith("Bạn: ")` **trả về một hàm**. Biến `label` giữ hàm được tạo; `label.apply("Lan")` mới chạy phép nối chuỗi.
4. `trim.andThen(length)` tạo hàm kết hợp: trước tiên cắt khoảng trắng đầu/cuối, sau đó đếm ký tự. `"Java"` có độ dài bốn.

`Stream.toList()` có từ Java 16 và trả về danh sách không thể thay đổi cấu trúc. Ví dụ này dùng Java 17+ như đã nêu.

## 5. Trả về hàm: tạo hành vi theo cấu hình

Phương thức trả về giao diện hàm hữu ích khi cần tạo một **quy tắc đã cấu hình sẵn**, rồi tái sử dụng ở nhiều chỗ. Chẳng hạn, từ một số cộng thêm, ta tạo một phép biến đổi `int`; hoặc từ một hàm xử lý bất kỳ, ta trả về một hàm mới kèm thao tác ghi nhận.

Lưu vào `FactoryDemo.java`:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class FactoryDemo {
    static IntUnaryOperator add(int amount) {
        return number -> number + amount;
    }

    static <T, R> Function<T, R> logged(Function<T, R> operation) {
        return input -> {
            R result = operation.apply(input);
            System.out.println("Đã xử lý: " + input);
            return result;
        };
    }

    public static void main(String[] args) {
        IntUnaryOperator plusFive = add(5);
        System.out.println(plusFive.applyAsInt(7));

        Function<String, Integer> count = logged(String::length);
        System.out.println(count.apply("Java"));
    }
}
```

Chạy:

```bash
javac FactoryDemo.java
java FactoryDemo
```

Kết quả:

```text
12
Đã xử lý: Java
4
```

`add(5)` trả về một lambda ghi nhớ `amount = 5`; sau này `plusFive.applyAsInt(7)` cho `12`. `logged` đặc biệt vì **vừa nhận một hàm vừa trả về một hàm khác**: nó bao quanh hành vi cũ bằng bước ghi nhận. Ta có thể dùng ý tưởng này để thêm ghi log, đo thời gian, kiểm tra quyền truy cập hoặc xử lý lỗi, miễn là có thiết kế rõ ràng cho các tác dụng phụ.

**Phạm vi biến được ghi nhớ (closure):** lambda có thể dùng tham số và biến cục bộ bên ngoài phạm vi của chính nó. Biến cục bộ được bắt giữ phải là `final` hoặc **effectively final** (không bị gán lại sau khi khởi tạo). Với biến cục bộ trỏ tới đối tượng có thể thay đổi, ràng buộc này chỉ cấm gán lại biến tham chiếu; nó không khiến đối tượng bất biến.

```java
int increment = 3;
IntUnaryOperator plusThree = n -> n + increment;
// increment = 4; // Nếu bỏ chú thích, mã không biên dịch.
```

Đây là đoạn minh họa trong thân phương thức, với `IntUnaryOperator` đã được import. Khi trả về lambda, không cần giữ khung ngăn xếp của phương thức tạo nó: các giá trị/tham chiếu được bắt giữ vẫn sẵn có qua đối tượng hàm đã tạo. Tránh bắt giữ đối tượng có trạng thái thay đổi thiếu đồng bộ khi nhiều luồng cùng dùng hàm.

## 6. Ghép các hàm thay vì lặp lại logic

Cho `f: A → B` và `g: B → C`, phép ghép `g(f(a))` biến đổi `A → C` mà không cần tạo phương thức mới cho từng tổ hợp.

Với `Function`, có hai cách viết tương đương về thứ tự thực hiện:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> a = trim.andThen(length);
Function<String, Integer> b = length.compose(trim);

System.out.println(a.apply("  Java  ")); // 4
System.out.println(b.apply("  Java  ")); // 4
```

Các câu lệnh này đặt trong thân phương thức và cần import `java.util.function.Function`.

- `f.andThen(g)`: chạy `f` trước, `g` sau.
- `g.compose(f)`: chạy `f` trước, `g` sau.
- `Predicate.and`, `Predicate.or`, `Predicate.negate`: kết hợp các điều kiện; `and` và `or` có đánh giá ngắn mạch, nên thứ tự có thể quan trọng nếu điều kiện gây tác dụng phụ.
- `Function.identity()`: hàm đồng nhất `x -> x`, hữu ích trong chuỗi biến đổi.

`Consumer.andThen` cũng ghép hai hành động nhưng không tạo kết quả trả về. Đừng dùng `andThen` như cách che giấu các tác dụng phụ nếu thứ tự thực hiện là yêu cầu quan trọng của nghiệp vụ.

Một mẫu khác là **áp dụng lặp cùng một hành vi**:

```java
import java.util.function.IntUnaryOperator;

public class TwiceDemo {
    static int applyTwice(IntUnaryOperator operation, int value) {
        return operation.applyAsInt(operation.applyAsInt(value));
    }

    public static void main(String[] args) {
        System.out.println(applyTwice(n -> n + 3, 4));
    }
}
```

Chạy `javac TwiceDemo.java` rồi `java TwiceDemo` in ra `10` vì `4 → 7 → 10`. Nếu truyền một hàm có tác dụng phụ, tác dụng đó cũng xảy ra **hai lần**.

## 7. Hàm nhiều tham số và tạo hàm từng bước

`BiFunction<A, B, R>` nhận hai đầu vào khi gọi `apply(a, b)`. Đôi khi bạn muốn cố định một tham số trước rồi nhận tham số còn lại ở lần gọi sau; cách biểu diễn này thường được gọi là **currying** (biến hàm nhiều tham số thành chuỗi hàm một tham số) hoặc **partial application** khi cố định sẵn một phần đối số.

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class CurryDemo {
    public static void main(String[] args) {
        BiFunction<Integer, Integer, Integer> add = Integer::sum;
        Function<Integer, IntUnaryOperator> addBy =
                amount -> number -> number + amount;

        System.out.println(add.apply(3, 4));
        IntUnaryOperator plusThree = addBy.apply(3);
        System.out.println(plusThree.applyAsInt(4));
    }
}
```

Chạy `javac CurryDemo.java` và `java CurryDemo`, kết quả là hai dòng `7` và `7`. Trong ví dụ này, `addBy.apply(3)` **chưa cộng vào một số cụ thể**: nó tạo hàm mới đang chờ số thứ hai.

Java không tự động currying mọi phương thức. Kiểu trả về `Function<Integer, IntUnaryOperator>` và các lambda lồng nhau phải được khai báo, hoặc dùng thư viện cung cấp cấu trúc tương đương.

## 8. Chọn kiểu đúng và hiểu ràng buộc kiểu tổng quát

Khi viết API nhận hàm, nên bộc lộ đúng **vai trò**:
- Trả về dữ liệu: `Function<T, R>`; cùng kiểu vào/ra: `UnaryOperator<T>`.
- Quyết định đúng/sai: `Predicate<T>`, thay vì `Function<T, Boolean>` nếu không có lý do riêng.
- Thực hiện hành động không trả về: `Consumer<T>`.
- Tạo dữ liệu theo yêu cầu: `Supplier<T>`.
- Xử lý `int`, `long`, `double` trong vòng lặp hiệu năng nhạy cảm: cân nhắc các giao diện chuyên biệt để giảm boxing.

Trong phương thức `map` ở trên, chữ ký `Function<? super T, ? extends R>` có chủ ý:

- `? super T` cho phép hàm nhận `T` **hoặc kiểu cha** của `T` (hàm “tiêu thụ” đầu vào).
- `? extends R` cho phép hàm tạo `R` **hoặc kiểu con** của `R` (hàm “sản xuất” kết quả).

Ví dụ, một `Function<Object, String>` có thể xử lý các phần tử `String`, và đầu ra `String` có thể được dùng tại vị trí yêu cầu `CharSequence`. Cách khai báo linh hoạt này giúp phương thức bậc cao dễ tái sử dụng. Hãy để trình biên dịch suy luận kiểu khi được; khi lambda có nhiều cách hiểu, có thể khai báo rõ kiểu tham số hoặc biến đích.

## 9. Thời điểm chạy, tác dụng phụ và các giới hạn thực tế

**Phân biệt tạo hàm và chạy hàm.** `Function<String, Integer> f = String::length;` tạo giá trị hành vi, còn `f.apply("Java")` mới gọi tính toán. Một phương thức bậc cao có thể gọi hàm ngay, gọi nhiều lần, chỉ giữ lại để dùng sau hoặc không gọi; **hợp đồng của API nhận hàm** mới quyết định điều đó.

Với Stream, các bước trung gian như `map` và `filter` thường thực thi **lười**. Chúng chỉ chạy khi có thao tác kết thúc như `toList()`, `count()` hoặc `forEach(...)` và có thể không xử lý mọi phần tử nếu kết quả có thể kết thúc sớm. Đừng dựa vào tác dụng phụ trong `map` để bảo đảm số lần hay thứ tự thực hiện khi pipeline thay đổi.

**Hàm thuần** trả cùng kết quả với cùng đầu vào và không tạo tác dụng phụ quan sát được; Java không bắt buộc lambda phải thuần. Các hàm thuần, bất biến và không phụ thuộc trạng thái dùng chung thường dễ kiểm thử và kết hợp hơn. Hàm có tác dụng phụ vẫn cần thiết cho I/O và ghi nhận, nhưng nên thể hiện rõ ý đồ (thường bằng `Consumer` hoặc tên phương thức phù hợp).

Các giao diện chuẩn như `Function.apply` không khai báo checked exception. Nếu hành vi cần ném ngoại lệ có kiểm tra, bạn phải xử lý trong lambda, chuyển đổi có chủ đích sang ngoại lệ không kiểm tra hoặc thiết kế giao diện hàm riêng khai báo `throws`. Đừng âm thầm nuốt lỗi.

**Giá trị `null`:** `Function` không mặc nhiên kiểm tra `null` cho bạn. Truyền `null` làm đối số hàm, nhận `null` làm kết quả hoặc dereference đầu vào `null` đều phải theo hợp đồng và cách xử lý được thiết kế; thường có thể dùng `Objects.requireNonNull` tại ranh giới API.

**Hiệu năng:** lambda không đồng nghĩa với tạo một luồng mới. Truyền hàm là cơ chế diễn đạt hành vi; Stream tuần tự vẫn chạy trên luồng gọi. Lambda bắt giữ biến có thể cần đối tượng lưu trạng thái; giao diện hàm chuyên biệt tránh một số chi phí đóng hộp số nguyên. Chỉ tối ưu khi có số đo đáng tin.

## 10. Các lỗi dễ mắc

| Tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Muốn “truyền phương thức” nhưng truyền `length.apply("Java")` | Đang truyền **kết quả** là `int`, không truyền hành vi | Truyền `String::length` hoặc `s -> s.length()` |
| Viết lambda nhưng không có kiểu đích phù hợp | Java không biết chữ ký của hành vi | Khai báo `Function<String, Integer>` hoặc tham số phương thức nhận giao diện hàm |
| Gán lại biến cục bộ đã bị lambda bắt giữ | Lỗi biên dịch do không còn effectively final | Tạo biến mới/giá trị bất biến; đừng dùng mảng hay đối tượng biến đổi chỉ để lách quy tắc |
| Nhầm `compose` và `andThen` | Các bước chạy sai thứ tự | Đọc từ `f.andThen(g)` = chạy f rồi g; `g.compose(f)` = chạy f rồi g |
| Dùng `Function` cho tác vụ chỉ có tác dụng phụ | Hợp đồng đầu ra gây hiểu nhầm | Dùng `Consumer` khi không cần trả kết quả |
| Hàm ghi vào danh sách hoặc biến dùng chung trong Stream | Kết quả khó dự đoán, nhất là khi chạy song song | Dùng phép biến đổi không trạng thái và thao tác kết thúc/collector thích hợp |
| Tưởng hàm trả về đã chạy ngay | Nhầm thời điểm thực hiện hoặc bỏ sót lời gọi | Phân biệt `Function` (giá trị hành vi) với `apply` (thực thi) |

## 11. Khi nào nên dùng và cách tự kiểm tra

Hàm bậc cao đặc biệt phù hợp khi **cấu trúc xử lý giống nhau nhưng quy tắc thay đổi**: ánh xạ và lọc dữ liệu, cấu hình bộ so sánh, tạo bộ kiểm tra, bọc thao tác bằng ghi log hoặc tạo các hàm theo tham số cấu hình. Với logic chỉ dùng một lần, đơn giản và không cần chuyển hành vi qua ranh giới API, một phương thức thông thường có thể dễ hiểu hơn.

Hãy thử tự làm ba bài tập sau:

1. Viết `static <T> long countMatching(List<T> items, Predicate<? super T> rule)` để đếm phần tử thỏa điều kiện. Kiểm thử với `List.of(2, 5, 8, 11)` và `n -> n % 2 == 0`; kết quả mong đợi là `2`.
2. Viết `static UnaryOperator<String> appendSuffix(String suffix)` trả về lambda nối hậu tố. Với hậu tố `"!"`, áp dụng vào `"Java"` phải được `"Java!"`. Xác định rõ lời gọi nào tạo hàm và lời gọi nào chạy hàm.
3. Dùng `Function.andThen` ghép bước chuẩn hóa chuỗi `String::trim` và bước đổi thành chữ in hoa `String::toUpperCase`; thử `"  java  "` và giải thích vì sao đổi thứ tự hai bước trong trường hợp này vẫn cho `"JAVA"`, nhưng không phải mọi phép biến đổi đều đổi thứ tự được.

**Câu hỏi tự đánh giá:** Nếu một phương thức có chữ ký `Function<Integer, Integer> makeAdder(int delta)` và trả về `n -> n + delta`, phương thức đó thuộc kiểu hàm bậc cao nào? Nó **trả về hàm**; đối tượng hàm này ghi nhớ `delta`, và phép cộng chỉ xảy ra khi gọi `apply`.

Điểm cần nắm chắc: trong Java, “hàm bậc cao” là cách tổ chức **hành vi thông qua giao diện hàm**. Một phương thức nhận hành vi, trả về hành vi hoặc làm cả hai cho phép phần thuật toán cố định và phần quy tắc thay đổi được kết hợp rõ ràng, kiểm thử riêng và tái sử dụng.