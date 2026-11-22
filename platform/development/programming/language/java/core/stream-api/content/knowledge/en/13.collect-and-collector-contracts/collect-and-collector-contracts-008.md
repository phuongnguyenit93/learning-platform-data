# Triển khai Collector với trạng thái tích lũy và bước hoàn tất

Trong Java Stream API, `collect` giúp chuyển nhiều phần tử thành một kết quả như danh sách, bản đồ, báo cáo thống kê hoặc cấu trúc nghiệp vụ. Khi các collector dựng sẵn chưa biểu diễn trọn vẹn kết quả mong muốn, ta có thể tự triển khai một **`Collector<T, A, R>`** với hai kiểu cần phân biệt: **`A` là trạng thái tích lũy tạm thời có thể thay đổi**, còn **`R` là kết quả được trả về sau bước hoàn tất** (*finisher*).

Bài học thuộc chương **Cơ chế collect và Collector** của mô-đun **JAVA_STREAM_API**. Trọng tâm là thiết kế `supplier`, `accumulator`, `combiner` và `finisher` sao cho kết quả đúng với pipeline lazy, khi dữ liệu rỗng, khi chia xử lý song song và khi kết quả cần bất biến. Kiến thức này kết nối trực tiếp các thao tác `filter`, `map`, `reduce`, `collect`, `groupingBy`, collector tùy chỉnh và các ràng buộc về trạng thái, tài nguyên, hiệu năng; `Spliterator` và Stream Gatherers được nhắc đến để định vị giới hạn của collector.

## 1. Vì sao một collector cần trạng thái tích lũy?

Giả sử ứng dụng bán hàng cần tạo **một báo cáo** từ các đơn đã thanh toán, gồm:

- Tổng số đơn.
- Tổng doanh thu chính xác.
- Giá trị trung bình mỗi đơn, làm tròn hai chữ số thập phân.
- Danh sách mã đơn theo thứ tự xuất hiện trong nguồn.

Nếu chỉ dùng `Collectors.counting()`, ta nhận số lượng; nếu dùng `Collectors.summingLong(...)`, ta nhận tổng trong miền `long`; nếu dùng `toList()`, ta nhận danh sách. Bài toán muốn **một đối tượng kết quả duy nhất**, kết hợp nhiều đại lượng và xử lý riêng trường hợp không có đơn.

Một thiết kế tự nhiên là:

```text
Stream<Order>
     |
     | filter(Order::paid)
     v
Collector<Order, MutableState, SalesReport>
     |
     | supplier: tạo MutableState rỗng
     v
 MutableState (đếm, cộng tổng, lưu mã)
     | \
     |  \ combiner: gộp trạng thái của các phần đã xử lý
     v
 finisher: tạo SalesReport (bất biến, tính trung bình)
     |
     v
 SalesReport
```

Việc thêm phần tử vào một trạng thái tạm thời trong `collect` là bình thường. Điều quan trọng là **trạng thái đó do collector tạo và quản lý**, khác với việc cập nhật biến chung bên ngoài pipeline.

## 2. Hợp đồng `Collector<T, A, R>`

Giao diện `java.util.stream.Collector` được tham số hóa bởi ba kiểu:

| Kiểu | Vai trò | Trong ví dụ báo cáo |
| --- | --- | --- |
| `T` | Kiểu phần tử đi vào collector | `Order` |
| `A` | Kiểu container/trạng thái tích lũy | `MutableState` |
| `R` | Kiểu kết quả trả về | `SalesReport` |

Năm thành phần của một collector:

| Phương thức | Kiểu chức năng | Nhiệm vụ |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Tạo trạng thái tích lũy ban đầu, độc lập |
| `accumulator()` | `BiConsumer<A, T>` | Cập nhật trạng thái `A` với một phần tử `T` |
| `combiner()` | `BinaryOperator<A>` | Kết hợp hai trạng thái thành một trạng thái |
| `finisher()` | `Function<A, R>` | Chuyển trạng thái `A` thành kết quả `R` |
| `characteristics()` | `Set<Characteristics>` | Khai báo những bảo đảm bổ sung của collector |

Về ý nghĩa, xử lý tuần tự có thể hình dung:

```text
A state = supplier.get()
for each T element selected by the pipeline:
    accumulator.accept(state, element)
R result = finisher.apply(state)
```

Khi chạy song song, framework có thể tạo **nhiều trạng thái `A`** rồi dùng `combiner` hợp nhất trước khi hoàn tất:

```text
supplier → A1 → accumulator(items 1..k)   ┐
                                           ├─ combiner(A1, A2) → A → finisher → R
supplier → A2 → accumulator(items k+1..n) ┘
```

Đây là mô hình ngữ nghĩa để hiểu công việc; JVM có quyền thực hiện theo cách khác miễn tuân thủ hợp đồng của Stream và Collector. Không được giả định luôn có đúng hai nhánh, hoặc `combiner` luôn được gọi.

