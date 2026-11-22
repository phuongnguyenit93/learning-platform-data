# Collectors.partitioningBy(): chia dữ liệu theo Predicate trong Java

Khi cần chia một tập phần tử thành **hai nhóm dựa trên điều kiện đúng/sai**, Java Stream API cung cấp collector **`Collectors.partitioningBy()`** trong gói `java.util.stream`. Thay vì viết hai vòng lặp, tự tạo hai danh sách rồi kiểm tra từng phần tử, bạn có thể mô tả một **`Predicate<T>`** và để collector thu thập kết quả thành `Map<Boolean, ...>`.

Ví dụ: phân loại số chẵn và lẻ, học sinh đạt/chưa đạt, đơn hàng vượt/ngưỡng chưa vượt, sản phẩm còn/hết hàng, hay bản ghi hợp lệ/chưa hợp lệ. Với mỗi phần tử, predicate xác định nhánh:

- **`true`**: phần tử thỏa điều kiện.
- **`false`**: phần tử không thỏa điều kiện.

Khác với nhiều phép grouping theo một khóa tùy ý, `partitioningBy` luôn mô tả **đúng hai phân vùng Boolean**, kể cả khi một phân vùng không có phần tử. Hãy chú ý **sự khác nhau giữa điều kiện phân loại và thao tác tổng hợp trong mỗi phân vùng**: downstream collector cho phép đếm, lấy tên, tính tổng, thống kê, hoặc nhóm sâu hơn thay vì chỉ tạo hai danh sách.

Sau bài học, bạn sẽ:
1. Viết đúng `partitioningBy(predicate)` và `partitioningBy(predicate, downstream)`.
2. Hiểu kết quả `Map<Boolean,List<T>>` và `Map<Boolean,D>`, kể cả dữ liệu rỗng.
3. Sử dụng `Predicate<T>` rõ ràng, xử lý null và điều kiện biên đúng.
4. Kết hợp `counting`, `mapping`, `summingInt`, `averagingInt`, `summarizingInt`, `groupingBy`.
5. So sánh với `filter`, `groupingBy`, `toMap` và lựa chọn theo nhu cầu.
6. Tránh shared mutable state, giả định sai về thứ tự `Map`, và lỗi khi xử lý song song.

Các chương trình hoàn chỉnh dùng **JDK 17+**; lệnh biên dịch/chạy và stdout đã được chọn sao cho không phụ thuộc thứ tự duyệt HashMap hoặc lịch trình thread.

## 1. Cú pháp và kiểu kết quả

Có hai overload chính trên `Collectors`:

```java
static <T> Collector<T, ?, Map<Boolean, List<T>>>
partitioningBy(Predicate<? super T> predicate)

static <T, D, A> Collector<T, ?, Map<Boolean, D>>
partitioningBy(
    Predicate<? super T> predicate,
    Collector<? super T, A, D> downstream
)
```

Đây là **chữ ký API rút gọn để học**, không phải hai method tự khai báo trong chương trình. Với một đối số, downstream mặc định thu thập các phần tử thành danh sách. Với hai đối số, downstream quyết định loại kết quả `D` của **mỗi phân vùng**.

Ví dụ mảnh mã trong phương thức (cần import `java.util.List`, `java.util.Map` và `java.util.stream.Collectors`):

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);
Map<Boolean, List<Integer>> byEven = numbers.stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

List<Integer> evens = byEven.get(true);  // [2, 4]
List<Integer> odds  = byEven.get(false); // [1, 3, 5]
```

Chú ý `n -> n % 2 == 0` là **predicate**, không phải phương thức tạo list. Predicate được dùng để phân loại phần tử vào nhánh đúng/sai; collector nhận trách nhiệm tích lũy các phần tử.

### Vì sao có Map<Boolean, ...>?

`Map<Boolean,List<Integer>>` có hai key `Boolean.TRUE` và `Boolean.FALSE`. Caller đọc từng nhánh bằng `get(true)` hoặc `get(false)`. Java tự boxing literal boolean `true`/`false` khi cần.

Nếu chỉ muốn danh sách những phần tử **đạt điều kiện** và không quan tâm nhóm còn lại, `filter(predicate).toList()` thường đơn giản hơn. `partitioningBy` có ý nghĩa khi **cần cả hai nhánh** hoặc cần thống kê cả nhánh đúng lẫn nhánh sai trong một lần thu thập.

## 2. Hai nhánh luôn có mặt, kể cả khi rỗng

Một tính chất quan trọng: kết quả của `partitioningBy` **luôn chứa cả hai khóa `true` và `false`**. Điều đó không có nghĩa cả hai danh sách đều có phần tử.

```java
Map<Boolean, List<Integer>> onlyOdd = List.of(1, 3, 5)
        .stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

