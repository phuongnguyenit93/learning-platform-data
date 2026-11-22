# Thu thập Stream nguyên thủy bằng collect ba tham số

Trong Java Stream API, `IntStream`, `LongStream` và `DoubleStream` cho phép xử lý các giá trị nguyên thủy mà không phải chuyển từng giá trị thành `Integer`, `Long` hoặc `Double`. Các phép kết thúc có sẵn như `sum()`, `average()` và `summaryStatistics()` giải quyết nhiều nhu cầu thống kê. Tuy nhiên, khi muốn **tích lũy các giá trị vào một đối tượng kết quả tùy chỉnh**, chẳng hạn bộ đếm nhiều nhóm, cấu trúc thống kê nghiệp vụ, danh sách hoặc chuỗi định dạng, ta có thể dùng phương thức **`collect` ba tham số**.

Bài học thuộc chương **Stream kiểu nguyên thủy** của module `JAVA_STREAM_API`. Đây là một hình thức *mutable reduction* trong pipeline lazy: bộ tích lũy cập nhật đối tượng kết quả, còn bộ kết hợp gộp kết quả từ các phần xử lý, đặc biệt quan trọng với parallel stream. Ta sẽ học cách thiết kế ba hàm `supplier`, `accumulator`, `combiner` đúng hợp đồng, phân biệt với `Collectors` trên `Stream<T>`, đồng thời nhận diện những giới hạn về trạng thái, tràn số, tài nguyên và hiệu năng.

## 1. Vì sao Stream nguyên thủy có collect riêng?

Java có ba loại Stream nguyên thủy chính:

| Loại Stream | Phần tử | Hàm tích lũy dùng trong `collect` |
| --- | --- | --- |
| `IntStream` | `int` | `ObjIntConsumer<R>` |
| `LongStream` | `long` | `ObjLongConsumer<R>` |
| `DoubleStream` | `double` | `ObjDoubleConsumer<R>` |

Chữ ký khái quát của `IntStream.collect`:

```java
<R> R collect(
        Supplier<R> supplier,
        ObjIntConsumer<R> accumulator,
        BiConsumer<R, R> combiner
)
```

Với `LongStream` và `DoubleStream`, vị trí `ObjIntConsumer<R>` lần lượt được thay bằng `ObjLongConsumer<R>` và `ObjDoubleConsumer<R>`. Cả ba phương thức đã có từ **Java 8**.

Ba thành phần có nhiệm vụ độc lập:

1. **`supplier`**: tạo **một đối tượng kết quả mới, rỗng** thuộc kiểu `R`, chẳng hạn `new ArrayList<>()`, `new long[10]` hoặc `new Stats()`.
2. **`accumulator`**: nhận **đối tượng `R` hiện tại và một giá trị nguyên thủy**, sau đó cập nhật đối tượng. Nó có kiểu `void`, ví dụ `(list, n) -> list.add(n)`.
3. **`combiner`**: nhận **hai đối tượng kết quả từng được tích lũy riêng**, rồi gộp kết quả thứ hai **vào đối tượng thứ nhất**. Nó cũng có kiểu `void`, ví dụ `(left, right) -> left.addAll(right)`.

```text
IntStream: 3, 5, 7, 9
             │
             ▼
   collect(supplier, accumulator, combiner)
             │
     ┌───────┴────────┐
     ▼                ▼
 supplier()        supplier()
  Stats A            Stats B
     │                │
  add(3), add(5)  add(7), add(9)
     │                │
     └── combine(A, B)┘
             │
             ▼
       Stats tổng hợp
```

Sơ đồ minh họa một cách **có thể** phân hoạch dữ liệu khi chạy song song; Java không cam kết luôn tạo chính xác hai bộ tích lũy hay chia dữ liệu theo cách này. Khi chạy tuần tự, `combiner` có thể không được gọi.

**Điểm phân biệt:** `IntStream` không có overload `collect(Collector)` giống `Stream<T>`. Cú pháp `IntStream.range(0, 5).collect(Collectors.toList())` sẽ **không biên dịch**. Nếu muốn dùng `Collectors.toList()` hoặc `Collectors.groupingBy()`, cần chuyển sang `Stream<Integer>` qua `boxed()`, hoặc `mapToObj(...)` nếu cần ánh xạ sang một kiểu object khác.

