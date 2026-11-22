# Phân biệt collect trên Stream song song và Collector đồng thời

Trong Java Stream API, **Stream chạy song song** (*parallel stream*) và **Collector đồng thời** (*concurrent collector*) là hai khái niệm khác nhau. Gọi `parallelStream()` hoặc `parallel()` cho phép framework phân chia dữ liệu để xử lý bằng nhiều worker. Trong khi đó, một Collector có đặc tính `CONCURRENT` cho biết **nhiều worker được phép gọi accumulator trên cùng một container kết quả**, khi framework lựa chọn phương án tích lũy đồng thời phù hợp.

Vì vậy, cả hai nhận định sau đều sai:

- “Đã dùng `parallelStream()` thì collector phải là thread-safe để nhiều thread cùng sửa một `ArrayList`.”
- “Muốn xử lý Stream song song thì bắt buộc dùng `groupingByConcurrent` hoặc `toConcurrentMap`.”

Một collector **không có `CONCURRENT`** vẫn có thể hoạt động đúng trên parallel stream: framework tạo những container riêng cho các nhánh, tích lũy cục bộ, sau đó gộp bằng `combiner`. Ngược lại, collector khai báo `CONCURRENT` phải thực sự chịu được việc nhiều worker truy cập **cùng container**.

Bài học thuộc chương **Thu thập đồng thời** của module **JAVA_STREAM_API**. Nó tiếp nối pipeline lazy, `filter`, `map`, `reduce` và `collect`, đồng thời liên kết với grouping, collector tùy chỉnh, `Spliterator` và ngữ nghĩa xử lý song song. Sau bài này, người học cần phân biệt *parallel processing*, *concurrent reduction*, yêu cầu thứ tự, hợp đồng Collector và những đánh đổi về hiệu năng, trạng thái, tài nguyên.

## 1. Hai câu hỏi độc lập khi thiết kế phép thu thập

Trước mỗi lời gọi `collect`, hãy hỏi:

1. **Nguồn/pipeline đang ở chế độ nào?** `stream()` thường tạo Stream tuần tự; `parallelStream()` hoặc `parallel()` yêu cầu chế độ song song.
2. **Collector công bố khả năng tích lũy nào?** Có đặc tính `CONCURRENT` hay không? Có `UNORDERED` hay không? Accumulator, combiner, finisher có tuân thủ hợp đồng của Collector hay không?

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(4, 1, 3, 2);

// Pipeline song song; Collector.toList() KHÔNG phải concurrent collector.
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 10)
        .collect(Collectors.toList());

System.out.println(result); // [40, 10, 30, 20]
```

Kết quả vẫn đúng và giữ encounter order của `List`, dù `Collectors.toList()` không khai báo `CONCURRENT`. Thư viện chịu trách nhiệm tích lũy và gộp các phần kết quả theo hợp đồng.

### 1.1. Bảng phân biệt

| Khía cạnh | Parallel Stream | Concurrent Collector |
|---|---|---|
| Cách xác định | `parallelStream()`, `parallel()`; kiểm tra bằng `isParallel()` | `collector.characteristics()` chứa `CONCURRENT` |
| Tác động chính | Cho phép xử lý pipeline bằng nhiều worker | Cho phép nhiều worker **tích lũy đồng thời trên cùng container** |
| Có buộc phải đi cùng nhau? | Không | Không |
| Có bảo đảm tăng tốc? | Không | Không |
| Tự bảo vệ side effect bên ngoài pipeline? | Không | Không |
| Giữ encounter order? | Vẫn có thể, tùy nguồn/hoạt động | Phụ thuộc `UNORDERED` và ngữ nghĩa collector |
| Có cần combiner hợp lệ? | Có, khi phép thu thập cần gộp các phần | Có, Collector vẫn phải có combiner đúng hợp đồng |

**Không nhầm chế độ xử lý với đặc tính Collector:** `isParallel() == true` chỉ mô tả cấu hình Stream. Nó không cho biết các worker có đang chia sẻ một container trong quá trình `collect` hay không.

## 2. Ôn lại năm thành phần của Collector

Giao diện `Collector<T, A, R>` mô tả cách giảm dãy đầu vào kiểu `T` vào một trạng thái tích lũy `A`, sau đó cho kết quả `R`.

| Thành phần | Vai trò |
|---|---|
| `supplier` | Tạo một container tích lũy mới |
| `accumulator` | Đưa một phần tử `T` vào container `A` |
| `combiner` | Kết hợp hai container tích lũy |
| `finisher` | Chuyển `A` thành `R` |
| `characteristics` | Mô tả các đảm bảo như `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH` |

Với `Collectors.toList()`, trạng thái trung gian thường có ý nghĩa một danh sách đang được tích lũy. Với `Collectors.summingLong(...)`, trạng thái có thể biểu diễn một tổng. Với `groupingBy(...)`, trạng thái chứa các kết quả nhóm. Collector có quyền sử dụng những trạng thái mutable **nội bộ**; điều đó không có nghĩa nó tự động cho phép nhiều worker sửa **cùng một** trạng thái.

Collector hợp lệ phải đáp ứng ít nhất ba nhóm yêu cầu:

- **Đơn vị (*identity*):** gộp một kết quả đã tích lũy với container rỗng từ supplier không đổi ý nghĩa kết quả.
- **Kết hợp (*associativity*):** tích lũy một lần và chia thành các nhánh rồi gộp phải cho kết quả tương đương.
- **Tương đương (*equivalence*):** cách phân chia/chạy hợp lệ cho kết quả có cùng ý nghĩa; với collector không `UNORDERED`, thứ tự đầu ra có thể là một phần của ý nghĩa đó.

Không có hợp đồng kết hợp đúng thì một collector có thể “chạy ổn” ở chế độ tuần tự nhưng mất phần tử hoặc sai tổng khi chạy song song, bất kể có khai báo `CONCURRENT` hay không.

## 3. Hai cách thực thi phép thu thập song song

### 3.1. Tích lũy trên container riêng rồi combiner gộp

Đây là mô hình phù hợp với `Collectors.toList()` và nhiều collector thông thường:

```text
Nguồn có thứ tự: [A, B, C, D, E, F]
                        |
                 chia thành nhánh
                 /              \
              [A,B,C]          [D,E,F]
                 |                |
              supplier         supplier
                 |                |
          container 1         container 2
          [A, B, C]           [D, E, F]
                 \                /
                    combiner
                        |
                 [A, B, C, D, E, F]
                        |
                     finisher