// onlyOdd.get(true)  -> []
// onlyOdd.get(false) -> [1, 3, 5]
```

Với nguồn rỗng:

```java
Map<Boolean, List<String>> empty = List.<String>of()
        .stream()
        .collect(Collectors.partitioningBy(s -> s.length() > 3));

// empty.get(true)  -> []
// empty.get(false) -> []
// empty.size()     -> 2
```

Hai ví dụ trên là **mảnh code độc lập**; `List.<String>of()` chỉ rõ generic type cho nguồn rỗng. Mặc dù Stream không có phần tử để kiểm tra, collector vẫn tạo hai phân vùng với kết quả downstream thích hợp.

Khác với `groupingBy(x -> condition)`, phép nhóm thông thường có thể **không tạo khóa** cho nhóm không xuất hiện. Ví dụ nếu mọi số đều lẻ, `groupingBy(n -> n % 2 == 0)` có thể chỉ chứa key `false`; `partitioningBy` bảo đảm có cả `true` với danh sách rỗng.

**Không phụ thuộc vào thứ tự iteration của Map.** API không hứa `true` hoặc `false` sẽ được in trước khi gọi `System.out.println(result)`. Nếu muốn stdout hoặc UI ổn định, in từng giá trị `result.get(true)` và `result.get(false)` với nhãn tương ứng.

## 3. Chương trình Java 17: phân vùng số và dữ liệu rỗng

Lưu tệp **`PartitionBasicsDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PartitionBasicsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);
        Predicate<Integer> isEven = n -> n % 2 == 0;

        Map<Boolean, List<Integer>> groups = numbers.stream()
                .collect(Collectors.partitioningBy(isEven));

        Map<Boolean, List<Integer>> onlyOdds = List.of(1, 3, 5)
                .stream()
                .collect(Collectors.partitioningBy(isEven));

        Map<Boolean, List<Integer>> empty = List.<Integer>of()
                .stream()
                .collect(Collectors.partitioningBy(isEven));

        System.out.println("even=" + groups.get(true));
        System.out.println("odd=" + groups.get(false));
        System.out.println("keys=" + groups.size());
        System.out.println("onlyOddsTrue=" + onlyOdds.get(true));
        System.out.println("onlyOddsFalse=" + onlyOdds.get(false));
        System.out.println("emptyTrue=" + empty.get(true));
        System.out.println("emptyFalse=" + empty.get(false));
        System.out.println("emptyKeys=" + empty.size());
    }
}
```

Biên dịch/chạy trong thư mục chứa file:

```bash
javac -encoding UTF-8 PartitionBasicsDemo.java
java PartitionBasicsDemo
```

**Stdout chính xác:**

```text
even=[2, 4, 6]
odd=[1, 3, 5]
keys=2
onlyOddsTrue=[]
onlyOddsFalse=[1, 3, 5]
emptyTrue=[]
emptyFalse=[]
emptyKeys=2
```

Giải thích:
- `isEven` thỏa đúng với 2, 4, 6.
- Số lẻ được đưa vào nhánh `false`.
- Cả `onlyOdds` và `empty` đều có hai key, dù danh sách nhánh đúng rỗng.
- Danh sách từ nguồn có encounter order được thu thập theo thứ tự gặp; ví dụ không phụ thuộc thứ tự của Map.

Trong API nghiệp vụ, nên đặt tên predicate đúng với nhánh `true`, ví dụ `isPassing`, `isActive`, `requiresReview`. Với tên mơ hồ như `check`, người đọc dễ nhầm hai nhánh.

## 4. Predicate<T> quyết định ngữ nghĩa phân vùng

`partitioningBy` nhận một `Predicate<? super T>`. Functional method của `Predicate<T>` là:

```java
boolean test(T value);
```

Đây là **chữ ký minh họa**. Điều kiện phải trả boolean, ví dụ:

```java
Predicate<String> longName = name -> name.length() >= 5;
Predicate<Integer> positive = n -> n > 0;
Predicate<String> containsJava = text -> text.contains("Java");
```

Đoạn minh họa yêu cầu `import java.util.function.Predicate;`. Một predicate có thể kết hợp bằng `and`, `or`, `negate`:

```java
Predicate<Integer> positiveEven = positive.and(n -> n % 2 == 0);
Map<Boolean, List<Integer>> grouped = List.of(-2, 0, 2, 3, 4)
        .stream()
        .collect(Collectors.partitioningBy(positiveEven));