## 2. Ví dụ đầu tiên: gom int thành List<Integer>

Cách viết dễ hiểu nhất là gom toàn bộ số nguyên vào `ArrayList<Integer>`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.rangeClosed(1, 5)
        .collect(
                () -> new ArrayList<Integer>(),
                (list, n) -> list.add(n),
                (left, right) -> left.addAll(right)
        );

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

Đối chiếu mỗi dòng với hợp đồng:

- `() -> new ArrayList<Integer>()` tạo danh sách riêng để tích lũy.
- `(list, n) -> list.add(n)` thêm một `int` vào danh sách, với việc **boxing** thành `Integer` vì `List<Integer>` lưu object.
- `(left, right) -> left.addAll(right)` gộp hai danh sách; không cần trả về danh sách nào vì `BiConsumer` trả `void`.

Viết bằng method reference sẽ ngắn hơn, nhưng cách có lambda thể hiện rõ hai đối số của `accumulator` và `combiner`. Có thể chọn kiểu cụ thể `ArrayList<Integer>` làm kết quả nếu muốn tránh nhầm suy luận generic.

Nếu mục tiêu chỉ là giữ toàn bộ `int` nguyên thủy, `toArray()` diễn đạt trực tiếp hơn và tránh boxing:

```java
int[] primitiveValues = IntStream.rangeClosed(1, 5).toArray();
System.out.println(java.util.Arrays.toString(primitiveValues));
// [1, 2, 3, 4, 5]
```

Không nên dùng `collect` chỉ vì có thể; hãy bắt đầu từ kết quả muốn biểu diễn. `List<Integer>` cần object; `int[]` và các phép kết thúc số học có thể tiết kiệm bộ nhớ và chi phí boxing trong nhiều trường hợp.

## 3. Ba tham số có hợp đồng gì khi xử lý song song?

`collect` là *mutable reduction*. Nó cho phép tạo một số bộ chứa cục bộ, đưa phần tử vào từng bộ chứa, rồi gộp chúng thành kết quả chung. Để kết quả đúng khi số lượng và cách chia nhánh thay đổi, ba hàm phải có các đặc tính sau.

### 3.1. Supplier tạo đối tượng mới mỗi lần gọi

Đúng:

```java
() -> new ArrayList<Integer>()
```

Sai:

```java
List<Integer> shared = new ArrayList<>();

// SAI: mọi lần gọi supplier đều trả cùng một đối tượng.
() -> shared
```

Nếu supplier trả lại cùng một bộ chứa, các nhánh song song có thể ghi vào cùng đối tượng không an toàn luồng; ngay cả khi không có race, việc gộp kết quả của một đối tượng với chính nó cũng có thể tạo phần tử trùng lặp. `supplier` phải tạo một **kết quả độc lập** ở mỗi lần được gọi.

### 3.2. Accumulator cập nhật bộ chứa được nhận

Đúng:

```java
(list, n) -> list.add(n)
```

Sai khi kỳ vọng thay thế kết quả:

```java
// SAI: đổi tham chiếu tham số cục bộ không thay kết quả collect.
(list, n) -> list = new ArrayList<Integer>()
```

`accumulator` là `ObjIntConsumer<R>`, không trả `R`. Vì vậy nó cần **thay đổi trạng thái đối tượng bộ chứa** theo hợp đồng của kiểu `R`. Không dùng biến đếm ngoài Stream để “giữ kết quả” thay cho bộ chứa được cấp.

### 3.3. Combiner gộp dữ liệu vào đối tượng thứ nhất

Đúng:

```java
(left, right) -> left.addAll(right)
```

Sai:

```java
// SAI: gán lại biến left cục bộ; dữ liệu không được gộp.
(left, right) -> left = right
```

`combiner` cần gộp **cả hai phần kết quả** và giữ đúng đặc tính toán học. Nó không được giả định chỉ có một bộ chứa hoặc luôn được gọi đúng một lần.

### 3.4. Đồng nhất và kết hợp được

