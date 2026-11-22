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
# Ảnh hưởng của Collector phía sau đến phân nhóm đồng thời

Trong **Java Stream API**, `Collectors.groupingByConcurrent` hỗ trợ phân nhóm vào `ConcurrentMap` và được thiết kế để tham gia quá trình thu thập song song. Tuy nhiên, một lời gọi `groupingByConcurrent` thường còn chứa **collector phía sau** (*downstream collector*), chẳng hạn `toList`, `counting`, `summingLong`, `mapping` hoặc một collector tự định nghĩa.

Đó là điểm dễ hiểu sai: **map ngoài có khả năng truy cập đồng thời không có nghĩa mọi đối tượng giá trị của nó đều thread-safe**, và **collector phía sau không có đặc tính `CONCURRENT` không có nghĩa `groupingByConcurrent` sai hoặc không thể dùng trên parallel stream**. Framework phải tuân thủ hợp đồng tích lũy của collector tổng hợp; cách xử lý cạnh tranh tại từng khóa có thể ảnh hưởng mạnh đến hiệu năng.

Bài học thuộc chương **Thu thập đồng thời** của mô-đun `JAVA_STREAM_API`. Mục tiêu là biết đọc hợp đồng của collector, lựa chọn downstream phù hợp, phân biệt tính đúng đắn với khả năng mở rộng, và tránh tự chia sẻ trạng thái mutable khi xử lý song song.

## 1. Ba lớp phải phân biệt khi nói “đồng thời”

Giả sử muốn phân loại các sự kiện theo `type` rồi lưu danh sách `id` của từng loại:

```text
Stream<Event> --parallel--> groupingByConcurrent(Event::type,
                                      mapping(Event::id, toList()))
                                      |
                                      v
                         ConcurrentMap<String, List<String>>
                              /                    \
                        "ERROR"                  "INFO"
                           |                        |
                       List<String>             List<String>
```

Có ba câu hỏi **khác nhau**:

| Lớp | Câu hỏi | Điều cần hiểu |
| --- | --- | --- |
| **Nguồn Stream** | Có xử lý song song không? | `parallel()` cho phép framework chia nguồn; không bảo đảm các phần tử được xử lý theo thứ tự hoặc nhanh hơn. |
| **Collector ngoài** | Có cho phép nhiều worker góp vào cùng kết quả tích lũy không? | `groupingByConcurrent` trả collector có đặc tính `CONCURRENT` và `UNORDERED` theo hợp đồng API. |
| **Downstream và giá trị kết quả** | Container của từng nhóm có an toàn khi cập nhật đồng thời hay không? | `toList()` không phải concurrent collector; danh sách trả về cũng **không được bảo đảm thread-safe**. |

Một `ConcurrentMap<K, List<V>>` chỉ cho biết **các thao tác tương thích trên cấu trúc map** được hỗ trợ đồng thời theo hợp đồng của kiểu `ConcurrentMap`. Nó không biến `List<V>` bên trong thành danh sách an toàn để nhiều thread tùy ý `add`.

Điều quan trọng là lúc **đang collect**, framework phải phối hợp việc cập nhật giá trị theo đúng đặc tính của downstream. Sau khi `collect` kết thúc, mã người dùng nhận map và các giá trị; từ đó, quyền sửa đổi và tính an toàn luồng của từng value phải được đánh giá **riêng**.

## 2. Cú pháp của `groupingByConcurrent`

Ba overload chính, rút gọn kiểu generic để dễ đọc:

```java
groupingByConcurrent(classifier);

groupingByConcurrent(classifier, downstream);

groupingByConcurrent(classifier, mapFactory, downstream);
```

Trong đó:

- `classifier` là `Function<T, K>`, trả khóa nhóm cho mỗi phần tử.
- `downstream` là một `Collector` khác, quyết định **kiểu kết quả và cách tích lũy** của từng nhóm.
- `mapFactory` là `Supplier` tạo một `ConcurrentMap` thích hợp, ví dụ `ConcurrentSkipListMap::new`.

Kết quả terminal operation có kiểu `ConcurrentMap<K, D>`, với `D` do downstream quyết định. Overload chỉ nhận `classifier` tương đương về ý tưởng với việc thu các phần tử mỗi khóa vào một `List<T>`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

List<String> labels = Arrays.asList("API", "AUTH", "UI", "UPLOAD");

ConcurrentMap<Character, List<String>> groups = labels.parallelStream()
    .collect(Collectors.groupingByConcurrent(s -> s.charAt(0)));

