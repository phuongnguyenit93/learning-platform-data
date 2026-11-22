# Tạo Collector tùy biến bằng `Collector.of`

> **Chương:** Cơ chế collect và Collector  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce` và `collect`; tìm hiểu thêm grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

Trong xử lý dữ liệu thực tế, kết quả mong muốn không phải lúc nào cũng là một `List`, `Map` hay một tổng số đơn giản. Chẳng hạn, báo cáo đơn hàng cần **đếm số đơn**, **tính tổng tiền**, **tìm giá trị nhỏ nhất, lớn nhất** và **tính trung bình đã làm tròn** trong cùng một lượt duyệt. Ta có thể thiết kế một đối tượng tích lũy trung gian và sử dụng `Collector.of(...)` để mô tả rõ cách tạo, cập nhật, hợp nhất và chuyển đổi đối tượng đó thành kết quả cuối.

Sau bài này, bạn có thể:

- Giải thích vai trò của `supplier`, `accumulator`, `combiner`, `finisher` trong `Collector.of`.
- Tạo collector trả về chính vùng tích lũy hoặc tạo kết quả khác kiểu.
- Bảo đảm tính đúng đắn của collector khi pipeline tuần tự hoặc song song.
- Lựa chọn đúng `Characteristics` và tránh các lỗi trạng thái dùng chung, hợp nhất sai hay xử lý luồng rỗng không rõ ràng.

## 1. Khi nào cần `Collector.of`?

Các collector dựng sẵn thường giải quyết tốt những bài toán phổ biến:

| Mục tiêu | API có sẵn |
| --- | --- |
| Thu thập thành danh sách | `Collectors.toList()`, `Stream.toList()` (Java 16+) |
| Đếm phần tử | `Collectors.counting()`, `Stream.count()` |
| Tính thống kê số kiểu nguyên thủy | `Collectors.summarizingInt(...)`, `summarizingLong(...)`, `summarizingDouble(...)` |
| Phân nhóm | `Collectors.groupingBy(...)` |
| Ghép chuỗi | `Collectors.joining(...)` |
| Tổng hợp hai kết quả của hai collector | `Collectors.teeing(...)` (Java 12+) |

Nếu các API này đã diễn đạt đầy đủ yêu cầu, nên ưu tiên chúng. `Collector.of` hữu ích khi **đối tượng tích lũy và kết quả có cấu trúc riêng**, ví dụ thống kê nhiều chỉ số trên `BigDecimal`, xây dựng chỉ mục chuyên biệt, thu thập có bước hoàn thiện, hoặc cần kiểm soát cách gộp các kết quả trung gian.

`collect` là **terminal operation**: nó kích hoạt duyệt nguồn của pipeline. `Collector.of` chỉ là **phương thức tạo ra một Collector**; gọi `Collector.of` chưa duyệt dữ liệu. Việc duyệt diễn ra khi dùng collector đó trong `stream.collect(collector)`.

## 2. Các kiểu dữ liệu và hai overload của `Collector.of`

Một `Collector<T, A, R>` có ba tham số kiểu:

- `T`: kiểu phần tử đầu vào của Stream.
- `A`: kiểu **trạng thái tích lũy trung gian**, thường là một đối tượng có thể thay đổi.
- `R`: kiểu **kết quả cuối** sau khi thu thập.

Hai dạng quan trọng của factory method `Collector.of`:

```java
// A cũng là kiểu kết quả cuối (không cần finisher riêng):
static <T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);

