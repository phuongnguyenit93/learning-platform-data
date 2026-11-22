# Trải phẳng tập các Optional trong Stream bằng Java

## Mục tiêu

Trong Java, **Optional<T>** biểu diễn một giá trị có thể hiện diện hoặc vắng mặt. Khi một collection hoặc Stream chứa nhiều Optional, ta thường muốn loại bỏ các giá trị rỗng và thu được một Stream chứa trực tiếp các giá trị có mặt.

Từ Java 9, **Optional.stream()** cung cấp cách chuẩn để chuyển một Optional thành Stream có 0 hoặc 1 phần tử. Kết hợp với **Stream.flatMap()**, ta có thể trải phẳng **Stream<Optional<T>>** thành **Stream<T>** mà không cần tự viết điều kiện kiểm tra từng Optional.

Cách làm này vẫn là API hiện hành trong Java 17+. Java cũng có **OptionalInt.stream()**, **OptionalLong.stream()** và **OptionalDouble.stream()** để xử lý các giá trị nguyên thủy tương ứng.

## 1. Vì sao cần trải phẳng Optional?

Một Optional có hai trạng thái:

- **Optional.of(value)**: chứa một giá trị khác null.
- **Optional.empty()**: không chứa giá trị.

Khi nhiều Optional nằm trong một Stream, kiểu dữ liệu là **Stream<Optional<T>>**. Mỗi phần tử của Stream vẫn là một wrapper Optional, không phải giá trị T trực tiếp.

Ví dụ, một danh sách có thể chứa tên đã tìm thấy và tên không tồn tại:

```java
List<Optional<String>> names = List.of(
        Optional.of("Ada"),
        Optional.empty(),
        Optional.of("Linus"));
```

Nếu muốn thu được Stream<String> chỉ chứa các tên thực sự có mặt, ta cần thực hiện hai việc:

1. Chuyển mỗi Optional thành một Stream: Optional có giá trị tạo Stream một phần tử; Optional rỗng tạo Stream rỗng.
2. Nối các Stream con đó thành một Stream duy nhất.

Đó chính là công việc của **Optional.stream()** và **Stream.flatMap()**.

## 2. Optional.stream() hoạt động như thế nào?

**Optional.stream()** được bổ sung từ Java 9. Phương thức trả về một Stream tuần tự:

- Nếu Optional chứa giá trị, Stream có đúng một phần tử là giá trị đó.
- Nếu Optional rỗng, Stream không có phần tử nào.

Ví dụ:

```java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();

System.out.println(present.stream().count());
System.out.println(absent.stream().count());
```

Stdout:

```text
1
0
```

Optional.stream() không tạo ra một giá trị mặc định cho trường hợp rỗng. Nó biểu diễn trường hợp rỗng bằng Stream.empty(), do đó các thao tác tiếp theo có thể bỏ qua trường hợp này một cách tự nhiên.

Có thể dùng Optional.stream() độc lập để tiếp tục xử lý một giá trị có thể vắng mặt bằng các phép toán Stream:

```java
Optional<String> candidate = Optional.of("  Java  ");

List<String> result = candidate.stream()
        .map(String::trim)
        .filter(text -> !text.isEmpty())
        .toList();
```

Nếu Optional rỗng, các thao tác map và filter không nhận phần tử nào và kết quả là danh sách rỗng.

## 3. Stream.flatMap() dùng để làm gì?

**map()** biến đổi mỗi phần tử đầu vào thành đúng một phần tử đầu ra. Nếu hàm ánh xạ trả về một Stream, kết quả sẽ là Stream chứa các Stream con.

Ví dụ:

```java
Stream<Optional<String>> optionals = Stream.of(
        Optional.of("Ada"),
        Optional.empty(),
        Optional.of("Linus"));

Stream<Stream<String>> nested = optionals.map(Optional::stream);
```

Kiểu kết quả là **Stream<Stream<String>>**. Ta chưa có một Stream<String> phẳng; các Stream con vẫn là phần tử bên trong Stream ngoài.

**flatMap()** giải quyết việc này. Với mỗi phần tử, hàm ánh xạ trả về một Stream; flatMap lấy các phần tử từ từng Stream con và nối chúng thành một Stream kết quả duy nhất.

