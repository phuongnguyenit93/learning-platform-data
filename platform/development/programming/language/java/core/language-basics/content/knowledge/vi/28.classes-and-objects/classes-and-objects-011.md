# Nhận diện lambda và tham chiếu phương thức trong lời gọi API — Java 17+

## 1. Nhìn cú pháp để biết API đang nhận một hành vi

Khi đọc mã Java, hai dạng phổ biến là:

~~~java
words.forEach(word -> System.out.println(word));
words.forEach(System.out::println);
~~~

Cả hai truyền một **hành vi** cho API `forEach`: với mỗi phần tử, gọi `println`. Dạng đầu là **lambda expression** có ký hiệu `->`; dạng sau là **method reference** có ký hiệu `::`.

Không cần hiểu trước mọi kỹ thuật lập trình hàm để đọc chúng. Hãy đặt ba câu hỏi:

1. API đang gọi phương thức nào (`forEach`, `map`, `removeIf`, `sort`...)?
2. API yêu cầu loại hành vi nào (nhận gì, trả gì)?
3. Lambda hoặc method reference cung cấp hành vi đó theo cách nào?

**Điểm quan trọng:** một lambda hoặc method reference tạo ra giá trị có kiểu **functional interface** phù hợp; bản thân việc tạo nó thường **chưa thực thi thân hành vi**. API hay lời gọi phương thức trừu tượng tương ứng mới kích hoạt hành vi khi thích hợp.

## 2. Lambda: `thamSo -> bieuThuc` hoặc `thamSo -> { ... }`

~~~java
x -> x * 2

(String text) -> text.length()

name -> {
    System.out.println("Hello " + name);
}
~~~

- Bên trái `->` là danh sách **tham số**. Một tham số có kiểu suy luận có thể bỏ dấu ngoặc: `x -> ...`; với nhiều tham số phải viết `(a, b) -> ...`.
- Bên phải là **biểu thức** hoặc **khối lệnh**. Nếu cần trả giá trị từ khối lệnh, dùng `return expression;` khi kiểu đích yêu cầu kết quả.
- Kiểu của các tham số thường được suy luận từ **ngữ cảnh kiểu đích** (*target typing*).

Ví dụ:

~~~java
java.util.function.IntUnaryOperator doubleIt = x -> x * 2;
System.out.println(doubleIt.applyAsInt(3));
~~~

**Exact stdout:**

~~~text
6
~~~

`IntUnaryOperator` có một phương thức trừu tượng `applyAsInt(int)`: nhận một số nguyên và trả một số nguyên. Lambda trên chính là phần cài đặt cho hành vi đó.

## 3. Functional interface là kiểu đích

Một **functional interface** có đúng **một phương thức trừu tượng cần triển khai** (*single abstract method / SAM*), không tính các phương thức của `Object`. Nó có thể còn có `default` hoặc `static` methods.

| Functional interface | Phương thức chính | Đọc như |
|---|---|---|
| `Consumer<T>` | `accept(T)` → `void` | Nhận giá trị để xử lý, không trả kết quả |
| `Predicate<T>` | `test(T)` → `boolean` | Kiểm tra điều kiện đúng/sai |
| `Function<T,R>` | `apply(T)` → `R` | Biến đổi một giá trị thành giá trị khác |
| `Supplier<T>` | `get()` → `T` | Cung cấp giá trị không cần đối số |
| `Comparator<T>` | `compare(T,T)` → `int` | Xác định thứ tự hai phần tử |
| `Runnable` | `run()` → `void` | Hành động không đối số và không trả giá trị |

Khi thấy `items.removeIf(s -> s.isBlank())`, có thể suy luận `removeIf` nhận `Predicate` nên lambda cần cho ra `boolean`. Khi thấy `items.forEach(s -> System.out.println(s))`, API nhận `Consumer`, nên hành vi không cần trả giá trị.

**Không phải mọi interface đều có thể làm kiểu đích cho lambda**: interface có nhiều phương thức trừu tượng độc lập không phải SAM. Annotation `@FunctionalInterface` giúp compiler kiểm tra ý định khai báo, nhưng lambda không yêu cầu interface bắt buộc có annotation ấy.