Ta có thể tưởng tượng bộ chứa rỗng do `supplier` tạo ra là phần tử **đơn vị**. Gộp với bộ chứa rỗng không được làm thay đổi ý nghĩa kết quả. Việc gộp ba nhánh theo `(A + B) + C` hoặc `A + (B + C)` phải cho kết quả tương đương về mặt nghiệp vụ.

Đối với danh sách dùng phép nối, toán tử là **nối dãy**, có tính kết hợp và giữ thứ tự trong từng nhánh. Đối với thống kê tổng, toán tử gộp phải cộng **tổng với tổng** và **số lượng với số lượng**. Không được lấy trung bình của các số trung bình mà bỏ qua số lượng phần tử ở từng nhánh.

Đồng thời, cách gộp hai kết quả phải tương thích với cách accumulator thêm từng phần tử. Nếu kết quả sau khi gộp khác với việc thêm lần lượt toàn bộ phần tử vào một bộ chứa, thiết kế có thể hỏng khi bật `parallel()`.

## 4. Ví dụ thực tế: thống kê count, sum và average trong một lượt

Giả sử cần đếm số giao dịch, cộng tổng giá trị và tính trung bình. Ta có thể thiết kế bộ chứa `Stats` tự tích lũy:

```java
import java.util.stream.IntStream;

final class Stats {
    long count;
    long sum;

    void add(int value) {
        count++;
        sum += value;
    }

    void combine(Stats other) {
        count += other.count;
        sum += other.sum;
    }

    double average() {
        return count == 0 ? Double.NaN : (double) sum / count;
    }
}

Stats stats = IntStream.of(3, 5, 7, 9)
        .collect(Stats::new, Stats::add, Stats::combine);

System.out.println(stats.count);     // 4
System.out.println(stats.sum);       // 24
System.out.println(stats.average()); // 6.0
```

Ý nghĩa của từng tham số:

| Tham số | Trên bộ chứa `Stats` |
| --- | --- |
| `supplier` | `Stats::new` tạo `count = 0`, `sum = 0` |
| `accumulator` | `Stats::add` nhận một `int` rồi tăng `count`, cộng `sum` |
| `combiner` | `Stats::combine` cộng hai bộ đếm và hai tổng |
| Terminal result | Một `Stats` đã gộp có thể được dùng để tính trung bình |

`sum` dùng `long` thay vì `int` để mở rộng miền giá trị cộng; tuy vậy **`long` vẫn có thể tràn** nếu tổng rất lớn. Nếu cần chính xác tuyệt đối vượt miền 64 bit, cân nhắc `BigInteger` hoặc cơ chế kiểm tra tràn số tùy yêu cầu.

Điều quan trọng hơn là **không tính trung bình của mỗi nhánh rồi lấy trung bình cộng các nhánh**. Ví dụ các nhánh `[10, 20]` và `[100]` có trung bình lần lượt 15 và 100. Kết hợp sai bằng `(15 + 100) / 2 = 57.5`; trung bình thực của ba giá trị là `130 / 3 ≈ 43.33`. Bộ chứa `(sum, count)` gộp được một cách đúng đắn, rồi mới tính trung bình cuối cùng.

### Khi nào nên dùng summaryStatistics()?

Nếu chỉ cần thống kê cơ bản của `int`, Java đã có `IntSummaryStatistics`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics s = IntStream.of(3, 5, 7, 9)
        .summaryStatistics();

System.out.println(s.getCount());   // 4
System.out.println(s.getSum());     // 24
System.out.println(s.getAverage()); // 6.0
System.out.println(s.getMin());     // 3
System.out.println(s.getMax());     // 9
```

Tự viết `Stats` hợp lý khi nghiệp vụ cần **thêm nhiều trường hoặc logic riêng**, chẳng hạn đếm số giao dịch bị từ chối, lưu histogram, phát hiện số ngày có doanh thu dương, hay phân loại theo ngưỡng. Để lấy đúng năm số liệu cơ bản trên, `summaryStatistics()` ngắn và dễ bảo trì hơn.

## 5. Gom số vào các nhóm: histogram bằng long[]

Đây là ví dụ nơi `collect` ba tham số thực sự phát huy lợi ích của Stream nguyên thủy. Giả sử điểm kiểm tra trong đoạn **0–100** và cần đếm theo mười nhóm điểm: 0–9, 10–19, ..., 90–100.

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] scores = {5, 12, 12, 27, 98, 100, -1, 105};

long[] histogram = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .parallel()
        .collect(
                () -> new long[10],
                (counts, score) -> {
                    int index = Math.min(score / 10, 9);
                    counts[index]++;
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(histogram));
// [1, 2, 1, 0, 0, 0, 0, 0, 0, 2]
```

