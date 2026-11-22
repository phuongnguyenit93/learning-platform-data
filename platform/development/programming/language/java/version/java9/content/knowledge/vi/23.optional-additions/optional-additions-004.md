# Chuyển Optional thành luồng bằng stream

## Mục tiêu

Java 9 bổ sung phương thức `Optional.stream()` để chuyển một giá trị có thể có hoặc không thành một Stream. Nếu Optional chứa giá trị, Stream tạo ra có đúng một phần tử; nếu Optional rỗng, Stream tạo ra không có phần tử nào.

Cơ chế này đặc biệt hữu ích khi một pipeline Stream tạo ra nhiều Optional. Thay vì kiểm tra từng Optional rồi tự thêm giá trị vào một Collection, có thể dùng `flatMap(Optional::stream)` để loại bỏ các Optional rỗng và trải phẳng những giá trị hiện diện thành một Stream thông thường.

## 1. Optional.stream() là gì?

Với `Optional<T>`, phương thức:

~~~java
Stream<T> stream()
~~~

trả về một Stream tuần tự:

- Optional có giá trị: Stream chứa đúng giá trị đó.
- Optional rỗng: Stream rỗng, không chứa phần tử.
- Giá trị bên trong không bị thay đổi hoặc sao chép thành một đối tượng khác.

Ví dụ:

~~~java
Optional<String> present = Optional.of("Java 9");
Optional<String> empty = Optional.empty();

System.out.println(present.stream().toList());
System.out.println(empty.stream().toList());
~~~

Kết quả:

~~~text
[Java 9]
[]
~~~

Có thể xem Optional như một cấu trúc chứa tối đa một giá trị, còn Stream có thể biểu diễn không, một hoặc nhiều giá trị. `Optional.stream()` tạo cầu nối từ cấu trúc 0..1 sang Stream 0..1.

Phương thức này có từ Java 9. Ví dụ dùng `Stream.toList()` cần Java 16 trở lên; với Java 9 đến Java 15, có thể dùng `collect(Collectors.toList())`.

## 2. Vì sao cần chuyển Optional thành Stream?

Một tình huống thường gặp là xử lý một danh sách đầu vào, trong đó mỗi phần tử được chuyển thành Optional. Đoạn mã sau minh họa kiểu dữ liệu trung gian; `parseInteger` là hàm chuyển đổi trả về `Optional<Integer>`:

~~~java
List<String> inputs = List.of("10", "20", "invalid", "30");

Stream<Optional<Integer>> parsed = inputs.stream()
        .map(value -> parseInteger(value));
~~~

Sau thao tác map, kiểu dữ liệu là `Stream<Optional<Integer>>`, không phải `Stream<Integer>`. Mỗi phần tử vẫn là một Optional, kể cả khi Optional đó rỗng.

Nếu muốn tiếp tục tính toán trên các số hợp lệ, cần chuyển mỗi Optional thành Stream rồi trải phẳng các Stream con:

~~~java
List<Integer> numbers = inputs.stream()
        .map(value -> parseInteger(value))
        .flatMap(Optional::stream)
        .toList();
~~~

Kết quả chỉ còn các số chuyển đổi thành công. Những Optional.empty() đóng góp một Stream rỗng nên không tạo phần tử trong kết quả.

### Luồng xử lý

~~~text
List<String>
    |
    v
map(parseInteger)
    |
    v
Stream<Optional<Integer>>
    |
    v
flatMap(Optional::stream)
    |
    v
Stream<Integer>
    |
    v
collect / toList / sum / reduce
~~~

`flatMap(Optional::stream)` là phần quan trọng: nó chuyển từng Optional thành Stream 0..1 phần tử và hợp nhất các Stream con thành một Stream phẳng.

## 3. Phân biệt map và flatMap khi làm việc với Optional

Đây là lỗi dễ gặp nhất khi chuyển Optional thành Stream.

