# `Stream.map()` và phép biến đổi một-một trong Java

## 1. Mục tiêu: biến đổi từng phần tử của một Stream

Khi có một tập dữ liệu, ta thường muốn tạo ra một cách biểu diễn mới cho **mỗi phần tử**: chuyển tên thành chữ hoa, lấy độ dài chuỗi, đổi đối tượng nghiệp vụ thành DTO, chuẩn hóa mã hoặc tính giá trị dẫn xuất. Trong Java Stream API, phương thức phù hợp với mô hình đó là **`map()`**.

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<Integer> lengths = names.stream()
        .map(String::length)
        .toList();

System.out.println(lengths); // [2, 4, 3]
~~~

Ở đây `Stream<String>` chuyển thành `Stream<Integer>` vì mỗi chuỗi được ánh xạ sang độ dài của chính nó. Không có phần tử nào bị chủ động loại bỏ hoặc nhân lên bởi **bản thân phép `map()`**.

Cụm từ **một-một** trong bài này có nghĩa thực tiễn: mỗi phần tử nguồn **được thực sự xử lý** bởi `map` tạo **một phần tử kết quả**. Đây là đặc tính về số phần tử ở một bước biến đổi, không nhất thiết là ánh xạ một-một theo nghĩa toán học *injective* (hai đầu vào khác nhau hoàn toàn có thể cho cùng đầu ra). Ví dụ `"An"` và `"My"` đều có độ dài 2.

Cũng cần lưu ý Stream là một pipeline **lazy**: nếu chưa có thao tác đầu cuối, mapper thường chưa chạy; thao tác dừng sớm và một số tối ưu hóa có thể khiến callback chỉ chạy trên một phần nguồn hoặc được lược bỏ khi kết quả vẫn đúng theo hợp đồng Stream. Vì vậy, không dùng số lần gọi mapper làm phép kiểm đếm có hiệu ứng phụ.

## 2. Chữ ký API và cách đọc kiểu

Trên `java.util.stream.Stream<T>`, chữ ký cốt lõi là:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
~~~

Giải nghĩa:

- `T`: kiểu phần tử trước khi biến đổi, chẳng hạn `String`.
- `R`: kiểu phần tử sau biến đổi, chẳng hạn `Integer` hoặc `UserDto`.
- `Function<? super T, ? extends R>`: hành vi nhận một giá trị tương thích với `T` và trả một giá trị tương thích với `R`.
- `Stream<R>`: kiểu pipeline mới nhận được. `map` là **intermediate operation**, chưa phải kết quả dạng `List<R>` hay `R[]`.
- Wildcard `? super T` cho phép hàm nhận kiểu đầu vào rộng hơn `T`; `? extends R` cho phép kết quả là kiểu con của `R`.

Nếu dùng lambda:

~~~java
Stream<Integer> lengths =
        Stream.of("Java", "API")
                .map(s -> s.length());
~~~

thì `s -> s.length()` thực hiện vai trò `Function<String,Integer>`. Nếu dùng method reference:

~~~java
Stream<Integer> lengths =
        Stream.of("Java", "API")
                .map(String::length);
~~~

thì `String::length` diễn đạt cùng phép ánh xạ với lambda bên trên.

Tham số `mapper` phải là hàm hợp lệ khác `null`. `map(null)` không tạo một phép biến đổi “giữ nguyên”; nó không hợp lệ. Muốn giữ nguyên đầu vào trong một API cần mapper, có thể dùng `Function.identity()` hoặc `x -> x`.

### 2.1. `map` không nhất thiết giữ nguyên kiểu phần tử

~~~java
Stream<String> source = Stream.of("1", "20", "300");

Stream<Integer> parsed =
        source.map(Integer::parseInt);

List<Integer> result = parsed.toList();
System.out.println(result); // [1, 20, 300]
~~~

Dữ liệu đầu vào là chuỗi; kết quả là số nguyên bọc `Integer`. Phương thức `Integer.parseInt` trả `int` nhưng Java có thể boxing thành `Integer` vì `Stream.map` trả một reference stream.

Nếu mục đích là thao tác số nguyên nguyên thủy, có thể chuyển sang `IntStream` bằng `mapToInt`; xem phần 5.

## 3. Vì sao gọi là phép biến đổi một-một?

Xét ví dụ:

