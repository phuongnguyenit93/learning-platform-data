# Collector đồng thời hoặc accumulator độc lập trong Parallel Stream (Java 8+)

Khi dùng `parallelStream()`, nhiều phần của pipeline có thể chạy đồng thời. Nếu kết thúc bằng `collect(...)`, cách tích lũy phải tránh **data race** và vẫn tạo kết quả đúng khi dữ liệu được chia thành nhiều phần rồi hợp nhất. Trong Java Stream API có hai mô hình quan trọng:

1. **Accumulator độc lập (isolated accumulation):** mỗi phần xử lý nhận vùng tích lũy riêng; khi các phần hoàn tất, framework dùng `combiner` để gộp chúng. Vùng tích lũy có thể là `ArrayList`, `HashMap` hoặc một object mutable **không thread-safe**, miễn được cô lập đúng hợp đồng `Collector`.
2. **Collector đồng thời (concurrent collector):** collector công bố đặc tính `CONCURRENT` vì nó **có thể nhận các lời gọi `accumulator` đồng thời trên cùng một result container**. Khi điều kiện về thứ tự cho phép, framework có thể dùng một container dùng chung và đưa nhiều phần tử vào đó song song.

**Không cần collector đồng thời mới dùng được Parallel Stream an toàn.** Hai cách đều được hỗ trợ từ Java 8 và vẫn đúng trong Java hiện đại. Chọn cách nào tùy theo yêu cầu về thứ tự, kiểu kết quả, chi phí hợp nhất và khả năng chịu tranh chấp giữa các luồng.

## 1. Hình dung luồng xử lý của hai mô hình

### Mô hình A: accumulator độc lập rồi gộp

```text
Nguồn có thứ tự: [a, b, c, d, e, f]
                        |
                  parallel stream
                 /       |       \
             [a, b]    [c, d]   [e, f]
                |         |        |
            supplier   supplier  supplier
                |         |        |
         accumulator accumulator accumulator
                |         |        |
              A1        A2       A3
                \         |       /
                    combiner
                        |
                 kết quả cuối
```

- `supplier` tạo **những container mới, độc lập**, không dùng cùng một `ArrayList` hay `HashMap` cho tất cả tác vụ.
- `accumulator` thao tác trên container mà framework cấp cho phần dữ liệu đang xử lý. Vì các container của collector **không concurrent** được cô lập trong giai đoạn tích lũy, có thể dùng mutable state không cần khóa cho riêng container đó.
- `combiner` kết hợp các container bộ phận thành một kết quả tương đương với xử lý tuần tự.
- Không được giả định luôn đúng ba partition hoặc ba lần gọi `supplier`; cách chia, gộp và số container phụ thuộc triển khai.

Ví dụ tích lũy danh sách bằng collector chuẩn:

```java
List<Integer> values = IntStream.rangeClosed(1, 6)
    .parallel()
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));

// Nguồn IntStream có encounter order:
// values = [1, 2, 3, 4, 5, 6]
```

`ArrayList` không thread-safe khi nhiều luồng cùng sửa **một instance**. Ví dụ trên vẫn an toàn vì collector chuẩn cùng framework đảm bảo cô lập từng vùng tích lũy và gộp kết quả theo hợp đồng của stream có thứ tự.

### Mô hình B: concurrent reduction

```text
Nguồn: [a, b, c, d, e, f]
             |
       parallel stream
        /     |     \
     task 1 task 2 task 3
        \     |     /
         accumulator
        đồng thời trên
       một container được
       thiết kế concurrent
                |
          kết quả cuối
```

Khi điều kiện cho phép, các tác vụ có thể cập nhật cùng một `ConcurrentMap` hoặc một vùng tích lũy thread-safe. Điều này có thể giảm công gộp nhiều map bộ phận, nhưng cũng có thể tạo **contention** nếu tất cả luồng cùng cập nhật vài khóa nóng.

Hai sơ đồ chỉ mô tả **các khả năng thực thi**, không phải bắt buộc framework luôn chọn chính xác một mô hình hoặc số lượng container cố định. Ngay cả collector `CONCURRENT` vẫn phải có `combiner` đúng và có thể được framework dùng theo cách gộp container.

## 2. Đọc hợp đồng `Collector<T,A,R>` trước khi tối ưu