```

Mỗi nhánh có thể dùng `ArrayList` không thread-safe **riêng**, vì không có hai worker đồng thời sửa cùng một container trong cách tích lũy thông thường. Framework quản lý cách phân nhánh và kết hợp. `combiner` ghép các trạng thái trung gian thành kết quả cuối, giữ ràng buộc encounter order khi collector và nguồn yêu cầu.

Ví dụ:

```java
List<String> ordered = Arrays.asList("A", "B", "C", "D")
        .parallelStream()
        .collect(Collectors.toList());

System.out.println(ordered); // [A, B, C, D]
```

**Không cần** đổi sang `Collections.synchronizedList` hay tự tạo `ConcurrentLinkedQueue` chỉ vì Stream được chạy song song. Collector chuẩn đã được thiết kế cho việc thu thập hợp lệ trên parallel stream.

### 3.2. Tích lũy đồng thời trên một container dùng chung

Collector có `CONCURRENT` có thể cho phép một kiểu thực thi khác:

```text
Nguồn song song: [A, B, C, D, E, F]
            /        |         \
         worker 1  worker 2   worker 3
            \        |         /
           accumulator concurrent
                      |
             container dùng chung
                      |
                   finisher
```

Ở đây, **cùng container** có thể nhận các lời gọi accumulator từ nhiều worker, nên container và phép cập nhật phải chịu được truy cập đồng thời. Một `ConcurrentHashMap` với phép cập nhật thích hợp là nền tảng phổ biến cho các collector Map đồng thời.

Framework **có thể** chọn cách tích lũy đồng thời khi đủ điều kiện; `CONCURRENT` không buộc runtime phải dùng chính xác một container hoặc một chiến lược cụ thể trong mọi tình huống.

## 4. Điều kiện để framework có thể thực hiện concurrent reduction

Trong mô hình `Stream.collect(Collector)`, concurrent reduction trực tiếp vào container chia sẻ được cho phép khi:

1. Stream đang ở **chế độ song song**;
2. Collector có characteristic **`CONCURRENT`**;
3. **Stream không có encounter order**, **hoặc** Collector công bố thêm **`UNORDERED`**.

Có thể ghi nhớ ngắn gọn:

```text
parallel
   AND collector.CONCURRENT
   AND (stream unordered OR collector.UNORDERED)
            |
            v
Framework được phép concurrent reduction
```

Đây là **điều kiện cho phép**, không phải lệnh bắt buộc framework sử dụng phương án ấy. Nếu không thỏa điều kiện cuối, runtime vẫn có thể xử lý Stream song song bằng các container riêng và combiner để giữ yêu cầu encounter order.

| Stream | Collector | Khả năng thu thập |
|---|---|---|
| Tuần tự | Không `CONCURRENT` | Thông thường tích lũy tuần tự |
| Song song, có thứ tự | `toList()` không `CONCURRENT` | Tích lũy phân nhánh và gộp; giữ encounter order |
| Song song, có thứ tự | `CONCURRENT` nhưng không `UNORDERED` | Không được tùy ý bỏ thứ tự; có thể dùng container riêng rồi gộp |
| Song song, có thứ tự | `CONCURRENT` và `UNORDERED` | Có thể tích lũy đồng thời vào container chung |
| Song song, không có thứ tự | Collector `CONCURRENT` | Có thể tích lũy đồng thời |

### 4.1. CONCURRENT khác UNORDERED

**`CONCURRENT`** là cam kết về khả năng gọi accumulator đồng thời trên cùng container. **`UNORDERED`** là cam kết rằng **thứ tự phần tử không góp phần quyết định tính tương đương của kết quả**.

Một Collector có thể `CONCURRENT` mà **không** `UNORDERED` về mặt hợp đồng, khi đó framework phải xem xét thứ tự của nguồn trước khi tích lũy đồng thời. Ngược lại, một collector như `Collectors.toSet()` có thể `UNORDERED` nhưng **không `CONCURRENT`**: kết quả không cần thứ tự, song accumulator vẫn chưa được phép nhận ghi đồng thời trên cùng `HashSet`.

**`IDENTITY_FINISH`** lại là tính chất thứ ba: finisher là phép đồng nhất giữa trạng thái tích lũy và kết quả. Nó **không** tự thể hiện thread safety hoặc tính không thứ tự.

### 4.2. Kiểm tra characteristics bằng code

```java
import java.util.stream.Collector;
import java.util.stream.Collectors;

