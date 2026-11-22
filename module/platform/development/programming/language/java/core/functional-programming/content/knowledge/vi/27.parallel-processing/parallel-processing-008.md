# groupingByConcurrent(), toConcurrentMap() và yêu cầu collector đồng thời trong Java

Khi xử lý dữ liệu bằng `parallelStream()`, nhiều phép biến đổi có thể được thực hiện trên các thread khác nhau. Để tổng hợp dữ liệu theo khóa hoặc tạo một `ConcurrentMap`, Java cung cấp hai họ collector quan trọng trong `java.util.stream.Collectors`:

- **`groupingByConcurrent()`**: gom phần tử thành các nhóm theo hàm phân loại (*classifier*), trả về `ConcurrentMap<K,...>`. Có thể kết hợp downstream collector để đếm, tính tổng hoặc tạo kết quả nhóm.
- **`toConcurrentMap()`**: biến từng phần tử thành cặp **khóa–giá trị**, đưa vào `ConcurrentMap<K,U>`; cho phép xác định cách gộp khi nhiều phần tử tạo cùng khóa.

Đặc trưng của hai họ này là các collector được thiết kế cho **concurrent reduction** và có các `Collector.Characteristics` phù hợp. Nhưng cần phân biệt rõ:

1. **Collector concurrent** nói về việc *accumulator có thể được framework gọi đồng thời trên cùng một result container* khi điều kiện cho phép.
2. **ConcurrentMap** nói về cơ chế truy cập/cập nhật map theo hợp đồng của triển khai; nó **không tự làm mọi object đang được lưu trong map trở thành thread-safe**.
3. **Parallel Stream** mô tả chế độ pipeline; nó **không bảo đảm** luôn chạy nhanh hơn, không bảo đảm thứ tự thread và không bắt buộc mọi collector phải có `CONCURRENT`.
4. **`UNORDERED`** cho phép bỏ yêu cầu về encounter order trong kết quả; nếu nghiệp vụ cần “bản ghi đầu tiên” hoặc thứ tự danh sách ổn định, phải thiết kế riêng.

Bài học sử dụng **Java 17+**, các ví dụ runnable có đầu ra xác định, cùng các quy tắc chọn collector đúng và những lỗi đồng thời cần tránh.

## 1. Ôn lại Collector<T,A,R> và concurrent reduction

Một `Collector<T,A,R>` có ba vai trò kiểu:

- `T`: kiểu phần tử Stream đầu vào.
- `A`: kiểu container/trạng thái tích lũy trung gian.
- `R`: kiểu kết quả cuối của `collect`.

Các hàm cốt lõi:

```java
Supplier<A> supplier()
BiConsumer<A, T> accumulator()
BinaryOperator<A> combiner()
Function<A, R> finisher()
```

Đây là **chữ ký minh họa**, không phải mã Java độc lập. Trong thực tế, phương thức của `Collector` dùng generic wildcard chi tiết hơn. `supplier` tạo state, `accumulator` thêm phần tử vào state, `combiner` gộp các state, và `finisher` tạo kết quả cuối.

Với một collector **không có `CONCURRENT`**, Stream framework vẫn có thể thu thập song song bằng cách tạo nhiều accumulator độc lập rồi gọi combiner để ghép lại. Ví dụ `Collectors.toList()` không cần được khai báo concurrent để dùng đúng với `parallelStream()`.

Với một collector có **`CONCURRENT`**, framework được phép cho nhiều thread **đồng thời cập nhật cùng một accumulator** khi các điều kiện về thứ tự và collector phù hợp. Vì vậy accumulator phải hỗ trợ concurrency thật sự. Không nên gắn `CONCURRENT` vào một collector có state là `ArrayList` nhưng accumulator gọi `add` không đồng bộ trên cùng list.

### Ba Characteristics thường gặp

| Characteristic | Ý nghĩa cốt lõi | Đừng hiểu nhầm |
| --- | --- | --- |
| `CONCURRENT` | Có thể gọi accumulator đồng thời trên cùng result container | Không bảo đảm luôn có nhiều thread, không bảo đảm mọi giá trị con thread-safe |
| `UNORDERED` | Collector không cam kết giữ encounter order của phần tử | Không có nghĩa ngẫu nhiên xáo kết quả mỗi lần |
| `IDENTITY_FINISH` | Trạng thái tích lũy có thể dùng trực tiếp làm kết quả | Không tự xuất hiện nếu finisher cần chuyển sang kiểu khác |

**Quy tắc về encounter order:** Với concurrent collector trên ordered Stream, một *concurrent reduction dùng một state chia sẻ* chỉ được áp dụng trong những điều kiện cho phép, như collector `UNORDERED` hoặc Stream đã được đánh dấu unordered. Hai họ collector của bài này thường có cả `CONCURRENT` và `UNORDERED`, nên không cung cấp cam kết giữ phần tử đầu tiên theo thứ tự List nguồn.

## 2. groupingByConcurrent(): gom nhóm bằng classifier

Hình thức phổ biến nhất:

```java
ConcurrentMap<K, List<T>> result = source.parallelStream()
        .collect(Collectors.groupingByConcurrent(classifier));
```

Đây là **mẫu cú pháp**: `source` phải là collection kiểu `T`, `classifier` là `Function<? super T, ? extends K>`, và cần import `ConcurrentMap`, `List`, `Collectors`.

