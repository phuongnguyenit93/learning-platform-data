# Thứ tự duyệt của `Map` kết quả khi dùng Collector trong Java 10+

*Chủ đề cha: Collector bản đồ. Bài học giải thích thứ tự duyệt khóa, giá trị và entry sau khi dùng `Collectors.toMap`, `groupingBy` và các Collector tạo Map, cùng cách chọn implementation theo hợp đồng ứng dụng. Ví dụ hoàn chỉnh dùng Java 17 trở lên; các quy tắc API còn áp dụng trong Java hiện đại.*

## 1. Mục tiêu và nguyên tắc cốt lõi

Sau bài học, bạn có thể:

1. Phân biệt **thứ tự duyệt của nguồn Stream (encounter order)** và **thứ tự duyệt của Map kết quả (iteration order)**.
2. Giải thích vì sao `stream.collect(Collectors.toMap(...))` hoặc `groupingBy(...)` **không mặc nhiên giữ thứ tự phần tử nguồn**.
3. Chọn `LinkedHashMap` để duyệt theo thứ tự chèn khóa, hoặc `TreeMap` để duyệt theo thứ tự sắp xếp khóa.
4. Dùng overload `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` và `groupingBy(classifier, mapFactory, downstream)`.
5. Hiểu khóa trùng, hàm `merge` và tác động của lần xuất hiện đầu tiên tới thứ tự khóa trong Map insertion-order.
6. Nhận biết những Collector không cam kết thứ tự Map, kể cả `toUnmodifiableMap`, `groupingByConcurrent` và `partitioningBy`.
7. Bảo vệ thứ tự khi cần xuất JSON, báo cáo, log, dữ liệu hiển thị hoặc API, đồng thời tránh dựa vào thứ tự không được hợp đồng bảo đảm.
8. Viết kiểm thử có tính xác định, không phụ thuộc một thứ tự tình cờ quan sát được trên máy phát triển.

**Điểm quan trọng nhất:** Một Stream có thứ tự **không đồng nghĩa** Map tạo từ Collector có thứ tự lặp giống Stream. Thứ tự duyệt Map phụ thuộc **hợp đồng của implementation Map trả về**, không chỉ phép xử lý ở phía nguồn. Khi thứ tự là một yêu cầu thật, hãy **chọn Map thích hợp tại lúc collect** hoặc **sắp xếp rõ ràng lúc xuất dữ liệu**.

## 2. Hai khái niệm “thứ tự” khác nhau

### 2.1. Encounter order của Stream

Một nguồn như `List.of("B", "A", "C")` có thứ tự duyệt xác định. `list.stream()` tạo Stream với encounter order tương ứng `B, A, C`. Một số thao tác vẫn giữ thứ tự đó; `sorted()` chủ động tạo thứ tự mới; `unordered()` cho phép bỏ ràng buộc encounter order.

```java
// Đoạn minh họa trong phương thức:
var keys = java.util.List.of("B", "A", "C");
var orderedStream = keys.stream(); // Encounter order: B, A, C
```

Thứ tự Stream mô tả **thứ tự logic của các phần tử trong pipeline**, không phải một Map đã được tạo.

### 2.2. Iteration order của Map

Map có các view:

- `map.keySet()`: tập các khóa.
- `map.values()`: tập các giá trị ứng với các mapping.
- `map.entrySet()`: tập cặp khóa–giá trị.

Khi duyệt các view này bằng `for-each` hoặc iterator, thứ tự theo **hợp đồng Map implementation**. Ba ví dụ quen thuộc:

| Map implementation | Thứ tự duyệt được cam kết | Ý nghĩa |
| --- | --- | --- |
| `HashMap` | **Không bảo đảm thứ tự** | Phù hợp tra cứu khi thứ tự không phải yêu cầu |
| `LinkedHashMap` (mặc định) | **Thứ tự chèn khóa** | Phù hợp hiển thị theo lần khóa xuất hiện đầu |
| `TreeMap` | **Thứ tự khóa** theo natural ordering hoặc Comparator | Phù hợp báo cáo/sắp xếp theo khóa |

`Map<K,V>` là một interface; chỉ vì biến khai báo là `Map<String,Integer>`, bạn **không được suy ra** nó đang có thứ tự chèn hay thứ tự tăng dần. Hãy xem implementation thực tế/hợp đồng của factory.

**Đừng lấy một lần in `Map.toString()` làm bằng chứng.** `HashMap` có thể tình cờ in ra cùng thứ tự ở nhiều lần chạy, nhưng API không hứa điều đó. Thứ tự có thể khác khi thay số khóa, phiên bản Java, cấu trúc băm hoặc cách xây Map.

## 3. Collector mặc định có cam kết thứ tự không?

Hai overload đơn giản:

```java
Collectors.toMap(keyMapper, valueMapper)

Collectors.groupingBy(classifier)
```

là những factory rất phổ biến. Hợp đồng của chúng **không bảo đảm loại Map cụ thể, thứ tự duyệt, tính mutable, khả năng serialization hay thread-safety của Map kết quả**. Đừng suy diễn rằng vì triển khai JDK bạn đang dùng thường trả một `HashMap`, bạn có thể viết code dựa vào đúng lớp đó hoặc một thứ tự băm cụ thể.

Ví dụ:

```java
// Đoạn minh họa, giả sử sales là List<Sale>:
var amountsByRegion = sales.stream()
        .collect(java.util.stream.Collectors.toMap(
                Sale::region,
                Sale::cents));
```

`amountsByRegion` là Map có khóa vùng và số tiền tương ứng (nếu không có khóa trùng). Nhưng thứ tự của `amountsByRegion.keySet()` không được cam kết bởi overload này. Thứ tự trong `sales` **không đủ** để xác định thứ tự của Map.