Giải thích:

- `supplier` tạo **mảng đếm riêng**, đã khởi tạo 0 cho mỗi nhánh.
- `accumulator` xác định nhóm và tăng ô tương ứng. Điểm 100 được đưa vào nhóm cuối nhờ `Math.min`.
- `combiner` cộng từng ô của mảng bên phải vào mảng bên trái.
- `filter` loại giá trị nằm ngoài miền hợp lệ trước khi đưa vào nhóm. Quy tắc bỏ điểm ngoài miền là **quyết định nghiệp vụ của ví dụ**, không phải hành vi mặc định của `collect`.

Số lượng nhóm được cố định và ít, nên bộ nhớ dành cho mỗi bộ chứa là `O(10)`. Trong chế độ song song, nhiều bộ chứa có thể tồn tại đồng thời; việc tạo quá nhiều nhánh vẫn có chi phí. Mảng `long[]` tránh phải tạo một `Integer` làm khóa mỗi lần cập nhật như cách gom theo `Map<Integer,Long>`, nhưng đánh đổi bằng việc các nhóm phải xác định trước.

Khi **không** biết trước các nhóm, hoặc cần gom bằng khóa object phức tạp, có thể thích hợp hơn nếu dùng `boxed()` hoặc `mapToObj(...)` kết hợp `Collectors.groupingBy(...)`. Không nên ép mọi bài toán vào mảng chỉ để tránh boxing.

## 6. Tạo chuỗi kết quả với StringJoiner

`collect` có thể tích lũy vào đối tượng khác List hoặc mảng. Ví dụ tạo chuỗi gồm các số nguyên cách nhau bởi dấu phẩy:

```java
import java.util.StringJoiner;
import java.util.stream.IntStream;

StringJoiner joined = IntStream.rangeClosed(1, 5)
        .collect(
                () -> new StringJoiner(", ", "[", "]"),
                (out, n) -> out.add(Integer.toString(n)),
                (left, right) -> left.merge(right)
        );

System.out.println(joined.toString()); // [1, 2, 3, 4, 5]
```

`StringJoiner::merge` cũng có thể làm combiner. Khác với việc nối chuỗi bằng `String` bất biến nhiều lần, `StringJoiner` là một đối tượng có thể cập nhật. Đặc điểm này phù hợp cho mutable reduction. Ở ví dụ tuần tự có encounter order, kết quả giữ thứ tự 1 đến 5.

Khi bật parallel stream, điều kiện để kết quả duy trì thứ tự gặp phần tử vẫn là Stream có encounter order và combiner gộp các nhánh đúng thứ tự. Không dùng `unordered()` hoặc giả định thứ tự gọi accumulator là thứ tự cuối cùng. Nếu phải tạo một chuỗi cực lớn, cần cân nhắc bộ nhớ của chuỗi kết quả; Stream nguyên thủy không làm biến mất chi phí tạo văn bản.

## 7. Áp dụng với LongStream và DoubleStream

Cùng một mô hình ba tham số xuất hiện ở cả `LongStream` và `DoubleStream`. Ví dụ dùng bộ thống kê có sẵn làm đối tượng mutable reduction:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics longStats = LongStream.of(
        10_000_000_000L,
        20_000_000_000L
).collect(
        LongSummaryStatistics::new,
        LongSummaryStatistics::accept,
        LongSummaryStatistics::combine
);

System.out.println(longStats.getCount()); // 2
System.out.println(longStats.getSum());   // 30000000000
```

Với `DoubleStream`:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics doubleStats = DoubleStream.of(1.5, 2.5, 3.0)
        .collect(
                DoubleSummaryStatistics::new,
                DoubleSummaryStatistics::accept,
                DoubleSummaryStatistics::combine
        );

System.out.println(doubleStats.getCount());   // 3
System.out.println(doubleStats.getAverage()); // gần 2.3333333333333335
```