boolean listConcurrent = Collectors.toList()
        .characteristics()
        .contains(Collector.Characteristics.CONCURRENT);

boolean setUnordered = Collectors.toSet()
        .characteristics()
        .contains(Collector.Characteristics.UNORDERED);

boolean concurrentMap = Collectors.toConcurrentMap(
                String::length, value -> value, (a, b) -> a)
        .characteristics()
        .contains(Collector.Characteristics.CONCURRENT);

System.out.println(listConcurrent); // false
System.out.println(setUnordered);    // true
System.out.println(concurrentMap);   // true
```

`characteristics()` mô tả **hợp đồng của collector**. Kết quả trên không phải bằng chứng rằng một lần chạy đã thực sự sử dụng bao nhiêu thread hay container.

## 5. So sánh các collector Map thường dùng

Hai cặp API liên quan trực tiếp tới bài toán này là `groupingBy`/`groupingByConcurrent` và `toMap`/`toConcurrentMap`.

| Collector | Kết quả thường gặp | `CONCURRENT` | Thứ tự |
|---|---|---|---|
| `Collectors.toMap(...)` | `Map<K, V>` | Không | Không bảo đảm thứ tự duyệt khóa của Map; có thể giữ ngữ nghĩa encounter order khi merge phụ thuộc thứ tự |
| `Collectors.toConcurrentMap(...)` | `ConcurrentMap<K, V>` | Có | Collector `UNORDERED`, không dựa vào “giá trị gặp đầu/cuối” |
| `Collectors.groupingBy(...)` | `Map<K, D>` | Không | Downstream có thể giữ encounter order phù hợp |
| `Collectors.groupingByConcurrent(...)` | `ConcurrentMap<K, D>` | Có | Collector `UNORDERED`, không cam kết thứ tự giá trị trong từng nhóm |
| `Collectors.toList()` | `List<T>` | Không | Giữ encounter order nếu nguồn có thứ tự |
| `Collectors.toSet()` | `Set<T>` | Không | Không bảo đảm encounter order |

Lựa chọn concurrent collector **không đơn thuần là “phiên bản nhanh hơn”**. Nó có thể thay đổi ràng buộc thứ tự mà nghiệp vụ cần, và không phải workload nào cũng hưởng lợi khi nhiều worker cập nhật chung một Map.

### 5.1. groupingBy trên parallel stream vẫn hợp lệ

```java
Map<String, Long> counts = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));
```

Đoạn minh họa giả định `Order` có `getRegion()` trả `String` và danh sách `orders` có những phần tử hợp lệ. Framework có thể tạo các Map của từng nhánh rồi kết hợp. `Collectors.groupingBy` **không cần `CONCURRENT`** để hoạt động đúng trong trường hợp này.

### 5.2. groupingByConcurrent khi không cần encounter order

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> counts = orders.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Order::getRegion,
                Collectors.counting()));
```

`groupingByConcurrent` trả collector có đặc tính concurrent và unordered. Nó có thể hỗ trợ tích lũy đồng thời theo khóa. Đừng hiểu rằng toàn bộ downstream collector như `Collectors.toList()` lập tức trở thành một List thread-safe để ứng dụng tùy ý sửa sau khi thu thập.

### 5.3. toMap và toConcurrentMap khi có khóa trùng

```java
Map<String, Long> totalBySku = orders.parallelStream()
        .collect(Collectors.toMap(
                Order::getSku,
                Order::getAmountCents,
                Long::sum));

ConcurrentMap<String, Long> concurrentTotals = orders.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Order::getSku,
                Order::getAmountCents,
                Long::sum));
```

Hai collector trên cùng giải quyết bài toán **cộng tiền theo mã hàng**, với điều kiện giá trị đầu vào hợp lệ và phép tổng không tràn `long`. Việc khác nhau ở **chiến lược tích lũy** và đặc tính kết quả, không phải ở công thức cộng.

Nếu bỏ `mergeFunction` khỏi `toMap` hoặc `toConcurrentMap` mà có khóa trùng, collector có thể ném `IllegalStateException`. Không dùng `(oldValue, newValue) -> newValue` trong `toConcurrentMap` để suy ra “bản ghi mới nhất”: collector unordered không bảo đảm thứ tự cập nhật theo dữ liệu đầu vào. Nếu cần mới nhất theo timestamp/version, hãy chọn cực đại theo một quy tắc so sánh xác định.

## 6. Ví dụ Java 8 hoàn chỉnh: cùng dữ liệu, hai chiến lược

