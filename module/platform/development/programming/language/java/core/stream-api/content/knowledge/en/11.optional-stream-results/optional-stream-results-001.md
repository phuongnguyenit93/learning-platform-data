# Xử lý Optional trả về từ findFirst, findAny, min, max và reduce

Trong Java Stream API, nhiều yêu cầu có dạng “tìm một phần tử”: tìm đơn hàng đầu tiên đủ điều kiện, tìm hóa đơn lớn nhất, lấy số điểm nhỏ nhất hoặc kết hợp nhiều giá trị thành một kết quả. Nhưng **không phải lúc nào cũng tìm được phần tử**. Một danh sách có thể rỗng, hoặc các bước `filter` có thể loại hết dữ liệu. Nếu API chỉ trả một đối tượng `T`, làm sao phân biệt “không có kết quả” với một giá trị hợp lệ?

Java giải quyết vấn đề đó bằng **`Optional<T>`**. Các phép toán kết thúc `findFirst()`, `findAny()`, `min(...)`, `max(...)` và một số overload của `reduce(...)` trả về `Optional` để thể hiện rõ **có một giá trị** hoặc **không có giá trị**. Đối với Stream kiểu nguyên thủy, Java cung cấp `OptionalInt`, `OptionalLong` và `OptionalDouble`.

Bài này thuộc chương **Optional trong kết quả Stream** của module **JAVA_STREAM_API**. Bạn sẽ học cách đọc các kết quả Optional, xử lý trường hợp rỗng an toàn, phân biệt các phương thức tìm kiếm và tổng hợp, hiểu ảnh hưởng của encounter order, lazy evaluation và parallel Stream, đồng thời chuẩn bị kiến thức cho `collect`, grouping, collector tùy chỉnh, `Spliterator` và Stream Gatherers.

## 1. Optional biểu diễn điều gì?

`Optional<T>` là một đối tượng biểu diễn một trong hai trạng thái:

- **Có giá trị (`present`):** chứa một đối tượng `T` khác `null`.
- **Không có giá trị (`empty`):** không chứa đối tượng nào.

Ví dụ:

~~~java
import java.util.Optional;

Optional<String> found = Optional.of("DH01");
Optional<String> absent = Optional.empty();

System.out.println(found.isPresent());  // true
System.out.println(absent.isPresent()); // false
~~~

Một giá trị có thể rỗng theo nghĩa nghiệp vụ mà vẫn là **present**: `Optional.of("")` có mặt và chứa chuỗi rỗng. `Optional.empty()` mới là trạng thái “không có giá trị”. Đừng đánh đồng chuỗi rỗng, số 0 hoặc danh sách rỗng với một Optional rỗng.

Với API Stream, Optional giúp người gọi **phải quyết định cách xử lý việc không tìm được kết quả**, chẳng hạn dùng giá trị mặc định, phát sinh lỗi nghiệp vụ, hoặc không thực hiện hành động nào.

~~~mermaid
flowchart LR
    A["Stream<Order>"] --> B["filter: đơn đã thanh toán"]
    B --> C["findFirst()"]
    C --> D{"Optional<Order>"}
    D -->|"present"| E["Xử lý Order"]
    D -->|"empty"| F["Dùng mặc định / báo không tìm thấy"]
~~~

Tất cả năm phép toán chính được học trong bài đều là **terminal operation**: khi được gọi, pipeline được tiêu thụ và không thể chạy lại trên cùng đối tượng Stream.

## 2. Bảng tra nhanh các phương thức trả về Optional

| Phép toán | Mục đích | Kiểu kết quả trên `Stream<T>` | Nếu Stream rỗng |
|---|---|---|---|
| `findFirst()` | Tìm phần tử đầu tiên theo encounter order nếu có | `Optional<T>` | `Optional.empty()` |
| `findAny()` | Tìm một phần tử bất kỳ | `Optional<T>` | `Optional.empty()` |
| `min(comparator)` | Tìm phần tử nhỏ nhất theo comparator | `Optional<T>` | `Optional.empty()` |
| `max(comparator)` | Tìm phần tử lớn nhất theo comparator | `Optional<T>` | `Optional.empty()` |
| `reduce(accumulator)` | Gộp các phần tử bằng phép kết hợp | `Optional<T>` | `Optional.empty()` |

Hai overload khác của `reduce` cần phân biệt:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
<U> U reduce(U identity,
             BiFunction<U, ? super T, U> accumulator,
             BinaryOperator<U> combiner)
~~~

Chúng **có giá trị khởi tạo `identity`**, nên trả về trực tiếp một giá trị, không phải Optional. Với Stream rỗng, kết quả là `identity`.

Trên các Stream nguyên thủy, các phương thức tương ứng trả về kiểu chuyên biệt: chẳng hạn `IntStream.findFirst()`, `IntStream.min()` và `IntStream.reduce(IntBinaryOperator)` trả `OptionalInt`. Bảng chi tiết có ở phần 7.

## 3. Ví dụ hoàn chỉnh: kết quả có thể không tồn tại

Giả sử hệ thống có các đơn hàng, mỗi đơn chứa mã, tên khách hàng, số tiền và trạng thái đã thanh toán. Ta cần tìm đơn đầu tiên đã thanh toán, một đơn bất kỳ đã thanh toán, đơn có giá trị nhỏ nhất/lớn nhất, và tổng số tiền của các đơn đã thanh toán.