## 3. Bắt đầu bằng một collector nhỏ

Trước khi xây báo cáo nhiều trường, ta thử triển khai collector thu thập **các tên sản phẩm** vào một `ArrayList<String>`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class SimpleCollectorDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "Stream", "API");

        Collector<String, ArrayList<String>, List<String>> collector =
            Collector.of(
                ArrayList::new,                    // supplier
                ArrayList::add,                    // accumulator
                (left, right) -> {                 // combiner
                    left.addAll(right);
                    return left;
                },
                List::copyOf                       // finisher
            );

        List<String> result = names.stream().collect(collector);
        System.out.println(result); // [Java, Stream, API]
    }
}
```

Trong ví dụ:

1. `supplier` tạo danh sách tạm, lúc đầu rỗng.
2. `accumulator` thêm một tên vào danh sách đó.
3. `combiner` nối hai danh sách tạm. Nó hữu ích khi một pipeline bị chia thành nhiều phần.
4. `finisher` gọi `List.copyOf` để tạo danh sách **không thể sửa** làm kết quả.

Hai kiểu `A` và `R` cố ý khác nhau: `A = ArrayList<String>`, còn `R = List<String>`. Mặc dù `ArrayList` triển khai `List`, bước hoàn tất ở đây có công việc cụ thể là tạo bản sao bất biến. Vì vậy collector này **không** có đặc tính `IDENTITY_FINISH`.

Ví dụ này chủ yếu nhằm giải thích hợp đồng. Nếu chỉ cần một danh sách bất biến, dùng `stream.toList()` hoặc `Collectors.toUnmodifiableList()` thông thường ngắn hơn. Tự viết collector có ích khi bước tích lũy và hoàn tất thể hiện quy tắc nghiệp vụ riêng.

## 4. Ví dụ hoàn chỉnh: Collector cho báo cáo doanh thu

Ta triển khai một collector thực tế có hai giai đoạn:

- **Trong lúc duyệt:** đếm đơn, cộng tiền và lưu mã đơn vào một trạng thái tạm.
- **Sau khi kết thúc:** tạo bản báo cáo bất biến, tính trung bình; nếu không có đơn thì trung bình là `Optional.empty()`.

Ví dụ sau chạy trên **Java 17 trở lên**, vì dùng `record` và các API có sẵn trên phiên bản này.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CustomSalesCollectorDemo {

    record Order(String id, String region, long amountVnd, boolean paid) {}

    record SalesReport(
        long count,
        BigInteger totalVnd,
        Optional<BigDecimal> averageVnd,
        List<String> orderIds
    ) {}

    // A: chỉ dùng nội bộ để tích lũy, có trạng thái thay đổi được.
    static final class MutableState {
        private long count = 0L;
        private BigInteger total = BigInteger.ZERO;
        private final List<String> ids = new ArrayList<>();

        void add(Order order) {
            count = Math.addExact(count, 1L);
            total = total.add(BigInteger.valueOf(order.amountVnd()));
            ids.add(order.id());
        }

        MutableState merge(MutableState other) {
            count = Math.addExact(count, other.count);
            total = total.add(other.total);
            ids.addAll(other.ids);
            return this;
        }

        SalesReport finish() {
            Optional<BigDecimal> average = count == 0
                ? Optional.empty()
                : Optional.of(new BigDecimal(total).divide(
                    BigDecimal.valueOf(count),
                    2,
                    RoundingMode.HALF_UP
                ));

            return new SalesReport(
                count,
                total,
                average,
                List.copyOf(ids)
            );
        }
    }

    static Collector<Order, MutableState, SalesReport> salesCollector() {
        return Collector.of(
            MutableState::new,     // Supplier<MutableState>
            MutableState::add,     // BiConsumer<MutableState, Order>
            MutableState::merge,   // BinaryOperator<MutableState>
            MutableState::finish   // Function<MutableState, SalesReport>
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc", 120_000L, true),
            new Order("O-02", "Nam",  50_000L, false),
            new Order("O-03", "Bắc", 200_000L, true),
            new Order("O-04", "Nam",  30_000L, true)
        );

        SalesReport report = orders.stream()
            .filter(Order::paid)
            .collect(salesCollector());

        System.out.println(report.count());        // 3
        System.out.println(report.totalVnd());     // 350000
        System.out.println(report.averageVnd());   // Optional[116666.67]
        System.out.println(report.orderIds());     // [O-01, O-03, O-04]

        SalesReport noOrders = Stream.<Order>empty()
            .collect(salesCollector());

        System.out.println(noOrders.count());       // 0
        System.out.println(noOrders.totalVnd());    // 0
        System.out.println(noOrders.averageVnd());  // Optional.empty
        System.out.println(noOrders.orderIds());    // []
    }
}
```

