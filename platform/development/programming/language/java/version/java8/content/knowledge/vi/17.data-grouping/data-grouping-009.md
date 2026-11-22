# Phân biệt không có nhóm với nhóm có tổng bằng không khi phân nhóm dữ liệu bằng Java Stream

Khi dùng `Collectors.groupingBy` và một collector tính tổng như `Collectors.summingInt`, hai câu hỏi **khác nhau** phải được trả lời riêng:

1. **Nhóm có tồn tại trong kết quả phân nhóm không?** Nghĩa là `Map` có chứa khóa nhóm đó hay không.
2. **Nếu nhóm tồn tại, tổng của nhóm bằng bao nhiêu?** Tổng `0` có thể là một kết quả tính toán hợp lệ.

Ví dụ một bộ phận có hai giao dịch `+50` và `-50` sẽ có tổng bằng `0`, nhưng bộ phận đó **đã xuất hiện trong dữ liệu**. Một bộ phận chưa có giao dịch nào thường **không có khóa** trong `Map` do `groupingBy` tạo ra. Việc hiển thị cả hai trường hợp thành “0” có thể làm sai báo cáo về tình trạng hoạt động, doanh thu, công nợ hoặc kiểm soát dữ liệu.

Bài học sử dụng các API Java vẫn đang áp dụng: `Stream`, `Collectors.groupingBy`, `summingInt`, `summarizingInt`, `Map.containsKey`, `getOrDefault` và, khi chạy trên Java 9 trở lên, `Collectors.filtering`. Ví dụ đầy đủ biên dịch trên **Java 17+**; các collector cơ bản đã có từ Java 8, còn cú pháp `record` trong ví dụ cần Java 16+.

## 1. Bản chất: sự tồn tại của khóa và giá trị tổng là hai thông tin riêng

Kết quả phân nhóm thường có kiểu:

```java
Map<String, Integer> sumByGroup
```

Trong đó:

- **Khóa** (`String`) mô tả nhóm, ví dụ mã phòng ban `"A"`.
- **Giá trị** (`Integer`) là tổng các số thuộc nhóm, ví dụ `0`, `25`, `-10`.
- `Map.containsKey(key)` trả lời **khóa có tồn tại hay không**.
- `Map.get(key)` trả giá trị nếu có mapping; thường trả `null` khi thiếu khóa. Với `Map` nói chung, giá trị `null` cũng có thể được lưu có chủ ý, vì vậy `get(key) == null` **không phải phép kiểm tra tồn tại khóa tổng quát**.
- `Map.getOrDefault(key, 0)` lấy tổng, hoặc cung cấp `0` nếu thiếu khóa. Cách này tiện để **hiển thị**, nhưng một mình kết quả `0` không còn cho biết có nhóm hay không.

Bảng đọc kết quả của `groupingBy(..., summingInt(...))`:

| Trạng thái dữ liệu | `containsKey("X")` | `get("X")` | `getOrDefault("X", 0)` | Diễn giải |
| --- | --- | --- | --- | --- |
| Không có phần tử nào của nhóm X sau bước tạo nhóm | `false` | `null` | `0` | **Không có nhóm X** trong kết quả |
| X có hai giá trị `+50` và `-50` | `true` | `0` | `0` | **Có nhóm X, tổng thuần bằng 0** |
| X có một phần tử giá trị `0` | `true` | `0` | `0` | **Có nhóm X, giá trị thực bằng 0** |
| X có giá trị `25` | `true` | `25` | `25` | Có nhóm X và tổng khác 0 |

Như vậy **`getOrDefault("X", 0) == 0` không chứng minh X đã tồn tại**. Muốn phân biệt, đọc thêm `containsKey("X")` hoặc mô hình hóa trạng thái tồn tại riêng.

### “Không có nhóm” phụ thuộc vào bước nào của pipeline?

Với cách dùng thông thường:

```java
source.stream().collect(Collectors.groupingBy(
        Item::group,
        Collectors.summingInt(Item::amount)))
```

