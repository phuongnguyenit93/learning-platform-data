# Chọn loại Map để kiểm soát thứ tự khóa khi nhóm và phân vùng trong Java

## 1. Vì sao Map của kết quả nhóm cần có thứ tự rõ ràng?

Khi dùng Java Stream để **nhóm dữ liệu** bằng `Collectors.groupingBy(...)`, kết quả thường là một `Map<K, ...>`: mỗi khóa đại diện cho một nhóm, còn giá trị là các phần tử hoặc thống kê của nhóm đó. Việc nhóm đúng chưa đủ nếu API, báo cáo hoặc giao diện cần hiển thị **các nhóm theo một thứ tự cụ thể**.

Ví dụ nguồn đơn hàng xuất hiện theo thứ tự:

~~~text
Games(15), Books(10), Food(8), Games(5), Books(20)
~~~

Sau khi nhóm theo loại hàng và tính tổng, có ba khóa:
- `Games` có tổng 20.
- `Books` có tổng 30.
- `Food` có tổng 8.

Ta có thể muốn hiển thị các nhóm theo hai quy tắc khác nhau:

~~~text
Thứ tự gặp lần đầu: Games → Books → Food
Thứ tự tên tăng dần: Books → Food → Games
~~~

Cùng dữ liệu và cùng hàm phân nhóm, **loại Map được chọn có thể điều khiển thứ tự duyệt khóa**. Vì vậy phải xác định yêu cầu trước khi gọi collector.

Ba lựa chọn nền tảng:

| Nhu cầu | Loại Map phù hợp | Ý nghĩa về thứ tự |
| --- | --- | --- |
| Chỉ tra cứu và thống kê, không phụ thuộc thứ tự | `Map` do collector cung cấp, hoặc `HashMap` nếu tự chọn | Không cam kết thứ tự duyệt |
| Duyệt theo thứ tự **khóa được thêm vào lần đầu** | `LinkedHashMap` kiểu insertion-order | Ghi nhớ thứ tự chèn khóa |
| Duyệt khóa **theo thứ tự so sánh** | `TreeMap` | Sắp tăng dần theo natural order hoặc theo Comparator |

**Lưu ý quan trọng:** `Map<K,V>` tự nó không đảm bảo một thứ tự duyệt chung. Phải xét **implementation thực tế** và **hợp đồng** của collector. Một kết quả trông như đã sắp xếp trên máy của bạn chưa đủ để khẳng định nó có thứ tự được bảo đảm.

## 2. groupingBy mặc định không cam kết loại Map hoặc thứ tự khóa

Cách viết ngắn nhất là:

~~~java
Map<String, List<Sale>> grouped = sales.stream()
        .collect(Collectors.groupingBy(Sale::category));
~~~

Đây là **đoạn minh họa trong một phương thức**, cần import `java.util.Map`, `java.util.List`, `java.util.stream.Collectors` và class `Sale` có phương thức `category()`.

Chữ ký tổng quát của dạng collector này có thể đọc là:

~~~java
groupingBy(classifier)
~~~

Hàm `classifier` nhận từng phần tử và trả về **khóa nhóm**. Các phần tử có cùng khóa theo tiêu chuẩn bằng nhau của Map được đưa vào cùng nhóm.

Theo hợp đồng API, overload `groupingBy(classifier)` **không bảo đảm** kiểu cụ thể, tính mutable, serialization, hoặc thread-safety của Map kết quả. Do đó không nên viết nghiệp vụ giả định nó nhất thiết là `HashMap` hay có thứ tự ngẫu nhiên ổn định.

Ví dụ một lần chạy có thể cho những khóa trông như:

~~~text
[Books, Games, Food]
~~~

Nhưng không được lấy dãy đó làm **kỳ vọng bắt buộc**. Lần chạy khác, dữ liệu khác hoặc implementation khác có thể cho thứ tự khác.

### 2.1. Đừng dựa vào sự trùng hợp của HashMap

`HashMap` không cam kết thứ tự iteration theo thứ tự chèn cũng như thứ tự sắp xếp. Thứ tự xuất hiện thực tế có thể chịu tác động của hash, dung lượng bảng, rehash và chi tiết implementation.

Nếu việc duyệt theo khóa là một phần của yêu cầu (ví dụ danh mục theo alphabet, thống kê giữ thứ tự nguồn), phải **chọn Map theo hợp đồng** thay vì cố điều khiển thứ tự dựa trên các giá trị hash hiện quan sát.

## 3. groupingBy với mapFactory — điểm mở rộng quan trọng

Java có overload:

~~~java
groupingBy(classifier, mapFactory, downstream)
~~~