Ví dụ chạy với **JDK 17 trở lên** vì dùng `record` và `List.of`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;

public class OptionalStreamResultsDemo {
    record Order(String id, String customer, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", "An",   120_000L, true),
            new Order("DH02", "Bình",  80_000L, false),
            new Order("DH03", "Chi",  250_000L, true),
            new Order("DH04", "Dũng", 250_000L, true)
        );

        // Mỗi phép toán kết thúc cần một Stream mới từ nguồn List.
        Optional<Order> firstPaid = orders.stream()
            .filter(Order::paid)
            .findFirst();

        Optional<Order> anyPaid = orders.stream()
            .filter(Order::paid)
            .findAny();

        Comparator<Order> byAmount =
            Comparator.comparingLong(Order::amountVnd);

        Optional<Order> cheapestPaid = orders.stream()
            .filter(Order::paid)
            .min(byAmount);

        Optional<Order> mostExpensivePaid = orders.stream()
            .filter(Order::paid)
            .max(byAmount);

        OptionalLong totalPaid = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .reduce(Long::sum);

        System.out.println(
            "Đầu tiên: " + firstPaid.map(Order::id).orElse("Không có")
        ); // Đầu tiên: DH01

        System.out.println("Có đơn bất kỳ: " + anyPaid.isPresent());
        // Có đơn bất kỳ: true; không giả định đó là mã đơn nào.

        System.out.println(
            "Nhỏ nhất: " + cheapestPaid.map(Order::amountVnd).orElse(0L)
        ); // Nhỏ nhất: 120000

        System.out.println(
            "Lớn nhất: " + mostExpensivePaid.map(Order::amountVnd).orElse(0L)
        ); // Lớn nhất: 250000

        System.out.println("Tổng: " + totalPaid.orElse(0L));
        // Tổng: 620000
    }
}
~~~

Có một số quyết định quan trọng ở ví dụ này:

1. `findFirst()` lấy đơn `DH01` vì nguồn là `List` có encounter order và `DH01` là đơn đã thanh toán đầu tiên.
2. `findAny()` chỉ bảo đảm trả về **một** đơn phù hợp nếu có; không nên viết kiểm thử ép nó luôn trả `DH01`.
3. `min` tìm số tiền thấp nhất; `max` tìm số tiền cao nhất theo `Comparator.comparingLong`.
4. Hai đơn `DH03` và `DH04` cùng có giá 250.000 đồng. `max` có thể chọn một đại diện trong các phần tử đồng hạng; nếu nghiệp vụ cần xác định chính xác ID, phải bổ sung quy tắc phụ vào comparator.
5. `mapToLong(...).reduce(Long::sum)` trả về `OptionalLong`. Với danh sách hiện tại, nó chứa 620.000; với không có đơn đã thanh toán, nó rỗng.

Trong ví dụ, `orElse(0L)` được dùng khi **quy ước hiển thị** là “không có dữ liệu thì hiện số 0”. Với báo cáo thực tế, “không có đơn”, “không xác định” và “giá trị thật bằng 0” có thể mang ý nghĩa khác nhau. Hãy chọn chính sách thiếu dữ liệu rõ ràng.

## 4. findFirst: ưu tiên phần tử đầu tiên theo encounter order

`Stream.findFirst()` có chữ ký:

~~~java
Optional<T> findFirst()
~~~

Đây là terminal operation **short-circuiting**: trong nhiều pipeline, nó có thể dừng ngay khi xác định được phần tử đầu tiên. “Đầu tiên” được xác định bởi **encounter order** nếu nguồn/pipeline có thứ tự.

~~~java
import java.util.List;
import java.util.Optional;

List<String> names = List.of("An", "Bình", "Chi");

Optional<String> firstLongName = names.stream()
    .filter(name -> name.length() >= 4)
    .findFirst();

System.out.println(firstLongName.orElse("Không tìm thấy")); // Bình
~~~

Vì `List` có thứ tự, `Bình` là phần tử đầu tiên đạt điều kiện độ dài ít nhất 4. Khi không có phần tử phù hợp:

~~~java
Optional<String> missing = names.stream()
    .filter(name -> name.startsWith("Z"))
    .findFirst();

System.out.println(missing.isPresent()); // false
~~~

### 4.1. “Đầu tiên” không luôn có nghĩa “nhỏ nhất”

Ví dụ, `List.of(9, 3, 5).stream().findFirst()` trả `9`, không phải `3`. Nếu muốn tìm giá trị nhỏ nhất, dùng `min` hoặc một phép toán tương đương theo tiêu chí nghiệp vụ. Nếu đã `sorted()` rồi `findFirst()` thì có thể thu phần tử nhỏ nhất, nhưng thường `min` diễn đạt ý định rõ hơn và tránh yêu cầu sắp xếp toàn bộ dữ liệu.

### 4.2. Với nguồn không có encounter order

~~~java
Optional<Integer> chosen = java.util.Set.of(3, 1, 2)
    .stream()
    .findFirst();
~~~

Không nên đoán `chosen` chứa `1` chỉ vì nó là giá trị nhỏ nhất hoặc vì một lần chạy xuất ra như vậy. Một `Set` không có encounter order được bảo đảm có thể khiến `findFirst` chọn bất kỳ phần tử nào. Tương tự, nếu dùng `unordered()` trên Stream, khái niệm phần tử đầu tiên không còn ràng buộc theo thứ tự nguồn.

