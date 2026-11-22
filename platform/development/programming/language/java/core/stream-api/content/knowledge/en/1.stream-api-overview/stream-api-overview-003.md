# Mô hình nguồn dữ liệu, phép toán trung gian và phép toán kết thúc

> **Chương:** Tổng quan Stream API  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Hiểu cách một pipeline Stream được tạo, biến đổi, thực thi và kết thúc.

Java Stream API cho phép diễn đạt việc xử lý một chuỗi phần tử theo phong cách khai báo: mô tả **cần lọc gì, biến đổi ra sao và tổng hợp kết quả thế nào**, thay vì tự điều khiển từng vòng lặp. Trong module **JAVA_STREAM_API**, mô hình pipeline này là nền tảng để học `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers. Trước khi dùng các kỹ thuật nâng cao, cần phân biệt rõ ba thành phần: **nguồn dữ liệu**, **phép toán trung gian** và **phép toán kết thúc**.

## 1. Bức tranh tổng thể: một pipeline có ba phần

Một pipeline Stream thường có cấu trúc:

```text
Nguồn dữ liệu
    │
    ▼
Stream<T> ──► trung gian 1 ──► trung gian 2 ──► ... ──► kết thúc
                  filter          map                 toList
                                                        │
                                                        ▼
                                                Kết quả / tác động
```

- **Nguồn dữ liệu (source):** cung cấp phần tử cho pipeline, chẳng hạn `List`, mảng, dãy số, dòng trong tệp hoặc nguồn tạo phần tử theo yêu cầu.
- **Phép toán trung gian (intermediate operation):** nhận một Stream và trả về một Stream khác, thường dùng để lọc, biến đổi, sắp xếp hoặc giới hạn phần tử. Có thể có **0, 1 hoặc nhiều** phép toán trung gian.
- **Phép toán kết thúc (terminal operation):** kích hoạt việc đánh giá pipeline khi cần, rồi tạo kết quả hoặc thực hiện tác động như đếm, tìm kiếm, tổng hợp hay duyệt phần tử.

Ví dụ:

```java
List<Integer> prices = List.of(80, 250, 120, 400, 250);

List<Integer> result = prices.stream()     // Nguồn: List<Integer>
    .filter(price -> price >= 200)          // Trung gian: giữ giá >= 200
    .map(price -> price / 10)                // Trung gian: đổi đơn vị
    .distinct()                              // Trung gian: bỏ trùng
    .toList();                               // Kết thúc: tạo List<Integer>

// result = [25, 40]
```

`prices` vẫn là danh sách ban đầu. Pipeline tạo ra một kết quả khác; bản thân Stream **không phải** là nơi lưu trữ dữ liệu. Các phần tử được lấy từ nguồn và đi qua những phép toán đã khai báo khi pipeline được thực thi.

Một mô hình quan trọng cần ghi nhớ:

1. Tạo Stream từ nguồn.
2. Khai báo các bước trung gian.
3. Gọi một phép toán kết thúc để nhận kết quả.
4. Không dùng lại chính đối tượng Stream vừa kết thúc.

Đây là **mô hình sử dụng phổ biến**, không có nghĩa mọi phép toán kết thúc đều phải đọc hết toàn bộ nguồn. Một số phép toán có thể dừng sớm hoặc tối ưu mà không duyệt từng phần tử.

## 2. Nguồn dữ liệu: phần tử đến từ đâu?

Nguồn quyết định loại phần tử, khả năng hữu hạn hay vô hạn, thứ tự gặp phần tử (nếu có) và đôi khi cả nhu cầu đóng tài nguyên.

| Nguồn | Cách tạo Stream | Ý nghĩa |
| --- | --- | --- |
| `Collection` | `list.stream()` | Đọc các phần tử của collection theo cơ chế duyệt của nó. |
| Mảng | `Arrays.stream(array)` | Tạo Stream từ mảng. Có các overload cho mảng nguyên thủy. |
| Giá trị trực tiếp | `Stream.of("A", "B")` | Tạo Stream từ các giá trị đã cho. |
| Dãy số nguyên | `IntStream.range(1, 5)` | Sinh `1, 2, 3, 4`; cận cuối không được tính. |
| Dòng văn bản trong tệp | `Files.lines(path)` | Đọc các dòng khi cần, gắn với tài nguyên I/O cần đóng. |
| Sinh vô hạn | `Stream.generate(supplier)` | Gọi nhà cung cấp phần tử khi pipeline yêu cầu. |
| Dãy lặp | `Stream.iterate(seed, next)` | Sinh dãy tiếp diễn từ giá trị khởi đầu. |

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

class SourceExamples {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");
        long fromList = names.stream().count();               // 3

        int[] scores = {7, 9, 6};
        int fromArray = Arrays.stream(scores).sum();          // 22

        List<Integer> fromRange = IntStream.range(1, 5)
            .boxed()
            .toList();                                        // [1, 2, 3, 4]

        List<String> fromValues = Stream.of("x", "y").toList(); // [x, y]

        List<Integer> firstThree = Stream.iterate(1, n -> n * 2)
            .limit(3)
            .toList();                                        // [1, 2, 4]

        System.out.println(fromList + fromArray);
        System.out.println(fromRange);
        System.out.println(fromValues);
        System.out.println(firstThree);
    }
}
```