Lưu ý với số thực: `double` dùng biểu diễn dấu phẩy động hữu hạn. Phép cộng không kết hợp hoàn toàn theo toán học khi làm tròn, nên kết quả tổng/trung bình **có thể khác chút ít** khi thay đổi cách phân hoạch hoặc thứ tự thực thi, nhất là với các giá trị rất lớn và rất nhỏ trộn lẫn. Ngay cả `DoubleStream.sum()` cũng có những giới hạn độ chính xác của số thực; nếu nghiệp vụ yêu cầu số tiền chính xác theo đơn vị nhỏ nhất hoặc số thập phân chính xác, cân nhắc `long` theo đơn vị nhỏ nhất hoặc `BigDecimal` với chính sách làm tròn rõ ràng.

Không dùng `DoubleStream.collect` như một bảo đảm rằng kết quả sẽ giống từng bit giữa tuần tự và song song. Bộ tích lũy phải có hành vi gộp hợp lý, còn độ chính xác số học phải được thiết kế theo yêu cầu.

## 8. So sánh collect ba tham số và các API khác

| Nhu cầu | API hợp lý | Ghi chú |
| --- | --- | --- |
| Tính tổng `int`, `long`, `double` | `sum()` | Ngắn gọn; kiểm tra tràn và sai số theo kiểu số |
| Trung bình của `IntStream` | `average()` | Trả `OptionalDouble` vì Stream có thể rỗng |
| Min/max | `min()` / `max()` | Trả kiểu Optional nguyên thủy |
| Count/sum/min/max/average | `summaryStatistics()` | Đã có bộ thống kê tích lũy |
| Giữ mọi phần tử dưới dạng nguyên thủy | `toArray()` | Kết quả `int[]`, `long[]` hoặc `double[]` |
| Biến mỗi `int` thành object rồi dùng Collector | `mapToObj(...).collect(Collectors...)` | Trả `Stream<R>` để dùng Collector |
| Giữ các số vào `List<Integer>` | `boxed().collect(Collectors.toList())` hoặc `collect(...)` ba tham số | Boxing không thể tránh khi tạo List kiểu wrapper |
| Tính histogram cố định hoặc nhiều chỉ số tùy chỉnh | `collect(supplier, accumulator, combiner)` | Chủ động thiết kế mutable container và phép gộp |
| Gom nhóm theo khóa linh hoạt, downstream collector phức tạp | `boxed().collect(Collectors.groupingBy(...))` | Dễ diễn đạt nhưng có boxing |

Ví dụ với `Collectors` yêu cầu chuyển kiểu:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 5)
        .boxed()
        .collect(Collectors.toList());

System.out.println(values); // [1, 2, 3, 4, 5]
```

Nếu mỗi số cần trở thành một object cụ thể, `mapToObj` tránh bước boxed rồi map thành object:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "item-" + n)
        .collect(Collectors.toList());

System.out.println(labels); // [item-1, item-2, item-3]
```

Các `Collector` dựng bằng `Collector.of(...)` có các tham số riêng, có thể khai báo *characteristics* và hỗ trợ downstream collecting. Nhưng overload ba tham số của `IntStream` **không nhận `Collector`**, và combiner của nó có kiểu `BiConsumer<R,R>` thay vì `BinaryOperator<R>` thường gặp trong `Collector.of`. Không chuyển nguyên xi mã combiner có `return left` sang đây khi thiết kế lambda.

## 9. Lỗi quan trọng khi bật parallel()

Parallel stream làm lộ những thiết kế combiner sai mà pipeline tuần tự chưa thể hiện.

### Sai: giữ mutable container bên ngoài

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

// SAI: tác dụng phụ lên shared từ nhiều nhánh.
IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add);
```

`ArrayList` không được bảo vệ cho ghi đồng thời, nên có thể thiếu phần tử, lỗi hoặc trạng thái sai. Dùng `collect` với supplier tạo container mới và combiner phù hợp:

```java
List<Integer> safe = IntStream.range(0, 10_000)
        .parallel()
        .collect(
                () -> new ArrayList<Integer>(),
                (part, n) -> part.add(n),
                (left, right) -> left.addAll(right)
        );