### Vì sao ví dụ chọn các kiểu này?

- `Order.amountVnd` là `long` để minh họa tiền theo đơn vị VND nguyên; dữ liệu đầu vào phải có quy tắc bảo đảm giá trị đúng và phù hợp nghiệp vụ.
- `MutableState.total` dùng `BigInteger` để **không tràn miền `long` trong phép cộng tổng**. Nếu tất cả số đầu vào đã được lưu vào `long`, điều đó không tự giải quyết lỗi xảy ra trước khi tạo `Order`.
- `MutableState.count` là `long` và dùng `Math.addExact` để phát hiện một phép đếm vượt 64 bit.
- `SalesReport.averageVnd` là `Optional<BigDecimal>`: có thể biểu diễn rõ tình huống **không có mẫu**. Bước chia đặt `scale = 2` và `RoundingMode.HALF_UP` để minh họa quy tắc làm tròn của báo cáo; nghiệp vụ thực tế cần xác định quy tắc này.
- `SalesReport.orderIds` nhận `List.copyOf(ids)` để không làm lộ danh sách đang thay đổi ở bộ tích lũy. Ví dụ giả định các mã đơn không null; nếu dữ liệu không bảo đảm, cần xác thực trước.

Ở đây, `filter(Order::paid)` xử lý chọn đơn **trước** khi collector tích lũy. Collector chỉ nhìn thấy các đơn đã lọc; các toán tử trung gian vẫn được đánh giá lazy cho đến khi terminal operation `collect` được gọi.

## 5. Phân tích bốn bước triển khai

### 5.1. `supplier`: tạo trạng thái mới, độc lập

```java
MutableState::new
```

Supplier phải tạo trạng thái phù hợp làm điểm bắt đầu cho quá trình tích lũy. Với ví dụ, trạng thái rỗng có:

```text
count = 0
total = BigInteger.ZERO
ids = []
```

Điều quan trọng là **mỗi lần gọi tạo một instance độc lập**. Không dùng một `MutableState` toàn cục làm trạng thái cho mọi pipeline, vì nhiều phép `collect` có thể chạy đồng thời hoặc song song.

Ví dụ thiết kế sai:

```java
// Không nên dùng làm supplier:
MutableState shared = new MutableState();

// () -> shared  // Các lượt collect có thể sửa cùng một object!
```

Mỗi `collect(salesCollector())` cần tự tích lũy kết quả của chính nó. Supplier không được âm thầm chia sẻ danh sách hoặc map có thể thay đổi giữa các lần thu thập.

### 5.2. `accumulator`: thêm một phần tử vào một trạng thái

Trong ví dụ:

```java
void add(Order order) {
    count = Math.addExact(count, 1L);
    total = total.add(BigInteger.valueOf(order.amountVnd()));
    ids.add(order.id());
}
```

Accumulator cập nhật **`MutableState` được framework cung cấp** cho nó. Chức năng này khác với `Stream.reduce` hai tham số, nơi phép giảm thường tạo một giá trị kết hợp mới thông qua `BinaryOperator<T>`.

Với `Collector`, việc cập nhật `ArrayList` hoặc `HashMap` bên trong trạng thái là hợp lệ, miễn là tuân thủ hợp đồng về thread confinement và kết hợp. Không sửa nguồn Stream, không ghi vào biến toàn cục, và không yêu cầu accumulator phải được gọi theo lịch trình cụ thể.

### 5.3. `combiner`: gộp hai trạng thái

```java
MutableState merge(MutableState other) {
    count = Math.addExact(count, other.count);
    total = total.add(other.total);
    ids.addAll(other.ids);
    return this;
}
```

Combiner của ví dụ **đột biến trạng thái bên trái**, hợp nhất trạng thái bên phải rồi trả về bên trái. Đây là một chiến lược hợp lệ nếu hai trạng thái do collector quản lý và không được truy cập đồng thời theo cách vi phạm hợp đồng.

Ví dụ minh họa một cách chia:

```text
Nhánh 1: (count = 1, total = 120000, ids = [O-01])
Nhánh 2: (count = 2, total = 230000, ids = [O-03, O-04])

merge(nhánh 1, nhánh 2)
       |
       v
(count = 3, total = 350000, ids = [O-01, O-03, O-04])
```

Với nguồn có thứ tự và collector không khai báo `UNORDERED`, phải thiết kế combiner để giữ ngữ nghĩa thứ tự của kết quả. `ids.addAll(other.ids)` ghép phần bên trái trước phần bên phải, phù hợp với việc bảo toàn thứ tự gặp theo trình tự các phần được kết hợp.

### 5.4. `finisher`: chuyển từ trạng thái tạm sang kết quả công khai

```java
SalesReport finish() {
    Optional<BigDecimal> average = count == 0
        ? Optional.empty()
        : Optional.of(new BigDecimal(total).divide(
            BigDecimal.valueOf(count), 2, RoundingMode.HALF_UP
        ));

    return new SalesReport(count, total, average, List.copyOf(ids));
}
```