### 4.3. findFirst và Stream song song

`findFirst` phải tôn trọng encounter order nếu Stream có thứ tự, kể cả khi xử lý bằng `parallel()`. Điều này có thể làm giảm hiệu năng do cần xác định phần tử đầu tiên theo thứ tự, thay vì lấy kết quả của nhánh hoàn thành sớm nhất.

Nếu nghiệp vụ chỉ cần **một phần tử bất kỳ**, `findAny` cho phép cách thực thi linh hoạt hơn.

## 5. findAny: tìm một phần tử phù hợp không ràng buộc đại diện

`Stream.findAny()` cũng trả `Optional<T>`:

~~~java
Optional<T> findAny()
~~~

Khác với `findFirst`, **API không cam kết** phần tử nào sẽ được trả nếu có nhiều phần tử phù hợp. Trên Stream tuần tự, bạn thường thấy nó trả phần tử đầu tiên, nhưng đó không phải quy tắc để viết logic nghiệp vụ.

~~~java
import java.util.List;

List<String> cities = List.of("Hà Nội", "Đà Nẵng", "Huế");

boolean hasLongName = cities.parallelStream()
    .filter(name -> name.length() >= 5)
    .findAny()
    .isPresent();

System.out.println(hasLongName); // true
~~~

Ở đây câu hỏi là **có phần tử nào phù hợp hay không**. Nếu chỉ cần một kết quả `boolean`, `anyMatch(...)` còn diễn đạt trực tiếp hơn:

~~~java
boolean hasLongNameDirectly = cities.stream()
    .anyMatch(name -> name.length() >= 5);
~~~

Chỉ chọn `findAny` khi bạn **cần sử dụng chính phần tử** tìm được. Các trường hợp phù hợp có thể là chọn một phần tử mẫu từ tập dữ liệu, hoặc lấy bất kỳ tài nguyên đáp ứng điều kiện mà không có ưu tiên thứ tự.

| Thuộc tính | `findFirst` | `findAny` |
|---|---|---|
| Kết quả | `Optional<T>` | `Optional<T>` |
| Có thể kết thúc sớm | Có | Có |
| Có giữ encounter order khi nguồn có thứ tự | Có | Không cam kết |
| Chạy parallel có thể linh hoạt chọn nhánh | Ít linh hoạt hơn | Linh hoạt hơn |
| Dùng khi | Muốn **đại diện đầu tiên** | Muốn **đại diện bất kỳ** |

**Điều kiện chung:** khi không có phần tử nào, cả hai trả `Optional.empty()`. Nếu phần tử được chọn là `null` thì API có thể ném `NullPointerException`; mục 9 giải thích cách xử lý.

## 6. min và max: Comparator định nghĩa giá trị nhỏ nhất/lớn nhất

Hai terminal operation:

~~~java
Optional<T> min(Comparator<? super T> comparator)
Optional<T> max(Comparator<? super T> comparator)
~~~

`Comparator` xác định **thứ tự so sánh**; `min` lấy phần tử thấp nhất, `max` lấy phần tử cao nhất theo quy tắc đó.

### 6.1. Min/max với số nguyên và chuỗi

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> scores = List.of(8, 5, 10, 7);

int lowest = scores.stream()
    .min(Integer::compareTo)
    .orElseThrow(() -> new IllegalStateException("Danh sách rỗng"));

int highest = scores.stream()
    .max(Comparator.naturalOrder())
    .orElseThrow(() -> new IllegalStateException("Danh sách rỗng"));

System.out.println(lowest);  // 5
System.out.println(highest); // 10
~~~

Với chuỗi, `Comparator.naturalOrder()` dựa vào quy tắc `String.compareTo`, **không mặc nhiên** tương đương sắp xếp theo ngôn ngữ tự nhiên hoặc không phân biệt hoa/thường.

### 6.2. So sánh đối tượng theo thuộc tính

Giả sử ta cần đơn hàng giá trị cao nhất:

~~~java
Comparator<Order> byAmount =
    Comparator.comparingLong(Order::amountVnd);

Optional<Order> mostExpensive = orders.stream()
    .max(byAmount);
~~~

`Comparator.comparingLong` thích hợp với thuộc tính `long`, tránh boxing chỉ để so sánh. Đoạn ví dụ này dùng kiểu `Order` và biến `orders` từ chương trình hoàn chỉnh ở mục 3.

**Tie-breaker:** nếu nhiều đơn có cùng số tiền, việc so sánh theo `amountVnd` cho kết quả bằng 0 giữa chúng. Nếu nghiệp vụ yêu cầu chọn **đơn có mã nhỏ nhất** khi số tiền bằng nhau, hãy diễn đạt bằng comparator và lựa chọn min/max cho nhất quán.

Ví dụ: “Lấy đơn có số tiền lớn nhất, nếu bằng nhau lấy mã **nhỏ hơn**”:

~~~java
Comparator<Order> byAmountThenPreferredId =
    Comparator.comparingLong(Order::amountVnd)
        .thenComparing(Order::id, Comparator.reverseOrder());

Optional<Order> selected = orders.stream()
    .max(byAmountThenPreferredId);

// Với ví dụ mục 3, hai đơn giá 250000 có ID DH03 và DH04.
// max theo comparator trên chọn DH03.
System.out.println(selected.map(Order::id).orElse("Không có")); // DH03
~~~