Các ví dụ dùng `List.of` (Java 9+) và `Stream.toList` (Java 16+). Với Java 8, có thể thay phần kết thúc `.toList()` bằng `.collect(Collectors.toList())`; hai cách này **không có cùng cam kết về tính sửa đổi được** của danh sách kết quả.

### 2.1. Stream đối tượng và Stream kiểu nguyên thủy

- `Stream<T>` biểu diễn phần tử tham chiếu, ví dụ `Stream<String>` hoặc `Stream<Order>`.
- `IntStream`, `LongStream`, `DoubleStream` hỗ trợ giá trị nguyên thủy, tránh boxing không cần thiết và cung cấp phép kết thúc như `sum()`, `average()`, `summaryStatistics()`.
- `mapToInt`, `mapToLong`, `mapToDouble` chuyển từ `Stream<T>` sang Stream nguyên thủy; `boxed()` chuyển ngược sang Stream của wrapper.

Ví dụ:

```java
double average = List.of(10, 20, 30).stream()
    .mapToInt(Integer::intValue)
    .average()
    .orElse(0.0); // 20.0
```

`average()` trả về `OptionalDouble` vì nguồn có thể không chứa phần tử. `orElse(0.0)` là chính sách mặc định do người viết chương trình lựa chọn, không phải giá trị trung bình mặc định của API.

### 2.2. Nguồn không nhất thiết có sẵn toàn bộ dữ liệu

Một Stream từ `List` có một collection đã tồn tại. Ngược lại, `Files.lines(...)` có thể đọc theo nhu cầu và `Stream.iterate(...)` có thể tạo dãy không có điểm kết thúc tự nhiên. Vì vậy, **tạo Stream không đồng nghĩa sao chép toàn bộ nguồn vào bộ nhớ**.

Với nguồn có khả năng vô hạn, phải chọn phép kết thúc có thể dừng sớm hoặc đặt giới hạn phù hợp:

```java
List<Integer> tenSoChan = Stream.iterate(0, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(10)
    .toList(); // [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
```

Nếu bỏ `limit(10)` và dùng `toList()`, pipeline trên không có điều kiện kết thúc. Ngoài ra, đặt một phép toán cần thấy toàn bộ dữ liệu, như `sorted()`, trước `limit()` trên nguồn vô hạn có thể khiến pipeline không bao giờ tạo được kết quả.

### 2.3. Nguồn I/O cần quản lý tài nguyên

