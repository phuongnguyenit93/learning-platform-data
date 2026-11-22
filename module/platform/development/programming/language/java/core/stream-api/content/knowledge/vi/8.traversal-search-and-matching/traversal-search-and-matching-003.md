# Tìm phần tử bằng `findFirst` và `findAny`

Trong **Java Stream API**, các phép toán `filter`, `map`, `distinct`, `sorted` và các phép toán cắt lát giúp mô tả cách chọn, biến đổi và sắp xếp dữ liệu theo một pipeline *lazy*. Khi mục tiêu chỉ là **tìm một phần tử phù hợp**, hai phép toán kết thúc thường dùng là `findFirst()` và `findAny()`. Chúng có vẻ giống nhau vì đều trả về `Optional<T>`, nhưng đưa ra hai hợp đồng khác nhau về **thứ tự gặp phần tử** (*encounter order*).

Điểm cần nắm là: **`findFirst()` cần phần tử đầu tiên theo encounter order nếu thứ tự ấy tồn tại; `findAny()` có thể chọn bất kỳ phần tử nào**. Sự khác biệt ảnh hưởng đến tính xác định của kết quả, khả năng xử lý song song và đôi khi cả hiệu năng.

## 1. Hai phép toán kết thúc ngắn mạch

Đối với `Stream<T>`, chữ ký đơn giản hóa là:

```java
Optional<T> findFirst();
Optional<T> findAny();
```

Đây là hai **terminal operation có khả năng ngắn mạch** (*short-circuiting terminal operations*). Khi tìm được kết quả hợp lệ, chúng có thể kết thúc mà không cần xử lý toàn bộ nguồn dữ liệu.

| Tiêu chí | `findFirst()` | `findAny()` |
| --- | --- | --- |
| Ý nghĩa | Lấy phần tử **đầu tiên theo encounter order**, nếu có. | Lấy **một phần tử bất kỳ**, nếu có. |
| Nguồn có thứ tự | Phải tôn trọng thứ tự gặp phần tử. | Không bị ràng buộc phải chọn phần tử đầu tiên. |
| Nguồn không có thứ tự | Có thể trả về một phần tử bất kỳ. | Có thể trả về một phần tử bất kỳ. |
| Kết quả khi stream rỗng | `Optional.empty()` | `Optional.empty()` |
| Khả năng ngắn mạch | Có. | Có. |
| Xử lý song song | Có thể tốn chi phí phối hợp để giữ thứ tự. | Thường có thêm cơ hội tối ưu khi thứ tự không quan trọng. |

Hai phương thức có từ **Java 8**. Kết quả của cả hai đều là `Optional` vì một stream có thể không chứa phần tử nào sau khi lọc. Với `IntStream`, `LongStream`, `DoubleStream`, API tương ứng trả về `OptionalInt`, `OptionalLong`, `OptionalDouble`.

### Ví dụ đầu tiên

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public class FindExample {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi", "Dung");

        Optional<String> first = names.stream()
            .filter(name -> name.length() >= 4)
            .findFirst();

        Optional<String> any = names.stream()
            .filter(name -> name.length() >= 4)
            .findAny();

        System.out.println(first.orElse("Không tìm thấy")); // Binh
        System.out.println(any.orElse("Không tìm thấy"));   // Có thể là Binh hoặc Dung
    }
}
```

Danh sách có encounter order là `An → Binh → Chi → Dung`. Sau `filter`, các phần tử phù hợp theo thứ tự là `Binh → Dung`, nên `findFirst()` **bắt buộc** trả `Binh`. `findAny()` được phép trả `Binh` hoặc `Dung`; trên một lần chạy tuần tự cụ thể, nó thường cũng trả phần tử đầu nhưng **đó không phải hợp đồng để dựa vào**.

## 2. Encounter order được xác định từ nguồn và pipeline

**Encounter order** là thứ tự logic mà stream nhận các phần tử từ nguồn và qua các phép toán trung gian. Nó không đồng nghĩa với thứ tự được CPU thực thi, cũng không tự động là thứ tự tăng dần về giá trị.

Những nguồn thông dụng:

| Nguồn | Có encounter order xác định? | Ghi chú |
| --- | --- | --- |
| `List.stream()`, `ArrayList.stream()` | Có. | Theo vị trí trong danh sách. |
| `Arrays.stream(array)`, `Stream.of(...)` | Có. | Theo thứ tự trong mảng hoặc đối số. |
| `LinkedHashSet.stream()` | Có. | Theo thứ tự duyệt của `LinkedHashSet`, thường là thứ tự thêm. |
| `TreeSet.stream()` | Có. | Theo thứ tự của comparator hoặc thứ tự tự nhiên. |
| `HashSet.stream()` | Không có bảo đảm encounter order. | Không dùng `findFirst` để suy ra phần tử ổn định. |
| `Stream.generate(supplier)` | Không có bảo đảm encounter order. | Giá trị được sinh khi pipeline yêu cầu. |

Ví dụ, `findFirst()` không phải phép toán tìm giá trị nhỏ nhất:

```java
import java.util.Arrays;