Chương trình sau chạy từ **Java 8**, minh họa:

- Thu thập thành List từ parallel stream mà **không cần concurrent collector**.
- So sánh `toMap` với `toConcurrentMap` khi cộng số theo khóa.
- So sánh `groupingBy` với `groupingByConcurrent` khi đếm bản ghi.
- Nhìn rõ vấn đề thứ tự danh sách trong từng nhóm.
- Kiểm tra characteristic `CONCURRENT` của hai kiểu collector.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ConcurrentCollectorDemo {
    static final class Order {
        private final String id;
        private final String region;
        private final String sku;
        private final long amountCents;
        private final boolean paid;

        Order(String id, String region, String sku,
                long amountCents, boolean paid) {
            this.id = id;
            this.region = region;
            this.sku = sku;
            this.amountCents = amountCents;
            this.paid = paid;
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        String getSku() {
            return sku;
        }

        long getAmountCents() {
            return amountCents;
        }

        boolean isPaid() {
            return paid;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("A1", "BAC", "P01", 100L, true),
                new Order("A2", "NAM", "P02", 250L, true),
                new Order("A3", "BAC", "P01", 150L, true),
                new Order("A4", "BAC", "P03", 500L, false),
                new Order("A5", "NAM", "P02", 350L, true),
                new Order("A6", "BAC", "P01", 200L, true)
        );

        // 1) Pipeline song song với collector KHÔNG CONCURRENT.
        List<String> paidIds = orders.parallelStream()
                .filter(Order::isPaid)
                .map(Order::getId)
                .collect(Collectors.toList());

        System.out.println(paidIds);
        // [A1, A2, A3, A5, A6] - encounter order của List nguồn

        // 2) Gộp Map từng nhánh bằng toMap.
        Map<String, Long> totalsBySku = orders.parallelStream()
                .filter(Order::isPaid)
                .collect(Collectors.toMap(
                        Order::getSku,
                        Order::getAmountCents,
                        Long::sum));

        // 3) Collector đồng thời và không có thứ tự.
        ConcurrentMap<String, Long> concurrentTotals =
                orders.parallelStream()
                        .filter(Order::isPaid)
                        .collect(Collectors.toConcurrentMap(
                                Order::getSku,
                                Order::getAmountCents,
                                Long::sum));

        System.out.println(totalsBySku.get("P01")); // 450
        System.out.println(concurrentTotals.get("P01")); // 450
        System.out.println(concurrentTotals.get("P02")); // 600

        // 4) Cả groupingBy và groupingByConcurrent đều đếm đúng.
        Map<String, Long> normalCounts = orders.parallelStream()
                .filter(Order::isPaid)
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.counting()));

        ConcurrentMap<String, Long> concurrentCounts =
                orders.parallelStream()
                        .filter(Order::isPaid)
                        .collect(Collectors.groupingByConcurrent(
                                Order::getRegion,
                                Collectors.counting()));

        System.out.println(normalCounts.get("BAC")); // 3
        System.out.println(concurrentCounts.get("BAC")); // 3
        System.out.println(concurrentCounts.get("NAM")); // 2

        // 5) groupBy giữ encounter order trong List của từng nhóm.
        Map<String, List<String>> idsByRegion = orders.parallelStream()
                .filter(Order::isPaid)
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.mapping(Order::getId, Collectors.toList())));

        ConcurrentMap<String, List<String>> concurrentIdsByRegion =
                orders.parallelStream()
                        .filter(Order::isPaid)
                        .collect(Collectors.groupingByConcurrent(
                                Order::getRegion,
                                Collectors.mapping(
                                        Order::getId,
                                        Collectors.toList())));

        System.out.println(idsByRegion.get("BAC")); // [A1, A3, A6]

        // Không dựa vào thứ tự của List trong concurrent collector.
        System.out.println(
                new HashSet<>(idsByRegion.get("BAC")).equals(
                        new HashSet<>(concurrentIdsByRegion.get("BAC"))));
        // true - cùng nội dung, dù thứ tự có thể khác

        // 6) Kiểm tra hợp đồng của collector, không suy từ số thread.
        boolean listIsConcurrent = Collectors.toList()
                .characteristics()
                .contains(Collector.Characteristics.CONCURRENT);

        boolean groupingIsConcurrent =
                Collectors.groupingByConcurrent(
                                Order::getRegion,
                                Collectors.counting())
                        .characteristics()
                        .contains(Collector.Characteristics.CONCURRENT);

        System.out.println(listIsConcurrent);     // false
        System.out.println(groupingIsConcurrent); // true
    }
}
```

**Diễn giải:** Với năm đơn đã thanh toán, tổng tiền theo SKU là `P01 = 450` và `P02 = 600`; số đơn theo khu vực là `BAC = 3`, `NAM = 2`. Hai chiến lược Map đều cho cùng kết quả số học. Sự khác biệt quan trọng xuất hiện ở **đặc tính thu thập**: List từ `groupingBy` giữ encounter order của các đơn trong mỗi nhóm, còn `groupingByConcurrent` không cam kết thứ tự ấy.

Chương trình cố tình dùng vài bản ghi để dễ quan sát **ngữ nghĩa API**, không phải để chứng minh lợi ích hiệu năng. Ở kích thước nhỏ, overhead của parallel stream và concurrent map có thể lớn hơn công việc thực.

## 7. Vì sao toList() không thread-safe vẫn dùng được với parallelStream()?

Đây là câu hỏi phỏng vấn rất phổ biến. `ArrayList` không cho phép nhiều thread cùng `add` vào **một instance** nếu không đồng bộ. Nhưng `Collectors.toList()` **không cam kết** rằng mọi worker cùng thêm vào một instance `ArrayList`.

Trong phép mutable reduction thông thường, framework có thể:

1. Tạo `List` riêng cho một nhánh.
2. Đưa các phần tử của nhánh đó vào `List` riêng.
3. Gộp các `List` trung gian bằng combiner.
4. Trả danh sách cuối khi `collect` kết thúc.

Điều đó khác hoàn toàn với:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> unsafeSharedList = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(unsafeSharedList::add); // SAI.
```

