# `groupingByConcurrent` và `toConcurrentMap` trong Java Stream

Khi xử lý nhiều phần tử bằng `parallelStream()`, thao tác gom về `Map` có thể tốn thời gian hợp nhất các map trung gian. Java cung cấp hai collector **concurrent** trong `java.util.stream.Collectors` để nhiều tác vụ có thể đóng góp vào một `ConcurrentMap`: `groupingByConcurrent` cho **một khóa → một nhóm/giá trị tổng hợp**, và `toConcurrentMap` cho **một khóa → một giá trị**, có thể gộp khi khóa trùng.

Cả hai API đã có từ Java 8 và **vẫn được sử dụng trong Java hiện đại**. Điều quan trọng nhất là hiểu sự đánh đổi: hỗ trợ concurrent reduction và không bảo đảm *encounter order*. `ConcurrentMap` ở kết quả cũng không có nghĩa mọi giá trị nằm bên trong map đều tự động an toàn khi bị sửa từ nhiều luồng.

## 1. Phân biệt bốn collector thường gặp

| Collector | Kiểu kết quả | Khi nhiều phần tử cùng khóa | Concurrent reduction | Thứ tự |
| --- | --- | --- | --- | --- |
| `groupingBy(classifier)` | `Map<K, List<T>>` | Giữ các phần tử trong nhóm | Collector không có `CONCURRENT` | Với nguồn ordered, downstream như `toList()` có thể bảo toàn encounter order trong mỗi nhóm |
| `groupingByConcurrent(classifier)` | `ConcurrentMap<K, List<T>>` | Giữ các phần tử trong nhóm | Có `CONCURRENT` và `UNORDERED` | Không cam kết thứ tự phần tử trong mỗi nhóm |
| `toMap(key, value)` | `Map<K, V>` | Mặc định ném `IllegalStateException` khi khóa trùng; overload khác nhận hàm merge | Collector không có `CONCURRENT` | Không cam kết thứ tự duyệt khóa nếu không chỉ định map |
| `toConcurrentMap(key, value)` | `ConcurrentMap<K, V>` | Mặc định ném `IllegalStateException` khi khóa trùng; overload khác nhận hàm merge | Có `CONCURRENT` và `UNORDERED` | Không cam kết encounter order |

Lưu ý: `groupingByConcurrent` **không tự động thay thế** `groupingBy`; `toConcurrentMap` **không tự động thay thế** `toMap`. Chúng giải quyết bài toán với thứ tự và đặc tính thực thi khác nhau. Nếu nhóm cần giữ đúng thứ tự từ nguồn, hãy cân nhắc `groupingBy` cùng downstream có đặc tính ordered, rồi đo hiệu năng với dữ liệu thực.

Trong `groupingByConcurrent`, số phần tử trong nhóm vẫn đúng cho dữ liệu hợp lệ; điều không được cam kết là **thứ tự** các phần tử trong danh sách. Khi cần xuất báo cáo theo thứ tự cụ thể, hãy sắp xếp **sau khi thu thập**, theo khóa/thuộc tính nghiệp vụ.

## 2. Concurrent reduction thực sự diễn ra khi nào?

Một `Collector` có đặc tính `CONCURRENT` cho phép `Stream.collect` tích lũy đồng thời vào cùng vùng chứa kết quả. Tuy nhiên, **chỉ gắn nhãn collector là concurrent không làm stream tự chạy song song**.

Theo hợp đồng của Stream API, concurrent reduction được thực hiện khi:

1. Stream chạy **parallel** (`parallelStream()` hoặc `stream().parallel()`).
2. Collector có `Collector.Characteristics.CONCURRENT`.
3. Stream là unordered **hoặc** collector có `Collector.Characteristics.UNORDERED`.

`groupingByConcurrent` và `toConcurrentMap` thỏa điều kiện collector thứ hai và thứ ba. Với nguồn `List`, dùng `parallelStream()` có thể giúp nhiều phần tử được xử lý đồng thời mà không cần gộp tất cả map con theo cách của một số collector thông thường. Việc scheduler chia task thế nào là chi tiết triển khai, không thể dựa vào để xác định “phần tử đầu tiên/cuối cùng”.