~~~java
List<String> source = List.of("a", "bb", "ccc");
List<Integer> mapped = source.stream()
        .map(String::length)
        .toList();

System.out.println(mapped); // [1, 2, 3]
~~~

Bản thân mapper chọn một kết quả cho từng phần tử:

~~~text
"a"   ── String::length ──> 1
"bb"  ── String::length ──> 2
"ccc" ── String::length ──> 3
~~~

Nếu pipeline duyệt toàn bộ ba phần tử không gặp lỗi hay thao tác thay đổi số lượng, kết quả có ba phần tử. `map` không kiểm tra kết quả trùng lặp và **không** loại phần tử bị biến đổi thành cùng một giá trị.

~~~java
List<Integer> sameLengths = Stream.of("An", "My")
        .map(String::length)
        .toList();

System.out.println(sameLengths); // [2, 2]
~~~

Hai phần tử đầu vào khác nhau cho hai phần tử đầu ra bằng nhau. Vì vậy **“một-một” ở đây không có nghĩa kết quả luôn duy nhất**. Muốn loại trùng, cần một thao tác riêng như `distinct()` với ngữ nghĩa equality phù hợp.

Tương tự, nếu hàm ánh xạ trả về `null`, `map` có thể tạo **một phần tử null**, chứ không tự loại bỏ nó:

~~~java
List<String> mapped = Stream.of("A", "", "C")
        .map(s -> s.isEmpty() ? null : s)
        .toList();

System.out.println(mapped); // [A, null, C]
~~~

Để bỏ null, thêm `filter(Objects::nonNull)` hoặc thiết kế callback trả Optional rồi flatten; xem phần 6.

## 4. Cơ chế pipeline: `map` là lazy và không sửa nguồn

`map` là phép biến đổi **trung gian, stateless, non-interfering theo yêu cầu sử dụng đúng API**. Mỗi khi phần tử cần đi qua `map`, mapper được dùng để tạo giá trị thay thế cho các bước sau của pipeline.

~~~java
List<String> source = List.of(" java ", " stream ");
Stream<String> pipeline = source.stream()
        .map(String::trim)
        .map(String::toUpperCase);

// Các mapper chưa cần thực thi tại đây.
List<String> result = pipeline.toList(); // Terminal operation.
System.out.println(result); // [JAVA, STREAM]
~~~

Có ba điều cần tách biệt:

1. **Tạo pipeline:** các lời gọi `stream()` và `map(...)` mô tả các giai đoạn xử lý.
2. **Tiêu thụ pipeline:** `toList()`, `collect(...)`, `forEach(...)`, `reduce(...)` hoặc terminal khác yêu cầu tính kết quả.
3. **Kết quả cuối:** có thể là một collection, số, giá trị đơn lẻ hoặc hiệu ứng được terminal tạo ra.

Java Stream **không phải cấu trúc chứa dữ liệu độc lập** giống `List`. `source.stream().map(...)` cũng không có nghĩa `source` đã được sửa. Dữ liệu nguồn vẫn là các giá trị ban đầu, trừ khi chính callback hoặc mã bên ngoài sửa trạng thái mutable.

### 4.1. Thứ tự biến đổi trong chuỗi `map`

~~~java
List<String> output = Stream.of(" java ", " api ")
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();

System.out.println(output); // [JAVA, API]
~~~

Mỗi phần tử đi qua phép trim rồi uppercase theo thứ tự logic được khai báo. Điều này tương ứng với kết hợp hàm:

~~~java
Function<String, String> normalize =
        ((Function<String, String>) String::trim)
                .andThen(String::toUpperCase);
~~~

Với ví dụ này, `stream.map(normalize)` và `stream.map(String::trim).map(String::toUpperCase)` có cùng kết quả cho các chuỗi hợp lệ, nếu chúng được áp dụng trên hai nguồn Stream tương đương và không có side effect ảnh hưởng.

### 4.2. Lazy không bảo đảm callback chạy đúng bằng số phần tử nguồn

~~~java
List<String> data = List.of("a", "b", "c");

long count = data.stream()
        .map(s -> {
            System.out.println("mapping " + s);
            return s.toUpperCase();
        })
        .count();
~~~

Không được lấy số dòng `mapping ...` làm hợp đồng API. Khi nguồn có kích thước đã biết và phép biến đổi không làm thay đổi số phần tử, implementation có thể tính `count()` mà **không cần chạy mapper**. Đây là tối ưu hóa hợp lệ của Stream. Dù `count` trả `3`, không có bảo đảm callback in ra ba lần.