System.out.println(
    Arrays.asList(30, 10, 20).stream().findFirst().get()
); // 30
```

Nếu bài toán cần **giá trị nhỏ nhất**, có thể dùng `min` hoặc sắp xếp trước khi tìm:

```java
import java.util.Arrays;

int smallest = Arrays.asList(30, 10, 20).stream()
    .min(Integer::compareTo)
    .orElseThrow(IllegalStateException::new);

System.out.println(smallest); // 10
```

`min` thường tiết kiệm công việc hơn `sorted().findFirst()` khi chỉ cần giá trị nhỏ nhất: `min` duyệt để giảm giá trị, còn `sorted` phải xét và tổ chức toàn bộ phần tử để bảo đảm thứ tự tăng dần. `min` **không** là terminal operation ngắn mạch trên dữ liệu thông thường; nó vẫn cần so sánh các phần tử còn lại.

### Phép toán trung gian có thể thay đổi thứ tự logic

```java
import java.util.Arrays;

Integer originalFirst = Arrays.asList(30, 10, 20).stream()
    .findFirst().orElse(-1);

Integer sortedFirst = Arrays.asList(30, 10, 20).stream()
    .sorted()
    .findFirst().orElse(-1);

System.out.println(originalFirst); // 30
System.out.println(sortedFirst);   // 10
```

`filter` giữ tương quan thứ tự của các phần tử còn lại đối với stream có thứ tự. `sorted` tạo thứ tự mới dựa trên comparator. `unordered()` **gỡ ràng buộc thứ tự** khỏi pipeline; điều này không nhất thiết đổi ngay thứ tự trong một lần chạy, nhưng từ điểm đó không được trông đợi `findFirst` giữ phần tử đầu của nguồn gốc.

Ví dụ:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> result = Arrays.asList(30, 10, 20).parallelStream()
    .unordered()
    .findFirst();

// Có thể là 30, 10 hoặc 20: thứ tự gặp phần tử không còn được bảo đảm.
```

Khi nghiệp vụ yêu cầu “đầu tiên”, phải định nghĩa **đầu tiên theo thứ tự nào**: thứ tự nhập, thời điểm, độ ưu tiên hay chỉ số. Nếu đầu vào chưa có thứ tự tương ứng, cần sắp xếp hoặc chọn bằng comparator trước.

## 3. Kết quả là `Optional<T>`: xử lý cả trường hợp không tìm thấy

Cả hai phương thức đều trả về `Optional<T>`. Đây là dấu hiệu ở cấp kiểu rằng kết quả **có thể vắng mặt**:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<String> found = Arrays.asList("A", "BB", "CCC").stream()
    .filter(text -> text.length() > 10)
    .findFirst();

System.out.println(found.isPresent());       // false
System.out.println(found.orElse("Không có")); // Không có
```

Cách xử lý thông dụng:

| Cách dùng | Ý nghĩa |
| --- | --- |
| `ifPresent(action)` | Chỉ thực hiện hành động nếu có phần tử. |
| `orElse(defaultValue)` | Trả giá trị dự phòng đã tính sẵn khi rỗng. |
| `orElseGet(supplier)` | Tạo giá trị dự phòng **khi cần** bằng `Supplier`. |
| `orElseThrow(...)` | Báo lỗi rõ ràng nếu thiếu phần tử bắt buộc. |
| `map(transform)` | Biến đổi giá trị bên trong `Optional` nếu nó tồn tại. |

Ví dụ xử lý kết quả mà không dùng `get()` một cách mù quáng:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<String> task = Arrays.asList("open", "closed", "pending").stream()
    .filter(value -> value.startsWith("pend"))
    .findFirst();

String label = task.map(String::toUpperCase)
    .orElseGet(() -> "NO_TASK");

System.out.println(label); // PENDING
```