Nó cho phép đưa một `Supplier<M extends Map<K,D>>` để **tạo Map kết quả**. Đó là cách kiểm soát loại Map được dùng trong grouping.

Ví dụ:

~~~java
Map<String, Long> counts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.counting()));
~~~

Đoạn minh họa này cần import `java.util.LinkedHashMap`, `java.util.Map`, `java.util.stream.Collectors`. `Collectors.counting()` là *downstream collector*, tạo giá trị tổng hợp là số phần tử của mỗi nhóm.

**Đọc ba tham số theo thứ tự:**

1. **classifier**: `Sale::category` quyết định khóa nhóm.
2. **mapFactory**: `LinkedHashMap::new` quyết định Map lưu kết quả và thứ tự chèn khóa.
3. **downstream**: `Collectors.counting()` quyết định giá trị tại mỗi khóa là tổng số phần tử.

Nếu muốn nhóm thành danh sách thay vì đếm:

~~~java
Map<String, List<Sale>> grouped = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.toList()));
~~~

Như vậy, **loại Map** và **cách tích lũy giá trị mỗi nhóm** là hai lựa chọn riêng. Không nên coi `LinkedHashMap` là một collector đếm hoặc tự nghĩ nó thay thế `Collectors.toList()`.

### 3.1. Vì sao không truyền LinkedHashMap trực tiếp cho groupingBy(classifier, downstream)?

Dạng hai đối số:

~~~java
groupingBy(classifier, downstream)
~~~

không có tham số mapFactory. Nếu muốn kiểm soát Map đầu ra, sử dụng **dạng ba đối số**. Đoạn mã cần supplier thực sự tạo Map, ví dụ `LinkedHashMap::new`, không dùng `new LinkedHashMap<>()` làm đối số chỗ đó.

## 4. LinkedHashMap — giữ thứ tự khóa xuất hiện lần đầu

`LinkedHashMap` mặc định lưu **insertion order**. Nếu một khóa được thêm vào rồi xuất hiện lại, cập nhật giá trị của khóa đó trong Map insertion-order thông thường không làm nó chuyển xuống cuối chỉ vì cập nhật.

Ví dụ đầu vào:

~~~text
Games, Books, Food, Games, Books
~~~

với một **Stream tuần tự, có encounter order**, dùng `groupingBy(..., LinkedHashMap::new, ...)`:

~~~java
Map<String, Long> counts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.counting()));

System.out.println(counts.keySet());
~~~

Nếu các phần tử nguồn đúng theo thứ tự trên, các khóa được chèn lần đầu lần lượt là `Games`, `Books`, `Food`. Kết quả mong đợi:

~~~text
[Games, Books, Food]
~~~

Với dữ liệu nhóm, đó thường là cách đúng cho yêu cầu **“giữ thứ tự nhóm xuất hiện trong file nhập hoặc danh sách nguồn”**.

### 4.1. Điều kiện để nói “thứ tự xuất hiện”

Không phải mọi nguồn Stream đều có thứ tự gặp rõ ràng. Các trường hợp:

- `List.of(...)` và `ArrayList` có encounter order theo thứ tự phần tử.
- `LinkedHashSet` thường cung cấp iteration order theo thứ tự chèn.
- `HashSet` không hứa thứ tự theo vị trí chèn.
- Sau `sorted(...)`, thứ tự gặp được quyết định bởi phép sắp xếp mới.
- Sau `unordered()`, không còn dựa vào ràng buộc encounter order tương tự.

Với `HashSet.stream()`, dù đích là `LinkedHashMap`, **thứ tự nhóm được thêm lần đầu khi duyệt không nhất thiết là thứ tự nguồn nghiệp vụ mong muốn**. LinkedHashMap ghi nhớ thứ tự chèn, nhưng không tạo ra thứ tự đúng nghiệp vụ nếu nguồn không có thứ tự.

### 4.2. Cẩn thận với parallel stream

Khi dùng `parallelStream()`, quá trình chia nguồn và hợp nhất kết quả làm việc suy luận “nhóm đầu tiên được phát hiện trên thread nào sẽ được chèn trước” trở nên nguy hiểm. Không dựa vào **lịch chạy vật lý** hoặc các lần thêm vào Map từng phần để suy ra thứ tự khóa.

Nếu mục tiêu là **thứ tự nhóm xuất hiện đầu tiên**, cách đơn giản, dễ giải thích và kiểm thử là dùng **sequential ordered Stream** rồi `LinkedHashMap::new`. Nếu mục tiêu là thứ tự bảng báo cáo ổn định không phụ thuộc lịch xử lý, `TreeMap` hoặc một bước sắp xếp tường minh sau khi tổng hợp có thể phù hợp hơn.