`Files.lines` trả về một `Stream<String>` gắn với tài nguyên tệp. Phải đóng Stream khi hoàn tất, kể cả khi xảy ra lỗi:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class FileLinesExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (Stream<String> lines = Files.lines(path)) {
            long nonEmptyLines = lines
                .filter(line -> !line.isBlank())
                .count();

            System.out.println(nonEmptyLines);
        }
    }
}
```

Ví dụ giả định `data.txt` có tồn tại. `try-with-resources` đảm bảo gọi `close()`. **Phép toán kết thúc không tự động đóng Stream**; với nguồn như collection, thường không có tài nguyên bên ngoài cần giải phóng.

## 3. Phép toán trung gian: mô tả cách xử lý

Phép toán trung gian trả về Stream để có thể nối nhiều bước bằng dấu chấm. Các phép toán này **thường lazy (đánh giá trễ)**: việc gọi `filter`, `map` hoặc `sorted` chưa tự quét hết nguồn. Chúng thiết lập chuỗi xử lý, còn việc lấy phần tử xảy ra khi một phép kết thúc cần dữ liệu.

| Phép toán | Tác dụng chính | Đặc điểm thường gặp |
| --- | --- | --- |
| `filter(predicate)` | Giữ phần tử thỏa điều kiện. | Không làm thay đổi kiểu phần tử. |
| `map(function)` | Biến đổi mỗi phần tử thành giá trị khác. | Có thể đổi kiểu, ví dụ `Stream<Order>` thành `Stream<Long>`. |
| `flatMap(function)` | Ánh xạ một phần tử thành một Stream rồi làm phẳng các Stream con. | Hữu ích với danh sách lồng nhau. |
| `distinct()` | Loại phần tử trùng theo `equals`. | Phải theo dõi phần tử đã gặp; có trạng thái. |
| `sorted()` / `sorted(comparator)` | Sắp xếp phần tử. | Thường phải thu thập dữ liệu trước khi phát kết quả. |
| `limit(n)` | Giữ tối đa `n` phần tử. | Có thể giúp pipeline dừng sớm. |
| `skip(n)` | Bỏ qua tối đa `n` phần tử đầu. | Việc đếm/bỏ qua liên quan đến thứ tự và trạng thái. |
| `peek(action)` | Gắn hành động quan sát khi phần tử đi qua. | Chủ yếu phục vụ chẩn đoán; không phù hợp làm nơi chứa logic bắt buộc. |

Ví dụ `filter` rồi `map`:

```java
List<String> users = List.of("  An  ", " Bình ", "  Chi ");

List<String> normalized = users.stream()
    .map(String::trim)
    .filter(name -> name.length() >= 3)
    .toList();

// normalized = [Bình, Chi]
```

Thứ tự các bước có thể làm thay đổi kết quả. Nếu lọc theo độ dài **trước** khi `trim`, khoảng trắng thừa có thể khiến một tên ngắn vượt qua điều kiện. Hãy đặt các bước theo đúng quy tắc nghiệp vụ.

### 3.1. `map` khác `flatMap` thế nào?

Giả sử mỗi nhóm có một danh sách kỹ năng:

```java
List<List<String>> groups = List.of(
    List.of("Java", "SQL"),
    List.of("Docker", "Git")
);

List<Integer> sizes = groups.stream()
    .map(List::size)
    .toList(); // [2, 2]

List<String> allSkills = groups.stream()
    .flatMap(List::stream)
    .toList(); // [Java, SQL, Docker, Git]
```

`map(List::size)` tạo **một kết quả cho mỗi danh sách đầu vào**. `flatMap(List::stream)` tạo một Stream các kỹ năng cho mỗi nhóm rồi nối chúng thành luồng phần tử phẳng. Số phần tử đầu ra của `flatMap` có thể là 0, 1 hoặc nhiều phần tử cho mỗi đầu vào.

### 3.2. Phép toán không trạng thái và có trạng thái

`filter` và `map` thường là phép toán **không trạng thái**: cách xử lý một phần tử không cần nhớ các phần tử trước. Ngược lại:

- `distinct()` cần nhận biết các giá trị đã gặp để loại trùng.
- `sorted()` cần đủ dữ liệu để xác định thứ tự sắp xếp; với nguồn vô hạn, đây thường là trở ngại không thể hoàn tất.
- `limit()` và `skip()` phụ thuộc số lượng phần tử đã đi qua, nên là những phép toán trung gian có trạng thái.

Sự khác biệt ảnh hưởng tới bộ nhớ, khả năng dừng sớm và chi phí khi chạy song song. Đặc biệt, phép toán có trạng thái và yêu cầu giữ thứ tự có thể làm giảm hiệu quả song song.

## 4. Phép toán kết thúc: kích hoạt và nhận kết quả

Phép toán kết thúc làm pipeline được đánh giá **trong phạm vi cần thiết để cho ra kết quả**. Kết quả có thể là collection, một giá trị, một `Optional` hoặc một tác động mà không trả về giá trị.

| Phép toán | Giá trị trả về | Khi dùng |
| --- | --- | --- |
| `toList()` | `List<T>` | Muốn lấy danh sách kết quả. |
| `collect(collector)` | Phụ thuộc collector | Gom nhóm, nối chuỗi, tạo map, tính thống kê. |
| `count()` | `long` | Đếm số phần tử. |
| `reduce(...)` | Giá trị hoặc `Optional` | Gộp các phần tử theo phép kết hợp. |
| `sum()` trên Stream nguyên thủy | Số | Tính tổng các số. |
| `min(...)` / `max(...)` | `Optional<T>` | Tìm phần tử nhỏ nhất/lớn nhất. |
| `findFirst()` / `findAny()` | `Optional<T>` | Tìm một phần tử; có thể dừng sớm. |
| `anyMatch` / `allMatch` / `noneMatch` | `boolean` | Kiểm tra điều kiện trên các phần tử. |
| `forEach(action)` | `void` | Thực hiện hành động trên phần tử. |

Ví dụ cùng một nguồn nhưng **mỗi phép kết thúc cần một Stream mới**:

```java
List<Integer> amounts = List.of(50, 120, 250, 80);