`groupingBy` tạo khóa cho **những nhóm thực sự có phần tử đi tới collector**. Nếu Stream đầu vào của `groupingBy` rỗng, kết quả là `Map` rỗng. Một nhóm không xuất hiện trong dữ liệu đầu vào **không tự được thêm chỉ vì ta mong đợi nhóm đó trong báo cáo**.

Tuy nhiên, thứ tự đặt `filter` có thể thay đổi việc nhóm có mặt hay không (phần 4), và `partitioningBy` có hợp đồng khác (phần 5). Vì vậy hãy luôn ghi rõ **tập dữ liệu được coi là nguồn** khi nói “không có nhóm”.

## 2. Ví dụ Java 17+: kiểm tra khóa trước khi diễn giải số 0

Tạo tệp `GroupSumBasics.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class GroupSumBasics {
    record Movement(String group, int delta) {}

    public static void main(String[] args) {
        List<Movement> movements = Arrays.asList(
                new Movement("A", 50),
                new Movement("A", -50),
                new Movement("B", 0),
                new Movement("C", 25));

        Map<String, Integer> totals = movements.stream()
                .collect(Collectors.groupingBy(
                        Movement::group,
                        TreeMap::new,
                        Collectors.summingInt(Movement::delta)));

        System.out.println("totals = " + totals);

        for (String key : Arrays.asList("A", "B", "C", "D")) {
            System.out.println(key + ": present=" + totals.containsKey(key)
                    + ", sum=" + totals.get(key));
        }

        System.out.println("A default = " + totals.getOrDefault("A", 0));
        System.out.println("D default = " + totals.getOrDefault("D", 0));

        Map<String, IntSummaryStatistics> stats = movements.stream()
                .collect(Collectors.groupingBy(
                        Movement::group,
                        TreeMap::new,
                        Collectors.summarizingInt(Movement::delta)));

        System.out.println("A count=" + stats.get("A").getCount()
                + ", sum=" + stats.get("A").getSum());
        System.out.println("B count=" + stats.get("B").getCount()
                + ", sum=" + stats.get("B").getSum());

        Map<String, Integer> empty = Stream.<Movement>empty()
                .collect(Collectors.groupingBy(
                        Movement::group,
                        TreeMap::new,
                        Collectors.summingInt(Movement::delta)));
        System.out.println("empty grouping = " + empty);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 GroupSumBasics.java
java GroupSumBasics
```

Đầu ra:

```text
totals = {A=0, B=0, C=25}
A: present=true, sum=0
B: present=true, sum=0
C: present=true, sum=25
D: present=false, sum=null
A default = 0
D default = 0
A count=2, sum=0
B count=1, sum=0
empty grouping = {}
```

Đọc từng kết quả:

- `A` có **hai** bản ghi và tổng bằng `0` do bù trừ `+50`, `-50`.
- `B` có **một** bản ghi, bản thân giá trị bằng `0`.
- `C` có **một** bản ghi và tổng `25`.
- `D` **không có khóa** trong `totals`, nên `get("D")` là `null`.
- Hai lệnh `getOrDefault(..., 0)` đều in `0` cho `A` và `D`: chính điều này minh họa nguy cơ **mất thông tin về sự tồn tại** khi chỉ hiển thị tổng.
- `summarizingInt` giúp xem thêm `count`. Cả `A` lẫn `B` tổng bằng `0` nhưng số bản ghi khác nhau.
- Nguồn rỗng với `groupingBy` trả `{}`, không tự thêm nhóm có tổng `0`.

`TreeMap::new` được dùng để thứ tự khóa ổn định khi in kết quả; `groupingBy` không mặc định cam kết kiểu Map hoặc thứ tự lặp. `record` là cú pháp dữ liệu ngắn gọn có từ Java 16; nếu phải biên dịch trên đúng Java 8, thay `record` bằng lớp Java thông thường có getter, còn logic `groupingBy`/`summingInt`/`summarizingInt` vẫn áp dụng.