Chữ ký khái quát:

```java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper)
```

Khi dùng với Optional:

```java
List<String> names = Stream.of(
            Optional.of("Ada"),
            Optional.empty(),
            Optional.of("Linus"))
        .flatMap(Optional::stream)
        .toList();
```

Kết quả:

```text
[Ada, Linus]
```

Mỗi Optional được ánh xạ thành một Stream 0 hoặc 1 phần tử. flatMap nối tất cả phần tử đó lại, vì vậy Optional.empty() đóng góp 0 phần tử và không tạo giá trị null hay giá trị mặc định.

## 4. Công thức thường dùng: flatMap(Optional::stream)

Với nguồn dữ liệu có kiểu **Stream<Optional<T>>**, biểu thức sau là mẫu thông dụng:

```java
streamOfOptionals
        .flatMap(Optional::stream)
```

Kết quả có kiểu **Stream<T>**.

Có thể đọc biểu thức theo từng bước:

1. Stream ngoài lần lượt đưa từng Optional cho mapper.
2. Optional.stream() trả về Stream một phần tử hoặc Stream rỗng.
3. flatMap lấy phần tử bên trong các Stream con.
4. Các giá trị có mặt được nối theo encounter order của Stream nguồn khi nguồn có thứ tự.
5. Optional rỗng không đóng góp phần tử nào.

Đây là một cách diễn đạt ngắn gọn và an toàn kiểu để loại bỏ các Optional rỗng khi muốn làm việc trực tiếp với giá trị bên trong.

### So sánh map và flatMap

| Biểu thức | Kiểu kết quả | Ý nghĩa |
|---|---|---|
| **map(Optional::stream)** | **Stream<Stream<T>>** | Tạo một Stream con cho mỗi Optional |
| **flatMap(Optional::stream)** | **Stream<T>** | Trải phẳng các Stream con thành một Stream |
| **filter(Optional::isPresent)** | **Stream<Optional<T>>** | Giữ lại wrapper Optional có giá trị |
| **filter(Optional::isPresent).map(Optional::orElseThrow)** | **Stream<T>** | Lọc rồi lấy giá trị từ Optional còn lại |

Cách filter kết hợp map cũng có thể dùng, nhưng **flatMap(Optional::stream)** diễn đạt trực tiếp việc chuyển 0/1 giá trị thành luồng phần tử và không cần tách riêng bước kiểm tra trạng thái.

## 5. Ví dụ thực tế: tìm dữ liệu có thể không tồn tại

Một phương thức tra cứu thường trả về `Optional<T>` để biểu diễn rằng dữ liệu có thể được tìm thấy hoặc không. Khi cần tra cứu nhiều ID và chỉ giữ các email thực sự tồn tại, có thể kết hợp method reference với `flatMap(Optional::stream)`.