Finisher **không xử lý thêm một phần tử nguồn**; nó chạy trên trạng thái đã tích lũy. Trong ví dụ, bước này có ba vai trò:

1. Tính một giá trị dẫn xuất (trung bình).
2. Thể hiện trường hợp rỗng bằng `Optional.empty()`.
3. Tạo kết quả không còn cho phép cập nhật danh sách mã đơn qua tham chiếu từ bên ngoài.

Vì `SalesReport` khác `MutableState`, collector này **cần thực hiện finisher**; không được đánh dấu `IDENTITY_FINISH`. Mặc dù `record` chỉ giữ các trường `final`, tính bất biến sâu còn phụ thuộc kiểu trường; `BigInteger`, `BigDecimal`, `Optional` và bản sao `List.copyOf` giúp ví dụ tránh để lộ trạng thái có thể thay đổi.

## 6. Hợp đồng tính đúng: identity và associativity

Để collector đưa ra kết quả tương đương giữa cách duyệt tuần tự và cách chia nhóm hợp lệ, ba thao tác chính phải tương thích.

### 6.1. Trạng thái rỗng phải là phần tử trung hòa khi kết hợp

Gọi `e = supplier.get()` là một trạng thái mới rỗng. Khi `a` đã chứa dữ liệu, kết hợp với một trạng thái rỗng phải cho kết quả tương đương `a` sau finisher:

```text
finish(combine(a, e))  ≡  finish(a)
```

Ký hiệu `≡` nghĩa là **tương đương theo quan sát của người dùng**, không bắt buộc là cùng một object trong bộ nhớ. Với `MutableState` ở trên, gộp một trạng thái đếm 0, tổng 0 và danh sách rỗng không thay đổi kết quả.

Một sai lầm điển hình là để `supplier` khởi tạo `count = 1` hoặc `total = 100` vì muốn cộng một phụ phí; nếu nhiều trạng thái được tạo, phụ phí ấy có thể bị tính nhiều lần. Phụ phí áp dụng **một lần cho báo cáo cuối** nên được đưa vào finisher hoặc xử lý sau `collect`, theo đúng yêu cầu nghiệp vụ.

### 6.2. Ghép các phần theo các nhóm khác nhau phải tương đương

Giả sử dữ liệu được chia thành ba phần `A`, `B` và `C`. Khi ghép:

```text
combine(combine(A, B), C)
          ≡
combine(A, combine(B, C))
```

Đối với trạng thái đếm, tổng và chuỗi danh sách có thứ tự, các phép cộng và phép nối danh sách đáp ứng nguyên tắc này theo ngữ nghĩa đã chọn, nếu các giá trị không rơi vào trường hợp tràn ngoài dự kiến.

Chọn accumulator và combiner sao cho việc **tích lũy trên các phần rồi gộp** tương đương với việc **tích lũy toàn bộ theo thứ tự gặp**. Đây là điều kiện cốt lõi để kết quả không phụ thuộc vào cách chia nguồn bởi `Spliterator`.

### 6.3. Accumulator và combiner phải cùng diễn đạt một phép tổng hợp

Nếu accumulator tăng `count` mỗi khi gặp một đơn, combiner phải cộng hai giá trị `count`. Nếu accumulator nối thêm mã đơn, combiner cũng phải nối mã đơn từ hai trạng thái. Chỉ cộng tổng tiền mà quên ghép mã đơn trong combiner có thể khiến báo cáo đúng ở chế độ tuần tự nhưng thiếu mã ở chế độ song song.

Không lưu những đại lượng có thể tính từ các đại lượng khác nếu điều đó khiến trạng thái khó giữ nhất quán. Ví dụ tính trung bình trong finisher từ `total / count` dễ kết hợp hơn việc duy trì một “trung bình đang chạy” và cố lấy trung bình của hai nhánh một cách không có trọng số.

## 7. `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT`

`Collector.Characteristics` là những **cam kết về hành vi**, không phải tùy chọn bật để tăng tốc vô điều kiện.

| Đặc tính | Ý nghĩa | Khi nào có thể khai báo |
| --- | --- | --- |
| `IDENTITY_FINISH` | Bước hoàn tất có thể được bỏ qua với phép chuyển kiểu không kiểm tra từ `A` sang `R` | Kết quả thực sự chính là trạng thái tích lũy theo hợp đồng; không cần tạo bản sao, bất biến hóa hay tính thêm trường |
| `UNORDERED` | Kết quả không phụ thuộc thứ tự gặp của phần tử nguồn | Thứ tự không mang ý nghĩa nghiệp vụ, ví dụ một tập hợp mà chỉ quan tâm thành viên |
| `CONCURRENT` | Accumulator cho phép các luồng khác nhau gọi đồng thời trên **cùng một trạng thái** | Cấu trúc tích lũy và mọi thao tác cập nhật trong accumulator đều an toàn khi thực hiện đồng thời |