## 3. Kiểm tra tồn tại đúng cách: `containsKey`, `get` và `getOrDefault`

Xét một Map có tổng hợp:

```java
Map<String, Integer> totals = Map.of("A", 0, "B", 15);
```

Đoạn này sử dụng `Map.of` (Java 9+). Các cách đọc sau có ý nghĩa khác nhau:

```java
boolean aExists = totals.containsKey("A"); // true
boolean cExists = totals.containsKey("C"); // false

Integer aTotal = totals.get("A"); // 0
Integer cTotal = totals.get("C"); // null

int displayedA = totals.getOrDefault("A", 0); // 0
int displayedC = totals.getOrDefault("C", 0); // 0
```

Trong báo cáo cần phân biệt, hãy viết điều kiện theo thứ tự:

```java
String message;
if (!totals.containsKey(group)) {
    message = "NO_GROUP";
} else if (totals.get(group) == 0) {
    message = "PRESENT_SUM_ZERO";
} else {
    message = "PRESENT_SUM_NONZERO";
}
```

Các đoạn mã trên là **minh họa trong một phương thức**: cần khai báo biến `group` và import `java.util.Map`. Ví dụ `Map.of` không chạy trên Java 8; dùng `HashMap` hay `TreeMap` nếu cần tương thích Java 8.

**Tại sao không chỉ dùng `get(key) != null`?** Bởi `Map` nói chung có thể chứa mapping `key -> null`. Theo hợp đồng `Map`, `containsKey` là phép kiểm tra sự tồn tại của mapping, kể cả khi giá trị bằng `null`. Với các collector `summingInt` trong bài, các tổng cho nhóm được tạo ra là số khác `null`, nhưng mã truy cập Map tốt không nên ngầm gán quy tắc của một collector cho mọi kiểu Map.

**`getOrDefault` có sửa Map không?** Không; nó chỉ trả kết quả mặc định khi khóa thiếu. Trái lại, các lệnh `putIfAbsent(key, 0)` hoặc `computeIfAbsent(key, ...)` có thể tạo mapping mới. Sau khi thêm khóa nhân tạo, `containsKey` không còn phản ánh chính xác việc nhóm đã có trong dữ liệu nguồn hay chưa. Hãy giữ thông tin hiện diện từ trước nếu có bước bổ sung tất cả nhóm mong đợi.

## 4. `filter` trước và trong `groupingBy`: trường hợp dễ bị nhầm nhất

Một nhóm có thể **có dữ liệu gốc**, nhưng không có phần tử nào đạt điều kiện xét tổng, ví dụ không có giao dịch được duyệt.

Có hai cách đặt bộ lọc và chúng tạo kết quả Map khác nhau:

**Lọc trước khi phân nhóm:**

```java
items.stream()
        .filter(Item::approved)
        .collect(Collectors.groupingBy(
                Item::group, Collectors.summingInt(Item::amount)));
```

Các nhóm mà **mọi phần tử đều bị lọc bỏ** không còn xuất hiện ở collector `groupingBy`, vì collector không hề nhận phần tử thuộc nhóm đó.

**Lọc bên trong collector của từng nhóm** (Java 9+):

```java
items.stream()
        .collect(Collectors.groupingBy(
                Item::group,
                Collectors.filtering(
                        Item::approved,
                        Collectors.summingInt(Item::amount))));
```

`groupingBy` vẫn thấy từng `Item` và tạo khóa nhóm; collector `filtering` chỉ cho những item hợp lệ đi tới phép cộng. Với nhóm có dữ liệu gốc nhưng **không có item hợp lệ**, collector tính tổng tạo `0` cho nhóm đó.

> Phân biệt: “không có nhóm”, “nhóm có phần tử hợp lệ nhưng tổng bằng 0” và “nhóm gốc có tồn tại nhưng không có phần tử nào vượt qua điều kiện lọc” là **ba trạng thái nghiệp vụ khác nhau**. Nếu cần phân biệt cả ba, phải lưu thêm số phần tử đạt lọc.

