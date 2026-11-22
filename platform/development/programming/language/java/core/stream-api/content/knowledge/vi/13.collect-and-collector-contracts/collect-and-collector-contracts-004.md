# Đọc kiểu `Collector<T, A, R>` và kiểu trạng thái tích lũy

## 1. Vì sao `collect` cần một kiểu trạng thái riêng?

Trong **JAVA_STREAM_API**, các phép `filter`, `map` và `flatMap` mô tả cách chọn hoặc biến đổi phần tử của pipeline; phép toán kết thúc `collect` biến nhiều phần tử thành một kết quả có cấu trúc. Kết quả có thể là danh sách, tập hợp, bản đồ theo nhóm, thống kê hoặc một đối tượng nghiệp vụ.

Chẳng hạn, muốn tính tổng tiền theo vùng từ một `Stream<Order>`:

```java
Map<String, Long> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

Ở đây, phần tử đầu vào là `Order`, nhưng kết quả là `Map<String, Long>`. Trong lúc thực hiện, collector có thể cần một vùng nhớ để ghi nhận các nhóm và tổng tạm thời. **Kiểu vùng nhớ đó không nhất thiết trùng với kiểu phần tử hoặc kiểu kết quả cuối.**

Đây là lý do interface `Collector` có **ba tham số kiểu**:

```java
Collector<T, A, R>
```

- **`T` (input)**: kiểu phần tử mà collector nhận từ stream.
- **`A` (accumulation)**: kiểu *trạng thái tích lũy có thể thay đổi* trong quá trình thu thập.
- **`R` (result)**: kiểu kết quả mà terminal operation trả về.

Mục tiêu sau bài học:

1. Đọc chính xác `Collector<T, A, R>` và chữ ký `Stream.collect`.
2. Hiểu năm thành phần `supplier`, `accumulator`, `combiner`, `finisher` và `characteristics`.
3. Phân biệt **`A` là trạng thái nội bộ** với **`R` là kết quả công khai**.
4. Đọc kiểu của `Collectors.toList`, `groupingBy`, `mapping` và downstream collector.
5. Tự xây collector có kết quả bất biến và phép gộp hợp lệ.
6. Phân tích điều kiện đúng đắn khi stream được phân chia để xử lý song song, cũng như các giới hạn về tài nguyên, trạng thái và hiệu năng.

Các ví dụ đầy đủ trong bài dùng **Java 17+**, vì có `record` và `Stream.toList()`. Phần lớn cơ chế `Collector` đã có từ Java 8; hãy kiểm tra mục `Since` của API nếu dự án dùng JDK cũ.

## 2. Giải mã chữ ký `Collector<T, A, R>`

Interface được khai báo trong `java.util.stream`:

```java
public interface Collector<T, A, R> {
    Supplier<A> supplier();
    BiConsumer<A, T> accumulator();
    BinaryOperator<A> combiner();
    Function<A, R> finisher();
    Set<Characteristics> characteristics();
}
```

Chữ ký trên được rút gọn để dễ học, nhưng thể hiện đúng vai trò của các phương thức. Các functional interface `Supplier`, `BiConsumer`, `BinaryOperator`, `Function` thuộc `java.util.function`.

| Ký hiệu | Được dùng ở đâu? | Đọc như thế nào? |
| --- | --- | --- |
| `T` | `BiConsumer<A,T>` | Mỗi phần tử đầu vào, ví dụ `Order` |
| `A` | `Supplier<A>`, `BiConsumer<A,T>`, `BinaryOperator<A>` | Trạng thái mà collector tạo, cập nhật và gộp |
| `R` | `Function<A,R>` | Dữ liệu cuối cùng đưa cho người gọi |
| `Supplier<A>` | `supplier()` | Tạo một trạng thái tích lũy mới, ban đầu rỗng |
| `BiConsumer<A,T>` | `accumulator()` | Nhập một `T` vào trạng thái `A` |
| `BinaryOperator<A>` | `combiner()` | Gộp hai trạng thái `A` thành một `A` |
| `Function<A,R>` | `finisher()` | Chuyển trạng thái cuối `A` thành kết quả `R` |

Một collector có thể dùng object mutable để tích lũy rồi trả object bất biến:

```text
                  supplier()
                      │
                      ▼
              A: trạng thái rỗng
                      │
          accumulator(A, T)
                      │
                  nhiều lần
                      ▼
              A: trạng thái đầy
                      │
             combiner(A, A)
         (khi cần gộp các phần)
                      │
                      ▼
                 finisher(A)
                      │
                      ▼
                 R: kết quả