### 3.1. Bảng nhanh các Collector Map

| Collector | Có tự bảo đảm thứ tự duyệt Map? | Ghi chú |
| --- | --- | --- |
| `toMap(keyMapper, valueMapper)` | Không | Trùng khóa gây `IllegalStateException` |
| `toMap(keyMapper, valueMapper, mergeFunction)` | Không | Có cách xử lý khóa trùng nhưng chưa chọn Map |
| `toMap(..., mapFactory)` | Theo Map do factory tạo | Dùng `LinkedHashMap::new` hoặc `TreeMap::new` |
| `groupingBy(classifier)` | Không | Map nhóm mặc định không cam kết thứ tự |
| `groupingBy(classifier, downstream)` | Không | Downstream không thay hợp đồng thứ tự khóa Map |
| `groupingBy(classifier, mapFactory, downstream)` | Theo Map do factory tạo | Có thể chỉ rõ thứ tự nhóm |
| `partitioningBy(predicate)` | Không cam kết thứ tự hai khóa | Truy cập qua `get(true)`/`get(false)` |
| `toUnmodifiableMap(...)` | Không cam kết thứ tự | Không cho sửa, nhưng không phải Map insertion-order |
| `toConcurrentMap(...)` | Không cam kết encounter order | Collector concurrent/unordered |
| `groupingByConcurrent(...)` | Không cam kết encounter order | Collector concurrent/unordered |

Tính **không cho sửa** và **thứ tự duyệt** là hai đặc tính độc lập. Map không cho sửa vẫn có thể không bảo đảm thứ tự khóa; Map mutable như `LinkedHashMap` lại có thể bảo đảm thứ tự chèn.

## 4. Chọn `LinkedHashMap` trong `Collectors.toMap`

Overload cho phép quyết định implementation:

```java
public static <T,K,U,M extends Map<K,U>>
Collector<T,?,M> toMap(
        Function<? super T,? extends K> keyMapper,
        Function<? super T,? extends U> valueMapper,
        BinaryOperator<U> mergeFunction,
        Supplier<M> mapFactory)
```

Đây là **chữ ký API rút gọn cách trình bày**, không phải chương trình Java độc lập. Tham số `mapFactory` tạo Map dùng để tích lũy kết quả. Nếu muốn duyệt theo lần xuất hiện đầu của khóa trong một Stream tuần tự, có encounter order rõ, dùng `LinkedHashMap::new`.

```java
var ordered = sales.stream().collect(
        java.util.stream.Collectors.toMap(
                Sale::region,
                Sale::cents,
                (first, second) -> second,
                java.util.LinkedHashMap::new));
```

Ý nghĩa:

- `Sale::region` tạo khóa.
- `Sale::cents` tạo giá trị.
- `(first, second) -> second` quyết định lấy giá trị của lần gặp sau nếu khóa trùng; đây là **chính sách ví dụ**, không phải mặc định của Collector.
- `LinkedHashMap::new` tạo Map có thứ tự chèn khóa.
- Khi khóa đã xuất hiện trước đó, cập nhật giá trị cho khóa trong một `LinkedHashMap` insertion-order thông thường **không chuyển khóa sang cuối**.

Không nhầm `mapFactory` với một hàm sắp xếp: `LinkedHashMap` **không sort**. Nó giữ thứ tự chèn, nên phải biết nguồn đưa khóa vào theo thứ tự nào.

## 5. Chọn `TreeMap` khi cần thứ tự khóa

Nếu yêu cầu là luôn xuất khóa theo thứ tự sắp xếp, không phụ thuộc lần xuất hiện ở nguồn, chọn `TreeMap::new` (hoặc cung cấp Comparator thích hợp):

```java
var bySortedKey = sales.stream().collect(
        java.util.stream.Collectors.toMap(
                Sale::region,
                Sale::cents,
                (first, second) -> second,
                java.util.TreeMap::new));
```

Với khóa kiểu `String`, `TreeMap` mặc định dùng natural ordering. `B`, `A`, `C` từ nguồn sẽ được duyệt thành `A`, `B`, `C`. `TreeMap` không phải Map “giữ thứ tự đầu vào”; nó có **thứ tự khóa theo Comparator/natural ordering**.

Lưu ý:

1. Khóa phải so sánh được bằng natural ordering, hoặc Map phải có Comparator tương ứng; không chỉ cung cấp `TreeMap::new` cho loại khóa không so sánh được.
2. Comparator quyết định tính **tương đương khóa** trong sorted map: nếu `compare(a,b)==0`, `TreeMap` xem chúng là cùng khóa theo quy tắc Map. Tránh Comparator không phù hợp với `equals` nếu nó gây bất ngờ cho nghiệp vụ.
3. Duyệt theo thứ tự khóa là **khác** việc sắp xếp theo giá trị. Nếu cần sắp xếp theo số tiền hoặc theo nhiều trường, hãy tạo danh sách entry và sắp xếp bằng Comparator của entry.

## 6. Chương trình hoàn chỉnh: so sánh Map theo nguồn và Map theo khóa

Tạo tệp **`MapOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapOrderDemo {
    record Sale(String region, int cents) {}

    public static void main(String[] args) {
        var sales = List.of(
                new Sale("South", 10),
                new Sale("North", 20),
                new Sale("East", 30));

        var inputOrdered = sales.stream().collect(
                Collectors.toMap(
                        Sale::region,
                        Sale::cents,
                        (first, second) -> second,
                        LinkedHashMap::new));

        var byKey = sales.stream().collect(
                Collectors.toMap(
                        Sale::region,
                        Sale::cents,
                        (first, second) -> second,
                        TreeMap::new));

        var unspecified = sales.stream().collect(
                Collectors.toMap(Sale::region, Sale::cents));

        System.out.println("input-keys="
                + new ArrayList<>(inputOrdered.keySet()));
        System.out.println("input-values="
                + new ArrayList<>(inputOrdered.values()));
        System.out.println("sorted-keys="
                + new ArrayList<>(byKey.keySet()));
        System.out.println("default-size=" + unspecified.size());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 MapOrderDemo.java
java MapOrderDemo
```