// Trạng thái trung gian A được chuyển thành kết quả R:
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
```

Các chữ ký trên được trình bày để giải thích kiểu; để biên dịch cần các interface trong `java.util.function`, `Collector` trong `java.util.stream`. Nhóm tham số `characteristics` là varargs, nên có thể bỏ qua khi không cần khai báo đặc tính bổ sung.

| Thành phần | Giao diện hàm | Nhiệm vụ |
| --- | --- | --- |
| `supplier` | `Supplier<A>` | Tạo **một vùng tích lũy mới, độc lập**. |
| `accumulator` | `BiConsumer<A, T>` | Đưa một phần tử `T` vào vùng tích lũy `A`. |
| `combiner` | `BinaryOperator<A>` | Gộp **hai vùng tích lũy** thành một `A` hợp lệ. |
| `finisher` | `Function<A, R>` | Chuyển trạng thái `A` sang kết quả `R`. |
| `characteristics` | Các hằng trong `Collector.Characteristics` | Khai báo đặc tính để Stream có thể chọn chiến lược thu thập phù hợp. |

Hình dung quy trình:

```text
  Stream<T>                    khi chia nguồn để xử lý
  phần tử T                     theo nhiều nhánh
      │                          ┌────────────┐
      ▼                          │ supplier A │──┐
 supplier() → A                  └────────────┘  │
      │                          ┌────────────┐  ├─► combiner(A, A) → A
 accumulator(A, T) ...           │ supplier A │──┘           │
      │                          └────────────┘              │
      └───────────── A ───────────────────────────────────────┘
                             │
                             ▼
                         finisher(A)
                             │
                             ▼
                        Kết quả R
```

`combiner` là thành phần của hợp đồng collector dù bạn chỉ gọi `stream()` tuần tự. Khi chạy song song, implementation thường tạo nhiều trạng thái `A` riêng, tích lũy từng phần rồi gộp chúng bằng `combiner`. Vì thế, collector phải được thiết kế đúng với **cả hai cách phân chia và hợp nhất**.

## 3. Ví dụ nhỏ: thu thập vào một danh sách bằng overload không có finisher

Để thấy rõ ba thành phần đầu, hãy viết collector mô phỏng việc thêm phần tử vào `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> result = List.of("Java", "Stream", "API").stream()
        .collect(Collector.of(
                () -> new ArrayList<String>(),  // supplier
                ArrayList::add,                  // accumulator
                (left, right) -> {               // combiner
                    left.addAll(right);
                    return left;
                }
        ));

System.out.println(result); // [Java, Stream, API]
```

Trong ví dụ:

1. `supplier` tạo **danh sách mới** khi cần vùng tích lũy.
2. `accumulator` thêm từng phần tử vào danh sách đang được tích lũy.
3. `combiner` nối các phần tử của danh sách phải vào danh sách trái, sau đó **trả về danh sách đã hợp nhất**.

Overload ba hàm có kết quả cùng kiểu với vùng tích lũy (`A = R`) và collector có đặc tính `IDENTITY_FINISH`. Nó **không tự biến danh sách thành bất biến**: `result` là `ArrayList` có thể sửa. Nếu chỉ cần thu thập danh sách, dùng collector có sẵn thường gọn và dễ duy trì hơn.

## 4. Ví dụ hoàn chỉnh: tính báo cáo doanh thu bằng `Collector.of`

Yêu cầu: trên các đơn hàng **đã thanh toán**, tính tổng số đơn, tổng tiền, tiền nhỏ nhất, tiền lớn nhất và tiền bình quân làm tròn hai chữ số. Sử dụng `BigDecimal` để tránh sai số dấu chấm động khi tổng hợp tiền; bình quân có quy tắc `HALF_UP`.

Chương trình dưới đây chạy độc lập trên Java 17+. Lưu thành `CustomCollectorDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collector;

public class CustomCollectorDemo {
    record Order(String id, boolean paid, BigDecimal amount) {}

    // Kết quả cuối: bất biến, thể hiện rõ những thống kê
    // không tồn tại khi tập đầu vào rỗng.
    record SalesReport(
            long count,
            BigDecimal total,
            Optional<BigDecimal> min,
            Optional<BigDecimal> max,
            Optional<BigDecimal> average
    ) {}

    // Trạng thái trung gian: mỗi supplier tạo một đối tượng riêng.
    static final class Accumulator {
        private long count;
        private BigDecimal total = BigDecimal.ZERO;
        private BigDecimal min;
        private BigDecimal max;