Ở ví dụ sai, **chính chương trình** tạo một `ArrayList` ngoài pipeline rồi chia sẻ nó cho mọi action. Framework không kiểm soát việc gộp trạng thái ấy, và `ArrayList` không thread-safe. Kết quả có thể thiếu phần tử, hỏng dữ liệu hoặc gây lỗi.

### 7.1. Overload collect(supplier, accumulator, combiner)

`Stream.collect` còn có overload ba tham số, cho phép tự mô tả mutable reduction:

```java
List<Integer> safeList = java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(
                ArrayList::new,
                List::add,
                (left, right) -> left.addAll(right));

System.out.println(safeList.size()); // 10000
```

Ở đây `supplier` tạo container riêng và `combiner` gộp chúng theo hợp đồng. Không đặt một `ArrayList` tĩnh, dùng chung ở supplier; nếu supplier luôn trả về **cùng container**, thuật toán có thể bị race khi chạy song song.

**Lưu ý:** overload này không nhận một đối tượng `Collector` với `characteristics()`; nó vẫn dựa trên cơ chế tích lũy phân nhánh và combiner. Không thể tùy ý khai báo “concurrent” cho nó chỉ bằng cách đổi từ `stream()` sang `parallelStream()`.

## 8. Tự viết concurrent collector: chỉ công bố khi accumulator thực sự an toàn

Đôi khi collector chuẩn không biểu diễn được bài toán. Lúc đó, một custom collector muốn công bố `CONCURRENT` phải đảm bảo:

- `supplier` tạo container mới hợp lệ, không trả lại một container dùng chung toàn cục cho mọi lần thu thập.
- `accumulator` chịu được nhiều lời gọi đồng thời trên **cùng container**.
- `combiner` vẫn kết hợp đúng hai container khi framework chọn cách gộp phân nhánh.
- `finisher` chỉ công bố `IDENTITY_FINISH` nếu thật sự không cần biến đổi `A` thành `R`.
- `UNORDERED` chỉ được công bố khi thứ tự gặp phần tử không thay đổi ý nghĩa kết quả.

### 8.1. Ví dụ collector concurrent dùng LongAdder

`LongAdder` trong `java.util.concurrent.atomic` hỗ trợ tích lũy số lượng hiệu quả dưới tranh chấp. Collector dưới đây đếm số phần tử của Stream. Mỗi phần tử làm tăng counter; kết quả cuối là kiểu `Long` nên **không** khai báo `IDENTITY_FINISH`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;

public class ConcurrentCountCollectorDemo {
    public static void main(String[] args) {
        Collector<String, LongAdder, Long> concurrentCount =
                Collector.of(
                        LongAdder::new,
                        (counter, value) -> counter.increment(),
                        (left, right) -> {
                            left.add(right.sum());
                            return left;
                        },
                        LongAdder::sum,
                        Collector.Characteristics.CONCURRENT,
                        Collector.Characteristics.UNORDERED);

        List<String> names = Arrays.asList("An", "Bình", "Chi", "Dũng");

        long count = names.parallelStream()
                .collect(concurrentCount);

        System.out.println(count); // 4
        System.out.println(concurrentCount.characteristics().contains(
                Collector.Characteristics.CONCURRENT)); // true
    }
}
```

Collector này có ý nghĩa **đếm**, không phụ thuộc thứ tự, nên `UNORDERED` phù hợp. `LongAdder.increment()` hỗ trợ cập nhật đồng thời. Combiner cộng tổng của nhánh phải vào nhánh trái nếu framework sử dụng nhiều container. `LongAdder::sum` chỉ được dùng để tạo kết quả khi quá trình thu thập đã kết thúc; đọc tổng trong lúc nhiều thread vẫn đang cập nhật có thể chỉ là giá trị quan sát chưa ổn định.

Trong thực tế, `Collectors.counting()` hoặc `Stream.count()` đơn giản hơn nhiều nếu chỉ cần đếm. Ví dụ `LongAdder` nhằm làm rõ **tại sao khai báo `CONCURRENT` phải đi cùng thiết kế accumulator an toàn**, không phải khuyến nghị luôn tự viết collector thay API chuẩn.

### 8.2. Ví dụ sai: khai báo CONCURRENT cho ArrayList

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

// SAI: tự công bố CONCURRENT dù ArrayList.add không thread-safe.
Collector<String, List<String>, List<String>> broken =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED);
```