`Collectors.filtering` được bổ sung từ **Java 9**; đây vẫn là API hiện hành, nhưng **không** có trong Java 8. Để đạt cùng mục đích trên Java 8, có thể phân nhóm dữ liệu gốc vào `Map<K, List<T>>` trước rồi lọc/tính tổng riêng trong từng nhóm, bảo toàn tập khóa gốc.

### Ví dụ Java 17+: hai vị trí của filter và bốn trạng thái

Tạo tệp `GroupAfterFilterDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupAfterFilterDemo {
    record Entry(String team, int amount, boolean approved) {}

    static String classify(
            String key,
            Map<String, Integer> sums,
            Map<String, Long> counts) {
        if (!sums.containsKey(key)) {
            return "NO_GROUP";
        }
        if (counts.get(key) == 0L) {
            return "GROUP_NO_MATCH";
        }
        return sums.get(key) == 0
                ? "MATCHED_SUM_ZERO"
                : "MATCHED_SUM_NONZERO";
    }

    public static void main(String[] args) {
        List<Entry> lines = List.of(
                new Entry("A", 10, false),
                new Entry("A", -10, false),
                new Entry("B", 7, true),
                new Entry("C", 0, true),
                new Entry("D", 3, false));

        Map<String, Integer> before = lines.stream()
                .filter(Entry::approved)
                .collect(Collectors.groupingBy(
                        Entry::team,
                        TreeMap::new,
                        Collectors.summingInt(Entry::amount)));

        Map<String, Integer> downstream = lines.stream()
                .collect(Collectors.groupingBy(
                        Entry::team,
                        TreeMap::new,
                        Collectors.filtering(
                                Entry::approved,
                                Collectors.summingInt(Entry::amount))));

        Map<String, Long> counts = lines.stream()
                .collect(Collectors.groupingBy(
                        Entry::team,
                        TreeMap::new,
                        Collectors.filtering(
                                Entry::approved,
                                Collectors.counting())));

        System.out.println("before = " + before);
        System.out.println("downstream = " + downstream);
        System.out.println("approved count = " + counts);

        for (String key : List.of("A", "B", "C", "D", "Z")) {
            System.out.println(key + " => " + classify(key, downstream, counts));
        }
    }
}
```

```bash
javac -encoding UTF-8 GroupAfterFilterDemo.java
java GroupAfterFilterDemo
```

```text
before = {B=7, C=0}
downstream = {A=0, B=7, C=0, D=0}
approved count = {A=0, B=1, C=1, D=0}
A => GROUP_NO_MATCH
B => MATCHED_SUM_NONZERO
C => MATCHED_SUM_ZERO
D => GROUP_NO_MATCH
Z => NO_GROUP
```

**Phân tích:**

| Mã | Có bản ghi gốc? | Bản ghi `approved` | Tổng được duyệt | Trạng thái |
| --- | ---: | ---: | ---: | --- |
| A | 2 | 0 | 0 | Nhóm có nhưng không có bản ghi đạt lọc |
| B | 1 | 1 | 7 | Nhóm có tổng khác 0 |
| C | 1 | 1 | 0 | Nhóm có tổng bằng 0 từ dữ liệu đạt lọc |
| D | 1 | 0 | 0 | Nhóm có nhưng không có bản ghi đạt lọc |
| Z | 0 | 0 | Không có mapping | Không có nhóm |

Map `before` không chứa `A` và `D` vì lọc diễn ra **trước** `groupingBy`. Map `downstream` vẫn chứa chúng với số `0` vì khóa được tạo từ dữ liệu gốc. `counts` cho biết có **bao nhiêu phần tử thực sự đóng góp vào phép tổng**, giúp phân biệt nhóm không có item hợp lệ với nhóm có item hợp lệ mà tổng `0`.