Một collector bao gồm bốn thành phần và các characteristics:

| Thành phần | Hợp đồng cần hiểu |
| --- | --- |
| `Supplier<A> supplier` | Tạo vùng tích lũy mới, có trạng thái ban đầu đúng |
| `BiConsumer<A,T> accumulator` | Đưa một phần tử nguồn vào vùng tích lũy |
| `BinaryOperator<A> combiner` | Hợp nhất hai vùng tích lũy thành một kết quả hợp lệ |
| `Function<A,R> finisher` | Chuyển vùng tích lũy thành kết quả cuối; có thể là identity |
| `Set<Characteristics> characteristics` | Khai báo thuộc tính được **bảo đảm**; framework được quyền sử dụng để tối ưu |

Ba đặc tính chuẩn còn được hỗ trợ:

- `Collector.Characteristics.CONCURRENT`: `accumulator` **an toàn khi gọi đồng thời lên cùng container**. Đây là một cam kết về thread-safety của toàn bộ phép tích lũy, không phải chỉ nói container là một `ConcurrentHashMap`.
- `Collector.Characteristics.UNORDERED`: kết quả **không cam kết giữ encounter order** của input. Không có nghĩa khóa của mọi loại `Map` đều được duyệt ngẫu nhiên; thứ tự khóa của `ConcurrentSkipListMap` vẫn theo comparator, nhưng collector không được dùng để cam kết thứ tự **phần tử đầu vào**.
- `Collector.Characteristics.IDENTITY_FINISH`: finisher là phép đồng nhất; container tích lũy có thể được trả trực tiếp làm kết quả. Không khai báo nếu phải chuyển `A` sang một `R` khác.

Để `Stream.collect(collector)` thực hiện **concurrent reduction** trên cùng container, các điều kiện quan trọng là:

1. Stream đang ở chế độ **parallel**.
2. Collector có đặc tính `CONCURRENT`.
3. **Stream không có encounter order** *hoặc* collector có đặc tính `UNORDERED`.

Đây là điều kiện được mô tả trong tài liệu chính thức của `java.util.stream`. Việc gọi `parallel()` đơn lẻ không thỏa điều kiện thứ hai; một collection có tên "Concurrent" cũng không tự động biến collector thành `CONCURRENT`.

## 3. Accumulator độc lập: cách dùng mặc định đáng tin cậy

`Collectors.toList()`, `toCollection(...)`, `groupingBy(...)` với collector chuẩn tương ứng thường tích lũy vào các kết quả bộ phận rồi hợp nhất khi chạy song song. Ví dụ phân nhóm và tổng tiền theo vùng:

```java
Map<String, Integer> totalByRegion = sales.parallelStream()
    .collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.summingInt(Sale::amount)
    ));
```

Đoạn này giả định lớp `Sale` ở chương trình mục 9. `TreeMap` không phải một cấu trúc concurrent, nhưng việc gom vẫn an toàn vì collector `groupingBy` là collector **không concurrent** và framework đảm bảo mỗi vùng tích lũy được sử dụng riêng cho đến khi gộp. Các khóa kết quả được sắp theo thứ tự tự nhiên.

### Vì sao không cần `synchronized` trên container riêng?

Với collector không concurrent, tài liệu `Collector` yêu cầu thư viện thực thi đảm bảo **serial thread confinement**: các container bộ phận không bị `accumulator` của nhiều luồng chạm đồng thời. `ArrayList` hoặc `HashMap` được cấp mới từ supplier có thể được cập nhật an toàn trong phạm vi đó.

Cơ chế này **khác hoàn toàn** với việc tự tạo một `ArrayList` chung bên ngoài rồi dùng `parallel().forEach(list::add)`. Trong cách làm sai ấy, các tác vụ thực sự cập nhật **cùng một danh sách không thread-safe** mà không có sự cô lập.

### `combiner` cần đúng

Để kết quả của việc chia một stream thành các phần tương đương với kết quả xử lý tuần tự, collector phải đáp ứng:

- **Identity:** gộp một kết quả với container rỗng mới phải tương đương chính kết quả đó.
- **Associativity:** xử lý `a,b,c` theo một lượt hoặc chia thành các nhóm rồi gộp phải cho kết quả tương đương.
- **Thứ tự:** nếu collector yêu cầu encounter order, phép gộp phải duy trì thứ tự được hợp đồng bảo đảm.
- **Không chia sẻ trạng thái ngoài:** container được sinh mới, không dùng chung mutable object bên ngoài supplier.