// true  -> [2, 4]
// false -> [-2, 0, 3]
```

Đây là mảnh code dùng cùng biến `positive` ở mảnh trên.

### Ranh giới điều kiện rất quan trọng

Ví dụ học sinh “đạt” khi điểm **từ 70 trở lên**:

```java
Predicate<Student> passing = student -> student.score() >= 70;
```

Khi điểm là 70, predicate trả `true`; nếu vô tình dùng `> 70`, điểm 70 bị đưa vào nhánh `false`. Đây là lỗi nghiệp vụ thường gặp nhưng vẫn biên dịch hợp lệ.

### Xử lý null có chủ đích

Nếu nguồn chứa null, viết `s -> s.length() > 3` sẽ ném `NullPointerException` khi gặp null. Chọn một chính sách rõ ràng:

```java
Predicate<String> longNonNull = s -> s != null && s.length() > 3;
```

Khi đó null đi vào nhánh false. Nếu null là dữ liệu không hợp lệ và không nên nằm trong nhóm “không đạt”, hãy `filter(Objects::nonNull)` trước khi phân vùng hoặc trả lỗi xác thực riêng. Đừng tự động biến dữ liệu hỏng thành nhánh false mà không hiểu yêu cầu.

Tương tự, nếu predicate có side effect, thứ tự và số lần gọi có thể trở thành mối quan tâm; nên ưu tiên hàm **stateless** và **non-interfering**, đặc biệt khi pipeline chạy song song.

## 5. Overload có downstream collector

Hình thức thứ hai:

```java
Collectors.partitioningBy(predicate, downstreamCollector)
```

cho phép **tổng hợp riêng từng phân vùng**. Thay vì hai `List<T>`, bạn có thể nhận hai kết quả đếm, tổng, trung bình, tập khóa, thống kê hoặc map con.

| Downstream | Kiểu kết quả toàn cục | Ý nghĩa |
| --- | --- | --- |
| `Collectors.counting()` | `Map<Boolean,Long>` | Số phần tử mỗi nhánh |
| `Collectors.mapping(f, toList())` | `Map<Boolean,List<R>>` | Chuyển mỗi phần tử rồi thu thập |
| `Collectors.summingInt(f)` | `Map<Boolean,Integer>` | Tổng thuộc tính int mỗi nhánh |
| `Collectors.averagingInt(f)` | `Map<Boolean,Double>` | Trung bình thuộc tính int |
| `Collectors.summarizingInt(f)` | `Map<Boolean,IntSummaryStatistics>` | Count, sum, min, max, average |
| `Collectors.toSet()` | `Map<Boolean,Set<T>>` | Loại trùng theo equals/hashCode |
| `Collectors.groupingBy(f)` | `Map<Boolean,Map<K,List<T>>>` | Chia hai nhánh, rồi nhóm theo khóa khác |

Ví dụ:

```java
Map<Boolean, Long> counts = List.of(1, 2, 3, 4, 5)
        .stream()
        .collect(Collectors.partitioningBy(
                n -> n % 2 == 0,
                Collectors.counting()
        ));