```

Mỗi nhánh có thể cập nhật bộ chứa riêng, rồi bộ kết hợp gộp kết quả. Không cần sử dụng `Collections.synchronizedList` để che giấu việc supplier dùng chung một object; sửa đúng cách tạo và gộp mới là giải pháp.

### Sai: combiner bỏ dữ liệu bên phải

```java
// SAI: combiner không thực hiện bất kỳ phép gộp nào.
IntStream.rangeClosed(1, 100)
        .parallel()
        .collect(
                () -> new long[1],
                (acc, n) -> acc[0] += n,
                (left, right) -> {}
        );
```

Kết quả khi chạy tuần tự có thể giống mong đợi vì combiner không được gọi, nhưng song song có thể mất tổng của các nhánh. Sửa bằng `(left, right) -> left[0] += right[0]`.

### Sai: tính toán không kết hợp được

Các phép như trừ liên tiếp hoặc chia liên tiếp không thích hợp cho combiner tùy ý:

```java
// Ví dụ sai về ý nghĩa nếu muốn thực hiện phép trừ liên tiếp:
// Không thể giả định kết hợp kết quả các nhánh bằng phép trừ
// sẽ tương đương duyệt lần lượt toàn bộ giá trị.
```

Với bài toán tính trung bình, phân vị, phương sai, tỷ lệ hoặc tỉ suất, cần lưu **thống kê đủ** trong container (như `sum`, `count` và các thành phần khác), rồi tính chỉ số ở bước cuối. Nếu phép toán không có cách gộp đúng hợp đồng, không nên ép chạy parallel bằng một combiner tùy ý.

### Chi phí và kích thước nguồn

Ngay cả combiner đúng cũng không bảo đảm parallel nhanh hơn. Song song có thêm chi phí tách công việc, tạo bộ chứa, kết hợp nhánh và tranh chấp tài nguyên CPU/bộ nhớ. Với vài chục phần tử, một vòng lặp hoặc Stream tuần tự thường đơn giản hơn; với tập lớn và mỗi phần tử xử lý đủ nặng, parallel có thể có lợi. Cần đo trên JDK và dữ liệu thực, không suy đoán dựa vào số lõi CPU.

## 10. Hợp đồng lifecycle: terminal collect vẫn không tự đóng nguồn I/O

`collect` là terminal operation. Khi gọi, pipeline bắt đầu được tiêu thụ và không được sử dụng lại; **nhưng terminal operation không tự gọi `close()` trên nguồn I/O**. Nếu pipeline nguyên thủy bắt nguồn từ `Files.lines`, cần đóng Stream tệp ở phạm vi sở hữu tài nguyên.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static Stats summarizeNumbers(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .mapToInt(Integer::parseInt)
                .collect(Stats::new, Stats::add, Stats::combine);
    }
}
```

Ví dụ giả định tệp chứa các dòng là số nguyên hợp lệ hoặc dòng rỗng. Nếu gặp một dòng sai định dạng, `Integer.parseInt` sẽ ném `NumberFormatException` và `try-with-resources` vẫn đóng Stream tệp. Lỗi đọc giữa pipeline lazy có thể xuất hiện dưới dạng `UncheckedIOException`. Trong chương trình thật, cần nêu chính sách xử lý dòng lỗi: bỏ qua có chủ đích, ghi nhận hoặc dừng xử lý.

Tài nguyên nằm ở **Stream nguồn ngoài** do `Files.lines` tạo; việc chuyển sang `IntStream` bằng `mapToInt` không khiến tệp tự giải phóng khi `collect` hoàn tất. Không trả một Stream đã bị đóng ra ngoài khối `try` để người gọi tiếp tục duyệt.

## 11. Ví dụ tổng hợp: thống kê kết quả kiểm tra

Yêu cầu: từ dãy điểm có thể chứa dữ liệu nằm ngoài phạm vi `0..100`, cần thống kê **số lượng hợp lệ**, **số lượng đạt (>= 50)** và **tổng điểm hợp lệ** trong một lượt duyệt.