```

**Điểm cần nhớ:** `A` là kiểu **bộ tích lũy**, không phải “mảng dữ liệu”, “kiểu của phần tử sau `map`”, hay “kiểu trả về của `collect`”. Nó có thể là `ArrayList<T>`, `HashMap<K,V>`, một object chứa nhiều bộ đếm, hoặc một kiểu nội bộ khác. Người gọi thường **không cần biết `A` cụ thể là gì**.

## 3. Đọc `Stream.collect(Collector)` từ ngoài vào trong

Overload nhận một collector trên `Stream<T>` có chữ ký:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

Lấy ví dụ `Stream<Order>`:

- `T = Order` do stream xác định.
- `Collector<? super T, A, R>` được phép nhận phần tử `Order` (hoặc kiểu cha tương thích).
- `A` xác định trạng thái tích lũy nội bộ.
- `R` là **kiểu trả về của chính `collect`**.

Một cách đọc thực tế:

```java
Stream<Order> source = orders.stream();
Map<String, Long> result = source.collect(
    Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    )
);
```

Ở dòng `result`, compiler suy ra `R = Map<String, Long>`. Kiểu `A` không hiện ra trong biến kết quả; nó được suy luận từ collector được truyền vào.

Không nhầm `collect` với `map`: `map` là **intermediate operation**, trả về stream mới và được thực thi lười. `collect` là **terminal operation**, tiêu thụ pipeline để trả một `R`. Muốn có hai kết quả từ cùng collection, cần mở hai stream mới; không thể gọi terminal operation lần hai trên stream đã tiêu thụ.

Tài liệu cần tra:

- [`Collector<T,A,R>` — Javadoc Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html)
- [`Stream.collect` — Javadoc Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector))
- [`Collectors` — các factory collector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [Package `java.util.stream` — reduction và parallelism](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)

## 4. Vòng đời của trạng thái `A`

### 4.1. `supplier` tạo bộ tích lũy

`Supplier<A>` trả một `A` mới ở trạng thái ban đầu. Thường là một container rỗng, chẳng hạn:

```java
Supplier<ArrayList<String>> supplier = ArrayList::new;
ArrayList<String> left = supplier.get();
ArrayList<String> right = supplier.get();
```

`left` và `right` là **hai trạng thái độc lập**; trong xử lý song song, thư viện có thể tạo nhiều trạng thái rồi gộp lại. Supplier không nên trả cùng một `ArrayList` mutable toàn cục cho mọi lời gọi.

### 4.2. `accumulator` đưa một phần tử vào `A`

`BiConsumer<A,T>` nhận trạng thái `A` và phần tử `T`; kiểu trả về là `void`. Khi tích lũy danh sách:

```java
BiConsumer<ArrayList<String>, String> accumulator =
    ArrayList::add;

accumulator.accept(left, "Java");
accumulator.accept(left, "Stream");
// left = ["Java", "Stream"]
```

Collector thông thường được thiết kế theo kiểu **mutable reduction**: accumulator cập nhật container đang được quản lý, tránh phải tạo lại toàn bộ container cho mỗi phần tử. Dù trạng thái mutable, phần `filter`/`map` trước đó vẫn nên không can thiệp vào nguồn và không phụ thuộc trạng thái thay đổi.

### 4.3. `combiner` gộp các trạng thái

`BinaryOperator<A>` nhận **hai `A`** và trả **một `A`** biểu diễn kết quả đã gộp:

```java
BinaryOperator<ArrayList<String>> combiner = (a, b) -> {
    a.addAll(b);
    return a;
};

ArrayList<String> combined = combiner.apply(left, right);
```

Việc gộp không được làm mất dữ liệu; điều kiện kết hợp và tương thích với accumulator rất quan trọng khi pipeline bị phân chia nhiều nhánh. Collector có thể được chạy với nhiều `A` ngay cả khi lập trình viên chỉ nhìn thấy một lời gọi `collect`.

### 4.4. `finisher` tạo `R`

Một collector có thể giữ `ArrayList<T>` trong lúc xử lý rồi trả một bản sao không thể sửa đổi:

```java
Function<ArrayList<String>, List<String>> finisher = List::copyOf;

List<String> result = finisher.apply(combined);
```

Trong ví dụ này:

```text
T = String
A = ArrayList<String>
R = List<String>
```

`List.copyOf` không cho phép phần tử `null`. Đây là một quyết định về hợp đồng dữ liệu, không phải thuộc tính mặc định của mọi collector. Nếu `A` và `R` cùng kiểu, finisher vẫn có thể làm công việc thực như sao chép; chỉ khi finisher **đúng là phép đồng nhất theo hợp đồng** mới có thể gắn đặc tính `IDENTITY_FINISH`.

### 4.5. `characteristics` mô tả bảo đảm của collector

Đặc tính nằm trong `Collector.Characteristics` và ảnh hưởng đến cách Stream framework có thể thực hiện thu thập. Ba giá trị chính là `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH`; chúng sẽ được phân tích ở mục 10.

## 5. Tại sao `A` thường xuất hiện dưới dạng `?`?

Những collector dựng sẵn thường **che kiểu tích lũy** trong chữ ký công khai. Ví dụ:

```java
// Chữ ký rút gọn của factory method:
<T> Collector<T, ?, List<T>> toList()

<T> Collector<T, ?, Set<T>> toSet()

<T> Collector<T, ?, Long> counting()
```

Ký hiệu `?` ở vị trí thứ hai không có nghĩa collector “không cần trạng thái”. Nó có nghĩa **người gọi không biết và không cần phụ thuộc vào kiểu `A` thực tế**. Trong lúc thực hiện, thư viện vẫn có thể tạo bộ tích lũy, cập nhật, gộp và hoàn thiện.

Ví dụ:

```java
List<String> names = Stream.of("An", "Bình", "Chi")
    .collect(Collectors.toList());