Tương tự, `findFirst()`, `findAny()`, `anyMatch()`, `limit()` và các terminal có thể dừng sớm thường không cần đi qua mọi phần tử. Với parallel stream, thứ tự thực thi callback cũng không phải thứ tự quan sát được bảo đảm, ngay cả khi kết quả cuối của một thao tác giữ thứ tự là đúng.

**Hệ quả:** mapper nên **stateless**, không can thiệp nguồn và không dựa vào side effect để bảo đảm tính đúng của chương trình. Những thao tác cần side effect nên có điểm thực thi rõ ràng, đồng thời vẫn phải hiểu hợp đồng của terminal operation.

## 5. `map` với đối tượng và các stream nguyên thủy

Trên `Stream<T>`, `map` trả `Stream<R>`. Trên các primitive stream, tên `map` vẫn có nhưng chữ ký khác:

| Nguồn | Mapper | Kết quả |
| --- | --- | --- |
| `Stream<T>.map` | `Function<T,R>` | `Stream<R>` |
| `IntStream.map` | `IntUnaryOperator` | `IntStream` |
| `LongStream.map` | `LongUnaryOperator` | `LongStream` |
| `DoubleStream.map` | `DoubleUnaryOperator` | `DoubleStream` |
| `Stream<T>.mapToInt` | `ToIntFunction<T>` | `IntStream` |
| `Stream<T>.mapToLong` | `ToLongFunction<T>` | `LongStream` |
| `Stream<T>.mapToDouble` | `ToDoubleFunction<T>` | `DoubleStream` |
| `IntStream.mapToObj` | `IntFunction<R>` | `Stream<R>` |

Ví dụ khi đã có `Stream<String>`:

~~~java
List<String> labels = List.of("An", "Binh", "Chi");

int sum = labels.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(sum); // 9
~~~

Nếu viết `labels.stream().map(String::length)` thì ta có `Stream<Integer>`; nó **không có phương thức `sum()` trực tiếp**. `mapToInt` trả `IntStream` nên có các terminal số học chuyên biệt và tránh boxing giá trị trung gian sang `Integer`.

Với `IntStream`:

~~~java
int sumOfSquares = IntStream.of(2, 3, 4)
        .map(n -> n * n)
        .sum();

List<String> labels = IntStream.of(2, 3, 4)
        .mapToObj(n -> "n=" + n)
        .toList();

System.out.println(sumOfSquares); // 29
System.out.println(labels);       // [n=2, n=3, n=4]
~~~

`IntStream.map` nhận một số `int` và trả số `int`; `mapToObj` tạo đối tượng, nên kiểu đầu ra thay đổi sang `Stream<String>`.

Lưu ý phép nhân/tổng trên `int` có thể **overflow** theo quy tắc số nguyên Java. Chọn kiểu `long` hoặc kiểm tra overflow nếu phạm vi giá trị lớn.

## 6. Phân biệt `map`, `filter` và `flatMap`

Ba phương thức này đều là thao tác trung gian nhưng trả lời ba câu hỏi khác nhau:

| Thao tác | Câu hỏi | Ảnh hưởng đến số phần tử |
| --- | --- | --- |
| `map(f)` | “Mỗi phần tử được đổi thành giá trị gì?” | Một đầu ra cho mỗi phần tử đã ánh xạ |
| `filter(p)` | “Phần tử nào nên được giữ?” | Giữ 0 hoặc 1 đầu ra cho mỗi phần tử |
| `flatMap(f)` | “Mỗi phần tử tạo ra một luồng con nào?” | Mỗi đầu vào có thể tạo 0, 1 hoặc nhiều đầu ra |

### 6.1. `filter` giữ hoặc bỏ dữ liệu, `map` biến đổi dữ liệu

~~~java
List<Integer> result = Stream.of("a", "bb", "ccc")
        .filter(s -> s.length() >= 2)
        .map(String::length)
        .toList();

System.out.println(result); // [2, 3]
~~~

`filter` làm mất phần tử `"a"`; `map` chuyển hai chuỗi còn lại thành số độ dài. Thứ tự có ý nghĩa nếu phép biến đổi có thể làm thay đổi điều kiện lọc; hãy đặt mỗi thao tác theo yêu cầu nghiệp vụ.