Dòng `counts.get(key) == 0L` chỉ chạy sau khi `sums.containsKey(key)` được kiểm tra. Trong ví dụ hai Map được thu thập từ **cùng dữ liệu gốc và cùng khóa**, nên một khóa xuất hiện ở `sums` cũng xuất hiện ở `counts`. Nếu dữ liệu được tính từ các nguồn khác nhau hoặc có biến đổi không đồng nhất, cần kiểm tra cả `counts.containsKey(key)` trước khi đọc `counts.get(key)`.

## 5. Ngoại lệ về ý nghĩa: `partitioningBy` chủ động tạo cả hai khóa Boolean

`Collectors.partitioningBy(predicate, downstream)` không giống `groupingBy` thông thường về tập khóa: kết quả của nó **luôn có mapping cho `true` và `false`**, kể cả khi nguồn không có phần tử nào thuộc một phía hoặc cả nguồn rỗng.

Vì vậy, với `partitioningBy`, `containsKey(true)` hoặc `containsKey(false)` **không chứng minh có phần tử**. Muốn biết nhánh có dữ liệu không, dùng downstream `counting` hoặc `summarizingInt` và đọc `count`.

Tạo tệp `PartitionDemo.java`:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class PartitionDemo {
    record Event(boolean active, int delta) {}

    public static void main(String[] args) {
        Map<Boolean, Integer> partitions = Stream.<Event>empty()
                .collect(Collectors.partitioningBy(
                        Event::active,
                        Collectors.summingInt(Event::delta)));

        System.out.println("partition true present = "
                + partitions.containsKey(true));
        System.out.println("partition false present = "
                + partitions.containsKey(false));
        System.out.println("partition true sum = " + partitions.get(true));
        System.out.println("partition false sum = " + partitions.get(false));
    }
}
```

```bash
javac -encoding UTF-8 PartitionDemo.java
java PartitionDemo
```

```text
partition true present = true
partition false present = true
partition true sum = 0
partition false sum = 0
```

Nguồn rỗng nhưng hai khóa đều có mặt. `0` ở đây là kết quả của downstream khi không có phần tử cho mỗi nhánh, **không phải bằng chứng giao dịch thực**. Hợp đồng “luôn có cả hai khóa” thuộc `partitioningBy`, không áp dụng mặc định cho `groupingBy`.

## 6. Nếu tổng bằng 0 nhưng muốn biết “đã phát sinh hoạt động” thì dùng thêm `count`

Một tổng bằng 0 có ít nhất hai cách giải thích:

- **Có một hoặc nhiều bản ghi**, tất cả giá trị bằng 0 hoặc các giá trị dương/âm triệt tiêu nhau.
- **Không có bản ghi đóng góp vào phép cộng** sau bước lọc, nên tổng dùng giá trị trung hòa `0`.

Dùng `Collectors.summarizingInt` để lấy cả `count` và `sum` từ **cùng tập phần tử đầu vào** khi không có bộ lọc phức tạp:

```java
Map<String, IntSummaryStatistics> statistics = movements.stream()
        .collect(Collectors.groupingBy(
                Movement::group,
                Collectors.summarizingInt(Movement::delta)));