Stdout:

```text
input-keys=[South, North, East]
input-values=[10, 20, 30]
sorted-keys=[East, North, South]
default-size=3
```

**Vì sao không in `unspecified.keySet()` làm expected output?** Nó không được Collector cam kết thứ tự, nên một bài kiểm thử có output cứng về thứ tự sẽ dễ gây hiểu nhầm. Ta chỉ kiểm tra số mapping bằng `size()` cho dạng Collector mặc định.

Từ chương trình:

- `sales` là List theo thứ tự `South, North, East`.
- `inputOrdered` dùng `LinkedHashMap` nên keySet/values/entrySet duyệt theo thứ tự chèn.
- `byKey` dùng `TreeMap` nên keySet duyệt theo thứ tự khóa `East, North, South`.
- `unspecified` là kết quả đúng về mapping, nhưng không có cam kết thứ tự từ overload `toMap` ngắn.
- `var` chỉ giúp suy luận kiểu kết quả; nó không tạo hay bảo đảm thứ tự. Với factory, kiểu cụ thể của biến có thể được suy ra là `LinkedHashMap<...>` hoặc `TreeMap<...>` theo chữ ký generic.

## 7. Khóa trùng, hàm merge và thứ tự chèn

Một nguồn thực tế thường có nhiều phần tử sinh cùng khóa. Overload `toMap(keyMapper, valueMapper)` **ném `IllegalStateException` nếu sinh khóa trùng**; nó không tự giữ phần tử đầu hoặc cuối.

Để xử lý trùng, cần `mergeFunction`. Nếu đồng thời cần thứ tự chèn khóa, dùng overload bốn tham số:

```java
var totals = sales.stream().collect(
        java.util.stream.Collectors.toMap(
                Sale::region,
                Sale::cents,
                Integer::sum,
                java.util.LinkedHashMap::new));
```

`Integer::sum` cộng các giá trị cùng khóa, không phụ thuộc việc phần tử được lặp lại bao nhiêu lần. Trong `LinkedHashMap` insertion-order, khóa giữ vị trí **lần xuất hiện đầu tiên**, kể cả khi giá trị của nó được cập nhật về sau.

Tạo tệp **`MergeOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;

public class MergeOrderDemo {
    record Sale(String region, int cents) {}

    public static void main(String[] args) {
        var sales = List.of(
                new Sale("South", 10),
                new Sale("North", 20),
                new Sale("South", 5),
                new Sale("East", 7));

        var totals = sales.stream().collect(
                Collectors.toMap(
                        Sale::region,
                        Sale::cents,
                        Integer::sum,
                        LinkedHashMap::new));

        System.out.println("keys="
                + new ArrayList<>(totals.keySet()));
        System.out.println("totals="
                + new ArrayList<>(totals.values()));
        System.out.println("south=" + totals.get("South"));
    }
}
```

Chạy:

```bash
javac --release 17 MergeOrderDemo.java
java MergeOrderDemo
```

Stdout:

```text
keys=[South, North, East]
totals=[15, 20, 7]
south=15
```

Phần tử `South` thứ hai chỉ làm giá trị của khóa `South` đổi từ 10 thành 15; khóa này **không chuyển ra cuối**, nên thứ tự vẫn `South, North, East`.

### 7.1. Thứ tự khóa và quy tắc gộp giá trị là hai quyết định riêng

Ví dụ với mã được lặp lại, bạn có thể muốn:

- Cộng tổng: `Integer::sum`.
- Giữ giá trị đầu: `(first, later) -> first`.
- Giữ giá trị cuối: `(first, later) -> later`.
- Báo lỗi trùng: không cung cấp merge function cho overload ngắn, hoặc validate rõ.

**Không dùng một merge function có side effect** (ghi biến ngoài, cập nhật List dùng chung, tăng bộ đếm không đồng bộ). Khi parallel stream, collector có thể gộp các phân vùng theo nhiều bước; merge function cần thỏa các yêu cầu về tính kết hợp theo hợp đồng reduction. Những phép tổng hợp nhạy thứ tự không thể tùy tiện chuyển sang parallel/unordered mà mong output như tuần tự.

### 7.2. Cảnh báo về `LinkedHashMap` access-order

`new LinkedHashMap<>()` mặc định dùng **insertion-order**. Nhưng constructor `LinkedHashMap(initialCapacity, loadFactor, true)` tạo Map **access-order**: chỉ đọc `get(key)` cũng có thể chuyển mapping được truy cập ra cuối thứ tự duyệt.

Vì vậy không suy rằng mọi `LinkedHashMap` luôn theo thứ tự chèn khi factory hoặc constructor được thay đổi. Với ví dụ `LinkedHashMap::new` ở trên, dùng đúng constructor mặc định nên thứ tự chèn ổn định khi không có thao tác tái sắp xếp đặc biệt.

## 8. `groupingBy`: thứ tự khóa nhóm không tự được đảm bảo

`Collectors.groupingBy(classifier)` phân loại phần tử thành Map từ khóa nhóm tới List phần tử, nhưng **không đảm bảo thứ tự khóa Map**. Nếu gọi:

```java
var byCity = people.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                Person::city));
```

thì ý nghĩa Map là đúng, còn thứ tự `byCity.keySet()` không được cam kết. Dù các Person trong List nguồn gặp lần lượt `HN, SG, HN, DN`, không được kỳ vọng thứ tự nhóm xuất ra phải là `HN, SG, DN`.