`Optional.get()` ném `NoSuchElementException` nếu rỗng. Chỉ dùng nó khi chắc chắn có giá trị hoặc đã kiểm tra `isPresent()`; trong hầu hết tình huống, `orElse`, `orElseThrow` và `ifPresent` rõ ý nghĩa hơn.

**Không dùng phần tử `null` làm giá trị kết quả.** Nếu phần tử được hai phép `find*` chọn là `null`, chúng ném `NullPointerException`. Trường hợp nguồn có thể chứa `null`, lọc trước:

```java
import java.util.Arrays;
import java.util.Objects;

String value = Arrays.asList(null, "A", "B").stream()
    .filter(Objects::nonNull)
    .findFirst()
    .orElse("n/a");

System.out.println(value); // A
```

### Phiên bản cho primitive stream

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt firstLarge = IntStream.of(5, 8, 13, 21)
    .filter(n -> n > 10)
    .findFirst();

System.out.println(firstLarge.orElse(-1)); // 13
```

`OptionalInt` giúp giữ giá trị nguyên trong API primitive, tránh boxing sang `Integer`. Với số thực và số nguyên dài, dùng `DoubleStream.findFirst`/`findAny` hoặc `LongStream.findFirst`/`findAny` tương ứng.

## 4. Vì sao nói đây là phép toán kết thúc ngắn mạch?

Một pipeline Stream gồm nguồn, các bước trung gian lazy và một phép toán kết thúc. `findFirst` hoặc `findAny` có thể quyết định kết quả **trước khi duyệt hết nguồn**.

```java
import java.util.Arrays;

String firstEvenText = Arrays.asList(3, 7, 8, 10, 12).stream()
    .filter(n -> n % 2 == 0)
    .map(n -> "even-" + n)
    .findFirst()
    .orElse("none");

System.out.println(firstEvenText); // even-8
```

Khi chạy tuần tự trên danh sách có thứ tự, pipeline đơn giản này có thể kết thúc sau khi gặp `8`; không cần kết quả từ `10` hay `12`. Tuy nhiên, **ngắn mạch không hứa số lần lambda chạy cố định**: JVM được phép tối ưu pipeline; trong chế độ song song, một số phần tử phía sau có thể đã được xử lý khi kết quả được chọn.

Vì vậy, viết `peek(System.out::println)` để “xác nhận mọi phần tử đều đã được xử lý” là sai. Không dùng `filter`, `map` hoặc `peek` để thực hiện những hiệu ứng phụ bắt buộc với *tất cả* phần tử như gửi yêu cầu thanh toán, ghi sổ hoặc cập nhật biến đếm bên ngoài.

### Khi nào phải duyệt nhiều phần tử?

`findFirst()` không mặc nhiên có độ phức tạp O(1). Nếu cần phần tử đầu tiên thỏa điều kiện mà nó nằm rất muộn, pipeline phải xét các phần tử trước đó. Nếu không có phần tử nào thỏa điều kiện trong nguồn hữu hạn, pipeline cần xác nhận hết nguồn:

```java
import java.util.stream.IntStream;

int number = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n == 999_999)
    .findFirst()
    .orElse(-1);

System.out.println(number); // 999999
```

`sorted()` còn là phép trung gian **có trạng thái**, thường phải đọc hết nguồn hữu hạn trước khi trả phần tử đầu của kết quả đã sắp xếp. `distinct()`, `skip()`, `limit()` và các thao tác giữ encounter order cũng có thể ảnh hưởng đến số phần tử cần duyệt. Đặt `limit` trước hay sau `filter` còn có thể thay đổi **ý nghĩa**:

```java
import java.util.Arrays;

Integer a = Arrays.asList(1, 3, 8, 10).stream()
    .limit(2).filter(n -> n % 2 == 0)
    .findFirst().orElse(-1);

Integer b = Arrays.asList(1, 3, 8, 10).stream()
    .filter(n -> n % 2 == 0).limit(2)
    .findFirst().orElse(-1);