        void add(Order order) {
            Objects.requireNonNull(order, "order");
            BigDecimal amount = Objects.requireNonNull(
                    order.amount(), "amount");

            count++;
            total = total.add(amount);

            if (min == null || amount.compareTo(min) < 0) {
                min = amount;
            }
            if (max == null || amount.compareTo(max) > 0) {
                max = amount;
            }
        }

        Accumulator combine(Accumulator other) {
            count += other.count;
            total = total.add(other.total);

            if (other.min != null
                    && (min == null || other.min.compareTo(min) < 0)) {
                min = other.min;
            }
            if (other.max != null
                    && (max == null || other.max.compareTo(max) > 0)) {
                max = other.max;
            }

            return this;
        }

        SalesReport finish() {
            Optional<BigDecimal> average = count == 0
                    ? Optional.empty()
                    : Optional.of(total.divide(
                            BigDecimal.valueOf(count),
                            2,
                            RoundingMode.HALF_UP));

            return new SalesReport(
                    count,
                    total,
                    Optional.ofNullable(min),
                    Optional.ofNullable(max),
                    average);
        }
    }

    static Collector<Order, ?, SalesReport> salesCollector() {
        return Collector.of(
                Accumulator::new,
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("D-01", true, new BigDecimal("120.00")),
                new Order("D-02", false, new BigDecimal("500.00")),
                new Order("D-03", true, new BigDecimal("80.00")),
                new Order("D-04", true, new BigDecimal("200.00"))
        );

        SalesReport report = orders.stream()
                .filter(Order::paid)
                .collect(salesCollector());

        System.out.println("Số đơn: " + report.count());
        System.out.println("Tổng tiền: " + report.total());
        System.out.println("Nhỏ nhất: " + report.min().orElseThrow());
        System.out.println("Lớn nhất: " + report.max().orElseThrow());
        System.out.println("Trung bình: " + report.average().orElseThrow());

        SalesReport parallelReport = orders.parallelStream()
                .filter(Order::paid)
                .collect(salesCollector());
        System.out.println("Song song giống tuần tự: "
                + report.equals(parallelReport));

        SalesReport emptyReport = orders.stream()
                .filter(o -> false)
                .collect(salesCollector());
        System.out.println("Rỗng: " + emptyReport.count()
                + " / " + emptyReport.average());
    }
}
```

Đầu ra:

```text
Số đơn: 3
Tổng tiền: 400.00
Nhỏ nhất: 80.00
Lớn nhất: 200.00
Trung bình: 133.33
Song song giống tuần tự: true
Rỗng: 0 / Optional.empty
```

### Vì sao tách `Accumulator` và `SalesReport`?

- `Accumulator` có trạng thái thay đổi theo phần tử; nhờ đó mỗi lần `add` chỉ cần cập nhật một số trường và mỗi lần `combine` chỉ cần gộp hai tập thống kê.
- `SalesReport` là record bất biến, không lộ vùng tích lũy có thể sửa. `finisher` làm tròn **một lần khi tạo báo cáo**, thay vì làm tròn sau từng phép cộng; điều này bảo toàn tính kết hợp cho tổng tiền.
- `Optional<BigDecimal>` biểu diễn rõ `min`, `max`, `average` **vắng mặt** nếu không có đơn nào. `count = 0` và `total = 0` là kết quả hợp lệ của tập rỗng.
- Đơn `D-02` không được tính vì đã bị loại bằng `filter(Order::paid)` trước terminal operation.

Trong ví dụ, mọi `amount` đều khác `null`; nếu dữ liệu nguồn cho phép thiếu tiền, cần xác định chính sách **lọc trước** hoặc báo lỗi. `Objects.requireNonNull` làm lỗi dữ liệu lộ rõ, tránh việc âm thầm xem số tiền bị thiếu là 0.

## 5. Hợp đồng đúng đắn: identity và associativity

Viết một collector chạy được tuần tự chưa đủ. Java Stream có thể chia nguồn thành các phần, tích lũy riêng và hợp nhất theo nhiều cách. Collector phải thỏa **hợp đồng identity và associativity**.

### Identity: vùng tích lũy rỗng phải trung hòa

Vùng `supplier.get()` tạo ra phải đại diện cho **chưa thu thập phần tử nào**. Với `Accumulator` ở ví dụ:

```text
count = 0
total = 0
min = chưa có
max = chưa có
```

Hợp nhất một trạng thái đã tích lũy `a` với trạng thái mới rỗng về mặt kết quả phải tương đương với `a` ban đầu:

```text
combine(a, empty)  ≈  a
```

`combine` trong ví dụ chỉ thêm `0` vào đếm/tổng và bỏ qua `min/max` rỗng, nên thỏa yêu cầu đó. Đây là **tương đương về kết quả**, không nhất thiết là cùng một đối tượng theo `==`.

### Associativity: cách chia và gộp không được làm đổi kết quả

Nếu nguồn gồm ba đoạn `X`, `Y`, `Z`, việc gộp `(X + Y) + Z` và `X + (Y + Z)` phải cho **kết quả tương đương**:

```text
combine(combine(Ax, Ay), Az)
             ≈