### 7.1. Khi nào có `IDENTITY_FINISH`?

Overload của `Collector.of` không nhận finisher:

```java
public static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
)
```

Theo hợp đồng của overload này, kết quả `R` chính là container tích lũy, và đặc tính `IDENTITY_FINISH` được cung cấp. Ví dụ:

```java
import java.util.ArrayList;
import java.util.stream.Collector;

// Order là record ở ví dụ hoàn chỉnh.
Collector<Order, ArrayList<String>, ArrayList<String>> idsCollector =
    Collector.of(
        ArrayList::new,
        (ids, order) -> ids.add(order.id()),
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Kết quả thu được là `ArrayList<String>` có thể thay đổi. Không khai báo `IDENTITY_FINISH` cho collector dùng `List.copyOf` ở finisher, vì việc bỏ qua finisher sẽ làm thay đổi tính chất của kết quả.

### 7.2. Khi nào có `UNORDERED`?

Báo cáo trong ví dụ giữ một danh sách `orderIds`, do đó **thứ tự mã đơn có ý nghĩa** và collector không khai báo `UNORDERED`. Nếu bài toán chỉ tính tổng/số lượng và hoàn toàn không cần thứ tự, có thể thiết kế collector không phụ thuộc thứ tự rồi khai báo đặc tính đó.

Việc khai báo `UNORDERED` có thể cho phép framework bỏ yêu cầu duy trì thứ tự gặp. Nó không có nghĩa kết quả sẽ ngẫu nhiên trong mọi lần chạy, và cũng không bảo đảm tốc độ tăng.

### 7.3. Khi nào có `CONCURRENT`?

Dùng `ArrayList.add` hoặc cập nhật biến `long count` bằng phép cộng thông thường trên cùng một container **không an toàn khi nhiều luồng cùng cập nhật**. Vì vậy collector `salesCollector()` **không khai báo `CONCURRENT`**.

Không cần `CONCURRENT` để collector chạy trong parallel Stream: với collector không concurrent, framework có thể tạo nhiều container riêng cho các nhánh, sau đó gộp bằng combiner. Nếu một collector khai báo `CONCURRENT`, framework chỉ có thể thực hiện tích lũy đồng thời thực sự trên cùng container khi điều kiện về thứ tự cũng cho phép, chẳng hạn nguồn không có thứ tự hoặc collector có `UNORDERED`.

Không thêm `CONCURRENT` chỉ vì một trường trong container dùng `ConcurrentHashMap`; **mọi cập nhật liên quan** đến count, total, danh sách, tính nhất quán giữa các trường và finisher đều phải đáp ứng hợp đồng tương ứng.

## 8. Kết hợp collector tùy chỉnh với `groupingBy`

Collector đã xây có thể làm **downstream collector** cho `Collectors.groupingBy`. Khi đó mỗi nhóm nhận một quá trình tích lũy riêng, và mỗi nhóm được chuyển thành một `SalesReport` ở finisher.

Giả sử sử dụng lại `Order`, `SalesReport` và `salesCollector()` trong lớp ví dụ hoàn chỉnh:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, SalesReport> reportByRegion = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        salesCollector()
    ));

System.out.println(reportByRegion.get("Bắc").totalVnd()); // 320000
System.out.println(reportByRegion.get("Nam").totalVnd()); // 30000
```

Ở đây, `groupingBy` chịu trách nhiệm phân phối phần tử theo `region`; `salesCollector` chịu trách nhiệm tạo báo cáo từng nhóm. Không nên đưa `region` vào chính `MutableState` chỉ để giải quyết nhu cầu nhóm, vì collector sẽ mất khả năng tái sử dụng cho nguồn không nhóm.

**Trường hợp cần chú ý:** một vùng không có đơn đã thanh toán thường **không xuất hiện như một khóa** trong kết quả `groupingBy`, vì không có phần tử nào đi vào nhóm đó. Khác với việc gọi `salesCollector()` trên Stream rỗng để nhận `SalesReport` rỗng, `groupingBy` không tự tạo khóa cho những nhóm vắng mặt. Nếu báo cáo yêu cầu mọi vùng đều xuất hiện, cần bổ sung danh sách vùng từ nguồn nghiệp vụ.

## 9. So sánh với `collect` ba tham số và collector dựng sẵn

`Stream.collect` có cả overload nhận một `Collector`:

```java
R collect(Collector<? super T, A, R> collector)
```

và overload nhận ba hàm:

```java
R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)
```

Ví dụ thu mã đơn vào một `ArrayList` bằng overload ba tham số:

```java
import java.util.ArrayList;
import java.util.List;

ArrayList<String> ids = orders.stream()
    .collect(
        ArrayList::new,
        (result, order) -> result.add(order.id()),
        ArrayList::addAll
    );
```