Ví dụ dùng độ dài chuỗi làm khóa:

```java
ConcurrentMap<Integer, List<String>> byLength =
        List.of("cat", "ox", "dog", "ant")
                .parallelStream()
                .collect(Collectors.groupingByConcurrent(String::length));
```

Kết quả có nhóm **2** chứa `"ox"`, nhóm **3** chứa `"cat"`, `"dog"`, `"ant"`. Tuy nhiên **không dựa vào thứ tự** phần tử trong danh sách nhóm khi dùng `groupingByConcurrent()`. Nếu cần in ổn định, hãy sort một bản sao của từng danh sách hoặc chuyển sang phép thu thập có yêu cầu encounter order phù hợp.

Điểm khác với `Collectors.groupingBy(String::length)`:
- `groupingBy` trả `Map<K,List<T>>` theo kiểu tĩnh và không công bố `CONCURRENT`.
- `groupingByConcurrent` trả `ConcurrentMap<K,List<T>>` theo kiểu tĩnh, công bố `CONCURRENT` và `UNORDERED`.
- Với xử lý song song, `groupingByConcurrent` có thể tránh chi phí gộp nhiều map trung gian trong một số workload, nhưng **không bảo đảm nhanh hơn**.

### Ba overload chính của groupingByConcurrent

```java
Collectors.groupingByConcurrent(classifier)
Collectors.groupingByConcurrent(classifier, downstream)
Collectors.groupingByConcurrent(classifier, mapFactory, downstream)
```

Đây là các **lời gọi API minh họa**. Dùng `downstream` khi cần kết quả nhóm khác `List<T>`; dùng `mapFactory` khi muốn một triển khai `ConcurrentMap` thích hợp, ví dụ `ConcurrentSkipListMap` để có thứ tự khóa.

Các overload trả về `ConcurrentMap<K,D>` với `D` phụ thuộc downstream. Ví dụ `Collectors.counting()` trả `Long`; `Collectors.summingInt(...)` trả `Integer`; `Collectors.mapping(..., toList())` trả `List<R>`.

## 3. Chương trình Java 17: groupingByConcurrent có đầu ra ổn định

Tạo tệp **`ConcurrentGroupingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupingDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "cat", "dog", "ox", "ant", "bee", "cow"
        );

        ConcurrentMap<Integer, List<String>> byLength =
                words.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                String::length));

        ConcurrentMap<Integer, Long> counts =
                words.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                String::length,
                                Collectors.counting()));

        new TreeMap<>(byLength).forEach((length, group) -> {
            List<String> sorted = new ArrayList<>(group);
            Collections.sort(sorted);
            System.out.println("length" + length + "=" + sorted);
        });
        System.out.println("counts=" + new TreeMap<>(counts));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ConcurrentGroupingDemo.java
java ConcurrentGroupingDemo
```

**Stdout chính xác:**

```text
length2=[ox]
length3=[ant, bee, cat, cow, dog]
counts={2=1, 3=5}
```

Giải thích:
1. Độ dài 2 chỉ có `"ox"`; độ dài 3 có năm từ còn lại.
2. `groupingByConcurrent` trả `ConcurrentMap` nhưng **không cam kết thứ tự duyệt map và phần tử trong list của mỗi nhóm**.
3. Chương trình dùng `new TreeMap<>(byLength)` để duyệt khóa theo thứ tự tăng dần, và tạo `ArrayList` mới để sort từng nhóm trước khi in. Như vậy stdout không phụ thuộc lịch trình worker.
4. `counting()` là downstream, nên mỗi nhóm có một `Long` thay vì list; kết quả `counts` được copy sang `TreeMap` trước khi in.

**Đừng hiểu `ConcurrentMap<Integer,List<String>>` là một map có các danh sách tự đồng bộ.** Một số downstream như `toList()` không phải concurrent collector. Framework có thể dùng cơ chế phối hợp cập nhật từng nhóm trong quá trình thu thập; sau khi trả kết quả, **caller vẫn chịu trách nhiệm an toàn luồng nếu nhiều thread tự sửa cùng một danh sách**.

## 4. Downstream collector không cần tự có CONCURRENT

Một điểm dễ nhầm: `groupingByConcurrent(classifier, Collectors.toList())` trả một collector có đặc tính concurrent, dù `Collectors.toList()` **không phải** một collector concurrent theo nghĩa nhiều thread được phép đồng thời gọi accumulator trên cùng `ArrayList`.

Tại sao vẫn đúng? Vì **collector bên ngoài có trách nhiệm tổ chức và đồng bộ việc cập nhật state downstream** khi downstream không công bố `CONCURRENT`. Trong triển khai JDK, các cập nhật vào container nhóm có thể được phối hợp riêng để tránh nhiều worker sửa một list nhóm cùng lúc.

Do đó cần phân biệt:

- **Concurrent collector tổng thể:** có thể cho phép nhiều phần tử được phân loại và thu thập đồng thời đúng hợp đồng.
- **Downstream non-concurrent:** không được caller tùy tiện chia sẻ accumulator của downstream giữa nhiều thread và sửa đồng thời.
- **Kết quả `List<T>` sau collect:** không nhất thiết là list thread-safe; hợp đồng của `ConcurrentMap` không bao phủ đồng bộ cho mọi object bên trong.

