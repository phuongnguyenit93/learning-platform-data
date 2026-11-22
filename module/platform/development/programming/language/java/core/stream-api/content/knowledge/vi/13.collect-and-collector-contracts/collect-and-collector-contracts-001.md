# Phân biệt rút gọn bất biến và rút gọn vào bộ chứa mutable

Trong một pipeline **Java Stream API**, sau các bước `filter` và `map`, ta thường cần kết hợp nhiều phần tử thành một kết quả: tổng doanh thu, số lượng đơn hàng, một chuỗi tóm tắt, danh sách đã chuẩn hóa, hay bảng thống kê theo nhóm. Hoạt động **rút gọn** (*reduction*) biến một dãy phần tử thành kết quả tổng hợp.

Java có hai cách tiếp cận quan trọng:

- **Rút gọn không đột biến kết quả tích lũy** (*non-mutating reduction*), thường dùng `reduce`. Mỗi bước tính một giá trị tích lũy mới từ giá trị trước đó và phần tử hiện tại, chẳng hạn cộng hai số để ra một số mới.
- **Rút gọn vào bộ chứa có thể thay đổi** (*mutable reduction*), thường dùng `collect`. Mỗi phần tử được đưa vào một **bộ chứa kết quả** như `ArrayList`, `HashMap` hoặc đối tượng thống kê; bộ chứa được cập nhật tại chỗ rồi có thể được hợp nhất với bộ chứa khác.

Hai cách đều thuộc mô hình xử lý dữ liệu khai báo của module **JAVA_STREAM_API**, nhưng hợp đồng API và cách vận hành trong **parallel Stream** khác nhau đáng kể. Bài này thuộc chương **Cơ chế collect và Collector**, cung cấp nền tảng để học `groupingBy`, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers mà vẫn nhận diện được những giới hạn về trạng thái, bộ nhớ và hiệu năng.

Sau bài, bạn có thể giải thích vì sao tính tổng thường dùng `reduce` hoặc `sum`, vì sao tạo `List` nên dùng `collect`, cách hoạt động của `supplier` / `accumulator` / `combiner`, và vì sao **không được dùng một danh sách mutable làm identity để giả lập `collect` bằng `reduce`**.

## 1. Một bài toán, hai loại kết quả

Giả sử hệ thống bán hàng có bốn đơn hàng. Ta muốn:

1. Tính **tổng tiền các đơn đã thanh toán**: kết quả là một giá trị `long`.
2. Thu **danh sách mã các đơn đã thanh toán**: kết quả là một `List<String>`.

Ví dụ hoàn chỉnh dùng **Java 17 trở lên** vì `record` và `Stream.toList()`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class TwoReductionStyles {
    record Order(String id, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", 120_000L, true),
            new Order("DH02",  80_000L, false),
            new Order("DH03", 150_000L, true),
            new Order("DH04",  50_000L, true)
        );

        long paidTotal = orders.stream()
            .filter(Order::paid)
            .map(Order::amountVnd)
            .reduce(0L, Long::sum);

        List<String> paidIds = orders.stream()
            .filter(Order::paid)
            .map(Order::id)
            .collect(Collectors.toList());

        System.out.println(paidTotal); // 320000
        System.out.println(paidIds);   // [DH01, DH03, DH04]
    }
}
~~~

Cả hai pipeline đều bắt đầu từ một `List<Order>` và sử dụng những bước trung gian lazy. Khác nhau nằm ở **cách xây kết quả**:

- `reduce(0L, Long::sum)` kết hợp các số thành một `long` mới sau mỗi bước. Không có đối tượng tích lũy kiểu collection cần sửa tại chỗ.
- `collect(Collectors.toList())` thu các chuỗi vào một hay nhiều bộ chứa dạng danh sách và trả kết quả. Việc thêm phần tử vào danh sách là thao tác **mutable**, nhưng được thực hiện bên trong cơ chế collector.

Có thể thay phép tính tổng bằng `mapToLong(Order::amountVnd).sum()`, thường gọn hơn và tránh boxing. Ở đây `reduce` được viết tường minh để nhìn rõ nguyên lý.

> **Rút gọn bất biến không có nghĩa mọi phần tử nguồn đều bất biến.** Nó mô tả cách tích lũy **không sửa chính đối tượng kết quả trước đó**. Giá trị trả về sau mỗi bước có thể là số, chuỗi hoặc đối tượng bất biến mới. Ngược lại, một collector có thể tạo kết quả cuối cùng không cho phép sửa dù **bộ chứa tạm thời** trong quá trình thu thập vẫn mutable.

## 2. Hình dung hai luồng dữ liệu

~~~mermaid
flowchart TD
    S["Nguồn: 120000, 150000, 50000"] --> R["reduce(0, Long::sum)"]
    R --> R1["0 + 120000 = 120000"]
    R1 --> R2["120000 + 150000 = 270000"]
    R2 --> R3["270000 + 50000 = 320000"]
    R3 --> V["Giá trị cuối: 320000"]
    T["Nguồn: DH01, DH03, DH04"] --> C["collect(toList())"]
    C --> C1["Tạo danh sách []"]
    C1 --> C2["add(DH01), add(DH03), add(DH04)"]
    C2 --> L["Danh sách kết quả"]
~~~

Sơ đồ trên diễn giải trình tự **tuần tự** cho dễ hiểu. Khi thực thi song song, framework có thể chia dữ liệu thành nhiều nhánh rồi kết hợp kết quả theo cấu trúc khác; code phải vẫn cho **kết quả hợp lệ** theo hợp đồng của từng phương thức.