Ở đây, container tích lũy và kết quả đều là `ArrayList<String>`. Overload này **không có tham số finisher** để tạo ra `SalesReport` khác kiểu. Nếu cần xử lý cuối, có thể làm sau lời gọi `collect`, hoặc định nghĩa `Collector<T, A, R>`.

Khi kết quả chỉ cần chuẩn hóa từ collector có sẵn, `Collectors.collectingAndThen` thường giúp tránh tự viết toàn bộ hợp đồng:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> immutableIds = orders.stream()
    .map(Order::id)
    .collect(Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    ));
```

`collectingAndThen` bổ sung finisher cho một collector khác. Khi mục tiêu chỉ là danh sách bất biến, `Stream.toList()` trên Java 16+ thường còn ngắn hơn. Hãy ưu tiên collector dựng sẵn nếu nó biểu diễn đủ nghiệp vụ, còn `Collector.of` hữu ích khi cần trạng thái nhiều trường và bước hoàn tất riêng.

| Mục tiêu | Công cụ thường phù hợp |
| --- | --- |
| Tạo danh sách | `toList()`, `Collectors.toList()` hoặc `toCollection(...)` theo yêu cầu tính mutable |
| Ghép chuỗi có dấu phân cách | `Collectors.joining(delimiter)` |
| Gom nhóm theo khóa | `Collectors.groupingBy(classifier, downstream)` |
| Tạo kết quả bất biến sau collector có sẵn | `Collectors.collectingAndThen(...)` |
| Tính tổng đơn giản | `IntStream.sum()`, `LongStream.sum()`, `summingLong(...)` |
| Tạo báo cáo nhiều trường và có bước hoàn tất nghiệp vụ | `Collector.of(supplier, accumulator, combiner, finisher)` |

## 10. Collector với Stream rỗng

Với nguồn rỗng, collector vẫn có thể tạo kết quả hợp lệ thông qua trạng thái từ supplier và phép hoàn tất:

```text
Stream rỗng
    ↓
supplier() → MutableState(count=0, total=0, ids=[])
    ↓