Đừng dùng phép tích lũy không kết hợp được, chẳng hạn "lấy trung bình của hai trung bình" mà **không kèm số lượng phần tử**, rồi trông chờ mọi cách chia partition cho cùng kết quả. Tương tự, một combiner chỉ `return left;` và bỏ qua `right` sẽ đánh rơi dữ liệu trong parallel stream.

## 4. Collector concurrent có sẵn: `groupingByConcurrent`

Nếu yêu cầu của bài toán là **gom nhóm nhưng không cần encounter order** trong mỗi nhóm, cân nhắc collector chuẩn:

```java
ConcurrentMap<String, Long> countByRegion = sales.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Sale::region,
        Collectors.counting()
    ));
```

`Collectors.groupingByConcurrent(...)` tạo collector có đặc tính **CONCURRENT** và **UNORDERED**, trả về một `ConcurrentMap`. Đây là cách thường phù hợp để phân nhóm hoặc đếm theo khóa trên dữ liệu lớn khi việc gộp nhiều map bộ phận của `groupingBy` trở nên tốn chi phí.

**Lưu ý quan trọng:**

- Không dựa vào thứ tự duyệt khóa mặc định của `ConcurrentMap` này.
- Nếu downstream là `Collectors.toList()`, các `List` trong map kết quả **không được hứa là thread-safe để ứng dụng tự sửa đồng thời sau `collect`**. Collector và Stream framework quản lý độ an toàn trong lúc thu thập; điều đó không nâng cấp mọi đối tượng giá trị thành concurrent collection.
- Thứ tự các phần tử nằm trong một danh sách nhóm **không được cam kết theo encounter order** bởi `groupingByConcurrent`, kể cả khi đầu vào là một `List` có thứ tự.
- `groupingByConcurrent` có overload nhận `mapFactory` khi cần một kiểu `ConcurrentMap` phù hợp; factory vẫn phải tạo map mới, rỗng, độc lập khi được gọi.

Nếu thật sự cần khóa map được **sắp theo comparator** và vẫn cần collector concurrent, có thể chọn một loại map đồng thời có thứ tự khóa, ví dụ:

```java
ConcurrentMap<String, Long> sortedKeys = sales.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Sale::region,
        ConcurrentSkipListMap::new,
        Collectors.counting()
    ));
```

Cần `import java.util.concurrent.ConcurrentSkipListMap;`. `ConcurrentSkipListMap` duyệt khóa theo thứ tự so sánh, nhưng **điều này vẫn không bảo đảm encounter order của các phần tử trong nhóm**. Cấu trúc có sắp xếp thường tốn thêm chi phí so sánh và quản lý nút; dùng khi có yêu cầu thực sự.

## 5. `toConcurrentMap` và cập nhật giá trị an toàn

Nếu mỗi phần tử tạo một khóa và một giá trị, `Collectors.toConcurrentMap(...)` là collector concurrent, unordered để gom thành `ConcurrentMap`:

```java
ConcurrentMap<String, Integer> totalByRegion = sales.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Sale::region,
        Sale::amount,
        Integer::sum
    ));
```

Hàm `Integer::sum` cho biết cách hợp nhất khi có khóa trùng. Nếu dùng overload hai tham số `toConcurrentMap(keyMapper, valueMapper)` và xuất hiện khóa trùng, quá trình gom sẽ thất bại với `IllegalStateException`; không nên dựa vào việc các lần ghi đè lẫn nhau.

Với các phép tính như tổng số nguyên không tràn, `Integer::sum` có tính kết hợp và giao hoán, nên thứ tự ghép không làm đổi kết quả. Với phép nối chuỗi hoặc chọn "giá trị đầu tiên" dựa vào thứ tự, **một collector unordered có thể không đạt yêu cầu**. Dùng `groupingBy` với encounter order được giữ hoặc mô hình xử lý khác nếu thứ tự là phần của nghiệp vụ.

Nếu mục tiêu là **đếm**, `groupingByConcurrent(classifier, counting())` nói rõ ý định. Khi muốn tổng theo khóa, cả `groupingByConcurrent(..., summingInt(...))` và `toConcurrentMap(keyMapper, valueMapper, mergeFunction)` có thể phù hợp; chọn cách có kiểu dữ liệu, chính sách khóa trùng và ý nghĩa nghiệp vụ dễ đọc hơn.