```

Ta biết `T = String` và `R = List<String>`. Không nên giả định từ chữ ký rằng `A` chắc chắn là `ArrayList<String>`, hay kết quả là một `ArrayList` có thể sửa đổi. Javadoc của `Collectors.toList()` **không cam kết** loại collection, khả năng sửa đổi, khả năng tuần tự hóa hoặc tính an toàn luồng của danh sách trả về.

So sánh:

| Cách thu kết quả | Hợp đồng |
| --- | --- |
| `stream.toList()` (JDK 16+) | Danh sách không thể sửa đổi; không cam kết loại triển khai |
| `stream.collect(Collectors.toList())` | Không cam kết tính có thể sửa đổi và loại triển khai |
| `stream.collect(Collectors.toUnmodifiableList())` (JDK 10+) | Danh sách không thể sửa đổi; từ chối phần tử `null` |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Tạo một `ArrayList` mới theo supplier được chỉ định |

Lựa chọn phương thức dựa trên hợp đồng mong muốn, thay vì dựa vào loại `A` mà ta đoán bên trong.

## 6. Ví dụ đầy đủ: collector tùy chỉnh `Order → RevenueAccumulator → Summary`

Giả sử ứng dụng cần thống kê **số đơn** và **tổng doanh thu** trong một lần thu thập. Kết quả công khai sẽ là một `record Summary` bất biến; trạng thái trung gian dùng một object mutable để cộng dồn.

Sơ đồ:

```text
T = Order
    ├── Order("HN", 120_000)
    ├── Order("HCM", 80_000)
    └── Order("HN", 100_000)
             │
             ▼
A = RevenueAccumulator
    count = 3
    totalVnd = 300_000
             │  finisher
             ▼
R = Summary(count=3, totalVnd=300_000)
```

Mã hoàn chỉnh chạy với **JDK 17+**:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collector;

public class RevenueCollectorDemo {

    public record Order(String region, long amountVnd) {
        public Order {
            Objects.requireNonNull(region, "region");
            if (region.isBlank() || amountVnd < 0) {
                throw new IllegalArgumentException("Order không hợp lệ");
            }
        }
    }

    public record Summary(long count, long totalVnd) {}

    // A: trạng thái nội bộ; caller không cần biết class này.
    private static final class RevenueAccumulator {
        long count;
        long totalVnd;

        void add(Order order) {
            count = Math.addExact(count, 1L);
            totalVnd = Math.addExact(totalVnd, order.amountVnd());
        }

        RevenueAccumulator merge(RevenueAccumulator other) {
            count = Math.addExact(count, other.count);
            totalVnd = Math.addExact(totalVnd, other.totalVnd);
            return this;
        }

        Summary finish() {
            return new Summary(count, totalVnd);
        }
    }

    public static Collector<Order, ?, Summary> revenueCollector() {
        return Collector.of(
            RevenueAccumulator::new,  // Supplier<A>
            RevenueAccumulator::add,  // BiConsumer<A, Order>
            RevenueAccumulator::merge, // BinaryOperator<A>
            RevenueAccumulator::finish // Function<A, Summary>
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("HN", 120_000L),
            new Order("HCM", 80_000L),
            new Order("HN", 100_000L)
        );

        Summary sequential = orders.stream()
            .collect(revenueCollector());
        Summary parallel = orders.parallelStream()
            .collect(revenueCollector());

        System.out.println(sequential);
        // Summary[count=3, totalVnd=300000]
        System.out.println(parallel.equals(sequential)); // true

        Summary empty = List.<Order>of().stream()
            .collect(revenueCollector());
        System.out.println(empty);
        // Summary[count=0, totalVnd=0]
    }
}
```

### 6.1. Theo dõi chính xác `T`, `A`, `R`

| Thành phần | Kiểu trong ví dụ | Vai trò |
| --- | --- | --- |
| Phần tử nguồn | `Order` | `T` |
| `RevenueAccumulator::new` | `Supplier<RevenueAccumulator>` | Tạo `A` rỗng |
| `RevenueAccumulator::add` | `BiConsumer<RevenueAccumulator,Order>` | Cập nhật `A` bằng `T` |
| `RevenueAccumulator::merge` | `BinaryOperator<RevenueAccumulator>` | Gộp hai `A` |
| `RevenueAccumulator::finish` | `Function<RevenueAccumulator,Summary>` | Chuyển `A` thành `R` |
| Kết quả cuối | `Summary` | `R` |

Phương thức `revenueCollector()` có kiểu trả về công khai là `Collector<Order, ?, Summary>`. Dấu `?` giúp **giấu class `RevenueAccumulator` là chi tiết triển khai**, trong khi lời gọi `collect(revenueCollector())` vẫn được compiler kiểm tra kiểu và trả về `Summary`.

### 6.2. Vì sao trạng thái mutable ở đây vẫn phù hợp với `parallelStream`?

Ở collector trên, mỗi trạng thái `RevenueAccumulator` được tạo mới bằng supplier và được Stream framework quản lý. Collector **không khai báo `CONCURRENT`**, nên framework không được tích lũy đồng thời từ nhiều luồng lên **cùng một container `A`**. Các container riêng có thể được xử lý đồng thời, rồi combiner gộp chúng.

Điều đó khác với việc khai báo một biến mutable dùng chung và sửa nó ngay trong `map` hoặc `forEach`. Việc chia/gộp của collector là một phần của giao thức `collect`.

`Math.addExact` giúp phát hiện tràn `long`; do ví dụ chỉ nhận số tiền không âm, mọi tổng từng phần đều không vượt tổng thực của nguồn, và nếu tổng thực nằm trong miền `long` thì không có phép cộng từng phần hợp lệ nào tràn. Với nguồn có thể có số âm hoặc quy tắc làm tròn, cần xem xét thêm tính kết hợp và tính độc lập của kết quả đối với thứ tự gộp.

### 6.3. Vì sao không gắn `IDENTITY_FINISH`?

`RevenueAccumulator` và `Summary` là **hai kiểu khác nhau**; hàm `finish()` còn phải tạo một record. Việc gắn `IDENTITY_FINISH` sẽ nói sai hợp đồng, có thể cho phép framework bỏ qua finisher và dẫn tới kiểu kết quả không hợp lệ. Collector ở trên không truyền characteristic nào, nên finisher phải được dùng để tạo `Summary`.