Muốn giữ thứ tự **lần xuất hiện đầu của mỗi nhóm**, dùng overload nhận `mapFactory`:

```java
var grouped = people.stream().collect(
        java.util.stream.Collectors.groupingBy(
                Person::city,
                java.util.LinkedHashMap::new,
                java.util.stream.Collectors.mapping(
                        Person::name,
                        java.util.stream.Collectors.toList())));
```

Chữ ký khái quát:

```java
public static <T,K,D,A,M extends Map<K,D>>
Collector<T,?,M> groupingBy(
        Function<? super T,? extends K> classifier,
        Supplier<M> mapFactory,
        Collector<? super T,A,D> downstream)
```

`mapFactory` kiểm soát loại Map chứa các **nhóm**. `downstream` quyết định nội dung từng nhóm (List tên, Set, tổng, đếm...). Hai thứ **không đồng nhất**: đổi downstream từ `toList()` sang `toSet()` không tự biến Map thành `LinkedHashMap` hay sắp xếp khóa nhóm.

## 9. Chương trình hoàn chỉnh: nhóm theo thứ tự gặp đầu tiên

Tạo **`GroupingOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;

public class GroupingOrderDemo {
    record Person(String name, String city) {}

    public static void main(String[] args) {
        var people = List.of(
                new Person("An", "HN"),
                new Person("Binh", "SG"),
                new Person("Chi", "HN"),
                new Person("Dung", "DN"));

        var grouped = people.stream().collect(
                Collectors.groupingBy(
                        Person::city,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList())));

        System.out.println("group-keys="
                + new ArrayList<>(grouped.keySet()));
        System.out.println("HN=" + grouped.get("HN"));
        System.out.println("SG=" + grouped.get("SG"));
        System.out.println("DN=" + grouped.get("DN"));
    }
}
```

Chạy:

```bash
javac --release 17 GroupingOrderDemo.java
java GroupingOrderDemo
```

Stdout:

```text
group-keys=[HN, SG, DN]
HN=[An, Chi]
SG=[Binh]
DN=[Dung]
```

Đọc kết quả ở hai tầng:

1. **Tầng Map:** nhóm `HN` xuất hiện đầu, sau đó `SG`, rồi `DN`. `LinkedHashMap::new` giữ thứ tự chèn nhóm trong pipeline tuần tự có encounter order.
2. **Tầng List trong mỗi nhóm:** `Collectors.mapping(Person::name, Collectors.toList())` lưu các tên thuộc nhóm. Với nguồn List tuần tự và ordered, `HN` có `[An, Chi]` theo thứ tự gặp.

Nếu cần khóa nhóm theo thứ tự chữ cái, đổi `LinkedHashMap::new` thành `TreeMap::new`. Khi đó thứ tự nhóm là `DN, HN, SG` (với String natural order), không còn theo lần gặp đầu tiên. Thứ tự phần tử *bên trong* mỗi nhóm là một quyết định riêng phụ thuộc downstream Collector và thứ tự đầu vào.

### 9.1. Grouping với sorted Map

```java
// Đoạn minh họa bên trong method:
var sortedGroups = people.stream().collect(
        Collectors.groupingBy(
                Person::city,
                java.util.TreeMap::new,
                Collectors.mapping(
                        Person::name,
                        Collectors.toList())));
```

`sortedGroups.keySet()` duyệt theo khóa nhóm có natural ordering. Nếu tên thành phố cần thứ tự tùy ý như `SG` trước `HN`, hãy cung cấp Comparator/logic thứ tự hợp lệ, không giả định `TreeMap` tự hiểu ưu tiên nghiệp vụ.

## 10. `keySet`, `values` và `entrySet` có cùng thứ tự nào?

Với một `LinkedHashMap` insertion-order có ba mapping:

```text
South -> 15
North -> 20
East  -> 7
```

ba view sẽ duyệt nhất quán theo thứ tự mapping của Map:

- `keySet()`: `South, North, East`.
- `values()`: `15, 20, 7` tương ứng các khóa ở trên.
- `entrySet()`: `South=15, North=20, East=7`.

Với `TreeMap`, cả ba view theo thứ tự **khóa đã sort**. Với Map không bảo đảm thứ tự, không suy diễn thứ tự của view từ tên `values` hay `entrySet`.

Nếu muốn in mapping một cách rõ ràng:

```java
for (var entry : totals.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

Khi `totals` là `LinkedHashMap` insertion-order từ ví dụ `MergeOrderDemo`, output của vòng lặp này có thứ tự khóa đã mô tả. Nếu cùng code nhận một `Map` bất kỳ từ API khác, không được coi thứ tự đó là cố định.

**Lưu ý về view:** `keySet()`, `values()`, `entrySet()` thường là view được hỗ trợ bởi Map. Không sửa Map cùng lúc đang duyệt (đặc biệt từ nhiều thread) mà không có thiết kế đồng bộ phù hợp; tránh làm code dựa vào hành vi fail-fast để đảm bảo tính đúng đắn.

## 11. Không cho sửa không đồng nghĩa giữ thứ tự: `toUnmodifiableMap` và `Map.copyOf`

`Collectors.toUnmodifiableMap(...)` (từ Java 10) tạo một Map **không hỗ trợ sửa** và từ chối khóa/giá trị `null`. Tuy nhiên, nó **không có hợp đồng giữ thứ tự duyệt của Stream đầu vào**.

```java
// Đoạn minh họa trong method:
var result = sales.stream().collect(
        java.util.stream.Collectors.toUnmodifiableMap(
                Sale::region,
                Sale::cents));