Lý do: `max` chọn giá trị được comparator xếp **lớn nhất**; ở phần mã đơn, `reverseOrder()` khiến mã chữ nhỏ hơn được xếp lớn hơn trong phép so sánh phụ. Cách này chỉ đúng với yêu cầu đang mô tả, không có một tie-breaker mặc định cho mọi miền nghiệp vụ.

### 6.3. min/max trên Stream rỗng

~~~java
Optional<Integer> min = List.<Integer>of().stream()
    .min(Integer::compareTo);

System.out.println(min.isPresent()); // false
~~~

Không có giá trị nhỏ nhất khi tập phần tử rỗng. Đó là lý do `min` và `max` trả Optional, thay vì tự chọn một số mặc định có thể không phù hợp.

Ngoài ra, **`min` và `max` thường phải xem đủ các phần tử của nguồn hữu hạn** để biết kết quả cuối, khác với `findFirst` có thể dừng sớm. Với nguồn vô hạn, một phép toán cần khảo sát toàn bộ nguồn có thể không hoàn thành. Nếu comparator hoặc hàm tạo dữ liệu có tác dụng phụ, không dựa vào số lần gọi comparator để thực hiện nghiệp vụ.

### 6.4. Không nhầm min/max với thứ tự theo equals

`min` và `max` làm việc theo `Comparator`. Hai đối tượng có thể được comparator xem là ngang nhau dù `equals` của chúng khác nhau. Ví dụ, hai đơn hàng có cùng giá trị 250.000 nhưng khác ID là hai đối tượng khác nhau; chúng vẫn đồng hạng theo `comparingLong(Order::amountVnd)`.

## 7. reduce: khi phép gộp có thể không có kết quả

`reduce` kết hợp nhiều phần tử thành một kết quả: tính tổng, tích, tìm giá trị tích lũy hoặc kết hợp các cấu trúc bất biến. Có **hai dạng quan trọng** khi xét kết quả rỗng.

### 7.1. reduce không có identity trả Optional

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Ví dụ tính tổng:

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> numbers = List.of(4, 6, 10);

Optional<Integer> total = numbers.stream()
    .reduce(Integer::sum);

System.out.println(total.orElse(0)); // 20
~~~

Với ba phần tử, phép gộp `Integer::sum` tạo `4 + 6 + 10 = 20`. Với Stream rỗng, không có phần tử nào để dùng làm giá trị ban đầu, nên:

~~~java
Optional<Integer> emptyTotal = List.<Integer>of()
    .stream()
    .reduce(Integer::sum);

System.out.println(emptyTotal.isPresent()); // false
~~~

Dù toán học có thể quy ước tổng tập rỗng bằng 0, **overload không có identity** vẫn trả Optional rỗng. Chính ứng dụng phải quyết định có dùng 0 làm giá trị mặc định hay không.

### 7.2. reduce có identity trả trực tiếp giá trị

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Ví dụ:

~~~java
int total = numbers.stream()
    .reduce(0, Integer::sum);

int emptyTotal = List.<Integer>of()
    .stream()
    .reduce(0, Integer::sum);

System.out.println(total);      // 20
System.out.println(emptyTotal); // 0
~~~

`identity` là phần tử trung hòa của phép kết hợp:

- Với cộng số học, identity là **0**.
- Với nhân số học, identity là **1**.
- Với nối chuỗi, identity thường là **""**.

Chọn identity sai làm sai cả dữ liệu không rỗng. Ví dụ `Stream.of(5, 8).reduce(0, Integer::min)` cho `0`, vì 0 nhỏ hơn cả 5 và 8. Do đó muốn tìm min thường nên dùng **`min(...)` trả Optional** hoặc `reduce(Integer::min)` không có identity, thay vì mặc định bắt đầu bằng 0.

### 7.3. Phép kết hợp cần bảo đảm associativity

Để `reduce` hoạt động đúng, đặc biệt khi chia nhỏ để xử lý song song, accumulator cần **associative**: 

`(a ◦ b) ◦ c = a ◦ (b ◦ c)`.

Cộng số nguyên thường là ví dụ quen thuộc trong phạm vi quy tắc số nguyên của Java; **phép trừ không có tính kết hợp**:

~~~java
List<Integer> values = List.of(10, 3, 2);

// Không dùng kiểu này nếu muốn một reduction ổn định khi song song.
int sequential = values.stream()
    .reduce((a, b) -> a - b)
    .orElse(0); // (10 - 3) - 2 = 5
~~~

Nếu chia nhóm và kết hợp theo thứ tự khác, phép trừ có thể cho kết quả khác. Với `double`, phép cộng cũng có vấn đề về **thứ tự làm tròn** và số học dấu phẩy động: xử lý song song hoặc đổi thứ tự phép gộp có thể tạo chênh lệch nhỏ. Với tổng tiền tệ cần tính chính xác, cân nhắc đơn vị tiền nguyên nhỏ nhất hoặc `BigDecimal` theo chính sách nghiệp vụ.

### 7.4. Primitive Stream dùng Optional chuyên biệt

Để tránh boxing, có thể chọn `IntStream` hoặc `LongStream`:

~~~java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt intTotal = IntStream.of(2, 3, 5)
    .reduce(Integer::sum);

