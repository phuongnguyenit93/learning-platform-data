# Ảnh hưởng của Collector phía sau đến phân nhóm đồng thời

Trong Java Stream API, `Collectors.groupingByConcurrent()` dùng để phân nhóm dữ liệu vào một `ConcurrentMap`. Tuy nhiên, việc **bản đồ kết quả hỗ trợ truy cập đồng thời** không có nghĩa mọi thao tác tích lũy bên trong từng nhóm đều diễn ra song song mà không cần phối hợp. Hiệu quả của pipeline còn phụ thuộc vào **downstream Collector** (collector phía sau): collector quyết định cách lưu, cộng dồn, biến đổi và hoàn thiện các giá trị của từng nhóm.

Bài học thuộc chương **Thu thập đồng thời**, tập trung vào cách lựa chọn và kết hợp downstream collector khi xử lý dữ liệu bằng parallel stream; qua đó nhận diện được các điểm nghẽn đồng bộ hóa, yêu cầu an toàn luồng và sự đánh đổi giữa tính đúng đắn với hiệu năng.

## 1. `groupingByConcurrent` làm gì?

Xét biểu thức:

```java
ConcurrentMap<K, D> result = stream.parallel().collect(
    Collectors.groupingByConcurrent(classifier, downstream)
);
```

- `classifier` tính khóa `K` của từng phần tử `T`.
- `groupingByConcurrent` quản lý một bản đồ có khả năng được nhiều luồng cập nhật, thông thường là `ConcurrentHashMap`.
- `downstream` thu thập các phần tử có **cùng khóa** thành một kết quả `D`; ví dụ `List<T>`, `Long`, `Set<T>` hoặc một bản đồ lồng nhau.

Chữ *concurrent* ở collector bên ngoài biểu thị khả năng hỗ trợ tích lũy đồng thời vào kết quả chung. Nó không bảo đảm rằng JVM sẽ sử dụng nhiều luồng trong mọi lần chạy, cũng không bảo đảm các giá trị `D` là đối tượng thread-safe sau khi thu thập xong. Muốn có cơ hội xử lý đồng thời, nguồn và pipeline cần được vận hành song song, chẳng hạn qua `parallelStream()`.

Khác với `groupingBy()`, collector `groupingByConcurrent()` có đặc tính `UNORDERED`: **thứ tự phần tử bên trong mỗi nhóm không được bảo đảm**, kể cả khi nguồn ban đầu có encounter order.

## 2. Downstream ảnh hưởng đến việc tích lũy như thế nào?

Mỗi downstream collector có một *accumulation container* (vùng tích lũy trung gian) và hàm `accumulator` dùng để đưa phần tử vào vùng đó. Các đặc tính `Collector.Characteristics` cho biết cách vùng tích lũy có thể được sử dụng:

| Đặc tính của downstream | Ý nghĩa đối với phân nhóm đồng thời |
| --- | --- |
| `CONCURRENT` | Cho phép nhiều luồng gọi `accumulator` trên **cùng vùng tích lũy** một cách an toàn. `groupingByConcurrent` có thể tích lũy đồng thời vào cùng một nhóm mà không cần khóa bao ngoài do downstream không hỗ trợ concurrency. |
| Không có `CONCURRENT` | Downstream không cam kết an toàn khi nhiều luồng cập nhật cùng container. `groupingByConcurrent` phải bảo vệ việc tích lũy vào từng nhóm; trong các triển khai JDK phổ biến, thao tác này được đồng bộ trên container của nhóm. |
| `UNORDERED` | Downstream không phụ thuộc vào thứ tự đầu vào. Dù downstream có đặc tính này hay không, **kết quả của `groupingByConcurrent` vẫn không bảo đảm encounter order**. |
| `IDENTITY_FINISH` | Có thể dùng chính vùng tích lũy làm giá trị kết quả mà không cần chuyển đổi ở bước cuối. Nếu downstream cần `finisher`, collector bên ngoài cũng cần hoàn thiện các giá trị trước khi trả về. |