// Không dựa vào thứ tự result.keySet().
```

Nếu khóa trùng, overload hai tham số của `toUnmodifiableMap` báo `IllegalStateException`; overload có merge function xử lý trùng theo quy tắc bạn chọn. Cả hai đều không biến Map thành insertion-order.

Cùng nhóm lưu ý:

- `Map.of(...)` và `Map.ofEntries(...)` không hứa thứ tự duyệt theo thứ tự viết đối số.
- `Map.copyOf(orderedMap)` trả Map không cho sửa, nhưng **không bảo đảm giữ thứ tự duyệt của `orderedMap`**.
- Không khẳng định output String cụ thể của Map tạo bằng các factory này. Một số JDK có cơ chế thứ tự duyệt thay đổi giữa các lần chạy để làm lộ phụ thuộc sai vào thứ tự.

Khi hợp đồng yêu cầu **vừa không cho sửa vừa giữ thứ tự chèn**, hãy làm rõ cả hai yêu cầu.

### 11.1. Snapshot không cho sửa nhưng vẫn giữ thứ tự chèn

```java
var orderedMap = sales.stream().collect(
        java.util.stream.Collectors.toMap(
                Sale::region,
                Sale::cents,
                (first, second) -> second,
                java.util.LinkedHashMap::new));

var readonlySnapshot = java.util.Collections.unmodifiableMap(
        new java.util.LinkedHashMap<>(orderedMap));
```

`readonlySnapshot` là view không cho sửa của **một bản sao LinkedHashMap mới**. Nó giữ thứ tự mapping từ `orderedMap` ở thời điểm sao chép và không nhận thêm/xóa mapping khi `orderedMap` thay đổi về sau.

Phân biệt:

```java
var readonlyView = java.util.Collections.unmodifiableMap(orderedMap);
```

`readonlyView` **không sao chép** `orderedMap`; nó chỉ chặn sửa qua view và có thể phản ánh thay đổi ở Map nền. Khi cần kết quả độc lập về cấu trúc, bọc `new LinkedHashMap<>(orderedMap)` thay vì bọc trực tiếp nguồn mutable.

**Giới hạn:** Kể cả snapshot không cho sửa, các đối tượng khóa/giá trị bên trong có thể vẫn mutable. Với khóa mutable tham gia `equals/hashCode`, thay đổi trạng thái khóa có thể làm lookup không còn đáng tin. `unmodifiableMap` không phải deep copy hay cơ chế thread-safety tự động.

## 12. Chương trình hoàn chỉnh: snapshot và view

Tạo **`ReadonlyOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class ReadonlyOrderDemo {
    public static void main(String[] args) {
        var source = new LinkedHashMap<String, Integer>();
        source.put("B", 2);
        source.put("A", 1);

        var readonlySnapshot = Collections.unmodifiableMap(
                new LinkedHashMap<>(source));
        var readonlyView = Collections.unmodifiableMap(source);

        source.put("C", 3);

        System.out.println("snapshot="
                + new ArrayList<>(readonlySnapshot.keySet()));
        System.out.println("view="
                + new ArrayList<>(readonlyView.keySet()));

        try {
            readonlySnapshot.put("D", 4);
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot-write-blocked=true");
        }

        var copy = Map.copyOf(source);
        System.out.println("copy-size=" + copy.size());
    }
}
```

Chạy:

```bash
javac --release 17 ReadonlyOrderDemo.java
java ReadonlyOrderDemo
```

Stdout:

```text
snapshot=[B, A]
view=[B, A, C]
snapshot-write-blocked=true
copy-size=3
```

Tại sao chỉ in `copy.size()`? `Map.copyOf(source)` không cam kết thứ tự, nên bài học không “đóng đinh” output của `copy.keySet()`. Chương trình thể hiện rõ:

1. `source` là `LinkedHashMap` mutable có thứ tự chèn.
2. `readonlySnapshot` độc lập cấu trúc với các lần `put` sau đó ở `source`.
3. `readonlyView` bị chi phối bởi thay đổi của `source`, dù bản thân view không hỗ trợ `put`.
4. `Map.copyOf` tạo kết quả không cho sửa, nhưng không dùng làm phương pháp bắt buộc giữ thứ tự insertion-order.

## 13. Map có thứ tự khóa cho dữ liệu domain đặc biệt

Ngoài `LinkedHashMap` và `TreeMap`, đôi khi có loại Map thích hợp hơn:

- **`EnumMap`:** khóa là một enum; iteration theo thứ tự khai báo các hằng enum, không phụ thuộc thứ tự record đầu vào. Khi cần map enum trạng thái → số lượng, đây là lựa chọn hợp lệ và tiết kiệm chi phí.
- **`ConcurrentSkipListMap`:** cung cấp concurrent sorted map theo natural ordering/Comparator; có thể dùng làm mapFactory trong một số collector concurrent khi muốn khóa sắp xếp và cần concurrency phù hợp.
- **`LinkedHashMap` dạng access-order:** hữu ích trong một số cache LRU, nhưng thứ tự có thể đổi khi truy cập khóa. Không chọn dạng này nếu ứng dụng cần một bản ghi lịch sử theo lần xuất hiện đầu tiên.

Ví dụ `EnumMap` (đoạn minh họa trong một lớp):

```java
enum State { NEW, ACTIVE, CLOSED }

var counts = new java.util.EnumMap<State, Integer>(State.class);
counts.put(State.CLOSED, 2);
counts.put(State.NEW, 1);
counts.put(State.ACTIVE, 5);