System.out.println(a); // -1: chỉ xem hai phần tử đầu là 1, 3
System.out.println(b); // 8: lấy tối đa hai phần tử chẵn
```

## 5. Stream vô hạn và điều kiện tìm kiếm

`Stream.iterate` và `Stream.generate` có thể tạo nguồn không giới hạn. Hai phép `find*` **có khả năng dừng sớm**, nhưng không bảo đảm sẽ tìm được kết quả. Điều kiện quyết định là có thật sự xuất hiện một phần tử phù hợp ở vị trí hữu hạn và các bước phía trước có thể cung cấp phần tử ấy hay không.

```java
import java.util.stream.Stream;

long found = Stream.iterate(1L, n -> n + 1)
    .filter(n -> n % 7 == 0)
    .findFirst()
    .orElse(-1L);

System.out.println(found); // 7
```

Ngược lại, đoạn sau **không nên thực thi** vì không có điều kiện kết thúc:

```java
// KHÔNG CHẠY:
// Stream.generate(() -> 0)
//     .filter(n -> n == 1)
//     .findFirst();
```

Nếu cần chặn số phần tử nguồn được xét, đặt `limit(n)` ở vị trí phù hợp trước `filter`:

```java
import java.util.stream.IntStream;

int result = IntStream.iterate(0, n -> n + 2)
    .limit(100)
    .filter(n -> n > 500)
    .findFirst()
    .orElse(-1);

System.out.println(result); // -1, vì 100 số đầu là 0, 2, ..., 198
```

Lưu ý: `filter(...).limit(100)` không tương đương với `limit(100).filter(...)`. Nếu nguồn vô hạn không bao giờ thỏa `filter`, phiên bản đầu có thể **không kết thúc** vì không thể tạo đủ 100 phần tử sau lọc. Với nguồn vô hạn, cũng tránh đặt `sorted` trước `findFirst` nếu không có cách giới hạn đầu vào cần sắp xếp.

## 6. `findFirst` và `findAny` khi xử lý song song

Khác biệt nổi bật nhất xuất hiện với `parallelStream()` hoặc `parallel()`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> numbers = Arrays.asList(10, 20, 30, 40, 50, 60);

Optional<Integer> first = numbers.parallelStream()
    .filter(n -> n >= 20)
    .findFirst();

Optional<Integer> any = numbers.parallelStream()
    .filter(n -> n >= 20)
    .findAny();

System.out.println(first.orElse(-1)); // Luôn 20
System.out.println(any.orElse(-1));   // Có thể là 20, 30, 40, 50 hoặc 60
```

Với nguồn có encounter order, `findFirst` phải trả phần tử phù hợp xuất hiện sớm nhất theo thứ tự đó, kể cả khi một luồng xử lý phần tử phía sau xong trước. Điều này có thể yêu cầu các nhánh phối hợp thêm. `findAny` cho phép chọn một phần tử phù hợp từ bất kỳ nhánh nào và vì thế thường mở ra cơ hội tối ưu.

**Không suy luận từ ví dụ rằng `findAny` sẽ luôn trả kết quả khác nhau hoặc luôn chạy nhanh hơn.** Trong một số môi trường và kích thước dữ liệu, nó có thể trả một phần tử giống nhau qua nhiều lần hoặc chậm hơn do chi phí thiết lập xử lý song song. Chỉ đánh giá lợi ích hiệu năng bằng phép đo trên workload thực tế.

| Nhu cầu | Lựa chọn phù hợp | Vì sao |
| --- | --- | --- |
| Lấy bản ghi hợp lệ sớm nhất theo thứ tự danh sách | `findFirst` | Thứ tự là một phần của yêu cầu. |
| Lấy bất kỳ bản ghi lỗi nào để điều tra | `findAny` | Chỉ cần một kết quả, không cần thứ tự. |
| Lấy sự kiện có timestamp sớm nhất | `min(comparator)` nếu nguồn chưa sắp theo thời gian; `findFirst` nếu đã sắp đúng | “Đầu tiên” phải dựa trên thứ tự nghiệp vụ. |
| Chỉ kiểm tra có bản ghi lỗi hay không | `anyMatch(predicate)` | Trả trực tiếp `boolean` thay vì tạo `Optional`. |
| Cần tất cả bản ghi phù hợp | `filter(...).collect(...)` | Không nên dùng `find*` khi cần toàn bộ kết quả. |