long expensiveCount = amounts.stream()
    .filter(amount -> amount >= 100)
    .count(); // 2

boolean hasVeryExpensive = amounts.stream()
    .anyMatch(amount -> amount > 200); // true

int total = amounts.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 500
```

### 4.1. `reduce` và `collect` xử lý hai kiểu tổng hợp khác nhau

`reduce` phù hợp để kết hợp phần tử thành một giá trị theo phép toán có tính kết hợp, chẳng hạn tổng hoặc tích:

```java
int sum = List.of(5, 10, 15).stream()
    .reduce(0, Integer::sum); // 30
```

Ở đây `0` là giá trị đồng nhất của phép cộng; `Integer::sum` kết hợp hai giá trị. Khi dùng song song, toán tử giảm phải thỏa tính kết hợp và tuân thủ hợp đồng của `reduce`. Không nên dùng một bộ tích lũy mutable chia sẻ giữa các phần tử làm toán tử `reduce`.

`collect` phù hợp khi xây dựng cấu trúc kết quả có thể thay đổi trong quá trình tích lũy, ví dụ nhóm đơn hàng theo loại:

```java
Map<String, List<String>> byFirstLetter = List.of("An", "Anh", "Bình")
    .stream()
    .collect(Collectors.groupingBy(name -> name.substring(0, 1)));

// byFirstLetter chứa nhóm "A" -> [An, Anh] và "B" -> [Bình]
```

`Collectors.groupingBy` là collector xây dựng map các nhóm. Những chủ đề như downstream collector và collector tùy chỉnh tiếp tục dựa trên đúng cơ chế kết thúc này.

**Chú ý về danh sách:** `Stream.toList()` (Java 16+) trả về danh sách không thể thêm, xóa hoặc thay phần tử. `Collectors.toList()` không cam kết cụ thể về kiểu triển khai hoặc tính sửa đổi được. Nếu cần `ArrayList` có thể thay đổi, hãy chỉ định rõ: `collect(Collectors.toCollection(ArrayList::new))`.

### 4.2. Phép kết thúc dừng sớm

Không phải lúc nào cũng cần đọc hết nguồn:

```java
boolean exists = Stream.of(3, 7, 12, 18)
    .anyMatch(n -> n % 2 == 0); // true, có thể dừng khi gặp 12

Optional<Integer> first = Stream.of(3, 7, 12, 18)
    .filter(n -> n % 2 == 0)
    .findFirst(); // Optional[12]
```

`findFirst` tôn trọng thứ tự gặp phần tử nếu nguồn có thứ tự. `findAny` cho phép chọn bất kỳ phần tử phù hợp nào, đặc biệt hữu ích khi chạy song song. `allMatch` với nguồn rỗng trả về `true`; `anyMatch` với nguồn rỗng trả về `false` theo định nghĩa của các phép kiểm tra này.

## 5. Lazy evaluation và cách dữ liệu thực sự chảy qua pipeline

Xét đoạn chương trình sau:

```java
import java.util.Optional;
import java.util.stream.Stream;