Không nên hiểu từ “Linked” là Map tự động thread-safe: `LinkedHashMap` **không** cung cấp tính an toàn ghi đồng thời tùy ý.

### 4.3. LinkedHashMap còn có access-order

Một constructor đặc biệt của `LinkedHashMap` cho phép access-order, chẳng hạn:

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
~~~

Đây là mã minh họa bên trong một phương thức, cần import `java.util.LinkedHashMap`. Giá trị `true` bật thứ tự **truy cập gần đây**, khác thứ tự chèn. Một số thao tác truy cập có thể thay đổi vị trí iteration của khóa.

Trong bài toán nhóm cần thứ tự xuất hiện lần đầu, nên dùng `LinkedHashMap::new` mặc định **insertion-order**. Không cung cấp một mapFactory kiểu access-order rồi cho rằng thứ tự khóa vẫn theo lần xuất hiện đầu.

## 5. TreeMap — sắp xếp khóa theo natural order hoặc Comparator

Nếu yêu cầu là **“hiển thị nhóm theo tên tăng dần”**, dùng `TreeMap`:

~~~java
Map<String, Integer> totals = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));
~~~

Đoạn minh họa cần import `java.util.Map`, `java.util.TreeMap`, `java.util.stream.Collectors`. Với các khóa `Games`, `Books` và `Food`, thứ tự iteration của `TreeMap` là:

~~~text
[Books, Food, Games]
~~~

`TreeMap` triển khai `SortedMap` và `NavigableMap`, sắp xếp khóa theo **natural ordering** hoặc `Comparator` do ta cung cấp. Đây là quy tắc về thứ tự **giá trị khóa**, không phải thứ tự xuất hiện của phần tử trong Stream.

### 5.1. Đảo thứ tự bằng comparator

~~~java
Map<String, Integer> reversed = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                () -> new TreeMap<>(Comparator.reverseOrder()),
                Collectors.summingInt(Sale::amount)));
~~~

Đoạn minh họa cần import `java.util.Comparator`, `TreeMap`, `Map` và `Collectors`. Khi duyệt khóa, kết quả:

~~~text
[Games, Food, Books]
~~~

Dùng cách này khi cần nhóm theo khóa giảm dần. Không dùng `HashMap` rồi trông chờ vào việc print ra chuỗi trông có vẻ giảm dần.

### 5.2. TreeMap sắp xếp theo khóa, không tự sắp xếp theo tổng nhóm

Ví dụ tổng tiền là:

~~~text
Games=20, Books=30, Food=8
~~~

`TreeMap<String,Integer>` sắp theo **String key**, nên thứ tự tăng dần là `Books`, `Food`, `Games`. Nó **không** tự đưa Food (8) lên đầu vì giá trị thấp hơn.

Nếu muốn **sắp các nhóm theo tổng tiền giảm dần**, phải tính xong tổng rồi **sắp xếp các entry theo value**, với tie-breaker phù hợp:

~~~java
List<Map.Entry<String, Integer>> byAmount = totals.entrySet().stream()
        .sorted(Map.Entry.<String, Integer>comparingByValue().reversed()
                .thenComparing(Map.Entry.comparingByKey()))
        .toList();
~~~

Đây là mã minh họa trong một phương thức, `totals` là `Map<String,Integer>` và cần import `java.util.List`, `java.util.Map`. Đầu ra có thứ tự giá trị giảm và khi bằng nhau được so sánh theo tên khóa. Nếu cần trả về Map vẫn duy trì thứ tự entry này, sau bước sort có thể collect sang `LinkedHashMap` với merge policy rõ ràng, thay vì `TreeMap`.

### 5.3. So sánh String không đồng nghĩa collation theo ngôn ngữ

Natural order của `String` dựa trên so sánh ký tự theo quy tắc Java, **không phải thứ tự từ điển theo locale** (ví dụ tiếng Việt).

Nếu báo cáo cần thứ tự phân loại theo vùng/ngôn ngữ, cần comparator phù hợp, có thể xem `java.text.Collator` hoặc một khóa sắp xếp được chuẩn hóa có chủ đích. Nhưng việc chọn Comparator cho `TreeMap` còn quyết định **khi nào hai khóa được coi là tương đương**; hãy xem phần tiếp theo.

## 6. Cạm bẫy của TreeMap: Comparator có thể gộp hai khóa khác nhau

Trong `TreeMap`, hai khóa được coi như cùng vị trí Map khi comparator cho kết quả **0**. Điều này ảnh hưởng trực tiếp tới `groupingBy`.

Ví dụ dữ liệu:

~~~text
Java, java, JAVA, Go
~~~

và collector:

~~~java
Map<String, Long> grouped = words.stream()
        .collect(Collectors.groupingBy(
                name -> name,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER),
                Collectors.counting()));
~~~

Đoạn minh họa cần import `Map`, `TreeMap` và `Collectors`. Comparator không phân biệt hoa/thường khi so sánh; vì vậy ba chuỗi `Java`, `java` và `JAVA` cùng thuộc **một khóa tương đương** trong TreeMap, dù `String.equals` trên ba chuỗi phân biệt chúng.

Kết quả kiểm thử Java 17:

~~~text
grouped.size() = 2
grouped.get("Java") = 3
grouped.get("Go") = 1
~~~

**Hệ quả:** Comparator không chỉ sắp xếp, nó còn có thể **làm thay đổi cách phân nhóm**! Nếu các khóa phải khác nhau theo `equals`, hãy bảo đảm comparator **consistent with equals** hoặc tách bước nhóm và bước hiển thị thành hai cấu trúc.

Ví dụ nếu muốn giữ `Java` và `java` là hai khóa khác nhau nhưng sắp xếp gần nhau, có thể dùng comparator case-insensitive **kèm tie-break theo natural order** để không trả 0 cho hai chuỗi khác nhau:

~~~java
Comparator<String> order = String.CASE_INSENSITIVE_ORDER
        .thenComparing(Comparator.naturalOrder());

Map<String, Integer> map = new TreeMap<>(order);
~~~

Đây là đoạn minh họa trong một phương thức, cần import `java.util.Comparator`, `Map`, `TreeMap`. Dùng comparator cần được kiểm thử trên domain khóa thực tế, đặc biệt với Unicode, chữ hoa/thường và chuỗi đã chuẩn hóa.

### 6.1. Null và khả năng so sánh

Với `TreeMap` theo natural order, khóa phải so sánh được một cách hợp lệ; kiểu không có natural ordering thích hợp có thể dẫn tới `ClassCastException` khi chèn/so sánh. Việc hỗ trợ `null` phụ thuộc comparator; natural-order TreeMap không chấp nhận khóa null theo hợp đồng thường dùng.

Riêng `Collectors.groupingBy` ở Java 17 cũng không phù hợp để dùng classifier trả null trong tình huống thông thường; implementation kiểm tra và có thể ném `NullPointerException`. Nếu dữ liệu nguồn có khóa thiếu, hãy làm rõ chính sách: bỏ phần tử, dùng một khóa sentinel phù hợp, hoặc mô hình hóa “không phân loại” thành loại nghiệp vụ rõ ràng.

## 7. Phân biệt thứ tự khóa với thứ tự phần tử trong từng nhóm

Có ít nhất **hai trục thứ tự độc lập**:

1. **Thứ tự các khóa được duyệt:** quyết định bởi loại Map.
2. **Thứ tự các phần tử trong mỗi nhóm:** quyết định bởi nguồn, pipeline và downstream collector.

Ví dụ:

~~~java
Map<String, List<Integer>> amounts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.mapping(Sale::amount, Collectors.toList())));
~~~

Với dữ liệu mẫu:

~~~text
Games=[15, 5]
Books=[10, 20]
Food=[8]
~~~

`LinkedHashMap` quyết định khóa hiển thị là Games, Books, Food. Còn `Collectors.mapping(Sale::amount, Collectors.toList())` quyết định giá trị nhóm là danh sách các khoản tiền; từ Stream tuần tự của `List` có encounter order trong ví dụ, chúng xuất hiện theo thứ tự tương ứng với phần tử nguồn trong từng nhóm.

Nếu thay mapFactory thành `TreeMap::new`, **thứ tự khóa thay đổi**, nhưng điều đó không tự động sắp xếp các số tiền bên trong nhóm. Muốn sắp giá trị từng nhóm, cần một downstream collector hoặc bước xử lý khác, ví dụ `collectingAndThen(toList(), list -> list.stream().sorted().toList())` khi đúng ngữ nghĩa.

Đừng hiểu “TreeMap đã sort” là “mọi danh sách con trong Map đều đã sort”.

## 8. partitioningBy: chỉ có hai khóa Boolean, không có mapFactory

`Collectors.partitioningBy(predicate)` chia phần tử thành hai tập theo một điều kiện:

- Khóa `Boolean.FALSE`: phần tử không thỏa.
- Khóa `Boolean.TRUE`: phần tử thỏa.

Ví dụ:

~~~java
Map<Boolean, Long> partition = sales.stream()
        .collect(Collectors.partitioningBy(
                sale -> sale.amount() >= 10,
                Collectors.counting()));
~~~

Với dữ liệu mẫu:

~~~text
false -> 2 phần tử
true  -> 3 phần tử
~~~

**Điều cần phân biệt:** `partitioningBy` không cung cấp một overload có tham số mapFactory như `groupingBy(classifier, mapFactory, downstream)`. API bảo đảm Map kết quả chứa hai khóa `true` và `false`, nhưng **không cam kết kiểu Map hay iteration order của hai khóa**.

Vì vậy, nếu UI yêu cầu **“Không đạt” trước “Đạt”**, hãy truy cập tường minh:

~~~java
System.out.println("Không đạt: " + partition.get(false));
System.out.println("Đạt: " + partition.get(true));
~~~

Thay vì:

~~~java
// Không nên coi iteration order là thứ tự nghiệp vụ:
// partition.forEach((key, value) -> System.out.println(key + ": " + value));
~~~

### 8.1. Trường hợp nguồn rỗng

Một đặc điểm hữu ích là `partitioningBy` với downstream được thiết kế theo hai phân vùng: Map kết quả vẫn chứa **cả hai khóa Boolean**, dù một phía hoặc cả hai không có phần tử.

Chẳng hạn trên nguồn rỗng và downstream mặc định `toList()`:

~~~java
Map<Boolean, List<String>> empty = Stream.<String>empty()
        .collect(Collectors.partitioningBy(s -> s.length() >= 3));

System.out.println(empty.get(false).size()); // 0
System.out.println(empty.get(true).size());  // 0
~~~

Đoạn minh họa cần import `Map`, `List`, `Stream`, `Collectors`. Cách truy cập này không dựa vào thứ tự khóa hoặc class Map do implementation chọn.

### 8.2. Nếu thực sự cần một Map có thứ tự sau phân vùng

Có thể tạo **một Map riêng** với cấu trúc cần dùng để xuất báo cáo, ví dụ:

~~~java
Map<Boolean, Long> ordered = new LinkedHashMap<>();
ordered.put(false, partition.get(false));
ordered.put(true, partition.get(true));
~~~

Đoạn minh họa đặt trong phương thức, cần import `Map` và `LinkedHashMap`. Nó nêu rõ thứ tự trình bày, **không thay đổi hợp đồng của partitioningBy**. Với chỉ hai nhãn nghiệp vụ, đôi khi một record có hai trường hoặc in hai dòng tường minh còn dễ hiểu hơn.

## 9. toMap: chọn Map bằng overload bốn đối số

Ngoài `groupingBy`, `Collectors.toMap(...)` cũng có một dạng nhận nhà cung cấp Map:

~~~java
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

Ví dụ gom tổng tiền theo loại bằng `TreeMap`:

~~~java
Map<String, Integer> totals = sales.stream()
        .collect(Collectors.toMap(
                Sale::category,
                Sale::amount,
                Integer::sum,
                TreeMap::new));
~~~

Đây là đoạn minh họa trong một phương thức. `keyMapper` chọn loại hàng, `valueMapper` chọn giá trị tiền, `mergeFunction` dùng khi có nhiều phần tử cùng khóa, còn `mapFactory` quyết định loại Map.

Với dữ liệu mẫu, kết quả được duyệt theo natural ordering của TreeMap:

~~~text
{Books=30, Food=8, Games=20}
~~~

**Lưu ý về khóa trùng:** nếu dùng dạng `toMap(keyMapper, valueMapper)` mà gặp nhiều phần tử có cùng khóa và không cung cấp hàm merge thích hợp, collector có thể ném `IllegalStateException`. Do đó, khi muốn cộng nhiều dòng chung khóa, cần `Integer::sum` (hoặc phép merge đúng domain). `groupingBy(..., summingInt(...))` thường diễn đạt ý định nhóm và tổng hợp một cách trực tiếp hơn.

Dạng `toMap` có mapFactory phù hợp khi ánh xạ và xử lý trùng khóa được xác định rõ, không phải cách duy nhất để nhóm.

## 10. groupingByConcurrent và thứ tự trong xử lý song song

Khi dùng `parallelStream()` với số lượng lớn, `Collectors.groupingByConcurrent(...)` có thể phù hợp cho một số yêu cầu hiệu năng và kết hợp dữ liệu **không cần bảo toàn encounter order**.

Nhưng cần phân biệt:

| Collector | Đặc điểm | Có phù hợp khi cần thứ tự khóa rõ? |
| --- | --- | --- |
| `groupingBy(...)` không mapFactory | Không cam kết loại Map | Không, nếu chỉ dựa vào mặc định |
| `groupingBy(..., LinkedHashMap::new, ...)` | Chọn insertion-order Map | Phù hợp với nguồn ordered, tuần tự khi muốn thứ tự xuất hiện đầu tiên |
| `groupingBy(..., TreeMap::new, ...)` | Chọn sorted-key Map | Phù hợp khi cần thứ tự theo comparator |
| `groupingByConcurrent(...)` | Collector concurrent và unordered | Không bảo đảm thứ tự khóa như LinkedHashMap/TreeMap |
| `partitioningBy(...)` | Hai khóa Boolean theo predicate | Truy cập false/true tường minh để kiểm soát thứ tự trình bày |

`groupingByConcurrent` tạo kết quả thuộc họ `ConcurrentMap`, có những overload nhận mapFactory kiểu concurrent, nhưng không nên cho rằng mình có thể truyền một `LinkedHashMap` thường vào đó để vừa concurrent vừa insertion-order. Các Map đồng thời có các hợp đồng riêng về tính an toàn và thứ tự.

Khi cần xử lý song song **và** thứ tự khóa theo báo cáo, một chiến lược dễ hiểu là **thu thập dữ liệu một cách hợp lệ**, sau đó **sắp xếp kết quả** với quy tắc được công bố. Cần đo chi phí thực tế nếu dữ liệu lớn; không mặc định groupingByConcurrent luôn nhanh hơn groupingBy trên mọi khối lượng.

**Phân biệt:** tính thread-safe của collector trong khuôn khổ Stream reduction không cho phép callback tự ý sửa Map nguồn hoặc container kết quả dùng chung bên ngoài.

## 11. Ví dụ Java 17 hoàn chỉnh: so sánh ba Map và phân vùng

Tạo file **GroupingMapOrderDemo.java**. Ví dụ có:
- `groupingBy` mặc định để tra cứu giá trị, **không dựa vào thứ tự khóa**.
- `LinkedHashMap` để giữ thứ tự nhóm xuất hiện đầu tiên.
- `TreeMap` để sắp xếp khóa tăng và giảm.
- Downstream `mapping(..., toList())` cho thấy thứ tự phần tử trong mỗi nhóm.
- `partitioningBy` với hai khóa Boolean.
- `toMap` với merge và Map factory.

~~~java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingMapOrderDemo {
    record Sale(String category, int amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Games", 15),
                new Sale("Books", 10),
                new Sale("Food", 8),
                new Sale("Games", 5),
                new Sale("Books", 20)
        );

        Map<String, Integer> defaultGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        Collectors.summingInt(Sale::amount)));

        Map<String, Integer> insertionGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        LinkedHashMap::new,
                        Collectors.summingInt(Sale::amount)));

        Map<String, Integer> sortedGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::amount)));

        Map<String, Integer> reversedGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        () -> new TreeMap<>(Comparator.reverseOrder()),
                        Collectors.summingInt(Sale::amount)));

        System.out.println("default lookups=" + defaultGroups.get("Games")
                + "/" + defaultGroups.get("Books")
                + "/" + defaultGroups.get("Food"));
        System.out.println("first-seen keys=" + insertionGroups.keySet());
        System.out.println("alphabetical keys=" + sortedGroups.keySet());
        System.out.println("reverse keys=" + reversedGroups.keySet());
        System.out.println("insertion totals=" + insertionGroups);

        Map<String, List<Integer>> amountByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        LinkedHashMap::new,
                        Collectors.mapping(Sale::amount, Collectors.toList())));
        System.out.println("amounts=" + amountByCategory);

        Map<Boolean, Long> partition = sales.stream()
                .collect(Collectors.partitioningBy(
                        sale -> sale.amount() >= 10,
                        Collectors.counting()));
        System.out.println("partition false=" + partition.get(false)
                + ", true=" + partition.get(true));

        Map<String, Integer> viaToMap = sales.stream()
                .collect(Collectors.toMap(
                        Sale::category,
                        Sale::amount,
                        Integer::sum,
                        TreeMap::new));
        System.out.println("toMap sorted=" + viaToMap);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 trở lên:

~~~bash
javac --release 17 GroupingMapOrderDemo.java
java GroupingMapOrderDemo
~~~

**Stdout đã kiểm chứng trực tiếp:**

~~~text
default lookups=20/30/8
first-seen keys=[Games, Books, Food]
alphabetical keys=[Books, Food, Games]
reverse keys=[Games, Food, Books]
insertion totals={Games=20, Books=30, Food=8}
amounts={Games=[15, 5], Books=[10, 20], Food=[8]}
partition false=2, true=3
toMap sorted={Books=30, Food=8, Games=20}
~~~

### 11.1. Giải thích output