### 6.2. `map` tạo luồng lồng nhau, `flatMap` làm phẳng

~~~java
List<List<String>> groups = List.of(
        List.of("A", "B"),
        List.of("C"));

Stream<Stream<String>> nested = groups.stream()
        .map(List::stream);

List<String> flattened = groups.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(flattened); // [A, B, C]
~~~

`map(List::stream)` tạo ra **mỗi phần tử là một Stream<String>** (kiểu `Stream<Stream<String>>`). `flatMap(List::stream)` nối các Stream con thành một `Stream<String>`; vì thế một nhóm hai phần tử có thể đóng góp hai phần tử kết quả. `map` không tự làm phẳng container.

### 6.3. Với Optional: `map` giữ lớp Optional, `flatMap` có thể bỏ Optional rỗng

Giả sử có phương thức:

~~~java
static Optional<Integer> parse(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
~~~

Khi ánh xạ:

~~~java
List<Optional<Integer>> parsed = Stream.of("10", "bad", "20")
        .map(MyParser::parse)
        .toList();
~~~

`map` tạo một Optional cho từng phần tử; Optional rỗng vẫn là **một phần tử đầu ra**:

~~~text
[Optional[10], Optional.empty, Optional[20]]
~~~

Nếu mục tiêu là chỉ giữ các số phân tích thành công:

~~~java
List<Integer> numbers = Stream.of("10", "bad", "20")
        .map(MyParser::parse)
        .flatMap(Optional::stream)
        .toList();

System.out.println(numbers); // [10, 20]
~~~

`Optional.stream()` có 0 phần tử khi rỗng hoặc 1 phần tử khi có giá trị. `flatMap(Optional::stream)` nối các luồng này và làm mất các nhánh rỗng. Khác biệt ở số lượng kết quả **đến từ `flatMap`**, không phải từ `map`.

Trong các đoạn nhỏ ở đây, `MyParser::parse` là tên giả định cho phương thức `static Optional<Integer> parse(String)` đã khai báo; chương trình chạy độc lập ở phần 10 dùng tên lớp và phương thức đầy đủ.

### 6.4. `map` không phải `forEach`

`map` trả về pipeline chuyển đổi cho bước tiếp theo; `forEach` là **terminal operation** nhận `Consumer<T>` và trả `void`, thường dùng khi thực sự muốn thực hiện hành động trên phần tử.

~~~java
List<String> upper = Stream.of("a", "b")
        .map(String::toUpperCase)
        .toList();
~~~

Đoạn trên tạo giá trị mới. Trái lại:

~~~java
Stream.of("a", "b").forEach(System.out::println);
~~~

chỉ tiêu thụ phần tử để in, không trả danh sách kết quả. Với parallel stream, `forEach` không bảo đảm encounter order; nếu cần thứ tự khi tiêu thụ, xem `forEachOrdered` và chi phí của nó.

## 7. Biến đổi entity sang DTO hoặc giá trị trình bày

Ứng dụng thường cần biến đổi đối tượng nghiệp vụ thành dữ liệu phục vụ hiển thị, báo cáo hoặc kết nối API. Dùng `map` giúp phân tách *nguồn dữ liệu* với *quy tắc chuyển đổi*.

~~~java
record User(String id, String name, int age) {}
record UserCard(String id, String label, boolean adult) {}

List<User> users = List.of(
        new User("u01", "An", 20),
        new User("u02", "Binh", 17));

List<UserCard> cards = users.stream()
        .map(u -> new UserCard(
                u.id(),
                u.name().toUpperCase(Locale.ROOT),
                u.age() >= 18))
        .toList();
~~~

Ở đây mỗi `User` tạo một `UserCard`. Không có cập nhật đối tượng `User` gốc; lambda tạo đối tượng mới. Nếu dùng `map(User::name)`, đầu ra sẽ là `Stream<String>`, còn `map(u -> u)` trả chính các `User` đang có.

**Lưu ý về tính bất biến:** `Stream.toList()` (Java 16+) tạo danh sách unmodifiable; điều này không có nghĩa mọi đối tượng phần tử đều immutable. Nếu mapper trả đối tượng mutable cũ, danh sách mới vẫn có thể giữ cùng tham chiếu tới đối tượng đó. Nếu cần tách dữ liệu hoàn toàn, phải xây dựng bản sao theo đúng yêu cầu nghiệp vụ.

## 8. `null`, ngoại lệ và dữ liệu sai

### 8.1. Mapper có thể trả null

~~~java
List<String> values = Stream.of("a", "", "b")
        .map(s -> s.isEmpty() ? null : s)
        .toList();

System.out.println(values); // [a, null, b]
~~~

`map` giữ **một phần tử đầu ra** cho chuỗi rỗng: đó là `null`. Tuy nhiên, terminal khác như `Collectors.toUnmodifiableList()` không chấp nhận phần tử null, vì vậy chính sách null cần phù hợp với terminal.

Để bỏ các phần tử null sau khi biến đổi:

~~~java
List<String> values = Stream.of("a", "", "b")
        .map(s -> s.isEmpty() ? null : s)
        .filter(Objects::nonNull)
        .toList();

System.out.println(values); // [a, b]
~~~

Đây là kết hợp `map` + `filter`; phép giảm số phần tử thuộc về `filter`.

### 8.2. Mapper nhận đầu vào null vẫn phải tự xử lý

~~~java
List<String> source = Arrays.asList("a", null, "b");

List<String> safe = source.stream()
        .map(s -> s == null ? "" : s.toUpperCase(Locale.ROOT))
        .toList();

System.out.println(safe); // [A, , B]
~~~

`Stream.map` không tự kiểm tra hoặc loại `null` trước khi gọi mapper. Nếu dùng `String::toUpperCase` trực tiếp trên một phần tử null, callback sẽ ném `NullPointerException`. Viết hàm chuyển đổi an toàn hoặc thêm `filter(Objects::nonNull)` theo chính sách xử lý mong muốn.

### 8.3. Khi callback ném ngoại lệ

~~~java
List<Integer> numbers = Stream.of("1", "bad", "3")
        .map(Integer::parseInt)
        .toList(); // NumberFormatException khi gặp "bad".
~~~

Với pipeline tuần tự dùng `toList`, lỗi được ném trong quá trình terminal thực thi; `map` không tự bắt lỗi hay biến nó thành Optional rỗng. Nếu cần tiếp tục xử lý các bản ghi hợp lệ, hãy chuyển từng đầu vào thành `Optional<Integer>` hoặc kết quả có thông tin lỗi rồi quyết định rõ cách làm phẳng/lưu lỗi. Đừng tùy tiện bắt mọi `RuntimeException` và bỏ qua lỗi lập trình.

### 8.4. Khác biệt giữa `Stream.map` và `Optional.map`

`Optional<T>.map(Function<T,U>)` trả `Optional<U>`, và mapper chỉ chạy nếu Optional có giá trị. Trong khi đó, `Stream<T>.map` trả `Stream<U>` và là một bước trung gian của pipeline Stream.

~~~java
Optional<String> maybeName = Optional.of("Java");
Optional<Integer> size = maybeName.map(String::length);

Stream<String> names = Stream.of("Java", "API");
Stream<Integer> sizes = names.map(String::length);
~~~

Tên cùng là `map` nhưng **container trước dấu chấm khác nhau**. Cần xem chữ ký và kiểu trả về trước khi sử dụng.

## 9. Thứ tự, song song và phép biến đổi thuần khiết

Trên nguồn có encounter order, `map` là một thao tác giữ quan hệ thứ tự giữa các phần tử đầu vào và đầu ra trong kết quả của các terminal giữ thứ tự như `toList()`. Điều này vẫn đúng khi pipeline được xử lý song song, miễn không có thao tác loại bỏ tính thứ tự hoặc terminal bỏ bảo đảm thứ tự.

~~~java
List<Integer> squares = IntStream.rangeClosed(1, 4)
        .parallel()
        .map(n -> n * n)
        .boxed()
        .toList();

System.out.println(squares); // [1, 4, 9, 16]
~~~

Parallel execution không bảo đảm **thứ tự chạy callback**, nhưng kết quả `toList()` ở đây được dựng theo encounter order của nguồn có thứ tự.

Không sửa collection nguồn trong mapper:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));