### `unordered()` có ý nghĩa gì?

Trên nguồn có thứ tự, `unordered()` cho phép loại bỏ nghĩa vụ bảo toàn encounter order ở các bước sau. Trong pipeline song song với `findAny`, ràng buộc thứ tự vốn đã không cần để chọn kết quả; vì vậy thêm `unordered()` không nhất thiết mang lại cải thiện rõ rệt. Ngược lại, `unordered().findFirst()` làm mất ý nghĩa “đầu tiên” của nguồn ban đầu.

Không dùng `unordered()` chỉ như một mẹo tăng tốc nếu yêu cầu nghiệp vụ cần kết quả ổn định theo thứ tự.

## 7. Ví dụ nghiệp vụ: chọn một sự kiện cần xử lý

Giả sử danh sách thông báo được đưa vào theo thứ tự tiếp nhận. Khi cần **thông báo lỗi sớm nhất**, dùng `findFirst`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public class EventSelection {
    public static void main(String[] args) {
        List<String> events = Arrays.asList(
            "INFO: started",
            "WARN: retry",
            "ERROR: timeout",
            "ERROR: connection reset"
        );

        Optional<String> firstError = events.stream()
            .filter(message -> message.startsWith("ERROR:"))
            .findFirst();

        firstError.ifPresent(System.out::println);
        // ERROR: timeout
    }
}
```

Nếu yêu cầu chỉ là “tìm bất kỳ lỗi nào để hiển thị một mẫu”, có thể đổi terminal operation sang `findAny`. Khi đó **không được dựa vào** việc luôn nhận thông báo `ERROR: timeout`, đặc biệt nếu sau này chuyển sang stream song song.

Với dữ liệu đầu vào từ `HashSet`, việc gọi `findFirst` không tạo ra một thứ tự thời gian đáng tin cậy. Muốn tìm sớm nhất theo timestamp, phải mang thông tin thời gian trong phần tử và dùng `min(comparator)`, hoặc sắp xếp theo thời gian trước khi gọi `findFirst`.

### Tìm trong tệp lớn và quản lý tài nguyên

Stream lấy từ `Files.lines` có thể giữ tài nguyên I/O. Vì vậy, dù `findFirst` dừng sớm sau khi thấy dòng phù hợp, vẫn cần **đóng stream**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public class FindInLog {
    public static Optional<String> firstError(Path file) throws IOException {
        try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
            return lines.filter(line -> line.startsWith("ERROR:"))
                .findFirst();
        }
    }
}
```

Terminal operation **không tự động đóng** mọi stream. `try-with-resources` giúp đóng tài nguyên khi có kết quả, khi không tìm thấy và khi phát sinh ngoại lệ.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| “`findFirst` luôn trả phần tử nhỏ nhất.” | Encounter order không đồng nghĩa thứ tự tăng dần. | Dùng `min` hoặc sắp xếp theo tiêu chí mong muốn. |
| “`findAny` luôn là phần tử đầu khi chạy tuần tự.” | API không bảo đảm cách chọn ấy. | Dùng `findFirst` nếu thứ tự quan trọng. |
| “`findFirst` trên `HashSet` tạo kết quả ổn định.” | Nguồn không có encounter order được bảo đảm. | Dùng nguồn có thứ tự hoặc sắp theo comparator rõ ràng. |
| Gọi `optional.get()` ngay sau `find*`. | Có thể ném `NoSuchElementException`. | Dùng `orElse`, `ifPresent`, `orElseThrow`. |
| Cho rằng `findAny` lúc nào cũng nhanh hơn. | Chi phí phụ thuộc nguồn, dữ liệu, điều kiện lọc, mức song song và thứ tự. | Đo đạc trên workload cụ thể. |
| Dùng `peek` để xử lý mọi phần tử trước `find*`. | Pipeline ngắn mạch có thể bỏ qua các phần tử còn lại. | Tách xử lý có hiệu ứng phụ bắt buộc khỏi bước tìm kiếm. |
| Gọi `count()` hoặc `findAny()` tiếp trên cùng stream. | Stream đã bị tiêu thụ sau terminal operation. | Tạo stream mới từ nguồn nếu cần phép toán khác. |
| Dùng `find*` với phần tử `null`. | Phần tử được chọn là `null` gây `NullPointerException`. | Lọc `Objects::nonNull` khi dữ liệu cho phép `null`. |
| Giả định `findFirst` luôn dừng nhanh trên stream vô hạn. | Có thể không bao giờ gặp phần tử phù hợp. | Đặt giới hạn và thiết kế điều kiện kết thúc rõ ràng. |