Ví dụ:

```java
ConcurrentMap<String, List<String>> buckets = words.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                word -> word.substring(0, 1),
                Collectors.toList()));
```

Đây là mảnh mã minh họa với `words` là `Collection<String>` không có chuỗi rỗng, đã import `ConcurrentMap`, `List`, `Collectors`. Các giá trị nhóm có thể là danh sách bình thường. Nếu nhiều thread cần thêm phần tử **sau khi collect xong**, hãy chọn cấu trúc dữ liệu và kỹ thuật đồng bộ khác phù hợp; không dựa vào việc map được concurrent để coi `buckets.get("a").add(...) ` luôn an toàn.

Cũng đừng sửa các nhóm trong khi một tác vụ khác còn đang phân tích chúng mà không có thiết kế đồng bộ. Concurrent collection không tự cung cấp *transaction* cho nhiều bước trên cấu trúc lồng nhau.

## 5. Thống kê từng nhóm với downstream

Downstream có thể là `counting`, `summingInt`, `summarizingInt`, `mapping`, `filtering` và nhiều collector chuẩn khác:

```java
ConcurrentMap<String, Long> counts = events.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Event::region,
                Collectors.counting()));
```

`events` và `Event` trong mảnh mã là dữ liệu/kiểu do ứng dụng cung cấp; `Event::region` là accessor trả String, ví dụ ở chương trình ngay sau.

Đặc biệt, với `IntSummaryStatistics`, bạn có thể tổng hợp count, sum, min, max, average cho mỗi nhóm. Nếu cần in theo thứ tự, đưa các key vào `TreeMap` hoặc sort các key trước khi xuất kết quả.

### Chương trình Java 17: downstream summarizingInt

Lưu thành **`ConcurrentGroupStatsDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupStatsDemo {
    record Event(String region, int duration) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event("N", 2),
                new Event("S", 3),
                new Event("N", 4),
                new Event("S", 5),
                new Event("N", 6)
        );

        ConcurrentMap<String, IntSummaryStatistics> stats =
                events.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                Event::region,
                                Collectors.summarizingInt(Event::duration)));

        new TreeMap<>(stats).forEach((region, s) -> {
            System.out.println(region
                    + ": count=" + s.getCount()
                    + ", sum=" + s.getSum()
                    + ", min=" + s.getMin()
                    + ", max=" + s.getMax()
                    + ", avg=" + s.getAverage());
        });
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ConcurrentGroupStatsDemo.java
java ConcurrentGroupStatsDemo
```

**Stdout chính xác:**

```text
N: count=3, sum=12, min=2, max=6, avg=4.0
S: count=2, sum=8, min=3, max=5, avg=4.0
```

Với nhóm N, duration lần lượt 2, 4, 6 nên count 3, sum 12, average 4.0. Nhóm S có 3 và 5 nên count 2, sum 8, average 4.0. `summarizingInt` có thể dùng làm downstream của collector concurrent tổng thể; framework chịu trách nhiệm cập nhật nhóm thích hợp trong pha thu thập.

**Điều kiện số học:** `IntSummaryStatistics.getSum()` trả `long`, thuận tiện cho nhiều tổng int, nhưng `long` vẫn có giới hạn. Đừng xem thống kê Java là cơ chế tính số chính xác vô hạn.

## 6. toConcurrentMap(): chuyển phần tử thành cặp khóa–giá trị

Trong khi `groupingByConcurrent` mặc định thu thập **nhiều phần tử trong một nhóm**, `toConcurrentMap` thu từng phần tử thành **một giá trị ứng với một khóa**, hoặc hợp nhất các giá trị nếu có khóa trùng.

Các overload quan trọng:

```java
Collectors.toConcurrentMap(keyMapper, valueMapper)
Collectors.toConcurrentMap(keyMapper, valueMapper, mergeFunction)
Collectors.toConcurrentMap(
        keyMapper, valueMapper, mergeFunction, mapFactory)
```

Đây là **mẫu API minh họa**; cần có các hàm và kiểu thích hợp.

- **`keyMapper`**: tính khóa `K` cho mỗi phần tử `T`.
- **`valueMapper`**: tính giá trị `U` cho mỗi phần tử `T`.
- **`mergeFunction`**: xử lý tình huống nhiều phần tử cùng tạo khóa `K`.
- **`mapFactory`**: tùy chọn cung cấp một `ConcurrentMap<K,U>` cụ thể.

Hai đối số đủ khi khóa chắc chắn duy nhất. Nếu có khóa trùng, overload hai đối số sẽ **ném `IllegalStateException`**; nó không tự chọn giá trị “đầu tiên” hoặc “cuối cùng”.

Khi khóa trùng là hợp lệ, hãy cung cấp merge function có nghĩa nghiệp vụ. Ví dụ muốn cộng số lượng theo mã sản phẩm:

```java
ConcurrentMap<String, Integer> quantities = sales.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Sale::sku, Sale::quantity, Integer::sum));
```

Đây là mảnh mã trong ứng dụng có `Sale`, `sales` tương ứng. `Integer::sum` có tính kết hợp và giao hoán trên những giá trị int nhỏ trong ví dụ; thứ tự gộp không làm thay đổi kết quả.

### Khi cần giữ khóa có thứ tự