Một điểm tinh tế: **`groupingByConcurrent()` vẫn là concurrent collector ngay cả khi downstream không có `CONCURRENT`**. Bộ thu thập bên ngoài chịu trách nhiệm điều phối việc cập nhật an toàn. Nhưng nếu nhiều phần tử rơi vào cùng một khóa, thao tác cập nhật nhóm đó có thể bị tuần tự hóa, làm giảm lợi ích của parallel stream.

Luồng xử lý có thể hình dung như sau:

```text
Nhiều luồng đọc phần tử T
          │
          ▼
    classifier(T) → khóa K
          │
          ▼
ConcurrentMap tìm/tạo container cho K
          │
          ├─ downstream CONCURRENT
          │    └─ Các luồng có thể tích lũy cùng container
          │
          └─ downstream không CONCURRENT
               └─ Các lần tích lũy cùng container cần được phối hợp
          │
          ▼
    downstream finisher (nếu cần)
          │
          ▼
        Map<K, D>
```

Các nhóm có khóa khác nhau vẫn có thể được xử lý đồng thời trong cả hai trường hợp. Vì vậy, **số lượng khóa khác nhau và mức độ phân bố dữ liệu giữa các khóa** ảnh hưởng mạnh đến hiệu năng.

## 3. So sánh những downstream collector thông dụng

| Downstream | Giá trị mỗi nhóm | `CONCURRENT` của downstream? | Hệ quả thực tế |
| --- | --- | --- | --- |
| `toList()` | `List<T>` | Không | Có thể gom song song giữa các nhóm; việc thêm vào cùng danh sách cần được bảo vệ. Danh sách kết quả không mặc nhiên thread-safe. |
| `toSet()` | `Set<T>` | Không | Khử trùng lặp theo nhóm; tập kết quả không mặc nhiên thread-safe. |
| `counting()` | `Long` | Không | Đếm đúng số phần tử mỗi nhóm; một khóa quá phổ biến có thể thành điểm nghẽn. |
| `summingInt(mapper)` | `Integer` | Không | Cộng các giá trị theo nhóm, có thể cần phối hợp cập nhật trên từng nhóm. |
| `mapping(mapper, toList())` | `List<U>` | Không | Chuyển đổi phần tử rồi gom danh sách; `mapping` không tự tạo khả năng tích lũy đồng thời. |
| `toConcurrentMap(keyMapper, valueMapper, merge)` | `ConcurrentMap<K2, V>` | Có | Bên trong mỗi nhóm có một concurrent map; các luồng có thể cập nhật container chung, dù vẫn có tranh chấp tại các khóa con. |
| `collectingAndThen(toList(), finisher)` | Tùy `finisher` | Không trong ví dụ này | Có thêm bước hoàn thiện giá trị mỗi nhóm; không biến `toList()` thành collector concurrent. |

Đặc tính `CONCURRENT` phải xuất phát từ **hợp đồng của collector**, không thể suy từ tên kiểu kết quả hoặc từ việc sử dụng `parallelStream()`. Ví dụ, `toSet()` có thể là `UNORDERED` nhưng vẫn không phải `CONCURRENT`.

## 4. Ví dụ đầy đủ: một tập đơn hàng, ba cách phân nhóm