## 4. Method reference: `::` thay cho lambda chuyển tiếp

Method reference dùng một phương thức hoặc constructor **đã tồn tại** để thỏa hợp đồng functional interface.

| Dạng | Ví dụ | Lambda tương đương về ý nghĩa |
|---|---|---|
| Static method | `Integer::parseInt` | `s -> Integer.parseInt(s)` |
| Instance method của object có sẵn | `System.out::println` | `s -> System.out.println(s)` |
| Instance method của object được truyền vào | `String::length` | `s -> s.length()` |
| Constructor | `StringBuilder::new` | `() -> new StringBuilder()` |

~~~java
java.util.function.Function<String, Integer> length = String::length;
System.out.println(length.apply("Java"));
~~~

**Exact stdout:**

~~~text
4
~~~

Ở `String::length`, **đối tượng nhận lời gọi** chính là đối số `"Java"`, nên API tương đương `s -> s.length()`.

Với method reference của một object cụ thể:

~~~java
String prefix = "Hi ";
java.util.function.Function<String, String> greet = prefix::concat;
System.out.println(greet.apply("Java"));
~~~

**Exact stdout:**

~~~text
Hi Java
~~~

`prefix::concat` đã gắn receiver `prefix` tại lúc tạo tham chiếu phương thức. Nó không tạo bản sao String hay gọi `concat` ngay. **Không viết `String::length()`**: method reference cần tên phương thức sau `::`, không có dấu ngoặc gọi.

## 5. Đọc `forEach`, `map`, `removeIf` và `sort`

~~~java
List<String> names = List.of("An", "Binh");
names.forEach(System.out::println);
~~~

`forEach` nhận `Consumer<String>` và thực hiện một hành động cho mỗi phần tử. Với danh sách này, stdout là:

~~~text
An
Binh
~~~

Các API thường gặp:

| Lời gọi | Đọc hiểu |
|---|---|
| `names.forEach(System.out::println)` | Gọi `println` trên mỗi phần tử |
| `names.stream().map(String::length)` | Tạo stream kết quả độ dài từng String |
| `mutable.removeIf(String::isBlank)` | Xóa những phần tử thỏa predicate “chuỗi chỉ chứa khoảng trắng hoặc rỗng” |
| `mutable.replaceAll(s -> s.toUpperCase())` | Thay từng phần tử bằng dạng chữ hoa |
| `mutable.sort(Comparator.comparingInt(String::length))` | Sắp xếp theo độ dài tăng dần |

**Phân biệt thời điểm chạy:** `Collection.forEach` thực hiện hành động khi được gọi. Với `Stream.map`, việc tạo pipeline thường **lazy**; hàm biến đổi được áp dụng khi có thao tác terminal, ví dụ `toList()` hoặc `forEach()`.

**Phân biệt tính thay đổi dữ liệu:** `List.of(...)` trả danh sách không thể sửa trực tiếp; gọi `removeIf`, `replaceAll` hay `sort` trên nó có thể ném `UnsupportedOperationException`. Nếu cần sửa danh sách, dùng `new ArrayList<>(List.of(...))`. Kết quả `Stream.toList()` từ Java 16 trở lên cũng không cho phép sửa cấu trúc danh sách kết quả.

## 6. Vì sao không phải lúc nào cũng thay lambda bằng method reference?

Hai cách viết thường tương đương khi lambda **chỉ chuyển tiếp đối số** đến một phương thức:

~~~java
words.stream().map(word -> word.length()).toList();
words.stream().map(String::length).toList();
~~~

Nhưng lambda rất hữu ích khi cần tính toán thêm hoặc nhiều bước:

~~~java
words.stream().map(word -> word.trim().toUpperCase()).toList();
~~~

Đoạn này không tương đương với một method reference duy nhất kiểu `String::trim` vì còn bước chữ hoa. Có thể đặt logic vào một phương thức có tên `normalize` và viết `ClassName::normalize` khi thao tác được tái sử dụng.

