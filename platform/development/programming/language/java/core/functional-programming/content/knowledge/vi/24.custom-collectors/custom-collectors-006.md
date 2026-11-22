# `Collector.of()` và xây dựng collector đơn giản trong Java

## 1. Khi nào cần viết một collector tùy chỉnh?

Các terminal operation của Stream như `toList()`, `count()`, `reduce(...)` và `collect(...)` giúp biến một chuỗi phần tử thành kết quả cần dùng. Với `collect(...)`, Java đã có nhiều collector dựng sẵn:

```java
List<String> names = values.stream().collect(Collectors.toList());
Set<String> unique = values.stream().collect(Collectors.toSet());
Map<String, Long> counts = values.stream().collect(
        Collectors.groupingBy(String::toLowerCase, Collectors.counting()));
```

Đoạn trên là minh họa khi `values` là `List<String>` và đã import các kiểu cần thiết. Phần lớn nhu cầu phổ biến nên dùng collector chuẩn. Nhưng nếu cần một **kiểu kết quả riêng**, ví dụ gom thông tin đơn hàng thành một bản thống kê bất biến gồm số dòng, tổng số lượng, doanh thu, hoặc xây chuỗi định dạng đặc biệt, `Collector.of(...)` cho phép chỉ ra cách tích lũy.

Học xong bài này, bạn sẽ:

- Hiểu các kiểu `T`, `A`, `R` trong `Collector<T,A,R>`.
- Phân biệt bốn thành phần `supplier`, `accumulator`, `combiner`, `finisher` và cách chúng phối hợp.
- Dùng hai dạng `Collector.of(...)`: không có finisher tường minh và có finisher.
- Xây dựng một collector đơn giản từ `StringJoiner`, rồi một collector tổng hợp dữ liệu thành record bất biến trong Java 17.
- Viết combiner đúng để hoạt động cả với Stream tuần tự lẫn song song.
- Hiểu đặc tính `IDENTITY_FINISH`, `UNORDERED`, `CONCURRENT`, không khai báo sai.
- Kiểm thử kết quả của Stream rỗng, một phần tử, nhiều phần tử, nguồn song song và nhóm theo khóa.

## 2. `collect` khác `Collector` ở chỗ nào?

`stream.collect(collector)` là **terminal operation**. Nó thực thi pipeline và sử dụng một collector để tạo kết quả.

`Collector` là **mô tả quy trình tích lũy**, không phải danh sách đã chứa sẵn dữ liệu và cũng không phải nơi mà chương trình nên tự giữ trạng thái qua nhiều lượt chạy. Một `Collector` có thể được dùng lại qua các lời gọi `collect` khác nhau nếu các hàm của nó được thiết kế đúng (đặc biệt supplier tạo container mới). Cùng một Stream đã tiêu thụ thì không dùng lại.

Ví dụ khái niệm:

```text
Stream<T> có các phần tử t1, t2, t3, ...
       │
       ▼
collector.supplier()       → container A mới
       │
       ▼
collector.accumulator()    → đưa từng T vào A
       │
       ├── xử lý song song có thể tạo nhiều A
       │                         │
       │                         ▼
       └──── collector.combiner() gộp hai A thành A
                                 │
                                 ▼
                      collector.finisher()
                                 │
                                 ▼
                           kết quả R
```

Đây là sơ đồ diễn giải hợp đồng API, **không** cam kết Java phải gọi các hàm đúng thứ tự/số lần như trên cho mọi Stream. Collector có finisher đồng nhất có thể bỏ qua bước chuyển đổi cuối; Stream song song có thể tạo và gộp nhiều container; các đặc tính của collector tác động đến cách thực thi.

## 3. Ba kiểu dữ liệu `T`, `A`, `R`

Khai báo:

```java
public interface Collector<T, A, R> {
    // supplier, accumulator, combiner, finisher, characteristics...
}
```

| Tham số | Vai trò | Ví dụ thống kê |
| --- | --- | --- |
| `T` | Kiểu **phần tử đầu vào** của Stream | `Order` |
| `A` | Kiểu **container tích lũy trung gian** | `MutableStats` |
| `R` | Kiểu **kết quả hoàn chỉnh** trả từ `collect` | `Report` |

`T`, `A`, `R` **không bắt buộc giống nhau**.

Ví dụ, `Stream<Order>` được thu thập thành `Report` bằng một đối tượng trung gian `MutableStats`:

```text
T = Order
A = MutableStats
R = Report
```

Cũng có trường hợp `A = R`, chẳng hạn gom một Stream các chuỗi thành một `List<String>`; vì container trung gian đã chính là kết quả, finisher có thể là hàm đồng nhất.

Sự phân biệt rất quan trọng: **accumulator của collector không trả về container mới**, nó thường **thay đổi container `A` được cung cấp**. Trong khi đó, combiner phải **trả về một container `A`** đại diện cho kết quả gộp.

## 4. Bốn thành phần cốt lõi của `Collector.of(...)`

Dạng đầy đủ:

```java
Collector.of(
        supplier,
        accumulator,
        combiner,
        finisher,
        characteristics...);
```

### 4.1. `supplier: Supplier<A>`

`supplier.get()` phải tạo một **container kết quả rỗng mới** cho một lượt tích lũy:

```java
ArrayList<String>::new
```

hoặc:

```java
() -> new MutableStats()
```

Tại sao “mới” quan trọng? Khi Stream song song, nhiều nhánh có thể tích lũy vào những container khác nhau. Trả về **cùng một đối tượng dùng chung** từ supplier tạo ra trạng thái bị ghi chồng, lỗi đếm trùng và race condition. Ngay cả Stream tuần tự, collector dùng lại cũng không nên mang dữ liệu từ lượt trước sang lượt sau.

Supplier phải có khả năng tạo container trung hòa: chưa đưa phần tử nào vào thì kết quả, sau finisher, phải là **kết quả đúng của Stream rỗng**.

### 4.2. `accumulator: BiConsumer<A,T>`

Hàm này nhận một container `A` và một phần tử `T`, sau đó **đưa đóng góp của phần tử vào container**:

```java
(list, word) -> list.add(word)
```

Vì `BiConsumer` trả về `void`, không dùng `return list` như ở `BinaryOperator`. Trong collector mutable, accumulator thường thay đổi `A` tại chỗ. Với dữ liệu thống kê:

```java
(stats, order) -> stats.add(order)
```

Accumulator cần tuân thủ hợp đồng non-interference: không tự thêm/xóa phần tử của nguồn Stream đang duyệt. Tránh side effect không liên quan hoặc cập nhật một biến dùng chung bên ngoài container.

### 4.3. `combiner: BinaryOperator<A>`

Khi có hai kết quả trung gian, combiner phải gộp chúng thành một kết quả phù hợp:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Combiner **trả lại `A`**, không phải `void`. Có thể sửa container bên trái rồi trả nó về, miễn không giữ tham chiếu cần sử dụng lại đến container bên phải và việc gộp bảo toàn đúng kết quả.

Với thống kê, combiner cộng số dòng, số lượng và doanh thu từ container `right` vào `left`. Nếu nó quên một trường, phép collect tuần tự có thể vẫn cho kết quả đúng, trong khi phép thu thập song song **sai** vì giá trị một nhánh bị bỏ.

Cách gộp phải có tính kết hợp theo ngữ nghĩa kết quả; nếu kết quả cần giữ thứ tự phần tử, không được tùy ý đảo `left` và `right`. Không nên giả định combiner chỉ được gọi một lần.

### 4.4. `finisher: Function<A,R>`

Finisher biến container tích lũy thành **kết quả cuối**. Ví dụ:

```java
stats -> new Report(stats.rows, stats.units, stats.revenue)
```

Khi `A` là một object mutable phục vụ quá trình cộng dồn, nhưng API muốn trả về một `record` bất biến, đây là bước quan trọng để **không làm lộ trạng thái mutable nội bộ**.

Nếu `A` và `R` là cùng kiểu và kết quả chính là container, có thể dùng overload `Collector.of(supplier, accumulator, combiner, characteristics...)` không cần finisher. Dạng này có đặc tính `IDENTITY_FINISH`: container trung gian được dùng trực tiếp làm kết quả.

## 5. Hai overload `Collector.of` nên phân biệt

### Không truyền finisher — `A` cũng là `R`

```java
static <T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);
```

Ví dụ:

```java
Collector<String, List<String>, List<String>> copyCollector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

Ở đây:

- Supplier tạo `ArrayList<String>` rỗng.
- Accumulator thêm một `String` vào List.
- Combiner nối các List trung gian, trả List bên trái.
- Kết quả là chính List đã tích lũy, vì vậy không có hàm chuyển đổi cuối riêng.

Với `Collector.of` ba hàm như trên, collector có đặc tính `IDENTITY_FINISH` theo hợp đồng. Danh sách kết quả **có thể chỉnh sửa được** vì ta đã dùng `ArrayList`; ngược lại `Stream.toList()` từ Java 16 trả List không thể chỉnh sửa. Không dùng hai cách này như thể chúng có cùng hợp đồng về mutability.

### Truyền finisher — `A` có thể khác `R`

```java
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
```

Ví dụ dùng `StringJoiner` làm container nhưng trả ra `String`:

```java
Collector<String, StringJoiner, String> bracketed =
        Collector.of(
                () -> new StringJoiner(" | ", "[", "]"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);
```

`StringJoiner::merge` trả `StringJoiner`, đúng yêu cầu combiner. Kết quả:

```java
String text = Stream.of("red", "green", "blue")
        .collect(bracketed);
// "[red | green | blue]"
```

Với Stream rỗng, `StringJoiner` có prefix/suffix trên trả `"[]"`; với dữ liệu có thứ tự, kết quả được tạo theo thứ tự gặp phần tử. **Không** khai báo `UNORDERED` ở collector này vì thứ tự các từ ảnh hưởng kết quả.

## 6. Ví dụ Java 17 hoàn chỉnh: tự tạo collector thống kê

Giả sử mỗi phần tử đầu vào là một dòng hàng:

```text
Order(category, quantity, unitPrice)
```

Mỗi bản ghi `Order` là immutable record, biểu diễn danh mục, số lượng và giá một đơn vị. Ta cần thu về `Report`:

- `lines`: tổng số dòng hàng.
- `units`: tổng số đơn vị sản phẩm.
- `revenue`: tổng doanh thu, bằng tổng `quantity × unitPrice`.

Kiến trúc thu thập:

```text
Stream<Order>           [Order, Order, Order, ...]
     │
     ▼
Collector<Order, MutableStats, Report>
     │
     ├─ supplier:   MutableStats::new
     ├─ accumulator: MutableStats::accept
     ├─ combiner:   MutableStats::merge
     └─ finisher:   MutableStats::finish
     │
     ▼
Report(lines, units, revenue) — bất biến
```

Khác `reduce` trả object bất biến **mới ở mỗi bước**, custom collector có thể tích lũy vào trạng thái mutable nội bộ và chỉ tạo bản ghi bất biến ở cuối. Các container trung gian phải có vòng đời phù hợp và không được chia sẻ tự do giữa thread.

Tạo file **`CustomCollectorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CustomCollectorDemo {
    record Order(String category, int quantity, long unitPrice) {
        Order {
            Objects.requireNonNull(category, "category");
            if (quantity < 0 || unitPrice < 0) {
                throw new IllegalArgumentException(
                        "quantity and price must be nonnegative");
            }
        }
    }

    record Report(long lines, long units, long revenue) {}

    static final class MutableStats {
        private long lines;
        private long units;
        private long revenue;

        void accept(Order order) {
            lines = Math.addExact(lines, 1L);
            units = Math.addExact(units, order.quantity());
            long amount = Math.multiplyExact(
                    (long) order.quantity(), order.unitPrice());
            revenue = Math.addExact(revenue, amount);
        }

        MutableStats merge(MutableStats other) {
            lines = Math.addExact(lines, other.lines);
            units = Math.addExact(units, other.units);
            revenue = Math.addExact(revenue, other.revenue);
            return this;
        }

        Report finish() {
            return new Report(lines, units, revenue);
        }
    }

    static Collector<Order, MutableStats, Report> reportCollector() {
        return Collector.of(
                MutableStats::new,
                MutableStats::accept,
                MutableStats::merge,
                MutableStats::finish,
                Collector.Characteristics.UNORDERED);
    }

    static Collector<String, List<String>, List<String>>
            listCollector() {
        return Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
    }

    static Collector<String, StringJoiner, String>
            bracketCollector() {
        return Collector.of(
                () -> new StringJoiner(" | ", "[", "]"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);
    }

    static List<Order> sample() {
        return List.of(
                new Order("Books", 2, 100),
                new Order("Food", 3, 40),
                new Order("Books", 1, 150),
                new Order("Tech", 1, 250),
                new Order("Food", 2, 30));
    }

    static Map<String, Report> byCategory(List<Order> orders) {
        return orders.stream().collect(
                Collectors.groupingBy(
                        Order::category,
                        TreeMap::new,
                        reportCollector()));
    }

    static void expect(Object wanted, Object actual, String name) {
        if (!Objects.equals(wanted, actual)) {
            throw new AssertionError(
                    name + ": expected=" + wanted
                            + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Order> orders = sample();
        Report all = new Report(5, 9, 780);

        expect(all, orders.stream().collect(reportCollector()),
                "sequential report");
        expect(all, orders.parallelStream().collect(reportCollector()),
                "parallel report");
        expect(new Report(0, 0, 0),
                Stream.<Order>empty().collect(reportCollector()),
                "empty report");
        expect(new Report(1, 2, 200),
                orders.stream().limit(1).collect(reportCollector()),
                "single item");

        expect(Map.of(
                "Books", new Report(2, 3, 350),
                "Food", new Report(2, 5, 180),
                "Tech", new Report(1, 1, 250)),
                byCategory(orders), "downstream grouping");

        expect(List.of("red", "green", "blue"),
                Stream.of("red", "green", "blue")
                        .collect(listCollector()),
                "list collector");

        expect("[red | green | blue]",
                Stream.of("red", "green", "blue")
                        .collect(bracketCollector()),
                "joining");
        expect("[]", Stream.<String>empty()
                .collect(bracketCollector()), "empty joining");

        expect(true, listCollector().characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH),
                "identity finisher on list collector");
        expect(false, reportCollector().characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH),
                "report has real finisher");
        expect(true, reportCollector().characteristics().contains(
                Collector.Characteristics.UNORDERED),
                "report does not depend on order");
        expect(false, reportCollector().characteristics().contains(
                Collector.Characteristics.CONCURRENT),
                "mutable stats are not shared concurrently");

        expect(5, orders.size(), "source unchanged");
    }

    public static void main(String[] args) {
        runTests();

        List<Order> orders = sample();
        Report sequential = orders.stream().collect(reportCollector());
        Report parallel = orders.parallelStream()
                .collect(reportCollector());

        System.out.println("report=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + Stream.<Order>empty()
                .collect(reportCollector()));
        System.out.println("grouped=" + byCategory(orders));
        System.out.println("joined=" + Stream.of("red", "green", "blue")
                .collect(bracketCollector()));
        System.out.println("copy=" + Stream.of("red", "green", "blue")
                .collect(listCollector()));
        System.out.println("identityFinish="
                + listCollector().characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("summaryIdentityFinish="
                + reportCollector().characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("summaryUnordered="
                + reportCollector().characteristics().contains(
                        Collector.Characteristics.UNORDERED));
        System.out.println("summaryConcurrent="
                + reportCollector().characteristics().contains(
                        Collector.Characteristics.CONCURRENT));
        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac CustomCollectorDemo.java
java CustomCollectorDemo
```

Stdout dự kiến:

```text
report=Report[lines=5, units=9, revenue=780]
parallel=Report[lines=5, units=9, revenue=780]
empty=Report[lines=0, units=0, revenue=0]
grouped={Books=Report[lines=2, units=3, revenue=350], Food=Report[lines=2, units=5, revenue=180], Tech=Report[lines=1, units=1, revenue=250]}
joined=[red | green | blue]
copy=[red, green, blue]
identityFinish=true
summaryIdentityFinish=false
summaryUnordered=true
summaryConcurrent=false
tests=PASS
```

### Phân tích kết quả

Năm dòng dữ liệu có doanh thu:

| Category | Quantity | Unit price | Revenue |
| --- | ---: | ---: | ---: |
| Books | 2 | 100 | 200 |
| Food | 3 | 40 | 120 |
| Books | 1 | 150 | 150 |
| Tech | 1 | 250 | 250 |
| Food | 2 | 30 | 60 |
| **Tổng** | **9** | | **780** |

Vậy `Report[lines=5, units=9, revenue=780]` là kết quả đúng. Khi nhóm theo danh mục, Books có hai dòng và doanh thu 350, Food có hai dòng và doanh thu 180, Tech có một dòng và doanh thu 250.

`TreeMap::new` trong `groupingBy` giúp các khóa `Books`, `Food`, `Tech` được duyệt theo thứ tự chữ cái, do vậy phần hiển thị `grouped=...` ổn định. Không giả định `groupingBy` mặc định có thứ tự khóa như vậy.

`runTests()` so sánh toàn bộ `Report`, kết quả từng danh mục, trường hợp rỗng, một dòng, output của hai collector khác, đặc tính khai báo và việc không sửa danh sách đầu vào. Phương thức `expect` ném `AssertionError` nếu có sai; không cần bật cờ JVM `-ea`.

### Vì sao record kết quả không bị sửa sau khi trả về?

`MutableStats` chỉ tồn tại trong quá trình `collect`; `MutableStats::finish` tạo `new Report(...)`. Vì `Report` là record chứa ba giá trị `long`, phía caller không thể thay đổi các field của kết quả sau khi hoàn thành. Bài toán thực tế có thể phức tạp hơn nếu record chứa `List`, `Map` hoặc đối tượng mutable; khi đó cần xem xét **defensive copy**, không nên kết luận mọi record đều bất biến sâu.

### Vì sao dùng `UNORDERED` lại hợp lệ ở đây?

Các chỉ số `lines`, `units`, `revenue` chỉ là phép cộng những đóng góp độc lập, kết quả không phụ thuộc thứ tự phần tử (trong phạm vi số học được chọn và không có lỗi overflow). Vì thế collector có thể khai báo `UNORDERED`.

Ngược lại, `bracketCollector()` nối các chuỗi theo thứ tự và **không khai báo `UNORDERED`**. Đánh dấu collector nối chuỗi là unordered trong khi vẫn mong `[red | green | blue]` theo thứ tự đầu vào sẽ mâu thuẫn với hợp đồng.

`UNORDERED` **không đồng nghĩa** `CONCURRENT`. `MutableStats` chỉ là object mutable thông thường; code **không** cho phép nhiều thread gọi `accept` đồng thời trên cùng một instance. Tuy vậy `parallelStream` vẫn có thể hoạt động đúng khi mỗi nhánh tích lũy trên container riêng, sau đó gọi combiner để gộp.

## 7. Hợp đồng của `supplier`, `accumulator` và `combiner`

Một collector phải có ngữ nghĩa nhất quán dù nguồn là rỗng, nhỏ, lớn, tuần tự hoặc song song. Có thể hình dung các quy tắc như sau.

### 7.1. Độc lập với cách phân đoạn dữ liệu

Giả sử nguồn gồm `[a,b,c,d]`, kết quả tổng hợp phải tương đương giữa:

```text
Cách 1:
  supplier → add a → add b → add c → add d → finish

Cách 2:
  supplier → add a → add b ┐
                            combiner → finish
  supplier → add c → add d ┘
```

Không nhất thiết hai container trung gian phải là cùng đối tượng. Điều cần giữ là **kết quả cuối tương đương** theo hợp đồng nghiệp vụ.

Với thống kê, combiner cộng từng chỉ số nên hai cách cho cùng ba tổng. Với List có thứ tự, combiner `left.addAll(right)` giữ thứ tự hai phân đoạn khi framework bảo toàn encounter order.

### 7.2. Identity của container trung gian

Một container mới từ supplier là trạng thái trung hòa. Nếu dùng `combiner(empty, accumulated)` hoặc `combiner(accumulated, empty)`, kết quả phải tương đương với `accumulated`.

`MutableStats` mới có ba trường bằng 0. Khi merge với kết quả đã có, cộng các số 0 không làm đổi giá trị. Một `ArrayList` mới rỗng cũng trung hòa với thao tác `addAll`.

Nếu supplier bắt đầu với một giá trị phụ, ví dụ `lines = 1`, thì xử lý song song có thể **đếm thừa theo số container trung gian**. Muốn cộng thêm một khoản phí cố định chỉ một lần, hãy thực hiện **sau** khi kết quả reduction hoàn thành, không đặt phí đó vào mỗi container supplier nếu nó không trung hòa.

### 7.3. Chỉ trả container hợp lệ từ combiner

Ví dụ đúng:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Ví dụ sai:

```java
// Sai: bỏ toàn bộ dữ liệu thuộc right.
(left, right) -> left
```

Với Stream tuần tự, một combiner sai có thể không bị gọi và test vẫn qua. Với Stream song song hoặc downstream collector phải gộp nhiều container, dữ liệu nhánh phải bị mất. Do đó **luôn kiểm thử combiner**, không chỉ kiểm thử trường hợp tuần tự.

### 7.4. Không làm lộ trạng thái còn đang tích lũy

Không giữ `MutableStats` vào một biến static dùng chung hoặc trả thẳng object mutable ra ngoài rồi tiếp tục sửa nó trong quá trình thu thập. Mỗi invocation của supplier cần container mới. Nếu finisher trả về cấu trúc mutable có tham chiếu đến vùng dữ liệu mà code khác cũng đang thay đổi, ứng dụng phải có hợp đồng sở hữu và sao chép rõ.

## 8. Đặc tính `Collector.Characteristics`

`Collector.of(...)` có thể nhận các đặc tính giúp mô tả các quyền tự do của framework khi thực thi:

| Đặc tính | Ý nghĩa | Khi khai báo |
| --- | --- | --- |
| `IDENTITY_FINISH` | Kết quả có thể dùng chính container `A`, không cần finisher chuyển đổi đáng kể | Khi `A` cũng là `R` và dùng finisher đồng nhất |
| `UNORDERED` | Kết quả không chịu ràng buộc bởi encounter order | Khi thứ tự phần tử không làm thay đổi ý nghĩa kết quả |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên **cùng một container** | Chỉ khi cấu trúc và thao tác tích lũy thực sự hỗ trợ truy cập đồng thời an toàn |

### `IDENTITY_FINISH`

Với overload chỉ gồm ba hàm `supplier`, `accumulator`, `combiner`, đặc tính `IDENTITY_FINISH` được thêm theo hợp đồng. Không tự đưa đặc tính này vào collector trả kiểu khác container:

```java
// Đúng: A=StringJoiner, R=String; finisher có chuyển kiểu.
Collector<String, StringJoiner, String> c =
        Collector.of(
                () -> new StringJoiner(","),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);
```

Collector trên **không** có `IDENTITY_FINISH` vì `StringJoiner` không thể thay thế cho `String`.

Nếu khai báo `IDENTITY_FINISH` sai với một finisher đổi kiểu, API có thể bỏ qua finisher; kết quả không còn có đúng kiểu mong đợi hoặc phát sinh lỗi runtime. Đừng dùng đặc tính như mẹo tối ưu tùy tiện.

### `UNORDERED`

Một phép tổng số lượng bằng cộng các số nguyên phù hợp có thể không phụ thuộc thứ tự, nhưng việc nối tên nhân viên thành chuỗi lại phụ thuộc thứ tự. Một collector chứa danh sách có thứ tự thường **không nên** khai báo `UNORDERED`.

Khi có `UNORDERED`, framework được phép bỏ yêu cầu duy trì encounter order của dữ liệu; đó là cam kết ngữ nghĩa của collector, không phải yêu cầu Stream phải chạy song song.

### `CONCURRENT`

`CONCURRENT` là cam kết rất mạnh. Ví dụ một `ArrayList` hay `MutableStats` có field `long` không thread-safe, do đó **không** được gắn `CONCURRENT` chỉ vì bạn muốn chạy nhanh trên `parallelStream()`.

Nếu dùng accumulator chung mà không đồng bộ, các cập nhật như `lines++` hoặc `revenue += amount` có thể mất dữ liệu. Muốn collector concurrent, cần thiết kế container, atomic operations hoặc cơ chế đồng bộ thực sự đúng, đồng thời xem xét yêu cầu thứ tự và đặc tính downstream.

Một collector **không có `CONCURRENT` vẫn có thể** xử lý parallel đúng qua supplier riêng và combiner. Một collector **có `CONCURRENT`** cũng không phải bảo đảm hiệu năng tốt hơn; còn phụ thuộc nguồn, số nhóm, contention và cách framework thực thi.

## 9. Dùng collector tự tạo làm downstream của `groupingBy`

Khả năng kết hợp là ưu điểm quan trọng của collector. Bạn có thể đưa `reportCollector()` vào sau `groupingBy`:

```java
Map<String, Report> byCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                TreeMap::new,
                reportCollector()));
```

Ở đây:

1. `groupingBy` xác định khóa từ `Order::category`.
2. `reportCollector()` xử lý **riêng những Order thuộc từng khóa**.
3. Mỗi khóa của Map có giá trị `Report`, không phải List.
4. `TreeMap` sắp xếp khóa khi xuất/duyệt, không thay đổi logic tính tổng của từng nhóm.

Không phải tạo `Map<String,List<Order>>` trước rồi lặp qua các List để tạo Report. Downstream có thể tính tổng trong quá trình thu thập. Với dữ liệu lớn, đây thường là cách có ý nghĩa hơn nếu chỉ cần các chỉ số, vì không giữ mọi Order trong kết quả nhóm.

Nếu nghiệp vụ còn yêu cầu lưu mọi Order bên cạnh thống kê, bạn phải chủ động chọn kiểu kết quả bao gồm chúng, hoặc kết hợp collector phù hợp. Không thay đổi yêu cầu chỉ để tránh viết thêm dữ liệu.

### Khóa `null` và dữ liệu không hợp lệ

`Collectors.groupingBy` không cho classifier trả về khóa `null`. `reportCollector()` **không thể** tự sửa lỗi này vì classifier ở lớp ngoài đã quyết định phân nhóm.

Nếu `Order.category()` có thể null, cần thiết kế chính sách rõ ràng: báo lỗi, chuẩn hóa thành khóa đặc biệt hoặc dùng kiểu khóa có trạng thái. Trong chương trình Java 17, constructor record `Order` đã gọi `Objects.requireNonNull` nên dữ liệu nguồn hợp lệ theo hợp đồng.

Các giá trị quantity, unitPrice cũng được validate không âm. Đây là lựa chọn của ví dụ; nếu nghiệp vụ dùng số lượng âm cho hoàn trả hoặc doanh thu âm cho điều chỉnh, hợp đồng cần thay đổi tương ứng.

## 10. `Collector.of` và `Stream.reduce`: khác nhau ở mutable reduction

Một bẫy phổ biến là dùng `Stream.reduce` như thể đó là `Collector.of`:

```java
// Không nên: mutation trên một identity ArrayList chia sẻ.
List<String> result = Stream.of("a", "b", "c")
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

Đây là ví dụ **thiết kế sai**, không phải collector khuyến nghị: reduction kiểu này dễ dùng chung object mutable identity giữa các nhánh, làm hỏng dữ liệu và vi phạm ý định của `reduce`. `reduce` phù hợp với phép kết hợp không gây side effect và các trạng thái giá trị theo hợp đồng của nó.

Với mutable accumulation, hãy dùng `collect`:

```java
List<String> good = Stream.of("a", "b", "c")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll);
```

Đây là overload **ba tham số của `Stream.collect`** nhận `supplier`, `BiConsumer` accumulator và `BiConsumer` combiner. Lưu ý nó khác với `Collector.of`: **combiner của `Stream.collect(supplier, accumulator, combiner)` trả `void`**, còn combiner của `Collector.of` phải trả `A`.

So sánh chữ ký:

```java
// Stream.collect dạng ba tham số:
<R> R collect(Supplier<R> supplier,
              BiConsumer<R, ? super T> accumulator,
              BiConsumer<R, R> combiner);

// Collector.of dạng tạo Collector:
<T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);
```

Vì thế `ArrayList::addAll` thích hợp cho combiner `BiConsumer` của `collect` (giá trị trả boolean bị bỏ trong ngữ cảnh void), nhưng không thể dùng trực tiếp làm `BinaryOperator<List<String>>` của `Collector.of`, vì BinaryOperator phải **trả về `List<String>`**. Trong `Collector.of` hãy viết lambda gọi `addAll` rồi `return left`.

## 11. Khi nào nên ưu tiên collector chuẩn thay vì `Collector.of`?

Đừng tạo collector tùy chỉnh chỉ vì muốn dùng API nâng cao. Nhiều bài toán có sẵn cách ngắn và dễ kiểm tra hơn:

| Nhu cầu | Collector/phép tính có sẵn | Ghi chú |
| --- | --- | --- |
| Thu thập List | `toList()` / `Collectors.toList()` | Phân biệt khả năng chỉnh sửa của kết quả |
| Tính tổng thuộc tính | `summingInt`, `summingLong`, `mapToLong(...).sum()` | Tránh viết state riêng chỉ cho một tổng |
| Đếm | `counting()` / `stream.count()` | Không cần container phức tạp |
| Min/max | `minBy`, `maxBy` | Dùng comparator rõ, kết quả `Optional` |
| Nhóm theo thuộc tính | `groupingBy` | Có thể kết hợp downstream |
| Kết hợp chuỗi | `joining(delimiter, prefix, suffix)` | Thường thay được collector `StringJoiner` minh họa |
| Thống kê nhiều chỉ số số học | `summarizingInt/Long/Double` | Có count, sum, min, max, average |
| Chuyển đổi kết quả collector | `collectingAndThen` | Tránh collector tự viết nếu chỉ cần finisher |
| Nhiều phép tổng hợp độc lập | `teeing` (Java 12+) | Có thể kết hợp hai collector và merger |

`CustomCollectorDemo` có ý nghĩa khi ứng dụng cần **đúng một Report** của miền nghiệp vụ với ba trường nhất quán, muốn dùng nó trực tiếp hoặc downstream. Ngay cả vậy, có thể thiết kế các collector chuẩn kết hợp qua `teeing`/`summarizing` nếu các kết quả phù hợp. Chọn hướng có ngữ nghĩa rõ ràng, bộ nhớ chấp nhận được và dễ kiểm thử.

## 12. Những lỗi thường gặp khi tự xây collector

**Lỗi 1 — supplier trả cùng một object:**

```java
List<String> shared = new ArrayList<>();
Collector<String, List<String>, List<String>> wrong =
        Collector.of(
                () -> shared,      // Sai: không tạo List mới.
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

Đoạn sai này khiến các lượt thu thập dùng chung `shared`; nếu chạy song song, các nhánh có thể sửa cùng container hoặc gộp cùng đối tượng với chính nó. Supplier phải tạo **container mới**.

**Lỗi 2 — combiner bỏ dữ liệu phía phải:** viết `(left,right) -> left` trong khi `right` có dữ liệu. Test tuần tự có thể không phát hiện, test song song và test kết hợp hai container sẽ bộc lộ lỗi.

**Lỗi 3 — nhầm `BiConsumer` với `BinaryOperator`:** accumulator không trả kết quả; combiner của `Collector.of` bắt buộc trả object trung gian.

**Lỗi 4 — khai báo `IDENTITY_FINISH` khi finisher chuyển kiểu:** nếu `A=MutableStats` và `R=Report`, không được khẳng định hai kiểu là một.

**Lỗi 5 — gắn `CONCURRENT` vào container không thread-safe:** `ArrayList`, `HashMap` hoặc các field đếm thường không hỗ trợ nhiều thread ghi vào cùng instance. `parallelStream()` không tự biện minh cho `CONCURRENT`.

**Lỗi 6 — gắn `UNORDERED` cho kết quả có thứ tự:** collector nối chuỗi hoặc thu thập List theo encounter order cần tôn trọng thứ tự đầu vào.

**Lỗi 7 — finisher làm rò rỉ trạng thái mutable:** trả một List/Map mutable vốn còn được giữ tham chiếu bởi code bên ngoài làm việc kiểm soát trạng thái khó dự đoán. Dùng defensive copy hoặc cấu trúc bất biến khi hợp đồng yêu cầu.

**Lỗi 8 — supplier không tạo trạng thái trung hòa:** nếu khởi tạo `lines=1` rồi chia nhiều nhánh, mỗi phần tích lũy đếm thừa. Test Stream rỗng, một phần tử và song song.

**Lỗi 9 — thao tác tích lũy không kết hợp đúng:** combiner có thể làm thay đổi kết quả nếu phụ thuộc vào thứ tự chia nhóm hoặc bỏ một trường. Hãy tự kiểm tra phép gộp ba container theo hai cách nhóm.

**Lỗi 10 — che ngoại lệ để trả kết quả có vẻ hợp lệ:** không bắt `Exception` rồi bỏ qua một dòng lỗi hoặc trả Report mặc định; xử lý lỗi nhập liệu rõ ràng trước khi collector hoặc báo thất bại. Trong demo, `Math.addExact`/`multiplyExact` sẽ báo `ArithmeticException` khi vượt giới hạn `long`, thay vì âm thầm trả số tràn.

**Lỗi 11 — mong collector được gọi theo đúng một thứ tự callback:** số lần `supplier`, `accumulator`, `combiner` và thời điểm `finisher` phụ thuộc cách thực thi; hãy kiểm tra kết quả cuối, không biến log callback thành nghiệp vụ.

**Lỗi 12 — không phân biệt tính bất biến của kết quả và trạng thái:** việc trả `Report` bất biến không làm cho `MutableStats` thread-safe. Hai vấn đề này độc lập; phải thiết kế collector đúng hợp đồng khi chạy song song.

## 13. Cách kiểm thử một collector tùy chỉnh

Chỉ kiểm thử `stream.collect(...)` trên ba phần tử tuần tự là chưa đủ. Nên có các lớp kiểm thử:

1. **Nguồn rỗng:** supplier tạo trạng thái trung hòa và finisher trả kết quả đúng.
2. **Một phần tử:** accumulator cập nhật đúng mọi trường.
3. **Nhiều phần tử:** kết quả đúng, không bỏ hay đếm trùng phần tử.
4. **Nhóm theo khóa:** downstream collector được khởi tạo và tích lũy riêng cho từng nhóm.
5. **Nguồn song song:** kết quả tương đương với tuần tự khi phép rút gọn đáp ứng hợp đồng.
6. **Combiner trực tiếp:** tạo hai container, tích lũy hai nửa nguồn, gộp, so với tích lũy toàn bộ.
7. **Identity:** container rỗng gộp với container có dữ liệu không làm thay đổi kết quả.
8. **Associativity:** gộp ba container theo `(a+b)+c` và `a+(b+c)` có cùng kết quả quan sát được.
9. **Characteristics:** xác minh chỉ khai báo đặc tính đúng với semantics thực tế.
10. **Tràn số và dữ liệu không hợp lệ:** ứng dụng có chính sách phản ứng rõ; collector không làm sai lệch thống kê.
11. **Thứ tự:** nếu kết quả phụ thuộc encounter order, kiểm tra đầu vào có thứ tự và combiner giữ thứ tự.
12. **Không thay đổi nguồn:** accumulator không sửa List/Set/Map được dùng làm nguồn Stream.

Ví dụ kiểm thử combiner trực tiếp trong cùng class `CustomCollectorDemo`:

```java
MutableStats left = new MutableStats();
MutableStats right = new MutableStats();
left.accept(new Order("Books", 2, 100));
right.accept(new Order("Food", 3, 40));

Report merged = left.merge(right).finish();
// merged = Report[lines=2, units=5, revenue=320]
```

Khi kiểm thử, đừng tái sử dụng `right` như thể combiner cam kết giữ nguyên mọi container. Hợp đồng chỉ quan tâm kết quả thích hợp sau gộp. Đoạn này là minh họa đặt trong class đã khai báo `MutableStats`, `Order`, `Report`.

### Kiểm tra các đặc tính về mặt hành vi

Một lời gọi `reportCollector().characteristics()` xác nhận collector **khai báo** `UNORDERED`/không khai báo `CONCURRENT`. Đây chỉ là test của đặc tính metadata, không đủ để chứng minh accumulator an toàn hoặc phép gộp kết hợp. Cần kiểm tra logic và chạy với nhiều dữ liệu/phân đoạn song song phù hợp.

Không nên dựa vào một lần `parallelStream()` thành công để khẳng định mọi collector tùy chỉnh đều thread-safe. Khả năng song song của framework phụ thuộc vào các đặc tính và cách chia phần; code tự viết phải có hợp đồng tổng hợp đúng trong mọi cách nhóm được phép.

## 14. Bài tập vận dụng

1. Viết `Collector<String,StringJoiner,String>` bằng `Collector.of(...)` để ghép các từ với dấu `" / "`, bọc giữa `"{"` và `"}"`. Kiểm tra trường hợp rỗng và thứ tự các từ.
2. Chuyển `listCollector()` thành collector thu về `List.copyOf(...)` thông qua finisher. Vì sao không được gắn `IDENTITY_FINISH` cho collector đó? Kiểm tra rằng List trả về không cho `add`.
3. Thêm `discount` vào record `Order`, cập nhật doanh thu sau giảm giá. Thiết kế chính sách kiểu số và cách làm tròn trước khi viết accumulator và combiner.
4. Viết collector thống kê cho `Stream<String>` trả `record TextStats(long items,long chars)`. Test Stream rỗng, Stream song song và nhóm chuỗi theo chữ cái đầu.
5. Cố tình sửa `MutableStats.merge` để quên cộng `units`. Tạo kiểm thử combiner trực tiếp để phát hiện sai, kể cả khi test Stream tuần tự còn chạy đúng.
6. Cố tình sửa supplier thành trả một `MutableStats` static được dùng chung. Giải thích vì sao đó là vi phạm hợp đồng collector, ngay cả khi chạy tuần tự có lúc in kết quả đúng.
7. Dùng collector báo cáo làm downstream của `partitioningBy(o -> o.quantity() >= 2, reportCollector())`. Dự đoán hai `Report`; trường hợp nhóm rỗng sẽ ra `Report(0,0,0)`.
8. So sánh `Collector.of` tự viết để cộng doanh thu với `Collectors.summingLong(o -> Math.multiplyExact((long)o.quantity(),o.unitPrice()))`. Khi chỉ cần tổng, cách nào đơn giản hơn?
9. Thiết kế collector giữ **thứ tự gặp phần tử** để trả chuỗi CSV đơn giản. Giải thích vì sao không được khai báo `UNORDERED`; nếu CSV có dấu phẩy trong giá trị, cần quy tắc quote/escape chính xác chứ không chỉ nối chuỗi.
10. Chỉ khi hiểu rõ thread safety, hãy mô tả một container có thể dùng với `CONCURRENT`. Nêu cách đảm bảo cập nhật đồng thời, khả năng giữ thứ tự và phép gộp.

## 15. Tổng kết

`Collector.of()` là công cụ tạo **collector tùy chỉnh** bằng cách mô tả các chức năng thiết yếu:

- `supplier` tạo container `A` mới ở trạng thái trung hòa.
- `accumulator` đưa từng phần tử `T` vào `A` bằng một `BiConsumer`.
- `combiner` gộp hai container `A` và **trả lại một `A`** qua `BinaryOperator`.
- `finisher` (nếu có) chuyển container `A` thành kết quả `R`.

Dạng không có finisher thích hợp khi **`A=R`**; dạng có finisher phù hợp khi cần chuyển từ trạng thái mutable sang kết quả khác, ví dụ `MutableStats` thành `Report` bất biến. Các đặc tính `IDENTITY_FINISH`, `UNORDERED`, `CONCURRENT` phải phản ánh đúng hợp đồng, đặc biệt khi pipeline chạy song song.

Hãy ưu tiên collector chuẩn cho nhu cầu phổ biến. Chỉ viết `Collector.of` khi kết quả miền nghiệp vụ hoặc quy tắc tích lũy thật sự cần một collector riêng, rồi kiểm thử nguồn rỗng, nhiều phần tử, combiner, xử lý song song và đầu ra bất biến. Một collector tốt phải **đúng cho nhiều cách phân đoạn nguồn**, không chỉ đúng trong lần chạy tuần tự đầu tiên.