### Dùng map(Optional::stream)

~~~java
Stream<Stream<String>> nested = optionals.stream()
        .map(Optional::stream);
~~~

map chỉ thay đổi từng phần tử. Vì hàm được truyền vào trả về Stream<String>, kết quả trở thành Stream<Stream<String>>. Các Stream con vẫn còn lồng bên trong.

### Dùng flatMap(Optional::stream)

~~~java
Stream<String> flattened = optionals.stream()
        .flatMap(Optional::stream);
~~~

flatMap lấy các phần tử từ từng Stream con rồi hợp nhất chúng. Kết quả là một Stream<String> phẳng.

| Cách viết | Kiểu kết quả | Ý nghĩa |
|---|---|---|
| `map(Optional::stream)` | `Stream<Stream<T>>` | Tạo Stream lồng nhau |
| `flatMap(Optional::stream)` | `Stream<T>` | Trải phẳng và bỏ Optional rỗng |
| `map(Optional::get)` | `Stream<T>` | Lấy giá trị trực tiếp, có thể ném NoSuchElementException nếu gặp Optional rỗng |

Không nên dùng `map(Optional::get)` để thay thế flatMap. Chỉ cần một Optional rỗng là pipeline có thể thất bại khi terminal operation tiêu thụ phần tử đó.

## 4. Ví dụ: lọc và chuyển đổi nhiều giá trị

Giả sử dữ liệu đầu vào là các chuỗi số, nhưng một số chuỗi không hợp lệ hoặc chứa số không dương. Ta muốn chỉ giữ các số nguyên dương.