~~~java
ConcurrentMap<String, Long> countByCity = people.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Person::getCity,
        Collectors.counting()
    ));
~~~

Đây là **mã minh họa**, giả sử `people` và `Person#getCity()` đã được định nghĩa. Mỗi khóa thành phố nhận một giá trị đếm; kết quả trả về là `ConcurrentMap<String, Long>`. `Collectors.counting()` làm downstream; không cần tự thêm synchronized vào lệnh `collect`.

**Nhận định hiệu năng:** concurrent reduction có thể bớt chi phí combiner hợp nhất nhiều `Map`, nhưng vẫn có chi phí đồng bộ/tranh chấp tại các khóa. Nguồn nhỏ, xử lý rẻ, ít khóa hoặc một khóa xuất hiện quá nhiều lần có thể khiến phiên bản parallel **chậm hơn**. Chỉ kết luận hiệu năng sau khi đo bằng dữ liệu đại diện.

## 3. `groupingByConcurrent`: gom nhiều phần tử theo một khóa

### 3.1. Một tham số: giữ các phần tử theo nhóm

~~~java
ConcurrentMap<String, List<Order>> byRegion = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(Order::getRegion));
~~~

Đây là **đoạn minh họa**, `Order` và `orders` thuộc chương trình riêng. Bộ phân loại `classifier` là hàm lấy khóa `region` từ mỗi phần tử; kết quả là một `ConcurrentMap` mà mỗi khóa ánh xạ tới nhóm các đơn hàng.

Ví dụ các mã vùng `north, south, north` tạo hai nhóm. Số phần tử của `north` là 2, nhưng **không nên kiểm tra `list.get(0)` là phần tử nào** khi chạy parallel. Với concurrent grouping, thứ tự của các phần tử trong cùng nhóm không được bảo đảm.

### 3.2. Hai tham số: gom nhóm kèm phép tổng hợp downstream

~~~java
ConcurrentMap<String, Long> count = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::getRegion,
        Collectors.counting()
    ));
~~~

Các downstream thường dùng:

- `Collectors.counting()`: số phần tử mỗi nhóm (`Long`).
- `Collectors.summingInt(Order::getQuantity)`: tổng số lượng mỗi nhóm (`Integer`).
- `Collectors.mapping(Order::getSku, Collectors.toSet())`: tập SKU của mỗi vùng; tránh trùng SKU trong tập.
- `Collectors.mapping(Order::getSku, Collectors.toList())`: danh sách SKU (có thể lặp), **không cam kết thứ tự**.
- `Collectors.maxBy(Comparator.comparingInt(Order::getQuantity))`: đơn hàng có số lượng lớn nhất mỗi nhóm, kết quả kiểu `Optional<Order>`.

Các đoạn trên đều là **mã minh họa**. Khi dùng `maxBy` với nhiều bản ghi có khóa so sánh bằng nhau, hãy bổ sung quy tắc tie-break nếu cần một lựa chọn ổn định. Khi dùng `summingInt`, cân nhắc tràn `int` nếu tổng lớn.

### 3.3. Ba tham số: tự chọn `ConcurrentMap` đích

~~~java
ConcurrentMap<String, Long> countByRegion = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::getRegion,
        ConcurrentSkipListMap::new,
        Collectors.counting()
    ));
~~~

`ConcurrentSkipListMap` cho phép duyệt **các khóa đã sắp xếp theo thứ tự của comparator/natural ordering**. Đây là thứ tự duyệt **khóa**, không biến các phần tử trong danh sách downstream thành ordered.

`mapFactory` phải cung cấp một `ConcurrentMap` mới, rỗng và phù hợp kiểu khóa/giá trị. `HashMap::new`, `LinkedHashMap::new` và `TreeMap::new` không thỏa ràng buộc kiểu `ConcurrentMap` của overload này. Dùng `ConcurrentHashMap::new` (không cam kết thứ tự khóa) hoặc `ConcurrentSkipListMap::new` (khóa có thứ tự) tùy mục đích. Factory có comparator phải nhất quán với cách xác định khóa tương đương của nghiệp vụ.

## 4. `toConcurrentMap`: mỗi khóa một giá trị