OptionalLong longTotal = LongStream.of(1_000_000_000L, 2_000_000_000L)
    .reduce(Long::sum);

System.out.println(intTotal.orElse(0));   // 10
System.out.println(longTotal.orElse(0L)); // 3000000000
~~~

`IntStream.reduce(IntBinaryOperator)` trả `OptionalInt`; `LongStream.reduce(LongBinaryOperator)` trả `OptionalLong`; `DoubleStream.reduce(DoubleBinaryOperator)` trả `OptionalDouble`. Nếu dùng overload có identity, chúng trả nguyên thủy `int`, `long` hoặc `double`.

Với tính tổng thông thường, `sum()` là cách ngắn gọn hơn. Nhưng `sum()` trả nguyên thủy và có quy tắc kết quả riêng cho Stream rỗng (tổng bằng 0), trong khi `reduce(operator)` trả Optional rỗng. Chọn API dựa theo nhu cầu thể hiện trạng thái “không có dữ liệu”.

### 7.5. reduce không dành cho cập nhật collection chia sẻ

Không dùng `reduce` để liên tục sửa một `ArrayList` hoặc `HashMap` tích lũy được chia sẻ. Phép gộp trong reduction nên tuân thủ hợp đồng về tính kết hợp và tránh tác dụng phụ. Khi muốn tạo `List`, `Map` hoặc nhóm dữ liệu, dùng **`collect` và `Collector`**; khi muốn tổng hợp nhiều thuộc tính, có thể dùng collector phù hợp hoặc custom collector với cách phối hợp thread-safe đúng hợp đồng.

## 8. Xử lý Optional an toàn và đúng nghiệp vụ

Tìm thấy một `Optional<T>` mới là nửa đầu câu chuyện. Phần quan trọng là **quyết định làm gì khi không có giá trị**.

### 8.1. orElse: cung cấp giá trị mặc định

~~~java
Optional<String> first = List.<String>of().stream()
    .findFirst();

String label = first.orElse("Không tìm thấy");

System.out.println(label); // Không tìm thấy
~~~

`orElse(defaultValue)` phù hợp khi giá trị mặc định có sẵn, rẻ để tạo và có ý nghĩa trong miền dữ liệu. Không nên mặc định chọn `null` hoặc một số như 0 nếu điều đó che giấu lỗi đầu vào.

### 8.2. orElseGet: chỉ tính mặc định khi cần

`orElseGet(Supplier<? extends T>)` gọi supplier **chỉ khi Optional rỗng**. Ngược lại, biểu thức truyền vào `orElse(...)` được Java đánh giá **ngay khi gọi phương thức**, dù Optional có giá trị.

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();
Optional<String> present = Optional.of("DH01");

String a = present.orElse("Mã-" + calls.incrementAndGet());
System.out.println(calls.get()); // 1: đã tính biểu thức mặc định

String b = present.orElseGet(() -> "Mã-" + calls.incrementAndGet());
System.out.println(calls.get()); // Vẫn là 1: supplier chưa được gọi

System.out.println(a + ", " + b); // DH01, DH01
~~~

Bộ đếm chỉ minh họa cơ chế đánh giá. Trong code thật, `orElseGet` thích hợp với việc lấy dữ liệu dự phòng hoặc tạo đối tượng tốn chi phí. Khi supplier có I/O hoặc trạng thái, vẫn cần xử lý lỗi và phạm vi tác dụng phụ.

### 8.3. orElseThrow: yêu cầu bắt buộc phải có giá trị

Nếu việc không tìm thấy là lỗi nghiệp vụ, hãy thể hiện trực tiếp:

~~~java
String required = List.of("A", "B").stream()
    .filter(value -> value.equals("B"))
    .findFirst()
    .orElseThrow(() -> new IllegalArgumentException("Không có giá trị B"));

System.out.println(required); // B
~~~

Overload `orElseThrow(Supplier<? extends X>)` có từ Java 8; `orElseThrow()` không tham số xuất hiện ở Java 10. Với Java 8, cũng có `get()` nhưng khi rỗng nó ném `NoSuchElementException` ít ngữ cảnh. Trong mã nghiệp vụ, `orElseThrow(() -> new ...("thông báo cụ thể"))` thường dễ chẩn đoán hơn.

### 8.4. ifPresent và ifPresentOrElse: xử lý theo nhánh

~~~java
import java.util.Optional;

Optional<String> result = Optional.of("DH01");

result.ifPresent(id -> System.out.println("Tìm thấy: " + id));
// Tìm thấy: DH01
~~~

`ifPresent(Consumer)` chỉ chạy khi có giá trị. Nếu cần nhánh khi rỗng, Java 9+ hỗ trợ `ifPresentOrElse(Consumer, Runnable)`:

~~~java
result.ifPresentOrElse(
    id -> System.out.println("Tìm thấy: " + id),
    () -> System.out.println("Không tìm thấy")
);
~~~

Với Java 8, có thể dùng `ifPresent` kết hợp xử lý khác ở bên gọi, hoặc dùng `orElse`/`orElseGet` tùy nhu cầu trả kết quả.

### 8.5. map, filter và flatMap trên Optional

`Optional` cũng có những phép toán khai báo để làm việc với **tối đa một giá trị**:

~~~java
Optional<String> normalizedId = orders.stream()
    .filter(Order::paid)
    .findFirst()
    .map(Order::id)
    .map(String::trim)
    .filter(id -> !id.isEmpty());