finisher() → SalesReport(0, 0, Optional.empty(), [])
```

Ví dụ trong mục 4 đã thể hiện tình huống này. Lựa chọn `Optional.empty()` cho trung bình giúp phân biệt **không có đơn** với **trung bình bằng 0 VND** của một tập đơn có dữ liệu.

Mỗi loại collector có cách diễn giải dữ liệu rỗng khác nhau. `Collectors.toList()` trả danh sách rỗng, `Collectors.counting()` trả `0L`, nhưng các phép tìm cực trị thường dùng `Optional` để biểu diễn thiếu dữ liệu. Nếu muốn kết quả ba trạng thái như `NO_DATA`, `PASS`, `FAIL`, hãy diễn đạt rõ bằng loại kết quả `R` phù hợp, thay vì cố gán nghĩa cho một số 0 hoặc giá trị boolean.

Không được giả định accumulator nhất thiết được gọi trên Stream rỗng; không có phần tử nào để gọi. Bước hoàn tất phải xử lý được container ở trạng thái ban đầu.

## 11. Những lỗi thiết kế dễ gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Supplier trả lại cùng một `ArrayList` được giữ toàn cục | Các lần thu thập chia sẻ dữ liệu, dễ lẫn kết quả | Mỗi lời gọi supplier tạo một container mới |
| Accumulator cập nhật biến static hoặc nguồn Stream | Tác dụng phụ, kết quả không ổn định, dễ race condition | Chỉ thay đổi container do collector quản lý |
| Combiner bỏ qua `count` hoặc `ids` | Song song cho kết quả thiếu/sai | Gộp đầy đủ từng thành phần trạng thái |
| Combiner không giữ đúng thứ tự kết quả có thứ tự | `orderIds` sai thứ tự gặp | Ghép phần trái trước phần phải khi ngữ nghĩa yêu cầu |
| Tính trung bình bằng trung bình cộng của hai nhánh | Sai nếu hai nhánh có số lượng khác nhau | Gộp `total` và `count` rồi chia trong finisher |
| Đánh dấu `IDENTITY_FINISH` dù finisher tạo bản sao bất biến | Framework có thể bỏ qua bước bất biến hóa | Chỉ khai báo khi chuyển `A` sang `R` thực sự là identity |
| Đánh dấu `CONCURRENT` nhưng cập nhật `ArrayList`, `long` chung | Mất dữ liệu hoặc kết quả sai khi tích lũy đồng thời | Bỏ flag hoặc thiết kế bộ tích lũy concurrent đúng hợp đồng |
| Đánh dấu `UNORDERED` trong collector tạo danh sách theo thứ tự | Có thể mất bảo đảm về thứ tự gặp | Không khai báo `UNORDERED` khi thứ tự mang ý nghĩa |
| Finisher trả trực tiếp danh sách mutable nội bộ nhưng quảng bá là bất biến | Bên gọi có thể thay đổi nội dung báo cáo | Dùng bản sao như `List.copyOf`, kiểm tra null |
| Không xử lý nguồn rỗng trước phép chia trung bình | Chia cho 0 hoặc giá trị vô nghĩa | Kiểm tra `count == 0` và chọn kiểu kết quả phù hợp |
| Gọi `collect` rồi sử dụng lại cùng Stream | Stream chỉ được tiêu thụ một lần | Tạo Stream mới từ nguồn |
| Dùng collector có mutable state rồi nghĩ phải luôn bật `parallel()` | Tăng overhead hoặc tạo lỗi nếu hợp đồng sai | Xác minh tính đúng trước, đo hiệu năng sau |

## 12. Hiệu năng, tài nguyên và xử lý song song

### 12.1. Giữ trạng thái nhỏ nhất cần thiết

Collector chỉ tính tổng và số lượng thường cần hai trường. Trong báo cáo mẫu, việc giữ `orderIds` có chi phí bộ nhớ tỷ lệ với **số đơn được giữ**. Nếu kết quả không yêu cầu danh sách mã, hãy loại trường đó để giảm bộ nhớ.

`List.copyOf(ids)` trong finisher còn tạo một kết quả độc lập với danh sách tích lũy. Chi phí này là sự đánh đổi có chủ đích cho việc không để lộ trạng thái nội bộ.

### 12.2. Phân biệt chi phí cộng số và chi phí tạo đối tượng

`BigInteger` dùng để giữ tổng số nguyên chính xác khi tổng có thể vượt `long`. Với bài toán có giới hạn rõ và an toàn trong `long`, một collector dùng `long` hoặc `Collectors.summingLong` có thể đơn giản và ít cấp phát hơn. Đừng dùng `BigInteger` hoặc collector tùy chỉnh chỉ vì chúng trông linh hoạt.

Trên đường chạy quan trọng, hãy đo cả **thời gian, cấp phát và bộ nhớ** bằng dữ liệu đại diện, chẳng hạn sử dụng JMH. Pipeline song song có chi phí chia nguồn qua `Spliterator`, tạo nhiều container và kết hợp chúng; một combiner nối các `ArrayList` lớn cũng có thể tạo chi phí đáng kể.

### 12.3. Parallel Stream và thứ tự

`parallelStream().collect(salesCollector())` có thể hoạt động đúng vì collector tạo container cho các phần xử lý, và combiner gộp các container. Việc collector không mang cờ `CONCURRENT` **không ngăn** Stream song song chạy.

Nhưng song song không nhất thiết nhanh hơn. Đừng đo dựa trên vài phần tử rồi suy rộng cho hàng triệu phần tử. Nếu cần danh sách mã đơn theo thứ tự nguồn, việc duy trì thứ tự cũng ảnh hưởng chi phí xử lý.

### 12.4. Nguồn có tài nguyên cần đóng

Với `Files.lines(path)` hoặc Stream từ nguồn I/O, cần đóng tài nguyên bằng `try-with-resources`. Bản thân collector không tự đóng Stream nguồn:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Đặt trong phương thức khai báo throws IOException hoặc xử lý ngoại lệ.
Path logFile = Path.of("app.log");

try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
    long errorCount = lines
        .filter(line -> line.contains("ERROR"))
        .collect(Collectors.counting());

    System.out.println(errorCount);
}
```

Nếu accumulator hoặc finisher có thể ném ngoại lệ, cần xác định quy tắc xử lý lỗi ở tầng ứng dụng; ví dụ `Math.addExact` trong mã mẫu ném `ArithmeticException` nếu đếm vượt `long`. Không nên dùng ngoại lệ như một cách “chuyển nghĩa” âm thầm thành báo cáo thành công.

## 13. Collector không thay thế mọi phép biến đổi có trạng thái

Collector được áp dụng **ở cuối pipeline** để biến luồng phần tử thành **một kết quả**. Nếu cần tạo một giá trị đầu ra sau *mỗi* phần tử, ví dụ số dư chạy theo thời gian, một collector cuối có thể lưu toàn bộ diễn tiến vào danh sách, nhưng điều đó không tương đương với một thao tác trung gian phát từng kết quả.

Bài toán phát các kết quả trạng thái giữa pipeline có thể phù hợp với vòng lặp, thiết kế một `Spliterator` chuyên biệt hoặc Stream Gatherers trên các JDK hỗ trợ. Các kỹ thuật đó giải quyết nhu cầu khác với một collector thông thường.

Trong khuôn khổ bài này, hãy tập trung vào hợp đồng `Collector<T,A,R>`: **chỉ dùng mutable state khi nó có chủ sở hữu rõ ràng, kết hợp được và được hoàn tất thành đúng kiểu kết quả**.