combine(Ax, combine(Ay, Az))
```

Khi từng trạng thái chứa `count`, `total`, `min`, `max`, việc cộng số đếm, cộng `BigDecimal` và chọn min/max là các cách gộp phù hợp. Vì `BigDecimal` tính tổng chính xác ở bước tích lũy, chỉ làm tròn `average` trong `finisher`, phép gộp không lệ thuộc vào nơi chia nguồn trong ví dụ này.

**Sai lầm đáng tránh:** nếu tính bình quân của hai nhánh rồi lấy trung bình hai bình quân, kết quả sẽ sai khi các nhánh có số phần tử khác nhau:

```text
Nhánh A: [10, 20]      → average = 15, count = 2
Nhánh B: [100]         → average = 100, count = 1

Sai:  (15 + 100) / 2 = 57.5
Đúng: (10 + 20 + 100) / 3 ≈ 43.33
```

Thay vì lưu một giá trị trung bình đã làm tròn rồi gộp, **lưu `sum` và `count`**, sau đó mới tính `sum / count` trong `finisher`.

### Không được bỏ quên trạng thái của nhánh phải

```java
// SAI: combiner bỏ kết quả của nhánh phải.
(left, right) -> left

// ĐÚNG với accumulator là danh sách:
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Collector có combiner sai đôi khi vẫn cho kết quả “đúng” khi chạy tuần tự, vì implementation có thể không cần gộp nhánh. Khi chạy song song, dữ liệu dễ bị mất hoặc cho kết quả không ổn định.

## 6. Các `Collector.Characteristics` và ý nghĩa thực tế

`Collector.of` cho phép khai báo các đặc tính bằng `Collector.Characteristics`.

| Đặc tính | Nghĩa | Điều kiện để khai báo đúng |
| --- | --- | --- |
| `IDENTITY_FINISH` | Có thể dùng luôn vùng tích lũy như kết quả, không cần chuyển đổi thực chất | `A` và `R` tương thích, finisher thực sự là identity. |
| `UNORDERED` | Kết quả không phụ thuộc encounter order của phần tử nguồn | Nghiệp vụ chấp nhận kết quả tương đương bất kể thứ tự đầu vào. |
| `CONCURRENT` | Cho phép nhiều luồng cùng gọi accumulator trên **một** vùng tích lũy | Vùng tích lũy và toàn bộ thao tác cập nhật phải an toàn với truy cập đồng thời. |

### `IDENTITY_FINISH`

Overload không có `finisher` của `Collector.of` dùng vùng tích lũy làm kết quả. Trong ví dụ danh sách ở mục 3, `A` cũng là `R`, vì vậy `IDENTITY_FINISH` phù hợp.