Ví dụ sau chạy với Java 16 trở lên (do sử dụng `record`):

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupingDemo {
    record Order(String region, String product, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("Bac", "A", 2),
            new Order("Nam", "A", 3),
            new Order("Bac", "A", 4),
            new Order("Bac", "B", 1)
        );

        // 1. Gom các đơn hàng theo vùng.
        ConcurrentMap<String, List<Order>> ordersByRegion =
            orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.toList()
                )
            );

        // 2. Đếm số đơn hàng trong từng vùng.
        ConcurrentMap<String, Long> countByRegion =
            orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.counting()
                )
            );

        // 3. Cộng số lượng theo sản phẩm bên trong từng vùng.
        ConcurrentMap<String, ConcurrentMap<String, Integer>> quantityByRegion =
            orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.toConcurrentMap(
                        Order::product,
                        Order::quantity,
                        Integer::sum
                    )
                )
            );

        System.out.println(ordersByRegion.get("Bac").size()); // 3
        System.out.println(countByRegion.get("Bac"));         // 3
        System.out.println(countByRegion.get("Nam"));         // 1
        System.out.println(quantityByRegion.get("Bac").get("A")); // 6
        System.out.println(quantityByRegion.get("Bac").get("B")); // 1
    }
}
```

Trong ví dụ:

1. `toList()` tích lũy nhiều đơn vào danh sách của từng vùng. Mặc dù `ordersByRegion` là `ConcurrentMap`, không nên giả định `ordersByRegion.get("Bac")` là một `CopyOnWriteArrayList` hay danh sách cho phép cập nhật đồng thời.
2. `counting()` sử dụng downstream không concurrent. Kết quả đếm vẫn chính xác vì `groupingByConcurrent` thực hiện việc tích lũy phù hợp với hợp đồng downstream.
3. `toConcurrentMap()` tạo ra bản đồ con dùng `product` làm khóa. Hai đơn `("Bac", "A")` được hợp nhất bằng `Integer::sum`, tạo tổng `6`. Downstream này có `CONCURRENT`, nên có khả năng cập nhật đồng thời container bản đồ con.

Thứ tự các đơn khi duyệt `ordersByRegion.get("Bac")`, và thứ tự các khóa khi duyệt các bản đồ kết quả, không được coi là thứ tự ổn định. Vì vậy, ví dụ chỉ kiểm tra số lượng và tổng theo khóa.

## 5. Ví dụ nâng cao: tự viết downstream hỗ trợ concurrency

`counting()` không có đặc tính `CONCURRENT`. Nếu mục tiêu là đếm một lượng dữ liệu lớn với nhiều luồng cùng cập nhật một nhóm, có thể cân nhắc downstream dựa trên `LongAdder`:

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<Order, LongAdder, Long> concurrentCounting = Collector.of(
    LongAdder::new,
    (counter, order) -> counter.increment(),
    (left, right) -> {
        left.add(right.sum());
        return left;
    },
    LongAdder::sum,
    Collector.Characteristics.CONCURRENT,
    Collector.Characteristics.UNORDERED
);

var counts = orders.parallelStream().collect(
    Collectors.groupingByConcurrent(Order::region, concurrentCounting)
);
```

Đoạn này giả sử `Order` và `orders` đã được khai báo như ví dụ trước. `LongAdder` hỗ trợ các luồng cùng tăng bộ đếm; `finisher` chuyển kết quả trung gian thành `Long` sau khi thu thập hoàn tất. Vì vậy collector **không** khai báo `IDENTITY_FINISH`. Đây là một phương án cần đo đạc trước khi áp dụng: `LongAdder`, việc tạo container và `finisher` cũng có chi phí; nó không tự động nhanh hơn `counting()` ở mọi tập dữ liệu.

Khi tự viết downstream có `CONCURRENT`, hàm `accumulator` **phải thực sự an toàn nếu được gọi đồng thời trên cùng container**. Chỉ thêm cờ `CONCURRENT` cho collector dựa trên `ArrayList`, `HashMap` hoặc một bộ đếm `long` thông thường có thể gây mất dữ liệu hoặc race condition.

## 6. Khi nào downstream làm mất lợi ích của parallel stream?

Hiệu năng phụ thuộc vào sự phân bố khóa, chi phí tích lũy và mức độ tranh chấp:

- **Rất ít khóa, phân bố lệch:** Hàng triệu bản ghi cùng một `region` với `counting()` hoặc `toList()` khiến nhiều luồng cùng chờ cập nhật một nhóm. Số luồng tăng chưa chắc giúp chạy nhanh hơn.
- **Nhiều khóa phân bố đều:** Các luồng thường cập nhật các container khác nhau. Downstream không concurrent vẫn có thể mang lại tốc độ tốt vì tranh chấp giữa các nhóm thấp.
- **Downstream concurrent nhưng có khóa con nóng:** Với `toConcurrentMap(product, quantity, Integer::sum)`, nếu mọi đơn cùng `product`, việc hợp nhất một khóa trong map con vẫn có thể trở thành điểm nghẽn.
- **`finisher` đắt đỏ:** `collectingAndThen(...)` hoặc collector có bước hoàn thiện tốn nhiều thời gian sẽ tăng tổng chi phí, kể cả khi giai đoạn tích lũy được xử lý song song.
- **Tập dữ liệu nhỏ hoặc phép xử lý rẻ:** Chi phí phân chia công việc, điều phối luồng và cập nhật concurrent map có thể lớn hơn lợi ích từ chạy song song.

Ví dụ, với `Collectors.mapping(Order::product, Collectors.toSet())`, thao tác ánh xạ có thể chạy ở các luồng khác nhau nhưng việc thêm phần tử vào **cùng set của một nhóm** vẫn phải được điều phối vì `toSet()` không có `CONCURRENT`. `mapping()` không thay đổi sự thật này.

Khi tối ưu, hãy đo trên dữ liệu thật và so sánh ít nhất ba phương án có cùng kết quả cần thiết:

```java
// A. Thu thập tuần tự theo nhóm.
orders.stream().collect(
    Collectors.groupingBy(Order::region, Collectors.counting())
);

// B. Parallel stream, groupingBy: kết hợp các bản đồ cục bộ.
orders.parallelStream().collect(
    Collectors.groupingBy(Order::region, Collectors.counting())
);

// C. Parallel stream, groupingByConcurrent: tích lũy vào concurrent map.
orders.parallelStream().collect(
    Collectors.groupingByConcurrent(Order::region, Collectors.counting())
);
```

Phương án B có chi phí gộp các bản đồ trung gian; phương án C có chi phí điều phối cập nhật bản đồ chung và có thể tranh chấp tại nhóm. Không có phương án nào mặc nhiên nhanh nhất. Trong benchmark nghiêm túc, nên dùng JMH, làm nóng JVM, lặp nhiều lần, giữ nguyên dữ liệu đầu vào và kiểm tra kết quả trước khi so thời gian.

## 7. Những lỗi dễ mắc

**Nhầm `ConcurrentMap` với giá trị thread-safe.**

```java
ConcurrentMap<String, List<Order>> byRegion = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(Order::region));

// Không an toàn nếu nhiều luồng tự ý gọi add() trên cùng list này sau collect.
byRegion.get("Bac").add(new Order("Bac", "C", 5));
```

Lời gọi `add()` riêng lẻ không phải vấn đề nếu chương trình đang chạy tuần tự; vấn đề xuất hiện khi **nhiều luồng đồng thời thay đổi cùng danh sách**. Tính an toàn trong quá trình `collect()` là trách nhiệm của collector; nó không biến danh sách trả về thành cấu trúc dữ liệu an toàn cho mọi thao tác sau đó. Nếu cần trạng thái chỉ đọc, cân nhắc hoàn thiện thành danh sách bất biến và không cho các luồng khác sửa bản đồ bên ngoài.

**Dựa vào thứ tự sau `sorted()`.**

```java
var grouped = orders.parallelStream()
    .sorted(java.util.Comparator.comparingInt(Order::quantity))
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.toList()
    ));
```

`sorted()` đặt thứ tự ở đầu ra của giai đoạn sắp xếp, nhưng `groupingByConcurrent` là collector `UNORDERED`, nên không bảo đảm các danh sách kết quả được sắp xếp theo `quantity`. Nếu thứ tự trong từng nhóm là yêu cầu nghiệp vụ, hãy dùng phương án có bảo toàn encounter order phù hợp hoặc sắp xếp rõ ràng các nhóm **sau khi** thu thập.