### "Dùng ConcurrentHashMap" chưa đủ

Ví dụ này có thể tạo ra một `ConcurrentHashMap` nhưng collector được chọn vẫn **không concurrent**:

```java
Collector<Sale, ?, ConcurrentHashMap<String, Integer>> c =
    Collectors.groupingBy(
        Sale::region,
        ConcurrentHashMap::new,
        Collectors.summingInt(Sale::amount)
    );

boolean sharedAccumulator =
    c.characteristics().contains(Collector.Characteristics.CONCURRENT);
// false: groupingBy là non-concurrent collector
```

Ngược lại, `groupingByConcurrent` **không đồng nghĩa** các phần tử nằm trong những downstream `List` đều có thể được sửa an toàn từ nhiều luồng sau khi trả kết quả. Đánh giá thread-safety phải xét **toàn bộ thao tác**, bao gồm cả các giá trị được chứa trong map.

## 6. Viết collector dùng accumulator riêng bằng `Collector.of`

Bạn có thể định nghĩa collector tùy biến khi phép tích lũy có cấu trúc đặc thù mà collector chuẩn không đáp ứng đúng. Ví dụ sau dùng mảng `long[1]` làm vùng tích lũy riêng để cộng số nguyên; đây là ví dụ **giải thích cơ chế**, vì trong ứng dụng thực tế `mapToLong(...).sum()` hoặc `Collectors.summingLong(...)` gọn hơn:

```java
Collector<Integer, long[], Long> sumCollector = Collector.of(
    () -> new long[1],                       // supplier: accumulator mới
    (acc, n) -> acc[0] += n,                 // thêm phần tử
    (left, right) -> {                       // combiner
        left[0] += right[0];
        return left;
    },
    acc -> acc[0]                            // finisher: long -> Long
);

long result = IntStream.rangeClosed(1, 6)
    .parallel()
    .boxed()
    .collect(sumCollector);
// 21
```

Phân tích:

1. Mỗi lần gọi supplier tạo **mảng riêng** khởi tạo bằng 0.
2. `accumulator` sửa `acc[0]` nhưng **không phải** do mọi luồng cùng sửa một mảng: collector này **không khai báo `CONCURRENT`**, nên framework có trách nhiệm cô lập vùng tích lũy.
3. `combiner` cộng hai tổng bộ phận theo luật kết hợp; kết quả bằng cách cộng tuần tự trong miền số không tràn.
4. `finisher` chuyển mảng thành `Long`, vì vậy không thể đánh dấu `IDENTITY_FINISH`.
5. Không gắn `CONCURRENT` vào collector này: mảng một phần tử và phép `+=` **không cho phép cập nhật đồng thời an toàn trên cùng mảng**.

Với lượng dữ liệu cực lớn, `long` vẫn có thể tràn; tránh khẳng định mọi phép cộng trên mọi kiểu số đều kết hợp được theo nghĩa toán học và chính xác tuyệt đối. Với `double`/`float`, kết quả số học cũng có thể thay đổi chút ít do thứ tự làm tròn khi chia và gộp các nhóm. Khi cần tính toán tiền tệ chính xác, thiết kế kiểu số và chính sách làm tròn thích hợp.

### Nếu thật sự viết collector `CONCURRENT`

Một collector custom concurrent phải đảm bảo **lời gọi accumulator từ nhiều luồng lên chính cùng một container là an toàn**. Cần đặc biệt xét:

- `ConcurrentHashMap.compute`, `merge` hoặc `LongAdder` cho cập nhật atomic/phân tán khi được dùng đúng; không dùng chuỗi thao tác `get` rồi `put` thiếu đồng bộ để giả lập tăng đếm.
- Các object **giá trị** bên trong map cũng phải có chiến lược thread-safety nếu nhiều luồng cùng sửa chúng; map concurrent không tự biến `ArrayList` bên trong thành thread-safe.
- `combiner` vẫn phải đúng, dù đường chạy concurrent có thể không cần gộp nhiều container trong một số trường hợp.
- Chỉ khai báo `UNORDERED` nếu kết quả không cần giữ thứ tự gặp; chỉ khai báo `IDENTITY_FINISH` khi `A` và `R` thực sự là cùng kết quả.
- Không dùng `ThreadLocal` hoặc biến `static` làm thay thế cho supplier đúng: vòng đời worker thread, kết hợp các partition và trạng thái sót giữa những lần chạy rất dễ tạo sai lệch.