Khác `groupingByConcurrent(classifier)`, `toConcurrentMap` tạo một giá trị `V` cho mỗi khóa `K`. Nếu nhiều phần tử ánh xạ vào cùng khóa, cần có **chính sách merge rõ ràng**.

### 4.1. Hai tham số: khóa bắt buộc duy nhất

~~~java
ConcurrentMap<String, User> byId = users.parallelStream()
    .collect(Collectors.toConcurrentMap(
        User::getId,
        Function.identity()
    ));
~~~

Đây là **mã minh họa**, giả sử `User` và `users` được định nghĩa. Với hai phần tử cùng khóa theo `equals`, collector mặc định ném `IllegalStateException`. Việc chạy song song không khiến khóa trùng tự biến mất, và ngoại lệ có thể được báo thông qua cơ chế xử lý task song song; không nên dựa vào thông điệp lỗi cụ thể.

Dùng dạng này khi khóa **phải duy nhất** và muốn phát hiện dữ liệu không hợp lệ. Không dùng chỉ để “hy vọng đầu vào không trùng”.

### 4.2. Ba tham số: merge giá trị khi khóa trùng

~~~java
ConcurrentMap<String, Integer> quantityBySku = orders.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Order::getSku,
        Order::getQuantity,
        Integer::sum
    ));
~~~

`keyMapper` lấy SKU, `valueMapper` lấy quantity, và `mergeFunction` gộp **hai giá trị Integer** khi các phần tử cùng SKU. Nếu một SKU có số lượng `2, 3, 4`, tổng là `9` bất kể các cặp được gộp ở thứ tự nào (trong miền không tràn số).

Một số merge policy:

~~~java
Integer::sum                    // cộng số lượng
Integer::max                    // chọn số lượng lớn nhất
(a, b) -> a                     // giữ một giá trị; "đầu" không xác định theo encounter order
(a, b) -> b                     // giữ một giá trị; "cuối" không xác định theo encounter order
~~~

**Không dùng `(a,b)->a` hoặc `(a,b)->b` để chọn “bản ghi đầu/cuối trong danh sách” khi collector là unordered.** Nếu cần “bản ghi mới nhất”, dùng thuộc tính thời gian và quy tắc tie-break rõ ràng, chẳng hạn chọn bản ghi theo `updatedAt` rồi `id`; không phụ thuộc task nào gộp trước.

Hàm merge nên **stateless, non-interfering, associative** để kết quả đúng khi chia/gộp dữ liệu song song. Những phép như `Integer::sum` và `Integer::max` phù hợp hơn việc lấy ngẫu nhiên một phía khi nghiệp vụ cần kết quả xác định.

### 4.3. Bốn tham số: lựa chọn map kết quả

~~~java
ConcurrentMap<String, Integer> totals = orders.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Order::getSku,
        Order::getQuantity,
        Integer::sum,
        ConcurrentSkipListMap::new
    ));
~~~

Đoạn minh họa trên tạo map có các **khóa** theo thứ tự. Nếu không quan tâm thứ tự, có thể dùng `ConcurrentHashMap::new` hoặc bỏ `mapFactory`.

Lưu ý: `toConcurrentMap` **không giữ nhiều giá trị riêng cho cùng khóa**. Nếu bạn muốn tất cả đơn hàng trong một nhóm, `groupingByConcurrent` mới là mô hình trực tiếp.

## 5. Ví dụ Java đầy đủ: grouping, counting, merge và khóa trùng

Lưu thành tệp **`ConcurrentCollectorsDemo.java`**. Mã chỉ dùng API có từ Java 8; biên dịch/chạy với JDK 17+.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

public class ConcurrentCollectorsDemo {

    static final class Purchase {
        private final String region;
        private final String sku;
        private final int quantity;

        Purchase(String region, String sku, int quantity) {
            this.region = region;
            this.sku = sku;
            this.quantity = quantity;
        }

        String getRegion() {
            return region;
        }

        String getSku() {
            return sku;
        }

        int getQuantity() {
            return quantity;
        }
    }

