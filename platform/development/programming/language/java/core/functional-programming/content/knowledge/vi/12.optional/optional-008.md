# `Optional.stream()` để phối hợp với Stream trong Java

## 1. Vấn đề: khi một phép xử lý có thể có hoặc không có kết quả

Trong Java, `Optional<T>` là một container đại diện cho **có một giá trị khác `null` hoặc không có giá trị**. Một hàm tra cứu có thể trả `Optional<User>`; một hàm phân tích chuỗi có thể trả `Optional<Integer>` nếu dữ liệu hợp lệ, hoặc `Optional.empty()` nếu không.

Giả sử xử lý nhiều chuỗi đầu vào, mỗi chuỗi được thử chuyển thành số nguyên:

~~~java
List<String> inputs = List.of("10", "invalid", "-2", "7");
Stream<Optional<Integer>> parsed =
        inputs.stream().map(MyParser::parseInteger);
~~~

Ở đây `map` nhận từng chuỗi và trả một `Optional<Integer>`. Vì thế kết quả là **`Stream<Optional<Integer>>`**, chưa phải `Stream<Integer>`. Nếu muốn bỏ các kết quả không có giá trị và chỉ xử lý các số đã phân tích thành công, ta cần chuyển mỗi `Optional<Integer>` thành một luồng 0 hoặc 1 phần tử rồi làm phẳng các luồng con.

Đó chính là công việc tự nhiên của **`Optional.stream()` kết hợp với `Stream.flatMap`**:

~~~java
Stream<Integer> values =
        inputs.stream()
                .map(MyParser::parseInteger)
                .flatMap(Optional::stream);
~~~

Trong các ví dụ này, `MyParser::parseInteger` biểu diễn một phương thức do ứng dụng tự định nghĩa, nhận `String` và trả `Optional<Integer>`; phần chương trình hoàn chỉnh phía dưới có định nghĩa chạy được.

## 2. `Optional.stream()` trả về gì?

Phương thức `Optional<T>.stream()` có từ **Java 9**; có sẵn trong Java 17+:

~~~java
public Stream<T> stream()
~~~

Đây là phương thức **instance** trên một `Optional<T>`:

- Nếu Optional có giá trị, trả một `Stream<T>` **tuần tự (sequential)** chứa đúng **một phần tử**, chính là giá trị đó.
- Nếu Optional rỗng, trả `Stream<T>` **rỗng**, có **không phần tử**.
- Nó không trả một `Stream<Optional<T>>`; phần tử của luồng là `T`, không phải Optional bọc bên ngoài.
- Đây là thao tác tạo một luồng, không phải thao tác đầu cuối như `count()`, `collect()` hay `toList()`.

Ví dụ:

~~~java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();

System.out.println(present.stream().toList()); // [Java]
System.out.println(absent.stream().toList());  // []
~~~

Có thể nhớ bằng công thức về số phần tử:

~~~text
Optional.of(value) ── stream() ──> Stream có đúng 1 phần tử: value
Optional.empty()   ── stream() ──> Stream có 0 phần tử
~~~

Vì `Optional` không chứa `null`, phần tử của `Optional.stream()` cũng không phải `null`. Nếu dùng `Optional.ofNullable(null)` thì Optional rỗng, nên luồng tương ứng cũng rỗng. Ngược lại, `Optional.of(null)` ném `NullPointerException` ngay khi tạo Optional.

**Điểm cần phân biệt:** một Optional không trở thành một nguồn phát nhiều phần tử chỉ nhờ `stream()`. Nếu muốn biểu diễn không hoặc nhiều kết quả, `Stream` hoặc collection mới là mô hình phù hợp; `Optional.stream()` chỉ là cầu nối giữa hai kiểu trừu tượng.

## 3. Vì sao `flatMap(Optional::stream)` quan trọng?

`Stream.flatMap` nhận một hàm biến mỗi phần tử đầu vào thành một Stream rồi **ghép các Stream con** thành một Stream kết quả. Chữ ký tổng quát:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

Với một `Stream<Optional<String>>`, mỗi phần tử nguồn là `Optional<String>`. Phương thức `Optional::stream` tương ứng lambda:

~~~java
opt -> opt.stream()
~~~

và trả `Stream<String>` cho từng Optional. Vì thế:

~~~java
List<Optional<String>> entries = List.of(
        Optional.of("An"),
        Optional.empty(),
        Optional.of("Binh"));

List<String> names = entries.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(names); // [An, Binh]
~~~

Diễn biến về kiểu:

~~~text
List<Optional<String>>
     |
     | .stream()
     v
Stream<Optional<String>>
     |
     | .flatMap(Optional::stream)
     v
Stream<String>
     |
     | .toList()
     v
List<String>          => [An, Binh]
~~~

Và diễn biến theo từng phần tử:

~~~text
Optional.of("An")   -> Stream("An")   \
Optional.empty()    -> Stream.empty()  > ghép thành Stream("An", "Binh")
Optional.of("Binh") -> Stream("Binh")  /
~~~

Thành phần rỗng không cung cấp phần tử nào, nên không cần lời gọi `get()` hoặc phép lọc riêng. Nếu source là Stream có encounter order, `flatMap` vẫn bảo toàn thứ tự encounter order của các phần tử kết quả theo semantics của pipeline có thứ tự. Tuy nhiên, với nguồn không có thứ tự hoặc thao tác như `unordered()`, đừng giả định thứ tự được bảo đảm.

### 3.1. So sánh với `map(Optional::stream)`

Hai pipeline có kiểu hoàn toàn khác nhau:

~~~java
Stream<Optional<String>> source = entries.stream();

Stream<Stream<String>> nested =
        source.map(Optional::stream);
~~~

`map` chỉ thay mỗi `Optional<String>` bằng một `Stream<String>` nên tạo **`Stream<Stream<String>>`**. Nếu cần một luồng phẳng gồm các `String`, phải dùng `flatMap`:

~~~java
Stream<String> flat =
        entries.stream().flatMap(Optional::stream);
~~~

Đừng dùng lại biến `source` sau một thao tác trung gian/đầu cuối đã sử dụng nó: Java Stream là pipeline sử dụng một lần. Các dòng code trên cố ý tạo luồng mới bằng `entries.stream()` cho minh họa thay vì tái sử dụng `source`.

### 3.2. Vì sao không dùng `filter(Optional::isPresent).map(Optional::get)`?

Cách cũ sau vẫn có thể hoạt động:

~~~java
List<String> values = entries.stream()
        .filter(Optional::isPresent)
        .map(Optional::get)
        .toList();
~~~

Nhưng `flatMap(Optional::stream)` gọn hơn và tránh phải gọi `get()` dựa trên điều kiện lọc trước đó:

~~~java
List<String> values = entries.stream()
        .flatMap(Optional::stream)
        .toList();
~~~

Hai dạng có cùng danh sách giá trị cho nguồn Optional hợp lệ. Với Java 9+, `flatMap(Optional::stream)` thường thể hiện ý định “giữ các giá trị hiện diện, bỏ các Optional rỗng” rõ ràng hơn. Trong những trường hợp cần thêm logic quanh việc không có giá trị, `filter`/`map` hoặc xử lý tường minh vẫn có chỗ dùng.

## 4. Tình huống thực tế: mỗi phần tử có thể phân tích thất bại

Xây dựng phương thức parse trả Optional để biểu diễn kết quả hợp lệ hoặc không hợp lệ:

~~~java
static Optional<Integer> parseInteger(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
~~~

Phương thức này chỉ bắt `NumberFormatException`; ví dụ minh họa việc không có số hợp lệ, không chứng minh rằng mọi lỗi nên bị chuyển thành `Optional.empty()`. Khi cần báo chi tiết lỗi, một cấu trúc kết quả mang thông tin lỗi sẽ phù hợp hơn.

Pipeline:

~~~java
List<String> raw = List.of("10", "invalid", "-2", "7");

List<Integer> numbers = raw.stream()
        .map(MyParser::parseInteger)
        .flatMap(Optional::stream)
        .toList();

System.out.println(numbers); // [10, -2, 7]
~~~

Hoặc viết trực tiếp:

~~~java
List<Integer> numbers = raw.stream()
        .flatMap(text -> MyParser.parseInteger(text).stream())
        .toList();
~~~

Cả hai có cùng ý nghĩa:

1. Xử lý từng chuỗi trong `raw`.
2. Nếu parse thành công, đưa đúng một `Integer` vào Stream kết quả.
3. Nếu parse thất bại, không đưa phần tử nào vào.
4. Tập hợp các giá trị có mặt theo thứ tự nguồn thành danh sách.

Đây là một dạng **lọc đồng thời biến đổi**. `filter` thông thường chỉ giữ/bỏ các phần tử hiện tại, còn `flatMap` có thể làm việc với phép biến đổi trả nhiều hoặc không phần tử.

Tuy nhiên, nếu các phần tử đầu vào hoặc kết quả cần lưu thông tin lỗi, việc bỏ các Optional rỗng có thể gây **mất thông tin** về từng lần parse thất bại. Hãy chọn hành vi bỏ qua lỗi chỉ khi nó phù hợp nghiệp vụ.

## 5. Phân biệt `Optional.map`, `Optional.flatMap` và `Stream.flatMap`

Ba API có tên gần nhau nhưng đối tượng nhận và kết quả khác nhau.

| API | Đầu vào của phép biến đổi | Kiểu callback điển hình | Kết quả |
| --- | --- | --- | --- |
| `Optional<T>.map` | Giá trị `T` khi có | `Function<T,U>` | `Optional<U>` |
| `Optional<T>.flatMap` | Giá trị `T` khi có | `Function<T,Optional<U>>` | `Optional<U>` |
| `Stream<T>.map` | Từng phần tử `T` | `Function<T,U>` | `Stream<U>` |
| `Stream<T>.flatMap` | Từng phần tử `T` | `Function<T,Stream<U>>` | `Stream<U>` |
| `Optional<T>.stream` | Không nhận callback | Không có | `Stream<T>` có 0 hoặc 1 phần tử |

Ví dụ với Optional đơn lẻ:

~~~java
Optional<String> text = Optional.of("123");

Optional<Integer> length =
        text.map(String::length);      // Optional<Integer>

Optional<Integer> parsed =
        text.flatMap(s -> parseInteger(s)); // Optional<Integer>

Stream<String> oneOrZero =
        text.stream();                 // Stream<String>
~~~

Trong đó `parseInteger` là phương thức trả `Optional<Integer>` đã mô tả ở trên.

- `Optional.map` bọc kết quả mới vào Optional; nếu mapper trả `null`, kết quả là Optional rỗng.
- `Optional.flatMap` yêu cầu mapper trả một `Optional` khác; **không bọc thêm một lớp**, và mapper trả `null` là lỗi (thường `NullPointerException`).
- `Optional.stream` chuyển từ Optional sang Stream; nó không áp dụng mapper.
- `Stream.flatMap(Optional::stream)` gọi `stream()` cho **mỗi Optional bên trong Stream** và nối các luồng.

Một trường hợp dễ nhầm:

~~~java
Optional<String> maybe = Optional.of("Java");

// maybe.flatMap(String::trim) // Sai: String::trim trả String, không trả Optional.
Optional<String> correct = maybe.map(String::trim);
~~~

Và:

~~~java
Stream<Optional<String>> options = entries.stream();

// options.flatMap(Function.identity()) // Sai kiểu: mapper cần trả Stream.
Stream<String> correct = options.flatMap(Optional::stream);
~~~

Đừng nhầm `Optional.flatMap` với `Stream.flatMap` chỉ vì có chung từ “flatMap”: cần xem **container nào đang đứng trước dấu chấm** và callback trả loại container gì.

## 6. Xử lý dữ liệu có `null`: so với `Stream.ofNullable`

`Optional.ofNullable(value)` nhận một giá trị có thể null, tạo Optional có giá trị nếu khác null và rỗng nếu null. Ghép với `stream()`:

~~~java
String value = null;
Stream<String> none =
        Optional.ofNullable(value).stream();

System.out.println(none.count()); // 0
~~~

Java 9+ cũng có phương thức tĩnh **`Stream.ofNullable(value)`**; nó trực tiếp trả Stream 0 hoặc 1 phần tử:

~~~java
String value = null;
Stream<String> none = Stream.ofNullable(value);
System.out.println(none.count()); // 0
~~~

Đối với một giá trị nullable đơn giản, `Stream.ofNullable(value)` thường ngắn gọn hơn `Optional.ofNullable(value).stream()`. Nhưng khi API đã cung cấp **`Optional<T>`**, `optional.stream()` là cách chuyển đổi tự nhiên.

Chẳng hạn một nguồn được phép chứa `null` (khác với `List.of`, vốn không chấp nhận phần tử null):

~~~java
List<String> raw = java.util.Arrays.asList(" An ", null, " Binh ");

List<String> cleaned = raw.stream()
        .flatMap(Stream::ofNullable)
        .map(String::trim)
        .toList();

System.out.println(cleaned); // [An, Binh]
~~~

Với mỗi `String`, `Stream::ofNullable` tạo Stream 1 phần tử nếu khác null, hoặc Stream rỗng nếu null. Điều này tương đương về giá trị với:

~~~java
List<String> cleaned = raw.stream()
        .flatMap(s -> Optional.ofNullable(s).stream())
        .map(String::trim)
        .toList();
~~~

**Không dùng `Stream.of(value)` thay cho `Stream.ofNullable(value)` khi mục đích là bỏ null:** `Stream.of((String) null)` tạo Stream **chứa một phần tử null**, chứ không tạo Stream rỗng.

Cũng không cần bọc tất cả biến nullable trong Optional một cách máy móc. Optional phù hợp nhất khi API cần diễn đạt “có thể không có kết quả”; `Stream.ofNullable` phù hợp nếu chỉ muốn đưa một giá trị nullable vào pipeline.

## 7. Optional của kiểu nguyên thủy

Java có các lớp chuyên biệt:

- `OptionalInt` với `IntStream stream()`.
- `OptionalLong` với `LongStream stream()`.
- `OptionalDouble` với `DoubleStream stream()`.

Các phương thức `stream()` này cũng được thêm từ Java 9. Chúng tránh phải boxing từng phần tử khi xử lý luồng nguyên thủy.

Với `Stream<OptionalInt>`, **không** gọi `flatMap(OptionalInt::stream)` vì `Stream.flatMap` mong callback trả `Stream<R>`, còn `OptionalInt.stream()` trả `IntStream`. Hãy chọn `flatMapToInt`:

~~~java
List<OptionalInt> numbers = List.of(
        OptionalInt.of(2),
        OptionalInt.empty(),
        OptionalInt.of(5));

int total = numbers.stream()
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(total); // 7
~~~

Tương tự, dùng `flatMapToLong(OptionalLong::stream)` và `flatMapToDouble(OptionalDouble::stream)` khi kiểu nguồn phù hợp.

Một Optional nguyên thủy không phải `Optional<Integer>`: chữ ký `OptionalInt::stream` và `Optional<Integer>::stream` trả hai loại luồng khác nhau, dẫn đến lựa chọn method khác nhau trên `Stream`.

## 8. Chương trình Java 17+ đầy đủ, có stdout xác định

Tạo tệp **`OptionalStreamDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.Stream;

public class OptionalStreamDemo {
    static Optional<Integer> parseInteger(String text) {
        try {
            return Optional.of(Integer.parseInt(text));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<Optional<String>> names = List.of(
                Optional.of("An"),
                Optional.empty(),
                Optional.of("Binh"));

        List<String> presentNames = names.stream()
                .flatMap(Optional::stream)
                .toList();
        System.out.println("names=" + presentNames);

        List<String> raw = List.of("10", "invalid", "-2", "7");
        List<Integer> numbers = raw.stream()
                .map(OptionalStreamDemo::parseInteger)
                .flatMap(Optional::stream)
                .toList();
        System.out.println("numbers=" + numbers);

        int sum = numbers.stream()
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("sum=" + sum);

        System.out.println("presentCount="
                + Optional.of("x").stream().count());
        System.out.println("emptyCount="
                + Optional.<String>empty().stream().count());

        String missing = null;
        System.out.println("nullCount="
                + Stream.ofNullable(missing).count());

        List<String> nullable = Arrays.asList(" A ", null, " B ");
        List<String> cleaned = nullable.stream()
                .flatMap(Stream::ofNullable)
                .map(String::trim)
                .toList();
        System.out.println("cleaned=" + cleaned);

        List<OptionalInt> maybeInts = List.of(
                OptionalInt.of(2),
                OptionalInt.empty(),
                OptionalInt.of(5));
        int primitiveSum = maybeInts.stream()
                .flatMapToInt(OptionalInt::stream)
                .sum();
        System.out.println("primitiveSum=" + primitiveSum);

        List<Integer> positive = raw.stream()
                .flatMap(s -> parseInteger(s).stream())
                .filter(n -> n > 0)
                .toList();
        System.out.println("positive=" + positive);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac OptionalStreamDemo.java
java OptionalStreamDemo
~~~

**Kết quả stdout:**

~~~text
names=[An, Binh]
numbers=[10, -2, 7]
sum=15
presentCount=1
emptyCount=0
nullCount=0
cleaned=[A, B]
primitiveSum=7
positive=[10, 7]
~~~

Giải thích lần lượt:

1. `names.stream()` tạo Stream chứa ba Optional; `flatMap(Optional::stream)` bỏ Optional rỗng và lấy hai tên.
2. `map(OptionalStreamDemo::parseInteger)` tạo Optional cho mỗi chuỗi; `flatMap(Optional::stream)` chỉ giữ các số hợp lệ.
3. `sum` dùng `mapToInt` để tính `10 + (-2) + 7 = 15`.
4. Optional có mặt tạo Stream 1 phần tử; Optional rỗng tạo Stream 0 phần tử.
5. `Stream.ofNullable(null)` tạo Stream rỗng.
6. `Stream::ofNullable` bỏ null trong danh sách nullable, sau đó `String::trim` xử lý chuỗi còn lại.
7. `flatMapToInt(OptionalInt::stream)` nối các `IntStream` có 0 hoặc 1 phần tử, cho tổng 7.
8. Lọc `n > 0` sau khi flatten, kết quả là `[10, 7]`.

Mọi thao tác trên collection trong ví dụ chạy theo thứ tự encounter order xác định. Chương trình không phụ thuộc thời gian hay lập lịch bất đồng bộ nên stdout có thể đối chiếu trực tiếp.

## 9. Tính lazy và vòng đời Stream

`Stream` sử dụng mô hình **pipeline lazy**: những thao tác trung gian như `map` và `flatMap` thường chưa chạy callback cho tới khi một thao tác đầu cuối (ví dụ `toList`, `count`, `forEach`, `sum`) bắt đầu traversal.

~~~java
List<String> raw = List.of("1", "2", "x");

Stream<Integer> pipeline = raw.stream()
        .map(s -> {
            System.out.println("parsing " + s);
            return parseInteger(s);
        })
        .flatMap(Optional::stream);

// Lúc này pipeline chưa được duyệt.
List<Integer> values = pipeline.toList(); // Bây giờ mới chạy mapper.
~~~

`Optional.stream()` không tự tạo xử lý bất đồng bộ hay trì hoãn việc **tạo Optional** đã có trước đó. Nếu các Optional được tạo sẵn trong một `List<Optional<T>>`, công việc tạo chúng đã hoàn tất; khi Stream được duyệt thì `flatMap` mới gọi `stream()` của từng Optional. Khi đọc hiệu ứng phụ trong `map`/`flatMap`, phải nhớ rằng Stream API có quyền tối ưu hóa các pipeline theo hợp đồng và side effect không nên dùng làm cơ sở thiết kế tính đúng đắn.

Ví dụ trên minh họa callback có side effect để nhìn thấy thời điểm chạy; trong thực tế nên ưu tiên hàm chuyển đổi không có side effect và sử dụng cơ chế logging thích hợp. Một Stream chỉ được tiêu thụ một lần; sau `pipeline.toList()` không được cố gọi tiếp `pipeline.count()` để tái sử dụng.

## 10. Hiệu năng và những giới hạn thực tế

### 10.1. Không tự mặc định mọi nơi đều cần `Optional.stream()`

Nếu cần đúng một giá trị, hãy giữ Optional và dùng các phương thức phù hợp:

~~~java
Optional<String> name = findName();

String display = name.orElse("Anonymous");
name.ifPresent(System.out::println);
~~~

Nếu đang có **nhiều Optional trong một Stream** và muốn lấy các phần tử có mặt, lúc đó `flatMap(Optional::stream)` đặc biệt phù hợp. Không cần đổi Optional thành Stream nếu ứng dụng chỉ cần `orElse` hay `ifPresent`.

### 10.2. Tạo Stream con có chi phí, nhưng đừng tối ưu bằng suy đoán

`Optional.stream()` tạo/đại diện một Stream con 0 hoặc 1 phần tử cho quá trình flatten. Khi xử lý tập dữ liệu rất lớn hoặc đường nóng về hiệu năng, có thể cân nhắc những cách khác sau khi đo bằng benchmark phù hợp. Sự rõ ràng và tính đúng của `flatMap(Optional::stream)` thường quan trọng hơn việc cố loại bỏ Stream con chỉ bằng trực giác.

Với dữ liệu có thể null mà không cần mô hình Optional, `Stream.ofNullable` tiết kiệm lớp diễn đạt trung gian. Với dữ liệu nguyên thủy, `OptionalInt.stream()` kết hợp `flatMapToInt` giúp tránh boxing cho các phần tử của luồng nguyên thủy.

### 10.3. Không thay thế xử lý lỗi nghiệp vụ

`Optional.empty()` chỉ cho biết không có giá trị; nó không giữ nguyên nhân thất bại. Khi dùng `flatMap(Optional::stream)`, các Optional rỗng biến mất khỏi dòng kết quả. Nếu cần thống kê số bản ghi không hợp lệ, trả thông báo lỗi cho người dùng hoặc audit dữ liệu nhập, hãy giữ thông tin lỗi trước khi flatten hoặc dùng kiểu kết quả thể hiện cả thành công và thất bại.

### 10.4. Null bên ngoài Optional vẫn có thể gây lỗi

Một `List<Optional<String>>` đúng thiết kế nên chứa các **đối tượng Optional khác null**. Nếu collection chứa chính một phần tử `null` thay vì `Optional.empty()`, đoạn:

~~~java
list.stream().flatMap(Optional::stream)
~~~

có thể ném `NullPointerException` vì cố gọi `stream()` trên Optional reference null. `Optional.stream()` xử lý trạng thái *Optional rỗng*, không tự bảo vệ trước một **biến Optional null**. Hãy chuẩn hóa nguồn dữ liệu hoặc xử lý null riêng, thay vì truyền null thay cho `Optional.empty()`.

## 11. Các lỗi phổ biến

| Lỗi | Vì sao sai/dễ nhầm | Cách sửa |
| --- | --- | --- |
| Dùng `optional.stream()` và tưởng kết quả luôn có một phần tử | Optional có thể rỗng | Nhớ kích thước 0 hoặc 1 |
| Dùng `map(Optional::stream)` khi cần giá trị `T` | Tạo `Stream<Stream<T>>` | Dùng `flatMap(Optional::stream)` |
| Dùng `Optional::get` trực tiếp trên Stream chứa Optional rỗng | `get()` có thể ném `NoSuchElementException` | Dùng `flatMap(Optional::stream)` |
| Truyền `Optional::stream` cho `Optional.flatMap` | `Optional.flatMap` yêu cầu callback trả Optional, không phải Stream | Dùng `optional.stream()` hoặc `Stream.flatMap` đúng ngữ cảnh |
| Gọi `flatMap(OptionalInt::stream)` | `OptionalInt.stream()` trả `IntStream` | Dùng `flatMapToInt(OptionalInt::stream)` |
| Dùng `Stream.of(nullable)` để loại null | Luồng chứa một phần tử null | Dùng `Stream.ofNullable(nullable)` |
| Coi `Optional.empty()` như lỗi có mô tả | Empty không giữ nguyên nhân | Dùng result type/diagnostics khi cần |
| Truyền null thay cho `Optional.empty()` | `Optional::stream` không gọi được trên reference null | Dùng Optional hợp lệ |
| Tái sử dụng Stream sau terminal operation | Stream không phải collection có thể duyệt vô hạn lần | Tạo pipeline mới |
| Giữ nguyên `map(Optional::stream)` vì kết quả “nhìn đúng” | Thực chất đang tạo luồng lồng nhau | Xem lại generic type và dùng flatMap |

## 12. Bài tập tự kiểm tra và lời giải

**Bài 1 — Phân tích kiểu.** Kiểu của `List<Optional<Integer>> values; values.stream().map(Optional::stream)` là gì?

**Lời giải:** `Stream<Stream<Integer>>`. `map` chỉ biến mỗi Optional thành Stream tương ứng, không nối các Stream con.

**Bài 2 — Làm phẳng.** Với ba phần tử `Optional.of("A")`, `Optional.empty()`, `Optional.of("C")`, kết quả `stream().flatMap(Optional::stream).toList()` là gì?

**Lời giải:** `[A, C]` theo thứ tự của danh sách nguồn. Optional rỗng tạo 0 phần tử.

**Bài 3 — Primitive Optional.** Vì sao `List<OptionalInt>.stream().flatMap(OptionalInt::stream)` không đúng kiểu, và cách thay thế là gì?

**Lời giải:** `flatMap` của `Stream` cần mapper trả `Stream<R>`, nhưng `OptionalInt::stream` trả `IntStream`. Dùng `flatMapToInt(OptionalInt::stream)`.

**Bài 4 — Null.** So sánh `Stream.of((String) null).count()` và `Stream.ofNullable((String) null).count()`.

**Lời giải:** Biểu thức đầu có kết quả `1` vì tạo luồng một phần tử null; biểu thức sau có kết quả `0` vì null được biểu diễn thành luồng rỗng.

**Bài 5 — Phân biệt hai flatMap.** `Optional<String> maybe = Optional.of("5");`; muốn tạo một `Optional<Integer>` bằng phương thức `parseInteger` trả `Optional<Integer>` thì dùng gì? Muốn lấy từ `Stream<Optional<Integer>>` ra `Stream<Integer>` thì dùng gì?

**Lời giải:** Với Optional đơn lẻ dùng `maybe.flatMap(MyParser::parseInteger)`. Với Stream chứa Optional dùng `stream.flatMap(Optional::stream)`.

**Bài 6 — Thiết kế API.** Một pipeline đọc các bản ghi trả về Optional vì không tìm thấy dữ liệu. Khi nào nên dùng `flatMap(Optional::stream)`?

**Lời giải:** Khi nghiệp vụ chủ ý **bỏ qua các bản ghi không có giá trị**, chỉ tiếp tục xử lý các bản ghi có mặt. Nếu cần đếm, ghi log hoặc phân loại các bản ghi không tìm thấy, hãy giữ thông tin ấy trước khi flatten.

## Ghi nhớ

`Optional.stream()` là cầu nối từ **“có hoặc không có một giá trị”** sang **“dòng 0 hoặc 1 phần tử”**. Khi đầu vào là `Stream<Optional<T>>`, cách dùng quan trọng nhất là:

~~~java
Stream<T> presentValues = streamOfOptionals.flatMap(Optional::stream);
~~~

Ở đây `flatMap` nối các Stream con và bỏ các nhánh rỗng mà không cần gọi `get()`. Với Optional nguyên thủy dùng `flatMapToInt`/`flatMapToLong`/`flatMapToDouble`; với giá trị nullable đơn giản có thể chọn `Stream.ofNullable`. Hãy phân biệt rõ `Optional.flatMap` với `Stream.flatMap`, hiểu kiểu kết quả trong từng bước và chỉ bỏ Optional rỗng khi đó là chính sách dữ liệu mong muốn.