// counts.get(true)  -> 2
// counts.get(false) -> 3
```

Đây là mảnh mã cần import `List`, `Map`, `Collectors`. Lợi ích: không cần giữ cả hai danh sách nếu mục tiêu cuối cùng chỉ là **đếm**.

**Một lưu ý quan trọng về downstream:** `partitioningBy` bảo đảm hai key, nhưng kiểu giá trị của nhóm rỗng phụ thuộc **downstream**. Với `counting()`, nhóm rỗng nhận `0L`; với `toList()`, nhận danh sách rỗng; với `maxBy(...)`, nhận `Optional.empty()`; với `averagingInt(...)`, nhóm rỗng nhận `0.0` theo hợp đồng collector. Nếu cần phân biệt “không có mẫu” với “trung bình bằng 0”, phải xem thêm `counting` hoặc một kết quả có trạng thái thích hợp.

## 6. Chương trình Java 17: đếm, lấy tên, tính trung bình và thống kê

Tạo file **`PartitionDownstreamDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PartitionDownstreamDemo {
    record Student(String name, int score) {}

    public static void main(String[] args) {
        List<Student> students = List.of(
                new Student("Lan", 85),
                new Student("Minh", 62),
                new Student("Mai", 92),
                new Student("An", 59)
        );
        Predicate<Student> passing = s -> s.score() >= 70;

        Map<Boolean, Long> counts = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.counting()));

        Map<Boolean, List<String>> names = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.mapping(Student::name, Collectors.toList())));

        Map<Boolean, Double> averages = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.averagingInt(Student::score)));

        Map<Boolean, IntSummaryStatistics> statistics = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.summarizingInt(Student::score)));

        System.out.println("passedCount=" + counts.get(true));
        System.out.println("failedCount=" + counts.get(false));
        System.out.println("passedNames=" + names.get(true));
        System.out.println("failedNames=" + names.get(false));
        System.out.println("passedAverage=" + averages.get(true));
        System.out.println("failedAverage=" + averages.get(false));
        System.out.println("passedTotal=" + statistics.get(true).getSum());
        System.out.println("failedMin=" + statistics.get(false).getMin());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PartitionDownstreamDemo.java
java PartitionDownstreamDemo
```

**Stdout chính xác:**

```text
passedCount=2
failedCount=2
passedNames=[Lan, Mai]
failedNames=[Minh, An]
passedAverage=88.5
failedAverage=60.5
passedTotal=177
failedMin=59
```

Chi tiết:
- `score >= 70` đúng với Lan (85) và Mai (92): tổng 177, trung bình 88.5.
- Minh (62) và An (59) ở nhánh false: trung bình 60.5, min 59.
- `mapping(Student::name, toList())` chỉ thu tên, không giữ toàn bộ `Student`.
- Mỗi `collect` tiêu thụ **một Stream mới** tạo từ `students.stream()`. Không tái dùng một Stream đã kết thúc.
- `record Student` cung cấp accessor `name()`, `score()` và giúp ví dụ ngắn gọn trong Java 17.

Khi cần nhiều chỉ số và dữ liệu lớn, `summarizingInt` cho count, sum, min, max, average trong **một lượt thu thập**; ví dụ phân tách các pipeline để làm rõ từng downstream chứ không nhất thiết là lựa chọn hiệu năng tối ưu.

## 7. partitioningBy khác groupingBy như thế nào?

Cả hai đều là collectors, nhưng có mục tiêu khác nhau:

| Tiêu chí | `partitioningBy(predicate)` | `groupingBy(classifier)` |
| --- | --- | --- |
| Đầu vào cho tiêu chí | `Predicate<T>` trả boolean | `Function<T,K>` trả khóa `K` |
| Số nhóm | Hai phân vùng `true` và `false` | Tùy số khóa khác nhau |
| Kiểu kết quả thông dụng | `Map<Boolean,List<T>>` | `Map<K,List<T>>` |
| Nhóm không có phần tử | Vẫn có hai key Boolean | Không buộc tạo key chưa xuất hiện |
| Phù hợp nhất | Đạt/không đạt, hợp lệ/không, có/không | Nhóm theo loại, phòng ban, khu vực, năm |
| Downstream | Có | Có |

Ví dụ chia theo điểm đạt/không đạt:

```java
Collectors.partitioningBy(student -> student.score() >= 70)
```

Ví dụ nhóm theo mức xếp loại ba bậc:

```java
Collectors.groupingBy(student ->
        student.score() >= 85 ? "A" :
        student.score() >= 70 ? "B" : "C")