Ở collector trên, khi được phép tích lũy đồng thời, nhiều worker có thể cùng sửa một `ArrayList`. Điều này gây data race. Việc thêm `CONCURRENT` **không tự làm container trở nên thread-safe**; nó là **lời cam kết của người viết collector** đối với framework.

Còn một lỗi khác: đánh dấu `UNORDERED` trong khi caller cần danh sách theo encounter order. Dù có khắc phục race bằng một collection thread-safe, thứ tự thêm của các worker vẫn không tương đương thứ tự nguồn.

## 9. groupingByConcurrent: Map an toàn không có nghĩa List bên trong cũng an toàn để dùng tùy ý

Ví dụ:

```java
ConcurrentMap<String, List<String>> ids = orders.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Order::getRegion,
                Collectors.mapping(
                        Order::getId,
                        Collectors.toList())));
```

`groupingByConcurrent` là collector concurrent. Tuy nhiên, downstream `toList` **không có đặc tính `CONCURRENT`**. JDK có thể bảo vệ thao tác tích lũy trên một container downstream bằng cơ chế đồng bộ thích hợp trong quá trình collect. Vì vậy, không được suy rằng các lời gọi `List.add` của ứng dụng trên danh sách kết quả trở thành thread-safe về sau.

Phân biệt ba tình huống:

1. **Trong quá trình collect:** framework có trách nhiệm triển khai đúng hợp đồng của collector, kể cả khi downstream không concurrent.
2. **Sau khi collect trả kết quả:** `ConcurrentMap` hỗ trợ thao tác Map đồng thời theo hợp đồng của nó, nhưng `List` nằm trong một giá trị vẫn có thể không thread-safe khi bị nhiều thread cùng sửa.
3. **Khi ứng dụng cần thứ tự trong mỗi nhóm:** `groupingByConcurrent` là collector unordered, nên không được dựa vào vị trí các phần tử trong `List` để biểu thị thời điểm hay thứ tự giao dịch.

Nếu cần vừa nhóm vừa có danh sách giữ thứ tự, `groupingBy(..., toList())` thường thể hiện ý định rõ hơn. Nếu cần nhiều thread cùng sửa danh sách sau thu thập, phải chọn một thiết kế dữ liệu/đồng bộ phù hợp ở **lớp sử dụng kết quả**, không dựa vào việc Map bên ngoài là concurrent.

## 10. Ngữ nghĩa thứ tự và hàm merge phụ thuộc thứ tự

Hai hàm merge thường gặp là:

```java
// Giữ giá trị xuất hiện trước trong một dãy có thứ tự.
(oldValue, newValue) -> oldValue

// Giữ giá trị xuất hiện sau trong một dãy có thứ tự.
(oldValue, newValue) -> newValue
```

Chúng **có tính kết hợp nhóm** nhưng **không giao hoán**: đổi thứ tự đầu vào có thể đổi kết quả. Vì `toConcurrentMap` là collector unordered, không nên dùng chúng để xác định “first” hoặc “last” theo encounter order.

Ví dụ, muốn chọn đơn mới nhất của mỗi khách hàng thì nên dùng thuộc tính nghiệp vụ như `timestamp`, `version` hoặc mã định danh duy nhất để phá hòa:

```java
import java.util.Comparator;
import java.util.function.BinaryOperator;

Comparator<Event> byTimeThenId =
        Comparator.comparingLong(Event::getTimestamp)
                .thenComparing(Event::getId);

BinaryOperator<Event> latest = BinaryOperator.maxBy(byTimeThenId);
```

Đoạn minh họa giả định có kiểu `Event`, `getTimestamp()` trả `long`, `getId()` trả khóa không null và các giá trị id dùng để phá hòa. Nếu comparator quy định được **một cực đại duy nhất**, phép chọn kết quả không phụ thuộc thứ tự các worker. Khi muốn chọn theo thứ tự giao dịch chứ không theo timestamp, phải giữ encounter order ở pipeline và dùng collector phù hợp.

### 10.1. Sắp xếp Map key cũng là vấn đề độc lập

`ConcurrentMap` hoặc `Map` từ các collector mặc định không cam kết một thứ tự duyệt khóa theo nghiệp vụ. Nếu muốn xuất báo cáo theo khóa tăng dần, hãy sắp xếp kết quả khi trình bày hoặc dùng một cấu trúc có thứ tự phù hợp. Đừng suy rằng `parallel()`, `CONCURRENT` hay `UNORDERED` tự tạo thứ tự ổn định.

## 11. Hiệu năng: concurrent reduction không đồng nghĩa nhanh hơn

Lợi ích tùy thuộc kích thước dữ liệu, chi phí mapping, số nhóm/khóa, phân bố khóa, mức tranh chấp, khả năng chia nguồn và yêu cầu thứ tự.