    public static void main(String[] args) {
        List<Purchase> purchases = Arrays.asList(
                new Purchase("north", "A", 2),
                new Purchase("south", "B", 4),
                new Purchase("north", "C", 3),
                new Purchase("south", "D", 1),
                new Purchase("north", "A", 5)
        );

        ConcurrentMap<String, List<Purchase>> groups =
                purchases.parallelStream().collect(
                        Collectors.groupingByConcurrent(Purchase::getRegion));

        Map<String, Integer> sizes = new TreeMap<>();
        groups.forEach((region, rows) -> sizes.put(region, rows.size()));

        ConcurrentMap<String, Long> counts =
                purchases.parallelStream().collect(
                        Collectors.groupingByConcurrent(
                                Purchase::getRegion,
                                Collectors.counting()
                        ));

        ConcurrentMap<String, List<String>> skus =
                purchases.parallelStream().collect(
                        Collectors.groupingByConcurrent(
                                Purchase::getRegion,
                                Collectors.mapping(
                                        Purchase::getSku,
                                        Collectors.toList()
                                )
                        ));
        List<String> northSkus = new ArrayList<>(skus.get("north"));
        Collections.sort(northSkus);

        ConcurrentMap<String, Integer> totals =
                purchases.parallelStream().collect(
                        Collectors.toConcurrentMap(
                                Purchase::getRegion,
                                Purchase::getQuantity,
                                Integer::sum
                        ));

        ConcurrentMap<String, Integer> sortedTotals =
                purchases.parallelStream().collect(
                        Collectors.toConcurrentMap(
                                Purchase::getRegion,
                                Purchase::getQuantity,
                                Integer::sum,
                                ConcurrentSkipListMap::new
                        ));

        ConcurrentMap<String, Long> sortedCounts =
                purchases.parallelStream().collect(
                        Collectors.groupingByConcurrent(
                                Purchase::getRegion,
                                ConcurrentSkipListMap::new,
                                Collectors.counting()
                        ));

        System.out.println("groupSizes = " + sizes);
        System.out.println("counts = " + new TreeMap<>(counts));
        System.out.println("northSkusSorted = " + northSkus);
        System.out.println("totals = " + new TreeMap<>(totals));
        System.out.println("sortedTotals = " + sortedTotals);
        System.out.println("sortedCounts = " + sortedCounts);

        try {
            purchases.parallelStream().collect(
                    Collectors.toConcurrentMap(
                            Purchase::getRegion,
                            Purchase::getQuantity
                    ));
            System.out.println("duplicates = unexpectedly accepted");
        } catch (IllegalStateException ex) {
            System.out.println("duplicates = IllegalStateException");
        }
    }
}
~~~

Chạy bằng:

~~~bash
javac -encoding UTF-8 ConcurrentCollectorsDemo.java
java ConcurrentCollectorsDemo
~~~

Đầu ra kỳ vọng **ổn định**:

~~~text
groupSizes = {north=3, south=2}
counts = {north=3, south=2}
northSkusSorted = [A, A, C]
totals = {north=10, south=5}
sortedTotals = {north=10, south=5}
sortedCounts = {north=3, south=2}
duplicates = IllegalStateException
~~~

**Vì sao đầu ra không phụ thuộc thứ tự chạy parallel?**

- `sizes` chỉ đếm số phần tử của mỗi nhóm sau khi đã thu thập xong và đưa khóa vào `TreeMap` để in theo thứ tự cố định.
- `counts` đếm được `north=3` và `south=2`; không phụ thuộc phần tử nào tích lũy trước.
- Danh sách `northSkus` **được sao chép và sắp xếp sau collect**, do `groupingByConcurrent` không bảo đảm encounter order. Nó chứa hai `A` và một `C`, nên kết quả là `[A, A, C]`.
- `totals` tính `north: 2+3+5=10`, `south: 4+1=5`. `Integer::sum` là merge rule phù hợp.
- `sortedTotals` và `sortedCounts` dùng `ConcurrentSkipListMap::new`, nên thứ tự **khóa** khi in là `north` trước `south`.
- Dạng `toConcurrentMap` hai tham số không có merge policy nên khi hai phần tử cùng `region`, nó ném `IllegalStateException`. Ví dụ chỉ in kiểu ngoại lệ để tránh phụ thuộc cách diễn đạt của JDK.