class LazyExample {
    public static void main(String[] args) {
        Stream<Integer> pipeline = Stream.of(1, 2, 3, 4, 5)
            .filter(n -> {
                System.out.println("filter " + n);
                return n % 2 == 0;
            })
            .map(n -> {
                System.out.println("map " + n);
                return n * 10;
            });

        System.out.println("Đã khai báo pipeline");
        Optional<Integer> first = pipeline.findFirst();
        System.out.println(first);
    }
}
```

Khi chạy tuần tự, thứ tự in là:

```text
Đã khai báo pipeline
filter 1
filter 2
map 2
Optional[20]
```

Từ đó thấy ba điều:

1. Lệnh tạo `pipeline` không gọi `filter` hay `map` ngay.
2. Khi `findFirst()` cần dữ liệu, phần tử đi qua các bước thích hợp; ví dụ phần tử `2` được lọc rồi ánh xạ trước khi xét tới phần tử `3`.
3. `findFirst()` dừng ngay khi tìm được phần tử đầu tiên hợp lệ. Phần tử `3`, `4`, `5` không cần được xử lý.

Đây thường được gọi là **xử lý theo phần tử kết hợp các bước (pipeline fusion)**. Tuy nhiên, không được suy ra rằng mọi pipeline đều hoạt động với từng phần tử độc lập: `sorted` có thể cần giữ nhiều phần tử trước khi trả phần tử đầu tiên.

### 5.1. Một phép kết thúc cũng có thể bỏ qua việc duyệt nhờ tối ưu

Đoạn sau không được dùng để trông chờ `peek` luôn in đủ ba dòng:

```java
long count = List.of("A", "B", "C").stream()
    .peek(System.out::println)
    .count(); // 3
```

Với một nguồn có kích thước đã biết và các bước không làm thay đổi số phần tử, triển khai Stream có thể tính `count()` mà **không duyệt các phần tử**, vì thế hành động `peek` có thể không chạy. Tương tự, các tối ưu và phép dừng sớm có thể khiến hành vi phụ trong lambda không diễn ra như trực giác.

**Nguyên tắc:** lambda dùng trong `filter`, `map`, `peek` nên không mang tác động phụ thiết yếu. Dùng dữ liệu đầu ra hoặc một phép kết thúc phù hợp để biểu diễn yêu cầu nghiệp vụ.

## 6. Ví dụ hoàn chỉnh: xử lý đơn hàng

Bài toán: có danh sách đơn hàng với khách hàng, nhóm hàng và số tiền. Chỉ giữ đơn có số tiền dương, sau đó tính **doanh thu theo nhóm hàng**. Ví dụ dùng Java 17+ (kiểu `record` và `List.of`); lưu trong tệp `OrderPipelineDemo.java` để chạy.

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderPipelineDemo {
    record Order(String customer, String category, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("An",   "Sách",      120_000),
            new Order("Bình", "Sách",       80_000),
            new Order("An",   "Phụ kiện",  200_000),
            new Order("Chi",  "Sách",      -10_000),
            new Order("Dung", "Phụ kiện",  150_000)
        );

        Map<String, Long> revenueByCategory = orders.stream()
            .filter(order -> order.amount() > 0)
            .collect(Collectors.groupingBy(
                Order::category,
                TreeMap::new,
                Collectors.summingLong(Order::amount)
            ));

        System.out.println(revenueByCategory);
        // {Phụ kiện=350000, Sách=200000}
    }
}
```

Phân tích từng phần:

| Thành phần | Mã | Vai trò |
| --- | --- | --- |
| Nguồn | `orders.stream()` | Cung cấp các đối tượng `Order`. |
| Trung gian | `filter(order -> order.amount() > 0)` | Bỏ đơn có giá trị không hợp lệ theo quy tắc ví dụ. |
| Kết thúc | `collect(...)` | Duyệt dữ liệu cần thiết và tích lũy thành `Map`. |
| Bộ gom | `groupingBy(Order::category, ...)` | Tách nhóm theo tên loại hàng. |
| Bộ gom con | `summingLong(Order::amount)` | Cộng tiền của các đơn trong mỗi nhóm. |
| Nơi lưu kết quả | `TreeMap::new` | Tạo map có thứ tự khóa tự nhiên để đầu ra dễ đọc. |

Nếu cần lấy danh sách các đơn có giá trị cao, ta tạo **một pipeline độc lập** trên cùng collection:

```java
List<String> highValueCustomers = orders.stream()
    .filter(order -> order.amount() >= 150_000)
    .map(Order::customer)
    .distinct()
    .toList(); // [An, Dung]
```

Cùng một nguồn `orders` được phép mở nhiều Stream mới. Việc không được làm là sử dụng lại **cùng một đối tượng `Stream` sau khi đã thực hiện phép kết thúc**.