// Tránh:
// source.stream().map(s -> {
//     source.add("C");  // Can thiệp nguồn trong lúc pipeline duyệt.
//     return s;
// }).toList();
~~~

Quy tắc non-interference yêu cầu không thay đổi nguồn không-concurrent khi đang thực thi pipeline. Thay đổi trạng thái dùng chung giữa các callback parallel cũng có thể gây race hoặc kết quả không ổn định. Nên viết mapper thuần khiết, ví dụ `n -> n * n` hoặc `String::trim`, và đưa side effect ra ranh giới phù hợp.

Trong trường hợp thực sự cần side effect kèm kết quả mới, hãy thiết kế rõ giai đoạn ghi nhận và giai đoạn biến đổi, kiểm soát lỗi và đảm bảo thread-safety. `peek` có thể phục vụ quan sát/debug nhưng không nên dùng để bảo đảm tác dụng phụ vì các phép tối ưu hóa và short-circuit của pipeline.

## 10. Ví dụ Java 17+ hoàn chỉnh

Lưu tệp **`MapOneToOneDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class MapOneToOneDemo {
    record User(String id, String name, int age) {}
    record UserCard(String id, String label, boolean adult) {}

    static Optional<Integer> parseInteger(String text) {
        try {
            return Optional.of(Integer.parseInt(text));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");
        System.out.println("lengths=" + names.stream()
                .map(String::length).toList());
        System.out.println("lengthSum=" + names.stream()
                .mapToInt(String::length).sum());

        List<String> normalized = Stream.of(" java ", " api ")
                .map(String::trim)
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();
        System.out.println("normalized=" + normalized);

        List<User> users = List.of(
                new User("u01", "An", 20),
                new User("u02", "Binh", 17));
        List<UserCard> cards = users.stream()
                .map(u -> new UserCard(
                        u.id(),
                        u.name().toUpperCase(Locale.ROOT),
                        u.age() >= 18))
                .toList();
        System.out.println("cards=" + cards);

        List<Optional<Integer>> wrapped = Stream.of("10", "bad", "-2")
                .map(MapOneToOneDemo::parseInteger)
                .toList();
        System.out.println("wrapped=" + wrapped);
        System.out.println("valid=" + Stream.of("10", "bad", "-2")
                .map(MapOneToOneDemo::parseInteger)
                .flatMap(Optional::stream)
                .toList());

        System.out.println("withNull=" + Stream.of("A", "", "C")
                .map(s -> s.isEmpty() ? null : s)
                .toList());
        System.out.println("nonNull=" + Stream.of("A", "", "C")
                .map(s -> s.isEmpty() ? null : s)
                .filter(Objects::nonNull)
                .toList());

        System.out.println("squares=" + IntStream.of(2, 3, 4)
                .map(n -> n * n)
                .boxed()
                .toList());

        AtomicInteger invoked = new AtomicInteger();
        Stream<String> lazy = Stream.of("a", "bb", "ccc")
                .map(s -> {
                    invoked.incrementAndGet();
                    return s.toUpperCase(Locale.ROOT);
                });
        System.out.println("before=" + invoked.get());
        System.out.println("lazyResult=" + lazy.toList());
        System.out.println("after=" + invoked.get());

        Function<String, Integer> length = String::length;
        System.out.println("composed=" + Stream.of("  xyz  ")
                .map(((Function<String, String>) String::trim)
                        .andThen(length))
                .toList());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MapOneToOneDemo.java
java MapOneToOneDemo
~~~

**Stdout:**

~~~text
lengths=[2, 4, 3]
lengthSum=9
normalized=[JAVA, API]
cards=[UserCard[id=u01, label=AN, adult=true], UserCard[id=u02, label=BINH, adult=false]]
wrapped=[Optional[10], Optional.empty, Optional[-2]]
valid=[10, -2]
withNull=[A, null, C]
nonNull=[A, C]
squares=[4, 9, 16]
before=0
lazyResult=[A, BB, CCC]
after=3
composed=[3]
~~~

**Đọc kết quả theo luồng dữ liệu:**

- `String::length` chuyển `String` thành `Integer`; `mapToInt` cho phép tính tổng trực tiếp bằng `IntStream.sum()`.
- Hai lần `map` liên tiếp chuẩn hóa chuỗi bằng `trim` rồi `toUpperCase(Locale.ROOT)`.
- Mapper tạo một `UserCard` cho mỗi `User`, giữ đúng hai phần tử tương ứng.
- `parseInteger` tạo một Optional cho cả dữ liệu hợp lệ và không hợp lệ; `flatMap(Optional::stream)` mới bỏ Optional rỗng.
- Mapper trả `null` vẫn tạo phần tử; `filter(Objects::nonNull)` làm mất phần tử đó.
- `IntStream.map` biến đổi giá trị `int` mà không cần boxing trước khi gọi `boxed()`.
- Với `lazy.toList()`, cả ba phần tử cần ánh xạ để dựng danh sách kết quả; ví dụ này cho `before=0` và `after=3`. Không suy rộng rằng **mọi** terminal luôn buộc mapper chạy đúng ba lần.
- `Function.andThen` ghép hàm trim rồi lấy độ dài, cho kết quả 3.

## 11. Những lựa chọn thiết kế nên nhớ

### 11.1. Có cần tạo object mới không?

`map` **không tự tạo bản sao**. Mapper quyết định trả gì:

~~~java
Stream<User> sameObjects = users.stream().map(u -> u);
Stream<String> names = users.stream().map(User::name);
Stream<UserCard> cards = users.stream()
        .map(u -> new UserCard(u.id(), u.name(), u.age() >= 18));
~~~

- `u -> u` giữ chính tham chiếu `User`.
- `User::name` trả thuộc tính `String`.
- `new UserCard(...)` tạo object mới.

Đừng nhầm thao tác `map` với phép copy collection hoặc deep copy object.

### 11.2. Có thể biến một phần tử thành danh sách không?

Có, vì một danh sách cũng là **một đối tượng kết quả**:

~~~java
Stream<List<String>> nested = Stream.of("A,B", "C")
        .map(s -> List.of(s.split(",")));
~~~

Kết quả có hai phần tử kiểu `List<String>`, không phải ba phần tử String. Nếu cần các phần tử bên trong, dùng `flatMap`:

~~~java
List<String> flat = Stream.of("A,B", "C")
        .flatMap(s -> Arrays.stream(s.split(",")))
        .toList();

System.out.println(flat); // [A, B, C]
~~~

### 11.3. Có bắt buộc dùng `map` cho mọi giá trị dẫn xuất không?

Không. Nếu chỉ cần tổng, cực trị hoặc thống kê số nguyên thủy, `mapToInt`/`mapToLong`/`mapToDouble` thường diễn đạt rõ hơn và tránh boxing. Nếu mục đích chỉ là chọn phần tử, `filter` phù hợp; nếu mục đích chỉ là thực hiện hành động, cân nhắc terminal `forEach` theo yêu cầu cụ thể. Nếu cần 0 hoặc nhiều phần tử cho mỗi nguồn, `flatMap` là lựa chọn tự nhiên.

### 11.4. Có thể tái sử dụng Stream sau `toList()` không?

Không. Stream chỉ được tiêu thụ một lần:

~~~java
Stream<String> s = Stream.of("a", "b");
List<String> output = s.map(String::toUpperCase).toList();

// Không được tái sử dụng s cho terminal mới.
~~~

Nếu cần nhiều kết quả độc lập từ dữ liệu nguồn, hãy tạo nhiều pipeline mới, hoặc thiết kế collector/tổng hợp phù hợp để tránh duyệt lại không cần thiết.

## 12. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tưởng `map` lọc bớt phần tử khi mapper trả null | Tạo phần tử null | Dùng `filter(Objects::nonNull)` hoặc `flatMap` có chủ đích |
| Tưởng `map` bảo đảm kết quả không trùng | Các kết quả có thể bằng nhau | `distinct` nếu yêu cầu loại trùng |
| Gọi `sum()` trực tiếp trên `Stream<Integer>` | Không có phương thức số học đó | Dùng `mapToInt` rồi `sum()` |
| Dùng `map` với mapper trả Stream rồi mong phẳng | Nhận `Stream<Stream<R>>` | Dùng `flatMap` |
| Dùng `map` với mapper trả Optional rồi mong bỏ empty | Nhận `Stream<Optional<R>>` | Dùng `flatMap(Optional::stream)` |
| Cho rằng map sửa collection nguồn | Pipeline tạo giá trị đi tiếp | Chỉ sửa dữ liệu nếu có thao tác mutation tường minh, tránh can thiệp nguồn |
| Dựa vào `map` để tăng counter/log chắc chắn | Callback có thể không chạy do tối ưu hóa hoặc short-circuit | Không đặt side effect bắt buộc vào mapper |
| Tái sử dụng một Stream đã chạy terminal | `IllegalStateException` thường xảy ra | Tạo stream mới từ nguồn |
| Gọi method reference trên phần tử null | Có thể ném `NullPointerException` | Kiểm tra/lọc/xử lý null theo hợp đồng |
| Giả định `parallel().map` chạy callback theo thứ tự | Thứ tự thực thi không bảo đảm | Dựa vào kết quả terminal có hợp đồng thứ tự, tránh side effect |
| Gọi `map` với mapper `null` | Mapper không hợp lệ | Cung cấp hàm thích hợp, `Function.identity()` nếu muốn giữ nguyên |

## 13. Bài tập tự kiểm tra

**Câu 1.** Với `List.of("a", "bb", "cc")`, kết quả `stream().map(String::length).toList()` là gì? Nó có loại bỏ phần tử trùng độ dài không?

Đáp án: `[1, 2, 2]`. Không. `map` không tự loại trùng.

**Câu 2.** `Stream.of("A", "", "B").map(s -> s.isEmpty() ? null : s).count()` có bằng 2 không?

Đáp án: bằng **3**. `map` vẫn có ba đầu ra theo ngữ nghĩa, kể cả null; `count()` có thể tính dựa vào kích thước nguồn mà không cần chạy mapper. Muốn loại phần tử null, dùng một `filter`/`flatMap` tương ứng.

**Câu 3.** `List<String> names` có ba phần tử. Muốn lấy tổng độ dài, dùng `map` hay `mapToInt`?

Đáp án: `names.stream().mapToInt(String::length).sum()` là cách trực tiếp vì `IntStream` có terminal `sum()`.

**Câu 4.** Với `List<List<String>> groups`, `groups.stream().map(List::stream)` trả kiểu gì?

Đáp án: `Stream<Stream<String>>`. Dùng `flatMap(List::stream)` nếu muốn `Stream<String>`.

**Câu 5.** Vì sao không dùng side effect trong lambda của `map` để đếm chắc chắn số phần tử nguồn?

Đáp án: Pipeline lazy, có short-circuit và các tối ưu hóa như `count()` trên nguồn đã biết kích thước. Java không hứa callback được chạy cho tất cả phần tử chỉ vì `map` đã xuất hiện trong pipeline.

**Câu 6.** Khi biến `User` thành `UserCard` qua `map`, nguồn `List<User>` có bị đổi thành `List<UserCard>` không?

Đáp án: Không. `map` tạo pipeline kết quả kiểu `Stream<UserCard>`, rồi terminal như `toList()` tạo danh sách kết quả riêng. Collection nguồn giữ nguyên cấu trúc nếu không có lệnh mutation khác.

**Câu 7.** `Optional<Integer>` được tạo từ mỗi chuỗi bằng `map`. Muốn bỏ Optional rỗng thì làm gì?

Đáp án: Sau `map(parser)`, gọi `flatMap(Optional::stream)`; mỗi Optional có giá trị đóng góp một phần tử, còn Optional rỗng đóng góp không phần tử.

## 14. Ghi nhớ

`Stream.map(Function<? super T, ? extends R>)` là thao tác trung gian **biến đổi từng phần tử từ `T` thành `R`**. Mỗi phần tử thực sự được mapper xử lý cho ra một kết quả, dù đó có thể là giá trị trùng lặp, `null` hoặc một container khác. `map` **không chủ động lọc, flatten, loại trùng hay sao chép dữ liệu**.

Phân biệt các mục tiêu:

- **`map`:** biến đổi mỗi giá trị thành một giá trị mới.
- **`filter`:** giữ hoặc bỏ giá trị theo điều kiện.
- **`flatMap`:** nối các nguồn 0 hoặc nhiều giá trị thành một stream phẳng.
- **`mapToInt`/`mapToLong`/`mapToDouble`:** biến đổi trực tiếp sang primitive stream để thao tác số.
- **Terminal operation:** kích hoạt xử lý và thu được kết quả, với khả năng short-circuit/tối ưu hóa tùy hợp đồng.

Chọn mapper dễ đọc, ưu tiên hành vi stateless và non-interfering, xem đúng kiểu ở mỗi giai đoạn, và không dựa vào việc callback chạy đúng bao nhiêu lần để thiết kế side effect quan trọng.