| Tiêu chí | Rút gọn bằng `reduce` | Rút gọn bằng `collect` |
|---|---|---|
| Ý tưởng | Kết hợp phần tử thành giá trị tích lũy mới | Đưa phần tử vào bộ chứa kết quả có thể thay đổi |
| Thường dùng cho | Tổng, tích, min/max, kết quả bất biến | `List`, `Set`, `Map`, nhóm, thống kê phức hợp |
| Hoạt động tích lũy | Hàm trả giá trị mới | Hàm cập nhật bộ chứa |
| Kết quả trên Stream rỗng | Identity nếu có; `Optional.empty()` nếu không có identity | Bộ chứa/giá trị rỗng do supplier và finisher tạo |
| Cách kết hợp nhánh | Phép kết hợp phải **associative** | Combiner hợp nhất các **bộ chứa** |
| Tác dụng phụ trong accumulator | Không nên có | Có tác dụng thay đổi **bộ chứa riêng** theo hợp đồng |
| API tiêu biểu | `reduce`, `mapToLong(...).sum()` | `collect`, `Collectors.toList()`, `groupingBy` |

## 3. reduce: tích lũy mà không thay đổi bộ chứa

`Stream<T>` có ba overload `reduce` phổ biến:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)

T reduce(T identity, BinaryOperator<T> accumulator)

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
~~~

Chúng đều thuộc **terminal operation**: chúng kích hoạt pipeline để tạo kết quả và tiêu thụ Stream. Điểm chung của `reduce` là accumulator mô tả **phép kết hợp giá trị**, không phải hành động sửa một container chia sẻ.

### 3.1. Có identity: kết quả rỗng trả identity

~~~java
import java.util.List;

List<Integer> values = List.of(3, 5, 7);

int total = values.stream()
    .reduce(0, (left, right) -> left + right);

int emptyTotal = List.<Integer>of().stream()
    .reduce(0, Integer::sum);

System.out.println(total);      // 15
System.out.println(emptyTotal); // 0
~~~

`0` là **identity** (phần tử trung hòa) của phép cộng: `0 + x = x` và `x + 0 = x`. `Integer::sum` là cách viết ngắn của hàm cộng hai số.

Đối với phép nhân, identity thường là `1`:

~~~java
int product = List.of(2, 3, 4).stream()
    .reduce(1, (a, b) -> a * b);

System.out.println(product); // 24
~~~

Nếu chọn identity sai, kết quả sai ngay từ ý nghĩa toán học. Ví dụ, `reduce(10, Integer::sum)` cộng thêm 10 so với tổng thực tế; identity 10 không hợp lệ cho phép cộng.

### 3.2. Không có identity: kết quả Optional

~~~java
import java.util.Optional;

Optional<Integer> max = List.of(4, 9, 2).stream()
    .reduce(Integer::max);

Optional<Integer> empty = List.<Integer>of().stream()
    .reduce(Integer::max);

System.out.println(max.orElse(-1));   // 9
System.out.println(empty.isPresent()); // false
~~~

Khi không có phần tử, không thể suy ra một giá trị lớn nhất hợp lệ từ dữ liệu, nên overload này trả `Optional.empty()`. Đừng chọn `reduce(0, Integer::max)` theo thói quen nếu nguồn có thể chứa toàn số âm: kết quả có thể sai. Với ý định tìm giá trị lớn nhất/nhỏ nhất, `max`/`min` cũng thể hiện đúng ngữ nghĩa và trả Optional.

### 3.3. Ba tham số: biến đổi kiểu kết quả tích lũy

Overload ba tham số cho phép phần tử đầu vào `T` được tích lũy vào kết quả `U` khác kiểu:

~~~java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi");

int totalCharacters = names.stream().reduce(
    0,
    (total, name) -> total + name.length(),
    Integer::sum
);

System.out.println(totalCharacters); // 9
~~~

Trong ví dụ này:

- `identity = 0`: độ dài ban đầu của kết quả.
- `accumulator`: nhận tổng `Integer` và một `String`, rồi **trả về tổng mới**.
- `combiner`: cộng hai tổng từng nhánh, cần thiết khi kết hợp các phần kết quả trong thực thi song song.

Lưu ý `"An"` có 2 ký tự, `"Bình"` có 4 ký tự và `"Chi"` có 3 ký tự; tổng bằng **9**. Dù đây là ví dụ hợp lệ, khi chỉ muốn tính số ký tự, pipeline `names.stream().mapToInt(String::length).sum()` thường ngắn hơn và tránh boxing.

## 4. Hợp đồng reduce: identity, tính kết hợp và trạng thái

Để framework có thể phân chia phần tử và kết hợp kết quả an toàn, phép giảm phải tuân thủ những điều kiện quan trọng.

### 4.1. Identity phải trung hòa

Với phép kết hợp `op`, identity `e` phải thỏa `op(e, x) = x` và `op(x, e) = x` cho các giá trị thích hợp. Với overload ba tham số, `combiner(identity, u)` phải bằng `u` đối với kết quả tích lũy hợp lệ.

Ví dụ: phép nối chuỗi có identity là chuỗi rỗng `""`. Nhưng dùng nối chuỗi bằng `reduce` cho đầu ra lớn có thể tốn nhiều phép cấp phát chuỗi vì `String` bất biến; khi cần xây chuỗi dài, `Collectors.joining` thường phù hợp hơn.

### 4.2. Phép kết hợp phải associative