## 7. Vòng đời và quy tắc một lần sử dụng

Một đối tượng Stream được thiết kế để tiêu thụ **một lần**. Ví dụ sau sai:

```java
Stream<String> names = Stream.of("An", "Bình", "Chi");
long count = names.count();
List<String> result = names.toList(); // IllegalStateException
```

Sau `count()`, `names` đã được tiêu thụ. Một số cách tái sử dụng pipeline cũng có thể bị phát hiện sớm hơn; vì vậy không nên giữ các nhánh rồi thử dùng đi dùng lại một Stream trung gian.

Cách đúng là tạo Stream mới từ nguồn có thể tái duyệt:

```java
List<String> names = List.of("An", "Bình", "Chi");

long count = names.stream().count();
List<String> result = names.stream()
    .filter(name -> name.length() > 2)
    .toList();
```

Nếu muốn mô tả một pipeline dùng nhiều lần, có thể viết hàm tạo Stream mới:

```java
Supplier<Stream<String>> nonBlankNames = () -> names.stream()
    .filter(name -> !name.isBlank());

long n = nonBlankNames.get().count();
List<String> clean = nonBlankNames.get().toList();
```

Đoạn cuối cần `import java.util.function.Supplier;` và `import java.util.stream.Stream;`. Mỗi lần gọi `get()` tạo một đối tượng Stream mới trên collection. Cách này **không tự làm cho một nguồn chỉ đọc được một lần (ví dụ một luồng I/O đang mở) trở nên có thể tái đọc**.

## 8. Giới hạn và lỗi thiết kế thường gặp

### 8.1. Không sửa nguồn đang được duyệt

`Stream` thường yêu cầu **non-interference**: không can thiệp vào nguồn dữ liệu trong lúc pipeline đang chạy, trừ những nguồn được thiết kế cho truy cập đồng thời. Ví dụ sau có nguy cơ gây `ConcurrentModificationException` hoặc kết quả khó dự đoán:

```java
List<String> names = new ArrayList<>(List.of("An", "Bình"));

names.stream().forEach(name -> {
    if (name.equals("An")) {
        names.add("Chi"); // Sai: sửa danh sách nguồn trong lúc duyệt
    }
});
```

Thay vì sửa trực tiếp collection đang duyệt, hãy tạo collection kết quả hoặc sử dụng thao tác phù hợp của collection, chẳng hạn `removeIf` khi mục tiêu là xóa phần tử theo điều kiện mà không cần Stream.

### 8.2. Tránh trạng thái mutable chia sẻ giữa các lambda

Không nên dùng một danh sách ngoài pipeline làm biến tích lũy:

```java
List<String> output = new ArrayList<>();
names.parallelStream()
    .filter(name -> !name.isBlank())
    .forEach(output::add); // Không an toàn với ArrayList trong parallel stream
```

Hãy sử dụng phép kết thúc được thiết kế để tích lũy:

```java
List<String> output = names.parallelStream()
    .filter(name -> !name.isBlank())
    .toList();
```

Các hành động phụ như ghi log, thay đổi biến đếm hoặc cập nhật đối tượng ngoài pipeline có thể chịu ảnh hưởng của tối ưu, thứ tự và nhiều luồng. `forEach` có mục đích thực hiện hành động nhưng **không đảm bảo thứ tự gặp phần tử khi song song**; nếu cần thứ tự khi duyệt, cân nhắc `forEachOrdered` cùng chi phí đồng bộ liên quan.

### 8.3. Chú ý thứ tự gặp phần tử

`List` thường cung cấp Stream có thứ tự; `HashSet` không cam kết thứ tự duyệt ổn định theo nghĩa hợp đồng API. `findFirst()` có ý nghĩa "đầu tiên" theo **encounter order** nếu Stream có thứ tự. `findAny()` không cam kết chọn phần tử đầu tiên.

`sorted()` tạo một thứ tự sắp xếp cho kết quả, nhưng đổi lại có chi phí; nếu bài toán chỉ cần tồn tại một phần tử phù hợp, `anyMatch` thường diễn đạt mục tiêu rõ hơn và có thể dừng sớm.

### 8.4. Không mặc định rằng parallel nhanh hơn