Với báo cáo `Accumulator -> SalesReport`, **không khai báo `IDENTITY_FINISH`**: Stream phải chạy `Accumulator::finish` để tạo record và tính bình quân. Khai báo sai có thể khiến implementation bỏ qua finisher và làm xuất hiện lỗi kiểu dữ liệu khi nhận kết quả.

### `UNORDERED`

Báo cáo chỉ gồm `count`, `sum`, `min`, `max`, `average`, nên với `BigDecimal` có tính toán theo hợp đồng trong ví dụ, giá trị kết quả **không phụ thuộc thứ tự xuất hiện**. Có thể khai báo `UNORDERED` nếu muốn:

```java
Collector<Order, ?, SalesReport> unorderedSummary = Collector.of(
        Accumulator::new,
        Accumulator::add,
        Accumulator::combine,
        Accumulator::finish,
        Collector.Characteristics.UNORDERED
);
```

Đoạn trên dùng `Order`, `Accumulator`, `SalesReport` đã định nghĩa trong `CustomCollectorDemo`; cần đặt trong phạm vi truy cập được các kiểu đó. `UNORDERED` **không có nghĩa** Java phải tráo ngẫu nhiên dữ liệu. Nó chỉ nói kết quả của collector không phụ thuộc vào encounter order.

Không đánh dấu `UNORDERED` cho collector khi cần bảo đảm danh sách theo thứ tự nguồn, ghép chuỗi theo thứ tự, chọn phần tử đầu tiên hay bất kỳ cấu trúc có ngữ nghĩa thứ tự nào.

### `CONCURRENT`

Đừng nhầm **collector có thể dùng trong `parallelStream()`** với **collector có đặc tính `CONCURRENT`**. Đối với collector không concurrent, Stream có thể cấp các `Accumulator` độc lập cho các nhánh song song và gộp chúng bằng combiner. Các trường thay đổi thông thường trong `Accumulator` ở mục 4 vẫn phù hợp với mô hình này.

Nếu khai báo `CONCURRENT`, `accumulator` phải xử lý được nhiều luồng cập nhật **cùng một trạng thái A**. Chẳng hạn, `count++` không phải phép tăng nguyên tử; việc cập nhật `min` và `max` cũng cần phối hợp đúng. Dùng một `AtomicLong` riêng cho count chưa đủ bảo đảm toàn bộ collector đúng nếu các trường khác vẫn có tranh chấp.

Với một collector khai báo `CONCURRENT` nhưng không khai báo `UNORDERED`, Stream chỉ được tích lũy đồng thời trên một container theo cách phù hợp khi nguồn không có yêu cầu encounter order. Không thêm đặc tính chỉ với hy vọng tăng tốc; hãy chứng minh hợp đồng và đo hiệu năng.

## 7. Trạng thái dùng chung, tính không can thiệp và nguồn dữ liệu

### Mỗi lần `supplier` phải tạo trạng thái mới