Overload bốn đối số cho phép cung cấp `ConcurrentSkipListMap::new` làm map factory:

```java
Collectors.toConcurrentMap(
        Sale::sku, Sale::quantity,
        Integer::sum,
        java.util.concurrent.ConcurrentSkipListMap::new)
```

`ConcurrentSkipListMap` có thứ tự khóa theo comparator hoặc natural ordering, phù hợp khi cần in khóa theo thứ tự xác định. **Thứ tự khóa của map không giải quyết thứ tự gộp nhiều giá trị cùng một khóa**: nếu merge function phụ thuộc thứ tự, kết quả parallel vẫn có thể không xác định như ý muốn.

## 7. Chương trình Java 17: toConcurrentMap, khóa trùng và merge

Tạo tệp **`ConcurrentMapMergeDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

public class ConcurrentMapMergeDemo {
    record Sale(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 3),
                new Sale("B", 4),
                new Sale("A", 7),
                new Sale("C", 2),
                new Sale("B", 1)
        );

        ConcurrentMap<String, Integer> totals = sales.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        Sale::sku,
                        Sale::quantity,
                        Integer::sum,
                        ConcurrentSkipListMap::new));

        System.out.println("totals=" + totals);

        try {
            sales.parallelStream()
                    .collect(Collectors.toConcurrentMap(
                            Sale::sku, Sale::quantity));
            System.out.println("unexpected");
        } catch (IllegalStateException ex) {
            System.out.println("duplicateKey=IllegalStateException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ConcurrentMapMergeDemo.java
java ConcurrentMapMergeDemo
```

**Stdout chính xác:**

```text
totals={A=10, B=5, C=2}
duplicateKey=IllegalStateException
```

Giải thích:
1. `Sale("A",3)` và `Sale("A",7)` cùng khóa A, `Integer::sum` gộp thành 10. B thành 5, C thành 2.
2. `ConcurrentSkipListMap` hiển thị khóa A, B, C theo thứ tự tự nhiên, nên stdout xác định.
3. Overload hai đối số **không có merge function**. Dữ liệu có khóa trùng nên `collect` ném `IllegalStateException`. Chương trình bắt đúng kiểu lỗi để minh họa; không dựa vào thông báo exception cụ thể vì thông báo có thể khác theo JDK.
4. Mỗi phép `collect` tạo một Stream mới từ `sales`; không tái sử dụng Stream đã bị terminal operation tiêu thụ.

**Không nuốt lỗi trùng khóa bằng merge function tùy tiện** như `(oldValue, newValue) -> newValue` nếu nghiệp vụ cần ghi nhận dữ liệu trùng, kiểm tra version hoặc chọn bản ghi mới nhất theo timestamp. Trong Stream song song và collector `UNORDERED`, “newValue” trong một lần merge không được đảm bảo là phần tử **đến sau theo encounter order**.

## 8. Merge function phải phù hợp với concurrent aggregation

Với các phép gộp song song, yêu cầu quan trọng là **tính kết hợp (associativity)**: thay đổi cách nhóm các phép gộp không được đổi kết quả về mặt ngữ nghĩa.

Ví dụ phép cộng:

```text
(a + b) + c = a + (b + c)
```

Ngược lại, phép trừ không kết hợp:

```text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
```

Hai khối trên là ký hiệu toán học, không phải mã Java. Nếu dùng phép trừ làm merge function cho các giá trị cùng khóa, kết quả có thể thay đổi theo thứ tự gộp.

Với collector `UNORDERED`, **tính giao hoán (commutativity)** cũng là một thuộc tính rất hữu ích để đảm bảo kết quả không phụ thuộc thứ tự cập nhật: `merge(a,b)` và `merge(b,a)` cần tương đương khi thứ tự không có ý nghĩa nghiệp vụ.

| Merge function | Thường phù hợp? | Lý do |
| --- | --- | --- |
| `Integer::sum` | Có, khi tổng int nằm trong giới hạn nghiệp vụ | Kết hợp và giao hoán cho cộng số nguyên |
| `Integer::max` | Có | Chọn max không phụ thuộc thứ tự |
| `Long::sum` | Có, khi không tràn phạm vi nghiệp vụ | Cộng long |
| `(a,b) -> a-b` | Không | Phép trừ không kết hợp |
| `(a,b) -> a` | Cẩn thận | “Giữ giá trị đã có” không hứa là bản đầu tiên trong List nguồn |
| `(a,b) -> b` | Cẩn thận | “Giữ giá trị mới” không hứa là bản cuối trong encounter order |
| `(a,b) -> a + "," + b` | Cẩn thận | Nối chuỗi phụ thuộc thứ tự, có thể tạo kết quả khác nhau |

Nếu yêu cầu thật sự là **bản có timestamp lớn nhất**, hãy gộp theo comparator thời gian, ví dụ chọn record có `timestamp` lớn hơn. Nếu có hai record trùng timestamp, thêm quy tắc tie-breaker rõ ràng để kết quả vẫn xác định.

Một số phép gộp như cộng `double` chịu ảnh hưởng sai số làm tròn và cách nhóm; không đòi kết quả bit-for-bit giống nhau giữa mọi lịch trình song song nếu bài toán không thiết kế được điều đó.

## 9. Null keys, null values và classifier