**Cẩn thận với overload:** `System.out::println` có nhiều overload, Java chọn phiên bản tương ứng với kiểu đích, ví dụ `Consumer<String>`. Không thể xem method reference như một giá trị “không có kiểu” trong mọi ngữ cảnh; nó cần target functional interface thích hợp.

## 7. Capture biến ngoài và những lỗi cơ bản

Lambda có thể sử dụng local bên ngoài nếu biến đó là `final` hoặc **effectively final** (không bị gán lại):

~~~java
int threshold = 3;
java.util.function.Predicate<String> longEnough =
        text -> text.length() >= threshold;
System.out.println(longEnough.test("Java"));
~~~

**Exact stdout:**

~~~text
true
~~~

Nếu sau đó viết `threshold = 5;` trong cùng phương thức, lambda capture `threshold` như trên sẽ **không biên dịch**, do biến không còn effectively final.

Phân biệt **gán lại tham chiếu** và **thay đổi nội dung object**: một tham chiếu local effectively final vẫn có thể trỏ tới một object mutable, nên callback có thể thấy thay đổi trạng thái object đó. Điều này có thể làm code khó hiểu, nhất là stream song song; ở mức nhập môn, ưu tiên các hàm không gây tác dụng phụ bất ngờ.

Lambda `x -> x + 1` không phải là phương thức có tên để gọi qua `x(...)`; nó được dùng thông qua functional interface, chẳng hạn `op.applyAsInt(5)`.

## 8. Chương trình Java 17+ hoàn chỉnh