Tính kết hợp có nghĩa:

~~~text
(a op b) op c = a op (b op c)
~~~

Phép cộng số nguyên trong phạm vi số học Java thường được dùng làm ví dụ. Phép trừ **không** associative:

~~~java
int sequential = List.of(10, 3, 2).stream()
    .reduce(0, (left, right) -> left - right);

System.out.println(sequential); // -15 (trên pipeline tuần tự này)
~~~

Kết quả tuần tự có thể trông hợp lý theo một công thức tự định nghĩa, nhưng **không phải reduction an toàn để chia nhánh rồi gộp tùy thứ tự**. Khi chạy song song, thứ tự ghép có thể khác và làm kết quả thay đổi.

Với `double`, phép cộng mang tính xấp xỉ do làm tròn số thực; thay đổi cách nhóm phép cộng có thể tạo khác biệt số học. Nếu dữ liệu tiền tệ cần chính xác, cân nhắc đơn vị tiền nguyên và xử lý tràn số, hoặc `BigDecimal` với quy tắc làm tròn đã xác định.

### 4.3. Accumulator phải không can thiệp nguồn và không có trạng thái ngoài

Một `reduce` chuẩn không nên có side effect lên nguồn hay bộ chứa dùng chung:

~~~java
int sum = List.of(2, 4, 6).parallelStream()
    .reduce(0, Integer::sum);

System.out.println(sum); // 12
~~~

Framework có thể tạo kết quả cục bộ cho từng nhánh và hợp nhất chúng. Vì vậy, hãy để phép tích lũy **trả kết quả từ các đối số** thay vì sửa biến ngoài; không dùng `reduce` để in log bắt buộc, cập nhật database hoặc ghi danh sách dùng chung.

### 4.4. Compatibility ở overload ba tham số

Với overload `reduce(identity, accumulator, combiner)`, accumulator và combiner còn phải **tương thích**. Về ý nghĩa, việc tích lũy `t` vào `u` rồi ghép với `v` phải cho kết quả giống tích lũy `t` sau khi đã ghép `u` và `v`:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

Đẳng thức trên biểu đạt luật tương thích cho các giá trị liên quan; nó giúp quá trình chia dãy thành các nhánh không đổi kết quả. Nếu accumulator và combiner thực hiện các phép toán khác ngữ nghĩa, pipeline song song có thể sai dù chạy tuần tự có vẻ đúng.

## 5. Vì sao không dùng reduce với một ArrayList mutable?

Một lỗi rất thường gặp là cố thu Stream thành danh sách bằng `reduce`:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

// Không nên làm: mutate identity và trả lại cùng đối tượng!
List<String> broken = words.parallelStream().reduce(
    new ArrayList<String>(),
    (list, word) -> {
        list.add(word);
        return list;
    },
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
~~~

**Đây không phải cách sử dụng `reduce` hợp lệ theo ý nghĩa rút gọn không đột biến.** Accumulator thay đổi chính `list` rồi trả về cùng tham chiếu; đối tượng `identity` có thể bị chia sẻ hoặc tái sử dụng giữa các nhánh, còn combiner có thể hợp nhất các tham chiếu trùng nhau. Kết quả có nguy cơ lặp, sai thứ tự, race condition hoặc lỗi runtime. Đừng dùng đoạn code này trong ứng dụng hoặc kỳ vọng nó luôn lỗi giống nhau.

Ngay cả khi chạy tuần tự và “có vẻ đúng”, cách viết vẫn gây hiểu lầm về hợp đồng của `reduce` và dễ hỏng khi đổi sang parallel Stream.

**Cách đúng:** dùng `collect`, vì API này được thiết kế để **tạo bộ chứa riêng, tích lũy vào bộ chứa, rồi gộp các bộ chứa**:

~~~java
List<String> words = List.of("Java", "Stream", "API");

List<String> safe = words.parallelStream()
    .collect(java.util.stream.Collectors.toList());

System.out.println(safe); // [Java, Stream, API]
~~~

Do nguồn là `List` có encounter order và collector `toList` duy trì thứ tự theo hợp đồng của kết quả thu thập có thứ tự, danh sách đầu ra có cùng trình tự giá trị. Dù vậy, API `Collectors.toList()` không bảo đảm lớp triển khai, khả năng sửa đổi, tính tuần tự hay thread-safety của **danh sách trả về**.

## 6. collect: rút gọn bằng bộ chứa mutable

`Stream<T>` có hai dạng `collect`:

~~~java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)

<R, A> R collect(Collector<? super T, A, R> collector)
~~~

Dạng thứ nhất truyền trực tiếp ba chức năng. Dạng thứ hai đóng gói quy tắc vào một `Collector` tái sử dụng được.

### 6.1. Thực hành dạng ba tham số

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

ArrayList<String> result = words.parallelStream().collect(
    ArrayList::new, // supplier: tạo bộ chứa mới
    ArrayList::add, // accumulator: thêm từng phần tử vào bộ chứa
    ArrayList::addAll // combiner: gộp bộ chứa khác vào bộ chứa này
);

System.out.println(result); // [Java, Stream, API]
~~~

Mỗi hàm làm đúng một việc:

| Thành phần | Kiểu hàm | Vai trò |
|---|---|---|
| `supplier` | `Supplier<R>` | Tạo **bộ chứa mới** khi cần |
| `accumulator` | `BiConsumer<R, T>` | Cập nhật một bộ chứa với một phần tử |
| `combiner` | `BiConsumer<R, R>` | Hợp nhất hai bộ chứa tương thích |