```java
import java.util.Arrays;

final class ExamStats {
    long valid;
    long passed;
    long totalScore;

    void accept(int score) {
        valid++;
        if (score >= 50) {
            passed++;
        }
        totalScore += score;
    }

    void combine(ExamStats other) {
        valid += other.valid;
        passed += other.passed;
        totalScore += other.totalScore;
    }

    double average() {
        return valid == 0 ? Double.NaN : (double) totalScore / valid;
    }
}

int[] input = {92, 40, 76, 51, -1, 105, 0};

ExamStats result = Arrays.stream(input)
        .filter(score -> score >= 0 && score <= 100)
        .collect(ExamStats::new, ExamStats::accept, ExamStats::combine);

System.out.println(result.valid);      // 5
System.out.println(result.passed);     // 3
System.out.println(result.totalScore); // 259
System.out.println(result.average());  // 51.8
```

Bước `filter` thể hiện quy tắc bỏ điểm ngoài miền, trước khi ghi vào bộ thống kê. Accumulator chỉ xử lý **một điểm `int` mỗi lần**; combiner gộp từng thành phần độc lập và giữ nguyên đơn vị. Đổi `Arrays.stream(input)` thành `Arrays.stream(input).parallel()` không đòi hỏi sửa công thức thống kê vì `ExamStats::combine` thỏa quy tắc gộp này (trong phạm vi không tràn số).

Nếu cần phân biệt “dữ liệu không hợp lệ” với “bị bỏ qua” để xuất báo cáo kiểm toán, không nên loại bỏ bằng `filter` một cách âm thầm. Có thể thay bằng bộ tích lũy có cả trường `invalid` và xử lý trực tiếp từng điểm để đếm đầy đủ.

## 12. Tự kiểm tra

1. Tại sao `IntStream.collect(Collectors.toList())` không biên dịch? **Vì** `IntStream.collect` yêu cầu **ba hàm** `supplier`, `ObjIntConsumer`, `BiConsumer`; overload nhận `Collector` thuộc `Stream<T>`.
2. Trong bộ tích lũy List, `supplier` có thể trả cùng một `ArrayList` cho mọi lời gọi không? **Không**, mỗi lần cần tạo bộ chứa độc lập.
3. Vì sao combiner `(left, right) -> {}` nguy hiểm? **Vì** kết quả từ nhánh bên phải bị mất khi pipeline cần gộp song song.
4. Nếu chỉ cần `int[]`, chọn `collect` hay `toArray()`? **`toArray()`** thường trực tiếp và tránh boxing hơn.
5. `IntSummaryStatistics` có cần tự viết combiner không? **Không** nếu gọi `summaryStatistics()`; có thể dùng `IntSummaryStatistics::combine` khi cố ý gọi `collect` ba tham số.
6. Khi tính trung bình song song, tại sao lưu `sum` và `count` tốt hơn gộp hai `average` bằng trung bình cộng? **Vì** các nhánh có thể có số phần tử khác nhau.
7. `collect` chạy xong trên `Files.lines` đã đóng tệp chưa? **Chưa**; đóng Stream nguồn qua `try-with-resources`.
8. Tại sao kiểu `long` trong bộ tích lũy vẫn cần kiểm tra miền dữ liệu? **Vì** phép cộng `long` vẫn có thể tràn nếu tổng vượt giới hạn.
9. `DoubleStream.collect` có bảo đảm kết quả tổng từng bit giống nhau giữa tuần tự và song song không? **Không**; phép cộng dấu phẩy động bị ảnh hưởng bởi thứ tự và cách nhóm.

**Nguyên tắc áp dụng:** Dùng `collect(supplier, accumulator, combiner)` khi Stream nguyên thủy cần xây dựng **một kết quả mutable tùy chỉnh**. Supplier tạo trạng thái mới, accumulator thêm một giá trị, combiner gộp đúng hai trạng thái; ba hàm phải nhất quán để hoạt động chính xác với cả tuần tự và song song. Khi đã có `sum()`, `toArray()` hoặc `summaryStatistics()` đáp ứng nhu cầu, ưu tiên API chuyên dụng để đơn giản và giảm lỗi.