~~~java
private static Optional<Integer> parsePositiveInt(String text) {
    try {
        int value = Integer.parseInt(text);
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
~~~

Hàm trên trả về Optional có giá trị khi chuyển đổi thành công và số dương; các trường hợp không hợp lệ trả về Optional.empty().

Pipeline sử dụng hàm này:

~~~java
List<Integer> values = rawValues.stream()
        .map(OptionalStreamDemo::parsePositiveInt)
        .flatMap(Optional::stream)
        .toList();
~~~

Sau flatMap, các thao tác tiếp theo làm việc trực tiếp với Integer. Có thể tiếp tục lọc, sắp xếp, tính tổng hoặc gom nhóm mà không phải mở Optional thủ công.

## 5. Kết hợp với các thao tác Stream khác

Sau khi chuyển Optional thành Stream, có thể dùng các thao tác Stream thông thường.

### Lọc giá trị

~~~java
List<String> names = optionals.stream()
        .flatMap(Optional::stream)
        .filter(name -> name.length() >= 4)
        .toList();
~~~

Các Optional rỗng bị loại bỏ khi trải phẳng; filter tiếp tục chỉ giữ tên có độ dài ít nhất bốn ký tự.

### Chuyển đổi giá trị

~~~java
List<String> labels = optionals.stream()
        .flatMap(Optional::stream)
        .map(String::toUpperCase)
        .toList();
~~~

map hoạt động trên giá trị thực, không phải trên Optional.

### Tính tổng

~~~java
int total = optionalNumbers.stream()
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();
~~~

Optional rỗng không đóng góp số nào. mapToInt chuyển Stream<Integer> thành IntStream để tính tổng mà không cần tự cộng từng giá trị.

### Kết hợp với findFirst và findAny

~~~java
Optional<String> firstName = optionals.stream()
        .flatMap(Optional::stream)
        .findFirst();
~~~

findFirst trả về Optional mới vì kết quả tìm kiếm vẫn có thể không tồn tại. Việc chuyển Optional thành Stream không loại bỏ khả năng kết quả cuối cùng rỗng.

## 6. Optional primitive cũng hỗ trợ stream()

Java 9 đồng thời bổ sung phương thức stream() cho ba kiểu Optional chuyên biệt:

| Kiểu Optional | Kiểu Stream trả về |
|---|---|
| `OptionalInt` | `IntStream` |
| `OptionalLong` | `LongStream` |
| `OptionalDouble` | `DoubleStream` |

Ví dụ:

~~~java
OptionalInt maybeInt = OptionalInt.of(42);
OptionalLong maybeLong = OptionalLong.empty();
OptionalDouble maybeDouble = OptionalDouble.of(3.5);

System.out.println(maybeInt.stream().sum());
System.out.println(maybeLong.stream().count());
System.out.println(maybeDouble.stream().average().orElse(0.0));
~~~

Kết quả:

~~~text
42
0
3.5
~~~

Các Stream primitive này có thể dùng các thao tác chuyên biệt như sum(), average(), min(), max() mà không cần chuyển qua Stream wrapper trước.

Nếu đang xử lý `Stream<OptionalInt>`, có thể viết:

~~~java
IntStream values = optionalInts.stream()
        .flatMapToInt(OptionalInt::stream);
~~~

Tương tự, `OptionalLong::stream` dùng với `flatMapToLong`, còn `OptionalDouble::stream` dùng với `flatMapToDouble`.

## 7. Optional.stream() và Stream.ofNullable()

Java 9 cũng bổ sung `Stream.ofNullable(value)`. Hai API có liên quan nhưng nhận đầu vào khác nhau:

- `optional.stream()` chuyển một Optional thành Stream.
- `Stream.ofNullable(value)` chuyển một tham chiếu có thể null thành Stream rỗng hoặc Stream có một phần tử.

Ví dụ:

~~~java
Optional<String> optional = Optional.of("Java");
String nullable = null;

Stream<String> fromOptional = optional.stream();
Stream<String> fromNullable = Stream.ofNullable(nullable);
~~~

Cả hai đều có thể tạo Stream rỗng, nhưng không nên nhầm Optional với null. Optional biểu đạt sự có mặt hoặc vắng mặt một cách tường minh; Stream.ofNullable phù hợp khi nguồn dữ liệu là một tham chiếu có thể null.

Nếu biến Optional bản thân nó là null, gọi `optional.stream()` vẫn gây NullPointerException. Hợp đồng sử dụng Optional thông thường là không dùng null để biểu diễn một Optional chưa có giá trị; hãy dùng Optional.empty().

## 8. Ví dụ hoàn chỉnh có thể chạy

Tệp `OptionalStreamDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

public class OptionalStreamDemo {
    private static Optional<Integer> parsePositiveInt(String text) {
        try {
            int value = Integer.parseInt(text);
            return value > 0 ? Optional.of(value) : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> rawValues = List.of("12", "abc", "0", "30", "7");

        List<Integer> parsed = rawValues.stream()
                .map(OptionalStreamDemo::parsePositiveInt)
                .flatMap(Optional::stream)
                .toList();

        int sum = parsed.stream()
                .mapToInt(Integer::intValue)
                .sum();

        List<String> words = List.of("java", " ", "stream");

        List<String> nonBlankWords = words.stream()
                .map(String::trim)
                .map(value -> value.isEmpty()
                        ? Optional.<String>empty()
                        : Optional.of(value))
                .flatMap(Optional::stream)
                .map(String::toUpperCase)
                .collect(Collectors.toList());

        OptionalDouble average = parsed.stream()
                .mapToInt(Integer::intValue)
                .average();

        System.out.println("parsed: " + parsed);
        System.out.println("sum: " + sum);
        System.out.println("non-blank: " + nonBlankWords);
        System.out.println("average: " + average.orElse(0.0));
        System.out.println("empty stream count: "
                + Optional.<String>empty().stream().count());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 OptionalStreamDemo.java
java OptionalStreamDemo
~~~

Kết quả chuẩn:

~~~text
parsed: [12, 30, 7]
sum: 49
non-blank: [JAVA, STREAM]
average: 16.333333333333332
empty stream count: 0
~~~

Ví dụ thực hiện hai tình huống:

1. Chuyển các chuỗi số thành Optional<Integer>, sau đó trải phẳng để chỉ giữ các số nguyên dương hợp lệ.
2. Chuẩn hóa chuỗi, biểu diễn chuỗi rỗng bằng Optional.empty(), rồi trải phẳng và chuyển các giá trị còn lại thành chữ hoa.

average() trả về OptionalDouble vì Stream có thể không có phần tử. orElse(0.0) cung cấp giá trị thay thế khi không có số để tính trung bình.

## 9. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Dùng map(Optional::stream) khi muốn Stream<T> | Kết quả là Stream<Stream<T>> | Dùng flatMap(Optional::stream) |
| Dùng map(Optional::get) | Optional rỗng gây NoSuchElementException | Trải phẳng bằng flatMap(Optional::stream) |
| Nghĩ Optional.stream() luôn tạo một phần tử | Optional.empty() tạo Stream rỗng | Kiểm tra kết quả và xử lý trường hợp không có phần tử |
| Gọi stream() trên Optional null | Tham chiếu null gây NullPointerException | Không dùng null làm Optional; dùng Optional.empty() |
| Dùng lại một Stream sau terminal operation | Stream đã được tiêu thụ | Tạo pipeline hoặc Stream mới |
| Chuyển Optional primitive sang Stream wrapper không cần thiết | Có thể phát sinh boxing | Dùng OptionalInt/Long/Double và flatMapToInt/Long/Double khi phù hợp |
| Dùng Stream cho một Optional đơn lẻ dù không cần pipeline | Tạo thêm cấu trúc xử lý không cần thiết | Dùng ifPresent, ifPresentOrElse, map, orElse hoặc orElseGet phù hợp |

## 10. Khi nào nên dùng Optional.stream()?

Nên dùng khi:

- Có một `Stream<Optional<T>>` và cần lấy các giá trị hiện diện thành `Stream<T>`.
- Mỗi phần tử đầu vào có thể tạo ra không hoặc một kết quả.
- Muốn kết hợp Optional với filter, map, sorted, distinct, collect hoặc các thao tác Stream khác.
- Muốn tránh tự quản lý Collection mutable và tránh gọi get() trên Optional rỗng.
- Đang làm việc với OptionalInt, OptionalLong hoặc OptionalDouble và muốn dùng các phép toán trên primitive Stream.

Không cần chuyển một Optional đơn lẻ thành Stream nếu chỉ muốn thực hiện một hành động hoặc lấy giá trị thay thế. Trong trường hợp đó, ifPresent, ifPresentOrElse, orElse, orElseGet hoặc map thường trực tiếp và dễ đọc hơn.

## 11. Checklist ghi nhớ

- `Optional.stream()` có từ Java 9.
- Optional có giá trị tạo Stream một phần tử; Optional rỗng tạo Stream rỗng.
- Dùng `flatMap(Optional::stream)` để chuyển `Stream<Optional<T>>` thành `Stream<T>`.
- `map(Optional::stream)` tạo Stream lồng nhau, không trải phẳng.
- Tránh `Optional.get()` trong pipeline khi Optional có thể rỗng.
- OptionalInt, OptionalLong và OptionalDouble cũng có stream() trả về Stream primitive tương ứng.
- Phân biệt Optional.stream() với Stream.ofNullable().
- Không dùng null để biểu diễn một Optional rỗng.
- Mỗi Stream chỉ được tiêu thụ một lần.
- Chọn Optional API trực tiếp nếu không cần các thao tác của Stream.

Optional.stream() giúp kết nối mô hình giá trị có thể vắng mặt với Stream một cách tự nhiên. Khi kết hợp đúng với flatMap, các pipeline có thể xử lý nhiều kết quả tùy chọn mà không phải lồng Optional, kiểm tra rỗng thủ công hoặc gọi get() không an toàn.