Với bài toán thống kê hoặc phân nhóm phổ biến, hãy thử `groupingByConcurrent`, `toConcurrentMap`, `counting`, `summingLong` trước khi thiết kế accumulator concurrent riêng. Collector chuẩn đã đóng gói phần lớn các ràng buộc khó của việc thu thập song song.

## 7. Thứ tự dữ liệu ảnh hưởng trực tiếp đến sự lựa chọn

**Encounter order** là thứ tự các phần tử được stream nguồn xác định. `List.stream()` và `IntStream.rangeClosed(...)` là nguồn có thứ tự; `HashSet.stream()` không có thứ tự encounter được cam kết. `sorted()` có thể tạo thứ tự; `unordered()` cho phép pipeline từ bỏ ràng buộc đó.

| Trường hợp | Kỳ vọng hợp lệ |
| --- | --- |
| `list.parallelStream().collect(toList())` | Collector chuẩn bảo toàn encounter order vào danh sách đầu ra |
| `list.parallelStream().collect(toCollection(ArrayList::new))` | Thu thập phần tử theo encounter order của nguồn có thứ tự |
| `list.parallelStream().collect(groupingBy(key, downstream))` | Collector không concurrent; gộp container, giữ các ràng buộc order do collector và downstream cam kết |
| `list.parallelStream().collect(groupingByConcurrent(key))` | Collector unordered; không đòi thứ tự phần tử trong mỗi nhóm hay thứ tự khóa |
| `list.parallelStream().unordered().collect(concurrentCollector)` | Cho phép bỏ encounter order; hữu ích nếu nghiệp vụ thực sự không yêu cầu thứ tự |

Đừng nhầm **thứ tự duyệt `Map.keySet()`** với encounter order của các phần tử; một `ConcurrentSkipListMap` có khóa đã được sắp theo tên vẫn có thể chứa mỗi nhóm với thứ tự phần tử không xác định.

Nếu bắt buộc giữ thứ tự phần tử hoặc "phần tử đầu tiên/cuối cùng" theo nguồn, không nên tự gắn `UNORDERED` hay chuyển sang `groupingByConcurrent` chỉ vì nhanh hơn ở một phép đo ngẫu nhiên. Dùng collector giữ order, xử lý tuần tự khi cần, hoặc định nghĩa thứ tự/khóa sắp xếp một cách rõ ràng.

## 8. Những cách làm dễ tạo data race

### Sai: chia sẻ `ArrayList` bên ngoài pipeline

```java
List<Integer> shared = new ArrayList<>();

// Không dùng: nhiều thread cùng add vào cùng ArrayList.
// IntStream.range(0, 100_000).parallel().forEach(shared::add);
```

Kết quả có thể thiếu phần tử, sai kích thước hoặc gây lỗi bộ nhớ logic do cấu trúc bị ghi đồng thời. `forEach` trong parallel stream cũng không cam kết encounter order.

Cách đúng cho bài toán gom danh sách:

```java
List<Integer> collected = IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));
```

Mỗi phần tích lũy được quản lý bởi collector và stream framework. Không cần tự dùng `Collections.synchronizedList` cho mục tiêu này. `synchronizedList` có thể bảo vệ một số thao tác trên list chia sẻ nhưng sẽ tạo tranh chấp và **không tự phục hồi encounter order** của nhiều lời gọi `forEach`.

### Sai: đếm bằng biến mutable dùng chung

```java
int[] counter = {0};

// Không dùng: counter[0]++ không atomic.
// IntStream.range(0, 100_000).parallel().forEach(n -> counter[0]++);
```

Nếu chỉ muốn đếm, sử dụng `count()`; nếu muốn tổng, dùng `sum()` hoặc collector tổng hợp. Không cần tự tạo một bộ đếm đồng thời chỉ để tính một kết quả terminal đơn giản.

### Sai: đánh dấu `CONCURRENT` để tối ưu bằng mọi giá