1. `default lookups=20/30/8`: ba giá trị được truy cập **trực tiếp bằng khóa**, không phụ thuộc thứ tự iteration của Map mặc định.
2. `first-seen keys=[Games, Books, Food]`: ba khóa được đưa vào `LinkedHashMap` lần đầu theo thứ tự xuất hiện trong nguồn List tuần tự.
3. `alphabetical keys=[Books, Food, Games]`: `TreeMap` tự duyệt khóa theo natural String ordering.
4. `reverse keys=[Games, Food, Books]`: comparator đảo natural ordering.
5. `insertion totals={Games=20, Books=30, Food=8}`: phép cộng nhóm đúng, cách in Map tuân theo insertion order của LinkedHashMap.
6. `amounts={Games=[15,5], Books=[10,20], Food=[8]}`: thứ tự các khoản tiền trong mỗi nhóm phản ánh thứ tự các phần tử nguồn trong ví dụ tuần tự; đó là **thứ tự downstream**, khác thứ tự khóa.
7. `partition false=2, true=3`: phân loại theo `amount >= 10`; hai giá trị không đạt là 8 và 5.
8. `toMap sorted={Books=30, Food=8, Games=20}`: `TreeMap` dùng với toMap và merge `Integer::sum` vẫn cho thứ tự khóa tăng.

Chương trình cố tình **không in trực tiếp** Map mặc định hoặc `partition.entrySet()` để tránh một output có thứ tự khóa không được bảo đảm bởi API. Những con số và danh sách được kiểm chứng bằng `javac --release 17` và JVM thực tế.

## 12. Những lỗi thường gặp khi kiểm soát thứ tự khóa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng groupingBy mặc định trả HashMap có một thứ tự cụ thể | API không cam kết loại/thứ tự Map | Dùng mapFactory |
| Dùng HashMap cho báo cáo cần thứ tự chèn | Không đảm bảo insertion order | Dùng LinkedHashMap |
| Dùng LinkedHashMap nhưng nguồn không ordered | Không có thứ tự lần đầu đúng nghiệp vụ | Chọn nguồn có thứ tự, hoặc sort trước |
| Dùng TreeMap để “sắp theo tổng tiền” | TreeMap sắp theo **khóa**, không theo value | Sort entry sau khi aggregate |
| Dùng TreeMap comparator ignore-case nhưng muốn khóa khác hoa/thường giữ riêng | Comparator cho 0 làm hai khóa bị gộp | Dùng comparator có tie-breaker hoặc thay thiết kế |
| Nhầm thứ tự Map với thứ tự List trong giá trị nhóm | Hai thứ tự do hai cơ chế khác nhau kiểm soát | Thiết kế downstream/sort rõ ràng |
| Cho rằng partitioningBy duyệt false rồi true | API không cam kết iteration order | Truy cập bằng `get(false)`, `get(true)` |
| Truyền LinkedHashMap::new cho groupingByConcurrent | Loại Map không thuộc kiểu ConcurrentMap phù hợp | Dùng collector tương thích và sort kết quả sau |
| Dùng toMap không merge khi khóa trùng | Có thể ném IllegalStateException | Cung cấp merge function |
| Tưởng TreeMap tự hỗ trợ mọi kiểu khóa | Cần Comparable hoặc Comparator hợp lệ | Chọn comparator phù hợp domain |
| Mặc định mọi thứ tự String là thứ tự từ điển theo tiếng Việt | Natural ordering không phải locale-aware | Dùng Collator/khóa so sánh hợp đồng rõ |
| Thay Map kết quả bằng Map.copyOf và vẫn đòi iteration order ban đầu | Map bất biến được tạo bằng API đó không hứa bảo toàn iteration order | Chọn cấu trúc kết quả/DTO trình bày phù hợp |

## 13. Checklist chọn loại Map trong grouping/partitioning

Trước khi dùng `collect(...)`, kiểm tra:

1. **Thứ tự khóa có phải yêu cầu nghiệp vụ không?** Nếu không, đừng thêm chi phí sắp xếp không cần thiết.
2. **Muốn thứ tự xuất hiện đầu tiên hay thứ tự so sánh?** Thứ nhất chọn LinkedHashMap trên nguồn ordered tuần tự; thứ hai chọn TreeMap/Comparator.
3. **Nguồn có encounter order được bảo đảm không?** Nếu không, insertion-order không đồng nghĩa thứ tự nghiệp vụ.
4. **Kiểu khóa có Comparable không?** Nếu không, TreeMap cần Comparator.
5. **Comparator có thể trả 0 cho hai khóa mà domain coi khác nhau không?** Nếu có, TreeMap có thể gộp nhóm không mong muốn.
6. **Thứ tự giá trị trong nhóm có cần riêng không?** Nếu có, thiết kế downstream.
7. **Collector là groupingBy hay partitioningBy?** PartitioningBy có hai khóa Boolean và không nhận Map factory.
8. **Có khóa trùng khi dùng toMap không?** Nếu có, cần merge.
9. **Có dùng parallel hoặc groupingByConcurrent không?** Không suy thứ tự từ lịch chạy vật lý; thiết kế báo cáo/sort riêng.
10. **Có cần sort theo giá trị thống kê thay vì khóa không?** Phải sort entry theo value với tie-breaker đúng.
11. **Đầu ra có phải JSON/API yêu cầu thứ tự không?** Nếu có, quyết định cấu trúc biểu diễn và bảo đảm serializer giữ thứ tự như contract, không tự suy từ Map.
12. **Đã kiểm thử trường hợp nguồn rỗng và khóa có vẻ tương đương không?** Đây là những dữ liệu dễ lộ lỗi về grouping và comparator.