~~~

Đoạn này dùng `Order` và `orders` ở mục 3. Từng `map` chỉ chạy khi Optional có giá trị. Nếu mapper trả `null`, `Optional.map` tạo Optional rỗng theo hợp đồng, nhưng nên tránh dùng `null` như tín hiệu điều khiển khi có thể định nghĩa rõ kết quả.

`flatMap` dùng khi mapper **đã trả về một Optional**, giúp tránh `Optional<Optional<T>>`:

~~~java
import java.util.Optional;

Optional<String> input = Optional.of("42");
Optional<Integer> parsed = input.flatMap(value -> {
    try {
        return Optional.of(Integer.parseInt(value));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
});

System.out.println(parsed.orElse(-1)); // 42
~~~

Lưu ý `Optional.flatMap` không chấp nhận mapper trả `null`: trường hợp đó ném `NullPointerException`. Ví dụ bắt `NumberFormatException` ở đây phục vụ minh họa quy tắc parse tùy chọn; với hệ thống có yêu cầu chẩn đoán lỗi, cần báo lỗi chi tiết thay vì luôn chuyển lỗi parse thành “không có”.

### 8.6. Optional.stream để kết hợp lại với Stream (Java 9+)

Nếu có nhiều Optional và muốn lấy tất cả giá trị có mặt:

~~~java
import java.util.List;
import java.util.Optional;

List<String> presentValues = List.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B")
    ).stream()
    .flatMap(Optional::stream)
    .toList(); // [A, B]
~~~

`Optional.stream()` có từ Java 9, còn `Stream.toList()` có từ Java 16. Với Java 9–15, thay `toList()` bằng `collect(Collectors.toList())`. Khi dùng `Optional.stream()`, Optional rỗng đóng góp **0 phần tử**, Optional có giá trị đóng góp **1 phần tử**.

## 9. OptionalInt, OptionalLong và OptionalDouble

Stream nguyên thủy không trả `Optional<Integer>`, `Optional<Long>` hoặc `Optional<Double>` trong các phép toán tìm một giá trị. Chúng trả các kiểu **chuyên biệt**, tránh boxing:

| Nguồn | `findFirst` / `findAny` | `min` / `max` | `reduce(operator)` | `average` |
|---|---|---|---|---|
| `IntStream` | `OptionalInt` | `OptionalInt` | `OptionalInt` | `OptionalDouble` |
| `LongStream` | `OptionalLong` | `OptionalLong` | `OptionalLong` | `OptionalDouble` |
| `DoubleStream` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |

Ví dụ:

~~~java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt min = IntStream.of(4, 7, 2).min();
OptionalDouble average = IntStream.of(4, 7, 2).average();

System.out.println(min.orElse(-1));           // 2
System.out.println(average.orElse(Double.NaN)); // 4.333...
~~~

`OptionalInt` có `getAsInt()`, `orElse(int)`, `orElseGet(IntSupplier)`, `orElseThrow(...)` và một số phương thức kiểm tra/tiêu thụ giá trị. Tương tự, `OptionalLong` có `getAsLong()`, `OptionalDouble` có `getAsDouble()`. Các kiểu này **không có đầy đủ mọi phép biến đổi `map`/`flatMap` giống `Optional<T>`**; đừng viết `optionalInt.map(...)` theo thói quen từ Optional đối tượng.

Nếu cần chuyển sang đối tượng hoặc tiếp tục với `Stream<T>`, cân nhắc tạo Stream từ Optional nguyên thủy bằng `stream()` (Java 9+) rồi `mapToObj` hoặc thực hiện chuyển kiểu rõ ràng khi có giá trị.

~~~java
int[] values = IntStream.of(8, 3, 6)
    .min()
    .stream() // IntStream 0 hoặc 1 phần tử, Java 9+
    .toArray();

System.out.println(java.util.Arrays.toString(values)); // [3]
~~~

Với Optional rỗng, `stream()` của Optional nguyên thủy cũng tạo Stream rỗng.

## 10. Optional và null: phân biệt “không có” với “có null”

`Optional<T>` **không chứa `null`**. Hai cách tạo Optional khác nhau:

~~~java
Optional<String> absent = Optional.ofNullable(null);
System.out.println(absent.isPresent()); // false

// Optional.of(null); // Ném NullPointerException.
~~~

Đối với các phép toán tìm kết quả trên Stream, có hai tình huống cần tách biệt:

1. **Stream không có phần tử phù hợp:** `findFirst`, `findAny`, `min`, `max` và `reduce(accumulator)` trả Optional rỗng.
2. **Stream có phần tử `null` được chọn làm kết quả:** một số phép toán như `findFirst`/`findAny` có thể ném `NullPointerException`, thay vì trả Optional chứa null.

Ví dụ:

~~~java
import java.util.Arrays;
import java.util.Objects;

// Nguồn này có một phần tử null:
List<String> values = Arrays.asList(null, "Java");

// values.stream().findFirst(); // Ném NullPointerException.

String firstNonNull = values.stream()
    .filter(Objects::nonNull)
    .findFirst()
    .orElse("Không có");

System.out.println(firstNonNull); // Java
~~~

`List.of(null, "Java")` không phải cách tạo nguồn tương đương, vì `List.of` tự từ chối null. Nếu nghiệp vụ cần giữ lại ý nghĩa đặc biệt của dữ liệu thiếu, hãy dùng một mô hình dữ liệu biểu diễn trạng thái thiếu rõ ràng thay vì để null đi qua pipeline một cách ngầm định.