## 7. Hai overload của `Collector.of`

`Collector.of` có hai dạng factory quan trọng:

**Dạng identity finish:**

```java
static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
)
```

Ở dạng này, **`A = R`**, và kết quả là chính container tích lũy theo hợp đồng identity finish. Factory khai báo `IDENTITY_FINISH` cho dạng này.

**Dạng có finisher riêng:**

```java
static <T, A, R> Collector<T, A, R> of(
    Supplier<A> supplier,
    BiConsumer<A, T> accumulator,
    BinaryOperator<A> combiner,
    Function<A, R> finisher,
    Collector.Characteristics... characteristics
)
```

Ở dạng thứ hai, `A` và `R` có thể khác nhau; phải cung cấp hàm hoàn thiện. Đây là overload được dùng trong ví dụ thống kê doanh thu.

Ví dụ tạo list có thể sửa đổi bằng overload đầu tiên:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Stream;

Collector<String, ArrayList<String>, ArrayList<String>> mutableListCollector =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );

ArrayList<String> names = Stream.of("An", "Bình")
    .collect(mutableListCollector);
names.add("Chi"); // Hợp lệ.
```

Ví dụ tạo danh sách bất biến bằng overload có finisher:

```java
Collector<String, ArrayList<String>, List<String>> immutableListCollector =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        List::copyOf
    );

List<String> immutableNames = Stream.of("An", "Bình")
    .collect(immutableListCollector);
// immutableNames.add("Chi"); // UnsupportedOperationException.
```

Trong ví dụ thứ hai `A = ArrayList<String>`, `R = List<String>`. Dù cả hai cùng chứa chuỗi, container tích lũy được phân biệt với kết quả cuối để caller không thể tiếp tục chỉnh sửa bằng các phương thức của danh sách mutable.

Với nghiệp vụ chỉ cần danh sách không thể sửa đổi, các API như `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` thường đơn giản hơn. Tự viết collector là hợp lý khi cần một phép tích lũy hoặc kiểu kết quả đặc biệt mà các collector chuẩn không mô tả tốt.

## 8. Đọc collector lồng trong `groupingBy`

Để hiểu generic của `groupingBy` có downstream collector, hãy xem chữ ký rút gọn:

```java
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)
```

Đọc các kiểu:

- `T`: phần tử đầu vào của **toàn bộ** pipeline.
- `K`: kiểu khóa nhóm do `classifier` tạo.
- `A`: trạng thái tích lũy **của downstream collector**.
- `D`: kết quả do downstream collector tạo ra **cho mỗi nhóm**.
- `Map<K,D>`: kiểu kết quả chung của collector grouping.
- `?` ở `Collector<T, ?, Map<K,D>>`: kiểu bộ tích lũy **của chính grouping collector** được che đi; không nhất thiết bằng `A` của downstream.

Ví dụ:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<RevenueCollectorDemo.Order> orders = List.of(
    new RevenueCollectorDemo.Order("HN", 120_000L),
    new RevenueCollectorDemo.Order("HCM", 80_000L),
    new RevenueCollectorDemo.Order("HN", 100_000L)
);

Map<String, Long> totals = orders.stream()
    .collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region,
        Collectors.summingLong(
            RevenueCollectorDemo.Order::amountVnd
        )
    ));

System.out.println(totals.get("HN"));  // 220000
System.out.println(totals.get("HCM")); // 80000
```

Ta suy ra `T = Order`, `K = String`, `D = Long`, nên kiểu trả về là `Map<String,Long>`. Không cần suy đoán collector đã dùng kiểu gì để lưu tổng tạm thời. Bên trong, grouping có thể quản lý một map gồm các **trạng thái downstream chưa hoàn thiện**, rồi hoàn thiện từng nhóm để tạo `Map<K,D>`.

Nếu cần kết quả `Map<String, List<Order>>`, không cung cấp downstream cũng được:

```java
Map<String, List<RevenueCollectorDemo.Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region
    ));
```

### 8.1. Kết hợp collector tùy chỉnh với grouping

Collector `revenueCollector()` ở mục 6 có đầu ra `Summary`, nên có thể tái sử dụng trực tiếp làm downstream:

```java
Map<String, RevenueCollectorDemo.Summary> summaryByRegion =
    orders.stream().collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region,
        RevenueCollectorDemo.revenueCollector()
    ));

System.out.println(summaryByRegion.get("HN"));
// Summary[count=2, totalVnd=220000]
```

Ví dụ này minh họa rõ **hai tầng tích lũy**: collector ngoài gom theo `K = String`; collector trong tích lũy các `Order` thành `Summary` của từng nhóm. Kiểu `A` của downstream không cần lộ ra ngoài.

### 8.2. `mapping`, `filtering` và `collectingAndThen`

Những factory khác cũng nhận downstream collector:

```java
// Rút gọn ý nghĩa:
Collectors.mapping(mapper, downstream)
Collectors.filtering(predicate, downstream) // JDK 9+
Collectors.collectingAndThen(downstream, finisher)
```

Ví dụ cần danh sách **số tiền** của từng vùng, thay vì danh sách nguyên đơn hàng:

```java
Map<String, List<Long>> amountsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region,
        Collectors.mapping(
            RevenueCollectorDemo.Order::amountVnd,
            Collectors.toList()
        )
    ));
```