```

Đoạn trên là mã minh họa trong phạm vi có `movements` và kiểu `Movement` của ví dụ mục 2. Khi có bộ lọc theo nhóm, dùng `Collectors.filtering(predicate, Collectors.summarizingInt(...))` trên Java 9+ để giữ khóa gốc và chỉ đếm/tổng các item đạt điều kiện. Nếu cần đồng thời biết **số bản ghi gốc** và **số bản ghi đạt lọc**, thu thêm một phép `counting` cho dữ liệu gốc hoặc thiết kế một accumulator có cả hai bộ đếm.

Lưu ý về loại số:

- `Collectors.counting()` trả `Long`; `IntSummaryStatistics.getCount()` trả `long`.
- `Collectors.summingInt` trả `Integer`, `summingLong` trả `Long`; với dữ liệu rất lớn cần nghĩ tới tràn số nguyên. Một kết quả `0` do tràn số **không tương đương** với tổng toán học thực.
- `IntSummaryStatistics.getSum()` trả `long` cho tổng các số `int`; đừng tự chuyển hẹp về `int` khi số lượng lớn.
- Với tiền hoặc số thập phân đòi hỏi độ chính xác, ưu tiên `BigDecimal` và quy tắc làm tròn/đơn vị tiền rõ ràng thay vì cộng số `double` tùy ý.

## 7. Tổng tiền bằng `BigDecimal.ZERO` và ý nghĩa của `equals`

Trong nghiệp vụ tiền tệ, một nhóm có thể có hai số tiền `1.10` và `-1.10`, cho tổng `0.00`. Không có collector chuẩn `summingBigDecimal` trong `Collectors`; có thể dùng `Collectors.reducing` với identity `BigDecimal.ZERO` và `BigDecimal::add`.

Tạo tệp `GroupMoneyDemo.java`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupMoneyDemo {
    record Posting(String team, BigDecimal amount) {}

    public static void main(String[] args) {
        List<Posting> transactions = List.of(
                new Posting("Ops", new BigDecimal("1.10")),
                new Posting("Ops", new BigDecimal("-1.10")),
                new Posting("HR", new BigDecimal("0.00")));

        Map<String, BigDecimal> sums = transactions.stream()
                .collect(Collectors.groupingBy(
                        Posting::team,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                Posting::amount,
                                BigDecimal::add)));

        System.out.println("Ops sum = " + sums.get("Ops").toPlainString());
        System.out.println("Ops equals ZERO = "
                + sums.get("Ops").equals(BigDecimal.ZERO));
        System.out.println("Ops compareTo ZERO = "
                + (sums.get("Ops").compareTo(BigDecimal.ZERO) == 0));
        System.out.println("Engineering present = "
                + sums.containsKey("Engineering"));
    }
}
```

```bash
javac -encoding UTF-8 GroupMoneyDemo.java
java GroupMoneyDemo
```

```text
Ops sum = 0.00
Ops equals ZERO = false
Ops compareTo ZERO = true
Engineering present = false
```

Giải thích: `BigDecimal.equals` so sánh cả giá trị lẫn **scale**, nên `new BigDecimal("0.00").equals(BigDecimal.ZERO)` là `false`. Khi chỉ quan tâm giá trị số có bằng 0 hay không, dùng `value.compareTo(BigDecimal.ZERO) == 0`. Nhưng phải **kiểm tra `containsKey` trước**: không nên gọi `compareTo` trên `null` khi nhóm vắng mặt. Nguồn dữ liệu có số tiền `null` cũng phải được xử lý theo chính sách nghiệp vụ trước khi cộng.

Đừng dùng biểu diễn số `0.00` để thay thế thông tin “không có nhóm”: số tiền bằng 0 là một giá trị có nghĩa, còn thiếu nhóm là một trạng thái hiện diện khác.

## 8. Khi báo cáo bắt buộc phải hiển thị cả các nhóm chưa có dữ liệu

Nhiều dashboard luôn phải hiển thị tất cả phòng ban, tỉnh thành hoặc loại giao dịch dù không có bản ghi phát sinh. Tập nhóm kỳ vọng có thể đến từ danh mục riêng, khác tập nhóm xuất hiện trong dữ liệu thực.

Nếu cần hiển thị `0` cho nhóm không phát sinh, vẫn phải giữ trạng thái thực tế:

```java
List<String> expectedGroups = List.of("A", "B", "C", "D");

for (String key : expectedGroups) {
    boolean presentInData = totals.containsKey(key);
    int displayTotal = totals.getOrDefault(key, 0);
    String status = presentInData ? "PRESENT" : "NO_DATA";
    System.out.println(key + ": " + displayTotal + " (" + status + ")");
}
```

Đoạn này là **mã minh họa** trong phương thức đã có `totals` như ví dụ mục 2; `List.of` cần Java 9+. Không nên tự `putIfAbsent("D", 0)` vào Map gốc trước khi kiểm tra, vì sau đó `D` sẽ trông như một nhóm thực sự được tạo từ Stream.