Ví dụ, nếu Stream được chia thành hai nhánh:

~~~text
Nhánh 1:
  supplier() -> []
  add("Java") -> ["Java"]
  add("Stream") -> ["Java", "Stream"]

Nhánh 2:
  supplier() -> []
  add("API") -> ["API"]

Kết hợp:
  left.addAll(right) -> ["Java", "Stream", "API"]
~~~

Đây là mô hình minh họa; số nhánh, thời điểm gọi supplier và cách gộp do framework quyết định. Không viết code phụ thuộc vào việc supplier được gọi đúng hai lần hay combiner chạy trên một thread nhất định.

### 6.2. Vì sao ArrayList không cần tự đồng bộ ở đây?

Trong mẫu thu thập thông thường, framework có thể phân chia dữ liệu và dùng **những container độc lập** cho các phần việc; sau đó kết hợp các container. Vì vậy accumulator có thể cập nhật `ArrayList` của chính nó, dù `ArrayList` không thread-safe.

Điều này **không đồng nghĩa** mọi cách chia sẻ một `ArrayList` giữa các thread đều an toàn. Nếu supplier luôn trả về **cùng một đối tượng** thay vì tạo mới, ví dụ trả biến danh sách đặt ngoài pipeline, tính độc lập sẽ bị phá vỡ và kết quả có thể sai. Tương tự, đưa các tác dụng phụ vào trạng thái ngoài collector có thể tạo race condition.

### 6.3. Muốn giữ một kiểu collection cụ thể

Nếu kết quả phải là `ArrayList` và cần một danh sách có thể sửa, có thể dùng:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> editable = words.stream()
    .collect(Collectors.toCollection(ArrayList::new));

editable.add("Collector");
System.out.println(editable); // [Java, Stream, API, Collector]
~~~

Khi chỉ cần một `List` và không có yêu cầu cụ thể về mutability, `Collectors.toList()` là cách đọc dễ hiểu. `Stream.toList()` (Java 16+) trả danh sách **không thể sửa**, khác với việc xác định một bộ chứa mutable cho quá trình thu thập.

## 7. Collector: hợp đồng của quá trình thu thập

`Collector<T, A, R>` mô tả cách biến các phần tử kiểu `T` thành kết quả `R` thông qua **bộ chứa trung gian** kiểu `A`.

Năm thành phần quan trọng của một Collector là:

1. **`supplier()`:** tạo bộ chứa `A` mới.
2. **`accumulator()`:** thêm một phần tử `T` vào `A`.
3. **`combiner()`:** hợp nhất hai bộ chứa `A`.
4. **`finisher()`:** chuyển bộ chứa `A` thành kết quả cuối `R`.
5. **`characteristics()`:** mô tả đặc tính như `IDENTITY_FINISH`, `UNORDERED` hoặc `CONCURRENT`.

~~~mermaid
flowchart TD
    S["Stream<T>"] --> L["Nhánh trái"]
    S --> R["Nhánh phải"]
    L --> A1["supplier -> A1"]
    R --> A2["supplier -> A2"]
    A1 --> B1["accumulator(A1, T)"]
    A2 --> B2["accumulator(A2, T)"]
    B1 --> C["combiner(A1, A2)"]
    B2 --> C
    C --> F["finisher(A) -> R"]
~~~

`A` và `R` **có thể là cùng một kiểu hoặc khác kiểu**. Ví dụ:

- `Collectors.toList()` dùng một container danh sách và trả danh sách.
- Một collector tính báo cáo có thể dùng `MutableStats` để cộng dồn trong lúc xử lý, rồi trả `Stats` bất biến khi hoàn tất.

Chính sự tách biệt **trung gian mutable** và **kết quả cuối** làm `Collector` linh hoạt hơn việc chỉ trả về một container.

### 7.1. Các đặc tính Collector cần hiểu đúng

| Đặc tính | Ý nghĩa |
|---|---|
| `IDENTITY_FINISH` | Finisher là phép đồng nhất, về bản chất kiểu tích lũy có thể được dùng làm kết quả; framework có thể bỏ qua bước finisher riêng |
| `UNORDERED` | Kết quả thu thập không cam kết giữ encounter order |
| `CONCURRENT` | Collector cho phép nhiều thread gọi accumulator **đồng thời trên cùng một container kết quả** theo hợp đồng |

**`CONCURRENT` không có nghĩa tất cả collector chạy parallel đều dùng chung container.** Các collector không concurrent vẫn có thể xử lý song song bằng những container độc lập và combiner. Ngược lại, nếu tự khai báo `CONCURRENT` cho collector mà accumulator không an toàn khi cập nhật cùng container, kết quả có thể bị hỏng.

`UNORDERED` và encounter order của Stream là hai khái niệm cần xem cùng nhau. Không nên khai báo `UNORDERED` cho collector nếu nghiệp vụ yêu cầu thứ tự đầu ra phải bám theo thứ tự nguồn.

## 8. Ví dụ collector tùy chỉnh: bộ chứa mutable, kết quả bất biến

Giả sử cần thống kê số đơn và tổng tiền; ta muốn **tích lũy hiệu quả** vào một đối tượng tạm có thể sửa, rồi trả một báo cáo cuối **bất biến**. Đây là ví dụ trực quan nhất cho việc **mutable reduction không bắt buộc sinh ra kết quả cuối mutable**.