```java
// SAI: chia sẻ đúng một danh sách cho mọi lần gọi supplier.
List<String> shared = new java.util.ArrayList<>();
var badCollector = Collector.of(
        () -> shared,
        List<String>::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

Nếu `supplier` trả cùng đối tượng, các nhánh có thể cùng sửa danh sách, rồi combiner còn có thể gộp một danh sách vào chính nó, gây dữ liệu nhân đôi hoặc lỗi đồng thời. `supplier` phải tạo ra **container mới, độc lập**:

```java
// Tốt hơn: mỗi lần gọi supplier có danh sách riêng.
() -> new java.util.ArrayList<String>()
```

Trong ví dụ đơn hàng, `Accumulator::new` cung cấp đúng đặc tính đó. `Collector` có thể dùng nhiều lần trên các Stream khác nhau miễn là nó không chứa trạng thái dùng chung bị thay đổi ngoài vòng đời thu thập.

### Không để dữ liệu thay đổi trong lúc collect

Các callback của collector không nên sửa collection nguồn, phụ thuộc vào bộ đếm bên ngoài hoặc dùng side effect không có hợp đồng rõ ràng. Với nguồn Stream song song, thứ tự các lần gọi callback không nhất thiết trùng thứ tự của nguồn. Hãy để dữ liệu cần tổng hợp nằm trong `A`, được cập nhật qua `accumulator` và `combiner`.

Ví dụ, thay vì tăng một biến `globalCount` trong lambda `filter` hay `peek`, nên tăng `count` trong trạng thái tích lũy nếu đây là chỉ số được báo cáo. Việc này giúp phép xử lý đúng với cách chia nhánh của Stream.

### Một Stream chỉ có một vòng đời thu thập

```java
// Sau collect, một đối tượng Stream đã bị tiêu thụ.
// Stream<Order> source = orders.stream();
// SalesReport a = source.collect(salesCollector());
// SalesReport b = source.collect(salesCollector()); // Không hợp lệ.
```

Muốn tạo hai báo cáo từ nguồn `List`, hãy gọi `orders.stream()` mới cho từng báo cáo. Nếu nguồn gắn với tài nguyên I/O hoặc chỉ đọc một lần, chọn collector tổng hợp nhiều chỉ số trong một lượt giúp giảm việc duyệt lại và phải tuân thủ quy tắc đóng tài nguyên.

## 8. So sánh với ba dạng `collect` khác và `reduce`

Có hai cách gọi `collect` dễ bị nhầm:

```java
// 1) Nhận một Collector<T, A, R>:
R result = stream.collect(collector);

// 2) Dạng ba đối số: trả trực tiếp một vùng kết quả R.
R result2 = stream.collect(supplier, accumulator, combiner);
```

Đây là chữ ký minh họa. Với dạng ba đối số của **`Stream.collect`**, `combiner` có kiểu **`BiConsumer<R,R>`** và hợp nhất bằng side effect; với `Collector.of`, `combiner` có kiểu **`BinaryOperator<A>`** và phải **trả về** container hợp nhất. Dạng `Collector.of` còn hỗ trợ `finisher` riêng và khai báo characteristics, thuận tiện cho collector tái sử dụng.

Ví dụ dùng `Stream.collect` ba đối số để gom danh sách:

```java
List<String> values = List.of("A", "B", "C").stream()
        .collect(
                java.util.ArrayList::new,
                java.util.List::add,
                java.util.List::addAll
        );