Với `reduce(accumulator)`, accumulator **không nên trả null**; nếu kết quả reduction là null, một số overload có thể ném `NullPointerException`. Tương tự, comparator và phép toán khác không nhất thiết xử lý được null. Cần xác định quy tắc lọc, chuẩn hóa hoặc báo lỗi dữ liệu trước khi tổng hợp.

## 11. Tính lazy, tài nguyên và khả năng dừng

`findFirst`, `findAny`, `min`, `max` và `reduce` là terminal operation: chúng **kích hoạt** pipeline lazy. Tuy nhiên, lượng dữ liệu cần duyệt không giống nhau:

~~~java
import java.util.stream.IntStream;

int firstMultipleOfSeven = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n % 7 == 0)
    .findFirst()
    .orElse(-1);

System.out.println(firstMultipleOfSeven); // 7
~~~

Ở đây `findFirst` có thể dừng khi tìm thấy 7, không cần kiểm tra hết một triệu số. `findAny` cũng có khả năng dừng sớm.

Ngược lại, `min`, `max` và `reduce` thường cần xử lý **toàn bộ nguồn hữu hạn** để xác định kết quả. Với nguồn vô hạn, ví dụ `IntStream.iterate(0, n -> n + 1).max()`, một phép toán yêu cầu giá trị cuối có thể không hoàn thành. Đừng kỳ vọng tính lazy tự biến nguồn vô hạn thành phép tính kết thúc.

### 11.1. Thứ tự thao tác thay đổi kết quả

~~~java
List<Integer> values = List.of(10, 2, 8, 4);

int firstOfFirstTwo = values.stream()
    .limit(2)
    .min(Integer::compareTo)
    .orElse(-1); // 2

int globalMinThenLimited = values.stream()
    .min(Integer::compareTo)
    .orElse(-1); // 2
~~~

Hai giá trị tình cờ giống nhau ở dữ liệu này; đổi danh sách thành `List.of(10, 8, 2, 4)` thì phép thứ nhất trả **8**, phép thứ hai trả **2**. Ý nghĩa của `limit(2).min(...)` là **min của hai phần tử đầu**, còn `min(...)` là **min của toàn bộ nguồn**.

Với `sorted()` và `findFirst()`, thao tác `sorted` thường phải khảo sát nguồn hữu hạn trước khi trả phần tử đầu; không nên suy luận rằng `findFirst` luôn làm pipeline dừng sớm ở mọi vị trí.

### 11.2. Stream chỉ được tiêu thụ một lần

~~~java
var stream = List.of(3, 6, 9).stream();
Optional<Integer> first = stream.findFirst();

// stream.max(Integer::compareTo); // Không hợp lệ: Stream đã tiêu thụ.
~~~

Cần tạo **Stream mới** từ `List` cho mỗi terminal operation. Nếu nguồn là Stream I/O như `Files.lines(...)`, còn phải đóng tài nguyên đúng cách, ví dụ dùng `try-with-resources`. Optional chỉ biểu diễn **kết quả có/không**, nó **không quản lý việc đóng Stream**.

### 11.3. Không dựa vào tác dụng phụ trong callback

Predicate, mapper và accumulator trong pipeline nên không can thiệp nguồn và không dựa vào trạng thái bên ngoài có thể thay đổi. Stream có thể dừng sớm, xử lý song song hoặc bỏ qua những bước không cần thiết cho kết quả cuối. Vì vậy không dùng các callback đó làm nơi bắt buộc ghi log, gửi thông báo hoặc cập nhật dữ liệu quan trọng.

## 12. Các lỗi thường gặp và cách sửa

| Cách viết có vấn đề | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| `stream.findFirst().get()` mà không kiểm tra | Khi rỗng, ném `NoSuchElementException` | Dùng `orElse`, `orElseGet` hoặc `orElseThrow` có thông báo |
| `findAny()` rồi so sánh cứng với phần tử đầu | `findAny` không bảo đảm đại diện nào | Nếu cần đầu tiên, dùng `findFirst` trên nguồn có thứ tự |
| `min(comparator)` với comparator sai chiều | Min thực tế có thể là max của tiêu chí | Xác định và kiểm tra quy tắc comparator |
| `reduce(0, Integer::min)` để tìm min | Identity 0 có thể nhỏ hơn mọi giá trị | Dùng `min` hoặc `reduce(Integer::min)` |
| `orElse(expensiveCall())` | Gọi hàm dự phòng ngay cả khi có dữ liệu | Dùng `orElseGet(() -> expensiveCall())` |
| `Optional.of(nullableValue)` | Ném lỗi nếu `null` | Dùng `ofNullable` khi chủ đích cho phép thiếu |
| Gọi `findFirst` trên nguồn có null đứng đầu | Optional không chứa null | Chuẩn hóa/lọc `Objects::nonNull` |
| `reduce` với accumulator dùng biến chung | Phụ thuộc trạng thái và có thể sai khi song song | Dùng phép kết hợp có tính kết hợp, không can thiệp trạng thái |
| Gọi tiếp một terminal trên cùng Stream | Stream đã tiêu thụ | Tạo Stream mới từ nguồn có thể dùng lại |
| Dùng `orElse(0)` mà không xét ý nghĩa nghiệp vụ | Có thể che giấu sự khác biệt giữa “không có” và “bằng 0” | Chọn chính sách thiếu dữ liệu và truyền đạt rõ |