Các concurrent map thường không cho phép khóa hoặc giá trị null; ví dụ `ConcurrentHashMap` và `ConcurrentSkipListMap` **không hỗ trợ null key hoặc null value**. Vì vậy cần kiểm soát kết quả của `keyMapper`, `valueMapper` và classifier.

```java
// MẪU NGUY HIỂM nếu sku có thể null:
Collectors.toConcurrentMap(Sale::sku, Sale::quantity, Integer::sum)
```

Nếu một `Sale.sku()` là null, không thể giả định collector sẽ tạo được một entry khóa null. Với `groupingByConcurrent`, classifier trả null cũng không được chấp nhận theo hợp đồng triển khai collector chuẩn.

Tùy nghiệp vụ, bạn có thể:

- **Lọc bản ghi không hợp lệ:** `filter(sale -> sale.sku() != null)`, nếu bỏ bản ghi là chính sách cho phép.
- **Thay bằng mã đại diện:** `sku == null ? "UNKNOWN" : sku`, nếu thực sự muốn gom tất cả null vào một nhóm cụ thể.
- **Báo lỗi xác thực:** xử lý trước khi aggregate khi null là vi phạm hợp đồng.
- **Biểu diễn nhiều trạng thái:** dùng kết quả có enum hoặc record rõ nghĩa nếu “không rõ SKU” khác với một nhóm hợp lệ.

Không dùng một merge function để cố xử lý khóa null; merge function được dùng **sau khi mapper đã tạo khóa**, và không biến một khóa không được map hỗ trợ thành hợp lệ.

### Merge function có thể trả null

Trong `Map.merge`, nếu remapping function trả null, entry liên quan có thể bị xóa. Vì vậy không viết merge function trả null khi mục tiêu là đảm bảo một khóa luôn có giá trị, trừ khi việc xóa là chủ ý và đã kiểm chứng hợp đồng. Nếu bài toán là kiểm tra trùng khóa nghiêm ngặt, overload hai đối số của `toConcurrentMap` giúp ném lỗi thay vì bỏ dữ liệu.

## 10. Khi nào nên dùng groupingByConcurrent, khi nào dùng toConcurrentMap?

| Mục tiêu | Collector phù hợp | Lý do |
| --- | --- | --- |
| Mỗi khu vực có **danh sách** đơn hàng | `groupingByConcurrent(Order::region)` | Một khóa có thể ứng với nhiều phần tử |
| Đếm đơn hàng theo khu vực | `groupingByConcurrent(Order::region, counting())` | Downstream chỉ tạo một số đếm |
| Tổng số lượng theo SKU | `toConcurrentMap(Sale::sku, Sale::quantity, Integer::sum)` | Mỗi khóa gộp thành một giá trị |
| Chuyển các ID duy nhất thành đối tượng | `toConcurrentMap(Entity::id, e -> e)` | Khóa trùng là lỗi |
| Chọn giá trị lớn nhất mỗi khóa | `toConcurrentMap(keyMapper, valueMapper, maxMerge)` | Merge xác định kết quả |
| Nhóm theo nhiều cấp | `groupingByConcurrent(..., downstream)` | Có thể kết hợp downstream theo yêu cầu |
| Cần bảo toàn thứ tự gặp đầu tiên | Cân nhắc `groupingBy` hoặc thuật toán có order rõ ràng | Concurrent collectors thường `UNORDERED` |
| Chỉ cần một giá trị Boolean | `anyMatch`, `allMatch`, `noneMatch` | Không nhất thiết tạo một Map |

Cả hai loại trả concurrent map, nhưng **mục tiêu aggregation** khác nhau. Với `groupingByConcurrent`, downstream có thể tạo cả `List<T>`, `Set<T>`, statistics hoặc bản đồ con. Với `toConcurrentMap`, bạn chủ động định nghĩa **một giá trị (U)** cho từng khóa và cách gộp khi trùng.

**Đừng tự viết `parallelStream().forEach(map::put)` để thay collector.** `ConcurrentMap.put` có thể an toàn cho một lần cập nhật, nhưng `put` đơn lẻ sẽ ghi đè giá trị khi khóa trùng, dễ mất thông tin. Với bài toán cộng dồn, dùng merge/collector để mô tả phép tổng hợp nguyên tử đúng hơn.

## 11. Kiểm tra Characteristics và finisher

Các collector có thể công bố `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`. Hãy kiểm tra **đặc tính thực sự của collector** thay vì suy đoán chỉ từ một phần tên API.

Ví dụ, một collector `groupingByConcurrent` dùng downstream `toList` có thể có `IDENTITY_FINISH` nếu kết quả container có thể dùng trực tiếp làm kết quả cuối. Khi thêm `collectingAndThen(..., List::copyOf)`, downstream cần finisher thật sự, nên không được công bố `IDENTITY_FINISH` cho collector hoàn chỉnh.

### Chương trình Java 17: các Characteristics và kết quả read-only