Ví dụ hoàn chỉnh cho **Java 17+**:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class CustomStatsCollectorDemo {
    record Order(String id, long amountVnd, boolean paid) {}
    record Stats(long count, long totalVnd) {}

    static final class StatsAccumulator {
        private long count;
        private long totalVnd;

        void add(Order order) {
            count++;
            totalVnd += order.amountVnd();
        }

        StatsAccumulator merge(StatsAccumulator other) {
            count += other.count;
            totalVnd += other.totalVnd;
            return this;
        }

        Stats finish() {
            return new Stats(count, totalVnd);
        }
    }

    static Collector<Order, StatsAccumulator, Stats> statsCollector() {
        return Collector.of(
            StatsAccumulator::new,   // supplier
            StatsAccumulator::add,   // accumulator
            StatsAccumulator::merge, // combiner
            StatsAccumulator::finish // finisher
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", 120_000L, true),
            new Order("DH02",  80_000L, false),
            new Order("DH03", 150_000L, true)
        );

        Stats result = orders.parallelStream()
            .filter(Order::paid)
            .collect(statsCollector());

        System.out.println(result.count());    // 2
        System.out.println(result.totalVnd()); // 270000
    }
}
~~~

Ở ví dụ này:

- `Order` là phần tử nguồn `T`.
- `StatsAccumulator` là bộ chứa trung gian `A`: hai trường `count` và `totalVnd` được thay đổi qua `add`/`merge`.
- `Stats` là kết quả `R` dưới dạng record, có các trường nguyên thủy và **không có setter**.
- `finish()` tạo một giá trị kết quả mới từ trạng thái tích lũy.
- `Collector.of(...)` **không** khai báo `CONCURRENT` hoặc `UNORDERED`. Các container tích lũy được xử lý theo hợp đồng collector thông thường; nó có thể được dùng trong parallel Stream nhờ cơ chế chia và gộp.

Không có đối tượng mutable dùng chung được đưa từ bên ngoài vào pipeline. `StatsAccumulator` chỉ được tạo qua `supplier` và được hợp nhất qua `combiner`. Cách thiết kế này phù hợp với yêu cầu thực thi song song **theo hợp đồng**, miễn là accumulator, combiner và finisher tiếp tục tuân thủ luật tương ứng.

> **Giới hạn số học:** Tổng tiền `long` có thể tràn nếu dữ liệu cực lớn. Ví dụ dùng số nhỏ để tập trung vào cơ chế collector; ứng dụng thật cần quy tắc về đơn vị tiền, tràn số và độ chính xác, có thể dùng `BigDecimal` hoặc biểu diễn khác phù hợp.

## 9. So sánh với reduce trả kết quả bất biến

Nếu kết quả tổng hợp rất nhỏ, ta **có thể** dùng một giá trị bất biến mới ở mỗi bước:

~~~java
import java.util.List;

record Stats(long count, long totalVnd) {}
record Order(String id, long amountVnd, boolean paid) {}

List<Order> orders = List.of(
    new Order("DH01", 100L, true),
    new Order("DH02", 200L, false),
    new Order("DH03", 300L, true)
);

Stats stats = orders.stream()
    .filter(Order::paid)
    .reduce(
        new Stats(0, 0),
        (current, order) -> new Stats(
            current.count() + 1,
            current.totalVnd() + order.amountVnd()
        ),
        (left, right) -> new Stats(
            left.count() + right.count(),
            left.totalVnd() + right.totalVnd()
        )
    );

System.out.println(stats); // Stats[count=2, totalVnd=400]
~~~

Bài minh họa sử dụng record `Stats` và `Order`, nên cần Java 16+. Với `reduce` này:

- `Stats` ở mỗi bước là một **đối tượng mới**, không có trường mutable để sửa.
- Identity `new Stats(0, 0)` không bị thay đổi khi tích lũy.
- Accumulator và combiner tạo `Stats` mới bằng cách cộng các thành phần.
- Phép gộp tuân thủ luật identity và associativity trong giới hạn số học nguyên.

Cách này rõ về mặt hàm, nhưng **có thể tạo nhiều đối tượng trung gian** nếu xử lý dữ liệu rất lớn. Collector trong mục 8 cập nhật một đối tượng mutable cho từng nhánh, có thể tiết kiệm cấp phát. Đánh giá hiệu năng thực tế cần dựa vào benchmark và khối lượng dữ liệu, không chỉ vào việc code dùng `reduce` hay `collect`.

### Ranh giới khái niệm

Một phép `reduce` **có thể trả một đối tượng** phức tạp; yêu cầu cốt lõi là accumulator không sửa trạng thái kết quả cũ. Một phép `collect` **có thể trả một giá trị bất biến** thông qua finisher. Vì vậy, hãy phân loại theo **cơ chế tích lũy**, không chỉ theo kiểu của kết quả cuối cùng.

## 10. Các collector chuẩn thường gặp

Java cung cấp `java.util.stream.Collectors` để giảm nhu cầu tự viết collector cho các trường hợp phổ biến.

| Mục tiêu | Collector | Kết quả minh họa |
|---|---|---|
| Thu các phần tử vào `List` | `Collectors.toList()` | Danh sách |
| Thu vào `Set` | `Collectors.toSet()` | Tập giá trị không trùng |
| Chỉ định loại collection | `Collectors.toCollection(ArrayList::new)` | `ArrayList` mutable |
| Nối chuỗi | `Collectors.joining(", ")` | Một `String` |
| Gom theo khóa | `Collectors.groupingBy(Order::category)` | `Map<key, List<Order>>` |
| Phân hoạch theo điều kiện | `Collectors.partitioningBy(Order::paid)` | `Map<Boolean, List<Order>>` |
| Đếm phần tử | `Collectors.counting()` | `Long` |
| Tổng hợp số | `Collectors.summingLong(Order::amountVnd)` | `Long` |
| Tính nhiều thống kê | `Collectors.summarizingLong(Order::amountVnd)` | `LongSummaryStatistics` |
| Thu danh sách không cho phép sửa (Java 10+) | `Collectors.toUnmodifiableList()` | `List` không thể sửa |