Trong `Collector.of(...)`, thêm `Collector.Characteristics.CONCURRENT` chỉ vì đang dùng `parallelStream()` là **sai hợp đồng** nếu accumulator không an toàn khi hai luồng cập nhật cùng container. Các lỗi này có thể khó xuất hiện khi test trên dữ liệu nhỏ nhưng bộc lộ ở tải thật. Đồng thời, đừng khai báo `UNORDERED` cho phép toán có ngữ nghĩa phụ thuộc thứ tự (ví dụ nối chuỗi theo lần xuất hiện).

## 9. Chương trình Java 8+ chạy được

Chương trình cho thấy **cả hai mô hình đều tính đúng cùng một dữ liệu**, và một custom collector không concurrent vẫn được sử dụng với `parallel()`.

Tạo file **`ParallelCollectorModelsDemo.java`**:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.*;

public class ParallelCollectorModelsDemo {

    static final class Sale {
        private final String region;
        private final int amount;

        Sale(String region, int amount) {
            this.region = region;
            this.amount = amount;
        }

        String region() {
            return region;
        }

        int amount() {
            return amount;
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
                new Sale("north", 10),
                new Sale("south", 5),
                new Sale("north", 30),
                new Sale("east", 8),
                new Sale("south", 7),
                new Sale("east", 12));