`mapping` thay đổi dữ liệu đưa vào downstream: collector ngoài vẫn nhận `Order`, nhưng downstream lúc này nhận `Long`. Đây là tình huống rất dễ nhầm `T` của collector bên ngoài với kiểu phần tử sau mapper bên trong.

**Ranh giới cần nhớ:** `Collectors.filtering` khác `Stream.filter` khi đặt trong `groupingBy`. Lọc trước grouping có thể làm mất hoàn toàn một nhóm; downstream filtering có thể giữ khóa nhóm với một kết quả tích lũy rỗng nếu nhóm có phần tử nhưng không phần tử nào qua điều kiện downstream.

## 9. Khác biệt giữa hai overload `Stream.collect`

Ngoài overload nhận một `Collector`, `Stream<T>` còn có dạng ba tham số:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)
```

Ví dụ thu thập vào một `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

ArrayList<String> names = Stream.of("An", "Bình", "Chi")
    .collect(
        ArrayList::new,
        ArrayList::add,
        ArrayList::addAll
    );

System.out.println(names); // [An, Bình, Chi]
```

Với overload này, **kiểu container `R` là kết quả luôn**; không có tham số kiểu `A` hay finisher riêng. Hàm combiner có dạng `BiConsumer<R,R>` và trả `void`, khác `BinaryOperator<A>` của interface `Collector` trả một `A`.

So sánh:

| Phần | `collect(Collector)` | `collect(supplier, accumulator, combiner)` |
| --- | --- | --- |
| Input type | `T` | `T` |
| Accumulation type | `A` | `R` |
| Result type | `R` | `R` |
| Combiner | `BinaryOperator<A>` trả `A` | `BiConsumer<R,R>` trả `void` |
| Finisher | Có thể có `Function<A,R>` | Không có finisher riêng |
| Characteristics | Có thể khai báo qua collector | Không có tham số characteristics |
| Khi dùng | Collector chuẩn, collector tùy chỉnh, kết quả tổng hợp | Mutable reduction trực tiếp khi container chính là kết quả |

Các primitive stream như `IntStream` có overload `collect(supplier, ObjIntConsumer, combiner)` phù hợp với dữ liệu nguyên thủy. Chúng không cung cấp overload `collect(Collector<T,A,R>)` tương tự `Stream<T>`; khi cần dùng `Collectors` với wrapper, có thể chuyển bằng `boxed()` hoặc tạo object bằng `mapToObj`.

## 10. Ba đặc tính của collector

`Collector.Characteristics` cung cấp các đặc tính để Stream framework biết những tối ưu hóa nào **hợp lệ**. Không gắn đặc tính chỉ vì muốn tăng tốc.

| Đặc tính | Cam kết | Điều dễ hiểu sai |
| --- | --- | --- |
| `IDENTITY_FINISH` | Hàm finisher có thể bỏ qua; `A` có thể được sử dụng trực tiếp như `R` | Không phải chỉ cần `A` và `R` cùng tên kiểu |
| `UNORDERED` | Kết quả không phụ thuộc encounter order | Không đồng nghĩa phần tử nguồn đã được sắp xếp |
| `CONCURRENT` | Có thể gọi accumulator từ nhiều luồng trên **cùng container `A`** | Không thể gắn cho `ArrayList`/`HashMap` mutable thông thường mà không có cơ chế an toàn |

### 10.1. `IDENTITY_FINISH`

Ví dụ một collector tạo `ArrayList<String>` và trả đúng list tích lũy có thể có `IDENTITY_FINISH`. Với `RevenueAccumulator → Summary`, finisher tạo record mới nên **không** có đặc tính này.

Theo hợp đồng, nếu khai báo `IDENTITY_FINISH`, framework có thể thực hiện phép ép kiểu `A → R` mà không gọi finisher; khai báo sai có thể gây `ClassCastException` hoặc kết quả không đúng. `Collector.of(supplier, accumulator, combiner)` tự cung cấp đặc tính này.

### 10.2. `UNORDERED`

Ví dụ, tập hợp phần tử không trùng có thể không quan tâm đến thứ tự gặp phần tử, nên một collector kiểu `toSet` là unordered. Ngược lại, collector tạo danh sách theo thứ tự nguồn không nên khai báo `UNORDERED` nếu vị trí các phần tử là một phần của kết quả cần bảo đảm.

`UNORDERED` nói về **tính tương đương của kết quả collector**, không phải việc nguồn chắc chắn là unordered; kết quả `Map` vẫn không tự được cam kết thứ tự khóa.

### 10.3. `CONCURRENT`

Collector concurrent cho phép nhiều luồng cập nhật **cùng một trạng thái** theo hợp đồng của nó. Cơ chế tích lũy phải thật sự an toàn đồng thời. Ví dụ `Collectors.toConcurrentMap` hoặc `groupingByConcurrent` có hợp đồng riêng cần đọc kỹ.

Ngay cả khi collector có `CONCURRENT`, việc cùng tích lũy vào một container còn phụ thuộc stream có encounter order hay không và collector có `UNORDERED` hay không. Trong môi trường song song, framework có thể vẫn dùng nhiều trạng thái và gộp chúng theo cách phù hợp. Đừng dựa vào số lần supplier/combiner được gọi để xác định tính đúng.

## 11. Các luật đúng đắn của collector

Các luật được mô tả trong Javadoc `Collector`, đặc biệt quan trọng khi xử lý song song.

### 11.1. Identity

Với một trạng thái tích lũy `a`, gộp với một container rỗng mới từ supplier phải **tương đương** trạng thái ban đầu:

```text
combiner(a, supplier()) ≈ a
```

“Tương đương” không nhất thiết là cùng một tham chiếu object; điều cần giữ là kết quả có cùng ý nghĩa theo hợp đồng collector.

Ví dụ khi tổng hợp doanh thu: trạng thái rỗng có count và total bằng 0. Gộp với trạng thái rỗng không làm thay đổi hai giá trị đó.

### 11.2. Associativity

Việc chia đầu vào thành nhiều phần và gộp theo các cách khác nhau phải tạo **kết quả tương đương**:

```text
accumulate(all elements sequentially)
    ≈ combine(accumulate(left), accumulate(right))