Các ví dụ với `Order::category` đòi hỏi `Order` có trường `category`; ở đây chúng là **mẫu lựa chọn API**, còn các ví dụ đầy đủ trong bài dùng `Order` theo mô hình riêng đã khai báo.

### 10.1. Nối chuỗi: cùng kết quả, cơ chế khác

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> tags = List.of("java", "stream", "collector");

String byReduce = tags.stream()
    .reduce("", (left, right) ->
        left.isEmpty() ? right : left + ", " + right
    );

String byCollect = tags.stream()
    .collect(Collectors.joining(", "));

System.out.println(byReduce);  // java, stream, collector
System.out.println(byCollect); // java, stream, collector
~~~

Cả hai đều có thể tạo cùng chuỗi trên pipeline tuần tự này. Tuy nhiên, accumulator trong `byReduce` đặc biệt ở chỗ **không tương thích với việc kết hợp tùy ý nếu quy tắc định dạng/identity không được thiết kế thận trọng**; ví dụ cho thấy tính thuận tiện nhưng không phải công thức khuyến nghị cho mọi môi trường song song.

`Collectors.joining(", ")` thể hiện trực tiếp mục tiêu và thường xử lý các lần nối hiệu quả hơn qua bộ chứa dạng builder. Khi yêu cầu chuỗi có delimiter, prefix hoặc suffix, ưu tiên `joining`. Nếu muốn biết thuật toán `reduce` hợp lệ khi chạy song song, hãy xác minh rõ identity, associativity và quy tắc ghép từng nhánh.

### 10.2. Danh sách không thể sửa và mutable reduction

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> ids = List.of("A", "B", "C");

List<String> immutableResult = ids.stream()
    .collect(Collectors.toUnmodifiableList());

// immutableResult.add("D"); // Ném UnsupportedOperationException.
~~~

`toUnmodifiableList()` có từ Java 10 và **không chấp nhận phần tử `null`**. Dù kết quả không thể sửa, collector vẫn có thể sử dụng bộ chứa mutable ở giai đoạn trung gian. Tính bất biến **của kết quả** không đồng nghĩa với việc pipeline đã dùng `reduce`.

`Stream.toList()` (Java 16+) cũng trả List không thể sửa, nhưng có chính sách về null khác với `Collectors.toUnmodifiableList()`; phải chọn theo hợp đồng API mà ứng dụng cần.

### 10.3. Grouping và tổng hợp theo nhóm

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String category, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("Sách", 100L),
    new Sale("Bút",   30L),
    new Sale("Sách",  50L)
);

Map<String, Long> revenueByCategory = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::category,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(revenueByCategory.get("Sách")); // 150
System.out.println(revenueByCategory.get("Bút"));  // 30
~~~

`groupingBy` đóng vai trò collector ngoài, còn `summingLong` là collector cuối cho mỗi nhóm. Nó minh họa khả năng **kết hợp collector**: tính nhóm và tổng hợp theo khóa trong một terminal operation. Không suy ra thứ tự duyệt các khóa của `Map` được trả về từ `groupingBy` nếu không chỉ định kiểu Map phù hợp.

## 11. Parallel Stream: tính đúng trước hiệu năng

Rút gọn được thiết kế để kết hợp kết quả của nhiều nhánh, nhưng chỉ đúng khi các hàm tuân thủ hợp đồng.

~~~mermaid
flowchart TD
    S["Nguồn: 1,2,3,4"] --> A["Nhánh A: 1,2"]
    S --> B["Nhánh B: 3,4"]
    A --> RA["reduce -> 3"]
    B --> RB["reduce -> 7"]
    RA --> RC["combiner: 3 + 7 = 10"]
    RB --> RC
    RC --> OUT["Kết quả: 10"]
~~~

Với mutable reduction, mỗi nhánh có thể có một **bộ chứa riêng**:

~~~text
Nhánh A: supplier() -> [] -> add(1), add(2) -> [1, 2]
Nhánh B: supplier() -> [] -> add(3), add(4) -> [3, 4]
Combiner: [1, 2] + [3, 4] -> [1, 2, 3, 4]
~~~

Hai chiến lược không mâu thuẫn nhau: `reduce` kết hợp các **giá trị**, còn `collect` kết hợp các **bộ chứa**.

### 11.1. Vì sao cùng một ArrayList không an toàn khi forEach?

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> output = new ArrayList<>();

// Nguy hiểm: nhiều thread có thể add vào cùng ArrayList.
List.of(1, 2, 3, 4).parallelStream()
    .forEach(output::add);
~~~

`ArrayList` không thread-safe; cập nhật đồng thời có thể làm mất phần tử, hỏng trạng thái hoặc cho kết quả khó đoán. Việc dùng một `synchronizedList` chỉ để sửa lỗi này cũng chưa chắc đáp ứng yêu cầu thứ tự và hiệu năng.

**Thay bằng collector**:

~~~java
List<Integer> output = List.of(1, 2, 3, 4)
    .parallelStream()
    .collect(java.util.stream.Collectors.toList());