Tạo tệp **`ConcurrentCollectorCharacteristicsDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ConcurrentCollectorCharacteristicsDemo {
    public static void main(String[] args) {
        Collector<String, ?, ConcurrentMap<Integer, List<String>>> basic =
                Collectors.groupingByConcurrent(String::length);

        Collector<String, ?, ConcurrentMap<Integer, List<String>>> finished =
                Collectors.groupingByConcurrent(
                        String::length,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf));

        System.out.println("concurrent=" + basic.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));
        System.out.println("unordered=" + basic.characteristics()
                .contains(Collector.Characteristics.UNORDERED));
        System.out.println("identityFinish=" + basic.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("finishedIdentity=" + finished.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));

        List<String> group = List.of("cat", "ant", "bee")
                .parallelStream()
                .collect(finished)
                .get(3);
        try {
            group.add("new");
            System.out.println("modifiable=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("modifiable=false");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ConcurrentCollectorCharacteristicsDemo.java
java ConcurrentCollectorCharacteristicsDemo
```

**Stdout chính xác:**

```text
concurrent=true
unordered=true
identityFinish=true
finishedIdentity=false
modifiable=false
```

`basic` có các Characteristics của collector concurrent trả kết quả danh sách thông thường. `finished` dùng downstream `collectingAndThen` để biến danh sách nhóm thành kết quả `List.copyOf` không sửa được, nên không có `IDENTITY_FINISH`. Chương trình **không in trực tiếp thứ tự** các phần tử trong nhóm, vì collector concurrent không cam kết thứ tự gặp.

**Lưu ý:** một kết quả `List` không sửa được về mặt cấu trúc không làm các object mutable bên trong nó bất biến. Với khóa và giá trị phức tạp, vẫn phải thiết kế an toàn truy cập/ghi đồng thời theo hợp đồng của từng loại dữ liệu.

## 12. Tạo map theo thứ tự khóa bằng ConcurrentSkipListMap

Một `ConcurrentMap` không đồng nghĩa với một `SortedMap`. `ConcurrentHashMap` không hứa thứ tự key, còn `ConcurrentSkipListMap` hỗ trợ thứ tự khóa đã chọn.

Với `groupingByConcurrent`, overload `mapFactory` có thể dùng:

```java
ConcurrentMap<String, List<Order>> grouped =
        orders.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Order::region,
                        java.util.concurrent.ConcurrentSkipListMap::new,
                        Collectors.toList()));
```

Đây là mảnh mã minh họa, `Order::region` và `orders` được định nghĩa trong ứng dụng. Khi dùng map factory có thứ tự khóa, việc duyệt **key** được sắp xếp, nhưng phần tử bên trong mỗi `List<Order>` của concurrent grouping **vẫn không có encounter-order guarantee**.

Với `toConcurrentMap`, overload bốn đối số cũng chấp nhận `ConcurrentSkipListMap::new`. Lựa chọn này đặc biệt hữu ích khi xuất báo cáo hoặc cần hiển thị map theo thứ tự mã/khóa tự nhiên mà không sort một bản sao ở bước cuối.

**Đánh đổi:** map có thứ tự có thể có chi phí khác `ConcurrentHashMap`. Đừng chọn một map factory chỉ vì nhìn đẹp trong `println` khi ứng dụng thực sự không cần thứ tự key.

## 13. Parallel Stream và quyền sở hữu kết quả sau collect

Trong quá trình terminal `collect` chạy, Stream framework quản lý accumulator và phối hợp công việc theo hợp đồng của collector. Sau khi terminal trả kết quả:

1. **Map trả về** có thể là `ConcurrentMap`, phù hợp một số thao tác đọc/ghi song song theo hợp đồng của implementation.
2. **Giá trị map** có thể là list, set, statistics hoặc domain object. **Đừng mặc định** chúng có thread safety chỉ vì bản thân map là concurrent.
3. **Các thao tác kết hợp nhiều bước** (kiểm tra rồi cập nhật, đọc hai nhóm rồi thay đồng thời) không tự trở thành transaction. Dùng phương thức nguyên tử phù hợp, lock hoặc thiết kế bất biến theo yêu cầu.
4. **Đọc trong khi đang cập nhật** thường có hợp đồng visibility/consistency cụ thể của collection. Không suy luận rằng một vòng lặp qua toàn bộ map đang thay đổi sẽ là snapshot bất biến tức thời.
5. **Nếu chỉ cần báo cáo cuối không thay đổi**, có thể chuyển kết quả sang các cấu trúc immutable hoặc bản sao phù hợp và xuất bản sau khi thu thập hoàn tất.

Ví dụ dưới đây là **mẫu sai** nếu nhiều thread có thể gọi cùng lúc:

```java
// Không an toàn chỉ vì buckets là ConcurrentMap:
buckets.get("A").add(item);
```

Nếu `buckets.get("A")` là `ArrayList`, thao tác thêm từ nhiều thread có thể gây race. Giải pháp cần dựa trên thiết kế dữ liệu: có thể dùng queue đồng thời, dùng `compute` với cơ chế phù hợp, hoặc chỉ cho phép cập nhật trong pha collect được framework quản lý.

Không dùng `Collections.synchronizedList` theo thói quen để che đi một mô hình cập nhật không rõ lifecycle: cần xác định cả quyền sở hữu, khả năng duyệt đồng thời, tính nhất quán của các bước xử lý và hiệu năng.

## 14. Hiệu năng: concurrent collector không phải lựa chọn mặc định tốt nhất

Các collectors concurrent có thể có lợi khi:
- Nguồn dữ liệu đủ lớn và dễ chia.
- Phép xử lý mỗi phần tử độc lập.
- Công việc CPU-bound đủ nặng để bù chi phí chia/gộp.
- Số nhóm/khóa đủ phân tán để tránh contention lớn trên một nhóm.
- Không cần giữ encounter order.