System.out.println(groups.get('A').size()); // 2
System.out.println(groups.get('U').size()); // 2
```

Trong ví dụ, hai nhóm tồn tại, nhưng **không được viết kiểm thử đòi các danh sách luôn theo thứ tự nguồn**. Collector có đặc tính `UNORDERED`; thứ tự phần tử trong từng nhóm không được bảo đảm, đặc biệt khi xử lý song song.

Ngoài ra, classifier trả `null` sẽ bị từ chối; dùng khóa bất biến hoặc khóa có `equals`/`hashCode` ổn định. Đối với loại nguồn có thể thay đổi, vẫn phải tuân thủ nguyên tắc *non-interference*: không sửa nguồn từ trong mapper hay classifier.

## 3. So sánh `groupingBy` và `groupingByConcurrent`

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

// events là List<Event>, Event có phương thức type().
Map<String, List<Event>> regular = events.parallelStream()
    .collect(Collectors.groupingBy(Event::type));

ConcurrentMap<String, List<Event>> concurrent = events.parallelStream()
    .collect(Collectors.groupingByConcurrent(Event::type));
```

Đoạn mã là minh họa trong phạm vi có sẵn kiểu `Event` và biến `events`. Hai collector tạo cùng **cấu trúc logic nhóm theo khóa**, nhưng không có cùng hợp đồng về thứ tự và chiến lược kết hợp.

| Tiêu chí | `groupingBy` | `groupingByConcurrent` |
| --- | --- | --- |
| Kết quả | `Map<K, D>` | `ConcurrentMap<K, D>` |
| Đặc tính `CONCURRENT` của collector ngoài | Không | Có |
| Đặc tính `UNORDERED` của collector ngoài | Không mặc định | Có |
| Cách xử lý song song điển hình | Tạo các map tích lũy bộ phận rồi gộp | Có thể nhiều worker tích lũy vào một map đồng thời |
| Encounter order của nhóm | Có thể giữ thứ tự theo hợp đồng downstream và nguồn có thứ tự | Không được kỳ vọng giữ encounter order |
| Giá trị `List<T>` có thread-safe không? | Không có bảo đảm | **Cũng không có bảo đảm** |
| Có luôn nhanh hơn không? | Không | Không; tùy phân bố khóa và downstream |

Trên nguồn có thứ tự, `groupingBy` kết hợp downstream `toList` phù hợp khi **thứ tự tương đối của phần tử trong từng danh sách là yêu cầu**. `groupingByConcurrent` ưu tiên khả năng tích lũy đồng thời, chấp nhận bỏ bảo đảm về encounter order.

Với số khóa ít nhưng rất nhiều phần tử cùng khóa, tranh chấp khi cập nhật nhóm có thể lớn. Khi số khóa đa dạng, công việc phân tán hơn và collector đồng thời có cơ hội hiệu quả hơn. Cần **benchmark trên phân bố khóa thực tế**, không kết luận chỉ từ kích thước nguồn.

## 4. Downstream `toList()`: không concurrent nhưng vẫn dùng được