**Không định nghĩa cách xử lý khóa con trùng lặp.**

```java
// Lỗi nếu hai Order trong cùng region có product trùng nhau.
Collectors.groupingByConcurrent(
    Order::region,
    Collectors.toConcurrentMap(Order::product, Order::quantity)
);
```

Overload `toConcurrentMap(keyMapper, valueMapper)` không có hàm gộp sẽ ném `IllegalStateException` khi gặp khóa con trùng. Nếu muốn cộng dồn số lượng, cần dùng overload có `mergeFunction`, chẳng hạn `Integer::sum`.

**Cho phép classifier trả về `null`.** `groupingByConcurrent()` không chấp nhận kết quả phân nhóm có khóa `null`; hãy chuẩn hóa khóa thiếu trước khi thu thập hoặc quyết định lọc bỏ phần tử theo yêu cầu nghiệp vụ.

**Gắn nhãn `CONCURRENT` cho downstream không an toàn.** Đặc tính này là một cam kết về khả năng gọi đồng thời `accumulator`, không phải mẹo tối ưu. Nếu logic tích lũy có trạng thái dùng chung nhưng không được đồng bộ phù hợp, kết quả có thể sai khó tái hiện.

## 8. Cách chọn collector trong thực tế

Trước tiên hãy hỏi: đầu ra mỗi nhóm cần là gì? Nếu chỉ cần phân nhóm để đọc danh sách, `groupingByConcurrent(classifier, toList())` là lựa chọn hợp lệ, miễn là không dựa vào thứ tự và không cập nhật các danh sách từ nhiều luồng sau khi `collect()` trả về. Nếu cần số lượng, `counting()` đơn giản và rõ nghĩa; chỉ cân nhắc một concurrent downstream tùy chỉnh khi phép đo cho thấy việc cập nhật nhóm là điểm nghẽn. Nếu cần tổng theo một khóa phụ, `toConcurrentMap()` thường là lựa chọn tự nhiên, với hàm gộp có tính kết hợp và phù hợp với việc xử lý không có thứ tự.

Hai câu hỏi tiếp theo quyết định hiệu năng và tính đúng đắn: **có bao nhiêu khóa thực sự được tạo ra?** và **downstream có thể cập nhật cùng container một cách an toàn hay không?** Với số khóa ít, áp lực lên từng nhóm thường chi phối; với nhiều khóa, chi phí phân bổ và gộp dữ liệu có thể chi phối. Khi kết quả yêu cầu thứ tự, cần một chiến lược bảo toàn hoặc tái tạo thứ tự rõ ràng thay vì suy luận từ `parallelStream()`.

### Tự kiểm tra

1. `groupingByConcurrent(classifier, toList())` có cho phép nhiều luồng thu thập an toàn không? Có: collector bên ngoài điều phối an toàn; điều đó **không** biến list trả về thành thread-safe.
2. Vì sao `groupingByConcurrent(classifier, counting())` có thể chậm khi chỉ có một khóa? Nhiều luồng tranh chấp việc cập nhật cùng một container đếm không concurrent.
3. Thay `toList()` bằng `mapping(mapper, toList())` có làm downstream trở thành concurrent không? Không; `mapping()` kế thừa các đặc tính thích hợp từ downstream, còn `toList()` không có `CONCURRENT`.
4. Khi nào `toConcurrentMap()` làm downstream hữu ích hơn? Khi mỗi nhóm cần một map con được cập nhật đồng thời, có hàm xử lý khóa con trùng đúng nghiệp vụ và mức tranh chấp đủ thấp để việc song song mang lại lợi ích.

Điểm cốt lõi: **an toàn luồng của collector bên ngoài, khả năng tích lũy đồng thời của downstream, và an toàn của giá trị kết quả là ba vấn đề riêng biệt**. Hiểu đúng từng lớp giúp chọn cấu trúc thu thập vừa chính xác vừa phù hợp với đặc điểm dữ liệu thực tế.