Chúng có thể kém lợi khi:
- Dataset nhỏ hoặc mapper/classifier rất rẻ.
- Hầu hết dữ liệu dồn vào **một khóa**, gây tranh chấp cập nhật.
- Downstream collector phải đồng bộ các cập nhật vào cùng một nhóm.
- Cần sắp xếp, xác định “bản đầu tiên”, hoặc hậu xử lý danh sách lớn.
- Truy cập nguồn I/O blocking, database hay network có giới hạn kết nối.
- Một lượng lớn thread khác cũng dùng tài nguyên Fork/Join chung.

Trong nhiều JDK, parallel Stream thường chạy dựa trên cơ chế Fork/Join và có thể dùng common pool. **Không dựa vào số thread hoặc thứ tự lịch trình như một hợp đồng cố định.** Muốn kiểm tra throughput và contention, dùng workload thật, làm nóng JIT, lặp nhiều lần và công cụ benchmark như **JMH**. Đo cả tính đúng đắn, bộ nhớ/GC và số lượng khóa trùng; chỉ bật parallel khi có lợi ích đo được.

### So sánh groupingBy với groupingByConcurrent

- `groupingBy` có thể phải gộp các map từng phần trong parallel Stream.
- `groupingByConcurrent` có thể tích lũy đồng thời và giảm bớt công việc kết hợp map trong trường hợp phù hợp.
- Nhưng `groupingByConcurrent` có hợp đồng `UNORDERED`. Nếu thứ tự trong mỗi nhóm là yêu cầu, `groupingBy` cùng pipeline ordered hoặc một thuật toán có thứ tự rõ ràng có thể dễ phù hợp hơn.
- Với nhóm rất nóng (hot key), việc đồng bộ ở downstream và contention có thể khiến concurrent grouping không nhanh hơn.

**Đúng trước, nhanh sau.** Tối ưu hóa không được đổi ý nghĩa nghiệp vụ mà không được phép, đặc biệt là chọn record đầu/cuối theo encounter order và gộp giá trị phụ thuộc thứ tự.

## 15. Các lỗi phổ biến

1. **Cho rằng parallelStream đòi mọi collector phải CONCURRENT.** Sai; collector không concurrent vẫn có thể dùng bằng accumulator độc lập và combiner.
2. **Cho rằng ConcurrentMap khiến List ở value thread-safe.** Sai; map và value có các hợp đồng concurrency riêng.
3. **Cho rằng groupingByConcurrent giữ thứ tự List nguồn.** Không có encounter-order guarantee; collector là `UNORDERED`.
4. **In thẳng ConcurrentHashMap rồi kiểm thử thứ tự key.** Không được bảo đảm; sort key hoặc chọn map factory có thứ tự.
5. **Dùng toConcurrentMap hai đối số khi khóa có thể trùng.** Ném `IllegalStateException`; cần merge function nếu trùng hợp lệ.
6. **Dùng merge (old,new) -> new để chọn bản cuối của List.** Trên collector unordered parallel, thứ tự cập nhật không đồng nghĩa encounter order.
7. **Dùng phép trừ hoặc phép gộp không kết hợp.** Có thể đổi kết quả theo lịch trình song song.
8. **Đánh đồng associative với commutative.** Phép nối chuỗi có thể associative nhưng không commutative; không phù hợp nếu kết quả cần độc lập thứ tự của concurrent aggregation.
9. **Trả null từ mapper để đại diện “không có”.** Concurrent maps thường cấm null; hãy lọc, chuẩn hóa hoặc báo lỗi theo hợp đồng.
10. **Trả null từ merge mà không chủ ý xóa entry.** Có thể làm mất dữ liệu.
11. **Sửa source Stream trong classifier hoặc mapper.** Vi phạm tính non-interfering và dễ race.
12. **Dùng state mutable toàn cục trong predicate/classifier.** Có thể phân loại không nhất quán trên nhiều thread.
13. **Tưởng groupingByConcurrent luôn nhanh hơn groupingBy.** Contention, số lượng nhóm và downstream quyết định lợi ích.
14. **Tưởng CONCURRENT đồng nghĩa có thread mới cho mỗi phần tử.** Framework chọn cơ chế chia công việc.
15. **Tự khai báo CONCURRENT cho custom Collector dùng ArrayList không đồng bộ.** Sai hợp đồng, có thể gây mất dữ liệu.
16. **Bỏ qua IDENTITY_FINISH khi có collectingAndThen.** Một finisher thật sự không được bỏ qua.
17. **Nhầm mapFactory có thứ tự với thứ tự merge value.** Sorted key không bảo đảm encounter order của phần tử trong nhóm hoặc quy tắc giữ bản ghi.
18. **Giữ kết quả ConcurrentMap rồi giả định mọi thao tác nhiều bước là nguyên tử.** Cần cơ chế đồng bộ/transaction phù hợp.
19. **Tối ưu mà chưa benchmark.** Collector concurrent có overhead và không bảo đảm tăng tốc.

## 16. Quyết định API trong một phút