```

Phép cộng số nguyên chính xác, phép đếm và phép hợp nhất nhóm được thiết kế phù hợp có thể đáp ứng yêu cầu này. Phép trừ thường **không kết hợp được**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Không dùng phép trừ làm combiner nếu yêu cầu kết quả bất biến theo cách chia/gộp. Với số thực `double`, phép cộng chịu sai số làm tròn và có thể khác nhau giữa các cách nhóm; khi cần tính toán chính xác hoặc kết quả tái lập tuyệt đối, hãy xác định chiến lược số học phù hợp.

### 11.3. Combiner phải phù hợp accumulator

Nếu accumulator chèn phần tử vào danh sách theo thứ tự, combiner cần gộp hai đoạn theo thứ tự tương ứng (trừ khi collector khai báo và thực sự bảo đảm `UNORDERED`).

Một phản ví dụ:

```java
// Sai về ý nghĩa: combiner bỏ mất container bên phải.
(left, right) -> left
```

Khi pipeline tuần tự tạo một container duy nhất, lỗi có thể không xuất hiện. Khi xử lý song song, dữ liệu ở các nhánh khác bị mất. Vì vậy, **thử chạy tuần tự thành công chưa chứng minh collector đúng**.

### 11.4. Ràng buộc về container và ownership

Một collector đúng không được phát tán các tham chiếu tích lũy mutable để các phần khác của chương trình sửa chúng trong lúc đang chạy. Sau khi một container được đưa vào combiner, việc dùng tiếp container ấy phải tuân theo ràng buộc của giao thức collector và cách framework quản lý nó.

`Supplier<A>` thường tạo container độc lập; `accumulator` và `combiner` phải chỉ thao tác trên trạng thái của collector, tránh phụ thuộc biến toàn cục hoặc sửa nguồn đang duyệt. Collector không khai báo `CONCURRENT` có thể hợp lệ khi chạy song song nhờ cơ chế phân tách container, **không đòi hỏi từng `A` tự an toàn luồng**.

## 12. Các phản mẫu quan trọng

### 12.1. Dùng `reduce` để sửa danh sách mutable

`reduce` phục vụ phép gộp thỏa luật kết hợp và không nên dùng accumulator mutable kiểu này:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

// Tránh: cùng identity List có thể bị chia sẻ khi giảm gọn song song.
List<String> wrong = Stream.of("A", "B", "C").reduce(
    new ArrayList<>(),
    (list, value) -> {
        list.add(value);
        return list;
    },
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);

// Đúng: dùng collect cho phép tích lũy mutable.
List<String> right = Stream.of("A", "B", "C")
    .collect(java.util.stream.Collectors.toList());
```

Đây là lỗi phân biệt giữa **immutable reduction** (`reduce`) và **mutable reduction** (`collect`). Với `reduce`, identity phải là giá trị trung hòa và accumulator/combiner tương thích, không dựa vào một object mutable có thể bị chia sẻ.

### 12.2. Supplier trả cùng một container dùng chung

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> shared = new ArrayList<>();