```

Hai đoạn là **biểu thức collector minh họa** trong ngữ cảnh Stream có kiểu phần tử `Student` với accessor `score()`. Nhóm ba nhãn A/B/C là bài toán của `groupingBy`, không phải của `partitioningBy`.

### Trường hợp cùng một điều kiện Boolean

Về dữ liệu có mặt, `groupingBy(s -> condition)` có thể tạo các nhóm tương tự, nhưng **không cùng hợp đồng hai key**. Nếu nghiệp vụ luôn cần hiển thị “Đạt: 0” và “Chưa đạt: n” ngay cả khi không có người đạt, `partitioningBy` diễn tả ý định chính xác hơn.

### Nếu chỉ cần một nhánh

```java
List<Integer> even = List.of(1, 2, 3, 4)
        .stream()
        .filter(n -> n % 2 == 0)
        .toList();
```

Đoạn này minh họa `filter`. Không cần phân vùng toàn bộ rồi gọi `get(true)` nếu nhóm false không bao giờ được sử dụng. `filter` cũng có thể làm giảm chi phí lưu trữ khi chỉ cần một phía.

## 8. Lồng partitioningBy và groupingBy cho dữ liệu nghiệp vụ

Bạn có thể chia đơn hàng theo điều kiện doanh số trước, sau đó nhóm từng nhánh theo khu vực. Chỉ nên làm vậy khi cần cả hai trục phân tích.

Ví dụ: đơn hàng `total >= 100` là giá trị cao, và trong mỗi nhánh cần đếm theo `region`.

Lưu thành **`PartitionNestedGroupingDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PartitionNestedGroupingDemo {
    record Order(String id, String region, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", "North", 120),
                new Order("B", "South", 80),
                new Order("C", "North", 45),
                new Order("D", "South", 160),
                new Order("E", "North", 200)
        );
        Predicate<Order> highValue = order -> order.total() >= 100;

        Map<Boolean, Map<String, Long>> regionCounts = orders.stream()
                .collect(Collectors.partitioningBy(
                        highValue,
                        Collectors.groupingBy(
                                Order::region,
                                TreeMap::new,
                                Collectors.counting())));

        Map<Boolean, Integer> totals = orders.stream()
                .collect(Collectors.partitioningBy(
                        highValue,
                        Collectors.summingInt(Order::total)));

        System.out.println("highRegions=" + regionCounts.get(true));
        System.out.println("lowRegions=" + regionCounts.get(false));
        System.out.println("highSum=" + totals.get(true));
        System.out.println("lowSum=" + totals.get(false));
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 PartitionNestedGroupingDemo.java
java PartitionNestedGroupingDemo
```

**Stdout chính xác:**

```text
highRegions={North=2, South=1}
lowRegions={North=1, South=1}
highSum=480
lowSum=125
```

Giải thích:
1. Nhánh true gồm A/North/120, D/South/160, E/North/200. Nhóm theo khu vực tạo `North=2`, `South=1`; tổng là 480.
2. Nhánh false gồm B/South/80 và C/North/45, nên mỗi khu vực có một đơn; tổng là 125.
3. `TreeMap::new` trong downstream `groupingBy` bảo đảm thứ tự khóa khu vực khi in Map con.
4. Mỗi phân vùng có thể có một Map con rỗng khi không có đơn hàng thuộc phân vùng đó; key true/false của Map ngoài vẫn tồn tại.

Nếu yêu cầu là “tổng doanh số theo khu vực rồi chia khu vực thành đạt/chưa đạt ngưỡng”, **thứ tự phân tích phải khác**: trước hết group/sum theo region, sau đó xét điều kiện trên tổng từng region. `partitioningBy` trên từng Order không tự biến thành partitioning theo tổng của nhóm.

## 9. partitioningBy với Set, min/max và phân vùng rỗng

Downstream có thể dùng collector khác ngoài `toList`. Ví dụ:

```java
Map<Boolean, java.util.Set<Integer>> uniqueByEven =
        List.of(2, 2, 3, 3, 4)
                .stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0,
                        Collectors.toSet()));