Không được đánh giá chất lượng concurrent collector bằng cách `System.out.println(map)` rồi dựa vào thứ tự ngẫu nhiên của `ConcurrentHashMap`. Hãy kiểm tra từng khóa, giá trị, kích thước nhóm hoặc sắp xếp để tạo output tái lập được.

## 6. Concurrent map an toàn đến đâu?

### 6.1. `ConcurrentMap` an toàn cho thao tác map, nhưng không tự bảo vệ giá trị mutable

Với:

~~~java
ConcurrentMap<String, List<Order>> byRegion =
    orders.parallelStream().collect(
        Collectors.groupingByConcurrent(Order::getRegion));
~~~

`ConcurrentMap` cung cấp các thao tác thread-safe ở **cấp map**. Nhưng theo hợp đồng Oracle, **không có bảo đảm rằng `List` của mỗi nhóm là thread-safe**. Collector phải xử lý tích lũy đúng trong lúc `collect` đang chạy; điều đó **không cấp quyền** cho mã khác tiếp tục gọi `list.add(...)` đồng thời lên cùng một danh sách sau khi `collect` kết thúc.

Nếu nhiều luồng sẽ tiếp tục cập nhật nhóm, hãy thiết kế một mô hình đồng bộ riêng (chẳng hạn cấu trúc dữ liệu concurrent phù hợp hoặc thao tác qua API đồng bộ có hợp đồng rõ). Chỉ vì reference của một `List` nằm trong `ConcurrentMap` không làm các phương thức trên `List` an toàn.

### 6.2. Sau khi có kết quả, ưu tiên thao tác nguyên tử khi cập nhật theo khóa

~~~java
ConcurrentMap<String, Integer> totals = new ConcurrentHashMap<>();

totals.merge("north", 2, Integer::sum);
totals.merge("north", 3, Integer::sum);
// totals.get("north") == 5
~~~

Đây là đoạn độc lập về biểu thức nhưng cần import `java.util.concurrent.ConcurrentMap` và `ConcurrentHashMap`. `merge` diễn đạt phép cập nhật dựa trên khóa tốt hơn chuỗi “`get` → tính → `put`” khi có nhiều luồng cùng ghi. Với `ConcurrentHashMap`, các thao tác kết hợp được cung cấp với bảo đảm đồng thời thích hợp; vẫn phải đọc hợp đồng cụ thể của map và hàm remapping.

**Không sửa map nguồn đang được duyệt trong pipeline.** Hàm classifier, value mapper và merge nên không can thiệp vào stream source, không phụ thuộc mutable state bên ngoài, và không thực hiện I/O có side effect khó kiểm soát.

### 6.3. Null và miền khóa

Với triển khai `ConcurrentHashMap` và `ConcurrentSkipListMap` thông dụng, **null key/null value không được chấp nhận**. `groupingByConcurrent` với classifier trả `null` có thể gây `NullPointerException`; `toConcurrentMap` với key mapper hoặc value mapper cho null cũng có thể thất bại. Hãy lọc dữ liệu không hợp lệ hoặc chọn chính sách biểu diễn “chưa có giá trị” rõ ràng, thay vì nhét null vào collector.

Đối với `ConcurrentSkipListMap`, khóa còn phải so sánh được theo natural order hoặc comparator. Comparator quyết định khi nào hai khóa tương đương; nếu comparator coi hai khóa khác nhau là bằng nhau, các giá trị có thể bị gộp về cùng một khóa logic.

### 6.4. Hàm merge và thứ tự không xác định

~~~java
(first, later) -> first
(first, later) -> later
~~~

Các chính sách trên không mang nghĩa “bản ghi đầu tiên/cuối cùng của `List`” đối với concurrent collector unordered. Nếu dữ liệu có `updatedAt`, hãy đưa ra quy tắc chọn thời điểm lớn hơn và tie-break bằng id để bảo đảm kết quả bất kể thứ tự kết hợp. Khi phép merge không kết hợp hoặc có side effect, dữ liệu có thể cho kết quả khác nhau giữa các lần chạy parallel.

Với số dấu phẩy động, cộng các giá trị `double` theo thứ tự khác nhau có thể thay đổi kết quả do làm tròn; khi đòi kết quả số học bitwise cố định, cần thiết kế cách tổng hợp khác và kiểm tra thực nghiệm.