// counts.keySet() duyệt: NEW, ACTIVE, CLOSED
```

Sắp xếp theo enum là hợp đồng `EnumMap`; không phải do `Collectors.groupingBy` tạo ra.

## 14. Stream song song, `unordered` và Collector concurrent

### 14.1. Thứ tự của Stream và thứ tự Map khác nhau ngay cả khi tuần tự

Trong `List.stream()` tuần tự, encounter order rõ. Tuy vậy, nếu dùng overload `toMap`/`groupingBy` không có mapFactory, **Map kết quả vẫn không có cam kết thứ tự**.

### 14.2. Khi dùng parallel, phải xét cả cách gộp các phân vùng

`parallelStream()` có thể chạy phép xử lý ở nhiều worker thread. Collector như `toMap` và `groupingBy` có thể tạo các Map trung gian rồi **merge**. Không được lấy thứ tự in ra trong một lần chạy làm hợp đồng cho tất cả các cấu hình, đặc biệt khi pipeline bị đánh dấu `unordered()`, nguồn vốn không có encounter order hoặc dùng Collector concurrent/unordered.

Khi thứ tự chèn gắn với **yêu cầu nghiệp vụ** và cần dự đoán chính xác:

1. Ưu tiên một nguồn có encounter order rõ, chẳng hạn `List` hoặc Stream đã sắp xếp.
2. Sử dụng pipeline **tuần tự** và mapFactory `LinkedHashMap::new` để mô tả thứ tự chèn khóa theo nguồn.
3. Hoặc chọn `TreeMap` nếu thực ra chỉ cần thứ tự theo khóa.
4. Hoặc sắp xếp thành một danh sách kết quả ở bước xuất dữ liệu.
5. Không dùng side effect ghi vào `LinkedHashMap` chung từ `parallel().forEach(...)`: vừa có rủi ro race condition, vừa không có thứ tự chèn đáng tin.
6. Nếu song song thực sự cần thiết, xem kỹ đặc tính `CONCURRENT`, `UNORDERED`, hợp đồng Collector và kiểm thử dữ liệu cụ thể; không tự kết luận chỉ vì gọi `parallel()` thì hiệu năng tốt hơn.

### 14.3. `groupingByConcurrent` và `toConcurrentMap`

Các collector `groupingByConcurrent` và `toConcurrentMap` được mô tả là **concurrent** và **unordered**. Vì vậy không dùng chúng để bảo đảm **thứ tự xuất hiện đầu của khóa**. Ngay cả khi nguồn là `List` có thứ tự, thứ tự tích lũy các phần tử trong danh sách thuộc mỗi nhóm cũng không mặc nhiên giống pipeline tuần tự.

```java
// Đoạn minh họa với biến people là List<Person>:
var groups = people.parallelStream()
        .collect(java.util.stream.Collectors.groupingByConcurrent(
                Person::city));
```

`groups` là ConcurrentMap chứa các nhóm, nhưng không có hợp đồng “khóa nhóm đầu là thành phố của phần tử đầu tiên”. Nếu yêu cầu là **thứ tự khóa được sắp xếp**, một concurrent sorted map phù hợp (ví dụ qua factory `ConcurrentSkipListMap::new`) có thể giải quyết tầng Map; tuy nhiên thứ tự phần tử trong mỗi nhóm vẫn phụ thuộc downstream collector và đặc tính pipeline.

## 15. Trường hợp `partitioningBy`: hai khóa không cần duyệt

`Collectors.partitioningBy(predicate)` tạo Map với hai khóa `Boolean.FALSE` và `Boolean.TRUE`, luôn có mapping cho cả hai (partition rỗng có List rỗng). Nhưng không có cam kết thứ tự của Map hoặc List implementation.

Nếu code cần xử lý nhóm đúng/sai, đọc **theo khóa**:

```java
// Đoạn minh họa trong một phương thức:
var partitions = people.stream()
        .collect(java.util.stream.Collectors.partitioningBy(
                person -> person.name().length() >= 4));

var longNames = partitions.get(true);
var shortNames = partitions.get(false);
```

Không viết một UI dựa vào `for (var group : partitions.entrySet())` rồi giả định luôn gặp `false` trước `true` hoặc ngược lại. Nếu thứ tự nhóm khi hiển thị là yêu cầu, tự tạo một danh sách thứ tự mong muốn như `List.of(false, true)` rồi truy cập `partitions.get(key)`.

## 16. Sắp xếp khi xuất thay vì ép mọi Map phải có thứ tự

Một Map có thể được thiết kế tối ưu cho lookup, còn yêu cầu sắp xếp chỉ xuất hiện khi tạo báo cáo. Khi đó có thể lấy entry từ Map rồi sort để xuất dữ liệu:

```java
// Giả sử anyMap là Map<String, Integer> có sẵn:
var sortedEntries = anyMap.entrySet().stream()
        .sorted(java.util.Map.Entry.comparingByKey())
        .toList();

for (var entry : sortedEntries) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

Khi khóa so sánh được, `comparingByKey()` cho thứ tự tăng theo khóa. Có thể cung cấp Comparator riêng nếu domain có thứ tự khác.

Nếu cần thứ tự **giảm dần theo giá trị**, hãy chọn phép so sánh tương ứng, kể cả tie-breaker theo khóa để output quyết định hoàn toàn:

```java
// Đoạn minh họa: anyMap có khóa String và giá trị Integer
var byValueThenKey = anyMap.entrySet().stream()
        .sorted(java.util.Comparator
                .<java.util.Map.Entry<String, Integer>, Integer>
                        comparing(java.util.Map.Entry::getValue)
                .reversed()
                .thenComparing(java.util.Map.Entry::getKey))
        .toList();
```

Đây là đoạn minh họa comparator với generic type chỉ rõ, không phải một chương trình độc lập. Việc sắp xếp entry **không thay đổi Map gốc**, mà tạo danh sách entry theo thứ tự yêu cầu. Nếu các giá trị hoặc khóa mutable được sửa đồng thời trong lúc xuất, vẫn phải quản lý nhất quán dữ liệu phù hợp.