Một ví dụ hoàn chỉnh (Java 8+):

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupingExample {
    static final class Event {
        final String type;
        final String id;

        Event(String type, String id) {
            this.type = type;
            this.id = id;
        }
    }

    public static void main(String[] args) {
        List<Event> events = Arrays.asList(
            new Event("ERROR", "E1"),
            new Event("INFO",  "I1"),
            new Event("ERROR", "E2"),
            new Event("WARN",  "W1"),
            new Event("ERROR", "E3")
        );

        ConcurrentMap<String, List<String>> idsByType =
            events.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                    event -> event.type,
                    Collectors.mapping(
                        event -> event.id,
                        Collectors.toList()
                    )
                ));

        System.out.println(idsByType.get("ERROR").size()); // 3
        System.out.println(idsByType.get("INFO").size());  // 1
        System.out.println(idsByType.get("WARN").size());  // 1
    }
}
```

`mapping` là downstream **adapter**: nó đổi `Event` thành `String` rồi chuyển kết quả cho `toList`. `toList` không có đặc tính `CONCURRENT`, nhưng **toàn bộ collector do `groupingByConcurrent` tạo vẫn là một collector hợp lệ cho stream song song**.

Tại sao không xảy ra race do các worker cùng ghi một `ArrayList`? Vì implementation của collector tổng hợp **chịu trách nhiệm điều phối accumulation theo đặc tính downstream**. Khi downstream không hỗ trợ đồng thời trên cùng container, implementation có thể bảo vệ các cập nhật của cùng nhóm, chẳng hạn bằng đồng bộ hóa. Cơ chế nội bộ cụ thể là chi tiết triển khai, không phải thứ ứng dụng nên dựa vào.

Tuy nhiên, sau khi `collect` trả về:

```java
// KHÔNG dùng một List trả về như container dùng chung
// cho nhiều thread tùy ý cùng add/remove.
List<String> errorIds = idsByType.get("ERROR");
```

`ConcurrentMap` bảo vệ thao tác truy cập map theo hợp đồng; **không bảo đảm** `errorIds.add(...)` được gọi đồng thời từ nhiều thread sẽ an toàn. Nếu cần chia sẻ và cập nhật danh sách kết quả, phải chọn kiểu container/cơ chế đồng bộ phù hợp hoặc chuyển sang kết quả bất biến.

## 5. Downstream quyết định hình dạng và chi phí từng nhóm

Không phải báo cáo nào cũng cần giữ lại **mọi phần tử**. Chọn downstream đúng có thể cải thiện khả năng mở rộng hơn việc chỉ đổi `groupingBy` thành `groupingByConcurrent`.

| Downstream | `D` trong `ConcurrentMap<K,D>` | Dữ liệu giữ lại | Lưu ý |
| --- | --- | --- | --- |
| `toList()` | `List<T>` | Toàn bộ phần tử | Chiếm bộ nhớ theo số phần tử; list không được bảo đảm thread-safe. |
| `toSet()` | `Set<T>` | Phần tử duy nhất | Không hứa loại Set, thứ tự hay thread-safety. |
| `counting()` | `Long` | Số đếm | Không lưu phần tử; có thể gặp tranh chấp với khóa “nóng”. |
| `summingLong(mapper)` | `Long` | Một tổng | Tổng có thể tràn `long`; không cần list. |
| `summarizingLong(mapper)` | `LongSummaryStatistics` | Count, sum, min, max, average | Đối tượng kết quả mutable, không an toàn cho cập nhật đồng thời tùy ý. |
| `mapping(mapper, downstream)` | Theo downstream trong | Phụ thuộc downstream | Biến đổi từng phần tử trước khi tích lũy. |
| `filtering(predicate, downstream)` (Java 9+) | Theo downstream trong | Chỉ phần tử được chọn vào downstream | Khóa đã được classifier nhìn thấy vẫn có thể tồn tại với kết quả rỗng/0. |
| `collectingAndThen(downstream, finisher)` | Theo `finisher` | Chốt đối tượng sau tích lũy | Không biến một accumulator không concurrent thành concurrent. |

Để tránh cấp phát danh sách lớn nếu chỉ cần đếm lỗi:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "ERROR", "INFO", "ERROR", "WARN", "ERROR"
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        type -> type,
        Collectors.counting()
    ));

System.out.println(counts.get("ERROR")); // 3
System.out.println(counts.get("INFO"));  // 1
```

`counting` là downstream có thể dùng an toàn **qua `groupingByConcurrent`** nhưng bản thân nó không phải một concurrent collector. Điều này không gây lỗi hợp đồng; song song vẫn có thể cần phối hợp khi nhiều worker tích lũy vào cùng khóa.

## 6. `summarizingLong`: nhiều chỉ số nhưng kết quả vẫn mutable

Nếu cần vừa đếm vừa đo thống kê theo nhóm, tránh `toList` rồi quét danh sách từng nhóm nhiều lần:

```java
import java.util.Arrays;
import java.util.LongSummaryStatistics;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

final class Sale {
    final String category;
    final long amount;

    Sale(String category, long amount) {
        this.category = category;
        this.amount = amount;
    }
}

ConcurrentMap<String, LongSummaryStatistics> stats =
    Arrays.asList(
        new Sale("BOOK", 100L),
        new Sale("TOOL", 300L),
        new Sale("BOOK", 200L)
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        sale -> sale.category,
        Collectors.summarizingLong(sale -> sale.amount)
    ));

LongSummaryStatistics books = stats.get("BOOK");
System.out.println(books.getCount());   // 2
System.out.println(books.getSum());     // 300
System.out.println(books.getMin());     // 100
System.out.println(books.getMax());     // 200
System.out.println(books.getAverage()); // 150.0
```

`LongSummaryStatistics` dùng trạng thái mutable trong quá trình tích lũy. **Framework xử lý việc tích lũy phù hợp với hợp đồng của downstream**; điều đó không cấp quyền cho mã khác sửa `books` cùng lúc khi đang đọc. Đừng gọi `books.accept(...)` từ nhiều thread mà không có cơ chế bảo vệ độc lập.

Số tiền `long` theo đơn vị nguyên nhỏ nhất giúp tránh sai số biểu diễn thập phân, nhưng `getSum()` vẫn có thể tràn `long`; `getAverage()` trả `double` có thể cần quy tắc làm tròn riêng. Nếu nghiệp vụ cần kết quả bất biến, **không trả trực tiếp các đối tượng thống kê mutable**.

### Chốt thống kê thành một giá trị bất biến

Ví dụ Java 16+ dùng `record` để không lộ bộ tích lũy mutable:

```java
import java.util.Arrays;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

record Metrics(long count, long sum, long min, long max) {
    static Metrics from(LongSummaryStatistics s) {
        return new Metrics(s.getCount(), s.getSum(), s.getMin(), s.getMax());
    }
}

Map<String, Metrics> immutableReport =
    Arrays.asList(
        new Sale("BOOK", 100L),
        new Sale("BOOK", 200L),
        new Sale("TOOL", 300L)
    ).parallelStream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingByConcurrent(
            sale -> sale.category,
            Collectors.collectingAndThen(
                Collectors.summarizingLong(sale -> sale.amount),
                Metrics::from
            )
        ),
        Map::copyOf
    ));

System.out.println(immutableReport.get("BOOK").sum()); // 300
```

Đoạn mã này sử dụng kiểu `Sale` ở ví dụ trước. Kết quả cuối là `Map` **không sửa đổi được**, còn các `Metrics` chỉ chứa primitive. Phần tích lũy ban đầu vẫn có thể mutable; `collectingAndThen` chỉ áp dụng finisher **sau khi việc tích lũy của từng phần đã hoàn tất**, không làm cho accumulator trở thành concurrent.

Đối với nhóm rỗng, `getMin()`/`getMax()` của `LongSummaryStatistics` chứa giá trị khởi tạo đặc biệt. Trong ví dụ `groupingByConcurrent`, mỗi khóa chỉ xuất hiện vì đã có phần tử được phân vào khóa; nếu thêm downstream `filtering` thì một nhóm có thể có count 0, cần xử lý trường hợp đó trước khi công bố min/max.

## 7. `mapping` và `filtering` không làm biến mất ràng buộc của downstream

Một sai lầm khác là cho rằng chỉ cần bọc `toList()` bằng `mapping()` hoặc `filtering()` thì việc tích lũy tự trở thành đồng thời. Trên thực tế, hai adapter này **chuyển tiếp việc tích lũy** cho downstream và đặc tính của collector kết quả phụ thuộc các collector được ghép.

Ví dụ đếm các sự kiện nghiêm trọng theo loại (Java 9+):

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

final class Alert {
    final String service;
    final boolean severe;

    Alert(String service, boolean severe) {
        this.service = service;
        this.severe = severe;
    }
}

ConcurrentMap<String, Long> severeCounts =
    Arrays.asList(
        new Alert("API", false),
        new Alert("API", true),
        new Alert("UI", false)
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        alert -> alert.service,
        Collectors.filtering(
            alert -> alert.severe,
            Collectors.counting()
        )
    ));

System.out.println(severeCounts.get("API")); // 1
System.out.println(severeCounts.get("UI"));  // 0
```

`filtering` đặt **sau** classifier: nhóm `UI` tồn tại vì đã xuất hiện sự kiện của `UI`, dù không có cảnh báo nghiêm trọng. Nếu đặt `stream.filter(alert -> alert.severe)` **trước** `groupingByConcurrent`, nhóm `UI` sẽ không xuất hiện.

Hãy phân biệt **hình dạng kết quả** (Map chứa `Long`, `List`, `Statistics`...) với **đặc tính tích lũy** (`CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`). `mapping` hay `filtering` thường hữu ích về ngữ nghĩa, nhưng không tự giải quyết tranh chấp tại một khóa nóng.

## 8. `Collector.Characteristics` cho biết điều gì?

Collector có tập đặc tính do `characteristics()` trả về:

| Đặc tính | Ý nghĩa | Điều **không** được suy ra |
| --- | --- | --- |
| `CONCURRENT` | Cho phép accumulator được gọi đồng thời từ nhiều thread trên **cùng một container tích lũy**. | Không bảo đảm **giá trị kết quả cuối** là immutable hoặc có mọi thao tác an toàn luồng. |
| `UNORDERED` | Phép thu thập không cam kết giữ encounter order. | Không có nghĩa đầu vào được xử lý ngẫu nhiên hoặc iteration order của một map cụ thể không có quy tắc. |
| `IDENTITY_FINISH` | Finisher về bản chất là phép đồng nhất, container tích lũy chính là kiểu kết quả. | Không có nghĩa đối tượng không thể thay đổi. |

Kiểm tra một số collector qua API:

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, List<String>> listCollector =
    Collectors.toList();

Collector<String, ?, ConcurrentMap<Integer, List<String>>> grouped =
    Collectors.groupingByConcurrent(String::length);

System.out.println(listCollector.characteristics()
    .contains(Collector.Characteristics.CONCURRENT)); // false
System.out.println(grouped.characteristics()
    .contains(Collector.Characteristics.CONCURRENT)); // true
System.out.println(grouped.characteristics()
    .contains(Collector.Characteristics.UNORDERED));  // true
```

**Quan trọng:** Collector có `CONCURRENT` nhưng **không** có `UNORDERED` chỉ được phép thực hiện *concurrent reduction* trên stream có thứ tự nếu stream đã được coi là **unordered**. `groupingByConcurrent` là `UNORDERED`, vì thế việc tích lũy đồng thời không phải bảo toàn thứ tự gặp phần tử.