Nên ưu tiên Optional ở **giá trị trả về nơi có thể thiếu kết quả**, thay vì đưa Optional tràn lan vào mọi trường dữ liệu, tham số hoặc collection. Đối với các miền nghiệp vụ cần biết **vì sao** thất bại (lỗi xác thực, dữ liệu không hợp lệ, nguồn mất kết nối), Optional không mang thông tin lỗi; hãy dùng kiểu kết quả hoặc ngoại lệ thích hợp.

## 13. Bài thực hành: phân tích điểm kiểm tra

Một khóa học có điểm đánh giá từ danh sách `List<Integer>`. Yêu cầu:

1. Tìm điểm đầu tiên từ 8 trở lên.
2. Tìm điểm nhỏ nhất và điểm lớn nhất.
3. Tính tổng điểm bằng `reduce` không có identity.
4. Giải quyết trường hợp danh sách rỗng bằng chính sách rõ ràng.
5. Không gọi `get()` nếu chưa xử lý Optional.

**Lời giải tham khảo (Java 8+):**

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ScoreOptionalPractice {
    public static void main(String[] args) {
        List<Integer> scores = Arrays.asList(6, 9, 7, 10, 8);

        Optional<Integer> firstHigh = scores.stream()
            .filter(score -> score >= 8)
            .findFirst();

        Optional<Integer> minimum = scores.stream()
            .min(Comparator.naturalOrder());

        Optional<Integer> maximum = scores.stream()
            .max(Comparator.naturalOrder());

        Optional<Integer> total = scores.stream()
            .reduce(Integer::sum);

        System.out.println("Điểm cao đầu tiên: "
            + firstHigh.map(String::valueOf).orElse("Không có"));
        System.out.println("Điểm thấp nhất: "
            + minimum.map(String::valueOf).orElse("Không có"));
        System.out.println("Điểm cao nhất: "
            + maximum.map(String::valueOf).orElse("Không có"));
        System.out.println("Tổng điểm: "
            + total.map(String::valueOf).orElse("Chưa có điểm"));
    }
}
~~~

Kết quả:

~~~text
Điểm cao đầu tiên: 9
Điểm thấp nhất: 6
Điểm cao nhất: 10
Tổng điểm: 40
~~~

Nếu thay `scores` bằng một danh sách rỗng, tất cả bốn kết quả sẽ là `Optional.empty()` và chương trình in thông báo theo từng chính sách thay vì ném lỗi. Nếu nghiệp vụ quy định “tổng của danh sách rỗng bằng 0” thì dùng `scores.stream().reduce(0, Integer::sum)` hoặc `mapToInt(Integer::intValue).sum()` và giải thích rõ quy ước đó.

**Tự kiểm tra kiến thức:**

1. `findFirst()` trên Stream rỗng trả gì? — **`Optional.empty()`**.
2. `findAny()` có bảo đảm giữ phần tử đầu tiên của `List` không? — **Không**.
3. `min(Comparator.naturalOrder())` trên `List.of(9, 2, 5)` trả gì? — **Optional chứa 2**.
4. `Stream.of(5, 8).reduce(0, Integer::min)` trả gì? — **0**, do identity không phù hợp với phép min trên các số dương.
5. `Stream.<Integer>empty().reduce(Integer::sum)` trả gì? — **Optional rỗng**, không phải Optional chứa 0.
6. `IntStream.of(2, 4).average()` trả kiểu nào? — **`OptionalDouble`**.
7. `orElseGet` có gọi supplier khi Optional có giá trị không? — **Không**.
8. `findFirst` có luôn duyệt toàn bộ dữ liệu không? — **Không**, có khả năng dừng sớm; các thao tác trước đó có thể khiến nó cần nhiều công việc hơn.

## 14. Ghi nhớ trước khi học các phép tổng hợp nâng cao

**`findFirst`** lấy phần tử đầu tiên khi có encounter order; **`findAny`** lấy phần tử bất kỳ; **`min`/`max`** chọn phần tử theo comparator; còn **`reduce(accumulator)`** kết hợp các phần tử khi không cung cấp identity. Chúng trả **Optional** vì kết quả có thể không tồn tại.

Hãy xem Optional như một **hợp đồng bắt người gọi đối diện với trường hợp rỗng**: dùng `orElse` cho mặc định đơn giản, `orElseGet` cho mặc định tính khi cần, `orElseThrow` khi kết quả là bắt buộc, hoặc `ifPresent` và các phép biến đổi Optional khi muốn tiếp tục xử lý khai báo. Với số nguyên thủy, sử dụng đúng `OptionalInt`, `OptionalLong` hoặc `OptionalDouble`.

Khi thiết kế pipeline, hãy kiểm tra **ngữ nghĩa rỗng**, **thứ tự và tiêu chí chọn phần tử**, **khả năng dừng của nguồn**, **phép kết hợp trong reduce** và **tác dụng phụ trong callback**. Nắm được những điều này giúp chuyển tiếp sang `collect`, grouping, collector tùy chỉnh, `Spliterator`, parallel Stream và Stream Gatherers mà vẫn giữ kết quả rõ nghĩa và có thể kiểm tra.