// Sai: mọi lời gọi supplier đều trả đúng đối tượng shared.
Collector<String, List<String>, List<String>> unsafe = Collector.of(
    () -> shared,
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

Collector này có nguy cơ trộn dữ liệu từ các lần chạy khác nhau, cập nhật đồng thời cùng list hoặc gộp một list với chính nó. Supplier phải tạo một vùng tích lũy mới theo đúng hợp đồng, ví dụ `ArrayList::new`.

### 12.3. Gắn `CONCURRENT` cho accumulator không an toàn

Một `ArrayList` thông thường không hỗ trợ nhiều luồng gọi `add` đồng thời trên cùng instance. Việc thêm `Collector.Characteristics.CONCURRENT` không biến nó thành thread-safe. Cần dùng cơ chế tích lũy phù hợp, hoặc để framework phân chia trạng thái rồi gộp mà **không** khai báo concurrent.

### 12.4. Quên xử lý nguồn rỗng, `null` và lỗi dữ liệu

`supplier()` phải cung cấp trạng thái cho phép thu thập nguồn rỗng. Trong ví dụ `RevenueCollectorDemo`, kết quả là `Summary(0,0)`; trong `groupingBy` thông thường là `Map` rỗng.

Đối với phần tử `null`, collector không tự có một chính sách chung: `ArrayList` có thể chứa `null`, `List.copyOf` và `Collectors.toUnmodifiableList` từ chối `null`, trong khi một classifier của `groupingBy` trả khóa `null` sẽ gây lỗi theo hợp đồng triển khai. Hãy xác định trước cần **từ chối, bỏ qua hay thay thế** dữ liệu thiếu. Đừng tự biến lỗi dữ liệu thành kết quả rỗng khiến báo cáo thiếu số liệu.

### 12.5. Gắn `UNORDERED` dù kết quả cần thứ tự

Nếu kết quả là danh sách biểu diễn lịch sử sự kiện, thứ tự có thể là thông tin nghiệp vụ. Gắn `UNORDERED` làm mất một ràng buộc quan trọng và có thể cho phép framework tạo kết quả khác yêu cầu. Chỉ khai báo khi các thứ tự gặp phần tử khác nhau đều cho kết quả tương đương.

## 13. Kiểm thử collector: nguồn rỗng, chia/gộp và song song

Các kiểm thử JUnit 5 dưới đây dùng lớp `RevenueCollectorDemo` ở mục 6. Chúng kiểm tra tính đúng đắn của kết quả, không phụ thuộc số lần gọi supplier/combiner:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class RevenueCollectorDemoTest {

    @Test
    void collectsCountAndSum() {
        List<RevenueCollectorDemo.Order> orders = List.of(
            new RevenueCollectorDemo.Order("HN", 120_000L),
            new RevenueCollectorDemo.Order("HCM", 80_000L),
            new RevenueCollectorDemo.Order("HN", 100_000L)
        );

        RevenueCollectorDemo.Summary actual = orders.stream()
            .collect(RevenueCollectorDemo.revenueCollector());

        assertEquals(
            new RevenueCollectorDemo.Summary(3L, 300_000L),
            actual
        );
    }

    @Test
    void emptyStreamReturnsNeutralSummary() {
        RevenueCollectorDemo.Summary actual =
            List.<RevenueCollectorDemo.Order>of().stream()
                .collect(RevenueCollectorDemo.revenueCollector());

        assertEquals(
            new RevenueCollectorDemo.Summary(0L, 0L),
            actual
        );
    }

    @Test
    void sequentialAndParallelResultsMatch() {
        List<RevenueCollectorDemo.Order> orders =
            java.util.stream.IntStream.range(0, 10_000)
                .mapToObj(i -> new RevenueCollectorDemo.Order(
                    i % 2 == 0 ? "HN" : "HCM", i
                ))
                .toList();

        RevenueCollectorDemo.Summary sequential = orders.stream()
            .collect(RevenueCollectorDemo.revenueCollector());
        RevenueCollectorDemo.Summary parallel = orders.parallelStream()
            .collect(RevenueCollectorDemo.revenueCollector());

        assertEquals(sequential, parallel);
        assertEquals(10_000L, parallel.count());
        assertEquals(49_995_000L, parallel.totalVnd());
    }

    @Test
    void reportsOverflowInsteadOfWrappingAround() {
        List<RevenueCollectorDemo.Order> orders = List.of(
            new RevenueCollectorDemo.Order("HN", Long.MAX_VALUE),
            new RevenueCollectorDemo.Order("HN", 1L)
        );

        assertThrows(ArithmeticException.class, () ->
            orders.stream().collect(
                RevenueCollectorDemo.revenueCollector()
            )
        );
    }

    @Test
    void rejectsInvalidOrder() {
        assertThrows(IllegalArgumentException.class, () ->
            new RevenueCollectorDemo.Order("HN", -1L)
        );
    }
}
```

Kiểm tra thêm các **luật gộp** khi tự viết collector phức tạp: chia một danh sách thành nhiều đoạn, tích lũy riêng và gộp theo các cấu trúc nhóm khác nhau, rồi so sánh kết quả cuối. Với collector có thứ tự, phải bảo toàn thứ tự mong đợi; với collector `UNORDERED`, so sánh theo tập hợp hoặc giá trị không phụ thuộc thứ tự.

## 14. Hiệu năng, tài nguyên và lựa chọn collector phù hợp

Collector không tự làm mọi pipeline nhanh hơn. Những quyết định sau ảnh hưởng đáng kể tới hiệu năng:

**Dung lượng `A`.** Collector tạo danh sách đầy đủ cần giữ nhiều phần tử trong bộ nhớ. Collector chỉ giữ count và sum có trạng thái nhỏ, thường phù hợp hơn nếu chỉ cần thống kê. Khi khối lượng dữ liệu rất lớn, cân nhắc đưa phép tổng hợp xuống hệ thống nguồn (ví dụ database) nếu đúng bài toán và mô hình dữ liệu.

**Chi phí finisher.** `List.copyOf` tạo hoặc chọn biểu diễn danh sách không thể sửa đổi, có thể cần thêm thời gian và bộ nhớ. Một finisher chuyển từ các map tạm thời sang DTO cũng tạo thêm công việc. Đổi lại, kết quả cuối có hợp đồng rõ và ít nguy cơ bị sửa ngoài ý muốn.

**Thứ tự và song song.** Collector cần giữ thứ tự đôi khi phải phối hợp/gộp kết quả theo thứ tự nguồn. `groupingByConcurrent` có thể hữu ích khi nghiệp vụ cho phép unordered accumulation, nhưng không tự bảo đảm thứ tự danh sách con. Đo trên dữ liệu thực trước khi chuyển sang `parallel()`.

**Tác dụng phụ.** Tránh gọi I/O, ghi log có ý nghĩa nghiệp vụ hoặc truy cập mạng từ accumulator/combiner. Một lần thu thập có thể tạo nhiều trạng thái và combiner được gọi theo cách khác giữa các phiên bản JVM hoặc cấu hình song song; những side effect bên ngoài có thể bị lặp hoặc chạy khác thứ tự dự kiến.

**Nguồn stream có tài nguyên.** `Files.lines(path)` và các stream liên quan I/O cần đóng bằng `try-with-resources`, dù terminal operation là `collect`. Ví dụ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> readNonBlankLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines
            .map(String::strip)
            .filter(s -> !s.isEmpty())
            .toList();
    }
}
```

Nếu dòng dữ liệu có thể quá lớn, việc `toList()` lưu toàn bộ dữ liệu cũng cần được cân nhắc; có thể thay bằng collector thống kê gọn hơn. Việc đóng nguồn I/O và quản lý bộ nhớ kết quả là **hai vấn đề độc lập**.

**Khi nào dùng collector chuẩn?** Với `toList`, `toSet`, `joining`, `counting`, `summingLong`, `groupingBy`, `partitioningBy`, `mapping`, `filtering` hoặc `collectingAndThen`, hãy ưu tiên API chuẩn nếu thể hiện đúng nghiệp vụ. Chỉ dùng `Collector.of` khi cần một trạng thái `A` và phép tổng hợp riêng.

## 15. Bài tập áp dụng

### Bài 1 — Xác định `T`, `A` và `R`

Với ba collector:

```java
Collectors.toList()
Collectors.counting()
Collectors.groupingBy(Order::region,
    Collectors.summingLong(Order::amountVnd))
```

Giả sử nguồn là `Stream<Order>`. Xác định `T`, `R`, và giải thích tại sao không nên suy đoán `A` chỉ từ kiểu kết quả. Phân biệt `A` của downstream và `A` bị che trong collector ngoài.

### Bài 2 — Gộp các trạng thái đếm

Thiết kế collector đếm số phần tử mà `T = String`, `A` là một object mutable chứa `long count` và `R = Long`. Viết supplier, accumulator, combiner, finisher. Kiểm thử nguồn rỗng và so sánh `stream()` với `parallelStream()`.

### Bài 3 — Kết quả bất biến

Viết `Collector<String, ArrayList<String>, List<String>>` sao cho finisher dùng `List.copyOf`. So sánh với overload `Collector.of` identity finish và với `Collectors.toList()`. Dự đoán chuyện gì xảy ra nếu input có `null`, rồi chọn chính sách xử lý.

### Bài 4 — Downstream collector

Dùng `groupingBy` để tạo `Map<String, Summary>` theo vùng từ ví dụ `RevenueCollectorDemo`. Xác định `K = String`, `D = Summary`, và vị trí `Collector<Order, ?, Summary>` được truyền vào. Thêm một vùng mới và kiểm tra kết quả.

### Bài 5 — Tìm lỗi combiner

Một collector có supplier tạo `ArrayList` mới, accumulator thêm phần tử, nhưng combiner trả nguyên `left` mà không gộp `right`. Hãy giải thích vì sao chạy tuần tự có thể “trông đúng” nhưng chạy song song có thể mất phần tử. Viết lại combiner và kiểm thử trên một danh sách lớn.

### Bài 6 — Tính trung bình an toàn với nguồn rỗng

Viết một collector tự giữ `count` và `sum` (kiểu số phù hợp), sau đó trả một kiểu kết quả có trạng thái rõ ràng: không có mẫu thì `OptionalDouble.empty()`, có mẫu thì trung bình. So sánh cách này với `Collectors.averagingLong` khi nghiệp vụ cần phân biệt “không có mẫu” và “trung bình bằng 0”.

### Bài 7 — Đặc tính nào là hợp lệ?

Với collector `RevenueAccumulator → Summary`, đánh giá có nên gắn `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT` không. Giải thích trên cơ sở **hợp đồng thực tế**, không dựa vào mong muốn tăng tốc.

## 16. Bảng ghi nhớ về `Collector<T, A, R>`

| Câu hỏi | Hướng suy luận |
| --- | --- |
| Phần tử stream đang là kiểu gì? | Đó là `T` |
| Collector tích lũy bằng cấu trúc nào? | Đó là `A` |
| `collect` phải trả kiểu gì? | Đó là `R` |
| Ai tạo trạng thái rỗng? | `supplier()` |
| Ai đưa một phần tử vào trạng thái? | `accumulator()` |
| Ai gộp các trạng thái khi chia pipeline? | `combiner()` |
| Ai biến trạng thái thành kết quả công khai? | `finisher()` |
| Khi nào `A` và `R` có thể dùng đồng nhất? | Khi hợp đồng thật sự đáp ứng `IDENTITY_FINISH` |
| Tại sao `Collector<T, ?, R>` có dấu `?`? | Kiểu trạng thái nội bộ được che khỏi người gọi |
| Khi nào collector dùng được với stream song song? | Supplier/accumulator/combiner tuân luật identity, associativity, ownership và characteristics |
| Collector thường dùng mặc định có phải concurrent không? | Không tự suy luận; xem `characteristics()` và hợp đồng |
| Cần nhóm dữ liệu theo khóa và gom mỗi nhóm? | `groupingBy(classifier, downstream)` |
| Chỉ cần tổng, count hoặc danh sách? | Ưu tiên collector chuẩn hoặc terminal operation tương ứng |

`Collector<T,A,R>` là hợp đồng nối **phần tử đầu vào** với **trạng thái tích lũy** và **kết quả cuối**. Đọc đúng ba kiểu này giúp bạn hiểu vì sao `collect` có thể tạo `Map`, DTO hay báo cáo từ một `Stream<Order>`, vì sao nhiều collector che `A` bằng wildcard, và vì sao combiner phải đúng khi chạy song song. Khi cần collector tùy chỉnh, hãy xác định rõ vòng đời trạng thái, luật gộp, cách xử lý nguồn rỗng và tính bất biến của kết quả trước khi tối ưu hiệu năng.