| Tình huống | Cân nhắc |
|---|---|
| Nhiều khóa độc lập, không cần thứ tự, dữ liệu lớn | `toConcurrentMap` hoặc `groupingByConcurrent` đáng thử |
| Hầu hết bản ghi cùng một khóa | Nhiều worker cùng tranh chấp một entry; concurrent collector có thể kém |
| Cần giữ danh sách các sự kiện đúng encounter order | `groupingBy(..., toList())` thường hợp lý hơn |
| Chỉ vài chục bản ghi, phép biến đổi rẻ | Overhead song song thường không đáng |
| Collector downstream có finisher hoặc combiner phức tạp | Đo chi phí gom kết quả; không suy từ tên “Concurrent” |
| Nguồn `Files.lines` hoặc I/O có tài nguyên cần đóng | Parallel không thay `try-with-resources`, có thể tăng tải I/O |
| Nhiều phần tử trùng khóa và merge tốn CPU | Kiểm tra contention, thời gian khóa và bộ nhớ |

### 11.1. Khả năng chia nguồn và đặc tính Spliterator

`Spliterator` quyết định khả năng chia các phần tử nguồn cho worker. Nguồn như `ArrayList` hoặc khoảng số `IntStream.range` thường dễ phân chia; nguồn phụ thuộc phần tử trước hoặc nguồn I/O có thể chia kém hơn. Vì vậy, `parallelStream()` không bảo đảm rằng mọi phần tử thực sự chạy đồng thời hay việc thu thập concurrent sẽ luôn bận rộn.

### 11.2. Đo hiệu năng đúng cách

Nếu muốn so `groupingBy` và `groupingByConcurrent`:

1. Dùng dữ liệu có số lượng bản ghi, tỷ lệ trùng khóa và phân bố nhóm gần sản xuất.
2. Kiểm tra hai kết quả **tương đương về giá trị**, không chỉ cùng số khóa; nếu một kết quả unordered, đừng dùng thứ tự in Map để so.
3. Khởi động JVM và chạy nhiều lần; benchmark bằng công cụ như JMH khi cần kết luận.
4. Đo thêm phân bổ bộ nhớ, contention, số worker hoạt động và tải tác vụ khác.
5. Không chạy `System.out.println` cho từng phần tử khi mục tiêu là đo thuật toán CPU.

Nếu yêu cầu nghiệp vụ bắt buộc có thứ tự, không đánh đổi tính đúng lấy tốc độ bằng cách chuyển sang một collector unordered.

## 12. Các lỗi thường gặp

| Nhận định hoặc cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| “Parallel stream cần mọi collector đều thread-safe.” | Framework có thể dùng container riêng rồi combiner | Dùng collector chuẩn như `toList`, `groupingBy` bình thường |
| “Collector có `CONCURRENT` thì luôn được dùng chung một container.” | Framework có thể chọn cách thực thi khác; cần điều kiện thứ tự | Xem cả chế độ Stream lẫn `UNORDERED` |
| “`UNORDERED` cũng đồng nghĩa `CONCURRENT`.” | Hai đặc tính độc lập | Kiểm tra từng characteristic |
| Tự khai báo `CONCURRENT` cho `ArrayList` | `ArrayList.add` không thread-safe | Bỏ characteristic hoặc thiết kế container/accumulator đồng thời thật |
| Gắn `UNORDERED` rồi mong danh sách giữ encounter order | Từ bỏ yêu cầu thứ tự | Dùng collector có thứ tự |
| `groupingByConcurrent(..., toList())` rồi sửa List từ nhiều thread | List downstream có thể không thread-safe | Bảo vệ hoặc sao chép kết quả trước khi sửa đồng thời |
| Dùng keep-last merge với `toConcurrentMap` để tìm “mới nhất” | Thứ tự cập nhật của worker không biểu thị timestamp | Chọn theo timestamp/version và tie-breaker |
| Dùng `toConcurrentMap(key,value)` với khóa trùng | Có thể ném `IllegalStateException` | Chọn hàm merge phù hợp |
| Mapper hoặc value mapper trả null | Dễ ném `NullPointerException` | Lọc/chuẩn hóa đầu vào |
| Tưởng concurrent collector luôn nhanh hơn | Có thể tranh chấp khóa, overhead lớn | Benchmark với phân bố dữ liệu thật |
| Lạm dụng side effect ngoài pipeline | Data race hoặc lỗi nghiệp vụ | Dùng reduction/collector và hàm thuần |

## 13. Bài tập tự kiểm tra có đáp án

### Bài 1. Parallel List và đặc tính CONCURRENT

```java
List<Integer> result = Arrays.asList(1, 2, 3)
        .parallelStream()
        .collect(Collectors.toList());
```

**Câu hỏi:** Vì sao mã hợp lệ dù `Collectors.toList()` không concurrent?

**Đáp án:** Framework có thể tạo container riêng cho các nhánh và gộp bằng combiner. Nhiều worker không bắt buộc cùng gọi `add` trên một List. Với nguồn List có encounter order, kết quả là `[1, 2, 3]`.

### Bài 2. Điều kiện concurrent reduction

**Câu hỏi:** Một Stream có thứ tự đang chạy song song. Collector có `CONCURRENT` nhưng **không có `UNORDERED`**. Có thể mặc định cho mọi worker cùng cập nhật một container bỏ qua thứ tự không?