Nếu kiến trúc cần một DTO của từng hàng báo cáo, có thể lưu riêng:

```java
record GroupRow(String key, boolean observed, long itemCount, long sum) {}
```

Cú pháp `record` cần Java 16+ và ở đây chỉ minh họa mô hình dữ liệu. Ba chiều `observed`, `itemCount`, `sum` diễn đạt tốt hơn một giá trị `sum` đơn lẻ. Khi yêu cầu phân biệt “chưa có dữ liệu” với “đã có giao dịch nhưng số dư bằng 0”, đây là phần dữ liệu cần được lưu hoặc tính trước khi chuẩn hóa đầu ra.

### Nên chọn cấu trúc nào?

| Nhu cầu | Cách làm gợi ý |
| --- | --- |
| Chỉ muốn tính tổng cho những nhóm có bản ghi | `groupingBy(..., summingInt(...))` |
| Muốn xem nhóm có tồn tại không | `containsKey(key)` trước khi đọc tổng |
| Muốn hiện 0 trên UI khi thiếu nhóm nhưng vẫn nhận biết là thiếu | `containsKey` + `getOrDefault(key, 0)`, giữ hai thông tin |
| Muốn biết số bản ghi thực góp vào tổng | `summarizingInt` hoặc `counting` đi kèm |
| Muốn giữ nhóm gốc dù mọi bản ghi bị loại bởi điều kiện | `groupingBy(..., filtering(...))` trên Java 9+ |
| Muốn biết nhóm gốc không có bản ghi đạt lọc | Thu thêm `counting` trên chính tập phần tử sau lọc |
| Muốn hiển thị đủ danh mục cố định | Kết hợp danh mục nhóm kỳ vọng với `Map`, lưu cờ hiện diện |
| Muốn cộng tiền chính xác | `BigDecimal` + `reducing`; kiểm tra 0 bằng `compareTo` |

## 9. Những lỗi thường gặp

1. **Chỉ kiểm tra `sum == 0`.** Kết quả `0` có thể là nhóm hiện diện, nhóm không có item đạt lọc, hoặc giá trị dự phòng của nhóm vắng mặt. Tách riêng cờ hiện diện, số lượng và tổng.
2. **Dùng `getOrDefault(key, 0)` để kết luận nhóm tồn tại.** Hàm này cố ý cho giá trị mặc định khi khóa thiếu; nó không cung cấp trạng thái tồn tại. Cần `containsKey`.
3. **Quên vị trí của `filter`.** `stream.filter` có thể xóa hẳn nhóm trước `groupingBy`; downstream `Collectors.filtering` (Java 9+) có thể giữ khóa và trả tổng 0.
4. **Cho rằng `partitioningBy` là `groupingBy` hai nhóm thông thường.** `partitioningBy` luôn tạo hai khóa Boolean, kể cả khi Stream rỗng. Khi cần “có phần tử thật không”, kiểm tra `count`.
5. **Gộp “không có bản ghi” với “tổng thuần 0”.** Một nhóm có giao dịch thu và chi bù trừ có thể tổng 0 nhưng vẫn phát sinh hoạt động; dùng thêm `count` hoặc chỉ số nghiệp vụ phù hợp.
6. **Thêm trước tất cả khóa với giá trị `0` rồi mới đo sự tồn tại.** Nếu `put`/`putIfAbsent` đã thêm khóa kỳ vọng, trạng thái “xuất hiện trong dữ liệu gốc” đã bị làm mờ. Giữ Map gốc bất biến hoặc ghi riêng cờ nguồn.
7. **Cho rằng mọi `Map.get(key) == null` đều có nghĩa là không có khóa.** Một số Map cho phép `null` làm giá trị. Kiểm tra `containsKey` khi cần phân biệt tồn tại mapping.
8. **Không kiểm soát null/overflow/đơn vị.** Phép tính tổng có thể lỗi khi mapper dùng unboxing `null`, tràn `int/long` hoặc cộng sai đơn vị. Giá trị `0` chỉ có ý nghĩa nếu dữ liệu và phép cộng hợp lệ.
9. **Đọc kết quả nhóm từ một Stream đã tiêu thụ.** `collect` là terminal operation; để tạo Map tổng, Map đếm từ cùng nguồn Collection, cần gọi `list.stream()` mới mỗi lần, không tái sử dụng một đối tượng Stream.
10. **Lấy nhóm không có trong Map rồi unbox về `int`.** `int total = totals.get("missing")` ném `NullPointerException` do unboxing `null`. Phân biệt khóa thiếu bằng `containsKey` hoặc xử lý mặc định có chủ đích.