~~~

`collect` tổ chức việc tạo, tích lũy và kết hợp kết quả theo hợp đồng. Cần nhớ rằng **thứ tự** được xử lý theo encounter order và đặc tính collector, không phải theo thứ tự thread hoàn thành.

### 11.2. Collector.CONCURRENT khác với Stream.parallel()

- `parallel()` hoặc `parallelStream()` nói về **cách pipeline có thể thực thi**.
- `Collector.Characteristics.CONCURRENT` nói về việc **accumulator của collector cho phép nhiều thread cập nhật cùng một container**.

Một collector có thể hỗ trợ xử lý song song **mà không khai báo `CONCURRENT`**, vì hệ thống dùng nhiều container độc lập. Khi tự xây collector đồng thời, phải thiết kế cả container lẫn accumulator phù hợp và xem xét `UNORDERED`/encounter order.

Không nên tự khai báo `CONCURRENT` hoặc `UNORDERED` chỉ để hy vọng tăng tốc khi chưa thỏa các tính chất tương ứng.

### 11.3. Chi phí phân chia và hợp nhất

Song song có thể hiệu quả khi dữ liệu đủ lớn, nguồn dễ chia (`Spliterator` có đặc tính phù hợp), và accumulator/combiner làm việc đủ nặng để bù chi phí điều phối. Với pipeline rất nhỏ, việc tạo nhánh và hợp nhất container có thể **tốn hơn chạy tuần tự**.

Cần đo trên dữ liệu thực tế: thời gian, cấp phát, số phần tử, khả năng tranh chấp và yêu cầu giữ thứ tự đều ảnh hưởng kết quả. Không có quy tắc rằng `collect` hoặc `reduce` luôn nhanh hơn nhau.

## 12. Các hợp đồng bổ sung: nguồn, lazy, trạng thái và null

### 12.1. Không sửa nguồn dữ liệu đang duyệt

`filter`, `map` và các hàm trong pipeline nên **non-interfering**, tức không tự sửa nguồn dữ liệu trong lúc duyệt. Chẳng hạn, trong pipeline đọc `List<Order>`, đừng thêm/bớt đơn hàng ngay bên trong accumulator hoặc lambda.

Với `collect`, **cập nhật container đích được tạo theo supplier** là hành vi dự kiến; nó khác với việc sửa nguồn hoặc thay đổi một đối tượng dùng chung không thuộc container đó.

### 12.2. Lazy và vòng đời một lần dùng

`reduce` và `collect` đều là terminal operation, nên kích hoạt các phép trung gian lazy. Sau khi đã gọi một terminal operation, không được dùng lại chính Stream cũ:

~~~java
var stream = List.of(1, 2, 3).stream();

int sum = stream.reduce(0, Integer::sum);

// stream.collect(Collectors.toList()); // Không hợp lệ: đã tiêu thụ.
List<Integer> copy = List.of(1, 2, 3).stream()
    .collect(java.util.stream.Collectors.toList());
~~~

Nếu nguồn là file I/O như `Files.lines(...)`, phải đóng Stream bằng `try-with-resources`. Kết quả của `collect` không thay thế trách nhiệm quản lý tài nguyên nguồn.

### 12.3. Null và quy tắc kết quả rỗng

`Collectors.toUnmodifiableList()` và `Stream.toList()` có chính sách về null khác nhau; đừng giả định mọi collector chấp nhận null. Với `Collectors.toMap`, khóa trùng có thể gây `IllegalStateException` nếu không cung cấp hàm xử lý trùng, và chính sách null cần được kiểm tra theo collector cụ thể.

Đối với nguồn rỗng:

~~~java
int zero = List.<Integer>of().stream()
    .reduce(0, Integer::sum);

List<Integer> emptyList = List.<Integer>of().stream()
    .collect(java.util.stream.Collectors.toList());

System.out.println(zero);              // 0
System.out.println(emptyList.isEmpty()); // true
~~~

`reduce(identity, ...)` trả identity; collector thường trả kết quả rỗng được tạo từ supplier và finisher. Nếu không có identity, `reduce(accumulator)` trả `Optional.empty()`. Những khác biệt này quan trọng khi phân biệt “giá trị bằng 0” với “không có bản ghi”.

## 13. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao sai hoặc gây rủi ro | Cách sửa |
|---|---|---|
| `reduce(new ArrayList<>(), ... add ...)` | Mutate identity, vi phạm ý tưởng giảm không đột biến; dễ sai khi song song | `collect(Collectors.toList())` hoặc `collect(ArrayList::new, List::add, List::addAll)` |
| `parallelStream().forEach(sharedList::add)` | Ghi vào trạng thái chia sẻ không an toàn | Thu bằng collector đúng hợp đồng |
| Supplier trả lại cùng một List có sẵn | Các nhánh không có container độc lập | Supplier phải tạo **container mới** khi được gọi |
| Combiner bỏ qua dữ liệu nhánh phải | Kết quả song song mất dữ liệu | Kết hợp đủ hai container và trả về container hợp lệ |
| `reduce(10, Integer::sum)` để tính tổng | Identity sai với phép cộng | Dùng 0 |
| `reduce(0, Integer::min)` để tìm min trên số dương | 0 chen vào và làm sai min | Dùng `min` hoặc `reduce(Integer::min)` |
| Accumulator của `reduce` dùng phép trừ | Không associative | Thiết kế phép kết hợp associative |
| Tự khai báo collector `CONCURRENT` trên ArrayList | Container không an toàn cho cập nhật đồng thời | Bỏ đặc tính hoặc dùng container/accumulator đồng thời đúng hợp đồng |
| Giả định `Collectors.toList()` luôn là `ArrayList` mutable | API không cam kết kiểu/mutability cụ thể | Dùng `toCollection(ArrayList::new)` khi cần |
| Dùng `toArray` hoặc `collect(toList)` trên nguồn vô hạn | Không thể hoàn thành hoặc tiêu hao tài nguyên | Đặt giới hạn hợp lý trước terminal operation |
| Gọi lại Stream sau `collect` | Stream đã tiêu thụ | Tạo Stream mới từ nguồn có thể dùng lại |