Tạo file đúng tên **`LambdaMethodReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Supplier;

public final class LambdaMethodReferenceDemo {
    private LambdaMethodReferenceDemo() {}

    static String normalize(String raw) {
        return raw.trim().toUpperCase(Locale.ROOT);
    }

    static void printTagged(String value) {
        System.out.println("word=" + value);
    }

    public static void main(String[] args) {
        List<String> raw = List.of(" java ", "go", " rust ");
        List<String> words = raw.stream()
                .map(LambdaMethodReferenceDemo::normalize)
                .toList();
        System.out.println("normalized=" + words);

        List<Integer> lengths = words.stream()
                .map(String::length)
                .toList();
        System.out.println("lengths=" + lengths);

        words.forEach(LambdaMethodReferenceDemo::printTagged);

        List<String> editable = new ArrayList<>(
                List.of("a", "", "bbb", "cc"));
        editable.removeIf(String::isBlank);
        System.out.println("filtered=" + editable);

        editable.replaceAll(s -> s.toUpperCase(Locale.ROOT));
        System.out.println("upper=" + editable);

        editable.sort(
                Comparator.<String>comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder()));
        System.out.println("sorted=" + editable);

        Predicate<String> longEnough = s -> s.length() >= 3;
        System.out.println("predicate=" + longEnough.test("JAVA"));

        Function<String, Integer> measure = String::length;
        System.out.println("function=" + measure.apply("RUST"));

        Consumer<String> printer = System.out::println;
        printer.accept("consumer=hello");

        Supplier<StringBuilder> supplier = StringBuilder::new;
        System.out.println("constructor="
                + supplier.get().append("OK"));

        String prefix = "Hi ";
        Function<String, String> bound = prefix::concat;
        System.out.println("bound=" + bound.apply("Java"));

        IntUnaryOperator doubleIt = n -> n * 2;
        System.out.println("lambda=" + doubleIt.applyAsInt(3));

        List<Integer> integers = List.of("2", "4").stream()
                .map(Integer::parseInt)
                .toList();
        System.out.println("parsed=" + integers);

        Runnable action =
                () -> System.out.println("runnable=executed");
        action.run();
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, không cần Maven, Gradle hoặc thư viện ngoài JDK, không dùng preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 LambdaMethodReferenceDemo.java
java -cp . LambdaMethodReferenceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\LambdaMethodReferenceDemo.java
java -cp . LambdaMethodReferenceDemo
~~~

### Exact expected stdout

~~~text
normalized=[JAVA, GO, RUST]
lengths=[4, 2, 4]
word=JAVA
word=GO
word=RUST
filtered=[a, bbb, cc]
upper=[A, BBB, CC]
sorted=[A, CC, BBB]
predicate=true
function=4
consumer=hello
constructor=OK
bound=Hi Java
lambda=6
parsed=[2, 4]
runnable=executed
~~~

**Giải thích:** `map` biến đổi chuỗi và sau đó lấy độ dài bằng method reference; `forEach` dùng static method reference tới `printTagged`. `removeIf` sử dụng predicate `String::isBlank`, `replaceAll` dùng lambda, `sort` dùng comparator xây từ `String::length`. Các ví dụ `Supplier`, `Function` và `Runnable` minh họa hành vi được thực thi khi gọi phương thức SAM hoặc API tương ứng.

## 9. Bài tập, lỗi thường gặp và checklist

| Sai lầm | Nguyên nhân | Cách hiểu đúng |
|---|---|---|
| Nghĩ `x -> x * 2` là phép tính chạy ngay | Lambda tạo hành vi để thực thi sau | Cần lời gọi SAM/API thích hợp |
| Nghĩ `String::length` là gọi `length()` tức thì | Đây là method reference | Dùng làm đối số cho API nhận functional interface |
| Viết `String::length()` | Sai cú pháp method reference | `String::length` |
| Dùng `map` mà không có terminal operation rồi chờ tác dụng | Pipeline stream thường lazy | Gọi `toList`, `forEach`, ... |
| Dùng `removeIf` trên `List.of(...)` | Danh sách không hỗ trợ thay đổi | Dùng `ArrayList` khi cần sửa |
| Dùng lambda mà không có kiểu đích hợp lệ | Lambda cần functional interface | Chọn `Predicate`, `Function`, `Consumer`... |
| Capture một local rồi gán lại local đó | Không effectively final | Tránh gán lại hoặc thiết kế lại |
| Nhầm `Consumer` với `Function` | Consumer không trả kết quả | Chọn functional interface đúng hợp đồng |

**Bài A:** `List.of("A","BB").stream().map(String::length).toList()` cho kết quả gì? **`[1, 2]`**.

**Bài B:** `names.forEach(System.out::println)` tương đương lambda nào? **`names.forEach(s -> System.out.println(s))`** trong ngữ cảnh `Consumer<String>`.

**Bài C:** API `removeIf` yêu cầu callback kiểm tra kiểu gì? **`Predicate<E>`**, có phương thức `test(E)` trả `boolean`.

**Bài D:** `StringBuilder::new` trong `Supplier<StringBuilder>` nghĩa là gì? **Một hành vi không tham số tạo `StringBuilder` mới khi `get()` được gọi**, không tạo object ngay lúc chỉ viết method reference.

### Checklist

- [ ] Nhận ra `->` là lambda và `::` là method reference.
- [ ] Biết functional interface là kiểu đích cho lambda/reference.
- [ ] Phân biệt `Consumer`, `Predicate`, `Function`, `Supplier`, `Comparator`, `Runnable`.
- [ ] Đọc được static, instance-bound, instance-unbound và constructor references.
- [ ] Hiểu callback thực thi khi API/lời gọi SAM kích hoạt, không phải khi viết cú pháp.
- [ ] Phân biệt stream trung gian `map` với terminal `toList`.
- [ ] Nhận ra API nào sửa danh sách, API nào tạo kết quả mới.
- [ ] Tránh capture local không effectively final.
- [ ] Chạy `LambdaMethodReferenceDemo.java` bằng JDK 17+ và đối chiếu exact stdout.

**Kết luận:** Khi gặp `list.forEach(x -> ...)` hoặc `stream.map(Type::method)`, hãy đọc đó là **truyền một hành vi cho API**. Lambda viết trực tiếp hành vi; method reference tái sử dụng phương thức/constructor đã có. Kiểu functional interface của API quyết định hành vi nhận đối số và trả kết quả như thế nào.