## 7. Chọn collector theo mục tiêu

### Khi cần nhiều phần tử trong mỗi nhóm

Dùng `groupingByConcurrent(classifier)` nếu:

- Dữ liệu đủ lớn để parallel processing có giá trị.
- Không cần thứ tự phần tử trong nhóm.
- Các nhóm có thể tích lũy concurrent.
- Muốn nhận `ConcurrentMap<K,List<T>>` sau khi thu thập.

Nếu cần giữ đúng encounter order, ưu tiên `groupingBy(...)` (hoặc thiết kế sắp xếp kết quả sau collect nếu yêu cầu là thứ tự theo một thuộc tính). Nếu chỉ cần số lượng/tổng, downstream `counting()`, `summingInt()`... tránh lưu toàn bộ danh sách.

### Khi cần đúng một giá trị cho mỗi khóa

Dùng `toConcurrentMap(keyMapper, valueMapper, mergeFunction)` nếu:

- Mỗi khóa cần một giá trị số hoặc một bản ghi được gộp theo quy tắc rõ ràng.
- Merge associative/stateless, không phụ thuộc thứ tự task.
- Không có yêu cầu bảo toàn encounter order.
- Muốn dùng kết quả theo hợp đồng `ConcurrentMap`.

Nếu khóa phải duy nhất, dùng overload **hai tham số** để fail fast; nếu khóa có thể trùng hợp lệ, cung cấp **merge**. Nếu muốn giữ mọi giá trị cùng khóa, chuyển sang grouping collector thay vì merge bằng việc bỏ dữ liệu.

### Khi cần thứ tự khóa

- Muốn sorted keys trong khi vẫn dùng collector concurrent: dùng overload có `ConcurrentSkipListMap::new`.
- Chỉ cần sorted output cuối cùng: có thể collect vào map thường rồi duyệt qua `new TreeMap<>(result)` hoặc sort `entrySet` sau collect. 
- Không nhầm sorted keys với encounter order của các phần tử bên trong mỗi nhóm.

## 8. Chi phí, tranh chấp và cách đo

Giả sử có `n` phần tử, `k` khóa khác nhau:

- Phân loại và thêm vào map hash có chi phí dự kiến gần `O(n)` khi hash phân bố tốt và hàm classifier/merge rẻ; đây là đánh giá bậc chi phí thông thường, không phải cam kết của API.
- `groupingByConcurrent(classifier)` lưu **mọi phần tử** trong các danh sách, nên dùng bộ nhớ theo tổng kích thước dữ liệu, xấp xỉ `O(n)` cộng overhead map.
- `groupingByConcurrent(classifier, counting())` và `toConcurrentMap(..., Integer::sum)` có thể chỉ cần lưu một giá trị tổng hợp mỗi khóa, thường gần `O(k)` (chưa tính bộ nhớ của nguồn).
- `ConcurrentSkipListMap` duy trì thứ tự khóa với các thao tác thường khoảng `O(log k)`, nên có overhead khác `ConcurrentHashMap`.
- **Hot key**: nếu hầu hết phần tử cùng một khóa, nhiều luồng có thể tranh chấp quyền cập nhật kết quả của khóa đó. Nhiều khóa phân bố tương đối đều thường có khả năng mở rộng tốt hơn.
- **Downstream nặng**: `counting()`, `mapping(...)`, phép tính phức tạp hoặc cấp phát nhiều đối tượng ảnh hưởng throughput. Concurrent collector không bảo đảm downstream bất kỳ chạy không cần phối hợp giữa luồng.
- **Nguồn nhỏ**: chi phí khởi tạo và phối hợp parallel tasks có thể vượt phần lợi ích. Thay `stream()` bằng `parallelStream()` cần số liệu thử nghiệm, không phải tối ưu mặc định.

Đo `throughput`, thời gian và bộ nhớ trên dữ liệu đại diện, đồng thời so sánh kết quả bằng **logic nội dung** thay vì thứ tự hiển thị. Khi benchmark nghiêm túc, dùng JMH, làm nóng JVM, thử nhiều kích thước và phân phối khóa. Không lấy một lần chạy `System.nanoTime()` làm kết luận.

## 9. Các lỗi phổ biến cần tránh