`parallelStream()` hoặc `stream().parallel()` có thể chia việc xử lý cho nhiều luồng, song việc chia/ghép, thứ tự, đồng bộ và kích thước dữ liệu đều ảnh hưởng hiệu năng. Dữ liệu ít, phép toán nhẹ, nhiều thao tác có trạng thái hoặc I/O chặn thường không hưởng lợi rõ rệt.

Ví dụ:

```java
long count = orders.parallelStream()
    .filter(order -> order.amount() > 0)
    .count();
```

Cấu trúc pipeline giống bản tuần tự, nhưng các lambda phải phù hợp với thực thi song song: **không dựa vào biến trạng thái dùng chung, không giả định thứ tự xử lý**. Việc chọn song song cần dựa trên đo đạc đúng tải thực tế.

### 8.5. Stream không phải lúc nào cũng tối ưu hơn vòng lặp

Stream giúp truyền đạt phép biến đổi dữ liệu và kết hợp nhiều bước xử lý. Tuy nhiên, khi thuật toán cần điều khiển luồng phức tạp, cập nhật nhiều trạng thái phụ thuộc nhau hoặc có yêu cầu hiệu năng rất cụ thể, vòng lặp truyền thống đôi khi dễ hiểu và dễ tối ưu hơn. Tránh tạo nhiều danh sách trung gian không cần thiết; một pipeline thường biểu đạt tốt hơn chuỗi chuyển đổi qua các collection tạm.

## 9. Chọn phép toán đúng theo mục tiêu

| Mục tiêu | Cách diễn đạt phù hợp |
| --- | --- |
| Giữ các đơn hàng hợp lệ | `filter(order -> order.amount() > 0)` |
| Lấy tên khách hàng từ đơn | `map(Order::customer)` |
| Trải phẳng các danh sách kỹ năng | `flatMap(List::stream)` |
| Lấy tối đa 10 mục | `limit(10)` |
| Kiểm tra có đơn trên một ngưỡng hay không | `anyMatch(order -> order.amount() > threshold)` |
| Đếm đơn thỏa điều kiện | `filter(...).count()` |
| Tính tổng tiền | `mapToLong(Order::amount).sum()` |
| Gom đơn theo loại | `collect(Collectors.groupingBy(Order::category))` |
| Thu danh sách kết quả | `toList()` hoặc `collect(...)` |
| Đọc các dòng tệp | `try (Stream<String> lines = Files.lines(path)) { ... }` |

Một pipeline dễ bảo trì thường đáp ứng các câu hỏi sau:

1. **Nguồn ở đâu?** Dữ liệu hữu hạn hay vô hạn, có thứ tự không, có tài nguyên cần đóng không?
2. **Mỗi bước trung gian làm gì?** Có thay đổi kiểu phần tử hoặc số lượng phần tử không? Có trạng thái hay chi phí sắp xếp không?
3. **Kết quả cuối cần gì?** Danh sách, map, một số, một phần tử hay chỉ kiểm tra điều kiện?
4. **Có thể dừng sớm không?** Nếu chỉ cần biết sự tồn tại, không nên thu toàn bộ danh sách.
5. **Có tác động phụ hoặc rủi ro đồng thời không?** Lambda nên độc lập và không sửa nguồn.
6. **Đã dùng Stream đúng một lần và đóng tài nguyên nếu cần chưa?**

## 10. Ghi nhớ cốt lõi

- **Nguồn** sinh hoặc cung cấp phần tử; Stream là cách biểu diễn quá trình duyệt và xử lý, không phải nơi cất giữ các phần tử.
- **Phép toán trung gian** tạo chuỗi xử lý và thường lazy; một số bước như `sorted` và `distinct` phải giữ trạng thái.
- **Phép toán kết thúc** đánh giá pipeline khi cần, có thể duyệt hết, dừng sớm hoặc áp dụng tối ưu không cần đọc mọi phần tử.
- **Một đối tượng Stream chỉ được tiêu thụ một lần**; muốn tính nhiều kết quả độc lập, hãy tạo Stream mới từ nguồn phù hợp.
- **Độ đúng của pipeline** phụ thuộc thứ tự xử lý, quy tắc không can thiệp nguồn, hạn chế tác động phụ và quản lý tài nguyên.
- **`filter` / `map` / `reduce` / `collect`** là bộ khung cốt lõi; các chủ đề grouping, collector tùy chỉnh, `Spliterator`, Stream song song và Stream Gatherers đều phát triển từ cách hiểu mô hình này.