Đừng tự gắn `CONCURRENT` vào collector khi accumulator sử dụng `ArrayList.add`, `HashMap.put` hoặc tăng biến `long` dùng chung mà không có cơ chế an toàn đồng thời. Đặc tính ấy là **cam kết cho Stream framework**, không phải chỉ thị tăng tốc.

## 9. Downstream concurrent thực sự: khi nào cần?

Nếu một nhóm cực lớn có nhiều worker cạnh tranh cập nhật cùng container, một downstream **thực sự concurrent** có thể cho phép tích lũy trực tiếp vào container nhóm mà không phải tuần tự hóa mọi cập nhật. Tuy nhiên, cấu trúc dữ liệu concurrent cũng có chi phí đồng bộ/cấp phát riêng và **không mặc nhiên nhanh hơn**.

Ví dụ collector tự định nghĩa vào `ConcurrentLinkedQueue` (Java 8+):

```java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.concurrent.ConcurrentMap;

Collector<String, ConcurrentLinkedQueue<String>, ConcurrentLinkedQueue<String>>
    queueCollector = Collector.of(
        ConcurrentLinkedQueue::new,
        ConcurrentLinkedQueue::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.CONCURRENT,
        Collector.Characteristics.UNORDERED
    );

ConcurrentMap<Integer, ConcurrentLinkedQueue<String>> byLength =
    Stream.of("AB", "CD", "A", "XYZ", "EF")
        .parallel()
        .collect(Collectors.groupingByConcurrent(
            String::length,
            queueCollector
        ));

System.out.println(byLength.get(2).size()); // 3
```

Ý nghĩa của thiết kế:

- `supplier` tạo **một queue mới** cho từng container tích lũy; không trả queue dùng chung cho tất cả khóa.
- `ConcurrentLinkedQueue.add` được thiết kế để nhiều thread có thể thêm phần tử an toàn.
- Combiner gộp hai queue khi framework cần kết hợp các kết quả bộ phận.
- `CONCURRENT` được khai báo vì **accumulator trên cùng queue** hỗ trợ cập nhật đồng thời.
- `UNORDERED` được khai báo vì thứ tự phần tử trong queue không được bảo đảm theo encounter order ở chế độ song song.

Lưu ý: `Collectors.toCollection(ConcurrentLinkedQueue::new)` **không tự trở thành concurrent collector** chỉ vì kiểu collection được tạo là concurrent. Đặc tính collector phải được thiết kế và khai báo đúng hợp đồng, không suy ra đơn thuần từ lớp container.

Collector tùy chỉnh có `CONCURRENT` cần được kiểm chứng về tính đúng đắn khi accumulator và combiner có thể được gọi theo những cách hợp lệ khác nhau. Nếu không có yêu cầu hiệu năng đã đo đạc, những downstream chuẩn như `counting`, `toList` hoặc `summarizingLong` thường dễ bảo trì hơn.

## 10. Dùng `toConcurrentMap` làm downstream khi muốn kết quả dạng map con

Không phải mọi nhóm đều cần danh sách. Đôi khi trong mỗi nhóm, ta muốn **lập bảng tra cứu theo một khóa phụ**; `toConcurrentMap` có thể phù hợp:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

final class Item {
    final String category;
    final String sku;
    final int quantity;

    Item(String category, String sku, int quantity) {
        this.category = category;
        this.sku = sku;
        this.quantity = quantity;
    }
}

ConcurrentMap<String, ConcurrentMap<String, Integer>> inventory =
    Arrays.asList(
        new Item("BOOK", "B1", 2),
        new Item("BOOK", "B1", 3),
        new Item("BOOK", "B2", 1),
        new Item("TOOL", "T1", 4)
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        item -> item.category,
        Collectors.toConcurrentMap(
            item -> item.sku,
            item -> item.quantity,
            Integer::sum
        )
    ));

System.out.println(inventory.get("BOOK").get("B1")); // 5
System.out.println(inventory.get("TOOL").get("T1")); // 4
```

`toConcurrentMap` tạo một downstream concurrent và unordered cho việc thu vào map con. Khi **trùng khóa SKU**, cần merger `Integer::sum` hoặc một quy tắc tương ứng với nghiệp vụ; overload hai mapper không chấp nhận khóa trùng.

Map con concurrent hỗ trợ các thao tác tương ứng an toàn đồng thời theo hợp đồng của nó, nhưng **không biến dữ liệu thành immutable**. Với dữ liệu tài chính hoặc inventory lớn, tổng kiểu `int` vẫn có khả năng tràn; dùng `long` hay kiểm tra tràn khi phù hợp.

Đừng xây cấu trúc map lồng nhau chỉ vì thấy từ “concurrent”. Nếu chỉ cần số lượng của mỗi category, `groupingByConcurrent(..., counting())` đơn giản hơn và giữ ít dữ liệu hơn.

## 11. Độ tập trung của khóa quyết định khả năng mở rộng

Ảnh hưởng của downstream bộc lộ rõ khi phân bố khóa thay đổi. So sánh hai tình huống:

```text
Phân bố khá đều:            Phân bố lệch mạnh:
  A: 25%                      HOT: 99%
  B: 25%                      A: 0.5%
  C: 25%                      B: 0.5%
  D: 25%