| Câu hỏi | Gợi ý |
| --- | --- |
| Cần **danh sách tất cả phần tử** theo khóa, không cần order? | `groupingByConcurrent(classifier)` |
| Cần **số lượng** mỗi khóa? | `groupingByConcurrent(classifier, counting())` |
| Cần thống kê theo khóa? | `groupingByConcurrent(classifier, summarizingInt(...))` |
| Cần Map từ khóa duy nhất sang giá trị? | `toConcurrentMap(keyMapper, valueMapper)` |
| Khóa trùng hợp lệ, cần cộng/tối đa? | `toConcurrentMap(keyMapper, valueMapper, merge)` |
| Cần sắp xếp khóa? | Overload `mapFactory` với `ConcurrentSkipListMap` |
| Cần giữ phần tử **đầu tiên theo encounter order**? | Cân nhắc `groupingBy` hoặc thuật toán ordered cụ thể |
| Chỉ cần một List kết quả? | `toList()` hoặc `collect(toCollection(...))` |
| Chỉ cần kiểm tra có phần tử khớp? | `anyMatch(predicate)`, không cần tạo Map |

Trước khi dùng một collector concurrent, hãy trả lời ba câu hỏi: **(1) Có cần encounter order không? (2) Dữ liệu cùng khóa có thể được gộp theo phép toán không phụ thuộc thứ tự không? (3) Downstream và dữ liệu kết quả có hợp đồng đồng thời phù hợp không?** Nếu chưa rõ, đừng thay `groupingBy` bằng `groupingByConcurrent` chỉ vì tên chứa từ “Concurrent”.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `groupingByConcurrent(String::length)` trả kiểu Map nào và mặc định mỗi value là gì?

**Đáp án:** Kiểu trả về là `ConcurrentMap<Integer,List<String>>`; mỗi value là danh sách các chuỗi có cùng độ dài. Thứ tự phần tử trong danh sách nhóm không được bảo đảm.

**Câu 2.** Vì sao `groupingByConcurrent(key, counting())` vẫn có thể là collector concurrent dù `counting()` không tự là concurrent collector?

Vì collector bên ngoài tổ chức việc tích lũy đồng thời và bảo vệ downstream accumulator khi cần. Không nên suy ra state downstream được phép tự sửa từ nhiều thread bất kỳ.

**Câu 3.** `toConcurrentMap(keyMapper,valueMapper)` làm gì nếu hai phần tử có cùng khóa?

**Đáp án:** Ném `IllegalStateException` vì overload này không có merge function.

**Câu 4.** Muốn cộng `quantity` cho từng `sku` trên một Stream song song, viết như thế nào?

```java
ConcurrentMap<String, Integer> totals = sales.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Sale::sku, Sale::quantity, Integer::sum));
```

Đây là mảnh mã có `Sale` và `sales` từ chương trình của bạn. Khi có khóa trùng, `Integer::sum` gộp các giá trị thành tổng.

**Câu 5.** ConcurrentMap có đảm bảo `map.get("A").add(item)` an toàn nếu value là ArrayList không?

**Không.** `ConcurrentMap` bảo vệ hoạt động trên map theo hợp đồng, không tự biến `ArrayList` ở value thành thread-safe.

**Câu 6.** Với collector `UNORDERED`, có thể dùng merge `(first,later) -> first` để luôn chọn bản ghi đầu tiên trong List không?

**Không nên.** Các tham số trong merge mô tả quan hệ giữa giá trị đã lưu và giá trị mới được gộp, không hứa đại diện encounter order. Hãy chọn theo một thuộc tính dữ liệu rõ ràng nếu cần kết quả xác định.

**Câu 7.** Vì sao dùng `ConcurrentSkipListMap` làm mapFactory chưa đủ để bảo đảm danh sách trong mỗi group đúng thứ tự nguồn?

Vì mapFactory quyết định cấu trúc và thứ tự **khóa**, còn grouping concurrent không cam kết encounter order của **các phần tử trong value list**.

**Câu 8.** Khi nào có thể có lợi khi dùng collector concurrent?

Khi workload đủ lớn, phân loại độc lập, không cần encounter order, gộp đúng, và benchmark cho thấy lợi ích thực tế. Không có cam kết tăng tốc tuyệt đối.

**Câu 9.** `CONCURRENT` và `IDENTITY_FINISH` có giống nhau không?

**Không.** `CONCURRENT` liên quan khả năng cập nhật accumulator đồng thời; `IDENTITY_FINISH` liên quan việc dùng state tích lũy trực tiếp làm kết quả cuối.

**Câu 10.** Nếu muốn giá trị lớn nhất theo key nhưng có hai record cùng điểm cao nhất, cần làm gì?

Xác định quy tắc tie-breaker (ví dụ ID hoặc timestamp bổ sung). Một merge function không có quy tắc tie có thể chọn record khác nhau theo thứ tự cập nhật song song.

**Ghi nhớ:** `groupingByConcurrent()` chia dữ liệu thành **các nhóm** trong `ConcurrentMap`; `toConcurrentMap()` tạo **một giá trị trên mỗi khóa** và cần merge function nếu khóa có thể trùng. Cả hai hỗ trợ concurrent reduction, nhưng **collector concurrent khác với tính an toàn đồng thời của từng value**, và `UNORDERED` không hứa giữ phần tử đầu tiên. Hãy thiết kế phép gộp kết hợp được, xử lý null và duplicate rõ ràng, đồng thời đo hiệu năng thay vì phỏng đoán.