## 14. Bài tập thực hành

### Bài 1: Collector đếm và tính tổng điểm

Cho `record Student(String name, int score)`. Tạo `Collector<Student, A, Report>` trả về `Report(count, sum, average)`. Dùng trạng thái `long count`, `long sum`; finisher trả về trung bình `OptionalDouble` khi không có sinh viên. Viết ví dụ với đầu vào rỗng và một sinh viên.

### Bài 2: Xác minh combiner

Với các đơn đã thanh toán, chia dữ liệu thành hai danh sách. Tích lũy từng danh sách vào hai `MutableState`, gọi `merge`, rồi đối chiếu với một lượt `collect(salesCollector())` trên danh sách đầy đủ. Vì sao phải gộp **cả số đơn, tiền và mã đơn**?

### Bài 3: Chỉ tạo danh sách bất biến

Viết `Collector<String, ArrayList<String>, List<String>>` bằng `Collector.of`, có finisher `List.copyOf`. Thử gọi `result.add("X")` sau khi thu thập và giải thích kết quả. Có được khai báo `IDENTITY_FINISH` không?

### Bài 4: Tính trung bình sai khi gộp nhánh

Nhánh thứ nhất có một đơn giá trị 100, nhánh thứ hai có ba đơn giá trị 200, 300, 400. Nếu tính trung bình từng nhánh rồi lấy trung bình của hai giá trị đó, kết quả có đúng không? Hãy tính bằng `total/count` sau khi gộp.

### Bài 5: Nhóm báo cáo theo khu vực

Mở rộng ví dụ doanh thu thành `Map<String, SalesReport>` theo `region` với `Collectors.groupingBy(Order::region, salesCollector())`. Thử một khu vực hoàn toàn không có đơn thanh toán. Vì sao khu vực đó không xuất hiện như một khóa?

### Bài 6: Đánh giá đặc tính Collector

Với ba collector sau, hãy nêu có thể khai báo `IDENTITY_FINISH`, `UNORDERED` hay `CONCURRENT` không và vì sao:

1. Collector xây `ArrayList<String>` và trả nguyên container.
2. Collector tạo danh sách mã đơn có thứ tự, finisher tạo `List.copyOf`.
3. Collector gom phần tử vào cấu trúc đồng thời, trong đó phép cập nhật mọi trường đều được chứng minh thread-safe và kết quả không phụ thuộc thứ tự.

### Bài 7: Chọn giữa collector dựng sẵn và collector tùy chỉnh

Giải quyết ba yêu cầu: ghép các chuỗi bằng dấu phẩy, đếm số phần tử theo nhóm, tạo báo cáo có tổng, số lượng và trung bình sau làm tròn. Chọn giữa `Collectors.joining`, `groupingBy`, `counting`, `collectingAndThen` và `Collector.of`. Giải thích vì sao chỉ nên tự viết hợp đồng khi nó giúp biểu diễn được yêu cầu khó thể hiện bằng các collector sẵn có.

## 15. Tự kiểm tra kiến thức

- Ba tham số `T`, `A` và `R` của `Collector<T,A,R>` khác nhau thế nào?
- Vai trò của `supplier`, `accumulator`, `combiner` và `finisher` là gì?
- Vì sao supplier không nên trả về một trạng thái dùng chung giữa nhiều lần thu thập?
- Tại sao tính trung bình nên thực hiện sau khi gộp tổng và số lượng?
- Khi nào được đánh dấu `IDENTITY_FINISH`, và vì sao `List.copyOf` làm thay đổi câu trả lời?
- Collector không mang đặc tính `CONCURRENT` có dùng được với `parallelStream()` không?
- Khi nào khai báo `UNORDERED` sẽ vi phạm yêu cầu nghiệp vụ?
- Vì sao kết quả `groupingBy` không tự có khóa cho một nhóm không xuất hiện?
- Trường hợp nào nên dùng `Collectors.collectingAndThen` thay vì tự triển khai `Collector.of`?
- Vì sao việc dùng `collect` để xây báo cáo không đồng nghĩa được phép sửa một biến ngoài lambda?
- Khi nào phải dùng `try-with-resources` dù terminal operation là `collect`?

**Ghi nhớ:** Triển khai Collector đúng bắt đầu từ việc phân biệt **trạng thái tích lũy `A`** với **kết quả `R`**, rồi bảo đảm `supplier` tạo trạng thái độc lập, `accumulator` cập nhật đúng, `combiner` kết hợp tương đương và `finisher` tạo kết quả theo hợp đồng. Các đặc tính như `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT` chỉ được khai báo khi thật sự thỏa điều kiện. Nhờ vậy, một collector có thể được dùng trong các pipeline Java Stream API theo cách rõ ràng, an toàn và có thể kiểm chứng.