```

Với một downstream không concurrent như `toList` hoặc `counting`, các cập nhật cùng khóa phải được phối hợp để giữ tính đúng đắn. **Khóa HOT** trở thành nơi có thể phát sinh tranh chấp, làm nhiều worker phải chờ hoặc giảm mức song song hữu ích. Thêm `parallel()` không xóa được điểm nghẽn logic ấy.

Khi downstream thực sự concurrent, một số cập nhật có thể tiến hành đồng thời trên cùng container; nhưng cấu trúc đồng thời thường dùng nguyên tử, phân mảnh dữ liệu hoặc phối hợp nội bộ. Điều đó vẫn có thể tốn chi phí, đặc biệt khi chỉ có vài phần tử.

| Yếu tố | Tác động cần đo |
| --- | --- |
| Số lượng khóa | Nhiều khóa độc lập có thể phân tán cập nhật tốt hơn. |
| Độ lệch phân bố | Một khóa rất nóng có thể gây tranh chấp tại nhóm ấy. |
| Downstream `toList` | Giữ toàn bộ phần tử, tốn bộ nhớ và cần phối hợp accumulation mỗi nhóm. |
| Downstream `counting` | Giữ ít dữ liệu nhưng vẫn có thể tranh chấp tại nhóm nóng. |
| Downstream concurrent | Có thể giúp giảm nút thắt, nhưng cấu trúc đồng thời cũng có overhead. |
| Chi phí mapper/classifier | Nếu tính toán nặng, overhead đồng bộ chiếm tỷ lệ nhỏ hơn; nếu rất rẻ, overhead dễ nổi bật. |
| Spliterator của nguồn | Nguồn khó chia sẽ hạn chế lợi ích parallel dù collector tối ưu. |
| Ordered vs unordered | `groupingByConcurrent` bỏ nghĩa vụ giữ encounter order, có thể có lợi nếu nghiệp vụ cho phép. |

Không nên kết luận `groupingByConcurrent` luôn tốt hơn `groupingBy`. Với dataset nhỏ hoặc số nhóm rất ít, việc chia nguồn và phối hợp có thể khiến nó chậm hơn. Với dữ liệu có thứ tự mà kết quả đòi giữ thứ tự trong từng nhóm, `groupingByConcurrent` còn có thể **sai yêu cầu nghiệp vụ**, dù thời gian benchmark đẹp.

## 12. Chọn factory cho map ngoài: đồng thời không đồng nghĩa không có thứ tự khóa

Overload ba tham số cho phép chọn loại `ConcurrentMap`:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "API", "UI", "API", "DB"
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        service -> service,
        ConcurrentSkipListMap::new,
        Collectors.counting()
    ));

System.out.println(counts.keySet()); // [API, DB, UI]
```

`ConcurrentSkipListMap` duyệt khóa theo thứ tự sắp xếp, khác với `ConcurrentHashMap` vốn không bảo đảm thứ tự duyệt. Nhưng **thứ tự khóa được sắp xếp** không đồng nghĩa với việc giữ encounter order của từng phần tử thuộc nhóm. Collector vẫn là `UNORDERED`.

Khi chọn comparator cho map có thứ tự, cần hiểu quy tắc trùng khóa: comparator trả `0` có nghĩa các khóa tương đương đối với map có thứ tự. Không sử dụng comparator có trạng thái thay đổi hoặc bất nhất.

Nếu chỉ cần hiển thị dữ liệu theo thứ tự khóa, cũng có thể **sắp xếp sau khi thu thập** để tách biệt logic tích lũy với logic hiển thị.

## 13. Tính đúng đắn: những điều cần và không cần kiểm tra

Với dữ liệu nguồn bất biến trong suốt pipeline, classifier/mapper không có side effect, downstream hợp lệ, một pipeline song song phải tạo kết quả đúng theo hợp đồng thu thập.

Ví dụ kiểm tra số lượng thay vì thứ tự trong danh sách:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

ConcurrentMap<Integer, List<Integer>> grouped =
    IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.groupingByConcurrent(
            n -> n % 4
        ));