        // Mô hình A: các Map tích lũy độc lập rồi được gộp.
        Map<String, Integer> independent = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.summingInt(Sale::amount)));

        // Mô hình B: collector concurrent, unordered.
        ConcurrentMap<String, Integer> concurrent = sales.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        Sale::region,
                        Sale::amount,
                        Integer::sum));

        ConcurrentMap<String, Long> counts = sales.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Sale::region,
                        Collectors.counting()));

        // ArrayList vẫn an toàn trong collector không concurrent.
        List<Integer> ordered = IntStream.rangeClosed(1, 6)
                .parallel()
                .boxed()
                .collect(Collectors.toCollection(ArrayList::new));

        // Custom collector không concurrent dùng accumulator riêng.
        Collector<Integer, long[], Long> custom = Collector.of(
                () -> new long[1],
                (acc, n) -> acc[0] += n,
                (left, right) -> {
                    left[0] += right[0];
                    return left;
                },
                acc -> acc[0]);

        long total = IntStream.rangeClosed(1, 6)
                .parallel()
                .boxed()
                .collect(custom);

        // Sắp ConcurrentMap khi in để kết quả demo dễ kiểm tra:
        // Không ngầm giả định thứ tự duyệt của ConcurrentMap.
        System.out.println("independent totals: " + independent);
        System.out.println("concurrent totals: " + new TreeMap<>(concurrent));
        System.out.println("concurrent counts: " + new TreeMap<>(counts));
        System.out.println("ordered list: " + ordered);
        System.out.println("independent custom sum: " + total);
    }
}
```

Biên dịch và chạy bằng JDK 17+ (mã chỉ dùng API Java 8):

```bash
javac -encoding UTF-8 ParallelCollectorModelsDemo.java
java ParallelCollectorModelsDemo
```

Đầu ra chuẩn:

```text
independent totals: {east=20, north=40, south=12}
concurrent totals: {east=20, north=40, south=12}
concurrent counts: {east=2, north=2, south=2}
ordered list: [1, 2, 3, 4, 5, 6]
independent custom sum: 21
```

Các phép tính được kiểm tra độc lập: `east = 8 + 12 = 20`, `north = 10 + 30 = 40`, `south = 5 + 7 = 12`. `groupingByConcurrent + counting` có hai giao dịch ở mỗi vùng. `IntStream.rangeClosed(1, 6)` có thứ tự nên collector `toCollection(ArrayList::new)` trả về `[1, 2, 3, 4, 5, 6]`. Custom collector cộng 1 đến 6 bằng 21.

**Tại sao in `new TreeMap<>(concurrent)`?** Để cố định thứ tự hiển thị cho ví dụ. Bản thân `toConcurrentMap` không cam kết thứ tự khóa của map kết quả. Việc tạo bản sao `TreeMap` chỉ thực hiện sau khi phép `collect` đã hoàn tất và không thay đổi cách collector hoạt động.

## 10. Chọn giải pháp nào cho chương trình thực tế?

| Câu hỏi | Lựa chọn ban đầu |
| --- | --- |
| Cần `List` theo encounter order? | `toList()` hoặc `toCollection(ArrayList::new)` (accumulator cô lập) |
| Cần `Map` với khóa sắp xếp? | `groupingBy(key, TreeMap::new, downstream)` |
| Cần giữ thứ tự gặp đầu tiên của khóa trong stream tuần tự? | `groupingBy(key, LinkedHashMap::new, downstream)` |
| Cần đếm hoặc tính tổng theo khóa, thứ tự không quan trọng? | Thử `groupingByConcurrent` hoặc `toConcurrentMap` |
| Mỗi khóa có nhiều phần tử cần giữ thứ tự nguồn? | Ưu tiên `groupingBy` có downstream phù hợp, xác minh ràng buộc order |
| Cần custom accumulator mutable không thread-safe? | Dùng non-concurrent collector với supplier tạo container riêng và combiner đúng |
| Muốn tích lũy vào cùng container từ nhiều luồng? | Chỉ dùng collector thực sự `CONCURRENT` và chấp nhận hoặc xử lý yêu cầu order |
| Chỉ cần số lượng, tổng hoặc cực trị? | Dùng terminal operation/collector chuẩn trước: `count`, `sum`, `min`, `max`, `summingLong` |

### Hiệu năng: parallel không phải lúc nào cũng nhanh hơn

- **Chi phí chia/gộp:** collector không concurrent có thể phải tạo/gộp nhiều container; `groupingBy` trên rất nhiều khóa có thể tốn chi phí hợp nhất map.
- **Tranh chấp khóa nóng:** collector concurrent có thể bị nhiều luồng cập nhật cùng một khóa; `ConcurrentMap` không loại bỏ contention.
- **Kích thước và công việc:** nguồn nhỏ hoặc thao tác nhẹ như cộng một vài số thường không đáng chi phí lập lịch và đồng bộ.
- **Thứ tự:** bảo toàn encounter order có chi phí, nhưng bỏ order không được làm thay đổi yêu cầu sản phẩm.
- **Đúng đắn của kết quả:** kiểm tra độ tràn của kiểu số; phép cộng số thực có thể có sai khác nhỏ do thứ tự làm tròn.
- **Đo lường:** dùng dữ liệu đại diện, JMH khi cần benchmark nghiêm túc, và so sánh pipeline tuần tự với các phương án parallel trong cùng điều kiện.

Không mặc định "concurrent collector luôn nhanh hơn" hoặc "parallelStream luôn nhanh hơn stream". Chọn phiên bản dễ đọc, đúng nghiệp vụ trước; tối ưu dựa trên phép đo và bộ dữ liệu thực tế.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách giải quyết |
| --- | --- | --- |
| Nghĩ `parallelStream()` đòi mọi accumulator phải thread-safe | Collector không concurrent được framework cô lập vùng tích lũy | Dùng collector chuẩn hoặc custom có supplier riêng, combiner đúng |
| Truyền `ArrayList::new` vào collector và cho rằng nhiều luồng cùng `add` lên một list | Framework có thể tạo nhiều list riêng, không nhất thiết dùng chung | Hiểu mô hình tích lũy và không suy đoán số container |
| Gắn `CONCURRENT` vào custom collector có `long[]` và phép `+=` | Phép cộng không atomic, data race khi dùng cùng mảng | Không gắn cờ này; hoặc thiết kế accumulator thực sự thread-safe |
| Đổi `groupingBy` sang `groupingByConcurrent` mà vẫn đòi order trong list nhóm | Collector concurrent là unordered | Giữ `groupingBy` hoặc thiết kế rõ cơ chế order |
| Dùng `ConcurrentHashMap::new` bên trong `groupingBy` rồi nghĩ collector là `CONCURRENT` | Kiểu container không quyết định characteristics | Chọn đúng collector và kiểm tra hợp đồng |
| Dùng `groupingByConcurrent(..., toList())` rồi sửa các list đồng thời ở bước sau | ConcurrentMap không khiến giá trị list thread-safe | Đồng bộ hoặc dùng cấu trúc phù hợp ở bước tiếp theo |
| Dùng `get` + `put` để cập nhật tổng trong map chia sẻ | Hai thao tác riêng lẻ không tạo cập nhật tổng nguyên tử | Dùng `merge`, `compute`, collector chuẩn |
| Dùng `toConcurrentMap(k,v)` khi nhiều phần tử trùng khóa | Overload này ném lỗi khi trùng khóa | Cung cấp merge function theo nghiệp vụ |
| Trông cậy `HashMap`/`ConcurrentMap` duyệt khóa ổn định | Không có cam kết về thứ tự duyệt | Sắp khóa khi trình bày, hoặc chọn map có hợp đồng thứ tự |
| Bỏ `combiner` đúng vì đang có `CONCURRENT` | Framework vẫn có thể dùng combiner | Đáp ứng luật identity/associativity trong mọi đường chạy |
| Có `CONCURRENT` thì chắc chắn cùng một container được dùng | Framework được phép chọn cách thực thi | Chỉ dựa trên hợp đồng kết quả, không dựa vào lịch chạy |
| Chia sẻ mutable `ArrayList` qua `parallel().forEach` | Race, mất phần tử, phá cấu trúc | `collect(toCollection(ArrayList::new))` |
| Dùng `peek` thay cho phép tổng hợp | Tác dụng phụ/optimizer không bảo đảm | Dùng terminal operation hoặc collector chuẩn |
| Tối ưu cho nguồn nhỏ mà không đo | Chi phí parallel có thể lớn hơn lợi ích | So sánh tuần tự/song song bằng benchmark đại diện |

## 12. Tự kiểm tra kiến thức

**Bài 1.** Một `List<Integer>` có một triệu số và bạn muốn lưu đủ các số trong `ArrayList` theo thứ tự nguồn. Có cần làm cho `ArrayList` thread-safe trước khi gọi `parallelStream().collect(toCollection(ArrayList::new))`?

**Đáp án:** Không. Đây là collector không concurrent tích lũy vào container độc lập, framework chịu trách nhiệm ghép đúng. Tuy nhiên cần đo xem chạy song song có thực sự có lợi cho phép gom đơn giản đó không.

**Bài 2.** Bạn cần thống kê số đơn hàng theo vùng và không quan tâm thứ tự các vùng. Có nên thử `groupingByConcurrent(Sale::region, counting())`?

**Đáp án:** Có thể thử; API đúng hợp đồng về kết quả và không yêu cầu encounter order. Sau đó benchmark so với `groupingBy` tuần tự/song song, đặc biệt nếu số vùng ít và có khóa nóng.

**Bài 3.** Custom collector có `supplier = () -> new long[1]`, `accumulator = (a,n) -> a[0] += n`, combiner cộng hai mảng. Collector này có thể chạy với `parallelStream()` mà không gắn `CONCURRENT` không?

**Đáp án:** Có. Stream framework cô lập các accumulator của non-concurrent collector và sử dụng combiner đúng. Không nên gắn `CONCURRENT` bởi một mảng `long[1]` không an toàn nếu nhiều luồng cùng cập nhật nó.

**Bài 4.** Cả `toConcurrentMap` và `groupingByConcurrent` trả kết quả map đồng thời. Điều đó có đảm bảo các `List` chứa bên trong có thể được nhiều luồng cùng gọi `add` an toàn sau khi thu thập?

**Đáp án:** Không. Phải đánh giá thread-safety của từng giá trị hoặc cấu trúc bên trong, không chỉ xét map bao ngoài.

**Bài 5.** Vì sao thay `groupingBy` bằng `groupingByConcurrent` có thể là thay đổi sai trong báo cáo yêu cầu "sản phẩm của mỗi nhóm theo đúng thứ tự xuất hiện"?

**Đáp án:** `groupingByConcurrent` là collector `UNORDERED`; thứ tự phần tử trong các nhóm không được bảo đảm. Cần giữ collector có ràng buộc encounter order hoặc xử lý thứ tự theo khóa xác định.

### Tài liệu API chính thức còn áp dụng

- [`Collector` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html): supplier/accumulator/combiner/finisher, identity, associativity, serial thread confinement.
- [`Collector.Characteristics` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html): `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH`.
- [`Collectors` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): `groupingByConcurrent`, `toConcurrentMap` và collector chuẩn khác.
- [`Stream` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): `collect` và các điều kiện concurrent reduction.
- [`java.util.stream` — Java SE 26 package documentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html): reduction, concurrency, encounter order và đánh đổi hiệu năng.