**Không dùng Map.toString() làm dạng serialization có thứ tự bền vững.** Nếu hệ thống yêu cầu output JSON hay format wire ổn định, quy định thứ tự xuất rõ ràng và dùng serializer có hợp đồng tương ứng.

## 17. Null, duplicate và việc đặt điều kiện đúng chỗ

Thứ tự không phải rủi ro duy nhất của Map collector. Cần nhớ:

- `toMap(keyMapper, valueMapper)` sẽ ném `IllegalStateException` khi khóa trùng. Dùng merge function nếu trùng hợp lệ, hoặc validate nếu trùng là lỗi.
- `toUnmodifiableMap` không cho khóa/giá trị `null`, có thể ném `NullPointerException` khi mapper trả null.
- `groupingBy` không chấp nhận classifier sinh khóa `null` theo hợp đồng collector này trong các JDK hiện đại; hãy xử lý dữ liệu thiếu theo chính sách domain trước khi phân nhóm.
- Khi Map implementation là `TreeMap` với natural ordering, khóa phải có khả năng so sánh; đừng cung cấp loại khóa không phù hợp.
- Một khóa object có `equals`/`hashCode` phụ thuộc dữ liệu mutable có thể làm hỏng lookup nếu thay đổi sau khi đã đưa vào Map. `LinkedHashMap` và `TreeMap` cũng không tự bảo vệ dữ liệu mutable trong đối tượng khóa.
- Trước khi gọi `Map.copyOf`, phải bảo đảm Map không có `null` trong khóa/giá trị; việc tạo Map không cho sửa không làm sạch dữ liệu.

Đừng làm cho một ví dụ có thứ tự hoạt động bằng cách âm thầm loại khóa trùng hay bỏ bản ghi thiếu. **Chính sách xử lý dữ liệu** và **chính sách thứ tự hiển thị** phải được lựa chọn độc lập.

## 18. Nhầm lẫn phổ biến và cách chỉnh sửa

| Nhầm lẫn | Thực tế và cách sửa |
| --- | --- |
| “Stream đầu vào là List nên `toMap` giữ thứ tự.” | Overload mặc định không cam kết thứ tự Map; dùng `LinkedHashMap::new` khi cần |
| “`HashMap` thường in ra A, B, C nên đã được sắp xếp.” | Đó là quan sát tình cờ, không phải hợp đồng |
| “`groupingBy` giữ thứ tự các nhóm.” | Mặc định không đảm bảo; dùng mapFactory phù hợp |
| “`TreeMap` là bản sao thứ tự nguồn.” | `TreeMap` sắp xếp khóa, không theo lần xuất hiện đầu |
| “`LinkedHashMap` tự sort theo giá trị.” | Nó giữ thứ tự chèn khóa; muốn sort giá trị, sắp xếp entry riêng |
| “Nếu khóa trùng thì khóa được chuyển ra cuối.” | Với `LinkedHashMap` insertion-order, cập nhật giá trị không đổi vị trí khóa |
| “`toUnmodifiableMap` đã không cho sửa nên giữ thứ tự.” | Unmodifiable khác ordered; không có bảo đảm thứ tự |
| “`Map.copyOf(linkedHashMap)` sẽ giữ thứ tự linked map.” | Không có hợp đồng giữ thứ tự; dùng bản sao `LinkedHashMap` được bọc unmodifiable khi cần |
| “`Collections.unmodifiableMap(source)` là snapshot.” | Là view; thay đổi Map nền vẫn có thể phản ánh |
| “`groupingByConcurrent` vẫn giữ thứ tự List vì nguồn có order.” | Collector concurrent/unordered không cam kết encounter order |
| “`partitioningBy` chắc chắn in false rồi true.” | Không có cam kết duyệt theo thứ tự Boolean |
| “`Map.entrySet` tự có thứ tự độc lập với Map.” | View đi theo đặc tính duyệt của implementation Map |
| “Chỉ cần `var` thì type inference quyết định order.” | `var` chỉ suy luận kiểu, không tạo hợp đồng thứ tự |
| “Cứ đổi collector sang parallel là nhanh hơn.” | Map collector có chi phí merge; cần đo và xét thứ tự/concurrency |

## 19. Bài tập có đáp án

### Bài 1 — Đầu vào có thứ tự nhưng Map mặc định

```java
var words = java.util.List.of("C", "A", "B");
var map = words.stream().collect(
        java.util.stream.Collectors.toMap(
                s -> s, String::length));
```

Bạn có thể khẳng định `map.keySet()` duyệt `C, A, B` không?

**Đáp án:** **Không.** Nguồn List có encounter order, nhưng overload `toMap` này không hứa thứ tự của Map. Kiểu logic của kết quả là `Map<String,Integer>` gồm ba mapping, còn thứ tự duyệt không được hợp đồng bảo đảm.

### Bài 2 — Giữ thứ tự khóa xuất hiện đầu

Hãy sửa đoạn ở bài 1 để có keySet `[C, A, B]` trong xử lý tuần tự.

**Đáp án:**

```java
var map = words.stream().collect(
        java.util.stream.Collectors.toMap(
                s -> s,
                String::length,
                (oldValue, newValue) -> newValue,
                java.util.LinkedHashMap::new));
```

Chọn `LinkedHashMap` insertion-order bằng mapFactory. Merge function chỉ có hiệu lực khi có khóa trùng.

### Bài 3 — Thứ tự theo khóa

Làm sao để `[C, A, B]` được duyệt thành `[A, B, C]`?

**Đáp án:** chọn `TreeMap::new` làm mapFactory nếu khóa so sánh được, hoặc sắp xếp `entrySet()`/`keySet()` khi xuất.

### Bài 4 — Khóa trùng có chuyển vị trí?