## 14. Bài tập thực hành: rút gọn và thu thập đơn hàng

Cho danh sách các khoản thanh toán, yêu cầu:

1. Tính tổng các khoản có trạng thái `successful = true` theo `reduce`.
2. Thu mã của các khoản thành công thành `List<String>` bằng `collect`.
3. Tạo bản đồ **số khoản thành công theo khách hàng** bằng collector tiêu chuẩn.
4. Viết cách thu mã bằng overload ba tham số của `collect`.
5. Giải thích điều gì xảy ra khi danh sách rỗng.

**Lời giải tham khảo (Java 17+):**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ReductionPractice {
    record Payment(String id, String customer, long amount, boolean successful) {}

    public static void main(String[] args) {
        List<Payment> payments = List.of(
            new Payment("P01", "An",   120L, true),
            new Payment("P02", "Bình", 200L, false),
            new Payment("P03", "An",    80L, true),
            new Payment("P04", "Chi",   50L, true)
        );

        long total = payments.stream()
            .filter(Payment::successful)
            .map(Payment::amount)
            .reduce(0L, Long::sum);

        List<String> ids = payments.stream()
            .filter(Payment::successful)
            .map(Payment::id)
            .collect(Collectors.toList());

        Map<String, Long> countByCustomer = payments.stream()
            .filter(Payment::successful)
            .collect(Collectors.groupingBy(
                Payment::customer,
                Collectors.counting()
            ));

        ArrayList<String> idsWithThreeArgs = payments.stream()
            .filter(Payment::successful)
            .map(Payment::id)
            .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
            );

        System.out.println(total);                    // 250
        System.out.println(ids);                      // [P01, P03, P04]
        System.out.println(countByCustomer.get("An")); // 2
        System.out.println(ids.equals(idsWithThreeArgs)); // true
    }
}
~~~

**Khi đầu vào rỗng:** `reduce(0L, Long::sum)` trả `0L`; `collect(toList())` trả danh sách rỗng; `groupingBy` trả Map rỗng; `collect(ArrayList::new, ...)` trả ArrayList rỗng. Kết quả rỗng là **quy tắc hợp lệ của các API**, nhưng hệ thống nghiệp vụ vẫn cần tự quyết định có xem “không có thanh toán” là giá trị 0 hay trạng thái phải được báo riêng hay không.

**Câu hỏi tự kiểm tra:**

1. Vì sao cộng số bằng `reduce` được xem là non-mutating reduction? — Accumulator tạo **giá trị số mới**, không sửa container tích lũy.
2. Vì sao `collect` cho phép `ArrayList::add` dù đang dùng parallel Stream? — Cơ chế collector thông thường sử dụng **các container độc lập** rồi hợp nhất; không tự dùng một danh sách ngoài chia sẻ.
3. `Supplier` có thể trả lại một `ArrayList` dùng chung trong mọi lần gọi không? — **Không nên**, vì phá hợp đồng độc lập của container.
4. Nếu Collector có finisher trả `List.copyOf(container)` thì nó còn là mutable reduction không? — **Có**, vì trạng thái trung gian vẫn được cập nhật mutable.
5. Hai overload `reduce` khác gì trên Stream rỗng? — Có identity trả identity; không có identity trả `Optional.empty()`.
6. `CONCURRENT` có đồng nghĩa với `parallelStream()` không? — **Không**; một bên là đặc tính collector, một bên là chế độ thực thi pipeline.
7. Nếu source vô hạn, `collect(toList())` có tự dừng không? — **Không**, trừ khi có bước hoặc điều kiện dừng thích hợp trước đó.

## 15. Ghi nhớ để lựa chọn đúng công cụ

**Dùng `reduce`** khi kết quả có thể được xây dựng bằng cách kết hợp **giá trị** theo một phép toán có identity và associativity phù hợp, chẳng hạn tổng, tích hoặc một record bất biến. **Dùng `collect`** khi cần xây **bộ chứa** như `List`, `Map`, `Set` hoặc đối tượng thống kê có trạng thái tích lũy, sau đó có thể dùng finisher tạo kết quả cuối theo hợp đồng.

Cả hai đều là terminal operation và đều có thể tham gia vào pipeline khai báo, lazy trước khi kết thúc. Khi dữ liệu lớn hoặc xử lý song song, điều quan trọng là tuân thủ hợp đồng về **trạng thái**, **tính kết hợp**, **bộ chứa độc lập**, **thứ tự**, **tài nguyên** và **chi phí gộp kết quả**.

Nắm được ranh giới giữa **non-mutating reduction** và **mutable reduction** giúp bạn chọn đúng API, viết collector tùy chỉnh an toàn và hiểu cách Java Stream API mở rộng sang grouping, xử lý đồng thời, `Spliterator` và Stream Gatherers.