// [A, B, C]
```

Nếu chỉ cần cộng một giá trị bất biến hoặc reduction theo phép toán kết hợp đơn giản, `reduce` thường rõ hơn:

```java
long total = java.util.stream.LongStream.of(4, 5, 6).sum(); // 15
```

`Collector.of` phù hợp với **mutable reduction** có vùng tích lũy riêng; không cần tự viết collector để thay thế một `sum()` hay `Collectors.joining()` đơn giản. Khi chỉ muốn chỉnh kết quả cuối của một collector sẵn có, `Collectors.collectingAndThen(...)` cũng là lựa chọn đáng cân nhắc.

## 9. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `supplier` trả về cùng container dùng chung | Các nhánh cùng sửa dữ liệu, có thể nhân đôi/mất dữ liệu | Tạo đối tượng mới mỗi lần gọi supplier. |
| `combiner` chỉ trả `left`, bỏ qua `right` | Mất dữ liệu khi có nhiều nhánh | Hợp nhất đầy đủ rồi trả container kết quả. |
| Gộp trung bình của hai nhánh bằng trung bình cộng thông thường | Sai khi nhánh có kích thước khác nhau | Gộp `sum` và `count`, tính average ở finisher. |
| Làm tròn tiền trong `accumulator` trước khi cộng | Kết quả phụ thuộc cách chia nguồn | Tính bằng `BigDecimal`, làm tròn khi hoàn thiện. |
| Khai báo `IDENTITY_FINISH` dù `A` khác `R` | Finisher có thể bị bỏ qua, trả sai kiểu | Không dùng đặc tính này cho collector có finisher biến đổi kết quả. |
| Khai báo `CONCURRENT` khi container không thread-safe | Tranh chấp dữ liệu, thống kê sai | Bỏ `CONCURRENT` hoặc thiết kế tích lũy đồng thời đúng hợp đồng. |
| Khai báo `UNORDERED` cho kết quả phụ thuộc thứ tự | Có thể thay đổi thứ tự kết quả | Giữ đặc tính thứ tự khi nghiệp vụ cần. |
| Dùng `null` cho dữ liệu không có quy tắc | `NullPointerException` hoặc báo cáo sai | Lọc, báo lỗi hoặc thể hiện thiếu bằng Optional theo chính sách. |
| Dùng lại cùng một Stream sau `collect` | `IllegalStateException` | Tạo Stream mới từ nguồn có thể duyệt lại. |

## 10. Tự kiểm tra

**Câu 1.** Trong `Collector<T,A,R>`, vì sao `A` và `R` có thể khác nhau?

**Trả lời:** `A` là vùng tích lũy cần được thay đổi trong lúc duyệt; `R` là kết quả cuối được tạo bởi `finisher`. Ví dụ `Accumulator` chứa trạng thái thay đổi còn `SalesReport` là record bất biến.

**Câu 2.** Vì sao collector dùng `ArrayList` làm vùng tích lũy vẫn có thể thu thập trên `parallelStream()` dù `ArrayList` không thread-safe?

**Trả lời:** Nếu không khai báo `CONCURRENT` và supplier tạo container riêng, Stream có thể tích lũy trên các container độc lập rồi dùng combiner để gộp. Việc dùng `parallelStream()` không đồng nghĩa accumulator bắt buộc phải chạy đồng thời trên một container.

**Câu 3.** Cho nhánh A có hai giá trị `10, 20` và nhánh B có một giá trị `100`. Cách gộp `(avgA + avgB)/2` có đúng không?

**Trả lời:** Không. Trung bình chung là `(10 + 20 + 100)/3 ≈ 43.33`, khác `57.5`. Cần gộp tổng và số lượng trước.

**Câu 4.** Collector đang xây dựng `StringBuilder` rồi gọi `toString()` để trả `String` có nên khai báo `IDENTITY_FINISH` không?

**Trả lời:** Không. `A = StringBuilder`, `R = String`; bước `finisher` có biến đổi kiểu kết quả.

**Câu 5.** Nếu Stream rỗng, `supplier` và `finisher` của báo cáo ở mục 4 phải cho kết quả thế nào?

**Trả lời:** Trạng thái rỗng có `count = 0`, `total = 0`, `min/max` chưa có; `finisher` trả `SalesReport` với `Optional.empty()` cho `min`, `max`, `average`. Không tự bịa cực trị.

## Ghi nhớ

- `Collector.of` mô tả **tạo trạng thái → tích lũy phần tử → gộp trạng thái → hoàn thiện kết quả**.
- `supplier` phải tạo container mới; `accumulator` cập nhật từng phần tử; `combiner` hợp nhất đầy đủ; `finisher` chuyển `A` thành `R`.
- Hợp đồng **identity** và **associativity** giúp kết quả đúng dù cách phân chia nhánh và thứ tự hợp nhất khác nhau.
- `IDENTITY_FINISH`, `UNORDERED`, `CONCURRENT` là các cam kết có ý nghĩa thực thi, chỉ khai báo khi thực sự đúng.
- Với nghiệp vụ tổng hợp nhiều chỉ số, ưu tiên trạng thái tích lũy độc lập, xử lý tập rỗng rõ ràng và làm tròn ở bước hoàn thiện; dùng collector sẵn có khi chúng đã diễn đạt đủ yêu cầu.