Ví dụ hoàn chỉnh sau tương thích với Java 9 trở lên. Phương thức `findEmail` được khai báo ngay trong lớp `EmailLookupDemo`, vì vậy method reference dùng tên lớp cụ thể, không cần placeholder:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public class EmailLookupDemo {
    private static Optional<String> findEmail(String userId) {
        switch (userId) {
            case "u1":
                return Optional.of("ada@example.com");
            case "u2":
                return Optional.empty();
            case "u3":
                return Optional.of("linus@example.com");
            default:
                return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> userIds = Arrays.asList("u1", "u2", "u3", "unknown");

        List<String> emails = userIds.stream()
                .map(EmailLookupDemo::findEmail)
                .flatMap(Optional::stream)
                .toList();

        System.out.println(emails);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 EmailLookupDemo.java
java EmailLookupDemo
```

Kết quả stdout:

```text
[ada@example.com, linus@example.com]
```

Kết quả chỉ gồm email của `u1` và `u3`. `u2` và `unknown` trả về `Optional.empty()`, vì vậy mỗi phần tử rỗng đóng góp 0 phần tử vào Stream sau khi flatten.

Cách này hữu ích khi tra cứu cache hoặc repository, phân tích dữ liệu có thể không hợp lệ, chuyển đổi chuỗi có thể thất bại hoặc lấy thuộc tính tùy chọn từ các phần tử trong collection. Nếu phương thức tra cứu nằm trong một lớp khác, hãy dùng method reference đến đúng lớp thực tế hoặc lambda tương ứng với chữ ký của phương thức.

## 6. Trải phẳng Optional từ các kiểu primitive

Java có ba Optional chuyên biệt cho kiểu số nguyên thủy:

| Kiểu Optional | Giá trị chứa | Phương thức stream |
|---|---|---|
| **OptionalInt** | **int** | Trả về **IntStream** có 0 hoặc 1 phần tử |
| **OptionalLong** | **long** | Trả về **LongStream** có 0 hoặc 1 phần tử |
| **OptionalDouble** | **double** | Trả về **DoubleStream** có 0 hoặc 1 phần tử |

Các phương thức stream() này cũng được bổ sung từ Java 9.

Khi nguồn là Stream chứa Optional primitive, hãy dùng đúng phương thức flatMap chuyên biệt:

- **Stream<OptionalInt>.flatMapToInt(OptionalInt::stream)**
- **Stream<OptionalLong>.flatMapToLong(OptionalLong::stream)**
- **Stream<OptionalDouble>.flatMapToDouble(OptionalDouble::stream)**

Ví dụ:

```java
List<OptionalInt> scores = List.of(
        OptionalInt.of(10),
        OptionalInt.empty(),
        OptionalInt.of(30));

int total = scores.stream()
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(total);
```

Stdout:

```text
40
```

Tương tự, với OptionalLong:

```java
List<OptionalLong> ids = List.of(
        OptionalLong.of(100L),
        OptionalLong.empty(),
        OptionalLong.of(300L));

long total = ids.stream()
        .flatMapToLong(OptionalLong::stream)
        .sum();
```

Với OptionalDouble:

```java
List<OptionalDouble> readings = List.of(
        OptionalDouble.of(1.5),
        OptionalDouble.empty(),
        OptionalDouble.of(2.5));

double average = readings.stream()
        .flatMapToDouble(OptionalDouble::stream)
        .average()
        .orElse(0.0);
```

Dùng các phương thức flatMapToInt, flatMapToLong và flatMapToDouble giúp giữ dữ liệu ở dạng primitive stream, phù hợp khi cần sum, average, min, max hoặc các phép tính số khác mà không phải boxing thành Integer, Long hay Double.

## 7. Ví dụ Java hoàn chỉnh

Ví dụ sau minh họa cả Optional object và ba Optional primitive. Mã dùng List.of() và Stream.toList(), do đó chạy trên Java 17+.

Tạo tệp **FlattenOptionalsDemo.java**:

```java
import java.util.List;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.Stream;

public class FlattenOptionalsDemo {
    public static void main(String[] args) {
        List<Optional<String>> values = List.of(
                Optional.of("Ada"),
                Optional.empty(),
                Optional.of("Linus"),
                Optional.of("Grace"));

        List<String> present = values.stream()
                .flatMap(Optional::stream)
                .toList();
        System.out.println("present: " + present);

        List<String> normalized = values.stream()
                .map(value -> value.orElse("(missing)"))
                .toList();
        System.out.println("normalized: " + normalized);

        List<OptionalInt> scores = List.of(
                OptionalInt.of(10), OptionalInt.empty(), OptionalInt.of(30));
        int scoreTotal = scores.stream()
                .flatMapToInt(OptionalInt::stream)
                .sum();
        System.out.println("score total: " + scoreTotal);

        List<OptionalLong> ids = List.of(
                OptionalLong.of(100L), OptionalLong.empty(), OptionalLong.of(300L));
        long idTotal = ids.stream()
                .flatMapToLong(OptionalLong::stream)
                .sum();
        System.out.println("id total: " + idTotal);

        List<OptionalDouble> readings = List.of(
                OptionalDouble.of(1.5), OptionalDouble.empty(), OptionalDouble.of(2.5));
        double average = readings.stream()
                .flatMapToDouble(OptionalDouble::stream)
                .average()
                .orElse(0.0);
        System.out.println("reading average: " + average);

        long nonBlankCount = Stream.of("one", " ", "three")
                .map(String::trim)
                .map(text -> text.isEmpty()
                        ? Optional.<String>empty()
                        : Optional.of(text))
                .flatMap(Optional::stream)
                .count();
        System.out.println("nonblank count: " + nonBlankCount);
    }
}
```

Biên dịch và chạy:

```bash
javac FlattenOptionalsDemo.java
java FlattenOptionalsDemo
```

Stdout chính xác:

```text
present: [Ada, Linus, Grace]
normalized: [Ada, (missing), Linus, Grace]
score total: 40
id total: 400
reading average: 2.0
nonblank count: 2
```

Giải thích:

- **present** chỉ chứa các giá trị thực sự có mặt; Optional.empty() bị loại bỏ trong bước flatMap.
- **normalized** giữ một phần tử cho mỗi đầu vào bằng cách thay trường hợp rỗng bằng chuỗi "(missing)". Đây là cách xử lý khác với flatten vì số phần tử đầu ra vẫn bằng số Optional đầu vào.
- **score total**, **id total** và **reading average** dùng primitive stream để tính toán trực tiếp.
- **nonBlankCount** minh họa tạo Optional từ kết quả xử lý rồi trải phẳng các giá trị không rỗng.

## 8. Optional.flatMap và Stream.flatMap là hai thao tác khác nhau

Hai phương thức cùng tên nhưng hoạt động trên hai abstraction khác nhau:

| Phương thức | Đầu vào | Hàm ánh xạ trả về | Kết quả |
|---|---|---|---|
| **Optional.flatMap()** | Một **Optional<T>** | **Optional<R>** | Một Optional, không tạo Optional lồng nhau |
| **Stream.flatMap()** | Một **Stream<T>** | **Stream<R>** cho mỗi phần tử | Một Stream đã trải phẳng |

Ví dụ với Optional.flatMap:

```java
Optional<String> name = Optional.of("Ada");

Optional<String> normalized = name.flatMap(
        value -> value.isBlank()
                ? Optional.empty()
                : Optional.of(value.trim()));
```

Phương thức này biến đổi một Optional thành một Optional khác. Nó không xử lý tập hợp nhiều Optional.

Ví dụ với Stream.flatMap:

```java
Stream<Optional<String>> names = Stream.of(
        Optional.of("Ada"),
        Optional.empty());

Stream<String> flattened = names.flatMap(Optional::stream);
```

Phương thức này xử lý từng Optional trong Stream và nối các giá trị thành một Stream duy nhất.

Khi đề bài nói "trải phẳng tập các Optional trong Stream", thao tác cần dùng là **Stream.flatMap(Optional::stream)**.

## 9. Trường hợp rỗng, null và thứ tự

### Optional.empty()

Optional.empty() được chuyển thành Stream rỗng. Khi flatMap xử lý Stream rỗng, nó không thêm phần tử nào vào kết quả.

Nếu tất cả Optional đều rỗng, Stream sau khi flatten cũng rỗng. Các terminal operation cần lưu ý trường hợp này:

- **count()** trả về 0.
- **toList()** trả về danh sách rỗng.
- **findFirst()** trả về Optional.empty().
- **average()** trên primitive stream trả OptionalDouble.empty(); cần dùng orElse hoặc orElseGet nếu muốn giá trị thay thế.

### Optional reference là null

Một Optional đúng cách không chứa null; hãy dùng Optional.empty() hoặc Optional.ofNullable(value) để biểu diễn giá trị có thể null.

Nếu chính đối tượng Optional trong Stream lại là null, **Optional::stream** sẽ gây NullPointerException. Ví dụ, Stream.of(Optional.of("A"), null) không phải nguồn dữ liệu Optional hợp lệ để dùng trực tiếp với flatMap(Optional::stream).

Hãy chuẩn hóa dữ liệu ngay khi tạo Optional:

```java
String raw = getPossiblyNullValue();
Optional<String> value = Optional.ofNullable(raw);
```

Sau đó đưa Optional không null vào collection hoặc Stream.

Nếu hệ thống đầu vào bắt buộc có thể chứa cả tham chiếu Optional null, cần xác định chính sách xử lý null rõ ràng. Có thể xử lý riêng bằng mapper có kiểm tra null, nhưng trong API nội bộ nên duy trì invariant rằng bản thân Optional không bao giờ null.

### Thứ tự phần tử

Với Stream nguồn có encounter order, flatMap giữ thứ tự các phần tử được phát ra từ từng Stream con theo thứ tự nguồn. Optional chỉ chứa tối đa một phần tử, vì vậy các giá trị còn lại xuất hiện theo thứ tự Optional ban đầu.

Không nên thêm unordered() nếu thứ tự kết quả là yêu cầu nghiệp vụ. Với parallel stream, thứ tự kết quả vẫn được bảo toàn khi pipeline yêu cầu encounter order và terminal operation phù hợp, nhưng việc xử lý song song có thể làm thay đổi thời điểm thực thi các mapper.

## 10. Khi nào nên flatten và khi nào nên dùng giá trị thay thế?

Chọn cách xử lý theo ý nghĩa dữ liệu:

- Dùng **flatMap(Optional::stream)** khi muốn bỏ qua các trường hợp không có giá trị và xử lý một Stream chỉ gồm các giá trị hiện diện.
- Dùng **map(optional -> optional.orElse(defaultValue))** khi mỗi đầu vào phải tạo đúng một kết quả và trường hợp rỗng cần giá trị thay thế.
- Dùng **filter(Optional::isPresent)** khi muốn giữ lại wrapper Optional để xử lý trạng thái sau đó; nếu cần lấy giá trị, có thể map tiếp bằng **Optional::orElseThrow** sau filter.
- Dùng **Optional.map()** khi chỉ có một Optional và muốn biến đổi giá trị bên trong nó.
- Dùng **Optional.flatMap()** khi phép biến đổi của một giá trị đã trả về Optional và muốn tránh Optional lồng nhau.

Không có cách nào luôn đúng cho mọi tình huống. Flatten làm giảm số phần tử khi Optional rỗng; thay thế bằng default giữ số phần tử và mang một ý nghĩa nghiệp vụ khác.

## 11. Lỗi thường gặp

1. **Dùng map thay vì flatMap**: kết quả là Stream<Stream<T>>, không phải Stream<T>. Hãy dùng flatMap(Optional::stream).
2. **Nhầm Optional.stream() với Stream.of(optional)**: Stream.of(optional) tạo một Stream chứa chính Optional; nó không lấy giá trị bên trong.
3. **Gọi get() mà chưa kiểm tra**: Optional.get() ném NoSuchElementException nếu Optional rỗng. Dùng stream() khi muốn bỏ qua trường hợp rỗng hoặc dùng orElse/orElseThrow khi muốn xử lý rõ ràng.
4. **Nhầm Optional.flatMap với Stream.flatMap**: một phương thức xử lý một Optional, phương thức kia trải phẳng các Stream con.
5. **Cho rằng Optional reference null tương đương Optional.empty()**: null là tham chiếu không hợp lệ; gọi stream() trên nó gây NullPointerException.
6. **Dùng flatMap khi cần giữ một kết quả cho mọi đầu vào**: flatten loại bỏ phần tử rỗng. Nếu cần giữ vị trí hoặc số lượng đầu vào, hãy ánh xạ Optional sang giá trị thay thế phù hợp.
7. **Boxing dữ liệu số không cần thiết**: với OptionalInt, OptionalLong và OptionalDouble, dùng flatMapToInt, flatMapToLong và flatMapToDouble để giữ primitive stream.
8. **Tái sử dụng Stream đã tiêu thụ**: Stream là pipeline dùng một lần. Sau terminal operation, hãy tạo Stream mới từ nguồn nếu cần xử lý lần nữa.

## Kết luận

Để trải phẳng một Stream chứa nhiều Optional, hãy chuyển mỗi Optional thành Stream 0 hoặc 1 phần tử bằng **Optional.stream()**, sau đó dùng **Stream.flatMap(Optional::stream)**. Kết quả là một Stream chỉ chứa các giá trị hiện diện, không còn lớp Optional bao quanh và không cần tự kiểm tra từng phần tử.

Với kiểu nguyên thủy, dùng **OptionalInt.stream()**, **OptionalLong.stream()**, **OptionalDouble.stream()** cùng **flatMapToInt**, **flatMapToLong** và **flatMapToDouble**. Chọn flatten khi muốn bỏ qua giá trị vắng mặt; chọn giá trị mặc định khi nghiệp vụ yêu cầu giữ một kết quả cho mỗi đầu vào.