1. **Cho rằng tên `groupingByConcurrent` làm `List` con thread-safe.** Chỉ `ConcurrentMap` có hợp đồng đồng thời ở cấp map; danh sách con không được bảo đảm an toàn cho thao tác ghi đồng thời bên ngoài collector.
2. **Phụ thuộc thứ tự xuất hiện.** `groupingByConcurrent` và `toConcurrentMap` là unordered collector. Không kỳ vọng phần tử đầu tiên trong nhóm hoặc `(a,b)->a` là “dòng đầu tiên” của nguồn.
3. **Nhầm trùng khóa với lỗi tất yếu.** Trùng khóa hợp lệ với `groupingByConcurrent` vì các phần tử được gom thành nhóm; trùng khóa chỉ lỗi với `toConcurrentMap` hai tham số, hoặc cần merge rule nếu dùng overload khác.
4. **Dùng sai map supplier.** Các overload concurrent yêu cầu `ConcurrentMap`, không nhận `HashMap::new`, `TreeMap::new` hay `LinkedHashMap::new`.
5. **Để mapper trả null.** Các triển khai concurrent map phổ biến cấm null key/value, gây lỗi khi collect; nên validate và xử lý dữ liệu thiếu từ trước.
6. **Gộp bằng hàm không associative hoặc có state bên ngoài.** Kết quả có thể phụ thuộc cách chia/gộp và scheduling; bảo đảm nguyên tắc cho parallel reduction.
7. **Tin rằng kết quả `Map` an toàn nghĩa là `value` cũng an toàn.** `ConcurrentMap<String, ArrayList<...>>` không tự bảo vệ phương thức `add` của các `ArrayList`.
8. **Dùng parallel ở mọi nơi.** Key skew, overhead và downstream contention có thể khiến hiệu năng xấu hơn; phải benchmark.
9. **Nhầm `sorted keys` với ordered groups.** `ConcurrentSkipListMap` chỉ đảm bảo thứ tự duyệt khóa, còn thứ tự phần tử trong `List` vẫn không được bảo đảm.
10. **Bỏ qua số học và dữ liệu biên.** `Integer::sum` có thể tràn int; stream rỗng trả map rỗng; classifier đưa tất cả phần tử về một khóa tạo hot key; null làm collector thất bại.

## 10. Checklist áp dụng

1. Muốn **nhóm nhiều phần tử** hay **một giá trị mỗi khóa**? Chọn `groupingByConcurrent` hoặc `toConcurrentMap` cho đúng mô hình.
2. Nếu chọn `toConcurrentMap`, khóa có thể trùng không? Nếu có, xác định merge policy gắn với yêu cầu nghiệp vụ.
3. Có cần encounter order không? Nếu có, chọn collector ordered phù hợp hoặc xác định quy tắc sort sau collect.
4. Hàm classifier/keyMapper/valueMapper/merge có stateless, không gây side effect và chịu được parallel không?
5. Có trường hợp khóa hoặc giá trị null, comparator không nhất quán, hay dữ liệu tràn số không?
6. Nếu có downstream danh sách, có ai sửa danh sách đồng thời sau collect không? Nếu có, cần cách đồng bộ riêng.
7. Có cần sorted keys không? Nếu có, cân nhắc `ConcurrentSkipListMap::new` hoặc bước sort riêng.
8. Nguồn đủ lớn, số khóa phân tán đủ tốt và công việc đủ nặng để parallel có lợi không? Đo rồi quyết định.

**Ghi nhớ:** `groupingByConcurrent` để tạo **nhóm theo khóa**; `toConcurrentMap` để tạo **một giá trị theo khóa** và giải quyết trùng bằng merge rule. Cả hai hỗ trợ concurrent reduction nhưng **không cam kết encounter order**, và cấu trúc dữ liệu nằm bên trong `ConcurrentMap` cần được đánh giá an toàn luồng một cách riêng biệt.

## Tài liệu chính thức

- [Oracle Java API — `Collectors.groupingByConcurrent` và `Collectors.toConcurrentMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java API — `java.util.stream`: Concurrent reduction, ordering và associativity](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java API — `Collector.Characteristics`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.Characteristics.html)
- [Oracle Java API — `ConcurrentMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)