Nguồn: `South=10`, `North=20`, `South=5`. Collector dùng `Integer::sum` và `LinkedHashMap::new`. Kết quả?

**Đáp án:** Map có khóa thứ tự `[South, North]`, giá trị `South=15`, `North=20`. Lần gặp `South` thứ hai cập nhật giá trị, không đẩy khóa ra cuối.

### Bài 5 — `groupingBy` và thứ tự nhóm

Với nguồn người ở thành phố `HN, SG, HN, DN`, vì sao `groupingBy(Person::city)` không đảm bảo thứ tự nhóm `HN, SG, DN`?

**Đáp án:** Collector không cam kết implementation/thứ tự Map. Dùng `groupingBy(Person::city, LinkedHashMap::new, toList())` khi cần các nhóm ở thứ tự lần gặp đầu (trên pipeline tuần tự có order), hoặc `TreeMap::new` để sắp xếp khóa.

### Bài 6 — Map không cho sửa

```java
var ordered = new java.util.LinkedHashMap<String, Integer>();
ordered.put("B", 2);
ordered.put("A", 1);
var result = java.util.Map.copyOf(ordered);
```

`result` có chắc chắn duyệt `B, A` không?

**Đáp án:** Không. `Map.copyOf` không hứa giữ thứ tự nguồn. Nếu cần bản sao không sửa giữ insertion-order, dùng `Collections.unmodifiableMap(new LinkedHashMap<>(ordered))`.

### Bài 7 — View và snapshot

Sau khi tạo `view = Collections.unmodifiableMap(original)` và `snapshot = Collections.unmodifiableMap(new LinkedHashMap<>(original))`, code thêm khóa vào `original`. Dữ liệu nào có thể đổi?

**Đáp án:** `view` phản ánh thay đổi ở Map nền; `snapshot` không đổi cấu trúc do được sao chép trước đó. Cả hai không cho sửa qua API của chính chúng.

### Bài 8 — Concurrent Map

Vì sao không nên dùng `groupingByConcurrent(...)` để tạo báo cáo yêu cầu thứ tự nhóm xuất hiện đầu?

**Đáp án:** Đây là collector concurrent và unordered, không cam kết encounter order. Dùng pipeline tuần tự với mapFactory giữ insertion-order, hoặc sort kết quả theo yêu cầu.

### Bài 9 — Kiểm thử đúng hợp đồng

Bạn muốn assert một Map chứa đúng mapping `A -> 1, B -> 2`, nhưng thứ tự không quan trọng. Có nên assert chuỗi `"{A=1, B=2}"` không?

**Đáp án:** Không. So sánh theo mapping, chẳng hạn `Map.of("A", 1, "B", 2).equals(actual)`. Chỉ kiểm tra `new ArrayList<>(map.keySet())` nếu thứ tự là một phần hợp đồng đã thiết kế với Map implementation phù hợp.

## 20. Quy trình kiểm tra khi thiết kế collector Map

Trước khi chốt code, hãy hỏi:

1. **Thứ tự là yêu cầu nghiệp vụ hay chỉ là cách trình bày?** Nếu chỉ cần lúc xuất, có thể sort entry ngay tại ranh giới output.
2. **Cần theo lần xuất hiện đầu hay theo khóa đã sort?** Chọn `LinkedHashMap` hoặc `TreeMap` tương ứng.
3. **Nguồn Stream có encounter order thật không?** List có, còn nhiều nguồn khác có thể không; pipeline `unordered()` có thể bỏ order.
4. **Collector nào đang dùng?** `toMap`, `groupingBy`, `partitioningBy`, `toUnmodifiableMap` hay concurrent collector có hợp đồng khác nhau.
5. **Có overload `mapFactory` không?** Chọn overload chính xác để quy định loại Map.
6. **Có khóa trùng không?** Chọn merge function đúng nghiệp vụ; đừng để kết quả tùy quy tắc chưa nêu.
7. **Có cần Map không cho sửa?** Phân biệt view với snapshot và tính mutable của object khóa/giá trị.
8. **Có chạy song song không?** Không dựa vào side effect hoặc thứ tự luồng; xem đặc tính unordered/concurrent.
9. **Có Map/Set factory không bảo đảm order được dùng về sau?** `Map.copyOf` hoặc `toUnmodifiableMap` có thể làm mất bảo đảm iteration order mong muốn.
10. **Kiểm thử có assert đúng tầng không?** So sánh mapping nếu thứ tự không quan trọng; so sánh danh sách khóa/entry khi thứ tự được hứa bởi hợp đồng.
11. **Điều gì xảy ra khi giá trị/khóa bị sửa?** Mutable key có thể ảnh hưởng lookup; Map không cho sửa không đồng nghĩa phần tử bất biến.
12. **Người đọc có biết rõ mục đích thứ tự không?** Tên như `ordersByFirstSeenRegion` hoặc chú thích ngắn có thể giúp hiểu vì sao dùng `LinkedHashMap::new` thay vì collector ngắn.

**Tóm tắt:** Collector tạo `Map` không tự bảo đảm thứ tự duyệt chỉ vì nguồn có encounter order. `Collectors.toMap` và `groupingBy` mặc định không cam kết thứ tự của Map kết quả; khi cần thứ tự, hãy chọn `LinkedHashMap::new` để giữ thứ tự chèn khóa trên pipeline tuần tự hoặc `TreeMap::new` để sắp xếp khóa. `Map.copyOf` và `toUnmodifiableMap` làm Map không cho sửa nhưng không bảo đảm iteration order. Phân biệt thứ tự phần tử đầu vào, thứ tự khóa của Map và thứ tự giá trị bên trong từng nhóm giúp viết code rõ hợp đồng, dễ kiểm thử và không phụ thuộc hành vi tình cờ của JDK.