## 10. Bài tập kiểm tra

**Câu 1.** Với dữ liệu `[("A", 5), ("A", -5)]`, kết quả `groupingBy` với `summingInt` có khóa `"A"` không? Giá trị tổng là gì?  
**Đáp án:** Có khóa `"A"`, tổng `0`. Hai phần tử đã được đưa vào nhóm.

**Câu 2.** Map tổng không có khóa `"B"`. `getOrDefault("B", 0)` trả `0`. Có thể suy ra B có dữ liệu gốc không?  
**Đáp án:** Không. Giá trị `0` là mặc định khi thiếu khóa; cần `containsKey("B")`.

**Câu 3.** Stream có 3 bản ghi thuộc nhóm X nhưng tất cả bị `filter` loại trước `groupingBy`. Nhóm X có trong Map tổng không?  
**Đáp án:** Không, nếu không còn bản ghi X nào đi vào `groupingBy`.

**Câu 4.** Vẫn có 3 bản ghi X nhưng dùng downstream `Collectors.filtering` bên trong `groupingBy`, không bản ghi nào đạt lọc. Tổng X là gì và nên kiểm tra gì thêm?  
**Đáp án:** Nhóm X vẫn có mapping, tổng thường `0` với `summingInt`. Thu thêm `counting` trên phần tử đạt lọc để xác định `count=0`; API `Collectors.filtering` có từ Java 9.

**Câu 5.** `partitioningBy` trên Stream rỗng có khóa Boolean nào?  
**Đáp án:** Cả `true` và `false`; không được suy ra có phần tử chỉ từ `containsKey`.

**Câu 6.** Một nhóm tổng tiền `BigDecimal("0.00")`: tại sao `equals(BigDecimal.ZERO)` có thể sai?  
**Đáp án:** `equals` xét cả scale; dùng `compareTo(BigDecimal.ZERO) == 0` để so sánh giá trị số, sau khi xác minh nhóm thực sự tồn tại.

## 11. Ghi nhớ

**Tập khóa và giá trị tổng phải được đọc riêng.** Với `groupingBy` thông thường, khóa vắng mặt biểu thị nhóm không được tạo từ dữ liệu đi tới collector. Khóa hiện diện có tổng `0` biểu thị một nhóm đã được tạo ra nhưng tổng tính được bằng 0; nhóm đó có thể có nhiều giá trị bù trừ hoặc không có giá trị đạt bộ lọc downstream.

Một báo cáo đúng khi cần phân biệt nên nắm ít nhất `groupPresent` và `sum`; nếu quan trọng số giao dịch hoặc kết quả lọc thì lưu cả `itemCount`. Chỉ trả một số `0` không đủ để xác định ba trạng thái này.

### Tài liệu API Java chính thức

- [Collectors — `groupingBy`, `summingInt`, `summarizingInt`, `counting`, `filtering` và `partitioningBy`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): xem hợp đồng và khác biệt của các collector.
- [Map — `containsKey`, `get`, `getOrDefault`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html): tồn tại mapping và xử lý giá trị mặc định.
- [IntSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IntSummaryStatistics.html): `getCount` và `getSum`.
- [BigDecimal](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html): so sánh `equals` và `compareTo`.