Một `Stream` chỉ được vận hành bằng một terminal operation. Ví dụ:

```java
import java.util.stream.Stream;

Stream<Integer> stream = Stream.of(1, 2, 3);
stream.findFirst();

// Không hợp lệ: stream đã được vận hành.
// stream.findAny(); // IllegalStateException

// Nếu cần tìm lại, tạo pipeline mới từ nguồn:
System.out.println(Stream.of(1, 2, 3).findAny().orElse(-1));
```

## 9. Quy trình chọn và tự kiểm tra

Khi thiết kế tìm kiếm bằng Java Stream API, có thể rà soát:

1. **Muốn biết có tồn tại hay muốn lấy phần tử?** Chỉ kiểm tra tồn tại thì chọn `anyMatch`; cần phần tử thì cân nhắc `findFirst` hoặc `findAny`.
2. **“Đầu tiên” được định nghĩa theo thứ tự nào?** Xác định nguồn có encounter order hay chưa; nếu cần giá trị nhỏ nhất hoặc mới nhất, thường dùng comparator/`min`/`max`.
3. **Có thực sự cần một phần tử ổn định?** Nếu không quan tâm phần tử nào, `findAny` phù hợp; nếu kết quả cần ổn định theo thứ tự, dùng `findFirst`.
4. **Pipeline có thể dừng không?** Xét độ dài nguồn, vị trí phần tử phù hợp, `sorted`, `filter`, `limit` và các bước trung gian có trạng thái.
5. **Kết quả rỗng thì xử lý ra sao?** Dùng API `Optional` theo ý nghĩa nghiệp vụ; không gọi `get()` nếu chưa bảo đảm tồn tại.
6. **Có chạy song song không?** Giữ các lambda không phụ thuộc trạng thái thay đổi bên ngoài, tránh giả định số lần gọi hoặc thứ tự thực thi, và đo hiệu năng khi cần.
7. **Nguồn có giữ tài nguyên không?** Với file và một số nguồn I/O, dùng `try-with-resources`.

### Bài tập thực hành

**Bài 1.** Cho danh sách `[7, 3, 12, 18, 4]`, viết pipeline tìm **số chẵn đầu tiên**. Đáp án đúng theo encounter order là `12`, không phải `4`. Sau đó dùng `min` để tìm **số chẵn nhỏ nhất** và so sánh hai kết quả.

**Bài 2.** Tạo một `List<String>` chứa nhiều mã lỗi. Viết `findFirst` để lấy lỗi đầu tiên theo thứ tự danh sách và `parallelStream().findAny()` để lấy một lỗi bất kỳ. Kiểm tra rằng phần tử trả về từ `findAny` luôn thỏa điều kiện, nhưng **không viết test yêu cầu nó luôn là cùng một mã**.

**Bài 3.** Dùng `IntStream.iterate(0, n -> n + 2)` tạo dãy vô hạn số chẵn, đặt `limit(100)`, lọc số lớn hơn `500` rồi gọi `findFirst`. Giải thích vì sao kết quả rỗng. Thử đổi `limit(100)` thành `limit(300)` và dự đoán kết quả.

**Bài 4.** Với danh sách có thể chứa `null`, viết pipeline bỏ `null`, lọc chuỗi không rỗng và lấy chuỗi đầu tiên hợp lệ. Xử lý kết quả bằng `orElse` thay vì `Optional.get()`.

**Ghi nhớ:** `findFirst` là lựa chọn khi **thứ tự có ý nghĩa**; `findAny` phù hợp khi **bất kỳ phần tử thỏa điều kiện nào cũng chấp nhận được**. Cả hai đều có khả năng ngắn mạch và trả `Optional`, nhưng khả năng dừng sớm, kết quả ổn định và hiệu năng thực tế còn phụ thuộc nguồn, encounter order, pipeline và chế độ xử lý.