```

Đây là mảnh mã minh họa cần `List`, `Map`, `Collectors`. Nhánh true chứa tập 2, 4; nhánh false chứa tập 3. **Không dựa vào thứ tự in của `Set`** từ `toSet()`.

Nếu muốn giá trị lớn nhất trong từng phân vùng:

```java
Map<Boolean, java.util.Optional<Integer>> maximum =
        List.of(1, 2, 3, 5)
                .stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0,
                        Collectors.maxBy(Integer::compare)));
```

`maximum.get(true)` chứa 2 và `maximum.get(false)` chứa 5. Kết quả downstream `maxBy` là `Optional<Integer>`, không phải `Integer` trực tiếp. Nếu một nhánh rỗng, Optional tương ứng **rỗng**, nhưng key Boolean của phân vùng vẫn có mặt.

**Không gọi `get()` trên Optional rỗng.** Dùng `orElse`, `orElseThrow` hoặc kiểm tra trạng thái. Phân biệt hai tầng “nhánh có tồn tại không?” và “nhánh có phần tử để tính max không?”: `partitioningBy` bảo đảm tầng thứ nhất, không bảo đảm tầng thứ hai.

### Kết quả downstream có cần mutable không?

`Collectors.toList()` không cam kết implementation cụ thể hoặc khả năng sửa. `Collectors.toUnmodifiableList()` trả danh sách không sửa được qua API và từ chối phần tử null. Nếu cần container cụ thể, dùng `Collectors.toCollection(ArrayList::new)`; nếu chỉ cần đọc kết quả, đừng giả định hai danh sách có thể sửa tự do hoặc thuộc class cụ thể.

## 10. Chạy song song: dùng collector, không dùng danh sách chung bên ngoài

Với `parallelStream()`, collector có thể chia phần việc thành nhiều accumulator và gộp kết quả. Cách dùng:

```java
Map<Boolean, List<Integer>> groups = List.of(1, 2, 3, 4)
        .parallelStream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));
```

Đoạn minh họa này phù hợp về mặt ngữ nghĩa. `partitioningBy` kết hợp với collector chuẩn giúp Stream framework quản lý quá trình thu thập, không cần tự cập nhật hai danh sách chia sẻ trên nhiều thread.

**Không nên** viết:

```java
// MẪU KHÔNG AN TOÀN với parallelStream():
List<Integer> yes = new java.util.ArrayList<>();
List<Integer> no = new java.util.ArrayList<>();
List.of(1, 2, 3, 4)
        .parallelStream()
        .forEach(n -> {
            if (n % 2 == 0) yes.add(n);
            else no.add(n);
        });
```

Đây là mảnh mã **cố ý cảnh báo**. Hai `ArrayList` không an toàn cho nhiều thread đồng thời cập nhật, dẫn đến race condition, kết quả thiếu hoặc thứ tự không ổn định. Dùng collector là lựa chọn phù hợp hơn.

**Predicate nên stateless, non-interfering**: không sửa nguồn đang duyệt, không phụ thuộc vào bộ đếm mutable tăng dần hoặc thứ tự thực thi. Nếu predicate có side effect, kết quả trên parallel stream khó kiểm tra; không dùng `partitioningBy` như giải pháp tự động đồng bộ.

### Encounter order của danh sách trong phân vùng

Với nguồn ordered như `List` và downstream phù hợp như `toList()`, các phần tử ở từng phân vùng được thu theo **encounter order**. Trong parallel stream, thứ tự thực thi giữa các worker có thể khác nhưng kết quả List vẫn theo hợp đồng thứ tự này. Bản thân **thứ tự duyệt hai key của Map** không được bảo đảm.

## 11. Chương trình Java 17: parallel partitioning vẫn có đầu ra xác định

Lưu thành **`ParallelPartitionDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelPartitionDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 12)
                .boxed()
                .toList();

        Map<Boolean, List<Integer>> divisibleByThree =
                numbers.parallelStream()
                        .collect(Collectors.partitioningBy(
                                n -> n % 3 == 0));

        Map<Boolean, Long> counts = numbers.parallelStream()
                .collect(Collectors.partitioningBy(
                        n -> n % 3 == 0,
                        Collectors.counting()));

        Map<Boolean, Optional<Integer>> maximum = numbers.parallelStream()
                .collect(Collectors.partitioningBy(
                        n -> n % 3 == 0,
                        Collectors.maxBy(Integer::compare)));

        System.out.println("divisible=" + divisibleByThree.get(true));
        System.out.println("other=" + divisibleByThree.get(false));
        System.out.println("divisibleCount=" + counts.get(true));
        System.out.println("otherCount=" + counts.get(false));
        System.out.println("divisibleMax=" + maximum.get(true).orElse(-1));
        System.out.println("otherMax=" + maximum.get(false).orElse(-1));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ParallelPartitionDemo.java