## 14. Bài tập tự kiểm tra

**Bài 1.** Một List chứa khóa theo thứ tự `["B","A","B","C"]`. Muốn Map nhóm duyệt theo thứ tự `B,A,C`, dùng gì?

**Đáp án:** `groupingBy(x -> x, LinkedHashMap::new, Collectors.toList())` trên Stream tuần tự của List. LinkedHashMap ghi lại khóa khi xuất hiện lần đầu.

**Bài 2.** Với dữ liệu đó, muốn hiển thị `A,B,C` dù nguồn có thứ tự khác, dùng gì?

**Đáp án:** `TreeMap::new` làm mapFactory nếu khóa có natural order mong muốn; hoặc comparator tường minh khi cần thứ tự khác.

**Bài 3.** Vì sao `Collectors.groupingBy(classifier)` không đủ nếu hệ thống cần in nhóm đúng thứ tự?

**Đáp án:** overload mặc định không hứa loại Map hoặc iteration order; cần mapFactory phù hợp hoặc bước sort riêng.

**Bài 4.** `partitioningBy(predicate)` có bảo đảm `entrySet()` luôn duyệt `false` trước `true` không?

**Đáp án:** Không. Truy cập tường minh `map.get(false)` rồi `map.get(true)`.

**Bài 5.** Nếu TreeMap dùng `String.CASE_INSENSITIVE_ORDER`, ba khóa `Java`, `java`, `JAVA` có thể thành bao nhiêu nhóm?

**Đáp án:** Một nhóm, vì comparator coi chúng tương đương (trả 0). Kiểm tra comparator để tránh hợp nhất khóa ngoài ý muốn.

**Bài 6.** Dùng TreeMap với khóa số tiền `price` sẽ làm gì?

**Đáp án:** Sắp xếp **theo price key**, không theo value chứa tổng số phần tử hoặc thông tin nhóm khác.

**Bài 7.** `Collectors.toMap(key, value)` có hai phần tử cùng khóa và không cung cấp merge thì sao?

**Đáp án:** Phát sinh lỗi duplicate key theo hợp đồng collector; khi cần gộp phải cung cấp merge function.

**Bài 8.** Với List sale trong ví dụ, `LinkedHashMap` có làm các khoản tiền Games tự sắp tăng từ 5 đến 15 không?

**Đáp án:** Không. Nó chỉ điều khiển iteration order của khóa Map; giá trị con do downstream collector quyết định.

**Bài 9.** Nếu cần một bảng có nhóm theo tổng tiền giảm dần, nên dùng TreeMap trực tiếp không?

**Đáp án:** Không nếu khóa TreeMap là tên nhóm. Trước hết tổng hợp rồi sort entry theo value giảm dần; dùng tie-breaker rõ ràng để có thứ tự xác định.

## 15. Tài liệu tham khảo

- [Java SE 17 — Collectors.groupingBy / partitioningBy / toMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).
- [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [Java SE 17 — Stream ordering](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

**Kết luận:** Khi nhóm hoặc phân vùng dữ liệu, **thứ tự khóa không tự được bảo đảm bởi Map hoặc groupingBy mặc định**. Với nhóm từ nguồn ordered tuần tự, dùng **`LinkedHashMap::new`** nếu muốn giữ thứ tự khóa xuất hiện lần đầu; dùng **`TreeMap::new` hoặc Comparator** nếu muốn sắp theo khóa. Với **`partitioningBy`**, truy cập `false`/`true` tường minh vì không có mapFactory; với **`toMap`**, chọn mapFactory và merge đúng. Cuối cùng, hãy luôn phân biệt **thứ tự khóa, thứ tự phần tử trong nhóm, thứ tự theo giá trị thống kê và tính đồng thời** để tránh những kết quả chỉ tình cờ đúng trên một lần chạy.