for (int key = 0; key < 4; key++) {
    List<Integer> group = grouped.get(key);
    if (group == null || group.size() != 2500) {
        throw new AssertionError("Sai số phần tử nhóm " + key);
    }
    for (int n : group) {
        if (n % 4 != key) {
            throw new AssertionError("Sai classifier");
        }
    }
}
```

Nếu còn cần chứng minh **không mất hoặc lặp phần tử**, có thể tạo một tập kiểm tra hoặc đếm tần suất giá trị trong từng nhóm khi nguồn có định danh duy nhất. Không được chỉ kiểm tra tổng kích thước nếu dữ liệu có thể bị ghi trùng mà vẫn giữ tổng.

**Không kiểm tra:**

- `grouped.get(key)` phải có thứ tự giống phần tử gốc của `IntStream.range`.
- Mọi worker phải xử lý một số lượng phần tử bằng nhau.
- Downstream `toList` phải là `ArrayList` hay một kiểu list thread-safe.
- `groupingByConcurrent` nhất thiết nhanh hơn phiên bản tuần tự.

Với nguồn chứa `null`, classifier trả `null`, merger không kết hợp, key có `hashCode` thay đổi hoặc lambda phụ thuộc trạng thái chia sẻ, phải xử lý các vấn đề đó **trước khi** đánh giá hiệu năng.

## 14. Đo hiệu năng có phân bố khóa và downstream rõ ràng

Để tìm hiểu ảnh hưởng downstream, hãy tạo một benchmark với các biến độc lập:

1. **Kích thước nguồn:** ví dụ 1.000, 100.000, 1.000.000 phần tử.
2. **Phân bố khóa:** phân bố đều trên nhiều khóa và phân bố lệch rất mạnh về một khóa.
3. **Downstream:** `counting`, `toList`, `summarizingLong`; nếu có nhu cầu thật, bổ sung custom concurrent collector.
4. **Cách thu thập:** `groupingBy` và `groupingByConcurrent`, chạy tuần tự và song song theo thiết kế so sánh.
5. **Môi trường:** số core, JDK, kích thước heap, mức tải và cách JMH thực thi benchmark.

Mọi phương án phải xuất phát từ **cùng dữ liệu** và tính **cùng chỉ số nghiệp vụ** khi so sánh thời gian. Không so `counting` với `toList` rồi tuyên bố collector A nhanh hơn B “trong cùng bài toán” nếu một bên giữ danh sách còn bên kia chỉ đếm; đó là hai mức công việc và hai hợp đồng đầu ra khác nhau.

Với JMH, dùng warm-up, nhiều measurement/fork và tiêu thụ kết quả phù hợp. Theo dõi `time/op`, throughput, allocation và GC nếu cần. **Không tự bịa số đo**: thời gian thay đổi theo phân bố khóa, thuật toán downstream, Spliterator và phần cứng.

Một bảng báo cáo hợp lý:

| Nguồn | Phân bố khóa | Downstream | Collector ngoài | Thời gian (đo thực tế) | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| 100.000 sự kiện | Đều | `counting` | `groupingBy` | Điền sau khi đo | Baseline |
| 100.000 sự kiện | Đều | `counting` | `groupingByConcurrent` | Điền sau khi đo | So chi phí gộp map |
| 100.000 sự kiện | Lệch mạnh | `counting` | `groupingByConcurrent` | Điền sau khi đo | Theo dõi hot key |
| 100.000 sự kiện | Lệch mạnh | `toList` | `groupingByConcurrent` | Điền sau khi đo | Thêm chi phí lưu phần tử |

### Vì sao một downstream concurrent có thể vẫn chậm?

Một queue concurrent có thể làm nhiều thread thêm phần tử vào cùng nhóm mà không cần khóa độc quyền của collector ngoài. Nhưng nó vẫn có overhead quản lý nút và truy cập đồng thời. Với việc chỉ cần **đếm**, tạo queue chứa mọi phần tử thường là thiết kế **tốn bộ nhớ hơn nhiều** so với một bộ đếm. Hãy tối ưu **đúng yêu cầu dữ liệu đầu ra** trước khi tối ưu công nghệ đồng thời.

## 15. Các sai lầm thường gặp

| Nhận định hoặc cách làm sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| “`groupingByConcurrent` dùng `toList` là không thread-safe nên sai.” | Nhầm an toàn của **collector trong lúc thu thập** với thread-safety của **list kết quả**. | Dùng collector chuẩn theo hợp đồng; đừng sửa list kết quả đồng thời ngoài pipeline. |
| “Map concurrent thì value nào cũng concurrent.” | `ConcurrentMap<K,List<V>>` không làm `List` tự an toàn luồng. | Chọn value immutable, concurrent hoặc đồng bộ riêng theo nhu cầu. |
| “Thêm `ConcurrentLinkedQueue` vào `toCollection` là có collector `CONCURRENT`.” | Đặc tính collector không được suy ra từ lớp container. | Dùng collector được thiết kế, kiểm tra và khai báo `CONCURRENT` đúng cách. |
| “`groupingByConcurrent` giữ thứ tự dữ liệu theo nhóm.” | Collector `UNORDERED` không hứa encounter order. | Chọn `groupingBy` phù hợp nếu thứ tự bắt buộc; hoặc sắp xếp kết quả. |
| “Dùng `toList` khi chỉ cần đếm.” | Tạo nhiều đối tượng và giữ dữ liệu không cần thiết. | Dùng `counting`. |
| “Downstream không concurrent làm parallel stream không thể chạy.” | Framework có thể phối hợp accumulator theo đặc tính downstream. | Vẫn dùng được; đo tranh chấp nếu hiệu năng quan trọng. |
| “Cứ có nhiều core thì `groupingByConcurrent` luôn nhanh hơn.” | Hot key, overhead và nguồn khó chia có thể triệt tiêu lợi ích. | Đo trên khóa phân bố thực tế; so với tuần tự và `groupingBy`. |
| “`LongSummaryStatistics` trả ra có thể cập nhật từ nhiều thread.” | Đối tượng mutable không được thiết kế để cùng cập nhật không đồng bộ. | Chốt thành DTO immutable hoặc phối hợp riêng. |
| “`collectingAndThen` biến downstream thành concurrent.” | Finisher chỉ chuyển kết quả, không làm accumulator tự an toàn luồng. | Xét đặc tính downstream và collector tổng hợp. |
| “Classifier có thể trả `null`.” | Collector phân nhóm concurrent từ chối khóa null. | Xác thực hoặc dùng khóa đại diện rõ nghĩa trước khi nhóm. |

## 16. Bài tập thực hành

**Bài 1 — Phân biệt ba lớp.** Với `groupingByConcurrent(Event::type, mapping(Event::id, toList()))`, xác định: (a) collector ngoài có đặc tính nào, (b) downstream có concurrent không, (c) có thể sửa danh sách kết quả đồng thời từ nhiều thread không. Giải thích vì sao không nên lẫn lộn ba câu hỏi.

**Bài 2 — Đếm thay vì lưu toàn bộ.** Từ một triệu mã dịch vụ, dùng `parallelStream().collect(groupingByConcurrent(identity(), counting()))` để đếm theo mã. Kiểm tra tổng mọi count bằng số lượng đầu vào. So sánh chi phí bộ nhớ dự kiến với downstream `toList`.

**Bài 3 — Khóa nóng.** Sinh dữ liệu sao cho 99% phần tử thuộc một khóa, 1% thuộc nhiều khóa còn lại. So sánh `groupingBy` và `groupingByConcurrent` cùng downstream `counting` bằng JMH. Tại sao kết quả có thể khác so với dữ liệu phân bố đều?

**Bài 4 — Thống kê bất biến.** Dùng `groupingByConcurrent(category, summarizingLong(amount))`, sau đó chuyển từng `LongSummaryStatistics` thành record chỉ có trường primitive và chốt map bằng `Map.copyOf`. Vì sao chỉ dùng `Map.copyOf` mà giữ `LongSummaryStatistics` chưa đủ?

**Bài 5 — Grouping và filtering.** Từ danh sách các alert theo service, dùng `groupingByConcurrent(service, filtering(severe, counting()))`. So sánh với việc `stream.filter(severe)` trước khi nhóm. Với service chỉ có alert không nghiêm trọng, hai kết quả có khác nhau không?

**Bài 6 — Collector tùy chỉnh.** Tạo một collector `CONCURRENT` từ `ConcurrentLinkedQueue`. Giải thích trách nhiệm của supplier, accumulator và combiner; vì sao `UNORDERED` phù hợp; và điều gì sai nếu supplier luôn trả về **cùng một queue dùng chung** cho tất cả nhóm.

**Bài 7 — Map con đồng thời.** Gom các mặt hàng theo category, rồi theo SKU bằng downstream `toConcurrentMap` có `Integer::sum`. Thử dữ liệu có SKU trùng; điều gì xảy ra nếu dùng overload không có merge function?

**Ghi nhớ:** `groupingByConcurrent` cung cấp cơ chế **thu thập đồng thời và không bảo đảm encounter order** ở tầng phân nhóm. Downstream quyết định **dạng giá trị, lượng trạng thái cần giữ và khả năng tranh chấp ở từng khóa**. Downstream như `toList` hoặc `counting` không phải concurrent collector nhưng vẫn được phép dùng bên trong `groupingByConcurrent` vì framework phối hợp tích lũy theo hợp đồng. Đừng nhầm điều đó với tính an toàn luồng của collection kết quả; chọn downstream theo nhu cầu dữ liệu và benchmark các phân bố khóa thực tế trước khi kết luận hiệu năng.