java ParallelPartitionDemo
```

**Stdout chính xác:**

```text
divisible=[3, 6, 9, 12]
other=[1, 2, 4, 5, 7, 8, 10, 11]
divisibleCount=4
otherCount=8
divisibleMax=12
otherMax=11
```

Các giá trị 3, 6, 9, 12 chia hết cho 3. Kết quả danh sách giữ encounter order của nguồn `IntStream.rangeClosed(...).boxed().toList()`. Các số còn lại gồm tám phần tử; max của nhánh đó là 11.

Chương trình không in trực tiếp object `Map`, nên không phụ thuộc thứ tự key true/false. Cũng không in thread ID hay log từ `forEach`, vì những chi tiết ấy không có stdout cố định khi chạy song song.

**Hiệu năng:** với 12 số, parallel stream gần như chắc chắn không phải một ví dụ chứng minh tăng tốc. Nếu dataset lớn và phép tính đủ nặng, parallel có thể hữu ích; còn overhead chia việc, gộp kết quả và giữ encounter order có thể khiến nó chậm hơn. Hãy benchmark workload thật, không suy luận từ tên `parallel`.

## 12. Những lỗi dễ mắc khi phân vùng

1. **Đảo ngược ý nghĩa key:** `get(true)` là nhóm **thỏa predicate**, không mặc định là “đạt” nếu predicate được viết theo “bị lỗi”.
2. **Nhầm dấu so sánh:** `>= 70` khác `> 70` khi điểm đúng bằng 70.
3. **Chỉ muốn nhóm true nhưng dùng partitioningBy phức tạp:** dùng `filter` nếu không cần nhóm false.
4. **Cho rằng Map chỉ có key đã xuất hiện:** `partitioningBy` luôn có cả true/false.
5. **Cho rằng `groupingBy(predicate)` luôn có hai key:** nhóm không có phần tử có thể không có key.
6. **Dựa vào thứ tự duyệt Map:** không được bảo đảm; truy cập `get(true)`/`get(false)` rõ ràng.
7. **Không xét null:** predicate gọi method trên phần tử null sẽ ném lỗi nếu không xử lý.
8. **Để predicate có side effect:** có thể khiến phép phân loại khó dự đoán và sai trên parallel.
9. **Sửa List chung bên ngoài bằng parallel forEach:** nguy cơ race condition; dùng collector.
10. **Nhầm downstream counting trả int:** `Collectors.counting()` trả `Long`.
11. **Nhầm downstream averagingInt trên nhánh rỗng với Optional.empty:** nó trả `Double` theo hợp đồng trung bình collector, với kết quả 0.0 cho nhánh không có mẫu.
12. **Gọi Optional.get trên kết quả maxBy của nhóm rỗng:** gây `NoSuchElementException`.
13. **Nhầm `Collectors.toList()` luôn trả ArrayList:** implementation và mutability không được cam kết.
14. **Dùng phân vùng hai nhánh cho bài toán ba hay nhiều trạng thái:** `groupingBy` hoặc cấu trúc khác thường phù hợp hơn.
15. **Tin rằng partitioningBy chỉ chạy một lần duy nhất qua source dù có nhiều terminal operations:** mỗi `collect` trên Stream mới kích hoạt một pipeline riêng.
16. **Cho rằng parallel partitioning luôn nhanh hơn sequential:** chi phí gộp, quản lý collector và ràng buộc thứ tự có thể cao.

## 13. Cách chọn nhanh theo yêu cầu

| Nhu cầu | API phù hợp |
| --- | --- |
| Chỉ cần các phần tử thỏa điều kiện | `stream.filter(predicate).toList()` |
| Cần cả nhóm đúng và sai | `collect(partitioningBy(predicate))` |
| Đếm nhóm đúng và sai | `collect(partitioningBy(predicate, counting()))` |
| Lấy danh sách tên ở mỗi nhóm | `collect(partitioningBy(predicate, mapping(..., toList())))` |
| Tổng một thuộc tính theo hai nhóm | `collect(partitioningBy(predicate, summingInt(...)))` |
| Thống kê min/max/avg/count theo hai nhóm | `collect(partitioningBy(predicate, summarizingInt(...)))` |
| Chia hai nhóm rồi phân loại theo khu vực | `collect(partitioningBy(predicate, groupingBy(...)))` |
| Nhóm theo nhiều nhãn (A/B/C/...) | `collect(groupingBy(classifier))` |
| Chỉ cần biết có phần tử nào thỏa không | `stream.anyMatch(predicate)` |

`partitioningBy` không phải lựa chọn mặc định cho mọi bài toán Boolean. Nếu mục tiêu chỉ là trả một boolean, `anyMatch`, `allMatch` hoặc `noneMatch` thường diễn đạt đúng hơn và có thể short-circuit. `partitioningBy` cần xử lý/tổng hợp các phần tử của hai nhánh, không phải tự động dừng khi gặp một phần tử đúng.

## 14. Bài tập tự kiểm tra

**Câu 1.** Với `List.of(1,2,3,4,5)`, `partitioningBy(n -> n > 3)` tạo hai nhóm nào?

**Đáp án:** `true -> [4, 5]` và `false -> [1, 2, 3]`.

**Câu 2.** Với Stream rỗng, `partitioningBy(predicate)` tạo bao nhiêu key?

**Đáp án:** Luôn **2** key: `true` và `false`. Mỗi giá trị là danh sách rỗng.

**Câu 3.** Nếu chỉ muốn đếm số học sinh đạt/chưa đạt mà không cần danh sách Student, dùng downstream nào?

**Đáp án:** `Collectors.counting()`, kết quả kiểu `Map<Boolean,Long>`.

**Câu 4.** Vì sao `groupingBy(n -> n % 2 == 0)` không hoàn toàn thay được `partitioningBy(n -> n % 2 == 0)`?

Vì `groupingBy` không bắt buộc tạo key cho nhóm không có phần tử, còn `partitioningBy` có hợp đồng hai phân vùng.

**Câu 5.** Có thể dùng `partitioningBy(predicate, Collectors.groupingBy(classifier))` không?

**Có.** Kết quả là Map hai nhánh Boolean, mỗi nhánh chứa một Map nhóm theo classifier. Đây là mẫu phân tích hai tầng.

**Câu 6.** Vì sao `parallelStream().forEach(x -> sharedList.add(x))` không thay thế an toàn cho collector?

**Đáp án:** `ArrayList` bên ngoài bị cập nhật đồng thời có thể gây race condition và thứ tự không xác định. Collector quản lý accumulator và combiner theo hợp đồng Stream.

**Câu 7.** Khi downstream dùng `maxBy` và một nhánh rỗng, `map.get(true)` có phải null không?

**Đáp án:** Key true vẫn tồn tại, nhưng giá trị của nó là `Optional.empty()` (nếu true là nhánh rỗng). Không gọi `get()` trên Optional rỗng.

**Câu 8.** Tại sao không nên in trực tiếp `Map<Boolean,List<T>>` rồi viết unit test trông chờ thứ tự key?

Vì thứ tự duyệt Map không phải hợp đồng của `partitioningBy`. Kiểm tra từng nhánh qua `get(true)` và `get(false)`, hoặc so sánh nội dung Map theo equality mà không dựa vào thứ tự hiển thị.

**Ghi nhớ:** **`partitioningBy(predicate)` chia Stream thành hai phân vùng `true`/`false` luôn tồn tại.** Khi cần nhiều hơn danh sách phần tử, thêm downstream collector để đếm, lấy thuộc tính, tính tổng, thống kê hoặc nhóm sâu. Nếu chỉ cần một nhánh, dùng `filter`; nếu cần nhiều khóa tùy ý, dùng `groupingBy`. Giữ Predicate rõ nghĩa và không có side effect để pipeline đáng tin cậy.