**Đáp án:** Không. Để thực hiện concurrent reduction không giữ thứ tự, phải thỏa cả điều kiện về encounter order: Stream không có thứ tự **hoặc** collector có `UNORDERED`. Framework có thể chia container và gộp để bảo toàn ngữ nghĩa thứ tự.

### Bài 3. Chọn collector theo nhóm

Nguồn là danh sách đơn hàng lớn. Nghiệp vụ chỉ cần **đếm số đơn theo khu vực**, không yêu cầu thứ tự. Có thể dùng `groupingByConcurrent(..., counting())` không?

**Đáp án:** Có, nếu các trường khóa hợp lệ. Nhưng nên so sánh hiệu năng với `groupingBy(..., counting())` vì tốc độ phụ thuộc mức phân tán khóa và tranh chấp.

### Bài 4. Nhận diện collector nguy hiểm

Một collector có supplier `ArrayList::new`, accumulator `List::add` và đánh dấu `CONCURRENT, UNORDERED`. Điều gì sai?

**Đáp án:** Khi runtime tích lũy nhiều worker vào cùng một `ArrayList`, các lời gọi `add` có data race. Không được công bố `CONCURRENT` cho container/accumulator không thực sự an toàn.

### Bài 5. Chọn bản ghi cuối

Ba bản ghi cùng khóa có timestamp `100, 130, 120`. Người viết dùng `toConcurrentMap` với merge `(oldValue, newValue) -> newValue`. Có bảo đảm nhận timestamp `120` như phần tử cuối của List nguồn không?

**Đáp án:** Không. Collector unordered; thứ tự gộp concurrent không đại diện encounter order. Nếu cần thời điểm lớn nhất, dùng phép chọn theo timestamp và phá hòa khi bằng nhau, nhận `130`.

### Bài 6. Thread safety của Map và giá trị List

Ứng dụng thu được `ConcurrentMap<String, List<String>>` từ `groupingByConcurrent(..., toList())`. Sau khi collect xong, hai thread đồng thời gọi `get("BAC").add(...)`. Có an toàn không?

**Đáp án:** Không có bảo đảm. Map bên ngoài concurrent nhưng `List` là giá trị downstream không mặc nhiên thread-safe cho các phép sửa tùy ý sau collect. Cần thiết kế đồng bộ hoặc kiểu collection khác khi ứng dụng có yêu cầu ấy.

### Bài 7. Tự viết một concurrent collector đếm

Vì sao collector dùng `LongAdder` ở phần 8 công bố `CONCURRENT, UNORDERED` nhưng không công bố `IDENTITY_FINISH`?

**Đáp án:** Accumulator `LongAdder` có thể được tăng an toàn từ nhiều worker và phép đếm không phụ thuộc thứ tự. Tuy nhiên, bộ tích lũy trung gian là `LongAdder` còn kết quả là `Long`; finisher `LongAdder::sum` cần được thực hiện, nên không phải identity finish.

## 14. Checklist trước khi chọn collector đồng thời

Trước khi thay `groupingBy` bằng `groupingByConcurrent` hoặc `toMap` bằng `toConcurrentMap`, hãy tự kiểm tra:

1. **Pipeline có thực sự song song không?** `parallelStream()` và `parallel()` thay đổi chế độ, không cam kết tăng tốc.
2. **Đầu ra có cần encounter order không?** Nếu cần thứ tự danh sách hoặc “đầu/cuối”, collector unordered có thể không phù hợp.
3. **Collector có đúng `CONCURRENT` không?** Kiểm tra `characteristics()` và hợp đồng, không suy từ tên biến.
4. **Accumulator có thể chịu nhiều lời gọi trên cùng container không?** Đừng khai báo `CONCURRENT` cho `ArrayList` hoặc `HashMap` không được bảo vệ.
5. **Combiner có đúng không?** Framework vẫn có thể chia kết quả thành nhiều nhánh rồi gộp.
6. **Downstream có giữ trạng thái mutable không?** Một `ConcurrentMap` không biến mọi đối tượng bên trong nó thành thread-safe.
7. **Hàm merge và phép tính có hợp lệ không?** Khóa trùng, tràn số, tính kết hợp nhóm, thứ tự và giá trị null cần xử lý rõ.
8. **Có thật sự lợi về hiệu năng không?** Đo dữ liệu lớn/nhỏ, số lượng nhóm, phân bố khóa và contention trước khi quyết định.

**Ghi nhớ:** `parallelStream().collect(...)` không đồng nghĩa “mọi thread cùng sửa một bộ tích lũy”. Collector thông thường có thể chạy đúng trên parallel stream bằng cách **tích lũy độc lập rồi kết hợp**. Collector có `CONCURRENT` cho phép **tích lũy đồng thời vào cùng container** khi đủ điều kiện, thường đi cùng `UNORDERED` để không phải giữ encounter order. Hãy ưu tiên tính đúng của hợp đồng Collector, chọn thứ tự theo nghiệp vụ và chỉ dùng chiến lược concurrent khi nó phù hợp với dữ liệu và đã được đo lường.
